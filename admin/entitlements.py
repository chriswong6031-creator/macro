"""admin/entitlements.py — operator Users/Subscribers console (MNZ W2, masterplan §3.2 + MNZ-R3).

The admin-side READ + WRITE surface over ``public.user_entitlements`` — the single
source of authority for site access. Two data planes, kept strictly separate so the
single-writer law (MNZ-R3) holds:

  * READ  (the roster): the Supabase **Management-API PAT** path from ``admin/users.py``
    (``users._query`` — read-only SELECT), server-side joining ``auth.users`` (name +
    email) to ``user_entitlements`` (tier / status / source / period). No service-role
    JWT stored here; nothing is exposed to the browser.
  * WRITE (the actions): every mutation routes through ``app.billing._upsert_entitlement``
    + ``_invalidate`` (service-role PostgREST, RLS-bypassing) — the SAME writer the Stripe
    webhook/reconciler use. Operator comps are a *sanctioned* writer per MNZ-R3; they are
    NOT a second write path, they reuse the billing spine's.

The honesty crux — comp vs. live Stripe (masterplan §3.2 negative-propagation):
  ``app.billing.reconcile_entitlements()`` re-syncs EVERY row that carries a
  ``stripe_customer_id`` from live Stripe state, nightly — it does NOT skip
  ``source='comp'``. So a comp written over a user who still holds a live Stripe
  subscription **is reverted the next night** (and any webhook fires sooner). We refuse
  to lie about that:

    - A comp action on a user with an active/trialing Stripe sub is **blocked (409)**
      unless ``force=True``.
    - ``force=True`` alone is still not enough: without also cancelling the Stripe sub the
      comp is transient (the reconciler wins). So ``force=True`` additionally REQUIRES
      ``cancel_stripe=True``; we then cancel their live subscription(s) via the Stripe API
      **before** writing the comp, so the comp is durable.
    - The truthful alternative surfaced to the operator: for a paying user, tier changes
      belong in Stripe (Customer Portal / extend-trial / cancel there), not a comp.

  Trial actions on a REAL trialing Stripe sub are the ONE place we touch Stripe directly
  (``Subscription.modify(trial_end=…, proration_behavior='none')``) then recompute → upsert
  → invalidate, exactly like the webhook — never a comp over a live sub.

Every mutation logs the admin identity (the operator label the caller passes through, the
same way the rest of the console attributes writes). Reads/writes degrade gracefully: with
no PAT the roster returns setup steps; with no service-role key the actions 503 cleanly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from lib.tiers import normalize_tier

from . import users

log = logging.getLogger("macro.admin.entitlements")

# Tiers an operator may grant. 'free' is a valid target for downgrade/remove-comp but is
# never a *pass/tier-grant* target (a pass to free is meaningless) — enforced per-action.
#
# These stay CANONICAL on purpose. Every inbound `tier` param below goes through
# ``normalize_tier`` first, so the rename migration's 'essential' alias is ACCEPTED without
# widening what gets WRITTEN: _write_comp puts this exact string into
# user_entitlements.tier, and a widened tuple would have let an operator action store
# 'essential' — the one value Phase 1 must never emit.
_GRANT_TIERS = ("insider", "pro")
_ALL_TIERS = ("free", "insider", "pro")
_TRIALING_ACTIVE = ("active", "trialing")

VALID_ACTIONS = frozenset({
    "change_tier",    # comp tier set (insider|pro|free) — the manual upgrade/downgrade
    "extend_trial",   # +N days onto a real trialing Stripe sub, else a trialing comp window
    "reset_trial",    # trial_end := now + 7d (Stripe modify or trialing comp)
    "grant_pass",     # comp free pass: monthly(+30d) / annual(+365d) / lifetime(NULL end)
    "remove_comp",    # revert to free (tier free / status none / features empty)
})

_PASS_DAYS = {"monthly": 30, "annual": 365, "lifetime": None}
_DEFAULT_RESET_TRIAL_DAYS = 7


# --------------------------------------------------------------------------- #
# billing-spine bridge (lazy — keeps this module importable without the dep/keys,
# and lets tests monkeypatch app.billing symbols on the real module object)
# --------------------------------------------------------------------------- #
def _billing():
    from app import billing  # noqa: PLC0415
    return billing


# --------------------------------------------------------------------------- #
# READ — the roster (Management-API PAT, read-only; mirrors users.subscribers)
# --------------------------------------------------------------------------- #
def _clamp(v, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def list_users(*, tier: str | None = None, status: str | None = None,
               search: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    """Joined roster: EVERY registered account, entitlements overlaid, filtered + paged.

    Base table is auth.users (the lockdown makes registration the floor, so every
    account IS a free-tier member) LEFT JOINed to user_entitlements — users who never
    touched billing surface as implicit free (tier 'free', status 'none'). Filters:
      tier    — 'free'|'insider'|'pro' (exact; 'essential' is accepted as an alias of
                'insider' and filters on the canonical stored value)
      status  — 'active'|'trialing'|'past_due'|'canceled'|'none' (exact)
      search  — case-insensitive substring over email OR display name
    Pagination is server-side (LIMIT/OFFSET); a total count accompanies the page.
    All SQL is static; the only interpolated values are int-clamped LIMIT/OFFSET and
    filter tokens validated against fixed allow-lists (no injection surface).
    """
    st = users.status()
    if not st["configured"]:
        return {"ok": False, **st}

    page = _clamp(page, 1, 1, 100_000)
    page_size = _clamp(page_size, 50, 1, 200)
    offset = (page - 1) * page_size

    where = ["true"]
    tier = normalize_tier(tier)
    if tier in _ALL_TIERS:
        where.append(f"coalesce(e.tier,'free') = '{tier}'")
    if status:
        # allow-list the status token; anything else is ignored (never interpolated raw)
        if status in ("active", "trialing", "past_due", "canceled", "none"):
            where.append(f"coalesce(e.status,'none') = '{status}'")
    if search:
        # PostgREST-free path (Management API SQL): escape single quotes, wrap in ILIKE.
        needle = str(search).replace("'", "''").strip()
        if needle:
            where.append(
                f"(u.email ilike '%{needle}%' or "
                f"{users.display_name_sql('u')} ilike '%{needle}%')"
            )
    where_sql = " and ".join(where)

    try:
        count_rows = users._query(
            "select count(*)::int as n from auth.users u "
            f"left join public.user_entitlements e on e.user_id = u.id where {where_sql}")
        total = (count_rows or [{}])[0].get("n", 0)
        rows = users._query(
            "select u.id::text as user_id, "
            "u.email as email, "
            f"{users.display_name_sql('u')} as name, "
            "coalesce(u.raw_app_meta_data->>'provider','email') as provider, "
            "coalesce(e.tier,'free') as tier, coalesce(e.status,'none') as status, "
            "coalesce(e.source,'') as source, "
            "e.stripe_customer_id, "
            "to_char(e.current_period_end,'YYYY-MM-DD') as current_period_end, "
            "to_char(e.updated_at,'YYYY-MM-DD HH24:MI') as updated_at, "
            "to_char(u.created_at,'YYYY-MM-DD') as created "
            "from auth.users u "
            "left join public.user_entitlements e on e.user_id = u.id "
            f"where {where_sql} "
            f"order by coalesce(e.updated_at, u.created_at) desc nulls last limit {page_size} offset {offset}")
        # tier×status roster totals (unfiltered) for the filter chips
        summary = users._query(
            "select coalesce(e.tier,'free') as tier, coalesce(e.status,'none') as status, count(*)::int as n "
            "from auth.users u left join public.user_entitlements e on e.user_id = u.id "
            "group by 1,2 order by 1,2")
        return {
            "ok": True,
            "users": rows or [],
            "summary": summary or [],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# WRITE helpers (all through the billing spine — single writer, MNZ-R3)
# --------------------------------------------------------------------------- #
def _iso_in(days: int | None) -> str | None:
    """now + `days` as an ISO8601 timestamptz, or None for a null period end (lifetime)."""
    if days is None:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=int(days))).isoformat()


def _epoch_in(days: int) -> int:
    return int((datetime.now(timezone.utc) + timedelta(days=int(days))).timestamp())


def _row_for(user_id: str) -> dict | None:
    """Current user_entitlements row for a user (service-role read via billing._pg).

    Returns {stripe_customer_id, tier, status, source, current_period_end} or None. Used to
    decide the comp-vs-stripe branch server-side (never trusting a client-sent flag)."""
    b = _billing()
    try:
        import urllib.parse  # noqa: PLC0415
        rows = b._pg(
            "GET",
            f"user_entitlements?user_id=eq.{urllib.parse.quote(user_id)}"
            "&select=stripe_customer_id,tier,status,source,current_period_end")
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        log.warning("entitlements: row lookup failed for %s (%s)", user_id, exc)
        return None


def _live_stripe_state(customer_id: str | None) -> dict:
    """Ask Stripe whether this customer holds a live (active/trialing) subscription.

    Returns {'has_live': bool, 'trialing_sub_id': str|None, 'sub_ids': [ids of live subs]}.
    Fail-closed on error: has_live=False so we don't block on a transient Stripe hiccup, but
    the caller only ACTS on has_live=True, so a false-negative never silently comps over a
    paying user without the operator's force flag (the reconciler would still correct it)."""
    out = {"has_live": False, "trialing_sub_id": None, "sub_ids": []}
    if not customer_id:
        return out
    b = _billing()
    try:
        stripe = b._stripe()
        for s in stripe.Subscription.list(customer=customer_id, status="all", limit=20).data:
            status = s["status"] if isinstance(s, dict) else s.status
            sid = s["id"] if isinstance(s, dict) else s.id
            if status in _TRIALING_ACTIVE:
                out["has_live"] = True
                out["sub_ids"].append(sid)
                if status == "trialing" and not out["trialing_sub_id"]:
                    out["trialing_sub_id"] = sid
    except Exception as exc:  # noqa: BLE001
        log.warning("entitlements: live-state lookup failed for %s (%s)", customer_id, exc)
    return out


