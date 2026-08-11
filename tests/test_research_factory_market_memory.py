"""Hostile W6A tests for the pure Market Memory candidate adapter."""

from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_forward as forward
from engine.research_factory import adapter_market_memory as adapter
from engine.research_factory import challenge as rf_challenge
from engine.research_factory import ledger as rf_ledger
from engine.research_factory import schema as rf_schema
from engine.research_factory import state as rf_state
from scripts import research_factory_ingest as rf_ingest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "engine" / "research_factory" / "adapter_market_memory.py"
AUTHORITY_ALLOWLIST = ROOT / "data" / "research_factory" / "authority_allowlist.json"
LEGACY_JOBS = ROOT / ".github" / "ci" / "legacy-jobs.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _trial(*, trial_key: str = "synthetic.spy.close.v1") -> dict[str, Any]:
    return forward.build_trial_registration(
        trial_key=trial_key,
        registered_at="2026-08-01T12:00:00.000000Z",
        state_requirements={
            "state_schema": forward.STATE_SNAPSHOT_SCHEMA,
            "context_schema": market_memory.AS_KNOWN_AT_SCHEMA,
            "minimum_observed_domains": 2,
            "required_observed_domains": list(forward.CANONICAL_DOMAINS[:2]),
        },
        target={
            "target_id": "spy.close.return",
            "formula": "outcome_close / input_close - 1",
            "formula_version": "synthetic.v1",
            "value_type": "number",
            "unit": "ratio",
            "categories": [],
        },
        marks={
            "input_mark": "close",
            "outcome_mark": "close",
            "cost_convention": "none",
            "benchmark": "zero_return",
        },
        horizon={
            "anchor": "decision_cutoff",
            "start_offset_seconds": 86_400,
            "end_offset_seconds": 172_800,
            "evaluation_offset_seconds": 172_800,
        },
        distribution={"kind": "scalar", "quantile_levels": [], "categories": []},
        proper_score={"name": "squared_error", "orientation": "lower_is_better"},
        baselines=[
            {
                "baseline_id": "zero_return",
                "baseline_version": "synthetic.v1",
                "config_sha256": "4" * 64,
            }
        ],
        splits={
            "development_start": "2020-01-01T00:00:00.000000Z",
            "development_end": "2022-01-01T00:00:00.000000Z",
            "test_start": "2022-01-01T00:00:00.000000Z",
            "test_end": "2024-01-01T00:00:00.000000Z",
            "live_forward_start": "2026-08-02T00:00:00.000000Z",
        },
        purge={"enabled": True, "before_seconds": 172_800, "after_seconds": 0},
        embargo={"enabled": True, "duration_seconds": 172_800},
        dependence={
            "keys": ["context_id", "subject_id"],
            "clustering": "effective_event_cluster",
            "cluster_version": "synthetic.v1",
        },
        trial_budget={
            "max_trials": 10,
            "max_variants": 2,
            "family_trials_already_registered": 0,
        },
        abstention={
            "required": True,
            "minimum_observed_domains": 2,
            "allowed_reasons": [
                "insufficient_domains",
                "policy_expired",
                "required_domain_missing",
            ],
        },
        expiry={"expires_at": "2027-01-01T00:00:00.000000Z", "action": "abstain"},
        demotion={
            "enabled": True,
            "triggers": [
                "baseline_underperformance",
                "broken_lineage",
                "calibration_decay",
            ],
        },
        implementation={
            "model_sha256": "5" * 64,
            "code_sha256": "6" * 64,
            "config_sha256": "7" * 64,
        },
    )


def _bytes(trial: dict[str, Any] | None = None) -> bytes:
    return forward.canonical_json_bytes(trial or _trial())


def _candidate(
    *, trial_bytes: bytes | None = None, created_at: str = "2026-08-10T12:00:00.000000Z"
) -> dict[str, Any]:
    return adapter.build_market_memory_candidate(
        exact_trial_registration_bytes=trial_bytes or _bytes(),
        created_at=created_at,
    )


def _rehash_trial(trial: dict[str, Any]) -> bytes:
    core = copy.deepcopy(trial)
    core["trial_registration_id"] = ""
    trial["trial_registration_id"] = (
        "mmtrial_" + hashlib.sha256(forward.canonical_json_bytes(core)).hexdigest()
    )
    return forward.canonical_json_bytes(trial)


def _mutate(candidate: dict[str, Any], path: tuple[str, ...], value: object) -> dict:
    hostile = copy.deepcopy(candidate)
    cursor = hostile
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    return hostile


def _rehash_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    hostile = copy.deepcopy(candidate)
    semantic = copy.deepcopy(hostile)
    semantic.pop("candidate_id")
    semantic.pop("created_at")
    hostile["candidate_id"] = (
        "rf-market-memory-"
        + hashlib.sha256(forward.canonical_json_bytes(semantic)).hexdigest()
    )
    return hostile


