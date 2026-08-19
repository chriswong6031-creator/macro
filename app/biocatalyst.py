"""Authenticated, fact-only API for BioCatalyst trial intelligence.

The serving process reads only the pointer-bound public projection created by
the isolated BioCatalyst worker.  It never opens the worker state tree, raw
ClinicalTrials.gov responses, source receipts, or private object storage.
"""
from __future__ import annotations

import base64
import binascii
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import logging
from math import isfinite
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter()
log = logging.getLogger("macro.biocatalyst")

_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_FULL_ISO_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_PARTIAL_ISO_DATE = re.compile(r"^[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?$")
_MILESTONE_KINDS = frozenset(("primary_completion", "completion"))
_MILESTONE_WINDOWS = frozenset(("all", "next_30d", "next_90d", "next_180d"))
_MILESTONE_DATE_TYPES = frozenset(("ACTUAL", "ESTIMATED", "UNKNOWN"))
_MILESTONE_CURSOR_VERSION = "m2"
_MILESTONE_CURSOR_DOMAIN = b"macro-biocatalyst:trial-milestones:cursor-key:v2"
_MILESTONE_CURSOR_PROCESS_KEY = os.urandom(32)
_CHANGE_KINDS = frozenset(
    (
        "endpoint_added",
        "endpoint_removed",
        "endpoint_role_changed",
        "endpoint_measure_changed",
        "endpoint_time_frame_changed",
        "endpoint_description_changed",
        "enrollment_changed",
        "registry_status_changed",
        "study_date_changed",
        "site_listing_changed",
        "lead_sponsor_text_changed",
        "intervention_added",
        "intervention_removed",
        "intervention_changed",
    )
)
_CHANGE_WINDOWS = frozenset(("last_30d", "last_90d", "last_180d", "all"))
_CHANGE_CURSOR_VERSION = "c1"
_CHANGE_CURSOR_DOMAIN = b"macro-biocatalyst:trial-registry-changes:cursor-key:v1"
_CHANGE_CURSOR_PROCESS_KEY = os.urandom(32)
_PROSPECTIVE_CURSOR_VERSION = "p1"
_PROSPECTIVE_CURSOR_DOMAIN = b"macro-biocatalyst:trial-prospective-changes:cursor-key:v1"
_PROSPECTIVE_CURSOR_PROCESS_KEY = os.urandom(32)
_CHANGE_TAPE_CURSOR_VERSION = "ct1"
_CHANGE_TAPE_CURSOR_DOMAIN = b"macro-biocatalyst:trial-change-tape:cursor-key:v1"
_CHANGE_TAPE_CURSOR_PROCESS_KEY = os.urandom(32)
_CHANGE_TAPE_MAX_CURSOR_OFFSET = 5_120_000
_PEER_SET_CURSOR_VERSION = "t1"
_PEER_SET_CURSOR_DOMAIN = b"macro-biocatalyst:trial-peer-sets:cursor-key:v1"
_PEER_SET_CURSOR_PROCESS_KEY = os.urandom(32)
_PEER_SET_DEFAULT_LIMIT = 50
_PEER_SET_MAX_BODY_BYTES = 16 * 1024
_TRIAL_SCREEN_CURSOR_VERSION = "s1"
_TRIAL_SCREEN_CURSOR_DOMAIN = b"macro-biocatalyst:trial-screen:cursor-key:v1"
_TRIAL_SCREEN_CURSOR_PROCESS_KEY = os.urandom(32)
_TRIAL_SCREEN_MAX_CURSOR_OFFSET = 10_000
# Access domain already gated by require_site_full_user. Production GoTrue users
# carry a stable id and do not carry a commercial pricing-tier field.
_CALLER_ACCESS_DOMAIN = "site_full"
_PROSPECTIVE_ACCRUAL_STATES = frozenset(("baseline_established", "accruing"))
_PROSPECTIVE_CHANGE_KINDS = frozenset(
    (
        "registry_status",
        "enrollment_target",
        "enrollment_actual",
        "enrollment_count",
        "enrollment_type",
        "primary_completion_date",
        "completion_date",
        "site_set",
        "endpoint_record",
    )
)
_PROSPECTIVE_OBSERVATION_BASIS = "first_observed_between_successful_polls"
_CHANGE_TAPE_FIELD_CLASSES = frozenset(
    (
        "registry_status",
        "enrollment",
        "milestone_date_constraint",
        "site_list",
        "intervention",
        "endpoint_record_delta",
    )
)
_CHANGE_TAPE_REVIEW_STATES = frozenset(("not_required", "needs_review"))
# Additive, optional v1 extension: exact recorded values, their RFC 6901 source
# locator, and declared correction lineage.  The serving process never imports
# the engine, so these bounds are restated here and revalidated on every read;
# a tape published before the extension carries none of it and stays servable.
_CHANGE_TAPE_MAX_VALUE_JSON_BYTES = 4_096
_CHANGE_TAPE_MAX_TAPE_VALUE_JSON_BYTES = 262_144
_CHANGE_TAPE_MAX_SOURCE_POINTER_BYTES = 512
_CHANGE_TAPE_MAX_DECLARED_VALUE_BYTE_LENGTH = 16_777_216
_CHANGE_TAPE_VALUE_ENTRY_KEYS = {
    "state",
    "value_json",
    "value_byte_length",
    "value_truncated",
    "unavailable_reason",
}
_CHANGE_TAPE_VALUE_UNAVAILABLE_REASONS = frozenset(
    ("tape_value_budget_exhausted", "value_bytes_not_representable")
)
_CHANGE_TAPE_LINEAGE_KEYS = {
    "relation",
    "predecessor_basis",
    "predecessor_source_version",
    "predecessor_exact_operation_index",
    "correction_assessed",
}
_CHANGE_TAPE_VALUE_DISCLOSURE_BASE = {
    "encoding": "canonical_json_utf8",
    "locator_grammar": "rfc6901_json_pointer_into_source_record",
    "max_value_bytes": _CHANGE_TAPE_MAX_VALUE_JSON_BYTES,
    "max_tape_value_bytes": _CHANGE_TAPE_MAX_TAPE_VALUE_JSON_BYTES,
    "truncation_behavior": "declared_prefix_with_original_byte_length",
    "unavailable_behavior": "explicit_row_marker_never_empty_and_never_guessed",
    "correction_assessed": False,
}
_CHANGE_TAPE_AUTHORITY = {
    "classification": "deterministic_registry_change_read_model",
    "decision_authority": False,
    "maximum_authority": "A1_EXPLAIN",
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "issuer_resolution",
        "security_resolution",
        "asset_resolution",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "neural_web_authority",
        "all_prophet_uses",
        "assess_materiality",
        "assert_protocol_change",
        "assess_correction",
        "deliver_alert",
        "raise_authority",
    ],
}
_PUBLIC_ROOT = Path(
    os.environ.get("BIOCATALYST_PUBLIC_ROOT", "/var/lib/macro-biocatalyst/public")
)
_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, noarchive",
}
_AUTHORITY = {
    "classification": "source_fact",
    "decision_authority": False,
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "raise_authority",
    ],
}
_HISTORY_PRIVATE_KEY_FRAGMENTS = (
    "raw",
    "hash",
    "receipt",
    "ref",
    "object_key",
    "path",
    "json_path",
    "provenance",
)


def _prospective_value_key_is_private(key: str) -> bool:
    """Reject source/integrity machinery without blocking clinical ``reference``."""

    normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", key)
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").casefold()
    compact = normalized.replace("_", "")
    if normalized in {"reference", "references"}:
        return False
    return (
        normalized.endswith(("_ref", "_refs", "_sha256", "_hash"))
        or normalized.startswith(("raw_", "receipt", "transaction_"))
        or normalized
        in {
            "canonical_study",
            "hash",
            "raw",
            "ref",
            "refs",
            "sha256",
            "transaction",
            "object_key",
            "json_path",
            "hash_scope",
            "provenance",
        }
        or compact in {"ref", "refs", "sha256", "objectkey", "jsonpath", "hashscope"}
        or compact.endswith("hash")
    )


def _publication_runtime() -> tuple[type[Exception], type[Any]]:
    """Load the heavy projection validator only for this product surface."""

    from engine.biocatalyst.publication import (  # noqa: PLC0415
        PublicationError,
        PublicGenerationPublisher,
    )

    return PublicationError, PublicGenerationPublisher


def _trial_screen_runtime() -> tuple[type[Exception], Any, Any, Any]:
    """Load the pure screen contract without adding a second data reader."""

    from engine.biocatalyst.trial_screen import (  # noqa: PLC0415
        TrialScreenError,
        build_trial_screen_facets_read_model,
        build_trial_screen_read_model,
        canonicalize_trial_screen_filters,
    )

    return (
        TrialScreenError,
        canonicalize_trial_screen_filters,
        build_trial_screen_read_model,
        build_trial_screen_facets_read_model,
    )


def _verify_serving_runtime() -> None:
    """Fail startup loudly once the operator-provisioned lane exists."""

    _publication_runtime()


# The unprovisioned product is intentionally dark and must not force every
# unrelated app.main consumer to install the BioCatalyst validation stack.
# Once setup creates the public root, a missing serving dependency is a startup
# error rather than a silently absent or request-time-only product route.
if _PUBLIC_ROOT.exists():
    _verify_serving_runtime()


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Authenticate first and enforce the paid payload even while staging."""

    from app.main import require_user as _require_user  # noqa: PLC0415
    from app.paywall import enforce_site_full  # noqa: PLC0415

    try:
        return enforce_site_full(_require_user(authorization), always=True)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=_merged_private_headers(exc.headers),
        ) from exc


def _merged_private_headers(existing: Mapping[str, str] | None) -> dict[str, str]:
    """Preserve auth metadata while enforcing the paid surface's cache fence."""

    mandatory = {name.casefold() for name in _PRIVATE_HEADERS}
    merged: dict[str, str] = {}
    vary_tokens: list[str] = []
    for name, value in (existing or {}).items():
        if name.casefold() == "vary":
            vary_tokens.extend(part.strip() for part in value.split(",") if part.strip())
        elif name.casefold() not in mandatory:
            merged[name] = value
    merged.update(_PRIVATE_HEADERS)
    if vary_tokens:
        seen = {token.casefold() for token in vary_tokens}
        if "authorization" not in seen:
            vary_tokens.append("Authorization")
        merged["Vary"] = ", ".join(vary_tokens)
    return merged


def _publisher() -> Any:
    _publication_error, publisher_type = _publication_runtime()
    return publisher_type(_PUBLIC_ROOT)


def _unavailable(exc: Exception | None = None) -> HTTPException:
    if exc is not None:
        code = getattr(exc, "code", type(exc).__name__)
        log.warning("BioCatalyst public projection unavailable (%s)", code)
    return HTTPException(
        status_code=503,
        detail="trial intelligence temporarily unavailable",
        headers=_PRIVATE_HEADERS,
    )


def _read_bundle() -> tuple[Any, dict[str, Any]]:
    publication_error, publisher_type = _publication_runtime()
    publisher = publisher_type(_PUBLIC_ROOT)
    try:
        bundle = publisher.read_product_bundle()
    except (OSError, publication_error) as exc:
        raise _unavailable(exc) from None
    if bundle is None:
        raise _unavailable()
    health = dict(bundle.operational_health)
    if health.get("last_error_code") == "OPERATIONAL_HEALTH_UNAVAILABLE":
        log.warning(
            "BioCatalyst operational health unavailable (%s)",
            health.get("last_error_code"),
        )
    return bundle.projection, health


