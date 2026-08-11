"""The ClinicalTrials.gov Record History bounded activation, and its fences.

The repository operator cleared the rights gate on 2026-08-07
(``research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md``, Ruling 1). The
2026-08-11 forward-clock wave separately arms the runtime and exact four-NCT
universe. Every assertion here fences that bounded activation:

* the **runtime** gate is on only for this reviewed canary path;
* the **universe** is exactly the four B1 NCTs, never discovery or expansion;
* the **source-shape canary** is still mandatory, because the transport is an
  undocumented UI-backing route that can change without notice;
* public projection is source facts with attribution only; and
* all seven distribution obligations that bind every surface displaying this
  data are intact.

It also pins that the frozen policy file is not rewritten to impersonate live
state. Exactly three clocks open through the activation receipt, never through
a config boolean, and they accrue from the receipt instant with no backfill.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from engine.biocatalyst.family_clock import evaluate_family_clocks

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = ROOT / "config" / "biocatalyst_sources.yml"
OUTCOME_POLICY = ROOT / "config" / "biocatalyst_outcome_family_policy.yml"
CLOSED_BETA_MANIFEST = ROOT / "config" / "biocatalyst_closed_beta_source_manifest.yml"

RULING_REF = "research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md"
# The exact bytes of the ruling this enablement claims as its authorization.
# Re-bound 2026-08-08 when the ruling document gained Ruling 3 (the four
# subsidiary sponsor rows).  Ruling 1 — the rights decision this file tests — is
# unchanged in that document; the digest tracks the whole file, so an amendment
# anywhere in it moves every binding that cites it.  The rights, runtime,
# universe, and clock assertions below are untouched and still pin the same
# facts.
RULING_SHA256 = "6d6fe5771b70a2c3f6eacab4b2b1bb270331a1bc8c121064293905846d98a530"

SOURCE_ID = "clinicaltrials_gov_record_history"

# From the source's own ``distribution_obligations``.  Every surface that
# displays record-history data inherits all seven.
DISTRIBUTION_OBLIGATIONS = {
    "attribute_clinicaltrials_gov",
    "display_source_processing_date",
    "keep_projected_data_current",
    "disclose_content_modifications",
    "do_not_assert_proprietary_rights_over_source_database",
    "do_not_use_extracted_email_addresses_for_marketing",
    "display_source_submitter_responsibility_note",
}

# The three outcome families the bounded source path makes activation-eligible.
HISTORY_BACKED_FAMILIES = {
    "trial_progression_termination",
    "timing_slip",
    "enrollment_site_change",
}
CANARY_NCTS = [
    "NCT04528082",
    "NCT05020236",
    "NCT06602479",
    "NCT07218380",
]


def _load(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _source() -> dict:
    return _load(SOURCE_REGISTRY)["sources"][SOURCE_ID]


def _canary() -> dict:
    return _load(SOURCE_REGISTRY)["b2_history_canary"]


# --------------------------------------------------------------------------
# What the ruling DID do
# --------------------------------------------------------------------------


def test_record_history_rights_gate_is_operator_reviewed_and_enabled() -> None:
    source = _source()
    assert source["production_ingest_allowed"] is True
    # The registry's existing vocabulary for a reviewed source, not a new word.
    assert source["rights_state"] == "official_terms_operator_reviewed_for_bounded_beta"
    assert source["rights_reviewed_at"] == "2026-08-07T00:00:00Z"
    assert source["rights_review_basis"] == "official_terms_conditions_not_legal_opinion"
    assert source["license_class"] == "us_government_source_facts"


def test_the_enablement_carries_its_authorization_by_content_digest() -> None:
    # An enablement that only names a document proves nothing: the document can
    # change under it.  The digest binds the exact bytes that authorized this.
    source = _source()
    assert source["rights_review_ruling_ref"] == RULING_REF
    assert source["rights_review_ruling_sha256"] == RULING_SHA256

    ruling = ROOT / RULING_REF
    if ruling.is_file():
        actual = hashlib.sha256(ruling.read_bytes()).hexdigest()
        assert actual == RULING_SHA256, (
            "the committed ruling document no longer matches the digest this "
            "enablement cites as its authorization"
        )


def test_the_closed_beta_denominator_mirrors_the_registry_rights_state() -> None:
    manifest = _load(CLOSED_BETA_MANIFEST)
    binding = next(
        binding
        for family in manifest["families"]
        for binding in family["bindings"]
        if binding.get("id") == SOURCE_ID
    )
    source = _source()
    assert binding["rights_state"] == source["rights_state"]
    assert binding["production_ingest_allowed"] == source["production_ingest_allowed"]
    # This artifact remains a denominator, not the activation receipt.
    assert manifest["state"] == "draft_denominator_unarmed"


# --------------------------------------------------------------------------
# The bounded activation fences that must still hold
# --------------------------------------------------------------------------


def test_the_runtime_gate_is_armed_for_the_reviewed_canary() -> None:
    canary = _canary()
    assert canary["production_enable_env"] == "BIOCATALYST_HISTORY_ENABLED"
    assert canary["default_enabled"] is True
    assert _source()["collection_target"] == "operator_armed_explicit_nct_allowlist"


def test_the_universe_is_exactly_the_four_b1_ncts() -> None:
    canary = _canary()
    assert canary["allowlist_config_env"] == "BIOCATALYST_CANARY_NCTS"
    assert canary["default_allowlist"] == CANARY_NCTS
    assert len(canary["default_allowlist"]) == len(set(canary["default_allowlist"]))
    assert canary["universe_mode"] == "explicit_nct_allowlist"
    assert canary["universe_relation"] == "exact_b1_current_nct_set"


def test_the_source_shape_canary_requirement_is_still_mandatory() -> None:
    source = _source()
    # An undocumented UI-backing route can change without notice; the canary is
    # the tripwire and the ruling explicitly kept it mandatory.
    assert source["interface_stability"] == "undocumented_ui_backing_route"
    assert source["source_shape_canary_required"] is True
    assert source["maximum_consecutive_misses"] == 0


def test_public_projection_is_attributed_source_facts_and_not_launch_critical() -> None:
    source = _source()
    assert source["public_projection"] == "source_facts_with_attribution"
    assert source["raw_archive"] == "private_only"
    assert source["launch_critical"] is False


def test_all_seven_distribution_obligations_are_intact() -> None:
    obligations = _source()["distribution_obligations"]
    assert DISTRIBUTION_OBLIGATIONS <= set(obligations)
    assert len(obligations) == len(set(obligations))


def test_the_prohibited_claim_list_survived_the_enablement() -> None:
    prohibited = set(_source()["prohibited_claims"])
    assert {
        "protocol_changed_from_registry_diff_alone",
        "material_trial_change_from_registry_diff_alone",
        "endpoint_met_or_missed_from_registry_diff_alone",
        "government_verified_science_or_safety",
        "source_record_is_independently_verified",
    } <= prohibited


def test_exactly_three_history_families_evaluate_open_but_policy_stays_frozen() -> None:
    policy = _load(OUTCOME_POLICY)
    families = policy["families"]
    assert HISTORY_BACKED_FAMILIES <= set(families), sorted(families)
    for name in sorted(HISTORY_BACKED_FAMILIES):
        family = families[name]
        gate = family["entry_gate"]
        assert family["state"] == "clock_not_opened", name
        assert gate["satisfied"] is False, name
        assert "clinicaltrials_gov_record_history" in gate["required_source_ids"], name
    decisions = {
        decision.family_id: decision
        for decision in evaluate_family_clocks(
            policy, _load(SOURCE_REGISTRY), writer_available=True
        )
    }
    assert {name for name, decision in decisions.items() if decision.opened} == (
        HISTORY_BACKED_FAMILIES
    )
    assert policy["clock_activation"]["clock_state_authority"] == (
        "activation_receipt_not_this_file"
    )


def test_the_frozen_policy_file_itself_declares_no_open_clock() -> None:
    families = _load(OUTCOME_POLICY)["families"]
    opened = sorted(
        name for name, family in families.items() if family["state"] != "clock_not_opened"
    )
    assert opened == [], opened
