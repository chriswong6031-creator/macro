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

STALENESS HALF-LIFE
-------------------
Declared UNMEASURED for all families.  Every replay parquet has
fill_offset uniformly = 1, so outcome-vs-days-late cannot be fit.
staleness half-life will display "unmeasured" and is NOT delivered here.

ESTIMATOR CLASSES
-----------------
CLASS-A: deep archive, ≥5 horizon points, any outcome_unit.
  Gate: Spearman(horizon, shrunken_ic) over __all__ marginal cells.
  If monotone-DECREASING (rho < 0 AND every step ≤ 0 within CI):
    fit y = A·exp(-h/τ) by WNLS on shrunken_ic; half_life = τ·ln2.
  If flat or rising: half_life = None, reason = "edge_non_decaying".

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
      "reason_null": str|null,
      "fit_rho": float|null
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
    "build_half_lives",
    "write_half_lives",
]

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
    """Return a null (unmeasured) entry with all required schema keys."""
    return {
        "decay_kind": None,
        "outcome_unit": outcome_unit or _outcome_unit_for(engine_key),
        "half_life": None,
        "ci_low": None,
        "ci_high": None,
        "ci_basis": None,
        "n_eff": int(n_eff),
        "n_horizons": int(n_horizons),
        "reason_null": str(reason),
        "fit_rho": None,
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

    # Pre-registered monotone-decrease gate
    is_dec, rho = _monotone_decrease_gate(h_sorted, ic_sorted)

    if not is_dec:
        entry = _null_entry(
            engine_key,
            reason="edge_non_decaying",
            n_eff=total_n_eff,
            n_horizons=n_horizons,
            outcome_unit=outcome_unit,
        )
        entry["fit_rho"] = float(rho) if math.isfinite(rho) else None
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
    else:
        half_life_val_final = round(half_life_val, 2)
        ci_low_final = round(ci_lo, 2)
        ci_high_final = round(ci_hi, 2)
        ci_basis_final = "raw_mean_proxy"
        reason = None

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

    return {
        "families": families_out,
        "status": "fit_ran",
        "produced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": (
            "W2 re-scoped to holding-horizon decay (B1: no age-at-fire column in spine). "
            "Staleness half-life: UNMEASURED (fill_offset uniformly=1 across all replay parquets; "
            "needs delayed-fill accrual in replay harness). "
            "Conservative defaults: family_floor=200, curve_floor=3, cell_floor=12, "
            "bootstrap=90pct event-block 200 resamples. "
            "Expected outcome: all families null (track_record IC rises; radar/us_board < 3 horizons). "
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
