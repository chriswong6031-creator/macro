"""International performance/rotation engine tests (engine/intl_performance.py).

Synthetic closes (real config ticker names) exercise the USD-conversion math, the
exact equity/FX decomposition identity, the RRG quadrant logic and the correlation
matrix shape; a light smoke test runs the full panel against the committed store.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intl_performance as P  # noqa: E402


def _synth_closes(n: int = 400, seed: int = 1) -> pd.DataFrame:
    idx = pd.bdate_range("2023-06-01", periods=n)
    rng = np.random.default_rng(seed)
    specs = {
        "^N225": 0.0006, "USDJPY=X": 0.0004,    # yen weakening (USD/JPY drifts up)
        "^KS11": 0.0005, "USDKRW=X": 0.0003,
        "^TWII": 0.0004, "USDTWD=X": 0.0001,
        "^FTSE": 0.0002, "GBPUSD=X": -0.0001,
        "^STOXX": 0.0003, "EURUSD=X": 0.00005,
    }
    cols = {}
    for t, dr in specs.items():
        r = rng.normal(dr, 0.008, n)
        cols[t] = pd.Series(100.0 * np.exp(np.cumsum(r)), index=idx)
    return pd.DataFrame(cols)


def test_usd_series_orientation():
    """USD/XXX pairs (fx_invert) DIVIDE; XXX/USD pairs MULTIPLY."""
    idx = pd.bdate_range("2024-01-01", periods=80)
    closes = pd.DataFrame({
        "^N225": pd.Series(30000.0, index=idx), "USDJPY=X": pd.Series(150.0, index=idx),   # JP: divide
        "^FTSE": pd.Series(8000.0, index=idx), "GBPUSD=X": pd.Series(1.25, index=idx),      # GB: multiply
    })
    jp = P.usd_series("JP", closes)
    gb = P.usd_series("GB", closes)
    assert abs(float(jp.iloc[-1]) - 200.0) < 1e-6      # 30000 / 150
    assert abs(float(gb.iloc[-1]) - 10000.0) < 1e-6    # 8000 * 1.25


def test_usd_decomposition_is_exact():
    """For every market & horizon: usd == local + fx (to within 1dp rounding)."""
    board = P.usd_leaderboard(_synth_closes())
    assert board, "leaderboard empty"
    for r in board:
        for h, x in r["returns"].items():
            assert abs(x["usd"] - (x["local"] + x["fx"])) <= 0.11, (r["cc"], h, x)


def test_local_leg_measured_on_usd_calendar():
    """Regression for the window-mismatch bug: the equity leg must be measured over
    the SAME dates as the USD leg even when the index and FX trade on different
    calendars (here FX skips Fridays, so its calendar is sparser than the index)."""
    idx_full = pd.bdate_range("2023-01-02", periods=420)       # Mon-Fri
    fx_idx = idx_full[idx_full.weekday != 4]                    # drop Fridays -> sparser
    rng = np.random.default_rng(7)
    n225 = pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.008, len(idx_full)))), index=idx_full)
    jpy = pd.Series(150.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.006, len(fx_idx)))), index=fx_idx)
    closes = pd.concat([n225.rename("^N225"), jpy.rename("USDJPY=X")], axis=1)
    board = P.usd_leaderboard(closes)
    jp = next(r for r in board if r["cc"] == "JP")
    usd = P.usd_series("JP", closes)
    loc = P._local_aligned("JP", usd, closes)
    for h, n in (("3m", 63), ("12m", 252)):
        if h not in jp["returns"]:
            continue
        # the USD-leg and local-leg windows share endpoints (same calendar)
        assert usd.index[-1] == loc.index[-1]
        assert usd.index[-1 - n] == loc.index[-1 - n]
        # and the reported local return equals the index return over those exact dates
        expected = round((loc.iloc[-1] / loc.iloc[-1 - n] - 1.0) * 100.0, 1)
        assert abs(jp["returns"][h]["local"] - expected) <= 0.11


def test_leaderboard_sorted_desc_by_12m():
    board = P.usd_leaderboard(_synth_closes())
    vals = [r["returns"]["12m"]["usd"] for r in board if "12m" in r["returns"]]
    assert vals == sorted(vals, reverse=True)


def test_yen_weakness_is_a_drag():
    """With a strictly-rising USD/JPY, Japan's USD return must trail its local return."""
    idx = pd.bdate_range("2024-01-01", periods=300)
    arange = np.arange(300)
    closes = pd.DataFrame({
        "^N225": pd.Series(100.0 * 1.001 ** arange, index=idx),     # local index up +0.1%/d
        "USDJPY=X": pd.Series(150.0 * 1.0005 ** arange, index=idx),  # yen weakening every day
    })
    board = P.usd_leaderboard(closes)
    jp = next(r for r in board if r["cc"] == "JP")
    h = jp["returns"]["12m"]
    assert h["fx"] < 0 and h["usd"] < h["local"]


