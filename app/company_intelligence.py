"""Public, context-only Company Intelligence API boundary.

The producer's verified reader already follows the immutable public R2
``marker -> generation -> company object`` chain and emits a deliberately
bounded projection.  This router gives the static Mastermind ticker dossiers a
same-origin way to read that projection without granting the browser access to
the reader's network controls or broadening its authority.

This endpoint is explanatory only.  It cannot create a signal, ranking,
position size, gate, or escalation.
"""
from __future__ import annotations

from collections import deque
import logging
import math
import re
from threading import Lock
import time
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from app import edge_client
from engine.company_intelligence.contracts import ContractError, safe_ticker
router = APIRouter()
log = logging.getLogger("macro.api.company_intelligence")

# This is intentionally *not* the reader's public contract.  The reader has a
# larger, authenticated/internal context contract used by Neural Web and
# Terminal.  This browser endpoint is the no-login teaser: enough verified
# information to make a company dossier useful, but not enough history or
# transport lineage to enumerate the underlying corpus.
#
# Keep this boundary recursively allowlisted.  Allowing ``latest_event`` as a
# top-level mapping would otherwise let a future reader field pass through to
# the browser by accident.
_TEASER_SCALAR_KEYS = (
    "available",
    "ticker",
    "company",
    "schema",
    "generated_at",
    "status",
    "is_context_only",
    "display_only",
    "authority",
    "untrusted_source_data",
    "latest_event",
    "note",
)
_COMPANY_KEYS = ("ticker", "display_name", "exchange")
_EVENT_SCALAR_KEYS = (
    "event_id",
    "fiscal_year",
    "fiscal_quarter",
    "call_date",
    "summary",
    "key_quote",
    "claim_citations_pending",
)
_PUBLIC_METRIC_KEYS = (
    "revenue_growth_pct",
    "eps_growth_pct",
    "gross_margin_pct",
    "questions_count",
)
_SOURCE_KEYS = ("kind", "status", "citation_precision")
_FIELD_LINEAGE_SCALAR_KEYS = ("summary", "key_quote")
_FIELD_LINEAGE_LIST_KEYS = (
    ("positive_highlights", 3),
    ("negative_highlights", 3),
    ("highlights", 6),
)
_NOT_COVERED_NOTE = "Company Intelligence does not cover this ticker"
_NOT_COVERED_WORKSPACE_NOTE = "Event workspace does not cover this ticker"
_NOT_COVERED_WORKSPACE_CODE = "event_workspace_not_covered"

# A teaser page can be CDN-cached safely because it contains no per-user data.
# Errors deliberately remain under app.main's default ``private, no-store``.
_PUBLIC_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=900"

# Anonymous public glance. Lifetime including SWR must not exceed the reader's
# 300-second workspace snapshot horizon.
_WORKSPACE_GLANCE_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=240"
_WORKSPACE_NOT_COVERED_CACHE_CONTROL = "public, max-age=60, stale-while-revalidate=240"

_GLANCE_SCHEMA = "event_workspace_public_glance.v1"
_PUBLIC_PRIMARY_RIGHTS = frozenset({"rp_public_primary_v1", "public_primary"})
_WATCH_MAX_ITEMS = 3
_WATCH_TEXT_MAX_CHARS = 500
_GUIDANCE_MAX_ITEMS = 4
_SOURCE_STATES_MAX_ITEMS = 8

