"""Fail-closed premium site wall for static HTML and generated artifacts.

Caddy calls ``GET /api/paywall/check`` only after the registration wall has
allowed a protected path.  The two controls remain deliberately independent:

* registration protects the site now, including JSON/data artifacts;
* ``PAYWALL_ENABLED=1`` additionally requires the ``site_full`` entitlement.

Public/free/premium classification comes from ``config/site_access.yml``.
Unknown paths are premium by default.  Config/auth/store errors deny.  A recent
positive entitlement may survive an entitlement-store outage for at most
``PAYWALL_GRACE_SECONDS`` (24h default); auth failures never receive grace.

``premium.enforced_early`` is the per-path escape from the global switch: those
paths require the entitlement even while ``PAYWALL_ENABLED=0``, so a single paid
surface can ship ahead of the site-wide launch.  They are payload paths whose
page keeps a free-visible preview shell (docs/TIER_PREVIEW_PATTERN.md).

``GET /api/paywall/check_pro`` is a SECOND, independent subrequest for a
Pro-only HOST (bot.mastermind-x.com).  It shares this module's auth and
entitlement machinery and nothing else: no path classification, no
``PAYWALL_ENABLED`` staging.  Its one non-entitlement admission is the operator
email allowlist that ``/api/me`` already honours (BRAIN_UNLIMITED_ALLOWLIST), so
the two agree about who a person is.  See the section at the bottom of this file.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from lib.tiers import normalize_tier

log = logging.getLogger("macro.paywall")
router = APIRouter()

REPO = Path(os.environ.get("MACRO_REPO") or Path(__file__).resolve().parents[1])
ACCESS_CONFIG = Path(os.environ.get("SITE_ACCESS_CONFIG") or REPO / "config" / "site_access.yml")
INTERSTITIAL = Path(__file__).with_name("paywall_interstitial.html")
_ACTIVE = frozenset({"active", "trialing"})

_CONFIG_CACHE: tuple[dict[str, Any], int] | None = None
_CONFIG_LOCK = threading.Lock()
#: sha256(token) -> (uid, email, expiry, record). Email and the Supabase user
#: record ride along because ``/auth/v1/user`` already returns them on the same
#: call; see ``_fresh_identity`` / ``_resolve_identity`` for why this is not a
#: second cache. ``require_user`` reuses this entry — it does not mint its own.
_AUTH_CACHE: dict[str, tuple[str | None, str, float, dict[str, Any] | None]] = {}
_AUTH_LOCK = threading.Lock()
#: Caps concurrent GET /auth/v1/user calls. Excess callers shed (busy) instead
#: of pinning FastAPI's ~40-thread pool — that is what kept /api/health up
#: during a vendor stall (MMX-004 / GATE-3).
_AUTH_UPSTREAM_LIMIT = 8
_AUTH_UPSTREAM_SEM = threading.BoundedSemaphore(_AUTH_UPSTREAM_LIMIT)
_TOKEN_REJECT_HTTP = frozenset({400, 401, 403})


@dataclass(frozen=True)
class _EntitlementVerdict:
    allowed: bool
    tier: str
    status: str
    fetched_at: float
    grace_until: float


_ENT_CACHE: dict[str, _EntitlementVerdict] = {}
_ENT_LOCK = threading.Lock()


def _enabled() -> bool:
    return os.environ.get("PAYWALL_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def _seconds(name: str, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


def _load_config() -> dict[str, Any]:
    """mtime-cached policy load. Any malformed/missing policy fails closed."""
    global _CONFIG_CACHE
    stat = ACCESS_CONFIG.stat()
    stamp = stat.st_mtime_ns
    with _CONFIG_LOCK:
        if _CONFIG_CACHE and _CONFIG_CACHE[1] == stamp:
            return _CONFIG_CACHE[0]
        raw = yaml.safe_load(ACCESS_CONFIG.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema") != "site_access.v1":
            raise ValueError("invalid site access policy schema")
        for section in ("public", "free_registered", "deny"):
            spec = raw.get(section)
            if not isinstance(spec, dict):
                raise ValueError(f"missing site access section: {section}")
            for field in ("exact", "prefixes"):
                if not isinstance(spec.get(field), list):
                    raise ValueError(f"{section}.{field} must be a list")
        premium = raw.get("premium")
        if not isinstance(premium, dict) or not premium.get("required_feature"):
            raise ValueError("premium.required_feature is required")
        early = premium.get("enforced_early")
        if early is not None:
            # Absent is allowed (nothing enforced ahead of launch); present-but-
            # malformed denies, like every other policy defect in this module.
            if not isinstance(early, dict):
                raise ValueError("premium.enforced_early must be a mapping")
            for field in ("exact", "prefixes"):
                if not isinstance(early.get(field), list):
                    raise ValueError(f"premium.enforced_early.{field} must be a list")
        _CONFIG_CACHE = (raw, stamp)
        return raw


def _normalized_path(raw: str | None) -> str:
    """Canonical same-origin path; malformed encodings remain premium/denied."""
    if not raw:
        return "/"
    try:
        path = urllib.parse.unquote(urllib.parse.urlsplit(raw).path)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid original URI") from exc
    if not path.startswith("/") or path.startswith("//") or "\x00" in path or "\\" in path:
        raise ValueError("unsafe original URI")
    parts = path.split("/")
    if any(part in {".", ".."} for part in parts):
        raise ValueError("non-canonical original URI")
    return path


def _matches(path: str, spec: dict[str, Any]) -> bool:
    return path in set(spec.get("exact") or []) or any(
        path.startswith(str(prefix)) for prefix in spec.get("prefixes") or []
    )


def classify_path(path: str) -> str:
    """Return public|free|premium|deny. Unknown is always premium."""
    cfg = _load_config()
    if _matches(path, cfg["deny"]):
        return "deny"
    if _matches(path, cfg["public"]):
        return "public"
    if _matches(path, cfg["free_registered"]):
        return "free"
    return "premium"


def enforced_early(path: str) -> bool:
    """True when this premium path is gated regardless of PAYWALL_ENABLED."""
    early = (_load_config()["premium"].get("enforced_early")) or {}
    return _matches(path, early)


def _is_document(request: Request, path: str) -> bool:
    if (request.headers.get("sec-fetch-dest") or "").strip().lower() == "document":
        return True
    kind = (request.headers.get("x-original-kind") or "").strip().lower()
    if kind:
        return kind == "document"
    return path == "/" or path.lower().endswith(".html")


@dataclass(frozen=True)
class _Identity:
    """One verification of one token. ``status`` is ok|invalid|outage|busy."""

    uid: str | None
    email: str
    record: dict[str, Any] | None
    status: str


def _auth_cache_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _copy_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(record) if isinstance(record, dict) else None


def _cache_get(key: str) -> _Identity | None:
    now = time.monotonic()
    with _AUTH_LOCK:
        hit = _AUTH_CACHE.get(key)
        if not hit or hit[2] <= now:
            return None
        uid, email, _expiry, record = hit[0], hit[1], hit[2], hit[3] if len(hit) > 3 else None
    if uid:
        return _Identity(uid, email, _copy_record(record), "ok")
    return _Identity(None, "", None, "invalid")


def _positive_token_ttl(token: str, configured_ttl: float) -> float:
    """Clamp a reusable positive identity to the JWT's own wall-clock expiry."""
    try:
        payload_part = token.split(".")[1]
        payload_part += "=" * (-len(payload_part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_part.encode("ascii")))
        expires_at = float(payload["exp"])
        if not math.isfinite(expires_at):
            return 0.0
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeError):
        return 0.0
    return max(0.0, min(configured_ttl, expires_at - time.time()))


