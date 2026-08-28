"""K3-E Opportunity Evidence Vector — contract + hostile-fixture kill suite.

Exercises lib/opportunity_evidence.py against the two frozen contract files
(contracts/opportunity_evidence/vector.v1.schema.json,
contracts/opportunity_evidence/slot_registry.v1.json) plus the K1 Evidence
Foundation vocabulary source (contracts/evidence_foundation/reference.v1.schema.json)
and the fusion-family law (research/prophet_fusion/families.yml).

Four golden fixtures prove a lawful vector validates clean and that
compose_vector is deterministic (same input -> byte-identical output).
Thirteen hostile fixtures each plant the commissioned defect; incidental
cascade findings may accompany a planted defect (R-9 test-honesty repair,
2026-08-25 red-team wave — an earlier "exactly one" claim here was false),
and tests assert only that the commissioned code fires. A further block of
programmatic mutation tests (built from golden_imxi in-memory, no files)
covers the remaining named mutation classes, including the repair-wave
findings (R-1..R-9) below.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from lib.opportunity_evidence import (
    compose_vector,
    compute_content_sha256,
    load_slot_registry,
    load_vector_schema,
    registry_hygiene_findings,
    validate_vector,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "opportunity_evidence"
VECTOR_SCHEMA_PATH = CONTRACT_DIR / "vector.v1.schema.json"
SLOT_REGISTRY_PATH = CONTRACT_DIR / "slot_registry.v1.json"
K1_REFERENCE_SCHEMA_PATH = ROOT / "contracts" / "evidence_foundation" / "reference.v1.schema.json"
SECURITY_STATE_SCHEMA_PATH = ROOT / "contracts" / "market_os" / "security_state.v1.schema.json"
FAMILIES_PATH = ROOT / "research" / "prophet_fusion" / "families.yml"
LIB_SOURCE_PATH = ROOT / "lib" / "opportunity_evidence.py"
FREEZE_PACKET_PATH = ROOT / "research" / "opportunity_evidence" / "K3E_OPPORTUNITY_EVIDENCE_VECTOR_CONTRACT_FREEZE_2026-08-25.md"
DEC_PATH = ROOT / "agentos" / "decisions" / "DEC-K3E-OPPORTUNITY-EVIDENCE-VECTOR-CONTRACT.md"

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "opportunity_evidence"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def _codes(findings):
    return {f.code for f in findings}


def _clock(value, grain="date"):
    return {"value": value, "grain": grain}


def _unknown_clock():
    return {"state": "unknown"}


def _t0_ref(owner_store, native_identity, recorded_value, *, clock_class, native_field,
            sha256=None, grain="date"):
    """Sol item 1: an authenticated decision-time origin — an immutable
    owner-backed PIT reference in K1 reference.v1 EvidenceRef shape."""

    return {
        "owner_store": owner_store,
        "native_identity": native_identity,
        "native_digest": (
            {"state": "known", "sha256": sha256} if sha256 else {"state": "unknown", "sha256": None}
        ),
        "recorded_clock": {
            "value": recorded_value,
            "grain": grain,
            "clock_class": clock_class,
            "native_field": native_field,
            "state": "known",
        },
    }


def _dump(vector: dict) -> str:
    return json.dumps(vector, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# Golden fixture builders. Each returns (subject, asof, slots, kwargs) so the
# determinism test can call compose_vector a second time with the identical
# inputs and diff the result byte-for-byte against the committed file.
# ---------------------------------------------------------------------------


def _build_golden_imxi_drl_event():
    subject = {
        "subject_type": "us_listing_symbol",
        "value": "IMXI",
        "identity_state": "single_owner_native",
        "identity_bridge": None,
    }
    asof = {
        "value": "2026-08-14",
        "grain": "date",
        "t0_source": "drl_event_date",
        "t0_mode": "live",
        "t0_evidence_ref": _t0_ref(
            "data/price_pressure/",
            {"ticker": "IMXI", "date": "2026-08-14", "direction": "up"},
            "2026-08-14",
            clock_class="observed",
            native_field="harvested_asof",
        ),
    }
    slots = [
        dict(
            construct="drl_resid_shock", state="observed",
            value_or_null={"ret": 0.2470, "peer_ret": 0.0014, "resid": 0.2456, "resid_z": 11.85},
            basis={"peer_basis": "market"}, coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-14"), known_at=_clock("2026-08-14"),
        ),
        dict(
            construct="drl_filing_coverage", state="observed", value_or_null="filing-coverage-unknown",
            coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-14"), known_at=_clock("2026-08-14"),
        ),
        dict(
            construct="estimate_revisions", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "not_applicable", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
        dict(
            # R-8 red-team repair (2026-08-25): known_at is now the FINRA
            # knowable_date clock (8th NYSE session after settlement, per
            # lib/finra_knowable.py) — settlement 2026-07-31 -> Aug 3, 4, 5,
            # 6, 7, 10, 11, 12 -> knowable_date 2026-08-12. State stays
            # stale: a settlement two NYSE sessions shy of three full weeks
            # old is stale for the current tape either way.
            construct="short_interest", state="stale", missingness={"reason": "stale"},
            coverage_flag={"state": "fallback", "note": "settlement is stale relative to the capture asof"},
            asof=_clock("2026-07-31"), known_at=_clock("2026-08-12"),
        ),
        dict(
            construct="smart_money_13f", state="identity_unresolved", missingness={"reason": "unresolved_identity"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_clock("2026-06-30"), known_at=_clock("2026-08-14"),
        ),
        dict(
            construct="options_state", state="modeled", value_or_null={"gex_regime": "n/a_low_coverage"},
            coverage_flag={"state": "fallback", "note": "modeled dealer-gamma read"},
            asof=_clock("2026-08-13"), known_at=_clock("2026-08-13"),
        ),
        dict(
            construct="attention_views", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "not_applicable", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
        dict(
            # ADMISSION/CONTEXT, carried but never referenced from any leg
            # (Sol item 3). Prophet's board says IMXI is not on the board —
            # which is an admission fact, NOT an entry verdict.
            construct="prophet_board_lane", state="observed",
            value_or_null={"lane": "not_on_board", "buyable": False, "eligible": False},
            coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-14"), known_at=_clock("2026-08-14"),
        ),
        dict(
            # THE actionability surface. IMXI is not a Prophet plan, so the
            # owner publishes no entry_signal.status for it and the slot is
            # typed missing -- the entry_availability leg therefore reads
            # "missing", never "no entry open" inferred from the admission
            # slot directly above it.
            construct="prophet_entry_signal", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": "no Prophet plan for this subject: owner publishes no entry_signal.status"},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
        dict(
            construct="radar_probe_admission", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
    ]
    kwargs = dict(
        economic_cause_hypothesis={
            "hypothesis": "unknown",
            "provenance_class": "deterministic_rule",
            "supporting_slot_refs": [],
            "set_because": (
                "Cell C/E: residual large vs market fallback; filing coverage unknown; "
                "co-movement is not cause"
            ),
        },
        strongest_unresolved_fact={
            "state": "named",
            "fact": "edgar_covered=false — filing-coverage-unknown at the event date",
            "slot_refs": ["drl_filing_coverage"],
        },
        next_observable={
            "state": "named",
            "observable": "next EDGAR filing resolves the filing-coverage family",
            "expected_clock_class": "knowable",
            "expected_by": None,
        },
    )
    return subject, asof, slots, kwargs


def _build_golden_fpi_absence():
    subject = {
        "subject_type": "us_listing_symbol",
        "value": "CCJ",
        "identity_state": "single_owner_native",
        "identity_bridge": None,
    }
    asof = {
        "value": "2026-08-10",
        "grain": "date",
        "t0_source": "owner_pit_reference",
        # The FPI zero-EDGAR fact for CCJ is recorded in a committed E0
        # casebook whose bytes are digest-pinned below. That document was
        # written 2026-08-18, EIGHT days after this t0 — past the 5-day live
        # budget for owner_pit_reference — so the vector declares
        # retrospective_research rather than claiming operational PIT. This is
        # the mode's whole purpose: the lag is disclosed, not hidden.
        "t0_mode": "retrospective_research",
        "t0_evidence_ref": _t0_ref(
            "research/opportunity_evidence/",
            {"document": "E0_PEER_RELATIVE_CASEBOOK.md", "subject": "CCJ"},
            "2026-08-18",
            clock_class="belief_or_build",
            native_field="git_committer_date",
            sha256="f8f5d7443b23a75ae70cadf69768026528932f91a51c730cd0e4540bc4a97592",
        ),
    }
    slots = [
        dict(
            construct="forensics_scalars", state="missing", missingness={"reason": "not_applicable"},
            coverage_flag={"state": "not_applicable", "note": "FPI: zero EDGAR statements; missing filings are not missing operations"},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
        dict(
            construct="turnover_liquidity", state="observed", value_or_null={"mdv20_usd": 41_200_000.0},
            coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-10"), known_at=_clock("2026-08-10"),
        ),
        dict(
            construct="prophet_board_lane", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
        dict(
            construct="radar_probe_admission", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
    ]
    kwargs = dict(economic_cause_hypothesis=None)
    return subject, asof, slots, kwargs


def _build_golden_dual_read():
    subject = {
        "subject_type": "us_listing_symbol",
        "value": "NEM",
        "identity_state": "bridge_validated",
        "identity_bridge": {"method": "owner_native_same_key", "receipt": "theme membership gold_miners@2026-08-09"},
    }
    asof = {
        "value": "2026-08-09",
        "grain": "date",
        "t0_source": "owner_pit_reference",
        # The operator's real-rate-peak dual-read case study was committed on
        # 2026-08-09 — the decision date itself, so the recording lag is zero.
        #
        # This golden USED to claim t0_mode "live" on that basis, reasoning that
        # the object "provably existed at t0". Sol REQUEST_CHANGES 2026-08-26
        # item A struck that down and was right: nothing here is proven at
        # validation time. owner_pit_reference pins no owner_store and no clock
        # class, so the store, the recording date and the bytes behind the
        # digest are all caller-declared — a zero lag computed from a
        # caller-supplied clock is not evidence, and "live" would have been the
        # caller vouching for the caller. The generic source is now restricted
        # to retrospective_research, and this golden declares it.
        "t0_mode": "retrospective_research",
        "t0_evidence_ref": _t0_ref(
            "research/",
            {"document": "CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md", "subject": "NEM"},
            "2026-08-09",
            clock_class="belief_or_build",
            native_field="git_committer_date",
            sha256="4baa27cc3ae84422b4a252bf6b45af9c3708099f44ce51318b7d128c13c025ca",
        ),
    }
    slots = [
        dict(
            construct="drl_resid_shock", state="observed",
            value_or_null={"ret": 0.061, "peer_ret": 0.011, "resid": 0.05, "resid_z": 3.4},
            basis={"peer_basis": "sector"}, coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-09"), known_at=_clock("2026-08-09"),
        ),
        dict(
            construct="macro_chain_state", state="observed",
            value_or_null={"chain": "real_rate_peak", "window_verdict": "FAILED_63D_WINDOW"},
            coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-09"), known_at=_clock("2026-08-09"),
        ),
        dict(
            construct="prophet_board_lane", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
        dict(
            construct="radar_probe_admission", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
    ]
    kwargs = dict(
        economic_cause_hypothesis=None,
        failed_or_unavailable_gates=[
            {
                "gate": "real_rate_peak_chain_63d",
                "owner": "engine chain",
                "state": "failed",
                "reason": "63d window verdict FAILED while tape advanced — instrument verdict is not a market verdict",
            }
        ],
    )
    return subject, asof, slots, kwargs


def _build_golden_optional_expectation():
    subject = {
        "subject_type": "us_listing_symbol",
        "value": "AAPL",
        "identity_state": "single_owner_native",
        "identity_bridge": None,
    }
    asof = {
        "value": "2026-08-10",
        "grain": "date",
        "t0_source": "owner_pit_reference",
        # SRC-A1 observation artifacts live at a configurable, append-only path
        # and are NOT committed to this repo, so this reference carries an
        # ILLUSTRATIVE digest (disclosed in the fixture manifest receipt). It
        # proves the required shape — a generic owner reference must carry a
        # KNOWN immutability receipt — not a specific committed object.
        #
        # An illustrative digest over an uncommitted store is the clearest case
        # for Sol's 2026-08-26 item A ceiling: this reference could not be
        # checked by anyone, so claiming operational PIT here was indefensible.
        # The generic source is restricted to retrospective_research.
        "t0_mode": "retrospective_research",
        "t0_evidence_ref": _t0_ref(
            "SRC-A1 observation store (configurable path, append-only)",
            {"symbol": "AAPL", "observation_date": "2026-08-09"},
            "2026-08-10",
            clock_class="system_recorded",
            native_field="appended_at",
            sha256="0" * 63 + "1",
        ),
    }
    slots = [
        dict(
            construct="prospective_expectation_src_a1", state="observed",
            value_or_null={"eps_estimate": 1.62, "revenue_estimate_usd_mn": 91_500.0},
            coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-09"), known_at=_clock("2026-08-10"),
        ),
        dict(
            construct="prophet_board_lane", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
        dict(
            construct="radar_probe_admission", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
    ]
    kwargs = dict(economic_cause_hypothesis=None)
    return subject, asof, slots, kwargs


GOLDEN_BUILDERS = {
    "golden_imxi_drl_event": _build_golden_imxi_drl_event,
    "golden_fpi_absence": _build_golden_fpi_absence,
    "golden_dual_read": _build_golden_dual_read,
    "golden_optional_expectation": _build_golden_optional_expectation,
}


def _compose_golden(name: str) -> dict:
    subject, asof, slots, kwargs = GOLDEN_BUILDERS[name]()
    return compose_vector(subject, asof, slots, **kwargs)


# ---------------------------------------------------------------------------
# Hostile fixture builders — each starts from a small valid base vector and
# plants exactly one commissioned defect.
# ---------------------------------------------------------------------------


def _base_vector():
    subject = {
        "subject_type": "us_listing_symbol",
        "value": "IMXI",
        "identity_state": "single_owner_native",
        "identity_bridge": None,
    }
    asof = {
        "value": "2026-08-14",
        "grain": "date",
        "t0_source": "drl_event_date",
        "t0_mode": "live",
        "t0_evidence_ref": _t0_ref(
            "data/price_pressure/",
            {"ticker": "IMXI", "date": "2026-08-14", "direction": "up"},
            "2026-08-14",
            clock_class="observed",
            native_field="harvested_asof",
        ),
    }
    slots = [
        dict(
            construct="drl_resid_shock", state="observed",
            value_or_null={"ret": 0.2470, "peer_ret": 0.0014, "resid": 0.2456, "resid_z": 11.85},
            basis={"peer_basis": "market"}, coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-14"), known_at=_clock("2026-08-14"),
        ),
        dict(
            construct="attention_views", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "not_applicable", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
        dict(
            construct="prophet_board_lane", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
        dict(
            construct="radar_probe_admission", state="missing", missingness={"reason": "source_missing"},
            coverage_flag={"state": "unknown", "note": None},
            asof=_unknown_clock(), known_at=_unknown_clock(),
        ),
    ]
    return subject, asof, slots


def _rehash(vector: dict) -> dict:
    vector["content_sha256"] = compute_content_sha256(vector)
    return vector


def _raw_slot(**overrides) -> dict:
    base = {
        "family_binding": {"kind": "research_only", "family_id": None, "routed_to": None},
        "object_class": "derived_view",
        "state": "observed",
        "value_or_null": 1.0,
        "asof": {"value": "2026-08-14", "grain": "date", "clock_class": "belief_or_build", "native_field": "x", "state": "known"},
        "known_at": {"value": "2026-08-14", "grain": "date", "clock_class": "belief_or_build", "native_field": "x", "state": "known"},
        "coverage_flag": {"state": "unknown", "note": None},
        "owner_ref": {"owner": "unknown", "artifact": "unknown", "reader": "unknown", "evidence_ref_id": None},
        "derivation": "owner_read",
        "provenance_class": "owner_artifact",
        "missingness": {"state": "present", "reason": None, "zero_substituted": False},
        "basis": None,
        "variation_receipt": None,
        "included_in_composition": True,
        "exclusion_reason": None,
    }
    base.update(overrides)
    return base


def _build_hostile_composite_scalar():
    subject, asof, slots = _base_vector()
    v = compose_vector(subject, asof, slots)
    v["slots"].append({**_raw_slot(), "construct": "opportunity_score"})
    return _rehash(v)


def _build_hostile_disloc_reconstitution():
    subject, asof, slots = _base_vector()
    slots = slots + [
        dict(construct="disloc.ret_mkt.21d", state="observed", value_or_null=0.05,
             basis={"peer_basis": "market"}, asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
        dict(construct="disloc.ret_sec.21d", state="observed", value_or_null=0.03,
             basis={"peer_basis": "sector"}, asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
        dict(construct="disloc.ret_fac.21d", state="observed", value_or_null=0.08,
             basis={"peer_basis": "market"}, asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
    ]
    v = compose_vector(subject, asof, slots)
    v["slots"].append({**_raw_slot(), "construct": "dislocation_total"})
    return _rehash(v)


def _build_hostile_missing_neutral():
    subject, asof, slots = _base_vector()
    v = compose_vector(subject, asof, slots)
    for slot in v["slots"]:
        if slot["construct"] == "attention_views":
            slot["value_or_null"] = 0.0
    v["compilation_state"] = "complete"
    return _rehash(v)


def _build_hostile_clock_collapse():
    subject, asof, slots = _base_vector()
    slots = slots + [
        dict(construct="short_interest", state="stale", missingness={"reason": "stale"},
             asof=_clock("2026-07-31"), known_at=_clock("2026-08-14")),
    ]
    v = compose_vector(subject, asof, slots)
    for slot in v["slots"]:
        if slot["construct"] == "short_interest":
            slot["asof"]["native_field"] = "asof"
            slot["known_at"]["native_field"] = "asof"
    return _rehash(v)


def _build_hostile_double_family():
    subject, asof, slots = _base_vector()
    slots = slots + [
        dict(construct="sue_surprise", state="observed", value_or_null=2.4,
             family_binding={"kind": "governed_family", "family_id": "F5_FLOW_POSITIONING", "routed_to": None},
             asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
    ]
    v = compose_vector(subject, asof, slots)
    return _rehash(v)


def _build_hostile_residual_rederived():
    subject, asof, slots = _base_vector()
    v = compose_vector(subject, asof, slots)
    for slot in v["slots"]:
        if slot["construct"] == "drl_resid_shock":
            slot["owner_ref"] = {"owner": "lib/opportunity_evidence.py", "artifact": "in-memory", "reader": "local_recompute", "evidence_ref_id": None}
    return _rehash(v)


def _build_hostile_cause_from_epsilon():
    subject, asof, slots = _base_vector()
    v = compose_vector(
        subject, asof, slots,
        economic_cause_hypothesis={
            "hypothesis": "company_impairment",
            "provenance_class": "deterministic_rule",
            "supporting_slot_refs": ["drl_resid_shock"],
            "set_because": "residual magnitude alone (defect under test: cause must not be set from epsilon)",
        },
    )
    return _rehash(v)


def _build_hostile_identity_launder():
    subject, asof, slots = _base_vector()
    subject = dict(subject, identity_state="unproven")
    slots = slots + [
        dict(construct="smart_money_13f", state="observed", value_or_null={"holders_delta": 3},
             asof=_clock("2026-06-30"), known_at=_clock("2026-08-14")),
    ]
    v = compose_vector(subject, asof, slots)
    return _rehash(v)


def _build_hostile_authority_leak():
    subject, asof, slots = _base_vector()
    v = compose_vector(subject, asof, slots)
    v["projection"]["entry_availability"]["entry_signal"] = {
        "state": "read",
        "slot_refs": ["drl_resid_shock"],
        "verdict_class": "owner_entry_actionability",
    }
    return _rehash(v)


def _build_hostile_admission_as_entry():
    """Sol REQUEST_CHANGES 2026-08-25 item 3, planted verbatim: the Entry
    Availability leg is satisfied by Prophet board ADMISSION (lane / buyable /
    eligible) instead of the canonical actionability surface."""

    subject, asof, slots = _base_vector()
    slots = slots + [
        dict(
            construct="prophet_board_lane", state="observed",
            value_or_null={"lane": "core", "buyable": True, "eligible": True},
            coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-14"), known_at=_clock("2026-08-14"),
        ),
    ]
    v = compose_vector(subject, asof, slots)
    # "buyable=True on the board, therefore an entry is available" — the exact
    # ownership confusion Sol's item 3 forbids.
    v["projection"]["entry_availability"]["entry_signal"] = {
        "state": "read",
        "slot_refs": ["prophet_board_lane"],
        "verdict_class": "owner_entry_actionability",
    }
    return _rehash(v)


def _build_hostile_retrospective_t0():
    """Sol item 1: a decision clock claiming operational PIT ('live') whose own
    referenced object was minted long after t0 — t0 chosen with hindsight."""

    subject, asof, slots = _base_vector()
    asof = dict(
        asof,
        t0_mode="live",
        t0_evidence_ref=_t0_ref(
            "data/price_pressure/",
            {"ticker": "IMXI", "date": "2026-08-14", "direction": "up"},
            "2026-09-30",  # 47 days after t0, far past the 4-day live budget
            clock_class="observed",
            native_field="harvested_asof",
        ),
    )
    v = compose_vector(subject, asof, slots)
    return _rehash(v)


def _build_hostile_generic_live_t0():
    """Sol REQUEST_CHANGES 2026-08-26 item A: the generic owner_pit_reference is
    an accountability receipt, not a validation-time verification, so it may not
    claim operational point-in-time.

    Everything else about this reference is maximally well-formed — a known
    64-hex immutability digest, a known minting clock, and ZERO recording lag
    (the object is declared recorded on t0 itself, which would clear any lag
    budget). That is the point of the mutation: the defect is not sloppiness
    that a stricter lag rule would catch, it is the assurance CLAIM. Nothing
    here is checkable — owner_store, clock class and the bytes behind the digest
    are all caller-declared — so 'live' would be the caller vouching for the
    caller, and it fails closed on K3E_R021 regardless of how clean the rest of
    the reference looks."""

    subject, asof, slots = _base_vector()
    asof = dict(
        asof,
        t0_source="owner_pit_reference",
        t0_mode="live",
        t0_evidence_ref=_t0_ref(
            "research/opportunity_evidence/",
            {"document": "E0_PEER_RELATIVE_CASEBOOK.md", "subject": "IMXI"},
            asof["value"],  # zero lag: recorded on t0 itself
            clock_class="belief_or_build",
            native_field="git_committer_date",
            sha256="f8f5d7443b23a75ae70cadf69768026528932f91a51c730cd0e4540bc4a97592",
        ),
    )
    v = compose_vector(subject, asof, slots)
    return _rehash(v)


def _build_hostile_denominator_tamper():
    """Sol item 2: both mandatory aggregate denominators tampered
    independently — market_reflection recounted so a modeled leg is dropped
    from the numerator, and the gate denominator inflated."""

    subject, asof, slots = _base_vector()
    slots = slots + [
        dict(
            construct="options_state", state="modeled", value_or_null={"gex_regime": "positive"},
            coverage_flag={"state": "fallback", "note": "modeled dealer-gamma read"},
            asof=_clock("2026-08-14"), known_at=_clock("2026-08-14"),
        ),
    ]
    v = compose_vector(
        subject, asof, slots,
        failed_or_unavailable_gates=[
            {"gate": "coverage_gate", "owner": "engine/price_pressure/", "state": "unavailable", "reason": "no filing coverage"},
        ],
    )
    mr = v["projection"]["market_reflection"]["denominator"]
    # Drop the modeled I4 leg out of the numerator: "not observed, so not
    # counted" — the exact silent-exclusion Sol's item 2 forbids.
    mr["included"] -= 1
    mr["excluded"] += 1
    v["projection"]["failed_or_unavailable_gates"]["denominator"]["included"] += 3
    return _rehash(v)


def _build_hostile_lookahead():
    subject, asof, slots = _base_vector()
    subject = dict(subject, identity_state="bridge_validated", identity_bridge={"method": "owner_native_same_key", "receipt": "test receipt"})
    slots = slots + [
        dict(construct="smart_money_13f", state="observed", value_or_null={"holders_delta": 3},
             asof=_clock("2026-06-30"), known_at=_clock("2026-09-28")),
    ]
    v = compose_vector(subject, asof, slots)
    for slot in v["slots"]:
        if slot["construct"] == "smart_money_13f":
            slot["included_in_composition"] = True
            slot["exclusion_reason"] = None
    for leg in v["projection"]["market_reflection"]["incorporation_legs"]:
        if leg["leg"] == "I7_persistence_rejection":
            leg["state"] = "observed"
    return _rehash(v)


def _build_hostile_flow_nominal():
    subject, asof, slots = _base_vector()
    subject = dict(subject, value="SPY")
    slots = slots + [
        dict(construct="etf_flow_shares_outstanding", state="observed", value_or_null={"so_mn": 900.0},
             variation_receipt={"field": "so_mn", "window_days": 35, "observations": 25, "distinct_values": 1},
             asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
    ]
    v = compose_vector(subject, asof, slots)
    return _rehash(v)


def _build_hostile_impairment_axis():
    subject, asof, slots = _base_vector()
    v = compose_vector(subject, asof, slots)
    v["slots"].append({**_raw_slot(), "construct": "drl_impairment"})
    return _rehash(v)


def _build_hostile_llm_provenance():
    subject, asof, slots = _base_vector()
    v = compose_vector(subject, asof, slots)
    for slot in v["slots"]:
        if slot["construct"] == "drl_resid_shock":
            slot["provenance_class"] = "llm"
    return _rehash(v)


HOSTILE_BUILDERS = {
    "hostile_composite_scalar": (_build_hostile_composite_scalar, {"K3E_R001", "K3E_R004"}),
    "hostile_disloc_reconstitution": (_build_hostile_disloc_reconstitution, {"K3E_R004"}),
    "hostile_missing_neutral": (_build_hostile_missing_neutral, {"K3E_R005"}),
    "hostile_clock_collapse": (_build_hostile_clock_collapse, {"K3E_R006"}),
    "hostile_double_family": (_build_hostile_double_family, {"K3E_R002", "K3E_R003"}),
    "hostile_residual_rederived": (_build_hostile_residual_rederived, {"K3E_R008"}),
    "hostile_cause_from_epsilon": (_build_hostile_cause_from_epsilon, {"K3E_R009"}),
    "hostile_identity_launder": (_build_hostile_identity_launder, {"K3E_R010"}),
    "hostile_authority_leak": (_build_hostile_authority_leak, {"K3E_R011"}),
    "hostile_lookahead": (_build_hostile_lookahead, {"K3E_R007"}),
    "hostile_flow_nominal": (_build_hostile_flow_nominal, {"K3E_R012"}),
    "hostile_impairment_axis": (_build_hostile_impairment_axis, {"K3E_R001", "K3E_R017"}),
    "hostile_llm_provenance": (_build_hostile_llm_provenance, {"K3E_SCHEMA_ENUM"}),
    # Sol REQUEST_CHANGES 2026-08-25 repair wave.
    "hostile_admission_as_entry": (_build_hostile_admission_as_entry, {"K3E_R011"}),
    "hostile_retrospective_t0": (_build_hostile_retrospective_t0, {"K3E_R021"}),
    "hostile_denominator_tamper": (_build_hostile_denominator_tamper, {"K3E_R015"}),
    # Sol REQUEST_CHANGES 2026-08-26 repair wave.
    "hostile_generic_live_t0": (_build_hostile_generic_live_t0, {"K3E_R021"}),
}


ALL_FIXTURE_NAMES = sorted(list(GOLDEN_BUILDERS) + list(HOSTILE_BUILDERS))


def _all_vectors():
    vectors = {name: _compose_golden(name) for name in GOLDEN_BUILDERS}
    vectors.update({name: builder() for name, (builder, _codes) in HOSTILE_BUILDERS.items()})
    return vectors


def _write_fixtures():
    """(Re)generate every fixture file + manifest.json from the builders
    above. Not part of the test run itself — invoked once via
    `python3 -m tests.test_opportunity_evidence_vector_contract` to produce
    the committed files; the tests below only ever READ the committed files
    back (plus, for golden fixtures, re-run compose_vector to prove
    determinism)."""

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "opportunity_evidence.fixture_manifest.v1", "fixtures": {}}
    for name, vector in _all_vectors().items():
        text = _dump(vector)
        path = FIXTURE_DIR / f"{name}.json"
        path.write_text(text, encoding="utf-8")
        entry = {
            "bytes": len(text.encode("utf-8")),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
        if name in GOLDEN_BUILDERS:
            entry["kind"] = "golden"
        else:
            entry["kind"] = "hostile"
            entry["expected_codes"] = sorted(HOSTILE_BUILDERS[name][1])
        manifest["fixtures"][name] = entry

    manifest["fixtures"]["golden_imxi_drl_event"]["receipts"] = [
        "IMXI DRL residual shock values are illustrative event-day figures in the shape read by "
        "engine.price_pressure.ledger.read_ledger (resid/resid_z/peer_ret/peer_basis, market basis).",
    ]
    manifest["fixtures"]["golden_imxi_drl_event"]["receipts"].append(
        "t0 authentication: t0_source drl_event_date, owner_store data/price_pressure/ (registry "
        "t0_sources pin), recorded_clock harvested_asof 2026-08-14 = t0 -> zero recording lag, live."
    )
    manifest["fixtures"]["golden_fpi_absence"]["receipts"] = [
        "FPI zero-EDGAR-statements rule: contracts/opportunity_evidence/slot_registry.v1.json "
        "constructs.forensics_scalars note ('Canadian/FPI names may have zero EDGAR rows: missing "
        "filings are not missing operations'); recorded verbatim at "
        "research/opportunity_evidence/E0_PEER_RELATIVE_CASEBOOK.md line 93 ('Canadian/FPI names "
        "(CCJ) miss US EDGAR fundamentals').",
        "t0 authentication: owner_pit_reference digest-pinned to that casebook's committed bytes "
        "(sha256 f8f5d744...c4bc97592, git committer date 2026-08-18). That is 8 days AFTER t0 "
        "2026-08-10, past the 5-day live budget, so the vector declares t0_mode "
        "retrospective_research rather than claiming operational PIT.",
    ]
    manifest["fixtures"]["golden_dual_read"]["receipts"] = [
        "Dual-read law receipt: constructs.macro_chain_state note (operator 2026-08-09 gold/real-rate "
        "case) plus CLAUDE.md 'Instrument verdicts are NOT market verdicts'.",
        "t0 authentication: owner_pit_reference digest-pinned to research/"
        "CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md (sha256 4baa27cc...13c025ca), git committer date "
        "2026-08-09 = t0 -> zero recording lag, lawfully live.",
    ]
    manifest["fixtures"]["golden_optional_expectation"]["receipts"] = [
        "constructs.prospective_expectation_src_a1 note: 'OPTIONAL evidence family only ... never a "
        "prerequisite for composition'.",
        "t0 authentication: the native_digest on this fixture's t0_evidence_ref is ILLUSTRATIVE. "
        "SRC-A1 observation artifacts live at a configurable, append-only path and are not committed "
        "to this repository, so the reference proves the required SHAPE (a generic owner_pit_reference "
        "must carry a KNOWN immutability receipt) and not a specific committed object. Every other "
        "golden's digest is the real sha256 of real committed bytes.",
    ]

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    _write_fixtures()
    print(f"wrote {len(ALL_FIXTURE_NAMES)} fixtures + manifest to {FIXTURE_DIR}")


# ---------------------------------------------------------------------------
# Fixture-file plumbing.
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_fixture_files_present_and_valid_json():
    assert MANIFEST_PATH.exists(), "manifest.json must be committed"
    manifest = _load_manifest()
    for name in ALL_FIXTURE_NAMES:
        path = FIXTURE_DIR / f"{name}.json"
        assert path.exists(), f"missing fixture file {path}"
        data = json.loads(path.read_text(encoding="utf-8"))  # raises if not valid JSON
        assert isinstance(data, dict)
        assert name in manifest["fixtures"], f"manifest missing entry for {name}"


def test_manifest_byte_and_sha_receipts_recompute():
    manifest = _load_manifest()
    for name, entry in manifest["fixtures"].items():
        text = (FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8")
        raw = text.encode("utf-8")
        assert entry["bytes"] == len(raw), f"{name}: byte count drifted"
        assert entry["sha256"] == hashlib.sha256(raw).hexdigest(), f"{name}: sha256 receipt drifted"


@pytest.mark.parametrize("name", sorted(GOLDEN_BUILDERS))
def test_golden_fixture_validates_clean(name):
    vector = _load_fixture(name)
    findings = validate_vector(vector)
    assert findings == [], f"{name}: expected zero findings, got {findings}"


@pytest.mark.parametrize("name", sorted(GOLDEN_BUILDERS))
def test_golden_fixture_is_byte_identical_to_regenerated_output(name):
    """Determinism proof: compose_vector(same inputs) -> byte-identical JSON."""

    committed = FIXTURE_DIR / f"{name}.json"
    regenerated = _dump(_compose_golden(name))
    assert regenerated == committed.read_text(encoding="utf-8"), (
        f"{name}: compose_vector is not deterministic against its own committed fixture"
    )


def test_golden_optional_expectation_proves_the_accrual_is_optional():
    # golden_imxi_drl_event never carries prospective_expectation_src_a1 and
    # still validates with zero findings -- the SRC-A1 accrual is optional,
    # never a prerequisite for a lawful vector.
    imxi = _load_fixture("golden_imxi_drl_event")
    constructs = {s["construct"] for s in imxi["slots"]}
    assert "prospective_expectation_src_a1" not in constructs
    assert validate_vector(imxi) == []

    opt = _load_fixture("golden_optional_expectation")
    constructs_opt = {s["construct"] for s in opt["slots"]}
    assert "prospective_expectation_src_a1" in constructs_opt
    assert validate_vector(opt) == []


def test_golden_dual_read_instrument_state_never_enters_observed_or_inferred():
    vector = _load_fixture("golden_dual_read")
    projection = vector["projection"]
    assert "macro_chain_state" not in projection["observed"]["slot_refs"]
    assert "macro_chain_state" not in projection["inferred"]["slot_refs"]
    for leg in projection["market_reflection"]["incorporation_legs"]:
        assert "macro_chain_state" not in leg["slot_refs"]
    gates = {g["gate"] for g in projection["failed_or_unavailable_gates"]["gates"]}
    assert "real_rate_peak_chain_63d" in gates


_HOSTILE_CASES = [(name, codes) for name, (_builder, codes) in sorted(HOSTILE_BUILDERS.items())]


@pytest.mark.parametrize("name,expected", _HOSTILE_CASES)
def test_hostile_fixture_kills_with_expected_code(name, expected):
    vector = _load_fixture(name)
    codes = _codes(validate_vector(vector))
    for code in expected:
        assert code in codes, f"{name}: expected {code} in findings, got {sorted(codes)}"


# ---------------------------------------------------------------------------
# Programmatic mutation tests, built from golden_imxi in-memory (no files).
# ---------------------------------------------------------------------------


def _golden_imxi_vector() -> dict:
    return _compose_golden("golden_imxi_drl_event")


def test_mutation_stale_slot_value_flipped_to_zero_fires_r005():
    v = _golden_imxi_vector()
    for slot in v["slots"]:
        if slot["construct"] == "short_interest":
            slot["value_or_null"] = 0.0
    codes = _codes(validate_vector(v))
    assert "K3E_R005" in codes


def test_mutation_relabel_smart_money_family_fires_r002():
    v = _golden_imxi_vector()
    for slot in v["slots"]:
        if slot["construct"] == "smart_money_13f":
            slot["family_binding"] = {"kind": "governed_family", "family_id": "F4_CATALYST_EVENT", "routed_to": None}
    codes = _codes(validate_vector(v))
    assert "K3E_R002" in codes


def test_mutation_permitted_consumers_prophet_ranker_fires_schema():
    v = _golden_imxi_vector()
    v["permitted_consumers"] = ["prophet_ranker"]
    codes = _codes(validate_vector(v))
    assert any(c.startswith("K3E_SCHEMA") for c in codes)


def test_mutation_delete_entry_availability_leg_fires_schema():
    v = _golden_imxi_vector()
    del v["projection"]["entry_availability"]
    codes = _codes(validate_vector(v))
    assert any(c.startswith("K3E_SCHEMA") for c in codes)


def test_mutation_dominant_degradation_set_to_none_fires_r015():
    v = _golden_imxi_vector()
    assert v["dominant_degradation"] != "none"  # sanity: the golden fixture has adverse slots
    v["dominant_degradation"] = "none"
    codes = _codes(validate_vector(v))
    assert "K3E_R015" in codes


def test_mutation_dangling_leg_ref_fires_r014():
    v = _golden_imxi_vector()
    v["projection"]["observed"]["slot_refs"].append("no_such_construct")
    codes = _codes(validate_vector(v))
    assert "K3E_R014" in codes


def test_mutation_stale_hash_fires_r020():
    v = _golden_imxi_vector()
    old_hash = v["content_sha256"]
    for slot in v["slots"]:
        if slot["construct"] == "drl_resid_shock":
            slot["value_or_null"] = dict(slot["value_or_null"], resid=0.9999)
    assert v["content_sha256"] == old_hash  # left stale on purpose
    codes = _codes(validate_vector(v))
    assert "K3E_R020" in codes


# ---------------------------------------------------------------------------
# Repair-wave (2026-08-25 red-team) mutation tests, R-1..R-9.
# ---------------------------------------------------------------------------


def test_mutation_r1_value_payload_forbidden_key_fires_r004():
    v = _golden_imxi_vector()
    for slot in v["slots"]:
        if slot["construct"] == "drl_resid_shock":
            slot["value_or_null"] = dict(slot["value_or_null"], score=0.9)
    codes = _codes(validate_vector(v))
    assert "K3E_R004" in codes


def test_mutation_r1_disloc_string_and_dict_values_both_fire_r004():
    subject, asof, slots = _base_vector()
    slots = slots + [
        dict(construct="disloc.ret_mkt.21d", state="observed", value_or_null="0.08",
             basis={"peer_basis": "market"}, asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
        dict(construct="disloc.ret_sec.21d", state="observed", value_or_null={"ret": 0.03},
             basis={"peer_basis": "sector"}, asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
    ]
    v = compose_vector(subject, asof, slots)
    findings = validate_vector(v)
    r004_paths = {f.path for f in findings if f.code == "K3E_R004"}
    assert any("ret_mkt" in p for p in r004_paths), r004_paths
    assert any("ret_sec" in p for p in r004_paths), r004_paths


def test_mutation_r3_disloc_near_sum_reconstruction_fires_r004():
    subject, asof, slots = _base_vector()
    slots = slots + [
        dict(construct="disloc.ret_mkt.21d", state="observed", value_or_null=0.05,
             basis={"peer_basis": "market"}, asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
        dict(construct="disloc.ret_sec.21d", state="observed", value_or_null=0.03,
             basis={"peer_basis": "sector"}, asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
        dict(construct="disloc.ret_fac.21d", state="observed", value_or_null=0.08000001,
             basis={"peer_basis": "market"}, asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
    ]
    v = compose_vector(subject, asof, slots)
    codes = _codes(validate_vector(v))
    assert "K3E_R004" in codes


def test_mutation_r2_intraday_datetime_lookahead_fires_r007_and_autoexcludes():
    subject = {
        "subject_type": "us_listing_symbol", "value": "IMXI",
        "identity_state": "bridge_validated",
        "identity_bridge": {"method": "owner_native_same_key", "receipt": "test receipt"},
    }
    asof = {
        "value": "2026-08-14T09:30:00Z", "grain": "datetime", "t0_source": "drl_event_date",
        "t0_mode": "live",
        "t0_evidence_ref": _t0_ref(
            "data/price_pressure/", {"ticker": "IMXI", "date": "2026-08-14"}, "2026-08-14",
            clock_class="observed", native_field="harvested_asof",
        ),
    }
    slots = [
        dict(construct="smart_money_13f", state="observed", value_or_null={"holders_delta": 1},
             asof=_clock("2026-06-30"), known_at={"value": "2026-08-14T23:59:59Z", "grain": "datetime"}),
    ]
    v = compose_vector(subject, asof, slots)
    slot = next(s for s in v["slots"] if s["construct"] == "smart_money_13f")
    assert slot["included_in_composition"] is False, "compose_vector must auto-exclude an intraday look-ahead slot"
    assert slot["exclusion_reason"] == "lookahead_known_at_after_asof"

    # Force it back in to prove the validator independently catches the same
    # defect, not just compose_vector's own auto-exclusion.
    slot["included_in_composition"] = True
    slot["exclusion_reason"] = None
    codes = _codes(validate_vector(v))
    assert "K3E_R007" in codes


def test_mutation_r4_only_unsupported_and_unknown_adverse_dominant_is_unsupported():
    subject = {"subject_type": "us_listing_symbol", "value": "IMXI", "identity_state": "single_owner_native", "identity_bridge": None}
    asof = {
        "value": "2026-08-14", "grain": "date", "t0_source": "drl_event_date",
        "t0_mode": "live",
        "t0_evidence_ref": _t0_ref(
            "data/price_pressure/", {"ticker": "IMXI", "date": "2026-08-14"}, "2026-08-14",
            clock_class="observed", native_field="harvested_asof",
        ),
    }
    slots = [
        dict(construct="drl_resid_shock", state="observed", value_or_null={"ret": 0.1, "resid": 0.09},
             basis={"peer_basis": "market"}, asof=_clock("2026-08-14"), known_at=_clock("2026-08-14")),
        dict(construct="estimate_revisions", state="unsupported", missingness={"reason": "unsupported"},
             asof=_unknown_clock(), known_at=_unknown_clock()),
        dict(construct="attention_views", state="unknown", missingness={"reason": "unknown"},
             asof=_unknown_clock(), known_at=_unknown_clock()),
    ]
    v = compose_vector(subject, asof, slots)
    assert validate_vector(v) == [], "compose_vector's own output must be receipt-consistent"
    assert v["dominant_degradation"] == "unsupported"

    v["dominant_degradation"] = "none"
    codes = _codes(validate_vector(v))
    assert "K3E_R015" in codes


def test_mutation_r5a_entry_leg_state_mismatches_owner_slot_fires_r011():
    v = _golden_imxi_vector()
    # golden_imxi's prophet_entry_signal slot is state=missing -> the leg must
    # read "missing"; forcing it to "read" while the owner slot stays missing
    # is the named leg/owner mismatch (the leg claiming more certainty than
    # the owner read carries).
    owner_slot = next(s for s in v["slots"] if s["construct"] == "prophet_entry_signal")
    assert owner_slot["state"] == "missing"
    v["projection"]["entry_availability"]["entry_signal"]["state"] = "read"
    codes = _codes(validate_vector(v))
    assert "K3E_R011" in codes


def test_mutation_r5b_gate_owner_self_or_computed_fires_r011():
    v = _golden_imxi_vector()
    v["projection"]["failed_or_unavailable_gates"] = {
        "gates": [
            {"gate": "self_read_gate", "owner": "lib/opportunity_evidence.py", "state": "failed", "reason": "x"},
            {"gate": "self_rule_gate", "owner": "Computed", "state": "failed", "reason": "y"},
        ],
        "denominator": {"total": 2, "included": 0, "excluded": 2},
    }
    codes = _codes(validate_vector(v))
    assert "K3E_R011" in codes


def test_mutation_r6_entry_owner_read_construct_in_inferred_leg_fires_r011():
    v = _golden_imxi_vector()
    # radar_probe_admission is object_class derived_view, which the generic
    # inferred-leg object_class check alone would accept -- only the R-6
    # entry_role fence catches this.
    radar_slot = next(s for s in v["slots"] if s["construct"] == "radar_probe_admission")
    assert radar_slot["object_class"] == "derived_view"
    v["projection"]["inferred"]["slot_refs"].append("radar_probe_admission")
    codes = _codes(validate_vector(v))
    assert "K3E_R011" in codes


def test_compose_vector_never_puts_entry_owner_read_constructs_in_observed_or_inferred():
    for name in GOLDEN_BUILDERS:
        v = _compose_golden(name)
        refs = set(v["projection"]["observed"]["slot_refs"]) | set(v["projection"]["inferred"]["slot_refs"])
        assert "prophet_board_lane" not in refs
        assert "prophet_entry_signal" not in refs
        assert "radar_probe_admission" not in refs


def test_r7_golden_imxi_i4_leg_reads_modeled_not_observed():
    v = _load_fixture("golden_imxi_drl_event")
    options_slot = next(s for s in v["slots"] if s["construct"] == "options_state")
    assert options_slot["state"] == "modeled"
    leg = next(l for l in v["projection"]["market_reflection"]["incorporation_legs"] if l["leg"] == "I4_options_repricing")
    assert leg["state"] == "modeled"


def test_mutation_r7_modeled_leg_mislabeled_observed_fires_r015():
    v = _golden_imxi_vector()
    leg = next(l for l in v["projection"]["market_reflection"]["incorporation_legs"] if l["leg"] == "I4_options_repricing")
    assert leg["state"] == "modeled"
    leg["state"] = "observed"
    codes = _codes(validate_vector(v))
    assert "K3E_R015" in codes


def test_r8_golden_imxi_short_interest_known_at_is_finra_knowable_date():
    v = _load_fixture("golden_imxi_drl_event")
    slot = next(s for s in v["slots"] if s["construct"] == "short_interest")
    assert slot["known_at"] == {
        "value": "2026-08-12", "grain": "date", "clock_class": "knowable",
        "native_field": "knowable_date", "state": "known",
    }
    assert slot["state"] == "stale"


def test_r9_compilation_state_enum_matches_security_state_recipe_compilation_receipt():
    vector_schema = load_vector_schema()
    security_schema = json.loads(SECURITY_STATE_SCHEMA_PATH.read_text(encoding="utf-8"))
    vector_enum = vector_schema["properties"]["compilation_state"]["enum"]
    compilation_node = (
        security_schema["properties"]["legs"]["properties"]["evidence"]["properties"]["compilation"]["oneOf"][1]
    )
    assert vector_enum == compilation_node["properties"]["state"]["enum"]


def test_r9_clock_value_grain_equals_k1_native_clock_grain_plus_unknown():
    vector_schema = load_vector_schema()
    k1_schema = json.loads(K1_REFERENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    vector_grain_enum = vector_schema["$defs"]["clockValue"]["properties"]["grain"]["enum"]
    k1_grain_enum = k1_schema["$defs"]["nativeClock"]["properties"]["grain"]["enum"]
    assert vector_grain_enum == k1_grain_enum + ["unknown"], (
        "grain is K1 nativeClock grain plus exactly one additive member, 'unknown' -- "
        "the sole declared delta from the K1 clock vocabulary"
    )


# ---------------------------------------------------------------------------
# K3E_R003(a) registry hygiene (test-level over the frozen registry).
# ---------------------------------------------------------------------------


def test_registry_one_column_one_family_hygiene():
    findings = registry_hygiene_findings()
    assert findings == [], f"registry double-homes a (family_id, member) pair: {findings}"


# ---------------------------------------------------------------------------
# K3E_R003(c) families-join: every governed (family_id, member) exists
# verbatim in research/prophet_fusion/families.yml.
# ---------------------------------------------------------------------------


def test_families_yaml_join_for_every_governed_construct():
    registry = load_slot_registry()
    with FAMILIES_PATH.open(encoding="utf-8") as fh:
        families = yaml.safe_load(fh)

    families_block = families["families"]
    for name, row in registry["constructs"].items():
        fb = row["family_binding"]
        if fb["kind"] != "governed_family":
            continue
        family_id = fb["family_id"]
        member = fb["member"]
        assert family_id in families_block, f"{name}: family {family_id!r} not in families.yml"
        member_names = {m["name"] for m in families_block[family_id]["members"]}
        assert member in member_names, (
            f"{name}: (family_id={family_id!r}, member={member!r}) does not exist verbatim in "
            f"research/prophet_fusion/families.yml"
        )


# ---------------------------------------------------------------------------
# K1 alignment: clock_class + missingness reason enums must be byte-identical
# to the K1 Evidence Foundation vocabulary. No fifth PIT vocabulary.
# ---------------------------------------------------------------------------

_K1_SEVEN_CLOCK_CLASSES = [
    "world_valid", "source_published", "knowable", "observed",
    "system_recorded", "belief_or_build", "review_due",
]


def test_k1_clock_class_enum_matches_reference_schema_exactly():
    vector_schema = load_vector_schema()
    k1_schema = json.loads(K1_REFERENCE_SCHEMA_PATH.read_text(encoding="utf-8"))

    vector_enum = vector_schema["$defs"]["clockValue"]["properties"]["clock_class"]["enum"]
    k1_enum = k1_schema["$defs"]["clockClass"]["enum"]

    assert vector_enum == _K1_SEVEN_CLOCK_CLASSES
    assert k1_enum == _K1_SEVEN_CLOCK_CLASSES
    assert vector_enum == k1_enum


def test_k1_missingness_reason_enum_matches_reference_schema_exactly():
    vector_schema = load_vector_schema()
    k1_schema = json.loads(K1_REFERENCE_SCHEMA_PATH.read_text(encoding="utf-8"))

    vector_enum = vector_schema["$defs"]["missingness"]["properties"]["reason"]["enum"]
    k1_enum = k1_schema["$defs"]["missingness"]["properties"]["reason"]["enum"]

    assert vector_enum == k1_enum


# ---------------------------------------------------------------------------
# No-store law: this contract is a view, never a store.
# ---------------------------------------------------------------------------


def test_no_opportunity_store_paths_are_tracked():
    import subprocess

    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    for path in out:
        assert not path.startswith("data/opportunity"), f"tracked store path exists: {path}"
        assert not path.startswith("engine/opportunity"), f"tracked engine module exists: {path}"


def test_lib_module_performs_no_writes():
    source = LIB_SOURCE_PATH.read_text(encoding="utf-8")
    forbidden_snippets = [
        "open(", "os.makedirs", "Path.mkdir", ".to_parquet(", ".to_csv(",
        "shutil.", "os.remove", "os.unlink",
    ]
    # `.mkdir(` alone would also flag Path methods used defensively elsewhere;
    # scan for the exact write-shaped calls this module must never contain.
    for snippet in forbidden_snippets:
        assert snippet not in source, f"lib/opportunity_evidence.py contains a write-shaped call: {snippet!r}"


def test_lib_module_is_stdlib_only():
    source = LIB_SOURCE_PATH.read_text(encoding="utf-8")
    for banned in ("import yaml", "import pandas", "from engine", "import engine", "import jsonschema"):
        assert banned not in source, f"lib/opportunity_evidence.py must stay stdlib-only; found {banned!r}"


@pytest.mark.parametrize("name", sorted(GOLDEN_BUILDERS))
def test_compose_output_round_trips_through_validate_with_zero_findings(name):
    vector = _compose_golden(name)
    assert validate_vector(vector) == []


# ---------------------------------------------------------------------------
# json.tool sanity on every fixture + the manifest (build commission).
# ---------------------------------------------------------------------------


def test_every_fixture_and_manifest_parse_as_json_tool_would():
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Sol REQUEST_CHANGES (2026-08-25) repair wave — S-1 decision-time origin,
# S-2 denominator integrity, S-3 Entry Availability ownership.
# ---------------------------------------------------------------------------


def test_s1_retired_free_string_t0_object_is_no_longer_expressible():
    """The old escape hatch — t0 trusted from an arbitrary caller string — must
    be structurally unrepresentable, not merely discouraged."""

    schema = load_vector_schema()
    decision_clock = schema["$defs"]["decisionClock"]
    assert "t0_source_object" not in decision_clock["properties"]
    assert "caller_named_pit_object" not in decision_clock["properties"]["t0_source"]["enum"]
    assert decision_clock["additionalProperties"] is False
    assert set(decision_clock["required"]) == {"value", "grain", "t0_source", "t0_mode", "t0_evidence_ref"}


def test_s1_t0_evidence_ref_reuses_k1_evidence_ref_field_semantics():
    """Sol item 1 asks for K1 EvidenceRef semantics 'where available'. The
    three carried fields must be the reference.v1 shapes, not lookalikes."""

    schema = load_vector_schema()
    k1 = json.loads(K1_REFERENCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    ref = schema["$defs"]["t0EvidenceRef"]["properties"]

    assert ref["owner_store"]["maxLength"] == k1["properties"]["owner_store"]["maxLength"]
    assert ref["native_identity"]["propertyNames"] == k1["properties"]["native_identity"]["propertyNames"]
    assert ref["native_identity"]["maxProperties"] == k1["properties"]["native_identity"]["maxProperties"]

    # K1 expresses the digest hash via {"$ref": "#/$defs/sha256"}; this
    # contract inlines that same definition because its stdlib-only structural
    # checker resolves $refs only within its OWN $defs. Resolve K1's ref and
    # require literal equality of the resulting shapes.
    k1_digest = json.loads(json.dumps(k1["$defs"]["nativeDigest"]).replace(
        '{"$ref": "#/$defs/sha256"}', json.dumps(k1["$defs"]["sha256"])
    ))
    assert ref["native_digest"]["oneOf"] == k1_digest["oneOf"]


def test_s1_mutation_retrospective_t0_claiming_live_fires_r021():
    v = _golden_imxi_vector()
    assert v["asof"]["t0_mode"] == "live"
    # The DRL event row is re-pointed at an object recorded 47 days after the
    # decision date while still claiming operational PIT.
    v["asof"]["t0_evidence_ref"]["recorded_clock"]["value"] = "2026-09-30"
    codes = _codes(validate_vector(_rehash(v)))
    assert "K3E_R021" in codes


def test_s1_same_lag_is_lawful_once_declared_retrospective():
    """The fence is on the CLAIM, not the research: the identical lag passes
    the moment the vector stops claiming operational PIT."""

    v = _golden_imxi_vector()
    v["asof"]["t0_evidence_ref"]["recorded_clock"]["value"] = "2026-09-30"
    # The vector is generated no earlier than the object it cites (K3E_R021's
    # generated_at invariant); move it with the recorded clock so this test
    # isolates the retrospective-lag law rather than tripping that one.
    v["generated_at"] = "2026-09-30T00:00:00Z"
    assert "K3E_R021" in _codes(validate_vector(_rehash(v)))
    v["asof"]["t0_mode"] = "retrospective_research"
    assert validate_vector(_rehash(v)) == []


def test_s1_mutation_wrong_owner_store_for_named_t0_source_fires_r021():
    v = _golden_imxi_vector()
    v["asof"]["t0_evidence_ref"]["owner_store"] = "data/us_prophet_rank/candidates/"
    codes = _codes(validate_vector(_rehash(v)))
    assert "K3E_R021" in codes


def test_s1_mutation_generic_owner_reference_without_digest_fires_r021():
    """owner_pit_reference — the only source with no owner_store pin — must
    carry a known immutability receipt, else it is a free string again."""

    v = _compose_golden("golden_dual_read")
    assert v["asof"]["t0_source"] == "owner_pit_reference"
    assert validate_vector(v) == []
    v["asof"]["t0_evidence_ref"]["native_digest"] = {"state": "unknown", "sha256": None}
    codes = _codes(validate_vector(_rehash(v)))
    assert "K3E_R021" in codes


# ---------------------------------------------------------------------------
# Sol REQUEST_CHANGES 2026-08-26 item A — generic t0 assurance ceiling.
# owner_pit_reference is an accountability receipt, not a validation-time
# verification, so it may not claim operational point-in-time.
# ---------------------------------------------------------------------------


def test_a1_generic_source_may_not_claim_live_t0():
    """The commissioned mutation: owner_pit_reference + t0_mode 'live' fails
    closed on K3E_R021, and the finding names the mode rather than blaming some
    incidental field."""

    v = _load_fixture("hostile_generic_live_t0")
    assert v["asof"]["t0_source"] == "owner_pit_reference"
    assert v["asof"]["t0_mode"] == "live"
    findings = validate_vector(v)
    assert "K3E_R021" in _codes(findings)
    mode_findings = [f for f in findings if f.code == "K3E_R021" and f.path == "$.asof.t0_mode"]
    assert mode_findings, f"no K3E_R021 finding on $.asof.t0_mode: {[(f.code, f.path) for f in findings]}"
    assert "may not claim t0_mode 'live'" in mode_findings[0].message


def test_a1_the_defect_is_the_claim_not_the_lag():
    """Proof the ceiling is not just the lag law wearing a different hat: this
    reference has ZERO recording lag, which clears every budget in the registry.
    Flip only the mode and the identical reference validates clean."""

    v = _load_fixture("hostile_generic_live_t0")
    assert v["asof"]["t0_evidence_ref"]["recorded_clock"]["value"] == v["asof"]["value"], "fixture must have zero lag for this proof to mean anything"
    assert "K3E_R021" in _codes(validate_vector(v))
    v["asof"]["t0_mode"] = "retrospective_research"
    assert validate_vector(_rehash(v)) == []


def test_a2_registry_restricts_the_generic_source_and_keeps_the_pinned_four_live_capable():
    """The rule lives in the registry, not in a hardcoded source name: the
    generic row may claim only retrospective_research, and the four rows whose
    owner_store and clock class validation actually checks keep 'live'."""

    sources = load_slot_registry()["t0_sources"]["sources"]
    assert sources["owner_pit_reference"]["lawful_t0_modes"] == ["retrospective_research"]
    # ...and its lag budget is null by construction, since 'live' is the only
    # mode that ever consults it. That null is the second, independent fence.
    assert sources["owner_pit_reference"]["max_recording_lag_days"] is None
    for name, pin in sources.items():
        if name == "owner_pit_reference":
            continue
        assert "live" in pin["lawful_t0_modes"], f"{name} lost its live capability"
        # A source that may claim live must be checkable AND budgeted.
        assert pin["owner_store"] is not None, f"{name} may claim live with no owner_store pin"
        assert pin["recorded_clock_class"] is not None, f"{name} may claim live with no clock-class pin"
        assert pin["max_recording_lag_days"] is not None, f"{name} may claim live with no lag budget"


def test_a2_pinned_source_still_validates_live():
    """Guard against over-correcting: the repair must not quietly disarm 'live'
    for the sources that legitimately carry it."""

    v = _golden_imxi_vector()
    assert v["asof"]["t0_source"] == "drl_event_date"
    assert v["asof"]["t0_mode"] == "live"
    assert validate_vector(v) == []


def test_a3_a_missing_lawful_modes_pin_denies_live_rather_than_granting_it():
    """Fail-closed direction. If the pin is deleted, the affected source drops
    to the WEAKER claim — a missing pin never hands out operational PIT."""

    import lib.opportunity_evidence as oe

    registry = copy.deepcopy(oe.load_slot_registry())
    del registry["t0_sources"]["sources"]["drl_event_date"]["lawful_t0_modes"]
    real = oe.load_slot_registry
    try:
        oe.load_slot_registry = lambda: registry
        live = _golden_imxi_vector()
        assert "K3E_R021" in _codes(validate_vector(live))
        retro = _golden_imxi_vector()
        retro["asof"]["t0_mode"] = "retrospective_research"
        assert validate_vector(_rehash(retro)) == []
    finally:
        oe.load_slot_registry = real


@pytest.mark.parametrize("bad_pin", ["live", 1, {"live": True}])
def test_a3_a_malformed_lawful_modes_pin_is_a_finding_not_a_crash(bad_pin):
    """`x in y` raises on a non-container and substring-matches on a bare
    string, so a drifted pin could either crash `validate_vector` — which
    documents that it never raises (red-team MAJOR 6) — or accept 'live' as a
    substring of some longer value. A malformed pin behaves as a missing one."""

    import lib.opportunity_evidence as oe

    registry = copy.deepcopy(oe.load_slot_registry())
    registry["t0_sources"]["sources"]["drl_event_date"]["lawful_t0_modes"] = bad_pin
    real = oe.load_slot_registry
    try:
        oe.load_slot_registry = lambda: registry
        assert "K3E_R021" in _codes(validate_vector(_golden_imxi_vector()))
    finally:
        oe.load_slot_registry = real


def test_a3_reopening_live_on_the_generic_source_needs_more_than_one_list_edit():
    """The null budget is load-bearing. Widening lawful_t0_modes ALONE does not
    resurrect a live generic t0 — the missing lag budget still fails closed, so
    a future wave has to mint a budget deliberately rather than edit one list."""

    import lib.opportunity_evidence as oe

    registry = copy.deepcopy(oe.load_slot_registry())
    registry["t0_sources"]["sources"]["owner_pit_reference"]["lawful_t0_modes"] = ["live", "retrospective_research"]
    real = oe.load_slot_registry
    try:
        oe.load_slot_registry = lambda: registry
        v = _load_fixture("hostile_generic_live_t0")
        findings = validate_vector(v)
        assert "K3E_R021" in _codes(findings), "widening the mode list alone re-opened live on the generic source"
        assert any("max_recording_lag_days" in f.message for f in findings), [f.message for f in findings]
    finally:
        oe.load_slot_registry = real


def test_a4_no_durable_artifact_calls_the_generic_path_fully_authenticated():
    """Sol item A's reconciliation leg. The overclaim must be gone from the
    artifacts a reader actually consults, and no shipped fixture may pair the
    generic source with an operational-PIT claim."""

    # Sol named schema, registry, freeze and DEC. The two machine-readable
    # contract files carry no quoted prose, so the retracted claim must be
    # absent outright; the two narrative records legitimately QUOTE it while
    # recording that it was wrong, so there the rule is that the phrase may
    # never stand unqualified.
    for path in (VECTOR_SCHEMA_PATH, SLOT_REGISTRY_PATH):
        assert "provably existed at t0" not in path.read_text(encoding="utf-8"), path

    for path in (VECTOR_SCHEMA_PATH, SLOT_REGISTRY_PATH, FREEZE_PACKET_PATH, DEC_PATH):
        text = path.read_text(encoding="utf-8")
        for claim in ("fully authenticated", "fully-authenticated"):
            for line in text.splitlines():
                if claim in line.lower():
                    # The phrase may only appear in a sentence that DENIES it.
                    assert any(w in line.lower() for w in ("no ", "not ", "never ")), f"{path}: unqualified {claim!r}: {line.strip()[:160]}"

    checked = 0
    for name in ALL_FIXTURE_NAMES:
        asof = _load_fixture(name)["asof"]
        if asof["t0_source"] == "owner_pit_reference" and name != "hostile_generic_live_t0":
            assert asof["t0_mode"] == "retrospective_research", f"{name} claims operational PIT on the generic source"
            checked += 1
    # Non-vacuity (red-team NIT 14: a guard that can never fail is not a guard).
    # This loop is the one that would have caught the shipped defect, so it must
    # actually be exercised — two goldens WERE claiming live on this source.
    assert checked >= 3, f"the generic-source fixture guard covered only {checked} fixtures"


def test_s1_mutation_unpinned_t0_source_fires_r021():
    v = _golden_imxi_vector()
    v["asof"]["t0_source"] = "prophet_stamp_date"  # pins a different owner store
    codes = _codes(validate_vector(_rehash(v)))
    assert "K3E_R021" in codes


def test_s1_native_identity_key_grammar_is_enforced_semantically():
    """The in-module structural checker implements no `propertyNames`, so the
    K1 key grammar would pass silently on shape alone. K3E_R021 re-checks it —
    without this the schema's propertyNames would be decorative."""

    v = _golden_imxi_vector()
    v["asof"]["t0_evidence_ref"]["native_identity"] = {"not a valid key!": "x"}
    codes = _codes(validate_vector(_rehash(v)))
    assert "K3E_R021" in codes

    empty = _golden_imxi_vector()
    empty["asof"]["t0_evidence_ref"]["native_identity"] = {}
    assert "K3E_R021" in _codes(validate_vector(_rehash(empty)))