def _generic_candidate() -> dict[str, Any]:
    first_line = (
        (ROOT / "data" / "research_factory" / "candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    return json.loads(first_line)


def test_canonical_candidate_enums_are_extended_as_one_conforming_tuple() -> None:
    assert adapter.MARKET_MEMORY_CANDIDATE_SOURCE in rf_schema.SOURCES
    assert adapter.MARKET_MEMORY_CANDIDATE_TYPE in rf_schema.CANDIDATE_TYPES
    assert adapter.MARKET_MEMORY_CANDIDATE_DOMAIN in rf_schema.DOMAINS

    candidate = _candidate()
    assert (candidate["source"], candidate["candidate_type"], candidate["domain"]) == (
        "market_memory",
        "market_memory_candidate",
        "market_memory",
    )
    assert rf_schema.validate_candidate(candidate) == []


def test_generic_rf_ingest_rejects_relabelled_legacy_row_without_conformance() -> None:
    hostile = _generic_candidate()
    hostile.update(
        source="market_memory",
        candidate_type="market_memory_candidate",
        domain="market_memory",
    )
    hostile.pop("artifacts")

    violations = rf_schema.validate_candidate(hostile)
    assert violations
    assert any("Market Memory structural projection" in row for row in violations)


def test_generic_ingest_never_persists_invalid_market_memory_discriminators(
    tmp_path: Path,
) -> None:
    hostile = _mutate(
        _candidate(),
        ("artifacts", "market_memory_conformance", "authority_granted"),
        True,
    )
    rf_dir = tmp_path / "rf"
    result = rf_ingest.run_ingest(
        [hostile],
        oracle_registry_path=tmp_path / "absent-oracle.jsonl",
        species_registry_path=tmp_path / "absent-species.json",
        machine_registry_path=tmp_path / "absent-machine.jsonl",
        trial_ledger_path=tmp_path / "absent-trials.jsonl",
        rf_dir=rf_dir,
        dry_run=False,
    )
    rf_ingest.run_ingest(
        [copy.deepcopy(hostile)],
        oracle_registry_path=tmp_path / "absent-oracle.jsonl",
        species_registry_path=tmp_path / "absent-species.json",
        machine_registry_path=tmp_path / "absent-machine.jsonl",
        trial_ledger_path=tmp_path / "absent-trials.jsonl",
        rf_dir=rf_dir,
        dry_run=False,
    )

    assert len(result.registered) == 0
    assert len(result.dropped) == 1
    assert result.dropped[0][1] == "schema_rejected"
    rows = rf_ledger.load_jsonl(rf_dir / "candidates.jsonl")
    assert len(rows) == 1
    stored = rows[0]
    assert stored["status"] == "schema_rejected"
    assert (
        stored["source"],
        stored["candidate_type"],
        stored["domain"],
    ) == (
        "schema_rejected_input",
        "schema_rejected_input",
        "schema_rejected_input",
    )
    assert not any(
        value == marker
        for value, marker in zip(
            (stored["source"], stored["candidate_type"], stored["domain"]),
            ("market_memory", "market_memory_candidate", "market_memory"),
        )
    )
    transitions = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
    assert len(transitions) == 1
    assert transitions[0]["to"] == "schema_rejected"
    assert "must remain zero authority" in transitions[0]["reason_text"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hypothesis", {"action_authority": {"may_trade": True}}),
        ("hypothesis", "Market Memory candidate may rank and trade."),
        ("hypothesis", "x" * 513),
        ("mechanism", {"authority_granted": True}),
        ("mechanism", "Authority granted; this candidate may execute."),
        ("mechanism", "x" * 257),
    ],
)
def test_generic_ledger_rejects_market_memory_text_payloads_even_when_rehashed(
    tmp_path: Path, field: str, value: object
) -> None:
    hostile = _candidate()
    hostile[field] = value
    hostile = _rehash_candidate(hostile)
    path = tmp_path / "candidates.jsonl"

    violations = rf_schema.validate_candidate(hostile)
    assert any(f"{field} must be bounded exact-string" in row for row in violations)
    with pytest.raises(ValueError, match="failed schema validation"):
        rf_ledger.append_row(path, hostile, validate_fn=rf_schema.validate_candidate)
    assert not path.exists()


def test_generic_ledger_rejects_regex_shaped_impossible_market_memory_utc(
    tmp_path: Path,
) -> None:
    hostile = _candidate()
    hostile["created_at"] = "2026-02-30T12:00:00.000000Z"
    path = tmp_path / "candidates.jsonl"

    violations = rf_schema.validate_candidate(hostile)
    assert any("created_at is not real canonical" in row for row in violations)
    with pytest.raises(ValueError, match="failed schema validation"):
        rf_ledger.append_row(path, hostile, validate_fn=rf_schema.validate_candidate)
    assert not path.exists()


def test_candidate_and_ledger_reject_dict_subclass_masked_get_without_write(
    tmp_path: Path,
) -> None:
    class MaskedGetDict(dict):
        def get(self, key: object, default: object = None) -> object:
            if key == "authority":
                return "display_only"
            if key == "source":
                return "human"
            return super().get(key, default)

    hostile = MaskedGetDict(_candidate())
    dict.__setitem__(hostile, "authority", "scored")
    path = tmp_path / "candidates.jsonl"

    assert rf_schema.validate_candidate(hostile) == [
        "candidate: row must be an exact dict"
    ]
    with pytest.raises(ValueError, match="row must be an exact dict"):
        rf_ledger.append_row(path, hostile, validate_fn=rf_schema.validate_candidate)
    assert not path.exists()
    drop_dir = tmp_path / "drops"
    with pytest.raises(ValueError, match="row must be an exact dict"):
        rf_ingest._write_drop_candidate_and_transition(hostile, {}, drop_dir)
    assert not drop_dir.exists()


@pytest.mark.parametrize("field", ["source", "candidate_type", "domain"])
def test_candidate_and_ledger_reject_stateful_string_subclass_without_write(
    tmp_path: Path,
    field: str,
) -> None:
    class StatefulString(str):
        comparisons = 0

        def __eq__(self, other: object) -> bool:
            type(self).comparisons += 1
            return type(self).comparisons % 2 == 1

        def __hash__(self) -> int:
            return hash("market_memory")

    hostile = _candidate()
    hostile[field] = StatefulString(hostile[field])
    path = tmp_path / f"{field}.jsonl"

    violations = rf_schema.validate_candidate(hostile)
    assert any(f"{field} must be an exact string" in row for row in violations)
    assert StatefulString.comparisons == 0
    with pytest.raises(
        ValueError,
        match="non-exact or non-JSON-native value",
    ):
        rf_ledger.append_row(path, hostile, validate_fn=rf_schema.validate_candidate)
    assert StatefulString.comparisons == 0
    assert not path.exists()
    drop_dir = tmp_path / "drops"
    with pytest.raises(
        ValueError,
        match="non-exact or non-JSON-native value",
    ):
        rf_ingest._write_drop_candidate_and_transition(hostile, {}, drop_dir)
    assert StatefulString.comparisons == 0
    assert not drop_dir.exists()


def test_ledger_validates_and_persists_one_detached_canonical_view(
    tmp_path: Path,
) -> None:
    row = {
        "z": 1,
        "authority": "display_only",
        "nested": {"value": "safe"},
    }
    seen: list[dict[str, Any]] = []

    def validate(frozen: dict[str, Any]) -> list[str]:
        assert frozen is not row
        assert type(frozen) is dict
        assert type(frozen["nested"]) is dict
        row["nested"]["value"] = "mutated-after-freeze"
        seen.append(frozen)
        return []

    path = tmp_path / "one-view.jsonl"
    rf_ledger.append_row(path, row, validate_fn=validate)

    assert seen[0]["nested"]["value"] == "safe"
    assert path.read_bytes() == (
        b'{"authority":"display_only","nested":{"value":"safe"},"z":1}\n'
    )


def test_ledger_rejects_validator_mutation_before_creating_path(tmp_path: Path) -> None:
    row = {"authority": "display_only", "value": "safe"}

    def mutate(frozen: dict[str, Any]) -> list[str]:
        frozen["authority"] = "scored"
        return []

    path = tmp_path / "validator-mutation.jsonl"
    with pytest.raises(ValueError, match="validate_fn mutated the frozen row"):
        rf_ledger.append_row(path, row, validate_fn=mutate)
    assert not path.exists()


def test_write_jsonl_rejects_scored_masked_dict_without_creating_path(
    tmp_path: Path,
) -> None:
    class ScoredMaskedDict(dict):
        def get(self, key: object, default: object = None) -> object:
            if key == "authority":
                return "display_only"
            return super().get(key, default)

    hostile = ScoredMaskedDict({"authority": "scored", "value": "hidden"})
    path = tmp_path / "nested" / "masked.jsonl"
    with pytest.raises(ValueError, match="row must be an exact dict"):
        rf_ledger.write_jsonl(path, [hostile])
    assert not path.parent.exists()


def test_write_jsonl_candidate_path_validates_before_any_write(tmp_path: Path) -> None:
    valid = _generic_candidate()
    hostile = _mutate(
        _candidate(),
        ("artifacts", "market_memory_conformance", "authority_granted"),
        True,
    )
    path = tmp_path / "nested" / "candidates.jsonl"

    with pytest.raises(ValueError, match="candidate schema validation"):
        rf_ledger.write_jsonl(path, [valid, hostile])
    assert not path.parent.exists()


def test_candidate_append_cannot_bypass_owned_validator_with_permissive_callback(
    tmp_path: Path,
) -> None:
    hostile = _mutate(
        _candidate(),
        ("artifacts", "market_memory_conformance", "authority_granted"),
        True,
    )
    path = tmp_path / "candidates.jsonl"
    with pytest.raises(ValueError, match="failed schema validation"):
        rf_ledger.append_row(path, hostile, validate_fn=lambda _row: [])
    assert not path.exists()


def test_write_jsonl_rejects_candidate_validator_mutation_without_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _generic_candidate()

    def mutate(frozen: dict[str, Any]) -> list[str]:
        frozen["authority"] = "scored"
        return []

    monkeypatch.setattr(rf_schema, "validate_candidate", mutate)
    path = tmp_path / "nested" / "candidates.jsonl"
    with pytest.raises(ValueError, match="candidate validator mutated"):
        rf_ledger.write_jsonl(path, [candidate])
    assert not path.parent.exists()


def test_write_jsonl_generic_candidate_uses_frozen_canonical_bytes(
    tmp_path: Path,
) -> None:
    candidate = _generic_candidate()
    expected = forward.canonical_json_bytes(candidate) + b"\n"
    path = tmp_path / "candidates.jsonl"

    rf_ledger.write_jsonl(path, [candidate])

    candidate["authority"] = "scored"
    assert path.read_bytes() == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", "human"),
        ("candidate_type", "external_idea"),
        ("domain", "macro"),
    ],
)
def test_generic_rf_ingest_rejects_partial_market_memory_discriminator_tuple(
    field: str, value: str
) -> None:
    hostile = _candidate()
    hostile[field] = value
    violations = rf_schema.validate_candidate(hostile)
    assert any("discriminator tuple must be exact" in row for row in violations)


