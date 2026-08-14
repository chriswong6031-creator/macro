"""Immutable, resumable ticker-by-date-range shards for the full-A TuShare spine.

This module owns only source acquisition evidence.  It never authorizes a vendor
call and never promotes a strategy.  The parent collector supplies an already
verified authorization grant, the exact endpoint fields, and an injected query.

One campaign is frozen to an endpoint, reference generation, market-session
range, and complete set of vendor query identities.  Leaf progress is persisted
as one atomic JSON file per range, rather than rewriting the collector's central
state for every ticker.  Every HTTP attempt receives an immutable receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd


CAMPAIGN_SCHEMA_VERSION = "cn_tushare_range_campaign.v1"
LEAF_STATE_SCHEMA_VERSION = "cn_tushare_range_leaf_state.v1"
ATTEMPT_RECEIPT_SCHEMA_VERSION = "cn_tushare_range_attempt_receipt.v1"
CAMPAIGN_RECEIPT_SCHEMA_VERSION = "cn_tushare_range_campaign_receipt.v1"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TUSHARE_CODE = re.compile(r"^\d{6}\.(?:SH|SS|SZ|BJ)$", re.IGNORECASE)


class RangeShardError(RuntimeError):
    """A campaign, request, or artifact failed its fail-closed contract."""


@dataclass(frozen=True)
class RangeLeaf:
    leaf_id: str
    campaign_id: str
    endpoint: str
    canonical_ticker: str
    source_ts_code: str
    alias_kind: str
    start_date: str
    end_date: str
    session_count: int
    session_sha256: str
    fields: tuple[str, ...]
    source_row_cap: int

    @property
    def unit(self) -> str:
        return f"range:{self.leaf_id}"

    @property
    def params(self) -> dict[str, str]:
        return {
            "ts_code": self.source_ts_code,
            "start_date": self.start_date.replace("-", ""),
            "end_date": self.end_date.replace("-", ""),
        }


@dataclass(frozen=True)
class CampaignVerification:
    campaign_id: str
    complete: bool
    resolved_frame: pd.DataFrame
    duplicate_alias_rows: pd.DataFrame
    conflicting_alias_rows: pd.DataFrame
    day_receipts: Mapping[str, Mapping[str, Any]]
    receipt: Mapping[str, Any] | None


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        return None if pd.isna(value) else value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _atomic_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_bytes(path, _canonical_json_bytes(dict(payload)) + b"\n")


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".parquet", dir=path.parent,
    )
    os.close(descriptor)
    try:
        frame.to_parquet(temporary, index=False)
        with open(temporary, "rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _normal_source_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.endswith(".SS"):
        text = text[:-3] + ".SH"
    if not _TUSHARE_CODE.fullmatch(text):
        raise RangeShardError(f"invalid TuShare query identity: {value!r}")
    return text


def _iso_date(value: Any) -> str:
    text = str(value or "").strip()
    try:
        parsed = pd.Timestamp(text)
    except (TypeError, ValueError) as exc:
        raise RangeShardError(f"invalid trade date: {value!r}") from exc
    if pd.isna(parsed):
        raise RangeShardError(f"invalid trade date: {value!r}")
    return parsed.date().isoformat()


def frame_semantic_sha256(frame: pd.DataFrame) -> str:
    """Order-insensitive semantic hash over every observed response row."""
    rows = [
        _canonical_json_bytes({
            str(key): _json_safe(value) for key, value in sorted(item.items())
        })
        for item in frame.to_dict(orient="records")
    ]
    return _sha256_bytes(b"\n".join(sorted(rows)))


def _campaign_dir(store: Path, campaign_id: str) -> Path:
    if not _HEX64.fullmatch(str(campaign_id)):
        raise RangeShardError("invalid range campaign id")
    return Path(store) / "range_campaigns" / campaign_id


def _plan_path(store: Path, campaign_id: str) -> Path:
    return _campaign_dir(store, campaign_id) / "plan.json"


def _leaf_state_path(store: Path, leaf_id: str, campaign_id: str) -> Path:
    if not _HEX64.fullmatch(leaf_id):
        raise RangeShardError("invalid range leaf id")
    return _campaign_dir(store, campaign_id) / "leaves" / leaf_id[:2] / f"{leaf_id}.json"


def _leaf_artifact_path(store: Path, leaf: RangeLeaf) -> Path:
    return (
        Path(store) / "source_range_shards" / leaf.endpoint / leaf.campaign_id
        / leaf.leaf_id[:2] / f"{leaf.leaf_id}.parquet"
    )


def _attempt_dir(store: Path, leaf: RangeLeaf) -> Path:
    return Path(store) / "receipts" / "requests" / leaf.endpoint / leaf.unit


def _relative(path: Path, store: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(Path(store).resolve()).as_posix()
    except ValueError as exc:
        raise RangeShardError("range artifact escaped its private store") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RangeShardError(f"unreadable range artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise RangeShardError(f"range artifact is not an object: {path}")
    return payload


def ensure_campaign(
    store: Path,
    *,
    endpoint: str,
    fields: Sequence[str],
    source_row_cap: int,
    sessions: Sequence[str],
    query_identities: Iterable[Mapping[str, Any]],
    reference_generation_id: str,
    reference_generation_semantic_sha256: str,
    universe_witness_sha256: str,
) -> dict[str, Any]:
    """Create or verify one immutable endpoint/range campaign plan."""
    canonical_sessions = sorted({_iso_date(value) for value in sessions})
    if not canonical_sessions:
        raise RangeShardError("range campaign requires at least one market session")
    if not isinstance(source_row_cap, int) or source_row_cap < 2:
        raise RangeShardError("range campaign source cap must be at least two")
    canonical_fields = [str(value) for value in fields]
    if not canonical_fields or len(set(canonical_fields)) != len(canonical_fields):
        raise RangeShardError("range campaign fields must be unique and non-empty")
    identities: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in query_identities:
        canonical_ticker = str(raw.get("canonical_ticker") or "").strip().upper()
        source_ts_code = _normal_source_code(raw.get("source_ts_code"))
        alias_kind = str(raw.get("alias_kind") or "canonical")
        if not canonical_ticker or (canonical_ticker, source_ts_code) in seen:
            if (canonical_ticker, source_ts_code) in seen:
                continue
            raise RangeShardError("range campaign contains an empty canonical ticker")
        seen.add((canonical_ticker, source_ts_code))
        identities.append({
            "canonical_ticker": canonical_ticker,
            "source_ts_code": source_ts_code,
            "alias_kind": alias_kind,
        })
    identities.sort(key=lambda item: (
        item["canonical_ticker"], item["alias_kind"] != "canonical", item["source_ts_code"],
    ))
    if not identities:
        raise RangeShardError("range campaign requires at least one query identity")
    for digest in (reference_generation_semantic_sha256, universe_witness_sha256):
        if not _HEX64.fullmatch(str(digest)):
            raise RangeShardError("range campaign witness hash is invalid")
    contract: dict[str, Any] = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "endpoint": str(endpoint),
        "fields": canonical_fields,
        "source_row_cap": source_row_cap,
        "acceptance_rule": "response_rows_strictly_below_documented_cap",
        "split_rule": "deterministic_contiguous_market_session_chunks_cap_minus_one_v1",
        "start_date": canonical_sessions[0],
        "end_date": canonical_sessions[-1],
        "sessions": canonical_sessions,
        "session_count": len(canonical_sessions),
        "session_sha256": _sha256_bytes("\n".join(canonical_sessions).encode("ascii")),
        "query_identities": identities,
        "query_identity_count": len(identities),
        "query_identity_sha256": _sha256_bytes(_canonical_json_bytes(identities)),
        "reference_generation_id": str(reference_generation_id),
        "reference_generation_semantic_sha256": reference_generation_semantic_sha256,
        "universe_witness_sha256": universe_witness_sha256,
    }
    campaign_id = _sha256_bytes(_canonical_json_bytes(contract))
    plan = {**contract, "campaign_id": campaign_id}
    path = _plan_path(store, campaign_id)
    if path.exists():
        if _read_json(path) != plan:
            raise RangeShardError("existing range campaign plan is not immutable")
    else:
        _atomic_json(path, plan)
    return plan


def load_plan(store: Path, campaign_id: str) -> dict[str, Any]:
    path = _plan_path(store, campaign_id)
    plan = _read_json(path)
    if plan.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        raise RangeShardError("unsupported range campaign schema")
    recorded_id = plan.pop("campaign_id", None)
    observed_id = _sha256_bytes(_canonical_json_bytes(plan))
    plan["campaign_id"] = recorded_id
    if recorded_id != campaign_id or observed_id != campaign_id:
        raise RangeShardError("range campaign plan hash does not bind its contents")
    if plan.get("sessions") != sorted(set(plan.get("sessions", []))):
        raise RangeShardError("range campaign sessions are not canonical")
    if plan.get("session_count") != len(plan.get("sessions", [])):
        raise RangeShardError("range campaign session count disagrees")
    if plan.get("query_identity_count") != len(plan.get("query_identities", [])):
        raise RangeShardError("range campaign query identity count disagrees")
    return plan


def planned_leaves(plan: Mapping[str, Any]) -> list[RangeLeaf]:
    """Return deterministic cap-safe leaves; no source response controls splitting."""
    sessions = list(plan["sessions"])
    cap = int(plan["source_row_cap"])
    width = cap - 1
    leaves: list[RangeLeaf] = []
    for identity in plan["query_identities"]:
        for offset in range(0, len(sessions), width):
            segment = sessions[offset:offset + width]
            contract = {
                "campaign_id": plan["campaign_id"],
                "endpoint": plan["endpoint"],
                "canonical_ticker": identity["canonical_ticker"],
                "source_ts_code": identity["source_ts_code"],
                "alias_kind": identity["alias_kind"],
                "start_date": segment[0],
                "end_date": segment[-1],
                "session_count": len(segment),
                "session_sha256": _sha256_bytes("\n".join(segment).encode("ascii")),
                "fields": list(plan["fields"]),
                "source_row_cap": cap,
            }
            leaf_id = _sha256_bytes(_canonical_json_bytes(contract))
            leaves.append(RangeLeaf(leaf_id=leaf_id, **{
                **contract,
                "fields": tuple(contract["fields"]),
            }))
    return leaves


def _leaf_contract(leaf: RangeLeaf) -> dict[str, Any]:
    return {
        "campaign_id": leaf.campaign_id,
        "endpoint": leaf.endpoint,
        "canonical_ticker": leaf.canonical_ticker,
        "source_ts_code": leaf.source_ts_code,
        "alias_kind": leaf.alias_kind,
        "start_date": leaf.start_date,
        "end_date": leaf.end_date,
        "session_count": leaf.session_count,
        "session_sha256": leaf.session_sha256,
        "fields": list(leaf.fields),
        "source_row_cap": leaf.source_row_cap,
    }


def _request_contract(leaf: RangeLeaf) -> dict[str, Any]:
    return {
        "endpoint": leaf.endpoint,
        "fields": list(leaf.fields),
        "params": leaf.params,
        "unit": leaf.unit,
    }


def _leaf_sessions(plan: Mapping[str, Any], leaf: RangeLeaf) -> tuple[str, ...]:
    sessions = tuple(
        value for value in plan["sessions"]
        if leaf.start_date <= value <= leaf.end_date
    )
    if (
        len(sessions) != leaf.session_count
        or _sha256_bytes("\n".join(sessions).encode("ascii")) != leaf.session_sha256
    ):
        raise RangeShardError("range leaf session witness disagrees with its campaign")
    return sessions


def _validate_response(
    leaf: RangeLeaf, frame: pd.DataFrame, *, allowed_sessions: Sequence[str],
) -> None:
    if list(frame.columns) != list(leaf.fields):
        raise RangeShardError("range response columns do not exactly match requested fields")
    sessions = None
    if not frame.empty:
        if not {"ts_code", "trade_date"}.issubset(frame.columns):
            raise RangeShardError("range response lacks ticker/date binding fields")
        observed_codes = {_normal_source_code(value) for value in frame["ts_code"]}
        if observed_codes != {leaf.source_ts_code}:
            raise RangeShardError("range response crossed the requested ts_code")
        observed_dates = [_iso_date(value) for value in frame["trade_date"]]
        if any(value not in set(allowed_sessions) for value in observed_dates):
            raise RangeShardError("range response crossed the requested date bounds")
        if len(set(zip(observed_dates, frame["ts_code"].map(_normal_source_code)))) != len(frame):
            raise RangeShardError("range response duplicated ticker/date keys")
        sessions = observed_dates
    if len(frame) > leaf.session_count:
        raise RangeShardError("range response exceeded one row per requested market session")
    if sessions is not None and len(set(sessions)) != len(sessions):
        raise RangeShardError("range response emitted multiple rows for one market session")


def _attempt_receipt(
    leaf: RangeLeaf,
    *,
    attempt_number: int,
    observed_at: str,
    frame: pd.DataFrame | None,
    response_status: str,
) -> tuple[dict[str, Any], str]:
    request_contract = _request_contract(leaf)
    contract_hash = _sha256_bytes(_canonical_json_bytes(request_contract))
    attempt_contract = {
        "request_contract_sha256": contract_hash,
        "attempt_number": attempt_number,
        "observed_at": observed_at,
    }
    attempt_id = _sha256_bytes(_canonical_json_bytes(attempt_contract))
    receipt = {
        "schema_version": ATTEMPT_RECEIPT_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "attempt_number": attempt_number,
        "request_id": attempt_id,
        "endpoint": leaf.endpoint,
        "unit": leaf.unit,
        "fields": list(leaf.fields),
        "params": leaf.params,
        "request_contract_sha256": contract_hash,
        "observed_at": observed_at,
        "response_status": response_status,
        "response_row_count": len(frame) if frame is not None else 0,
        "response_columns": list(frame.columns) if frame is not None else [],
        "response_semantic_sha256": (
            frame_semantic_sha256(frame) if frame is not None else None
        ),
        "receipt_role": (
            "discarded_non_authoritative_cap_probe"
            if response_status == "non_authoritative_cap_probe" else None
        ),
        "discarded_probe_row_count": (
            len(frame) if frame is not None and response_status == "non_authoritative_cap_probe"
            else None
        ),
    }
    return receipt, attempt_id


def record_attempt(
    store: Path,
    plan: Mapping[str, Any],
    leaf: RangeLeaf,
    *,
    frame: pd.DataFrame | None,
    observed_at: str,
) -> dict[str, Any]:
    """Persist one immutable attempt and the leaf commit marker, terminal last."""
    if leaf.campaign_id != plan.get("campaign_id"):
        raise RangeShardError("range leaf is not owned by this campaign")
    expected_leaf_id = _sha256_bytes(_canonical_json_bytes(_leaf_contract(leaf)))
    if expected_leaf_id != leaf.leaf_id:
        raise RangeShardError("range leaf id does not bind its contract")
    state_path = _leaf_state_path(store, leaf.leaf_id, leaf.campaign_id)
    previous = _read_json(state_path) if state_path.exists() else None
    if previous:
        _validate_leaf_state_header(previous, plan, leaf)
        _validate_attempt_ledger(store, leaf, previous)
        if previous.get("status") == "terminal":
            verify_leaf(store, plan, leaf)
            return previous
        if previous.get("status") == "fatal":
            raise RangeShardError("fatal range leaf cannot be retried in place")
    attempts = list(previous.get("attempts", [])) if previous else []
    attempt_number = len(attempts) + 1
    response_status = "unavailable"
    validation_error: RangeShardError | None = None
    if frame is not None:
        try:
            _validate_response(leaf, frame, allowed_sessions=_leaf_sessions(plan, leaf))
        except RangeShardError as exc:
            response_status = "rejected_contract"
            validation_error = exc
        else:
            if len(frame) >= leaf.source_row_cap:
                response_status = "non_authoritative_cap_probe"
                validation_error = RangeShardError(
                    "cap reached inside a cap-safe ticker range leaf"
                )
            else:
                response_status = "accepted_empty" if frame.empty else "accepted"
    receipt_frame = frame
    if frame is not None and validation_error is None:
        receipt_frame = frame.copy()
        if not receipt_frame.empty:
            receipt_frame["trade_date"] = receipt_frame["trade_date"].map(_iso_date)
            receipt_frame["ts_code"] = receipt_frame["ts_code"].map(_normal_source_code)
            receipt_frame = receipt_frame.sort_values(
                ["trade_date", "ts_code"], kind="stable",
            ).reset_index(drop=True)
    receipt, attempt_id = _attempt_receipt(
        leaf, attempt_number=attempt_number, observed_at=observed_at,
        frame=receipt_frame, response_status=response_status,
    )
    receipt_path = _attempt_dir(store, leaf) / f"{attempt_number:06d}-{attempt_id}.json"
    if receipt_path.exists():
        if _read_json(receipt_path) != receipt:
            raise RangeShardError("range attempt receipt path collision")
    else:
        _atomic_json(receipt_path, receipt)
    attempt_ref = {
        "attempt_id": attempt_id,
        "attempt_number": attempt_number,
        "path": _relative(receipt_path, store),
        "sha256": _file_sha256(receipt_path),
        "response_status": response_status,
    }
    attempts.append(attempt_ref)
    state: dict[str, Any] = {
        "schema_version": LEAF_STATE_SCHEMA_VERSION,
        "leaf_id": leaf.leaf_id,
        "campaign_id": leaf.campaign_id,
        "leaf_contract": _leaf_contract(leaf),
        "status": "retryable" if frame is None else (
            "fatal" if validation_error is not None else "terminal"
        ),
        "attempts": attempts,
        "terminal_attempt_id": attempt_id if validation_error is None and frame is not None else None,
        "reason": (
            "vendor_unavailable_or_unlicensed" if frame is None
            else (type(validation_error).__name__ if validation_error else None)
        ),
    }
    if frame is not None and validation_error is None:
        artifact_path = _leaf_artifact_path(store, leaf)
        if frame.empty:
            artifact = {
                "path": None,
                "byte_sha256": None,
                "row_count": 0,
                "semantic_sha256": frame_semantic_sha256(frame),
                "columns": list(frame.columns),
            }
        else:
            assert receipt_frame is not None
            canonical = receipt_frame
            _atomic_parquet(artifact_path, canonical)
            artifact = {
                "path": _relative(artifact_path, store),
                "byte_sha256": _file_sha256(artifact_path),
                "row_count": len(canonical),
                "semantic_sha256": frame_semantic_sha256(canonical),
                "columns": list(canonical.columns),
            }
        state["artifact"] = artifact
    _atomic_json(state_path, state)
    if validation_error is not None:
        raise validation_error
    return state


def _validate_attempt_receipt(store: Path, leaf: RangeLeaf, ref: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(store) / str(ref.get("path") or "")
    expected_parent = _attempt_dir(store, leaf).resolve(strict=False)
    try:
        path.resolve(strict=False).relative_to(expected_parent)
    except ValueError as exc:
        raise RangeShardError("range attempt receipt escaped its canonical leaf directory") from exc
    if not path.is_file() or _file_sha256(path) != ref.get("sha256"):
        raise RangeShardError("range attempt receipt is missing or modified")
    receipt = _read_json(path)
    if receipt.get("schema_version") != ATTEMPT_RECEIPT_SCHEMA_VERSION:
        raise RangeShardError("range attempt receipt schema is invalid")
    request_contract = _request_contract(leaf)
    expected_contract_hash = _sha256_bytes(_canonical_json_bytes(request_contract))
    attempt_number = ref.get("attempt_number")
    attempt_id = ref.get("attempt_id")
    canonical_path = _attempt_dir(store, leaf) / f"{attempt_number:06d}-{attempt_id}.json"
    if path.resolve(strict=False) != canonical_path.resolve(strict=False):
        raise RangeShardError("range attempt receipt is not at its canonical path")
    for key, expected in (
        ("endpoint", leaf.endpoint), ("unit", leaf.unit),
        ("fields", list(leaf.fields)), ("params", leaf.params),
        ("request_contract_sha256", expected_contract_hash),
        ("attempt_id", attempt_id),
        ("attempt_number", attempt_number),
        ("response_status", ref.get("response_status")),
    ):
        if receipt.get(key) != expected:
            raise RangeShardError(f"range attempt receipt does not bind {key}")
    expected_attempt_id = _sha256_bytes(_canonical_json_bytes({
        "request_contract_sha256": expected_contract_hash,
        "attempt_number": attempt_number,
        "observed_at": receipt.get("observed_at"),
    }))
    if attempt_id != expected_attempt_id or receipt.get("request_id") != attempt_id:
        raise RangeShardError("range attempt id does not bind request, ordinal, and time")
    status = receipt.get("response_status")
    row_count = receipt.get("response_row_count")
    columns = receipt.get("response_columns")
    semantic = receipt.get("response_semantic_sha256")
    if (
        status not in {
            "accepted", "accepted_empty", "unavailable",
            "rejected_contract", "non_authoritative_cap_probe",
        }
        or not isinstance(row_count, int)
        or row_count < 0
        or not isinstance(columns, list)
    ):
        raise RangeShardError("range attempt response evidence is malformed")
    if status == "unavailable":
        if row_count != 0 or columns or semantic is not None:
            raise RangeShardError("unavailable range attempt carries false response evidence")
    elif not _HEX64.fullmatch(str(semantic or "")):
        raise RangeShardError("range attempt response semantic hash is invalid")
    if status == "non_authoritative_cap_probe":
        if (
            row_count < leaf.source_row_cap
            or receipt.get("receipt_role") != "discarded_non_authoritative_cap_probe"
            or receipt.get("discarded_probe_row_count") != row_count
        ):
            raise RangeShardError("range cap probe receipt is not explicitly discarded")
    elif receipt.get("receipt_role") is not None or receipt.get(
        "discarded_probe_row_count"
    ) is not None:
        raise RangeShardError("authoritative range attempt carries cap-probe metadata")
    return receipt


def _validate_leaf_state_header(
    state: Mapping[str, Any], plan: Mapping[str, Any], leaf: RangeLeaf,
) -> None:
    if (
        state.get("schema_version") != LEAF_STATE_SCHEMA_VERSION
        or state.get("leaf_id") != leaf.leaf_id
        or state.get("campaign_id") != plan.get("campaign_id")
        or state.get("leaf_contract") != _leaf_contract(leaf)
        or state.get("status") not in {"retryable", "fatal", "terminal"}
    ):
        raise RangeShardError("range leaf state header is invalid")


def _validate_attempt_ledger(
    store: Path, leaf: RangeLeaf, state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    attempts = state.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise RangeShardError("range leaf has no immutable attempt evidence")
    if [item.get("attempt_number") for item in attempts if isinstance(item, Mapping)] != list(
        range(1, len(attempts) + 1)
    ):
        raise RangeShardError("range attempt ordinals are not contiguous")
    decoded = [_validate_attempt_receipt(store, leaf, ref) for ref in attempts]
    referenced = {
        (Path(store) / str(ref["path"])).resolve(strict=False)
        for ref in attempts
    }
    observed = {
        path.resolve(strict=False) for path in _attempt_dir(store, leaf).glob("*.json")
    }
    if observed != referenced:
        raise RangeShardError("range attempt directory and leaf ledger disagree")
    statuses = [item["response_status"] for item in decoded]
    state_status = state.get("status")
    terminal_id = state.get("terminal_attempt_id")
    if any(status != "unavailable" for status in statuses[:-1]):
        raise RangeShardError("range leaf continued after a terminal or fatal response")
    if state_status == "retryable":
        valid = statuses[-1] == "unavailable" and terminal_id is None
    elif state_status == "fatal":
        valid = statuses[-1] in {
            "rejected_contract", "non_authoritative_cap_probe",
        } and terminal_id is None
    else:
        valid = (
            statuses[-1] in {"accepted", "accepted_empty"}
            and terminal_id == decoded[-1]["attempt_id"]
        )
    if not valid:
        raise RangeShardError("range attempt ledger disagrees with leaf status")
    return decoded


def verify_leaf(
    store: Path, plan: Mapping[str, Any], leaf: RangeLeaf,
) -> tuple[dict[str, Any], pd.DataFrame]:
    state_path = _leaf_state_path(store, leaf.leaf_id, leaf.campaign_id)
    state = _read_json(state_path)
    _validate_leaf_state_header(state, plan, leaf)
    if state.get("status") != "terminal":
        raise RangeShardError("range leaf terminal marker is invalid")
    decoded = _validate_attempt_ledger(store, leaf, state)
    terminal = [item for item in decoded if item.get("attempt_id") == state.get("terminal_attempt_id")]
    if len(terminal) != 1 or terminal[0].get("response_status") not in {"accepted", "accepted_empty"}:
        raise RangeShardError("range leaf terminal attempt is absent or non-authoritative")
    artifact = state.get("artifact")
    if not isinstance(artifact, dict):
        raise RangeShardError("range leaf lacks an artifact receipt")
    if artifact.get("path") is None:
        frame = pd.DataFrame(columns=list(leaf.fields))
        if artifact != {
            "path": None, "byte_sha256": None, "row_count": 0,
            "semantic_sha256": frame_semantic_sha256(frame), "columns": list(leaf.fields),
        }:
            raise RangeShardError("empty range leaf artifact receipt is invalid")
    else:
        path = Path(store) / str(artifact["path"])
        if path.resolve(strict=False) != _leaf_artifact_path(store, leaf).resolve(strict=False):
            raise RangeShardError("range leaf artifact is not at its canonical path")
        if not path.is_file() or _file_sha256(path) != artifact.get("byte_sha256"):
            raise RangeShardError("range leaf artifact is missing or modified")
        try:
            frame = pd.read_parquet(path)
        except Exception as exc:
            raise RangeShardError("range leaf artifact is unreadable") from exc
        _validate_response(leaf, frame, allowed_sessions=_leaf_sessions(plan, leaf))
        if (
            list(frame.columns) != artifact.get("columns")
            or len(frame) != artifact.get("row_count")
            or frame_semantic_sha256(frame) != artifact.get("semantic_sha256")
        ):
            raise RangeShardError("range leaf artifact semantic receipt disagrees")
    if (
        len(frame) != terminal[0].get("response_row_count")
        or frame_semantic_sha256(frame) != terminal[0].get("response_semantic_sha256")
    ):
        raise RangeShardError("range leaf artifact does not bind its accepted response")
    return state, frame


def pending_leaves(store: Path, plan: Mapping[str, Any]) -> list[RangeLeaf]:
    never: list[RangeLeaf] = []
    retryable: list[tuple[int, str, RangeLeaf]] = []
    for leaf in planned_leaves(plan):
        path = _leaf_state_path(store, leaf.leaf_id, leaf.campaign_id)
        if not path.exists():
            never.append(leaf)
            continue
        state = _read_json(path)
        _validate_leaf_state_header(state, plan, leaf)
        _validate_attempt_ledger(store, leaf, state)
        status = state.get("status")
        if status == "terminal":
            verify_leaf(store, plan, leaf)
        elif status == "retryable":
            retryable.append((len(state.get("attempts", [])), leaf.leaf_id, leaf))
        elif status == "fatal":
            continue
        else:
            raise RangeShardError("range leaf has an unknown progress state")
    never.sort(key=lambda leaf: (leaf.canonical_ticker, leaf.source_ts_code, leaf.start_date))
    retryable.sort(key=lambda item: (item[0], item[1]))
    return [*never, *(item[2] for item in retryable)]


def campaign_progress(store: Path, plan: Mapping[str, Any]) -> dict[str, int]:
    """Recompute leaf and physical-attempt counts from independently stored state."""
    counts = {
        "planned_leaf_count": 0,
        "unattempted_leaf_count": 0,
        "retryable_leaf_count": 0,
        "failed_leaf_count": 0,
        "completed_leaf_count": 0,
        "physical_attempt_count": 0,
        "retry_attempt_count": 0,
    }
    leaves = planned_leaves(plan)
    counts["planned_leaf_count"] = len(leaves)
    for leaf in leaves:
        path = _leaf_state_path(store, leaf.leaf_id, leaf.campaign_id)
        if not path.exists():
            counts["unattempted_leaf_count"] += 1
            continue
        state = _read_json(path)
        _validate_leaf_state_header(state, plan, leaf)
        decoded = _validate_attempt_ledger(store, leaf, state)
        counts["physical_attempt_count"] += len(decoded)
        counts["retry_attempt_count"] += max(0, len(decoded) - 1)
        status = state["status"]
        if status == "terminal":
            verify_leaf(store, plan, leaf)
            counts["completed_leaf_count"] += 1
        elif status == "retryable":
            counts["retryable_leaf_count"] += 1
        else:
            counts["failed_leaf_count"] += 1
    return counts


def _resolve_aliases(
    plan: Mapping[str, Any], frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        empty = frame.copy()
        return empty, empty, empty
    identities = {
        _normal_source_code(item["source_ts_code"]): (
            item["canonical_ticker"], item["alias_kind"],
        )
        for item in plan["query_identities"]
    }
    work = frame.copy()
    work["__source"] = work["ts_code"].map(_normal_source_code)
    work["__canonical"] = work["__source"].map(lambda value: identities[value][0])
    work["__rank"] = work["__source"].map(
        lambda value: 0 if identities[value][1] == "canonical" else 1
    )
    resolved: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for _, group in work.groupby(["trade_date", "__canonical"], sort=True, dropna=False):
        records = group.to_dict(orient="records")
        fingerprints = {
            _canonical_json_bytes({
                key: _json_safe(value)
                for key, value in sorted(item.items())
                if key not in {"ts_code", "__source", "__canonical", "__rank"}
            })
            for item in records
        }
        if len(fingerprints) > 1:
            conflicts.extend(records)
            continue
        records.sort(key=lambda item: (item["__rank"], item["__source"]))
        resolved.append(records[0])
        duplicates.extend(records[1:])
    def clean(rows: list[dict[str, Any]]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=list(frame.columns))
        return pd.DataFrame(rows).drop(columns=["__source", "__canonical", "__rank"])
    return clean(resolved), clean(duplicates), clean(conflicts)


def _terminal_index_row(
    store: Path, leaf: RangeLeaf, state: Mapping[str, Any],
) -> dict[str, Any]:
    state_path = _leaf_state_path(store, leaf.leaf_id, leaf.campaign_id)
    artifact = state["artifact"]
    attempts = state["attempts"]
    return {
        "leaf_id": leaf.leaf_id,
        "canonical_ticker": leaf.canonical_ticker,
        "source_ts_code": leaf.source_ts_code,
        "alias_kind": leaf.alias_kind,
        "start_date": leaf.start_date,
        "end_date": leaf.end_date,
        "row_count": int(artifact["row_count"]),
        "semantic_sha256": artifact["semantic_sha256"],
        "terminal_attempt_id": state["terminal_attempt_id"],
        "attempt_count": len(attempts),
        "attempt_ledger_sha256": _sha256_bytes(_canonical_json_bytes(attempts)),
        "leaf_state_path": _relative(state_path, store),
        "leaf_state_byte_sha256": _file_sha256(state_path),
    }


def _alias_conflict_artifact_receipt(
    store: Path, campaign_id: str, conflicts: pd.DataFrame,
) -> dict[str, Any] | None:
    path = _campaign_dir(store, campaign_id) / "alias_conflicts.parquet"
    if conflicts.empty:
        if path.exists():
            raise RangeShardError("unexpected alias-conflict artifact exists")
        return None
    if not path.is_file():
        raise RangeShardError("BSE alias conflicts were not retained")
    try:
        observed = pd.read_parquet(path)
    except Exception as exc:
        raise RangeShardError("BSE alias-conflict artifact is unreadable") from exc
    if (
        len(observed) != len(conflicts)
        or list(observed.columns) != list(conflicts.columns)
        or frame_semantic_sha256(observed) != frame_semantic_sha256(conflicts)
    ):
        raise RangeShardError("BSE alias-conflict artifact disagrees with raw leaves")
    return {
        "path": _relative(path, store),
        "byte_sha256": _file_sha256(path),
        "row_count": len(observed),
        "semantic_sha256": frame_semantic_sha256(observed),
    }


def _campaign_projection(
    store: Path, plan: Mapping[str, Any], *, require_receipt: bool,
) -> CampaignVerification:
    frames: list[pd.DataFrame] = []
    index_rows: list[dict[str, Any]] = []
    for leaf in planned_leaves(plan):
        state, frame = verify_leaf(store, plan, leaf)
        frames.append(frame)
        index_rows.append(_terminal_index_row(store, leaf, state))
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=plan["fields"])
    if not raw.empty and raw.duplicated(["trade_date", "ts_code"]).any():
        raise RangeShardError("range campaign duplicated raw ticker/date keys across leaves")
    resolved, duplicate_aliases, conflicts = _resolve_aliases(plan, raw)
    day_receipts: dict[str, dict[str, Any]] = {}
    for day in plan["sessions"]:
        day_frame = resolved[
            resolved["trade_date"].map(_iso_date) == day
        ].copy() if not resolved.empty else pd.DataFrame(columns=plan["fields"])
        day_receipts[day] = {
            "trade_date": day,
            "authoritative_row_count": len(day_frame),
            "authoritative_semantic_sha256": frame_semantic_sha256(day_frame),
        }
    index = pd.DataFrame(index_rows).sort_values("leaf_id", kind="stable").reset_index(drop=True)
    receipt_path = _campaign_dir(store, plan["campaign_id"]) / "campaign_receipt.json"
    receipt = _read_json(receipt_path) if receipt_path.exists() else None
    if require_receipt:
        if receipt is None or receipt.get("schema_version") != CAMPAIGN_RECEIPT_SCHEMA_VERSION:
            raise RangeShardError("range campaign terminal receipt is absent")
        index_path = _campaign_dir(store, plan["campaign_id"]) / "terminal_index.parquet"
        conflict_artifact = _alias_conflict_artifact_receipt(
            store, plan["campaign_id"], conflicts,
        )
        expected = {
            "schema_version": CAMPAIGN_RECEIPT_SCHEMA_VERSION,
            "campaign_id": plan["campaign_id"],
            "plan_path": _relative(_plan_path(store, plan["campaign_id"]), store),
            "plan_byte_sha256": _file_sha256(_plan_path(store, plan["campaign_id"])),
            "leaf_count": len(index),
            "terminal_index_path": _relative(index_path, store),
            "terminal_index_byte_sha256": _file_sha256(index_path) if index_path.exists() else None,
            "terminal_index_semantic_sha256": frame_semantic_sha256(index),
            "observed_response_row_count": len(raw),
            "authoritative_row_count": len(resolved),
            "duplicate_alias_observation_row_count": len(duplicate_aliases),
            "conflicting_alias_row_count": len(conflicts),
            "source_accounting_complete": len(raw) == len(resolved) + len(duplicate_aliases) + len(conflicts),
            "raw_semantic_sha256": frame_semantic_sha256(raw),
            "authoritative_semantic_sha256": frame_semantic_sha256(resolved),
            "duplicate_alias_semantic_sha256": frame_semantic_sha256(duplicate_aliases),
            "conflicting_alias_semantic_sha256": frame_semantic_sha256(conflicts),
            "alias_conflict_artifact": conflict_artifact,
            "day_receipts": [day_receipts[day] for day in sorted(day_receipts)],
            "status": "complete" if conflicts.empty else "alias_conflict",
        }
        if receipt != expected:
            raise RangeShardError("range campaign terminal receipt does not bind current artifacts")
        try:
            observed_index = pd.read_parquet(index_path)
        except Exception as exc:
            raise RangeShardError("range campaign terminal index is unreadable") from exc
        if frame_semantic_sha256(observed_index) != frame_semantic_sha256(index):
            raise RangeShardError("range campaign terminal index was modified")
    return CampaignVerification(
        campaign_id=plan["campaign_id"], complete=bool(conflicts.empty),
        resolved_frame=resolved, duplicate_alias_rows=duplicate_aliases,
        conflicting_alias_rows=conflicts, day_receipts=day_receipts, receipt=receipt,
    )


def finalize_campaign(store: Path, plan: Mapping[str, Any]) -> CampaignVerification:
    """Write the terminal index/receipt after every leaf verifies."""
    projection = _campaign_projection(store, plan, require_receipt=False)
    campaign_dir = _campaign_dir(store, plan["campaign_id"])
    if not projection.conflicting_alias_rows.empty:
        _atomic_parquet(campaign_dir / "alias_conflicts.parquet", projection.conflicting_alias_rows)
    index_rows = []
    for leaf in planned_leaves(plan):
        state, _ = verify_leaf(store, plan, leaf)
        index_rows.append(_terminal_index_row(store, leaf, state))
    index = pd.DataFrame(index_rows).sort_values("leaf_id", kind="stable").reset_index(drop=True)
    index_path = campaign_dir / "terminal_index.parquet"
    _atomic_parquet(index_path, index)
    raw_count = (
        len(projection.resolved_frame) + len(projection.duplicate_alias_rows)
        + len(projection.conflicting_alias_rows)
    )
    receipt = {
        "schema_version": CAMPAIGN_RECEIPT_SCHEMA_VERSION,
        "campaign_id": plan["campaign_id"],
        "plan_path": _relative(_plan_path(store, plan["campaign_id"]), store),
        "plan_byte_sha256": _file_sha256(_plan_path(store, plan["campaign_id"])),
        "leaf_count": len(index),
        "terminal_index_path": _relative(index_path, store),
        "terminal_index_byte_sha256": _file_sha256(index_path),
        "terminal_index_semantic_sha256": frame_semantic_sha256(index),
        "observed_response_row_count": raw_count,
        "authoritative_row_count": len(projection.resolved_frame),
        "duplicate_alias_observation_row_count": len(projection.duplicate_alias_rows),
        "conflicting_alias_row_count": len(projection.conflicting_alias_rows),
        "source_accounting_complete": raw_count == (
            len(projection.resolved_frame) + len(projection.duplicate_alias_rows)
            + len(projection.conflicting_alias_rows)
        ),
        "raw_semantic_sha256": None,
        "authoritative_semantic_sha256": frame_semantic_sha256(projection.resolved_frame),
        "duplicate_alias_semantic_sha256": frame_semantic_sha256(projection.duplicate_alias_rows),
        "conflicting_alias_semantic_sha256": frame_semantic_sha256(projection.conflicting_alias_rows),
        "alias_conflict_artifact": _alias_conflict_artifact_receipt(
            store, plan["campaign_id"], projection.conflicting_alias_rows,
        ),
        "day_receipts": [projection.day_receipts[day] for day in sorted(projection.day_receipts)],
        "status": "complete" if projection.conflicting_alias_rows.empty else "alias_conflict",
    }
    # Raw semantic hash is over all leaf rows, before BSE alias de-duplication.
    raw_frames = [verify_leaf(store, plan, leaf)[1] for leaf in planned_leaves(plan)]
    raw = pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame(columns=plan["fields"])
    receipt["raw_semantic_sha256"] = frame_semantic_sha256(raw)
    _atomic_json(campaign_dir / "campaign_receipt.json", receipt)
    return _campaign_projection(store, plan, require_receipt=True)


def verify_campaign(store: Path, campaign_id: str) -> CampaignVerification:
    plan = load_plan(store, campaign_id)
    return _campaign_projection(store, plan, require_receipt=True)


def campaign_receipt_reference(store: Path, verification: CampaignVerification) -> dict[str, Any]:
    if verification.receipt is None:
        raise RangeShardError("cannot reference a non-terminal range campaign")
    path = _campaign_dir(store, verification.campaign_id) / "campaign_receipt.json"
    return {
        "campaign_id": verification.campaign_id,
        "path": _relative(path, store),
        "byte_sha256": _file_sha256(path),
        "status": verification.receipt["status"],
        "authoritative_row_count": verification.receipt["authoritative_row_count"],
        "duplicate_alias_observation_row_count": verification.receipt[
            "duplicate_alias_observation_row_count"
        ],
    }


__all__ = [
    "CAMPAIGN_RECEIPT_SCHEMA_VERSION",
    "CAMPAIGN_SCHEMA_VERSION",
    "CampaignVerification",
    "RangeLeaf",
    "RangeShardError",
    "campaign_progress",
    "campaign_receipt_reference",
    "ensure_campaign",
    "finalize_campaign",
    "frame_semantic_sha256",
    "load_plan",
    "pending_leaves",
    "planned_leaves",
    "record_attempt",
    "verify_campaign",
    "verify_leaf",
]
