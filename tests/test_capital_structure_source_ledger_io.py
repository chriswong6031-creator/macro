"""The source-manifest ledger's stored form must not rewrite retained rows.

These tests pin the defect that failed ``compile_capital_structure_events`` every
night from 2026-08-05: pyarrow unifies nested struct schemas across rows, so one
new row carrying a nested key no existing row had back-filled null into all 1258
retained rows and broke the IDs they were written with.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.capital_structure.source_identity import (
    ManifestIdentityError,
    manifest_id_for,
    source_ledger_prefix_hash,
    validate_manifest_ledger,
)
from engine.capital_structure.source_ledger_io import (
    LEGACY_SOURCE_LEDGER_FILENAME,
    SOURCE_LEDGER_FILENAME,
    decode_source_ledger,
    encode_source_ledger,
    read_source_ledger,
    source_ledger_path,
    write_source_ledger,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED_LEDGER = REPO_ROOT / "data" / "capital_structure" / SOURCE_LEDGER_FILENAME
# Pinned in data/capital_structure/telemetry.json as source_ledger_receipt,
# which declares immutable_prefix: true.  The JSONL migration preserved it.
PINNED_PREFIX_SHA256 = "73631e1f83f1d5deb4ee240680534fe4764201e908091e6fa8b315a6277a16e3"


def _record(source_id: str, **filing_extra: object) -> dict:
    record = {
        "schema": "capital_structure.source_manifest/v1",
        "source_system": "sec_edgar",
        "source_id": source_id,
        "issuer": {"issuer_id": "sec:cik:0000000320", "cik": "320", "ticker": None, "aliases": []},
        "filing": {
            "accession": "0000000320-26-000001",
            "form": "S-3",
            "filing_date": "2026-07-31",
            "accepted_at": "2026-07-31T18:12:46+00:00",
            "file_number": None,
            **filing_extra,
        },
        "document": {"document_role": "complete_submission", "byte_length": 12},
        "retrieval": {"retrieved_at": "2026-07-31T18:12:46+00:00"},
        "storage": {"backend": "r2"},
        "rights": {"redistribution_class": "public_source_link"},
        "privacy": {"classification": "public"},
        "parser": {"eligibility": "eligible"},
        "spans": [{"span_id": "root:a", "locator_type": "document"}],
    }
    record["manifest_id"] = manifest_id_for(record)
    return record


def _retained_and_grown() -> tuple[dict, dict]:
    """A retained row, plus a new row introducing nested keys it never had."""
    retained = _record("retained:0:complete-submission.txt")
    grown = _record(
        "grown:0:complete-submission.txt",
        # Exactly the #4243 growth: one nested dict, one scalar.
        file_number_provenance={"state": "observed", "encoding": "modern"},
        collection_scope="daily_index",
    )
    return retained, grown


def test_parquet_storage_would_break_retained_identity(tmp_path: Path) -> None:
    """The control: prove the guard below can see the failure it claims to catch.

    If this ever stops failing, pyarrow changed and the test that follows has
    become vacuous rather than protective.
    """
    retained, grown = _retained_and_grown()
    path = tmp_path / LEGACY_SOURCE_LEDGER_FILENAME
    pd.DataFrame([retained, grown]).to_parquet(path, index=False)
    read_back = [
        {key: value for key, value in row.items()}
        for row in pd.read_parquet(path).to_dict(orient="records")
    ]

    assert "file_number_provenance" not in retained["filing"]
    # The retained row came back carrying a key it was never written with.
    assert read_back[0]["filing"]["file_number_provenance"] is None
    with pytest.raises(ManifestIdentityError):
        validate_manifest_ledger(read_back)


def test_jsonl_storage_preserves_retained_identity_across_schema_growth(
    tmp_path: Path,
) -> None:
    """The fix: a new nested key must not touch any retained row's identity."""
    retained, grown = _retained_and_grown()
    path = source_ledger_path(tmp_path)
    write_source_ledger([retained, grown], path)

    read_back = read_source_ledger(path)
    validate_manifest_ledger(read_back)
    assert read_back == [retained, grown]
    assert read_back[0]["manifest_id"] == retained["manifest_id"]
    assert "file_number_provenance" not in read_back[0]["filing"]
    assert read_back[1]["filing"]["file_number_provenance"] == {
        "state": "observed", "encoding": "modern",
    }
    # The immutable prefix over the retained row is unchanged by the append.
    assert source_ledger_prefix_hash(read_back, 1) == source_ledger_prefix_hash([retained])


def test_write_refuses_a_drifted_ledger(tmp_path: Path) -> None:
    """A ledger whose IDs no longer match its bodies must not reach disk."""
    retained, _grown = _retained_and_grown()
    drifted = copy.deepcopy(retained)
    drifted["filing"]["file_number_provenance"] = None  # the back-fill, by hand
    path = source_ledger_path(tmp_path)

    with pytest.raises(ManifestIdentityError):
        write_source_ledger([drifted], path)
    assert not path.exists()


def test_legacy_parquet_ledger_is_an_error_not_an_empty_read(tmp_path: Path) -> None:
    """A leftover parquet ledger holds real provenance; never read it as absent."""
    retained, _grown = _retained_and_grown()
    pd.DataFrame([retained]).to_parquet(
        tmp_path / LEGACY_SOURCE_LEDGER_FILENAME, index=False,
    )
    with pytest.raises(ManifestIdentityError, match="superseded parquet form"):
        read_source_ledger(source_ledger_path(tmp_path))


def test_absent_ledger_reads_empty(tmp_path: Path) -> None:
    assert read_source_ledger(source_ledger_path(tmp_path)) == []


@pytest.mark.parametrize(
    "body",
    [
        b'{"a": 1}',                      # unterminated final row
        b'{"a": 1}\n\n{"b": 2}\n',        # blank line
        b'{"a": 1}\nnot json\n',          # unparseable row
        b'[1, 2]\n',                      # not an object
    ],
)
def test_corrupt_ledger_bytes_are_rejected(body: bytes) -> None:
    with pytest.raises(ManifestIdentityError):
        decode_source_ledger(body, label="fixture")


def test_encode_is_canonical_and_line_oriented() -> None:
    retained, grown = _retained_and_grown()
    body = encode_source_ledger([retained, grown])
    lines = body.decode("utf-8").splitlines()
    assert len(lines) == 2
    for line, record in zip(lines, (retained, grown)):
        assert json.loads(line) == record
        # Canonical form: sorted keys, no incidental whitespace.
        assert line == json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )


@pytest.mark.skipif(not COMMITTED_LEDGER.exists(), reason="ledger not retained here")
def test_committed_ledger_validates_and_matches_its_pinned_receipt() -> None:
    """The migrated ledger must still be the exact prefix the receipt commits to."""
    records = read_source_ledger(COMMITTED_LEDGER)
    validate_manifest_ledger(records)
    assert records
    assert source_ledger_prefix_hash(records) == PINNED_PREFIX_SHA256
