"""tests/test_cycle_pattern_lattice_batch2.py — guards for the §15 batch-2 lattice runner.

Covers:
  (a) frozen constants match §15 (AST guard — parse SOURCE, not import), incl. the named
      LT2-020 re-test cell spec;
  (b) machinery delegation — embargo/targets/sanity/promotion-gate/bootstrap helpers are the
      SAME objects as the §14 runner; james_stein/derive_phase are the W4.4 objects;
  (c) THE §15 regression test — within-family pooling kills a pure family base-rate offset
      (the §14 confound reproduces a large cross-family diagnostic gap but a ~0 within-family
      gap), while a true within-family phase effect IS detected;
  (d) pool enumeration — L-A pools by family (3×5), L-B pools by family×phase (15×2);
      cell count reconstruction = 135;
  (e) era signs recomputed under the WITHIN-FAMILY pool definition;
  (f) named re-test lookup finds exactly the frozen cell;
  (g) batch-1 candidate resolution logic (pass → keep screened; fail → numeric_rejected);
  (h) --smoke completes on the real panel (data-guarded skipif), writes nothing real.

Pure numpy/pandas. Deterministic (seed 7).
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_RUNNER = _ROOT / "scripts" / "build_cycle_pattern_lattice_batch2.py"

import scripts.build_cycle_pattern_lattice_batch2 as L2  # noqa: E402
import scripts.build_cycle_pattern_lattice_phase0 as L1  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# (a) Frozen constants match §15 (AST guard — parse SOURCE)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_module_const(name: str):
    tree = ast.parse(_RUNNER.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"module-level constant {name!r} not found in {_RUNNER}")


def test_frozen_targets_and_lattices_match_prereg():
    """§15: same search space as §14 — exact targets and lattice dims."""
    assert _parse_module_const("TARGETS") == ["rdd_63d", "turn_event_3m", "phase_persist_3m"]
    lattices = _parse_module_const("LATTICES")
    assert lattices["L-A"] == [] and lattices["L-B"] == ["trend_pass"]
    assert set(lattices) == {"L-A", "L-B"}


def test_frozen_budget_family_and_gate_constants():
    """§15: 135 candidates, family rf.cycle_pattern.lattice_v1, FDR q=0.10, n-floor 40."""
    assert _parse_module_const("N_TRIALS") == 135
    assert _parse_module_const("FAMILY") == "rf.cycle_pattern.lattice_v1"
    assert _parse_module_const("TRIAL_FAMILY_SUFFIX") == "lattice_v1"
    assert _parse_module_const("FDR_Q") == 0.10
    assert _parse_module_const("N_MONTHS_PROMOTE_FLOOR") == 40
    assert (5 * 3 + 5 * 2 * 3) * 3 == 135


def test_frozen_named_retest_spec():
    """§15 LT2-020: the exact CPI-020 cell — L-B, Downturn, cn_sector, trend_pass=0, rdd_63d."""
    spec = _parse_module_const("NAMED_RETEST")
    assert spec["lattice"] == "L-B"
    assert spec["phase_v2"] == "Downturn"
    assert spec["family"] == "cn_sector"
    assert spec["trend_pass"] == 0.0
    assert spec["target"] == "rdd_63d"
    assert spec["truth_id"] == "cycle_truth_cn_downturn_broken_trend_tail_candidate_v1"


def test_embargo_is_the_section14_constant():
    """§15 inherits the §14 embargo object verbatim (import identity, no re-declaration)."""
    assert L2.EMBARGO_DATE is L1.EMBARGO_DATE
    assert L2.EMBARGO_DATE == pd.Timestamp("2024-01-01")
    assert L2.ERA_SPLIT_DATE is L1.ERA_SPLIT_DATE
    assert L2.ERA_SPLIT_DATE == pd.Timestamp("2018-01-01")  # value-pin the frozen era split


def test_gate_constants_cross_pinned_to_consumed_values():
    """apply_promotion_gate is imported from the §14 runner and consumes ITS module globals.
    Cross-pin: batch-2's declared constants must equal the consumed ones, so an edit to
    either module's gate numbers fails THIS suite too."""
    assert L2.FDR_Q == L1.FDR_Q == 0.10
    assert L2.N_MONTHS_PROMOTE_FLOOR == L1.N_MONTHS_PROMOTE_FLOOR == 40


# ══════════════════════════════════════════════════════════════════════════════
# (b) Machinery delegation — same objects, never forked
# ══════════════════════════════════════════════════════════════════════════════

