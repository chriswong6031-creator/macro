"""Tests for engine/desk_grader.py — the unified forward desk grader.

Two seams are exercised:
  * REAL price math — synthetic data/yahoo/<T>.parquet written under tmp_path, so the
    trading-day maturation + coverage-skip + missing-parquet-degrade paths run for real.
  * LOGIC — _fwd_rel monkeypatched to a fixed map, so IC / on-desk-vs-departed split /
    velocity / alarm gating are deterministic and independent of the price layer.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from engine import desk_grader as G  # noqa: E402

_OLD = date(2026, 1, 5)           # snapshot date
_NOW = date(2026, 6, 21)          # well past every horizon


def _rows(n=14, score_base=10):
    """n alt_data-style surfaced rows, ascending score, all long."""
    out = []
    for i in range(n):
        out.append({"ticker": f"T{i:02d}", "rank": i + 1, "score": score_base + i * 5,
                    "lean": 1, "entry_tier": "T1" if i >= n - 3 else None})
    return out


# --------------------------------------------------------------------------- #
# 1. snapshot idempotency + leave detection
# --------------------------------------------------------------------------- #
def test_snapshot_idempotent(tmp_path):
    rows = _rows()
    r1 = G.snapshot_desk("alt_data", rows, _OLD, root=tmp_path)
    assert r1["n_new"] == len(rows)
    r2 = G.snapshot_desk("alt_data", rows, _OLD, root=tmp_path)          # same day → no re-append
    assert r2["n_new"] == 0 and r2["n_departed"] == 0
    r3 = G.snapshot_desk("alt_data", rows, _OLD + timedelta(days=1), root=tmp_path)
    assert r3["n_new"] == len(rows)


def test_junk_ticker_filtered(tmp_path):
    rows = _rows(3) + [{"ticker": "N/A", "score": 0, "lean": 0},
                       {"ticker": "", "score": 0, "lean": 1}]
    r = G.snapshot_desk("alt_data", rows, _OLD, root=tmp_path)
    assert r["n_new"] == 3                                                # placeholders dropped


def test_leave_detection_writes_departure(tmp_path):
    day1 = _rows(6)
    G.snapshot_desk("alt_data", day1, _OLD, root=tmp_path)
    # day2 drops T00 and T01
    day2 = _rows(6)[2:]
    r = G.snapshot_desk("alt_data", day2, _OLD + timedelta(days=1), root=tmp_path)
    assert r["n_departed"] == 2
    rows = G._load_jsonl(G._snap_path(tmp_path, "alt_data"))
    deps = {x["ticker"] for x in rows if x.get("departed")}
    assert deps == {"T00", "T01"}
    dep_row = next(x for x in rows if x.get("departed") and x["ticker"] == "T00")
    assert dep_row["left_desk"] == (_OLD + timedelta(days=1)).isoformat()
    assert dep_row["last_score"] == 10                                   # T00's last on-desk score


def test_empty_desk_day_does_not_mass_evict(tmp_path):
    G.snapshot_desk("alt_data", _rows(6), _OLD, root=tmp_path)
    r = G.snapshot_desk("alt_data", [], _OLD + timedelta(days=1), root=tmp_path)
    assert r["n_departed"] == 0                                          # empty day → no evictions


def test_name_leaves_then_returns(tmp_path):
    G.snapshot_desk("alt_data", _rows(6), _OLD, root=tmp_path)           # T00..T05
    G.snapshot_desk("alt_data", _rows(6)[1:], _OLD + timedelta(days=1), root=tmp_path)  # drop T00 → departure
    ret = _rows(6)                                                       # T00 back
    r = G.snapshot_desk("alt_data", ret, _OLD + timedelta(days=2), root=tmp_path)
    assert any(x["ticker"] == "T00" for x in [x for x in G._load_jsonl(G._snap_path(tmp_path, "alt_data")) if not x.get("departed") and x["date"] == (_OLD + timedelta(days=2)).isoformat()])
    # a NEW live snapshot for T00 exists on day3, and the day1 departure marker also exists
    all_rows = G._load_jsonl(G._snap_path(tmp_path, "alt_data"))
    assert any(x["ticker"] == "T00" and x.get("departed") for x in all_rows)
    live_t00_dates = sorted(x["date"] for x in all_rows if x["ticker"] == "T00" and not x.get("departed"))
    assert (_OLD + timedelta(days=2)).isoformat() in live_t00_dates      # re-arm recorded


# --------------------------------------------------------------------------- #
# 2. REAL price maturation on synthetic yahoo parquets
# --------------------------------------------------------------------------- #
def _write_yahoo(root: Path, ticker: str, closes: list[float], start="2026-01-01"):
    """Write a business-day close series to tmp/data/yahoo/<T>.parquet."""
    idx = pd.bdate_range(start=start, periods=len(closes))
    df = pd.DataFrame({"close": closes, "volume": [1e6] * len(closes)}, index=idx)
    p = root / "data" / "yahoo" / f"{ticker}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)


def test_fwd_ret_trading_days(tmp_path):
    G._reset_px_cache()
    # 60 business days; ticker +1%/day compounding-ish via linear ramp, SPY flat
    closes = [100.0 + i for i in range(60)]                             # 100,101,...159
    _write_yahoo(tmp_path, "AAA", closes)
    _write_yahoo(tmp_path, "SPY", [200.0] * 60)                         # bench flat → rel == abs
    start = pd.bdate_range("2026-01-01", periods=60)[0].strftime("%Y-%m-%d")
    ret5, cov5 = G._fwd_ret_trading("AAA", tmp_path, start, 5)
    assert cov5 is True
    assert ret5 == pytest.approx((105.0 / 100.0) - 1.0)                 # exactly 5 trading bars later
    rel5, reason = G._fwd_rel("AAA", tmp_path, start, 5)
    assert reason == "ok" and rel5 == pytest.approx(ret5)              # SPY flat → rel == abs


def test_immature_and_missing_price_degrade(tmp_path):
    G._reset_px_cache()
    _write_yahoo(tmp_path, "AAA", [100.0 + i for i in range(8)])       # only 8 bars
    _write_yahoo(tmp_path, "SPY", [200.0] * 8)
    start = pd.bdate_range("2026-01-01", periods=8)[0].strftime("%Y-%m-%d")
    # horizon 30 has NOT elapsed (only 8 bars) → immature coverage skip, not a wrong number
    rel, reason = G._fwd_rel("AAA", tmp_path, start, 30)
    assert rel is None and reason == "immature"
    # a name not in yahoo → no_price (NOT a breadth-cache fallthrough)
    rel2, reason2 = G._fwd_rel("ZZZ_NOT_IN_YAHOO", tmp_path, start, 5)
    assert rel2 is None and reason2 == "no_price"


def test_coverage_pct_reported(tmp_path):
    G._reset_px_cache()
    # AAA fully covered, BBB missing → coverage 50%
    _write_yahoo(tmp_path, "AAA", [100.0 + i for i in range(60)])
    _write_yahoo(tmp_path, "SPY", [200.0] * 60)
    start = pd.bdate_range("2026-01-01", periods=60)[0].strftime("%Y-%m-%d")
    G.snapshot_desk("alt_data", [{"ticker": "AAA", "score": 80, "lean": 1},
                                 {"ticker": "BBB", "score": 40, "lean": 1}],
                    start, root=tmp_path)
    out = G.compute("alt_data", _NOW, root=tmp_path)
    cov = out["horizons"]["5"]["coverage"]
    assert cov["eligible"] == 2 and cov["ok"] == 1 and cov["no_price"] == 1
    assert cov["coverage_pct"] == 50.0


# --------------------------------------------------------------------------- #
# 3. IC / split / velocity / alarm — monkeypatched price layer
# --------------------------------------------------------------------------- #
def _patch_fwd(monkeypatch, fmap):
    monkeypatch.setattr(G, "_fwd_rel", lambda t, root, start, h: (fmap.get(t), "ok")
                        if fmap.get(t) is not None else (None, "no_price"))


def test_positive_ic_and_departed_split(tmp_path, monkeypatch):
    # 8 dates × 12 names; score ranks the forward return → positive IC, proven gate can fire.
    fwd = {f"N{i:02d}": (i - 5) * 0.01 for i in range(12)}
    for k in range(8):
        rows = [{"ticker": f"N{i:02d}", "rank": i + 1, "score": 10 + i * 6, "lean": 1}
                for i in range(12)]
        G.snapshot_desk("alt_data", rows, _OLD + timedelta(days=k), root=tmp_path)
    _patch_fwd(monkeypatch, fwd)
    out = G.compute("alt_data", _NOW, root=tmp_path)
    h5 = out["horizons"]["5"]
    d = h5["level_ic_daily"]
    assert d.get("mean_ic") is not None and d["mean_ic"] > 0.9
    assert h5["level_ic"] == d["mean_ic"]
    assert h5["status"] == "proven"                                    # n≥40 + HAC-t + positive
    assert out["any_proven"] and out["lead_time_d"] in G.HORIZONS


def test_alarm_on_significant_negative_ic(tmp_path, monkeypatch):
    # score INVERSELY ranks the forward return → significant NEGATIVE IC → 'alarm'
    fwd = {f"N{i:02d}": -(i - 5) * 0.01 for i in range(12)}
    for k in range(8):
        rows = [{"ticker": f"N{i:02d}", "rank": i + 1, "score": 10 + i * 6, "lean": 1}
                for i in range(12)]
        G.snapshot_desk("alt_data", rows, _OLD + timedelta(days=k), root=tmp_path)
    _patch_fwd(monkeypatch, fwd)
    out = G.compute("alt_data", _NOW, root=tmp_path)
    h5 = out["horizons"]["5"]
    assert h5["level_ic"] < 0 and h5["status"] == "alarm"
    assert out["any_alarm"]
    assert any(f["severity"] == "alarm" for f in out["auto_findings"])


def test_velocity_axis_computed(tmp_path, monkeypatch):
    # one name, rising score across 7 snapshots → velocity defined from the 6th snapshot on.
    for k in range(7):
        G.snapshot_desk("alt_data", [{"ticker": "AAA", "score": 10 + k * 5, "lean": 1},
                                     {"ticker": "BBB", "score": 90 - k * 5, "lean": 1}],
                        _OLD + timedelta(days=k), root=tmp_path)
    rows = G._load_desk("alt_data", tmp_path)
    vel = G._velocity(rows)
    # AAA on day6 (index 5) has 5 prior snaps → vel = score[5]-score[0] = (10+25)-(10) = 25
    key = ("AAA", (_OLD + timedelta(days=5)).isoformat())
    assert key in vel and vel[key] == pytest.approx(25.0)
    # BBB falling → negative velocity
    kb = ("BBB", (_OLD + timedelta(days=5)).isoformat())
    assert vel[kb] == pytest.approx(-25.0)


def test_velocity_ic_side_by_side(tmp_path, monkeypatch):
    # 8 dates, 10 names; forward return tracks the score CHANGE not the level → velocity IC > level.
    n_names = 10
    for k in range(8):
        rows = []
        for i in range(n_names):
            # every name drifts up by i each day → level roughly constant ranking, velocity ranks by i
            rows.append({"ticker": f"V{i:02d}", "score": 50 + i * k, "lean": 1})
        G.snapshot_desk("alt_data", rows, _OLD + timedelta(days=k), root=tmp_path)
    # fwd return proportional to i (the velocity driver)
    fwd = {f"V{i:02d}": (i - 4) * 0.01 for i in range(n_names)}
    _patch_fwd(monkeypatch, fwd)
    out = G.compute("alt_data", _NOW, root=tmp_path)
    h5 = out["horizons"]["5"]
    assert h5["velocity_n"] > 0                                         # velocity axis populated
    # velocity only defined from the 6th snapshot on → <6 dates → the daily-HAC path abstains
    # (correct: it needs enough dates), but the POOLED velocity IC is available and, by
    # construction here, ranks the forward return better than the level IC (owner's hypothesis).
    assert h5["velocity_ic_pooled"] is not None
    assert h5["velocity_ic_pooled"] > (h5["level_ic_pooled"] or -1)


def test_on_desk_vs_departed_grading(tmp_path, monkeypatch):
    # T00 leaves on day3; its day1/day2 snaps are on-desk, later ones (none) after. Ensure the
    # split runs and departed grading continues from historical snapshot dates.
    for k in range(3):
        G.snapshot_desk("alt_data", _rows(6), _OLD + timedelta(days=k), root=tmp_path)
    # day4: drop T00 → departure
    G.snapshot_desk("alt_data", _rows(6)[1:], _OLD + timedelta(days=3), root=tmp_path)
    fwd = {f"T{i:02d}": 0.02 for i in range(6)}
    _patch_fwd(monkeypatch, fwd)
    out = G.compute("alt_data", _NOW, root=tmp_path)
    h5 = out["horizons"]["5"]
    # T00's snapshots (dates all < departure date) are on-desk; nothing after → departed n small/0
    assert h5["overall"]["n"] >= h5["on_desk"]["n"]
    assert h5["on_desk"]["n"] > 0


# --------------------------------------------------------------------------- #
# 4. intel_hub adapter + degrade
# --------------------------------------------------------------------------- #
def test_hub_adapter_reshapes_and_no_double_snapshot(tmp_path):
    import json
    # write a mini hub ledger; the adapter must read it WITHOUT a desk-grader snapshot write
    hub_p = tmp_path / "data" / "hub" / "signal_snapshots.jsonl"
    hub_p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for k in range(2):
        for i in range(5):
            lines.append(json.dumps({"date": (_OLD + timedelta(days=k)).isoformat(),
                                     "t": f"H{i:02d}", "opp": 50 + i * 5, "edge": 0.5,
                                     "stage": "emerging", "lean": 1}))
    lines.append(json.dumps({"date": _OLD.isoformat(), "t": "N/A", "opp": 0, "lean": 0}))  # junk
    hub_p.write_text("\n".join(lines) + "\n")
    adapted = G._load_hub_adapter(tmp_path)
    live = [r for r in adapted if not r.get("departed")]
    assert all("score" in r and r["ticker"] != "N/A" for r in live)     # opp→score, junk filtered
    assert len(live) == 10
    # snapshot_desk on intel_hub is a NO-OP write (adapter mode)
    r = G.snapshot_desk("intel_hub", [{"ticker": "X", "score": 1}], _NOW, root=tmp_path)
    assert r.get("adapter") is True and r["n_new"] == 0
    assert not G._snap_path(tmp_path, "intel_hub").exists()             # no separate ledger written


def test_compute_accruing_when_empty(tmp_path):
    out = G.compute("congress", _NOW, root=tmp_path)
    assert out["schema"] == G.SCHEMA and out["desk"] == "congress"
    assert out["any_matured"] is False and out["n_snapshots_live"] == 0
    assert "Accruing" in out["note"] or "accruing" in out["note"]


def test_corrupt_jsonl_line_skipped(tmp_path):
    p = G._snap_path(tmp_path, "alt_data")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"date":"2026-01-05","ticker":"AAA","score":50,"lean":1}\n'
                 'THIS IS NOT JSON\n'
                 '{"date":"2026-01-05","ticker":"BBB","score":40,"lean":1}\n')
    rows = G._load_jsonl(p)
    assert len(rows) == 2 and {r["ticker"] for r in rows} == {"AAA", "BBB"}


def test_bad_desk_name_degrades(tmp_path):
    out = G.compute("not_a_desk", _NOW, root=tmp_path)
    assert out["horizons"] == {} and out["any_matured"] is False        # never raises


# --------------------------------------------------------------------------- #
# 5. notes + seed
# --------------------------------------------------------------------------- #
def test_seed_notes_idempotent(tmp_path):
    n1 = G.seed_notes(root=tmp_path)
    assert n1 == len(G._SEED_NOTES)
    n2 = G.seed_notes(root=tmp_path)
    assert n2 == 0                                                      # already seeded
    notes = G._load_notes(tmp_path, "intel_hub")
    assert notes and all(x["desk"] in ("intel_hub", "all", None) for x in notes)


def test_add_note_appends(tmp_path):
    G.seed_notes(root=tmp_path)
    assert G.add_note("alt_data", "convergence IC negative at n=61 → watch", root=tmp_path)
    notes = G._load_notes(tmp_path, "alt_data")
    assert any("convergence IC negative" in x["note"] for x in notes)
