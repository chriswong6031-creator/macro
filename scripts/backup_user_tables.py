"""Nightly encrypted dump of customer/billing tables to private R2 (MMX-001 / GATE-1).

WS-1 in research/MASTERMIND_RED_TEAM_REMEDIATION_PLAN.md. This is the belt-and-braces
copy of the tables whose loss is existential: entitlements, Stripe idempotency, and
the user workspace. Supabase-managed backups (if the plan has them) are a separate
control; this job does not replace them and does not claim they exist.

Dump backends
-------------
* ``pg_dump`` when ``SUPABASE_DB_URL`` or ``DATABASE_URL`` is set (preferred).
* PostgREST (service-role) when only ``SUPABASE_URL`` + service key are set.
  The VPS already carries those in ``/etc/macro-api.env``; the direct DB URL
  is an operator add in ``/etc/macro-user-backup.env``.

Neither backend is optional at runtime: missing source, missing encryption key,
or missing destination (R2 or ``--local-dir``) exits 2. A partial table set is
not uploaded.

Restore is refuse-closed against production. ``restore`` requires
``--i-am-restoring-into-scratch`` AND a destination whose project ref / URL
does not match the production project. There is no override flag that accepts
the production ref. Never point this at the live project.

Stdlib + openssl + optional boto3. No repo-package imports — the observer of
last resort for customer data must not depend on config.yml or the engine tree.

Usage
-----
    python -m scripts.backup_user_tables dump
    python -m scripts.backup_user_tables dump --local-dir /tmp/mmx-backups
    python -m scripts.backup_user_tables list --local-dir /tmp/mmx-backups
    python -m scripts.backup_user_tables verify --backup-id <id> --local-dir /tmp/mmx-backups
    python -m scripts.backup_user_tables restore --backup-id <id> \\
        --dest-db-url "$SCRATCH_DB_URL" --i-am-restoring-into-scratch
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

SCHEMA = "mmx.user_table_backup.v1"
RECEIPT_SCHEMA = "mmx.user_table_restore_receipt.v1"
PROTECTED_TABLES: tuple[str, ...] = (
    "profiles",
    "watchlists",
    "watchlist_symbols",
    "chart_layouts",
    "saved_scripts",
    "alerts",
    "favorites",
    "user_entitlements",
    "stripe_events",
)
# Parents before children. auth.users is owned by GoTrue and is NOT in this
# dump; a scratch project must already have matching users, or the restore
# must run with session_replication_role = replica (pg_dump path does).
RESTORE_ORDER: tuple[str, ...] = (
    "profiles",
    "watchlists",
    "watchlist_symbols",
    "chart_layouts",
    "saved_scripts",
    "alerts",
    "favorites",
    "user_entitlements",
    "stripe_events",
)
PRODUCTION_PROJECT_REFS: tuple[str, ...] = ("fsldfzlxyavsuwqbceod",)
DEFAULT_PREFIX = "private/user-table-backups/"
DEFAULT_RETENTION_DAYS = 30
RPO_DECLARED_HOURS = 24
RTO_TARGET_MINUTES = 30
OPENSSL_ITER_DEFAULT = 200_000
CIPHER = "openssl-aes-256-cbc-pbkdf2"
EXIT_USAGE = 2


class BackupError(RuntimeError):
    """Fail-closed operational error. Message is safe to print (no secrets)."""


@dataclass
class ObjectMeta:
    key: str
    last_modified: datetime
    size: int = 0


class ObjectStore:
    """Minimal put/get/list/delete. Tests inject MemoryStore; prod uses R2."""

    def put(self, key: str, data: bytes, *, content_type: str = "") -> None:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def list(self, prefix: str) -> list[ObjectMeta]:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class MemoryStore(ObjectStore):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.mtime: dict[str, datetime] = {}

    def put(self, key: str, data: bytes, *, content_type: str = "") -> None:
        self.objects[key] = data
        self.mtime[key] = datetime.now(timezone.utc)

    def get(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as exc:
            raise BackupError(f"object not found: {key}") from exc

    def list(self, prefix: str) -> list[ObjectMeta]:
        out = []
        for key, data in self.objects.items():
            if key.startswith(prefix):
                out.append(ObjectMeta(key=key, last_modified=self.mtime[key], size=len(data)))
        return sorted(out, key=lambda item: item.key)

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.mtime.pop(key, None)


class LocalDirStore(ObjectStore):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if key.startswith("/") or ".." in Path(key).parts:
            raise BackupError(f"refusing unsafe object key: {key}")
        return self.root / key

    def put(self, key: str, data: bytes, *, content_type: str = "") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise BackupError(f"object not found: {key}")
        return path.read_bytes()

    def list(self, prefix: str) -> list[ObjectMeta]:
        out: list[ObjectMeta] = []
        base = self.root
        if not base.exists():
            return out
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            key = path.relative_to(base).as_posix()
            if key.startswith(prefix):
                stat = path.stat()
                out.append(ObjectMeta(
                    key=key,
                    last_modified=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                    size=stat.st_size,
                ))
        return sorted(out, key=lambda item: item.key)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()


class R2Store(ObjectStore):
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put(self, key: str, data: bytes, *, content_type: str = "") -> None:
        extra: dict[str, str] = {}
        if content_type:
            extra["ContentType"] = content_type
        extra["ServerSideEncryption"] = "AES256"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)

    def get(self, key: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise BackupError(f"R2 get failed for {key}") from exc
        return resp["Body"].read()

    def list(self, prefix: str) -> list[ObjectMeta]:
        out: list[ObjectMeta] = []
        token = None
        while True:
            kw: dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kw["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kw)
            for item in resp.get("Contents") or []:
                modified = item["LastModified"]
                if modified.tzinfo is None:
                    modified = modified.replace(tzinfo=timezone.utc)
                out.append(ObjectMeta(
                    key=item["Key"],
                    last_modified=modified,
                    size=int(item.get("Size") or 0),
                ))
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return out

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@dataclass
class TableDump:
    name: str
    rows: list[dict[str, Any]]
    sha256: str
    raw: bytes


@dataclass
class BackupArtifact:
    backup_id: str
    manifest: dict[str, Any]
    plaintext: bytes
    ciphertext: bytes
    tables: dict[str, TableDump] = field(default_factory=dict)


TableFetcher = Callable[[str], list[dict[str, Any]]]
TableWriter = Callable[[str, list[dict[str, Any]]], int]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_backup_id(now: datetime | None = None) -> str:
    stamp = (now or utcnow()).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"user-tables-{stamp}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def require_env(name: str) -> str:
    value = env(name)
    if not value:
        raise BackupError(f"{name} is required")
    return value


def redact_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    netloc = parsed.netloc
    if "@" in netloc:
        userinfo, _, host = netloc.rpartition("@")
        account = userinfo.split(":", 1)[0]
        netloc = f"{account}:***@{host}"
    return parsed._replace(netloc=netloc).geturl()


def project_ref_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    match = re.match(r"^([a-z0-9]+)\.supabase\.co$", host)
    if match:
        return match.group(1)
    # Direct / pooler DSNs: postgres.<ref>.supabase.com or user postgres.<ref>
    match = re.search(r"(?:^|[./@])postgres\.([a-z0-9]+)\.", url)
    if match:
        return match.group(1)
    match = re.search(r"([a-z0-9]{20})\.supabase\.", url)
    if match:
        return match.group(1)
    return None


def production_refs() -> frozenset[str]:
    extra = env("PRODUCTION_SUPABASE_PROJECT_REFS")
    refs = set(PRODUCTION_PROJECT_REFS)
    if extra:
        refs.update(part.strip() for part in extra.split(",") if part.strip())
    return frozenset(refs)


def production_urls() -> list[str]:
    return [value for value in (
        env("SUPABASE_URL"),
        env("SUPABASE_DB_URL"),
        env("DATABASE_URL"),
    ) if value]


def dest_is_production(dest: str) -> str | None:
    """Return the matching production marker, or None if dest looks non-prod."""
    if not dest:
        return "empty destination"
    dest_ref = project_ref_from_url(dest)
    refs = production_refs()
    if dest_ref and dest_ref in refs:
        return f"project ref {dest_ref}"
    dest_host = (urlparse(dest).hostname or "").lower()
    for url in production_urls():
        if dest.rstrip("/") == url.rstrip("/"):
            return "exact match of a production URL"
        host = (urlparse(url).hostname or "").lower()
        if dest_host and host and dest_host == host:
            return f"shared host {dest_host}"
    for ref in refs:
        if ref and ref in dest:
            return f"embedded production ref {ref}"
    return None


def openssl_iter() -> int:
    raw = env("BACKUP_PBKDF2_ITER", str(OPENSSL_ITER_DEFAULT))
    try:
        value = int(raw)
    except ValueError as exc:
        raise BackupError("BACKUP_PBKDF2_ITER must be an integer") from exc
    if value < 10_000:
        raise BackupError("BACKUP_PBKDF2_ITER must be >= 10000")
    return value


def _openssl(args: list[str], data: bytes, key: str) -> bytes:
    if not shutil.which("openssl"):
        raise BackupError("openssl is required; refusing to handle plaintext")
    env_map = os.environ.copy()
    env_map["BACKUP_ENCRYPTION_KEY"] = key
    try:
        proc = subprocess.run(
            args,
            input=data,
            capture_output=True,
            check=False,
            env=env_map,
        )
    except OSError as exc:
        raise BackupError("openssl failed to start") from exc
    if proc.returncode != 0:
        raise BackupError("openssl rejected the payload (bad key or corrupt ciphertext)")
    return proc.stdout


def encrypt_payload(plaintext: bytes, key: str) -> bytes:
    if not key:
        raise BackupError("BACKUP_ENCRYPTION_KEY is required")
    if len(key) < 16:
        raise BackupError("BACKUP_ENCRYPTION_KEY must be at least 16 characters")
    args = [
        "openssl", "enc", "-aes-256-cbc", "-pbkdf2",
        "-iter", str(openssl_iter()), "-salt",
        "-pass", "env:BACKUP_ENCRYPTION_KEY",
    ]
    ciphertext = _openssl(args, plaintext, key)
    if ciphertext == plaintext:
        raise BackupError("openssl returned plaintext; refusing to store")
    return ciphertext


def decrypt_payload(ciphertext: bytes, key: str) -> bytes:
    if not key:
        raise BackupError("BACKUP_ENCRYPTION_KEY is required")
    args = [
        "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
        "-iter", str(openssl_iter()),
        "-pass", "env:BACKUP_ENCRYPTION_KEY",
    ]
    return _openssl(args, ciphertext, key)


def rows_to_jsonl(rows: Iterable[dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    for row in rows:
        buf.write(json.dumps(row, sort_keys=True, default=str).encode("utf-8"))
        buf.write(b"\n")
    return buf.getvalue()


def jsonl_to_rows(raw: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not raw:
        return rows
    for line in raw.splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def dump_table(name: str, rows: list[dict[str, Any]]) -> TableDump:
    if name not in PROTECTED_TABLES:
        raise BackupError(f"refusing to dump non-protected table {name}")
    raw = rows_to_jsonl(rows)
    return TableDump(name=name, rows=rows, sha256=sha256_bytes(raw), raw=raw)


def build_tar(
    backup_id: str,
    tables: dict[str, TableDump],
    manifest: dict[str, Any],
    extra_files: dict[str, bytes] | None = None,
) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        _add_bytes(tar, f"{backup_id}/manifest.json", manifest_bytes)
        for name in PROTECTED_TABLES:
            table = tables[name]
            _add_bytes(tar, f"{backup_id}/tables/{name}.jsonl", table.raw)
        for rel, data in (extra_files or {}).items():
            _add_bytes(tar, f"{backup_id}/{rel}", data)
    return buf.getvalue()


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = int(time.time())
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(data))


def parse_tar(plaintext: bytes) -> tuple[dict[str, Any], dict[str, TableDump]]:
    buf = io.BytesIO(plaintext)
    tables: dict[str, TableDump] = {}
    manifest: dict[str, Any] | None = None
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            data = extracted.read()
            path = Path(member.name)
            if path.name == "manifest.json":
                manifest = json.loads(data.decode("utf-8"))
            elif path.suffix == ".jsonl":
                name = path.stem
                tables[name] = TableDump(
                    name=name,
                    rows=jsonl_to_rows(data),
                    sha256=sha256_bytes(data),
                    raw=data,
                )
    if manifest is None:
        raise BackupError("backup archive has no manifest.json")
    missing = [name for name in PROTECTED_TABLES if name not in tables]
    if missing:
        raise BackupError("backup archive missing tables: " + ", ".join(missing))
    return manifest, tables


def build_manifest(
    backup_id: str,
    tables: dict[str, TableDump],
    *,
    mode: str,
    source: dict[str, Any],
    now: datetime,
    payload_sha256: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "backup_id": backup_id,
        "created_at": iso(now),
        "mode": mode,
        "tables": {
            name: {"rows": len(tables[name].rows), "sha256": tables[name].sha256}
            for name in PROTECTED_TABLES
        },
        "source": source,
        "retention_days": DEFAULT_RETENTION_DAYS,
        "rpo_declared_hours": RPO_DECLARED_HOURS,
        "rto_target_minutes": RTO_TARGET_MINUTES,
        "payload_sha256": payload_sha256,
        "encrypted": True,
        "cipher": CIPHER,
        "protected_tables": list(PROTECTED_TABLES),
    }


def fetch_via_rest(table: str, *, base_url: str, service_key: str, page_size: int = 1000) -> list[dict[str, Any]]:
    if table not in PROTECTED_TABLES:
        raise BackupError(f"refusing to fetch non-protected table {table}")
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + page_size - 1
        url = f"{base_url.rstrip('/')}/rest/v1/{table}?select=*"
        req = urllib.request.Request(
            url,
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Range": f"{start}-{end}",
                "Prefer": "count=exact",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8") or "[]")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            raise BackupError(f"PostgREST {table} failed HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise BackupError(f"PostgREST {table} unreachable") from exc
        if not isinstance(payload, list):
            raise BackupError(f"PostgREST {table} returned a non-list")
        rows.extend(payload)
        if len(payload) < page_size:
            break
        start += page_size
    return rows


def write_via_rest(
    table: str,
    rows: list[dict[str, Any]],
    *,
    base_url: str,
    service_key: str,
) -> int:
    if table not in PROTECTED_TABLES:
        raise BackupError(f"refusing to write non-protected table {table}")
    url = f"{base_url.rstrip('/')}/rest/v1/{table}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    if not rows:
        return 0
    req = urllib.request.Request(
        url,
        data=json.dumps(rows, default=str).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise BackupError(f"PostgREST write {table} failed HTTP {exc.code}: {body}") from exc
    return len(rows)


def fetch_via_psql(table: str, db_url: str) -> list[dict[str, Any]]:
    if table not in PROTECTED_TABLES:
        raise BackupError(f"refusing to fetch non-protected table {table}")
    if not shutil.which("psql"):
        raise BackupError("psql is not installed")
    sql = (
        f"SELECT COALESCE(json_agg(t), '[]'::json) "
        f"FROM public.{table} AS t"
    )
    proc = subprocess.run(
        ["psql", "-d", db_url, "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        hint = err[-1] if err else "psql failed"
        raise BackupError(f"psql {table}: {hint}")
    payload = json.loads(proc.stdout or "[]")
    if not isinstance(payload, list):
        raise BackupError(f"psql {table} returned a non-list")
    return payload


def run_pg_dump_sql(db_url: str) -> bytes:
    """Optional sibling of the JSONL payload — the GATE-1 'nightly pg_dump' bytes."""
    if not shutil.which("pg_dump"):
        raise BackupError("pg_dump is not installed")
    cmd = [
        "pg_dump",
        "--data-only",
        "--no-owner",
        "--no-acl",
        "--inserts",
        "--rows-per-insert=100",
    ]
    for name in PROTECTED_TABLES:
        cmd.extend(["-t", f"public.{name}"])
    cmd.append(db_url)
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip().splitlines()
        hint = err[-1] if err else "pg_dump failed"
        raise BackupError(f"pg_dump: {hint}")
    return proc.stdout


def pg_insert_jsonl(db_url: str, tables: dict[str, TableDump]) -> dict[str, int]:
    if not shutil.which("psql"):
        raise BackupError("psql is not installed")
    restored: dict[str, int] = {}
    for name in RESTORE_ORDER:
        rows = tables[name].rows
        if not rows:
            restored[name] = 0
            continue
        literal = json.dumps(rows, default=str).replace("'", "''")
        sql = (
            "SET session_replication_role = replica;\n"
            f"INSERT INTO public.{name} "
            f"SELECT * FROM json_populate_recordset(NULL::public.{name}, '{literal}');\n"
            "SET session_replication_role = DEFAULT;\n"
        )
        proc = subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", "-d", db_url],
            input=sql,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or "").strip().splitlines()
            hint = err[-1] if err else "psql failed"
            raise BackupError(f"psql restore {name}: {hint}")
        restored[name] = len(rows)
    return restored


def dump_via_fetcher(fetcher: TableFetcher, *, allow_missing: bool = False) -> dict[str, TableDump]:
    tables: dict[str, TableDump] = {}
    missing: list[str] = []
    for name in PROTECTED_TABLES:
        try:
            rows = fetcher(name)
        except BackupError:
            if allow_missing:
                missing.append(name)
                rows = []
            else:
                raise
        tables[name] = dump_table(name, rows)
    if missing and not allow_missing:
        raise BackupError("missing tables: " + ", ".join(missing))
    return tables


def verify_tables(expected: dict[str, Any], actual_counts: dict[str, int]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    ok = True
    for name in PROTECTED_TABLES:
        want = int(expected.get(name, {}).get("rows", 0))
        got = int(actual_counts.get(name, -1))
        match = want == got
        ok = ok and match
        report[name] = {"expected": want, "restored": got, "ok": match}
    return {"tables": report, "integrity": "pass" if ok else "fail", "ok": ok}


def make_artifact(
    tables: dict[str, TableDump],
    *,
    mode: str,
    source: dict[str, Any],
    key: str,
    now: datetime | None = None,
    extra_files: dict[str, bytes] | None = None,
) -> BackupArtifact:
    stamp = now or utcnow()
    backup_id = new_backup_id(stamp)
    skeleton = build_manifest(
        backup_id, tables, mode=mode, source=source, now=stamp, payload_sha256="",
    )
    plaintext = build_tar(backup_id, tables, skeleton, extra_files)
    skeleton["payload_sha256"] = sha256_bytes(plaintext)
    plaintext = build_tar(backup_id, tables, skeleton, extra_files)
    skeleton["payload_sha256"] = sha256_bytes(plaintext)
    ciphertext = encrypt_payload(plaintext, key)
    return BackupArtifact(
        backup_id=backup_id,
        manifest=skeleton,
        plaintext=plaintext,
        ciphertext=ciphertext,
        tables=tables,
    )


def object_keys(backup_id: str, prefix: str) -> tuple[str, str]:
    root = prefix if prefix.endswith("/") else prefix + "/"
    return f"{root}{backup_id}.tar.enc", f"{root}{backup_id}.manifest.json"


def publish_artifact(store: ObjectStore, artifact: BackupArtifact, prefix: str) -> None:
    enc_key, man_key = object_keys(artifact.backup_id, prefix)
    store.put(enc_key, artifact.ciphertext, content_type="application/octet-stream")
    sidecar = json.dumps(artifact.manifest, indent=2, sort_keys=True).encode("utf-8")
    store.put(man_key, sidecar, content_type="application/json")


def prune_expired(
    store: ObjectStore,
    prefix: str,
    *,
    now: datetime | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> list[str]:
    if retention_days < 30:
        raise BackupError("retention_days must be >= 30")
    cutoff = (now or utcnow()) - timedelta(days=retention_days)
    deleted: list[str] = []
    for item in store.list(prefix):
        if item.last_modified < cutoff:
            store.delete(item.key)
            deleted.append(item.key)
    return deleted


def load_artifact(store: ObjectStore, backup_id: str, prefix: str, key: str) -> BackupArtifact:
    enc_key, man_key = object_keys(backup_id, prefix)
    ciphertext = store.get(enc_key)
    sidecar = json.loads(store.get(man_key).decode("utf-8"))
    plaintext = decrypt_payload(ciphertext, key)
    if sha256_bytes(plaintext) != sidecar.get("payload_sha256"):
        raise BackupError("payload sha256 mismatch after decrypt")
    manifest, tables = parse_tar(plaintext)
    return BackupArtifact(
        backup_id=backup_id,
        manifest=manifest,
        plaintext=plaintext,
        ciphertext=ciphertext,
        tables=tables,
    )


def restore_via_writer(
    tables: dict[str, TableDump],
    writer: TableWriter,
) -> dict[str, int]:
    restored: dict[str, int] = {}
    for name in RESTORE_ORDER:
        restored[name] = writer(name, tables[name].rows)
    return restored


def build_receipt(
    *,
    backup_id: str,
    dest: str,
    started: datetime,
    ended: datetime,
    source_as_of: datetime | None,
    verification: dict[str, Any],
    commands: list[str],
    environment: str,
) -> dict[str, Any]:
    rpo_seconds = None
    if source_as_of is not None:
        rpo_seconds = max(0, int((started - source_as_of).total_seconds()))
    return {
        "schema": RECEIPT_SCHEMA,
        "backup_id": backup_id,
        "dest": redact_url(dest),
        "environment": environment,
        "started_at": iso(started),
        "ended_at": iso(ended),
        "rto_seconds": max(0, int((ended - started).total_seconds())),
        "rpo_seconds": rpo_seconds,
        "rpo_declared_hours": RPO_DECLARED_HOURS,
        "rto_target_minutes": RTO_TARGET_MINUTES,
        "commands": commands,
        "verification": verification,
        "gate1_scratch_supabase": environment == "scratch-supabase",
    }


def resolve_mode(explicit: str) -> str:
    if explicit in {"pg_dump", "rest", "memory"}:
        return explicit
    if env("SUPABASE_DB_URL") or env("DATABASE_URL"):
        return "pg_dump"
    if env("SUPABASE_URL") and (env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_SERVICE_KEY")):
        return "rest"
    raise BackupError(
        "no dump source: set SUPABASE_DB_URL (preferred) or "
        "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY"
    )


def r2_store_from_env() -> R2Store:
    endpoint = env("BACKUP_R2_ENDPOINT") or env("R2_ENDPOINT")
    access = env("BACKUP_R2_ACCESS_KEY_ID") or env("R2_ACCESS_KEY_ID")
    secret = env("BACKUP_R2_SECRET_ACCESS_KEY") or env("R2_SECRET_ACCESS_KEY")
    bucket = env("BACKUP_R2_BUCKET") or env("R2_BUCKET")
    if not (endpoint and access and secret and bucket):
        raise BackupError(
            "R2 destination is required (BACKUP_R2_* or R2_ENDPOINT / "
            "R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET), or pass --local-dir"
        )
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise BackupError("boto3 is required for R2 upload") from exc
    cfg = Config(
        region_name="auto",
        signature_version="s3v4",
        retries={"max_attempts": 8, "mode": "standard"},
        connect_timeout=15,
        read_timeout=60,
    )
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        config=cfg,
    )
    return R2Store(client, bucket)


def store_from_args(args: argparse.Namespace) -> ObjectStore:
    if args.local_dir:
        return LocalDirStore(Path(args.local_dir))
    return r2_store_from_env()


def source_info(mode: str) -> dict[str, Any]:
    url = env("SUPABASE_URL") or env("SUPABASE_DB_URL") or env("DATABASE_URL")
    return {
        "mode": mode,
        "project_ref": project_ref_from_url(url),
        "as_of": iso(utcnow()),
        "url": redact_url(url),
    }


def cmd_dump(args: argparse.Namespace) -> int:
    key = env("BACKUP_ENCRYPTION_KEY")
    if not key:
        raise BackupError("BACKUP_ENCRYPTION_KEY is required")
    mode = resolve_mode(args.mode)
    extra_files: dict[str, bytes] = {}
    if mode == "pg_dump":
        db_url = env("SUPABASE_DB_URL") or env("DATABASE_URL")
        if not db_url:
            raise BackupError("SUPABASE_DB_URL or DATABASE_URL is required for --mode pg_dump")

        def fetcher(name: str) -> list[dict[str, Any]]:
            return fetch_via_psql(name, db_url)

        tables = dump_via_fetcher(fetcher, allow_missing=args.allow_missing)
        if shutil.which("pg_dump"):
            extra_files["pg_dump.sql"] = run_pg_dump_sql(db_url)
    elif mode == "rest":
        base = require_env("SUPABASE_URL")
        service = env("SUPABASE_SERVICE_ROLE_KEY") or require_env("SUPABASE_SERVICE_KEY")

        def fetcher(name: str) -> list[dict[str, Any]]:
            return fetch_via_rest(name, base_url=base, service_key=service)

        tables = dump_via_fetcher(fetcher, allow_missing=args.allow_missing)
    else:
        raise BackupError(f"unsupported dump mode {mode}")
    artifact = make_artifact(
        tables, mode=mode, source=source_info(mode), key=key, extra_files=extra_files,
    )
    store = store_from_args(args)
    publish_artifact(store, artifact, args.prefix)
    deleted = prune_expired(store, args.prefix, retention_days=args.retention_days)
    print(json.dumps({
        "ok": True,
        "backup_id": artifact.backup_id,
        "mode": mode,
        "tables": {name: artifact.manifest["tables"][name]["rows"] for name in PROTECTED_TABLES},
        "enc_key": object_keys(artifact.backup_id, args.prefix)[0],
        "pruned": deleted,
        "rpo_declared_hours": RPO_DECLARED_HOURS,
        "rto_target_minutes": RTO_TARGET_MINUTES,
    }, indent=2, sort_keys=True))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = store_from_args(args)
    items = [item for item in store.list(args.prefix) if item.key.endswith(".manifest.json")]
    rows = []
    for item in items:
        try:
            manifest = json.loads(store.get(item.key).decode("utf-8"))
        except BackupError:
            continue
        rows.append({
            "backup_id": manifest.get("backup_id"),
            "created_at": manifest.get("created_at"),
            "mode": manifest.get("mode"),
            "key": item.key,
        })
    print(json.dumps({"ok": True, "backups": rows}, indent=2, sort_keys=True))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    key = require_env("BACKUP_ENCRYPTION_KEY")
    store = store_from_args(args)
    artifact = load_artifact(store, args.backup_id, args.prefix, key)
    counts = {name: len(artifact.tables[name].rows) for name in PROTECTED_TABLES}
    report = verify_tables(artifact.manifest["tables"], counts)
    print(json.dumps({
        "ok": report["ok"],
        "backup_id": artifact.backup_id,
        "verification": report,
    }, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def _parse_as_of(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def cmd_restore(args: argparse.Namespace) -> int:
    if not args.i_am_restoring_into_scratch:
        raise BackupError(
            "restore refused: pass --i-am-restoring-into-scratch "
            "(production restore is forbidden)"
        )
    dest = args.dest_db_url or args.dest_supabase_url
    if not dest:
        raise BackupError("restore requires --dest-db-url or --dest-supabase-url")
    reason = dest_is_production(dest)
    if reason:
        raise BackupError(f"restore refused: destination matches production ({reason})")
    key = require_env("BACKUP_ENCRYPTION_KEY")
    store = store_from_args(args)
    started = utcnow()
    artifact = load_artifact(store, args.backup_id, args.prefix, key)
    mode = artifact.manifest.get("mode") or "rest"
    if args.dest_db_url:
        actual = pg_insert_jsonl(args.dest_db_url, artifact.tables)
        dest_used = args.dest_db_url
        environment = "scratch-postgres"
    else:
        service = env("SUPABASE_SCRATCH_SERVICE_ROLE_KEY") or env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_SERVICE_KEY")
        if not service:
            raise BackupError("scratch restore via REST needs SUPABASE_SCRATCH_SERVICE_ROLE_KEY")

        def writer(name: str, rows: list[dict[str, Any]]) -> int:
            return write_via_rest(
                name, rows, base_url=args.dest_supabase_url, service_key=service,
            )

        actual = restore_via_writer(artifact.tables, writer)
        dest_used = args.dest_supabase_url
        environment = "scratch-supabase"
    ended = utcnow()
    report = verify_tables(artifact.manifest["tables"], actual)
    commands = [
        f"python -m scripts.backup_user_tables restore --backup-id {args.backup_id} "
        f"--i-am-restoring-into-scratch "
        + ("--dest-db-url \"$SCRATCH_DB_URL\"" if args.dest_db_url else "--dest-supabase-url \"$SCRATCH_SUPABASE_URL\""),
    ]
    receipt = build_receipt(
        backup_id=artifact.backup_id,
        dest=dest_used,
        started=started,
        ended=ended,
        source_as_of=_parse_as_of((artifact.manifest.get("source") or {}).get("as_of")),
        verification=report,
        commands=commands,
        environment=environment,
    )
    if args.write_receipt:
        path = Path(args.write_receipt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--local-dir", help="Read/write backups on a local directory instead of R2")
    shared.add_argument("--prefix", default=env("BACKUP_R2_PREFIX", DEFAULT_PREFIX))
    shared.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    shared.add_argument("--mode", choices=("auto", "pg_dump", "rest"), default="auto")
    shared.add_argument("--allow-missing", action="store_true", help="Dump empty JSONL for missing REST tables")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("dump", parents=[shared], help="Create an encrypted backup and publish it")
    sub.add_parser("list", parents=[shared], help="List published backup manifests")

    verify = sub.add_parser("verify", parents=[shared], help="Decrypt a backup and check table hashes/counts")
    verify.add_argument("--backup-id", required=True)

    restore = sub.add_parser("restore", parents=[shared], help="Restore into a scratch destination (never production)")
    restore.add_argument("--backup-id", required=True)
    restore.add_argument("--dest-db-url", help="Scratch Postgres DSN for pg_restore/psql")
    restore.add_argument("--dest-supabase-url", help="Scratch Supabase API URL for REST restore")
    restore.add_argument(
        "--i-am-restoring-into-scratch",
        action="store_true",
        help="Required acknowledgement. Production destinations are still refused.",
    )
    restore.add_argument("--write-receipt", help="Write the restore receipt JSON to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.retention_days < 30:
        print("retention-days must be >= 30", file=sys.stderr)
        return EXIT_USAGE
    try:
        if args.command == "dump":
            return cmd_dump(args)
        if args.command == "list":
            return cmd_list(args)
        if args.command == "verify":
            return cmd_verify(args)
        if args.command == "restore":
            return cmd_restore(args)
    except BackupError as exc:
        print(f"backup_user_tables: {exc}", file=sys.stderr)
        return EXIT_USAGE
    parser.error(f"unknown command {args.command}")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
