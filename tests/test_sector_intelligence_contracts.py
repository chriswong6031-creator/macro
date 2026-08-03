from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from engine.sector_intelligence.contracts import (
    ContractError,
    ContractRegistry,
    ContractRegistryError,
    ContractValidationError,
    UnsupportedContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    ctgov_query_manifest_sha256,
    discover_contract_schemas,
    exact_json_diff,
    receipt_payloads_sha256,
    validate_contract,
    validate_ctgov_publication_bundle,
    validate_ctgov_fetch_run_against_receipts,
    validate_evidence_claim_against_source_records,
    validate_source_page_receipt_against_raw_response,
    validate_biocatalyst_launch_slo_manifest,
    validate_trial_observation_against_source_evidence,
    validate_trial_source_snapshot_against_fetch_evidence,
    validate_trial_diff_against_snapshots,
    validate_trial_projection_against_source,
)


ROOT = Path(__file__).resolve().parents[1]
GENERIC_FIXTURE_DIR = ROOT / "data" / "sector_intelligence" / "fixtures"
BIOCATALYST_FIXTURE_DIR = ROOT / "data" / "biocatalyst" / "fixtures"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_launch_slo_manifest() -> dict:
    payload = yaml.safe_load(
        (ROOT / "config" / "biocatalyst_launch_slo_manifest.yml").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(payload, dict)
    return payload


def _rebind_launch_slo_manifest(payload: dict) -> dict:
    rebound = deepcopy(payload)
    content = {
        key: value
        for key, value in rebound.items()
        if key not in {"manifest_id", "content_sha256"}
    }
    digest = canonical_json_sha256(content)
    rebound["content_sha256"] = digest
    rebound["manifest_id"] = f"biocatalyst_launch_slo_{digest[:24]}"
    return rebound


def _launch_slo_artifact(
    kind: str,
    *,
    scheduled_manifest_id: str,
    scheduled_manifest_content_sha256: str,
    source_id: str | None = None,
) -> dict:
    digest = hashlib.sha256(f"synthetic-{kind}-evidence".encode()).hexdigest()
    return {
        "artifact_id": f"biocatalyst_artifact_{digest[:24]}",
        "kind": kind,
        "object_ref": f"r2://biocatalyst-soak/{kind}/{digest}.json",
        "content_sha256": digest,
        "byte_count": 128,
        "captured_at": "2026-08-18T00:01:00Z",
        "scheduled_manifest_id": scheduled_manifest_id,
        "scheduled_manifest_content_sha256": scheduled_manifest_content_sha256,
        "source_id": source_id,
        "window_start": "2026-08-04T00:00:00Z",
        "window_end": "2026-08-18T00:00:00Z",
    }


def _completed_launch_slo_manifest() -> dict:
    payload = _load_launch_slo_manifest()
    predecessor_id = payload["manifest_id"]
    predecessor_hash = payload["content_sha256"]
    payload["state"] = "soak_complete_passed"
    payload["supersedes_manifest_id"] = predecessor_id
    payload["supersedes_manifest_content_sha256"] = predecessor_hash
    payload["sources"][0]["activation_state"] = "armed"
    payload["soak"] = {
        "required_duration_seconds": 1209600,
        "window_start": "2026-08-04T00:00:00Z",
        "window_end": "2026-08-18T00:00:00Z",
        "telemetry_generation_ref": _launch_slo_artifact(
            "telemetry_generation",
            scheduled_manifest_id=predecessor_id,
            scheduled_manifest_content_sha256=predecessor_hash,
        ),
        "raw_telemetry_refs": [
            _launch_slo_artifact(
                "raw_telemetry",
                scheduled_manifest_id=predecessor_id,
                scheduled_manifest_content_sha256=predecessor_hash,
                source_id="clinicaltrials_gov_v2",
            )
        ],
        "correction_replay_evidence_refs": [
            _launch_slo_artifact(
                "correction_replay",
                scheduled_manifest_id=predecessor_id,
                scheduled_manifest_content_sha256=predecessor_hash,
                source_id="clinicaltrials_gov_v2",
            )
        ],
        "rollback_restore_evidence_refs": [
            _launch_slo_artifact(
                "rollback_restore",
                scheduled_manifest_id=predecessor_id,
                scheduled_manifest_content_sha256=predecessor_hash,
                source_id="clinicaltrials_gov_v2",
            )
        ],
        "ci_validation_receipt_ref": _launch_slo_artifact(
            "ci_validation",
            scheduled_manifest_id=predecessor_id,
            scheduled_manifest_content_sha256=predecessor_hash,
        ),
        "source_results": [
            {
                "source_id": "clinicaltrials_gov_v2",
                "expected_opportunities": 336,
                "excluded_predeclared_maintenance": 0,
                "excluded_source_native_nonpublication": 0,
                "denominator": 336,
                "stage_successes": {
                    "fetch": 335,
                    "parse": 335,
                    "contract_validation": 335,
                    "completeness_reconciliation": 335,
                    "publication": 335,
                    "watermark_or_pointer": 335,
                },
                "successful_opportunities": 335,
                "misses": 1,
                "upstream_unavailable_observations": 1,
                "maximum_consecutive_misses_observed": 1,
                "freshness_p95_seconds": 3600,
                "minimum_completeness_ratio_observed": 1.0,
                "minimum_vs_prior_scope_ratio_observed": 1.0,
                "critical_failure_types": [],
                "passed": True,
            }
        ],
        "aggregate_passed": True,
        "scheduling_blockers": [],
    }
    return _rebind_launch_slo_manifest(payload)


def _load_trial_run_evidence() -> tuple[dict, list[dict], dict, list[dict]]:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    return (
        _load(fixture_dir / "ctgov_fetch_run.before.v1.valid.json"),
        [_load(fixture_dir / "source_page_receipt.before.v1.valid.json")],
        _load(fixture_dir / "ctgov_fetch_run.v1.valid.json"),
        [_load(fixture_dir / "source_page_receipt.v1.valid.json")],
    )


def _load_trial_raw_page(*, before: bool = False) -> bytes:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    name = (
        "source_page_response.before.raw.json"
        if before
        else "source_page_response.after.raw.json"
    )
    return (fixture_dir / name).read_bytes()


def _rebind_receipt_to_raw(receipt: dict, raw_page_body: bytes) -> str:
    response = receipt["response"]
    response_hash = hashlib.sha256(raw_page_body).hexdigest()
    object_key_prefix = response["raw_response_object_key"].rsplit("/", 1)[0]
    response["exact_response_sha256"] = response_hash
    response["raw_response_object_key"] = f"{object_key_prefix}/{response_hash}.json"
    response["byte_count"] = len(raw_page_body)
    response["headers"]["content-length"] = str(len(raw_page_body))
    return response_hash


def _raw_page_map(
    receipts: list[dict],
    *,
    before: bool = False,
    raw_page_body: bytes | None = None,
) -> dict[str, bytes]:
    assert len(receipts) == 1
    return {
        receipts[0]["receipt_id"]: (
            raw_page_body
            if raw_page_body is not None
            else _load_trial_raw_page(before=before)
        )
    }


def _validate_fixture_projection(projection: dict, source: dict) -> None:
    _, _, run, receipts = _load_trial_run_evidence()
    validate_trial_projection_against_source(
        projection,
        source,
        run=run,
        receipts=receipts,
        raw_page_bodies_by_receipt=_raw_page_map(receipts),
        repo_root=ROOT,
    )


def _write_minimal_schema(path: Path, contract_id: str, schema_uri: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": schema_uri
                or f"https://mastermind-x.com/contracts/sector_intelligence/{path.name}",
                "type": "object",
                "required": ["contract_id"],
                "properties": {"contract_id": {"const": contract_id}},
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )


def _temporary_contract_root(tmp_path: Path) -> Path:
    (tmp_path / "contracts" / "sector_intelligence").mkdir(parents=True)
    (tmp_path / "contracts" / "biocatalyst").mkdir(parents=True)
    return tmp_path


def test_discovers_every_declared_contract_by_document_id() -> None:
    schemas = discover_contract_schemas(ROOT)
    schema_files = sorted(
        list((ROOT / "contracts" / "sector_intelligence").glob("*.schema.json"))
        + list((ROOT / "contracts" / "biocatalyst").glob("*.schema.json"))
    )

    assert len(schemas) == len(schema_files)
    assert set(schemas) == {
        schema["properties"]["contract_id"]["const"] for schema in schemas.values()
    }
    assert "sector_intelligence_packet.v1" in schemas
    assert "biocatalyst_ontology.v1" in schemas


def test_b2_history_contracts_are_discovered_as_a_closed_contract_set() -> None:
    schemas = discover_contract_schemas(ROOT)

    assert {
        "ctgov_history_receipt.v1",
        "ctgov_history_run.v1",
        "trial_history_source_snapshot.v1",
        "trial_history_exact_diff.v1",
        "trial_registry_change_fact.v1",
        "trial_history_read_model.v1",
    } <= set(schemas)


@pytest.mark.parametrize(
    "fixture",
    sorted(GENERIC_FIXTURE_DIR.glob("*.valid.json")),
    ids=lambda path: path.name,
)
def test_every_generic_synthetic_fixture_validates(fixture: Path) -> None:
    validate_contract(_load(fixture), repo_root=ROOT)


@pytest.mark.parametrize(
    "fixture",
    sorted(BIOCATALYST_FIXTURE_DIR.rglob("*.valid.json")),
    ids=lambda path: path.name,
)
def test_every_biocatalyst_synthetic_fixture_validates(fixture: Path) -> None:
    validate_contract(_load(fixture), repo_root=ROOT)


def test_duplicate_contract_ids_abort_registry_build(tmp_path: Path) -> None:
    root = _temporary_contract_root(tmp_path)
    _write_minimal_schema(
        root / "contracts" / "sector_intelligence" / "one.schema.json", "duplicate.v1"
    )
    _write_minimal_schema(
        root / "contracts" / "biocatalyst" / "two.schema.json",
        "duplicate.v1",
        "https://mastermind-x.com/contracts/biocatalyst/two.schema.json",
    )

    with pytest.raises(ContractRegistryError, match="duplicate contract_id 'duplicate.v1'"):
        ContractRegistry(root)


def test_non_2020_12_schema_aborts_registry_build(tmp_path: Path) -> None:
    root = _temporary_contract_root(tmp_path)
    path = root / "contracts" / "sector_intelligence" / "legacy.schema.json"
    _write_minimal_schema(path, "legacy.v1")
    schema = _load(path)
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    path.write_text(json.dumps(schema), encoding="utf-8")

    with pytest.raises(ContractRegistryError, match="must declare JSON Schema Draft 2020-12"):
        ContractRegistry(root)


@pytest.mark.parametrize(
    "contract_id", ["../source_record.v1", "sector_intelligence/source_record.v1", "", None]
)
def test_rejects_unsafe_contract_ids(contract_id: object) -> None:
    with pytest.raises(UnsupportedContractError, match="unsafe contract_id"):
        validate_contract({"contract_id": contract_id}, repo_root=ROOT)


def test_rejects_safe_but_unsupported_contract_id() -> None:
    with pytest.raises(UnsupportedContractError, match="unsupported contract_id 'missing.v1'"):
        validate_contract({"contract_id": "missing.v1"}, repo_root=ROOT)


def test_rejects_schema_symlink_even_when_target_is_inside_tree(tmp_path: Path) -> None:
    root = _temporary_contract_root(tmp_path)
    real = root / "contracts" / "sector_intelligence" / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = root / "contracts" / "sector_intelligence" / "linked.schema.json"
    link.symlink_to(real)

    with pytest.raises(ContractRegistryError, match="unsafe schema path"):
        ContractRegistry(root)


def test_format_checking_and_error_order_are_deterministic() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "source_record.v1.valid.json")
    payload["source_uri"] = "not a uri"
    payload["retrieved_at"] = "not a timestamp"

    with pytest.raises(ContractValidationError) as first:
        validate_contract(payload, repo_root=ROOT)
    with pytest.raises(ContractValidationError) as second:
        validate_contract(dict(reversed(list(payload.items()))), repo_root=ROOT)

    assert str(first.value) == str(second.value)
    assert "$.retrieved_at: [schema]" in str(first.value)
    assert "$.source_uri: [schema]" in str(first.value)


