"""Bounded, official USAspending IDV-to-child-award evidence collector.

This is an identity rail, not a vehicle-participation or conversion model.  It
uses only the official IDV activity endpoint and preserves the source-issued
generated natural IDs for both endpoints of each relationship:

* ``POST /api/v2/idvs/activity/``
* parent identity: request ``award_id`` / response ``parent_generated_unique_award_id``
* child identity: response ``generated_unique_award_id``

Numeric ``award_id`` and ``parent_award_id`` are documented USAspending
surrogates and are deliberately not used as identities.  PIIDs are display
context only.  A source ``grandchild`` flag is retained so a two-hop row can
never be presented as a direct child relationship.
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

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config


IDV_ACTIVITY_URL = "https://api.usaspending.gov/api/v2/idvs/activity/"
IDV_DISCOVERY_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
DEFAULT_USER_AGENT = "MastermindX Government Revenue Foresight contact@mastermind-x.com"

IDV_DISCOVERY_AWARD_TYPE_CODES = (
    "IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B", "IDV_B_C", "IDV_C", "IDV_D", "IDV_E",
)
IDV_DISCOVERY_FIELDS = (
    "Award ID", "Recipient Name", "Start Date", "End Date", "Award Amount",
    "Awarding Agency", "Contract Award Type", "generated_internal_id",
)
MAX_DISCOVERY_PAGES = 5

IDV_RELATIONSHIP_SNAPSHOT_SCHEMA = "government_revenue.idv_relationship_snapshot.v1"
IDV_PROJECTION_STATE_SCHEMA = "government_revenue.idv_projection_state.v1"
IDV_COLLECTION_RECEIPT_SCHEMA = "government_revenue.idv_collection_receipt.v1"
IDV_DISCOVERY_RECEIPT_SCHEMA = "government_revenue.idv_discovery_receipt.v1"
IDV_SELECTION_MANIFEST_SCHEMA = "government_revenue.idv_selection_manifest.v1"
IDV_DISCOVERY_CONFIG_SCHEMA = "government_revenue.idv_discovery_config.v1"
IDV_INGEST_STATUS_SCHEMA = "government_revenue.idv_ingest_status.v1"
SCHEMA_VERSION = "1.0.0"

IDV_RELATIONSHIP_SNAPSHOTS_FILENAME = "idv_relationship_snapshots.parquet"
IDV_COLLECTION_RECEIPTS_FILENAME = "idv_collection_receipts.jsonl"
IDV_PROJECTION_STATE_FILENAME = "idv_projection_state.json"
IDV_INGEST_STATUS_FILENAME = "idv_ingest_status.json"
IDV_COLLECTOR_HEARTBEAT_FILENAME = "idv_collector_heartbeat.parquet"

MAX_IDVS = 80
PAGE_SIZE = 100
MAX_PAGES_PER_IDV = 5
MAX_DETAIL_ROWS_PER_IDV = PAGE_SIZE * MAX_PAGES_PER_IDV
MAX_DETAIL_ROWS_PER_RUN = 2_000
PUBLIC_DOWNSTREAM_ROW_CAP = 2_000
MAX_PUBLIC_TEXT_UTF8_BYTES = 2_000

IDV_RELATIONSHIP_SNAPSHOT_COLUMNS = [
    "idv_generated_award_id",
    "child_generated_award_id",
    "grandchild",
    "parent_piid",
    "child_piid",
    "recipient_name",
    "awarding_agency",
    "start_date",
    "potential_end_date",
    "obligated_amount",
    "awarded_amount",
    "idv_relationship_state_sha256",
    "known_at",
    "effective_at",
    "first_seen_at",
    "source_url",
    "source_receipt_id",
    "source_response_sha256",
    "receipt_verified",
]
IDV_RELATIONSHIP_STATE_FIELDS = tuple(
    column
    for column in IDV_RELATIONSHIP_SNAPSHOT_COLUMNS
    if column
    not in {
        "idv_relationship_state_sha256",
        "known_at",
        "effective_at",
        "first_seen_at",
        "source_url",
        "source_receipt_id",
        "source_response_sha256",
        "receipt_verified",
    }
)
IDV_PROJECTION_GENERATION_FIELDS = (
    "projection_generation_id",
    "idv_relationship_snapshots_semantic_sha256",
    "idv_relationship_snapshots_row_count",
    "projection_semantic_sha256",
)
IDV_ACTIVE_RELATIONSHIP_FIELDS = (
    "child_generated_award_id",
    "grandchild",
    "idv_relationship_state_sha256",
    "source_receipt_id",
)


def idv_selection_manifest_semantic_sha256(manifest: dict[str, Any]) -> str:
    if not isinstance(manifest, dict):
        raise TypeError("IDV selection manifest must be an object")
    return _sha256_json({key: value for key, value in manifest.items() if key != "semantic_sha256"})


def _selection_manifest_matches(state: dict[str, Any], parent_ids: list[str]) -> bool:
    manifest = state.get("selection_manifest")
    if not isinstance(manifest, dict):
        return False
    source = state.get("selection_source")
    receipts = manifest.get("discovery_receipts")
    selected = manifest.get("selected_parent_ids")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("contract") != IDV_SELECTION_MANIFEST_SCHEMA
        or manifest.get("selection_source") != source
        or manifest.get("observed_at") != state.get("observed_at")
        or not isinstance(receipts, list)
        or not isinstance(selected, list)
        or selected != parent_ids
        or len(selected) != len(set(selected))
        or any(not _is_generated_idv(value) for value in selected)
        or manifest.get("semantic_sha256") != idv_selection_manifest_semantic_sha256(manifest)
        or state.get("selection_manifest_semantic_sha256") != manifest.get("semantic_sha256")
    ):
        return False
    if source == "reviewed_source_native_idv_manifest":
        return (
            receipts == []
            and manifest.get("reviewed_manifest_sha256") == _sha256_json(selected)
            and manifest.get("endpoint") is None
            and manifest.get("filters_semantic_sha256") is None
        )
    if source != "official_usaspending_idv_discovery" or not receipts:
        return False
    if (
        manifest.get("endpoint") != IDV_DISCOVERY_URL
        or re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("recipient_scope_sha256") or "")) is None
        or re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("filters_semantic_sha256") or "")) is None
        or not isinstance(manifest.get("collection_scope_tickers"), list)
    ):
        return False
    pages: list[int] = []
    receipt_selected: list[str] = []
    for receipt in receipts:
        if (
            not isinstance(receipt, dict)
            or receipt.get("schema_version") != SCHEMA_VERSION
            or receipt.get("contract") != IDV_DISCOVERY_RECEIPT_SCHEMA
            or receipt.get("rail") != "idv_discovery_page"
            or receipt.get("endpoint") != IDV_DISCOVERY_URL
            or receipt.get("observed_at") != manifest.get("observed_at")
            or not isinstance(receipt.get("page"), int)
            or not 1 <= receipt["page"] <= MAX_DISCOVERY_PAGES
            or not isinstance(receipt.get("record_count"), int)
            or receipt["record_count"] < 0
            or not isinstance(receipt.get("selected_parent_ids"), list)
            or any(not _is_generated_idv(value) for value in receipt["selected_parent_ids"])
            or any(re.fullmatch(r"[a-f0-9]{64}", str(receipt.get(key) or "")) is None for key in ("request_sha256", "response_sha256"))
        ):
            return False
        expected_id = "usaspending-idv-discovery:" + _sha256_json({key: value for key, value in receipt.items() if key != "receipt_id"})
        if receipt.get("receipt_id") != expected_id:
            return False
        pages.append(receipt["page"])
        receipt_selected.extend(receipt["selected_parent_ids"])
    return pages == list(range(1, len(pages) + 1)) and selected == receipt_selected


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False, default=str
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _utc_iso(value: str | datetime | None = None) -> str:
    if value is None:
        stamp = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        stamp = value
    else:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat()


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


def _bounded_utf8_text(value: Any, *, label: str) -> str | None:
    text = _text(value)
    if text is not None and len(text.encode("utf-8")) > MAX_PUBLIC_TEXT_UTF8_BYTES:
        raise ValueError(f"IDV {label} exceeds the {MAX_PUBLIC_TEXT_UTF8_BYTES}-byte UTF-8 cap")
    return text


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) and result not in {float("inf"), float("-inf")} else None


def _safe_error(exc: Exception | str) -> str:
    return re.sub(
        r"(?i)(api[\s_-]?key|authorization|token|secret|password)\s*[=:]\s*[^,;\n]+",
        r"\1=[redacted]",
        str(exc),
    )[:800]


def _generation_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, dict):
        return {str(key): _generation_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
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


def _is_generated_idv(value: Any) -> bool:
    """Accept only USAspending's source-generated contract IDV namespace."""
    return bool((_text(value) or "").startswith("CONT_IDV_"))


