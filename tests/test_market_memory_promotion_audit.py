"""Hostile tests for the inert W7 Market Memory no-promotion audit."""

from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_forward as forward
from engine.neuralweb import market_memory_promotion_audit as audit

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "engine" / "neuralweb" / "market_memory_promotion_audit.py"
SCHEMA = ROOT / "contracts" / "market_memory" / "feature_promotion_audit.v1.schema.json"
LEGACY_JOBS = ROOT / ".github" / "ci" / "legacy-jobs.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
KONSEKI = (
    ROOT
    / "research"
    / "KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md"
)
AUDITED_AT = "2026-08-11T12:00:00.000000Z"


def _artifact(*, audited_at: str = AUDITED_AT) -> dict[str, Any]:
    return audit.build_feature_promotion_audit(audited_at=audited_at)


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _mutate(
    value: dict[str, Any], path: tuple[object, ...], replacement: object
) -> dict:
    hostile = copy.deepcopy(value)
    cursor: Any = hostile
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = replacement
    return hostile


def _reject_runtime_and_schema(hostile: dict[str, Any]) -> None:
    with pytest.raises(audit.MarketMemoryPromotionAuditContractError):
        audit.validate_feature_promotion_audit(hostile)
    with pytest.raises(ValidationError):
        Draft202012Validator(_schema()).validate(hostile)


def test_schema_and_runtime_emit_all_18_sorted_owner_features_exactly() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    artifact = _artifact()
    Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(artifact)

    feature_ids = [row["feature_id"] for row in artifact["features"]]
    assert feature_ids == sorted(market_memory.CANONICAL_FEATURE_REGISTRY)
    assert len(feature_ids) == 18
    assert len(set(feature_ids)) == 18
    for row in artifact["features"]:
        assert (
            row["domain"]
            == market_memory.CANONICAL_FEATURE_REGISTRY[row["feature_id"]].domain
        )


def test_actual_evidence_checkpoint_is_exactly_one_degraded_and_17_missing() -> None:
    artifact = _artifact()
    degraded = [
        row
        for row in artifact["features"]
        if row["registry_state"] == "current_degraded"
    ]
    missing = [
        row for row in artifact["features"] if row["registry_state"] == "missing"
    ]
    assert [(row["feature_id"], row["blocking_reason"]) for row in degraded] == [
        ("macro.regime_state", "component_receipts_unauthenticated")
    ]
    assert len(missing) == 17
    assert {row["blocking_reason"] for row in missing} == {"feature_missing"}
    assert artifact["counts"] == {
        "feature_count": 18,
        "missing_count": 17,
        "current_degraded_count": 1,
        "failed_gate_count": 18,
        "not_run_gate_count": 126,
        "eligible_count": 0,
        "promoted_count": 0,
    }


def test_gate_matrix_can_only_fail_or_remain_not_run() -> None:
    expected_gate_ids = [
        "g0_temporal_data_integrity",
        "g1_reproducibility",
        "g2_conceptual_soundness",
        "g3_predictive_validity",
        "g4_leakage_selection_control",
        "g5_robustness_incremental_value",
        "g6_shadow_forward",
        "g7_bounded_feature_promotion",
    ]
    for row in _artifact()["features"]:
        assert [gate["gate_id"] for gate in row["gates"]] == expected_gate_ids
        assert [gate["status"] for gate in row["gates"]] == [
            "failed",
            "not_run",
            "not_run",
            "not_run",
            "not_run",
            "not_run",
            "not_run",
            "not_run",
        ]
        assert row["eligible"] is False
        assert row["promoted"] is False
        assert row["authority_granted"] is False

    gate_statuses = _schema()["$defs"]["gate"]["properties"]["status"]["enum"]
    assert gate_statuses == ["failed", "not_run"]
    feature_properties = _schema()["$defs"]["feature"]["properties"]
    assert feature_properties["eligible"] == {"const": False}
    assert feature_properties["promoted"] == {"const": False}
    assert feature_properties["authority_granted"] == {"const": False}


