"""Facts-only assembly for explicit ClinicalTrials.gov protocol cohorts.

This module consumes only ``trial_protocol_projection.v1`` artifacts that have
already crossed the publication boundary.  It deliberately has no identity,
ranking, clustering, inference, or score surface: a caller supplies every NCT
ID in the cohort.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping, Sequence

from engine.sector_intelligence import canonical_json_bytes, validate_contract
from engine.sector_intelligence.contracts import ContractError

from .protocols import (
    TrialProtocolProjectionError,
    validate_trial_protocol_projection,
)


class TrialPeerSetError(ValueError):
    """A bounded public-projection or peer-set assembly failure."""


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
_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_PUBLIC_SOURCE_FIELD_LOCATORS = frozenset(
    (
        "/protocolSection/identificationModule/briefTitle",
        "/protocolSection/identificationModule/officialTitle",
        "/protocolSection/statusModule/overallStatus",
        "/protocolSection/designModule/studyType",
        "/protocolSection/designModule/phases",
        "/protocolSection/sponsorCollaboratorsModule/leadSponsor",
        "/protocolSection/designModule/enrollmentInfo",
        "/protocolSection/statusModule/startDateStruct",
        "/protocolSection/statusModule/primaryCompletionDateStruct",
        "/protocolSection/statusModule/completionDateStruct",
        "/protocolSection/conditionsModule/conditions",
        "/protocolSection/armsInterventionsModule/interventions",
        "/protocolSection/armsInterventionsModule/armGroups",
        "/protocolSection/outcomesModule/primaryOutcomes",
        "/protocolSection/outcomesModule/secondaryOutcomes",
        "/protocolSection/contactsLocationsModule/locations",
    )
)
_MAX_TRIAL_PEER_SET_RESPONSE_BYTES = 1024 * 1024


def _text(value: object, *, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        return None
    return cleaned if len(cleaned) <= maximum else cleaned[: maximum - 1].rstrip() + "…"


def _text_list(value: object, *, limit: int, maximum: int) -> list[str]:
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
        if len(rows) == limit:
            break
    return rows


def _fact(facts: Mapping[str, Any], key: str) -> Any:
    value = facts.get(key)
    if not isinstance(value, Mapping) or value.get("state") != "observed":
        return None
    return value.get("value")


def _field_evidence(
    facts: Mapping[str, Any],
    *fact_names: str,
    transform: str,
) -> dict[str, Any]:
    """Expose exact retained locators for one rendered facts-only field.

    The public protocol artifact already holds the registered source path beside
    every fact.  Returning a compact field-to-locator map makes the response
    independently explainable without returning the private source snapshot.
    """

    locators: list[str] = []
    states: list[str] = []
    for fact_name in fact_names:
        fact = facts.get(fact_name)
        if not isinstance(fact, Mapping):
            raise TrialPeerSetError("trial_protocol_projection_invalid")
        path = fact.get("source_json_path")
        state = fact.get("state")
        if (
            not isinstance(path, str)
            or path not in _PUBLIC_SOURCE_FIELD_LOCATORS
            or not isinstance(state, str)
        ):
            raise TrialPeerSetError("trial_protocol_projection_invalid")
        locators.append(path)
        states.append(state)
    distinct_states = set(states)
    state = states[0] if len(distinct_states) == 1 else "mixed"
    return {
        "state": state,
        "source_field_locators": locators,
        "transform": transform,
    }


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
                    raw.get("otherNames")
                    if "otherNames" in raw
                    else raw.get("other_names"),
                    limit=20,
                    maximum=256,
                ),
            }
            if row["name"] is None:
                continue
        elif kind == "arm_group":
            row = {
                "label": _text(raw.get("label"), maximum=1000),
                "type": _text(raw.get("type"), maximum=80),
                "description": _text(raw.get("description"), maximum=6000),
                "intervention_names": _text_list(
                    raw.get("interventionNames")
                    if "interventionNames" in raw
                    else raw.get("intervention_names"),
                    limit=100,
                    maximum=512,
                ),
            }
            if row["label"] is None:
                continue
        else:
            row = {
                "measure": _text(raw.get("measure"), maximum=1000),
                "time_frame": _text(
                    raw.get("timeFrame")
                    if "timeFrame" in raw
                    else raw.get("time_frame"),
                    maximum=1000,
                ),
                "description": _text(raw.get("description"), maximum=6000),
            }
            if row["measure"] is None:
                continue
        rows.append(row)
        if len(rows) == limit:
            break
    return rows


def _date_value(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    raw = _text(value.get("date"), maximum=10)
    if raw is None or not re.fullmatch(r"[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?", raw):
        return None
    precision = {4: "year", 7: "month", 10: "day"}.get(len(raw))
    if precision is None:
        return None
    return {"date": raw, "type": _text(value.get("type"), maximum=20), "precision": precision}


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


def _locations(value: object) -> tuple[int | None, list[str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None, []
    count = 0
    countries: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        count += 1
        country = _text(raw.get("country"), maximum=128)
        if country is not None and country not in seen and len(countries) < 100:
            countries.append(country)
            seen.add(country)
    return count, countries


def _record_age(*, as_of: str, retrieved_at: str) -> dict[str, Any]:
    """Return a deterministic observation age without inventing event timing."""

    try:
        as_of_time = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        retrieved_time = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrialPeerSetError("peer_set_as_of_invalid") from exc
    if as_of_time.tzinfo is None or retrieved_time.tzinfo is None:
        raise TrialPeerSetError("peer_set_as_of_invalid")
    elapsed_seconds = (as_of_time - retrieved_time).total_seconds()
    if elapsed_seconds < 0:
        raise TrialPeerSetError("peer_set_as_of_invalid")
    return {
        "seconds": int(elapsed_seconds),
        "basis": "as_of_minus_retrieved_at_floor_seconds",
    }


def _history_availability(model: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(model, Mapping) or model.get("available") is not True:
        reason = _text(
            model.get("unavailable_reason") if isinstance(model, Mapping) else None,
            maximum=80,
        )
        return {
            "available": False,
            "state": "unavailable",
            "coverage": None,
            "reason": reason or "not_collected",
        }
    coverage = _text(model.get("coverage_class"), maximum=80)
    if coverage is None:
        raise TrialPeerSetError("history_projection_invalid")
    return {
        "available": True,
        "state": "available",
        "coverage": coverage,
        "reason": None,
    }


def public_trial_protocol_row(
    projection: Mapping[str, Any],
    *,
    history_model: Mapping[str, Any] | None,
    as_of: str,
) -> dict[str, Any]:
    """Render a protocol projection through a closed, public field allowlist."""

    try:
        protocol = validate_trial_protocol_projection(projection)
    except TrialProtocolProjectionError as exc:
        raise TrialPeerSetError("trial_protocol_projection_invalid") from exc
    facts = protocol.get("facts")
    attribution = protocol.get("source_attribution")
    if not isinstance(facts, Mapping) or not isinstance(attribution, Mapping):
        raise TrialPeerSetError("trial_protocol_projection_invalid")
    nct_id = protocol.get("nct_id")
    if not isinstance(nct_id, str) or not _NCT_ID.fullmatch(nct_id):
        raise TrialPeerSetError("trial_protocol_projection_invalid")
    official_title = _text(_fact(facts, "official_title"), maximum=2000)
    brief_title = _text(_fact(facts, "brief_title"), maximum=1000)
    site_count, countries = _locations(_fact(facts, "locations"))
    retrieved_at = protocol.get("retrieved_at")
    first_seen_at = protocol.get("first_seen_at")
    source_uri = attribution.get("source_uri")
    if not isinstance(retrieved_at, str) or not isinstance(first_seen_at, str) or not isinstance(source_uri, str):
        raise TrialPeerSetError("trial_protocol_projection_invalid")
    return {
        "nct_id": nct_id,
        "title": official_title or brief_title,
        "brief_title": brief_title,
        "status": _text(_fact(facts, "overall_status"), maximum=80),
        "study_type": _text(_fact(facts, "study_type"), maximum=80),
        "phases": _text_list(_fact(facts, "phases"), limit=12, maximum=80),
        "sponsor": _sponsor_value(_fact(facts, "sponsor")),
        "conditions": _text_list(_fact(facts, "conditions"), limit=100, maximum=512),
        "interventions": _named_rows(
            _fact(facts, "interventions"), kind="intervention", limit=100
        ),
        "arm_groups": _named_rows(
            _fact(facts, "arm_groups"), kind="arm_group", limit=100
        ),
        "enrollment": _enrollment_value(_fact(facts, "enrollment")),
        "endpoints": {
            "primary": _named_rows(
                _fact(facts, "primary_outcomes"), kind="endpoint", limit=100
            ),
            "secondary": _named_rows(
                _fact(facts, "secondary_outcomes"), kind="endpoint", limit=200
            ),
        },
        "dates": {
            "start": _date_value(_fact(facts, "start_date")),
            "primary_completion": _date_value(
                _fact(facts, "primary_completion_date")
            ),
            "completion": _date_value(_fact(facts, "completion_date")),
        },
        "site_count": site_count,
        "countries": countries,
        "record_age": _record_age(as_of=as_of, retrieved_at=retrieved_at),
        "evidence": {
            "provider": "ClinicalTrials.gov",
            "record_id": nct_id,
            "url": source_uri,
            "updated_at": attribution.get("source_last_update_posted_at"),
            "retrieved_at": retrieved_at,
            "first_seen_at": first_seen_at,
            "coverage": protocol.get("coverage_class"),
        },
        "history": _history_availability(history_model),
        "field_evidence": {
            "title": _field_evidence(
                facts,
                "official_title",
                "brief_title",
                transform="first_nonblank_then_normalize_whitespace_and_field_cap",
            ),
            "brief_title": _field_evidence(
                facts, "brief_title", transform="normalize_whitespace_and_cap_1000"
            ),
            "status": _field_evidence(
                facts, "overall_status", transform="normalize_whitespace_and_cap_80"
            ),
            "study_type": _field_evidence(
                facts, "study_type", transform="normalize_whitespace_and_cap_80"
            ),
            "phases": _field_evidence(
                facts,
                "phases",
                transform="normalize_whitespace_dedupe_source_order_cap_12",
            ),
            "sponsor": _field_evidence(
                facts,
                "sponsor",
                transform="normalize_whitespace_and_field_caps",
            ),
            "conditions": _field_evidence(
                facts,
                "conditions",
                transform="normalize_whitespace_dedupe_source_order_cap_100",
            ),
            "interventions": _field_evidence(
                facts,
                "interventions",
                transform="normalize_whitespace_filter_missing_name_cap_100",
            ),
            "arm_groups": _field_evidence(
                facts,
                "arm_groups",
                transform="normalize_whitespace_filter_missing_label_cap_100",
            ),
            "enrollment": _field_evidence(
                facts,
                "enrollment",
                transform="nonnegative_integer_count_and_normalized_type",
            ),
            "endpoints": _field_evidence(
                facts,
                "primary_outcomes",
                "secondary_outcomes",
                transform="normalize_whitespace_filter_missing_measure_and_caps",
            ),
            "dates": _field_evidence(
                facts,
                "start_date",
                "primary_completion_date",
                "completion_date",
                transform="validate_iso_date_and_derive_precision",
            ),
            "site_count": _field_evidence(
                facts,
                "locations",
                transform="count_mapping_location_rows",
            ),
            "countries": _field_evidence(
                facts,
                "locations",
                transform="unique_country_values_in_source_order_cap_100",
            ),
        },
    }


def build_trial_peer_set(
    *,
    cohort_nct_ids: Sequence[str],
    protocols_by_nct: Mapping[str, Mapping[str, Any]],
    history_models_by_nct: Mapping[str, Mapping[str, Any]] | None,
    as_of: str,
    page_limit: int,
    offset: int,
    next_cursor: str | None,
) -> dict[str, Any]:
    """Build one deterministic page of an explicit NCT cohort.

    The caller has already authenticated and verified its HMAC cursor.  This
    function still rejects malformed rows rather than permitting an invalid
    public generation to look like an empty or partial clinical result.
    """

    if (
        not isinstance(page_limit, int)
        or isinstance(page_limit, bool)
        or not 1 <= page_limit <= 100
        or not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset < 0
        or not isinstance(as_of, str)
    ):
        raise TrialPeerSetError("peer_set_request_invalid")
    cohort = tuple(cohort_nct_ids)
    if (
        not 2 <= len(cohort) <= 100
        or tuple(sorted(cohort)) != cohort
        or len(set(cohort)) != len(cohort)
        or any(not isinstance(nct_id, str) or not _NCT_ID.fullmatch(nct_id) for nct_id in cohort)
    ):
        raise TrialPeerSetError("peer_set_cohort_invalid")
    history = history_models_by_nct or {}
    covered: list[dict[str, Any]] = []
    uncovered: list[str] = []
    for nct_id in cohort:
        protocol = protocols_by_nct.get(nct_id)
        if protocol is None:
            uncovered.append(nct_id)
            continue
        covered.append(
            public_trial_protocol_row(
                protocol,
                history_model=history.get(nct_id),
                as_of=as_of,
            )
        )
    if len(covered) + len(uncovered) != len(cohort):
        raise TrialPeerSetError("peer_set_coverage_invalid")
    page = covered[offset : offset + page_limit]
    if offset > len(covered):
        page = []
    has_next_page = offset + len(page) < len(covered)
    if has_next_page != (next_cursor is not None):
        raise TrialPeerSetError("peer_set_pagination_binding_invalid")
    result: dict[str, Any] = {
        "contract_id": "trial_peer_set.v1",
        "schema_version": "1.0.0",
        "as_of": as_of,
        "cohort_nct_ids": list(cohort),
        "uncovered_nct_ids": uncovered,
        "coverage": {
            "class": "current_only",
            "selection_basis": "explicit_nct_id_cohort",
            "requested_count": len(cohort),
            "covered_count": len(covered),
            "uncovered_count": len(uncovered),
        },
        "pagination": {
            "limit": page_limit,
            "total": len(covered),
            "next_cursor": next_cursor,
        },
        "trials": page,
        "authority": dict(_AUTHORITY),
    }
    try:
        validate_contract("trial_peer_set.v1", result)
    except (ContractError, TypeError, ValueError) as exc:
        raise TrialPeerSetError("trial_peer_set_invalid") from exc
    if len(canonical_json_bytes(result)) > _MAX_TRIAL_PEER_SET_RESPONSE_BYTES:
        raise TrialPeerSetError("peer_set_response_too_large")
    return result


__all__ = [
    "TrialPeerSetError",
    "build_trial_peer_set",
    "public_trial_protocol_row",
]
