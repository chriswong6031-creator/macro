from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from engine.earnings_narrative.contracts import canonical_json_bytes, sha256_bytes
from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_transcript_intake import canonical_body_sha256
from scripts import publish_earnings_story_packets_r2 as story_publisher
from scripts import refresh_earnings_story_packets as refresh_module


class _PreconditionFailed(RuntimeError):
    response = {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}}


class _FakeR2:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.puts: list[str] = []

    @staticmethod
    def _etag(body: bytes) -> str:
        return '"' + sha256_bytes(body)[:32] + '"'

    def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
        if Key not in self.objects:
            raise RuntimeError("missing")
        body = self.objects[Key]
        return {"Body": io.BytesIO(body), "ETag": self._etag(body)}

    def head_object(self, *, Bucket: str, Key: str):  # noqa: N803
        if Key not in self.objects:
            raise RuntimeError("missing")
        return {
            "ContentLength": len(self.objects[Key]),
            "Metadata": self.metadata.get(Key, {}),
        }

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        body = kwargs["Body"]
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise _PreconditionFailed()
        if "IfMatch" in kwargs:
            current = self.objects.get(key)
            if current is None or kwargs["IfMatch"] != self._etag(current):
                raise _PreconditionFailed()
        self.objects[key] = body
        self.metadata[key] = dict(kwargs.get("Metadata") or {})
        self.puts.append(key)


def _body(*, guidance: str = "For the full year, we expect revenue of 500 million and an operating margin of 20%.") -> dict:
    return {
        "schema": "mastermind.tx/v1",
        "ticker": "AAPL",
        "id": "2026Q1",
        "period": "Q1 FY2026",
        "date": "2026-01-30",
        "title": "AAPL earnings call",
        "segments": [
            {
                "speaker": "Chief Executive Officer",
                "role": "executive",
                "text": "Revenue grew 12% to 120 million, while gross margin reached 45%.",
            },
            {
                "speaker": "Chief Financial Officer",
                "role": "executive",
                "text": guidance,
            },
            {
                "speaker": "Chief Executive Officer",
                "role": "executive",
                "text": "We will invest 50 million in capacity and continue our share repurchase program.",
            },
            {
                "speaker": "Research Analyst",
                "role": "analyst",
                "text": "Can you discuss customer demand and the 10% slowdown in Europe?",
            },
        ],
    }


def _write_evidence(root: Path, body: dict, *, generated_at: str) -> dict:
    body_sha = canonical_body_sha256(body)
    index = {
        "schema": "mastermind.tx-index/v1",
        "generated_at": generated_at,
        "symbols": {"AAPL": ["2026Q1"]},
        "revisions": {"AAPL/2026Q1": body_sha},
        "dates": {"AAPL/2026Q1": "2026-01-30"},
        "body_count": 1,
        "symbol_count": 1,
    }
    fact_pack, claim_graph = build_evidence_pair(
        body,
        index_payload=index,
        indexed_body_sha256=body_sha,
        index_generated_at=generated_at,
    )
    _generation, manifest = write_generation(
        root,
        [EvidencePair(fact_pack=fact_pack, claim_graph=claim_graph, transcript=body)],
        coverage={
            "selection_policy": "explicit_input",
            "batch_limit": 1,
            "historical_completeness": False,
            "index_body_count": 1,
            "index_generated_at": generated_at,
        },
    )
    return manifest


def _seed_evidence(fake: _FakeR2, root: Path, manifest: dict) -> None:
    prefix = refresh_module.EVIDENCE_PREFIX
    marker = canonical_json_bytes(manifest)
    fake.objects[f"{prefix}/manifest.json"] = marker
    fake.objects[f"{prefix}/generations/{manifest['generation_id']}/manifest.json"] = marker
    for receipt in manifest["files"].values():
        body = (root / receipt["object_key"]).read_bytes()
        fake.objects[f"{prefix}/{receipt['object_key']}"] = body
        fake.metadata[f"{prefix}/{receipt['object_key']}"] = {"sha256": receipt["sha256"]}


