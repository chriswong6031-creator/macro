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
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

log = logging.getLogger("macro.paywall")
router = APIRouter()

REPO = Path(os.environ.get("MACRO_REPO") or Path(__file__).resolve().parents[1])
ACCESS_CONFIG = Path(os.environ.get("SITE_ACCESS_CONFIG") or REPO / "config" / "site_access.yml")
INTERSTITIAL = Path(__file__).with_name("paywall_interstitial.html")
_ACTIVE = frozenset({"active", "trialing"})

_CONFIG_CACHE: tuple[dict[str, Any], int] | None = None
_CONFIG_LOCK = threading.Lock()
_AUTH_CACHE: dict[str, tuple[str | None, float]] = {}
_AUTH_LOCK = threading.Lock()


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


def _fresh_uid(token: str) -> str | None:
    """Verify token against Supabase with a ≤60s hashed-token cache."""
    from app.main import SUPABASE_ANON_KEY, SUPABASE_URL  # noqa: PLC0415

    key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.monotonic()
    with _AUTH_LOCK:
        hit = _AUTH_CACHE.get(key)
        if hit and hit[1] > now:
            return hit[0]
    uid = None
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read())
        candidate = data.get("id")
        if isinstance(candidate, str):
            uuid.UUID(candidate)
            uid = candidate
    except Exception:  # noqa: BLE001 — invalid/expired/upstream failure all deny
        uid = None
    ttl = _seconds("PAYWALL_AUTH_CACHE_SECONDS", 45.0, 1.0, 60.0)
    with _AUTH_LOCK:
        if len(_AUTH_CACHE) > 5000:
            _AUTH_CACHE.clear()
        _AUTH_CACHE[key] = (uid, now + ttl)
    return uid


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