def _cache_put(
    key: str,
    token: str,
    uid: str | None,
    email: str,
    record: dict[str, Any] | None,
) -> None:
    ttl = _seconds("PAYWALL_AUTH_CACHE_SECONDS", 45.0, 1.0, 60.0)
    if uid:
        ttl = _positive_token_ttl(token, ttl)
        if ttl <= 0.0:
            return
    now = time.monotonic()
    with _AUTH_LOCK:
        if len(_AUTH_CACHE) > 5000:
            _AUTH_CACHE.clear()
        _AUTH_CACHE[key] = (uid, email, now + ttl, _copy_record(record))


def _fetch_supabase_user(token: str) -> _Identity:
    """One bounded GET /auth/v1/user. Never writes the cache — caller decides."""
    from app.main import SUPABASE_ANON_KEY, SUPABASE_URL  # noqa: PLC0415

    if not _AUTH_UPSTREAM_SEM.acquire(blocking=False):
        return _Identity(None, "", None, "busy")
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # Supabase ANSWERED. 400/401/403 is a verdict on this token; 5xx/429 is
        # the service failing and must not be remembered as "invalid".
        if exc.code in _TOKEN_REJECT_HTTP:
            return _Identity(None, "", None, "invalid")
        return _Identity(None, "", None, "outage")
    except Exception:  # noqa: BLE001 — timeout/DNS/TLS/reset/bad body: no verdict
        return _Identity(None, "", None, "outage")
    finally:
        _AUTH_UPSTREAM_SEM.release()

    if not isinstance(data, dict):
        return _Identity(None, "", None, "invalid")
    uid: str | None = None
    candidate = data.get("id")
    if isinstance(candidate, str):
        try:
            uuid.UUID(candidate)
            uid = candidate
        except (ValueError, TypeError):
            uid = None
    email = ""
    addr = data.get("email")
    if uid and isinstance(addr, str):
        email = addr.strip().lower()
    if not uid:
        return _Identity(None, "", None, "invalid")
    return _Identity(uid, email, dict(data), "ok")


