"""Public-safe, point-in-time Capital Structure event-state projection.

This module intentionally projects only facts already present in the verified
``capital_structure.event.v1`` spine.  It does not parse financing terms or
infer issuance, capacity, runway, overhang, risk, or probability.  Those
capabilities remain explicitly unavailable until their own ledgers exist.

The projection is pure and network-free.  Issuers are keyed by the stable SEC
issuer identifier, never by ticker, and every visible event is filtered on the
canonical Mastermind system clock.  Relationship edges have their own clock
and cannot appear before that clock.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from engine.capital_structure.event_spine import current_events_as_of


PROJECTION_SCHEMA = "capital_structure.projection.v1"
PROJECTION_BUNDLE_SCHEMA = "capital_structure.projection_bundle.v1"
PROJECTION_VERSION = "capital-structure-event-projection/1.0.0"
FRESHNESS_SLA_HOURS = 30

AUTHORITY = {
    "is_context_only": True,
    "rank_authority": False,
    "sizing_authority": False,
    "entry_authority": False,
    "prophet_authority": False,
}

UNAVAILABLE_CAPABILITIES = [
    "active_instrument_overhang",
    "cash_runway",
    "financing_probability",
    "fully_diluted_shares",
    "instruments",
    "normalized_terms",
    "offering_ability",
    "remaining_capacity",
]

_CHANGE_LABELS = {
    "registration_statement": ("registration_observed", "Registration statement observed"),
    "automatic_shelf_registration": (
        "automatic_shelf_registration_observed",
        "Automatic shelf registration observed",
    ),
    "registration_amendment": (
        "registration_amendment_observed",
        "Registration amendment observed",
    ),
    "post_effective_amendment": (
        "post_effective_amendment_observed",
        "Post-effective amendment observed",
    ),
    "effectiveness_notice": (
        "effectiveness_notice_observed",
        "SEC effectiveness notice observed",
    ),
    "withdrawal_request": ("withdrawal_observed", "Withdrawal filing observed"),
    "automatic_shelf_withdrawal": (
        "withdrawal_observed",
        "Automatic-shelf withdrawal observed",
    ),
    "offering_statement": ("reg_a_statement_observed", "Regulation A statement observed"),
    "offering_statement_amendment": (
        "reg_a_amendment_observed",
        "Regulation A amendment observed",
    ),
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _parse_time(value: Any, field: str, *, nullable: bool = False) -> datetime | None:
    if value is None or str(value).strip() == "":
        if nullable:
            return None
        raise ValueError(f"{field} is required")
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: Any, field: str) -> str:
    parsed = _parse_time(value, field)
    assert parsed is not None
    return parsed.isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, body: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(body)).hexdigest()[:24]


def _visible_edges(
    edges: Sequence[Mapping[str, Any]], as_of: str
) -> list[dict[str, Any]]:
    cutoff = _parse_time(as_of, "as_of")
    assert cutoff is not None
    visible: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in edges:
        edge = deepcopy(dict(raw))
        edge_id = str(edge.get("edge_id") or "")
        observed_at = _parse_time(edge.get("observed_at"), "edge.observed_at")
        if not edge_id:
            raise ValueError("every edge requires edge_id")
        if edge_id in seen:
            raise ValueError(f"duplicate edge_id: {edge_id}")
        seen.add(edge_id)
        if observed_at is not None and observed_at <= cutoff:
            visible.append(edge)
    return sorted(
        visible,
        key=lambda item: (str(item.get("observed_at") or ""), str(item["edge_id"])),
    )


def _visible_event_history(
    events: Sequence[Mapping[str, Any]], as_of: str
) -> dict[str, dict[str, Any]]:
    """Return every immutable event version visible on the system clock.

    Current projection rows collapse corrections by logical event, but an
    immutable edge may legitimately target an older visible version. Keeping a
    separate visible-history map admits that case without allowing an edge to
    reveal an endpoint whose own system clock is still in the future.
    """
    cutoff = _parse_time(as_of, "as_of")
    assert cutoff is not None
    visible: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for raw in events:
        event = deepcopy(dict(raw))
        event_id = str(event.get("event_id") or "")
        if not event_id:
            raise ValueError("every event requires event_id")
        if event_id in seen:
            raise ValueError(f"duplicate event_id: {event_id}")
        seen.add(event_id)
        available_at = _parse_time(
            (event.get("point_in_time") or {}).get("available_at"),
            "event.point_in_time.available_at",
        )
        if available_at is not None and available_at <= cutoff:
            visible[event_id] = event
    return visible


def _review_by_event(
    review_items: Sequence[Mapping[str, Any]], as_of: str
) -> dict[str, list[dict[str, Any]]]:
    """Return current rebuild-queue rows visible by their first queue clock.

    The review queue is explicitly a current rebuild, not an append-only
    historical ledger.  The projection therefore exposes the queue semantic
    and never claims that these rows are a complete historical review replay.
    """
    cutoff = _parse_time(as_of, "as_of")
    assert cutoff is not None
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for raw in review_items:
        item = deepcopy(dict(raw))
        queue_id = str(item.get("queue_id") or "")
        if not queue_id:
            raise ValueError("every review item requires queue_id")
        if queue_id in seen:
            raise ValueError(f"duplicate queue_id: {queue_id}")
        seen.add(queue_id)
        queued_at = _parse_time(item.get("first_queued_at"), "review.first_queued_at")
        if queued_at is not None and queued_at <= cutoff:
            grouped[str(item.get("event_id") or "")].append(item)
    for rows in grouped.values():
        rows.sort(key=lambda item: str(item["queue_id"]))
    return grouped


def _event_change(event: Mapping[str, Any]) -> dict[str, Any]:
    event_body = event.get("event") or {}
    classification = event.get("classification") or {}
    subtype = str(event_body.get("subtype") or "")
    if classification.get("state") not in {"classified", "not_applicable"}:
        change_type = "classification_pending"
        if subtype == "prospectus_event":
            label = "Prospectus observed; classification pending"
        else:
            label = "Filing observed; classification pending"
    else:
        change_type, label = _CHANGE_LABELS.get(
            subtype, ("filing_state_observed", "Filing state observed")
        )
    body = {
        "event_id": str(event["event_id"]),
        "change_type": change_type,
        "label": label,
        "observed_at": str((event.get("point_in_time") or {}).get("available_at")),
    }
    return {"change_id": _stable_id("change:cs:", body), **body, "edge_id": None}


def _edge_change(edge: Mapping[str, Any]) -> dict[str, Any]:
    relationship = str(edge.get("relationship") or "")
    labels = {
        "amendment_of": "Registration amendment link observed",
        "effectuates": "Effectiveness link observed",
        "withdraws": "Withdrawal link observed",
        "supersedes": "Source correction link observed",
    }
    body = {
        "event_id": str(edge.get("from_event_id") or ""),
        "change_type": relationship + "_link_observed",
        "label": labels.get(relationship, "Filing relationship observed"),
        "observed_at": str(edge.get("observed_at") or ""),
    }
    return {
        "change_id": _stable_id("change:cs:", {**body, "edge_id": edge["edge_id"]}),
        **body,
        "edge_id": str(edge["edge_id"]),
    }


def _event_projection(
    event: Mapping[str, Any],
    *,
    generated_at: str,
    edges: Sequence[Mapping[str, Any]],
    review_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    filing = event.get("filing") or {}
    event_body = event.get("event") or {}
    classification = event.get("classification") or {}
    point_in_time = event.get("point_in_time") or {}
    version = event.get("version") or {}
    source = event.get("source") or {}
    event_id = str(event["event_id"])
    event_edges = [
        {
            "edge_id": str(edge["edge_id"]),
            "relationship": str(edge["relationship"]),
            "to_event_id": str(edge["to_event_id"]),
            "observed_at": str(edge["observed_at"]),
        }
        for edge in edges
        if str(edge.get("from_event_id") or "") == event_id
    ]
    return {
        "event_id": event_id,
        "accession": filing.get("accession"),
        "form": filing.get("form"),
        "filing_date": filing.get("filing_date"),
        "family": event_body.get("family"),
        "subtype": event_body.get("subtype"),
        "lifecycle_state": (event.get("lifecycle") or {}).get("state"),
        "classification_state": classification.get("state"),
        "defer_reason": classification.get("defer_reason"),
        "correction_version": int(version.get("correction_version") or 1),
        "correction_of": version.get("correction_of"),
        "relationships": event_edges,
        "review": {
            "state": "pending" if review_rows else "none",
            "queue_ids": sorted(str(item["queue_id"]) for item in review_rows),
            "items": [
                {
                    "queue_id": str(item["queue_id"]),
                    "classification_state": str(item.get("classification_state") or ""),
                    "defer_reason": str(item.get("defer_reason") or ""),
                    "candidate_event_ids": sorted(
                        str(value) for value in item.get("candidate_event_ids") or []
                    ),
                    "first_queued_at": str(item.get("first_queued_at") or ""),
                }
                for item in sorted(review_rows, key=lambda row: str(row["queue_id"]))
            ],
        },
        "clocks": {
            "sec_accepted_at": filing.get("accepted_at"),
            "mastermind_observed_at": point_in_time.get("available_at"),
            "projection_generated_at": generated_at,
        },
        "source": {
            "source_system": source.get("source_system"),
            "source_id": source.get("source_id"),
            "filing_url": filing.get("primary_document_url"),
            "manifest_ids": sorted(str(value) for value in source.get("manifest_ids") or []),
            "evidence": sorted(
                [
                    {
                        "manifest_id": str(item.get("manifest_id") or ""),
                        "span_id": str(item.get("span_id") or ""),
                        "text_sha256": str(item.get("text_sha256") or ""),
                    }
                    for item in event.get("evidence") or []
                ],
                key=lambda item: (item["manifest_id"], item["span_id"]),
            ),
        },
    }


def _identity(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        events,
        key=lambda event: (
            str((event.get("point_in_time") or {}).get("available_at") or ""),
            str(event.get("event_id") or ""),
        ),
    )
    tickers = sorted(
        {
            str((event.get("issuer") or {}).get("ticker"))
            for event in ordered
            if (event.get("issuer") or {}).get("ticker")
        }
    )
    current_ticker = next(
        (
            str((event.get("issuer") or {}).get("ticker"))
            for event in reversed(ordered)
            if (event.get("issuer") or {}).get("ticker")
        ),
        None,
    )
    aliases = sorted(
        {
            str(alias)
            for event in ordered
            for alias in ((event.get("issuer") or {}).get("aliases") or [])
            if alias
        }
    )
    ciks = {
        str((event.get("issuer") or {}).get("cik"))
        for event in ordered
        if (event.get("issuer") or {}).get("cik")
    }
    if len(ciks) > 1:
        raise ValueError(f"issuer projection contains conflicting CIKs: {sorted(ciks)}")
    return {
        "cik": next(iter(ciks), None),
        "ticker": current_ticker,
        "observed_tickers": tickers,
        "aliases": aliases,
    }


def _freshness(
    telemetry: Mapping[str, Any], generated_at: str
) -> tuple[str, float | None]:
    source_as_of = _parse_time(telemetry.get("as_of"), "telemetry.as_of", nullable=True)
    produced = _parse_time(generated_at, "generated_at")
    assert produced is not None
    if source_as_of is None:
        return "unknown", None
    age = (produced - source_as_of).total_seconds() / 3600
    if age < 0:
        return "unknown", round(age, 6)
    return ("fresh" if age <= FRESHNESS_SLA_HOURS else "stale"), round(age, 6)


def _unavailable_bundle(
    telemetry: Mapping[str, Any], *, as_of: str, generated_at: str, reason: str
) -> dict[str, Any]:
    freshness, age_hours = _freshness(telemetry, generated_at)
    artifact_hashes = telemetry.get("artifact_hashes") or {}
    source_receipt = {
        "generation_id": telemetry.get("generation_id"),
        "as_of": telemetry.get("as_of"),
        "artifact_hashes": {
            "event_versions": artifact_hashes.get("event_versions"),
            "event_edges": artifact_hashes.get("event_edges"),
            "review_queue": artifact_hashes.get("review_queue"),
        },
        "source_ledger_receipt": telemetry.get("source_ledger_receipt"),
    }
    body: dict[str, Any] = {
        "schema": PROJECTION_BUNDLE_SCHEMA,
        "projection_version": PROJECTION_VERSION,
        "generated_at": generated_at,
        "as_of": as_of,
        "source_receipt": source_receipt,
        "coverage": {
            "state": "unavailable",
            "freshness": freshness,
            "age_hours": age_hours,
            "freshness_sla_hours": FRESHNESS_SLA_HOURS,
            "source_status": str(telemetry.get("status") or "missing"),
            "coverage_claim": telemetry.get("coverage_claim"),
            "known_exclusions": sorted(str(value) for value in telemetry.get("known_exclusions") or []),
            "reason": reason,
            "issuer_count": 0,
            "event_count": 0,
            "classified_event_count": 0,
            "deferred_event_count": 0,
            "edge_count": 0,
            "review_count": 0,
        },
        "records": [],
        "unavailable": list(UNAVAILABLE_CAPABILITIES),
        "authority": dict(AUTHORITY),
    }
    body["generation_id"] = _stable_id("projection:cs:", body)
    return body


def build_projection_bundle(
    events: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    review_items: Sequence[Mapping[str, Any]],
    telemetry: Mapping[str, Any],
    as_of: str,
    generated_at: str,
) -> dict[str, Any]:
    """Build a strict event-state snapshot from an already-verified generation."""
    as_of_iso = _iso(as_of, "as_of")
    generated_iso = _iso(generated_at, "generated_at")
    generated_dt = _parse_time(generated_iso, "generated_at")
    as_of_dt = _parse_time(as_of_iso, "as_of")
    assert generated_dt is not None and as_of_dt is not None
    if generated_dt < as_of_dt:
        raise ValueError("generated_at cannot precede projection as_of")

    source_status = str(telemetry.get("status") or "missing")
    if source_status != "ok":
        return _unavailable_bundle(
            telemetry,
            as_of=as_of_iso,
            generated_at=generated_iso,
            reason=f"source_generation_{source_status}",
        )
    if not telemetry.get("generation_id"):
        return _unavailable_bundle(
            telemetry,
            as_of=as_of_iso,
            generated_at=generated_iso,
            reason="source_generation_unbound",
        )

    source_as_of = _parse_time(telemetry.get("as_of"), "telemetry.as_of")
    assert source_as_of is not None
    if as_of_dt > source_as_of:
        raise ValueError("projection as_of cannot exceed the verified source generation clock")
    if generated_dt < source_as_of:
        raise ValueError("generated_at cannot precede the verified source generation clock")
    counts = telemetry.get("counts") or {}
    expected_counts = {
        "event_versions": len(events),
        "event_edges": len(edges),
        "review_queue": len(review_items),
    }
    for field, actual in expected_counts.items():
        if int(counts.get(field, -1)) != actual:
            raise ValueError(
                f"projection input {field} count does not match verified telemetry"
            )

    visible_history = _visible_event_history(events, as_of_iso)
    visible_events = current_events_as_of(events, as_of_iso, mode="system")
    visible_edges = _visible_edges(edges, as_of_iso)
    reviews = _review_by_event(review_items, as_of_iso)
    event_ids = {str(event["event_id"]) for event in visible_events}
    endpoint_visible_edges: list[dict[str, Any]] = []
    for edge in visible_edges:
        from_id = str(edge.get("from_event_id") or "")
        to_id = str(edge.get("to_event_id") or "")
        if from_id not in visible_history or to_id not in visible_history:
            continue
        from_issuer = str(
            (visible_history[from_id].get("issuer") or {}).get("issuer_id") or ""
        )
        to_issuer = str(
            (visible_history[to_id].get("issuer") or {}).get("issuer_id") or ""
        )
        if not from_issuer or from_issuer != to_issuer:
            raise ValueError(f"cross-issuer event edge is forbidden: {edge.get('edge_id')}")
        if from_id in event_ids:
            endpoint_visible_edges.append(edge)
    visible_edges = endpoint_visible_edges
    reviews = {
        event_id: rows for event_id, rows in reviews.items() if event_id in event_ids
    }

    by_issuer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in visible_events:
        issuer_id = str((event.get("issuer") or {}).get("issuer_id") or "")
        if not issuer_id:
            raise ValueError(f"event {event.get('event_id')} has no issuer_id")
        by_issuer[issuer_id].append(event)

    records: list[dict[str, Any]] = []
    for issuer_id in sorted(by_issuer):
        issuer_events = sorted(
            by_issuer[issuer_id],
            key=lambda event: (
                str((event.get("point_in_time") or {}).get("available_at") or ""),
                str(event.get("event_id") or ""),
            ),
            reverse=True,
        )
        issuer_event_ids = {str(event["event_id"]) for event in issuer_events}
        issuer_edges = [
            edge
            for edge in visible_edges
            if str(edge.get("from_event_id") or "") in issuer_event_ids
        ]
        timeline = [
            _event_projection(
                event,
                generated_at=generated_iso,
                edges=issuer_edges,
                review_rows=reviews.get(str(event["event_id"]), []),
            )
            for event in issuer_events
        ]
        changes = [_event_change(event) for event in issuer_events]
        changes.extend(_edge_change(edge) for edge in issuer_edges)
        changes.sort(
            key=lambda item: (
                str(item["observed_at"]),
                str(item["change_id"]),
            ),
            reverse=True,
        )
        classified = sum(
            (event.get("classification") or {}).get("state") == "classified"
            for event in issuer_events
        )
        deferred = sum(
            str((event.get("classification") or {}).get("state") or "").startswith("deferred_")
            for event in issuer_events
        )
        issuer_review_count = sum(
            len(reviews.get(str(event["event_id"]), [])) for event in issuer_events
        )
        contradiction_ids = sorted(
            {
                str(value)
                for event in issuer_events
                for value in ((event.get("reconciliation") or {}).get("contradiction_ids") or [])
            }
        )
        records.append({
            "schema": PROJECTION_SCHEMA,
            "issuer_id": issuer_id,
            "identity": _identity(issuer_events),
            "as_of": as_of_iso,
            "generated_at": generated_iso,
            "latest_observed_event": timeline[0] if timeline else None,
            "timeline": timeline,
            "what_changed": changes,
            "coverage": {
                "state": "contradicted" if contradiction_ids else "partial",
                "event_count": len(issuer_events),
                "classified_event_count": classified,
                "deferred_event_count": deferred,
                "review_count": issuer_review_count,
                "review_queue_semantics": "current_rebuild_not_historical_ledger",
                "contradiction_ids": contradiction_ids,
            },
            "unavailable": list(UNAVAILABLE_CAPABILITIES),
            "authority": dict(AUTHORITY),
        })

    freshness, age_hours = _freshness(telemetry, generated_iso)
    classified_count = sum(
        (event.get("classification") or {}).get("state") == "classified"
        for event in visible_events
    )
    deferred_count = sum(
        str((event.get("classification") or {}).get("state") or "").startswith("deferred_")
        for event in visible_events
    )
    visible_review_count = sum(len(rows) for rows in reviews.values())
    source_receipt = {
        "generation_id": telemetry.get("generation_id"),
        "as_of": telemetry.get("as_of"),
        "artifact_hashes": deepcopy(dict(telemetry.get("artifact_hashes") or {})),
        "source_ledger_receipt": deepcopy(telemetry.get("source_ledger_receipt")),
    }
    bundle_state = (
        "contradicted"
        if any(record["coverage"]["state"] == "contradicted" for record in records)
        else "partial"
    )
    body = {
        "schema": PROJECTION_BUNDLE_SCHEMA,
        "projection_version": PROJECTION_VERSION,
        "generated_at": generated_iso,
        "as_of": as_of_iso,
        "source_receipt": source_receipt,
        "coverage": {
            "state": bundle_state,
            "freshness": freshness,
            "age_hours": age_hours,
            "freshness_sla_hours": FRESHNESS_SLA_HOURS,
            "source_status": source_status,
            "coverage_claim": telemetry.get("coverage_claim"),
            "known_exclusions": sorted(str(value) for value in telemetry.get("known_exclusions") or []),
            "reason": "event_state_only_terms_and_issuer_state_unavailable",
            "issuer_count": len(records),
            "event_count": len(visible_events),
            "classified_event_count": classified_count,
            "deferred_event_count": deferred_count,
            "edge_count": len(visible_edges),
            "review_count": visible_review_count,
        },
        "records": records,
        "unavailable": list(UNAVAILABLE_CAPABILITIES),
        "authority": dict(AUTHORITY),
    }
    body["generation_id"] = _stable_id("projection:cs:", body)
    return body


def validate_projection_bundle(
    bundle: Mapping[str, Any], schema_path: Path | str | None = None
) -> None:
    """Validate the serialized public contract, including format checks."""
    from jsonschema import Draft202012Validator, FormatChecker

    path = Path(schema_path) if schema_path else (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "capital_structure_projection.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(dict(bundle)), key=lambda error: list(error.path))
    if errors:
        messages = [
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors[:10]
        ]
        raise ValueError("capital-structure projection contract violation: " + "; ".join(messages))


__all__ = [
    "AUTHORITY",
    "FRESHNESS_SLA_HOURS",
    "PROJECTION_BUNDLE_SCHEMA",
    "PROJECTION_SCHEMA",
    "PROJECTION_VERSION",
    "UNAVAILABLE_CAPABILITIES",
    "build_projection_bundle",
    "validate_projection_bundle",
]