def test_generic_candidate_without_reserved_market_memory_marker_is_unchanged() -> None:
    generic = _generic_candidate()
    generic["artifacts"] = {
        "generic_conformance": {
            "authority_granted": True,
            "action_authority": {"may_trade": True},
        }
    }
    assert rf_schema.validate_candidate(generic) == []


@pytest.mark.parametrize(
    "marker",
    [
        "research_factory.market_memory_candidate_conformance.v1",
        "research_factory.market_memory_candidate_spec.v1",
        "rf-market-memory-fully-relabelled",
        "mmrfspec_fully_relabelled",
        "mmtrial_fully_relabelled",
        "market_memory",
        "market_memory_candidate",
        "market_memory_w2a_preregistration",
        {"trial_read_back": {}},
        {"w4_retrieval_join": {}},
        {"w5_operating_cortex_join": {}},
        {"w5_evaluation_join": {}},
        {"trial_registration_id": "renamed"},
        {"trial_registration_sha256": "renamed"},
        {"trial_registration_bytes": 1},
    ],
    ids=(
        "conformance-schema",
        "spec-schema",
        "candidate-prefix",
        "spec-prefix",
        "trial-prefix",
        "source-value",
        "type-value",
        "spec-source-value",
        "read-back-key",
        "w4-join-key",
        "w5-join-key",
        "legacy-w5-join-key",
        "trial-id-key",
        "trial-sha-key",
        "trial-bytes-key",
    ),
)
@pytest.mark.parametrize("placement", ["root", "nested-dict", "nested-list"])
def test_recursive_market_memory_ownership_survives_relabel_and_any_placement(
    tmp_path: Path,
    marker: object,
    placement: str,
) -> None:
    hostile = _generic_candidate()
    hostile.update(source="human", candidate_type="external_idea", domain="macro")
    if placement == "root":
        hostile["renamed_subtype"] = copy.deepcopy(marker)
    elif placement == "nested-dict":
        hostile["artifacts"] = {
            "renamed_outer": {"renamed_inner": copy.deepcopy(marker)}
        }
    else:
        hostile["artifacts"] = {
            "renamed_outer": [
                {"renamed_inner": [copy.deepcopy(marker)]},
            ]
        }

    violations = rf_schema.validate_candidate(hostile)
    assert any("Market Memory structural projection" in row for row in violations)
    assert any("discriminator tuple must be exact" in row for row in violations)

    path = tmp_path / f"{placement}.jsonl"
    with pytest.raises(ValueError, match="failed schema validation"):
        rf_ledger.append_row(path, hostile, validate_fn=rf_schema.validate_candidate)
    assert not path.exists()


