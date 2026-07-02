"""W1 N7 stats hardening tests — dual-track calibration artifacts.

Tests verify:
  1. calibration.json carries both `allocation` (gated) and `allocation_raw` blocks.
  2. multiple_testing_raw block exists and has valid DSR/verdict.
  3. trial_log.json carries n_trials_declared = n_trials_config + override dof.
  4. override dof > 0 (midterm_blackout dof_cost=3 is registered).
  5. dsr_effN sub-dict present in both multiple_testing tracks.
  6. allocation_raw Sharpe differs from gated Sharpe (override has real effect).

All tests skip cleanly if the data store is absent (CI without full data).

Run: python -m pytest tests/test_btc_vector_w1.py -q
     or  python -m pytest tests/ -k "vector or btc" -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CAL_PATH = Path("data/vector/calibration.json")
TRIAL_PATH = Path("data/vector/trial_log.json")


def _load_cal():
    if not CAL_PATH.exists():
        pytest.skip("data/vector/calibration.json not found — run calibrate_vector first")
    return json.loads(CAL_PATH.read_text())


def _load_trial():
    if not TRIAL_PATH.exists():
        pytest.skip("data/vector/trial_log.json not found — run calibrate_vector first")
    return json.loads(TRIAL_PATH.read_text())


# ---------------------------------------------------------------------------
# 1. calibration.json schema — dual allocation blocks
# ---------------------------------------------------------------------------
def test_calibration_has_gated_allocation_block():
    """allocation block (gated, back-compat) must be present with at least one variant."""
    cal = _load_cal()
    assert "allocation" in cal, "missing 'allocation' block"
    assert len(cal["allocation"]) > 0, "'allocation' block is empty"


def test_calibration_has_raw_allocation_block():
    """W1 N7: allocation_raw block (pure engine) must be present."""
    cal = _load_cal()
    assert "allocation_raw" in cal, (
        "missing 'allocation_raw' block — W1 N7 dual-track compute not wired"
    )
    assert len(cal["allocation_raw"]) > 0, "'allocation_raw' block is empty"


def test_raw_allocation_has_same_variants_as_gated():
    """Both blocks must have the same set of strategy variants."""
    cal = _load_cal()
    if "allocation_raw" not in cal:
        pytest.skip("allocation_raw not present")
    assert set(cal["allocation_raw"]) == set(cal["allocation"]), (
        f"variant mismatch: gated={set(cal['allocation'])} raw={set(cal['allocation_raw'])}"
    )


def test_raw_allocation_sharpe_differs_from_gated():
    """The gated and raw optimal Sharpe must differ (override has real effect).

    If they are identical, the raw series is not being computed separately —
    the dual-track wiring is broken.
    """
    cal = _load_cal()
    if "allocation_raw" not in cal or "optimal" not in cal.get("allocation_raw", {}):
        pytest.skip("allocation_raw/optimal not present")
    sh_gated = cal["allocation"]["optimal"]["sharpe"]
    sh_raw = cal["allocation_raw"]["optimal"]["sharpe"]
    # They should differ because the gated series has 0% during the 2026 midterm window,
    # which inflates its Sharpe relative to raw when the raw engine is non-zero in that window.
    # Use a tolerance loose enough for numerical noise but tight enough to catch no-op.
    assert abs(sh_gated - sh_raw) > 0.01, (
        f"gated Sharpe {sh_gated} == raw Sharpe {sh_raw}: dual-track may not be computing separately"
    )


# ---------------------------------------------------------------------------
# 2. multiple_testing_raw block
# ---------------------------------------------------------------------------
def test_multiple_testing_raw_block_exists():
    """W1 N7: multiple_testing_raw (DSR on raw series) must be present."""
    cal = _load_cal()
    assert "multiple_testing_raw" in cal, (
        "missing 'multiple_testing_raw' block — W1 N7 raw DSR not computed"
    )


def test_multiple_testing_raw_has_dsr():
    """multiple_testing_raw must carry a numeric DSR value."""
    cal = _load_cal()
    if "multiple_testing_raw" not in cal:
        pytest.skip("multiple_testing_raw not present")
    mt_raw = cal["multiple_testing_raw"]
    assert mt_raw.get("dsr") is not None, "multiple_testing_raw.dsr is None"
    assert 0.0 <= float(mt_raw["dsr"]) <= 1.0, f"DSR out of range: {mt_raw['dsr']}"


def test_multiple_testing_raw_has_verdict():
    """multiple_testing_raw must carry a verdict string."""
    cal = _load_cal()
    if "multiple_testing_raw" not in cal:
        pytest.skip("multiple_testing_raw not present")
    mt_raw = cal["multiple_testing_raw"]
    assert isinstance(mt_raw.get("verdict"), str) and len(mt_raw["verdict"]) > 0


# ---------------------------------------------------------------------------
# 3. dsr_effN sub-dict in both tracks
# ---------------------------------------------------------------------------
def test_multiple_testing_gated_has_dsr_effN():
    """W1 N7: multiple_testing must carry dsr_effN (autocorrelation-adjusted)."""
    cal = _load_cal()
    mt = cal.get("multiple_testing") or {}
    assert "dsr_effN" in mt, "missing dsr_effN in multiple_testing (gated)"


def test_multiple_testing_raw_has_dsr_effN():
    """W1 N7: multiple_testing_raw must carry dsr_effN."""
    cal = _load_cal()
    mt_raw = cal.get("multiple_testing_raw") or {}
    if not mt_raw:
        pytest.skip("multiple_testing_raw not present")
    assert "dsr_effN" in mt_raw, "missing dsr_effN in multiple_testing_raw"


def test_dsr_effN_has_required_keys():
    """dsr_effN sub-dict must have: dsr_effN, dsr_legacy, T_raw, T_eff, rho_sum_K20."""
    cal = _load_cal()
    mt = cal.get("multiple_testing") or {}
    effN = mt.get("dsr_effN") or {}
    if not effN:
        pytest.skip("dsr_effN not present")
    required = {"dsr_effN", "dsr_legacy", "T_raw", "T_eff", "rho_sum_K20"}
    missing = required - set(effN)
    assert not missing, f"dsr_effN missing keys: {missing}"


def test_T_eff_less_than_T_raw():
    """T_eff (autocorr-adjusted) should be less than T_raw for trend-following returns."""
    cal = _load_cal()
    effN = (cal.get("multiple_testing") or {}).get("dsr_effN") or {}
    if not effN or effN.get("T_eff") is None:
        pytest.skip("dsr_effN not populated")
    T_eff = float(effN["T_eff"])
    T_raw = float(effN["T_raw"])
    # BTC momentum returns have positive autocorrelation → T_eff < T_raw.
    # Allow small positive autocorr cases where T_eff ≈ T_raw.
    assert T_eff <= T_raw, f"T_eff {T_eff} > T_raw {T_raw}: unexpected negative autocorr sum"


# ---------------------------------------------------------------------------
# 4. trial_log.json — n_trials breakdown (reconciled W5 schema:
#    n_trials_config + overrides_dof{id: cost} -> n_trials_declared)
# ---------------------------------------------------------------------------
def test_trial_log_has_n_trials_breakdown():
    """N7: trial_log.json must carry n_trials_config, overrides_dof, n_trials_declared."""
    tl = _load_trial()
    for key in ("n_trials_config", "overrides_dof", "n_trials_declared"):
        assert key in tl, f"trial_log.json missing key: {key}"


def test_n_trials_declared_equals_config_plus_overrides():
    """n_trials_declared = n_trials_config + sum(overrides_dof.values())."""
    tl = _load_trial()
    if not all(k in tl for k in ("n_trials_config", "overrides_dof", "n_trials_declared")):
        pytest.skip("trial_log breakdown keys missing")
    assert tl["n_trials_declared"] == tl["n_trials_config"] + sum(tl["overrides_dof"].values()), (
        f"n_trials_declared {tl['n_trials_declared']} != config {tl['n_trials_config']} + "
        f"overrides {sum(tl['overrides_dof'].values())}"
    )


def test_overrides_dof_positive():
    """Override DOF must be > 0 (midterm_blackout dof_cost=3 is registered)."""
    tl = _load_trial()
    if "overrides_dof" not in tl:
        pytest.skip("overrides_dof not in trial_log")
    assert sum(tl["overrides_dof"].values()) > 0, (
        "overrides_dof sums to 0 — midterm_blackout dof_cost not being counted"
    )


def test_midterm_blackout_in_overrides_dof():
    """midterm_blackout must appear in the overrides_dof breakdown."""
    tl = _load_trial()
    if "overrides_dof" not in tl:
        pytest.skip("overrides_dof not in trial_log")
    assert "midterm_blackout" in tl["overrides_dof"], (
        f"midterm_blackout missing from overrides_dof: {list(tl['overrides_dof'])}"
    )



def test_midterm_blackout_dof_cost_is_3():
    """midterm_blackout dof_cost must be 3 (as declared in config.yml)."""
    tl = _load_trial()
    cost = tl.get("overrides_dof", {}).get("midterm_blackout")
    if cost is None:
        pytest.skip("midterm_blackout not in overrides_dof")
    assert cost == 3, f"midterm_blackout dof_cost={cost} (expected 3)"


# ---------------------------------------------------------------------------
# 5. Back-compat: existing allocation block schema unchanged
# ---------------------------------------------------------------------------
def test_gated_allocation_has_required_metrics():
    """Back-compat: the gated allocation block must still have all legacy fields."""
    cal = _load_cal()
    required = {"sharpe", "cagr", "maxdd", "time_in_market", "hodl_sharpe", "hodl_cagr",
                "hodl_maxdd", "total_return"}
    for variant, m in cal["allocation"].items():
        missing = required - set(m)
        assert not missing, f"allocation[{variant}] missing fields: {missing}"


if __name__ == "__main__":
    import sys as _sys
    # run all tests manually
    tests = [
        test_calibration_has_gated_allocation_block,
        test_calibration_has_raw_allocation_block,
        test_raw_allocation_has_same_variants_as_gated,
        test_raw_allocation_sharpe_differs_from_gated,
        test_multiple_testing_raw_block_exists,
        test_multiple_testing_raw_has_dsr,
        test_multiple_testing_raw_has_verdict,
        test_multiple_testing_gated_has_dsr_effN,
        test_multiple_testing_raw_has_dsr_effN,
        test_dsr_effN_has_required_keys,
        test_T_eff_less_than_T_raw,
        test_trial_log_has_n_trials_breakdown,
        test_n_trials_declared_equals_config_plus_overrides,
        test_overrides_dof_positive,
        test_midterm_blackout_in_overrides_dof,
        test_midterm_blackout_dof_cost_is_3,
        test_gated_allocation_has_required_metrics,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            if "skip" in str(type(exc).__name__).lower() or "skip" in str(exc).lower():
                print(f"SKIP {fn.__name__}: {exc}")
            else:
                print(f"FAIL {fn.__name__}: {exc}")
                failed += 1
    _sys.exit(failed)
