from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.contracts import canonical_json_bytes, sha256_bytes
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_transcript_intake import canonical_body_sha256
from scripts.publish_earnings_evidence_graph_r2 import (
    ImmutableAddressIntegrityError,
    PUBLISH_CONFLICT,
    PREFIX,
    audit_remote_generation,
    load_remote_root_marker,
    publish,
)


class _PreconditionFailed(RuntimeError):
    response = {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}}


class _FakeR2:
    def __init__(self, *, marker: dict | None = None, marker_etag: str = "prior", race_marker: bool = False) -> None:
        self.marker = marker
        self.marker_etag = marker_etag
        self.marker_body = self._canonical_marker(marker) if marker is not None else None
        self.race_marker = race_marker
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict] = {}
        self.puts: list[tuple[str, dict]] = []

    @staticmethod
    def _canonical_marker(marker: dict) -> bytes:
        return json.dumps(marker, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"

    def get_object(self, *, Bucket, Key):
        if Key == f"{PREFIX}/manifest.json" and self.marker is not None:
            return {"Body": io.BytesIO(self.marker_body or self._canonical_marker(self.marker)), "ETag": self.marker_etag}
        if Key in self.objects:
            return {"Body": io.BytesIO(self.objects[Key])}
        raise RuntimeError("missing")

    def head_object(self, *, Bucket, Key):
        if Key in self.objects:
            return {"ContentLength": len(self.objects[Key]), "Metadata": self.metadata.get(Key, {})}
        raise RuntimeError("missing")

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if key == f"{PREFIX}/manifest.json" and self.race_marker:
            raise _PreconditionFailed()
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise _PreconditionFailed()
        self.puts.append((key, kwargs))
        self.objects[key] = kwargs["Body"]
        self.metadata[key] = dict(kwargs.get("Metadata") or {})
        if key == f"{PREFIX}/manifest.json":
            self.marker = json.loads(kwargs["Body"].decode("utf-8"))
            self.marker_body = kwargs["Body"]


def _tree(tmp_path: Path):
    body = {
        "schema": "mastermind.tx/v1", "ticker": "AAPL", "id": "2026Q1",
        "period": "Q1 FY2026", "date": "2026-01-30", "title": "Apple call",
        "segments": [{"speaker": "CFO", "role": "executive", "text": "Revenue increased 12%."}],
    }
    digest = canonical_body_sha256(body)
    index = {
        "schema": "mastermind.tx-index/v1", "generated_at": "2026-02-01T00:00:00Z",
        "symbols": {"AAPL": ["2026Q1"]}, "revisions": {"AAPL/2026Q1": digest},
        "dates": {"AAPL/2026Q1": "2026-01-30"}, "body_count": 1, "symbol_count": 1,
    }
    pack, graph = build_evidence_pair(body, index_payload=index, indexed_body_sha256=digest, index_generated_at=index["generated_at"])
    _dir, manifest = write_generation(tmp_path, [EvidencePair(pack, graph, body)])
    return manifest


def _append(tmp_path: Path, prior: dict, *, ticker: str, text: str) -> dict:
    body = {
        "schema": "mastermind.tx/v1", "ticker": ticker, "id": "2026Q1",
        "period": "Q1 FY2026", "date": "2026-01-31", "title": f"{ticker} call",
        "segments": [{"speaker": "CFO", "role": "executive", "text": text}],
    }
    digest = canonical_body_sha256(body)
    index = {
        "schema": "mastermind.tx-index/v1", "generated_at": "2026-02-02T00:00:00Z",
        "symbols": {ticker: ["2026Q1"]}, "revisions": {f"{ticker}/2026Q1": digest},
        "dates": {f"{ticker}/2026Q1": "2026-01-31"}, "body_count": 2, "symbol_count": 2,
    }
    pack, graph = build_evidence_pair(body, index_payload=index, indexed_body_sha256=digest, index_generated_at=index["generated_at"])
    _dir, manifest = write_generation(
        tmp_path,
        [EvidencePair(pack, graph, body)],
        prior_manifest=prior,
        warnings=["backfill_pending"],
        coverage={
            "selection_policy": "append_only_full_index", "batch_limit": 100,
            "historical_completeness": False, "index_body_count": 2,
            "index_generated_at": index["generated_at"],
        },
    )
    return manifest


def test_r2_uploads_full_immutable_tree_before_mutable_root_marker(tmp_path: Path) -> None:
    manifest = _tree(tmp_path)
    fake = _FakeR2()
    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    keys = [key for key, _kwargs in fake.puts]
    assert keys[-1] == f"{PREFIX}/manifest.json"
    assert keys[-2] == f"{PREFIX}/generations/{manifest['generation_id']}/manifest.json"
    assert set(keys[:-2]) == {f"{PREFIX}/{receipt['object_key']}" for receipt in manifest["files"].values()}
    assert fake.puts[-1][1]["Metadata"]["generation-id"] == manifest["generation_id"]


def test_r2_existing_immutable_collision_never_advances_root_marker(tmp_path: Path) -> None:
    manifest = _tree(tmp_path)
    path = next(iter(manifest["files"]))
    key = f"{PREFIX}/{manifest['files'][path]['object_key']}"
    fake = _FakeR2()
    fake.objects[key] = b"forged collision"
    assert publish(tmp_path, s3=fake, bucket="bucket") == 1
    assert f"{PREFIX}/manifest.json" not in [written for written, _kwargs in fake.puts]


def test_r2_marker_cas_loss_is_safe_and_reported(tmp_path: Path) -> None:
    _tree(tmp_path)
    fake = _FakeR2(race_marker=True)
    assert publish(tmp_path, s3=fake, bucket="bucket") == PUBLISH_CONFLICT


def test_absent_credentials_is_deliberate_noop(monkeypatch, tmp_path: Path) -> None:
    _tree(tmp_path)
    monkeypatch.setattr("scripts.publish_earnings_evidence_graph_r2._client", lambda: None)
    assert publish(tmp_path) == 0


def test_remote_lineage_hydration_rejects_an_invalid_public_marker() -> None:
    fake = _FakeR2(marker={"schema": "untrusted"})
    with pytest.raises(ImmutableAddressIntegrityError, match="fails its contract"):
        load_remote_root_marker(s3=fake, bucket="bucket")


def test_append_uploads_only_new_content_addressed_objects_and_unchanged_root_is_noop(tmp_path: Path) -> None:
    first = _tree(tmp_path)
    fake = _FakeR2()
    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    fake.marker = first
    fake.puts.clear()
    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    assert fake.puts == []

    body = {
        "schema": "mastermind.tx/v1", "ticker": "MSFT", "id": "2026Q1",
        "period": "Q1 FY2026", "date": "2026-01-31", "title": "Microsoft call",
        "segments": [{"speaker": "CFO", "role": "executive", "text": "Revenue increased 13%."}],
    }
    digest = canonical_body_sha256(body)
    index = {
        "schema": "mastermind.tx-index/v1", "generated_at": "2026-02-02T00:00:00Z",
        "symbols": {"MSFT": ["2026Q1"]}, "revisions": {"MSFT/2026Q1": digest},
        "dates": {"MSFT/2026Q1": "2026-01-31"}, "body_count": 1, "symbol_count": 1,
    }
    pack, graph = build_evidence_pair(body, index_payload=index, indexed_body_sha256=digest, index_generated_at=index["generated_at"])
    _dir, second = write_generation(
        tmp_path,
        [EvidencePair(pack, graph, body)],
        prior_manifest=first,
        warnings=["backfill_pending"],
        coverage={
            "selection_policy": "append_only_full_index", "batch_limit": 100,
            "historical_completeness": False, "index_body_count": 2,
            "index_generated_at": index["generated_at"],
        },
    )
    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    keys = [key for key, _kwargs in fake.puts]
    old_keys = {receipt["object_key"] for receipt in first["files"].values()}
    new_keys = {receipt["object_key"] for receipt in second["files"].values()} - old_keys
    assert {key for key in keys if key.startswith(f"{PREFIX}/objects/")} == {f"{PREFIX}/{key}" for key in new_keys}
    assert keys[-2:] == [f"{PREFIX}/generations/{second['generation_id']}/manifest.json", f"{PREFIX}/manifest.json"]


def test_public_audit_replays_marker_manifest_and_every_cas_object(tmp_path: Path) -> None:
    _tree(tmp_path)
    fake = _FakeR2()
    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    assert audit_remote_generation(s3=fake, bucket="bucket")["status"] == "ready"


def test_disjoint_concurrent_appends_cannot_overwrite_their_shared_parent(tmp_path: Path) -> None:
    base = _tree(tmp_path / "base")
    fake = _FakeR2()
    assert publish(tmp_path / "base", s3=fake, bucket="bucket") == 0
    left = _append(tmp_path / "left", base, ticker="MSFT", text="Revenue increased 13%.")
    _right = _append(tmp_path / "right", base, ticker="GOOG", text="Revenue increased 14%.")
    base_digest = sha256_bytes(canonical_json_bytes(base))
    assert publish(tmp_path / "left", s3=fake, bucket="bucket", expected_base_marker_sha256=base_digest) == 0
    # The right candidate names base as its parent, not the now-current left
    # generation. Even a direct publisher invocation must fail closed.
    assert publish(tmp_path / "right", s3=fake, bucket="bucket") == PUBLISH_CONFLICT
    assert fake.marker["generation_id"] == left["generation_id"]


def test_same_event_correction_race_cannot_replace_a_newer_correction(tmp_path: Path) -> None:
    base = _tree(tmp_path / "base")
    fake = _FakeR2()
    assert publish(tmp_path / "base", s3=fake, bucket="bucket") == 0
    first = _append(tmp_path / "first", base, ticker="AAPL", text="Revenue increased 13%.")
    _second = _append(tmp_path / "second", base, ticker="AAPL", text="Revenue increased 14%.")
    assert publish(tmp_path / "first", s3=fake, bucket="bucket") == 0
    assert publish(tmp_path / "second", s3=fake, bucket="bucket") == PUBLISH_CONFLICT
    assert fake.marker["generation_id"] == first["generation_id"]
