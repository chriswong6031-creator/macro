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

Failure semantics (three distinct states — do not collapse them):
  absent credential      -> exit 0, "skipping (not configured)". The lane is off, not broken.
  rejected credential    -> exit 3 + a ::error annotation naming the secret to rotate. The
                            lane IS broken; it stays red rather than serving stale geography
                            behind a green badge. Management API PATs expire (~30 days).
  provider 5xx / 429     -> the IP stays pending and is retried next tick. Nothing is written,
                            so last-known-good survives and nothing is stamped fresh.
An unresolvable IP is ABSTAINED on, never guessed and never NULL-pinned.

Env:
  SUPABASE_ACCESS_TOKEN / SUPABASE_PAT   sbp_… PAT (Management API)
  SUPABASE_PROJECT_REF                   default fsldfzlxyavsuwqbceod
  IPLOCATE_API_KEY                       IPLocate API key
  IPLOCATE_DAILY_BUDGET                  max lookups per run (default 900)
"""
from __future__ import annotations

import ipaddress
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
# Cloudflare's WAF in front of api.supabase.com 403s the default Python-urllib UA (edge error 1010);
# send a browser UA (same fix as scripts/deploy/analytics_migrate.py). Without this ip_geo never fills.
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"


class CredentialRejected(RuntimeError):
    """A provider answered 401/403 — the credential is present but expired or revoked.

    Raised for BOTH of this lane's credentials: SUPABASE_ACCESS_TOKEN (Management API) and
    IPLOCATE_API_KEY. `credential` says which, so the operator is told to rotate the right
    one. Deliberately distinct from the neighbouring states: an ABSENT credential means the
    lane was never switched on (clean exit 0), a 429 is a rate limit, and a 5xx means the
    provider is briefly down (retried next tick). This one needs a human, so it is named
    loudly and is never counted as a per-IP failure — a dead credential fails every item
    identically, so counting it per-item reports a successful run that wrote nothing."""

    def __init__(self, code: int, detail: str = "",
                 credential: str = "SUPABASE_ACCESS_TOKEN") -> None:
        self.code = code
        self.detail = detail
        self.credential = credential
        super().__init__(f"{credential} was rejected (HTTP {code})")


def _err_body(ex: urllib.error.HTTPError) -> str:
    """Best-effort provider message. urllib discards this by default, which is why 13 days
    of 401s never said whether Supabase or the Cloudflare edge was refusing us."""
    try:
        return ex.read().decode("utf-8", "replace")[:200]
    except Exception:
        return ""


def _sql(query: str):
    """Run SQL via the Supabase Management API; returns a list of row dicts (or []).

    A 401/403 is re-raised as CredentialRejected so callers can tell "our token is dead"
    apart from "this one statement failed". Every other HTTPError propagates unchanged."""
    req = urllib.request.Request(
        QUERY_URL,
        data=json.dumps({"query": query}).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json", "User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as ex:
        if ex.code in (401, 403):
            raise CredentialRejected(ex.code, _err_body(ex)) from ex
        raise
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


def _routable(ip: str) -> bool:
    """True only for a globally-routable public address (v4 or v6). Private / loopback /
    link-local / reserved / multicast / unspecified addresses are never geolocatable —
    skip them so they neither burn the IPLocate budget nor land a permanent NULL-geo row
    that the `not in ip_geo` filter in pending_ips() would exclude from every future run.
    Handles IPv6 too (the Cloudflare-fronted Terminal collector can store a v6 client IP)."""
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def _resolved(g: dict) -> bool:
    """True if IPLocate actually placed the IP (has at least a country or city). A 200 with
    neither means it couldn't locate it — we deliberately DON'T upsert those, so the IP stays
    pending and a later run can retry, instead of writing a permanent NULL row that would
    never be revisited."""
    return bool(g.get("country_code") or g.get("country") or g.get("city"))


def iplocate(ip: str) -> dict:
    """Look one IP up via IPLocate. Query-param auth (verified working) so no header ambiguity."""
    url = (
        f"https://iplocate.io/api/lookup/{urllib.parse.quote(ip)}"
        f"?apikey={urllib.parse.quote(IPLOCATE_KEY)}"
    )
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "mastermind-geo-enrich/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as ex:
        if ex.code in (401, 403):
            # A dead IPLocate key fails EVERY lookup identically. Left as a per-IP `failed`
            # it would report a successful run that enriched nothing — the same false green
            # the Supabase side of this boundary had. 429 stays a rate limit, not a rejection.
            raise CredentialRejected(ex.code, _err_body(ex), credential="IPLOCATE_API_KEY") from ex
        raise


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


def _credential_fault(ex: CredentialRejected, **counts) -> dict:
    """Terminal, named summary for a rejected credential — never ok, never swallowed."""
    return {"ok": False, "reason": "credential_rejected", "code": ex.code,
            "credential": ex.credential, "detail": ex.detail, **counts}


def run(budget: int = DEFAULT_BUDGET) -> dict:
    """Enrich up to `budget` pending IPs. Returns a summary dict (safe to call from the admin)."""
    if not PAT or not IPLOCATE_KEY:
        return {"ok": False, "reason": "missing SUPABASE_ACCESS_TOKEN or IPLOCATE_API_KEY"}
    try:
        ips = pending_ips(budget)
    except CredentialRejected as ex:
        # The READ plane rejected the PAT. This is exactly where the lane died at
        # 2026-08-13T13:08Z (30 days after the token was minted) and stayed dead.
        return _credential_fault(ex, pending=0, enriched=0, failed=0, skipped=0,
                                 unresolved=0, rate_limited=False)
    done, failed, skipped, unresolved = 0, 0, 0, 0
    for ip in ips:
        if not _routable(ip):
            skipped += 1  # private/reserved/bogon — never spend a lookup on it
            continue
        try:
            g = iplocate(ip)
            if not _resolved(g):
                unresolved += 1  # located nothing; leave pending for a later retry, don't NULL-pin it
                continue
            upsert(ip, g)
            done += 1
        except CredentialRejected as ex:
            # MUST precede `except Exception` (CredentialRejected is a RuntimeError). A dead
            # PAT fails every remaining upsert identically; counting those as per-IP `failed`
            # returned ok=True -> exit 0, painting the lane GREEN having written nothing.
            return _credential_fault(ex, pending=len(ips), enriched=done, failed=failed,
                                     skipped=skipped, unresolved=unresolved, rate_limited=False)
        except urllib.error.HTTPError as ex:
            if ex.code == 429:
                return {"ok": True, "pending": len(ips), "enriched": done, "failed": failed,
                        "skipped": skipped, "unresolved": unresolved, "rate_limited": True}
            failed += 1
        except Exception:
            failed += 1
        time.sleep(0.05)  # be gentle on IPLocate
    return {"ok": True, "pending": len(ips), "enriched": done, "failed": failed,
            "skipped": skipped, "unresolved": unresolved, "rate_limited": False}


def main() -> int:
    res = run(DEFAULT_BUDGET)
    print(f"geo_enrich: {json.dumps(res)}")
    if res.get("ok"):
        return 0
    reason = str(res.get("reason", ""))
    # A not-yet-configured lane (missing secret) is a clean skip, not a failure — exiting
    # non-zero here turns an unset-secret state into a persistent red X on the every-30-min
    # cron. Only genuine runtime failures should trip the run.
    if reason.startswith("missing "):
        print("geo_enrich: skipping (not configured) — set SUPABASE_ACCESS_TOKEN + IPLOCATE_API_KEY to enable")
        return 0
    if reason == "credential_rejected":
        # A CONFIGURED lane whose credential died IS broken, so it stays red — going green
        # here would serve stale geography behind a passing badge. But it must SAY so: this
        # lane sat red for 13 days behind a bare urllib traceback that named neither the
        # credential nor the remedy. The annotation must START the line and be a bare print
        # — a logger prefix makes GitHub drop it silently.
        cred = str(res.get("credential") or "SUPABASE_ACCESS_TOKEN")
        hint = (" Supabase Management API PATs expire ~30 days after they are minted."
                if cred == "SUPABASE_ACCESS_TOKEN" else "")
        print(
            f"::error title=geo_enrich_credential::{cred} was rejected by its provider "
            f"(HTTP {res.get('code')}) — the key is present but expired or revoked. ip_geo "
            f"enrichment is FROZEN: analytics events keep arriving while their geography goes "
            f"stale. Rotate the {cred} repo secret.{hint}",
            flush=True,
        )
        detail = str(res.get("detail") or "").replace("\n", " ").replace("\r", " ").strip()
        if detail:
            print(f"geo_enrich: provider said: {detail}", flush=True)
        return 3
    return 2


if __name__ == "__main__":
    sys.exit(main())