def test_relative_to_us_quadrants():
    closes = _synth_closes()
    bench = pd.Series(  # flat-ish US benchmark so intl up-drift reads as "leading"
        100.0 * np.exp(np.cumsum(np.random.default_rng(9).normal(0.0, 0.006, 400))),
        index=closes.index)
    rrg = P.relative_to_us(closes, bench=bench)
    assert rrg is not None and rrg["n"] >= 1
    valid = {"lead", "weak", "impr", "lag"}
    for row in rrg["rows"]:
        assert row["q"] in valid
        # quadrant must agree with the (level, momentum) coordinates it was placed by
        if row["q"] == "lead":
            assert row["rs_level"] >= 100 and row["rs_mom"] >= 0
        if row["q"] == "lag":
            assert row["rs_level"] < 100 and row["rs_mom"] < 0
    assert rrg["tilt"] in {"ex_us", "us", "mixed"}


def test_correlation_matrix_symmetry_and_diagonal():
    closes = _synth_closes()
    bench = pd.Series(100.0 * np.exp(np.cumsum(
        np.random.default_rng(3).normal(0.0003, 0.007, 400))), index=closes.index)
    cm = P.correlation_matrix(closes, bench=bench)
    assert cm is not None
    n = len(cm["order"])
    assert "US" in cm["order"]
    for i in range(n):
        assert cm["cells"][i][i] == 1.0                       # diagonal
        for j in range(n):
            a, b = cm["cells"][i][j], cm["cells"][j][i]
            if a is not None and b is not None:
                assert abs(a - b) < 1e-9                       # symmetric
            if a is not None:
                assert -1.0001 <= a <= 1.0001
    assert -1.0 <= cm["avg_offdiag"] <= 1.0


def test_risk_appetite_bounds():
    ra = P.risk_appetite(_synth_closes())
    assert ra is not None
    assert 0 <= ra["score"] <= 100
    assert ra["label_en"] in {"Risk-on", "Split tape", "Neutral", "Risk-off"}
    assert ra["tone"] in {"up", "warn", "flat", "down"}
    # v2 contract keys present
    for k in ("coverage_pct", "n_available", "n_universe", "breakdown_share_pct",
              "top_drags", "per_market", "breadth_above_200d", "median_mom_3m"):
        assert k in ra, k


# ===== World Risk Appetite v2 =====

def _wr_trend(start: float, daily_ret: float, n: int = 400, seed: int = 0,
              noise: float = 0.0) -> pd.Series:
    """Geometric price with an optional tail crash: daily_ret compounds for the
    whole window unless `noise` is used for small jitter."""
    idx = pd.bdate_range("2023-06-01", periods=n)
    rng = np.random.default_rng(seed)
    lr = np.full(n, np.log(1 + daily_ret)) + (rng.normal(0, noise, n) if noise else 0.0)
    return pd.Series(start * np.exp(np.cumsum(lr)), index=idx)


def _wr_crash(start: float, up_ret: float, crash_frac: float, seed: int = 0,
              n: int = 400, crash_days: int = 40) -> pd.Series:
    """Rise for most of the window then decline crash_frac over the final
    crash_days sessions (a fresh KOSPI-style drawdown)."""
    idx = pd.bdate_range("2023-06-01", periods=n)
    lr = np.full(n, np.log(1 + up_ret))
    lr[-crash_days:] = np.log(1 - crash_frac / crash_days)
    return pd.Series(start * np.exp(np.cumsum(lr)), index=idx)


# intl 7-market synthetic closes (index + FX), all mild-uptrend by default
_INTL_SPECS = {
    "^N225": ("JP", "USDJPY=X"), "^KS11": ("KR", "USDKRW=X"),
    "^TWII": ("TW", "USDTWD=X"), "^FTSE": ("GB", "GBPUSD=X"),
    "^STOXX": ("EZ", "EURUSD=X"), "^NSEI": ("IN", "USDINR=X"),
    "^AXJO": ("AU", "AUDUSD=X"),
}


