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
  sessions   recent VISITS (per-tab/per-origin session_ids stitched — see _visit_break)
  session    the ordered event path of ONE visit (the 1:1 replay)
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
from datetime import datetime
from pathlib import Path

from . import settings, users

try:
    from zoneinfo import ZoneInfo
except Exception:  # noqa: BLE001 — py<3.9 / missing tzdata
    ZoneInfo = None  # type: ignore

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

_API = "https://api.supabase.com/v1"
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")  # session_id / visitor_id shape (uuid or 's-…')

# ── Display timezone ───────────────────────────────────────────────────────────
# analytics_events.created_at is timestamptz and Postgres renders it in the SESSION zone
# (UTC on Supabase), so every panel timestamp used to read as UTC while the operator reads
# it as a wall clock. All formatting now goes through _lt(): an `at time zone` conversion to
# the operator's zone. A named zone (not a fixed -08:00) so PST/PDT switch on their own —
# `America/Los_Angeles` IS "PST time" in the sense meant, correct year-round. Day buckets in
# the overview series are truncated AFTER the conversion, so a "day" is a local midnight-to-
# midnight day. Env-overridable for a future operator in another zone.
_TZ = os.environ.get("ANALYTICS_TZ", "America/Los_Angeles")
_TZ_SQL = "'" + re.sub(r"[^A-Za-z0-9_/+-]", "", _TZ) + "'"

# ── Visit stitching ────────────────────────────────────────────────────────────
# The tracker's session_id lives in sessionStorage, so it is per TAB *and* per ORIGIN: one
# person reading macro, hopping to the Terminal (app.mastermind-x.com — a different origin,
# hence a different sessionStorage) and coming back files THREE session rows for what is
# plainly one sitting. A visit re-joins them: order a person's events (login-merged identity
# where known, else the mm_aid cookie) and start a new visit only after _VISIT_GAP_MIN of
# silence — the same 30-minute idle rule GA/Plausible use, and the same one the client-side
# sid rotation already uses, just applied across tabs and origins instead of within one.
_VISIT_GAP_MIN = 30


def _tz_label() -> str:
    """Short zone abbreviation for the UI ('PST' / 'PDT'); falls back to the zone name."""
    if ZoneInfo is None:
        return _TZ
    try:
        return datetime.now(ZoneInfo(_TZ)).strftime("%Z") or _TZ
    except Exception:  # noqa: BLE001
        return _TZ


def _lt(col: str) -> str:
    """`col` (a timestamptz expression) rendered in the operator's display timezone."""
    return f"({col} at time zone {_TZ_SQL})"


def _gap(v, default: int = _VISIT_GAP_MIN) -> int:
    """Idle minutes that end a visit, clamped to [1 minute, 12 hours]."""
    try:
        return max(1, min(720, int(v)))
    except (TypeError, ValueError):
        return default


def _visit_break(gap: int, part: str | None = "canon") -> str:
    """SQL: 1 on the FIRST event of a visit — no predecessor, or `gap`+ minutes of silence.
    Flagging each person's very first row too means `count(*) filter (where b = 1)` is exactly
    the visit count, with no separate "+1 per person" correction. `part=None` for a query
    already narrowed to one person. Both callers wrap the source in a subquery first, so
    `canon` is a real column here (a window function cannot see a sibling SELECT alias)."""
    over = f"over ({f'partition by {part} ' if part else ''}order by created_at, id)"
    return (f"case when lag(created_at) {over} is null "
            f"or created_at - lag(created_at) {over} > interval '{int(gap)} minutes' "
            "then 1 else 0 end")


def _visit_no(part: str | None = "canon") -> str:
    """SQL: running visit number within a person — a running sum of _visit_break's flag."""
    return (f"sum(b) over ({f'partition by {part} ' if part else ''}"
            "order by created_at, id rows unbounded preceding)")

# Canonical-identity CTE — built by `_cte(include_ident=True)`. Maps each mm_aid cookie to the
# Supabase user uuid it belongs to, EXCLUDING cookies signed into by 2+ accounts (ambiguous
# shared/kiosk devices — never merged). Prepend to a query that aliases analytics_events as `e`
# and left-joins `ident i`; then _CANON_VISITORS counts PEOPLE (a signed-in user's devices
# collapse to one), so the headline counts reconcile with the merged 'Frequent visitors' list.
_CANON_VISITORS = "count(distinct coalesce(i.uid, e.visitor_id))::int as visitors"

# ── Operator self-exclusion ────────────────────────────────────────────────────
# Hide the operator's own sessions/visitors from every analytics surface. Driven by
# admin/analytics_exclusions.json (registered emails, home locations, IPs, cookie ids)
# PLUS a baked-in loopback rule (below). See that file's _comment. All matching is done in SQL via the `excluded` CTE (below); the config values
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
# Loopback specifically. Both collectors resolve the client IP from the CDN/proxy headers and
# fall back to the socket peer (app/main.py:_mm_client_ip, terminal lib/rateLimit.ts:clientIp),
# and every public request arrives through Caddy with X-Forwarded-For set — so a loopback IP
# can ONLY be a request made ON the box: a `npm run dev` browser, a curl, an agent driving the
# app over a tunnel. That is never a visitor, so it is seeded into `excluded` by default (and
# from there its device-fingerprint siblings are hidden too). Distinct from _NON_ID_IPS: this
# HIDES on a loopback IP, that refuses to LINK on one — a shared 127.0.0.1 must not merge two
# unrelated dev machines, so linking still goes through the fingerprint only.
_LOOPBACK_IPS = ("'::1'", "'127.0.0.1'", "'localhost'")

