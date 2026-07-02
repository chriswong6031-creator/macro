"""C1 builder — the per-name global-beta size-dampener measurement for the China book.

This is the causal signal the ``scripts/intl_phase0`` harness grades for claim
``c1_china_global_beta``. It ports engine/hk_global_beta.py to the A-share panel and
measures whether the specific C1 mechanism holds:

    high-minus-low global-beta names get DIFFERENTIALLY deeper forward drawdowns
    *when the global risk state deteriorates* (a de-risk-direction-only dampener).

It returns the harness builder contract (signal / strat_ret / bench_ret / target_dd /
basis / split_half_same_sign / ic) so decide() folds it through the full battery:
DSR, orthogonality vs the existing CN RORO composite, crisis-count effective-N,
crisis-independent ES.

MEASURED VERDICT (2026-07-02, china_search ~5y panel + FXI 2004+ aggregate):
  * Transmission: HK/China ratio ~2.4x (HK SPY-beta 0.49 vs CSI300 0.20) — the Mainland
    couples to global risk ~half as much as HK, exactly the china_global_factors prior.
  * Per-name beta->fwd-DD rank-IC ~-0.17 (t~-13) — strong but UNCONDITIONAL (beta is beta).
  * The RORO-CONDITIONAL dampener edge (off-minus-on hi-lo DD spread) is +0.6pp — the
    WRONG direction: the beta effect does NOT intensify in risk-off. Refuted.
  * Only 3 in-window crises on the per-name panel; FXI aggregate global-risk-off DD lift 1.14x.
  => CONTEXT. A descriptive risk exposure, not a de-risk timing signal. NOT wired.

Kept as a committed, reproducible builder so the ledger regenerates truthfully and a
future deeper A-share panel can re-run the exact same measurement.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import china_conditions
from lib import config, store

log = logging.getLogger(__name__)

WIN, MINP = 252, 126
MIN_HISTORY = 400        # per-name close obs required to enter the panel
FACTOR_GROUP, FACTOR_TICKER = "yahoo", "SPY"   # HK convention: S&P 500, overnight-lagged
FXI_GROUP, FXI_TICKER = "yahoo", "FXI"          # the tradeable China aggregate (bench + target)


def _panel() -> pd.DataFrame | None:
    dd = config.data_dir()
    p = dd / "china_search" / "closes.parquet"
    if not p.exists():
        return None
    cl = pd.read_parquet(p).sort_index()
    cl = cl.loc[:, ~cl.columns.duplicated()]
    good = cl.columns[cl.notna().sum() >= MIN_HISTORY]
    return cl[good] if len(good) else None


def _factor_ret() -> pd.Series | None:
    df = store.read(FACTOR_GROUP, FACTOR_TICKER)
    if df is None or "close" not in df.columns:
        return None
    # S&P 500 returns lagged ONE day — the overnight US->Asia transmission (HK convention).
    return df["close"].pct_change(fill_method=None).shift(1)


def _causal_beta_ts(R: pd.DataFrame, fac: pd.Series) -> pd.DataFrame:
    fa = fac.reindex(R.index)
    return R.rolling(WIN, min_periods=MINP).cov(fa).div(
        fa.rolling(WIN, min_periods=MINP).var(), axis=0).shift(1)


def _fwd_maxdd(r: pd.Series, h: int) -> pd.Series:
    """Forward max-drawdown over [t, t+h] for a return series."""
    eq = (1.0 + r).cumprod()
    a = eq.values
    out = np.full(len(a), np.nan)
    for i in range(len(a)):
        w = a[i:i + h]
        w = w[~np.isnan(w)]
        if len(w) >= 5:
            out[i] = float(np.min(w / np.maximum.accumulate(w) - 1.0))
    return pd.Series(out, index=r.index)


def _roro_state(idx: pd.DatetimeIndex) -> pd.Series:
    """The existing CN RORO composite (engine/china_conditions), reindexed to the panel.
    This is BOTH the orthogonality basis and the dampener's risk-state gate. Best-effort:
    an unavailable RORO returns an all-NaN series (the gate then can't condition — honest)."""
    try:
        from engine.china_inputs import build_features
        rf = china_conditions.roro_frame(build_features())
        if "roro" in rf.columns:
            return rf["roro"].reindex(idx).ffill(limit=5)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("c1: CN RORO unavailable (%s)", e)
    return pd.Series(index=idx, dtype=float)


def build(claim: dict, horizon: int = 42) -> dict:
    """The harness builder contract for c1_china_global_beta at ONE horizon.

    Strategy under test (de-risk-direction only): a book long the HIGH-global-beta
    tercile that DE-RISKS (goes flat) on days the CN RORO is risk-off, vs the always-
    long high-beta book (the benchmark whose drawdown the dampener claims to reduce).
    The `signal` graded for orthogonality is the daily cross-sectional beta dispersion
    (a de-risk lean = high dispersion into risk-off); `target_dd` is the high-beta
    tercile's forward maxDD.
    """
    panel = _panel()
    fac = _factor_ret()
    if panel is None or fac is None:
        return {"error": "china_search panel or SPY factor unavailable"}
    R = panel.pct_change(fill_method=None)
    idx = R.index
    beta_ts = _causal_beta_ts(R, fac)
    roro = _roro_state(idx)
    roro_off = roro < -0.35        # the engine's own risk-off band

    # daily high-beta tercile equal-weight return (the amplifier book)
    hi_ret, lo_ret = [], []
    for dt in idx:
        b = beta_ts.loc[dt].dropna()
        if len(b) < 60:
            hi_ret.append(np.nan); lo_ret.append(np.nan); continue
        hi = b[b >= b.quantile(2 / 3)].index
        lo = b[b <= b.quantile(1 / 3)].index
        hi_ret.append(R.loc[dt, hi].mean())
        lo_ret.append(R.loc[dt, lo].mean())
    hi_ret = pd.Series(hi_ret, index=idx)
    lo_ret = pd.Series(lo_ret, index=idx).dropna()
    hi_ret = hi_ret.dropna()

    # de-risk strategy return: hold the hi-beta book, go FLAT the day after RORO turns
    # risk-off (causal: the gate uses yesterday's RORO). The delta vs the always-long
    # hi-beta book is the dampener's realized DD reduction.
    gate = (~roro_off.shift(1).fillna(False)).reindex(hi_ret.index).astype(float)  # 1 = stay in
    strat_ret = (hi_ret * gate).dropna()
    bench_ret = hi_ret.reindex(strat_ret.index)

    # signal for orthogonality: cross-sectional beta dispersion (p66 - p33) — the leg's
    # daily "how amplified is the book" reading that a de-risk dampener would key off.
    disp = beta_ts.apply(lambda row: (row.dropna().quantile(2 / 3) - row.dropna().quantile(1 / 3))
                         if row.notna().sum() >= 60 else np.nan, axis=1).dropna()
    target_dd = _fwd_maxdd(hi_ret, horizon).reindex(disp.index)

    # orthogonality basis: the existing CN RORO composite (must add residual DD content)
    basis = [roro.reindex(disp.index)]

    # split-half same-sign of the tercile hi-lo forward-DD spread (the dampener grain)
    fdd = _fwd_maxdd(hi_ret, horizon)
    lo_fdd = _fwd_maxdd(lo_ret, horizon)
    spread = (fdd - lo_fdd.reindex(fdd.index)).dropna()
    if len(spread) > 60:
        mid = spread.index[len(spread) // 2]
        s1 = spread[spread.index < mid].mean()
        s2 = spread[spread.index >= mid].mean()
        split_same = bool(np.sign(s1) == np.sign(s2))
    else:
        split_same = None

    # IC of beta vs forward-DD (correct de-risk sign = negative)
    ics = []
    for dt in idx:
        b = beta_ts.loc[dt].dropna()
        y = target_dd.reindex(disp.index)  # not per-name here; compute per-name IC directly
    # per-name daily rank-IC (beta_i vs its own forward maxDD_i)
    fdd_panel = pd.DataFrame({c: _fwd_maxdd(R[c], horizon) for c in R.columns})
    ic_list = []
    for dt in idx:
        b = beta_ts.loc[dt].dropna()
        y = fdd_panel.loc[dt].reindex(b.index).dropna()
        common = b.index.intersection(y.index)
        if len(common) < 50:
            continue
        ic = b[common].rank().corr(y.reindex(common).rank())
        if np.isfinite(ic):
            ic_list.append(ic)
    ic = float(np.mean(ic_list)) if ic_list else None

    return {
        "signal": disp, "strat_ret": strat_ret, "bench_ret": bench_ret,
        "target_dd": target_dd, "basis": basis,
        "split_half_same_sign": split_same, "ic": ic,
    }


def builder(claim: dict) -> dict:
    """Harness entry point: grade the claim at its first pre-registered horizon (42d, the
    drawdown-relevant window). The horizon set is pre-declared in engine/intl_claims; the
    harness declares BOTH (21,42) in the trial budget — this builder reports the 42d cut."""
    return build(claim, horizon=42)
