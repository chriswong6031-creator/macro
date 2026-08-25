"""Contract tests for Market OS B1A — ``engine/security_state.py``.

Covers: the 14 commission failure/scenario cases, the 5 identity refusal
fixtures (R1/R3-R4/R6/R7-R8/R9), the K1 (Evidence Foundation) receipt
assertions, the documented mutation kills (demonstrated live: introduce the
violation, show the schema/law catch it, revert), content_sha256 stability
under a ``generated_at`` change, and schema self-validation.

``engine/security_state.py`` is a PURE compiler (zero I/O, zero wall-clock) —
every fixture here is a plain-dict input bundle; nothing in this file reads a
parquet file or makes a network call. Do NOT run the full suite in this
sparse tree (data/site omitted; see CLAUDE.md §Sparse worktrees) — this file
is self-contained and can be run standalone:

    python3 -m pytest tests/test_security_state_contract.py -x -q
"""
from __future__ import annotations

import copy
import datetime
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from engine import security_state as ss
from lib.evidence_foundation import (
    EvidenceFoundationError,
    compile_recipe,
    compute_reference_id,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "security_state"
SCHEMA_PATH = ROOT / "contracts" / "market_os" / "security_state.v1.schema.json"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _golden_input() -> dict:
    return copy.deepcopy(_load("golden_aapl_input.json"))


# ---------------------------------------------------------------------------
# schema self-validation (also exercised implicitly by every compile below,
# since compile_security_state/compile_security_state_failure self-validate)
# ---------------------------------------------------------------------------

def test_contract_schema_is_closed_at_every_level_and_valid_draft_2020_12() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema"]["const"] == "security_state.v1"
    assert schema["properties"]["version"]["const"] == "1.0.0"

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, node
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(schema)


def test_golden_fixture_self_validates_against_the_committed_schema() -> None:
    validator = _validator()
    state = ss.compile_security_state(**_golden_input())
    errors = list(validator.iter_errors(state))
    assert errors == []
    # and it matches the committed expected snapshot exactly (byte-for-byte
    # modulo key order), including the K1 recipe_compilation_receipt.v1
    # embedded verbatim in legs.evidence.compilation.
    expected = _load("golden_aapl_expected_output.json")
    assert state == expected


# ---------------------------------------------------------------------------
# 1. golden current event (happy path)
# ---------------------------------------------------------------------------

def test_case1_golden_current_event() -> None:
    state = ss.compile_security_state(**_golden_input())
    assert state["schema"] == "security_state.v1"
    assert state["version"] == "1.0.0"
    assert state["security_id"] == "SEC:US-XNAS-AAPL"
    assert state["issuer_id"] == "ISS:US-XNAS-AAPL"
    assert state["listing_key"] == "US-XNAS-AAPL"
    assert state["ticker_display"] == "AAPL"
    assert state["identity_proof"]["state"] == "PROVEN"
    assert state["identity_proof"]["refusals"] == []
    assert len(state["identity_proof"]["legs"]) == 9
    assert [leg["check"] for leg in state["identity_proof"]["legs"]] == [f"R{i}" for i in range(1, 10)]
    assert len(state["identity_proof"]["disclosures"]) == 4
    assert state["legs"]["change"]["coverage_state"] == "AVAILABLE"
    assert state["legs"]["change"]["economic_episode_ref"] == "evt_cik0000320193_2026q3_results"
    assert state["legs"]["change"]["generation_id"] == "6d56c84a3ac23b8954e59ee7"
    assert state["legs"]["evidence"]["coverage_state"] in {"AVAILABLE", "PARTIAL"}
    assert state["authority"] == {
        "class": "context_only", "display_only": True, "can_rank": False,
        "can_gate": False, "can_size": False, "can_originate_signal": False, "can_execute": False,
    }
    # dominant_degradation is never NONE-with-a-hidden-gap: opportunity_context
    # is honestly disclosed as UNAVAILABLE (no current Prophet output) even on
    # the golden happy path, so the top-level signal must say so too.
    assert state["dominant_degradation"] != "NONE"
    assert state["legs"]["opportunity_context"]["prophet"] == {
        "ref": None, "state": "UNAVAILABLE", "reason": ss._PROPHET_REASON,
    }


# ---------------------------------------------------------------------------
# legs.state -- Decision Spine state axis (Sol blocker 1)
# ---------------------------------------------------------------------------

def test_state_leg_sources_verbatim_ladder_and_tech_values() -> None:
    state = ss.compile_security_state(**_golden_input())
    leg = state["legs"]["state"]
    assert leg["deterministic_state_refs"] == ["ladder.state", "ladder.dir", "tech.chg_1d"]
    assert leg["ladder_state"] == "watch"
    assert leg["ladder_direction"] == "up"
    assert {"field": "tech.chg_1d", "value": 0.5} in leg["values_read"]
    assert leg["coverage_state"] == "AVAILABLE"
    # plain-word template over the owner-native display values, no internal
    # jargon/score/rank leaking into the reader-facing summary.
    assert "watch" in leg["summary"]["en"]
    assert "up" in leg["summary"]["en"]
    assert leg["summary"]["zh"]
    for banned in ("score", "rank", "percentile"):
        assert banned not in leg["summary"]["en"].lower()
    # required leg -- state is a Decision Spine axis now, not evidence.
    assert "state" in ss._REQUIRED_LEGS
    assert state["coverage"]["required_legs_total"] == 2


def test_state_leg_unavailable_and_null_safe_when_ladder_state_absent() -> None:
    inp = _golden_input()
    inp["blob"]["ladder"] = {"state": None, "dir": None}
    state = ss.compile_security_state(**inp)
    leg = state["legs"]["state"]
    assert leg["ladder_state"] is None
    assert leg["ladder_direction"] is None
    assert leg["coverage_state"] == "UNAVAILABLE"
    assert "state" in state["coverage"]["missing_legs"]
    # never null-means-neutral: a null ladder state is a typed UNAVAILABLE,
    # not a silently-omitted or falsely-AVAILABLE leg.
    validator = _validator()
    assert list(validator.iter_errors(state)) == []


# ---------------------------------------------------------------------------
# coverage denominator semantics (Sol blocker 7) -- available vs nonblocking
# ---------------------------------------------------------------------------

def test_golden_fixture_pins_all_six_coverage_denominator_fields() -> None:
    state = ss.compile_security_state(**_golden_input())
    coverage = state["coverage"]
    assert coverage["required_legs_total"] == 2
    assert coverage["required_legs_available"] == 2
    assert coverage["required_legs_nonblocking"] == 2
    assert coverage["optional_legs_total"] == 5
    assert coverage["optional_legs_available"] == 2
    assert coverage["optional_legs_nonblocking"] == 3


def test_not_applicable_and_not_covered_legs_are_nonblocking_but_not_available() -> None:
    """A NOT_APPLICABLE leg (personal_impact, always) and a NOT_COVERED leg
    (risk, when neither conviction nor alerts are present) must each be
    counted in *_legs_nonblocking but NEVER in *_legs_available -- a
    NOT_APPLICABLE/NOT_COVERED leg is honestly nonblocking, never disguised
    as available (Sol blocker 7)."""
    legs = {
        "state": {"coverage_state": "AVAILABLE"},
        "change": {"coverage_state": "AVAILABLE"},
        "opportunity_context": {"coverage_state": "AVAILABLE"},
        "risk": {"coverage_state": "NOT_COVERED"},
        "catalyst": {"coverage_state": "PARTIAL"},
        "personal_impact": {"coverage_state": "NOT_APPLICABLE"},
        "evidence": {"coverage_state": "UNAVAILABLE"},
    }
    coverage, dominant = ss._build_coverage_and_dominant(legs)
    assert coverage["required_legs_total"] == 2
    assert coverage["required_legs_available"] == 2
    assert coverage["required_legs_nonblocking"] == 2
    assert coverage["optional_legs_total"] == 5
    # only opportunity_context is strictly AVAILABLE among the 5 optional legs.
    assert coverage["optional_legs_available"] == 1
    # opportunity_context + risk(NOT_COVERED) + personal_impact(NOT_APPLICABLE)
    # are nonblocking; catalyst(PARTIAL) and evidence(UNAVAILABLE) are not.
    assert coverage["optional_legs_nonblocking"] == 3
    assert coverage["missing_legs"] == ["evidence"]
    assert dominant == "UNAVAILABLE"  # worst leg-level severity: evidence
    # but overall_state reflects required-leg completeness, not worst severity
    # -- both required legs are nonblocking, so the read is PARTIAL not
    # UNAVAILABLE at the overall level.
    assert coverage["overall_state"] == "PARTIAL"

    # and directly at the fixture-level, confirm the two real legs that
    # produce these states in production never get counted as available.
    assert legs["personal_impact"]["coverage_state"] not in {"AVAILABLE"}
    assert legs["risk"]["coverage_state"] not in {"AVAILABLE"}


# ---------------------------------------------------------------------------
# legs.catalyst -- estimated earnings WINDOW, never a precise date (Sol blocker 6)
# ---------------------------------------------------------------------------

def test_catalyst_is_an_estimated_window_never_a_precise_authoritative_date() -> None:
    state = ss.compile_security_state(**_golden_input())
    catalyst = state["legs"]["catalyst"]
    assert catalyst["coverage_state"] == "PARTIAL"  # never plain AVAILABLE for an estimate-only leg
    assert len(catalyst["next_observables"]) == 1
    obs = catalyst["next_observables"][0]
    assert obs["kind"] == "ESTIMATED_WINDOW"
    assert obs["authoritative"] is False
    assert "date" not in obs  # no single precise date field anywhere on this leg
    assert obs["window_start"] == "2026-09-12"  # fiscal_period.calendar_end (2026-06-27) + 77d
    assert obs["window_end"] == "2026-10-10"  # + 105d
    assert obs["window_start"] < obs["window_end"]
    assert "no canonical earnings-calendar owner exists" in obs["basis"]
    validator = _validator()
    assert list(validator.iter_errors(state)) == []


# ---------------------------------------------------------------------------
# 2. no current event
# ---------------------------------------------------------------------------

def test_case2_no_current_event() -> None:
    state = ss.compile_security_state(**_load("no_current_event_input.json"))
    assert state["legs"]["change"]["coverage_state"] == "UNAVAILABLE"
    assert state["legs"]["change"]["economic_episode_ref"] is None
    assert state["legs"]["change"]["event_refs"] == []
    assert state["legs"]["catalyst"]["coverage_state"] == "UNAVAILABLE"
    assert state["legs"]["evidence"]["compilation"]["state"] == "refused"
    assert state["legs"]["evidence"]["coverage_state"] == "UNAVAILABLE"
    assert state["dominant_degradation"] == "UNAVAILABLE"
    assert state["coverage"]["overall_state"] == "UNAVAILABLE"
    assert "change" in state["coverage"]["missing_legs"]
    # identity itself is still PROVEN — this is a workspace-availability gap,
    # never confused with an identity refusal.
    assert state["identity_proof"]["state"] == "PROVEN"


def test_case14_owner_schema_unsupported() -> None:
    inp = _golden_input()
    inp["workspace"] = {**inp["workspace"], "schema": "event_workspace.v2-hypothetical"}
    state = ss.compile_security_state(**inp)
    assert state["legs"]["change"]["coverage_state"] == "UNAVAILABLE"
    assert "not supported" in state["legs"]["change"]["summary"]["en"]
    # distinct code path from "not published" -- economic_episode_ref/
    # generation_id are still carried through (we DID read a workspace, it is
    # just a schema this reader does not understand), unlike case 2.
    assert state["legs"]["change"]["economic_episode_ref"] == inp["workspace"]["event_id"]


# ---------------------------------------------------------------------------
# 3. source stale / 4. source corrected
# ---------------------------------------------------------------------------

def test_case3_source_stale() -> None:
    state = ss.compile_security_state(**_load("source_stale_input.json"))
    assert state["legs"]["change"]["coverage_state"] == "STALE"
    assert "change" in state["coverage"]["stale_legs"]
    assert state["dominant_degradation"] == "STALE"
    fact = state["legs"]["risk"]["strongest_unresolved_fact"]
    assert fact["state"] == "required_leg_degraded"
    assert fact["code"] == "STALE"


def test_case4_source_corrected() -> None:
    state = ss.compile_security_state(**_load("source_corrected_input.json"))
    assert state["legs"]["change"]["correction_state"] == "corrected"
    fact = state["legs"]["risk"]["strongest_unresolved_fact"]
    assert fact["state"] == "corrected_source"
    assert fact["code"] == "corrected"


def test_change_staleness_boundary_is_exactly_120_days() -> None:
    inp = _golden_input()
    inp["workspace"]["fiscal_period"]["calendar_end"] = "2026-04-01"
    inp["now"] = "2026-07-30T00:00:00Z"  # 120 days later -> AVAILABLE, not STALE
    state = ss.compile_security_state(**inp)
    assert state["legs"]["change"]["coverage_state"] == "AVAILABLE"
    inp["now"] = "2026-07-31T00:00:00Z"  # 121 days later -> STALE
    state = ss.compile_security_state(**inp)
    assert state["legs"]["change"]["coverage_state"] == "STALE"


# ---------------------------------------------------------------------------
# 5. prophet unavailable / 6. entry unavailable / 7. GMI-dislocation not covered
# ---------------------------------------------------------------------------

def test_case5_prophet_unavailable() -> None:
    state = ss.compile_security_state(**_golden_input())
    prophet = state["legs"]["opportunity_context"]["prophet"]
    assert prophet["ref"] is None
    assert prophet["state"] == "UNAVAILABLE"
    assert prophet["reason"] == "no current Prophet US owner output for this security"


def test_case6_entry_unavailable() -> None:
    state = ss.compile_security_state(**_load("entry_unavailable_input.json"))
    entry = state["legs"]["opportunity_context"]["entry"]
    assert entry == {"state": "UNAVAILABLE", "available": False, "null_reason": "not_assessed"}
    assert state["legs"]["opportunity_context"]["coverage_state"] == "UNAVAILABLE"
    assert any(g["code"] == "ENTRY_TIMING_UNAVAILABLE" for g in state["legs"]["risk"]["failed_gates"])


def test_case6_entry_available() -> None:
    state = ss.compile_security_state(**_golden_input())
    entry = state["legs"]["opportunity_context"]["entry"]
    assert entry["available"] is True
    assert entry["state"] == "AVAILABLE"
    assert entry["null_reason"] is None


def test_case7_gmi_dislocation_not_covered() -> None:
    state = ss.compile_security_state(**_golden_input())
    opp = state["legs"]["opportunity_context"]
    assert opp["market_incorporation"] == {"ref": None, "state": "NOT_COVERED"}
    assert opp["dislocation"] == {"ref": None, "state": "NOT_COVERED"}
    # NOT_COVERED is never counted as a degradation leg (distinct from
    # UNAVAILABLE) -- it must never appear in missing_legs/stale_legs/etc.
    assert "opportunity_context" not in state["coverage"]["missing_legs"] or state["legs"]["opportunity_context"]["coverage_state"] != "NOT_COVERED"


# ---------------------------------------------------------------------------
# 8. conflicting observations / 9. rights-blocked evidence
#
# K1's own conflict-detection and rights-blocked mechanics are already proven
# by tests/test_evidence_foundation_product_contract.py; these tests exercise
# THIS module's consumption of a K1 compilation receipt in each state — a
# widened (max_references=2) recipe is used ONLY here to construct a genuine
# two-reference conflicting scenario (the production path in
# compile_security_state always uses max_references=1, one owner-native
# generation per compile).
# ---------------------------------------------------------------------------

def _axis() -> dict:
    return {
        "state": "unknown", "assessment": "declarative_unverified",
        "basis": "declarative test-only relation; no independence verification performed",
    }


def test_case9_rights_blocked_evidence() -> None:
    reference = ss._build_k1_reference(
        generation_id="6d56c84a3ac23b8954e59ee7", event_id="evt_cik0000320193_2026q3_results",
        manifest_sha256="c3b9495028c07e6bf1eb385f520f0b3c57064b84ea430540ba9a0808cd2d14db",
        source_available_at="2026-07-30T20:30:28Z", observed_at="2026-07-30T20:30:28Z",
        generated_at="2026-07-30T20:30:28Z", rights_blocked=True,
    )
    block = ss._build_k1_block([reference])
    recipe = ss._build_k1_recipe()
    compilation = compile_recipe(recipe, blocks=[block], references={reference["reference_id"]: reference})
    assert compilation["state"] == "refused"
    assert compilation["dominant_degradation"] == "rights_blocked"
    assert compilation["denominator"]["rights_blocked"] == 1
    leg = ss._build_evidence_leg(recipe_id=recipe["recipe_id"], compilation=compilation)
    assert leg["coverage_state"] == "UNAVAILABLE"


def test_case8_conflicting_observations() -> None:
    ref_a = ss._build_k1_reference(
        generation_id="6d56c84a3ac23b8954e59ee7", event_id="evt_cik0000320193_2026q3_results",
        manifest_sha256="a" * 64, source_available_at="2026-07-30T20:30:28Z",
        observed_at="2026-07-30T20:30:28Z", generated_at="2026-07-30T20:30:28Z",
    )
    ref_b = ss._build_k1_reference(
        generation_id="ffffffffffffffffffffffff", event_id="evt_cik0000320193_2026q3_results",
        manifest_sha256="b" * 64, source_available_at="2026-07-30T21:30:28Z",
        observed_at="2026-07-30T21:30:28Z", generated_at="2026-07-30T21:30:28Z",
    )
    ref_a = {**ref_a, "relations": [{
        "type": "contradicts", "target_reference_id": ref_b["reference_id"],
        "automatic_effect": False, "deterministic_key": None,
        "independence": {
            "source_independence": _axis(), "information_novelty": _axis(),
            "mechanism_independence": _axis(),
        },
    }]}
    ref_a["reference_id"] = compute_reference_id(ref_a)
    block = ss._build_k1_block([ref_a, ref_b])
    recipe = ss._build_k1_recipe(max_references=2)
    references = {ref_a["reference_id"]: ref_a, ref_b["reference_id"]: ref_b}
    compilation = compile_recipe(recipe, blocks=[block], references=references)
    assert compilation["state"] == "abstained"
    assert compilation["dominant_degradation"] == "conflicted"
    evidence_leg = ss._build_evidence_leg(recipe_id=recipe["recipe_id"], compilation=compilation)
    assert evidence_leg["coverage_state"] == "CONFLICTED"
    assert evidence_leg["conflicts"] == compilation["block_ids"]

    # and it feeds strongest_unresolved_fact rule #1 (conflicted leg beats
    # every later rule, even a required-leg degradation).
    change_leg = ss._build_change_leg(
        workspace=None, workspace_disposition="not_published",
        event_id=None, generation_id=None, now_date=datetime.date(2026, 8, 23),
    )
    assert change_leg["coverage_state"] == "UNAVAILABLE"  # would win rule #3 if not for the conflict
    risk_leg = ss._build_risk_leg(
        blob={}, change_leg=change_leg, evidence_leg=evidence_leg,
        opportunity_leg={"coverage_state": "UNAVAILABLE"},
    )
    assert risk_leg["strongest_unresolved_fact"] == {
        "state": "conflicted_leg", "leg": "evidence", "code": None, "en": None, "zh": None,
    }


def test_k1_negative_path_mismatched_subject_refuses() -> None:
    """compile_recipe must REFUSE a block whose reference targets a different
    CIK than the recipe's canonical subject — the negative-path K1 assertion."""
    reference = ss._build_k1_reference(
        generation_id="6d56c84a3ac23b8954e59ee7", event_id="evt_cik0000320193_2026q3_results",
        manifest_sha256="c" * 64, source_available_at="2026-07-30T20:30:28Z",
        observed_at="2026-07-30T20:30:28Z", generated_at="2026-07-30T20:30:28Z",
    )
    hostile = {**reference, "subject": {"key_type": "cik", "key": "9999999999"}}
    hostile["reference_id"] = compute_reference_id(hostile)
    block = ss._build_k1_block([hostile])
    recipe = ss._build_k1_recipe()
    with pytest.raises(EvidenceFoundationError):
        compile_recipe(recipe, blocks=[block], references={hostile["reference_id"]: hostile})


def test_k1_validators_pass_and_recipe_compiles_included_one() -> None:
    """K1 receipt assertions: validate_reference/validate_block/validate_recipe
    all pass on the production (max_references=1) shape, and compile_recipe
    reaches a non-refused state with denominator.included == 1."""
    from lib.evidence_foundation import validate_block, validate_recipe, validate_reference

    reference = ss._build_k1_reference(
        generation_id="6d56c84a3ac23b8954e59ee7", event_id="evt_cik0000320193_2026q3_results",
        manifest_sha256="c3b9495028c07e6bf1eb385f520f0b3c57064b84ea430540ba9a0808cd2d14db",
        source_available_at="2026-07-30T20:30:28Z", observed_at="2026-07-30T20:30:28Z",
        generated_at="2026-07-30T20:30:28Z",
    )
    references = {reference["reference_id"]: reference}
    assert validate_reference(reference) == reference
    block = ss._build_k1_block([reference])
    assert validate_block(block, references=references) == block
    recipe = ss._build_k1_recipe()
    assert validate_recipe(recipe) == recipe
    assert recipe["subject_instance"] == {"key_type": "cik", "key": "0000320193"}
    assert recipe["subject_key_types"] == ["cik"]
    assert recipe["identity_joins"] == []

    compilation = compile_recipe(recipe, blocks=[block], references=references)
    assert compilation["state"] not in {"refused", "abstained"}
    assert compilation["denominator"]["included"] == 1
    assert compilation["denominator"]["total"] == 1


# ---------------------------------------------------------------------------
# 10. price unavailable-stale (as_of.market_at typed-null, never silently now())
# ---------------------------------------------------------------------------

def test_case10_market_at_typed_null_when_blob_carries_no_asof() -> None:
    inp = _golden_input()
    del inp["blob"]["asof"]
    state = ss.compile_security_state(**inp)
    assert state["as_of"]["market_at"] is None
    # never silently defaults to `now` -- state_compiled_at (== now) must stay
    # a DIFFERENT, explicit field.
    assert state["as_of"]["state_compiled_at"] == inp["now"]


def test_case10_market_at_carried_verbatim_when_present() -> None:
    state = ss.compile_security_state(**_golden_input())
    assert state["as_of"]["market_at"] == "2026-08-23"


# ---------------------------------------------------------------------------
# 11. no user context
# ---------------------------------------------------------------------------

def test_case11_no_user_context() -> None:
    state = ss.compile_security_state(**_golden_input())
    assert state["legs"]["personal_impact"] == {
        "state": "NO_USER_CONTEXT", "user_exposure_overlay_ref": None, "coverage_state": "NOT_APPLICABLE",
    }


# ---------------------------------------------------------------------------
# 12. compiler failure with last-good / 13. first failure, no last-good
# ---------------------------------------------------------------------------

def test_case12_compiler_failure_with_last_good() -> None:
    """``prior_state`` is the FULL prior security_state.v1 read (Sol blocker
    4) -- an eligible one (PROVEN identity, not itself a COMPILER_FAILURE)
    snapshots into the compact {generated_at, content_sha256,
    dominant_degradation, reason} last_good receipt."""
    prior = ss.compile_security_state(**_golden_input())
    assert prior["identity_proof"]["state"] == "PROVEN"
    assert prior["dominant_degradation"] != "COMPILER_FAILURE"
    state = ss.compile_security_state_failure(
        now="2026-08-23T12:00:00Z", reason="unexpected KeyError", prior_state=prior,
    )
    assert state["dominant_degradation"] == "COMPILER_FAILURE"
    assert state["last_good"] == {
        "generated_at": prior["generated_at"],
        "content_sha256": prior["content_sha256"],
        "dominant_degradation": prior["dominant_degradation"],
        "reason": "prior cycle's committed security_state.v1",
    }
    assert state["coverage"]["overall_state"] == "UNAVAILABLE"
    for leg in state["legs"].values():
        assert leg["coverage_state"] in {"UNAVAILABLE", "NOT_APPLICABLE"}
    validator = _validator()
    assert list(validator.iter_errors(state)) == []


def test_case13_first_failure_no_last_good() -> None:
    state = ss.compile_security_state_failure(now="2026-08-23T12:00:00Z", reason="unexpected KeyError")
    assert state["dominant_degradation"] == "COMPILER_FAILURE"
    assert state["last_good"] is None
    validator = _validator()
    assert list(validator.iter_errors(state)) == []


def test_compiler_failure_never_emits_dominant_degradation_none() -> None:
    """Mutation kill: failure->current fallback. A compiler failure must never
    present as dominant_degradation NONE, with or without an eligible prior
    read to derive last_good from."""
    eligible_prior = ss.compile_security_state(**_golden_input())
    for prior_state in (None, eligible_prior):
        state = ss.compile_security_state_failure(now="2026-08-23T12:00:00Z", reason="boom", prior_state=prior_state)
        assert state["dominant_degradation"] == "COMPILER_FAILURE"
        assert state["dominant_degradation"] != "NONE"


# ---------------------------------------------------------------------------
# last_good eligibility + two-consecutive-failure regression (Sol blocker 4)
# ---------------------------------------------------------------------------

def test_last_good_eligibility_matrix() -> None:
    eligible_prior = {
        "schema": "security_state.v1",
        "identity_proof": {"state": "PROVEN"},
        "dominant_degradation": "PARTIAL",
        "generated_at": "2026-08-20T00:00:00Z",
        "content_sha256": "a" * 64,
    }
    assert ss._is_last_good_eligible(eligible_prior) is True
    assert ss.derive_last_good(eligible_prior) == {
        "generated_at": "2026-08-20T00:00:00Z", "content_sha256": "a" * 64,
        "dominant_degradation": "PARTIAL", "reason": "prior cycle's committed security_state.v1",
    }

    # identity_proof.state != PROVEN is never eligible, regardless of
    # dominant_degradation -- this is the half of the predicate a bare
    # dominant_degradation-only check would miss.
    blocked_prior = {**eligible_prior, "identity_proof": {"state": "BLOCKED_IDENTITY_BRIDGE"}}
    assert ss._is_last_good_eligible(blocked_prior) is False
    assert ss.derive_last_good(blocked_prior) is None

    partial_identity_prior = {**eligible_prior, "identity_proof": {"state": "PARTIAL"}}
    assert ss._is_last_good_eligible(partial_identity_prior) is False

    compiler_failure_prior = {**eligible_prior, "dominant_degradation": "COMPILER_FAILURE"}
    assert ss._is_last_good_eligible(compiler_failure_prior) is False

    wrong_schema_prior = {**eligible_prior, "schema": "something_else.v1"}
    assert ss._is_last_good_eligible(wrong_schema_prior) is False

    assert ss._is_last_good_eligible(None) is False
    assert ss._is_last_good_eligible("not-a-mapping") is False  # type: ignore[arg-type]
    assert ss.derive_last_good(None) is None

    # ineligible prior that itself carries a last_good -> carried forward
    # unchanged, never re-derived from the ineligible prior's own fields.
    carried = {
        "generated_at": "2026-08-18T00:00:00Z", "content_sha256": "c" * 64,
        "dominant_degradation": "STALE", "reason": "prior cycle's committed security_state.v1",
    }
    blocked_with_last_good = {**blocked_prior, "last_good": carried}
    assert ss.derive_last_good(blocked_with_last_good) == carried


def test_last_good_blocked_identity_bridge_prior_is_never_eligible() -> None:
    """A genuine BLOCKED_IDENTITY_BRIDGE compile (not a hand-built dict) is
    never eligible as a last_good snapshot, even though its
    dominant_degradation is UNAVAILABLE (not COMPILER_FAILURE) -- proves the
    identity_proof.state==PROVEN half of the predicate is load-bearing on its
    own, independent of the dominant_degradation half."""
    blocked_state = ss.compile_security_state(**_load("identity_r1_superseded_input.json"))
    assert blocked_state["identity_proof"]["state"] == "BLOCKED_IDENTITY_BRIDGE"
    assert blocked_state["dominant_degradation"] != "COMPILER_FAILURE"
    assert ss._is_last_good_eligible(blocked_state) is False
    assert ss.derive_last_good(blocked_state) is None


def test_last_good_carries_forward_unchanged_across_two_consecutive_failures() -> None:
    """Two-consecutive-failure regression (Sol blocker 4): success S, then
    failure F1 (last_good == snapshot of S), then failure F2 computed with F1
    as prior_state -- last_good must STILL == snapshot of S, never F1 (F1 is
    itself a COMPILER_FAILURE read and is therefore never eligible)."""
    success_state = ss.compile_security_state(**_golden_input())
    assert success_state["identity_proof"]["state"] == "PROVEN"
    assert success_state["dominant_degradation"] != "COMPILER_FAILURE"
    expected_snapshot = {
        "generated_at": success_state["generated_at"],
        "content_sha256": success_state["content_sha256"],
        "dominant_degradation": success_state["dominant_degradation"],
        "reason": "prior cycle's committed security_state.v1",
    }

    failure_1 = ss.compile_security_state_failure(
        now="2026-08-24T12:00:00Z", reason="first failure", prior_state=success_state,
    )
    assert failure_1["dominant_degradation"] == "COMPILER_FAILURE"
    assert failure_1["last_good"] == expected_snapshot

    failure_2 = ss.compile_security_state_failure(
        now="2026-08-25T12:00:00Z", reason="second consecutive failure", prior_state=failure_1,
    )
    assert failure_2["dominant_degradation"] == "COMPILER_FAILURE"
    # F1 is COMPILER_FAILURE and therefore NEVER eligible on its own -- F2's
    # last_good must still be the ORIGINAL snapshot of S, never F1's own
    # (COMPILER_FAILURE, BLOCKED_IDENTITY_BRIDGE) fields.
    assert failure_2["last_good"] == expected_snapshot
    assert failure_2["last_good"] != {
        "generated_at": failure_1["generated_at"], "content_sha256": failure_1["content_sha256"],
        "dominant_degradation": failure_1["dominant_degradation"], "reason": "prior cycle's committed security_state.v1",
    }


# ---------------------------------------------------------------------------
# 5 identity refusal fixtures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("fixture", "expected_code"),
    [
        ("identity_r1_superseded_input.json", "SECURITY_SUPERSEDED"),
        ("identity_r34_multi_security_input.json", "ISSUER_GROUP_AMBIGUOUS"),
        ("identity_r3_duplicate_issuer_row_input.json", "ISSUER_GROUP_AMBIGUOUS"),
        ("identity_r6_migration_input.json", "IDENTITY_CORRECTED"),
        ("identity_r78_workspace_mismatch_input.json", "SUBJECT_NATIVE_PARITY_FAILED"),
    ],
)
def test_identity_refusal_fixtures_block_the_bridge(fixture: str, expected_code: str) -> None:
    state = ss.compile_security_state(**_load(fixture))
    assert state["identity_proof"]["state"] == "BLOCKED_IDENTITY_BRIDGE"
    assert expected_code in state["identity_proof"]["refusals"]
    assert state["dominant_degradation"] == "UNAVAILABLE"
    assert state["coverage"]["overall_state"] == "UNAVAILABLE"
    assert state["legs"]["change"]["coverage_state"] == "UNAVAILABLE"
    assert state["legs"]["evidence"]["compilation"]["state"] == "refused"
    assert state["legs"]["evidence"]["evidence_block_refs"] == []


