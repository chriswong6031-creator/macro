"""Entry-Stack Expansion Amendment 2 — esx_macro_release + esx_pos_reset Phase-0.

Masterplan refs:
  - research/ENTRY_STACK_EXPANSION_AMENDMENT2_BY_FABLE.md §B RUL-20/21/22/24/25/26
  - research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md (program house laws)

Families:
  esx_macro_release (Tier B, R1-M, RUL-22):
    Budget declared: 8. Consumed: 8.
    Trials = {M1 macro_m1_fsi_turn, M2 macro_m2_oas_turn} × {deep, baskets}
             × 2 contrasts:
      (A) turn-vs-rest over ALL fires in date-panel coverage
      (B) turn-vs-elevated-not-turning: mask = elevated-stress dates
          (M1: ofr_fsi_pctile_exp ≥ 0.80; M2: hy_oas_pctile_exp ≥ 0.80),
          both arms restricted to elevated dates — TURN is isolated from the
          elevation itself (market-level analog of the I1w within-washout contrast).

  esx_pos_reset (Tier B, R1-M, RUL-22):
    Budget declared: 8. Consumed: 4. Reserve: 4.
    Contrast B is NOT computable from v1.1 panel — pctile columns for NAAIM
    and COT (raw trailing-3y pctile series) are not exported; only the derived
    binary reset flags are present. Reserve 4 trials (contrast B × 2 panels).
    Trials run = {P1 pos_p1_naaim_reset, P2 pos_p2_cot_reset} × {deep, baskets}
             × 1 contrast:
      (A) reset-vs-rest over fires where the flag is non-null (full coverage
          since 2002 per panel meta, but inherits pctile warm-up ~1999-2002
          handled by the flag's own construction).

Estimator: r1m_estimate per RUL-24.
  Per-trial pre-registered controls (RUL-24 shared-source exclusion):
    M1 → ["vix", "spy_dd126", "hy_oas"]
    M2 → ["vix", "spy_dd126"]         (hy_oas is the treatment source → excluded)
    P1, P2 → ["vix", "spy_dd126"]

Outcomes: stop5 (primary), mae21 (co-primary), plus: zone_held_21, stop_vol_21,
  state_rot/state_pos/dead_money, mfe63.

Era tables per trial. BH q≤0.10 within each family separately (RUL-21: BH
family = declared budget, NOT union across families).

Recall = flag base-rate among sampled (non-null) fires.

Deploy-ceiling: these are regime-conditioning CONTEXT families (RUL-24) —
they can NEVER become ticker-level chips. This is printed in the report.

Join mechanics: merge date panel onto fires by date; grade ONCE per panel
with flag columns as extra_columns; r1m_estimate per trial with null-date drops.

Usage:
    cd /path/to/repo
    python scripts/research/run_a2_macro_pos.py
    python scripts/research/run_a2_macro_pos.py --smoke       # 50 boot, deep only
    python scripts/research/run_a2_macro_pos.py --n-bootstrap 500
    python scripts/research/run_a2_macro_pos.py --panel deep baskets
    python scripts/research/run_a2_macro_pos.py --out research/entry_stack/A2_MACRO_POS_REPORT.md
"""
from __future__ import annotations

import argparse
import json
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
    grade_fires,
    load_fires,
    r1m_estimate,
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
_DATA             = _REPO_ROOT / "data"
_RESEARCH_DIR     = _REPO_ROOT / "research" / "entry_stack"
_FIRES_DEEP       = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS    = _DATA / "research" / "gate_fires_baskets.parquet"
_MACRO_CTX        = _DATA / "research" / "macro_fire_context.parquet"
_MACRO_CTX_META   = _DATA / "research" / "macro_fire_context_meta.json"
_LEDGER_PATH      = _DATA / "trial_ledger.jsonl"

_FIRES_FILES = {
    "deep":    _FIRES_DEEP,
    "baskets": _FIRES_BASKETS,
}

# ---------------------------------------------------------------------------
# Study constants (frozen at registration, A2 RUL-26)
# ---------------------------------------------------------------------------

# ---- esx_macro_release ----
FAMILY_MACRO       = "esx_macro_release"
BUDGET_MACRO_DECL  = 8
BUDGET_MACRO_CONS  = 8   # 4 trials × 2 panels
BUDGET_MACRO_RES   = 0

# Pre-registered controls per trial (RUL-24 shared-source exclusion).
# M1 (FSI turn): drops FSI-family control; retains vix + spy_dd126 + hy_oas level.
# M2 (OAS turn): drops OAS-derived control; retains vix + spy_dd126 only.
_MACRO_CONTROLS = {
    "M1": ["vix", "spy_dd126", "hy_oas"],
    "M2": ["vix", "spy_dd126"],
}

# Macro trial definitions:
#   (trial_id, stratum_col, contrast, mask_col_or_None, label, controls_key)
# Contrast A: no mask (all fires in panel coverage, null-flag dates dropped)
# Contrast B: mask restricts both arms to elevated-stress dates
#             (M1: ofr_fsi_pctile_exp >= 0.80; M2: hy_oas_pctile_exp >= 0.80)
MACRO_TRIAL_DEFS = [
    # M1 — FSI turn
    ("M1-A", "macro_m1_fsi_turn", "A", None,
     "M1-A: FSI turn vs rest (all fires)", "M1"),
    ("M1-B", "macro_m1_fsi_turn", "B", "mask_m1_elevated",
     "M1-B: FSI turn vs elevated-not-turning (within-elevated mask)", "M1"),
    # M2 — HY-OAS turn
    ("M2-A", "macro_m2_oas_turn", "A", None,
     "M2-A: HY-OAS turn vs rest (all fires)", "M2"),
    ("M2-B", "macro_m2_oas_turn", "B", "mask_m2_elevated",
     "M2-B: HY-OAS turn vs elevated-not-turning (within-elevated mask)", "M2"),
]

