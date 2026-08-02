from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from engine.earnings_narrative.contracts import canonical_json_bytes, sha256_bytes
from scripts import publish_earnings_story_packets_r2 as publisher


class _PreconditionFailed(RuntimeError):
    response = {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}}


class _FakeR2:
    def __init__(self, *, marker: dict | None = None, marker_etag: str = "prior", race_marker: bool = False) -> None:
        self.marker = marker
        self.marker_body = canonical_json_bytes(marker) if marker is not None else None
        self.marker_etag = marker_etag
        self.race_marker = race_marker
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.puts: list[tuple[str, dict]] = []

    def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
        if Key == f"{publisher.PREFIX}/manifest.json" and self.marker_body is not None:
            return {"Body": io.BytesIO(self.marker_body), "ETag": self.marker_etag}
        if Key in self.objects:
            return {"Body": io.BytesIO(self.objects[Key])}
        raise RuntimeError("missing")

    def head_object(self, *, Bucket: str, Key: str):  # noqa: N803
        if Key in self.objects:
            return {"ContentLength": len(self.objects[Key]), "Metadata": self.metadata.get(Key, {})}
        raise RuntimeError("missing")

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if key == f"{publisher.PREFIX}/manifest.json" and self.race_marker:
            raise _PreconditionFailed()
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise _PreconditionFailed()
        self.puts.append((key, kwargs))
        self.objects[key] = kwargs["Body"]
        self.metadata[key] = dict(kwargs.get("Metadata") or {})
        if key == f"{publisher.PREFIX}/manifest.json":
            self.marker_body = kwargs["Body"]
            self.marker = json.loads(kwargs["Body"].decode("utf-8"))


def _manifest_is_valid(payload: object) -> None:
    if not isinstance(payload, dict):
        raise ValueError("manifest must be object")
    required = {"schema", "generation_id", "parent_generation_id", "status", "packets", "files"}
    if set(payload) != required or payload["schema"] != "earnings.story_packet_catalog/v1":
        raise ValueError("manifest fields")
    if payload["status"] != "ready" or not isinstance(payload["packets"], dict) or not payload["packets"]:
        raise ValueError("manifest catalog")
    if not isinstance(payload["files"], dict) or not payload["files"]:
        raise ValueError("manifest files")


def _verify_store(out_dir: Path, *, manifest: dict) -> dict[str, int | str]:
    _manifest_is_valid(manifest)
    root = Path(out_dir)
    if (root / "manifest.json").read_bytes() != canonical_json_bytes(manifest):
        raise ValueError("root receipt")
    if (root / "generations" / manifest["generation_id"] / "manifest.json").read_bytes() != canonical_json_bytes(manifest):
        raise ValueError("generation receipt")
    for receipt in manifest["files"].values():
        body = (root / receipt["object_key"]).read_bytes()
        if len(body) != receipt["bytes"] or sha256_bytes(body) != receipt["sha256"]:
            raise ValueError("object receipt")
    return {"status": "ready", "packet_count": len(manifest["packets"])}


@pytest.fixture(autouse=True)
def _projection_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publisher, "_story_contracts", lambda: (_manifest_is_valid, _verify_store))
    monkeypatch.setattr(publisher, "_audit_bound_evidence", lambda *args, **kwargs: None)


