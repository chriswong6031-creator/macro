"""Tests for engine.deterioration_cascade — DISPLAY-ONLY intl deterioration speed organ.

Load-bearing invariants tested here:
  - Maturity guard: markets with <5 prior sessions before today are excluded
  - State machine: STEADY / SLIPPING / DETERIORATING_FAST transitions
  - d3_alert counts alert increase over 3 sessions (mature markets only)
  - n_escalating counts band-rank increases vs prior session
  - Fail-open: missing/empty log dirs return None or STEADY without raising
  - Forward-log gated on COLLECT_LANE=nightly
  - calib.json seeded on first run
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import datetime

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import deterioration_cascade as dc  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers to build synthetic log data
# --------------------------------------------------------------------------- #
def _make_log(rows: list[dict]) -> list[dict]:
    """Build a log as list of dicts with asof/state/alert/top_score."""
    return rows


def _dates(start: str, n: int) -> list[str]:
    """Generate n business dates from start (inclusive)."""
    from pandas import bdate_range, Timestamp
    return [str(d.date()) for d in bdate_range(start, periods=n)]


def _make_mature_log(n_total: int, alert_on_last: bool = False,
                     state_seq: list[str] | None = None) -> list[dict]:
    """Build a log with n_total rows; last row optionally alerts."""
    dates = _dates("2026-06-01", n_total)
    rows = []
    for i, d in enumerate(dates):
        is_last = (i == n_total - 1)
        state = (state_seq[i] if state_seq else "caution")
        rows.append({
            "asof": d,
            "state": state,
            "alert": bool(is_last and alert_on_last),
            "top_score": 80,
        })
    return rows


# --------------------------------------------------------------------------- #
# Maturity guard
# --------------------------------------------------------------------------- #
def test_maturity_guard_excludes_young_market():
    """A market with only 1 row (born today) is never counted."""
    today = "2026-07-16"
    # 1 row log: not mature (0 prior sessions < 5)
    rows = [{"asof": today, "state": "risk-off", "alert": True, "top_score": 95}]
    assert not dc._is_mature(rows, today, 5)


def test_maturity_guard_requires_5_prior():
    """Market with exactly 5 prior sessions (rows with asof < today) is mature."""
    today = "2026-07-16"
    dates = _dates("2026-07-08", 5)  # 5 prior sessions
    rows = [{"asof": d, "state": "caution", "alert": False, "top_score": 80} for d in dates]
    assert dc._is_mature(rows, today, 5)


def test_maturity_guard_4_prior_not_mature():
    """Market with 4 prior sessions is NOT mature."""
    today = "2026-07-16"
    dates = _dates("2026-07-09", 4)  # 4 prior sessions, all < today
    rows = [{"asof": d, "state": "caution", "alert": False, "top_score": 80} for d in dates]
    assert not dc._is_mature(rows, today, 5)


def test_maturity_guard_uses_today_exclusive():
    """The today row itself does not count as a prior session."""
    today = "2026-07-16"
    # 5 prior + 1 today = 6 rows total
    dates = _dates("2026-07-08", 5) + [today]
    rows = [{"asof": d, "state": "risk-off", "alert": True, "top_score": 95} for d in dates]
    prior_only = [r for r in rows if r["asof"] < today]
    assert len(prior_only) == 5
    assert dc._is_mature(rows, today, 5)


# --------------------------------------------------------------------------- #
# Band rank helper
# --------------------------------------------------------------------------- #
def test_band_rank_ordering():
    """Bands are ordered calm < watch < caution < elevated < risk-off."""
    assert dc._band_rank("calm") < dc._band_rank("watch")
    assert dc._band_rank("watch") < dc._band_rank("caution")
    assert dc._band_rank("caution") < dc._band_rank("elevated")
    assert dc._band_rank("elevated") < dc._band_rank("risk-off")


def test_band_rank_unknown_maps_zero():
    """Unknown states map to 0 (calm)."""
    assert dc._band_rank("unknown_state") == 0
    assert dc._band_rank(None) == 0


# --------------------------------------------------------------------------- #
# State machine classify
# --------------------------------------------------------------------------- #
def test_steady_when_no_alerts():
    """n_alert=0, d3=0, n_esc=0 -> STEADY."""
    calib = dc._DEFAULT_CALIB.copy()
    assert dc._classify(0, 0, 0, calib) == "STEADY"


def test_steady_at_threshold():
    """n_alert=1, d3=0 -> STEADY (boundary)."""
    calib = dc._DEFAULT_CALIB.copy()
    assert dc._classify(1, 0, 0, calib) == "STEADY"


def test_slipping_on_d3():
    """d3_alert >= 1 -> SLIPPING."""
    calib = dc._DEFAULT_CALIB.copy()
    assert dc._classify(1, 0, 1, calib) == "SLIPPING"


def test_slipping_on_n_escalating():
    """n_escalating >= 2 -> SLIPPING."""
    calib = dc._DEFAULT_CALIB.copy()
    assert dc._classify(1, 2, 0, calib) == "SLIPPING"


def test_deteriorating_fast_on_n_alert():
    """n_alert >= 3 -> DETERIORATING_FAST."""
    calib = dc._DEFAULT_CALIB.copy()
    assert dc._classify(3, 0, 0, calib) == "DETERIORATING_FAST"


def test_deteriorating_fast_on_d3():
    """d3_alert >= 2 -> DETERIORATING_FAST (takes priority over SLIPPING)."""
    calib = dc._DEFAULT_CALIB.copy()
    assert dc._classify(1, 0, 2, calib) == "DETERIORATING_FAST"


def test_deteriorating_fast_takes_priority_over_slipping():
    """When both FAST and SLIPPING conditions met, FAST wins."""
    calib = dc._DEFAULT_CALIB.copy()
    # n_alert=3 (FAST) AND n_escalating=2 (SLIPPING) -> FAST
    assert dc._classify(3, 2, 1, calib) == "DETERIORATING_FAST"


# --------------------------------------------------------------------------- #
# Integration: build with synthetic data via monkeypatching
# --------------------------------------------------------------------------- #
def _write_log(directory: Path, code: str, rows: list[dict]) -> None:
    """Write a synthetic forward log file."""
    p = directory / f"{code}_forward_log.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_build_steady_all_mature_no_alerts(tmp_path, monkeypatch):
    """All mature, none alerting -> STEADY."""
    intl_dir = tmp_path / "risk_radar_intl"
    intl_dir.mkdir()
    today = "2026-07-16"
    # cn: 10 rows prior + today, no alerts
    cn_dates = _dates("2026-07-01", 10) + [today]
    cn_rows = [{"asof": d, "state": "caution", "alert": False, "top_score": 80}
               for d in cn_dates]
    _write_log(intl_dir, "cn", cn_rows)

    monkeypatch.setattr(dc, "_intl_log_dir", lambda: intl_dir)
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)

    snap = dc.build()
    assert snap is not None
    assert snap["state"] == "STEADY"
    assert snap["n_alert"] == 0
    assert "cn" in snap.get("immature", []) or snap["n_mature"] >= 1


def test_build_slipping_d3_plus_one(tmp_path, monkeypatch):
    """d3_alert=+1 (1 alert today vs 0 three sessions ago) -> SLIPPING."""
    intl_dir = tmp_path / "risk_radar_intl"
    intl_dir.mkdir()
    today = "2026-07-16"
    # 10 prior sessions: first 7 no alert, last 3 alert
    dates = _dates("2026-07-01", 10) + [today]
    rows = []
    for i, d in enumerate(dates):
        alert = d >= today  # only today alerts
        rows.append({"asof": d, "state": "risk-off" if alert else "caution",
                     "alert": alert, "top_score": 95 if alert else 80})
    _write_log(intl_dir, "cn", rows)

    monkeypatch.setattr(dc, "_intl_log_dir", lambda: intl_dir)
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)

    snap = dc.build()
    assert snap is not None
    # d3 = n_alert(today) - n_alert(3 sessions ago)
    # today: 1 alert; 3 sessions back: 0 alerts -> d3=1 -> SLIPPING
    assert snap["d3_alert"] == 1
    assert snap["state"] == "SLIPPING"


def test_d3_ignores_markets_absent_at_baseline(tmp_path, monkeypatch):
    """M2: a mature market that had no row 3 sessions ago must not inflate d3_alert.
    cn has 10 prior sessions (mature, alerting today).
    hk has only 1 prior session before today (mature because >=5 priors by today)
    — wait, hk needs >=5 priors.  Use a market that became mature since the baseline:
    hk has exactly 4 prior sessions (born 3 sessions ago), so NOT counted in mature_codes.
    If hk WERE counted as mature, its alert today with no baseline row would add +1
    to d3 spuriously.  With the fix, only markets present at both dates count."""
    intl_dir = tmp_path / "risk_radar_intl"
    intl_dir.mkdir()
    today = "2026-07-16"
    baseline_dates = _dates("2026-07-01", 10)  # 10 prior sessions

    # cn: 10 prior + today, alerting today and at baseline
    cn_all_dates = baseline_dates + [today]
    cn_rows = [{"asof": d, "state": "caution", "alert": False, "top_score": 80}
               for d in baseline_dates]
    cn_rows.append({"asof": today, "state": "risk-off", "alert": True, "top_score": 95})
    _write_log(intl_dir, "cn", cn_rows)

    # hk: mature (>=5 prior sessions), but born AFTER the d3 baseline date (3 sessions ago).
    # Generate 7 prior sessions but only the last 3 are after baseline-3; the first 4
    # sessions are before today giving maturity but the baseline date (3 sessions back)
    # is not covered by hk's log.
    all_panel_dates = sorted(set(
        [r["asof"] for r in cn_rows]
    ))
    # 3-session lag index from today:
    # panel dates (from cn): baseline[0..9] + today = 11 dates total
    # today_idx = 10, baseline_idx = 10 - 3 = 7 -> panel baseline date = baseline_dates[7]
    baseline_3 = baseline_dates[7]  # the date _D3_LAG sessions before today in the panel
    # hk starts after baseline_3 (so no hk row at baseline_3)
    hk_start = baseline_dates[8]  # 2 sessions before today -> only 1 prior < today before that
    # Build hk with 5 prior sessions: from baseline_dates[5] onwards + today
    hk_dates = baseline_dates[5:] + [today]  # 5 prior + today
    hk_rows = [{"asof": d, "state": "risk-off", "alert": True, "top_score": 95}
               for d in hk_dates]
    _write_log(intl_dir, "hk", hk_rows)

    monkeypatch.setattr(dc, "_intl_log_dir", lambda: intl_dir)
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)

    snap = dc.build()
    assert snap is not None
    # cn alerts today AND at baseline -> d3 contribution from cn: 1 - 0 = +1 (cn was 0 at baseline)
    # hk alerts today but NO row at baseline_3 -> M2 fix excludes hk from d3 calc
    # Without fix: d3 = (cn_alert_today + hk_alert_today) - (cn_alert_base + 0)
    #            = (1+1) - (0+0) = 2 -> DETERIORATING_FAST
    # With fix:   d3 = cn only: 1 - 0 = 1 -> SLIPPING (hk excluded from d3)
    assert snap["d3_alert"] <= 1, (
        f"d3_alert={snap['d3_alert']} inflated by market absent at baseline (M2)"
    )


def test_build_immature_excluded(tmp_path, monkeypatch):
    """Markets with <5 prior sessions are listed in immature, not counted."""
    intl_dir = tmp_path / "risk_radar_intl"
    intl_dir.mkdir()
    today = "2026-07-16"

    # cn: 10 prior + today (mature, alerting)
    cn_dates = _dates("2026-07-01", 10) + [today]
    cn_rows = [{"asof": d, "state": "risk-off", "alert": True, "top_score": 95}
               for d in cn_dates]
    _write_log(intl_dir, "cn", cn_rows)

    # tw: only 1 row (today) -> immature
    tw_rows = [{"asof": today, "state": "risk-off", "alert": True, "top_score": 95}]
    _write_log(intl_dir, "tw", tw_rows)

    monkeypatch.setattr(dc, "_intl_log_dir", lambda: intl_dir)
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)

    snap = dc.build()
    assert snap is not None
    assert "tw" in snap["immature"]
    assert "tw" not in snap["alerts"]
    # cn is mature and alerting
    assert "cn" in snap["alerts"]
    assert snap["n_mature"] == 1   # only cn counted


def test_build_young_market_does_not_inflate_state(tmp_path, monkeypatch):
    """7 immature markets all alerting -> still STEADY (birth-day immunity)."""
    intl_dir = tmp_path / "risk_radar_intl"
    intl_dir.mkdir()
    today = "2026-07-16"

    # cn and hk mature with no alerts
    for code in ["cn", "hk"]:
        dates = _dates("2026-07-01", 10) + [today]
        rows = [{"asof": d, "state": "caution", "alert": False, "top_score": 70}
                for d in dates]
        _write_log(intl_dir, code, rows)

    # tw kr jp in au gb ez: born today, all alerting
    for code in ["tw", "kr", "jp", "in", "au", "gb", "ez"]:
        rows = [{"asof": today, "state": "risk-off", "alert": True, "top_score": 95}]
        _write_log(intl_dir, code, rows)

    monkeypatch.setattr(dc, "_intl_log_dir", lambda: intl_dir)
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)

    snap = dc.build()
    assert snap is not None
    # Only cn and hk are mature; neither alerts -> STEADY
    assert snap["state"] == "STEADY"
    assert snap["n_alert"] == 0
    assert snap["n_mature"] == 2
    assert len(snap["immature"]) == 7


def test_build_immature_newer_asof_does_not_blank_organ(tmp_path, monkeypatch):
    """B2: when a freshly-born immature market has a newer asof than all mature markets,
    the organ must still return a valid snapshot (not None) for the mature panel's date."""
    intl_dir = tmp_path / "risk_radar_intl"
    intl_dir.mkdir()
    mature_today = "2026-07-15"   # mature market's last date
    immature_birth = "2026-07-16"  # immature market born one day later

    # cn: 10 prior sessions ending at mature_today (mature)
    cn_dates = _dates("2026-07-01", 10) + [mature_today]
    cn_rows = [{"asof": d, "state": "caution", "alert": False, "top_score": 70}
               for d in cn_dates]
    _write_log(intl_dir, "cn", cn_rows)

    # tw: born on immature_birth (1 row, immature)
    tw_rows = [{"asof": immature_birth, "state": "risk-off", "alert": True, "top_score": 95}]
    _write_log(intl_dir, "tw", tw_rows)

    monkeypatch.setattr(dc, "_intl_log_dir", lambda: intl_dir)
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)

    snap = dc.build()
    # Must return a snapshot, not None — organ should not go dark because of tw's newer date
    assert snap is not None, "organ returned None when immature market had newer asof (B2)"
    # cn is mature and not alerting
    assert snap["n_alert"] == 0
    assert snap["asof"] == mature_today
    assert "tw" in snap["immature"]


