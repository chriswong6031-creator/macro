"""Strict, display-only projection of receipt-bound USAspending subawards.

The projector has no network path and no fuzzy parent resolution.  It either
reads one complete collector generation or emits the explicit empty-first
state when the entire four-file source bundle has not been initialized.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import pandas as pd


SUBAWARD_DOSSIER_CONTRACT = "government_subaward_dossiers.v1"
SUBAWARD_DOSSIER_SCHEMA_VERSION = "1.0.0"
SUBAWARD_DOSSIER_FILENAME = "subaward_dossiers.json"
SUBAWARD_DOSSIER_CONTENT_ID_PREFIX = "grsd1-"
MAX_SUBAWARD_RECORDS = 2_000
MAX_DESCRIPTION_BYTES = 2_000
_COUNT_URL_PREFIX = "https://api.usaspending.gov/api/v2/awards/count/subaward/"
_DETAIL_URL = "https://api.usaspending.gov/api/v2/subawards/"

_SOURCE_FILES = (
    "subaward_snapshots.parquet",
    "subaward_collection_receipts.jsonl",
    "subaward_projection_state.json",
    "subaward_ingest_status.json",
)
_TAG = re.compile(r"<[^>]*>")
_SENSITIVE_QUERY_KEY = re.compile(
    r"(?:api[_-]?key|authorization|secret|token|password|credential)", re.IGNORECASE
)
_ALLOWED_SOURCE_HOSTS = {"api.usaspending.gov", "usaspending.gov", "www.usaspending.gov"}
_SOURCE_CONTRACTS = {
    "state": "government_revenue.subaward_projection_state.v1",
    "status": "government_revenue.subaward_ingest_status.v1",
    "receipt": "government_revenue.subaward_collection_receipt.v1",
}

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "context_only": True,
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_add_candidates": False,
    "can_escalate": False,
}

REPORTED_AMOUNT_LIMITATION = (
    "Reported subaward amount is a self-reported USAspending subaward observation; "
    "it is not a federal obligation, outlay, prime-award value, revenue, backlog, "
    "cash flow, or an additive amount."
)


def _root(root: Path | None) -> Path:
    return Path(root).resolve() if root is not None else Path.cwd().resolve()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _receipt_content_id(receipt: Mapping[str, Any]) -> str:
    fingerprint = {
        "observed_at": receipt["observed_at"],
        "rail": receipt["rail"],
        "endpoint": receipt["endpoint"],
        "parent_generated_award_id": receipt["parent_generated_award_id"],
        "page": receipt["page"],
        "record_count": receipt["record_count"],
        "reported_subaward_count": receipt.get("reported_subaward_count"),
        "request_sha256": receipt["request_sha256"],
        "response_sha256": receipt["response_sha256"],
    }
    raw = json.dumps(
        fingerprint,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "usaspending-subaward:" + hashlib.sha256(raw).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def subaward_dossier_content_id(payload: Mapping[str, Any]) -> str | None:
    """Return the immutable semantic identity, excluding assembly metadata."""
    try:
        fingerprint = {
            str(key): value
            for key, value in payload.items()
            if key not in {"content_id", "generated_at"}
        }
        digest = hashlib.sha256(_canonical_json(fingerprint).encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        return None
    return SUBAWARD_DOSSIER_CONTENT_ID_PREFIX + digest[:24]


def _clean_text(value: Any, *, limit: int = 4_000) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = " ".join(_TAG.sub(" ", str(value)).split())
    return text[:limit] or None


def _utf8_prefix(value: Any, *, max_bytes: int) -> tuple[str | None, bool]:
    text = _clean_text(value, limit=100_000)
    if text is None:
        return None, False
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text, False
    return raw[:max_bytes].decode("utf-8", errors="ignore"), True


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(parsed):
        return None
    return parsed.tz_localize("UTC") if parsed.tzinfo is None else parsed.tz_convert("UTC")


def _instant(value: Any) -> str | None:
    parsed = _timestamp(value)
    return parsed.isoformat() if parsed is not None else None


def _required_source_instant(value: Any, label: str) -> str:
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"subaward source row lacks {label}") from exc
    if pd.isna(parsed) or parsed.tzinfo is None:
        raise ValueError(f"subaward source row lacks offset-aware {label}")
    return parsed.tz_convert("UTC").isoformat()


def _date(value: Any) -> str | None:
    parsed = _timestamp(value)
    return parsed.date().isoformat() if parsed is not None else None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _first(row: Mapping[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        try:
            if bool(pd.isna(value)):
                continue
        except (TypeError, ValueError):
            pass
        return value
    return None


def _public_url(value: Any) -> str | None:
    text = _clean_text(value, limit=1_000)
    if text is None:
        return None
    try:
        parsed = urlsplit(text)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.hostname.lower() not in _ALLOWED_SOURCE_HOSTS
            or parsed.username
            or parsed.password
        ):
            return None
        port = parsed.port
    except ValueError:
        return None
    host = parsed.hostname.lower() + (f":{port}" if port else "")
    query = urlencode([
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _SENSITIVE_QUERY_KEY.search(key)
    ])
    return urlunsplit(("https", host, parsed.path, query, parsed.fragment))


def _parent_url(generated_award_id: str, supplied: Any) -> str:
    return _public_url(supplied) or f"https://www.usaspending.gov/award/{generated_award_id}/"


def _subaward_url(supplied: Any) -> str:
    return _public_url(supplied) or "https://api.usaspending.gov/api/v2/subawards/"


def _required_text(value: Any, label: str, *, limit: int = 1_000) -> str:
    text = _clean_text(value, limit=limit)
    if text is None:
        raise ValueError(f"subaward source row lacks {label}")
    return text


def _normalized_prime_map(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("prime award bridge must be a mapping")
    result: dict[str, str] = {}
    for generated_award_id, award_key in value.items():
        if not isinstance(generated_award_id, str) or not generated_award_id.strip():
            raise ValueError("prime award bridge contains an invalid generated award ID")
        if not isinstance(award_key, str) or not award_key.strip():
            raise ValueError("prime award bridge contains an invalid award key")
        if generated_award_id in result or award_key in result.values():
            raise ValueError("prime award bridge is ambiguous")
        result[generated_award_id] = award_key
    return dict(sorted(result.items()))


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - corrupt source bundle must fail closed
        raise ValueError(f"subaward {label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"subaward {label} must be an object")
    return value


def _load_receipts(path: Path) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    try:
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError(f"receipt line {line_number} is not an object")
            receipts.append(value)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("subaward collection receipts are unreadable") from exc
    return receipts


def _require_source_contract(value: Mapping[str, Any], kind: str) -> None:
    if value.get("contract") != _SOURCE_CONTRACTS[kind]:
        raise ValueError(f"subaward {kind} contract mismatch")
    if value.get("schema_version") != "1.0.0":
        raise ValueError(f"subaward {kind} schema version mismatch")


def _reject_unsafe_source_keys(value: Any, *, path: str = "source") -> None:
    """Reject raw-response or secret-shaped fields instead of merely redacting them."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            hash_only = normalized.endswith(("_sha256", "_hash", "_digest"))
            blocked = (
                re.search(r"(?:credential|authorization|password|secret|token|api_?key)", normalized)
                or re.search(r"(?:^|_)(?:headers?|body|payload)(?:_|$)", normalized)
                or re.search(r"(?:^|_)raw_(?:request|response)(?:_|$)", normalized)
            )
            if blocked and not hash_only:
                raise ValueError(f"subaward {path} contains forbidden raw or secret-shaped key")
            _reject_unsafe_source_keys(child, path=path)
    elif isinstance(value, list):
        for child in value:
            _reject_unsafe_source_keys(child, path=path)