# Closed label map for watch items keyed on metric or claim_id.
_WATCH_LABEL_MAP: dict[str, str] = {
    "demand_vs_supply": "Supply constraint",
    "claim_demand_vs_supply": "Supply constraint",
    "memory": "Memory cost/flood",
    "claim_memory_flood": "Memory cost/flood",
    "fx_yoy_headwind": "FX headwind",
    "claim_fx_headwind": "FX headwind",
}
_WATCH_RE = re.compile(r"memory|flood|fx|headwind|supply|constraint", re.IGNORECASE)
# Match "up 16%" or "up 16.5%" in lede text for YoY extraction.
_YOY_UP_RE = re.compile(r"up\s+(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
# Fallback: first bare percent figure.
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# Extract Qn from a horizon string like "FY2026 Q4" or "Q4".
_HORIZON_QN_RE = re.compile(r"Q([1-4])")

# Keep the inexpensive unauthenticated endpoint from becoming an R2 fetch
# amplifier.  Client-IP headers are attacker-suppliable by the time a request
# reaches the app, so this intentionally uses two independent budgets:
#
# * the claimed client identity is tight (60/min) and protects normal traffic;
# * the Caddy-injected TCP peer is looser (600/min) and catches someone who
#   rotates claimed EO/CF headers to burn a fresh client bucket every request.
#
# ``X-MM-Peer`` is trusted specifically because the production Caddy contract
# uses ``header_up`` to overwrite any inbound value before proxying.  It is not
# an application-level authentication header.  The CDN cache is the primary
# steady-state protection; these bounded process-local counters are the origin
# backstop.
_RATE_LIMIT_REQUESTS = 60
_PEER_RATE_LIMIT_REQUESTS = 600
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_KEYS = 8_192
_TRUSTED_PEER_HEADER = "x-mm-peer"
_rate_limit_lock = Lock()
_rate_limit_buckets: dict[str, deque[float]] = {}


def _is_public_scalar(value: Any) -> bool:
    """Return whether ``value`` is a finite JSON scalar (or null)."""
    return (
        value is None
        or isinstance(value, (str, bool, int))
        or (isinstance(value, float) and math.isfinite(value))
    )


def _scalar_projection(raw: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Copy explicitly named scalar fields and nothing else."""
    return {
        key: raw[key]
        for key in keys
        if key in raw and _is_public_scalar(raw[key])
    }


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value[:limit] if isinstance(item, str)]


def _company_projection(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    return _scalar_projection(raw, _COMPANY_KEYS)


def _metric_projection(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    return _scalar_projection(raw, _PUBLIC_METRIC_KEYS)


def _source_projection(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    # Do not expose source URL, receipt/hash, source_ref, or storage locator.
    # The three retained fields are semantic evidence labels only.
    return _scalar_projection(raw, _SOURCE_KEYS)


def _field_lineage_projection(value: Any, *, tags: list[str]) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    projected = _scalar_projection(raw, _FIELD_LINEAGE_SCALAR_KEYS)
    if isinstance(raw.get("metrics"), Mapping):
        projected["metrics"] = _scalar_projection(raw["metrics"], _PUBLIC_METRIC_KEYS)
    for key, limit in _FIELD_LINEAGE_LIST_KEYS:
        if key in raw:
            projected[key] = _string_list(raw[key], limit=limit)
    tag_lineage = raw.get("tags")
    if isinstance(tag_lineage, Mapping):
        projected["tags"] = {
            tag: tag_lineage[tag]
            for tag in tags[:24]
            if tag in tag_lineage and _is_public_scalar(tag_lineage[tag])
        }
    return projected


def _event_projection(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    projected = _scalar_projection(raw, _EVENT_SCALAR_KEYS)
    for key, limit in (
        ("positive_highlights", 3),
        ("negative_highlights", 3),
        ("tags", 24),
    ):
        if key in raw:
            projected[key] = _string_list(raw[key], limit=limit)
    tags = projected.get("tags") if isinstance(projected.get("tags"), list) else []
    if isinstance(raw.get("metrics"), Mapping):
        projected["metrics"] = _metric_projection(raw["metrics"])
    if isinstance(raw.get("field_lineage"), Mapping):
        projected["field_lineage"] = _field_lineage_projection(raw["field_lineage"], tags=tags)
    if isinstance(raw.get("previous_event_deltas"), Mapping):
        projected["previous_event_deltas"] = _metric_projection(raw["previous_event_deltas"])
    if isinstance(raw.get("sources"), (list, tuple)):
        projected["sources"] = [
            _source_projection(source)
            for source in raw["sources"][:3]
            if isinstance(source, Mapping)
        ]
    return projected


def _format_usd_millions(value: float) -> str:
    """Deterministic USD formatter — mirrors Terminal presentEventWorkspace."""
    billions = value / 1000.0
    if abs(billions) >= 1:
        if billions == int(billions):
            return f"${int(billions)}B"
        return f"${billions:.1f}B"
    return f"${int(round(value))}M"


def _format_percent_range(low: float, high: float) -> str:
    """Format guidance range with an en-dash, e.g. "9\u201311%"."""
    def _fmt(v: float) -> str:
        return str(int(v)) if v == int(v) else f"{v:.1f}"
    return f"{_fmt(low)}\u2013{_fmt(high)}%"


def _is_exact_public_evidence(span: object) -> bool:
    """True only for a byte-replayed span with an approved public-primary profile."""
    if not isinstance(span, Mapping):
        return False
    if span.get("receipt_state") != "byte_replayed":
        return False
    return str(span.get("rights_profile") or "") in _PUBLIC_PRIMARY_RIGHTS


def _bound_public_text(value: object, *, limit: int = _WATCH_TEXT_MAX_CHARS) -> str:
    text = str(value or "")
    return text[:limit]


def _extract_yoy_pct(text: str) -> str | None:
    """Return e.g. "+16%" from "up 16%" in lede text, or None."""
    m = _YOY_UP_RE.search(text)
    if m:
        raw = m.group(1)
        return f"+{raw.rstrip('0').rstrip('.') if '.' in raw else raw}%"
    m = _PCT_RE.search(text)
    if m:
        raw = m.group(1)
        return f"+{raw.rstrip('0').rstrip('.') if '.' in raw else raw}%"
    return None


def _glance_reported(workspace: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build the ``reported[]`` list — Revenue only in this wave."""
    facts = workspace.get("facts") or []
    claims = workspace.get("claims") or []

    revenue_fact = next(
        (f for f in facts
         if isinstance(f, Mapping)
         and f.get("metric") == "revenue"
         and isinstance(f.get("value"), (int, float))
         and _is_exact_public_evidence(f.get("source_span"))),
        None,
    )
    if revenue_fact is None:
        return []

    value_raw = float(revenue_fact["value"])
    formatted = _format_usd_millions(value_raw)
    sp = revenue_fact["source_span"]

    # YoY is a separate claim-derived assertion. Append it only when the
    # revenue-lede claim itself is exact-public. Typed-absent / address-only /
    # non-public lede still allows the exact revenue dollar figure.
    yoy: str | None = None
    for claim in claims:
        if not isinstance(claim, Mapping):
            continue
        if claim.get("claim_id") != "claim_revenue_lede":
            continue
        if _is_exact_public_evidence(claim.get("source_span")):
            yoy = _extract_yoy_pct(str(claim.get("text") or ""))
        break

    display_value = f"{formatted} \u00b7 {yoy}" if yoy else formatted
    item: dict[str, Any] = {
        "id": revenue_fact.get("fact_id") or "fact_revenue_gaap",
        "metric": "revenue",
        "label": "Revenue",
        "value": display_value,
        "receipt_state": sp.get("receipt_state"),
    }
    unit = revenue_fact.get("unit")
    if unit is not None:
        item["unit"] = unit
    return [item]


def _glance_guidance(workspace: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build the ``guidance[]`` list."""
    guidance = workspace.get("guidance") or []
    fiscal_period = workspace.get("fiscal_period") or {}
    fiscal_quarter = fiscal_period.get("quarter")
    next_q = (int(fiscal_quarter) % 4) + 1 if fiscal_quarter is not None else None

    items: list[dict[str, Any]] = []
    for g in guidance:
        if len(items) >= _GUIDANCE_MAX_ITEMS:
            break
        if not isinstance(g, Mapping):
            continue
        sp = g.get("source_span")
        if not _is_exact_public_evidence(sp):
            continue
        low = g.get("low")
        high = g.get("high")
        if low is None or high is None:
            continue

        horizon = g.get("horizon") or ""
        m = _HORIZON_QN_RE.search(horizon)
        horizon_qn = int(m.group(1)) if m else None

        if horizon_qn is not None and next_q is not None and horizon_qn == next_q:
            label: str = f"Q{horizon_qn} revenue growth"
        elif horizon:
            label = horizon
        else:
            label = "Guidance"

        item: dict[str, Any] = {
            "id": f"guidance:{g.get('metric') or 'guidance'}:{len(items)}",
            "metric": g.get("metric") or "guidance",
            "label": label,
            "value": _format_percent_range(float(low), float(high)),
            "receipt_state": sp.get("receipt_state"),
        }
        if horizon:
            item["horizon"] = horizon
        items.append(item)
    return items


def _glance_watch(workspace: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build the ``watch[]`` list — quoted/flagged claims only."""
    claims = workspace.get("claims") or []
    items: list[dict[str, Any]] = []

    for claim in claims:
        if len(items) >= _WATCH_MAX_ITEMS:
            break
        if not isinstance(claim, Mapping):
            continue
        claim_id = claim.get("claim_id") or ""
        metric = claim.get("metric") or ""
        text = claim.get("text") or ""
        kind = claim.get("kind") or ""

        if claim_id == "claim_revenue_lede":
            continue

        if not _is_exact_public_evidence(claim.get("source_span")):
            continue

        is_quote = kind == "quote"
        search_text = f"{claim_id} {metric} {text}"
        is_pattern = bool(_WATCH_RE.search(search_text))
        if not (is_quote or is_pattern):
            continue

        label = (
            _WATCH_LABEL_MAP.get(claim_id)
            or _WATCH_LABEL_MAP.get(metric)
        )
        if label is None:
            continue  # No closed-map entry → omit per spec.

        items.append({
            "id": claim_id,
            "metric": metric,
            "label": label,
            "value": _bound_public_text(text),
            "receipt_state": "byte_replayed",
        })
    return items


def _glance_coverage_states(workspace: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build ``coverage_states[]`` from completeness block only.

    Market reaction is NEVER borrowed from the ``public_wire`` source state.
    questions_count typed_absence → ``unstructured``; NEVER emit the numeric 14.
    """
    completeness = workspace.get("completeness") or {}
    facts = workspace.get("facts") or []

    # Consensus
    consensus_status = (completeness.get("consensus") or {}).get("status") or "unlicensed"

    # Market reaction — completeness.reaction.status only
    reaction_status = (completeness.get("reaction") or {}).get("status") or "not_joined"

    # Analyst questions — typed_absence on questions_count → unstructured
    questions_fact = next(
        (f for f in facts
         if isinstance(f, Mapping) and f.get("metric") == "questions_count"),
        None,
    )
    qa_exchanges = workspace.get("qa_exchanges") or []
    states = [
        {"id": "consensus", "label": "Consensus", "state": consensus_status},
        {"id": "reaction", "label": "Market reaction", "state": reaction_status},
    ]
    if isinstance(qa_exchanges, list) and qa_exchanges:
        states.append({
            "id": "questions_count",
            "label": "Analyst questions",
            "state": f"{len(qa_exchanges)} exchanges",
        })
    elif questions_fact is not None and isinstance(questions_fact.get("typed_absence"), Mapping):
        states.append({
            "id": "questions_count",
            "label": "Analyst questions",
            "state": "unstructured",
        })
    return states


def _glance_source_states(workspace: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build ``source_states[]`` — kind + semantic status; no URLs/hashes."""
    sources = workspace.get("sources") or []
    items: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        kind = source.get("kind") or ""
        receipt_state = source.get("receipt_state") or ""

        if receipt_state in ("byte_replayed", "address_only"):
            status = "present"
        elif kind == "edgar_collector":
            status = "not_joined"
        else:
            status = "absent"

        items.append({"kind": kind, "status": status})
        if len(items) >= _SOURCE_STATES_MAX_ITEMS:
            break
    return items


def _public_workspace_glance(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build the ``event_workspace_public_glance.v1`` projection.

    All formatting is deterministic (no LLM involvement).  The projection
    strips every receipt, URL, hash, and internal workspace field; it never
    emits beat/miss, the numeric 14 as questions_count, or score overlay data.
    """
    workspace = result.get("workspace") or {}
    fiscal_period = workspace.get("fiscal_period") or {}
    lifecycle = workspace.get("lifecycle") or {}

    # event_date: prefer source_available_at, fall back to observed_at / generated_at.
    event_date: str | None = None
    for key in ("source_available_at", "observed_at"):
        val = lifecycle.get(key)
        if val:
            event_date = str(val)[:10]
            break
    if not event_date:
        val = workspace.get("generated_at")
        if val:
            event_date = str(val)[:10]

    return {
        "schema": _GLANCE_SCHEMA,
        "available": True,
        "ticker": result.get("ticker"),
        "plane": "event_workspace.v1",
        "event_id": workspace.get("event_id"),
        "event_alias": result.get("event_alias"),
        "generation_id": workspace.get("generation_id"),
        "fiscal_period": {
            "year": fiscal_period.get("year"),
            "quarter": fiscal_period.get("quarter"),
        },
        "event_date": event_date,
        "lifecycle_state": lifecycle.get("state"),
        "authority": "context_only",
        "reported": _glance_reported(workspace),
        "guidance": _glance_guidance(workspace),
        "watch": _glance_watch(workspace),
        "coverage_states": _glance_coverage_states(workspace),
        "source_states": _glance_source_states(workspace),
    }


def _public_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a recursive, single-event public teaser projection.

    ``history``, topic rollups, completeness diagnostics, and every receipt or
    source locator are intentionally absent.  This endpoint must remain a
    teaser even if its internal reader receives a broader context object.
    """
    projected = _scalar_projection(result, tuple(
        key for key in _TEASER_SCALAR_KEYS if key not in {"company", "latest_event"}
    ))
    if "company" in result:
        projected["company"] = _company_projection(result["company"])
    if "latest_event" in result:
        projected["latest_event"] = (
            _event_projection(result["latest_event"])
            if isinstance(result["latest_event"], Mapping)
            else None
        )
    return projected


def _claimed_client_identity(request: Request) -> str:
    """Return the per-visitor identity for the tight bucket, with a local fallback.

    Resolved by app/edge_client.py, which reads only the header the edge overwrites.
    This used to read ``EO-Client-IP`` then ``CF-Connecting-IP``; both are measured to
    arrive carrying whatever a direct-to-origin caller sent, so the "claimed" key was
    free to rotate per request and the tight budget below bounded nobody. It is still
    only the tight half — ``_trusted_peer_identity`` remains the hard boundary — but a
    caller behind the edge can no longer choose it at all.
    """
    resolved = edge_client.client_ip(request.headers)
    if resolved != edge_client.UNKNOWN:
        return resolved[:128]
    return str(request.client.host if request.client else "unknown")[:128]


def _trusted_peer_identity(request: Request) -> str:
    """Return the Caddy-overwritten peer key, or a local-development fallback."""
    peer = str(request.headers.get(_TRUSTED_PEER_HEADER) or "").strip()
    if peer:
        return peer[:128]
    return str(request.client.host if request.client else "unknown")[:128]


def _book_rate_limit(key: str, *, limit: int, current: float, cutoff: float) -> bool:
    """Book one bounded rate slot. Caller must hold ``_rate_limit_lock``."""
    bucket = _rate_limit_buckets.get(key)
    if bucket is None:
        if len(_rate_limit_buckets) >= _RATE_LIMIT_MAX_KEYS:
            # Bounded global memory: discard the least-recently-used bucket.
            # This never relaxes an existing client's/peer's current limit.
            oldest = min(_rate_limit_buckets, key=lambda item: _rate_limit_buckets[item][-1])
            del _rate_limit_buckets[oldest]
        bucket = deque()
        _rate_limit_buckets[key] = bucket
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(current)
    return True


def _allow_request(request: Request, *, now: float | None = None) -> bool:
    """Consume both claimed-client and trusted-peer request slots.

    Both buckets are booked even when the first has already refused.  That is
    what prevents a spray of fabricated client headers from avoiding the peer
    backstop.
    """
    current = time.monotonic() if now is None else now
    cutoff = current - _RATE_LIMIT_WINDOW_SECONDS
    client = _claimed_client_identity(request)
    peer = _trusted_peer_identity(request)
    with _rate_limit_lock:
        ok_client = _book_rate_limit(
            f"client:{client}", limit=_RATE_LIMIT_REQUESTS, current=current, cutoff=cutoff,
        )
        ok_peer = _book_rate_limit(
            f"peer:{peer}", limit=_PEER_RATE_LIMIT_REQUESTS, current=current, cutoff=cutoff,
        )
        return ok_client and ok_peer


def _reset_rate_limit_for_tests() -> None:
    """Reset process-local limiter state for isolated API tests."""
    with _rate_limit_lock:
        _rate_limit_buckets.clear()


def _normalized_ticker_or_422(ticker: str) -> str:
    try:
        return safe_ticker(ticker)
    except ContractError as exc:
        raise HTTPException(
            status_code=422,
            detail="ticker must be a listed symbol using A-Z, 0-9, dots, or dashes",
        ) from exc


def _read_company_intelligence(params: Mapping[str, Any]) -> Mapping[str, Any]:
    """Load the network-backed reader only when this route is exercised.

    ``app.main`` mounts many independent routers and is intentionally imported
    by narrow, dependency-isolated security suites.  Importing the reader at
    module load time would make those unrelated surfaces require its HTTP
    transport dependency merely to start the app.  Production installs the
    complete app requirements; this lazy boundary keeps startup composable and
    still fails closed at the route's existing 503 boundary if the reader or
    transport cannot load.
    """
    from engine.neuralweb import company_intelligence_reader

    return company_intelligence_reader.read_company_intelligence(dict(params))


def _read_current_event_workspace(params: Mapping[str, Any]) -> Mapping[str, Any]:
    """Lazy loader for the event-workspace ticker-keyed reader."""
    from engine.neuralweb import company_intelligence_reader

    return company_intelligence_reader.read_current_event_workspace(dict(params))


@router.get("/api/company-intelligence/{ticker}")
def company_intelligence(
    ticker: str,
    request: Request,
    response: Response,
    # Retained temporarily for existing static dossiers.  It is accepted for
    # compatibility but never expands the public response or reader request.
    limit: int = Query(default=1, ge=1, le=12),
) -> dict[str, Any]:
    """Return one verified Company Intelligence event as a public teaser.

    A syntactically valid ticker missing from the immutable generation is a
    stable 404.  A source, verification, or projection failure is intentionally
    a 503: returning an empty-looking 200 would make a temporary upstream fault
    indistinguishable from an absence of earnings context.

    Successes set an explicit short public cache policy because the projection
    is non-personal and deliberately contains no corpus locator.  The global
    API middleware keeps errors ``private, no-store``.
    """
    if not _allow_request(request):
        raise HTTPException(
            status_code=429,
            detail="Too many Company Intelligence requests. Please retry shortly.",
            headers={"Retry-After": str(int(_RATE_LIMIT_WINDOW_SECONDS))},
        )
    normalized = _normalized_ticker_or_422(ticker)
    # Never request or expose more than the one latest event on this anonymous
    # route.  ``limit`` remains parsed only to avoid a hard frontend break.
    del limit
    try:
        result = _read_company_intelligence({"ticker": normalized, "limit": 1})
    except Exception:  # noqa: BLE001 - an API source boundary must fail closed
        log.exception("company intelligence reader raised for %s", normalized)
        raise HTTPException(
            status_code=503,
            detail="Company Intelligence is temporarily unavailable.",
        ) from None

    if result.get("available") is True:
        response.headers["Cache-Control"] = _PUBLIC_CACHE_CONTROL
        return _public_projection(result)

    # The reader has already normalized and verified the ticker.  Its one
    # explicit coverage absence is safe to expose as a stable not-found state;
    # every other unavailable result represents failed retrieval or validation.
    if result.get("note") == _NOT_COVERED_NOTE:
        raise HTTPException(
            status_code=404,
            detail=f"Company Intelligence is not available for {normalized}.",
        )

    log.warning("company intelligence unavailable for %s: %s", normalized, result.get("note"))
    raise HTTPException(
        status_code=503,
        detail="Company Intelligence is temporarily unavailable.",
    )


@router.get("/api/event-workspace/{ticker}")
def event_workspace_glance(
    ticker: str,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    """Return a public ``event_workspace_public_glance.v1`` for one ticker.

    Finds the most-recent ``T/YYYYQn`` alias for *ticker* in the event-workspace
    manifest and returns a stripped, deterministic projection.  All receipts,
    URLs, hashes, and raw workspace internals are omitted.

    *   **200** — glance projection; short public cache within the 300s snapshot.
    *   **404** — machine-coded coverage absence (``event_workspace_not_covered``).
    *   **422** — ticker fails the safe-ticker contract.
    *   **429** — rate-limited.
    *   **503** — ambiguous selector, verification failure, or upstream error;
        the internal note is never leaked in the response body.
    """
    if not _allow_request(request):
        raise HTTPException(
            status_code=429,
            detail="Too many Company Intelligence requests. Please retry shortly.",
            headers={"Retry-After": str(int(_RATE_LIMIT_WINDOW_SECONDS))},
        )
    normalized = _normalized_ticker_or_422(ticker)
    try:
        result = _read_current_event_workspace({"ticker": normalized})
    except Exception:  # noqa: BLE001 — API boundary must fail closed
        log.exception("event workspace reader raised for %s", normalized)
        raise HTTPException(
            status_code=503,
            detail="Verified event temporarily unavailable.",
        ) from None

    if result.get("available") is True:
        response.headers["Cache-Control"] = _WORKSPACE_GLANCE_CACHE_CONTROL
        return _public_workspace_glance(result)

    note = str(result.get("note") or "")
    if note == _NOT_COVERED_WORKSPACE_NOTE:
        return JSONResponse(
            status_code=404,
            content={
                "code": _NOT_COVERED_WORKSPACE_CODE,
                "ticker": normalized,
            },
            headers={"Cache-Control": _WORKSPACE_NOT_COVERED_CACHE_CONTROL},
        )

    # Ambiguous selector, verification failure, or snapshot error — never
    # leak the internal note or any URL/hash in the 503 body.
    log.warning("event workspace unavailable for %s: %s", normalized, note)
    raise HTTPException(
        status_code=503,
        detail="Verified event temporarily unavailable.",
    )
