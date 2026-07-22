"""Tests for the Bottom Ledger P1 — the policy-free bottom-calling learning instrument.

Covers (design: research/signal_engine/BOTTOM_LEDGER_DESIGN.md, PR #3182):
* engine.bottom_ruler.grade_call: exact synthetic pins (known trough / undercut → hand-computed
  numbers), the close_only fallback basis, and immature → None at both window boundaries.
* engine.bottom_ruler.cohort_table / pinpoint: aggregation + pin5/held/broke fractions.
* scripts.grade_bottom_calls: idempotent accrual (second run = byte-identical parquet, no
  regrades), snapshot-shape tolerance (missing lane / missing washout payload), and baseline
  determinism (two builds byte-identical). All store writes are redirected to tmp_path — the
  real data/ tree is never touched (MM_DATA_GUARD; conftest sessionfinish guard).

The grade arithmetic pins here are derived independently by hand (see the module docstring of
each test), so a drift in engine.bottom_ruler that still matched bottom_ruler_study.py would
still break these — they anchor the yardstick to ground truth, not just to the study copy.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import bottom_ruler as BR  # noqa: E402
import scripts.grade_bottom_calls as G  # noqa: E402


# ---------------------------------------------------------------------------
# synthetic OHLC builders — n=90, signal at i=15 (i-PRE=5>=0, i+H=75<90 matured)
# ---------------------------------------------------------------------------
_N, _I = 90, 15


def _series(close, high=None, low=None):
    idx = pd.bdate_range("2024-01-01", periods=_N)
    c = pd.Series(close, index=idx)
    h = pd.Series(high, index=idx) if high is not None else None
    lo = pd.Series(low, index=idx) if low is not None else None
    return idx, c, h, lo


# ---------------------------------------------------------------------------
# grade_call — exact hand-computed pins
# ---------------------------------------------------------------------------
def test_grade_call_deep_undercut_exact():
    """Trough 95 AFTER the signal (t_off=+5); floor F=99 (trailing-20d low, dip is after i);
    forward low 95 undercuts F by 1-95/99=4.04% → 'deep'. MFE spike 130, fwd close 110.
    All numbers are exact under next-close fill=100."""
    i = _I
    close = np.full(_N, 100.0)
    high = np.full(_N, 101.0)
    low = np.full(_N, 99.0)
    low[i + 5] = 95.0           # eventual trough, +5 days from signal
    high[i + 10] = 130.0        # MFE spike (inside high[f+1:i+H+1])
    close[i + BR.H] = 110.0     # fwd60 endpoint
    idx, c, h, lo = _series(close, high, low)

    g = BR.grade_call(c, h, lo, idx[i])
    assert g is not None
    assert g["prox"] == pytest.approx(100 / 95 - 1)        # 0.0526315…
    assert g["t_off"] == 5
    assert g["undercut"] == pytest.approx(1 - 95 / 99)     # 0.0404040…
    assert g["undercut_class"] == "deep"
    assert g["mfe60"] == pytest.approx(130 / 100 - 1)      # 0.30
    assert g["mae60"] == pytest.approx(95 / 100 - 1)       # -0.05
    assert g["fwd60"] == pytest.approx(110 / 100 - 1)      # 0.10
    assert g["basis"] == "ohlc"
    assert BR.pinpoint(g) is False                          # prox 5.26% > 5%


def test_grade_call_pinpoint_and_held_exact():
    """Trough 98 two days BEFORE the signal (t_off=-2); prox 2.04% → pinpoint. Forward low
    never dips below the floor (98) → undercut 0 → 'held'."""
    i = _I
    close = np.full(_N, 100.0)
    high = np.full(_N, 101.0)
    low = np.full(_N, 99.0)
    low[i - 2] = 98.0           # trough already in before the signal
    high[i + 10] = 120.0
    close[i + BR.H] = 105.0
    idx, c, h, lo = _series(close, high, low)

    g = BR.grade_call(c, h, lo, idx[i])
    assert g["t_off"] == -2
    assert g["prox"] == pytest.approx(100 / 98 - 1)        # 0.0204…
    assert g["undercut"] == 0.0
    assert g["undercut_class"] == "held"
    assert BR.pinpoint(g) is True


def test_grade_call_close_only_basis():
    """high/low absent → basis close_only, trough taken from the close series."""
    i = _I
    close = np.full(_N, 100.0)
    close[i + 5] = 95.0
    close[i + BR.H] = 108.0
    idx, c, _, _ = _series(close)

    g = BR.grade_call(c, None, None, idx[i])
    assert g is not None
    assert g["basis"] == "close_only"
    assert g["prox"] == pytest.approx(100 / 95 - 1)
    # floor from close = 100 (dip is after i); undercut 1-95/100 = 0.05 → 'deep' (>0.03,<=0.10)
    assert g["undercut"] == pytest.approx(0.05)
    assert g["undercut_class"] == "deep"


def test_grade_call_immature_returns_none_both_boundaries():
    """< PRE bars before OR < H bars after the signal → None (matured-only, frozen grades)."""
    idx, c, _, _ = _series(np.full(_N, 100.0))
    assert BR.grade_call(c, None, None, idx[85]) is None    # i+H = 145 > n
    assert BR.grade_call(c, None, None, idx[5]) is None      # i-PRE = -5 < 0


def test_grade_call_missing_flag_date_returns_none():
    idx, c, _, _ = _series(np.full(_N, 100.0))
    assert BR.grade_call(c, None, None, pd.Timestamp("1999-01-01")) is None


def test_undercut_class_thresholds():
    """held ≤0.5% / probed ≤3% / deep ≤10% / broke >10% (frozen study thresholds)."""
    assert BR._undercut_class(0.0) == "held"
    assert BR._undercut_class(0.005) == "held"
    assert BR._undercut_class(0.0051) == "probed"
    assert BR._undercut_class(0.03) == "probed"
    assert BR._undercut_class(0.0301) == "deep"
    assert BR._undercut_class(0.10) == "deep"
    assert BR._undercut_class(0.1001) == "broke"


# ---------------------------------------------------------------------------
# cohort_table / pinpoint
# ---------------------------------------------------------------------------
def test_cohort_table_aggregates_and_rates():
    rows = [
        {"source": "board_buy", "lane": "bottom", "prox": 0.02, "undercut": 0.0,
         "undercut_class": "held", "mfe60": 0.1, "fwd60": 0.05},
        {"source": "board_buy", "lane": "bottom", "prox": 0.08, "undercut": 0.15,
         "undercut_class": "broke", "mfe60": 0.2, "fwd60": -0.03},
        {"source": "prophet_plan", "lane": "long", "prox": 0.04, "undercut": 0.01,
         "undercut_class": "probed", "mfe60": 0.3, "fwd60": 0.12},
        # ungraded row (prox None) must be skipped by the cohort summary.
        {"source": "board_buy", "lane": "bottom", "prox": None},
    ]
    tbl = BR.cohort_table(rows, by=["source", "lane"])
    by_key = {(r["source"], r["lane"]): r for r in tbl}
    bb = by_key[("board_buy", "bottom")]
    assert bb["n"] == 2                       # the None row excluded
    assert bb["pin5"] == pytest.approx(0.5)   # one of two prox ≤ 0.05
    assert bb["held_pct"] == pytest.approx(0.5)
    assert bb["broke_pct"] == pytest.approx(0.5)
    assert bb["prox_med"] == pytest.approx(0.05)
    pp = by_key[("prophet_plan", "long")]
    assert pp["n"] == 1 and pp["pin5"] == pytest.approx(1.0)
    # deterministic sorted order by the by-key tuple
    assert [(r["source"], r["lane"]) for r in tbl] == sorted(
        (r["source"], r["lane"]) for r in tbl)


def test_pinpoint_none_and_missing_prox():
    assert BR.pinpoint(None) is False
    assert BR.pinpoint({}) is False
    assert BR.pinpoint({"prox": 0.05}) is True
    assert BR.pinpoint({"prox": 0.0501}) is False


# ---------------------------------------------------------------------------
# grader — accrual, idempotency, shape tolerance, baseline determinism
# ---------------------------------------------------------------------------
def _snapshot_line(as_of, buy=None, watch=None):
    import json
    return json.dumps({"as_of": as_of, "buy": buy or [], "watch": watch or []})


@pytest.fixture()
def _grader_env(tmp_path, monkeypatch):
    """Redirect every grader store/source path into tmp_path (nothing touches real data/)."""
    snaps = tmp_path / "snapshots.jsonl"
    plans = tmp_path / "plans"
    plans.mkdir()
    monkeypatch.setattr(G, "SNAPSHOTS_JSONL", snaps)
    monkeypatch.setattr(G, "PROPHET_PLANS_DIR", plans)
    # price readers point at empty dirs → immature/ungradeable, so nothing matures in these tests
    monkeypatch.setattr(G, "STOCKS_DIR", tmp_path / "stocks_empty")
    monkeypatch.setattr(G, "YAHOO_DIR", tmp_path / "yahoo_empty")
    rows_path = tmp_path / "rows.parquet"
    emit_path = tmp_path / "us_bottom_ledger.json"
    return snaps, plans, rows_path, emit_path


def test_accrual_counts_by_source_and_shape_tolerance(_grader_env):
    snaps, plans, rows_path, emit_path = _grader_env
    import json
    # new-shape buy (lane+conviction+signal), old-shape buy (bare), a watch WITH washout payload,
    # and a watch WITHOUT one (must be ignored — payload not landed yet).
    snaps.write_text("\n".join([
        _snapshot_line("2026-06-30",
                       buy=[{"ticker": "AAA", "lane": "bottom",
                             "conviction": {"score": 0.8}, "signal": {"tier_cascade": "T2"}},
                            {"ticker": "BBB"}],  # old shape, no lane
                       watch=[{"ticker": "CCC", "washout": {"tier": "W1", "weeks_at_floor": 4,
                                                            "late_pct": 0.12}},
                              {"ticker": "DDD"}]),  # no washout payload → skipped
    ]) + "\n")
    (plans / "p1.json").write_text(json.dumps(
        {"asset": "EEE", "signal_date": "2026-06-30", "direction": "long",
         "_conviction_score": 0.6, "_act_level": "act"}))

    doc = G.run_pipeline(rows_path, emit_path, accrue=True,
                         as_of=pd.Timestamp("2026-07-01"), quiet=True)
    assert doc["schema"] == "bottom_ledger/v1"
    assert doc["accrual_by_source"] == {"board_buy": 2, "prophet_plan": 1, "washout_watch": 1}
    assert doc["n_accruing"] == 4
    assert doc["n_matured"] == 0                         # no price history → nothing matures
    assert doc["first_maturity_est"] == G.FIRST_MATURITY_EST
    assert doc["summary"]["pin5"] is None                # nulls printed while unmatured
    assert doc["cohorts"] == []
    # the old-shape buy defaulted lane → "unknown"; washout carried its tier
    store = pd.read_parquet(rows_path)
    lanes = dict(zip(store["ticker"], store["lane"]))
    assert lanes["BBB"] == "unknown"
    assert lanes["CCC"] == "washout"
    assert "DDD" not in set(store["ticker"])             # no-payload watch was not accrued


def test_grader_idempotent_byte_identical_parquet(_grader_env):
    snaps, plans, rows_path, emit_path = _grader_env
    snaps.write_text(_snapshot_line("2026-06-30",
                     buy=[{"ticker": "AAA", "lane": "bottom"}]) + "\n")
    as_of = pd.Timestamp("2026-07-01")
    G.run_pipeline(rows_path, emit_path, accrue=True, as_of=as_of, quiet=True)
    first = rows_path.read_bytes()
    # second accrue with the SAME inputs must not re-append or re-grade → identical bytes
    G.run_pipeline(rows_path, emit_path, accrue=True, as_of=as_of, quiet=True)
    assert rows_path.read_bytes() == first


def test_read_only_run_does_not_write_rows(_grader_env):
    """accrue=False (non-nightly) must NOT create/advance the rows store (only re-emit)."""
    snaps, plans, rows_path, emit_path = _grader_env
    snaps.write_text(_snapshot_line("2026-06-30", buy=[{"ticker": "AAA"}]) + "\n")
    G.run_pipeline(rows_path, emit_path, accrue=False,
                   as_of=pd.Timestamp("2026-07-01"), quiet=True)
    assert not rows_path.exists()                        # no forward advance
    assert emit_path.exists()                            # display artifact still emitted


def test_frozen_grade_never_regraded(_grader_env, monkeypatch):
    """A row already graded=True is never regraded, even if grade_call would now return a value."""
    snaps, plans, rows_path, emit_path = _grader_env
    snaps.write_text(_snapshot_line("2026-06-30", buy=[{"ticker": "AAA"}]) + "\n")
    # first accrue: no prices → ungraded
    G.run_pipeline(rows_path, emit_path, accrue=True,
                   as_of=pd.Timestamp("2026-07-01"), quiet=True)
    store = pd.read_parquet(rows_path)
    # force the row to graded=True with a sentinel grade, persist it
    store.loc[:, "graded"] = True
    store.loc[:, "prox"] = 0.123
    G._atomic_write_parquet(rows_path, store)
    # spy: grade_call must never be called for an already-graded row
    called = {"n": 0}
    real = BR.grade_call
    monkeypatch.setattr(BR, "grade_call", lambda *a, **k: (called.__setitem__("n", called["n"] + 1), real(*a, **k))[1])
    G.run_pipeline(rows_path, emit_path, accrue=True,
                   as_of=pd.Timestamp("2027-01-01"), quiet=True)
    assert called["n"] == 0
    assert pd.read_parquet(rows_path)["prox"].iloc[0] == pytest.approx(0.123)


def test_baseline_deterministic(monkeypatch, tmp_path):
    """Two build_baseline() runs over the same panel produce byte-identical JSON."""
    import json
    # tiny synthetic panel so the test is fast and self-contained
    stocks = tmp_path / "stocks"
    stocks.mkdir()
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2015-01-01", periods=400)
    for t in ("AAA", "BBB"):
        walk = 100 + np.cumsum(rng.normal(0, 1, len(idx)))
        df = pd.DataFrame({"close": walk, "high": walk + 1, "low": walk - 1,
                           "volume": 1e6}, index=idx)
        df.to_parquet(stocks / f"{t}.parquet")
    monkeypatch.setattr(G, "STOCKS_DIR", stocks)
    d1 = G.build_baseline()
    d2 = G.build_baseline()
    s1 = json.dumps(d1, ensure_ascii=False, indent=1, default=str, sort_keys=True)
    s2 = json.dumps(d2, ensure_ascii=False, indent=1, default=str, sort_keys=True)
    assert s1 == s2
    assert d1["schema"] == "bottom_ruler_baseline/v1"