def test_s1_missing_t0_evidence_ref_fails_closed():
    v = _golden_imxi_vector()
    del v["asof"]["t0_evidence_ref"]
    codes = _codes(validate_vector(_rehash(v)))
    assert "K3E_R021" in codes
    assert any(c.startswith("K3E_SCHEMA") for c in codes)


def test_s1_every_schema_t0_source_has_a_registry_pin():
    schema = load_vector_schema()
    registry = load_slot_registry()
    schema_sources = set(schema["$defs"]["decisionClock"]["properties"]["t0_source"]["enum"])
    pinned = set(registry["t0_sources"]["sources"])
    assert schema_sources == pinned, "every lawful t0_source must be authenticable"


def test_s2_public_validation_recomputes_every_mandatory_denominator():
    """Sol item 2: not one denominator on the wire may be taken on trust."""

    v = _golden_imxi_vector()
    assert validate_vector(v) == []

    tampers = [
        ("$.denominator", lambda d: d["denominator"].__setitem__("included", d["denominator"]["included"] + 1)),
        ("$.projection.observed.denominator", lambda d: d["projection"]["observed"]["denominator"].__setitem__("total", 99)),
        ("$.projection.inferred.denominator", lambda d: d["projection"]["inferred"]["denominator"].__setitem__("included", 0)),
        ("$.projection.market_reflection.denominator", lambda d: d["projection"]["market_reflection"]["denominator"].__setitem__("included", 0)),
        ("$.projection.failed_or_unavailable_gates.denominator", lambda d: d["projection"]["failed_or_unavailable_gates"]["denominator"].__setitem__("excluded", 7)),
    ]
    for label, tamper in tampers:
        mutated = _golden_imxi_vector()
        tamper(mutated)
        codes = _codes(validate_vector(_rehash(mutated)))
        assert "K3E_R015" in codes, f"{label}: tampered denominator survived validation"