def _is_generated_definitive_award(value: Any) -> bool:
    return bool((_text(value) or "").startswith("CONT_AWD_"))


def select_parent_idvs(
    awards: pd.DataFrame,
    reviewed_idv_ids: Iterable[str] | None = None,
    max_idvs: int = MAX_IDVS,
) -> pd.DataFrame:
    """Return only an explicit, reviewed list of source-native IDV identities.

    The current award ledger is a definitive-award ledger, not an IDV discovery
    universe. In particular, no ``CONT_AWD_*`` row may become an IDV merely
    because it is present locally. A caller must provide a reviewed manifest of
    official ``CONT_IDV_*`` generated IDs (or implement a separate official IDV
    discovery lane). ``awards`` is retained only for a stable call signature.
    """
    del awards
    limit = max(0, min(int(max_idvs), MAX_IDVS))
    if limit == 0:
        return pd.DataFrame({"generated_award_id": []})
    selected_ids: list[str] = []
    seen: set[str] = set()
    for value in reviewed_idv_ids or []:
        parent_id = _text(value)
        if not _is_generated_idv(parent_id):
            raise ValueError("reviewed IDV manifest contains a non-CONT_IDV source identity")
        if parent_id not in seen:
            selected_ids.append(parent_id)
            seen.add(parent_id)
        if len(selected_ids) >= limit:
            break
    return pd.DataFrame({"generated_award_id": selected_ids})


def _relationship_state_sha256(row: dict | pd.Series) -> str:
    return _sha256_json({field: _generation_value(row.get(field)) for field in IDV_RELATIONSHIP_STATE_FIELDS})


def idv_projection_generation(frame: pd.DataFrame) -> dict[str, str | int]:
    """Return an order-independent binding for the complete accrued ledger."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("IDV relationship snapshots must be a pandas DataFrame")
    missing = [column for column in IDV_RELATIONSHIP_SNAPSHOT_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("IDV relationship snapshots missing canonical columns: " + ", ".join(missing))
    records = [
        _canonical_json_bytes({column: _generation_value(row.get(column)) for column in IDV_RELATIONSHIP_SNAPSHOT_COLUMNS})
        for _, row in frame.loc[:, IDV_RELATIONSHIP_SNAPSHOT_COLUMNS].iterrows()
    ]
    records.sort()
    hasher = hashlib.sha256()
    hasher.update(_canonical_json_bytes({
        "schema_version": SCHEMA_VERSION,
        "contract": IDV_RELATIONSHIP_SNAPSHOT_SCHEMA,
        "columns": IDV_RELATIONSHIP_SNAPSHOT_COLUMNS,
        "row_count": len(records),
    }))
    for record in records:
        hasher.update(b"\n")
        hasher.update(record)
    snapshots_sha = hasher.hexdigest()
    projection_sha = _sha256_json({
        "schema_version": SCHEMA_VERSION,
        "contract": IDV_PROJECTION_STATE_SCHEMA,
        "idv_relationship_snapshots_semantic_sha256": snapshots_sha,
        "idv_relationship_snapshots_row_count": len(records),
    })
    return {
        "projection_generation_id": f"idv-{projection_sha[:24]}",
        "idv_relationship_snapshots_semantic_sha256": snapshots_sha,
        "idv_relationship_snapshots_row_count": len(records),
        "projection_semantic_sha256": projection_sha,
    }


def idv_parent_coverage_semantic_sha256(parents: list[dict[str, Any]]) -> str:
    normalized = [_generation_value(parent) for parent in parents]
    normalized.sort(key=_canonical_json_bytes)
    return _sha256_json({
        "schema_version": SCHEMA_VERSION,
        "contract": IDV_PROJECTION_STATE_SCHEMA,
        "parents": normalized,
    })


def idv_active_relationships_semantic_sha256(rows: list[dict[str, Any]]) -> str:
    """Bind one parent's exact active relationship set to the current run."""
    normalized = [
        {field: _generation_value(row.get(field)) for field in IDV_ACTIVE_RELATIONSHIP_FIELDS}
        for row in rows
    ]
    normalized.sort(key=_canonical_json_bytes)
    return _sha256_json({
        "schema_version": SCHEMA_VERSION,
        "contract": IDV_PROJECTION_STATE_SCHEMA,
        "active_relationships": normalized,
    })


