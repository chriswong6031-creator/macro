"""Live Entry Radar PR-3 (W3) — the detector registry.

WHAT THIS PINS
--------------
Five challengers acquire real specs at W3 and ``F1_FUSION`` does not.  Three
properties keep that honest:

**Identity is frozen.**  Each ``spec_hash`` is pinned as a literal, so a spec
edit breaks this file on purpose — a detector whose constants moved silently is a
detector whose past results are no longer attributable to it.

**The hash covers EVERYTHING that decides a fire (PIT-19).**  Mutating any single
key of any spec block must move its hash.  Written as a mutation sweep rather than
an assertion about the current value, because the failure it guards is a future
``spec_hash`` computed over a convenient SUBSET — which would pass every
equality test in this file while making the identity meaningless.

**The registry cannot drift from the code (registry-vs-implementation).**  Each
registered hash IS the implementing module's own ``*_spec_hash()``, and the check
iterates the REGISTRY so a detector added without wiring its hash fails loudly.

Nothing here reads ``data/``, ``site/`` or the network.
"""
from __future__ import annotations

import copy

import pytest

from engine.entry_radar.c5_adapter import C5_DETECTOR_ID, C5_SPEC, c5_spec_hash
from engine.entry_radar.challengers import (
    C1_DETECTOR_ID,
    C1_SPEC,
    C2_DETECTOR_ID,
    C2_PRIMARY_VARIANT,
    C2_SPEC,
    C2_VARIANTS,
    C4_DETECTOR_ID,
    C4_SPEC,
    c1_spec_hash,
    c2_spec_hash,
    c4_spec_hash,
)
from engine.entry_radar.detectors import (
    DETECTORS,
    RESERVED_DETECTOR_IDS,
    STRATIFICATION_ONLY,
    DetectorError,
    DetectorSpec,
    NotYetSpecified,
    assert_registry_matches_implementations,
    get_spec,
)
from engine.entry_radar.entry_events import (
    RADAR_1D_TURN_SUBTYPES,
    RADAR_NATIVE_SUBTYPES,
    sha16,
)
from engine.entry_radar.four_hour import C3_DETECTOR_ID, C3_SPEC, c3_spec_hash
from engine.entry_radar.g0_adapter import G0_DETECTOR_ID, g0_spec_hash

#: FROZEN literals.  Editing any value inside a spec block changes these and
#: breaks this test ON PURPOSE (the W2 precedent, `test_entry_radar_w2_guards.py`).
FROZEN_SPEC_HASHES = {
    "G0_GREY_DOT@1": "9be89a8acc8b905c",
    # TRUTH CHANGE, 2026-08-14 adversarial review: W3-4 moved four firing-relevant
    # constants INTO the spec blocks by value (ATR window, minute-knowability
    # offset, the three §10 re-arm numbers), W3-2 added C3's arm-expiry constant,
    # and W3-1/W3-5/W3-13 stated the basis, freshness and non-positive-ATR
    # refusals.  Those are spec CHANGES, so the hashes move — which is the
    # mechanism working, not a golden regenerated to hide a failure.  Lawful
    # because no result has ever been attributed to the old values: nothing has
    # shipped from this branch.
    "C1_1D_LIVE_WASHOUT@1": "f0bbd6cf3a6e2339",
    "C2_1D_TURN@1": "d8ba60a25cfa7400",
    "C3_1D_4H_RECOVERY@1": "d54dc1e55c4261c8",
    "C4_MTF_TURN@1": "dce21ac680233ee2",
    "C5_BOTTOM_WATCH@1": "13dec66345a0376c",
}

SPEC_BLOCKS = {
    C1_DETECTOR_ID: C1_SPEC,
    C2_DETECTOR_ID: C2_SPEC,
    C3_DETECTOR_ID: C3_SPEC,
    C4_DETECTOR_ID: C4_SPEC,
    C5_DETECTOR_ID: C5_SPEC,
}

IMPLEMENTATION_HASHES = {
    G0_DETECTOR_ID: g0_spec_hash,
    C1_DETECTOR_ID: c1_spec_hash,
    C2_DETECTOR_ID: c2_spec_hash,
    C3_DETECTOR_ID: c3_spec_hash,
    C4_DETECTOR_ID: c4_spec_hash,
    C5_DETECTOR_ID: c5_spec_hash,
}