def _wr_intl_frame(index_specs: dict[str, float] | None = None) -> pd.DataFrame:
    """Build the 7-market index+FX frame. index_specs overrides a ticker's daily
    drift (default 0.0006 up); all FX held flat so the USD leg tracks the index."""
    index_specs = index_specs or {}
    cols: dict[str, pd.Series] = {}
    for i, (idx_t, (cc, fx_t)) in enumerate(_INTL_SPECS.items()):
        dr = index_specs.get(idx_t, 0.0006)
        cols[idx_t] = _wr_trend(100.0, dr, seed=i)
        cols[fx_t] = _wr_trend(100.0, 0.0, seed=50 + i)
    return pd.DataFrame(cols)


_ALL_CCS = ["JP", "KR", "TW", "GB", "EZ", "IN", "AU", "US", "CN", "HK"]


def test_wr_all_healthy_is_risk_on():
    """Test 1: an all-healthy 10-market universe reads Risk-on, score >=70, no drags."""
    closes = _wr_intl_frame()
    extra = {"US": _wr_trend(4000.0, 0.0006, seed=20),
             "CN": _wr_trend(3000.0, 0.0006, seed=21),
             "HK": _wr_trend(18000.0, 0.0006, seed=22)}
    states = {cc: {"state": "uptrend"} for cc in _ALL_CCS}
    ra = P.risk_appetite(closes, extra_closes=extra, states=states)
    assert ra is not None
    assert ra["score"] >= 70, ra["score"]
    assert ra["label_en"] == "Risk-on"
    assert ra["top_drags"] == []
    assert ra["n_available"] == 10
    assert ra["coverage_pct"] == 100.0


def test_wr_heavy_crash_beats_equal_weight_and_leads_with_big_markets():
    """Test 2: US + CN (heavy caps) in crash, small markets healthy → score drops
    materially vs an equal-weight read; drags lead with US/CN; label != Risk-on when
    the breakdown share is >=20%."""
    closes = _wr_intl_frame()
    extra = {"US": _wr_trend(4000.0, -0.001, seed=20),
             "CN": _wr_trend(3000.0, -0.001, seed=21),
             "HK": _wr_trend(18000.0, 0.0006, seed=22)}
    states = {cc: {"state": "uptrend"} for cc in _ALL_CCS}
    states["US"] = {"state": "crash"}
    states["CN"] = {"state": "crash"}
    ra = P.risk_appetite(closes, extra_closes=extra, states=states)
    assert ra is not None
    # equal-weight sanity: if every market counted the same, 8/10 healthy would
    # dominate; the cap weighting must pull the score down instead.
    assert ra["score"] < 60, ra["score"]
    assert ra["top_drags"][0]["cc"] in {"US", "CN"}
    assert ra["breakdown_share_pct"] >= 20
    assert ra["label_en"] != "Risk-on"


def test_wr_missing_cn_hk_renormalises():
    """Test 3: missing CN/HK series → coverage_pct < 100, still returns a dict."""
    closes = _wr_intl_frame()
    extra = {"US": _wr_trend(4000.0, 0.0006, seed=20)}   # no CN, no HK
    states = {cc: {"state": "uptrend"} for cc in ["JP", "KR", "TW", "GB", "EZ", "IN", "AU", "US"]}
    ra = P.risk_appetite(closes, extra_closes=extra, states=states)
    assert ra is not None                                # no raise
    assert ra["coverage_pct"] < 100.0
    assert "CN" not in ra["per_market"] and "HK" not in ra["per_market"]
    assert ra["n_available"] == 8


