from __future__ import annotations

import io
import json

from engine.company_theme_exposure.views import build_bundle, write_generation
from scripts.publish_company_theme_exposure_r2 import PREFIX, publish

from tests.test_company_theme_exposure import _company_tree, _crosswalk, _membership, _state


class FakeR2:
    def __init__(self):
        self.objects = {}
        self.puts = []

    def get_object(self, *, Bucket, Key):
        if Key in self.objects:
            body, _ = self.objects[Key]
            return {"Body": io.BytesIO(body), "ETag": "etag"}
        raise RuntimeError("missing")

    def head_object(self, *, Bucket, Key):
        if Key in self.objects:
            body, metadata = self.objects[Key]
            return {"Metadata": metadata, "ContentLength": len(body)}
        raise RuntimeError("missing")

    def put_object(self, **kwargs):
        if kwargs.get("IfNoneMatch") == "*" and kwargs["Key"] in self.objects:
            raise RuntimeError("collision")
        self.puts.append((kwargs["Key"], kwargs))
        self.objects[kwargs["Key"]] = (kwargs["Body"], dict(kwargs.get("Metadata") or {}))


def test_immutable_objects_and_generation_manifest_precede_root_marker(tmp_path) -> None:
    contexts, ci_manifest = _company_tree(tmp_path / "company")
    exposures, manifest = build_bundle(
        contexts, company_manifest=ci_manifest, membership=_membership(), crosswalk=_crosswalk(), theme_state=_state(), as_of="2026-02-02",
    )
    write_generation(tmp_path / "out", exposures, manifest)
    client = FakeR2()
    assert publish(tmp_path / "out", s3=client, bucket="bucket") == 0
    keys = [key for key, _ in client.puts]
    assert keys[-1] == f"{PREFIX}/manifest.json"
    assert all(f"{PREFIX}/generations/" in key for key in keys[:-1])
    assert keys[-2].endswith("/manifest.json")
    assert client.puts[-1][1]["Metadata"]["generation-id"] == manifest["generation_id"]
