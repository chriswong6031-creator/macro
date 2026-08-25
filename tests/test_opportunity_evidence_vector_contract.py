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

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "opportunity_evidence"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def _codes(findings):
    return {f.code for f in findings}


def _clock(value, grain="date"):
    return {"value": value, "grain": grain}


def _unknown_clock():
    return {"state": "unknown"}


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
        "t0_source_object": "drl:IMXI:2026-08-14:up",
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
            construct="prophet_board_lane", state="observed",
            value_or_null={"lane": "not_on_board", "buyable": False, "eligible": False},
            coverage_flag={"state": "full", "note": None},
            asof=_clock("2026-08-14"), known_at=_clock("2026-08-14"),
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
        "t0_source": "caller_named_pit_object",
        "t0_source_object": "fpi-absence-receipt:CCJ:2026-08-10",
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
        "t0_source": "caller_named_pit_object",
        "t0_source_object": "dual-read-receipt:NEM:2026-08-09",
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
        "t0_source": "caller_named_pit_object",
        "t0_source_object": "optional-accrual-receipt:AAPL:2026-08-10",
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
        "t0_source_object": "drl:IMXI:2026-08-14:up",
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
    v["projection"]["entry_availability"]["prophet_board"] = {"state": "read", "slot_refs": ["drl_resid_shock"]}
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
    manifest["fixtures"]["golden_fpi_absence"]["receipts"] = [
        "FPI zero-EDGAR-statements rule: contracts/opportunity_evidence/slot_registry.v1.json "
        "constructs.forensics_scalars note ('Canadian/FPI names may have zero EDGAR rows: missing "
        "filings are not missing operations').",
    ]
    manifest["fixtures"]["golden_dual_read"]["receipts"] = [
        "Dual-read law receipt: constructs.macro_chain_state note (operator 2026-08-09 gold/real-rate "
        "case) plus CLAUDE.md 'Instrument verdicts are NOT market verdicts'.",
    ]
    manifest["fixtures"]["golden_optional_expectation"]["receipts"] = [
        "constructs.prospective_expectation_src_a1 note: 'OPTIONAL evidence family only ... never a "
        "prerequisite for composition'.",
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
    asof = {"value": "2026-08-14T09:30:00Z", "grain": "datetime", "t0_source": "drl_event_date", "t0_source_object": "x"}
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
    asof = {"value": "2026-08-14", "grain": "date", "t0_source": "drl_event_date", "t0_source_object": "x"}
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
    # golden_imxi's prophet_board_lane slot is state=observed -> the leg must
    # read "read"; forcing it to "missing" while the owner slot stays
    # observed is the named leg/owner mismatch.
    owner_slot = next(s for s in v["slots"] if s["construct"] == "prophet_board_lane")
    assert owner_slot["state"] == "observed"
    v["projection"]["entry_availability"]["prophet_board"]["state"] = "missing"
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
    # entry_owner_read fence catches this.
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
