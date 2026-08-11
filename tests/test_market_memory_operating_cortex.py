"""W5A synthetic/private Operating Cortex conformance."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
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


def _rehash(value: dict[str, Any], *, field: str, prefix: str) -> None:
    core = copy.deepcopy(value)
    core[field] = ""
    value[field] = (
        prefix + hashlib.sha256(forward.canonical_json_bytes(core)).hexdigest()
    )


def _components(value: str | None = "1.000000000000000000") -> dict[str, str | None]:
    return {name: value for name in cortex.SALIENCE_WEIGHTS}


def _card(
    *,
    evidence_id: str,
    episode_id: str,
    kind: str,
    source_id: str,
    source: bytes,
    stance: str = "neutral",
    group: str | None = None,
    components: dict[str, str | None] | None = None,
    citations: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "episode_forecast_id": episode_id,
        "evidence_kind": kind,
        "source_id": source_id,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "citations": citations
        if citations is not None
        else [{"byte_start": 0, "byte_end": 5}],
        "stance": stance,
        "contradiction_group_id": group,
        "salience_components": components or _components(),
    }


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
    query_id = record["query"]["forecast_id"]
    selected_id = record["selected_forecast_ids"][0]
    sources = {
        "src.a": b"macro datum alpha",
        "src.b": b"technical datum beta",
        "src.c": b"macro datum gamma",
        "src.d": b"technical datum delta",
    }
    half = _components("0.500000000000000000")
    missing = _components("0.250000000000000000")
    missing["freshness"] = None
    evidence = [
        _card(
            evidence_id="ev.a",
            episode_id=query_id,
            kind="macro_fact",
            source_id="src.a",
            source=sources["src.a"],
            stance="supports",
            group="group.a",
        ),
        _card(
            evidence_id="ev.b",
            episode_id=query_id,
            kind="technical_fact",
            source_id="src.b",
            source=sources["src.b"],
            stance="challenges",
            group="group.a",
            components=half,
        ),
        _card(
            evidence_id="ev.c",
            episode_id=selected_id,
            kind="macro_fact",
            source_id="src.c",
            source=sources["src.c"],
            components=missing,
        ),
        _card(
            evidence_id="ev.d",
            episode_id=query_id,
            kind="macro_fact",
            source_id="src.d",
            source=sources["src.d"],
            citations=[],
        ),
    ]
    claims = [
        {
            "claim_id": "claim.a",
            "episode_forecast_id": query_id,
            "evidence_ids": ["ev.a", "ev.b"],
            "required_evidence_kinds": ["macro_fact", "technical_fact"],
            "falsifier_evidence_ids": ["ev.b"],
        },
        {
            "claim_id": "claim.b",
            "episode_forecast_id": query_id,
            "evidence_ids": ["ev.a"],
            "required_evidence_kinds": ["macro_fact", "technical_fact"],
            "falsifier_evidence_ids": [],
        },
        {
            "claim_id": "claim.c",
            "episode_forecast_id": query_id,
            "evidence_ids": ["ev.d"],
            "required_evidence_kinds": ["macro_fact"],
            "falsifier_evidence_ids": [],
        },
        {
            "claim_id": "claim.d",
            "episode_forecast_id": query_id,
            "evidence_ids": ["ev.a"],
            "required_evidence_kinds": ["macro_fact"],
            "falsifier_evidence_ids": ["ev.z"],
        },
        {
            "claim_id": "claim.e",
            "episode_forecast_id": query_id,
            "evidence_ids": ["ev.z"],
            "required_evidence_kinds": ["macro_fact"],
            "falsifier_evidence_ids": [],
        },
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
        "evidence_cards": evidence,
        "exact_source_bytes": sources,
        "claim_inputs": claims,
        "assembled_at": "2026-08-29T00:00:00.000000Z",
    }
    packet = cortex.build_operating_cortex_packet(**build_kwargs)
    join_kwargs = {
        key: value
        for key, value in build_kwargs.items()
        if key not in {"evidence_cards", "claim_inputs", "assembled_at"}
    }
    return {
        "packet": packet,
        "registration": registration,
        "retrieval_registration": retrieval_registration,
        "trial": trial,
        "record": record,
        "query": query,
        "candidates": candidates,
        "sources": sources,
        "evidence": evidence,
        "claims": claims,
        "build_kwargs": build_kwargs,
        "join_kwargs": join_kwargs,
    }


def test_registration_and_packet_are_schema_valid_content_addressed_and_zero_authority() -> (
    None
):
    fixture = _fixture()
    registration = fixture["registration"]
    packet = fixture["packet"]

    assert registration["salience_policy"]["weights"] == dict(cortex.SALIENCE_WEIGHTS)
    assert registration["input_profile"] == "synthetic_fixture_only"
    assert packet["input_profile"] == "synthetic_fixture_only"
    assert not any(registration["claims"].values())
    assert not any(packet["claims"].values())
    assert registration["authority"] == dict(forward.AUTHORITY)
    assert packet["authority"] == dict(forward.AUTHORITY)
    assert registration["emission_enabled"] is False
    assert packet["emission_enabled"] is False
    _validate_schema("operating_cortex_registration.v1.schema.json", registration)
    _validate_schema("operating_cortex_packet.v1.schema.json", packet)


def test_registration_is_frozen_after_w4_and_before_w2_live_forward() -> None:
    fixture = _fixture()
    common = {
        "retrieval_registration": fixture["retrieval_registration"],
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


def test_schemas_fail_closed_on_authority_q18_and_extra_field_forgery() -> None:
    fixture = _fixture()
    registration = copy.deepcopy(fixture["registration"])
    registration["claims"]["attention_quality_evaluated"] = True
    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_registration.v1.schema.json", registration)

    packet = copy.deepcopy(fixture["packet"])
    packet["evidence_cards"][0]["salience_components"]["freshness"] = (
        "1.500000000000000000"
    )
    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_packet.v1.schema.json", packet)

    packet = copy.deepcopy(fixture["packet"])
    packet["unexpected"] = False
    with pytest.raises(ValidationError):
        _validate_schema("operating_cortex_packet.v1.schema.json", packet)


def test_packet_revalidates_complete_w4_join_before_processing_evidence() -> None:
    fixture = _fixture()
    kwargs = copy.deepcopy(fixture["build_kwargs"])
    kwargs["episodic_retrieval_record"]["counts"]["supplied_candidates"] = 99
    kwargs["exact_source_bytes"] = {"src.a": b"buy"}

    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="W4A"):
        cortex.build_operating_cortex_packet(**kwargs)


def test_salience_uses_six_frozen_weights_one_final_q18_and_abstains_on_missing() -> (
    None
):
    packet = _fixture()["packet"]
    queue = packet["attention_queue"]

    assert [row["evidence_id"] for row in queue] == ["ev.a", "ev.d", "ev.b", "ev.c"]
    assert [row["salience_score"] for row in queue] == [
        "1.000000000000000000",
        "1.000000000000000000",
        "0.500000000000000000",
        None,
    ]
    assert queue[-1]["status"] == "abstained"
    assert queue[-1]["reason"] == "missing_salience_component"


def test_salience_mixed_components_matches_exact_frozen_weight_sum() -> None:
    fixture = _fixture()
    components = {
        "freshness": "1.000000000000000000",
        "source_quality": "0.500000000000000000",
        "episode_relevance": "0.000000000000000000",
        "contradiction_relevance": "1.000000000000000000",
        "missingness_relevance": "0.000000000000000000",
        "falsifier_relevance": "0.500000000000000000",
    }
    fixture["build_kwargs"]["evidence_cards"][0]["salience_components"] = components
    packet = cortex.build_operating_cortex_packet(**fixture["build_kwargs"])
    row = next(
        item for item in packet["attention_queue"] if item["evidence_id"] == "ev.a"
    )
    assert row["salience_score"] == "0.550000000000000000"


@pytest.mark.parametrize(
    ("freshness", "expected"),
    [
        ("0.000000000000000002", "0.000000000000000000"),
        ("0.000000000000000006", "0.000000000000000002"),
    ],
)
def test_salience_one_final_quantization_is_half_even(
    freshness: str, expected: str
) -> None:
    fixture = _fixture()
    components = _components("0.000000000000000000")
    components["freshness"] = freshness
    fixture["build_kwargs"]["evidence_cards"][0]["salience_components"] = components
    packet = cortex.build_operating_cortex_packet(**fixture["build_kwargs"])
    row = next(
        item for item in packet["attention_queue"] if item["evidence_id"] == "ev.a"
    )
    assert row["salience_score"] == expected


def test_structural_contradiction_and_required_kind_missingness_are_bounded_to_inputs() -> (
    None
):
    fixture = _fixture()
    packet = fixture["packet"]

    assert packet["contradictions"] == [
        {
            "contradiction_group_id": "group.a",
            "supports_evidence_ids": ["ev.a"],
            "challenges_evidence_ids": ["ev.b"],
            "status": "structural_conflict",
        }
    ]
    missingness = {row["episode_forecast_id"]: row for row in packet["missingness"]}
    query_id = fixture["record"]["query"]["forecast_id"]
    selected_id = fixture["record"]["selected_forecast_ids"][0]
    assert missingness[query_id]["missing_required_evidence_kinds"] == []
    assert missingness[selected_id]["missing_required_evidence_kinds"] == [
        "technical_fact"
    ]
    assert all(
        row["scope"] == "supplied_synthetic_evidence_only"
        for row in missingness.values()
    )


def test_falsifiers_are_audited_but_never_generated() -> None:
    rows = {row["claim_id"]: row for row in _fixture()["packet"]["falsifier_audit"]}

    assert rows["claim.a"]["status"] == "complete"
    assert rows["claim.b"]["status"] == "not_registered"
    assert rows["claim.d"]["status"] == "incomplete"
    assert rows["claim.d"]["missing_falsifier_evidence_ids"] == ["ev.z"]
    assert all(row["generation"] == "never_generated" for row in rows.values())


def test_citation_projection_is_byte_closed_not_entailment_and_withholding_is_deterministic() -> (
    None
):
    packet = _fixture()["packet"]
    rows = {row["claim_id"]: row for row in packet["citation_projection"]}

    assert rows["claim.a"]["status"] == "available"
    assert len(rows["claim.a"]["citation_refs"]) == 2
    assert rows["claim.a"]["entailment"] == "not_evaluated"
    assert rows["claim.b"]["withholding_reason"] == "required_evidence_kind_missing"
    assert rows["claim.c"]["withholding_reason"] == "citation_not_closed"
    assert rows["claim.d"]["withholding_reason"] == "falsifier_reference_missing"
    assert rows["claim.e"]["withholding_reason"] == "evidence_reference_missing"
    assert all(
        not row["citation_refs"] for row in rows.values() if row["status"] == "withheld"
    )


def test_scorecards_report_only_structural_unsupported_rate_and_no_attention_quality() -> (
    None
):
    scorecards = _fixture()["packet"]["scorecards"]

    assert scorecards["structural_unsupported_rate"] == {
        "status": "computed",
        "value_decimal": "0.800000000000000000",
        "numerator": 4,
        "denominator": 5,
        "scope": "supplied_synthetic_claims_only",
    }
    assert scorecards["attention_quality"] == {
        "status": "not_evaluated",
        "value": None,
        "reason": "no_labeled_attention_outcomes",
    }


def test_empty_claims_abstain_structural_rate_without_inventing_quality() -> None:
    fixture = _fixture()
    fixture["build_kwargs"]["claim_inputs"] = []
    packet = cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    assert packet["scorecards"]["structural_unsupported_rate"]["status"] == "abstained"
    assert packet["scorecards"]["structural_unsupported_rate"]["value_decimal"] is None
    assert packet["scorecards"]["attention_quality"]["status"] == "not_evaluated"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda fixture: fixture["build_kwargs"]["evidence_cards"][0][
            "salience_components"
        ].__setitem__("freshness", "0.1"),
        lambda fixture: fixture["build_kwargs"]["evidence_cards"][0][
            "salience_components"
        ].__setitem__("freshness", float("nan")),
        lambda fixture: fixture["build_kwargs"]["evidence_cards"][0].__setitem__(
            "episode_forecast_id", "mmforecast_" + "0" * 64
        ),
        lambda fixture: fixture["build_kwargs"]["evidence_cards"][0]["citations"][
            0
        ].update({"byte_start": 5, "byte_end": 5}),
        lambda fixture: fixture["build_kwargs"]["evidence_cards"].reverse(),
        lambda fixture: fixture["build_kwargs"]["claim_inputs"].reverse(),
    ],
)
def test_hostile_evidence_decimal_scope_span_and_order_inputs_fail_closed(
    mutation,
) -> None:
    fixture = _fixture()
    mutation(fixture)
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


@pytest.mark.parametrize(
    "body", [b"buy now", b"profits", b"bearish datum", b"p&l datum", b"actions"]
)
def test_forbidden_semantic_token_family_is_rejected_from_source_bytes(
    body: bytes,
) -> None:
    fixture = _fixture()
    fixture["build_kwargs"]["exact_source_bytes"]["src.a"] = body
    fixture["build_kwargs"]["evidence_cards"][0]["source_sha256"] = hashlib.sha256(
        body
    ).hexdigest()
    fixture["build_kwargs"]["evidence_cards"][0]["citations"] = [
        {"byte_start": 0, "byte_end": min(3, len(body))}
    ]

    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="forbidden"
    ):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


def test_exact_source_hash_bytes_and_aggregate_bounds_fail_closed() -> None:
    fixture = _fixture()
    fixture["build_kwargs"]["exact_source_bytes"]["src.a"] = b"macro datum changed"
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="hash"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["exact_source_bytes"]["src.a"] = b"x" * (64 * 1024 + 1)
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="64 KiB"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["exact_source_bytes"]["src.unused"] = b"unused datum"
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="every and only"
    ):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


def test_self_validator_rejects_rehashed_projection_score_and_claim_forgery() -> None:
    packet = _fixture()["packet"]
    packet["attention_queue"][0]["salience_score"] = "0.000000000000000000"
    _rehash(packet, field="operating_cortex_packet_id", prefix="mmcortexpacket_")
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="attention"
    ):
        cortex.validate_operating_cortex_packet(packet)

    packet = _fixture()["packet"]
    packet["scorecards"]["structural_unsupported_rate"]["numerator"] = 0
    _rehash(packet, field="operating_cortex_packet_id", prefix="mmcortexpacket_")
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="scorecards"
    ):
        cortex.validate_operating_cortex_packet(packet)

    packet = _fixture()["packet"]
    packet["claims"]["attention_quality_evaluated"] = True
    _rehash(packet, field="operating_cortex_packet_id", prefix="mmcortexpacket_")
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="claims"):
        cortex.validate_operating_cortex_packet(packet)


def test_join_detects_exact_source_and_registration_dependency_tampering() -> None:
    fixture = _fixture()
    sources = dict(fixture["sources"])
    sources["src.a"] = b"macro datum altered"
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError):
        cortex.validate_operating_cortex_packet_join(
            fixture["packet"],
            **{**fixture["join_kwargs"], "exact_source_bytes": sources},
        )

    registration = copy.deepcopy(fixture["registration"])
    registration["required_evidence_kinds"] = ["macro_fact"]
    _rehash(
        registration,
        field="operating_cortex_registration_id",
        prefix="mmcortexregistration_",
    )
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError):
        cortex.validate_operating_cortex_packet_join(
            fixture["packet"],
            **{
                **fixture["join_kwargs"],
                "operating_cortex_registration": registration,
            },
        )


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
            b"{" + b" " * (256 * 1024),
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
        )


def test_reader_is_immutable_detached_and_exposes_only_frozen_read_surface() -> None:
    fixture = _fixture()
    reader = cortex.OperatingCortexReader(fixture["packet"], **fixture["join_kwargs"])

    assert reader.read_episode_scope() == fixture["packet"]["episode_scope"]
    assert reader.read_attention_queue() == fixture["packet"]["attention_queue"]
    assert reader.read_contradictions() == fixture["packet"]["contradictions"]
    assert reader.read_missingness() == fixture["packet"]["missingness"]
    assert reader.read_falsifier_audit() == fixture["packet"]["falsifier_audit"]
    assert reader.read_citation_projection() == fixture["packet"]["citation_projection"]
    assert reader.read_scorecards() == fixture["packet"]["scorecards"]
    mutable = reader.read_attention_queue()
    mutable.clear()
    assert reader.read_attention_queue()
    with pytest.raises(AttributeError):
        reader.packet = fixture["packet"]

    public = {
        name
        for name, member in inspect.getmembers(cortex.OperatingCortexReader)
        if callable(member) and not name.startswith("_")
    }
    assert public == {
        "read_attention_queue",
        "read_episode_scope",
        "read_contradictions",
        "read_missingness",
        "read_falsifier_audit",
        "read_citation_projection",
        "read_scorecards",
    }


def test_module_is_pure_stdlib_plus_exact_w2_w4_owners_and_has_no_cortex_llm_import() -> (
    None
):
    path = Path(cortex.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    forbidden_calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"open", "eval", "exec", "compile", "__import__"}
        ):
            forbidden_calls.add(node.func.id)

    allowed = {
        "__future__",
        "copy",
        "hashlib",
        "json",
        "re",
        "collections.abc",
        "datetime",
        "decimal",
        "types",
        "typing",
        "engine.neuralweb",
    }
    assert imports <= allowed
    assert not forbidden_calls
    assert "cortex.py" not in source
    assert "os.environ" not in source
    assert "requests" not in source


def test_depth_node_string_evidence_claim_reference_and_kind_bounds() -> None:
    fixture = _fixture()
    too_many_evidence = [copy.deepcopy(fixture["evidence"][0]) for _ in range(65)]
    for index, row in enumerate(too_many_evidence):
        row["evidence_id"] = f"ev.{index:03d}"
    fixture["build_kwargs"]["evidence_cards"] = too_many_evidence
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="64"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["claim_inputs"][0]["evidence_ids"] = [
        f"ev.{i}" for i in range(9)
    ]
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="8"):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["evidence_cards"][0]["evidence_kind"] = "x" * 257
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])

    fixture = _fixture()
    fixture["build_kwargs"]["claim_inputs"][0]["required_evidence_kinds"] = [
        "unregistered_fact"
    ]
    with pytest.raises(
        cortex.MarketMemoryOperatingCortexContractError, match="preregistered"
    ):
        cortex.build_operating_cortex_packet(**fixture["build_kwargs"])


def test_json_resource_depth_and_node_bounds_precede_deep_semantics() -> None:
    fixture = _fixture()
    registration = copy.deepcopy(fixture["registration"])
    nested: Any = False
    for _ in range(18):
        nested = [nested]
    registration["claims"]["extra"] = nested
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="depth"):
        cortex.validate_operating_cortex_registration_record(registration)

    registration = copy.deepcopy(fixture["registration"])
    registration["claims"]["extra"] = [False] * 16_385
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="nodes"):
        cortex.validate_operating_cortex_registration_record(registration)


def test_registration_loader_and_join_reject_wrong_w4_hash_even_when_rehashed() -> None:
    fixture = _fixture()
    registration = copy.deepcopy(fixture["registration"])
    registration["retrieval_registration_sha256"] = "0" * 64
    _rehash(
        registration,
        field="operating_cortex_registration_id",
        prefix="mmcortexregistration_",
    )
    with pytest.raises(cortex.MarketMemoryOperatingCortexContractError, match="bytes"):
        cortex.validate_operating_cortex_registration_join(
            registration,
            retrieval_registration=fixture["retrieval_registration"],
            trial_registration=fixture["trial"],
        )