def _response(payload: Mapping[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=dict(payload),
        status_code=status_code,
        headers=_PRIVATE_HEADERS,
    )


def _fact(facts: Mapping[str, Any], key: str) -> Any:
    value = facts.get(key)
    if not isinstance(value, Mapping) or value.get("state") != "observed":
        return None
    return value.get("value")


def _text(value: object, *, maximum: int = 4096) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        return None
    return cleaned if len(cleaned) <= maximum else cleaned[: maximum - 1].rstrip() + "…"


def _text_list(value: object, *, limit: int = 100, maximum: int = 512) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    rows: list[str] = []
    seen: set[str] = set()
    for item in value:
        rendered = _text(item, maximum=maximum)
        if rendered is None or rendered in seen:
            continue
        rows.append(rendered)
        seen.add(rendered)
        if len(rows) >= limit:
            break
    return rows


def _named_rows(value: object, *, kind: str, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    rows: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        if kind == "intervention":
            row = {
                "name": _text(raw.get("name"), maximum=512),
                "type": _text(raw.get("type"), maximum=80),
                "description": _text(raw.get("description"), maximum=4000),
                "other_names": _text_list(
                    raw.get("otherNames") if "otherNames" in raw else raw.get("other_names"),
                    limit=20,
                    maximum=256,
                ),
            }
            if row["name"] is None:
                continue
        else:
            row = {
                "measure": _text(raw.get("measure"), maximum=1000),
                "time_frame": _text(
                    raw.get("timeFrame") if "timeFrame" in raw else raw.get("time_frame"),
                    maximum=1000,
                ),
                "description": _text(raw.get("description"), maximum=6000),
            }
            if row["measure"] is None:
                continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def _date_value(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    date_value = _text(value.get("date"), maximum=10)
    if date_value is None:
        return None
    return {
        "date": date_value,
        "type": _text(value.get("type"), maximum=20),
    }


def _sponsor_value(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    name = _text(value.get("name"), maximum=512)
    if name is None:
        return None
    return {"name": name, "class": _text(value.get("class"), maximum=80)}


def _enrollment_value(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    count = value.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return None
    return {"count": count, "type": _text(value.get("type"), maximum=20)}


def _countries(value: object) -> tuple[int | None, list[str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None, []
    countries: list[str] = []
    seen: set[str] = set()
    count = 0
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        count += 1
        country = _text(raw.get("country"), maximum=128)
        if country and country not in seen:
            countries.append(country)
            seen.add(country)
    return count, countries[:100]


def _history_json_value(value: object, *, depth: int = 0) -> Any:
    """Copy a bounded historical value or reject leaked provenance recursively."""

    if depth > 12:
        raise _unavailable()
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise _unavailable()
        return value
    if isinstance(value, str):
        # These are source-derived before/after values, not prose labels.  Do
        # not collapse whitespace, turn an empty string into null, or silently
        # truncate a value while presenting the result as an exact registry
        # difference.  Oversized values make the projection unavailable until
        # a separately typed truncation contract exists.
        if len(value) > 12_000:
            raise _unavailable()
        return value
    if isinstance(value, Mapping):
        if len(value) > 100:
            raise _unavailable()
        copied: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str) or len(key) > 256 or any(
                fragment in key.casefold()
                for fragment in _HISTORY_PRIVATE_KEY_FRAGMENTS
            ):
                raise _unavailable()
            copied[key] = _history_json_value(nested, depth=depth + 1)
        return copied
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) > 200:
            raise _unavailable()
        return [_history_json_value(item, depth=depth + 1) for item in value]
    raise _unavailable()


def _history_url(value: object, *, nct_id: str, version: int | None = None) -> str:
    rendered = _text(value, maximum=512)
    if rendered is None:
        raise _unavailable()
    expected = f"https://clinicaltrials.gov/study/{nct_id}"
    if version is None:
        if rendered != expected + "?tab=history":
            raise _unavailable()
    elif rendered != expected + f"?a={version}&tab=history":
        raise _unavailable()
    return rendered


def _history_for_api(model: Mapping[str, Any], *, nct_id: str) -> dict[str, Any]:
    """Serve only the pointer-bound, public-safe B2 history read model.

    The model carries an integrity self-hash for publication validation, but
    product clients must never receive hash, receipt, object, reference, or
    source-path provenance.  Every nested before/after value is copied through
    the same denylist to make this boundary robust to future model additions.
    """

    available = model.get("available")
    if available is False:
        reason = _text(
            model.get("unavailable_reason")
            if "unavailable_reason" in model
            else model.get("reason"),
            maximum=80,
        )
        return {
            "available": False,
            "state": "unavailable",
            "reason": reason or "not_collected",
        }
    if available is not True or model.get("nct_id") != nct_id:
        raise _unavailable()
    source_name = _text(model.get("source_name"), maximum=80)
    if source_name != "ClinicalTrials.gov":
        raise _unavailable()
    versions = model.get("versions")
    changes = model.get("changes")
    if (
        not isinstance(versions, Sequence)
        or isinstance(versions, (str, bytes))
        or not isinstance(changes, Sequence)
        or isinstance(changes, (str, bytes))
        or len(versions) > 500
        or len(changes) > 2_000
    ):
        raise _unavailable()
    public_versions: list[dict[str, Any]] = []
    for row in versions:
        if not isinstance(row, Mapping):
            raise _unavailable()
        display_version = row.get("display_version")
        submitted_at = _text(row.get("source_submitted_at"), maximum=10)
        if (
            not isinstance(display_version, int)
            or isinstance(display_version, bool)
            or display_version < 1
            or submitted_at is None
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", submitted_at)
        ):
            raise _unavailable()
        public_versions.append(
            {
                "display_version": display_version,
                "submitted_at": submitted_at,
                "url": _history_url(
                    row.get("url"), nct_id=nct_id, version=display_version
                ),
            }
        )
    public_changes: list[dict[str, Any]] = []
    for row in changes:
        if not isinstance(row, Mapping):
            raise _unavailable()
        kind = _text(row.get("kind"), maximum=120)
        before_version = row.get("before_display_version")
        after_version = row.get("after_display_version")
        if (
            kind is None
            or not isinstance(before_version, int)
            or isinstance(before_version, bool)
            or not isinstance(after_version, int)
            or isinstance(after_version, bool)
            or before_version < 1
            or after_version <= before_version
        ):
            raise _unavailable()
        public_changes.append(
            {
                "kind": kind,
                "before_display_version": before_version,
                "after_display_version": after_version,
                "before_value": _history_json_value(row.get("before_value")),
                "after_value": _history_json_value(row.get("after_value")),
            }
        )
    return {
        "available": True,
        "state": "available",
        "source": {
            "name": source_name,
            "url": _history_url(model.get("source_history_url"), nct_id=nct_id),
        },
        "coverage": _text(model.get("coverage_class"), maximum=80),
        "retrieved_at": _text(model.get("retrieved_at"), maximum=64),
        "versions": public_versions,
        "changes": public_changes,
    }


def _public_trial(
    snapshot: Mapping[str, Any],
    *,
    detail: bool,
    history_model: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    facts = snapshot.get("facts")
    attribution = snapshot.get("source_attribution")
    if not isinstance(facts, Mapping) or not isinstance(attribution, Mapping):
        raise _unavailable()
    official_title = _text(_fact(facts, "official_title"), maximum=2000)
    brief_title = _text(_fact(facts, "brief_title"), maximum=1000)
    title = official_title or brief_title
    locations = _fact(facts, "locations")
    site_count, countries = _countries(locations)
    row: dict[str, Any] = {
        "nct_id": snapshot["nct_id"],
        "title": title,
        "brief_title": brief_title,
        "status": _text(_fact(facts, "overall_status"), maximum=80),
        "study_type": _text(_fact(facts, "study_type"), maximum=80),
        "phases": _text_list(_fact(facts, "phases"), limit=12, maximum=80),
        "sponsor": _sponsor_value(_fact(facts, "sponsor")),
        "conditions": _text_list(_fact(facts, "conditions"), limit=100, maximum=512),
        "enrollment": _enrollment_value(_fact(facts, "enrollment")),
        "dates": {
            "start": _date_value(_fact(facts, "start_date")),
            "primary_completion": _date_value(_fact(facts, "primary_completion_date")),
            "completion": _date_value(_fact(facts, "completion_date")),
        },
        "updated_at": attribution.get("source_last_update_posted_at"),
        "retrieved_at": snapshot.get("retrieved_at"),
    }
    if detail:
        row.update(
            {
                "interventions": _named_rows(
                    _fact(facts, "interventions"), kind="intervention", limit=100
                ),
                "endpoints": {
                    "primary": _named_rows(
                        _fact(facts, "primary_outcomes"), kind="outcome", limit=100
                    ),
                    "secondary": _named_rows(
                        _fact(facts, "secondary_outcomes"), kind="outcome", limit=200
                    ),
                },
                "site_count": site_count,
                "countries": countries,
                "evidence": {
                    "provider": "ClinicalTrials.gov",
                    "record_id": snapshot["nct_id"],
                    "url": attribution.get("source_uri"),
                    "updated_at": attribution.get("source_last_update_posted_at"),
                    "retrieved_at": snapshot.get("retrieved_at"),
                    "coverage": snapshot.get("coverage_class"),
                },
                "history": _history_for_api(
                    history_model
                    if isinstance(history_model, Mapping)
                    else {"available": False, "unavailable_reason": "not_collected"},
                    nct_id=snapshot["nct_id"],
                ),
            }
        )
    return row


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"v1:{offset}".encode("ascii")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    if len(cursor) > 32 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    try:
        raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
        version, offset_text = raw.decode("ascii").split(":", 1)
        offset = int(offset_text)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS) from exc
    if version != "v1" or offset < 0 or offset > 100_000:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    return offset


def _query_text(
    value: str | None,
    *,
    name: str,
    maximum: int,
) -> str | None:
    """Validate query text inside the route so every error keeps private headers."""

    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum:
        raise HTTPException(
            status_code=400,
            detail=f"invalid {name}",
            headers=_PRIVATE_HEADERS,
        )
    return cleaned


def _query_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]{1,3}", value):
        raise HTTPException(
            status_code=400,
            detail="invalid limit",
            headers=_PRIVATE_HEADERS,
        )
    limit = int(value)
    if limit < 1 or limit > 250:
        raise HTTPException(
            status_code=400,
            detail="invalid limit",
            headers=_PRIVATE_HEADERS,
        )
    return limit


def _query_iso_date(value: str | None, *, name: str) -> date | None:
    """Accept one exact civil ISO date without assigning a source timezone."""

    if value is None:
        return None
    if not _FULL_ISO_DATE.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail=f"invalid {name}",
            headers=_PRIVATE_HEADERS,
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid {name}",
            headers=_PRIVATE_HEADERS,
        ) from exc


def _generation_as_of_time(projection: Any) -> datetime:
    """Return the committed generation clock, never request-time wall clock."""

    value = getattr(getattr(projection, "generation", None), "last_success_at", None)
    if not isinstance(value, str):
        raise _unavailable()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _unavailable() from None
    if parsed.tzinfo is None:
        raise _unavailable()
    return parsed.astimezone(timezone.utc)


def _generation_as_of_date(projection: Any) -> date:
    """Return the committed generation's UTC civil date."""

    return _generation_as_of_time(projection).date()


def _milestone_date_interval(value: object) -> tuple[date, date, str] | None:
    """Expand a source date of year/month/day precision into its full interval.

    ClinicalTrials.gov permits partial dates.  The monitor treats a partial
    value as the complete civil interval it denotes, rather than pretending a
    month or year is a point estimate.  A value is consequently displayed only
    when that whole interval is inside the requested range.
    """

    if not isinstance(value, str) or not _PARTIAL_ISO_DATE.fullmatch(value):
        return None
    try:
        if len(value) == 4:
            year = int(value)
            return date(year, 1, 1), date(year, 12, 31), "year"
        if len(value) == 7:
            year, month = (int(part) for part in value.split("-"))
            start = date(year, month, 1)
            if month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month + 1, 1) - timedelta(days=1)
            return start, end, "month"
        parsed = date.fromisoformat(value)
        return parsed, parsed, "day"
    except ValueError:
        return None


def _milestone_type(value: object) -> str:
    """Expose the registry's bounded date type, stating unknown honestly."""

    rendered = _text(value, maximum=20)
    normalized = rendered.upper() if rendered else "UNKNOWN"
    return normalized if normalized in _MILESTONE_DATE_TYPES else "UNKNOWN"


def _milestone_query_binding(
    *,
    milestone_kind: str,
    window: str,
    from_date: date | None,
    to_date: date | None,
    q: str | None,
    phase: str | None,
    status: str | None,
    condition: str | None,
    limit: int,
) -> dict[str, Any]:
    """Return only normalized selection inputs for an endpoint-local cursor."""

    return {
        "milestone_kind": milestone_kind,
        "window": window,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "q": q.casefold() if q else None,
        "phase": phase.casefold() if phase else None,
        "status": status.casefold() if status else None,
        "condition": condition.casefold() if condition else None,
        "limit": limit,
    }


def _opaque_digest(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def _resolve_peer_set_payload(payload: Any) -> tuple[tuple[str, ...], int, str | None]:
    """Parse one strict explicit-NCT cohort without deriving any membership."""

    if not isinstance(payload, Mapping) or set(payload) - {"nct_ids", "limit", "cursor"}:
        raise HTTPException(
            status_code=400,
            detail="invalid peer set request",
            headers=_PRIVATE_HEADERS,
        )
    nct_ids = payload.get("nct_ids")
    if (
        not isinstance(nct_ids, list)
        or not 2 <= len(nct_ids) <= 100
        or any(not isinstance(nct_id, str) or not _NCT_ID.fullmatch(nct_id) for nct_id in nct_ids)
        or len(set(nct_ids)) != len(nct_ids)
    ):
        raise HTTPException(
            status_code=400,
            detail="invalid NCT IDs",
            headers=_PRIVATE_HEADERS,
        )
    raw_limit = payload.get("limit", _PEER_SET_DEFAULT_LIMIT)
    if (
        not isinstance(raw_limit, int)
        or isinstance(raw_limit, bool)
        or not 1 <= raw_limit <= 100
    ):
        raise HTTPException(
            status_code=400,
            detail="invalid limit",
            headers=_PRIVATE_HEADERS,
        )
    cursor = payload.get("cursor")
    if cursor is not None and not isinstance(cursor, str):
        raise HTTPException(
            status_code=400,
            detail="invalid cursor",
            headers=_PRIVATE_HEADERS,
        )
    return tuple(sorted(nct_ids)), raw_limit, cursor


async def _read_peer_set_payload(request: Request) -> Any:
    """Read one bounded JSON body only after FastAPI has authenticated it."""

    declared_size = request.headers.get("content-length")
    if declared_size is not None:
        try:
            declared_bytes = int(declared_size)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="invalid peer set request",
                headers=_PRIVATE_HEADERS,
            ) from None
        if declared_bytes < 0:
            raise HTTPException(
                status_code=400,
                detail="invalid peer set request",
                headers=_PRIVATE_HEADERS,
            )
        if declared_bytes > _PEER_SET_MAX_BODY_BYTES:
            raise HTTPException(
                status_code=413,
                detail="request body too large",
                headers=_PRIVATE_HEADERS,
            )
    chunks: list[bytes] = []
    received_bytes = 0
    async for chunk in request.stream():
        received_bytes += len(chunk)
        if received_bytes > _PEER_SET_MAX_BODY_BYTES:
            raise HTTPException(
                status_code=413,
                detail="request body too large",
                headers=_PRIVATE_HEADERS,
            )
        chunks.append(chunk)
    body = b"".join(chunks)
    if not body:
        raise HTTPException(
            status_code=400,
            detail="invalid peer set request",
            headers=_PRIVATE_HEADERS,
        )
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=400,
            detail="invalid peer set request",
            headers=_PRIVATE_HEADERS,
        ) from None


def _peer_set_caller_binding(user: Mapping[str, Any]) -> dict[str, str]:
    """Bind cursors to the authenticated subject and this API's access domain.

    ``require_site_full_user`` has already enforced ``site_full``. Production
    GoTrue users expose a stable ``id`` and do not carry a commercial ``tier``.
    Isolation is therefore subject id plus the capability this route gated on
    — not a pricing-tier field, not ``user_metadata``, and not a second
    entitlement-store lookup. An incidental ``tier`` key is ignored.
    """

    user_id = user.get("id")
    if (
        not isinstance(user_id, str)
        or not user_id.strip()
        or len(user_id) > 256
    ):
        raise _unavailable()
    return {"subject": user_id, "entitlement": _CALLER_ACCESS_DOMAIN}


def _peer_set_query_binding(
    *, cohort_nct_ids: Sequence[str], page_limit: int, user: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "cohort_nct_ids": list(cohort_nct_ids),
        "limit": page_limit,
        "caller": _peer_set_caller_binding(user),
    }


def _peer_set_cursor_key() -> bytes:
    """Use a domain-separated signing key for peer-matrix pagination."""

    configured = os.environ.get("BIOCATALYST_CURSOR_SECRET")
    if configured is None:
        return _PEER_SET_CURSOR_PROCESS_KEY
    try:
        raw = configured.encode("utf-8")
    except UnicodeEncodeError:
        raise _unavailable() from None
    if len(raw) < 32:
        raise _unavailable()
    return hmac.new(raw, _PEER_SET_CURSOR_DOMAIN, sha256).digest()


def _peer_set_cursor_payload(
    offset: int, *, generation_digest: str, query_digest: str
) -> bytes:
    return ":".join(
        (
            _PEER_SET_CURSOR_VERSION,
            str(offset),
            generation_digest,
            query_digest,
        )
    ).encode("ascii")


def _encode_peer_set_cursor(
    offset: int,
    *,
    generation_id: str,
    query_binding: Mapping[str, Any],
    cursor_key: bytes | None = None,
) -> str:
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    payload = _peer_set_cursor_payload(
        offset,
        generation_digest=_opaque_digest({"generation_id": generation_id}),
        query_digest=_opaque_digest(dict(query_binding)),
    )
    key = cursor_key if cursor_key is not None else _peer_set_cursor_key()
    signature = hmac.new(key, payload, sha256).hexdigest()
    return base64.urlsafe_b64encode(payload + b":" + signature.encode("ascii")).decode(
        "ascii"
    ).rstrip("=")


def _decode_peer_set_cursor(
    cursor: str | None, *, cursor_key: bytes | None = None
) -> tuple[int, str | None, str | None]:
    """Verify cursor integrity before opening a public generation."""

    if cursor is None or cursor == "":
        return 0, None, None
    if len(cursor) > 512 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    try:
        raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
        version, offset_text, generation_digest, query_digest, signature = raw.decode(
            "ascii"
        ).split(":")
        offset = int(offset_text)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS) from exc
    if (
        version != _PEER_SET_CURSOR_VERSION
        or not re.fullmatch(r"[0-9]+", offset_text)
        or offset < 0
        or not re.fullmatch(r"[0-9a-f]{64}", generation_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", query_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", signature)
    ):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    payload = _peer_set_cursor_payload(
        offset,
        generation_digest=generation_digest,
        query_digest=query_digest,
    )
    key = cursor_key if cursor_key is not None else _peer_set_cursor_key()
    expected_signature = hmac.new(key, payload, sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    return offset, generation_digest, query_digest


def _trial_screen_query_binding(
    *, filters: Mapping[str, Any], page_limit: int, user: Mapping[str, Any]
) -> dict[str, Any]:
    """Bind every normalized screen selector to one authenticated caller."""

    expected = {
        "sponsor",
        "intervention",
        "study_type",
        "phase",
        "status",
        "condition",
        "primary_completion_from",
        "primary_completion_to",
    }
    if set(filters) != expected:
        raise _unavailable()
    return {
        "sponsor": filters["sponsor"],
        "intervention": filters["intervention"],
        "study_type": filters["study_type"],
        "phase": filters["phase"],
        "status": filters["status"],
        "condition": filters["condition"],
        "primary_completion_from": filters["primary_completion_from"],
        "primary_completion_to": filters["primary_completion_to"],
        "limit": page_limit,
        "caller": _peer_set_caller_binding(user),
    }


def _trial_screen_cursor_key() -> bytes:
    """Return the screen-only HMAC key before any public projection read."""

    configured = os.environ.get("BIOCATALYST_CURSOR_SECRET")
    if configured is None:
        return _TRIAL_SCREEN_CURSOR_PROCESS_KEY
    try:
        raw = configured.encode("utf-8")
    except UnicodeEncodeError:
        raise _unavailable() from None
    if len(raw) < 32:
        raise _unavailable()
    return hmac.new(raw, _TRIAL_SCREEN_CURSOR_DOMAIN, sha256).digest()


def _trial_screen_cursor_payload(
    offset: int, *, generation_digest: str, query_digest: str
) -> bytes:
    return ":".join(
        (
            _TRIAL_SCREEN_CURSOR_VERSION,
            str(offset),
            generation_digest,
            query_digest,
        )
    ).encode("ascii")


def _encode_trial_screen_cursor(
    offset: int,
    *,
    generation_id: str,
    query_binding: Mapping[str, Any],
    cursor_key: bytes | None = None,
) -> str:
    """Encode an opaque screen cursor without filter, caller, or generation text."""

    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset < 0
        or offset > _TRIAL_SCREEN_MAX_CURSOR_OFFSET
    ):
        raise ValueError("offset must be a bounded non-negative integer")
    payload = _trial_screen_cursor_payload(
        offset,
        generation_digest=_opaque_digest({"generation_id": generation_id}),
        query_digest=_opaque_digest(dict(query_binding)),
    )
    key = cursor_key if cursor_key is not None else _trial_screen_cursor_key()
    signature = hmac.new(key, payload, sha256).hexdigest()
    return base64.urlsafe_b64encode(payload + b":" + signature.encode("ascii")).decode(
        "ascii"
    ).rstrip("=")