@pytest.mark.parametrize(
    "malformed_uri",
    ["http://[", "http://example.com:bad", "http://%zz", "https://user:secret@example.com"],
)
def test_uri_format_fails_closed_without_crashing(malformed_uri: str) -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "source_record.v1.valid.json")
    payload["source_uri"] = malformed_uri

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "$.source_uri: [schema]" in str(caught.value)


@pytest.mark.parametrize(
    ("fixture", "first", "second", "code"),
    [
        ("source_record.v1.valid.json", "valid_from", "valid_to", "interval.valid"),
        (
            "source_record.v1.valid.json",
            "transaction_from",
            "transaction_to",
            "interval.transaction",
        ),
        ("lobe_run.v1.valid.json", "started_at", "finished_at", "interval.run"),
    ],
)
def test_semantic_intervals_must_be_forward(
    fixture: str, first: str, second: str, code: str
) -> None:
    fixture_dir = GENERIC_FIXTURE_DIR
    payload = _load(fixture_dir / fixture)
    payload[first] = "2026-08-02T00:00:00Z"
    payload[second] = "2026-08-01T00:00:00Z"

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert code in str(caught.value)


@pytest.mark.parametrize(
    ("fixture", "successor"),
    [
        ("feature_snapshot.v1.valid.json", "as_of"),
        ("lobe_run.v1.valid.json", "started_at"),
        ("outcome_label.v1.valid.json", "resolved_at"),
        ("prediction.v1.valid.json", "issued_at"),
        ("sector_intelligence_packet.v1.valid.json", "generated_at"),
    ],
)
def test_knowledge_cutoff_cannot_postdate_artifact_time(fixture: str, successor: str) -> None:
    payload = _load(GENERIC_FIXTURE_DIR / fixture)
    payload["knowledge_cutoff"] = "2030-01-01T00:00:00Z"
    payload[successor] = "2029-01-01T00:00:00Z"

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "interval.knowledge_cutoff" in str(caught.value)
    assert successor in str(caught.value)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"max_authority": "A2_ATTEND"}, "may not exceed A1_EXPLAIN"),
        ({"allowed_actions": ["observe", "attend"]}, "prohibited: attend"),
        (
            {
                "forbidden_actions": [
                    "originate_signal",
                    "raise_authority_from_llm",
                    "select_security",
                    "size_position",
                    "gate_decision",
                    "execute_trade",
                ]
            },
            "rank_security",
        ),
        ({"llm_may_originate_signals": True}, "forbid LLM signal origination"),
    ],
)
def test_sector_packets_are_enforced_as_facts_only(mutation: dict, expected: str) -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "sector_intelligence_packet.v1.valid.json")
    payload["authority_caps"].update(mutation)

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert expected in str(caught.value)


def test_llm_prediction_cannot_self_promote_or_gain_decision_authority() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "prediction.v1.valid.json")
    payload.update(
        {
            "originator_type": "llm_assisted",
            "llm_role": "explanation_only",
            "publication_tier": "SCORED",
            "decision_authority": True,
            "permitted_decision_uses": ["rank", "select", "size", "gate"],
            "promotion_evidence_refs": [],
            "governance_decision_refs": [],
        }
    )

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    message = str(caught.value)
    assert "decision_authority" in message
    assert "publication_tier" in message
    assert "permitted_decision_uses" in message


def test_elevated_authority_manifest_requires_governance_evidence() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "authority_manifest.v1.valid.json")
    payload.update(
        {
            "publication_tier": "SCORED",
            "max_authority": "A6_TUNE",
            "allowed_actions": ["observe", "explain", "tune"],
            "promotion_evidence_refs": [],
            "governance_decision_refs": [],
        }
    )

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "promotion_evidence_refs" in str(caught.value)
    assert "governance_decision_refs" in str(caught.value)


def test_authority_manifest_actions_cannot_exceed_declared_cap() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "authority_manifest.v1.valid.json")
    payload["max_authority"] = "A1_EXPLAIN"
    payload["allowed_actions"] = ["observe", "explain", "tune"]

    with pytest.raises(ContractValidationError, match="authority.action_cap"):
        validate_contract(payload, repo_root=ROOT)


def test_explicit_contract_id_must_match_document() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "source_record.v1.valid.json")
    with pytest.raises(ContractValidationError, match="contract_id.mismatch"):
        validate_contract("entity_link.v1", payload, repo_root=ROOT)


def test_canonical_json_sorts_object_keys_and_preserves_array_order() -> None:
    first = {"z": [3, {"b": 2, "a": 1}], "a": "é"}
    reordered_objects = {"a": "é", "z": [3, {"a": 1, "b": 2}]}
    reordered_array = {"a": "é", "z": [{"a": 1, "b": 2}, 3]}

    assert canonical_json_bytes(first) == b'{"a":"\xc3\xa9","z":[3,{"a":1,"b":2}]}'
    assert canonical_json_sha256(first) == canonical_json_sha256(reordered_objects)
    assert canonical_json_sha256(first) != canonical_json_sha256(reordered_array)
    assert canonical_json_sha256(first) == hashlib.sha256(canonical_json_bytes(first)).hexdigest()


