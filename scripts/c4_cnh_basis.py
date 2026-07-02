"""C4c builder — the CNH offshore-vs-onshore basis vs CSI300/FXI forward drawdowns.

The causal signal ``scripts/intl_phase0`` grades for claim ``c4_cnh_basis``. Tests whether
``cnh_basis_bps`` widening (offshore USD/CNH RICHER than onshore USD/CNY = capital-outflow
stress) leads China (CSI300 → FXI proxy on disk) forward drawdowns at the declared DD
horizons (21, 42d), as a candidate SECOND China RORO leg beside the EXISTING raw usdcnh
leg (engine.china_conditions.roro_frame legs["usdcnh"] = −z(offshore 20d move)).

Basis (offshore CME USD/CNH − onshore PBoC USD/CNY, in bps) is the engine's own
engine.forex_signals.cnh_basis construction. Offshore = yahoo/CNH_F (live daily from
2013-02); onshore = fred/DEXCHUS (CNY per USD, ~2-week publishing lag).

The DECIDING gate (masterplan §5 C4c + W2-C1's finding that CN RORO's own legs already
carry beta-type content): ORTHOGONALITY vs the existing raw usdcnh RORO leg. If the basis
adds no residual forward-DD content beyond the 20d offshore-move leg the RORO already
carries, it is CONTEXT (weight 0) and NOT wired — a second leg that double-counts the same
information hurts. The basis is a FUNDING-STRESS state (offshore-onshore spread), a
different mechanism than a raw offshore move, so it MIGHT be orthogonal — that is the
empirical question this builder answers, not asserts.

Everything CAUSAL: the basis z-score uses trailing windows; the onshore is ffilled (never
forward-peeked); the de-risk position acts next-bar before interacting with next-bar returns.

MEASURED VERDICT (2026-07-02, CNH_F 2013+ / DEXCHUS): the raw basis→FXI-forward-DD link is
WEAK (Spearman −0.06 @21d, −0.005 @42d) and the 2013+ window carries only ~2 independent
China bears (2015 deval, 2018/22 rate) — below the crisis-count floor. See
reports/forex-reer-n1-phase0.md (C4c section) + data/intl_bridge/ledger.json (c4_cnh_basis).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import store

log = logging.getLogger(__name__)

OFF_GROUP, OFF_SERIES = "yahoo", "CNH_F"          # offshore CME USD/CNH futures (close)
ON_GROUP, ON_SERIES = "fred", "DEXCHUS"           # onshore PBoC USD/CNY reference (CNY per USD)
TGT_GROUP, TGT_SERIES = "yahoo", "FXI"            # CSI300 proxy on disk (no CSI300 parquet)
Z_WIN = 252                                        # trailing z lookback (matches china_conditions)
STRESS_Z = 1.0                                     # de-risk band: basis-z above this = outflow stress


def _close(group: str, name: str) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else df.columns[0]
    s = df[col].dropna()
    if not len(s):
        return None
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _z(s: pd.Series, win: int = Z_WIN) -> pd.Series:
    m = s.rolling(win, min_periods=win // 4).mean()
    sd = s.rolling(win, min_periods=win // 4).std()
    return (s - m) / sd.replace(0, np.nan)


def _cnh_basis_bps(idx: pd.Index) -> pd.Series | None:
    """(offshore USD/CNH − onshore USD/CNY)/onshore × 1e4, in bps. + = offshore yuan weaker
    = outflow/depreciation stress (engine.forex_signals.cnh_basis). Onshore ffilled (causal)."""
    off = _close(OFF_GROUP, OFF_SERIES)
    on = _close(ON_GROUP, ON_SERIES)
    if off is None or on is None:
        return None
    on_a = on.reindex(idx.union(on.index)).ffill().reindex(idx)
    off_a = off.reindex(idx)
    return ((off_a - on_a) / on_a * 10000.0).rename("cnh_basis_bps")


def _fwd_maxdd(px: pd.Series, h: int) -> pd.Series:
    a = px.to_numpy()
    out = np.full(len(a), np.nan)
    for i in range(len(a)):
        w = a[i:i + h + 1]
        w = w[~np.isnan(w)]
        if len(w) >= 3:
            out[i] = float((w / np.maximum.accumulate(w) - 1.0).min())
    return pd.Series(out, index=px.index)


def _existing_usdcnh_roro_leg(idx: pd.Index) -> pd.Series:
    """The EXISTING raw usdcnh RORO leg — offshore 20d move, z-scored, SIGN-FLIPPED so a
    WEAKER yuan (higher USDCNH) reads risk-off (engine.china_conditions.roro_frame:
    legs["usdcnh"] = −z(cnh.pct_change(20))). This is the orthogonality basis the new basis
    leg must beat: if the basis carries no residual content beyond this, it double-counts."""
    off = _close(OFF_GROUP, OFF_SERIES)
    if off is None:
        return pd.Series(index=idx, dtype=float)
    return (-_z(off.reindex(idx).pct_change(20, fill_method=None))).reindex(idx)


def build(claim: dict, horizon: int = 42) -> dict:
    """Harness builder contract for c4_cnh_basis at ONE declared DD horizon (default 42d; the
    grid declares both 21 and 42). De-risk strategy: hold FXI, go flat the day after the
    causal basis-z crosses into outflow stress (basis-z > STRESS_Z). The `signal` graded for
    orthogonality is the causal basis-z (widening = de-risk tell); `target_dd` = FXI forward
    maxDD; `basis` = the EXISTING raw usdcnh RORO leg (the deciding orthogonality test)."""
    tgt = _close(TGT_GROUP, TGT_SERIES)
    if tgt is None:
        return {"error": "FXI target unavailable"}
    idx = tgt.index
    basis_bps = _cnh_basis_bps(idx)
    if basis_bps is None:
        return {"error": "CNH basis inputs unavailable"}
    basis_z = _z(basis_bps.ffill(limit=5))
    ret = tgt.pct_change(fill_method=None)

    # de-risk long-flat book: hold FXI, step out when basis-z says outflow stress (causal:
    # acts next-bar). Bench = passive FXI.
    off_gate = (basis_z > STRESS_Z)
    pos = (~off_gate.shift(1).fillna(False)).astype(float)
    strat_ret = (pos * ret).dropna()
    bench_ret = ret.reindex(strat_ret.index)

    target_dd = _fwd_maxdd(tgt, horizon).reindex(idx)
    signal = basis_z.rename("cnh_basis_z")

    # THE deciding orthogonality basis: the existing raw usdcnh RORO leg
    basis = [_existing_usdcnh_roro_leg(idx)]

    # rank-IC of basis-z vs forward maxDD (correct de-risk sign = negative: wider basis →
    # deeper drawdown). split at the midpoint of the (short) 2013+ window.
    j = pd.concat([signal.rename("f"), target_dd.rename("y")], axis=1).dropna()
    ic = float(j["f"].rank().corr(j["y"].rank())) if len(j) > 60 else None
    if len(j) > 120:
        mid = j.index[len(j) // 2]
        i1 = j[j.index < mid]["f"].rank().corr(j[j.index < mid]["y"].rank())
        i2 = j[j.index >= mid]["f"].rank().corr(j[j.index >= mid]["y"].rank())
        split_same = bool(np.isfinite(i1) and np.isfinite(i2) and np.sign(i1) == np.sign(i2))
    else:
        split_same = None

    return {
        "signal": signal, "strat_ret": strat_ret, "bench_ret": bench_ret,
        "target_dd": target_dd, "basis": basis,
        "split_half_same_sign": split_same, "ic": ic,
    }


def builder(claim: dict) -> dict:
    """Harness entry point — grade at 42d (the drawdown-relevant window of the declared
    (21, 42) DD horizons). The horizon set is pre-declared in engine/intl_claims."""
    return build(claim, horizon=42)
