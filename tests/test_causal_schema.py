"""tests/test_causal_schema.py — Hermetic tests for engine.neuralweb.causal_schema.

Covers:
- Card validation: missing falsifiers (<2) rejected; frozen env-map hash tamper
  detected; banned words sanitized; min_n clamped; exit-a card with unknown
  claim_shape rejected; LLM actor transition raises (CHF-R17); status machine
  legal/illegal paths.
- Instrument validator: missing exogeneity_class / missing confounds.
"""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from engine.neuralweb.causal_schema import (
    ALLOWED_ACTORS,
    AUTHORITY_BLOCK,
    MIN_N_FLOOR,
    SCHEMA,
    VALID_FAMILIES,
    VALID_STATUSES,
    IllegalTransition,
    _compute_env_hash,
    _contains_banned,
    _sanitize_text,
    canonical_card,
    load_instruments,
    sanitize_card,
    transition_card,
    validate_card,
    validate_instruments,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _env_map(hold=None, break_=None):
    """Build an environment_map with a correct frozen_hash."""
    em = {
        "should_hold": hold or ["risk_on", "bull_trend"],
        "should_break": break_ or ["risk_off", "crisis"],
    }
    em["frozen_hash"] = _compute_env_hash(em)
    return em


def _valid_card(**overrides) -> dict:
    """Return a minimal valid mechanism card."""
    base = {
        "mechanism_id": "test-lead-lag-001",
        "family": "macro_transmission",
        "claim_en": "When liquidity expands, equities tend to follow within 10 days.",
        "claim_zh": "当流动性扩张时，股票倾向于在10天内跟随。",
        "causal_graph": {
            "cause": "fed_balance_sheet_growth",
            "target": "equity_breadth_index",
            "mediators": ["risk_premium_compression"],
            "confounders": ["growth_surprise"],
            "colliders_to_avoid": ["realized_vol"],
        },
        "environment_map": _env_map(),
        "falsifiers": [
            "If lagged-placebo equity_breadth_index predicts fed_balance_sheet_growth, reverse causation explains the signal.",
            "If the relationship disappears in risk-off regimes where the mechanism should hold, the mechanism is refuted.",
        ],
        "test_spec": {
            "exit_path": "a",
            "claim_shape": "lead_lag",
            "horizon_d": 21,
            "metric": "forward_breadth_21d",
            "threshold": 0.55,
            "min_n": 50,
            "environment": "risk_on",
        },
        "lineage": {
            "source": "llm_proposed",
            "pack_id": "pack-2026-07-09-001",
            "model": "gpt-4o",
        },
        "status": "inbox",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# validate_card — valid card passes
# ---------------------------------------------------------------------------

def test_valid_card_passes():
    card = _valid_card()
    errors = validate_card(card)
    assert errors == [], f"Expected no errors, got: {errors}"


# ---------------------------------------------------------------------------
# validate_card — missing required fields
# ---------------------------------------------------------------------------

def test_missing_required_field_mechanism_id():
    card = _valid_card()
    del card["mechanism_id"]
    errors = validate_card(card)
    assert any("mechanism_id" in e for e in errors)


def test_missing_required_field_falsifiers():
    card = _valid_card()
    del card["falsifiers"]
    errors = validate_card(card)
    assert any("falsifiers" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_card — falsifiers < 2 rejected
# ---------------------------------------------------------------------------

def test_too_few_falsifiers_rejected():
    card = _valid_card(falsifiers=["Only one falsifier."])
    errors = validate_card(card)
    assert any("falsifiers" in e and "at least" in e for e in errors), f"errors={errors}"


def test_zero_falsifiers_rejected():
    card = _valid_card(falsifiers=[])
    errors = validate_card(card)
    assert any("falsifiers" in e for e in errors)


def test_two_falsifiers_accepted():
    card = _valid_card()
    errors = validate_card(card)
    assert errors == []


# ---------------------------------------------------------------------------
# validate_card — frozen env-map hash tamper detection
# ---------------------------------------------------------------------------

def test_frozen_hash_correct_passes():
    card = _valid_card()
    assert card["environment_map"]["frozen_hash"]
    errors = validate_card(card)
    assert errors == []


def test_frozen_hash_tamper_detected():
    card = _valid_card()
    # Tamper: add a new condition without recomputing the hash
    card["environment_map"]["should_hold"].append("new_condition")
    errors = validate_card(card)
    assert any("frozen_hash" in e and "mismatch" in e for e in errors), f"errors={errors}"


def test_frozen_hash_missing_rejected():
    card = _valid_card()
    del card["environment_map"]["frozen_hash"]
    errors = validate_card(card)
    assert any("frozen_hash" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_card — banned words (RUL-CC-5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("banned_word,field", [
    ("caused", "claim_en"),
    ("proved", "claim_en"),
    ("proof", "claim_zh"),
    ("validated", "claim_en"),
])
def test_banned_word_rejected(banned_word, field):
    card = _valid_card()
    card[field] = f"The indicator {banned_word} the return."
    errors = validate_card(card)
    assert any(banned_word in e for e in errors), f"Expected {banned_word!r} error, got: {errors}"


def test_banned_word_in_falsifier_rejected():
    card = _valid_card(
        falsifiers=[
            "This is a valid falsifier.",
            "The mechanism validated by the lagged placebo test.",
        ]
    )
    errors = validate_card(card)
    assert any("validated" in e for e in errors)


# ---------------------------------------------------------------------------
# _sanitize_text — banned words replaced
# ---------------------------------------------------------------------------

def test_sanitize_caused():
    text = "The indicator caused the return."
    result = _sanitize_text(text)
    assert "caused" not in result.lower()
    assert "co-moved with" in result


def test_sanitize_proved():
    result = _sanitize_text("The data proved the hypothesis.")
    assert "proved" not in result.lower()
    assert "is consistent with" in result


def test_sanitize_proof():
    result = _sanitize_text("This is proof of the mechanism.")
    assert "proof" not in result.lower()
    assert "evidence" in result


def test_sanitize_validated():
    result = _sanitize_text("The signal has been validated.")
    assert "validated" not in result.lower()
    assert "tested" in result


def test_sanitize_card_cleans_all_fields():
    card = _valid_card(
        claim_en="The factor caused the outcome.",
        claim_zh="该因素validated了结果。",
        falsifiers=[
            "proof of mechanism exists here.",
            "This proved the null.",
        ],
    )
    cleaned = sanitize_card(card)
    assert "caused" not in cleaned["claim_en"].lower()
    assert "validated" not in cleaned["claim_zh"].lower()
    assert "proof" not in cleaned["falsifiers"][0].lower()
    assert "proved" not in cleaned["falsifiers"][1].lower()


# ---------------------------------------------------------------------------
# validate_card — min_n clamped check (the validator checks, ingest clamps)
# ---------------------------------------------------------------------------

def test_min_n_below_floor_fails_validation():
    card = _valid_card()
    card["test_spec"]["min_n"] = 10  # below floor of 25
    errors = validate_card(card)
    assert any("min_n" in e and "floor" in e for e in errors), f"errors={errors}"


def test_min_n_at_floor_passes():
    card = _valid_card()
    card["test_spec"]["min_n"] = MIN_N_FLOOR
    errors = validate_card(card)
    assert errors == []


def test_min_n_above_floor_passes():
    card = _valid_card()
    card["test_spec"]["min_n"] = 100
    errors = validate_card(card)
    assert errors == []


# ---------------------------------------------------------------------------
# validate_card — exit-a card with unknown claim_shape rejected
# ---------------------------------------------------------------------------

def test_exit_a_unknown_claim_shape_rejected():
    card = _valid_card()
    card["test_spec"]["exit_path"] = "a"
    card["test_spec"]["claim_shape"] = "unknown_shape_xyz"
    errors = validate_card(card)
    assert any("claim_shape" in e for e in errors), f"errors={errors}"


def test_exit_a_valid_claim_shape_passes():
    card = _valid_card()
    card["test_spec"]["exit_path"] = "a"
    card["test_spec"]["claim_shape"] = "lead_lag"
    errors = validate_card(card)
    assert errors == []


def test_exit_b_domain_harness_required():
    card = _valid_card()
    card["test_spec"]["exit_path"] = "b"
    del card["test_spec"]["claim_shape"]
    card["test_spec"]["domain_harness"] = "engine.causal_discovery.battery"
    errors = validate_card(card)
    assert errors == []


def test_exit_b_missing_domain_harness_rejected():
    card = _valid_card()
    card["test_spec"]["exit_path"] = "b"
    card["test_spec"].pop("domain_harness", None)
    # Remove claim_shape since it's exit-b
    card["test_spec"].pop("claim_shape", None)
    errors = validate_card(card)
    assert any("domain_harness" in e for e in errors), f"errors={errors}"


# ---------------------------------------------------------------------------
# Status machine (CHF-R17)
# ---------------------------------------------------------------------------

def test_llm_actor_transition_raises():
    """CHF-R17: actor='llm' attempting any transition must raise IllegalTransition."""
    card = _valid_card()
    with pytest.raises(IllegalTransition, match="llm"):
        transition_card(card, "deduped", "llm", "test reason")


def test_unlisted_actor_raises():
    """Any actor not in ALLOWED_ACTORS raises IllegalTransition."""
    card = _valid_card()
    with pytest.raises(IllegalTransition):
        transition_card(card, "deduped", "anthropic", "test reason")


def test_script_actor_legal_transition():
    """actor='script' can move inbox → deduped."""
    card = _valid_card()
    result = transition_card(card, "deduped", "script", "dedup pass")
    assert result["status"] == "deduped"


def test_operator_actor_legal_transition():
    """actor='operator' can move skeptic_passed → filed."""
    card = _valid_card(status="skeptic_passed")
    result = transition_card(card, "filed", "operator", "operator approval")
    assert result["status"] == "filed"


def test_fable_actor_legal_transition():
    """actor='fable' can move deduped → rejected."""
    card = _valid_card(status="deduped")
    result = transition_card(card, "rejected", "fable", "fable review reject")
    assert result["status"] == "rejected"


def test_illegal_status_transition_raises():
    """Cannot transition filed → inbox (not in allowed map)."""
    card = _valid_card(status="filed")
    with pytest.raises(IllegalTransition, match="not allowed"):
        transition_card(card, "inbox", "script", "test")


def test_terminal_status_raises():
    """rejected is terminal — no transitions out."""
    card = _valid_card(status="rejected")
    with pytest.raises(IllegalTransition, match="terminal"):
        transition_card(card, "inbox", "operator", "test")


def test_decayed_is_terminal():
    """decayed is terminal."""
    card = _valid_card(status="decayed")
    with pytest.raises(IllegalTransition, match="terminal"):
        transition_card(card, "inbox", "operator", "test")


def test_transition_records_lineage():
    """transition_card appends a lineage.transitions entry."""
    card = _valid_card()
    result = transition_card(card, "deduped", "script", "auto-dedup")
    transitions = result["lineage"].get("transitions", [])
    assert len(transitions) == 1
    assert transitions[0]["from"] == "inbox"
    assert transitions[0]["to"] == "deduped"
    assert transitions[0]["actor"] == "script"


def test_transition_does_not_mutate_original():
    """transition_card returns a new dict; original is unchanged."""
    card = _valid_card()
    _ = transition_card(card, "deduped", "script", "test")
    assert card["status"] == "inbox"


# ---------------------------------------------------------------------------
# Family validation
# ---------------------------------------------------------------------------

def test_invalid_family_rejected():
    card = _valid_card(family="unknown_family_xyz")
    errors = validate_card(card)
    assert any("family" in e for e in errors)


@pytest.mark.parametrize("family", sorted(VALID_FAMILIES))
def test_all_valid_families_pass(family):
    card = _valid_card(family=family)
    errors = validate_card(card)
    assert errors == [], f"family={family!r} failed: {errors}"


# ---------------------------------------------------------------------------
# lineage.source validation
# ---------------------------------------------------------------------------

def test_invalid_lineage_source_rejected():
    card = _valid_card()
    card["lineage"]["source"] = "ai_bot"
    errors = validate_card(card)
    assert any("lineage.source" in e for e in errors)


# ---------------------------------------------------------------------------
# canonical_card determinism
# ---------------------------------------------------------------------------

def test_canonical_card_deterministic():
    card = _valid_card()
    c1 = canonical_card(card)
    c2 = canonical_card(card)
    assert c1 == c2


def test_canonical_card_sort_keys():
    """canonical_card is stable even if dict key order differs."""
    card_a = _valid_card()
    card_b = {k: v for k, v in reversed(list(card_a.items()))}
    assert canonical_card(card_a) == canonical_card(card_b)


# ---------------------------------------------------------------------------
# _compute_env_hash stability
# ---------------------------------------------------------------------------

def test_env_hash_stable_across_list_order():
    """frozen_hash must be identical regardless of list insertion order."""
    em1 = {"should_hold": ["risk_on", "bull_trend"], "should_break": ["crisis", "risk_off"]}
    em2 = {"should_hold": ["bull_trend", "risk_on"], "should_break": ["risk_off", "crisis"]}
    assert _compute_env_hash(em1) == _compute_env_hash(em2)


def test_env_hash_changes_on_content_change():
    em1 = {"should_hold": ["risk_on"], "should_break": ["risk_off"]}
    em2 = {"should_hold": ["risk_on", "extra"], "should_break": ["risk_off"]}
    assert _compute_env_hash(em1) != _compute_env_hash(em2)


# ---------------------------------------------------------------------------
# AUTHORITY_BLOCK constants
# ---------------------------------------------------------------------------

def test_authority_block_not_a_signal():
    assert AUTHORITY_BLOCK["not_a_signal"] is True


def test_authority_block_all_gates_false():
    for key in ("may_rank", "may_gate", "may_size", "may_escalate"):
        assert AUTHORITY_BLOCK[key] is False, f"AUTHORITY_BLOCK[{key!r}] should be False"


def test_authority_block_forbidden_uses_complete():
    expected = {
        "ranking", "sizing", "alert_escalation", "claim_validation",
        "board_ordering", "mastermind_arming",
    }
    assert expected.issubset(set(AUTHORITY_BLOCK["forbidden_uses"]))


# ---------------------------------------------------------------------------
# Instrument validator
# ---------------------------------------------------------------------------

def _sample_instruments():
    return [
        {
            "instrument_id": "opex_calendar",
            "event_tape": "declared",
            "exogeneity_class": "timing_only",
            "required_confounds": [],
            "mechanism_families": ["entry_quality"],
            "notes": "Test entry.",
        },
        {
            "instrument_id": "fomc_decision",
            "event_tape": "declared",
            "exogeneity_class": "surprise_component",
            "required_confounds": ["anticipated_component", "futures_implied_path"],
            "mechanism_families": ["macro_transmission"],
            "notes": "Test entry.",
        },
        {
            "instrument_id": "china_rrr_moves",
            "event_tape": "declared",
            "exogeneity_class": "endogenous_reaction",
            "required_confounds": ["policy_reaction_function_state"],
            "mechanism_families": ["liquidity_transmission"],
            "notes": "Test entry.",
        },
    ]


def test_validate_instruments_all_valid():
    instruments = _sample_instruments()
    errors = validate_instruments(instruments)
    assert errors == [], f"Unexpected errors: {errors}"


def test_validate_instruments_missing_exogeneity_class():
    instruments = [
        {
            "instrument_id": "bad_instrument",
            "event_tape": "declared",
            "required_confounds": [],
            "mechanism_families": [],
            "notes": "Missing exogeneity_class.",
        }
    ]
    errors = validate_instruments(instruments)
    assert any("exogeneity_class" in e for e in errors), f"errors={errors}"


def test_validate_instruments_unknown_exogeneity_class():
    instruments = [
        {
            "instrument_id": "bad_class",
            "event_tape": "declared",
            "exogeneity_class": "maybe_exogenous",
            "required_confounds": [],
        }
    ]
    errors = validate_instruments(instruments)
    assert any("exogeneity_class" in e for e in errors)


def test_validate_instruments_surprise_component_missing_confounds():
    instruments = [
        {
            "instrument_id": "fomc_no_confounds",
            "event_tape": "declared",
            "exogeneity_class": "surprise_component",
            "required_confounds": [],  # should be non-empty
        }
    ]
    errors = validate_instruments(instruments)
    assert any("required_confounds" in e for e in errors), f"errors={errors}"


def test_validate_instruments_endogenous_reaction_missing_confounds():
    instruments = [
        {
            "instrument_id": "china_rrr_no_confounds",
            "event_tape": "declared",
            "exogeneity_class": "endogenous_reaction",
            "required_confounds": [],
        }
    ]
    errors = validate_instruments(instruments)
    assert any("required_confounds" in e for e in errors)


def test_validate_instruments_timing_only_empty_confounds_ok():
    instruments = [
        {
            "instrument_id": "opex",
            "event_tape": "declared",
            "exogeneity_class": "timing_only",
            "required_confounds": [],
        }
    ]
    errors = validate_instruments(instruments)
    assert errors == []


def test_load_instruments_absent_returns_empty(tmp_path):
    result = load_instruments(tmp_path)
    assert result == []
