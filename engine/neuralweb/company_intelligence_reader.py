"""Verified public reader for the Company Intelligence context plane.

This module deliberately reads the public R2 *marker -> immutable generation ->
company object* chain.  It never falls back to a checkout, a mutable ``latest``
object, or an inference path.  That keeps this useful for Brain grounding while
leaving it incapable of originating a signal, ranking, gate, or sizing action.
"""
from __future__ import annotations

import copy
from hashlib import sha256
import ipaddress
import json
import os
import socket
import threading
import time
import urllib.parse
from typing import Any, Mapping

import requests

from engine.company_intelligence.contracts import (
    ContractError,
    PUBLIC_METRICS,
    canonical_json_bytes,
    company_filename,
    safe_ticker,
    validate_context,
    validate_manifest,
)


_DEFAULT_BASE_URL = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence"
_CACHE_TTL_SECONDS = 300.0
_REQUEST_TIMEOUT_SECONDS = 8.0
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_CONTEXT_BYTES = 512 * 1024
_MAX_HISTORY = 12
_MAX_CONTEXT_CACHE_ENTRIES = 256


class CompanyIntelligenceReadError(RuntimeError):
    """The public source is unavailable or fails its immutable-contract checks."""


_cache_lock = threading.Lock()
_snapshot_cache: dict[str, tuple[float, dict[str, Any], dict[str, str]]] = {}
_context_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any], str]] = {}


def _origin_tuple(parsed: urllib.parse.SplitResult) -> tuple[str, str, int]:
    """Return a normalized HTTPS origin without accepting a malformed port."""
    try:
        port = parsed.port
    except ValueError as exc:
        raise CompanyIntelligenceReadError("Company Intelligence public origin has an invalid port") from exc
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise CompanyIntelligenceReadError("Company Intelligence public origin has no host")
    return parsed.scheme.lower(), host, port or 443


def _is_public_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    # ``is_global`` rejects private, loopback, link-local, unspecified,
    # multicast, reserved, and carrier-grade/shared ranges.
    return parsed.is_global


def _require_public_hostname(host: str) -> None:
    """Fail closed for literal or DNS-resolved non-public endpoints.

    The base is operator configuration, but it is still a network egress
    boundary.  Resolving it once before any request blocks an HTTPS URL aimed
    at localhost, metadata ranges, or a private split-horizon DNS record.
    """
    normalized = host.rstrip(".").lower()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".localhost"):
        raise CompanyIntelligenceReadError("Company Intelligence public origin must not use a local host")
    try:
        literal = ipaddress.ip_address(normalized)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise CompanyIntelligenceReadError("Company Intelligence public origin must not use a private host")
        return
    try:
        records = socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise CompanyIntelligenceReadError("Company Intelligence public origin host cannot be resolved") from exc
    addresses = {
        str(record[4][0])
        for record in records
        if len(record) >= 5 and isinstance(record[4], tuple) and record[4]
    }
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise CompanyIntelligenceReadError("Company Intelligence public origin must resolve only to public hosts")


def _public_base_url() -> str:
    """Resolve one operator-controlled HTTPS origin, never from tool input."""
    raw = os.environ.get("COMPANY_INTELLIGENCE_R2_BASE_URL", _DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urllib.parse.urlsplit(raw)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise CompanyIntelligenceReadError("Company Intelligence public origin is not a safe HTTPS URL")
    _scheme, host, _port = _origin_tuple(parsed)
    _require_public_hostname(host)
    return raw


def _object_url(base_url: str, relative_path: str) -> str:
    """Join a contract-owned relative path without permitting URL injection."""
    if not relative_path or relative_path.startswith("/") or ".." in relative_path.split("/"):
        raise CompanyIntelligenceReadError("unsafe public object path")
    return f"{base_url}/{urllib.parse.quote(relative_path, safe='/')}"


def _fetch_bytes(url: str, *, limit: int) -> bytes:
    """Fetch bounded bytes from R2 with a non-default user agent.

    The public R2 binding can reject Python's stock agent.  More importantly,
    the explicit bound prevents an unexpected object from becoming a chat-token
    or memory exhaustion vector.
    """
    parsed_url = urllib.parse.urlsplit(url)
    expected_origin = _origin_tuple(parsed_url)
    if expected_origin[0] != "https" or parsed_url.username or parsed_url.password:
        raise CompanyIntelligenceReadError("Company Intelligence object URL is not a safe HTTPS origin")
    try:
        response = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "MastermindCompanyIntelligence/1.0",
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
            stream=True,
            # A redirected R2 object could switch this server-side fetch to a
            # private endpoint.  Immutable objects never need a redirect.
            allow_redirects=False,
        )
        with response:
            response_url = urllib.parse.urlsplit(str(getattr(response, "url", url) or url))
            if (
                getattr(response, "is_redirect", False)
                or 300 <= int(getattr(response, "status_code", 0) or 0) < 400
                or _origin_tuple(response_url) != expected_origin
            ):
                raise CompanyIntelligenceReadError("Company Intelligence public source redirected or changed host")
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > limit:
                        raise CompanyIntelligenceReadError("public object exceeds safe size bound")
                except ValueError:
                    raise CompanyIntelligenceReadError("public object has invalid Content-Length") from None
            chunks: list[bytes] = []
            used = 0
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                used += len(chunk)
                if used > limit:
                    raise CompanyIntelligenceReadError("public object exceeds safe size bound")
                chunks.append(chunk)
            body = b"".join(chunks)
    except CompanyIntelligenceReadError:
        raise
    except requests.RequestException as exc:
        raise CompanyIntelligenceReadError("Company Intelligence public source unavailable") from exc
    if len(body) > limit:
        raise CompanyIntelligenceReadError("public object exceeds safe size bound")
    return body