def _collector_contract(frame: pd.DataFrame, state: Mapping[str, Any]) -> None:
    """Use collector-owned columns/generation when that module is available."""
    try:
        collector = importlib.import_module("collectors.usaspending_subawards")
    except ModuleNotFoundError as exc:
        if exc.name == "collectors.usaspending_subawards":
            raise ValueError("subaward collector contract is unavailable") from exc
        raise
    columns = getattr(collector, "SUBAWARD_SNAPSHOT_COLUMNS", None)
    matcher = getattr(collector, "subaward_projection_generation_matches", None)
    coverage_hasher = getattr(
        collector, "subaward_parent_coverage_semantic_sha256", None
    )
    if not isinstance(columns, (list, tuple)) or not all(isinstance(item, str) for item in columns):
        raise ValueError("subaward collector column contract is unavailable")
    if list(frame.columns) != list(columns):
        raise ValueError("subaward snapshot columns do not match the collector contract")
    if not callable(matcher) or matcher(state, frame) is not True:
        raise ValueError("subaward source snapshot does not match its activation generation")
    if (
        not callable(coverage_hasher)
        or coverage_hasher(state.get("parents"))
        != state.get("parent_coverage_semantic_sha256")
    ):
        raise ValueError("subaward parent coverage digest mismatch")


def _collector_state_sha256(row: Mapping[str, Any]) -> str:
    collector = importlib.import_module("collectors.usaspending_subawards")
    hasher = getattr(collector, "_subaward_state_sha256", None)
    if not callable(hasher):
        raise ValueError("subaward collector state-hash contract is unavailable")
    value = hasher(row)
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("subaward collector state-hash contract is invalid")
    return value


