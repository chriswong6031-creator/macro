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


_ORDER = ["calm", "watch", "caution", "elevated", "risk-off"]


def _band_idx(score: pd.Series, bands: dict) -> pd.Series:
    """Vectorized band index 0..4 (calm..risk-off) for a 0-100 sub-score series."""
    idx = pd.Series(0, index=score.index)
    idx = idx.mask(score >= bands["watch"], 1)
    idx = idx.mask(score >= bands["caution"], 2)
    idx = idx.mask(score >= bands["elevated"], 3)
    idx = idx.mask(score >= bands["risk_off"], 4)
    return idx


def state_series(subs: pd.DataFrame, calib: dict) -> pd.Series:
    """Daily engine STATE (calm..risk-off) under a given calibration — vectorized replica of
    compute()'s tier-aware logic: Tier-A scares originate the state (max band), conjunction
    (>=2 Tier-A >= caution) escalates one band, and Tier-B (vol) escalates a hot Tier-A. Used by
    the do-no-harm gate so a proposed recalibration can be scored over full history."""
    bands = calib["bands"]
    scares = calib["scares"]
    tierA = [s for s, v in scares.items() if v.get("tier") == "A" and s in subs.columns]
    tierB = [s for s, v in scares.items() if v.get("tier") == "B" and s in subs.columns]
    if not tierA:
        return pd.Series("calm", index=subs.index)
    a_idx = pd.concat([_band_idx(subs[s], bands) for s in tierA], axis=1)
    maxA = a_idx.max(axis=1)
    n_hotA = pd.concat([(subs[s] >= bands["caution"]).astype(int) for s in tierA], axis=1).sum(axis=1)
    conj = n_hotA >= 2
    b_hot = (pd.concat([(subs[s] >= bands["caution"]) for s in tierB], axis=1).any(axis=1)
             if tierB else pd.Series(False, index=subs.index))
    esc = (conj | (b_hot & (maxA > 0)))
    st = maxA + (esc & (maxA < 4) & (maxA > 0)).astype(int)
    st = st.clip(0, 4)
    # CONTEXT GATE: cap the loud (elevated+) state at caution where the broad tape isn't breaking
    # (SPY<200dma AND breadth weak). The verified #1 false-positive lever; mirrors compute().
    try:
        from engine.risk_radar import context_gate_series
        gate = context_gate_series(subs.index).reindex(subs.index).fillna(False)
        cap = _ORDER.index("caution")
        st = st.mask((~gate) & (st > cap), cap)
    except Exception:  # noqa: BLE001
        pass
    return st.map(lambda i: _ORDER[int(i)])


def state_accuracy(calib: dict, *, onsets=None, dd: float = 0.05, H: int = 21,
                   alert_from: str = "elevated", lo=None) -> dict:
    """Precision / recall / F1 / fire-rate of the ALERT state (>= alert_from) vs a forward
    >= dd SPY drawdown within H bd, under `calib`. The do-no-harm objective for recalibration."""
    from engine.risk_radar import subscore_series, leading_signals
    subs = subscore_series(leading_signals(), calib)
    if subs is None or subs.empty:
        return {"f1": None}
    spy = _spy().reindex(subs.index).ffill()
    fdd = pd.Series({d: (spy.iloc[i + 1:i + 1 + H].min() / spy.iloc[i] - 1.0)
                     if i + 1 < len(spy) else np.nan
                     for i, d in enumerate(spy.index)})
    label = (fdd <= -dd)
    state = state_series(subs, calib)
    alert = state.map(lambda s: _ORDER.index(s) >= _ORDER.index(alert_from))
    common = alert.index.intersection(label.dropna().index)
    if lo is not None:
        common = common[common >= pd.Timestamp(lo)]
    a = alert.reindex(common).fillna(False); y = label.reindex(common).fillna(False)
    tp = int((a & y).sum()); fp = int((a & ~y).sum()); fn = int((~a & y).sum())
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else 0.0
    return {"precision": None if prec is None else round(prec, 3),
            "recall": None if rec is None else round(rec, 3),
            "f1": round(f1, 3), "fire_rate": round(float(a.mean()), 4),
            "n_alert": int(a.sum()), "n_days": int(len(common))}


def compare_calib(proposed: dict, base: dict | None = None, *, dd: float = 0.05, H: int = 21) -> dict:
    """Do-no-harm gate: is `proposed` calibration at least as good as `base` (full + 2020+ F1),
    without breaking the evidence gate (validated legs still lead)? Returns the verdict + numbers."""
    from engine.risk_radar import _calib
    base = base or _calib()
    onsets = detect_events()
    sigs = None
    out = {}
    for label, c in (("base", base), ("proposed", proposed)):
        out[label] = {"full": state_accuracy(c, onsets=onsets, dd=dd, H=H),
                      "y2020": state_accuracy(c, onsets=onsets, dd=dd, H=H, lo="2020-01-01")}
    # validated legs must still lead under proposed (legs don't depend on bands, but thr_pct does)
    rep = gate_report(thr=0.90)
    legs_ok = all((rep.get(leg, {}).get("lift_2020") or 0) >= 1.0
                  for leg, lc in proposed.get("legs", {}).items()
                  if (lc.get("lift_2020") or 0) >= 1.2)
    bf = out["base"]["full"]["f1"] or 0; pf = out["proposed"]["full"]["f1"] or 0
    b20 = out["base"]["y2020"]["f1"] or 0; p20 = out["proposed"]["y2020"]["f1"] or 0
    improves = (pf >= bf - 1e-9) and (p20 >= b20 - 1e-9) and legs_ok and (pf + p20) > (bf + b20)
    out["legs_ok"] = legs_ok
    out["improves"] = bool(improves)
    return out


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