def _write_tree(
    root: Path,
    *,
    generation: str = "packet_one",
    parent: str | None = None,
    packets: tuple[str, ...] = ("earnings:AAPL/2026Q1",),
) -> dict:
    files: dict[str, dict] = {}
    for packet in packets:
        body = canonical_json_bytes({"packet": packet, "generation": generation})
        digest = sha256_bytes(body)
        object_key = f"objects/{digest}.json"
        path = root / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        files[f"packets/{packet}.json"] = {"object_key": object_key, "sha256": digest, "bytes": len(body)}
    manifest = {
        "schema": "earnings.story_packet_catalog/v1",
        "generation_id": generation,
        "parent_generation_id": parent,
        "status": "ready",
        "packets": {packet: {"object": f"packets/{packet}.json"} for packet in packets},
        "files": files,
    }
    (root / "generations" / generation).mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    (root / "generations" / generation / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    return manifest


def test_r2_uploads_immutable_objects_then_generation_then_root(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    keys = [key for key, _kwargs in fake.puts]
    assert keys[-2:] == [
        f"{publisher.PREFIX}/generations/{manifest['generation_id']}/manifest.json",
        f"{publisher.PREFIX}/manifest.json",
    ]
    assert set(keys[:-2]) == {f"{publisher.PREFIX}/{row['object_key']}" for row in manifest["files"].values()}
    assert fake.puts[-1][1]["IfNoneMatch"] == "*"
    assert fake.puts[-1][1]["Metadata"]["generation-id"] == manifest["generation_id"]


def test_existing_immutable_collision_cannot_advance_root(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path)
    receipt = next(iter(manifest["files"].values()))
    key = f"{publisher.PREFIX}/{receipt['object_key']}"
    fake = _FakeR2()
    fake.objects[key] = b"forged collision"
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 1
    assert f"{publisher.PREFIX}/manifest.json" not in [key for key, _kwargs in fake.puts]


def test_marker_compare_and_swap_loss_is_safe_and_reported(tmp_path: Path) -> None:
    _write_tree(tmp_path)
    assert publisher.publish(tmp_path, s3=_FakeR2(race_marker=True), bucket="bucket") == publisher.PUBLISH_CONFLICT


def test_absent_credentials_is_deliberate_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_tree(tmp_path)
    monkeypatch.setattr(publisher, "_client", lambda: None)
    assert publisher.publish(tmp_path) == 0


def test_stale_parent_cannot_replace_current_catalog(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir)
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0
    next_dir = tmp_path / "next"
    _write_tree(next_dir, generation="packet_two", parent="some_other_parent", packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"))
    assert publisher.publish(next_dir, s3=fake, bucket="bucket") == publisher.PUBLISH_CONFLICT
    assert fake.marker == base


def test_ready_root_may_not_shrink_packet_catalog(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir, packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"))
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0
    shrink_dir = tmp_path / "shrink"
    _write_tree(shrink_dir, generation="packet_two", parent=base["generation_id"])
    assert publisher.publish(shrink_dir, s3=fake, bucket="bucket") == 1
    assert fake.marker == base


def test_unchanged_root_is_a_true_noop_and_public_audit_replays_every_receipt(tmp_path: Path) -> None:
    _write_tree(tmp_path)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    fake.puts.clear()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    assert fake.puts == []
    health = publisher.audit_remote_generation(s3=fake, bucket="bucket")
    assert health == {"status": "ready", "packet_count": 1}


def test_public_audit_rejects_a_tampered_referenced_object(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    receipt = next(iter(manifest["files"].values()))
    fake.objects[f"{publisher.PREFIX}/{receipt['object_key']}"] = b'{"forged":true}\n'
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="public earnings story packet audit failed"):
        publisher.audit_remote_generation(s3=fake, bucket="bucket")


def test_public_audit_materializes_and_replays_parent_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir)
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0
    next_dir = tmp_path / "next"
    _write_tree(
        next_dir,
        generation="packet_two",
        parent=base["generation_id"],
        packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"),
    )
    assert publisher.publish(next_dir, s3=fake, bucket="bucket") == 0

    def verify_with_lineage(out_dir: Path, *, manifest: dict) -> dict[str, int | str]:
        health = _verify_store(out_dir, manifest=manifest)
        cursor = manifest
        while cursor["parent_generation_id"] is not None:
            parent_path = Path(out_dir) / "generations" / cursor["parent_generation_id"] / "manifest.json"
            parent = json.loads(parent_path.read_text(encoding="utf-8"))
            _manifest_is_valid(parent)
            if parent["generation_id"] != cursor["parent_generation_id"]:
                raise ValueError("parent receipt")
            cursor = parent
        return health

    monkeypatch.setattr(publisher, "_story_contracts", lambda: (_manifest_is_valid, verify_with_lineage))
    assert publisher.audit_remote_generation(s3=fake, bucket="bucket") == {
        "status": "ready",
        "packet_count": 2,
    }


def test_remote_marker_contract_failure_cannot_supply_lineage() -> None:
    fake = _FakeR2(marker={"schema": "untrusted"})
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="fails its contract"):
        publisher.load_remote_root_marker(s3=fake, bucket="bucket")
