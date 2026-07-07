"""Publish oracle rotation panels (panel_s.parquet + panel_m.parquet) to R2.

PR-C1 — B0 sponsorship publish path (RUL-7).

These panels are built off the nightly render path on the Mac (via
scripts/build_oracle_panel.py or scripts/oracle_nightly.py).  They are
gitignored (data/oracle/*.parquet) and must be published to R2 so the CI
nightly runner can download them before build_bottom_sensors runs.

Key layout:  data/oracle/panel_s.parquet  →  R2 key  oracle/panel_s.parquet
             data/oracle/panel_m.parquet  →  R2 key  oracle/panel_m.parquet
             data/oracle/manifest.json    →  R2 key  oracle/manifest.json
             (optional — uploaded when present)

Design mirrors scripts/publish_r2.py exactly:
  - No-op (exit 0) when R2_* creds are absent — safe to call from any lane.
  - Reads: R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
  - Content-hash skip: compares local MD5 to R2 ETag; unchanged files are not
    re-uploaded.
  - Named single-writer: only the Mac-side oracle ops lane invokes this.

Usage
-----
  python -m scripts.publish_oracle_panels [--data-dir PATH] [--dry-run]

  --data-dir PATH   override for the data directory (default: config.data_dir())
  --dry-run         report delta, upload nothing
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("publish_oracle_panels")

# Files to publish, relative to data/oracle/
_ORACLE_FILES = [
    "panel_s.parquet",
    "panel_m.parquet",
    "manifest.json",  # optional — skipped if absent
]

# R2 key prefix for oracle data
_R2_PREFIX = "oracle"

_CT = {
    ".parquet": "application/octet-stream",
    ".json": "application/json",
}


def _client():
    """S3 client for R2, or None when creds are absent (graceful no-op).
    Mirrors the _client() function in scripts/publish_r2.py exactly.
    """
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config
        kw = dict(region_name="auto", signature_version="s3v4",
                  max_pool_connections=8, retries={"max_attempts": 4, "mode": "standard"})
        try:  # newer botocore: keep R2 happy (it rejects the default CRC32 trailer)
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                            aws_secret_access_key=sk, config=cfg)
    except ImportError:
        log.warning("boto3 not installed — cannot publish oracle panels")
        return None


def _md5(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _remote_etag(s3, bucket: str, key: str) -> str | None:
    """Return the ETag (MD5) of an existing R2 object, or None if absent."""
    try:
        r = s3.head_object(Bucket=bucket, Key=key)
        return r.get("ETag", "").strip('"')
    except Exception:  # noqa: BLE001 — NoSuchKey, auth errors, etc.
        return None


def publish(data_dir: Path | None = None, dry_run: bool = False) -> int:
    """Upload oracle panels to R2.  Returns 0 on success, 1 on error."""
    s3 = _client()
    if s3 is None:
        log.info("no R2 creds (R2_ENDPOINT/ACCESS_KEY_ID/SECRET_ACCESS_KEY) — skip")
        return 0

    bucket = os.environ.get("R2_BUCKET", "")
    if not bucket:
        log.error("R2_BUCKET not set")
        return 1

    if data_dir is None:
        from lib import config  # noqa: PLC0415
        data_dir = config.data_dir()

    oracle_dir = data_dir / "oracle"
    if not oracle_dir.is_dir():
        log.error("oracle dir not found: %s", oracle_dir)
        return 1

    up = skip = 0
    errors = 0

    for filename in _ORACLE_FILES:
        local_path = oracle_dir / filename
        if not local_path.exists():
            if filename == "manifest.json":
                log.info("manifest.json absent — skipping (optional)")
                continue
            log.error("required file absent: %s", local_path)
            errors += 1
            continue

        key = f"{_R2_PREFIX}/{filename}"
        remote_etag = _remote_etag(s3, bucket, key)
        local_md5 = _md5(local_path)

        if remote_etag == local_md5:
            log.info("unchanged: %s (md5 match)", key)
            skip += 1
            continue

        size_mb = local_path.stat().st_size / 1_048_576
        log.info("uploading: %s (%.1f MB) → %s", filename, size_mb, key)

        if dry_run:
            log.info("DRY-RUN: would upload %s → %s", filename, key)
            up += 1
            continue

        try:
            s3.upload_file(
                str(local_path), bucket, key,
                ExtraArgs={"ContentType": _CT.get(local_path.suffix, "application/octet-stream")},
            )
            log.info("uploaded: %s", key)
            up += 1
        except Exception as e:  # noqa: BLE001
            log.error("upload failed: %s — %s", key, e)
            errors += 1

    log.info(
        "oracle panels publish done: %d uploaded, %d unchanged, %d errors (bucket=%s)",
        up, skip, errors, bucket,
    )
    return 1 if errors else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=None, metavar="PATH",
                    help="Override data directory (default: config.data_dir())")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report delta, upload nothing")
    args = ap.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else None
    return publish(data_dir=data_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
