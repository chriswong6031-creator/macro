"""scripts/ad_ingest_run.py — nightly: first-party analytics → Ad Central ledgers.

Ad Central Plane O (`research/AD_CENTRAL_MASTERPLAN.md` §2).  Reads the
``ad_exposure`` rows the browser shim emitted, plus the identity events that
resolve them into conversions, and hands both to
``engine.marketing.ad_ingest.ingest``.

The I/O lives here and not in the engine on purpose — the same split
``engine/marketing/attribution.py`` documents: engine modules stay pure and
testable, and only a script reaches the network.  Nightly is the sole advancer of
a forward ledger (masterplan §0 G-I), so this is the only writer.

Credentials (same pair `scripts/geo_enrich.py` uses):
    SUPABASE_ACCESS_TOKEN / SUPABASE_PAT   sbp_… Management API PAT
    SUPABASE_PROJECT_REF                   project ref

Unconfigured is a **skip, not a failure**: a nightly that hard-fails when a
secret is absent turns an optional lane into a broken pipeline. Nothing is
written and the exit code stays 0.

Usage:
    python -m scripts.ad_ingest_run [--days 7] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import ad_ingest  # noqa: E402

PROJECT_REF = os.environ.get("SUPABASE_PROJECT_REF") or "fsldfzlxyavsuwqbceod"
PAT = os.environ.get("SUPABASE_ACCESS_TOKEN") or os.environ.get("SUPABASE_PAT") or ""
QUERY_URL = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
# Cloudflare's WAF in front of api.supabase.com 403s the default Python-urllib UA
# (edge error 1010) — same fix as scripts/geo_enrich.py. Without this the query
# fails with a 403 that looks nothing like an auth problem.
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/122.0 Safari/537.36")

DEFAULT_DAYS = 7
MAX_ROWS = 200_000


def _sql(query: str):
    """Run SQL via the Supabase Management API; returns a list of row dicts."""
    req = urllib.request.Request(
        QUERY_URL,
        data=json.dumps({"query": query}).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json",
                 "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode()
    return json.loads(body) if body else []


def fetch_rows(days: int = DEFAULT_DAYS, *, sql=None) -> list[dict]:
    """Every row needed to fold exposures and their conversions.

    Two shapes, unioned in one round trip:

      * ``ad_exposure`` rows — the assignments themselves.
      * any row carrying a ``user_id`` **for a visitor that has an exposure** —
        the identity signal a conversion is derived from. Restricting to those
        visitors is what keeps this from dragging the whole events table back.

    The window is a lookback, not a watermark: `ad_ingest` is idempotent, so
    re-reading yesterday costs nothing and a missed night self-heals. All SQL is
    static text with an int-clamped window — nothing interpolates user input.
    """
    runner = sql or _sql
    days = max(1, min(365, int(days)))
    query = f"""
        with exposed as (
          select distinct visitor_id
            from analytics_events
           where type = 'ad_exposure'
             and created_at > now() - interval '{days} days'
             and visitor_id is not null
        )
        select id, type, visitor_id, user_id, created_at, client_ts, meta
          from analytics_events
         where created_at > now() - interval '{days} days'
           and visitor_id in (select visitor_id from exposed)
           and (type = 'ad_exposure' or user_id is not null)
         order by created_at asc
         limit {MAX_ROWS}
    """
    rows = runner(query)
    return rows if isinstance(rows, list) else []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fold ad_exposure events into the arena ledgers.")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help=f"lookback window in days (default {DEFAULT_DAYS})")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print, write nothing")
    ap.add_argument("--root", default=None,
                    help="repo root to write ledgers under (tests point this at a tmp dir "
                         "so a run can never touch the committed ledger)")
    args = ap.parse_args(argv)
    root = Path(args.root) if args.root else ROOT

    if not PAT:
        # Not an error: the lane is optional until the credential is provisioned.
        print("ad_ingest_run: skipping — set SUPABASE_ACCESS_TOKEN to enable")
        return 0

    try:
        rows = fetch_rows(args.days)
    except Exception as exc:  # noqa: BLE001
        # A read failure must not fail the nightly; the ledger simply does not
        # advance tonight and the next run picks the window up again.
        print(f"::warning title=ad_ingest::analytics read failed: {exc}")
        return 0

    result = ad_ingest.ingest(rows, root=root, dry_run=args.dry_run)
    if not result.get("ok"):
        print(f"::warning title=ad_ingest::{result.get('error')}")
        return 0

    print(f"ad_ingest_run: {result.get('plain', '')}")
    if result.get("anomalies"):
        print(f"ad_ingest_run: anomalies {result['anomalies']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