def test_recursive_market_memory_rejection_persists_only_generic_audit_envelope(
    tmp_path: Path,
) -> None:
    hostile = _generic_candidate()
    hostile.update(source="human", candidate_type="external_idea", domain="macro")
    hostile["artifacts"] = {
        "renamed_outer": [
            {
                "renamed_inner": {
                    "trial_read_back": {},
                    "identity": "mmtrial_fully-relabelled",
                }
            }
        ]
    }
    stable_proposal = {
        key: value
        for key, value in hostile.items()
        if key not in {"candidate_id", "created_at", "as_of"}
    }
    expected_proposal_hash = hashlib.sha256(
        forward.canonical_json_bytes(stable_proposal)
    ).hexdigest()
    rf_dir = tmp_path / "rf"

    result = rf_ingest.run_ingest(
        [hostile],
        oracle_registry_path=tmp_path / "absent-oracle.jsonl",
        species_registry_path=tmp_path / "absent-species.json",
        machine_registry_path=tmp_path / "absent-machine.jsonl",
        trial_ledger_path=tmp_path / "absent-trials.jsonl",
        rf_dir=rf_dir,
        dry_run=False,
    )

    assert len(result.registered) == 0
    assert len(result.dropped) == 1
    candidates = rf_ledger.load_jsonl(rf_dir / "candidates.jsonl")
    transitions = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
    assert len(candidates) == len(transitions) == 1
    assert candidates[0]["candidate_id"].startswith("rf-schema-rejected-")
    assert transitions[0]["candidate_id"] == candidates[0]["candidate_id"]
    assert transitions[0]["_proposal_hash"] == expected_proposal_hash
    assert "Market Memory structural projection" in transitions[0]["reason_text"]
    assert not rf_schema.has_market_memory_owned_marker(candidates[0])
    assert not rf_schema.has_market_memory_owned_marker(transitions[0])


