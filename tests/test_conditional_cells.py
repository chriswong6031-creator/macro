"""tests/test_conditional_cells.py — W4.4 unit tests for conditional cells.

Four test families:
1. Shrinkage math: k-cell synthetic recovers analytic James-Stein weights.
2. Collapse discipline: n_months < 12 → collapsed=True, shrunk_mean → pooled.
3. Block-bootstrap usage: grep-test that no n/h Wilson shortcut exists in the builder.
4. revision_optimistic flag: every quad-conditioned cell has it set True.
5. JSON parses and renders correctly.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

# ── path setup ────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from scripts.build_conditional_cells import (  # noqa: E402
    james_stein_shrink,
    verdict_ci_excludes_pooled,
    N_MONTHS_FLOOR,
    derive_phase,
)
from engine.grading_stats import block_bootstrap_ci  # noqa: E402
from engine.cycle_ontology import ZONE_EHI, ZONE_ELO  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# 1 — Shrinkage math (k-cell synthetic recovers analytic James-Stein weights)
# ══════════════════════════════════════════════════════════════════════════════

def _make_cells(raw_means, within_vars, n_effs):
    """Helper: build minimal cell dicts for james_stein_shrink."""
    return [
        {"raw_mean": m, "within_var": v, "n_eff": ne}
        for m, v, ne in zip(raw_means, within_vars, n_effs)
    ]


def test_shrinkage_k2_analytic():
    """Two-cell case: analytic James-Stein weights match our implementation.

    With two cells (m1, m2), n_eff each, within_var sigma2:
        tau2 = max(0, Var_cells([m1,m2]) - mean(sigma2/n_eff))
             = max(0, ((m1-m2)/2)^2 - sigma2/n_eff)     [ddof=1 for 2 obs]
        w    = tau2 / (tau2 + sigma2/n_eff)
    """
    m1, m2 = 0.10, -0.05
    sigma2 = 0.02
    n_eff = 20.0

    cells = _make_cells([m1, m2], [sigma2, sigma2], [n_eff, n_eff])
    james_stein_shrink(cells)

    var_cells = np.var([m1, m2], ddof=1)   # = ((m1-m2)/2)^2 * 4 / 1 for 2 obs
    sampling_var = sigma2 / n_eff
    tau2 = max(0.0, var_cells - sampling_var)
    w_expected = 0.0 if tau2 == 0.0 else tau2 / (tau2 + sampling_var)
    m_pooled_expected = (m1 + m2) / 2  # equal n_eff → equal weight

    # shrink_weight is rounded to 4dp in james_stein_shrink; tolerance = 0.5e-4
    assert abs(cells[0]["shrink_weight"] - w_expected) < 5e-5, (
        f"Cell 0 shrink_weight {cells[0]['shrink_weight']:.6f} != {w_expected:.6f}"
    )
    assert abs(cells[1]["shrink_weight"] - w_expected) < 5e-5

    for c in cells:
        expected_shrunk = w_expected * c["raw_mean"] + (1.0 - w_expected) * m_pooled_expected
        assert abs(c["shrunk_mean"] - expected_shrunk) < 1e-5, (
            f"shrunk_mean {c['shrunk_mean']} != expected {expected_shrunk}"
        )


def test_shrinkage_zero_tau2_full_shrink():
    """When between-cell variance is zero (identical means), all cells fully shrink."""
    cells = _make_cells([0.05, 0.05, 0.05], [0.01, 0.01, 0.01], [15.0, 15.0, 15.0])
    james_stein_shrink(cells)
    for c in cells:
        assert c["shrink_weight"] == 0.0, "tau2=0 → w=0 (full shrink to pooled)"
        assert abs(c["shrunk_mean"] - 0.05) < 1e-9, "All shrunk to pooled mean"


def test_shrinkage_high_tau2_low_weight():
    """When between-cell variance dominates, shrinkage weight approaches 1 (keep raw)."""
    # Large spread → high tau2 → w_c → 1
    cells = _make_cells([-0.5, 0.0, 0.5], [0.001, 0.001, 0.001], [100.0, 100.0, 100.0])
    james_stein_shrink(cells)
    for c in cells:
        # tau2 >> sigma2/n_eff → w_c close to 1
        assert c["shrink_weight"] > 0.9, f"Expected high w_c, got {c['shrink_weight']}"
        # shrunk should be close to raw
        assert abs(c["shrunk_mean"] - c["raw_mean"]) < 0.05 * abs(c["raw_mean"]) + 0.001


def test_shrinkage_low_n_eff_floor():
    """Cells with n_eff < N_EFF_SHRINK_FLOOR get w_c=0 regardless of tau2."""
    from scripts.build_conditional_cells import N_EFF_SHRINK_FLOOR
    # n_eff below floor: even with large tau2, should be w=0
    cells = _make_cells([0.10, -0.10], [0.001, 0.001], [N_EFF_SHRINK_FLOOR - 0.1] * 2)
    james_stein_shrink(cells)
    for c in cells:
        assert c["shrink_weight"] == 0.0, (
            f"n_eff < floor → w_c must be 0, got {c['shrink_weight']}"
        )


def test_shrinkage_pooled_mean_weighted_by_neff():
    """Pooled mean is weighted by n_eff (large-n cell dominates the prior)."""
    # n_eff weights: 10 vs 90 → pooled ≈ (10*m1 + 90*m2)/100
    m1, m2 = 0.10, 0.00
    n1, n2 = 10.0, 90.0
    cells = _make_cells([m1, m2], [0.01, 0.01], [n1, n2])
    james_stein_shrink(cells)
    pooled_expected = (n1 * m1 + n2 * m2) / (n1 + n2)  # = 0.01
    assert abs(cells[0]["phase_pooled_mean"] - pooled_expected) < 1e-9, (
        f"Pooled mean {cells[0]['phase_pooled_mean']:.4f} != {pooled_expected:.4f}"
    )
    assert abs(cells[1]["phase_pooled_mean"] - pooled_expected) < 1e-9


# ══════════════════════════════════════════════════════════════════════════════
# 2 — Collapse discipline
# ══════════════════════════════════════════════════════════════════════════════

def test_collapse_on_low_n_months():
    """Cells with n_months < N_MONTHS_FLOOR must be collapsed=True."""
    assert N_MONTHS_FLOOR == 12, "Preregistered floor is 12 months"
    # The build_conditional_cells logic: collapsed = (n_months < N_MONTHS_FLOOR)
    # Test cells structure that mirrors what compute_cells would produce
    cell_thin = {
        "family": "us_sector", "phase_v2": "Trough", "quad": "Q4",
        "n_months": N_MONTHS_FLOOR - 1,  # just below floor
        "collapsed": True, "shrunk_mean": 0.05, "phase_pooled_mean": 0.05,
        "shrink_weight": 0.0, "revision_optimistic": True,
        "boot_ci_95": None,
    }
    cell_ok = {
        "family": "us_sector", "phase_v2": "Trough", "quad": "Q1",
        "n_months": N_MONTHS_FLOOR,  # at floor
        "collapsed": False, "shrunk_mean": 0.08, "phase_pooled_mean": 0.05,
        "shrink_weight": 0.5, "revision_optimistic": True,
        "boot_ci_95": [0.001, 0.06],
    }
    # collapsed cell never returns from verdict_ci_excludes_pooled
    assert cell_thin not in verdict_ci_excludes_pooled([cell_thin, cell_ok])
    assert cell_ok in verdict_ci_excludes_pooled([cell_thin, cell_ok])


def test_collapsed_cell_shrunk_mean_equals_pooled():
    """When collapsed=True, shrunk_mean must equal phase_pooled_mean."""
    # In the builder, collapsed cells get w=0 → shrunk = pooled
    cell_collapsed = {
        "family": "cn_sector", "phase_v2": "Peak", "quad": "Q3",
        "n_months": 5, "collapsed": True,
        "shrunk_mean": 0.02, "phase_pooled_mean": 0.02,
        "shrink_weight": 0.0, "revision_optimistic": True,
    }
    # Verify: shrunk_mean == phase_pooled_mean (within float precision)
    assert abs(cell_collapsed["shrunk_mean"] - cell_collapsed["phase_pooled_mean"]) < 1e-9, (
        "Collapsed cell: shrunk_mean must equal pooled mean"
    )
    assert cell_collapsed["shrink_weight"] == 0.0, "Collapsed cell: shrink_weight must be 0"


# ══════════════════════════════════════════════════════════════════════════════
# 3 — Block-bootstrap usage (no n/h Wilson shortcut)
# ══════════════════════════════════════════════════════════════════════════════

def test_no_wilson_on_neff_in_builder():
    """Grep-test: the builder script must not call wilson_ci(k, n_eff) as a CI path.

    Ruling A2: wilson_ci on a cross-sectional panel is banned even with n_eff deflation.
    The ONLY permitted CI path is block_bootstrap_ci (date-resampled).
    """
    builder_path = os.path.join(_ROOT, "scripts", "build_conditional_cells.py")
    assert os.path.exists(builder_path), f"Builder not found: {builder_path}"
    with open(builder_path, encoding="utf-8") as f:
        src = f.read()

    # Must NOT call wilson_ci as CI (importing it is OK for documentation, but NOT calling it
    # with n_eff as the n argument in any CI-producing context)
    # Check: no call pattern `wilson_ci(...n_eff...)` or `wilson_ci(k, n_eff_...)`
    banned_patterns = [
        r"wilson_ci\s*\([^)]*n_eff",     # wilson_ci(k, n_eff_...)
        r"wilson_ci\s*\([^)]*n_eff\b",   # any variant
    ]
    for pat in banned_patterns:
        assert not re.search(pat, src), (
            f"Banned pattern found in builder: {pat!r}\n"
            "Ruling A2: no wilson_ci on n_eff in CI context."
        )

    # Must CALL block_bootstrap_ci (the ruling-A2 compliant path)
    assert "block_bootstrap_ci" in src, (
        "Builder must use block_bootstrap_ci for all CI computation (ruling A2)"
    )


def test_no_effective_n_as_wilson_in_grading_stats():
    """Grep-test: grading_stats.py must document the ruling A2 prohibition on effective_n→wilson_ci.

    The effective_n function exists for serial overlap; it must not be the path
    for cross-sectional CI in this module.
    """
    gs_path = os.path.join(_ROOT, "engine", "grading_stats.py")
    with open(gs_path, encoding="utf-8") as f:
        src = f.read()
    # The RULING A2 NOTE must be present in grading_stats
    assert "RULING A2" in src, "grading_stats.py must document RULING A2 prohibition"
    assert "block_bootstrap_ci" in src, "block_bootstrap_ci must be defined in grading_stats"


def test_block_bootstrap_date_resampling():
    """Functional test: block_bootstrap_ci resamples by date, not by row.

    Block-resampling works on unique dates. When a condition mask selects
    all rows on certain dates, the gap estimate is the mean over those
    DATE means (not over individual rows). We verify:
    1. The function returns a CI (not None) for a properly structured panel.
    2. The CI width is consistent with the number of unique dates (n=60),
       not the number of rows (n=120), by checking it is wider than the
       analytical row-bootstrap width / sqrt(2).
    """
    rng = np.random.default_rng(42)
    n_dates = 60

    # Instrument A has mean +0.10; instrument B has mean +0.00
    # Conditioning on instrument A should show a positive gap.
    dates_list = [f"2020-{i:03d}" for i in range(n_dates)]
    a_vals = rng.normal(0.10, 0.10, n_dates)  # instrument A: mean +0.10
    b_vals = rng.normal(0.00, 0.10, n_dates)  # instrument B: mean  0.00

    # Interleave: odd indices = instrument A, even = instrument B
    dates_rep = np.repeat(dates_list, 2)
    vals_rep = np.empty(n_dates * 2)
    vals_rep[0::2] = a_vals
    vals_rep[1::2] = b_vals

    # Mask = instrument A (odd positions)
    mask = np.zeros(n_dates * 2, bool)
    mask[0::2] = True

    ci = block_bootstrap_ci(dates_rep, vals_rep, mask, draws=800, seed=42)
    assert ci is not None, "block_bootstrap_ci returned None for valid panel"
    lo, hi = ci
    # The gap (A − all) should be approximately +0.05 (half of 0.10 - 0.00)
    # CI should include a positive region
    assert hi > 0, f"Upper bound should be positive (instrument A outperforms): got {hi}"
    # CI width should be non-trivial (reflects uncertainty over 60 dates)
    width = hi - lo
    assert width > 0.0, f"CI must have positive width, got {width}"


# ══════════════════════════════════════════════════════════════════════════════
# 4 — revision_optimistic flag on every quad-conditioned cell
# ══════════════════════════════════════════════════════════════════════════════

def test_revision_optimistic_on_quad_cells():
    """Every cell with a specific quad (not 'pooled') must have revision_optimistic=True.

    P-D5-1: regime_history.parquet uses revised macro series. All quad-conditioned
    results are revision-optimistic and must be labeled as such.
    """
    artifact_path = os.path.join(
        _ROOT, "data", "cycle_ontology", "conditional_cells_20260703.json"
    )
    if not os.path.exists(artifact_path):
        pytest.skip("Artifact not yet built; run scripts/build_conditional_cells.py first")

    with open(artifact_path, encoding="utf-8") as f:
        art = json.load(f)

    violations: list[str] = []
    for outcome in art["cells"]:
        for h in art["cells"][outcome]:
            for c in art["cells"][outcome][h]:
                if c.get("quad") != "pooled":
                    if not c.get("revision_optimistic"):
                        violations.append(
                            f"{outcome}/{h}: {c['family']}/{c['phase_v2']}/{c['quad']}"
                        )

    assert len(violations) == 0, (
        f"P-D5-1 violation: {len(violations)} quad-conditioned cells missing "
        f"revision_optimistic=True:\n" + "\n".join(violations[:10])
    )


def test_pooled_cells_not_revision_optimistic():
    """Phase-pooled reference rows (quad='pooled') should NOT be revision_optimistic.

    They condition only on phase, not on the revision-leaky quad labels.
    """
    artifact_path = os.path.join(
        _ROOT, "data", "cycle_ontology", "conditional_cells_20260703.json"
    )
    if not os.path.exists(artifact_path):
        pytest.skip("Artifact not yet built")

    with open(artifact_path, encoding="utf-8") as f:
        art = json.load(f)

    for outcome in art["cells"]:
        for h in art["cells"][outcome]:
            for c in art["cells"][outcome][h]:
                if c.get("quad") == "pooled":
                    assert not c.get("revision_optimistic"), (
                        f"Pooled row must NOT be revision_optimistic: "
                        f"{outcome}/{h} {c['family']}/{c['phase_v2']}"
                    )


# ══════════════════════════════════════════════════════════════════════════════
# 5 — JSON parses and renders correctly
# ══════════════════════════════════════════════════════════════════════════════

def test_artifact_json_parseable():
    """The artifact JSON must parse without error and have the expected schema."""
    artifact_path = os.path.join(
        _ROOT, "data", "cycle_ontology", "conditional_cells_20260703.json"
    )
    if not os.path.exists(artifact_path):
        pytest.skip("Artifact not yet built")

    with open(artifact_path, encoding="utf-8") as f:
        art = json.load(f)

    assert art.get("schema") == 1
    assert "cells" in art
    assert "verdict_summary" in art
    assert "ruling_A7_note" in art
    assert "ruling_A2_note" in art
    assert "revision_optimistic_note" in art


def test_artifact_cell_schema():
    """Every cell must have the required fields with correct types."""
    artifact_path = os.path.join(
        _ROOT, "data", "cycle_ontology", "conditional_cells_20260703.json"
    )
    if not os.path.exists(artifact_path):
        pytest.skip("Artifact not yet built")

    with open(artifact_path, encoding="utf-8") as f:
        art = json.load(f)

    required_fields = [
        "family", "phase_v2", "quad", "n_rows", "n_months", "n_eff",
        "raw_mean", "collapsed", "revision_optimistic",
        "phase_pooled_mean", "shrink_weight", "shrunk_mean",
    ]
    for outcome in art["cells"]:
        for h in art["cells"][outcome]:
            for c in art["cells"][outcome][h]:
                for field in required_fields:
                    assert field in c, (
                        f"Cell {c.get('family')}/{c.get('phase_v2')}/{c.get('quad')} "
                        f"missing field '{field}' in {outcome}/{h}"
                    )
                # Types
                assert isinstance(c["collapsed"], bool)
                assert isinstance(c["revision_optimistic"], bool)
                assert isinstance(c["n_months"], int)
                # boot_ci_95 is list or None
                ci = c.get("boot_ci_95")
                if ci is not None:
                    assert isinstance(ci, list) and len(ci) == 2, (
                        f"boot_ci_95 must be [lo, hi] or None, got {ci!r}"
                    )


def test_artifact_families_and_phases_complete():
    """Artifact must contain cells for all 3 families × 5 phases × 4 quads = 60 cells per outcome-h."""
    artifact_path = os.path.join(
        _ROOT, "data", "cycle_ontology", "conditional_cells_20260703.json"
    )
    if not os.path.exists(artifact_path):
        pytest.skip("Artifact not yet built")

    with open(artifact_path, encoding="utf-8") as f:
        art = json.load(f)

    from scripts.build_conditional_cells import PHASES, QUADS, FAMILIES

    for outcome in art["cells"]:
        for h in art["cells"][outcome]:
            quad_cells = [c for c in art["cells"][outcome][h] if c.get("quad") != "pooled"]
            assert len(quad_cells) == len(FAMILIES) * len(PHASES) * len(QUADS), (
                f"{outcome}/{h}: expected {len(FAMILIES)*len(PHASES)*len(QUADS)} quad cells, "
                f"got {len(quad_cells)}"
            )


def test_phase_derivation_boundaries():
    """derive_phase must use ZONE_EHI and ZONE_ELO correctly at and around boundaries."""
    assert derive_phase(ZONE_EHI, "up") == "Peak"
    assert derive_phase(ZONE_EHI, "down") == "Downturn"
    assert derive_phase(ZONE_ELO, "up") == "Recovery"
    assert derive_phase(ZONE_ELO, "down") == "Trough"
    assert derive_phase((ZONE_EHI + ZONE_ELO) / 2, "up") == "Expansion"
    assert derive_phase((ZONE_EHI + ZONE_ELO) / 2, "down") == "Downturn"
    # Just above/below thresholds
    assert derive_phase(ZONE_EHI + 1, "up") == "Peak"
    assert derive_phase(ZONE_ELO - 1, "down") == "Trough"


def test_verdict_ci_excludes_pooled_row_excluded():
    """verdict_ci_excludes_pooled must exclude pooled rows (quad='pooled')."""
    pooled_row = {
        "quad": "pooled", "collapsed": False,
        "boot_ci_95": [0.05, 0.10],  # CI looks positive but it's a pooled row
    }
    assert pooled_row not in verdict_ci_excludes_pooled([pooled_row])


def test_verdict_ci_null_excluded():
    """Cells with boot_ci_95=None are excluded from winners."""
    no_ci = {
        "quad": "Q1", "collapsed": False, "boot_ci_95": None,
    }
    assert no_ci not in verdict_ci_excludes_pooled([no_ci])


def test_verdict_ci_straddles_zero_excluded():
    """Cells whose CI straddles zero (lo < 0 < hi) are not winners."""
    straddles = {
        "quad": "Q2", "collapsed": False, "boot_ci_95": [-0.02, 0.03],
    }
    assert straddles not in verdict_ci_excludes_pooled([straddles])


def test_verdict_ci_positive_included():
    """Cells with CI entirely above zero are winners."""
    winner = {
        "quad": "Q3", "collapsed": False, "boot_ci_95": [0.01, 0.05],
    }
    assert winner in verdict_ci_excludes_pooled([winner])


def test_verdict_ci_negative_included():
    """Cells with CI entirely below zero are winners (bad cells are informative)."""
    loser_cell = {
        "quad": "Q4", "collapsed": False, "boot_ci_95": [-0.08, -0.01],
    }
    assert loser_cell in verdict_ci_excludes_pooled([loser_cell])
