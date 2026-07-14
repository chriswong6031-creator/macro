"""First-party analytics reader — the self-hosted alternative to Umami/GA4.

Reads the shared Supabase analytics tables (analytics_events, search_events, ip_geo — created by
the Terminal repo's supabase/migrations/0004_analytics.sql + 0003_search_events.sql) through the
Management API SQL endpoint, exactly like users.py: a read-only SELECT with the sbp_… PAT, no
service_role JWT stored, nothing exposed to the browser. All SQL is static text authored here; the
only interpolated values are int-clamped (days/limit) or allowlist-validated ids (session/visitor),
so there is no injection surface.

Surfaces (all return the {ok, …} / {ok:False, reason} envelope the SPA expects):
  overview   headline counts + by-site split + daily series
  pages      top pages/paths by views + unique visitors
  geo        visitor map — by country and by city (lat/lon for plotting)
  sessions   recent sessions (one row per session_id)
  session    the ordered event path of ONE session (the 1:1 replay)
  flow       navigation patterns — from→to path-pair counts (window over each session)
  terminal   Terminal usage — top tickers SEARCHED (search_events) and VIEWED (ticker_view)
  visitor    identity stitch — one visitor's sessions/IPs/fingerprints + linked visitor_ids
  realtime   distinct visitors/sessions active in the last 5 minutes
  geo_enrich_now  on-demand IPLocate backfill (subprocesses scripts/geo_enrich.py)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from . import settings

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

_API = "https://api.supabase.com/v1"
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")  # session_id / visitor_id shape (uuid or 's-…')


def status() -> dict:
    pat = settings.supabase_pat()
    configured = bool(pat and requests)
    reason = None
    if not configured:
        reason = ("requests not installed" if not requests else
                  "SUPABASE_ACCESS_TOKEN (sbp_… personal access token) not set")
    return {
        "configured": configured,
        "project_ref": settings.supabase_project_ref(),
        "reason": reason,
        "setup_steps": [
            "Apply supabase/migrations/0004_analytics.sql (+ 0003) to the Supabase project.",
            "Set SUPABASE_ACCESS_TOKEN (sbp_… PAT) in the admin service env.",
            "Add the tracker: templates/theme.js beacon (macro) + the Terminal <Tracker/> ship live.",
        ],
    }


def _query(sql: str):
    pat = settings.supabase_pat()
    if not (pat and requests):
        return None
    ref = settings.supabase_project_ref()
    r = requests.post(
        f"{_API}/projects/{ref}/database/query",
        headers={"Authorization": f"Bearer {pat}", "Content-Type": "application/json"},
        json={"query": sql}, timeout=20)
    if not (200 <= r.status_code < 300):   # the query endpoint answers 201 on success
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def _days(v, default: int = 7) -> int:
    try:
        return max(1, min(365, int(v)))
    except (TypeError, ValueError):
        return default


def _limit(v, default: int = 50, hi: int = 500) -> int:
    try:
        return max(1, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _guard(fn):
    if not status()["configured"]:
        return {"ok": False, **status()}
    try:
        return {"ok": True, **fn()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# ---------- surfaces ----------
def overview(days=7) -> dict:
    d = _days(days)
    def run():
        win = (_query(
            "select count(*)::int as events, "
            "count(distinct visitor_id)::int as visitors, "
            "count(distinct session_id)::int as sessions, "
            "count(*) filter (where type in ('pageview','route'))::int as pageviews, "
            "count(*) filter (where type='ticker_view')::int as ticker_views, "
            "count(*) filter (where type='search')::int as searches "
            f"from public.analytics_events where created_at > now() - interval '{d} days'") or [{}])[0]
        alltime = (_query("select count(*)::int as events, count(distinct visitor_id)::int as visitors "
                          "from public.analytics_events") or [{}])[0]
        by_site = _query(
            "select site, count(*)::int as events, count(distinct visitor_id)::int as visitors "
            f"from public.analytics_events where created_at > now() - interval '{d} days' "
            "group by site order by events desc") or []
        daily = _query(
            "select to_char(date_trunc('day', created_at),'YYYY-MM-DD') as day, "
            "count(distinct visitor_id)::int as visitors, count(*)::int as events "
            f"from public.analytics_events where created_at > now() - interval '{d} days' "
            "group by 1 order by 1") or []
        return {"days": d, "window": win, "alltime": alltime, "by_site": by_site, "daily": daily}
    return _guard(run)


def pages(days=7, limit=25) -> dict:
    d, n = _days(days), _limit(limit, 25)
    def run():
        rows = _query(
            "select site, coalesce(path,'(none)') as path, "
            "count(*) filter (where type in ('pageview','route'))::int as views, "
            "count(distinct visitor_id)::int as visitors, "
            "round(avg(dwell_ms) filter (where dwell_ms is not null))::int as avg_dwell_ms "
            f"from public.analytics_events where created_at > now() - interval '{d} days' "
            "group by 1,2 order by views desc nulls last "
            f"limit {n}") or []
        return {"days": d, "pages": rows}
    return _guard(run)


def geo(days=30, limit=200) -> dict:
    d, n = _days(days, 30), _limit(limit, 200)
    def run():
        countries = _query(
            "select coalesce(g.country,'(unknown)') as country, g.country_code, "
            "count(distinct e.visitor_id)::int as visitors, count(*)::int as events "
            "from public.analytics_events e left join public.ip_geo g on g.ip = e.ip "
            f"where e.created_at > now() - interval '{d} days' "
            "group by 1,2 order by visitors desc nulls last") or []
        cities = _query(
            "select g.city, g.region, g.country_code, g.lat, g.lon, "
            "count(distinct e.visitor_id)::int as visitors "
            "from public.analytics_events e join public.ip_geo g on g.ip = e.ip "
            f"where e.created_at > now() - interval '{d} days' and g.city is not null "
            "group by 1,2,3,4,5 order by visitors desc "
            f"limit {n}") or []
        return {"days": d, "countries": countries, "cities": cities}
    return _guard(run)


def sessions(limit=40) -> dict:
    n = _limit(limit, 40, 200)
    def run():
        rows = _query(
            "select s.session_id, s.visitor_id, s.site, s.events, s.pages, "
            "to_char(s.started,'YYYY-MM-DD HH24:MI') as started, "
            "round(extract(epoch from (s.ended - s.started)))::int as duration_s, "
            "g.city, g.country_code "
            "from (select session_id, max(visitor_id) as visitor_id, max(site) as site, "
            "  count(*)::int as events, count(*) filter (where type in ('pageview','route'))::int as pages, "
            "  min(created_at) as started, max(created_at) as ended, "
            "  (array_agg(ip order by created_at))[1] as ip "
            "  from public.analytics_events where session_id is not null "
            "  group by session_id order by max(created_at) desc "
            f"  limit {n}) s "
            "left join public.ip_geo g on g.ip = s.ip "
            "order by s.started desc") or []
        return {"sessions": rows}
    return _guard(run)


def session(session_id: str) -> dict:
    if not session_id or not _ID_RE.match(session_id):
        return {"ok": False, "reason": "invalid session id"}
    def run():
        path = _query(
            "select type, coalesce(path,'') as path, ticker, dwell_ms, scroll, "
            "to_char(created_at,'HH24:MI:SS') as t, meta "
            f"from public.analytics_events where session_id = '{session_id}' "
            "order by id asc limit 1000") or []
        head = (_query(
            "select max(visitor_id) as visitor_id, max(site) as site, "
            "max(user_id::text) as user_id, min(created_at) as started, "
            "(array_agg(ip order by created_at))[1] as ip, (array_agg(fp) filter (where fp is not null))[1] as fp "
            f"from public.analytics_events where session_id = '{session_id}'") or [{}])[0]
        return {"session_id": session_id, "head": head, "path": path}
    return _guard(run)


def flow(days=7, limit=40) -> dict:
    d, n = _days(days), _limit(limit, 40, 200)
    def run():
        rows = _query(
            "with ev as (select session_id, path, "
            "  lag(path) over (partition by session_id order by id) as prev "
            "  from public.analytics_events "
            f"  where type in ('pageview','route') and path is not null "
            f"    and created_at > now() - interval '{d} days') "
            "select prev as from_path, path as to_path, count(*)::int as n "
            "from ev where prev is not null and prev <> path "
            "group by 1,2 order by n desc "
            f"limit {n}") or []
        return {"days": d, "edges": rows}
    return _guard(run)


def terminal(days=7, limit=25) -> dict:
    d, n = _days(days), _limit(limit, 25)
    def run():
        searches = _query(
            "select symbol as ticker, count(*)::int as searches, "
            "count(distinct coalesce(user_id::text, anon_id, ip))::int as visitors "
            f"from public.search_events where created_at > now() - interval '{d} days' "
            f"group by 1 order by searches desc limit {n}") or []
        views = _query(
            "select ticker, count(*)::int as views, count(distinct visitor_id)::int as visitors "
            "from public.analytics_events where type='ticker_view' and ticker is not null "
            f"and created_at > now() - interval '{d} days' "
            f"group by 1 order by views desc limit {n}") or []
        totals = (_query(
            "select (select count(*)::int from public.search_events "
            f"  where created_at > now() - interval '{d} days') as search_total, "
            "(select count(*)::int from public.analytics_events where type='ticker_view' "
            f"  and created_at > now() - interval '{d} days') as view_total") or [{}])[0]
        return {"days": d, "top_searches": searches, "top_views": views, "totals": totals}
    return _guard(run)


def visitor(visitor_id: str) -> dict:
    if not visitor_id or not _ID_RE.match(visitor_id):
        return {"ok": False, "reason": "invalid visitor id"}
    v = visitor_id
    def run():
        profile = (_query(
            "select min(created_at) as first_seen, max(created_at) as last_seen, "
            "count(*)::int as events, count(distinct session_id)::int as sessions, "
            "count(distinct ip)::int as ips, count(distinct fp)::int as fingerprints, "
            "max(user_id::text) as user_id "
            f"from public.analytics_events where visitor_id = '{v}'") or [{}])[0]
        ips = _query(
            "select e.ip, g.city, g.region, g.country_code, g.asn, g.org, "
            "g.is_vpn, g.is_proxy, g.is_hosting, count(*)::int as events "
            "from public.analytics_events e left join public.ip_geo g on g.ip = e.ip "
            f"where e.visitor_id = '{v}' group by 1,2,3,4,5,6,7,8,9 order by events desc") or []
        # same human, different cookie/IP: visitors that share a fingerprint or an IP with this one
        linked = _query(
            "select e2.visitor_id, count(*)::int as shared_events, "
            "max(case when e2.fp = e1fp then 1 else 0 end) as via_fp, "
            "max(case when e2.ip = e1ip then 1 else 0 end) as via_ip "
            "from public.analytics_events e2 "
            "join (select distinct fp as e1fp, ip as e1ip from public.analytics_events "
            f"      where visitor_id = '{v}') k "
            "  on (e2.fp = k.e1fp and e2.fp is not null) "
            "  or (e2.ip = k.e1ip and e2.ip is not null and e2.ip <> 'unknown') "
            f"where e2.visitor_id <> '{v}' group by 1 order by shared_events desc limit 50") or []
        recent = _query(
            "select type, coalesce(path,'') as path, ticker, "
            "to_char(created_at,'YYYY-MM-DD HH24:MI') as t "
            f"from public.analytics_events where visitor_id = '{v}' order by id desc limit 40") or []
        return {"visitor_id": v, "profile": profile, "ips": ips, "linked": linked, "recent": recent}
    return _guard(run)


def realtime() -> dict:
    def run():
        now = (_query(
            "select count(distinct visitor_id)::int as visitors, "
            "count(distinct session_id)::int as sessions, count(*)::int as events "
            "from public.analytics_events where created_at > now() - interval '5 minutes'") or [{}])[0]
        recent = _query(
            "select e.type, e.site, coalesce(e.path,'') as path, e.ticker, "
            "to_char(e.created_at,'HH24:MI:SS') as t, g.city, g.country_code "
            "from public.analytics_events e left join public.ip_geo g on g.ip = e.ip "
            "where e.created_at > now() - interval '15 minutes' order by e.id desc limit 30") or []
        return {"active": now, "recent": recent}
    return _guard(run)


def geo_enrich_now(budget: int = 300) -> dict:
    """On-demand IPLocate backfill: subprocess scripts/geo_enrich.py (needs IPLOCATE_API_KEY in the
    admin service env). Best-effort; the scheduled Action is the primary mechanism."""
    repo = Path(__file__).resolve().parent.parent   # /opt/macro
    script = repo / "scripts" / "geo_enrich.py"
    if not script.exists():
        return {"ok": False, "reason": "scripts/geo_enrich.py not found"}
    try:
        env = dict(os.environ)
        env["IPLOCATE_DAILY_BUDGET"] = str(max(1, min(1000, int(budget))))
        out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                             timeout=150, env=env)
        return {"ok": out.returncode == 0, "output": (out.stdout or out.stderr or "").strip()[-600:]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": str(e)}
