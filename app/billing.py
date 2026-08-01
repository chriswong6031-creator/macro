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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from lib.tiers import normalize_tier

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


def _product_tiers() -> frozenset[str]:
    """Every entitlement tier the catalog actually SELLS — the enum for an inbound `tier`.

    Authored once because it was hardcoded once too often: /upgrade carried a literal
    ``("insider", "pro")`` that a fourth product would have silently locked out of the
    upgrade path while checkout happily sold it.
    """
    return frozenset(str(p["tier"]) for p in _catalog()["products"].values())


def _lookup_key_to_tier() -> dict[str, str]:
    """Current and grandfathered price lookup_key -> entitlement tier."""
    out: dict[str, str] = {}
    for prod in _catalog()["products"].values():
        for pspec in prod["prices"].values():
            out[pspec["lookup_key"]] = prod["tier"]
        for lookup_key in prod.get("legacy_lookup_keys", []):
            out[lookup_key] = prod["tier"]
    for offer in (_catalog().get("offers") or {}).values():
        if offer.get("base_lookup_key"):
            out[offer["base_lookup_key"]] = offer["tier"]
    return out


def _tier_to_lookup_key(tier: str, interval: str) -> str | None:
    for prod in _catalog()["products"].values():
        if prod["tier"] == tier:
            spec = prod["prices"].get(interval)
            return spec["lookup_key"] if spec else None
    return None


def _purchase_lookup_key(tier: str, interval: str, offer_key: str | None = None) -> str | None:
    """Resolve the price anchor for a purchase, preserving an offer's promised total forever."""
    if offer_key:
        spec = (_catalog().get("offers") or {}).get(offer_key) or {}
        if spec.get("tier") == tier and spec.get("interval") == interval:
            anchored = (spec.get("base_lookup_key") or "").strip()
            if anchored:
                return anchored
    return _tier_to_lookup_key(tier, interval)


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


# monthly bills sooner than annual, so annual outranks monthly on the interval axis.
_INTERVAL_RANK = {"monthly": 0, "annual": 1}


def _upgrade_allowed(cur_tier: str, cur_interval: str, tgt_tier: str, tgt_interval: str) -> bool:
    """Whether (cur_tier, cur_interval) -> (tgt_tier, tgt_interval) is a legal upgrade.

    The matrix law (operator order): a move is allowed iff it never steps DOWN on either axis and
    is not a no-op — the target tier ranks at or above the current tier (via _tier_rank, so the
    ordering stays config-driven), the target interval ranks at or above the current interval
    (monthly < annual), AND the pair actually changes. This is exactly the five reachable moves:
    insider·m -> {insider·a, pro·m, pro·a}, pro·m -> pro·a, insider·a -> pro·a. Everything else —
    any tier downgrade, any annual->monthly, and pro·annual (already at the top) — is refused.
    Unknown tiers/intervals rank -1 and can only ever satisfy the >= against themselves, which the
    no-op clause then rejects, so a garbage pair fails closed.

    Both tiers are normalized first. That is not belt-and-braces: an ALIAS ranks -1 like any
    unknown string, so an un-normalized `cur_tier` of 'essential' would out-rank nothing and
    make a real DOWNGRADE look legal — the one direction this matrix exists to refuse.
    """
    cur_tier, tgt_tier = normalize_tier(cur_tier), normalize_tier(tgt_tier)
    rank = _tier_rank()

    def tr(t: str) -> int:
        return rank.index(t) if t in rank else -1

    def ir(i: str) -> int:
        return _INTERVAL_RANK.get(i, -1)

    return (
        tr(tgt_tier) >= tr(cur_tier)
        and ir(tgt_interval) >= ir(cur_interval)
        and (tgt_tier, tgt_interval) != (cur_tier, cur_interval)
    )


def _upgrade_denial(cur_tier: str, cur_interval: str, tgt_tier: str, tgt_interval: str) -> str:
    """The honest 409 detail for an illegal move (caller has already checked _upgrade_allowed is False).

    Names WHY the move is refused, not a generic "already pro": a no-op (target == current) says
    exactly which plan the user is already on (so pro·annual, the top, reads "already on pro annual");
    a tier or interval step-down says downgrades aren't handled here and points at the portal.
    """
    if (tgt_tier, tgt_interval) == (cur_tier, cur_interval):
        return f"already on {cur_tier} {cur_interval}"
    return ("downgrades are not supported here — manage a downgrade or cancellation in the "
            f"customer portal (current plan: {cur_tier} {cur_interval})")


# --------------------------------------------------------------------------- #
# Stripe client (lazy — keeps the API process importable without the dep/key)
# --------------------------------------------------------------------------- #
# Wall-clock ceiling for any single Stripe call. The SDK's default is NO timeout, so one
# hung Stripe socket used to be able to park a webhook (and, before the threadpool hop
# below, the whole event loop) indefinitely. A webhook that takes too long is retried by
# Stripe and converges on the next delivery; one that never returns does not.
_STRIPE_TIMEOUT_SEC = int(os.environ.get("STRIPE_TIMEOUT_SEC") or 20)


def _stripe():
    try:
        import stripe  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(503, "billing unavailable: stripe SDK not installed") from exc
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        raise HTTPException(503, "billing not configured (STRIPE_SECRET_KEY unset)")
    stripe.api_key = key
    # Best-effort: the http-client factory has moved between SDK majors, and a billing
    # route must not 500 because a timeout could not be pinned.
    try:
        if getattr(stripe, "default_http_client", None) is None:
            stripe.default_http_client = stripe.http_client.new_default_http_client(
                timeout=_STRIPE_TIMEOUT_SEC)
    except Exception as exc:  # noqa: BLE001
        log.debug("billing: could not pin the Stripe HTTP timeout (%s)", type(exc).__name__)
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
        # Public error bodies must never carry runbook commands or Stripe provisioning
        # state — the operator signal lives in the server log only.
        log.error(
            "billing: price %r is missing in the current Stripe mode — "
            "run scripts/stripe_bootstrap.py (--allow-live against the live key)", lookup_key)
        raise HTTPException(503, "billing is temporarily unavailable, please try again shortly")
    pid = data[0].id
    with _PRICE_CACHE_LOCK:
        _PRICE_CACHE[lookup_key] = (pid, now + 300)
    return pid