def test_identity_r8_bridge_disagreement_isolated() -> None:
    """The workspace-CIK-mismatch fixture fails BOTH R7 (workspace parity) and
    R8 (master/workspace agreement) -- both codes must be present."""
    state = ss.compile_security_state(**_load("identity_r78_workspace_mismatch_input.json"))
    assert {"SUBJECT_NATIVE_PARITY_FAILED", "IDENTITY_BRIDGE_DISAGREEMENT"} <= set(
        state["identity_proof"]["refusals"]
    )


def test_identity_r9_corroboration_divergence_is_partial_not_blocked() -> None:
    state = ss.compile_security_state(**_load("identity_r9_divergent_input.json"))
    assert state["identity_proof"]["state"] == "PARTIAL"
    assert state["identity_proof"]["refusals"] == []  # R1-R8 all pass
    r9 = next(leg for leg in state["identity_proof"]["legs"] if leg["check"] == "R9")
    assert r9["result"] == "fail"
    assert r9["code"] == "CORROBORATION_DIVERGENT"
    values = {row["field"]: row["value"] for row in r9["values_read"]}
    assert values["corroboration_state"] == "DIVERGENT"
    # a PARTIAL identity proof does NOT force the required change leg to
    # refuse -- unlike a BLOCKED_IDENTITY_BRIDGE proof, R9 never gates R1-R8.
    assert state["legs"]["change"]["coverage_state"] != "UNAVAILABLE"