#: The §18 A5 material each spec MUST name.  Without this a spec could keep a
#: stable hash while quietly dropping the constant the amendment turns on — the
#: hash would still be "sensitive to every key it has", just not to the one that
#: left.
REQUIRED_SPEC_KEYS = {
    C1_DETECTOR_ID: ("arm_condition", "oversold_threshold", "promotion_rule",
                     "candidates_per_episode", "depth_requirement", "sampling_law",
                     "interval_minutes", "minute_knowability",
                     "provisional_close_rule", "confirmed_history", "indicator_core",
                     # W3-4 / W3-1 / W3-5
                     "minute_bar_seconds", "rearm_law", "price_basis_law",
                     "freshness_law"),
    C2_DETECTOR_ID: ("variants", "variant_count", "primary_variant",
                     "combination_rule", "rebound_atr_multiple", "rebound_low_law",
                     "atr_law", "basis_law", "eligibility",
                     "current_oversold_requirement", "pre_arm_rule", "indicator_core",
                     # W3-4 / W3-8 / W3-1 / W3-5
                     "sampling", "pre_arm_encoding", "price_basis_law",
                     "freshness_law"),
    C3_DETECTOR_ID: ("daily_condition", "daily_knowability", "arm_rule", "turn_rule",
                     "turn_primitive", "grid_anchor", "grid_nominal_minutes",
                     "grid_key", "grid_effective_end", "grid_early_close",
                     "bucket_confirmation", "partial_bucket", "warm_up",
                     "extended_hours", "indicator_core",
                     # W3-2 / W3-5 / W3-11
                     "arm_expiry_sessions", "arm_expiry_rule", "freshness_law",
                     "empty_bucket_law"),
    C4_DETECTOR_ID: ("role", "can_fire", "firing_fence", "base_population", "anchor",
                     "anchor_era", "anchor_rejected", "grains", "turn_primitive",
                     "recent_os", "recent_os_window", "recovery_count",
                     "confirmed_bar_law", "indicator_core"),
    C5_DETECTOR_ID: ("upstream_pin", "constants", "formula_drawdown",
                     "formula_monthly_dwell", "formula_recent_os", "formula_washed",
                     "formula_blocked_trigger", "candidate_population", "precedence",
                     "knowability", "mutation_law"),
}


