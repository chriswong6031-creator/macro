"""Tests for bootstrap_effective_t (W5/N7) and the extended deflated_sharpe.

Covers:
  1. IID normal returns → t_eff ≈ t_raw (0.6–1.4 × ratio)
  2. AR(1) φ=0.9 returns → t_eff < 0.5 × t_raw (autocorrelation penalty visible)
  3. Golden regression: deflated_sharpe without t_eff reproduces pre-W5 output exactly
     (commodity/forex callers untouched)
  4. With t_eff=300 the DSR is strictly lower than the golden DSR for a positive-SR case
  5. _override_dof: registry list, legacy gate fallback, and disabled-gate path
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# path setup — make root importable the same way conftest / other tests do it
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.validation import bootstrap_effective_t, deflated_sharpe


# ---------------------------------------------------------------------------
# Helpers to avoid a literal n_trials= call tripping the ratchet.
# The ratchet only scans engine/ and scripts/ — tests/ is exempt — but we use
# TrialLedger.with_declared_budget() to stay clean and explicit.
# ---------------------------------------------------------------------------
def _led(n: int, fam: str = "test"):
    from engine.trial_ledger import TrialLedger
    return TrialLedger.with_declared_budget(n, fam)


# ---------------------------------------------------------------------------
# 1. IID normal returns — ratio should be in [0.6, 1.4]
# ---------------------------------------------------------------------------
def test_iid_normal_ratio_near_one():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.02, 1500))
    result = bootstrap_effective_t(r, block=21, B=2000, seed=7)
    assert result, "Expected non-empty result for n=1500 iid series"
    ratio = result["ratio"]
    assert 0.6 <= ratio <= 1.4, f"IID ratio {ratio:.3f} outside [0.6, 1.4]"
    assert result["t_raw"] == 1500
    assert 30 <= result["t_eff"] <= 1500


# ---------------------------------------------------------------------------
# 2. AR(1) φ=0.9 — strong autocorrelation → t_eff < 0.5 × t_raw
# ---------------------------------------------------------------------------
def test_ar1_high_autocorrelation_shrinks_t_eff():
    rng = np.random.default_rng(42)
    n = 2000
    phi = 0.9
    eps = rng.normal(0, 1, n)
    r = np.zeros(n)
    for i in range(1, n):
        r[i] = phi * r[i - 1] + eps[i]
    # Scale to daily-return-like magnitudes
    r = r * 0.01
    result = bootstrap_effective_t(pd.Series(r), block=21, B=2000, seed=7)
    assert result, "Expected non-empty result for n=2000 AR(1) series"
    assert result["t_eff"] < 0.5 * result["t_raw"], (
        f"AR(1) φ=0.9: t_eff={result['t_eff']} should be < 0.5 × t_raw={result['t_raw']}"
    )


# ---------------------------------------------------------------------------
# 3. Golden regression — no t_eff must reproduce pre-W5 output exactly
# Golden values captured by running deflated_sharpe BEFORE the W5 edit.
# ---------------------------------------------------------------------------
GOLDEN = {
    "dsr": 0.2366,
    "sr_daily": 0.05,
    "sr_annual": 0.79,
    "sr0_daily": 0.073003,
    "sr0_annual": 1.16,
    "n_trials": 50,
    "T": 1000,
    "skew": -0.5,
    "kurt": 5.0,
}


def test_deflated_sharpe_golden_regression_no_t_eff():
    """Without t_eff the function must be bit-for-bit identical to pre-W5."""
    result = deflated_sharpe(
        sr_daily=0.05, skew=-0.5, kurt=5.0, T=1000,
        ledger=_led(50, "test_golden_regression"),
        family="test_golden_regression",
    )
    assert result is not None
    # Verify no t_eff key injected when t_eff not passed
    assert "t_eff" not in result
    for key, expected in GOLDEN.items():
        assert result[key] == expected, (
            f"Golden mismatch on '{key}': got {result[key]!r}, expected {expected!r}"
        )


# ---------------------------------------------------------------------------
# 4. With t_eff=300 the DSR must be strictly lower than golden DSR
#    (positive SR case: shrinking T tightens the test statistic)
# ---------------------------------------------------------------------------
def test_deflated_sharpe_with_t_eff_lowers_dsr():
    result_teff = deflated_sharpe(
        sr_daily=0.05, skew=-0.5, kurt=5.0, T=1000,
        ledger=_led(50, "test_teff_lowers"),
        family="test_teff_lowers",
        t_eff=300,
    )
    assert result_teff is not None
    assert "t_eff" in result_teff, "Expected t_eff key in result when t_eff= passed"
    assert result_teff["t_eff"] == 300
    assert result_teff["T"] == 1000       # raw T preserved
    assert result_teff["dsr"] < GOLDEN["dsr"], (
        f"DSR with t_eff=300 ({result_teff['dsr']}) should be < golden DSR ({GOLDEN['dsr']})"
    )


# ---------------------------------------------------------------------------
# 5. Short series returns {} from bootstrap_effective_t
# ---------------------------------------------------------------------------
def test_bootstrap_effective_t_too_short():
    r = pd.Series(np.random.default_rng(0).normal(0, 0.01, 30))
    assert bootstrap_effective_t(r, block=21) == {}


# ---------------------------------------------------------------------------
# 6. _override_dof — registry list path, legacy fallback, disabled gate
# ---------------------------------------------------------------------------
def test_override_dof_registry_list():
    from scripts.calibrate_vector import _override_dof
    vcfg = {
        "overrides": [
            {"id": "midterm_blackout", "dof_cost": 3},
            {"id": "another_override", "dof_cost": 1},
        ]
    }
    result = _override_dof(vcfg)
    assert result == {"midterm_blackout": 3, "another_override": 1}


def test_override_dof_legacy_fallback_gate_enabled():
    from scripts.calibrate_vector import _override_dof
    vcfg = {
        "allocation": {
            "midterm_gate": {"enabled": True}
        }
    }
    result = _override_dof(vcfg)
    assert result == {"midterm_blackout": 3}


def test_override_dof_gate_disabled_no_registry():
    from scripts.calibrate_vector import _override_dof
    vcfg = {
        "allocation": {
            "midterm_gate": {"enabled": False}
        }
    }
    assert _override_dof(vcfg) == {}


def test_override_dof_empty_dict():
    from scripts.calibrate_vector import _override_dof
    assert _override_dof({}) == {}