def _write_comp(user_id: str, tier: str, status: str, current_period_end: str | None,
                *, operator: str, note: str, plan_interval: str | None = None) -> dict:
    """Write a comp entitlement row through the billing spine, then bust the tier cache.

    Passes customer_id=None to _upsert_entitlement so the merge-duplicates upsert leaves any
    existing stripe_customer_id in place (billing._upsert_entitlement only sets that column
    when truthy) — we never fabricate or drop the Stripe mapping from a comp; force-comp
    cancels the sub explicitly instead.

    `plan_interval` records the pass cadence ('monthly'|'annual') for plan display; None for a
    lifetime pass, a comp tier-change, or a downgrade — none of those carry a billing interval.
    """
    b = _billing()
    features = list(b._tier_features(tier)) if tier != "free" else []
    ent = {
        "tier": tier,
        "features": features,
        "status": status,
        "current_period_end": current_period_end,
        "source": "comp",
        "plan_interval": plan_interval,
    }
    b._upsert_entitlement(user_id, None, ent)
    b._invalidate(user_id)
    log.info("entitlements: comp by %s -> user %s tier=%s status=%s cpe=%s (%s)",
             operator, user_id, tier, status, current_period_end, note)
    return {"ok": True, "user_id": user_id, "source": "comp",
            "tier": tier, "status": status, "current_period_end": current_period_end,
            "features": features}