def test_canonical_json_rejects_non_json_numbers() -> None:
    with pytest.raises(ContractError, match="not canonicalizable JSON"):
        canonical_json_sha256({"bad": float("nan")})


@pytest.mark.parametrize(
    ("before", "after"),
    [(1, 1.0), (True, 1), (False, 0)],
)
def test_exact_json_diff_preserves_json_type_changes(before: object, after: object) -> None:
    operations = exact_json_diff({"value": before}, {"value": after})

    assert len(operations) == 1
    assert operations[0]["op"] == "replace"
    assert operations[0]["json_path"] == "/value"
    assert canonical_json_sha256({"value": before}) != canonical_json_sha256(
        {"value": after}
    )


def test_actual_enrollment_change_is_not_labeled_as_target_change() -> None:
    before = {
        "protocolSection": {
            "designModule": {"enrollmentInfo": {"count": 120, "type": "ACTUAL"}}
        }
    }
    after = {
        "protocolSection": {
            "designModule": {"enrollmentInfo": {"count": 121, "type": "ACTUAL"}}
        }
    }

    operations = exact_json_diff(before, after)

    assert operations[0]["change_family"] == "enrollment_actual"

    added = exact_json_diff(
        {"protocolSection": {"designModule": {}}},
        after,
    )
    assert added[0]["json_path"].endswith("/enrollmentInfo")
    assert added[0]["change_family"] == "enrollment_actual"


def test_trial_source_fixture_hash_is_bound_to_canonical_study() -> None:
    fixture = BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / (
        "trial_source_snapshot.after.v1.valid.json"
    )
    payload = _load(fixture)

    assert canonical_json_sha256(payload["canonical_study"]) == payload[
        "canonical_content_sha256"
    ]
    validate_contract(payload, repo_root=ROOT)

    payload["canonical_study"]["protocolSection"]["designModule"]["enrollmentInfo"][
        "count"
    ] = 999
    with pytest.raises(ContractValidationError, match="source_snapshot.hash"):
        validate_contract(payload, repo_root=ROOT)


def test_trial_projection_is_bound_to_source_fields_even_after_rehash() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    projection = _load(fixture_dir / "trial_snapshot.v1.valid.json")

    _validate_fixture_projection(projection, source)
    projection["facts"]["overall_status"]["value"] = "COMPLETED"
    unhashed = dict(projection)
    unhashed.pop("projection_sha256")
    projection["projection_sha256"] = canonical_json_sha256(unhashed)

    with pytest.raises(ContractValidationError, match="trial_snapshot.fact_binding"):
        _validate_fixture_projection(projection, source)


def test_trial_projection_cannot_relabel_source_paths_or_hide_present_facts() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    projection = _load(fixture_dir / "trial_snapshot.v1.valid.json")
    projection["facts"]["overall_status"].update(
        {
            "source_json_path": "/protocolSection/identificationModule/briefTitle",
            "value": "Synthetic Phase 2 Study",
        }
    )
    unhashed = dict(projection)
    unhashed.pop("projection_sha256")
    projection["projection_sha256"] = canonical_json_sha256(unhashed)

    with pytest.raises(ContractValidationError) as caught:
        _validate_fixture_projection(projection, source)

    assert "source_json_path" in str(caught.value)

    projection = _load(fixture_dir / "trial_snapshot.v1.valid.json")
    projection["facts"]["overall_status"].update(
        {"state": "parser_degraded", "value": None}
    )
    unhashed = dict(projection)
    unhashed.pop("projection_sha256")
    projection["projection_sha256"] = canonical_json_sha256(unhashed)

    with pytest.raises(ContractValidationError, match="trial_snapshot.fact_binding"):
        _validate_fixture_projection(projection, source)


def test_trial_source_publication_time_is_bound_to_hashed_study() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR
        / "clinicaltrials"
        / "trial_source_snapshot.after.v1.valid.json"
    )
    payload["source_last_update_posted_at"] = "2020-01-01"
    payload["source_published_at"] = "2020-01-01"

    with pytest.raises(
        ContractValidationError, match="source_snapshot.publication_binding"
    ):
        validate_contract(payload, repo_root=ROOT)


def test_trial_projection_provenance_is_bound_to_source_snapshot() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    projection = _load(fixture_dir / "trial_snapshot.v1.valid.json")
    projection["source_published_at"] = "2020-01-01"
    projection["source_attribution"]["source_last_update_posted_at"] = "2020-01-01"
    unhashed = dict(projection)
    unhashed.pop("projection_sha256")
    projection["projection_sha256"] = canonical_json_sha256(unhashed)

    validate_contract(projection, repo_root=ROOT)
    with pytest.raises(ContractValidationError, match="trial_snapshot.source_binding"):
        _validate_fixture_projection(projection, source)


def test_trial_projection_transaction_cannot_precede_source_snapshot() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    projection = _load(fixture_dir / "trial_snapshot.v1.valid.json")
    projection["transaction_from"] = projection["knowledge_cutoff"]
    unhashed = dict(projection)
    unhashed.pop("projection_sha256")
    projection["projection_sha256"] = canonical_json_sha256(unhashed)

    with pytest.raises(
        ContractValidationError, match="trial_snapshot.transaction_binding"
    ):
        _validate_fixture_projection(projection, source)


def test_trial_observation_flags_must_match_content_hashes() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR
        / "clinicaltrials"
        / "trial_snapshot_observation.after.v1.valid.json"
    )
    payload["same_content_as_prior"] = True

    with pytest.raises(ContractValidationError, match="observation.hash_state"):
        validate_contract(payload, repo_root=ROOT)


def test_trial_observation_is_bound_to_run_receipt_and_source_snapshot() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    observation = _load(
        fixture_dir / "trial_snapshot_observation.after.v1.valid.json"
    )
    _, _, run, receipts = _load_trial_run_evidence()

    validate_trial_observation_against_source_evidence(
        observation,
        source,
        run,
        receipts,
        raw_page_bodies_by_receipt=_raw_page_map(receipts),
        repo_root=ROOT,
    )
    observation["run_ref"] = "ctgov_run_fabricated"
    observation["page_receipt_ref"] = "ctgov_receipt_fabricated_0"
    observation["source_dataset_timestamp_raw"] = "2020-01-01T00:00:00"
    observation["source_last_update_posted_at"] = "2020-01-01"

    with pytest.raises(ContractValidationError) as caught:
        validate_trial_observation_against_source_evidence(
            observation,
            source,
            run,
            receipts,
            raw_page_bodies_by_receipt=_raw_page_map(receipts),
            repo_root=ROOT,
        )

    message = str(caught.value)
    assert "observation.source_binding" in message
    assert "observation.receipt_binding" in message


def test_observation_and_projection_reject_incomplete_fetch_evidence() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    observation = _load(
        fixture_dir / "trial_snapshot_observation.after.v1.valid.json"
    )
    projection = _load(fixture_dir / "trial_snapshot.v1.valid.json")
    _, _, run, receipts = _load_trial_run_evidence()
    run["run_state"] = "partial"
    run["completeness_state"] = "page_incomplete"
    run["watermark_after"] = run["watermark_before"]
    run["counts"]["studies_published"] = 0
    run["published_source_record_refs"] = []

    with pytest.raises(ContractValidationError, match="source_snapshot.complete_run"):
        validate_trial_observation_against_source_evidence(
            observation,
            source,
            run,
            receipts,
            raw_page_bodies_by_receipt=_raw_page_map(receipts),
            repo_root=ROOT,
        )
    with pytest.raises(ContractValidationError, match="source_snapshot.complete_run"):
        validate_trial_projection_against_source(
            projection,
            source,
            run=run,
            receipts=receipts,
            raw_page_bodies_by_receipt=_raw_page_map(receipts),
            repo_root=ROOT,
        )


def test_trial_diff_operation_state_is_not_ambiguous() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR
        / "clinicaltrials"
        / "trial_version_diff.v1.valid.json"
    )
    payload["operations"][0]["op"] = "add"

    with pytest.raises(ContractValidationError, match="trial_diff.operation_state"):
        validate_contract(payload, repo_root=ROOT)


