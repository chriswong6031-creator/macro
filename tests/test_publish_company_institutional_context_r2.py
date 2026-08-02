from __future__ import annotations

import io

from engine.company_institutional_context.views import write_generation
from scripts.publish_company_institutional_context_r2 import PREFIX, PUBLISH_CONFLICT, publish
from tests.test_company_institutional_context import _bundle


class FakeR2:
    def __init__(self):
        self.objects = {}
        self.puts = []
        self.fail_cas = False

    def get_object(self, *, Bucket, Key):
        if Key in self.objects:
            body, _meta = self.objects[Key]
            return {"Body": io.BytesIO(body), "ETag": "etag"}
        raise RuntimeError("missing")

    def head_object(self, *, Bucket, Key):
        if Key in self.objects:
            body, metadata = self.objects[Key]
            return {"Metadata": metadata, "ContentLength": len(body)}
        raise RuntimeError("missing")

    def put_object(self, **kwargs):
        if self.fail_cas and kwargs["Key"].endswith("/manifest.json") and "generations" not in kwargs["Key"]:
            raise type("Precondition", (Exception,), {"response": {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}}})()
        if kwargs.get("IfNoneMatch") == "*" and kwargs["Key"] in self.objects:
            raise RuntimeError("collision")
        self.puts.append((kwargs["Key"], kwargs))
        self.objects[kwargs["Key"]] = (kwargs["Body"], dict(kwargs.get("Metadata") or {}))


def test_publish_immutable_before_marker_heals_and_honors_dry_run(tmp_path) -> None:
    contexts, manifest, _root, _universe, _config = _bundle(tmp_path)
    write_generation(tmp_path / "out", contexts, manifest)
    client = FakeR2()
    assert publish(tmp_path / "out", dry_run=True, s3=client, bucket="bucket") == 0
    assert not client.objects
    assert publish(tmp_path / "out", s3=client, bucket="bucket") == 0
    keys = [key for key, _kwargs in client.puts]
    assert keys[-1] == f"{PREFIX}/manifest.json"
    assert all(f"{PREFIX}/generations/" in key for key in keys[:-1])
    root = f"{PREFIX}/manifest.json"
    client.objects = {key: value for key, value in client.objects.items() if key == root}
    client.puts.clear()
    assert publish(tmp_path / "out", s3=client, bucket="bucket") == 0
    assert root not in [key for key, _kwargs in client.puts]


def test_publish_rejects_immutable_collision_and_returns_safe_cas_conflict(tmp_path) -> None:
    contexts, manifest, _root, _universe, _config = _bundle(tmp_path)
    write_generation(tmp_path / "out", contexts, manifest)
    client = FakeR2()
    generation = manifest["generation_id"]
    key = f"{PREFIX}/generations/{generation}/companies/AAPL.json"
    client.objects[key] = (b"wrong", {"sha256": "0" * 64})
    assert publish(tmp_path / "out", s3=client, bucket="bucket") == 1
    client = FakeR2()
    client.fail_cas = True
    assert publish(tmp_path / "out", s3=client, bucket="bucket") == PUBLISH_CONFLICT