def _parent_coverage_matches(state: dict[str, Any]) -> bool:
    parents = state.get("parents")
    if not isinstance(parents, list):
        return False
    seen: set[str] = set()
    detail_rows_total = 0
    for parent in parents:
        if not isinstance(parent, dict):
            return False
        parent_id = _text(parent.get("idv_generated_award_id"))
        total = parent.get("child_award_count")
        count_receipt_id = _text(parent.get("count_receipt_id"))
        count_binding = parent.get("count_receipt_binding")
        state_name = parent.get("collection_state")
        detail_rows = parent.get("detail_rows")
        pages_fetched = parent.get("pages_fetched")
        detail_receipt_ids = parent.get("detail_receipt_ids")
        active_relationships = parent.get("active_relationships")
        active_relationships_sha = parent.get("active_relationships_semantic_sha256")
        if (
            not _is_generated_idv(parent_id)
            or parent_id in seen
            or isinstance(total, bool) or not isinstance(total, int) or total < 0
            or parent.get("count_verified") is not True
            or not count_receipt_id
            or not isinstance(count_binding, dict)
            or count_binding.get("receipt_id") != count_receipt_id
            or count_binding.get("idv_generated_award_id") != parent_id
            or count_binding.get("reported_child_award_count") != total
            or state_name not in {"zero", "complete", "high_count_count_only", "run_cap_count_only"}
            or isinstance(detail_rows, bool) or not isinstance(detail_rows, int) or detail_rows < 0
            or isinstance(pages_fetched, bool) or not isinstance(pages_fetched, int) or pages_fetched < 0
            or not isinstance(detail_receipt_ids, list)
            or len(set(detail_receipt_ids)) != len(detail_receipt_ids)
            or any(not _text(item) for item in detail_receipt_ids)
            or not isinstance(active_relationships, list)
            or any(not isinstance(item, dict) for item in active_relationships)
            or active_relationships_sha != idv_active_relationships_semantic_sha256(active_relationships)
        ):
            return False
        active_identities: set[tuple[str, bool]] = set()
        for relationship in active_relationships:
            if not isinstance(relationship, dict) or set(relationship) != set(IDV_ACTIVE_RELATIONSHIP_FIELDS):
                return False
            child = relationship.get("child_generated_award_id")
            grandchild = relationship.get("grandchild")
            state_sha = relationship.get("idv_relationship_state_sha256")
            source_receipt_id = relationship.get("source_receipt_id")
            identity = (str(child or ""), grandchild)
            if (
                not _is_generated_definitive_award(child)
                or not isinstance(grandchild, bool)
                or identity in active_identities
                or re.fullmatch(r"[a-f0-9]{64}", str(state_sha or "")) is None
                or not isinstance(source_receipt_id, str)
                or source_receipt_id not in detail_receipt_ids
            ):
                return False
            active_identities.add(identity)
        expected_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        if state_name == "zero" and not (
            total == 0 and detail_rows == 0 and pages_fetched == 0 and not detail_receipt_ids
            and not active_relationships and parent.get("source_exhausted") is True
        ):
            return False
        if state_name == "complete" and not (
            1 <= total <= MAX_DETAIL_ROWS_PER_IDV and detail_rows == total
            and len(active_relationships) == total
            and pages_fetched == expected_pages and len(detail_receipt_ids) == expected_pages
            and count_receipt_id == detail_receipt_ids[0] and parent.get("source_exhausted") is True
        ):
            return False
        if state_name in {"high_count_count_only", "run_cap_count_only"} and not (
            detail_rows == 0 and pages_fetched == 0 and not detail_receipt_ids and not active_relationships
            and parent.get("source_exhausted") is False
        ):
            return False
        if state_name == "high_count_count_only" and total <= MAX_DETAIL_ROWS_PER_IDV:
            return False
        if state_name == "run_cap_count_only" and not (1 <= total <= MAX_DETAIL_ROWS_PER_IDV):
            return False
        detail_rows_total += detail_rows
        seen.add(parent_id)
    return (
        state.get("selected_idv_count") == len(parents)
        and state.get("detail_rows_this_run") == detail_rows_total
        and detail_rows_total <= MAX_DETAIL_ROWS_PER_RUN
        and state.get("parent_coverage_semantic_sha256") == idv_parent_coverage_semantic_sha256(parents)
        and _selection_manifest_matches(state, [str(parent["idv_generated_award_id"]) for parent in parents])
    )


def idv_projection_generation_matches(state: dict | None, frame: pd.DataFrame) -> bool:
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != SCHEMA_VERSION
        or state.get("contract") != IDV_PROJECTION_STATE_SCHEMA
        or state.get("activation_state") != "live"
        or state.get("projection_eligible") is not True
        or not _parent_coverage_matches(state)
    ):
        return False
    try:
        observed_at = _utc_iso(state.get("observed_at"))
    except (TypeError, ValueError):
        return False
    if (
        state.get("observed_at") != observed_at
        or state.get("last_successful_observed_at") != observed_at
        or not _text(state.get("run_id"))
        or state.get("public_downstream_row_cap") != PUBLIC_DOWNSTREAM_ROW_CAP
    ):
        return False
    try:
        generation = idv_projection_generation(frame)
    except (TypeError, ValueError):
        return False
    return all(state.get(field) == generation[field] for field in IDV_PROJECTION_GENERATION_FIELDS)


def _validated_receipt(receipt: dict | None, parent_id: str, observed_at: str) -> tuple[str, str]:
    if not isinstance(receipt, dict):
        raise ValueError("IDV relationship row is missing its exact page receipt")
    receipt_id = _text(receipt.get("receipt_id"))
    response_sha = _text(receipt.get("response_sha256"))
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("contract") != IDV_COLLECTION_RECEIPT_SCHEMA
        or receipt.get("rail") != "idv_activity_page"
        or receipt.get("endpoint") != IDV_ACTIVITY_URL
        or receipt.get("idv_generated_award_id") != parent_id
        or _text(receipt.get("observed_at")) is None
        or _utc_iso(str(receipt.get("observed_at"))) != observed_at
        or not receipt_id
        or not response_sha
        or re.fullmatch(r"[0-9a-f]{64}", response_sha) is None
    ):
        raise ValueError("IDV relationship row has an invalid receipt binding")
    return receipt_id, response_sha


