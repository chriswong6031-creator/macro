"""Bounded, facts-only ClinicalTrials.gov Trial Screen for BioCatalyst.

This module is intentionally a pure transform.  It accepts only validated
``trial_snapshot.v1`` mappings plus the public metadata bound by the active
publication pointer.  It does not open a generation, archive, store, queue,
or network connection and it deliberately cannot rank trials, resolve an
issuer/security, infer a catalyst, or originate a signal.

The only fuzzy-looking operation here is explicitly lexical: sponsor,
condition, and intervention filters use a normalized substring match against
the source name (and ClinicalTrials.gov ``otherNames`` aliases for an
intervention).  Every supplied filter is combined with literal AND semantics.
"""
from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from engine.sector_intelligence import (
    canonical_json_bytes,
    validate_contract,
)
from engine.sector_intelligence.contracts import (
    ContractError,
    ContractValidationError,
    ValidationIssue,
)

from .trials import TrialProjectionError, validate_trial_snapshot


CONTRACT_ID = "trial_screen_read_model.v1"
MAX_INPUT_SNAPSHOTS = 10_000
MAX_PAGE_LIMIT = 250
MAX_TEXT_LENGTH = 2_000
MAX_FACT_ITEMS = 128
MAX_INTERVENTION_ALIASES = 64
MAX_CURSOR_LENGTH = 384
MAX_ENROLLMENT = 100_000_000
MAX_SANITIZED_ROW_BYTES = 128 * 1024
MAX_SANITIZED_SCAN_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024

_DATE_LITERAL = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
_SOURCE_CLOCK = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?$"
)
_UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_NCT_ID = re.compile(r"^NCT\d{8}$")
_FILTER_FIELDS = (
    "sponsor",
    "condition",
    "intervention",
    "phase",
    "status",
    "study_type",
    "primary_completion_from",
    "primary_completion_to",
)
_TEXT_FILTER_FIELDS = frozenset(
    ("sponsor", "condition", "intervention", "phase", "status", "study_type")
)
_AUTHORITY = {
    "classification": "source_fact_screen",
    "decision_authority": False,
    "maximum_authority": "A1_EXPLAIN",
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "issuer_resolution",
        "security_resolution",
        "sponsor_resolution",
        "trial_resolution",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "neural_web_authority",
        "all_prophet_uses",
        "forecast_outcome",
        "assess_materiality",
        "deliver_alert",
        "raise_authority",
    ],
}
_CAPACITY = {
    "max_input_snapshots": MAX_INPUT_SNAPSHOTS,
    "max_page_limit": MAX_PAGE_LIMIT,
    "max_sanitized_row_bytes": MAX_SANITIZED_ROW_BYTES,
    "max_sanitized_scan_bytes": MAX_SANITIZED_SCAN_BYTES,
    "max_response_bytes": MAX_RESPONSE_BYTES,
    "overflow_behavior": "reject_no_partial_screen",
}


class TrialScreenError(ValueError):
    """A Trial Screen input or self-consistency invariant failed closed."""


def _copy(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value))
    except (ContractError, TypeError, ValueError) as exc:
        raise TrialScreenError("trial_screen_value_must_be_canonical_json") from exc


def _bounded_response_copy(value: Any) -> Any:
    try:
        encoded = canonical_json_bytes(value)
    except (ContractError, TypeError, ValueError) as exc:
        raise TrialScreenError("trial_screen_response_not_canonical_json") from exc
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise TrialScreenError("trial_screen_response_too_large")
    return json.loads(encoded)


def _bounded_text(value: Any, *, field: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) == 0 or len(value) > MAX_TEXT_LENGTH:
        raise TrialScreenError(f"trial_screen_{field}_invalid")
    return value


