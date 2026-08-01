"""Publish earnings-call intelligence stores to R2.

SGA W4 (rulings SGA-R5/R6).  Cloned from scripts/publish_oracle_panels.py.

The earnings-call scores are produced OFF the repo pipeline — primarily by the
standalone Windows-PC Qwen worker (tools/earnings_worker/), and as a cloud
fallback by engine/earnings_qual.py running off-render on the Mac Studio.  The
store is gitignored (data/earnings_calls/) and MUST be published to R2 so the CI
nightly runner can download it (scripts/fetch_earnings_scores.py) before
engine/stage_analysis.py joins scores into the Stage Analysis context.

SGA-R6 (producer / transport): workers write immutable R2 generations via this
script and never advance score data through git. Manifest compare-and-swap plus
worker-side rebase makes concurrent PC/Mac producers lossless. Nightly consumes
the committed generation through the fetch shim.

Key layout: payloads are immutable generation objects under
             earnings_calls/generations/<generation_id>/
            while earnings_calls/manifest.json is the sole mutable commit marker.
            The manifest is synthesized or refreshed from the local stores.

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
    # Full numeric/tag/highlight call history.  This is an optional bootstrap
    # object: the producer may publish scores before the historical migration is
    # available.  It stays out of git and gives fresh CI checkouts the same
    # history used by the Stage Analysis season/comparison surfaces.
    "history.parquet",
    "manifest.json",  # synthesized/refreshed from the local stores
]

# R2 key prefix for earnings-call scores
_R2_PREFIX = "earnings_calls"

# Distinct retryable outcome used by the worker when another producer wins the
# manifest compare-and-swap.  Generic upload/validation failures remain 1.
PUBLISH_CONFLICT = 2

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


def _remote_md5(
    s3,
    bucket: str,
    key: str,
    *,
    filename: str,
    manifest: dict | None = None,
) -> str | None:
    """Return an object's content MD5, including multipart R2 objects.

    A multipart S3/R2 ETag is not a content MD5 (it ends in ``-N``).  New
    uploads carry an explicit metadata hash; the remote manifest is the bridge
    for older large objects uploaded before that metadata existed.
    """
    try:
        r = s3.head_object(Bucket=bucket, Key=key)
        etag = r.get("ETag", "").strip('"')
        if etag and "-" not in etag:
            return etag
        metadata = r.get("Metadata") or {}
        explicit = metadata.get("content-md5")
        if explicit:
            return explicit
        if isinstance(manifest, dict):
            block_name = {
                "scores.parquet": "scores",
                "history.parquet": "history",
            }.get(filename)
            block = manifest.get(block_name) if block_name else None
            if isinstance(block, dict) and block.get("md5"):
                return str(block["md5"])
        return None
    except Exception:  # noqa: BLE001 — NoSuchKey, auth errors, etc.
        return None


def _parquet_stats(path: Path) -> dict:
    """Return compact, fail-open metadata for one parquet object."""
    out: dict[str, object] = {
        "rows": 0,
        "tickers": 0,
        "md5": None,
        "bytes": int(path.stat().st_size) if path.exists() else 0,
    }
    if not path.exists():
        return out
    try:
        out["md5"] = _md5(path)
    except Exception:  # noqa: BLE001
        pass
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
        out["rows"] = int(len(df))
        ticker_col = "ticker" if "ticker" in df.columns else (
            "document_ticker" if "document_ticker" in df.columns else None
        )
        if ticker_col:
            out["tickers"] = int(df[ticker_col].nunique())
        for date_col in ("scored_at", "call_date"):
            if date_col in df.columns and len(df):
                out[f"latest_{date_col}"] = str(df[date_col].max())
    except Exception as exc:  # noqa: BLE001
        log.debug("publish_earnings_r2: parquet stats partial for %s (%s)", path.name, exc)
    return out


def _load_reconciliation(scores_path: Path) -> dict | None:
    path = scores_path.parent.parent / "quality" / "earnings_import_reconciliation.json"
    payload = _read_manifest(path)
    if not isinstance(payload, dict):
        return None
    return {
        "schema": payload.get("schema"),
        "status": payload.get("status"),
        "input_rows": payload.get("input_rows"),
        "output_rows": payload.get("output_rows"),
        "rejected_rows": payload.get("rejected_rows"),
        "duplicate_group_count": payload.get("duplicate_group_count"),
        "source_sha256": payload.get("source_sha256"),
        "source_updated_at_max": payload.get("source_updated_at_max"),
        "invalid_fiscal_period_rows": payload.get("invalid_fiscal_period_rows"),
    }


def _generation_id(scores: dict, history: dict | None) -> str:
    material = ":".join([
        str(scores.get("md5") or ""),
        str((history or {}).get("md5") or ""),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _generation_key(generation_id: str, filename: str) -> str:
    return f"{_R2_PREFIX}/generations/{generation_id}/{filename}"


def _synth_manifest(scores_path: Path, history_path: Path | None = None) -> dict:
    """Build a small manifest describing the earnings intelligence stores.

    Recorded so a consumer can tell scores generations apart at promotion time
    without reading the whole parquet.  NEVER raises — degrades to a minimal
    manifest on any parquet-read error.
    """
    score_stats = _parquet_stats(scores_path)
    history_stats = (
        _parquet_stats(history_path)
        if history_path is not None and history_path.exists()
        else None
    )
    generation_id = _generation_id(score_stats, history_stats)
    score_stats["key"] = _generation_key(generation_id, "scores.parquet")
    if history_stats is not None:
        history_stats["key"] = _generation_key(generation_id, "history.parquet")
    manifest: dict = {
        "schema": "earnings_intelligence_manifest.v3",
        "built": datetime.now(timezone.utc).isoformat(),
        "generation_id": generation_id,
        "scores": score_stats,
        "history": history_stats,
        "reconciliation": _load_reconciliation(scores_path),
    }
    # Keep the v1 top-level fields for older health consumers.
    scores = manifest["scores"] or {}
    manifest["rows"] = scores.get("rows", 0)
    manifest["tickers"] = scores.get("tickers", 0)
    manifest["md5"] = scores.get("md5")
    return manifest


def _read_manifest(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _remote_manifest(s3, bucket: str) -> dict | None:
    """Read the prior R2 manifest so an edge producer can preserve history metadata."""
    payload, _etag = _remote_manifest_snapshot(s3, bucket)
    return payload


def _remote_manifest_snapshot(s3, bucket: str) -> tuple[dict | None, str | None]:
    """Return the current manifest and its opaque ETag for conditional commit."""
    try:
        response = s3.get_object(
            Bucket=bucket,
            Key=f"{_R2_PREFIX}/manifest.json",
        )
        etag = str(response.get("ETag") or "").strip() or None
        payload = json.loads(response["Body"].read())
        return (payload if isinstance(payload, dict) else None), etag
    except Exception:  # noqa: BLE001
        return None, None


def _is_precondition_failed(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error") if isinstance(response.get("Error"), dict) else {}
    metadata = (
        response.get("ResponseMetadata")
        if isinstance(response.get("ResponseMetadata"), dict) else {}
    )
    return (
        str(error.get("Code") or "") in {"PreconditionFailed", "412"}
        or int(metadata.get("HTTPStatusCode") or 0) == 412
    )


def _refresh_manifest(
    manifest_path: Path,
    scores_path: Path,
    history_path: Path,
    *,
    prior: dict | None = None,
) -> bool:
    """Atomically align manifest stats with local objects; return True if changed.

    A score-only producer may not carry the historical migration locally.  In
    that case the last published history block is retained rather than falsely
    declaring the still-present R2 history object absent.
    """
    local_current = _read_manifest(manifest_path) or {}
    preservation_source = prior or local_current
    desired = _synth_manifest(
        scores_path,
        history_path if history_path.exists() else None,
    )
    if not history_path.exists() and isinstance(preservation_source.get("history"), dict):
        desired["history"] = preservation_source["history"]
        desired["generation_id"] = _generation_id(
            desired.get("scores") or {}, desired.get("history"),
        )
        desired["scores"]["key"] = _generation_key(
            desired["generation_id"], "scores.parquet",
        )
    if desired.get("reconciliation") is None and isinstance(
        preservation_source.get("reconciliation"), dict
    ):
        desired["reconciliation"] = preservation_source["reconciliation"]
    current_scores = (
        local_current.get("scores")
        if isinstance(local_current.get("scores"), dict) else {}
    )
    desired_scores = desired.get("scores") or {}
    current_history = (
        local_current.get("history")
        if isinstance(local_current.get("history"), dict) else None
    )
    desired_history = desired.get("history") if isinstance(desired.get("history"), dict) else None
    same = (
        local_current.get("schema") == desired.get("schema")
        and local_current.get("generation_id") == desired.get("generation_id")
        and current_scores.get("md5") == desired_scores.get("md5")
        and (current_history or {}).get("md5") == (desired_history or {}).get("md5")
    )
    if same and manifest_path.exists():
        return False
    tmp = manifest_path.with_name(manifest_path.name + ".tmp")
    tmp.write_text(json.dumps(desired, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, manifest_path)
    return True


def _validate_local_generation(
    manifest: dict | None,
    scores_path: Path,
    history_path: Path,
) -> tuple[bool, str | None]:
    if not isinstance(manifest, dict):
        return False, "manifest_unreadable"
    if manifest.get("schema") != "earnings_intelligence_manifest.v3":
        return False, "manifest_schema_not_v3"
    for name, path, required in (
        ("scores", scores_path, True),
        ("history", history_path, False),
    ):
        block = manifest.get(name)
        if not path.exists():
            if required:
                return False, f"{name}_absent"
            continue
        if not isinstance(block, dict):
            return False, f"{name}_manifest_block_absent"
        stats = _parquet_stats(path)
        for field in ("md5", "bytes", "rows", "tickers"):
            if str(block.get(field)) != str(stats.get(field)):
                return False, f"{name}_{field}_mismatch"
        if int(stats.get("rows") or 0) <= 0:
            return False, f"{name}_empty"
    expected_generation = _generation_id(
        manifest.get("scores") or {}, manifest.get("history"),
    )
    if manifest.get("generation_id") != expected_generation:
        return False, "generation_id_mismatch"
    generation_prefix = f"{_R2_PREFIX}/generations/"
    for name, path in (("scores", scores_path), ("history", history_path)):
        block = manifest.get(name)
        if not isinstance(block, dict):
            continue
        key = str(block.get("key") or "")
        if not key.startswith(generation_prefix) or not key.endswith(f"/{path.name}"):
            return False, f"{name}_immutable_key_invalid"
        # A locally-present payload will be uploaded for this exact generation.
        # A score-only producer may retain an older immutable history key.
        if path.exists() and key != _generation_key(expected_generation, path.name):
            return False, f"{name}_generation_key_mismatch"
    reconciliation = manifest.get("reconciliation")
    if isinstance(reconciliation, dict):
        try:
            if int(reconciliation.get("input_rows")) != (
                int(reconciliation.get("output_rows"))
                + int(reconciliation.get("rejected_rows"))
            ):
                return False, "reconciliation_arithmetic_mismatch"
        except (TypeError, ValueError):
            return False, "reconciliation_counts_invalid"
    return True, None


def publish(
    data_dir: Path | None = None,
    dry_run: bool = False,
    *,
    expected_manifest_etag: str | None = None,
) -> int:
    """Upload earnings scores to R2.

    ``expected_manifest_etag`` is the commit marker observed during the
    caller's pre-write hydration. When supplied, promotion is conditional on
    that exact parent still being current; a newer producer therefore forces a
    rebase instead of allowing a stale read to overwrite its rows.
    """
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

    # Refresh the manifest whenever either store advances.  The previous
    # absent-only behavior let a healthy producer publish new parquet bytes
    # beside a permanently stale generation record.
    manifest_path = earnings_dir / "manifest.json"
    remote_manifest, remote_manifest_etag = _remote_manifest_snapshot(s3, bucket)
    try:
        prior = _read_manifest(manifest_path) or remote_manifest
        if _refresh_manifest(
            manifest_path,
            scores_path,
            earnings_dir / "history.parquet",
            prior=prior,
        ):
            log.info("refreshed manifest.json from earnings stores")
    except Exception as exc:  # noqa: BLE001
        log.warning("could not refresh manifest.json (%s)", exc)

    manifest = _read_manifest(manifest_path)
    valid, reason = _validate_local_generation(
        manifest, scores_path, earnings_dir / "history.parquet",
    )
    if not valid:
        log.error("refusing earnings publish: invalid local generation (%s)", reason)
        return 1

    up = skip = errors = 0

    # Payloads first.  The manifest is the generation commit marker and is only
    # promoted after every required local payload succeeds or is hash-current.
    payload_files = ["scores.parquet"]
    if (earnings_dir / "history.parquet").exists():
        payload_files.append("history.parquet")

    for filename in payload_files:
        local_path = earnings_dir / filename
        block_name = "scores" if filename == "scores.parquet" else "history"
        block = manifest.get(block_name) or {}
        key = str(block.get("key") or "")
        if not key:
            log.error("payload key absent from manifest: %s", filename)
            errors += 1
            continue
        remote_hash = _remote_md5(
            s3,
            bucket,
            key,
            filename=filename,
            manifest=remote_manifest,
        )
        local_md5 = _md5(local_path)

        if remote_hash == local_md5:
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
                ExtraArgs={
                    "ContentType": _CT.get(local_path.suffix, "application/octet-stream"),
                    "Metadata": {"content-md5": local_md5},
                },
            )
            log.info("uploaded: %s", key)
            up += 1
        except Exception as e:  # noqa: BLE001
            log.error("upload failed: %s — %s", key, e)
            errors += 1

    if errors:
        log.error(
            "payload publish incomplete; manifest generation %s NOT promoted",
            manifest.get("generation_id"),
        )
        return 1

    # Commit marker last.  A consumer that races the payload uploads either sees
    # the prior manifest and rejects mismatched bytes, or sees this complete one.
    manifest_key = f"{_R2_PREFIX}/manifest.json"
    manifest_md5 = _md5(manifest_path)
    remote_manifest_md5 = _remote_md5(
        s3, bucket, manifest_key, filename="manifest.json",
    )
    if remote_manifest_md5 == manifest_md5:
        log.info("unchanged: %s (md5 match)", manifest_key)
        skip += 1
    elif dry_run:
        log.info("DRY-RUN: would promote generation %s", manifest.get("generation_id"))
        up += 1
    else:
        try:
            put_args = {
                "Bucket": bucket,
                "Key": manifest_key,
                "Body": manifest_path.read_bytes(),
                "ContentType": "application/json",
                "Metadata": {
                    "content-md5": manifest_md5,
                    "generation-id": str(manifest.get("generation_id") or ""),
                },
            }
            conditional_etag = (
                str(expected_manifest_etag).strip()
                if expected_manifest_etag is not None
                else remote_manifest_etag
            )
            if conditional_etag:
                put_args["IfMatch"] = conditional_etag
            else:
                put_args["IfNoneMatch"] = "*"
            s3.put_object(**put_args)
            log.info("promoted generation: %s", manifest.get("generation_id"))
            up += 1
        except Exception as exc:  # noqa: BLE001
            if _is_precondition_failed(exc):
                log.warning(
                    "manifest promotion lost compare-and-swap for generation %s",
                    manifest.get("generation_id"),
                )
                return PUBLISH_CONFLICT
            log.error("manifest promotion failed: %s", exc)
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
