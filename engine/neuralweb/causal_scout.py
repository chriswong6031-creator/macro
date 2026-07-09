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
write site.  The sanitizer acts ONLY on the four root banned words (caused,
proved/proof, validated) so that replacement strings remain grammatical.

Power floor: min_n=25 (house floor, CHF-R5 / P0 memo §2.4.6).

Cross-sectional N law (ticker-cluster time-confound):
  Effective N for ticker-panel targets is reported in calendar PERIODS (months),
  never fire counts.  Per-date demeaning (date fixed-effect) is applied before
  any time-series inference.  The within-period cross-ticker permutation is the
  null for level-threshold causes.

Effect series definition (cause-aware primary statistic):
  e_t = z(x_{t-lag}) * z(y_t)
  where z() is a zscore over the aligned sample.  The Newey-West HAC t-stat is
  computed on the MEAN of e_t (after non-overlapping subsampling for overlap
  correction).  This is the cross_asset.py leadlag_pairs z-product pattern.
  Positive mean(e_t) means the cause predicts the target in the same direction
  at the declared lag; the t-stat gauges significance of that co-movement.

Overlap correction: non-overlapping subsampling (default) of e_t; HAC lag >=
  horizon on the full e_t as fallback.  Plain-HAC on overlapping target-only
  is unreachable by construction.

Era policy (DT-R16): pre/post-2010 break required.  When the target's span does
  not straddle 2010-01-01, the leg returns 'insufficient_era_span' — never a
  within-regime split dressed as an era test.

Invariance leg (B2 fix): block-bootstrap CI on the DIFFERENCE of effect means
  across splits.  Effect significant in one split and near-zero/opposite in
  complement, with difference CI excluding zero → invariance_failure concern.

This is a PURE LIBRARY module.  No network, no data stores, no DAG/synapse
registration.  Live batching is W3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

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
N_BOOTSTRAP = 200   # CHF-R5: >=200 draws, time-structure preserving (DT-R14)
N_SHIFT = 200       # CHF-R5: time-shift placebo draws (DT-R14)
MIN_BLOCK = 5       # minimum block size for circular bootstrap

# Language sanitizer banned words (RUL-CC-5) — exactly four root words
# "cause" is NOT banned (only "caused"); "proves" is NOT banned (only "proved/proof")
_BANNED_WORDS = re.compile(
    r"\b(caused|proved|proof|proofs|validated|validates|validation)\b",
    re.IGNORECASE,
)
_REPLACEMENTS = {
    "caused": "co-moved with",
    "proved": "was consistent with",
    "proof": "evidence",
    "proofs": "evidence",
    "validated": "assessed",
    "validates": "assesses",
    "validation": "assessment",
}


def _sanitize_text(text: str) -> str:
    """Replace banned causal-claim words with neutral alternatives (RUL-CC-5).

    Acts ONLY on: caused, proved, proof, validated (and inflections).
    Does NOT replace 'cause' (noun), 'proves', 'proves' etc. so that
    concern strings remain grammatical after substitution.
    """
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

def _zscore(a: np.ndarray) -> np.ndarray:
    """Zscore over the full sample; return zeros if zero variance."""
    s = float(np.std(a))
    if s < 1e-12:
        return np.zeros_like(a)
    return (a - np.mean(a)) / s


