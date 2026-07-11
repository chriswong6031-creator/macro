"""engine.neuralweb.half_life — W2 "Measured Half-Lives" (Signal Commons program).

HONESTY HEADER
--------------
This module is DISPLAY-ONLY.  It measures holding-horizon decay curves from
the kernel_estimates.parquet and spine_index.parquet, and writes a per-family
half-life artifact.  Zero behavior-changing consumers may read the output until
a separately gated change proposes it.

BLOCKER RE-SCOPE (from Fable pre-reg review)
--------------------------------------------
B1 — "age-at-fire vs realized excess" is UNBUILDABLE from the current spine
     index (no signal-age column).  W2 is RE-SCOPED to "holding-horizon decay":
     does shrunken_ic peak and then decay as the holding period grows?

B2 — Exponential / power-law half-life is ill-posed when the curve RISES.
     track_record shrunken_ic {5:0.0487, 10:0.0573, 21:0.0717, 63:0.1112,
     126:0.1578} is monotonically INCREASING.  A pre-registered monotone-
     decrease gate is applied first; a rising curve emits half_life=None.

B3 — outcome_excess unit incommensurability: track_record outcome_excess is
     a non-negative magnitude (0% negatives); radar outcome_excess is a signed
     excess (≈45% negatives).  outcome_unit is mandatory in the schema.

B4 — Insufficient horizon points: radar has only h=5 graded rows; us_board
     only h=5,10.  Both are CLASS-B (< 3 admissible horizons → NaN always).

STALENESS HALF-LIFE (decay_kind='staleness')
--------------------------------------------
Measured per family when data/replay/replay_delay.parquet is present
(Mac-local; never in git per EI R9). Coverage stamp (which years/families)
is included in the artifact.

Per-family fitter (staleness path):
  - Input: replay_delay.parquet rows for this family
    (family_key matched against replay_boarded.parquet tier_cascade / via
    a direct lookup where episode_id/signal_date groups map to families).
    Currently the replay fires do not carry a kernel family tag — the fitter
    operates on the FULL fire population (no family split) and is labelled
    "__fires__" family key to be explicit.
  - Measurement: mean fwd_ret_21 (and MAE = mean fwd_mdd_21) by delay_n,
    restricted to horizon_censored=False, survivor_bias=False rows (era law).
  - Monotone-decrease check on mean fwd_ret_21 vs delay_n (same HAC-t–gated
    negative-slope gate as the CLASS-A horizon fitter — numpy only, no scipy).
  - Exponential fit: mirroring the CLASS-A functional form (y = A·exp(-d/τ));
    numpy-only least-squares via log-linear regression (no scipy, matching
    the "reuse validation.py primitives — numpy only" spec requirement).
  - Gate: negative slope significant at HAC/Newey-West t > 1.96.
    HAC-t is computed from OLS residuals on the log-linear form with NW
    standard errors (numpy only, 1-lag Bartlett kernel per spec).
  - Passing families report staleness_half_life in days-late (τ·ln2).
  - Failing families print an HONEST NULL (the W2 pattern).

Coverage stamp: when the artifact is absent (CI runners, no replay_delay.parquet)
the module degrades gracefully to the current "UNMEASURED" declaration — no crash.
The honesty header is updated to reflect which state applies.

ESTIMATOR CLASSES
-----------------
CLASS-A: deep archive, ≥5 horizon points, any outcome_unit.
  Gate: Spearman(horizon, shrunken_ic) over __all__ marginal cells.
  If monotone-DECREASING (rho < 0 AND every step ≤ 0 within CI):
    fit y = A·exp(-h/τ) by WNLS on shrunken_ic; half_life = τ·ln2.
  If flat or rising: half_life = None, reason = "edge_non_decaying" — PLUS the
    measured curve-shape facts (audit fix): trend='non_decaying',
    ic_ratio_long_short = IC(longest h)/IC(shortest h), and fit_direction
    ('rising'/'flat'/'non_monotone' from Spearman rho). A rising curve is a
    useful fact, not a bare null: e.g. track_record shrunken_ic RISES 5d
    0.0487 → 126d 0.1578 (ratio ≈ 3.24x).

CLASS-B: < 3 admissible graded horizons → half_life = None always.

CLASS-C: zero graded outcomes → half_life = None, "unmeasured (no graded outcomes yet)".

N-FLOORS (pre-registered)
--------------------------
- Per-cell floor: WILSON_MIN_N = 12 (n_eff per horizon point to be admissible).
- Curve floor: ≥ 3 admissible horizon points required to attempt a fit.
- Family floor: total graded n_eff ≥ 200.

UNCERTAINTY
-----------
For any family that does pass the gate (currently none): block-bootstrap over
(symbol, as_of) events, 200 resamples, 90th-percentile CI [ci_low, ci_high].
If CI spans a sign change or is unbounded → NaN.

OUTPUT ARTIFACT: data/neuralweb/half_life.json
  {
    "<engine:family_key>": {
      "decay_kind": "horizon"|"staleness"|null,
      "outcome_unit": "signed_excess"|"magnitude",
      "half_life": float|null,
      "ci_low": float|null,
      "ci_high": float|null,
      "ci_basis": "raw_mean_proxy"|null,  # proxy nature explicit; null when CI not computed
      "n_eff": int,
      "n_horizons": int,
      "reason_null": str|null,        # ALWAYS a non-empty string on null entries
      "fit_rho": float|null,
      "trend": "non_decaying"|"decaying"|null,   # curve-shape fact (see below)
      "ic_ratio_long_short": float|null,  # IC(longest h)/IC(shortest h), short IC>0 only
      "fit_direction": "rising"|"flat"|"non_monotone"|"falling"|null
    },
    ...
    "status": "fit_ran"|"fit_failed",   # sentinel key — present in every write
    "produced_at": "YYYY-MM-DDTHH:MM:SSZ",
    # + five sibling envelope keys
  }

CONSERVATIVE DEFAULTS TAKEN
----------------------------
- family_floor N = 200 (flagged)
- curve_floor ≥ 3 horizon points
- per-cell floor = WILSON_MIN_N = 12
- bootstrap 90th-percentile, 200 resamples, event-block
- column named "family_half_life" in the row-stamp docstring to prevent
  future misreading, but written under the COLUMNS key "half_life" (W1 contract)
- monotone-decrease is a HARD pre-registered gate (rising → NaN)

OPEN QUESTIONS (flagged, not acted on)
---------------------------------------
- B1 is the gating decision: W2 is re-scoped to holding-horizon; staleness
  is declared unmeasured and registered as a W0-blocked item.
- track_record outcome_excess is a non-negative magnitude, not signed edge;
  the honest expected outcome of W2 is all-null.
- Row-level stamp: "half_life" matches the W1 slot name; column semantics
  are family-level constants broadcast to rows (a future consumer risk).
  Flagged in notes; a separate gated change would rename if needed.
- Staleness half-life blocked on fill_offset variation (currently uniform=1);
  needs delayed-fill accrual in the replay harness.

USAGE
-----
  from engine.neuralweb.half_life import build_half_lives, write_half_lives
  payload = build_half_lives(root)     # full in-memory build
  write_half_lives(root)               # idempotent write to disk
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.neuralweb.kernel import (
    HORIZONS,
    MARGINAL_BUCKET,
    WILSON_MIN_N,
)

log = logging.getLogger(__name__)

__all__ = [
    "FAMILY_FLOOR_N",
    "CURVE_FLOOR_HORIZONS",
    "BOOTSTRAP_N_RESAMPLES",
    "BOOTSTRAP_CI_PCT",
    "CI_COHERENCE_EPSILON",
    "STALENESS_MIN_N",
    "STALENESS_HAC_LAGS",
    "STALENESS_T_THRESHOLD",
    "build_half_lives",
    "write_half_lives",
    "build_staleness_half_lives",
]

# ---------------------------------------------------------------------------
# Staleness-fitter constants (pre-registered, staleness_delay_v1)
# ---------------------------------------------------------------------------

#: Minimum number of uncensored non-survivor-bias fire rows for staleness fit.
STALENESS_MIN_N: int = 30

#: HAC Newey-West lag count (1 for delay grid of size 5 — Bartlett kernel).
STALENESS_HAC_LAGS: int = 1

#: HAC-t threshold for "significant negative slope" gate (two-tailed 5%).
STALENESS_T_THRESHOLD: float = 1.96

# Canonical data path for replay_delay.parquet (Mac-local; never git, EI R9).
_CANONICAL_ROOT = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
_REPLAY_DELAY_PATH = _CANONICAL_ROOT / "data" / "replay" / "replay_delay.parquet"

# ---------------------------------------------------------------------------
# Pre-registered constants
# ---------------------------------------------------------------------------

#: Minimum total graded n_eff for a family to be eligible for fitting.
FAMILY_FLOOR_N: int = 200  # conservative default; flagged as open question

#: Minimum admissible horizon points to attempt a 2-parameter exp fit.
CURVE_FLOOR_HORIZONS: int = 3

#: Number of bootstrap resamples for CI.
BOOTSTRAP_N_RESAMPLES: int = 200

#: Bootstrap percentile CI (90th = [5%, 95%] symmetric around median).
BOOTSTRAP_CI_PCT: float = 90.0

#: Minimum CI width (trading days) below which the CI is considered degenerate.
#: Triggered when all events share one as_of so the block bootstrap has ~1 unique block.
CI_COHERENCE_EPSILON: float = 0.5

# Per-cell n_eff floor reuses WILSON_MIN_N from kernel.py (= 12).
_CELL_FLOOR_N: int = WILSON_MIN_N

# Families known to have signed-excess outcome_unit vs magnitude.
# track_record outcome_excess is a NON-NEGATIVE magnitude (0% negatives).
# radar outcome_excess is a SIGNED excess (≈45% negatives).
# This mapping is sourced from Fable pre-reg review findings.
_OUTCOME_UNIT_MAP: dict[str, str] = {
    "track_record": "magnitude",  # non-negative favorable-excursion
    "radar": "signed_excess",
    "us_board": "signed_excess",
    "altdata": "signed_excess",
    "altdata_conv": "signed_excess",
    "desk:ai_desk": "signed_excess",
    "policy": "signed_excess",
}
_DEFAULT_OUTCOME_UNIT: str = "signed_excess"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _data_dir(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root) / "data"
    from lib import config  # noqa: PLC0415
    return config.data_dir()


def _load_estimates(root: Path | str | None) -> pd.DataFrame:
    p = _data_dir(root) / "neuralweb" / "kernel_estimates.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("half_life._load_estimates: read failed: %s", e)
        return pd.DataFrame()


def _load_index(root: Path | str | None) -> pd.DataFrame:
    """Load the spine index via query.load_index (fail-open)."""
    try:
        from engine.neuralweb.query import load_index  # noqa: PLC0415
        return load_index(root)
    except Exception as e:  # noqa: BLE001
        log.warning("half_life._load_index: failed: %s", e)
        return pd.DataFrame()


def _outcome_unit_for(engine_key: str) -> str:
    """Return outcome_unit for a family engine key."""
    return _OUTCOME_UNIT_MAP.get(engine_key, _DEFAULT_OUTCOME_UNIT)


def _null_entry(
    engine_key: str,
    reason: str,
    n_eff: int = 0,
    n_horizons: int = 0,
    outcome_unit: str | None = None,
) -> dict[str, Any]:
    """Return a null (unmeasured) entry with all required schema keys.

    reason is coerced to a NON-EMPTY string: an honest null must always say
    why (empty reason strings render as 'unknown' on the committee chip and
    were flagged by the audit critic — never emit them).
    """
    return {
        "decay_kind": None,
        "outcome_unit": outcome_unit or _outcome_unit_for(engine_key),
        "half_life": None,
        "ci_low": None,
        "ci_high": None,
        "ci_basis": None,
        "n_eff": int(n_eff),
        "n_horizons": int(n_horizons),
        "reason_null": str(reason).strip() or "unspecified",
        "fit_rho": None,
        # Curve-shape facts (filled for edge_non_decaying + measured entries;
        # honest None elsewhere — see _estimate_family).
        "trend": None,
        "ic_ratio_long_short": None,
        "fit_direction": None,
    }


def _monotone_decrease_gate(
    horizons: list[int],
    ic_values: list[float],
) -> tuple[bool, float]:
    """Pre-registered monotonicity gate.

    Returns (is_decreasing, spearman_rho).

    Gate PASSES (is_decreasing=True) only when:
      - Spearman rho < 0 (negative correlation with horizon)
      - Every consecutive step is ≤ 0 (strictly non-increasing)

    The gate FAILS for flat or rising curves, returning (False, rho).

    Note: scipy import is deferred so the module loads in environments
    where scipy is absent (fails at fit time, not import time).
    """
    if len(horizons) < 2:  # noqa: PLR2004
        return False, float("nan")

    try:
        from scipy.stats import spearmanr  # noqa: PLC0415
        rho, _ = spearmanr(horizons, ic_values)
    except Exception as e:  # noqa: BLE001
        log.warning("half_life: Spearman failed: %s", e)
        return False, float("nan")

    # Every consecutive step must be ≤ 0
    steps_nonincreasing = all(
        ic_values[i + 1] <= ic_values[i]
        for i in range(len(ic_values) - 1)
    )

    is_decreasing = bool(rho < 0 and steps_nonincreasing)
    return is_decreasing, float(rho)


def _exp_decay(h: float, A: float, tau: float) -> float:
    """y = A * exp(-h / tau)."""
    return A * math.exp(-h / tau)


def _fit_exp_decay(
    horizons: list[int],
    ic_values: list[float],
    weights: list[float],
) -> tuple[float | None, float | None]:
    """Fit y = A * exp(-h / tau) by WNLS.

    Returns (tau, residual_sse) or (None, None) on failure.
    """
    try:
        from scipy.optimize import curve_fit  # noqa: PLC0415
    except ImportError:
        log.warning("half_life: scipy.optimize not available — cannot fit")
        return None, None

    h_arr = np.array(horizons, dtype=float)
    y_arr = np.array(ic_values, dtype=float)
    w_arr = np.array(weights, dtype=float)

    # Guard: weights must be positive; set floor at 1
    w_arr = np.where(w_arr > 0, w_arr, 1.0)
    sigma = 1.0 / w_arr  # WNLS: sigma proportional to inverse weight

    try:
        # p0 guesses: A ≈ max IC, tau ≈ midpoint horizon
        p0 = [float(max(y_arr)), float(np.median(h_arr))]
        popt, _ = curve_fit(
            lambda h, A, tau: A * np.exp(-h / tau),
            h_arr,
            y_arr,
            p0=p0,
            sigma=sigma,
            maxfev=5000,
            bounds=([0, 1e-6], [np.inf, 1e6]),
        )
        tau_fit = float(popt[1])
        if tau_fit <= 0 or not math.isfinite(tau_fit):
            return None, None
        return tau_fit, None
    except Exception as e:  # noqa: BLE001
        log.warning("half_life: curve_fit failed: %s", e)
        return None, None


def _bootstrap_ci(
    graded_df: pd.DataFrame,
    horizon_col: list[int],
    n_resamples: int,
    ci_pct: float,
) -> tuple[float | None, float | None]:
    """Block-bootstrap CI for tau over (symbol, as_of) event blocks.

    Resamples events (symbol, as_of unique pairs), recomputes shrunken_ic
    per horizon (mean proxy since we don't have full kernel per resample),
    refits exp-decay, and returns the [lo, hi] CI percentiles.

    Returns (ci_lo, ci_hi) half-lives (tau * ln2) or (None, None) on failure.

    NOTE: This is a simplified bootstrap that uses mean_ic per horizon as
    a proxy for shrunken_ic, since the full hierarchical shrinkage requires
    the full kernel machinery.  This understates uncertainty slightly vs
    a full resample of the kernel.  Flagged as a known limitation.
    """
    if graded_df.empty or "symbol" not in graded_df.columns or "as_of" not in graded_df.columns:
        return None, None

    # Get unique event keys (symbol, as_of)
    events = list(graded_df.drop_duplicates(subset=["symbol", "as_of"])[["symbol", "as_of"]].itertuples(index=False, name=None))
    n_events = len(events)
    if n_events < CURVE_FLOOR_HORIZONS:
        return None, None

    rng = np.random.default_rng(seed=42)
    tau_samples: list[float] = []

    for _ in range(n_resamples):
        # Resample events with replacement
        idx = rng.integers(0, n_events, size=n_events)
        sampled_events = [events[i] for i in idx]

        # Build a (symbol, as_of) mask
        event_set = set(sampled_events)
        mask = graded_df.apply(
            lambda r: (r["symbol"], r["as_of"]) in event_set, axis=1
        )
        boot_df = graded_df[mask]
        if boot_df.empty:
            continue

        # Compute mean outcome_excess per horizon as proxy
        h_ics: dict[int, list[float]] = {}
        h_ns: dict[int, int] = {}
        for h in horizon_col:
            h_rows = boot_df[boot_df["horizon"] == h]["outcome_excess"]
            h_vals = pd.to_numeric(h_rows, errors="coerce").dropna()
            n_h = len(h_vals)
            if n_h >= _CELL_FLOOR_N:
                h_ics[h] = [float(h_vals.mean())]
                h_ns[h] = n_h

        if len(h_ics) < CURVE_FLOOR_HORIZONS:
            continue

        # Check monotone decrease (required for fit)
        h_sorted = sorted(h_ics.keys())
        ic_sorted = [h_ics[h][0] for h in h_sorted]
        is_dec, _ = _monotone_decrease_gate(h_sorted, ic_sorted)
        if not is_dec:
            continue

        tau, _ = _fit_exp_decay(
            h_sorted,
            ic_sorted,
            [float(h_ns[h]) for h in h_sorted],
        )
        if tau is not None and tau > 0 and math.isfinite(tau):
            tau_samples.append(tau * math.log(2))

    if len(tau_samples) < 10:  # noqa: PLR2004
        return None, None

    lo_pct = (100 - ci_pct) / 2
    hi_pct = 100 - lo_pct
    ci_lo = float(np.percentile(tau_samples, lo_pct))
    ci_hi = float(np.percentile(tau_samples, hi_pct))

    # If CI spans sign change or is unbounded → NaN
    if ci_lo < 0 or ci_hi < 0 or not math.isfinite(ci_lo) or not math.isfinite(ci_hi):
        return None, None

    return ci_lo, ci_hi


# ---------------------------------------------------------------------------
# Per-family half-life estimator
# ---------------------------------------------------------------------------

def _estimate_family(
    engine_key: str,
    marginal_cells: pd.DataFrame,
    graded_df: pd.DataFrame,
) -> dict[str, Any]:
    """Estimate the horizon half-life for a single engine family.

    Parameters
    ----------
    engine_key:      The engine family key (e.g. "track_record").
    marginal_cells:  Rows from kernel_estimates for this engine, regime='__all__'.
    graded_df:       All graded rows from spine_index for this engine.

    Returns
    -------
    A dict matching the per-family schema.
    """
    outcome_unit = _outcome_unit_for(engine_key)

    # CLASS-C: zero graded outcomes
    total_graded = int(len(graded_df))
    if total_graded == 0:
        return _null_entry(
            engine_key,
            reason="unmeasured (no graded outcomes yet)",
            n_eff=0,
            n_horizons=0,
            outcome_unit=outcome_unit,
        )

    # Total n_eff from deduped events
    events_deduped = graded_df.drop_duplicates(subset=["symbol", "as_of"])
    total_n_eff = int(len(events_deduped))

    # Family floor check
    if total_n_eff < FAMILY_FLOOR_N:
        return _null_entry(
            engine_key,
            reason=f"unmeasured (family n_eff={total_n_eff} < floor={FAMILY_FLOOR_N})",
            n_eff=total_n_eff,
            n_horizons=0,
            outcome_unit=outcome_unit,
        )

    # Extract admissible horizon points from marginal cells
    # A horizon point is admissible if: row has a valid shrunken_ic AND
    # the kernel cell's n_eff >= _CELL_FLOOR_N
    admissible: list[tuple[int, float, float]] = []  # (horizon, ic, n_eff)
    for _, row in marginal_cells.iterrows():
        h = row.get("horizon")
        ic = row.get("shrunken_ic")
        n_cell = row.get("n_eff")

        # Type guards
        try:
            h = int(h)
            ic = float(ic)
            n_cell = float(n_cell)
        except (TypeError, ValueError):
            continue

        if not math.isfinite(ic) or not math.isfinite(n_cell):
            continue
        if n_cell < _CELL_FLOOR_N:
            continue
        admissible.append((h, ic, n_cell))

    n_horizons = len(admissible)

    # CLASS-B: < 3 admissible horizon points
    if n_horizons < CURVE_FLOOR_HORIZONS:
        return _null_entry(
            engine_key,
            reason=f"unmeasured (only {n_horizons} admissible horizon points; need {CURVE_FLOOR_HORIZONS})",
            n_eff=total_n_eff,
            n_horizons=n_horizons,
            outcome_unit=outcome_unit,
        )

    # Sort by horizon
    admissible_sorted = sorted(admissible, key=lambda x: x[0])
    h_sorted = [x[0] for x in admissible_sorted]
    ic_sorted = [x[1] for x in admissible_sorted]
    w_sorted = [x[2] for x in admissible_sorted]

    # Long/short IC ratio (longest admissible horizon / shortest): the useful
    # curve-shape fact for both rising and decaying families. Only meaningful
    # when the short-horizon IC is positive (a sign flip or zero denominator
    # makes the ratio uninterpretable → None).
    ic_ratio: float | None = None
    if (
        math.isfinite(ic_sorted[0]) and math.isfinite(ic_sorted[-1])
        and ic_sorted[0] > 0
    ):
        ic_ratio = round(ic_sorted[-1] / ic_sorted[0], 4)

    # Pre-registered monotone-decrease gate
    is_dec, rho = _monotone_decrease_gate(h_sorted, ic_sorted)

    if not is_dec:
        # AUDIT FIX: a rising curve is a measured FACT, not a bare null.
        # half_life stays None (the fit is ill-posed on a rising curve) but the
        # trend, the long/short IC ratio, and the fitted direction are emitted
        # so displays can say "edge grows with horizon (126d/5d = 3.2x)"
        # instead of only "unmeasured".
        entry = _null_entry(
            engine_key,
            reason="edge_non_decaying",
            n_eff=total_n_eff,
            n_horizons=n_horizons,
            outcome_unit=outcome_unit,
        )
        entry["fit_rho"] = float(rho) if math.isfinite(rho) else None
        entry["trend"] = "non_decaying"
        entry["ic_ratio_long_short"] = ic_ratio
        if math.isfinite(rho):
            if rho > 0:
                entry["fit_direction"] = "rising"
            elif rho < 0:
                entry["fit_direction"] = "non_monotone"  # rho<0 but a step rose
            else:
                entry["fit_direction"] = "flat"
        return entry

    # CLASS-A: gate passed → attempt WNLS fit
    tau, _ = _fit_exp_decay(h_sorted, ic_sorted, w_sorted)

    if tau is None:
        entry = _null_entry(
            engine_key,
            reason="fit_failed",
            n_eff=total_n_eff,
            n_horizons=n_horizons,
            outcome_unit=outcome_unit,
        )
        entry["fit_rho"] = float(rho) if math.isfinite(rho) else None
        return entry

    half_life_val = tau * math.log(2)

    # Bootstrap CI (event-block, raw-mean proxy per horizon).
    # The CI refits the same curve construction used for the point estimate, but on
    # per-resample raw mean(outcome_excess) per horizon rather than shrunken_ic
    # (shrunken_ic requires the full hierarchical kernel per resample, which is not
    # recomputable here).  ci_basis="raw_mean_proxy" is recorded in the artifact to
    # make this explicit.
    ci_lo, ci_hi = _bootstrap_ci(
        graded_df=graded_df,
        horizon_col=h_sorted,
        n_resamples=BOOTSTRAP_N_RESAMPLES,
        ci_pct=BOOTSTRAP_CI_PCT,
    )

    # COHERENCE GUARD (pre-registered): unstable_ci conditions → emit half_life=None.
    # Triggered when:
    #   (a) bootstrap returned None (sign-change, unbounded, or too few valid resamples), OR
    #   (b) point estimate lies outside the bootstrap CI (ci_low > point OR ci_high < point), OR
    #   (c) CI width < CI_COHERENCE_EPSILON trading days (degenerate — e.g. all events share
    #       one as_of, so the block bootstrap has ~1 unique block).
    # Per prereg rule: "unstable fit = unmeasured".
    if ci_lo is None or ci_hi is None:
        unstable = True
        unstable_reason = "unstable_ci"
    elif (ci_hi - ci_lo) < CI_COHERENCE_EPSILON:
        unstable = True
        unstable_reason = "unstable_ci"
    elif half_life_val < ci_lo or half_life_val > ci_hi:
        unstable = True
        unstable_reason = "unstable_ci"
    else:
        unstable = False
        unstable_reason = None

    if unstable:
        half_life_val_final = None
        ci_low_final = None
        ci_high_final = None
        ci_basis_final = None
        reason = unstable_reason
        # Honest null: no curve-shape claims on an unstable fit.
        trend = None
        fit_direction = None
        ratio_out = None
    else:
        half_life_val_final = round(half_life_val, 2)
        ci_low_final = round(ci_lo, 2)
        ci_high_final = round(ci_hi, 2)
        ci_basis_final = "raw_mean_proxy"
        reason = None
        trend = "decaying"
        fit_direction = "falling"
        ratio_out = ic_ratio

    return {
        "decay_kind": "horizon",
        "outcome_unit": outcome_unit,
        "half_life": half_life_val_final,
        "ci_low": ci_low_final,
        "ci_high": ci_high_final,
        "ci_basis": ci_basis_final,
        "n_eff": int(total_n_eff),
        "n_horizons": int(n_horizons),
        "reason_null": reason,
        "fit_rho": float(rho) if math.isfinite(rho) else None,
        "trend": trend,
        "ic_ratio_long_short": ratio_out,
        "fit_direction": fit_direction,
    }


# ---------------------------------------------------------------------------
# Build function
# ---------------------------------------------------------------------------

def build_half_lives(root: Path | str | None = None) -> dict:
    """Build the half-life payload.

    Reads kernel_estimates.parquet (for shrunken_ic per horizon) and
    spine_index.parquet (for graded event counts / bootstrap).

    Returns the JSON-serialisable dict (without envelope keys).
    All numeric scalars are python-native (not numpy) to prevent the
    np.float64 + json.dumps TypeError gotcha.

    The returned dict always contains "status": "fit_ran" as a sentinel
    key, so downstream consumers can distinguish a successful (all-null)
    run from a job that crashed and wrote nothing.
    """
    estimates = _load_estimates(root)
    index_df = _load_index(root)

    if estimates.empty:
        log.warning("half_life.build_half_lives: kernel_estimates empty — returning all-null")
        return {
            "families": {},
            "status": "fit_ran",
            "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "notes": (
                "W2 re-scoped to holding-horizon decay (B1: no age-at-fire column). "
                "Staleness half-life: UNMEASURED (fill_offset uniformly=1 across all replay parquets). "
                "kernel_estimates absent — all families null."
            ),
        }

    # Filter spine index to entity-scope graded rows with finite outcomes
    entity_graded: pd.DataFrame
    if index_df.empty:
        entity_graded = pd.DataFrame()
        log.warning("half_life.build_half_lives: spine index empty — bootstrap will be skipped")
    else:
        mask_entity = index_df["scope_type"].astype(str) == "entity"
        mask_graded = index_df["outcome_graded"].fillna(False).map(
            lambda x: bool(x) if x is not None else False
        )
        eidx = index_df[mask_entity & mask_graded].copy()
        eidx["outcome_excess"] = pd.to_numeric(eidx["outcome_excess"], errors="coerce")
        entity_graded = eidx[np.isfinite(eidx["outcome_excess"])].reset_index(drop=True)

    engine_families = estimates["engine"].unique().tolist()
    families_out: dict[str, Any] = {}

    for engine in sorted(engine_families):
        # Marginal cells for this engine (regime='__all__')
        eng_cells = estimates[estimates["engine"] == engine]
        marginal_cells = eng_cells[eng_cells["regime"] == MARGINAL_BUCKET].copy()

        # Graded rows from spine index for this engine
        if entity_graded.empty:
            eng_graded = pd.DataFrame()
        else:
            eng_graded = entity_graded[
                entity_graded["engine"].astype(str) == engine
            ].copy()

        families_out[engine] = _estimate_family(engine, marginal_cells, eng_graded)

    # Staleness half-life (decay_kind='staleness'): measured where replay_delay.parquet
    # is present (Mac-local; absent on CI runners — degrades gracefully).
    staleness_out = build_staleness_half_lives()
    staleness_coverage = staleness_out.pop("_coverage_stamp", {})

    staleness_measured = staleness_coverage.get("artifact_present", False)
    if staleness_measured:
        staleness_note = (
            f"MEASURED from replay_delay.parquet "
            f"(years={staleness_coverage.get('years')}, "
            f"n_rows={staleness_coverage.get('n_rows')}, "
            f"n_eligible={staleness_coverage.get('n_rows_eligible')}). "
            "Gate: HAC-t on log-linear slope of mean fwd_ret_21 vs delay_n; "
            "monotone-decrease pre-gate. Null = honest null (W2 pattern)."
        )
    else:
        staleness_note = (
            "UNMEASURED (replay_delay.parquet absent — CI runner or pre-sweep). "
            "Staleness half-life unblocked by nwqs-d Item D; "
            "re-run write_half_lives() after replay_delay.parquet accrues."
        )

    return {
        "families": families_out,
        "staleness": staleness_out,
        "staleness_measured": staleness_measured,
        "staleness_note": staleness_note,
        "status": "fit_ran",
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": (
            "W2 re-scoped to holding-horizon decay (B1: no age-at-fire column in spine). "
            "Staleness half-life: measured when replay_delay.parquet is present (nwqs-d); "
            "unmeasured on CI runners (Mac-local artifact, EI R9). "
            "Conservative defaults: family_floor=200, curve_floor=3, cell_floor=12, "
            "bootstrap=90pct event-block 200 resamples. "
            "Expected outcome: horizon families mostly null (track_record IC rises; radar/us_board < 3 horizons). "
            "family_half_life naming recommendation: the 'half_life' column is a family-level "
            "constant broadcast to rows; future consumers should not read it as a per-signal value."
        ),
    }


# ---------------------------------------------------------------------------
# Write function (idempotent)
# ---------------------------------------------------------------------------

def write_half_lives(root: Path | str | None = None) -> dict:
    """Build the half-life payload and write to data/neuralweb/half_life.json.

    Stamps the envelope (artifact_id='kernel-half-lives') as sibling keys,
    mirroring the kernel-families pattern in engine/neuralweb/decay.py.

    The artifact ALWAYS writes (even if all-null) — the "status":"fit_ran"
    sentinel key allows downstream/display to distinguish a successful
    all-null run from a crashed job that wrote nothing.

    Returns a stats dict with output_path and n_families.
    """
    payload = build_half_lives(root)

    # Ensure all numeric scalars are python-native before json.dumps.
    # (numpy scalars poison json.dumps silently — qledger-numpy-json-dumps gotcha)
    payload = _sanitize_for_json(payload)

    if root is not None:
        out_dir = Path(root) / "data" / "neuralweb"
    else:
        from lib import config  # noqa: PLC0415
        out_dir = config.data_dir() / "neuralweb"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "half_life.json"

    # Stamp with envelope (sibling keys)
    try:
        from engine.neuralweb.envelope import stamp  # noqa: PLC0415
        payload = stamp(payload, artifact_id="kernel-half-lives")
    except Exception as e:  # noqa: BLE001
        log.warning("half_life.write_half_lives: envelope stamp failed: %s", e)

    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    n_families = len(payload.get("families", {}))
    n_measured = sum(
        1 for v in payload.get("families", {}).values()
        if isinstance(v, dict) and v.get("half_life") is not None
    )
    log.info(
        "half_life: wrote %d families (%d measured) to %s",
        n_families,
        n_measured,
        out_path,
    )

    return {
        "output_path": str(out_path),
        "n_families": n_families,
        "n_measured": n_measured,
    }


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively convert numpy scalars to python-native types.

    Prevents the np.float64 / np.int64 + json.dumps TypeError gotcha
    (qledger-numpy-json-dumps-zeroes-ledger memory entry).
    """
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    # numpy scalar types
    if isinstance(obj, np.floating):
        f = float(obj)
        return None if not math.isfinite(f) else f
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# ---------------------------------------------------------------------------
# Staleness half-life fitter (decay_kind='staleness')
# ---------------------------------------------------------------------------

def _nw_hac_t(x: np.ndarray, y: np.ndarray, lags: int) -> float:
    """HAC/Newey-West t-statistic for the slope in a simple OLS regression.

    Regresses y on [1, x] (intercept + slope), returns the NW-adjusted
    t-statistic for the slope coefficient.  Uses a 1-lag Bartlett kernel.

    Pure numpy: no scipy, no statsmodels.  Matches the spec requirement
    "reuse validation.py primitives — numpy only, no scipy".

    Returns float('nan') on degenerate inputs (< 2 points, zero variance).
    """
    n = len(x)
    if n < 2:  # noqa: PLR2004
        return float("nan")

    X = np.column_stack([np.ones(n), x.astype(float)])
    y_arr = y.astype(float)

    # OLS: β = (X'X)^{-1} X'y
    try:
        XtX = X.T @ X
        XtX_inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        return float("nan")

    beta = XtX_inv @ (X.T @ y_arr)
    resid = y_arr - X @ beta

    # Newey-West HAC variance for slope (coefficient index 1)
    # S = (1/n) * Σ_{t} e_t^2 * x_t x_t'
    #   + (2/n) * Σ_{l=1}^{lags} w_l * Σ_{t=l+1}^n e_t x_t (e_{t-l} x_{t-l})'
    # where w_l = 1 - l/(lags+1) (Bartlett kernel)
    S = np.zeros((2, 2))
    for t in range(n):
        xt = X[t:t + 1, :].T  # column vector
        S += (resid[t] ** 2) * (xt @ xt.T)
    S /= n

    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1)
        gamma = np.zeros((2, 2))
        for t in range(lag, n):
            xt = X[t:t + 1, :].T
            xt_l = X[t - lag:t - lag + 1, :].T
            gamma += resid[t] * resid[t - lag] * (xt @ xt_l.T)
        gamma /= n
        S += w * (gamma + gamma.T)

    # HAC variance of slope estimator
    var_beta = XtX_inv @ S @ XtX_inv
    var_slope = float(var_beta[1, 1])
    if var_slope <= 0 or not math.isfinite(var_slope):
        return float("nan")

    se_slope = math.sqrt(var_slope)
    if se_slope == 0:
        return float("nan")

    return float(beta[1]) / se_slope