def test_trial_diff_is_recomputed_against_source_snapshots() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    before = _load(fixture_dir / "trial_source_snapshot.before.v1.valid.json")
    after = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    before_observation = _load(
        fixture_dir / "trial_snapshot_observation.before.v1.valid.json"
    )
    after_observation = _load(
        fixture_dir / "trial_snapshot_observation.after.v1.valid.json"
    )
    before_run, before_receipts, after_run, after_receipts = (
        _load_trial_run_evidence()
    )
    diff = _load(fixture_dir / "trial_version_diff.v1.valid.json")

    assert diff["operations"] == exact_json_diff(
        before["canonical_study"], after["canonical_study"]
    )
    validate_trial_diff_against_snapshots(
        diff,
        before,
        after,
        before_observation,
        after_observation,
        before_run=before_run,
        before_receipts=before_receipts,
        before_raw_page_bodies_by_receipt=_raw_page_map(
            before_receipts, before=True
        ),
        after_run=after_run,
        after_receipts=after_receipts,
        after_raw_page_bodies_by_receipt=_raw_page_map(after_receipts),
        repo_root=ROOT,
    )

    diff["operations"][0]["before_value"] = 121
    unhashed = dict(diff)
    unhashed.pop("diff_payload_sha256")
    diff["diff_payload_sha256"] = canonical_json_sha256(unhashed)
    validate_contract(diff, repo_root=ROOT)
    with pytest.raises(ContractValidationError, match="trial_diff.exactness"):
        validate_trial_diff_against_snapshots(
            diff,
            before,
            after,
            before_observation,
            after_observation,
            before_run=before_run,
            before_receipts=before_receipts,
            before_raw_page_bodies_by_receipt=_raw_page_map(
                before_receipts, before=True
            ),
            after_run=after_run,
            after_receipts=after_receipts,
            after_raw_page_bodies_by_receipt=_raw_page_map(after_receipts),
            repo_root=ROOT,
        )


def test_trial_diff_timing_is_bound_to_observation_records() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    before = _load(fixture_dir / "trial_source_snapshot.before.v1.valid.json")
    after = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    before_observation = _load(
        fixture_dir / "trial_snapshot_observation.before.v1.valid.json"
    )
    after_observation = _load(
        fixture_dir / "trial_snapshot_observation.after.v1.valid.json"
    )
    before_run, before_receipts, after_run, after_receipts = (
        _load_trial_run_evidence()
    )
    diff = _load(fixture_dir / "trial_version_diff.v1.valid.json")
    diff["observed_interval"] = {
        "after": "2020-01-01T00:00:00Z",
        "at_or_before": "2020-01-02T00:00:00Z",
    }
    unhashed = dict(diff)
    unhashed.pop("diff_payload_sha256")
    diff["diff_payload_sha256"] = canonical_json_sha256(unhashed)

    validate_contract(diff, repo_root=ROOT)
    with pytest.raises(ContractValidationError, match="trial_diff.observation_binding"):
        validate_trial_diff_against_snapshots(
            diff,
            before,
            after,
            before_observation,
            after_observation,
            before_run=before_run,
            before_receipts=before_receipts,
            before_raw_page_bodies_by_receipt=_raw_page_map(
                before_receipts, before=True
            ),
            after_run=after_run,
            after_receipts=after_receipts,
            after_raw_page_bodies_by_receipt=_raw_page_map(after_receipts),
            repo_root=ROOT,
        )


def test_cross_trial_diff_is_rejected() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    before = _load(fixture_dir / "trial_source_snapshot.before.v1.valid.json")
    after = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    before_observation = _load(
        fixture_dir / "trial_snapshot_observation.before.v1.valid.json"
    )
    after_observation = _load(
        fixture_dir / "trial_snapshot_observation.after.v1.valid.json"
    )
    before_run, before_receipts, after_run, after_receipts = (
        _load_trial_run_evidence()
    )
    diff = _load(fixture_dir / "trial_version_diff.v1.valid.json")

    after["nct_id"] = "NCT00000002"
    after["source_snapshot_id"] = "ctgov_snapshot_NCT00000002_after"
    after["source_uri"] = "https://clinicaltrials.gov/study/NCT00000002"
    after["canonical_study"]["protocolSection"]["identificationModule"][
        "nctId"
    ] = "NCT00000002"
    after_hash = canonical_json_sha256(after["canonical_study"])
    after["canonical_content_sha256"] = after_hash
    after["source_record_ref"] = f"src:ctgov:NCT00000002:sha256:{after_hash}"
    after["raw_object_key"] = (
        f"biocatalyst/raw/clinicaltrials/v2/NCT00000002/{after_hash}.json"
    )
    after_observation["nct_id"] = "NCT00000002"
    after_observation["source_snapshot_ref"] = after["source_snapshot_id"]
    after_observation["canonical_content_sha256"] = after_hash
    after_run["query_manifest"]["configured_nct_ids"] = ["NCT00000002"]
    after_query_hash = ctgov_query_manifest_sha256(after_run["query_manifest"])
    after_run["query_manifest"]["query_sha256"] = after_query_hash
    after_receipts[0]["request"]["query_sha256"] = after_query_hash
    after_raw_page_body = canonical_json_bytes(
        {"studies": [after["canonical_study"]]}
    )
    after_response_hash = _rebind_receipt_to_raw(
        after_receipts[0], after_raw_page_body
    )
    after["exact_response_sha256"] = after_response_hash
    after_run["published_source_record_refs"] = [after["source_record_ref"]]
    after_run["receipt_payloads_sha256"] = receipt_payloads_sha256(after_receipts)
    diff["after_source_snapshot_ref"] = after["source_snapshot_id"]
    diff["after_content_sha256"] = after_hash
    diff["source_record_refs"] = [
        before["source_record_ref"],
        after["source_record_ref"],
    ]
    diff["operations"] = exact_json_diff(
        before["canonical_study"], after["canonical_study"]
    )
    unhashed = dict(diff)
    unhashed.pop("diff_payload_sha256")
    diff["diff_payload_sha256"] = canonical_json_sha256(unhashed)

    with pytest.raises(ContractValidationError, match="same NCT ID"):
        validate_trial_diff_against_snapshots(
            diff,
            before,
            after,
            before_observation,
            after_observation,
            before_run=before_run,
            before_receipts=before_receipts,
            before_raw_page_bodies_by_receipt=_raw_page_map(
                before_receipts, before=True
            ),
            after_run=after_run,
            after_receipts=after_receipts,
            after_raw_page_bodies_by_receipt=_raw_page_map(
                after_receipts, raw_page_body=after_raw_page_body
            ),
            repo_root=ROOT,
        )


def test_trial_diff_cannot_claim_protocol_change() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR
        / "clinicaltrials"
        / "trial_version_diff.v1.valid.json"
    )
    payload["protocol_change_asserted"] = True

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "$.protocol_change_asserted: [schema]" in str(caught.value)


def test_incomplete_fetch_run_cannot_advance_watermark() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
    )
    payload["run_state"] = "partial"
    payload["completeness_state"] = "page_incomplete"

    with pytest.raises(ContractValidationError, match="fetch_run.watermark"):
        validate_contract(payload, repo_root=ROOT)


def test_zero_evidence_fetch_run_cannot_be_complete() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
    )
    payload["source_dataset_timestamp_before_raw"] = None
    payload["source_dataset_timestamp_after_raw"] = None
    payload["receipt_refs"] = []
    payload["counts"].update(
        {
            "pages_attempted": 0,
            "pages_succeeded": 0,
            "studies_fetched": 0,
            "studies_unique": 0,
            "studies_published": 0,
        }
    )

    with pytest.raises(ContractValidationError, match="fetch_run.complete"):
        validate_contract(payload, repo_root=ROOT)


def test_complete_fetch_run_requires_full_publication_manifest() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
    )
    payload["counts"]["studies_published"] = 0
    payload["published_source_record_refs"] = []

    with pytest.raises(ContractValidationError, match="fetch_run.complete"):
        validate_contract(payload, repo_root=ROOT)


def test_source_change_mid_run_cannot_be_complete() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
    )
    payload["source_dataset_timestamp_after_raw"] = "2026-08-01T09:01:00"

    with pytest.raises(ContractValidationError, match="fetch_run.complete"):
        validate_contract(payload, repo_root=ROOT)


def test_query_manifest_hash_binds_configured_universe() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
    )
    payload["query_manifest"]["configured_nct_ids"] = ["NCT99999999"]

    with pytest.raises(ContractValidationError, match="fetch_run.query_manifest_hash"):
        validate_contract(payload, repo_root=ROOT)


def test_fetch_run_page_cap_is_enforced() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
    )
    payload["query_manifest"]["page_cap"] = 1
    payload["query_manifest"]["query_sha256"] = ctgov_query_manifest_sha256(
        payload["query_manifest"]
    )
    payload["counts"]["pages_attempted"] = 2

    with pytest.raises(ContractValidationError, match="fetch_run.page_cap"):
        validate_contract(payload, repo_root=ROOT)


@pytest.mark.parametrize(
    "mutation",
    [
        {"receipt_refs": []},
        {
            "watermark_before": "2026-08-02T15:00:05Z",
            "watermark_after": "2026-08-01T15:00:05Z",
        },
        {
            "finished_at": "2026-08-01T15:00:07Z",
            "transaction_from": "2026-08-01T15:00:06Z",
        },
    ],
)
def test_complete_fetch_run_cannot_bypass_reconciliation(mutation: dict) -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
    )
    payload.update(mutation)

    with pytest.raises(ContractValidationError, match="fetch_run.complete"):
        validate_contract(payload, repo_root=ROOT)


