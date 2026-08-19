"""app/research.py — FastAPI router for the Research Vault serving tier (RV W2).

Mirrors ``app/hub.py`` (R2 read-through + TTL cache + ``{stale:true}`` idiom) for
the two PUBLIC routes, and the ``brain_gateway`` gate idiom (Supabase tier resolve
+ file-based day quota) for the three PAID routes. Contract: masterplan §9.

Routes
------
GET  /api/research/catalog            public  — latest 3 summaries; full catalog for Pro
GET  /api/research/search?q=&…        public  — preview-only results; full search for Pro
GET  /api/research/view/{doc_id}      PRO     — stream PDF inline (rate-limited, no quota)
POST /api/research/download/{doc_id}  PRO     — watermark + attachment (daily quota
                                                10/day; 50/day on a lifetime grant)
GET  /api/research/quota              authed  — read-only remaining today

SECURITY INVARIANTS (the red-team probes these — see the block above each guard):
  1. doc_id is validated to the slug shape ``^[a-z0-9][a-z0-9-]{0,120}$`` AND must
     EXIST in the catalog before any R2 key is built. The key is
     ``f"research_vault/{doc_id}.pdf"`` built ONLY from the validated id — raw user
     input never reaches an R2 key. Blocks path traversal / key injection / prefix
     listing.
  2. Entitlement fails CLOSED: any error/absence resolving tier → 'free' → blocked
     (402). Reading is PRO-only — essential/free/unknown are NEVER granted view (402
     paid_required); Essential is a browse-and-teaser tier. (The download COUNTER
     fails OPEN per the availability rule in download_quota — deliberate asymmetry.)
  3. Server-authoritative quota: the 402 on exhaustion is returned regardless of
     client state; the counter increments only on a successful allow, before bytes.
  4. No public PDF path: PDFs come from the PRIVATE bucket via server creds; there
     is no public URL and no static route. view=inline, download=attachment; both
     ``no-store`` + ``noindex``.
  5. Never log/leak the bearer, Supabase keys, or R2 creds; never echo a raw IP
     into a filename (view_ratelimit hashes it).

Never-raise at the route boundary: every handler returns a proper HTTP status
(400/402/404/429/503), never a 500 stack.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from engine.research_vault import catalog as catalog_mod
from engine.research_vault import corpus as corpus_mod
from engine.research_vault import download_quota, view_ratelimit, watermark

log = logging.getLogger("research_vault.api")

router = APIRouter()

# R2 keys (canonical — mirror the W1 engine constants; do not reinterpolate).
_CATALOG_KEY = "research_vault/catalog.json"          # catalog_mod.CATALOG_KEY
_VAULT_PREFIX = "research_vault/"                      # ingest VAULT_PREFIX
# The corpus key now lives with the reader that fetches it: corpus_mod.CORPUS_KEY.

_UPGRADE_URL = "/plans.html"
# Reading research (stream PDF + download) is a PRO-only benefit. Essential is a
# TEASER tier: it may browse the latest three summaries, but the full catalog,
# full search, view, and download surfaces require PRO — essential/free/unknown all
# stay on the preview or resolve to 402 paid_required. Fails CLOSED.
_VIEW_TIERS = frozenset({"pro"})
_PUBLIC_PREVIEW_COUNT = 3

# ── doc_id validation ──────────────────────────────────────────────────────
# The slug shape produced by sidecar.slug (lowercase alnum + hyphens, first char
# alnum, ≤121 chars). ANY id failing this is a 400 — it never reaches an R2 key.
# ``\A``/``\Z`` (absolute string anchors), NOT ``^``/``$`` — a ``$`` would match
# just before a trailing "\n", so "valid-id\n" would clear a ``$``-anchored check
# and let a newline into the R2 key. ``\Z`` matches only the true end of string.
_DOC_ID_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{0,120}\Z")

# ── search input clamps ────────────────────────────────────────────────────
_SEARCH_LIMIT_MAX = 50
_SEARCH_LIMIT_DEFAULT = 30
_Q_MAX = 200
_FACET_MAX = 80


# ---------------------------------------------------------------------------
# auth dependency — lazy wrapper around app.main.require_user
# ---------------------------------------------------------------------------
# Imported at CALL time, NOT module-import time: app/main.py mounts this router
# inside its own module body, so a top-level `from app.main import require_user`
# would run during app.main's partial initialization and raise ImportError (which
# the mount guard swallows → the router silently never mounts). Resolving it in the
# request path avoids that circular window entirely and keeps the same 401 behavior
# (require_user reads the bearer + verifies it against Supabase, secretless).

def require_user(authorization: str | None = Header(default=None)) -> dict:
    """Verify the Supabase bearer via app.main.require_user (resolved lazily).

    Kept as a thin ``Depends`` wrapper so this module has no import-time dependency
    on app.main. Tests override this dependency (``app.dependency_overrides``) to
    inject a stub user without hitting Supabase.
    """
    from app.main import require_user as _ru  # noqa: PLC0415 — lazy, breaks cycle
    return _ru(authorization)


# ---------------------------------------------------------------------------
# store factory (monkeypatchable in tests → LocalStore, no real R2)
# ---------------------------------------------------------------------------

def _build_store():
    """Return the active object store for the PRIVATE research bucket, or None.

    Delegates to ``engine.research_vault.r2_store.build_store`` (env precedence:
    RESEARCH_LOCAL_STORE → R2_RESEARCH_BUCKET+creds). Tests monkeypatch THIS
    function to inject a ``LocalStore`` so no live R2/Supabase is hit. Imported
    lazily so the router mounts even if boto3 is absent.
    """
    from engine.research_vault.r2_store import build_store  # noqa: PLC0415
    return build_store()


# ---------------------------------------------------------------------------
# catalog read-through (hub.py TTL + {stale:true} idiom, but over R2Store creds)
# ---------------------------------------------------------------------------

_CATALOG_CACHE: dict[str, tuple[dict, float]] = {}
_CATALOG_TTL = 60.0  # seconds (masterplan §9)
_CATALOG_LOCK = threading.Lock()


def _cached_good() -> dict | None:
    """The last catalog that PASSED validation, or None. Never a synthetic empty."""
    with _CATALOG_LOCK:
        hit = _CATALOG_CACHE.get(_CATALOG_KEY)
    return hit[0] if hit is not None else None


def _with_health(catalog: dict, reason: str = "") -> dict:
    """Attach the freshness projection to a shallow copy of ``catalog``.

    ``catalog_health`` is the explicit block (state/generated_at/age_seconds/
    reason); ``stale`` is retained as the pre-Wave-4 boolean so an un-updated
    client keeps working. Both are DERIVED from the document's own producer clock
    on every call — nothing is persisted, so there is no second health store to
    fall out of sync with the catalog (freeze §A).
    """
    out = dict(catalog)
    try:
        state = catalog_mod.health(catalog, reason=reason)
    except catalog_mod.CatalogUnavailable as exc:
        # A cached copy always validated on the way in, so this is unreachable in
        # practice; fail toward "not live" rather than inventing a fresh label.
        state = {"state": catalog_mod.STATE_STALE, "generated_at": "",
                 "age_seconds": None, "reason": exc.reason}
    out["catalog_health"] = state
    out["stale"] = state["state"] != catalog_mod.STATE_FRESH
    return out


def _load_catalog() -> dict:
    """Authoritative catalog + its freshness verdict; 503 when nothing is valid.

    Fail-CLOSED read (``catalog.read_strict``) behind the 60s TTL cache. The cache
    holds only documents that PASSED validation, so a corrupt or missing object can
    never be served as an empty-but-healthy vault (Defect 3), and a successful read
    of an arbitrarily old object can never be labelled live (Defect 1) — age is
    recomputed from ``generated_at`` on every call, including cache hits, so a
    cached copy ages into ``stale`` on its own.

    Degradation ladder, in order:
      1. fresh/old-but-valid authoritative read → serve it, health says which;
      2. read failed (missing / corrupt / store outage) but a validated copy is
         cached → serve that copy as STALE, carrying the failure ``reason``;
      3. no valid copy has ever been seen → HTTPException(503).
    """
    now = time.monotonic()
    with _CATALOG_LOCK:
        hit = _CATALOG_CACHE.get(_CATALOG_KEY)
        if hit is not None and (now - hit[1]) < _CATALOG_TTL:
            return _with_health(hit[0])

    store = _build_store()
    if store is None:
        cached = _cached_good()
        if cached is not None:
            return _with_health(cached, reason="store_unavailable")
        raise HTTPException(503, "research catalog unavailable (no store configured)")

    try:
        cat = catalog_mod.read_strict(store)
    except catalog_mod.CatalogUnavailable as exc:
        log.warning("research_vault: catalog unavailable (%s) — %s", exc.reason, exc.detail)
        cached = _cached_good()
        if cached is not None:
            return _with_health(cached, reason=exc.reason)
        raise HTTPException(503, f"research catalog unavailable ({exc.reason})") from None
    except Exception as exc:  # noqa: BLE001 — belt: read_strict already classifies
        log.warning("research_vault: catalog read raised (%s)", exc)
        cached = _cached_good()
        if cached is not None:
            return _with_health(cached, reason="store_error")
        raise HTTPException(503, "research catalog unavailable") from None

    with _CATALOG_LOCK:
        _CATALOG_CACHE[_CATALOG_KEY] = (cat, now)
    return _with_health(cat)


def _catalog_ids() -> set[str]:
    """The ids the CURRENT catalog admits — the universal visibility set.

    Every user-visible surface is restricted to this set, for every tier. The
    corpus is published BEFORE the catalog (freeze §A), so between those two puts
    the corpus can legitimately hold a row the catalog has not admitted yet; that
    row must stay invisible until the catalog publishes. Raises the same 503 as
    :func:`_load_catalog` when visibility cannot be established at all — refusing
    to answer is correct, because with no catalog we cannot prove ANY id is public.
    """
    return {
        str((item or {}).get("id") or "")
        for item in (_load_catalog().get("items") or [])
    }


def _catalog_has(doc_id: str) -> bool:
    """True iff ``doc_id`` is a known catalog item id (existence gate for §1)."""
    try:
        cat = _load_catalog()
    except HTTPException:
        # Catalog unavailable → we cannot prove existence → treat as not-found
        # (fail closed on existence; we never serve an unverified id).
        return False
    items = cat.get("items") or []
    return any((it or {}).get("id") == doc_id for it in items)


def _catalog_title(doc_id: str) -> str:
    """Best-effort title for the download filename; '' when unknown."""
    try:
        cat = _load_catalog()
    except HTTPException:
        return ""
    for it in cat.get("items") or []:
        if (it or {}).get("id") == doc_id:
            return str((it or {}).get("title") or "")
    return ""


# ---------------------------------------------------------------------------
# corpus read-through — DELEGATED to engine.research_vault.corpus (W4)
# ---------------------------------------------------------------------------
# The fetch + tempdir + TTL + background-refresh machinery used to live here and
# was the process's only corpus reader. The Mastermind brain now reads the same
# corpus (mode='report' on search_research) from the SAME process — app/main.py
# imports brain_gateway in the request path — so the logic moved to the engine
# module and this router delegates. One local copy, one refresh clock, one
# download; behaviour otherwise unchanged (serve-stale-while-revalidate, 300s TTL,
# only the very first call on a cold process blocks).
#
# `_build_store` is passed BY NAME and resolved at call time, so this module's
# store factory (and every test that monkeypatches it) still decides where the
# bytes come from.


def _corpus_conn():
    """Open the shared local corpus copy. Returns a connection or None; never raises.

    Thin delegation to :func:`engine.research_vault.corpus.corpus_connection` —
    see the block comment above. The caller owns closing the connection.
    """
    return corpus_mod.corpus_connection(store_factory=_build_store)


# ---------------------------------------------------------------------------
# tier resolution — reuse brain_gateway._resolve_tier (canonical, fail-safe→free)
# ---------------------------------------------------------------------------

# Only these subscription statuses unlock a paid tier. A row that still carries a
# paid ``tier`` but a non-active status (canceled / past_due / incomplete / unpaid)
# collapses to 'free' — mirrors engine/neuralweb/brain_gateway._get_allowance
# (brain_gateway.py: status=='active'→tier bucket, 'trialing'→trial, else→free).
# Without this a lapsed subscriber whose entitlement row is flipped (not deleted)
# by the Stripe webhook would keep full vault access. Fails CLOSED.
_ACTIVE_STATUSES = frozenset({"active", "trialing"})


def _effective_tier(tier: str | None, status: str | None) -> str:
    """Collapse (tier, status) → the tier that actually grants access, or 'free'.

    A paid tier only counts when ``status`` is active/trialing; any other status
    (or a missing/blank one) → 'free'. This is the paywall's status gate.
    """
    t = str(tier or "free").strip().lower() or "free"
    if t == "free":
        return "free"
    s = str(status or "").strip().lower()
    return t if s in _ACTIVE_STATUSES else "free"


def _resolve_tier(user_id: str) -> str:
    """Resolve the caller's EFFECTIVE plan tier, failing CLOSED to 'free'.

    Canonical resolver is ``engine.neuralweb.brain_gateway._resolve_tier`` (queries
    Supabase ``user_entitlements`` via PostgREST with the service key, 60s cache,
    fail-safe → free), which returns ``{tier, status, current_period_end}``. We
    honor ``status`` via :func:`_effective_tier` — a paid tier with a non-active
    status (lapsed/canceled) is treated as 'free'. We import it lazily; if it is
    unimportable in the app context we fall back to a self-contained PostgREST
    query that ALSO fails CLOSED → 'free'. Under NO path does an unknown OR a
    non-active user resolve to a paid tier (SECURITY invariant 2).
    """
    if not user_id:
        return "free"
    try:
        from engine.neuralweb.brain_gateway import _resolve_tier as _bg  # noqa: PLC0415
        ent = _bg(user_id) or {}
        return _effective_tier(ent.get("tier"), ent.get("status"))
    except Exception as exc:  # noqa: BLE001 — canonical resolver unavailable
        log.debug("research_vault: canonical tier resolver unavailable (%s) — fallback", exc)
        return _resolve_tier_fallback(user_id)


def _resolve_tier_fallback(user_id: str) -> str:
    """Self-contained PostgREST entitlement lookup; fail-CLOSED → 'free'.

    Only used if the canonical brain_gateway resolver cannot be imported. Mirrors
    its query (service key, user_entitlements, tier+status) and status gate but is
    intentionally minimal (no cache). Any missing config, network error, empty
    result, or non-active status → 'free'.
    """
    import json as _json  # noqa: PLC0415
    import urllib.parse as _url  # noqa: PLC0415
    import urllib.request as _req  # noqa: PLC0415

    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        return "free"
    try:
        url = (
            f"{base}/rest/v1/user_entitlements"
            f"?user_id=eq.{_url.quote(user_id)}&select=tier,status"
        )
        r = _req.Request(url, headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        })
        with _req.urlopen(r, timeout=5) as resp:
            rows = _json.loads(resp.read())
        if isinstance(rows, list) and rows:
            return _effective_tier(rows[0].get("tier"), rows[0].get("status"))
    except Exception as exc:  # noqa: BLE001 — fail CLOSED, never leak the key
        log.debug("research_vault: fallback tier resolve failed (%s) — free", exc)
    return "free"


def _can_view(tier: str) -> bool:
    """True only for tiers that may stream/download a research PDF (PRO-only)."""
    return tier in _VIEW_TIERS


def _is_lifetime(user_id: str) -> bool:
    """True when the caller holds a LIFETIME entitlement (comp grant, no period end).

    Mirrors the account panel's rule verbatim (``site/theme.js`` ``_sdPlanChip``:
    ``(tier==='unlimited' || source==='comp') && !current_period_end && status !==
    'canceled'``) — the exact row ``admin/entitlements.grant_pass(kind='lifetime')``
    writes. Kept in sync on purpose: a user whose plan is chipped "Lifetime" is the
    user who gets the lifetime download allowance.

    This only ever RAISES the cap — ``download_quota._limit_for`` refuses to promote
    a zero-allowance tier, so ``_resolve_tier``/``_can_view`` remain the sole
    paywall. Fails CLOSED to False (the standard Pro 10/day) on any error: a
    Supabase hiccup costs a lifetime holder headroom, never hands a stranger access.

    Costs one extra PostgREST read on the two metered routes, which is why callers
    go through :func:`_lifetime_for` and skip it entirely for tiers that get 0.
    """
    if not user_id:
        return False
    try:
        from app.billing import read_entitlement  # noqa: PLC0415 — lazy, mirrors _resolve_tier
        ent = read_entitlement(user_id) or {}
    except Exception as exc:  # noqa: BLE001 — a plan lookup must never break a download
        log.debug("research_vault: lifetime lookup failed (%s) — standard allowance", exc)
        return False
    if str(ent.get("status") or "").strip().lower() == "canceled":
        return False
    if ent.get("current_period_end"):  # a dated period is a subscription, not a lifetime
        return False
    return (str(ent.get("source") or "").strip().lower() == "comp"
            or str(ent.get("tier") or "").strip().lower() == "unlimited")


def _lifetime_for(tier: str, user_id: str) -> bool:
    """Lifetime flag for the quota call, short-circuited for tiers that cannot download.

    Free/essential have a 0 allowance that a lifetime flag cannot lift, so there is
    nothing to learn from the lookup — skipping it keeps ``/api/research/quota``
    a single Supabase round-trip for the non-paid callers who hit it most.
    """
    return _can_view(tier) and _is_lifetime(user_id)


def _user_id_of(user: dict) -> str:
    """Stable user key: Supabase id, else email, else 'unknown'."""
    return str((user or {}).get("id") or (user or {}).get("email") or "unknown")


def _optional_tier(authorization: str | None) -> str:
    """Resolve a bearer when present; missing/invalid credentials stay anonymous.

    These read routes remain reachable without an account, but an invalid token
    must never unlock more than the public preview.
    """
    if not authorization:
        return "anon"
    try:
        return _resolve_tier(_user_id_of(require_user(authorization)))
    except Exception as exc:  # noqa: BLE001 — fail closed to the public preview
        log.debug("research_vault: optional auth failed (%s) — anon preview", exc)
        return "anon"


def _client_ip(request: Request) -> str:
    """Best-effort client IP for the view rate-limiter (hashed downstream).

    Prefers the CDN/proxy forwarded header (first hop), else the socket peer.
    Only used as a rate-limit key — never trusted for auth, never logged raw.
    """
    xff = request.headers.get("x-forwarded-for") or ""
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client else "unknown"


def _validate_doc_id(doc_id: str) -> str:
    """Validate the slug shape and REQUIRE catalog existence, or raise 400/404.

    Order matters: shape first (400 on malformed — path traversal, uppercase,
    '..', slashes all die here), then existence (404 for a well-formed but unknown
    id). Only a value that clears BOTH is ever used to build an R2 key.
    """
    if not doc_id or not _DOC_ID_RE.match(doc_id):
        raise HTTPException(400, "invalid document id")
    if not _catalog_has(doc_id):
        raise HTTPException(404, "document not found")
    return doc_id


def _pdf_key(doc_id: str) -> str:
    """Build the private-bucket PDF key from an ALREADY-VALIDATED doc_id."""
    return f"{_VAULT_PREFIX}{doc_id}.pdf"


def _safe_filename(doc_id: str, title: str) -> str:
    """A safe attachment filename derived from the title (fallback: the id).

    Restricted to ``[A-Za-z0-9._ -]`` and length-capped so nothing exotic lands in
    the Content-Disposition header. Always ends in '.pdf'.
    """
    base = (title or "").strip() or doc_id
    base = re.sub(r"[^A-Za-z0-9._ -]", "", base).strip() or doc_id
    return f"{base[:80].rstrip()}.pdf"


# ---------------------------------------------------------------------------
# PUBLIC PREVIEW routes (optional Pro bearer)
# ---------------------------------------------------------------------------


def _catalog_preview(catalog: dict, limit: int = _PUBLIC_PREVIEW_COUNT) -> dict:
    """Return only the newest summary-ready reports while retaining total count."""
    items = list(catalog.get("items") or [])
    ready = [
        item for item in items
        if any(str(point or "").strip() for point in ((item or {}).get("summary_points") or []))
    ]
    preview = ready[:limit]
    selected = {str((item or {}).get("id") or "") for item in preview}
    if len(preview) < limit:
        preview.extend(
            item for item in items
            if str((item or {}).get("id") or "") not in selected
        )
    public = dict(catalog)
    public["items"] = preview[:limit]
    public["count"] = len(items)
    public["preview"] = True
    public["summary"] = catalog.get("summary") or catalog_mod.public_summary(catalog)
    public["institutions"] = sorted({
        str((item or {}).get("institution") or "").strip()
        for item in public["items"]
        if str((item or {}).get("institution") or "").strip()
    })
    return public


@router.get("/api/research/catalog")
def research_catalog(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Three public summaries, or the complete catalog for an authenticated Pro.

    R2 read-through of ``research_vault/catalog.json`` from the PRIVATE bucket via
    server creds, 60s TTL cache. ``{stale:true}`` merged when a refresh fails but a
    prior copy exists; 503 only if never fetched. No PDF bytes are returned.
    """
    catalog = dict(_load_catalog())
    catalog["preview"] = False
    catalog["summary"] = catalog_mod.public_summary(catalog)
    return catalog if _can_view(_optional_tier(authorization)) else _catalog_preview(catalog)


