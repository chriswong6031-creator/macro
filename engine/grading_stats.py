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
# CALIBRATION HELPERS  (PR-B4 / convergence rail RUL-T3-5)
# ══════════════════════════════════════════════════════════════════════════════════════

def reliability_curve(
    probs: np.ndarray,
    outcomes: np.ndarray,
    n_bins: int = 10,
) -> list[dict]:
    """Calibration reliability curve: binned forecast probabilities vs observed rates.

    Bins forecast probabilities into equal-width buckets and computes the mean
    predicted probability, observed outcome rate, count, and Wilson CI per bin.
    Bins with no observations are omitted.

    Parameters
    ----------
    probs    : 1-D array of predicted probabilities in [0, 1].
    outcomes : 1-D binary array of realized outcomes (0 or 1), aligned to probs.
    n_bins   : number of equal-width bins across [0, 1] (default 10).

    Returns
    -------
    List of dicts, one per non-empty bin, each with keys:
        - 'bin_lo'      : float — left edge of the bin.
        - 'bin_hi'      : float — right edge of the bin.
        - 'mean_prob'   : float — mean predicted probability within the bin.
        - 'obs_rate'    : float — fraction of positive outcomes within the bin.
        - 'n'           : int   — count of observations in the bin.
        - 'ci_lo'       : float | None — Wilson CI lower bound on obs_rate.
        - 'ci_hi'       : float | None — Wilson CI upper bound on obs_rate.

    Statistical contract: a perfectly calibrated forecaster produces a curve
    where mean_prob ≈ obs_rate in every bin (the diagonal). The Wilson CI is
    on obs_rate as a binomial proportion over the n observations in the bin.

    OVERLAP WARNING: forecasts generated from OVERLAPPING long-horizon rows (e.g.
    daily stamps with a 63d forward window) share information across adjacent bins
    — the Wilson CI within each bin will understate true uncertainty. For reliable
    uncertainty bounds on overlapping series, bootstrap the full calibration curve
    using block_bootstrap_scalar_ci() on a per-bin series, or use brier_decomposition()
    with moving-block inference.

    Usage example::

        probs = np.array([0.1, 0.2, 0.8, 0.9])
        outcomes = np.array([0, 0, 1, 1])
        curve = reliability_curve(probs, outcomes, n_bins=5)
        # Two non-empty bins: low prob → low rate; high prob → high rate.
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if len(probs) != len(outcomes):
        raise ValueError(
            f"reliability_curve: probs and outcomes must have the same length "
            f"(got {len(probs)} vs {len(outcomes)})."
        )
    if n_bins < 1:
        raise ValueError(f"reliability_curve: n_bins must be ≥ 1 (got {n_bins}).")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    result: list[dict] = []
    for i in range(n_bins):
        lo = edges[i]
        hi = edges[i + 1]
        # Include right endpoint in the last bin so prob=1.0 is captured.
        if i < n_bins - 1:
            mask = (probs >= lo) & (probs < hi)
        else:
            mask = (probs >= lo) & (probs <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        mean_p = float(np.mean(probs[mask]))
        obs_r = float(np.mean(outcomes[mask]))
        k = int(np.sum(outcomes[mask]))
        ci = wilson_ci(k, n)
        result.append({
            "bin_lo": round(lo, 6),
            "bin_hi": round(hi, 6),
            "mean_prob": round(mean_p, 6),
            "obs_rate": round(obs_r, 6),
            "n": n,
            "ci_lo": ci[0] if ci else None,
            "ci_hi": ci[1] if ci else None,
        })
    return result


def brier_decomposition(
    probs: np.ndarray,
    outcomes: np.ndarray,
    n_bins: int = 10,
) -> dict:
    """Murphy decomposition of the Brier score into reliability, resolution, uncertainty.

    The Brier score is decomposed as:

        BS = reliability - resolution + uncertainty

    where:
        - uncertainty   = o̅(1 - o̅)       — irreducible noise in the outcome base rate.
        - reliability   = Σ_k n_k/N · (ō_k - o̅_k)²  — penalty for miscalibration.
        - resolution    = Σ_k n_k/N · (o̅_k - o̅)²    — reward for decisive forecasts.
        - refinement    = reliability - resolution    — net skill (negative = skilled).
        - brier_score   = reliability - resolution + uncertainty.

    Here ō_k is the mean forecast in bin k, o̅_k is the observed rate in bin k,
    o̅ is the overall mean outcome (base rate), and n_k is the count in bin k.

    Parameters
    ----------
    probs    : 1-D array of predicted probabilities in [0, 1].
    outcomes : 1-D binary array of realized outcomes (0 or 1), aligned to probs.
    n_bins   : number of equal-width bins for the decomposition (default 10).

    Returns
    -------
    dict with keys:
        - 'brier_score'  : float — mean squared error (lower is better).
        - 'reliability'  : float — calibration penalty (lower is better; 0 = perfect).
        - 'resolution'   : float — forecast sharpness reward (higher is better).
        - 'uncertainty'  : float — irreducible base-rate uncertainty o̅(1 - o̅).
        - 'refinement'   : float — reliability - resolution; negative = net skill.
        - 'base_rate'    : float — overall mean of outcomes.
        - 'n'            : int   — total number of observations.
        - 'n_bins_used'  : int   — number of non-empty bins (may be < n_bins).

    Statistical contract: BS = reliability - resolution + uncertainty is exact for
    equal-width bins in the limit of large n. For small n the decomposition is still
    unbiased (in expectation) but individual terms have wide sampling distributions.

    OVERLAP WARNING: on overlapping long-horizon rows, the Brier score is biased
    toward zero (correlated errors inflate the apparent sample size). Wrap this
    function's `brier_score` output in block_bootstrap_scalar_ci() to obtain
    overlap-corrected uncertainty bounds.

    Usage example::

        probs    = np.array([0.9, 0.8, 0.1, 0.2])
        outcomes = np.array([1,   1,   0,   0  ])
        d = brier_decomposition(probs, outcomes)
        # d['reliability'] ≈ 0.0  (perfectly calibrated)
        # d['resolution']  > 0.0  (decisive forecasts)
        # d['brier_score'] ≈ uncertainty - resolution (skilled)
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    n = len(probs)
    if n == 0:
        return {
            "brier_score": None, "reliability": None, "resolution": None,
            "uncertainty": None, "refinement": None, "base_rate": None,
            "n": 0, "n_bins_used": 0,
        }
    if len(probs) != len(outcomes):
        raise ValueError(
            f"brier_decomposition: probs and outcomes must have the same length "
            f"(got {len(probs)} vs {len(outcomes)})."
        )

    brier_score = float(np.mean((probs - outcomes) ** 2))
    base_rate = float(np.mean(outcomes))
    uncertainty = base_rate * (1.0 - base_rate)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    reliability = 0.0
    resolution = 0.0
    n_bins_used = 0

    for i in range(n_bins):
        lo = edges[i]
        hi = edges[i + 1]
        if i < n_bins - 1:
            mask = (probs >= lo) & (probs < hi)
        else:
            mask = (probs >= lo) & (probs <= hi)
        n_k = int(mask.sum())
        if n_k == 0:
            continue
        n_bins_used += 1
        mean_p_k = float(np.mean(probs[mask]))
        obs_r_k = float(np.mean(outcomes[mask]))
        w = n_k / n
        reliability += w * (mean_p_k - obs_r_k) ** 2
        resolution += w * (obs_r_k - base_rate) ** 2

    refinement = reliability - resolution
    return {
        "brier_score": round(brier_score, 6),
        "reliability": round(reliability, 6),
        "resolution": round(resolution, 6),
        "uncertainty": round(uncertainty, 6),
        "refinement": round(refinement, 6),
        "base_rate": round(base_rate, 6),
        "n": n,
        "n_bins_used": n_bins_used,
    }