def _normalized_text(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TrialScreenError(f"trial_screen_{field}_invalid")
    normalized = " ".join(value.split()).casefold()
    if not normalized:
        return None
    if len(normalized) > 240:
        raise TrialScreenError(f"trial_screen_{field}_invalid")
    return normalized


def _date_interval(value: Any, *, field: str) -> tuple[str, str, str]:
    """Return a closed calendar interval without inventing day precision."""

    if not isinstance(value, str) or not _DATE_LITERAL.fullmatch(value):
        raise TrialScreenError(f"trial_screen_{field}_invalid")
    parts = value.split("-")
    try:
        year = int(parts[0])
        if len(parts) == 1:
            return (
                date(year, 1, 1).isoformat(),
                date(year, 12, 31).isoformat(),
                "year",
            )
        month = int(parts[1])
        if len(parts) == 2:
            return (
                date(year, month, 1).isoformat(),
                date(year, month, monthrange(year, month)[1]).isoformat(),
                "month",
            )
        day = int(parts[2])
        exact = date(year, month, day).isoformat()
        return exact, exact, "day"
    except ValueError as exc:
        raise TrialScreenError(f"trial_screen_{field}_invalid") from exc


def _utc_z(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _UTC_Z.fullmatch(value):
        raise TrialScreenError(f"trial_screen_{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrialScreenError(f"trial_screen_{field}_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise TrialScreenError(f"trial_screen_{field}_invalid")
    return value


def _utc_z_datetime(value: Any, *, field: str) -> datetime:
    literal = _utc_z(value, field=field)
    return datetime.fromisoformat(literal.replace("Z", "+00:00"))


def _source_clock(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SOURCE_CLOCK.fullmatch(value):
        raise TrialScreenError(f"trial_screen_{field}_invalid")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrialScreenError(f"trial_screen_{field}_invalid") from exc
    return value


def canonicalize_trial_screen_filters(filters: Mapping[str, Any] | None = None) -> dict[str, str | None]:
    """Normalize the finite public filter grammar without creating aliases.

    Text is case-folded and whitespace-collapsed before matching.  Date query
    bounds must be real day-precise calendar dates; source literals may retain
    year, month, or day precision and are expanded only as closed intervals.
    """

    if filters is None:
        raw: Mapping[str, Any] = {}
    elif isinstance(filters, Mapping):
        raw = filters
    else:
        raise TrialScreenError("trial_screen_filters_must_be_a_mapping")
    unknown = set(raw) - set(_FILTER_FIELDS)
    if unknown:
        raise TrialScreenError("trial_screen_unknown_filter")
    normalized: dict[str, str | None] = {}
    for field in _FILTER_FIELDS:
        value = raw.get(field)
        if field in _TEXT_FILTER_FIELDS:
            normalized[field] = _normalized_text(value, field=field)
            continue
        if value is None:
            normalized[field] = None
            continue
        if not isinstance(value, str):
            raise TrialScreenError(f"trial_screen_{field}_invalid")
        literal = value.strip()
        if not literal:
            normalized[field] = None
            continue
        _start, _end, precision = _date_interval(literal, field=field)
        if precision != "day":
            raise TrialScreenError(f"trial_screen_{field}_must_be_day_precise")
        normalized[field] = literal
    lower = normalized["primary_completion_from"]
    upper = normalized["primary_completion_to"]
    if lower is not None and upper is not None:
        lower_start, _, _ = _date_interval(lower, field="primary_completion_from")
        _, upper_end, _ = _date_interval(upper, field="primary_completion_to")
        if lower_start > upper_end:
            raise TrialScreenError("trial_screen_primary_completion_range_invalid")
    return normalized


def _normalize_publication_context(
    publication_context: Mapping[str, Any], *, observed_count: int
) -> dict[str, Any]:
    if not isinstance(publication_context, Mapping):
        raise TrialScreenError("trial_screen_publication_context_must_be_a_mapping")
    context = _copy(publication_context)
    if not isinstance(context, dict) or set(context) != {
        "as_of",
        "last_success_at",
        "source_dataset_timestamp_raw",
        "configured_nct_count",
        "observed_nct_count",
    }:
        raise TrialScreenError("trial_screen_publication_context_invalid")
    as_of = _utc_z(context["as_of"], field="as_of")
    last_success = _utc_z(context["last_success_at"], field="last_success_at")
    if as_of != last_success:
        raise TrialScreenError("trial_screen_publication_context_time_mismatch")
    source_timestamp = _source_clock(
        context["source_dataset_timestamp_raw"], field="source_dataset_timestamp_raw"
    )
    configured = context["configured_nct_count"]
    observed = context["observed_nct_count"]
    for value, field in ((configured, "configured_nct_count"), (observed, "observed_nct_count")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10_000_000:
            raise TrialScreenError(f"trial_screen_{field}_invalid")
    if observed > configured or observed != observed_count:
        raise TrialScreenError("trial_screen_publication_context_coverage_mismatch")
    return {
        "as_of": as_of,
        "last_success_at": last_success,
        "source_dataset_timestamp_raw": source_timestamp,
        "configured_nct_count": configured,
        "observed_nct_count": observed,
    }


def _fact(snapshot: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    facts = snapshot.get("facts")
    value = facts.get(name) if isinstance(facts, Mapping) else None
    if not isinstance(value, Mapping):
        raise TrialScreenError("trial_screen_snapshot_fact_missing")
    return value


def _string_fact(snapshot: Mapping[str, Any], name: str) -> dict[str, Any]:
    fact = _fact(snapshot, name)
    state = fact.get("state")
    if state == "observed":
        return {"state": state, "value": _bounded_text(fact.get("value"), field=name)}
    return {"state": state, "value": None}


def _string_array_fact(snapshot: Mapping[str, Any], name: str) -> dict[str, Any]:
    fact = _fact(snapshot, name)
    state = fact.get("state")
    if state != "observed":
        return {"state": state, "values": None}
    values = fact.get("value")
    if not isinstance(values, list) or len(values) > MAX_FACT_ITEMS:
        raise TrialScreenError(f"trial_screen_{name}_invalid")
    return {
        "state": state,
        "values": [_bounded_text(value, field=name) for value in values],
    }


def _sponsor_fact(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    fact = _fact(snapshot, "sponsor")
    state = fact.get("state")
    if state != "observed":
        return {"state": state, "value": None}
    value = fact.get("value")
    if not isinstance(value, Mapping):
        raise TrialScreenError("trial_screen_sponsor_invalid")
    raw_class = value.get("class")
    if raw_class is not None and (
        not isinstance(raw_class, str) or len(raw_class) > 200
    ):
        raise TrialScreenError("trial_screen_sponsor_invalid")
    return {
        "state": state,
        "value": {
            "name": _bounded_text(value.get("name"), field="sponsor"),
            "class": raw_class,
        },
    }


def _enrollment_fact(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    fact = _fact(snapshot, "enrollment")
    state = fact.get("state")
    if state != "observed":
        return {"state": state, "value": None}
    value = fact.get("value")
    if not isinstance(value, Mapping):
        raise TrialScreenError("trial_screen_enrollment_invalid")
    count = value.get("count")
    kind = value.get("type")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        or count > MAX_ENROLLMENT
        or kind not in {"ACTUAL", "ESTIMATED", "UNKNOWN", None}
    ):
        raise TrialScreenError("trial_screen_enrollment_invalid")
    return {"state": state, "value": {"count": count, "type": kind}}


def _interventions_fact(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    fact = _fact(snapshot, "interventions")
    state = fact.get("state")
    if state != "observed":
        return {"state": state, "values": None}
    raw_values = fact.get("value")
    if not isinstance(raw_values, list) or len(raw_values) > MAX_FACT_ITEMS:
        raise TrialScreenError("trial_screen_interventions_invalid")
    values: list[dict[str, Any]] = []
    for raw in raw_values:
        if not isinstance(raw, Mapping):
            raise TrialScreenError("trial_screen_interventions_invalid")
        raw_name = raw.get("name")
        if raw_name is not None and not isinstance(raw_name, str):
            raise TrialScreenError("trial_screen_interventions_invalid")
        name = _bounded_text(raw_name, field="intervention", nullable=True)
        raw_aliases = raw.get("otherNames", [])
        if raw_aliases is None:
            raw_aliases = []
        if not isinstance(raw_aliases, list) or len(raw_aliases) > MAX_INTERVENTION_ALIASES:
            raise TrialScreenError("trial_screen_interventions_invalid")
        aliases: list[str] = []
        for alias in raw_aliases:
            normalized_alias = _bounded_text(alias, field="intervention")
            if normalized_alias not in aliases:
                aliases.append(normalized_alias)
        raw_type = raw.get("type")
        if raw_type is not None and (
            not isinstance(raw_type, str) or len(raw_type) > 80
        ):
            raise TrialScreenError("trial_screen_interventions_invalid")
        # CT.gov's object can carry arm-only metadata with no searchable name.
        # Excluding that metadata is a sanitization, not an absence conclusion.
        if name is not None or aliases:
            values.append({"name": name, "aliases": aliases, "type": raw_type})
    return {"state": state, "values": values}


def _primary_completion_fact(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    fact = _fact(snapshot, "primary_completion_date")
    state = fact.get("state")
    if state != "observed":
        return {
            "state": state,
            "literal": None,
            "precision": None,
            "interval": None,
            "type": None,
        }
    value = fact.get("value")
    if not isinstance(value, Mapping):
        raise TrialScreenError("trial_screen_primary_completion_invalid")
    literal = _bounded_text(value.get("date"), field="primary_completion_date")
    start, end, precision = _date_interval(literal, field="primary_completion_date")
    kind = value.get("type")
    if kind not in {"ACTUAL", "ESTIMATED", "UNKNOWN", None}:
        raise TrialScreenError("trial_screen_primary_completion_invalid")
    return {
        "state": state,
        "literal": literal,
        "precision": precision,
        "interval": {"start": start, "end": end},
        "type": kind,
    }


def _screen_row(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    nct_id = snapshot.get("nct_id")
    if not isinstance(nct_id, str) or not _NCT_ID.fullmatch(nct_id):
        raise TrialScreenError("trial_screen_snapshot_nct_id_invalid")
    attribution = snapshot.get("source_attribution")
    if not isinstance(attribution, Mapping):
        raise TrialScreenError("trial_screen_snapshot_attribution_invalid")
    url = attribution.get("source_uri")
    if not isinstance(url, str) or url != f"https://clinicaltrials.gov/study/{nct_id}":
        raise TrialScreenError("trial_screen_snapshot_attribution_invalid")
    retrieved_at = _utc_z(snapshot.get("retrieved_at"), field="retrieved_at")
    return {
        "nct_id": nct_id,
        "brief_title": _string_fact(snapshot, "brief_title"),
        "official_title": _string_fact(snapshot, "official_title"),
        "overall_status": _string_fact(snapshot, "overall_status"),
        "study_type": _string_fact(snapshot, "study_type"),
        "phases": _string_array_fact(snapshot, "phases"),
        "sponsor": _sponsor_fact(snapshot),
        "enrollment": _enrollment_fact(snapshot),
        "conditions": _string_array_fact(snapshot, "conditions"),
        "interventions": _interventions_fact(snapshot),
        "primary_completion": _primary_completion_fact(snapshot),
        "source": {
            "url": url,
            "last_update_posted_at": attribution.get("source_last_update_posted_at"),
            "retrieved_at": retrieved_at,
        },
    }


def _contains(haystack: Any, needle: str) -> bool:
    return isinstance(haystack, str) and needle in " ".join(haystack.split()).casefold()


def _matches(row: Mapping[str, Any], query: Mapping[str, str | None]) -> bool:
    sponsor = query["sponsor"]
    if sponsor is not None:
        sponsor_value = row["sponsor"]["value"]
        if not isinstance(sponsor_value, Mapping) or not _contains(sponsor_value.get("name"), sponsor):
            return False
    condition = query["condition"]
    if condition is not None:
        values = row["conditions"]["values"]
        if not isinstance(values, list) or not any(_contains(value, condition) for value in values):
            return False
    intervention = query["intervention"]
    if intervention is not None:
        values = row["interventions"]["values"]
        if not isinstance(values, list) or not any(
            _contains(value.get("name"), intervention)
            or any(_contains(alias, intervention) for alias in value.get("aliases", []))
            for value in values
            if isinstance(value, Mapping)
        ):
            return False
    phase = query["phase"]
    if phase is not None:
        values = row["phases"]["values"]
        if not isinstance(values, list) or phase not in {
            " ".join(value.split()).casefold() for value in values
        }:
            return False
    status = query["status"]
    if status is not None:
        value = row["overall_status"]["value"]
        if not isinstance(value, str) or " ".join(value.split()).casefold() != status:
            return False
    study_type = query["study_type"]
    if study_type is not None:
        value = row["study_type"]["value"]
        if not isinstance(value, str) or " ".join(value.split()).casefold() != study_type:
            return False
    lower = query["primary_completion_from"]
    upper = query["primary_completion_to"]
    if lower is not None or upper is not None:
        interval = row["primary_completion"]["interval"]
        if not isinstance(interval, Mapping):
            return False
        start = interval.get("start")
        end = interval.get("end")
        if not isinstance(start, str) or not isinstance(end, str):
            return False
        if lower is not None:
            lower_start, _, _ = _date_interval(lower, field="primary_completion_from")
            if start < lower_start:
                return False
        if upper is not None:
            _, upper_end, _ = _date_interval(upper, field="primary_completion_to")
            if end > upper_end:
                return False
    return True


def _row_order(row: Mapping[str, Any]) -> tuple[int, str, str, str]:
    interval = row.get("primary_completion", {}).get("interval")
    if isinstance(interval, Mapping):
        start = interval.get("start")
        end = interval.get("end")
        if isinstance(start, str) and isinstance(end, str):
            return (0, start, end, str(row["nct_id"]))
    return (1, "", "", str(row["nct_id"]))


def _validated_snapshots(trial_snapshots: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(trial_snapshots, (str, bytes)) or not isinstance(trial_snapshots, Sequence):
        raise TrialScreenError("trial_screen_snapshots_must_be_a_sequence")
    if len(trial_snapshots) > MAX_INPUT_SNAPSHOTS:
        raise TrialScreenError("trial_screen_input_snapshot_limit_exceeded")
    snapshots: list[dict[str, Any]] = []
    nct_ids: set[str] = set()
    for snapshot in trial_snapshots:
        try:
            normalized = validate_trial_snapshot(snapshot)
        except TrialProjectionError as exc:
            raise TrialScreenError("trial_screen_snapshot_invalid") from exc
        nct_id = normalized["nct_id"]
        if nct_id in nct_ids:
            raise TrialScreenError("trial_screen_duplicate_nct_id")
        nct_ids.add(nct_id)
        snapshots.append(normalized)
    return snapshots


def _validate_publication_binding(
    snapshots: Sequence[Mapping[str, Any]], context: Mapping[str, Any]
) -> None:
    """Bind every current snapshot to the exact committed source cut and clock."""

    as_of = _utc_z_datetime(context.get("as_of"), field="as_of")
    source_timestamp = context.get("source_dataset_timestamp_raw")
    for snapshot in snapshots:
        attribution = snapshot.get("source_attribution")
        if (
            not isinstance(attribution, Mapping)
            or attribution.get("source_processed_at_raw") != source_timestamp
        ):
            raise TrialScreenError("trial_screen_publication_source_cut_mismatch")
        retrieved_at = _utc_z_datetime(
            snapshot.get("retrieved_at"), field="retrieved_at"
        )
        if retrieved_at > as_of:
            raise TrialScreenError("trial_screen_publication_clock_mismatch")


def _build_model(
    *,
    trial_snapshots: Sequence[Mapping[str, Any]],
    publication_context: Mapping[str, Any],
    filters: Mapping[str, Any] | None,
    offset: int,
    limit: int,
    next_cursor_factory: Callable[[int], str] | None,
) -> dict[str, Any]:
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0 or offset > MAX_INPUT_SNAPSHOTS:
        raise TrialScreenError("trial_screen_offset_invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_LIMIT:
        raise TrialScreenError("trial_screen_limit_invalid")
    snapshots = _validated_snapshots(trial_snapshots)
    context = _normalize_publication_context(
        publication_context, observed_count=len(snapshots)
    )
    _validate_publication_binding(snapshots, context)
    query_filters = canonicalize_trial_screen_filters(filters)
    matched: list[dict[str, Any]] = []
    sanitized_scan_bytes = 0
    for snapshot in snapshots:
        row = _screen_row(snapshot)
        try:
            row_bytes = len(canonical_json_bytes(row))
        except (ContractError, TypeError, ValueError) as exc:
            raise TrialScreenError("trial_screen_row_not_canonical_json") from exc
        if row_bytes > MAX_SANITIZED_ROW_BYTES:
            raise TrialScreenError("trial_screen_row_too_large")
        sanitized_scan_bytes += row_bytes
        if sanitized_scan_bytes > MAX_SANITIZED_SCAN_BYTES:
            raise TrialScreenError("trial_screen_sanitized_scan_too_large")
        if _matches(row, query_filters):
            matched.append(row)
    matched.sort(key=_row_order)
    total = len(matched)
    if offset > total:
        raise TrialScreenError("trial_screen_offset_out_of_range")
    page = matched[offset : offset + limit]
    next_offset = offset + len(page)
    next_cursor: str | None = None
    if next_offset < total:
        if next_cursor_factory is None:
            raise TrialScreenError("trial_screen_next_cursor_factory_required")
        try:
            candidate_cursor = next_cursor_factory(next_offset)
        except Exception as exc:  # The caller's signer must fail closed too.
            raise TrialScreenError("trial_screen_next_cursor_factory_failed") from exc
        if (
            not isinstance(candidate_cursor, str)
            or not candidate_cursor
            or len(candidate_cursor) > MAX_CURSOR_LENGTH
        ):
            raise TrialScreenError("trial_screen_next_cursor_invalid")
        next_cursor = candidate_cursor
    payload: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "schema_version": "1.0.0",
        "as_of": context["as_of"],
        "query": {
            **query_filters,
            "filter_composition": "literal_and",
            "lexical_matching": "sponsor_condition_intervention_name_or_other_names_normalized_substring",
            "exact_matching": "phase_status_study_type_normalized_exact",
            "primary_completion_matching": "full_interval_containment",
        },
        "source": {
            "name": "ClinicalTrials.gov",
            "dataset_timestamp_raw": context["source_dataset_timestamp_raw"],
        },
        "coverage": {
            "class": "current_only",
            "configured": context["configured_nct_count"],
            "observed": context["observed_nct_count"],
            "matched": total,
        },
        "sort_order": "primary_completion_interval_ascending_then_nct_id",
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "returned": len(page),
            "next_cursor": next_cursor,
        },
        "row_count": len(page),
        "rows": page,
        "authority": _copy(_AUTHORITY),
        "capacity": _copy(_CAPACITY),
    }
    try:
        if len(canonical_json_bytes(payload)) > MAX_RESPONSE_BYTES:
            raise TrialScreenError("trial_screen_response_too_large")
    except TrialScreenError:
        raise
    except (ContractError, TypeError, ValueError) as exc:
        raise TrialScreenError("trial_screen_response_not_canonical_json") from exc
    return payload


def build_trial_screen_read_model(
    *,
    trial_snapshots: Sequence[Mapping[str, Any]],
    publication_context: Mapping[str, Any],
    filters: Mapping[str, Any] | None = None,
    offset: int = 0,
    limit: int = 50,
    next_cursor_factory: Callable[[int], str] | None = None,
) -> dict[str, Any]:
    """Build one deterministic screen page from current source facts only.

    ``next_cursor_factory`` is deliberately injected by the authenticated
    serving boundary.  This pure engine sees only its opaque output and never
    handles a generation ID, caller identity, HMAC secret, or cursor payload.
    """

    payload = _build_model(
        trial_snapshots=trial_snapshots,
        publication_context=publication_context,
        filters=filters,
        offset=offset,
        limit=limit,
        next_cursor_factory=next_cursor_factory,
    )
    try:
        validate_contract(CONTRACT_ID, payload)
    except ContractValidationError as exc:
        raise TrialScreenError("invalid_trial_screen_read_model") from exc
    return _bounded_response_copy(payload)


def validate_trial_screen_read_model(
    model: Mapping[str, Any],
    *,
    trial_snapshots: Sequence[Mapping[str, Any]],
    publication_context: Mapping[str, Any],
    filters: Mapping[str, Any] | None = None,
    offset: int = 0,
    limit: int = 50,
    next_cursor_factory: Callable[[int], str] | None = None,
) -> dict[str, Any]:
    """Validate a page both structurally and against its exact pure inputs."""

    if not isinstance(model, Mapping):
        raise TrialScreenError("trial_screen_model_must_be_a_mapping")
    normalized = _bounded_response_copy(model)
    if not isinstance(normalized, dict):
        raise TrialScreenError("trial_screen_model_must_be_an_object")
    try:
        validate_contract(CONTRACT_ID, normalized)
    except ContractValidationError as exc:
        raise TrialScreenError("invalid_trial_screen_read_model") from exc
    expected = _build_model(
        trial_snapshots=trial_snapshots,
        publication_context=publication_context,
        filters=filters,
        offset=offset,
        limit=limit,
        next_cursor_factory=next_cursor_factory,
    )
    if normalized != expected:
        raise TrialScreenError("trial_screen_input_binding_mismatch")
    return normalized


def trial_screen_contract_semantic_issues(
    document: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Contract-only self-consistency checks; never opens a data source."""

    issues: list[ValidationIssue] = []
    query_filters: dict[str, str | None] | None = None
    try:
        if len(canonical_json_bytes(document)) > MAX_RESPONSE_BYTES:
            issues.append(
                ValidationIssue(
                    "$",
                    "trial_screen.response_bytes",
                    "the complete canonical response exceeds the advertised byte ceiling",
                )
            )
        as_of = _utc_z_datetime(document.get("as_of"), field="as_of")
        source = document.get("source")
        if isinstance(source, Mapping):
            _source_clock(source.get("dataset_timestamp_raw"), field="source_dataset_timestamp_raw")
        coverage = document.get("coverage")
        if isinstance(coverage, Mapping):
            configured = coverage.get("configured")
            observed = coverage.get("observed")
            matched = coverage.get("matched")
            if isinstance(configured, int) and isinstance(observed, int) and observed > configured:
                issues.append(
                    ValidationIssue(
                        "$.coverage.observed",
                        "trial_screen.coverage",
                        "observed current snapshots cannot exceed configured coverage",
                    )
                )
            if isinstance(observed, int) and isinstance(matched, int) and matched > observed:
                issues.append(
                    ValidationIssue(
                        "$.coverage.matched",
                        "trial_screen.coverage",
                        "matched current snapshots cannot exceed observed coverage",
                    )
                )
        query = document.get("query")
        if isinstance(query, Mapping):
            supplied = {field: query.get(field) for field in _FILTER_FIELDS}
            query_filters = canonicalize_trial_screen_filters(supplied)
            if query_filters != supplied:
                issues.append(
                    ValidationIssue(
                        "$.query",
                        "trial_screen.query_normalization",
                        "query text must be case-folded and whitespace-collapsed before matching",
                    )
                )
        pagination = document.get("pagination")
        rows = document.get("rows")
        if isinstance(pagination, Mapping) and isinstance(rows, list):
            offset = pagination.get("offset")
            total = pagination.get("total")
            limit = pagination.get("limit")
            returned = pagination.get("returned")
            if all(isinstance(item, int) and not isinstance(item, bool) for item in (offset, total, limit, returned)):
                expected_returned = min(limit, max(0, total - offset)) if offset <= total else None
                if returned != len(rows) or returned != expected_returned:
                    issues.append(
                        ValidationIssue(
                            "$.pagination",
                            "trial_screen.pagination",
                            "returned must equal the exact bounded page slice",
                        )
                    )
                next_cursor = pagination.get("next_cursor")
                if (offset + returned < total) != isinstance(next_cursor, str):
                    issues.append(
                        ValidationIssue(
                            "$.pagination.next_cursor",
                            "trial_screen.pagination",
                            "next_cursor is present exactly when another page exists",
                        )
                    )
            if document.get("row_count") != len(rows):
                issues.append(
                    ValidationIssue(
                        "$.row_count",
                        "trial_screen.row_count",
                        "row_count must equal the returned sanitized row count",
                    )
                )
            coverage = document.get("coverage")
            if isinstance(coverage, Mapping) and coverage.get("matched") != pagination.get("total"):
                issues.append(
                    ValidationIssue(
                        "$.coverage.matched",
                        "trial_screen.coverage",
                        "matched must equal the full filtered total before pagination",
                    )
                )
            nct_ids = [row.get("nct_id") for row in rows if isinstance(row, Mapping)]
            if len(nct_ids) != len(rows) or len(set(nct_ids)) != len(nct_ids):
                issues.append(
                    ValidationIssue(
                        "$.rows",
                        "trial_screen.row_identity",
                        "a page cannot contain duplicate or malformed NCT IDs",
                    )
                )
            try:
                if rows != sorted(rows, key=_row_order):
                    issues.append(
                        ValidationIssue(
                            "$.rows",
                            "trial_screen.order",
                            "rows must be ordered by full primary-completion interval then NCT ID, with undated rows last",
                        )
                    )
            except (AttributeError, TypeError, KeyError):
                pass
            for index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    continue
                primary_completion = row.get("primary_completion")
                if not isinstance(primary_completion, Mapping):
                    continue
                state = primary_completion.get("state")
                literal = primary_completion.get("literal")
                interval = primary_completion.get("interval")
                try:
                    if state == "observed":
                        expected_start, expected_end, expected_precision = _date_interval(
                            literal, field="primary_completion_date"
                        )
                        if (
                            primary_completion.get("precision") != expected_precision
                            or interval != {"start": expected_start, "end": expected_end}
                        ):
                            issues.append(
                                ValidationIssue(
                                    f"$.rows[{index}].primary_completion",
                                    "trial_screen.primary_completion_interval",
                                    "the displayed interval and precision must be the exact expansion of the preserved source literal",
                                )
                            )
                    elif any(
                        primary_completion.get(field) is not None
                        for field in ("literal", "precision", "interval", "type")
                    ):
                        issues.append(
                            ValidationIssue(
                                f"$.rows[{index}].primary_completion",
                                "trial_screen.primary_completion_missingness",
                                "a non-observed primary-completion source fact cannot carry an inferred date",
                            )
                        )
                except TrialScreenError:
                    issues.append(
                        ValidationIssue(
                            f"$.rows[{index}].primary_completion.literal",
                            "trial_screen.primary_completion_interval",
                            "the preserved source date literal must be a real calendar date",
                        )
                    )
                source_row = row.get("source")
                nct_id = row.get("nct_id")
                if (
                    isinstance(source_row, Mapping)
                    and isinstance(nct_id, str)
                    and source_row.get("url") != f"https://clinicaltrials.gov/study/{nct_id}"
                ):
                    issues.append(
                        ValidationIssue(
                            f"$.rows[{index}].source.url",
                            "trial_screen.row_identity",
                            "row source URL must identify the same NCT ID",
                        )
                    )
                if query_filters is not None:
                    try:
                        if not _matches(row, query_filters):
                            issues.append(
                                ValidationIssue(
                                    f"$.rows[{index}]",
                                    "trial_screen.query_membership",
                                    "every returned row must satisfy every declared literal filter",
                                )
                            )
                    except (KeyError, TypeError, AttributeError):
                        pass
                if isinstance(source_row, Mapping):
                    try:
                        if _utc_z_datetime(
                            source_row.get("retrieved_at"), field="retrieved_at"
                        ) > as_of:
                            issues.append(
                                ValidationIssue(
                                    f"$.rows[{index}].source.retrieved_at",
                                    "trial_screen.publication_clock",
                                    "a displayed source fact cannot be retrieved after the screen as_of clock",
                                )
                            )
                    except TrialScreenError:
                        pass
    except (TrialScreenError, ContractError, TypeError, ValueError):
        # Schema validation reports the malformed field; never let a hostile
        # in-memory document escape the generic fail-closed registry path.
        pass
    return issues


__all__ = [
    "CONTRACT_ID",
    "MAX_INPUT_SNAPSHOTS",
    "MAX_PAGE_LIMIT",
    "MAX_RESPONSE_BYTES",
    "MAX_SANITIZED_ROW_BYTES",
    "MAX_SANITIZED_SCAN_BYTES",
    "TrialScreenError",
    "build_trial_screen_read_model",
    "canonicalize_trial_screen_filters",
    "trial_screen_contract_semantic_issues",
    "validate_trial_screen_read_model",
]
