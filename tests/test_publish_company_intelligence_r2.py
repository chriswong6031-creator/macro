from __future__ import annotations

import io
from hashlib import sha256
import json

import pytest

from engine.company_intelligence.views import build_bundle, write_generation
from scripts.publish_company_intelligence_r2 import publish


class _FakeR2:
    def __init__(self, remote_manifest: dict | None = None, objects: dict[str, tuple[bytes, dict]] | None = None) -> None:
        self.remote_manifest = remote_manifest
        self.objects = dict(objects or {})
        self.puts: list[tuple[str, dict]] = []

    def get_object(self, *, Bucket, Key):
        if Key == "company_intelligence/manifest.json" and self.remote_manifest is not None:
            return {"Body": io.BytesIO(json.dumps(self.remote_manifest).encode()), "ETag": "prior-etag"}
        if Key in self.objects:
            body, _metadata = self.objects[Key]
            return {"Body": io.BytesIO(body)}
        if Key == "company_intelligence/manifest.json":
            raise RuntimeError("missing")
        raise RuntimeError("missing")

    def head_object(self, *, Bucket, Key):
        if Key in self.objects:
            body, metadata = self.objects[Key]
            return {"Metadata": metadata, "ContentLength": len(body)}
        raise RuntimeError("missing")

    def put_object(self, **kwargs):
        if kwargs.get("IfNoneMatch") == "*" and kwargs["Key"] in self.objects:
            raise _PreconditionFailed()
        self.puts.append((kwargs["Key"], kwargs))
        body = kwargs["Body"]
        assert isinstance(body, bytes)
        self.objects[kwargs["Key"]] = (body, dict(kwargs.get("Metadata") or {}))


class _PreconditionFailed(RuntimeError):
    response = {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}}


def _tree(tmp_path):
    history = [{
        "document_ticker": "AAPL", "fiscal_year": 2026, "fiscal_quarter": 1,
        "call_date": "2026-01-29", "earnings_call_sent": 0.2,
        "raw_source_url": "https://example.test/source",
    }]
    tx = {"schema": "mastermind.tx-index/v1", "documents": [{"ticker": "AAPL", "fiscal_year": 2026, "fiscal_quarter": 1, "present": True}]}
    contexts, manifest = build_bundle(history, tx_index=tx, as_of="2026-02-02")
    write_generation(tmp_path, contexts, manifest)
    return json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))


def test_absent_credentials_is_noop(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scripts.publish_company_intelligence_r2._client", lambda: None)
    assert publish(tmp_path) == 0


def test_payloads_and_generation_manifest_precede_mutable_marker(tmp_path) -> None:
    manifest = _tree(tmp_path)
    fake = _FakeR2()
    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    keys = [key for key, _ in fake.puts]
    assert keys[-1] == "company_intelligence/manifest.json"
    assert keys[0].endswith("/companies/AAPL.json")
    assert keys[-2].endswith("/manifest.json")
    assert fake.puts[-1][1]["Metadata"]["generation-id"] == manifest["generation_id"]


def test_last_good_manifest_shrink_rejection_stops_before_writes(tmp_path) -> None:
    _tree(tmp_path)
    fake = _FakeR2({"status": "ready", "company_count": 10, "event_count": 100})
    assert publish(tmp_path, s3=fake, bucket="bucket") == 1
    assert fake.puts == []


def test_identical_remote_root_manifest_is_safe_publish_noop(tmp_path) -> None:
    _tree(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    fake = _FakeR2(manifest)
    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    assert fake.puts == []


@pytest.mark.parametrize("relative", ["companies/AAPL.json", "manifest.json"])
def test_existing_generation_object_with_mismatched_bytes_is_hard_collision(tmp_path, relative: str) -> None:
    manifest = _tree(tmp_path)
    generation = tmp_path / "generations" / manifest["generation_id"]
    key = f"company_intelligence/generations/{manifest['generation_id']}/{relative}"
    expected_sha = (manifest["files"][relative]["sha256"] if relative.startswith("companies/") else sha256((generation / relative).read_bytes()).hexdigest())
    # A forged matching checksum must still fail: the publisher reads and
    # checks existing bytes rather than trusting mutable object metadata.
    fake = _FakeR2(objects={key: (b"not-the-immutable-object", {"sha256": expected_sha})})

    assert publish(tmp_path, s3=fake, bucket="bucket") == 1
    assert all(written_key != key for written_key, _ in fake.puts)
    assert "company_intelligence/manifest.json" not in [written_key for written_key, _ in fake.puts]


def test_existing_exact_generation_objects_are_safe_noops_before_marker_promotion(tmp_path) -> None:
    manifest = _tree(tmp_path)
    generation = tmp_path / "generations" / manifest["generation_id"]
    prefix = f"company_intelligence/generations/{manifest['generation_id']}"
    company = generation / "companies" / "AAPL.json"
    immutable_manifest = generation / "manifest.json"
    fake = _FakeR2(
        remote_manifest={"status": "ready", "company_count": 1, "event_count": 1},
        objects={
            f"{prefix}/companies/AAPL.json": (company.read_bytes(), {"sha256": manifest["files"]["companies/AAPL.json"]["sha256"]}),
            f"{prefix}/manifest.json": (immutable_manifest.read_bytes(), {"sha256": sha256(immutable_manifest.read_bytes()).hexdigest()}),
        },
    )

    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    assert [key for key, _ in fake.puts] == ["company_intelligence/manifest.json"]