def test_s2_modeled_market_reflection_evidence_counts_as_included():
    """The named half of Sol item 2: modeled evidence must not be silently
    counted excluded merely because it is not observed."""

    v = _golden_imxi_vector()
    legs = v["projection"]["market_reflection"]["incorporation_legs"]
    i4 = next(l for l in legs if l["leg"] == "I4_options_repricing")
    assert i4["state"] == "modeled"
    observed_legs = [l for l in legs if l["state"] == "observed"]
    assert len(observed_legs) == 1  # I2 only
    # included counts BOTH the observed leg and the modeled one.
    assert v["projection"]["market_reflection"]["denominator"]["included"] == 2
    assert validate_vector(v) == []


def test_s2_dropping_a_modeled_leg_from_the_numerator_fires_r015():
    v = _golden_imxi_vector()
    denom = v["projection"]["market_reflection"]["denominator"]
    denom["included"] -= 1   # "modeled is not observed, so don't count it"
    denom["excluded"] += 1
    codes = _codes(validate_vector(_rehash(v)))
    assert "K3E_R015" in codes


def test_s2_gate_denominator_semantics_are_frozen_and_recomputed():
    subject, asof, slots = _base_vector()
    v = compose_vector(
        subject, asof, slots,
        failed_or_unavailable_gates=[
            {"gate": "g_failed", "owner": "engine/price_pressure/", "state": "failed", "reason": None},
            {"gate": "g_unavailable", "owner": "engine/price_pressure/", "state": "unavailable", "reason": None},
            {"gate": "g_not_evaluated", "owner": "engine/price_pressure/", "state": "not_evaluated", "reason": None},
        ],
    )
    assert validate_vector(v) == []
    # failed + unavailable are evaluated adverse verdicts (included);
    # not_evaluated is a coverage fact, not a verdict (excluded).
    assert v["projection"]["failed_or_unavailable_gates"]["denominator"] == {"total": 3, "included": 2, "excluded": 1}