def _public_packet(fake: _FakeR2) -> tuple[dict, dict]:
    marker = json.loads(fake.objects[f"{story_publisher.PREFIX}/manifest.json"])
    index = marker["packets"]["AAPL/2026Q1"]
    packet = json.loads(fake.objects[f"{story_publisher.PREFIX}/{index['object_key']}"])
    return marker, packet


def test_refresh_publishes_a_verified_projection_then_exact_root_is_noop(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence-source"
    manifest = _write_evidence(evidence, _body(), generated_at="2026-02-01T00:00:00Z")
    fake = _FakeR2()
    _seed_evidence(fake, evidence, manifest)

    assert refresh_module.refresh(
        tmp_path / "run-one",
        promote=True,
        s3=fake,
        bucket="bucket",
    ) == 0
    marker, packet = _public_packet(fake)
    assert marker["evidence_root"]["generation_id"] == manifest["generation_id"]
    assert packet["promotion"]["tier"] == "B"
    assert packet["execution"] == {"mode": "deterministic", "providers": [], "model_calls": 0, "tokens": 0}
    assert story_publisher.audit_remote_generation(s3=fake, bucket="bucket")["packet_count"] == 1

    fake.puts.clear()
    assert refresh_module.refresh(
        tmp_path / "run-two",
        promote=True,
        s3=fake,
        bucket="bucket",
    ) == 0
    assert fake.puts == []

    event = manifest["events"]["AAPL/2026Q1"]
    source_receipt = manifest["files"][event["source_body"]]
    del fake.objects[f"{refresh_module.EVIDENCE_PREFIX}/{source_receipt['object_key']}"]
    with pytest.raises(
        story_publisher.ImmutableAddressIntegrityError,
        match="bound evidence object",
    ):
        story_publisher.audit_remote_generation(s3=fake, bucket="bucket")


def test_refresh_hydrates_prior_lineage_and_compiles_a_source_correction(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence-source"
    first = _write_evidence(evidence, _body(), generated_at="2026-02-01T00:00:00Z")
    fake = _FakeR2()
    _seed_evidence(fake, evidence, first)
    assert refresh_module.refresh(tmp_path / "run-one", promote=True, s3=fake, bucket="bucket") == 0
    first_marker, first_packet = _public_packet(fake)

    corrected = _write_evidence(
        evidence,
        _body(guidance="For the full year, we expect revenue of 510 million and an operating margin of 21%."),
        generated_at="2026-02-02T00:00:00Z",
    )
    _seed_evidence(fake, evidence, corrected)
    assert refresh_module.refresh(tmp_path / "run-two", promote=True, s3=fake, bucket="bucket") == 0
    corrected_marker, corrected_packet = _public_packet(fake)
    assert corrected_marker["parent_generation_id"] == first_marker["generation_id"]
    assert corrected_packet["story"]["story_id"] == first_packet["story"]["story_id"]
    assert corrected_packet["story"]["correction"]["status"] == "corrected"
    assert corrected_packet["prior"]["packet_id"] == first_packet["packet_id"]
    health = story_publisher.audit_remote_generation(s3=fake, bucket="bucket")
    assert health["status"] == "ready"
    assert health["packet_count"] == 1

    first_event = first["events"]["AAPL/2026Q1"]
    first_source = first["files"][first_event["source_body"]]
    del fake.objects[f"{refresh_module.EVIDENCE_PREFIX}/{first_source['object_key']}"]
    with pytest.raises(
        story_publisher.ImmutableAddressIntegrityError,
        match="bound evidence object",
    ):
        story_publisher.audit_remote_generation(s3=fake, bucket="bucket")


def test_refresh_refuses_a_root_whose_immutable_generation_differs(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence-source"
    manifest = _write_evidence(evidence, _body(), generated_at="2026-02-01T00:00:00Z")
    fake = _FakeR2()
    _seed_evidence(fake, evidence, manifest)
    fake.objects[
        f"{refresh_module.EVIDENCE_PREFIX}/generations/{manifest['generation_id']}/manifest.json"
    ] = b'{"forged":true}\n'
    with pytest.raises(refresh_module.RefreshError, match="differs from its root marker"):
        refresh_module.refresh(tmp_path / "run", promote=True, s3=fake, bucket="bucket")
