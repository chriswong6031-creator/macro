"""scripts/mirror_flow_idx.py — R2 mirror for site/flow/index.json.

Uploads site/flow/index.json to R2 key live_flow/flow_idx.json so the live
options-flow heatmap layer can read a fresh flow manifest without waiting for a
full GitHub Pages deploy cycle.

Called as a non-fatal step in daily.yml (engine job) AFTER the parallel band
finishes (cl_gex → build_options_flow has written site/flow/index.json).

Graceful degradation:
  • If R2 creds are absent → skip silently (exit 0).
  • If site/flow/index.json is absent → warn + exit 0.
  • Any upload failure → warn + exit 0 (never fails the nightly).

Usage
-----
    python -m scripts.mirror_flow_idx

No arguments; all config comes from environment variables:
    R2_ENDPOINT           Cloudflare R2 endpoint URL
    R2_ACCESS_KEY_ID      R2 access key
    R2_SECRET_ACCESS_KEY  R2 secret
    R2_BUCKET             R2 bucket name (default: mastermindx)
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parent.parent
FLOW_INDEX_PATH = _REPO / "site" / "flow" / "index.json"
R2_KEY = "live_flow/flow_idx.json"


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
        log.warning("mirror_flow_idx: R2 client build failed: %s", e)
        return None


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not FLOW_INDEX_PATH.exists():
        log.warning(
            "mirror_flow_idx: %s absent — build_options_flow may not have run yet; skipping",
            FLOW_INDEX_PATH,
        )
        return 0

    s3 = _r2_client()
    if s3 is None:
        log.info("mirror_flow_idx: R2 creds absent — skipping upload (non-fatal)")
        return 0

    bucket = os.environ.get("R2_BUCKET", "mastermindx")
    try:
        s3.upload_file(
            str(FLOW_INDEX_PATH),
            bucket,
            R2_KEY,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("mirror_flow_idx: uploaded %s → R2:%s", FLOW_INDEX_PATH.name, R2_KEY)
    except Exception as e:  # noqa: BLE001
        log.warning("mirror_flow_idx: upload failed for %s: %s", R2_KEY, e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