def _resolve_identity(token: str) -> _Identity:
    """Shared identity lookup for the paywall and ``require_user``.

    ONE cache (``_AUTH_CACHE``), keyed on ``sha256(token)``, TTL clamped 1–60s.
    A cached valid record is served through a vendor blip for that TTL only.
    Invalid/expired tokens are cached as rejected. Transport failures and a
    full semaphore are not token verdicts and are not remembered.
    """
    key = _auth_cache_key(token)
    hit = _cache_get(key)
    if hit is not None:
        return hit
    ident = _fetch_supabase_user(token)
    if ident.status in {"ok", "invalid"}:
        _cache_put(key, token, ident.uid, ident.email, ident.record)
    return ident


def _fresh_identity(token: str) -> tuple[str | None, str]:
    """Verify token against Supabase with a ≤60s hashed-token cache; return (uid, email).

    ONE upstream call serves both fields: ``/auth/v1/user`` has always returned the
    email and this function simply dropped it. No new request is made.

    The two are cached TOGETHER deliberately. A second, separately-expiring email cache
    could hand a caller an email resolved from a DIFFERENT verification of the same
    token than the uid it is paired with -- and the Pro host gate uses the pair to
    decide access. One entry, one expiry, no way for the halves to disagree.

    Email is ``''`` whenever it is absent, non-string, or the uid did not verify; the
    uid contract is unchanged (``None`` on any invalid/expired/upstream failure).
    ``require_user`` reads the same cache entry — it does not keep a second map.
    """
    ident = _resolve_identity(token)
    return ident.uid, ident.email


def _fresh_uid(token: str) -> str | None:
    """Verify token against Supabase with a ≤60s hashed-token cache."""
    return _fresh_identity(token)[0]


def _store_entitlement(user_id: str) -> tuple[dict[str, Any] | None, bool]:
    """Return (row, store_reachable). Empty row is reachable and unentitled."""
    from app import billing  # noqa: PLC0415

    quoted = urllib.parse.quote(user_id)
    try:
        rows = billing._pg(  # noqa: SLF001 — same-process authority read, no Stripe call
            "GET",
            f"user_entitlements?user_id=eq.{quoted}&select=tier,features,status",
            timeout=4,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("paywall: entitlement store unavailable (%s)", exc)
        return None, False
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0], True
    return None, True