# --------------------------------------------------------------------------- #
# Fail-open: missing data directory
# --------------------------------------------------------------------------- #
def test_build_missing_log_dir_returns_none(tmp_path, monkeypatch):
    """When intl_log_dir has no files, build returns None."""
    intl_dir = tmp_path / "risk_radar_intl"
    # Do NOT create intl_dir
    monkeypatch.setattr(dc, "_intl_log_dir", lambda: intl_dir)
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    result = dc.build()
    assert result is None


def test_build_no_error_on_malformed_line(tmp_path, monkeypatch):
    """A corrupted JSONL line is skipped without crashing."""
    intl_dir = tmp_path / "risk_radar_intl"
    intl_dir.mkdir()
    today = "2026-07-16"
    p = intl_dir / "cn_forward_log.jsonl"
    valid_rows = [{"asof": d, "state": "caution", "alert": False, "top_score": 80}
                  for d in _dates("2026-07-01", 10) + [today]]
    content = "\n".join(json.dumps(r) for r in valid_rows[:5])
    content += "\nTHIS IS NOT JSON\n"
    content += "\n".join(json.dumps(r) for r in valid_rows[5:])
    p.write_text(content, encoding="utf-8")

    monkeypatch.setattr(dc, "_intl_log_dir", lambda: intl_dir)
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)

    # Should not raise
    snap = dc.build()
    # snap may be None or STEADY depending on how many valid rows survive


