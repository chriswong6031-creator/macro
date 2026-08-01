"""Download earnings-call intelligence stores from R2 (CI nightly shim).

SGA W4 (rulings SGA-R5/R6).  Cloned from scripts/fetch_oracle_panels.py.

The nightly CI runner starts with a fresh checkout; data/earnings_calls/*.parquet
is gitignored and absent.  This shim downloads scores plus the optional full
historical call store from R2 before
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
import json
import logging
import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetch_earnings_scores")

# Files to fetch — mirrors publish_earnings_r2.py
_EARNINGS_FILES = [
    "scores.parquet",
    "history.parquet",  # optional full numeric/tag/highlight migration
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


def _remote_manifest(s3, bucket: str) -> dict | None:
    try:
        body = s3.get_object(
            Bucket=bucket, Key=f"{_R2_PREFIX}/manifest.json",
        )["Body"].read()
        payload = json.loads(body)
        return payload if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _generation_id(manifest: dict) -> str:
    explicit = str(manifest.get("generation_id") or "")
    if explicit:
        return explicit
    scores = manifest.get("scores") if isinstance(manifest.get("scores"), dict) else {}
    history = manifest.get("history") if isinstance(manifest.get("history"), dict) else {}
    material = f"{scores.get('md5') or ''}:{history.get('md5') or ''}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _manifest_contract(manifest: dict | None) -> tuple[bool, str | None]:
    if not isinstance(manifest, dict):
        return False, "manifest_absent_or_unreadable"
    if manifest.get("schema") not in {
        "earnings_intelligence_manifest.v2",
        "earnings_intelligence_manifest.v3",
    }:
        return False, "unsupported_manifest_schema"
    scores = manifest.get("scores")
    if not isinstance(scores, dict):
        return False, "scores_block_absent"
    for field in ("md5", "rows", "tickers"):
        if scores.get(field) in (None, ""):
            return False, f"scores_{field}_absent"
    history = manifest.get("history")
    if history is not None:
        if not isinstance(history, dict):
            return False, "history_block_invalid"
        for field in ("md5", "rows", "tickers"):
            if history.get(field) in (None, ""):
                return False, f"history_{field}_absent"
    if manifest.get("schema") == "earnings_intelligence_manifest.v3":
        for name, filename in (("scores", "scores.parquet"), ("history", "history.parquet")):
            block = manifest.get(name)
            if block is None:
                continue
            key = str(block.get("key") or "")
            if (
                not key.startswith(f"{_R2_PREFIX}/generations/")
                or not key.endswith(f"/{filename}")
            ):
                return False, f"{name}_immutable_key_invalid"
    if manifest.get("generation_id") and manifest.get("generation_id") != _generation_id({
        **manifest, "generation_id": None,
    }):
        return False, "generation_id_mismatch"
    reconciliation = manifest.get("reconciliation")
    if isinstance(reconciliation, dict):
        try:
            if int(reconciliation["input_rows"]) != (
                int(reconciliation["output_rows"])
                + int(reconciliation["rejected_rows"])
            ):
                return False, "reconciliation_arithmetic_mismatch"
        except (KeyError, TypeError, ValueError):
            return False, "reconciliation_counts_invalid"
    return True, None


def _validate_parquet(path: Path, block: dict, name: str) -> tuple[bool, str | None]:
    try:
        if _md5(path) != str(block.get("md5") or ""):
            return False, f"{name}_md5_mismatch"
        expected_bytes = block.get("bytes")
        if expected_bytes is not None and int(expected_bytes) != int(path.stat().st_size):
            return False, f"{name}_bytes_mismatch"
        import pandas as pd  # noqa: PLC0415
        frame = pd.read_parquet(path)
        if int(block.get("rows")) != int(len(frame)):
            return False, f"{name}_rows_mismatch"
        ticker_col = "ticker" if name == "scores" else "document_ticker"
        if ticker_col not in frame.columns:
            return False, f"{name}_{ticker_col}_absent"
        actual_tickers = int(frame[ticker_col].dropna().astype(str).nunique())
        if int(block.get("tickers")) != actual_tickers:
            return False, f"{name}_tickers_mismatch"
    except Exception as exc:  # noqa: BLE001
        return False, f"{name}_validation_error:{exc}"
    return True, None


def _local_generation_current(earnings_dir: Path, manifest: dict) -> bool:
    local_manifest_path = earnings_dir / "manifest.json"
    try:
        local_manifest = json.loads(local_manifest_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    if _generation_id(local_manifest) != _generation_id(manifest):
        return False
    for name, filename in (("scores", "scores.parquet"), ("history", "history.parquet")):
        block = manifest.get(name)
        if block is None:
            if name == "history" and (earnings_dir / filename).exists():
                return False
            continue
        ok, _ = _validate_parquet(earnings_dir / filename, block, name)
        if not ok:
            return False
    return True


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

    manifest = _remote_manifest(s3, bucket)
    valid, reason = _manifest_contract(manifest)
    if not valid:
        log.warning("earnings generation rejected before download: %s", reason)
        return 0
    assert manifest is not None
    generation = _generation_id(manifest)
    if _local_generation_current(earnings_dir, manifest):
        log.info("earnings generation already current: %s", generation)
        return 0
    if dry_run:
        log.info("DRY-RUN: would fetch and validate earnings generation %s", generation)
        return 0

    blocks = [
        ("scores", "scores.parquet", manifest["scores"]),
    ]
    if isinstance(manifest.get("history"), dict):
        blocks.append(("history", "history.parquet", manifest["history"]))

    with tempfile.TemporaryDirectory(prefix=".incoming-earnings-", dir=earnings_dir) as td:
        incoming = Path(td)
        staged: dict[str, Path] = {}
        for name, filename, block in blocks:
            local_path = earnings_dir / filename
            local_ok, _ = _validate_parquet(local_path, block, name) if local_path.exists() else (False, None)
            if local_ok:
                log.info("reusing hash-current local %s", filename)
                continue
            key = str(block.get("key") or f"{_R2_PREFIX}/{filename}")
            target = incoming / filename
            try:
                s3.download_file(bucket, key, str(target))
            except Exception as exc:  # noqa: BLE001
                log.warning("earnings generation %s download failed: %s", generation, exc)
                return 0
            ok, why = _validate_parquet(target, block, name)
            if not ok:
                log.warning(
                    "earnings generation %s rejected: %s", generation, why,
                )
                return 0
            staged[filename] = target

        # Promote payloads with rollback, then atomically commit manifest last.
        backups: dict[str, Path] = {}
        promoted: list[Path] = []
        try:
            targets = {filename for _, filename, _ in blocks}
            if "history.parquet" not in targets and (earnings_dir / "history.parquet").exists():
                old_history = earnings_dir / "history.parquet"
                backup = incoming / "history.parquet.previous"
                os.replace(old_history, backup)
                backups["history.parquet"] = backup
            for filename, source in staged.items():
                target = earnings_dir / filename
                if target.exists():
                    backup = incoming / f"{filename}.previous"
                    os.replace(target, backup)
                    backups[filename] = backup
                os.replace(source, target)
                promoted.append(target)
            manifest_tmp = incoming / "manifest.promote.json"
            manifest_tmp.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
            )
            os.replace(manifest_tmp, earnings_dir / "manifest.json")
        except Exception as exc:  # noqa: BLE001
            for target in promoted:
                target.unlink(missing_ok=True)
            for filename, backup in backups.items():
                if backup.exists():
                    os.replace(backup, earnings_dir / filename)
            log.warning("earnings generation %s promotion rolled back: %s", generation, exc)
            return 0

    log.info("earnings generation promoted: %s", generation)
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