# ── Crawler / bot detection (default-on; config can extend the patterns) ────────
# A visitor is a bot if ANY holds: its user-agent matches _DEFAULT_BOT_UA, its IP sits in a
# datacenter that is NOT a consumer VPN (is_hosting and not is_vpn — keeps real VPN users),
# the IP's network org matches _DEFAULT_BOT_ORG, the IP's ASN matches _DEFAULT_BOT_ASN, the IP
# is in the config bots.ips list, or its device fingerprint is a FARM fingerprint (see
# _FP_FANOUT).
# Bots are hidden from every surface by default but stay REVEALABLE (include_bots=1) and are
# counted, so detection is transparent and false positives are catchable. Behavioural signals
# (short dwell / bounce) are deliberately NOT used — real humans bounce too.
_DEFAULT_BOT_UA = (
    r"bot|crawl|spider|slurp|scrape|Googlebot|bingbot|DuckDuckBot|Baiduspider|YandexBot|"
    r"facebookexternalhit|meta-externalagent|Applebot|PetalBot|Bytespider|GPTBot|ClaudeBot|"
    r"Claude-Web|anthropic-ai|OAI-SearchBot|CCBot|Amazonbot|SemrushBot|AhrefsBot|DotBot|"
    r"MJ12bot|DataForSeo|python-requests|Go-http-client|node-fetch|axios|libwww|curl/|wget|"
    r"Scrapy|HeadlessChrome|PhantomJS"
)
_DEFAULT_BOT_ORG = (
    r"googlebot|google llc|google cloud|meta platforms|facebook|amazon|amazonaws|aws|"
    r"microsoft|azure|openai|anthropic|bytedance|censys|shodan|internet.?archive|"
    r"digitalocean|linode|hetzner|ovh|scaleway"
)
# ASN match is a belt-and-braces companion to _DEFAULT_BOT_ORG: some crawler/hosting IPs geolocate
# with an org string that doesn't literally contain the vendor name (proxy resellers, regional
# RIR records, etc.), but the ASN never lies. 15169 = Google LLC (Googlebot's home network),
# 396982 = Google Cloud Platform (GCP-hosted crawlers/services — confirmed against a batch of
# "visitor" IPs that were plain GCP traffic recurring in the admin Visitors list, 2026-08-02).
# `g.asn` is stored as returned by IPLocate (e.g. "AS396982" or "396982" depending on vendor
# response shape) so this matches on substring, not an exact cast, to be robust to either.
_DEFAULT_BOT_ASN = r"15169|396982"
# ── Fingerprint-farm detection ─────────────────────────────────────────────────
# A residential-proxy scraper defeats every signal above: it rotates through real consumer
# ISPs (Comcast, BT, Cox — is_hosting false, org clean) and sends an ordinary Chrome UA. What
# it CANNOT hide is that every request comes off the same headless image, so one fingerprint
# turns up under many cookies AND many IPs at once. Requiring BOTH counts is what makes the
# rule safe: a household or office behind one NAT gives many cookies on ONE IP; a roaming
# phone gives ONE cookie across many IPs; only a farm is wide on both axes. On this dataset
# the split is unambiguous — one fp at 74 cookies / 74 IPs across 8 countries (Oxylabs,
# code200, Latitude.sh …, 1 pageview + 1 click each, no dwell), and no real visitor above 1
# cookie. Farms land in `bots`, not `excluded`: hidden from every surface by default, but
# still counted and revealable via 'show bots', so the detection stays auditable.
_FP_FANOUT = 12


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


def _clean_ips(seq) -> list:
    """Keep only plausible IP literals (digits, dots, colons, hex) — belt-and-braces before
    they are single-quoted into SQL. Blanks/garbage dropped."""
    out = []
    for v in (seq or []):
        s = re.sub(r"[^0-9a-fA-F.:]", "", str(v or ""))
        if s:
            out.append(s)
    return out


def _load_exclusions() -> dict:
    """Read the analytics-filter config. Missing/malformed → empty (nothing hidden/relabelled).

    Keys: emails[], locations[{city,region,country_code}], ips[], visitor_ids[] (operator
    self-exclusion); bots{ips[],ua_pattern,org_pattern,asn_pattern} (crawler filter — patterns
    EXTEND the baked-in defaults); geo_overrides[{ip_prefix,city,region,country_code,country}]
    (display relabel by IP prefix)."""
    empty = {"emails": [], "locations": [], "ips": [], "visitor_ids": [],
             "bots": {}, "geo_overrides": []}
    try:
        cfg = json.loads(_EXCL_PATH.read_text())
    except Exception:  # noqa: BLE001 — never break analytics on a bad config file
        return empty
    emails = [str(e).strip().lower() for e in (cfg.get("emails") or []) if str(e).strip()]
    locations = [l for l in (cfg.get("locations") or []) if isinstance(l, dict)]
    ips = _clean_ips(cfg.get("ips"))
    # Cookie ids to hide outright. Validated against the same shape the read endpoints
    # allowlist, so a typo'd entry is dropped rather than smuggled into SQL.
    vids = [str(v).strip() for v in (cfg.get("visitor_ids") or []) if _ID_RE.match(str(v).strip())]
    bots = cfg.get("bots") if isinstance(cfg.get("bots"), dict) else {}
    geo = [o for o in (cfg.get("geo_overrides") or [])
           if isinstance(o, dict) and str(o.get("ip_prefix") or "").strip()]
    return {"emails": emails, "locations": locations, "ips": ips, "visitor_ids": vids,
            "bots": bots, "geo_overrides": geo}


def _excluded_cte() -> str:
    """CTE bodies (excl_users, excl_geo_ips, excl_ips, excl_vids, excl_seed, excl_link,
    excluded) — always syntactically valid regardless of config. `excluded` is the set of
    visitor_id cookies to hide: the operator's own (via registered email, a home-location IP,
    a listed IP, a listed cookie id, or a loopback IP — see _LOOPBACK_IPS) PLUS the cookies
    linked to them by shared device fingerprint or routable IP."""
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
    ips_body = (f"select unnest(array[{','.join(_sql_str(i) for i in cfg['ips'])}]::text[]) as ip"
                if cfg["ips"] else "select null::text as ip where false")
    vids_body = (
        f"select unnest(array[{','.join(_sql_str(v) for v in cfg['visitor_ids'])}]::text[]) as visitor_id"
        if cfg["visitor_ids"] else "select null::text as visitor_id where false")
    return (
        f"excl_users as ({users_body}), "
        f"excl_geo_ips as ({geo_body}), "
        f"excl_ips as ({ips_body}), "
        f"excl_vids as ({vids_body}), "
        "excl_seed as (select distinct e.visitor_id from public.analytics_events e "
        "  where e.visitor_id is not null and (e.user_id in (select id from excl_users) "
        "  or e.ip in (select ip from excl_geo_ips) or e.ip in (select ip from excl_ips) "
        "  or e.visitor_id in (select visitor_id from excl_vids) "
        f"  or e.ip in ({','.join(_LOOPBACK_IPS)}))), "
        "excl_link as (select distinct e2.visitor_id from public.analytics_events e2 "
        "  join (select distinct fp, ip from public.analytics_events "
        "        where visitor_id in (select visitor_id from excl_seed)) k "
        "    on (e2.fp = k.fp and e2.fp is not null) "
        f"    or (e2.ip = k.ip and {_routable('e2.ip')} and {_routable('k.ip')}) "
        "  where e2.visitor_id is not null), "
        "excluded as (select visitor_id from excl_seed "
        "             union select visitor_id from excl_link)"
    )


