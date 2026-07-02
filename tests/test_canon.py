"""Golden-vector + invariant tests for engine/canon.py (audit #7 #12 #28 #40 #45).

canon is the single source of truth for concepts computed divergently across engines.
These tests (a) pin every canon function to its committed golden vector so a silent math
change is caught, (b) assert the cross-engine invariants (net-liq 3-term + mixed-unit
guard, credit-impulse LEVEL≠ACCEL, one VIX basis, XLC impossible-prior retired), and
(c) prove canon byte-matches the consumers it is migrating (anticipation netliq loader,
china credit-impulse locals, vol_regime/conditions VIX ratio).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import canon

GOLDEN = json.loads((Path(__file__).parent / "golden" / "canon_vectors.json").read_text())


def _close(nan_ok=True):
    return  # placeholder for parametrization symmetry


def _eq(a, b, atol=1e-6):
    a = [np.nan if x is None else x for x in a]
    b = [np.nan if x is None else x for x in b]
    return np.allclose(np.asarray(a, float), np.asarray(b, float), atol=atol, equal_nan=True)


# ── 1 · NET LIQUIDITY ────────────────────────────────────────────────────────
def test_net_liquidity_golden():
    g = GOLDEN["net_liquidity_bn"]
    i = g["inputs"]
    out = canon.net_liquidity_bn(pd.Series(i["walcl_bn"]), pd.Series(i["rrp_bn"]),
                                 pd.Series(i["tga_bn"]))
    assert _eq(out.round(4).to_list(), g["expected"])


def test_net_liquidity_is_three_term():
    """WALCL − RRP − TGA, not the 2-term forex variant (which dropped TGA — a bug)."""
    idx = pd.date_range("2024-01-01", periods=5)
    walcl = pd.Series([7000.0] * 5, idx)
    rrp = pd.Series([50.0] * 5, idx)
    tga = pd.Series([500.0] * 5, idx)
    assert (canon.net_liquidity_bn(walcl, rrp, tga) == 6450.0).all()
    # dropping TGA (the forex bug) would give 6950 — canon must include it
    assert (canon.net_liquidity_bn(walcl, rrp, tga) != 6950.0).all()


def test_net_liquidity_mixed_unit_guard_fires():
    """The #28 mixed-unit subtraction (WALCL trillions − RRP billions) fails LOUDLY."""
    with pytest.raises(ValueError, match="audit #28"):
        canon.net_liquidity_bn(pd.Series([6.7, 6.75, 6.8, 6.85]),
                               pd.Series([26.9, 27.0, 28.0, 29.0]), None)


def test_net_liquidity_missing_drain_does_not_annihilate():
    """A missing RRP/TGA contributes 0 — the balance-sheet trend must survive."""
    walcl = pd.Series([7000.0, 7050.0, 7100.0])
    out = canon.net_liquidity_bn(walcl, None, None)
    assert out.equals(walcl)  # no drain → net == balance sheet, trend intact


def test_dollar_liquidity_roc_is_negated_change():
    """forex framing = −Δ net-liq: falling liquidity ⇒ positive (USD supportive)."""
    g = GOLDEN["dollar_liquidity_roc"]
    i = GOLDEN["net_liquidity_bn"]["inputs"]
    nl = canon.net_liquidity_bn(pd.Series(i["walcl_bn"]), pd.Series(i["rrp_bn"]),
                                pd.Series(i["tga_bn"]))
    out = canon.dollar_liquidity_roc(nl, g["window_d"])
    assert _eq(out.round(4).to_list(), g["expected"])
    # sign contract: it is exactly the negative of the raw change
    raw = canon.net_liquidity_bn_change(nl, g["window_d"])
    assert _eq((-raw).round(4).to_list(), out.round(4).to_list())


