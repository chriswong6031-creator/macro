"""app/billing.py — Stripe billing spine (MNZ W2, masterplan §3.2).

The WRITER side of the entitlement contract that brain_gateway._resolve_tier already
reads. Four surfaces, mounted on the macro-api FastAPI app:

  POST /api/billing/checkout  — authed; create a Stripe Checkout Session (subscription,
                                7-day card-required trial) and return its hosted URL.
  POST /api/billing/webhook   — unauthed but signature-verified; on every relevant event
                                RECOMPUTE the customer's entitlement from live Stripe state
                                and upsert public.user_entitlements, then bust the tier cache.
  GET  /api/billing/portal    — authed; return a Stripe Customer Portal URL (upgrade/cancel).
  reconcile_entitlements()    — CLI/cron re-sync (`python -m app.billing --reconcile`), off
                                the render path; also a webhook-failure backstop.

Design notes
------------
* **Naturally idempotent.** Every webhook handler ignores the event's *delta* and instead
  recomputes {tier, features, status, current_period_end} from the customer's current
  subscriptions + active entitlements, then upserts. Replaying any event — or processing them
  out of order — converges to the same row. The `stripe_events` ledger only short-circuits
  obvious replays to save Stripe API calls.
* **Negative propagation.** cancel / delete recompute to tier='free'. A chargeback
  (`charge.dispute.created`) additionally cancels the customer's live subscriptions first, so the
  free downgrade STICKS (a later subscription.* event can't re-grant); refunds / failed invoices
  recompute + bust the cache. The cache-bust makes any downgrade effective within one request, not
  one TTL. (Refunds are not auto-revoking — often partial/goodwill; revoke by canceling the sub.)
* **Prices are addressed by lookup_key** (config/plans.yml), never by hardcoded id, so the same
  code runs unchanged against test and live objects created by scripts/stripe_bootstrap.py.
* **Only the service-role writes.** Reads/writes to Supabase use SUPABASE_SERVICE_ROLE_KEY over
  PostgREST (RLS-bypassing); the browser never writes entitlements.

Secrets (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, SUPABASE_SERVICE_ROLE_KEY) come from
/etc/macro-api.env — never the repo. If STRIPE_SECRET_KEY is absent the routes 503 cleanly.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

log = logging.getLogger("macro.billing")
router = APIRouter()

# --------------------------------------------------------------------------- #
# Config / environment
# --------------------------------------------------------------------------- #
REPO = Path(os.environ.get("MACRO_REPO") or Path(__file__).resolve().parents[1])
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fsldfzlxyavsuwqbceod.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
# Where hosted Checkout / Portal return the browser. Apex, not www (www has broken edge TLS).
MM_SITE_BASE = os.environ.get("MM_SITE_BASE", "https://mastermind-x.com").rstrip("/")
# Stripe Tax is an account-level setting (origin address required). Default ON per masterplan;
# the operator can force it off with STRIPE_AUTOMATIC_TAX=0 until the account is configured.
_AUTOMATIC_TAX = os.environ.get("STRIPE_AUTOMATIC_TAX", "1") not in ("0", "false", "no", "")

_CATALOG: dict | None = None


def _catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        import yaml  # noqa: PLC0415
        with (REPO / "config" / "plans.yml").open() as fh:
            _CATALOG = yaml.safe_load(fh)
    return _CATALOG


def _tier_rank() -> list[str]:
    return list(_catalog().get("tier_rank", ["free", "insider", "pro"]))


def _lookup_key_to_tier() -> dict[str, str]:
    """price lookup_key -> tier string (insider_monthly -> 'insider', …)."""
    out: dict[str, str] = {}
    for prod in _catalog()["products"].values():
        for pspec in prod["prices"].values():
            out[pspec["lookup_key"]] = prod["tier"]
    return out


def _tier_to_lookup_key(tier: str, interval: str) -> str | None:
    for prod in _catalog()["products"].values():
        if prod["tier"] == tier:
            spec = prod["prices"].get(interval)
            return spec["lookup_key"] if spec else None
    return None


def _tier_trial_days(tier: str) -> int:
    for prod in _catalog()["products"].values():
        if prod["tier"] == tier:
            return int(prod.get("trial_days", 0))
    return 0


def _tier_features(tier: str) -> list[str]:
    for prod in _catalog()["products"].values():
        if prod["tier"] == tier:
            return list(prod.get("features", []))
    return []


# --------------------------------------------------------------------------- #
# Stripe client (lazy — keeps the API process importable without the dep/key)
# --------------------------------------------------------------------------- #
def _stripe():
    try:
        import stripe  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(503, "billing unavailable: stripe SDK not installed") from exc
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        raise HTTPException(503, "billing not configured (STRIPE_SECRET_KEY unset)")
    stripe.api_key = key
    return stripe


_PRICE_CACHE: dict[str, tuple[str, float]] = {}  # lookup_key -> (price_id, expire_ts)
_PRICE_CACHE_LOCK = threading.Lock()


def _price_id(lookup_key: str) -> str:
    now = time.monotonic()
    with _PRICE_CACHE_LOCK:
        hit = _PRICE_CACHE.get(lookup_key)
        if hit and hit[1] > now:
            return hit[0]
    stripe = _stripe()
    data = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1).data
    if not data:
        raise HTTPException(500, f"price '{lookup_key}' not found in Stripe — run scripts/stripe_bootstrap.py")
    pid = data[0].id
    with _PRICE_CACHE_LOCK:
        _PRICE_CACHE[lookup_key] = (pid, now + 300)
    return pid


# --------------------------------------------------------------------------- #
# PostgREST helpers (service-role — mirrors app/main.py _mm_analytics_insert)
# --------------------------------------------------------------------------- #
def _pg(method: str, path: str, body: Any = None, prefer: str | None = None, timeout: int = 6) -> Any:
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY unset")
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def _existing_customer(user_id: str) -> str | None:
    try:
        rows = _pg("GET", f"user_entitlements?user_id=eq.{urllib.parse.quote(user_id)}&select=stripe_customer_id")
        if rows and rows[0].get("stripe_customer_id"):
            return rows[0]["stripe_customer_id"]
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: customer lookup failed for %s (%s)", user_id, exc)
    return None


def _user_for_customer(customer_id: str) -> str | None:
    try:
        rows = _pg("GET", f"user_entitlements?stripe_customer_id=eq.{urllib.parse.quote(customer_id)}&select=user_id")
        if rows:
            return rows[0].get("user_id")
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: user lookup failed for %s (%s)", customer_id, exc)
    return None


def read_entitlement(user_id: str) -> dict:
    """Full entitlement row for a user: {tier, features, status, current_period_end, source}.

    Fail-safe to the free default (table/key absent, network error → free). Used by
    /api/me and /api/account for plan display + client-side Pro gating. `source`
    ('stripe'|'substack'|'comp') lets the client distinguish a comp/lifetime grant
    (source='comp' with a null current_period_end) from a canceled Stripe row.
    """
    default = {"tier": "free", "features": [], "status": "none", "current_period_end": None, "source": "stripe"}
    if not user_id or not SUPABASE_SERVICE_ROLE_KEY:
        return default
    try:
        rows = _pg(
            "GET",
            f"user_entitlements?user_id=eq.{urllib.parse.quote(user_id)}"
            "&select=tier,features,status,current_period_end,source",
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("billing: read_entitlement failed for %s (%s)", user_id, exc)
        return default
    if rows:
        r = rows[0]
        return {
            "tier": r.get("tier") or "free",
            "features": r.get("features") or [],
            "status": r.get("status") or "none",
            "current_period_end": r.get("current_period_end"),
            "source": r.get("source") or "stripe",
        }
    return default


def _upsert_entitlement(user_id: str, customer_id: str | None, ent: dict) -> None:
    row = {
        "user_id": user_id,
        "tier": ent["tier"],
        "features": ent["features"],
        "status": ent["status"],
        "current_period_end": ent["current_period_end"],
        "source": ent.get("source", "stripe"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if customer_id:
        row["stripe_customer_id"] = customer_id
    _pg("POST", "user_entitlements?on_conflict=user_id", body=[row],
        prefer="resolution=merge-duplicates,return=minimal")


def _persist_customer(user_id: str, customer_id: str) -> None:
    """Persist ONLY the user_id -> stripe_customer_id mapping, without touching tier/status/features.

    Used by the Elements /subscribe/init lane the instant a Stripe customer is created, BEFORE any
    subscription exists (card-up-front trial law). merge-duplicates on the user_id conflict target
    REPLACES exactly the columns present in the body, so shipping only {user_id, stripe_customer_id,
    updated_at} leaves an existing row's tier/status/current_period_end/features untouched (or, for a
    brand-new row, they default per the 0005 migration). The convergent webhook + the /complete
    recompute own the entitlement fields; this only pins the mapping so the webhook can resolve it.
    """
    _pg("POST", "user_entitlements?on_conflict=user_id",
        body=[{
            "user_id": user_id,
            "stripe_customer_id": customer_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }],
        prefer="resolution=merge-duplicates,return=minimal")


# --------------------------------------------------------------------------- #
# Tier-cache invalidation bridge (into brain_gateway, same process)
# --------------------------------------------------------------------------- #
def _invalidate(user_id: str) -> None:
    try:
        from engine.neuralweb.brain_gateway import invalidate_tier  # noqa: PLC0415
        invalidate_tier(user_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("billing: tier cache invalidate skipped (%s)", exc)


# --------------------------------------------------------------------------- #
# Entitlement computation from live Stripe state (the single source of truth)
# --------------------------------------------------------------------------- #
def _iso(epoch: int | None) -> str | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()


def _sub_items(sub: Any) -> list:
    try:
        return sub["items"]["data"] if isinstance(sub, dict) else sub.items.data
    except Exception:  # noqa: BLE001
        return []


def _sub_period_end(sub: Any) -> int | None:
    """Subscription current-period-end as an epoch int.

    Newer Stripe API versions (2025+) moved `current_period_end` OFF the subscription and
    onto each subscription item, so read the item level and fall back to the legacy top-level
    field for older versions.
    """
    top = sub.get("current_period_end") if isinstance(sub, dict) else getattr(sub, "current_period_end", None)
    if top:
        return top
    ends = []
    for it in _sub_items(sub):
        v = it.get("current_period_end") if isinstance(it, dict) else getattr(it, "current_period_end", None)
        if v:
            ends.append(v)
    return max(ends) if ends else None


def _sub_tier(sub: Any) -> str | None:
    """Resolve a subscription's tier from its item price lookup_keys.

    Returns the HIGHEST-ranked mapped tier across ALL items, so a multi-item subscription
    (add-ons, or a migrated sub carrying two prices) resolves by tier, not by item order.
    An unrecognized price contributes nothing → unknown-only subs return None (fail closed).
    """
    lk2t = _lookup_key_to_tier()
    rank = _tier_rank()
    found: list[str] = []
    for it in _sub_items(sub):
        price = it["price"] if isinstance(it, dict) else it.price
        lk = (price.get("lookup_key") if isinstance(price, dict) else price.lookup_key) or None
        if lk and lk in lk2t:
            found.append(lk2t[lk])
    if not found:
        return None
    return max(found, key=lambda t: rank.index(t) if t in rank else -1)


def _entitlement_from_state(subs: list[dict], entitlement_keys: list[str]) -> dict:
    """Pure reducer: (subscriptions, active-entitlement lookup_keys) -> entitlement row fields.

    subs items: {"status": str, "current_period_end": int|None, "tier": str|None}.
    Kept side-effect-free so it can be unit-tested without any network.
    """
    rank = _tier_rank()

    def rk(t: str | None) -> int:
        return rank.index(t) if t in rank else -1

    entitled = [s for s in subs if s.get("status") in ("active", "trialing") and s.get("tier")]
    if entitled:
        best = max(entitled, key=lambda s: rk(s["tier"]))
        tier = best["tier"]
        status = best["status"]
        cpe = best.get("current_period_end")
        features = list(entitlement_keys) if entitlement_keys else _tier_features(tier)
        return {"tier": tier, "status": status, "current_period_end": _iso(cpe), "features": features}

    # No entitling subscription → free. DELIBERATE, fail-closed: a `past_due` sub (soft decline in
    # Stripe's dunning window) is not in the entitled set above, so it lands here and loses access
    # immediately — consistent with the masterplan (MNZ: grace never extends to past_due/canceled).
    # The real status is still recorded for the admin view. If dunning-grace is ever wanted, it is a
    # read-side policy change (brain_gateway._get_allowance / the W3 paywall), not here.
    if subs:
        latest = max(subs, key=lambda s: s.get("current_period_end") or 0)
        status = latest.get("status") or "canceled"
        if status in ("active", "trialing"):  # entitled-but-no-tier (shouldn't happen) → treat as none
            status = "none"
        cpe = latest.get("current_period_end")
        return {"tier": "free", "status": status, "current_period_end": _iso(cpe), "features": []}

    return {"tier": "free", "status": "none", "current_period_end": None, "features": []}


def _compute_entitlement(customer_id: str) -> dict:
    """Fetch the customer's live Stripe state and reduce it to an entitlement row."""
    stripe = _stripe()
    raw_subs = stripe.Subscription.list(customer=customer_id, status="all", limit=20).data
    subs = [
        {"status": s.status, "current_period_end": _sub_period_end(s), "tier": _sub_tier(s)}
        for s in raw_subs
    ]
    keys: list[str] = []
    try:
        ents = stripe.entitlements.ActiveEntitlement.list(customer=customer_id, limit=100).data
        keys = [e.lookup_key for e in ents]
    except Exception as exc:  # noqa: BLE001 — entitlement propagation lag → config fallback in reducer
        log.debug("billing: active-entitlement list failed for %s (%s)", customer_id, exc)
    return _entitlement_from_state(subs, keys)


