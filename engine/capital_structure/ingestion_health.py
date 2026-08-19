"""Capital Structure ingestion health: census, watermarks, and run verdict.

This module is the truth plane for whether a collector run actually retained
durable verified evidence. Compiler ``telemetry.as_of`` is generation time and
must not be treated as source freshness.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

HEALTH_SCHEMA = "capital_structure.ingestion_health/v1"
INGESTION_RUN_SCHEMA = "capital_structure.ingestion_run/v1"
HEALTH_FILENAME = "health.json"
INGESTION_RUN_FILENAME = "ingestion_run.json"

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
        return value != value
    except Exception:  # noqa: BLE001 - pandas NA raises on equality
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
    return {
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


def build_health_record(
    *,
    generated_at: str,
    ingestion_run: Mapping[str, Any],
    attempts: Sequence[Mapping[str, Any]],
    compiled_events: int | None,
    compiler_generated_at: str | None,
    queue_receipt: Mapping[str, Any] | None = None,
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
    return {
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
    compiled_events = (telemetry.get("counts") or {}).get("event_versions")
    if compiled_events is not None:
        compiled_events = int(compiled_events)
    queue_receipt = _load_json(root / "retrieval_queue_receipt.json")
    record = build_health_record(
        generated_at=now,
        ingestion_run=ingestion_run,
        attempts=_load_attempts(root),
        compiled_events=compiled_events,
        compiler_generated_at=telemetry.get("as_of"),
        queue_receipt=queue_receipt,
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
