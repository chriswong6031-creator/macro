"""Restore-leg guarantees in scripts/fetch_r2.py: manifest keys never land on
disk (nested-manifest growth), warm files aren't re-downloaded, and an EMPTY
R2 prefix is a FAILURE (exit 1) — daily.yml gates the attention publish-back
on that exit code, so 'restored nothing' must never read as success (a shallow
collector rebuild would then clobber the deep store). Stubbed s3 — no boto3
creds needed."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import scripts.fetch_r2 as fetch_r2

_ROOT = Path(__file__).resolve().parents[1]


class _FakeS3:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.downloads: list[str] = []
        self.transfer_configs: list[object] = []

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        contents = [{"Key": k, "ETag": f'"{hashlib.md5(v).hexdigest()}"', "Size": len(v)}
                    for k, v in self.objects.items() if k.startswith(Prefix)]
        return {"Contents": contents, "IsTruncated": False}

    def download_file(self, bucket, key, dest, Config=None):
        self.downloads.append(key)
        self.transfer_configs.append(Config)
        Path(dest).write_bytes(self.objects[key])


def _wire(monkeypatch, tmp_path, objects):
    s3 = _FakeS3(objects)
    monkeypatch.setattr(fetch_r2, "_client", lambda *a, **k: s3)
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
    monkeypatch.setattr(fetch_r2, "_client", lambda *a, **k: None)
    assert fetch_r2.fetch(["attention"]) == 0


def test_restore_leg_sizes_its_own_pool(monkeypatch, tmp_path):
    """The RESTORE leg is the one you run when you actually need the backup —
    download_file fans a large object into concurrent ranged GETs just as
    upload_file fans out parts, so it must size the pool for ITS worker count
    rather than inherit publish()'s default (see publish_r2._pool_size)."""
    seen: list[int] = []
    s3 = _wire(monkeypatch, tmp_path, {"attention/A.parquet": b"deep-history-bytes"})

    def _spy(workers=32, *a, **k):
        seen.append(workers)
        return s3

    monkeypatch.setattr(fetch_r2, "_client", _spy)
    assert fetch_r2.fetch(["attention"], workers=4) == 0
    assert seen == [4], f"fetch did not hand its worker count to the client: {seen}"


def _subproc_repo(tmp_path: Path) -> Path:
    """Copy the real modules into a tmp repo root so a fresh interpreter
    exercises the SHIPPED import order against a controlled ROOT/.env
    (lib.config resolves ROOT from its own file location — see the twin
    helper in test_publish_r2)."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "lib").mkdir()
    for rel in ("scripts/publish_r2.py", "scripts/fetch_r2.py", "lib/config.py"):
        (root / rel).write_text((_ROOT / rel).read_text())
    (root / "lib" / "__init__.py").write_text("")  # scripts/ is a namespace pkg
    return root


def _run_clean(code: str, root: Path) -> subprocess.CompletedProcess:
    """Fresh interpreter, every R2_* var stripped, cwd at the tmp repo root;
    PYTHONPATH dropped so the real checkout can never shadow the tmp copies."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("R2_") and k != "PYTHONPATH"}
    return subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                          capture_output=True, text=True, timeout=120)


def test_module_import_loads_dotenv_before_client_reads_creds(tmp_path):
    """Regression (2026-08-06): fetch() called _client() before lib.config was
    imported (the import sat mid-function, after the creds check), so a local
    `python -m scripts.fetch_r2` with a fully-keyed ROOT/.env no-op'd as
    "no R2 creds — skip". Importing the module must be enough to surface .env
    creds to _client."""
    root = _subproc_repo(tmp_path)
    (root / ".env").write_text(
        "R2_ENDPOINT=https://env-order.example\n"
        "R2_ACCESS_KEY_ID=env-order-ak\n"
        "R2_SECRET_ACCESS_KEY=env-order-sk\n"
        "R2_BUCKET=env-order-bucket\n")
    proc = _run_clean(
        "import json, os\n"
        "import scripts.fetch_r2\n"
        "print(json.dumps([os.environ.get(k) for k in ("
        "'R2_ENDPOINT', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')]))\n",
        root)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == [
        "https://env-order.example", "env-order-ak", "env-order-sk",
        "env-order-bucket"]


def test_no_dotenv_no_creds_still_graceful_noop(tmp_path):
    """The .env hoist must not break the other half of the contract: with no
    .env and no env vars, fetch() still no-ops at exit 0 through the REAL
    _client (no boto3 import, no traceback)."""
    root = _subproc_repo(tmp_path)
    proc = _run_clean(
        "import sys\n"
        "from scripts.fetch_r2 import fetch\n"
        "sys.exit(fetch(['attention']))\n",
        root)
    assert proc.returncode == 0, proc.stderr
    assert "no R2 creds" in proc.stderr
