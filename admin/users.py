"""Supabase user tracking via the Management API SQL endpoint.

The site's accounts run on Supabase (Google OAuth + email/password, #761). We
read the user roster from auth.users with a Personal Access Token
(SUPABASE_ACCESS_TOKEN, the sbp_… token), running read-only SELECTs through the
Management API's database-query endpoint. No service_role JWT to store, and
nothing is exposed to the browser. All SQL is static text authored here (the
only interpolated value is an int-clamped LIMIT), so there is no injection
surface. Degrades gracefully: with no PAT it returns setup steps.
"""
from __future__ import annotations

from . import settings

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

_API = "https://api.supabase.com/v1"


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
            "Supabase dashboard → Account → Access Tokens → generate a PAT (sbp_…).",
            "Set SUPABASE_ACCESS_TOKEN in the admin service env.",
            "Optional: SUPABASE_PROJECT_REF (defaults to the MarketIntelligence project).",
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
        json={"query": sql}, timeout=15)
    if not (200 <= r.status_code < 300):   # the query endpoint answers 201 on success
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def summary() -> dict:
    if not status()["configured"]:
        return {"ok": False, **status()}
    try:
        agg = _query(
            "select "
            "count(*)::int as total, "
            "count(*) filter (where created_at > now() - interval '24 hours')::int as new_24h, "
            "count(*) filter (where created_at > now() - interval '7 days')::int as new_7d, "
            "count(*) filter (where created_at > now() - interval '30 days')::int as new_30d, "
            "count(*) filter (where last_sign_in_at > now() - interval '24 hours')::int as active_24h, "
            "count(*) filter (where last_sign_in_at > now() - interval '7 days')::int as active_7d, "
            "count(*) filter (where email_confirmed_at is not null)::int as confirmed, "
            "max(created_at) as newest "
            "from auth.users")
        series = _query(
            "select to_char(date_trunc('day', created_at), 'YYYY-MM-DD') as day, "
            "count(*)::int as n from auth.users "
            "where created_at > now() - interval '30 days' group by 1 order by 1")
        providers = _query(
            "select coalesce(raw_app_meta_data->>'provider','email') as provider, "
            "count(*)::int as n from auth.users group by 1 order by 2 desc")
        return {"ok": True, "summary": (agg or [{}])[0],
                "signups_daily": series or [], "providers": providers or []}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def recent(limit: int = 30) -> dict:
    if not status()["configured"]:
        return {"ok": False, **status()}
    try:
        n = max(1, min(200, int(limit)))   # int-clamped → safe to interpolate
        rows = _query(
            "select email, "
            "coalesce(raw_app_meta_data->>'provider','email') as provider, "
            "to_char(created_at,'YYYY-MM-DD HH24:MI') as created_at, "
            "to_char(last_sign_in_at,'YYYY-MM-DD HH24:MI') as last_sign_in_at, "
            "(email_confirmed_at is not null) as confirmed "
            f"from auth.users order by created_at desc limit {n}")
        return {"ok": True, "users": rows or []}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