def test_private_limits_wave_state_absent_evidence_and_exclusions_are_honest() -> None:
    artifact = _artifact()
    limitations = {row["lane"]: row for row in artifact["private_limitations"]}
    assert set(limitations) == {
        "private_technical_ratio",
        "private_breadth",
        "private_option_oi",
    }
    assert all(row["status"] == "insufficient" for row in limitations.values())
    assert (
        "not canonical price.ret_20d"
        in limitations["private_technical_ratio"]["finding"]
    )
    assert "survivor bias" in limitations["private_breadth"]["finding"]
    assert (
        "not a complete dated or atomic" in limitations["private_option_oi"]["finding"]
    )
    assert artifact["wave_evidence"] == [
        {"wave": "W2", "status": "synthetic_only"},
        {"wave": "W4", "status": "synthetic_only"},
        {"wave": "W5", "status": "not_shipped"},
        {"wave": "W6", "status": "not_shipped"},
    ]
    assert artifact["absent_evidence"] == [
        "operational_forward_n",
        "calibration_evidence",
        "clustered_dependence_intervals",
        "incremental_value_after_prophet",
        "shadow_forward_evidence",
    ]
    assert artifact["excluded_constructs"] == [
        "action_authority",
        "feature_pass_state",
        "promotion_eligibility",
        "promotion_decision",
        "runtime_integration",
        "synapse_registration",
        "training_consumption",
    ]


def test_exact_forward_authority_and_every_capability_remain_false() -> None:
    artifact = _artifact()
    assert artifact["authority"] == dict(forward.AUTHORITY)
    assert artifact["authority_granted"] is False
    assert artifact["authority"]["emission_enabled"] is False
    assert artifact["authority"]["training_eligible"] is False
    assert artifact["authority"]["promotion_eligible"] is False
    assert artifact["authority"]["proposal_weight"] == 0
    action_values = [
        value for key, value in artifact["authority"].items() if key.startswith("may_")
    ]
    assert len(action_values) == 11
    assert not any(action_values)


def test_audit_id_content_addresses_the_complete_negative_payload() -> None:
    first = _artifact()
    repeated = _artifact()
    later = _artifact(audited_at="2026-08-11T12:00:00.000001Z")
    assert first == repeated
    assert first["audit_id"] != later["audit_id"]

    semantic = copy.deepcopy(first)
    audit_id = semantic.pop("audit_id")
    expected = (
        "mmpromotionaudit_"
        + hashlib.sha256(audit.canonical_json_bytes(semantic)).hexdigest()
    )
    assert audit_id == expected


@pytest.mark.parametrize(
    "hostile",
    [
        lambda value: {**value, "features": value["features"][:-1]},
        lambda value: _mutate(value, ("features", 0, "feature_id"), "substituted"),
        lambda value: {
            **value,
            "features": [value["features"][0], *value["features"][:-1]],
        },
        lambda value: {
            **value,
            "features": list(reversed(value["features"])),
        },
    ],
)
def test_omitted_substituted_duplicate_or_unsorted_features_fail_closed(
    hostile,
) -> None:
    _reject_runtime_and_schema(hostile(_artifact()))


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("features", 0, "gates", 0, "status"), "pass"),
        (("features", 0, "eligible"), True),
        (("features", 0, "promoted"), True),
        (("features", 0, "authority_granted"), True),
        (("authority_granted",), True),
        (("authority", "emission_enabled"), True),
        (("authority", "training_eligible"), True),
        (("authority", "promotion_eligible"), True),
        (("authority", "may_rank"), True),
    ],
)
def test_any_pass_eligibility_promotion_or_authority_drift_fails_closed(
    path: tuple[object, ...], replacement: object
) -> None:
    _reject_runtime_and_schema(_mutate(_artifact(), path, replacement))


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("counts", "feature_count"), 17),
        (("counts", "eligible_count"), 1),
        (("counts", "promoted_count"), 1),
        (("counts", "failed_gate_count"), 0),
    ],
)
def test_forged_counts_fail_closed(
    path: tuple[object, ...], replacement: object
) -> None:
    _reject_runtime_and_schema(_mutate(_artifact(), path, replacement))