@router.get("/api/research/search")
def research_search(
    q: str = Query("", max_length=_Q_MAX),
    institution: str = Query("", max_length=_FACET_MAX),
    from_: str = Query("", alias="from", max_length=32),
    to: str = Query("", max_length=32),
    limit: int = Query(_SEARCH_LIMIT_DEFAULT),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """FTS search over the corpus, restricted to CATALOG-ADMITTED ids for every tier.

    Input is clamped (limit ≤ 50) and malformed queries degrade to an empty result.

    Two nested visibility gates, in order:

      1. **catalog admission — universal.** The catalog is the visibility commit
         (freeze §A) and the corpus is published BEFORE it, so a corpus row whose
         catalog publish has not landed yet is legitimately AHEAD of the public
         inventory. Every result, Pro included, is filtered to the ids the current
         catalog admits; before Wave 4 only the non-Pro branch did this, so a Pro
         search could surface a report that the vault had not admitted and whose
         PDF may not exist. If visibility cannot be established at all (no valid
         catalog anywhere) the route reports ``available: False`` rather than
         answering from the corpus alone.
      2. **tier preview — non-Pro only.** Anonymous, free, and Essential callers
         are then narrowed further to the three public preview reports.
    """
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        lim = _SEARCH_LIMIT_DEFAULT
    lim = max(1, min(_SEARCH_LIMIT_MAX, lim))

    # Establish the admitted id set BEFORE touching the corpus: with no valid
    # catalog there is no id we can prove is public, so there is nothing to search.
    try:
        admitted = _catalog_ids()
    except HTTPException:
        return {"items": [], "count": 0, "available": False}

    conn = _corpus_conn()
    if conn is None:
        return {"items": [], "count": 0, "available": False}

    try:
        items = corpus_mod.search(
            conn,
            q or "",
            institution=(institution or None),
            date_from=(from_ or None),
            date_to=(to or None),
            limit=lim,
        )
    except Exception as exc:  # noqa: BLE001 — corpus.search already degrades; belt
        log.debug("research_vault: search failed (%s)", exc)
        items = []
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    # Gate 1 — catalog admission, applied to EVERY tier (see the docstring).
    items = [item for item in items if str((item or {}).get("id") or "") in admitted]

    # Gate 2 — the non-Pro preview narrowing, applied on top.
    if not _can_view(_optional_tier(authorization)):
        preview_ids = {
            str((item or {}).get("id") or "")
            for item in _catalog_preview(_load_catalog()).get("items", [])
        }
        items = [item for item in items if str((item or {}).get("id") or "") in preview_ids]

    return {"items": items, "count": len(items), "available": True}


# ---------------------------------------------------------------------------
# PAID routes (require_user + paid tier)
# ---------------------------------------------------------------------------

@router.get("/api/research/view/{doc_id}")
def research_view(doc_id: str, request: Request,
                  user: dict = Depends(require_user)) -> Response:
    """Stream a PDF inline to an authenticated PRO user (no quota consumed).

    Gate order (each step is a distinct guard the red-team probes):
      1. auth (require_user) — 401 handled by the dependency.
      2. tier resolve → non-pro (essential/free/unknown) → 402 paid_required.
      3. doc_id validate (shape 400 / existence 404) BEFORE any R2 key.
      4. hourly view rate-limit (anti-scrape) → 429 on exceed.
      5. fetch from the PRIVATE bucket; 404 if the object is absent.
    Response: ``application/pdf`` · ``inline`` · ``private, no-store`` ·
    ``X-Robots-Tag: noindex, noimageindex``. Never touches the download quota.
    """
    user_id = _user_id_of(user)

    tier = _resolve_tier(user_id)
    if not _can_view(tier):
        return JSONResponse(
            {"error": "paid_required", "tier": tier, "upgrade": _UPGRADE_URL}, status_code=402)

    doc_id = _validate_doc_id(doc_id)  # 400 / 404

    allowed, info = view_ratelimit.allow(user_id, _client_ip(request))
    if not allowed:
        return JSONResponse(
            {"error": "rate_limited", "limit": info.get("limit"), "remaining": 0},
            status_code=429,
            headers={"Retry-After": "3600"})

    store = _build_store()
    pdf = store.get_bytes(_pdf_key(doc_id)) if store is not None else None
    if not pdf:
        raise HTTPException(404, "document not available")

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "private, no-store",
            "X-Robots-Tag": "noindex, noimageindex",
        },
    )


