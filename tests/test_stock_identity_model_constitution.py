"""Stock Identity W3A — Channel-A model constitution (freeze §4.1b, plan Task 3B).

Prereg only — no fitting. What a reader should not have to take on trust:

1. The declared feature subset is a real subset of the W1 fingerprint columns.
2. The functional form is ``additive_monotone`` unless a real
   ``separately_preregistered_form_ref`` document is named.
3. ``count_p_eff`` implements the exact declared per-feature counting rule
   deterministically, and ``assert_capacity`` raises exactly at
   ``p_eff > floor(N_train_names / 10)`` and passes exactly at the boundary.
4. The module imports no fitting/estimation library and defines no fit entry point.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engine.stock_identity.model_constitution import (
    CapacityViolation,
    ChannelAConstitution,
    assert_capacity,
    count_p_eff,
    load_constitution,
)

ROOT = Path(__file__).resolve().parents[1]
CONSTITUTION_PATH = ROOT / "data" / "stock_identity" / "ruler" / "channel_a_constitution_v1.json"
MODULE_SRC = ROOT / "engine" / "stock_identity" / "model_constitution.py"
FINGERPRINT_PATH = ROOT / "data" / "stock_identity" / "fingerprints" / "pilot_fingerprint_v0.parquet"

_FORBIDDEN_IMPORTS = {
    "sklearn", "scipy.optimize", "statsmodels", "xgboost", "lightgbm", "torch",
    "tensorflow", "keras", "cvxpy",
}


def test_declared_feature_subset_is_subset_of_real_fingerprint_columns():
    constitution = load_constitution(CONSTITUTION_PATH)
    assert len(constitution.feature_subset) > 0
    if FINGERPRINT_PATH.exists():
        import pandas as pd
        cols = set(pd.read_parquet(FINGERPRINT_PATH, columns=None).columns)
        assert set(constitution.feature_subset) <= cols


def test_functional_form_is_additive_monotone_or_real_prereg_ref():
    constitution = load_constitution(CONSTITUTION_PATH)
    if constitution.functional_form != "additive_monotone":
        assert constitution.separately_preregistered_form_ref
    else:
        assert constitution.separately_preregistered_form_ref is None


def test_shipped_constitution_uses_additive_monotone_with_no_ref():
    constitution = load_constitution(CONSTITUTION_PATH)
    assert constitution.functional_form == "additive_monotone"
    assert constitution.separately_preregistered_form_ref is None


def test_count_p_eff_is_deterministic():
    constitution = load_constitution(CONSTITUTION_PATH)
    assert count_p_eff(constitution) == count_p_eff(constitution)
    assert count_p_eff(constitution) == sum(constitution.p_eff_terms.values())
    assert count_p_eff(constitution) > 0


def test_assert_capacity_passes_exactly_at_boundary():
    constitution = load_constitution(CONSTITUTION_PATH)
    p_eff = 5
    n_train_names = 50  # floor(50/10) == 5
    assert_capacity(p_eff, n_train_names, constitution)  # must not raise


def test_assert_capacity_raises_one_over_boundary():
    constitution = load_constitution(CONSTITUTION_PATH)
    p_eff = 6
    n_train_names = 50  # floor(50/10) == 5; 6 > 5
    with pytest.raises(CapacityViolation):
        assert_capacity(p_eff, n_train_names, constitution)


def test_assert_capacity_uses_exact_floor_law():
    constitution = load_constitution(CONSTITUTION_PATH)
    # floor(59/10) == 5, so p_eff=5 is still legal even though 59/10 == 5.9
    assert_capacity(5, 59, constitution)
    with pytest.raises(CapacityViolation):
        assert_capacity(6, 59, constitution)


def test_assert_capacity_reads_denominator_from_constitution_not_module_default():
    """A constitution declaring a non-default denominator must actually govern the
    boundary — assert_capacity must read constitution.capacity_denominator, never
    silently fall back to the module-level CAPACITY_DENOMINATOR constant."""
    from dataclasses import replace
    constitution = load_constitution(CONSTITUTION_PATH)
    narrow = replace(constitution, capacity_denominator=5)  # floor(50/5) == 10
    assert_capacity(10, 50, narrow)  # legal under denominator=5, illegal under 10
    with pytest.raises(CapacityViolation):
        assert_capacity(11, 50, narrow)


def test_count_p_eff_raises_on_terms_feature_mismatch():
    """A p_eff_terms map that drifts from the declared feature_subset (extra or
    missing feature) must raise rather than silently mis-count capacity."""
    from dataclasses import replace
    constitution = load_constitution(CONSTITUTION_PATH)
    missing_one = replace(
        constitution,
        p_eff_terms={k: v for i, (k, v) in enumerate(constitution.p_eff_terms.items()) if i > 0},
    )
    with pytest.raises(ValueError):
        count_p_eff(missing_one)

    extra = dict(constitution.p_eff_terms)
    extra["undeclared_feature"] = 1
    with_extra = replace(constitution, p_eff_terms=extra)
    with pytest.raises(ValueError):
        count_p_eff(with_extra)


def test_module_imports_no_fitting_library():
    tree = ast.parse(MODULE_SRC.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for forbidden in _FORBIDDEN_IMPORTS:
        assert not any(imp == forbidden or imp.startswith(forbidden + ".") for imp in imported), (
            f"{forbidden!r} must not be imported by model_constitution.py"
        )


def test_module_defines_no_fit_entry_point():
    tree = ast.parse(MODULE_SRC.read_text(encoding="utf-8"))
    fn_names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in fn_names:
        assert not name.lower().startswith("fit_"), f"fit entry point found: {name}"
        assert name.lower() != "fit"


def test_constitution_authority_all_false():
    constitution = load_constitution(CONSTITUTION_PATH)
    assert constitution.authority == {
        "can_rank": False, "can_size": False, "can_gate": False,
        "can_originate_signal": False, "can_escalate": False,
    }


def test_constitution_spec_hash_is_stable():
    a = load_constitution(CONSTITUTION_PATH)
    b = load_constitution(CONSTITUTION_PATH)
    assert a.spec_hash() == b.spec_hash()
    assert len(a.spec_hash()) == 64
