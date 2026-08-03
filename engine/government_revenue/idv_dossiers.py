"""Strict, display-only projection of official USAspending IDV activity.

An IDV is deliberately *not* assumed to be a definitive award in the prime
dossier.  This projection therefore keeps source-native ``CONT_IDV_*`` parents
as standalone provenance entities and optionally bridges a child only when its
exact generated natural ID is already present in the prime dossier map.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from collectors import usaspending_idv_graph as collector


IDV_DOSSIER_CONTRACT = "government_idv_dossiers.v1"
IDV_DOSSIER_SCHEMA_VERSION = "1.0.0"
IDV_DOSSIER_FILENAME = "idv_dossiers.json"
IDV_DOSSIER_CONTENT_ID_PREFIX = "griv1-"
MAX_IDV_RECORDS = 2_000
FRESHNESS_MAX_AGE_DAYS = 4
_SOURCE_FILES = (
    collector.IDV_RELATIONSHIP_SNAPSHOTS_FILENAME,
    collector.IDV_COLLECTION_RECEIPTS_FILENAME,
    collector.IDV_PROJECTION_STATE_FILENAME,
    collector.IDV_INGEST_STATUS_FILENAME,
)
_SOURCE_CONTRACTS = {
    "state": collector.IDV_PROJECTION_STATE_SCHEMA,
    "status": collector.IDV_INGEST_STATUS_SCHEMA,
    "receipt": collector.IDV_COLLECTION_RECEIPT_SCHEMA,
}
_IDV_LIMITATION = (
    "Official USAspending IDV activity records an award relationship only; it does not establish "
    "vehicle participation, a vehicle seat, utilization, conversion, revenue, backlog, or investment authority."
)

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


def _root(root: Path | None) -> Path:
    return Path(root).resolve() if root is not None else Path.cwd().resolve()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def idv_dossier_content_id(payload: Mapping[str, Any]) -> str | None:
    """Return the immutable identity, excluding assembly timestamp and self-ID."""
    try:
        fingerprint = {key: value for key, value in payload.items() if key not in {"content_id", "generated_at"}}
        return IDV_DOSSIER_CONTENT_ID_PREFIX + _canonical_sha256(fingerprint)[:24]
    except (TypeError, ValueError):
        return None


def _text(value: Any, *, limit: int = 4_000) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    value = " ".join(str(value).split())
    return value[:limit] or None


def _required_text(value: Any, label: str, *, limit: int = 4_000) -> str:
    result = _text(value, limit=limit)
    if result is None:
        raise ValueError(f"IDV source lacks {label}")
    return result


def _public_text(value: Any, label: str) -> str | None:
    result = _text(value, limit=4_000)
    if result is not None and len(result.encode("utf-8")) > collector.MAX_PUBLIC_TEXT_UTF8_BYTES:
        raise ValueError(f"IDV {label} exceeds the public UTF-8 byte cap")
    return result


def _timestamp(value: Any) -> pd.Timestamp | None:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(stamp):
        return None
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _instant(value: Any) -> str | None:
    stamp = _timestamp(value)
    return stamp.isoformat() if stamp is not None else None


def _required_instant(value: Any, label: str) -> str:
    stamp = _timestamp(value)
    if stamp is None:
        raise ValueError(f"IDV source lacks valid {label}")
    return stamp.isoformat()


def _date(value: Any) -> str | None:
    stamp = _timestamp(value)
    return stamp.date().isoformat() if stamp is not None else None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a source bundle must fail closed
        raise ValueError(f"IDV {label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"IDV {label} must be an object")
    return value


def _load_receipts(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"IDV receipt line {line_number} is not an object")
            rows.append(value)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("IDV collection receipts are unreadable") from exc
    return rows


def _reject_unsafe_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            hash_only = normalized.endswith(("_sha256", "_hash", "_digest"))
            if not hash_only and (
                re.search(r"(?:credential|authorization|password|secret|token|api_?key)", normalized)
                or re.search(r"(?:^|_)(?:headers?|body|payload)(?:_|$)", normalized)
                or re.search(r"(?:^|_)raw_(?:request|response)(?:_|$)", normalized)
            ):
                raise ValueError("IDV source bundle contains a raw or secret-shaped key")
            _reject_unsafe_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_unsafe_keys(child)


def _require_contract(value: Mapping[str, Any], kind: str) -> None:
    if value.get("schema_version") != collector.SCHEMA_VERSION or value.get("contract") != _SOURCE_CONTRACTS[kind]:
        raise ValueError(f"IDV {kind} contract mismatch")


def _receipt_identity(receipt: Mapping[str, Any]) -> str:
    fingerprint = {
        "observed_at": receipt["observed_at"],
        "rail": receipt["rail"],
        "endpoint": receipt["endpoint"],
        "idv_generated_award_id": receipt["idv_generated_award_id"],
        "page": receipt["page"],
        "record_count": receipt["record_count"],
        "reported_child_award_count": receipt["reported_child_award_count"],
        "request_sha256": receipt["request_sha256"],
        "response_sha256": receipt["response_sha256"],
    }
    return "usaspending-idv:" + _canonical_sha256(fingerprint)


def _receipt_index(receipts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    expected_keys = {
        "schema_version", "contract", "receipt_id", "observed_at", "rail", "endpoint",
        "idv_generated_award_id", "page", "record_count", "reported_child_award_count",
        "request_sha256", "response_sha256",
    }
    indexed: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        _require_contract(receipt, "receipt")
        if set(receipt) != expected_keys:
            raise ValueError("IDV collection receipt shape mismatch")
        receipt_id = _required_text(receipt.get("receipt_id"), "receipt ID", limit=400)
        parent = _required_text(receipt.get("idv_generated_award_id"), "receipt IDV generated award ID", limit=1_000)
        page, count, reported = receipt.get("page"), receipt.get("record_count"), receipt.get("reported_child_award_count")
        if (
            receipt_id in indexed or not collector._is_generated_idv(parent)
            or receipt.get("rail") != "idv_activity_page" or receipt.get("endpoint") != collector.IDV_ACTIVITY_URL
            or isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= collector.MAX_PAGES_PER_IDV
            or isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= collector.PAGE_SIZE
            or isinstance(reported, bool) or not isinstance(reported, int) or reported < 0
        ):
            raise ValueError("IDV collection receipt has invalid identity or bounds")
        _required_instant(receipt.get("observed_at"), "receipt observed_at")
        for key in ("request_sha256", "response_sha256"):
            if re.fullmatch(r"[a-f0-9]{64}", _required_text(receipt.get(key), key, limit=64).lower()) is None:
                raise ValueError(f"IDV receipt has invalid {key}")
        expected_request = {"award_id": parent, "page": page, "limit": collector.PAGE_SIZE, "hide_edge_cases": False}
        if receipt["request_sha256"] != _canonical_sha256(expected_request) or receipt_id != _receipt_identity(receipt):
            raise ValueError("IDV collection receipt request hash or identity mismatch")
        indexed[receipt_id] = receipt
    return indexed


def _normalized_prime_map(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("prime award bridge must be a mapping")
    result: dict[str, str] = {}
    for generated_id, award_key in value.items():
        source_id = _required_text(generated_id, "prime bridge source ID", limit=1_000)
        key = _required_text(award_key, "prime bridge award key", limit=1_000)
        if not collector._is_generated_definitive_award(source_id):
            raise ValueError("prime award bridge source must use the CONT_AWD namespace")
        if source_id in result or key in result.values():
            raise ValueError("prime award bridge is ambiguous")
        result[source_id] = key
    return dict(sorted(result.items()))


def _relationship_key(parent: str, child: str, grandchild: bool) -> str:
    return "idvrel:" + _canonical_sha256([parent, child, grandchild])[:32]


def _coverage(
    state: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str, bool], dict[str, Any]]]:
    parents = state.get("parents")
    if not isinstance(parents, list):
        raise ValueError("IDV projection state lacks parent coverage")
    result: dict[str, dict[str, Any]] = {}
    active: dict[tuple[str, str, bool], dict[str, Any]] = {}
    for item in parents:
        if not isinstance(item, Mapping):
            raise ValueError("IDV parent coverage row is invalid")
        parent = _required_text(item.get("idv_generated_award_id"), "parent generated ID", limit=1_000)
        state_name = _required_text(item.get("collection_state"), "collection state", limit=80)
        if parent in result or not collector._is_generated_idv(parent) or state_name not in {"zero", "complete", "high_count_count_only", "run_cap_count_only"}:
            raise ValueError("IDV parent coverage has invalid identity or collection state")
        count = item.get("child_award_count")
        detail_rows, pages = item.get("detail_rows"), item.get("pages_fetched")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (count, detail_rows, pages)):
            raise ValueError("IDV parent coverage has invalid counts")
        count_receipt_id = _required_text(item.get("count_receipt_id"), "count receipt ID", limit=400)
        binding = item.get("count_receipt_binding")
        detail_ids = item.get("detail_receipt_ids")
        active_rows = item.get("active_relationships")
        if (
            item.get("count_verified") is not True or not isinstance(binding, Mapping)
            or binding.get("receipt_id") != count_receipt_id or binding.get("idv_generated_award_id") != parent
            or binding.get("reported_child_award_count") != count or count_receipt_id not in receipts
            or not isinstance(detail_ids, list) or len(set(detail_ids)) != len(detail_ids)
            or any(not isinstance(value, str) or value not in receipts for value in detail_ids)
            or not isinstance(item.get("source_exhausted"), bool)
            or not isinstance(active_rows, list)
            or any(not isinstance(value, Mapping) for value in active_rows)
            or item.get("active_relationships_semantic_sha256")
            != collector.idv_active_relationships_semantic_sha256(active_rows)
        ):
            raise ValueError("IDV parent coverage has invalid receipt bindings")
        count_receipt = receipts[count_receipt_id]
        if count_receipt["idv_generated_award_id"] != parent or count_receipt["reported_child_award_count"] != count:
            raise ValueError("IDV parent coverage count receipt mismatch")
        count_only = state_name in {"high_count_count_only", "run_cap_count_only"}
        parent_active: dict[tuple[str, str, bool], dict[str, Any]] = {}
        for active_row in active_rows:
            if set(active_row) != set(collector.IDV_ACTIVE_RELATIONSHIP_FIELDS):
                raise ValueError("IDV active relationship manifest shape is invalid")
            child = _required_text(active_row.get("child_generated_award_id"), "active child ID", limit=1_000)
            grandchild = active_row.get("grandchild")
            state_sha = _required_text(active_row.get("idv_relationship_state_sha256"), "active state SHA-256", limit=64).lower()
            receipt_id = _required_text(active_row.get("source_receipt_id"), "active receipt ID", limit=400)
            if not isinstance(grandchild, bool):
                raise ValueError("IDV active relationship depth is invalid")
            identity = (parent, child, grandchild)
            receipt = receipts.get(receipt_id)
            if (
                not collector._is_generated_definitive_award(child)
                or identity in parent_active
                or re.fullmatch(r"[a-f0-9]{64}", state_sha) is None
                or receipt_id not in detail_ids
                or receipt is None
                or receipt.get("idv_generated_award_id") != parent
            ):
                raise ValueError("IDV active relationship manifest binding is invalid")
            parent_active[identity] = {
                "idv_relationship_state_sha256": state_sha,
                "source_receipt_id": receipt_id,
            }
        expected_pages = (count + collector.PAGE_SIZE - 1) // collector.PAGE_SIZE
        if state_name == "zero" and not (
            count == detail_rows == pages == 0 and not detail_ids and not parent_active
            and item["source_exhausted"] is True
        ):
            raise ValueError("zero IDV coverage is inconsistent")
        if state_name == "complete" and not (
            1 <= count <= collector.MAX_DETAIL_ROWS_PER_IDV and detail_rows == count and pages == expected_pages
            and len(parent_active) == count
            and len(detail_ids) == expected_pages
            and detail_ids[0] == count_receipt_id and item["source_exhausted"] is True
            and all(receipts[receipt_id]["idv_generated_award_id"] == parent for receipt_id in detail_ids)
            and [receipts[receipt_id]["page"] for receipt_id in detail_ids] == list(range(1, expected_pages + 1))
            and sum(receipts[receipt_id]["record_count"] for receipt_id in detail_ids) == count
        ):
            raise ValueError("complete IDV coverage is inconsistent")
        if count_only and not (
            detail_rows == pages == 0 and not detail_ids and not parent_active
            and item["source_exhausted"] is False
        ):
            raise ValueError("count-only IDV coverage contains detail rows")
        if state_name == "high_count_count_only" and count <= collector.MAX_DETAIL_ROWS_PER_IDV:
            raise ValueError("high-count IDV coverage does not exceed per-IDV cap")
        if state_name == "run_cap_count_only" and not 1 <= count <= collector.MAX_DETAIL_ROWS_PER_IDV:
            raise ValueError("run-cap IDV coverage has invalid count")
        result[parent] = {
            "status": "partial" if count_only else "ok",
            "collection_state": state_name,
            "reported_count": count,
            "count_verified": True,
            "detail_rows": detail_rows,
            "pages_fetched": pages,
            "source_exhausted": item["source_exhausted"],
            "truncated_by_collection_policy": count_only,
            "reason": (
                "Count is verified; detail rows were intentionally withheld by the bounded collection policy."
                if count_only else "Count and detail rows are receipt-bound to this exact source-native IDV."
            ),
        }
        for identity, binding_row in parent_active.items():
            if identity in active:
                raise ValueError("IDV active relationship appears under multiple parents")
            active[identity] = binding_row
    if state.get("selected_idv_count") != len(result):
        raise ValueError("IDV parent coverage selected count mismatch")
    return result, active


def _row_from_source(
    source: Mapping[str, Any], *, receipts: Mapping[str, Mapping[str, Any]], prime_map: Mapping[str, str], collection_scope_ticker: str | None,
) -> dict[str, Any]:
    parent = _required_text(source.get("idv_generated_award_id"), "IDV generated award ID", limit=1_000)
    child = _required_text(source.get("child_generated_award_id"), "child generated award ID", limit=1_000)
    grandchild = source.get("grandchild")
    if not collector._is_generated_idv(parent) or not collector._is_generated_definitive_award(child) or not isinstance(grandchild, bool):
        raise ValueError("IDV source row has invalid natural relationship identity")
    receipt_id = _required_text(source.get("source_receipt_id"), "source receipt ID", limit=400)
    receipt = receipts.get(receipt_id)
    if receipt is None or receipt["idv_generated_award_id"] != parent:
        raise ValueError("IDV source row is not bound to its parent receipt")
    response_sha = _required_text(source.get("source_response_sha256"), "source response SHA-256", limit=64).lower()
    if response_sha != receipt["response_sha256"] or source.get("receipt_verified") is not True:
        raise ValueError("IDV source row receipt binding is invalid")
    if _required_text(source.get("source_url"), "source URL", limit=1_000) != collector.IDV_ACTIVITY_URL:
        raise ValueError("IDV source row does not use the official activity endpoint")
    if _required_text(source.get("idv_relationship_state_sha256"), "state SHA-256", limit=64).lower() != collector._relationship_state_sha256(source):
        raise ValueError("IDV source row state hash mismatch")
    known_at = _required_instant(source.get("known_at"), "known_at")
    if known_at != _required_instant(receipt.get("observed_at"), "receipt observed_at"):
        raise ValueError("IDV source row evidence clock does not match receipt")
    first_seen_at = _required_instant(source.get("first_seen_at"), "first_seen_at")
    if first_seen_at > known_at:
        raise ValueError("IDV source row first_seen_at exceeds known_at")
    return {
        "relationship_key": _relationship_key(parent, child, grandchild),
        "child_award_key": prime_map.get(child),
        "identity": {
            "idv_generated_award_id": parent,
            "child_generated_award_id": child,
            "relationship_depth": "grandchild_award" if grandchild else "direct_child",
            "parent_piid": _public_text(source.get("parent_piid"), "parent PIID"),
            "child_piid": _public_text(source.get("child_piid"), "child PIID"),
        },
        "recipient_name": _public_text(source.get("recipient_name"), "recipient name"),
        "agency": _public_text(source.get("awarding_agency"), "awarding agency"),
        "dates": {
            "start_date": _date(source.get("start_date")),
            "potential_end_date": _date(source.get("potential_end_date")),
            "known_at": known_at,
            "first_seen_at": first_seen_at,
        },
        "amounts": {
            "obligated_amount": _number(source.get("obligated_amount")),
            "awarded_amount": _number(source.get("awarded_amount")),
            "currency": "USD",
            "semantic": "source_reported_idv_activity",
        },
        "source": {"publisher": "USAspending.gov", "activity_url": collector.IDV_ACTIVITY_URL},
        "provenance": {
            "receipt_id": receipt_id,
            "response_sha256": response_sha,
            "source_record_count": receipt["record_count"],
            "known_at": known_at,
            "collection_scope_ticker": collection_scope_ticker,
            "limitations": [
                "Official USAspending IDV activity observation bound to a stored collection receipt.",
                "Collection scope ticker is provenance only and is not issuer attribution.",
                _IDV_LIMITATION,
            ],
        },
    }


def _as_of(value: str | None, candidates: list[Any]) -> str:
    if value is not None:
        parsed = _date(value)
        if parsed is None:
            raise ValueError("IDV dossier as_of must be a date")
        return parsed
    stamps = [stamp for stamp in (_timestamp(item) for item in candidates) if stamp is not None]
    return max(stamps).date().isoformat() if stamps else datetime.now(timezone.utc).date().isoformat()


def _selection_provenance_unavailable() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "selection_source": None,
        "selection_manifest_id": None,
        "reviewed_at": None,
        "selected_parent_count": 0,
        "scope_hashes": {
            "recipient_scope_sha256": None,
            "filters_semantic_sha256": None,
            "reviewed_manifest_sha256": None,
        },
    }


def _optional_sha256(value: Any, label: str) -> str | None:
    if value is None:
        return None
    digest = _required_text(value, label, limit=64).lower()
    if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise ValueError(f"IDV selection manifest has invalid {label}")
    return digest


def _selection_provenance(
    state: Mapping[str, Any],
    parent_ids: list[str],
) -> dict[str, Any]:
    """Publish a bounded receipt for parent selection, never its raw scope."""
    manifest = state.get("selection_manifest")
    if not isinstance(manifest, dict) or not collector._selection_manifest_matches(dict(state), parent_ids):
        raise ValueError("IDV parent selection manifest is not publication eligible")
    source = manifest.get("selection_source")
    if source not in {
        "official_usaspending_idv_discovery",
        "reviewed_source_native_idv_manifest",
    }:
        raise ValueError("IDV parent selection source is unsupported")
    semantic_sha = _optional_sha256(manifest.get("semantic_sha256"), "semantic SHA-256")
    assert semantic_sha is not None
    reviewed_raw = manifest.get("reviewed_at")
    reviewed_at = None if reviewed_raw is None else _required_instant(reviewed_raw, "selection review time")
    recipient_sha = _optional_sha256(manifest.get("recipient_scope_sha256"), "recipient scope SHA-256")
    filters_sha = _optional_sha256(manifest.get("filters_semantic_sha256"), "filter semantics SHA-256")
    reviewed_sha = _optional_sha256(manifest.get("reviewed_manifest_sha256"), "reviewed manifest SHA-256")
    if source == "official_usaspending_idv_discovery":
        if recipient_sha is None or filters_sha is None or reviewed_sha is not None:
            raise ValueError("IDV official discovery selection hashes are inconsistent")
    elif recipient_sha is not None or filters_sha is not None or reviewed_sha is None:
        raise ValueError("IDV reviewed selection hashes are inconsistent")
    return {
        "status": "verified",
        "selection_source": source,
        "selection_manifest_id": "idvsel1-" + semantic_sha[:24],
        "reviewed_at": reviewed_at,
        "selected_parent_count": len(parent_ids),
        "scope_hashes": {
            "recipient_scope_sha256": recipient_sha,
            "filters_semantic_sha256": filters_sha,
            "reviewed_manifest_sha256": reviewed_sha,
        },
    }


def _base_payload(
    *, as_of: str, known_at: str | None, idv_coverage: Mapping[str, Mapping[str, Any]], rows: list[dict[str, Any]],
    source_coverage: dict[str, Any], freshness: dict[str, Any], selection_provenance: dict[str, Any],
) -> dict[str, Any]:
    keys_by_idv: dict[str, list[str]] = {parent: [] for parent in idv_coverage}
    for row in rows:
        keys_by_idv[row["identity"]["idv_generated_award_id"]].append(row["relationship_key"])
    idvs = []
    for parent in sorted(idv_coverage):
        coverage = dict(idv_coverage[parent])
        keys = sorted(keys_by_idv[parent])
        coverage["records_published"] = len(keys)
        idvs.append({"idv_generated_award_id": parent, "coverage": coverage, "relationship_keys": keys, "relationship_count": len(keys)})
    payload: dict[str, Any] = {
        "contract": IDV_DOSSIER_CONTRACT,
        "schema_version": IDV_DOSSIER_SCHEMA_VERSION,
        "content_id": "",
        "as_of": as_of,
        "known_at": known_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": AUTHORITY.copy(),
        "source_coverage": source_coverage,
        "freshness": freshness,
        "selection_provenance": selection_provenance,
        "limitations": [
            "IDV parents remain source-native provenance entities; this artifact does not create a definitive-award dossier for an IDV.",
            "A child award key is present only when its exact generated natural ID matches an existing definitive-award dossier.",
            _IDV_LIMITATION,
        ],
        "idvs": idvs,
        "relationships": rows,
    }
    content_id = idv_dossier_content_id(payload)
    if content_id is None:
        raise ValueError("IDV dossier cannot be canonically represented")
    payload["content_id"] = content_id
    if not is_valid_idv_dossier_payload(payload):
        raise ValueError("IDV dossier failed strict public validation")
    return payload


def build_idv_dossier_payload(
    root: Path | None = None,
    *,
    prime_award_key_by_generated_id: Mapping[str, str] | None = None,
    collection_scope_ticker: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Project one complete, receipt-bound IDV source generation without network access."""
    data_dir = _root(root) / "data" / "government_revenue"
    paths = [data_dir / name for name in _SOURCE_FILES]
    present = [path.exists() for path in paths]
    if not any(present):
        reason = "The receipt-bound USAspending IDV source bundle is not initialized."
        return _base_payload(
            as_of=_as_of(as_of, []), known_at=None, idv_coverage={}, rows=[],
            source_coverage={"status": "unavailable", "records_loaded": 0, "records_published": 0, "records_dropped": 0, "configured_cap": MAX_IDV_RECORDS, "truncated_by_artifact_cap": False, "bounded_collection": None, "reason": reason},
            freshness={"status": "unavailable", "observed_at": None, "known_at": None, "reason": reason},
            selection_provenance=_selection_provenance_unavailable(),
        )
    if not all(present):
        raise ValueError("IDV source bundle is partial; all four artifacts are required")
    prime_map = _normalized_prime_map(prime_award_key_by_generated_id)
    ticker = _text(collection_scope_ticker, limit=32)
    snapshot_path, receipts_path, state_path, status_path = paths
    try:
        frame = pd.read_parquet(snapshot_path)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("IDV snapshot parquet is unreadable") from exc
    state, status, receipt_rows = _load_json(state_path, "projection state"), _load_json(status_path, "ingest status"), _load_receipts(receipts_path)
    for value in (state, status, receipt_rows):
        _reject_unsafe_keys(value)
    _require_contract(state, "state")
    _require_contract(status, "status")
    if list(frame.columns) != collector.IDV_RELATIONSHIP_SNAPSHOT_COLUMNS or not collector.idv_projection_generation_matches(state, frame):
        raise ValueError("IDV snapshot does not match collector activation generation")
    generation = _required_text(state.get("projection_generation_id"), "projection generation", limit=200)
    shared_generation_fields = (
        "run_id",
        "observed_at",
        "last_successful_observed_at",
        "selection_source",
        "selection_manifest_semantic_sha256",
        "bounds",
    )
    if (
        status.get("projection_generation_id") != generation or state.get("activation_state") != "live"
        or state.get("bounded_collection_complete") is not True or state.get("projection_eligible") is not True
        or status.get("status") != "ok" or status.get("partial") is not False or status.get("collection_complete") is not True
        or status.get("projection_eligible") is not True or status.get("bounded") is not True or status.get("source_only") is not True
        or status.get("daily_lane") is not True or status.get("errors") != [] or state.get("public_downstream_row_cap") != MAX_IDV_RECORDS
        or any(status.get(field) != state.get(field) for field in shared_generation_fields)
        or status.get("idvs_selected") != state.get("selected_idv_count")
        or status.get("detail_rows_seen") != state.get("detail_rows_this_run")
        or status.get("snapshot_versions_total") != len(frame)
    ):
        raise ValueError("IDV source generation is not publication eligible")
    receipts = _receipt_index(receipt_rows)
    coverage, active_relationships = _coverage(state, receipts)
    selection_provenance = _selection_provenance(state, list(coverage))
    latest: dict[tuple[str, str, bool], tuple[str, str, dict[str, Any]]] = {}
    for source in frame.to_dict(orient="records"):
        row = _row_from_source(source, receipts=receipts, prime_map=prime_map, collection_scope_ticker=ticker)
        parent = row["identity"]["idv_generated_award_id"]
        identity = (parent, row["identity"]["child_generated_award_id"], row["identity"]["relationship_depth"] == "grandchild_award")
        state_hash = _required_text(source.get("idv_relationship_state_sha256"), "state SHA-256", limit=64).lower()
        previous = latest.get(identity)
        candidate = (row["dates"]["known_at"], state_hash, row)
        if previous is not None and previous[0] == candidate[0] and previous[1] != candidate[1]:
            raise ValueError("IDV source has conflicting states at the same evidence clock")
        if previous is None or candidate[0] > previous[0] or (candidate[0] == previous[0] and candidate[1] == previous[1] and row["provenance"]["receipt_id"] < previous[2]["provenance"]["receipt_id"]):
            latest[identity] = candidate
    rows: list[dict[str, Any]] = []
    active_observed_at = _required_instant(state.get("observed_at"), "active observed_at")
    for identity, binding in sorted(active_relationships.items()):
        candidate = latest.get(identity)
        if candidate is None or candidate[1] != binding["idv_relationship_state_sha256"]:
            raise ValueError("IDV active relationship manifest does not match accrued semantic history")
        current_receipt = receipts[binding["source_receipt_id"]]
        if _required_instant(current_receipt.get("observed_at"), "active receipt observed_at") != active_observed_at:
            raise ValueError("IDV active relationship receipt is outside the active evidence clock")
        historical = candidate[2]
        row = {
            **historical,
            "dates": {**historical["dates"], "known_at": active_observed_at},
            "provenance": {
                **historical["provenance"],
                "receipt_id": binding["source_receipt_id"],
                "response_sha256": current_receipt["response_sha256"],
                "source_record_count": current_receipt["record_count"],
                "known_at": active_observed_at,
            },
        }
        rows.append(row)
    rows.sort(key=lambda row: (row["dates"]["start_date"] or "", row["dates"]["known_at"], row["relationship_key"]), reverse=True)
    loaded = len(rows)
    if loaded > MAX_IDV_RECORDS:
        raise ValueError("IDV active relationship set exceeds the public artifact cap")
    dropped = 0
    observed_at = _instant(status.get("observed_at"))
    known_candidates = [observed_at, *[row["dates"]["known_at"] for row in rows]]
    known_stamps = [stamp for stamp in (_timestamp(item) for item in known_candidates) if stamp is not None]
    known_at = max(known_stamps).isoformat() if known_stamps else None
    source_status = "ok"
    reason = "Published all receipt-bound IDV relationship rows in the bounded collector generation."
    observed_stamp = _timestamp(observed_at)
    now = pd.Timestamp(datetime.now(timezone.utc))
    if observed_stamp is None:
        raise ValueError("IDV active generation lacks an observed clock")
    if observed_stamp > now + pd.Timedelta(minutes=15):
        raise ValueError("IDV active generation observed clock is implausibly in the future")
    stale = now - observed_stamp > pd.Timedelta(days=FRESHNESS_MAX_AGE_DAYS)
    freshness_status = "stale" if stale else source_status
    freshness_reason = (
        f"Last complete IDV observation is older than the {FRESHNESS_MAX_AGE_DAYS}-day freshness window."
        if stale else reason
    )
    return _base_payload(
        as_of=_as_of(as_of, [observed_at, *[row["dates"]["start_date"] for row in rows]]), known_at=known_at,
        idv_coverage=coverage, rows=rows,
        source_coverage={"status": source_status, "records_loaded": loaded, "records_published": len(rows), "records_dropped": dropped, "configured_cap": MAX_IDV_RECORDS, "truncated_by_artifact_cap": bool(dropped), "bounded_collection": True, "reason": reason},
        freshness={"status": freshness_status, "observed_at": observed_at, "known_at": known_at, "reason": freshness_reason},
        selection_provenance=selection_provenance,
    )


