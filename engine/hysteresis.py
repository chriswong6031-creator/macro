"""Hysteresis for the not-topped veto — the W6 #22 fix for single-bar veto flicker.

THE PROBLEM (audit #22): ``confluence_tiers`` computes the not-topped veto (the AMAT overbought /
rolled-over guard) from ``iloc[last]`` ONLY — a single bar. A one-bar oscillator wiggle on the
provisional resample tail silently drops a genuinely-fresh name (returns a blank tier) and then
re-admits it the next bar, driving the "appear / vanish / reappear" churn. But the veto is
intentional (it kills the AMAT case: 3D stoch k=82/d=86, overbought AND rolled over), so simply
persisting it risks re-admitting genuinely topped names.

THE FIX: N-bar confirmation. The veto only TRIPS (name becomes topped/vetoed) after ``confirm``
consecutive topped bars, and only CLEARS after ``confirm`` consecutive constructive bars — a
Schmitt-trigger / debounce. A single noisy bar can no longer flip the state either way, so:
  * a genuinely-fresh name is not dropped by one wiggle (recall up), and
  * a genuinely topped name (sustained overbought/rolled-over) still trips (precision held),
    because the AMAT case is topped for many consecutive bars, not one.

This module is a pure library on a BOOLEAN not-topped stream (True = constructive, False = topped).
The replay harness measures the single-bar vs hysteretic veto's precision/recall + flicker so the
``confirm`` value is chosen by the replay numbers, not taste. Pure pandas/numpy; never raises.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Default confirmation length: 2 consecutive bars (one native tick of persistence). The replay's
# precision/recall study picks the shipped value; this is the documented starting point.
DEFAULT_CONFIRM = 2


def hysteretic_not_topped(raw: pd.Series | list | np.ndarray,
                          confirm: int = DEFAULT_CONFIRM) -> pd.Series:
    """Debounce a raw single-bar not-topped stream with ``confirm``-bar confirmation.

    ``raw`` is boolean: True = constructive (not topped), False = topped/vetoed. The output holds
    its prior state until ``confirm`` consecutive raw bars agree in the OTHER direction — a symmetric
    Schmitt trigger. State is SEEDED to the first bar's raw value (no look-ahead: at bar 0 there is
    no prior, so we adopt the observation). ``confirm=1`` reproduces the raw single-bar behaviour
    exactly (so a caller can A/B it). Returns a bool Series aligned to ``raw``'s index.

    Leak-free / causal: the state at bar i depends only on bars <= i (a run of `confirm` topped bars
    ENDING at i trips it; it never peeks forward)."""
    s = pd.Series(raw)
    vals = s.to_numpy()
    n = len(vals)
    if n == 0:
        return pd.Series([], dtype=bool, index=s.index)
    k = max(1, int(confirm))
    out = np.empty(n, dtype=bool)
    # seed: the first bar has no history; adopt its raw observation (bool-coerce None -> True,
    # matching the cascade default not_topped=True).
    state = bool(vals[0]) if vals[0] is not None else True
    run_val = state
    run_len = 1
    out[0] = state
    for i in range(1, n):
        obs = bool(vals[i]) if vals[i] is not None else state
        if obs == run_val:
            run_len += 1
        else:
            run_val = obs
            run_len = 1
        # flip state only once `k` consecutive bars agree in the opposite direction
        if obs != state and run_len >= k:
            state = obs
        out[i] = state
    return pd.Series(out, index=s.index)


def flip_rate(stream: pd.Series | list | np.ndarray) -> float:
    """Fraction of adjacent-bar transitions (state changes) — the churn a trader sees. 0..1."""
    vals = [bool(x) for x in pd.Series(stream).tolist() if x is not None]
    if len(vals) < 2:
        return 0.0
    flips = sum(1 for a, b in zip(vals[:-1], vals[1:]) if a != b)
    return flips / (len(vals) - 1)


def flicker_rate(stream: pd.Series | list | np.ndarray) -> float:
    """Fraction of bars that differ from BOTH neighbours (True->False->True single-bar wiggles) —
    the specific pathology hysteresis targets. 0..1 over interior bars."""
    vals = [bool(x) for x in pd.Series(stream).tolist() if x is not None]
    if len(vals) < 3:
        return 0.0
    flick = sum(1 for a, b, c in zip(vals[:-2], vals[1:-1], vals[2:]) if a == c and a != b)
    return flick / (len(vals) - 2)


def veto_precision_recall(raw: pd.Series, *, confirm: int = DEFAULT_CONFIRM,
                          sustained: int = 3) -> dict:
    """Precision/recall of the hysteretic veto vs the single-bar veto, treating a SUSTAINED topped
    run (>= ``sustained`` consecutive raw-topped bars) as the ground-truth "genuinely topped" event
    the AMAT guard exists to catch.

    * recall  = of bars inside a sustained-topped run, the fraction the veto correctly marks topped.
                Hysteresis should keep this ~1 (the AMAT case is a long run).
    * precision = of bars the veto marks topped, the fraction that are inside a sustained run
                (i.e. NOT a one-bar wiggle). Hysteresis should RAISE this (fewer false trips).
    Returns both arms + the flip/flicker rates so the replay can pick ``confirm`` on measured
    numbers. ``raw`` True=constructive; a "topped" bar is raw False / veto False."""
    r = pd.Series([bool(x) if x is not None else True for x in pd.Series(raw).tolist()])
    hyst = hysteretic_not_topped(r, confirm=confirm)
    single = r.copy()
    truth_topped = _sustained_false(r, sustained)  # ground-truth genuinely-topped bars

    def _pr(veto_not_topped: pd.Series) -> dict:
        veto_topped = ~veto_not_topped.to_numpy(dtype=bool)
        tt = truth_topped.to_numpy(dtype=bool)
        tp = int((veto_topped & tt).sum())
        fp = int((veto_topped & ~tt).sum())
        fn = int((~veto_topped & tt).sum())
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        return {"precision": _r(prec), "recall": _r(rec),
                "n_veto_topped": int(veto_topped.sum())}

    return {
        "confirm": confirm, "sustained_truth": sustained,
        "single_bar": {**_pr(single), "flip_rate": _r(flip_rate(single)),
                       "flicker_rate": _r(flicker_rate(single))},
        "hysteretic": {**_pr(hyst), "flip_rate": _r(flip_rate(hyst)),
                       "flicker_rate": _r(flicker_rate(hyst))},
        "n_bars": int(len(r)), "n_truth_topped": int(truth_topped.sum()),
    }


def _sustained_false(raw: pd.Series, run: int) -> pd.Series:
    """True on bars inside a run of >= ``run`` consecutive False (topped) raw bars — the
    ground-truth "genuinely topped" label (a one-bar dip is NOT genuinely topped)."""
    vals = raw.to_numpy(dtype=bool)
    n = len(vals)
    out = np.zeros(n, dtype=bool)
    i = 0
    while i < n:
        if not vals[i]:
            j = i
            while j < n and not vals[j]:
                j += 1
            if (j - i) >= run:
                out[i:j] = True
            i = j
        else:
            i += 1
    return pd.Series(out, index=raw.index)


def _r(x):
    return round(float(x), 4) if x is not None else None
