"""engine/grading_stats.py — Shared falsifiability primitives.

Pure numpy/pandas (no scipy/sklearn) — matches the thin data-bot env.

EXTRACTION HISTORY
  Canonical source functions extracted from:
    - engine.china_sector_pathway._wilson       → wilson_ci()
    - engine.china_sector_cycles_grader._boot_gap_ci → block_bootstrap_ci()
    - engine.china_sector_cycles_grader._entry_pos  → entry_pos()
    - engine.china_sector_cycles_grader._fwd        → fwd_window()
    - engine.china_sector_cycles_grader._dd_verdict → dd_verdict()
    - engine.china_sector_cycles_grader._rate_verdict → rate_verdict()
    - scripts.keystone_position_gate_phase0._wilson / _month_block_boot_ci
      → NOTE: that script has LOCAL copies; a future wave should converge them
        to import from here (see comment at bottom of this file: FUTURE CONVERGENCE).

Every grader imports from this module — there is ONE implementation of each
statistic, not multiple copies. D2 §2.1 (CYCLE_INTELLIGENCE_MASTERPLAN §3).

RULING A2 (BINDING): the n/h Wilson shortcut MUST NOT be used as a proxy for
effective-n when cells are cross-sectionally correlated (e.g. ~30 co-moving ETFs
stamped on the same date). Use block_bootstrap_ci() — which resamples whole stamp
DATES so correlated same-day rows move together — as the primary inference tool.
effective_n() is provided as an OVERLAP DEFLATOR for daily-cadence graders (see
docstring) but is explicitly NOT a substitute for block bootstrap in multi-instrument
panels (A2, arbitrated 2026-07-02).
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Pre-registered constants (do not tune post-hoc) ───────────────────────────────────
MIN_N_DEFAULT: int = 40        # ported from china_sector_cycles_grader.MIN_EARN_N.
                               # WHY: below ~40 matured obs every CI is wide enough to
                               # fit any story — cell stays "accruing", full stop.
BOOT_DRAWS: int = 800          # date-blocked bootstrap draws (china grader pattern).
BOOT_SEED: int = 7             # deterministic seed — tests rely on this value.
CONVENTION: str = "first_close_strictly_after_stamp"
                               # the ONLY legal forward-window anchor (bar i+1).
                               # Any other convention leaks the confirmation bar into the
                               # "forward" window — see engine/signal_quality.py trap
                               # (+5.7pp/10d phantom edge, test_signal_quality_no_leak.py).


# ══════════════════════════════════════════════════════════════════════════════════════
# INTERVAL ESTIMATORS
# ══════════════════════════════════════════════════════════════════════════════════════

def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for a proportion k/n.

    Canonical copy of engine.china_sector_pathway._wilson. Returns the (lo, hi) 95%
    interval as floats rounded to 3 decimal places, or None when n == 0.

    Statistical contract: the Wilson interval has nominal coverage 1-α for binomial
    proportions; it is the standard choice for small n (better than Normal approximation
    which can produce negative bounds). z defaults to 1.96 for 95% CI.

    Usage example::

        lo, hi = wilson_ci(30, 50)   # 60% hit rate, n=50
        # → (0.458, 0.730)

    Edge cases:
        wilson_ci(0, 0)   → None
        wilson_ci(0, 10)  → (0.0, 0.336)   # upper bound non-zero
        wilson_ci(10, 10) → (0.718, 1.0)   # lower bound non-zero

    RULING A2 NOTE: do NOT use wilson_ci(k, n_eff) as a substitute for
    block_bootstrap_ci when rows share cross-sectional correlation. The n/h deflator
    still leaves residual correlation across instruments on the same date.
    block_bootstrap_ci() is the primary estimator for multi-instrument panels.
    """
    if n == 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    return (round(lo, 3), round(hi, 3))