def _has_live_subscription(customer_id: str) -> bool:
    """True if the customer already holds an active or trialing subscription.

    The Elements lane's no-double-subscribe guard (409). Checked at BOTH /subscribe/init (fail
    early before creating a SetupIntent) and /subscribe/complete (a second tab could have subscribed
    between the two calls — the card-up-front window). `status='all'` then filter, mirroring
    _cancel_subscriptions, so this sees the same set the recompute reduces over.
    """
    stripe = _stripe()
    for s in stripe.Subscription.list(customer=customer_id, status="all", limit=20).data:
        status = s["status"] if isinstance(s, dict) else s.status
        if status in ("active", "trialing"):
            return True
    return False


def _live_subscription(customer_id: str) -> Any | None:
    """Return the customer's live (active|trialing) subscription OBJECT, or None.

    The upgrade lane needs the object itself (item id + current price), not just the boolean
    _has_live_subscription gives. Same `status='all'` then filter as the recompute/guards, so all
    three see the same set. Returns the first live sub — the app only ever creates one at a time.
    """
    stripe = _stripe()
    for s in stripe.Subscription.list(customer=customer_id, status="all", limit=20).data:
        status = s["status"] if isinstance(s, dict) else s.status
        if status in ("active", "trialing"):
            return s
    return None