def test_well_shaped_but_forged_content_hash_fails_runtime_authentication() -> None:
    hostile = _mutate(_artifact(), ("audit_id",), "mmpromotionaudit_" + "0" * 64)
    Draft202012Validator(_schema()).validate(hostile)
    with pytest.raises(audit.MarketMemoryPromotionAuditContractError):
        audit.validate_feature_promotion_audit(hostile)


def test_exact_loader_rejects_duplicate_noncanonical_nonbytes_and_bounds() -> None:
    artifact = _artifact()
    exact = audit.canonical_json_bytes(artifact)
    assert audit.load_feature_promotion_audit_json(exact) == artifact

    hostile_bodies = (
        json.dumps(artifact, indent=2, sort_keys=True).encode("utf-8"),
        b'{"schema":"x","schema":"y"}',
        b"\xef\xbb\xbf" + exact,
        b"x" * (256 * 1024 + 1),
        b"",
    )
    for body in hostile_bodies:
        with pytest.raises(audit.MarketMemoryPromotionAuditContractError):
            audit.load_feature_promotion_audit_json(body)
    with pytest.raises(audit.MarketMemoryPromotionAuditContractError):
        audit.load_feature_promotion_audit_json(bytearray(exact))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "audited_at",
    [
        "2026-08-11T12:00:00Z",
        "2026-08-11T12:00:00.000000+00:00",
        "2026-02-30T12:00:00.000000Z",
        "1969-12-31T23:59:59.999999Z",
        "2101-01-01T00:00:00.000000Z",
        "2026-08-12T00:00:00.000000Z",
    ],
)
def test_audit_timestamp_is_exact_real_utc_and_bounded(audited_at: str) -> None:
    with pytest.raises(audit.MarketMemoryPromotionAuditContractError):
        audit.build_feature_promotion_audit(audited_at=audited_at)


def test_builder_is_detached_clock_free_and_performs_no_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("W7 audit must not perform I/O")

    monkeypatch.setattr(builtins, "open", forbidden_io)
    first = _artifact()
    first["features"][0]["gates"][0]["status"] = "not_run"
    assert _artifact()["features"][0]["gates"][0]["status"] == "failed"

    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MODULE))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert not (
        {
            "os",
            "pathlib",
            "socket",
            "subprocess",
            "urllib",
            "requests",
            "httpx",
            "fastapi",
        }
        & imports
    )
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not ({"now", "utcnow", "open", "write_text", "write_bytes"} & calls)


def test_no_api_store_writer_data_config_synapse_runtime_or_production_import() -> None:
    for forbidden in (
        "route",
        "store",
        "writer",
        "save",
        "append",
        "register",
        "promote",
        "materialize",
        "run",
    ):
        assert not hasattr(audit, forbidden)

    callers: set[Path] = set()
    for parent in (ROOT / "app", ROOT / "engine", ROOT / "scripts"):
        for path in parent.rglob("*.py"):
            if path == MODULE:
                continue
            source = path.read_text(encoding="utf-8")
            if (
                "market_memory_promotion_audit" in source
                or "build_feature_promotion_audit" in source
            ):
                callers.add(path.relative_to(ROOT))
    assert callers == set()


def test_ci_explicitly_owns_schema_module_hostiles_and_konseki_trigger() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    jobs = LEGACY_JOBS.read_text(encoding="utf-8")
    lane = jobs.split("  market-memory-contract:", 1)[1].split("\n  group-pulse:", 1)[0]
    assert "tests/test_market_memory_promotion_audit.py" in lane
    for path in (
        "contracts/market_memory/feature_promotion_audit.v1.schema.json",
        "engine/neuralweb/market_memory.py",
        "engine/neuralweb/market_memory_forward.py",
        "engine/neuralweb/market_memory_promotion_audit.py",
        "tests/test_market_memory_promotion_audit.py",
        "research/KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md",
    ):
        assert f'- "{path}"' in workflow
    assert KONSEKI.exists()