def _field(obj: Any, key: str, default: Any = None) -> Any:
    """Read a StripeObject or a plain test dict without coupling callers to either."""
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


_PROMO_CACHE: dict[str, tuple[Any, float]] = {}  # offer key -> (PromotionCode, expire_ts)
_PROMO_CACHE_LOCK = threading.Lock()


def _offer_key(raw: str | None, tier: str, interval: str) -> str | None:
    """Validate an optional offer against its one allowed tier/cadence."""
    key = (raw or "").strip().lower() or None
    if key is None:
        return None
    spec = (_catalog().get("offers") or {}).get(key)
    if not spec:
        raise HTTPException(400, f"unknown offer '{key}'")
    if spec.get("tier") != tier or spec.get("interval") != interval:
        raise HTTPException(400, f"offer '{key}' is not valid for {tier}/{interval}")
    return key


def _promotion_code(offer_key: str) -> Any:
    """Resolve the Stripe PromotionCode that atomically owns an offer's real cap."""
    now = time.monotonic()
    with _PROMO_CACHE_LOCK:
        hit = _PROMO_CACHE.get(offer_key)
        if hit and hit[1] > now:
            return hit[0]
    spec = (_catalog().get("offers") or {}).get(offer_key)
    if not spec:
        raise HTTPException(400, f"unknown offer '{offer_key}'")
    stripe = _stripe()
    data = stripe.PromotionCode.list(code=spec["promotion_code"], limit=1).data
    if not data:
        # Public error bodies must never carry runbook commands or Stripe provisioning
        # state — the operator signal lives in the server log only.
        log.error(
            "billing: offer '%s' promotion code %r is missing in the current Stripe mode — "
            "run scripts/stripe_bootstrap.py (--allow-live against the live key)",
            offer_key, spec["promotion_code"])
        raise HTTPException(503, f"offer '{offer_key}' is temporarily unavailable")
    promo = data[0]
    with _PROMO_CACHE_LOCK:
        _PROMO_CACHE[offer_key] = (promo, now + 30)
    return promo


# --------------------------------------------------------------------------- #
# Scheduled allotment withdrawal (plans.yml `allotment_pacing`).
#
# The operator retires founding memberships from public sale on a daily schedule: the
# reserved pool starts at baseline_unavailable minus what was already redeemed, then
# grows by daily_step on each day that brought zero new redemptions (a day's real
# redemptions stand in for that day's step). The reserved pool is NOT cosmetic —
# `remaining`/`active` below subtract it, and every checkout path gates on those, so a
# withdrawn membership genuinely cannot be bought. The published availability is
# therefore a true statement; the payload still discloses `claimed` (real redemptions)
# and `reserved` (operator-withdrawn) separately.
#
# The ledger advances lazily on read — no cron. State loss self-heals: re-seeding
# assumes every elapsed day since baseline was quiet, which is deterministic and can
# only over-withdraw (never resurrect withdrawn inventory).
# --------------------------------------------------------------------------- #
_ALLOTMENT_LOCK = threading.Lock()


def _allotment_state_path() -> Path:
    return Path(os.environ.get("MACRO_API_STATE_DIR", "/var/lib/macro-api")) / "founding_allotment.json"


def _pacing_today(pacing: dict) -> date:
    return datetime.now(ZoneInfo(str(pacing.get("timezone", "America/New_York")))).date()


def _paced_reserved(offer_key: str, spec: dict, claimed: int, cap: int) -> int:
    """Advance and return the operator-reserved (withdrawn) share of the allotment."""
    pacing = spec.get("allotment_pacing") or {}
    if not pacing:
        return 0
    baseline_date = pacing["baseline_date"]
    if not isinstance(baseline_date, date):
        baseline_date = date.fromisoformat(str(baseline_date))
    step = int(pacing.get("daily_step", 2))
    today = _pacing_today(pacing)
    if today < baseline_date:
        return 0
    path = _allotment_state_path()
    with _ALLOTMENT_LOCK:
        doc: dict[str, Any] = {}
        state: dict[str, Any] = {}
        try:
            doc = json.loads(path.read_text())
            state = doc.get(offer_key) or {}
            reserved = int(state["reserved"])
            as_of = date.fromisoformat(state["as_of"])
            snapshot = int(state["claimed"])
        except Exception:  # noqa: BLE001 — missing/corrupt ledger re-seeds below
            doc = doc if isinstance(doc, dict) else {}
            state = {}
        if not state:
            reserved = max(0, int(pacing["baseline_unavailable"]) - claimed)
            reserved += step * (today - baseline_date).days
            as_of, snapshot = today, claimed
        elif today > as_of:
            gap_days = (today - as_of).days
            new_redemptions = max(0, claimed - snapshot)
            reserved += step * (gap_days - min(new_redemptions, gap_days))
            as_of, snapshot = today, claimed
        else:
            return max(0, min(reserved, cap - min(claimed, cap)))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            doc[offer_key] = {"reserved": reserved, "as_of": as_of.isoformat(), "claimed": snapshot}
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(doc))
            tmp.replace(path)
        except OSError as exc:
            log.warning("billing: founding allotment ledger write failed (%s)", exc)
        return max(0, min(reserved, cap - min(claimed, cap)))