def _generation(value: Mapping[str, Any]) -> str | None:
    raw = _first(
        value,
        (
            "projection_generation_id",
            "active_projection_generation_id",
            "projection_generation",
            "generation",
            "generation_id",
            "snapshot_generation",
        ),
    )
    return _clean_text(raw, limit=200)


def _receipt_index(
    receipts: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    base_keys = {
        "schema_version",
        "contract",
        "receipt_id",
        "observed_at",
        "rail",
        "endpoint",
        "parent_generated_award_id",
        "page",
        "record_count",
        "request_sha256",
        "response_sha256",
    }
    for receipt in receipts:
        _require_source_contract(receipt, "receipt")
        expected_keys = base_keys | (
            {"reported_subaward_count"}
            if receipt.get("rail") == "subaward_count"
            else set()
        )
        if set(receipt) != expected_keys:
            raise ValueError("subaward collection receipt shape mismatch")
        receipt_id = _required_text(
            _first(receipt, ("receipt_id", "collection_receipt_id")), "receipt ID", limit=400
        )
        if receipt_id in result:
            raise ValueError("subaward collection receipts contain duplicate receipt IDs")
        response_sha256 = _required_text(
            _first(receipt, ("response_sha256", "response_hash")),
            "response SHA-256",
            limit=64,
        ).lower()
        if not re.fullmatch(r"[a-f0-9]{64}", response_sha256):
            raise ValueError("subaward collection receipt has an invalid response SHA-256")
        request_sha256 = _required_text(
            receipt.get("request_sha256"), "request SHA-256", limit=64
        ).lower()
        if not re.fullmatch(r"[a-f0-9]{64}", request_sha256):
            raise ValueError("subaward collection receipt has an invalid request SHA-256")
        _required_source_instant(receipt.get("observed_at"), "receipt observed_at")
        if receipt.get("rail") not in {"subaward_count", "subaward_detail"}:
            raise ValueError("subaward collection receipt has an invalid rail")
        parent_id = _required_text(
            receipt.get("parent_generated_award_id"), "receipt parent generated award ID"
        )
        page = receipt.get("page")
        if receipt.get("rail") == "subaward_count":
            if page is not None:
                raise ValueError("subaward count receipt must not carry a detail page")
            if (
                receipt.get("endpoint")
                != f"{_COUNT_URL_PREFIX}{quote(parent_id, safe='')}/"
                or _source_record_count(receipt) != 1
            ):
                raise ValueError("subaward count receipt has an invalid endpoint or shape")
            if isinstance(receipt.get("reported_subaward_count"), bool):
                raise ValueError("subaward count receipt has an invalid reported count")
            try:
                reported_count = int(receipt.get("reported_subaward_count"))
            except (TypeError, ValueError) as exc:
                raise ValueError("subaward count receipt lacks its reported count") from exc
            if reported_count < 0:
                raise ValueError("subaward count receipt has a negative reported count")
            expected_request = {
                "method": "GET",
                "endpoint": receipt["endpoint"],
            }
        elif (
            isinstance(page, bool)
            or not isinstance(page, int)
            or page < 1
            or page > 5
            or receipt.get("endpoint") != _DETAIL_URL
            or _source_record_count(receipt) > 100
        ):
            raise ValueError("subaward detail receipt has an invalid endpoint, page, or row count")
        else:
            expected_request = {
                "award_id": parent_id,
                "page": page,
                "limit": 100,
                "sort": "action_date",
                "order": "desc",
            }
        if request_sha256 != _canonical_sha256(expected_request):
            raise ValueError("subaward collection receipt request hash mismatch")
        if receipt_id != _receipt_content_id(receipt):
            raise ValueError("subaward collection receipt identity mismatch")
        result[receipt_id] = receipt
    return result


def _source_record_count(receipt: Mapping[str, Any]) -> int:
    raw = _first(receipt, ("source_record_count", "record_count", "records_received"))
    if isinstance(raw, bool):
        raise ValueError("subaward collection receipt has an invalid record count")
    try:
        count = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("subaward collection receipt lacks a record count") from exc
    if count < 0:
        raise ValueError("subaward collection receipt has a negative record count")
    return count


def _subaward_key(parent_generated_award_id: str, source_subaward_id: str) -> str:
    digest = hashlib.sha256(
        _canonical_json([parent_generated_award_id, source_subaward_id]).encode("utf-8")
    ).hexdigest()
    return "subaward:" + digest[:32]


def _parent_coverage(
    state: Mapping[str, Any],
    *,
    prime_map: Mapping[str, str],
    receipts: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    source = state.get("parents")
    if not isinstance(source, list):
        raise ValueError("subaward projection state lacks parent coverage")
    result: dict[str, dict[str, Any]] = {}
    allowed_states = {"zero", "complete", "high_count_count_only", "run_cap_count_only"}
    for item in source:
        if not isinstance(item, Mapping):
            raise ValueError("subaward parent coverage row is invalid")
        parent_id = _required_text(
            item.get("parent_generated_award_id"), "parent coverage generated award ID"
        )
        if parent_id not in prime_map:
            raise ValueError("subaward parent coverage has no exact prime dossier parent")
        if parent_id in result:
            raise ValueError("subaward projection state repeats parent coverage")
        collection_state = _required_text(item.get("collection_state"), "collection state")
        if collection_state not in allowed_states:
            raise ValueError("subaward parent coverage has an invalid collection state")
        try:
            reported_count = int(item.get("subaward_count"))
            detail_rows = int(item.get("detail_rows"))
            pages_fetched = int(item.get("pages_fetched"))
        except (TypeError, ValueError) as exc:
            raise ValueError("subaward parent coverage has invalid counts") from exc
        if min(reported_count, detail_rows, pages_fetched) < 0:
            raise ValueError("subaward parent coverage has negative counts")
        if item.get("count_verified") is not True:
            raise ValueError("subaward parent coverage count is not verified")
        if not isinstance(item.get("high_count_parent"), bool):
            raise ValueError("subaward parent coverage lacks high-count state")
        if not isinstance(item.get("source_exhausted"), bool):
            raise ValueError("subaward parent coverage lacks source exhaustion state")
        count_binding = item.get("count_receipt_binding")
        if not isinstance(count_binding, Mapping):
            raise ValueError("subaward parent coverage lacks its count receipt binding")
        count_receipt_id = _required_text(
            count_binding.get("receipt_id"), "count receipt binding ID"
        )
        if (
            count_binding.get("rail") != "subaward_count"
            or count_binding.get("parent_generated_award_id") != parent_id
            or count_binding.get("reported_subaward_count") != reported_count
            or item.get("count_receipt_id") != count_receipt_id
        ):
            raise ValueError("subaward parent coverage count binding mismatch")
        detail_receipt_ids = item.get("detail_receipt_ids")
        if not isinstance(detail_receipt_ids, list) or any(
            not isinstance(receipt_id, str) or not receipt_id for receipt_id in detail_receipt_ids
        ):
            raise ValueError("subaward parent coverage detail receipt IDs are invalid")
        if len(set(detail_receipt_ids)) != len(detail_receipt_ids):
            raise ValueError("subaward parent coverage repeats detail receipt IDs")
        if count_receipt_id not in receipts or any(
            receipt_id not in receipts for receipt_id in detail_receipt_ids
        ):
            raise ValueError("subaward parent coverage is not receipt-bound")
        count_receipt = receipts[count_receipt_id]
        if (
            count_receipt.get("rail") != "subaward_count"
            or count_receipt.get("parent_generated_award_id") != parent_id
            or count_receipt.get("reported_subaward_count") != reported_count
        ):
            raise ValueError("subaward parent count receipt mismatch")
        if any(
            receipts[receipt_id].get("rail") != "subaward_detail"
            or receipts[receipt_id].get("parent_generated_award_id") != parent_id
            for receipt_id in detail_receipt_ids
        ):
            raise ValueError("subaward parent detail receipt mismatch")
        detail_receipts = [receipts[receipt_id] for receipt_id in detail_receipt_ids]
        detail_pages = sorted(receipt.get("page") for receipt in detail_receipts)
        detail_receipt_rows = sum(_source_record_count(receipt) for receipt in detail_receipts)
        count_only = collection_state in {"high_count_count_only", "run_cap_count_only"}
        expected_pages = (reported_count + 99) // 100
        if pages_fetched != len(detail_receipt_ids) or detail_rows != detail_receipt_rows:
            raise ValueError("subaward parent coverage detail totals do not match receipts")
        if collection_state == "complete" and (
            item.get("source_exhausted") is not True
            or reported_count < 1
            or reported_count > 500
            or detail_rows != reported_count
            or pages_fetched != expected_pages
            or detail_pages != list(range(1, expected_pages + 1))
            or item.get("high_count_parent") is not False
        ):
            raise ValueError("complete subaward parent coverage is internally inconsistent")
        if collection_state == "zero" and (
            reported_count != 0
            or detail_rows != 0
            or pages_fetched != 0
            or detail_receipt_ids
            or item.get("source_exhausted") is not True
            or item.get("high_count_parent") is not False
        ):
            raise ValueError("zero subaward parent coverage has non-zero evidence")
        if count_only and (
            reported_count < 1
            or detail_rows != 0
            or pages_fetched != 0
            or detail_receipt_ids
            or item.get("source_exhausted") is not False
        ):
            raise ValueError("count-only subaward parent coverage contains detail evidence")
        if collection_state == "high_count_count_only" and (
            reported_count <= 500 or item.get("high_count_parent") is not True
        ):
            raise ValueError("high-count subaward parent coverage is inconsistent")
        if collection_state == "run_cap_count_only" and (
            reported_count > 500 or item.get("high_count_parent") is not False
        ):
            raise ValueError("run-cap subaward parent coverage is inconsistent")
        result[parent_id] = {
            "status": "partial" if count_only else "ok",
            "collection_state": collection_state,
            "reported_count": reported_count,
            "count_verified": True,
            "high_count_parent": item["high_count_parent"],
            "detail_rows": detail_rows,
            "pages_fetched": pages_fetched,
            "source_exhausted": item["source_exhausted"],
            "truncated_by_collection_policy": count_only,
            "reason": (
                "Count is verified; detail rows are intentionally not fetched under the bounded collection policy."
                if count_only
                else "Count and bounded detail coverage are receipt-bound for this exact prime."
            ),
        }
    return result


def _row_from_source(
    row: Mapping[str, Any],
    *,
    prime_map: Mapping[str, str],
    receipts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    parent_generated_award_id = _required_text(
        _first(
            row,
            (
                "parent_generated_award_id",
                "prime_generated_award_id",
                "generated_award_id",
            ),
        ),
        "exact parent generated award ID",
        limit=1_000,
    )
    parent_award_key = prime_map.get(parent_generated_award_id)
    if parent_award_key is None:
        raise ValueError("subaward source row has no exact prime dossier parent")
    source_subaward_id = _required_text(
        _first(row, ("source_subaward_id", "broker_subaward_id", "subaward_id")),
        "native broker subaward ID",
        limit=1_000,
    )
    receipt_id = _required_text(
        _first(row, ("source_receipt_id", "receipt_id", "collection_receipt_id")),
        "receipt binding",
        limit=400,
    )
    receipt = receipts.get(receipt_id)
    if receipt is None:
        raise ValueError("subaward source row is not bound to a collection receipt")
    response_sha256 = _required_text(
        _first(row, ("source_response_sha256", "response_sha256", "response_hash")),
        "response SHA-256",
        limit=64,
    ).lower()
    receipt_sha256 = _required_text(
        _first(receipt, ("response_sha256", "response_hash")), "receipt response SHA-256", limit=64
    ).lower()
    if response_sha256 != receipt_sha256:
        raise ValueError("subaward source row response hash does not match its receipt")
    if row.get("receipt_verified") is not True:
        raise ValueError("subaward source row is not marked receipt-verified")
    if (
        receipt.get("rail") != "subaward_detail"
        or receipt.get("parent_generated_award_id") != parent_generated_award_id
    ):
        raise ValueError("subaward source row receipt has the wrong rail or parent")

    source_state_sha256 = _required_text(
        row.get("subaward_state_sha256"), "subaward state SHA-256", limit=64
    ).lower()
    if source_state_sha256 != _collector_state_sha256(row):
        raise ValueError("subaward source row state hash mismatch")
    receipt_observed_at = _required_source_instant(
        receipt.get("observed_at"), "receipt observed_at"
    )

    description, description_truncated = _utf8_prefix(
        _first(row, ("description", "subaward_description")), max_bytes=MAX_DESCRIPTION_BYTES
    )
    action_date = _date(_first(row, ("action_date", "subaward_action_date")))
    effective_at = _date(_first(row, ("effective_at", "action_date", "subaward_action_date")))
    known_at = _required_source_instant(
        _first(row, ("known_at", "observed_at", "collected_at")), "known_at"
    )
    first_seen_at = _required_source_instant(
        _first(row, ("first_seen_at",)), "first_seen_at"
    )
    if known_at != receipt_observed_at:
        raise ValueError("subaward source row evidence clock does not match its receipt")
    if first_seen_at > known_at:
        raise ValueError("subaward source row first-seen clock exceeds known_at")
    last_seen_at = _instant(_first(row, ("last_seen_at",))) or known_at
    displayed_number = _clean_text(
        _first(row, ("displayed_subaward_number", "subaward_number")), limit=1_000
    )
    amount = _number(
        _first(
            row,
            ("reported_subaward_amount", "reported_amount", "subaward_amount", "amount"),
        )
    )
    source_record_count = _source_record_count(receipt)
    if row.get("source_url") != _DETAIL_URL:
        raise ValueError("subaward source row has an invalid official source URL")

    return {
        "subaward_key": _subaward_key(parent_generated_award_id, source_subaward_id),
        "parent_award_key": parent_award_key,
        "identity": {
            "source_subaward_id": source_subaward_id,
            "displayed_subaward_number": displayed_number,
            "parent_generated_award_id": parent_generated_award_id,
        },
        "subawardee_name": _clean_text(
            _first(row, ("subawardee_name", "subrecipient_name", "recipient_name")),
            limit=1_000,
        ),
        "subaward_type": _clean_text(
            _first(row, ("subaward_type", "award_type")), limit=200
        ),
        "description": description,
        "description_truncated": description_truncated,
        "dates": {
            "action_date": action_date,
            "effective_at": effective_at,
            "known_at": known_at,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
        },
        "reported_amount": {
            "amount": amount,
            "semantic": "reported_subaward_amount",
            "currency": "USD",
        },
        "source": {
            "publisher": "USAspending.gov",
            "subaward_url": _subaward_url(
                _first(row, ("source_url", "subaward_url"))
            ),
            "parent_award_url": _parent_url(
                parent_generated_award_id,
                _first(row, ("parent_award_url", "award_page_url")),
            ),
        },
        "provenance": {
            "receipt_id": receipt_id,
            "response_sha256": response_sha256,
            "source_record_count": source_record_count,
            "effective_at": effective_at,
            "known_at": known_at,
            "limitations": [
                "Official self-reported subaward observation bound to a stored collection receipt.",
                REPORTED_AMOUNT_LIMITATION,
            ],
        },
    }


def _status(value: Any, *, fallback: str) -> str:
    text = _clean_text(value, limit=40)
    return text if text in {"ok", "partial", "unavailable", "failed"} else fallback


def _as_of_day(value: str | None, candidates: Iterable[Any]) -> str:
    if value is not None:
        parsed = _date(value)
        if parsed is None:
            raise ValueError("subaward dossier as_of must be a valid date")
        return parsed
    parsed = [stamp for stamp in (_timestamp(item) for item in candidates) if stamp is not None]
    return max(parsed).date().isoformat() if parsed else datetime.now(timezone.utc).date().isoformat()


def _base_payload(
    *,
    as_of_day: str,
    known_at: str | None,
    prime_map: Mapping[str, str],
    rows: list[dict[str, Any]],
    source_coverage: dict[str, Any],
    freshness: dict[str, Any],
    prime_coverage: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    keys_by_parent: dict[str, list[str]] = {key: [] for key in prime_map}
    for row in rows:
        keys_by_parent[row["identity"]["parent_generated_award_id"]].append(row["subaward_key"])
    primes = []
    for generated_award_id, award_key in prime_map.items():
        keys = sorted(keys_by_parent[generated_award_id])
        coverage = dict((prime_coverage or {}).get(generated_award_id, {}))
        if not coverage:
            coverage = {
                "status": "unavailable",
                "collection_state": "not_selected",
                "reported_count": None,
                "count_verified": False,
                "high_count_parent": False,
                "detail_rows": 0,
                "pages_fetched": 0,
                "source_exhausted": False,
                "truncated_by_collection_policy": False,
                "reason": (
                    "The source bundle is unavailable."
                    if source_coverage["status"] == "unavailable"
                    else "This exact prime was not selected by the bounded collector generation."
                ),
            }
        coverage["records_published"] = len(keys)
        primes.append({
            "parent_generated_award_id": generated_award_id,
            "award_key": award_key,
            "coverage": coverage,
            "subaward_keys": keys,
            "subaward_count": len(keys),
        })
    payload: dict[str, Any] = {
        "contract": SUBAWARD_DOSSIER_CONTRACT,
        "schema_version": SUBAWARD_DOSSIER_SCHEMA_VERSION,
        "content_id": "",
        "as_of": as_of_day,
        "known_at": known_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": AUTHORITY.copy(),
        "source_coverage": source_coverage,
        "freshness": freshness,
        "limitations": [
            "The source collection is bounded and is not the complete USAspending subaward corpus.",
            REPORTED_AMOUNT_LIMITATION,
            "Every published row requires an exact generated-award-ID parent and a native broker subaward ID.",
        ],
        "primes": primes,
        "subawards": rows,
    }
    content_id = subaward_dossier_content_id(payload)
    if content_id is None:
        raise ValueError("subaward dossier cannot be represented as canonical JSON")
    payload["content_id"] = content_id
    if not is_valid_subaward_dossier_payload(payload):
        raise ValueError("subaward dossier failed its strict public contract")
    return payload


def build_subaward_dossier_payload(
    root: Path | None = None,
    *,
    prime_award_key_by_generated_id: Mapping[str, str] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Build one bounded public generation from the collector's four-file bundle."""
    prime_map = _normalized_prime_map(prime_award_key_by_generated_id)
    data_dir = _root(root) / "data" / "government_revenue"
    paths = [data_dir / name for name in _SOURCE_FILES]
    present = [path.exists() for path in paths]
    if not any(present):
        as_of_day = _as_of_day(as_of, ())
        reason = "The receipt-bound USAspending subaward source bundle is not initialized."
        return _base_payload(
            as_of_day=as_of_day,
            known_at=None,
            prime_map=prime_map,
            rows=[],
            source_coverage={
                "status": "unavailable",
                "records_loaded": 0,
                "records_published": 0,
                "records_dropped": 0,
                "configured_cap": MAX_SUBAWARD_RECORDS,
                "truncated_by_artifact_cap": False,
                "bounded_collection": None,
                "reason": reason,
            },
            freshness={
                "status": "unavailable",
                "observed_at": None,
                "known_at": None,
                "reason": reason,
            },
        )
    if not all(present):
        raise ValueError("subaward source bundle is partial; all four artifacts are required")

    snapshot_path, receipts_path, state_path, status_path = paths
    try:
        frame = pd.read_parquet(snapshot_path)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("subaward snapshot parquet is unreadable") from exc
    state = _load_json(state_path, "projection state")
    ingest_status = _load_json(status_path, "ingest status")
    receipts_list = _load_receipts(receipts_path)
    _reject_unsafe_source_keys(state, path="projection state")
    _reject_unsafe_source_keys(ingest_status, path="ingest status")
    _reject_unsafe_source_keys(receipts_list, path="collection receipts")
    _require_source_contract(state, "state")
    _require_source_contract(ingest_status, "status")
    _collector_contract(frame, state)

    generation = _required_text(_generation(state), "projection generation", limit=200)
    ingest_generation = _required_text(
        _generation(ingest_status), "ingest projection generation", limit=200
    )
    if ingest_generation != generation:
        raise ValueError("subaward ingest status generation mismatch")
    if state.get("activation_state") != "live":
        raise ValueError("subaward projection generation is not live")
    if (
        ingest_status.get("status") != "ok"
        or ingest_status.get("partial") is not False
        or ingest_status.get("bounded") is not True
        or ingest_status.get("source_only") is not True
        or ingest_status.get("daily_lane") is not True
        or ingest_status.get("errors") != []
        or state.get("public_downstream_row_cap") != MAX_SUBAWARD_RECORDS
        or state.get("bounded_collection_complete") is not True
        or state.get("projection_eligible") is not True
        or ingest_status.get("collection_complete") is not True
        or ingest_status.get("projection_eligible") is not True
    ):
        raise ValueError("subaward source generation is not publication-eligible")
    receipts = _receipt_index(receipts_list)
    if not frame.empty and not receipts:
        raise ValueError("subaward rows exist without collection receipts")

    latest_by_identity: dict[tuple[str, str], tuple[str, str, dict[str, Any]]] = {}
    for source_row in frame.to_dict(orient="records"):
        row = _row_from_source(source_row, prime_map=prime_map, receipts=receipts)
        state_sha256 = _required_text(
            source_row.get("subaward_state_sha256"), "subaward state SHA-256", limit=64
        ).lower()
        if not re.fullmatch(r"[a-f0-9]{64}", state_sha256):
            raise ValueError("subaward source row has an invalid state SHA-256")
        identity = (
            row["identity"]["parent_generated_award_id"],
            row["identity"]["source_subaward_id"],
        )
        previous = latest_by_identity.get(identity)
        known_at = row["dates"]["known_at"]
        if previous is not None and previous[0] == known_at and previous[1] != state_sha256:
            raise ValueError("subaward source has conflicting states at the same evidence clock")
        candidate = (known_at, state_sha256, row)
        if previous is None or known_at > previous[0] or (
            known_at == previous[0]
            and state_sha256 == previous[1]
            and row["provenance"]["receipt_id"] < previous[2]["provenance"]["receipt_id"]
        ):
            latest_by_identity[identity] = candidate
    rows = [item[2] for item in latest_by_identity.values()]

    rows.sort(
        key=lambda row: (
            row["dates"]["action_date"] or "",
            row["dates"]["known_at"] or "",
            row["subaward_key"],
        ),
        reverse=True,
    )
    loaded = len(rows)
    rows = rows[:MAX_SUBAWARD_RECORDS]
    dropped = loaded - len(rows)
    observed_at = _instant(
        _first(ingest_status, ("observed_at", "known_at", "completed_at"))
    )
    row_known_at = [row["dates"]["known_at"] for row in rows]
    known_candidates = [observed_at, *row_known_at]
    known_stamps = [stamp for stamp in (_timestamp(item) for item in known_candidates) if stamp]
    known_at = max(known_stamps).isoformat() if known_stamps else None
    source_status = "partial" if dropped else _status(ingest_status.get("status"), fallback="ok")
    reason = (
        f"Published the newest {len(rows)} of {loaded} receipt-bound subaward rows."
        if dropped
        else "Published all receipt-bound subaward rows in the bounded collector generation."
    )
    as_of_day = _as_of_day(
        as_of,
        [ingest_status.get("effective_at"), observed_at]
        + [row["dates"]["action_date"] for row in rows],
    )
    prime_coverage = _parent_coverage(state, prime_map=prime_map, receipts=receipts)
    return _base_payload(
        as_of_day=as_of_day,
        known_at=known_at,
        prime_map=prime_map,
        rows=rows,
        source_coverage={
            "status": source_status,
            "records_loaded": loaded,
            "records_published": len(rows),
            "records_dropped": dropped,
            "configured_cap": MAX_SUBAWARD_RECORDS,
            "truncated_by_artifact_cap": bool(dropped),
            "bounded_collection": bool(ingest_status.get("bounded", True)),
            "reason": reason,
        },
        freshness={
            "status": source_status,
            "observed_at": observed_at,
            "known_at": known_at,
            "reason": reason,
        },
        prime_coverage=prime_coverage,
    )


@lru_cache(maxsize=1)
def _validator() -> Any:
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "government_revenue"
        / "government_subaward_dossiers.v1.schema.json"
    )
    return Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    )


def is_valid_subaward_dossier_payload(value: Any) -> bool:
    """Validate schema, immutable identity, and every internal parent envelope."""
    if not isinstance(value, dict):
        return False
    try:
        if any(_validator().iter_errors(value)):
            return False
        if subaward_dossier_content_id(value) != value.get("content_id"):
            return False
        rows = value.get("subawards")
        primes = value.get("primes")
        if not isinstance(rows, list) or not isinstance(primes, list):
            return False
        prime_map = {
            row["parent_generated_award_id"]: row
            for row in primes
            if isinstance(row, dict)
        }
        if len(prime_map) != len(primes):
            return False
        row_map = {
            row["subaward_key"]: row for row in rows if isinstance(row, dict)
        }
        if len(row_map) != len(rows):
            return False
        identities: set[tuple[str, str]] = set()
        expected_by_parent: dict[str, list[str]] = {key: [] for key in prime_map}
        for key, row in row_map.items():
            identity = row.get("identity")
            if not isinstance(identity, dict):
                return False
            parent_id = identity.get("parent_generated_award_id")
            native_id = identity.get("source_subaward_id")
            identity_pair = (parent_id, native_id)
            if not all(isinstance(item, str) and item for item in identity_pair):
                return False
            if identity_pair in identities or _subaward_key(*identity_pair) != key:
                return False
            identities.add(identity_pair)
            prime = prime_map.get(parent_id)
            if prime is None or prime.get("award_key") != row.get("parent_award_key"):
                return False
            if len((row.get("description") or "").encode("utf-8")) > MAX_DESCRIPTION_BYTES:
                return False
            expected_by_parent[parent_id].append(key)
        for parent_id, prime in prime_map.items():
            expected = sorted(expected_by_parent[parent_id])
            if prime.get("subaward_keys") != expected:
                return False
            if prime.get("subaward_count") != len(expected):
                return False
            if prime.get("coverage", {}).get("records_published") != len(expected):
                return False
        return True
    except Exception:  # noqa: BLE001 - validation is a fail-closed public boundary
        return False


__all__ = [
    "AUTHORITY",
    "MAX_DESCRIPTION_BYTES",
    "MAX_SUBAWARD_RECORDS",
    "REPORTED_AMOUNT_LIMITATION",
    "SUBAWARD_DOSSIER_CONTENT_ID_PREFIX",
    "SUBAWARD_DOSSIER_CONTRACT",
    "SUBAWARD_DOSSIER_FILENAME",
    "SUBAWARD_DOSSIER_SCHEMA_VERSION",
    "build_subaward_dossier_payload",
    "is_valid_subaward_dossier_payload",
    "subaward_dossier_content_id",
]