def _bot_cte() -> str:
    """CTE bodies (bot_ips, fp_farm, bots) — the visitor_ids that look like crawlers/automation.
    Signals: config bot IPs, a bot user-agent, a datacenter-but-not-VPN IP, a known crawler
    network org, a known crawler network ASN, or a farm fingerprint. Patterns come from the
    baked-in defaults, EXTENDED by config; the farm threshold is `bots.fp_fanout` (default
    _FP_FANOUT, <2 disables)."""
    cfg = _load_exclusions()
    bots_cfg = cfg["bots"]
    ua = _DEFAULT_BOT_UA + (f"|{bots_cfg['ua_pattern']}" if bots_cfg.get("ua_pattern") else "")
    org = _DEFAULT_BOT_ORG + (f"|{bots_cfg['org_pattern']}" if bots_cfg.get("org_pattern") else "")
    asn = _DEFAULT_BOT_ASN + (f"|{bots_cfg['asn_pattern']}" if bots_cfg.get("asn_pattern") else "")
    bot_ips = _clean_ips(bots_cfg.get("ips"))
    ips_body = (f"select unnest(array[{','.join(_sql_str(i) for i in bot_ips)}]::text[]) as ip"
                if bot_ips else "select null::text as ip where false")
    try:
        fanout = int(bots_cfg.get("fp_fanout", _FP_FANOUT))
    except (TypeError, ValueError):
        fanout = _FP_FANOUT
    farm_body = (
        "select fp from public.analytics_events where fp is not null group by fp "
        f"having count(distinct visitor_id) >= {fanout} and count(distinct ip) >= {fanout}"
        if fanout >= 2 else "select null::text as fp where false")
    # A prefix the operator manually relabelled (geo_overrides) is a curated REAL user —
    # never let the datacenter/org heuristic auto-flag it as a bot (e.g. a residential-VPN
    # exit read as datacenter).
    keep = [str(o.get("ip_prefix")) for o in cfg["geo_overrides"] if o.get("ip_prefix")]
    keep_clause = (" and not (" + " or ".join(f"e.ip like {_sql_str(p + '%')}" for p in keep) + ")"
                   if keep else "")
    return (
        f"bot_ips as ({ips_body}), "
        f"fp_farm as ({farm_body}), "
        "bots as (select distinct e.visitor_id from public.analytics_events e "
        "  left join public.ip_geo g on g.ip = e.ip "
        "  where e.visitor_id is not null and ("
        "    e.ip in (select ip from bot_ips) "
        f"    or (e.ua is not null and e.ua ~* {_sql_str(ua)}) "
        "    or (g.is_hosting is true and coalesce(g.is_vpn, false) = false) "
        f"    or (g.org is not null and g.org ~* {_sql_str(org)}) "
        f"    or (g.asn is not null and g.asn::text ~* {_sql_str(asn)}) "
        "    or (e.fp is not null and e.fp in (select fp from fp_farm)))"
        f"{keep_clause})"
    )


_IDENT_CTE = (
    "ident as (select visitor_id, max(user_id::text) as uid "
    "from public.analytics_events where visitor_id is not null and user_id is not null "
    "group by visitor_id having count(distinct user_id) = 1)")


def _candidate_cte(window_minutes: int | None = None) -> str:
    """CTE (`uanchor`, `cand_fp`, `cand_ip`, `cand`) that links an ANONYMOUS cookie to the
    registered user it MOST LIKELY belongs to, via a device fingerprint or routable IP it shares
    with that user's login-attributed events.

    This is SOFT attribution — a heuristic suggestion, never a merge: `cand` is only left-joined at
    read time to annotate a row, and the PEOPLE/session/event counts are never computed from it. A
    cookie is linked to a uid only when the shared anchor maps to EXACTLY ONE registered user
    (count(distinct uid)=1); a fingerprint/IP shared by two accounts is ambiguous and dropped,
    mirroring the `ident` 2+-accounts rule so one person's activity is never mis-attributed. A
    fingerprint match ('device') is stronger than an IP match ('ip') and wins when both exist; IPs
    are used only when routable (loopback/tunnel/unknown never link — same `_routable` guard the
    operator-exclusion linker uses). Requires the `ident` CTE to precede it in the `with` chain.

    `window_minutes` bounds every analytics_events scan here to the same period the calling surface
    shows (via the created_at index), so this linkage never adds an unbounded full-table scan to
    the panel query — matching is within the displayed window on BOTH the cookie and anchor sides."""
    win = (f" and e.created_at > now() - interval '{int(window_minutes)} minutes'"
           if window_minutes else "")
    wwin = (f" where e.created_at > now() - interval '{int(window_minutes)} minutes'"
            if window_minutes else "")
    return (
        # Anchors: the distinct (uid, fp, ip) points where a KNOWN user has been seen (their
        # stitched events). `distinct` keeps the fan-out into the two joins below bounded.
        "uanchor as (select distinct i.uid, e.fp, e.ip from public.analytics_events e "
        f"  join ident i on i.visitor_id = e.visitor_id{wwin}), "
        # A cookie sharing a fingerprint with exactly one user → that user (device-strength link).
        "cand_fp as (select e.visitor_id, min(a.uid) as uid "
        "  from public.analytics_events e join uanchor a on a.fp = e.fp and e.fp is not null "
        f"  where e.visitor_id is not null{win} "
        "  group by e.visitor_id having count(distinct a.uid) = 1), "
        # A cookie sharing a routable IP with exactly one user → that user (IP-strength link).
        "cand_ip as (select e.visitor_id, min(a.uid) as uid "
        f"  from public.analytics_events e join uanchor a on a.ip = e.ip "
        f"    and {_routable('e.ip')} and {_routable('a.ip')} "
        f"  where e.visitor_id is not null{win} "
        "  group by e.visitor_id having count(distinct a.uid) = 1), "
        # Collapse to one candidate per cookie: fingerprint wins over IP; carry the basis for display.
        "cand as (select v.visitor_id, coalesce(f.uid, p.uid) as uid, "
        "    case when f.uid is not null then 'device' else 'ip' end as basis "
        "  from (select visitor_id from cand_fp union select visitor_id from cand_ip) v "
        "  left join cand_fp f on f.visitor_id = v.visitor_id "
        "  left join cand_ip p on p.visitor_id = v.visitor_id)"
    )


def _cte(include_ident: bool = False, include_candidate: bool = False,
         candidate_window: int | None = None) -> str:
    """Full `with …` prefix: the excluded-visitor + bot chains, optionally preceded by `ident`
    and followed by the soft candidate-identity chain (which requires `ident`). `candidate_window`
    (minutes) bounds the candidate scans to the surface's window."""
    parts = []
    if include_ident or include_candidate:
        parts.append(_IDENT_CTE)
    parts.append(_excluded_cte())
    parts.append(_bot_cte())
    if include_candidate:
        parts.append(_candidate_cte(candidate_window))
    return "with " + ", ".join(parts) + " "