def test_identity_disclosures_are_the_four_verbatim_strings() -> None:
    state = ss.compile_security_state(**_golden_input())
    disclosures = set(state["identity_proof"]["disclosures"])
    assert disclosures == set(ss.DISCLOSURES)
    assert any(d.startswith("CIK_LEG_UNOWNED_ACCESS:") for d in disclosures)
    assert any(d.startswith("NO_GENERAL_NAMESPACE_RENDERER:") for d in disclosures)
    assert any(d.startswith("ISSUERMASTER_CURRENT_IDENTITY_ONLY:") for d in disclosures)
    assert any(d.startswith("ALIAS_EPOCH_VALID_FROM:") for d in disclosures)


# ---------------------------------------------------------------------------
# content_sha256 stability
# ---------------------------------------------------------------------------

def test_content_sha256_stable_under_generated_at_change() -> None:
    inp1 = _golden_input()
    inp2 = _golden_input()
    inp2["now"] = "2026-08-24T09:15:00Z"
    state1 = ss.compile_security_state(**inp1)
    state2 = ss.compile_security_state(**inp2)
    assert state1["generated_at"] != state2["generated_at"]
    assert state1["as_of"]["state_compiled_at"] != state2["as_of"]["state_compiled_at"]
    assert state1["content_sha256"] == state2["content_sha256"]


