#!/usr/bin/env python3
"""Apply the analytics migration + verify, via the Supabase Management API SQL endpoint.

Reads the PAT from the environment (SUPABASE_ACCESS_TOKEN) — intended to run ON the VPS with
/etc/macro-admin.env sourced, so the token never leaves the operator's box. Idempotent (the SQL is
CREATE ... IF NOT EXISTS). Exit 0 iff the migration applied and both tables exist.
"""
import json
import os
import sys
import urllib.error
import urllib.request

PAT = os.environ["SUPABASE_ACCESS_TOKEN"]
REF = os.environ.get("SUPABASE_PROJECT_REF") or "fsldfzlxyavsuwqbceod"
URL = f"https://api.supabase.com/v1/projects/{REF}/database/query"


def call(sql: str):
    req = urllib.request.Request(
        URL, data=json.dumps({"query": sql}).encode(), method="POST",
        headers={"Authorization": "Bearer " + PAT, "Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=45)
        return resp.getcode(), resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def main() -> int:
    sqlfile = sys.argv[1]
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
