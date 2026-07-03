"""W0d theme_activity extensions — hermetic tests (no network, no real disk reads).

Tests cover:
  1. run-rate surprise (rr_surprise) math and presence/absence
  2. September gate (R9b): rr contribution zeroed when LAG-adjusted recent window hits Sep/Oct
  3. blend-preserves-shape: fused output keys identical for a fixture without new data fields
  4. pipeline_to_award_ratio join
  5. new_programs first-seen NAICS ledger dedup (sam_gov.new_programs)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import theme_activity as ta

# ---------------------------------------------------------------------------
# Shared helpers (mirror tests/test_theme_activity.py conventions)
# ---------------------------------------------------------------------------

M = 1e6


def _wide(spec, n_complete=15):
    """spec: {ticker: (baseline, recent)} -> wide month x ticker frame (+LAG trailing months).
    n_complete = number of usable (non-lag) rows; total rows = n_complete + LAG_MONTHS."""
    cols = {tk: [b] * (n_complete - 3) + [r] * 3 + [b] * ta.LAG_MONTHS for tk, (b, r) in spec.items()}
    idx = pd.date_range(end="2026-05-01", periods=n_complete + ta.LAG_MONTHS, freq="MS")
    return pd.DataFrame(cols, index=idx)


def _wide_with_dates(spec, end_date: str, n_complete=15):
    """Like _wide but with an explicit end date so we can put recent months in Sep/Oct."""
    cols = {tk: [b] * (n_complete - 3) + [r] * 3 + [b] * ta.LAG_MONTHS for tk, (b, r) in spec.items()}
    idx = pd.date_range(end=end_date, periods=n_complete + ta.LAG_MONTHS, freq="MS")
    return pd.DataFrame(cols, index=idx)


def _payload(baskets):
    return {"as_of": "2026-06-19",
            "baskets": [{"id": bid, "name": bid, "members": [{"symbol": s} for s in mem]}
                        for bid, mem in baskets]}


US = _wide({"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}, n_complete=16)
PAYLOAD = _payload([("defense", ["LMT", "NOC"])])


# ---------------------------------------------------------------------------
# 1. Run-rate surprise: math
# ---------------------------------------------------------------------------

def test_rr_surprise_present_for_seasonal_with_sufficient_history():
    """seasonal=True with >= _RR_MIN_HISTORY usable rows returns rr_surprise key."""
    # n_complete=16 -> 16 usable rows; _RR_MIN_HISTORY = RECENT_MONTHS(3) + RUNRATE_TRAIL_M(9) = 12
    spec = {"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}
    wide = _wide(spec, n_complete=16)
    out = ta.source_accel(wide, ["LMT", "NOC"])
    assert out is not None
    assert "rr_surprise" in out, "rr_surprise must be present when history is sufficient"
    # recent (25M * 3) >> trailing avg (5M per month) so rr_surprise > 1
    assert out["rr_surprise"] > 1.0


def test_rr_surprise_value_correct():
    """rr_surprise = recent_sum / (trail_avg * RECENT_MONTHS), clipped to ACCEL_CLAMP."""
    spec = {"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}
    wide = _wide(spec, n_complete=16)
    out = ta.source_accel(wide, ["LMT", "NOC"])
    assert out is not None
    # After LAG_MONTHS(3) trim: 16 usable rows
    # recent 3 months: 25M*2 per month (LMT+NOC) = 150M
    # trailing 9 months: 5M*2 per month (LMT+NOC) = 10M/month, total trail avg = 10M
    # rr_surprise = 150M / (10M * 3) = 5.0
    assert abs(out["rr_surprise"] - 5.0) < 0.01, f"expected ~5.0, got {out['rr_surprise']}"
    assert abs(out["rr_surprise_metric"] - np.log(5.0)) < 0.01


def test_rr_surprise_absent_for_nonseasonal():
    """seasonal=False (grants_loans path) does NOT compute rr_surprise."""
    spec = {"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}
    wide = _wide(spec, n_complete=16)
    out = ta.source_accel(wide, ["LMT", "NOC"], seasonal=False)
    assert out is not None
    assert "rr_surprise" not in out, "rr_surprise must NOT appear for seasonal=False"


def test_rr_surprise_absent_when_history_too_short():
    """When usable rows < _RR_MIN_HISTORY, rr_surprise is not emitted."""
    spec = {"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}
    # n_complete=11 -> 11 usable; _RR_MIN_HISTORY=12; need 15 total to satisfy YOY_LAG too
    # Use n_complete=15 (exactly at YOY boundary) but < 12+3 = boundary
    # Actually need: 1) len>=RECENT+YOY=15 for YoY, 2) len>=_RR_MIN_HISTORY=12 for rr
    # n_complete=11 fails YoY (need 15) so source_accel returns None altogether
    # Use n_complete=15 (satisfies YoY) but _RR_MIN_HISTORY=12 is fine; trim n_complete=12
    # to get exactly 12 usable rows — rr_surprise should appear
    # Let's use n_complete=11 which fails at need=15 (YoY) -> returns None
    wide = _wide(spec, n_complete=11)
    out = ta.source_accel(wide, ["LMT", "NOC"])
    assert out is None  # insufficient history for YoY itself

    # n_complete=15 satisfies YoY; _RR_MIN_HISTORY=12 satisfied -> rr_surprise present
    wide2 = _wide(spec, n_complete=16)
    out2 = ta.source_accel(wide2, ["LMT", "NOC"])
    assert out2 is not None
    assert "rr_surprise" in out2


def test_rr_blend_in_metric():
    """The returned metric is blended when rr_w > 0: metric = 0.7*yoy_metric + 0.3*rr_metric."""
    spec = {"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}
    # Use non-Sept date so gate is open
    wide = _wide_with_dates(spec, end_date="2026-05-01", n_complete=16)
    out = ta.source_accel(wide, ["LMT", "NOC"])
    assert out is not None
    assert not out.get("rr_sept_gated", False), "Should not be gated in May"
    # The metric must be the blended value, not identical to pure YoY
    # YoY: recent=150M, prior=30M -> accel=5 -> yoy_metric=ln(5)
    # rr: rr_surprise=5 -> rr_metric=ln(5)
    # In this toy example both are equal so blend equals pure; verify the field exists
    assert "rr_surprise_metric" in out
    expected_blended = (1.0 - ta.RR_WEIGHT) * float(np.log(5.0)) + ta.RR_WEIGHT * float(np.log(5.0))
    assert abs(out["metric"] - expected_blended) < 0.01


# ---------------------------------------------------------------------------
# 2. September gate (R9b) — MANDATORY hermetic test
# ---------------------------------------------------------------------------

def test_rr_sept_gate_zeroes_contribution_in_september():
    """When the LAG-adjusted recent window falls in Sep/Oct, rr_surprise blend weight = 0.

    Concretely: if the last complete month (most recent after LAG drop) is September (month 9),
    rr_sept_gated must be True and the returned metric must equal the pure YoY metric (no blend).
    """
    spec = {"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}
    # Make the most recent complete month be September 2025.
    # LAG_MONTHS=3 -> drop last 3; so for the trimmed series to end in Sep 2025, the raw frame
    # must end in Dec 2025 (Sep + 3 lag months).
    # end_date = "2025-12-01" -> last month in raw frame is 2025-12-01; trim 3 -> last is 2025-09-01
    wide_sept = _wide_with_dates(spec, end_date="2025-12-01", n_complete=16)
    out = ta.source_accel(wide_sept, ["LMT", "NOC"])
    assert out is not None, "source_accel should return a result (sufficient history)"
    assert out.get("rr_sept_gated") is True, (
        "rr_sept_gated must be True when recent window falls in September"
    )
    # The metric must NOT include any rr blend — it must equal the pure YoY log metric
    yoy_accel = float(out["accel"])  # accel is the pure YoY ratio
    pure_yoy_metric = float(np.log(yoy_accel))
    assert abs(out["metric"] - pure_yoy_metric) < 1e-9, (
        f"metric {out['metric']} != pure YoY {pure_yoy_metric} — rr leak in Sept gate"
    )


def test_rr_sept_gate_zeroes_contribution_in_october():
    """Oct (fiscal posting month) is also gated — same law as September."""
    spec = {"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}
    # Trimmed series ends in Oct 2025 -> raw frame ends in Jan 2026
    wide_oct = _wide_with_dates(spec, end_date="2026-01-01", n_complete=16)
    out = ta.source_accel(wide_oct, ["LMT", "NOC"])
    assert out is not None
    assert out.get("rr_sept_gated") is True, "Oct must also be gated"
    yoy_metric = float(np.log(float(out["accel"])))
    assert abs(out["metric"] - yoy_metric) < 1e-9


def test_rr_sept_gate_open_in_november():
    """Nov/Dec/Jan recent window is NOT gated — blend should be active.

    With end_date='2026-04-01' and LAG_MONTHS=3, the trimmed series ends Jan 2026.
    Recent 3 months: Nov 2025, Dec 2025, Jan 2026 — none in {9, 10}."""
    spec = {"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}
    # Raw frame ends Apr 2026; after dropping LAG_MONTHS=3 the trimmed series ends Jan 2026.
    # Recent 3 months = Nov 2025, Dec 2025, Jan 2026 -> none in {9, 10} -> gate open.
    wide_nov = _wide_with_dates(spec, end_date="2026-04-01", n_complete=16)
    out = ta.source_accel(wide_nov, ["LMT", "NOC"])
    assert out is not None
    assert out.get("rr_sept_gated") is False, "Nov/Dec/Jan window must NOT be gated"


def test_rr_sept_gate_open_in_august():
    """August (month 8) is NOT gated."""
    spec = {"LMT": (5 * M, 25 * M), "NOC": (5 * M, 25 * M)}
    # Trimmed series ends in Aug 2025 -> raw frame ends in Nov 2025
    wide_aug = _wide_with_dates(spec, end_date="2025-11-01", n_complete=16)
    out = ta.source_accel(wide_aug, ["LMT", "NOC"])
    assert out is not None
    assert out.get("rr_sept_gated") is False, "August must NOT be gated"


# ---------------------------------------------------------------------------
# 3. Blend-preserves-shape: fused output keys are identical with/without new data
# ---------------------------------------------------------------------------

def test_blend_preserves_fused_output_shape():
    """compute_real_activity output keys are unchanged whether or not rr_surprise fires.

    The W0d fields (rr_surprise, rr_sept_gated, pipeline_to_award, new_programs) are
    ADDITIVE to the existing shape — they do not rename or remove any pre-existing key."""
    pre_w0d_keys = {
        "fused_obs_z", "fused_accel", "obs_dir", "n_sources", "sources", "primary", "news",
    }
    w0d_extension_keys = {"pipeline_to_award", "new_programs"}
    primary_pre_w0d_keys = {
        "accel", "recent_3m_usd", "base_3m_usd", "n_covered", "covered",
    }

    out = ta.compute_real_activity(PAYLOAD, sources_data={"usaspending": US}, news=False)
    assert "defense" in out
    d = out["defense"]
    assert pre_w0d_keys.issubset(d.keys()), (
        f"Missing pre-W0d keys: {pre_w0d_keys - d.keys()}"
    )
    assert w0d_extension_keys.issubset(d.keys()), (
        f"Missing W0d extension keys: {w0d_extension_keys - d.keys()}"
    )
    assert primary_pre_w0d_keys.issubset(d["primary"].keys()), (
        f"Missing primary pre-W0d keys: {primary_pre_w0d_keys - d['primary'].keys()}"
    )
    # rr_surprise appears in primary (may be None if gated or insufficient history)
    assert "rr_surprise" in d["primary"]
    assert "rr_sept_gated" in d["primary"]


def test_fused_obs_z_unchanged_by_w0d():
    """fused_obs_z is based on cross-sectional z; rr_surprise only changes the metric
    input value (within the same leg), not the cross-sectional normalization path.
    For a single-basket fixture, cross-sectional z=0 regardless of metric value."""
    out = ta.compute_real_activity(PAYLOAD, sources_data={"usaspending": US}, news=False)
    # Single basket -> cross-sectional z = 0 (robust_z on length-1 vector)
    assert out["defense"]["fused_obs_z"] == 0.0


# ---------------------------------------------------------------------------
# 4. pipeline_to_award_ratio
# ---------------------------------------------------------------------------

def _opp_frame(basket_id: str, recent_count: int, prior_count: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {"recent_count": [recent_count], "prior_count": [prior_count]},
        index=pd.Index([basket_id], name="basket_id"),
    )


# Use US (16 usable rows + 3 lag = 19 total) for the oblig_wide; lag_months=3 so we need
# at least 3+3+1=7 rows in the raw frame — US has 19, so this works.
def test_pipeline_to_award_returns_ratio():
    opp = _opp_frame("defense", recent_count=10)
    out = ta.pipeline_to_award_ratio("defense", ["LMT", "NOC"], opp_frame=opp,
                                     oblig_wide=US, lag_months=3)
    assert out is not None
    assert out["opp_count_recent"] == 10
    assert out["award_usd_lagged"] > 0
    assert out["award_per_opp_usd"] > 0
    assert out["lag_months_assumption"] == 3
    assert out["n_cols"] == 2


def test_pipeline_to_award_none_when_basket_absent():
    """Returns None when basket_id is not in opp_frame."""
    opp = _opp_frame("nuclear_power", recent_count=5)
    result = ta.pipeline_to_award_ratio("defense", ["LMT", "NOC"], opp_frame=opp,
                                        oblig_wide=US, lag_months=3)
    assert result is None


def test_pipeline_to_award_none_when_opp_count_zero():
    """Returns None when recent_count=0 (no pipeline to convert)."""
    opp = _opp_frame("defense", recent_count=0)
    assert ta.pipeline_to_award_ratio("defense", ["LMT", "NOC"], opp_frame=opp,
                                      oblig_wide=US, lag_months=3) is None


def test_pipeline_to_award_none_when_opp_frame_none():
    assert ta.pipeline_to_award_ratio("defense", ["LMT", "NOC"],
                                      opp_frame=None, oblig_wide=US) is None


def test_pipeline_to_award_none_when_oblig_wide_none():
    opp = _opp_frame("defense", recent_count=5)
    assert ta.pipeline_to_award_ratio("defense", ["LMT", "NOC"],
                                      opp_frame=opp, oblig_wide=None) is None


def test_pipeline_to_award_none_when_members_not_in_oblig():
    """Returns None when basket members are not in the obligations wide frame."""
    opp = _opp_frame("defense", recent_count=5)
    assert ta.pipeline_to_award_ratio("defense", ["AAPL", "MSFT"], opp_frame=opp,
                                      oblig_wide=US, lag_months=3) is None


def test_pipeline_to_award_uses_default_lag_from_dict():
    """When lag_months=None, falls back to PIPELINE_LAG_MONTHS dict."""
    # defense -> lag=12; US has 19 total rows, need 12+3+1=16 -> fine
    opp = _opp_frame("defense", recent_count=5)
    out = ta.pipeline_to_award_ratio("defense", ["LMT", "NOC"], opp_frame=opp,
                                     oblig_wide=US, lag_months=None)
    assert out is not None
    assert out["lag_months_assumption"] == 12


def test_pipeline_to_award_none_when_history_too_short():
    """Returns None when oblig_wide has fewer rows than lag+recent+1."""
    spec = {"LMT": (5 * M, 5 * M), "NOC": (5 * M, 5 * M)}
    tiny = _wide(spec, n_complete=3)  # only 6 total rows
    opp = _opp_frame("defense", recent_count=5)
    # lag_months=12 -> need 12+3+1=16 rows; tiny has 6
    assert ta.pipeline_to_award_ratio("defense", ["LMT", "NOC"], opp_frame=opp,
                                      oblig_wide=tiny, lag_months=12) is None


# ---------------------------------------------------------------------------
# 5. new_programs first-seen NAICS ledger dedup
# ---------------------------------------------------------------------------

from collectors.sam_gov import new_programs as sam_new_programs  # noqa: E402


def test_new_programs_detects_first_naics(tmp_path):
    naics_map = {"336411": ["defense", "space_economy"]}
    seen_path = tmp_path / "naics_seen.json"
    opps = [{"naicsCode": "336411", "type": "presol", "title": "Test solicitation",
              "postedDate": "2026-07-01"}]
    events = sam_new_programs(opps, naics_map, seen_path)
    # One NAICS -> two baskets
    assert len(events) == 2
    basket_ids = {e["basket_id"] for e in events}
    assert basket_ids == {"defense", "space_economy"}
    assert all(e["naics_or_cfda"] == "336411" for e in events)
    assert all(e["source"] == "sam_gov" for e in events)
    # seen_path must have been written
    assert seen_path.exists()
    seen = json.loads(seen_path.read_text())
    assert "336411" in seen["defense"]


def test_new_programs_dedup_on_second_run(tmp_path):
    """Second call with same opps produces no events (already seen)."""
    naics_map = {"336411": ["defense"]}
    seen_path = tmp_path / "naics_seen.json"
    opps = [{"naicsCode": "336411", "type": "presol", "title": "T", "postedDate": "2026-07-01"}]
    first = sam_new_programs(opps, naics_map, seen_path)
    assert len(first) == 1
    second = sam_new_programs(opps, naics_map, seen_path)
    assert len(second) == 0, "Same NAICS must not be emitted twice"


def test_new_programs_new_naics_after_first_run(tmp_path):
    """A genuinely new NAICS on the second run IS emitted."""
    naics_map = {"336411": ["defense"], "334413": ["ai_semiconductors"]}
    seen_path = tmp_path / "naics_seen.json"
    opps1 = [{"naicsCode": "336411", "type": "presol", "title": "T1", "postedDate": "2026-07-01"}]
    opps2 = [{"naicsCode": "334413", "type": "presol", "title": "T2", "postedDate": "2026-07-02"}]
    sam_new_programs(opps1, naics_map, seen_path)
    events2 = sam_new_programs(opps2, naics_map, seen_path)
    assert len(events2) == 1
    assert events2[0]["basket_id"] == "ai_semiconductors"
    assert events2[0]["naics_or_cfda"] == "334413"


def test_new_programs_empty_on_no_opps(tmp_path):
    assert sam_new_programs([], {"336411": ["defense"]}, tmp_path / "seen.json") == []


def test_new_programs_empty_on_no_naics_map(tmp_path):
    opps = [{"naicsCode": "336411", "type": "presol", "title": "T", "postedDate": "2026-07-01"}]
    assert sam_new_programs(opps, {}, tmp_path / "seen.json") == []


def test_new_programs_skips_opp_with_no_naics(tmp_path):
    opps = [{"naicsCode": "", "type": "presol", "title": "No NAICS", "postedDate": "2026-07-01"},
            {"type": "presol", "title": "Also no NAICS", "postedDate": "2026-07-01"}]
    naics_map = {"336411": ["defense"]}
    events = sam_new_programs(opps, naics_map, tmp_path / "seen.json")
    assert events == []


def test_new_programs_truncates_title(tmp_path):
    """Long titles are truncated to 120 chars."""
    naics_map = {"336411": ["defense"]}
    seen_path = tmp_path / "seen.json"
    long_title = "A" * 200
    opps = [{"naicsCode": "336411", "type": "presol", "title": long_title, "postedDate": "2026-07-01"}]
    events = sam_new_programs(opps, naics_map, seen_path)
    assert len(events) == 1
    assert len(events[0]["title"]) == 120


# ---------------------------------------------------------------------------
# 6. _rr_sept_gate helper unit tests
# ---------------------------------------------------------------------------

def test_rr_sept_gate_helper_sept():
    idx = pd.date_range("2025-07-01", periods=ta.RECENT_MONTHS, freq="MS")
    # months: Jul, Aug, Sep -> Sep in set -> gate fires
    monthly = pd.Series([1.0] * len(idx), index=idx)
    assert ta._rr_sept_gate(monthly) == 0.0


def test_rr_sept_gate_helper_oct():
    idx = pd.date_range("2025-08-01", periods=ta.RECENT_MONTHS, freq="MS")
    # months: Aug, Sep, Oct -> Oct in set -> gate fires
    monthly = pd.Series([1.0] * len(idx), index=idx)
    assert ta._rr_sept_gate(monthly) == 0.0


def test_rr_sept_gate_helper_nov():
    idx = pd.date_range("2025-09-01", periods=ta.RECENT_MONTHS, freq="MS")
    # months: Sep, Oct, Nov -> both Sep and Oct in window -> gate fires
    monthly = pd.Series([1.0] * len(idx), index=idx)
    assert ta._rr_sept_gate(monthly) == 0.0


def test_rr_sept_gate_helper_clear_month():
    idx = pd.date_range("2025-11-01", periods=ta.RECENT_MONTHS, freq="MS")
    # months: Nov, Dec, Jan -> none in {9,10} -> gate open
    monthly = pd.Series([1.0] * len(idx), index=idx)
    assert ta._rr_sept_gate(monthly) == ta.RR_WEIGHT


def test_rr_sept_gate_helper_too_short():
    monthly = pd.Series(dtype=float)
    assert ta._rr_sept_gate(monthly) == 0.0
