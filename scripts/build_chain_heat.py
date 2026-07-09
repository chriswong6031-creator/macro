"""scripts/build_chain_heat.py — Chain Heat aggregator publisher.

Fetches live_flow/feed_current.json from R2, runs aggregate_chain_heat,
wraps the result in the options_flow.chain_heat/v1 envelope, and publishes
to R2 as live_flow/chain_heat_current.json.

Usage
-----
  python -m scripts.build_chain_heat          # publish to R2
  python -m scripts.build_chain_heat --no-publish  # write local chain_heat_current.json

Fail-soft contract
------------------
Any exception → logged + exit 0 (the card stays on last-good data; the spinner
is worse than stale honest data).  Only --no-publish writes to disk on success.

Display-tier only — no signal origination, no scoring.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

log = logging.getLogger(__name__)


# ─── Feed fetch ───────────────────────────────────────────────────────────────

_FEED_KEY     = "live_flow/feed_current.json"
_PUBLISH_KEY  = "live_flow/chain_heat_current.json"
_PUBLIC_BASE  = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"


def _r2_client():
    """Build a boto3 S3 client from env vars (loaded by run_with_env.sh)."""
    import boto3  # type: ignore[import]
    endpoint = os.environ.get("R2_ENDPOINT", "")
    key_id   = os.environ.get("R2_ACCESS_KEY_ID", "")
    secret   = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    if not (endpoint and key_id and secret):
        raise RuntimeError(
            "R2_ENDPOINT / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY not set"
        )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
    )


def _fetch_feed_r2(bucket: str) -> dict:
    """Fetch live_flow/feed_current.json via boto3."""
    client = _r2_client()
    obj = client.get_object(Bucket=bucket, Key=_FEED_KEY)
    return json.loads(obj["Body"].read())


def _fetch_feed_public() -> dict:
    """Fallback: fetch via public R2 HTTPS endpoint."""
    import urllib.request
    url = f"{_PUBLIC_BASE}/{_FEED_KEY}"
    log.info("falling back to public R2 URL: %s", url)
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read())


def fetch_feed() -> dict:
    """Fetch feed_current.json; try R2 boto3 first, then public HTTPS."""
    bucket = os.environ.get("R2_BUCKET", "")
    if bucket:
        try:
            return _fetch_feed_r2(bucket)
        except Exception as exc:
            log.warning("R2 boto3 fetch failed (%s); trying public URL", exc)
    return _fetch_feed_public()


# ─── side → ask_share mapping ─────────────────────────────────────────────────
# live_flow.feed/v1 events carry 'side' ("~buy" | "~sell" | "mixed") rather
# than a per-event ask_share fraction.  Map to ask_share proxy so the
# aggregate_chain_heat lean logic works correctly.
#
# Mapping rationale (display-tier only — lean stays "soft"):
#   ~buy  → ask-side aggression → ask_share = 0.80 (above accumulation threshold 0.65)
#   ~sell → bid-side aggression → ask_share = 0.20 (below distribution threshold 0.35)
#   mixed → no signal           → ask_share = 0.50 (contested range)
#   None  → unknown             → ask_share = None  (contested by default)

_SIDE_TO_ASK_SHARE: dict[str, float | None] = {
    "~buy":  0.80,
    "~sell": 0.20,
    "mixed": 0.50,
}


def _enrich_events(events: list[dict]) -> list[dict]:
    """Inject ask_share from side field so the aggregator can compute lean."""
    enriched = []
    for ev in events:
        side = ev.get("side")
        ev_out = dict(ev)
        if "ask_share" not in ev_out:
            ev_out["ask_share"] = _SIDE_TO_ASK_SHARE.get(side)  # type: ignore[assignment]
        enriched.append(ev_out)
    return enriched


# ─── Envelope builder ─────────────────────────────────────────────────────────

def build_envelope(campaigns_raw: list[dict], session_date: str, asof: str) -> dict:
    """Wrap aggregated campaigns in the options_flow.chain_heat/v1 envelope.

    The UI (FlowDeskView.tsx / ChainHeatRail) reads:
        schema, asof, session_date, threshold_mn, note_en, note_zh, campaigns[]
    Each campaign must carry:
        option_symbol, ticker, type ("CALL"|"PUT"), strike, expiry, dte,
        total_premium_mn, alert_count, span_minutes, first_seen,
        ask_share, lean, direction_reliability, authority_tier, note (nullable)

    aggregate_chain_heat returns 'right' ("CALL"|"PUT"); we rename it to 'type'
    to match the UI interface (ChainHeatCampaign.type in FlowDeskView.tsx).
    """
    campaigns: list[dict] = []
    for c in campaigns_raw:
        campaign = dict(c)
        # Rename 'right' → 'type' (UI contract)
        if "right" in campaign and "type" not in campaign:
            campaign["type"] = campaign.pop("right")
        # Remove internal-only 'last_seen' (not in UI contract)
        campaign.pop("last_seen", None)
        # Ensure 'note' key is present (nullable)
        if "note" not in campaign:
            campaign["note"] = None
        campaigns.append(campaign)

    return {
        "schema":        "options_flow.chain_heat/v1",
        "asof":          asof,
        "session_date":  session_date,
        "threshold_mn":  3,
        "note_en":       "DISPLAY-ONLY — intraday chain-heat snapshot. Not investment advice.",
        "note_zh":       "仅供展示 — 盘中链热快照，不构成投资建议。",
        "campaigns":     campaigns,
    }


# ─── Publish ──────────────────────────────────────────────────────────────────

def publish_r2(payload: dict, bucket: str) -> None:
    """PUT chain_heat_current.json to R2."""
    client = _r2_client()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    client.put_object(
        Bucket=bucket,
        Key=_PUBLISH_KEY,
        Body=body,
        ContentType="application/json",
    )
    log.info("published %s bytes to R2: %s", len(body), _PUBLISH_KEY)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """Entry point; returns exit code (always 0 — fail-soft)."""
    parser = argparse.ArgumentParser(description="Build + publish chain_heat_current.json")
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="write chain_heat_current.json locally instead of uploading to R2",
    )
    parser.add_argument(
        "--min-premium-mn",
        type=float,
        default=3.0,
        help="minimum campaign premium in $M (default 3.0)",
    )
    parser.add_argument(
        "--min-alerts",
        type=int,
        default=2,
        help="minimum alert count per campaign (default 2)",
    )
    args = parser.parse_args(argv)

    try:
        # 1. Fetch feed
        log.info("fetching %s", _FEED_KEY)
        feed = fetch_feed()
        events = feed.get("events", [])
        session_date = feed.get("session_date", "")
        feed_asof = feed.get("asof", "")
        log.info("feed: session=%s asof=%s events=%d", session_date, feed_asof, len(events))

        # 2. Enrich events with ask_share proxy from side field
        enriched = _enrich_events(events)

        # 3. Aggregate
        from engine.options_structure import aggregate_chain_heat  # type: ignore[import]
        campaigns_raw = aggregate_chain_heat(
            enriched,
            min_premium_mn=args.min_premium_mn,
            min_alerts=args.min_alerts,
            session_date=session_date,
        )
        log.info("aggregated %d campaigns", len(campaigns_raw))

        # 4. Wrap in envelope
        # asof = now (when we built the snapshot); session_date from feed
        asof_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = build_envelope(campaigns_raw, session_date, asof_now)

        # 5. Publish or write local
        if args.no_publish:
            out_path = "chain_heat_current.json"
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            log.info("wrote local: %s (%d campaigns)", out_path, len(campaigns_raw))
        else:
            bucket = os.environ.get("R2_BUCKET", "")
            if not bucket:
                raise RuntimeError("R2_BUCKET not set")
            publish_r2(payload, bucket)
            log.info("done — %d campaigns published", len(campaigns_raw))

    except Exception:
        log.exception("build_chain_heat failed — exiting 0 (fail-soft)")

    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    sys.exit(main())
