#!/usr/bin/env python3
"""Backfill public.ip_geo from visitor IPs seen in the analytics tables, using IPLocate.

Why a separate job: the collectors (Terminal /api/collect + macro /api/collect) store only the
raw IP on each event — they never call an external geo API on the hot path, so a beacon can never
block. This job runs off that path: it finds IPs that appear in analytics_events / search_events
but are not yet in ip_geo, looks each up via IPLocate (city / subdivision / country + ASN + VPN /
proxy / hosting flags — works for mainland-China IPs, unlike the discontinued free GeoLite City
DB), and upserts the result. Cached forever per IP (an IP's geo is effectively static).

Budget: capped at IPLOCATE_DAILY_BUDGET lookups per run (default 900, under the 1000/day free
tier); a 429 stops the run early. The next scheduled run picks up whatever is left.

Runs as a GitHub Action cron (.github/workflows/geo-enrich.yml) and is invokable on demand from
the admin console. Reads Supabase through the Management API SQL endpoint — the same mechanism
admin/users.py uses — so it needs no DB driver.

Env:
  SUPABASE_ACCESS_TOKEN / SUPABASE_PAT   sbp_… PAT (Management API)
  SUPABASE_PROJECT_REF                   default fsldfzlxyavsuwqbceod
  IPLOCATE_API_KEY                       IPLocate API key
  IPLOCATE_DAILY_BUDGET                  max lookups per run (default 900)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PROJECT_REF = os.environ.get("SUPABASE_PROJECT_REF") or "fsldfzlxyavsuwqbceod"
PAT = os.environ.get("SUPABASE_ACCESS_TOKEN") or os.environ.get("SUPABASE_PAT") or ""
IPLOCATE_KEY = os.environ.get("IPLOCATE_API_KEY", "")
DEFAULT_BUDGET = int(os.environ.get("IPLOCATE_DAILY_BUDGET", "900"))
QUERY_URL = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"


def _sql(query: str):
    """Run SQL via the Supabase Management API; returns a list of row dicts (or [])."""
    req = urllib.request.Request(
        QUERY_URL,
        data=json.dumps({"query": query}).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    return json.loads(body) if body else []


def _lit(v):
    """Render a Python value as a SQL literal. Values here are IPs / geo strings / numbers / bools
    from IPLocate — no free-form user input — but single-quotes are still escaped defensively."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def pending_ips(limit: int):
    """Distinct IPs present in the event tables but not yet enriched in ip_geo."""
    rows = _sql(
        "select distinct ip from ("
        "  select ip from public.analytics_events where ip is not null "
        "  union "
        "  select ip from public.search_events where ip is not null"
        ") s "
        "where ip <> 'unknown' and ip not in (select ip from public.ip_geo) "
        f"limit {int(limit)}"
    )
    return [r["ip"] for r in rows if r.get("ip")]


def iplocate(ip: str) -> dict:
    """Look one IP up via IPLocate. Query-param auth (verified working) so no header ambiguity."""
    url = (
        f"https://iplocate.io/api/lookup/{urllib.parse.quote(ip)}"
        f"?apikey={urllib.parse.quote(IPLOCATE_KEY)}"
    )
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "mastermind-geo-enrich/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def upsert(ip: str, g: dict) -> None:
    asn = g.get("asn") or {}
    priv = g.get("privacy") or {}
    cols = {
        "ip": ip,
        "country": g.get("country"),
        "country_code": g.get("country_code"),
        "region": g.get("subdivision"),
        "city": g.get("city"),
        "lat": g.get("latitude"),
        "lon": g.get("longitude"),
        "asn": asn.get("asn"),
        "org": asn.get("name"),
        "is_vpn": priv.get("is_vpn"),
        "is_proxy": priv.get("is_proxy"),
        "is_tor": priv.get("is_tor"),
        "is_hosting": priv.get("is_hosting"),
        "is_abuser": priv.get("is_abuser"),
    }
    keys = ", ".join(cols.keys())
    vals = ", ".join(_lit(v) for v in cols.values())
    updates = ", ".join(f"{k} = excluded.{k}" for k in cols if k != "ip")
    _sql(
        f"insert into public.ip_geo ({keys}, fetched_at) values ({vals}, now()) "
        f"on conflict (ip) do update set {updates}, fetched_at = now();"
    )


def run(budget: int = DEFAULT_BUDGET) -> dict:
    """Enrich up to `budget` pending IPs. Returns a summary dict (safe to call from the admin)."""
    if not PAT or not IPLOCATE_KEY:
        return {"ok": False, "reason": "missing SUPABASE_ACCESS_TOKEN or IPLOCATE_API_KEY"}
    ips = pending_ips(budget)
    done, failed = 0, 0
    for ip in ips:
        try:
            upsert(ip, iplocate(ip))
            done += 1
        except urllib.error.HTTPError as ex:
            if ex.code == 429:
                return {"ok": True, "pending": len(ips), "enriched": done, "failed": failed, "rate_limited": True}
            failed += 1
        except Exception:
            failed += 1
        time.sleep(0.05)  # be gentle on IPLocate
    return {"ok": True, "pending": len(ips), "enriched": done, "failed": failed, "rate_limited": False}


def main() -> int:
    res = run(DEFAULT_BUDGET)
    print(f"geo_enrich: {json.dumps(res)}")
    if res.get("ok"):
        return 0
    # A not-yet-configured lane (missing secret) is a clean skip, not a failure — exiting
    # non-zero here turns an unset-secret state into a persistent red X on the every-30-min
    # cron. Only genuine runtime failures should trip the run.
    if str(res.get("reason", "")).startswith("missing "):
        print("geo_enrich: skipping (not configured) — set SUPABASE_ACCESS_TOKEN + IPLOCATE_API_KEY to enable")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
