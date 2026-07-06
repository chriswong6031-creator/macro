"""CPI lattice batch-2 runner — family ``cycle_pattern_lattice_v1`` (PREREGISTRATION.md §15).

RESEARCH TRACK (masterplan §4). FROZEN by §15. Batch 2 re-tests the SAME 135-cell search space
as §14 against WITHIN-FAMILY baselines — the §14 adjudication showed the cross-family
phase-pooled baseline conflates family base-rate offsets with phase effects (truth
``cycle_truth_lattice1_confirmatory_and_baseline_confound_v1``). The W4.4 machinery
(``scripts/build_conditional_cells.py``: ``derive_phase``, ``james_stein_shrink``,
``cell_boot_ci``, vol-residualized DD) is reused VERBATIM, with **no quad conditioning**.

WHAT THIS DOES (all parameters frozen in §15; none tuned here)
  1. Loads the price-basis person-period panel ``data/hazard/panel_price_c4414dcb.parquet`` and
     the SAME W4.4 forward joins. EMBARGO: rows with date >= 2024-01-01 dropped BEFORE any
     estimate (fit AND gate).

  2. Two FROZEN lattices (same as §14):
       L-A: phase_v2(5) × family(3)                 = 15 cells
       L-B: phase_v2(5) × trend_pass(2) × family(3) = 30 cells

  3. Three FROZEN targets (same as §14): rdd_63d, turn_event_3m, phase_persist_3m.

  4. THE §15 change — WITHIN-FAMILY baseline pools:
       L-A cell (phase p, family f): pool = ALL rows of family f (all phases). Gap = shrunk
         cell mean − family-pooled mean. James-Stein group = the 5 phase cells of family f.
         Question: does this phase differ from the family's own norm?
       L-B cell (phase p, trend t, family f): pool = rows of family f × phase p (both trend
         values). James-Stein group = the 2 trend cells of (f, p). Question: does the trend
         split matter within this family-phase? (The CPI-020 falsifier's "against CN's own
         Downturn baseline".)
     Month-block bootstrap of the gap (800 draws, seed 7) resamples POOL dates once per draw;
     collapse below 12 unique cell months (pinned to the pool mean). Era split (pre/post-2018)
     recomputes the gap sign under the SAME pool definition per era.
     The §14-style cross-family gap ships as a DISCLOSED DIAGNOSTIC only: ``gap_xfam`` +
     ``pooled_xfam`` (raw point estimates, no CI, no gate role).

  5. PROMOTION gate (§15, same shape as §14): within-family gap CI95 excludes 0 AND
     n_months >= 40 AND era signs both match the full-sample sign AND survives BH-FDR q=0.10
     across ALL 135 gap tests.

  6. NAMED RE-TEST (LT2-020): the cell (L-B, Downturn, cn_sector, trend_pass=0, rdd_63d) is
     the preregistered CPI-020 re-test — one of the 135, NO extra budget. PASS iff it clears
     the full promotion gate. The artifact carries a ``named_retest`` block either way.

  7. SANITY GATE (printed, not a claim): raw-DD KG-2 direction must reproduce (Trough deeper,
     Peak shallower than pooled) on the full sample, else abort sys.exit(2) as pipeline error.

  8. Prints the candidate count (135) BEFORE any evaluation (anti-mining law). Declares the
     trial budget as family ``rf.cycle_pattern.lattice_v1`` (production ledger on the real
     run; scratch under --smoke). Writes data/cycle_pattern/lattice/batch2.json (+ cells
     parquet). Promoted cells → factory candidates (status 'screened', trial_family
     'lattice_v1') + adapter truth_guard. The artifact also carries the mechanical §14
     candidate resolutions (batch-1 candidates whose cell fails the within-family gate →
     marked for screened→numeric_rejected; the transition write happens in the results wave).

Pure numpy/pandas/pyarrow. Deterministic (seed 7). NO sklearn / statsmodels / scipy.stats.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).parent.parent.resolve()
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Reuse the W4.4 machinery VERBATIM — import, never fork (§15 "reused verbatim").
from scripts.build_conditional_cells import (  # noqa: E402
    build_panel_with_returns,
    derive_phase,
    james_stein_shrink,
    cell_boot_ci,
    FAMILIES,
    PHASES,
    N_MONTHS_FLOOR,
)
from engine.grading_stats import BOOT_DRAWS, BOOT_SEED  # noqa: E402
from scripts.fit_cycle_hazard import bh_fdr  # noqa: E402

# Reuse the §14 runner's frozen-shared helpers verbatim (embargo, persistence label, sanity
# gate, CI/p helper, promotion gate) — same machinery, same conventions.
from scripts.build_cycle_pattern_lattice_phase0 import (  # noqa: E402
    EMBARGO_DATE,
    ERA_SPLIT_DATE,
    truncate_embargo,
    build_targets,
    sanity_gate_rawdd,
    apply_promotion_gate,
    _boot_gaps_for_phase as _boot_gaps_for_pool,   # pool-generic: resamples whatever pool given
    _ci_and_p,
    _r6,
)

# ── FROZEN constants (§15; not tuned). Tests parse these via AST and assert vs §15. ──
FAMILY = "rf.cycle_pattern.lattice_v1"       # trial-budget family (§15)
TRIAL_FAMILY_SUFFIX = "lattice_v1"           # bare suffix for factory candidates
N_TRIALS = 135                               # (15 L-A + 30 L-B) × 3 — same declared space as §14

FDR_Q = 0.10                                 # BH-FDR q across ALL 135 gap tests (§15)
N_MONTHS_PROMOTE_FLOOR = 40                  # n_months >= 40 promotion floor (§15)

LATTICES = {
    "L-A": [],                # extra dims beyond (phase_v2, family)
    "L-B": ["trend_pass"],    # + trend_pass split
}
TARGETS = ["rdd_63d", "turn_event_3m", "phase_persist_3m"]
TREND_PASS_VALUES = [0.0, 1.0]

# The preregistered CPI-020 named re-test cell (LT2-020) — one of the 135, no extra budget.
NAMED_RETEST = {
    "lattice": "L-B",
    "phase_v2": "Downturn",
    "family": "cn_sector",
    "trend_pass": 0.0,
    "target": "rdd_63d",
    "truth_id": "cycle_truth_cn_downturn_broken_trend_tail_candidate_v1",
}

_PANEL_PATH = _REPO / "data" / "hazard" / "panel_price_c4414dcb.parquet"
_OUT_DIR = _REPO / "data" / "cycle_pattern" / "lattice"
_CANDIDATES_PATH = _REPO / "data" / "cycle_pattern" / "pattern_candidates.jsonl"
_BATCH1_ARTIFACT = _REPO / "data" / "cycle_pattern" / "lattice" / "batch1.json"


# ═══════════════════════════════════════════════════════════════════════════════
# Pool + cell enumeration (§15 within-family pools)
# ═══════════════════════════════════════════════════════════════════════════════

def _pool_specs(lattice: str) -> list[dict]:
    """Enumerate the WITHIN-FAMILY baseline pools for a lattice (§15).

    L-A: one pool per family (all phases pooled)          → 3 pools × 5 cells.
    L-B: one pool per (family, phase) (trend pooled)      → 15 pools × 2 cells.
    Each pool dict: {"pool_key": {...}, "cells": [cell_spec, ...]}.
    """
    pools: list[dict] = []
    if lattice == "L-A":
        for family in FAMILIES:
            cells = [{"lattice": lattice, "phase_v2": phase, "family": family}
                     for phase in PHASES]
            pools.append({"pool_key": {"family": family}, "cells": cells})
    else:  # L-B
        for family in FAMILIES:
            for phase in PHASES:
                cells = [{"lattice": lattice, "phase_v2": phase, "family": family,
                          "trend_pass": tp} for tp in TREND_PASS_VALUES]
                pools.append({"pool_key": {"family": family, "phase_v2": phase},
                              "cells": cells})
    return pools


def _mask_for(df: pd.DataFrame, spec: dict) -> np.ndarray:
    """Boolean row-mask for a pool_key or cell spec (only known dims consulted)."""
    m = np.ones(len(df), bool)
    if "family" in spec:
        m &= (df["family"].to_numpy() == spec["family"])
    if "phase_v2" in spec:
        m &= (df["phase_v2"].to_numpy() == spec["phase_v2"])
    if "trend_pass" in spec:
        m &= (df["trend_pass"].to_numpy(float) == spec["trend_pass"])
    return m


# ═══════════════════════════════════════════════════════════════════════════════
# Main per-target cell builder (within-family pooling, §15)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_lattice_cells(df: pd.DataFrame, lattice: str, target: str) -> list[dict]:
    """Compute all cells for one (lattice, target) under §15 within-family pools.

    Censoring (W4.4 fidelity, unchanged from §14): rdd_63d filters ``censored == 0``;
    turn_event_3m / phase_persist_3m are panel labels (NaN-drop only).
    """
    d = df.copy()
    if target == "rdd_63d" and "censored" in d.columns:
        d = d[d["censored"] == 0]
    d = d.dropna(subset=[target]).copy()
    dates_all = d["date"].astype(str).to_numpy()
    vals_all = d[target].to_numpy(float)

    # §14-style cross-family phase-pooled means — DIAGNOSTIC ONLY (§15): raw point estimates.
    phase_all = d["phase_v2"].to_numpy()
    xfam_pool_mean: dict[str, float] = {}
    for phase in PHASES:
        pv = vals_all[phase_all == phase]
        xfam_pool_mean[phase] = float(np.mean(pv)) if len(pv) > 0 else np.nan

    cells: list[dict] = []
    for pool in _pool_specs(lattice):
        pool_mask = _mask_for(d, pool["pool_key"])
        pool_dates = dates_all[pool_mask]
        pool_vals = vals_all[pool_mask]
        pooled_mean = float(np.mean(pool_vals)) if len(pool_vals) > 0 else np.nan

        cell_specs = pool["cells"]
        cell_masks_full = [_mask_for(d, s) for s in cell_specs]
        js_inputs: list[dict] = []
        raw_records: list[dict] = []
        for s, cm in zip(cell_specs, cell_masks_full):
            cell_dates = dates_all[cm]
            cell_vals = vals_all[cm]
            n_raw = int(cm.sum())
            n_months = int(len(np.unique(cell_dates))) if n_raw > 0 else 0
            collapsed = (n_months < N_MONTHS_FLOOR)
            if n_raw > 1 and not collapsed:
                raw_mean = float(np.mean(cell_vals))
                within_var = float(np.var(cell_vals, ddof=1))
                n_eff = float(n_raw)  # non-overlapping labels & DD at month-end (as §14)
            else:
                raw_mean = pooled_mean
                within_var = float(np.var(pool_vals, ddof=1)) if len(pool_vals) > 1 else 0.0
                n_eff = float(n_raw)
            raw_records.append({
                "spec": s, "n_raw": n_raw, "n_months": n_months,
                "collapsed": collapsed, "raw_mean": raw_mean,
            })
            js_inputs.append({"raw_mean": raw_mean, "within_var": within_var, "n_eff": n_eff})

        # James-Stein shrink toward the WITHIN-FAMILY pool mean; group = the pool's cells
        # (reuse W4.4 verbatim). Collapsed cells pinned to the pool mean (w=0).
        non_collapsed_idx = [i for i, r in enumerate(raw_records) if not r["collapsed"]]
        if non_collapsed_idx:
            nc_cells = [js_inputs[i] for i in non_collapsed_idx]
            james_stein_shrink(nc_cells, raw_mean_key="raw_mean",
                               n_eff_key="n_eff", within_var_key="within_var")
        shrunk_by_idx: dict[int, float] = {}
        for i in non_collapsed_idx:
            shrunk_by_idx[i] = js_inputs[i]["shrunk_mean"]

        # Vectorized month-block bootstrap of the gap within THIS pool.
        boot_cell_idx = [i for i in non_collapsed_idx
                         if raw_records[i]["n_months"] >= N_MONTHS_FLOOR]
        boot_masks = [cell_masks_full[i][pool_mask] for i in boot_cell_idx]
        boot_gaps = _boot_gaps_for_pool(pool_dates, pool_vals, boot_masks) if boot_masks else []
        gaps_by_idx: dict[int, np.ndarray | None] = {
            i: g for i, g in zip(boot_cell_idx, boot_gaps)
        }

        for i, (s, r) in enumerate(zip(cell_specs, raw_records)):
            collapsed = r["collapsed"]
            shrunk = shrunk_by_idx.get(i, pooled_mean)
            gap = (float(shrunk) - pooled_mean) if not np.isnan(pooled_mean) else None
            ci95, boot_p = _ci_and_p(gaps_by_idx.get(i))
            era_pre_sign, era_post_sign = _era_signs_wf(d, s, pool["pool_key"], target)
            xfam_mean = xfam_pool_mean.get(s["phase_v2"], np.nan)
            gap_xfam = (r["raw_mean"] - xfam_mean
                        if (r["n_raw"] > 0 and not np.isnan(xfam_mean)) else None)
            cell = {
                "lattice": lattice,
                "phase_v2": s["phase_v2"],
                "family": s["family"],
                "target": target,
                "n_months": r["n_months"],
                "n_raw": r["n_raw"],
                "shrunk": _r6(shrunk),
                "pooled": _r6(pooled_mean),        # the §15 WITHIN-FAMILY baseline
                "gap": _r6(gap) if gap is not None else None,
                "ci95": ci95,
                "boot_p": round(boot_p, 6) if boot_p is not None else None,
                "era_pre_sign": era_pre_sign,
                "era_post_sign": era_post_sign,
                "collapsed": bool(collapsed),
                "pooled_xfam": _r6(xfam_mean),     # DIAGNOSTIC (§14-style baseline)
                "gap_xfam": _r6(gap_xfam) if gap_xfam is not None else None,
                "promoted": False,                  # set jointly after BH across all 135
            }
            if "trend_pass" in s:
                cell["trend_pass"] = float(s["trend_pass"])
            cells.append(cell)

    return cells


def _era_signs_wf(d: pd.DataFrame, spec: dict, pool_key: dict, target: str,
                  ) -> tuple[int | None, int | None]:
    """Era gap signs under the §15 WITHIN-FAMILY pool: per era, sign(cell mean − pool mean)
    with the pool recomputed inside the era (point estimates only, no bootstrap)."""
    dt = pd.to_datetime(d["date"])
    out: list[int | None] = []
    for lo, hi in ((None, ERA_SPLIT_DATE), (ERA_SPLIT_DATE, None)):
        era_mask = np.ones(len(d), bool)
        if lo is not None:
            era_mask &= (dt >= lo).to_numpy()
        if hi is not None:
            era_mask &= (dt < hi).to_numpy()
        sub = d[era_mask]
        pool_sub = sub[_mask_for(sub, pool_key)]
        cell_sub = sub[_mask_for(sub, spec)]
        if len(cell_sub) == 0 or len(pool_sub) == 0:
            out.append(None)
            continue
        g = float(cell_sub[target].mean()) - float(pool_sub[target].mean())
        out.append(int(np.sign(g)))
    return out[0], out[1]


# ═══════════════════════════════════════════════════════════════════════════════
# Named re-test (LT2-020) + §14 candidate resolution (mechanical, frozen in §15)
# ═══════════════════════════════════════════════════════════════════════════════

def find_named_retest_cell(cells: list[dict]) -> dict | None:
    """Locate the LT2-020 cell among the computed cells (exact frozen spec)."""
    for c in cells:
        if (c["lattice"] == NAMED_RETEST["lattice"]
                and c["phase_v2"] == NAMED_RETEST["phase_v2"]
                and c["family"] == NAMED_RETEST["family"]
                and c.get("trend_pass") == NAMED_RETEST["trend_pass"]
                and c["target"] == NAMED_RETEST["target"]):
            return c
    return None


def _cell_key(lattice: str, phase: str, family: str, trend_pass, target: str) -> str:
    tp = "" if trend_pass is None or (isinstance(trend_pass, float) and np.isnan(trend_pass)) \
        else f"-trend_pass={float(trend_pass):.0f}"
    return f"{lattice}-{phase}-{family}{tp}-{target}"


def resolve_batch1_candidates(cells: list[dict], batch1_path: Path) -> list[dict]:
    """Mechanical §15 resolution of the 48 §14 factory candidates: a batch-1 candidate whose
    cell FAILS the within-family gate → marked for screened→numeric_rejected; a candidate
    whose cell PASSES keeps screened with batch2 evidence. Returns resolution rows (the
    factory transition WRITES happen in the results wave, not here)."""
    if not batch1_path.exists():
        return []
    b1 = json.loads(batch1_path.read_text())
    by_key = {
        _cell_key(c["lattice"], c["phase_v2"], c["family"], c.get("trend_pass"),
                  c["target"]): c
        for c in cells
    }
    resolutions: list[dict] = []
    for p in b1.get("promotions", []):
        key = _cell_key(p["lattice"], p["phase_v2"], p["family"], p.get("trend_pass"),
                        p["target"])
        c2 = by_key.get(key)
        passed = bool(c2 and c2.get("promoted"))
        if c2 is None:
            resolution = "cell_missing_PIPELINE_ERROR"   # never a scientific kill
        elif passed:
            resolution = "keep_screened_with_batch2_evidence"
        else:
            resolution = "numeric_rejected"
        resolutions.append({
            "cell_key": key,
            "batch1_gap": p.get("gap"),
            "batch2_gap_wf": c2.get("gap") if c2 else None,
            "batch2_promoted": passed,
            "resolution": resolution,
        })
    return resolutions


# ═══════════════════════════════════════════════════════════════════════════════
# Trial budget + factory candidates
# ═══════════════════════════════════════════════════════════════════════════════

def declare_trial_budget(ledger_path: Path, *, run_at: str) -> None:
    """log_declared_budget BEFORE any p-value (house convention; scratch under --smoke)."""
    from engine.trial_ledger import TrialLedger
    led = TrialLedger(path=ledger_path, family=FAMILY)
    led.log_declared_budget(
        N_TRIALS, family=FAMILY,
        reason=(f"PREREGISTRATION.md §15 cycle_pattern_lattice_v1: same 135-cell space as §14 "
                f"re-tested vs WITHIN-FAMILY baselines; run_at={run_at}"),
    )


def _candidate_from_cell(cell: dict, *, artifact_path: str, created_at: str) -> dict:
    """Project one promoted cell into a factory candidate row (status 'screened',
    trial_family 'lattice_v1')."""
    tp = f"/trend_pass={cell['trend_pass']:.0f}" if "trend_pass" in cell else ""
    cid = (f"rf-{created_at[:10].replace('-', '')}-cycle_pattern-b2-{cell['lattice']}"
           f"-{cell['phase_v2']}-{cell['family']}{tp.replace('/', '-')}-{cell['target']}")
    baseline = ("its family's all-phase norm" if cell["lattice"] == "L-A"
                else "its own family×phase baseline")
    statement = (f"{cell['lattice']} cell phase_v2={cell['phase_v2']} family={cell['family']}"
                 f"{tp}: {cell['target']} within-family gap {cell['gap']} vs {baseline} "
                 f"(CI95 {cell['ci95']})")
    return {
        "schema": "research_factory.candidate.v1",
        "authority": "display_only",
        "domain": "cycle_pattern",
        "source": "cycle_pattern_scan",
        "candidate_type": "cycle_pattern_rule",
        "candidate_id": cid,
        "created_at": created_at,
        "status": "screened",
        "hypothesis": (f"{cell['target']} in {cell['lattice']} cell "
                       f"(phase_v2={cell['phase_v2']}, family={cell['family']}{tp}) "
                       f"differs from {baseline}"),
        "mechanism": ("within-family phase/trend conditioning captures a persistent "
                      "regularity net of family base-rate offsets (the §14 confound removed; "
                      "no macro/quad leak)"),
        "statement": statement,
        "target": cell["target"],
        "scope": {"families": [cell["family"]], "regions": [], "sample": "pre-2024 embargoed"},
        "trial_family": TRIAL_FAMILY_SUFFIX,
        "artifacts": {"evidence": artifact_path, "gap": cell["gap"], "ci95": cell["ci95"],
                      "n_months": cell["n_months"], "boot_p": cell["boot_p"],
                      "gap_xfam_diagnostic": cell.get("gap_xfam")},
    }


def _cells_to_parquet(cells: list[dict], path: Path) -> None:
    rows = []
    for c in cells:
        ci = c.get("ci95")
        rows.append({
            "lattice": c["lattice"], "phase_v2": c["phase_v2"], "family": c["family"],
            "trend_pass": c.get("trend_pass", np.nan), "target": c["target"],
            "n_months": c["n_months"], "n_raw": c["n_raw"],
            "shrunk": c["shrunk"], "pooled": c["pooled"], "gap": c["gap"],
            "ci_lo": ci[0] if ci else np.nan, "ci_hi": ci[1] if ci else np.nan,
            "boot_p": c["boot_p"], "era_pre_sign": c["era_pre_sign"],
            "era_post_sign": c["era_post_sign"], "collapsed": c["collapsed"],
            "pooled_xfam": c["pooled_xfam"], "gap_xfam": c["gap_xfam"],
            "promoted": c["promoted"],
        })
    pd.DataFrame(rows).to_parquet(path, index=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════════════

def _run(panel_path: Path, out_dir: Path, *, smoke: bool = False,
         ledger_path: Path | None = None, write: bool = True) -> dict:
    panel = pd.read_parquet(panel_path)
    epoch = panel_path.stem.replace("panel_price_", "")
    panel = truncate_embargo(panel)                      # EMBARGO before ANY estimate (§15)
    run_at = datetime.now(timezone.utc).isoformat()

    print("[W4.4-join] building phase_v2 + forward joins (rdd_63d) ...")
    joined = build_panel_with_returns(panel)             # W4.4 verbatim → phase_v2, rdd_63d
    joined["date"] = pd.to_datetime(joined["date"])
    df = build_targets(joined)

    lattices = ["L-A"] if smoke else ["L-A", "L-B"]
    targets = [TARGETS[0]] if smoke else TARGETS
    if smoke:
        keep_months = np.sort(df["date"].unique())[:50]
        df = df[df["date"].isin(keep_months)].reset_index(drop=True)
        print(f"[SMOKE] L-A × {targets[0]} only, first 50 months, {len(df)} rows")

    # ── ANTI-MINING LAW (§15): print the candidate count BEFORE any evaluation ──────
    print(f"CANDIDATE COUNT (pre-registered, evaluated BEFORE any p-value): {N_TRIALS} "
          f"cells = (15 L-A + 30 L-B) × 3 targets, WITHIN-FAMILY baselines  [family={FAMILY}]")

    if ledger_path is None:
        ledger_path = (Path(tempfile.gettempdir()) / "cpi_lattice2_smoke_trial_ledger.jsonl"
                       if smoke else _REPO / "data" / "trial_ledger.jsonl")
    declare_trial_budget(ledger_path, run_at=run_at)
    print(f"Declared trial budget: family={FAMILY} n={N_TRIALS} → {ledger_path}")

    # ── SANITY GATE (raw-DD KG-2 direction, unchanged from §14) ─────────────────────
    sanity = sanity_gate_rawdd(joined)
    print("\n[SANITY GATE] raw-DD (fwd_maxdd_63d) phase×pooled point estimates (KG-2 check):")
    print(f"  overall raw-DD_63d = {sanity['overall_rawdd_63d']}")
    for row in sanity["table"]:
        marker = ""
        if row["phase_v2"] == "Trough":
            marker = "  <- must be DEEPER (more negative) than overall"
        elif row["phase_v2"] == "Peak":
            marker = "  <- must be SHALLOWER (less negative) than overall"
        print(f"    {row['phase_v2']:10s} mean={row['mean_rawdd_63d']:+.6f}  n={row['n']}{marker}")
    print(f"  → {sanity['reason']}")
    if not sanity["passed"]:
        print("\n[ABORT] Sanity gate FAILED — this is a PIPELINE ERROR, not a finding.",
              file=sys.stderr)
        sys.exit(2)

    # ── Compute all cells across lattices × targets ─────────────────────────────────
    all_cells: list[dict] = []
    for lattice in lattices:
        for target in targets:
            print(f"[cells] {lattice} × {target} (within-family pools) ...")
            all_cells.extend(compute_lattice_cells(df, lattice, target))
    print(f"[cells] computed {len(all_cells)} cells "
          f"({'smoke subset' if smoke else 'full 135 expected'})")

    # ── Promotion gate (BH-FDR jointly across the family; §14 logic reused) ─────────
    apply_promotion_gate(all_cells)
    promotions = [c for c in all_cells if c["promoted"]]
    n_promoted = len(promotions)

    # ── Named re-test (LT2-020) ─────────────────────────────────────────────────────
    named_cell = find_named_retest_cell(all_cells)
    named_retest = {
        "spec": NAMED_RETEST,
        "found": named_cell is not None,
        "cell": named_cell,
        "passed": bool(named_cell and named_cell["promoted"]),
    }
    if named_cell is not None:
        print(f"\n[NAMED RE-TEST LT2-020] gap_wf={named_cell['gap']} ci95={named_cell['ci95']} "
              f"n_months={named_cell['n_months']} boot_p={named_cell['boot_p']} "
              f"era=({named_cell['era_pre_sign']},{named_cell['era_post_sign']}) "
              f"bh={named_cell.get('bh_survives')} → "
              f"{'PASS' if named_retest['passed'] else 'FAIL'}")
    elif not smoke:
        print("\n[NAMED RE-TEST LT2-020] cell NOT FOUND — pipeline error", file=sys.stderr)
        sys.exit(2)

    # ── §14 candidate resolution (mechanical; writes happen in the results wave) ────
    b1_resolutions = [] if smoke else resolve_batch1_candidates(all_cells, _BATCH1_ARTIFACT)

    artifact = {
        "schema": 1,
        "registered_ref": "PREREGISTRATION.md §15",
        "run_at": run_at,
        "embargo": EMBARGO_DATE.strftime("%Y-%m-%d"),
        "panel_epoch": epoch,
        "sanity_gate": sanity,
        "candidate_count_printed": N_TRIALS,
        "cells": all_cells,
        "promotions": promotions,
        "n_promoted": n_promoted,
        "named_retest": named_retest,
        "batch1_candidate_resolutions": b1_resolutions,
    }

    if smoke:
        print(f"[SMOKE] {len(all_cells)} cells, {n_promoted} promoted. "
              "No real artifacts written.")
        return {"smoke": True, "cells": all_cells, "sanity_gate": sanity,
                "named_retest": named_retest}

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        art_path = out_dir / "batch2.json"
        art_path.write_text(json.dumps(artifact, indent=2, default=str))
        _cells_to_parquet(all_cells, out_dir / "batch2_cells.parquet")
        print(f"Wrote {art_path} and {out_dir/'batch2_cells.parquet'}")

    truth_guard_flags: list[dict] = []
    if n_promoted > 0:
        art_abs = out_dir / "batch2.json"
        try:
            art_rel = str(art_abs.relative_to(_REPO))
        except ValueError:
            art_rel = str(art_abs)
        candidates = [_candidate_from_cell(c, artifact_path=art_rel, created_at=run_at)
                      for c in promotions]
        from engine.research_factory.adapter_cycle_pattern import truth_guard
        truth_guard_flags = truth_guard(candidates)
        artifact["truth_guard_flags"] = truth_guard_flags
        if write:
            with _CANDIDATES_PATH.open("a", encoding="utf-8") as fh:
                for cand in candidates:
                    fh.write(json.dumps(cand, default=str) + "\n")
            (out_dir / "batch2.json").write_text(json.dumps(artifact, indent=2, default=str))
            print(f"Wrote {len(candidates)} factory candidates → {_CANDIDATES_PATH}; "
                  f"truth_guard flags: {len(truth_guard_flags)}")

    # ── Honest run-log summary ──────────────────────────────────────────────────────
    print(f"\nRESULT (panel_epoch={epoch}, embargo<{EMBARGO_DATE.date()}, "
          f"cells={len(all_cells)}): {n_promoted} promoted / {N_TRIALS} "
          f"[within-family baselines]")
    for c in promotions:
        tp = f" trend_pass={c['trend_pass']:.0f}" if "trend_pass" in c else ""
        print(f"  PROMOTE {c['lattice']} {c['phase_v2']}/{c['family']}{tp} {c['target']}: "
              f"gap_wf={c['gap']} ci95={c['ci95']} n_months={c['n_months']} "
              f"boot_p={c['boot_p']} era=({c['era_pre_sign']},{c['era_post_sign']}) "
              f"[xfam diag {c['gap_xfam']}]")
    if n_promoted == 0:
        print("  → 0 promotions: the scoped within-family null truth is the honest verdict "
              "(exploration tables ship to the measurement surface either way, §15).")
    return {"artifact": artifact, "n_promoted": n_promoted,
            "named_retest": named_retest, "truth_guard_flags": truth_guard_flags}


def main(argv=None):
    ap = argparse.ArgumentParser(description="CPI lattice batch-2 runner (PREREG §15)")
    ap.add_argument("--panel", default=str(_PANEL_PATH))
    ap.add_argument("--out-dir", default=str(_OUT_DIR))
    ap.add_argument("--smoke", action="store_true",
                    help="one lattice (L-A) × one target, first 50 months, scratch ledger; "
                         "writes NO real artifacts")
    args = ap.parse_args(argv)
    _run(Path(args.panel), Path(args.out_dir), smoke=args.smoke, write=not args.smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
