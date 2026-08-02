"""Disk compiler tests for the registration lifecycle truth plane."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.capital_structure.registration_lifecycle import (
    validate_registration_lifecycle_bundle,
)
from engine.capital_structure.source_identity import manifest_id_for
from scripts.compile_capital_structure_events import compile_from_disk as compile_events
from scripts.compile_capital_structure_registration_lifecycles import (
    compile_from_disk,
)


def _manifest(*, role: str, parent_manifest_id: str | None = None) -> dict:
    accession = "0000000001-26-000001"
    name = "complete-submission.txt" if role == "complete_submission" else "primary.htm"
    sequence = "0" if role == "complete_submission" else "1"
    raw = f"{accession}|S-3|{role}".encode()
    digest = sha256(raw).hexdigest()
    row = {
        "schema": "capital_structure.source_manifest/v1",
        "manifest_id": "",
        "source_system": "sec_edgar",
        "source_id": f"{accession}:{sequence}:{name}",
        "issuer": {
            "issuer_id": "sec:cik:0000000001",
            "cik": "1",
            "ticker": "ABC",
            "aliases": ["ABC Corp"],
        },
        "filing": {
            "accession": accession,
            "form": "S-3",
            "filing_date": "2026-08-01",
            "accepted_at": "2026-08-01T10:00:00Z",
            "file_number": "333-123",
        },
        "document": {
            "canonical_url": f"https://www.sec.gov/Archives/{accession}.txt#document={sequence}",
            "document_name": name,
            "document_type": "S-3",
            "document_role": role,
            "sequence": sequence,
            "media_type": "text/plain",
            "byte_length": len(raw),
            "document_version": 1,
            "content_sha256": digest,
            "parent_manifest_id": parent_manifest_id,
            "root_locator": f"sha256:{digest}",
        },
        "retrieval": {
            "retrieved_at": "2026-08-01T10:00:03Z",
            "first_seen_at": "2026-08-01T10:00:03Z",
            "transport_status": "retrieved",
        },
        "storage": {
            "backend": "r2",
            "store_id": "r2_shared",
            "object_key": f"capital_structure/sec/sha256/{digest[:2]}/{digest}",
            "content_addressed": True,
            "retention_state": "retained",
        },
        "rights": {
            "redistribution_class": "public_source_link",
            "attribution_required": True,
            "license_note": "SEC filing",
        },
        "privacy": {
            "classification": "public",
            "contains_personal_data": False,
        },
        "parser": {
            "eligibility": "eligible",
            "corruption_state": "clean",
            "parser_version": "fixture/1.0",
        },
        "spans": [
            {
                "span_id": f"root:{digest}",
                "locator_type": "document",
                "locator": f"bytes:0-{len(raw)}",
                "text_sha256": digest,
            }
        ],
    }
    row["manifest_id"] = manifest_id_for(row)
    return row


def _compiled_root(tmp_path: Path) -> Path:
    root = tmp_path / "capital_structure"
    root.mkdir()
    complete = _manifest(role="complete_submission")
    primary = _manifest(
        role="primary", parent_manifest_id=complete["manifest_id"]
    )
    pd.DataFrame([complete, primary]).to_parquet(
        root / "source_manifest.parquet", index=False
    )
    compile_events(root=root, generated_at="2026-08-02T12:00:00Z")
    return root


def test_disk_compiler_verifies_generation_and_writes_receipt_bound_artifact(tmp_path):
    root = _compiled_root(tmp_path)
    output = tmp_path / "out" / "registration_lifecycles.json"

    summary = compile_from_disk(
        root=root,
        output_path=output,
        generated_at="2026-08-02T13:00:00Z",
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    telemetry = json.loads((root / "telemetry.json").read_text(encoding="utf-8"))
    validate_registration_lifecycle_bundle(payload)
    if payload["records"]:
        # Wave2C source generations carry the trusted provenance object.
        assert summary["status"] == "observed"
        assert summary["lifecycles"] == 1
        assert summary["timeline_events"] == 1
        assert payload["records"][0]["observed_registration_state"] == "filed"
    else:
        # A pre-Wave2C generation is intentionally non-publishable rather than
        # treating its legacy file-number scalar as an exact grouping key.
        assert summary["status"] == "partial"
        assert summary["lifecycles"] == 0
        assert summary["timeline_events"] == 0
        assert {item["reason"] for item in payload["deferred"]} == {
            "untrusted_file_number_provenance"
        }
    assert telemetry["generation_id"]
    assert (
        payload["source_receipt"]["verification_state"]
        == "verified_telemetry_last_generation"
    )
    assert payload["source_receipt"]["visible_event_version_count"] == 1
    assert payload["source_receipt"]["visible_edge_count"] == 0


def test_failed_upstream_receipt_verification_preserves_last_good_output(tmp_path):
    root = _compiled_root(tmp_path)
    output = tmp_path / "out" / "registration_lifecycles.json"
    compile_from_disk(
        root=root,
        output_path=output,
        generated_at="2026-08-02T13:00:00Z",
    )
    last_good = output.read_bytes()
    with (root / "event_versions.parquet").open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(ValueError, match="receipt hash mismatch"):
        compile_from_disk(
            root=root,
            output_path=output,
            generated_at="2026-08-02T14:00:00Z",
        )

    assert output.read_bytes() == last_good


def test_missing_generation_writes_explicit_unavailable_artifact(tmp_path):
    root = tmp_path / "capital_structure"
    output = tmp_path / "out" / "registration_lifecycles.json"

    summary = compile_from_disk(
        root=root,
        output_path=output,
        generated_at="2026-08-02T13:00:00Z",
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    validate_registration_lifecycle_bundle(payload)
    assert summary["status"] == "unavailable"
    assert payload["coverage"]["reason"] == "upstream_generation_unavailable"
    assert payload["records"] == []


def test_incomplete_upstream_generation_fails_before_output_promotion(tmp_path):
    root = tmp_path / "capital_structure"
    root.mkdir()
    (root / "event_versions.parquet").write_bytes(b"partial")
    output = tmp_path / "registration_lifecycles.json"

    with pytest.raises(ValueError, match="committed generation is incomplete"):
        compile_from_disk(
            root=root,
            output_path=output,
            generated_at="2026-08-02T13:00:00Z",
        )

    assert not output.exists()