def _sub_id(sub: Any) -> str | None:
    return sub["id"] if isinstance(sub, dict) else getattr(sub, "id", None)


def _first_item_id(sub: Any) -> str | None:
    """The id of the subscription's first item — the target of Subscription.modify's items[0].id."""
    items = _sub_items(sub)
    if not items:
        return None
    it = items[0]
    return it["id"] if isinstance(it, dict) else getattr(it, "id", None)


def _sub_interval(sub: Any) -> str | None:
    """Derive the billing interval ('monthly'|'annual') from the first item's price.

    Reads the price lookup_key suffix (pro_monthly -> 'monthly', insider_annual -> 'annual') so the
    upgrade keeps the user on their current cadence unless the request overrides it. Falls back to the
    price's raw `interval` field ('month'->'monthly', 'year'->'annual') if the lookup_key is missing or
    unrecognized. Returns None only when neither signal is present (caller then defaults to 'monthly').
    """
    items = _sub_items(sub)
    if not items:
        return None
    it = items[0]
    price = it["price"] if isinstance(it, dict) else getattr(it, "price", None)
    if price is None:
        return None
    lk = (price.get("lookup_key") if isinstance(price, dict) else getattr(price, "lookup_key", None)) or ""
    suffix = lk.rsplit("_", 1)[-1] if "_" in lk else ""
    if suffix in ("monthly", "annual"):
        return suffix
    raw = (price.get("interval") if isinstance(price, dict) else getattr(price, "interval", None)) or ""
    return {"month": "monthly", "year": "annual"}.get(raw)


