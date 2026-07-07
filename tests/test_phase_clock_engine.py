"""Acceptance tests for engine/cycle_pattern/phase_clock.py and
scripts/build_phase_clock_table.py (PREREGISTRATION.md §18 Wave 1).

Guards:
  (a) classify() covers all 6 valid states with concrete inputs.
  (b) ambiguous=True fires on fall-through bars (not matched by any of the 6 rules).
  (c) NaN inputs yield state='unknown', ambiguous=True.
  (d) Sign boundary: mmacd_sign=0 falls through to early_contraction (ambiguous).
  (e) Threshold boundary: stoch_k exactly at 20 (not < 20) does NOT fire capitulation.
  (f) Threshold boundary: stoch_k exactly at 80 fires late_expansion.
  (g) FROZEN constants: STOCH_OVERSOLD==20, STOCH_OVERBOUGHT==80.
  (h) classify_array is deterministic across two identical calls.
  (i) build_phase_clock_table is deterministic: two runs produce frame-equal output.
  (j) Survival table has expected columns and non-negative n_obs/n_turns.
  (k) Table builder smoke flag suppresses file writes.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_REPO))

from engine.cycle_pattern.phase_clock import (  # noqa: E402
    STOCH_OVERSOLD,
    STOCH_OVERBOUGHT,
    VALID_STATES,
    UNKNOWN_STATE,
    PhaseClockResult,
    classify,
    classify_array,
)

_SURVIVAL_TABLE = _REPO / "data" / "cycle_pattern" / "phase_clock_survival.parquet"
_PANEL_EXISTS = (_REPO / "data" / "hazard" / "panel_price_c4414dcb.parquet").exists()
_STATE_EXISTS = (_REPO / "data" / "cycle_pattern" / "state_monthly.parquet").exists()


# ─────────────────────────────────────────────────────────────────────────────
# (g) FROZEN constants guard — values can never be tuned after preregistration
# ─────────────────────────────────────────────────────────────────────────────

def test_frozen_stoch_oversold():
    """STOCH_OVERSOLD must be 20 — frozen by PREREGISTRATION.md §18."""
    assert STOCH_OVERSOLD == 20.0, (
        f"STOCH_OVERSOLD was changed to {STOCH_OVERSOLD}; "
        "thresholds are frozen post-preregistration (anti-curve-fit guarantee)."
    )


def test_frozen_stoch_overbought():
    """STOCH_OVERBOUGHT must be 80 — frozen by PREREGISTRATION.md §18."""
    assert STOCH_OVERBOUGHT == 80.0, (
        f"STOCH_OVERBOUGHT was changed to {STOCH_OVERBOUGHT}; "
        "thresholds are frozen post-preregistration (anti-curve-fit guarantee)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# (a) All 6 states — concrete inputs that should unambiguously classify
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_capitulation():
    """Rule 1: sign<0, k<20 => capitulation, not ambiguous."""
    result = classify(
        mmacd_sign=-1.0,
        mmacd_slope=0.1,    # slope doesn't matter for this rule
        mstoch_k=15.0,      # < 20
        mstoch_d=18.0,
    )
    assert result.state == "capitulation"
    assert result.ambiguous is False


def test_classify_basing():
    """Rule 2: sign<0, slope>0, k>=20 => basing, not ambiguous."""
    result = classify(
        mmacd_sign=-1.0,
        mmacd_slope=0.2,    # positive slope
        mstoch_k=35.0,      # >= 20 (not oversold)
        mstoch_d=30.0,
    )
    assert result.state == "basing"
    assert result.ambiguous is False


def test_classify_early_expansion():
    """Rule 3: sign>0, k<80, k>d => early_expansion, not ambiguous."""
    result = classify(
        mmacd_sign=1.0,
        mmacd_slope=0.1,
        mstoch_k=60.0,      # < 80
        mstoch_d=55.0,      # k > d
    )
    assert result.state == "early_expansion"
    assert result.ambiguous is False


def test_classify_late_expansion():
    """Rule 4: sign>0, k>=80 => late_expansion, not ambiguous."""
    result = classify(
        mmacd_sign=1.0,
        mmacd_slope=0.1,
        mstoch_k=85.0,      # >= 80
        mstoch_d=70.0,
    )
    assert result.state == "late_expansion"
    assert result.ambiguous is False


def test_classify_rolling_over():
    """Rule 5: sign>0, slope<=0, k<=d => rolling_over, not ambiguous."""
    result = classify(
        mmacd_sign=1.0,
        mmacd_slope=-0.1,   # falling slope
        mstoch_k=55.0,
        mstoch_d=60.0,      # k < d (not k>d)
    )
    assert result.state == "rolling_over"
    assert result.ambiguous is False


def test_classify_early_contraction():
    """Rule 6: sign<0, slope<=0 => early_contraction, not ambiguous."""
    result = classify(
        mmacd_sign=-1.0,
        mmacd_slope=-0.1,   # falling slope
        mstoch_k=45.0,      # >= 20 (not capitulation)
        mstoch_d=50.0,
    )
    assert result.state == "early_contraction"
    assert result.ambiguous is False


# ─────────────────────────────────────────────────────────────────────────────
# (b) Fall-through: bars not matched by any rule => ambiguous=True
# ─────────────────────────────────────────────────────────────────────────────

def test_fallthrough_bull_sign_positive_ambiguous():
    """sign>0, k<80, k<d (not k>d), slope>0 — falls through to early_expansion, ambiguous."""
    # Rule 3 requires k > d. If k <= d AND sign>0 AND k<80, none of rules 3-6 match
    # unless slope<=0 (rule 5). When slope>0 and k<=d and sign>0 and k<80: fall-through.
    result = classify(
        mmacd_sign=1.0,
        mmacd_slope=0.5,    # positive slope (rules out rule 5)
        mstoch_k=60.0,      # < 80 (rules out rule 4)
        mstoch_d=65.0,      # k < d (rules out rule 3)
    )
    assert result.state == "early_expansion"
    assert result.ambiguous is True


def test_fallthrough_sign_negative_kge20_positive_slope_klt_d():
    """sign<0, slope>0, k<20 — wait, that's capitulation (rule 1 fires first)."""
    # Actually: sign<0, slope>0, k<20: rule 1 fires (k<20) => capitulation, not fall-through
    result = classify(
        mmacd_sign=-1.0,
        mmacd_slope=0.2,    # positive slope
        mstoch_k=10.0,      # < 20 => rule 1 fires
        mstoch_d=12.0,
    )
    assert result.state == "capitulation"
    assert result.ambiguous is False


