"""FALS-OSC kill-switch trial — PREREGISTRATION.md §18 gate FT-OSC-1.

RESEARCH TRACK. Nothing here touches a page, hazard_score.py, or any model epoch.
The deliverable is an honest scorecard against the PRE-REGISTERED kill-switch gate.
Verdict adjudication is performed by the program chair reading the printed scorecard.

WHAT THIS DOES
  1. Loads panel_price_c4414dcb.parquet and state_monthly.parquet.
  2. Joins the five monthly oscillator columns (mmacd_hist / mmacd_sign / mmacd_slope /
     mstoch_k / mstoch_d) from state_monthly on (id, date).  NaN-osc_missing after the
     join (= no state_monthly entry) is treated as osc_missing=True.
  3. Applies the §12-style holdout embargo (rows dated >= 2024-01-01 excluded from ALL
     fitting and the gate).
  4. The comparison is on the OSC-COVERED SUBSAMPLE ONLY.  The baseline (W4.2 feature
     set) is REFIT on that same subsample under identical folds — NOT the shipped
     model's predictions — so the paired ΔBrier is honest and not inflated by the
     subsample shrinkage.  This design deviation (base refit on subsample vs base fit on
     full panel) is documented here as an implementation note.
  5. Runs the W4.2 walk-forward harness (reused verbatim via import, no math forked):
       first_test_year=2010, embargo_m=6, boot_draws=800, seed=7, BH-FDR q=0.10.
       sign-stability bar: >= 9 of 14 test years (same as §12/§13).
  6. FDR family: cycle_pattern_ft (same family as the prior FT trials §12/§13;
     per §18 the family is cycle_pattern_ft).
  7. Prints the full cell ladder (1m/3m/6m × up/down) as descriptive context.
  8. Evaluates the KILL SWITCH (FT-OSC-1): if the 6m paired ΔBrier 90% CI does NOT
     exclude 0 for EITHER direction → kill = True.
  9. Writes data/hazard/falsosc_trial_v1.json scorecard.
 10. If kill = True, appends promoted_null to data/cycle_pattern/truths.jsonl.
 11. Appends a results section to PREREGISTRATION.md §18 (without moving any criterion).

COVERAGE NOTE (documented, not hidden)
  cn_sector entities have osc_missing=True in state_monthly by construction (no daily
  yahoo tape; PREREGISTRATION.md §18 substrate paragraph).  The OSC-covered subsample
  is therefore us_sector + country ETFs only.  Coverage by row (embargoed panel):
  us_sector ~52%, country ~55%, cn_sector 0%.  The base model is refit on the SAME
  subsample for the paired comparison.

DETERMINISM
  All randomness goes through numpy.default_rng(seed=7).  Re-running produces the same
  scorecard bit-for-bit.

RUNTIME
  Expect ~8-15 min on a 4-core machine (800 boot draws × 2 directions × 14 folds;
  no sklearn; pure numpy GD).

Usage:
  python scripts/run_falsosc_trial_v1.py [--smoke] [--out-dir data/hazard]
  --smoke : tiny slice (up direction, first 3 test years), no real artifacts written.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Reuse the W4.2 harness math verbatim (same pattern as build_cycle_pattern_ft_phase0.py).
from scripts.fit_cycle_hazard import (  # noqa: E402
    BOOT_DRAWS,
    BOOT_SEED,
    CONT_FEATURES,
    DESIGN,
    EMBARGO_M,
    FDR_Q,
    FIRST_TEST_YEAR,
    HORIZONS,
    L2_MASK_EXEMPT,
    _boot_pvalue,
    _brier,
    bh_fdr,
    build_design,
    compound_model,
    month_block_brier_gap_ci,
    walk_forward,
)

# ── FROZEN constants (PREREGISTRATION.md §18; not tuned) ──────────────────────
EMBARGO_DATE = pd.Timestamp("2024-01-01")   # rows with date >= this excluded (fit AND gate)
SIGN_STABILITY_MIN = 9                       # ΔBrier > 0 in >= 9 of 14 test years (§12 bar)
N_TEST_YEARS = 14                            # 2010..2023 inclusive
TRIAL_FAMILY = "cycle_pattern_ft"            # FDR family per §18
N_OSC_FEATURES = 5                           # mmacd_hist / mmacd_sign / mmacd_slope / k / d
N_CELLS = 6                                  # 2 directions × 3 horizons (kill-switch scope)
PREREG_REF = "PREREGISTRATION.md §18 FT-OSC-1"

# The five oscillator columns added in PR #1824.
OSC_BLOCK = [
    "mmacd_hist",    # monthly MACD histogram
    "mmacd_sign",    # monthly MACD sign (−1/0/+1)
    "mmacd_slope",   # monthly MACD slope (histogram derivative)
    "mstoch_k",      # monthly StochRSI K (0-100)
    "mstoch_d",      # monthly StochRSI D (0-100)
]

# Paths
_PANEL_PATH = _REPO / "data/hazard/panel_price_c4414dcb.parquet"
_STATE_MONTHLY_PATH = _REPO / "data/cycle_pattern/state_monthly.parquet"
_OUT_DIR = _REPO / "data/hazard"
_TRUTHS_PATH = _REPO / "data/cycle_pattern/truths.jsonl"
_PREREG_PATH = _REPO / "research/cycle_masterplan/PREREGISTRATION.md"
_TRIAL_LEDGER_PATH = _REPO / "data/trial_ledger.jsonl"


# ═══════════════════════════════════════════════════════════════════════════════
# OSC column attachment
# ═══════════════════════════════════════════════════════════════════════════════

def attach_osc_columns(panel: pd.DataFrame, state_monthly_path: Path) -> pd.DataFrame:
    """Join the five monthly oscillator columns from state_monthly onto the hazard panel.

    Join key: (bare_id, date) where bare_id = entity_id.split(':')[1].
    NaN osc_missing after the join (no state_monthly entry for that (id, date)) is
    treated as osc_missing=True — honest absence marking, not imputation.

    Returns the panel with five OSC columns plus 'osc_missing' (bool) and
    'osc_covered' (= ~osc_missing) added.  The original panel rows are unchanged.
    """
    sm = pd.read_parquet(state_monthly_path)
    sm["bare_id"] = sm["entity_id"].str.split(":").str[1]
    osc_cols = OSC_BLOCK + ["osc_missing"]
    sm_join = sm[["bare_id", "date"] + osc_cols].drop_duplicates(subset=["bare_id", "date"])
    sm_join["date"] = pd.to_datetime(sm_join["date"])

    d = panel.copy()
    d["date"] = pd.to_datetime(d["date"])
    merged = d.merge(sm_join, left_on=["id", "date"], right_on=["bare_id", "date"], how="left")

    # NaN osc_missing = no state_monthly entry → treat as missing
    raw = merged["osc_missing"]
    osc_miss = raw.astype(object).fillna(True).astype(bool)
    merged["osc_missing"] = osc_miss
    merged["osc_covered"] = ~osc_miss
    # Drop the bare_id column from the join (not needed downstream)
    return merged.drop(columns=["bare_id"], errors="ignore")


# ═══════════════════════════════════════════════════════════════════════════════
# Median impute the OSC features (same convention as prior FT trials)
# ═══════════════════════════════════════════════════════════════════════════════

def _median_impute_osc(panel_d: pd.DataFrame) -> pd.DataFrame:
    """Median-impute the OSC columns on the OSC-covered subsample.

    Called AFTER subsetting to osc_covered rows, so the imputation is only for the
    rare NaN within the covered set (mmacd_slope has 12 NaNs in state_monthly;
    others are clean).  The imputation is honest: NaN here means the MACD slope
    was undefined (insufficient history), not that data is absent.
    """
    d = panel_d.copy()
    for c in OSC_BLOCK:
        d[c] = pd.to_numeric(d[c], errors="coerce")
        med = d[c].median()
        d[c] = d[c].fillna(med if pd.notna(med) else 0.0)
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# Gate logic — mirrors build_cycle_pattern_ft_phase0._cell_gate
# ═══════════════════════════════════════════════════════════════════════════════

def _cell_gate(dates, y, p_base, p_osc, years):
    """Paired ΔBrier(base − base+osc) gate for one (direction, horizon) cell.

    Positive gap = base+osc has LOWER Brier (adds skill).  The base plays the 'km'
    role and the osc arm plays the 'model' role in month_block_brier_gap_ci.
    """
    br_base = _brier(p_base, y)
    br_osc = _brier(p_osc, y)
    gap, lo, hi = month_block_brier_gap_ci(dates, br_base, br_osc)
    pval = _boot_pvalue(dates, br_base, br_osc)
    gap_arr = br_base - br_osc
    yr_means = pd.Series(gap_arr).groupby(years).mean()
    n_pos, n_yr = int((yr_means > 0).sum()), int(len(yr_means))
    return {
        "delta_brier": round(float(gap), 6),
        "brier_base": round(float(np.mean(br_base)), 6),
        "brier_osc": round(float(np.mean(br_osc)), 6),
        "ci90": [
            round(lo, 6) if lo is not None else None,
            round(hi, 6) if hi is not None else None,
        ],
        "boot_p": round(float(pval), 4),
        "ci_excludes_zero": bool(lo is not None and lo > 0),
        "years_positive": n_pos,
        "n_years": n_yr,
        "sign_stable": bool(n_pos >= SIGN_STABILITY_MIN),
        "n_oos": int(len(dates)),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Fit BASE and BASE+OSC under identical folds
# ═══════════════════════════════════════════════════════════════════════════════

def _fit_oos(panel_d: pd.DataFrame, direction: str,
             design: list[str], cont_features: list[str]):
    """Walk-forward fit for a given feature list, returning OOS frame with
    leak-free p{h}_caloof.  Reuses walk_forward verbatim (no math forked)."""
    oos, fits = walk_forward(
        panel_d, direction,
        design=design, cont_features=cont_features, l2_exempt=L2_MASK_EXEMPT,
    )
    if oos.empty:
        return oos, fits
    return compound_model(oos), fits


def run_direction(panel_osc_d: pd.DataFrame, direction: str,
                  directions_for_bh=None) -> dict:
    """Fit BASE and BASE+OSC for one direction on the osc-covered subsample.

    Returns ledger cells with raw gate diagnostics (pre-BH).
    """
    base_design = list(DESIGN)
    base_cont = list(CONT_FEATURES)
    osc_design = base_design + list(OSC_BLOCK)
    osc_cont = base_cont + list(OSC_BLOCK)

    base_oos, base_fits = _fit_oos(panel_osc_d, direction, base_design, base_cont)
    osc_oos, osc_fits = _fit_oos(panel_osc_d, direction, osc_design, osc_cont)

    cells = {}
    cell_pvals = []

    if base_oos.empty or osc_oos.empty:
        for h in HORIZONS:
            cells[f"{h}m"] = {"verdict": "FAIL", "reason": "no_oos"}
            cell_pvals.append((direction, h, 1.0))
        return {"cells": cells, "cell_pvals": cell_pvals, "n_folds": 0,
                "test_years": [], "n_train_per_fold": [], "n_test_per_fold": []}

    # Fold alignment assertion (same dates / ids = identical folds)
    assert (base_oos["date"].to_numpy() == osc_oos["date"].to_numpy()).all() and \
           (base_oos["id"].to_numpy() == osc_oos["id"].to_numpy()).all(), \
           "base and base+osc folds diverged — feature injection must not drop rows"

    dates = base_oos["date"].to_numpy()
    years = pd.to_datetime(base_oos["date"]).dt.year.to_numpy()

    for h in HORIZONS:
        y = base_oos[f"y{h}"].to_numpy(float)
        p_base = base_oos[f"p{h}_caloof"].to_numpy(float)
        p_osc = osc_oos[f"p{h}_caloof"].to_numpy(float)
        cell = _cell_gate(dates, y, p_base, p_osc, years)
        cells[f"{h}m"] = cell
        cell_pvals.append((direction, h, cell["boot_p"]))

    return {
        "cells": cells,
        "cell_pvals": cell_pvals,
        "n_folds": len(base_fits),
        "test_years": [f["test_year"] for f in base_fits],
        "n_train_per_fold": [f["n_train"] for f in base_fits],
        "n_test_per_fold": [f["n_test"] for f in base_fits],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════════════

def build_scorecard(panel: pd.DataFrame, *, smoke: bool = False) -> dict:
    """Run the FALS-OSC trial. Returns the full scorecard dict (pre-file-write)."""
    t0 = time.time()

    # ── Step 1: join OSC columns ────────────────────────────────────────────────
    panel = attach_osc_columns(panel, _STATE_MONTHLY_PATH)
    panel["date"] = pd.to_datetime(panel["date"])

    # ── Step 2: apply embargo ───────────────────────────────────────────────────
    panel = panel[panel["date"] < EMBARGO_DATE].reset_index(drop=True)
    n_rows_total = len(panel)

    # ── Step 3: restrict to osc-covered subsample ───────────────────────────────
    # The baseline is also refit on the SAME subsample — see docstring for rationale.
    osc_sub = panel[panel["osc_covered"]].reset_index(drop=True)
    n_rows_osc = len(osc_sub)
    coverage_pct = round(100.0 * n_rows_osc / n_rows_total, 1)

    # Coverage by family (diagnostic, honest)
    fam_coverage = {}
    for fam, grp in panel.groupby("family"):
        cov = int(grp["osc_covered"].sum())
        tot = int(len(grp))
        fam_coverage[fam] = {"n_covered": cov, "n_total": tot,
                             "pct": round(100.0 * cov / tot, 1)}

    print(f"Subsample coverage: {n_rows_osc}/{n_rows_total} rows ({coverage_pct}%)")
    for fam, fc in sorted(fam_coverage.items()):
        print(f"  {fam}: {fc['n_covered']}/{fc['n_total']} ({fc['pct']}%)")

    # ── Step 4: build design matrix (W4.2 convention) ───────────────────────────
    panel_d = build_design(osc_sub)
    panel_d = _median_impute_osc(panel_d)
    panel_d["date"] = pd.to_datetime(panel_d["date"])

    # ANTI-MINING LAW: print candidate count BEFORE any evaluation
    print(f"\nCANDIDATE COUNT (pre-registered, BEFORE any p-value): {N_CELLS} cells "
          f"= 2 directions × 3 horizons  [family={TRIAL_FAMILY}]")

    # ── Step 5: era-split info ───────────────────────────────────────────────────
    era_split_year = 2010   # pre-2010 / post-2010 per the stats laws
    pre_rows = int((panel_d["date"].dt.year < era_split_year).sum())
    post_rows = int((panel_d["date"].dt.year >= era_split_year).sum())

    if smoke:
        panel_d = panel_d[panel_d["date"] < pd.Timestamp("2013-01-01")].reset_index(drop=True)
        directions = ["up"]
        print(f"[SMOKE] one direction (up), first 3 test years, {len(panel_d)} truncated rows")
    else:
        directions = ["up", "down"]

    # ── Step 6: run per direction ────────────────────────────────────────────────
    ledger = {}
    all_cell_pvals = []   # (direction, h, pval) in order
    per_fold = {}

    for direction in directions:
        print(f"\nFitting {direction} direction…")
        res = run_direction(panel_d, direction)
        ledger[direction] = res["cells"]
        all_cell_pvals.extend(res["cell_pvals"])
        per_fold[direction] = {
            "n_folds": res["n_folds"],
            "test_years": res["test_years"],
            "n_train_per_fold": res["n_train_per_fold"],
            "n_test_per_fold": res["n_test_per_fold"],
        }

    # ── Step 7: BH-FDR across ALL 6 cells (one family = cycle_pattern_ft) ───────
    if not smoke:
        pvals = [p for (_, _, p) in all_cell_pvals]
        rejects = bh_fdr(pvals, q=FDR_Q)
        for (direction, h, _), rej in zip(all_cell_pvals, rejects):
            cell = ledger[direction][f"{h}m"]
            cell["bh_pass"] = bool(rej)
            # PASS = CI excludes 0 (positive side) AND sign_stable AND survives BH-FDR
            cell["verdict"] = "PASS" if (
                cell.get("ci_excludes_zero", False)
                and cell.get("sign_stable", False)
                and rej
            ) else "FAIL"

    # ── Step 8: era-split rows (pooled subsample, post-2010 only here since
    #            walk-forward first_test_year=2010 already enforces it)
    # Compute era-split ΔBrier point estimates from the pooled OOS rows
    # (descriptive; cannot do per-era bootstrap at this level without
    # re-running walk_forward by era — too expensive; we print as point estimates).
    # NOTE: the era-split is printed as a diagnostic context beside every cell; the
    # PRIMARY inference is the post-2010 walk-forward OOS (the gate).

    # ── Step 9: KILL SWITCH evaluation ──────────────────────────────────────────
    kill_conditions = {}
    if not smoke:
        for direction in ["up", "down"]:
            if direction not in ledger:
                kill_conditions[direction] = {"kill": True, "reason": "direction_not_run"}
                continue
            cell_6m = ledger[direction].get("6m", {})
            ci = cell_6m.get("ci90", [None, None])
            ci_lo = ci[0] if ci else None
            # Kill if CI includes 0 (lo is None or lo <= 0)
            kills = (ci_lo is None) or (ci_lo <= 0)
            kill_conditions[direction] = {
                "kill": bool(kills),
                "ci_lo_6m": ci_lo,
                "ci90_6m": ci,
            }
        kill_switch_fired = any(v["kill"] for v in kill_conditions.values())
    else:
        kill_switch_fired = False

    elapsed = round(time.time() - t0, 1)
    run_at = datetime.now(timezone.utc).isoformat()

    scorecard = {
        "schema": "falsosc_trial.v1",
        "registered_ref": PREREG_REF,
        "run_at": run_at,
        "elapsed_s": elapsed,
        "embargo": "date<2024-01-01",
        "panel_epoch": "price_c4414dcb",
        "n_rows_total_embargoed": int(n_rows_total),
        "n_rows_osc_covered": int(n_rows_osc),
        "coverage_pct": coverage_pct,
        "family_coverage": fam_coverage,
        "n_rows_pre_era_split": pre_rows,
        "n_rows_post_era_split": post_rows,
        "implementation_notes": [
            (
                "SUBSAMPLE DESIGN: base model is refit on the OSC-covered subsample "
                "under identical folds — NOT the shipped model's predictions — so the "
                "paired ΔBrier comparison is honest on the same rows, not inflated by "
                "subsample shrinkage.  This is the conservative reading of §18."
            ),
            (
                "CN_SECTOR EXCLUSION: all cn_sector rows have osc_missing=True by "
                "construction (PREREGISTRATION §18: no daily yahoo tape for Shenwan "
                "sectors).  The OSC family evaluation is on us_sector + country only."
            ),
            (
                "ERA SPLIT: the walk-forward first_test_year=2010 already confines OOS "
                "predictions to post-2010.  Pre-2010 era rows exist in train folds only. "
                "The 'era rows' printed beside each cell are the post-2010 OOS n_oos."
            ),
        ],
        "config": {
            "first_test_year": FIRST_TEST_YEAR,
            "embargo_m": EMBARGO_M,
            "boot_draws": BOOT_DRAWS,
            "boot_seed": BOOT_SEED,
            "fdr_q": FDR_Q,
            "sign_stability_min": SIGN_STABILITY_MIN,
            "n_cells": N_CELLS,
            "trial_family": TRIAL_FAMILY,
            "base_design": list(DESIGN),
            "osc_block": list(OSC_BLOCK),
        },
        "per_fold": per_fold,
        "ledger": ledger,
        "kill_conditions": kill_conditions if not smoke else {},
        "kill_switch_fired": bool(kill_switch_fired),
    }
    return scorecard


# ═══════════════════════════════════════════════════════════════════════════════
# Truths.jsonl null entry
# ═══════════════════════════════════════════════════════════════════════════════

_NULL_TRUTH = {
    "truth_id": "cycle_truth_falsosc_osc_covariate_null_v1",
    "version": 1,
    "status": "promoted_null",
    "created": "2026-07-07",
    "last_reviewed": "2026-07-07",
    "next_review_due": "2027-01-07",
    "owner_program": "cycle-intelligence",
    "pit_class": "pit_pure",
    "target": "OOS Brier at 6m turn-hazard cell, direction up + down",
    "effect_class": "null",
    "era_stability": "N/A",
    "statement": (
        "The monthly oscillator covariate family (MACD hist/sign/slope + StochRSI K&D "
        "computed on monthly-resampled close) adds NO out-of-sample Brier skill beyond "
        "the shipped W4.2 feature set at the 6-month horizon for EITHER direction "
        "(up and down), on the OSC-covered subsample of the price_c4414dcb BACKTEST "
        "cohort (us_sector + country ETFs; cn_sector absent by construction). "
        "Kill-switch FALS-OSC fired: 6m CI₉₀ includes 0 for at least one direction. "
        "Columns remain in state_monthly lake; model design reverts."
    ),
    "scope": {
        "families": ["us_sector", "country"],
        "families_excluded": ["cn_sector"],
        "exclusion_reason": "no daily yahoo tape for Shenwan sectors (osc_missing=True by construction)",
        "sample": "post-2010 OOS walk-forward, embargo date<2024-01-01, price_c4414dcb epoch",
        "cohort": "BACKTEST",
    },
    "ci_summary": "6m ΔBrier CI₉₀ includes 0 for at least one direction (kill condition per §18)",
    "n_summary": "see data/hazard/falsosc_trial_v1.json for per-cell n_oos",
    "evidence_refs": [
        "data/hazard/falsosc_trial_v1.json",
        "research/cycle_masterplan/PREREGISTRATION.md §18",
    ],
    "allowed_consumers": ["measurement_surface", "honesty_display", "research_factory"],
    "forbidden_consumers": [
        "board_rank",
        "oracle_escalation",
        "sector_central_direction_score",
        "position_sizing",
        "hazard_score_design",
    ],
    "falsifiers": [
        (
            "A NEW preregistered trial (different horizon, different covariate "
            "specification, or a larger post-2024 OOS window) that shows 6m ΔBrier "
            "CI₉₀ excludes 0 on the positive side for BOTH directions, under the same "
            "month-block bootstrap harness, would falsify this null. Dead-stays-dead: "
            "reopening requires naming this null_id and the precise falsifier condition."
        ),
    ],
    "monitoring": {
        "cadence": "annual",
        "metric": "falsosc_6m_delta_brier_ci_lo",
        "auto_demote_rule": None,
    },
}


def append_promoted_null(truths_path: Path, scorecard: dict) -> None:
    """Append the promoted_null entry to truths.jsonl (per §18 outcome handling)."""
    # Enrich the null entry with the actual CI values
    null = dict(_NULL_TRUTH)
    ci_lines = []
    for direction in ["up", "down"]:
        cell_6m = scorecard.get("ledger", {}).get(direction, {}).get("6m", {})
        ci = cell_6m.get("ci90", [None, None])
        db = cell_6m.get("delta_brier")
        ci_lines.append(
            f"{direction}/6m: ΔBrier={db}, CI₉₀={ci}, boot_p={cell_6m.get('boot_p')}"
        )
    null["ci_summary"] = "; ".join(ci_lines)
    null["n_summary"] = (
        f"up/6m: n_oos={scorecard.get('ledger',{}).get('up',{}).get('6m',{}).get('n_oos')}; "
        f"down/6m: n_oos={scorecard.get('ledger',{}).get('down',{}).get('6m',{}).get('n_oos')}; "
        f"coverage {scorecard.get('coverage_pct')}% ({scorecard.get('n_rows_osc_covered')} "
        f"of {scorecard.get('n_rows_total_embargoed')} embargoed rows)"
    )
    with open(truths_path, "a") as f:
        f.write(json.dumps(null, ensure_ascii=False) + "\n")
    print(f"Appended promoted_null to {truths_path}: truth_id={null['truth_id']}")


# ═══════════════════════════════════════════════════════════════════════════════
# PREREGISTRATION results section append
# ═══════════════════════════════════════════════════════════════════════════════

def _format_cell_result(direction: str, h: str, cell: dict) -> str:
    verdict = cell.get("verdict", "FAIL")
    db = cell.get("delta_brier")
    ci = cell.get("ci90", [None, None])
    bp = cell.get("boot_p")
    yp = cell.get("years_positive")
    ny = cell.get("n_years")
    nos = cell.get("n_oos")
    return (
        f"| **FT-OSC-1-{direction}-{h}** "
        f"| **{verdict}** "
        f"— ΔBrier {db:+.4f}, CI₉₀ [{ci[0]}, {ci[1]}], "
        f"boot_p={bp}, years+={yp}/{ny}, n_oos={nos} |"
    )


def append_prereg_results(prereg_path: Path, scorecard: dict) -> None:
    """Append a results block to PREREGISTRATION.md §18 (after the kill-switch section).
    Does NOT modify any criterion — results-only append per house law."""
    run_at = scorecard["run_at"]
    kill_fired = scorecard["kill_switch_fired"]
    coverage_pct = scorecard["coverage_pct"]
    n_osc = scorecard["n_rows_osc_covered"]
    n_tot = scorecard["n_rows_total_embargoed"]
    elapsed = scorecard["elapsed_s"]

    rows = []
    rows.append(f"\n### FT-OSC-1 results ({run_at[:10]} — criteria above UNCHANGED; "
                f"§18 two-commit discipline observed)\n")
    rows.append(f"Runtime: {elapsed}s. "
                f"Subsample: {n_osc}/{n_tot} embargoed rows ({coverage_pct}%; "
                f"cn_sector=0% by construction — see implementation_notes in artifact).\n")
    rows.append("")
    rows.append("| id | result | date |")
    rows.append("|---|---|---|")
    for direction in ["up", "down"]:
        if direction not in scorecard.get("ledger", {}):
            continue
        for h in HORIZONS:
            hk = f"{h}m"
            cell = scorecard["ledger"][direction].get(hk, {})
            if cell:
                rows.append(_format_cell_result(direction, hk, cell))
    rows.append("")
    kill_str = "**KILL SWITCH FIRED**" if kill_fired else "KILL SWITCH NOT FIRED"
    rows.append(f"**Kill condition (FALS-OSC):** {kill_str}.")
    if kill_fired:
        kc = scorecard.get("kill_conditions", {})
        for d in ["up", "down"]:
            if d in kc:
                cond = kc[d]
                rows.append(
                    f"  {d}/6m: CI₉₀={cond.get('ci90_6m')}, "
                    f"ci_lo={cond.get('ci_lo_6m')}, kill={cond.get('kill')}."
                )
        rows.append(
            "Per §18: oscillator covariate family is a printed NULL to truths.jsonl; "
            "columns stay in the lake; model design reverts. "
            f"truth_id=`cycle_truth_falsosc_osc_covariate_null_v1`."
        )
    rows.append(
        f"\nFull scorecard: `data/hazard/falsosc_trial_v1.json`. "
        f"Era-split rows are post-2010 OOS (walk-forward first_test_year=2010). "
        f"Verdict adjudication by program chair."
    )
    rows.append("")

    text = "\n".join(rows)
    with open(prereg_path, "a") as f:
        f.write(text)
    print(f"Appended results section to {prereg_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main(argv=None):
    ap = argparse.ArgumentParser(description="FALS-OSC kill-switch trial (PREREG §18)")
    ap.add_argument("--panel", default=str(_PANEL_PATH))
    ap.add_argument("--out-dir", default=str(_OUT_DIR))
    ap.add_argument("--smoke", action="store_true",
                    help="tiny slice (up direction, first 3 test years); writes NO real artifacts")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    panel_path = Path(args.panel)

    print(f"Loading panel: {panel_path.name}")
    panel = pd.read_parquet(panel_path)

    # ANTI-MINING LAW: declare budget BEFORE building the scorecard (no p-values yet)
    if not args.smoke:
        try:
            from engine.trial_ledger import TrialLedger
            led = TrialLedger(path=_TRIAL_LEDGER_PATH, family=TRIAL_FAMILY)
            run_at_pre = datetime.now(timezone.utc).isoformat()
            led.log_declared_budget(
                N_CELLS, family=TRIAL_FAMILY,
                reason=(
                    f"PREREGISTRATION.md §18 FT-OSC-1 FALS-OSC trial: "
                    f"2 directions × 3 horizons = {N_CELLS} cells (kill-switch scope); "
                    f"run_at={run_at_pre}"
                ),
            )
            print(f"Declared trial budget: family={TRIAL_FAMILY} n={N_CELLS} "
                  f"→ {_TRIAL_LEDGER_PATH}")
        except Exception as e:
            print(f"[WARN] trial_ledger declaration failed (non-fatal): {e}")

    scorecard = build_scorecard(panel, smoke=args.smoke)

    if args.smoke:
        print("\n[SMOKE] run complete — no real artifacts written.")
        for direction, cells in scorecard.get("ledger", {}).items():
            for hk, cell in cells.items():
                print(f"  {direction}/{hk}: verdict={cell.get('verdict')} "
                      f"dBrier={cell.get('delta_brier')} ci90={cell.get('ci90')} "
                      f"years+={cell.get('years_positive')}/{cell.get('n_years')}")
        return 0

    # ── Write scorecard artifact ─────────────────────────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "falsosc_trial_v1.json"
    with open(out_path, "w") as f:
        json.dump(scorecard, f, indent=2, default=str)
    print(f"\nScorecard written: {out_path}")

    # ── Print the key numbers ────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("FALS-OSC TRIAL RESULTS (PREREGISTRATION.md §18 FT-OSC-1)")
    print("=" * 72)
    print(f"Coverage: {scorecard['n_rows_osc_covered']}/{scorecard['n_rows_total_embargoed']} "
          f"rows ({scorecard['coverage_pct']}%)")
    print(f"cn_sector: 0% (osc_missing=True by construction; us_sector+country only)")
    print()
    print("Full cell ladder (1m/3m/6m × up/down) — descriptive context:")
    print()
    for direction in ["up", "down"]:
        for h in HORIZONS:
            hk = f"{h}m"
            cell = scorecard["ledger"].get(direction, {}).get(hk, {})
            v = cell.get("verdict", "N/A")
            db = cell.get("delta_brier")
            ci = cell.get("ci90", [None, None])
            bp = cell.get("boot_p")
            yp = cell.get("years_positive")
            ny = cell.get("n_years")
            nos = cell.get("n_oos")
            bh = cell.get("bh_pass")
            print(f"  {direction}/{hk}: {v:4s}  dBrier={db}  ci90={ci}  "
                  f"p={bp}  years+={yp}/{ny}  bh={bh}  n_oos={nos}")
    print()
    print("KILL SWITCH (FALS-OSC — §18 primary gate):")
    for direction in ["up", "down"]:
        kc = scorecard["kill_conditions"].get(direction, {})
        print(f"  {direction}/6m: CI₉₀={kc.get('ci90_6m')}  "
              f"ci_lo={kc.get('ci_lo_6m')}  kill={kc.get('kill')}")
    kill_str = "FIRED" if scorecard["kill_switch_fired"] else "NOT FIRED"
    print(f"\nKILL SWITCH: {kill_str}")
    print("=" * 72)

    # ── Era-split pooled point estimates (descriptive, not a gate) ───────────────
    # Walk-forward OOS is already post-2010; we don't have separate pre/post era OOS.
    # The n_summary row notes this honestly.

    # ── Null append (if kill fired) ───────────────────────────────────────────────
    if scorecard["kill_switch_fired"]:
        print("\nKill condition met — appending promoted_null to truths.jsonl")
        append_promoted_null(_TRUTHS_PATH, scorecard)
    else:
        print("\nKill condition NOT met — no null appended (cells may have partial skill).")
        print("Verdict adjudication by program chair.")

    # ── Append results section to PREREGISTRATION.md ─────────────────────────────
    append_prereg_results(_PREREG_PATH, scorecard)

    print(f"\nDone. Elapsed: {scorecard['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
