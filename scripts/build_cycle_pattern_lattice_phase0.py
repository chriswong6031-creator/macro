"""CPI lattice runner — family ``cycle_pattern_lattice_v0`` (PREREGISTRATION.md §14).

RESEARCH TRACK (masterplan §4 — the information program). FROZEN by §14. Mode shift after
the FT synthesis (§13): NO model fitting. Shrunken conditional-cell estimates over PIT-pure,
price-derived dimensions only — the W4.4 machinery
(``scripts/build_conditional_cells.py``: ``derive_phase``, ``james_stein_shrink``, month-block
``cell_boot_ci``, vol-residualized DD) is reused VERBATIM, with **no quad conditioning** →
survivors carry NO revision-optimistic caveat (the novelty vs W4.4).

WHAT THIS DOES (all parameters frozen in §14; none tuned here)
  1. Loads the price-basis person-period panel ``data/hazard/panel_price_c4414dcb.parquet`` and
     the SAME W4.4 forward joins (``build_panel_with_returns`` — derives ``phase_v2`` via
     ``derive_phase``, joins ``rdd_63d`` = vol-residualized forward max-DD over 63 trading days).
     EMBARGO: rows with date >= 2024-01-01 are dropped BEFORE any estimate (fit AND gate).

  2. Two FROZEN lattices:
       L-A: phase_v2(5) × family(3)                = 15 cells
       L-B: phase_v2(5) × trend_pass(2) × family(3) = 30 cells

  3. Three FROZEN targets:
       rdd_63d          — vol-residualized forward max-DD, 63 trading days (the W4.6 metric)
       turn_event_3m    — panel y3 label
       phase_persist_3m — 1 if phase_v2(id, t+1..t+3 month-ends) all equal phase_v2(id, t);
                          a calendar gap breaks the chain → NaN (excluded).

  4. (15 + 30) × 3 = 135 shrunken cell estimates — the whole declared search space.
     Per cell × target: n_months, n_raw, James-Stein shrink weight + shrunk mean toward the
     phase-pooled mean (pooled over the OTHER dimensions within the same phase_v2 × target),
     95% month-block bootstrap CI on the GAP (shrunk − pooled) via cell_boot_ci conventions
     (800 draws, seed 7). collapsed=True if n_months < 12.

  5. ERA SPLIT: the gap sign is recomputed on pre-2018 and post-2018 sub-panels (point
     estimates only; no bootstrap for the sign check).

  6. PROMOTION gate (§14): CI95 excludes 0 AND n_months >= 40 AND era signs both match the
     full-sample sign AND survives BH-FDR q=0.10 across ALL 135 gap tests (two-sided
     bootstrap p-values; reuse ``fit_cycle_hazard.bh_fdr``).

  7. SANITY GATE (printed, not a claim): the RAW-DD (not residualized) phase×family point
     estimates must reproduce the KG-2 direction — Trough deeper than pooled, Peak shallower
     than pooled — on the full sample, else the run ABORTS (sys.exit 2) as a pipeline error.

  8. Prints the candidate count (135) BEFORE any evaluation (anti-mining law). Declares the
     trial budget as family ``rf.cycle_pattern.lattice_v0`` n=135 (production ledger on the
     real run; scratch under --smoke). Writes data/cycle_pattern/lattice/batch1.json (+ a
     compact cells parquet). If any cell is promoted: writes factory candidates
     (status 'screened', trial_family 'lattice_v0') and runs the adapter truth_guard.

Pure numpy/pandas/pyarrow. Deterministic (seed 7). NO sklearn / statsmodels / scipy.stats.
Expected full runtime: minutes (135 cells × 800 bootstrap draws — the bootstrap is vectorized
over cells: month indices are resampled ONCE per draw and all cell means computed per draw).
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

# Reuse the W4.4 machinery VERBATIM — import, never fork (§14 "reused verbatim").
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

# ── FROZEN constants (§14; not tuned). Tests parse these via AST and assert vs §14. ──
EMBARGO_DATE = pd.Timestamp("2024-01-01")   # rows with date >= this excluded (estimates AND gate)
ERA_SPLIT_DATE = pd.Timestamp("2018-01-01")  # pre-2018 / post-2018 era sign check

FAMILY = "rf.cycle_pattern.lattice_v0"       # trial-budget family (§14)
TRIAL_FAMILY_SUFFIX = "lattice_v0"           # bare suffix for factory candidates
N_TRIALS = 135                               # (15 + 30) × 3 — the declared search space

FDR_Q = 0.10                                 # BH-FDR q across ALL 135 gap tests (§14)
N_MONTHS_PROMOTE_FLOOR = 40                  # n_months >= 40 promotion floor (§14)

# Frozen lattices. Each names its conditioning dimensions BEYOND phase_v2×family.
# L-A: phase_v2 × family. L-B: phase_v2 × trend_pass × family.
LATTICES = {
    "L-A": [],                # extra dims beyond (phase_v2, family)
    "L-B": ["trend_pass"],    # + trend_pass split
}

# Frozen targets (3). rdd_63d = vol-residualized forward max-DD (W4.6 metric, joined by W4.4);
# turn_event_3m = panel y3; phase_persist_3m = derived self-join label.
TARGETS = ["rdd_63d", "turn_event_3m", "phase_persist_3m"]

TREND_PASS_VALUES = [0.0, 1.0]               # trend_pass split values (L-B)

_PANEL_PATH = _REPO / "data" / "hazard" / "panel_price_c4414dcb.parquet"
_OUT_DIR = _REPO / "data" / "cycle_pattern" / "lattice"
_CANDIDATES_PATH = _REPO / "data" / "cycle_pattern" / "pattern_candidates.jsonl"


# ═══════════════════════════════════════════════════════════════════════════════
# Panel loading + embargo + target derivation
# ═══════════════════════════════════════════════════════════════════════════════

def _load_panel(panel_path: Path) -> tuple[pd.DataFrame, str]:
    """Load the hazard panel; return (panel, epoch_tag from the filename)."""
    panel = pd.read_parquet(panel_path)
    epoch = panel_path.stem.replace("panel_price_", "")
    return panel, epoch


def truncate_embargo(panel: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with date >= EMBARGO_DATE BEFORE any estimate (§14)."""
    d = panel.copy()
    d["date"] = pd.to_datetime(d["date"])
    return d[d["date"] < EMBARGO_DATE].reset_index(drop=True)


