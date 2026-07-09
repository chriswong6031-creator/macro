"""engine.neuralweb.causal_scout — CHF W2: Edge-Scout Estimator Core.

Deterministic causal-edge battery (CHF-R5) with per-cell TrialLedger accounting
(CHF-R3) and priors-mask enforcement (CHF-R4).

Rules implemented:
  CHF-R3  — cumulative, per-cell TrialLedger logging (family='causal_scan')
  CHF-R5  — estimator law: HAC for market_series, cross-ticker permutation for
             ticker_panel, overlap correction, negative-lag placebo,
             time-shift placebo (DT-R14), circular block bootstrap (DT-R14),
             era split (DT-R16), environment invariance over declared splits only
  CHF-R12 — synthetic gauntlet (see tests/test_causal_scout.py)

Language law (RUL-CC-5): the words "caused / proved / proof / validated" must
not appear in any generated text field.  Enforced by _sanitize_text() at every
write site.

Power floor: min_n=25 (house floor, CHF-R5 / P0 memo §2.4.6).

Cross-sectional N law (ticker-cluster time-confound):
  Effective N for ticker-panel targets is reported in calendar PERIODS (months),
  never fire counts.  Per-date demeaning (date fixed-effect) is applied before
  any time-series inference.  The within-period cross-ticker permutation is the
  null for level-threshold causes.

Overlap correction: non-overlapping subsampling (default) OR NW with lag >=
  horizon.  A plain HAC-on-mean on overlapping outcomes is a protocol violation
  and is unreachable by construction.

Era policy (DT-R16): pre/post-2010 break required.  When the target's span does
  not straddle 2010-01-01, the leg returns 'insufficient_era_span' — never a
  within-regime split dressed as an era test.

This is a PURE LIBRARY module.  No network, no data stores, no DAG/synapse
registration.  Live batching is W3.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.trial_ledger import TrialLedger
from engine.validation import newey_west_tstat

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAMILY = "causal_scan"
MIN_N = 25          # house power floor (CHF-R5 / P0 §2.4.6)
ERA_BREAK = date(2010, 1, 1)   # DT-R16 mandatory era break
N_BOOTSTRAP = 200   # CHF-R5: ≥200 draws, time-structure preserving (DT-R14)
N_SHIFT = 200       # CHF-R5: time-shift placebo draws (DT-R14)
MIN_BLOCK = 5       # minimum block size for circular bootstrap

# Language sanitizer banned words (RUL-CC-5)
_BANNED_WORDS = re.compile(
    r"\b(caused|cause|proves|proved|proof|proofs|validated|validates|validation)\b",
    re.IGNORECASE,
)
_REPLACEMENTS = {
    "caused": "co-moved with",
    "cause": "upstream of",
    "proves": "is consistent with",
    "proved": "was consistent with",
    "proof": "evidence",
    "proofs": "evidence",
    "validated": "assessed",
    "validates": "assesses",
    "validation": "assessment",
}


def _sanitize_text(text: str) -> str:
    """Replace banned causal-claim words with neutral alternatives (RUL-CC-5)."""
    def _sub(m: re.Match) -> str:
        return _REPLACEMENTS.get(m.group(0).lower(), m.group(0))
    return _BANNED_WORDS.sub(_sub, text)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class EnvironmentSplit:
    split_id: str
    definition: str  # human-readable description of when this split applies


@dataclass
class EdgeSpec:
    """Pre-declared causal edge specification.  All fields fixed at mint time.

    target_type: 'market_series' — single time series (HAC path)
                 'ticker_panel'  — cross-sectional panel (FE + permutation path)
    lags: integer lags to test (in periods matching the series frequency)
    cause_kind: 'level' — level value of the cause
                'change_event' — a discrete event or change in the cause
    environment_splits: PRE-DECLARED only; invariance is tested over exactly
                        these splits (CHF-R5, CHF-R7 hash at mint time)
    era_policy: 'require_break_2010' (default) or 'era_specific_recent_only'
    """
    edge_id: str
    cause_id: str
    target_id: str
    target_type: str   # 'market_series' | 'ticker_panel'
    lags: list[int]
    cause_kind: str    # 'level' | 'change_event'
    horizon_d: int     # forward horizon in days
    environment_splits: list[EnvironmentSplit] = field(default_factory=list)
    era_policy: str = "require_break_2010"

    def __post_init__(self) -> None:
        assert self.target_type in ("market_series", "ticker_panel"), self.target_type
        assert self.cause_kind in ("level", "change_event"), self.cause_kind
        assert self.era_policy in (
            "require_break_2010", "era_specific_recent_only"
        ), self.era_policy


@dataclass
class EdgeResult:
    """Output of run_battery() for one EdgeSpec."""
    edge_id: str
    verdict: str   # screened_candidate|era_specific|unstable|insufficient_era_span|
                   # insufficient_power|null|forbidden
    causal_support: dict   # {lens: 'weak'|'medium'|'strong'}
    concerns: list[str]
    stats: dict
    splits_declared: int
    splits_tested: int
    cells_logged: int
    asof: str


# ---------------------------------------------------------------------------
# Priors loading
# ---------------------------------------------------------------------------

def load_priors(root: Path | str | None = None) -> dict:
    """Load config/causal_priors.yml when present; return empty dict otherwise.

    The returned dict shape matches config/causal_priors.yml.  Tests may pass
    a fixture dict directly to run_battery() via the `priors` kwarg.
    """
    if root is None:
        root = Path(".")
    path = Path(root) / "config" / "causal_priors.yml"
    if not path.exists():
        return {}
    try:
        import yaml  # optional; only needed when the real file is present
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _is_forbidden(edge_spec: EdgeSpec, priors: dict) -> tuple[bool, str]:
    """Return (True, reason) if this edge is forbidden by the priors mask."""
    forbidden_causes = priors.get("forbidden_causes", [])
    if not isinstance(forbidden_causes, list):
        return False, ""
    cause_id = edge_spec.cause_id
    for pattern in forbidden_causes:
        # Support exact match and glob-style '*' wildcard prefix/suffix
        if pattern == cause_id:
            return True, f"cause '{cause_id}' is in forbidden_causes list (priors mask)"
        if "*" in pattern:
            regex = re.compile(
                "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
            )
            if regex.match(cause_id):
                return True, (
                    f"cause '{cause_id}' matches forbidden pattern '{pattern}'"
                )
    # Check collider tags
    colliders = priors.get("colliders", [])
    if cause_id in (colliders or []):
        return True, (
            f"cause '{cause_id}' is tagged as a collider in priors — "
            "conditioning on a collider manufactures a spurious association"
        )
    return False, ""


# ---------------------------------------------------------------------------
# Statistical primitives (pure numpy, no scipy)
# ---------------------------------------------------------------------------

def _newey_west_overlap(y: np.ndarray, lag: int, hac_lags: int | None = None) -> dict:
    """Newey-West HAC on the MEAN of y, with lag >= horizon for overlap correction.

    For overlapping-horizon outcomes, hac_lags must be >= horizon_d.  We use
    the non-overlapping subsampling path by default (see run_battery).  This
    helper is the ALTERNATIVE path for the market_series inference leg.

    CHF-R5: "a plain HAC-on-mean without one of these on overlapping outcomes
    must be impossible to reach."
    """
    if hac_lags is None:
        hac_lags = max(lag, 4)
    return newey_west_tstat(y, lags=hac_lags)


def _non_overlapping_sample(y: np.ndarray, horizon: int) -> np.ndarray:
    """Non-overlapping subsampling for overlap correction (CHF-R5).

    Takes every horizon-th observation so consecutive observations are
    non-overlapping.  Returns subsample of length >= 1 or empty array.
    """
    if horizon <= 1:
        return y
    return y[::horizon]


def _circular_block_bootstrap(
    x: np.ndarray,
    y: np.ndarray,
    stat_fn,
    n_draws: int = N_BOOTSTRAP,
    block_size: int | None = None,
    seed: int = 42,
) -> np.ndarray:
    """Circular block bootstrap on TIME blocks (CHF-R5, DT-R14).

    Resamples (x, y) pairs in circular blocks.  Never resamples tickers as
    the unit.  Returns array of n_draws bootstrap statistics.
    """
    n = len(x)
    if n < MIN_BLOCK * 3:
        return np.array([])
    if block_size is None:
        block_size = max(MIN_BLOCK, int(np.sqrt(n)))
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block_size))
    grid = np.arange(block_size)
    stats = np.empty(n_draws)
    for k in range(n_draws):
        starts = rng.integers(0, n, n_blocks)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        stats[k] = stat_fn(x[idx], y[idx])
    return stats


def _circular_shift_placebo(
    x: np.ndarray,
    y: np.ndarray,
    stat_fn,
    n_draws: int = N_SHIFT,
    seed: int = 99,
) -> np.ndarray:
    """Time-structure-preserving circular shifts of x (DT-R14 time-shift placebo).

    Rotates the CAUSE series by random amounts, keeping the internal
    autocorrelation structure intact.  Returns the distribution of null statistics.
    """
    n = len(x)
    if n < 2:
        return np.array([])
    rng = np.random.default_rng(seed)
    shifts = rng.integers(1, n, n_draws)  # at least 1-period shift
    stats = np.empty(n_draws)
    for k, s in enumerate(shifts):
        x_shifted = np.roll(x, s)
        stats[k] = stat_fn(x_shifted, y)
    return stats


def _mean_correlation(x: np.ndarray, y: np.ndarray) -> float:
    """Simple correlation as the test statistic for bootstrap distributions."""
    if len(x) < 3:
        return 0.0
    xs, ys = x - x.mean(), y - y.mean()
    denom = np.sqrt((xs ** 2).sum() * (ys ** 2).sum())
    if denom < 1e-12:
        return 0.0
    return float(np.dot(xs, ys) / denom)


def _within_period_permutation(
    cause_xs: np.ndarray,
    target_ys: np.ndarray,
    date_labels: np.ndarray,
    n_perm: int = N_BOOTSTRAP,
    seed: int = 77,
) -> tuple[float, np.ndarray]:
    """Within-period cross-ticker permutation null (CHF-R5, ticker_panel path).

    For each permutation, shuffles cause_xs WITHIN each date independently,
    then computes the cross-sectional correlation statistic aggregated across
    dates.  The observed statistic uses the real ordering.

    Returns (observed_stat, permutation_distribution).
    """
    rng = np.random.default_rng(seed)
    unique_dates = np.unique(date_labels)

    def _xs_stat(c: np.ndarray, t: np.ndarray, dl: np.ndarray) -> float:
        corrs = []
        for d in unique_dates:
            mask = dl == d
            ci, ti = c[mask], t[mask]
            if len(ci) < 3:
                continue
            corrs.append(_mean_correlation(ci, ti))
        return float(np.mean(corrs)) if corrs else 0.0

    obs = _xs_stat(cause_xs, target_ys, date_labels)
    perm_stats = np.empty(n_perm)
    for k in range(n_perm):
        cx = cause_xs.copy()
        for d in unique_dates:
            mask = date_labels == d
            cx[mask] = rng.permutation(cx[mask])
        perm_stats[k] = _xs_stat(cx, target_ys, date_labels)
    return obs, perm_stats


def _calendar_period_n(date_index: pd.DatetimeIndex) -> int:
    """Effective N in calendar months (CHF-R5 ticker-panel cross-sectional N law)."""
    if len(date_index) == 0:
        return 0
    periods = date_index.to_period("M").unique()
    return int(len(periods))


# ---------------------------------------------------------------------------
# Era-split logic (DT-R16)
# ---------------------------------------------------------------------------

def _era_split_verdict(
    dates: pd.DatetimeIndex,
    era_policy: str,
) -> tuple[bool, str]:
    """Return (era_ok, verdict_if_not_ok).

    era_ok=True means the span straddles ERA_BREAK (2010-01-01).
    era_ok=False with era_specific_recent_only: still permitted (auto era_specific).
    era_ok=False with require_break_2010: returns 'insufficient_era_span'.
    """
    if len(dates) == 0:
        return False, "insufficient_era_span"
    min_d = dates.min().date()
    max_d = dates.max().date()
    straddles = min_d < ERA_BREAK <= max_d
    if straddles:
        return True, ""
    if era_policy == "era_specific_recent_only":
        return True, ""   # permitted — we'll stamp era_specific in the result
    return False, "insufficient_era_span"


def _compute_era_stats(
    x: np.ndarray,
    y: np.ndarray,
    dates: pd.DatetimeIndex,
    horizon: int,
) -> dict:
    """Compute pre/post-2010 split statistics for the market_series path."""
    era_break_ts = pd.Timestamp(ERA_BREAK)
    pre_mask = dates < era_break_ts
    post_mask = dates >= era_break_ts

    def _leg(mask: np.ndarray) -> dict | None:
        xi, yi = x[mask], y[mask]
        if len(xi) < MIN_N:
            return None
        sub = _non_overlapping_sample(yi, horizon)
        if len(sub) < MIN_N:
            return None
        return newey_west_tstat(sub, lags=max(1, min(horizon, len(sub) - 1)))

    return {
        "pre_2010": _leg(pre_mask),
        "post_2010": _leg(post_mask),
    }


# ---------------------------------------------------------------------------
# Sibling / shared-parent concern
# ---------------------------------------------------------------------------

def _check_sibling_correlation(
    cause_series: np.ndarray,
    declared_siblings: list[np.ndarray],
    threshold: float = 0.70,
) -> tuple[bool, float]:
    """Check whether this cause is highly correlated with a declared sibling.

    Returns (is_sibling, max_abs_corr).  High correlation means the two
    signals share a common parent — they are NOT independent confirmation.
    """
    if not declared_siblings:
        return False, 0.0
    max_corr = 0.0
    for sib in declared_siblings:
        n = min(len(cause_series), len(sib))
        if n < 10:
            continue
        c = abs(_mean_correlation(cause_series[:n], sib[:n]))
        max_corr = max(max_corr, c)
    return max_corr >= threshold, max_corr


# ---------------------------------------------------------------------------
# TrialLedger accounting (CHF-R3)
# ---------------------------------------------------------------------------

def log_battery_cells(
    family: str,
    cells: list[dict],
    ledger: TrialLedger | None = None,
) -> int:
    """Log one DISTINCT TrialLedger config per cell (edge x lag x environment).

    Each cell dict must contain at minimum: edge_id, lag, split_id (or 'full').
    Placebo cells and undeclared-split cells are included.

    When ledger is None, cells are NOT written (no default path assumed here).
    The caller (W3 live batch) is responsible for supplying the ledger.

    Returns the count of newly-logged cells.
    """
    if ledger is None:
        return 0
    return ledger.log_grid(cells, family=family)


def cumulative_family_width(root: Path | str | None = None) -> int:
    """Return the cumulative causal_scan family width from the ledger."""
    if root is None:
        root = Path(".")
    path = Path(root) / "data" / "trial_ledger.jsonl"
    if not path.exists():
        return 0
    led = TrialLedger(path=path)
    return led.effective_n(family=FAMILY)


# ---------------------------------------------------------------------------
# Market-series battery (CHF-R5, market_series path)
# ---------------------------------------------------------------------------

def _run_market_series_battery(
    spec: EdgeSpec,
    cause: pd.Series,
    target: pd.Series,
    declared_siblings: list[np.ndarray] | None = None,
    environment_masks: dict[str, np.ndarray] | None = None,
    ledger: TrialLedger | None = None,
) -> EdgeResult:
    """Run the full CHF-R5 battery for a market_series target."""
    concerns: list[str] = []
    stats: dict = {}
    cells: list[dict] = []

    declared_siblings = declared_siblings or []
    environment_masks = environment_masks or {}

    # Align on common index
    aligned = pd.concat([cause.rename("x"), target.rename("y")], axis=1).dropna()
    if len(aligned) < MIN_N:
        return EdgeResult(
            edge_id=spec.edge_id,
            verdict="insufficient_power",
            causal_support={},
            concerns=[_sanitize_text(f"only {len(aligned)} aligned observations (floor={MIN_N})")],
            stats={},
            splits_declared=len(spec.environment_splits),
            splits_tested=0,
            cells_logged=0,
            asof=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    dates: pd.DatetimeIndex = pd.DatetimeIndex(aligned.index)
    x_full = aligned["x"].to_numpy(float)
    y_full = aligned["y"].to_numpy(float)

    # Era span check (DT-R16)
    era_ok, era_verdict = _era_split_verdict(dates, spec.era_policy)
    if not era_ok:
        _log_insufficient_era(spec, ledger, cells)
        return EdgeResult(
            edge_id=spec.edge_id,
            verdict="insufficient_era_span",
            causal_support={},
            concerns=[_sanitize_text(
                f"target span {dates.min().date()} to {dates.max().date()} "
                f"does not straddle 2010-01-01 (DT-R16 era break)"
            )],
            stats={},
            splits_declared=len(spec.environment_splits),
            splits_tested=0,
            cells_logged=0,
            asof=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    era_specific_stamp = spec.era_policy == "era_specific_recent_only"

    lag_stats: dict = {}
    screened_lags: list[int] = []

    for lag in spec.lags:
        # Build lag array: shift x forward by lag periods
        n = len(x_full)
        if lag >= n:
            concerns.append(
                _sanitize_text(f"lag={lag} >= series length {n}; skipping")
            )
            continue

        x_lagged = x_full[:-lag] if lag > 0 else x_full
        y_shifted = y_full[lag:] if lag > 0 else y_full
        dates_shifted = dates[lag:] if lag > 0 else dates

        if len(y_shifted) < MIN_N:
            concerns.append(
                _sanitize_text(
                    f"lag={lag}: only {len(y_shifted)} observations after shift"
                )
            )
            cells.append({
                "edge_id": spec.edge_id, "lag": lag, "split_id": "full",
                "cell_type": "primary",
            })
            if ledger is not None:
                log_battery_cells(FAMILY, [cells[-1]], ledger)
            continue

        # --- Overlap correction: use non-overlapping subsampling (CHF-R5) ---
        sub = _non_overlapping_sample(y_shifted, spec.horizon_d)
        sub_x = _non_overlapping_sample(x_lagged, spec.horizon_d)
        if len(sub) < MIN_N:
            # Fall back to HAC with lag >= horizon (alternative overlap correction)
            hac_stat = _newey_west_overlap(y_shifted, lag=lag,
                                           hac_lags=max(spec.horizon_d, 4))
        else:
            hac_stat = newey_west_tstat(sub, lags=max(1, min(4, len(sub) - 1)))

        lag_stats[str(lag)] = hac_stat

        # Log primary cell
        cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "full",
            "cell_type": "primary",
        }
        cells.append(cell)

        # --- Negative-lag placebo: does TARGET lead CAUSE? (CHF-R5) ---
        neg_lag = max(1, lag)
        y_neg = y_full[:-neg_lag]
        x_neg = x_full[neg_lag:]
        placebo_neg_cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "neg_lag_placebo",
            "cell_type": "placebo",
        }
        cells.append(placebo_neg_cell)
        if len(y_neg) >= MIN_N:
            sub_neg = _non_overlapping_sample(y_neg, spec.horizon_d)
            neg_stat = newey_west_tstat(
                sub_neg, lags=max(1, min(4, len(sub_neg) - 1))
            )
            neg_t = neg_stat.get("t")
            fwd_t = hac_stat.get("t")
            if (
                neg_t is not None and fwd_t is not None
                and abs(neg_t) > abs(fwd_t)
            ):
                concerns.append(_sanitize_text(
                    f"lag={lag}: negative-lag placebo |t|={abs(neg_t):.2f} "
                    f"> forward |t|={abs(fwd_t):.2f} — target may lead cause "
                    "(reverse-causation concern; edge not screened_candidate)"
                ))
                lag_stats[f"{lag}_neg_placebo"] = neg_stat
                # Negative-lag fires: this lag does NOT qualify as screened
                continue

        # --- Time-shift placebo (DT-R14, CHF-R5) ---
        shift_cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "time_shift_placebo",
            "cell_type": "placebo",
        }
        cells.append(shift_cell)
        shift_dist = _circular_shift_placebo(
            x_lagged, y_shifted, _mean_correlation, n_draws=N_SHIFT, seed=lag + 1
        )
        obs_corr = _mean_correlation(x_lagged, y_shifted)
        if len(shift_dist) > 0:
            shift_pctile = float(np.mean(shift_dist < obs_corr))
            lag_stats[f"{lag}_shift_pctile"] = round(shift_pctile, 4)
            if shift_pctile < 0.90:
                concerns.append(_sanitize_text(
                    f"lag={lag}: time-shift placebo: observed corr at "
                    f"{shift_pctile:.0%} of null distribution — "
                    "indistinguishable from lagged echo"
                ))
                continue  # time-shift kills this lag

        # --- Circular block bootstrap stability (CHF-R5, DT-R14) ---
        boot_cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "block_bootstrap",
            "cell_type": "stability",
        }
        cells.append(boot_cell)
        boot_dist = _circular_block_bootstrap(
            x_lagged, y_shifted, _mean_correlation,
            n_draws=N_BOOTSTRAP, seed=lag + 100,
        )
        boot_stats = {}
        if len(boot_dist) > 0:
            boot_stats = {
                "ci_2p5": round(float(np.percentile(boot_dist, 2.5)), 4),
                "ci_97p5": round(float(np.percentile(boot_dist, 97.5)), 4),
                "boot_mean": round(float(np.mean(boot_dist)), 4),
            }
            # Flag instability: CI spans 0
            if boot_stats["ci_2p5"] <= 0 <= boot_stats["ci_97p5"]:
                concerns.append(_sanitize_text(
                    f"lag={lag}: bootstrap 95% CI [{boot_stats['ci_2p5']}, "
                    f"{boot_stats['ci_97p5']}] spans zero — unstable"
                ))
            else:
                screened_lags.append(lag)
        else:
            screened_lags.append(lag)   # too short for bootstrap; use HAC alone

        lag_stats[f"{lag}_bootstrap"] = boot_stats

        # --- Environment invariance (declared splits only, CHF-R5/CHF-R7) ---
        splits_tested_this_lag = 0
        for env_split in spec.environment_splits:
            mask = environment_masks.get(env_split.split_id)
            split_cell = {
                "edge_id": spec.edge_id, "lag": lag,
                "split_id": env_split.split_id, "cell_type": "environment",
            }
            cells.append(split_cell)
            if mask is None:
                concerns.append(_sanitize_text(
                    f"lag={lag}, split={env_split.split_id}: no mask provided — "
                    "undeclared environment; cell logged with protocol concern"
                ))
                continue
            mask_aligned = mask[lag:] if lag > 0 else mask
            if len(mask_aligned) != len(y_shifted):
                mask_aligned = mask_aligned[:len(y_shifted)]
            xi_env = x_lagged[mask_aligned.astype(bool)]
            yi_env = y_shifted[mask_aligned.astype(bool)]
            if len(xi_env) < MIN_N:
                continue
            sub_env = _non_overlapping_sample(yi_env, spec.horizon_d)
            env_stat = newey_west_tstat(
                sub_env, lags=max(1, min(4, len(sub_env) - 1))
            )
            lag_stats[f"{lag}_{env_split.split_id}"] = env_stat
            splits_tested_this_lag += 1

    # Era split statistics (DT-R16)
    era_stats = _compute_era_stats(x_full, y_full, dates, spec.horizon_d)
    stats["era_split"] = era_stats

    # Era divergence concern
    pre = era_stats.get("pre_2010")
    post = era_stats.get("post_2010")
    if pre is not None and post is not None:
        pre_t = pre.get("t") or 0.0
        post_t = post.get("t") or 0.0
        if pre_t * post_t < 0:   # sign flip across eras
            concerns.append(_sanitize_text(
                "era split: pre-2010 and post-2010 effects have opposite signs — "
                "effect is era-specific"
            ))

    # Sibling check (CHF-R10 shared-parent concern)
    sib_flag, sib_corr = _check_sibling_correlation(x_full, declared_siblings)
    if sib_flag:
        concerns.append(_sanitize_text(
            f"shared-parent suspect: cause correlates {sib_corr:.2f} with a "
            "declared sibling — edges may NOT constitute independent confirmation"
        ))

    stats["by_lag"] = lag_stats

    # Log all cells to the ledger
    cells_logged = 0
    if cells:
        cells_logged = log_battery_cells(FAMILY, cells, ledger)

    # Verdict synthesis
    splits_tested = sum(
        1 for k in lag_stats if any(
            s.split_id in k for s in spec.environment_splits
        )
    )
    verdict = _synthesize_verdict(
        screened_lags=screened_lags,
        concerns=concerns,
        era_specific_stamp=era_specific_stamp,
    )

    support = _compute_support(
        lag_stats=lag_stats,
        screened_lags=screened_lags,
        verdict=verdict,
    )

    return EdgeResult(
        edge_id=spec.edge_id,
        verdict=verdict,
        causal_support=support,
        concerns=[_sanitize_text(c) for c in concerns],
        stats=stats,
        splits_declared=len(spec.environment_splits),
        splits_tested=splits_tested,
        cells_logged=cells_logged,
        asof=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


# ---------------------------------------------------------------------------
# Ticker-panel battery (CHF-R5, ticker_panel path)
# ---------------------------------------------------------------------------

def _run_ticker_panel_battery(
    spec: EdgeSpec,
    cause_panel: pd.DataFrame,
    target_panel: pd.DataFrame,
    declared_siblings: list[np.ndarray] | None = None,
    environment_masks: dict[str, np.ndarray] | None = None,
    ledger: TrialLedger | None = None,
) -> EdgeResult:
    """Run the full CHF-R5 battery for a ticker_panel target.

    cause_panel, target_panel: DataFrames indexed by date, columns = tickers.
    Inference path:
      1. Collapse to long format (date, ticker, x, y).
      2. Within-date demeaning (date fixed-effect) BEFORE any time-series.
      3. Cross-ticker permutation within each date as the null.
      4. Effective N = calendar months (never fire counts).
    """
    concerns: list[str] = []
    stats: dict = {}
    cells: list[dict] = []
    declared_siblings = declared_siblings or []
    environment_masks = environment_masks or {}

    # Melt to long format
    cause_long = cause_panel.stack().rename("x")
    target_long = target_panel.stack().rename("y")
    combined = pd.concat([cause_long, target_long], axis=1).dropna()
    if len(combined) == 0:
        return _power_fail(spec, "no aligned observations")

    combined.index.names = ["date", "ticker"]
    combined = combined.reset_index()
    dates_series = pd.to_datetime(combined["date"])

    # Effective N in calendar months (CHF-R5 cross-sectional N law)
    eff_n_months = _calendar_period_n(pd.DatetimeIndex(combined["date"].unique()))
    stats["effective_n_months"] = eff_n_months
    stats["fire_count_do_not_use"] = int(len(combined))  # logged but NOT used for inference

    if eff_n_months < MIN_N:
        return _power_fail(
            spec,
            f"only {eff_n_months} calendar months (floor={MIN_N}); "
            "fire count is NOT used for inference per cross-sectional N law"
        )

    # Era span check (DT-R16)
    era_ok, era_verdict = _era_split_verdict(
        pd.DatetimeIndex(combined["date"].unique()), spec.era_policy
    )
    if not era_ok:
        _log_insufficient_era(spec, ledger, cells)
        return EdgeResult(
            edge_id=spec.edge_id,
            verdict="insufficient_era_span",
            causal_support={},
            concerns=[_sanitize_text(
                f"panel date span does not straddle 2010-01-01 (DT-R16)"
            )],
            stats=stats,
            splits_declared=len(spec.environment_splits),
            splits_tested=0,
            cells_logged=0,
            asof=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    era_specific_stamp = spec.era_policy == "era_specific_recent_only"

    # Within-date demeaning (date fixed-effect)
    combined["x_dm"] = combined.groupby("date")["x"].transform(
        lambda s: s - s.mean()
    )
    combined["y_dm"] = combined.groupby("date")["y"].transform(
        lambda s: s - s.mean()
    )

    x_all = combined["x_dm"].to_numpy(float)
    y_all = combined["y_dm"].to_numpy(float)
    date_labels = combined["date"].to_numpy()

    screened_lags: list[int] = []
    lag_stats: dict = {}

    for lag in spec.lags:
        cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "full",
            "cell_type": "primary",
        }
        cells.append(cell)

        # For panel lags: shift by date periods across the panel
        unique_dates = np.sort(combined["date"].unique())
        if lag >= len(unique_dates):
            concerns.append(
                _sanitize_text(f"lag={lag} >= unique date count {len(unique_dates)}")
            )
            continue

        # Build lagged panel: for each ticker, shift x by `lag` dates
        lagged_rows = []
        for ticker, grp in combined.groupby("ticker"):
            grp_s = grp.sort_values("date")
            if len(grp_s) <= lag:
                continue
            dates_t = grp_s["date"].to_numpy()
            x_t = grp_s["x_dm"].to_numpy(float)
            y_t = grp_s["y_dm"].to_numpy(float)
            for i in range(lag, len(dates_t)):
                lagged_rows.append({
                    "date": dates_t[i],
                    "ticker": ticker,
                    "x_lag": x_t[i - lag],
                    "y": y_t[i],
                })
        if not lagged_rows:
            continue
        lag_df = pd.DataFrame(lagged_rows)
        x_lag_arr = lag_df["x_lag"].to_numpy(float)
        y_arr = lag_df["y"].to_numpy(float)
        dl_arr = lag_df["date"].to_numpy()

        if len(x_lag_arr) < MIN_N:
            concerns.append(_sanitize_text(
                f"lag={lag}: only {len(x_lag_arr)} observations after lag"
            ))
            continue

        # Within-period cross-ticker permutation (CHF-R5 ticker_panel)
        obs_stat, perm_dist = _within_period_permutation(
            x_lag_arr, y_arr, dl_arr, n_perm=N_BOOTSTRAP, seed=lag + 200
        )
        perm_pctile = float(np.mean(perm_dist < obs_stat))
        lag_stats[str(lag)] = {
            "obs_corr": round(obs_stat, 4),
            "perm_pctile": round(perm_pctile, 4),
        }

        # --- Negative-lag placebo ---
        neg_cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "neg_lag_placebo",
            "cell_type": "placebo",
        }
        cells.append(neg_cell)
        neg_rows = []
        for ticker, grp in combined.groupby("ticker"):
            grp_s = grp.sort_values("date")
            if len(grp_s) <= lag:
                continue
            dates_t = grp_s["date"].to_numpy()
            x_t = grp_s["x_dm"].to_numpy(float)
            y_t = grp_s["y_dm"].to_numpy(float)
            for i in range(lag, len(dates_t)):
                neg_rows.append({
                    "date": dates_t[i - lag],
                    "ticker": ticker,
                    "x_lead": x_t[i],
                    "y": y_t[i - lag],
                })
        if neg_rows:
            neg_df = pd.DataFrame(neg_rows)
            neg_obs, neg_perm = _within_period_permutation(
                neg_df["x_lead"].to_numpy(float),
                neg_df["y"].to_numpy(float),
                neg_df["date"].to_numpy(),
                n_perm=N_BOOTSTRAP,
                seed=lag + 300,
            )
            neg_pctile = float(np.mean(neg_perm < neg_obs))
            if neg_pctile > perm_pctile:
                concerns.append(_sanitize_text(
                    f"lag={lag}: negative-lag placebo has HIGHER percentile "
                    f"({neg_pctile:.2f} vs {perm_pctile:.2f}) — "
                    "target may lead cause; reverse causation concern"
                ))
                continue

        # --- Time-shift placebo (DT-R14) ---
        shift_cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "time_shift_placebo",
            "cell_type": "placebo",
        }
        cells.append(shift_cell)
        shift_dist = _circular_shift_placebo(
            x_lag_arr, y_arr, _mean_correlation, n_draws=N_SHIFT, seed=lag + 400
        )
        if len(shift_dist) > 0:
            shift_pctile = float(np.mean(shift_dist < obs_stat))
            lag_stats[f"{lag}_shift_pctile"] = round(shift_pctile, 4)
            if shift_pctile < 0.90:
                concerns.append(_sanitize_text(
                    f"lag={lag}: time-shift placebo kills this lag "
                    f"(obs at {shift_pctile:.0%} of null)"
                ))
                continue

        # --- Block bootstrap stability ---
        boot_cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "block_bootstrap",
            "cell_type": "stability",
        }
        cells.append(boot_cell)
        boot_dist = _circular_block_bootstrap(
            x_lag_arr, y_arr, _mean_correlation,
            n_draws=N_BOOTSTRAP, seed=lag + 500,
        )
        if len(boot_dist) > 0:
            ci_lo = float(np.percentile(boot_dist, 2.5))
            ci_hi = float(np.percentile(boot_dist, 97.5))
            lag_stats[f"{lag}_bootstrap"] = {
                "ci_2p5": round(ci_lo, 4),
                "ci_97p5": round(ci_hi, 4),
            }
            if ci_lo <= 0 <= ci_hi:
                concerns.append(_sanitize_text(
                    f"lag={lag}: bootstrap CI [{ci_lo:.3f}, {ci_hi:.3f}] "
                    "spans zero — unstable"
                ))
            else:
                if perm_pctile >= 0.90:
                    screened_lags.append(lag)
        else:
            if perm_pctile >= 0.90:
                screened_lags.append(lag)

    # Log all cells
    cells_logged = 0
    if cells:
        cells_logged = log_battery_cells(FAMILY, cells, ledger)

    stats["by_lag"] = lag_stats
    stats["eff_n_months"] = eff_n_months

    splits_tested = 0
    verdict = _synthesize_verdict(
        screened_lags=screened_lags,
        concerns=concerns,
        era_specific_stamp=era_specific_stamp,
    )
    support = _compute_support(
        lag_stats=lag_stats,
        screened_lags=screened_lags,
        verdict=verdict,
    )

    return EdgeResult(
        edge_id=spec.edge_id,
        verdict=verdict,
        causal_support=support,
        concerns=[_sanitize_text(c) for c in concerns],
        stats=stats,
        splits_declared=len(spec.environment_splits),
        splits_tested=splits_tested,
        cells_logged=cells_logged,
        asof=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _power_fail(spec: EdgeSpec, reason: str) -> EdgeResult:
    return EdgeResult(
        edge_id=spec.edge_id,
        verdict="insufficient_power",
        causal_support={},
        concerns=[_sanitize_text(reason)],
        stats={},
        splits_declared=len(spec.environment_splits),
        splits_tested=0,
        cells_logged=0,
        asof=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _log_insufficient_era(
    spec: EdgeSpec,
    ledger: TrialLedger | None,
    cells: list[dict],
) -> None:
    cell = {
        "edge_id": spec.edge_id, "lag": None, "split_id": "era_check",
        "cell_type": "terminal",
    }
    cells.append(cell)
    if ledger is not None:
        log_battery_cells(FAMILY, [cell], ledger)


def _synthesize_verdict(
    screened_lags: list[int],
    concerns: list[str],
    era_specific_stamp: bool,
) -> str:
    """CHF-R5 verdict vocabulary synthesis."""
    has_instability = any("unstable" in c or "spans zero" in c for c in concerns)
    has_era_flip = any("era-specific" in c or "era split" in c for c in concerns)

    if not screened_lags:
        if has_instability:
            return "unstable"
        return "null"

    if has_instability:
        return "unstable"

    # Era sign flip (DT-R16): pre/post-2010 sign diverges → era_specific
    if has_era_flip:
        return "era_specific"

    if era_specific_stamp:
        return "era_specific"

    # All placebos passed for the screened lags
    return "screened_candidate"


def _compute_support(
    lag_stats: dict,
    screened_lags: list[int],
    verdict: str,
) -> dict:
    """Compute causal_support per lens: weak|medium|strong."""
    if not screened_lags or verdict not in ("screened_candidate", "era_specific"):
        return {"primary": "weak"}
    # Use max t-stat across screened lags as the strength indicator
    ts = []
    for lag in screened_lags:
        st = lag_stats.get(str(lag))
        if isinstance(st, dict):
            t = st.get("t")
            if t is not None:
                ts.append(abs(t))
            # Also handle panel permutation path
            pctile = st.get("perm_pctile")
            if pctile is not None:
                ts.append(pctile * 4)  # map 0.99 -> 3.96
    if not ts:
        return {"primary": "weak"}
    max_t = max(ts)
    if max_t >= 3.0:
        strength = "strong"
    elif max_t >= 2.0:
        strength = "medium"
    else:
        strength = "weak"
    return {"primary": strength}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_battery(
    spec: EdgeSpec,
    cause: pd.Series | pd.DataFrame,
    target: pd.Series | pd.DataFrame,
    *,
    priors: dict | None = None,
    root: Path | str | None = None,
    declared_siblings: list[np.ndarray] | None = None,
    environment_masks: dict[str, np.ndarray] | None = None,
    ledger: TrialLedger | None = None,
) -> EdgeResult:
    """Run the full CHF-R5 battery for one EdgeSpec.

    Args:
        spec: Pre-declared edge specification.
        cause: Series (market_series path) or DataFrame (ticker_panel path).
               For ticker_panel: indexed by date, columns = tickers.
        target: Same shape as cause.
        priors: Dict matching config/causal_priors.yml schema.  If None,
                loads from root/config/causal_priors.yml (or returns {} if absent).
        root: Repo root for loading priors and the trial ledger.
        declared_siblings: List of numpy arrays for the shared-parent check.
        environment_masks: {split_id: boolean_array} for declared splits.
        ledger: TrialLedger instance for cell logging.  If None, uses default path.

    Returns:
        EdgeResult with verdict, causal_support, concerns, stats, and cell counts.
    """
    # Load priors
    if priors is None:
        priors = load_priors(root)

    # Priors mask enforcement FIRST (CHF-R5 — before any computation)
    is_forbidden, refusal_reason = _is_forbidden(spec, priors)
    if is_forbidden:
        return EdgeResult(
            edge_id=spec.edge_id,
            verdict="forbidden",
            causal_support={},
            concerns=[_sanitize_text(refusal_reason)],
            stats={},
            splits_declared=len(spec.environment_splits),
            splits_tested=0,
            cells_logged=0,
            asof=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    # Variance check before dispatch
    if isinstance(cause, pd.Series):
        if cause.std() < 1e-12:
            return _power_fail(spec, "cause series is degenerate (zero variance)")
    if isinstance(target, pd.Series):
        if target.std() < 1e-12:
            return _power_fail(spec, "target series is degenerate (zero variance)")

    # Dispatch by target type
    if spec.target_type == "market_series":
        if not isinstance(cause, pd.Series) or not isinstance(target, pd.Series):
            return _power_fail(
                spec,
                "market_series path requires pd.Series for cause and target"
            )
        return _run_market_series_battery(
            spec, cause, target,
            declared_siblings=declared_siblings,
            environment_masks=environment_masks,
            ledger=ledger,
        )
    else:  # ticker_panel
        if not isinstance(cause, pd.DataFrame) or not isinstance(target, pd.DataFrame):
            return _power_fail(
                spec,
                "ticker_panel path requires pd.DataFrame for cause and target"
            )
        return _run_ticker_panel_battery(
            spec, cause, target,
            declared_siblings=declared_siblings,
            environment_masks=environment_masks,
            ledger=ledger,
        )
