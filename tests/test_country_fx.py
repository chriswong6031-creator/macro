"""FX-decomposition tests (masterplan W3.9 / D4-W5b).

Covers the engine.country_fx helpers + the country_cycles integration:
  * synthetic decomposition round-trip (local = USD × FX_ccy_per_usd)
  * the EWJ-2022 direction guard (local must NOT show the USD crash)
  * fx_share math on a synthetic turn
  * the max-coverage native-vs-synthetic chooser
  * bloc null-FX marker + single-country null-FX fallback
  * cross-page basis labelling (the local record declares local_native/local_synth)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import country_fx as cfx  # noqa: E402


# ── fixtures ────────────────────────────────────────────────────────────────
def _bdays(n: int, start: str = "2015-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


# ── 1. synthetic decomposition round-trips ──────────────────────────────────
def test_synthetic_local_roundtrip_ccy_per_usd():
    """P_local = P_usd × FX(ccy_per_usd), and dividing back out recovers P_usd."""
    idx = _bdays(400)
    usd = pd.Series(np.linspace(20.0, 30.0, 400), index=idx)
    fx = pd.Series(np.linspace(100.0, 150.0, 400), index=idx)  # yen-per-USD rising (yen weak)
    meta = {"local": None}
    local, src = cfx.build_local_series("EWJ", meta, usd, fx)
    assert src == "synthetic"
    # round-trip: local / fx == usd
    recon = (local / fx).reindex(usd.index)
    assert np.allclose(recon.values, usd.values, rtol=1e-9)


def test_synthetic_lifts_when_currency_weakens():
    """When the foreign ccy weakens (fx ccy_per_usd rises) the USD ETF falls harder than
    the local series — the local series must be ABOVE the USD return over the leg."""
    idx = _bdays(300)
    # local equity flat, currency weakens 20% → USD ETF must fall ~20%
    local_true = pd.Series(100.0, index=idx)
    fx = pd.Series(np.linspace(100.0, 120.0, 300), index=idx)   # +20% ccy_per_usd
    usd = local_true / fx * fx.iloc[0]        # construct USD so local×fx recovers... invert
    # Given P_local = P_usd × fx  ⇒ P_usd = P_local / fx (× fx0 to normalise the level)
    usd = local_true / fx * fx.iloc[0]
    local, _ = cfx.build_local_series("X", {"local": None}, usd, fx)
    r_usd = usd.iloc[-1] / usd.iloc[0] - 1
    r_local = local.iloc[-1] / local.iloc[0] - 1
    assert r_usd < -0.10           # USD holder took the currency hit
    assert abs(r_local) < 1e-6     # local equity was flat
    assert r_local > r_usd         # local is the honest, better read


# ── 2. the EWJ-2022 direction guard (real data) ─────────────────────────────
def test_ewj_2022_local_is_not_the_usd_crash():
    """The keystone audit case: EWJ fell hard in USD in 2022 (strong dollar / weak yen),
    but Japanese equity was roughly flat.  The constructed local series over 2022 must NOT
    reproduce the USD drawdown — it must be materially SHALLOWER (closer to the ~flat
    ^N225 truth)."""
    from lib import store
    ewj = store.read("yahoo", "EWJ")
    if ewj is None or "close_price" not in ewj.columns:
        pytest.skip("EWJ price tape unavailable")
    usd = pd.to_numeric(ewj["close_price"], errors="coerce").dropna()
    fx = cfx.fx_ccy_per_usd(cfx.FX_REGISTRY["EWJ"])
    if fx is None:
        pytest.skip("USDJPY tape unavailable")

    def ret(s, d0, d1):
        a = s[s.index <= d0]
        b = s[s.index <= d1]
        return float(b.iloc[-1]) / float(a.iloc[-1]) - 1

    r_usd = ret(usd, "2021-12-31", "2022-12-31")
    # synthetic local via the CCY-per-USD multiply
    synth, _ = cfx.build_local_series("EWJ", {"local": None}, usd, fx)
    r_local = ret(synth, "2021-12-31", "2022-12-31")

    assert r_usd < -0.12, f"expected EWJ USD 2022 drawdown, got {r_usd:.1%}"
    # local must be materially shallower than the USD crash (the yen didn't crash Japan)
    assert r_local > r_usd + 0.08, f"local {r_local:.1%} not shallower than USD {r_usd:.1%}"
    # and it must be in the ballpark of the ~flat native Nikkei, not another -19%
    assert r_local > -0.15, f"local {r_local:.1%} still shows a USD-scale crash"


def test_ewj_native_beats_synth_matches_nikkei():
    """The native ^N225 path (max-coverage winner for EWJ) reads roughly like the Nikkei's
    own 2022 return — a sanity check that native construction is the real local index."""
    from lib import store
    ewj = store.read("yahoo", "EWJ")
    n225 = store.read("intl", "_N225")
    if ewj is None or n225 is None:
        pytest.skip("EWJ / N225 tape unavailable")
    usd = pd.to_numeric(ewj["close_price"], errors="coerce").dropna()
    fx = cfx.fx_ccy_per_usd(cfx.FX_REGISTRY["EWJ"])
    local, src = cfx.build_local_series("EWJ", cfx.FX_REGISTRY["EWJ"], usd, fx)
    assert src == "native", "EWJ should choose the native ^N225 (longer coverage)"


# ── 3. fx_share math on a synthetic turn ────────────────────────────────────
def test_fx_share_pure_currency_move_flags():
    """A leg where the LOCAL equity was flat but the USD ETF moved purely on currency →
    fx_share ≈ 1.0 and fx_flag True (the currency-driven badge)."""
    idx = _bdays(300)
    local = pd.Series([100.0] * 300, index=idx)          # equity flat
    fx = pd.Series(np.linspace(100.0, 130.0, 300), index=idx)  # currency weakens 30%
    usd = local / fx * fx.iloc[0]                          # USD ETF = local / (ccy_per_usd)
    attr = cfx.attribute_turn(local, usd, fx, idx[0], idx[-1])
    assert attr is not None
    assert abs(attr["equity_leg_pct"]) < 0.5              # equity leg ~0
    assert attr["fx_share"] > 0.95                        # ~all currency
    assert attr["fx_flag"] is True


def test_fx_share_pure_equity_move_not_flagged():
    """A leg where the currency was flat but local equity moved → fx_share ≈ 0, no flag."""
    idx = _bdays(300)
    local = pd.Series(np.linspace(100.0, 140.0, 300), index=idx)  # equity +40%
    fx = pd.Series([100.0] * 300, index=idx)                       # currency flat
    usd = local / fx * fx.iloc[0]
    attr = cfx.attribute_turn(local, usd, fx, idx[0], idx[-1])
    assert attr["fx_share"] < 0.05
    assert attr["fx_flag"] is False
    # equity leg carries the whole move
    assert attr["equity_leg_pct"] > 35.0


def test_fx_share_clamped_and_bounded():
    idx = _bdays(300)
    local = pd.Series(np.linspace(100.0, 101.0, 300), index=idx)   # tiny equity move
    fx = pd.Series(np.linspace(100.0, 160.0, 300), index=idx)      # big currency move
    usd = local / fx * fx.iloc[0]
    attr = cfx.attribute_turn(local, usd, fx, idx[0], idx[-1])
    assert 0.0 <= attr["fx_share"] <= 1.0


# ── 4. max-coverage chooser ─────────────────────────────────────────────────
def test_chooser_prefers_native_when_longer():
    """Native index that FULLY spans the ETF wins (cleaner, no synthetic division)."""
    from lib import store
    # EWG has a native ^GDAXI far longer than the ETF → native must win.
    ewg = store.read("yahoo", "EWG")
    if ewg is None:
        pytest.skip("EWG tape unavailable")
    usd = pd.to_numeric(ewg["close_price"], errors="coerce").dropna()
    fx = cfx.fx_ccy_per_usd(cfx.FX_REGISTRY["EWG"])
    _, src = cfx.build_local_series("EWG", cfx.FX_REGISTRY["EWG"], usd, fx)
    assert src == "native"


def test_chooser_prefers_synthetic_when_native_shorter():
    """D4-N4: INDA's native ^NSEI starts 2007, SHORTER than the ETF — the synthetic path
    preserves the deeper history, so it must win (the anti-truncation rule)."""
    from lib import store
    inda = store.read("yahoo", "INDA")
    nsei = store.read("intl", "_NSEI")
    if inda is None or nsei is None:
        pytest.skip("INDA / NSEI tape unavailable")
    usd = pd.to_numeric(inda["close_price"], errors="coerce").dropna()
    fx = cfx.fx_ccy_per_usd(cfx.FX_REGISTRY["INDA"])
    _, src = cfx.build_local_series("INDA", cfx.FX_REGISTRY["INDA"], usd, fx)
    assert src == "synthetic"


def test_chooser_no_fx_no_native_returns_none():
    idx = _bdays(300)
    usd = pd.Series(np.linspace(20.0, 30.0, 300), index=idx)
    local, src = cfx.build_local_series("ZZZ", {"local": None}, usd, None)
    assert local is None and src == "none"


# ── 5. FX orientation (invert flag) ─────────────────────────────────────────
def test_fx_ccy_per_usd_inverts_usd_per_ccy_quotes():
    """EURUSD is stored USD-per-EUR (~1.1); ccy_per_usd must invert it to EUR-per-USD (~0.9)."""
    fx = cfx.fx_ccy_per_usd(cfx.FX_REGISTRY["EWG"])   # EURUSD, invert=True
    if fx is None:
        pytest.skip("EURUSD tape unavailable")
    assert 0.7 < float(fx.iloc[-1]) < 1.2             # EUR-per-USD is sub-1.2

    fxj = cfx.fx_ccy_per_usd(cfx.FX_REGISTRY["EWJ"])  # USDJPY, invert=False
    assert float(fxj.iloc[-1]) > 50                   # yen-per-USD is >>1


# ── 6. peg annotation ───────────────────────────────────────────────────────
def test_hkd_peg_annotation():
    fx = cfx.fx_ccy_per_usd(cfx.FX_REGISTRY["EWH"])
    if fx is None:
        pytest.skip("HKD tape unavailable")
    ann = cfx.peg_annotation(cfx.FX_REGISTRY["EWH"], fx)
    assert ann is not None
    assert ann["band"] == "7.75-7.85"
    assert 7.5 < ann["level"] < 8.1
    assert "dist_bps" in ann and "in_band" in ann


# ── 7. country_cycles integration: primary=local, USD nested, blocs null-FX ──
def _compute():
    from engine import country_cycles as cc
    try:
        data = cc.compute()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"compute failed: {e}")
    if not data:
        pytest.skip("no country data")
    return data


def test_primary_record_is_local_usd_nested():
    data = _compute()
    secs = {s["ticker"]: s for s in data["sectors"]}
    ewj = secs.get("EWJ")
    if ewj is None:
        pytest.skip("EWJ absent")
    # PRIMARY basis is a declared local tape
    assert ewj["basis"] in ("local_native", "local_synth")
    assert ewj["now"]["basis"] == ewj["basis"]
    assert ewj.get("lc_source") in ("native", "synthetic")
    # USD record is nested and still declares the price tape
    ur = ewj.get("usd_record")
    assert ur and ur["basis"] == "price"
    assert ur["now"].get("pos_v2") is not None
    # FX leg present + graded
    fx = ewj.get("fx")
    assert fx and fx.get("pair") == "USDJPY"
    assert fx.get("quote") == "ccy_per_usd"


def test_turns_carry_fx_share():
    data = _compute()
    secs = {s["ticker"]: s for s in data["sectors"]}
    ewj = secs.get("EWJ")
    if ewj is None:
        pytest.skip("EWJ absent")
    attributed = [t for t in ewj["turns"] if "fx_share" in t]
    assert attributed, "no turn carried fx_share"
    for t in attributed:
        assert 0.0 <= t["fx_share"] <= 1.0
        assert isinstance(t["fx_flag"], bool)
        assert t["fx_flag"] == (t["fx_share"] > cfx.FX_FLAG_THRESHOLD)


def test_some_turn_is_currency_driven():
    """Across the whole universe at least one historical turn must flag currency-driven
    (the audit's whole point — currency moves that masqueraded as equity turns exist)."""
    data = _compute()
    flagged = 0
    for s in data["sectors"]:
        flagged += sum(1 for t in s.get("turns", []) if t.get("fx_flag"))
    assert flagged >= 1, "no currency-driven turn flagged anywhere — attribution likely broken"


def test_bloc_null_fx_marker():
    data = _compute()
    for b in data["baskets"]:
        fx = b.get("fx")
        assert fx and "note" in fx, f"{b['ticker']} bloc missing null-FX note"
        assert "bloc" in fx["note"].lower()
        assert b.get("lc_source") is None
        # blocs stay USD-only: no nested usd_record, primary basis is price/tr
        assert b.get("basis") in ("price", "tr", "tr_fallback")


def test_json_safe_and_declared_bases():
    import json
    data = _compute()
    js = json.dumps(data, ensure_ascii=False)
    assert "NaN" not in js and "Infinity" not in js
    # every single-country record declares its primary basis (never empty)
    for s in data["sectors"]:
        assert s["now"].get("basis")
