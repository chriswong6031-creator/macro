"""K3-D Economic Propagation — hypothesis-record validator + hostile-fixture
kill suite.

Exercises lib/economic_propagation.py against the two frozen contract files
(contracts/economic_propagation/propagation_hypothesis.v1.schema.json,
contracts/economic_propagation/generator_registry.v1.json).

Three golden fixtures prove a lawful record validates clean (one
supported_hypothesis, two typed abstentions) and that compose_hypothesis is
deterministic (same input -> byte-identical output, including record_id and
content_sha256). Fourteen hostile fixtures each plant one commissioned
defect via the standard technique: compose a lawful record with
compose_hypothesis, tamper the targeted field(s) directly on the dict, then
recompute content_sha256 (the one exception, hostile_sha_mismatch, tampers
and deliberately leaves the hash stale). Incidental cascade findings may
accompany a planted defect -- e.g. tampering a leg's graph/construct pairing
also perturbs the derived graph_states summary -- so every assertion here
checks only that the commissioned code is PRESENT in the findings, never
that it is the only one. A further block of pure compose_hypothesis()
raise-path tests (no fixture files -- EconomicPropagationError is raised
before a record ever exists) covers every laundering attack the composer
refuses outright, plus registry/schema alignment and no-store proofs.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from lib.economic_propagation import (
    BINDING_KILLS,
    EconomicPropagationError,
    compose_hypothesis,
    content_sha256,
    load_generator_registry,
    load_hypothesis_schema,
    validate_hypothesis,
)

ROOT = Path(__file__).resolve().parents[1]
LIB_SOURCE_PATH = ROOT / "lib" / "economic_propagation.py"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "economic_propagation"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"

ASOF = "2026-08-20"
COMPILED_AT = "2026-08-20T04:00:00Z"

BINDING_KILLS_EXPECTED = {
    "DNR:KILL-PSS-SR2-PEER-DIFFUSION",
    "DNR:KILL-PSS-SR3-PARTICIPATION",
    "DNR:KILL-CN-SUPPLY-ABSORPTION",
    "DNR:KILL-CAUSAL-DAG-ALPHA",
}


def _codes(findings):
    return {f.code for f in findings}


# ---------------------------------------------------------------------------
# Shape builders. Each returns a lawful sub-object; hostile builders tamper
# a copy of a composed record rather than trying to smuggle a defect through
# compose_hypothesis itself (which refuses unlawful input up front).
# ---------------------------------------------------------------------------


def _owner_ref(program="group-reads", artifact="data/edgar/material_8k_events.parquet",
               schema="group_linked_outsiders.v1"):
    return {"owner_program": program, "artifact": artifact, "artifact_schema": schema}


def _identity(state="RESOLVED", issuer="ISSUER-ACME", security="SEC-ACME", asof=ASOF, ref=None):
    return {
        "resolution_state": state,
        "owner_ref": ref or _owner_ref("stock-identity", "data/identity/master.parquet", "stock_identity.master.v1"),
        "issuer_id": issuer,
        "security_id": security,
        "resolution_asof": asof,
    }


def _source_event(event_id="evt-8k-0001", resolution=None, event_time="2026-08-18",
                   known_at="2026-08-18T12:00:00Z", event_class="filing_8k"):
    return {
        "event_id": event_id,
        "owner_ref": _owner_ref(),
        "event_class": event_class,
        "source_identity": resolution or _identity(),
        "event_time": event_time,
        "known_at": known_at,
    }


def _target(requested_key="ACME", resolution=None):
    return {"requested_key": requested_key, "resolution": resolution or _identity()}


def _g1_leg(leg_id="g1_customer", construct="disclosed_customer_supplier", role="customer",
            role_evidence_class="disclosed_role_specific", claim_strength="disclosed",
            usability_state="usable", asof=ASOF, known_at=ASOF):
    return {
        "leg_id": leg_id, "graph": "graph_1", "construct": construct,
        "role": role, "role_evidence_class": role_evidence_class, "claim_strength": claim_strength,
        "owner_ref": _owner_ref(), "evidence_refs": ["evidence-ref-g1"],
        "asof": asof, "known_at": known_at, "usability_state": usability_state,
    }


def _g2_leg(leg_id="g2_theme", construct="theme_membership", comparability_basis="shared_theme_vocabulary",
            usability_state="usable", asof=ASOF, known_at=ASOF):
    return {
        "leg_id": leg_id, "graph": "graph_2", "construct": construct,
        "comparability_basis": comparability_basis,
        "owner_ref": _owner_ref("gmi-theme-graph", "data/theme_graph/edges.parquet", "theme_graph.edges.v1"),
        "evidence_refs": ["evidence-ref-g2"], "asof": asof, "known_at": known_at, "usability_state": usability_state,
    }


def _g3_leg(leg_id="g3_resid", construct="residual_comovement", market_state_basis="residual_comovement",
            usability_state="usable", asof=ASOF, known_at=ASOF):
    return {
        "leg_id": leg_id, "graph": "graph_3", "construct": construct,
        "market_state_basis": market_state_basis,
        "owner_ref": _owner_ref("group-reads", "data/baskets/group_pulse.json", "group_pulse.v1"),
        "evidence_refs": ["evidence-ref-g3"], "asof": asof, "known_at": known_at, "usability_state": usability_state,
    }


def _admission(generator_id, graph, construct, coverage_state="covered", asof=ASOF, known_at=ASOF):
    return {
        "generator_id": generator_id, "graph": graph, "construct": construct,
        "owner_ref": _owner_ref(), "evidence_refs": ["evidence-ref-admission"],
        "asof": asof, "known_at": known_at, "coverage_state": coverage_state,
    }


def _mechanism_proposal(
    text="Demand for widgets shifts from Acme to Beta as capacity reallocates toward Beta's line.",
    direction="improves", mclass="demand_transfer", metric="revenue",
):
    return {
        "mechanism_class": mclass, "hypothesis_text": text,
        "predicted_operating_direction": direction, "operating_metric_class": metric,
    }


_ALTERNATIVES = [{
    "explanation_class": "sector_factor",
    "text": "A common sector-wide demand shift could also explain the co-movement without direct transfer.",
}]
_FALSIFIERS = [{
    "condition": "No incremental orders observed within two quarters of the filing.",
    "observable": "Segment revenue disclosure in the next two 10-Q filings.",
}]
_EXPIRY = {"review_by": "2026-11-20", "note": "Review after next quarterly filing."}


def _rehash(record: dict) -> dict:
    record = copy.deepcopy(record)
    record["content_sha256"] = content_sha256(record)
    return record


def _dump(record: dict) -> str:
    return json.dumps(record, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# Golden builders.
# ---------------------------------------------------------------------------


def _build_golden_supported_hypothesis():
    return compose_hypothesis(
        source_event=_source_event(),
        target=_target(),
        asof=ASOF, compiled_at=COMPILED_AT,
        generator_admissions=[
            _admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier"),
            _admission("gen_theme_membership", "graph_2", "theme_membership"),
            _admission("gen_residual_comovement", "graph_3", "residual_comovement"),
        ],
        relationship_paths=[_g1_leg()],
        similarity_evidence=[_g2_leg()],
        market_evidence=[_g3_leg()],
        mechanism_proposal=_mechanism_proposal(),
        alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
    )


def _build_golden_typed_abstention_unresolved():
    unresolved = _identity(state="NOT_IN_MASTER", issuer=None, security=None)
    return compose_hypothesis(
        source_event=_source_event(event_id="evt-8k-0002", resolution=unresolved),
        target=_target(requested_key="BETA", resolution=unresolved),
        asof=ASOF, compiled_at=COMPILED_AT,
        generator_admissions=[], relationship_paths=[], similarity_evidence=[], market_evidence=[],
        mechanism_proposal=None,
        alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
    )


def _build_golden_typed_abstention_rights_blocked():
    return compose_hypothesis(
        source_event=_source_event(event_id="evt-8k-0003"),
        target=_target(requested_key="GAMMA"),
        asof=ASOF, compiled_at=COMPILED_AT,
        generator_admissions=[_admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier")],
        relationship_paths=[_g1_leg(leg_id="g1_blocked", usability_state="rights_blocked")],
        similarity_evidence=[], market_evidence=[],
        mechanism_proposal=None,
        alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
    )


GOLDEN_BUILDERS = {
    "golden_supported_hypothesis": _build_golden_supported_hypothesis,
    "golden_typed_abstention_unresolved": _build_golden_typed_abstention_unresolved,
    "golden_typed_abstention_rights_blocked": _build_golden_typed_abstention_rights_blocked,
}


def _base_min():
    """RESOLVED identity, one supported graph_1 leg, one matching admission,
    no mechanism proposed. Reused as a tamper base for several hostile
    fixtures so each isolates its own commissioned defect."""

    return compose_hypothesis(
        source_event=_source_event(event_id="evt-min-0001"),
        target=_target(requested_key="MINCO"),
        asof=ASOF, compiled_at=COMPILED_AT,
        generator_admissions=[_admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier")],
        relationship_paths=[_g1_leg(leg_id="g1_min")],
        similarity_evidence=[], market_evidence=[],
        mechanism_proposal=None,
        alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
    )


def _base_no_graph1():
    """RESOLVED identity, admitted only via Graph 2, zero relationship_paths
    -- graph_1 stays unknown_unavailable. Tamper base for the mechanism-
    without-relationship attack (item 10)."""

    return compose_hypothesis(
        source_event=_source_event(event_id="evt-nog1-0001"),
        target=_target(requested_key="NOG1CO"),
        asof=ASOF, compiled_at=COMPILED_AT,
        generator_admissions=[_admission("gen_theme_membership", "graph_2", "theme_membership")],
        relationship_paths=[], similarity_evidence=[_g2_leg()], market_evidence=[],
        mechanism_proposal=None,
        alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
    )


# ---------------------------------------------------------------------------
# Hostile builders. One per numbered attack in the commission (some attacks
# share a fixture where the same tamper naturally trips both named codes).
# ---------------------------------------------------------------------------


def _build_hostile_unresolved_identity_laundered():
    # (1) NOT_IN_MASTER record with abstained flipped false AND evidence
    # smuggled in -- both R010 (abstention lie) and R011 (evidence present
    # on an unresolved identity) must fire from one tamper.
    rec = copy.deepcopy(_build_golden_typed_abstention_unresolved())
    rec["abstention"] = {"abstained": False, "reasons": []}
    rec["generator_admissions"] = [_admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier")]
    rec["relationship_paths"] = [_g1_leg()]
    return _rehash(rec)


def _build_hostile_relationship_construct_laundering():
    # (2)/(3) Graph 2 and Graph 3 constructs (theme_membership,
    # residual_comovement) placed as Graph-1 relationship_paths legs.
    rec = copy.deepcopy(_base_min())
    rec["relationship_paths"] = [
        _g1_leg(leg_id="g1_bad_g2", construct="theme_membership", role="role_unknown",
                role_evidence_class="none", claim_strength="candidate"),
        _g1_leg(leg_id="g1_bad_g3", construct="residual_comovement", role="role_unknown",
                role_evidence_class="none", claim_strength="candidate"),
    ]
    return _rehash(rec)


def _build_hostile_role_laundering():
    # (4) A generic agreement / financing-agent-shaped leg claiming a
    # specific economic role.
    rec = copy.deepcopy(_base_min())
    rec["relationship_paths"] = [
        _g1_leg(leg_id="g1_role_bad", construct="disclosed_agreement_role_unknown", role="supplier",
                role_evidence_class="agreement_role_unknown", claim_strength="candidate"),
    ]
    return _rehash(rec)


def _build_hostile_generator_refusal_admission():
    # (5) The one refusal row in the registry used as a target admission.
    rec = copy.deepcopy(_base_min())
    rec["generator_admissions"] = [_admission("gen_peer_participation_breadth", "graph_3", "peer_participation_breadth")]
    return _rehash(rec)


def _build_hostile_forbidden_key_injection():
    # (6) A scalar-authority-shaped key smuggled into source_event.
    rec = copy.deepcopy(_build_golden_supported_hypothesis())
    rec["source_event"] = {**rec["source_event"], "confidence_note": "high"}
    return _rehash(rec)


def _build_hostile_economic_share_nonnull():
    # (7) economic_share is reserved-null; any non-null value is unlawful.
    rec = copy.deepcopy(_build_golden_supported_hypothesis())
    rec["economic_share"] = 0.42
    return _rehash(rec)


def _build_hostile_clock_violations():
    # (8) One leg lookahead (known_at after asof), one leg with an
    # unparseable clock.
    rec = copy.deepcopy(_build_golden_supported_hypothesis())
    rec["relationship_paths"][0]["known_at"] = "2026-09-01"
    rec["similarity_evidence"][0]["known_at"] = "not-a-date"
    return _rehash(rec)


def _build_hostile_rights_blocked_claimed_supported():
    # (9) Only Graph-1 leg is rights_blocked, but graph_states.graph_1
    # still claims "supported" -- non-usable evidence counted.
    rec = copy.deepcopy(_base_min())
    rec["relationship_paths"][0]["usability_state"] = "rights_blocked"
    return _rehash(rec)


def _build_hostile_mechanism_without_relationship():
    # (10) Mechanism hypothesized while relationship_paths stays empty --
    # derived Graph-1 state can never be "supported" with zero legs.
    rec = copy.deepcopy(_base_no_graph1())
    rec["mechanism"] = {
        "state": "hypothesized",
        "mechanism_class": "demand_transfer",
        "hypothesis_text": "Demand shifts as capacity reallocates.",
        "predicted_operating_direction": "improves",
        "operating_metric_class": "revenue",
    }
    return _rehash(rec)


def _build_hostile_sha_mismatch():
    # (11) Tamper WITHOUT recomputing content_sha256 -- the one fixture
    # that deliberately skips the standard re-hash step.
    rec = copy.deepcopy(_build_golden_supported_hypothesis())
    rec["expiry"] = {**rec["expiry"], "note": "tampered without rehash"}
    return rec


def _build_hostile_binding_kills_drop():
    # (12) Drop one of the four const binding_kills entries.
    rec = copy.deepcopy(_build_golden_supported_hypothesis())
    rec["binding_kills"] = rec["binding_kills"][:3]
    return _rehash(rec)


def _build_hostile_authority_trading_true():
    # (13) authority.trading flipped true -- the const all-false object
    # violated both structurally and semantically.
    rec = copy.deepcopy(_build_golden_supported_hypothesis())
    rec["authority"] = {**rec["authority"], "trading": True}
    return _rehash(rec)


def _build_hostile_mechanism_trade_language():
    # (13) Trade/price vocabulary smuggled into mechanism prose.
    rec = copy.deepcopy(_build_golden_supported_hypothesis())
    rec["mechanism"] = {
        **rec["mechanism"],
        "hypothesis_text": "We expect a rally toward a new price target for Beta on this transfer.",
    }
    return _rehash(rec)


def _build_hostile_disagreeing_derived_summary():
    # (14) Caller-authored graph_states/hypothesis_state/abstention that
    # disagree with what the legs actually derive to.
    rec = copy.deepcopy(_base_min())
    rec["graph_states"] = {**rec["graph_states"], "graph_2": "present"}
    rec["hypothesis_state"] = "supported_hypothesis"
    rec["abstention"] = {"abstained": False, "reasons": []}
    return _rehash(rec)


HOSTILE_BUILDERS = {
    "hostile_unresolved_identity_laundered": (_build_hostile_unresolved_identity_laundered, {"K3D_R010", "K3D_R011"}),
    "hostile_relationship_construct_laundering": (_build_hostile_relationship_construct_laundering, {"K3D_R032"}),
    "hostile_role_laundering": (_build_hostile_role_laundering, {"K3D_R031"}),
    "hostile_generator_refusal_admission": (_build_hostile_generator_refusal_admission, {"K3D_R021"}),
    "hostile_forbidden_key_injection": (_build_hostile_forbidden_key_injection, {"K3D_R071"}),
    "hostile_economic_share_nonnull": (_build_hostile_economic_share_nonnull, {"K3D_R072"}),
    "hostile_clock_violations": (_build_hostile_clock_violations, {"K3D_R060", "K3D_R061"}),
    "hostile_rights_blocked_claimed_supported": (_build_hostile_rights_blocked_claimed_supported, {"K3D_R051", "K3D_R063"}),
    "hostile_mechanism_without_relationship": (_build_hostile_mechanism_without_relationship, {"K3D_R042"}),
    "hostile_sha_mismatch": (_build_hostile_sha_mismatch, {"K3D_R081"}),
    "hostile_binding_kills_drop": (_build_hostile_binding_kills_drop, {"K3D_R001"}),
    "hostile_authority_trading_true": (_build_hostile_authority_trading_true, {"K3D_R070"}),
    "hostile_mechanism_trade_language": (_build_hostile_mechanism_trade_language, {"K3D_R041"}),
    "hostile_disagreeing_derived_summary": (_build_hostile_disagreeing_derived_summary, {"K3D_R051", "K3D_R052", "K3D_R053"}),
}

ALL_FIXTURE_NAMES = sorted(list(GOLDEN_BUILDERS) + list(HOSTILE_BUILDERS))

FIXTURE_PURPOSES = {
    "golden_supported_hypothesis": "Lawful supported_hypothesis record: disclosed customer/supplier leg + comparable + market context, mechanism hypothesized.",
    "golden_typed_abstention_unresolved": "Lawful typed abstention: NOT_IN_MASTER identity, zero evidence legs, zero mechanism.",
    "golden_typed_abstention_rights_blocked": "Lawful typed abstention: RESOLVED identity, but the only Graph-1 leg is rights_blocked.",
    "hostile_unresolved_identity_laundered": "NOT_IN_MASTER identity with abstained flipped false and evidence legs smuggled in.",
    "hostile_relationship_construct_laundering": "Graph-2/Graph-3 constructs (theme_membership, residual_comovement) placed as Graph-1 relationship legs.",
    "hostile_role_laundering": "A generic-agreement leg (disclosed_agreement_role_unknown) claims a specific economic role.",
    "hostile_generator_refusal_admission": "The registry's one admits_target=false refusal row used as a target-admitting generator.",
    "hostile_forbidden_key_injection": "A scalar-authority-shaped key ('confidence_note') smuggled into source_event.",
    "hostile_economic_share_nonnull": "economic_share tampered non-null; it is a reserved-null axis.",
    "hostile_clock_violations": "One leg with known_at after asof (lookahead), one leg with an unparseable clock.",
    "hostile_rights_blocked_claimed_supported": "Only Graph-1 leg is rights_blocked but graph_states.graph_1 still claims supported.",
    "hostile_mechanism_without_relationship": "Mechanism hypothesized while relationship_paths stays empty (no Graph-1 support).",
    "hostile_sha_mismatch": "Field tampered WITHOUT recomputing content_sha256 (the stale-hash exception fixture).",
    "hostile_binding_kills_drop": "One of the four const binding_kills entries dropped.",
    "hostile_authority_trading_true": "authority.trading flipped true against the const all-false object.",
    "hostile_mechanism_trade_language": "Trade/price vocabulary ('rally', 'price target') smuggled into mechanism prose.",
    "hostile_disagreeing_derived_summary": "Caller-authored graph_states/hypothesis_state/abstention disagree with the actual derivation.",
}


def _all_records():
    records = {name: builder() for name, builder in GOLDEN_BUILDERS.items()}
    records.update({name: builder() for name, (builder, _codes) in HOSTILE_BUILDERS.items()})
    return records


def _write_fixtures():
    """(Re)generate every fixture file + manifest.json from the builders
    above. Not part of the test run itself -- invoked once via
    `python3 -m tests.test_economic_propagation_hypothesis_contract` to
    produce the committed files; the tests below only ever READ the
    committed files back (plus, for golden fixtures, re-run
    compose_hypothesis to prove determinism)."""

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "economic_propagation.fixture_manifest.v1", "fixtures": {}}
    for name, record in _all_records().items():
        text = _dump(record)
        path = FIXTURE_DIR / f"{name}.json"
        path.write_text(text, encoding="utf-8")
        entry = {
            "purpose": FIXTURE_PURPOSES[name],
            "bytes": len(text.encode("utf-8")),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
        if name in GOLDEN_BUILDERS:
            entry["kind"] = "golden"
            entry["expected_codes"] = []
        else:
            entry["kind"] = "hostile"
            entry["expected_codes"] = sorted(HOSTILE_BUILDERS[name][1])
        manifest["fixtures"][name] = entry

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
        assert entry["purpose"], f"{name}: manifest purpose must be non-empty"


# ---------------------------------------------------------------------------
# (17) Golden fixtures validate clean + determinism proof.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(GOLDEN_BUILDERS))
def test_golden_fixture_validates_clean(name):
    record = _load_fixture(name)
    findings = validate_hypothesis(record)
    assert findings == [], f"{name}: expected zero findings, got {findings}"


@pytest.mark.parametrize("name", sorted(GOLDEN_BUILDERS))
def test_golden_fixture_is_byte_identical_to_regenerated_output(name):
    """Determinism proof: compose_hypothesis(same inputs) -> byte-identical JSON."""

    committed = FIXTURE_DIR / f"{name}.json"
    regenerated = _dump(GOLDEN_BUILDERS[name]())
    assert regenerated == committed.read_text(encoding="utf-8"), (
        f"{name}: compose_hypothesis is not deterministic against its own committed fixture"
    )


def test_golden_supported_hypothesis_has_all_three_graph_states_present_or_supported():
    record = _load_fixture("golden_supported_hypothesis")
    assert record["graph_states"] == {"graph_1": "supported", "graph_2": "present", "graph_3": "present"}
    assert record["hypothesis_state"] == "supported_hypothesis"
    assert record["abstention"] == {"abstained": False, "reasons": []}


def test_golden_typed_abstentions_carry_no_semantic_inference():
    unresolved = _load_fixture("golden_typed_abstention_unresolved")
    assert unresolved["abstention"]["abstained"] is True
    assert unresolved["abstention"]["reasons"] == ["unresolved_identity"]
    assert unresolved["relationship_paths"] == []
    assert unresolved["generator_admissions"] == []
    assert unresolved["mechanism"]["state"] == "abstained"

    rights_blocked = _load_fixture("golden_typed_abstention_rights_blocked")
    assert rights_blocked["graph_states"]["graph_1"] == "rights_blocked_only"
    assert rights_blocked["abstention"]["reasons"] == ["rights_blocked"]


# ---------------------------------------------------------------------------
# Manifest-driven hostile kill test (item 17: expected_codes subset-match).
# ---------------------------------------------------------------------------


def test_manifest_driven_fixture_kills():
    manifest = _load_manifest()
    for name, entry in manifest["fixtures"].items():
        record = _load_fixture(name)
        findings = validate_hypothesis(record)
        codes = _codes(findings)
        expected = set(entry["expected_codes"])
        if entry["kind"] == "golden":
            assert findings == [], f"{name}: golden fixture must validate with zero findings, got {findings}"
        else:
            assert expected.issubset(codes), f"{name}: expected {expected} subset of {sorted(codes)}"


_HOSTILE_CASES = [(name, codes) for name, (_builder, codes) in sorted(HOSTILE_BUILDERS.items())]


@pytest.mark.parametrize("name,expected", _HOSTILE_CASES)
def test_hostile_fixture_kills_with_expected_code(name, expected):
    record = _load_fixture(name)
    codes = _codes(validate_hypothesis(record))
    for code in expected:
        assert code in codes, f"{name}: expected {code} in findings, got {sorted(codes)}"


# ---------------------------------------------------------------------------
# (1) NOT_IN_MASTER identity gate.
# ---------------------------------------------------------------------------


def test_r010_unresolved_identity_with_abstained_false():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_unresolved_identity_laundered")))
    assert "K3D_R010" in codes


def test_r011_unresolved_identity_carrying_evidence_legs():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_unresolved_identity_laundered")))
    assert "K3D_R011" in codes


def test_compose_raises_when_unresolved_target_carries_legs():
    unresolved = _identity(state="UNRESOLVED", issuer=None, security=None)
    with pytest.raises(EconomicPropagationError):
        compose_hypothesis(
            source_event=_source_event(event_id="evt-raise-1", resolution=unresolved),
            target=_target(requested_key="RAISE1", resolution=unresolved),
            asof=ASOF, compiled_at=COMPILED_AT,
            generator_admissions=[_admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier")],
            relationship_paths=[_g1_leg()], similarity_evidence=[], market_evidence=[],
            mechanism_proposal=None, alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
        )


# ---------------------------------------------------------------------------
# (2)/(3) Graph 2 / Graph 3 constructs laundered as Graph-1 legs.
# ---------------------------------------------------------------------------


def test_r032_theme_membership_or_curated_peer_set_in_relationship_paths():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_relationship_construct_laundering")))
    assert "K3D_R032" in codes


def test_compose_raises_for_graph2_construct_in_relationship_paths():
    with pytest.raises(EconomicPropagationError):
        compose_hypothesis(
            source_event=_source_event(event_id="evt-raise-2"),
            target=_target(requested_key="RAISE2"),
            asof=ASOF, compiled_at=COMPILED_AT,
            generator_admissions=[_admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier")],
            relationship_paths=[_g1_leg(construct="theme_membership", role="role_unknown",
                                         role_evidence_class="none", claim_strength="candidate")],
            similarity_evidence=[], market_evidence=[],
            mechanism_proposal=None, alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
        )


def test_r032_earnings_sympathy_or_residual_comovement_in_relationship_paths():
    # Same fixture also plants the graph_3-construct-in-graph_1 variant.
    record = _load_fixture("hostile_relationship_construct_laundering")
    constructs = {leg["construct"] for leg in record["relationship_paths"]}
    assert "residual_comovement" in constructs
    codes = _codes(validate_hypothesis(record))
    assert "K3D_R032" in codes


# ---------------------------------------------------------------------------
# (4) Role laundering.
# ---------------------------------------------------------------------------


def test_r031_role_supplier_with_agreement_role_unknown_evidence_class():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_role_laundering")))
    assert "K3D_R031" in codes


def test_r031_disclosed_agreement_role_unknown_construct_with_named_role():
    # The construct disclosed_agreement_role_unknown can only carry
    # role=role_unknown; claiming customer/supplier on it is R031 too.
    rec = copy.deepcopy(_base_min())
    rec["relationship_paths"] = [
        _g1_leg(leg_id="g1_role_bad2", construct="disclosed_agreement_role_unknown", role="customer",
                role_evidence_class="strongly_evidenced_role", claim_strength="candidate"),
    ]
    rec = _rehash(rec)
    codes = _codes(validate_hypothesis(rec))
    assert "K3D_R031" in codes


# ---------------------------------------------------------------------------
# (5) Generator refusal row.
# ---------------------------------------------------------------------------


def test_r021_peer_participation_breadth_admission_is_refused():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_generator_refusal_admission")))
    assert "K3D_R021" in codes


def test_compose_raises_for_generator_refusal_row_with_refusal_message():
    with pytest.raises(EconomicPropagationError, match="refusal row"):
        compose_hypothesis(
            source_event=_source_event(event_id="evt-raise-5"),
            target=_target(requested_key="RAISE5"),
            asof=ASOF, compiled_at=COMPILED_AT,
            generator_admissions=[_admission("gen_peer_participation_breadth", "graph_3", "peer_participation_breadth")],
            relationship_paths=[], similarity_evidence=[], market_evidence=[],
            mechanism_proposal=None, alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
        )


# ---------------------------------------------------------------------------
# (6) Forbidden scalar-authority keys.
# ---------------------------------------------------------------------------


def test_r071_forbidden_key_injected_into_composed_record():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_forbidden_key_injection")))
    assert "K3D_R071" in codes
    # K3D_R001 (schema additionalProperties:false) is an acceptable, expected
    # cascade -- the commission explicitly allows it for this attack.


def test_compose_refuses_input_parts_carrying_forbidden_keys():
    poisoned_source_event = _source_event(event_id="evt-raise-6")
    poisoned_source_event["confidence_note"] = "high"
    with pytest.raises(EconomicPropagationError, match="forbidden scalar-authority key"):
        compose_hypothesis(
            source_event=poisoned_source_event,
            target=_target(requested_key="RAISE6"),
            asof=ASOF, compiled_at=COMPILED_AT,
            generator_admissions=[_admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier")],
            relationship_paths=[_g1_leg()], similarity_evidence=[], market_evidence=[],
            mechanism_proposal=None, alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
        )


# ---------------------------------------------------------------------------
# (7) economic_share reserved-null.
# ---------------------------------------------------------------------------


def test_r072_economic_share_non_null():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_economic_share_nonnull")))
    assert "K3D_R072" in codes


# ---------------------------------------------------------------------------
# (8) Clocks: lookahead + unparseable.
# ---------------------------------------------------------------------------


def test_r061_leg_known_at_after_record_asof():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_clock_violations")))
    assert "K3D_R061" in codes


def test_r060_leg_clock_unparseable():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_clock_violations")))
    assert "K3D_R060" in codes


# ---------------------------------------------------------------------------
# (9) Non-usable evidence counted toward a supported graph_1 claim.
# ---------------------------------------------------------------------------


def test_r051_and_r063_rights_blocked_leg_counted_as_supported():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_rights_blocked_claimed_supported")))
    assert "K3D_R051" in codes
    assert "K3D_R063" in codes


# ---------------------------------------------------------------------------
# (10) Mechanism without a supporting Graph-1 relationship.
# ---------------------------------------------------------------------------


def test_r042_mechanism_hypothesized_with_empty_relationship_paths():
    record = _load_fixture("hostile_mechanism_without_relationship")
    assert record["relationship_paths"] == []
    codes = _codes(validate_hypothesis(record))
    assert "K3D_R042" in codes


def test_compose_raises_for_mechanism_without_supported_graph1():
    with pytest.raises(EconomicPropagationError):
        compose_hypothesis(
            source_event=_source_event(event_id="evt-raise-10"),
            target=_target(requested_key="RAISE10"),
            asof=ASOF, compiled_at=COMPILED_AT,
            generator_admissions=[_admission("gen_theme_membership", "graph_2", "theme_membership")],
            relationship_paths=[], similarity_evidence=[_g2_leg()], market_evidence=[],
            mechanism_proposal=_mechanism_proposal(),
            alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
        )


# ---------------------------------------------------------------------------
# (11) Determinism + stale-hash detection.
# ---------------------------------------------------------------------------


def test_compose_hypothesis_is_deterministic_byte_identical():
    kwargs = dict(
        source_event=_source_event(),
        target=_target(),
        asof=ASOF, compiled_at=COMPILED_AT,
        generator_admissions=[_admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier")],
        relationship_paths=[_g1_leg()],
        similarity_evidence=[_g2_leg()],
        market_evidence=[_g3_leg()],
        mechanism_proposal=_mechanism_proposal(),
        alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
    )
    r1 = compose_hypothesis(**kwargs)
    r2 = compose_hypothesis(**kwargs)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
    assert r1["record_id"] == r2["record_id"]
    assert r1["content_sha256"] == r2["content_sha256"]


def test_r081_content_sha256_mismatch_when_tampered_without_rehash():
    record = _load_fixture("hostile_sha_mismatch")
    stale_hash = record["content_sha256"]
    recomputed = content_sha256(record)
    assert stale_hash != recomputed, "fixture must actually be stale for this test to mean anything"
    codes = _codes(validate_hypothesis(record))
    assert "K3D_R081" in codes


# ---------------------------------------------------------------------------
# (12) Binding kills: const list + cross-artifact presence.
# ---------------------------------------------------------------------------


def test_r001_binding_kills_list_tampered():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_binding_kills_drop")))
    assert "K3D_R001" in codes


def test_binding_kills_present_in_schema_registry_and_lib():
    schema = load_hypothesis_schema()
    registry = load_generator_registry()
    assert set(schema["properties"]["binding_kills"]["const"]) == BINDING_KILLS_EXPECTED
    assert set(registry["binding_kills"].keys()) == BINDING_KILLS_EXPECTED
    assert set(BINDING_KILLS) == BINDING_KILLS_EXPECTED


# ---------------------------------------------------------------------------
# (13) Authority const + trade-language mechanism prose.
# ---------------------------------------------------------------------------


def test_r070_authority_trading_true():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_authority_trading_true")))
    assert "K3D_R070" in codes


def test_r041_trade_language_in_mechanism_hypothesis_text():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_mechanism_trade_language")))
    assert "K3D_R041" in codes


def test_compose_raises_for_trade_language_in_mechanism_prose():
    with pytest.raises(EconomicPropagationError):
        compose_hypothesis(
            source_event=_source_event(event_id="evt-raise-13"),
            target=_target(requested_key="RAISE13"),
            asof=ASOF, compiled_at=COMPILED_AT,
            generator_admissions=[_admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier")],
            relationship_paths=[_g1_leg()], similarity_evidence=[], market_evidence=[],
            mechanism_proposal=_mechanism_proposal(text="We see upside toward a new price target as Beta captures share."),
            alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
        )


# ---------------------------------------------------------------------------
# (14) Caller-authored derived fields (graph_states/hypothesis_state/abstention).
# ---------------------------------------------------------------------------


def test_r051_r052_r053_caller_authored_summary_disagrees_with_derivation():
    codes = _codes(validate_hypothesis(_load_fixture("hostile_disagreeing_derived_summary")))
    assert "K3D_R051" in codes
    assert "K3D_R052" in codes
    assert "K3D_R053" in codes


def test_compose_refuses_input_part_carrying_a_derived_field():
    poisoned_source_event = _source_event(event_id="evt-raise-14")
    poisoned_source_event["graph_states"] = {"graph_1": "supported", "graph_2": "absent", "graph_3": "absent"}
    with pytest.raises(EconomicPropagationError, match="derived/authority field"):
        compose_hypothesis(
            source_event=poisoned_source_event,
            target=_target(requested_key="RAISE14"),
            asof=ASOF, compiled_at=COMPILED_AT,
            generator_admissions=[_admission("gen_disclosed_customer_supplier", "graph_1", "disclosed_customer_supplier")],
            relationship_paths=[_g1_leg()], similarity_evidence=[], market_evidence=[],
            mechanism_proposal=None, alternatives=_ALTERNATIVES, falsifiers=_FALSIFIERS, expiry=_EXPIRY,
        )


# ---------------------------------------------------------------------------
# (15) Registry/schema alignment.
# ---------------------------------------------------------------------------


def test_construct_vocabulary_matches_schema_construct_enum():
    schema = load_hypothesis_schema()
    registry = load_generator_registry()
    schema_constructs = set(schema["$defs"]["construct"]["enum"])
    registry_constructs = set(registry["construct_vocabulary"].keys())
    assert schema_constructs == registry_constructs


def test_every_generator_row_construct_is_in_vocabulary_with_matching_graph():
    registry = load_generator_registry()
    vocabulary = registry["construct_vocabulary"]
    for row in registry["generators"]:
        construct = row["construct"]
        assert construct in vocabulary, f"generator {row['generator_id']} construct {construct!r} not in construct_vocabulary"
        assert vocabulary[construct] == row["graph"], (
            f"generator {row['generator_id']}: vocabulary says {construct!r} is {vocabulary[construct]!r}, "
            f"row claims graph {row['graph']!r}"
        )


def test_exactly_one_refusal_row_and_it_is_peer_participation_breadth():
    registry = load_generator_registry()
    refusals = [row["generator_id"] for row in registry["generators"] if not row.get("admits_target", False)]
    assert refusals == ["gen_peer_participation_breadth"]


# ---------------------------------------------------------------------------
# (16) No-store law: this module is a pure in-memory view/join executor.
# ---------------------------------------------------------------------------


def test_lib_module_performs_no_writes():
    source = LIB_SOURCE_PATH.read_text(encoding="utf-8")
    forbidden_snippets = [
        ".write_text(", ".write_bytes(", "open(", "mkdir(", "to_parquet", "to_csv", "shutil", "os.makedirs",
    ]
    for snippet in forbidden_snippets:
        assert snippet not in source, f"lib/economic_propagation.py contains a write-shaped call: {snippet!r}"


# ---------------------------------------------------------------------------
# (17) json.tool sanity + round-trip proof on every committed fixture.
# ---------------------------------------------------------------------------


def test_every_fixture_and_manifest_parse_as_json_tool_would():
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(GOLDEN_BUILDERS))
def test_compose_output_round_trips_through_validate_with_zero_findings(name):
    record = GOLDEN_BUILDERS[name]()
    assert validate_hypothesis(record) == []