def _json_object(body: bytes, *, name: str) -> dict[str, Any]:
    def reject_nonfinite(token: str) -> None:
        raise ValueError(f"non-finite JSON token: {token}")

    try:
        # Python's default decoder accepts NaN/Infinity even though they are
        # outside RFC 8259 and cannot pass our canonical immutable comparison.
        parsed = json.loads(body.decode("utf-8"), parse_constant=reject_nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CompanyIntelligenceReadError(f"{name} is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise CompanyIntelligenceReadError(f"{name} must be a JSON object")
    return parsed


def _load_snapshot(base_url: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Load and cross-check marker plus immutable generation manifest."""
    now = time.monotonic()
    with _cache_lock:
        cached = _snapshot_cache.get(base_url)
        if cached is not None and cached[0] > now:
            return copy.deepcopy(cached[1]), copy.deepcopy(cached[2])

    marker_url = _object_url(base_url, "manifest.json")
    marker_body = _fetch_bytes(marker_url, limit=_MAX_MANIFEST_BYTES)
    marker = _json_object(marker_body, name="Company Intelligence marker")
    try:
        validate_manifest(marker)
    except ContractError as exc:
        raise CompanyIntelligenceReadError("Company Intelligence marker failed contract validation") from exc

    generation_id = str(marker["generation_id"])
    immutable_url = _object_url(base_url, f"generations/{generation_id}/manifest.json")
    immutable_body = _fetch_bytes(immutable_url, limit=_MAX_MANIFEST_BYTES)
    immutable = _json_object(immutable_body, name="Company Intelligence immutable manifest")
    try:
        validate_manifest(immutable)
    except ContractError as exc:
        raise CompanyIntelligenceReadError("Company Intelligence immutable manifest failed contract validation") from exc
    try:
        equivalent = canonical_json_bytes(marker) == canonical_json_bytes(immutable)
    except ContractError as exc:
        raise CompanyIntelligenceReadError("Company Intelligence marker canonical comparison failed") from exc
    if not equivalent:
        raise CompanyIntelligenceReadError("Company Intelligence marker does not match immutable generation")

    receipt = {
        "marker_url": marker_url,
        "immutable_manifest_url": immutable_url,
        "marker_sha256": sha256(marker_body).hexdigest(),
        "generation_id": generation_id,
    }
    with _cache_lock:
        _snapshot_cache[base_url] = (now + _CACHE_TTL_SECONDS, copy.deepcopy(marker), copy.deepcopy(receipt))
    return copy.deepcopy(marker), copy.deepcopy(receipt)


def _load_context(base_url: str, ticker: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve and hash-verify one generation-addressed company context object."""
    manifest, receipt = _load_snapshot(base_url)
    generation_id = str(manifest["generation_id"])
    key = (base_url, generation_id, ticker)
    now = time.monotonic()
    with _cache_lock:
        cached = _context_cache.get(key)
        if cached is not None and cached[0] > now:
            return copy.deepcopy(cached[1]), {**copy.deepcopy(receipt), "company_url": cached[2]}

    relative = company_filename(ticker)
    expected = (manifest.get("files") or {}).get(relative)
    if not isinstance(expected, Mapping):
        raise CompanyIntelligenceReadError("Company Intelligence does not cover this ticker")
    expected_hash = expected.get("sha256")
    expected_bytes = expected.get("bytes")
    if not isinstance(expected_hash, str) or not isinstance(expected_bytes, int) or expected_bytes <= 0:
        raise CompanyIntelligenceReadError("Company Intelligence manifest has an invalid company receipt")
    if expected_bytes > _MAX_CONTEXT_BYTES:
        raise CompanyIntelligenceReadError("Company Intelligence context exceeds safe size bound")

    company_url = _object_url(base_url, f"generations/{generation_id}/{relative}")
    body = _fetch_bytes(company_url, limit=_MAX_CONTEXT_BYTES)
    if len(body) != expected_bytes or sha256(body).hexdigest() != expected_hash:
        raise CompanyIntelligenceReadError("Company Intelligence context failed immutable receipt verification")
    context = _json_object(body, name="Company Intelligence context")
    try:
        validate_context(context)
    except ContractError as exc:
        raise CompanyIntelligenceReadError("Company Intelligence context failed contract validation") from exc
    if context.get("generation_id") != generation_id or context.get("company", {}).get("ticker") != ticker:
        raise CompanyIntelligenceReadError("Company Intelligence context identity mismatch")

    with _cache_lock:
        # Expired generation/ticker objects must not accumulate forever in a
        # long-lived Brain process.  Keep the newest bounded working set; every
        # miss is still revalidated through the immutable manifest receipt.
        expired = [cache_key for cache_key, cached in _context_cache.items() if cached[0] <= now]
        for cache_key in expired:
            _context_cache.pop(cache_key, None)
        while len(_context_cache) >= _MAX_CONTEXT_CACHE_ENTRIES:
            oldest = min(_context_cache, key=lambda cache_key: _context_cache[cache_key][0])
            _context_cache.pop(oldest, None)
        _context_cache[key] = (now + _CACHE_TTL_SECONDS, copy.deepcopy(context), company_url)
    return copy.deepcopy(context), {**copy.deepcopy(receipt), "company_url": company_url, "company_sha256": expected_hash}


def _bounded_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:limit] if text else None


def _metric_projection(values: object) -> dict[str, int | float | None]:
    """Return only the fixed public metric vocabulary after contract validation."""
    raw = values if isinstance(values, Mapping) else {}
    return {name: raw.get(name) for name in sorted(PUBLIC_METRICS)}


def _source_projection(source: object) -> dict[str, Any]:
    """Do not hand source receipts or future source fields to the model.

    ``record_id`` is useful in the stored provenance object but it is an
    upstream free-form identifier, not needed for a Brain answer.  Keeping it
    out of the model-facing projection is intentional boundary reduction.
    """
    raw = source if isinstance(source, Mapping) else {}
    receipt = raw.get("receipt") if isinstance(raw.get("receipt"), Mapping) else {}
    projected: dict[str, Any] = {
        "source_ref": raw.get("source_ref"),
        "kind": raw.get("kind"),
        "status": raw.get("status"),
        "citation_precision": raw.get("citation_precision"),
        "url": raw.get("url"),
    }
    compact_receipt = {
        key: receipt[key]
        for key in ("source_hash", "source_date")
        if key in receipt
    }
    if compact_receipt:
        projected["receipt"] = compact_receipt
    return projected


def _topics_projection(topics: object) -> dict[str, Any]:
    raw = topics if isinstance(topics, Mapping) else {}
    timeline = raw.get("timeline") if isinstance(raw.get("timeline"), list) else []
    return {
        "timeline": [
            {
                "tag": item.get("tag"),
                "first_event_id": item.get("first_event_id"),
                "last_event_id": item.get("last_event_id"),
                "event_count": item.get("event_count"),
                "status": item.get("status"),
            }
            for item in timeline[:48]
            if isinstance(item, Mapping)
        ],
        "added": list(raw.get("added") or [])[:24],
        "dropped": list(raw.get("dropped") or [])[:24],
        "persistent": list(raw.get("persistent") or [])[:24],
    }


def _source_completeness_projection(completeness: object) -> dict[str, Any]:
    raw = completeness if isinstance(completeness, Mapping) else {}
    return {
        name: {
            "status": block.get("status"),
            "event_count": block.get("event_count"),
        }
        for name in ("earnings_history", "score_overlay", "transcripts")
        if isinstance((block := raw.get(name)), Mapping)
    }


def _event_projection(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return the fixed, model-facing event shape; never forward raw maps."""
    raw_lineage = event.get("field_lineage")
    lineage = raw_lineage if isinstance(raw_lineage, Mapping) else {}
    metric_lineage = lineage.get("metrics") if isinstance(lineage.get("metrics"), Mapping) else {}
    tag_lineage = lineage.get("tags") if isinstance(lineage.get("tags"), Mapping) else {}
    return {
        "event_id": event.get("event_id"),
        "fiscal_year": event.get("fiscal_year"),
        "fiscal_quarter": event.get("fiscal_quarter"),
        "call_date": event.get("call_date"),
        "summary": _bounded_text(event.get("summary"), limit=1600),
        "positive_highlights": [
            text for item in (event.get("positive_highlights") or [])[:3]
            if (text := _bounded_text(item, limit=500))
        ],
        "negative_highlights": [
            text for item in (event.get("negative_highlights") or [])[:3]
            if (text := _bounded_text(item, limit=500))
        ],
        "key_quote": _bounded_text(event.get("key_quote"), limit=800),
        "tags": list(event.get("tags") or [])[:24],
        "metrics": _metric_projection(event.get("metrics")),
        "field_lineage": {
            "summary": lineage.get("summary"),
            "key_quote": lineage.get("key_quote"),
            "metrics": {name: metric_lineage.get(name) for name in sorted(PUBLIC_METRICS)},
            "positive_highlights": list(lineage.get("positive_highlights") or [])[:3],
            "negative_highlights": list(lineage.get("negative_highlights") or [])[:3],
            "highlights": list(lineage.get("highlights") or [])[:6],
            "tags": {tag: tag_lineage.get(tag) for tag in list(event.get("tags") or [])[:24]},
        },
        "previous_event_deltas": _metric_projection(event.get("previous_event_deltas")),
        "sources": [_source_projection(source) for source in list(event.get("sources") or [])[:3]],
        # This is an important honesty rail: documents may be present, but no
        # summary/highlight is misrepresented as a line-level source citation.
        "claim_citations_pending": event.get("claim_citations_pending") is True,
    }


def read_company_intelligence(params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return verified per-ticker earnings/event context and nothing actionable.

    Supported input is intentionally tiny: ``ticker`` is required; ``limit``
    may narrow the newest-first history to 1..12; ``event_id`` may select one
    disclosed immutable event.  No source URL, generation id, score threshold,
    or query expression comes from the model.
    """
    raw = dict(params) if isinstance(params, Mapping) else {}
    try:
        ticker = safe_ticker(raw.get("ticker"))
    except ContractError:
        return {
            "available": False,
            "is_context_only": True,
            "display_only": True,
            "note": "A valid ticker is required for Company Intelligence context.",
        }
    try:
        limit = int(raw.get("limit", 4))
    except (TypeError, ValueError):
        limit = 4
    limit = max(1, min(_MAX_HISTORY, limit))
    event_id = str(raw.get("event_id") or "").strip()
    if len(event_id) > 64:
        event_id = ""

    try:
        context, receipt = _load_context(_public_base_url(), ticker)
    except CompanyIntelligenceReadError as exc:
        return {
            "available": False,
            "ticker": ticker,
            "is_context_only": True,
            "display_only": True,
            "note": str(exc),
        }

    history = list(context.get("history") or [])
    if event_id:
        history = [event for event in history if isinstance(event, Mapping) and event.get("event_id") == event_id]
    projected = [_event_projection(event) for event in history[:limit] if isinstance(event, Mapping)]
    latest = projected[0] if projected else None
    return {
        "available": True,
        "ticker": ticker,
        "company": {
            "ticker": context["company"].get("ticker"),
            "display_name": _bounded_text(context["company"].get("display_name"), limit=240),
            "exchange": None,
        },
        "schema": context.get("schema"),
        "generation_id": context.get("generation_id"),
        "generated_at": context.get("generated_at"),
        "status": context.get("status"),
        "is_context_only": True,
        "display_only": True,
        "authority": "context_only",
        "untrusted_source_data": True,
        "latest_event": latest,
        "history": projected,
        "topics": _topics_projection(context.get("topics")),
        "source_completeness": _source_completeness_projection(context.get("source_completeness")),
        "warnings": list(context.get("warnings") or [])[:12],
        "missing_sources": list(context.get("missing_sources") or [])[:12],
        "receipt": receipt,
        "note": (
            "Verified company event context only. It may explain dated earnings, transcript, "
            "and topic history; it cannot create a signal, rank, size, gate, or escalation. "
            "Document presence is not a line-level citation."
        ),
    }


def clear_company_intelligence_cache() -> None:
    """Test/operator seam; never required by a normal tool call."""
    with _cache_lock:
        _snapshot_cache.clear()
        _context_cache.clear()