# ---- esx_pos_reset ----
FAMILY_POS        = "esx_pos_reset"
BUDGET_POS_DECL   = 8
BUDGET_POS_CONS   = 4   # contrast A only × 2 panels; contrast B = reserve
BUDGET_POS_RES    = 4

POS_CONTRAST_B_NOTE = (
    "**Contrast B uncomputable from v1.1 panel — pctile columns not exported; "
    "reserve 4.** "
    "The v1.1 panel exports only the derived binary reset flags "
    "(pos_p1_naaim_reset, pos_p2_cot_reset). The raw trailing-3y percentile "
    "series needed to build a washout-level mask (pctile ≤ 0.20) are NOT "
    "present. Contrast B requires those series to restrict both arms to "
    "washout-present dates. Per the bind-first law (Amendment 2 §C), no "
    "recomputation of feeds is permitted. 4 trials (P1-B and P2-B × 2 panels) "
    "are reserved for the v1.2 panel release."
)

# Pos trial definitions (contrast A only):
#   (trial_id, stratum_col, controls_key, label)
POS_TRIAL_DEFS = [
    ("P1-A", "pos_p1_naaim_reset", "P",
     "P1-A: NAAIM reset vs rest (all fires, post-warmup)"),
    ("P2-A", "pos_p2_cot_reset", "P",
     "P2-A: COT reset vs rest (all fires, post-warmup)"),
]

# Pre-registered controls for all pos trials (no shared-source exclusion)
_POS_CONTROLS = ["vix", "spy_dd126"]

PANELS = ["deep", "baskets"]

# ---------------------------------------------------------------------------
# Outcomes to sweep (same pattern as insider runner; R1-M variant)
# ---------------------------------------------------------------------------
_OUTCOME_SWEEP = [
    "stop5",            # primary
    "mae21",            # co-primary (RUL-13)
    "zone_held_21",     # co-primary (RUL-14)
    "stop_vol_21",      # co-primary (RUL-14)
    "rotational_liftoff",
    "positional_liftoff",
    "dead_money",
    "mfe63",
]


# ---------------------------------------------------------------------------
# Panel metadata helpers
# ---------------------------------------------------------------------------