def test_net_liquidity_loader_matches_anticipation():
    """canon.load_net_liquidity_components byte-matches anticipation's migrated local."""
    fred = Path("data/fred")
    if not (fred / "WALCL.parquet").exists():
        pytest.skip("no local FRED store")
    from engine import anticipation
    idx = pd.bdate_range("2015-01-01", "2026-06-30")
    c = canon.load_net_liquidity_components(idx)
    a = anticipation._net_liquidity_bn(idx)
    for k in ("walcl_bn", "rrp_bn", "tga_bn", "netliq_bn"):
        assert np.allclose(c[k].fillna(-999.0), a[k].fillna(-999.0)), k


# ── 2 · CREDIT IMPULSE (label collision) ─────────────────────────────────────
def test_credit_impulse_golden():
    g = GOLDEN["credit_impulse"]
    tsf = pd.Series(g["inputs"]["tsf_total"],
                    index=pd.date_range("2020-01-31", periods=len(g["inputs"]["tsf_total"]),
                                        freq="ME"))
    assert _eq(canon.credit_impulse_level(tsf).to_list(), g["level_expected"])
    assert _eq(canon.credit_impulse_accel(tsf).to_list(), g["accel_expected"])


def test_credit_impulse_level_and_accel_differ():
    """The whole point of the fix: they are mathematically DIFFERENT series."""
    tsf = pd.Series(GOLDEN["credit_impulse"]["inputs"]["tsf_total"],
                    index=pd.date_range("2020-01-31",
                                        periods=len(GOLDEN["credit_impulse"]["inputs"]["tsf_total"]),
                                        freq="ME"))
    lvl = canon.credit_impulse_level(tsf).dropna()
    acc = canon.credit_impulse_accel(tsf).dropna()
    common = lvl.index.intersection(acc.index)
    assert not np.allclose(lvl.loc[common], acc.loc[common])


def test_credit_impulse_matches_radar_and_strategies_locals():
    """LEVEL == china_radar local; ACCEL == china_strategies local (pre-migration math)."""
    tsf = pd.Series(np.linspace(100, 400, 60),
                    index=pd.date_range("2019-01-31", periods=60, freq="ME"))
    radar_local = tsf.rolling(12).sum().pct_change(6)
    strat_local = (tsf.rolling(12).sum().pct_change(12) * 100.0).diff(6)
    assert _eq(canon.credit_impulse_level(tsf).to_list(), radar_local.to_list())
    assert _eq(canon.credit_impulse_accel(tsf).to_list(), strat_local.to_list())


# ── 3 · VIX TERM ─────────────────────────────────────────────────────────────
def test_vix_term_golden():
    g = GOLDEN["vix_term"]
    out = canon.vix_term(pd.Series(g["inputs"]["vix"]), pd.Series(g["inputs"]["vix3m"]))
    assert _eq(out.to_list(), g["expected"])
    assert abs(canon.vix_term_scalar(20, 19) - g["scalar_20_19"]) < 1e-6


def test_vix_term_backwardation_semantics():
    """≥ 1 = backwardation (stress); < 1 = contango (calm) — the one basis."""
    assert canon.vix_term_scalar(30, 24) > 1.0   # spike front-month → backwardation
    assert canon.vix_term_scalar(14, 18) < 1.0   # calm → contango
    assert canon.vix_term_scalar(20, 0) is None  # degenerate → None, never a div-by-zero


# ── 4 · SECTOR MACRO BETA (shadow) ───────────────────────────────────────────
def test_sector_macro_beta_blend_golden():
    g = GOLDEN["sector_macro_beta_blend"]
    i = g["inputs"]
    out = canon.sector_macro_beta_blend(i["prior"], i["measured"],
                                        shrink_k=i["shrink_k"], measured_n=i["measured_n"])
    assert out == g["expected"]


def test_sector_macro_beta_retires_impossible_xlc():
    """XLC=1.0 predates XLC's 2018 launch → retired to 0.0, flagged."""
    out = canon.sector_macro_beta_blend({"XLC": 1.0}, {}, measured_n={})
    assert out["XLC"]["blended"] == 0.0
    assert out["XLC"]["retired_impossible_prior"] is True


def test_sector_macro_beta_shrinks_toward_prior_when_unmeasured():
    out = canon.sector_macro_beta_blend({"XLE": 0.16}, {}, measured_n={})
    assert out["XLE"]["w"] == 0.0 and out["XLE"]["blended"] == 0.16