def _entitled(user_id: str, required_feature: str) -> tuple[bool, str]:
    """Resolve entitlement with short cache and positive-only outage grace."""
    now = time.monotonic()
    fresh_ttl = _seconds("PAYWALL_ENTITLEMENT_CACHE_SECONDS", 60.0, 5.0, 120.0)
    grace = _seconds("PAYWALL_GRACE_SECONDS", 86400.0, 0.0, 86400.0)
    with _ENT_LOCK:
        cached = _ENT_CACHE.get(user_id)
        if cached and cached.fetched_at + fresh_ttl > now:
            return cached.allowed, cached.tier

    row, reachable = _store_entitlement(user_id)
    if reachable:
        tier = str((row or {}).get("tier") or "free").strip().lower()
        status = str((row or {}).get("status") or "none").strip().lower()
        features = {str(x) for x in ((row or {}).get("features") or [])}
        allowed = tier != "free" and status in _ACTIVE and required_feature in features
        verdict = _EntitlementVerdict(
            allowed=allowed,
            tier=tier,
            status=status,
            fetched_at=now,
            grace_until=(now + grace if allowed else now),
        )
        with _ENT_LOCK:
            if len(_ENT_CACHE) > 10000:
                _ENT_CACHE.clear()
            _ENT_CACHE[user_id] = verdict
        return allowed, tier

    # Store outage only: preserve a previously confirmed positive verdict. A
    # token/auth failure never reaches this function, and invalidation removes
    # the positive before a webhook-triggered downgrade can receive grace.
    if cached and cached.allowed and cached.status in _ACTIVE and cached.grace_until > now:
        return True, cached.tier
    return False, "free"


def invalidate_entitlement(user_id: str) -> None:
    """Called by billing immediately after any entitlement mutation."""
    with _ENT_LOCK:
        _ENT_CACHE.pop(user_id, None)


def enforce_site_full(user: dict[str, Any], *, always: bool = False) -> dict[str, Any]:
    """FastAPI dependency policy for premium API surfaces.

    Static Caddy matching cannot cover /api/* because those requests are proxied
    before file serving. Premium APIs call this same authority explicitly.
    During staging (PAYWALL_ENABLED=0) the existing registered-user behavior is
    unchanged unless ``always=True``. Premium payload routes that launch ahead
    of the global wall use that flag and fail closed in every environment.
    """
    if not always and not _enabled():
        return user
    user_id = str(user.get("id") or "")
    if not user_id:
        from fastapi import HTTPException  # noqa: PLC0415
        raise HTTPException(403, detail={"locked": True, "required_feature": "site_full"})
    try:
        cfg = _load_config()
        feature = str(cfg["premium"]["required_feature"])
        allowed, _tier = _entitled(user_id, feature)
    except Exception as exc:  # noqa: BLE001
        log.warning("paywall: API entitlement check failed closed (%s)", exc)
        allowed = False
    if not allowed:
        from fastapi import HTTPException  # noqa: PLC0415
        raise HTTPException(
            403,
            detail={
                "locked": True,
                "tier": "essential",
                "required_feature": "site_full",
                "upgrade_url": "/plans.html?upgrade=1",
            },
        )
    return user


def _headers(verdict: str) -> dict[str, str]:
    return {
        "Cache-Control": "private, no-store",
        "Vary": "Cookie",
        "X-Paywall": verdict,
        "X-Robots-Tag": "noindex, noarchive",
    }


def _locked(request: Request, path: str, tier: str = "essential") -> Response:
    if _is_document(request, path):
        try:
            body = INTERSTITIAL.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 — still deny with a self-contained fallback
            body = "<!doctype html><title>Member access required</title><h1>Member access required</h1>"
        return HTMLResponse(body, status_code=403, headers=_headers("deny"))
    return JSONResponse(
        {
            "locked": True,
            "tier": tier,
            "required_feature": "site_full",
            "upgrade_url": "/plans.html?upgrade=1",
        },
        status_code=403,
        headers=_headers("deny"),
    )