def normalize_idv_relationship(raw: dict, idv_generated_award_id: str, receipt: dict, observed_at: str | datetime) -> dict[str, Any]:
    """Normalize one official relationship without falling back to PIID/surrogates."""
    if not isinstance(raw, dict):
        raise TypeError("IDV activity result must be an object")
    parent_id = _text(idv_generated_award_id)
    if not _is_generated_idv(parent_id):
        raise ValueError("IDV relationship requires a source-generated IDV ID")
    returned_parent = _text(raw.get("parent_generated_unique_award_id"))
    child_id = _text(raw.get("generated_unique_award_id"))
    grandchild = raw.get("grandchild")
    if returned_parent != parent_id:
        raise ValueError("IDV activity result parent natural ID does not match request")
    if not _is_generated_definitive_award(child_id):
        raise ValueError("IDV activity child must use the source-generated CONT_AWD namespace")
    if not isinstance(grandchild, bool):
        raise ValueError("IDV activity result lacks native grandchild relationship flag")
    known_at = _utc_iso(observed_at)
    receipt_id, response_sha = _validated_receipt(receipt, parent_id, known_at)
    row: dict[str, Any] = {
        "idv_generated_award_id": parent_id,
        "child_generated_award_id": child_id,
        "grandchild": grandchild,
        "parent_piid": _bounded_utf8_text(raw.get("parent_award_piid"), label="parent PIID"),
        "child_piid": _bounded_utf8_text(raw.get("piid"), label="child PIID"),
        "recipient_name": _bounded_utf8_text(raw.get("recipient_name"), label="recipient name"),
        "awarding_agency": _bounded_utf8_text(raw.get("awarding_agency"), label="awarding agency"),
        "start_date": _text(raw.get("period_of_performance_start_date")),
        "potential_end_date": _text(raw.get("period_of_performance_potential_end_date")),
        "obligated_amount": _number(raw.get("obligated_amount")),
        "awarded_amount": _number(raw.get("awarded_amount")),
        "idv_relationship_state_sha256": None,
        "known_at": known_at,
        "effective_at": _text(raw.get("period_of_performance_start_date")),
        "first_seen_at": known_at,
        "source_url": IDV_ACTIVITY_URL,
        "source_receipt_id": receipt_id,
        "source_response_sha256": response_sha,
        "receipt_verified": True,
    }
    row["idv_relationship_state_sha256"] = _relationship_state_sha256(row)
    return {column: row.get(column) for column in IDV_RELATIONSHIP_SNAPSHOT_COLUMNS}