def derive_phase_persist_3m(joined: pd.DataFrame) -> pd.Series:
    """phase_persist_3m per (id, t): 1 if phase_v2 is unchanged across the NEXT 3 month-ends.

    Convention (§14):
      * self-join on CONSECUTIVE month-ends per instrument;
      * a calendar gap (missing month-end between t and t+k) BREAKS the chain → NaN (excluded);
      * value is 1 iff phase_v2(t+1)==phase_v2(t+2)==phase_v2(t+3)==phase_v2(t), else 0;
      * the last <=3 month-ends of every instrument (no full forward window) → NaN.

    Returns a float Series (1.0 / 0.0 / NaN) aligned to ``joined``'s index.
    """
    out = pd.Series(np.nan, index=joined.index, dtype=float)
    # Month-index integer per timestamp so "consecutive month-end" = index delta of exactly 1.
    dt = pd.to_datetime(joined["date"])
    month_idx = dt.dt.year * 12 + (dt.dt.month - 1)
    work = pd.DataFrame({
        "_ridx": joined.index.to_numpy(),
        "id": joined["id"].to_numpy(),
        "midx": month_idx.to_numpy(),
        "phase": joined["phase_v2"].to_numpy(),
    })
    for _iid, grp in work.groupby("id", sort=False):
        g = grp.sort_values("midx")
        midx = g["midx"].to_numpy()
        phase = g["phase"].to_numpy(object)
        ridx = g["_ridx"].to_numpy()
        # Map month-index → phase for O(1) lookahead within this instrument.
        by_month = {int(m): p for m, p in zip(midx, phase)}
        for i in range(len(g)):
            m0 = int(midx[i])
            p0 = phase[i]
            if p0 is None or (isinstance(p0, float) and np.isnan(p0)):
                continue
            future = [by_month.get(m0 + k) for k in (1, 2, 3)]
            if any(f is None for f in future):
                # a calendar gap (or the end of the series) breaks the chain → NaN
                continue
            out.loc[ridx[i]] = 1.0 if all(f == p0 for f in future) else 0.0
    return out