def _not_a_bot(alias: str = "e") -> str:
    """WHERE fragment that drops crawler/automation cookies. Null visitor_id is KEPT."""
    col = f"{alias}.visitor_id" if alias else "visitor_id"
    return f"({col} is null or {col} not in (select visitor_id from bots))"


def _apply_geo_overrides(rows, ip_key: str = "ip"):
    """Relabel the displayed location of rows whose IP starts with a configured prefix
    (fixes IPs geolocated to the wrong place — e.g. an HK VPN read as Frankfurt). Applied at
    read time in Python so a single stale ip_geo row can't misfile a whole prefix. Mutates
    and returns `rows`."""
    ovr = _load_exclusions()["geo_overrides"]
    if not ovr or not rows:
        return rows
    for r in rows:
        ip = str(r.get(ip_key) or "")
        if not ip:
            continue
        for o in ovr:
            if ip.startswith(str(o.get("ip_prefix"))):
                for fld in ("city", "region", "country_code", "country"):
                    if o.get(fld):
                        r[fld] = o[fld]
                break
    return rows


def _not_excluded(alias: str = "e") -> str:
    """WHERE fragment that drops the operator's hidden cookies. `alias` = table alias
    holding visitor_id ('' for an unaliased table). Null visitor_id is KEPT (it can't be a
    hidden cookie, and a bare `not in` would drop it via SQL three-valued logic)."""
    col = f"{alias}.visitor_id" if alias else "visitor_id"
    return f"({col} is null or {col} not in (select visitor_id from excluded))"


def _not_excluded_search() -> str:
    """WHERE fragment for public.search_events (no visitor_id column): drop the operator's
    rows by anon cookie (which already carries the hidden-cookie-id and loopback seeds through
    `excluded`), registered user, home-location IP, listed IP, or loopback IP — searches fired
    from a dev server have no cookie the beacon ever saw. Each arm keeps NULLs."""
    return ("(anon_id is null or anon_id not in (select visitor_id from excluded)) "
            "and (user_id is null or user_id not in (select id from excl_users)) "
            "and (ip is null or ip not in (select ip from excl_geo_ips)) "
            "and (ip is null or ip not in (select ip from excl_ips)) "
            f"and (ip is null or ip not in ({','.join(_LOOPBACK_IPS)}))")


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


def _minutes(v, default_min: int) -> int:
    """Window in MINUTES, clamped to [1 minute, 365 days]. Powers the sub-day time presets."""
    try:
        return max(1, min(365 * 1440, int(float(v))))
    except (TypeError, ValueError):
        return default_min


def _win(minutes, days, default_min: int) -> int:
    """Effective window in MINUTES. `minutes` wins (sub-day presets); else the legacy `days`
    param (x 1440); else `default_min`. Lets old ?days= callers and new ?minutes= callers coexist."""
    if minutes is not None and str(minutes).strip() != "":
        return _minutes(minutes, default_min)
    if days is not None and str(days).strip() != "":
        return _days(days) * 1440
    return default_min