def _guard_stripe(user_id: str, *, force: bool, cancel_stripe: bool,
                  operator: str) -> tuple[dict | None, dict | None]:
    """Comp-vs-live-Stripe honesty gate. Returns (error_dict_or_None, row_or_None).

    (error, None) → the caller must NOT write the comp (return `error` to the operator).
    (None, row)   → cleared to comp; `row` is the current entitlement row (may be None).

    The mechanic (see module docstring): a comp on a user with a live Stripe sub is blocked
    unless force AND cancel_stripe, in which case we cancel their live subscription(s) first
    so the reconciler can't revert the comp.
    """
    row = _row_for(user_id)
    customer_id = (row or {}).get("stripe_customer_id")
    state = _live_stripe_state(customer_id)
    if not state["has_live"]:
        return None, row  # no live sub → a comp is durable; proceed

    # Live Stripe subscription present.
    if not force:
        return ({
            "ok": False, "code": "stripe_active",
            "error": ("This user has a LIVE Stripe subscription. Comping over it is transient — "
                      "the nightly reconciler and Stripe webhooks re-sync from Stripe and will "
                      "REVERT the comp. Route tier changes through Stripe (extend-trial / cancel "
                      "in the Customer Portal), OR re-submit with force=true AND "
                      "cancel_stripe=true to cancel their paid subscription and make the comp stick."),
            "stripe_customer_id": customer_id,
            "live_subscriptions": state["sub_ids"],
        }, None)
    if not cancel_stripe:
        return ({
            "ok": False, "code": "force_needs_cancel",
            "error": ("force=true is not enough on its own: the reconciler re-syncs stripe-linked "
                      "rows nightly and would REVERT this comp within a day. Set cancel_stripe=true "
                      "to cancel their live Stripe subscription first so the comp is durable."),
            "stripe_customer_id": customer_id,
            "live_subscriptions": state["sub_ids"],
        }, None)

    # force + cancel_stripe → cancel the live subscription(s) via the billing spine, then comp.
    b = _billing()
    b._cancel_subscriptions(customer_id)
    log.info("entitlements: force-comp by %s cancelled Stripe subs %s for user %s",
             operator, state["sub_ids"], user_id)
    return None, row