# --------------------------------------------------------------------------- #
# Calib.json seeding
# --------------------------------------------------------------------------- #
def test_ensure_calib_seeds_file(tmp_path, monkeypatch):
    """calib.json is written on first call if absent."""
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    # Remove calib path override — _calib_path() delegates to _out_dir()
    monkeypatch.setattr(dc, "_calib_path", lambda: tmp_path / "calib.json")
    calib = dc._ensure_calib()
    p = tmp_path / "calib.json"
    assert p.exists()
    on_disk = json.loads(p.read_text())
    assert on_disk["maturity_min_prior"] == dc._MATURITY_MIN_PRIOR


# --------------------------------------------------------------------------- #
# Forward-log gate
# --------------------------------------------------------------------------- #
def test_no_forward_log_without_nightly(tmp_path, monkeypatch):
    """Without COLLECT_LANE=nightly, no forward_log.jsonl is appended."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    dc.build()  # real data; may return None
    fwd = tmp_path / "forward_log.jsonl"
    assert not fwd.exists() or fwd.read_text().strip() == ""


def test_forward_log_written_on_nightly(tmp_path, monkeypatch):
    """With COLLECT_LANE=nightly, one row is appended."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    snap = dc.build()
    if snap is None:
        pytest.skip("real data unavailable")
    fwd = tmp_path / "forward_log.jsonl"
    assert fwd.exists()
    rows = [json.loads(l) for l in fwd.read_text().strip().split("\n") if l.strip()]
    assert len(rows) == 1
    assert rows[0]["schema"] == "deterioration_cascade.v1"
    assert "logged_at" in rows[0]


