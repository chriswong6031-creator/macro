from __future__ import annotations

import io
import json
from pathlib import Path

from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_transcript_intake import canonical_body_sha256
from scripts.publish_earnings_evidence_graph_r2 import PUBLISH_CONFLICT, PREFIX, publish


class _PreconditionFailed(RuntimeError):
    response = {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}}


class _FakeR2:
    def __init__(self, *, marker: dict | None = None, marker_etag: str = "prior", race_marker: bool = False) -> None:
        self.marker = marker
        self.marker_etag = marker_etag
        self.race_marker = race_marker
        self.objects: dict[str, bytes] = {}
        self.puts: list[tuple[str, dict]] = []

    def get_object(self, *, Bucket, Key):
        if Key == f"{PREFIX}/manifest.json" and self.marker is not None:
            return {"Body": io.BytesIO(json.dumps(self.marker).encode("utf-8")), "ETag": self.marker_etag}
        if Key in self.objects:
            return {"Body": io.BytesIO(self.objects[Key])}
        raise RuntimeError("missing")

    def head_object(self, *, Bucket, Key):
        if Key in self.objects:
            return {"ContentLength": len(self.objects[Key]), "Metadata": {"sha256": "unused"}}
        raise RuntimeError("missing")

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if key == f"{PREFIX}/manifest.json" and self.race_marker:
            raise _PreconditionFailed()
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise _PreconditionFailed()
        self.puts.append((key, kwargs))
        self.objects[key] = kwargs["Body"]


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
    _dir, manifest = write_generation(tmp_path, [EvidencePair(pack, graph)])
    return manifest


def test_r2_uploads_full_immutable_tree_before_mutable_root_marker(tmp_path: Path) -> None:
    manifest = _tree(tmp_path)
    fake = _FakeR2()
    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    keys = [key for key, _kwargs in fake.puts]
    assert keys[-1] == f"{PREFIX}/manifest.json"
    assert keys[-2] == f"{PREFIX}/generations/{manifest['generation_id']}/manifest.json"
    assert set(keys[:-2]) == {f"{PREFIX}/generations/{manifest['generation_id']}/{path}" for path in manifest["files"]}
    assert fake.puts[-1][1]["Metadata"]["generation-id"] == manifest["generation_id"]


def test_r2_existing_immutable_collision_never_advances_root_marker(tmp_path: Path) -> None:
    manifest = _tree(tmp_path)
    path = next(iter(manifest["files"]))
    key = f"{PREFIX}/generations/{manifest['generation_id']}/{path}"
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