def _decode_trial_screen_cursor(
    cursor: str | None, *, cursor_key: bytes | None = None
) -> tuple[int, str | None, str | None]:
    """Authenticate an s1 cursor before opening the committed generation."""

    if not cursor:
        return 0, None, None
    if len(cursor) > 384 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    try:
        raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
        version, offset_text, generation_digest, query_digest, signature = raw.decode(
            "ascii"
        ).split(":")
        offset = int(offset_text)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS) from exc
    if (
        version != _TRIAL_SCREEN_CURSOR_VERSION
        or not re.fullmatch(r"[0-9]+", offset_text)
        or offset < 0
        or offset > _TRIAL_SCREEN_MAX_CURSOR_OFFSET
        or not re.fullmatch(r"[0-9a-f]{64}", generation_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", query_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", signature)
    ):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    payload = _trial_screen_cursor_payload(
        offset,
        generation_digest=generation_digest,
        query_digest=query_digest,
    )
    key = cursor_key if cursor_key is not None else _trial_screen_cursor_key()
    expected_signature = hmac.new(key, payload, sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    return offset, generation_digest, query_digest


def _milestone_cursor_key() -> bytes:
    """Return a private cursor key without imposing a deployment secret.

    The process-random fallback deliberately invalidates cursors across process
    restarts. Operators that need cross-process or restart-stable pagination
    may provide a sufficiently strong secret; it is domain-separated before
    use so the configured material is never used directly as an HMAC key.
    """

    configured = os.environ.get("BIOCATALYST_CURSOR_SECRET")
    if configured is None:
        return _MILESTONE_CURSOR_PROCESS_KEY
    try:
        raw = configured.encode("utf-8")
    except UnicodeEncodeError:
        raise _unavailable() from None
    if len(raw) < 32:
        raise _unavailable()
    return hmac.new(raw, _MILESTONE_CURSOR_DOMAIN, sha256).digest()


def _milestone_cursor_payload(
    offset: int,
    *,
    generation_digest: str,
    query_digest: str,
) -> bytes:
    return ":".join(
        (
            _MILESTONE_CURSOR_VERSION,
            str(offset),
            generation_digest,
            query_digest,
        )
    ).encode("ascii")


def _encode_milestone_cursor(
    offset: int,
    *,
    generation_id: str,
    query_binding: Mapping[str, Any],
    cursor_key: bytes | None = None,
) -> str:
    """Encode a signed endpoint-only cursor without raw query or generation data."""

    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    payload = _milestone_cursor_payload(
        offset,
        generation_digest=_opaque_digest({"generation_id": generation_id}),
        query_digest=_opaque_digest(dict(query_binding)),
    )
    key = cursor_key if cursor_key is not None else _milestone_cursor_key()
    signature = hmac.new(key, payload, sha256).hexdigest()
    raw = payload + b":" + signature.encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_milestone_cursor(
    cursor: str | None,
    *,
    cursor_key: bytes | None = None,
) -> tuple[int, str | None, str | None]:
    """Authenticate syntax before the public read; bindings are checked separately."""

    if not cursor:
        return 0, None, None
    if len(cursor) > 384 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    try:
        raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
        version, offset_text, generation_digest, query_digest, signature = raw.decode(
            "ascii"
        ).split(":")
        offset = int(offset_text)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS) from exc
    if (
        version != _MILESTONE_CURSOR_VERSION
        or not re.fullmatch(r"[0-9]+", offset_text)
        or offset < 0
        or not re.fullmatch(r"[0-9a-f]{64}", generation_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", query_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", signature)
    ):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    payload = _milestone_cursor_payload(
        offset,
        generation_digest=generation_digest,
        query_digest=query_digest,
    )
    key = cursor_key if cursor_key is not None else _milestone_cursor_key()
    expected_signature = hmac.new(key, payload, sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    return offset, generation_digest, query_digest


def _change_query_binding(
    *,
    change_kind: str,
    window: str,
    from_date: date | None,
    to_date: date | None,
    q: str | None,
    phase: str | None,
    status: str | None,
    condition: str | None,
    limit: int,
) -> dict[str, Any]:
    """Return the normalized, endpoint-local selection behind a tape cursor."""

    return {
        "change_kind": change_kind,
        "window": window,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "q": q.casefold() if q else None,
        "phase": phase.casefold() if phase else None,
        "status": status.casefold() if status else None,
        "condition": condition.casefold() if condition else None,
        "limit": limit,
    }


def _change_cursor_key() -> bytes:
    """Return the separate HMAC key for registry-change pagination.

    This mirrors the milestone route's deployment-secret contract exactly, but
    domain separation prevents a valid cursor on either route from being used
    on the other.  The process fallback intentionally expires across restarts.
    """

    configured = os.environ.get("BIOCATALYST_CURSOR_SECRET")
    if configured is None:
        return _CHANGE_CURSOR_PROCESS_KEY
    try:
        raw = configured.encode("utf-8")
    except UnicodeEncodeError:
        raise _unavailable() from None
    if len(raw) < 32:
        raise _unavailable()
    return hmac.new(raw, _CHANGE_CURSOR_DOMAIN, sha256).digest()


def _change_cursor_payload(
    offset: int,
    *,
    generation_digest: str,
    query_digest: str,
) -> bytes:
    return ":".join(
        (
            _CHANGE_CURSOR_VERSION,
            str(offset),
            generation_digest,
            query_digest,
        )
    ).encode("ascii")


def _encode_change_cursor(
    offset: int,
    *,
    generation_id: str,
    query_binding: Mapping[str, Any],
    cursor_key: bytes | None = None,
) -> str:
    """Encode a signed, opaque cursor without query or generation disclosure."""

    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    payload = _change_cursor_payload(
        offset,
        generation_digest=_opaque_digest({"generation_id": generation_id}),
        query_digest=_opaque_digest(dict(query_binding)),
    )
    key = cursor_key if cursor_key is not None else _change_cursor_key()
    signature = hmac.new(key, payload, sha256).hexdigest()
    raw = payload + b":" + signature.encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_change_cursor(
    cursor: str | None,
    *,
    cursor_key: bytes | None = None,
) -> tuple[int, str | None, str | None]:
    """Authenticate a registry-change cursor before the projection is opened."""

    if not cursor:
        return 0, None, None
    if len(cursor) > 384 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    try:
        raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
        version, offset_text, generation_digest, query_digest, signature = raw.decode(
            "ascii"
        ).split(":")
        offset = int(offset_text)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS) from exc
    if (
        version != _CHANGE_CURSOR_VERSION
        or not re.fullmatch(r"[0-9]+", offset_text)
        or offset < 0
        or not re.fullmatch(r"[0-9a-f]{64}", generation_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", query_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", signature)
    ):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    payload = _change_cursor_payload(
        offset,
        generation_digest=generation_digest,
        query_digest=query_digest,
    )
    key = cursor_key if cursor_key is not None else _change_cursor_key()
    expected_signature = hmac.new(key, payload, sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    return offset, generation_digest, query_digest


def _change_tape_query_binding(
    *,
    nct_id: str | None,
    field_class: str,
    review_state: str,
    limit: int,
) -> dict[str, Any]:
    """Return the normalized, endpoint-local tape selection for pagination."""

    return {
        "nct_id": nct_id,
        "field_class": field_class,
        "review_state": review_state,
        "limit": limit,
    }


def _change_tape_cursor_key() -> bytes:
    """Return a domain-separated HMAC key for classified change-tape cursors."""

    configured = os.environ.get("BIOCATALYST_CURSOR_SECRET")
    if configured is None:
        return _CHANGE_TAPE_CURSOR_PROCESS_KEY
    try:
        raw = configured.encode("utf-8")
    except UnicodeEncodeError:
        raise _unavailable() from None
    if len(raw) < 32:
        raise _unavailable()
    return hmac.new(raw, _CHANGE_TAPE_CURSOR_DOMAIN, sha256).digest()


def _change_tape_cursor_payload(
    offset: int,
    *,
    generation_digest: str,
    query_digest: str,
) -> bytes:
    return ":".join(
        (
            _CHANGE_TAPE_CURSOR_VERSION,
            str(offset),
            generation_digest,
            query_digest,
        )
    ).encode("ascii")


def _encode_change_tape_cursor(
    offset: int,
    *,
    generation_id: str,
    query_binding: Mapping[str, Any],
    cursor_key: bytes | None = None,
) -> str:
    """Encode a signed cursor that contains no query or generation plaintext."""

    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    payload = _change_tape_cursor_payload(
        offset,
        generation_digest=_opaque_digest({"generation_id": generation_id}),
        query_digest=_opaque_digest(dict(query_binding)),
    )
    key = cursor_key if cursor_key is not None else _change_tape_cursor_key()
    signature = hmac.new(key, payload, sha256).hexdigest()
    raw = payload + b":" + signature.encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_change_tape_cursor(
    cursor: str | None,
    *,
    cursor_key: bytes | None = None,
) -> tuple[int, str | None, str | None]:
    """Authenticate a tape cursor before the pointer-bound projection is read."""

    if not cursor:
        return 0, None, None
    if len(cursor) > 384 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    try:
        raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
        version, offset_text, generation_digest, query_digest, signature = raw.decode(
            "ascii"
        ).split(":")
        offset = int(offset_text)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS) from exc
    if (
        version != _CHANGE_TAPE_CURSOR_VERSION
        or not re.fullmatch(r"[0-9]+", offset_text)
        or offset < 0
        or offset > _CHANGE_TAPE_MAX_CURSOR_OFFSET
        or not re.fullmatch(r"[0-9a-f]{64}", generation_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", query_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", signature)
    ):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    payload = _change_tape_cursor_payload(
        offset,
        generation_digest=generation_digest,
        query_digest=query_digest,
    )
    key = cursor_key if cursor_key is not None else _change_tape_cursor_key()
    expected_signature = hmac.new(key, payload, sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    return offset, generation_digest, query_digest


def _prospective_query_binding(
    *,
    change_kind: str,
    window: str,
    from_date: date | None,
    to_date: date | None,
    q: str | None,
    phase: str | None,
    status: str | None,
    condition: str | None,
    limit: int,
) -> dict[str, Any]:
    """Bind the normalized public selection to a prospective-feed cursor."""

    return {
        "change_kind": change_kind,
        "window": window,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "q": q.casefold() if q else None,
        "phase": phase.casefold() if phase else None,
        "status": status.casefold() if status else None,
        "condition": condition.casefold() if condition else None,
        "limit": limit,
    }


def _prospective_cursor_key() -> bytes:
    """Return an endpoint-separated HMAC key for prospective pagination."""

    configured = os.environ.get("BIOCATALYST_CURSOR_SECRET")
    if configured is None:
        return _PROSPECTIVE_CURSOR_PROCESS_KEY
    try:
        raw = configured.encode("utf-8")
    except UnicodeEncodeError:
        raise _unavailable() from None
    if len(raw) < 32:
        raise _unavailable()
    return hmac.new(raw, _PROSPECTIVE_CURSOR_DOMAIN, sha256).digest()


def _prospective_cursor_payload(
    offset: int,
    *,
    generation_digest: str,
    query_digest: str,
) -> bytes:
    return ":".join(
        (
            _PROSPECTIVE_CURSOR_VERSION,
            str(offset),
            generation_digest,
            query_digest,
        )
    ).encode("ascii")


def _encode_prospective_cursor(
    offset: int,
    *,
    generation_id: str,
    query_binding: Mapping[str, Any],
    cursor_key: bytes | None = None,
) -> str:
    """Encode a signed opaque cursor without query or generation disclosure."""

    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    payload = _prospective_cursor_payload(
        offset,
        generation_digest=_opaque_digest({"generation_id": generation_id}),
        query_digest=_opaque_digest(dict(query_binding)),
    )
    key = cursor_key if cursor_key is not None else _prospective_cursor_key()
    signature = hmac.new(key, payload, sha256).hexdigest()
    raw = payload + b":" + signature.encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_prospective_cursor(
    cursor: str | None,
    *,
    cursor_key: bytes | None = None,
) -> tuple[int, str | None, str | None]:
    """Authenticate a prospective cursor before reading any public artifact."""

    if not cursor:
        return 0, None, None
    if len(cursor) > 384 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    try:
        raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
        version, offset_text, generation_digest, query_digest, signature = raw.decode(
            "ascii"
        ).split(":")
        offset = int(offset_text)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS) from exc
    if (
        version != _PROSPECTIVE_CURSOR_VERSION
        or not re.fullmatch(r"[0-9]+", offset_text)
        or offset < 0
        or not re.fullmatch(r"[0-9a-f]{64}", generation_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", query_digest)
        or not re.fullmatch(r"[0-9a-f]{64}", signature)
    ):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    payload = _prospective_cursor_payload(
        offset,
        generation_digest=generation_digest,
        query_digest=query_digest,
    )
    key = cursor_key if cursor_key is not None else _prospective_cursor_key()
    expected_signature = hmac.new(key, payload, sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    return offset, generation_digest, query_digest


def _change_window(
    *,
    anchor: date,
    window: str,
    from_date: date | None,
    to_date: date | None,
) -> tuple[date, date, dict[str, str | None]]:
    """Resolve a retrospective, source-submission window from the committed cut."""

    if window == "all":
        return (
            from_date or date.min,
            to_date or date.max,
            {
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "anchor_date": anchor.isoformat(),
                "date_basis": "source_submitted_at",
            },
        )
    days = {"last_30d": 30, "last_90d": 90, "last_180d": 180}[window]
    try:
        start = anchor - timedelta(days=days - 1)
    except OverflowError:
        raise _unavailable() from None
    return (
        start,
        anchor,
        {
            "from_date": start.isoformat(),
            "to_date": anchor.isoformat(),
            "anchor_date": anchor.isoformat(),
            "date_basis": "source_submitted_at",
        },
    )


def _history_authority_for_tape(model: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only the closed facts-only authority envelope from a history model."""

    authority = model.get("authority")
    if not isinstance(authority, Mapping) or set(authority) != set(_AUTHORITY):
        raise _unavailable()
    if (
        authority.get("classification") != _AUTHORITY["classification"]
        or authority.get("decision_authority") is not False
        or authority.get("allowed_uses") != _AUTHORITY["allowed_uses"]
        or authority.get("forbidden_uses") != _AUTHORITY["forbidden_uses"]
    ):
        raise _unavailable()
    return {
        "classification": _AUTHORITY["classification"],
        "decision_authority": False,
        "allowed_uses": list(_AUTHORITY["allowed_uses"]),
        "forbidden_uses": list(_AUTHORITY["forbidden_uses"]),
    }


def _history_change_groups(
    model: Mapping[str, Any],
    *,
    nct_id: str,
    change_kind: str,
) -> tuple[list[dict[str, Any]], datetime, str] | None:
    """Turn one complete, validated history model into bounded tape groups.

    ``_history_for_api`` is deliberately reused before grouping: its recursive
    public-value and URL sanitization ceiling applies equally to the detail view
    and this new feed.  The tape adds only temporal and relational validation
    needed to bind a change to its after-version's source submission date.
    """

    if model.get("nct_id") != nct_id or model.get("source_name") != "ClinicalTrials.gov":
        raise _unavailable()
    available = model.get("available")
    if available is False:
        if model.get("coverage_class") != "unavailable":
            raise _unavailable()
        return None
    if available is not True:
        raise _unavailable()

    history = _history_for_api(model, nct_id=nct_id)
    if (
        history.get("available") is not True
        or history.get("coverage") != "record_history_complete"
        or not isinstance(history.get("source"), Mapping)
    ):
        raise _unavailable()
    retrieved_at = _text(history.get("retrieved_at"), maximum=64)
    history_url = history["source"].get("url")
    if retrieved_at is None or not isinstance(history_url, str):
        raise _unavailable()
    try:
        retrieved_time = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except ValueError:
        raise _unavailable() from None
    if retrieved_time.tzinfo is None:
        raise _unavailable()
    retrieved_date = retrieved_time.astimezone(timezone.utc).date()
    authority = _history_authority_for_tape(model)

    versions_by_display: dict[int, tuple[date, str, str]] = {}
    versions = history.get("versions")
    if not isinstance(versions, Sequence) or isinstance(versions, (str, bytes)):
        raise _unavailable()
    for version in versions:
        if not isinstance(version, Mapping):
            raise _unavailable()
        display_version = version.get("display_version")
        submitted_at = version.get("submitted_at")
        url = version.get("url")
        if (
            not isinstance(display_version, int)
            or isinstance(display_version, bool)
            or display_version < 1
            or not isinstance(submitted_at, str)
            or not isinstance(url, str)
            or display_version in versions_by_display
        ):
            raise _unavailable()
        try:
            submitted_date = date.fromisoformat(submitted_at)
        except ValueError:
            raise _unavailable() from None
        # A source submission cannot be known before the complete history was
        # retrieved.  The endpoint-wide knowledge cutoff is resolved only
        # after every pointer-bound history artifact has been inspected because
        # B2 collection may finish after the current-record B1 cut.
        if submitted_date > retrieved_date:
            raise _unavailable()
        if url != f"https://clinicaltrials.gov/study/{nct_id}?a={display_version}&tab=history":
            raise _unavailable()
        versions_by_display[display_version] = (submitted_date, submitted_at, url)

    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    changes = history.get("changes")
    if not isinstance(changes, Sequence) or isinstance(changes, (str, bytes)):
        raise _unavailable()
    for change in changes:
        if not isinstance(change, Mapping):
            raise _unavailable()
        kind = change.get("kind")
        before_version = change.get("before_display_version")
        after_version = change.get("after_display_version")
        if (
            not isinstance(kind, str)
            or kind not in _CHANGE_KINDS
            or not isinstance(before_version, int)
            or isinstance(before_version, bool)
            or not isinstance(after_version, int)
            or isinstance(after_version, bool)
            or before_version < 1
            or after_version <= before_version
            or before_version not in versions_by_display
            or after_version not in versions_by_display
        ):
            raise _unavailable()
        grouped.setdefault((before_version, after_version), []).append(
            {
                "kind": kind,
                "before_value": _history_json_value(change.get("before_value")),
                "after_value": _history_json_value(change.get("after_value")),
            }
        )

    rendered: list[dict[str, Any]] = []
    for (before_version, after_version), group_changes in grouped.items():
        submitted_date, submitted_at, version_url = versions_by_display[after_version]
        ordered_changes = sorted(group_changes, key=lambda item: item["kind"])
        selected = (
            ordered_changes
            if change_kind == "all"
            else [item for item in ordered_changes if item["kind"] == change_kind]
        )
        if not selected:
            continue
        rendered.append(
            {
                "registry_change": {
                    "before_display_version": before_version,
                    "after_display_version": after_version,
                    "source_submitted_at": submitted_at,
                    "interpretation": "registry_record_changed",
                    "protocol_change_asserted": False,
                    "materiality_assessed": False,
                    "total_display_safe_changes": len(ordered_changes),
                    "shown_change_count": len(selected),
                    "changes": selected,
                },
                "evidence": {
                    "provider": "ClinicalTrials.gov",
                    "record_id": nct_id,
                    "version_url": version_url,
                    "history_url": history_url,
                    "retrieved_at": retrieved_at,
                    "coverage": "record_history_complete",
                },
                "authority": authority,
                "_submitted_date": submitted_date,
                "_kind_tie": tuple(item["kind"] for item in selected),
            }
        )
    return rendered, retrieved_time.astimezone(timezone.utc), retrieved_at


def _prospective_utc_time(value: object) -> tuple[datetime, str]:
    """Parse one exact ``Z``-suffixed observation instant without rewriting it."""

    if not isinstance(value, str) or not value or len(value) > 64 or not value.endswith("Z"):
        raise _unavailable()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _unavailable() from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise _unavailable()
    return parsed, value


def _prospective_current_study_url(snapshot: Mapping[str, Any], *, nct_id: str) -> str:
    """Return the only evidence URL the prospective tape may disclose."""

    attribution = snapshot.get("source_attribution")
    expected = f"https://clinicaltrials.gov/study/{nct_id}"
    if not isinstance(attribution, Mapping) or attribution.get("source_uri") != expected:
        raise _unavailable()
    return expected


def _prospective_json_value(value: object, *, depth: int = 0) -> Any:
    """Copy one display-safe prospective value using the model's public bounds.

    The prospective model is already a purpose-built public projection.  We
    therefore mirror its typed value bounds instead of substring-blocking
    ordinary clinical field names such as ``reference``.  Provenance stays out
    through the closed event and evidence envelopes below.
    """

    if depth > 6:
        raise _unavailable()
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise _unavailable()
        return value
    if isinstance(value, str):
        if len(value) > 2_000:
            raise _unavailable()
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) > 32:
            raise _unavailable()
        copied: Any = [_prospective_json_value(item, depth=depth + 1) for item in value]
    elif isinstance(value, Mapping):
        if len(value) > 32:
            raise _unavailable()
        copied = {}
        for key, nested in value.items():
            if (
                not isinstance(key, str)
                or len(key) > 128
                or _prospective_value_key_is_private(key)
            ):
                raise _unavailable()
            copied[key] = _prospective_json_value(nested, depth=depth + 1)
    else:
        raise _unavailable()
    try:
        serialized = json.dumps(
            copied,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise _unavailable() from None
    if len(serialized) > 16_384:
        raise _unavailable()
    return copied


def _prospective_model_events(
    model: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
    nct_id: str,
    change_kind: str,
) -> tuple[str, list[dict[str, Any]], datetime | None, datetime | None]:
    """Serve the closed public prospective model, never raw diff artifacts.

    The product may say a current registry record was first observed changed
    between two successful observations.  It must not invent an effective
    change time, expose private source bindings, or translate an exact JSON
    operation into a protocol, issuer, catalyst, or trading conclusion.
    """

    # B1/B2 pointer generations predate the prospective public artifact.  The
    # publisher maps only those old, validated generations to this exact small
    # placeholder.  It is an explicit coverage absence, not a malformed B4D
    # model and never a license to synthesize an event from earlier records.
    if model == {
        "available": False,
        "unavailable_reason": "baseline_not_established",
    }:
        return "unavailable", [], None, None
    if (
        model.get("contract_id") != "trial_prospective_change_read_model.v1"
        or model.get("schema_version") != "1.0.0"
        or model.get("nct_id") != nct_id
        or model.get("available") is not True
        or model.get("unavailable_reason") is not None
        or model.get("coverage_class") != "current_only"
        or model.get("coverage_method") != "prospective_api_polling"
        or model.get("interpretation") != "registry_record_changed"
        or model.get("protocol_change_asserted") is not False
        or model.get("materiality_assessed") is not False
    ):
        raise _unavailable()
    accrual_state = model.get("accrual_state")
    if accrual_state not in _PROSPECTIVE_ACCRUAL_STATES:
        raise _unavailable()
    authority = _history_authority_for_tape(model)
    coverage_epoch_id = model.get("coverage_epoch_id")
    if not isinstance(coverage_epoch_id, str) or not re.fullmatch(
        r"ctgov_coverage_[A-Za-z0-9_-]{1,240}", coverage_epoch_id
    ):
        raise _unavailable()
    coverage_started_at, _coverage_started_literal = _prospective_utc_time(
        model.get("coverage_started_at")
    )
    baseline_established_at, _baseline_established_literal = _prospective_utc_time(
        model.get("baseline_established_at")
    )
    last_observed_at, _last_observed_literal = _prospective_utc_time(
        model.get("last_observed_at")
    )
    if not coverage_started_at <= baseline_established_at <= last_observed_at:
        raise _unavailable()
    observation_count = model.get("observation_count")
    events = model.get("events")
    if (
        not isinstance(observation_count, int)
        or isinstance(observation_count, bool)
        or observation_count < 1
        or not isinstance(events, Sequence)
        or isinstance(events, (str, bytes))
        or len(events) > 2_048
    ):
        raise _unavailable()
    if accrual_state == "baseline_established" and (observation_count != 1 or events):
        raise _unavailable()
    if accrual_state == "accruing" and observation_count < 2:
        raise _unavailable()

    official_url = _prospective_current_study_url(snapshot, nct_id=nct_id)
    rendered: list[dict[str, Any]] = []
    seen_change_ids: set[str] = set()
    latest_observation = last_observed_at
    previous_upper: datetime | None = None
    for event in events:
        if not isinstance(event, Mapping) or set(event) != {
            "change_id",
            "first_observed_at",
            "observed_interval",
            "total_exact_operation_count",
            "display_change_count",
            "omitted_operation_count",
            "changes",
            "evidence",
            "interpretation",
            "protocol_change_asserted",
            "materiality_assessed",
            "authority",
        }:
            raise _unavailable()
        change_id = event.get("change_id")
        if (
            not isinstance(change_id, str)
            or not re.fullmatch(rf"prospective_change_{nct_id}_[0-9a-f]{{24}}", change_id)
            or change_id in seen_change_ids
        ):
            raise _unavailable()
        seen_change_ids.add(change_id)
        interval = event.get("observed_interval")
        if not isinstance(interval, Mapping) or set(interval) != {"after", "at_or_before"}:
            raise _unavailable()
        after_time, after_literal = _prospective_utc_time(interval.get("after"))
        observed_time, observed_literal = _prospective_utc_time(interval.get("at_or_before"))
        first_time, first_literal = _prospective_utc_time(event.get("first_observed_at"))
        if (
            after_time >= observed_time
            or first_time != observed_time
            or observed_time > last_observed_at
            or (previous_upper is not None and after_time < previous_upper)
        ):
            raise _unavailable()
        previous_upper = observed_time
        exact_count = event.get("total_exact_operation_count")
        display_count = event.get("display_change_count")
        omitted_count = event.get("omitted_operation_count")
        changes = event.get("changes")
        if (
            not isinstance(exact_count, int)
            or isinstance(exact_count, bool)
            or not isinstance(display_count, int)
            or isinstance(display_count, bool)
            or not isinstance(omitted_count, int)
            or isinstance(omitted_count, bool)
            or not 1 <= exact_count <= 1_000_000
            or not 0 <= display_count <= 128
            or not 0 <= omitted_count <= 1_000_000
            or exact_count != display_count + omitted_count
            or not isinstance(changes, Sequence)
            or isinstance(changes, (str, bytes))
            or len(changes) != display_count
        ):
            raise _unavailable()
        if (
            event.get("interpretation") != "registry_record_changed"
            or event.get("protocol_change_asserted") is not False
            or event.get("materiality_assessed") is not False
        ):
            raise _unavailable()
        evidence = event.get("evidence")
        if not isinstance(evidence, Mapping) or set(evidence) != {
            "source_name",
            "source_uri",
            "retrieved_at",
        }:
            raise _unavailable()
        evidence_time, evidence_literal = _prospective_utc_time(evidence.get("retrieved_at"))
        if (
            evidence.get("source_name") != "ClinicalTrials.gov"
            or evidence.get("source_uri") != official_url
            or evidence_time != observed_time
            or evidence_literal != observed_literal
        ):
            raise _unavailable()
        if _history_authority_for_tape(event) != authority:
            raise _unavailable()
        display_changes: list[dict[str, Any]] = []
        for change in changes:
            if not isinstance(change, Mapping) or set(change) != {
                "kind",
                "op",
                "before_state",
                "before_value",
                "after_state",
                "after_value",
            }:
                raise _unavailable()
            kind = change.get("kind")
            op = change.get("op")
            before_state = change.get("before_state")
            after_state = change.get("after_state")
            expected_states = {
                "add": ("missing", "present"),
                "remove": ("present", "missing"),
                "replace": ("present", "present"),
            }.get(op)
            if (
                kind not in _PROSPECTIVE_CHANGE_KINDS
                or expected_states is None
                or (before_state, after_state) != expected_states
                or (before_state == "missing" and change.get("before_value") is not None)
                or (after_state == "missing" and change.get("after_value") is not None)
            ):
                raise _unavailable()
            display_changes.append(
                {
                    "kind": kind,
                    "op": op,
                    "before_state": before_state,
                    "before_value": _prospective_json_value(change.get("before_value")),
                    "after_state": after_state,
                    "after_value": _prospective_json_value(change.get("after_value")),
                }
            )
        selected = (
            display_changes
            if change_kind == "all"
            else [item for item in display_changes if item["kind"] == change_kind]
        )
        # An all-omitted event remains a public prospective observation.  A
        # caller's explicit category filter is the only reason to omit it.
        if change_kind != "all" and not selected:
            continue
        rendered.append(
            {
                "trial": _public_trial(snapshot, detail=False),
                "prospective_change": {
                    "change_id": change_id,
                    "first_observed_at": first_literal,
                    "observed_interval": {
                        "after": after_literal,
                        "at_or_before": observed_literal,
                    },
                    "observation_basis": _PROSPECTIVE_OBSERVATION_BASIS,
                    "interpretation": "registry_record_changed",
                    "protocol_change_asserted": False,
                    "materiality_assessed": False,
                    "total_exact_operation_count": exact_count,
                    "display_change_count": display_count,
                    "omitted_operation_count": omitted_count,
                    # ``change_kind`` selects matching events; it must not
                    # rewrite a selected event's immutable exact/display/
                    # omitted count contract or return a partial `changes`
                    # array under the original display_change_count.
                    "changes": display_changes,
                },
                "evidence": {
                    "provider": "ClinicalTrials.gov",
                    "record_id": nct_id,
                    "url": official_url,
                    "retrieved_at": evidence_literal,
                    "coverage": "current_only",
                },
                "authority": authority,
                "_observed_time": observed_time,
                "_sort": (
                    -observed_time.toordinal(),
                    -(
                        observed_time.hour * 3_600_000_000
                        + observed_time.minute * 60_000_000
                        + observed_time.second * 1_000_000
                        + observed_time.microsecond
                    ),
                    nct_id,
                    change_id,
                ),
            }
        )
    return (
        "pre_baseline" if accrual_state == "baseline_established" else "active",
        rendered,
        latest_observation,
        coverage_started_at,
    )


def _prospective_window(
    *,
    anchor: datetime,
    window: str,
    from_date: date | None,
    to_date: date | None,
) -> tuple[date, date, dict[str, str | None]]:
    """Resolve inclusive UTC civil windows from observation upper bounds."""

    anchor_date = anchor.date()
    if window == "all":
        return (
            from_date or date.min,
            to_date or date.max,
            {
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "anchor_at": anchor.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "anchor_date": anchor_date.isoformat(),
                "date_basis": "observation_at_or_before_utc",
            },
        )
    days = {"last_30d": 30, "last_90d": 90, "last_180d": 180}[window]
    try:
        start = anchor_date - timedelta(days=days - 1)
    except OverflowError:
        raise _unavailable() from None
    return (
        start,
        anchor_date,
        {
            "from_date": start.isoformat(),
            "to_date": anchor_date.isoformat(),
            "anchor_at": anchor.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "anchor_date": anchor_date.isoformat(),
            "date_basis": "observation_at_or_before_utc",
        },
    )


def _milestone_window(
    *,
    projection: Any,
    window: str,
    from_date: date | None,
    to_date: date | None,
) -> tuple[date, date, dict[str, str | None]]:
    """Resolve a stable civil-date range against the pointer-bound generation."""

    if window == "all":
        return (
            from_date or date.min,
            to_date or date.max,
            {
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "anchor_date": None,
            },
        )
    anchor = _generation_as_of_date(projection)
    days = {"next_30d": 30, "next_90d": 90, "next_180d": 180}[window]
    # The anchor date is day one, so this is exactly N inclusive civil days.
    try:
        end = anchor + timedelta(days=days - 1)
    except OverflowError:
        raise _unavailable() from None
    return (
        anchor,
        end,
        {
            "from_date": anchor.isoformat(),
            "to_date": end.isoformat(),
            "anchor_date": anchor.isoformat(),
        },
    )


def _matches_trial_filters(
    row: Mapping[str, Any],
    *,
    query: str | None,
    phase: str | None,
    status: str | None,
    condition: str | None,
) -> bool:
    """Apply the existing public trial filters without inferring omitted facts."""

    if query:
        sponsor = row.get("sponsor") or {}
        haystack = " ".join(
            [
                str(row.get("nct_id") or ""),
                str(row.get("title") or ""),
                str(row.get("brief_title") or ""),
                str(sponsor.get("name") or ""),
                *row.get("conditions", []),
            ]
        ).casefold()
        if query not in haystack:
            return False
    if phase and phase not in {str(item).casefold() for item in row["phases"]}:
        return False
    if status and status != str(row.get("status") or "").casefold():
        return False
    return not condition or any(condition in str(item).casefold() for item in row["conditions"])


def _public_milestone_evidence(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    attribution = snapshot.get("source_attribution")
    if not isinstance(attribution, Mapping):
        raise _unavailable()
    return {
        "provider": "ClinicalTrials.gov",
        "record_id": snapshot["nct_id"],
        "url": _text(attribution.get("source_uri"), maximum=2000),
        "coverage": _text(snapshot.get("coverage_class"), maximum=80),
    }


def _meta(projection: Any, health: Mapping[str, Any]) -> dict[str, Any]:
    generation = projection.generation
    return {
        "schema_version": "biocatalyst_api.v1",
        "as_of": generation.last_success_at,
        "source": {
            "name": "ClinicalTrials.gov",
            "dataset_timestamp_raw": generation.source_dataset_timestamp_raw,
        },
        "health": {
            "state": health.get("state"),
            "last_attempt_at": health.get("last_attempt_at"),
            "last_success_at": health.get("last_success_at"),
            "last_error_code": health.get("last_error_code"),
        },
        "coverage": {
            "class": "current_only",
            "configured": generation.configured_nct_count,
            "observed": generation.observed_nct_count,
        },
        "authority": dict(_AUTHORITY),
    }


@router.get("/api/biocatalyst/v1/health")
def health(_user: dict = Depends(require_site_full_user)) -> JSONResponse:
    projection, operational = _read_bundle()
    return _response(_meta(projection, operational))


@router.get("/api/biocatalyst/v1/trials")
def trials(
    q: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    condition: str | None = None,
    sort: str = "updated_desc",
    cursor: str | None = None,
    limit: str = "100",
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    q = _query_text(q, name="query", maximum=100)
    phase = _query_text(phase, name="phase", maximum=40)
    status = _query_text(status, name="status", maximum=40)
    condition = _query_text(condition, name="condition", maximum=100)
    if sort not in {"updated_desc", "completion_asc", "nct"}:
        raise HTTPException(
            status_code=400,
            detail="invalid sort",
            headers=_PRIVATE_HEADERS,
        )
    page_limit = _query_limit(limit)
    projection, operational = _read_bundle()
    query = q.casefold().strip() if q else None
    phase_value = phase.casefold().strip() if phase else None
    status_value = status.casefold().strip() if status else None
    condition_value = condition.casefold().strip() if condition else None
    rows: list[dict[str, Any]] = []
    for snapshot in projection.trials:
        row = _public_trial(snapshot, detail=False)
        if query:
            sponsor = row.get("sponsor") or {}
            haystack = " ".join(
                [
                    str(row.get("nct_id") or ""),
                    str(row.get("title") or ""),
                    str(row.get("brief_title") or ""),
                    str(sponsor.get("name") or ""),
                    *row.get("conditions", []),
                ]
            ).casefold()
            if query not in haystack:
                continue
        if phase_value and phase_value not in {str(item).casefold() for item in row["phases"]}:
            continue
        if status_value and status_value != str(row.get("status") or "").casefold():
            continue
        if condition_value and not any(
            condition_value in str(item).casefold() for item in row["conditions"]
        ):
            continue
        rows.append(row)
    if sort == "nct":
        rows.sort(key=lambda item: item["nct_id"])
    elif sort == "completion_asc":
        rows.sort(
            key=lambda item: (
                str(((item.get("dates") or {}).get("primary_completion") or {}).get("date") or "9999-12-31"),
                item["nct_id"],
            )
        )
    else:
        rows.sort(key=lambda item: (str(item.get("updated_at") or ""), item["nct_id"]), reverse=True)
    offset = _decode_cursor(cursor)
    total = len(rows)
    page = rows[offset : offset + page_limit]
    next_offset = offset + len(page)
    payload = _meta(projection, operational)
    payload.update(
        {
            "query": {
                "q": q,
                "phase": phase,
                "status": status,
                "condition": condition,
                "sort": sort,
            },
            "pagination": {
                "limit": page_limit,
                "total": total,
                "next_cursor": _encode_cursor(next_offset) if next_offset < total else None,
            },
            "trials": page,
        }
    )
    return _response(payload)


def _resolve_trial_peer_set_payload(
    payload: Any,
    *,
    user: Mapping[str, Any],
) -> JSONResponse:
    """Pure payload resolver for an already-authenticated peer-set request."""

    cohort_nct_ids, page_limit, cursor = _resolve_peer_set_payload(payload)
    query_binding = _peer_set_query_binding(
        cohort_nct_ids=cohort_nct_ids,
        page_limit=page_limit,
        user=user,
    )
    offset, cursor_generation_digest, cursor_query_digest = _decode_peer_set_cursor(
        cursor
    )
    expected_query_digest = _opaque_digest(query_binding)
    if cursor_query_digest is not None and not hmac.compare_digest(
        cursor_query_digest, expected_query_digest
    ):
        raise HTTPException(
            status_code=400,
            detail="cursor query mismatch",
            headers=_PRIVATE_HEADERS,
        )
    projection, _operational = _read_bundle()
    generation = getattr(projection, "generation", None)
    generation_id = getattr(generation, "generation_id", None)
    generation_schema = getattr(generation, "schema_version", None)
    protocols_by_nct = getattr(projection, "protocols_by_nct", None)
    history_models_by_nct = getattr(projection, "history_models_by_nct", None)
    if (
        not isinstance(generation_id, str)
        or generation_schema not in {"1.4.0", "1.5.0", "1.6.0", "1.7.0"}
        or not isinstance(protocols_by_nct, Mapping)
        or not isinstance(history_models_by_nct, Mapping)
    ):
        raise _unavailable()
    expected_generation_digest = _opaque_digest({"generation_id": generation_id})
    if (
        cursor_generation_digest is not None
        and not hmac.compare_digest(
            cursor_generation_digest, expected_generation_digest
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="trial data changed; restart pagination",
            headers=_PRIVATE_HEADERS,
        )
    covered_count = sum(1 for nct_id in cohort_nct_ids if nct_id in protocols_by_nct)
    next_offset = offset + min(page_limit, max(0, covered_count - offset))
    next_cursor = (
        _encode_peer_set_cursor(
            next_offset,
            generation_id=generation_id,
            query_binding=query_binding,
        )
        if next_offset < covered_count
        else None
    )
    try:
        from engine.biocatalyst.peer_matrix import (  # noqa: PLC0415
            TrialPeerSetError,
            build_trial_peer_set,
        )

        response_payload = build_trial_peer_set(
            cohort_nct_ids=cohort_nct_ids,
            protocols_by_nct=protocols_by_nct,
            history_models_by_nct=history_models_by_nct,
            as_of=_generation_as_of_time(projection).isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            page_limit=page_limit,
            offset=offset,
            next_cursor=next_cursor,
        )
    except TrialPeerSetError as exc:
        log.warning("BioCatalyst protocol peer projection unavailable (%s)", exc)
        raise _unavailable() from None
    return _response(response_payload)


@router.post("/api/biocatalyst/v1/trial-peer-sets:resolve")
async def resolve_trial_peer_set(
    request: Request,
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    """Resolve an explicit NCT cohort into a facts-only protocol matrix.

    ``nct_ids`` are caller-supplied identifiers, not a retrieved, inferred, or
    ranked cohort.  The route reads only pointer-bound protocol artifacts
    written by the worker; it has no private-source or identity-plane access.
    """

    payload = await _read_peer_set_payload(request)
    return _resolve_trial_peer_set_payload(payload, user=_user)


@router.get("/api/biocatalyst/v1/trials/milestones")
def trial_milestones(
    milestone_kind: str = "primary_completion",
    window: str = "next_90d",
    from_date: str | None = None,
    to_date: str | None = None,
    q: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    condition: str | None = None,
    cursor: str | None = None,
    limit: str = "50",
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    """List factual registry date milestones from the committed trial cut.

    This monitor is deliberately not a catalyst calendar: it neither infers an
    event timing nor treats a registry date as an approval, outcome, or market
    signal.  The single selected source field is returned at its original
    precision, with partial dates included only when their whole interval is
    inside the requested civil-date window.
    """

    q = _query_text(q, name="query", maximum=100)
    phase = _query_text(phase, name="phase", maximum=40)
    status = _query_text(status, name="status", maximum=40)
    condition = _query_text(condition, name="condition", maximum=100)
    if milestone_kind not in _MILESTONE_KINDS:
        raise HTTPException(
            status_code=400,
            detail="invalid milestone_kind",
            headers=_PRIVATE_HEADERS,
        )
    if window not in _MILESTONE_WINDOWS:
        raise HTTPException(status_code=400, detail="invalid window", headers=_PRIVATE_HEADERS)
    parsed_from = _query_iso_date(from_date, name="from_date")
    parsed_to = _query_iso_date(to_date, name="to_date")
    if window != "all" and (parsed_from is not None or parsed_to is not None):
        raise HTTPException(
            status_code=400,
            detail="from_date and to_date require window=all",
            headers=_PRIVATE_HEADERS,
        )
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise HTTPException(status_code=400, detail="invalid date range", headers=_PRIVATE_HEADERS)
    page_limit = _query_limit(limit)

    query = q.casefold() if q else None
    phase_value = phase.casefold() if phase else None
    status_value = status.casefold() if status else None
    condition_value = condition.casefold() if condition else None
    query_binding = _milestone_query_binding(
        milestone_kind=milestone_kind,
        window=window,
        from_date=parsed_from,
        to_date=parsed_to,
        q=query,
        phase=phase_value,
        status=status_value,
        condition=condition_value,
        limit=page_limit,
    )
    cursor_key = _milestone_cursor_key()
    offset, cursor_generation_digest, cursor_query_digest = _decode_milestone_cursor(
        cursor,
        cursor_key=cursor_key,
    )
    expected_query_digest = _opaque_digest(query_binding)
    if cursor_query_digest is not None and not hmac.compare_digest(
        cursor_query_digest,
        expected_query_digest,
    ):
        raise HTTPException(
            status_code=400,
            detail="cursor query mismatch",
            headers=_PRIVATE_HEADERS,
        )

    projection, operational = _read_bundle()
    generation_id = getattr(projection.generation, "generation_id", None)
    if not isinstance(generation_id, str) or not generation_id:
        raise _unavailable()
    if cursor_generation_digest is not None and not hmac.compare_digest(
        cursor_generation_digest,
        _opaque_digest({"generation_id": generation_id}),
    ):
        # Do not expose which generation changed; callers can restart from the
        # current pointer-bound cut using the same normalized selection.
        raise HTTPException(
            status_code=409,
            detail="trial data changed; restart pagination",
            headers=_PRIVATE_HEADERS,
        )
    range_start, range_end, effective_window = _milestone_window(
        projection=projection,
        window=window,
        from_date=parsed_from,
        to_date=parsed_to,
    )

    milestones: list[dict[str, Any]] = []
    for snapshot in projection.trials:
        trial = _public_trial(snapshot, detail=False)
        if not _matches_trial_filters(
            trial,
            query=query,
            phase=phase_value,
            status=status_value,
            condition=condition_value,
        ):
            continue
        date_value = (trial.get("dates") or {}).get(milestone_kind)
        if not isinstance(date_value, Mapping):
            continue
        interval = _milestone_date_interval(date_value.get("date"))
        if interval is None:
            # A malformed source-shaped date is not a valid registry fact for
            # calendar display.  Omit it rather than inventing a precision.
            continue
        interval_start, interval_end, precision = interval
        if interval_start < range_start or interval_end > range_end:
            continue
        milestones.append(
            {
                "trial": trial,
                "registry_milestone": {
                    "kind": milestone_kind,
                    "date": date_value["date"],
                    "type": _milestone_type(date_value.get("type")),
                    "precision": precision,
                },
                "evidence": _public_milestone_evidence(snapshot),
                "_sort": (interval_start, interval_end, trial["nct_id"]),
            }
        )
    milestones.sort(key=lambda item: item["_sort"])
    total = len(milestones)
    page = milestones[offset : offset + page_limit]
    for item in page:
        item.pop("_sort", None)
    next_offset = offset + len(page)
    payload = _meta(projection, operational)
    payload.update(
        {
            "query": {
                "milestone_kind": milestone_kind,
                "window": window,
                "from_date": parsed_from.isoformat() if parsed_from else None,
                "to_date": parsed_to.isoformat() if parsed_to else None,
                "q": q,
                "phase": phase,
                "status": status,
                "condition": condition,
            },
            "effective_window": effective_window,
            "pagination": {
                "limit": page_limit,
                "total": total,
                "next_cursor": (
                    _encode_milestone_cursor(
                        next_offset,
                        generation_id=generation_id,
                        query_binding=query_binding,
                        cursor_key=cursor_key,
                    )
                    if next_offset < total
                    else None
                ),
            },
            "milestones": page,
        }
    )
    return _response(payload)


@router.get("/api/biocatalyst/v1/trials/changes")
def trial_registry_changes(
    change_kind: str = "all",
    window: str = "last_90d",
    from_date: str | None = None,
    to_date: str | None = None,
    q: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    condition: str | None = None,
    cursor: str | None = None,
    limit: str = "50",
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    """List exact ClinicalTrials.gov record-history updates from the committed cut.

    A tape row says only that a registry record field changed between two
    displayed history versions.  It does not establish a protocol amendment,
    clinical significance, outcome, catalyst, issuer attribution, or trade
    conclusion.  Current-trial filters intentionally select against the
    pointer-bound current public record, never a historical version.
    """

    q = _query_text(q, name="query", maximum=100)
    phase = _query_text(phase, name="phase", maximum=40)
    status = _query_text(status, name="status", maximum=40)
    condition = _query_text(condition, name="condition", maximum=100)
    if change_kind != "all" and change_kind not in _CHANGE_KINDS:
        raise HTTPException(
            status_code=400,
            detail="invalid change_kind",
            headers=_PRIVATE_HEADERS,
        )
    if window not in _CHANGE_WINDOWS:
        raise HTTPException(status_code=400, detail="invalid window", headers=_PRIVATE_HEADERS)
    parsed_from = _query_iso_date(from_date, name="from_date")
    parsed_to = _query_iso_date(to_date, name="to_date")
    if window != "all" and (parsed_from is not None or parsed_to is not None):
        raise HTTPException(
            status_code=400,
            detail="from_date and to_date require window=all",
            headers=_PRIVATE_HEADERS,
        )
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise HTTPException(status_code=400, detail="invalid date range", headers=_PRIVATE_HEADERS)
    page_limit = _query_limit(limit)

    query = q.casefold() if q else None
    phase_value = phase.casefold() if phase else None
    status_value = status.casefold() if status else None
    condition_value = condition.casefold() if condition else None
    query_binding = _change_query_binding(
        change_kind=change_kind,
        window=window,
        from_date=parsed_from,
        to_date=parsed_to,
        q=query,
        phase=phase_value,
        status=status_value,
        condition=condition_value,
        limit=page_limit,
    )
    # Authenticate syntax and signature, then bind the normalized query before
    # reading a pointer-bound projection.  A forged or reused cursor must not
    # become a disk-read oracle.
    cursor_key = _change_cursor_key()
    offset, cursor_generation_digest, cursor_query_digest = _decode_change_cursor(
        cursor,
        cursor_key=cursor_key,
    )
    expected_query_digest = _opaque_digest(query_binding)
    if cursor_query_digest is not None and not hmac.compare_digest(
        cursor_query_digest,
        expected_query_digest,
    ):
        raise HTTPException(
            status_code=400,
            detail="cursor query mismatch",
            headers=_PRIVATE_HEADERS,
        )

    projection, operational = _read_bundle()
    generation_id = getattr(projection.generation, "generation_id", None)
    if not isinstance(generation_id, str) or not generation_id:
        raise _unavailable()
    if cursor_generation_digest is not None and not hmac.compare_digest(
        cursor_generation_digest,
        _opaque_digest({"generation_id": generation_id}),
    ):
        raise HTTPException(
            status_code=409,
            detail="trial data changed; restart pagination",
            headers=_PRIVATE_HEADERS,
        )
    history_models = getattr(projection, "history_models_by_nct", None)
    trials = getattr(projection, "trials", None)
    if not isinstance(history_models, Mapping) or not isinstance(trials, Sequence):
        raise _unavailable()

    changes: list[dict[str, Any]] = []
    available_trials = 0
    unavailable_trials = 0
    seen_nct_ids: set[str] = set()
    generation_as_of = _generation_as_of_time(projection)
    history_knowledge_cutoff: tuple[datetime, str] | None = None
    for snapshot in trials:
        if not isinstance(snapshot, Mapping):
            raise _unavailable()
        nct_id = snapshot.get("nct_id")
        if not isinstance(nct_id, str) or not _NCT_ID.fullmatch(nct_id) or nct_id in seen_nct_ids:
            raise _unavailable()
        seen_nct_ids.add(nct_id)
        model = history_models.get(nct_id)
        if not isinstance(model, Mapping):
            raise _unavailable()
        trial = _public_trial(snapshot, detail=False)
        selected = _matches_trial_filters(
            trial,
            query=query,
            phase=phase_value,
            status=status_value,
            condition=condition_value,
        )
        grouped = _history_change_groups(
            model,
            nct_id=nct_id,
            change_kind=change_kind,
        )
        if grouped is None:
            if selected:
                unavailable_trials += 1
            continue
        groups, retrieved_time, retrieved_at = grouped
        if history_knowledge_cutoff is None or retrieved_time > history_knowledge_cutoff[0]:
            history_knowledge_cutoff = (retrieved_time, retrieved_at)
        if not selected:
            continue
        available_trials += 1
        if not groups:
            continue
        for group in groups:
            submitted_date = group.get("_submitted_date")
            kind_tie = group.get("_kind_tie")
            if not isinstance(submitted_date, date) or not isinstance(kind_tie, tuple):
                raise _unavailable()
            group["trial"] = trial
            group["_sort"] = (
                -submitted_date.toordinal(),
                nct_id,
                group["registry_change"]["after_display_version"],
                group["registry_change"]["before_display_version"],
                kind_tie,
            )
            changes.append(group)
    if set(history_models) != seen_nct_ids:
        # Publication binding guarantees this, but the serving adapter must not
        # silently turn a mismatched current/history projection into coverage.
        raise _unavailable()

    response_as_of = generation_as_of
    response_as_of_literal = getattr(projection.generation, "last_success_at", None)
    if not isinstance(response_as_of_literal, str):
        raise _unavailable()
    if history_knowledge_cutoff is not None and history_knowledge_cutoff[0] > response_as_of:
        response_as_of, response_as_of_literal = history_knowledge_cutoff
    range_start, range_end, effective_window = _change_window(
        anchor=response_as_of.date(),
        window=window,
        from_date=parsed_from,
        to_date=parsed_to,
    )
    changes = [
        item
        for item in changes
        if range_start <= item["_submitted_date"] <= range_end
    ]
    changes.sort(key=lambda item: item["_sort"])
    total = len(changes)
    page = changes[offset : offset + page_limit]
    for item in page:
        item.pop("_sort", None)
        item.pop("_submitted_date", None)
        item.pop("_kind_tie", None)
    next_offset = offset + len(page)
    payload = _meta(projection, operational)
    payload["as_of"] = response_as_of_literal
    payload.update(
        {
            "query": {
                "change_kind": change_kind,
                "window": window,
                "from_date": parsed_from.isoformat() if parsed_from else None,
                "to_date": parsed_to.isoformat() if parsed_to else None,
                "q": q,
                "phase": phase,
                "status": status,
                "condition": condition,
            },
            "effective_window": effective_window,
            "history_coverage": {
                "class": "record_history_complete",
                "selection_basis": "current_trial_record",
                "available_trials": available_trials,
                "unavailable_trials": unavailable_trials,
                "knowledge_cutoff": (
                    history_knowledge_cutoff[1]
                    if history_knowledge_cutoff is not None
                    else None
                ),
            },
            "pagination": {
                "limit": page_limit,
                "total": total,
                "next_cursor": (
                    _encode_change_cursor(
                        next_offset,
                        generation_id=generation_id,
                        query_binding=query_binding,
                        cursor_key=cursor_key,
                    )
                    if next_offset < total
                    else None
                ),
            },
            "changes": page,
        }
    )
    return _response(payload)


def _change_tape_value_entry(entry: Any, *, row_state: str) -> tuple[dict[str, Any], int]:
    """Revalidate one disclosed value and return it with the bytes it charges.

    The API restates the whole disclosure contract rather than trusting the
    artifact: a value is either the exact recorded canonical JSON text, an
    explicitly declared truncated prefix of it, or an explicitly unavailable
    marker with a reason.  It is never an empty string and never a guess.
    """

    if not isinstance(entry, Mapping) or set(entry) != _CHANGE_TAPE_VALUE_ENTRY_KEYS:
        raise _unavailable()
    state = entry.get("state")
    value_json = entry.get("value_json")
    byte_length = entry.get("value_byte_length")
    truncated = entry.get("value_truncated")
    reason = entry.get("unavailable_reason")
    if (
        not isinstance(byte_length, int)
        or isinstance(byte_length, bool)
        or not 0 <= byte_length <= _CHANGE_TAPE_MAX_DECLARED_VALUE_BYTE_LENGTH
        or not isinstance(truncated, bool)
    ):
        raise _unavailable()
    if row_state == "missing":
        if state != "missing":
            raise _unavailable()
    elif state not in {"present", "unavailable"}:
        raise _unavailable()
    charged = 0
    if state == "missing":
        if value_json is not None or byte_length != 0 or truncated or reason is not None:
            raise _unavailable()
    elif state == "unavailable":
        if (
            value_json is not None
            or truncated
            or reason not in _CHANGE_TAPE_VALUE_UNAVAILABLE_REASONS
        ):
            raise _unavailable()
    else:
        if not isinstance(value_json, str) or not value_json or reason is not None:
            raise _unavailable()
        charged = len(value_json.encode("utf-8"))
        if charged > _CHANGE_TAPE_MAX_VALUE_JSON_BYTES:
            raise _unavailable()
        if truncated:
            if byte_length <= _CHANGE_TAPE_MAX_VALUE_JSON_BYTES:
                raise _unavailable()
        elif byte_length != charged:
            raise _unavailable()
    return (
        {
            "state": state,
            "value_json": value_json,
            "value_byte_length": byte_length,
            "value_truncated": truncated,
            "unavailable_reason": reason,
        },
        charged,
    )


def _change_tape_expected_lineage(
    *,
    op: str,
    before_version: int,
    predecessor: tuple[int, int] | None,
) -> dict[str, Any]:
    """Recompute the declared lineage a row must carry for this chain position."""

    if predecessor is not None:
        basis = "prior_tape_row"
        predecessor_version: int | None = predecessor[0]
        predecessor_index: int | None = predecessor[1]
    elif op in {"replace", "remove"}:
        basis = "before_version_record"
        predecessor_version = before_version
        predecessor_index = None
    else:
        basis = "none"
        predecessor_version = None
        predecessor_index = None
    if op == "remove":
        relation = "clears_prior_recorded_value"
    elif basis == "none":
        relation = "no_prior_recorded_value"
    else:
        relation = "supersedes_prior_recorded_value"
    return {
        "relation": relation,
        "predecessor_basis": basis,
        "predecessor_source_version": predecessor_version,
        "predecessor_exact_operation_index": predecessor_index,
        "correction_assessed": False,
    }


def _change_tape_row_extension(
    row: Mapping[str, Any],
    *,
    last_row_by_pointer: dict[str, tuple[int, int]],
    before_version: int,
    after_version: int,
    operation_index: int,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Revalidate one row's exact values and declared correction lineage."""

    values = row.get("exact_values")
    if not isinstance(values, Mapping) or set(values) != {
        "source_pointer",
        "before",
        "after",
    }:
        raise _unavailable()
    pointer = values.get("source_pointer")
    if (
        not isinstance(pointer, str)
        or not pointer.startswith("/")
        or len(pointer.encode("utf-8")) > _CHANGE_TAPE_MAX_SOURCE_POINTER_BYTES
    ):
        raise _unavailable()
    before_entry, before_charged = _change_tape_value_entry(
        values.get("before"), row_state=row["before_state"]
    )
    after_entry, after_charged = _change_tape_value_entry(
        values.get("after"), row_state=row["after_state"]
    )
    lineage = row.get("correction_lineage")
    if not isinstance(lineage, Mapping) or set(lineage) != _CHANGE_TAPE_LINEAGE_KEYS:
        raise _unavailable()
    expected = _change_tape_expected_lineage(
        op=row["op"],
        before_version=before_version,
        predecessor=last_row_by_pointer.get(pointer),
    )
    if dict(lineage) != expected:
        raise _unavailable()
    last_row_by_pointer[pointer] = (after_version, operation_index)
    return (
        {"source_pointer": pointer, "before": before_entry, "after": after_entry},
        expected,
        before_charged + after_charged,
    )


def _change_tape_value_disclosure(model: Mapping[str, Any], *, discloses: bool) -> None:
    """Bind a tape's declared value policy to what its rows actually carry."""

    disclosure = model.get("value_disclosure")
    if disclosure is None:
        if discloses:
            raise _unavailable()
        return
    expected = dict(_CHANGE_TAPE_VALUE_DISCLOSURE_BASE)
    expected["state"] = "exact_values_present" if discloses else "exact_values_absent"
    if not isinstance(disclosure, Mapping) or dict(disclosure) != expected:
        raise _unavailable()


def _change_tape_model_rows(
    model: Mapping[str, Any],
    *,
    nct_id: str,
) -> tuple[str, str | None, list[dict[str, Any]]]:
    """Return a closed DTO row set without exposing a tape's integrity layer."""

    if model == {"available": False, "unavailable_reason": "not_materialized"}:
        return "unavailable", "not_materialized", []
    if (
        model.get("contract_id") != "trial_change_tape_read_model.v1"
        or model.get("schema_version") != "1.0.0"
        or model.get("nct_id") != nct_id
        or model.get("chronology_order")
        != "source_version_then_exact_operation_order"
        or model.get("interpretation") != "registry_record_changed"
        or model.get("protocol_change_asserted") is not False
        or model.get("materiality_assessed") is not False
        or model.get("correction_assessed") is not False
        or model.get("authority") != _CHANGE_TAPE_AUTHORITY
    ):
        raise _unavailable()
    history = model.get("history")
    prospective = model.get("prospective")
    if not isinstance(history, Mapping) or not isinstance(prospective, Mapping):
        raise _unavailable()
    history_available = history.get("available")
    history_reason = history.get("unavailable_reason")
    history_rows = history.get("rows")
    history_count = history.get("row_count")
    classification_count = history.get("classification_count")
    if (
        not isinstance(history_available, bool)
        or not isinstance(history_rows, Sequence)
        or isinstance(history_rows, (str, bytes))
        or not isinstance(history_count, int)
        or isinstance(history_count, bool)
        or not isinstance(classification_count, int)
        or isinstance(classification_count, bool)
        or not 0 <= history_count <= 512
        or not 0 <= classification_count <= 128
        or history_count != len(history_rows)
    ):
        raise _unavailable()
    # The prospective part of this model is deliberately a capability-state
    # disclosure only.  No T2b prospective row may be served until two exact
    # activation proofs are retained and replayed at publication.
    if (
        prospective.get("available") is not False
        or prospective.get("classification_count") != 0
        or prospective.get("row_count") != 0
        or prospective.get("rows") != []
        or not isinstance(prospective.get("unavailable_reason"), str)
    ):
        raise _unavailable()
    disclosing_rows = sum(
        1 for row in history_rows if isinstance(row, Mapping) and "exact_values" in row
    )
    if disclosing_rows and disclosing_rows != len(history_rows):
        raise _unavailable()
    discloses_values = bool(history_rows) and disclosing_rows == len(history_rows)
    _change_tape_value_disclosure(model, discloses=discloses_values)
    if history_available is False:
        if history_rows or history_count != 0 or classification_count != 0 or not isinstance(history_reason, str):
            raise _unavailable()
        return "unavailable", history_reason, []
    if history_available is not True or history_reason is not None:
        raise _unavailable()
    charged_bytes = 0
    last_row_by_pointer: dict[str, tuple[int, int]] = {}
    rendered: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_pair: tuple[int, int] | None = None
    previous_index: int | None = None
    previous_observed_time: datetime | None = None
    pair_observed_literal: str | None = None
    expected_states = {
        "add": ("missing", "present"),
        "remove": ("present", "missing"),
        "replace": ("present", "present"),
    }
    base_row_keys = {
        "field_class", "review_state", "semantic_resolution", "op", "before_state",
        "after_state", "protocol_change_asserted", "materiality_assessed",
        "correction_assessed", "source_versions", "observed_at", "exact_operation_index",
    }
    extended_row_keys = base_row_keys | {"exact_values", "correction_lineage"}
    expected_row_keys = extended_row_keys if discloses_values else base_row_keys
    for row in history_rows:
        if not isinstance(row, Mapping) or set(row) != expected_row_keys:
            raise _unavailable()
        field_class = row.get("field_class")
        review_state = row.get("review_state")
        op = row.get("op")
        exact_operation_index = row.get("exact_operation_index")
        versions = row.get("source_versions")
        observed_at = row.get("observed_at")
        if (
            field_class not in _CHANGE_TAPE_FIELD_CLASSES
            or review_state not in _CHANGE_TAPE_REVIEW_STATES
            or expected_states.get(op) != (row.get("before_state"), row.get("after_state"))
            or not isinstance(versions, Mapping)
            or set(versions) != {"before", "after"}
            or not isinstance(versions.get("before"), int)
            or isinstance(versions.get("before"), bool)
            or not isinstance(versions.get("after"), int)
            or isinstance(versions.get("after"), bool)
            or versions["before"] < 1
            or versions["after"] != versions["before"] + 1
            or not isinstance(exact_operation_index, int)
            or isinstance(exact_operation_index, bool)
            or not 0 <= exact_operation_index < 4_096
            or row.get("protocol_change_asserted") is not False
            or row.get("materiality_assessed") is not False
            or row.get("correction_assessed") is not False
        ):
            raise _unavailable()
        observed_time, observed_literal = _prospective_utc_time(observed_at)
        pair = (versions["before"], versions["after"])
        if previous_pair is not None and pair < previous_pair:
            raise _unavailable()
        same_pair = pair == previous_pair
        if same_pair and (
            previous_index is None or exact_operation_index <= previous_index
        ):
            raise _unavailable()
        if same_pair and pair_observed_literal is not None and observed_literal != pair_observed_literal:
            raise _unavailable()
        if not same_pair and previous_observed_time is not None and observed_time < previous_observed_time:
            raise _unavailable()
        previous_pair = pair
        previous_index = exact_operation_index
        previous_observed_time = observed_time
        pair_observed_literal = observed_literal
        if field_class == "endpoint_record_delta":
            if row.get("semantic_resolution") != "unresolved" or review_state != "needs_review":
                raise _unavailable()
        elif (
            row.get("semantic_resolution") != "registry_field_class_only"
            or review_state != "not_required"
        ):
            raise _unavailable()
        public_row = {
            "field_class": field_class,
            "exact_operation_index": exact_operation_index,
            "review_state": review_state,
            "semantic_resolution": row["semantic_resolution"],
            "op": op,
            "before_state": row["before_state"],
            "after_state": row["after_state"],
            "source_versions": {"before": versions["before"], "after": versions["after"]},
            "observed_at": observed_literal,
            "protocol_change_asserted": False,
            "materiality_assessed": False,
            "correction_assessed": False,
        }
        if discloses_values:
            exact_values, correction_lineage, charged = _change_tape_row_extension(
                row,
                last_row_by_pointer=last_row_by_pointer,
                before_version=versions["before"],
                after_version=versions["after"],
                operation_index=exact_operation_index,
            )
            charged_bytes += charged
            if charged_bytes > _CHANGE_TAPE_MAX_TAPE_VALUE_JSON_BYTES:
                raise _unavailable()
            public_row["exact_values"] = exact_values
            public_row["correction_lineage"] = correction_lineage
        serialized = json.dumps(
            public_row,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if serialized in seen:
            raise _unavailable()
        seen.add(serialized)
        public_row["_observed_time"] = observed_time
        rendered.append(public_row)
    if len(
        {
            (item["source_versions"]["before"], item["source_versions"]["after"])
            for item in rendered
        }
    ) != classification_count:
        raise _unavailable()
    return "available", None, rendered


@router.get("/api/biocatalyst/v1/trials/change-tape")
def trial_change_tape(
    nct_id: str | None = None,
    field_class: str = "all",
    review_state: str = "all",
    cursor: str | None = None,
    limit: str = "50",
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    """List replay-verified registry field classes from the immutable B2 tape.

    This is not an alert, catalyst, protocol-amendment, materiality, issuer,
    security, or market conclusion.  It serves only the exact T2b
    retrospective classification after its raw/private evidence has been
    replayed during worker publication.
    """

    if nct_id is not None and _NCT_ID.fullmatch(nct_id) is None:
        raise HTTPException(status_code=400, detail="invalid NCT ID", headers=_PRIVATE_HEADERS)
    if field_class != "all" and field_class not in _CHANGE_TAPE_FIELD_CLASSES:
        raise HTTPException(status_code=400, detail="invalid field_class", headers=_PRIVATE_HEADERS)
    if review_state != "all" and review_state not in _CHANGE_TAPE_REVIEW_STATES:
        raise HTTPException(status_code=400, detail="invalid review_state", headers=_PRIVATE_HEADERS)
    page_limit = _query_limit(limit)
    query_binding = _change_tape_query_binding(
        nct_id=nct_id,
        field_class=field_class,
        review_state=review_state,
        limit=page_limit,
    )
    cursor_key = _change_tape_cursor_key()
    offset, cursor_generation_digest, cursor_query_digest = _decode_change_tape_cursor(
        cursor,
        cursor_key=cursor_key,
    )
    expected_query_digest = _opaque_digest(query_binding)
    if cursor_query_digest is not None and not hmac.compare_digest(
        cursor_query_digest, expected_query_digest
    ):
        raise HTTPException(status_code=400, detail="cursor query mismatch", headers=_PRIVATE_HEADERS)
    projection, operational = _read_bundle()
    generation_id = getattr(projection.generation, "generation_id", None)
    if not isinstance(generation_id, str) or not generation_id:
        raise _unavailable()
    if cursor_generation_digest is not None and not hmac.compare_digest(
        cursor_generation_digest,
        _opaque_digest({"generation_id": generation_id}),
    ):
        raise HTTPException(
            status_code=409,
            detail="trial data changed; restart pagination",
            headers=_PRIVATE_HEADERS,
        )
    trials = getattr(projection, "trials", None)
    tapes = getattr(projection, "change_tapes_by_nct", None)
    if not isinstance(trials, Sequence) or not isinstance(tapes, Mapping):
        raise _unavailable()
    rows: list[dict[str, Any]] = []
    available_trials = 0
    unavailable_trials = 0
    unavailable_reasons: dict[str, int] = {}
    seen_nct_ids: set[str] = set()
    for snapshot in trials:
        if not isinstance(snapshot, Mapping):
            raise _unavailable()
        current_nct = snapshot.get("nct_id")
        if not isinstance(current_nct, str) or _NCT_ID.fullmatch(current_nct) is None or current_nct in seen_nct_ids:
            raise _unavailable()
        seen_nct_ids.add(current_nct)
        if nct_id is not None and current_nct != nct_id:
            continue
        tape = tapes.get(current_nct)
        if not isinstance(tape, Mapping):
            raise _unavailable()
        state, reason, tape_rows = _change_tape_model_rows(tape, nct_id=current_nct)
        if state != "available":
            unavailable_trials += 1
            if not isinstance(reason, str) or len(reason) > 96:
                raise _unavailable()
            unavailable_reasons[reason] = unavailable_reasons.get(reason, 0) + 1
            continue
        available_trials += 1
        trial = _public_trial(snapshot, detail=False)
        for row in tape_rows:
            if field_class != "all" and row["field_class"] != field_class:
                continue
            if review_state != "all" and row["review_state"] != review_state:
                continue
            rendered = {
                "trial": trial,
                "change": {key: value for key, value in row.items() if key != "_observed_time"},
                "authority": dict(_CHANGE_TAPE_AUTHORITY),
                "_sort": (
                    -row["_observed_time"].toordinal(),
                    -(
                        row["_observed_time"].hour * 3_600_000_000
                        + row["_observed_time"].minute * 60_000_000
                        + row["_observed_time"].second * 1_000_000
                        + row["_observed_time"].microsecond
                    ),
                    current_nct,
                    row["source_versions"]["after"],
                    row["exact_operation_index"],
                    row["field_class"],
                    row["op"],
                ),
            }
            rows.append(rendered)
    if set(tapes) != seen_nct_ids:
        raise _unavailable()
    rows.sort(key=lambda item: item["_sort"])
    total = len(rows)
    page = rows[offset : offset + page_limit]
    for item in page:
        item.pop("_sort", None)
    next_offset = offset + len(page)
    payload = _meta(projection, operational)
    payload.update(
        {
            "query": {
                "nct_id": nct_id,
                "field_class": field_class,
                "review_state": review_state,
            },
            "change_tape_coverage": {
                "class": "replay_verified_record_history",
                "selection_basis": "committed_trial_record",
                "available_trials": available_trials,
                "unavailable_trials": unavailable_trials,
                "unavailable_reasons": dict(sorted(unavailable_reasons.items())),
                "prospective_state": "unavailable_without_retained_activation_proofs",
            },
            "pagination": {
                "limit": page_limit,
                "total": total,
                "next_cursor": (
                    _encode_change_tape_cursor(
                        next_offset,
                        generation_id=generation_id,
                        query_binding=query_binding,
                        cursor_key=cursor_key,
                    )
                    if next_offset < total
                    else None
                ),
            },
            "change_tape": page,
        }
    )
    return _response(payload)


@router.get("/api/biocatalyst/v1/trials/prospective-changes")
def trial_prospective_changes(
    change_kind: str = "all",
    window: str = "last_90d",
    from_date: str | None = None,
    to_date: str | None = None,
    q: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    condition: str | None = None,
    cursor: str | None = None,
    limit: str = "50",
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    """List prospective registry changes first observed between successful polls.

    This is a prospective, current-record product surface.  A row is not a
    reconstruction of Registry Record History and does not establish a
    protocol amendment, clinical outcome, issuer relationship, catalyst, or
    trading conclusion.
    """

    q = _query_text(q, name="query", maximum=100)
    phase = _query_text(phase, name="phase", maximum=40)
    status = _query_text(status, name="status", maximum=40)
    condition = _query_text(condition, name="condition", maximum=100)
    if change_kind != "all" and change_kind not in _PROSPECTIVE_CHANGE_KINDS:
        raise HTTPException(
            status_code=400,
            detail="invalid change_kind",
            headers=_PRIVATE_HEADERS,
        )
    if window not in _CHANGE_WINDOWS:
        raise HTTPException(status_code=400, detail="invalid window", headers=_PRIVATE_HEADERS)
    parsed_from = _query_iso_date(from_date, name="from_date")
    parsed_to = _query_iso_date(to_date, name="to_date")
    if window != "all" and (parsed_from is not None or parsed_to is not None):
        raise HTTPException(
            status_code=400,
            detail="from_date and to_date require window=all",
            headers=_PRIVATE_HEADERS,
        )
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise HTTPException(status_code=400, detail="invalid date range", headers=_PRIVATE_HEADERS)
    page_limit = _query_limit(limit)

    query = q.casefold() if q else None
    phase_value = phase.casefold() if phase else None
    status_value = status.casefold() if status else None
    condition_value = condition.casefold() if condition else None
    query_binding = _prospective_query_binding(
        change_kind=change_kind,
        window=window,
        from_date=parsed_from,
        to_date=parsed_to,
        q=query,
        phase=phase_value,
        status=status_value,
        condition=condition_value,
        limit=page_limit,
    )
    # Authenticate all cursor syntax and its query binding before opening the
    # pointer-bound generation.  The endpoint's p1 HMAC domain is deliberately
    # independent from milestone and retrospective-history pagination.
    cursor_key = _prospective_cursor_key()
    offset, cursor_generation_digest, cursor_query_digest = _decode_prospective_cursor(
        cursor,
        cursor_key=cursor_key,
    )
    expected_query_digest = _opaque_digest(query_binding)
    if cursor_query_digest is not None and not hmac.compare_digest(
        cursor_query_digest,
        expected_query_digest,
    ):
        raise HTTPException(
            status_code=400,
            detail="cursor query mismatch",
            headers=_PRIVATE_HEADERS,
        )

    projection, operational = _read_bundle()
    generation_id = getattr(projection.generation, "generation_id", None)
    if not isinstance(generation_id, str) or not generation_id:
        raise _unavailable()
    if cursor_generation_digest is not None and not hmac.compare_digest(
        cursor_generation_digest,
        _opaque_digest({"generation_id": generation_id}),
    ):
        raise HTTPException(
            status_code=409,
            detail="trial data changed; restart pagination",
            headers=_PRIVATE_HEADERS,
        )
    trials = getattr(projection, "trials", None)
    prospective_models = getattr(projection, "prospective_models_by_nct", None)
    if not isinstance(trials, Sequence):
        raise _unavailable()
    # A pre-B4D pointer contains no prospective artifact at all.  It is still
    # a valid current-record generation, but must produce an explicit empty,
    # unavailable prospective surface rather than guessed historical rows.
    legacy_generation = prospective_models is None
    if prospective_models is not None and not isinstance(prospective_models, Mapping):
        raise _unavailable()

    prospective_changes: list[dict[str, Any]] = []
    active_trials = 0
    pre_baseline_trials = 0
    unavailable_trials = 0
    # Keep the window clock global and stable across filters.  Coverage uses a
    # separate selected clock so an excluded current trial cannot overstate
    # the freshness of the caller's actual selection.
    latest_observation: datetime | None = None
    selected_latest_observation: datetime | None = None
    earliest_coverage_started_at: datetime | None = None
    seen_nct_ids: set[str] = set()
    for snapshot in trials:
        if not isinstance(snapshot, Mapping):
            raise _unavailable()
        nct_id = snapshot.get("nct_id")
        if not isinstance(nct_id, str) or not _NCT_ID.fullmatch(nct_id) or nct_id in seen_nct_ids:
            raise _unavailable()
        seen_nct_ids.add(nct_id)
        trial = _public_trial(snapshot, detail=False)
        selected = _matches_trial_filters(
            trial,
            query=query,
            phase=phase_value,
            status=status_value,
            condition=condition_value,
        )
        if legacy_generation:
            if selected:
                unavailable_trials += 1
            continue
        model = prospective_models.get(nct_id)
        if not isinstance(model, Mapping):
            raise _unavailable()
        (
            coverage_state,
            model_rows,
            model_latest_observation,
            model_coverage_started_at,
        ) = _prospective_model_events(
            model,
            snapshot=snapshot,
            nct_id=nct_id,
            change_kind=change_kind,
        )
        if model_latest_observation is not None and (
            latest_observation is None or model_latest_observation > latest_observation
        ):
            latest_observation = model_latest_observation
        if not selected:
            continue
        if model_latest_observation is not None and (
            selected_latest_observation is None
            or model_latest_observation > selected_latest_observation
        ):
            selected_latest_observation = model_latest_observation
        if coverage_state == "active":
            active_trials += 1
        elif coverage_state == "pre_baseline":
            pre_baseline_trials += 1
        else:
            unavailable_trials += 1
        if model_coverage_started_at is not None and (
            earliest_coverage_started_at is None
            or model_coverage_started_at < earliest_coverage_started_at
        ):
            earliest_coverage_started_at = model_coverage_started_at
        prospective_changes.extend(model_rows)
    if not legacy_generation and set(prospective_models) != seen_nct_ids:
        # The public projection must bind exactly one prospective model to each
        # current NCT.  Never turn a partial or extra artifact set into an
        # apparently complete coverage count.
        raise _unavailable()

    # No prospective event may be fabricated for a pre-baseline or old
    # generation.  A normal committed-generation clock still gives the empty
    # response a deterministic user-visible window anchor.
    window_anchor = latest_observation or _generation_as_of_time(projection)
    range_start, range_end, effective_window = _prospective_window(
        anchor=window_anchor,
        window=window,
        from_date=parsed_from,
        to_date=parsed_to,
    )
    prospective_changes = [
        item
        for item in prospective_changes
        if range_start <= item["_observed_time"].date() <= range_end
    ]
    prospective_changes.sort(key=lambda item: item["_sort"])
    total = len(prospective_changes)
    page = prospective_changes[offset : offset + page_limit]
    for item in page:
        item.pop("_observed_time", None)
        item.pop("_sort", None)
    next_offset = offset + len(page)
    coverage_state = (
        "active"
        if active_trials
        else ("pre_baseline" if pre_baseline_trials else "unavailable")
    )
    payload = _meta(projection, operational)
    payload.update(
        {
            "query": {
                "change_kind": change_kind,
                "window": window,
                "from_date": parsed_from.isoformat() if parsed_from else None,
                "to_date": parsed_to.isoformat() if parsed_to else None,
                "q": q,
                "phase": phase,
                "status": status,
                "condition": condition,
            },
            "effective_window": effective_window,
            "prospective_coverage": {
                "class": "prospective_current_only",
                "selection_basis": "current_trial_record",
                "coverage_state": coverage_state,
                "coverage_started_at": (
                    earliest_coverage_started_at.isoformat(timespec="microseconds").replace(
                        "+00:00", "Z"
                    )
                    if earliest_coverage_started_at is not None
                    else None
                ),
                "last_observed_at": (
                    selected_latest_observation.isoformat(timespec="microseconds").replace(
                        "+00:00", "Z"
                    )
                    if selected_latest_observation is not None
                    else None
                ),
                "active_trials": active_trials,
                "pre_baseline_trials": pre_baseline_trials,
                "unavailable_trials": unavailable_trials,
            },
            "pagination": {
                "limit": page_limit,
                "total": total,
                "next_cursor": (
                    _encode_prospective_cursor(
                        next_offset,
                        generation_id=generation_id,
                        query_binding=query_binding,
                        cursor_key=cursor_key,
                    )
                    if next_offset < total
                    else None
                ),
            },
            "prospective_changes": page,
        }
    )
    return _response(payload)


@router.get("/api/biocatalyst/v1/trials:screen")
def trial_screen(
    sponsor: str | None = None,
    intervention: str | None = None,
    study_type: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    condition: str | None = None,
    primary_completion_from: str | None = None,
    primary_completion_to: str | None = None,
    cursor: str | None = None,
    limit: str = "50",
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    """Screen the current committed trial cut using literal source facts only.

    This route deliberately remains separate from the legacy ``/trials``
    query surface.  It performs no ontology expansion, issuer or security
    resolution, ranking, catalyst inference, forecasting, or alerting.
    """

    raw_filters = {
        "sponsor": _query_text(sponsor, name="sponsor", maximum=240),
        "intervention": _query_text(
            intervention, name="intervention", maximum=240
        ),
        "study_type": _query_text(study_type, name="study_type", maximum=80),
        "phase": _query_text(phase, name="phase", maximum=80),
        "status": _query_text(status, name="status", maximum=80),
        "condition": _query_text(condition, name="condition", maximum=240),
        "primary_completion_from": primary_completion_from,
        "primary_completion_to": primary_completion_to,
    }
    parsed_from = _query_iso_date(
        primary_completion_from,
        name="primary_completion_from",
    )
    parsed_to = _query_iso_date(
        primary_completion_to,
        name="primary_completion_to",
    )
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise HTTPException(
            status_code=400,
            detail="invalid primary completion range",
            headers=_PRIVATE_HEADERS,
        )
    raw_filters["primary_completion_from"] = (
        parsed_from.isoformat() if parsed_from is not None else None
    )
    raw_filters["primary_completion_to"] = (
        parsed_to.isoformat() if parsed_to is not None else None
    )
    page_limit = _query_limit(limit)
    TrialScreenError, canonicalize_filters, build_read_model, _build_facets = (
        _trial_screen_runtime()
    )
    try:
        filters = canonicalize_filters(raw_filters)
    except TrialScreenError:
        raise HTTPException(
            status_code=400,
            detail="invalid trial screen query",
            headers=_PRIVATE_HEADERS,
        ) from None

    query_binding = _trial_screen_query_binding(
        filters=filters,
        page_limit=page_limit,
        user=_user,
    )
    # Authenticate syntax, signature, query, and caller binding before opening
    # the pointer-bound public generation.
    cursor_key = _trial_screen_cursor_key()
    offset, cursor_generation_digest, cursor_query_digest = (
        _decode_trial_screen_cursor(cursor, cursor_key=cursor_key)
    )
    expected_query_digest = _opaque_digest(query_binding)
    if cursor_query_digest is not None and not hmac.compare_digest(
        cursor_query_digest,
        expected_query_digest,
    ):
        raise HTTPException(
            status_code=400,
            detail="cursor query mismatch",
            headers=_PRIVATE_HEADERS,
        )

    projection, _operational = _read_bundle()
    generation = getattr(projection, "generation", None)
    generation_id = getattr(generation, "generation_id", None)
    trials = getattr(projection, "trials", None)
    if not isinstance(generation_id, str) or not generation_id:
        raise _unavailable()
    expected_generation_digest = _opaque_digest({"generation_id": generation_id})
    if cursor_generation_digest is not None and not hmac.compare_digest(
        cursor_generation_digest,
        expected_generation_digest,
    ):
        raise HTTPException(
            status_code=409,
            detail="trial data changed; restart pagination",
            headers=_PRIVATE_HEADERS,
        )
    if isinstance(trials, (str, bytes)) or not isinstance(trials, Sequence):
        raise _unavailable()

    publication_context = {
        "as_of": getattr(generation, "last_success_at", None),
        "last_success_at": getattr(generation, "last_success_at", None),
        "source_dataset_timestamp_raw": getattr(
            generation, "source_dataset_timestamp_raw", None
        ),
        "configured_nct_count": getattr(
            generation, "configured_nct_count", None
        ),
        "observed_nct_count": getattr(generation, "observed_nct_count", None),
    }

    def next_cursor_factory(next_offset: int) -> str:
        return _encode_trial_screen_cursor(
            next_offset,
            generation_id=generation_id,
            query_binding=query_binding,
            cursor_key=cursor_key,
        )

    try:
        payload = build_read_model(
            trial_snapshots=trials,
            publication_context=publication_context,
            filters=filters,
            offset=offset,
            limit=page_limit,
            next_cursor_factory=next_cursor_factory,
        )
    except TrialScreenError as exc:
        log.warning("BioCatalyst trial screen projection unavailable (%s)", exc)
        raise _unavailable() from None
    return _response(payload)


@router.get("/api/biocatalyst/v1/trials:screen/facets")
def trial_screen_facets(
    request: Request,
    sponsor: str | None = None,
    intervention: str | None = None,
    study_type: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    condition: str | None = None,
    primary_completion_from: str | None = None,
    primary_completion_to: str | None = None,
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    """Return atomic source-fact facet counts for one committed trial cut.

    This is deliberately unpaginated.  It has the same literal filter grammar
    as Trial Screen, but no cursor, caller binding, or identity-bearing query
    state: one request derives one aggregate from one committed projection.
    """

    del _user  # Authentication gates this private response; facets need no binding.
    allowed_filters = {
        "sponsor",
        "intervention",
        "study_type",
        "phase",
        "status",
        "condition",
        "primary_completion_from",
        "primary_completion_to",
    }
    unknown = set(request.query_params) - allowed_filters
    duplicated = {
        name
        for name in allowed_filters
        if len(request.query_params.getlist(name)) > 1
    }
    if unknown or duplicated:
        raise HTTPException(
            status_code=400,
            detail="invalid trial screen facets query",
            headers=_PRIVATE_HEADERS,
        )
    raw_filters = {
        "sponsor": _query_text(sponsor, name="sponsor", maximum=240),
        "intervention": _query_text(
            intervention, name="intervention", maximum=240
        ),
        "study_type": _query_text(study_type, name="study_type", maximum=80),
        "phase": _query_text(phase, name="phase", maximum=80),
        "status": _query_text(status, name="status", maximum=80),
        "condition": _query_text(condition, name="condition", maximum=240),
        "primary_completion_from": primary_completion_from,
        "primary_completion_to": primary_completion_to,
    }
    parsed_from = _query_iso_date(
        primary_completion_from,
        name="primary_completion_from",
    )
    parsed_to = _query_iso_date(
        primary_completion_to,
        name="primary_completion_to",
    )
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise HTTPException(
            status_code=400,
            detail="invalid primary completion range",
            headers=_PRIVATE_HEADERS,
        )
    raw_filters["primary_completion_from"] = (
        parsed_from.isoformat() if parsed_from is not None else None
    )
    raw_filters["primary_completion_to"] = (
        parsed_to.isoformat() if parsed_to is not None else None
    )
    TrialScreenError, canonicalize_filters, _build_screen, build_facets = (
        _trial_screen_runtime()
    )
    try:
        filters = canonicalize_filters(raw_filters)
    except TrialScreenError:
        raise HTTPException(
            status_code=400,
            detail="invalid trial screen facets query",
            headers=_PRIVATE_HEADERS,
        ) from None

    # Canonicalize the whole request before opening the pointer-bound public
    # generation.  Unlike the page reader, this response is atomic and cannot
    # be replayed against a later cut, so no cursor HMAC or caller binding exists.
    projection, _operational = _read_bundle()
    try:
        generation = getattr(projection, "generation", None)
        trials = getattr(projection, "trials", None)
        if isinstance(trials, (str, bytes)) or not isinstance(trials, Sequence):
            raise TrialScreenError("trial_screen_facets_projection_invalid")
        publication_context = {
            "as_of": getattr(generation, "last_success_at", None),
            "last_success_at": getattr(generation, "last_success_at", None),
            "source_dataset_timestamp_raw": getattr(
                generation, "source_dataset_timestamp_raw", None
            ),
            "configured_nct_count": getattr(
                generation, "configured_nct_count", None
            ),
            "observed_nct_count": getattr(generation, "observed_nct_count", None),
        }
        payload = build_facets(
            trial_snapshots=trials,
            publication_context=publication_context,
            filters=filters,
        )
        if not isinstance(payload, Mapping):
            raise TrialScreenError("trial_screen_facets_payload_invalid")
        return _response(payload)
    except Exception as exc:
        log.warning(
            "BioCatalyst trial screen facets unavailable (%s)", type(exc).__name__
        )
        raise _unavailable() from None


@router.get("/api/biocatalyst/v1/trials/{nct_id}")
def trial_detail(
    nct_id: str,
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    if not _NCT_ID.fullmatch(nct_id):
        raise HTTPException(status_code=400, detail="invalid NCT ID", headers=_PRIVATE_HEADERS)
    projection, operational = _read_bundle()
    snapshot = next(
        (item for item in projection.trials if item.get("nct_id") == nct_id),
        None,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="trial not covered", headers=_PRIVATE_HEADERS)
    history_model = projection.history_models_by_nct.get(nct_id)
    if not isinstance(history_model, Mapping):
        raise _unavailable()
    payload = _meta(projection, operational)
    payload["trial"] = _public_trial(
        snapshot,
        detail=True,
        history_model=history_model,
    )
    return _response(payload)
