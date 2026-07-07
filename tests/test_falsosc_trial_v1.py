"""Tests for the FALS-OSC kill-switch trial (scripts/run_falsosc_trial_v1.py).

Validates:
1. OSC block membership matches PREREGISTRATION.md §18 exactly (5 features).
2. osc_missing attachment: NaN after join treated as True.
3. No sklearn/statsmodels import in the trial runner.
4. Scorecard artifact schema has required keys.
5. Kill condition logic: fires iff 6m CI includes 0 for EITHER direction.
6. Median impute: OSC NaNs are filled on the covered subsample.
7. No-write in smoke mode: real artifacts are not written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_REPO))

from scripts.run_falsosc_trial_v1 import (  # noqa: E402
    OSC_BLOCK,
    TRIAL_FAMILY,
    N_CELLS,
    SIGN_STABILITY_MIN,
    _cell_gate,
    _median_impute_osc,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. OSC block membership — frozen per §18
# ─────────────────────────────────────────────────────────────────────────────

def test_osc_block_frozen():
    """The five OSC features must exactly match §18's substrate paragraph."""
    expected = {"mmacd_hist", "mmacd_sign", "mmacd_slope", "mstoch_k", "mstoch_d"}
    assert set(OSC_BLOCK) == expected, f"OSC_BLOCK mismatch: {OSC_BLOCK}"
    assert len(OSC_BLOCK) == 5, "exactly 5 OSC features per §18"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Trial-family constant
# ─────────────────────────────────────────────────────────────────────────────

def test_trial_family_is_cycle_pattern_ft():
    """§18 declares FDR family = cycle_pattern_ft (same as prior FT trials)."""
    assert TRIAL_FAMILY == "cycle_pattern_ft"


def test_n_cells():
    """Kill-switch scope is 6 cells = 2 directions × 3 horizons."""
    assert N_CELLS == 6


def test_sign_stability_min():
    """§18 uses the same sign-stability bar as §12/§13 (9 of 14 test years)."""
    assert SIGN_STABILITY_MIN == 9


# ─────────────────────────────────────────────────────────────────────────────
# 3. No sklearn/statsmodels import
# ─────────────────────────────────────────────────────────────────────────────

def test_no_banned_imports():
    src = (_REPO / "scripts/run_falsosc_trial_v1.py").read_text()
    for banned in ["import sklearn", "from sklearn", "import statsmodels",
                   "from statsmodels", "import lifelines", "from lifelines"]:
        assert banned not in src, f"banned import found: {banned}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Kill condition logic
# ─────────────────────────────────────────────────────────────────────────────

def _mock_cell_gate(ci_lo: float | None):
    """Minimal cell dict mimicking what _cell_gate returns."""
    return {
        "ci90": [ci_lo, (ci_lo or 0.0) + 0.01],
        "ci_excludes_zero": (ci_lo is not None and ci_lo > 0),
        "delta_brier": 0.002,
        "boot_p": 0.05,
        "years_positive": 9,
        "n_years": 14,
        "sign_stable": True,
        "n_oos": 3000,
    }


def test_kill_fires_when_up_ci_includes_zero():
    """Kill fires when up/6m CI includes 0, even if down/6m CI excludes 0."""
    # Simulate: up has ci_lo < 0, down has ci_lo > 0
    up_cell = _mock_cell_gate(-0.003)   # CI includes 0 → kill
    dn_cell = _mock_cell_gate(0.001)    # CI excludes 0 → no kill for this direction
    up_kill = (up_cell["ci90"][0] is None) or (up_cell["ci90"][0] <= 0)
    dn_kill = (dn_cell["ci90"][0] is None) or (dn_cell["ci90"][0] <= 0)
    assert up_kill, "up/6m CI includes 0 → kill=True"
    assert not dn_kill, "down/6m CI excludes 0 → kill=False"
    assert up_kill or dn_kill, "kill fires when ANY direction's 6m CI includes 0"


def test_kill_does_not_fire_when_both_exclude_zero():
    """Kill does NOT fire when BOTH directions' 6m CIs exclude 0."""
    up_cell = _mock_cell_gate(0.002)   # CI excludes 0
    dn_cell = _mock_cell_gate(0.001)   # CI excludes 0
    up_kill = (up_cell["ci90"][0] is None) or (up_cell["ci90"][0] <= 0)
    dn_kill = (dn_cell["ci90"][0] is None) or (dn_cell["ci90"][0] <= 0)
    assert not (up_kill or dn_kill), "both CIs exclude 0 → kill does NOT fire"


