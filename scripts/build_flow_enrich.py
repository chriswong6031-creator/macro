"""scripts/build_flow_enrich.py — I/O wrapper for the flow enrichment engine.

Reads live_flow/feed_current.json from R2 (boto3) with a public-URL fallback,
samples trailing-session archive keys to build threshold pools,
runs engine.flow_enrich.enrich_feed, and publishes live_flow/enrich_current.json.

Usage:
  python -m scripts.build_flow_enrich            # full publish cycle
  python -m scripts.build_flow_enrich --no-publish   # smoke (no R2 write)
  python -m scripts.build_flow_enrich --verbose  # debug logging

Archive strategy:
  The poller archives each hourly snapshot as live_flow/archive/YYYYMMDDTHH.json.
  This script lists the archive prefix, groups keys by session date (YYYYMMDD),
  samples the last key (latest hour) per session for the trailing-5-session pool.
  If archive access is impractical or yields < 2 sessions, bootstrap=True is
  recorded in the envelope.

Fail-soft: any error in threshold computation or OI join → fall back gracefully;
any R2 error → log + exit 0 (never crash-loop launchd).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ── R2 constants ──────────────────────────────────────────────────────────────
_PUBLIC_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"
_R2_PREFIX   = "live_flow/"
_R2_ENRICH_KEY = "live_flow/enrich_current.json"
_OI_KEY        = "options_hub/oi_confirmed.json"

# Trailing sessions to sample for threshold pool
_TRAIL_SESSIONS = 5

# Local output dir (gitignored)
_OUT_DIR_NAME = "live_flow_out"


# ── boto3 R2 client ───────────────────────────────────────────────────────────

def _r2_client():
    ep = os.environ.get("R2_ENDPOINT")
    ak = os.environ.get("R2_ACCESS_KEY_ID")
    sk = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (ep and ak and sk):
        return None
    try:
        import boto3
        from botocore.config import Config

        kw = dict(region_name="auto", signature_version="s3v4",
                  retries={"max_attempts": 3, "mode": "standard"})
        try:
            cfg = Config(**kw, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**kw)
        return boto3.client("s3", endpoint_url=ep,
                            aws_access_key_id=ak,
                            aws_secret_access_key=sk,
                            config=cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_enrich: R2 client build failed: %s", e)
        return None


def _r2_get_json(s3, bucket: str, key: str) -> dict | None:
    """Download and parse JSON from R2.  None on any error."""
    try:
        resp  = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read())
    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_enrich: R2 get %s failed: %s", key, e)
        return None


def _public_get_json(path: str) -> dict | None:
    """Fetch JSON from the R2 public URL as fallback.  None on any error."""
    url = f"{_PUBLIC_BASE}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_enrich: public fetch %s failed: %s", url, e)
        return None


def _fetch_feed(s3, bucket: str) -> dict | None:
    """Fetch feed_current.json: R2 first, public fallback."""
    if s3 and bucket:
        data = _r2_get_json(s3, bucket, _R2_PREFIX + "feed_current.json")
        if data:
            return data
    log.info("build_flow_enrich: falling back to public URL for feed_current.json")
    return _public_get_json("live_flow/feed_current.json")


def _fetch_oi_confirmed(s3, bucket: str) -> dict | None:
    """Fetch options_hub/oi_confirmed.json: R2 first, public fallback."""
    if s3 and bucket:
        data = _r2_get_json(s3, bucket, _OI_KEY)
        if data:
            return data
    return _public_get_json("options_hub/oi_confirmed.json")


# ── archive sampling ──────────────────────────────────────────────────────────

def _sample_archive(s3, bucket: str) -> list[dict]:
    """Sample trailing sessions from live_flow/archive/ for threshold pooling.

    Strategy: list all archive keys, group by session date (YYYYMMDD prefix
    of YYYYMMDDTHH), take the last key (latest hour) per session, sample up to
    _TRAIL_SESSIONS most recent sessions, fetch each and collect events.

    Returns a flat list of all events across the sampled sessions (may be empty).
    If archive is inaccessible, returns [] silently.
    """
    if not (s3 and bucket):
        log.info("build_flow_enrich: no R2 client — skipping archive sample (bootstrap mode)")
        return []

    try:
        out, tok = [], None
        while True:
            kw: dict = {"Bucket": bucket, "Prefix": _R2_PREFIX + "archive/"}
            if tok:
                kw["ContinuationToken"] = tok
            resp = s3.list_objects_v2(**kw)
            for obj in resp.get("Contents", []):
                out.append(obj["Key"])
            if not resp.get("IsTruncated"):
                break
            tok = resp.get("NextContinuationToken")

        if not out:
            log.info("build_flow_enrich: no archive keys found — bootstrap mode")
            return []

        # Group by session date (YYYYMMDD)
        by_date: dict[str, list[str]] = {}
        for key in out:
            # key format: live_flow/archive/YYYYMMDDTHH.json
            stem = Path(key).stem   # e.g. "20260708T14"
            try:
                date_part = stem[:8]   # YYYYMMDD
                datetime.strptime(date_part, "%Y%m%d")   # validate
                by_date.setdefault(date_part, []).append(key)
            except (ValueError, IndexError):
                pass

        # Sort dates descending, take the latest key per session
        pool_events: list[dict] = []
        sessions_sampled = 0
        for date_str in sorted(by_date.keys(), reverse=True)[:_TRAIL_SESSIONS]:
            latest_key = sorted(by_date[date_str], reverse=True)[0]
            data = _r2_get_json(s3, bucket, latest_key)
            if not data:
                continue
            evs = data.get("events", [])
            # Tag each event with its session_date for bootstrap detection
            date_as_sess = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            for ev in evs:
                if isinstance(ev, dict):
                    ev.setdefault("session_date", date_as_sess)
            pool_events.extend(evs)
            sessions_sampled += 1
            log.info("build_flow_enrich: archive session %s → %d events", date_str, len(evs))

        log.info("build_flow_enrich: archive pool: %d sessions, %d events total",
                 sessions_sampled, len(pool_events))
        return pool_events

    except Exception as e:  # noqa: BLE001
        log.warning("build_flow_enrich: archive sample failed: %s — bootstrap mode", e)
        return []


# ── local output ──────────────────────────────────────────────────────────────

def _out_dir() -> Path:
    try:
        from lib import config
        p = config.data_dir() / _OUT_DIR_NAME
    except Exception:  # noqa: BLE001
        p = Path("data") / _OUT_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_json(filename: str, obj: dict) -> Path:
    out = _out_dir() / filename
    tmp = out.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(obj, default=str))
    tmp.rename(out)
    return out


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flow enrichment publisher")
    parser.add_argument("--no-publish", action="store_true",
                        help="Smoke run: compute but do not upload to R2")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from engine import flow_enrich as fe

    asof = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bucket = os.environ.get("R2_BUCKET", "")
    s3 = _r2_client()

    if not s3:
        log.warning("build_flow_enrich: R2 creds absent — using public URL fallback")
    if not bucket and s3:
        log.warning("build_flow_enrich: R2_BUCKET not set — uploads disabled")
        s3 = None  # can't upload without bucket

    # 1. Fetch current feed
    feed_payload = _fetch_feed(s3, bucket)
    if not feed_payload:
        log.error("build_flow_enrich: could not fetch feed_current.json — exit 0 (fail-soft)")
        return 0

    session_date = feed_payload.get("session_date", "")
    n_events     = len(feed_payload.get("events", []))
    log.info("build_flow_enrich: feed asof=%s session=%s events=%d",
             feed_payload.get("asof"), session_date, n_events)

    # 2. Archive sample for trailing-session thresholds
    pool_events = _sample_archive(s3, bucket)

    # 3. Fetch OI confirmed artifact (fail-soft)
    oi_confirmed = _fetch_oi_confirmed(s3, bucket)
    if oi_confirmed:
        n_conf = len(oi_confirmed.get("confirmed", []))
        log.info("build_flow_enrich: oi_confirmed asof=%s confirmed=%d",
                 oi_confirmed.get("asof"), n_conf)
    else:
        log.info("build_flow_enrich: oi_confirmed unavailable — skip OI join")

    # 4. Enrich
    try:
        envelope = fe.enrich_feed(
            feed_payload=feed_payload,
            asof=asof,
            pool_events=pool_events if pool_events else None,
            oi_confirmed=oi_confirmed,
        )
    except Exception as e:  # noqa: BLE001
        log.error("build_flow_enrich: enrich_feed failed: %s — exit 0 (fail-soft)", e,
                  exc_info=True)
        return 0

    log.info("build_flow_enrich: enriched %d events, bootstrap=%s, elite_q=%.1f",
             envelope.get("n_events", 0),
             envelope.get("bootstrap"),
             envelope.get("thresholds", {}).get("elite", 0.0))

    # 5. Write locally
    local_path = _write_json("enrich_current.json", envelope)
    log.info("build_flow_enrich: wrote %s", local_path)

    if args.no_publish:
        log.info("build_flow_enrich: --no-publish set — skipping R2 upload")
        # Print a brief smoke summary
        thresholds = envelope.get("thresholds", {})
        events     = envelope.get("events", [])
        badge_counts: dict[str, int] = {}
        for ev in events:
            for b in ev.get("badges", []):
                badge_counts[b] = badge_counts.get(b, 0) + 1
        print("=== SMOKE SUMMARY ===")
        print(f"  session_date : {session_date}")
        print(f"  n_events     : {envelope.get('n_events', 0)}")
        print(f"  bootstrap    : {envelope.get('bootstrap')}")
        print(f"  thresholds   : elite={thresholds.get('elite'):.1f}  "
              f"strong={thresholds.get('strong'):.1f}  "
              f"high={thresholds.get('high'):.1f}  "
              f"medium={thresholds.get('medium'):.1f}  "
              f"n={thresholds.get('n')}")
        print(f"  badge_counts : {badge_counts}")
        conf_yday = envelope.get("confirmed_yesterday", [])
        print(f"  confirmed_yesterday : {len(conf_yday)}")
        if envelope.get("oi_confirm_note"):
            print(f"  oi_confirm_note : {envelope['oi_confirm_note']}")
        # Sample 3 events
        print("  --- 3 sample enriched events ---")
        for ev in events[:3]:
            print(f"    {ev.get('root'):6s} {ev.get('right')} "
                  f"exp={ev.get('exp')} strike={ev.get('strike')} "
                  f"prem=${ev.get('premium',0)/1e6:.2f}M  "
                  f"q={ev.get('q_score')} tier={ev.get('q_tier')} "
                  f"badges={ev.get('badges')}")
        return 0

    # 6. Upload to R2
    if not s3 or not bucket:
        log.warning("build_flow_enrich: R2 not configured — skipping upload")
        return 0

    try:
        s3.upload_file(
            str(local_path),
            bucket,
            _R2_ENRICH_KEY,
            ExtraArgs={"ContentType": "application/json"},
        )
        log.info("build_flow_enrich: R2 upload ok → %s", _R2_ENRICH_KEY)
    except Exception as e:  # noqa: BLE001
        log.error("build_flow_enrich: R2 upload failed: %s — exit 0 (fail-soft)", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