def append_idv_relationship_versions(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Append semantic versions by exact natural-ID relationship, retaining A-B-A."""
    prior = existing.reindex(columns=IDV_RELATIONSHIP_SNAPSHOT_COLUMNS).copy()
    fresh = incoming.reindex(columns=IDV_RELATIONSHIP_SNAPSHOT_COLUMNS).copy()
    retained = prior.to_dict("records")
    latest: dict[tuple[str, str, bool], dict[str, Any]] = {}
    for row in retained:
        parent = _text(row.get("idv_generated_award_id"))
        child = _text(row.get("child_generated_award_id"))
        grandchild = row.get("grandchild")
        if parent and child and isinstance(grandchild, bool):
            latest[(parent, child, grandchild)] = row
    additions: list[dict[str, Any]] = []
    for candidate in fresh.to_dict("records"):
        parent = _text(candidate.get("idv_generated_award_id"))
        child = _text(candidate.get("child_generated_award_id"))
        grandchild = candidate.get("grandchild")
        if not _is_generated_idv(parent) or not _is_generated_definitive_award(child) or not isinstance(grandchild, bool):
            raise ValueError("IDV relationship snapshot identity requires exact natural IDs and grandchild flag")
        candidate["idv_generated_award_id"] = parent
        candidate["child_generated_award_id"] = child
        candidate["idv_relationship_state_sha256"] = _relationship_state_sha256(candidate)
        key = (parent, child, grandchild)
        previous = latest.get(key)
        if previous is not None:
            candidate["first_seen_at"] = previous.get("first_seen_at") or candidate.get("first_seen_at")
            if _text(previous.get("idv_relationship_state_sha256")) == candidate["idv_relationship_state_sha256"]:
                continue
            if _utc_iso(str(candidate.get("known_at"))) <= _utc_iso(str(previous.get("known_at"))):
                raise ValueError("IDV relationship semantic versions require a strictly increasing evidence clock")
        additions.append(candidate)
        latest[key] = candidate
    return pd.DataFrame([*retained, *additions], columns=IDV_RELATIONSHIP_SNAPSHOT_COLUMNS).reindex(
        columns=IDV_RELATIONSHIP_SNAPSHOT_COLUMNS
    ).reset_index(drop=True)


def _read_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=IDV_RELATIONSHIP_SNAPSHOT_COLUMNS)
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"refusing to overwrite unreadable IDV ledger: {path}: {exc}") from exc
    if list(frame.columns) != IDV_RELATIONSHIP_SNAPSHOT_COLUMNS:
        raise RuntimeError("refusing to overwrite incompatible IDV relationship ledger")
    return frame.reindex(columns=IDV_RELATIONSHIP_SNAPSHOT_COLUMNS)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"refusing to overwrite unreadable IDV state: {_safe_error(exc)}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("refusing to overwrite non-object IDV state")
    return payload


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        frame.to_parquet(temp, index=False)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _restore_file(path: Path, previous: bytes | None) -> None:
    if previous is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.rollback")
    try:
        temp.write_bytes(previous)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _append_receipts(receipts: Iterable[dict[str, Any]], path: Path) -> int:
    """Append immutable hash-only receipts. Raw request/response bodies never persist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    ids: set[str] = set()
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8")
            for line in existing.splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if not isinstance(item, dict) or not _text(item.get("receipt_id")):
                    raise ValueError("missing receipt ID")
                ids.add(str(item["receipt_id"]))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"refusing to overwrite unreadable IDV receipt ledger: {_safe_error(exc)}") from exc
    lines: list[str] = []
    for receipt in receipts:
        receipt_id = _text(receipt.get("receipt_id")) if isinstance(receipt, dict) else None
        if not receipt_id:
            raise ValueError("IDV collection receipt lacks receipt ID")
        if receipt_id not in ids:
            lines.append(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
            ids.add(receipt_id)
    if lines:
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            newline = "" if not existing or existing.endswith("\n") else "\n"
            temp.write_text(existing + newline + "\n".join(lines) + "\n", encoding="utf-8")
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
    return len(lines)


class UsaspendingIdvGraphCollector:
    """Daily, bounded source-only collector whose active state is an atomic bundle."""

    def __init__(
        self,
        root: Path | None = None,
        session: requests.Session | None = None,
        reviewed_idv_ids: Iterable[str] | None = None,
        idv_discovery_request: dict[str, Any] | None = None,
        max_idvs: int = MAX_IDVS,
        request_pacing_seconds: float = 0.2,
        user_agent: str | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else Path.cwd().resolve()
        self.session = session or requests.Session()
        self.reviewed_idv_ids = tuple(reviewed_idv_ids or ())
        self.idv_discovery_request = dict(idv_discovery_request) if idv_discovery_request is not None else None
        self.selection_manifest: dict[str, Any] | None = None
        self.max_idvs = max(0, min(int(max_idvs), MAX_IDVS))
        self.request_pacing_seconds = max(0.0, float(request_pacing_seconds))
        self.headers = {
            "User-Agent": user_agent or os.getenv("USA_SPENDING_USER_AGENT", DEFAULT_USER_AGENT),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post_json(
        self, body: dict[str, Any], *, endpoint: str = IDV_ACTIVITY_URL, retries: int = 3, timeout: int = 60,
    ) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                response = self.session.post(endpoint, json=body, headers=self.headers, timeout=timeout)
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("expected object response from IDV activity endpoint")
                return payload
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt + 1 < retries:
                    time.sleep(1.5 * (attempt + 1))
        assert last is not None
        raise last

    def discover_parent_idvs(self, *, observed_at: str | datetime | None = None) -> list[str]:
        """Run an explicitly configured, bounded official IDV discovery phase.

        This is intentionally injectable: callers supply the selection filters
        (including a reviewed recipient scope) rather than allowing the local
        definitive-award ledger to infer an IDV population. Discovery output is
        only a source-native parent seed, never issuer attribution.
        """
        if self.idv_discovery_request is None:
            return []
        supplied = self.idv_discovery_request
        observed = _utc_iso(observed_at)
        filters = supplied.get("filters")
        if not isinstance(filters, dict):
            raise ValueError("IDV discovery requires an explicit filters object")
        recipient_scope = filters.get("recipient_search_text")
        if not isinstance(recipient_scope, list) or not recipient_scope or any(not _text(item) for item in recipient_scope):
            raise ValueError("IDV discovery requires a reviewed recipient_search_text collection scope")
        supplied_codes = filters.get("award_type_codes")
        if not isinstance(supplied_codes, list) or set(supplied_codes) != set(IDV_DISCOVERY_AWARD_TYPE_CODES):
            raise ValueError("IDV discovery requires the complete official IDV award-type code set")
        scope_tickers = supplied.get("collection_scope_tickers") or []
        if (
            not isinstance(scope_tickers, list)
            or len(scope_tickers) != len(set(scope_tickers))
            or any(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", str(value or "")) is None for value in scope_tickers)
        ):
            raise ValueError("IDV discovery collection_scope_tickers are malformed")
        limit = min(self.max_idvs, PAGE_SIZE)
        if limit == 0:
            return []
        selected: list[str] = []
        seen: set[str] = set()
        discovery_receipts: list[dict[str, Any]] = []
        for page in range(1, MAX_DISCOVERY_PAGES + 1):
            body = {
                "filters": filters,
                "fields": list(IDV_DISCOVERY_FIELDS),
                "page": page,
                "limit": limit,
                "sort": "Award Amount",
                "order": "desc",
                "subawards": False,
            }
            payload = self._post_json(body, endpoint=IDV_DISCOVERY_URL)
            results, metadata = payload.get("results"), payload.get("page_metadata")
            if not isinstance(results, list) or not isinstance(metadata, dict) or any(not isinstance(row, dict) for row in results):
                raise ValueError("IDV discovery requires object results and page metadata")
            if len(results) > limit or (metadata.get("page") is not None and metadata.get("page") != page):
                raise ValueError("IDV discovery pagination is inconsistent")
            page_selected: list[str] = []
            for result in results:
                parent_id = _text(result.get("generated_internal_id"))
                if parent_id is not None and _is_generated_idv(parent_id) and parent_id not in seen:
                    selected.append(parent_id)
                    page_selected.append(parent_id)
                    seen.add(parent_id)
                    if len(selected) >= self.max_idvs:
                        break
            receipt = {
                "schema_version": SCHEMA_VERSION,
                "contract": IDV_DISCOVERY_RECEIPT_SCHEMA,
                "receipt_id": "",
                "observed_at": observed,
                "rail": "idv_discovery_page",
                "endpoint": IDV_DISCOVERY_URL,
                "page": page,
                "record_count": len(results),
                "selected_parent_ids": page_selected,
                "request_sha256": _sha256_json(body),
                "response_sha256": _sha256_json(payload),
            }
            receipt["receipt_id"] = "usaspending-idv-discovery:" + _sha256_json(
                {key: value for key, value in receipt.items() if key != "receipt_id"}
            )
            discovery_receipts.append(receipt)
            if len(selected) >= self.max_idvs or metadata.get("hasNext") is not True:
                break
            if self.request_pacing_seconds:
                time.sleep(self.request_pacing_seconds)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "contract": IDV_SELECTION_MANIFEST_SCHEMA,
            "selection_source": "official_usaspending_idv_discovery",
            "observed_at": observed,
            "reviewed_at": _text(supplied.get("reviewed_at")),
            "endpoint": IDV_DISCOVERY_URL,
            "collection_scope_tickers": sorted(str(value) for value in scope_tickers),
            "recipient_scope_sha256": _sha256_json(sorted(_text(value) for value in recipient_scope)),
            "filters_semantic_sha256": _sha256_json(filters),
            "discovery_receipts": discovery_receipts,
            "selected_parent_ids": selected,
            "semantic_sha256": "",
        }
        manifest["semantic_sha256"] = idv_selection_manifest_semantic_sha256(manifest)
        self.selection_manifest = manifest
        return selected

    @staticmethod
    def _receipt(
        *, request_payload: dict[str, Any], response_payload: dict[str, Any], idv_generated_award_id: str,
        observed_at: str, page: int, record_count: int, reported_child_award_count: int,
    ) -> dict[str, Any]:
        request_sha = _sha256_json(request_payload)
        response_sha = _sha256_json(response_payload)
        digest = _sha256_json({
            "observed_at": observed_at, "rail": "idv_activity_page", "endpoint": IDV_ACTIVITY_URL,
            "idv_generated_award_id": idv_generated_award_id, "page": page, "record_count": record_count,
            "reported_child_award_count": reported_child_award_count, "request_sha256": request_sha,
            "response_sha256": response_sha,
        })
        return {
            "schema_version": SCHEMA_VERSION, "contract": IDV_COLLECTION_RECEIPT_SCHEMA,
            "receipt_id": f"usaspending-idv:{digest}", "observed_at": observed_at,
            "rail": "idv_activity_page", "endpoint": IDV_ACTIVITY_URL,
            "idv_generated_award_id": idv_generated_award_id, "page": page, "record_count": record_count,
            "reported_child_award_count": reported_child_award_count,
            "request_sha256": request_sha, "response_sha256": response_sha,
        }

    def fetch_activity_page(self, idv_generated_award_id: str, page: int, *, observed_at: str) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
        parent_id = _text(idv_generated_award_id)
        page_int = int(page)
        if not _is_generated_idv(parent_id):
            raise ValueError("IDV activity requires a source-generated CONT_IDV identifier")
        if page_int < 1 or page_int > MAX_PAGES_PER_IDV:
            raise ValueError("IDV activity page exceeds the five-page safety cap")
        body = {"award_id": parent_id, "page": page_int, "limit": PAGE_SIZE, "hide_edge_cases": False}
        payload = self._post_json(body)
        rows = payload.get("results")
        metadata = payload.get("page_metadata")
        if not isinstance(rows, list) or not isinstance(metadata, dict) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("IDV activity page requires object results and metadata")
        if len(rows) > PAGE_SIZE:
            raise ValueError("IDV activity page exceeded its 100-row limit")
        total = metadata.get("total")
        if isinstance(total, bool):
            raise ValueError("IDV activity page has invalid total")
        try:
            total_int = int(total)
        except (TypeError, ValueError) as exc:
            raise ValueError("IDV activity page lacks total count") from exc
        if total_int < 0 or total_int != total:
            raise ValueError("IDV activity total must be a non-negative integer")
        if metadata.get("page") is not None and int(metadata["page"]) != page_int:
            raise ValueError("IDV activity metadata page does not match request")
        expected_has_next = page_int * PAGE_SIZE < total_int
        if metadata.get("hasNext") is not expected_has_next:
            raise ValueError("IDV activity pagination metadata is inconsistent with total")
        expected_rows = max(0, min(PAGE_SIZE, total_int - ((page_int - 1) * PAGE_SIZE)))
        if len(rows) != expected_rows:
            raise ValueError("IDV activity page result count does not match total")
        if rows and any(_text(row.get("parent_generated_unique_award_id")) != parent_id for row in rows):
            raise ValueError("IDV activity page contains a relationship for the wrong parent")
        receipt = self._receipt(
            request_payload=body, response_payload=payload, idv_generated_award_id=parent_id,
            observed_at=observed_at, page=page_int, record_count=len(rows), reported_child_award_count=total_int,
        )
        return rows, receipt, total_int

    def _paths(self) -> dict[str, Path]:
        data_dir = self.root / "data" / "government_revenue"
        return {
            "awards": data_dir / "awards.parquet", "snapshots": data_dir / IDV_RELATIONSHIP_SNAPSHOTS_FILENAME,
            "receipts": data_dir / IDV_COLLECTION_RECEIPTS_FILENAME, "state": data_dir / IDV_PROJECTION_STATE_FILENAME,
            "status": data_dir / IDV_INGEST_STATUS_FILENAME,
        }

    def collect(self, *, observed_at: str | datetime | None = None) -> dict[str, Any]:
        observed = _utc_iso(observed_at)
        paths = self._paths()
        reviewed_ids = self.reviewed_idv_ids or tuple(self.discover_parent_idvs(observed_at=observed))
        selection_source = (
            "reviewed_source_native_idv_manifest"
            if self.reviewed_idv_ids
            else "official_usaspending_idv_discovery"
            if self.idv_discovery_request is not None
            else "reviewed_source_native_idv_manifest"
        )
        # This rail never reads ``awards.parquet`` for parent selection: that
        # ledger contains definitive awards and is not an IDV discovery source.
        parents = select_parent_idvs(pd.DataFrame(), reviewed_ids, self.max_idvs)
        if parents.empty:
            # Do not manufacture a zero-IDV "live" bundle from a
            # definitive-award ledger. This rail needs an explicit reviewed
            # source-native manifest or a separately governed official IDV
            # discovery collector before it may call the activity endpoint.
            return {
                "schema_version": SCHEMA_VERSION,
                "contract": IDV_INGEST_STATUS_SCHEMA,
                "status": "unavailable",
                "partial": True,
                "collection_complete": False,
                "projection_eligible": False,
                "observed_at": observed,
                "activation_state": "not_initialized",
                "selection_source": selection_source,
                "idvs_selected": 0,
                "errors": [
                    "no reviewed source-native CONT_IDV manifest or official IDV discovery result configured; definitive-award rows are not IDV parents"
                ],
            }
        selected_parent_ids = parents["generated_award_id"].astype(str).tolist()
        if self.reviewed_idv_ids:
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "contract": IDV_SELECTION_MANIFEST_SCHEMA,
                "selection_source": "reviewed_source_native_idv_manifest",
                "observed_at": observed,
                "reviewed_at": None,
                "endpoint": None,
                "collection_scope_tickers": [],
                "recipient_scope_sha256": None,
                "filters_semantic_sha256": None,
                "reviewed_manifest_sha256": _sha256_json(selected_parent_ids),
                "discovery_receipts": [],
                "selected_parent_ids": selected_parent_ids,
                "semantic_sha256": "",
            }
            manifest["semantic_sha256"] = idv_selection_manifest_semantic_sha256(manifest)
            self.selection_manifest = manifest
        if self.selection_manifest is None or self.selection_manifest.get("selected_parent_ids") != selected_parent_ids:
            raise RuntimeError("IDV parent selection lacks an exact immutable selection manifest")
        previous_snapshots = _read_existing(paths["snapshots"])
        previous_state = _read_json(paths["state"])
        previous_status = _read_json(paths["status"])
        if previous_state and not idv_projection_generation_matches(previous_state, previous_snapshots):
            raise RuntimeError("refusing to replace an invalid active IDV source bundle")
        if previous_state and _utc_iso(previous_state.get("observed_at")) >= observed:
            raise RuntimeError("IDV collection evidence clock must advance strictly")
        if previous_status and (
            previous_status.get("schema_version") != SCHEMA_VERSION
            or previous_status.get("contract") != IDV_INGEST_STATUS_SCHEMA
            or previous_status.get("status") != "ok" or previous_status.get("partial") is not False
        ):
            raise RuntimeError("refusing to replace unknown or incomplete IDV ingest status")

        receipts: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        parent_states: list[dict[str, Any]] = []
        detail_rows_used = 0
        try:
            for parent_id in parents["generated_award_id"].astype(str).tolist():
                first_rows, count_receipt, total = self.fetch_activity_page(parent_id, 1, observed_at=observed)
                receipts.append(count_receipt)
                active_relationships: list[dict[str, Any]] = []
                if self.request_pacing_seconds:
                    time.sleep(self.request_pacing_seconds)
                if total == 0:
                    state_name, source_exhausted, detail_receipt_ids, pages_fetched, detail_rows = "zero", True, [], 0, 0
                elif total > MAX_DETAIL_ROWS_PER_IDV:
                    state_name, source_exhausted, detail_receipt_ids, pages_fetched, detail_rows = "high_count_count_only", False, [], 0, 0
                elif detail_rows_used + total > MAX_DETAIL_ROWS_PER_RUN:
                    state_name, source_exhausted, detail_receipt_ids, pages_fetched, detail_rows = "run_cap_count_only", False, [], 0, 0
                else:
                    state_name, source_exhausted = "complete", True
                    detail_receipt_ids, pages_fetched = [str(count_receipt["receipt_id"])], 1
                    parent_observations = [(raw, count_receipt) for raw in first_rows]
                    expected_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
                    for page in range(2, expected_pages + 1):
                        page_rows, page_receipt, reported_total = self.fetch_activity_page(parent_id, page, observed_at=observed)
                        if reported_total != total:
                            raise ValueError("IDV activity total changed during one collection run")
                        receipts.append(page_receipt)
                        detail_receipt_ids.append(str(page_receipt["receipt_id"]))
                        pages_fetched += 1
                        parent_observations.extend((raw, page_receipt) for raw in page_rows)
                        if self.request_pacing_seconds:
                            time.sleep(self.request_pacing_seconds)
                    if len(parent_observations) != total:
                        raise ValueError("IDV activity count/detail mismatch")
                    identities: set[tuple[str, bool]] = set()
                    for raw, page_receipt in parent_observations:
                        normalized = normalize_idv_relationship(raw, parent_id, page_receipt, observed)
                        identity = (normalized["child_generated_award_id"], normalized["grandchild"])
                        if identity in identities:
                            raise ValueError("duplicate natural child relationship within an IDV page set")
                        identities.add(identity)
                        rows.append(normalized)
                        active_relationships.append({
                            "child_generated_award_id": normalized["child_generated_award_id"],
                            "grandchild": normalized["grandchild"],
                            "idv_relationship_state_sha256": normalized["idv_relationship_state_sha256"],
                            "source_receipt_id": normalized["source_receipt_id"],
                        })
                    detail_rows = len(parent_observations)
                    detail_rows_used += detail_rows
                active_relationships.sort(key=_canonical_json_bytes)
                parent_states.append({
                    "idv_generated_award_id": parent_id, "child_award_count": int(total), "count_verified": True,
                    "collection_state": state_name, "detail_rows": int(detail_rows), "pages_fetched": int(pages_fetched),
                    "source_exhausted": bool(source_exhausted), "count_receipt_id": count_receipt["receipt_id"],
                    "count_receipt_binding": {"receipt_id": count_receipt["receipt_id"], "idv_generated_award_id": parent_id, "reported_child_award_count": int(total)},
                    "detail_receipt_ids": detail_receipt_ids,
                    "active_relationships": active_relationships,
                    "active_relationships_semantic_sha256": idv_active_relationships_semantic_sha256(active_relationships),
                })
        except Exception:
            if receipts:
                _append_receipts(receipts, paths["receipts"])
            raise

        if len(rows) > MAX_DETAIL_ROWS_PER_RUN:
            raise RuntimeError("IDV collection exceeded its hard row cap")
        incoming = pd.DataFrame(rows, columns=IDV_RELATIONSHIP_SNAPSHOT_COLUMNS)
        merged = append_idv_relationship_versions(previous_snapshots, incoming)
        generation = idv_projection_generation(merged)
        bounds = {
            "max_idvs": MAX_IDVS, "selected_idv_limit": self.max_idvs, "page_size": PAGE_SIZE,
            "max_pages_per_idv": MAX_PAGES_PER_IDV, "max_detail_rows_per_idv": MAX_DETAIL_ROWS_PER_IDV,
            "max_detail_rows_per_run": MAX_DETAIL_ROWS_PER_RUN, "public_downstream_row_cap": PUBLIC_DOWNSTREAM_ROW_CAP,
        }
        run_id = "usaspending-idv-" + _sha256_json({"observed_at": observed, "selection_manifest": self.selection_manifest["semantic_sha256"]})[:24]
        state = {
            "schema_version": SCHEMA_VERSION, "contract": IDV_PROJECTION_STATE_SCHEMA, "activation_state": "live",
            "bounded_collection_complete": True, "projection_eligible": True, "run_id": run_id, "observed_at": observed,
            "last_successful_observed_at": observed, "bounds": bounds, "selected_idv_count": int(len(parents)),
            "selection_source": selection_source,
            "selection_manifest_semantic_sha256": self.selection_manifest["semantic_sha256"],
            "selection_manifest": self.selection_manifest,
            "detail_rows_this_run": int(len(rows)), "public_downstream_row_cap": PUBLIC_DOWNSTREAM_ROW_CAP,
            "parents": parent_states, "parent_coverage_semantic_sha256": idv_parent_coverage_semantic_sha256(parent_states), **generation,
        }
        status = {
            "schema_version": SCHEMA_VERSION, "contract": IDV_INGEST_STATUS_SCHEMA, "status": "ok", "partial": False,
            "collection_complete": True, "projection_eligible": True, "observed_at": observed, "last_successful_observed_at": observed,
            "run_id": run_id, "projection_generation_id": generation["projection_generation_id"], "bounded": True, "source_only": True,
            "daily_lane": True, "idvs_selected": int(len(parents)), "idvs_counted": int(len(parent_states)),
            "detail_idvs_collected": sum(item["collection_state"] == "complete" for item in parent_states),
            "high_count_idvs": sum(item["collection_state"] == "high_count_count_only" for item in parent_states),
            "run_cap_count_only_idvs": sum(item["collection_state"] == "run_cap_count_only" for item in parent_states),
            "detail_rows_seen": int(len(rows)), "snapshot_versions_total": int(len(merged)), "receipts_this_run": int(len(receipts)),
            "selection_source": selection_source,
            "selection_manifest_semantic_sha256": self.selection_manifest["semantic_sha256"],
            "bounds": bounds, "errors": [],
            "source_urls": [IDV_ACTIVITY_URL] + ([IDV_DISCOVERY_URL] if self.idv_discovery_request is not None else []),
            "relationship_semantics": "official USAspending IDV activity only; not a vehicle seat, utilization, conversion, revenue, or investment authority",
        }
        _append_receipts(receipts, paths["receipts"])
        backups = {name: path.read_bytes() if path.exists() else None for name, path in (("snapshots", paths["snapshots"]), ("state", paths["state"]), ("status", paths["status"]))}
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


def heartbeat_frame(status: dict[str, Any]) -> pd.DataFrame:
    if not isinstance(status, dict) or status.get("status") != "ok":
        raise ValueError("IDV heartbeat requires a successful collection status")
    observed = pd.Timestamp(status["observed_at"])
    if observed.tzinfo is not None:
        observed = observed.tz_convert(None)
    observed = observed.normalize()
    return pd.DataFrame([{
        "collection_complete": 1.0, "idvs_selected": float(status.get("idvs_selected", 0)),
        "idvs_counted": float(status.get("idvs_counted", 0)), "detail_idvs_collected": float(status.get("detail_idvs_collected", 0)),
        "high_count_idvs": float(status.get("high_count_idvs", 0)), "run_cap_count_only_idvs": float(status.get("run_cap_count_only_idvs", 0)),
        "detail_rows_seen": float(status.get("detail_rows_seen", 0)), "snapshot_versions_total": float(status.get("snapshot_versions_total", 0)),
    }], index=[observed])


def load_idv_discovery_config(root: Path, path: Path | None = None) -> dict[str, Any] | None:
    config_path = path or (Path(root) / "config" / "government_revenue" / "idv_discovery.v1.json")
    if not config_path.exists():
        return None
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("IDV discovery config is unreadable") from exc
    expected_keys = {
        "contract", "schema_version", "enabled", "reviewed_at", "max_idvs",
        "collection_scope_tickers", "filters", "limitations",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ValueError("IDV discovery config shape mismatch")
    if value.get("contract") != IDV_DISCOVERY_CONFIG_SCHEMA or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("IDV discovery config contract mismatch")
    if not isinstance(value.get("enabled"), bool):
        raise ValueError("IDV discovery config enabled flag is invalid")
    if value["enabled"] is False:
        return None
    try:
        _utc_iso(value.get("reviewed_at"))
    except (TypeError, ValueError) as exc:
        raise ValueError("IDV discovery config reviewed_at is invalid") from exc
    max_idvs = value.get("max_idvs")
    filters = value.get("filters")
    tickers = value.get("collection_scope_tickers")
    limitations = value.get("limitations")
    if (
        isinstance(max_idvs, bool) or not isinstance(max_idvs, int) or not 1 <= max_idvs <= MAX_IDVS
        or not isinstance(filters, dict) or set(filters) != {"recipient_search_text", "award_type_codes"}
        or not isinstance(filters.get("recipient_search_text"), list) or not filters["recipient_search_text"]
        or any(not _bounded_utf8_text(item, label="recipient discovery scope") for item in filters["recipient_search_text"])
        or not isinstance(filters.get("award_type_codes"), list)
        or set(filters["award_type_codes"]) != set(IDV_DISCOVERY_AWARD_TYPE_CODES)
        or not isinstance(tickers, list) or len(tickers) != len(set(tickers))
        or any(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", str(value or "")) is None for value in tickers)
        or not isinstance(limitations, list) or not limitations or any(not _text(item) for item in limitations)
    ):
        raise ValueError("IDV discovery config bounds or reviewed scope are invalid")
    return {
        "max_idvs": max_idvs,
        "idv_discovery_request": {
            "filters": filters,
            "collection_scope_tickers": tickers,
            "reviewed_at": value["reviewed_at"],
        },
    }


class UsaspendingIdvGraphAdapter(Adapter):
    name = "usaspending_idv_graph"
    group = "government_revenue"
    stale_after_days = 4

    def stored_series(self) -> list[str]:
        return [Path(IDV_COLLECTOR_HEARTBEAT_FILENAME).stem]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        del full_history
        settings = load_idv_discovery_config(config.ROOT)
        if settings is None:
            return {}
        status = UsaspendingIdvGraphCollector(root=config.ROOT, **settings).collect()
        if status.get("status") != "ok":
            return {}
        return {Path(IDV_COLLECTOR_HEARTBEAT_FILENAME).stem: heartbeat_frame(status)}


def write_heartbeat(status: dict[str, Any], root: Path) -> Path:
    path = Path(root) / "data" / "government_revenue" / IDV_COLLECTOR_HEARTBEAT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        heartbeat_frame(status).to_parquet(temp, index=True)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--max-idvs", type=int, default=MAX_IDVS)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--reviewed-idv", action="append", default=[])
    args = parser.parse_args(argv)
    settings = load_idv_discovery_config(args.root, args.config) if args.config or not args.reviewed_idv else None
    collector = UsaspendingIdvGraphCollector(
        root=args.root,
        max_idvs=min(args.max_idvs, settings["max_idvs"]) if settings else args.max_idvs,
        reviewed_idv_ids=args.reviewed_idv,
        idv_discovery_request=settings["idv_discovery_request"] if settings else None,
    )
    status = collector.collect()
    if status.get("status") == "ok":
        write_heartbeat(status, args.root)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