def _offer_status(offer_key: str) -> dict[str, Any]:
    """Public inventory: Stripe redemptions + the operator's scheduled withdrawal.

    `claimed` is always the real Stripe redemption count. `reserved` is the share the
    operator has retired from public sale (see `_paced_reserved`). Both reduce
    `remaining`, and `active` follows `remaining`, so the published availability is
    enforced — never a cosmetic counter.
    """
    spec = (_catalog().get("offers") or {}).get(offer_key)
    if not spec:
        raise HTTPException(404, f"unknown offer '{offer_key}'")
    promo = _promotion_code(offer_key)
    cap = int(spec["max_redemptions"])
    claimed = max(0, int(_field(promo, "times_redeemed", 0) or 0))
    reserved = _paced_reserved(offer_key, spec, claimed, cap)
    unavailable = min(cap, claimed + reserved)
    active = bool(_field(promo, "active", False)) and unavailable < cap
    regular = next(
        int(prod["prices"][spec["interval"]]["unit_amount"])
        for prod in _catalog()["products"].values()
        if prod["tier"] == spec["tier"]
    )
    return {
        "key": offer_key,
        "name": spec["name"],
        "tier": spec["tier"],
        "interval": spec["interval"],
        "active": active,
        "claimed": min(claimed, cap),
        "reserved": reserved,
        "unavailable": unavailable,
        "remaining": max(0, cap - unavailable),
        "cap": cap,
        "public_count_threshold": int(spec.get("public_count_threshold", 0)),
        "unit_amount": int(spec["unit_amount"]),
        "regular_unit_amount": regular,
        "currency": _catalog().get("currency", "usd"),
        "renews_at_offer_rate": spec.get("duration") == "forever",
    }


def _offer_entitlement_key(offer_key: str) -> str | None:
    spec = (_catalog().get("offers") or {}).get(offer_key) or {}
    return (spec.get("entitlement_metadata_key") or "").strip() or None


def _grant_offer_entitlement(customer_id: str, offer_key: str | None) -> None:
    """Persist a grandfathered offer on the Stripe Customer without touching subscription state."""
    if not offer_key:
        return
    metadata_key = _offer_entitlement_key(offer_key)
    if metadata_key:
        _stripe().Customer.modify(customer_id, metadata={metadata_key: "true"})


def _customer_offer_entitled(customer_id: str | None, offer_key: str) -> bool:
    """Return durable founding eligibility, with subscription history as a recovery backstop.

    Customer metadata is the fast path. Historical subscription metadata is deliberately also
    authoritative: it survives cancellation and expiry and repairs the Customer marker if the
    post-checkout metadata write was interrupted.
    """
    if not customer_id:
        return False
    metadata_key = _offer_entitlement_key(offer_key)
    if not metadata_key:
        return False
    stripe = _stripe()
    customer = stripe.Customer.retrieve(customer_id)
    metadata = _field(customer, "metadata", {}) or {}
    if str(metadata.get(metadata_key, "")).lower() == "true":
        return True
    subscriptions = stripe.Subscription.list(customer=customer_id, status="all", limit=100).data
    for sub in subscriptions:
        sub_metadata = _field(sub, "metadata", {}) or {}
        if sub_metadata.get("mm_offer") == offer_key:
            try:
                _grant_offer_entitlement(customer_id, offer_key)
            except Exception as exc:  # noqa: BLE001 — history remains the durable recovery record
                log.warning("billing: failed to repair %s entitlement for %s (%s)",
                            offer_key, customer_id, exc)
            return True
    return False


def _effective_offer_key(
    raw: str | None,
    tier: str,
    interval: str,
    customer_id: str | None,
) -> str | None:
    """Validate an explicit offer or silently restore a matching grandfathered offer."""
    explicit = _offer_key(raw, tier, interval)
    if explicit:
        return explicit
    for offer_key, spec in (_catalog().get("offers") or {}).items():
        if spec.get("tier") != tier or spec.get("interval") != interval:
            continue
        if _customer_offer_entitled(customer_id, offer_key):
            return offer_key
    return None


def _offer_discount(
    offer_key: str | None,
    customer_id: str | None = None,
) -> list[dict[str, str]] | None:
    """Return a capped acquisition promo or the uncapped coupon for an existing founder."""
    if not offer_key:
        return None
    spec = (_catalog().get("offers") or {}).get(offer_key)
    if not spec:
        raise HTTPException(400, f"unknown offer '{offer_key}'")
    if _customer_offer_entitled(customer_id, offer_key):
        return [{"coupon": spec["coupon_id"]}]
    status = _offer_status(offer_key)
    if not status["active"]:
        raise HTTPException(410, f"{status['name']} is sold out")
    promo = _promotion_code(offer_key)
    promo_id = _field(promo, "id")
    if not promo_id:
        log.error("billing: offer '%s' promotion code carries no id in the Stripe payload", offer_key)
        raise HTTPException(503, f"offer '{offer_key}' is temporarily unavailable")
    return [{"promotion_code": promo_id}]


def _offer_sold_out_after_error(offer_key: str | None) -> bool:
    """Re-read Stripe after a create/modify race and map a newly exhausted cap to 410."""
    if not offer_key:
        return False
    with _PROMO_CACHE_LOCK:
        _PROMO_CACHE.pop(offer_key, None)
    try:
        return not _offer_status(offer_key)["active"]
    except Exception:  # noqa: BLE001 — preserve the caller's original Stripe failure
        return False


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


def _stored_customer(user_id: str) -> str | None:
    """The `cus_…` persisted on the user's row — a raw read, NOT proof it exists in Stripe."""
    try:
        rows = _pg("GET", f"user_entitlements?user_id=eq.{urllib.parse.quote(user_id)}&select=stripe_customer_id")
        if rows and rows[0].get("stripe_customer_id"):
            return rows[0]["stripe_customer_id"]
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: customer lookup failed for %s (%s)", user_id, exc)
    return None