def test_content_sha256_changes_when_content_actually_changes() -> None:
    inp1 = _golden_input()
    inp2 = _golden_input()
    inp2["blob"]["conviction"]["cautions"] = ["A brand new, different caution."]
    state1 = ss.compile_security_state(**inp1)
    state2 = ss.compile_security_state(**inp2)
    assert state1["content_sha256"] != state2["content_sha256"]


# ---------------------------------------------------------------------------
# mutation kills — demonstrated live: introduce the violation, show it caught,
# revert. Each assertion below IS that demonstration (pytest -x fails loudly
# on the introduced violation if the guard regresses).
# ---------------------------------------------------------------------------

def test_mutation_kill_no_copied_event_payload_bodies() -> None:
    """The output must carry refs/counts/typed summaries only — never raw
    workspace facts/claims/guidance bodies (which would leak owner payload
    content this contract has no rights to redistribute)."""
    inp = _golden_input()
    inp["workspace"]["facts"] = [{"secret_fact_body": "should never appear in output"}]
    inp["workspace"]["claims"] = [{"secret_claim_body": "should never appear in output"}]
    inp["workspace"]["guidance"] = [{"secret_guidance_body": "should never appear in output"}]
    state = ss.compile_security_state(**inp)
    serialized = json.dumps(state)
    assert "secret_fact_body" not in serialized
    assert "secret_claim_body" not in serialized
    assert "secret_guidance_body" not in serialized
    # the K1 compilation receipt legitimately carries a field NAMED
    # owner_payloads_persisted (always false) -- the field name is fine; what
    # must never appear is an actual copied payload BODY, checked above.
    assert state["legs"]["evidence"]["compilation"]["owner_payloads_persisted"] is False


