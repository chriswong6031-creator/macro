"""Authenticated serving route for the private Filing Forensics state."""
from __future__ import annotations

import json
import os
import re
import threading
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response

from engine.fundamental_forensics.private_state import load_state_blob

router = APIRouter()
REPO = Path(os.environ.get("MACRO_REPO", "/opt/macro"))

# The receipt API is an authenticated, private research surface even when it is
# mounted by itself in a narrow test app (and therefore outside app.main's
# no-store middleware).  Keep the policy on both successful responses and the
# expected failure boundary: caches must never replay an entitlement or a
# receipt response across users.
_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, noarchive",
}

_SNAPSHOT_ID_RE = re.compile(r"\Affqsv2_[a-f0-9]{64}\Z")
_ROOT_CELL_ID_RE = re.compile(r"\Ametric_cell_[a-f0-9]{64}\Z")
_MAX_QUERY_VALUE_BYTES = 128
# Bounded receipt reads do not automatically bound response construction.  A
# valid sealed receipt can name many selected leaves; never turn it into a
# multi-megabyte roots page or detail waterfall at request time.
_MAX_LEAF_REFS_PER_ROOT = 1_024
_MAX_LEAF_REFS_PER_ROOT_RESPONSE = 3_072
_MAX_LEAF_REFS_PER_ROOTS_PAGE = 12_288
_MAX_ROOT_DETAIL_RESPONSE_BYTES = 4 * 1024 * 1024
_ROOT_DETAIL_WATERFALL_FIELD_BYTES = len(b',"waterfall":[]')
_B3_PROJECTION_FIELDS = frozenset(
    {
        "attestation_id",
        "authority_snapshot_id",
        "package_id",
        "extraction_id",
        "cik",
        "accession",
        "companyfacts_capture_id",
        "companyfacts_manifest_id",
        "companyfacts_response_sha256",
        "companyfacts_match_count",
        "attested_at",
    }
)
_STORE_LOCK = threading.Lock()
_STORE_CACHE: Any | None = None
_STORE_INITIALIZED = False
_PRIVATE_HEADER_NAMES = frozenset(name.lower() for name in _PRIVATE_HEADERS)
_CONVERSION_RECEIPT_CLOCK_FIELDS = (
    "acquisition_started_at",
    "captured_at",
    "recorded_at",
    "source_snapshot_at",
    "submissions_recorded_at",
)


def _private(response: Response) -> None:
    """Apply the private policy in standalone-router tests and production."""
    response.headers.update(_PRIVATE_HEADERS)


def _private_error(
    status_code: int,
    detail: Any,
    extra_headers: Mapping[str, str] | None = None,
) -> HTTPException:
    """Construct an expected failure which cannot be shared-cached."""
    # HTTP field names are case-insensitive.  Normalize only for comparison so
    # a hostile/lowercase upstream ``cache-control`` or mixed-case ``Vary``
    # cannot coexist with and weaken the route policy.  Unrelated safe headers
    # such as WWW-Authenticate remain intact.
    inherited = {
        str(name): str(value)
        for name, value in dict(extra_headers or {}).items()
        if str(name).lower() not in _PRIVATE_HEADER_NAMES
    }
    return HTTPException(
        status_code=status_code,
        detail=detail,
        # Inherited auth/paywall headers are informative only.  The private
        # policy is non-negotiable and must not be weakened by an upstream
        # exception's Cache-Control/Vary directive.
        headers={**inherited, **_PRIVATE_HEADERS},
    )


