"""Supabase user tracking via the Management API SQL endpoint.

The site's accounts run on Supabase (Google OAuth + email/password, #761). We
read the user roster from auth.users with a Personal Access Token
(SUPABASE_ACCESS_TOKEN, the sbp_… token), running read-only SELECTs through the
Management API's database-query endpoint. No service_role JWT to store, and
nothing is exposed to the browser. All SQL is static text authored here (the
only interpolated value is an int-clamped LIMIT), so there is no injection
surface. Degrades gracefully: with no PAT it returns setup steps.

PASSWORD RESET (the one WRITE here) uses a second, separate plane: the GoTrue
admin API with ``SUPABASE_SERVICE_ROLE_KEY`` (the same key app/billing.py already
holds — this is not a new secret). The Management-API PAT cannot set a password:
it runs SQL, and ``auth.users.encrypted_password`` is GoTrue's private storage,
not a column an operator may safely hand-hash.

Why a DIRECT set and not "email them a recovery link" — the honest constraint:

  templates/theme.js pins the browser SDK to ``flowType:'pkce'``, and the vendored
  gotrue-js throws "Not a valid PKCE flow url." on any return URL that is not a
  ``?code=`` the SAME browser initiated (it needs the code_verifier it stored).
  A recovery link minted server-side — by this console, by ``POST /auth/v1/recover``,
  or by the **Supabase dashboard's own "Reset password" button** — carries no
  code_challenge, so GoTrue returns it as an implicit ``#access_token=…&type=recovery``
  fragment, which that client refuses BY DESIGN (anti session-fixation). Such a link
  lands on the site and silently does nothing.

  So a server-issued link is not a reset mechanism here, and offering one from this
  console would be shipping a button that cannot work. The two paths that DO work:
  the customer clicking "Forgot your password?" on the site (browser-initiated, so
  PKCE holds end to end), and this direct set, which involves no link at all.
"""
from __future__ import annotations

import logging
import re
import secrets
import string

from . import actions, settings

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

log = logging.getLogger("macro.admin.users")

_API = "https://api.supabase.com/v1"
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# GoTrue's own floor is 6; the site's sign-up forms ask for 8, so an operator-set
# password may never be weaker than what a customer would have been made to choose.
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 72          # bcrypt truncates past 72 bytes — refuse rather than silently cut

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


# --------------------------------------------------------------------------- #
# WRITE — operator password reset (GoTrue admin API, service-role)
# --------------------------------------------------------------------------- #
def _lit(value, *, maxlen: int) -> str:
    """A safe single-quoted SQL literal: length-capped, NUL-stripped, quotes doubled."""
    s = str(value if value is not None else "")[:maxlen].replace("\x00", "")
    return "'" + s.replace("'", "''") + "'"


def _billing():
    from app import billing  # noqa: PLC0415
    return billing


def password_reset_status() -> dict:
    """Whether the WRITE plane is usable (separate from the PAT read plane)."""
    try:
        key = bool(_billing().SUPABASE_SERVICE_ROLE_KEY)
    except Exception:  # noqa: BLE001 — app.billing may be unimportable without deps
        key = False
    return {
        "configured": bool(key and requests),
        "reason": None if (key and requests) else (
            "requests not installed" if not requests
            else "SUPABASE_SERVICE_ROLE_KEY not set in the admin service env"),
    }


def generate_password(length: int = 20) -> str:
    """A strong random password the operator hands over out-of-band.

    Ambiguous glyphs (O/0, l/1/I) are excluded because this string gets read aloud,
    pasted into chat, or typed from a screenshot — a password the customer cannot
    retype is a support ticket, not a reset.
    """
    alphabet = ((string.ascii_lowercase + string.ascii_uppercase + string.digits)
                .translate(str.maketrans("", "", "O0lI1"))) + "!@#$%^&*-_=+"
    n = max(MIN_PASSWORD_LEN, min(MAX_PASSWORD_LEN, int(length)))
    return "".join(secrets.choice(alphabet) for _ in range(n))