def test_noncomplete_watermark_candidate_cannot_advance() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_watermark.v1.valid.json"
    )
    payload["candidate_run_state"] = "partial"
    payload["advance_reason"] = "run_not_complete"

    with pytest.raises(ContractValidationError, match="watermark.advance"):
        validate_contract(payload, repo_root=ROOT)


@pytest.mark.parametrize(
    "private_ref",
    [
        "/var/lib/macro-biocatalyst/state/snapshot.json",
        "biocatalyst/raw/clinicaltrials/v2/NCT00000001/private.json",
    ],
)
def test_trial_read_projection_rejects_private_snapshot_paths(private_ref: str) -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "trial_snapshot.v1.valid.json"
    )
    payload["source_snapshot_ref"] = private_ref

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "$.source_snapshot_ref: [schema]" in str(caught.value)


def test_receipt_rejects_sensitive_headers() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR
        / "clinicaltrials"
        / "source_page_receipt.v1.valid.json"
    )
    payload["request"]["headers"]["authorization"] = "secret"

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "$.request.headers" in str(caught.value)
    assert "authorization" in str(caught.value)


def test_receipt_binds_private_raw_response_to_exact_hash() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR
        / "clinicaltrials"
        / "source_page_receipt.v1.valid.json"
    )
    payload["response"]["exact_response_sha256"] = "f" * 64

    with pytest.raises(ContractValidationError, match="receipt.object_key"):
        validate_contract(payload, repo_root=ROOT)


def test_receipt_is_verified_against_exact_archived_page_bytes() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    receipt = _load(fixture_dir / "source_page_receipt.v1.valid.json")
    raw_page_body = _load_trial_raw_page()

    parsed = validate_source_page_receipt_against_raw_response(
        receipt, raw_page_body, repo_root=ROOT
    )
    assert len(parsed["studies"]) == 1

    with pytest.raises(ContractValidationError, match="receipt.raw_response_hash"):
        validate_source_page_receipt_against_raw_response(
            receipt, raw_page_body + b" ", repo_root=ROOT
        )


def test_receipt_raw_study_count_and_pagination_token_are_verified() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    receipt = _load(fixture_dir / "source_page_receipt.v1.valid.json")
    raw_page_body = _load_trial_raw_page()
    receipt["response"]["study_count"] = 2

    with pytest.raises(
        ContractValidationError, match="receipt.raw_response_study_count"
    ):
        validate_source_page_receipt_against_raw_response(
            receipt, raw_page_body, repo_root=ROOT
        )

    receipt = _load(fixture_dir / "source_page_receipt.v1.valid.json")
    receipt["response"]["next_page_token_sha256"] = "f" * 64
    with pytest.raises(
        ContractValidationError, match="receipt.raw_pagination_token"
    ):
        validate_source_page_receipt_against_raw_response(
            receipt, raw_page_body, repo_root=ROOT
        )


def test_source_snapshot_must_be_extracted_from_archived_page() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    _, _, run, receipts = _load_trial_run_evidence()
    source["canonical_study"]["protocolSection"]["identificationModule"][
        "briefTitle"
    ] = "Fabricated but schema-valid title"
    source_hash = canonical_json_sha256(source["canonical_study"])
    source["canonical_content_sha256"] = source_hash
    source["source_record_ref"] = f"src:ctgov:NCT00000001:sha256:{source_hash}"
    source["raw_object_key"] = (
        f"biocatalyst/raw/clinicaltrials/v2/NCT00000001/{source_hash}.json"
    )
    run["published_source_record_refs"] = [source["source_record_ref"]]

    validate_contract(source, repo_root=ROOT)
    validate_contract(run, repo_root=ROOT)
    with pytest.raises(
        ContractValidationError, match="raw_run.derived_manifest"
    ):
        validate_trial_source_snapshot_against_fetch_evidence(
            source,
            run,
            receipts,
            raw_page_bodies_by_receipt=_raw_page_map(receipts),
            repo_root=ROOT,
        )


def test_source_snapshot_study_index_must_resolve_in_archived_page() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    _, _, run, receipts = _load_trial_run_evidence()
    source["source_page_study_index"] = 1

    with pytest.raises(
        ContractValidationError, match="source_snapshot.extraction_binding"
    ):
        validate_trial_source_snapshot_against_fetch_evidence(
            source,
            run,
            receipts,
            raw_page_bodies_by_receipt=_raw_page_map(receipts),
            repo_root=ROOT,
        )


def test_publication_bundle_proves_all_raw_pages_and_snapshots() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    _, _, run, receipts = _load_trial_run_evidence()
    receipt_id = receipts[0]["receipt_id"]

    validate_ctgov_publication_bundle(
        run,
        receipts,
        {receipt_id: _load_trial_raw_page()},
        [source],
        repo_root=ROOT,
    )

    with pytest.raises(
        ContractValidationError, match="raw_run.raw_page_coverage"
    ):
        validate_ctgov_publication_bundle(
            run,
            receipts,
            {},
            [source],
            repo_root=ROOT,
        )


def test_publication_bundle_verifies_every_page_in_multi_page_run() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    _, _, run, base_receipts = _load_trial_run_evidence()
    first = base_receipts[0]
    second = json.loads(json.dumps(first))
    next_token = "fixture-next-page"
    next_token_hash = hashlib.sha256(next_token.encode("utf-8")).hexdigest()
    first_page_body = canonical_json_bytes(
        {"studies": [source["canonical_study"]], "nextPageToken": next_token}
    )
    first_hash = _rebind_receipt_to_raw(first, first_page_body)
    first["response"]["next_page_token_sha256"] = next_token_hash

    second["receipt_id"] = "ctgov_receipt_fixture_20260801T150000Z_1"
    second["page_ordinal"] = 1
    second["receipt_object_key"] = (
        "biocatalyst/receipts/clinicaltrials/2026/08/"
        "ctgov_run_fixture_20260801T150000Z/1.json"
    )
    second["request"]["page_token_sha256"] = next_token_hash
    second["response"]["raw_response_object_key"] = second["response"][
        "raw_response_object_key"
    ].replace("/0/", "/1/")
    second_page_body = canonical_json_bytes({"studies": []})
    _rebind_receipt_to_raw(second, second_page_body)
    second["response"]["study_count"] = 0
    second["response"]["next_page_token_sha256"] = None

    receipts = [first, second]
    run["receipt_refs"] = [receipt["receipt_id"] for receipt in receipts]
    run["terminal_receipt_ref"] = second["receipt_id"]
    run["receipt_payloads_sha256"] = receipt_payloads_sha256(receipts)
    run["counts"]["pages_attempted"] = 2
    run["counts"]["pages_succeeded"] = 2
    source["exact_response_sha256"] = first_hash
    raw_pages = {
        first["receipt_id"]: first_page_body,
        second["receipt_id"]: second_page_body,
    }

    validate_ctgov_publication_bundle(
        run, receipts, raw_pages, [source], repo_root=ROOT
    )
    with pytest.raises(ContractValidationError, match="raw_run.raw_page_coverage"):
        validate_ctgov_publication_bundle(
            run,
            receipts,
            {first["receipt_id"]: first_page_body},
            [source],
            repo_root=ROOT,
        )


def test_publication_bundle_rejects_divergent_duplicate_raw_study() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    source = _load(fixture_dir / "trial_source_snapshot.after.v1.valid.json")
    _, _, run, receipts = _load_trial_run_evidence()
    raw_page = json.loads(_load_trial_raw_page().decode("utf-8"))
    divergent = json.loads(json.dumps(raw_page["studies"][0]))
    divergent["protocolSection"]["identificationModule"]["briefTitle"] = (
        "Divergent duplicate"
    )
    raw_page["studies"].append(divergent)
    raw_page_body = canonical_json_bytes(raw_page)
    response_hash = _rebind_receipt_to_raw(receipts[0], raw_page_body)
    receipts[0]["response"]["study_count"] = 2
    source["exact_response_sha256"] = response_hash
    run["counts"].update(
        {"studies_fetched": 2, "studies_unique": 1, "studies_duplicate": 1}
    )
    run["receipt_payloads_sha256"] = receipt_payloads_sha256(receipts)

    with pytest.raises(
        ContractValidationError, match="raw_run.divergent_duplicate"
    ):
        validate_trial_source_snapshot_against_fetch_evidence(
            source,
            run,
            receipts,
            raw_page_bodies_by_receipt=_raw_page_map(
                receipts, raw_page_body=raw_page_body
            ),
            repo_root=ROOT,
        )
    with pytest.raises(
        ContractValidationError, match="raw_run.divergent_duplicate"
    ):
        validate_ctgov_publication_bundle(
            run,
            receipts,
            {receipts[0]["receipt_id"]: raw_page_body},
            [source],
            repo_root=ROOT,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"query_manifest": None},
        {"query_manifest": {"configured_nct_ids": [{}]}},
        {"published_source_record_refs": ["valid", 1]},
    ],
)
def test_fetch_run_malformed_shapes_fail_without_crashing(mutation: dict) -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
    )
    if mutation.get("query_manifest") == {"configured_nct_ids": [{}]}:
        payload["query_manifest"]["configured_nct_ids"] = [{}]
    else:
        payload.update(mutation)

    with pytest.raises(ContractValidationError):
        validate_contract(payload, repo_root=ROOT)


