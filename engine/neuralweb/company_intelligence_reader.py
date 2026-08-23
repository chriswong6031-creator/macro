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
# Duplicate constant removed — _DEFAULT_BASE_URL was defined twice in the original.


_DEFAULT_BASE_URL = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence"
_CACHE_TTL_SECONDS = 300.0
_REQUEST_TIMEOUT_SECONDS = 8.0
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_CONTEXT_BYTES = 512 * 1024
_MAX_WORKSPACE_BYTES = 512 * 1024
_MAX_HISTORY = 12
_MAX_CONTEXT_CACHE_ENTRIES = 256
# Keep this string identical to engine.company_intelligence.event_workspace.NEST.
# The binder is imported only inside the workspace reader so Brain/API load
# time does not pull Exhibit 99.1 parsing into the restart closure.
_EVENT_WORKSPACE_NEST = "event_workspaces"


_DEFAULT_BASE_URL = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence"
_CACHE_TTL_SECONDS = 300.0
_REQUEST_TIMEOUT_SECONDS = 8.0
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_CONTEXT_BYTES = 512 * 1024
_MAX_WORKSPACE_BYTES = 512 * 1024
_MAX_HISTORY = 12
_MAX_CONTEXT_CACHE_ENTRIES = 256


class CompanyIntelligenceReadError(RuntimeError):
    """The public source is unavailable or fails its immutable-contract checks."""


_cache_lock = threading.Lock()
_snapshot_cache: dict[str, tuple[float, dict[str, Any], dict[str, str]]] = {}
_context_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any], str]] = {}
_workspace_snapshot_cache: dict[str, tuple[float, dict[str, Any], dict[str, str]]] = {}
_workspace_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any], str]] = {}


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


def _public_base_url(override: str | None = None, *, require_public_host: bool = True) -> str:
    """Resolve one operator-controlled HTTPS origin — MAJOR-7: the ONE base-
    URL resolver for both the model-facing reads above and the producer-
    facing workspace-chain primitives below (never a second implementation).

    *override* lets a producer caller (or a test) pin an explicit origin;
    model-facing callers never pass it, always resolving from
    ``COMPANY_INTELLIGENCE_R2_BASE_URL``/the hardcoded default.

    *require_public_host* gates the live DNS/public-IP-only check
    (:func:`_require_public_hostname`) — always True for the model-facing
    path (its base can, in principle, come from operator env config read at
    request time, so the SSRF-style guard stays load-bearing there).
    Producer/nightly-builder callers (refresh/discovery/chain-walk — trusted
    admin-side code, never model/tool input) pass ``require_public_host=
    False``: their *override* is frequently a test-only, non-resolving
    domain (``example.test``, RFC 2606), and the producer path already runs
    inside a controlled CI/nightly context rather than serving live model
    requests. HTTPS-scheme validation, no query/fragment/credentials, and
    (inside ``_fetch_bytes``) redirect refusal + origin-pinning + a size
    bound apply UNCONDITIONALLY either way — only the live-DNS check is
    parameterized.
    """
    raw = (override or os.environ.get("COMPANY_INTELLIGENCE_R2_BASE_URL", _DEFAULT_BASE_URL)).strip().rstrip("/")
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
    if require_public_host:
        _require_public_hostname(host)
    return raw


def _object_url(base_url: str, relative_path: str) -> str:
    """Join a contract-owned relative path without permitting URL injection."""
    if not relative_path or relative_path.startswith("/") or ".." in relative_path.split("/"):
        raise CompanyIntelligenceReadError("unsafe public object path")
    return f"{base_url}/{urllib.parse.quote(relative_path, safe='/')}"


