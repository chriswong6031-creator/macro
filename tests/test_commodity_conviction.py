"""Commodity CONVICTION engine tests on synthetic data — no network.

Run: .venv/bin/python -m tests.test_commodity_conviction
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import commodity_conviction as CC  # noqa: E402

VALID_ACTIONS = {"STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"}


def _sig(n=1600, trend=0.0003, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2013-01-01", periods=n, freq="B")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(trend, 0.012, n))), index=idx)
    return pd.DataFrame({
        "close": close,
        "ts_momentum": np.tanh(close.pct_change(252) * 5).fillna(0.0),
        "structure": pd.Series(rng.uniform(-1, 1, n), index=idx),
        "risk_index": pd.Series(rng.uniform(0, 100, n), index=idx),
        "driver_score": pd.Series(np.clip(rng.normal(0, 0.4, n), -1, 1), index=idx),
        "pos_pctile": pd.Series(rng.uniform(0, 100, n), index=idx),
        "shock_z": pd.Series(rng.normal(0, 1, n), index=idx),
        "gsr_pctile": pd.Series(rng.uniform(0, 100, n), index=idx),
        "bw_spread_pctile": pd.Series(rng.uniform(0, 100, n), index=idx),
    }, index=idx)


def _drivers(idx, seed=7) -> dict:
    rng = np.random.default_rng(seed)
    walk = lambda s, sc: pd.Series(s + np.cumsum(rng.normal(0, sc, len(idx))), index=idx)
    return {"indpro": pd.Series(100 + np.cumsum(rng.normal(0, 0.05, len(idx))), index=idx),
            "breakeven10": walk(2.0, 0.01),
            "real_yield": walk(1.0, 0.02),
            "dxy": pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.004, len(idx)))), index=idx),
            "broad_dollar": pd.Series(120 * np.exp(np.cumsum(rng.normal(0, 0.003, len(idx)))), index=idx)}


def _extras(idx, seed=9) -> dict:
    rng = np.random.default_rng(seed)
    walk = lambda s, sc: pd.Series(s + np.cumsum(rng.normal(0, sc, len(idx))), index=idx)
    return {"fed_funds_fut": pd.Series(96 + np.cumsum(rng.normal(0, 0.02, len(idx))), index=idx),
            "curve_2s10s": walk(0.5, 0.01),
            "vix": (18 + pd.Series(rng.normal(0, 3, len(idx)), index=idx)).abs(),
            "move": (80 + pd.Series(rng.normal(0, 10, len(idx)), index=idx)).abs(),
            "hy_oas": walk(3.5, 0.02).abs(),
            "net_liquidity": walk(6000, 5),
            "m2": pd.Series(20000 + np.cumsum(rng.normal(0, 3, len(idx))), index=idx)}


def test_factor_panel_bounds() -> None:
    sig = _sig()
    f = CC.factor_panel("gold", sig, _drivers(sig.index), _extras(sig.index))
    assert {"trend", "dollar", "real_rates", "carry", "riskoff", "liquidity", "value"} <= set(f.columns)
    assert "macro" not in f.columns           # decomposed — no composite driver_score factor
    tail = f.dropna(how="all").iloc[-200:]
    assert (tail.abs() <= 1.0 + 1e-9).all().all()   # every factor stays in [-1,1]


def test_action_mapping() -> None:
    assert CC._action(70)[0] == "STRONG BUY"
    assert CC._action(30)[0] == "BUY"
    assert CC._action(0)[0] == "HOLD"
    assert CC._action(-30)[0] == "SELL"
    assert CC._action(-70)[0] == "STRONG SELL"
    th = {"strong_buy": 25, "buy": 5, "sell": -5, "strong_sell": -25}
    assert CC._action(10, th)[0] == "BUY"
    assert CC._action(-30, th)[0] == "STRONG SELL"


def test_conviction_shape() -> None:
    sig = _sig()
    v = CC.conviction("gold", sig, _drivers(sig.index), _extras(sig.index), {}, None, {})
    assert v["action"] in VALID_ACTIONS
    assert -100 <= v["score"] <= 100
    assert v["factors"] and v["groups"]
    assert "cycle" in v and "confidence" in v
    # factors sorted by |contribution| descending
    contribs = [abs(r["contribution"]) for r in v["factors"]]
    assert contribs == sorted(contribs, reverse=True)


def test_conviction_empty_on_empty() -> None:
    assert CC.conviction("gold", pd.DataFrame(), {}, {}, {}, None, {}) == {}


def test_inverted_weight_flips_contribution() -> None:
    # a NEGATIVE measured weight (oil trend mean-reverts) must turn a positive trend
    # reading into a NEGATIVE contribution — the calibration-honesty hinge.
    sig = _sig(trend=0.0015)                       # strong up-trend -> trend factor > 0
    calib = {"assets": {"oil": {"weights": {"trend": -0.30, "macro": 0.10}}}}
    v = CC.conviction("oil", sig, _drivers(sig.index), _extras(sig.index), {}, None, calib)
    tr = next(r for r in v["factors"] if r["key"] == "trend")
    assert tr["value"] > 0 and tr["weight"] < 0 and tr["contribution"] < 0


def test_cycle_segments_handle_negative_prices() -> None:
    # a synthetic series with a negative spike (the 2020 oil anomaly) must not crash
    # and must still produce alternating legs.
    idx = pd.date_range("2010-01-01", periods=2000, freq="B")
    rng = np.random.default_rng(3)
    s = pd.Series(60 + 30 * np.sin(np.linspace(0, 12 * np.pi, 2000))
                  + np.cumsum(rng.normal(0, 0.3, 2000)), index=idx)
    s.iloc[1000] = -37.0                            # the anomaly print
    legs = CC.cycle_segments(s, 0.20)
    assert len(legs) >= 4
    kinds = [l["kind"] for l in legs]
    assert all(kinds[i] != kinds[i + 1] for i in range(len(kinds) - 1))  # alternating


def test_cycle_position_fields() -> None:
    idx = pd.date_range("2008-01-01", periods=3000, freq="B")
    s = pd.Series(50 + 25 * np.sin(np.linspace(0, 16 * np.pi, 3000)), index=idx)
    pos = CC.cycle_position(s, "oil", 0.20)
    assert pos["regime"] in ("bull", "bear")
    assert pos["days_in"] >= 0 and pos["median_len_d"] > 0
    assert pos["next_event"] in ("top", "bottom")
    assert pos["eta_lo"] <= pos["eta_hi"] or pos["eta_days"] == 0


def test_weight_loading_fallback_and_override() -> None:
    dw = CC.default_weights("oil")
    assert dw["trend"] < 0 and dw["shock"] < 0     # oil inversions in the prior
    assert CC.asset_weights("gold", {}) == CC.default_weights("gold")
    cal = {"assets": {"gold": {"weights": {"trend": 0.5}}}}
    assert CC.asset_weights("gold", cal) == {"trend": 0.5}


def test_verdict_polarity_helper_unused_but_score_normalized() -> None:
    # score is normalized by used weight mass -> bounded even with a single factor
    sig = _sig()
    calib = {"assets": {"gold": {"weights": {"trend": 0.9}}}}
    v = CC.conviction("gold", sig, _drivers(sig.index), _extras(sig.index), {}, None, calib)
    assert -100 <= v["score"] <= 100


# ----- 2026-06 verdict-hardening upgrade ----------------------------------- #
def _bounce_close(n=300) -> pd.Series:
    """A bear downtrend that bounces sharply off a 20-day low in the last 5 bars."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    base = np.linspace(120.0, 100.5, n)
    base[-6:] = [100.0, 101.2, 102.4, 103.6, 104.8, 106.0]   # +6% off the low
    return pd.Series(base, index=idx)


