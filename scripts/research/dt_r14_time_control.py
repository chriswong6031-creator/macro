"""DT-R14 time-controlled recomputation for S-SQ Phase-0.

DT-R14 ruling (verbatim from DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §7):
  'The 12 declared trials stand as registered (family esx_sq_phase0, budget=12, declared
   pre-DT-R14). A time-controlled recomputation of the same cells (within-month demeaning
   of outcomes or month-block bootstrap over fire months) is a MANDATORY robustness pass,
   not new trials. Verdict may be PASS only where both bases agree; disagreement → DEFER
   with both printed.'

This script:
  1. Loads cached FIRED_UP events (from /private/tmp/_ssq_event_cache/)
  2. Re-grades them using the harness grader (fast — no enumeration)
  3. Runs month-block bootstrap over fire months for stop5 (deep panel, standalone form,
     defaults cfg) — the primary inference cell
  4. Also runs within-month outcome demeaning as the second robustness basis
  5. Prints results in machine-readable markdown format for inclusion in the report

No new trials are registered. Budget: NOT CHARGED (robustness pass per DT-R14).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path("/private/tmp/esx-ssq")
sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

_CACHE_ROOT = Path("/private/tmp/_ssq_event_cache")
_DATA = _REPO_ROOT / "data"

# Import from harness (reuse, do not rewrite)
from scripts.research.run_w2_ssq import (
    _load_deep_ohlcv_volume,
    grade_sq_events,
    SPECIES_FAMILY,
    SPECIES_ID,
    SPECIES_NAME,
    RNG_SEED,
)
from scripts.research.run_w2_sur import _prepare_binary_outcomes

N_BOOTSTRAP = 500  # month-block bootstrap resamples (sufficient for 95% CI stability at n>400)
OUTCOME_COL = "stop5"  # primary inference cell per DT-R14


def load_cached_events(panel: str, cfg_key: str) -> pd.DataFrame:
    """Load per-ticker cached events from the SSQ event cache."""
    cache_dir = _CACHE_ROOT / panel / cfg_key
    if not cache_dir.exists():
        raise FileNotFoundError(f"Cache dir not found: {cache_dir}")
    dfs = []
    for f in sorted(cache_dir.glob("*.parquet")):
        df = pd.read_parquet(f)
        dfs.append(df)
    if not dfs:
        raise ValueError(f"No cached files in {cache_dir}")
    events = pd.concat(dfs, ignore_index=True)
    events["date"] = pd.to_datetime(events["date"])
    # Only FIRED_UP / direction=up events (FIRED_DOWN excluded)
    events = events[events["fired_dir"] == "up"].copy()
    log.info("Loaded %d FIRED_UP events from cache panel=%s cfg=%s", len(events), panel, cfg_key)
    return events


def month_block_bootstrap_stop5(
    graded: pd.DataFrame,
    n_bootstrap: int = N_BOOTSTRAP,
    rng_seed: int = RNG_SEED,
) -> dict:
    """Month-block bootstrap for demeaned stop5 contrast (treatment vs control).

    Resampling unit = calendar month of fire date.
    - Within-month demeaning applied BEFORE the month-block resample:
      stop5_demeaned = stop5 - monthly_mean(stop5, pooled treatment+control)
    - For each bootstrap iteration: sample months WITH REPLACEMENT
    - Compute mean(stop5_demeaned | _is_ssq=1) - mean(stop5_demeaned | _is_ssq=0)
    - Return point estimate, 95% CI, and whether CI excludes 0

    DT-R14 F2 corrected estimand: the naive mean difference treat.mean() - ctrl.mean()
    is NOT a time control — it conflates calendar-time confounds with the treatment
    effect. The correct estimand applies within-month cross-sectional demeaning BEFORE
    the bootstrap resample, so each iteration estimates the demeaned contrast (parallel
    to Method 2 / OLS with month FE). Expected result: near the primary date-FE estimate
    (-0.0118) and Method 2 demeaned coefficient (-0.0125), not the naive raw difference.
    """
    df = graded[graded["gradable"] == True].copy()  # noqa: E712
    if df.empty:
        return {"error": "no gradable events"}

    df["fire_month"] = pd.to_datetime(df["date"]).dt.to_period("M")

    # Within-month demeaning of stop5 outcome (BEFORE bootstrap)
    # Subtract the monthly mean (pooled treatment + control) from each observation.
    # This absorbs calendar-time effects so the bootstrap contrast is date-FE-corrected.
    month_means = df.groupby("fire_month")[OUTCOME_COL].transform("mean")
    DEMEANED_COL = OUTCOME_COL + "_demeaned"
    df[DEMEANED_COL] = df[OUTCOME_COL] - month_means

    rng = np.random.default_rng(rng_seed)
    months = df["fire_month"].unique()
    if len(months) < 4:
        return {"error": f"only {len(months)} unique months — cannot month-block bootstrap"}

    # Point estimate: demeaned mean difference (treatment - control on demeaned outcome)
    treat = df[df["_is_ssq"] == 1][DEMEANED_COL].values
    ctrl  = df[df["_is_ssq"] == 0][DEMEANED_COL].values
    point_est = treat.mean() - ctrl.mean()

    # Precompute per-month numpy arrays for fast bootstrap (avoids pandas concat per iteration)
    month_arr = df["fire_month"].values
    is_ssq_arr = df["_is_ssq"].values
    dem_arr = df[DEMEANED_COL].values
    month_to_idx = {m: np.where(month_arr == m)[0] for m in months}

    # Month-block bootstrap on demeaned outcome (numpy-based, avoids per-iteration concat)
    boot_diffs = []
    for _ in range(n_bootstrap):
        sampled_months = rng.choice(months, size=len(months), replace=True)
        # Gather indices for all sampled months (with replacement)
        boot_idx = np.concatenate([month_to_idx[m] for m in sampled_months])
        t = dem_arr[boot_idx[is_ssq_arr[boot_idx] == 1]]
        c = dem_arr[boot_idx[is_ssq_arr[boot_idx] == 0]]
        if len(t) > 0 and len(c) > 0:
            boot_diffs.append(t.mean() - c.mean())

    if len(boot_diffs) < 100:
        return {"error": f"too few valid bootstrap iterations: {len(boot_diffs)}"}

    boot_diffs = np.array(boot_diffs)
    ci_lo = float(np.percentile(boot_diffs, 2.5))
    ci_hi = float(np.percentile(boot_diffs, 97.5))
    ci_excl_0 = ci_hi < 0 or ci_lo > 0

    return {
        "method": "month-block bootstrap",
        "n_months": int(len(months)),
        "n_boot": len(boot_diffs),
        "n_treatment": int((df["_is_ssq"] == 1).sum()),
        "n_control": int((df["_is_ssq"] == 0).sum()),
        "point_est": float(point_est),
        "ci_lo": float(ci_lo),
        "ci_hi": float(ci_hi),
        "ci_excl_0": bool(ci_excl_0),
        "noninferiority_pass": bool(ci_hi < 0.01),
    }


def within_month_demeaning_stop5(graded: pd.DataFrame) -> dict:
    """Within-month demeaning of stop5 outcome.

    Subtracts the monthly mean stop5 rate (pooled treatment + control) from each
    observation, then regresses demeaned stop5 on _is_ssq using numpy OLS
    with HC3 sandwich SEs (no statsmodels dependency).

    DT-R14 rationale: removes calendar-time confounding by demeaning within each
    month's cross-section. Orthogonal to the month-block bootstrap approach.
    """
    df = graded[graded["gradable"] == True].copy()  # noqa: E712
    if df.empty:
        return {"error": "no gradable events"}

    df["fire_month"] = pd.to_datetime(df["date"]).dt.to_period("M")

    # Compute monthly mean stop5 (pooled)
    month_means = df.groupby("fire_month")[OUTCOME_COL].transform("mean")
    df["stop5_demeaned"] = df[OUTCOME_COL] - month_means

    # OLS: stop5_demeaned ~ _is_ssq using numpy
    # Design matrix: [intercept, _is_ssq]
    y = df["stop5_demeaned"].values
    X = np.column_stack([np.ones(len(df)), df["_is_ssq"].values])

    try:
        # OLS via normal equations
        XtX = X.T @ X
        XtX_inv = np.linalg.inv(XtX)
        beta = XtX_inv @ (X.T @ y)
        coef = float(beta[1])

        # Residuals
        resid = y - X @ beta
        n = len(y)
        k = X.shape[1]

        # HC3 sandwich SE
        h = np.einsum('ij,jk,ik->i', X, XtX_inv, X)  # leverage
        e_hc3 = resid ** 2 / (1.0 - h) ** 2
        meat = (X.T * e_hc3) @ X
        V_hc3 = XtX_inv @ meat @ XtX_inv
        se_hc3 = float(np.sqrt(V_hc3[1, 1]))

        # 95% CI via normal approximation (n large)
        from scipy import stats
        z = stats.norm.ppf(0.975)
        ci_lo = float(coef - z * se_hc3)
        ci_hi = float(coef + z * se_hc3)
        pval = float(2 * stats.norm.sf(abs(coef / se_hc3)))
        ci_excl_0 = ci_hi < 0 or ci_lo > 0
        noninferiority_pass = ci_hi < 0.01
    except Exception as e:
        return {"error": f"OLS failed: {e}"}

    return {
        "method": "within-month demeaning",
        "n_months": int(df["fire_month"].nunique()),
        "n_treatment": int((df["_is_ssq"] == 1).sum()),
        "n_control": int((df["_is_ssq"] == 0).sum()),
        "coef": coef,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "pval": pval,
        "ci_excl_0": bool(ci_excl_0),
        "noninferiority_pass": bool(noninferiority_pass),
    }


def run_dt_r14_recomputation() -> str:
    """Run DT-R14 time-controlled recomputation and return markdown section."""
    log.info("=== DT-R14 TIME-CONTROLLED RECOMPUTATION STARTING ===")
    log.info("DT-R14 ruling: mandatory robustness pass (not new trials; budget NOT charged).")

    # Load sector map (needed for grading)
    sector_map_path = _DATA / "research" / "sector_map.csv"
    if sector_map_path.exists():
        sector_df = pd.read_csv(sector_map_path)
        sector_map = dict(zip(sector_df["ticker"], sector_df["sector"]))
    else:
        sector_map = {}
        log.warning("sector_map.csv not found — sector will be NaN")

    # Load gate fires for control arm (deep panel)
    fires_path = _DATA / "research" / "gate_fires_deep.parquet"
    gate_fires = pd.read_parquet(fires_path)
    gate_fires["date"] = pd.to_datetime(gate_fires["date"])
    log.info("Loaded %d gate fires (control arm)", len(gate_fires))

    # Load deep OHLCV + volume (needed for grading)
    log.info("Loading deep OHLCV+volume panel for grading...")
    ohlcv_store = _load_deep_ohlcv_volume()
    closes_for_grade = {t: df["close"] for t, df in ohlcv_store.items()}
    log.info("Loaded %d tickers for grading", len(ohlcv_store))

    # Load cached events (defaults cfg, deep panel)
    events_deep = load_cached_events("deep", "defaults")

    # Grade S-SQ events
    log.info("Grading S-SQ events for deep panel...")
    graded_ssq = grade_sq_events(events_deep, ohlcv_store, sector_map, "deep")
    if graded_ssq.empty:
        return "## DT-R14 Time-Controlled Recomputation\n\nERROR: No gradable events.\n"

    graded_ssq["_is_ssq"] = 1

    # Grade gate fires (control arm)
    from scripts.research.run_w2_sur import run_form_analysis
    from scripts.research.entry_strata_phase0 import grade_fires
    gf_df = pd.DataFrame({
        "ticker": gate_fires["ticker"].values,
        "date": gate_fires["date"].values,
        "tier": "GF",
        "sub": "gf",
        "ticks": 0.0,
        "not_topped": True,
        "eligible": True,
        "panel": "deep",
    })
    gf_df["sector"] = gf_df["ticker"].map(sector_map)
    gf_graded = grade_fires(gf_df, closes_for_grade)
    gf_graded = _prepare_binary_outcomes(gf_graded)
    gf_graded["_is_ssq"] = 0
    log.info("Graded %d gate fires", len(gf_graded))

    # Combine treatment + control
    combined = pd.concat([graded_ssq, gf_graded], ignore_index=True, sort=False)
    combined["date"] = pd.to_datetime(combined["date"])
    n_treat = int((combined["_is_ssq"] == 1).sum())
    n_ctrl  = int((combined["_is_ssq"] == 0).sum())
    log.info("Combined: %d treatment + %d control", n_treat, n_ctrl)

    # --- Reference: raw stop5 coefficient from primary run ---
    # (from report: standalone deep defaults stop5 coef=-0.0118 CI_hi=0.0022)
    primary_coef = -0.0118
    primary_ci_lo = -0.016
    primary_ci_hi = 0.0022
    primary_noninferiority = primary_ci_hi < 0.01  # True

    # --- DT-R14 Method 1: Month-block bootstrap ---
    log.info("Running month-block bootstrap (DT-R14)...")
    mbb_result = month_block_bootstrap_stop5(combined, n_bootstrap=N_BOOTSTRAP, rng_seed=RNG_SEED)
    log.info("Month-block bootstrap result: %s", mbb_result)

    # --- DT-R14 Method 2: Within-month demeaning ---
    log.info("Running within-month demeaning (DT-R14)...")
    wmd_result = within_month_demeaning_stop5(combined)
    log.info("Within-month demeaning result: %s", wmd_result)

    # --- Agreement check per DT-R14 ruling ---
    def verdict_from_result(r: dict, method_name: str) -> tuple[str, bool]:
        if "error" in r:
            return f"ERROR ({r['error']})", False
        ni = r.get("noninferiority_pass", False)
        return ("NON-INFERIOR" if ni else "INFERIOR"), ni

    mbb_label, mbb_ni = verdict_from_result(mbb_result, "month-block bootstrap")
    wmd_label, wmd_ni = verdict_from_result(wmd_result, "within-month demeaning")
    primary_ni = primary_noninferiority

    both_bases_agree = (mbb_ni == wmd_ni)
    all_three_agree = (primary_ni == mbb_ni == wmd_ni)

    if all_three_agree and primary_ni:
        overall_verdict = "PASS (all three bases: primary + month-block + within-month agree NON-INFERIOR)"
    elif all_three_agree and not primary_ni:
        overall_verdict = "FAIL (all three bases agree INFERIOR)"
    elif both_bases_agree and mbb_ni != primary_ni:
        overall_verdict = (
            "DEFER — primary and time-controlled bases disagree: "
            f"primary={'NON-INFERIOR' if primary_ni else 'INFERIOR'}, "
            f"time-controlled={mbb_label}. Both results printed."
        )
    else:
        # Two bases disagree with each other
        overall_verdict = (
            f"DEFER — time-controlled bases disagree with each other: "
            f"month-block={mbb_label}, within-month={wmd_label}. Both printed."
        )

    # --- Format markdown section ---
    lines = []
    lines.append("")
    lines.append("## DT-R14 Time-Controlled Recomputation (Mandatory Robustness Pass)")
    lines.append("")
    lines.append("**DT-R14 ruling (verbatim):** 'The 12 declared trials stand as registered "
                 "(family esx_sq_phase0, budget=12, declared pre-DT-R14). A time-controlled "
                 "recomputation of the same cells (within-month demeaning of outcomes or "
                 "month-block bootstrap over fire months) is a MANDATORY robustness pass, "
                 "not new trials. Verdict may be PASS only where both bases agree; "
                 "disagreement → DEFER with both printed.'")
    lines.append("")
    lines.append("**Scope:** deep panel, standalone form, defaults cfg, outcome=stop5.")
    lines.append("**Budget status:** NOT CHARGED (mandatory robustness pass, not a new trial).")
    lines.append("**Control arm:** gate_fires_deep.parquet (same as primary analysis).")
    lines.append("")
    lines.append("### Reference: Primary Analysis Result")
    lines.append("")
    lines.append(f"| Method | stop5 coef | 95% CI | CI_hi | Non-inferior (CI_hi<+0.01)? |")
    lines.append(f"|---|---|---|---|---|")
    lines.append(
        f"| Primary (R1 date-FE, episode-block bootstrap) | {primary_coef:.4f} "
        f"| [{primary_ci_lo:.3f}, +{primary_ci_hi:.4f}] "
        f"| {primary_ci_hi:.4f} "
        f"| {'YES' if primary_ni else 'NO'} |"
    )
    lines.append("")
    lines.append("### DT-R14 Method 1: Month-Block Bootstrap (F2-corrected demeaned estimand)")
    lines.append("")
    lines.append("**Resampling unit:** calendar month of fire date. "
                 "Months sampled WITH REPLACEMENT. "
                 "**F2 fix:** within-month demeaning applied BEFORE bootstrap resample — "
                 "stop5_demeaned = stop5 minus monthly mean (pooled). "
                 "Statistic: mean(stop5_demeaned | treatment) − mean(stop5_demeaned | control) per resample. "
                 "Estimates the date-FE-corrected contrast, not the naive raw difference.")
    lines.append(f"**Bootstrap resamples:** {N_BOOTSTRAP}")
    lines.append("")
    if "error" in mbb_result:
        lines.append(f"> ERROR: {mbb_result['error']}")
    else:
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        lines.append(f"| Unique fire months | {mbb_result['n_months']} |")
        lines.append(f"| Valid bootstrap iterations | {mbb_result['n_boot']} |")
        lines.append(f"| N treatment | {mbb_result['n_treatment']} |")
        lines.append(f"| N control | {mbb_result['n_control']} |")
        lines.append(f"| Point estimate (mean diff) | {mbb_result['point_est']:.4f} |")
        lines.append(f"| 95% CI lower | {mbb_result['ci_lo']:.4f} |")
        lines.append(f"| 95% CI upper | {mbb_result['ci_hi']:.4f} |")
        lines.append(f"| CI excludes 0? | {'YES' if mbb_result['ci_excl_0'] else 'no'} |")
        lines.append(f"| Non-inferior (CI_hi < +0.01)? | {'YES' if mbb_result['noninferiority_pass'] else 'NO'} |")
    lines.append("")
    lines.append("### DT-R14 Method 2: Within-Month Outcome Demeaning")
    lines.append("")
    lines.append("**Method:** Subtract monthly mean stop5 (pooled) from each observation. "
                 "OLS of demeaned stop5 on _is_ssq with HC3 robust SEs. "
                 "Month effects absorbed by demeaning.")
    lines.append("")
    if "error" in wmd_result:
        lines.append(f"> ERROR: {wmd_result['error']}")
    else:
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        lines.append(f"| Unique fire months | {wmd_result['n_months']} |")
        lines.append(f"| N treatment | {wmd_result['n_treatment']} |")
        lines.append(f"| N control | {wmd_result['n_control']} |")
        lines.append(f"| OLS coef (_is_ssq) | {wmd_result['coef']:.4f} |")
        lines.append(f"| 95% CI | [{wmd_result['ci_lo']:.4f}, {wmd_result['ci_hi']:.4f}] |")
        lines.append(f"| p-value | {wmd_result['pval']:.4f} |")
        lines.append(f"| CI excludes 0? | {'YES' if wmd_result['ci_excl_0'] else 'no'} |")
        lines.append(f"| Non-inferior (CI_hi < +0.01)? | {'YES' if wmd_result['noninferiority_pass'] else 'NO'} |")
    lines.append("")
    lines.append("### DT-R14 Agreement Assessment")
    lines.append("")
    lines.append(f"| Basis | Non-inferior? |")
    lines.append(f"|---|---|")
    lines.append(f"| Primary (R1 date-FE) | {'YES' if primary_ni else 'NO'} |")
    lines.append(f"| Month-block bootstrap | {mbb_label} |")
    lines.append(f"| Within-month demeaning | {wmd_label} |")
    lines.append("")
    lines.append(f"**DT-R14 VERDICT: {overall_verdict}**")
    lines.append("")
    lines.append(
        "> DT-R14 rule: 'Verdict may be PASS only where both bases agree; "
        "disagreement → DEFER with both printed.' "
        "Results above are printed with both bases as required regardless of outcome."
    )

    result_text = "\n".join(lines)
    log.info("=== DT-R14 COMPLETE ===")
    log.info("DT-R14 verdict: %s", overall_verdict)
    return result_text


if __name__ == "__main__":
    result = run_dt_r14_recomputation()
    print(result)