def _fetch_bytes(url: str, *, limit: int, allow_404: bool = False) -> bytes | None:
    """Fetch bounded bytes from R2 with a non-default user agent.

    The public R2 binding can reject Python's stock agent.  More importantly,
    the explicit bound prevents an unexpected object from becoming a chat-token
    or memory exhaustion vector.

    *allow_404*: when True, a clean HTTP 404 returns ``None`` instead of
    raising — MAJOR-7's unified fetch helper, used by the producer-facing
    workspace-chain primitives (which must distinguish "genuinely not
    published" from every other failure — the model-facing callers above
    never pass this and keep raising on 404 exactly as before).
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
            if allow_404 and int(getattr(response, "status_code", 0) or 0) == 404:
                return None
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
    # NIT-21: this model-facing call never passes allow_404, so _fetch_bytes
    # never returns None here — a 404 raises. Assert rather than silently
    # trust the union type, so the None branch is honestly unreachable.
    assert marker_body is not None
    marker = _json_object(marker_body, name="Company Intelligence marker")
    try:
        validate_manifest(marker)
    except ContractError as exc:
        raise CompanyIntelligenceReadError("Company Intelligence marker failed contract validation") from exc

    generation_id = str(marker["generation_id"])
    immutable_url = _object_url(base_url, f"generations/{generation_id}/manifest.json")
    immutable_body = _fetch_bytes(immutable_url, limit=_MAX_MANIFEST_BYTES)
    assert immutable_body is not None  # NIT-21: allow_404 never passed here
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
    assert body is not None  # NIT-21: allow_404 never passed here
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


def _workspace_contracts():
    """Import the workspace contract only when a workspace is actually read.

    ``company_intelligence_reader`` is on the macro-api load path.  Schema and
    publication live in ``event_workspace``; Exhibit 99.1 binding lives in
    ``event_workspace_build`` so exclusive CI jobs and the API import-closure
    do not inherit ``engine.earnings_release``.
    """
    from engine.company_intelligence import event_workspace as mod
    return mod


def _load_workspace_snapshot(base_url: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Load marker + immutable generation for the event_workspaces nest."""
    ws = _workspace_contracts()
    now = time.monotonic()
    cache_key = f"{base_url}/{_EVENT_WORKSPACE_NEST}"
    with _cache_lock:
        cached = _workspace_snapshot_cache.get(cache_key)
        if cached is not None and cached[0] > now:
            return copy.deepcopy(cached[1]), copy.deepcopy(cached[2])

    marker_url = _object_url(base_url, f"{_EVENT_WORKSPACE_NEST}/manifest.json")
    marker_body = _fetch_bytes(marker_url, limit=_MAX_MANIFEST_BYTES)
    assert marker_body is not None  # NIT-21: allow_404 never passed here
    marker = _json_object(marker_body, name="event workspace marker")
    try:
        ws.validate_workspace_manifest(marker)
    except ContractError as exc:
        raise CompanyIntelligenceReadError("event workspace marker failed contract validation") from exc

    generation_id = str(marker["generation_id"])
    immutable_url = _object_url(
        base_url, f"{_EVENT_WORKSPACE_NEST}/generations/{generation_id}/manifest.json"
    )
    immutable_body = _fetch_bytes(immutable_url, limit=_MAX_MANIFEST_BYTES)
    assert immutable_body is not None  # NIT-21: allow_404 never passed here
    immutable = _json_object(immutable_body, name="event workspace immutable manifest")
    try:
        ws.validate_workspace_manifest(immutable)
    except ContractError as exc:
        raise CompanyIntelligenceReadError(
            "event workspace immutable manifest failed contract validation"
        ) from exc
    try:
        equivalent = canonical_json_bytes(marker) == canonical_json_bytes(immutable)
    except ContractError as exc:
        raise CompanyIntelligenceReadError("event workspace marker canonical comparison failed") from exc
    if not equivalent:
        raise CompanyIntelligenceReadError("event workspace marker does not match immutable generation")

    receipt = {
        "marker_url": marker_url,
        "immutable_manifest_url": immutable_url,
        "marker_sha256": sha256(marker_body).hexdigest(),
        "generation_id": generation_id,
    }
    with _cache_lock:
        _workspace_snapshot_cache[cache_key] = (
            now + _CACHE_TTL_SECONDS, copy.deepcopy(marker), copy.deepcopy(receipt)
        )
    return copy.deepcopy(marker), copy.deepcopy(receipt)