def test_wr_regression_todays_failure_scores_below_60():
    """Test 4: the exact scenario that gave the old dial 75/100 while KR was in a
    crash — 6-of-7 small markets above 200d, KR crashing, US below 50d/above 200d,
    CN + HK breaking. The v2 dial must read < 60."""
    # KR crashes; the other 6 intl markets healthy above 200d
    closes = _wr_intl_frame()
    closes["^KS11"] = _wr_crash(100.0, 0.0006, 0.25, seed=99)   # KR ~-25%
    # US: rose all year then a mild late decline → above 200d but under 50d (rollover)
    us = np.full(400, np.log(1.0006))
    us[-40:] = np.log(0.9990)
    us_s = pd.Series(4000.0 * np.exp(np.cumsum(us)),
                     index=pd.bdate_range("2023-06-01", periods=400))
    extra = {"US": us_s,
             "CN": _wr_crash(3000.0, 0.0004, 0.14, seed=21),
             "HK": _wr_crash(18000.0, 0.0004, 0.14, seed=22)}
    states = {"JP": {"state": "uptrend"}, "TW": {"state": "uptrend"},
              "GB": {"state": "uptrend"}, "EZ": {"state": "uptrend"},
              "IN": {"state": "uptrend"}, "AU": {"state": "uptrend"},
              "KR": {"state": "crash"}, "US": {"state": "downtrend"},
              "CN": {"state": "breaking"}, "HK": {"state": "breaking"}}
    ra = P.risk_appetite(closes, extra_closes=extra, states=states)
    assert ra is not None
    assert ra["score"] < 60, f"v2 score {ra['score']} should be < 60 (old dial gave ~75)"
    assert ra["label_en"] != "Risk-on"
    drag_ccs = {d["cc"] for d in ra["top_drags"]}
    assert drag_ccs & {"US", "CN", "HK", "KR"}


def test_wr_split_tape_verdict_is_label_not_score_floor():
    """A high score with a concentrated (>=20% cap) breakdown reads 'Split tape' —
    verdict-label semantics on the display dial; the score itself is untouched."""
    closes = _wr_intl_frame()
    extra = {"US": _wr_trend(4000.0, 0.0006, seed=20),
             "CN": _wr_trend(3000.0, 0.0006, seed=21),
             "HK": _wr_trend(18000.0, 0.0006, seed=22)}
    states = {cc: {"state": "uptrend"} for cc in _ALL_CCS}
    # break EZ (9) + JP (5.5) + HK (3.5) + CN (6.5) = 24.5% of covered cap
    for cc in ("EZ", "JP", "HK", "CN"):
        states[cc] = {"state": "breaking"}
    ra = P.risk_appetite(closes, extra_closes=extra, states=states)
    assert ra is not None
    assert ra["breakdown_share_pct"] >= 20
    if ra["score"] >= 60:
        assert ra["label_en"] == "Split tape"
        assert ra["tone"] == "warn"


def test_wr_state_health_map_matches_market_state_keys():
    """Test 5 (drift guard): the state-health map's keys == the STATES catalogue."""
    from engine.intl_market_state import STATES
    assert set(P._STATE_HEALTH.keys()) == set(STATES.keys())


def test_wr_no_state_renormalises_over_trend_and_mom():
    """A market with no turn state must still contribute via trend+mom (leg weights
    renormalise over the present legs), not be dropped."""
    closes = _wr_intl_frame()
    extra = {"US": _wr_trend(4000.0, 0.0006, seed=20)}
    ra = P.risk_appetite(closes, extra_closes=extra, states={})   # NO states at all
    assert ra is not None
    assert ra["n_available"] >= 8                                 # 7 intl + US
    # per-market health computed from trend+mom only (state leg absent)
    assert ra["per_market"]["US"]["state"] is None
    assert 0.0 <= ra["per_market"]["US"]["h"] <= 1.0


def test_degrade_on_empty():
    empty = pd.DataFrame()
    assert P.usd_leaderboard(empty) == []
    assert P.correlation_matrix(empty, bench=None) is None or True  # must not raise


def test_global_read_is_bilingual_text():
    closes = _synth_closes()
    board = P.usd_leaderboard(closes)
    records = [{"cc": "JP", "name": "Japan", "name_zh": "日本", "quad_name": "Goldilocks"},
               {"cc": "GB", "name": "United Kingdom", "name_zh": "英国", "quad_name": "Reflation"}]
    gr = P.global_read(records, board, None, None)
    assert gr["en"] and gr["zh"]
    # quad label is plain-worded at composition (Design Doctrine Law 2; ITR W1) —
    # the raw "Goldilocks" token must NOT reach the glance tier
    assert "Goldilocks" not in gr["en"]
    assert "growth OK, inflation calm" in gr["en"]
    assert "增长尚可、通胀温和" in gr["zh"]


def test_performance_panel_smoke():
    """Full panel against the committed store — structure only (no network)."""
    panel = P.performance_panel()
    assert "leaderboard" in panel and "horizons" in panel
    assert {h["key"] for h in panel["horizons"]} >= {"1m", "3m", "12m", "ytd"}
    if panel["leaderboard"]:
        r = panel["leaderboard"][0]
        assert "returns" in r and "spark" in r
