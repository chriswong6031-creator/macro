from __future__ import annotations

from copy import deepcopy
import re

import pytest

from engine.capital_structure.source_identity import (
    ManifestIdentityError,
    manifest_id_for,
    merge_manifest_ledgers,
    source_ledger_prefix_hash,
    validate_manifest_identity,
    validate_manifest_ledger,
)


def _record(marker: str) -> dict:
    record = {
        "schema": "capital_structure.source_manifest/v1",
        "source_system": "sec_edgar",
        "source_id": f"source:{marker}",
        "nested": {
            "marker": marker,
            "rights": ["public", "attribution"],
            "retained": True,
        },
    }
    record["manifest_id"] = manifest_id_for(record)
    return record


def test_manifest_id_commits_to_full_body_except_identity_field():
    record = _record("one")
    reordered = {
        "nested": deepcopy(record["nested"]),
        "source_id": record["source_id"],
        "source_system": record["source_system"],
        "schema": record["schema"],
        "manifest_id": "ignored-when-computing",
    }

    assert re.fullmatch(r"manifest:cs:[a-f0-9]{64}", record["manifest_id"])
    assert manifest_id_for(reordered) == record["manifest_id"]
    changed = deepcopy(record)
    changed["nested"]["rights"].append("excerpt")
    assert manifest_id_for(changed) != record["manifest_id"]


def test_identity_validation_fails_closed_on_any_body_mutation():
    record = _record("one")
    validate_manifest_identity(record)
    record["nested"]["retained"] = False

    with pytest.raises(ManifestIdentityError, match="identity mismatch"):
        validate_manifest_identity(record)


def test_manifest_merge_preserves_prefix_and_rejects_duplicate_prior_ledger():
    first = _record("one")
    second = _record("two")

    merged = merge_manifest_ledgers([first], [first, second])

    assert merged == [first, second]
    assert source_ledger_prefix_hash(merged, count=1) == source_ledger_prefix_hash([first])
    assert source_ledger_prefix_hash(merged) != source_ledger_prefix_hash(
        list(reversed(merged))
    )
    with pytest.raises(ManifestIdentityError, match="duplicate global manifest_id"):
        validate_manifest_ledger([first, first])


def test_manifest_merge_rejects_same_id_with_divergent_body():
    first = _record("one")
    divergent = deepcopy(first)
    divergent["nested"]["marker"] = "changed"

    with pytest.raises(ManifestIdentityError, match="identity mismatch"):
        merge_manifest_ledgers([first], [divergent])


@pytest.mark.parametrize("count", [-1, 2, True])
def test_prefix_hash_rejects_invalid_count(count):
    with pytest.raises(ValueError, match="valid source-ledger prefix"):
        source_ledger_prefix_hash([_record("one")], count=count)