def _load_event_workspace(base_url: str, event_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve and hash-verify one generation-addressed event workspace."""
    ws = _workspace_contracts()
    manifest, receipt = _load_workspace_snapshot(base_url)
    try:
        canonical_id = ws.resolve_workspace_event_id(event_id, manifest.get("aliases") or {})
    except ContractError as exc:
        raise CompanyIntelligenceReadError("event workspace alias could not be resolved") from exc
    generation_id = str(manifest["generation_id"])
    key = (base_url, generation_id, canonical_id)
    now = time.monotonic()
    with _cache_lock:
        cached = _workspace_cache.get(key)
        if cached is not None and cached[0] > now:
            return copy.deepcopy(cached[1]), {**copy.deepcopy(receipt), "workspace_url": cached[2]}

    relative = f"workspaces/{canonical_id}.json"
    expected = (manifest.get("files") or {}).get(relative)
    if not isinstance(expected, Mapping):
        raise CompanyIntelligenceReadError("event workspace does not cover this event")
    expected_hash = expected.get("sha256")
    expected_bytes = expected.get("bytes")
    if not isinstance(expected_hash, str) or not isinstance(expected_bytes, int) or expected_bytes <= 0:
        raise CompanyIntelligenceReadError("event workspace manifest has an invalid receipt")
    if expected_bytes > _MAX_WORKSPACE_BYTES:
        raise CompanyIntelligenceReadError("event workspace exceeds safe size bound")

    workspace_url = _object_url(
        base_url, f"{_EVENT_WORKSPACE_NEST}/generations/{generation_id}/{relative}"
    )
    body = _fetch_bytes(workspace_url, limit=_MAX_WORKSPACE_BYTES)
    assert body is not None  # NIT-21: allow_404 never passed here
    if len(body) != expected_bytes or sha256(body).hexdigest() != expected_hash:
        raise CompanyIntelligenceReadError("event workspace failed immutable receipt verification")
    workspace = _json_object(body, name="event workspace")
    try:
        ws.validate_event_workspace(workspace)
    except ContractError as exc:
        raise CompanyIntelligenceReadError("event workspace failed contract validation") from exc
    if workspace.get("generation_id") != generation_id or workspace.get("event_id") != canonical_id:
        raise CompanyIntelligenceReadError("event workspace identity mismatch")

    with _cache_lock:
        expired = [cache_key for cache_key, cached in _workspace_cache.items() if cached[0] <= now]
        for cache_key in expired:
            _workspace_cache.pop(cache_key, None)
        while len(_workspace_cache) >= _MAX_CONTEXT_CACHE_ENTRIES:
            oldest = min(_workspace_cache, key=lambda cache_key: _workspace_cache[cache_key][0])
            _workspace_cache.pop(oldest, None)
        _workspace_cache[key] = (now + _CACHE_TTL_SECONDS, copy.deepcopy(workspace), workspace_url)
    return copy.deepcopy(workspace), {
        **copy.deepcopy(receipt),
        "workspace_url": workspace_url,
        "workspace_sha256": expected_hash,
    }


def read_event_workspace(params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the full ``event_workspace.v1`` for one canonical event or alias.

    This is the real E1 consumer.  It follows marker → immutable generation →
    hash-verified workspace object on the ``event_workspaces/`` nest.  It does
    not read or widen the closed v1 teaser.
    """
    raw = dict(params) if isinstance(params, Mapping) else {}
    event_id = str(raw.get("event_id") or "").strip()
    if not event_id or len(event_id) > 128:
        return {
            "available": False,
            "is_context_only": True,
            "display_only": True,
            "authority": "context_only",
            "note": "A canonical event id or published alias is required.",
        }
    try:
        workspace, receipt = _load_event_workspace(_public_base_url(), event_id)
    except CompanyIntelligenceReadError as exc:
        return {
            "available": False,
            "event_id": event_id,
            "is_context_only": True,
            "display_only": True,
            "authority": "context_only",
            "note": str(exc),
        }
    return {
        "available": True,
        "event_id": workspace.get("event_id"),
        "workspace": workspace,
        "is_context_only": True,
        "display_only": True,
        "authority": "context_only",
        "untrusted_source_data": True,
        "receipt": receipt,
        "note": (
            "Verified event workspace context only. It cannot create a signal, "
            "rank, size, gate, or escalation."
        ),
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


_NOT_COVERED_NOTE = "Event workspace does not cover this ticker"


def _verify_selected_workspace(
    *,
    ticker: str,
    selected: Any,
    workspace: Mapping[str, Any],
) -> None:
    """Cross-check ticker/period/alias after the workspace object is loaded.

    A mismatch is a verification failure, never coverage-absence. The HTTP
    layer maps these notes to 503, not 404.
    """
    issuer = workspace.get("issuer") if isinstance(workspace.get("issuer"), Mapping) else {}
    listings = issuer.get("listings") or []
    listed = {
        str(item.get("ticker") or "").strip().upper()
        for item in listings
        if isinstance(item, Mapping)
    }
    if ticker not in listed:
        raise CompanyIntelligenceReadError(
            "event workspace issuer listings do not include the requested ticker"
        )

    fiscal = workspace.get("fiscal_period") if isinstance(workspace.get("fiscal_period"), Mapping) else {}
    try:
        year = int(fiscal.get("year"))
        quarter = int(fiscal.get("quarter"))
    except (TypeError, ValueError) as exc:
        raise CompanyIntelligenceReadError(
            "event workspace fiscal period does not match the selected alias period"
        ) from exc
    if year != selected.year or quarter != selected.quarter:
        raise CompanyIntelligenceReadError(
            "event workspace fiscal period does not match the selected alias period"
        )

    owned = {str(item) for item in (workspace.get("aliases") or [])}
    owned.add(str(workspace.get("event_id") or ""))
    if selected.alias not in owned:
        raise CompanyIntelligenceReadError(
            "selected alias does not belong to the loaded workspace"
        )
    if workspace.get("event_id") != selected.event_id:
        raise CompanyIntelligenceReadError("event workspace identity mismatch")


def read_current_event_workspace(params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the current ``event_workspace.v1`` for *ticker* selected by alias.

    Reads the ``event_workspaces/`` manifest, finds the T/YYYYQn alias for the
    requested ticker via ``select_current_event_from_aliases``, then fetches and
    hash-verifies the workspace object.  It does NOT read or consult the closed
    v1 ``company_intelligence_context.v1`` at any point.

    Return envelope
    ---------------
    Success: ``available True`` with ``workspace``, ``event_alias`` (the T/YYYYQn
    key), ``is_context_only True``, ``display_only True``, ``authority
    context_only``, ``untrusted_source_data True``, and a ``receipt``.

    Coverage absence: ``available False``, ``ticker`` set, ``note`` exactly
    ``"Event workspace does not cover this ticker"``.

    All other failures: ``available False``, ``ticker`` set, ``note`` is the
    internal error string.  The HTTP layer maps these to 503.
    """
    raw = dict(params) if isinstance(params, Mapping) else {}
    ws = _workspace_contracts()

    # Validate ticker; return available False (no ticker set) on invalid input.
    try:
        ticker = safe_ticker(raw.get("ticker"))
    except ContractError:
        return {
            "available": False,
            "is_context_only": True,
            "display_only": True,
            "authority": "context_only",
            "note": "A valid ticker is required for Event Workspace context.",
        }

    # Load the workspace manifest snapshot.
    try:
        base_url = _public_base_url()
        manifest, receipt = _load_workspace_snapshot(base_url)
    except CompanyIntelligenceReadError as exc:
        return {
            "available": False,
            "ticker": ticker,
            "is_context_only": True,
            "display_only": True,
            "authority": "context_only",
            "note": str(exc),
        }

    # Select the most-recent T/YYYYQn alias for this ticker.
    try:
        selected = ws.select_current_event_from_aliases(
            ticker, manifest.get("aliases") or {}
        )
    except ws.WorkspaceError as exc:
        note_text = str(exc)
        if "does not cover" in note_text:
            return {
                "available": False,
                "ticker": ticker,
                "is_context_only": True,
                "display_only": True,
                "authority": "context_only",
                "note": _NOT_COVERED_NOTE,
            }
        return {
            "available": False,
            "ticker": ticker,
            "is_context_only": True,
            "display_only": True,
            "authority": "context_only",
            "note": note_text,
        }

    # Fetch and hash-verify the selected workspace object.
    try:
        workspace, workspace_receipt = _load_event_workspace(base_url, selected.event_id)
        _verify_selected_workspace(ticker=ticker, selected=selected, workspace=workspace)
    except CompanyIntelligenceReadError as exc:
        return {
            "available": False,
            "ticker": ticker,
            "is_context_only": True,
            "display_only": True,
            "authority": "context_only",
            "note": str(exc),
        }

    merged_receipt = {**receipt, **workspace_receipt}
    return {
        "available": True,
        "ticker": ticker,
        "event_id": workspace.get("event_id"),
        "event_alias": selected.alias,
        "workspace": workspace,
        "is_context_only": True,
        "display_only": True,
        "authority": "context_only",
        "untrusted_source_data": True,
        "receipt": merged_receipt,
        "note": (
            "Verified event workspace context only. It cannot create a signal, "
            "rank, size, gate, or escalation."
        ),
    }


def clear_company_intelligence_cache() -> None:
    """Test/operator seam; never required by a normal tool call."""
    with _cache_lock:
        _snapshot_cache.clear()
        _context_cache.clear()
        _workspace_snapshot_cache.clear()
        _workspace_cache.clear()


# ---------------------------------------------------------------------------
# IMCE A5C (frozen spec D) — ONE shared disposition-aware canonical history
# reader.  Before this PR, three independent implementations fetched the
# event_workspaces nest over HTTP: scripts.refresh_event_workspaces.
# load_prior_workspace / load_prior_workspace_for_ticker, and
# scripts.build_cycle_pattern_imce_prospective._raw_fetch_workspace (whose
# OWN docstring named itself a duplicate, authorized only as a stopgap).
# Every one of those functions now delegates to the primitives below.
#
# MAJOR-7 (red-team, corrects an earlier draft's false claim): these
# primitives are NOT a second GET-sequence implementation — they reuse the
# SAME ``_object_url`` (safe path join) / ``_fetch_bytes`` (HTTPS-scheme
# check, redirect refusal, origin pinning, size bound) / ``_json_object``
# machinery the model-facing Brain surface above uses, via ``_fetch_bytes``'s
# new ``allow_404`` parameter and ``_public_base_url``'s new
# ``require_public_host`` parameter (see each docstring). There is ONE URL
# builder, ONE nest-prefix constant pattern, and ONE fetch helper in this
# module, full stop.
# ---------------------------------------------------------------------------


class WorkspaceChainNotPublished(Exception):
    """A clean 404 (top-level marker, a generation's own manifest, or one
    workspace object) — the thing asked for genuinely has no publication
    yet. Distinct from any OTHER fetch failure (network error, timeout,
    non-2xx, malformed JSON) — a caller must never conflate the two; see
    each wrapper's own docstring for the erasure risk of doing so."""


class WorkspaceChainIntegrityError(RuntimeError):
    """A predecessor link in the manifest chain is broken: it names a
    generation that does not exist, or that generation's own immutable
    manifest bytes do not hash to the ``previous_manifest_sha256`` receipt
    the CHILD generation recorded. This is a HARD, typed failure — frozen
    spec D2(c) requires it never be silently swallowed into a shorter
    history or an empty revision list."""


_WORKSPACE_NEST_PREFIX = "event_workspaces"
# D2(c): a documented, finite, CONFIGURABLE (via the max_hops parameter)
# bound on how many predecessor hops a chain walk will follow before
# refusing — prevents an unbounded walk against a malicious or corrupted
# chain. MAJOR-8(b): with the semantic-no-op discipline (A4) the chain only
# grows on a genuine CONTENT change, so real depth is on the order of tens
# of generations by the first natural multi-quarter event, not hundreds;
# 500 is generous headroom, not a sizing estimate. Chain compaction/
# archival of very old generations is explicitly future work, not attempted
# here.
DEFAULT_MAX_CHAIN_HOPS = 500


def _workspace_object_url(base_url: str, relative_path: str) -> str:
    """Join a ``event_workspaces/``-relative path onto *base_url* through
    the SAME safe joiner the model-facing path uses."""
    return _object_url(base_url, f"{_WORKSPACE_NEST_PREFIX}/{relative_path}")


def fetch_current_workspace_marker_raw(
    *, base_url: str | None = None,
) -> tuple[bytes, dict[str, Any]] | None:
    """(raw_bytes, parsed_dict) for the top-level ``event_workspaces/
    manifest.json`` marker, or ``None`` on a clean 404 (no nest has ever
    been published). Raises on any other failure.

    MINOR-18: callers that must hash EXACTLY what was fetched (e.g. a
    producer computing a chain link's ``previous_manifest_sha256``) need
    the RAW bytes — re-serializing the parsed dict via
    ``canonical_json_bytes`` is not equivalent in general (see
    :func:`read_event_source_revisions`'s own MINOR-10 fix, which applies
    the identical discipline to predecessor-generation manifests)."""
    resolved = _public_base_url(base_url, require_public_host=False)
    url = _workspace_object_url(resolved, "manifest.json")
    body = _fetch_bytes(url, limit=_MAX_MANIFEST_BYTES, allow_404=True)
    if body is None:
        return None
    marker = _json_object(body, name="event workspace marker")
    return body, marker


def fetch_current_workspace_marker(*, base_url: str | None = None) -> dict[str, Any] | None:
    """The top-level ``event_workspaces/manifest.json`` marker, or ``None``
    on a clean 404 (no nest has ever been published). Raises on any other
    failure (network error, timeout, non-2xx, malformed JSON, non-object
    body, unsafe origin) — a genuine fetch failure must never be read as
    "no nest yet"."""
    result = fetch_current_workspace_marker_raw(base_url=base_url)
    return result[1] if result is not None else None


def fetch_generation_manifest(generation_id: str, *, base_url: str | None = None) -> dict[str, Any]:
    """One generation's own immutable ``manifest.json``.

    Raises ``WorkspaceChainNotPublished`` on a clean 404. Raises any other
    exception (network error, timeout, non-2xx, malformed JSON, non-object
    body, unsafe origin) on a genuine fetch failure."""
    return _fetch_generation_manifest_raw(generation_id, base_url=base_url)[1]


def _fetch_generation_manifest_raw(
    generation_id: str, *, base_url: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """(raw_bytes, parsed_dict) for one generation's own manifest — MAJOR-8(a):
    the RAW bytes are returned alongside the parsed object so a predecessor-
    link verification (MINOR-10: hash the bytes actually fetched, never a
    re-serialization) can reuse this SAME fetch as the next hop's own
    "current" manifest, instead of a second GET for the same object."""
    resolved = _public_base_url(base_url, require_public_host=False)
    url = _workspace_object_url(resolved, f"generations/{generation_id}/manifest.json")
    body = _fetch_bytes(url, limit=_MAX_MANIFEST_BYTES, allow_404=True)
    if body is None:
        raise WorkspaceChainNotPublished(f"generation {generation_id} manifest 404")
    manifest = _json_object(body, name=f"generation {generation_id} manifest")
    return body, manifest


def fetch_raw_workspace(event_id: str, generation_id: str, *, base_url: str | None = None) -> dict[str, Any]:
    """One workspace object, addressed by its OWN generation (no manifest
    receipt cross-check here — callers that need hash verification against
    a generation manifest's own ``files`` receipt do that themselves, e.g.
    :func:`_load_event_workspace` above for the model-facing path).

    Raises ``WorkspaceChainNotPublished`` on a clean 404. Raises any other
    exception on a genuine fetch failure."""
    resolved = _public_base_url(base_url, require_public_host=False)
    url = _workspace_object_url(resolved, f"generations/{generation_id}/workspaces/{event_id}.json")
    body = _fetch_bytes(url, limit=_MAX_WORKSPACE_BYTES, allow_404=True)
    if body is None:
        raise WorkspaceChainNotPublished(f"{event_id}: workspace 404 in generation {generation_id}")
    payload = _json_object(body, name=f"{event_id} workspace")
    return payload


def load_current_workspace(event_id: str, *, base_url: str | None = None) -> dict[str, Any]:
    """The event's workspace body in the CURRENTLY PUBLISHED (marker) generation.

    Raises ``WorkspaceChainNotPublished`` when the top-level marker is a
    clean 404, carries no ``generation_id``, or the event is absent from
    that generation. Raises any other exception on a genuine fetch failure.
    """
    marker = fetch_current_workspace_marker(base_url=base_url)
    if marker is None:
        raise WorkspaceChainNotPublished(f"{event_id}: manifest 404")
    generation_id = str(marker.get("generation_id") or "")
    if not generation_id:
        raise WorkspaceChainNotPublished(f"{event_id}: manifest carries no generation_id")
    return fetch_raw_workspace(event_id, generation_id, base_url=base_url)


def load_workspace_with_disposition(
    event_id: str, *, base_url: str | None = None,
    fetch: Any = None,
) -> tuple[dict[str, Any] | None, str]:
    """(workspace_or_None, disposition) in {"found", "not_published", "fetch_failed"}.

    The three-way disposition D2(a) requires: a genuine network/timeout/
    non-2xx/malformed-JSON failure must be distinguishable from "this event
    has no publication yet" — collapsing the two would let a transient CDN
    blip be minted as "the issuer had no event". *fetch* is injectable for
    tests (a stub raising ``WorkspaceChainNotPublished`` for a clean 404,
    any other exception for a network failure, or returning a dict for a
    hit); production callers never pass it, always exercising
    :func:`load_current_workspace`.
    """
    fetcher = fetch or (lambda eid: load_current_workspace(eid, base_url=base_url))
    try:
        return fetcher(event_id), "found"
    except WorkspaceChainNotPublished:
        return None, "not_published"
    except Exception:  # noqa: BLE001 — every other failure is fetch_failed, never silently absent
        return None, "fetch_failed"


def find_current_event_id_for_company(
    company_id: str, *, base_url: str | None = None,
) -> str | None:
    """The event_id of *company_id*'s most-recently-published event in the
    CURRENT generation, scanning ONLY the generation manifest's own
    ``files`` map (event_ids, no workspace bodies fetched) — a static,
    acquisition-independent lookup.

    Returns ``None`` ONLY for: (i) the top-level marker is a clean 404 (no
    nest ever published); (ii) the current generation's manifest is
    well-formed and simply carries no entry for *company_id*. EVERY other
    outcome is an ANOMALY and raises (a marker with no generation_id, that
    generation's own manifest 404ing, a non-object manifest payload, or a
    manifest with no usable ``files`` map) — the publish protocol (immutable
    workspaces, THEN the generation manifest, THEN the marker) guarantees
    all of those exist once the marker names a generation_id, so any of them
    failing means something is genuinely broken, not "nothing to carry".
    On a double match (should never happen — one event per issuer per
    generation), the NEWEST fiscal period wins, never the first one iterated
    (``files`` iterates in sorted-string key order, which is NOT
    chronological).
    """
    from engine.company_intelligence.events import parse_canonical_event_id

    marker = fetch_current_workspace_marker(base_url=base_url)
    if marker is None:
        return None  # (i)
    generation_id = str(marker.get("generation_id") or "")
    if not generation_id:
        raise WorkspaceChainIntegrityError(
            "top-level marker carries no generation_id despite a non-404 read"
        )
    manifest = fetch_generation_manifest(generation_id, base_url=base_url)
    if not isinstance(manifest, Mapping):
        raise WorkspaceChainIntegrityError(
            f"generation {generation_id} manifest payload is not an object"
        )
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise WorkspaceChainIntegrityError(
            f"generation {generation_id} manifest carries no usable 'files' map"
        )
    matches: list[tuple[tuple[int, int], str]] = []
    for relative in files:
        relative_text = str(relative)
        if not relative_text.startswith("workspaces/") or not relative_text.endswith(".json"):
            continue
        candidate_event_id = relative_text[len("workspaces/"):-len(".json")]
        try:
            candidate_company_id, fiscal_period, _event_type = parse_canonical_event_id(candidate_event_id)
        except Exception:  # noqa: BLE001 — a non-canonical file name is simply not a match
            continue
        if candidate_company_id == company_id:
            matches.append(((fiscal_period.year, fiscal_period.quarter or 0), candidate_event_id))
    if not matches:
        return None  # (ii)
    matches.sort(key=lambda item: item[0])
    return matches[-1][1]


def _event_revision_from_generation(
    manifest: Mapping[str, Any], event_id: str, *, generation_id: str, base_url: str | None,
) -> dict[str, Any] | None:
    """The event's workspace body in *manifest*'s own generation, or None if
    this generation's manifest carries no entry for the event at all (a
    carried-forward nest that predates this event's first appearance, or an
    event that had already been superseded off the nest by this point)."""
    files = manifest.get("files") if isinstance(manifest.get("files"), Mapping) else {}
    relative = f"workspaces/{event_id}.json"
    if relative not in files:
        return None
    return fetch_raw_workspace(event_id, generation_id, base_url=base_url)


def read_event_source_revisions(
    event_id: str,
    *,
    base_url: str | None = None,
    max_hops: int = DEFAULT_MAX_CHAIN_HOPS,
    start_generation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Walk the verified predecessor chain and return *event_id*'s own
    ordered source revisions, OLDEST FIRST.

    Frozen spec D2(d): each hop verifies ``previous_manifest_sha256``
    against the FETCHED predecessor manifest's own bytes — a link to a
    nonexistent generation, or a hash mismatch, is a HARD
    ``WorkspaceChainIntegrityError``, never a silent skip or truncation. A
    v1 manifest (no ``previous_generation_id`` key at all) terminates the
    walk as the chain ROOT — v1 is lawful history, never an error. *max_hops*
    (documented, finite — D2(c)) bounds the walk; exceeding it is also a
    ``WorkspaceChainIntegrityError`` (an unbounded walk is never attempted).

    Each returned revision is a receipt dict: ``generation_id``,
    ``source_sha256`` (the workspace's own issuer_release source row hash,
    or ``None`` if absent), ``source_available_at``, ``observed_at``,
    ``lifecycle_state``, ``form`` (the issuer_release source row's SEC
    form), and ``workspace`` (the full body). CONSECUTIVE generations
    carrying a byte-identical ``source_sha256`` for this event (a
    carry-forward hop, WORLD STATE note) are deduped — only the FIRST
    generation that introduced a given source_sha256 is kept, so a carry
    creates no phantom revision.

    *start_generation_id* lets a caller resume from a KNOWN generation_id
    without a fresh marker fetch (e.g. the generation just minted locally
    this cycle, not yet visible on R2 under cache); default resolves the
    CURRENT published marker.
    """
    if start_generation_id is not None:
        generation_id: str | None = start_generation_id
        manifest_bytes: bytes | None = None
        manifest: dict[str, Any] | None = None
    else:
        marker = fetch_current_workspace_marker(base_url=base_url)
        generation_id = str(marker["generation_id"]) if marker else None
        manifest_bytes = None
        manifest = None

    newest_first: list[dict[str, Any]] = []
    hops = 0
    while generation_id is not None:
        if hops >= max_hops:
            raise WorkspaceChainIntegrityError(
                f"{event_id}: predecessor chain exceeds the {max_hops}-hop bound "
                "without reaching a root — refusing an unbounded walk"
            )
        hops += 1
        if manifest is None:
            # First iteration (fresh marker read, or a caller-supplied
            # start_generation_id): fetch fresh. On every LATER iteration
            # this generation's bytes were already fetched+hash-verified as
            # the PREVIOUS hop's predecessor — reused below (MAJOR-8(a): no
            # second fetch per hop).
            try:
                manifest_bytes, manifest = _fetch_generation_manifest_raw(generation_id, base_url=base_url)
            except WorkspaceChainNotPublished as exc:
                raise WorkspaceChainIntegrityError(
                    f"{event_id}: chain link names generation {generation_id!r}, which does not exist"
                ) from exc

        revision = _event_revision_from_generation(
            manifest, event_id, generation_id=generation_id, base_url=base_url,
        )
        if revision is not None:
            lifecycle = revision.get("lifecycle") if isinstance(revision.get("lifecycle"), Mapping) else {}
            source_sha256 = None
            for source in revision.get("sources") or []:
                if isinstance(source, Mapping) and source.get("kind") == "issuer_release":
                    source_sha256 = source.get("source_sha256")
                    form = source.get("form")
                    break
            else:
                form = None
            newest_first.append({
                "generation_id": generation_id,
                "source_sha256": source_sha256,
                "source_available_at": lifecycle.get("source_available_at"),
                "observed_at": lifecycle.get("observed_at"),
                "lifecycle_state": lifecycle.get("state"),
                "form": form,
                "workspace": revision,
            })

        schema = manifest.get("schema")
        if schema == "event_workspace_manifest.v1":
            break  # v1 is the chain root; no predecessor field to follow.
        previous_id = manifest.get("previous_generation_id")
        if previous_id is None:
            break  # A genuine first-ever v2 generation.
        previous_id = str(previous_id)
        expected_sha = str(manifest.get("previous_manifest_sha256") or "")
        try:
            predecessor_bytes, predecessor_manifest = _fetch_generation_manifest_raw(previous_id, base_url=base_url)
        except WorkspaceChainNotPublished as exc:
            raise WorkspaceChainIntegrityError(
                f"{event_id}: generation {generation_id} names predecessor {previous_id!r}, "
                "which does not exist"
            ) from exc
        # MINOR-10: verify against the sha256 of the RAW FETCHED BYTES of
        # the predecessor manifest — never a re-serialization of the parsed
        # dict, which would not catch a byte-level divergence that happens
        # to parse identically.
        actual_sha = sha256(predecessor_bytes).hexdigest()
        if actual_sha != expected_sha:
            raise WorkspaceChainIntegrityError(
                f"{event_id}: generation {generation_id}'s previous_manifest_sha256 "
                f"({expected_sha!r}) does not match predecessor {previous_id}'s actual "
                f"manifest bytes ({actual_sha!r})"
            )
        # MAJOR-8(a): the predecessor's bytes/manifest are ALREADY verified —
        # reuse them as the NEXT loop iteration's "current" generation
        # instead of re-fetching (halves manifest GETs from 2N to N).
        generation_id = previous_id
        manifest_bytes, manifest = predecessor_bytes, predecessor_manifest

    newest_first.reverse()  # now oldest -> newest
    deduped: list[dict[str, Any]] = []
    for revision in newest_first:
        if deduped and revision["source_sha256"] == deduped[-1]["source_sha256"]:
            # A carry-forward hop: consecutive generations with a
            # byte-identical source_sha256 for this event create no phantom
            # revision (WORLD STATE chain/carry interplay note).
            continue
        deduped.append(revision)
    return deduped