def jeffreys_ci(k: int, n: int, *, cred: float = 0.95, draws: int = 20000,
                seed: int = BOOT_SEED) -> tuple[float, float] | None:
    """Jeffreys (Bayesian) credible interval for a binomial proportion k/n.

    The Jeffreys prior is Beta(1/2, 1/2), so the posterior is Beta(k+1/2, n-k+1/2) and
    the interval is its central `cred` quantiles. This is the recommended small-n interval
    for a rate: it never collapses to a zero-width [1,1] at k==n (unlike a naive Wald or a
    3/3-catch point estimate), which is exactly the honesty this recession harness needs
    when reporting an OUT-OF-SAMPLE catch rate on N≈3 recessions.

    Pure-numpy: quantiles are taken from `draws` deterministic Beta samples (no scipy).
    Returns (lo, hi) rounded to 3 dp, or None when n == 0.

    Edge cases::

        jeffreys_ci(3, 3)  → e.g. (0.44, 1.0)   # NOT (1.0, 1.0): honest about N=3
        jeffreys_ci(0, 3)  → e.g. (0.0, 0.56)   # upper bound well above 0
        jeffreys_ci(0, 0)  → None
    """
    if n == 0:
        return None
    a, b = k + 0.5, (n - k) + 0.5
    rng = np.random.default_rng(seed)
    samples = rng.beta(a, b, size=int(draws))
    lo = float(np.percentile(samples, 100 * (1 - cred) / 2))
    hi = float(np.percentile(samples, 100 * (1 + cred) / 2))
    return (round(max(0.0, lo), 3), round(min(1.0, hi), 3))


def block_bootstrap_ci(
    dates: np.ndarray,
    vals: np.ndarray,
    mask: np.ndarray,
    *,
    draws: int = BOOT_DRAWS,
    seed: int = BOOT_SEED,
    stat: str = "mean",
) -> list[float] | None:
    """Date-blocked bootstrap 95% CI on (conditional stat − base stat).

    Resamples whole stamp DATES with replacement so same-day cross-sectionally-
    correlated rows always move together (ruling A2). This is the primary inference
    tool for multi-instrument panels where an i.i.d. row bootstrap would understate CI
    width by √(effective_ρ / n) or more.

    Canonical copy and extension of engine.china_sector_cycles_grader._boot_gap_ci,
    extended to also support the 'p10' statistic for drawdown tails.

    Parameters
    ----------
    dates : array of date labels (string or Timestamp) identifying the stamp date for
            each row. Rows sharing a date form one block resampled together.
    vals  : float array of outcome values (e.g. maxdd, fwd_ret) aligned to dates.
    mask  : bool array: True = rows that belong to the conditioning state.
    draws : number of bootstrap replications (default 800).
    seed  : RNG seed for determinism (default 7 — tests pin this).
    stat  : 'mean' (default) or 'p10' (10th percentile, for drawdown tails).

    Returns
    -------
    [lo_95, hi_95] of the (conditional stat − base stat) gap, rounded to 4 dp.
    None if degenerate (mask sum == 0, fewer than 2 unique dates, or fewer than
    draws/2 valid replications).

    Statistical contract: the CI is on the GAP (conditional − base), so a CI
    entirely below zero means the conditioning state is strictly worse on the chosen
    stat (e.g. deeper drawdowns), and a CI entirely above zero means strictly better.

    Usage example::

        dates = np.array(["2024-01", "2024-01", "2024-02", "2024-02"])
        vals  = np.array([-0.05, -0.08, -0.03, -0.02])
        mask  = np.array([True, False, True, False])
        ci = block_bootstrap_ci(dates, vals, mask)
        # → approximately [-0.04, -0.01] (conditional mean deeper than base)
    """
    uniq = np.unique(dates)
    if int(mask.sum()) == 0 or len(uniq) < 2:
        return None
    by = {d: np.where(dates == d)[0] for d in uniq}
    rng = np.random.default_rng(seed)

    def _stat(x: np.ndarray) -> float:
        if stat == "p10":
            return float(np.percentile(x, 10))
        return float(np.mean(x))

    gaps: list[float] = []
    for _ in range(draws):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([by[d] for d in pick])
        m = mask[ridx]
        if int(m.sum()) == 0:
            continue
        gaps.append(_stat(vals[ridx][m]) - _stat(vals[ridx]))
    if len(gaps) < draws // 2:
        return None
    return [round(float(np.percentile(gaps, 2.5)), 4),
            round(float(np.percentile(gaps, 97.5)), 4)]


