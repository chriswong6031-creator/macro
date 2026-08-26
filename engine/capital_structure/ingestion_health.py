"""Capital Structure ingestion health: census, watermarks, and run verdict.

This module is the truth plane for whether a collector run actually retained
durable verified evidence. Compiler ``telemetry.as_of`` is generation time and
must not be treated as source freshness.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from engine.capital_structure.sec_discovery_clock import (
    SEC_TIMEZONE,
    latest_expected_daily_index_date,
    latest_expected_realtime_filing_date,
)

HEALTH_SCHEMA = "capital_structure.ingestion_health/v1"
INGESTION_RUN_SCHEMA = "capital_structure.ingestion_run/v1"
HEALTH_FILENAME = "health.json"
INGESTION_RUN_FILENAME = "ingestion_run.json"
HORIZON_SLA_HOURS = 6
HORIZON_STATES = {
    "current", "lagging", "degraded_capacity", "degraded_discovery", "unavailable",
}
LIVE_TAIL = "LIVE_TAIL"

_AUTHORITY = {
    "is_context_only": True,
    "rank_authority": False,
    "sizing_authority": False,
    "entry_authority": False,
    "prophet_authority": False,
}

_HEX = re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE)
_URL = re.compile(r"https?://\S+")
_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}T[0-9:.+-]+\b")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUM = re.compile(r"\b\d+\b")

_ATTEMPT_STATE_STAGE = {
    "stored": "storage",
    "stored_parser_deferred": "parser",
    "storage_deferred": "storage",
    "transient_error": "retrieval",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _native(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            return value
    return value


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)
    except (TypeError, ValueError):  # pandas NA has no boolean truth value
        return True


def _opt_str(value: Any) -> str | None:
    value = _native(value)
    if _is_missing(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text


def _opt_int(value: Any) -> int | None:
    value = _native(value)
    if _is_missing(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opt_iso_date(value: Any) -> str | None:
    text = _opt_str(value)
    if text is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) is None:
        return None
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _opt_iso_datetime(value: Any) -> str | None:
    text = _opt_str(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return text if parsed.tzinfo is not None else None


def _latest_date_value(
    rows: Sequence[Mapping[str, Any]], field: str
) -> tuple[str | None, bool]:
    raw = [_opt_str(row.get(field)) for row in rows]
    invalid = any(value is not None and _opt_iso_date(value) is None for value in raw)
    valid = [value for value in (_opt_iso_date(value) for value in raw) if value]
    return (max(valid) if valid else None), invalid


def fingerprint_error(message: str | None) -> str:
    """Collapse volatile tokens so identical defects group together."""
    if not message:
        return ""
    text = _URL.sub("<URL>", str(message))
    text = _ISO.sub("<TS>", text)
    text = _HEX.sub("<HEX>", text)
    text = _DATE.sub("<DATE>", text)
    text = _NUM.sub("N", text)
    return text[:240]


def source_high_watermark(manifests: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Point-in-time source freshness, independent of compiler generation time."""
    retrieved: list[str] = []
    filing_dates: list[str] = []
    complete = 0
    for record in manifests:
        document = record.get("document") or {}
        if document.get("document_role") == "complete_submission":
            complete += 1
        retrieved_at = (record.get("retrieval") or {}).get("retrieved_at")
        if retrieved_at:
            retrieved.append(str(retrieved_at))
        filing_date = (record.get("filing") or {}).get("filing_date")
        if filing_date:
            filing_dates.append(str(filing_date)[:10])
    return {
        "source_manifest_count": int(len(manifests)),
        "complete_submission_count": int(complete),
        "latest_retrieved_at": max(retrieved) if retrieved else None,
        "latest_filing_date": max(filing_dates) if filing_dates else None,
    }


