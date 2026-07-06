"""Restore-leg guarantees in scripts/fetch_r2.py: manifest keys never land on
disk (nested-manifest growth), warm files aren't re-downloaded, and an EMPTY
R2 prefix is a FAILURE (exit 1) — daily.yml gates the attention publish-back
on that exit code, so 'restored nothing' must never read as success (a shallow
collector rebuild would then clobber the deep store). Stubbed s3 — no boto3
creds needed."""
from __future__ import annotations

import hashlib
from pathlib import Path

import scripts.fetch_r2 as fetch_r2


class _FakeS3:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.downloads: list[str] = []

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        contents = [{"Key": k, "ETag": f'"{hashlib.md5(v).hexdigest()}"', "Size": len(v)}
                    for k, v in self.objects.items() if k.startswith(Prefix)]
        return {"Contents": contents, "IsTruncated": False}

    def download_file(self, bucket, key, dest):
        self.downloads.append(key)
        Path(dest).write_bytes(self.objects[key])


def _wire(monkeypatch, tmp_path, objects):
    s3 = _FakeS3(objects)
    monkeypatch.setattr(fetch_r2, "_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    monkeypatch.setattr("lib.config.ROOT", tmp_path)
    monkeypatch.setattr("lib.config.load",
                        lambda: {"storage": {"site_dir": "site", "data_dir": "data"}})
    return s3


def test_restore_writes_data_dir_and_skips_manifest(monkeypatch, tmp_path):
    s3 = _wire(monkeypatch, tmp_path, {
        "attention/A.parquet": b"deep-history-bytes",
        "attention/_manifest.json": b'{"count": 1}',
    })
    assert fetch_r2.fetch(["attention"]) == 0
    base = tmp_path / "data" / "attention"
    assert (base / "A.parquet").read_bytes() == b"deep-history-bytes"
    assert not (base / "_manifest.json").exists()
    assert s3.downloads == ["attention/A.parquet"]


def test_current_files_not_redownloaded(monkeypatch, tmp_path):
    body = b"already-here"
    s3 = _wire(monkeypatch, tmp_path, {"attention/A.parquet": body})
    dest = tmp_path / "data" / "attention"
    dest.mkdir(parents=True)
    (dest / "A.parquet").write_bytes(body)
    assert fetch_r2.fetch(["attention"]) == 0
    assert s3.downloads == []


def test_empty_prefix_is_a_failure(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, {})
    assert fetch_r2.fetch(["attention"]) == 1


def test_missing_creds_is_graceful_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_r2, "_client", lambda: None)
    assert fetch_r2.fetch(["attention"]) == 0