@router.post("/api/research/download/{doc_id}")
def research_download(doc_id: str, request: Request,
                      user: dict = Depends(require_user)) -> Response:
    """Metered, watermarked PDF download for an authenticated PRO user.

    Gate order (Wave 4, Defect 7 reordered steps 4-6 — see below):
      1. auth (require_user).
      2. tier resolve → non-pro (essential/free/unknown) → 402 paid_required.
      3. doc_id validate (400/404) BEFORE any R2 key.
      4. ``download_quota.peek`` — read-only. Exhausted → 402 WITHOUT fetching, so
         an exhausted caller can never be used to hammer R2.
      5. fetch PDF. Absent → 404 with the ledger UNTOUCHED.
      6. ``download_quota.check_and_increment`` — the authoritative debit, taken
         only once the bytes are in hand. A concurrent request that consumed the
         final slot between the peek and here is still refused: the increment,
         not the peek, is the server-authoritative gate.
      7. watermark with the buyer's identity, return as ``attachment`` ·
         ``private, no-store`` · ``X-Robots-Tag: noindex``.

    WHY the reorder: the debit used to happen BEFORE the fetch and was explicitly
    never refunded, so a missing object spent one of a paid subscriber's ten daily
    downloads and returned them nothing. That was rationalized as a rare
    just-deleted-document race — but Defect 5 in this same wave made missing PDFs
    PERSISTENT (a failed promotion still admitted the report to the catalog), which
    turns a rare race into a repeatable way to burn a paid allowance. Peek-then-
    fetch-then-debit removes the false debit without opening an unmetered fetch
    path, and needs no refund subsystem — there is nothing to refund.

    NOTE the deliberate asymmetry, unchanged: the tier resolve fails CLOSED
    (unknown→free→402) while the quota counter fails OPEN (broken ledger → allow,
    LOUD) — the first guards the paywall, the second guards a paid subscriber's
    availability. The peek inherits that: a ledger it cannot read reports the full
    allowance, so an outage never blocks a paying reader.
    """
    user_id = _user_id_of(user)
    email = str((user or {}).get("email") or user_id)

    tier = _resolve_tier(user_id)
    if not _can_view(tier):
        return JSONResponse(
            {"error": "paid_required", "tier": tier, "upgrade": _UPGRADE_URL}, status_code=402)

    doc_id = _validate_doc_id(doc_id)  # 400 / 404

    lifetime = _lifetime_for(tier, user_id)

    def _exhausted(info: dict) -> JSONResponse:
        return JSONResponse(
            {
                "error": "quota_exhausted",
                "remaining": 0,
                "limit": info.get("limit"),
                "tier": tier,
                "upgrade": _UPGRADE_URL,
            },
            status_code=402,
        )

    # (4) Read-only pre-check. Refusing here keeps an exhausted caller from
    # reaching R2 at all, which is what stops "no debit before fetch" from
    # becoming "unlimited un-metered fetches".
    peeked = download_quota.peek(user_id, tier, lifetime=lifetime)
    if int(peeked.get("remaining") or 0) <= 0:
        return _exhausted(peeked)

    # (5) Fetch BEFORE debiting: an object we cannot serve must cost nothing.
    store = _build_store()
    pdf = store.get_bytes(_pdf_key(doc_id)) if store is not None else None
    if not pdf:
        log.warning("research_vault: %s is catalog-admitted but its canonical PDF "
                    "is absent — 404 served, quota NOT debited", doc_id)
        raise HTTPException(404, "document not available")

    # (6) The authoritative debit, now that delivery is certain. peek() is advisory
    # only — between it and here a concurrent request may have taken the last slot,
    # and this call, which increments before it returns an allow, is what decides.
    allowed, info = download_quota.check_and_increment(
        user_id, tier, lifetime=lifetime)
    if not allowed:
        return _exhausted(info)

    from datetime import datetime, timezone  # noqa: PLC0415
    stamp_text = (
        f"{email} · {datetime.now(timezone.utc).strftime('%Y-%m-%d')} · "
        f"Mastermind Research — not for redistribution"
    )
    stamped = watermark.stamp(pdf, stamp_text)  # degrades to original on any error

    filename = _safe_filename(doc_id, _catalog_title(doc_id))
    return Response(
        content=stamped,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Robots-Tag": "noindex",
        },
    )


@router.get("/api/research/quota")
def research_quota(request: Request,
                   user: dict = Depends(require_user)) -> dict[str, Any]:
    """Read-only remaining downloads today (+ cheap remaining views this hour).

    Backs the viewer's download button. ``download_quota.peek`` does NOT increment.
    Non-paid tiers get ``limit: 0`` (the UI shows the Upgrade CTA).
    """
    user_id = _user_id_of(user)
    tier = _resolve_tier(user_id)

    info = download_quota.peek(user_id, tier, lifetime=_lifetime_for(tier, user_id))
    out = dict(info)
    # Cheap add-on: remaining views this hour (read-only, no increment).
    try:
        vinfo = view_ratelimit.peek(user_id, _client_ip(request))
        out["view_remaining"] = vinfo.get("remaining")
        out["view_limit"] = vinfo.get("limit")
    except Exception:  # noqa: BLE001 — view info is best-effort
        pass
    return out