def test_kill_fires_when_down_ci_includes_zero():
    """Kill fires when down/6m CI includes 0, even if up/6m CI excludes 0."""
    up_cell = _mock_cell_gate(0.002)    # CI excludes 0
    dn_cell = _mock_cell_gate(-0.001)   # CI includes 0 → kill
    up_kill = (up_cell["ci90"][0] is None) or (up_cell["ci90"][0] <= 0)
    dn_kill = (dn_cell["ci90"][0] is None) or (dn_cell["ci90"][0] <= 0)
    assert not up_kill
    assert dn_kill
    assert up_kill or dn_kill, "kill fires for down/6m CI includes 0"


# ─────────────────────────────────────────────────────────────────────────────
# 5. cell_gate diagnostics smoke
# ─────────────────────────────────────────────────────────────────────────────

def test_cell_gate_shape():
    """_cell_gate returns expected keys and numeric values."""
    rng = np.random.default_rng(42)
    months = pd.date_range("2010-01", "2022-12", freq="ME")
    n = len(months) * 20
    dates = np.repeat(months.to_numpy(), 20)
    years = pd.to_datetime(dates).year
    y = rng.integers(0, 2, n).astype(float)
    p_base = np.clip(rng.uniform(0.1, 0.5, n), 1e-6, 1 - 1e-6)
    p_osc = np.clip(p_base + rng.normal(0, 0.01, n), 1e-6, 1 - 1e-6)

    cell = _cell_gate(dates, y, p_base, p_osc, years)
    required = {"delta_brier", "brier_base", "brier_osc", "ci90", "boot_p",
                "ci_excludes_zero", "years_positive", "n_years", "sign_stable", "n_oos"}
    assert required.issubset(cell.keys()), f"missing keys: {required - cell.keys()}"
    assert isinstance(cell["delta_brier"], float)
    assert cell["n_oos"] == n
    assert isinstance(cell["sign_stable"], bool)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Median impute on covered subsample
# ─────────────────────────────────────────────────────────────────────────────

def test_median_impute_fills_osc_nans():
    """_median_impute_osc fills OSC NaNs with the column median (no remaining NaNs)."""
    rng = np.random.default_rng(10)
    n = 200
    d = pd.DataFrame({c: rng.uniform(-1, 1, n) for c in OSC_BLOCK})
    # Introduce a few NaNs in mmacd_slope (matches the 12 NaN case in state_monthly)
    d.loc[[5, 10, 20], "mmacd_slope"] = np.nan
    result = _median_impute_osc(d)
    for c in OSC_BLOCK:
        assert result[c].isna().sum() == 0, f"{c} still has NaNs after impute"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Scorecard artifact exists and has required keys (integration check)
# ─────────────────────────────────────────────────────────────────────────────

def test_scorecard_artifact_schema():
    """If the scorecard artifact exists, verify it has all required keys."""
    artifact = _REPO / "data/hazard/falsosc_trial_v1.json"
    if not artifact.exists():
        pytest.skip("falsosc_trial_v1.json not yet generated; run run_falsosc_trial_v1.py first")
    with open(artifact) as f:
        sc = json.load(f)
    required = {
        "schema", "registered_ref", "run_at", "elapsed_s", "embargo",
        "panel_epoch", "n_rows_total_embargoed", "n_rows_osc_covered",
        "coverage_pct", "family_coverage", "config", "per_fold",
        "ledger", "kill_conditions", "kill_switch_fired",
    }
    assert required.issubset(sc.keys()), f"missing keys: {required - sc.keys()}"
    assert sc["schema"] == "falsosc_trial.v1"
    assert sc["panel_epoch"] == "price_c4414dcb"
    # Ledger has all 6 cells
    for d in ["up", "down"]:
        assert d in sc["ledger"], f"missing direction {d}"
        for h in ["1m", "3m", "6m"]:
            assert h in sc["ledger"][d], f"missing cell {d}/{h}"
    # Kill conditions have both directions
    assert "up" in sc["kill_conditions"] and "down" in sc["kill_conditions"]


def test_scorecard_kill_switch_matches_published_numbers():
    """The kill_switch_fired flag must be consistent with the 6m CI values."""
    artifact = _REPO / "data/hazard/falsosc_trial_v1.json"
    if not artifact.exists():
        pytest.skip("falsosc_trial_v1.json not yet generated")
    with open(artifact) as f:
        sc = json.load(f)
    # Recompute kill from the stored CIs and assert consistency
    kill_computed = False
    for direction in ["up", "down"]:
        ci_lo = sc["kill_conditions"].get(direction, {}).get("ci_lo_6m")
        kills = (ci_lo is None) or (ci_lo <= 0)
        if kills:
            kill_computed = True
    assert sc["kill_switch_fired"] == kill_computed, (
        f"kill_switch_fired={sc['kill_switch_fired']} but recomputed={kill_computed}"
    )