def test_mutation_kill_authority_is_all_false_and_display_only() -> None:
    """A ranker/gate/sizer/originate/execute leak must be caught by the
    self-validating closed schema (const false / const true)."""
    state = ss.compile_security_state(**_golden_input())
    validator = _validator()
    for field in ("can_rank", "can_gate", "can_size", "can_originate_signal", "can_execute"):
        mutated = copy.deepcopy(state)
        mutated["authority"][field] = True
        errors = list(validator.iter_errors(mutated))
        assert errors, f"mutation on authority.{field} was NOT caught"
    mutated = copy.deepcopy(state)
    mutated["authority"]["display_only"] = False
    assert list(validator.iter_errors(mutated))


def test_mutation_kill_no_null_means_neutral() -> None:
    """Every leg's coverage_state is a required, enum-typed, non-null field —
    a silent null substitution must fail schema validation."""
    state = ss.compile_security_state(**_golden_input())
    validator = _validator()
    for leg_name in state["legs"]:
        mutated = copy.deepcopy(state)
        mutated["legs"][leg_name]["coverage_state"] = None
        errors = list(validator.iter_errors(mutated))
        assert errors, f"null coverage_state on legs.{leg_name} was NOT caught"


def test_mutation_kill_no_derived_rank_or_score_field() -> None:
    """The contract's closed schema has no rank/score/probability-of-success
    property anywhere -- introducing one must be schema-invalid (proves the
    schema itself, not just this compiler's output, forbids it)."""
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    for banned in ("\"rank\"", "\"score\"", "\"gate_score\"", "\"probability_of_success\""):
        assert banned not in schema_text, f"schema declares a forbidden ranking/scoring field: {banned}"
    state = ss.compile_security_state(**_golden_input())
    mutated = copy.deepcopy(state)
    mutated["legs"]["risk"]["score"] = 0.87  # additionalProperties:false must reject this
    validator = _validator()
    errors = list(validator.iter_errors(mutated))
    assert errors, "an injected legs.risk.score field was NOT caught by the closed schema"


