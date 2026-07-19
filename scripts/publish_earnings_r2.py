"""Publish earnings-call qualitative scores (scores.parquet + manifest.json) to R2.

SGA W4 (rulings SGA-R5/R6).  Cloned from scripts/publish_oracle_panels.py.

The earnings-call scores are produced OFF the repo pipeline — primarily by the
standalone Windows-PC Qwen worker (tools/earnings_worker/), and as a cloud
fallback by engine/earnings_qual.py running off-render on the Mac Studio.  The
store is gitignored (data/earnings_calls/) and MUST be published to R2 so the CI
nightly runner can download it (scripts/fetch_earnings_scores.py) before
engine/stage_analysis.py joins scores into the Stage Analysis context.

SGA-R6 (single-writer / transport): the Windows worker is producer-only — it
writes R2 via this script and NEVER touches git.  Nightly is the sole ledger
advancer via the fetch shim.

Key layout:  data/earnings_calls/scores.parquet   →  R2 key  earnings_calls/scores.parquet
             data/earnings_calls/manifest.json     →  R2 key  earnings_calls/manifest.json
             (manifest optional — synthesized from the parquet when absent)

Design mirrors scripts/publish_r2.py exactly:
  - No-op (exit 0) when R2_* creds are absent — safe to call from any lane.
  - Reads: R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
  - Content-hash skip: compares local MD5 to R2 ETag; unchanged files skipped.

Usage
-----
  python -m scripts.publish_earnings_r2 [--data-dir PATH] [--dry-run]

  --data-dir PATH   override for the data directory (default: config.data_dir())
  --dry-run         report delta, upload nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("publish_earnings_r2")

# Files to publish, relative to data/earnings_calls/
_EARNINGS_FILES = [
    "scores.parquet",
    "manifest.json",  # synthesized from the parquet if absent
]

# R2 key prefix for earnings-call scores
_R2_PREFIX = "earnings_calls"

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
        log.warning("boto3 not installed — cannot publish earnings scores")
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


def _synth_manifest(scores_path: Path) -> dict:
    """Build a small manifest describing the scores parquet.

    Recorded so a consumer can tell scores generations apart at promotion time
    without reading the whole parquet.  NEVER raises — degrades to a minimal
    manifest on any parquet-read error.
    """
    manifest: dict = {
        "schema": "earnings_scores_manifest.v1",
        "built": datetime.now(timezone.utc).isoformat(),
        "rows": 0,
        "tickers": 0,
        "md5": None,
    }
    try:
        manifest["md5"] = _md5(scores_path)
    except Exception:  # noqa: BLE001
        pass
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(scores_path)
        manifest["rows"] = int(len(df))
        if "ticker" in df.columns:
            manifest["tickers"] = int(df["ticker"].nunique())
        if "scored_at" in df.columns and len(df):
            manifest["latest_scored_at"] = str(df["scored_at"].max())
    except Exception as exc:  # noqa: BLE001
        log.debug("publish_earnings_r2: manifest synth partial (%s)", exc)
    return manifest


def publish(data_dir: Path | None = None, dry_run: bool = False) -> int:
    """Upload earnings scores to R2.  Returns 0 on success, 1 on error."""
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

    earnings_dir = data_dir / "earnings_calls"
    if not earnings_dir.is_dir():
        log.error("earnings_calls dir not found: %s", earnings_dir)
        return 1

    scores_path = earnings_dir / "scores.parquet"
    if not scores_path.exists():
        log.error("required file absent: %s", scores_path)
        return 1

    # Synthesize a manifest if the producer did not write one.
    manifest_path = earnings_dir / "manifest.json"
    if not manifest_path.exists():
        try:
            manifest_path.write_text(
                json.dumps(_synth_manifest(scores_path), indent=2), encoding="utf-8"
            )
            log.info("synthesized manifest.json from scores.parquet")
        except Exception as exc:  # noqa: BLE001
            log.warning("could not synthesize manifest.json (%s)", exc)

    up = skip = errors = 0

    for filename in _EARNINGS_FILES:
        local_path = earnings_dir / filename
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
        "earnings scores publish done: %d uploaded, %d unchanged, %d errors (bucket=%s)",
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
