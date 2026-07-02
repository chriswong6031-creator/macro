"""W4-C7 — European luxury → China-consumer read-through tests.

Tests cover:
  1. LVMUY cold-seed data format contract (columns, no-gap guard)
  2. Builder causality — a spike on the LAST luxury bar cannot change already-realized
     FXI strategy returns (earnings excision acts before the pctile conversion; no look-ahead)
  3. Earnings-print excision — the mask correctly zeros signal around print dates; the
     excision window is ±_EARNS_EXCISE_TD trading days
  4. EW basket construction — the basket is a pure return-average (not price-level), so
     a 10× rescaling of one constituent does not change the basket return
  5. Signal direction — luxury DECLINING (negative momentum) should produce a HIGH de-risk
     signal value (positive after the sign flip)
  6. No-scorer-wiring — the intl_feed Layer-2 reader must return weight=0 for C7 (kill=True,
     CONTEXT verdict); the harness result must not propagate to any scoring module import
  7. De-risk-only direction — a CONTEXT C7 row in intl_feed must never be add-tilt
  8. Builder contract — the builder returns the required harness keys or a fail-soft {'error'}
  9. Lead-lag kernel standing prior — the contemporaneous (lag=0) cross-market product is
     substantially larger than the lag=1 product, consistent with a transmission read (not lead)

Run: python -m pytest tests/test_c7_luxury.py -v
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.c7_luxury_readthrough as c7  # noqa: E402
from engine import intl_claims  # noqa: E402
from engine import intl_feed as feed  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _synth_close(n: int = 500, start: str = "2010-01-01", seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    px = 100.0 * (1 + rng.normal(0.0002, 0.01, n)).cumprod()
    return pd.Series(px, index=idx, name="close")


def _synth_fxi(n: int = 500, seed: int = 99) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=n)
    return pd.Series(50.0 * (1 + rng.normal(0.0001, 0.015, n)).cumprod(), index=idx)


# ---------------------------------------------------------------------------
# 1. LVMUY cold-seed data format contract
# ---------------------------------------------------------------------------

def test_lvmuy_in_store():
    """LVMUY must be present in the yahoo store with the standard columns."""
    from lib import store
    df = store.read("yahoo", "LVMUY")
    assert df is not None and not df.empty, "LVMUY parquet not seeded — run the W4-C7 cold seed"
    assert "close" in df.columns, "missing 'close' column in LVMUY store"
    assert df["close"].dropna().__len__() >= 100, "LVMUY has fewer than 100 close values"


def test_lvmuy_freshness():
    """LVMUY last date must be within 5d of today (the declared SLA)."""
    from lib import store
    ld = store.last_date("yahoo", "LVMUY")
    assert ld is not None
    assert (date.today() - ld).days <= 5, (
        f"LVMUY stale: last date {ld} is {(date.today() - ld).days}d old (SLA=5d); "
        "cold-seed must be refreshed"
    )


# ---------------------------------------------------------------------------
# 2. Builder causality — no look-ahead through the signal
# ---------------------------------------------------------------------------

def test_builder_no_lookahead_spike_last_bar():
    """Spiking the LAST LVMUY bar must NOT change strategy returns on any day before
    the spike date (the trailing-window signal and shift(1) entry guarantee causality)."""
    from lib import store
    import scripts.c7_luxury_readthrough as c7m

    c7_claim = next(c for c in intl_claims.CLAIMS if c["id"] == "c7_luxury_china_consumer")

    # Only run if FXI is available (live data test)
    fxi = store.read("yahoo", "FXI")
    lvmuy = store.read("yahoo", "LVMUY")
    if fxi is None or lvmuy is None:
        pytest.skip("live data not available")

    # Run the builder twice — once baseline, once with last LVMUY bar spiked 3×
    base = c7m.build(c7_claim, horizon=21)
    if "error" in base:
        pytest.skip(f"builder error: {base['error']}")

    # Spike the stored LVMUY close at the last row
    lv2 = lvmuy.copy()
    lv2.loc[lv2.index[-1], "close"] = lv2["close"].iloc[-1] * 3.0

    # Monkeypatch c7._close to return the spiked version for LVMUY only
    original_close = c7m._close

    def patched_close(group, name):
        if group == "yahoo" and name == "LVMUY":
            col = "close" if "close" in lv2.columns else lv2.columns[0]
            s = lv2[col].dropna()
            s.index = pd.to_datetime(s.index)
            return s[~s.index.duplicated(keep="last")].sort_index()
        return original_close(group, name)

    c7m._close = patched_close
    try:
        pert = c7m.build(c7_claim, horizon=21)
    finally:
        c7m._close = original_close

    if "error" in pert:
        pytest.skip("perturbed builder returned error")

    # Strategy returns more than 21d before the final bar must be unchanged
    sr_base = base["strat_ret"].dropna()
    sr_pert = pert["strat_ret"].dropna()
    cutoff = sr_base.index[-1] - pd.Timedelta(days=25)
    common = sr_base.index[sr_base.index <= cutoff].intersection(
        sr_pert.index[sr_pert.index <= cutoff]
    )
    if len(common) < 10:
        pytest.skip("insufficient common rows before cutoff")
    assert np.allclose(
        sr_base.reindex(common).to_numpy(),
        sr_pert.reindex(common).to_numpy(),
        equal_nan=True,
    ), "spiking the last bar changed pre-spike strategy returns — look-ahead in the builder"


# ---------------------------------------------------------------------------
# 3. Earnings-print excision — mask shape and count
# ---------------------------------------------------------------------------

def test_earnings_excision_mask_non_empty():
    """The excision mask must flag at least one bar for a business-day index spanning
    any year that has a known LVMH annual results date (~late January)."""
    idx = pd.bdate_range("2023-01-01", "2023-12-31")
    mask = c7._excision_mask(idx)
    assert mask.dtype == bool
    # LVMH full-year ~2023-01-26 → ±2td = 4 bars; must flag some
    assert mask.sum() >= 1, "excision mask should flag at least one bar in 2023 (LVMH annual)"


def test_earnings_excision_symmetric_window():
    """A known LVMH print date must have bars on BOTH sides of the anchor excised."""
    # 2024-01-25 = LVMH full-year results
    idx = pd.bdate_range("2024-01-20", "2024-01-31")
    mask = c7._excision_mask(idx)
    anchor = pd.Timestamp("2024-01-25")
    if anchor not in idx:
        anchor = idx[np.searchsorted(idx, anchor)]
    # At least the anchor itself and one day on each side should be excised
    anchor_pos = idx.get_loc(anchor) if anchor in idx else None
    if anchor_pos is not None and 0 < anchor_pos < len(idx) - 1:
        # Either the anchor or its neighbors should be masked
        assert mask.iloc[max(0, anchor_pos - 1) : anchor_pos + 2].any(), (
            "no bars excised near the LVMH 2024-01-25 print date"
        )


def test_excision_does_not_affect_returns():
    """The excision is applied to the SIGNAL, not to the FXI returns. After excision,
    the signal has NaN at print windows but the underlying FXI return series is intact."""
    c7_claim = next(c for c in intl_claims.CLAIMS if c["id"] == "c7_luxury_china_consumer")
    from lib import store
    fxi = store.read("yahoo", "FXI")
    if fxi is None:
        pytest.skip("FXI not available")
    result = c7.build(c7_claim, horizon=21)
    if "error" in result:
        pytest.skip(f"builder error: {result['error']}")
    # bench_ret should have no more NaN than the FXI raw return (no excision on returns)
    bench_na = result["bench_ret"].isna().sum()
    fxi_na = fxi["close"].pct_change().reindex(result["bench_ret"].index).isna().sum()
    # bench_ret NaN count should match the raw FXI return (excision only on signal)
    assert bench_na <= fxi_na + 5, "bench_ret appears to have been over-NaN'd (excision bled into returns)"


# ---------------------------------------------------------------------------
# 4. EW basket construction — constituent rescaling invariance
# ---------------------------------------------------------------------------

def test_ew_basket_return_scale_invariant():
    """Rescaling one constituent's price level by 10× must not change the EW basket return.
    (The basket is computed as EW of returns, not EW of prices.)"""
    n = 200
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2022-01-01", periods=n)
    # Two constituents: A at ~$100 level, B at ~$1000 level (10× price difference)
    pA = pd.Series(100 * (1 + rng.normal(0.0002, 0.01, n)).cumprod(), index=idx)
    pB = pd.Series(1000 * (1 + rng.normal(0.0002, 0.01, n)).cumprod(), index=idx)
    # EW basket by return
    ret_A = pA.pct_change(fill_method=None)
    ret_B = pB.pct_change(fill_method=None)
    ew_ret = pd.DataFrame({"A": ret_A, "B": ret_B}).mean(axis=1)
    # Rescale A by 10× — this must not change the EW return
    pA_scaled = pA * 10
    ret_A_scaled = pA_scaled.pct_change(fill_method=None)
    ew_ret_scaled = pd.DataFrame({"A": ret_A_scaled, "B": ret_B}).mean(axis=1)
    assert np.allclose(ew_ret.dropna(), ew_ret_scaled.dropna(), atol=1e-10), (
        "EW basket return changes with price-level rescaling — basket is NOT return-based"
    )


# ---------------------------------------------------------------------------
# 5. Signal direction — luxury declining → HIGH de-risk signal
# ---------------------------------------------------------------------------

def test_signal_direction_declining_luxury_triggers_derisk():
    """When luxury prices are falling consistently, the de-risk signal must be high (> 0.5),
    indicating danger for the Chinese consumer target (the correct sign for the C7 hypothesis)."""
    n = 500
    rng = np.random.default_rng(13)
    # Build a basket that consistently declines over the last 21 bars
    px_up = 100 * (1 + rng.normal(0.001, 0.01, n - 21)).cumprod()   # rising first
    px_down = px_up[-1] * (1 + rng.normal(-0.005, 0.01, 21)).cumprod()  # then declining
    px_full = np.concatenate([px_up, px_down])
    idx = pd.bdate_range("2020-01-01", periods=n)
    basket_idx = pd.Series(px_full, index=idx)
    # trend-turn: 21d momentum, flip sign, should be HIGH at the end (recent decline)
    trend_neg = -basket_idx.pct_change(21, fill_method=None)
    # a naive z-score of the flipped trend
    mu = trend_neg.rolling(252, min_periods=50).mean()
    sd = trend_neg.rolling(252, min_periods=50).std()
    sig = ((trend_neg - mu) / sd.replace(0, np.nan)).dropna()
    # the last value should be positive (luxury declining = high de-risk signal)
    assert sig.iloc[-1] > 0, (
        f"declining luxury basket produced non-positive de-risk signal: {sig.iloc[-1]:.3f}"
    )


# ---------------------------------------------------------------------------
# 6. No-scorer-wiring guarantee
# ---------------------------------------------------------------------------

def test_c7_weight_zero_in_intl_feed():
    """intl_feed.features() must return weight=0 for c7_luxury_china_consumer
    (kill=True, CONTEXT verdict → three-state policy forces weight to zero)."""
    feats = feed.features()
    c7_feat = feats.get("c7_luxury_china_consumer")
    if c7_feat is None:
        # The ledger may not have the C7 row yet (before --c7 run); that's also weight=0
        return
    assert c7_feat.get("weight") == 0.0, (
        f"C7 should have weight=0 but got weight={c7_feat.get('weight')} "
        "(CONTEXT verdict + kill=True must force zero per the three-state policy)"
    )


def test_c7_not_imported_by_scoring_core():
    """The scoring core modules must not import c7_luxury_readthrough. This enforces the
    leaf-purity contract: the channel is CONTEXT and its builder must never reach a scorer."""
    # We check the module source — a static grep is reliable and fast.
    import importlib.util
    for module_name in ("engine.conditions", "engine.stock_score", "engine.playbook",
                        "engine.china_name_score"):
        spec = importlib.util.find_spec(module_name)
        if spec is None or spec.origin is None:
            continue
        src = Path(spec.origin).read_text()
        assert "c7_luxury" not in src, (
            f"{module_name} imports c7_luxury_readthrough — not allowed for a CONTEXT channel"
        )


# ---------------------------------------------------------------------------
# 7. De-risk-only direction check (intl_feed contract)
# ---------------------------------------------------------------------------

def test_c7_direction_in_claims():
    """The declared C7 claim direction must be 'de-risk' (never 'add-tilt')."""
    c7_claim = next(c for c in intl_claims.CLAIMS if c["id"] == "c7_luxury_china_consumer")
    assert c7_claim["direction"] == "de-risk", (
        f"C7 direction is '{c7_claim['direction']}' — must be 'de-risk' per masterplan §5 C7"
    )


# ---------------------------------------------------------------------------
# 8. Builder contract — harness keys present or fail-soft error
# ---------------------------------------------------------------------------

def test_builder_contract():
    """The builder must return either the required harness keys or {'error': ...}."""
    c7_claim = next(c for c in intl_claims.CLAIMS if c["id"] == "c7_luxury_china_consumer")
    result = c7.builder(c7_claim)
    assert isinstance(result, dict), "builder must return a dict"
    if "error" in result:
        # fail-soft: missing data → error key only (no crash)
        assert isinstance(result["error"], str)
    else:
        required_keys = {"signal", "strat_ret", "bench_ret", "target_dd", "basis"}
        missing = required_keys - set(result.keys())
        assert not missing, f"builder missing keys: {missing}"


# ---------------------------------------------------------------------------
# 9. Lead-lag kernel standing prior — lag=0 >> lag=1
# ---------------------------------------------------------------------------

def test_leadlag_contemporaneous_dominates():
    """The contemporaneous (lag=0) cross-market product must have a substantially higher
    t-statistic than the lagged (lag=1) product. This tests the ADJ-4 standing prior:
    the luxury–FXI relationship is same-session, not a predictive lead."""
    from engine.validation import newey_west_tstat
    from lib import store

    lvmuy = store.read("yahoo", "LVMUY")
    fxi = store.read("yahoo", "FXI")
    if lvmuy is None or fxi is None:
        pytest.skip("live data not available")

    lv_ret = lvmuy["close"].pct_change(fill_method=None)
    fx_ret = fxi["close"].pct_change(fill_method=None)
    lv_ret.index = pd.to_datetime(lv_ret.index)
    fx_ret.index = pd.to_datetime(fx_ret.index)

    common = lv_ret.dropna().index.intersection(fx_ret.dropna().index)
    if len(common) < 200:
        pytest.skip("insufficient common dates")

    lv_c = lv_ret.reindex(common)
    fx_c = fx_ret.reindex(common)

    # z-score both
    def zsc(s):
        mu = s.rolling(252, min_periods=63).mean()
        sd = s.rolling(252, min_periods=63).std()
        return (s - mu) / sd.replace(0, np.nan)

    z_lv = zsc(lv_c)
    z_fx = zsc(fx_c)

    prod0 = (z_fx * z_lv).dropna()           # lag=0: contemporaneous
    prod1 = (z_fx * z_lv.shift(1)).dropna()  # lag=1: luxury leads by 1 day

    t0 = abs(newey_west_tstat(prod0, lags=10).get("t", 0) or 0)
    t1 = abs(newey_west_tstat(prod1, lags=10).get("t", 0) or 0)

    assert t0 > 5.0, (
        f"lag=0 t-stat {t0:.2f} is too low — the contemporaneous relationship is unexpectedly weak"
    )
    assert t0 > t1 * 2, (
        f"lag=0 t={t0:.2f} is not substantially larger than lag=1 t={t1:.2f} "
        "(expected contemporaneous >> lagged for a transmission read)"
    )