def test_s3_registry_binds_exactly_one_actionability_owner():
    registry = load_slot_registry()
    roles = {
        name: row.get("entry_role")
        for name, row in registry["constructs"].items()
        if row.get("entry_role")
    }
    assert roles["prophet_entry_signal"] == "actionability"
    assert roles["prophet_board_lane"] == "admission_context"
    assert roles["radar_probe_admission"] == "probe_coverage"
    assert sum(1 for r in roles.values() if r == "actionability") == 1


def test_s3_actionability_owner_names_the_canonical_live_surface():
    """The entry leg must read engine.entry_signal's status axis projected by
    prophet.board_read/v1 — not a board admission column."""

    registry = load_slot_registry()
    row = registry["constructs"]["prophet_entry_signal"]
    assert "engine/entry_signal.py" in row["owner"]
    assert "prophet.board_read/v1" in row["artifact"]
    assert "entry_signal.status" in row["artifact"]
    assert row["reader"] == "engine.prophet_board_read.build_board_read"

    board_read_source = (ROOT / "engine" / "prophet_board_read.py").read_text(encoding="utf-8")
    assert 'SCHEMA = "prophet.board_read/v1"' in board_read_source
    assert "entry_signal" in board_read_source


def test_s3_mutation_board_admission_cannot_satisfy_the_entry_leg_fires_r011():
    v = _golden_imxi_vector()
    admission = next(s for s in v["slots"] if s["construct"] == "prophet_board_lane")
    assert admission["state"] == "observed"  # the board DOES have a verdict
    v["projection"]["entry_availability"]["entry_signal"] = {
        "state": "read",
        "slot_refs": ["prophet_board_lane"],
        "verdict_class": "owner_entry_actionability",
    }
    codes = _codes(validate_vector(_rehash(v)))
    assert "K3E_R011" in codes