# --------------------------------------------------------------------------- #
# Auth dependency (lazy import avoids the app.main <-> app.billing import cycle)
# --------------------------------------------------------------------------- #
def _current_user(authorization: str | None = Header(default=None)) -> dict:
    from app.main import require_user  # noqa: PLC0415
    return require_user(authorization)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
class CheckoutRequest(BaseModel):
    tier: str = Field(..., description="'insider' | 'pro'")
    interval: str = Field("annual", description="'monthly' | 'annual'")


@router.post("/api/billing/checkout")
def checkout(body: CheckoutRequest, user: dict = Depends(_current_user)) -> dict:
    """Create a Stripe Checkout Session and return its hosted URL."""
    tier, interval = body.tier.strip().lower(), body.interval.strip().lower()
    if tier not in {p["tier"] for p in _catalog()["products"].values()}:
        raise HTTPException(400, f"unknown tier '{tier}'")
    if interval not in ("monthly", "annual"):
        raise HTTPException(400, f"unknown interval '{interval}'")
    lookup_key = _tier_to_lookup_key(tier, interval)
    if not lookup_key:
        raise HTTPException(400, f"no price for {tier}/{interval}")

    stripe = _stripe()
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(401, "no user id")
    email = user.get("email")
    customer = _existing_customer(user_id)

    args: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": _price_id(lookup_key), "quantity": 1}],
        "client_reference_id": user_id,
        "success_url": f"{MM_SITE_BASE}/plans.html?checkout=success",
        "cancel_url": f"{MM_SITE_BASE}/plans.html?checkout=cancel",
        "subscription_data": {
            "trial_period_days": _tier_trial_days(tier),
            "metadata": {"mm_user_id": user_id},
        },
        "allow_promotion_codes": True,
    }
    if _AUTOMATIC_TAX:
        args["automatic_tax"] = {"enabled": True}
    if customer:
        args["customer"] = customer
        if _AUTOMATIC_TAX:
            args["customer_update"] = {"address": "auto"}
    elif email:
        args["customer_email"] = email

    try:
        session = stripe.checkout.Session.create(**args)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: checkout create failed (%s)", exc)
        raise HTTPException(502, f"checkout failed: {exc}") from None
    return {"url": session.url, "id": session.id}


@router.get("/api/billing/portal")
def portal(user: dict = Depends(_current_user)) -> dict:
    """Return a Stripe Customer Portal URL for self-serve upgrade/downgrade/cancel."""
    customer = _existing_customer(user.get("id", ""))
    if not customer:
        raise HTTPException(404, "no billing account yet")
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(customer=customer, return_url=f"{MM_SITE_BASE}/plans.html")
    return {"url": session.url}