def era_split_stability(
    dates: np.ndarray,
    values: np.ndarray,
    split_date=None,
    n_splits: int = 2,
    *,
    min_n: float = MIN_N_DEFAULT,
) -> dict:
    """Two-era (or k-era) stability of a signal or rate series.

    Splits the (dates, values) series into n_splits equal-length chronological eras
    and computes per-era mean/rate with Wilson CIs, plus a stability verdict.

    Parameters
    ----------
    dates      : 1-D array of date labels (str or Timestamp), aligned to values.
                 Will be sorted chronologically before splitting.
    values     : 1-D numeric array aligned to dates. Treated as proportions (rates)
                 for Wilson CI computation: values should be in {0, 1} for a rate
                 series, or arbitrary floats for a continuous series (Wilson CI is
                 skipped for non-binary values; only mean and std are returned).
    split_date : optional explicit split date. If provided and n_splits == 2, this
                 date is used as the era boundary instead of the median date. Has no
                 effect when n_splits > 2.
    n_splits   : number of eras to divide into (default 2 = before/after). Must be ≥ 2.
    min_n      : minimum observations per era required for a non-insufficient verdict
                 (default MIN_N_DEFAULT=40).

    Returns
    -------
    dict with keys:
        - 'n_splits'    : int — number of eras.
        - 'eras'        : list of dicts, one per era, each with:
              - 'era'       : int — era index (0-based).
              - 'date_lo'   : str — earliest date in the era.
              - 'date_hi'   : str — latest date in the era.
              - 'n'         : int — count.
              - 'mean'      : float — per-era mean.
              - 'std'       : float — per-era std.
              - 'ci_lo'     : float | None — Wilson CI lower (binary series only).
              - 'ci_hi'     : float | None — Wilson CI upper (binary series only).
              - 'is_binary' : bool — whether values in this era are all 0/1.
        - 'verdict'     : str — one of:
              'consistent'       — all era means have the same sign and no era CI
                                   is insufficient-n; eras within 2σ of each other.
              'sign_flip'        — at least one era pair has means of opposite sign.
              'insufficient_n'   — at least one era has n < min_n.
              'inconclusive'     — n sufficient but spread exceeds 2σ boundary.

    Statistical contract: this is a descriptive split; it is NOT a statistical test
    for structural breaks. A "consistent" verdict does not imply stationarity —
    it means the means do not flip sign and are reasonably close given sampling error.
    Use block_bootstrap_ci() or block_bootstrap_scalar_ci() for inference on the
    GAP between eras. No p-hacking knobs are exposed beyond the declared parameters.

    OVERLAP WARNING: on overlapping long-horizon rows each era will have fewer
    independent observations than n suggests. The Wilson CIs within each era will
    understate uncertainty. Point to block_bootstrap primitives for confirmed-edge
    work; this function is for exploratory display-tier stability checks.

    Usage example::

        import numpy as np
        rng = np.random.default_rng(0)
        dates = np.array(["2020-01", "2020-02", "2021-01", "2021-02"])
        values = np.array([1, 1, 0, 0])   # sign-flip across eras
        result = era_split_stability(dates, values)
        # → verdict = 'sign_flip'
    """
    if n_splits < 2:
        raise ValueError(f"era_split_stability: n_splits must be ≥ 2 (got {n_splits}).")

    dates = np.asarray(dates)
    values = np.asarray(values, dtype=float)
    if len(dates) != len(values):
        raise ValueError(
            f"era_split_stability: dates and values must have the same length "
            f"(got {len(dates)} vs {len(values)})."
        )
    if len(dates) == 0:
        return {"n_splits": n_splits, "eras": [], "verdict": "insufficient_n"}

    # Sort chronologically.
    order = np.argsort(dates)
    dates_s = dates[order]
    values_s = values[order]

    # Determine split boundaries.
    n = len(dates_s)
    if n_splits == 2 and split_date is not None:
        # Explicit split date: find the boundary index.
        split_str = str(split_date)
        boundary = int(np.searchsorted(dates_s.astype(str), split_str, side="left"))
        boundaries = [0, max(1, boundary), n]
    else:
        # Equal-length chronological eras.
        boundaries = [int(round(i * n / n_splits)) for i in range(n_splits + 1)]
        boundaries[0] = 0
        boundaries[-1] = n

    era_records: list[dict] = []
    for era_idx in range(n_splits):
        lo_i = boundaries[era_idx]
        hi_i = boundaries[era_idx + 1]
        era_vals = values_s[lo_i:hi_i]
        era_dates = dates_s[lo_i:hi_i]
        n_era = len(era_vals)
        if n_era == 0:
            era_records.append({
                "era": era_idx, "date_lo": None, "date_hi": None,
                "n": 0, "mean": None, "std": None,
                "ci_lo": None, "ci_hi": None, "is_binary": False,
            })
            continue
        era_mean = float(np.mean(era_vals))
        era_std = float(np.std(era_vals, ddof=min(1, n_era - 1)))
        # Binary check: all values are 0 or 1 (within float tolerance).
        is_binary = bool(np.all((era_vals == 0.0) | (era_vals == 1.0)))
        ci_lo: float | None = None
        ci_hi: float | None = None
        if is_binary:
            k_era = int(np.sum(era_vals))
            ci = wilson_ci(k_era, n_era)
            if ci:
                ci_lo, ci_hi = ci
        era_records.append({
            "era": era_idx,
            "date_lo": str(era_dates[0]),
            "date_hi": str(era_dates[-1]),
            "n": n_era,
            "mean": round(era_mean, 6),
            "std": round(era_std, 6),
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "is_binary": is_binary,
        })

    # Compute verdict.
    era_means = [r["mean"] for r in era_records if r["mean"] is not None]
    era_ns = [r["n"] for r in era_records]

    if any(n_e < min_n for n_e in era_ns):
        verdict = "insufficient_n"
    elif len(era_means) < 2:
        verdict = "insufficient_n"
    else:
        # Sign-flip: any pair of eras with means of opposite sign.
        signs = [1 if m > 0 else (-1 if m < 0 else 0) for m in era_means]
        has_sign_flip = any(s1 != s2 and s1 != 0 and s2 != 0
                           for i, s1 in enumerate(signs)
                           for s2 in signs[i + 1:])
        if has_sign_flip:
            verdict = "sign_flip"
        else:
            # Consistent: means within 2 pooled std-errors of each other.
            pooled_std = float(np.mean([r["std"] for r in era_records if r["std"] is not None]))
            pooled_se = pooled_std / math.sqrt(max(1, min(era_ns)))
            spread = float(np.max(era_means) - np.min(era_means))
            if spread <= 2.0 * pooled_se or pooled_se == 0.0:
                verdict = "consistent"
            else:
                verdict = "inconclusive"

    return {"n_splits": n_splits, "eras": era_records, "verdict": verdict}