def test_raw_page_malformed_shapes_fail_without_crashing() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    base = _load(fixture_dir / "source_page_receipt.v1.valid.json")
    cases = (
        (b"null", 0, "receipt.raw_response_shape"),
        (b'{"studies":[{"value":1e400}]}', 1, "receipt.raw_response_json"),
        (
            b'{"studies":[{"value":0.100000000000000005}]}',
            1,
            "receipt.raw_response_json",
        ),
        (b'{"studies":[{"value":"\\ud800"}]}', 1, "receipt.raw_response_json"),
        (b'{"studies":[1]}', 1, "receipt.raw_response_study_shape"),
        (
            b'{"studies":[],"nextPageToken":"\\ud800"}',
            0,
            "receipt.raw_pagination_token",
        ),
    )
    for raw_page_body, study_count, expected in cases:
        receipt = json.loads(json.dumps(base))
        _rebind_receipt_to_raw(receipt, raw_page_body)
        receipt["response"]["study_count"] = study_count
        with pytest.raises(ContractValidationError, match=expected):
            validate_source_page_receipt_against_raw_response(
                receipt, raw_page_body, repo_root=ROOT
            )

    receipt = json.loads(json.dumps(base))
    receipt["response"]["headers"]["content-length"] = "9" * 5000
    with pytest.raises(
        ContractValidationError, match="receipt.raw_response_length"
    ):
        validate_source_page_receipt_against_raw_response(
            receipt, _load_trial_raw_page(), repo_root=ROOT
        )


def test_complete_fetch_run_is_bound_to_terminal_receipt_chain() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    run = _load(fixture_dir / "ctgov_fetch_run.v1.valid.json")
    receipt = _load(fixture_dir / "source_page_receipt.v1.valid.json")

    validate_ctgov_fetch_run_against_receipts(
        run, [receipt], repo_root=ROOT
    )

    receipt["response"]["next_page_token_sha256"] = "f" * 64
    run["receipt_payloads_sha256"] = receipt_payloads_sha256([receipt])
    with pytest.raises(ContractValidationError, match="fetch_run.terminal_receipt"):
        validate_ctgov_fetch_run_against_receipts(
            run, [receipt], repo_root=ROOT
        )


def test_fetch_run_rejects_repeated_pagination_token_cycles() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    run = _load(fixture_dir / "ctgov_fetch_run.v1.valid.json")
    base = _load(fixture_dir / "source_page_receipt.v1.valid.json")
    token = "1" * 64
    receipts = []
    for ordinal, request_token, next_token, response_hash in (
        (0, None, token, "b" * 64),
        (1, token, token, "c" * 64),
        (2, token, None, "d" * 64),
    ):
        receipt = json.loads(json.dumps(base))
        receipt_id = f"ctgov_receipt_fixture_20260801T150000Z_{ordinal}"
        receipt["receipt_id"] = receipt_id
        receipt["page_ordinal"] = ordinal
        receipt["receipt_object_key"] = (
            "biocatalyst/receipts/clinicaltrials/2026/08/"
            f"ctgov_run_fixture_20260801T150000Z/{ordinal}.json"
        )
        receipt["request"]["page_token_sha256"] = request_token
        receipt["response"]["exact_response_sha256"] = response_hash
        receipt["response"]["raw_response_object_key"] = (
            "biocatalyst/raw/clinicaltrials/v2/pages/2026/08/"
            f"ctgov_run_fixture_20260801T150000Z/{ordinal}/{response_hash}.json"
        )
        receipt["response"]["next_page_token_sha256"] = next_token
        receipt["response"]["received_at"] = (
            f"2026-08-01T15:00:0{ordinal + 1}Z"
        )
        receipts.append(receipt)

    run["receipt_refs"] = [receipt["receipt_id"] for receipt in receipts]
    run["terminal_receipt_ref"] = receipts[-1]["receipt_id"]
    run["receipt_payloads_sha256"] = receipt_payloads_sha256(receipts)
    run["counts"].update(
        {
            "pages_attempted": 3,
            "pages_succeeded": 3,
            "studies_fetched": 3,
            "studies_unique": 1,
            "studies_duplicate": 2,
        }
    )

    with pytest.raises(ContractValidationError, match="fetch_run.pagination_cycle"):
        validate_ctgov_fetch_run_against_receipts(
            run, receipts, repo_root=ROOT
        )


def test_fetch_run_transaction_cannot_precede_receipt_transaction() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    run = _load(fixture_dir / "ctgov_fetch_run.v1.valid.json")
    receipt = _load(fixture_dir / "source_page_receipt.v1.valid.json")
    receipt["transaction_from"] = "2030-01-01T00:00:00Z"
    run["receipt_payloads_sha256"] = receipt_payloads_sha256([receipt])

    with pytest.raises(ContractValidationError, match="fetch_run.receipt_transaction"):
        validate_ctgov_fetch_run_against_receipts(
            run, [receipt], repo_root=ROOT
        )


def test_fetch_run_cannot_substitute_arbitrary_receipt_references() -> None:
    fixture_dir = BIOCATALYST_FIXTURE_DIR / "clinicaltrials"
    run = _load(fixture_dir / "ctgov_fetch_run.v1.valid.json")
    receipt = _load(fixture_dir / "source_page_receipt.v1.valid.json")
    run["receipt_refs"] = ["ctgov_receipt_fabricated_0"]
    run["terminal_receipt_ref"] = "ctgov_receipt_fabricated_0"

    validate_contract(run, repo_root=ROOT)
    with pytest.raises(ContractValidationError, match="fetch_run.receipt_binding"):
        validate_ctgov_fetch_run_against_receipts(
            run, [receipt], repo_root=ROOT
        )


def test_source_dataset_timestamp_is_preserved_but_calendar_valid() -> None:
    payload = _load(
        BIOCATALYST_FIXTURE_DIR / "clinicaltrials" / "ctgov_fetch_run.v1.valid.json"
    )
    payload["source_dataset_timestamp_before_raw"] = "2026-99-99T09:00:00"

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "$.source_dataset_timestamp_before_raw: [schema]" in str(caught.value)


def test_packet_and_ontology_hashes_are_semantically_enforced() -> None:
    packet = _load(BIOCATALYST_FIXTURE_DIR / "sector_intelligence_packet.v1.valid.json")
    ontology = _load(BIOCATALYST_FIXTURE_DIR / "ontology.v1.valid.json")

    packet["quality"]["warnings"].append("tampered")
    ontology["canonical_unit"] = "tampered"

    with pytest.raises(ContractValidationError, match="packet.hash"):
        validate_contract(packet, repo_root=ROOT)
    with pytest.raises(ContractValidationError, match="ontology.hash"):
        validate_contract(ontology, repo_root=ROOT)


def test_feature_missingness_summary_and_freshness_must_reconcile() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "feature_snapshot.v1.valid.json")
    payload["values"][0].update(
        {
            "value": None,
            "missingness": "observed",
            "source_claim_refs": [],
        }
    )
    payload["missingness_summary"] = {"present": 99, "missing": 0, "stale": 0}

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    message = str(caught.value)
    assert "feature.missingness" in message
    assert "feature.missingness_summary" in message


def test_point_in_time_features_cannot_use_future_observations() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "feature_snapshot.v1.valid.json")
    payload["values"][0]["observed_at"] = "2030-01-01T00:00:00Z"

    with pytest.raises(ContractValidationError, match="feature.point_in_time"):
        validate_contract(payload, repo_root=ROOT)


def test_generic_provenance_chronology_is_fail_closed() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "source_record.v1.valid.json")
    payload["first_seen_at"] = "2026-08-03T08:00:00Z"
    payload["transaction_from"] = "2026-07-31T08:00:00Z"

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "provenance.first_seen" in str(caught.value)
    assert "provenance.transaction" in str(caught.value)


def test_clinicaltrials_source_rights_cannot_be_relabelled() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "source_record.v1.valid.json")
    payload["license_class"] = "public_domain"
    payload["redistribution_allowed"] = True
    payload["rights_note"] = None

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "rights.clinicaltrials_gov" in str(caught.value)