def test_s3_admission_context_may_not_be_referenced_from_any_leg():
    for leg_path in (
        ("observed", "slot_refs"),
        ("inferred", "slot_refs"),
        ("strongest_unresolved_fact", "slot_refs"),
    ):
        v = _golden_imxi_vector()
        v["projection"][leg_path[0]][leg_path[1]].append("prophet_board_lane")
        codes = _codes(validate_vector(_rehash(v)))
        assert "K3E_R011" in codes, f"{leg_path}: admission context leaked into a projection leg"


def test_s3_entry_leg_stays_explicitly_unknown_when_owner_is_unavailable():
    """When the actionability surface is unavailable the leg is explicitly
    typed — never inferred from admission, never a neutral 'no entry'."""

    v = _compose_golden("golden_fpi_absence")
    constructs = {s["construct"] for s in v["slots"]}
    assert "prophet_entry_signal" not in constructs
    assert v["projection"]["entry_availability"]["entry_signal"] == {
        "state": "unknown", "slot_refs": [], "verdict_class": "owner_entry_actionability",
    }
    assert validate_vector(v) == []

    # golden_imxi HAS the owner slot, typed missing -> the leg types missing,
    # even though the board admission slot right beside it is observed.
    imxi = _golden_imxi_vector()
    assert imxi["projection"]["entry_availability"]["entry_signal"]["state"] == "missing"
    assert next(s for s in imxi["slots"] if s["construct"] == "prophet_board_lane")["state"] == "observed"