def test_decompress_thresholds_floors_compression() -> None:
    th = CC._decompress_thresholds({"strong_sell": -13.6, "sell": -1.9,
                                    "buy": 6.2, "strong_buy": 24.8})
    assert th == {"strong_sell": -CC.STRONG_FLOOR, "sell": -CC.WEAK_FLOOR,
                  "buy": CC.WEAK_FLOOR, "strong_buy": CC.STRONG_FLOOR}
    # a mild -14 is no longer STRONG SELL once the bands are floored
    assert CC._action(-14, th)[0] == "SELL"
    assert CC._action(-40, th)[0] == "STRONG SELL"
    assert CC._action(-5, th)[0] == "HOLD"
    # an already-more-extreme calibrated band is honoured, not widened back
    th2 = CC._decompress_thresholds({"strong_sell": -55, "sell": -18,
                                     "buy": 18, "strong_buy": 55})
    assert th2["strong_sell"] == -55 and th2["sell"] == -18 and th2["strong_buy"] == 55


def test_trend_floor_preserves_sign() -> None:
    g = CC._trend_floored({"trend": 0.078, "dollar": 0.1}, "gold")
    assert g["trend"] >= CC.TREND_FLOOR                       # un-starved, stays positive
    o = CC._trend_floored({"trend": -0.05}, "oil")
    assert o["trend"] <= -CC.TREND_FLOOR                      # oil trend stays inverted
    z = CC._trend_floored({"trend": 0.0}, "oil")              # zeroed -> prior (oil -) sign
    assert z["trend"] < 0
    keep = CC._trend_floored({"trend": 0.5}, "gold")          # already above floor
    assert keep["trend"] == 0.5