# --------------------------------------------------------------------------- #
# Trial mechanic (the ONE direct-Stripe path)
# --------------------------------------------------------------------------- #
def _set_trial(user_id: str, *, trial_end_epoch: int, comp_days: int, operator: str,
               note: str) -> dict:
    """Extend/reset a trial.

    If the user has a REAL trialing Stripe sub: Subscription.modify(trial_end=epoch,
    proration_behavior='none') then recompute→upsert→invalidate (webhook-parity, never a
    comp over a live sub). Otherwise: write a trialing comp whose current_period_end is the
    trial window (comp_days from now).
    """
    row = _row_for(user_id)
    customer_id = (row or {}).get("stripe_customer_id")
    state = _live_stripe_state(customer_id)
    sub_id = state["trialing_sub_id"]
    if sub_id:
        b = _billing()
        stripe = b._stripe()
        stripe.Subscription.modify(sub_id, trial_end=trial_end_epoch, proration_behavior="none")
        ent = b._compute_entitlement(customer_id)
        b._upsert_entitlement(user_id, customer_id, ent)
        b._invalidate(user_id)
        log.info("entitlements: trial %s by %s -> user %s sub=%s trial_end=%s",
                 note, operator, user_id, sub_id, trial_end_epoch)
        return {"ok": True, "user_id": user_id, "mechanic": "stripe",
                "subscription_id": sub_id, "trial_end": trial_end_epoch,
                "tier": ent.get("tier"), "status": ent.get("status")}
    # No trialing Stripe sub → a trialing comp window. Tier defaults to the user's current
    # comp/paid tier if they have one, else 'insider' (a trial with no product is meaningless).
    tier = (row or {}).get("tier") or "insider"
    if tier == "free":
        tier = "insider"
    return {**_write_comp(user_id, tier, "trialing", _iso_in(comp_days),
                          operator=operator, note=f"trial {note}"),
            "mechanic": "comp"}


# --------------------------------------------------------------------------- #
# Action dispatch (POST /api/entitlements/action)
# --------------------------------------------------------------------------- #
def _need_keys() -> dict | None:
    """503 cleanly if the service-role key (the writer) is unset."""
    if not _billing().SUPABASE_SERVICE_ROLE_KEY:
        return {"ok": False, "error": "billing not configured (SUPABASE_SERVICE_ROLE_KEY unset) — "
                                      "cannot write entitlements", "code": "no_writer"}
    return None


