"""Pure ClinicalTrials.gov discovery control contracts.

No transport, storage, activation, or projection code belongs here.  The
module accepts already-bounded page metadata and proves only what that metadata
supports: an inclusive source-date selection, a stable source cut, and a
receipt-time knowledge boundary.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import re
from typing import Any, Mapping, Sequence

from engine.sector_intelligence import canonical_json_bytes, canonical_json_sha256, validate_contract
from engine.sector_intelligence.contracts import ContractError, ContractValidationError, ValidationIssue


DISCOVERY_SCOPE_CONTRACT_ID = "ctgov_discovery_scope.v1"
DISCOVERY_RUN_CONTRACT_ID = "ctgov_discovery_run.v1"
DISCOVERY_COVERAGE_CONTRACT_ID = "ctgov_discovery_coverage_epoch.v1"

_SOURCE_ID = "clinicaltrials_gov_v2"
_NCT_RE = re.compile(r"^NCT[0-9]{8}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_SOURCE_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})?$"
)

MAX_PAGE_SIZE = 1000
MAX_PAGES = 2048
MAX_RECORDS = 200_000
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 256 * 1024
DEFAULT_RECORD_BYTES = 64 * 1024
MAX_TOKEN_BYTES = 512
MAX_STRING_BYTES = 4096
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MAX_JSON_CONTAINER_ITEMS = 10_000
MAX_WINDOW_DAYS = 366
_MINIMAL_FIELDS = (
    "protocolSection.identificationModule.nctId",
    "protocolSection.statusModule.lastUpdatePostDateStruct.date",
)

_CODE_BY_CONDITION = {
    "page_chain_invalid": "DISCOVERY_PAGE_CHAIN_INVALID",
    "total_count_mismatch": "DISCOVERY_TOTAL_COUNT_MISMATCH",
    "source_version_race": "DISCOVERY_SOURCE_VERSION_RACE",
    "source_version_incomplete": "DISCOVERY_SOURCE_VERSION_INCOMPLETE",
    "duplicate_content_ambiguity": "DISCOVERY_DUPLICATE_CONTENT_AMBIGUITY",
    "scope_selection_violation": "DISCOVERY_SCOPE_SELECTION_VIOLATION",
    "time_chain_invalid": "DISCOVERY_TIME_CHAIN_INVALID",
}
_STATE_PRIORITY = (
    "source_version_race",
    "source_version_incomplete",
    "duplicate_content_ambiguity",
    "page_chain_invalid",
    "total_count_mismatch",
    "scope_selection_violation",
    "time_chain_invalid",
)


class DiscoveryError(ValueError):
    """A bounded, fail-closed construction error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _copy_json(value: Any, *, code: str) -> Any:
    try:
        return json.loads(canonical_json_bytes(value))
    except (ContractError, TypeError, ValueError, RecursionError, MemoryError) as exc:
        raise DiscoveryError(code) from exc


def _require_string(value: object, *, cap: int, code: str) -> str:
    if not isinstance(value, str):
        raise DiscoveryError(code)
    try:
        if not value or len(value.encode("utf-8")) > cap:
            raise DiscoveryError(code)
    except UnicodeEncodeError as exc:
        raise DiscoveryError(code) from exc
    return value