# --------------------------------------------------------------------------- #
# Elements subscription lane (MNZ onboarding W2) — the in-sheet alternative to hosted Checkout.
#
# Card-up-front trial law (masterplan §2/§6): the subscription must NOT exist until the card is
# captured. Two round trips enforce it:
#   /subscribe/init     — find-or-create the customer, create a SetupIntent, hand its client_secret
#                         to the sheet's Stripe.js Elements. NO subscription yet.
#   /subscribe/complete — after Elements confirms the SetupIntent client-side, the sheet posts the
#                         setup_intent_id back; we verify it succeeded + belongs to THIS customer,
#                         THEN create the trialing subscription with the captured payment method.
# GET /api/billing/config exposes the publishable key (public by design) so the sheet can boot
# Stripe.js without shipping the key in a build.
# --------------------------------------------------------------------------- #
def _resolve_lookup_key(tier: str, interval: str) -> str:
    """Validate (tier, interval) exactly like checkout() and return the price lookup_key (or 400)."""
    if tier not in {p["tier"] for p in _catalog()["products"].values()}:
        raise HTTPException(400, f"unknown tier '{tier}'")
    if interval not in ("monthly", "annual"):
        raise HTTPException(400, f"unknown interval '{interval}'")
    lookup_key = _tier_to_lookup_key(tier, interval)
    if not lookup_key:
        raise HTTPException(400, f"no price for {tier}/{interval}")
    return lookup_key


@router.get("/api/billing/config")
def billing_config() -> dict:
    """Public Stripe publishable key for booting Elements in the browser.

    NO auth: publishable keys are public by design (they can only tokenize cards, never move money).
    503 cleanly when unset so the sheet can fall back to hosted Checkout instead of showing a broken
    card form.
    """
    pk = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()
    if not pk:
        raise HTTPException(503, "billing not configured (STRIPE_PUBLISHABLE_KEY unset)")
    return {"publishable_key": pk}


class SubscribeInitRequest(BaseModel):
    tier: str = Field(..., description="'insider' | 'pro'")
    interval: str = Field("annual", description="'monthly' | 'annual'")