def test_sector_macro_beta_blend_is_convex():
    """blended is a convex combination of measured and prior (never extrapolates)."""
    out = canon.sector_macro_beta_blend({"XLF": 1.0}, {"XLF": 0.5},
                                        shrink_k=8.0, measured_n={"XLF": 100})
    r = out["XLF"]
    assert min(r["measured"], r["prior"]) <= r["blended"] <= max(r["measured"], r["prior"])


# ── 5 · CORRECTED CONFLUENCE PRIMITIVES ──────────────────────────────────────
def _golden_close():
    g = GOLDEN["confluence_primitives"]["inputs"]
    return pd.Series(g["close"], pd.bdate_range(g["start"], periods=len(g["close"])))


def test_confluence_primitives_golden():
    g = GOLDEN["confluence_primitives"]
    c = _golden_close()
    assert _eq(canon.rma(c, 14).to_numpy()[-10:], g["rma14_tail"])
    assert _eq(canon.ema(c, 14).to_numpy()[-10:], g["ema14_tail"])
    assert _eq(canon.rsi(c, 14).to_numpy()[-10:], g["rsi14_tail"])
    b, _ = canon.resample_sessions(c, 3)
    assert len(b) == g["session3_len"]
    assert str(b.index[-1].date()) == g["session3_last_date"]


def test_rma_is_sma_seeded():
    """The seed is the SMA of the first n bars (Pine ta.rma), not ewm-from-bar-0."""
    c = pd.Series(np.arange(1, 21, dtype=float))
    r = canon.rma(c, 5)
    assert r.iloc[:4].isna().all()          # warm-up NaN before the seed
    assert abs(r.iloc[4] - 3.0) < 1e-9      # SMA of 1..5 == 3.0
    # bare ewm(alpha=1/5) would give a different, non-3.0 value at bar 4
    bare = c.ewm(alpha=1 / 5, min_periods=5).mean()
    assert abs(bare.iloc[4] - 3.0) > 1e-6


def test_ema_is_adjust_false():
    c = pd.Series(np.arange(1, 21, dtype=float))
    assert canon.ema(c, 5).equals(c.ewm(span=5, adjust=False, min_periods=5).mean())
    # and differs from the adjust=True default
    assert not np.allclose(canon.ema(c, 5).dropna(),
                           c.ewm(span=5, min_periods=5).mean().dropna())


def test_session_resample_not_calendar_3b():
    """Session-grouping every 3rd BAR ≠ calendar resample('3B') across gaps.

    A holiday/gap makes the calendar bin re-anchor; session-grouping does not.  We insert
    a gap and assert the two produce different bucket COUNTS (the audit's ~80%-relocation
    root cause on NVDA)."""
    idx = list(pd.bdate_range("2024-01-01", periods=30))
    # drop a week mid-series to simulate a listing/holiday gap
    idx = idx[:10] + idx[20:]
    c = pd.Series(np.arange(len(idx), dtype=float), index=pd.DatetimeIndex(idx))
    session_buckets = len(canon.resample_sessions(c, 3)[0])
    calendar_buckets = len(c.resample("3B").last().dropna())
    assert session_buckets != calendar_buckets


def test_confluence_signals_columns_match_terminal():
    """The oracle frame carries exactly the columns golden_gate diffs 1:1."""
    c = _golden_close()
    # extend to ≥90 3D buckets so compute doesn't early-return
    long_c = pd.concat([c, c.iloc[-1] * (1 + pd.Series(
        np.cumsum(np.random.RandomState(1).randn(400) * 0.01),
        index=pd.bdate_range(c.index[-1] + pd.Timedelta(days=1), periods=400)))])
    sig = canon.confluence_signals(long_c)
    if sig.empty:
        pytest.skip("insufficient history for the fixture")
    for col in ("macd", "sig", "k", "d", "rsi14", "CB", "CS", "revBuy", "revSell",
                "w_bull", "above200", "mo_bull", "w2_bull"):
        assert col in sig.columns, col
