"""Tests for the three new crypto data-models: Coinbase Premium (self-computed
Coinbase-USD vs OKX-USDT), options/futures (VRP regime + DVOL expected-move band +
consolidated futures carry), and per-fund spot-ETF flows (Farside). Pure — synthetic
inputs + inline HTML fixture, no network.

Run: .venv/bin/python -m tests.test_crypto_data_models
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_signals as S  # noqa: E402
from lib import config  # noqa: E402


def _price(n=800, trend=0.001, vol=0.02, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    close = pd.Series(40000 * np.exp(np.cumsum(rng.normal(trend, vol, n))), index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": rng.uniform(1, 2, n)}, index=idx)


# --------------------------------------------------------------------------- #
# 1. Coinbase Premium model (in onchain_regime)
# --------------------------------------------------------------------------- #
def test_coinbase_premium_self_computed_and_states() -> None:
    cfg = config.load()["vector"]["onchain"]
    px = _price(seed=2)
    close = px["close"]
    # offshore USDT price sits ~0.3% BELOW Coinbase -> a positive (US-bid) premium
    okx = close * 0.997
    out = S.onchain_regime({"price": px, "okx_spot_usdt": okx, "coinbase_premium": None}, cfg)
    assert "coinbase_premium" in out and "coinbase_premium_ema" in out
    # self-computed premium ≈ +0.30%
    assert abs(out["coinbase_premium"].dropna().tail(50).mean() - 0.30) < 0.05
    assert out["coinbase_premium_z"].dropna().between(-4, 4).all()
    assert out["coinbase_premium_pctile"].dropna().between(0, 100).all()
    assert set(out["coinbase_premium_state"].dropna().unique()) <= {
        "overheated", "premium", "neutral", "discount", "deep_discount"}
    assert set(out["coinbase_premium_divergence"].dropna().unique()) <= {
        "distribution", "accumulation", "aligned"}


def test_coinbase_premium_falls_back_to_bgeo() -> None:
    """No OKX series -> the bgeo index fills the premium (graceful degradation)."""
    cfg = config.load()["vector"]["onchain"]
    px = _price(seed=3)
    bgeo = pd.Series(0.5, index=px.index)
    out = S.onchain_regime({"price": px, "okx_spot_usdt": None, "coinbase_premium": bgeo}, cfg)
    assert abs(out["coinbase_premium"].dropna().iloc[-1] - 0.5) < 1e-6


# --------------------------------------------------------------------------- #
# 2. Options: VRP regime + DVOL expected-move band
# --------------------------------------------------------------------------- #
def test_options_vrp_and_expected_move() -> None:
    cfg = config.load()["vector"]["options"]
    px = _price(seed=4)
    dvol = pd.Series(np.linspace(40, 80, len(px)), index=px.index)   # rising implied vol
    out = S.options({"price": px, "dvol": dvol, "options_structure": None}, cfg)
    assert out["vrp_z"].dropna().between(-4, 4).all()
    assert set(out["vrp_state"].dropna().unique()) <= {"vol_rich", "vol_cheap", "vol_fair"}
    em = out["expected_move_pct"].dropna()
    assert (em > 0).all()                                  # ±1σ move is positive
    last = out.dropna(subset=["em_upper", "em_lower"]).iloc[-1]
    assert last["em_upper"] > px["close"].iloc[-1] > last["em_lower"]   # band brackets spot


# --------------------------------------------------------------------------- #
# 3. Futures: consolidated carry across CME + funding (+ Deribit)
# --------------------------------------------------------------------------- #
def test_futures_carry_state_and_bounds() -> None:
    cfg = config.load()["vector"]["futures_carry"]
    px = _price(seed=5)
    close = px["close"]
    fut = close * 1.02                                     # CME ~2% rich (contango)
    funding = pd.Series(0.0001, index=close.index)         # mild positive funding
    out = S.futures_carry({"price": px, "btc_future": fut, "funding": funding,
                           "options_structure": None}, cfg)
    assert "carry_cme_pct" in out and "futures_carry_z" in out
    assert out["futures_carry_z"].dropna().between(-4, 4).all()
    assert set(out["futures_carry_state"].dropna().unique()) <= {"froth", "stress", "neutral"}


def test_futures_carry_empty_when_no_inputs() -> None:
    cfg = config.load()["vector"]["futures_carry"]
    out = S.futures_carry({"price": _price(seed=6), "btc_future": None, "funding": None,
                           "options_structure": None}, cfg)
    assert "futures_carry_z" not in out.columns   # nothing to fuse -> no carry column


# --------------------------------------------------------------------------- #
# 4. ETF flows: Farside per-fund USD model
# --------------------------------------------------------------------------- #
def test_etf_flow_farside_usd_model() -> None:
    cfg = config.load()["vector"]["etf_flow"]
    px = _price(n=400, seed=7)
    idx = px.index
    rng = np.random.default_rng(7)
    ibit = pd.Series(rng.normal(120, 40, len(idx)), index=idx)     # dominant inflows
    gbtc = pd.Series(rng.normal(-30, 20, len(idx)), index=idx)     # one-way outflows
    fbtc = pd.Series(rng.normal(20, 15, len(idx)), index=idx)
    total = ibit + gbtc + fbtc
    fdf = pd.DataFrame({"ibit": ibit, "fbtc": fbtc, "gbtc": gbtc, "total": total})
    out = S.etf_flow({"price": px, "etf_flow": None, "farside_total": total,
                      "farside_etf": fdf}, cfg)
    assert "etf_flow_total_usd" in out and "etf_usd_cum" in out
    assert out["etf_usd_z"].dropna().between(-3, 3).all()
    assert out["etf_concentration"].dropna().between(0, 1).all()
    # ex-GBTC net strips the negative GBTC leg -> bigger than the raw total cumulative
    assert out["etf_exgbtc_cum"].dropna().iloc[-1] > out["etf_usd_cum"].dropna().iloc[-1]
    # no bgeo series -> the scored z/state is driven off the USD flow
    assert "etf_flow_state" in out
    assert set(out["etf_flow_divergence"].dropna().unique()) <= {
        "distribution", "accumulation", "aligned"}


# --------------------------------------------------------------------------- #
# 5. Farside HTML parser
# --------------------------------------------------------------------------- #
def test_farside_parse_table() -> None:
    from collectors.farside import parse_table, _num
    assert _num("(95.1)") == -95.1 and _num("1,234") == 1234.0
    assert np.isnan(_num("-")) and np.isnan(_num(""))
    html = """<table>
      <tr><th>Date</th><th>IBIT</th><th>GBTC</th><th>Total</th></tr>
      <tr><td></td><td></td><td></td><td></td></tr>
      <tr><td>11 Jan 2024</td><td>111.7</td><td>(95.1)</td><td>16.6</td></tr>
      <tr><td>12 Jan 2024</td><td>386.0</td><td>(484.1)</td><td>(98.1)</td></tr>
      <tr><td>Total</td><td>497.7</td><td>(579.2)</td><td>(81.5)</td></tr>
    </table>"""
    df = parse_table(html, ["ibit", "gbtc"])
    assert list(df.columns) == ["ibit", "gbtc", "total"]
    assert len(df) == 2                                    # blank + cumulative "Total" rows dropped
    assert df["ibit"].iloc[0] == 111.7 and df["gbtc"].iloc[0] == -95.1
    assert df.index[0] == pd.Timestamp("2024-01-11")


def _run() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
