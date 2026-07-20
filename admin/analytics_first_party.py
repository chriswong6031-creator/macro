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

import json
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

# Canonical-identity CTE — built by `_cte(include_ident=True)`. Maps each mm_aid cookie to the
# Supabase user uuid it belongs to, EXCLUDING cookies signed into by 2+ accounts (ambiguous
# shared/kiosk devices — never merged). Prepend to a query that aliases analytics_events as `e`
# and left-joins `ident i`; then _CANON_VISITORS counts PEOPLE (a signed-in user's devices
# collapse to one), so the headline counts reconcile with the merged 'Frequent visitors' list.
_CANON_VISITORS = "count(distinct coalesce(i.uid, e.visitor_id))::int as visitors"

# ── Operator self-exclusion ────────────────────────────────────────────────────
# Hide the operator's own sessions/visitors from every analytics surface. Driven by
# admin/analytics_exclusions.json (registered emails + home locations). See that file's
# _comment. All matching is done in SQL via the `excluded` CTE (below); the config values
# are the ONLY interpolated strings and every one goes through _sql_str (quotes doubled)
# on top of a JSON-typed load, so there is no injection surface.
# Path is env-overridable (same idiom as site_gate's SITE_GATE_STATE) so the operator can
# keep the hide-list in an untracked server file (e.g. /var/lib/macro-admin/…) instead of
# the committed default, keeping personal emails out of git history.
_EXCL_PATH = Path(os.environ.get(
    "ANALYTICS_EXCLUSIONS",
    str(Path(__file__).resolve().parent / "analytics_exclusions.json")))
# Non-identifying IPs — never used to LINK cookies (loopback/tunnel traffic is shared by
# many unrelated visitors, so linking on it would falsely merge/over-hide them).
_NON_ID_IPS = ("'unknown'", "'::1'", "'127.0.0.1'", "'localhost'")


def _sql_str(s) -> str:
    """A single-quoted SQL string literal with embedded quotes doubled (raw-SQL endpoint)."""
    return "'" + str(s).replace("'", "''") + "'"


def _routable(col: str) -> str:
    """SQL predicate: `col` is a real, identifying IP (not null, not loopback/unknown)."""
    return f"{col} is not null and {col} not in ({','.join(_NON_ID_IPS)})"


def _sanitize_q(v, maxlen: int = 64) -> str:
    """Free-text table filter → a safe fragment. Allows only letters, digits and the
    characters that appear in emails / UUIDs / IPs (@ . - : space). Strips quotes, `%`
    and `_` so the value is safe to inline inside an ILIKE pattern (no injection, no
    stray wildcards). Returns '' when nothing usable remains."""
    return re.sub(r"[^A-Za-z0-9@.\-: ]", "", str(v or ""))[:maxlen].strip()


def _load_exclusions() -> dict:
    """Read the self-exclusion config. Missing/malformed → empty (nothing hidden)."""
    try:
        cfg = json.loads(_EXCL_PATH.read_text())
    except Exception:  # noqa: BLE001 — never break analytics on a bad config file
        return {"emails": [], "locations": []}
    emails = [str(e).strip().lower() for e in (cfg.get("emails") or []) if str(e).strip()]
    locations = [l for l in (cfg.get("locations") or []) if isinstance(l, dict)]
    return {"emails": emails, "locations": locations}