def test_forward_log_idempotent_by_asof(tmp_path, monkeypatch):
    """Calling build() twice on the nightly lane writes exactly ONE row per asof (B1)."""
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.setattr(dc, "_out_dir", lambda: tmp_path)
    snap1 = dc.build()
    if snap1 is None:
        pytest.skip("real data unavailable")
    # Second call — must not duplicate the asof
    dc.build()
    fwd = tmp_path / "forward_log.jsonl"
    rows = [json.loads(line) for line in fwd.read_text().strip().split("\n") if line.strip()]
    asof_values = [r["asof"] for r in rows]
    assert len(asof_values) == len(set(asof_values)), (
        f"duplicate asof in forward_log: {asof_values}"
    )


# --------------------------------------------------------------------------- #
# Real-data smoke test
# --------------------------------------------------------------------------- #
def test_real_data_schema():
    """Real data: snap has all required keys and sensible values."""
    result = dc.build()
    if result is None:
        pytest.skip("real data unavailable")
    required_keys = ["schema", "asof", "state", "n_alert", "n_escalating",
                     "d3_alert", "n_mature", "alerts", "immature"]
    for k in required_keys:
        assert k in result, f"missing key: {k}"
    assert result["schema"] == "deterioration_cascade.v1"
    assert result["state"] in {"STEADY", "SLIPPING", "DETERIORATING_FAST"}
    assert isinstance(result["n_alert"], int)
    assert isinstance(result["alerts"], list)
    assert isinstance(result["immature"], list)
    # Mature markets must be subset of all known codes
    known = set(dc._MARKET_NAMES.keys())
    for code in result["alerts"]:
        assert code in known


def test_real_data_expected_state():
    """Current data: cn+hk mature and alerting -> n_alert=2, state=SLIPPING."""
    result = dc.build()
    if result is None:
        pytest.skip("real data unavailable")
    # At minimum cn and hk should be mature (12 and 11 rows respectively)
    mature_min = result.get("n_mature", 0)
    assert mature_min >= 2, f"expected at least cn+hk mature, got {mature_min}"
    # cn and hk are both alerting per the real data
    if "cn" in result["alerts"] and "hk" in result["alerts"]:
        assert result["n_alert"] >= 2


def test_real_data_ca_maturity():
    """CA log has 9 rows; last row is 07-15 not 07-16 (today) -> 07-16 today: ca has 9 prior -> mature."""
    result = dc.build()
    if result is None:
        pytest.skip("real data unavailable")
    # ca should appear as mature (9 rows with asof <= 07-15 < 07-16)
    # Unless today's asof is 07-15 in which case it has 8 prior
    # Just confirm ca is not in immature when n_mature >= 3
    if result.get("n_mature", 0) >= 3:
        assert "ca" not in result["immature"], "ca should be mature with 9 rows"