def test_clinicaltrials_source_record_id_is_content_addressed() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "source_record.v1.valid.json")
    payload["record_id"] = "opaque-record-id"

    with pytest.raises(ContractValidationError, match="source_record.content_address"):
        validate_contract(payload, repo_root=ROOT)


def test_clinicaltrials_source_record_requires_canonical_nct_id() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "source_record.v1.valid.json")
    payload["external_id"] = "NOT_AN_NCT"
    payload["source_uri"] = "https://clinicaltrials.gov/study/NOT_AN_NCT"
    payload["record_id"] = (
        f"src:ctgov:NOT_AN_NCT:sha256:{payload['content_sha256']}"
    )

    with pytest.raises(ContractValidationError, match="source_record.identity"):
        validate_contract(payload, repo_root=ROOT)


def test_evidence_claim_cannot_launder_source_record_rights() -> None:
    source = _load(GENERIC_FIXTURE_DIR / "source_record.v1.valid.json")
    claim = _load(GENERIC_FIXTURE_DIR / "evidence_claim.v1.valid.json")
    claim["source_record_refs"] = ["opaque-record-id"]
    claim["license_class"] = "public_domain"

    validate_contract(claim, repo_root=ROOT)
    with pytest.raises(ContractValidationError, match="evidence.rights_binding"):
        validate_evidence_claim_against_source_records(
            claim, [source], repo_root=ROOT
        )


def test_evidence_claim_transaction_cannot_precede_source_record() -> None:
    source = _load(GENERIC_FIXTURE_DIR / "source_record.v1.valid.json")
    claim = _load(GENERIC_FIXTURE_DIR / "evidence_claim.v1.valid.json")
    claim["transaction_from"] = claim["retrieved_at"]

    with pytest.raises(ContractValidationError, match="evidence.transaction_binding"):
        validate_evidence_claim_against_source_records(
            claim, [source], repo_root=ROOT
        )


def test_prediction_probability_and_horizon_invariants() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "prediction.v1.valid.json")
    payload["horizon"] = {
        "starts_at": "2027-08-01T08:10:00Z",
        "ends_at": "2026-08-01T08:10:00Z",
    }
    payload["scenarios"][0].update(
        {"probability": 0.9, "lower_bound": 0.95, "upper_bound": 0.99}
    )
    payload["scenarios"][1]["probability"] = 0.9

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    message = str(caught.value)
    assert "prediction.horizon" in message
    assert "prediction.bounds" in message
    assert "prediction.probability_mass" in message


def test_outcome_window_and_value_kind_invariants() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "outcome_label.v1.valid.json")
    payload["observation_window"] = {
        "starts_at": "2027-08-01T08:10:00Z",
        "ends_at": "2026-08-01T08:10:00Z",
    }
    payload["outcome"] = {"kind": "censored", "value": "success", "unit": None}

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)

    assert "outcome.observation_window" in str(caught.value)
    assert "outcome.value_kind" in str(caught.value)


def test_final_censored_outcome_waits_for_window_close() -> None:
    payload = _load(GENERIC_FIXTURE_DIR / "outcome_label.v1.valid.json")
    payload["resolved_at"] = "2027-01-01T00:00:00Z"
    payload["knowledge_cutoff"] = "2026-12-31T23:59:59Z"
    payload["transaction_from"] = "2027-01-01T00:00:01Z"

    with pytest.raises(ContractValidationError, match="outcome.censoring_window"):
        validate_contract(payload, repo_root=ROOT)


def test_biocatalyst_launch_slo_schema_is_discovered_and_committed_forms_validate() -> None:
    registry = ContractRegistry(ROOT)
    assert "biocatalyst_launch_slo_manifest.v1" in registry.contract_ids

    configured = _load_launch_slo_manifest()
    fixture = _load(
        BIOCATALYST_FIXTURE_DIR / "biocatalyst_launch_slo_manifest.v1.valid.json"
    )
    assert canonical_json_bytes(configured) == canonical_json_bytes(fixture)
    validate_biocatalyst_launch_slo_manifest(configured, repo_root=ROOT)
    validate_contract(fixture, repo_root=ROOT)


def test_launch_slo_digest_is_map_order_stable_and_semantic_edits_require_new_identity() -> None:
    payload = _load_launch_slo_manifest()
    reordered = {key: payload[key] for key in reversed(tuple(payload))}
    assert canonical_json_sha256(
        {key: value for key, value in payload.items() if key not in {"manifest_id", "content_sha256"}}
    ) == canonical_json_sha256(
        {key: value for key, value in reordered.items() if key not in {"manifest_id", "content_sha256"}}
    )
    validate_contract(reordered, repo_root=ROOT)

    edited = deepcopy(payload)
    edited["sources"][0]["error_budget"]["minimum_opportunity_success_ratio"] = 0.999
    with pytest.raises(ContractValidationError, match="launch_slo.hash"):
        validate_contract(edited, repo_root=ROOT)

    rebound = _rebind_launch_slo_manifest(edited)
    assert rebound["manifest_id"] != payload["manifest_id"]
    with pytest.raises(ContractValidationError, match="launch_slo.error_budget"):
        validate_contract(rebound, repo_root=ROOT)


def test_launch_slo_rejects_self_supersession_and_registry_hash_drift() -> None:
    payload = _load_launch_slo_manifest()
    payload["supersedes_manifest_id"] = payload["manifest_id"]
    with pytest.raises(ContractValidationError, match="launch_slo.self_supersession"):
        validate_contract(payload, repo_root=ROOT)

    payload = _load_launch_slo_manifest()
    payload["source_registry_sha256"] = "0" * 64
    payload = _rebind_launch_slo_manifest(payload)
    with pytest.raises(ContractValidationError, match="launch_slo.source_registry_hash"):
        validate_contract(payload, repo_root=ROOT)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda rows: rows.clear(), "launch_slo.omitted_source"),
        (
            lambda rows: rows.append(
                {**deepcopy(rows[0]), "source_id": "unknown_launch_source"}
            ),
            "launch_slo.unknown_source",
        ),
        (lambda rows: rows.append(deepcopy(rows[0])), "launch_slo.duplicate_source"),
    ],
)
def test_launch_slo_source_set_is_exact_and_closed(mutation, expected_code: str) -> None:
    payload = _load_launch_slo_manifest()
    mutation(payload["sources"])
    payload = _rebind_launch_slo_manifest(payload)
    with pytest.raises(ContractValidationError, match=expected_code):
        validate_contract(payload, repo_root=ROOT)


def test_launch_slo_rejects_source_owner_and_registry_binding_mismatch() -> None:
    payload = _load_launch_slo_manifest()
    payload["sources"][0]["owner"] = "another_owner"
    payload["sources"][0]["registry_binding"]["freshness_slo_seconds"] = 3600
    payload = _rebind_launch_slo_manifest(payload)

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)
    assert "launch_slo.owner_mismatch" in str(caught.value)
    assert "launch_slo.registry_mismatch" in str(caught.value)


def test_launch_slo_rejects_vague_denominators_missing_stage_gates_and_weighting() -> None:
    payload = _load_launch_slo_manifest()
    payload["sources"][0]["denominator_policy"]["upstream_outage_treatment"] = (
        "exclude_upstream_outage"
    )
    del payload["sources"][0]["success_gates"]["publication"]
    payload["aggregate_pass_policy"]["weighted_aggregate_allowed"] = True
    payload = _rebind_launch_slo_manifest(payload)

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)
    message = str(caught.value)
    assert "record_denominator_miss_and_upstream_unavailable_observation" in message
    assert "publication" in message
    assert "False was expected" in message


def test_pre_soak_manifest_is_explicitly_unarmed_and_cannot_claim_release_pass() -> None:
    payload = _load_launch_slo_manifest()
    assert payload["state"] == "pre_soak_unarmed"
    assert payload["sources"][0]["activation_state"] == "dark_unarmed"
    assert payload["soak"]["window_start"] is None
    assert payload["soak"]["source_results"] == []
    assert payload["soak"]["aggregate_passed"] is False
    assert all(value is False for value in payload["authority"].values())

    false_pass = deepcopy(payload)
    false_pass["state"] = "soak_complete_passed"
    false_pass["soak"]["aggregate_passed"] = True
    false_pass = _rebind_launch_slo_manifest(false_pass)
    with pytest.raises(ContractValidationError) as caught:
        validate_contract(false_pass, repo_root=ROOT)
    assert "window_start" in str(caught.value)
    assert "telemetry_generation_ref" in str(caught.value)
    assert "source_results" in str(caught.value)