def _excluded_cte() -> str:
    """CTE bodies (excl_users, excl_geo_ips, excl_seed, excl_link, excluded) — always
    syntactically valid regardless of config. `excluded` is the set of visitor_id cookies
    to hide: the operator's own (via registered email or a home-location IP) PLUS the
    cookies linked to them by shared device fingerprint or routable IP."""
    cfg = _load_exclusions()
    if cfg["emails"]:
        emails = ",".join(_sql_str(e) for e in cfg["emails"])
        users_body = f"select id from auth.users where lower(email) in ({emails})"
    else:
        users_body = "select id from auth.users where false"
    preds = []
    for loc in cfg["locations"]:
        terms = []
        if loc.get("city"):
            terms.append(f"lower(g.city) = lower({_sql_str(loc['city'])})")
        if loc.get("region"):
            terms.append(f"lower(g.region) = lower({_sql_str(loc['region'])})")
        if loc.get("country_code"):
            terms.append(f"upper(g.country_code) = upper({_sql_str(loc['country_code'])})")
        if terms:
            preds.append("(" + " and ".join(terms) + ")")
    geo_body = (f"select ip from public.ip_geo g where {' or '.join(preds)}"
                if preds else "select ip from public.ip_geo where false")
    return (
        f"excl_users as ({users_body}), "
        f"excl_geo_ips as ({geo_body}), "
        "excl_seed as (select distinct e.visitor_id from public.analytics_events e "
        "  where e.visitor_id is not null and (e.user_id in (select id from excl_users) "
        "  or e.ip in (select ip from excl_geo_ips))), "
        "excl_link as (select distinct e2.visitor_id from public.analytics_events e2 "
        "  join (select distinct fp, ip from public.analytics_events "
        "        where visitor_id in (select visitor_id from excl_seed)) k "
        "    on (e2.fp = k.fp and e2.fp is not null) "
        f"    or (e2.ip = k.ip and {_routable('e2.ip')} and {_routable('k.ip')}) "
        "  where e2.visitor_id is not null), "
        "excluded as (select visitor_id from excl_seed "
        "             union select visitor_id from excl_link)"
    )


def _cte(include_ident: bool = False) -> str:
    """Full `with …` prefix: the excluded-visitor chain, optionally preceded by `ident`."""
    parts = []
    if include_ident:
        parts.append(
            "ident as (select visitor_id, max(user_id::text) as uid "
            "from public.analytics_events where visitor_id is not null and user_id is not null "
            "group by visitor_id having count(distinct user_id) = 1)")
    parts.append(_excluded_cte())
    return "with " + ", ".join(parts) + " "


def _not_excluded(alias: str = "e") -> str:
    """WHERE fragment that drops the operator's hidden cookies. `alias` = table alias
    holding visitor_id ('' for an unaliased table). Null visitor_id is KEPT (it can't be a
    hidden cookie, and a bare `not in` would drop it via SQL three-valued logic)."""
    col = f"{alias}.visitor_id" if alias else "visitor_id"
    return f"({col} is null or {col} not in (select visitor_id from excluded))"