def test_s3_radar_leg_is_typed_probe_coverage_never_a_trade_verdict():
    v = _golden_imxi_vector()
    radar_leg = v["projection"]["entry_availability"]["radar_probe_coverage"]
    assert radar_leg["verdict_class"] == "probe_coverage_state_not_trade_entry"
    schema = load_vector_schema()
    entry = schema["$defs"]["projection"]["properties"]["entry_availability"]["properties"]
    assert entry["radar_probe_coverage"]["properties"]["verdict_class"]["const"] == "probe_coverage_state_not_trade_entry"
    # The legacy leg names are gone: nothing can address the entry leg as a
    # Prophet board read any more. Assert the exact key set — `"radar" not in
    # entry` was vacuous (the recut key is `radar_probe_coverage`, so a
    # substring-style check could never fail whatever the recut did).
    assert set(entry) == {"entry_signal", "radar_probe_coverage", "composition_law"}


def test_s3_dangling_refs_are_caught_in_the_recut_entry_legs():
    """Regression guard for the recut itself: the leg-membership pass must
    follow the NEW leg names. Checking retired keys would leave both entry
    legs unpoliced while every other test still passed."""

    for leg_key in ("entry_signal", "radar_probe_coverage"):
        v = _golden_imxi_vector()
        v["projection"]["entry_availability"][leg_key]["slot_refs"].append("no_such_construct")
        codes = _codes(validate_vector(_rehash(v)))
        assert "K3E_R014" in codes, f"{leg_key}: dangling ref went unchecked"