def test_cycle_inflection_damps_without_flipping() -> None:
    damp, cr = CC._cycle_inflection(_bounce_close(), "bear")
    assert 1.0 - 0.8 - 1e-9 <= damp < 1.0 and cr > 0.03       # shrunk toward neutral
    assert (-1.0) * damp <= 0.0                               # bear cycle factor never flips +
    # a bull leg making new highs has no opposing move -> untouched
    up = pd.Series(np.linspace(100, 160, 300),
                   index=pd.date_range("2024-01-01", periods=300, freq="B"))
    d2, cr2 = CC._cycle_inflection(up, "bull")
    assert d2 == 1.0 and cr2 == 0.0
    # a stale price drifting (not rising short-term) does not trigger the damp
    flat = pd.Series(np.linspace(120, 100, 300),
                     index=pd.date_range("2024-01-01", periods=300, freq="B"))
    d3, cr3 = CC._cycle_inflection(flat, "bear")
    assert d3 == 1.0 and cr3 == 0.0


def test_macro_pulse_is_bounded_and_display_only() -> None:
    sig = _sig()
    mp = CC.macro_pulse("gold", sig, _drivers(sig.index), _extras(sig.index))
    assert mp["rows"] and {"real_rates", "dollar"} <= {r["key"] for r in mp["rows"]}
    for r in mp["rows"]:
        assert abs(r["slow"]) <= 1 + 1e-9 and abs(r["fast"]) <= 1 + 1e-9
    # the pulse is NOT a scored factor in the panel
    assert "macro_pulse" not in CC.factor_panel("gold", sig, _drivers(sig.index),
                                                _extras(sig.index)).columns


def test_regime_inflection_banner_states() -> None:
    no_turn, turning = {"n_turning": 0}, {"n_turning": 3}
    b = CC.regime_inflection("bear", 0.06, no_turn)
    assert b["state"] == "price_only" and b["confidence_mult"] < 1.0 and not b["drivers_turning"]
    c = CC.regime_inflection("bear", 0.06, turning)
    assert c["state"] == "confirming" and c["drivers_turning"]
    assert CC.regime_inflection("bear", 0.01, no_turn)["state"] == "none"   # move too small
    assert CC.regime_inflection(None, 0.06, no_turn)["state"] == "none"     # no leg
    # a pullback in a BULL leg (negative counter move) also flags
    assert CC.regime_inflection("bull", -0.06, no_turn)["state"] == "price_only"


def test_data_freshness_flags_stale() -> None:
    idx = pd.date_range("2024-01-01", periods=80, freq="B")
    asof = idx[-1] + pd.Timedelta(days=5)
    fr = CC.data_freshness(asof, {"real_yield": pd.Series(2.0, index=idx)},
                           {"vix": pd.Series(18.0, index=idx)})
    assert fr["stale"] and fr["max_stale_days"] >= 5 and len(fr["items"]) == 2
    fresh = CC.data_freshness(idx[-1], {"real_yield": pd.Series(2.0, index=idx)}, {})
    assert not fresh["stale"]


def test_conviction_exposes_upgrade_fields_without_flipping() -> None:
    sig = _sig()
    v = CC.conviction("gold", sig, _drivers(sig.index), _extras(sig.index), {}, None, {})
    assert {"macro_pulse", "inflection", "freshness"} <= set(v)
    # the action must still be a pure function of (score, floored thresholds) — the banner
    # only modulates confidence, it never changes direction.
    th = CC._decompress_thresholds(None)
    assert v["action"] == CC._action(v["score"], th)[0]


if __name__ == "__main__":
    for fn in [test_factor_panel_bounds, test_action_mapping, test_conviction_shape,
               test_conviction_empty_on_empty, test_inverted_weight_flips_contribution,
               test_cycle_segments_handle_negative_prices, test_cycle_position_fields,
               test_weight_loading_fallback_and_override,
               test_verdict_polarity_helper_unused_but_score_normalized,
               test_decompress_thresholds_floors_compression, test_trend_floor_preserves_sign,
               test_cycle_inflection_damps_without_flipping,
               test_macro_pulse_is_bounded_and_display_only,
               test_regime_inflection_banner_states, test_data_freshness_flags_stale,
               test_conviction_exposes_upgrade_fields_without_flipping]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all commodity conviction tests passed")
