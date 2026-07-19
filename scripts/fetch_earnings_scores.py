"""Download earnings-call scores from R2 into data/earnings_calls/ (CI nightly shim).

SGA W4 (rulings SGA-R5/R6).  Cloned from scripts/fetch_oracle_panels.py.

The nightly CI runner starts with a fresh checkout; data/earnings_calls/scores.parquet
is gitignored and absent.  This shim downloads it from R2 before
engine/stage_analysis.py joins earnings scores into the Stage Analysis context
(top_stage2[].earnings + earnings-desk section).

SGA-R6: nightly fetches via this shim and is the SOLE ledger advancer.  The
Windows Qwen worker only produces (publishes to R2) — it never touches git.

Absent-object-safe: if scores.parquet is not in R2 yet (first deploy, or the
worker has not run), the consumer degrades gracefully — the earnings desk shows
its honest null ("No call analyzed yet") and top_stage2[].earnings.present stays
False.  This script NEVER crashes the build — it exits 0 in all cases.

Design mirrors scripts/publish_r2.py conventions:
  - No-op (exit 0) when R2_* creds are absent.
  - Reads: R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
  - Content-hash skip: already-current files are not re-downloaded.

Usage
-----
  python -m scripts.fetch_earnings_scores [--data-dir PATH] [--dry-run]

  --data-dir PATH   override for the data directory (default: config.data_dir())
  --dry-run         report what would be downloaded, write nothing
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
log = logging.getLogger("fetch_earnings_scores")

# Files to fetch — mirrors publish_earnings_r2.py
_EARNINGS_FILES = [
    "scores.parquet",
    "manifest.json",  # optional — skipped if absent on R2
]

_R2_PREFIX = "earnings_calls"


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
        try:
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                            aws_secret_access_key=sk, config=cfg)
    except ImportError:
        log.warning("boto3 not installed — cannot fetch earnings scores")
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
    except Exception:  # noqa: BLE001 — NoSuchKey or absent
        return None


def fetch(data_dir: Path | None = None, dry_run: bool = False) -> int:
    """Download earnings scores from R2.  Always returns 0 (absent-object-safe).

    The caller (nightly CI) relies on exit-0 behaviour: if the scores are not in
    R2 yet, the Stage Analysis earnings desk degrades to its honest null state.
    """
    s3 = _client()
    if s3 is None:
        log.info("no R2 creds (R2_ENDPOINT/ACCESS_KEY_ID/SECRET_ACCESS_KEY) — skip")
        return 0

    bucket = os.environ.get("R2_BUCKET", "")
    if not bucket:
        log.info("R2_BUCKET not set — skip")
        return 0

    if data_dir is None:
        try:
            from lib import config  # noqa: PLC0415
            data_dir = config.data_dir()
        except Exception:  # noqa: BLE001
            log.warning("config.data_dir() failed — using ./data")
            data_dir = Path("data")

    earnings_dir = data_dir / "earnings_calls"
    earnings_dir.mkdir(parents=True, exist_ok=True)

    fetched = skip = absent = 0

    for filename in _EARNINGS_FILES:
        key = f"{_R2_PREFIX}/{filename}"
        local_path = earnings_dir / filename

        remote_etag = _remote_etag(s3, bucket, key)
        if remote_etag is None:
            if filename == "scores.parquet":
                log.warning("earnings scores not in R2 yet: %s — earnings desk will show null", key)
            else:
                log.info("optional object absent: %s — skip", key)
            absent += 1
            continue

        if local_path.exists() and _md5(local_path) == remote_etag:
            log.info("already current: %s (md5 match)", filename)
            skip += 1
            continue

        size_mb: float = 0.0
        try:
            r = s3.head_object(Bucket=bucket, Key=key)
            size_mb = r.get("ContentLength", 0) / 1_048_576
        except Exception:  # noqa: BLE001
            pass

        log.info("fetching: %s (%.1f MB) → %s", key, size_mb, local_path)

        if dry_run:
            log.info("DRY-RUN: would download %s → %s", key, local_path)
            fetched += 1
            continue

        try:
            s3.download_file(bucket, key, str(local_path))
            log.info("fetched: %s (%.1f MB)", filename, size_mb)
            fetched += 1
        except Exception as e:  # noqa: BLE001
            # Non-fatal: log a warning and continue; the earnings desk degrades.
            log.warning("fetch failed for %s — earnings desk may show null: %s", key, e)

    log.info(
        "earnings scores fetch done: %d fetched, %d already-current, %d absent (bucket=%s)",
        fetched, skip, absent, bucket,
    )
    return 0  # Always exit 0 — absent scores do not crash the build


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=None, metavar="PATH",
                    help="Override data directory (default: config.data_dir())")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be fetched, write nothing")
    args = ap.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else None
    return fetch(data_dir=data_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
