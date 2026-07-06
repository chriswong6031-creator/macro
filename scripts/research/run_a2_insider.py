"""Entry-Stack Expansion Amendment 2 — esx_insider_sponsor Phase-0 Study.

Masterplan refs:
  - research/ENTRY_STACK_EXPANSION_AMENDMENT2_BY_FABLE.md §B RUL-20/21/22/26, §C
  - research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md (program house laws)
  - research/INSIDER_FACTOR.md §6 (adjacency prior — orthogonal confirmer verdict)

Family: esx_insider_sponsor
Budget declared: 12 (A2 RUL-26, program ceiling 115→165)
Consumed: 10 trials = {I1, I1-sens, I2, I3, I1w-reserve} × 2 panels (deep, baskets)
Reserve: 2

Pre-registered trial definitions (frozen at registration, A2 RUL-26):
  I1 (ins_cluster_washout):
    Stratum: washout_flag AND ≥2 distinct open-market buyers in 45 trading days
             prior to fire, by filing_date. Computable mask = ins_computable.
  I1-sens (ins_cluster_washout_3):
    Sensitivity: same but ≥3 buyers. Same computable mask.
  I2 (ins_cluster_pre20):
    Stratum: ≥2 distinct buyers by filing_date in [t-20td, t].
             Computable mask = ins_computable.
  I3 (ins_netusd_mcap_sn_p80):
    Stratum: trailing 6-month net_usd/mcap sector-neutral p80 (FDR-survivor
             construction). Computable mask = ins_i3_computable.

Contrast: stratum-vs-computable-rest under computable_mask (A2 §C2).
Estimator: module-level r1_estimate (entry_strata_phase0) with computable_mask.
  This path includes mae21 (co-primary), zone_held_21/stop_vol_21 (RUL-14),
  and state_rot/clean8_21 in EFFECT_OUTCOMES — unlike the fast path (run_w1_nc)
  which omits mae21 and RUL-14 co-primaries.

Grading: grade ONCE per panel (full fire set + all insider extra_columns),
  then run r1_estimate per stratum on the same graded frame. T+1 fill.
  Era tables: {2012-2015, 2016-2019, 2020-2022, 2023-2026}.
  BH q≤0.10 within-family across all 10 consumed trials (primary = stop5 + mae21).
  Block bootstrap CIs.
  Recall (stratum coverage: % of computable fires in-stratum) beside every effect.
  Survivor-bias stamp on all absolute rates.

Known-date law (A2 RUL-23, frozen):
  filing_date is the known_date for all I1/I2/I3 forms.
  ins_cluster_post15 (post-entry) is EXCLUDED per Amendment 2 §C — it is
  pit_at_entry=false and must never be used as a stratum.

CHIP promotion is IMPOSSIBLE this wave: NC-2 eq_band remains DEFERRED
(A2 §C3). Results are report-only per RUL-4.

Usage:
    cd /path/to/repo
    python scripts/research/run_a2_insider.py
    python scripts/research/run_a2_insider.py --smoke          # 50 boot, deep only
    python scripts/research/run_a2_insider.py --n-bootstrap 500
    python scripts/research/run_a2_insider.py --panel deep baskets
    python scripts/research/run_a2_insider.py --out research/entry_stack/A2_INSIDER_REPORT.md
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Harness imports
# ---------------------------------------------------------------------------
from scripts.research.entry_strata_phase0 import (  # noqa: E402
    _build_sector_map,
    _get_closes,
    _register_all_families,
    _prepare_binary_outcomes,
    _assign_era,
    compute_recall,
    grade_fires,
    load_fires,
    r1_estimate,
    bh_correction,
    FAMILY_BUDGETS,
    PROGRAM_ERAS,
    BH_Q_THRESHOLD,
    N_BOOTSTRAP,
    RNG_SEED,
    EFFECT_OUTCOMES,
)

from scripts.research.run_w1_nc import (  # noqa: E402
    _fmt_pct,
    _fmt_f,
    _ci_str,
    _excl_zero,
    _write_effect_md,
    fast_era_table,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA                   = _REPO_ROOT / "data"
_RESEARCH_DIR           = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP             = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS          = _DATA / "research" / "gate_fires_baskets.parquet"
_INSIDER_CTX_DEEP       = _DATA / "research" / "insider_fire_context_deep.parquet"
_INSIDER_CTX_BASKETS    = _DATA / "research" / "insider_fire_context_baskets.parquet"
_LEDGER_PATH            = _DATA / "trial_ledger.jsonl"

# ---------------------------------------------------------------------------
# Study constants (frozen at registration, A2 RUL-26)
# ---------------------------------------------------------------------------
FAMILY              = "esx_insider_sponsor"
BUDGET_DECLARED     = 12
BUDGET_CONSUMED     = 10
BUDGET_RESERVE      = 2

# Trial definitions: (trial_id, stratum_col, computable_mask_col, label)
TRIAL_DEFS = [
    ("I1",      "ins_cluster_washout",   "ins_computable",    "I1: cluster≥2 post-washout"),
    ("I1-sens", "ins_cluster_washout_3", "ins_computable",    "I1-sens: cluster≥3 post-washout"),
    ("I2",      "ins_cluster_pre20",     "ins_computable",    "I2: cluster≥2 near-fire (20td)"),
    ("I3",      "ins_netusd_mcap_sn_p80","ins_i3_computable", "I3: net_usd/mcap SN p≥80"),
    # RESERVE trials (registered 2026-07-05 AFTER the initial 8-trial read; see
    # RESERVE_NOTE): within-washout contrast — mask restricts BOTH arms to
    # washed-out computable fires, so the stratum isolates the cluster's
    # marginal effect vs washout-alone controls.
    ("I1w",     "ins_cluster_washout",   "ins_computable_washout",
     "I1w (RESERVE): cluster≥2 vs washout-alone (within-washout)"),
]

RESERVE_NOTE = (
    "**Reserve consumption (2026-07-05):** trials I1w x2 (deep, baskets) were "
    "registered from the family reserve AFTER the initial 8-trial read, "
    "motivated by the washout confound in I1 (its control pool includes "
    "non-washout fires, so the I1 contrast conflates the washout state with "
    "the cluster itself). The I1w mask restricts both arms to washed-out "
    "computable fires; the stratum isolates the cluster's marginal effect. "
    "Post-initial-read registration is stamped here for trial-ledger "
    "transparency; BH q<=0.10 is applied across ALL 10 consumed trials."
)

PANELS = ["deep", "baskets"]

# Insider context files per panel
_CTX_FILES = {
    "deep":    _INSIDER_CTX_DEEP,
    "baskets": _INSIDER_CTX_BASKETS,
}

# Price stores per panel
_FIRES_FILES = {
    "deep":    _FIRES_DEEP,
    "baskets": _FIRES_BASKETS,
}


# ---------------------------------------------------------------------------
# Trial-ledger registration
# ---------------------------------------------------------------------------

def _register_insider_trials(ledger_path: Path | None = None) -> None:
    """Log each A2 insider trial configuration in the esx_insider_sponsor family."""
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("trial_ledger not importable; trial rows skipped")
        return
    led = TrialLedger(path=ledger_path or _LEDGER_PATH)
    for trial_id, stratum_col, mask_col, label in TRIAL_DEFS:
        for panel in PANELS:
            cfg = {
                "trial_id":    trial_id,
                "stratum_col": stratum_col,
                "mask_col":    mask_col,
                "panel":       panel,
                "label":       label,
            }
            led.log_trial(cfg, family=FAMILY, note=f"A2 Phase-0 {trial_id} {panel}")
    log.info(
        "Logged %d trial configs in %s (declared=%d consumed=%d reserve=%d)",
        len(TRIAL_DEFS) * len(PANELS), FAMILY,
        BUDGET_DECLARED, BUDGET_CONSUMED, BUDGET_RESERVE,
    )


# ---------------------------------------------------------------------------
# Insider context loading
# ---------------------------------------------------------------------------

def load_insider_context(panel: str) -> pd.DataFrame:
    """Load insider fire context parquet for panel (join key: ticker + date).

    v1.2 columns used:
      ins_computable      — computable mask for I1/I2
      ins_cluster_washout — I1 stratum (≥2 buyers post-washout, 45td)
      ins_cluster_washout_3 — I1-sens stratum (≥3 buyers)
      ins_cluster_pre20   — I2 stratum (≥2 buyers in [t-20td, t])
      ins_netusd_mcap_sn_p80 — I3 stratum (p80 sector-neutral net_usd/mcap)
      ins_i3_computable   — computable mask for I3
      ins_cluster_post15  — EXCLUDED (pit_at_entry=False)
    """
    ctx_path = _CTX_FILES.get(panel)
    if ctx_path is None or not ctx_path.exists():
        raise FileNotFoundError(
            f"Insider context not found for panel={panel}: {ctx_path}"
        )
    ctx = pd.read_parquet(ctx_path)
    ctx["date"] = pd.to_datetime(ctx["date"])

    # Validate that pit_at_entry=False column is not used
    if "ins_cluster_post15" in ctx.columns:
        log.debug(
            "ins_cluster_post15 is present but excluded (pit_at_entry=False, A2 §C). "
            "It is descriptive-only and must never be used as a stratum."
        )

    return ctx


def _cast_stratum_col(series: pd.Series) -> pd.Series:
    """Cast stratum column to float (1.0/0.0/NaN).

    Handles:
      - bool dtype: True→1.0, False→0.0
      - object dtype with None/True/False: None→NaN, True→1.0, False→0.0
      - already float: pass through
    """
    if series.dtype == bool:
        return series.astype(float)
    # Object dtype (e.g. ins_netusd_mcap_sn_p80 with None/True/False)
    out = pd.to_numeric(series.map(lambda x: 1.0 if x is True else (0.0 if x is False else None)), errors="coerce")
    return out


# ---------------------------------------------------------------------------
# Per-stratum R1 estimation with computable mask
# ---------------------------------------------------------------------------

def _run_one_stratum(
    graded: pd.DataFrame,
    stratum_col: str,
    mask_col: str,
    sector_col: str,
    *,
    panel_name: str,
    trial_id: str,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Run R1 estimation for one stratum on the pre-graded frame.

    Uses module-level r1_estimate (with computable_mask = A2 §C2).
    Treatment = stratum fired; control = computable-but-silent; out-of-mask dropped.

    Returns per-outcome results dict including per-trial BH and recall.
    """
    df = graded.copy()

    # Cast stratum column to float
    if stratum_col not in df.columns:
        return {"error": f"stratum_col '{stratum_col}' not in graded frame", "trial_id": trial_id}
    if mask_col not in df.columns:
        return {"error": f"mask_col '{mask_col}' not in graded frame", "trial_id": trial_id}

    df[stratum_col] = _cast_stratum_col(df[stratum_col])
    df[mask_col]    = df[mask_col].astype(bool)

    computable_mask = pd.Series(df[mask_col].values, index=df.index)

    # Recall: fraction of computable-gradable fires where stratum=1
    df_computable = df[df[mask_col]].copy()
    df_computable_gradable = df_computable[df_computable["gradable"].fillna(False)]
    n_computable_gradable = len(df_computable_gradable)
    n_stratum_in_mask = int((df_computable_gradable[stratum_col] == 1.0).sum()) if n_computable_gradable > 0 else 0
    recall_val = (n_stratum_in_mask / n_computable_gradable) if n_computable_gradable > 0 else 0.0

    log.info(
        "Panel=%s trial=%s: computable_gradable=%d, stratum_in_mask=%d, recall=%.2f%%",
        panel_name, trial_id, n_computable_gradable, n_stratum_in_mask, recall_val * 100,
    )

    # Prepare binary outcomes (state_rot → rotational_liftoff, etc.)
    df_prep = _prepare_binary_outcomes(df)
    df_gradable = df_prep[df_prep["gradable"].fillna(False)].copy()

    if len(df_gradable) < 10:
        return {
            "trial_id":      trial_id,
            "stratum_col":   stratum_col,
            "mask_col":      mask_col,
            "panel":         panel_name,
            "n_computable":  n_computable_gradable,
            "n_treatment":   n_stratum_in_mask,
            "recall":        recall_val,
            "effects":       [],
            "bh_panel":      [],
            "era_table":     [],
            "note":          "insufficient gradable rows",
        }

    # Build the computable_mask aligned on gradable index
    comp_mask_gradable = pd.Series(
        df_gradable[mask_col].values,
        index=df_gradable.index,
        dtype=bool,
    )

    # Run R1 per outcome
    outcomes_to_run = [
        ("stop5",              "stop5"),
        ("mae21",              "mae21"),
        ("rotational_liftoff", "rotational_liftoff"),
        ("positional_liftoff", "positional_liftoff"),
        ("dead_money",         "dead_money"),
        ("cushion_rot",        "cushion_rot"),
        ("mae63",              "mae63"),
        ("mfe63",              "mfe63"),
        ("zone_held_21",       "zone_held_21"),
        ("stop_vol_21",        "stop_vol_21"),
    ]

    effects: list[dict[str, Any]] = []
    p_values: list[float | None] = []
    labels: list[str] = []

    for label, col in outcomes_to_run:
        if col not in df_gradable.columns:
            log.debug("Outcome '%s' not in graded frame — skipped", col)
            continue
        try:
            res = r1_estimate(
                df_gradable, col, stratum_col,
                fe_granularity="date",
                sector_col=sector_col if sector_col in df_gradable.columns else None,
                n_bootstrap=n_bootstrap,
                computable_mask=comp_mask_gradable,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("r1_estimate failed for %s/%s/%s: %s", trial_id, panel_name, col, exc)
            res = {
                "coef": None, "ci_lo": None, "ci_hi": None,
                "n_total": 0, "n_treatment": 0, "n_control": 0,
                "n_blocks": 0, "p_value": None,
                "outcome": col, "stratum": stratum_col,
                "note": str(exc),
            }
        res["label"] = label
        effects.append(res)
        p_values.append(res.get("p_value"))
        labels.append(label)

    # BH within-trial (per-trial p-values; family BH runs later across all 10 consumed trials)
    bh_within = bh_correction(p_values, labels)

    # Era table on the computable subset
    df_computable_prep = df_prep[df_prep[mask_col] & df_prep["gradable"].fillna(False)].copy()
    era_tbl = fast_era_table(df_computable_prep, stratum_col, panel_label=panel_name)
    era_records = era_tbl.to_dict(orient="records") if era_tbl is not None else []

    # Arm counts post-mask (from the first valid effect)
    n_treatment_eff = 0
    n_control_eff   = 0
    n_blocks_eff    = 0
    for eff in effects:
        if eff.get("n_treatment", 0) > 0 or eff.get("n_control", 0) > 0:
            n_treatment_eff = eff.get("n_treatment", 0)
            n_control_eff   = eff.get("n_control", 0)
            n_blocks_eff    = eff.get("n_blocks", 0)
            break

    return {
        "trial_id":      trial_id,
        "stratum_col":   stratum_col,
        "mask_col":      mask_col,
        "panel":         panel_name,
        "n_computable":  n_computable_gradable,
        "n_treatment":   n_treatment_eff,
        "n_control":     n_control_eff,
        "n_blocks":      n_blocks_eff,
        "recall":        round(recall_val, 4),
        "effects":       effects,
        "bh_panel":      bh_within,
        "era_table":     era_records,
        "survivor_stamp": (
            "SURVIVOR BIAS: absolute rates on surviving names only. "
            "Within-arm comparisons are directionally valid."
        ),
    }


# ---------------------------------------------------------------------------
# Family-wide BH correction (across all 10 consumed trials, primary outcomes)
# ---------------------------------------------------------------------------

def _family_bh(
    trial_results: list[dict[str, Any]],
    primary_outcome: str = "stop5",
) -> list[dict[str, Any]]:
    """BH FDR across all consumed trials (10 = 8 initial + 2 reserve) on the primary outcome p-values."""
    p_values: list[float | None] = []
    labels: list[str] = []
    for res in trial_results:
        effects = {e["label"]: e for e in res.get("effects", [])}
        prim = effects.get(primary_outcome, {})
        p_values.append(prim.get("p_value"))
        labels.append(f"{res['trial_id']}_{res['panel']}")
    return bh_correction(p_values, labels)


# ---------------------------------------------------------------------------
# Main study runner
# ---------------------------------------------------------------------------

def run_insider_study(
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    panels: list[str] | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Run the esx_insider_sponsor Phase-0 study across panels and trials.

    Structure:
      1. Register all families and this study's trials.
      2. For each panel: load fires + insider context, grade ONCE, run 4 strata.
      3. Family-wide BH on stop5 p-values (all 10 consumed trials).
      4. Return all results.
    """
    _register_all_families(ledger_path)
    _register_insider_trials(ledger_path)

    panels_to_run = panels or PANELS
    sector_map = _build_sector_map()
    log.info("Sector map: %d tickers", len(sector_map))

    all_panel_results: dict[str, Any] = {}

    for panel_name in panels_to_run:
        fires_path = _FIRES_FILES.get(panel_name)
        ctx_path   = _CTX_FILES.get(panel_name)

        if fires_path is None or not fires_path.exists():
            log.warning("Fire dump not found for panel=%s; skipping", panel_name)
            all_panel_results[panel_name] = {"error": f"fires not found: {fires_path}"}
            continue

        if ctx_path is None or not ctx_path.exists():
            log.warning("Insider context not found for panel=%s; skipping", panel_name)
            all_panel_results[panel_name] = {"error": f"insider_ctx not found: {ctx_path}"}
            continue

        # Load fires
        fires = load_fires(fires_path)
        log.info("Panel %s: %d fires loaded", panel_name, len(fires))

        # Load insider context and join
        ctx = load_insider_context(panel_name)
        insider_cols = [
            "ins_computable", "ins_cluster_washout", "ins_cluster_washout_3",
            "ins_cluster_pre20", "ins_netusd_mcap_sn_p80", "ins_i3_computable",
            "washout_flag",
        ]
        ctx_subset = ctx[["ticker", "date"] + [c for c in insider_cols if c in ctx.columns]]
        ctx_subset = ctx_subset.drop_duplicates(subset=["ticker", "date"])

        fires_merged = fires.merge(ctx_subset, on=["ticker", "date"], how="left")
        # Derived mask for the I1w reserve trials: computable AND washed-out.
        if "washout_flag" in fires_merged.columns:
            fires_merged["ins_computable_washout"] = (
                fires_merged["ins_computable"].fillna(False).astype(bool)
                & fires_merged["washout_flag"].fillna(False).astype(bool)
            )
        else:
            log.warning("washout_flag missing from context parquet; I1w mask empty")
            fires_merged["ins_computable_washout"] = False
        insider_cols = insider_cols + ["ins_computable_washout"]
        n_matched = fires_merged[insider_cols[0]].notna().sum() if insider_cols[0] in fires_merged.columns else 0
        log.info("Panel %s: %d/%d fires matched insider context", panel_name, n_matched, len(fires_merged))

        # Attach sector
        fires_merged["sector"] = fires_merged["ticker"].map(sector_map)

        # Load closes
        closes = _get_closes(panel_name)
        log.info("Panel %s: %d close series loaded", panel_name, len(closes))

        # Build extra_columns dict for grader
        extra_cols: dict[str, pd.Series] = {}
        for col in insider_cols:
            if col in fires_merged.columns:
                extra_cols[col] = fires_merged[col].reset_index(drop=True)

        # Grade ONCE (all fires + all insider columns attached)
        log.info("Panel %s: grading %d fires (once for all strata)...", panel_name, len(fires_merged))
        graded = grade_fires(fires_merged, closes, extra_columns=extra_cols)
        n_gradable = int(graded["gradable"].fillna(False).sum())
        log.info("Panel %s: gradable=%d/%d", panel_name, n_gradable, len(graded))

        # Add sector column to graded (for block construction)
        graded["sector"] = fires_merged["sector"].values if len(fires_merged) == len(graded) else np.nan

        # Run 4 strata on the same graded frame
        panel_trial_results: list[dict[str, Any]] = []
        for trial_id, stratum_col, mask_col, label in TRIAL_DEFS:
            log.info("Panel %s trial %s (%s)...", panel_name, trial_id, stratum_col)
            res = _run_one_stratum(
                graded, stratum_col, mask_col, "sector",
                panel_name=panel_name,
                trial_id=trial_id,
                n_bootstrap=n_bootstrap,
            )
            res["label"]      = label
            res["n_gradable"] = n_gradable
            panel_trial_results.append(res)
            log.info(
                "  Panel %s trial %s: n_treatment=%d recall=%.1f%%",
                panel_name, trial_id,
                res.get("n_treatment", 0),
                (res.get("recall") or 0) * 100,
            )

        all_panel_results[panel_name] = {
            "trials":          panel_trial_results,
            "n_fires_total":   len(fires_merged),
            "n_gradable":      n_gradable,
        }

    # Family-wide BH on stop5 across all 10 consumed trials
    all_trial_results: list[dict[str, Any]] = []
    for panel_name in panels_to_run:
        pr = all_panel_results.get(panel_name, {})
        if "error" in pr:
            continue
        all_trial_results.extend(pr.get("trials", []))

    family_bh_stop5 = _family_bh(all_trial_results, primary_outcome="stop5")
    family_bh_mae21 = _family_bh(all_trial_results, primary_outcome="mae21")

    return {
        "family":            FAMILY,
        "budget_declared":   BUDGET_DECLARED,
        "budget_consumed":   BUDGET_CONSUMED,
        "budget_reserve":    BUDGET_RESERVE,
        "panels":            all_panel_results,
        "all_trials":        all_trial_results,
        "family_bh_stop5":   family_bh_stop5,
        "family_bh_mae21":   family_bh_mae21,
    }


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def _get_effect(effects: list[dict], label: str) -> dict:
    return next((e for e in effects if e.get("label") == label), {})


def _get_bh(bh_panel: list[dict], label: str) -> dict:
    return next((b for b in bh_panel if b.get("label") == label), {})


def _ci_excl_zero(e: dict) -> bool:
    lo = e.get("ci_lo")
    hi = e.get("ci_hi")
    return lo is not None and hi is not None and (lo > 0 or hi < 0)


def write_report(study_results: dict[str, Any], out_path: Path) -> None:
    """Write A2_INSIDER_REPORT.md."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Load NC yardstick from W1_NC_REPORT.md (RUL-3)
    nc_report_path = _RESEARCH_DIR / "W1_NC_REPORT.md"
    nc_yardstick_lines: list[str] = []
    if nc_report_path.exists():
        nc_text = nc_report_path.read_text(encoding="utf-8")
        in_yardstick = False
        for line in nc_text.splitlines():
            if "## YARDSTICK" in line:
                in_yardstick = True
            if in_yardstick:
                nc_yardstick_lines.append(line)
    else:
        nc_yardstick_lines = [
            "*(W1_NC_REPORT.md not found — see that file for NC reference numbers)*"
        ]

    lines: list[str] = []
    a = lines.append

    # Header
    a("# A2 W2a — esx_insider_sponsor Phase-0 Study Report")
    a("")
    a(f"**Family:** `{study_results['family']}` "
      f"(budget declared: {study_results['budget_declared']} / "
      f"consumed: {study_results['budget_consumed']} / "
      f"reserve: {study_results['budget_reserve']})")
    a("**Status:** Phase-0 study report only — no promotion, no product change (RUL-4).")
    a("**Amendment:** Entry-Stack Expansion Amendment 2 (A2 RUL-26).")
    a("**Date:** 2026-07-05")
    a("")
    a(RESERVE_NOTE)
    a("")
    a("**CHIP PROMOTION IMPOSSIBLE THIS WAVE:** NC-2 eq_band remains DEFERRED (A2 §C3).")
    a("Results are printed, verdict section states the NC-2 incompleteness explicitly.")
    a("")
    a("---")
    a("")

    # Adjacency (RUL-2)
    a("## Adjacency Citation (R2 — RUL-2)")
    a("")
    a("**Primary prior:** `research/INSIDER_FACTOR.md` §6 — binding verdict:")
    a("> 'Ship as an ORTHOGONAL conviction/confirmer leg, expressed LONG-ONLY. "
      "NOT a standalone dollar-neutral alpha sizer. The L/S fails DSR outright.'")
    a("")
    a("This study tests whether fire-conditioned insider cluster patterns improve")
    a("stop5 (primary) and mae21 (co-primary) outcomes at 21d under the program")
    a("grader. It is a confirmer-entry study, not a standalone alpha claim.")
    a("")
    a("**Secondary prior:** SUE-insider NEUTRAL study (from INSIDER_FACTOR.md §5")
    a("and ENTRY_STACK_EXPANSION_AMENDMENT2_BY_FABLE.md §A): SUE deep-PIT IC 0.038→0.0006")
    a("(HAC t 0.06, demoted to display). Repair-layer is hostile — insider cluster")
    a("conditioned on price washout (not earnings) may be mechanically distinct.")
    a("")
    a("**Known-date law (A2 RUL-23, frozen):** `filing_date` is the known_date for")
    a("all I1/I2/I3 forms. The ≤2-business-day legal trade→file lag is the only")
    a("look-ahead risk; all windows are trading-day arithmetic (v1.1 fix).")
    a("ins_cluster_post15 (pit_at_entry=False) is EXCLUDED as a stratum.")
    a("")
    a("---")
    a("")

    # NC Yardstick (RUL-3 — FIRST table requirement)
    a("## NC Yardstick (RUL-3) — First Table")
    a("")
    a("> Per §10 RUL-3: null-competitors appear as the FIRST table in every")
    a("> subsequent W1/W2 report. Source: research/entry_stack/W1_NC_REPORT.md.")
    a("> Note which CIs are marked [proxy] or [low-block caveat].")
    a("")
    for nc_line in nc_yardstick_lines:
        a(nc_line)
    a("")
    a("---")
    a("")

    # Study design
    a("## Study Design")
    a("")
    a("**Estimator:** module-level `r1_estimate` (entry_strata_phase0.py) with")
    a("`computable_mask`. This path includes mae21 (co-primary, A2 RUL-20),")
    a("zone_held_21/stop_vol_21 (RUL-14), and state_rot in EFFECT_OUTCOMES.")
    a("")
    a("**Contrast:** stratum-vs-computable-rest. Treatment = sensor fired within")
    a("the computable universe; control = computable-but-silent. Out-of-mask")
    a("fires dropped, not zero-coded (A2 §C2 — S7 same-computable-subset discipline).")
    a("")
    a("**Grading:** ONCE per panel (T+1 fill, RUL-9) on the full fire set with")
    a("all insider extra_columns attached. All strata run on the same graded frame.")
    a("")
    a("**Era tables:** 2012-2015, 2016-2019, 2020-2022, 2023-2026.")
    a("")
    a("**BH correction:** q≤0.10 within-family across all 10 consumed trials — 8 initial + 2 reserve (stop5 primary).")
    a("")
    a("**Trial registration:**")
    a(f"- Budget declared: {BUDGET_DECLARED} | Consumed: {BUDGET_CONSUMED} "
      f"| Reserve: {BUDGET_RESERVE}")
    a("- 10 trials = {I1, I1-sens, I2, I3} × 2 panels (initial 8) + I1w reserve × 2 panels")
    a("")
    a("| Trial | Stratum col | Computable mask | Definition |")
    a("|---|---|---|---|")
    for trial_id, stratum_col, mask_col, label in TRIAL_DEFS:
        a(f"| {trial_id} | `{stratum_col}` | `{mask_col}` | {label} |")
    a("")
    a("---")
    a("")

    # Per-panel, per-trial results
    all_trials_list: list[dict[str, Any]] = study_results.get("all_trials", [])
    family_bh_stop5 = {
        b["label"]: b for b in study_results.get("family_bh_stop5", [])
    }
    family_bh_mae21 = {
        b["label"]: b for b in study_results.get("family_bh_mae21", [])
    }

    for panel_name, panel_data in study_results.get("panels", {}).items():
        a(f"## Panel: {panel_name.upper()}")
        a("")

        if "error" in panel_data:
            a(f"**ERROR:** {panel_data['error']}")
            a("")
            continue

        a("**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only.")
        a("Within-arm comparisons are directionally valid.")
        a("")
        a(f"- Total fires loaded: {panel_data.get('n_fires_total', '?'):,}")
        a(f"- Gradable fires: {panel_data.get('n_gradable', '?'):,}")
        a("")

        for trial_res in panel_data.get("trials", []):
            trial_id   = trial_res.get("trial_id", "?")
            label      = trial_res.get("label", trial_id)
            stratum_col = trial_res.get("stratum_col", "?")
            mask_col   = trial_res.get("mask_col", "?")

            a(f"### {trial_id}: {label}")
            a("")
            a(f"- Stratum column: `{stratum_col}`")
            a(f"- Computable mask: `{mask_col}`")

            if "error" in trial_res:
                a(f"**ERROR:** {trial_res['error']}")
                a("")
                continue

            n_comp    = trial_res.get("n_computable", 0)
            n_treat   = trial_res.get("n_treatment", 0)
            n_ctrl    = trial_res.get("n_control", 0)
            n_blocks  = trial_res.get("n_blocks", 0)
            recall    = trial_res.get("recall", 0.0)

            a(f"- Computable-gradable fires: {n_comp:,}")
            a(f"- N treatment (stratum=1): {n_treat:,}")
            a(f"- N control (computable-silent): {n_ctrl:,}")
            a(f"- N blocks: {n_blocks:,}")
            a(f"- **Recall (stratum coverage): {_fmt_pct(recall)}** of computable-gradable fires in-stratum")
            a("")

            if trial_res.get("note"):
                a(f"**Note:** {trial_res['note']}")
                a("")
                continue

            # Effect table
            effects   = trial_res.get("effects", [])
            bh_within = trial_res.get("bh_panel", [])
            bh_map    = {b["label"]: b for b in bh_within}

            # Build report effect table
            eff_key = f"{trial_id}_{panel_name}"
            fam_stop5 = family_bh_stop5.get(eff_key, {})
            fam_mae21 = family_bh_mae21.get(eff_key, {})

            a("#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)")
            a("")
            a(f"N total (post-mask): {n_treat + n_ctrl:,} | "
              f"N estimation sample: shown in n_treatment + n_control | "
              f"N blocks: {n_blocks:,}")
            _sf = next((e.get("sector_fallback") for e in effects
                        if e.get("sector_fallback") is not None), None)
            a(f"FE: `date` | Sector fallback to date-only blocks: "
              f"{'YES' if _sf else ('no' if _sf is not None else 'unknown')}")
            a("")

            # Primary + co-primary highlighted
            a("| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |")
            a("|---|---|---|---|---|---|---|---|---|")

            # Primary outcomes first, then remainder
            outcome_order = [
                "stop5", "mae21", "zone_held_21", "stop_vol_21",
                "rotational_liftoff", "positional_liftoff", "dead_money",
                "cushion_rot", "mae63", "mfe63",
            ]
            for oc_label in outcome_order:
                eff = _get_effect(effects, oc_label)
                if not eff:
                    continue
                bh_w = bh_map.get(oc_label, {})
                coef   = eff.get("coef")
                ci_lo  = eff.get("ci_lo")
                ci_hi  = eff.get("ci_hi")
                naive  = eff.get("naive_diff")
                p      = eff.get("p_value")
                bh_q   = bh_w.get("q_value")
                bh_rej = bh_w.get("rejected")

                # Family BH q (only for stop5 and mae21 rows)
                fam_q_stop5 = fam_stop5.get("q_value") if oc_label == "stop5" else None
                fam_q_mae21 = fam_mae21.get("q_value") if oc_label == "mae21" else None

                excl = _ci_excl_zero(eff)
                star = " *" if excl else ""

                ci_str_val = (
                    f"[{_fmt_f(ci_lo, 4)}, {_fmt_f(ci_hi, 4)}]{star}"
                    if ci_lo is not None and ci_hi is not None
                    else "—"
                )
                a(f"| {oc_label} | {_fmt_f(coef, 4)} | {ci_str_val} | "
                  f"{_fmt_f(naive, 4)} | {_fmt_f(p, 4)} | "
                  f"{_fmt_f(bh_q, 4)} | "
                  f"{_fmt_f(fam_q_stop5, 4) if fam_q_stop5 is not None else '—'} | "
                  f"{_fmt_f(fam_q_mae21, 4) if fam_q_mae21 is not None else '—'} | "
                  f"{'YES' if bh_rej else 'no' if bh_rej is not None else '—'} |")
            a("")

            # Era table
            era_recs = trial_res.get("era_table", [])
            if era_recs:
                era_df = pd.DataFrame(era_recs)
                prog = era_df[era_df["era"].isin(PROGRAM_ERAS)] if "era" in era_df.columns else era_df
                if not prog.empty:
                    a(f"#### Era Table (program eras, computable subset, {trial_id} {panel_name})")
                    a("")
                    era_cols = [c for c in [
                        "era", stratum_col, "n_fires", "stop5_rate", "mae63_mean"
                    ] if c in prog.columns]
                    a("| " + " | ".join(era_cols) + " |")
                    a("|" + "---|" * len(era_cols))
                    for _, row in prog.iterrows():
                        cells = []
                        for c in era_cols:
                            v = row.get(c)
                            if c == "stop5_rate":
                                cells.append(_fmt_pct(v))
                            elif c == "mae63_mean":
                                cells.append(_fmt_f(v))
                            else:
                                cells.append(str(v) if v is not None else "—")
                        a("| " + " | ".join(cells) + " |")
                    a("")

        a("---")
        a("")

    # Family-wide BH summary
    a("## Family-Wide BH Summary (10 consumed trials, q≤0.10)")
    a("")
    a("BH correction runs independently on stop5 (primary) and mae21 (co-primary)")
    a("across all 10 consumed trials (8 initial + 2 stamped reserve).")
    a("")
    a("**stop5 family BH:**")
    a("")
    a("| Trial | Panel | p_value | q_value | BH rej? |")
    a("|---|---|---|---|---|")
    for b in study_results.get("family_bh_stop5", []):
        lbl = b.get("label", "?")
        parts = lbl.rsplit("_", 1)
        tid = parts[0] if len(parts) == 2 else lbl
        pnl = parts[1] if len(parts) == 2 else "?"
        a(f"| {tid} | {pnl} | {_fmt_f(b.get('p_value'), 4)} | "
          f"{_fmt_f(b.get('q_value'), 4)} | {'YES' if b.get('rejected') else 'no' if b.get('rejected') is not None else '—'} |")
    a("")

    a("**mae21 family BH:**")
    a("")
    a("| Trial | Panel | p_value | q_value | BH rej? |")
    a("|---|---|---|---|---|")
    for b in study_results.get("family_bh_mae21", []):
        lbl = b.get("label", "?")
        parts = lbl.rsplit("_", 1)
        tid = parts[0] if len(parts) == 2 else lbl
        pnl = parts[1] if len(parts) == 2 else "?"
        a(f"| {tid} | {pnl} | {_fmt_f(b.get('p_value'), 4)} | "
          f"{_fmt_f(b.get('q_value'), 4)} | {'YES' if b.get('rejected') else 'no' if b.get('rejected') is not None else '—'} |")
    a("")
    a("---")
    a("")

    # Verdict
    a("## Verdict (Phase-0)")
    a("")
    a("**CHIP promotion bar (A2 RUL-21):** stop5 FE-coef ≥2pp, CI excluding 0,")
    a("BH q≤0.10 within the declared family, sign-stable ≥3/4 eras, n≥400 treatment,")
    a("beats NC-1 AND NC-2, MFE/|MAE| conjunctive.")
    a("")
    a("**NC-2 eq_band status:** DEFERRED (A2 §C3, cycles.py pipeline required).")
    a("CHIP promotion is therefore **impossible this wave regardless of results**.")
    a("No promotion decision can be made until NC-2 is computable.")
    a("")
    a("**Null result declaration:** Any trial with CI-including-0 on stop5 is a NULL.")
    a("Nulls are printed above, not hidden. A null is informative: insider clustering")
    a("conditional on fire does not demonstrably improve stop5 at this sample size.")
    a("")
    a("**Recall note:** I1/I1-sens/I2 are rare events (<<5% of computable fires).")
    a("I3 has higher recall but n_treatment is still limited by the computable universe.")
    a("Low n_treatment limits power; CI-including-0 does not rule out a true effect.")
    a("")
    a("**Era sign-stability note (RUL-21):** ≥3/4 eras required for CHIP. Check era")
    a("tables above for directional consistency.")
    a("")
    a("No promotion language. Report only (RUL-4). These results inform Amendment 2")
    a("come-back scheduling and the esx_support_dose dose-response study (RUL-25).")
    a("")
    a("---")
    a("")
    a("*Generated by `scripts/research/run_a2_insider.py`*")
    a("*Grader: engine/grading.py (program barriers, RUL-9). T+1 fill.*")
    a("*'validated' word deliberately absent (CI-enforced).*")
    a("*No promotion language. Phase-0 study report only.*")
    a(f"*Family: {FAMILY} | Budget declared: {BUDGET_DECLARED} | "
      f"Consumed: {BUDGET_CONSUMED} | Reserve: {BUDGET_RESERVE}*")
    a("*CHIP promotion impossible this wave: NC-2 eq_band DEFERRED (A2 §C3).*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote %s", out_path)
    try:
        import json as _json

        def _np_safe(o):
            import numpy as _np
            if isinstance(o, (_np.integer,)):
                return int(o)
            if isinstance(o, (_np.floating,)):
                return float(o)
            if isinstance(o, (_np.bool_,)):
                return bool(o)
            if isinstance(o, _np.ndarray):
                return o.tolist()
            return str(o)

        _json_path = out_path.with_suffix(".results.json")
        _json_path.write_text(_json.dumps(study_results, default=_np_safe, indent=1))
        log.info("Wrote %s", _json_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("results JSON dump failed (report unaffected): %s", exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Entry-Stack Expansion A2 — esx_insider_sponsor Phase-0 Study.",
    )
    parser.add_argument(
        "--out",
        default=str(_RESEARCH_DIR / "A2_INSIDER_REPORT.md"),
        help="Output path for A2_INSIDER_REPORT.md",
    )
    parser.add_argument(
        "--n-bootstrap", type=int, default=1000,
        help="Block-bootstrap resamples (default 1000; --smoke uses 50)",
    )
    parser.add_argument(
        "--panel", nargs="+", choices=["deep", "baskets"],
        default=None,
        help="Restrict to named panel(s); default runs all.",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Quick smoke test: 50 bootstrap, deep panel only.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    n_boot = 50 if args.smoke else args.n_bootstrap
    panels = ["deep"] if args.smoke else args.panel

    log.info(
        "Starting A2 insider study (family=%s, n_bootstrap=%d, panels=%s)",
        FAMILY, n_boot, panels or "all",
    )

    results = run_insider_study(n_bootstrap=n_boot, panels=panels)
    write_report(results, Path(args.out))
    log.info("Done. Report at %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
