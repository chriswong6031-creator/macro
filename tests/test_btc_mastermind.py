"""Mastermind-upgrade tests: the new deep/context factors (miner economics,
conditional beta, holder spread, attention, taker flow) + the Master Signal
synthesis. Synthetic series only — no network.

Run: python -m pytest tests/test_btc_mastermind.py -q
     or  python tests/test_btc_mastermind.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_master as M  # noqa: E402
from engine import btc_signals as S  # noqa: E402
from lib import config  # noqa: E402

_VCFG = config.load()["vector"]


def _price(n=900, trend=0.001, vol=0.02, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", periods=n, freq="D")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(trend, vol, n))), index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": rng.uniform(1, 2, n)}, index=idx)


# --------------------------------------------------------------------------- #
# miner economics
# --------------------------------------------------------------------------- #
def test_miner_economics_bounds_and_capitulation() -> None:
    px = _price()
    idx = px.index
    # flat USD issuance but a STEADILY RISING hashrate -> hashprice falls to its
    # own low percentile = squeezed margins = the capitulation/bottoming zone.
    iss = pd.Series(5e6, index=idx)
    hashrate = pd.Series(np.linspace(1.0, 6.0, len(idx)), index=idx)
    out = S.miner_economics({"price": px, "issuance_usd": iss, "hashrate": hashrate},
                            _VCFG["miner_econ"])
    assert out["hashprice_pctile"].dropna().between(0, 100).all()
    assert out["miner_stress"].dropna().between(0, 100).all()
    assert set(out["miner_econ_state"].dropna().unique()) <= {
        "capitulation", "stress", "healthy", "euphoria"}
    # the most-recent rows sit at the bottom of the hashprice range -> low percentile
    assert out["hashprice_pctile"].iloc[-1] < 25
    assert out["miner_econ_state"].iloc[-1] == "capitulation"


def test_miner_economics_no_lookahead() -> None:
    px = _price(seed=7)
    idx = px.index
    iss = pd.Series(np.linspace(4e6, 6e6, len(idx)), index=idx)
    hr = pd.Series(np.linspace(1.0, 5.0, len(idx)), index=idx)
    full = S.miner_economics({"price": px, "issuance_usd": iss, "hashrate": hr}, _VCFG["miner_econ"])
    cut = px.index[600]
    tpx = px.loc[:cut]
    trunc = S.miner_economics({"price": tpx, "issuance_usd": iss.loc[:cut],
                               "hashrate": hr.loc[:cut]}, _VCFG["miner_econ"])
    ov = full["hashprice_pctile"].loc[trunc.index].iloc[400:590]
    assert np.allclose(ov.values, trunc["hashprice_pctile"].iloc[400:590].values,
                       atol=1e-6, equal_nan=True)


def test_miner_economics_missing_inputs_safe() -> None:
    out = S.miner_economics({"price": _price()}, _VCFG["miner_econ"])
    assert out.empty or "hashprice" not in out.columns


# --------------------------------------------------------------------------- #
# conditional beta
# --------------------------------------------------------------------------- #
def test_conditional_beta_downside_dominates() -> None:
    n = 700
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    rng = np.random.default_rng(3)
    mret = rng.normal(0, 0.012, n)
    # BTC tracks the market 1.4x on DOWN days, 0.4x on UP days (the real asymmetry)
    bret = np.where(mret < 0, 1.4 * mret, 0.4 * mret) + rng.normal(0, 0.002, n)
    ndx = pd.Series(100 * np.exp(np.cumsum(mret)), index=idx)
    close = pd.Series(100 * np.exp(np.cumsum(bret)), index=idx)
    px = pd.DataFrame({"close": close, "high": close, "low": close}, index=idx)
    out = S.conditional_beta({"price": px, "ndx": ndx}, _VCFG["conditional_beta"])
    db, ub = out["down_beta"].iloc[-1], out["up_beta"].iloc[-1]
    assert db > ub                      # couples harder on the way down
    assert out["beta_asym"].iloc[-1] < 0
    assert out["down_beta_pctile"].dropna().between(0, 100).all()


def test_conditional_beta_missing_market_safe() -> None:
    out = S.conditional_beta({"price": _price()}, _VCFG["conditional_beta"])
    assert "down_beta" not in out.columns  # no market proxy -> no columns, no crash


# --------------------------------------------------------------------------- #
# holder spread
# --------------------------------------------------------------------------- #
def test_holder_spread_states() -> None:
    px = _price(n=500)
    idx = px.index
    # STH realizing far MORE profit than LTH -> distribution
    sth = pd.Series(1.10, index=idx)
    lth = pd.Series(1.00, index=idx)
    out = S.holder_spread({"price": px, "sth_sopr": sth, "lth_sopr": lth}, _VCFG["holder_spread"])
    assert out["sth_lth_sopr_spread"].iloc[-1] > 0
    assert out["holder_state"].iloc[-1] == "distribution"


# --------------------------------------------------------------------------- #
# attention
# --------------------------------------------------------------------------- #
def test_attention_mania_and_apathy() -> None:
    n = 800
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    base = pd.Series(1000.0, index=idx)
    base.iloc[-5:] = 20000.0                    # a mania blow-off spike
    out = S.attention({"price": pd.DataFrame({"close": base}), "wiki_views": base},
                      _VCFG["attention"])
    assert out["wiki_views_z"].dropna().between(-4, 4).all()
    assert out["attention_state"].iloc[-1] == "mania"


# --------------------------------------------------------------------------- #
# taker flow
# --------------------------------------------------------------------------- #
def test_taker_flow_cvd_and_divergence() -> None:
    n = 200
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100, 140, n), index=idx)         # price rising
    taker = pd.Series(np.linspace(0.55, 0.42, n), index=idx)       # but aggressor flow fading
    out = S.taker_flow({"price": pd.DataFrame({"close": close}), "okx_taker_buy": taker},
                       _VCFG["taker_flow"])
    assert out["taker_buy_share"].iloc[-1] == taker.iloc[-1]
    assert out["taker_divergence"].iloc[-1] == "bearish"           # price up, flow down


# --------------------------------------------------------------------------- #
# Master Signal synthesis
# --------------------------------------------------------------------------- #
def _sig_frame(bias: str) -> pd.DataFrame:
    """A small signals frame with the columns synthesize() reads, tilted bullish/bearish."""
    n = 120
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    s = 1.0 if bias == "bull" else -1.0
    df = pd.DataFrame(index=idx)
    df["momentum"] = s * 0.8
    df["structure"] = s * 0.7
    df["impulse"] = s * 0.5
    df["risk_index"] = 15 if bias == "bull" else 70
    df["leverage_stress"] = 20 if bias == "bull" else 70
    df["bfi"] = 70 if bias == "bull" else 30
    df["macro_score"] = s * 0.5
    df["etf_flow_z"] = s * 1.0
    df["stbl_growth_z"] = s * 1.0
    df["valuation_state"] = "undervalued" if bias == "bull" else "overvalued"
    df["market_extreme"] = "capitulation" if bias == "bull" else "euphoria"
    df["down_beta"] = 0.5
    df["beta_asym"] = s * 0.2
    df["cphase_phase"] = "markup" if bias == "bull" else "markdown"
    df["cphase_pct"] = 0.4
    df["mvrv_z"] = -1.0 if bias == "bull" else 4.0
    df["wiki_views_z"] = 0.0
    df["hashprice_pctile"] = 50.0
    df["extreme_score"] = s
    df["reserve_risk"] = 0.001 if bias == "bull" else 0.03
    df["cot_z"] = -s * 1.0
    df["funding_z"] = -s * 1.0
    df["miner_econ_state"] = "healthy"
    df["holder_state"] = "neutral"
    df["attention_state"] = "normal"
    df["coinbase_premium_ema"] = 0.0
    df["sth_lth_sopr_spread"] = 0.0
    return df


def test_master_score_bounds_and_direction() -> None:
    bull = M.synthesize(_sig_frame("bull"), {})
    bear = M.synthesize(_sig_frame("bear"), {})
    for m in (bull, bear):
        assert m["ok"]
        assert -100 <= m["score"] <= 100
        assert 0 <= m["gauge"] <= 100
        assert m["band"] in {"STRONG RISK-ON", "RISK-ON", "NEUTRAL", "RISK-OFF", "STRONG RISK-OFF"}
    assert bull["score"] > 25 and bull["tone"] == "bull"
    assert bear["score"] < -25 and bear["tone"] == "bear"
    # gauge tracks score monotonically
    assert bull["gauge"] > bear["gauge"]


def test_master_board_and_drivers() -> None:
    m = M.synthesize(_sig_frame("bear"), {})
    assert m["board"], "board should have groups"
    rows = [r for grp in m["board"] for r in grp["rows"]]
    assert len(rows) >= 12
    assert all(r["tone"] in {"bull", "bear", "neutral"} for r in rows)
    # a bearish frame surfaces cautionary drivers
    assert m["drivers_neg"]
    assert all("label_en" in d and "state_en" in d for d in m["drivers_pos"] + m["drivers_neg"])


def test_master_grade_from_calibration() -> None:
    calib = {"signals": {"risk_index": {"verdict": "CONFIRMED near-term risk gauge"},
                         "momentum": {"verdict": "DIRECTIONAL (one half weak)"},
                         "mvrv_z": {"verdict": "EXTREMES — low <0"}}}
    m = M.synthesize(_sig_frame("bull"), calib)
    grades = {r["key"]: r["grade"] for grp in m["board"] for r in grp["rows"]}
    assert grades.get("risk") == "CONFIRMED"
    assert grades.get("momentum") == "DIRECTIONAL"
    assert grades.get("valuation") == "EXTREMES"
    assert grades.get("miner") == "NEW"       # mastermind-upgrade axis, not yet calibrated


def test_master_nan_safe() -> None:
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    empty = pd.DataFrame({"momentum": [np.nan] * 10}, index=idx)
    m = M.synthesize(empty, {})
    assert m["ok"]
    assert -100 <= m["score"] <= 100         # degrades to a usable neutral-ish read
    assert M.synthesize(pd.DataFrame(), {}) == {"ok": False}


def test_spark_points_monotone() -> None:
    s = pd.Series(range(60), dtype=float)
    pts = M._spark(s)
    assert pts and len(pts.split(" ")) == 60
    ys = [float(p.split(",")[1]) for p in pts.split(" ")]
    assert ys[0] > ys[-1]                     # rising series -> y inverted (last is highest = smallest y)
    assert M._spark(None) == "" and M._spark(pd.Series([1.0])) == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"all {len(fns)} mastermind tests passed")
