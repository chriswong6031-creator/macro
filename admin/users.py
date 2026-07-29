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

# Exclude soft-deleted, banned, and anonymous rows from every roster count so the
# primary totals reflect real, active accounts. deleted_at (soft-delete),
# banned_until (temp/perm bans), and is_anonymous are the three auth.users flags.
_ACTIVE = ("deleted_at is null "
           "and coalesce(is_anonymous, false) = false "
           "and (banned_until is null or banned_until < now())")


def display_name_sql(alias: str = "u") -> str:
    """SQL expression for the best non-empty name in a Supabase auth user row.

    OAuth providers and email sign-up flows do not all use the same metadata
    key. Keep the precedence shared by every admin surface so Analytics, Users,
    and Subscribers identify the same person consistently.
    """
    meta = f"{alias}.raw_user_meta_data"
    first_last = (
        f"nullif(trim(coalesce(nullif(trim({meta}->>'first_name'), ''), "
        f"nullif(trim({meta}->>'given_name'), ''), '') || ' ' || "
        f"coalesce(nullif(trim({meta}->>'last_name'), ''), "
        f"nullif(trim({meta}->>'family_name'), ''), '')), '')"
    )
    return (
        "coalesce("
        f"nullif(trim({meta}->>'display_name'), ''), "
        f"nullif(trim({meta}->>'name'), ''), "
        f"nullif(trim({meta}->>'full_name'), ''), "
        f"{first_last})"
    )


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
            f"from auth.users where {_ACTIVE}")
        # Excluded (banned/anon/deleted) surfaced separately — never folded into totals.
        excluded = _query(
            f"select count(*)::int as excluded from auth.users where not ({_ACTIVE})")
        # Zero-filled 30-day calendar: a generate_series scaffold LEFT JOINed to the
        # per-day counts, so every day 0..29 appears (n=0 where none) and gap days
        # can't shift later bars left.
        series = _query(
            "select to_char(d.day, 'YYYY-MM-DD') as day, coalesce(c.n, 0)::int as n "
            "from generate_series("
            "date_trunc('day', now()) - interval '29 days', "
            "date_trunc('day', now()), interval '1 day') as d(day) "
            "left join (select date_trunc('day', created_at) as day, count(*)::int as n "
            f"from auth.users where {_ACTIVE} "
            "and created_at > now() - interval '30 days' group by 1) as c "
            "on c.day = d.day order by d.day")
        providers = _query(
            "select coalesce(raw_app_meta_data->>'provider','email') as provider, "
            f"count(*)::int as n from auth.users where {_ACTIVE} group by 1 order by 2 desc")
        return {"ok": True, "summary": (agg or [{}])[0],
                "excluded": (excluded or [{}])[0].get("excluded", 0),
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
            f"{display_name_sql('u')} as name, "
            "coalesce(raw_app_meta_data->>'provider','email') as provider, "
            "to_char(created_at,'YYYY-MM-DD HH24:MI') as created_at, "
            "to_char(last_sign_in_at,'YYYY-MM-DD HH24:MI') as last_sign_in_at, "
            "(email_confirmed_at is not null) as confirmed "
            f"from auth.users u where {_ACTIVE} order by created_at desc limit {n}")
        return {"ok": True, "users": rows or []}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def subscribers(limit: int = 200) -> dict:
    """Paid + trialing entitlement roster joined to auth.users email (MNZ W2).

    Reads public.user_entitlements (written by the Stripe webhook/reconciler in
    app/billing.py) via the same read-only Management API path as the user roster.
    Degrades gracefully when the table does not exist yet (returns ok:False + error).
    """
    if not status()["configured"]:
        return {"ok": False, **status()}
    try:
        n = max(1, min(500, int(limit)))   # int-clamped → safe to interpolate
        summary = _query(
            "select tier, status, count(*)::int as n "
            "from public.user_entitlements group by 1,2 order by 1,2")
        rows = _query(
            "select coalesce(u.email, e.user_id::text) as email, "
            f"{display_name_sql('u')} as name, "
            "e.tier, e.status, e.source, "
            "to_char(e.current_period_end,'YYYY-MM-DD') as renews, "
            "e.stripe_customer_id, "
            "to_char(e.updated_at,'YYYY-MM-DD HH24:MI') as updated_at "
            "from public.user_entitlements e "
            "left join auth.users u on u.id = e.user_id "
            "where e.tier <> 'free' or e.status in ('active','trialing','past_due') "
            f"order by e.updated_at desc limit {n}")
        return {"ok": True, "summary": summary or [], "subscribers": rows or []}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