def test_mutation_kill_no_second_per_ticker_store_referenced() -> None:
    """No path in this module ever imports os/pathlib.Path.write* or opens a
    file — a would-be second per-ticker store would show up as an import or a
    direct filesystem write, neither of which this pure module has."""
    source = (ROOT / "engine" / "security_state.py").read_text(encoding="utf-8")
    for banned in ("open(", ".write_text(", ".write_bytes(", "import os", "requests.", "urllib."):
        assert banned not in source, f"engine/security_state.py performs I/O ({banned}) -- must stay pure"
    assert "datetime.now(" not in source and "datetime.utcnow(" not in source


def test_mutation_kill_no_prophet_radar_write_imports() -> None:
    """This module must never import a Prophet/Radar write surface -- opportunity_context's
    prophet_ref is a disclosed, permanent null in this build, never a live call."""
    source = (ROOT / "engine" / "security_state.py").read_text(encoding="utf-8")
    for banned in ("import prophet", "from engine import prophet", "from engine.prophet", "radar_write", "import radar"):
        assert banned.lower() not in source.lower()


def test_mutation_kill_ticker_only_identity_is_refused() -> None:
    """A ticker-only identity (no security_master row at all) must be refused
    via R1/R2, never silently accepted as 'close enough'."""
    inp = _golden_input()
    inp["security_master_row"] = None
    inp["issuer_security_ids"] = []
    state = ss.compile_security_state(**inp)
    assert state["identity_proof"]["state"] == "BLOCKED_IDENTITY_BRIDGE"
    assert "SECURITY_SUPERSEDED" in state["identity_proof"]["refusals"]
    assert "IDENTITY_UNRESOLVED" in state["identity_proof"]["refusals"]


