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
from engine.research_factory import ledger as rf_ledger
from engine.research_factory import schema as rf_schema
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
    first_line = (
        (ROOT / "data" / "research_factory" / "candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    hostile = json.loads(first_line)
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
        "episode_set_id": None,
        "evidence_ref": None,
    }
    assert spec["w5_evaluation_join"] == {
        "status": "not_run",
        "evaluation_id": None,
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
                "episode_set_id",
            ),
            "fabricated",
        ),
        (
            (
                "artifacts",
                "market_memory_conformance",
                "spec",
                "w5_evaluation_join",
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