def lookup(identifier: str) -> dict:
    """Resolve an email or a uuid to one auth.users row. Read plane (PAT)."""
    ident = str(identifier or "").strip()
    if not ident:
        return {"ok": False, "error": "email or user id required"}
    if not status()["configured"]:
        return {"ok": False, **status()}
    try:
        if _UUID_RE.match(ident):
            where = f"u.id = {_lit(ident, maxlen=64)}::uuid"
        else:
            where = f"lower(u.email) = lower({_lit(ident, maxlen=320)})"
        rows = _query(
            "select u.id::text as user_id, u.email, "
            f"{display_name_sql('u')} as name, "
            "coalesce(u.raw_app_meta_data->>'provider','email') as provider, "
            "(u.email_confirmed_at is not null) as confirmed, "
            "to_char(u.last_sign_in_at,'YYYY-MM-DD HH24:MI') as last_sign_in_at "
            f"from auth.users u where {where} and {_ACTIVE} limit 2")
        if not rows:
            return {"ok": False, "error": f"no active account for {ident!r}", "code": "not_found"}
        if len(rows) > 1:                      # only reachable for a duplicated email
            return {"ok": False, "error": f"{ident!r} matches more than one account — "
                                          "use the user id", "code": "ambiguous"}
        return {"ok": True, "user": rows[0]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def set_password(identifier: str, password: str | None = None, *,
                 operator: str = "operator") -> tuple[dict, int]:
    """Set a user's password directly via the GoTrue admin API.

    `password=None` mints a strong random one and returns it ONCE — it is never
    stored, never logged, and never written to the operator ledger (the ledger
    records that a reset happened and for whom, which is the auditable fact).

    Returns (payload, http_status).
    """
    st = password_reset_status()
    if not st["configured"]:
        return {"ok": False, "error": st["reason"], "code": "no_writer",
                "setup_steps": [
                    "Supabase dashboard → Project Settings → API → copy the service_role key.",
                    "Set SUPABASE_SERVICE_ROLE_KEY in the admin service env.",
                    "Restart the admin service.",
                ]}, 503

    found = lookup(identifier)
    if not found.get("ok"):
        return found, (404 if found.get("code") == "not_found" else 400)
    user = found["user"]

    generated = password is None
    pw = generate_password() if generated else str(password)
    if len(pw) < MIN_PASSWORD_LEN:
        return {"ok": False, "error": f"password must be at least {MIN_PASSWORD_LEN} characters"}, 400
    if len(pw.encode("utf-8")) > MAX_PASSWORD_LEN:
        return {"ok": False, "error": f"password must be at most {MAX_PASSWORD_LEN} bytes "
                                      "(bcrypt truncates past that)"}, 400

    b = _billing()
    try:
        r = requests.put(
            f"{b.SUPABASE_URL}/auth/v1/admin/users/{user['user_id']}",
            headers={"apikey": b.SUPABASE_SERVICE_ROLE_KEY,
                     "Authorization": f"Bearer {b.SUPABASE_SERVICE_ROLE_KEY}",
                     "Content-Type": "application/json"},
            json={"password": pw}, timeout=15)
    except Exception as e:  # noqa: BLE001
        log.warning("users: password reset transport failure for %s (%s)", user["email"], e)
        return {"ok": False, "error": f"could not reach GoTrue: {e}"}, 502
    if not (200 <= r.status_code < 300):
        # Surface GoTrue's own words — a weak-password policy rejection and an
        # expired service-role key fail here identically otherwise.
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}, 502

    actions.append_action(
        surface=f"password_reset:{user['email']}",
        action="overrode",
        direction_note=(f"operator {operator} set a new password for {user['email']} "
                        f"({'generated' if generated else 'operator-supplied'}); "
                        "existing sessions are NOT revoked by this write"))
    log.info("users: password reset for %s by %s (generated=%s)",
             user["email"], operator, generated)
    return {"ok": True, "user": {k: user[k] for k in ("user_id", "email", "name", "provider")},
            # Returned once, to the operator's own browser, over the admin console's
            # authenticated channel. Not persisted anywhere on this side.
            "password": pw if generated else None,
            "generated": generated,
            "note": "Hand this to the customer over a channel you trust, and tell them to "
                    "change it after signing in. Their existing sessions stay valid."}, 200


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