@router.api_route("/api/control-room/auth-check", methods=["GET", "HEAD"])
def control_room_auth_check(request: Request) -> Response:
    """Bodyless Caddy subrequest admitting only the configured operator UUID."""
    raw_operator = os.environ.get("SUPABASE_OPERATOR_USER_ID", "")
    try:
        operator = str(uuid.UUID(raw_operator))
    except (ValueError, TypeError, AttributeError):
        return Response(status_code=503)
    if operator != raw_operator:
        return Response(status_code=503)

    from app.main import _mm_supabase_access_token  # noqa: PLC0415

    token = _mm_supabase_access_token(request)
    if not token:
        return Response(status_code=401)
    identity = _resolve_identity(token)
    if identity.status in {"outage", "busy"}:
        return Response(status_code=502)
    if identity.status != "ok" or not identity.uid:
        return Response(status_code=401)
    if not hmac.compare_digest(identity.uid, operator):
        return Response(status_code=403)
    return Response(status_code=204)


@router.get("/api/paywall/check")
def paywall_check(request: Request) -> Response:
    """Caddy auth subrequest. Any unhandled failure denies, never serves."""
    path = "/"
    try:
        path = _normalized_path(request.headers.get("x-original-uri"))
        access = classify_path(path)
        if access == "deny":
            if _is_document(request, path):
                return HTMLResponse(
                    "<!doctype html><title>Not found</title><h1>Not found</h1>",
                    status_code=404,
                    headers=_headers("not-found"),
                )
            return JSONResponse({"error": "not_found"}, status_code=404, headers=_headers("not-found"))
        if access in {"public", "free"}:
            return Response(status_code=204, headers=_headers(access))
        early = enforced_early(path)
        if not (_enabled() or early):
            return Response(status_code=204, headers=_headers("off"))

        from app.main import _mm_supabase_access_token  # noqa: PLC0415

        token = _mm_supabase_access_token(request)
        if not token:
            return _locked(request, path)
        uid = _fresh_uid(token)
        if not uid:
            return _locked(request, path)
        cfg = _load_config()
        feature = str(cfg["premium"]["required_feature"])
        allowed, tier = _entitled(uid, feature)
        if not allowed:
            return _locked(request, path, str(cfg["premium"].get("default_tier") or "essential"))
        return Response(status_code=204, headers=_headers(f"allow-{tier}"))
    except Exception as exc:  # noqa: BLE001 — fail CLOSED under every error
        log.warning("paywall: check failed closed (%s)", exc)
        return _locked(request, path)


# =============================================================================
# Pro-only HOST gate — bot.mastermind-x.com (the Mastermind Bot desk)
# =============================================================================
# A second Caddy auth subrequest, deliberately NOT a mode of ``paywall_check``.
#
# The bot desk is a DIFFERENT application (mastermind.service, uvicorn :8001,
# repo ../Mastermind) with its own URL space -- ``/``, ``/research``, ``/desk``,
# ``/api/positions``, ... . ``config/site_access.yml`` describes the MACRO site's
# paths and nothing else, so classifying a bot URL against it answers a question
# about a page that does not exist: every unknown path reads ``premium`` (right
# answer by accident) and any path that happens to collide with a macro ``deny``
# entry would 404 a real bot page. So this endpoint classifies NOTHING. It gates
# on WHO the caller is, identically on every path of that host.
#
# It is also independent of ``PAYWALL_ENABLED``: that switch stages the macro
# site's wall, while the bot desk is Pro-only from the moment it ships.
#
# WHO GETS IN, in order: the operator email allowlist (``_operator_unlimited``,
# the same one /api/me reads), then a paid entitlement whose tier ranks at or
# above ``pro``. Nothing else. The allowlist comes FIRST because /api/me grants
# `unlimited` without ever writing it to the entitlement row -- checking the row
# first would deny an operator the account card says is uncapped.