def _mutate(value):
    """One minimal, type-appropriate change to a spec value."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + " (mutated)"
    if isinstance(value, list):
        return list(value) + ["mutated"]
    if isinstance(value, dict):
        return {**value, "__mutated__": True}
    return "mutated"


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def test_the_six_detectors_are_registered_and_f1_is_not():
    assert sorted(DETECTORS) == sorted(FROZEN_SPEC_HASHES)
    assert "F1_FUSION" not in DETECTORS


@pytest.mark.parametrize("detector_id", sorted(FROZEN_SPEC_HASHES))
def test_spec_hash_is_frozen_and_stable_within_a_run(detector_id):
    record = DETECTORS[detector_id]
    assert record.spec_hash == FROZEN_SPEC_HASHES[detector_id]
    assert record.spec_hash == record.spec_hash, "hash must not vary within a run"


@pytest.mark.parametrize("detector_id", sorted(IMPLEMENTATION_HASHES))
def test_registry_hash_is_the_implementation_hash(detector_id):
    """The registry may not become a second source of truth for an identity."""
    assert DETECTORS[detector_id].spec_hash == IMPLEMENTATION_HASHES[detector_id]()


def test_registry_implementation_check_iterates_the_registry():
    assert_registry_matches_implementations()


def test_MUTATION_a_registered_detector_with_no_implementation_hash_is_caught():
    """Control for the check above: it must fail on the gap it exists to find."""
    from engine.entry_radar import detectors as module

    original = dict(module.IMPLEMENTATION_HASHES)
    try:
        module.IMPLEMENTATION_HASHES.pop(C4_DETECTOR_ID)
        with pytest.raises(DetectorError, match="names no implementing"):
            module.assert_registry_matches_implementations()
    finally:
        module.IMPLEMENTATION_HASHES.clear()
        module.IMPLEMENTATION_HASHES.update(original)
    assert_registry_matches_implementations()


# ---------------------------------------------------------------------------
# PIT-19 — the hash covers every firing-relevant key
# ---------------------------------------------------------------------------

def _spec_key_cases():
    for detector_id, spec in sorted(SPEC_BLOCKS.items()):
        for key in sorted(spec):
            yield pytest.param(detector_id, key, id=f"{detector_id}:{key}")


@pytest.mark.parametrize("detector_id,key", list(_spec_key_cases()))
def test_PIT19_changing_any_single_spec_key_moves_the_spec_hash(detector_id, key):
    """Every key in every spec block is load-bearing for the identity.

    A ``spec_hash`` that ignored a key would let that constant change without the
    detector's identity changing — and every result attributed to the old hash
    would silently absorb the new behaviour.
    """
    spec = SPEC_BLOCKS[detector_id]
    baseline = sha16(spec)
    mutated = copy.deepcopy(spec)
    mutated[key] = _mutate(mutated[key])
    assert sha16(mutated) != baseline, f"{detector_id}.{key} does not reach the hash"
    record = DETECTORS[detector_id]
    moved = DetectorSpec(detector_id=record.detector_id, version=record.version,
                         grain=record.grain, bar_family=record.bar_family,
                         spec=mutated)
    assert moved.spec_hash != record.spec_hash


@pytest.mark.parametrize("detector_id", sorted(SPEC_BLOCKS))
def test_PIT19_adding_a_key_moves_the_hash_and_key_order_does_not(detector_id):
    spec = SPEC_BLOCKS[detector_id]
    assert sha16({**spec, "__new__": 1}) != sha16(spec)
    reordered = {k: spec[k] for k in reversed(list(spec))}
    assert sha16(reordered) == sha16(spec), "canonical JSON must sort keys"


@pytest.mark.parametrize("detector_id,keys", sorted(REQUIRED_SPEC_KEYS.items()))
def test_spec_blocks_name_the_A5_material(detector_id, keys):
    """A stable hash over a spec that DROPPED a constant is still a wrong identity."""
    missing = [k for k in keys if k not in SPEC_BLOCKS[detector_id]]
    assert missing == [], f"{detector_id} spec is missing {missing}"


# ---------------------------------------------------------------------------
# PIT-20 — F1 stays unspecified
# ---------------------------------------------------------------------------

def test_PIT20_f1_fusion_is_the_only_reserved_id_and_refuses_a_spec():
    assert RESERVED_DETECTOR_IDS == ("F1_FUSION",)
    with pytest.raises(NotYetSpecified, match="F1 is NOT in"):
        get_spec("F1_FUSION")


def test_PIT20_an_unknown_detector_is_a_different_refusal_from_a_reserved_one():
    with pytest.raises(DetectorError) as unknown:
        get_spec("C9_NOT_A_DETECTOR")
    assert "unknown detector_id" in str(unknown.value)
    assert not isinstance(unknown.value, NotYetSpecified)


def test_a_spec_with_no_constants_is_refused_outright():
    with pytest.raises(DetectorError, match="must be RESERVED"):
        DetectorSpec(detector_id="C9_EMPTY", version=1, grain="x", bar_family="y",
                     spec={})


# ---------------------------------------------------------------------------
# the six C2 variants have exactly one source
# ---------------------------------------------------------------------------

def test_the_c2_variant_enum_has_one_source_and_six_members():
    assert C2_VARIANTS == RADAR_1D_TURN_SUBTYPES
    assert len(C2_VARIANTS) == 6
    assert set(C2_SPEC["variants"]) == set(C2_VARIANTS)
    assert C2_SPEC["variant_count"] == 6
    assert C2_SPEC["primary_variant"] == C2_PRIMARY_VARIANT == "c2a_kd_cross"
    assert set(RADAR_NATIVE_SUBTYPES["radar_1d_turn"]) == set(C2_VARIANTS)


def test_c4_is_registered_stratification_only_and_declares_it_cannot_fire():
    assert STRATIFICATION_ONLY == (C4_DETECTOR_ID,)
    assert DETECTORS[C4_DETECTOR_ID].spec["role"] == "stratification_only"
    assert DETECTORS[C4_DETECTOR_ID].spec["can_fire"] is False
    assert "radar_mtf_turn" not in RADAR_NATIVE_SUBTYPES
    assert len(RADAR_NATIVE_SUBTYPES) == 3


# ---------------------------------------------------------------------------
# 2026-08-14 adversarial-review regressions (W3-10, W3-13)
# ---------------------------------------------------------------------------

def test_W3_13_the_c2f_spec_states_the_non_positive_ATR_refusal():
    """W3-13: the guard was implemented and unstated.  A spec that omits a
    refusal the code performs is a spec a reader cannot reason from — and the
    omission is invisible, because the hash covers what IS written.
    """
    formula = C2_SPEC["variants"]["c2f_rebound_atr"]
    assert "non-positive" in formula and "unavailable" in formula
    assert "never a trivial pass" in formula


def test_W3_10_the_run_helpers_state_that_their_episodes_are_not_a_ledger():
    """W3-10 (docstring-only ruling): a per-path trace is not a §10 ledger, and
    the §10 clocks belong to PR-4/PR-5.  Pinned so the statement cannot quietly
    disappear and leave a reader assuming the ledger is here.
    """
    from engine.entry_radar import challengers as ch

    for func in (ch.run_c1, ch.run_c2):
        doc = func.__doc__ or ""
        assert "NOT" in doc or "not a" in doc.lower()
        assert "PR-4" in doc or "PR-5" in doc
    assert "rearm_eligible" in (ch.run_c1.__doc__ or "")
    assert callable(ch.rearm_eligible)
