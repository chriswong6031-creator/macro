"""Bounded official USAspending subaward collection.

This lane intentionally records source-only subaward context.  A reported
subaward amount is a prime recipient's report about a subrecipient; it is not a
federal obligation, outlay, backlog, revenue, cash receipt, or an additive prime
award value.  The immutable identity is the exact parent generated award id
plus USAspending's native broker row ``id``.  The displayed subaward number is
not an identity field and may repeat.

Only the official count and identity-page endpoints are used:

* ``GET /api/v2/awards/count/subaward/{generated_award_id}/``
* ``POST /api/v2/subawards/``

The collector is deliberately bounded: at most 160 exact parents, 100 rows per
page, five pages/500 detail rows per parent, and 2,000 detail rows per run.  A
parent whose exact count exceeds 500 is retained as count-only coverage and no
detail page is requested for it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config


SUBAWARD_COUNT_URL = (
    "https://api.usaspending.gov/api/v2/awards/count/subaward/{award_id}/"
)
SUBAWARDS_URL = "https://api.usaspending.gov/api/v2/subawards/"
DEFAULT_USER_AGENT = "MastermindX Government Revenue Foresight contact@mastermind-x.com"

SUBAWARD_SNAPSHOT_SCHEMA = "government_revenue.subaward_snapshot.v1"
SUBAWARD_PROJECTION_STATE_SCHEMA = "government_revenue.subaward_projection_state.v1"
SUBAWARD_COLLECTION_RECEIPT_SCHEMA = "government_revenue.subaward_collection_receipt.v1"
SUBAWARD_INGEST_STATUS_SCHEMA = "government_revenue.subaward_ingest_status.v1"
SCHEMA_VERSION = "1.0.0"

SUBAWARD_SNAPSHOTS_FILENAME = "subaward_snapshots.parquet"
SUBAWARD_COLLECTION_RECEIPTS_FILENAME = "subaward_collection_receipts.jsonl"
SUBAWARD_PROJECTION_STATE_FILENAME = "subaward_projection_state.json"
SUBAWARD_INGEST_STATUS_FILENAME = "subaward_ingest_status.json"
SUBAWARD_COLLECTOR_HEARTBEAT_FILENAME = "subaward_collector_heartbeat.parquet"

MAX_PARENTS = 160
PAGE_SIZE = 100
MAX_PAGES_PER_PARENT = 5
MAX_DETAIL_ROWS_PER_PARENT = PAGE_SIZE * MAX_PAGES_PER_PARENT
MAX_DETAIL_ROWS_PER_RUN = 2_000
PUBLIC_DOWNSTREAM_ROW_CAP = 2_000
MAX_DESCRIPTION_UTF8_BYTES = 2_000

SUBAWARD_SNAPSHOT_COLUMNS = [
    "parent_generated_award_id",
    "subaward_id",
    "subaward_number",
    "action_date",
    "reported_subaward_amount",
    "description",
    "subrecipient_name",
    "subaward_state_sha256",
    "known_at",
    "effective_at",
    "first_seen_at",
    "source_url",
    "source_receipt_id",
    "source_response_sha256",
    "receipt_verified",
]

SUBAWARD_STATE_FIELDS = (
    "parent_generated_award_id",
    "subaward_id",
    "subaward_number",
    "action_date",
    "reported_subaward_amount",
    "description",
    "subrecipient_name",
)

SUBAWARD_PROJECTION_GENERATION_FIELDS = (
    "projection_generation_id",
    "subaward_snapshots_semantic_sha256",
    "subaward_snapshots_row_count",
    "projection_semantic_sha256",
)


def _canonical_json_bytes(value: Any) -> bytes:
    """Return stable JSON bytes used for every receipt and generation hash."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _utc_iso(value: str | datetime | None = None) -> str:
    if value is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"none", "nan", "nat"} else None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) and result not in {float("inf"), float("-inf")} else None


def _safe_error(exc: Exception | str) -> str:
    """Keep diagnostics while redacting credential-shaped material."""
    return re.sub(
        r"(?i)(api[\s_-]?key|authorization|token|secret|password)\s*[=:]\s*[^,;\n]+",
        r"\1=[redacted]",
        str(exc),
    )[:800]


