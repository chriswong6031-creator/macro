"""scripts/mirror_terminal_context_r2.py — mirror the Terminal EOD-context artifacts to R2.

The nightly commits these into site/, but the Terminal reads R2 (it has no GitHub Pages
dependency and must not wait a full deploy cycle for fresh EOD context). Same problem the
gex_state mirror solved for the GEX regime chip (scripts/mirror_gex_state_r2.py); same
conventions and the same fail-soft contract.

Mirrored (OEU_MASTERPLAN §4 M-XP b — consumed by lane T-E, the Terminal EOD context belt):

    site/darkpool_eod.json  →  R2  darkpool/eod.json    (Dark Pool mini-panel)
    site/vol/regime.json    →  R2  vol/regime.json      (vol-regime snapshot + game plan)

Both are whole-file JSON artifacts, so the keys mirror the source names rather than the
per-root fan-out gex_state uses.

Fail-soft (this must never break the nightly — it is a freshness convenience, not a gate):
  * R2 creds absent            → skip silently, exit 0.
  * Source file absent         → warn, exit 0 (the builder may not have run this cycle).
  * Source file not valid JSON → warn + SKIP that file, exit 0 (never mirror a corrupt
                                 artifact over a good one — mirror_gex_state_r2 convention).
  * Upload failure             → warn, exit 0.
Exit code is always 0. The only signal is the log line + the returned counts.

Usage
-----
    python -m scripts.mirror_terminal_context_r2                  # both
    python -m scripts.mirror_terminal_context_r2 --only darkpool  # one
    python -m scripts.mirror_terminal_context_r2 --dry-run        # resolve + validate, no IO

Environment:
    R2_ENDPOINT           Cloudflare R2 endpoint URL
    R2_ACCESS_KEY_ID      R2 access key
    R2_SECRET_ACCESS_KEY  R2 secret
    R2_BUCKET             R2 bucket name (default: mastermindx)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("terminal_context_mirror")

_REPO = Path(__file__).resolve().parent.parent

# name → (repo-relative source, R2 key). Order is the mirror order.
MIRRORS: dict[str, tuple[str, str]] = {
    "darkpool":   ("site/darkpool_eod.json", "darkpool/eod.json"),
    "vol-regime": ("site/vol/regime.json",   "vol/regime.json"),
}


def source_path(name: str) -> Path:
    """Absolute path to a mirror's source artifact."""
    return _REPO / MIRRORS[name][0]


def r2_key(name: str) -> str:
    """R2 key a mirror uploads to."""
    return MIRRORS[name][1]


def _r2_client():
    """Build a boto3 S3 client for R2, or None if creds are absent."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config

        kw = dict(
            region_name="auto",
            signature_version="s3v4",
            max_pool_connections=8,
            retries={"max_attempts": 3, "mode": "standard"},
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
            endpoint_url=ep,
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            config=cfg,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("R2 client build failed: %s", e)
        return None


def read_valid_json_bytes(path: Path) -> bytes | None:
    """Return the file's bytes iff they parse as JSON, else None (logs why).

    Guards the "never mirror a corrupt file" law: a half-written artifact must not replace
    a good copy already in R2.
    """
    if not path.exists():
        log.warning("%s absent — builder may not have run; skipping", path)
        return None
    try:
        body = path.read_bytes()
        json.loads(body)
        return body
    except Exception as e:  # noqa: BLE001
        log.warning("%s is not valid JSON (%s) — skipping (never mirror a corrupt file)",
                    path, e)
        return None


def mirror(names: list[str], *, dry_run: bool = False) -> dict:
    """Mirror the named artifacts. Returns {ok, skipped, failed} counts. Never raises."""
    res = {"ok": 0, "skipped": 0, "failed": 0}
    payloads: list[tuple[str, bytes]] = []
    for name in names:
        body = read_valid_json_bytes(source_path(name))
        if body is None:
            res["skipped"] += 1
            continue
        payloads.append((name, body))

    if dry_run:
        for name, body in payloads:
            log.info("dry-run: would upload %s (%d KB) → R2:%s",
                     MIRRORS[name][0], len(body) // 1024, r2_key(name))
        res["ok"] = len(payloads)
        return res

    if not payloads:
        return res

    s3 = _r2_client()
    if s3 is None:
        log.info("R2 creds absent — skipping upload (non-fatal)")
        res["skipped"] += len(payloads)
        return res

    bucket = os.environ.get("R2_BUCKET", "mastermindx")
    for name, body in payloads:
        key = r2_key(name)
        try:
            s3.put_object(Bucket=bucket, Key=key, Body=body,
                          ContentType="application/json")
            log.info("uploaded %s (%d KB) → R2:%s", MIRRORS[name][0], len(body) // 1024, key)
            res["ok"] += 1
        except Exception as e:  # noqa: BLE001
            log.warning("upload failed for %s: %s", key, e)
            res["failed"] += 1
    return res


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description="Mirror Terminal EOD-context artifacts to R2")
    ap.add_argument("--only", action="append", choices=sorted(MIRRORS),
                    help="mirror only this artifact (repeatable); default: all")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve + JSON-validate the sources, print the keys, upload nothing")
    args = ap.parse_args(argv)

    names = args.only or list(MIRRORS)
    res = mirror(names, dry_run=args.dry_run)
    log.info("terminal-context mirror done: ok=%d skipped=%d failed=%d",
             res["ok"], res["skipped"], res["failed"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