def build_targets(joined: pd.DataFrame) -> pd.DataFrame:
    """Attach the 3 frozen targets to the W4.4-joined panel.

    rdd_63d already present (from build_panel_with_returns). turn_event_3m := y3;
    phase_persist_3m := the self-join persistence label.
    """
    d = joined.copy()
    d["turn_event_3m"] = pd.to_numeric(d["y3"], errors="coerce").astype(float)
    d["phase_persist_3m"] = derive_phase_persist_3m(d)
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# Cell enumeration
# ═══════════════════════════════════════════════════════════════════════════════

def _cell_specs(lattice: str) -> list[dict]:
    """Enumerate the conditioning cells for a lattice (phase_v2 × family [× trend_pass])."""
    specs: list[dict] = []
    for phase in PHASES:
        for family in FAMILIES:
            if lattice == "L-A":
                specs.append({"lattice": lattice, "phase_v2": phase, "family": family})
            else:  # L-B adds the trend_pass split
                for tp in TREND_PASS_VALUES:
                    specs.append({"lattice": lattice, "phase_v2": phase,
                                  "family": family, "trend_pass": tp})
    return specs


def _cell_mask(df: pd.DataFrame, spec: dict) -> np.ndarray:
    """Boolean row-mask for a cell spec (within the target-nonnull frame)."""
    m = (df["phase_v2"].to_numpy() == spec["phase_v2"]) & \
        (df["family"].to_numpy() == spec["family"])
    if "trend_pass" in spec:
        m = m & (df["trend_pass"].to_numpy(float) == spec["trend_pass"])
    return m


# ═══════════════════════════════════════════════════════════════════════════════
# Vectorized month-block bootstrap over all cells at one phase_v2 (one target)
# ═══════════════════════════════════════════════════════════════════════════════