def _not_excluded_search() -> str:
    """WHERE fragment for public.search_events (no visitor_id column): drop the operator's
    rows by anon cookie, registered user, or home-location IP. Each arm keeps NULLs."""
    return ("(anon_id is null or anon_id not in (select visitor_id from excluded)) "
            "and (user_id is null or user_id not in (select id from excl_users)) "
            "and (ip is null or ip not in (select ip from excl_geo_ips))")


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
        # 'visitors' counts PEOPLE (canonical identity), not raw cookies. The operator's own
        # hidden cookies (excluded CTE) are dropped so headline counts match the tables below.
        win = (_query(_cte(include_ident=True) +
            "select count(*)::int as events, "
            f"{_CANON_VISITORS}, "
            "count(distinct e.session_id)::int as sessions, "
            "count(*) filter (where e.type in ('pageview','route'))::int as pageviews, "
            "count(*) filter (where e.type='ticker_view')::int as ticker_views, "
            "count(*) filter (where e.type='search')::int as searches "
            "from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"where e.created_at > now() - interval '{d} days' and {_not_excluded('e')}") or [{}])[0]
        alltime = (_query(_cte(include_ident=True) +
            f"select count(*)::int as events, {_CANON_VISITORS} "
            "from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"where {_not_excluded('e')}") or [{}])[0]
        by_site = _query(_cte(include_ident=True) +
            f"select e.site, count(*)::int as events, {_CANON_VISITORS} "
            "from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"where e.created_at > now() - interval '{d} days' and {_not_excluded('e')} "
            "group by e.site order by events desc") or []
        daily = _query(_cte(include_ident=True) +
            "select to_char(date_trunc('day', e.created_at),'YYYY-MM-DD') as day, "
            f"{_CANON_VISITORS}, count(*)::int as events "
            "from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"where e.created_at > now() - interval '{d} days' and {_not_excluded('e')} "
            "group by 1 order by 1") or []
        return {"days": d, "window": win, "alltime": alltime, "by_site": by_site, "daily": daily}
    return _guard(run)


def pages(days=7, limit=25) -> dict:
    d, n = _days(days), _limit(limit, 25)
    def run():
        rows = _query(_cte() +
            "select site, coalesce(path,'(none)') as path, "
            "count(*) filter (where type in ('pageview','route'))::int as views, "
            "count(distinct visitor_id)::int as visitors, "
            "round(avg(dwell_ms) filter (where dwell_ms is not null))::int as avg_dwell_ms "
            f"from public.analytics_events where created_at > now() - interval '{d} days' "
            f"and {_not_excluded('')} "
            "group by 1,2 order by views desc nulls last "
            f"limit {n}") or []
        return {"days": d, "pages": rows}
    return _guard(run)


def geo(days=30, limit=200) -> dict:
    d, n = _days(days, 30), _limit(limit, 200)
    def run():
        countries = _query(_cte() +
            "select coalesce(g.country,'(unknown)') as country, g.country_code, "
            "count(distinct e.visitor_id)::int as visitors, count(*)::int as events "
            "from public.analytics_events e left join public.ip_geo g on g.ip = e.ip "
            f"where e.created_at > now() - interval '{d} days' and {_not_excluded('e')} "
            "group by 1,2 order by visitors desc nulls last") or []
        cities = _query(_cte() +
            "select g.city, g.region, g.country_code, g.lat, g.lon, "
            "count(distinct e.visitor_id)::int as visitors "
            "from public.analytics_events e join public.ip_geo g on g.ip = e.ip "
            f"where e.created_at > now() - interval '{d} days' and g.city is not null "
            f"and {_not_excluded('e')} "
            "group by 1,2,3,4,5 order by visitors desc "
            f"limit {n}") or []
        return {"days": d, "countries": countries, "cities": cities}
    return _guard(run)


def sessions(limit=100, q="") -> dict:
    n = _limit(limit, 100, 2000)
    qq = _sanitize_q(q)
    # Free-text filter (visitor id / IP / site / city / region / country). Applied AFTER the
    # geo join and BEFORE the limit so it searches the full history, not just the newest n.
    where = ""
    if qq:
        cols = ("s.visitor_id", "s.ip", "s.site", "g.city", "g.region", "g.country_code")
        where = "where (" + " or ".join(f"{c} ilike '%{qq}%'" for c in cols) + ") "
    def run():
        rows = _query(_cte() +
            "select s.session_id, s.visitor_id, s.site, s.events, s.pages, "
            "to_char(s.started,'YYYY-MM-DD HH24:MI') as started, "
            "round(extract(epoch from (s.ended - s.started)))::int as duration_s, "
            "s.ip, g.city, g.region, g.country_code "
            "from (select session_id, max(visitor_id) as visitor_id, max(site) as site, "
            "  count(*)::int as events, count(*) filter (where type in ('pageview','route'))::int as pages, "
            "  min(created_at) as started, max(created_at) as ended, "
            "  (array_agg(ip order by created_at))[1] as ip "
            f"  from public.analytics_events where session_id is not null and {_not_excluded('')} "
            "  group by session_id) s "
            "left join public.ip_geo g on g.ip = s.ip "
            f"{where}"
            f"order by s.started desc limit {n}") or []
        return {"sessions": rows, "q": qq}
    return _guard(run)


def visitors(limit=250, q="") -> dict:
    """One row per PERSON — the 'Frequent Visitors' list.

    Identity resolution: any anonymous cookie (mm_aid) that ever appears on a signed-in
    event is merged under that user, so all of one person's cookies/devices collapse into
    a single row keyed by their Supabase user id and labelled with their email. Purely
    anonymous visitors stay keyed by their mm_aid. `identities` = how many cookies merged.
    Ordered by session count."""
    n = _limit(limit, 250, 2000)
    qq = _sanitize_q(q)
    # Free-text filter (email / visitor id / IP / city / region / country). Applied AFTER the
    # user+geo joins and BEFORE the limit so it searches the whole roster, not just the top n.
    where = ""
    if qq:
        cols = ("u.email", "v.canon", "v.last_ip", "g.city", "g.region", "g.country", "g.country_code")
        where = "where (" + " or ".join(f"{c} ilike '%{qq}%'" for c in cols) + ") "
    def run():
        rows = _query(
            # ident: each mm_aid -> the user uuid it belongs to (if ever authenticated).
            # A cookie signed into by 2+ DIFFERENT accounts (shared/kiosk device) is
            # AMBIGUOUS — excluded from the auto-merge so one person's activity is never
            # silently reassigned to another; those events stay under the cookie.
            "with ident as ("
            "  select visitor_id, max(user_id::text) as uid "
            "  from public.analytics_events "
            "  where visitor_id is not null and user_id is not null "
            "  group by visitor_id having count(distinct user_id) = 1"
            "), " + _excluded_cte() +
            # ev: every (non-hidden) event tagged with its canonical identity (uid if known, else mm_aid)
            ", ev as ("
            "  select e.session_id, e.ip, e.created_at, e.visitor_id, i.uid, "
            "    coalesce(i.uid, e.visitor_id) as canon "
            "  from public.analytics_events e "
            "  left join ident i on i.visitor_id = e.visitor_id "
            f"  where e.visitor_id is not null and {_not_excluded('e')}"
            ") "
            "select v.canon as visitor_id, (v.uid is not null) as is_user, u.email, "
            "  v.events, v.sessions, v.identities, v.ips, v.last_ip, "
            "  to_char(v.first_seen,'YYYY-MM-DD HH24:MI') as first_seen, "
            "  to_char(v.last_seen,'YYYY-MM-DD HH24:MI') as last_seen, "
            "  g.city, g.region, g.country, g.country_code, g.is_vpn "
            "from (select canon, max(uid) as uid, count(*)::int as events, "
            "  count(distinct session_id)::int as sessions, "
            "  count(distinct visitor_id)::int as identities, count(distinct ip)::int as ips, "
            "  min(created_at) as first_seen, max(created_at) as last_seen, "
            "  (array_agg(ip order by created_at desc))[1] as last_ip "
            "  from ev group by canon) v "
            "left join auth.users u on u.id::text = v.uid "
            "left join public.ip_geo g on g.ip = v.last_ip "
            f"{where}"
            f"order by v.sessions desc, v.last_seen desc limit {n}") or []
        return {"visitors": rows, "q": qq}
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
            "with " + _excluded_cte() + ", ev as (select session_id, path, "
            "  lag(path) over (partition by session_id order by id) as prev "
            "  from public.analytics_events "
            f"  where type in ('pageview','route') and path is not null and {_not_excluded('')} "
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
        searches = _query(_cte() +
            "select symbol as ticker, count(*)::int as searches, "
            "count(distinct coalesce(user_id::text, anon_id, ip))::int as visitors "
            f"from public.search_events where created_at > now() - interval '{d} days' "
            f"and {_not_excluded_search()} "
            f"group by 1 order by searches desc limit {n}") or []
        views = _query(_cte() +
            "select ticker, count(*)::int as views, count(distinct visitor_id)::int as visitors "
            "from public.analytics_events where type='ticker_view' and ticker is not null "
            f"and created_at > now() - interval '{d} days' and {_not_excluded('')} "
            f"group by 1 order by views desc limit {n}") or []
        totals = (_query(_cte() +
            "select (select count(*)::int from public.search_events "
            f"  where created_at > now() - interval '{d} days' and {_not_excluded_search()}) as search_total, "
            "(select count(*)::int from public.analytics_events where type='ticker_view' "
            f"  and created_at > now() - interval '{d} days' and {_not_excluded('')}) as view_total") or [{}])[0]
        return {"days": d, "top_searches": searches, "top_views": views, "totals": totals}
    return _guard(run)


def visitor(visitor_id: str) -> dict:
    """One person's profile. `visitor_id` is the canonical id from the visitors() list —
    either a Supabase user uuid (a registered person, whose every mm_aid cookie is merged)
    or a bare mm_aid (a purely anonymous visitor). All sub-queries resolve it to the full
    set of that person's cookies via the `myaids` CTE, so a signed-in user's activity across
    every device/cookie shows as one profile."""
    if not visitor_id or not _ID_RE.match(visitor_id):
        return {"ok": False, "reason": "invalid visitor id"}
    v = visitor_id   # _ID_RE-allowlisted ([A-Za-z0-9._:-]{1,64}) — safe to interpolate
    # Prepended to every sub-query: map the canonical id to all mm_aid cookies of the person.
    # If v is a user uuid -> every mm_aid ever seen on one of that user's events; if v is an
    # mm_aid -> just itself (the `union select '{v}'` covers the anonymous case).
    cte = (
        "with ident as ("
        "  select visitor_id, max(user_id::text) as uid from public.analytics_events "
        "  where visitor_id is not null and user_id is not null "
        "  group by visitor_id having count(distinct user_id) = 1"   # drop ambiguous shared cookies
        f"), myaids as (select visitor_id from ident where uid = '{v}' union select '{v}') "
    )
    inaids = "visitor_id in (select visitor_id from myaids)"
    def run():
        profile = (_query(cte +
            "select min(created_at) as first_seen, max(created_at) as last_seen, "
            "count(*)::int as events, count(distinct session_id)::int as sessions, "
            "count(distinct ip)::int as ips, count(distinct fp)::int as fingerprints, "
            "count(distinct visitor_id)::int as identities, max(user_id::text) as user_id "
            f"from public.analytics_events where {inaids}") or [{}])[0]
        er = _query(f"select email from auth.users where id::text = '{v}'") or []
        email = er[0].get("email") if er else None
        ips = _query(cte +
            "select e.ip, g.city, g.region, g.country_code, g.asn, g.org, "
            "g.is_vpn, g.is_proxy, g.is_hosting, count(*)::int as events "
            "from public.analytics_events e left join public.ip_geo g on g.ip = e.ip "
            f"where e.{inaids} group by 1,2,3,4,5,6,7,8,9 order by events desc") or []
        # OTHER anon visitors sharing a fingerprint or IP with this person (not yet merged by login)
        linked = _query(cte +
            "select e2.visitor_id, count(*)::int as shared_events, "
            "max(case when e2.fp = k.e1fp then 1 else 0 end) as via_fp, "
            "max(case when e2.ip = k.e1ip then 1 else 0 end) as via_ip "
            "from public.analytics_events e2 "
            "join (select distinct fp as e1fp, ip as e1ip from public.analytics_events "
            f"      where {inaids}) k "
            "  on (e2.fp = k.e1fp and e2.fp is not null) "
            f"  or (e2.ip = k.e1ip and {_routable('e2.ip')}) "
            "where e2.visitor_id not in (select visitor_id from myaids) "
            "group by 1 order by shared_events desc limit 50") or []
        recent = _query(cte +
            "select type, coalesce(path,'') as path, ticker, "
            "to_char(created_at,'YYYY-MM-DD HH24:MI') as t "
            f"from public.analytics_events where {inaids} order by id desc limit 40") or []
        # tickers this person searched (search_events.anon_id = the mm_aid cookie, OR the
        # signed-in user_id directly — catches searches from a cookie with no beacon rows) + viewed
        searches = _query(cte +
            "select symbol as ticker, count(*)::int as n, "
            "to_char(max(created_at),'YYYY-MM-DD HH24:MI') as last "
            "from public.search_events "
            f"where (anon_id in (select visitor_id from myaids) or user_id::text = '{v}') "
            "group by 1 order by n desc, last desc limit 50") or []
        tickers_viewed = _query(cte +
            "select ticker, count(*)::int as n "
            f"from public.analytics_events where {inaids} and type='ticker_view' and ticker is not null "
            "group by 1 order by n desc limit 50") or []
        return {"visitor_id": v, "email": email, "profile": profile, "ips": ips, "linked": linked,
                "recent": recent, "searches": searches, "tickers_viewed": tickers_viewed}
    return _guard(run)


def realtime() -> dict:
    def run():
        now = (_query(_cte() +
            "select count(distinct visitor_id)::int as visitors, "
            "count(distinct session_id)::int as sessions, count(*)::int as events "
            "from public.analytics_events where created_at > now() - interval '5 minutes' "
            f"and {_not_excluded('')}") or [{}])[0]
        recent = _query(_cte() +
            "select e.type, e.site, coalesce(e.path,'') as path, e.ticker, "
            "to_char(e.created_at,'HH24:MI:SS') as t, g.city, g.country_code "
            "from public.analytics_events e left join public.ip_geo g on g.ip = e.ip "
            f"where e.created_at > now() - interval '15 minutes' and {_not_excluded('e')} "
            "order by e.id desc limit 30") or []
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
