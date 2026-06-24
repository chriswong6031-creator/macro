"""Evidence gate for the Risk Radar — the STRICT bar, committed + reusable.

Re-implements the day-level forward-lift + frequency-matched permutation + era-split
methodology from research/RISK_ENGINE_V2_FINDINGS.md §8, on committed code (no /tmp).
Used by tests/test_risk_radar.py (a leg that stops leading FAILS CI) and by the Opus
self-correction loop (engine/risk_radar_review.py) to re-grade legs after a retune.

A signal column is a CAUSAL 0-1 risk-rising percentile (as produced by
risk_radar.leading_signals). 'elevated' = pctile >= thr. Lift = P(SPY drawdown-onset
within the next `fwd_bd` business days | elevated) / base rate. All leak-free.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import store


def _spy():
    df = store.read("yahoo", "SPY")
    s = df["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def detect_events(spy=None, fwd: int = 63, depth: float = 0.08, min_gap: int = 40) -> list:
    """Drawdown-onset dates: a local peak whose max drawdown over the next `fwd` trading
    days is >= `depth`. De-duplicated to one onset per decline (>= min_gap apart, keep the
    highest peak). Returns a list of pd.Timestamp onsets (forward-looking labels — fine)."""
    spy = _spy() if spy is None else spy
    px = spy.to_numpy()
    n = len(px)
    onsets = []
    for i in range(n - 1):
        window = px[i + 1: i + 1 + fwd]
        if len(window) == 0:
            continue
        if (window.min() / px[i] - 1.0) <= -depth:
            onsets.append(i)
    # de-dup: keep the highest peak within min_gap
    merged = []
    for i in onsets:
        if merged and (i - merged[-1]) < min_gap:
            if px[i] > px[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)
    return [spy.index[i] for i in merged]


def _fwd_label(idx: pd.DatetimeIndex, onsets: list, fwd_bd: int) -> pd.Series:
    on = np.array([o.to_datetime64() for o in onsets])
    out = pd.Series(False, index=idx)
    vals = idx.values
    for k, d in enumerate(vals):
        hi = (pd.Timestamp(d) + pd.tseries.offsets.BDay(fwd_bd)).to_datetime64()
        if np.any((on > d) & (on <= hi)):
            out.iloc[k] = True
    return out


def lift(pct: pd.Series, onsets: list, *, thr: float = 0.90, fwd_bd: int = 15,
         lo=None, hi=None) -> dict:
    """Day-level forward lift of a causal percentile series at threshold `thr`, optionally
    restricted to an era [lo, hi). Returns {lift, fire_rate, n_elev, base, n_days}."""
    pct = pct.dropna()
    if lo is not None:
        pct = pct[pct.index >= pd.Timestamp(lo)]
    if hi is not None:
        pct = pct[pct.index < pd.Timestamp(hi)]
    if len(pct) < 200:
        return {"lift": None, "fire_rate": None, "n_elev": 0, "base": None, "n_days": len(pct)}
    fwd = _fwd_label(pct.index, onsets, fwd_bd)
    base = float(fwd.mean())
    elev = pct >= thr
    n_elev = int(elev.sum())
    if n_elev == 0 or base == 0:
        return {"lift": None, "fire_rate": float(elev.mean()), "n_elev": n_elev,
                "base": base, "n_days": len(pct)}
    p = float(fwd[elev].mean())
    return {"lift": round(p / base, 3), "fire_rate": round(float(elev.mean()), 4),
            "n_elev": n_elev, "base": round(base, 4), "n_days": len(pct)}


def perm_p(pct: pd.Series, onsets: list, *, thr: float = 0.90, fwd_bd: int = 15,
           n: int = 300, seed: int = 0) -> float | None:
    """Frequency-matched permutation p-value: random elevated days at the SAME fire-rate ->
    day-level lift null; p = fraction of random lifts >= the real lift. Low p = real edge."""
    real = lift(pct, onsets, thr=thr, fwd_bd=fwd_bd)
    if real["lift"] is None:
        return None
    pct = pct.dropna()
    fwd = _fwd_label(pct.index, onsets, fwd_bd).to_numpy().astype(float)
    base = fwd.mean()
    if base == 0:
        return None
    k = max(1, real["n_elev"])
    rng = np.random.default_rng(seed)
    null = np.empty(n)
    for j in range(n):
        sel = rng.choice(len(fwd), size=k, replace=False)
        null[j] = fwd[sel].mean() / base
    return float((null >= real["lift"]).mean())


def gate_report(sigs=None, onsets=None, *, thr: float = 0.90) -> dict:
    """Per-leg lift (full + 2020+) for the gate. Returns {leg: {lift, lift_2020, fire_rate, ...}}."""
    from engine.risk_radar import leading_signals
    sigs = leading_signals() if sigs is None else sigs
    onsets = detect_events() if onsets is None else onsets
    out = {}
    for leg in sigs.columns:
        full = lift(sigs[leg], onsets, thr=thr)
        e20 = lift(sigs[leg], onsets, thr=thr, lo="2020-01-01", hi="2027-01-01")
        out[leg] = {"lift": full["lift"], "lift_2020": e20["lift"],
                    "fire_rate": full["fire_rate"], "n_elev_2020": e20["n_elev"]}
    return out