# ─────────────────────────────────────────────────────────────────────────────
# (c) NaN inputs => unknown, ambiguous
# ─────────────────────────────────────────────────────────────────────────────

def test_nan_sign():
    result = classify(float("nan"), 0.1, 50.0, 45.0)
    assert result.state == UNKNOWN_STATE
    assert result.ambiguous is True


def test_nan_slope():
    result = classify(1.0, float("nan"), 50.0, 45.0)
    assert result.state == UNKNOWN_STATE
    assert result.ambiguous is True


def test_nan_stoch_k():
    result = classify(1.0, 0.1, float("nan"), 45.0)
    assert result.state == UNKNOWN_STATE
    assert result.ambiguous is True


def test_nan_stoch_d():
    result = classify(1.0, 0.1, 50.0, float("nan"))
    assert result.state == UNKNOWN_STATE
    assert result.ambiguous is True


# ─────────────────────────────────────────────────────────────────────────────
# (d) sign=0 => falls through to early_contraction (ambiguous)
# ─────────────────────────────────────────────────────────────────────────────

def test_sign_zero_fallthrough():
    """mmacd_sign=0 means no bull momentum; falls to early_contraction, ambiguous."""
    result = classify(
        mmacd_sign=0.0,
        mmacd_slope=0.1,
        mstoch_k=50.0,
        mstoch_d=45.0,
    )
    # sign=0: not >0, not <0; none of the named rules match; fall-through to sign<=0 path
    assert result.state == "early_contraction"
    assert result.ambiguous is True


# ─────────────────────────────────────────────────────────────────────────────
# (e) Threshold boundary: k==20 does NOT fire capitulation (strictly k < 20)
# ─────────────────────────────────────────────────────────────────────────────

def test_stoch_k_exactly_20_not_capitulation():
    """k == STOCH_OVERSOLD (20) does NOT trigger capitulation (rule requires k < 20)."""
    result_at_20 = classify(
        mmacd_sign=-1.0,
        mmacd_slope=0.2,    # positive slope => basing rule applies if k >= 20
        mstoch_k=20.0,      # exactly at threshold
        mstoch_d=18.0,
    )
    # k=20 is NOT < 20, so rule 1 does not fire; rule 2 fires (sign<0, slope>0, k>=20)
    assert result_at_20.state == "basing"
    assert result_at_20.ambiguous is False

    # And k=19.9 DOES trigger capitulation
    result_below = classify(
        mmacd_sign=-1.0,
        mmacd_slope=0.2,
        mstoch_k=19.9,
        mstoch_d=18.0,
    )
    assert result_below.state == "capitulation"


# ─────────────────────────────────────────────────────────────────────────────
# (f) Threshold boundary: k==80 fires late_expansion (rule requires k >= 80)
# ─────────────────────────────────────────────────────────────────────────────

def test_stoch_k_exactly_80_fires_late_expansion():
    """k == STOCH_OVERBOUGHT (80) triggers late_expansion (rule requires k >= 80)."""
    result = classify(
        mmacd_sign=1.0,
        mmacd_slope=0.1,
        mstoch_k=80.0,      # exactly at threshold
        mstoch_d=75.0,
    )
    assert result.state == "late_expansion"
    assert result.ambiguous is False

    # k=79.9 is < 80, so rule 4 does not fire; rule 3 or rule 5 applies
    result_below = classify(
        mmacd_sign=1.0,
        mmacd_slope=0.1,
        mstoch_k=79.9,
        mstoch_d=75.0,      # k > d => rule 3
    )
    assert result_below.state == "early_expansion"