def _load_macro_ctx() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load the macro/pos date panel and its metadata."""
    if not _MACRO_CTX.exists():
        raise FileNotFoundError(f"macro_fire_context.parquet not found: {_MACRO_CTX}")
    ctx = pd.read_parquet(_MACRO_CTX)
    ctx.index = pd.to_datetime(ctx.index)
    meta: dict[str, Any] = {}
    if _MACRO_CTX_META.exists():
        try:
            meta = json.loads(_MACRO_CTX_META.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not load macro_fire_context_meta.json: %s", exc)
    return ctx, meta


def _build_elevated_masks(ctx: pd.DataFrame) -> pd.DataFrame:
    """Derive contrast-B mask columns from existing pctile columns.

    M1 mask: ofr_fsi_pctile_exp >= 0.80  (both M1 arms restricted to elevated FSI)
    M2 mask: hy_oas_pctile_exp  >= 0.80  (both M2 arms restricted to elevated OAS)

    Both masks are pre-registered (RUL-26; Amendment 2 §B Table): they define
    the ELEVATION level that must already be present for the turn to be the
    marginal isolating feature — the market-level analog of I1w within-washout.
    """
    ctx = ctx.copy()
    if "ofr_fsi_pctile_exp" in ctx.columns:
        ctx["mask_m1_elevated"] = (ctx["ofr_fsi_pctile_exp"] >= 0.80).astype(float)
    else:
        log.warning("ofr_fsi_pctile_exp absent from panel — mask_m1_elevated = 0 (contrast B uncomputable)")
        ctx["mask_m1_elevated"] = 0.0

    if "hy_oas_pctile_exp" in ctx.columns:
        ctx["mask_m2_elevated"] = (ctx["hy_oas_pctile_exp"] >= 0.80).astype(float)
    else:
        log.warning("hy_oas_pctile_exp absent from panel — mask_m2_elevated = 0 (contrast B uncomputable)")
        ctx["mask_m2_elevated"] = 0.0

    return ctx


# ---------------------------------------------------------------------------
# Trial-ledger registration
# ---------------------------------------------------------------------------

def _register_macro_pos_trials(ledger_path: Path | None = None) -> None:
    """Log each A2 macro/pos trial in the respective families. Append-only."""
    try:
        from engine.trial_ledger import TrialLedger
    except ImportError:
        log.warning("trial_ledger not importable; trial rows skipped")
        return

    led = TrialLedger(path=ledger_path or _LEDGER_PATH)

    # esx_macro_release
    for trial_id, stratum_col, contrast, mask_col, label, ctrl_key in MACRO_TRIAL_DEFS:
        for panel in PANELS:
            cfg = {
                "trial_id":    trial_id,
                "stratum_col": stratum_col,
                "contrast":    contrast,
                "mask_col":    mask_col,
                "panel":       panel,
                "label":       label,
                "controls":    _MACRO_CONTROLS[ctrl_key],
                "estimator":   "r1m",
            }
            led.log_trial(cfg, family=FAMILY_MACRO,
                          note=f"A2 Phase-0 {trial_id} {panel} (R1-M, RUL-24)")

    # esx_pos_reset (contrast A only; B reserved)
    for trial_id, stratum_col, ctrl_key, label in POS_TRIAL_DEFS:
        for panel in PANELS:
            cfg = {
                "trial_id":    trial_id,
                "stratum_col": stratum_col,
                "contrast":    "A",
                "panel":       panel,
                "label":       label,
                "controls":    _POS_CONTROLS,
                "estimator":   "r1m",
            }
            led.log_trial(cfg, family=FAMILY_POS,
                          note=f"A2 Phase-0 {trial_id} {panel} (R1-M, RUL-24)")

    log.info(
        "Logged %d macro trials (%s) + %d pos trials (%s) to ledger",
        len(MACRO_TRIAL_DEFS) * len(PANELS), FAMILY_MACRO,
        len(POS_TRIAL_DEFS) * len(PANELS), FAMILY_POS,
    )


# ---------------------------------------------------------------------------
# Core per-trial R1-M runner
# ---------------------------------------------------------------------------

def _run_r1m_trial(
    graded: pd.DataFrame,
    stratum_col: str,
    controls: list[str],
    *,
    panel_name: str,
    trial_id: str,
    mask_col: str | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, Any]:
    """Run R1-M for one trial on the pre-graded + macro-joined frame.

    For contrast B trials, computable_mask is set to the mask column so both
    arms are restricted to elevated-stress dates (the isolation target).

    Sample restriction (null-flag dates):
      Fires whose date has null flag value for stratum_col are already NaN
      in the merged frame. r1m_estimate drops them via the dropna() on the
      required columns. No extra explicit drop needed — but we compute n_dropped
      explicitly for the report.
    """
    df = graded.copy()

    if stratum_col not in df.columns:
        return {
            "trial_id": trial_id, "panel": panel_name,
            "error": f"stratum_col '{stratum_col}' not in graded frame",
        }
    for c in controls:
        if c not in df.columns:
            return {
                "trial_id": trial_id, "panel": panel_name,
                "error": f"control column '{c}' not in graded frame",
            }

    # Compute recall: fraction of non-null-flag, gradable fires where flag=1
    df_nonnull = df[df[stratum_col].notna() & df["gradable"].fillna(False)].copy()
    n_nonnull = len(df_nonnull)
    n_flag_on = int((df_nonnull[stratum_col].astype(float) == 1.0).sum()) if n_nonnull > 0 else 0
    recall_val = n_flag_on / n_nonnull if n_nonnull > 0 else 0.0

    # Count null-flag drops
    n_null_flag = int(df["gradable"].fillna(False).sum()) - n_nonnull

    log.info(
        "Panel=%s trial=%s: nonnull_gradable=%d flag_on=%d recall=%.2f%% null_flag_drops=%d",
        panel_name, trial_id, n_nonnull, n_flag_on, recall_val * 100, n_null_flag,
    )

    # Computable mask for contrast B
    computable_mask: pd.Series | None = None
    if mask_col is not None:
        if mask_col not in df.columns:
            return {
                "trial_id": trial_id, "panel": panel_name,
                "error": f"mask_col '{mask_col}' not in graded frame",
            }
        computable_mask = df[mask_col].fillna(0.0).astype(bool)

    # Prepare binary outcomes
    df_prep = _prepare_binary_outcomes(df)
    df_gradable = df_prep[df_prep["gradable"].fillna(False)].copy()

    if len(df_gradable) < 10:
        return {
            "trial_id":    trial_id,
            "panel":       panel_name,
            "stratum_col": stratum_col,
            "controls":    controls,
            "n_nonnull":   n_nonnull,
            "n_flag_on":   n_flag_on,
            "recall":      recall_val,
            "effects":     [],
            "bh_within":   [],
            "era_table":   [],
            "note":        "insufficient gradable rows",
        }

    # Align computable_mask to gradable index
    comp_mask_gradable: pd.Series | None = None
    if computable_mask is not None:
        comp_mask_gradable = pd.Series(
            computable_mask.reindex(df_gradable.index).fillna(False).values,
            index=df_gradable.index, dtype=bool,
        )

    # Run R1-M across outcome sweep
    effects: list[dict[str, Any]] = []
    p_values: list[float | None] = []
    eff_labels: list[str] = []

    for oc in _OUTCOME_SWEEP:
        if oc not in df_gradable.columns:
            log.debug("Outcome '%s' not in graded frame — skipped (trial=%s)", oc, trial_id)
            continue
        try:
            res = r1m_estimate(
                df_gradable, oc, stratum_col, controls,
                n_bootstrap=n_bootstrap,
                rng_seed=RNG_SEED,
                computable_mask=comp_mask_gradable,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("r1m_estimate failed for %s/%s/%s: %s", trial_id, panel_name, oc, exc)
            res = {
                "coef": None, "ci_lo": None, "ci_hi": None,
                "n_total": 0, "n_treatment": 0, "n_control": 0,
                "n_blocks": 0, "p_value": None,
                "outcome": oc, "stratum": stratum_col,
                "controls_used": controls,
                "mask_n_dropped": 0, "mask_coverage": 1.0,
                "note": str(exc),
            }
        res["label"] = oc
        effects.append(res)
        p_values.append(res.get("p_value"))
        eff_labels.append(oc)

    # Within-trial BH (informational)
    bh_within = bh_correction(p_values, eff_labels)

    # Era table on the non-null flag subset
    df_nonnull_prep = df_prep[df_prep[stratum_col].notna() & df_prep["gradable"].fillna(False)].copy()
    era_tbl = fast_era_table(df_nonnull_prep, stratum_col, panel_label=panel_name)
    era_records = era_tbl.to_dict(orient="records") if era_tbl is not None else []

    # Pull arm counts from first valid effect
    n_treatment_eff = n_control_eff = n_blocks_eff = 0
    for eff in effects:
        if eff.get("n_treatment", 0) > 0 or eff.get("n_control", 0) > 0:
            n_treatment_eff = eff.get("n_treatment", 0)
            n_control_eff   = eff.get("n_control", 0)
            n_blocks_eff    = eff.get("n_blocks", 0)
            break

    return {
        "trial_id":     trial_id,
        "panel":        panel_name,
        "stratum_col":  stratum_col,
        "controls":     controls,
        "n_nonnull":    n_nonnull,
        "n_null_drops": n_null_flag,
        "n_flag_on":    n_flag_on,
        "recall":       round(recall_val, 4),
        "n_treatment":  n_treatment_eff,
        "n_control":    n_control_eff,
        "n_blocks":     n_blocks_eff,
        "effects":      effects,
        "bh_within":    bh_within,
        "era_table":    era_records,
        "survivor_stamp": (
            "SURVIVOR BIAS: absolute rates on surviving names only. "
            "Within-arm comparisons are directionally valid."
        ),
    }


# ---------------------------------------------------------------------------
# Family-wide BH
# ---------------------------------------------------------------------------

def _family_bh_on(
    trial_results: list[dict[str, Any]],
    primary_outcome: str,
) -> list[dict[str, Any]]:
    """BH FDR across all consumed trials for one primary outcome."""
    p_values: list[float | None] = []
    labels:   list[str] = []
    for res in trial_results:
        effects_map = {e["label"]: e for e in res.get("effects", [])}
        prim = effects_map.get(primary_outcome, {})
        p_values.append(prim.get("p_value"))
        labels.append(f"{res.get('trial_id', '?')}_{res.get('panel', '?')}")
    return bh_correction(p_values, labels)


# ---------------------------------------------------------------------------
# Main study runner
# ---------------------------------------------------------------------------

def _run_family(
    family: str,
    trial_defs_iter,   # yields (trial_id, stratum_col, controls, mask_col_or_None, label)
    panels_to_run: list[str],
    macro_ctx: pd.DataFrame,
    extra_ctx_cols: list[str],
    *,
    n_bootstrap: int,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Run one family across panels and trials.

    macro_ctx: date-indexed panel with flag + control columns.
    extra_ctx_cols: which columns to join as extra_columns in grade_fires.
    """
    all_panel_results: dict[str, Any] = {}

    for panel_name in panels_to_run:
        fires_path = _FIRES_FILES.get(panel_name)
        if fires_path is None or not fires_path.exists():
            log.warning("Fire dump not found for panel=%s; skipping", panel_name)
            all_panel_results[panel_name] = {"error": f"fires not found: {fires_path}"}
            continue

        fires = load_fires(fires_path)
        log.info("Panel %s: %d fires loaded (family=%s)", panel_name, len(fires), family)

        # Join date panel onto fires by date
        ctx_reset = macro_ctx.reset_index()
        ctx_reset.columns = ["date"] + list(macro_ctx.columns)
        ctx_reset["date"] = pd.to_datetime(ctx_reset["date"])
        fires["date"] = pd.to_datetime(fires["date"])

        # Select columns: flag + controls + mask columns
        ctx_cols_to_join = [c for c in extra_ctx_cols if c in ctx_reset.columns]
        ctx_sub = ctx_reset[["date"] + ctx_cols_to_join].drop_duplicates(subset=["date"])

        fires_merged = fires.merge(ctx_sub, on="date", how="left")

        n_joined = fires_merged[extra_ctx_cols[0]].notna().sum() if extra_ctx_cols else len(fires_merged)
        log.info(
            "Panel %s family=%s: %d/%d fires matched date panel",
            panel_name, family, n_joined, len(fires_merged),
        )

        # Load closes
        closes = _get_closes(panel_name)
        log.info("Panel %s: %d close series loaded", panel_name, len(closes))

        # Build extra_columns dict
        extra_cols: dict[str, pd.Series] = {}
        for col in extra_ctx_cols:
            if col in fires_merged.columns:
                extra_cols[col] = fires_merged[col].reset_index(drop=True)

        # Grade ONCE
        log.info("Panel %s family=%s: grading %d fires...", panel_name, family, len(fires_merged))
        graded = grade_fires(fires_merged, closes, extra_columns=extra_cols)
        n_gradable = int(graded["gradable"].fillna(False).sum())
        log.info("Panel %s family=%s: gradable=%d/%d", panel_name, family, n_gradable, len(graded))

        # Run trials
        panel_trial_results: list[dict[str, Any]] = []
        for td in trial_defs_iter(panel_name):
            trial_id, stratum_col, controls, mask_col, label = td
            log.info("Panel %s family=%s trial %s...", panel_name, family, trial_id)
            res = _run_r1m_trial(
                graded, stratum_col, controls,
                panel_name=panel_name,
                trial_id=trial_id,
                mask_col=mask_col,
                n_bootstrap=n_bootstrap,
            )
            res["label"] = label
            res["n_gradable"] = n_gradable
            panel_trial_results.append(res)
            log.info(
                "  Panel %s trial %s: n_treatment=%d recall=%.1f%%",
                panel_name, trial_id,
                res.get("n_treatment", 0),
                (res.get("recall") or 0) * 100,
            )

        all_panel_results[panel_name] = {
            "trials":        panel_trial_results,
            "n_fires_total": len(fires_merged),
            "n_gradable":    n_gradable,
        }

    # Flatten all trial results for family BH
    all_trial_results: list[dict[str, Any]] = []
    for panel_name in panels_to_run:
        pr = all_panel_results.get(panel_name, {})
        if "error" not in pr:
            all_trial_results.extend(pr.get("trials", []))

    family_bh_stop5 = _family_bh_on(all_trial_results, "stop5")
    family_bh_mae21 = _family_bh_on(all_trial_results, "mae21")

    return {
        "family":          family,
        "panels":          all_panel_results,
        "all_trials":      all_trial_results,
        "family_bh_stop5": family_bh_stop5,
        "family_bh_mae21": family_bh_mae21,
    }