def _forget_customer(user_id: str) -> None:
    """Null out a dead `stripe_customer_id` mapping, leaving tier/status/features alone.

    A PATCH, not the merge-duplicates upsert: `_upsert_entitlement` writes the column only when
    the value is truthy (so a comp can't drop a real mapping), which makes it structurally unable
    to clear one. Best-effort — a failure here just means the next call retries the heal.
    """
    try:
        _pg("PATCH", f"user_entitlements?user_id=eq.{urllib.parse.quote(user_id)}",
            body={"stripe_customer_id": None, "updated_at": datetime.now(timezone.utc).isoformat()},
            prefer="return=minimal")
        log.info("billing: cleared dead stripe_customer_id mapping for %s", user_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: could not clear customer mapping for %s (%s)", user_id, exc)


def _customer_gone(exc: Exception) -> bool:
    """True only for Stripe's "this customer does not exist here" error.

    Deliberately narrow. Any other failure (timeout, 5xx, rate limit, auth) must NOT be read as
    absence, or a transient Stripe outage would erase every mapping and mint duplicate customers
    against live cards.
    """
    msg = str(exc)
    return "No such customer" in msg or "resource_missing" in msg


def _existing_customer(user_id: str) -> str | None:
    """The user's Stripe customer, verified to exist in the CURRENT Stripe mode.

    Customer ids are mode-scoped: a `cus_…` minted in test mode is a 404 once STRIPE_SECRET_KEY
    is a live key. Returning one unchecked wedges every downstream lane permanently — checkout,
    portal, subscribe, and upgrade all hand it straight to Stripe and get `resource_missing` back,
    for that user, forever. So a stored id that Stripe no longer knows is dropped from the row and
    reported absent, which is exactly what the callers already handle: the two creating lanes
    (checkout, /subscribe/init) mint a fresh customer, the three acting lanes 404/400.

    Costs one `Customer.retrieve` on a handful of human-initiated billing routes — never a hot
    path — and only when a mapping actually exists.
    """
    customer_id = _stored_customer(user_id)
    if not customer_id:
        return None
    try:
        customer = _stripe().Customer.retrieve(customer_id)
    except HTTPException:
        raise  # billing not configured (503) — not a verdict on the customer
    except Exception as exc:  # noqa: BLE001
        if not _customer_gone(exc):
            log.warning("billing: customer verify inconclusive for %s (%s) — keeping mapping", user_id, exc)
            return customer_id  # fail SAFE: unproven absence is not absence
        log.warning("billing: stored customer %s is unknown to Stripe (user %s) — re-minting", customer_id, user_id)
        _forget_customer(user_id)
        return None
    # A customer deleted in the dashboard still retrieves, flagged rather than raising.
    if (customer.get("deleted") if isinstance(customer, dict) else getattr(customer, "deleted", False)):
        log.warning("billing: stored customer %s is deleted (user %s) — re-minting", customer_id, user_id)
        _forget_customer(user_id)
        return None
    return customer_id


def _user_for_customer(customer_id: str) -> str | None:
    try:
        rows = _pg("GET", f"user_entitlements?stripe_customer_id=eq.{urllib.parse.quote(customer_id)}&select=user_id")
        if rows:
            return rows[0].get("user_id")
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: user lookup failed for %s (%s)", customer_id, exc)
    return None


def read_entitlement(user_id: str) -> dict:
    """Full entitlement row for a user: {tier, features, status, current_period_end, source, interval}.

    Fail-safe to the free default (table/key absent, network error → free). Used by
    /api/me and /api/account for plan display + client-side Pro gating. `source`
    ('stripe'|'substack'|'comp') lets the client distinguish a comp/lifetime grant
    (source='comp' with a null current_period_end) from a canceled Stripe row.
    """
    default = {"tier": "free", "features": [], "status": "none", "current_period_end": None,
               "source": "stripe", "interval": None}
    if not user_id or not SUPABASE_SERVICE_ROLE_KEY:
        return default
    try:
        rows = _pg(
            "GET",
            f"user_entitlements?user_id=eq.{urllib.parse.quote(user_id)}"
            "&select=tier,features,status,current_period_end,source,plan_interval",
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("billing: read_entitlement failed for %s (%s)", user_id, exc)
        return default
    if rows:
        r = rows[0]
        # `interval` surfaces the billing cadence ('monthly'|'annual') for plan display; None for
        # free/comp rows with no cadence. Flows into /api/me (spreads this dict) and /api/account.
        return {
            "tier": r.get("tier") or "free",
            "features": r.get("features") or [],
            "status": r.get("status") or "none",
            "current_period_end": r.get("current_period_end"),
            "source": r.get("source") or "stripe",
            "interval": r.get("plan_interval"),
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
        # Tolerant: admin/entitlements.py comp callers pass dicts without a cadence -> None (null),
        # which is correct — a comp has no billing interval.
        "plan_interval": ent.get("plan_interval"),
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
# Entitlement-cache invalidation bridges (same process)
# --------------------------------------------------------------------------- #
def _invalidate(user_id: str) -> None:
    try:
        from engine.neuralweb.brain_gateway import invalidate_tier  # noqa: PLC0415
        invalidate_tier(user_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("billing: tier cache invalidate skipped (%s)", exc)
    try:
        # The static-site paywall caches the full feature verdict separately
        # from brain_gateway's tier-only cache. Every purchase, cancellation,
        # dunning transition, comp edit, and chargeback must evict both.
        from app.paywall import invalidate_entitlement  # noqa: PLC0415
        invalidate_entitlement(user_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("billing: paywall cache invalidate skipped (%s)", exc)


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

    subs items: {"status": str, "current_period_end": int|None, "tier": str|None, "interval": str|None}.
    Kept side-effect-free so it can be unit-tested without any network. `plan_interval` mirrors the
    chosen sub's cadence ('monthly'|'annual'); None whenever there is no entitling sub (free row).
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
        return {"tier": tier, "status": status, "current_period_end": _iso(cpe),
                "features": features, "plan_interval": best.get("interval")}

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
        return {"tier": "free", "status": status, "current_period_end": _iso(cpe),
                "features": [], "plan_interval": None}

    return {"tier": "free", "status": "none", "current_period_end": None,
            "features": [], "plan_interval": None}


def _compute_entitlement(customer_id: str) -> dict:
    """Fetch the customer's live Stripe state and reduce it to an entitlement row."""
    stripe = _stripe()
    raw_subs = stripe.Subscription.list(customer=customer_id, status="all", limit=20).data
    subs = [
        {"status": s.status, "current_period_end": _sub_period_end(s),
         "tier": _sub_tier(s), "interval": _sub_interval(s)}
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
    tier: str = Field(..., description="'insider' (alias: 'essential') | 'pro'")
    interval: str = Field("annual", description="'monthly' | 'annual'")
    offer: str | None = Field(None, description="optional catalog offer key")


@router.post("/api/billing/checkout")
def checkout(body: CheckoutRequest, user: dict = Depends(_current_user)) -> dict:
    """Create a Stripe Checkout Session and return its hosted URL."""
    tier, interval = normalize_tier(body.tier), body.interval.strip().lower()
    if tier not in _product_tiers():
        raise HTTPException(400, f"unknown tier '{tier}'")
    if interval not in ("monthly", "annual"):
        raise HTTPException(400, f"unknown interval '{interval}'")
    stripe = _stripe()
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(401, "no user id")
    email = user.get("email")
    customer = _existing_customer(user_id)
    offer_key = _effective_offer_key(body.offer, tier, interval, customer)
    lookup_key = _purchase_lookup_key(tier, interval, offer_key)
    if not lookup_key:
        raise HTTPException(400, f"no price for {tier}/{interval}")
    discounts = _offer_discount(offer_key, customer)

    args: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": _price_id(lookup_key), "quantity": 1}],
        "client_reference_id": user_id,
        "metadata": {
            "mm_user_id": user_id,
            **({"mm_offer": offer_key} if offer_key else {}),
        },
        # Land a PAYING customer on the desk, not back on the pricing page. The Elements
        # sheet lane already ends at start.html (its Done step -> loginDest()); hosted
        # Checkout used to return to /plans.html?checkout=success, where the banner told
        # the user to "head to the dashboard" without giving them a link and the plan
        # cards still read "Subscribe". site/hub-welcome.js consumes ?checkout=success on
        # the hub and confirms the tier it reads back from /api/me. A CANCEL still belongs
        # on the pricing page — that user is still choosing.
        "success_url": f"{MM_SITE_BASE}/start.html?checkout=success",
        "cancel_url": f"{MM_SITE_BASE}/plans.html?checkout=cancel",
        "subscription_data": {"metadata": {
            "mm_user_id": user_id, **({"mm_offer": offer_key} if offer_key else {})}},
    }
    # A no-trial tier (plans.yml trial_days: 0) OMITS the field: Stripe's minimum for
    # trial_period_days is 1, so sending a 0 is an API error, not "charge immediately".
    trial_days = _tier_trial_days(tier)
    if trial_days > 0:
        args["subscription_data"]["trial_period_days"] = trial_days
    if discounts:
        args["discounts"] = discounts
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
        if _offer_sold_out_after_error(offer_key):
            raise HTTPException(410, f"{_catalog()['offers'][offer_key]['name']} is sold out") from None
        raise HTTPException(502, "checkout failed, please try again") from None
    return {"url": session.url, "id": session.id}


@router.get("/api/billing/offers/{offer_key}")
def offer_status(offer_key: str) -> dict:
    """Truthful public inventory: Stripe redemptions + enforced scheduled withdrawal."""
    return _offer_status(offer_key.strip().lower())


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
    """Validate (tier, interval) exactly like checkout() and return the price lookup_key (or 400).

    ``tier`` is expected already normalized by the caller (every route does it on the way in,
    because the canonical value is what goes into Stripe metadata); the extra hop here costs
    nothing and keeps this helper correct if it is ever called with a raw value.
    """
    tier = normalize_tier(tier)
    if tier not in _product_tiers():
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
    tier: str = Field(..., description="'insider' (alias: 'essential') | 'pro'")
    interval: str = Field("annual", description="'monthly' | 'annual'")
    offer: str | None = Field(None, description="optional catalog offer key")


@router.post("/api/billing/subscribe/init")
def subscribe_init(body: SubscribeInitRequest, user: dict = Depends(_current_user)) -> dict:
    """Find-or-create the Stripe customer and open a SetupIntent for in-sheet card capture.

    No subscription is created here — that is /subscribe/complete's job, after the card is captured
    (card-up-front trial law). Returns the SetupIntent client_secret for Stripe.js Elements + the
    customer id (opaque to the browser; /complete re-derives it server-side, never trusting it back).
    """
    # Normalize BEFORE anything downstream: the SetupIntent below stamps `mm_tier` into
    # Stripe metadata, and /complete + the webhook read it back — an alias stored there
    # would leak a non-canonical tier into the entitlement row.
    tier, interval = normalize_tier(body.tier), body.interval.strip().lower()
    _resolve_lookup_key(tier, interval)  # validate before touching Stripe
    _offer_key(body.offer, tier, interval)  # validate before touching Stripe

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
            raise HTTPException(502, "subscribe init failed, please try again") from None
        customer_id = customer.id
        # Persist the mapping immediately (mapping only — no tier/status), so the webhook can resolve
        # customer->user even if the browser abandons before /complete.
        try:
            _persist_customer(user_id, customer_id)
        except Exception as exc:  # noqa: BLE001 — mapping persist is best-effort; sub metadata still carries mm_user_id
            log.warning("billing: persist customer mapping failed for %s (%s)", user_id, exc)

    offer_key = _effective_offer_key(body.offer, tier, interval, customer_id)
    if not _purchase_lookup_key(tier, interval, offer_key):
        raise HTTPException(400, f"no price for {tier}/{interval}")
    # Resolve before card capture so a sold-out offer never advances with a stale price.
    _offer_discount(offer_key, customer_id)

    # No-double-subscribe guard (409) — fail before creating a SetupIntent for an already-paid user.
    try:
        already = _has_live_subscription(customer_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: subscribe init sub-check failed (%s)", exc)
        raise HTTPException(502, "subscribe init failed, please try again") from None
    if already:
        raise HTTPException(409, "already subscribed")

    try:
        metadata = {"mm_user_id": user_id, "mm_tier": tier, "mm_interval": interval}
        if offer_key:
            metadata["mm_offer"] = offer_key
        si = stripe.SetupIntent.create(
            customer=customer_id,
            usage="off_session",
            # Card-family only, no redirect-based payment methods: redirect PMs would
            # (a) demand a return_url on confirm and (b) navigate away from the
            # floating onboarding sheet — the exact thing the Elements lane exists to
            # avoid. Found live in the sandbox E2E: without this, dashboard-enabled
            # redirect PMs make SetupIntent.confirm 400 ("must provide a return_url").
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: setup intent create failed for %s (%s)", user_id, exc)
        raise HTTPException(502, "subscribe init failed, please try again") from None
    return {"client_secret": si.client_secret, "customer_id": customer_id}


class SubscribeCompleteRequest(BaseModel):
    setup_intent_id: str = Field(..., description="the SetupIntent confirmed client-side by Elements")
    tier: str = Field(..., description="'insider' (alias: 'essential') | 'pro'")
    interval: str = Field("annual", description="'monthly' | 'annual'")
    offer: str | None = Field(None, description="optional catalog offer key")


@router.post("/api/billing/subscribe/complete")
def subscribe_complete(body: SubscribeCompleteRequest, user: dict = Depends(_current_user)) -> dict:
    """Create the trialing subscription once the SetupIntent has captured the card.

    Everything the client sends is re-verified server-side (never trust the client): the SetupIntent
    is retrieved fresh, must be 'succeeded', must belong to THIS user's customer, and must carry a
    payment method. Only then is the subscription created with the 7-day trial and the captured PM.
    """
    tier, interval = normalize_tier(body.tier), body.interval.strip().lower()
    _resolve_lookup_key(tier, interval)

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(401, "no user id")
    customer_id = _existing_customer(user_id)
    if not customer_id:
        raise HTTPException(400, "no billing customer for this user (call /subscribe/init first)")
    offer_key = _effective_offer_key(body.offer, tier, interval, customer_id)
    lookup_key = _purchase_lookup_key(tier, interval, offer_key)
    if not lookup_key:
        raise HTTPException(400, f"no price for {tier}/{interval}")

    stripe = _stripe()
    try:
        si = stripe.SetupIntent.retrieve(body.setup_intent_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: setup intent retrieve failed (%s)", exc)
        raise HTTPException(502, "subscribe complete failed, please try again") from None

    si_status = si["status"] if isinstance(si, dict) else si.status
    si_customer = si["customer"] if isinstance(si, dict) else si.customer
    si_pm = si["payment_method"] if isinstance(si, dict) else si.payment_method
    si_metadata = _field(si, "metadata", {}) or {}
    if si_status != "succeeded":
        raise HTTPException(400, f"setup intent not succeeded (status={si_status})")
    if si_customer != customer_id:
        # Never trust the client: the SI must belong to THIS user's customer.
        raise HTTPException(400, "setup intent customer mismatch")
    if not si_pm:
        raise HTTPException(400, "setup intent has no payment method")
    if (si_metadata.get("mm_offer") or None) != offer_key:
        raise HTTPException(400, "setup intent offer mismatch")

    # Re-check the no-double-subscribe guard — a second tab could have subscribed in the card-capture
    # window between /init and /complete.
    try:
        if _has_live_subscription(customer_id):
            raise HTTPException(409, "already subscribed")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: subscribe complete sub-check failed (%s)", exc)
        raise HTTPException(502, "subscribe complete failed, please try again") from None

    try:
        create_args: dict[str, Any] = {
            "customer": customer_id,
            "items": [{"price": _price_id(lookup_key)}],
            "default_payment_method": si_pm,
            "payment_settings": {"save_default_payment_method": "on_subscription"},
            "metadata": {"mm_user_id": user_id, **({"mm_offer": offer_key} if offer_key else {})},
        }
        # No-trial tier (plans.yml trial_days: 0) → charge on creation. Both trial keys
        # come off together: trial_settings only describes what happens AT trial end, so
        # sending it beside an absent trial is meaningless, and a literal 0 is rejected.
        trial_days = _tier_trial_days(tier)
        if trial_days > 0:
            create_args["trial_period_days"] = trial_days
            create_args["trial_settings"] = {"end_behavior": {"missing_payment_method": "cancel"}}
        discounts = _offer_discount(offer_key, customer_id)
        if discounts:
            create_args["discounts"] = discounts
        sub = stripe.Subscription.create(
            **create_args
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("billing: subscription create failed for %s (%s)", user_id, exc)
        if _offer_sold_out_after_error(offer_key):
            raise HTTPException(410, f"{_catalog()['offers'][offer_key]['name']} is sold out") from None
        raise HTTPException(502, "subscribe complete failed, please try again") from None

    if offer_key:
        try:
            _grant_offer_entitlement(customer_id, offer_key)
        except Exception as exc:  # noqa: BLE001 — subscription metadata lets the webhook/re-entry repair this
            log.warning("billing: post-subscribe %s entitlement grant failed for %s (%s)",
                        offer_key, user_id, exc)

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
    tier: str | None = Field(
        None,
        description="'insider' (alias: 'essential') | 'pro' — target tier; defaults to 'pro' "
                    "(settings-dashboard back-compat)")
    interval: str | None = Field(
        None, description="'monthly' | 'annual' — defaults to the current subscription's cadence")
    offer: str | None = Field(None, description="optional catalog offer key")


@router.post("/api/billing/upgrade")
def upgrade(body: UpgradeRequest, user: dict = Depends(_current_user)) -> dict:
    """Upgrade the caller's live subscription along the tier×interval matrix, charging the prorated
    difference NOW. We modify the existing subscription in place (never create a second one), swapping
    its price for the target price.

    Matrix law (operator order — never a downgrade, never a no-op):

        current \\ target   insider·m  insider·a  pro·m  pro·a
        insider·monthly        —         yes      yes    yes
        insider·annual         no        —        no     yes
        pro·monthly            no        no       —      yes
        pro·annual             no        no       no     —

    i.e. the target tier may not rank below the current tier, the target interval may not step from
    annual back to monthly, and the pair must actually change. `tier` defaults to 'pro' (the
    settings-dashboard caller sends only `interval`); `interval` defaults to the current cadence.
    Both are validated to their enums (400); an out-of-matrix move is refused with a specific 409.

    Proration law (the operator's ask — "pro-rated rate using their leftover time, by the difference
    in cost"): `proration_behavior='always_invoice'` credits the unused time on the old price and
    charges the new price pro-rata for the remainder of the current period, invoicing that net
    difference immediately. `payment_behavior='error_if_incomplete'` makes a card decline fail the
    call (→ 402) instead of leaving a half-switched subscription in an incomplete state.

    TRIALING subs are honest by construction: Stripe swaps the price but does NOT prorate during a
    trial (there is nothing to prorate — no money has changed hands), and trial_end is untouched. The
    user simply starts the new-plan billing when the trial ends. We surface that as trialing:true /
    prorated:false.

    Same-module authority (like /subscribe/complete + _handle_event): on success we recompute → upsert
    → invalidate so /api/me reflects the new plan immediately; the webhook remains the convergent
    source of truth. The response carries the TARGET tier + interval.
    """
    # Catalog-driven, alias-aware. This was a literal ("insider", "pro"): checkout sold from
    # the catalog while THIS gate did not, so a fourth product — or the display rename's
    # 'essential' alias — would 400 here after selling fine everywhere else.
    target_tier = normalize_tier(body.tier or "pro")
    if target_tier not in _product_tiers():
        raise HTTPException(400, f"unknown tier '{target_tier}'")
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
        raise HTTPException(502, "upgrade failed, please try again") from None
    if sub is None:
        raise HTTPException(404, "no subscription")

    # Current = (tier, cadence); target defaults each axis to the current one. Matrix-gate BEFORE
    # touching Stripe so an illegal move never modifies the subscription.
    cur_tier = _sub_tier(sub) or "free"
    cur_interval = _sub_interval(sub) or "monthly"
    interval = interval_override or cur_interval
    if not _upgrade_allowed(cur_tier, cur_interval, target_tier, interval):
        raise HTTPException(409, _upgrade_denial(cur_tier, cur_interval, target_tier, interval))
    offer_key = _effective_offer_key(body.offer, target_tier, interval, customer_id)
    discounts = _offer_discount(offer_key, customer_id)

    sub_id = _sub_id(sub)
    item_id = _first_item_id(sub)
    if not sub_id or not item_id:
        raise HTTPException(502, "upgrade failed: subscription has no modifiable item")

    target_lookup_key = _purchase_lookup_key(target_tier, interval, offer_key)
    if not target_lookup_key:
        raise HTTPException(400, f"no price for {target_tier}/{interval}")

    is_trialing = (sub["status"] if isinstance(sub, dict) else sub.status) == "trialing"

    try:
        modify_args: dict[str, Any] = {
            "items": [{"id": item_id, "price": _price_id(target_lookup_key)}],
            "proration_behavior": "always_invoice",
            "payment_behavior": "error_if_incomplete",
            "metadata": {"mm_user_id": user_id, **({"mm_offer": offer_key} if offer_key else {})},
            "expand": ["latest_invoice"],
        }
        if discounts:
            modify_args["discounts"] = discounts
        updated = stripe.Subscription.modify(sub_id, **modify_args)
    except stripe.error.CardError as exc:
        # error_if_incomplete surfaces the decline synchronously — pass Stripe's message straight through.
        msg = getattr(exc, "user_message", None) or str(exc)
        log.info("billing: upgrade declined for %s (%s)", user_id, msg)
        raise HTTPException(402, msg) from None
    except Exception as exc:  # noqa: BLE001 — house pattern: any other Stripe failure -> 502
        log.warning("billing: upgrade modify failed for %s (%s)", user_id, exc)
        if _offer_sold_out_after_error(offer_key):
            raise HTTPException(410, f"{_catalog()['offers'][offer_key]['name']} is sold out") from None
        raise HTTPException(502, "upgrade failed, please try again") from None

    if offer_key:
        try:
            _grant_offer_entitlement(customer_id, offer_key)
        except Exception as exc:  # noqa: BLE001 — subscription metadata lets the webhook/re-entry repair this
            log.warning("billing: post-upgrade %s entitlement grant failed for %s (%s)",
                        offer_key, user_id, exc)

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
        "interval": interval,
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


def _billing_emails():
    """The SEE-W3 email module, or None when it is unavailable.

    Lazy + tolerant on purpose: mail is a side effect of the entitlement write, so an
    import error (module absent in a slimmer deployment, a syntax slip in a hotfix) must
    degrade to "no email", never to a webhook 500 that makes Stripe retry forever.
    """
    try:
        from app import billing_emails  # noqa: PLC0415
        return billing_emails
    except Exception as exc:  # noqa: BLE001
        log.debug("billing: email module unavailable (%s)", type(exc).__name__)
        return None


# Per-user serialisation of the read-compare-write-mail sequence below.
#
# The email hook compares the entitlement BEFORE the upsert against the one after, so two
# events for the same user must not interleave: both would read the same "before" and
# both could decide an upgrade happened, mailing twice. That was structurally impossible
# while the webhook ran inline on a single event loop; it stopped being impossible the
# moment the handler moved to a threadpool (and would stop again under `--workers`, which
# no lock in this process can cover — that needs an advisory lock in Postgres). Locks are
# created on demand and kept: one small mutex per paying customer is not a leak worth
# managing, and a lock we might still be holding must never be evicted.
_USER_LOCKS: dict[str, threading.Lock] = {}
_USER_LOCKS_GUARD = threading.Lock()


def _user_lock(user_id: str) -> threading.Lock:
    with _USER_LOCKS_GUARD:
        lock = _USER_LOCKS.get(user_id)
        if lock is None:
            lock = _USER_LOCKS[user_id] = threading.Lock()
        return lock


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
    if etype in {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
    }:
        event_offer = (obj.get("metadata") or {}).get("mm_offer")
        if event_offer in (_catalog().get("offers") or {}):
            _grant_offer_entitlement(customer_id, event_offer)
    if etype in _REVOKING:
        _cancel_subscriptions(customer_id)   # chargeback → cancel so the free downgrade sticks (C1)
    emails = _billing_emails()
    outbox = None
    with _user_lock(user_id):
        # THE DECISION, serialised per user. An upgrade is a comparison against the
        # pre-upsert row and a failed payment has already lost its tier by the time the
        # recompute lands, so those two events need the row as it stands NOW; the
        # snapshot, the recompute, the upsert and the decision therefore sit in ONE
        # critical section, and the comparison can never straddle another event's write.
        # The module decides which events pay for that extra read; every other event
        # costs nothing.
        pre_ent = None
        if emails is not None:
            try:
                pre_ent = emails.pre_upsert_snapshot(etype, user_id)
            except Exception as exc:  # noqa: BLE001
                log.debug("billing: pre-email snapshot skipped (%s)", type(exc).__name__)
        ent = _compute_entitlement(customer_id)
        _upsert_entitlement(user_id, customer_id, ent)
        _invalidate(user_id)
        log.info("billing: %s -> user %s tier=%s status=%s", etype, user_id, ent["tier"], ent["status"])
        # AFTER the entitlement write, never before: the DB row is the source of truth and
        # mail is a side effect. prepare() never raises; the guard here covers the import
        # boundary itself, so a broken composer cannot 5xx the webhook (SEE G2/G7).
        if emails is not None:
            try:
                outbox = emails.prepare(event, user_id=user_id, customer_id=customer_id,
                                        ent=ent, pre=pre_ent)
            except Exception as exc:  # noqa: BLE001
                log.warning("billing: %s email prepare failed (%s)", etype, type(exc).__name__)

    # THE SEND, outside the lock. Resolving the address, rendering and the SMTP
    # conversation (up to ~21.5s with its one retry) need no serialisation: mailer.send is
    # ledger-first on a UNIQUE idem_key, so racing deliveries of the same decision produce
    # one send and one 'duplicate'. Holding the lock across it would make the second of
    # two events that arrive together — invoice.payment_failed and
    # customer.subscription.updated on a failed renewal, routinely — wait out the first's
    # entire send while pinning an anyio threadpool token.
    if outbox is not None and emails is not None:
        try:
            emails.deliver(outbox)
        except Exception as exc:  # noqa: BLE001
            log.warning("billing: %s email deliver failed (%s)", etype, type(exc).__name__)


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
    # OFF the event loop. _handle_event is entirely blocking — several urllib round trips
    # to Supabase, up to a few Stripe calls, and (since SEE W3) an SMTP conversation with
    # one retry. Left inline in this `async def`, a slow Stripe or relay stalls EVERY
    # other request on this single-process API, not just the webhook. run_in_threadpool
    # is the house-standard hop for a blocking call inside an async route.
    # raises -> 500 -> Stripe retries (no record written); the recompute is idempotent.
    await run_in_threadpool(_handle_event, event)
    _record_event(event_id, etype)
    return {"status": "ok", "id": event_id, "type": etype}


# --------------------------------------------------------------------------- #
# Reconciler — nightly cron + webhook-failure backstop (off the render path)
# --------------------------------------------------------------------------- #
def reconcile_entitlements() -> dict:
    """Re-sync every known customer's entitlement from live Stripe state.

    Comp rows are only partially in scope, and the boundary is the honesty contract stated in
    admin/entitlements.py: a comp over a LIVE Stripe subscription is transient (this reconciler
    wins, which is why force-comp cancels the subscription first), but a comp over a customer with
    no live sub is DURABLE. The row-level select can't express that, so the check happens per row
    after the recompute: Stripe overrides a comp only when it actually has an entitling
    subscription to override it with. Silence from Stripe — no subs, or no such customer — is not
    authority to revoke what an operator granted.

    Without that guard the nightly cron quietly deletes operator grants: `_compute_entitlement`
    returns no `source`, so `_upsert_entitlement` defaults it to 'stripe' and a lifetime comp
    becomes tier=free/source=stripe the first night after the user's row picks up a customer id.
    Switching STRIPE_SECRET_KEY from test to live makes it certain rather than incidental, because
    every test-mode `cus_…` becomes a `resource_missing` the moment the live key is in place.
    """
    rows = _pg("GET",
               "user_entitlements?select=user_id,stripe_customer_id,source&stripe_customer_id=not.is.null") or []
    n = 0
    preserved = 0
    for r in rows:
        cid, uid = r.get("stripe_customer_id"), r.get("user_id")
        is_comp = (r.get("source") or "") == "comp"
        if not cid or not uid:
            continue
        mapping = cid
        try:
            ent = _compute_entitlement(cid)
        except Exception as exc:  # noqa: BLE001
            if not _customer_gone(exc):
                log.warning("billing: reconcile failed for %s (%s)", uid, exc)
                continue
            # The customer is gone from this Stripe mode. Clear the dead mapping either way so the
            # billing lanes can mint a fresh customer instead of 502ing on a ghost id — and pass
            # None below, or the upsert would immediately write the ghost id back.
            _forget_customer(uid)
            mapping = None
            if is_comp:
                log.info("billing: kept comp for %s (stripe customer %s absent)", uid, cid)
                preserved += 1
                continue
            # A deleted / invalid Stripe customer can no longer entitle anyone → downgrade to free
            # rather than leave a stale 'active' row lingering.
            ent = {"tier": "free", "status": "canceled", "current_period_end": None, "features": []}
        if is_comp and ent.get("status") not in ("active", "trialing"):
            log.info("billing: kept comp for %s (no entitling stripe subscription)", uid)
            preserved += 1
            continue
        _upsert_entitlement(uid, mapping, ent)
        _invalidate(uid)
        n += 1
    log.info("billing: reconciled %d/%d rows (%d comps preserved)", n, len(rows), preserved)
    return {"reconciled": n, "total": len(rows), "comps_preserved": preserved}


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