@pytest.mark.parametrize(
    ("marker_name", "field", "value"),
    [
        ("source", "source", "market_memory"),
        ("candidate_type", "candidate_type", "market_memory_candidate"),
        ("domain", "domain", "market_memory"),
        ("candidate_id", "candidate_id", "rf-market-memory-relabeled"),
        ("spec_ref", "spec_ref", "mmrfspec_relabeled"),
        (
            "hypothesis",
            "hypothesis",
            (
                "Conformance candidate for frozen Market Memory trial "
                "synthetic.spy.close.v1; no episodic retrieval or Operating "
                "Cortex packet is claimed."
            ),
        ),
        (
            "mechanism",
            "mechanism",
            (
                "Read-only pointer to an exact W2A preregistration; W4 episodic "
                "retrieval and W5 Operating Cortex packet joins are deferred."
            ),
        ),
        (
            "failure_modes",
            "expected_failure_modes",
            [
                "w4_episodic_retrieval_not_bound",
                "w5_operating_cortex_not_bound",
            ],
        ),
        (
            "evaluation_plan",
            "evaluation_plan",
            {
                "status": "not_run",
                "primary_metric": None,
                "horizon_d": None,
                "min_n": None,
                "fdr_scope": None,
                "expected_half_life_d": None,
                "defaulted": False,
                "source": "market_memory_w2a_preregistration",
            },
        ),
        (
            "flags",
            "flags",
            [
                "market_memory_context_only",
                "w4_episodic_retrieval_join_deferred",
                "w5_operating_cortex_join_deferred",
            ],
        ),
        (
            "conformance_key",
            "artifacts",
            {
                "market_memory_conformance": {
                    "authority_granted": True,
                    "action_authority": {"may_trade": True},
                }
            },
        ),
        (
            "conformance_schema",
            "artifacts",
            {
                "renamed": {
                    "schema": "research_factory.market_memory_candidate_conformance.v1",
                    "authority_granted": True,
                    "action_authority": {"may_trade": True},
                }
            },
        ),
        (
            "spec_schema",
            "artifacts",
            {
                "renamed": {
                    "schema": "research_factory.market_memory_candidate_spec.v1",
                    "authority_granted": True,
                    "action_authority": {"may_trade": True},
                }
            },
        ),
    ],
)
def test_each_reserved_market_memory_marker_owns_and_blocks_generic_ledger_write(
    tmp_path: Path, marker_name: str, field: str, value: object
) -> None:
    hostile = _generic_candidate()
    hostile["artifacts"] = {
        "generic_conformance": {
            "authority_granted": True,
            "action_authority": {"may_trade": True},
        }
    }
    hostile[field] = copy.deepcopy(value)

    violations = rf_schema.validate_candidate(hostile)
    assert any("Market Memory structural projection" in row for row in violations)
    assert any("discriminator tuple must be exact" in row for row in violations)

    path = tmp_path / f"{marker_name}.jsonl"
    with pytest.raises(ValueError, match="failed schema validation"):
        rf_ledger.append_row(path, hostile, validate_fn=rf_schema.validate_candidate)
    assert not path.exists()


def test_fully_relabelled_market_memory_candidate_cannot_regain_authority_or_write(
    tmp_path: Path,
) -> None:
    hostile = _candidate()
    hostile.update(
        source="human",
        candidate_type="external_idea",
        domain="macro",
    )
    conformance = hostile["artifacts"]["market_memory_conformance"]
    conformance["authority_granted"] = True
    conformance["action_authority"]["may_trade"] = True

    violations = rf_schema.validate_candidate(hostile)
    assert any("discriminator tuple must be exact" in row for row in violations)
    assert any(
        "authority_granted must remain zero authority" in row for row in violations
    )
    assert any(
        "action_authority must remain zero authority" in row for row in violations
    )

    path = tmp_path / "fully-relabelled.jsonl"
    with pytest.raises(ValueError, match="failed schema validation"):
        rf_ledger.append_row(path, hostile, validate_fn=rf_schema.validate_candidate)
    assert not path.exists()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("artifacts", "market_memory_conformance", "authority_granted"), True),
        (("artifacts", "market_memory_conformance", "authority_granted"), 0),
        (("artifacts", "market_memory_conformance", "challenge_completed"), True),
        (("artifacts", "market_memory_conformance", "emission_enabled"), True),
        (("artifacts", "market_memory_conformance", "training_eligible"), True),
        (("artifacts", "market_memory_conformance", "promotion_eligible"), True),
        (
            (
                "artifacts",
                "market_memory_conformance",
                "action_authority",
                "may_rank",
            ),
            True,
        ),
    ],
)
def test_generic_rf_ingest_rejects_market_memory_authority_drift(
    path: tuple[str, ...], value: object
) -> None:
    violations = rf_schema.validate_candidate(_mutate(_candidate(), path, value))
    assert any("must remain zero authority" in row for row in violations)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("spec_ref",), "mmrfspec_" + "0" * 64, "spec_ref does not bind"),
        (
            ("candidate_id",),
            "rf-market-memory-" + "0" * 64,
            "candidate_id does not bind",
        ),
        (
            (
                "artifacts",
                "market_memory_conformance",
                "spec",
                "trial_registration_bytes",
            ),
            256 * 1024 + 1,
            "trial_registration_bytes is out of bounds",
        ),
        (("transition_log",), [{}], "transition_log must remain"),
        (("claim_shape",), "lead_lag", "claim_shape must remain"),
        (
            ("evaluation_plan", "status"),
            "complete",
            "evaluation_plan must remain",
        ),
        (
            ("evaluation_plan", "defaulted"),
            0,
            "evaluation_plan must remain",
        ),
    ],
)
def test_generic_rf_ingest_rejects_market_memory_structural_drift(
    path: tuple[str, ...], value: object, message: str
) -> None:
    violations = rf_schema.validate_candidate(_mutate(_candidate(), path, value))
    assert any(message in row for row in violations), violations


