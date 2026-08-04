"""Closed catalog contracts for the future native share-count v4 head."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _registry() -> Registry:
    names = (
        "capital_structure_share_count_head_witness.schema.json",
        "capital_structure_share_count_head_guard_scope.schema.json",
        "capital_structure_share_count_head_witness_v3.schema.json",
        "capital_structure_share_count_head_witness_v4.schema.json",
        "capital_structure_share_count_external_head.schema.json",
    )
    schemas = [_schema(name) for name in names]
    return Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )


def _selection(*, sequence: int = 1, previous_receipt=None) -> dict:
    if previous_receipt is None and sequence >= 2:
        previous_receipt = {
            "sequence": sequence - 1,
            "receipt_id": f"receipt:cs-share-count-materialization-v2:{HASH_B}",
            "receipt_sha256": HASH_B,
            "receipt_byte_length": 100,
        }
    return {
        "key_id": "share-count-head",
        "sequence": sequence,
        "receipt_id": f"receipt:cs-share-count-materialization-v2:{HASH_A}",
        "receipt_sha256": HASH_A,
        "receipt_byte_length": 101,
        "receipt_object_key": f"capital_structure/share_counts/v2/receipts/{HASH_A}.json",
        "generation_id": f"generation:cs-share-count-materialization-v2:{HASH_A}",
        "ledger_sha256": HASH_A,
        "ledger_byte_length": 1024,
        "ledger_object_key": f"capital_structure/share_counts/v2/generations/{HASH_A}/ledger.json",
        "published_at": "2026-08-03T00:00:00Z",
        "previous_receipt": previous_receipt,
        "signature": HASH_C,
    }


def _scope() -> dict:
    return {
        "schema": "capital_structure.share_count_head_guard_scope/v1",
        "backend": "r2",
        "account_id": "d" * 32,
        "bucket": "capital-structure",
        "head_key": "capital_structure/share_counts/v2/current_head.json",
    }


def _v2() -> dict:
    return {
        "schema": "capital_structure.share_count_head_witness/v2",
        **_selection(),
    }


def _v3() -> dict:
    return {
        "schema": "capital_structure.share_count_head_witness/v3",
        **_selection(),
        "guard_scope": _scope(),
        "migration": {
            "from_schema": "capital_structure.share_count_head_witness/v2",
            "from_witness_sha256": HASH_B,
        },
    }


def _v4(kind: str, *, sequence: int = 1) -> dict:
    transition = {"kind": kind}
    if kind == "migration":
        transition.update(
            {
                "from_schema": "capital_structure.share_count_head_witness/v2",
                "from_witness_sha256": HASH_B,
                "v2_anchor_sha256": HASH_B,
            }
        )
    elif kind == "successor":
        transition["previous_witness_sha256"] = HASH_B
    return {
        "schema": "capital_structure.share_count_head_witness/v4",
        **_selection(sequence=sequence),
        "guard_scope": _scope(),
        "transition": transition,
    }


def _errors(schema_name: str, value: dict) -> list:
    return list(
        Draft202012Validator(
            _schema(schema_name), registry=_registry(), format_checker=FormatChecker()
        ).iter_errors(value)
    )


def test_v4_and_closed_external_head_union_are_valid_draft_2020_12_contracts():
    for name in (
        "capital_structure_share_count_head_witness_v4.schema.json",
        "capital_structure_share_count_external_head.schema.json",
    ):
        Draft202012Validator.check_schema(_schema(name))


def test_external_head_union_resolves_only_complete_v2_v3_or_v4_witnesses():
    for witness in (_v2(), _v3(), _v4("genesis"), _v4("migration"), _v4("successor", sequence=2)):
        assert not _errors("capital_structure_share_count_external_head.schema.json", witness)

    unknown = _v4("genesis")
    unknown["schema"] = "capital_structure.share_count_head_witness/v5"
    assert _errors("capital_structure_share_count_external_head.schema.json", unknown)

    extra = _v4("genesis")
    extra["unrecognized"] = True
    assert _errors("capital_structure_share_count_external_head.schema.json", extra)


def test_v4_transition_union_is_closed_and_preserves_genesis_successor_shapes():
    bad_genesis = _v4("genesis", sequence=2)
    assert _errors("capital_structure_share_count_head_witness_v4.schema.json", bad_genesis)

    bad_successor = _v4("successor", sequence=2)
    bad_successor["previous_receipt"] = None
    assert _errors("capital_structure_share_count_head_witness_v4.schema.json", bad_successor)

    mixed_transition = _v4("migration")
    mixed_transition["transition"]["previous_witness_sha256"] = HASH_C
    assert _errors("capital_structure_share_count_head_witness_v4.schema.json", mixed_transition)

    unsupported_from_schema = _v4("migration")
    unsupported_from_schema["transition"]["from_schema"] = "capital_structure.share_count_head_witness/v4"
    assert _errors("capital_structure_share_count_head_witness_v4.schema.json", unsupported_from_schema)


def test_v4_migration_allows_only_explicit_v2_or_v3_anchors():
    from_v3 = copy.deepcopy(_v4("migration"))
    from_v3["transition"]["from_schema"] = "capital_structure.share_count_head_witness/v3"
    assert not _errors("capital_structure_share_count_head_witness_v4.schema.json", from_v3)