def test_s3_authority_envelope_still_denies_entry_after_the_recut():
    for name in GOLDEN_BUILDERS:
        v = _compose_golden(name)
        assert v["authority"]["can_open_entry"] is False
        assert v["projection"]["entry_availability"]["composition_law"] == "owner_read_only_never_computed"


# ---------------------------------------------------------------------------
# Second red-team wave (2026-08-25, post-Sol-repair). Each test below reproduces
# a defect an independent opus reviewer found in the FIRST repair and proves it
# is closed. Named RT2-* by finding.
# ---------------------------------------------------------------------------


def _honest_receipts(v: dict) -> dict:
    """Re-derive the slot-level receipts so a probe isolates the defect under
    test instead of tripping the denominator check on its way."""
    from lib.opportunity_evidence import _recompute_denominator, _recompute_dominant_degradation

    v["denominator"] = _recompute_denominator(v["slots"])
    v["dominant_degradation"] = _recompute_dominant_degradation(v["slots"])
    return _rehash(v)


def test_rt2_blocker1_admission_payload_wearing_the_actionability_name_fires_r008():
    """BLOCKER 1: the construct NAME was the only thing separating the
    actionability owner from board admission. A caller could put the board's
    payload AND the board's owner_ref into a slot named prophet_entry_signal
    and satisfy the Entry Availability leg with zero findings."""

    v = _golden_imxi_vector()
    for s in v["slots"]:
        if s["construct"] == "prophet_entry_signal":
            s.update(
                state="observed", object_class="system_belief",
                value_or_null={"lane": "not_on_board", "buyable": False, "eligible": False},
                missingness={"state": "present", "reason": None, "zero_substituted": False},
                asof={"value": "2026-08-14", "grain": "date", "clock_class": "belief_or_build", "native_field": "as_of", "state": "known"},
                known_at={"value": "2026-08-14", "grain": "date", "clock_class": "knowable", "native_field": "as_of", "state": "known"},
                owner_ref={
                    "owner": "Prophet US (engine/us_board_rank.py + nightly stamp)",
                    "artifact": "data/us_prophet_rank/candidates/ frame columns lane, buyable, eligible",
                    "reader": "engine.us_context_vector.load_candidates",
                    "evidence_ref_id": None,
                },
                coverage_flag={"state": "full", "note": None},
                exclusion_reason=None, included_in_composition=True,
            )
    v["projection"]["entry_availability"]["entry_signal"] = {
        "state": "read", "slot_refs": ["prophet_entry_signal"],
        "verdict_class": "owner_entry_actionability",
    }
    codes = _codes(validate_vector(_honest_receipts(v)))
    assert "K3E_R008" in codes, f"board admission still satisfies the entry leg: {codes}"


