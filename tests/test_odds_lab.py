"""Tests for engine/odds_lab.py — the Odds Desk factor/forward engine.

Coverage (spec §Tests — the five families):
1. bucket boundary edges per factor (incl. VIX 11.99/12.00/15.00/34.99/35.00)
2. forward-return alignment on a synthetic 30-bar frame with known opens/closes
   (exact fwd1/fwd5 values, nulls at the tail, holiday-gap indifference)
3. no-look-ahead: ATR / rel_vol denominators use only <= t-1 data (frames where
   including t would change the answer; assert it doesn't + positive control)
4. matcher cross-check: Python match on the REAL built SPY matrix (defaults,
   10y, 1d) vs an independent pandas computation to 1e-9; one factor-match
   template row too. Skips with a reason pre-build.
5. matrix JSON round-trip: schema keys, equal array lengths, ascending dates,
   ints only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import odds_lab
from engine.odds_lab import (
    ASSET_FACTORS,
    MARKET_FACTORS,
    OUTCOME_COLS,
    RANGE_DAYS,
    SCHEMA_MATRIX,
    bucket_dist_52w,
    bucket_gap,
    bucket_magnitude,
    bucket_mkt_trend,
    bucket_pct_move,
    bucket_rel_vol,
    bucket_rsi_slope,
    bucket_rsi_zone,
    bucket_trend_structure,
    bucket_vix_level,
    bucket_vix_move,
    build_matrix,
    compute_asset_factors,
    compute_forward,
    compute_market_frame,
    map_quad,
    matrix_frame,
    run_match,
    wilder_atr,
    wilson_ci,
)

ROOT = Path(__file__).resolve().parent.parent
SPY_MATRIX = ROOT / "site" / "oddsmatrix" / "SPY.json"
FACTOR_MATCH = ROOT / "site" / "oddsdata" / "factor_match.json"


# ---------------------------------------------------------------------------
# fixture helpers
# ---------------------------------------------------------------------------

def _ohlcv(closes, opens=None, highs=None, lows=None, volumes=None, index=None):
    n = len(closes)
    closes = [float(c) for c in closes]
    if opens is None:
        opens = closes
    if highs is None:
        highs = [c + 1.0 for c in closes]
    if lows is None:
        lows = [c - 1.0 for c in closes]
    if volumes is None:
        volumes = [1000.0] * n
    if index is None:
        index = pd.bdate_range("2024-01-02", periods=n)
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": volumes}, index=index)


# ---------------------------------------------------------------------------
# 1. bucket boundary edges (exact contracts)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vix,expected", [
    (11.99, 0), (12.00, 1), (14.99, 1), (15.00, 2), (19.99, 2), (20.00, 3),
    (24.99, 3), (25.00, 4), (34.99, 4), (35.00, 5), (80.0, 5), (float("nan"), None),
])
def test_bucket_vix_level_edges(vix, expected):
    assert bucket_vix_level(vix) == expected


@pytest.mark.parametrize("rsi,expected", [
    (29.99, -2), (30.0, -1), (44.99, -1), (45.0, 0), (54.99, 0), (55.0, 1),
    (69.99, 1), (70.0, 2), (100.0, 2), (float("nan"), None),
])
def test_bucket_rsi_zone_edges(rsi, expected):
    assert bucket_rsi_zone(rsi) == expected


@pytest.mark.parametrize("d,expected", [
    (-8.0, -2), (-7.99, -1), (-2.0, -1), (-1.99, 0), (1.99, 0), (2.0, 1),
    (7.99, 1), (8.0, 2), (float("nan"), None),
])
def test_bucket_rsi_slope_edges(d, expected):
    assert bucket_rsi_slope(d) == expected


@pytest.mark.parametrize("r,expected", [
    (0.49, -2), (0.50, -1), (0.79, -1), (0.80, 0), (1.19, 0), (1.20, 1),
    (1.74, 1), (1.75, 2), (2.49, 2), (2.50, 3), (9.0, 3), (float("nan"), None),
])
def test_bucket_rel_vol_edges(r, expected):
    assert bucket_rel_vol(r) == expected


@pytest.mark.parametrize("s,expected", [
    (-1.00, -2), (-0.999, -1), (-0.15, -1), (-0.1499, 0), (0.1499, 0),
    (0.15, 1), (0.999, 1), (1.00, 2), (float("nan"), None),
])
def test_bucket_trend_structure_edges(s, expected):
    assert bucket_trend_structure(s) == expected


@pytest.mark.parametrize("d,expected", [
    # right-closed intervals per spec: 0 >=-1 · -1 (-5,-1] · -2 (-10,-5] ·
    # -3 (-20,-10] · -4 <=-20 — boundary values fall in the LOWER bucket
    (0.0, 0), (-1.0, 0), (-1.001, -1), (-4.999, -1), (-5.0, -2), (-9.999, -2),
    (-10.0, -3), (-19.999, -3), (-20.0, -4), (-60.0, -4), (float("nan"), None),
])
def test_bucket_dist_52w_edges(d, expected):
    assert bucket_dist_52w(d) == expected


@pytest.mark.parametrize("pct,expected", [
    (0.0, 0), (0.12, 0), (0.13, 1), (-0.13, -1), (1.0, 4), (3.0, 12),
    (9.9, 12), (-9.9, -12), (float("nan"), None),
])
def test_bucket_pct_move_edges(pct, expected):
    assert bucket_pct_move(pct) == expected


@pytest.mark.parametrize("chg,expected", [
    (0.0, 0), (2.9, 1), (3.1, 2), (-3.1, -2), (20.0, 8), (-20.0, -8),
    (float("nan"), None),
])
def test_bucket_vix_move_edges(chg, expected):
    assert bucket_vix_move(chg) == expected


@pytest.mark.parametrize("gap,expected", [
    (0.0, 0), (0.3, 1), (-0.4, -2), (2.0, 6), (-2.0, -6), (float("nan"), None),
])
def test_bucket_gap_edges(gap, expected):
    assert bucket_gap(gap) == expected


@pytest.mark.parametrize("pct,atr_pct,expected", [
    (1.0, 1.0, 2),        # 1% move / half of 1% ATR = 2 steps
    (3.2, 1.0, 6),
    (4.0, 1.0, 6),        # clip +6
    (-4.0, 1.0, -6),      # clip -6
    (1.0, 0.0, None),     # degenerate ATR -> null
    (1.0, float("nan"), None),
])
def test_bucket_magnitude_edges(pct, atr_pct, expected):
    assert bucket_magnitude(pct, atr_pct) == expected


@pytest.mark.parametrize("close,sma50,sma200,expected", [
    (105.0, 100.0, 90.0, 0),    # Full Bull
    (95.0, 100.0, 90.0, 1),     # Bull Correction
    (95.0, 90.0, 100.0, 2),     # Bear Rally
    (85.0, 90.0, 100.0, 3),     # Full Bear
    (100.0, 100.0, 90.0, 1),    # equality counts as "not above"
    (100.0, 90.0, 100.0, 2),
    (100.0, float("nan"), 90.0, None),
])
def test_bucket_mkt_trend_states(close, sma50, sma200, expected):
    assert bucket_mkt_trend(close, sma50, sma200) == expected


def test_map_quad():
    out = map_quad(pd.Series(["Q1", "Q4", "q2", None, "unknown"]))
    assert out.iloc[0] == 1.0
    assert out.iloc[1] == 4.0
    assert out.iloc[2] == 2.0
    assert pd.isna(out.iloc[3])
    assert pd.isna(out.iloc[4])


def test_wilson_ci_formula():
    wins, n, z = 53, 100, 1.96
    lo, hi = wilson_ci(wins, n)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    assert lo == pytest.approx(center - half, abs=1e-12)
    assert hi == pytest.approx(center + half, abs=1e-12)
    assert wilson_ci(0, 0) == (None, None)


# ---------------------------------------------------------------------------
# 2. forward-return alignment (synthetic 30-bar frame, positional logic)
# ---------------------------------------------------------------------------

def _fwd_frame(index=None):
    closes = [100.0 + i for i in range(30)]
    opens = [99.5 + i for i in range(30)]
    return _ohlcv(closes, opens=opens, index=index)


def test_forward_alignment_exact_values():
    fwd = compute_forward(_fwd_frame())
    # fwd1[t] = close[t+1]/open[t+1] - 1
    assert fwd["fwd1_bp"].iloc[0] == pytest.approx((101.0 / 100.5 - 1) * 1e4, abs=1e-9)
    assert fwd["fwd1_bp"].iloc[28] == pytest.approx((129.0 / 128.5 - 1) * 1e4, abs=1e-9)
    # fwd5[t] = close[t+5]/open[t+1] - 1 ; fwd20[t] = close[t+20]/open[t+1] - 1
    assert fwd["fwd5_bp"].iloc[0] == pytest.approx((105.0 / 100.5 - 1) * 1e4, abs=1e-9)
    assert fwd["fwd20_bp"].iloc[0] == pytest.approx((120.0 / 100.5 - 1) * 1e4, abs=1e-9)
    # every in-range position, independently recomputed
    for t in range(29):
        assert fwd["fwd1_bp"].iloc[t] == pytest.approx(
            ((100.0 + t + 1) / (99.5 + t + 1) - 1) * 1e4, abs=1e-9)
    # ret/gap spine
    assert pd.isna(fwd["ret_bp"].iloc[0])
    assert fwd["ret_bp"].iloc[1] == pytest.approx(100.0, abs=1e-9)      # 101/100
    assert fwd["gap_bp"].iloc[1] == pytest.approx(50.0, abs=1e-9)       # 100.5/100


def test_forward_alignment_tail_nulls():
    fwd = compute_forward(_fwd_frame())
    assert pd.isna(fwd["fwd1_bp"].iloc[29])
    assert fwd["fwd1_bp"].iloc[:29].notna().all()
    assert fwd["fwd5_bp"].iloc[25:].isna().all()
    assert fwd["fwd5_bp"].iloc[:25].notna().all()
    assert fwd["fwd20_bp"].iloc[10:].isna().all()
    assert fwd["fwd20_bp"].iloc[:10].notna().all()


def test_forward_alignment_holiday_indifference():
    """Positional (iloc/shift) forward logic: a huge calendar hole between bars
    changes NOTHING — same bar sequence, same forward returns."""
    contiguous = pd.bdate_range("2024-01-02", periods=30)
    gapped = list(pd.bdate_range("2024-01-02", periods=10)) + \
        list(pd.bdate_range("2024-03-01", periods=20))     # 6-week hole
    a = compute_forward(_fwd_frame(index=contiguous))
    b = compute_forward(_fwd_frame(index=pd.DatetimeIndex(gapped)))
    for col in OUTCOME_COLS:
        assert np.allclose(a[col].to_numpy(), b[col].to_numpy(), equal_nan=True)


def test_forward_int_rounding_in_matrix():
    m = build_matrix("TST", _fwd_frame())
    assert m["cols"]["fwd1_bp"][0] == int(round((101.0 / 100.5 - 1) * 1e4))  # 50
    assert m["cols"]["fwd1_bp"][29] is None


# ---------------------------------------------------------------------------
# 3. no-look-ahead: ATR / rel_vol denominators use only <= t-1 data
# ---------------------------------------------------------------------------

def _atr_frames():
    """A and B identical through bar 38; bar 39 (same close/open) has a wild
    high/low range in B. If ATR leaked bar t, magnitude[39] would differ."""
    n = 40
    closes = [100.0] * (n - 1) + [102.0]        # +2% move on the last bar
    opens = list(closes)
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    a = _ohlcv(closes, opens=opens, highs=highs, lows=lows)
    hb, lb = list(highs), list(lows)
    hb[-1], lb[-1] = 160.0, 90.0                # massive same-day range in B
    b = _ohlcv(closes, opens=opens, highs=hb, lows=lb)
    return a, b


def test_no_lookahead_atr_prior_day_only():
    a, b = _atr_frames()
    fa = compute_asset_factors(a)
    fb = compute_asset_factors(b)
    # Baseline ATR is exactly 2.0 -> atr_pct 2%; +2% move = round(2/1) = 2 steps
    assert fa["magnitude"].iloc[-1] == 2
    # Including bar t's range would give atr ~6.86 -> bucket 1. Must NOT happen:
    assert fb["magnitude"].iloc[-1] == 2
    # and the ATR series itself is identical through t-1
    atr_a = wilder_atr(a["high"], a["low"], a["close"])
    atr_b = wilder_atr(b["high"], b["low"], b["close"])
    assert np.allclose(atr_a.iloc[:-1].to_numpy(), atr_b.iloc[:-1].to_numpy(),
                       equal_nan=True)
    assert atr_a.iloc[38] == pytest.approx(2.0, abs=1e-9)


def test_no_lookahead_atr_positive_control():
    """The instrument works: bar 39's range DOES flow into bar 40's ATR."""
    a, b = _atr_frames()
    nxt = pd.DataFrame({"open": [102.0], "high": [103.0], "low": [101.0],
                        "close": [104.04], "volume": [1000.0]},
                       index=[a.index[-1] + pd.Timedelta(days=1)])
    a2 = pd.concat([a, nxt])
    b2 = pd.concat([b, nxt])
    fa = compute_asset_factors(a2)
    fb = compute_asset_factors(b2)
    assert fa["magnitude"].iloc[-1] == 2   # atr[39]~2.07 -> ~1.97 steps
    assert fb["magnitude"].iloc[-1] == 1   # atr[39]~6.86 -> ~0.60 steps
    assert fa["magnitude"].iloc[-1] != fb["magnitude"].iloc[-1]


def test_no_lookahead_rel_vol_prior_20_only():
    """volume[t]=2600 vs flat 1000: SMA20 through t-1 -> ratio 2.6 -> bucket 3.
    An implementation that includes t in the SMA would get 2600/1080=2.41 ->
    bucket 2. Including t must NOT change the answer."""
    n = 30
    closes = [100.0 + 0.1 * i for i in range(n)]
    volumes = [1000.0] * (n - 1) + [2600.0]
    f = compute_asset_factors(_ohlcv(closes, volumes=volumes))
    assert f["rel_vol"].iloc[-1] == 3


# ---------------------------------------------------------------------------
# synthetic matcher sanity (same code path family 4 exercises on real data)
# ---------------------------------------------------------------------------

def _synthetic_matrix(n=320):
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(7)
    steps = rng.normal(0.0005, 0.01, n)
    closes = 100.0 * np.cumprod(1 + steps)
    opens = closes * (1 + rng.normal(0, 0.002, n))
    ohlcv = _ohlcv(closes, opens=opens,
                   highs=(np.maximum(closes, opens) * 1.005),
                   lows=(np.minimum(closes, opens) * 0.995),
                   volumes=1000 + rng.integers(0, 500, n).astype(float),
                   index=idx)
    spy = pd.Series(100 + 0.05 * np.arange(n), index=idx)
    vix = pd.Series(15 + 3 * np.sin(np.arange(n) / 17.0), index=idx)
    regime = pd.DataFrame({"quad": ["Q2"] * n}, index=idx)
    market = compute_market_frame(spy, vix, regime)
    return build_matrix("TST", ohlcv, market)


def test_run_match_mirrors_independent_computation():
    matrix = _synthetic_matrix()
    active = ["rsi_zone", "mkt_trend"]
    res = run_match(matrix, active, range_key="max", horizon="1d", tol=0)
    df = matrix_frame(matrix)
    today = df.iloc[-1]
    if any(pd.isna(today[f]) for f in active):
        pytest.fail("synthetic today's buckets unexpectedly null")
    mask = np.ones(len(df), dtype=bool)
    for f in active:
        col = df[f].to_numpy()
        mask &= ~np.isnan(col) & (np.abs(col - today[f]) <= 0)
    mask &= ~np.isnan(df["fwd1_bp"].to_numpy())
    mask[-1] = False
    vals = df["fwd1_bp"].to_numpy()[mask]
    assert res["stats"]["n"] == int(mask.sum()) > 0
    assert res["stats"]["mean"] == pytest.approx(vals.mean(), abs=1e-9)
    assert res["stats"]["median"] == pytest.approx(np.median(vals), abs=1e-9)
    assert res["stats"]["win_rate"] == pytest.approx((vals > 0).mean(), abs=1e-9)


# ---------------------------------------------------------------------------
# 4. matcher cross-check on the REAL built SPY matrix (skips pre-build)
# ---------------------------------------------------------------------------

def _independent_match(matrix: dict, active: list[str], range_key: str,
                       outcome: str) -> np.ndarray:
    """Deliberately different implementation: raw numpy over the JSON arrays."""
    cols = {k: np.array([np.nan if v is None else float(v) for v in vals])
            for k, vals in matrix["cols"].items()}
    days = np.asarray(matrix["dates"], dtype=np.int64)
    mask = np.ones(len(days), dtype=bool)
    for f in active:
        col = cols[f]
        tv = col[-1]
        assert not np.isnan(tv), f"today's {f} bucket is null in the built matrix"
        mask &= ~np.isnan(col) & (np.abs(col - tv) <= 0)
    mask &= ~np.isnan(cols[outcome])
    if range_key != "max":
        mask &= days >= days[-1] - RANGE_DAYS[range_key]
    mask[-1] = False
    return cols[outcome][mask]


@pytest.mark.skipif(not SPY_MATRIX.exists(),
                    reason="site/oddsmatrix/SPY.json not built yet — run scripts/build_odds.py first")
def test_spy_matcher_cross_check_real_matrix():
    matrix = json.loads(SPY_MATRIX.read_text())
    active = ["magnitude", "vix_level", "mkt_trend"]     # the UI defaults
    today = {f: matrix["cols"][f][-1] for f in active}
    if any(v is None for v in today.values()):
        pytest.skip(f"today's default buckets contain null ({today}) — nothing to match")
    res = run_match(matrix, active, range_key="10y", horizon="1d", tol=0)
    vals = _independent_match(matrix, active, "10y", "fwd1_bp")
    assert res["stats"]["n"] == len(vals) > 0
    assert res["stats"]["mean"] == pytest.approx(vals.mean(), abs=1e-9)
    assert res["stats"]["median"] == pytest.approx(np.median(vals), abs=1e-9)
    assert res["stats"]["win_rate"] == pytest.approx(float((vals > 0).mean()), abs=1e-9)
    # base rate over the same range+horizon
    base = _independent_match(matrix, [], "10y", "fwd1_bp")
    assert res["base"]["n"] == len(base)
    assert res["base"]["win_rate"] == pytest.approx(float((base > 0).mean()), abs=1e-9)


@pytest.mark.skipif(not (SPY_MATRIX.exists() and FACTOR_MATCH.exists()),
                    reason="factor_match.json / SPY matrix not built yet — run scripts/build_odds.py first")
def test_factor_match_spy_row_cross_check():
    fm = json.loads(FACTOR_MATCH.read_text())
    assert fm["schema"] == "odds_factor_match.v1"
    row = next((r for r in fm["rows"] if r["t"] == "SPY"), None)
    assert row is not None, "SPY missing from factor_match rows"
    core = (row.get("res") or {}).get("core")
    if core is None:
        pytest.skip("core template not applicable today (a null active bucket)")
    matrix = json.loads(SPY_MATRIX.read_text())
    tpl = next(t for t in fm["templates"] if t["id"] == "core")
    vals = _independent_match(matrix, tpl["factors"], fm["range"], "fwd1_bp")
    n, win_rate, median_bp, mean_bp = core["1d"]
    assert n == len(vals)
    if n:
        assert win_rate == pytest.approx(round(float((vals > 0).mean()), 4), abs=1e-9)
        assert median_bp == int(round(float(np.median(vals))))
        assert mean_bp == int(round(float(vals.mean())))


# ---------------------------------------------------------------------------
# 5. matrix JSON round-trip
# ---------------------------------------------------------------------------

def test_matrix_json_round_trip():
    m = json.loads(json.dumps(_synthetic_matrix()))
    assert set(m.keys()) == {"schema", "ticker", "asof", "dates", "close", "cols"}
    assert m["schema"] == SCHEMA_MATRIX
    assert m["ticker"] == "TST"
    n = len(m["dates"])
    assert len(m["close"]) == n
    expected_cols = set(MARKET_FACTORS) | set(ASSET_FACTORS) | set(OUTCOME_COLS)
    assert set(m["cols"].keys()) == expected_cols
    for k, vals in m["cols"].items():
        assert len(vals) == n, f"{k} length mismatch"
        for v in vals:
            assert v is None or (isinstance(v, int) and not isinstance(v, bool)), \
                f"{k} carries a non-int {v!r}"
    # dates: epoch days, strictly ascending ints
    assert all(isinstance(d, int) for d in m["dates"])
    assert all(b > a for a, b in zip(m["dates"], m["dates"][1:]))
    # close: numeric
    assert all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in m["close"])
    # joined market content is sane
    quads = [v for v in m["cols"]["quad"] if v is not None]
    assert quads and set(quads) == {2}                      # regime was all Q2
    months = [v for v in m["cols"]["month"] if v is not None]
    assert months and all(1 <= v <= 12 for v in months)