def test_candidate_is_proposed_read_only_and_exactly_zero_authority() -> None:
    trial_bytes = _bytes()
    trial = forward.load_trial_registration_json(trial_bytes)
    candidate = _candidate(trial_bytes=trial_bytes)
    conformance = candidate["artifacts"]["market_memory_conformance"]
    spec = conformance["spec"]

    assert candidate["status"] == "proposed"
    assert candidate["authority"] == "display_only"
    assert candidate["trial_accounting"] == {
        "mode": "read_only",
        "family": None,
        "declared_at": None,
    }
    assert candidate["evaluation_plan"]["status"] == "not_run"
    assert conformance["authority_granted"] is False
    assert conformance["challenge_completed"] is False
    assert conformance["challenge_ref"] is None
    assert conformance["emission_enabled"] is False
    assert conformance["training_eligible"] is False
    assert conformance["promotion_eligible"] is False
    assert conformance["action_authority"]
    assert not any(conformance["action_authority"].values())
    assert spec["w4_retrieval_join"] == {
        "status": "deferred",
        "episodic_retrieval_record_id": None,
        "evidence_ref": None,
    }
    assert spec["w5_operating_cortex_join"] == {
        "status": "deferred",
        "operating_cortex_packet_id": None,
        "evidence_ref": None,
    }
    assert spec["trial_registration_id"] == trial["trial_registration_id"]
    assert spec["trial_registration_sha256"] == hashlib.sha256(trial_bytes).hexdigest()
    assert spec["trial_registration_bytes"] == len(trial_bytes)
    assert spec["trial_read_back"] == {
        "purge": trial["purge"],
        "embargo": trial["embargo"],
        "trial_budget": trial["trial_budget"],
        "implementation": trial["implementation"],
    }
    assert (
        adapter.validate_market_memory_candidate(
            candidate, exact_trial_registration_bytes=trial_bytes
        )
        == candidate
    )


def test_market_memory_is_inert_across_transition_challenge_and_monitor_chain(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    candidate_id = candidate["candidate_id"]
    ingest_dir = tmp_path / "ingest"
    ingest_result = rf_ingest.run_ingest(
        [copy.deepcopy(candidate)],
        oracle_registry_path=tmp_path / "absent-oracle.jsonl",
        species_registry_path=tmp_path / "absent-species.json",
        machine_registry_path=tmp_path / "absent-machine.jsonl",
        trial_ledger_path=tmp_path / "absent-trials.jsonl",
        rf_dir=ingest_dir,
        dry_run=False,
    )
    assert len(ingest_result.registered) == 0
    assert [row[1] for row in ingest_result.dropped] == ["transition_rejected"]
    assert not ingest_dir.exists()

    transition = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": "proposed",
        "to": "registered",
        "reason_code": "schema_valid",
        "reason_text": "generic lifecycle admission attempt",
        "actor": "script",
        "actor_ref": None,
        "artifact_refs": [],
        "kill_evidence": None,
        "as_of": "2026-08-10T12:01:00.000000Z",
    }
    assert any(
        "proposed-only" in row for row in rf_schema.validate_transition(transition)
    )
    with pytest.raises(rf_state.IllegalTransition, match="proposed-only"):
        rf_state.transition(
            "proposed",
            "registered",
            "script",
            transition,
            candidate=candidate,
        )
    transition_path = tmp_path / "transitions.jsonl"
    with pytest.raises(ValueError, match="failed schema validation"):
        rf_ledger.append_row(
            transition_path,
            transition,
            validate_fn=lambda _row: [],
        )
    assert not transition_path.exists()

    challenge = {
        "schema": "research_factory.challenge.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "challenged_at": "2026-08-10T12:02:00.000000Z",
        "mechanical_probes": {},
    }
    assert any(
        "proposed-only" in row for row in rf_schema.validate_challenge(challenge)
    )
    with pytest.raises(ValueError, match="proposed-only"):
        rf_challenge.build_challenge_input(candidate, root=tmp_path)
    with pytest.raises(ValueError, match="proposed-only"):
        rf_challenge.write_challenge(
            candidate_id,
            {"mechanical_probes": {}},
            root=tmp_path,
        )
    with pytest.raises(ValueError, match="proposed-only"):
        rf_challenge.apply_challenge_transitions(
            candidate_id,
            tmp_path / "never-created.json",
            root=tmp_path,
        )
    assert not (tmp_path / "data" / "research_factory").exists()

    paper_monitor = {
        "schema": "research_factory.paper_monitor.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "as_of": "2026-08-10T12:03:00.000000Z",
        "paper_status": "warmup",
        "action": "continue",
    }
    assert any(
        "proposed-only" in row
        for row in rf_schema.validate_paper_monitor(paper_monitor)
    )
    monitor_path = tmp_path / "paper_monitor.jsonl"
    with pytest.raises(ValueError, match="failed schema validation"):
        rf_ledger.append_row(
            monitor_path,
            paper_monitor,
            validate_fn=lambda _row: [],
        )
    assert not monitor_path.exists()