def _unavailable() -> HTTPException:
    """Do not distinguish missing, malformed, non-strict, or unavailable R2 state."""
    return _private_error(503, "attested query history temporarily unavailable")


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Lazy wrapper avoids importing partially initialized app.main at mount time."""
    from app.main import require_user as _require_user  # noqa: PLC0415
    from app.paywall import enforce_site_full  # noqa: PLC0415

    try:
        # Authentication must happen before the entitlement check.  More
        # importantly, store construction happens only in endpoint bodies, so
        # either denial returns before a private object can be opened.
        return enforce_site_full(_require_user(authorization), always=True)
    except HTTPException as exc:
        # app.main's API middleware adds only Cache-Control.  This wrapper also
        # runs under isolated router tests, so attach the full privacy policy at
        # the dependency boundary.
        raise _private_error(exc.status_code, exc.detail, exc.headers) from None


@router.get("/api/forensics/state")
def forensics_state(_user: dict = Depends(require_site_full_user)) -> Response:
    """Return the validated gzip object to an entitled user, never a public URL."""
    blob = load_state_blob(REPO)
    if blob is None:
        raise _private_error(503, "forensics state temporarily unavailable")
    return Response(
        content=blob,
        media_type="application/gzip",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'inline; filename="forensics-state.json.gz"',
            "Vary": "Authorization",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, noarchive",
        },
    )


# ---------------------------------------------------------------------------
# Attested history: receipt-serving only, never a request-time verifier.
# ---------------------------------------------------------------------------

def _build_store():
    """Build one private research store lazily, then reuse it for immutable reads.

    Reconstructing a boto3/R2 client on every request defeats the engine's
    bounded immutable-reader cache and can leak connection pools.  A missing
    store is cached too: it remains a bounded 503 until process restart or the
    explicit test/operator reset, never a fallback to a different bucket.
    """
    global _STORE_CACHE, _STORE_INITIALIZED
    with _STORE_LOCK:
        if _STORE_INITIALIZED:
            return _STORE_CACHE
        from engine.research_vault.r2_store import build_store  # noqa: PLC0415

        _STORE_CACHE = build_store()
        _STORE_INITIALIZED = True
        return _STORE_CACHE


def _reset_store_cache() -> None:
    """Resettable test seam; production does not refresh or swap private stores."""
    global _STORE_CACHE, _STORE_INITIALIZED
    with _STORE_LOCK:
        _STORE_CACHE = None
        _STORE_INITIALIZED = False


def load_attested_query_receipt_index(store: Any, *, snapshot_id: str | None = None) -> Any:
    """Late-bind the bounded engine reader so this router has no import-time cycle.

    The engine reader validates/digest-checks the pointer, manifest, coverage,
    bindings, and receipt projection.  It intentionally does not replay the
    v1 snapshot, fetch SEC sources, or write an object; this transport layer
    must not turn a read request into a 1.5 GB verification job.
    """
    from engine.fundamental_forensics.attested_query_snapshots import (  # noqa: PLC0415
        load_attested_query_receipt_index as _load,
    )

    return _load(store, snapshot_id=snapshot_id)


def _strict_snapshot_id(snapshot_id: str) -> str:
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise _private_error(400, "invalid attested snapshot id")
    return snapshot_id


def _safe_cell_id(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _ROOT_CELL_ID_RE.fullmatch(value):
        raise _private_error(400, f"invalid {field}")
    return value


def _single_query_value(request: Request, name: str) -> str | None:
    """Bound query input and reject duplicate keys rather than choosing one silently."""
    values = request.query_params.getlist(name)
    if not values:
        return None
    if len(values) != 1:
        raise _private_error(400, f"invalid {name}")
    value = values[0]
    if len(value.encode("utf-8")) > _MAX_QUERY_VALUE_BYTES:
        raise _private_error(400, f"invalid {name}")
    return value


def _page_arguments(request: Request) -> tuple[str | None, int]:
    """Parse keyset controls ourselves so every invalid-input error stays private."""
    cursor = _single_query_value(request, "cursor")
    if cursor is not None:
        _safe_cell_id(cursor, field="cursor")

    raw_limit = _single_query_value(request, "limit")
    if raw_limit is None:
        return cursor, 25
    # ASCII decimal only: no whitespace, sign, float, or surprising coercion.
    if not raw_limit.isascii() or not raw_limit.isdecimal():
        raise _private_error(400, "invalid limit")
    limit = int(raw_limit)
    if not 1 <= limit <= 100:
        raise _private_error(400, "invalid limit")
    return cursor, limit


def _mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} is not a mapping")
    return value


def _index_attr(index: Any, name: str) -> Any:
    value = getattr(index, name, None)
    if value is None:
        raise ValueError(f"receipt index missing {name}")
    return value


def _load_receipt_index(snapshot_id: str | None = None) -> Any:
    """Open the private store only after auth/entitlement, then fail closed."""
    try:
        store = _build_store()
        if store is None:
            raise RuntimeError("private store is not configured")
        index = load_attested_query_receipt_index(store, snapshot_id=snapshot_id)
        if index is None:
            raise RuntimeError("receipt index is unavailable")
        return index
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - private storage is a fail-closed boundary
        raise _unavailable() from exc


def _manifest(index: Any) -> Mapping[str, Any]:
    return _mapping(_index_attr(index, "manifest"), field="receipt manifest")


def _receipt_identity(index: Any) -> dict[str, Any]:
    """Return only safe identity fields, never manifest/object-store key material."""
    snapshot_id = _index_attr(index, "snapshot_id")
    base_snapshot_id = _index_attr(index, "base_snapshot_id")
    query_hash = _index_attr(index, "query_hash")
    published_at = _index_attr(index, "published_at")
    if (
        not isinstance(snapshot_id, str)
        or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id)
        or not isinstance(base_snapshot_id, str)
        or not base_snapshot_id.startswith("ffqs_")
        or not isinstance(query_hash, str)
        or not re.fullmatch(r"[a-f0-9]{64}", query_hash)
    ):
        raise ValueError("receipt identity is invalid")
    # The engine emits a UTC datetime, while purpose-built test seams may emit
    # the canonical wire string.  Neither type is a private storage location.
    if hasattr(published_at, "isoformat"):
        published_at = published_at.isoformat().replace("+00:00", "Z")
    if not isinstance(published_at, str) or len(published_at) > 64:
        raise ValueError("receipt publication clock is invalid")
    return {
        "snapshot_id": snapshot_id,
        "base_snapshot_id": base_snapshot_id,
        "query_hash": query_hash,
        "published_at": published_at,
    }


def _authority(index: Any) -> dict[str, Any]:
    """The narrow positive claim is immutable; manifest nonclaims stay exact."""
    manifest = _manifest(index)
    nonclaims = _mapping(manifest.get("nonclaims"), field="receipt nonclaims")
    if any(value is not False for value in nonclaims.values()):
        raise ValueError("receipt nonclaims are invalid")
    return {
        "positive_claim": "B3_selected_member_companyfacts_row_correspondence_only",
        "coverage_scope": "selected_raw_fact_leaves_only",
        "claim_basis": "sealed_publication_receipt",
        "source_reverified_at_read": False,
        "match_body_replayed_at_read": False,
        "nonclaims": dict(nonclaims),
    }


def _coverage_components(row: Any) -> tuple[Mapping[str, Any], str, Sequence[str], Sequence[str], Sequence[str], str]:
    """Validate immutable coverage sizes before allocating response lists."""
    value = _mapping(row, field="root coverage")
    root_cell_id = value.get("root_cell_id")
    selected = value.get("selected_leaf_occurrence_ids")
    eligible = value.get("eligible_leaf_occurrence_ids")
    attested = value.get("attested_occurrence_ids")
    status = value.get("status")
    if (
        not isinstance(root_cell_id, str)
        or not _ROOT_CELL_ID_RE.fullmatch(root_cell_id)
        or not isinstance(selected, (list, tuple))
        or not isinstance(eligible, (list, tuple))
        or not isinstance(attested, (list, tuple))
        or status not in {"all_leaves_attested", "partially_attested", "not_attested", "not_evaluable"}
    ):
        raise ValueError("root coverage is invalid")
    if (
        len(selected) > _MAX_LEAF_REFS_PER_ROOT
        or len(eligible) > _MAX_LEAF_REFS_PER_ROOT
        or len(attested) > _MAX_LEAF_REFS_PER_ROOT
        or len(selected) + len(eligible) + len(attested) > _MAX_LEAF_REFS_PER_ROOT_RESPONSE
    ):
        raise ValueError("root coverage exceeds response budget")
    for collection in (selected, eligible, attested):
        if any(not isinstance(item, str) or len(item) > _MAX_QUERY_VALUE_BYTES for item in collection):
            raise ValueError("root coverage is invalid")
    return value, root_cell_id, selected, eligible, attested, status


def _coverage_row(row: Any) -> dict[str, Any]:
    """Limit list/detail coverage to the exact immutable coverage arrays."""
    _value, root_cell_id, selected, eligible, attested, status = _coverage_components(row)
    return {
        "root_cell_id": root_cell_id,
        "selected_leaf_occurrence_ids": list(selected),
        "eligible_leaf_occurrence_ids": list(eligible),
        "attested_occurrence_ids": list(attested),
        "status": status,
    }


def _root_ids(index: Any) -> Sequence[str]:
    """Read the engine's validated immutable root-id index without copying it."""
    root_ids = _index_attr(index, "root_ids")
    if not isinstance(root_ids, Sequence) or isinstance(root_ids, (str, bytes)):
        raise ValueError("receipt root index is invalid")
    # The engine validates order/uniqueness while digest-checking coverage.  Do
    # not rewalk up to 100k rows in HTTP just to reconstruct the same index.
    endpoints = (*root_ids[0:1], *root_ids[-1:])
    if any(not isinstance(value, str) or not _ROOT_CELL_ID_RE.fullmatch(value) for value in endpoints):
        raise ValueError("receipt root index endpoints are invalid")
    return root_ids