PRO_INTERSTITIAL = Path(__file__).with_name("paywall_pro_interstitial.html")
PLANS_CONFIG = REPO / "config" / "plans.yml"

#: Where a denied visitor is sent. Deliberately RELATIVE, matching ``_locked``'s
#: ``upgrade_url`` -- but note this body is delivered on bot.mastermind-x.com, which does
#: not serve /plans.html, so a client that follows it verbatim needs to resolve it against
#: the macro origin itself. The HTML branch below does that resolution for the visitor
#: because a plain <a href> would not.
PRO_UPGRADE_URL = "/plans.html?upgrade=1&plan=pro"
_SITE_BASE = os.environ.get("MM_SITE_BASE", "https://mastermind-x.com").rstrip("/")

#: The entitlement feature every paid product carries (config/plans.yml
#: products.*.features). Named here rather than read from site_access.yml's
#: ``premium.required_feature``: that file is the macro site's policy and this gate must
#: not move when it does. The TIER check below is what makes the desk Pro-only.
_PRO_FEATURE = "site_full"

#: Floor tier for the bot desk, resolved against config/plans.yml ``tier_rank``.
_PRO_MIN_TIER = "pro"

#: An entitlement ROW that literally carries an uncapped tier. This is the belt to
#: ``_operator_unlimited``'s braces, and it is NOT how the operator actually gets in:
#: /api/me never reads ``unlimited`` out of the database either -- it computes the real
#: tier and then OVERWRITES it from the email allowlist (app/main.py, get_user_quotas ->
#: tier == "unlimited"). So this constant only fires if some future provisioning writes
#: the string into ``user_entitlements.tier``, and claiming it as the operator bypass
#: would be a false guarantee. Every OTHER off-catalog string denies: unknown ranks
#: nowhere.
_UNCAPPED_TIERS = frozenset({"unlimited"})

_PLANS_CACHE: tuple[dict[str, Any], int] | None = None
_PLANS_LOCK = threading.Lock()

_PRO_FALLBACK_HTML = (
    '<!doctype html><html lang="en"><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    "<title>Pro members only</title>"
    "<h1>Pro members only</h1>"
    "<p>The Mastermind Bot desk is part of the Pro membership.</p>"
    "<p>此页面仅向 Pro 会员开放。</p>"
    f'<p><a href="{_SITE_BASE}/plans.html?upgrade=1&amp;plan=pro">See plans</a></p>'
    "</html>"
)


