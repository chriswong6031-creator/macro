#!/usr/bin/env python3
"""W5 preregistered descriptive method evaluation + threshold calibration harness.

Runs the FROZEN construction in ``research/flow_observatory/W5_PREREG.md`` (committed
BEFORE this harness was written — the prereg's git blame predates this file) over the
three Flow Observatory lenses: themes (22 curated baskets_china), names (~1,500 A-share
主力 tickers), southbound (the single Connect aggregate). It reports; it does not decide.
No engine constant, threshold, or method is changed by running this — the selection
between M0 (incumbent, #3561) and the M1/M2/M3 challengers is reserved for the Fable
principal against the frozen §5 decision rule (``research/FLOW_OBSERVATORY_V2_MASTERPLAN
_BY_FABLE.md`` §8).

WHY OFF THE RENDER PATH. This replays the full flow_hist / baskets_china / southbound
history under four normalization constructions and a 24-cell threshold grid — orders of
magnitude more compute than one nightly render tick needs. It is never imported by
``engine/`` or any builder; it is a pure-read research script that writes two committed
artifacts (``reports/flow_observatory_w5_methods.md`` human, ``...json`` machine) and
never mutates ``data/``.

DETERMINISM. Every random draw (coverage-drop draws, revision-perturbation draws) comes
from ONE seeded ``numpy.random.Generator`` (see ``SEED`` below, printed in both report
artifacts) — same seed, same output, byte-for-byte on the JSON (asserted in
``tests/test_flow_observatory_methods.py::test_harness_is_deterministic``).

CANDIDATE DEFINITIONS (frozen, W5_PREREG.md §2). All four candidates share ONE causal
demeaning step (the ``demean`` window already in ``engine.flow_velocity``'s horizon
configs — 126d themes/names, 252d southbound): the raw per-entity flow series minus its
own causal trailing mean. Call that shared series ``x_t``. Then:
  M0  slope_z(x, w, base) — sqrt(w)*mean(x,w)/std(x,base), floored at 0.25x the series'
      own causal expanding std. THE INCUMBENT (#3561) — reproduced here via the exact
      same primitive ``engine.flow_velocity._vel_series`` uses, DataFrame-vectorized.
  M1  M0 but ``x`` is first winsorized at its own causal rolling 2.5th/97.5th percentile
      (window 126) before the slope_z drift AND vol are computed from it.
  M2  v_t = (x_t - rolling_median_126(x)) / floor(1.4826*rolling_MAD_126(x), 0.25*
      expanding_std(x)) — a location-scale swap (median/MAD replacing mean/std), single
      window, no separate multi-horizon breakdown (the frozen formula carries none).
  M3  v_t = norm_ppf(rolling_percentile_rank_126(x_t)) — a rank-based normal-scores
      transform, single window. See the M3 NOTE below for why this deviates from the
      prereg's literal string.

INTERPRETIVE NOTES ON THE FROZEN TEXT (reported as DEVIATIONS, not silently resolved):
  M3  W5_PREREG.md §2 literally reads "v_t = 2x(rolling_percentile_rank_126(x_t) - 0.5)
      mapped ... via the normal quantile function (probit)". Applying norm.ppf (domain
      (0,1)) to 2*(rank-0.5) (range (-1,1)) is mathematically undefined whenever
      rank < 0.5 — i.e. for roughly half of all sessions by construction. That cannot be
      the intended construction (it would make M3 degenerate on exactly the outlier-vs-
      quiet-series axis metric 4/5 exist to test). Implemented as v_t = norm_ppf(rank)
      directly — the standard rank-based normal-scores transform, always defined, and
      the ONLY reading under which "mapped to a sigma-like scale via probit" parses as a
      complete sentence. The "2x(...-0.5)" clause is treated as a redundant/loose gloss
      of probit's own centering (norm_ppf(0.5) == 0) and antisymmetry, not a separate
      pre-transform. Flagging for principal confirmation.
  M3 floor  "floored identically" (§2) has no literal referent for M3: unlike M0/M1/M2,
      M3 has no vol/scale denominator to floor (a rank is already bounded in (0,1)
      before the probit map). Interpreted as inapplicable — no floor operation is
      applied to M3.
  M2 floor  "the same 0.25x expanding floor applied to the MAD scale" is implemented by
      reusing the IDENTICAL expanding-std reference series M0 already computes (rather
      than a separately-computed expanding MAD, which for a roughly-normal series
      converges to the same quantity via 1.4826*MAD ~ std, at a fraction of the compute
      cost) — i.e. floor(1.4826*rolling_MAD_126(x), 0.25*expanding_std(x)), the same
      construction M0 uses, applied to the MAD-based scale term.
  Sec 4 "winning method"  the frozen sweep procedure names sweeping thresholds "for the
      winning method (and M0 if it wins)" — but selecting a winner is explicitly reserved
      to the principal (§5: "the harness reports, it does not decide"). Rather than
      pre-select a method (which would itself be a selection act), the sweep grid is run
      for ALL FOUR candidates on every lens, a strict superset of "the winning method"
      whichever way §5 is later adjudicated. This is a MORE-not-less resolution: it
      cannot bias the outcome toward any one candidate.
  Sec 4 lens generalization  the frozen breadth-tilt sweep (tau x beta) is written for
      the sector-breadth gauge, which only the THEMES lens has a native "how many
      sectors are in/out" reading for. Generalized as: themes lens sweeps (tau, beta)
      jointly over the 22-theme breadth-tilt state; names lens sweeps (tau, beta) jointly
      over an analogous names-in/names-out breadth-tilt state (same tilt formula, ~1,500
      names as the population); southbound (a single series, no cross-sectional breadth
      is possible with n=1) sweeps tau ONLY against its own entity-level state series
      (beta reported as not applicable). This is stated in the report, not silently
      applied.

Usage:
    python3 scripts/research_flow_observatory_methods.py [--seed N] [--top-names N]
"""
from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import flow_velocity as fv  # noqa: E402
from engine.baskets_china import _membership as _china_membership  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("research_flow_observatory_methods")

SEED = 20260903          # frozen for this run; --seed overrides, both are printed
REPORT_JSON = Path("reports/flow_observatory_w5_methods.json")
REPORT_MD = Path("reports/flow_observatory_w5_methods.md")

CANDIDATES = ("M0", "M1", "M2", "M3")
CANDIDATE_LABEL = {
    "M0": "incumbent slope_z (#3561)",
    "M1": "winsorized slope_z",
    "M2": "median/MAD location-scale",
    "M3": "causal percentile -> probit",
}
VIN, VOUT = 0.5, -0.5     # production's own cutoffs, used for the FIXED-threshold metrics
HELD_OUT_SESSIONS = 60
TAU_GRID = (0.3, 0.4, 0.5, 0.6, 0.75, 1.0)
BETA_GRID = (15, 20, 25, 30)
COVERAGE_DRAWS = 100
COVERAGE_DROP_FRAC = 0.20
REVISION_DRAWS = 40
REVISION_FALLBACK_PCT = 0.10   # ledger has <5 real revisions -> ±10% of series std (frozen fallback)
REVISION_MAX_NAMES = 250       # seeded subsample cap for metric 7 on the ~1,500-name lens (perf)