# ─────────────────────────────────────────────────────────────────────────────
# (h) classify_array determinism
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_array_deterministic():
    """Two calls to classify_array with identical inputs produce identical outputs."""
    rng = np.random.default_rng(42)
    n = 50
    signs = rng.choice([-1.0, 0.0, 1.0], size=n)
    slopes = rng.uniform(-1.0, 1.0, size=n)
    k_vals = rng.uniform(0.0, 100.0, size=n)
    d_vals = rng.uniform(0.0, 100.0, size=n)

    out1 = classify_array(signs, slopes, k_vals, d_vals)
    out2 = classify_array(signs, slopes, k_vals, d_vals)
    np.testing.assert_array_equal(out1, out2)


def test_classify_array_all_states_covered():
    """classify_array produces all 6 valid states given canonical inputs."""
    signs = np.array([-1.0, -1.0, 1.0, 1.0, 1.0, -1.0])
    slopes = np.array([0.1, 0.2, 0.1, 0.1, -0.1, -0.1])
    k_vals = np.array([10.0, 35.0, 60.0, 85.0, 55.0, 45.0])
    d_vals = np.array([12.0, 30.0, 55.0, 70.0, 60.0, 50.0])

    out = classify_array(signs, slopes, k_vals, d_vals)
    assert set(out) == set(VALID_STATES), f"Missing states: {set(VALID_STATES) - set(out)}"


def test_classify_array_osc_missing_yields_unknown():
    """Rows with osc_missing=True always yield 'unknown'."""
    signs = np.array([1.0, -1.0, 1.0])
    slopes = np.array([0.1, -0.1, 0.1])
    k_vals = np.array([60.0, 45.0, 85.0])
    d_vals = np.array([55.0, 50.0, 70.0])
    osc_missing = np.array([True, False, True])

    out = classify_array(signs, slopes, k_vals, d_vals, osc_missing)
    assert out[0] == UNKNOWN_STATE
    assert out[1] != UNKNOWN_STATE   # should classify
    assert out[2] == UNKNOWN_STATE


# ─────────────────────────────────────────────────────────────────────────────
# (i) Table builder determinism — data-guarded
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not (_PANEL_EXISTS and _STATE_EXISTS),
    reason="hazard panel or state_monthly not on disk (CI data-guarded)",
)
def test_phase_clock_table_deterministic():
    """Two calls to build_survival_table produce frame-equal output."""
    import scripts.build_phase_clock_table as tbl_mod

    panel = tbl_mod.build_merged_panel()
    run1 = tbl_mod.build_survival_table(panel)
    run2 = tbl_mod.build_survival_table(panel)
    pd.testing.assert_frame_equal(run1, run2, check_like=False)


# ─────────────────────────────────────────────────────────────────────────────
# (j) Survival table schema — if the file is on disk
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not _SURVIVAL_TABLE.exists(),
    reason="phase_clock_survival.parquet not on disk",
)
def test_survival_table_schema():
    """Survival table has expected columns and non-negative values."""
    df = pd.read_parquet(_SURVIVAL_TABLE)
    required_cols = [
        "family", "direction", "phase_state", "age_bucket", "pooling",
        "n_obs", "n_turns", "p25_m", "p50_m", "p75_m",
        "p_turn_3m", "p_turn_6m", "p_turn_12m",
    ]
    for col in required_cols:
        assert col in df.columns, f"Missing column: {col}"

    assert (df["n_obs"] >= 0).all(), "n_obs must be non-negative"
    assert (df["n_turns"] >= 0).all(), "n_turns must be non-negative"
    # Turn probabilities must be in [0, 1]
    for col in ("p_turn_3m", "p_turn_6m", "p_turn_12m"):
        valid = df[col].notna()
        assert ((df.loc[valid, col] >= 0) & (df.loc[valid, col] <= 1)).all(), (
            f"{col} out of [0, 1] range"
        )
    # phase_state values must be in VALID_STATES
    valid_states = set(VALID_STATES)
    actual_states = set(df["phase_state"].unique())
    assert actual_states.issubset(valid_states), (
        f"Unknown phase states in table: {actual_states - valid_states}"
    )
    # age_bucket values
    valid_buckets = {"0-6m", "6-18m", "18+m"}
    actual_buckets = set(df["age_bucket"].unique())
    assert actual_buckets.issubset(valid_buckets), (
        f"Unknown age buckets: {actual_buckets - valid_buckets}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# (k) Table builder smoke mode — no writes
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not (_PANEL_EXISTS and _STATE_EXISTS),
    reason="data not on disk",
)
def test_phase_clock_table_smoke_no_writes(tmp_path: Path):
    """--smoke mode completes without writing any files to OUTPUT_PATH."""
    import scripts.build_phase_clock_table as tbl_mod

    # Override output path to tmp so real artifact is never touched
    orig = tbl_mod.OUTPUT_PATH
    tbl_mod.OUTPUT_PATH = tmp_path / "phase_clock_survival.parquet"
    try:
        tbl_mod.main(smoke=True)
        assert not tbl_mod.OUTPUT_PATH.exists(), "smoke mode must not write the output file"
    finally:
        tbl_mod.OUTPUT_PATH = orig