def _eligible_retained_manifests(
    manifests: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Return verified durable complete roots, independent of queue closure.

    Pre-Wave-2C roots without file-number provenance remain valid, readable W1
    evidence. The collector may re-observe them to harden provenance, but that
    operational queue rule cannot erase their already-proven retention from the
    information horizon.
    """
    eligible: list[Mapping[str, Any]] = []
    for record in manifests:
        filing = record.get("filing") or {}
        document = record.get("document") or {}
        parser = record.get("parser") or {}
        if not all(isinstance(value, Mapping) for value in (filing, document, parser)):
            continue
        if (
            document.get("document_role") == "complete_submission"
            and parser.get("eligibility") == "eligible"
            and parser.get("corruption_state") == "clean"
        ):
            eligible.append(record)
    return eligible


def _latest_datetime_value(
    rows: Sequence[Mapping[str, Any]], field: str
) -> tuple[str | None, bool]:
    raw = [_opt_str(row.get(field)) for row in rows]
    invalid = any(
        value is not None and _opt_iso_datetime(value) is None for value in raw
    )
    instants: list[datetime] = []
    for value in raw:
        if _opt_iso_datetime(value) is None:
            continue
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        instants.append(parsed.astimezone(timezone.utc))
    if not instants:
        return None, invalid
    latest = max(instants)
    return latest.isoformat().replace("+00:00", "Z"), invalid


def _completed_session_gap(
    completed_index_dates: Sequence[str], *, older: str | None, newer: str | None,
) -> int | None:
    """Count persisted complete SEC index sessions across a watermark gap.

    Calendar subtraction would fabricate a session when SEC was closed or a
    daily index was never observed.  The only authoritative calendar here is
    the ordered persisted coverage receipt.
    """
    if not older or not newer:
        return None
    if newer <= older:
        return 0
    return sum(older < value <= newer for value in completed_index_dates)


def _work_class_row(queue_receipt: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Read the W2 expanded queue receipt while refusing legacy false-freshness."""
    if not isinstance(queue_receipt, Mapping):
        return None
    classes = queue_receipt.get("work_classes")
    if isinstance(classes, Mapping):
        for key in (LIVE_TAIL, "live_tail"):
            value = classes.get(key)
            if isinstance(value, Mapping):
                return value
    if isinstance(classes, list):
        for value in classes:
            if isinstance(value, Mapping) and str(value.get("work_class") or value.get("class") or "").upper() == LIVE_TAIL:
                return value
    return None


def _class_metric(row: Mapping[str, Any], *names: str) -> int | None:
    for name in names:
        value = _opt_int(row.get(name))
        if value is not None:
            return max(0, value)
    return None


def calculate_horizon(
    *,
    discovery: Sequence[Mapping[str, Any]],
    index_coverage: Sequence[Mapping[str, Any]],
    manifests: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    telemetry: Mapping[str, Any],
    queue_receipt: Mapping[str, Any] | None,
    ingestion_run: Mapping[str, Any] | None = None,
    calculated_at: str,
) -> dict[str, Any]:
    """Calculate the one canonical discovery-to-compiled information horizon."""
    policy_version = _opt_str((queue_receipt or {}).get("policy_version"))
    discovery_clock_policy_version = _opt_str(
        (queue_receipt or {}).get("discovery_clock_policy_version")
    )
    clock_contract_active = discovery_clock_policy_version is not None
    calculated_clock = datetime.fromisoformat(calculated_at.replace("Z", "+00:00"))
    if calculated_clock.tzinfo is None:
        raise ValueError("calculated_at must include a timezone")
    coverage_rows = [dict(row) for row in index_coverage]
    if policy_version:
        coverage_rows = [
            row for row in coverage_rows
            if _opt_str(row.get("policy_version")) == policy_version
        ]
    coverage_kind_invalid = clock_contract_active and any(
        (_opt_str(row.get("coverage_kind")) or "daily_index")
        not in {"daily_index", "latest_filings"}
        for row in coverage_rows
    )
    coverage_date_invalid = any(
        _opt_str(row.get("index_date")) is not None
        and _opt_iso_date(row.get("index_date")) is None
        for row in coverage_rows
    )
    coverage_rows = [
        row for row in coverage_rows
        if _opt_iso_date(row.get("index_date")) is not None
    ]
    coverage_rows.sort(key=lambda row: _opt_iso_date(row.get("index_date")) or "")
    latest_expected_date: str | None = None
    latest_realtime_date: str | None = None
    latest_overlay: Mapping[str, Any] | None = None
    if clock_contract_active:
        expected_daily = latest_expected_daily_index_date(calculated_clock)
        expected_realtime = latest_expected_realtime_filing_date(calculated_clock)
        latest_expected_date = expected_daily.isoformat()
        latest_realtime_date = expected_realtime.isoformat()
        daily_rows = [
            row for row in coverage_rows
            if (_opt_str(row.get("coverage_kind")) or "daily_index") == "daily_index"
        ]
        overlay_rows = [
            row for row in coverage_rows
            if _opt_str(row.get("coverage_kind")) == "latest_filings"
        ]
        expected_daily_rows = [
            row for row in daily_rows
            if _opt_iso_date(row.get("index_date")) == latest_expected_date
        ]
        latest_expected = expected_daily_rows[-1] if expected_daily_rows else None
        expected_overlay_rows = [
            row for row in overlay_rows
            if _opt_iso_date(row.get("index_date")) == latest_realtime_date
        ]
        latest_overlay = expected_overlay_rows[-1] if expected_overlay_rows else None
        complete_rows = [
            row for row in daily_rows
            if _opt_str(row.get("status")) == "complete"
            and (_opt_iso_date(row.get("index_date")) or "") <= latest_expected_date
        ]
    else:
        latest_expected = coverage_rows[-1] if coverage_rows else None
        latest_expected_date = (
            _opt_iso_date(latest_expected.get("index_date"))
            if latest_expected else None
        )
        complete_rows = [
            row for row in coverage_rows
            if _opt_str(row.get("status")) == "complete"
        ]
    latest_complete = complete_rows[-1] if complete_rows else None
    completed_dates = [str(row.get("index_date"))[:10] for row in complete_rows if _opt_str(row.get("index_date"))]

    # The collector owns current form/scope admission. Its expanded W2 receipt
    # carries the watermark across every admitted discovery row (including
    # already-retained and parked rows), so health does not fork that policy.
    discovered_filing_raw = _opt_str(
        (queue_receipt or {}).get("latest_discovered_in_policy_filing_date")
    )
    discovered_filing = _opt_iso_date(discovered_filing_raw)
    discovered_date_invalid = (
        discovered_filing_raw is not None and discovered_filing is None
    )
    discovered_at_raw = _opt_str(
        (queue_receipt or {}).get("latest_discovered_in_policy_observed_at")
    )
    discovered_at = _opt_iso_datetime(discovered_at_raw)
    discovered_clock_invalid = discovered_at_raw is not None and discovered_at is None
    retained = _eligible_retained_manifests(manifests)
    retained_filing, retained_date_invalid = _latest_date_value(
        [(row.get("filing") or {}) for row in retained], "filing_date"
    )
    retained_at_horizon = [
        row
        for row in retained
        if _opt_str((row.get("filing") or {}).get("filing_date")) == retained_filing
    ]
    retained_at, retained_clock_invalid = _latest_datetime_value(
        [(row.get("retrieval") or {}) for row in retained_at_horizon], "retrieved_at"
    )
    compiled_rows = [
        {"filing_date": row.get("filing_date")}
        if _opt_str(row.get("filing_date")) is not None
        else {"filing_date": (row.get("filing") or {}).get("filing_date")}
        for row in events
    ]
    compiled_filing, compiled_date_invalid = _latest_date_value(
        compiled_rows, "filing_date"
    )

    live = _work_class_row(queue_receipt)
    metrics_known = isinstance(queue_receipt, Mapping) and live is not None
    arrivals = pending = selected = effective_capacity = None
    if metrics_known:
        arrivals = _class_metric(queue_receipt, "live_tail_arrivals_current_run")
        pending = _class_metric(
            queue_receipt,
            "live_tail_pending_before_selection",
            "live_session_pending_count",
        )
        selected = _class_metric(queue_receipt, "live_tail_selected")
        if selected is None:
            unserved_receipt = _class_metric(
                queue_receipt,
                "live_tail_unserved_after_selection",
                "live_session_unserved_count",
            )
            if pending is not None and unserved_receipt is not None:
                selected = max(0, pending - unserved_receipt)
        effective_capacity = _class_metric(
            queue_receipt, "live_tail_effective_capacity"
        )
        if arrivals is None:
            arrivals = sum(
                _class_metric(row, "current_run_arrivals") or 0
                for row in (queue_receipt.get("work_classes") or [])
                if isinstance(row, Mapping)
            )
        reserved = _class_metric(live, "reserved_slots", "reserved_capacity")
        spill_received = _class_metric(live, "spill_in_slots", "spill_received")
        if effective_capacity is None and reserved is not None and selected is not None:
            effective_capacity = reserved + (spill_received or 0)
    overflow = max(0, arrivals - effective_capacity) if arrivals is not None and effective_capacity is not None else None
    unserved = max(0, pending - selected) if pending is not None and selected is not None else None

    progress_rows = {
        str(row.get("work_class")): row
        for row in ((ingestion_run or {}).get("work_classes") or [])
        if isinstance(row, Mapping) and row.get("work_class")
    }
    class_rows: list[dict[str, Any]] = []
    for row in ((queue_receipt or {}).get("work_classes") or []):
        if not isinstance(row, Mapping):
            continue
        work_class = _opt_str(row.get("work_class"))
        if not work_class:
            continue
        progress = progress_rows.get(work_class) or {}
        class_rows.append({
            "work_class": work_class,
            "pending_count": _class_metric(row, "pending_count"),
            "selected_count": _class_metric(row, "selected_count"),
            "deferred_count": _class_metric(row, "deferred_count"),
            "retrieved_count": _class_metric(progress, "retrieved_count"),
            "parser_deferred_count": _class_metric(
                progress, "parser_deferred_count"
            ),
            "storage_deferred_count": _class_metric(
                progress, "storage_deferred_count"
            ),
            "transient_error_count": _class_metric(
                progress, "transient_error_count"
            ),
        })

    reasons: list[str] = []
    unavailable = False
    degraded_discovery = False
    degraded_capacity = False
    lagging = False
    generation_id = _opt_str(telemetry.get("generation_id"))
    compiler_as_of_raw = _opt_str(telemetry.get("as_of"))
    compiler_as_of = _opt_iso_datetime(compiler_as_of_raw)
    if not generation_id or not compiler_as_of:
        unavailable = True
        reasons.append("compiler_generation_unbound")
    if compiler_as_of_raw is not None and compiler_as_of is None:
        reasons.append("compiler_as_of_invalid")
    if coverage_date_invalid:
        unavailable = True
        reasons.append("discovery_coverage_date_invalid")
    if coverage_kind_invalid:
        unavailable = True
        reasons.append("discovery_coverage_kind_invalid")
    if not latest_expected and clock_contract_active:
        degraded_discovery = True
        reasons.append("latest_expected_index_not_observed")
    elif not latest_expected:
        unavailable = True
        reasons.append("discovery_coverage_missing")
    elif _opt_str(latest_expected.get("status")) == "not_published" and not (
        _opt_str(latest_expected.get("last_error")) or ""
    ).startswith("SEC calendar closure:"):
        degraded_discovery = True
        reasons.append("latest_expected_index_not_observed")
    elif _opt_str(latest_expected.get("status")) not in {
        "complete", "not_published",
    }:
        degraded_discovery = True
        reasons.append("latest_expected_index_not_complete")
    overlay_observed_raw = (
        _opt_str(latest_overlay.get("observed_through"))
        if latest_overlay else None
    )
    overlay_observed = _opt_iso_datetime(overlay_observed_raw)
    if clock_contract_active and not latest_overlay:
        degraded_discovery = True
        reasons.append("latest_filings_observation_missing")
    elif clock_contract_active and _opt_str(latest_overlay.get("status")) != "complete":
        degraded_discovery = True
        reasons.append("latest_filings_observation_not_complete")
    elif clock_contract_active and overlay_observed_raw is None:
        degraded_discovery = True
        reasons.append("latest_filings_observed_through_missing")
    elif clock_contract_active and overlay_observed is None:
        unavailable = True
        reasons.append("latest_filings_observed_through_invalid")
    elif clock_contract_active and (
        datetime.fromisoformat(str(overlay_observed).replace("Z", "+00:00"))
        .astimezone(SEC_TIMEZONE).date().isoformat()
        < str(latest_realtime_date)
    ):
        degraded_discovery = True
        reasons.append("latest_filings_observation_stale")
    if not discovered_filing:
        unavailable = True
        reasons.append("discovered_watermark_missing")
    if discovered_date_invalid:
        reasons.append("discovered_watermark_invalid")
    if discovered_clock_invalid:
        unavailable = True
        reasons.append("discovered_observed_at_invalid")
    elif discovered_filing and not discovered_at:
        unavailable = True
        reasons.append("discovered_observed_at_missing")
    if retained_date_invalid:
        unavailable = True
        reasons.append("retained_watermark_invalid")
    if retained_clock_invalid:
        unavailable = True
        reasons.append("retained_observed_at_invalid")
    elif retained_filing and not retained_at:
        unavailable = True
        reasons.append("retained_observed_at_missing")
    if compiled_date_invalid:
        unavailable = True
        reasons.append("compiled_watermark_invalid")
    if not metrics_known or any(value is None for value in (arrivals, pending, selected, effective_capacity)):
        unavailable = True
        reasons.append("live_tail_metrics_unavailable")
    if overflow and overflow > 0:
        degraded_capacity = True
        reasons.append("live_tail_arrival_overflow")
    if unserved and unserved > 0:
        degraded_capacity = True
        reasons.append("live_tail_unserved_after_selection")
    if discovered_filing and (not retained_filing or retained_filing < discovered_filing):
        lagging = True
        reasons.append("retained_behind_discovery")
    known_needed = [
        value for value in (discovered_filing, retained_filing) if value
    ]
    newest_needed = max(known_needed) if known_needed else None
    if newest_needed and (not compiled_filing or compiled_filing < newest_needed):
        lagging = True
        reasons.append("compiled_behind_retained_or_discovery")
    elif (
        discovered_filing
        and retained_filing
        and compiled_filing
        and len({discovered_filing, retained_filing, compiled_filing}) != 1
    ):
        lagging = True
        reasons.append("filing_horizons_not_at_parity")

    if unavailable:
        state = "unavailable"
    elif degraded_discovery:
        state = "degraded_discovery"
    elif degraded_capacity:
        state = "degraded_capacity"
    elif lagging:
        state = "lagging"
    else:
        state = "current"
    return {
        "state": state,
        "reason_codes": reasons,
        "target_sla_hours": HORIZON_SLA_HOURS,
        "target_next_downstream_job": "capital-structure",
        "policy_version": policy_version,
        "discovery_clock_policy_version": discovery_clock_policy_version,
        "compiler_generation_id": generation_id,
        "compiler_as_of": compiler_as_of,
        "calculated_at": calculated_at,
        "watermarks": {
            "latest_expected_sec_index_date": latest_expected_date,
            "latest_expected_sec_index_status": _opt_str(latest_expected.get("status")) if latest_expected else None,
            "latest_completed_sec_index_date": _opt_str(latest_complete.get("index_date")) if latest_complete else None,
            "latest_expected_realtime_filing_date": latest_realtime_date,
            "latest_filings_status": _opt_str(latest_overlay.get("status")) if latest_overlay else None,
            "latest_filings_observed_through": overlay_observed,
            "latest_discovered_in_policy_filing_date": discovered_filing,
            "latest_discovered_observed_at": discovered_at,
            "latest_eligible_retained_filing_date": retained_filing,
            "latest_eligible_retained_retrieved_at": retained_at,
            "latest_compiled_in_policy_filing_date": compiled_filing,
        },
        "gaps": {
            "discovery_to_retained_completed_sessions": _completed_session_gap(completed_dates, older=retained_filing, newer=discovered_filing),
            "retained_to_compiled_completed_sessions": _completed_session_gap(completed_dates, older=compiled_filing, newer=retained_filing),
        },
        "live_tail": {
            "live_tail_arrivals_current_run": arrivals,
            "live_tail_effective_capacity": effective_capacity,
            "live_tail_arrival_overflow": overflow,
            "live_tail_pending_before_selection": pending,
            "live_tail_selected": selected,
            "live_tail_unserved_after_selection": unserved,
        },
        "work_classes": class_rows,
    }


def census_attempts(attempts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group retrieval attempts by stage/outcome/error/HTTP/storage/lane."""
    grouped: dict[tuple, dict[str, Any]] = {}
    for row in attempts:
        state = _opt_str(row.get("state")) or ""
        error = _opt_str(row.get("error"))
        error_class = _opt_str(row.get("error_class"))
        if not error_class and error:
            error_class = error.split(":", 1)[0].strip() or None
        http_status = _opt_int(row.get("http_status"))
        operation = _opt_str(row.get("storage_operation"))
        lane = _opt_str(row.get("retrieval_lane"))
        attempted_at = _opt_str(row.get("attempted_at"))
        key = (
            _ATTEMPT_STATE_STAGE.get(state, "retrieval"),
            state,
            error_class or "",
            fingerprint_error(error),
            http_status,
            operation or "",
            lane or "",
        )
        bucket = grouped.get(key)
        if bucket is None:
            grouped[key] = {
                "stage": key[0],
                "outcome": state,
                "error_class": error_class,
                "error_fingerprint": fingerprint_error(error),
                "http_status": http_status,
                "storage_operation": operation,
                "lane": lane,
                "count": 1,
                "first_occurrence": attempted_at,
                "latest_occurrence": attempted_at,
            }
        else:
            bucket["count"] += 1
            if attempted_at and (
                not bucket["first_occurrence"] or attempted_at < bucket["first_occurrence"]
            ):
                bucket["first_occurrence"] = attempted_at
            if attempted_at and (
                not bucket["latest_occurrence"] or attempted_at > bucket["latest_occurrence"]
            ):
                bucket["latest_occurrence"] = attempted_at
    return sorted(
        grouped.values(),
        key=lambda row: (-int(row["count"]), str(row["outcome"]), str(row["lane"] or "")),
    )


def decide_verdict(
    *,
    selected: int,
    manifested_delta: int,
    verified_retained: int,
    no_new_work_proven: bool,
    no_new_work_reason: str | None,
    re_observed: int = 0,
) -> tuple[str, str]:
    """Fail closed when work was selected but no durable evidence progressed.

    Third progress term (W1): a verified re-observation of an already-retained
    evidence_id counts as progress so idempotent nights are not the #5792 fail.
    selected>0 AND no progressed AND re_observed==0 still fails (#5792 must not
    regress).
    """
    progressed = (
        int(manifested_delta) > 0
        or int(verified_retained) > 0
        or int(re_observed) > 0
    )
    if progressed:
        return "ok", "durable verified source evidence advanced"
    if int(selected) == 0 and no_new_work_proven:
        return "no_new_work", no_new_work_reason or "queue selected no new filings"
    if int(selected) > 0:
        return (
            "fail",
            "filings were eligible/selected but zero durable verified evidence progressed",
        )
    return (
        "fail",
        "zero durable progress without a proven duplicate/already-known/no-new-work condition",
    )


def build_ingestion_run(
    *,
    as_of: str,
    store_id: str | None,
    selected: int,
    retrieved: int,
    verified_retained: int,
    manifested: int,
    deferred: int,
    parser_deferred: int,
    storage_deferred: int,
    parked: int,
    watermark_before: Mapping[str, Any],
    watermark_after: Mapping[str, Any],
    no_new_work_proven: bool,
    no_new_work_reason: str | None = None,
    re_observed: int = 0,
    unique_evidence_count: int | None = None,
    manifest_revision_count: int | None = None,
    observation_count: int | None = None,
    work_classes: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    manifested_delta = int(watermark_after["source_manifest_count"]) - int(
        watermark_before["source_manifest_count"]
    )
    verdict, reason = decide_verdict(
        selected=selected,
        manifested_delta=manifested_delta,
        verified_retained=verified_retained,
        no_new_work_proven=no_new_work_proven,
        no_new_work_reason=no_new_work_reason,
        re_observed=re_observed,
    )
    counters: dict[str, Any] = {
        "selected": int(selected),
        "retrieved": int(retrieved),
        "verified_retained_sources": int(verified_retained),
        "manifested_sources": int(manifested),
        "deferred": int(deferred),
        "parser_deferred": int(parser_deferred),
        "storage_deferred": int(storage_deferred),
        "parked": int(parked),
        "re_observed": int(re_observed),
    }
    if unique_evidence_count is not None:
        counters["unique_evidence_count"] = int(unique_evidence_count)
    if manifest_revision_count is not None:
        counters["manifest_revision_count"] = int(manifest_revision_count)
    if observation_count is not None:
        counters["observation_count"] = int(observation_count)
    record = {
        "schema": INGESTION_RUN_SCHEMA,
        "as_of": as_of,
        "authority": dict(_AUTHORITY),
        "store_id": store_id,
        "counters": counters,
        "source_high_watermark_before": dict(watermark_before),
        "source_high_watermark_after": dict(watermark_after),
        "no_new_work_proven": bool(no_new_work_proven),
        "no_new_work_reason": no_new_work_reason,
        "verdict": verdict,
        "verdict_reason": reason,
    }
    if work_classes is not None:
        record["work_classes"] = [dict(row) for row in work_classes]
    return record


def build_health_record(
    *,
    generated_at: str,
    ingestion_run: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
    compiled_events: int | None,
    compiler_generated_at: str | None,
    queue_receipt: Mapping[str, Any] | None = None,
    horizon: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    after = dict(ingestion_run.get("source_high_watermark_after") or {})
    counters = dict(ingestion_run.get("counters") or {})
    backlog = {
        "pending": None,
        "parked": counters.get("parked"),
        "oldest_pending_first_seen": None,
        "deferred_count": None,
        "selected_count": None,
    }
    if queue_receipt:
        backlog["pending"] = int(sum(
            int((lane.get("pending_count") or 0))
            for lane in (queue_receipt.get("lanes") or [])
        ))
        backlog["deferred_count"] = queue_receipt.get("deferred_count")
        backlog["selected_count"] = queue_receipt.get("selected_count")
        oldest = [
            str(lane.get("oldest_pending_first_seen"))
            for lane in (queue_receipt.get("lanes") or [])
            if lane.get("oldest_pending_first_seen")
        ]
        backlog["oldest_pending_first_seen"] = min(oldest) if oldest else None
    record = {
        "schema": HEALTH_SCHEMA,
        "generated_at": generated_at,
        "authority": dict(_AUTHORITY),
        "compiler_generated_at": compiler_generated_at,
        "latest_source_retrieved_at": after.get("latest_retrieved_at"),
        "latest_source_filing_date": after.get("latest_filing_date"),
        "store_id": ingestion_run.get("store_id"),
        "counters": {
            **counters,
            "compiled_events": compiled_events,
        },
        "source_high_watermark_before": dict(
            ingestion_run.get("source_high_watermark_before") or {}
        ),
        "source_high_watermark_after": after,
        "census": census_attempts(attempts),
        "backlog": backlog,
        "verdict": ingestion_run.get("verdict"),
        "verdict_reason": ingestion_run.get("verdict_reason"),
        "no_new_work_proven": bool(ingestion_run.get("no_new_work_proven")),
        "no_new_work_reason": ingestion_run.get("no_new_work_reason"),
    }
    if horizon is not None:
        record["horizon"] = dict(horizon)
    return record


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def _load_attempts(root: Path) -> list[dict[str, Any]]:
    path = root / "retrieval_attempts.parquet"
    if not path.exists():
        return []
    import pandas as pd

    frame = pd.read_parquet(path)
    return [
        {str(key): _native(value) for key, value in row.items()}
        for row in frame.to_dict("records")
    ]


def evaluate_health(root: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    """Build the health artifact from on-disk collector and compiler outputs."""
    from engine.capital_structure.source_ledger_io import (
        read_source_ledger,
        source_ledger_path,
    )

    now = generated_at or _utc_now_iso()
    import pandas as pd

    ingestion_run = _load_json(root / INGESTION_RUN_FILENAME)
    if ingestion_run is None:
        manifests = read_source_ledger(source_ledger_path(root))
        watermark = source_high_watermark(manifests)
        queue = _load_json(root / "retrieval_queue_receipt.json") or {}
        selected = int(queue.get("selected_count") or 0)
        ingestion_run = build_ingestion_run(
            as_of=now,
            store_id=None,
            selected=selected,
            retrieved=0,
            verified_retained=0,
            manifested=0,
            deferred=selected,
            parser_deferred=0,
            storage_deferred=selected if selected else 0,
            parked=0,
            watermark_before=watermark,
            watermark_after=watermark,
            no_new_work_proven=selected == 0,
            no_new_work_reason="queue selected no new filings" if selected == 0 else None,
        )
    telemetry = _load_json(root / "telemetry.json") or {}
    discovery_path = root / "discovery.parquet"
    coverage_path = root / "index_coverage.parquet"
    events_path = root / "event_versions.parquet"

    def rows(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        frame = pd.read_parquet(path)
        return [
            {str(key): _native(value) for key, value in row.items()}
            for row in frame.to_dict("records")
        ]

    manifests = read_source_ledger(source_ledger_path(root))
    queue_receipt = _load_json(root / "retrieval_queue_receipt.json")
    horizon = calculate_horizon(
        discovery=rows(discovery_path),
        index_coverage=rows(coverage_path),
        manifests=manifests,
        events=rows(events_path),
        telemetry=telemetry,
        queue_receipt=queue_receipt,
        ingestion_run=ingestion_run,
        calculated_at=now,
    )
    compiled_events = (telemetry.get("counts") or {}).get("event_versions")
    if compiled_events is not None:
        compiled_events = int(compiled_events)
    record = build_health_record(
        generated_at=now,
        ingestion_run=ingestion_run,
        attempts=_load_attempts(root),
        compiled_events=compiled_events,
        compiler_generated_at=telemetry.get("as_of"),
        queue_receipt=queue_receipt,
        horizon=horizon,
    )
    _validate_health(record)
    return record


def _schema_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "capital_structure_ingestion_health.schema.json"
    )


def _validate_health(record: Mapping[str, Any]) -> None:
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(record),
        key=lambda error: list(error.path),
    )
    if errors:
        raise ValueError(
            "capital-structure health artifact failed schema: "
            + "; ".join(error.message for error in errors)
        )


def write_health(record: Mapping[str, Any], path: Path) -> None:
    _validate_health(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def health_exit_code(record: Mapping[str, Any]) -> int:
    return 1 if record.get("verdict") == "fail" else 0
