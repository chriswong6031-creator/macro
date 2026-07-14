#!/usr/bin/env python3
"""Apply the analytics migration + verify (or --count rows), via the Supabase Management API SQL
endpoint. Reads the PAT from the environment (SUPABASE_ACCESS_TOKEN) — intended to run ON the VPS
with /etc/macro-admin.env sourced, so the token never leaves the operator's box. Idempotent.

NOTE: sends a browser User-Agent. Cloudflare's WAF in front of api.supabase.com 403s the default
`Python-urllib/*` UA with edge error 1010 (same reason admin/users.py uses `requests` and the FRED
client sends a custom UA). Without this header the request is banned before Supabase sees the token.
"""
import json
import os
import sys
import urllib.error
import urllib.request

PAT = os.environ["SUPABASE_ACCESS_TOKEN"]
REF = os.environ.get("SUPABASE_PROJECT_REF") or "fsldfzlxyavsuwqbceod"
URL = f"https://api.supabase.com/v1/projects/{REF}/database/query"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"


def call(sql: str):
    req = urllib.request.Request(
        URL, data=json.dumps({"query": sql}).encode(), method="POST",
        headers={"Authorization": "Bearer " + PAT, "Content-Type": "application/json", "User-Agent": UA})
    try:
        resp = urllib.request.urlopen(req, timeout=45)
        return resp.getcode(), resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def main() -> int:
    if "--count" in sys.argv:
        code, body = call("select count(*)::int as n, max(created_at) as last from public.analytics_events")
        print(f"count_http={code} analytics_events={body}")
        return 0 if code in (200, 201) else 1
    sqlfile = [a for a in sys.argv[1:] if not a.startswith("-")][0]
    code, body = call(open(sqlfile).read())
    print(f"migrate_http={code} {'ok' if code in (200, 201) else body}")
    code, body = call(
        "select table_name from information_schema.tables where table_schema='public' "
        "and table_name in ('analytics_events','ip_geo') order by table_name")
    print(f"verify_tables={body}")
    ok = code in (200, 201) and "analytics_events" in body and "ip_geo" in body
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