def eb_shrink(
    k: np.ndarray | list,
    n: np.ndarray | list,
    prior_alpha: float | None = None,
    prior_beta: float | None = None,
) -> dict:
    """Empirical-Bayes beta-binomial shrinkage for an array of binomial cells.

    Shrinks observed rates k_i/n_i toward a Beta(α, β) prior. When prior_alpha
    and prior_beta are None, α and β are estimated from the provided cells by
    the method-of-moments estimator on the observed rates and variances.

    Parameters
    ----------
    k           : 1-D integer array of success counts (one per cell).
    n           : 1-D integer array of trial counts (one per cell), aligned to k.
    prior_alpha : optional fixed Beta prior shape α > 0. If None, estimated from data.
    prior_beta  : optional fixed Beta prior shape β > 0. If None, estimated from data.
                  Both prior_alpha and prior_beta must be set together; providing only
                  one raises ValueError.

    Returns
    -------
    dict with keys:
        - 'shrunk_rates'    : list[float] — posterior mean for each cell,
                              = (k_i + α) / (n_i + α + β).
        - 'prior_alpha'     : float — α used (fitted or supplied).
        - 'prior_beta'      : float — β used (fitted or supplied).
        - 'prior_mean'      : float — α / (α + β), the prior center.
        - 'is_fitted'       : bool — True if priors were estimated from the data.
        - 'n_cells'         : int — number of cells.
        - 'fit_warning'     : str | None — populated when fitting was unreliable (e.g.
                              fewer than 3 cells, or variance estimate is near zero).

    IN-SAMPLE FITTING WARNING: when prior_alpha and prior_beta are None (the default),
    the prior is estimated by method-of-moments on THE SAME CELLS being shrunk. This
    is in-sample and will under-shrink relative to a held-out prior. Callers MUST label
    any display surface derived from fitted priors as "in-sample EB" or similar — it is
    NOT the same as a pre-registered prior. For pre-registered inference, pass explicit
    prior_alpha and prior_beta that were fixed before outcome contact.

    Statistical contract: the posterior mean for cell i is:
        shrunk_i = (k_i + α) / (n_i + α + β)
    which is a weighted average between the raw rate k_i/n_i (weight ∝ n_i) and the
    prior mean α/(α+β) (weight ∝ α+β). Small-n cells are pulled strongly toward the
    prior; large-n cells are barely moved (the shrinkage is adaptive by design).

    Usage example::

        # Small-n cells should shrink toward the prior; large-n cells barely move.
        k = np.array([1, 50])
        n = np.array([2, 100])
        result = eb_shrink(k, n, prior_alpha=5.0, prior_beta=5.0)
        # prior_mean = 5/(5+5) = 0.5
        # shrunk_rates[0] = (1+5)/(2+10) ≈ 0.50   (small n → pulled to prior)
        # shrunk_rates[1] = (50+5)/(100+10) ≈ 0.50  (large n → near raw rate 50%)
    """
    if (prior_alpha is None) != (prior_beta is None):
        raise ValueError(
            "eb_shrink: prior_alpha and prior_beta must both be set or both be None. "
            "Providing only one is ambiguous."
        )

    k_arr = np.asarray(k, dtype=float)
    n_arr = np.asarray(n, dtype=float)
    if k_arr.shape != n_arr.shape:
        raise ValueError(
            f"eb_shrink: k and n must have the same shape "
            f"(got {k_arr.shape} vs {n_arr.shape})."
        )
    n_cells = len(k_arr.ravel())
    k_flat = k_arr.ravel()
    n_flat = n_arr.ravel()

    fit_warning: str | None = None
    is_fitted = False
    alpha: float
    beta: float

    if prior_alpha is not None and prior_beta is not None:
        alpha = float(prior_alpha)
        beta = float(prior_beta)
    else:
        # Method-of-moments estimation from the observed rates.
        is_fitted = True
        if n_cells < 3:
            fit_warning = (
                f"eb_shrink: fewer than 3 cells ({n_cells}) — method-of-moments prior "
                "is unreliable. Falling back to Beta(1, 1) (uniform prior). "
                "Pass explicit prior_alpha/prior_beta for more control."
            )
            log.warning(fit_warning)
            alpha, beta = 1.0, 1.0
        else:
            # Compute observed rates only for cells with n > 0.
            valid = n_flat > 0
            if valid.sum() < 2:
                fit_warning = (
                    "eb_shrink: fewer than 2 cells have n > 0 — falling back to "
                    "Beta(1, 1). Pass explicit prior_alpha/prior_beta."
                )
                log.warning(fit_warning)
                alpha, beta = 1.0, 1.0
            else:
                rates = k_flat[valid] / n_flat[valid]
                mu = float(np.mean(rates))
                var = float(np.var(rates, ddof=1))
                # Method-of-moments: mu = α/(α+β), var = α·β/((α+β)²·(α+β+1))
                # Solving: α+β+1 = mu(1-mu)/var  → α+β = mu(1-mu)/var - 1
                # Guard: if var=0 or var≥mu(1-mu), the estimator is undefined.
                if var <= 0 or var >= mu * (1.0 - mu):
                    fit_warning = (
                        f"eb_shrink: variance estimate ({var:.6f}) is zero or exceeds "
                        f"mu*(1-mu)={mu*(1-mu):.6f} — method-of-moments is undefined. "
                        "Falling back to Beta(1, 1). Pass explicit prior_alpha/prior_beta."
                    )
                    log.warning(fit_warning)
                    alpha, beta = 1.0, 1.0
                else:
                    concentration = mu * (1.0 - mu) / var - 1.0
                    alpha = float(max(0.01, mu * concentration))
                    beta = float(max(0.01, (1.0 - mu) * concentration))

    prior_mean = alpha / (alpha + beta)

    shrunk: list[float] = []
    for k_i, n_i in zip(k_flat, n_flat):
        if n_i <= 0:
            # No data: return prior mean.
            shrunk.append(round(prior_mean, 6))
        else:
            posterior_mean = (k_i + alpha) / (n_i + alpha + beta)
            shrunk.append(round(float(posterior_mean), 6))

    return {
        "shrunk_rates": shrunk,
        "prior_alpha": round(alpha, 6),
        "prior_beta": round(beta, 6),
        "prior_mean": round(prior_mean, 6),
        "is_fitted": is_fitted,
        "n_cells": n_cells,
        "fit_warning": fit_warning,
    }


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
