"""engine.prophet_live.r2io — R2 object helpers for the Prophet Live runtime plane.

Everything this program publishes is RUNTIME tier and lives in R2, never in
``data/`` (G0.2 — the nightly reconciler is the only writer of
``data/prophet_live/``). Three lanes share these helpers: the nightly pack
publisher, the */5 evaluator, and the nightly reconciler.

Client construction is copied from ``scripts/publish_r2.py::_client`` — same
endpoint/credential env vars, same botocore checksum workaround (R2 rejects the
default CRC32 trailer). boto3 is imported LAZILY so a lane that only reads the
public mirror, and every test lane, can import this module without it.

READS PREFER THE AUTHENTICATED PATH. The public ``r2.dev`` base sits behind a CDN,
and a cached copy of the previous pass's artifact would silently corrupt the
evaluator's debounce counters (the stale-CDN-variant trap). So ``get_json`` goes
through the S3 API when credentials exist and only falls back to the public base
when they do not — in which case the lane can still read but not publish, which is
the honest degradation.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

#: Same literal every other build_* script falls back to.
_DEFAULT_PUBLIC_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"

PACK_KEY = "live_flow/prophet_live_armed.json"
LIVE_KEY = "live_flow/prophet_live.json"
EVENTS_PREFIX = "live_flow/prophet_live_events"


def public_base() -> str:
    """The R2 public base URL (no trailing slash). config.yml → in-code fallback."""
    base = ""
    try:
        from lib import config  # noqa: PLC0415
        base = str((config.load().get("r2_data_plane") or {}).get("public_base") or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("r2io: config public_base read failed (%s) — fallback", exc)
    return (base or _DEFAULT_PUBLIC_BASE).rstrip("/")


def bucket() -> str:
    return os.environ.get("R2_BUCKET", "mastermindx").strip() or "mastermindx"


def client():
    """S3 client for R2, or None when credentials are absent (graceful no-op)."""
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config  # noqa: PLC0415
        kw: dict[str, Any] = dict(region_name="auto", signature_version="s3v4",
                                  max_pool_connections=8,
                                  retries={"max_attempts": 4, "mode": "standard"},
                                  connect_timeout=15, read_timeout=60)
        try:
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep, aws_access_key_id=ak,
                            aws_secret_access_key=sk, config=cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("r2io: client build failed: %s", exc)
        return None


def fetch_public_json(key: str, *, timeout: float = 20.0) -> dict | None:
    """GET one JSON object off the public base with stdlib urllib (no requests dep)."""
    import urllib.request  # noqa: PLC0415
    url = f"{public_base()}/{key.lstrip('/')}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "macro-prophet-live/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("r2io: public GET %s failed: %s", url, exc)
        return None


def get_json(key: str, *, s3=None, allow_public: bool = True) -> dict | None:
    """Read one JSON object: authenticated S3 first, public base as the fallback."""
    cl = s3 if s3 is not None else client()
    if cl is not None:
        try:
            body = cl.get_object(Bucket=bucket(), Key=key)["Body"].read()
            return json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            # A missing key is the normal first-pass case, not a failure.
            log.info("r2io: S3 GET %s unavailable (%s)", key, exc)
    return fetch_public_json(key) if allow_public else None


def put_json(key: str, payload: Any, *, s3=None) -> bool:
    """Write one JSON object. False (never a raise) when credentials are absent.

    ``PROPHET_LIVE_NO_PUBLISH=1`` refuses every write with a line-start warning. Set it
    in any receipt, rehearsal or demo that runs the real lane end to end: the event
    spool is the ledger's raw input, and a fabricated row joined to real closes is
    indistinguishable from a genuine one forever. The reconciler's
    ``LEDGER_FLOOR_SESSION`` is the second layer of the same protection.
    """
    if os.environ.get("PROPHET_LIVE_NO_PUBLISH", "").strip() not in ("", "0", "false"):
        print(f"::warning title=prophet-live::PROPHET_LIVE_NO_PUBLISH is set — "
              f"refusing to write {key}", flush=True)
        return False
    cl = s3 if s3 is not None else client()
    if cl is None:
        log.warning("r2io: no R2 credentials — %s not published", key)
        return False
    try:
        body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("r2io: %s payload is not JSON-safe: %s", key, exc)
        return False
    try:
        cl.put_object(Bucket=bucket(), Key=key, Body=body,
                      ContentType="application/json")
        log.info("r2io: published %s (%d bytes)", key, len(body))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("r2io: PUT %s failed: %s", key, exc)
        return False


def list_keys(prefix: str, *, s3=None) -> list[str]:
    """Every key under ``prefix``, paginated. Empty list on any failure."""
    cl = s3 if s3 is not None else client()
    if cl is None:
        return []
    out: list[str] = []
    kw: dict[str, Any] = {"Bucket": bucket(), "Prefix": prefix}
    try:
        while True:
            r = cl.list_objects_v2(**kw)
            out.extend(str(o["Key"]) for o in (r.get("Contents") or []))
            token = r.get("NextContinuationToken")
            if not r.get("IsTruncated") or not token:
                break
            kw["ContinuationToken"] = token
    except Exception as exc:  # noqa: BLE001
        log.warning("r2io: LIST %s failed: %s", prefix, exc)
        return out
    return out


def events_key(session: str, stamp: str, *, prefix: str = EVENTS_PREFIX) -> str:
    """``<prefix>/<YYYY-MM-DD>/<HHMMSS>.json`` — one object per pass.

    Object-per-pass, never read-modify-write: two passes cannot both be holding the
    day's file, so nothing can lose a row (the shared-``.tmp`` erasure class).
    """
    return f"{prefix}/{session}/{stamp}.json"