def run_macro_pos_study(
    *,
    n_bootstrap: int = N_BOOTSTRAP,
    panels: list[str] | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Run both esx_macro_release and esx_pos_reset Phase-0 studies.

    Returns combined results dict with keys:
        macro_results, pos_results, contrast_b_computable (per family),
        budget accounting.
    """
    _register_all_families(ledger_path)
    _register_macro_pos_trials(ledger_path)

    panels_to_run = panels or PANELS

    # Load date panel
    macro_ctx, meta = _load_macro_ctx()
    macro_ctx = _build_elevated_masks(macro_ctx)
    log.info("Date panel loaded: %d rows, columns=%s", len(macro_ctx), list(macro_ctx.columns))

    # All columns needed (controls + flags + mask cols)
    _all_macro_ctx_cols = [
        "vix", "spy_dd126", "hy_oas",
        "macro_m1_fsi_turn", "macro_m2_oas_turn",
        "pos_p1_naaim_reset", "pos_p2_cot_reset",
        "mask_m1_elevated", "mask_m2_elevated",
    ]

    # --- esx_macro_release ---
    def macro_trial_iter(panel_name):  # noqa: ARG001
        for (trial_id, stratum_col, contrast, mask_col, label, ctrl_key) in MACRO_TRIAL_DEFS:
            yield (trial_id, stratum_col, _MACRO_CONTROLS[ctrl_key], mask_col, label)

    macro_results = _run_family(
        FAMILY_MACRO,
        macro_trial_iter,
        panels_to_run,
        macro_ctx,
        _all_macro_ctx_cols,
        n_bootstrap=n_bootstrap,
        ledger_path=ledger_path,
    )
    macro_results["budget_declared"] = BUDGET_MACRO_DECL
    macro_results["budget_consumed"] = BUDGET_MACRO_CONS
    macro_results["budget_reserve"]  = BUDGET_MACRO_RES
    macro_results["contrast_b_computable"] = True

    # --- esx_pos_reset ---
    def pos_trial_iter(panel_name):  # noqa: ARG001
        for (trial_id, stratum_col, ctrl_key, label) in POS_TRIAL_DEFS:
            yield (trial_id, stratum_col, _POS_CONTROLS, None, label)

    pos_results = _run_family(
        FAMILY_POS,
        pos_trial_iter,
        panels_to_run,
        macro_ctx,
        _all_macro_ctx_cols,
        n_bootstrap=n_bootstrap,
        ledger_path=ledger_path,
    )
    pos_results["budget_declared"] = BUDGET_POS_DECL
    pos_results["budget_consumed"] = BUDGET_POS_CONS
    pos_results["budget_reserve"]  = BUDGET_POS_RES
    pos_results["contrast_b_computable"] = False
    pos_results["contrast_b_note"]       = POS_CONTRAST_B_NOTE

    return {
        "macro_results": macro_results,
        "pos_results":   pos_results,
        "panel_meta":    meta,
    }


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def _ci_excl_zero(e: dict) -> bool:
    lo = e.get("ci_lo")
    hi = e.get("ci_hi")
    return lo is not None and hi is not None and (lo > 0 or hi < 0)


def _write_trial_section(
    lines: list[str],
    trial_res: dict[str, Any],
    family_bh_stop5: dict[str, Any],
    family_bh_mae21: dict[str, Any],
) -> None:
    """Write one trial's result block into the lines list."""
    a = lines.append
    trial_id   = trial_res.get("trial_id", "?")
    panel_name = trial_res.get("panel", "?")
    label      = trial_res.get("label", trial_id)
    stratum_col = trial_res.get("stratum_col", "?")
    controls   = trial_res.get("controls", [])

    a(f"### {trial_id}: {label}")
    a("")
    a(f"- Stratum column: `{stratum_col}`")
    a(f"- Controls: {controls}")

    if "error" in trial_res:
        a(f"**ERROR:** {trial_res['error']}")
        a("")
        return

    n_nonnull  = trial_res.get("n_nonnull", 0)
    n_drops    = trial_res.get("n_null_drops", 0)
    n_flag_on  = trial_res.get("n_flag_on", 0)
    n_treat    = trial_res.get("n_treatment", 0)
    n_ctrl     = trial_res.get("n_control", 0)
    n_blocks   = trial_res.get("n_blocks", 0)
    recall     = trial_res.get("recall", 0.0)

    a(f"- Non-null flag + gradable fires: {n_nonnull:,}")
    a(f"- Null-flag drops (pre-coverage excluded): {n_drops:,}")
    a(f"- N flag=1 (treatment fires): {n_flag_on:,}")
    a(f"- N treatment (estimation): {n_treat:,} | N control: {n_ctrl:,} | N blocks: {n_blocks:,}")
    a(f"- **Recall (flag base-rate): {_fmt_pct(recall)}** of non-null gradable fires")
    a("")

    if trial_res.get("note"):
        a(f"**Note:** {trial_res['note']}")
        a("")
        return

    effects    = trial_res.get("effects", [])
    bh_within  = {b["label"]: b for b in trial_res.get("bh_within", [])}

    eff_key     = f"{trial_id}_{panel_name}"
    fam_stop5   = family_bh_stop5.get(eff_key, {})
    fam_mae21   = family_bh_mae21.get(eff_key, {})

    a("#### Effect Table (R1-M, block bootstrap, Frisch-Waugh controls partialled)")
    a("")
    a(f"N total: {n_treat + n_ctrl:,} | N blocks: {n_blocks:,} | Estimator: R1-M (no date FE, RUL-24)")
    a("")
    a("| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | Excl 0? |")
    a("|---|---|---|---|---|---|---|---|---|")

    for eff in effects:
        oc     = eff.get("label", "?")
        coef   = eff.get("coef")
        ci_lo  = eff.get("ci_lo")
        ci_hi  = eff.get("ci_hi")
        naive  = eff.get("naive_diff")
        p      = eff.get("p_value")
        bh_w   = bh_within.get(oc, {})
        bh_q   = bh_w.get("q_value")

        # Family BH q only for primary outcomes
        fam_q_stop5 = fam_stop5.get("q_value") if oc == "stop5" else None
        fam_q_mae21 = fam_mae21.get("q_value") if oc == "mae21" else None

        excl = _ci_excl_zero(eff)
        star = " *" if excl else ""

        ci_str_val = (
            f"[{_fmt_f(ci_lo, 4)}, {_fmt_f(ci_hi, 4)}]{star}"
            if ci_lo is not None and ci_hi is not None else "—"
        )
        a(f"| {oc} | {_fmt_f(coef, 4)} | {ci_str_val} | "
          f"{_fmt_f(naive, 4)} | {_fmt_f(p, 4)} | "
          f"{_fmt_f(bh_q, 4)} | "
          f"{_fmt_f(fam_q_stop5, 4) if fam_q_stop5 is not None else '—'} | "
          f"{_fmt_f(fam_q_mae21, 4) if fam_q_mae21 is not None else '—'} | "
          f"{'YES *' if excl else 'no'} |")
    a("")

    # Era table
    era_recs = trial_res.get("era_table", [])
    if era_recs:
        era_df = pd.DataFrame(era_recs)
        prog   = era_df[era_df["era"].isin(PROGRAM_ERAS)] if "era" in era_df.columns else era_df
        if not prog.empty:
            a(f"#### Era Table ({trial_id} {panel_name}, non-null flag subset)")
            a("")
            era_cols = [c for c in ["era", stratum_col, "n_fires", "stop5_rate", "mae63_mean"]
                        if c in prog.columns]
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


def _write_family_bh_section(
    lines: list[str],
    family_name: str,
    budget_declared: int,
    budget_consumed: int,
    budget_reserve: int,
    family_bh_stop5: list[dict[str, Any]],
    family_bh_mae21: list[dict[str, Any]],
) -> None:
    a = lines.append
    a(f"## Family-Wide BH Summary — `{family_name}` "
      f"(declared={budget_declared}, consumed={budget_consumed}, reserve={budget_reserve})")
    a("")
    a("BH q≤0.10 applied within each family independently (RUL-21: BH family = declared budget).")
    a("")
    a("**stop5 (primary):**")
    a("")
    a("| Trial | Panel | p_value | q_value | BH rej? |")
    a("|---|---|---|---|---|")
    for b in family_bh_stop5:
        lbl = b.get("label", "?")
        parts = lbl.rsplit("_", 1)
        tid = parts[0] if len(parts) == 2 else lbl
        pnl = parts[1] if len(parts) == 2 else "?"
        a(f"| {tid} | {pnl} | {_fmt_f(b.get('p_value'), 4)} | "
          f"{_fmt_f(b.get('q_value'), 4)} | "
          f"{'YES' if b.get('rejected') else 'no' if b.get('rejected') is not None else '—'} |")
    a("")

    a("**mae21 (co-primary):**")
    a("")
    a("| Trial | Panel | p_value | q_value | BH rej? |")
    a("|---|---|---|---|---|")
    for b in family_bh_mae21:
        lbl = b.get("label", "?")
        parts = lbl.rsplit("_", 1)
        tid = parts[0] if len(parts) == 2 else lbl
        pnl = parts[1] if len(parts) == 2 else "?"
        a(f"| {tid} | {pnl} | {_fmt_f(b.get('p_value'), 4)} | "
          f"{_fmt_f(b.get('q_value'), 4)} | "
          f"{'YES' if b.get('rejected') else 'no' if b.get('rejected') is not None else '—'} |")
    a("")
    a("---")
    a("")


def write_report(study_results: dict[str, Any], out_path: Path) -> None:
    """Write A2_MACRO_POS_REPORT.md."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    macro_res = study_results["macro_results"]
    pos_res   = study_results["pos_results"]

    # Load NC yardstick
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
    if not nc_yardstick_lines:
        nc_yardstick_lines = ["*(W1_NC_REPORT.md not found — see that file for NC reference numbers)*"]

    lines: list[str] = []
    a = lines.append

    # Header
    a("# A2 W2b — esx_macro_release + esx_pos_reset Phase-0 Study Report")
    a("")
    a("**Families:**")
    a(f"- `{FAMILY_MACRO}`: budget declared={BUDGET_MACRO_DECL} / consumed={BUDGET_MACRO_CONS} / reserve={BUDGET_MACRO_RES}")
    a(f"- `{FAMILY_POS}`: budget declared={BUDGET_POS_DECL} / consumed={BUDGET_POS_CONS} / reserve={BUDGET_POS_RES}")
    a("")
    a("**Status:** Phase-0 study report only — no promotion, no product change (RUL-4).")
    a("**Amendment:** Entry-Stack Expansion Amendment 2 (A2 RUL-26).")
    a("**Date:** 2026-07-06")
    a("**Estimator:** R1-M (market-level, no date FE, RUL-24). Controls partialled via Frisch-Waugh.")
    a("")
    a("**DEPLOY CEILING (mandatory per RUL-24):** These are regime-conditioning CONTEXT")
    a("families. They can NEVER become ticker-level chips. Permitted ceiling: context only.")
    a("")
    a("**CHIP PROMOTION IMPOSSIBLE THIS WAVE:** NC-2 eq_band remains DEFERRED (A2 §C3).")
    a("")
    a("---")
    a("")

    # Contrast B computable / pos note
    a("## Panel Meta and Contrast-B Computability")
    a("")
    a(f"**esx_macro_release contrast B:** COMPUTABLE.")
    a(f"Panel exports `ofr_fsi_pctile_exp` and `hy_oas_pctile_exp` (expanding-window,")
    a(f"no look-ahead). Mask M1 = `ofr_fsi_pctile_exp >= 0.80`; Mask M2 =")
    a(f"`hy_oas_pctile_exp >= 0.80`. Both consumed (8 trials total).")
    a("")
    a(f"**esx_pos_reset contrast B:** {POS_CONTRAST_B_NOTE}")
    a("")
    a("---")
    a("")

    # NC Yardstick (FIRST table, RUL-3)
    a("## NC Yardstick (RUL-3) — First Table")
    a("")
    a("> Per §10 RUL-3: NC yardstick is the FIRST table. Source: W1_NC_REPORT.md.")
    a("> NOTE: NC contrasts are ticker-level R1 while these are R1-M market-level.")
    a("> The yardstick is CONTEXT, not a promotion bar. R1-M families ceiling at")
    a("> regime-conditioning context, never a ticker-level chip (RUL-24).")
    a("")
    for nc_line in nc_yardstick_lines:
        a(nc_line)
    a("")
    a("---")
    a("")

    # Adjacency (RUL-2)
    a("## Adjacency Citations (RUL-2)")
    a("")
    a("**M1 FSI turn:** `validate_stress_gate.py` — OFR FSI is DISPLAY-ONLY verdict")
    a("(coincident indicator). The turn (M1) is the inverse of the calibrated de-risk")
    a("leg; its sign at fire-time tests whether FSI peaking improves entry quality.")
    a("")
    a("**M2 HY-OAS turn:** `credit_oas_roc` is a calibrated Tier-A de-risk leg in the")
    a("conditions engine. The turn (negative ROC from ≥p80 level = stress receding)")
    a("is the market-level analog. The repo carries an internal contradiction on its")
    a("2020+ vitality (immaterial here: bottom-side turn is the genuinely absent test).")
    a("")
    a("**P1 NAAIM:** NAAIM is a CONFIRMER in the conditions engine. The 3-leg")
    a("capitulation family (of which NAAIM is one leg) does not beat VIX-30 priors")
    a("(prior from conditions.py evaluation). This study tests the marginal entry-quality")
    a("increment over VIX + SPY drawdown controls, not the confirmer level claim.")
    a("")
    a("**P2 COT:** COT ES+NDX spec net is a standard position-extremes confirmer.")
    a("No prior fire-conditioned study; this is first-instance evidence.")
    a("")
    a("**Anti-fusion (Signal Commons R3, A2 RUL-25):** No fused positioning/macro")
    a("permission score, leg, or tier may be constructed. esx_macro_release and")
    a("esx_pos_reset remain independent families. The esx_support_dose ordinal")
    a("monotonicity study (RUL-25) is unlocked only after ≥2 leg verdicts filed.")
    a("")
    a("---")
    a("")

    # Study design
    a("## Study Design")
    a("")
    a("**Estimator:** `r1m_estimate` (entry_strata_phase0.py) — no date FE, mandatory")
    a("controls partialled via Frisch-Waugh (RUL-24). Block bootstrap CIs.")
    a("")
    a("**Pre-registered controls per trial (RUL-24 shared-source exclusion):**")
    a("")
    a("| Family-Form | Controls | Exclusion reason |")
    a("|---|---|---|")
    a("| M1 (FSI turn) | vix, spy_dd126, hy_oas | FSI-family controls dropped (shared source with treatment) |")
    a("| M2 (OAS turn) | vix, spy_dd126 | hy_oas excluded (shared source: treatment = HY-OAS ROC turn) |")
    a("| P1, P2 | vix, spy_dd126 | no shared-source exclusion |")
    a("")
    a("**Contrasts:**")
    a("")
    a("esx_macro_release:")
    a("- Contrast A: turn-vs-rest over all fires in date-panel coverage.")
    a("- Contrast B: turn-vs-elevated-not-turning. BOTH arms restricted to")
    a("  elevated-stress dates (M1: ofr_fsi_pctile_exp ≥ 0.80; M2: hy_oas_pctile_exp")
    a("  ≥ 0.80). Isolates the TURN from the elevation itself.")
    a("")
    a("esx_pos_reset:")
    a("- Contrast A only: reset-vs-rest over non-null flag dates.")
    a("- Contrast B: RESERVE (pctile columns absent from v1.1 panel; see above).")
    a("")
    a("**Grading:** ONCE per panel (T+1 fill, RUL-9). Null-flag dates dropped via")
    a("r1m_estimate dropna on required columns. Sample window stamped per trial.")
    a("")
    a("**Era tables:** 2012-2015, 2016-2019, 2020-2022, 2023-2026.")
    a("")
    a("**BH:** q≤0.10 within each family independently (stop5 primary + mae21 co-primary).")
    a("BH families are NOT pooled across macro and pos (RUL-21).")
    a("")
    a("---")
    a("")

    # ---- esx_macro_release results ----
    a(f"# Family: `{FAMILY_MACRO}`")
    a("")
    a(f"Budget declared: {BUDGET_MACRO_DECL} | Consumed: {BUDGET_MACRO_CONS} | Reserve: {BUDGET_MACRO_RES}")
    a("Contrast B: COMPUTABLE (pctile columns present in v1.1 panel).")
    a("")

    macro_bh_stop5_map = {b["label"]: b for b in macro_res.get("family_bh_stop5", [])}
    macro_bh_mae21_map = {b["label"]: b for b in macro_res.get("family_bh_mae21", [])}

    for panel_name, panel_data in macro_res.get("panels", {}).items():
        a(f"## Panel: {panel_name.upper()} — {FAMILY_MACRO}")
        a("")

        if "error" in panel_data:
            a(f"**ERROR:** {panel_data['error']}")
            a("")
            continue

        a("**SURVIVOR BIAS STAMP:** Absolute rates on surviving names only.")
        a("")
        a(f"- Total fires loaded: {panel_data.get('n_fires_total', '?'):,}")
        a(f"- Gradable fires: {panel_data.get('n_gradable', '?'):,}")
        a("")

        for trial_res in panel_data.get("trials", []):
            _write_trial_section(lines, trial_res, macro_bh_stop5_map, macro_bh_mae21_map)

        a("---")
        a("")

    _write_family_bh_section(
        lines, FAMILY_MACRO,
        BUDGET_MACRO_DECL, BUDGET_MACRO_CONS, BUDGET_MACRO_RES,
        macro_res.get("family_bh_stop5", []),
        macro_res.get("family_bh_mae21", []),
    )

    # ---- esx_pos_reset results ----
    a(f"# Family: `{FAMILY_POS}`")
    a("")
    a(f"Budget declared: {BUDGET_POS_DECL} | Consumed: {BUDGET_POS_CONS} | Reserve: {BUDGET_POS_RES}")
    a("")
    a(POS_CONTRAST_B_NOTE)
    a("")

    pos_bh_stop5_map = {b["label"]: b for b in pos_res.get("family_bh_stop5", [])}
    pos_bh_mae21_map = {b["label"]: b for b in pos_res.get("family_bh_mae21", [])}

    for panel_name, panel_data in pos_res.get("panels", {}).items():
        a(f"## Panel: {panel_name.upper()} — {FAMILY_POS}")
        a("")

        if "error" in panel_data:
            a(f"**ERROR:** {panel_data['error']}")
            a("")
            continue

        a("**SURVIVOR BIAS STAMP:** Absolute rates on surviving names only.")
        a("")
        a(f"- Total fires loaded: {panel_data.get('n_fires_total', '?'):,}")
        a(f"- Gradable fires: {panel_data.get('n_gradable', '?'):,}")
        a("")

        for trial_res in panel_data.get("trials", []):
            _write_trial_section(lines, trial_res, pos_bh_stop5_map, pos_bh_mae21_map)

        a("---")
        a("")

    _write_family_bh_section(
        lines, FAMILY_POS,
        BUDGET_POS_DECL, BUDGET_POS_CONS, BUDGET_POS_RES,
        pos_res.get("family_bh_stop5", []),
        pos_res.get("family_bh_mae21", []),
    )

    # Verdict
    a("## Verdict (Phase-0)")
    a("")
    a("**DEPLOY CEILING:** esx_macro_release and esx_pos_reset are R1-M market-level")
    a("context families (RUL-24). They can NEVER become ticker-level chips.")
    a("Permitted ceiling: regime-conditioning context only.")
    a("")
    a("**CHIP promotion bar (A2 RUL-21):** Inapplicable — these families are context")
    a("ceiling per RUL-24. Results inform the esx_support_dose ordinal study (RUL-25)")
    a("when ≥2 leg verdicts are filed.")
    a("")
    a("**NC-2 eq_band status:** DEFERRED (A2 §C3). CHIP promotion blocked regardless.")
    a("")
    a("**RUL-24 control disclosure:** market_state/risk_regime is unavailable_v1 in the panel (snapshot engines, no historical series); all trials partial VIX + spy_dd126 only (plus hy_oas level for M1). The F5 kill-rule is operationalized as VIX+drawdown-only this wave.")
    a("")
    a("**Null result declaration:** Any trial with CI-including-0 on stop5 is a NULL.")
    a("Nulls are printed above, not hidden. Market-level conditioning is low-power at")
    a("the fire level (see per-trial recall lines above; market-level flags are rare)")
    a("— CI-including-0 does not rule out a true market-regime effect.")
    a("")
    a("**Anti-fusion (RUL-25):** No fused macro/positioning score permitted.")
    a("Independent family results only.")
    a("")
    a("No promotion language. Report only (RUL-4).")
    a("")
    a("---")
    a("")
    a("*Generated by `scripts/research/run_a2_macro_pos.py`*")
    a("*Grader: engine/grading.py (program barriers, RUL-9). T+1 fill.*")
    a("*'validated' word deliberately absent (CI-enforced).*")
    a("*No promotion language. Phase-0 study report only.*")
    a(f"*{FAMILY_MACRO}: declared={BUDGET_MACRO_DECL} consumed={BUDGET_MACRO_CONS}*")
    a(f"*{FAMILY_POS}: declared={BUDGET_POS_DECL} consumed={BUDGET_POS_CONS} reserve={BUDGET_POS_RES}*")
    a("*CHIP promotion impossible this wave: NC-2 eq_band DEFERRED (A2 §C3).*")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote report: %s", out_path)

    # Dump results JSON (numpy-safe)
    try:
        def _np_safe(o: Any) -> Any:
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
            if isinstance(o, (np.bool_,)):
                return bool(o)
            if isinstance(o, np.ndarray):
                return o.tolist()
            return str(o)

        json_path = out_path.with_suffix(".results.json")
        json_path.write_text(json.dumps(study_results, default=_np_safe, indent=1))
        log.info("Wrote results JSON: %s", json_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("results JSON dump failed (report unaffected): %s", exc)


# ---------------------------------------------------------------------------
# load_fires re-export (used by tests)
# ---------------------------------------------------------------------------
# load_fires imported above from entry_strata_phase0; re-export for test use
__all__ = [
    "run_macro_pos_study", "write_report",
    "FAMILY_MACRO", "BUDGET_MACRO_DECL", "BUDGET_MACRO_CONS", "BUDGET_MACRO_RES",
    "FAMILY_POS", "BUDGET_POS_DECL", "BUDGET_POS_CONS", "BUDGET_POS_RES",
    "MACRO_TRIAL_DEFS", "POS_TRIAL_DEFS", "POS_CONTRAST_B_NOTE",
    "_MACRO_CONTROLS", "_POS_CONTROLS",
    "_build_elevated_masks", "_run_r1m_trial",
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Entry-Stack Expansion A2 — esx_macro_release + esx_pos_reset Phase-0.",
    )
    parser.add_argument(
        "--out",
        default=str(_RESEARCH_DIR / "A2_MACRO_POS_REPORT.md"),
        help="Output path for the report",
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

    n_boot  = 50 if args.smoke else args.n_bootstrap
    panels  = ["deep"] if args.smoke else args.panel

    log.info(
        "Starting A2 macro/pos study (n_bootstrap=%d, panels=%s)",
        n_boot, panels or "all",
    )

    results = run_macro_pos_study(n_bootstrap=n_boot, panels=panels)
    write_report(results, Path(args.out))
    log.info("Done. Report at %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