@router.post("/api/billing/subscribe/init")
def subscribe_init(body: SubscribeInitRequest, user: dict = Depends(_current_user)) -> dict:
    """Find-or-create the Stripe customer and open a SetupIntent for in-sheet card capture.

    No subscription is created here — that is /subscribe/complete's job, after the card is captured
    (card-up-front trial law). Returns the SetupIntent client_secret for Stripe.js Elements + the
    customer id (opaque to the browser; /complete re-derives it server-side, never trusting it back).
    """
    tier, interval = body.tier.strip().lower(), body.interval.strip().lower()
    _resolve_lookup_key(tier, interval)  # validate before touching Stripe

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(401, "no user id")
    email = user.get("email")

    stripe = _stripe()
    customer_id = _existing_customer(user_id)
    if not customer_id:
        try:
            customer = stripe.Customer.create(email=email, metadata={"mm_user_id": user_id})
        except Exception as exc:  # noqa: BLE001
            log.warning("billing: customer create failed for %s (%s)", user_id, exc)
            raise HTTPException(502, f"subscribe init failed: {exc}") from None
        customer_id = customer.id
        # Persist the mapping immediately (mapping only — no tier/status), so the webhook can resolve
        # customer->user even if the browser abandons before /complete.
        try:
            _persist_customer(user_id, customer_id)
        except Exception as exc:  # noqa: BLE001 — mapping persist is best-effort; sub metadata still carries mm_user_id
            log.warning("billing: persist customer mapping failed for %s (%s)", user_id, exc)

    # No-double-subscribe guard (409) — fail before creating a SetupIntent for an already-paid user.
    try:
        already = _has_live_subscription(customer_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: subscribe init sub-check failed (%s)", exc)
        raise HTTPException(502, f"subscribe init failed: {exc}") from None
    if already:
        raise HTTPException(409, "already subscribed")

    try:
        si = stripe.SetupIntent.create(
            customer=customer_id,
            usage="off_session",
            # Card-family only, no redirect-based payment methods: redirect PMs would
            # (a) demand a return_url on confirm and (b) navigate away from the
            # floating onboarding sheet — the exact thing the Elements lane exists to
            # avoid. Found live in the sandbox E2E: without this, dashboard-enabled
            # redirect PMs make SetupIntent.confirm 400 ("must provide a return_url").
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            metadata={"mm_user_id": user_id, "mm_tier": tier, "mm_interval": interval},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: setup intent create failed for %s (%s)", user_id, exc)
        raise HTTPException(502, f"subscribe init failed: {exc}") from None
    return {"client_secret": si.client_secret, "customer_id": customer_id}


class SubscribeCompleteRequest(BaseModel):
    setup_intent_id: str = Field(..., description="the SetupIntent confirmed client-side by Elements")
    tier: str = Field(..., description="'insider' | 'pro'")
    interval: str = Field("annual", description="'monthly' | 'annual'")


@router.post("/api/billing/subscribe/complete")
def subscribe_complete(body: SubscribeCompleteRequest, user: dict = Depends(_current_user)) -> dict:
    """Create the trialing subscription once the SetupIntent has captured the card.

    Everything the client sends is re-verified server-side (never trust the client): the SetupIntent
    is retrieved fresh, must be 'succeeded', must belong to THIS user's customer, and must carry a
    payment method. Only then is the subscription created with the 7-day trial and the captured PM.
    """
    tier, interval = body.tier.strip().lower(), body.interval.strip().lower()
    lookup_key = _resolve_lookup_key(tier, interval)

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(401, "no user id")
    customer_id = _existing_customer(user_id)
    if not customer_id:
        raise HTTPException(400, "no billing customer for this user (call /subscribe/init first)")

    stripe = _stripe()
    try:
        si = stripe.SetupIntent.retrieve(body.setup_intent_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: setup intent retrieve failed (%s)", exc)
        raise HTTPException(502, f"subscribe complete failed: {exc}") from None

    si_status = si["status"] if isinstance(si, dict) else si.status
    si_customer = si["customer"] if isinstance(si, dict) else si.customer
    si_pm = si["payment_method"] if isinstance(si, dict) else si.payment_method
    if si_status != "succeeded":
        raise HTTPException(400, f"setup intent not succeeded (status={si_status})")
    if si_customer != customer_id:
        # Never trust the client: the SI must belong to THIS user's customer.
        raise HTTPException(400, "setup intent customer mismatch")
    if not si_pm:
        raise HTTPException(400, "setup intent has no payment method")

    # Re-check the no-double-subscribe guard — a second tab could have subscribed in the card-capture
    # window between /init and /complete.
    try:
        if _has_live_subscription(customer_id):
            raise HTTPException(409, "already subscribed")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: subscribe complete sub-check failed (%s)", exc)
        raise HTTPException(502, f"subscribe complete failed: {exc}") from None

    try:
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": _price_id(lookup_key)}],
            trial_period_days=_tier_trial_days(tier),
            default_payment_method=si_pm,
            payment_settings={"save_default_payment_method": "on_subscription"},
            trial_settings={"end_behavior": {"missing_payment_method": "cancel"}},
            metadata={"mm_user_id": user_id},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: subscription create failed for %s (%s)", user_id, exc)
        raise HTTPException(502, f"subscribe complete failed: {exc}") from None

    # Same-module authority (MNZ-R3): this IS the billing spine, so it may write the entitlement row
    # directly. Recompute + upsert + invalidate exactly like _handle_event, so /api/me reflects
    # `trialing` instantly instead of waiting on the webhook round trip. The webhook remains the
    # convergent source of truth — this write is naturally idempotent with it (both recompute from
    # the same live Stripe state).
    try:
        ent = _compute_entitlement(customer_id)
        _upsert_entitlement(user_id, customer_id, ent)
        _invalidate(user_id)
    except Exception as exc:  # noqa: BLE001 — the sub exists; the webhook will converge the row even if this fails
        log.warning("billing: post-subscribe entitlement sync failed for %s (%s)", user_id, exc)

    trial_end = sub["trial_end"] if isinstance(sub, dict) else sub.trial_end
    sub_id = sub["id"] if isinstance(sub, dict) else sub.id
    sub_status = sub["status"] if isinstance(sub, dict) else sub.status
    return {"status": sub_status, "subscription_id": sub_id, "trial_end": trial_end}


class UpgradeRequest(BaseModel):
    interval: str | None = Field(
        None, description="'monthly' | 'annual' — defaults to the current subscription's cadence")


@router.post("/api/billing/upgrade")
def upgrade(body: UpgradeRequest, user: dict = Depends(_current_user)) -> dict:
    """Upgrade the caller's live subscription to Pro, charging the prorated difference NOW.

    The only upgrade that exists is → tier 'pro' (Insider → Pro). We modify the existing
    subscription in place (never create a second one), swapping its price for the Pro price at the
    same cadence the user is already on — unless the body overrides `interval`.

    Proration law (the operator's ask — "pro-rated rate using their leftover time, by the difference
    in cost"): `proration_behavior='always_invoice'` credits the unused time on the old (Insider) price
    and charges the new (Pro) price pro-rata for the remainder of the current period, invoicing that
    net difference immediately. `payment_behavior='error_if_incomplete'` makes a card decline fail the
    call (→ 402) instead of leaving a half-switched subscription in an incomplete state.

    TRIALING subs are honest by construction: Stripe swaps the price but does NOT prorate during a
    trial (there is nothing to prorate — no money has changed hands), and trial_end is untouched. The
    user simply starts Pro billing when the trial ends. We surface that as trialing:true / prorated:false.

    Same-module authority (like /subscribe/complete + _handle_event): on success we recompute → upsert
    → invalidate so /api/me reflects Pro immediately; the webhook remains the convergent source of truth.
    """
    target_tier = "pro"
    interval_override = (body.interval or "").strip().lower() or None
    if interval_override and interval_override not in ("monthly", "annual"):
        raise HTTPException(400, f"unknown interval '{interval_override}'")

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(401, "no user id")

    customer_id = _existing_customer(user_id)
    if not customer_id:
        raise HTTPException(404, "no subscription")

    stripe = _stripe()
    try:
        sub = _live_subscription(customer_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: upgrade sub-lookup failed for %s (%s)", user_id, exc)
        raise HTTPException(502, f"upgrade failed: {exc}") from None
    if sub is None:
        raise HTTPException(404, "no subscription")

    if _sub_tier(sub) == target_tier:
        raise HTTPException(409, "already pro")

    sub_id = _sub_id(sub)
    item_id = _first_item_id(sub)
    if not sub_id or not item_id:
        raise HTTPException(502, "upgrade failed: subscription has no modifiable item")

    interval = interval_override or _sub_interval(sub) or "monthly"
    target_lookup_key = _tier_to_lookup_key(target_tier, interval)
    if not target_lookup_key:
        raise HTTPException(400, f"no price for {target_tier}/{interval}")

    is_trialing = (sub["status"] if isinstance(sub, dict) else sub.status) == "trialing"

    try:
        updated = stripe.Subscription.modify(
            sub_id,
            items=[{"id": item_id, "price": _price_id(target_lookup_key)}],
            proration_behavior="always_invoice",
            payment_behavior="error_if_incomplete",
            metadata={"mm_user_id": user_id},
            expand=["latest_invoice"],
        )
    except stripe.error.CardError as exc:
        # error_if_incomplete surfaces the decline synchronously — pass Stripe's message straight through.
        msg = getattr(exc, "user_message", None) or str(exc)
        log.info("billing: upgrade declined for %s (%s)", user_id, msg)
        raise HTTPException(402, msg) from None
    except Exception as exc:  # noqa: BLE001 — house pattern: any other Stripe failure -> 502
        log.warning("billing: upgrade modify failed for %s (%s)", user_id, exc)
        raise HTTPException(502, f"upgrade failed: {exc}") from None

    # Same-module authority: recompute -> upsert -> invalidate so /api/me flips to Pro instantly.
    try:
        ent = _compute_entitlement(customer_id)
        _upsert_entitlement(user_id, customer_id, ent)
        _invalidate(user_id)
    except Exception as exc:  # noqa: BLE001 — the sub is switched; the webhook converges the row even if this fails
        log.warning("billing: post-upgrade entitlement sync failed for %s (%s)", user_id, exc)

    # Trials don't prorate (no money moves during the trial); a real switch always invoices.
    prorated = not is_trialing
    inv = updated.get("latest_invoice") if isinstance(updated, dict) else getattr(updated, "latest_invoice", None)
    invoice_total_cents = None
    if isinstance(inv, dict):
        invoice_total_cents = inv.get("total")
    elif inv is not None and not isinstance(inv, str):
        invoice_total_cents = getattr(inv, "total", None)
    return {
        "status": "ok",
        "tier": target_tier,
        "prorated": prorated,
        "trialing": is_trialing,
        "invoice_total_cents": invoice_total_cents,
        "current_period_end": _iso(_sub_period_end(updated)),
    }


# events we act on; anything else is acknowledged (200) and ignored
_HANDLED = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "charge.refunded",
    "charge.dispute.created",
    "entitlements.active_entitlement_summary.updated",
}


def _customer_id_for_event(etype: str, obj: dict) -> str | None:
    """Extract the Stripe customer id from an event's data object."""
    cid = obj.get("customer")
    if cid:
        return cid
    if etype.startswith("charge.dispute"):
        charge_id = obj.get("charge")
        if charge_id:
            try:
                return _stripe().Charge.retrieve(charge_id).customer
            except Exception:  # noqa: BLE001
                return None
    return None


def _user_id_for_event(etype: str, obj: dict, customer_id: str | None) -> str | None:
    # 1) checkout carries the authoritative mapping
    if etype == "checkout.session.completed" and obj.get("client_reference_id"):
        return obj["client_reference_id"]
    # 2) we stamp mm_user_id onto the subscription at checkout
    meta = obj.get("metadata") or {}
    if meta.get("mm_user_id"):
        return meta["mm_user_id"]
    # 3) fall back to the persisted customer->user mapping
    if customer_id:
        return _user_for_customer(customer_id)
    return None


def _event_seen(event_id: str) -> bool:
    try:
        rows = _pg("GET", f"stripe_events?id=eq.{urllib.parse.quote(event_id)}&select=id")
        return bool(rows)
    except Exception:  # noqa: BLE001 — dedupe is an optimization; recompute is idempotent anyway
        return False


def _record_event(event_id: str, etype: str) -> None:
    try:
        _pg("POST", "stripe_events?on_conflict=id", body=[{"id": event_id, "type": etype}],
            prefer="resolution=ignore-duplicates,return=minimal")
    except Exception:  # noqa: BLE001
        pass


# Chargeback: a dispute leaves the subscription 'active' in Stripe, so a plain recompute would
# KEEP premium. We cancel the customer's live subs first, so the recompute-from-state sees no
# active sub and the downgrade to free STICKS (a later subscription.* event can't re-grant).
# (Refunds are intentionally NOT auto-revoking — they are often partial/goodwill; an operator who
# wants to revoke on refund cancels the sub, which arrives here as subscription.deleted.)
_REVOKING = {"charge.dispute.created"}


def _cancel_subscriptions(customer_id: str) -> None:
    """Best-effort cancel of a customer's live subscriptions. Never raises (a cancel failure must
    not wedge the webhook); the reconciler re-syncs later if a cancel didn't land."""
    try:
        stripe = _stripe()
        for s in stripe.Subscription.list(customer=customer_id, status="all", limit=20).data:
            if s.status in ("active", "trialing", "past_due"):
                try:
                    stripe.Subscription.cancel(s.id)
                    log.info("billing: canceled sub %s on chargeback (%s)", s.id, customer_id)
                except Exception as exc:  # noqa: BLE001
                    log.warning("billing: cancel sub %s failed (%s)", s.id, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: chargeback cancel sweep failed for %s (%s)", customer_id, exc)


def _handle_event(event: dict) -> None:
    etype = event["type"]
    if etype not in _HANDLED:
        return
    obj = event["data"]["object"]
    customer_id = _customer_id_for_event(etype, obj)
    user_id = _user_id_for_event(etype, obj, customer_id)
    if not user_id or not customer_id:
        log.warning("billing: unresolved ids for %s (customer=%s user=%s)", etype, customer_id, user_id)
        return
    if etype in _REVOKING:
        _cancel_subscriptions(customer_id)   # chargeback → cancel so the free downgrade sticks (C1)
    ent = _compute_entitlement(customer_id)
    _upsert_entitlement(user_id, customer_id, ent)
    _invalidate(user_id)
    log.info("billing: %s -> user %s tier=%s status=%s", etype, user_id, ent["tier"], ent["status"])


@router.post("/api/billing/webhook")
async def webhook(request: Request) -> dict:
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(503, "webhook not configured (STRIPE_WEBHOOK_SECRET unset)")
    stripe = _stripe()
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except ValueError:
        raise HTTPException(400, "invalid payload") from None
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "invalid signature") from None

    event = dict(event)
    event_id, etype = event["id"], event["type"]
    if _event_seen(event_id):
        return {"status": "duplicate", "id": event_id}
    _handle_event(event)   # raises -> 500 -> Stripe retries (no record written); recompute is idempotent
    _record_event(event_id, etype)
    return {"status": "ok", "id": event_id, "type": etype}


# --------------------------------------------------------------------------- #
# Reconciler — nightly cron + webhook-failure backstop (off the render path)
# --------------------------------------------------------------------------- #
def reconcile_entitlements() -> dict:
    """Re-sync every known customer's entitlement from live Stripe state."""
    rows = _pg("GET", "user_entitlements?select=user_id,stripe_customer_id&stripe_customer_id=not.is.null") or []
    n = 0
    for r in rows:
        cid, uid = r.get("stripe_customer_id"), r.get("user_id")
        if not cid or not uid:
            continue
        try:
            ent = _compute_entitlement(cid)
        except Exception as exc:  # noqa: BLE001
            # A deleted / invalid Stripe customer can no longer entitle anyone → downgrade to free
            # rather than leave a stale 'active' row lingering. Any other error: skip this row.
            if "No such customer" in str(exc) or "resource_missing" in str(exc):
                ent = {"tier": "free", "status": "canceled", "current_period_end": None, "features": []}
            else:
                log.warning("billing: reconcile failed for %s (%s)", uid, exc)
                continue
        _upsert_entitlement(uid, cid, ent)
        _invalidate(uid)
        n += 1
    log.info("billing: reconciled %d/%d rows", n, len(rows))
    return {"reconciled": n, "total": len(rows)}


def _main(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(description="Billing reconciler")
    ap.add_argument("--reconcile", action="store_true", help="re-sync all entitlements from Stripe")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.reconcile:
        print(json.dumps(reconcile_entitlements()))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