def _effect_series(x_lagged: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Compute the z-product effect series e_t = z(x_lagged_t) * z(y_t).

    This is the cause-aware primary statistic (cross_asset.py leadlag_pairs
    z-product pattern).  Positive mean(e_t) signals that the cause predicts
    the target in the same direction at the declared lag.

    Both arrays must be pre-aligned (same length).
    """
    return _zscore(x_lagged) * _zscore(y)


def _newey_west_overlap(e: np.ndarray, lag: int, hac_lags: int | None = None) -> dict:
    """Newey-West HAC on the MEAN of the effect series e_t.

    For overlapping-horizon outcomes, hac_lags must be >= horizon_d.  We use
    the non-overlapping subsampling path by default (see run_battery).  This
    helper is the ALTERNATIVE path for the market_series inference leg.

    CHF-R5: 'a plain HAC-on-mean without one of these on overlapping outcomes
    must be impossible to reach.'  This path operates on the effect series,
    never the raw target.
    """
    if hac_lags is None:
        hac_lags = max(lag, 4)
    return newey_west_tstat(e, lags=hac_lags)


def _non_overlapping_sample(y: np.ndarray, horizon: int) -> np.ndarray:
    """Non-overlapping subsampling for overlap correction (CHF-R5).

    Takes every horizon-th observation so consecutive observations are
    non-overlapping.  Returns subsample of length >= 1 or empty array.
    """
    if horizon <= 1:
        return y
    return y[::horizon]


def _circular_block_bootstrap_1d(
    e: np.ndarray,
    n_draws: int = N_BOOTSTRAP,
    block_size: int | None = None,
    seed: int = 42,
) -> np.ndarray:
    """Circular block bootstrap on DATE blocks of the effect series e_t.

    Resamples the 1-d effect series in circular time blocks.  Returns
    array of n_draws bootstrap mean(e) statistics.  Calendar-period count
    governs CI precision (B5 fix).
    """
    n = len(e)
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
        stats[k] = float(np.mean(e[idx]))
    return stats


def _circular_block_bootstrap(
    x: np.ndarray,
    y: np.ndarray,
    stat_fn,
    n_draws: int = N_BOOTSTRAP,
    block_size: int | None = None,
    seed: int = 42,
) -> np.ndarray:
    """Circular block bootstrap on TIME blocks for the stability leg.

    Resamples (x, y) pairs in circular blocks; computes stat_fn(x_boot, y_boot).
    Used for the correlation-based stability check (block bootstrap CI on the
    observed correlation).

    NOTE: the effect-series invariance bootstrap uses _circular_block_bootstrap_1d.
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
    lag: int = 0,
) -> dict:
    """Compute pre/post-2010 split effect statistics for the market_series path.

    The effect estimate within each era is mean(e_sub) where e_sub is the
    non-overlapping subsample of the effect series e_t = z(x_{t-lag})*z(y_t).
    The t-stat is Newey-West on the effect subsample, not the target mean.

    Comparison of effect estimates across eras (not target means) is what
    the era concern text describes.

    lag: the same x[:-lag]/y[lag:] shift applied for the primary lag — era stats
    must be computed on the SAME aligned window, not the contemporaneous series.
    When lag=0, the full contemporaneous arrays are used (no shift).
    """
    # Apply the same lag-shift as the primary leg (FIX 1 — Defect A):
    # contemporaneous x/y are NOT the same as the lag-shifted window used for
    # the primary HAC — computing era stats on x_full/y_full measures a different
    # z-product than the screened lag.
    n = len(x)
    if lag > 0 and lag < n:
        x_lag = x[:-lag]
        y_lag = y[lag:]
        dates_lag = dates[lag:]
    else:
        x_lag = x
        y_lag = y
        dates_lag = dates

    era_break_ts = pd.Timestamp(ERA_BREAK)
    pre_mask = dates_lag < era_break_ts
    post_mask = dates_lag >= era_break_ts

    def _leg(mask: np.ndarray) -> dict | None:
        xi, yi = x_lag[mask], y_lag[mask]
        if len(xi) < MIN_N:
            return None
        e_era = _effect_series(xi, yi)
        sub_e = _non_overlapping_sample(e_era, horizon)
        if len(sub_e) < MIN_N:
            # fall back to HAC on full effect series with horizon lag
            return newey_west_tstat(e_era, lags=max(1, min(horizon, len(e_era) - 1)))
        return newey_west_tstat(sub_e, lags=max(1, min(4, len(sub_e) - 1)))

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
    """Run the full CHF-R5 battery for a market_series target.

    Primary statistic: Newey-West HAC t of mean(e_t) where
    e_t = z(x_{t-lag}) * z(y_t) — the cause-aware z-product effect series.
    """
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
    # Track splits_tested across all lags (unique split keys)
    splits_tested_set: set[str] = set()

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

        # --- Effect series: e_t = z(x_{t-lag}) * z(y_t) ---
        e_series = _effect_series(x_lagged, y_shifted)

        # --- Overlap correction: non-overlapping subsampling of effect series ---
        sub_e = _non_overlapping_sample(e_series, spec.horizon_d)
        if len(sub_e) < MIN_N:
            # Fall back to HAC on full effect series with lag >= horizon
            hac_stat = _newey_west_overlap(e_series, lag=lag,
                                           hac_lags=max(spec.horizon_d, 4))
        else:
            hac_stat = newey_west_tstat(sub_e, lags=max(1, min(4, len(sub_e) - 1)))

        lag_stats[str(lag)] = hac_stat

        # Log primary cell
        cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "full",
            "cell_type": "primary",
        }
        cells.append(cell)

        # --- Negative-lag placebo (B4 fix): reverse z-product effect ---
        # Forward: z(x_{t-lag}) * z(y_t) — cause predicts target
        # Reverse: z(y_{t-lag}) * z(x_t) — target predicts cause (same lag)
        # If reverse |effect| >= forward |effect|, fire placebo.
        neg_lag = max(1, lag)
        placebo_neg_cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "neg_lag_placebo",
            "cell_type": "placebo",
        }
        cells.append(placebo_neg_cell)
        if len(y_shifted) >= MIN_N:
            # Reverse roles: y leads x
            y_neg_lagged = y_full[:-neg_lag]   # y at t-lag (the "cause" in reverse)
            x_neg_shifted = x_full[neg_lag:]   # x at t (the "target" in reverse)
            if len(y_neg_lagged) >= MIN_N and len(x_neg_shifted) >= MIN_N:
                min_len_neg = min(len(y_neg_lagged), len(x_neg_shifted))
                e_reverse = _effect_series(
                    y_neg_lagged[:min_len_neg], x_neg_shifted[:min_len_neg]
                )
                sub_e_neg = _non_overlapping_sample(e_reverse, spec.horizon_d)
                if len(sub_e_neg) >= MIN_N:
                    neg_stat = newey_west_tstat(
                        sub_e_neg, lags=max(1, min(4, len(sub_e_neg) - 1))
                    )
                else:
                    neg_stat = newey_west_tstat(
                        e_reverse, lags=max(spec.horizon_d, 4)
                    )
                neg_effect = neg_stat.get("mean") or 0.0
                fwd_effect = hac_stat.get("mean") or 0.0
                neg_t = neg_stat.get("t") or 0.0
                fwd_t = hac_stat.get("t") or 0.0
                # Placebo fires if reverse effect is >= forward, OR reverse is
                # significant while forward is not
                reverse_dominates = abs(neg_effect) >= abs(fwd_effect)
                reverse_sig_fwd_not = (abs(neg_t) >= 2.0 and abs(fwd_t) < 2.0)
                if reverse_dominates or reverse_sig_fwd_not:
                    concerns.append(_sanitize_text(
                        f"lag={lag}: negative-lag placebo: reverse effect "
                        f"mean={neg_effect:.3f} (t={neg_t:.2f}) >= forward effect "
                        f"mean={fwd_effect:.3f} (t={fwd_t:.2f}) — target may lead "
                        "cause (reverse-causation concern; edge not screened_candidate)"
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
        # Bootstrap the effect series e_t in date blocks (B5 fix: resample e_t,
        # never flattened rows; CI precision governed by calendar-period count)
        boot_cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "block_bootstrap",
            "cell_type": "stability",
        }
        cells.append(boot_cell)
        boot_dist = _circular_block_bootstrap_1d(
            e_series, n_draws=N_BOOTSTRAP, seed=lag + 100
        )
        boot_stats = {}
        if len(boot_dist) > 0:
            boot_stats = {
                "ci_2p5": round(float(np.percentile(boot_dist, 2.5)), 4),
                "ci_97p5": round(float(np.percentile(boot_dist, 97.5)), 4),
                "boot_mean": round(float(np.mean(boot_dist)), 4),
            }
            # Flag instability: CI spans 0 means effect is unstable across time blocks
            if boot_stats["ci_2p5"] <= 0 <= boot_stats["ci_97p5"]:
                concerns.append(_sanitize_text(
                    f"lag={lag}: bootstrap 95% CI of effect [{boot_stats['ci_2p5']}, "
                    f"{boot_stats['ci_97p5']}] spans zero — unstable"
                ))
            else:
                screened_lags.append(lag)
        else:
            screened_lags.append(lag)   # too short for bootstrap; use HAC alone

        lag_stats[f"{lag}_bootstrap"] = boot_stats

        # --- Era split statistics per lag (FIX 1 — Defect A): compute era stats
        # on the SAME lag-shifted window used for the primary HAC, not the
        # contemporaneous full series.  Called here inside the per-lag loop.
        lag_era_stats = _compute_era_stats(x_full, y_full, dates, spec.horizon_d, lag=lag)
        lag_stats[f"{lag}_era"] = lag_era_stats

        # Era divergence concern (M2 fix + FIX 2 — Defect B): compare EFFECT
        # estimates across eras using the lag-aware era stats.
        # PRIMARY trigger: block-bootstrap CI on the era-effect DIFFERENCE excludes
        # zero AND the weaker side's effect is materially smaller (|weak| < 0.5*|strong|).
        # SECONDARY (XOR) trigger: significant in one era but not the other.
        # The sign-flip trigger is unconditional (separate branch).
        _pre_era = lag_era_stats.get("pre_2010")
        _post_era = lag_era_stats.get("post_2010")
        if _pre_era is not None and _post_era is not None:
            pre_effect_lag = _pre_era.get("mean") or 0.0
            post_effect_lag = _post_era.get("mean") or 0.0
            pre_t_lag = _pre_era.get("t") or 0.0
            post_t_lag = _post_era.get("t") or 0.0
            effect_sign_flip = (pre_effect_lag * post_effect_lag < 0)
            if effect_sign_flip:
                concerns.append(_sanitize_text(
                    f"lag={lag}: era split: pre-2010 effect "
                    f"(mean={pre_effect_lag:.3f}, t={pre_t_lag:.2f}) "
                    f"and post-2010 effect (mean={post_effect_lag:.3f}, "
                    f"t={post_t_lag:.2f}) have opposite signs — "
                    "effect direction reverses across eras"
                ))
                if lag in screened_lags:
                    screened_lags.remove(lag)
            else:
                # Build per-era effect series for the difference-CI bootstrap
                # (same lag shift as primary leg)
                n_full = len(x_full)
                x_lag_era = x_full[:-lag] if lag > 0 and lag < n_full else x_full
                y_lag_era = y_full[lag:] if lag > 0 and lag < n_full else y_full
                dates_lag_era = dates[lag:] if lag > 0 and lag < n_full else dates
                era_break_ts = pd.Timestamp(ERA_BREAK)
                pre_mask_lag = dates_lag_era < era_break_ts
                post_mask_lag = dates_lag_era >= era_break_ts
                e_pre_era = _effect_series(x_lag_era[pre_mask_lag], y_lag_era[pre_mask_lag]) \
                    if pre_mask_lag.sum() >= MIN_N else np.array([])
                e_post_era = _effect_series(x_lag_era[post_mask_lag], y_lag_era[post_mask_lag]) \
                    if post_mask_lag.sum() >= MIN_N else np.array([])

                era_concern_fired = False
                if len(e_pre_era) > 0 and len(e_post_era) > 0:
                    boot_pre_era = _circular_block_bootstrap_1d(
                        e_pre_era, n_draws=N_BOOTSTRAP, seed=lag + 1000
                    )
                    boot_post_era = _circular_block_bootstrap_1d(
                        e_post_era, n_draws=N_BOOTSTRAP, seed=lag + 1100
                    )
                    if len(boot_pre_era) > 0 and len(boot_post_era) > 0:
                        era_diff_boot = boot_pre_era - boot_post_era
                        era_diff_ci_lo = float(np.percentile(era_diff_boot, 2.5))
                        era_diff_ci_hi = float(np.percentile(era_diff_boot, 97.5))
                        era_ci_excludes_zero = not (era_diff_ci_lo <= 0 <= era_diff_ci_hi)
                        # Materiality: weaker side's absolute effect < 0.5 * stronger side's
                        stronger_era = max(abs(pre_effect_lag), abs(post_effect_lag))
                        weaker_era = min(abs(pre_effect_lag), abs(post_effect_lag))
                        era_material_diff = (stronger_era > 1e-9 and
                                             weaker_era < 0.5 * stronger_era)
                        lag_stats[f"{lag}_era"]["diff_ci_2p5"] = round(era_diff_ci_lo, 5)
                        lag_stats[f"{lag}_era"]["diff_ci_97p5"] = round(era_diff_ci_hi, 5)
                        # PRIMARY trigger: difference-CI excludes zero AND material difference
                        if era_ci_excludes_zero and era_material_diff:
                            era_concern_fired = True
                            concerns.append(_sanitize_text(
                                f"lag={lag}: era split: effect concentrated in single era — "
                                f"pre-2010 (mean={pre_effect_lag:.3f}, t={pre_t_lag:.2f}), "
                                f"post-2010 (mean={post_effect_lag:.3f}, t={post_t_lag:.2f}); "
                                f"era-difference CI [{era_diff_ci_lo:.3f}, {era_diff_ci_hi:.3f}] "
                                "excludes zero (effect not invariant across eras)"
                            ))
                            if lag in screened_lags:
                                screened_lags.remove(lag)
                    # XOR as additional (non-required) trigger — fires if diff-CI unavailable
                    # or as a second signal when bootstrap is silent
                    if not era_concern_fired:
                        one_era_sig = (abs(pre_t_lag) >= 2.0) != (abs(post_t_lag) >= 2.0)
                        if one_era_sig:
                            era_concern_fired = True
                            concerns.append(_sanitize_text(
                                f"lag={lag}: era split: effect concentrated in single era — "
                                f"pre-2010 (mean={pre_effect_lag:.3f}, t={pre_t_lag:.2f}), "
                                f"post-2010 (mean={post_effect_lag:.3f}, t={post_t_lag:.2f})"
                            ))
                            if lag in screened_lags:
                                screened_lags.remove(lag)
                elif _pre_era is not None or _post_era is not None:
                    # Only one era has enough data — XOR fires by construction
                    one_era_sig = (abs(pre_t_lag) >= 2.0) != (abs(post_t_lag) >= 2.0)
                    if one_era_sig:
                        concerns.append(_sanitize_text(
                            f"lag={lag}: era split: effect concentrated in single era — "
                            f"pre-2010 (mean={pre_effect_lag:.3f}, t={pre_t_lag:.2f}), "
                            f"post-2010 (mean={post_effect_lag:.3f}, t={post_t_lag:.2f})"
                        ))
                        if lag in screened_lags:
                            screened_lags.remove(lag)

        # --- Environment invariance (B2 fix): effect estimate per split + block-bootstrap
        # CI on the DIFFERENCE of split effect-means (CHF-R5/CHF-R7) ---
        # FIX 2 (Defect B): difference-CI is PRIMARY trigger; XOR is ADDITIONAL only.
        # Threshold for materiality: |weak| < 0.5 * |strong| (documented here).
        for env_split in spec.environment_splits:
            split_key = f"{lag}_{env_split.split_id}"
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
            bool_mask = mask_aligned.astype(bool)
            bool_mask_complement = ~bool_mask

            xi_env = x_lagged[bool_mask]
            yi_env = y_shifted[bool_mask]
            xi_comp = x_lagged[bool_mask_complement]
            yi_comp = y_shifted[bool_mask_complement]

            if len(xi_env) < MIN_N or len(xi_comp) < MIN_N:
                # Not enough data in one or both splits for comparison
                continue

            # Effect estimate in each split
            e_env = _effect_series(xi_env, yi_env)
            e_comp = _effect_series(xi_comp, yi_comp)

            sub_e_env = _non_overlapping_sample(e_env, spec.horizon_d)
            sub_e_comp = _non_overlapping_sample(e_comp, spec.horizon_d)

            if len(sub_e_env) < MIN_N:
                stat_env = newey_west_tstat(e_env, lags=max(spec.horizon_d, 4))
            else:
                stat_env = newey_west_tstat(sub_e_env, lags=max(1, min(4, len(sub_e_env) - 1)))

            if len(sub_e_comp) < MIN_N:
                stat_comp = newey_west_tstat(e_comp, lags=max(spec.horizon_d, 4))
            else:
                stat_comp = newey_west_tstat(sub_e_comp, lags=max(1, min(4, len(sub_e_comp) - 1)))

            mean_env = stat_env.get("mean") or 0.0
            mean_comp = stat_comp.get("mean") or 0.0
            t_env = stat_env.get("t") or 0.0
            t_comp = stat_comp.get("t") or 0.0

            lag_stats[split_key] = {
                "split_mean_effect": round(mean_env, 5),
                "complement_mean_effect": round(mean_comp, 5),
                "split_t": round(t_env, 3),
                "complement_t": round(t_comp, 3),
            }
            splits_tested_set.add(f"{env_split.split_id}")

            # Block-bootstrap CI on the difference of split effects
            diff_obs = mean_env - mean_comp
            # Bootstrap the difference: resample e_env and e_comp independently
            boot_env = _circular_block_bootstrap_1d(e_env, n_draws=N_BOOTSTRAP, seed=lag + 600)
            boot_comp = _circular_block_bootstrap_1d(e_comp, n_draws=N_BOOTSTRAP, seed=lag + 700)
            invariance_failure = False
            if len(boot_env) > 0 and len(boot_comp) > 0:
                diff_boot = boot_env - boot_comp
                diff_ci_lo = float(np.percentile(diff_boot, 2.5))
                diff_ci_hi = float(np.percentile(diff_boot, 97.5))
                lag_stats[split_key]["diff_effect"] = round(diff_obs, 5)
                lag_stats[split_key]["diff_ci_2p5"] = round(diff_ci_lo, 5)
                lag_stats[split_key]["diff_ci_97p5"] = round(diff_ci_hi, 5)

                # FIX 2: PRIMARY trigger — difference CI excludes zero AND weaker
                # side's effect is materially smaller (|weak| < 0.5 * |strong|).
                # SECONDARY (XOR) trigger remains as additional signal.
                ci_excludes_zero = not (diff_ci_lo <= 0 <= diff_ci_hi)
                stronger = max(abs(mean_env), abs(mean_comp))
                weaker = min(abs(mean_env), abs(mean_comp))
                material_diff = (stronger > 1e-9 and weaker < 0.5 * stronger)
                one_split_sig = (abs(t_env) >= 2.0) != (abs(t_comp) >= 2.0)
                if ci_excludes_zero and (material_diff or one_split_sig):
                    invariance_failure = True
                    concerns.append(_sanitize_text(
                        f"lag={lag}, split={env_split.split_id}: "
                        f"environment invariance failure — split effect "
                        f"(mean={mean_env:.3f}, t={t_env:.2f}) materially differs "
                        f"from complement (mean={mean_comp:.3f}, t={t_comp:.2f}); "
                        f"difference CI [{diff_ci_lo:.3f}, {diff_ci_hi:.3f}] "
                        "excludes zero"
                    ))
            else:
                # No bootstrap available — use effect size heuristic
                one_split_sig = (abs(t_env) >= 2.0) != (abs(t_comp) >= 2.0)
                opposite_signs = (mean_env * mean_comp < 0)
                if one_split_sig or opposite_signs:
                    invariance_failure = True
                    concerns.append(_sanitize_text(
                        f"lag={lag}, split={env_split.split_id}: "
                        "environment invariance concern — effect differs across splits "
                        f"(split t={t_env:.2f}, complement t={t_comp:.2f})"
                    ))

            if invariance_failure and lag in screened_lags:
                screened_lags.remove(lag)

    # Era split statistics (DT-R16) — aggregate across lags for the top-level stats key.
    # Per-lag era stats are already stored as lag_stats[f"{lag}_era"] inside the loop.
    # For backward compatibility, report the era stats of the first screened lag
    # (or any lag if none screened) as stats["era_split"].
    if screened_lags:
        _representative_lag = screened_lags[0]
    elif spec.lags:
        _representative_lag = spec.lags[0]
    else:
        _representative_lag = 0
    _rep_era_key = f"{_representative_lag}_era"
    if _rep_era_key in lag_stats:
        stats["era_split"] = lag_stats[_rep_era_key]
    else:
        # Fallback: compute era stats on full (lag=0) arrays for the stats key
        stats["era_split"] = _compute_era_stats(x_full, y_full, dates, spec.horizon_d, lag=0)

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

    # Verdict synthesis — splits_tested uses the exact count of unique split keys
    splits_tested = len(splits_tested_set)
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
      5. Environment invariance (B2 fix): splits partition dates; compare
         date-aggregated cross-sectional effect within each split.
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
                "panel date span does not straddle 2010-01-01 (DT-R16)"
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

    screened_lags: list[int] = []
    lag_stats: dict = {}
    splits_tested_set: set[str] = set()

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

        # --- Block bootstrap stability (B5 fix: resample date-aggregated
        # effect series, not flattened per-(date,ticker) rows) ---
        boot_cell = {
            "edge_id": spec.edge_id, "lag": lag, "split_id": "block_bootstrap",
            "cell_type": "stability",
        }
        cells.append(boot_cell)

        # Date-aggregate the cross-sectional effect into a time series of mean corrs
        # and bootstrap THAT series (calendar-period count governs CI precision)
        lag_df["date_ts"] = pd.to_datetime(lag_df["date"])
        unique_lag_dates = np.sort(lag_df["date"].unique())
        date_effect_series = np.array([
            _mean_correlation(
                lag_df.loc[lag_df["date"] == d, "x_lag"].to_numpy(float),
                lag_df.loc[lag_df["date"] == d, "y"].to_numpy(float),
            )
            for d in unique_lag_dates
        ])

        boot_dist = _circular_block_bootstrap_1d(
            date_effect_series, n_draws=N_BOOTSTRAP, seed=lag + 500
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

        # --- Environment invariance for panel path (B2 fix) ---
        # Splits partition DATES; compare date-aggregated effect within each split
        for env_split in spec.environment_splits:
            split_key = f"{lag}_{env_split.split_id}"
            split_date_mask = environment_masks.get(env_split.split_id)
            split_cell_env = {
                "edge_id": spec.edge_id, "lag": lag,
                "split_id": env_split.split_id, "cell_type": "environment",
            }
            cells.append(split_cell_env)
            if split_date_mask is None:
                concerns.append(_sanitize_text(
                    f"lag={lag}, split={env_split.split_id}: no mask provided — "
                    "undeclared environment"
                ))
                continue

            # Map date-level mask onto the lagged rows
            # split_date_mask must be the same length as unique_dates
            unique_dates_full = np.sort(combined["date"].unique())
            if len(split_date_mask) != len(unique_dates_full):
                concerns.append(_sanitize_text(
                    f"lag={lag}, split={env_split.split_id}: mask length "
                    f"{len(split_date_mask)} != unique dates {len(unique_dates_full)}"
                ))
                continue

            split_dates_in = set(
                d for d, m in zip(unique_dates_full, split_date_mask) if m
            )
            split_dates_out = set(
                d for d, m in zip(unique_dates_full, split_date_mask) if not m
            )

            # Date-effect series for each split
            in_effect = np.array([
                _mean_correlation(
                    lag_df.loc[lag_df["date"] == d, "x_lag"].to_numpy(float),
                    lag_df.loc[lag_df["date"] == d, "y"].to_numpy(float),
                )
                for d in unique_lag_dates if d in split_dates_in
            ])
            out_effect = np.array([
                _mean_correlation(
                    lag_df.loc[lag_df["date"] == d, "x_lag"].to_numpy(float),
                    lag_df.loc[lag_df["date"] == d, "y"].to_numpy(float),
                )
                for d in unique_lag_dates if d in split_dates_out
            ])

            if len(in_effect) < MIN_N or len(out_effect) < MIN_N:
                continue

            mean_in = float(np.mean(in_effect))
            mean_out = float(np.mean(out_effect))
            stat_in = newey_west_tstat(in_effect, lags=max(1, min(4, len(in_effect) - 1)))
            stat_out = newey_west_tstat(out_effect, lags=max(1, min(4, len(out_effect) - 1)))
            t_in = stat_in.get("t") or 0.0
            t_out = stat_out.get("t") or 0.0

            lag_stats[split_key] = {
                "split_mean_effect": round(mean_in, 5),
                "complement_mean_effect": round(mean_out, 5),
                "split_t": round(t_in, 3),
                "complement_t": round(t_out, 3),
            }
            splits_tested_set.add(env_split.split_id)

            # Block-bootstrap CI on the difference (FIX 2 — Defect B):
            # PRIMARY trigger: CI excludes zero AND material effect difference
            # (|weak| < 0.5 * |strong|).  XOR (one_split_sig) is ADDITIONAL.
            boot_in = _circular_block_bootstrap_1d(in_effect, n_draws=N_BOOTSTRAP, seed=lag + 800)
            boot_out = _circular_block_bootstrap_1d(out_effect, n_draws=N_BOOTSTRAP, seed=lag + 900)
            invariance_failure = False
            if len(boot_in) > 0 and len(boot_out) > 0:
                diff_boot = boot_in - boot_out
                diff_ci_lo = float(np.percentile(diff_boot, 2.5))
                diff_ci_hi = float(np.percentile(diff_boot, 97.5))
                lag_stats[split_key]["diff_ci_2p5"] = round(diff_ci_lo, 5)
                lag_stats[split_key]["diff_ci_97p5"] = round(diff_ci_hi, 5)

                ci_excludes_zero = not (diff_ci_lo <= 0 <= diff_ci_hi)
                stronger_p = max(abs(mean_in), abs(mean_out))
                weaker_p = min(abs(mean_in), abs(mean_out))
                material_diff = (stronger_p > 1e-9 and weaker_p < 0.5 * stronger_p)
                one_split_sig = (abs(t_in) >= 2.0) != (abs(t_out) >= 2.0)
                if ci_excludes_zero and (material_diff or one_split_sig):
                    invariance_failure = True
                    concerns.append(_sanitize_text(
                        f"lag={lag}, split={env_split.split_id}: "
                        f"environment invariance failure — split effect "
                        f"(mean={mean_in:.3f}, t={t_in:.2f}) materially differs "
                        f"from complement (mean={mean_out:.3f}, t={t_out:.2f}); "
                        f"difference CI [{diff_ci_lo:.3f}, {diff_ci_hi:.3f}] "
                        "excludes zero"
                    ))
            else:
                one_split_sig = (abs(t_in) >= 2.0) != (abs(t_out) >= 2.0)
                if one_split_sig:
                    invariance_failure = True
                    concerns.append(_sanitize_text(
                        f"lag={lag}, split={env_split.split_id}: "
                        "environment invariance concern — effect differs across splits"
                    ))

            if invariance_failure and lag in screened_lags:
                screened_lags.remove(lag)

    # Log all cells
    cells_logged = 0
    if cells:
        cells_logged = log_battery_cells(FAMILY, cells, ledger)

    stats["by_lag"] = lag_stats
    stats["eff_n_months"] = eff_n_months

    splits_tested = len(splits_tested_set)
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
    has_instability = any(
        "unstable" in c or "spans zero" in c or "invariance failure" in c
        for c in concerns
    )
    has_era_concern = any(
        "era-specific" in c or "era split" in c or "concentrated in single era" in c
        or "effect concentrated" in c
        for c in concerns
    )

    if not screened_lags:
        if has_instability:
            return "unstable"
        return "null"

    if has_instability:
        return "unstable"

    # Era effect concentration or sign flip (DT-R16): → era_specific
    if has_era_concern:
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
    """Compute causal_support per lens: weak|medium|strong.

    Mapping (N1 fix): derived from the effect-series t-stats, not inflated
    permutation percentiles.

    For market_series lags: t-stat from the HAC on mean(e_t).
      t >= 3.0 -> strong, t in [2.0, 3.0) -> medium, else -> weak.
    For ticker_panel lags: perm_pctile is used as a secondary indicator but
      NOT inflated by 4x (perm_pctile is a rank, not a t-stat).
      perm_pctile >= 0.99 -> strong, >= 0.95 -> medium, else -> weak.

    Both paths: only screened lags contribute.
    """
    if not screened_lags or verdict not in ("screened_candidate", "era_specific"):
        return {"primary": "weak"}
    ts = []
    for lag in screened_lags:
        st = lag_stats.get(str(lag))
        if isinstance(st, dict):
            t = st.get("t")
            if t is not None:
                ts.append(abs(float(t)))
            # Panel path: use perm_pctile mapped to an equivalent t-range
            # perm_pctile 0.99 ~ t=2.33 (z-score), 0.999 ~ t=3.09
            # We apply a conservative mapping: 0.99 -> 2.5, never exceeds 3.5
            pctile = st.get("perm_pctile")
            if pctile is not None and t is None:
                # Convert percentile to a t-equivalent via normal quantile
                # Clamp to avoid inf: pctile in (0.5, 0.9999)
                p = max(0.5001, min(float(pctile), 0.9999))
                t_equiv = _rational_probit(p)
                ts.append(t_equiv)
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


def _rational_probit(p: float) -> float:
    """Rational approximation of the standard normal quantile (probit) for p in (0,1).

    Accurate to ~3 decimal places for p in [0.5, 0.9999].
    Used for converting perm_pctile to an effect-size-equivalent t for support mapping.
    """
    import math
    # Abramowitz & Stegun 26.2.17 approximation
    if p <= 0.5:
        return 0.0
    t = math.sqrt(-2.0 * math.log(1.0 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    num = c0 + c1 * t + c2 * t ** 2
    den = 1.0 + d1 * t + d2 * t ** 2 + d3 * t ** 3
    return t - num / den


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
    hermetic: bool = False,
) -> EdgeResult:
    """Run the full CHF-R5 battery for one EdgeSpec.

    Args:
        spec: Pre-declared edge specification.
        cause: Series (market_series path) or DataFrame (ticker_panel path).
               For ticker_panel: indexed by date, columns = tickers.
        target: Same shape as cause.
        priors: Dict matching config/causal_priors.yml schema.  If None,
                loads from root/config/causal_priors.yml (or returns {} if absent).
        root: Repo root for loading priors.
        declared_siblings: List of numpy arrays for the shared-parent check.
        environment_masks: {split_id: boolean_array} for declared splits.
        ledger: TrialLedger instance for cell logging.  When None and
                hermetic=False, raises ValueError — no default ledger path is
                assumed (M1 fix).  Pass hermetic=True to run without a ledger
                (tests and exploration only).
        hermetic: If True, allows running without a ledger (cells not logged).

    Returns:
        EdgeResult with verdict, causal_support, concerns, stats, and cell counts.

    Raises:
        ValueError: If ledger is None and hermetic is not True.
    """
    # M1 fix: refuse to run without a ledger unless explicitly hermetic
    if ledger is None and not hermetic:
        raise ValueError(
            "run_battery() requires a TrialLedger (ledger=) for cell accounting. "
            "Pass hermetic=True only for tests or exploratory use where logging "
            "is intentionally disabled. No default ledger path is assumed."
        )

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