def _require_int(value: object, *, lower: int, upper: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise DiscoveryError(code)
    return value


def _parse_date(value: object, *, code: str) -> date:
    if not isinstance(value, str):
        raise DiscoveryError(code)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DiscoveryError(code) from exc


def _parse_datetime(value: object, *, code: str) -> datetime:
    if not isinstance(value, str):
        raise DiscoveryError(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise DiscoveryError(code) from exc
    if parsed.tzinfo is None:
        raise DiscoveryError(code)
    return parsed


def _safe_datetime(value: object) -> datetime | None:
    try:
        return _parse_datetime(value, code="DISCOVERY_TIME_INVALID")
    except DiscoveryError:
        return None


def _require_hash(value: object, *, code: str) -> str:
    value = _require_string(value, cap=64, code=code)
    if _SHA256_RE.fullmatch(value) is None:
        raise DiscoveryError(code)
    return value


def _require_nct_id(value: object, *, code: str) -> str:
    value = _require_string(value, cap=11, code=code)
    if _NCT_RE.fullmatch(value) is None:
        raise DiscoveryError(code)
    return value


def _require_source_timestamp(value: object, *, code: str) -> str:
    value = _require_string(value, cap=32, code=code)
    if _SOURCE_TIMESTAMP_RE.fullmatch(value) is None:
        raise DiscoveryError(code)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise DiscoveryError(code) from exc
    return value


def _window(start: object, end: object, *, code: str) -> tuple[date, date]:
    parsed_start = _parse_date(start, code=code)
    parsed_end = _parse_date(end, code=code)
    if parsed_start > parsed_end:
        raise DiscoveryError(code)
    return parsed_start, parsed_end


def _safe_window(value: object) -> tuple[date, date] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return _window(value.get("start_date"), value.get("end_date"), code="DISCOVERY_WINDOW_INVALID")
    except DiscoveryError:
        return None


def _window_dict(start: date, end: date) -> dict[str, str]:
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


def _query_expression(start: str, end: str) -> str:
    return f"AREA[LastUpdatePostDate]RANGE[{start},{end}]"


def _selection_issues(value: object, *, path: str, require_window_cap: bool) -> list[ValidationIssue]:
    if not isinstance(value, Mapping):
        return []
    issues: list[ValidationIssue] = []
    start_raw, end_raw = value.get("start_date"), value.get("end_date")
    start = end = None
    try:
        start = _parse_date(start_raw, code="DISCOVERY_WINDOW_INVALID")
        end = _parse_date(end_raw, code="DISCOVERY_WINDOW_INVALID")
    except DiscoveryError:
        return issues  # Schema reports malformed dates.
    if start > end:
        issues.append(ValidationIssue(path, "discovery.window_order", "start_date must not be later than end_date"))
        return issues
    if require_window_cap and (end - start).days + 1 > MAX_WINDOW_DAYS:
        issues.append(ValidationIssue(path, "discovery.window_bound", f"selection windows may span at most {MAX_WINDOW_DAYS} days"))
    if value.get("query_expression") != _query_expression(str(start_raw), str(end_raw)):
        issues.append(ValidationIssue(f"{path}.query_expression", "discovery.query_expression", "query_expression must exactly bind the inclusive source-date window"))
    return issues


def _hash_issue(document: Mapping[str, Any], *, field: str, code: str) -> ValidationIssue | None:
    value = document.get(field)
    if not isinstance(value, str):
        return None
    try:
        expected = canonical_json_sha256({key: item for key, item in document.items() if key != field})
    except ContractError:
        return ValidationIssue(f"$.{field}", code, "document must be finite canonical JSON")
    if value != expected:
        return ValidationIssue(f"$.{field}", code, "declared digest does not match the canonical payload")
    return None


def _normalise_record(value: object, *, record_byte_cap: int, string_byte_cap: int) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise DiscoveryError("DISCOVERY_RECORD_INVALID")
    record = {
        "nct_id": _require_nct_id(value.get("nct_id"), code="DISCOVERY_RECORD_ID_INVALID"),
        "canonical_content_sha256": _require_hash(value.get("canonical_content_sha256"), code="DISCOVERY_RECORD_HASH_INVALID"),
        "last_update_posted_date": _require_string(value.get("last_update_posted_date"), cap=min(10, string_byte_cap), code="DISCOVERY_RECORD_DATE_INVALID"),
    }
    _parse_date(record["last_update_posted_date"], code="DISCOVERY_RECORD_DATE_INVALID")
    try:
        if len(canonical_json_bytes(record)) > record_byte_cap:
            raise DiscoveryError("DISCOVERY_RECORD_BYTES_EXCEEDED")
    except ContractError as exc:
        raise DiscoveryError("DISCOVERY_RECORD_INVALID") from exc
    return record


def _normalise_page(value: object, *, query: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DiscoveryError("DISCOVERY_PAGE_INVALID")
    records_value = value.get("records")
    if not isinstance(records_value, (list, tuple)):
        raise DiscoveryError("DISCOVERY_PAGE_RECORDS_INVALID")
    if len(records_value) > query["page_record_cap"]:
        raise DiscoveryError("DISCOVERY_PAGE_SIZE_EXCEEDED")
    records = [
        _normalise_record(
            item,
            record_byte_cap=query["record_byte_cap"],
            string_byte_cap=query["string_byte_cap"],
        )
        for item in records_value
    ]
    records.sort(key=lambda row: (row["nct_id"], row["canonical_content_sha256"], row["last_update_posted_date"]))

    def token(name: str) -> str | None:
        raw = value.get(name)
        if raw is None:
            return None
        parsed = _require_hash(raw, code="DISCOVERY_TOKEN_INVALID")
        if len(parsed.encode("utf-8")) > query["token_byte_cap"]:
            raise DiscoveryError("DISCOVERY_TOKEN_BYTES_EXCEEDED")
        return parsed

    total_count = value.get("total_count")
    if total_count is not None:
        total_count = _require_int(total_count, lower=0, upper=query["record_cap"], code="DISCOVERY_TOTAL_COUNT_INVALID")
    received_at = _require_string(value.get("received_at"), cap=query["string_byte_cap"], code="DISCOVERY_RECEIPT_TIME_INVALID")
    _parse_datetime(received_at, code="DISCOVERY_RECEIPT_TIME_INVALID")
    return {
        "page_ordinal": _require_int(value.get("page_ordinal"), lower=0, upper=query["page_cap"] - 1, code="DISCOVERY_PAGE_ORDINAL_INVALID"),
        "response_sha256": _require_hash(value.get("response_sha256"), code="DISCOVERY_PAGE_HASH_INVALID"),
        "byte_count": _require_int(value.get("byte_count"), lower=0, upper=query["per_page_byte_cap"], code="DISCOVERY_PAGE_BYTES_EXCEEDED"),
        "received_at": received_at,
        "request_page_token_sha256": token("request_page_token_sha256"),
        "next_page_token_sha256": token("next_page_token_sha256"),
        "total_count": total_count,
        "records": records,
    }


def _normalise_version(value: Mapping[str, Any] | None, *, string_byte_cap: int) -> dict[str, str | None]:
    if value is None:
        return {"data_timestamp_raw": None, "api_version": None, "retrieved_at": None}
    if not isinstance(value, Mapping):
        raise DiscoveryError("DISCOVERY_SOURCE_VERSION_INVALID")
    retrieved_at = _require_string(value.get("retrieved_at"), cap=string_byte_cap, code="DISCOVERY_VERSION_TIME_INVALID")
    _parse_datetime(retrieved_at, code="DISCOVERY_VERSION_TIME_INVALID")
    return {
        "data_timestamp_raw": _require_source_timestamp(value.get("data_timestamp_raw"), code="DISCOVERY_SOURCE_TIMESTAMP_INVALID"),
        "api_version": _require_string(value.get("api_version"), cap=min(256, string_byte_cap), code="DISCOVERY_API_VERSION_INVALID"),
        "retrieved_at": retrieved_at,
    }


def _derive_run(
    *,
    pages: Sequence[Mapping[str, Any]],
    selection_window: Mapping[str, Any],
    source_cut: Mapping[str, Any],
    started_at: object,
    finished_at: object,
    transaction_from: object,
) -> tuple[dict[str, int], list[dict[str, str]], tuple[str, ...]]:
    """Replay bounded metadata and derive its only permitted result state."""

    conditions: set[str] = set()
    if not pages:
        conditions.add("page_chain_invalid")
    expected_ordinals = list(range(len(pages)))
    if [page.get("page_ordinal") for page in pages] != expected_ordinals:
        conditions.add("page_chain_invalid")

    selection = _safe_window(selection_window)
    if selection is None:
        conditions.add("scope_selection_violation")
    previous_next: str | None = None
    seen_tokens: set[str] = set()
    total_declared: int | None = None
    records_returned = 0
    occurrences: dict[str, int] = {}
    records_by_nct: dict[str, set[tuple[str, str]]] = {}
    response_hashes: set[str] = set()
    page_times: list[datetime] = []
    for index, page in enumerate(pages):
        request_token = page.get("request_page_token_sha256")
        next_token = page.get("next_page_token_sha256")
        if request_token != previous_next:
            conditions.add("page_chain_invalid")
        if isinstance(request_token, str) and request_token in seen_tokens:
            conditions.add("page_chain_invalid")
        if isinstance(next_token, str) and (next_token == request_token or next_token in seen_tokens):
            conditions.add("page_chain_invalid")
        if index < len(pages) - 1 and next_token is None:
            conditions.add("page_chain_invalid")
        if index == len(pages) - 1 and next_token is not None:
            conditions.add("page_chain_invalid")
        if isinstance(request_token, str):
            seen_tokens.add(request_token)
        previous_next = next_token if isinstance(next_token, str) else None
        response_hash = page.get("response_sha256")
        if isinstance(response_hash, str):
            if response_hash in response_hashes:
                conditions.add("duplicate_content_ambiguity")
            response_hashes.add(response_hash)
        current_total = page.get("total_count")
        if index == 0:
            if isinstance(current_total, int) and not isinstance(current_total, bool):
                total_declared = current_total
            else:
                conditions.add("total_count_mismatch")
        elif current_total is not None and current_total != total_declared:
            conditions.add("total_count_mismatch")
        parsed_page_time = _safe_datetime(page.get("received_at"))
        if parsed_page_time is None:
            conditions.add("time_chain_invalid")
        else:
            page_times.append(parsed_page_time)
        records = page.get("records")
        if not isinstance(records, list):
            conditions.add("page_chain_invalid")
            continue
        for record in records:
            if not isinstance(record, Mapping):
                conditions.add("page_chain_invalid")
                continue
            nct_id, content, source_date = record.get("nct_id"), record.get("canonical_content_sha256"), record.get("last_update_posted_date")
            if not all(isinstance(item, str) for item in (nct_id, content, source_date)):
                conditions.add("page_chain_invalid")
                continue
            records_returned += 1
            occurrences[nct_id] = occurrences.get(nct_id, 0) + 1
            records_by_nct.setdefault(nct_id, set()).add((content, source_date))
            if selection is not None:
                try:
                    parsed_source_date = _parse_date(source_date, code="DISCOVERY_RECORD_DATE_INVALID")
                except DiscoveryError:
                    conditions.add("scope_selection_violation")
                else:
                    if not selection[0] <= parsed_source_date <= selection[1]:
                        conditions.add("scope_selection_violation")
    if any(count > 1 for count in occurrences.values()) or any(len(items) != 1 for items in records_by_nct.values()):
        conditions.add("duplicate_content_ambiguity")
    if total_declared is None or total_declared != len(records_by_nct):
        conditions.add("total_count_mismatch")

    required_source_values = (
        source_cut.get("dataset_timestamp_before_raw"),
        source_cut.get("dataset_timestamp_after_raw"),
        source_cut.get("api_version_before"),
        source_cut.get("api_version_after"),
        source_cut.get("version_before_retrieved_at"),
        source_cut.get("version_after_retrieved_at"),
    )
    if any(value is None for value in required_source_values):
        conditions.add("source_version_incomplete")
    elif (
        source_cut.get("dataset_timestamp_before_raw") != source_cut.get("dataset_timestamp_after_raw")
        or source_cut.get("api_version_before") != source_cut.get("api_version_after")
    ):
        conditions.add("source_version_race")

    started = _safe_datetime(started_at)
    finished = _safe_datetime(finished_at)
    transaction = _safe_datetime(transaction_from)
    before = _safe_datetime(source_cut.get("version_before_retrieved_at"))
    after = _safe_datetime(source_cut.get("version_after_retrieved_at"))
    first_claimed = _safe_datetime(source_cut.get("first_page_receipt_retrieved_at"))
    terminal_claimed = _safe_datetime(source_cut.get("terminal_page_receipt_retrieved_at"))
    if pages:
        if not page_times or first_claimed != page_times[0]:
            conditions.add("time_chain_invalid")
        if not page_times or terminal_claimed != page_times[-1]:
            conditions.add("time_chain_invalid")
        ordered_times = [started, before, *page_times, after, finished, transaction]
        if any(item is None for item in ordered_times) or ordered_times != sorted(ordered_times):
            conditions.add("time_chain_invalid")
    elif first_claimed is not None or terminal_claimed is not None:
        conditions.add("time_chain_invalid")

    counts = {
        "pages": len(pages),
        "records_returned": records_returned,
        "records_unique": len(records_by_nct),
        "records_duplicates": records_returned - len(records_by_nct),
        "declared_total_count": 0 if total_declared is None else total_declared,
    }
    deduplicated = [
        {
            "nct_id": nct_id,
            "canonical_content_sha256": next(iter(items))[0],
            "last_update_posted_date": next(iter(items))[1],
        }
        for nct_id, items in records_by_nct.items()
    ]
    deduplicated.sort(key=lambda row: row["nct_id"])
    # A quarantined candidate must never retain a silently usable subset.
    if conditions:
        deduplicated = []
    return counts, deduplicated, tuple(sorted(conditions))


def _state(conditions: Sequence[str]) -> str:
    for candidate in _STATE_PRIORITY:
        if candidate in conditions:
            return candidate
    return "reconciled"


def _codes(conditions: Sequence[str]) -> list[str]:
    return sorted(_CODE_BY_CONDITION[condition] for condition in conditions)


def build_discovery_scope(
    *,
    selection_start_date: str,
    selection_end_date: str,
    page_size: int = 500,
    page_record_cap: int | None = None,
    page_cap: int = 400,
    per_page_byte_cap: int = MAX_PAGE_BYTES,
    total_byte_cap: int = MAX_TOTAL_BYTES,
    record_cap: int | None = None,
    record_byte_cap: int = DEFAULT_RECORD_BYTES,
    token_byte_cap: int = MAX_TOKEN_BYTES,
    string_byte_cap: int = MAX_STRING_BYTES,
    json_depth_cap: int = MAX_JSON_DEPTH,
    json_node_cap: int = MAX_JSON_NODES,
    json_container_item_cap: int = MAX_JSON_CONTAINER_ITEMS,
) -> dict[str, Any]:
    """Build one canonical inclusive ``LastUpdatePostDate`` scope."""

    start, end = _window(selection_start_date, selection_end_date, code="DISCOVERY_SELECTION_WINDOW_INVALID")
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        raise DiscoveryError("DISCOVERY_SELECTION_WINDOW_EXCEEDED")
    page_size = _require_int(page_size, lower=1, upper=MAX_PAGE_SIZE, code="DISCOVERY_PAGE_SIZE_INVALID")
    if page_record_cap is None:
        page_record_cap = page_size
    page_record_cap = _require_int(page_record_cap, lower=1, upper=page_size, code="DISCOVERY_PAGE_RECORD_CAP_INVALID")
    page_cap = _require_int(page_cap, lower=1, upper=MAX_PAGES, code="DISCOVERY_PAGE_CAP_INVALID")
    capacity = page_size * page_cap
    if record_cap is None:
        record_cap = capacity
    record_cap = _require_int(record_cap, lower=1, upper=MAX_RECORDS, code="DISCOVERY_RECORD_CAP_INVALID")
    if capacity > record_cap:
        raise DiscoveryError("DISCOVERY_CAPACITY_INCONSISTENT")
    per_page_byte_cap = _require_int(per_page_byte_cap, lower=1, upper=MAX_PAGE_BYTES, code="DISCOVERY_PAGE_BYTE_CAP_INVALID")
    total_byte_cap = _require_int(total_byte_cap, lower=1, upper=MAX_TOTAL_BYTES, code="DISCOVERY_TOTAL_BYTE_CAP_INVALID")
    if per_page_byte_cap > total_byte_cap:
        raise DiscoveryError("DISCOVERY_CAPACITY_INCONSISTENT")
    record_byte_cap = _require_int(record_byte_cap, lower=1, upper=MAX_RECORD_BYTES, code="DISCOVERY_RECORD_BYTE_CAP_INVALID")
    token_byte_cap = _require_int(token_byte_cap, lower=1, upper=MAX_TOKEN_BYTES, code="DISCOVERY_TOKEN_BYTE_CAP_INVALID")
    string_byte_cap = _require_int(string_byte_cap, lower=1, upper=MAX_STRING_BYTES, code="DISCOVERY_STRING_BYTE_CAP_INVALID")
    json_depth_cap = _require_int(json_depth_cap, lower=1, upper=MAX_JSON_DEPTH, code="DISCOVERY_JSON_DEPTH_CAP_INVALID")
    json_node_cap = _require_int(json_node_cap, lower=1, upper=MAX_JSON_NODES, code="DISCOVERY_JSON_NODE_CAP_INVALID")
    json_container_item_cap = _require_int(json_container_item_cap, lower=1, upper=MAX_JSON_CONTAINER_ITEMS, code="DISCOVERY_JSON_CONTAINER_CAP_INVALID")
    selection_window = {
        "field": "LastUpdatePostDate",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "query_expression": _query_expression(start.isoformat(), end.isoformat()),
    }
    payload: dict[str, Any] = {
        "contract_id": DISCOVERY_SCOPE_CONTRACT_ID,
        "schema_version": "1.0.0",
        "source_id": _SOURCE_ID,
        "source_native_identifier_kind": "nct_id",
        "selection_window": selection_window,
        "source_query": {
            "api_root": "https://clinicaltrials.gov/api/v2",
            "request_path": "/studies",
            "response_format": "json",
            "count_total": True,
            "page_size": page_size,
            "page_record_cap": page_record_cap,
            "page_cap": page_cap,
            "per_page_byte_cap": per_page_byte_cap,
            "total_byte_cap": total_byte_cap,
            "record_cap": record_cap,
            "record_byte_cap": record_byte_cap,
            "token_byte_cap": token_byte_cap,
            "string_byte_cap": string_byte_cap,
            "json_depth_cap": json_depth_cap,
            "json_node_cap": json_node_cap,
            "json_container_item_cap": json_container_item_cap,
            "minimal_fields": list(_MINIMAL_FIELDS),
        },
        "scope_semantics": {
            "record_set": "records_returned_for_declared_source_query_only",
            "dataset_freshness": "version_dataTimestamp_is_source_dataset_freshness_not_selection_date",
            "selection_date": "LastUpdatePostDate_is_source_selection_date_not_knowledge_time",
            "knowledge_time": "receipt_retrieved_at_is_biocatalyst_knowledge_time",
            "absence": "absence_from_declared_query_is_not_deletion",
            "global_coverage": "not_all_clinicaltrials_gov",
            "record_identity": "source_native_nct_id_only",
        },
        "hash_scope": "canonical_payload_excluding_scope_payload_sha256",
    }
    identity = canonical_json_sha256(payload)
    payload["scope_id"] = f"ctgov_discovery_scope_{identity[:24]}"
    payload["scope_payload_sha256"] = canonical_json_sha256(payload)
    return validate_discovery_scope(payload)


def reconcile_discovery_run(
    *,
    scope: Mapping[str, Any],
    run_id: str,
    pages: Sequence[Mapping[str, Any]],
    source_version_before: Mapping[str, Any] | None,
    source_version_after: Mapping[str, Any] | None,
    started_at: str,
    finished_at: str,
    transaction_from: str,
) -> dict[str, Any]:
    """Reconcile one bounded chain into a complete or quarantined candidate."""

    normalized_scope = validate_discovery_scope(scope)
    query = normalized_scope["source_query"]
    if not isinstance(pages, (list, tuple)) or len(pages) > query["page_cap"]:
        raise DiscoveryError("DISCOVERY_PAGE_CAP_EXCEEDED")
    normalized_pages: list[dict[str, Any]] = []
    total_bytes = total_records = 0
    for page in pages:
        normalized = _normalise_page(page, query=query)
        total_bytes += normalized["byte_count"]
        total_records += len(normalized["records"])
        if total_bytes > query["total_byte_cap"]:
            raise DiscoveryError("DISCOVERY_TOTAL_BYTES_EXCEEDED")
        if total_records > query["record_cap"]:
            raise DiscoveryError("DISCOVERY_RECORD_CAP_EXCEEDED")
        normalized_pages.append(normalized)
    normalized_pages.sort(key=lambda row: row["page_ordinal"])
    before = _normalise_version(source_version_before, string_byte_cap=query["string_byte_cap"])
    after = _normalise_version(source_version_after, string_byte_cap=query["string_byte_cap"])
    started_at = _require_string(started_at, cap=MAX_STRING_BYTES, code="DISCOVERY_RUN_TIME_INVALID")
    finished_at = _require_string(finished_at, cap=MAX_STRING_BYTES, code="DISCOVERY_RUN_TIME_INVALID")
    transaction_from = _require_string(transaction_from, cap=MAX_STRING_BYTES, code="DISCOVERY_TRANSACTION_TIME_INVALID")
    _parse_datetime(started_at, code="DISCOVERY_RUN_TIME_INVALID")
    _parse_datetime(finished_at, code="DISCOVERY_RUN_TIME_INVALID")
    _parse_datetime(transaction_from, code="DISCOVERY_TRANSACTION_TIME_INVALID")
    source_cut = {
        "dataset_timestamp_before_raw": before["data_timestamp_raw"],
        "dataset_timestamp_after_raw": after["data_timestamp_raw"],
        "api_version_before": before["api_version"],
        "api_version_after": after["api_version"],
        "version_before_retrieved_at": before["retrieved_at"],
        "version_after_retrieved_at": after["retrieved_at"],
        "first_page_receipt_retrieved_at": normalized_pages[0]["received_at"] if normalized_pages else None,
        "terminal_page_receipt_retrieved_at": normalized_pages[-1]["received_at"] if normalized_pages else None,
    }
    counts, deduplicated, conditions = _derive_run(
        pages=normalized_pages,
        selection_window=normalized_scope["selection_window"],
        source_cut=source_cut,
        started_at=started_at,
        finished_at=finished_at,
        transaction_from=transaction_from,
    )
    payload: dict[str, Any] = {
        "contract_id": DISCOVERY_RUN_CONTRACT_ID,
        "schema_version": "1.0.0",
        "run_id": _require_string(run_id, cap=128, code="DISCOVERY_RUN_ID_INVALID"),
        "source_id": _SOURCE_ID,
        "scope": _copy_json(normalized_scope, code="DISCOVERY_SCOPE_INVALID"),
        "scope_ref": normalized_scope["scope_id"],
        "scope_payload_sha256": normalized_scope["scope_payload_sha256"],
        "selection_window": _copy_json(normalized_scope["selection_window"], code="DISCOVERY_SCOPE_INVALID"),
        "source_cut": source_cut,
        "pages": normalized_pages,
        "deduplicated_records": deduplicated,
        "counts": counts,
        "run_state": "complete" if not conditions else "quarantined",
        "reconciliation_state": _state(conditions),
        "quarantine_codes": _codes(conditions),
        "coverage_claim": "complete_only_for_this_declared_source_query_when_reconciled",
        "started_at": started_at,
        "finished_at": finished_at,
        "transaction_from": transaction_from,
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_run_payload_sha256",
    }
    payload["run_payload_sha256"] = canonical_json_sha256(payload)
    return validate_discovery_run(payload, scope=normalized_scope)


def _partition_windows(windows: Sequence[tuple[date, date]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Calculate exact inclusive gaps and day-precision multiple coverage."""

    if not windows:
        return [], []
    deltas: dict[int, int] = {}
    for start, end in windows:
        deltas[start.toordinal()] = deltas.get(start.toordinal(), 0) + 1
        deltas[end.toordinal() + 1] = deltas.get(end.toordinal() + 1, 0) - 1
    points = sorted(deltas)
    active = 0
    gaps: list[dict[str, str]] = []
    overlaps: list[dict[str, str]] = []
    for index, ordinal in enumerate(points):
        active += deltas[ordinal]
        if index + 1 == len(points):
            continue
        next_ordinal = points[index + 1]
        if active == 0:
            gaps.append(_window_dict(date.fromordinal(ordinal), date.fromordinal(next_ordinal - 1)))
        elif active >= 2:
            overlaps.append(_window_dict(date.fromordinal(ordinal), date.fromordinal(next_ordinal - 1)))
    return gaps, overlaps


def _has_consecutive_overlap(windows: Sequence[tuple[date, date]]) -> bool:
    return all(current[0] <= previous[1] for previous, current in zip(windows, windows[1:]))


def build_discovery_coverage_epoch(
    *,
    coverage_epoch_id: str,
    runs: Sequence[Mapping[str, Any]],
    declared_start_date: str,
    declared_end_date: str,
    transaction_from: str,
) -> dict[str, Any]:
    """Build a complete atomic epoch; partial candidates are rejected."""

    if not isinstance(runs, (list, tuple)) or not runs or len(runs) > MAX_PAGES:
        raise DiscoveryError("DISCOVERY_COVERAGE_RUN_CAP_INVALID")
    declared = _window(declared_start_date, declared_end_date, code="DISCOVERY_COVERAGE_WINDOW_INVALID")
    normalized_runs = [validate_discovery_run(run) for run in runs]
    if any(run["run_state"] != "complete" or run["reconciliation_state"] != "reconciled" for run in normalized_runs):
        raise DiscoveryError("DISCOVERY_PARTIAL_COVERAGE_REFUSED")
    included = [
        {
            "run_ref": run["run_id"],
            "run_payload_sha256": run["run_payload_sha256"],
            "run_state": "complete",
            "reconciliation_state": "reconciled",
            "run_transaction_from": run["transaction_from"],
            "scope_ref": run["scope_ref"],
            "scope_payload_sha256": run["scope_payload_sha256"],
            "selection_window": _copy_json(run["selection_window"], code="DISCOVERY_RUN_INVALID"),
            "source_cut": _copy_json(run["source_cut"], code="DISCOVERY_RUN_INVALID"),
        }
        for run in normalized_runs
    ]
    included.sort(key=lambda row: (row["selection_window"]["start_date"], row["selection_window"]["end_date"], row["run_ref"]))
    if len({row["run_ref"] for row in included}) != len(included):
        raise DiscoveryError("DISCOVERY_DUPLICATE_RUN_REF")
    windows = [_safe_window(row["selection_window"]) for row in included]
    if any(window is None for window in windows):
        raise DiscoveryError("DISCOVERY_COVERAGE_SCOPE_INVALID")
    typed_windows = [window for window in windows if window is not None]
    if (min(start for start, _ in typed_windows), max(end for _, end in typed_windows)) != declared:
        raise DiscoveryError("DISCOVERY_COVERAGE_OUTSIDE_EVIDENCE")
    gaps, overlaps = _partition_windows(typed_windows)
    if gaps or (len(typed_windows) > 1 and not _has_consecutive_overlap(typed_windows)):
        raise DiscoveryError("DISCOVERY_PARTIAL_COVERAGE_REFUSED")
    payload: dict[str, Any] = {
        "contract_id": DISCOVERY_COVERAGE_CONTRACT_ID,
        "schema_version": "1.0.0",
        "coverage_epoch_id": _require_string(coverage_epoch_id, cap=128, code="DISCOVERY_COVERAGE_ID_INVALID"),
        "source_id": _SOURCE_ID,
        "source_native_identifier_kind": "nct_id",
        "declared_window": _window_dict(*declared),
        "coverage_state": "complete",
        "coverage_claim": "complete_only_for_evidenced_declared_source_query_scopes",
        "included_runs": included,
        "gap_windows": gaps,
        "overlap_windows": overlaps,
        "quarantine_codes": [],
        "transaction_from": _require_string(transaction_from, cap=MAX_STRING_BYTES, code="DISCOVERY_TRANSACTION_TIME_INVALID"),
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_coverage_payload_sha256",
    }
    _parse_datetime(payload["transaction_from"], code="DISCOVERY_TRANSACTION_TIME_INVALID")
    payload["coverage_payload_sha256"] = canonical_json_sha256(payload)
    return validate_discovery_coverage_epoch(payload, runs=normalized_runs)


def discovery_scope_contract_semantic_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    """Registry-facing semantic checks for ``ctgov_discovery_scope.v1``."""

    issues = _selection_issues(document.get("selection_window"), path="$.selection_window", require_window_cap=True)
    query = document.get("source_query")
    if isinstance(query, Mapping):
        page_size, page_cap, record_cap = query.get("page_size"), query.get("page_cap"), query.get("record_cap")
        if all(isinstance(value, int) and not isinstance(value, bool) for value in (page_size, page_cap, record_cap)) and page_size * page_cap > record_cap:
            issues.append(ValidationIssue("$.source_query", "discovery.capacity", "page_size multiplied by page_cap may not exceed record_cap"))
        for left, right, message in (
            ("per_page_byte_cap", "total_byte_cap", "per_page_byte_cap may not exceed total_byte_cap"),
            ("page_record_cap", "page_size", "page_record_cap may not exceed page_size"),
        ):
            first, second = query.get(left), query.get(right)
            if all(isinstance(value, int) and not isinstance(value, bool) for value in (first, second)) and first > second:
                issues.append(ValidationIssue("$.source_query", "discovery.capacity", message))
    issue = _hash_issue(document, field="scope_payload_sha256", code="discovery_scope.hash")
    if issue is not None:
        issues.append(issue)
    scope_id = document.get("scope_id")
    try:
        identity_payload = {key: value for key, value in document.items() if key not in {"scope_id", "scope_payload_sha256"}}
        expected_id = f"ctgov_discovery_scope_{canonical_json_sha256(identity_payload)[:24]}"
    except ContractError:
        expected_id = None
    if isinstance(scope_id, str) and expected_id is not None and scope_id != expected_id:
        issues.append(ValidationIssue("$.scope_id", "discovery_scope.identity", "scope_id must be derived from the payload excluding identity and digest"))
    return issues


def discovery_run_contract_semantic_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    """Registry-facing semantic checks for ``ctgov_discovery_run.v1``."""

    issues = _selection_issues(document.get("selection_window"), path="$.selection_window", require_window_cap=True)
    issue = _hash_issue(document, field="run_payload_sha256", code="discovery_run.hash")
    if issue is not None:
        issues.append(issue)
    embedded_scope = document.get("scope")
    if isinstance(embedded_scope, Mapping):
        try:
            bound_scope = validate_discovery_scope(embedded_scope)
        except ContractError:
            issues.append(ValidationIssue("$.scope", "discovery_run.scope_binding", "embedded scope must be independently valid"))
        else:
            expected_scope_binding = {
                "scope_ref": bound_scope["scope_id"],
                "scope_payload_sha256": bound_scope["scope_payload_sha256"],
                "selection_window": bound_scope["selection_window"],
            }
            for field, expected_value in expected_scope_binding.items():
                if document.get(field) != expected_value:
                    issues.append(ValidationIssue(f"$.{field}", "discovery_run.scope_binding", "run must exactly bind its embedded immutable scope"))
    pages, cut, window = document.get("pages"), document.get("source_cut"), document.get("selection_window")
    if not isinstance(pages, list) or not isinstance(cut, Mapping) or not isinstance(window, Mapping):
        return issues
    try:
        counts, deduplicated, conditions = _derive_run(
            pages=pages,
            selection_window=window,
            source_cut=cut,
            started_at=document.get("started_at"),
            finished_at=document.get("finished_at"),
            transaction_from=document.get("transaction_from"),
        )
    except (TypeError, ValueError, DiscoveryError, RecursionError, MemoryError):
        issues.append(ValidationIssue("$.pages", "discovery_run.replay", "page metadata must be replayable as bounded control data"))
        return issues
    expected_conditions = tuple(sorted(conditions))
    if document.get("counts") != counts:
        issues.append(ValidationIssue("$.counts", "discovery_run.counts", "counts must exactly equal the bounded page replay"))
    if document.get("deduplicated_records") != deduplicated:
        issues.append(ValidationIssue("$.deduplicated_records", "discovery_run.dedupe", "candidate output must be empty on any quarantine and otherwise deterministic by NCT ID"))
    if document.get("run_state") != ("complete" if not expected_conditions else "quarantined"):
        issues.append(ValidationIssue("$.run_state", "discovery_run.state", "run_state must equal the replayed reconciliation state"))
    if document.get("reconciliation_state") != _state(expected_conditions):
        issues.append(ValidationIssue("$.reconciliation_state", "discovery_run.state", "reconciliation_state must equal the priority-ordered replayed condition"))
    if document.get("quarantine_codes") != _codes(expected_conditions):
        issues.append(ValidationIssue("$.quarantine_codes", "discovery_run.quarantine", "quarantine codes must exactly equal the replayed condition set"))
    if [page.get("page_ordinal") if isinstance(page, Mapping) else None for page in pages] != list(range(len(pages))):
        issues.append(ValidationIssue("$.pages", "discovery_run.order", "pages must use contiguous zero-based ordinal order"))
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping) or not isinstance(page.get("records"), list):
            continue
        records = page["records"]
        expected = (
            sorted(
                records,
                key=lambda row: (
                    str(row.get("nct_id")),
                    str(row.get("canonical_content_sha256")),
                    str(row.get("last_update_posted_date")),
                ),
            )
            if all(isinstance(row, Mapping) for row in records)
            else records
        )
        if records != expected:
            issues.append(ValidationIssue(f"$.pages[{index}].records", "discovery_run.order", "records must use deterministic NCT order"))
    return issues


def discovery_coverage_epoch_contract_semantic_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    """Registry-facing semantic checks for ``ctgov_discovery_coverage_epoch.v1``."""

    issues: list[ValidationIssue] = []
    issue = _hash_issue(document, field="coverage_payload_sha256", code="discovery_coverage.hash")
    if issue is not None:
        issues.append(issue)
    declared = _safe_window(document.get("declared_window"))
    rows = document.get("included_runs")
    if declared is None or not isinstance(rows, list):
        return issues
    windows: list[tuple[date, date]] = []
    keys: list[tuple[str, str, str]] = []
    refs: list[str] = []
    run_transaction_times: list[datetime] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        issues.extend(_selection_issues(row.get("selection_window"), path=f"$.included_runs[{index}].selection_window", require_window_cap=True))
        window = _safe_window(row.get("selection_window"))
        run_ref = row.get("run_ref")
        if window is not None and isinstance(run_ref, str):
            windows.append(window)
            refs.append(run_ref)
            keys.append((window[0].isoformat(), window[1].isoformat(), run_ref))
        cut = row.get("source_cut")
        run_transaction = _safe_datetime(row.get("run_transaction_from"))
        if run_transaction is not None:
            run_transaction_times.append(run_transaction)
        if not isinstance(cut, Mapping):
            issues.append(ValidationIssue(f"$.included_runs[{index}].source_cut", "discovery_coverage.source_cut", "included reconciled runs require a complete source cut"))
        else:
            values = (
                cut.get("dataset_timestamp_before_raw"),
                cut.get("dataset_timestamp_after_raw"),
                cut.get("api_version_before"),
                cut.get("api_version_after"),
                cut.get("version_before_retrieved_at"),
                cut.get("first_page_receipt_retrieved_at"),
                cut.get("terminal_page_receipt_retrieved_at"),
                cut.get("version_after_retrieved_at"),
            )
            parsed = [_safe_datetime(value) for value in values[4:]]
            if (
                any(value is None for value in values)
                or values[0] != values[1]
                or values[2] != values[3]
                or any(value is None for value in parsed)
                or parsed != sorted(parsed)
            ):
                issues.append(ValidationIssue(f"$.included_runs[{index}].source_cut", "discovery_coverage.source_cut", "included reconciled runs require one stable, chronologically bounded source cut"))
            elif run_transaction is None or run_transaction < parsed[-1]:
                issues.append(ValidationIssue(f"$.included_runs[{index}].run_transaction_from", "discovery_coverage.knowledge_time", "included run transaction time must not precede its terminal source evidence"))
    if len(refs) != len(set(refs)):
        issues.append(ValidationIssue("$.included_runs", "discovery_coverage.duplicate_run", "run references must be unique"))
    if keys != sorted(keys):
        issues.append(ValidationIssue("$.included_runs", "discovery_coverage.order", "included runs must be ordered by day window then run reference"))
    if not windows:
        return issues
    epoch_transaction = _safe_datetime(document.get("transaction_from"))
    if (
        epoch_transaction is not None
        and run_transaction_times
        and epoch_transaction < max(run_transaction_times)
    ):
        issues.append(ValidationIssue("$.transaction_from", "discovery_coverage.knowledge_time", "coverage transaction time must not precede any included run"))
    envelope = (min(start for start, _ in windows), max(end for _, end in windows))
    if envelope != declared:
        issues.append(ValidationIssue("$.declared_window", "discovery_coverage.evidenced_extent", "declared window must equal the union envelope of included scopes"))
    ordered_windows = sorted(windows)
    gaps, overlaps = _partition_windows(ordered_windows)
    if document.get("gap_windows") != gaps:
        issues.append(ValidationIssue("$.gap_windows", "discovery_coverage.gaps", "gap_windows must exactly replay all day-precision coverage gaps"))
    if document.get("overlap_windows") != overlaps:
        issues.append(ValidationIssue("$.overlap_windows", "discovery_coverage.overlaps", "overlap_windows must exactly replay all day-precision multiple coverage"))
    conditions: list[str] = []
    if gaps:
        conditions.append("DISCOVERY_COVERAGE_GAP")
    if len(ordered_windows) > 1 and not _has_consecutive_overlap(ordered_windows):
        conditions.append("DISCOVERY_COVERAGE_OVERLAP_REQUIRED")
    expected_state = "complete" if not conditions else "quarantined"
    if document.get("coverage_state") != expected_state:
        issues.append(ValidationIssue("$.coverage_state", "discovery_coverage.state", "coverage state must exactly reflect atomic full-window reconciliation"))
    if document.get("quarantine_codes") != sorted(conditions):
        issues.append(ValidationIssue("$.quarantine_codes", "discovery_coverage.quarantine", "quarantine codes must exactly encode gap and overlap conditions"))
    return issues


def _schema_document(contract_id: str, document: Mapping[str, Any], *, code: str) -> dict[str, Any]:
    normalized = _copy_json(document, code=code)
    if not isinstance(normalized, dict):
        raise DiscoveryError(code)
    try:
        validate_contract(contract_id, normalized)
    except ContractValidationError:
        raise
    except ContractError as exc:
        raise DiscoveryError(code) from exc
    return normalized


def validate_discovery_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    """Return a defensive scope after schema and semantic validation."""

    normalized = _schema_document(DISCOVERY_SCOPE_CONTRACT_ID, scope, code="DISCOVERY_SCOPE_CONTRACT_INVALID")
    issues = discovery_scope_contract_semantic_issues(normalized)
    if issues:
        raise ContractValidationError(DISCOVERY_SCOPE_CONTRACT_ID, issues)
    return normalized


def validate_discovery_run(run: Mapping[str, Any], *, scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a defensive run and optionally prove its exact scope binding."""

    normalized = _schema_document(DISCOVERY_RUN_CONTRACT_ID, run, code="DISCOVERY_RUN_CONTRACT_INVALID")
    issues = discovery_run_contract_semantic_issues(normalized)
    if scope is not None:
        bound_scope = validate_discovery_scope(scope)
        expected = {
            "scope": bound_scope,
            "scope_ref": bound_scope["scope_id"],
            "scope_payload_sha256": bound_scope["scope_payload_sha256"],
            "selection_window": bound_scope["selection_window"],
        }
        for field, value in expected.items():
            if normalized.get(field) != value:
                issues.append(ValidationIssue(f"$.{field}", "discovery_run.scope_binding", "run must exactly bind the supplied scope"))
    if issues:
        raise ContractValidationError(DISCOVERY_RUN_CONTRACT_ID, issues)
    return normalized


def validate_discovery_coverage_epoch(epoch: Mapping[str, Any], *, runs: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Return a defensive epoch and optionally prove its exact included runs."""

    normalized = _schema_document(DISCOVERY_COVERAGE_CONTRACT_ID, epoch, code="DISCOVERY_COVERAGE_CONTRACT_INVALID")
    issues = discovery_coverage_epoch_contract_semantic_issues(normalized)
    if runs is not None:
        if not isinstance(runs, (list, tuple)) or len(runs) > MAX_PAGES:
            raise DiscoveryError("DISCOVERY_COVERAGE_RUN_CAP_INVALID")
        bound_runs = [validate_discovery_run(run) for run in runs]
        if any(run["run_state"] != "complete" or run["reconciliation_state"] != "reconciled" for run in bound_runs):
            issues.append(ValidationIssue("$.included_runs", "discovery_coverage.run_binding", "coverage may include only reconciled complete runs"))
        by_ref = {run["run_id"]: run for run in bound_runs}
        rows = normalized.get("included_runs")
        expected_refs = set(by_ref)
        observed_refs = {row.get("run_ref") for row in rows if isinstance(row, Mapping)} if isinstance(rows, list) else set()
        if len(by_ref) != len(bound_runs) or observed_refs != expected_refs:
            issues.append(ValidationIssue("$.included_runs", "discovery_coverage.run_binding", "included runs must exactly match the supplied run set"))
        elif isinstance(rows, list):
            for index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    continue
                run = by_ref.get(row.get("run_ref"))
                if run is None:
                    continue
                expected = {
                    "run_ref": run["run_id"],
                    "run_payload_sha256": run["run_payload_sha256"],
                    "run_state": "complete",
                    "reconciliation_state": "reconciled",
                    "run_transaction_from": run["transaction_from"],
                    "scope_ref": run["scope_ref"],
                    "scope_payload_sha256": run["scope_payload_sha256"],
                    "selection_window": run["selection_window"],
                    "source_cut": run["source_cut"],
                }
                if dict(row) != expected:
                    issues.append(ValidationIssue(f"$.included_runs[{index}]", "discovery_coverage.run_binding", "included run cut must exactly equal its supplied run"))
    if issues:
        raise ContractValidationError(DISCOVERY_COVERAGE_CONTRACT_ID, issues)
    return normalized


__all__ = [
    "DISCOVERY_COVERAGE_CONTRACT_ID",
    "DISCOVERY_RUN_CONTRACT_ID",
    "DISCOVERY_SCOPE_CONTRACT_ID",
    "DiscoveryError",
    "MAX_JSON_CONTAINER_ITEMS",
    "MAX_JSON_DEPTH",
    "MAX_JSON_NODES",
    "MAX_PAGE_BYTES",
    "MAX_PAGE_SIZE",
    "MAX_PAGES",
    "MAX_RECORD_BYTES",
    "MAX_RECORDS",
    "MAX_STRING_BYTES",
    "MAX_TOKEN_BYTES",
    "MAX_TOTAL_BYTES",
    "MAX_WINDOW_DAYS",
    "build_discovery_coverage_epoch",
    "build_discovery_scope",
    "discovery_coverage_epoch_contract_semantic_issues",
    "discovery_run_contract_semantic_issues",
    "discovery_scope_contract_semantic_issues",
    "reconcile_discovery_run",
    "validate_discovery_coverage_epoch",
    "validate_discovery_run",
    "validate_discovery_scope",
]