def _boot_gaps_for_phase(
    dates: np.ndarray,
    vals: np.ndarray,
    cell_masks: list[np.ndarray],
    *,
    draws: int = BOOT_DRAWS,
    seed: int = BOOT_SEED,
) -> list[np.ndarray | None]:
    """Vectorized month-block bootstrap of the gap (cell_mean − pooled_mean) for every cell
    that shares one phase_v2 pool. Month dates are resampled ONCE per draw; every cell's gap
    is computed on that same resample (§14 "resample month indices once per draw and compute
    all cell means per draw").

    ``dates``/``vals`` span the POOL (all rows at this phase_v2, all families/trend_pass).
    Returns, per cell (order of ``cell_masks``), a float array of ``<=draws`` gap draws, or
    None if degenerate (cell empty or fewer than 2 unique pool dates). The [2.5, 97.5]
    percentiles of the returned array reproduce ``cell_boot_ci``/``block_bootstrap_ci`` exactly
    for the same resample stream — this is the vectorized equivalent of calling cell_boot_ci
    once per cell.
    """
    uniq = np.unique(dates)
    if len(uniq) < 2:
        return [None] * len(cell_masks)
    by = {d: np.where(dates == d)[0] for d in uniq}
    rng = np.random.default_rng(seed)

    gaps: list[list[float]] = [[] for _ in cell_masks]
    for _ in range(draws):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        ridx = np.concatenate([by[d] for d in pick])
        v = vals[ridx]
        pool_mean = float(np.mean(v))
        for ci, cm in enumerate(cell_masks):
            m = cm[ridx]
            if int(m.sum()) == 0:
                continue
            gaps[ci].append(float(np.mean(v[m])) - pool_mean)
    out: list[np.ndarray | None] = []
    for g in gaps:
        out.append(np.asarray(g, float) if len(g) >= draws // 2 else None)
    return out


def _ci_and_p(gap_draws: np.ndarray | None) -> tuple[list[float] | None, float | None]:
    """[lo, hi] 95% CI (rounded 4dp, matching block_bootstrap_ci) and a TWO-SIDED bootstrap
    p-value on the gap distribution. p = 2·min(P(gap<=0), P(gap>=0)), clipped to [0, 1]."""
    if gap_draws is None or len(gap_draws) == 0:
        return None, None
    lo = round(float(np.percentile(gap_draws, 2.5)), 4)
    hi = round(float(np.percentile(gap_draws, 97.5)), 4)
    p_le = float(np.mean(gap_draws <= 0.0))
    p_ge = float(np.mean(gap_draws >= 0.0))
    p = min(1.0, 2.0 * min(p_le, p_ge))
    return [lo, hi], p


# ═══════════════════════════════════════════════════════════════════════════════
# Main per-target cell builder
# ═══════════════════════════════════════════════════════════════════════════════

def compute_lattice_cells(df: pd.DataFrame, lattice: str, target: str) -> list[dict]:
    """Compute all cells for one (lattice, target). Returns cell dicts with the §14 fields
    EXCEPT the FDR flags (`promoted`, `boot_p` retained; BH applied jointly across all 135).

    Pooling convention (§14): the phase-pooled mean over the OTHER dimensions within the same
    phase_v2 × target (i.e. all families, and for L-B all trend_pass, at that phase_v2). The
    James-Stein group is the set of lattice cells sharing a phase_v2.

    Censoring (W4.4 fidelity): for ``rdd_63d`` — the W4.6 forward-DD metric — censored rows have
    no valid forward window, so W4.4's ``compute_cells`` filters ``censored == 0``; we do the
    same to "reuse its computation exactly" (§14). ``turn_event_3m`` and ``phase_persist_3m`` are
    panel labels defined for every row (§14 "panel y3 label"), so no censored filter is applied
    to them (only NaN-drop).
    """
    d = df.copy()
    if target == "rdd_63d" and "censored" in d.columns:
        d = d[d["censored"] == 0]
    d = d.dropna(subset=[target]).copy()
    dates_all = d["date"].astype(str).to_numpy()
    vals_all = d[target].to_numpy(float)
    phase_all = d["phase_v2"].to_numpy()

    cells: list[dict] = []
    specs = _cell_specs(lattice)

    for phase in PHASES:
        phase_specs = [s for s in specs if s["phase_v2"] == phase]
        pool_mask = (phase_all == phase)
        pool_dates = dates_all[pool_mask]
        pool_vals = vals_all[pool_mask]
        pooled_mean = float(np.mean(pool_vals)) if len(pool_vals) > 0 else np.nan

        # Per-cell raw stats within the pool
        cell_masks_full = [_cell_mask(d, s) for s in phase_specs]
        js_inputs: list[dict] = []
        raw_records: list[dict] = []
        for s, cm in zip(phase_specs, cell_masks_full):
            cell_dates = dates_all[cm]
            cell_vals = vals_all[cm]
            n_raw = int(cm.sum())
            n_months = int(len(np.unique(cell_dates))) if n_raw > 0 else 0
            collapsed = (n_months < N_MONTHS_FLOOR)
            if n_raw > 1 and not collapsed:
                raw_mean = float(np.mean(cell_vals))
                within_var = float(np.var(cell_vals, ddof=1))
                n_eff = float(n_raw)  # non-overlapping labels (turn/persist) & DD at month-end
            else:
                raw_mean = pooled_mean
                within_var = float(np.var(pool_vals, ddof=1)) if len(pool_vals) > 1 else 0.0
                n_eff = float(n_raw)
            raw_records.append({
                "spec": s, "n_raw": n_raw, "n_months": n_months,
                "collapsed": collapsed, "raw_mean": raw_mean,
            })
            js_inputs.append({"raw_mean": raw_mean, "within_var": within_var, "n_eff": n_eff})

        # James-Stein shrink toward the phase-pooled mean (reuse W4.4 verbatim) — non-collapsed
        # cells only; collapsed cells are pinned to the pooled mean (w=0).
        non_collapsed_idx = [i for i, r in enumerate(raw_records) if not r["collapsed"]]
        if non_collapsed_idx:
            nc_cells = [js_inputs[i] for i in non_collapsed_idx]
            james_stein_shrink(nc_cells, raw_mean_key="raw_mean",
                               n_eff_key="n_eff", within_var_key="within_var")
        shrunk_by_idx: dict[int, float] = {}
        for j, i in enumerate(non_collapsed_idx):
            shrunk_by_idx[i] = js_inputs[i]["shrunk_mean"]

        # Vectorized month-block bootstrap of the gap for every non-collapsed cell.
        boot_cell_idx = [i for i in non_collapsed_idx
                         if raw_records[i]["n_months"] >= N_MONTHS_FLOOR]
        boot_masks = [cell_masks_full[i][pool_mask] for i in boot_cell_idx]
        boot_gaps = _boot_gaps_for_phase(pool_dates, pool_vals, boot_masks) if boot_masks else []
        gaps_by_idx: dict[int, np.ndarray | None] = {
            i: g for i, g in zip(boot_cell_idx, boot_gaps)
        }

        for i, (s, r) in enumerate(zip(phase_specs, raw_records)):
            collapsed = r["collapsed"]
            shrunk = shrunk_by_idx.get(i, pooled_mean)
            gap = (float(shrunk) - pooled_mean) if not np.isnan(pooled_mean) else None
            ci95, boot_p = _ci_and_p(gaps_by_idx.get(i))
            era_pre_sign, era_post_sign = _era_signs(d, s, target, pooled_ref=pooled_mean,
                                                     phase=phase)
            cell = {
                "lattice": lattice,
                "phase_v2": phase,
                "family": s["family"],
                "target": target,
                "n_months": r["n_months"],
                "n_raw": r["n_raw"],
                "shrunk": _r6(shrunk),
                "pooled": _r6(pooled_mean),
                "gap": _r6(gap) if gap is not None else None,
                "ci95": ci95,
                "boot_p": round(boot_p, 6) if boot_p is not None else None,
                "era_pre_sign": era_pre_sign,
                "era_post_sign": era_post_sign,
                "collapsed": bool(collapsed),
                "promoted": False,   # set jointly after BH across all 135
            }
            if "trend_pass" in s:
                cell["trend_pass"] = float(s["trend_pass"])
            cells.append(cell)

    return cells


def _era_signs(d: pd.DataFrame, spec: dict, target: str, *, pooled_ref: float,
               phase: str) -> tuple[int | None, int | None]:
    """Recompute the gap SIGN (cell_mean − phase_pooled_mean) on the pre-2018 and post-2018
    sub-panels (point estimates only; no bootstrap — §14). Pooled recomputed within each era.
    Returns (pre_sign, post_sign) each in {-1, 0, +1} or None if that era's cell is empty."""
    dt = pd.to_datetime(d["date"])
    out: list[int | None] = []
    for lo, hi in ((None, ERA_SPLIT_DATE), (ERA_SPLIT_DATE, None)):
        era_mask = np.ones(len(d), bool)
        if lo is not None:
            era_mask &= (dt >= lo).to_numpy()
        if hi is not None:
            era_mask &= (dt < hi).to_numpy()
        sub = d[era_mask]
        pool_sub = sub[sub["phase_v2"] == phase]
        cell_sub = pool_sub[_cell_mask(pool_sub, spec)]
        if len(cell_sub) == 0 or len(pool_sub) == 0:
            out.append(None)
            continue
        g = float(cell_sub[target].mean()) - float(pool_sub[target].mean())
        out.append(int(np.sign(g)))
    return out[0], out[1]


# ═══════════════════════════════════════════════════════════════════════════════
# Sanity gate (raw-DD KG-2 direction) — printed, abort on failure
# ═══════════════════════════════════════════════════════════════════════════════

def sanity_gate_rawdd(joined: pd.DataFrame) -> dict:
    """Full-sample RAW-DD (fwd_maxdd_63d, NOT residualized) phase×family point estimates must
    show Trough DEEPER than pooled and Peak SHALLOWER than pooled (KG-2 direction). DD is <=0,
    so "deeper" = more negative. Returns {passed, table, trough_ok, peak_ok, reason}. This is a
    PIPELINE check, not a finding — the caller sys.exit(2)s if passed is False.
    """
    col = "fwd_maxdd_63d"
    d = joined
    if "censored" in d.columns:
        d = d[d["censored"] == 0]   # W4.4 fidelity: forward-DD is undefined on censored rows
    d = d.dropna(subset=[col])
    overall = float(d[col].mean())
    table: list[dict] = []
    trough_vals: list[float] = []
    peak_vals: list[float] = []
    for phase in PHASES:
        pm = d[d["phase_v2"] == phase]
        if len(pm) == 0:
            continue
        mean_dd = float(pm[col].mean())
        table.append({"phase_v2": phase, "mean_rawdd_63d": round(mean_dd, 6),
                      "n": int(len(pm))})
        if phase == "Trough":
            trough_vals.append(mean_dd)
        if phase == "Peak":
            peak_vals.append(mean_dd)
    trough_ok = bool(trough_vals and trough_vals[0] < overall)   # deeper = more negative
    peak_ok = bool(peak_vals and peak_vals[0] > overall)         # shallower = less negative
    passed = trough_ok and peak_ok
    reason = ("KG-2 direction reproduced (Trough deeper, Peak shallower than pooled)"
              if passed else
              f"KG-2 VIOLATED: trough_ok={trough_ok} peak_ok={peak_ok} "
              f"(overall_rawdd={overall:.6f})")
    return {"passed": passed, "overall_rawdd_63d": round(overall, 6), "table": table,
            "trough_ok": trough_ok, "peak_ok": peak_ok, "reason": reason}


# ═══════════════════════════════════════════════════════════════════════════════
# Promotion gate
# ═══════════════════════════════════════════════════════════════════════════════

def apply_promotion_gate(cells: list[dict]) -> list[dict]:
    """Set `promoted` on each cell per §14: CI95 excludes 0 AND n_months >= 40 AND era signs
    both match the full-sample gap sign AND survives BH-FDR q=0.10 across ALL 135 gap tests.

    BH-FDR is applied jointly over EVERY cell that carries a boot_p (order preserved via
    fit_cycle_hazard.bh_fdr). Cells without a p-value (collapsed / degenerate) do not enter the
    family count as testable, so they take p=1.0 (never reject) to keep the family size honest
    at 135 — the declared search space is the full lattice, and a null-p cell is a genuine
    non-rejection, not an exclusion.
    """
    pvals = [c["boot_p"] if c["boot_p"] is not None else 1.0 for c in cells]
    bh = bh_fdr(pvals, q=FDR_Q)
    for c, survives_bh in zip(cells, bh):
        c["bh_survives"] = bool(survives_bh)
        ci = c.get("ci95")
        ci_excl = bool(ci is not None and (ci[0] > 0 or ci[1] < 0))
        n_ok = c["n_months"] >= N_MONTHS_PROMOTE_FLOOR
        gap = c.get("gap")
        full_sign = int(np.sign(gap)) if gap is not None else 0
        era_ok = (c["era_pre_sign"] is not None and c["era_post_sign"] is not None and
                  full_sign != 0 and
                  c["era_pre_sign"] == full_sign and c["era_post_sign"] == full_sign)
        c["promoted"] = bool(ci_excl and n_ok and era_ok and survives_bh)
    return cells


# ═══════════════════════════════════════════════════════════════════════════════
# Trial-budget declaration (house convention: log_declared_budget BEFORE any p-value)
# ═══════════════════════════════════════════════════════════════════════════════

def declare_trial_budget(ledger_path: Path, *, run_at: str) -> None:
    """Register the multiple-testing budget as a runtime log_declared_budget BEFORE any
    p-value (mirrors §12/§13 runner). Under --smoke the ledger_path is a scratch file, never
    data/trial_ledger.jsonl."""
    from engine.trial_ledger import TrialLedger
    led = TrialLedger(path=ledger_path, family=FAMILY)
    led.log_declared_budget(
        N_TRIALS, family=FAMILY,
        reason=(f"PREREGISTRATION.md §14 cycle_pattern_lattice_v0: "
                f"(15 L-A + 30 L-B) × 3 targets = 135 pre-registered cells; run_at={run_at}"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Factory candidates (promoted cells only)
# ═══════════════════════════════════════════════════════════════════════════════

def _candidate_from_cell(cell: dict, *, artifact_path: str, created_at: str) -> dict:
    """Project one promoted cell into a CYCLE_PATTERN_CANDIDATE_SCHEMA row (status 'screened',
    trial_family 'lattice_v0', evidence = the artifact path)."""
    tp = f"/trend_pass={cell['trend_pass']:.0f}" if "trend_pass" in cell else ""
    cid = (f"rf-{created_at[:10].replace('-', '')}-cycle_pattern-{cell['lattice']}"
           f"-{cell['phase_v2']}-{cell['family']}{tp.replace('/', '-')}-{cell['target']}")
    statement = (f"{cell['lattice']} cell phase_v2={cell['phase_v2']} family={cell['family']}"
                 f"{tp}: {cell['target']} gap {cell['gap']} vs phase-pooled (CI95 {cell['ci95']})")
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
                       f"differs from its phase-pooled baseline"),
        "mechanism": ("phase×structure conditioning captures a persistent cross-sectional "
                      "regularity in the price-derived cycle lattice (no macro/quad leak)"),
        "statement": statement,
        "target": cell["target"],
        "scope": {"families": [cell["family"]], "regions": [], "sample": "pre-2024 embargoed"},
        "trial_family": TRIAL_FAMILY_SUFFIX,
        "artifacts": {"evidence": artifact_path, "gap": cell["gap"], "ci95": cell["ci95"],
                      "n_months": cell["n_months"], "boot_p": cell["boot_p"]},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _r6(x) -> float | None:
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(xf) else round(xf, 6)


def _cells_to_parquet(cells: list[dict], path: Path) -> None:
    """Compact cells parquet (flat rows; ci95 unpacked to ci_lo/ci_hi)."""
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
            "promoted": c["promoted"],
        })
    pd.DataFrame(rows).to_parquet(path, index=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestration
# ═══════════════════════════════════════════════════════════════════════════════

def _run(panel_path: Path, out_dir: Path, *, smoke: bool = False,
         ledger_path: Path | None = None, write: bool = True) -> dict:
    panel, epoch = _load_panel(panel_path)
    panel = truncate_embargo(panel)                      # EMBARGO before ANY estimate (§14)
    run_at = datetime.now(timezone.utc).isoformat()

    print("[W4.4-join] building phase_v2 + forward joins (rdd_63d) ...")
    joined = build_panel_with_returns(panel)             # W4.4 verbatim → phase_v2, rdd_63d
    joined["date"] = pd.to_datetime(joined["date"])
    df = build_targets(joined)

    lattices = ["L-A"] if smoke else ["L-A", "L-B"]
    targets = [TARGETS[0]] if smoke else TARGETS
    if smoke:
        # one lattice (L-A) × one target, first 50 months, scratch ledger, no real writes.
        keep_months = np.sort(df["date"].unique())[:50]
        df = df[df["date"].isin(keep_months)].reset_index(drop=True)
        print(f"[SMOKE] L-A × {targets[0]} only, first 50 months, {len(df)} rows")

    # ── ANTI-MINING LAW (§14): print the candidate count BEFORE any evaluation ──────
    print(f"CANDIDATE COUNT (pre-registered, evaluated BEFORE any p-value): {N_TRIALS} "
          f"cells = (15 L-A + 30 L-B) × 3 targets  [family={FAMILY}]")

    # ── Trial-budget declaration (log_declared_budget BEFORE any p-value) ───────────
    if ledger_path is None:
        ledger_path = (Path(tempfile.gettempdir()) / "cpi_lattice_smoke_trial_ledger.jsonl"
                       if smoke else _REPO / "data" / "trial_ledger.jsonl")
    declare_trial_budget(ledger_path, run_at=run_at)
    print(f"Declared trial budget: family={FAMILY} n={N_TRIALS} → {ledger_path}")

    # ── SANITY GATE (raw-DD KG-2 direction) — abort as pipeline error if violated ───
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
        print("\n[ABORT] Sanity gate FAILED — this is a PIPELINE ERROR, not a finding. "
              "The raw-DD phase ordering does not reproduce KG-2; refusing to emit estimates.",
              file=sys.stderr)
        sys.exit(2)

    # ── Compute all cells across lattices × targets ─────────────────────────────────
    all_cells: list[dict] = []
    for lattice in lattices:
        for target in targets:
            print(f"[cells] {lattice} × {target} ...")
            cells = compute_lattice_cells(df, lattice, target)
            all_cells.extend(cells)
    print(f"[cells] computed {len(all_cells)} cells "
          f"({'smoke subset' if smoke else 'full 135 expected'})")

    # ── Promotion gate (BH-FDR jointly across the family) ───────────────────────────
    apply_promotion_gate(all_cells)
    promotions = [c for c in all_cells if c["promoted"]]
    n_promoted = len(promotions)

    artifact = {
        "schema": 1,
        "registered_ref": "PREREGISTRATION.md §14",
        "run_at": run_at,
        "embargo": EMBARGO_DATE.strftime("%Y-%m-%d"),
        "panel_epoch": epoch,
        "sanity_gate": sanity,
        "candidate_count_printed": N_TRIALS,
        "cells": all_cells,
        "promotions": promotions,
        "n_promoted": n_promoted,
    }

    if smoke:
        print(f"[SMOKE] {len(all_cells)} cells, {n_promoted} promoted. "
              "No real artifacts written.")
        return {"smoke": True, "cells": all_cells, "sanity_gate": sanity}

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        art_path = out_dir / "batch1.json"
        art_path.write_text(json.dumps(artifact, indent=2, default=str))
        _cells_to_parquet(all_cells, out_dir / "batch1_cells.parquet")
        print(f"Wrote {art_path} and {out_dir/'batch1_cells.parquet'}")

    # ── Factory candidates (only if promotions > 0) ─────────────────────────────────
    truth_guard_flags: list[dict] = []
    if n_promoted > 0:
        art_abs = out_dir / "batch1.json"
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
            # rewrite artifact with the flags now attached
            (out_dir / "batch1.json").write_text(json.dumps(artifact, indent=2, default=str))
            print(f"Wrote {len(candidates)} factory candidates → {_CANDIDATES_PATH}; "
                  f"truth_guard flags: {len(truth_guard_flags)}")

    # ── Honest run-log summary ──────────────────────────────────────────────────────
    print(f"\nRESULT (panel_epoch={epoch}, embargo<{EMBARGO_DATE.date()}, "
          f"cells={len(all_cells)}): {n_promoted} promoted / {N_TRIALS}")
    for c in promotions:
        tp = f" trend_pass={c['trend_pass']:.0f}" if "trend_pass" in c else ""
        print(f"  PROMOTE {c['lattice']} {c['phase_v2']}/{c['family']}{tp} {c['target']}: "
              f"gap={c['gap']} ci95={c['ci95']} n_months={c['n_months']} "
              f"boot_p={c['boot_p']} era=({c['era_pre_sign']},{c['era_post_sign']})")
    if n_promoted == 0:
        print("  → 0 promotions: a scoped null truth for the two lattices is the honest verdict "
              "(exploration tables ship to the measurement surface either way, §14).")
    return {"artifact": artifact, "n_promoted": n_promoted,
            "truth_guard_flags": truth_guard_flags}


def main(argv=None):
    ap = argparse.ArgumentParser(description="CPI lattice runner (PREREG §14)")
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