def _roots_by_id(index: Any) -> Mapping[str, Any]:
    return _mapping(_index_attr(index, "roots_by_id"), field="receipt root index")


def _minimal_conversion_receipt(index: Any) -> dict[str, Any]:
    """Expose receipt identity/counts, never conversion inputs, rows, or sources."""
    receipt = _mapping(_manifest(index).get("companyfacts_conversion_receipt"), field="conversion receipt")
    scalar_fields = (
        "receipt_id",
        "schema",
        "adapter_version",
        "capture_id",
        "manifest_id",
        "cik",
        "availability",
        "occurrence_count",
        "output_occurrence_count",
        "pit_eligible_count",
    )
    if any(name not in receipt for name in (*scalar_fields, "clocks")):
        raise ValueError("conversion receipt is incomplete")
    clocks = _mapping(receipt["clocks"], field="conversion receipt clocks")
    if set(clocks) != set(_CONVERSION_RECEIPT_CLOCK_FIELDS) or any(
        not isinstance(clocks[name], str) or not clocks[name] or len(clocks[name]) > 64
        for name in _CONVERSION_RECEIPT_CLOCK_FIELDS
    ):
        raise ValueError("conversion receipt clocks are invalid")
    if any(
        not isinstance(receipt[name], str) or not receipt[name]
        for name in scalar_fields[:6]
    ) or not isinstance(receipt["availability"], str):
        raise ValueError("conversion receipt identity is invalid")
    if any(
        isinstance(receipt[name], bool) or not isinstance(receipt[name], int) or receipt[name] < 0
        for name in scalar_fields[-3:]
    ):
        raise ValueError("conversion receipt counts are invalid")

    # Project each public scalar explicitly.  The engine index recursively
    # freezes its manifest with MappingProxyType, which is intentionally not
    # JSON serializable.  Do not generic-thaw the receipt: doing so would make a
    # future private source/object field one shallow edit away from HTTP.
    return {
        "receipt_id": receipt["receipt_id"],
        "schema": receipt["schema"],
        "adapter_version": receipt["adapter_version"],
        "capture_id": receipt["capture_id"],
        "manifest_id": receipt["manifest_id"],
        "cik": receipt["cik"],
        "clocks": {name: clocks[name] for name in _CONVERSION_RECEIPT_CLOCK_FIELDS},
        "availability": receipt["availability"],
        "occurrence_count": receipt["occurrence_count"],
        "output_occurrence_count": receipt["output_occurrence_count"],
        "pit_eligible_count": receipt["pit_eligible_count"],
    }