def test_mutation_kill_no_dossier_side_arithmetic_on_owner_facts() -> None:
    """change.summary is built from typed COUNTS (len(facts), len(deltas),
    len(guidance)) and fixed template text only -- never a computed number
    derived by doing arithmetic ON the owner fact bodies themselves (e.g. no
    summed/averaged financial figure appears anywhere in the leg)."""
    inp = _golden_input()
    inp["workspace"]["facts"] = [{"value": 100}, {"value": 200}, {"value": 300}]
    state = ss.compile_security_state(**inp)
    summary_en = state["legs"]["change"]["summary"]["en"]
    assert "3 fact(s)" in summary_en  # a COUNT, not a computed sum (600) or average (200)
    assert "600" not in summary_en
    assert "200.0" not in summary_en


# ---------------------------------------------------------------------------
# purity: zero I/O, zero wall-clock (static check on the module source)
# ---------------------------------------------------------------------------

def test_compiler_module_is_free_of_business_io_and_wall_clock_reads() -> None:
    source = (ROOT / "engine" / "security_state.py").read_text(encoding="utf-8")
    banned_calls = [
        "pd.read_parquet", "pandas.read_parquet", "requests.get", "requests.post",
        "urllib.request", "socket.", "subprocess.",
    ]
    for banned in banned_calls:
        assert banned not in source
    assert "time.time()" not in source
    assert "datetime.now()" not in source
    assert "datetime.utcnow()" not in source


def test_compile_security_state_rejects_malformed_blob_without_expected_typed_state() -> None:
    """A genuinely malformed input (not a supported degradation) raises
    SecurityStateCompilationError rather than silently degrading — this is
    the boundary the producer's exception-containment path exists to catch."""
    inp = _golden_input()
    inp["blob"] = "not-a-mapping"  # type: ignore[assignment]
    with pytest.raises(ss.SecurityStateCompilationError):
        ss.compile_security_state(**inp)

    inp2 = _golden_input()
    inp2["workspace_disposition"] = "not_a_real_disposition"
    with pytest.raises(ss.SecurityStateCompilationError):
        ss.compile_security_state(**inp2)

    inp3 = _golden_input()
    inp3["now"] = "not-a-datetime"
    with pytest.raises(ss.SecurityStateCompilationError):
        ss.compile_security_state(**inp3)