def test_completed_launch_slo_candidate_is_fail_closed_without_external_evidence() -> None:
    valid = _completed_launch_slo_manifest()
    issues = ContractRegistry(ROOT).issues(valid["contract_id"], valid)
    assert {issue.code for issue in issues} == {
        "launch_slo.trusted_evidence_verifier_unavailable"
    }
    with pytest.raises(
        ContractValidationError,
        match="launch_slo.trusted_evidence_verifier_unavailable",
    ):
        validate_contract(valid, repo_root=ROOT)

    denominator = deepcopy(valid)
    denominator["soak"]["source_results"][0]["denominator"] = 335
    denominator = _rebind_launch_slo_manifest(denominator)
    with pytest.raises(ContractValidationError, match="launch_slo.denominator"):
        validate_contract(denominator, repo_root=ROOT)

    outage = deepcopy(valid)
    outage["soak"]["source_results"][0]["upstream_unavailable_observations"] = 2
    outage = _rebind_launch_slo_manifest(outage)
    with pytest.raises(ContractValidationError, match="launch_slo.upstream_outage"):
        validate_contract(outage, repo_root=ROOT)

    critical = deepcopy(valid)
    critical["soak"]["source_results"][0]["critical_failure_types"] = [
        "integrity_failure"
    ]
    critical = _rebind_launch_slo_manifest(critical)
    with pytest.raises(ContractValidationError) as caught:
        validate_contract(critical, repo_root=ROOT)
    assert "launch_slo.source_pass" in str(caught.value)
    assert "launch_slo.aggregate_pass" in str(caught.value)


def test_launch_slo_completed_window_is_exactly_fourteen_days() -> None:
    payload = _completed_launch_slo_manifest()
    payload["soak"]["window_end"] = "2026-08-17T23:59:59Z"
    payload = _rebind_launch_slo_manifest(payload)
    with pytest.raises(ContractValidationError, match="launch_slo.soak_window"):
        validate_contract(payload, repo_root=ROOT)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda result, payload: result.update(
                expected_opportunities=1,
                denominator=1,
                successful_opportunities=1,
                misses=0,
                upstream_unavailable_observations=0,
                maximum_consecutive_misses_observed=0,
                stage_successes={
                    stage: 1 for stage in result["stage_successes"]
                },
            ),
            "launch_slo.expected_opportunities",
        ),
        (
            lambda result, payload: result.update(
                excluded_predeclared_maintenance=335,
                denominator=1,
                successful_opportunities=1,
                misses=0,
                upstream_unavailable_observations=0,
                maximum_consecutive_misses_observed=0,
                stage_successes={
                    stage: 1 for stage in result["stage_successes"]
                },
            ),
            "launch_slo.maintenance_exclusion_unverifiable",
        ),
        (
            lambda result, payload: result.update(
                excluded_source_native_nonpublication=335,
                denominator=1,
                successful_opportunities=1,
                misses=0,
                upstream_unavailable_observations=0,
                maximum_consecutive_misses_observed=0,
                stage_successes={
                    stage: 1 for stage in result["stage_successes"]
                },
            ),
            "launch_slo.nonpublication_must_remain_in_denominator",
        ),
        (
            lambda result, payload: result["stage_successes"].update(parse=1),
            "launch_slo.stage_reconciliation",
        ),
    ],
)
def test_launch_slo_rejects_manufactured_denominators_and_stage_passes(
    mutation, expected_code: str
) -> None:
    payload = _completed_launch_slo_manifest()
    mutation(payload["soak"]["source_results"][0], payload)
    payload = _rebind_launch_slo_manifest(payload)
    with pytest.raises(ContractValidationError, match=expected_code):
        validate_contract(payload, repo_root=ROOT)


def test_launch_slo_rejects_non_content_addressed_evidence() -> None:
    payload = _completed_launch_slo_manifest()
    payload["soak"]["raw_telemetry_refs"] = ["fake:raw"]
    payload = _rebind_launch_slo_manifest(payload)

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)
    assert "is not of type 'object'" in str(caught.value)


def test_launch_slo_rejects_inexact_or_noncanonical_utc_windows() -> None:
    payload = _completed_launch_slo_manifest()
    payload["soak"]["window_end"] = "2026-08-18T00:00:00.999Z"
    payload = _rebind_launch_slo_manifest(payload)
    with pytest.raises(ContractValidationError, match="launch_slo.soak_window"):
        validate_contract(payload, repo_root=ROOT)

    payload = _completed_launch_slo_manifest()
    payload["soak"]["window_start"] = "2026-08-03T17:00:00-07:00"
    payload["soak"]["window_end"] = "2026-08-17T17:00:00-07:00"
    payload = _rebind_launch_slo_manifest(payload)
    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)
    assert "does not match" in str(caught.value)
    assert "launch_slo.soak_window" in str(caught.value)

    payload = _completed_launch_slo_manifest()
    payload["soak"]["window_start"] = "3000-01-01T00:00:00.000001Z"
    payload["soak"]["window_end"] = "3000-01-15T00:00:00.000001Z"
    payload = _rebind_launch_slo_manifest(payload)
    with pytest.raises(ContractValidationError, match="launch_slo.schedule_alignment"):
        validate_contract(payload, repo_root=ROOT)


def test_launch_slo_rejects_predecessor_digest_mismatch_and_artifact_reuse() -> None:
    payload = _completed_launch_slo_manifest()
    payload["supersedes_manifest_content_sha256"] = "f" * 64
    payload = _rebind_launch_slo_manifest(payload)
    with pytest.raises(ContractValidationError, match="launch_slo.predecessor_identity"):
        validate_contract(payload, repo_root=ROOT)

    payload = _completed_launch_slo_manifest()
    reused = deepcopy(payload["soak"]["telemetry_generation_ref"])
    reused["kind"] = "ci_validation"
    payload["soak"]["ci_validation_receipt_ref"] = reused
    payload = _rebind_launch_slo_manifest(payload)
    with pytest.raises(ContractValidationError, match="launch_slo.artifact_role_reuse"):
        validate_contract(payload, repo_root=ROOT)


def test_launch_slo_artifacts_bind_predecessor_window_and_source_scope() -> None:
    payload = _completed_launch_slo_manifest()
    artifact = payload["soak"]["raw_telemetry_refs"][0]
    artifact["scheduled_manifest_id"] = "biocatalyst_launch_slo_" + "f" * 24
    artifact["window_start"] = "2026-08-05T00:00:00Z"
    artifact["source_id"] = "unknown_source"
    payload = _rebind_launch_slo_manifest(payload)

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)
    message = str(caught.value)
    assert "launch_slo.artifact_manifest_binding" in message
    assert "launch_slo.artifact_window_binding" in message
    assert "launch_slo.artifact_source_binding" in message


def test_launch_slo_rejects_completed_dark_or_blocked_claims() -> None:
    payload = _completed_launch_slo_manifest()
    payload["sources"][0]["activation_state"] = "dark_unarmed"
    payload["soak"]["scheduling_blockers"] = ["operator_arming"]
    payload = _rebind_launch_slo_manifest(payload)

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)
    assert "launch_slo.passed_soak_activation" in str(caught.value)
    assert "launch_slo.active_soak_blockers" in str(caught.value)


@pytest.mark.parametrize(
    "bad_value",
    ["not-a-number", 10**400],
)
def test_launch_slo_malformed_numbers_fail_as_contract_validation(
    bad_value,
) -> None:
    payload = _completed_launch_slo_manifest()
    payload["sources"][0]["error_budget"][
        "minimum_opportunity_success_ratio"
    ] = bad_value
    payload = _rebind_launch_slo_manifest(payload)

    with pytest.raises(ContractValidationError):
        validate_contract(payload, repo_root=ROOT)


def test_launch_slo_cyclic_python_mapping_fails_as_contract_validation() -> None:
    payload = _load_launch_slo_manifest()
    payload["cycle"] = payload

    with pytest.raises(ContractValidationError, match="schema.cyclic_document"):
        validate_contract(payload, repo_root=ROOT)


def test_launch_slo_superseded_label_cannot_smuggle_a_pass() -> None:
    payload = _completed_launch_slo_manifest()
    payload["state"] = "superseded"
    payload["sources"][0]["activation_state"] = "dark_unarmed"
    payload["soak"]["scheduling_blockers"] = ["operator_arming"]
    payload = _rebind_launch_slo_manifest(payload)

    with pytest.raises(ContractValidationError) as caught:
        validate_contract(payload, repo_root=ROOT)
    assert "launch_slo.trusted_evidence_verifier_unavailable" in str(caught.value)
    assert "False was expected" in str(caught.value)
    assert "is expected to be empty" in str(caught.value)


def test_launch_slo_extreme_python_integer_fails_as_contract_validation() -> None:
    payload = _completed_launch_slo_manifest()
    payload["soak"]["source_results"][0]["expected_opportunities"] = 10**5000

    with pytest.raises(
        ContractValidationError, match="schema.invalid_in_memory_document"
    ):
        validate_contract(payload, repo_root=ROOT)
