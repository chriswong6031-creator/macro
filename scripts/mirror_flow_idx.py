"""scripts/mirror_flow_idx.py — R2 mirror for site/flow/index.json and flow leaders.

Uploads site/flow/index.json to R2 key live_flow/flow_idx.json so the live
options-flow heatmap layer can read a fresh flow manifest without waiting for a
full GitHub Pages deploy cycle.

With --leaders flag, uploads site/flowleaders/leaders.json to R2 key
flowleaders/leaders.json (Flow Leaders Desk W2).

Called as a non-fatal step in daily.yml (engine job) AFTER the parallel band
finishes (cl_gex → build_options_flow has written site/flow/index.json).

Graceful degradation:
  * If R2 creds are absent → skip silently (exit 0).
  * If source file is absent → warn + exit 0.
  * Any upload failure → warn + exit 0 (never fails the nightly).

Usage
-----
    python -m scripts.mirror_flow_idx             # uploads flow_idx.json
    python -m scripts.mirror_flow_idx --leaders   # uploads leaders.json

No other arguments; all config comes from environment variables:
    R2_ENDPOINT           Cloudflare R2 endpoint URL
    R2_ACCESS_KEY_ID      R2 access key
    R2_SECRET_ACCESS_KEY  R2 secret
    R2_BUCKET             R2 bucket name (default: mastermindx)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parent.parent
FLOW_INDEX_PATH = _REPO / "site" / "flow" / "index.json"
R2_KEY = "live_flow/flow_idx.json"

LEADERS_PATH = _REPO / "site" / "flowleaders" / "leaders.json"
LEADERS_R2_KEY = "flowleaders/leaders.json"


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


def _upload(s3, local_path: Path, r2_key: str, bucket: str) -> None:
    """Upload local_path to R2 bucket/r2_key. Logs warning on failure (non-fatal)."""
    if not local_path.exists():
        log.warning(
            "mirror_flow_idx: %s absent — skipping R2 upload for %s",
            local_path,
            r2_key,
        )
        return
    try:
        s3.upload_file(
            str(local_path),
            bucket,
            r2_key,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("mirror_flow_idx: uploaded %s → R2:%s", local_path.name, r2_key)
    except Exception as e:  # noqa: BLE001
        log.warning("mirror_flow_idx: upload failed for %s: %s", r2_key, e)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="R2 mirror for flow index / leaders")
    parser.add_argument(
        "--leaders",
        action="store_true",
        help="Upload site/flowleaders/leaders.json instead of site/flow/index.json",
    )
    args = parser.parse_args()

    if args.leaders:
        local_path = LEADERS_PATH
        r2_key = LEADERS_R2_KEY
    else:
        local_path = FLOW_INDEX_PATH
        r2_key = R2_KEY

    if not local_path.exists():
        log.warning(
            "mirror_flow_idx: %s absent — builder may not have run yet; skipping",
            local_path,
        )
        return 0

    s3 = _r2_client()
    if s3 is None:
        log.info("mirror_flow_idx: R2 creds absent — skipping upload (non-fatal)")
        return 0

    bucket = os.environ.get("R2_BUCKET", "mastermindx")
    _upload(s3, local_path, r2_key, bucket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