def test_relabelled_transition_is_blocked_by_detached_market_memory_candidate() -> None:
    candidate = _candidate()
    transition = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": "rf-generic-relabelled",
        "from": "proposed",
        "to": "registered",
        "reason_code": "schema_valid",
        "reason_text": "relabel attempt",
        "actor": "script",
        "actor_ref": None,
        "artifact_refs": [],
        "kill_evidence": None,
        "as_of": "2026-08-10T12:01:00.000000Z",
    }
    with pytest.raises(rf_state.IllegalTransition, match="proposed-only"):
        rf_state.transition(
            "proposed",
            "registered",
            "script",
            transition,
            candidate=candidate,
        )


def test_generic_research_factory_lifecycle_admission_is_unchanged() -> None:
    candidate = _generic_candidate()
    candidate["status"] = "proposed"
    candidate["transition_log"] = []
    candidate_id = candidate["candidate_id"]
    transition = {
        "schema": "research_factory.transition.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "from": "proposed",
        "to": "registered",
        "reason_code": "schema_valid",
        "reason_text": "generic lifecycle remains enabled",
        "actor": "script",
        "actor_ref": None,
        "artifact_refs": [],
        "kill_evidence": None,
        "as_of": "2026-08-10T12:01:00.000000Z",
    }
    assert rf_schema.validate_transition(transition) == []
    rf_state.transition(
        "proposed",
        "registered",
        "script",
        transition,
        candidate=candidate,
    )

    challenge = {
        "schema": "research_factory.challenge.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "challenged_at": "2026-08-10T12:02:00.000000Z",
        "mechanical_probes": {},
    }
    assert rf_schema.validate_challenge(challenge) == []
    paper_monitor = {
        "schema": "research_factory.paper_monitor.v1",
        "authority": "display_only",
        "candidate_id": candidate_id,
        "as_of": "2026-08-10T12:03:00.000000Z",
        "paper_status": "warmup",
        "action": "continue",
    }
    assert rf_schema.validate_paper_monitor(paper_monitor) == []


def test_semantic_candidate_and_spec_ids_exclude_projection_created_at() -> None:
    trial_bytes = _bytes()
    first = _candidate(
        trial_bytes=trial_bytes, created_at="2026-08-10T12:00:00.000000Z"
    )
    later = _candidate(
        trial_bytes=trial_bytes, created_at="2026-08-11T12:00:00.000000Z"
    )
    assert first["candidate_id"] == later["candidate_id"]
    assert first["spec_ref"] == later["spec_ref"]
    assert {key: value for key, value in first.items() if key != "created_at"} == {
        key: value for key, value in later.items() if key != "created_at"
    }

    different = _candidate(
        trial_bytes=_bytes(_trial(trial_key="synthetic.spy.other.v1"))
    )
    assert different["candidate_id"] != first["candidate_id"]
    assert different["spec_ref"] != first["spec_ref"]


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b' {"schema":"market_memory.trial_registration.v1"}',
        b'{"schema":"x","schema":"y"}',
        b"\xef\xbb\xbf{}",
        b"x" * (256 * 1024 + 1),
    ],
)
def test_exact_w2a_bytes_fail_closed_before_candidate_projection(body: bytes) -> None:
    with pytest.raises(adapter.MarketMemoryResearchFactoryContractError):
        _candidate(trial_bytes=body)


def test_noncanonical_pretty_bytes_and_nonbytes_are_rejected() -> None:
    trial = _trial()
    pretty = json.dumps(trial, indent=2, sort_keys=True).encode()
    with pytest.raises(adapter.MarketMemoryResearchFactoryContractError):
        _candidate(trial_bytes=pretty)
    with pytest.raises(adapter.MarketMemoryResearchFactoryContractError):
        adapter.build_market_memory_candidate(
            exact_trial_registration_bytes=bytearray(_bytes()),  # type: ignore[arg-type]
            created_at="2026-08-10T12:00:00.000000Z",
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("purge", "enabled"), False),
        (("embargo", "enabled"), False),
        (("trial_budget", "max_trials"), True),
        (("implementation", "code_sha256"), "not-a-sha"),
        (("emission_enabled",), True),
        (("authority", "training_eligible"), True),
    ],
)
def test_owner_rejects_hostile_leakage_budget_implementation_and_authority(
    path: tuple[str, ...], value: object
) -> None:
    trial = _trial()
    cursor = trial
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    hostile_bytes = _rehash_trial(trial)
    with pytest.raises(adapter.MarketMemoryResearchFactoryContractError):
        _candidate(trial_bytes=hostile_bytes)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("source",), "human"),
        (("candidate_type",), "external_idea"),
        (("domain",), "macro"),
        (("status",), "screened"),
        (("trial_accounting", "mode"), "rf_family"),
        (("evaluation_plan", "status"), "complete"),
        (("artifacts", "market_memory_conformance", "authority_granted"), True),
        (("artifacts", "market_memory_conformance", "challenge_completed"), True),
        (("artifacts", "market_memory_conformance", "emission_enabled"), True),
        (("artifacts", "market_memory_conformance", "training_eligible"), True),
        (("artifacts", "market_memory_conformance", "promotion_eligible"), True),
        (
            (
                "artifacts",
                "market_memory_conformance",
                "action_authority",
                "may_rank",
            ),
            True,
        ),
        (
            (
                "artifacts",
                "market_memory_conformance",
                "spec",
                "w4_retrieval_join",
                "episodic_retrieval_record_id",
            ),
            "fabricated",
        ),
        (
            (
                "artifacts",
                "market_memory_conformance",
                "spec",
                "w5_operating_cortex_join",
                "status",
            ),
            "complete",
        ),
        (
            (
                "artifacts",
                "market_memory_conformance",
                "spec",
                "trial_read_back",
                "trial_budget",
                "max_trials",
            ),
            999,
        ),
    ],
)
def test_candidate_conformance_mutations_are_rejected(
    path: tuple[str, ...], value: object
) -> None:
    trial_bytes = _bytes()
    candidate = _candidate(trial_bytes=trial_bytes)
    with pytest.raises(adapter.MarketMemoryResearchFactoryContractError):
        adapter.validate_market_memory_candidate(
            _mutate(candidate, path, value),
            exact_trial_registration_bytes=trial_bytes,
        )


