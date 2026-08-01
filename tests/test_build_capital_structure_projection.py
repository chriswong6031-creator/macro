"""Disk-writer tests for the Capital Structure public projection twin."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from engine.capital_structure.projection import validate_projection_bundle
from engine.capital_structure.source_identity import manifest_id_for
import scripts.build_capital_structure_projection as projection_builder
from scripts.build_capital_structure_projection import build_from_disk
from scripts.compile_capital_structure_events import compile_from_disk


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
        "privacy": {"classification": "public", "contains_personal_data": False},
        "parser": {
            "eligibility": "eligible",
            "corruption_state": "clean",
            "parser_version": "fixture/1.0",
        },
        "spans": [{
            "span_id": f"root:{digest}",
            "locator_type": "document",
            "locator": f"bytes:0-{len(raw)}",
            "text_sha256": digest,
        }],
    }
    row["manifest_id"] = manifest_id_for(row)
    return row


def _compiled_root(tmp_path: Path) -> Path:
    root = tmp_path / "capital_structure"
    root.mkdir()
    complete = _manifest(role="complete_submission")
    primary = _manifest(role="primary", parent_manifest_id=complete["manifest_id"])
    pd.DataFrame([complete, primary]).to_parquet(root / "source_manifest.parquet", index=False)
    compile_from_disk(root=root, generated_at="2026-08-02T12:00:00Z")
    return root


def test_builder_writes_valid_byte_identical_projection_without_network(tmp_path, monkeypatch):
    root = _compiled_root(tmp_path)
    canonical = tmp_path / "out" / "projection.json"
    public = tmp_path / "site" / "capital-structure-data" / "latest.json"

    def explode(*args, **kwargs):
        raise AssertionError("projection builder attempted network access")

    monkeypatch.setattr(requests, "get", explode)
    summary = build_from_disk(
        root=root,
        canonical_path=canonical,
        public_path=public,
        generated_at="2026-08-02T13:00:00Z",
    )

    assert summary["status"] == "partial"
    assert summary["issuers"] == 1
    assert summary["events"] == 1
    assert canonical.read_bytes() == public.read_bytes()
    payload = json.loads(canonical.read_text(encoding="utf-8"))
    validate_projection_bundle(payload)
    assert payload["records"][0]["identity"]["ticker"] == "ABC"
    assert payload["records"][0]["latest_observed_event"]["source"]["filing_url"].startswith(
        "https://www.sec.gov/"
    )


def test_receipt_mismatch_preserves_both_prior_projection_files(tmp_path):
    root = _compiled_root(tmp_path)
    canonical = tmp_path / "out" / "projection.json"
    public = tmp_path / "site" / "capital-structure-data" / "latest.json"
    build_from_disk(
        root=root,
        canonical_path=canonical,
        public_path=public,
        generated_at="2026-08-02T13:00:00Z",
    )
    prior_canonical = canonical.read_bytes()
    prior_public = public.read_bytes()

    with (root / "event_versions.parquet").open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(ValueError, match="receipt hash mismatch"):
        build_from_disk(
            root=root,
            canonical_path=canonical,
            public_path=public,
            generated_at="2026-08-02T14:00:00Z",
        )

    assert canonical.read_bytes() == prior_canonical
    assert public.read_bytes() == prior_public


def test_builder_rejects_same_canonical_and_public_target(tmp_path):
    root = _compiled_root(tmp_path)
    target = tmp_path / "projection.json"
    with pytest.raises(ValueError, match="must be distinct"):
        build_from_disk(
            root=root,
            canonical_path=target,
            public_path=target,
            generated_at="2026-08-02T13:00:00Z",
        )


def test_missing_generation_publishes_explicit_unavailable_not_empty_green(tmp_path):
    root = tmp_path / "capital_structure"
    root.mkdir()
    canonical = tmp_path / "out" / "projection.json"
    public = tmp_path / "site" / "capital-structure-data" / "latest.json"

    summary = build_from_disk(
        root=root,
        canonical_path=canonical,
        public_path=public,
        generated_at="2026-08-02T13:00:00Z",
    )

    payload = json.loads(canonical.read_text(encoding="utf-8"))
    validate_projection_bundle(payload)
    assert summary["status"] == "unavailable"
    assert payload["coverage"]["source_status"] == "missing"
    assert payload["coverage"]["reason"] == "source_generation_missing"
    assert payload["coverage"]["event_count"] == 0
    assert payload["records"] == []
    assert canonical.read_bytes() == public.read_bytes()


def test_pair_promotion_rolls_both_targets_back_if_second_replace_fails(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical.json"
    public = tmp_path / "latest.json"
    canonical.write_bytes(b"old-canonical")
    public.write_bytes(b"old-public")
    real_replace = projection_builder.os.replace
    failed = False

    def flaky_replace(source, target):
        nonlocal failed
        if ".backup-" in Path(source).name:
            assert Path(target).exists()
        if Path(target) == public and not failed:
            assert canonical.exists()
            assert public.exists()
            assert public.read_bytes() == b"old-public"
            failed = True
            raise OSError("fixture second-target failure")
        return real_replace(source, target)

    monkeypatch.setattr(projection_builder.os, "replace", flaky_replace)
    with pytest.raises(OSError, match="second-target failure"):
        projection_builder._promote_pair(b"new-payload", canonical, public)

    assert canonical.read_bytes() == b"old-canonical"
    assert public.read_bytes() == b"old-public"


def test_startup_recovers_interrupted_pair_before_current_source_verification(tmp_path):
    root = _compiled_root(tmp_path)
    canonical = tmp_path / "out" / "projection.json"
    public = tmp_path / "site" / "capital-structure-data" / "latest.json"

    build_from_disk(
        root=root,
        canonical_path=canonical,
        public_path=public,
        generated_at="2026-08-02T13:00:00Z",
    )
    old_public = public.read_bytes()
    build_from_disk(
        root=root,
        canonical_path=canonical,
        public_path=public,
        generated_at="2026-08-02T14:00:00Z",
    )
    new_canonical = canonical.read_bytes()
    assert new_canonical != old_public

    # Simulate a process stop after canonical replacement but before the public
    # replacement, then make the current source generation unverifiable.
    public.write_bytes(old_public)
    with (root / "event_versions.parquet").open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(ValueError, match="receipt hash mismatch"):
        build_from_disk(
            root=root,
            canonical_path=canonical,
            public_path=public,
            generated_at="2026-08-02T15:00:00Z",
        )

    assert canonical.read_bytes() == public.read_bytes() == new_canonical


def test_startup_recovers_missing_canonical_from_valid_public_twin(tmp_path):
    root = _compiled_root(tmp_path)
    canonical = tmp_path / "out" / "projection.json"
    public = tmp_path / "site" / "capital-structure-data" / "latest.json"
    build_from_disk(
        root=root,
        canonical_path=canonical,
        public_path=public,
        generated_at="2026-08-02T13:00:00Z",
    )
    last_good = public.read_bytes()
    canonical.unlink()

    recovered = projection_builder._recover_projection_pair(canonical, public)

    assert recovered is True
    assert canonical.read_bytes() == public.read_bytes() == last_good