def _fit_staleness_exp_numpy(
    delay_ns: np.ndarray,
    mean_rets: np.ndarray,
) -> tuple[float | None, float | None]:
    """Fit y = A * exp(-d / tau) via log-linear OLS (numpy only).

    log(y) = log(A) - d/tau  →  log(y) = c0 + c1 * d
    where c1 = -1/tau.

    Returns (tau, slope) or (None, None) on failure.

    Only uses positive y values (non-positive mean_ret → skip).
    """
    mask = mean_rets > 0
    if mask.sum() < 2:  # noqa: PLR2004
        return None, None

    d_arr = delay_ns[mask].astype(float)
    log_y = np.log(mean_rets[mask].astype(float))

    n = len(d_arr)
    if n < 2:  # noqa: PLR2004
        return None, None

    # OLS: log_y = c0 + c1 * d
    X = np.column_stack([np.ones(n), d_arr])
    try:
        XtX_inv = np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        return None, None
    beta = XtX_inv @ (X.T @ log_y)
    c1 = float(beta[1])  # slope = -1/tau

    if c1 >= 0 or not math.isfinite(c1):
        return None, None  # not decaying

    tau = -1.0 / c1
    if tau <= 0 or not math.isfinite(tau):
        return None, None

    return float(tau), float(c1)