def _truncate_utf8(value: Any, max_bytes: int = MAX_DESCRIPTION_UTF8_BYTES) -> str | None:
    text = _text(value)
    if text is None:
        return None
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _generation_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {
            str(key): _generation_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_generation_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_generation_value(item) for item in value), key=_canonical_json_bytes)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return _utc_iso(value)
    if isinstance(value, float):
        return value if value not in {float("inf"), float("-inf")} else str(value)
    if isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return _generation_value(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def subaward_projection_generation(frame: pd.DataFrame) -> dict[str, str | int]:
    """Return an order-independent binding for the complete snapshot ledger."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("subaward snapshots must be a pandas DataFrame")
    missing = [column for column in SUBAWARD_SNAPSHOT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(
            "subaward snapshots are missing canonical projection columns: "
            + ", ".join(missing)
        )
    records = [
        _canonical_json_bytes({
            column: _generation_value(row.get(column))
            for column in SUBAWARD_SNAPSHOT_COLUMNS
        })
        for _, row in frame.loc[:, SUBAWARD_SNAPSHOT_COLUMNS].iterrows()
    ]
    records.sort()
    hasher = hashlib.sha256()
    hasher.update(_canonical_json_bytes({
        "schema_version": SCHEMA_VERSION,
        "contract": SUBAWARD_SNAPSHOT_SCHEMA,
        "columns": SUBAWARD_SNAPSHOT_COLUMNS,
        "row_count": len(records),
    }))
    for record in records:
        hasher.update(b"\n")
        hasher.update(record)
    snapshot_digest = hasher.hexdigest()
    projection_digest = _sha256_json({
        "schema_version": SCHEMA_VERSION,
        "contract": SUBAWARD_PROJECTION_STATE_SCHEMA,
        "subaward_snapshots_semantic_sha256": snapshot_digest,
        "subaward_snapshots_row_count": len(records),
    })
    return {
        "projection_generation_id": f"subaward-{projection_digest[:24]}",
        "subaward_snapshots_semantic_sha256": snapshot_digest,
        "subaward_snapshots_row_count": len(records),
        "projection_semantic_sha256": projection_digest,
    }


def subaward_projection_generation_matches(
    state: dict | None,
    frame: pd.DataFrame,
) -> bool:
    """Return whether state activates exactly the supplied full ledger."""
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != SCHEMA_VERSION
        or state.get("contract") != SUBAWARD_PROJECTION_STATE_SCHEMA
        or state.get("activation_state") != "live"
        or state.get("projection_eligible") is not True
        or not _parent_coverage_matches(state)
    ):
        return False
    try:
        generation = subaward_projection_generation(frame)
    except (TypeError, ValueError):
        return False
    return all(
        state.get(field) == generation[field]
        for field in SUBAWARD_PROJECTION_GENERATION_FIELDS
    )


def subaward_parent_coverage_semantic_sha256(parents: list[dict[str, Any]]) -> str:
    """Bind count-only as well as detail-covered parent evidence into activation."""
    normalized = [_generation_value(parent) for parent in parents]
    normalized.sort(key=lambda row: _canonical_json_bytes(row))
    return _sha256_json({
        "schema_version": SCHEMA_VERSION,
        "contract": SUBAWARD_PROJECTION_STATE_SCHEMA,
        "parents": normalized,
    })


def _parent_coverage_matches(state: dict[str, Any]) -> bool:
    parents = state.get("parents")
    if not isinstance(parents, list):
        return False
    seen: set[str] = set()
    for parent in parents:
        if not isinstance(parent, dict):
            return False
        parent_id = _text(parent.get("parent_generated_award_id"))
        count = parent.get("subaward_count")
        binding = parent.get("count_receipt_binding")
        collection_state = parent.get("collection_state")
        detail_rows = parent.get("detail_rows")
        pages_fetched = parent.get("pages_fetched")
        detail_receipt_ids = parent.get("detail_receipt_ids")
        if (
            not parent_id
            or parent_id in seen
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or parent.get("count_verified") is not True
            or not isinstance(binding, dict)
            or binding.get("rail") != "subaward_count"
            or _text(binding.get("parent_generated_award_id")) != parent_id
            or binding.get("reported_subaward_count") != count
            or _text(binding.get("receipt_id")) != _text(parent.get("count_receipt_id"))
            or collection_state
            not in {"zero", "complete", "high_count_count_only", "run_cap_count_only"}
            or isinstance(detail_rows, bool)
            or not isinstance(detail_rows, int)
            or detail_rows < 0
            or isinstance(pages_fetched, bool)
            or not isinstance(pages_fetched, int)
            or pages_fetched < 0
            or not isinstance(detail_receipt_ids, list)
            or len(set(detail_receipt_ids)) != len(detail_receipt_ids)
            or any(not _text(receipt_id) for receipt_id in detail_receipt_ids)
            or pages_fetched != len(detail_receipt_ids)
        ):
            return False
        expected_pages = (count + PAGE_SIZE - 1) // PAGE_SIZE
        if collection_state == "zero" and not (
            count == 0
            and detail_rows == 0
            and pages_fetched == 0
            and parent.get("high_count_parent") is False
            and parent.get("source_exhausted") is True
        ):
            return False
        if collection_state == "complete" and not (
            1 <= count <= MAX_DETAIL_ROWS_PER_PARENT
            and detail_rows == count
            and pages_fetched == expected_pages
            and parent.get("high_count_parent") is False
            and parent.get("source_exhausted") is True
        ):
            return False
        if collection_state == "high_count_count_only" and not (
            count > MAX_DETAIL_ROWS_PER_PARENT
            and detail_rows == 0
            and pages_fetched == 0
            and parent.get("high_count_parent") is True
            and parent.get("source_exhausted") is False
        ):
            return False
        if collection_state == "run_cap_count_only" and not (
            1 <= count <= MAX_DETAIL_ROWS_PER_PARENT
            and detail_rows == 0
            and pages_fetched == 0
            and parent.get("high_count_parent") is False
            and parent.get("source_exhausted") is False
        ):
            return False
        seen.add(parent_id)
    return (
        state.get("selected_parent_count") == len(parents)
        and
        state.get("parent_coverage_semantic_sha256")
        == subaward_parent_coverage_semantic_sha256(parents)
    )


def _subaward_state_sha256(row: dict | pd.Series) -> str:
    return _sha256_json({
        field: _generation_value(row.get(field))
        for field in SUBAWARD_STATE_FIELDS
    })


def _validated_detail_receipt(
    receipt: dict | None,
    parent_generated_award_id: str,
    observed_at: str,
) -> tuple[str, str]:
    if not isinstance(receipt, dict):
        raise ValueError("subaward row is missing its exact identity-page receipt")
    receipt_id = _text(receipt.get("receipt_id"))
    response_sha256 = _text(receipt.get("response_sha256"))
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("contract") != SUBAWARD_COLLECTION_RECEIPT_SCHEMA
        or receipt.get("rail") != "subaward_detail"
        or receipt.get("endpoint") != SUBAWARDS_URL
        or _text(receipt.get("parent_generated_award_id")) != parent_generated_award_id
        or _text(receipt.get("observed_at")) is None
        or _utc_iso(str(receipt.get("observed_at"))) != observed_at
        or not receipt_id
        or not response_sha256
        or not re.fullmatch(r"[0-9a-f]{64}", response_sha256)
    ):
        raise ValueError("subaward row has an invalid identity-page receipt binding")
    return receipt_id, response_sha256


def normalize_subaward_snapshot(
    raw: dict,
    parent_generated_award_id: str,
    receipt: dict,
    observed_at: str | datetime,
) -> dict[str, Any]:
    """Normalize one official result without changing its source semantics."""
    if not isinstance(raw, dict):
        raise TypeError("subaward result must be an object")
    parent_id = _text(parent_generated_award_id)
    if not parent_id:
        raise ValueError("parent generated award id is required")
    raw_id = raw.get("id")
    raw_id_text = _text(raw_id)
    if (
        isinstance(raw_id, bool)
        or raw_id_text is None
        or re.fullmatch(r"[0-9]+", raw_id_text) is None
    ):
        raise ValueError("subaward result is missing native broker row id")
    subaward_id = str(int(raw_id_text))
    known_at = _utc_iso(observed_at)
    receipt_id, response_sha256 = _validated_detail_receipt(receipt, parent_id, known_at)
    action_date = _text(raw.get("action_date"))
    row: dict[str, Any] = {
        "parent_generated_award_id": parent_id,
        "subaward_id": subaward_id,
        "subaward_number": _text(raw.get("subaward_number")),
        "action_date": action_date,
        "reported_subaward_amount": _number(raw.get("amount")),
        "description": _truncate_utf8(raw.get("description")),
        "subrecipient_name": _text(raw.get("recipient_name")),
        "subaward_state_sha256": None,
        "known_at": known_at,
        "effective_at": action_date,
        "first_seen_at": known_at,
        "source_url": SUBAWARDS_URL,
        "source_receipt_id": receipt_id,
        "source_response_sha256": response_sha256,
        "receipt_verified": True,
    }
    row["subaward_state_sha256"] = _subaward_state_sha256(row)
    return {column: row.get(column) for column in SUBAWARD_SNAPSHOT_COLUMNS}


def append_subaward_snapshot_versions(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    """Append semantic versions by exact parent+broker identity, retaining A-B-A."""
    existing_frame = (
        existing.reindex(columns=SUBAWARD_SNAPSHOT_COLUMNS).copy()
        if isinstance(existing, pd.DataFrame)
        else pd.DataFrame(columns=SUBAWARD_SNAPSHOT_COLUMNS)
    )
    incoming_frame = (
        incoming.reindex(columns=SUBAWARD_SNAPSHOT_COLUMNS).copy()
        if isinstance(incoming, pd.DataFrame)
        else pd.DataFrame(columns=SUBAWARD_SNAPSHOT_COLUMNS)
    )
    retained = existing_frame.to_dict("records")
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in retained:
        parent_id = _text(row.get("parent_generated_award_id"))
        subaward_id = _text(row.get("subaward_id"))
        if parent_id and subaward_id:
            latest[(parent_id, subaward_id)] = row

    additions: list[dict[str, Any]] = []
    for candidate in incoming_frame.to_dict("records"):
        parent_id = _text(candidate.get("parent_generated_award_id"))
        subaward_id = _text(candidate.get("subaward_id"))
        if not parent_id or not subaward_id:
            raise ValueError("subaward snapshot identity requires exact parent id and broker id")
        candidate["parent_generated_award_id"] = parent_id
        candidate["subaward_id"] = subaward_id
        candidate["subaward_state_sha256"] = _subaward_state_sha256(candidate)
        key = (parent_id, subaward_id)
        prior = latest.get(key)
        if prior is not None:
            candidate["first_seen_at"] = prior.get("first_seen_at") or candidate.get("first_seen_at")
            if _text(prior.get("subaward_state_sha256")) == candidate["subaward_state_sha256"]:
                continue
            prior_clock = _utc_iso(str(prior.get("known_at")))
            candidate_clock = _utc_iso(str(candidate.get("known_at")))
            if candidate_clock <= prior_clock:
                raise ValueError(
                    "subaward semantic versions require a strictly increasing evidence clock"
                )
        additions.append(candidate)
        latest[key] = candidate

    return pd.DataFrame(
        [*retained, *additions],
        columns=SUBAWARD_SNAPSHOT_COLUMNS,
    ).reindex(columns=SUBAWARD_SNAPSHOT_COLUMNS).reset_index(drop=True)


def select_parent_awards(frame: pd.DataFrame, max_parents: int = MAX_PARENTS) -> pd.DataFrame:
    """Select the deterministic top exact parent ids from ``awards.parquet``."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("awards must be a pandas DataFrame")
    if "generated_award_id" not in frame.columns:
        raise ValueError("awards.parquet is missing generated_award_id")
    limit = max(0, min(int(max_parents), MAX_PARENTS))
    if limit == 0 or frame.empty:
        return frame.iloc[0:0].copy()

    selected = frame.copy()
    selected["generated_award_id"] = selected["generated_award_id"].map(_text)
    selected = selected.dropna(subset=["generated_award_id"])
    selected = selected.drop_duplicates(subset=["generated_award_id"], keep="last")
    if "total_obligated" in selected.columns:
        selected["__subaward_total_obligated"] = pd.to_numeric(
            selected["total_obligated"], errors="coerce"
        ).fillna(float("-inf"))
    else:
        selected["__subaward_total_obligated"] = float("-inf")
    selected = selected.sort_values(
        ["__subaward_total_obligated", "generated_award_id"],
        ascending=[False, True],
        kind="mergesort",
    ).head(limit)
    return selected.drop(columns=["__subaward_total_obligated"]).reset_index(drop=True)


def heartbeat_frame(status: dict) -> pd.DataFrame:
    """Build the runner-owned dated heartbeat only for a successful activation."""
    if not isinstance(status, dict) or status.get("status") != "ok":
        raise ValueError("subaward heartbeat requires a successful collection status")
    observed = pd.Timestamp(status["observed_at"])
    if observed.tzinfo is not None:
        observed = observed.tz_convert(None)
    observed = observed.normalize()
    row = {
        "collection_complete": 1.0,
        "parents_selected": float(status.get("parents_selected", 0)),
        "parents_counted": float(status.get("parents_counted", 0)),
        "detail_parents_collected": float(status.get("detail_parents_collected", 0)),
        "high_count_parents": float(status.get("high_count_parents", 0)),
        "run_cap_count_only_parents": float(status.get("run_cap_count_only_parents", 0)),
        "detail_rows_seen": float(status.get("detail_rows_seen", 0)),
        "snapshot_versions_total": float(status.get("snapshot_versions_total", 0)),
        "errors": float(len(status.get("errors") or [])),
    }
    return pd.DataFrame([row], index=[observed])


def _read_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=SUBAWARD_SNAPSHOT_COLUMNS)
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 - never overwrite unreadable accrued history
        raise RuntimeError(f"refusing to overwrite unreadable subaward ledger: {path}: {exc}") from exc
    if list(frame.columns) != SUBAWARD_SNAPSHOT_COLUMNS:
        raise RuntimeError(
            f"refusing to overwrite incompatible subaward ledger {path}: "
            "canonical columns or order do not match"
        )
    return frame.reindex(columns=SUBAWARD_SNAPSHOT_COLUMNS)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"refusing to overwrite unreadable subaward state: {path}: {_safe_error(exc)}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"refusing to overwrite non-object subaward state: {path}")
    return payload


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        frame.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _restore_file(path: Path, previous: bytes | None) -> None:
    """Best-effort rollback of a not-yet-activated bundle member."""
    if previous is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.rollback")
    try:
        tmp.write_bytes(previous)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _append_receipts(receipts: Iterable[dict[str, Any]], path: Path) -> int:
    """Append immutable hash-only receipts; no bodies, headers, or credentials."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = ""
    existing_receipts: dict[str, str] = {}
    if path.exists():
        try:
            existing_text = path.read_text(encoding="utf-8")
            for raw_line in existing_text.splitlines():
                if not raw_line.strip():
                    continue
                row = json.loads(raw_line)
                if not isinstance(row, dict) or not _text(row.get("receipt_id")):
                    raise ValueError("receipt record missing receipt_id")
                if _contains_forbidden_receipt_key(row):
                    raise ValueError("raw or sensitive receipt field is forbidden")
                canonical = json.dumps(row, sort_keys=True, separators=(",", ":"))
                receipt_id = str(row["receipt_id"])
                previous = existing_receipts.get(receipt_id)
                if previous is not None and previous != canonical:
                    raise ValueError("receipt ID is bound to conflicting evidence")
                existing_receipts[receipt_id] = canonical
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"refusing to overwrite unreadable receipt ledger: {path}: {_safe_error(exc)}") from exc

    new_lines: list[str] = []
    for receipt in receipts:
        receipt_id = _text(receipt.get("receipt_id"))
        if not receipt_id:
            raise ValueError("subaward collection receipt missing receipt_id")
        if _contains_forbidden_receipt_key(receipt):
            raise ValueError("raw or sensitive receipt field is forbidden")
        canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
        previous = existing_receipts.get(receipt_id)
        if previous is not None:
            if previous != canonical:
                raise ValueError("receipt ID is bound to conflicting evidence")
            continue
        new_lines.append(canonical)
        existing_receipts[receipt_id] = canonical
    if not new_lines:
        if not path.exists():
            tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            try:
                tmp.write_text("", encoding="utf-8")
                os.replace(tmp, path)
            finally:
                if tmp.exists():
                    tmp.unlink()
        return 0

    separator = "" if not existing_text or existing_text.endswith("\n") else "\n"
    content = existing_text + separator + "\n".join(new_lines) + "\n"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return len(new_lines)


_FORBIDDEN_RECEIPT_KEY = re.compile(
    r"(?i)(authorization|credential|password|secret|token|api[\s_-]?key|"
    r"^(?:raw[\s_-]?)?(?:request|response|body|headers?)$|"
    r"(?:request|response).*(?:body|headers?|payload|raw)|"
    r"raw.*(?:request|response|body|headers?))"
)


def _contains_forbidden_receipt_key(value: Any) -> bool:
    """Reject raw/sensitive key variants recursively while allowing hash names."""
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() not in {"request_sha256", "response_sha256"} and (
                _FORBIDDEN_RECEIPT_KEY.search(key_text)
            ):
                return True
            if _contains_forbidden_receipt_key(item):
                return True
    elif isinstance(value, (list, tuple, set)):
        return any(_contains_forbidden_receipt_key(item) for item in value)
    return False


class UsaspendingSubawardsCollector:
    """Collect the bounded exact-parent subaward source lane."""

    def __init__(
        self,
        root: Path | None = None,
        session: requests.Session | None = None,
        *,
        max_parents: int = MAX_PARENTS,
        request_pacing_seconds: float = 0.2,
        user_agent: str | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else Path(config.ROOT).resolve()
        self.session = session or requests.Session()
        self.max_parents = max(0, min(int(max_parents), MAX_PARENTS))
        self.request_pacing_seconds = max(0.0, float(request_pacing_seconds))
        self.headers = {
            "User-Agent": user_agent or os.getenv("USA_SPENDING_USER_AGENT", DEFAULT_USER_AGENT),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        body: dict[str, Any] | None = None,
        retries: int = 3,
        timeout: int = 60,
    ) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                if method == "GET":
                    response = self.session.get(endpoint, headers=self.headers, timeout=timeout)
                else:
                    response = self.session.post(
                        endpoint,
                        json=body,
                        headers=self.headers,
                        timeout=timeout,
                    )
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError(f"expected object response from {endpoint}")
                return payload
            except Exception as exc:  # noqa: BLE001 - bounded retry then fail closed
                last = exc
                if attempt + 1 < retries:
                    time.sleep(1.5 * (attempt + 1))
        assert last is not None
        raise last

    @staticmethod
    def _receipt(
        *,
        rail: str,
        endpoint: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        parent_generated_award_id: str,
        observed_at: str,
        page: int | None,
        record_count: int,
        reported_subaward_count: int | None = None,
    ) -> dict[str, Any]:
        """Bind canonical request/response hashes without persisting either body."""
        request_sha256 = _sha256_json(request_payload)
        response_sha256 = _sha256_json(response_payload)
        receipt_digest = _sha256_json({
            "observed_at": observed_at,
            "rail": rail,
            "endpoint": endpoint,
            "parent_generated_award_id": parent_generated_award_id,
            "page": page,
            "record_count": int(record_count),
            "reported_subaward_count": (
                int(reported_subaward_count)
                if reported_subaward_count is not None
                else None
            ),
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
        })
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "contract": SUBAWARD_COLLECTION_RECEIPT_SCHEMA,
            "receipt_id": f"usaspending-subaward:{receipt_digest}",
            "observed_at": observed_at,
            "rail": rail,
            "endpoint": endpoint,
            "parent_generated_award_id": parent_generated_award_id,
            "page": page,
            "record_count": int(record_count),
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
        }
        if reported_subaward_count is not None:
            receipt["reported_subaward_count"] = int(reported_subaward_count)
        return receipt

    def fetch_count(
        self,
        parent_generated_award_id: str,
        *,
        observed_at: str,
    ) -> tuple[int, dict[str, Any]]:
        parent_id = _text(parent_generated_award_id)
        if not parent_id:
            raise ValueError("parent generated award id is required")
        endpoint = SUBAWARD_COUNT_URL.format(award_id=quote(parent_id, safe=""))
        payload = self._request_json("GET", endpoint)
        count = payload.get("subawards")
        if isinstance(count, bool):
            raise ValueError("subaward count must be a non-negative integer")
        try:
            count_int = int(count)
        except (TypeError, ValueError) as exc:
            raise ValueError("subaward count response is missing exact subawards count") from exc
        if count_int < 0 or count_int != count:
            raise ValueError("subaward count must be a non-negative integer")
        request_payload = {"method": "GET", "endpoint": endpoint}
        return count_int, self._receipt(
            rail="subaward_count",
            endpoint=endpoint,
            request_payload=request_payload,
            response_payload=payload,
            parent_generated_award_id=parent_id,
            observed_at=observed_at,
            page=None,
            record_count=1,
            reported_subaward_count=count_int,
        )

    def fetch_detail_page(
        self,
        parent_generated_award_id: str,
        page: int,
        *,
        observed_at: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        parent_id = _text(parent_generated_award_id)
        if not parent_id:
            raise ValueError("parent generated award id is required")
        page_int = int(page)
        if page_int < 1 or page_int > MAX_PAGES_PER_PARENT:
            raise ValueError("subaward page exceeds the five-page safety cap")
        body = {
            "award_id": parent_id,
            "page": page_int,
            "limit": PAGE_SIZE,
            "sort": "action_date",
            "order": "desc",
        }
        payload = self._request_json("POST", SUBAWARDS_URL, body=body)
        results = payload.get("results")
        metadata = payload.get("page_metadata")
        if not isinstance(results, list) or not isinstance(metadata, dict):
            raise ValueError("subaward identity page requires results and page_metadata")
        if len(results) > PAGE_SIZE:
            raise ValueError("subaward identity page exceeded its 100-row limit")
        metadata_page = metadata.get("page")
        if metadata_page is not None and int(metadata_page) != page_int:
            raise ValueError("subaward identity page metadata does not match request")
        if any(not isinstance(row, dict) for row in results):
            raise ValueError("subaward identity page contains a non-object result")
        receipt = self._receipt(
            rail="subaward_detail",
            endpoint=SUBAWARDS_URL,
            request_payload=body,
            response_payload=payload,
            parent_generated_award_id=parent_id,
            observed_at=observed_at,
            page=page_int,
            record_count=len(results),
        )
        return results, receipt

    def _paths(self) -> dict[str, Path]:
        data_dir = self.root / "data" / "government_revenue"
        return {
            "awards": data_dir / "awards.parquet",
            "snapshots": data_dir / SUBAWARD_SNAPSHOTS_FILENAME,
            "receipts": data_dir / SUBAWARD_COLLECTION_RECEIPTS_FILENAME,
            "state": data_dir / SUBAWARD_PROJECTION_STATE_FILENAME,
            "status": data_dir / SUBAWARD_INGEST_STATUS_FILENAME,
        }

    def collect(self, *, observed_at: str | datetime | None = None) -> dict[str, Any]:
        """Run one complete bounded collection or leave the active bundle unchanged."""
        observed = _utc_iso(observed_at)
        paths = self._paths()
        if not paths["awards"].exists():
            raise FileNotFoundError(f"parent award ledger missing: {paths['awards']}")
        awards = pd.read_parquet(paths["awards"])
        parents = select_parent_awards(awards, self.max_parents)

        previous_snapshots = _read_existing(paths["snapshots"])
        previous_state = _read_json(paths["state"])
        previous_status = _read_json(paths["status"])
        if previous_state and (
            previous_state.get("schema_version") != SCHEMA_VERSION
            or previous_state.get("contract") != SUBAWARD_PROJECTION_STATE_SCHEMA
            or previous_state.get("activation_state") != "live"
        ):
            raise RuntimeError("refusing to replace unknown or inactive subaward projection state")
        if previous_status and (
            previous_status.get("schema_version") != SCHEMA_VERSION
            or previous_status.get("contract") != SUBAWARD_INGEST_STATUS_SCHEMA
            or previous_status.get("status") != "ok"
            or previous_status.get("partial") is not False
        ):
            raise RuntimeError("refusing to replace unknown or incomplete subaward ingest status")
        if previous_state.get("activation_state") == "live" and not subaward_projection_generation_matches(
            previous_state, previous_snapshots
        ):
            raise RuntimeError("active subaward projection state does not match its snapshot ledger")

        run_id = "usaspending-subaward-" + _sha256_json({
            "observed_at": observed,
            "parents": parents["generated_award_id"].astype(str).tolist(),
        })[:24]
        receipts: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        parent_states: list[dict[str, Any]] = []
        detail_rows_used = 0
        try:
            for parent_id in parents["generated_award_id"].astype(str).tolist():
                count, count_receipt = self.fetch_count(parent_id, observed_at=observed)
                receipts.append(count_receipt)
                if self.request_pacing_seconds:
                    time.sleep(self.request_pacing_seconds)

                high_count = count > MAX_DETAIL_ROWS_PER_PARENT
                run_cap_count_only = (
                    not high_count
                    and count > 0
                    and detail_rows_used + count > MAX_DETAIL_ROWS_PER_RUN
                )
                detail_receipt_ids: list[str] = []
                pages_fetched = 0
                parent_detail_rows = 0
                if count == 0:
                    collection_state = "zero"
                    source_exhausted = True
                elif high_count:
                    collection_state = "high_count_count_only"
                    source_exhausted = False
                elif run_cap_count_only:
                    collection_state = "run_cap_count_only"
                    source_exhausted = False
                else:
                    collection_state = "complete"
                    pages = (count + PAGE_SIZE - 1) // PAGE_SIZE
                    parent_subaward_ids: set[str] = set()
                    for page in range(1, pages + 1):
                        raw_rows, detail_receipt = self.fetch_detail_page(
                            parent_id,
                            page,
                            observed_at=observed,
                        )
                        receipts.append(detail_receipt)
                        detail_receipt_ids.append(str(detail_receipt["receipt_id"]))
                        pages_fetched += 1
                        for raw in raw_rows:
                            normalized = normalize_subaward_snapshot(
                                raw,
                                parent_id,
                                detail_receipt,
                                observed,
                            )
                            if normalized["subaward_id"] in parent_subaward_ids:
                                raise ValueError(
                                    f"duplicate native subaward id for {parent_id}: "
                                    f"{normalized['subaward_id']}"
                                )
                            parent_subaward_ids.add(normalized["subaward_id"])
                            rows.append(normalized)
                        parent_detail_rows += len(raw_rows)
                        if self.request_pacing_seconds:
                            time.sleep(self.request_pacing_seconds)
                    if parent_detail_rows != count:
                        raise ValueError(
                            f"subaward count/detail mismatch for {parent_id}: "
                            f"count={count} details={parent_detail_rows}"
                        )
                    detail_rows_used += parent_detail_rows
                    source_exhausted = True

                parent_states.append({
                    "parent_generated_award_id": parent_id,
                    "subaward_count": int(count),
                    "count_verified": True,
                    "high_count_parent": bool(high_count),
                    "collection_state": collection_state,
                    "detail_rows": int(parent_detail_rows),
                    "pages_fetched": int(pages_fetched),
                    "source_exhausted": bool(source_exhausted),
                    "count_receipt_id": count_receipt["receipt_id"],
                    "count_receipt_binding": {
                        "receipt_id": count_receipt["receipt_id"],
                        "rail": count_receipt["rail"],
                        "parent_generated_award_id": count_receipt["parent_generated_award_id"],
                        "reported_subaward_count": count_receipt["reported_subaward_count"],
                    },
                    "detail_receipt_ids": detail_receipt_ids,
                })
        except Exception:
            # Successful responses remain useful immutable evidence, but no partial
            # detail bundle, activation state, status, or heartbeat is published.
            if receipts:
                _append_receipts(receipts, paths["receipts"])
            raise

        if len(rows) > MAX_DETAIL_ROWS_PER_RUN:
            raise RuntimeError("subaward run exceeded its 2,000-row hard cap")
        incoming = pd.DataFrame(rows, columns=SUBAWARD_SNAPSHOT_COLUMNS)
        merged = append_subaward_snapshot_versions(previous_snapshots, incoming)
        generation = subaward_projection_generation(merged)
        bounds = {
            "max_parents": MAX_PARENTS,
            "selected_parent_limit": self.max_parents,
            "page_size": PAGE_SIZE,
            "max_pages_per_parent": MAX_PAGES_PER_PARENT,
            "max_detail_rows_per_parent": MAX_DETAIL_ROWS_PER_PARENT,
            "max_detail_rows_per_run": MAX_DETAIL_ROWS_PER_RUN,
            "public_downstream_row_cap": PUBLIC_DOWNSTREAM_ROW_CAP,
            "description_utf8_bytes": MAX_DESCRIPTION_UTF8_BYTES,
        }
        state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "contract": SUBAWARD_PROJECTION_STATE_SCHEMA,
            "activation_state": "live",
            "bounded_collection_complete": True,
            "projection_eligible": True,
            "run_id": run_id,
            "observed_at": observed,
            "last_successful_observed_at": observed,
            "bounds": bounds,
            "selected_parent_count": int(len(parents)),
            "detail_rows_this_run": int(len(rows)),
            "public_downstream_row_cap": PUBLIC_DOWNSTREAM_ROW_CAP,
            "parents": parent_states,
            "parent_coverage_semantic_sha256": subaward_parent_coverage_semantic_sha256(
                parent_states
            ),
            **generation,
        }
        status: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "contract": SUBAWARD_INGEST_STATUS_SCHEMA,
            "status": "ok",
            "partial": False,
            "collection_complete": True,
            "projection_eligible": True,
            "observed_at": observed,
            "last_successful_observed_at": observed,
            "run_id": run_id,
            "projection_generation_id": generation["projection_generation_id"],
            "bounded": True,
            "source_only": True,
            "daily_lane": True,
            "parents_selected": int(len(parents)),
            "parents_counted": int(len(parent_states)),
            "detail_parents_collected": sum(
                row["collection_state"] == "complete" for row in parent_states
            ),
            "high_count_parents": sum(
                row["collection_state"] == "high_count_count_only" for row in parent_states
            ),
            "run_cap_count_only_parents": sum(
                row["collection_state"] == "run_cap_count_only" for row in parent_states
            ),
            "detail_rows_seen": int(len(rows)),
            "snapshot_versions_total": int(len(merged)),
            "receipts_this_run": int(len(receipts)),
            "bounds": bounds,
            "errors": [],
            "source_urls": [SUBAWARD_COUNT_URL, SUBAWARDS_URL],
            "amount_semantics": (
                "reported subaward amount is self-reported subrecipient context; never federal "
                "obligation, outlay, backlog, revenue, cash, or additive prime award value"
            ),
        }

        # Receipt evidence lands before the ledger.  The state and status are the
        # activation markers and therefore land only after the full ledger does.
        _append_receipts(receipts, paths["receipts"])
        backups = {
            name: path.read_bytes() if path.exists() else None
            for name, path in (
                ("snapshots", paths["snapshots"]),
                ("state", paths["state"]),
                ("status", paths["status"]),
            )
        }
        try:
            _atomic_parquet(merged, paths["snapshots"])
            _atomic_json(state, paths["state"])
            _atomic_json(status, paths["status"])
        except Exception:
            for name in ("snapshots", "state", "status"):
                try:
                    _restore_file(paths[name], backups[name])
                except Exception:
                    pass
            raise
        return status


class UsaspendingSubawardsAdapter(Adapter):
    """Daily source-only adapter; the heartbeat exists only after success."""

    name = "usaspending_subawards"
    group = "government_revenue"
    stale_after_days = 4

    def stored_series(self) -> list[str]:
        return [Path(SUBAWARD_COLLECTOR_HEARTBEAT_FILENAME).stem]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        del full_history  # source-only daily lane has no historical expansion mode
        status = UsaspendingSubawardsCollector(root=config.ROOT).collect()
        if status.get("status") != "ok":
            raise RuntimeError("subaward collector did not activate a complete bundle")
        return {Path(SUBAWARD_COLLECTOR_HEARTBEAT_FILENAME).stem: heartbeat_frame(status)}


def write_heartbeat(status: dict[str, Any], root: Path) -> Path:
    """Persist direct-CLI health at the same path used by the standard runner."""
    path = (
        Path(root)
        / "data"
        / "government_revenue"
        / SUBAWARD_COLLECTOR_HEARTBEAT_FILENAME
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        heartbeat_frame(status).to_parquet(tmp, index=True)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--max-parents", type=int, default=MAX_PARENTS)
    args = parser.parse_args()
    status = UsaspendingSubawardsCollector(
        root=args.root,
        max_parents=args.max_parents,
    ).collect()
    write_heartbeat(status, args.root)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
