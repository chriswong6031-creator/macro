"""engine.marketing.media_publish — publish marketing chart PNGs to R2.

Buffer hosts no uploads: to attach a chart to an X post the PNG must live at a
publicly reachable https URL. This module puts a rendered PNG into the SAME R2
data plane every build_* script already reads publicly
(config.yml r2_data_plane.public_base → https://pub-…​.r2.dev), under a
`marketing/charts/<as_of>/<chart_id>.png` key, and returns that public URL.

DARK BY DEFAULT / fail-soft (mirrors scripts/publish_r2.py + social_publisher):
  * R2_* creds absent  → publish_chart_png returns None + one log line (no raise).
  * boto3 missing / any upload error → None + log.warning.
The caller (content_studio) writes the PNG to a local repo path regardless, so a
None here just means "no public URL this run" — the post degrades to text-only.

We invent NO new bucket and touch NO ACLs: the object rides the existing public
data plane. The operator arms this by providing the same R2_ENDPOINT /
R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET the oracle/data lanes use.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# R2 key prefix for marketing chart images (public data plane).
R2_MARKETING_PREFIX = "marketing/charts"

# Fallback public base if config.yml lacks r2_data_plane.public_base. This is the
# same bucket domain every build_* script hard-codes (build_flow_enrich.py,
# build_chain_heat.py, build_prophet_marks.py, audit_r2.py).
_DEFAULT_PUBLIC_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"


def _public_base() -> str:
    """Resolve the R2 public base URL (no trailing slash). Config → fallback const."""
    base = ""
    try:
        from lib import config  # noqa: PLC0415
        base = str(config.load().get("r2_data_plane", {}).get("public_base", "") or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("media_publish: config public_base read failed (%s) — fallback", exc)
    return (base or _DEFAULT_PUBLIC_BASE).rstrip("/")


def _r2_client():
    """S3 client for R2, or None when creds are absent. Mirrors publish_r2._client()."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
        kw: dict[str, Any] = dict(
            region_name="auto", signature_version="s3v4",
            max_pool_connections=8, retries={"max_attempts": 4, "mode": "standard"},
            connect_timeout=15, read_timeout=60)
        try:  # newer botocore: keep R2 happy (it rejects the default CRC32 trailer)
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                            aws_secret_access_key=sk, config=cfg)
    except ImportError:
        log.warning("media_publish: boto3 not installed — cannot upload chart PNG")
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("media_publish: R2 client init failed: %s", exc)
        return None


def chart_key(as_of: str, chart_id: str) -> str:
    """The R2 key for a chart PNG: marketing/charts/<as_of>/<chart_id>.png."""
    safe_as_of = (str(as_of or "").strip() or "unknown").replace("/", "-")
    safe_id = (str(chart_id or "").strip() or "chart").replace("/", "-")
    return f"{R2_MARKETING_PREFIX}/{safe_as_of}/{safe_id}.png"


def public_url_for_key(key: str) -> str:
    """The public https URL a given R2 key resolves to on the data plane."""
    return f"{_public_base()}/{key.lstrip('/')}"


def publish_chart_png(png_bytes: bytes, key: str, *, s3=None) -> str | None:
    """Upload PNG bytes to R2 under `key`; return the public https URL or None.

    Fail-soft: creds absent (no client) → None + log line; any upload error →
    None + log.warning. `s3` may be injected for tests (a stub with put_object).
    Content-Type is image/png. `key` is the full R2 key (see chart_key()).
    """
    if not png_bytes:
        log.warning("media_publish: empty png_bytes for key %s — skip", key)
        return None

    client = s3 if s3 is not None else _r2_client()
    if client is None:
        log.info("media_publish: no R2 creds (R2_ENDPOINT/ACCESS_KEY_ID/SECRET_ACCESS_KEY"
                 "/R2_BUCKET) — chart PNG stays local (no public URL this run)")
        return None

    bucket = os.environ.get("R2_BUCKET", "").strip()
    if not bucket:
        log.warning("media_publish: R2_BUCKET not set — cannot upload %s", key)
        return None

    try:
        client.put_object(Bucket=bucket, Key=key, Body=png_bytes,
                          ContentType="image/png")
    except Exception as exc:  # noqa: BLE001
        log.warning("media_publish: upload failed for %s: %s", key, exc)
        return None

    url = public_url_for_key(key)
    log.info("media_publish: uploaded chart PNG → %s (%d bytes)", url, len(png_bytes))
    return url