def build_staleness_half_lives(
    replay_delay_path: Path | None = None,
) -> dict[str, Any]:
    """Fit the decay_kind='staleness' half-life per family from replay_delay.parquet.

    Degrades gracefully when the artifact is absent (CI runners):
    returns an unmeasured declaration with a coverage stamp explaining why.

    Spec requirements (nwqs_spec_d.md §2):
    - Per family: mean fwd_ret_21 (and MAE = -mean(fwd_mdd_21)) by delay_n
    - Monotone-decrease check on mean fwd_ret_21 vs delay_n
    - Exponential fit mirroring CLASS-A form; gate = negative slope
      significant at HAC/Newey-West t; numpy only, no scipy
    - Passing families: staleness_half_life in days-late (tau * ln2)
    - Failing families: HONEST NULL (W2 pattern)
    - Coverage stamp: which years/families are covered

    Returns a dict keyed by family_key (currently "__fires__" for the full
    population; future waves can split by tier_cascade or engine family).
    """
    p = replay_delay_path or _REPLAY_DELAY_PATH

    # Degrade gracefully when replay_delay.parquet is absent
    if not Path(p).exists():
        return {
            "__fires__": {
                "decay_kind": None,
                "staleness_half_life": None,
                "staleness_half_life_mae": None,
                "t_stat": None,
                "mean_by_delay": None,
                "mae_by_delay": None,
                "n_by_delay": None,
                "reason_null": "unmeasured (replay_delay.parquet absent — CI runner or pre-sweep)",
                "coverage_years": [],
                "coverage_families": [],
            },
            "_coverage_stamp": {
                "artifact_present": False,
                "path_checked": str(p),
                "years": [],
                "n_rows": 0,
            },
        }

    # Load the delay artifact
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("half_life.build_staleness: read failed: %s", e)
        return {
            "__fires__": {
                "decay_kind": None,
                "staleness_half_life": None,
                "staleness_half_life_mae": None,
                "t_stat": None,
                "mean_by_delay": None,
                "mae_by_delay": None,
                "n_by_delay": None,
                "reason_null": f"unmeasured (read error: {e})",
                "coverage_years": [],
                "coverage_families": [],
            },
            "_coverage_stamp": {
                "artifact_present": False,
                "path_checked": str(p),
                "years": [],
                "n_rows": 0,
                "error": str(e),
            },
        }

    n_rows_total = len(df)
    years_covered: list[int] = []
    if "year" in df.columns:
        years_covered = sorted(int(y) for y in df["year"].dropna().unique())

    # Era-law filter: uncensored rows only, survivor_bias=False
    mask_ok = ~df["horizon_censored"]
    if "survivor_bias" in df.columns:
        mask_ok = mask_ok & (~df["survivor_bias"])
    df_ok = df[mask_ok].copy()

    log.info(
        "staleness fitter: %d total delay rows, %d after era-law filter (years=%s)",
        n_rows_total, len(df_ok), years_covered,
    )

    # Coverage stamp
    coverage_stamp = {
        "artifact_present": True,
        "path_checked": str(p),
        "years": years_covered,
        "n_rows": n_rows_total,
        "n_rows_eligible": int(len(df_ok)),
    }

    # Single family "__fires__" (all fire rows, all tiers)
    # Future wave: split by tier_cascade, episode family, etc.
    result = _fit_staleness_family(
        family_key="__fires__",
        df=df_ok,
        years_covered=years_covered,
    )

    return {
        "__fires__": result,
        "_coverage_stamp": coverage_stamp,
    }