def _bucket(m: int) -> tuple:
    """(date_trunc unit, to_char fmt) for a time series over an m-minute window — chosen so the
    chart has a readable point count. Unit is whitelisted (minute/hour/day) so it's injection-safe."""
    if m <= 180:
        return ("minute", "HH24:MI")      # <= 3h
    if m <= 4320:
        return ("hour", "MM-DD HH24:MI")  # <= 3d
    return ("day", "YYYY-MM-DD")


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
def overview(days=7, minutes=None, gap=None) -> dict:
    m = _win(minutes, days, 10080)
    g = _gap(gap)
    trunc, fmt = _bucket(m)
    # Truncate AFTER converting to the display zone so a "day" is a local midnight-to-midnight
    # day, not a UTC one (which would split the operator's evening across two bars).
    dt = f"date_trunc('{trunc}', {_lt('e.created_at')})"
    def run():
        # 'visitors' counts PEOPLE (canonical identity), not raw cookies. The operator's own
        # hidden cookies (excluded) AND crawlers (bots) are dropped so the headline counts
        # reflect real humans and match the tables below.
        human = f"and {_not_excluded('e')} and {_not_a_bot('e')}"
        win = (_query(_cte(include_ident=True) +
            "select count(*)::int as events, "
            f"{_CANON_VISITORS}, "
            "count(*) filter (where e.type in ('pageview','route'))::int as pageviews, "
            "count(*) filter (where e.type='ticker_view')::int as ticker_views, "
            "count(*) filter (where e.type='search')::int as searches "
            "from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"where e.created_at > now() - interval '{m} minutes' {human}") or [{}])[0]
        # 'sessions' counts VISITS, not raw per-tab session_ids, so the headline agrees with
        # the Sessions tab (which stitches tabs/origins) instead of triple-counting a hop.
        win["sessions"] = (_query(_cte(include_ident=True) +
            f"select count(*) filter (where b = 1)::int as sessions from ("
            f"  select {_visit_break(g)} as b from ("
            "    select coalesce(i.uid, e.visitor_id) as canon, e.created_at, e.id "
            "    from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"    where e.visitor_id is not null and e.created_at > now() - interval '{m} minutes' "
            f"    {human}) y) z") or [{}])[0].get("sessions")
        alltime = (_query(_cte(include_ident=True) +
            f"select count(*)::int as events, {_CANON_VISITORS} "
            "from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"where {_not_excluded('e')} and {_not_a_bot('e')}") or [{}])[0]
        # Bots filtered out of the window (shown separately so detection is transparent).
        bots = (_query(_cte() +
            "select count(distinct e.visitor_id)::int as visitors, count(*)::int as events "
            "from public.analytics_events e "
            f"where e.created_at > now() - interval '{m} minutes' and {_not_excluded('e')} "
            "and e.visitor_id in (select visitor_id from bots)") or [{}])[0]
        by_site = _query(_cte(include_ident=True) +
            f"select e.site, count(*)::int as events, {_CANON_VISITORS} "
            "from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"where e.created_at > now() - interval '{m} minutes' {human} "
            "group by e.site order by events desc") or []
        daily = _query(_cte(include_ident=True) +
            f"select to_char({dt},'{fmt}') as day, "
            f"{_CANON_VISITORS}, count(*)::int as events "
            "from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"where e.created_at > now() - interval '{m} minutes' {human} "
            f"group by {dt} order by {dt}") or []
        return {"days": round(m / 1440, 2), "minutes": m, "window": win, "alltime": alltime, "bots": bots,
                "by_site": by_site, "daily": daily, "tz": _TZ, "tz_label": _tz_label(),
                "visit_gap_min": g}
    return _guard(run)


def pages(days=7, limit=25, minutes=None) -> dict:
    m, n = _win(minutes, days, 10080), _limit(limit, 25)
    def run():
        rows = _query(_cte() +
            "select site, coalesce(path,'(none)') as path, "
            "count(*) filter (where type in ('pageview','route'))::int as views, "
            "count(distinct visitor_id)::int as visitors, "
            "round(avg(dwell_ms) filter (where dwell_ms is not null))::int as avg_dwell_ms "
            f"from public.analytics_events where created_at > now() - interval '{m} minutes' "
            f"and {_not_excluded('')} and {_not_a_bot('')} "
            "group by 1,2 order by views desc nulls last "
            f"limit {n}") or []
        return {"days": round(m / 1440, 2), "minutes": m, "pages": rows}
    return _guard(run)


def geo(days=30, limit=200, minutes=None) -> dict:
    m, n = _win(minutes, days, 43200), _limit(limit, 200)
    def run():
        countries = _query(_cte() +
            "select coalesce(g.country,'(unknown)') as country, g.country_code, "
            "count(distinct e.visitor_id)::int as visitors, count(*)::int as events "
            "from public.analytics_events e left join public.ip_geo g on g.ip = e.ip "
            f"where e.created_at > now() - interval '{m} minutes' and {_not_excluded('e')} and {_not_a_bot('e')} "
            "group by 1,2 order by visitors desc nulls last") or []
        cities = _query(_cte() +
            "select g.city, g.region, g.country_code, g.lat, g.lon, "
            "count(distinct e.visitor_id)::int as visitors "
            "from public.analytics_events e join public.ip_geo g on g.ip = e.ip "
            f"where e.created_at > now() - interval '{m} minutes' and g.city is not null "
            f"and {_not_excluded('e')} and {_not_a_bot('e')} "
            "group by 1,2,3,4,5 order by visitors desc "
            f"limit {n}") or []
        return {"days": round(m / 1440, 2), "minutes": m, "countries": countries, "cities": cities}
    return _guard(run)


def sessions(limit=100, q="", include_bots=False, minutes=None, days=None, gap=None) -> dict:
    """Recent VISITS — one row per continuous sitting, not per raw session_id.

    Rows still ship under the `sessions` key and still carry a `session_id` (the FIRST raw
    session of the visit, which the replay resolves back to the whole visit), so the SPA's
    shape is unchanged. New per-row fields: `tab_sessions` (how many raw sessions merged)
    and `sites` (the origins touched, in the order they were first hit — `site` is that list
    joined with an arrow, so one macro → terminal → macro sitting reads as the trip it was)."""
    n = _limit(limit, 100, 2000)
    m = _win(minutes, days, 43200)
    g = _gap(gap)
    qq = _sanitize_q(q)
    # Filter clauses, applied AFTER the user+geo joins and BEFORE the limit so they see full
    # history — name/email identify the login-attributed user of the visit's cookie;
    # candidate_name/candidate_email are the soft device/IP guess, so the operator can
    # search Sessions by either. Site matching runs over the whole visit's site list.
    conds = []
    if qq:
        cols = ("s.visitor_id", "s.ip", "array_to_string(sn.sites,' ')",
                "g.city", "g.region", "g.country_code",
                "hu.email", users.display_name_sql("hu"),
                "cu.email", users.display_name_sql("cu"))
        conds.append("(" + " or ".join(f"{c} ilike '%{qq}%'" for c in cols) + ")")
    if not include_bots:
        conds.append("s.is_bot = 0")          # crawlers hidden unless explicitly revealed
    where = ("where " + " and ".join(conds) + " ") if conds else ""
    def run():
        rows = _query(_cte(include_ident=True, include_candidate=True, candidate_window=m) +
            # ev: in-window, non-hidden events tagged with their canonical person, so a
            # signed-in visitor's separate macro/terminal cookies stitch into one visit.
            ", ev as (select e.id, e.session_id, e.visitor_id, e.site, e.ip, e.type, e.created_at, "
            "    coalesce(i.uid, e.visitor_id) as canon "
            "  from public.analytics_events e left join ident i on i.visitor_id = e.visitor_id "
            f"  where e.session_id is not null and e.visitor_id is not null and {_not_excluded('e')} "
            f"    and e.created_at > now() - interval '{m} minutes'), "
            f"brk as (select ev.*, {_visit_break(g)} as b from ev), "
            f"vis as (select brk.*, {_visit_no()} as vn from brk), "
            # Sites in first-touch order — aggregated per (visit, site) first so the array is
            # one entry per origin however many events it holds.
            "sv as (select canon, vn, site, min(created_at) as t0 from vis "
            "  where site is not null group by 1,2,3), "
            "sn as (select canon, vn, array_agg(site order by t0) as sites from sv group by 1,2), "
            "s as (select canon, vn, "
            "    (array_agg(session_id order by created_at, id))[1] as session_id, "
            "    (array_agg(visitor_id order by created_at, id))[1] as visitor_id, "
            "    count(distinct session_id)::int as tab_sessions, count(*)::int as events, "
            "    count(*) filter (where type in ('pageview','route'))::int as pages, "
            "    min(created_at) as started, max(created_at) as ended, "
            "    (array_agg(ip order by created_at, id))[1] as ip, "
            "    max(case when visitor_id in (select visitor_id from bots) then 1 else 0 end) as is_bot "
            "  from vis group by 1,2) "
            "select s.session_id, s.visitor_id, hi.uid as user_id, "
            "  array_to_string(sn.sites,' → ') as site, sn.sites, s.tab_sessions, "
            "  s.events, s.pages, "
            f"  to_char({_lt('s.started')},'YYYY-MM-DD HH24:MI') as started, "
            "  round(extract(epoch from (s.ended - s.started)))::int as duration_s, "
            "  s.ip, s.is_bot, g.city, g.region, g.country_code, "
            # hard: the verified user this visit's cookie is stitched to.
            f"  hu.email as email, {users.display_name_sql('hu')} as name, "
            # soft: the registered user this anonymous cookie most likely belongs to (device/IP).
            f"  cu.email as candidate_email, {users.display_name_sql('cu')} as candidate_name, "
            "  c.basis as candidate_basis "
            "from s "
            "left join sn on sn.canon = s.canon and sn.vn = s.vn "
            "left join public.ip_geo g on g.ip = s.ip "
            "left join ident hi on hi.visitor_id = s.visitor_id "
            "left join auth.users hu on hu.id::text = hi.uid "
            "left join cand c on c.visitor_id = s.visitor_id "
            "left join auth.users cu on cu.id::text = c.uid "
            f"{where}"
            f"order by s.started desc limit {n}") or []
        return {"sessions": _apply_geo_overrides(rows), "q": qq, "include_bots": include_bots,
                "tz": _TZ, "tz_label": _tz_label(), "visit_gap_min": g}
    return _guard(run)


def visitors(limit=250, q="", include_bots=False, minutes=None, days=None, gap=None) -> dict:
    """One row per PERSON — the 'Frequent Visitors' list.

    Identity resolution: any anonymous cookie (mm_aid) that ever appears on a signed-in
    event is merged under that user, so all of one person's cookies/devices collapse into
    a single row keyed by their Supabase user id and labelled with their name when available
    (otherwise email). Purely anonymous visitors stay keyed by their mm_aid. `identities` =
    how many cookies merged.

    `sessions` counts VISITS on the same rule the Sessions tab uses (see _visit_break), so the
    two tabs agree; `tab_sessions` keeps the raw per-tab/per-origin count alongside it.
    Ordered by visit count."""
    n = _limit(limit, 250, 2000)
    m = _win(minutes, days, 43200)
    g = _gap(gap)
    qq = _sanitize_q(q)
    # Filters, applied AFTER the user+geo joins and BEFORE the limit so they see the whole roster.
    conds = []
    if qq:
        cols = ("u.email", users.display_name_sql("u"),
                "cu.email", users.display_name_sql("cu"),
                "v.canon", "v.last_ip", "g.city", "g.region", "g.country", "g.country_code")
        conds.append("(" + " or ".join(f"{c} ilike '%{qq}%'" for c in cols) + ")")
    if not include_bots:
        conds.append("v.is_bot = 0")           # crawlers hidden unless explicitly revealed
    where = ("where " + " and ".join(conds) + " ") if conds else ""
    def run():
        rows = _query(
            # ident: each mm_aid -> the user uuid it belongs to (if ever authenticated).
            # A cookie signed into by 2+ DIFFERENT accounts (shared/kiosk device) is
            # AMBIGUOUS — excluded from the auto-merge so one person's activity is never
            # silently reassigned to another; those events stay under the cookie.
            "with " + _IDENT_CTE +
            ", " + _excluded_cte() + ", " + _bot_cte() + ", " + _candidate_cte(m) +
            # ev: every (non-hidden) event tagged with its canonical identity (uid if known, else mm_aid)
            ", ev0 as ("
            "  select e.id, e.session_id, e.ip, e.created_at, e.visitor_id, i.uid, "
            "    coalesce(i.uid, e.visitor_id) as canon "
            "  from public.analytics_events e "
            "  left join ident i on i.visitor_id = e.visitor_id "
            f"  where e.visitor_id is not null and {_not_excluded('e')} "
            f"    and e.created_at > now() - interval '{m} minutes'"
            "), "
            # ev: the same events with a visit number, so `sessions` below counts sittings
            # (macro → terminal → macro = 1) rather than per-tab/per-origin session_ids.
            f"ev1 as (select ev0.*, {_visit_break(g)} as b from ev0), "
            f"ev as (select ev1.*, {_visit_no()} as vn from ev1) "
            "select v.canon as visitor_id, (v.uid is not null) as is_user, u.email, "
            f"  {users.display_name_sql('u')} as name, "
            # candidate: for an ANONYMOUS row (canon is a cookie, not a uid), the registered user
            # it most likely belongs to via a shared device/IP — a suggestion, never merged.
            f"  cu.email as candidate_email, {users.display_name_sql('cu')} as candidate_name, "
            "  c.basis as candidate_basis, "
            "  v.events, v.sessions, v.tab_sessions, v.identities, v.ips, v.last_ip, v.is_bot, "
            f"  to_char({_lt('v.first_seen')},'YYYY-MM-DD HH24:MI') as first_seen, "
            f"  to_char({_lt('v.last_seen')},'YYYY-MM-DD HH24:MI') as last_seen, "
            "  g.city, g.region, g.country, g.country_code, g.is_vpn "
            "from (select canon, max(uid) as uid, count(*)::int as events, "
            "  count(distinct vn)::int as sessions, "
            "  count(distinct session_id)::int as tab_sessions, "
            "  count(distinct visitor_id)::int as identities, count(distinct ip)::int as ips, "
            "  min(created_at) as first_seen, max(created_at) as last_seen, "
            "  (array_agg(ip order by created_at desc))[1] as last_ip, "
            "  max(case when visitor_id in (select visitor_id from bots) then 1 else 0 end) as is_bot "
            "  from ev group by canon) v "
            "left join auth.users u on u.id::text = v.uid "
            "left join cand c on c.visitor_id = v.canon "
            "left join auth.users cu on cu.id::text = c.uid "
            "left join public.ip_geo g on g.ip = v.last_ip "
            f"{where}"
            f"order by v.sessions desc, v.last_seen desc limit {n}") or []
        return {"visitors": _apply_geo_overrides(rows, "last_ip"), "q": qq,
                "include_bots": include_bots, "tz": _TZ, "tz_label": _tz_label(),
                "visit_gap_min": g}
    return _guard(run)


def session(session_id: str, gap=None) -> dict:
    """The ordered event path of the VISIT containing `session_id` (the 1:1 replay).

    Because sessions() stitches per-tab/per-origin session_ids into visits, the replay has to
    stitch too — otherwise clicking through from a merged row would show only the first tab.
    So: resolve the seed session's person to all their cookies, re-split their events on the
    same idle rule, and return the visit the seed falls in. Each event carries its own `site`
    and `session_id`, so the origin hops and tab boundaries stay visible inside the timeline.

    The scan is bounded to ±12h around the seed session so it never walks the person's whole
    history — a visit is by construction a chain of <= `gap`-minute hops, and the gap ceiling
    is 12h, so a visit cannot reach beyond that bound without the seed itself spanning it."""
    if not session_id or not _ID_RE.match(session_id):
        return {"ok": False, "reason": "invalid session id"}
    g = _gap(gap)
    sid = session_id   # _ID_RE-allowlisted ([A-Za-z0-9._:-]{1,64}) — safe to interpolate
    def run():
        cte = (
            "with " + _IDENT_CTE + ", "
            "seed as (select max(visitor_id) as vid, min(created_at) as t0, max(created_at) as t1 "
            f"  from public.analytics_events where session_id = '{sid}'), "
            # The seed cookie's owner (if it ever signed in) → all of that person's cookies,
            # so a macro cookie and a terminal cookie of one logged-in visitor stitch together.
            "seeduid as (select uid from ident where visitor_id = (select vid from seed)), "
            "myaids as (select visitor_id from ident where uid in (select uid from seeduid) "
            "           union select vid from seed), "
            # visitor_id-indexed + time-bounded, so this never degrades into a full scan.
            "win as (select e.* from public.analytics_events e "
            "  where e.visitor_id in (select visitor_id from myaids) "
            "    and e.created_at >= (select t0 from seed) - interval '12 hours' "
            "    and e.created_at <= (select t1 from seed) + interval '12 hours'), "
            f"brk as (select win.*, {_visit_break(g, part=None)} as b from win), "
            f"vis as (select brk.*, {_visit_no(part=None)} as vn from brk), "
            f"cur as (select vn from vis where session_id = '{sid}' order by created_at, id limit 1) "
        )
        path = _query(cte +
            "select type, coalesce(path,'') as path, ticker, dwell_ms, scroll, site, session_id, "
            f"to_char({_lt('created_at')},'HH24:MI:SS') as t, meta "
            "from vis where vn = (select vn from cur) order by created_at, id limit 2000") or []
        head = (_query(cte +
            "select s.*, u.email, "
            f"{users.display_name_sql('u')} as name from ("
            "select (array_agg(visitor_id order by created_at, id))[1] as visitor_id, "
            "max(user_id::text) as user_id, "
            "count(distinct session_id)::int as tab_sessions, "
            f"to_char(min({_lt('created_at')}),'YYYY-MM-DD HH24:MI') as started, "
            f"to_char(max({_lt('created_at')}),'HH24:MI') as ended, "
            "round(extract(epoch from (max(created_at) - min(created_at))))::int as duration_s, "
            "(array_agg(ip order by created_at, id))[1] as ip, "
            "(array_agg(fp) filter (where fp is not null))[1] as fp "
            "from vis where vn = (select vn from cur)) s "
            "left join auth.users u on u.id::text = s.user_id") or [{}])[0]
        # Origins in first-touch order — derived from the already-ordered path rather than a
        # third round trip.
        sites = list(dict.fromkeys([r.get("site") for r in path if r.get("site")]))
        head["site"] = " → ".join(sites)
        return {"session_id": sid, "head": head, "path": path, "sites": sites,
                "tz": _TZ, "tz_label": _tz_label(), "visit_gap_min": g}
    return _guard(run)


def flow(days=7, limit=40, minutes=None) -> dict:
    m, n = _win(minutes, days, 10080), _limit(limit, 40, 200)
    def run():
        rows = _query(
            "with " + _excluded_cte() + ", " + _bot_cte() + ", ev as (select session_id, path, "
            "  lag(path) over (partition by session_id order by id) as prev "
            "  from public.analytics_events "
            f"  where type in ('pageview','route') and path is not null and {_not_excluded('')} and {_not_a_bot('')} "
            f"    and created_at > now() - interval '{m} minutes') "
            "select prev as from_path, path as to_path, count(*)::int as n "
            "from ev where prev is not null and prev <> path "
            "group by 1,2 order by n desc "
            f"limit {n}") or []
        return {"days": round(m / 1440, 2), "minutes": m, "edges": rows}
    return _guard(run)


def terminal(days=7, limit=25, minutes=None) -> dict:
    m, n = _win(minutes, days, 10080), _limit(limit, 25)
    def run():
        no_bot_search = "(anon_id is null or anon_id not in (select visitor_id from bots))"
        searches = _query(_cte() +
            "select symbol as ticker, count(*)::int as searches, "
            "count(distinct coalesce(user_id::text, anon_id, ip))::int as visitors "
            f"from public.search_events where created_at > now() - interval '{m} minutes' "
            f"and {_not_excluded_search()} and {no_bot_search} "
            f"group by 1 order by searches desc limit {n}") or []
        views = _query(_cte() +
            "select ticker, count(*)::int as views, count(distinct visitor_id)::int as visitors "
            "from public.analytics_events where type='ticker_view' and ticker is not null "
            f"and created_at > now() - interval '{m} minutes' and {_not_excluded('')} and {_not_a_bot('')} "
            f"group by 1 order by views desc limit {n}") or []
        totals = (_query(_cte() +
            "select (select count(*)::int from public.search_events "
            f"  where created_at > now() - interval '{m} minutes' and {_not_excluded_search()} and {no_bot_search}) as search_total, "
            "(select count(*)::int from public.analytics_events where type='ticker_view' "
            f"  and created_at > now() - interval '{m} minutes' and {_not_excluded('')} and {_not_a_bot('')}) as view_total") or [{}])[0]
        return {"days": round(m / 1440, 2), "minutes": m, "top_searches": searches, "top_views": views, "totals": totals}
    return _guard(run)


def visitor(visitor_id: str, gap=None) -> dict:
    """One person's profile. `visitor_id` is the canonical id from the visitors() list —
    either a Supabase user uuid (a registered person, whose every mm_aid cookie is merged)
    or a bare mm_aid (a purely anonymous visitor). All sub-queries resolve it to the full
    set of that person's cookies via the `myaids` CTE, so a signed-in user's activity across
    every device/cookie shows as one profile."""
    if not visitor_id or not _ID_RE.match(visitor_id):
        return {"ok": False, "reason": "invalid visitor id"}
    g = _gap(gap)
    v = visitor_id   # _ID_RE-allowlisted ([A-Za-z0-9._:-]{1,64}) — safe to interpolate
    # Prepended to every sub-query: map the canonical id to all mm_aid cookies of the person.
    # If v is a user uuid -> every mm_aid ever seen on one of that user's events; if v is an
    # mm_aid -> just itself (the `union select '{v}'` covers the anonymous case).
    # ident drops cookies signed into by 2+ accounts (ambiguous shared devices); the excluded +
    # bot chains ride along so the linked-visitor list below can drop crawler and hidden cookies
    # rather than reporting "50 linked identities" that are all one scraper's rotating cookies.
    cte = (
        "with " + _IDENT_CTE + ", " + _excluded_cte() + ", " + _bot_cte() +
        f", myaids as (select visitor_id from ident where uid = '{v}' union select '{v}') "
    )
    inaids = "visitor_id in (select visitor_id from myaids)"
    def run():
        # `sessions` counts VISITS (the Sessions-tab rule), so one person's numbers agree
        # across every surface; `tab_sessions` keeps the raw per-tab/per-origin count.
        profile = (_query(cte +
            f"select to_char(min({_lt('created_at')}),'YYYY-MM-DD HH24:MI') as first_seen, "
            f"to_char(max({_lt('created_at')}),'YYYY-MM-DD HH24:MI') as last_seen, "
            "count(*)::int as events, count(distinct vn)::int as sessions, "
            "count(distinct session_id)::int as tab_sessions, "
            "count(distinct ip)::int as ips, count(distinct fp)::int as fingerprints, "
            "count(distinct visitor_id)::int as identities, max(user_id::text) as user_id "
            f"from (select w.*, {_visit_no(part=None)} as vn from ("
            f"  select x.*, {_visit_break(g, part=None)} as b "
            f"  from public.analytics_events x where {inaids}) w) z") or [{}])[0]
        er = _query(
            "select u.email, "
            f"{users.display_name_sql('u')} as name "
            f"from auth.users u where u.id::text = '{v}'") or []
        email = er[0].get("email") if er else None
        name = er[0].get("name") if er else None
        ips = _apply_geo_overrides(_query(cte +
            "select e.ip, g.city, g.region, g.country_code, g.asn, g.org, "
            "g.is_vpn, g.is_proxy, g.is_hosting, count(*)::int as events "
            "from public.analytics_events e left join public.ip_geo g on g.ip = e.ip "
            f"where e.{inaids} group by 1,2,3,4,5,6,7,8,9 order by events desc") or [])
        # OTHER visitors sharing a fingerprint or IP with this person (not yet merged by login).
        # Each linked cookie is resolved to its registered email when it is itself login-stitched,
        # so a shared device/IP surfaces WHO the other identity is — not just an opaque cookie.
        linked = _query(cte +
            "select e2.visitor_id, max(li.uid) as user_id, count(*)::int as shared_events, "
            "max(case when e2.fp = k.e1fp then 1 else 0 end) as via_fp, "
            "max(case when e2.ip = k.e1ip then 1 else 0 end) as via_ip, "
            "max(lu.email) as email, "
            f"max({users.display_name_sql('lu')}) as name "
            "from public.analytics_events e2 "
            "join (select distinct fp as e1fp, ip as e1ip from public.analytics_events "
            f"      where {inaids}) k "
            "  on (e2.fp = k.e1fp and e2.fp is not null) "
            f"  or (e2.ip = k.e1ip and {_routable('e2.ip')}) "
            "left join ident li on li.visitor_id = e2.visitor_id "
            "left join auth.users lu on lu.id::text = li.uid "
            "where e2.visitor_id not in (select visitor_id from myaids) "
            f"  and {_not_a_bot('e2')} and {_not_excluded('e2')} "
            f"group by 1 order by coalesce(max({users.display_name_sql('lu')}), "
            "max(lu.email)) is null, shared_events desc limit 50") or []
        # If THIS profile is an anonymous cookie, name the registered user it most likely belongs
        # to: the account owning a fingerprint/routable-IP it shares — but only when exactly one
        # account matches (ambiguous shared device/IP → no guess). Suggestion only, never a merge.
        candidate = None
        if not (name or email):
            crows = _query(cte +
                "select i2.uid, "
                "  max(case when e2.fp = k.e1fp and e2.fp is not null then 1 else 0 end) as via_fp, "
                f"  max(case when e2.ip = k.e1ip and {_routable('e2.ip')} then 1 else 0 end) as via_ip "
                "from public.analytics_events e2 "
                "join (select distinct fp as e1fp, ip as e1ip from public.analytics_events "
                f"      where {inaids}) k "
                "  on (e2.fp = k.e1fp and e2.fp is not null) "
                f"  or (e2.ip = k.e1ip and {_routable('e2.ip')} and {_routable('k.e1ip')}) "
                "join ident i2 on i2.visitor_id = e2.visitor_id "   # e2 is a KNOWN user's cookie
                f"where {_not_a_bot('e2')} and {_not_excluded('e2')} "
                "group by i2.uid") or []
            if len(crows) == 1 and crows[0].get("uid"):
                er2 = _query(
                    "select u.email, "
                    f"{users.display_name_sql('u')} as name "
                    f"from auth.users u where u.id::text = '{crows[0]['uid']}'") or []
                candidate = {"uid": crows[0]["uid"],
                             "email": (er2[0].get("email") if er2 else None),
                             "name": (er2[0].get("name") if er2 else None),
                             "via_fp": crows[0].get("via_fp"), "via_ip": crows[0].get("via_ip")}
        recent = _query(cte +
            "select type, coalesce(path,'') as path, ticker, site, "
            f"to_char({_lt('created_at')},'YYYY-MM-DD HH24:MI') as t "
            f"from public.analytics_events where {inaids} order by id desc limit 40") or []
        # tickers this person searched (search_events.anon_id = the mm_aid cookie, OR the
        # signed-in user_id directly — catches searches from a cookie with no beacon rows) + viewed
        searches = _query(cte +
            "select symbol as ticker, count(*)::int as n, "
            f"to_char(max({_lt('created_at')}),'YYYY-MM-DD HH24:MI') as last "
            "from public.search_events "
            f"where (anon_id in (select visitor_id from myaids) or user_id::text = '{v}') "
            "group by 1 order by n desc, last desc limit 50") or []
        tickers_viewed = _query(cte +
            "select ticker, count(*)::int as n "
            f"from public.analytics_events where {inaids} and type='ticker_view' and ticker is not null "
            "group by 1 order by n desc limit 50") or []
        return {"visitor_id": v, "email": email, "name": name,
                "candidate": candidate, "profile": profile,
                "ips": ips, "linked": linked, "recent": recent, "searches": searches,
                "tickers_viewed": tickers_viewed,
                "tz": _TZ, "tz_label": _tz_label(), "visit_gap_min": g}
    return _guard(run)


def realtime() -> dict:
    def run():
        now = (_query(_cte() +
            "select count(distinct visitor_id)::int as visitors, "
            "count(distinct session_id)::int as sessions, count(*)::int as events "
            "from public.analytics_events where created_at > now() - interval '5 minutes' "
            f"and {_not_excluded('')} and {_not_a_bot('')}") or [{}])[0]
        recent = _apply_geo_overrides(_query(_cte() +
            "select e.type, e.site, coalesce(e.path,'') as path, e.ticker, e.ip, "
            f"to_char({_lt('e.created_at')},'HH24:MI:SS') as t, g.city, g.country_code "
            "from public.analytics_events e left join public.ip_geo g on g.ip = e.ip "
            f"where e.created_at > now() - interval '15 minutes' and {_not_excluded('e')} and {_not_a_bot('e')} "
            "order by e.id desc limit 30") or [])
        return {"active": now, "recent": recent, "tz": _TZ, "tz_label": _tz_label()}
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
