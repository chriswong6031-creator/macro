"""Closed public contracts for the Company Institutional Context sidecar.

This is a deterministic 13F *context* projection.  It deliberately carries
coverage and public-filing receipts beside every descriptive observation so a
consumer cannot accidentally turn a partly-filed quarter into a consensus.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping

from engine.company_intelligence.contracts import ContractError, iso_timestamp, parse_date, safe_ticker


CONTEXT_SCHEMA = "company_institutional_context.v1"
MANIFEST_SCHEMA = "company_institutional_context_manifest.v1"
AUTHORITY = "context_only"

_SHA = re.compile(r"^[0-9a-f]{64}$")
_GENERATION = re.compile(r"^[0-9a-f]{24,64}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_CONTEXT_KEYS = frozenset({
    "schema", "authority", "generated_at", "generation_id", "status", "company",
    "company_intelligence", "period", "coverage", "positions", "consensus", "trend", "warnings",
})
_COMPANY_KEYS = frozenset({"ticker"})
_CI_KEYS = frozenset({"generation_id", "context_sha256", "latest_event_id", "latest_event_call_date"})
_PERIOD_KEYS = frozenset({
    "build_as_of", "consensus_period", "comparison_period", "filing_window_closed_on",
    "consensus_available_on", "latest_reporting_filing_date",
})
_COVERAGE_KEYS = frozenset({
    "configured_manager_count", "active_manager_count", "closed_manager_count",
    "reporting_manager_count", "missing_manager_count", "comparison_reporting_manager_count",
    "comparison_missing_manager_count", "resolved_position_count", "unresolved_position_count",
})
_POSITION_KEYS = frozenset({
    "manager", "manager_name", "manager_style", "manager_grade", "action", "is_current_holder",
    "value_usd", "book_weight_pct", "shares", "shares_change_pct", "period_end", "filing_date", "snapshot",
})
_SNAPSHOT_KEYS = frozenset({"path", "sha256", "bytes"})
_CONSENSUS_KEYS = frozenset({
    "current_holder_count", "buyer_count", "trimmer_count", "exit_count", "unknown_move_count",
    "total_value_usd", "ownership_hhi", "max_book_weight_pct", "avg_book_weight_pct",
})
_TREND_KEYS = frozenset({"status", "direction", "eligible_period_count", "periods"})
_TREND_PERIOD_KEYS = frozenset({
    "period_end", "available_on", "reporting_manager_count", "missing_manager_count",
    "holder_count", "total_value_usd", "eligible",
})
_MANIFEST_KEYS = frozenset({
    "schema", "generation_id", "generated_at", "company_count", "covered_company_count",
    "position_record_count", "consensus_period", "coverage", "source", "files", "status", "warnings",
})
_MANIFEST_COVERAGE_KEYS = frozenset({
    "configured_manager_count", "active_manager_count", "closed_manager_count",
    "reporting_manager_count", "missing_manager_count", "comparison_reporting_manager_count",
    "comparison_missing_manager_count", "resolved_position_count", "unresolved_position_count",
})
_SOURCE_KEYS = frozenset({"company_intelligence", "smart_money_config", "share_class_equivalence", "universe_membership", "snapshot_index", "builder"})
_CI_SOURCE_KEYS = frozenset({"generation_id", "sha256"})
_HASH_SOURCE_KEYS = frozenset({"sha256"})
_SNAPSHOT_SOURCE_KEYS = frozenset({"sha256", "snapshot_count", "manager_count"})
_FILE_KEYS = frozenset({"sha256", "bytes"})
_WARNINGS = frozenset({
    "current_snapshots_missing", "comparison_snapshots_missing", "resolution_partial", "history_coverage_incomplete",
})


def canonical_json_bytes(payload: object) -> bytes:
    try:
        return json.dumps(payload, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    except (TypeError, ValueError) as exc:
        raise ContractError(f"payload is not canonical JSON: {exc}") from exc


def canonical_json_sha256(payload: object) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


def bytes_sha256(path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def company_filename(ticker: object) -> str:
    return f"companies/{safe_ticker(ticker)}.json"


def _map(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: frozenset[str], name: str) -> None:
    if set(value) != expected:
        missing, unknown = sorted(expected - set(value)), sorted(set(value) - expected)
        parts = ([f"missing={missing}"] if missing else []) + ([f"unsupported={unknown}"] if unknown else [])
        raise ContractError(f"{name} fields mismatch ({', '.join(parts)})")


def _sha(value: object, name: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ContractError(f"{name} must be sha256 hex")


def _generation(value: object, name: str) -> None:
    if not isinstance(value, str) or not _GENERATION.fullmatch(value):
        raise ContractError(f"{name} invalid")


def _date(value: object, name: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ContractError(f"{name} must be ISO date")
    parse_date(value, field=name)


def _count(value: object, name: str, *, maximum: int = 100_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ContractError(f"{name} invalid")
    return value


def _number(value: object, name: str, *, nullable: bool = False, minimum: float | None = None, maximum: float = 1e16) -> None:
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractError(f"{name} invalid")
    if abs(float(value)) > maximum or (minimum is not None and float(value) < minimum):
        raise ContractError(f"{name} out of bounds")


def _text(value: object, name: str, *, maximum: int = 240) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise ContractError(f"{name} invalid")
    return value


def _ci_pin(value: object, name: str) -> None:
    item = _map(value, name)
    _keys(item, _CI_KEYS, name)
    _generation(item.get("generation_id"), f"{name}.generation_id")
    _sha(item.get("context_sha256"), f"{name}.context_sha256")
    event_id, event_date = item.get("latest_event_id"), item.get("latest_event_call_date")
    if (event_id is None) != (event_date is None):
        raise ContractError(f"{name} latest event identity must be jointly null or present")
    if event_id is not None:
        _text(event_id, f"{name}.latest_event_id", maximum=128)
        if not isinstance(event_date, str) or iso_timestamp(event_date) is None:
            raise ContractError(f"{name}.latest_event_call_date invalid")


def _coverage(value: object, name: str) -> None:
    item = _map(value, name)
    _keys(item, _COVERAGE_KEYS, name)
    values = {field: _count(item.get(field), f"{name}.{field}") for field in _COVERAGE_KEYS}
    if values["configured_manager_count"] != values["active_manager_count"] + values["closed_manager_count"]:
        raise ContractError(f"{name} configured/active/closed counts mismatch")
    if values["active_manager_count"] != values["reporting_manager_count"] + values["missing_manager_count"]:
        raise ContractError(f"{name} current reporting counts mismatch")
    if values["active_manager_count"] != values["comparison_reporting_manager_count"] + values["comparison_missing_manager_count"]:
        raise ContractError(f"{name} comparison reporting counts mismatch")


def _position(value: object, name: str) -> None:
    item = _map(value, name)
    _keys(item, _POSITION_KEYS, name)
    manager = _text(item.get("manager"), f"{name}.manager", maximum=96)
    if not _SLUG.fullmatch(manager):
        raise ContractError(f"{name}.manager invalid")
    _text(item.get("manager_name"), f"{name}.manager_name")
    _text(item.get("manager_style"), f"{name}.manager_style", maximum=96)
    _text(item.get("manager_grade"), f"{name}.manager_grade", maximum=96)
    if item.get("action") not in {"new", "add", "hold", "trim", "exit", "unavailable"}:
        raise ContractError(f"{name}.action invalid")
    if not isinstance(item.get("is_current_holder"), bool):
        raise ContractError(f"{name}.is_current_holder invalid")
    if item["action"] == "exit" and item["is_current_holder"]:
        raise ContractError(f"{name}.exit cannot be current holder")
    if item["action"] != "exit" and not item["is_current_holder"]:
        raise ContractError(f"{name}.non-exit must be current holder")
    _number(item.get("value_usd"), f"{name}.value_usd", minimum=0)
    _number(item.get("book_weight_pct"), f"{name}.book_weight_pct", minimum=0, maximum=100)
    _number(item.get("shares"), f"{name}.shares", minimum=0)
    _number(item.get("shares_change_pct"), f"{name}.shares_change_pct", nullable=True, maximum=1e7)
    _date(item.get("period_end"), f"{name}.period_end")
    _date(item.get("filing_date"), f"{name}.filing_date")
    snapshot = _map(item.get("snapshot"), f"{name}.snapshot")
    _keys(snapshot, _SNAPSHOT_KEYS, f"{name}.snapshot")
    path = _text(snapshot.get("path"), f"{name}.snapshot.path", maximum=320)
    if not path.startswith("data/smart_money/") or not path.endswith(".parquet") or ".." in path:
        raise ContractError(f"{name}.snapshot.path invalid")
    _sha(snapshot.get("sha256"), f"{name}.snapshot.sha256")
    if _count(snapshot.get("bytes"), f"{name}.snapshot.bytes", maximum=1_000_000_000) <= 0:
        raise ContractError(f"{name}.snapshot.bytes invalid")


def _consensus(value: object, name: str, positions: list[Mapping[str, Any]]) -> None:
    item = _map(value, name)
    _keys(item, _CONSENSUS_KEYS, name)
    for key in ("current_holder_count", "buyer_count", "trimmer_count", "exit_count", "unknown_move_count"):
        _count(item.get(key), f"{name}.{key}")
    current = [position for position in positions if position["is_current_holder"]]
    if item["current_holder_count"] != len(current):
        raise ContractError(f"{name}.current_holder_count mismatch")
    if item["buyer_count"] != sum(position["action"] in {"new", "add"} for position in current):
        raise ContractError(f"{name}.buyer_count mismatch")
    if item["trimmer_count"] != sum(position["action"] == "trim" for position in current):
        raise ContractError(f"{name}.trimmer_count mismatch")
    if item["exit_count"] != sum(position["action"] == "exit" for position in positions):
        raise ContractError(f"{name}.exit_count mismatch")
    if item["unknown_move_count"] != sum(position["action"] == "unavailable" for position in current):
        raise ContractError(f"{name}.unknown_move_count mismatch")
    _number(item.get("total_value_usd"), f"{name}.total_value_usd", minimum=0)
    _number(item.get("ownership_hhi"), f"{name}.ownership_hhi", nullable=True, minimum=0, maximum=1)
    _number(item.get("max_book_weight_pct"), f"{name}.max_book_weight_pct", nullable=True, minimum=0, maximum=100)
    _number(item.get("avg_book_weight_pct"), f"{name}.avg_book_weight_pct", nullable=True, minimum=0, maximum=100)


def _trend(value: object, name: str, active_count: int) -> None:
    item = _map(value, name)
    _keys(item, _TREND_KEYS, name)
    if item.get("status") not in {"available", "insufficient_coverage", "no_history"}:
        raise ContractError(f"{name}.status invalid")
    if item.get("direction") not in {"accumulating", "distributing", "stable", None}:
        raise ContractError(f"{name}.direction invalid")
    _count(item.get("eligible_period_count"), f"{name}.eligible_period_count", maximum=64)
    periods = item.get("periods")
    if not isinstance(periods, list) or len(periods) > 20:
        raise ContractError(f"{name}.periods invalid")
    prior = ""
    eligible = 0
    for index, raw in enumerate(periods):
        point = _map(raw, f"{name}.periods[{index}]")
        _keys(point, _TREND_PERIOD_KEYS, f"{name}.periods[{index}]")
        period = point.get("period_end")
        _date(period, f"{name}.periods[{index}].period_end")
        if str(period) <= prior:
            raise ContractError(f"{name}.periods must be sorted uniquely")
        prior = str(period)
        _date(point.get("available_on"), f"{name}.periods[{index}].available_on", nullable=True)
        reporting = _count(point.get("reporting_manager_count"), f"{name}.periods[{index}].reporting_manager_count")
        missing = _count(point.get("missing_manager_count"), f"{name}.periods[{index}].missing_manager_count")
        if reporting + missing != active_count:
            raise ContractError(f"{name}.periods[{index}] coverage mismatch")
        _count(point.get("holder_count"), f"{name}.periods[{index}].holder_count")
        _number(point.get("total_value_usd"), f"{name}.periods[{index}].total_value_usd", minimum=0)
        if not isinstance(point.get("eligible"), bool) or point["eligible"] != (missing == 0 and point["available_on"] is not None):
            raise ContractError(f"{name}.periods[{index}].eligible invalid")
        eligible += int(point["eligible"])
    if item["eligible_period_count"] != eligible:
        raise ContractError(f"{name}.eligible_period_count mismatch")
    if item["status"] == "available" and (eligible < 2 or item["direction"] is None):
        raise ContractError(f"{name}.available requires two coverage-aligned periods and direction")
    if item["status"] != "available" and item["direction"] is not None:
        raise ContractError(f"{name}.unavailable must not assert direction")


def validate_context(payload: object) -> None:
    item = _map(payload, "context")
    _keys(item, _CONTEXT_KEYS, "context")
    if item.get("schema") != CONTEXT_SCHEMA or item.get("authority") != AUTHORITY:
        raise ContractError("institutional context schema/authority mismatch")
    _generation(item.get("generation_id"), "context.generation_id")
    if iso_timestamp(item.get("generated_at")) is None:
        raise ContractError("context.generated_at invalid")
    if item.get("status") not in {"ready", "partial", "no_covered_holder"}:
        raise ContractError("context.status invalid")
    company = _map(item.get("company"), "context.company")
    _keys(company, _COMPANY_KEYS, "context.company")
    safe_ticker(company.get("ticker"))
    _ci_pin(item.get("company_intelligence"), "context.company_intelligence")
    period = _map(item.get("period"), "context.period")
    _keys(period, _PERIOD_KEYS, "context.period")
    for field in _PERIOD_KEYS:
        _date(period.get(field), f"context.period.{field}", nullable=field in {"consensus_available_on", "latest_reporting_filing_date"})
    build_as_of = parse_date(period["build_as_of"], field="context.period.build_as_of")
    if period["comparison_period"] >= period["consensus_period"] or period["filing_window_closed_on"] < period["consensus_period"]:
        raise ContractError("context.period chronology invalid")
    if parse_date(period["filing_window_closed_on"], field="context.period.filing_window_closed_on") > build_as_of:
        raise ContractError("context.period filing window cannot close after build cutoff")
    consensus_end = parse_date(period["consensus_period"], field="context.period.consensus_period")
    for field in ("consensus_available_on", "latest_reporting_filing_date"):
        if period[field] is not None:
            availability = parse_date(period[field], field=f"context.period.{field}")
            if availability <= consensus_end:
                raise ContractError("context.period availability must be a public filing date after period end")
            if availability > build_as_of:
                raise ContractError("context.period availability cannot be after build cutoff")
    _coverage(item.get("coverage"), "context.coverage")
    coverage = item["coverage"]
    if (period["consensus_available_on"] is None) != bool(coverage["missing_manager_count"]):
        raise ContractError("context.period consensus availability must match reporting coverage")
    if period["consensus_available_on"] is not None and period["consensus_available_on"] != period["latest_reporting_filing_date"]:
        raise ContractError("context.period consensus availability must equal latest reporting filing date")
    positions = item.get("positions")
    if not isinstance(positions, list) or len(positions) > coverage["active_manager_count"]:
        raise ContractError("context.positions invalid")
    seen: set[str] = set()
    for index, raw in enumerate(positions):
        _position(raw, f"context.positions[{index}]")
        if parse_date(raw["filing_date"], field=f"context.positions[{index}].filing_date") > build_as_of:
            raise ContractError("context.positions filing date cannot be after build cutoff")
        manager = raw["manager"]
        if manager in seen:
            raise ContractError("context.positions manager duplicate")
        seen.add(manager)
    if positions != sorted(positions, key=lambda p: (p["action"], p["manager"])):
        raise ContractError("context.positions must be sorted")
    _consensus(item.get("consensus"), "context.consensus", positions)
    _trend(item.get("trend"), "context.trend", coverage["active_manager_count"])
    for index, point in enumerate(item["trend"]["periods"]):
        if point["available_on"] is not None and parse_date(
            point["available_on"], field=f"context.trend.periods[{index}].available_on"
        ) > build_as_of:
            raise ContractError("context.trend availability cannot be after build cutoff")
    warnings = item.get("warnings")
    if not isinstance(warnings, list) or warnings != sorted(set(warnings)) or any(w not in _WARNINGS for w in warnings):
        raise ContractError("context.warnings invalid")
    expected = []
    if coverage["missing_manager_count"]:
        expected.append("current_snapshots_missing")
    if coverage["comparison_missing_manager_count"]:
        expected.append("comparison_snapshots_missing")
    if coverage["unresolved_position_count"]:
        expected.append("resolution_partial")
    if item["trend"]["status"] == "insufficient_coverage":
        expected.append("history_coverage_incomplete")
    if warnings != sorted(expected):
        raise ContractError("context.warnings coverage mismatch")
    current_holders = item["consensus"]["current_holder_count"]
    if (item["status"] == "no_covered_holder") != (current_holders == 0):
        raise ContractError("context no-covered-holder status mismatch")
    if item["status"] == "ready" and warnings:
        raise ContractError("ready context cannot carry warnings")
    if item["status"] == "partial" and not warnings:
        raise ContractError("partial context requires warnings")


def validate_manifest(payload: object, *, allow_unmaterialized_files: bool = False) -> None:
    item = _map(payload, "manifest")
    _keys(item, _MANIFEST_KEYS, "manifest")
    if item.get("schema") != MANIFEST_SCHEMA:
        raise ContractError("manifest schema mismatch")
    _generation(item.get("generation_id"), "manifest.generation_id")
    if iso_timestamp(item.get("generated_at")) is None:
        raise ContractError("manifest.generated_at invalid")
    for field in ("company_count", "covered_company_count", "position_record_count"):
        _count(item.get(field), f"manifest.{field}", maximum=1_000_000)
    if item["covered_company_count"] > item["company_count"]:
        raise ContractError("manifest covered company count invalid")
    _date(item.get("consensus_period"), "manifest.consensus_period")
    coverage = _map(item.get("coverage"), "manifest.coverage")
    _keys(coverage, _MANIFEST_COVERAGE_KEYS, "manifest.coverage")
    _coverage(coverage, "manifest.coverage")
    source = _map(item.get("source"), "manifest.source")
    _keys(source, _SOURCE_KEYS, "manifest.source")
    ci = _map(source.get("company_intelligence"), "manifest.source.company_intelligence")
    _keys(ci, _CI_SOURCE_KEYS, "manifest.source.company_intelligence")
    _generation(ci.get("generation_id"), "manifest source company intelligence generation")
    _sha(ci.get("sha256"), "manifest source company intelligence sha")
    for key in ("smart_money_config", "share_class_equivalence", "universe_membership"):
        block = _map(source.get(key), f"manifest.source.{key}")
        _keys(block, _HASH_SOURCE_KEYS, f"manifest.source.{key}")
        _sha(block.get("sha256"), f"manifest source {key} sha")
    snapshots = _map(source.get("snapshot_index"), "manifest.source.snapshot_index")
    _keys(snapshots, _SNAPSHOT_SOURCE_KEYS, "manifest.source.snapshot_index")
    _sha(snapshots.get("sha256"), "manifest source snapshot index sha")
    _count(snapshots.get("snapshot_count"), "manifest source snapshot count", maximum=100_000)
    _count(snapshots.get("manager_count"), "manifest source snapshot manager count", maximum=10_000)
    if source.get("builder") != CONTEXT_SCHEMA:
        raise ContractError("manifest source builder invalid")
    files = _map(item.get("files"), "manifest.files")
    if len(files) != item["company_count"] and not (allow_unmaterialized_files and not files):
        raise ContractError("manifest company_count must match files")
    for relative, receipt in files.items():
        if not isinstance(relative, str) or not relative.startswith("companies/") or not relative.endswith(".json"):
            raise ContractError("manifest file path invalid")
        company_filename(relative[len("companies/"):-5])
        block = _map(receipt, f"manifest file {relative}")
        _keys(block, _FILE_KEYS, f"manifest file {relative}")
        _sha(block.get("sha256"), f"manifest file {relative} sha")
        if _count(block.get("bytes"), f"manifest file {relative} bytes", maximum=100_000_000) <= 0:
            raise ContractError("manifest file bytes invalid")
    if item.get("status") not in {"ready", "partial", "empty"}:
        raise ContractError("manifest.status invalid")
    if item["status"] == "empty" and (item["company_count"] or item["covered_company_count"] or item["position_record_count"]):
        raise ContractError("empty manifest must have zero counts")
    if item["status"] != "empty" and item["company_count"] == 0:
        raise ContractError("nonempty manifest must have companies")
    warnings = item.get("warnings")
    if not isinstance(warnings, list) or warnings != sorted(set(warnings)) or any(w not in _WARNINGS for w in warnings):
        raise ContractError("manifest.warnings invalid")
    expected = []
    if coverage["missing_manager_count"]:
        expected.append("current_snapshots_missing")
    if coverage["comparison_missing_manager_count"]:
        expected.append("comparison_snapshots_missing")
    if coverage["unresolved_position_count"]:
        expected.append("resolution_partial")
    if item["status"] == "ready" and warnings:
        raise ContractError("ready manifest cannot carry warnings")
    if item["status"] == "partial" and not warnings:
        raise ContractError("partial manifest requires warnings")