def _fit_staleness_family(
    family_key: str,
    df: pd.DataFrame,
    years_covered: list[int],
) -> dict[str, Any]:
    """Fit the staleness half-life for a single family of fire rows.

    Honest NULL printed per the W2 pattern when the gate fails.
    """
    null_base = {
        "decay_kind": None,
        "staleness_half_life": None,
        "staleness_half_life_mae": None,
        "t_stat": None,
        "mean_by_delay": None,
        "mae_by_delay": None,
        "n_by_delay": None,
        "reason_null": None,
        "coverage_years": years_covered,
        "coverage_families": [family_key],
    }

    if df.empty or "delay_n" not in df.columns or "fwd_ret_21" not in df.columns:
        return {**null_base, "reason_null": "no eligible rows or missing columns"}

    # Compute mean fwd_ret_21 and MAE (= -mean fwd_mdd_21) by delay_n
    grp = df.groupby("delay_n")
    mean_ret = grp["fwd_ret_21"].mean().dropna()
    n_per_delay = grp["fwd_ret_21"].count()

    mae_by_delay: dict[int, float | None] = {}
    if "fwd_mdd_21" in df.columns:
        mae_ser = grp["fwd_mdd_21"].mean()  # mdd is negative, so -mean = MAE
        for d in mean_ret.index:
            v = mae_ser.get(d)
            mae_by_delay[int(d)] = float(-v) if v is not None and math.isfinite(float(v)) else None
    else:
        mae_by_delay = {int(d): None for d in mean_ret.index}

    mean_by_delay = {int(d): float(v) for d, v in mean_ret.items()}
    n_by_delay = {int(d): int(v) for d, v in n_per_delay.items()}

    # Minimum N gate
    total_n = sum(n_by_delay.values())
    if total_n < STALENESS_MIN_N:
        return {
            **null_base,
            "mean_by_delay": mean_by_delay,
            "mae_by_delay": mae_by_delay,
            "n_by_delay": n_by_delay,
            "reason_null": f"insufficient n (total={total_n} < {STALENESS_MIN_N})",
        }

    if len(mean_by_delay) < 2:  # noqa: PLR2004
        return {
            **null_base,
            "mean_by_delay": mean_by_delay,
            "mae_by_delay": mae_by_delay,
            "n_by_delay": n_by_delay,
            "reason_null": "fewer than 2 delay_n points available",
        }

    d_arr = np.array(sorted(mean_by_delay.keys()), dtype=float)
    y_arr = np.array([mean_by_delay[int(d)] for d in d_arr], dtype=float)

    # Monotone-decrease check on raw means (per spec: same gate as CLASS-A)
    steps_nonincreasing = all(y_arr[i + 1] <= y_arr[i] for i in range(len(y_arr) - 1))
    if not steps_nonincreasing:
        return {
            **null_base,
            "mean_by_delay": mean_by_delay,
            "mae_by_delay": mae_by_delay,
            "n_by_delay": n_by_delay,
            "reason_null": "staleness_non_decaying (fwd_ret_21 not monotone-decreasing by delay_n)",
        }

    # HAC/Newey-West t-stat on the log-linear slope (numpy only)
    # log-linearize: only positive mean_rets are usable
    pos_mask = y_arr > 0
    if pos_mask.sum() < 2:  # noqa: PLR2004
        return {
            **null_base,
            "mean_by_delay": mean_by_delay,
            "mae_by_delay": mae_by_delay,
            "n_by_delay": n_by_delay,
            "reason_null": "staleness_non_decaying (non-positive mean fwd_ret_21 — cannot log-linearize)",
        }

    d_pos = d_arr[pos_mask]
    log_y_pos = np.log(y_arr[pos_mask])
    t_stat = _nw_hac_t(d_pos, log_y_pos, lags=STALENESS_HAC_LAGS)

    t_stat_val = float(t_stat) if math.isfinite(t_stat) else None

    # Gate: slope significant at HAC-t (slope should be < 0 → t_stat < -threshold)
    gate_passes = (
        t_stat_val is not None and t_stat_val < -STALENESS_T_THRESHOLD
    )

    if not gate_passes:
        return {
            **null_base,
            "mean_by_delay": mean_by_delay,
            "mae_by_delay": mae_by_delay,
            "n_by_delay": n_by_delay,
            "t_stat": t_stat_val,
            "reason_null": (
                f"staleness_insignificant (HAC-t={t_stat_val:.3f} not < -{STALENESS_T_THRESHOLD})"
                if t_stat_val is not None
                else "staleness_insignificant (HAC-t could not be computed)"
            ),
        }

    # Fit exponential decay (numpy log-linear OLS)
    tau, slope = _fit_staleness_exp_numpy(d_arr, y_arr)

    if tau is None:
        return {
            **null_base,
            "mean_by_delay": mean_by_delay,
            "mae_by_delay": mae_by_delay,
            "n_by_delay": n_by_delay,
            "t_stat": t_stat_val,
            "reason_null": "fit_failed (exponential fit did not converge)",
        }

    half_life_days = tau * math.log(2)

    # MAE half-life: same procedure on -mean(fwd_mdd_21) if available
    mae_hl: float | None = None
    mae_vals = np.array([
        mae_by_delay.get(int(d)) for d in d_arr
    ], dtype=object)
    mae_finite = np.array([v for v in mae_vals if v is not None and math.isfinite(float(v))], dtype=float)
    mae_ds = np.array([
        int(d_arr[i]) for i, v in enumerate(mae_vals)
        if v is not None and math.isfinite(float(v))
    ], dtype=float)
    if len(mae_finite) >= 2 and np.all(mae_finite > 0):  # noqa: PLR2004
        tau_mae, _ = _fit_staleness_exp_numpy(mae_ds, mae_finite)
        if tau_mae is not None:
            mae_hl = round(tau_mae * math.log(2), 2)

    return {
        "decay_kind": "staleness",
        "staleness_half_life": round(half_life_days, 2),
        "staleness_half_life_mae": mae_hl,
        "t_stat": round(t_stat_val, 3),
        "mean_by_delay": mean_by_delay,
        "mae_by_delay": mae_by_delay,
        "n_by_delay": n_by_delay,
        "reason_null": None,
        "coverage_years": years_covered,
        "coverage_families": [family_key],
    }