def test_rt2_major7_object_class_relabel_to_escape_a_fence_fires_r008():
    v = _golden_imxi_vector()
    for s in v["slots"]:
        if s["construct"] == "drl_filing_coverage":
            s["object_class"] = "world_observation"  # registry pins derived_view
    assert "K3E_R008" in _codes(validate_vector(_honest_receipts(v)))


@pytest.mark.parametrize("mutate,label", [
    (lambda legs: [dict(l, state="observed") if l["leg"] in ("I1_anticipation", "I6_peer_response") else l for l in legs],
     "ref-less legs declare themselves observed"),
    (lambda legs: [l for l in legs if l["leg"] in ("I2_immediate_response", "I4_options_repricing")],
     "adverse legs deleted so coverage reads 100%"),
    (lambda legs: legs + [copy.deepcopy(next(l for l in legs if l["leg"] == "I2_immediate_response"))],
     "the one observed leg duplicated"),
])
def test_rt2_blocker2_market_reflection_leg_set_cannot_be_forged(mutate, label):
    """BLOCKER 2: recomputing a denominator from wire-declared leg states is
    worthless while the leg SET is attacker-controlled. All three forgeries
    recomputed 'consistently' and validated clean before the fix."""

    v = _golden_imxi_vector()
    mr = v["projection"]["market_reflection"]
    mr["incorporation_legs"] = mutate(mr["incorporation_legs"])
    legs = mr["incorporation_legs"]
    included = sum(1 for l in legs if l["state"] in ("observed", "modeled", "partial"))
    mr["denominator"] = {"total": len(legs), "included": included, "excluded": len(legs) - included}
    codes = _codes(validate_vector(_rehash(v)))
    assert "K3E_R015" in codes, f"forgery survived ({label}): {codes}"


def test_rt2_major5_lag_is_measured_as_an_instant_not_a_truncated_day():
    """MAJOR 5: the lag was day-truncated via `.date()`, so an object minted
    1.9999 days after t0 measured as exactly 1 day and slipped under a 1-day
    budget. Both sides are now compared as instants."""

    from lib.opportunity_evidence import _t0_recording_lag_seconds

    # The reviewer's own case: t0 just after midnight, object minted just before
    # midnight two calendar days later. Day-truncation called this "1 day".
    lag = _t0_recording_lag_seconds("2026-08-15T23:59:59Z", "2026-08-14T00:00:01Z")
    assert lag is not None and lag / 86400 > 1.99
    budget_days = load_slot_registry()["t0_sources"]["sources"]["radar_observed_at"]["max_recording_lag_days"]
    assert budget_days == 1
    assert lag > budget_days * 86400, "a ~2-day lag must not pass a 1-day budget"

    # End to end through the validator on the radar source.
    v = _golden_imxi_vector()
    v["asof"]["value"] = "2026-08-14T00:00:01Z"
    v["asof"]["grain"] = "datetime"
    v["asof"]["t0_source"] = "radar_observed_at"
    v["asof"]["t0_evidence_ref"].update(
        owner_store="data/entry_radar/",
        recorded_clock={"value": "2026-08-15T23:59:59Z", "grain": "datetime",
                        "clock_class": "belief_or_build", "native_field": "assembled_at", "state": "known"},
    )
    v["generated_at"] = "2026-08-16T00:00:00Z"
    assert "K3E_R021" in _codes(validate_vector(_rehash(v)))

    # A lag genuinely inside the budget still passes — the fence is on the
    # boundary, not on intraday precision as such.
    inside = _t0_recording_lag_seconds("2026-08-14T18:00:00Z", "2026-08-14T00:00:01Z")
    assert inside is not None and inside < budget_days * 86400


def test_rt2_major6_validate_vector_never_raises_on_hostile_clock():
    """MAJOR 6: len() on a non-string wire value escaped as TypeError, breaking
    the documented never-raises contract a fail-closed caller depends on."""

    v = _golden_imxi_vector()
    for bad in (20260814, [], {}, True):
        v["asof"]["t0_evidence_ref"]["recorded_clock"]["value"] = bad
        findings = validate_vector(v)  # must not raise
        assert any(f.code.startswith("K3E_") for f in findings)


def test_rt2_major4_generated_at_cannot_precede_the_cited_object():
    v = _golden_imxi_vector()
    v["generated_at"] = "2020-01-01T00:00:00Z"
    assert "K3E_R021" in _codes(validate_vector(_rehash(v)))


def test_rt2_major4_composer_never_backdates_generated_at():
    """The shipped FPI golden claimed it was generated eight days before the
    decision-time object it cites existed."""

    for name in GOLDEN_BUILDERS:
        v = _compose_golden(name)
        recorded = v["asof"]["t0_evidence_ref"]["recorded_clock"]["value"]
        rec = recorded if len(recorded) > 10 else f"{recorded}T00:00:00Z"
        assert v["generated_at"] >= rec, f"{name}: generated_at {v['generated_at']} precedes cited object {rec}"
        assert validate_vector(v) == []


@pytest.mark.parametrize("construct", ["prophet_entry_signal", "radar_probe_admission", "prophet_board_lane"])
def test_rt2_major8_entry_owner_reads_cannot_launder_into_strongest_unresolved_fact(construct):
    """MAJOR 8: the fence covered observed/inferred/market_reflection only, so
    the actionability and probe-coverage owners laundered cleanly into a leg the
    composer already refuses to put them in."""

    v = _golden_imxi_vector()
    v["projection"]["strongest_unresolved_fact"] = {
        "state": "named", "fact": "laundering probe", "slot_refs": [construct],
    }
    assert "K3E_R011" in _codes(validate_vector(_rehash(v)))


def test_rt2_minor9_deleting_the_i7_leg_is_refused():
    """MINOR 9: freeze §7 cited 'I7 structural exclusion' as a look-ahead proof,
    but the leg could simply be deleted from the wire."""

    v = _golden_imxi_vector()
    mr = v["projection"]["market_reflection"]
    mr["incorporation_legs"] = [l for l in mr["incorporation_legs"] if l["leg"] != "I7_persistence_rejection"]
    legs = mr["incorporation_legs"]
    included = sum(1 for l in legs if l["state"] in ("observed", "modeled", "partial"))
    mr["denominator"] = {"total": len(legs), "included": included, "excluded": len(legs) - included}
    assert "K3E_R015" in _codes(validate_vector(_rehash(v)))


def test_rt2_minor10_anchored_patterns_reject_a_trailing_newline():
    """MINOR 10: Python's `$` matches before a trailing newline, unlike the
    ECMA-262 `$` JSON Schema is defined against — so "IMXI\\n" satisfied K1's
    explicitly newline-free ^[^\\r\\n]+$."""

    v = _golden_imxi_vector()
    v["asof"]["t0_evidence_ref"]["native_identity"] = {"ticker": "IMXI\nrm -rf"}
    assert _codes(validate_vector(_rehash(v))), "newline smuggled through an anchored pattern"

    v2 = _golden_imxi_vector()
    v2["asof"]["value"] = "2026-08-14\n"
    assert _codes(validate_vector(_rehash(v2)))


def test_rt2_minor11_registry_pins_fail_closed_when_a_budget_or_digest_pin_is_missing():
    import lib.opportunity_evidence as oe

    v = _golden_imxi_vector()
    registry = copy.deepcopy(oe.load_slot_registry())
    del registry["t0_sources"]["sources"]["drl_event_date"]["max_recording_lag_days"]
    real = oe.load_slot_registry
    try:
        oe.load_slot_registry = lambda: registry
        assert "K3E_R021" in _codes(validate_vector(_rehash(v)))
    finally:
        oe.load_slot_registry = real


def test_rt2_minor12_self_named_gate_owners_are_refused():
    for owner in ("self", "internal", "this rule", "Computed", "lib/opportunity_evidence.py"):
        v = _golden_imxi_vector()
        v["projection"]["failed_or_unavailable_gates"] = {
            "gates": [{"gate": "g", "owner": owner, "state": "failed", "reason": None}],
            "denominator": {"total": 1, "included": 1, "excluded": 0},
        }
        assert "K3E_R011" in _codes(validate_vector(_rehash(v))), f"gate owner {owner!r} accepted"


def test_mutation_disloc_residual_slot_with_noncanonical_owner_fires_r008():
    # R008 sub-clause: a value-bearing disloc.ret_resid.<w> / disloc.resid_z.<w>
    # slot must cite one of the two canonical residual owners; windowed
    # attribution has no third producer to point at.
    v = _golden_imxi_vector()
    template = next(s for s in v["slots"] if s["construct"] == "drl_resid_shock")
    rogue = json.loads(json.dumps(template))
    rogue["construct"] = "disloc.ret_resid.21d"
    rogue["family_binding"] = {"kind": "research_only", "family_id": None, "routed_to": None}
    rogue["value_or_null"] = 0.1234
    rogue["asof"] = {"value": "2026-08-14", "grain": "date", "clock_class": "world_valid", "native_field": "bar_date", "state": "known"}
    rogue["known_at"] = {"value": "2026-08-14", "grain": "date", "clock_class": "observed", "native_field": "bar_date", "state": "known"}
    rogue["owner_ref"] = {"owner": "lib/opportunity_evidence.py", "artifact": "local", "reader": "local_recompute", "evidence_ref_id": None}
    v["slots"].append(rogue)
    codes = _codes(validate_vector(v))
    assert "K3E_R008" in codes
