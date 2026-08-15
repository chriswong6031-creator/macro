#!/usr/bin/env python3
"""Nightly logical dump of customer / billing tables to private encrypted R2.

MMX-001 / GATE-1. This is the repo-side recovery path: dump nine protected
tables, encrypt them, ship them to a non-public R2 prefix, keep >=30 days,
and restore ONLY into a scratch target.

Fail-closed: missing encryption key, missing source, or a refused production
restore target exits 2. A backup job that cannot run must be red, not silent.

Never restores into the production Supabase project
(``fsldfzlxyavsuwqbceod``). The restore command requires
``--i-am-restoring-into-scratch``.

Usage::

    python -m scripts.backup_user_tables backup \\
        --source-dir /tmp/src --output-dir /tmp/dump --encryption-key "$KEY"

    python -m scripts.backup_user_tables restore \\
        --input-dir /tmp/dump --target-dir /tmp/dst \\
        --encryption-key "$KEY" --i-am-restoring-into-scratch

    python -m scripts.backup_user_tables verify --input-dir /tmp/dump --target-dir /tmp/dst
    python -m scripts.backup_user_tables prune --output-dir /tmp/store --retention-days 30
    python -m scripts.backup_user_tables list --output-dir /tmp/store
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

log = logging.getLogger("backup_user_tables")

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

# Children after parents so a scratch restore can upsert in FK-safe order.
RESTORE_ORDER: tuple[str, ...] = (
    "profiles",
    "user_entitlements",
    "stripe_events",
    "watchlists",
    "watchlist_symbols",
    "chart_layouts",
    "saved_scripts",
    "alerts",
    "favorites",
)

PRODUCTION_PROJECT_REFS: frozenset[str] = frozenset({"fsldfzlxyavsuwqbceod"})
DEFAULT_R2_PREFIX = "backups/user-tables"
DEFAULT_RETENTION_DAYS = 30
MIN_RETENTION_DAYS = 30
MIN_KEY_CHARS = 16
PAGE_SIZE = 1000
MAGIC = b"MMUB1\n"
NONCE_LEN = 16
HMAC_LEN = 32
EXIT_REFUSED = 2

Row = dict[str, Any]
WriteTable = Callable[[str, list[Row]], int]


class BackupError(RuntimeError):
    """Operator-visible failure; exit 2."""


class ProductionRestoreRefused(BackupError):
    """Restore targeted the live project. Never proceed."""


@dataclass
class TableArtifact:
    name: str
    rows: int
    sha256: str
    bytes: int
    filename: str


@dataclass
class BackupManifest:
    backup_id: str
    created_at: str
    format: str
    tables: list[TableArtifact]
    source: str
    source_project_ref: str | None
    rpo_seconds: int
    retention_days: int
    encrypted: bool
    encryption: str
    notes: list[str] = field(default_factory=list)

    def table_map(self) -> dict[str, TableArtifact]:
        return {item.name: item for item in self.tables}


@dataclass
class RestoreReceipt:
    backup_id: str
    started_at: str
    ended_at: str
    rto_seconds: float
    rpo_seconds: int
    source: str
    target: str
    tables: dict[str, dict[str, int | str | bool]]
    integrity_ok: bool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_backup_id(ts: datetime | None = None) -> str:
    stamp = (ts or utcnow()).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"user-tables-{stamp}"


def project_ref_from_url(url: str) -> str | None:
    text = (url or "").strip().lower()
    if not text:
        return None
    for ref in PRODUCTION_PROJECT_REFS:
        if ref in text:
            return ref
    marker = "https://"
    if "supabase.co" in text and marker in text:
        host = text.split("://", 1)[1].split("/", 1)[0]
        prefix = host.split(".", 1)[0]
        return prefix or None
    return None


def forbid_production_target(target: str) -> None:
    """Refuse any restore whose target names the live project."""
    blob = (target or "").strip().lower()
    if not blob:
        raise BackupError("restore target is empty")
    for ref in PRODUCTION_PROJECT_REFS:
        if ref in blob:
            raise ProductionRestoreRefused(
                f"refusing restore into production Supabase project {ref}"
            )


def derive_key(passphrase: str) -> bytes:
    secret = (passphrase or "").strip()
    if len(secret) < MIN_KEY_CHARS:
        raise BackupError(
            f"BACKUP_ENCRYPTION_KEY must be at least {MIN_KEY_CHARS} characters"
        )
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _keystream(key: bytes, nonce: bytes, n: int) -> bytes:
    """SHA-256 counter mode. Stdlib-only so the VPS and CI need no extra wheel."""
    out = bytearray()
    counter = 0
    while len(out) < n:
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:n])


def encrypt_bytes(plaintext: bytes, key: bytes) -> bytes:
    nonce = os.urandom(NONCE_LEN)
    stream = _keystream(key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream, strict=True))
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return MAGIC + nonce + tag + ciphertext


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise BackupError("ciphertext is missing the MMUB1 header")
    body = blob[len(MAGIC) :]
    nonce = body[:NONCE_LEN]
    tag = body[NONCE_LEN : NONCE_LEN + HMAC_LEN]
    ciphertext = body[NONCE_LEN + HMAC_LEN :]
    if len(nonce) != NONCE_LEN or len(tag) != HMAC_LEN:
        raise BackupError("ciphertext is truncated")
    expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise BackupError("decrypt failed — wrong key or corrupt blob")
    stream = _keystream(key, nonce, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream, strict=True))


def canonical_jsonl(rows: Iterable[Row]) -> bytes:
    lines = [
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for row in rows
    ]
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


def parse_jsonl(blob: bytes) -> list[Row]:
    rows: list[Row] = []
    if not blob:
        return rows
    for line in blob.decode("utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_table_dir(source_dir: Path, table: str) -> list[Row]:
    path = source_dir / f"{table}.json"
    if not path.is_file():
        alt = source_dir / f"{table}.jsonl"
        if not alt.is_file():
            raise BackupError(f"source table missing: {path}")
        return parse_jsonl(alt.read_bytes())
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return payload["rows"]
    raise BackupError(f"{path} is not a JSON list or {{rows: [...]}} object")


def write_table_dir(target_dir: Path, table: str, rows: list[Row]) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{table}.json"
    path.write_text(
        json.dumps(rows, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return len(rows)


def dump_tables(
    tables: Iterable[str],
    reader: Callable[[str], list[Row]],
    *,
    allow_missing: bool = False,
) -> dict[str, list[Row]]:
    out: dict[str, list[Row]] = {}
    missing: list[str] = []
    for table in tables:
        try:
            rows = reader(table)
        except BackupError as exc:
            if allow_missing and "missing" in str(exc):
                missing.append(table)
                out[table] = []
                continue
            raise
        if not isinstance(rows, list):
            raise BackupError(f"{table}: reader returned {type(rows).__name__}, not list")
        out[table] = rows
    if missing:
        log.warning("missing tables dumped as empty: %s", ", ".join(missing))
    expected = list(tables)
    if sorted(out) != sorted(expected):
        raise BackupError(
            "dump is incomplete: "
            f"have {sorted(out)} expected {sorted(expected)}"
        )
    return out


def write_encrypted_backup(
    output_dir: Path,
    dumps: dict[str, list[Row]],
    *,
    key: bytes,
    backup_id: str,
    source: str,
    source_project_ref: str | None,
    retention_days: int,
    created_at: datetime | None = None,
) -> BackupManifest:
    created = created_at or utcnow()
    dest = output_dir / backup_id
    dest.mkdir(parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    artifacts: list[TableArtifact] = []
    for table in PROTECTED_TABLES:
        rows = dumps[table]
        plaintext = canonical_jsonl(rows)
        blob = encrypt_bytes(plaintext, key)
        filename = f"{table}.jsonl.aes"
        path = dest / filename
        path.write_bytes(blob)
        os.chmod(path, 0o600)
        artifacts.append(
            TableArtifact(
                name=table,
                rows=len(rows),
                sha256=sha256_hex(plaintext),
                bytes=len(blob),
                filename=filename,
            )
        )
    manifest = BackupManifest(
        backup_id=backup_id,
        created_at=isoformat(created),
        format="jsonl-aesgcm-v1",
        tables=artifacts,
        source=source,
        source_project_ref=source_project_ref,
        rpo_seconds=24 * 60 * 60,
        retention_days=retention_days,
        encrypted=True,
        encryption="MMUB1 HMAC-SHA256 + SHA-256-CTR; private R2 prefix; optional SSE-C",
        notes=[
            "Logical dump of protected customer/billing tables.",
            "auth.users is NOT in this dump — scratch restores need matching user UUIDs "
            "or a dashboard-level project restore that includes Auth.",
        ],
    )
    manifest_path = dest / "manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest_to_json(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(manifest_path, 0o600)
    return manifest


def _manifest_to_json(manifest: BackupManifest) -> dict[str, Any]:
    payload = asdict(manifest)
    return payload


def read_manifest(input_dir: Path) -> BackupManifest:
    path = _resolve_manifest_path(input_dir)
    raw = json.loads(path.read_text(encoding="utf-8"))
    tables = [TableArtifact(**item) for item in raw["tables"]]
    return BackupManifest(
        backup_id=raw["backup_id"],
        created_at=raw["created_at"],
        format=raw["format"],
        tables=tables,
        source=raw.get("source", ""),
        source_project_ref=raw.get("source_project_ref"),
        rpo_seconds=int(raw.get("rpo_seconds", 24 * 60 * 60)),
        retention_days=int(raw.get("retention_days", DEFAULT_RETENTION_DAYS)),
        encrypted=bool(raw.get("encrypted", True)),
        encryption=raw.get("encryption", ""),
        notes=list(raw.get("notes") or []),
    )


def _resolve_manifest_path(input_dir: Path) -> Path:
    direct = input_dir / "manifest.json"
    if direct.is_file():
        return direct
    nested = list(input_dir.glob("*/manifest.json"))
    if len(nested) == 1:
        return nested[0]
    if input_dir.is_dir():
        for child in sorted(input_dir.iterdir()):
            cand = child / "manifest.json"
            if cand.is_file():
                return cand
    raise BackupError(f"manifest.json not found under {input_dir}")


def load_encrypted_backup(input_dir: Path, key: bytes) -> tuple[BackupManifest, dict[str, list[Row]]]:
    manifest = read_manifest(input_dir)
    root = _resolve_manifest_path(input_dir).parent
    dumps: dict[str, list[Row]] = {}
    for artifact in manifest.tables:
        blob = (root / artifact.filename).read_bytes()
        plaintext = decrypt_bytes(blob, key)
        if sha256_hex(plaintext) != artifact.sha256:
            raise BackupError(f"{artifact.name}: sha256 mismatch after decrypt")
        rows = parse_jsonl(plaintext)
        if len(rows) != artifact.rows:
            raise BackupError(
                f"{artifact.name}: row count {len(rows)} != manifest {artifact.rows}"
            )
        dumps[artifact.name] = rows
    missing = [name for name in PROTECTED_TABLES if name not in dumps]
    if missing:
        raise BackupError("backup is missing tables: " + ", ".join(missing))
    return manifest, dumps


def restore_tables(
    dumps: dict[str, list[Row]],
    writer: WriteTable,
    *,
    target: str,
    scratch_confirmed: bool,
) -> dict[str, int]:
    if not scratch_confirmed:
        raise BackupError("restore refused: pass --i-am-restoring-into-scratch")
    forbid_production_target(target)
    written: dict[str, int] = {}
    for table in RESTORE_ORDER:
        written[table] = writer(table, dumps[table])
    return written


def verify_restore(
    dumps: dict[str, list[Row]],
    restored: dict[str, list[Row]],
) -> dict[str, dict[str, int | str | bool]]:
    report: dict[str, dict[str, int | str | bool]] = {}
    for table in PROTECTED_TABLES:
        src = canonical_jsonl(dumps[table])
        dst = canonical_jsonl(restored[table])
        ok = src == dst
        report[table] = {
            "source_rows": len(dumps[table]),
            "restored_rows": len(restored[table]),
            "source_sha256": sha256_hex(src),
            "restored_sha256": sha256_hex(dst),
            "ok": ok,
        }
    return report


def prune_backup_ids(
    backup_ids: Iterable[str],
    *,
    now: datetime,
    retention_days: int,
) -> list[str]:
    if retention_days < MIN_RETENTION_DAYS:
        raise BackupError(f"retention_days must be >= {MIN_RETENTION_DAYS}")
    cutoff = now.astimezone(timezone.utc) - timedelta(days=retention_days)
    expired: list[str] = []
    for backup_id in backup_ids:
        ts = _parse_backup_id_time(backup_id)
        if ts is not None and ts < cutoff:
            expired.append(backup_id)
    return expired


def _parse_backup_id_time(backup_id: str) -> datetime | None:
    stamp = backup_id.rsplit("-", 1)[-1]
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def list_local_backup_ids(store_dir: Path) -> list[str]:
    if not store_dir.is_dir():
        return []
    ids: list[str] = []
    for child in store_dir.iterdir():
        if child.is_dir() and (child / "manifest.json").is_file():
            ids.append(child.name)
    return sorted(ids)


# ---------------------------------------------------------------------------
# PostgREST source (production VPS path)
# ---------------------------------------------------------------------------
def _service_key() -> str:
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    )
    if not key:
        raise BackupError("SUPABASE_SERVICE_ROLE_KEY is not set")
    return key


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if not url:
        raise BackupError("SUPABASE_URL is not set")
    return url


def fetch_table_postgrest(table: str, *, page_size: int = PAGE_SIZE) -> list[Row]:
    base = _supabase_url()
    key = _service_key()
    url = f"{base}/rest/v1/{table}?select=*"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Prefer": "count=exact",
    }
    rows: list[Row] = []
    start = 0
    while True:
        req_headers = dict(headers)
        req_headers["Range"] = f"{start}-{start + page_size - 1}"
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                content_range = resp.headers.get("Content-Range", "")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            raise BackupError(f"PostgREST {table} HTTP {exc.code}: {body}") from exc
        if not isinstance(payload, list):
            raise BackupError(f"PostgREST {table} returned {type(payload).__name__}")
        rows.extend(payload)
        if len(payload) < page_size:
            break
        start += page_size
        total = _content_range_total(content_range)
        if total is not None and start >= total:
            break
    return rows


def _content_range_total(header: str) -> int | None:
    if "/" not in header:
        return None
    tail = header.rsplit("/", 1)[-1].strip()
    if tail == "*":
        return None
    try:
        return int(tail)
    except ValueError:
        return None


def write_table_postgrest(table: str, rows: list[Row], *, target_url: str) -> int:
    key = _service_key()
    url = f"{target_url.rstrip('/')}/rest/v1/{table}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    if not rows:
        return 0
    # PostgREST accepts a JSON array upsert.
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:400]
        raise BackupError(f"PostgREST upsert {table} HTTP {exc.code}: {err}") from exc
    return len(rows)


# ---------------------------------------------------------------------------
# R2 (optional; local --output-dir drills do not need it)
# ---------------------------------------------------------------------------
def _r2_client():
    endpoint = os.environ.get("R2_ENDPOINT", "").strip()
    access = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    if not (endpoint and access and secret):
        return None
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise BackupError("boto3 is required to talk to R2") from exc
    kw = dict(
        region_name="auto",
        signature_version="s3v4",
        retries={"max_attempts": 8, "mode": "standard"},
        connect_timeout=15,
        read_timeout=60,
    )
    try:
        cfg = Config(
            **kw,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        )
    except TypeError:
        cfg = Config(**kw)
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        config=cfg,
    )


def upload_backup_dir(local_dir: Path, *, prefix: str, sse_key: bytes | None) -> list[str]:
    client = _r2_client()
    bucket = os.environ.get("R2_BUCKET", "").strip()
    if client is None or not bucket:
        raise BackupError("R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET required")
    uploaded: list[str] = []
    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        key = f"{prefix.rstrip('/')}/{local_dir.name}/{path.name}"
        extra: dict[str, Any] = {"ACL": "private"}
        if sse_key is not None:
            extra.update(
                {
                    "SSECustomerAlgorithm": "AES256",
                    "SSECustomerKey": sse_key,
                }
            )
        client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes(), **extra)
        uploaded.append(key)
    return uploaded


def prune_r2_prefix(*, prefix: str, retention_days: int, now: datetime | None = None) -> list[str]:
    client = _r2_client()
    bucket = os.environ.get("R2_BUCKET", "").strip()
    if client is None or not bucket:
        raise BackupError("R2 credentials required for prune")
    now = now or utcnow()
    cutoff = now - timedelta(days=retention_days)
    expired: list[str] = []
    token = None
    while True:
        kw: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix.rstrip("/") + "/"}
        if token:
            kw["ContinuationToken"] = token
        resp = client.list_objects_v2(**kw)
        for obj in resp.get("Contents") or []:
            modified = obj["LastModified"]
            if modified.tzinfo is None:
                modified = modified.replace(tzinfo=timezone.utc)
            if modified < cutoff:
                client.delete_object(Bucket=bucket, Key=obj["Key"])
                expired.append(obj["Key"])
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return expired


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _require_encryption_key(args: argparse.Namespace) -> str:
    key = (args.encryption_key or os.environ.get("BACKUP_ENCRYPTION_KEY", "")).strip()
    if not key:
        raise BackupError("BACKUP_ENCRYPTION_KEY / --encryption-key is required")
    return key


def cmd_backup(args: argparse.Namespace) -> int:
    key = derive_key(_require_encryption_key(args))
    retention = int(args.retention_days)
    if retention < MIN_RETENTION_DAYS:
        raise BackupError(f"--retention-days must be >= {MIN_RETENTION_DAYS}")
    backup_id = args.backup_id or make_backup_id()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)

    if args.source_dir:
        source_dir = Path(args.source_dir)
        source = f"file:{source_dir}"
        source_ref = None
        dumps = dump_tables(
            PROTECTED_TABLES,
            lambda table: load_table_dir(source_dir, table),
            allow_missing=args.allow_missing_tables,
        )
    else:
        source = _supabase_url()
        source_ref = project_ref_from_url(source)
        dumps = dump_tables(
            PROTECTED_TABLES,
            fetch_table_postgrest,
            allow_missing=args.allow_missing_tables,
        )

    manifest = write_encrypted_backup(
        output_dir,
        dumps,
        key=key,
        backup_id=backup_id,
        source=source,
        source_project_ref=source_ref,
        retention_days=retention,
    )
    log.info(
        "wrote %s (%s tables, %s rows)",
        backup_id,
        len(manifest.tables),
        sum(item.rows for item in manifest.tables),
    )

    if args.upload_r2:
        prefix = args.r2_prefix or os.environ.get("BACKUP_R2_PREFIX", DEFAULT_R2_PREFIX)
        uploaded = upload_backup_dir(
            output_dir / backup_id,
            prefix=prefix,
            sse_key=key if args.r2_sse_c else None,
        )
        log.info("uploaded %d objects under %s/%s", len(uploaded), prefix, backup_id)
        if args.prune:
            deleted = prune_r2_prefix(prefix=prefix, retention_days=retention)
            log.info("pruned %d expired R2 objects", len(deleted))
    elif args.prune:
        expired = prune_backup_ids(
            list_local_backup_ids(output_dir),
            now=utcnow(),
            retention_days=retention,
        )
        for backup in expired:
            _rmtree(output_dir / backup)
        log.info("pruned %d expired local backups", len(expired))
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    started = utcnow()
    key = derive_key(_require_encryption_key(args))
    input_dir = Path(args.input_dir)
    manifest, dumps = load_encrypted_backup(input_dir, key)

    if args.target_dir:
        target = f"file:{Path(args.target_dir)}"
        forbid_production_target(str(args.target_dir))
        target_dir = Path(args.target_dir)
        written = restore_tables(
            dumps,
            lambda table, rows: write_table_dir(target_dir, table, rows),
            target=target,
            scratch_confirmed=args.i_am_restoring_into_scratch,
        )
        restored = {table: load_table_dir(target_dir, table) for table in PROTECTED_TABLES}
    else:
        target = (args.target_url or "").strip()
        if not target:
            raise BackupError("restore requires --target-dir or --target-url")
        written = restore_tables(
            dumps,
            lambda table, rows: write_table_postgrest(table, rows, target_url=target),
            target=target,
            scratch_confirmed=args.i_am_restoring_into_scratch,
        )
        restored = dumps  # remote verify is a separate operator step

    ended = utcnow()
    report = verify_restore(dumps, restored) if args.target_dir else {
        table: {
            "source_rows": len(dumps[table]),
            "restored_rows": written[table],
            "source_sha256": sha256_hex(canonical_jsonl(dumps[table])),
            "restored_sha256": "",
            "ok": written[table] == len(dumps[table]),
        }
        for table in PROTECTED_TABLES
    }
    integrity_ok = all(bool(item["ok"]) for item in report.values())
    receipt = RestoreReceipt(
        backup_id=manifest.backup_id,
        started_at=isoformat(started),
        ended_at=isoformat(ended),
        rto_seconds=round((ended - started).total_seconds(), 3),
        rpo_seconds=manifest.rpo_seconds,
        source=str(input_dir),
        target=target,
        tables=report,
        integrity_ok=integrity_ok,
    )
    text = json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n"
    if args.receipt:
        Path(args.receipt).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    if not integrity_ok:
        raise BackupError("restore integrity check failed")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    key = derive_key(_require_encryption_key(args))
    manifest, dumps = load_encrypted_backup(Path(args.input_dir), key)
    if args.target_dir:
        restored = {
            table: load_table_dir(Path(args.target_dir), table)
            for table in PROTECTED_TABLES
        }
        report = verify_restore(dumps, restored)
        ok = all(bool(item["ok"]) for item in report.values())
        sys.stdout.write(json.dumps({"backup_id": manifest.backup_id, "tables": report, "ok": ok}, indent=2) + "\n")
        if not ok:
            raise BackupError("verify failed")
        return 0
    sys.stdout.write(
        json.dumps(
            {
                "backup_id": manifest.backup_id,
                "tables": {item.name: {"rows": item.rows, "sha256": item.sha256} for item in manifest.tables},
                "ok": True,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    ids = list_local_backup_ids(Path(args.output_dir))
    sys.stdout.write(json.dumps({"backups": ids}, indent=2) + "\n")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    retention = int(args.retention_days)
    if args.upload_r2:
        prefix = args.r2_prefix or os.environ.get("BACKUP_R2_PREFIX", DEFAULT_R2_PREFIX)
        deleted = prune_r2_prefix(prefix=prefix, retention_days=retention)
        sys.stdout.write(json.dumps({"deleted": deleted}, indent=2) + "\n")
        return 0
    store = Path(args.output_dir)
    expired = prune_backup_ids(
        list_local_backup_ids(store),
        now=utcnow(),
        retention_days=retention,
    )
    for backup_id in expired:
        _rmtree(store / backup_id)
    sys.stdout.write(json.dumps({"deleted": expired}, indent=2) + "\n")
    return 0


def _rmtree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    if path.is_dir():
        path.rmdir()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encryption-key", default="", help="overrides BACKUP_ENCRYPTION_KEY")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--r2-prefix", default="")
    parser.add_argument("--upload-r2", action="store_true")
    parser.add_argument("--r2-sse-c", action="store_true", help="also apply R2 SSE-C with the derived key")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--allow-missing-tables", action="store_true")
    parser.add_argument("--backup-id", default="")
    parser.add_argument("--output-dir", default=os.environ.get("USER_BACKUP_DIR", "/var/lib/macro-user-backup"))
    parser.add_argument("--source-dir", default="")
    parser.add_argument("--input-dir", default="")
    parser.add_argument("--target-dir", default="")
    parser.add_argument("--target-url", default="")
    parser.add_argument("--receipt", default="")
    parser.add_argument(
        "--i-am-restoring-into-scratch",
        action="store_true",
        help="required for restore; production project refs are still refused",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="backup",
        choices=("backup", "restore", "verify", "list", "prune"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "backup":
            return cmd_backup(args)
        if args.command == "restore":
            if not args.input_dir:
                raise BackupError("restore requires --input-dir")
            return cmd_restore(args)
        if args.command == "verify":
            if not args.input_dir:
                raise BackupError("verify requires --input-dir")
            return cmd_verify(args)
        if args.command == "list":
            return cmd_list(args)
        if args.command == "prune":
            return cmd_prune(args)
        raise BackupError(f"unknown command {args.command}")
    except ProductionRestoreRefused as exc:
        log.error("%s", exc)
        return EXIT_REFUSED
    except BackupError as exc:
        log.error("%s", exc)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