def test_shared_machinery_is_imported_not_forked():
    import scripts.build_conditional_cells as W44
    assert L2.james_stein_shrink is W44.james_stein_shrink
    assert L2.derive_phase is W44.derive_phase
    assert L2.build_panel_with_returns is W44.build_panel_with_returns
    # §14 runner helpers reused verbatim
    assert L2.truncate_embargo is L1.truncate_embargo
    assert L2.build_targets is L1.build_targets
    assert L2.sanity_gate_rawdd is L1.sanity_gate_rawdd
    assert L2.apply_promotion_gate is L1.apply_promotion_gate
    assert L2._boot_gaps_for_pool is L1._boot_gaps_for_phase
    assert L2._ci_and_p is L1._ci_and_p


# ══════════════════════════════════════════════════════════════════════════════
# (c) THE §15 regression test — family base-rate offset vs true within-family effect
# ══════════════════════════════════════════════════════════════════════════════

def _month_ends(n: int) -> list[pd.Timestamp]:
    return [pd.Timestamp("2005-01-01") + pd.offsets.MonthEnd(k + 1) for k in range(n)]


def _synthetic_panel(*, family_offset: float, cn_downturn_effect: float,
                     n_months: int = 120, seed: int = 7) -> pd.DataFrame:
    """Synthetic target frame over 2 families × 5 phases × n_months.

    ``family_offset``: cn_sector rows get target += offset EVERYWHERE (pure base-rate offset —
    the §14 confound generator; no phase structure within the family).
    ``cn_downturn_effect``: cn_sector×Downturn rows additionally shift by this (a TRUE
    within-family phase effect).
    """
    rng = np.random.default_rng(seed)
    phases = ["Trough", "Recovery", "Expansion", "Peak", "Downturn"]
    rows = []
    for me in _month_ends(n_months):
        for family, base in (("us_sector", 0.0), ("cn_sector", family_offset)):
            for phase in phases:
                for k in range(4):  # 4 members per family-phase-month (trend_pass 0/1 balanced)
                    v = base + rng.normal(0, 0.01)
                    if family == "cn_sector" and phase == "Downturn":
                        v += cn_downturn_effect
                    rows.append({
                        "date": me, "id": f"{family}-{phase}-{k}", "family": family,
                        "phase_v2": phase, "trend_pass": float(k % 2),
                        "rdd_63d": v, "censored": 0,
                    })
    return pd.DataFrame(rows)


def _get_cell(cells, *, phase, family, trend_pass=None):
    for c in cells:
        if (c["phase_v2"] == phase and c["family"] == family
                and c.get("trend_pass") == trend_pass):
            return c
    raise AssertionError(f"cell not found: {phase}/{family}/tp={trend_pass}")


def test_pure_family_offset_yields_zero_within_family_gap_but_large_xfam_diag():
    """The §14 confound generator: cn_sector is offset −0.10 EVERYWHERE, no phase structure.
    Within-family gaps must be ~0 (CI includes 0 for every cn cell); the cross-family
    DIAGNOSTIC gap must show the offset (~−0.10) — proving the §15 baseline kills exactly
    the confound the §14 baseline promoted."""
    df = _synthetic_panel(family_offset=-0.10, cn_downturn_effect=0.0)
    cells = L2.compute_lattice_cells(df, "L-A", "rdd_63d")
    for phase in ["Trough", "Recovery", "Expansion", "Peak", "Downturn"]:
        c = _get_cell(cells, phase=phase, family="cn_sector")
        assert c["gap"] is not None and abs(c["gap"]) < 0.005, (
            f"within-family gap should be ~0 under a pure family offset, got {c['gap']} "
            f"({phase})")
        assert c["ci95"] is not None and c["ci95"][0] <= 0 <= c["ci95"][1], (
            f"CI must straddle 0 under a pure family offset, got {c['ci95']} ({phase})")
        assert c["gap_xfam"] is not None and c["gap_xfam"] < -0.04, (
            f"cross-family diagnostic must expose the offset, got {c['gap_xfam']} ({phase})")