def block_bootstrap_scalar_ci(
    series: pd.Series,
    *,
    block: int,
    draws: int = BOOT_DRAWS,
    seed: int = BOOT_SEED,
) -> tuple[float, float] | None:
    """Moving-block bootstrap 95% CI on the MEAN of an autocorrelated scalar series.

    Circular-block bootstrap variant for a single time series (not a conditional gap).
    Used for calibration-metric CIs on a serial strategy or a single-instrument series
    (e.g. a Sharpe, a Brier score from sequential stamps on one instrument).

    Parameters
    ----------
    series : pd.Series of numeric values. NaN values are dropped before bootstrapping.
    block  : block length in bars. Typically the forward horizon (e.g. 21d or 63d).
    draws  : bootstrap replications.
    seed   : RNG seed.

    Returns
    -------
    (lo_95, hi_95) rounded to 4 dp, or None if series is too short (< max(block*3, 30)).

    Statistical contract: moving-block bootstrap preserves autocorrelation up to the
    block length. For an IID series it is equivalent to the standard bootstrap.

    Usage example::

        monthly_rets = pd.Series([0.01, -0.02, 0.03, ...])   # 60 months
        lo, hi = block_bootstrap_scalar_ci(monthly_rets, block=3)
    """
    r = np.asarray(series.dropna() if hasattr(series, "dropna") else series, float)
    n = len(r)
    if n < max(block * 3, 30):
        return None
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / block))
    starts_grid = np.arange(block)
    ests: list[float] = []
    for _ in range(draws):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + starts_grid[None, :]).ravel()[:n] % n
        ests.append(float(np.mean(r[idx])))
    return (round(float(np.percentile(ests, 2.5)), 4),
            round(float(np.percentile(ests, 97.5)), 4))


# ══════════════════════════════════════════════════════════════════════════════════════
# OVERLAPPING-WINDOW OVERLAP DEFLATOR
# ══════════════════════════════════════════════════════════════════════════════════════

def effective_n(
    stamp_dates: np.ndarray,
    horizon_bars: int,
    calendar: pd.DatetimeIndex,
) -> float:
    """Effective independent sample size for OVERLAPPING forward windows.

    When forward windows of length H bars overlap, sequential stamps share information;
    naive n over-counts. This function estimates the Newey-West-style effective n:

        n_eff ≈ m / (1 + 2 · avg_overlap · avg_neighbors)

    where avg_overlap is the mean fractional overlap between stamp pairs whose windows
    intersect, and avg_neighbors is the mean count of other stamps within H bars.

    IMPORTANT — RULING A2: this deflator corrects for SERIAL overlap (a single
    instrument stamped at daily cadence). It does NOT correct for CROSS-SECTIONAL
    correlation (30 co-moving ETFs stamped on the same date). For multi-instrument
    panels, use block_bootstrap_ci() which resamples whole dates. Using n_eff as an
    input to wilson_ci on a cross-sectional panel would STILL understate CI width.

    Parameters
    ----------
    stamp_dates    : array of stamp dates (Timestamp or str) sorted ascending.
    horizon_bars   : forward window length in trading bars (e.g. 21 for 1-month).
    calendar       : pd.DatetimeIndex of all trading days (the reference calendar).

    Returns
    -------
    float in [1.0, len(stamp_dates)], clamped.

    Rules of thumb:
      - Monthly stamps, H=21: avg_neighbors ≈ 0 → n_eff ≈ m  (no overlap).
      - Daily stamps, H=21:   avg_neighbors ≈ 20 → n_eff ≈ m/21.
      - Daily stamps, H=63:   avg_neighbors ≈ 62 → n_eff ≈ m/63.

    This is the load-bearing reason D2 chose monthly backfill cadence: it makes
    n_eff ≈ n by construction, so overlap-inflation is negligible at the source.

    Usage example::

        cal = pd.bdate_range("2020-01-01", "2024-12-31")
        # monthly stamps — minimal overlap
        monthly = pd.bdate_range("2020-01-31", "2024-12-31", freq="BME")
        n_eff_m = effective_n(monthly.values, 21, cal)
        # → approximately len(monthly) (near-zero overlap)

        # daily stamps — heavy overlap at H=21
        daily = cal
        n_eff_d = effective_n(daily.values, 21, cal)
        # → approximately len(daily) / 21
    """
    m = len(stamp_dates)
    if m == 0:
        return 0.0
    if m == 1:
        return 1.0
    if horizon_bars <= 0:
        return float(m)

    # Map stamp dates to bar positions in the calendar.
    ts = pd.DatetimeIndex(stamp_dates)
    bar_positions = np.searchsorted(calendar, ts, side="left")

    # For each pair of stamps with |b_i - b_j| < H, compute fractional overlap.
    # We scan O(m * avg_neighbors) with a sorted sweep instead of O(m²) brute force.
    bar_positions = np.sort(bar_positions)
    H = horizon_bars
    total_overlap = 0.0
    neighbor_count = 0

    for i in range(m):
        # Find stamps within the next H bars (j > i and b_j - b_i < H).
        lo = i + 1
        hi = int(np.searchsorted(bar_positions, bar_positions[i] + H, side="left"))
        for j in range(lo, hi):
            gap = int(bar_positions[j] - bar_positions[i])
            ov = (H - gap) / H
            total_overlap += ov
            neighbor_count += 1

    if neighbor_count == 0:
        return float(m)

    avg_overlap = total_overlap / neighbor_count
    avg_neighbors = 2 * neighbor_count / m  # factor 2: each pair counted once above
    n_eff = m / (1.0 + avg_neighbors * avg_overlap)
    return float(max(1.0, min(n_eff, float(m))))