def _load_plans() -> dict[str, Any]:
    """mtime-cached catalog load, same shape as ``_load_config``.

    A missing, unreadable or shapeless catalog RAISES; every caller sits inside a
    fail-closed ``except``, so an unusable catalog denies rather than guesses an order.
    """
    global _PLANS_CACHE
    stamp = PLANS_CONFIG.stat().st_mtime_ns
    with _PLANS_LOCK:
        if _PLANS_CACHE and _PLANS_CACHE[1] == stamp:
            return _PLANS_CACHE[0]
        raw = yaml.safe_load(PLANS_CONFIG.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("invalid plan catalog")
        rank = raw.get("tier_rank")
        if not isinstance(rank, list) or not rank:
            raise ValueError("plans.tier_rank must be a non-empty list")
        _PLANS_CACHE = (raw, stamp)
        return raw


def _tier_rank() -> list[str]:
    """The catalog's low -> high tier ordering (config/plans.yml ``tier_rank``)."""
    return [str(t).strip().lower() for t in _load_plans()["tier_rank"]]


def _ranks_at_least(tier: object, minimum: str) -> bool:
    """True when the observed tier sits at or above ``minimum`` in the catalog order.

    The catalog is read FIRST, before the uncapped exception, so an unusable catalog
    denies EVERYONE -- one rule, no exception to fail-closed. A catalog that no longer
    carries ``minimum`` raises out of ``.index`` for the same reason: a catalog without
    Pro must not open the door.

    The tier is normalized (lib/tiers.py) because a pre-rename row still says
    ``insider`` and an alias ranks nowhere; skipping it reaches the same verdict for
    every tier the catalog sells today, but reports the customer's tier wrongly.

    Unknown => deny.
    """
    rank = _tier_rank()
    floor = rank.index(str(minimum).strip().lower())
    canonical = normalize_tier(tier)
    if canonical in _UNCAPPED_TIERS:
        return True
    if canonical not in rank:
        return False
    return rank.index(canonical) >= floor


def _operator_unlimited(email: str) -> bool:
    """True iff ``email`` is on BRAIN_UNLIMITED_ALLOWLIST -- the operator bypass.

    This is the ONLY thing that admits an operator whose entitlement row is unpaid, and
    it is reached through the SAME accessor /api/me uses (``app.main._brain_module()``
    -> ``brain_gateway._unlimited_allowed``) rather than re-reading the env var here.
    Two copies of the parsing would be two answers to "what tier is this human", and
    the pill on the account card disagreeing with the door is the bug this closes.

    The lookup is an exact strip+lower set membership against an env var -- no IO, safe
    on an auth path. ANY failure returns False and the caller falls through to the
    normal tier check: a broken allowlist must never be the reason someone is denied,
    and never the reason someone is admitted.
    """
    try:
        from app.main import _brain_module  # noqa: PLC0415

        return bool(_brain_module()._unlimited_allowed(email))  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        log.warning("paywall: unlimited allowlist unavailable, falling through (%s)", exc)
        return False


def _locked_pro(request: Request, path: str, tier: str) -> Response:
    """403 for the Pro host: the interstitial for a document, JSON for anything else."""
    if _is_document(request, path):
        try:
            body = PRO_INTERSTITIAL.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 — still deny, with a self-contained fallback
            body = _PRO_FALLBACK_HTML
        return HTMLResponse(body, status_code=403, headers=_headers("deny"))
    return JSONResponse(
        {
            "locked": True,
            "tier": tier,
            "required_tier": _PRO_MIN_TIER,
            "upgrade_url": PRO_UPGRADE_URL,
        },
        status_code=403,
        headers=_headers("deny"),
    )


@router.get("/api/paywall/check_pro")
def paywall_check_pro(request: Request) -> Response:
    """Caddy auth subrequest for a Pro-only HOST. Any unhandled failure denies.

    Identity rides the shared Supabase session cookie, which is scoped to
    ``.mastermind-x.com`` (templates/theme.js), so a request to a ``bot.`` URL carries
    it unchanged. 204 lets Caddy's ``@status 2xx`` matcher continue to the origin;
    anything else is streamed back to the visitor and the origin is never reached.
    """
    path = "/"
    try:
        path = _normalized_path(request.headers.get("x-original-uri"))

        from app.main import _mm_supabase_access_token  # noqa: PLC0415

        token = _mm_supabase_access_token(request)
        uid, email = _fresh_identity(token) if token else (None, "")
        if not uid:
            return _locked_pro(request, path, "anon")
        # The operator bypass, before any entitlement read: /api/me grants `unlimited`
        # off this same allowlist WITHOUT touching the row, so gating the operator on
        # his row would make the account pill and this door disagree.
        if email and _operator_unlimited(email):
            return Response(status_code=204, headers=_headers("allow-unlimited"))
        # Same authority, cache and positive-only outage grace as the macro wall; it
        # already requires status in {active, trialing}. The tier gate is the extra half.
        allowed, tier = _entitled(uid, _PRO_FEATURE)
        if not allowed or not _ranks_at_least(tier, _PRO_MIN_TIER):
            return _locked_pro(request, path, normalize_tier(tier) or "free")
        return Response(status_code=204, headers=_headers(f"allow-{normalize_tier(tier)}"))
    except Exception as exc:  # noqa: BLE001 — fail CLOSED under every error
        log.warning("paywall: pro host gate failed closed (%s)", exc)
        return _locked_pro(request, path, "anon")