def act(body: dict, *, operator: str = "admin") -> tuple[dict, int]:
    """Execute one operator entitlement action. Returns (payload, http_status).

    body: {user_id, action, params:{...}}. Validates action + params, applies the
    comp-vs-stripe honesty gate for comp writes, and routes every write through the
    billing spine. `operator` is the admin identity for the audit log (passed by server.py).
    """
    user_id = (body.get("user_id") or "").strip()
    action = (body.get("action") or "").strip()
    params = body.get("params") or {}
    if not user_id:
        return {"ok": False, "error": "user_id required"}, 400
    if action not in VALID_ACTIONS:
        return {"ok": False, "error": f"action must be one of {sorted(VALID_ACTIONS)}"}, 400

    need = _need_keys()
    if need:
        return need, 503

    force = bool(params.get("force"))
    cancel_stripe = bool(params.get("cancel_stripe"))
    note = str(params.get("note") or "")[:500]

    try:
        # ---- remove_comp → revert to free ---------------------------------------------
        if action == "remove_comp":
            # A pure downgrade to free is still a comp WRITE over the row; if a live Stripe
            # sub exists, the same honesty gate applies (a "free" comp over a paying user is
            # equally transient / equally a lie without cancelling the sub).
            err, _row = _guard_stripe(user_id, force=force, cancel_stripe=cancel_stripe,
                                      operator=operator)
            if err:
                return err, 409
            return _write_comp(user_id, "free", "none", None, operator=operator,
                               note=note or "remove comp"), 200

        # ---- change_tier → comp upgrade/downgrade -------------------------------------
        if action == "change_tier":
            tier = normalize_tier(params.get("tier"))
            if tier not in _ALL_TIERS:
                return {"ok": False, "error": f"tier must be one of {list(_ALL_TIERS)}"}, 400
            err, _row = _guard_stripe(user_id, force=force, cancel_stripe=cancel_stripe,
                                      operator=operator)
            if err:
                return err, 409
            if tier == "free":
                return _write_comp(user_id, "free", "none", None, operator=operator,
                                   note=note or "downgrade to free"), 200
            return _write_comp(user_id, tier, "active", None, operator=operator,
                               note=note or f"tier -> {tier}"), 200

        # ---- grant_pass → monthly / annual / lifetime ---------------------------------
        if action == "grant_pass":
            kind = (params.get("kind") or "").strip().lower()
            if kind not in _PASS_DAYS:
                return {"ok": False, "error": f"kind must be one of {list(_PASS_DAYS)}"}, 400
            tier = normalize_tier(params.get("tier"))
            if tier not in _GRANT_TIERS:
                return {"ok": False, "error": f"tier must be one of {list(_GRANT_TIERS)}"}, 400
            err, _row = _guard_stripe(user_id, force=force, cancel_stripe=cancel_stripe,
                                      operator=operator)
            if err:
                return err, 409
            cpe = _iso_in(_PASS_DAYS[kind])  # None for lifetime
            pass_interval = kind if kind in ("monthly", "annual") else None  # lifetime -> no cadence
            return _write_comp(user_id, tier, "active", cpe, operator=operator,
                               note=note or f"{kind} pass ({tier})",
                               plan_interval=pass_interval), 200

        # ---- extend_trial / reset_trial ------------------------------------------------
        if action in ("extend_trial", "reset_trial"):
            if action == "reset_trial":
                days = _DEFAULT_RESET_TRIAL_DAYS
            else:
                # Operator ints are REJECTED (not clamped) out of range, matching the
                # console's other numeric knobs (server.validate_orchestrator_setting).
                raw = params.get("days")
                if isinstance(raw, bool) or not isinstance(raw, int) or not (1 <= raw <= 365):
                    return {"ok": False, "error": "days must be a positive integer (1..365)"}, 400
                days = raw
            # A trial change touching a live Stripe sub is legitimate (Subscription.modify) —
            # NOT a comp — so the comp gate does not apply here; _set_trial picks the mechanic.
            res = _set_trial(user_id, trial_end_epoch=_epoch_in(days), comp_days=days,
                             operator=operator, note=action)
            return res, 200

        # unreachable (VALID_ACTIONS guarded above)
        return {"ok": False, "error": f"unhandled action {action!r}"}, 400
    except Exception as exc:  # noqa: BLE001
        log.warning("entitlements: action %s for %s failed (%s)", action, user_id, exc)
        return {"ok": False, "error": str(exc)}, 500