def test_true_within_family_effect_is_detected():
    """A real cn_sector×Downturn effect (−0.08) with no global family offset: the L-A
    cn/Downturn within-family gap must be clearly negative with CI excluding 0, and the
    other cn phases must NOT show it (their gaps are small/positive-compensating)."""
    df = _synthetic_panel(family_offset=0.0, cn_downturn_effect=-0.08)
    cells = L2.compute_lattice_cells(df, "L-A", "rdd_63d")
    c = _get_cell(cells, phase="Downturn", family="cn_sector")
    assert c["gap"] is not None and c["gap"] < -0.04
    assert c["ci95"] is not None and c["ci95"][1] < 0, f"CI must exclude 0, got {c['ci95']}"
    # a non-Downturn cn cell must not carry the effect (small positive compensation only)
    c2 = _get_cell(cells, phase="Peak", family="cn_sector")
    assert c2["gap"] is not None and abs(c2["gap"]) < 0.05
    # us_sector Downturn must be clean (~0)
    c3 = _get_cell(cells, phase="Downturn", family="us_sector")
    assert c3["gap"] is not None and abs(c3["gap"]) < 0.005


def test_lb_pool_isolates_trend_within_family_phase():
    """L-B: a trend_pass=0 effect confined to cn_sector×Downturn must appear in exactly that
    cell vs its family×phase pool, not in trend cells of other family-phases."""
    df = _synthetic_panel(family_offset=0.0, cn_downturn_effect=0.0)
    # inject: cn Downturn broken-trend (trend_pass=0) deeper by −0.06
    m = ((df["family"] == "cn_sector") & (df["phase_v2"] == "Downturn")
         & (df["trend_pass"] == 0.0))
    df.loc[m, "rdd_63d"] -= 0.06
    cells = L2.compute_lattice_cells(df, "L-B", "rdd_63d")
    c = _get_cell(cells, phase="Downturn", family="cn_sector", trend_pass=0.0)
    assert c["gap"] is not None and c["gap"] < -0.02
    assert c["ci95"] is not None and c["ci95"][1] < 0
    # complement cell (trend_pass=1) must mirror positively within the same pool
    c1 = _get_cell(cells, phase="Downturn", family="cn_sector", trend_pass=1.0)
    assert c1["gap"] is not None and c1["gap"] > 0.02
    # us_sector Downturn trend cells stay clean
    c2 = _get_cell(cells, phase="Downturn", family="us_sector", trend_pass=0.0)
    assert c2["gap"] is not None and abs(c2["gap"]) < 0.005


# ══════════════════════════════════════════════════════════════════════════════
# (d) Pool enumeration
# ══════════════════════════════════════════════════════════════════════════════

def test_pool_specs_shape():
    la = L2._pool_specs("L-A")
    assert len(la) == 3 and all(len(p["cells"]) == 5 for p in la)
    assert all(set(p["pool_key"]) == {"family"} for p in la)
    lb = L2._pool_specs("L-B")
    assert len(lb) == 15 and all(len(p["cells"]) == 2 for p in lb)
    assert all(set(p["pool_key"]) == {"family", "phase_v2"} for p in lb)
    n_cells = sum(len(p["cells"]) for p in la) + sum(len(p["cells"]) for p in lb)
    assert n_cells * 3 == 135  # × 3 targets = the declared budget


# ══════════════════════════════════════════════════════════════════════════════
# (e) Era signs under the WITHIN-FAMILY pool definition
# ══════════════════════════════════════════════════════════════════════════════

def test_era_signs_use_within_family_pool():
    """Construct eras where the cell is BELOW its family pool pre-2018 and ABOVE post-2018;
    the within-family era signs must be (−1, +1) even though vs a cross-family pool both
    eras would look negative (family offset −0.5 dominates)."""
    rows = []
    for yr, cell_shift in ((2015, -0.1), (2020, +0.1)):
        for m in range(1, 13):
            me = pd.Timestamp(year=yr, month=m, day=1) + pd.offsets.MonthEnd(0)
            for phase in ["Peak", "Downturn"]:
                for k in range(3):
                    # cn family sits at −0.5 everywhere (offset); Downturn cell shifts by era
                    v = -0.5 + (cell_shift if phase == "Downturn" else 0.0)
                    rows.append({"date": me, "id": f"cn-{phase}-{k}", "family": "cn_sector",
                                 "phase_v2": phase, "trend_pass": 0.0, "rdd_63d": v,
                                 "censored": 0})
                    rows.append({"date": me, "id": f"us-{phase}-{k}", "family": "us_sector",
                                 "phase_v2": phase, "trend_pass": 0.0, "rdd_63d": 0.0,
                                 "censored": 0})
    df = pd.DataFrame(rows)
    pre, post = L2._era_signs_wf(df, {"family": "cn_sector", "phase_v2": "Downturn"},
                                 {"family": "cn_sector"}, "rdd_63d")
    assert pre == -1 and post == +1