# ── standard-normal inverse CDF without a scipy dependency ────────────────────────────
# Acklam's rational approximation (max abs error ~1.15e-9). Kept local rather than
# importing scipy.stats.norm.ppf because the CI lane this harness's test is wired into
# (`express-render-guards` in .github/ci/legacy-jobs.yml) does not install scipy, and
# widening that lane's pip line is out of this packet's scope.
def norm_ppf(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    out = np.full(p.shape, np.nan)
    valid = np.isfinite(p) & (p > 0) & (p < 1)
    if not valid.any():
        return out
    pv = p[valid]
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low, p_high = 0.02425, 1 - 0.02425
    result = np.empty_like(pv)
    low, high = pv < p_low, pv > p_high
    mid = ~low & ~high
    if low.any():
        q = np.sqrt(-2 * np.log(pv[low]))
        result[low] = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                      ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if high.any():
        q = np.sqrt(-2 * np.log(1 - pv[high]))
        result[high] = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                       ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if mid.any():
        q = pv[mid] - 0.5
        r = q * q
        result[mid] = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
                      (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    out[valid] = result
    return out


# ── shared causal primitives (DataFrame-vectorized re-implementations of the SAME math
#    engine.flow_velocity._vel_series uses, so M0 here == production M0 exactly) ──────
def causal_demean(df: pd.DataFrame, dm: int) -> pd.DataFrame:
    n = len(df)
    dm_eff = min(dm, max(30, n // 2))
    roll_mean = df.rolling(dm_eff, min_periods=max(20, dm_eff // 2)).mean()
    return df - roll_mean


def _floor_to_ref(vol: pd.DataFrame, ref: pd.DataFrame, floor_frac: float) -> pd.DataFrame:
    """Elementwise ``a if (isna(b) or a>=b) else b`` — the exact combine() flow_velocity
    uses, generalized to full DataFrames (production's version is Series-only)."""
    if not floor_frac:
        return vol
    floor = ref * floor_frac
    mask = floor.notna() & (vol.isna() | (vol < floor))
    return vol.mask(mask, floor)


def vel_series_wide(x: pd.DataFrame, w: int, base: int, floor_frac: float) -> pd.DataFrame:
    drift = x.rolling(w, min_periods=w).mean()
    vol = x.rolling(base, min_periods=max(2, base // 2)).std()
    if floor_frac:
        ref = x.expanding(min_periods=max(8, base // 2)).std()
        vol = _floor_to_ref(vol, ref, floor_frac)
    return drift / (vol.replace(0, np.nan) / np.sqrt(w))


def rolling_slope_wide(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """indicators.rolling_slope, DataFrame-vectorized (same OLS-slope-vs-time formula)."""
    t = np.arange(window, dtype=float)
    t_mean = t.mean()
    t_var = ((t - t_mean) ** 2).sum()
    vals = df.to_numpy(dtype=float)
    n, k = vals.shape
    out = np.full((n, k), np.nan)
    for i in range(window - 1, n):
        y = vals[i - window + 1:i + 1, :]
        valid_cols = ~np.isnan(y).any(axis=0)
        if not valid_cols.any():
            continue
        ym = y[:, valid_cols].mean(axis=0)
        num = ((t - t_mean)[:, None] * (y[:, valid_cols] - ym)).sum(axis=0)
        out[i, valid_cols] = num / t_var
    return pd.DataFrame(out, index=df.index, columns=df.columns)


def rolling_median_mad_rank(df: pd.DataFrame, window: int, min_periods: int):
    """One pass -> (rolling median, rolling 1.4826*MAD, rolling percentile rank of the
    LAST value in each window). Custom loop (pandas has no rolling MAD) but vectorized
    ACROSS ENTITIES per row-step, not per-entity-per-step, which is what keeps this
    tractable at ~1,500 columns (measured wall time is in the report's Evidence run)."""
    vals = df.to_numpy(dtype=float)
    n, k = vals.shape
    med = np.full((n, k), np.nan)
    mad = np.full((n, k), np.nan)
    rank = np.full((n, k), np.nan)
    for i in range(n):
        lo = max(0, i + 1 - window)
        w = vals[lo:i + 1, :]
        if (i + 1 - lo) < min_periods:
            continue
        m = np.nanmedian(w, axis=0)
        med[i, :] = m
        mad[i, :] = np.nanmedian(np.abs(w - m), axis=0) * 1.4826
        cur = vals[i, :]
        valid_n = (~np.isnan(w)).sum(axis=0)
        le = np.nansum(w <= cur, axis=0)
        with np.errstate(invalid="ignore"):
            rank[i, :] = np.where(valid_n > 0, le / np.where(valid_n > 0, valid_n, 1), np.nan)
    idx, cols = df.index, df.columns
    return (pd.DataFrame(med, index=idx, columns=cols),
            pd.DataFrame(mad, index=idx, columns=cols),
            pd.DataFrame(rank, index=idx, columns=cols))


def rolling_quantile_wide(df: pd.DataFrame, window: int, q: float, min_periods: int) -> pd.DataFrame:
    return df.rolling(window, min_periods=min_periods).quantile(q)


def winsorize_causal_wide(x: pd.DataFrame, window: int = 126, lo_q: float = 0.025,
                          hi_q: float = 0.975, min_periods: int | None = None) -> pd.DataFrame:
    """M1's causal winsorization primitive (W5_PREREG.md §2): clip each session's value to
    the [lo_q, hi_q] percentile of its OWN trailing `window`-session history (a window that
    includes the current session, so this stays causal/PIT). During warm-up (bounds not yet
    defined), the value passes through unclipped rather than being dropped."""
    mp = min_periods if min_periods is not None else max(20, window // 2)
    lo = rolling_quantile_wide(x, window, lo_q, mp)
    hi = rolling_quantile_wide(x, window, hi_q, mp)
    wins = x.clip(lower=lo, upper=hi)
    return wins.where(lo.notna() & hi.notna(), x)


# ── candidate v_t construction (all consume the SAME demeaned x, W5_PREREG.md §2) ─────
def build_candidates(raw: pd.DataFrame, cfg: dict) -> dict[str, dict]:
    """raw: [date x entity] wide flow panel. Returns {candidate: {"vel": df, "accel": df}}."""
    dm = cfg["demean"]
    w = cfg["horizons"][cfg["primary"]]
    base = cfg["base"]
    floor_frac = cfg.get("vol_floor") or 0.0
    accel_w = cfg["accel_w"]
    x = causal_demean(raw, dm)

    out: dict[str, dict] = {}

    # M0 — incumbent
    v0 = vel_series_wide(x, w, base, floor_frac)
    out["M0"] = {"vel": v0}

    # M1 — winsorized before slope_z
    wins = winsorize_causal_wide(x, 126, 0.025, 0.975)
    v1 = vel_series_wide(wins, w, base, floor_frac)
    out["M1"] = {"vel": v1}

    # M2 (median/MAD) and M3 (percentile->probit) share ONE pass over the same rolling
    # median/MAD/rank primitive (both are single-window, no horizon breakdown per §2).
    mp = max(20, 126 // 2)
    med, mad, rank = rolling_median_mad_rank(x, 126, mp)

    # M2 — median/MAD location-scale
    ref = x.expanding(min_periods=max(8, base // 2)).std()
    scale = _floor_to_ref(mad, ref, floor_frac) if floor_frac else mad
    v2 = (x - med) / scale.replace(0, np.nan)
    out["M2"] = {"vel": v2}

    # M3 — causal percentile -> probit (no floor — see module docstring "M3 floor" note)
    v3 = pd.DataFrame(norm_ppf(rank.to_numpy()), index=rank.index, columns=rank.columns)
    out["M3"] = {"vel": v3}

    for c in CANDIDATES:
        out[c]["accel"] = rolling_slope_wide(out[c]["vel"], accel_w)
    return out


def classify_wide(vel: pd.DataFrame, accel: pd.DataFrame, vin: float = VIN, vout: float = VOUT) -> pd.DataFrame:
    """Same 5-state taxonomy as engine.flow_velocity._classify, vectorized."""
    a = accel.fillna(0.0)
    state = pd.DataFrame("no data", index=vel.index, columns=vel.columns)
    known = vel.notna()
    above = known & (vel >= vin)
    below = known & (vel <= vout)
    mid = known & ~above & ~below
    state = state.mask(above & (a > 0), "above norm, rising")
    state = state.mask(above & ~(a > 0), "above norm, cooling")
    state = state.mask(below & (a < 0), "below norm, worsening")
    state = state.mask(below & ~(a < 0), "below norm, easing")
    state = state.mask(mid, "near its norm")
    return state


STATE_NAMES = ("above norm, rising", "above norm, cooling", "near its norm",
               "below norm, worsening", "below norm, easing")


# ── metric 1: state distribution ───────────────────────────────────────────────────
def metric_state_distribution(state: pd.DataFrame) -> dict:
    flat = state.to_numpy().ravel()
    flat = flat[flat != "no data"]
    n = len(flat)
    if n == 0:
        return {"n": 0, "shares": {}, "degeneracy_alarm": True}
    shares = {s: float((flat == s).sum()) / n for s in STATE_NAMES}
    alarm = any(v > 0.80 for v in shares.values()) or any(v == 0.0 for v in shares.values())
    return {"n": n, "shares": {k: round(v, 4) for k, v in shares.items()}, "degeneracy_alarm": bool(alarm)}


# ── metric 2: one-day flip rate ────────────────────────────────────────────────────
def metric_flip_rate(state: pd.DataFrame) -> dict:
    valid = state != "no data"
    same_col = valid & valid.shift(1)
    flipped = same_col & (state != state.shift(1))
    pooled = float(flipped.to_numpy().sum()) / max(1, int(same_col.to_numpy().sum()))
    per_entity = []
    for col in state.columns:
        v = same_col[col]
        denom = int(v.sum())
        if denom == 0:
            continue
        per_entity.append(float(flipped[col].sum()) / denom)
    med = float(np.median(per_entity)) if per_entity else None
    return {"pooled": round(pooled, 4), "per_entity_median": round(med, 4) if med is not None else None}


# ── metric 3: persistence (median run-length of non-neutral states) ───────────────
def metric_persistence(state: pd.DataFrame) -> dict:
    runs: list[int] = []
    for col in state.columns:
        s = state[col].to_numpy()
        cur_len = 0
        cur_nonneutral = False
        for v in s:
            if v == "no data":
                if cur_len:
                    runs.append(cur_len)
                cur_len, cur_nonneutral = 0, False
                continue
            nonneutral = v != "near its norm"
            if nonneutral and cur_nonneutral and cur_len:
                cur_len += 1
            elif nonneutral:
                if cur_len:
                    runs.append(cur_len)
                cur_len, cur_nonneutral = 1, True
            else:
                if cur_len:
                    runs.append(cur_len)
                cur_len, cur_nonneutral = 0, False
        if cur_len:
            runs.append(cur_len)
    med = float(np.median(runs)) if runs else None
    return {"median_run_length": med, "n_runs": len(runs)}


# ── metrics 4/5: constructed fixtures (outlier + quiet-series), per lens cfg ──────
def _method_v(x: pd.Series, method: str, cfg: dict) -> pd.Series:
    """Single-entity v_t series for one candidate, direct from a raw (undemeaned) flow
    Series — bypasses the entity-eligibility gate (min_obs) deliberately, because these
    are MATH-PRIMITIVE fixture tests (mirrors tests/test_flow_velocity.py's own style of
    calling the kinetics primitive directly on a hand-built series). Routed through
    ``build_candidates`` itself (a single-column frame) rather than a parallel
    reimplementation, so a fixture result can never silently drift from the real
    per-lens computation."""
    cands = build_candidates(x.to_frame("e"), cfg)
    return cands[method]["vel"]["e"]


def metric_outlier_sensitivity(cfg: dict, seed: int) -> dict:
    """max|delta v_t| from injecting one +/-5sigma spike into an otherwise median flat
    series, per candidate. A fresh seeded RNG per call keeps this independent of draw
    order elsewhere in the harness (determinism test asserts stability)."""
    rng = np.random.default_rng(seed)
    n = 260
    base_vals = rng.normal(0, 1.0, n)
    idx = pd.bdate_range("2024-01-02", periods=n)
    spike_pos = n - 40
    sigma = float(np.std(base_vals))
    out = {}
    for direction, mult in (("pos", 5.0), ("neg", -5.0)):
        spiked = base_vals.copy()
        spiked[spike_pos] += mult * sigma
        s_base = pd.Series(base_vals, index=idx)
        s_spike = pd.Series(spiked, index=idx)
        for m in CANDIDATES:
            v_base = _method_v(s_base, m, cfg)
            v_spike = _method_v(s_spike, m, cfg)
            d = (v_spike - v_base).abs()
            out.setdefault(m, {})[direction] = round(float(d.max()) if d.notna().any() else 0.0, 4)
    return {m: {"max_abs_delta": round(max(out[m]["pos"], out[m]["neg"]), 4), **out[m]} for m in CANDIDATES}


def metric_quiet_series(cfg: dict, seed: int) -> dict:
    """|v_t| on a 60-session near-zero-variance fixture (the frozen "60-session" length
    is the MEASUREMENT window, taken from the TAIL of a longer quiet stretch — see
    below). Warmed up with 240 sessions of ordinary noise so the fixture actually
    exercises the floor mechanism the flow_velocity docstring names ("a name whose flow
    goes quiet gets a collapsing baseline vol and a manufactured extreme") — the SAME
    shape as tests/test_flow_velocity.py's own test_vol_floor_caps_the_quiet_series_
    blowup (loud-then-quiet). A quiet fixture with NO antecedent loud history is not
    actually testable against this alarm at all: since a z-score-style measure is
    scale-invariant, i.i.d. noise (of ANY fixed variance) produces v_t ~ N(0,1)-like
    behavior on its own terms, so |v|>1.5 is ordinary sampling noise there (~13% tail
    probability per draw), not degeneracy.

    The quiet phase runs 240 sessions (not 60) so the measured 60-session TAIL of it is
    clear of every rolling window this harness's candidates use (demean<=126, base<=65,
    horizon<=63) — otherwise a window straddling the loud/quiet boundary reflects the
    loud phase's own LOCAL sampling noise (a short sub-window of zero-mean loud data is
    not itself exactly zero), which tests boundary-transition noise, not the floor."""
    rng = np.random.default_rng(seed)
    n_warm, n_quiet_total, n_measure = 240, 240, 60
    loud = rng.normal(0, 6.0, n_warm)
    quiet = rng.normal(0, 0.05, n_quiet_total)
    vals = np.concatenate([loud, quiet])
    idx = pd.bdate_range("2023-01-02", periods=len(vals))
    s = pd.Series(vals, index=idx)
    out = {}
    for m in CANDIDATES:
        v = _method_v(s, m, cfg).tail(n_measure)
        vmax = float(v.abs().max()) if v.notna().any() else None
        out[m] = {"max_abs_v": round(vmax, 4) if vmax is not None else None,
                  "degenerate_extreme_alarm": bool(vmax is not None and vmax > 1.5)}
    return out


# ── metric 6: coverage sensitivity (themes lens only) ─────────────────────────────
def metric_coverage_sensitivity(theme_members: dict[str, list[str]], names_wide: pd.DataFrame,
                                cfg: dict, seed: int, n_draws: int = COVERAGE_DRAWS) -> dict:
    """20% member-drop sensitivity, themes lens only (frozen: "themes lens, 100 draws").

    Batched into ONE build_candidates call over a wide frame of {theme}__base /
    {theme}__d<i> columns, rather than one call per (theme, draw) pair — measured at
    ~60ms/call from pandas' own per-call setup overhead, batching turns 22*100=2,200
    such calls into a single vectorized pass (see the identical rationale in
    metric_revision_sensitivity)."""
    rng = np.random.default_rng(seed)
    frames: dict[str, pd.Series] = {}
    theme_cols: dict[str, list[str]] = {}
    for bid, members in theme_members.items():
        cols = [t for t in members if t in names_wide.columns]
        if len(cols) < 5:
            continue
        theme_cols[bid] = cols
        frames[f"{bid}__base"] = names_wide[cols].mean(axis=1)
        n_drop = max(1, int(round(len(cols) * COVERAGE_DROP_FRAC)))
        for d in range(n_draws):
            drop = set(rng.choice(cols, size=n_drop, replace=False))
            keep = [c for c in cols if c not in drop]
            if len(keep) < 3:
                continue
            frames[f"{bid}__d{d}"] = names_wide[keep].mean(axis=1)
    if not theme_cols:
        return {"median_abs_delta_by_method": {m: None for m in CANDIDATES},
                "n_themes_evaluated": 0, "by_theme": {}}
    wide = pd.DataFrame(frames)
    cands = build_candidates(wide, cfg)
    last = wide.index[-1]
    per_method: dict[str, list[float]] = {m: [] for m in CANDIDATES}
    per_theme: dict[str, dict[str, list[float]]] = {}
    for bid in theme_cols:
        deltas: dict[str, list[float]] = {m: [] for m in CANDIDATES}
        base_col = f"{bid}__base"
        for m in CANDIDATES:
            vbase = cands[m]["vel"].at[last, base_col]
            if pd.isna(vbase):
                continue
            for d in range(n_draws):
                col = f"{bid}__d{d}"
                if col not in wide.columns:
                    continue
                v = cands[m]["vel"].at[last, col]
                if pd.notna(v):
                    deltas[m].append(abs(float(v - vbase)))
        for m in CANDIDATES:
            if deltas[m]:
                per_method[m].extend(deltas[m])
        per_theme[bid] = {m: (round(float(np.median(deltas[m])), 4) if deltas[m] else None) for m in CANDIDATES}
    out = {m: (round(float(np.median(per_method[m])), 4) if per_method[m] else None) for m in CANDIDATES}
    return {"median_abs_delta_by_method": out, "n_themes_evaluated": len(per_theme), "by_theme": per_theme}


# ── metric 7: revision sensitivity ────────────────────────────────────────────────
def metric_revision_sensitivity(raw: pd.DataFrame, cfg: dict, seed: int,
                                n_draws: int = REVISION_DRAWS, max_entities: int | None = None) -> dict:
    """Perturb the last 3 (panel-calendar) sessions by +/- REVISION_FALLBACK_PCT*std (the
    frozen fallback — the ledger carries fewer than 5 real desk revisions for these
    sources, see the ledger check in the report's methodology section) and measure
    |delta v_t| at the perturbed tail vs baseline, pooled across entities and draws.

    Batched into ONE build_candidates call over a wide frame of {entity}__base /
    {entity}__d<i> columns (see metric_coverage_sensitivity's docstring for why: ~60ms
    of pandas per-call setup overhead makes one call per (entity, draw) pair cost
    minutes at the names lens' ~1,500-entity scale). `max_entities` seeded-subsamples
    the entity pool when it is large — the pooled median over several hundred
    entities x draws is already a stable estimate without paying for every entity."""
    rng = np.random.default_rng(seed)
    cols = [c for c in raw.columns if raw[c].notna().sum() >= cfg["min_obs"]
            and np.isfinite(raw[c].std()) and raw[c].std() != 0]
    if max_entities is not None and len(cols) > max_entities:
        cols = list(rng.choice(cols, size=max_entities, replace=False))
    if not cols:
        return {m: None for m in CANDIDATES}
    tail_idx = raw.index[-3:]
    frames: dict[str, pd.Series] = {}
    for c in cols:
        std = float(raw[c].std())
        frames[f"{c}__base"] = raw[c]
        for d in range(n_draws):
            pert = raw[c].copy()
            shock = rng.normal(0, REVISION_FALLBACK_PCT * std, size=3)
            pert.loc[tail_idx] = pert.loc[tail_idx].to_numpy() + shock
            frames[f"{c}__d{d}"] = pert
    wide = pd.DataFrame(frames)
    cands = build_candidates(wide, cfg)
    per_method: dict[str, list[float]] = {m: [] for m in CANDIDATES}
    for c in cols:
        for m in CANDIDATES:
            vbase = cands[m]["vel"][f"{c}__base"].reindex(tail_idx)
            for d in range(n_draws):
                vpert = cands[m]["vel"][f"{c}__d{d}"].reindex(tail_idx)
                diff = (vpert - vbase).abs()
                per_method[m].extend([float(x) for x in diff if pd.notna(x)])
    return {m: (round(float(np.median(per_method[m])), 4) if per_method[m] else None) for m in CANDIDATES}


# ── metric 8: concordance (theme orderings vs M0) ─────────────────────────────────
def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 3:
        return None
    ra = pd.Series(a[mask]).rank()
    rb = pd.Series(b[mask]).rank()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def metric_concordance(vel_by_method: dict[str, pd.DataFrame]) -> dict:
    v0 = vel_by_method["M0"]
    out = {}
    for m in CANDIDATES:
        if m == "M0":
            out[m] = 1.0
            continue
        vm = vel_by_method[m]
        latest = _spearman(v0.iloc[-1].to_numpy(dtype=float), vm.iloc[-1].to_numpy(dtype=float))
        pooled_vals = []
        common_idx = v0.index.intersection(vm.index)
        for d in common_idx:
            r = _spearman(v0.loc[d].to_numpy(dtype=float), vm.loc[d].to_numpy(dtype=float))
            if r is not None:
                pooled_vals.append(r)
        pooled = float(np.median(pooled_vals)) if pooled_vals else None
        out[m] = {"latest_session": round(latest, 4) if latest is not None else None,
                  "pooled_median": round(pooled, 4) if pooled is not None else None}
    return out


# ── §4 threshold sweep ─────────────────────────────────────────────────────────────
def _tilt_state(n_in: pd.Series, n_out: pd.Series, n_tot: pd.Series, beta: float) -> pd.Series:
    tilt = 100.0 * (n_in - n_out) / n_tot.replace(0, np.nan)
    state = pd.Series("mixed", index=tilt.index)
    state[tilt >= beta] = "broad_in"
    state[tilt <= -beta] = "broad_out"
    state[tilt.isna()] = "no data"
    return state


def _lexicographic_score(neutral_share: float, flip_rate: float, in_reach: float, out_reach: float) -> tuple:
    """Lower tuple sorts first. §4: (1) neutral share in [0.25,0.60] preferred — distance
    to that band is the primary key; (2) minimize flip rate; (3) hard constraint (both
    non-neutral verdicts >=5%) enforced by pushing violators to +inf on the primary key."""
    band_ok = 0.25 <= neutral_share <= 0.60
    reach_ok = in_reach >= 0.05 and out_reach >= 0.05
    if not reach_ok:
        return (float("inf"), flip_rate)
    band_penalty = 0.0 if band_ok else min(abs(neutral_share - 0.25), abs(neutral_share - 0.60))
    return (band_penalty, flip_rate)


def threshold_sweep_cross_sectional(vel: pd.DataFrame, held_out: int) -> dict:
    """Themes/names lens: sweep (tau, beta) jointly over the breadth-tilt state built
    from the ENTITY population's own in/out counts at threshold tau. Returns the full
    grid plus the winner-by-objective, split main-window vs held-out tail (§5)."""
    main = vel.iloc[:-held_out] if held_out and len(vel) > held_out else vel
    tail = vel.iloc[-held_out:] if held_out and len(vel) > held_out else vel.iloc[0:0]
    grid = []
    for tau in TAU_GRID:
        n_in = (vel >= tau).sum(axis=1)
        n_out = (vel <= -tau).sum(axis=1)
        n_tot = vel.notna().sum(axis=1)
        for beta in BETA_GRID:
            state = _tilt_state(n_in, n_out, n_tot, beta)

            def _stats(st: pd.Series) -> dict:
                st = st[st != "no data"]
                n = len(st)
                if n == 0:
                    return {"neutral_share": None, "flip_rate": None, "in_reach": 0.0, "out_reach": 0.0}
                neutral_share = float((st == "mixed").sum()) / n
                flips = int((st != st.shift(1)).iloc[1:].sum())
                flip_rate = flips / max(1, n - 1)
                in_reach = float((st == "broad_in").sum()) / n
                out_reach = float((st == "broad_out").sum()) / n
                return {"neutral_share": round(neutral_share, 4), "flip_rate": round(flip_rate, 4),
                        "in_reach": round(in_reach, 4), "out_reach": round(out_reach, 4)}

            main_stats = _stats(state.loc[main.index])
            tail_stats = _stats(state.loc[tail.index]) if len(tail) else None
            grid.append({"tau": tau, "beta": beta, "main": main_stats, "held_out": tail_stats})
    scored = [g for g in grid if g["main"]["neutral_share"] is not None]
    winner = None
    if scored:
        winner = min(scored, key=lambda g: _lexicographic_score(
            g["main"]["neutral_share"], g["main"]["flip_rate"], g["main"]["in_reach"], g["main"]["out_reach"]))
    incumbent = next((g for g in grid if g["tau"] == 0.5 and g["beta"] == 25), None)
    return {"grid": grid, "winner": winner, "incumbent": incumbent, "n_held_out": len(tail)}


def threshold_sweep_single_entity(vel: pd.Series, held_out: int) -> dict:
    """Southbound lens: n=1, no cross-sectional breadth is possible, so only tau is
    swept against the entity's OWN state series (near-norm/inflow/outflow at +-tau).
    beta is reported as not applicable — see the module docstring's lens-generalization
    note."""
    main = vel.iloc[:-held_out] if held_out and len(vel) > held_out else vel
    tail = vel.iloc[-held_out:] if held_out and len(vel) > held_out else vel.iloc[0:0]
    grid = []
    for tau in TAU_GRID:
        state = pd.Series("mixed", index=vel.index)
        state[vel >= tau] = "broad_in"
        state[vel <= -tau] = "broad_out"
        state[vel.isna()] = "no data"

        def _stats(st: pd.Series) -> dict:
            st = st[st != "no data"]
            n = len(st)
            if n == 0:
                return {"neutral_share": None, "flip_rate": None, "in_reach": 0.0, "out_reach": 0.0}
            neutral_share = float((st == "mixed").sum()) / n
            flips = int((st != st.shift(1)).iloc[1:].sum())
            flip_rate = flips / max(1, n - 1)
            in_reach = float((st == "broad_in").sum()) / n
            out_reach = float((st == "broad_out").sum()) / n
            return {"neutral_share": round(neutral_share, 4), "flip_rate": round(flip_rate, 4),
                    "in_reach": round(in_reach, 4), "out_reach": round(out_reach, 4)}

        main_stats = _stats(state.loc[main.index])
        tail_stats = _stats(state.loc[tail.index]) if len(tail) else None
        grid.append({"tau": tau, "beta": None, "main": main_stats, "held_out": tail_stats})
    scored = [g for g in grid if g["main"]["neutral_share"] is not None]
    winner = None
    if scored:
        winner = min(scored, key=lambda g: _lexicographic_score(
            g["main"]["neutral_share"], g["main"]["flip_rate"], g["main"]["in_reach"], g["main"]["out_reach"]))
    incumbent = next((g for g in grid if g["tau"] == 0.5), None)
    return {"grid": grid, "winner": winner, "incumbent": incumbent, "n_held_out": len(tail)}


# ── §5 decision-rule condition table (facts only — no selection prose) ────────────
def decision_conditions(metrics: dict) -> dict:
    """Per challenger (M1/M2/M3), per lens: which of the four §5 conditions it satisfies
    against M0. Facts only; the harness names pass/fail, never a recommendation."""
    out: dict[str, dict] = {}
    for lens in ("themes", "names", "southbound"):
        lm = metrics[lens]
        m0_out = lm["metric4_outlier"]["M0"]["max_abs_delta"]
        m0_quiet = lm["metric5_quiet"]["M0"]["max_abs_v"]
        m0_flip = lm["metric2_flip"]["M0"]["pooled"]
        for c in ("M1", "M2", "M3"):
            out_sens = lm["metric4_outlier"][c]["max_abs_delta"]
            quiet = lm["metric5_quiet"][c]["max_abs_v"]
            flip = lm["metric2_flip"][c]["pooled"]
            conc = lm["metric8_concordance"][c]
            conc_val = conc["pooled_median"] if isinstance(conc, dict) else conc
            cond_a_outlier = (out_sens is not None and m0_out is not None and m0_out > 0
                              and out_sens <= m0_out * 0.70)
            cond_a_quiet = (quiet is not None and m0_quiet is not None and m0_quiet > 0
                            and quiet <= m0_quiet * 0.70)
            cond_a = bool(cond_a_outlier or cond_a_quiet)
            cond_b = bool(flip is not None and m0_flip is not None
                          and flip <= m0_flip * 1.10)
            # metric 8 (concordance) is frozen as "theme orderings" (W5_PREREG.md §3.8) —
            # a rank correlation needs >=3 entities, so it is structurally UNDEFINED for
            # the southbound lens (n_entities==1). Condition (c) is reported as None
            # (not applicable) there rather than a false negative that would silently
            # veto every southbound challenger regardless of its actual behavior; a
            # None condition does not block all_conditions_met, only a concrete False
            # does — see the "Sec 4 lens generalization" deviation note.
            conc_applicable = lm["n_entities"] >= 3
            cond_c = (bool(conc_val is not None and conc_val >= 0.8) if conc_applicable else None)
            cond_d = bool(not lm["metric1_state"][c]["degeneracy_alarm"])
            adopt = cond_a and cond_b and cond_d and (cond_c is not False)
            out.setdefault(lens, {})[c] = {
                "a_improves_outlier_or_quiet_by_30pct": cond_a,
                "a_outlier_ratio_vs_m0": round(out_sens / m0_out, 4) if (out_sens is not None and m0_out) else None,
                "a_quiet_ratio_vs_m0": round(quiet / m0_quiet, 4) if (quiet is not None and m0_quiet) else None,
                "b_flip_rate_not_worse_than_10pct": cond_b,
                "b_flip_ratio_vs_m0": round(flip / m0_flip, 4) if (flip is not None and m0_flip) else None,
                "c_concordance_ge_0_8": cond_c,
                "c_concordance_value": conc_val,
                "c_not_applicable": not conc_applicable,
                "d_no_degeneracy_alarm": cond_d,
                "all_conditions_met": adopt,
            }
    return out


# ── lens assembly ──────────────────────────────────────────────────────────────────
def load_names_wide() -> pd.DataFrame:
    p = config.data_dir() / "tushare" / "flow_hist.parquet"
    fh = pd.read_parquet(p)
    fh["date"] = pd.to_datetime(fh["date"].astype(str))
    return fh.pivot_table(index="date", columns="ticker", values="flow").sort_index()


def load_southbound() -> pd.Series:
    p = config.data_dir() / "china_connect" / "southbound.parquet"
    df = pd.read_parquet(p)
    return df["net"].dropna().sort_index()


def load_theme_members() -> dict[str, list[str]]:
    mem = _china_membership() or {}
    out = {}
    for bid, b in (mem.get("baskets") or {}).items():
        out[bid] = [m["ticker"] for m in b.get("members", [])
                    if isinstance(m, dict) and m.get("ticker") and not m.get("removed")]
    return out


def evaluate_lens(lens: str, raw: pd.DataFrame, cfg: dict, seed: int,
                  extra_for_coverage: dict | None = None) -> dict:
    cands = build_candidates(raw, cfg)
    vel_by_method = {m: cands[m]["vel"] for m in CANDIDATES}
    state_by_method = {m: classify_wide(cands[m]["vel"], cands[m]["accel"]) for m in CANDIDATES}

    m1_state = {m: metric_state_distribution(state_by_method[m]) for m in CANDIDATES}
    m2_flip = {m: metric_flip_rate(state_by_method[m]) for m in CANDIDATES}
    m3_persist = {m: metric_persistence(state_by_method[m]) for m in CANDIDATES}
    m4_outlier = metric_outlier_sensitivity(cfg, seed + 1)
    m5_quiet = metric_quiet_series(cfg, seed + 2)
    # names lens seeded-subsamples its ~1,500-entity pool to REVISION_MAX_NAMES for
    # metric 7 (see metric_revision_sensitivity's docstring) — a pooled median over
    # several hundred names x draws is already stable without paying for every name.
    m7_revision = metric_revision_sensitivity(
        raw, cfg, seed + 3, n_draws=REVISION_DRAWS,
        max_entities=REVISION_MAX_NAMES if lens == "names" else None)
    # metric_concordance always returns {"M0": 1.0, ...} — the theme/names lens gets a
    # genuine cross-sectional rank correlation; southbound (n_entities==1) correctly
    # returns None for M1/M2/M3 (rank correlation needs >=3 entities, _spearman's own
    # guard), which the report/decision table treat as "not computable", not zero.
    m8_conc = metric_concordance(vel_by_method)

    result = {
        "n_entities": int(raw.shape[1]),
        "n_sessions": int(raw.shape[0]),
        "metric1_state": m1_state,
        "metric2_flip": m2_flip,
        "metric3_persistence": m3_persist,
        "metric4_outlier": m4_outlier,
        "metric5_quiet": m5_quiet,
        "metric7_revision": m7_revision,
        "metric8_concordance": m8_conc,
    }

    if lens == "themes" and extra_for_coverage is not None:
        result["metric6_coverage"] = metric_coverage_sensitivity(
            extra_for_coverage["theme_members"], extra_for_coverage["names_wide"], cfg, seed + 4)

    if lens == "southbound":
        # build_candidates always returns a DataFrame (even for a 1-column input);
        # threshold_sweep_single_entity wants the bare Series.
        vel_series_by_method = {m: vel_by_method[m].iloc[:, 0] for m in CANDIDATES}
        result["threshold_sweep"] = threshold_sweep_single_entity(vel_series_by_method["M0"], HELD_OUT_SESSIONS)
        result["threshold_sweep_all"] = {
            m: threshold_sweep_single_entity(vel_series_by_method[m], HELD_OUT_SESSIONS) for m in CANDIDATES}
    else:
        result["threshold_sweep"] = threshold_sweep_cross_sectional(vel_by_method["M0"], HELD_OUT_SESSIONS)
        result["threshold_sweep_all"] = {
            m: threshold_sweep_cross_sectional(vel_by_method[m], HELD_OUT_SESSIONS) for m in CANDIDATES}

    return result


# ── report rendering ───────────────────────────────────────────────────────────────
def render_markdown(payload: dict) -> str:
    lines = []
    lines.append("# Flow Observatory W5 — descriptive method evaluation + threshold calibration")
    lines.append("")
    lines.append(f"`prereg: research/flow_observatory/W5_PREREG.md` · `seed: {payload['seed']}` · "
                 f"`wall_time_s: {payload['wall_time_s']}` · `generated_at: {payload['generated_at']}`")
    lines.append("")
    lines.append("Report only — no method/threshold/engine change was applied by this run. "
                 "Selection is reserved for the Fable principal against the frozen §5 decision rule.")
    lines.append("")
    lines.append("## Candidates")
    for c in CANDIDATES:
        lines.append(f"- **{c}** — {CANDIDATE_LABEL[c]}")
    lines.append("")
    for lens in ("themes", "names", "southbound"):
        lm = payload["metrics"][lens]
        lines.append(f"## Lens: {lens} (n_entities={lm['n_entities']}, n_sessions={lm['n_sessions']})")
        lines.append("")
        lines.append("### Metric 1 — state distribution (share of sessions, pooled)")
        lines.append("| state | " + " | ".join(CANDIDATES) + " |")
        lines.append("|---" * (len(CANDIDATES) + 1) + "|")
        for s in STATE_NAMES:
            row = [f"{lm['metric1_state'][c]['shares'].get(s, 0.0):.3f}" for c in CANDIDATES]
            lines.append(f"| {s} | " + " | ".join(row) + " |")
        lines.append("| degeneracy alarm | " +
                     " | ".join(str(lm["metric1_state"][c]["degeneracy_alarm"]) for c in CANDIDATES) + " |")
        lines.append("")
        lines.append("### Metric 2 — one-day flip rate")
        lines.append("| | " + " | ".join(CANDIDATES) + " |")
        lines.append("|---" * (len(CANDIDATES) + 1) + "|")
        lines.append("| pooled | " + " | ".join(str(lm["metric2_flip"][c]["pooled"]) for c in CANDIDATES) + " |")
        lines.append("| per-entity median | " +
                     " | ".join(str(lm["metric2_flip"][c]["per_entity_median"]) for c in CANDIDATES) + " |")
        lines.append("")
        lines.append("### Metric 3 — persistence (median non-neutral run length, sessions)")
        lines.append("| " + " | ".join(CANDIDATES) + " |")
        lines.append("|---" * len(CANDIDATES) + "|")
        lines.append("| " + " | ".join(str(lm["metric3_persistence"][c]["median_run_length"]) for c in CANDIDATES) + " |")
        lines.append("")
        lines.append("### Metric 4 — outlier sensitivity (max|Δv| on a +/-5σ spike fixture)")
        lines.append("| " + " | ".join(CANDIDATES) + " |")
        lines.append("|---" * len(CANDIDATES) + "|")
        lines.append("| " + " | ".join(str(lm["metric4_outlier"][c]["max_abs_delta"]) for c in CANDIDATES) + " |")
        lines.append("")
        lines.append("### Metric 5 — quiet-series behavior (max|v| on a 60-session near-zero-variance fixture)")
        lines.append("| | " + " | ".join(CANDIDATES) + " |")
        lines.append("|---" * (len(CANDIDATES) + 1) + "|")
        lines.append("| max\\|v\\| | " + " | ".join(str(lm["metric5_quiet"][c]["max_abs_v"]) for c in CANDIDATES) + " |")
        lines.append("| alarm | " +
                     " | ".join(str(lm["metric5_quiet"][c]["degenerate_extreme_alarm"]) for c in CANDIDATES) + " |")
        lines.append("")
        if "metric6_coverage" in lm:
            lines.append("### Metric 6 — coverage sensitivity (themes only; 20% member drop, "
                         f"{COVERAGE_DRAWS} draws, median |Δv|)")
            lines.append("| " + " | ".join(CANDIDATES) + " |")
            lines.append("|---" * len(CANDIDATES) + "|")
            row = [str(lm["metric6_coverage"]["median_abs_delta_by_method"][c]) for c in CANDIDATES]
            lines.append("| " + " | ".join(row) + " |")
            lines.append(f"\n_themes evaluated: {lm['metric6_coverage']['n_themes_evaluated']}_\n")
        lines.append("### Metric 7 — revision sensitivity (median |Δv|, fallback ±10% std, "
                     f"{REVISION_DRAWS} draws)")
        lines.append("| " + " | ".join(CANDIDATES) + " |")
        lines.append("|---" * len(CANDIDATES) + "|")
        lines.append("| " + " | ".join(str(lm["metric7_revision"][c]) for c in CANDIDATES) + " |")
        lines.append("")
        lines.append("### Metric 8 — concordance vs M0 (pooled median Spearman rho)")
        lines.append("| " + " | ".join(CANDIDATES) + " |")
        lines.append("|---" * len(CANDIDATES) + "|")
        row = []
        for c in CANDIDATES:
            v = lm["metric8_concordance"][c]
            row.append("1.0" if v == 1.0 else str(v.get("pooled_median") if isinstance(v, dict) else v))
        lines.append("| " + " | ".join(row) + " |")
        lines.append("")
        sw = lm["threshold_sweep"]
        lines.append("### §4 threshold sweep — M0 grid winner-by-objective")
        if sw["winner"]:
            w = sw["winner"]
            lines.append(f"Winner: tau={w['tau']} beta={w['beta']} — main-window "
                         f"neutral_share={w['main']['neutral_share']} flip_rate={w['main']['flip_rate']} "
                         f"in_reach={w['main']['in_reach']} out_reach={w['main']['out_reach']}")
            if w["held_out"]:
                lines.append(f"Held-out ({sw['n_held_out']} sessions) at the winning (tau,beta): "
                             f"neutral_share={w['held_out']['neutral_share']} "
                             f"flip_rate={w['held_out']['flip_rate']}")
        if sw["incumbent"]:
            i = sw["incumbent"]
            lines.append(f"Incumbent (tau=0.5, beta={i['beta']}): main-window "
                         f"neutral_share={i['main']['neutral_share']} flip_rate={i['main']['flip_rate']}")
        lines.append("")
    lines.append("## §5 decision-rule condition table (facts only — no selection made here)")
    lines.append("")
    for lens in ("themes", "names", "southbound"):
        lines.append(f"### {lens}")
        lines.append("| challenger | (a) outlier/quiet improve >=30% | (b) flip rate not worse >10% | "
                     "(c) concordance >=0.8 | (d) no degeneracy | ALL CONDITIONS MET |")
        lines.append("|---|---|---|---|---|---|")
        for c in ("M1", "M2", "M3"):
            d = payload["decision_conditions"][lens][c]
            lines.append(f"| {c} | {d['a_improves_outlier_or_quiet_by_30pct']} | "
                         f"{d['b_flip_rate_not_worse_than_10pct']} | {d['c_concordance_ge_0_8']} | "
                         f"{d['d_no_degeneracy_alarm']} | {d['all_conditions_met']} |")
        lines.append("")
    lines.append("## Deviations / interpretive notes")
    lines.append("")
    for d in payload["deviations"]:
        lines.append(f"- {d}")
    lines.append("")
    return "\n".join(lines)


DEVIATIONS = [
    "M3's frozen formula ('v_t = 2x(percentile_rank-0.5) mapped via probit') is "
    "mathematically undefined for rank<0.5 if read literally (norm.ppf's domain is "
    "(0,1); 2x(rank-0.5) ranges (-1,1)). Implemented as v_t = norm_ppf(rank) directly "
    "-- the only reading under which the construction is defined for all sessions. "
    "Flagging for principal confirmation before any production use.",
    "M3 has no vol/scale denominator, so 'floored identically' (§2) has no literal "
    "referent there; interpreted as no-op for M3.",
    "M2's '0.25x expanding floor applied to the MAD scale' is implemented by reusing "
    "the SAME expanding-std reference series M0 already computes (rather than a "
    "separately-computed expanding MAD), since 1.4826*MAD approximates std for a "
    "roughly-normal series and this keeps the floor construction identical to M0's own.",
    "Sec 4 says to sweep thresholds 'for the winning method (and M0 if it wins)', but "
    "the harness does not select a winner (reserved to the principal per §5). The full "
    "(tau,beta) grid was computed for ALL FOUR candidates on every lens -- a strict "
    "superset of 'the winning method', so this cannot bias which method the sweep "
    "favors.",
    "Sec 4's breadth-tilt sweep is written for the sector-breadth gauge (themes-native). "
    "Generalized: themes and names lenses each sweep (tau,beta) jointly over their own "
    "cross-sectional breadth-tilt state; southbound (n=1, no cross-section) sweeps tau "
    "only against its own entity state series, with beta reported not applicable.",
    "Metric 7's ledger check found data/flow_observatory/observations.parquet not yet "
    "materialized in this tree and no separate desk-revision-magnitude ledger for "
    "flow_hist/southbound raw inputs, so the frozen fallback applies: perturbation "
    "magnitude = +/-10% of each entity's own series std.",
    "Metric 6 (coverage sensitivity) is themes-lens only per the frozen metric text "
    "('themes lens, 100 draws') -- not computed for names or southbound, where the "
    "concept of dropping 'members' does not apply.",
    "Metric 8 (concordance) is frozen as 'rank correlation of THEME orderings' -- "
    "generalized here to the names lens too (an analogous cross-sectional rank "
    "correlation across ~1,500 names), reported as its own number rather than folded "
    "into a single cross-lens figure. Southbound (n_entities=1) has no cross-section "
    "to rank at all, so concordance -- and therefore Sec 5 condition (c) -- is reported "
    "as not-applicable there rather than a silent False that would veto every "
    "southbound challenger regardless of its actual behavior.",
    f"Metric 7 (revision sensitivity) on the names lens (~1,500 scored tickers) seeded-"
    f"subsamples to {REVISION_MAX_NAMES} entities before drawing perturbations -- a pure "
    "performance measure (running the frozen fallback on every name at full draw count "
    "measured at several minutes; batching the compute, see the metric's own docstring, "
    "brought this down but the entity count is still capped so the harness stays inside "
    "its <10min budget). The pooled median over "
    f"{REVISION_MAX_NAMES}*{REVISION_DRAWS} name/draw pairs is reported as the names-"
    "lens figure; themes (22) and southbound (1) use their full entity pool.",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out-json", type=Path, default=REPORT_JSON)
    ap.add_argument("--out-md", type=Path, default=REPORT_MD)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    t0 = time.time()

    names_wide = load_names_wide()
    kmap = fv._name_kinetics_map(names_wide)
    scored_cols = [c for c in kmap.keys() if c in names_wide.columns]
    names_panel = names_wide[scored_cols]
    log.info("names lens: %d scored tickers of %d total, %d sessions",
             len(scored_cols), names_wide.shape[1], names_wide.shape[0])

    theme_members = load_theme_members()
    theme_cols, theme_series = [], {}
    for bid, members in theme_members.items():
        cols = [t for t in members if t in names_wide.columns]
        if len(cols) < 3:
            continue
        theme_series[bid] = names_wide[cols].mean(axis=1)
    themes_panel = pd.DataFrame(theme_series).sort_index()
    log.info("themes lens: %d of %d baskets usable, %d sessions",
             themes_panel.shape[1], len(theme_members), themes_panel.shape[0])

    sb = load_southbound()
    sb_panel = sb.to_frame("southbound")
    log.info("southbound lens: %d sessions (%s -> %s)", len(sb), sb.index.min().date(), sb.index.max().date())

    metrics = {}
    metrics["themes"] = evaluate_lens("themes", themes_panel, fv.WK, args.seed,
                                      extra_for_coverage={"theme_members": theme_members, "names_wide": names_wide})
    metrics["names"] = evaluate_lens("names", names_panel, fv.WK, args.seed + 1000)
    metrics["southbound"] = evaluate_lens("southbound", sb_panel, fv._AGG, args.seed + 2000)

    dconds = decision_conditions(metrics)

    wall = round(time.time() - t0, 1)
    payload = {
        "program": "macro-flow-observatory-v2-program-20260902-sol-001",
        "wave": "W5",
        "prereg": "research/flow_observatory/W5_PREREG.md",
        "seed": args.seed,
        "wall_time_s": wall,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "candidates": CANDIDATE_LABEL,
        "metrics": metrics,
        "decision_conditions": dconds,
        "deviations": DEVIATIONS,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, default=str, sort_keys=True))
    args.out_md.write_text(render_markdown(payload))

    log.info("wall_time_s=%s seed=%s", wall, args.seed)
    log.info("wrote %s and %s", args.out_json, args.out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