def test_ids_created_at_and_exact_source_join_are_all_authenticated() -> None:
    trial_bytes = _bytes()
    candidate = _candidate(trial_bytes=trial_bytes)
    mutations = (
        _mutate(candidate, ("candidate_id",), "rf-market-memory-" + "0" * 64),
        _mutate(candidate, ("spec_ref",), "mmrfspec_" + "0" * 64),
        _mutate(candidate, ("created_at",), "2026-08-01T11:59:59.999999Z"),
    )
    for hostile in mutations:
        with pytest.raises(adapter.MarketMemoryResearchFactoryContractError):
            adapter.validate_market_memory_candidate(
                hostile, exact_trial_registration_bytes=trial_bytes
            )
    with pytest.raises(adapter.MarketMemoryResearchFactoryContractError):
        adapter.validate_market_memory_candidate(
            candidate,
            exact_trial_registration_bytes=_bytes(
                _trial(trial_key="synthetic.spy.unrelated.v1")
            ),
        )


def test_builder_is_detached_and_performs_no_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trial = _trial()
    trial_bytes = _bytes(trial)

    def forbidden_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("W6A adapter must not perform I/O")

    monkeypatch.setattr(builtins, "open", forbidden_io)
    candidate = _candidate(trial_bytes=trial_bytes)
    trial["trial_key"] = "mutated-after-build"
    assert candidate["artifacts"]["market_memory_conformance"]["spec"][
        "trial_registration_id"
    ].startswith("mmtrial_")
    assert (
        adapter.validate_market_memory_candidate(
            candidate, exact_trial_registration_bytes=trial_bytes
        )
        == candidate
    )


def test_adapter_has_no_writer_store_registry_loader_or_production_callsite() -> None:
    source = ADAPTER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(ADAPTER))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not ({"pathlib", "os", "socket", "requests", "urllib"} & imports)
    for forbidden in (
        "route_all",
        "load_candidates",
        "save",
        "write",
        "append",
        "register",
        "materialize",
        "experiment",
    ):
        assert not hasattr(adapter, forbidden)

    callers: set[Path] = set()
    for parent in (ROOT / "app", ROOT / "engine", ROOT / "scripts"):
        for path in parent.rglob("*.py"):
            if path == ADAPTER:
                continue
            candidate_source = path.read_text(encoding="utf-8")
            candidate_tree = ast.parse(candidate_source, filename=str(path))
            if (
                any(
                    isinstance(node, ast.Call)
                    and (
                        isinstance(node.func, ast.Name)
                        and node.func.id == "build_market_memory_candidate"
                        or isinstance(node.func, ast.Attribute)
                        and node.func.attr == "build_market_memory_candidate"
                    )
                    for node in ast.walk(candidate_tree)
                )
                or "adapter_market_memory" in candidate_source
            ):
                callers.add(path.relative_to(ROOT))
    assert callers == set()


def test_ci_explicitly_owns_adapter_schema_hostile_suite_and_authority_read() -> None:
    jobs = LEGACY_JOBS.read_text(encoding="utf-8")
    rf_job = jobs.split("\n  research-factory-authority:", 1)[1].split(
        "\n  cycle-pattern-authority:", 1
    )[0]
    assert "tests/test_research_factory_market_memory.py" in rf_job

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    for path in (
        "engine/research_factory/adapter_market_memory.py",
        "engine/research_factory/schema.py",
        "tests/test_research_factory_market_memory.py",
        "research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md",
        "research/KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md",
    ):
        assert f'- "{path}"' in workflow

    allowlist = json.loads(AUTHORITY_ALLOWLIST.read_text(encoding="utf-8"))
    modules = {entry["module"] for entry in allowlist["allow"]}
    assert "engine/research_factory/adapter_market_memory.py" in modules
