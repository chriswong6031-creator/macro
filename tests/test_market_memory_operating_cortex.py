"""W5A frozen synthetic/private Operating Cortex conformance."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from decimal import ROUND_DOWN, Inexact, getcontext, setcontext
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from engine.neuralweb import market_memory_forward as forward
from engine.neuralweb import market_memory_operating_cortex as cortex
from tests.test_market_memory_retrieval import _record

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "market_memory"
QUERY_COORDINATES = {
    "alpha": "0.000000000000000000",
    "beta": "0.000000000000000000",
}

REGISTRATION_FIELDS = {
    "schema",
    "operating_cortex_registration_id",
    "registration_key",
    "registered_at",
    "retrieval_registration_id",
    "trial_registration_id",
    "trial_plan_sha256",
    "required_evidence_kinds",
    "salience_policy",
    "citation_policy",
    "read_tools",
    "bounds",
    "implementation",
    "input_profile",
    "claims",
    "emission_enabled",
    "authority",
}
PACKET_FIELDS = {
    "schema",
    "operating_cortex_packet_id",
    "operating_cortex_registration_id",
    "retrieval_registration_id",
    "episodic_retrieval_record_id",
    "trial_registration_id",
    "subject",
    "produced_at",
    "episode_scope",
    "evidence_manifest",
    "attention_queue",
    "contradictions",
    "missingness",
    "falsifier_audit",
    "citation_projection",
    "unsupported_claim_scorecard",
    "attention_quality_scorecard",
    "read_tools",
    "coverage",
    "input_profile",
    "claims",
    "emission_enabled",
    "authority",
}
EVIDENCE_FIELDS = {
    "evidence_card_id",
    "episode_role",
    "episode_forecast_id",
    "subject",
    "evidence_kind",
    "claim_key",
    "stance",
    "known_at",
    "salience_components",
    "citation",
}
CITATION_FIELDS = {
    "citation_id",
    "source_record_ref",
    "source_sha256",
    "source_bytes",
    "span_start_byte",
    "span_end_byte",
    "span_sha256",
    "known_at",
}
CLAIM_FIELDS = {
    "claim_id",
    "subject",
    "claim_key",
    "stance",
    "evidence_card_refs",
    "falsifier_code",
}
EXPECTED_READ_TOOLS = [
    "read_attention_queue",
    "read_citation_projection",
    "read_contradictions",
    "read_episode_scope",
    "read_falsifier_audit",
    "read_missingness",
    "read_scorecards",
]
EXPECTED_BOUNDS = {
    "max_registration_bytes": 262_144,
    "max_packet_bytes": 2_097_152,
    "max_source_bytes": 65_536,
    "max_aggregate_source_bytes": 4_194_304,
    "max_evidence_cards": 64,
    "max_claims": 128,
    "max_evidence_card_refs": 8,
    "max_evidence_kinds": 16,
    "max_contradictions": 128,
    "max_episodes": 33,
    "max_string_bytes": 256,
    "max_depth": 16,
    "max_nodes": 16_384,
}
EXPECTED_CLAIMS = {
    "operational_input_authenticated": False,
    "evidence_population_complete": False,
    "salience_component_provenance_authenticated": False,
    "citation_semantic_entailment_evaluated": False,
    "unsupported_claim_truth_evaluated": False,
    "attention_quality_evaluated": False,
    "learned_synthesis_performed": False,
    "hypotheses_generated": False,
    "forecast_input_eligible": False,
    "aggregate_eligible": False,
    "skill_claim_eligible": False,
    "prophet_input_eligible": False,
}


def _registry() -> Registry:
    registry = Registry()
    for path in SCHEMA_DIR.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def _validate_schema(name: str, value: dict[str, Any]) -> None:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator(
        schema,
        registry=_registry(),
        format_checker=FormatChecker(),
    ).validate(value)


def _content_id(prefix: str, value: dict[str, Any], field: str) -> str:
    core = copy.deepcopy(value)
    core[field] = ""
    return prefix + hashlib.sha256(forward.canonical_json_bytes(core)).hexdigest()


def _rehash(value: dict[str, Any], *, field: str, prefix: str) -> None:
    value[field] = _content_id(prefix, value, field)


def _components(value: str | None = "1.000000000000000000") -> dict[str, str | None]:
    return {name: value for name in cortex.SALIENCE_WEIGHTS}


def _evidence_input(
    *,
    episode_role: str,
    episode_id: str,
    subject: dict[str, str],
    evidence_kind: str,
    claim_key: str,
    stance: str,
    known_at: str,
    source_ref: str,
    source: bytes,
    components: dict[str, str | None] | None = None,
    span_start: int = 0,
    span_end: int = 5,
) -> dict[str, Any]:
    citation = {
        "citation_id": "",
        "source_record_ref": source_ref,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_bytes": len(source),
        "span_start_byte": span_start,
        "span_end_byte": span_end,
        "span_sha256": hashlib.sha256(source[span_start:span_end]).hexdigest(),
        "known_at": known_at,
    }
    _rehash(citation, field="citation_id", prefix="mmcitation_")
    card = {
        "evidence_card_id": "",
        "episode_role": episode_role,
        "episode_forecast_id": episode_id,
        "subject": copy.deepcopy(subject),
        "evidence_kind": evidence_kind,
        "claim_key": claim_key,
        "stance": stance,
        "known_at": known_at,
        "salience_components": components or _components(),
        "citation": citation,
    }
    _rehash(card, field="evidence_card_id", prefix="mmevidencecard_")
    return {"evidence_card": card, "exact_source_bytes": source}


def _claim(
    *,
    subject: dict[str, str],
    claim_key: str,
    stance: str,
    evidence_card_refs: list[str],
    falsifier_code: str | None = None,
) -> dict[str, Any]:
    row = {
        "claim_id": "",
        "subject": copy.deepcopy(subject),
        "claim_key": claim_key,
        "stance": stance,
        "evidence_card_refs": sorted(evidence_card_refs),
        "falsifier_code": falsifier_code,
    }
    _rehash(row, field="claim_id", prefix="mmclaim_")
    return row


def _fixture() -> dict[str, Any]:
    record, retrieval_registration, trial, query, candidates = _record()
    registration = cortex.build_operating_cortex_registration(
        retrieval_registration=retrieval_registration,
        trial_registration=trial,
        registration_key="synthetic.cortex.v1",
        registered_at="2026-08-01T19:00:00.000000Z",
        required_evidence_kinds=["macro_fact", "technical_fact"],
        producer_code_sha256="a" * 64,
        producer_config_sha256="b" * 64,
    )
    subject = record["query"]["subject"]
    query_id = record["query"]["forecast_id"]
    analogue_id = record["selected_forecast_ids"][0]
    half = _components("0.500000000000000000")
    close = _components("0.510000000000000000")
    three_quarters = _components("0.750000000000000000")
    quarter = _components("0.250000000000000000")
    missing = _components("0.250000000000000000")
    missing["standardized_surprise"] = None
    evidence_inputs = [
        _evidence_input(
            episode_role="query",
            episode_id=query_id,
            subject=subject,
            evidence_kind="macro_fact",
            claim_key="inflation.pressure",
            stance="supports",
            known_at="2026-08-27T19:00:00.000000Z",
            source_ref="source.alpha.macro",
            source=b"buy signal language is allowed in exact cited source bytes",
            components=close,
        ),
        _evidence_input(
            episode_role="query",
            episode_id=query_id,
            subject=subject,
            evidence_kind="technical_fact",
            claim_key="inflation.pressure",
            stance="supports",
            known_at="2026-08-27T19:01:00.000000Z",
            source_ref="source.alpha.technical",
            source=b"technical source beta",
            components=half,
        ),
        _evidence_input(
            episode_role="query",
            episode_id=query_id,
            subject=subject,
            evidence_kind="macro_fact",
            claim_key="inflation.pressure",
            stance="challenges",
            known_at="2026-08-27T19:02:00.000000Z",
            source_ref="source.alpha.challenge.macro",
            source=b"macro challenge gamma",
            components=three_quarters,
        ),
        _evidence_input(
            episode_role="query",
            episode_id=query_id,
            subject=subject,
            evidence_kind="technical_fact",
            claim_key="inflation.pressure",
            stance="challenges",
            known_at="2026-08-27T19:03:00.000000Z",
            source_ref="source.alpha.challenge.technical",
            source=b"technical challenge delta",
            components=missing,
        ),
        _evidence_input(
            episode_role="analogue",
            episode_id=analogue_id,
            subject=subject,
            evidence_kind="macro_fact",
            claim_key="growth.pulse",
            stance="neutral",
            known_at="2026-08-17T19:00:00.000000Z",
            source_ref="source.growth.macro",
            source=b"analogue macro epsilon",
            components=quarter,
        ),
        _evidence_input(
            episode_role="query",
            episode_id=query_id,
            subject=subject,
            evidence_kind="technical_fact",
            claim_key="growth.pulse",
            stance="neutral",
            known_at="2026-08-27T19:04:00.000000Z",
            source_ref="source.growth.technical",
            source=b"query technical zeta",
            components=quarter,
        ),
    ]
    cards = [row["evidence_card"] for row in evidence_inputs]
    by = {
        (
            row["claim_key"],
            row["stance"],
            row["evidence_kind"],
            row["episode_role"],
        ): row["evidence_card_id"]
        for row in cards
    }
    claims = [
        _claim(
            subject=subject,
            claim_key="inflation.pressure",
            stance="supports",
            evidence_card_refs=[
                by[("inflation.pressure", "supports", "macro_fact", "query")],
                by[("inflation.pressure", "supports", "technical_fact", "query")],
            ],
            falsifier_code="data_reversal",
        ),
        _claim(
            subject=subject,
            claim_key="inflation.pressure",
            stance="challenges",
            evidence_card_refs=[
                by[("inflation.pressure", "challenges", "macro_fact", "query")],
                by[("inflation.pressure", "challenges", "technical_fact", "query")],
            ],
        ),
        _claim(
            subject=subject,
            claim_key="inflation.pressure",
            stance="supports",
            evidence_card_refs=[
                by[("inflation.pressure", "supports", "macro_fact", "query")]
            ],
        ),
        _claim(
            subject=subject,
            claim_key="inflation.pressure",
            stance="neutral",
            evidence_card_refs=[],
        ),
        _claim(
            subject=subject,
            claim_key="inflation.pressure",
            stance="neutral",
            evidence_card_refs=[
                by[("growth.pulse", "neutral", "macro_fact", "analogue")],
                by[("growth.pulse", "neutral", "technical_fact", "query")],
            ],
        ),
    ]
    build_kwargs = {
        "operating_cortex_registration": registration,
        "retrieval_registration": retrieval_registration,
        "trial_registration": trial,
        "episodic_retrieval_record": record,
        "query_state_snapshot": query["state_snapshot"],
        "query_forecast_record": query["forecast_record"],
        "query_exact_context_bytes": query["exact_context_bytes"],
        "query_coordinates": QUERY_COORDINATES,
        "candidate_inputs": candidates,
        "evidence_inputs": evidence_inputs,
        "claim_cards": claims,
        "produced_at": "2026-08-29T00:00:00.000000Z",
    }
    packet = cortex.build_operating_cortex_packet(**build_kwargs)
    join_kwargs = {
        key: value for key, value in build_kwargs.items() if key != "produced_at"
    }
    return {
        "packet": packet,
        "registration": registration,
        "retrieval_registration": retrieval_registration,
        "trial": trial,
        "record": record,
        "query": query,
        "candidates": candidates,
        "evidence_inputs": evidence_inputs,
        "claims": claims,
        "build_kwargs": build_kwargs,
        "join_kwargs": join_kwargs,
    }


def test_frozen_top_level_and_row_matrices_are_exact_and_schema_valid() -> None:
    fixture = _fixture()
    registration = fixture["registration"]
    packet = fixture["packet"]

    assert set(registration) == REGISTRATION_FIELDS
    assert set(packet) == PACKET_FIELDS
    assert set(packet["evidence_manifest"][0]) == EVIDENCE_FIELDS
    assert set(packet["evidence_manifest"][0]["citation"]) == CITATION_FIELDS
    assert set(packet["attention_queue"][0]) == {
        "attention_item_id",
        "evidence_card_id",
        "status",
        "reason",
        "salience_score_q18",
    }
    assert set(packet["contradictions"][0]) == {
        "contradiction_group_id",
        "subject",
        "claim_key",
        "supporting_claim_ids",
        "challenging_claim_ids",
        "status",
    }
    assert set(packet["missingness"][0]) == {"evidence_kind", "status", "scope"}
    assert set(packet["falsifier_audit"][0]) == {
        "claim_id",
        "falsifier_code",
        "status",
        "generation_performed",
    }
    assert set(packet["citation_projection"][0]) == CLAIM_FIELDS | {
        "status",
        "withholding_reason",
        "citation_ids",
        "semantic_entailment_evaluated",
    }
    assert set(packet["unsupported_claim_scorecard"]) == {
        "status",
        "total",
        "included",
        "withheld",
        "counts_by_reason",
        "structural_unsupported_rate_q18",
    }
    assert registration["read_tools"] == EXPECTED_READ_TOOLS
    assert packet["read_tools"] == EXPECTED_READ_TOOLS
    assert list(cortex.READ_TOOLS) == EXPECTED_READ_TOOLS
    assert registration["bounds"] == EXPECTED_BOUNDS
    assert dict(cortex.BOUNDS) == EXPECTED_BOUNDS
    assert registration["citation_policy"] == {
        "byte_closure": "source_sha256_length_and_half_open_span_sha256",
        "semantic_entailment": "not_evaluated",
        "withholding_precedence": [
            "evidence_reference_missing",
            "evidence_reference_mismatch",
            "required_evidence_kind_missing",
            "semantic_entailment_not_evaluated",
        ],
    }
    _validate_schema("operating_cortex_registration.v1.schema.json", registration)
    _validate_schema("operating_cortex_packet.v1.schema.json", packet)


def test_registration_closes_exact_w4_w2_ids_plan_and_freeze_window() -> None:
    fixture = _fixture()
    registration = fixture["registration"]
    retrieval_registration = fixture["retrieval_registration"]

    assert (
        registration["retrieval_registration_id"]
        == retrieval_registration["retrieval_registration_id"]
    )
    assert (
        registration["trial_registration_id"]
        == retrieval_registration["trial_registration_id"]
    )
    assert (
        registration["trial_plan_sha256"] == retrieval_registration["trial_plan_sha256"]
    )
    common = {
        "retrieval_registration": retrieval_registration,
        "trial_registration": fixture["trial"],
        "registration_key": "synthetic.cortex.v1",
        "required_evidence_kinds": ["macro_fact"],
        "producer_code_sha256": "a" * 64,
        "producer_config_sha256": "b" * 64,
    }
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="precede"
    ):
        cortex.build_operating_cortex_registration(
            **common, registered_at="2026-08-01T17:59:59.999999Z"
        )
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="before"):
        cortex.build_operating_cortex_registration(
            **common, registered_at="2026-08-02T00:00:00.000000Z"
        )


def test_exact_claims_coverage_authority_and_emission_are_honest() -> None:
    fixture = _fixture()
    for value in (fixture["registration"], fixture["packet"]):
        assert value["claims"] == EXPECTED_CLAIMS
        assert not any(value["claims"].values())
        assert value["authority"] == dict(forward.AUTHORITY)
        assert value["emission_enabled"] is False
        assert value["input_profile"] == "synthetic_fixture_only"
    assert dict(cortex.CLAIMS) == EXPECTED_CLAIMS
    assert fixture["packet"]["coverage"] == {
        "w4_exact_join_validated": True,
        "citation_byte_closure_validated": True,
        "evidence_population_complete": False,
        "citation_semantic_entailment_evaluated": False,
        "attention_quality_evaluated": False,
    }


def test_source_span_citation_evidence_claim_and_packet_ids_are_content_addressed() -> (
    None
):
    fixture = _fixture()
    registration = fixture["registration"]
    assert registration["operating_cortex_registration_id"] == _content_id(
        "mmcortexregistration_",
        registration,
        "operating_cortex_registration_id",
    )
    packet = fixture["packet"]
    source_by_ref = {
        row["evidence_card"]["citation"]["source_record_ref"]: row["exact_source_bytes"]
        for row in fixture["evidence_inputs"]
    }
    for card in packet["evidence_manifest"]:
        citation = card["citation"]
        source = source_by_ref[citation["source_record_ref"]]
        assert citation["source_sha256"] == hashlib.sha256(source).hexdigest()
        assert citation["source_bytes"] == len(source)
        assert (
            citation["span_sha256"]
            == hashlib.sha256(
                source[citation["span_start_byte"] : citation["span_end_byte"]]
            ).hexdigest()
        )
        assert citation["citation_id"] == _content_id(
            "mmcitation_", citation, "citation_id"
        )
        assert card["evidence_card_id"] == _content_id(
            "mmevidencecard_", card, "evidence_card_id"
        )
    for projection in packet["citation_projection"]:
        claim = {key: projection[key] for key in CLAIM_FIELDS}
        assert claim["claim_id"] == _content_id("mmclaim_", claim, "claim_id")
    for item in packet["attention_queue"]:
        assert item["attention_item_id"] == _content_id(
            "mmattentionitem_", item, "attention_item_id"
        )
    assert packet["operating_cortex_packet_id"] == _content_id(
        "mmcortexpacket_", packet, "operating_cortex_packet_id"
    )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (
            lambda f: f["build_kwargs"]["evidence_inputs"][0][
                "evidence_card"
            ].__setitem__("evidence_card_id", "mmevidencecard_" + "f" * 64),
            "evidence_card_id",
        ),
        (
            lambda f: f["build_kwargs"]["evidence_inputs"][0]["evidence_card"][
                "citation"
            ].__setitem__("citation_id", "mmcitation_" + "f" * 64),
            "citation_id",
        ),
        (
            lambda f: f["build_kwargs"]["claim_cards"][0].__setitem__(
                "claim_id", "mmclaim_" + "f" * 64
            ),
            "claim_id",
        ),
        (
            lambda f: f["build_kwargs"]["evidence_inputs"][0]["evidence_card"][
                "citation"
            ].__setitem__("source_sha256", "f" * 64),
            "source_sha256",
        ),
        (
            lambda f: f["build_kwargs"]["evidence_inputs"][0]["evidence_card"][
                "citation"
            ].__setitem__("source_bytes", 1),
            "source_bytes",
        ),
        (
            lambda f: f["build_kwargs"]["evidence_inputs"][0]["evidence_card"][
                "citation"
            ].__setitem__("span_sha256", "f" * 64),
            "span_sha256",
        ),
    ],
)
def test_opaque_identity_and_source_span_forgery_fail_closed(
    mutation, match: str
) -> None:
    fixture = _fixture()
    mutation(fixture)
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match=match):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


def test_exact_w4_subject_episode_role_known_at_and_produced_time_fail_closed() -> None:
    fixture = _fixture()
    card = fixture["build_kwargs"]["evidence_inputs"][0]["evidence_card"]
    card["subject"]["subject_id"] = "other"
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="subject"
    ):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["evidence_inputs"][0]["evidence_card"]["episode_role"] = (
        "analogue"
    )
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="role"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    card = fixture["build_kwargs"]["evidence_inputs"][0]["evidence_card"]
    card["known_at"] = "2026-08-28T00:00:00.000000Z"
    card["citation"]["known_at"] = card["known_at"]
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="decision cutoff"
    ):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["produced_at"] = "2026-08-27T23:59:59.999999Z"
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="retrieval"
    ):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


def test_episode_scope_is_exact_query_then_w4_selected_analogues() -> None:
    fixture = _fixture()
    packet = fixture["packet"]
    record = fixture["record"]
    assert [row["episode_role"] for row in packet["episode_scope"]] == [
        "query",
        "analogue",
        "analogue",
        "analogue",
    ]
    assert [row["episode_forecast_id"] for row in packet["episode_scope"]] == [
        record["query"]["forecast_id"],
        *record["selected_forecast_ids"],
    ]
    assert all(
        row["subject"] == record["query"]["subject"] for row in packet["episode_scope"]
    )


def test_frozen_salience_names_weights_one_final_q18_and_missing_abstention() -> None:
    fixture = _fixture()
    registration = fixture["registration"]
    queue = fixture["packet"]["attention_queue"]
    assert registration["salience_policy"]["weights"] == {
        "standardized_surprise": "0.250000000000000000",
        "change_hazard": "0.200000000000000000",
        "novelty": "0.150000000000000000",
        "disagreement": "0.150000000000000000",
        "materiality": "0.150000000000000000",
        "data_health_deficit": "0.100000000000000000",
    }
    assert registration["salience_policy"]["components"] == [
        "standardized_surprise",
        "change_hazard",
        "novelty",
        "disagreement",
        "materiality",
        "data_health_deficit",
    ]
    assert registration["salience_policy"]["missing_component"] == "abstain"
    assert (
        registration["salience_policy"]["ordering"]
        == "score_desc_then_evidence_card_id_then_abstained_evidence_card_id"
    )
    assert (
        registration["salience_policy"]["numeric_convention"]
        == "decimal64_half_even_one_final_q18/v1"
    )
    scored = [row for row in queue if row["status"] == "scored"]
    assert [row["salience_score_q18"] for row in scored] == sorted(
        (row["salience_score_q18"] for row in scored), reverse=True
    )
    abstained = [row for row in queue if row["status"] == "abstained"]
    assert len(abstained) == 1
    assert abstained[0]["reason"] == "missing_salience_component"
    assert abstained[0]["salience_score_q18"] is None


@pytest.mark.parametrize(
    ("surprise", "expected"),
    [
        ("0.000000000000000002", "0.000000000000000000"),
        ("0.000000000000000006", "0.000000000000000002"),
    ],
)
def test_salience_uses_one_final_half_even_quantization(
    surprise: str, expected: str
) -> None:
    fixture = _fixture()
    target = fixture["build_kwargs"]["evidence_inputs"][0]["evidence_card"]
    target["salience_components"] = _components("0.000000000000000000")
    target["salience_components"]["standardized_surprise"] = surprise
    target["evidence_card_id"] = ""
    packet = cortex.build_operating_cortex_packet(**fixture["build_kwargs"])
    new_id = next(
        card["evidence_card_id"]
        for card in packet["evidence_manifest"]
        if card["citation"]["source_record_ref"] == "source.alpha.macro"
    )
    row = next(
        item for item in packet["attention_queue"] if item["evidence_card_id"] == new_id
    )
    assert row["salience_score_q18"] == expected


def test_global_decimal_precision_rounding_flags_and_traps_cannot_change_packet() -> (
    None
):
    fixture = _fixture()
    baseline = fixture["packet"]
    original = getcontext().copy()
    try:
        getcontext().prec = 1
        getcontext().rounding = ROUND_DOWN
        getcontext().traps[Inexact] = True
        hostile = cortex.build_operating_cortex_packet(**fixture["build_kwargs"])
    finally:
        setcontext(original)
    assert hostile == baseline
    queue = hostile["attention_queue"]
    by_source = {
        card["citation"]["source_record_ref"]: card["evidence_card_id"]
        for card in hostile["evidence_manifest"]
    }
    ids = [row["evidence_card_id"] for row in queue]
    assert ids.index(by_source["source.alpha.macro"]) < ids.index(
        by_source["source.alpha.technical"]
    )


def test_contradictions_are_derived_from_exact_subject_claim_key_and_claim_stance() -> (
    None
):
    fixture = _fixture()
    rows = fixture["packet"]["contradictions"]
    assert len(rows) == 1
    row = rows[0]
    assert row["subject"] == fixture["record"]["query"]["subject"]
    assert row["claim_key"] == "inflation.pressure"
    assert row["status"] == "structural_conflict"
    claims = {claim["claim_id"]: claim for claim in fixture["claims"]}
    assert all(
        claims[item]["stance"] == "supports" for item in row["supporting_claim_ids"]
    )
    assert all(
        claims[item]["stance"] == "challenges" for item in row["challenging_claim_ids"]
    )
    assert row["contradiction_group_id"] == _content_id(
        "mmcontradictiongroup_", row, "contradiction_group_id"
    )


def test_missingness_is_structural_and_bounded_to_required_kinds() -> None:
    rows = _fixture()["packet"]["missingness"]
    assert rows == [
        {
            "evidence_kind": "macro_fact",
            "status": "present",
            "scope": "supplied_evidence_manifest_only",
        },
        {
            "evidence_kind": "technical_fact",
            "status": "present",
            "scope": "supplied_evidence_manifest_only",
        },
    ]


def test_falsifiers_are_registered_or_absent_but_never_generated() -> None:
    fixture = _fixture()
    rows = {row["claim_id"]: row for row in fixture["packet"]["falsifier_audit"]}
    registered = next(claim for claim in fixture["claims"] if claim["falsifier_code"])
    assert rows[registered["claim_id"]] == {
        "claim_id": registered["claim_id"],
        "falsifier_code": "data_reversal",
        "status": "registered",
        "generation_performed": False,
    }
    assert all(row["generation_performed"] is False for row in rows.values())
    assert all(
        row["status"] == ("registered" if row["falsifier_code"] else "not_registered")
        for row in rows.values()
    )


def test_citation_projection_pins_structural_precedence_and_semantic_withholding() -> (
    None
):
    fixture = _fixture()
    rows = fixture["packet"]["citation_projection"]
    by_shape = {
        (row["stance"], len(row["evidence_card_refs"]), row["falsifier_code"]): row
        for row in rows
    }
    included = [row for row in rows if row["status"] == "included_structural_only"]
    assert len(included) == 2
    assert all(
        row["withholding_reason"] == "semantic_entailment_not_evaluated"
        and row["semantic_entailment_evaluated"] is False
        and len(row["citation_ids"]) == 2
        for row in included
    )
    zero = by_shape[("neutral", 0, None)]
    assert zero["status"] == "withheld"
    assert zero["withholding_reason"] == "evidence_reference_missing"
    missing_kind = next(
        row
        for row in rows
        if row["status"] == "withheld" and len(row["evidence_card_refs"]) == 1
    )
    assert missing_kind["withholding_reason"] == "required_evidence_kind_missing"
    mismatch = next(
        row
        for row in rows
        if row["status"] == "withheld" and len(row["evidence_card_refs"]) == 2
    )
    assert mismatch["withholding_reason"] == "evidence_reference_mismatch"
    assert all(not row["citation_ids"] for row in rows if row["status"] == "withheld")


def test_claim_references_must_close_exact_subject_claim_key_and_stance() -> None:
    fixture = _fixture()
    claim = next(
        row
        for row in fixture["claims"]
        if row["stance"] == "supports" and len(row["evidence_card_refs"]) == 2
    )
    claim["stance"] = "neutral"
    claim["claim_id"] = ""
    fixture["build_kwargs"]["claim_cards"] = [claim]
    packet = cortex.build_operating_cortex_packet(**fixture["build_kwargs"])
    assert (
        packet["citation_projection"][0]["withholding_reason"]
        == "evidence_reference_mismatch"
    )


def test_structural_unsupported_scorecard_and_attention_quality_are_exact() -> None:
    packet = _fixture()["packet"]
    assert packet["unsupported_claim_scorecard"] == {
        "status": "structural_only",
        "total": 5,
        "included": 2,
        "withheld": 3,
        "counts_by_reason": {
            "evidence_reference_missing": 1,
            "evidence_reference_mismatch": 1,
            "required_evidence_kind_missing": 1,
        },
        "structural_unsupported_rate_q18": "0.600000000000000000",
    }
    assert packet["attention_quality_scorecard"] == {
        "status": "not_evaluated",
        "reason": "no_preregistered_attention_outcomes",
        "graded_items": 0,
        "precision_q18": None,
        "recall_q18": None,
        "false_positive_rate_q18": None,
        "ndcg_q18": None,
    }


def test_zero_claims_has_null_rate_and_zero_evidence_refs_are_accepted() -> None:
    fixture = _fixture()
    fixture["build_kwargs"]["claim_cards"] = []
    packet = cortex.build_operating_cortex_packet(**fixture["build_kwargs"])
    score = packet["unsupported_claim_scorecard"]
    assert score["total"] == score["included"] == score["withheld"] == 0
    assert score["structural_unsupported_rate_q18"] is None
    assert packet["citation_projection"] == []

    fixture = _fixture()
    fixture["build_kwargs"]["claim_cards"] = [
        claim for claim in fixture["claims"] if not claim["evidence_card_refs"]
    ]
    packet = cortex.build_operating_cortex_packet(**fixture["build_kwargs"])
    assert (
        packet["citation_projection"][0]["withholding_reason"]
        == "evidence_reference_missing"
    )


@pytest.mark.parametrize(
    "token",
    [
        "buy_signal",
        "buySignal",
        "buyingSignal",
        "buyingsignal",
        "BuySignal",
        "authority",
        "authoritytoken",
        "permissions",
        "proposal_weight",
        "safeProposalWeightV1",
        "may_rank",
        "maybuy",
        "maysell",
        "mayhold",
        "mayforecast",
        "maypromote",
        "mayrecommend",
        "rankingGate",
        "rankinggate",
        "rankingsignal",
        "executeNow",
        "executenow",
        "forecastsignal",
        "promotion_eligible",
        "promotioncandidate",
        "prophetinput",
        "outcomeFree",
        "recommendationEngine",
        "sellingsignal",
        "tradingsignal",
        "mayTrainProphet",
        "permissiontoken",
        "signalbuy",
        "tokenauthority",
        "candidatepromotion",
        "inputprophet",
        "contextforecast",
        "nowexecute",
        "maybuyv2",
        "buyv2",
        "authorityv2",
        "tradev2",
        "a.ction",
        "auth.ority",
        "tr-ade",
        "forecastingSignal",
        "executingNow",
        "promotingCandidate",
        "recommends",
        "ranks",
        "sizes",
        "trains",
        "ｂｕｙｉｎｇＳｉｇｎａｌ",
    ],
)
def test_action_and_authority_morphology_is_rejected_from_caller_codes(
    token: str,
) -> None:
    fixture = _fixture()
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="forbidden"
    ):
        cortex.build_operating_cortex_registration(
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
            registration_key=token,
            registered_at="2026-08-01T19:00:00.000000Z",
            required_evidence_kinds=["macro_fact"],
            producer_code_sha256="a" * 64,
            producer_config_sha256="b" * 64,
        )


def test_every_forbidden_word_rejects_versions_and_intra_token_splits() -> None:
    for word in sorted(cortex._FORBIDDEN_WORDS):
        variants = [f"{word}v2"]
        variants.extend(
            f"{word[:index]}.{word[index:]}" for index in range(1, len(word))
        )
        for variant in variants:
            with pytest.raises(
                cortex.MarketMemoryOperatingCortexContractError, match="forbidden"
            ):
                cortex._opaque(variant, field="hostile")


def test_morphology_applies_to_source_refs_kinds_claim_keys_and_falsifier_codes() -> (
    None
):
    for path, value in [
        (
            ("evidence_inputs", 0, "evidence_card", "citation", "source_record_ref"),
            "mayRank",
        ),
        (("evidence_inputs", 0, "evidence_card", "evidence_kind"), "tradeSignal"),
        (("evidence_inputs", 0, "evidence_card", "claim_key"), "forecast_context"),
        (("claim_cards", 0, "falsifier_code"), "promotionEligible"),
    ]:
        fixture = _fixture()
        target: Any = fixture["build_kwargs"]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(
            cortex.MarketMemoryOperatingCortexContractError, match="forbidden"
        ):
            cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


@pytest.mark.parametrize(
    "registration_key",
    [
        "constraint.audit.v1",
        "aggregate",
        "aggregate.signal.audit",
        "classification",
        "classification.signal.audit",
        "buyer",
        "buyer.profile.v1",
        "executioner",
        "executioner.nowcast.v1",
        "prophetic",
        "prophetic.context.audit",
    ],
)
def test_morphology_does_not_reject_safe_substring_only_codes(
    registration_key: str,
) -> None:
    fixture = _fixture()
    registration = cortex.build_operating_cortex_registration(
        retrieval_registration=fixture["retrieval_registration"],
        trial_registration=fixture["trial"],
        registration_key=registration_key,
        registered_at="2026-08-01T19:00:00.000000Z",
        required_evidence_kinds=["macro_fact"],
        producer_code_sha256="a" * 64,
        producer_config_sha256="b" * 64,
    )
    assert registration["registration_key"] == registration_key


def test_exact_source_bytes_may_contain_action_words_without_gaining_authority() -> (
    None
):
    fixture = _fixture()
    wrapper = fixture["build_kwargs"]["evidence_inputs"][0]
    source = b"buySignal authority may_rank executeNow proposal_weight outcomeFree"
    wrapper["exact_source_bytes"] = source
    citation = wrapper["evidence_card"]["citation"]
    citation.update(
        {
            "citation_id": "",
            "source_sha256": "",
            "source_bytes": 0,
            "span_start_byte": 0,
            "span_end_byte": 9,
            "span_sha256": "",
        }
    )
    wrapper["evidence_card"]["evidence_card_id"] = ""
    packet = cortex.build_operating_cortex_packet(**fixture["build_kwargs"])
    assert packet["authority"] == dict(forward.AUTHORITY)
    assert not any(packet["claims"].values())


def test_structural_schemas_reject_action_outcome_and_unknown_fields() -> None:
    fixture = _fixture()
    packet = copy.deepcopy(fixture["packet"])
    packet["action"] = "none"
    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_packet.v1.schema.json", packet)
    card = copy.deepcopy(fixture["packet"]["evidence_manifest"][0])
    card["outcome"] = "none"
    schema = json.loads(
        (SCHEMA_DIR / "operating_cortex_packet.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, registry=_registry())
    errors = list(
        validator.iter_errors({**fixture["packet"], "evidence_manifest": [card]})
    )
    assert errors


def test_duplicate_and_unused_exact_source_wrappers_fail_closed() -> None:
    fixture = _fixture()
    second = fixture["build_kwargs"]["evidence_inputs"][1]["evidence_card"]
    first = fixture["build_kwargs"]["evidence_inputs"][0]["evidence_card"]
    second["citation"]["source_record_ref"] = first["citation"]["source_record_ref"]
    second["citation"]["citation_id"] = ""
    second["evidence_card_id"] = ""
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="duplicate"
    ):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["evidence_inputs"][0]["unused_source"] = b"orphan"
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="extra"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


def test_strict_loaders_reject_duplicate_nonfinite_and_oversize_json() -> None:
    fixture = _fixture()
    packet_body = forward.canonical_json_bytes(fixture["packet"])
    registration_body = forward.canonical_json_bytes(fixture["registration"])
    assert (
        cortex.load_operating_cortex_packet_join_json(
            packet_body, **fixture["join_kwargs"]
        )
        == fixture["packet"]
    )
    assert (
        cortex.load_operating_cortex_registration_join_json(
            registration_body,
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
        )
        == fixture["registration"]
    )
    duplicate = packet_body.replace(b'"authority":', b'"authority":{},"authority":', 1)
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="duplicate"
    ):
        cortex.load_operating_cortex_packet_join_json(
            duplicate, **fixture["join_kwargs"]
        )
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="non-finite"
    ):
        cortex.load_operating_cortex_registration_join_json(
            b'{"x":NaN}',
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
        )
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="byte bound"
    ):
        cortex.load_operating_cortex_registration_join_json(
            b"{" + b" " * 262_144,
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
        )
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="byte bound"
    ):
        cortex.load_operating_cortex_packet_join_json(
            b"{" + b" " * 2_097_152, **fixture["join_kwargs"]
        )


def test_lone_surrogates_fail_as_contract_errors_in_validators_and_loaders() -> None:
    fixture = _fixture()
    registration = fixture["registration"]
    registration["registration_key"] = "\ud800"
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="surrogate"
    ):
        cortex.validate_operating_cortex_registration_record(registration)
    registration_body = json.dumps(
        registration, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="surrogate"
    ):
        cortex.load_operating_cortex_registration_join_json(
            registration_body,
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
        )

    fixture = _fixture()
    packet = fixture["packet"]
    packet["coverage"]["\ud800"] = False
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="surrogate"
    ):
        cortex.validate_operating_cortex_packet(packet)
    packet_body = json.dumps(
        packet, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="surrogate"
    ):
        cortex.load_operating_cortex_packet_join_json(
            packet_body, **fixture["join_kwargs"]
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda p: p["attention_queue"][0].__setitem__(
            "salience_score_q18", "0.000000000000000000"
        ),
        lambda p: p["unsupported_claim_scorecard"].__setitem__("withheld", 0),
        lambda p: p["coverage"].__setitem__("evidence_population_complete", True),
        lambda p: p["claims"].__setitem__("attention_quality_evaluated", True),
        lambda p: p["citation_projection"][0].__setitem__(
            "semantic_entailment_evaluated", True
        ),
    ],
)
def test_self_validator_rejects_rehashed_derived_claim_coverage_forgery(
    mutator,
) -> None:
    packet = _fixture()["packet"]
    mutator(packet)
    _rehash(packet, field="operating_cortex_packet_id", prefix="mmcortexpacket_")
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError):
        cortex.validate_operating_cortex_packet(packet)


@pytest.mark.parametrize(
    ("section", "field", "integer"),
    [
        ("claims", "attention_quality_evaluated", 0),
        ("coverage", "evidence_population_complete", 0),
        ("coverage", "w4_exact_join_validated", 1),
    ],
)
def test_packet_boolean_blocks_reject_fully_rehashed_integer_aliases(
    section: str, field: str, integer: int
) -> None:
    fixture = _fixture()
    packet = fixture["packet"]
    packet[section][field] = integer
    _rehash(packet, field="operating_cortex_packet_id", prefix="mmcortexpacket_")

    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_packet.v1.schema.json", packet)
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError):
        cortex.validate_operating_cortex_packet(packet)


def test_registration_claims_reject_fully_rehashed_integer_boolean_alias() -> None:
    fixture = _fixture()
    registration = fixture["registration"]
    registration["claims"]["attention_quality_evaluated"] = 0
    _rehash(
        registration,
        field="operating_cortex_registration_id",
        prefix="mmcortexregistration_",
    )

    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_registration.v1.schema.json", registration)
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError):
        cortex.validate_operating_cortex_registration_record(registration)


@pytest.mark.parametrize(
    ("path", "malformed", "match"),
    [
        (("episode_scope", 0, "episode_role"), ["query"], "episode_role"),
        (
            ("evidence_manifest", 0, "episode_role"),
            ["query"],
            "episode_role",
        ),
        (
            ("evidence_manifest", 0, "citation", "source_sha256"),
            ["a" * 64],
            "source_sha256",
        ),
        (
            ("evidence_manifest", 0, "citation", "source_bytes"),
            [1],
            "source_bytes",
        ),
        (
            ("evidence_manifest", 0, "citation", "span_sha256"),
            ["a" * 64],
            "span_sha256",
        ),
        (
            ("evidence_manifest", 0, "citation", "citation_id"),
            ["mmcitation_" + "a" * 64],
            "citation_id",
        ),
        (
            ("evidence_manifest", 0, "evidence_card_id"),
            ["mmevidencecard_" + "a" * 64],
            "evidence_card_id",
        ),
    ],
)
def test_list_shaped_identity_fields_fail_as_contract_errors_in_validator_and_loader(
    path: tuple[str | int, ...], malformed: list[Any], match: str
) -> None:
    fixture = _fixture()
    packet = fixture["packet"]
    target: Any = packet
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = malformed

    if path[:2] == ("evidence_manifest", 0):
        card = packet["evidence_manifest"][0]
        if path[2] == "citation":
            citation = card["citation"]
            if path[-1] != "citation_id":
                _rehash(citation, field="citation_id", prefix="mmcitation_")
        if path[-1] != "evidence_card_id":
            _rehash(card, field="evidence_card_id", prefix="mmevidencecard_")
    _rehash(packet, field="operating_cortex_packet_id", prefix="mmcortexpacket_")

    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_packet.v1.schema.json", packet)
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match=match):
        cortex.validate_operating_cortex_packet(packet)
    body = forward.canonical_json_bytes(packet)
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match=match):
        cortex.load_operating_cortex_packet_join_json(body, **fixture["join_kwargs"])


@pytest.mark.parametrize(
    ("path", "malformed", "match"),
    [
        (("episode_role",), ["query"], "episode_role"),
        (("citation", "source_sha256"), ["a" * 64], "source_sha256"),
        (("citation", "source_bytes"), [1], "source_bytes"),
        (("citation", "span_sha256"), ["a" * 64], "span_sha256"),
        (
            ("citation", "citation_id"),
            ["mmcitation_" + "a" * 64],
            "citation_id",
        ),
        (
            ("evidence_card_id",),
            ["mmevidencecard_" + "a" * 64],
            "evidence_card_id",
        ),
    ],
)
def test_list_shaped_evidence_input_fields_fail_as_contract_errors_in_builder(
    path: tuple[str, ...], malformed: list[Any], match: str
) -> None:
    fixture = _fixture()
    card = fixture["build_kwargs"]["evidence_inputs"][0]["evidence_card"]
    target: Any = card
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = malformed

    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match=match):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


def test_join_rejects_fully_rehashed_source_span_and_dependency_forgery() -> None:
    fixture = _fixture()
    alternative_kwargs = copy.deepcopy(fixture["build_kwargs"])
    wrapper = alternative_kwargs["evidence_inputs"][0]
    card = wrapper["evidence_card"]
    old_evidence_id = card["evidence_card_id"]
    source = b"forged source bytes with an internally valid identity"
    wrapper["exact_source_bytes"] = source
    citation = card["citation"]
    citation["source_sha256"] = hashlib.sha256(source).hexdigest()
    citation["source_bytes"] = len(source)
    citation["span_sha256"] = hashlib.sha256(
        source[citation["span_start_byte"] : citation["span_end_byte"]]
    ).hexdigest()
    _rehash(citation, field="citation_id", prefix="mmcitation_")
    _rehash(card, field="evidence_card_id", prefix="mmevidencecard_")
    for claim in alternative_kwargs["claim_cards"]:
        claim["evidence_card_refs"] = sorted(
            card["evidence_card_id"] if ref == old_evidence_id else ref
            for ref in claim["evidence_card_refs"]
        )
        claim["claim_id"] = ""
    alternative = cortex.build_operating_cortex_packet(**alternative_kwargs)
    assert cortex.validate_operating_cortex_packet(alternative) == alternative
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError):
        cortex.validate_operating_cortex_packet_join(
            alternative, **fixture["join_kwargs"]
        )

    fixture = _fixture()
    fixture["build_kwargs"]["episodic_retrieval_record"]["counts"][
        "supplied_candidates"
    ] = 99
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="W4A"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


def test_registration_join_rejects_rehashed_trial_plan_or_owner_forgery() -> None:
    fixture = _fixture()
    registration = fixture["registration"]
    registration["trial_plan_sha256"] = "f" * 64
    _rehash(
        registration,
        field="operating_cortex_registration_id",
        prefix="mmcortexregistration_",
    )
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="trial-plan"
    ):
        cortex.validate_operating_cortex_registration_join(
            registration,
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
        )


def test_canonical_time_q18_span_reference_and_source_bounds_fail_closed() -> None:
    fixture = _fixture()
    fixture["build_kwargs"]["produced_at"] = "2026-08-29T00:00:00Z"
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="canonical"
    ):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    card = fixture["build_kwargs"]["evidence_inputs"][0]["evidence_card"]
    card["salience_components"]["novelty"] = "NaN"
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    citation = fixture["build_kwargs"]["evidence_inputs"][0]["evidence_card"][
        "citation"
    ]
    citation["span_start_byte"] = 1
    citation["span_end_byte"] = 1
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="non-empty"
    ):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["evidence_inputs"][0]["exact_source_bytes"] = b"x" * 65_537
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="64 KiB"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    claim = fixture["build_kwargs"]["claim_cards"][0]
    claim["evidence_card_refs"] = [
        "mmevidencecard_" + f"{index:064x}" for index in range(9)
    ]
    claim["claim_id"] = ""
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="0..8"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


def test_packet_and_registration_schema_reject_wrong_q18_extra_and_authority() -> None:
    fixture = _fixture()
    registration = copy.deepcopy(fixture["registration"])
    registration["salience_policy"]["weights"]["novelty"] = "0.15"
    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_registration.v1.schema.json", registration)
    packet = copy.deepcopy(fixture["packet"])
    packet["authority"]["may_rank"] = True
    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_packet.v1.schema.json", packet)
    packet = copy.deepcopy(fixture["packet"])
    packet["evidence_manifest"][0]["extra"] = 1
    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_packet.v1.schema.json", packet)
    packet = copy.deepcopy(fixture["packet"])
    packet["attention_queue"][0]["status"] = "abstained"
    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_packet.v1.schema.json", packet)
    packet = copy.deepcopy(fixture["packet"])
    included = next(
        row
        for row in packet["citation_projection"]
        if row["status"] == "included_structural_only"
    )
    included["withholding_reason"] = "evidence_reference_missing"
    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_packet.v1.schema.json", packet)


def test_reader_is_detached_immutable_seven_view_and_has_no_generic_field_access() -> (
    None
):
    fixture = _fixture()
    reader = cortex.OperatingCortexReader(fixture["packet"], **fixture["join_kwargs"])

    assert reader.read_attention_queue() == fixture["packet"]["attention_queue"]
    assert reader.read_episode_scope() == fixture["packet"]["episode_scope"]
    assert reader.read_contradictions() == fixture["packet"]["contradictions"]
    assert reader.read_missingness() == fixture["packet"]["missingness"]
    assert reader.read_falsifier_audit() == fixture["packet"]["falsifier_audit"]
    assert reader.read_citation_projection() == fixture["packet"]["citation_projection"]
    assert reader.read_scorecards() == {
        "unsupported_claim_scorecard": fixture["packet"]["unsupported_claim_scorecard"],
        "attention_quality_scorecard": fixture["packet"]["attention_quality_scorecard"],
    }
    detached = reader.read_attention_queue()
    detached.clear()
    assert reader.read_attention_queue()
    assert not hasattr(reader, "_read")
    assert not hasattr(reader, "packet")
    with pytest.raises(AttributeError):
        reader.packet = fixture["packet"]
    backing = reader._OperatingCortexReader__attention_queue
    assert type(backing) is bytes
    with pytest.raises(AttributeError):
        reader._OperatingCortexReader__attention_queue = b"[]"
    with pytest.raises(AttributeError):
        del reader._OperatingCortexReader__sealed
    with pytest.raises(AttributeError):
        del reader._OperatingCortexReader__attention_queue
    with pytest.raises(AttributeError):
        reader._OperatingCortexReader__attention_queue = b"[]"
    assert reader.read_attention_queue() == fixture["packet"]["attention_queue"]
    public = {
        name
        for name, member in inspect.getmembers(cortex.OperatingCortexReader)
        if callable(member) and not name.startswith("_")
    }
    assert public == set(cortex.READ_TOOLS)


def test_module_is_pure_and_has_no_llm_filesystem_network_clock_or_write_capability() -> (
    None
):
    path = Path(cortex.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert imports <= {
        "__future__",
        "copy",
        "hashlib",
        "json",
        "re",
        "unicodedata",
        "collections.abc",
        "datetime",
        "decimal",
        "types",
        "typing",
        "engine.neuralweb",
    }
    assert not (
        calls
        & {
            "open",
            "write",
            "write_text",
            "write_bytes",
            "request",
            "urlopen",
            "connect",
            "socket",
            "run",
            "Popen",
            "system",
            "now",
            "utcnow",
        }
    )


def test_resource_depth_node_string_evidence_claim_and_kind_bounds_fail_closed() -> (
    None
):
    fixture = _fixture()
    registration = copy.deepcopy(fixture["registration"])
    nested: Any = "leaf"
    for _ in range(18):
        nested = {"x": nested}
    registration["implementation"]["producer_config_sha256"] = nested
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="depth"):
        cortex.validate_operating_cortex_registration_record(registration)

    fixture = _fixture()
    packet = copy.deepcopy(fixture["packet"])
    packet["coverage"]["extra"] = [0] * 16_384
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="nodes"):
        cortex.validate_operating_cortex_packet(packet)

    fixture = _fixture()
    registration = copy.deepcopy(fixture["registration"])
    registration["registration_key"] = "x" * 257
    _rehash(
        registration,
        field="operating_cortex_registration_id",
        prefix="mmcortexregistration_",
    )
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="256 bytes"
    ):
        cortex.validate_operating_cortex_registration_record(registration)

    fixture = _fixture()
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="UTF-8 byte bound"
    ):
        cortex.build_operating_cortex_registration(
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
            registration_key="x" * 4096,
            registered_at="2026-08-01T19:00:00.000000Z",
            required_evidence_kinds=["macro_fact"],
            producer_code_sha256="a" * 64,
            producer_config_sha256="b" * 64,
        )

    fixture = _fixture()
    fixture["build_kwargs"]["evidence_inputs"] = fixture["evidence_inputs"] * 11
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="64"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["claim_cards"] = fixture["claims"] * 26
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="128"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="16"):
        cortex.build_operating_cortex_registration(
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
            registration_key="synthetic.cortex.v1",
            registered_at="2026-08-01T19:00:00.000000Z",
            required_evidence_kinds=[f"kind.{index:02d}" for index in range(17)],
            producer_code_sha256="a" * 64,
            producer_config_sha256="b" * 64,
        )