@lru_cache(maxsize=1)
def _validator() -> Any:
    from jsonschema import Draft202012Validator, FormatChecker

    path = Path(__file__).resolve().parents[2] / "contracts" / "government_revenue" / "government_idv_dossiers.v1.schema.json"
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")), format_checker=FormatChecker())


def is_valid_idv_dossier_payload(value: Any) -> bool:
    """Validate schema, immutable content ID, and source-native envelopes."""
    try:
        if not isinstance(value, dict) or any(_validator().iter_errors(value)) or idv_dossier_content_id(value) != value.get("content_id"):
            return False
        idvs, rows = value["idvs"], value["relationships"]
        source_coverage = value["source_coverage"]
        freshness = value["freshness"]
        selection = value["selection_provenance"]
        by_idv = {item["idv_generated_award_id"]: item for item in idvs if isinstance(item, dict)}
        by_key = {item["relationship_key"]: item for item in rows if isinstance(item, dict)}
        if len(by_idv) != len(idvs) or len(by_key) != len(rows):
            return False
        unavailable_selection = {
            "status": "unavailable",
            "selection_source": None,
            "selection_manifest_id": None,
            "reviewed_at": None,
            "selected_parent_count": 0,
            "scope_hashes": {
                "recipient_scope_sha256": None,
                "filters_semantic_sha256": None,
                "reviewed_manifest_sha256": None,
            },
        }
        if selection.get("status") == "unavailable":
            if (
                selection != unavailable_selection
                or source_coverage.get("status") != "unavailable"
                or freshness.get("status") != "unavailable"
                or idvs or rows
                or source_coverage.get("records_loaded") != 0
                or source_coverage.get("records_published") != 0
                or source_coverage.get("records_dropped") != 0
                or source_coverage.get("truncated_by_artifact_cap") is not False
                or source_coverage.get("bounded_collection") is not None
            ):
                return False
        else:
            hashes = selection.get("scope_hashes", {})
            source = selection.get("selection_source")
            if (
                selection.get("status") != "verified"
                or selection.get("selection_manifest_id") is None
                or not idvs
                or selection.get("selected_parent_count") != len(idvs)
                or source_coverage.get("status") != "ok"
                or freshness.get("status") not in {"ok", "stale"}
                or source_coverage.get("records_loaded") != len(rows)
                or source_coverage.get("records_published") != len(rows)
                or source_coverage.get("records_dropped") != 0
                or source_coverage.get("truncated_by_artifact_cap") is not False
                or source_coverage.get("bounded_collection") is not True
            ):
                return False
            if source == "official_usaspending_idv_discovery":
                if hashes.get("recipient_scope_sha256") is None or hashes.get("filters_semantic_sha256") is None or hashes.get("reviewed_manifest_sha256") is not None:
                    return False
            elif source == "reviewed_source_native_idv_manifest":
                if hashes.get("recipient_scope_sha256") is not None or hashes.get("filters_semantic_sha256") is not None or hashes.get("reviewed_manifest_sha256") is None:
                    return False
            else:
                return False
        expected: dict[str, list[str]] = {key: [] for key in by_idv}
        seen: set[tuple[str, str, str]] = set()
        for key, row in by_key.items():
            identity = row.get("identity", {})
            parent, child, depth = identity.get("idv_generated_award_id"), identity.get("child_generated_award_id"), identity.get("relationship_depth")
            triple = (parent, child, depth)
            if parent not in by_idv or triple in seen or key != _relationship_key(parent, child, depth == "grandchild_award"):
                return False
            seen.add(triple)
            expected[parent].append(key)
        for parent, envelope in by_idv.items():
            keys = sorted(expected[parent])
            coverage = envelope.get("coverage", {})
            state = coverage.get("collection_state")
            reported = coverage.get("reported_count")
            detail_rows = coverage.get("detail_rows")
            pages = coverage.get("pages_fetched")
            relationship_count = len(keys)
            if envelope.get("relationship_keys") != keys or envelope.get("relationship_count") != relationship_count or coverage.get("records_published") != relationship_count:
                return False
            if state == "zero":
                if not (
                    coverage.get("status") == "ok"
                    and reported == detail_rows == pages == relationship_count == 0
                    and coverage.get("count_verified") is True
                    and coverage.get("source_exhausted") is True
                    and coverage.get("truncated_by_collection_policy") is False
                ):
                    return False
            elif state == "complete":
                expected_pages = (reported + collector.PAGE_SIZE - 1) // collector.PAGE_SIZE
                if not (
                    coverage.get("status") == "ok"
                    and 1 <= reported <= collector.MAX_DETAIL_ROWS_PER_IDV
                    and detail_rows == reported == relationship_count
                    and pages == expected_pages
                    and coverage.get("count_verified") is True
                    and coverage.get("source_exhausted") is True
                    and coverage.get("truncated_by_collection_policy") is False
                ):
                    return False
            elif state in {"high_count_count_only", "run_cap_count_only"}:
                valid_count = (
                    reported > collector.MAX_DETAIL_ROWS_PER_IDV
                    if state == "high_count_count_only"
                    else 1 <= reported <= collector.MAX_DETAIL_ROWS_PER_IDV
                )
                if not (
                    coverage.get("status") == "partial"
                    and valid_count
                    and detail_rows == pages == relationship_count == 0
                    and coverage.get("count_verified") is True
                    and coverage.get("source_exhausted") is False
                    and coverage.get("truncated_by_collection_policy") is True
                ):
                    return False
            else:
                return False
        return True
    except Exception:  # noqa: BLE001 - public validation must fail closed
        return False