# ══════════════════════════════════════════════════════════════════════════════
# (f) Named re-test lookup
# ══════════════════════════════════════════════════════════════════════════════

def test_named_retest_lookup_exact():
    cells = [
        {"lattice": "L-B", "phase_v2": "Downturn", "family": "cn_sector",
         "trend_pass": 1.0, "target": "rdd_63d"},
        {"lattice": "L-B", "phase_v2": "Downturn", "family": "cn_sector",
         "trend_pass": 0.0, "target": "turn_event_3m"},
        {"lattice": "L-B", "phase_v2": "Downturn", "family": "cn_sector",
         "trend_pass": 0.0, "target": "rdd_63d"},   # ← the one
        {"lattice": "L-A", "phase_v2": "Downturn", "family": "cn_sector",
         "target": "rdd_63d"},
    ]
    hit = L2.find_named_retest_cell(cells)
    assert hit is cells[2]
    assert L2.find_named_retest_cell(cells[:2]) is None


# ══════════════════════════════════════════════════════════════════════════════
# (g) Batch-1 candidate resolution logic
# ══════════════════════════════════════════════════════════════════════════════

def test_batch1_candidate_resolution(tmp_path):
    b1 = {"promotions": [
        {"lattice": "L-A", "phase_v2": "Peak", "family": "us_sector",
         "target": "rdd_63d", "gap": 0.03},
        {"lattice": "L-B", "phase_v2": "Downturn", "family": "cn_sector",
         "trend_pass": 0.0, "target": "rdd_63d", "gap": -0.0597},
    ]}
    p = tmp_path / "batch1.json"
    p.write_text(json.dumps(b1))
    cells = [
        {"lattice": "L-A", "phase_v2": "Peak", "family": "us_sector",
         "target": "rdd_63d", "gap": 0.001, "promoted": False},
        {"lattice": "L-B", "phase_v2": "Downturn", "family": "cn_sector",
         "trend_pass": 0.0, "target": "rdd_63d", "gap": -0.05, "promoted": True},
    ]
    res = L2.resolve_batch1_candidates(cells, p)
    assert len(res) == 2
    by_key = {r["cell_key"]: r for r in res}
    assert by_key["L-A-Peak-us_sector-rdd_63d"]["resolution"] == "numeric_rejected"
    assert (by_key["L-B-Downturn-cn_sector-trend_pass=0-rdd_63d"]["resolution"]
            == "keep_screened_with_batch2_evidence")
    # missing artifact → empty resolution list (no crash)
    assert L2.resolve_batch1_candidates(cells, tmp_path / "nope.json") == []


# ══════════════════════════════════════════════════════════════════════════════
# (h) --smoke completes on the real panel (data-guarded skipif), writes nothing real
# ══════════════════════════════════════════════════════════════════════════════

_PANEL = _ROOT / "data" / "hazard" / "panel_price_c4414dcb.parquet"


@pytest.mark.skipif(not _PANEL.exists(), reason="hazard panel not present")
def test_smoke_completes_and_writes_nothing_real():
    real_artifact = _ROOT / "data" / "cycle_pattern" / "lattice" / "batch2.json"
    real_cands = _ROOT / "data" / "cycle_pattern" / "pattern_candidates.jsonl"
    real_ledger = _ROOT / "data" / "trial_ledger.jsonl"

    art_before = real_artifact.exists()
    cands_before = real_cands.read_text() if real_cands.exists() else None
    ledger_before = real_ledger.read_text() if real_ledger.exists() else None

    proc = subprocess.run(
        [sys.executable, str(_RUNNER), "--smoke"],
        cwd=str(_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"smoke failed:\nSTDOUT{proc.stdout}\nSTDERR{proc.stderr}"
    out = proc.stdout
    assert "CANDIDATE COUNT" in out and "135" in out
    assert "SANITY GATE" in out
    assert "No real artifacts written" in out
    assert "WITHIN-FAMILY" in out or "within-family" in out

    assert real_artifact.exists() == art_before, "smoke must not create the real artifact"
    cands_after = real_cands.read_text() if real_cands.exists() else None
    assert cands_after == cands_before, "smoke must not touch pattern_candidates.jsonl"
    ledger_after = real_ledger.read_text() if real_ledger.exists() else None
    assert ledger_after == ledger_before, "smoke must not touch the real trial ledger"
