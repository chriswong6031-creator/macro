"""The ClinicalTrials.gov Record History RIGHTS enablement, and its fences.

The repository operator cleared exactly ONE of three gates on 2026-08-07
(``research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md``, Ruling 1): the rights
gate.  This file is the guard that the ruling did not quietly become an
activation.  Every assertion here is a fence the ruling explicitly left standing:

* the **runtime** gate (``production_enable_env`` / ``default_enabled``) is still
  off, so nothing collects;
* the **universe** gate (``allowlist_config_env`` / ``default_allowlist``) is
  still empty, so even an armed runtime would have nothing to fetch;
* the **source-shape canary** is still mandatory, because the transport is an
  undocumented UI-backing route that can change without notice;
* public projection is still blocked; and
* all seven distribution obligations that bind every surface displaying this
  data are intact.

It also pins that no outcome-family clock was opened.  A clock over a source
with no proven collection path would record "accruing since 2026-08-07" while
accruing nothing, which is the exact fabrication this program exists to prevent.
Clocks open through the activation receipt, never through a config edit.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = ROOT / "config" / "biocatalyst_sources.yml"
OUTCOME_POLICY = ROOT / "config" / "biocatalyst_outcome_family_policy.yml"
CLOSED_BETA_MANIFEST = ROOT / "config" / "biocatalyst_closed_beta_source_manifest.yml"

RULING_REF = "research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md"
# The exact bytes of the ruling this enablement claims as its authorization.
RULING_SHA256 = "f2536d82f8d77ed8bc6571765a269f29db896844fcd3c77042edf848540f6b2a"

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

# The three outcome families the rights ruling made gate-ELIGIBLE. None of them
# may have a clock: there is no proven collection path for this source.
HISTORY_BACKED_FAMILIES = {
    "trial_progression_termination",
    "timing_slip",
    "enrollment_site_change",
}


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
    # A denominator, not an activation: the family stays deferred/unavailable.
    assert manifest["state"] == "draft_denominator_unarmed"


# --------------------------------------------------------------------------
# What the ruling did NOT do -- the fences that must still hold
# --------------------------------------------------------------------------


def test_the_runtime_gate_is_still_off_so_nothing_collects() -> None:
    canary = _canary()
    assert canary["production_enable_env"] == "BIOCATALYST_HISTORY_ENABLED"
    assert canary["default_enabled"] is False
    assert _source()["collection_target"] == "operator_armed_explicit_nct_allowlist"


def test_the_universe_gate_is_still_empty_so_there_is_nothing_to_fetch() -> None:
    canary = _canary()
    assert canary["allowlist_config_env"] == "BIOCATALYST_CANARY_NCTS"
    assert canary["default_allowlist"] == []
    assert canary["universe_mode"] == "explicit_nct_allowlist"
    assert canary["universe_relation"] == "exact_b1_current_nct_set"


def test_the_source_shape_canary_requirement_is_still_mandatory() -> None:
    source = _source()
    # An undocumented UI-backing route can change without notice; the canary is
    # the tripwire and the ruling explicitly kept it mandatory.
    assert source["interface_stability"] == "undocumented_ui_backing_route"
    assert source["source_shape_canary_required"] is True
    assert source["maximum_consecutive_misses"] == 0


def test_public_projection_is_still_blocked_and_the_source_is_not_launch_critical() -> None:
    source = _source()
    assert source["public_projection"] == "blocked_until_enable"
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


def test_no_outcome_family_clock_was_opened_by_the_rights_enablement() -> None:
    # The ruling is explicit: a clock over a source with no proven collection
    # path would record accrual that is not happening.  Clearing a rights flag
    # makes families gate-ELIGIBLE; it does not start any clock.
    families = _load(OUTCOME_POLICY)["families"]
    assert HISTORY_BACKED_FAMILIES <= set(families), sorted(families)
    for name in sorted(HISTORY_BACKED_FAMILIES):
        family = families[name]
        gate = family["entry_gate"]
        assert family["state"] == "clock_not_opened", name
        assert gate["satisfied"] is False, name
        # The rights ruling made these families gate-ELIGIBLE. The writer is what
        # is still missing, and it is missing for every one of them.
        assert "o1b_outcome_writer" in gate["unsatisfied_preconditions"], name
        assert gate["blockers"], name
        assert "clinicaltrials_gov_record_history" in gate["required_source_ids"], name


def test_no_family_anywhere_in_the_policy_has_an_open_clock() -> None:
    families = _load(OUTCOME_POLICY)["families"]
    opened = sorted(
        name for name, family in families.items() if family["state"] != "clock_not_opened"
    )
    assert opened == [], opened