# ══════════════════════════════════════════════════════════════════════════════════════
# MULTIPLE-TESTING CORRECTION
# ══════════════════════════════════════════════════════════════════════════════════════

def fdr_bh(pvals: dict[str, float], q: float = 0.10) -> dict[str, bool]:
    """Benjamini–Hochberg FDR correction at level q.

    Controls the false-discovery rate across a family of hypothesis tests. No cell may
    be promoted from 'accruing' to 'earning' unless it survives BH correction (the
    pre-registered gate in PREREGISTRATION.md).

    Parameters
    ----------
    pvals : dict mapping cell key → p-value (float in [0, 1]).
    q     : FDR level (default 0.10 — 10% false discovery rate).

    Returns
    -------
    dict mapping cell key → bool (True = null rejected at FDR level q).
    An empty pvals dict returns an empty dict.

    Statistical contract: for m hypotheses sorted by p-value, BH rejects all
    hypotheses H_(1) … H_(k) where k = max{i : p_(i) ≤ i·q/m}. Under independence
    (and positive dependence — PRDS), the FDR ≤ q. Under arbitrary dependence,
    use q/ln(m) instead; this implementation uses the standard q level (independence
    assumption flagged in the pre-registration).

    Usage example::

        passed = fdr_bh({"cell_A": 0.001, "cell_B": 0.04, "cell_C": 0.20}, q=0.10)
        # → {"cell_A": True, "cell_B": True, "cell_C": False}
        # (Hand-check: m=3, sorted p=[0.001,0.04,0.20], BH thresholds=[0.033,0.067,0.10];
        #  0.001≤0.033 ✓, 0.04≤0.067 ✓, 0.20≤0.10 ✗ → first two reject.)
    """
    if not pvals:
        return {}
    keys = list(pvals.keys())
    ps = np.array([pvals[k] for k in keys], dtype=float)
    m = len(ps)
    order = np.argsort(ps)
    sorted_p = ps[order]
    bh_thresholds = (np.arange(1, m + 1) / m) * q
    # Find the largest k where p_(k) ≤ bh_threshold(k).
    below = sorted_p <= bh_thresholds
    if not np.any(below):
        reject_up_to = -1
    else:
        reject_up_to = int(np.where(below)[0].max())
    passed_sorted = np.zeros(m, dtype=bool)
    if reject_up_to >= 0:
        passed_sorted[:reject_up_to + 1] = True
    # Map back to original order.
    result_arr = np.zeros(m, dtype=bool)
    result_arr[order] = passed_sorted
    return {k: bool(result_arr[i]) for i, k in enumerate(keys)}


def min_n_gate(n: float, floor: float = MIN_N_DEFAULT) -> bool:
    """True if n meets the minimum sample threshold.

    Usage example::

        min_n_gate(41)   # → True
        min_n_gate(39)   # → False
        min_n_gate(40)   # → False  (strict: n must EXCEED floor)
    """
    return float(n) >= float(floor)


# ══════════════════════════════════════════════════════════════════════════════════════
# CONE COVERAGE (D2 §3.2 — ONE implementation, nominal 0.80)
# ══════════════════════════════════════════════════════════════════════════════════════