def _latest_payload(index: Any) -> dict[str, Any]:
    manifest = _manifest(index)
    policy = _mapping(manifest.get("policy"), field="receipt policy")
    clocks = _mapping(manifest.get("clocks"), field="receipt clocks")
    coverage_summary = _mapping(manifest.get("coverage_summary"), field="coverage summary")
    return _receipt_identity(index) | {
        "policy": dict(policy),
        "clocks": dict(clocks),
        "coverage_summary": dict(coverage_summary),
        "companyfacts_conversion_receipt": _minimal_conversion_receipt(index),
        "authority": _authority(index),
    }


def _page_root_ids(root_ids: Sequence[str], cursor: str | None, limit: int) -> tuple[Sequence[str], str | None, str | None]:
    """Bisect an immutable ID index, then read only the requested coverage rows."""
    start = 0
    if cursor is not None:
        start = bisect_right(root_ids, cursor)
        if start == 0 or root_ids[start - 1] != cursor:
            raise _private_error(400, "invalid cursor")
    page_ids = root_ids[start : start + limit]
    next_cursor = page_ids[-1] if start + len(page_ids) < len(root_ids) and page_ids else None
    return page_ids, cursor, next_cursor


def _page_coverage_rows(roots_by_id: Mapping[str, Any], page_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Budget page leaves before serializing one row; no all-roots materialization."""
    raw_rows: list[tuple[str, Any]] = []
    leaf_refs = 0
    for root_id in page_ids:
        raw_root = roots_by_id.get(root_id)
        _value, covered_id, selected, eligible, attested, _status = _coverage_components(raw_root)
        if covered_id != root_id:
            raise ValueError("receipt root index binding is invalid")
        leaf_refs += len(selected) + len(eligible) + len(attested)
        if leaf_refs > _MAX_LEAF_REFS_PER_ROOTS_PAGE:
            raise ValueError("roots page exceeds response budget")
        raw_rows.append((root_id, raw_root))
    return [_coverage_row(raw_root) for _root_id, raw_root in raw_rows]


def _attestation_projections(index: Any) -> Mapping[str, Mapping[str, Any]]:
    """Use the engine's pre-indexed compact B3 projections, never raw B3 records."""
    records = _mapping(_index_attr(index, "attestations_by_id"), field="attestation index")
    # The receipt reader has already sealed the entire map.  Walk only entries
    # selected into this bounded waterfall rather than paying O(all B3 records)
    # per detail request.
    return records


def _json_wire_upper_bound(value: Any) -> int:
    """Conservatively size one JSON fragment without retaining its encoding.

    ``ensure_ascii=True`` is never smaller than the UTF-8 JSON emitted by
    Starlette for non-ASCII text.  Measuring one bounded row at a time keeps a
    legal but extremely long canonical decimal from accumulating into a large
    response before the aggregate ceiling is enforced.
    """
    try:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("attested history response is not bounded JSON") from exc
    return len(payload)


def _waterfall(
    index: Any,
    root: Mapping[str, Any],
    response_prefix: Mapping[str, Any],
) -> list[dict[str, Any]]:
    bindings = _mapping(_index_attr(index, "bindings_by_occurrence"), field="receipt bindings")
    projections = _attestation_projections(index)
    eligible = set(root["eligible_leaf_occurrence_ids"])
    attested = set(root["attested_occurrence_ids"])
    selected = root["selected_leaf_occurrence_ids"]
    if not attested.issubset(set(selected)) or not eligible.issubset(set(selected)):
        raise ValueError("root coverage membership is invalid")

    # Size every already-built response field, plus the exact punctuation for
    # adding an empty waterfall to that object.  Each emitted row is then sized
    # before retention.  One comma is charged for every row (including the
    # first, where it is a harmless one-byte overestimate), so this remains a
    # conservative bound without ever serializing the growing aggregate.
    wire_bytes = _json_wire_upper_bound(response_prefix) + _ROOT_DETAIL_WATERFALL_FIELD_BYTES
    if wire_bytes > _MAX_ROOT_DETAIL_RESPONSE_BYTES:
        raise ValueError("root detail exceeds serialized response budget")

    rows: list[dict[str, Any]] = []
    for occurrence_id in selected:
        row: dict[str, Any] = {
            "occurrence_id": occurrence_id,
            "eligible": occurrence_id in eligible,
            "attested": occurrence_id in attested,
        }
        if occurrence_id in attested:
            binding = _mapping(bindings.get(occurrence_id), field="occurrence binding")
            attestation_id = binding.get("attestation_id")
            match_id = binding.get("match_id")
            companyfacts = _mapping(binding.get("companyfacts"), field="binding Company Facts projection")
            projection = projections.get(attestation_id)
            if not isinstance(attestation_id, str) or not isinstance(match_id, str) or projection is None:
                raise ValueError("attested occurrence binding is invalid")
            projection = _mapping(projection, field="attestation projection")
            if (
                not attestation_id.startswith("ffatt_")
                or projection.get("attestation_id") != attestation_id
                or set(projection) != _B3_PROJECTION_FIELDS
            ):
                raise ValueError("attestation projection is invalid")
            fields = ("cik", "accession", "taxonomy", "concept", "unit", "start", "end", "value")
            if any(name not in companyfacts for name in fields):
                raise ValueError("binding Company Facts projection is incomplete")
            row.update(
                {
                    "attestation_id": attestation_id,
                    "match_id": match_id,
                    "companyfacts": {
                        "cik": companyfacts["cik"],
                        "accession": companyfacts["accession"],
                        "taxonomy": companyfacts["taxonomy"],
                        "concept": companyfacts["concept"],
                        "unit": companyfacts["unit"],
                        "period": {
                            "start": companyfacts["start"],
                            "end": companyfacts["end"],
                        },
                        "value": companyfacts["value"],
                    },
                    "stored_b3_projection": dict(projection),
                }
            )
        wire_bytes += _json_wire_upper_bound(row) + 1
        if wire_bytes > _MAX_ROOT_DETAIL_RESPONSE_BYTES:
            raise ValueError("root detail exceeds serialized response budget")
        rows.append(row)
    return rows


def _with_unavailable_boundary(callback):
    """Convert malformed index projections into the bounded public 503 contract."""
    try:
        return callback()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - no private parser/storage details over HTTP
        raise _unavailable() from exc


@router.get("/api/forensics/v1/attested-history/latest")
def attested_history_latest(
    response: Response,
    _user: dict = Depends(require_site_full_user),
) -> dict[str, Any]:
    """Return the latest compact immutable receipt; never reverify source at read."""
    _private(response)
    return _with_unavailable_boundary(lambda: _latest_payload(_load_receipt_index()))


@router.get("/api/forensics/v1/attested-history/snapshots/{snapshot_id}/roots")
def attested_history_roots(
    snapshot_id: str,
    request: Request,
    response: Response,
    _user: dict = Depends(require_site_full_user),
) -> dict[str, Any]:
    """Keyset-paginate compact root coverage by immutable root_cell_id."""
    _private(response)
    snapshot_id = _strict_snapshot_id(snapshot_id)
    cursor, limit = _page_arguments(request)

    def payload() -> dict[str, Any]:
        index = _load_receipt_index(snapshot_id)
        identity = _receipt_identity(index)
        if identity["snapshot_id"] != snapshot_id:
            raise ValueError("receipt index returned a different snapshot")
        root_ids = _root_ids(index)
        page_ids, requested_cursor, next_cursor = _page_root_ids(root_ids, cursor, limit)
        roots_by_id = _roots_by_id(index)
        page = _page_coverage_rows(roots_by_id, page_ids)
        return identity | {
            "authority": _authority(index),
            "page": {
                "cursor": requested_cursor,
                "next_cursor": next_cursor,
                "limit": limit,
                "returned": len(page),
                "total": len(root_ids),
            },
            "roots": page,
        }

    return _with_unavailable_boundary(payload)


@router.get("/api/forensics/v1/attested-history/snapshots/{snapshot_id}/roots/{root_cell_id}")
def attested_history_root_detail(
    snapshot_id: str,
    root_cell_id: str,
    response: Response,
    _user: dict = Depends(require_site_full_user),
) -> dict[str, Any]:
    """Return one selected-leaf waterfall and its compact B3 correspondence receipt."""
    _private(response)
    snapshot_id = _strict_snapshot_id(snapshot_id)
    root_cell_id = _safe_cell_id(root_cell_id, field="root_cell_id")

    def payload() -> dict[str, Any]:
        index = _load_receipt_index(snapshot_id)
        identity = _receipt_identity(index)
        if identity["snapshot_id"] != snapshot_id:
            raise ValueError("receipt index returned a different snapshot")
        raw_root = _roots_by_id(index).get(root_cell_id)
        if raw_root is None:
            raise _private_error(404, "root cell not covered")
        root = _coverage_row(raw_root)
        if root["root_cell_id"] != root_cell_id:
            raise ValueError("receipt root index binding is invalid")
        response_prefix = identity | {
            "authority": _authority(index),
            "root": root,
        }
        return response_prefix | {"waterfall": _waterfall(index, root, response_prefix)}

    return _with_unavailable_boundary(payload)


@router.get(
    "/api/forensics/v1/attested-history/{remainder:path}",
    include_in_schema=False,
)
def attested_history_private_not_found(
    remainder: str,
    response: Response,
    _user: dict = Depends(require_site_full_user),
) -> None:
    """Hide malformed/extra history paths behind the same paid private boundary.

    Encoded slashes are decoded before route matching, so an otherwise valid
    root ID followed by ``%2F...`` lands here instead of receiving a framework
    404 without the full private/noindex policy.  Authentication and entitlement
    still run first, and this catchall never constructs or reads the store.
    """
    del remainder
    _private(response)
    raise _private_error(404, "attested history route not found")


__all__ = ["router", "require_site_full_user"]
