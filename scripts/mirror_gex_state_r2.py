"""scripts/mirror_gex_state_r2.py — mirror site/options_structure/gex_state/*.json to R2.

The nightly commits per-root gex_state regime files into site/, but the Terminal's
f=gexstate proxy reads R2 (options_structure/gex_state/<ROOT>.json) — which was never
populated (QA sweep 2026-07-10: 404 for every root -> GEX tab regime chip 503).

Runs at the end of ops/launchd/run_options_matrix.sh (and standalone). Fail-soft:
any error logs and exits 0 — this mirror must never break the matrix lane.

Env: R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gex_state_mirror")

def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    src = repo / "site" / "options_structure" / "gex_state"
    if not src.is_dir():
        log.warning("source dir absent: %s — nothing to mirror", src)
        return 0
    endpoint = os.environ.get("R2_ENDPOINT")
    bucket = os.environ.get("R2_BUCKET")
    if not endpoint or not bucket:
        log.warning("R2 env absent — skipping mirror (fail-soft)")
        return 0
    try:
        import boto3  # type: ignore
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("boto3 unavailable/misconfigured: %s — skipping", e)
        return 0
    ok = bad = 0
    for f in sorted(src.glob("*.json")):
        try:
            body = f.read_bytes()
            json.loads(body)  # never mirror a corrupt file
            client.put_object(
                Bucket=bucket,
                Key=f"options_structure/gex_state/{f.name}",
                Body=body,
                ContentType="application/json",
            )
            ok += 1
        except Exception as e:  # noqa: BLE001
            bad += 1
            log.warning("skip %s: %s", f.name, e)
    log.info("gex_state mirror done: ok=%d skipped=%d", ok, bad)
    return 0

if __name__ == "__main__":
    sys.exit(main())