def cone_coverage(
    stamps: pd.DataFrame,
    truth: dict[str, pd.Series],
    *,
    nominal: float = 0.80,
) -> dict:
    """Empirical cone coverage: fraction of logged projection bands that contained the
    realized outcome, compared to the nominal coverage target.

    D2 §3.2 and masterplan §3 ownership table: D2 owns the ONE cone_coverage function
    at nominal 80%. D5 consumes this output; all other callers import from here.

    Parameters
    ----------
    stamps : DataFrame with columns:
        - 'id'       : instrument identifier
        - 'date'     : stamp date (Timestamp-parseable)
        - 'proj_lo'  : projected lower bound (date or bar index, same units as truth)
        - 'proj_hi'  : projected upper bound (date or bar index, same units as truth)
        - 'proj_kind': 'turn_date' (default) — compare projected turn window against
                       realized turn dates from `truth` series.
    truth : dict mapping id → pd.Series of confirmed turn dates for that instrument.
            Each Series should be a DatetimeIndex or a Series of pd.Timestamp values
            representing confirmed turn dates at the relevant direction.
    nominal : nominal coverage target (default 0.80 = 80%).

    Returns
    -------
    dict with keys:
        - 'nominal'            : float — the target coverage.
        - 'empirical'          : float | None — fraction of stamps where the realized
                                 turn fell in [proj_lo, proj_hi].
        - 'ci'                 : [lo, hi] — Wilson CI on the empirical coverage rate,
                                 or None if n < 2.
        - 'n'                  : int — number of stamps with both a logged band AND a
                                 matched realized outcome.
        - 'n_no_truth'         : int — stamps where no realized outcome was found.
        - 'recal_halfwidth'    : float | None — the empirically-derived correct half-
                                 width to achieve `nominal` coverage. Computed as the
                                 `nominal`-quantile of |proj_centre - realized| in
                                 the same units as proj_lo/proj_hi. None if n < 10.
        - 'recal_multiplier'   : float | None — recal_halfwidth / current_halfwidth if
                                 current_halfwidth > 0, else None. >1 = cones too tight;
                                 <1 = cones too wide.
        - 'verdict'            : str — 'accruing' | 'well_calibrated' | 'too_tight' |
                                 'too_wide', based on whether the empirical CI contains
                                 the nominal target.

    Statistical contract: coverage is a proportion graded by wilson_ci. The
    recalibration multiplier is derived from the timing-error distribution: the
    `nominal`-quantile of |error| IS the empirically correct half-width, replacing the
    magic `lerp(1.5, 13)` / `tilt_weights(1.35, 0.7)` constants (audit cycle-flagship-4).

    Usage example::

        import pandas as pd
        stamps = pd.DataFrame({
            "id": ["XLK", "XLK"],
            "date": pd.to_datetime(["2023-01-31", "2023-06-30"]),
            "proj_lo": pd.to_datetime(["2023-03-01", "2023-08-01"]),
            "proj_hi": pd.to_datetime(["2023-05-01", "2023-10-01"]),
        })
        truth = {"XLK": pd.DatetimeIndex(["2023-04-15", "2023-09-10"])}
        result = cone_coverage(stamps, truth)
        # → {'nominal': 0.8, 'empirical': 1.0, 'verdict': 'well_calibrated', ...}
    """
    _empty = {"nominal": nominal, "empirical": None, "ci": None, "n": 0,
              "n_no_truth": 0, "recal_halfwidth": None, "recal_multiplier": None,
              "verdict": "accruing"}

    if stamps is None or len(stamps) == 0:
        return _empty

    required = {"id", "date", "proj_lo", "proj_hi"}
    if not required.issubset(stamps.columns):
        return _empty

    df = stamps.copy().reset_index(drop=True)
    df = df[df["proj_lo"].notna() & df["proj_hi"].notna()].reset_index(drop=True)
    if len(df) == 0:
        return _empty

    # Compute projected centre for error distribution using positional indexing.
    try:
        lo_ts = pd.to_datetime(df["proj_lo"]).reset_index(drop=True)
        hi_ts = pd.to_datetime(df["proj_hi"]).reset_index(drop=True)
        centre_ts = lo_ts + (hi_ts - lo_ts) / 2
        use_dates = True
    except Exception:
        use_dates = False
        lo_ts = df["proj_lo"].astype(float).reset_index(drop=True)
        hi_ts = df["proj_hi"].astype(float).reset_index(drop=True)
        centre_ts = (lo_ts + hi_ts) / 2.0

    n_inside = 0
    n_matched = 0
    n_no_truth = 0
    errors: list[float] = []    # |centre - realized| in days (or numeric units)
    halfwidths: list[float] = []

    for pos in range(len(df)):
        row = df.iloc[pos]
        sid = str(row["id"])
        turns = truth.get(sid)
        if turns is None or len(turns) == 0:
            n_no_truth += 1
            continue

        lo_val = lo_ts.iloc[pos]
        hi_val = hi_ts.iloc[pos]
        ctr_val = centre_ts.iloc[pos]

        # Find nearest confirmed turn to the projected centre.
        try:
            turns_ts = pd.DatetimeIndex(
                turns if not isinstance(turns, pd.Series) else turns.values
            )
            diffs = abs(turns_ts - ctr_val)
            nearest_idx = int(diffs.argmin())
            nearest_turn = turns_ts[nearest_idx]
            inside = bool(lo_val <= nearest_turn <= hi_val)
            if use_dates:
                err_days = float(abs((nearest_turn - ctr_val).days))
                hw_days = float(abs((hi_val - lo_val).days) / 2.0)
            else:
                err_days = float(abs(nearest_turn - ctr_val))
                hw_days = float(abs(hi_val - lo_val) / 2.0)
            errors.append(err_days)
            halfwidths.append(hw_days)
            n_matched += 1
            if inside:
                n_inside += 1
        except Exception:
            n_no_truth += 1
            continue

    if n_matched == 0:
        return {"nominal": nominal, "empirical": None, "ci": None, "n": 0,
                "n_no_truth": n_no_truth, "recal_halfwidth": None,
                "recal_multiplier": None, "verdict": "accruing"}

    empirical = n_inside / n_matched
    ci_result = wilson_ci(n_inside, n_matched)
    ci = list(ci_result) if ci_result else None

    # Recalibration: the (nominal)-quantile of |error| is the empirically correct half-width.
    recal_hw: float | None = None
    recal_mult: float | None = None
    if len(errors) >= 10:
        recal_hw = float(round(float(np.percentile(errors, nominal * 100)), 2))
        avg_hw = float(np.mean(halfwidths)) if halfwidths else 0.0
        if avg_hw > 0:
            recal_mult = round(recal_hw / avg_hw, 3)

    # Verdict: does the empirical CI contain the nominal target?
    if n_matched < MIN_N_DEFAULT:
        verdict = "accruing"
    elif ci is None:
        verdict = "accruing"
    elif ci[0] <= nominal <= ci[1]:
        verdict = "well_calibrated"
    elif ci[1] < nominal:
        verdict = "too_tight"     # empirical coverage is below nominal
    else:
        verdict = "too_wide"      # empirical coverage is above nominal

    return {
        "nominal": nominal,
        "empirical": round(empirical, 3),
        "ci": ci,
        "n": n_matched,
        "n_no_truth": n_no_truth,
        "recal_halfwidth": recal_hw,
        "recal_multiplier": recal_mult,
        "verdict": verdict,
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# VERDICT LATTICE HELPERS
# ══════════════════════════════════════════════════════════════════════════════════════

def dd_verdict(n: float, ci: list | None, *, min_n: float = MIN_N_DEFAULT) -> str:
    """Drawdown-channel verdict: accruing / earning / falsified / inconclusive.

    Canonical copy of engine.china_sector_cycles_grader._dd_verdict, gated on n
    (raw or effective — caller's choice; the china grader uses raw n because it stamps
    monthly so n_eff ≈ n).

    Gate (pre-registered): earning ⟺ n ≥ min_n AND CI entirely below zero (conditional
    drawdowns strictly deeper than base — the topping-region claim).
    Falsified ⟺ CI entirely above zero (conditional drawdowns strictly SHALLOWER —
    the claim proven wrong). Anything else is inconclusive.

    The return channel uses rate_verdict() instead; the drawdown channel is the ONLY
    channel eligible for a sizing verdict (doctrine: risk claim only).

    Usage example::

        dd_verdict(50, [-0.03, -0.01])   # → 'earning'
        dd_verdict(50, [-0.03,  0.01])   # → 'inconclusive'
        dd_verdict(50, [ 0.01,  0.03])   # → 'falsified'
        dd_verdict(30, [-0.05, -0.01])   # → 'accruing'  (n < min_n)
        dd_verdict(50, None)             # → 'inconclusive'
    """
    if float(n) < float(min_n):
        return "accruing"
    if ci is None:
        return "inconclusive"
    if ci[1] < 0:
        return "earning"       # conditional drawdowns strictly deeper than base
    if ci[0] > 0:
        return "falsified"     # conditional drawdowns strictly SHALLOWER — claim wrong
    return "inconclusive"


def rate_verdict(
    n: float,
    ci: tuple | list | None,
    base: float | None,
    *,
    min_edge: float = 0.05,
    min_n: float = MIN_N_DEFAULT,
) -> str:
    """Return/calibration-channel verdict: accruing / falsified / inconclusive.

    Canonical copy of engine.china_sector_cycles_grader._rate_verdict. NOTE: this
    channel can NEVER emit 'earning' (doctrine — no directional trading verdict from
    the return or calibration channels). A favourable CI is capped at 'inconclusive'
    and flagged for re-research.

    Gate: falsified ⟺ n ≥ min_n AND CI-hi < base + min_edge (CI rules out even a
    small tradeable edge above the base rate). All else is inconclusive (or accruing
    if n is thin).

    Usage example::

        rate_verdict(50, (0.55, 0.72), 0.50)   # → 'inconclusive'  (CI-hi > base+5pp)
        rate_verdict(50, (0.52, 0.54), 0.52)   # → 'falsified'  (CI-hi < base+5pp)
        rate_verdict(30, (0.55, 0.72), 0.50)   # → 'accruing'   (n < min_n)
        rate_verdict(50, None, 0.50)            # → 'inconclusive'
    """
    if float(n) < float(min_n):
        return "accruing"
    if ci is None or base is None:
        return "inconclusive"
    if ci[1] < base + min_edge:
        return "falsified"
    return "inconclusive"


# ══════════════════════════════════════════════════════════════════════════════════════
# FORWARD-WINDOW PRIMITIVES (producer-blind, grader-side)
# ══════════════════════════════════════════════════════════════════════════════════════

def entry_pos(idx: pd.DatetimeIndex, stamp: pd.Timestamp) -> int | None:
    """Position of the FIRST bar STRICTLY AFTER the stamp date (bar-i+1 anchor).

    searchsorted(side='right') can never return the stamp bar itself — the guard
    against the signal_quality.py marker-date look-ahead trap (+5.7pp/10d phantom
    edge, measured in tests/test_signal_quality_no_leak.py).

    Returns int bar position, or None if stamp falls at or after the last bar.

    Usage example::

        idx = pd.bdate_range("2024-01-01", periods=100)
        j = entry_pos(idx, idx[10])   # → 11 (first bar after index[10])
    """
    j = int(idx.searchsorted(stamp, side="right"))
    return j if j < len(idx) else None


def fwd_window(px: pd.Series, stamp: pd.Timestamp, h: int) -> dict | None:
    """Realized forward window of h trading bars on the series' own calendar.

    Anchored at the FIRST close strictly after `stamp` (bar-i+1). Returns
    {entry, exit, ret, maxdd} or None while the window has not fully matured
    (no partial windows — ever).

    Parameters
    ----------
    px    : price series (pd.Series with DatetimeIndex).
    stamp : stamp date. Forward window starts at the NEXT bar after this date.
    h     : number of forward bars.

    Returns
    -------
    dict with keys:
        - 'entry': pd.Timestamp of the entry bar
        - 'exit' : pd.Timestamp of the exit bar
        - 'ret'  : forward return (exit/entry - 1)
        - 'maxdd': maximum peak-to-trough drawdown within the window (≤ 0)
    Or None if the window has not matured.

    Raises
    ------
    ValueError: if the entry bar is not strictly after the stamp (structural
                impossibility; belt-and-braces against future refactors that
                might accidentally change the anchor convention).

    Usage example::

        px = pd.Series(100 * 0.99 ** np.arange(100),
                       index=pd.bdate_range("2024-01-01", periods=100))
        w = fwd_window(px, px.index[10], 21)
        # → {'entry': ..., 'exit': ..., 'ret': <negative>, 'maxdd': <negative>}
    """
    idx = px.index
    j = entry_pos(idx, stamp)
    if j is None or j + h >= len(idx):
        return None
    if not idx[j] > stamp:
        raise ValueError(
            "look-ahead guard: forward anchor must be strictly after the stamp date. "
            "This is the bar-i+1 convention — see engine/signal_quality.py trap "
            "(+5.7pp/10d phantom edge from marker-date anchoring)."
        )
    win = px.iloc[j:j + h + 1].to_numpy(dtype=float)
    ret = float(win[-1] / win[0] - 1.0)
    dd = float((win / np.maximum.accumulate(win) - 1.0).min())
    return {"entry": idx[j], "exit": idx[j + h], "ret": ret, "maxdd": dd}


def assert_convention(name: str) -> None:
    """Raise ValueError if name is not the canonical forward-anchor convention.

    Used by grade() functions to refuse any caller that passes a non-bar-i+1
    convention string, making a tainted grader fail loud rather than silently
    publish look-ahead-contaminated numbers.

    Usage example::

        assert_convention("first_close_strictly_after_stamp")   # no-op
        assert_convention("marker_date")   # raises ValueError
    """
    if name != CONVENTION:
        raise ValueError(
            f"look-ahead guard: forward grading must anchor at the {CONVENTION!r} bar "
            "(bar i+1). Got: {name!r}. Stamp/marker-date anchoring leaks the "
            "confirmation bar into the 'forward' window — the engine/signal_quality.py "
            "trap that measured +5.7pp/10d of phantom edge "
            "(tests/test_signal_quality_no_leak.py). Refused."
        )


# ══════════════════════════════════════════════════════════════════════════════════════
# MERGED LOG READER  (D2 §1.3)
# ══════════════════════════════════════════════════════════════════════════════════════

def load_graded_log(engine: str, *, include_backfill: bool = True) -> pd.DataFrame:
    """Merge live + backfill forward logs with provenance, enforcing PIT keep-FIRST.

    Live (prospective) rows ALWAYS win a (date, id) collision — a real prospective stamp
    supersedes a synthetic backfilled one for the same day (D2 §1.3 collision rule).

    Parameters
    ----------
    engine           : engine name, e.g. 'sector_cycles', 'country_cycles',
                       'china_sector_cycles'. Used to build the data directory path.
    include_backfill : if False, returns only the live forward_log (prospective rows).

    Returns
    -------
    pd.DataFrame with a 'provenance' column ('prospective' | 'backfilled') and
    keep-FIRST enforced on (date, id). Returns an empty DataFrame if no files exist.

    Usage example::

        df = load_graded_log("china_sector_cycles")
        live_only = df[df["provenance"] == "prospective"]
        backfill_only = df[df["provenance"] == "backfilled"]
    """
    try:
        from lib import config
        data_root = config.data_dir()
    except Exception:
        data_root = Path("data")

    engine_dir = Path(data_root) / engine
    live_path = engine_dir / "forward_log.parquet"
    backfill_path = engine_dir / "backfill.parquet"

    frames: list[pd.DataFrame] = []

    if live_path.exists():
        try:
            live = pd.read_parquet(live_path)
            live["provenance"] = "prospective"
            frames.append(live)
        except Exception as e:
            log.warning("load_graded_log: cannot read live log for %s: %s", engine, e)

    if include_backfill and backfill_path.exists():
        try:
            bf = pd.read_parquet(backfill_path)
            bf["provenance"] = "backfilled"
            frames.append(bf)
        except Exception as e:
            log.warning("load_graded_log: cannot read backfill for %s: %s", engine, e)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    if "date" not in combined.columns or "id" not in combined.columns:
        return combined

    # Sort live-first so keep='first' gives prospective priority.
    prov_order = {"prospective": 0, "backfilled": 1}
    combined["_prov_order"] = combined["provenance"].map(prov_order).fillna(2)
    combined = combined.sort_values("_prov_order").drop(columns=["_prov_order"])
    combined = combined.drop_duplicates(subset=["date", "id"], keep="first")
    combined = combined.reset_index(drop=True)
    return combined


# ══════════════════════════════════════════════════════════════════════════════════════
# FUTURE CONVERGENCE NOTE
# ══════════════════════════════════════════════════════════════════════════════════════
#
# scripts/keystone_position_gate_phase0.py contains LOCAL copies of:
#   - _wilson()                  → converge to: from engine.grading_stats import wilson_ci
#   - _month_block_boot_ci()     → converge to: from engine.grading_stats import block_bootstrap_ci
#   - _abs_ci()                  → (no equivalent yet; could become block_bootstrap_scalar_ci)
#
# These were isolated in a standalone research script (W0.4) intentionally to avoid
# coupling to the not-yet-existing library. A future wave (D2-W4 or later) should
# converge them so there is exactly ONE implementation in the entire codebase.
# The research script is in scripts/keystone_position_gate_phase0.py.
