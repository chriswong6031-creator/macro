"""Fail-closed collector for the ClinicalTrials.gov record-history surface.

ClinicalTrials.gov exposes the record-history data used by its public study page
through ``/api/int``.  That route is useful, but it is not the documented v2
API.  This module therefore treats it as an opt-in, source-shape-gated input:
every byte is retained privately, all version bindings are checked, and a
round-trip of the history index must agree before a complete run is emitted.

Nothing in this collector writes a public object, derives a clinical claim, or
turns a registry edit into a signal.  Historical snapshots are private source
evidence for the pure B2 diff engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import time
from typing import Any, Callable, Mapping, Sequence

import requests

from engine.sector_intelligence import (
    ContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
)


HISTORY_API_ROOT = "https://clinicaltrials.gov/api/int/studies"
HISTORY_SOURCE_ID = "clinicaltrials_gov_record_history"
PARSER_VERSION = "clinicaltrials_record_history_parser.v1"
RETRYABLE_STATUS_CODES = frozenset((408, 429, 500, 502, 503, 504))
SAFE_RESPONSE_HEADERS = frozenset(
    ("content-type", "content-length", "content-encoding", "date", "etag", "last-modified")
)
_NCT_RE = re.compile(r"NCT[0-9]{8}")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_HISTORY_URI_RE = re.compile(
    r"https://clinicaltrials\.gov/api/int/studies/NCT[0-9]{8}"
    r"(?:\?history=true|/history/[0-9]+)"
)


class CollectionError(RuntimeError):
    """A bounded source-invariant failure; callers must not publish on it."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ClinicalTrialsHistoryConfig:
    """Explicit bounded canary universe and HTTP safety limits.

    The source root is deliberately not configurable.  A config-controlled URL
    would turn a historical source collector into a server-side request proxy.
    """

    nct_ids: tuple[str, ...]
    user_agent: str
    max_history_versions: int = 64
    max_response_bytes: int = 3_000_000
    max_total_response_bytes: int = 16_000_000
    max_attempts: int = 3
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 45.0
    retry_backoff_seconds: float = 1.0
    max_retry_delay_seconds: float = 30.0
    retry_budget_seconds: float = 120.0
    min_request_interval_seconds: float = 0.25

    def __post_init__(self) -> None:
        if not self.nct_ids:
            raise ValueError("nct_ids must be non-empty")
        try:
            normalized = tuple(sorted({canonical_nct_id(value) for value in self.nct_ids}))
        except CollectionError as exc:
            raise ValueError("nct_ids must contain NCT identifiers") from exc
        object.__setattr__(self, "nct_ids", normalized)
        if not self.user_agent.strip():
            raise ValueError("a descriptive user_agent is required")
        if not 1 <= self.max_history_versions <= 256:
            raise ValueError("max_history_versions must be between 1 and 256")
        if self.max_response_bytes < 1024:
            raise ValueError("max_response_bytes must be at least 1024")
        if self.max_total_response_bytes < self.max_response_bytes:
            raise ValueError("max_total_response_bytes must cover one response")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if min(self.connect_timeout_seconds, self.read_timeout_seconds, self.retry_budget_seconds) <= 0:
            raise ValueError("request timeouts and retry budget must be positive")
        if min(self.retry_backoff_seconds, self.max_retry_delay_seconds, self.min_request_interval_seconds) < 0:
            raise ValueError("retry and request pacing values cannot be negative")


@dataclass(frozen=True)
class HistoryCollectionResult:
    """Private source evidence written by one atomic-completeness attempt."""

    nct_id: str
    run_id: str
    run_path: Path
    history_index_receipt: Mapping[str, Any]
    history_index_roundtrip_receipt: Mapping[str, Any]
    history_version_receipts: tuple[Mapping[str, Any], ...]
    source_snapshots: tuple[Mapping[str, Any], ...]
    source_snapshot_paths: tuple[Path, ...]


def canonical_nct_id(value: object) -> str:
    """Normalize the only permitted external identifier to canonical uppercase."""

    if not isinstance(value, str):
        raise CollectionError("INVALID_NCT_ID", "NCT identifier must be a string")
    canonical = value.upper()
    if not _NCT_RE.fullmatch(canonical):
        raise CollectionError("INVALID_NCT_ID", "expected NCT followed by eight digits")
    return canonical


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("clock must return timezone-aware datetimes")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _after(value: datetime, floor: datetime) -> datetime:
    value = _as_utc(value)
    return value if value > floor else floor + timedelta(microseconds=1)


def _strict_json_object(raw: bytes, label: str) -> Mapping[str, Any]:
    """Decode one exact JSON object without silent key/number coercion."""

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError(f"duplicate JSON object key {key!r}")
            parsed[key] = value
        return parsed

    def reject_nonfinite_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value!r}")

    def lossless_json_float(value: str) -> float:
        try:
            exact = Decimal(value)
            parsed = float(value)
            round_tripped = Decimal(repr(parsed))
        except (InvalidOperation, OverflowError, ValueError) as exc:
            raise ValueError(f"invalid JSON number {value!r}") from exc
        if not math.isfinite(parsed):
            raise ValueError(f"non-finite JSON number {value!r}")
        if round_tripped != exact:
            raise ValueError(f"JSON number {value!r} is not losslessly binary64")
        return parsed

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite_constant,
            parse_float=lossless_json_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CollectionError("INVALID_SOURCE_JSON", f"{label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CollectionError("INVALID_SOURCE_SHAPE", f"{label}: expected JSON object")
    try:
        canonical_json_bytes(payload)
    except ContractError as exc:
        raise CollectionError("INVALID_SOURCE_JSON", f"{label}: {exc}") from exc
    return payload


def _safe_path(root: Path, object_key: str) -> Path:
    key = PurePosixPath(object_key)
    if key.is_absolute() or ".." in key.parts or not key.parts:
        raise CollectionError("UNSAFE_OBJECT_KEY", object_key)
    resolved_root = root.resolve()
    candidate = (resolved_root / Path(*key.parts)).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise CollectionError("UNSAFE_OBJECT_KEY", object_key) from exc
    return candidate


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise CollectionError("IMMUTABLE_OBJECT_COLLISION", str(path))
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
        return
    _atomic_write(path, payload)
    if path.read_bytes() != payload:
        raise CollectionError("ARCHIVE_READBACK_MISMATCH", str(path))


def _self_hash(document: Mapping[str, Any], field: str) -> str:
    return canonical_json_sha256({key: value for key, value in document.items() if key != field})


def _require_date(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise CollectionError("INVALID_HISTORY_DATE", label)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise CollectionError("INVALID_HISTORY_DATE", label) from exc
    return value


def _require_study_nct(study: object, expected_nct_id: str, label: str) -> Mapping[str, Any]:
    if not isinstance(study, Mapping):
        raise CollectionError("INVALID_SOURCE_SHAPE", f"{label}: study must be an object")
    try:
        source_nct = study["protocolSection"]["identificationModule"]["nctId"]
    except (KeyError, TypeError) as exc:
        raise CollectionError("HISTORY_NCT_BINDING", f"{label}: missing study NCT ID") from exc
    if source_nct != expected_nct_id:
        raise CollectionError("HISTORY_NCT_BINDING", f"{label}: source NCT does not match request")
    return study


@dataclass(frozen=True)
class _HistoryVersion:
    source_version: int
    display_version: int
    source_submitted_at: str
    source_last_update_submit_qc_at: str | None
    module_labels: tuple[str, ...]

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "source_version": self.source_version,
            "display_version": self.display_version,
            "source_submitted_at": self.source_submitted_at,
            "source_last_update_submit_qc_at": self.source_last_update_submit_qc_at,
            "module_labels": list(self.module_labels),
        }


def _parse_history_index(payload: Mapping[str, Any], nct_id: str, label: str) -> tuple[_HistoryVersion, ...]:
    _require_study_nct(payload.get("study"), nct_id, label)
    history = payload.get("history")
    if not isinstance(history, Mapping):
        raise CollectionError("INVALID_HISTORY_INDEX", f"{label}: history object missing")
    changes = history.get("changes")
    if not isinstance(changes, list) or not changes:
        raise CollectionError("INVALID_HISTORY_INDEX", f"{label}: changes must be non-empty list")
    versions: list[_HistoryVersion] = []
    seen_versions: set[int] = set()
    for ordinal, change in enumerate(changes):
        if not isinstance(change, Mapping):
            raise CollectionError("INVALID_HISTORY_INDEX", f"{label}: change {ordinal} must be object")
        source_version = change.get("version")
        if isinstance(source_version, bool) or not isinstance(source_version, int) or source_version < 0:
            raise CollectionError("INVALID_HISTORY_VERSION", f"{label}: change {ordinal}")
        if source_version in seen_versions:
            raise CollectionError("DUPLICATE_HISTORY_VERSION", f"{label}: version {source_version}")
        seen_versions.add(source_version)
        submitted = _require_date(change.get("date"), f"{label}: change {ordinal} date")
        qc = change.get("lastUpdateSubmitQcDate")
        if qc is not None:
            qc = _require_date(qc, f"{label}: change {ordinal} QC date")
        labels = change.get("moduleLabels")
        if not isinstance(labels, list) or any(
            not isinstance(item, str) or not item.strip() for item in labels
        ):
            raise CollectionError("INVALID_HISTORY_INDEX", f"{label}: change {ordinal} module labels")
        if len(labels) != len(set(labels)):
            raise CollectionError("INVALID_HISTORY_INDEX", f"{label}: duplicate module label")
        for required_string in ("status", "studyType"):
            if not isinstance(change.get(required_string), str) or not change[required_string]:
                raise CollectionError("INVALID_HISTORY_INDEX", f"{label}: change {ordinal} {required_string}")
        versions.append(
            _HistoryVersion(
                source_version=source_version,
                display_version=source_version + 1,
                source_submitted_at=submitted,
                source_last_update_submit_qc_at=qc,
                module_labels=tuple(labels),
            )
        )
    source_versions = [entry.source_version for entry in versions]
    if len(versions) > 256:
        raise CollectionError("HISTORY_VERSION_CAP_EXCEEDED", label)
    if source_versions != list(range(len(source_versions))):
        raise CollectionError("HISTORY_VERSION_GAP", label)
    return tuple(versions)


class ClinicalTrialsHistoryCollector:
    """Archive one exact historical chain per configured NCT identifier."""

    def __init__(
        self,
        *,
        private_root: Path,
        config: ClinicalTrialsHistoryConfig,
        session: requests.Session | None = None,
        now_fn: Callable[[], datetime] = _utc_now,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        retry_now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.private_root = Path(private_root).resolve()
        self.config = config
        if session is None:
            self.session = requests.Session()
            self.session.trust_env = False
        else:
            self.session = session
        self.now_fn = now_fn
        self.sleep_fn = sleep_fn
        self.monotonic_fn = monotonic_fn
        self.retry_now_fn = retry_now_fn
        self.request_headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": config.user_agent,
        }
        self._last_request_started: float | None = None
        self._run_response_bytes = 0

    @staticmethod
    def _response_headers(response: Any) -> dict[str, str]:
        lowered = {str(key).lower(): str(value) for key, value in response.headers.items()}
        return {key: lowered[key] for key in sorted(SAFE_RESPONSE_HEADERS) if key in lowered}

    def _pace(self) -> None:
        if self._last_request_started is None or self.config.min_request_interval_seconds == 0:
            self._last_request_started = self.monotonic_fn()
            return
        elapsed = self.monotonic_fn() - self._last_request_started
        delay = self.config.min_request_interval_seconds - elapsed
        if delay > 0:
            self.sleep_fn(delay)
        self._last_request_started = self.monotonic_fn()

    def _retry_after_seconds(self, response: Any | None) -> float:
        if response is None:
            return 0.0
        headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
        raw = headers.get("retry-after", "").strip()
        if re.fullmatch(r"[0-9]{1,10}", raw):
            return float(raw)
        if not raw or len(raw) > 100:
            return 0.0
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at.astimezone(timezone.utc) - _as_utc(self.retry_now_fn())).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0.0

    def _bounded_response_bytes(self, response: Any, label: str) -> bytes:
        headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise CollectionError("UNEXPECTED_CONTENT_TYPE", f"{label}: {content_type or 'missing'}")
        encoding = headers.get("content-encoding", "").strip().lower()
        if encoding not in {"", "identity"}:
            raise CollectionError("UNSUPPORTED_CONTENT_ENCODING", f"{label}: {encoding}")
        declared = headers.get("content-length")
        if declared is not None:
            if not re.fullmatch(r"[0-9]{1,10}", declared):
                raise CollectionError("INVALID_CONTENT_LENGTH", label)
            if int(declared) > self.config.max_response_bytes:
                raise CollectionError("RESPONSE_TOO_LARGE", label)

        chunks: list[bytes] = []
        total = 0
        iterator = getattr(response, "iter_content", None)
        if callable(iterator):
            source_chunks = iterator(chunk_size=64 * 1024)
        else:
            source_chunks = (bytes(response.content),)
        for chunk in source_chunks:
            if not chunk:
                continue
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                raise CollectionError("INVALID_RESPONSE_BODY", label)
            copied = bytes(chunk)
            total += len(copied)
            if total > self.config.max_response_bytes:
                raise CollectionError("RESPONSE_TOO_LARGE", label)
            chunks.append(copied)
        raw = b"".join(chunks)
        if not raw:
            raise CollectionError("EMPTY_RESPONSE_BODY", label)
        self._run_response_bytes += len(raw)
        if self._run_response_bytes > self.config.max_total_response_bytes:
            raise CollectionError("TOTAL_RESPONSE_CAP_EXCEEDED", label)
        return raw

    def _get(self, source_uri: str, label: str) -> tuple[Any, bytes]:
        """Fetch only a fixed official HTTPS URI with bounded retries and bytes."""

        if not _HISTORY_URI_RE.fullmatch(source_uri):
            raise CollectionError("UNSAFE_SOURCE_URI", source_uri)
        last_error: Exception | None = None
        retry_started = self.monotonic_fn()
        for attempt in range(self.config.max_attempts):
            remaining = self.config.retry_budget_seconds - (self.monotonic_fn() - retry_started)
            if remaining <= 0:
                break
            self._pace()
            connect_timeout = min(self.config.connect_timeout_seconds, remaining / 2)
            read_timeout = min(self.config.read_timeout_seconds, remaining - connect_timeout)
            try:
                response = self.session.get(
                    source_uri,
                    headers=self.request_headers,
                    timeout=(connect_timeout, read_timeout),
                    allow_redirects=False,
                    stream=True,
                )
                status = int(response.status_code)
                if status in RETRYABLE_STATUS_CODES:
                    raise requests.HTTPError(f"HTTP {status}", response=response)
                if status != 200:
                    raise CollectionError(
                        "UNEXPECTED_HTTP_STATUS",
                        f"GET {label} returned HTTP {status}; redirects are disabled",
                    )
                return response, self._bounded_response_bytes(response, label)
            except requests.RequestException as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if not (status in RETRYABLE_STATUS_CODES or status is None) or attempt + 1 == self.config.max_attempts:
                    break
                local_delay = self.config.retry_backoff_seconds * (2**attempt)
                server_delay = self._retry_after_seconds(getattr(exc, "response", None))
                delay = max(local_delay, server_delay)
                remaining = self.config.retry_budget_seconds - (self.monotonic_fn() - retry_started)
                if delay > self.config.max_retry_delay_seconds or delay > remaining:
                    break
                self.sleep_fn(delay)
        raise CollectionError("HTTP_REQUEST_FAILED", f"GET {label}: {last_error}")

    @staticmethod
    def _run_id(nct_id: str, started_at: datetime) -> str:
        stamp = _iso(started_at).replace("-", "").replace(":", "").replace(".", "")
        return f"ctgov_history_run_{nct_id}_{stamp}"

    @staticmethod
    def _history_index_uri(nct_id: str) -> str:
        return f"{HISTORY_API_ROOT}/{nct_id}?history=true"

    @staticmethod
    def _history_version_uri(nct_id: str, source_version: int) -> str:
        return f"{HISTORY_API_ROOT}/{nct_id}/history/{source_version}"

    def _receipt(
        self,
        *,
        run_id: str,
        nct_id: str,
        receipt_suffix: str,
        resource_kind: str,
        source_version: int | None,
        source_uri: str,
        response: Any,
        raw: bytes,
        received_at: datetime,
    ) -> dict[str, Any]:
        if resource_kind not in {"history_index", "history_version"}:
            raise CollectionError("INVALID_RECEIPT", "unknown resource kind")
        if resource_kind == "history_index":
            raw_key = f"biocatalyst/raw/clinicaltrials/history/{nct_id}/index/{hashlib.sha256(raw).hexdigest()}.json"
        else:
            assert source_version is not None
            raw_key = f"biocatalyst/raw/clinicaltrials/history/{nct_id}/version-{source_version}/{hashlib.sha256(raw).hexdigest()}.json"
        receipt = {
            "contract_id": "ctgov_history_receipt.v1",
            "schema_version": "1.0.0",
            "receipt_id": f"ctgov_history_receipt_{run_id.removeprefix('ctgov_history_run_')}_{receipt_suffix}",
            "run_id": run_id,
            "source_id": HISTORY_SOURCE_ID,
            "resource_kind": resource_kind,
            "nct_id": nct_id,
            "source_version": source_version,
            "request": {
                "method": "GET",
                "source_uri": source_uri,
                "headers": {key.lower(): value for key, value in self.request_headers.items()},
                "credentials_stored": False,
            },
            "response": {
                "status_code": int(response.status_code),
                "headers": self._response_headers(response),
                "exact_response_sha256": hashlib.sha256(raw).hexdigest(),
                "raw_response_object_key": raw_key,
                "byte_count": len(raw),
                "received_at": _iso(received_at),
            },
            "parser_version": PARSER_VERSION,
            "transaction_from": _iso(_after(self.now_fn(), received_at)),
            "transaction_to": None,
            "receipt_payload_sha256": "",
            "hash_scope": "canonical_payload_excluding_receipt_payload_sha256",
        }
        receipt["receipt_payload_sha256"] = _self_hash(receipt, "receipt_payload_sha256")
        validate_contract(receipt)
        return receipt

    def _archive_receipt(self, receipt: Mapping[str, Any], raw: bytes, year: str, month: str) -> Path:
        raw_path = _safe_path(self.private_root, receipt["response"]["raw_response_object_key"])
        receipt_path = _safe_path(
            self.private_root,
            f"biocatalyst/receipts/clinicaltrials/history/{year}/{month}/{receipt['run_id']}/{receipt['receipt_id']}.json",
        )
        _write_immutable(raw_path, raw)
        _write_immutable(receipt_path, canonical_json_bytes(receipt) + b"\n")
        return receipt_path

    def _source_snapshot(
        self,
        *,
        run_id: str,
        nct_id: str,
        index_receipt: Mapping[str, Any],
        version_receipt: Mapping[str, Any],
        version: _HistoryVersion,
        study: Mapping[str, Any],
    ) -> dict[str, Any]:
        content_hash = canonical_json_sha256(study)
        retrieved_at = version_receipt["response"]["received_at"]
        snapshot_seed = canonical_json_sha256(
            {
                "nct_id": nct_id,
                "source_version": version.source_version,
                "canonical_content_sha256": content_hash,
                "run_ref": run_id,
            }
        )
        snapshot = {
            "contract_id": "trial_history_source_snapshot.v1",
            "schema_version": "1.0.0",
            "source_snapshot_id": f"ctgov_history_snapshot_{nct_id}_{snapshot_seed[:24]}",
            "nct_id": nct_id,
            "source_id": HISTORY_SOURCE_ID,
            "run_ref": run_id,
            "history_index_receipt_ref": index_receipt["receipt_id"],
            "history_version_receipt_ref": version_receipt["receipt_id"],
            "source_version": version.source_version,
            "display_version": version.display_version,
            "source_record_ref": f"src:ctgov-history:{nct_id}:version:{version.source_version}:sha256:{content_hash}",
            "source_uri": f"https://clinicaltrials.gov/study/{nct_id}?a={version.display_version}&tab=history",
            "source_submitted_at": version.source_submitted_at,
            "source_last_update_submit_qc_at": version.source_last_update_submit_qc_at,
            "canonical_study": dict(study),
            "canonical_content_sha256": content_hash,
            "retrieved_at": retrieved_at,
            "source_fact": True,
            "current_only": False,
            "coverage_class": "record_history_complete",
            "authority": {
                "classification": "source_fact",
                "decision_authority": False,
                "allowed_uses": ["display", "context", "explain"],
                "forbidden_uses": [
                    "originate_signal", "rank_security", "select_security", "size_position",
                    "gate_decision", "execute_trade", "raise_authority",
                ],
            },
            "transaction_from": _iso(_after(self.now_fn(), datetime.fromisoformat(retrieved_at.replace("Z", "+00:00")))),
            "transaction_to": None,
            "snapshot_payload_sha256": "",
            "hash_scope": "canonical_payload_excluding_snapshot_payload_sha256",
        }
        snapshot["snapshot_payload_sha256"] = _self_hash(snapshot, "snapshot_payload_sha256")
        validate_contract(snapshot)
        return snapshot

    def _archive_snapshot(self, snapshot: Mapping[str, Any]) -> Path:
        path = _safe_path(
            self.private_root,
            "biocatalyst/source_snapshots/clinicaltrials/history/"
            f"{snapshot['nct_id']}/{snapshot['source_snapshot_id']}.json",
        )
        _write_immutable(path, canonical_json_bytes(snapshot) + b"\n")
        return path

    def _run(
        self,
        *,
        run_id: str,
        nct_id: str,
        index_receipt: Mapping[str, Any],
        index_post_receipt: Mapping[str, Any],
        versions: Sequence[_HistoryVersion],
        version_receipts: Sequence[Mapping[str, Any]],
        started_at: datetime,
        finished_floor: datetime,
    ) -> dict[str, Any]:
        finished_at = _after(self.now_fn(), finished_floor)
        run = {
            "contract_id": "ctgov_history_run.v1",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "source_id": HISTORY_SOURCE_ID,
            "nct_id": nct_id,
            "history_index_receipt_ref": index_receipt["receipt_id"],
            "history_index_post_receipt_ref": index_post_receipt["receipt_id"],
            "version_manifest": [version.manifest_entry() for version in versions],
            "history_version_receipt_refs": [receipt["receipt_id"] for receipt in version_receipts],
            "started_at": _iso(started_at),
            "finished_at": _iso(finished_at),
            "run_state": "complete",
            "completeness_state": "history_complete",
            "parser_version": PARSER_VERSION,
            "error_codes": [],
            "transaction_from": _iso(_after(self.now_fn(), finished_at)),
            "transaction_to": None,
            "run_payload_sha256": "",
            "hash_scope": "canonical_payload_excluding_run_payload_sha256",
        }
        run["run_payload_sha256"] = _self_hash(run, "run_payload_sha256")
        validate_contract(run)
        return run

    def _archive_run(self, run: Mapping[str, Any], year: str, month: str) -> Path:
        path = _safe_path(
            self.private_root,
            f"biocatalyst/runs/clinicaltrials/history/{year}/{month}/{run['run_id']}.json",
        )
        _write_immutable(path, canonical_json_bytes(run) + b"\n")
        return path

    def collect_nct(self, nct_id: str) -> HistoryCollectionResult:
        """Fetch one all-or-nothing historical chain into the private archive."""

        canonical_nct = canonical_nct_id(nct_id)
        if canonical_nct not in self.config.nct_ids:
            raise CollectionError("NCT_NOT_CONFIGURED", canonical_nct)
        self._run_response_bytes = 0
        started_at = _as_utc(self.now_fn())
        run_id = self._run_id(canonical_nct, started_at)
        year, month = started_at.strftime("%Y"), started_at.strftime("%m")

        index_uri = self._history_index_uri(canonical_nct)
        index_response, index_raw = self._get(index_uri, "history index before")
        index_received = _after(self.now_fn(), started_at)
        index_payload = _strict_json_object(index_raw, "history index before")
        versions = _parse_history_index(index_payload, canonical_nct, "history index before")
        if len(versions) > self.config.max_history_versions:
            raise CollectionError("HISTORY_VERSION_CAP_EXCEEDED", canonical_nct)
        index_receipt = self._receipt(
            run_id=run_id, nct_id=canonical_nct, receipt_suffix="index_pre",
            resource_kind="history_index", source_version=None, source_uri=index_uri,
            response=index_response, raw=index_raw, received_at=index_received,
        )
        self._archive_receipt(index_receipt, index_raw, year, month)

        version_receipts: list[Mapping[str, Any]] = []
        studies_by_version: dict[int, Mapping[str, Any]] = {}
        last_received = index_received
        for version in versions:
            version_uri = self._history_version_uri(canonical_nct, version.source_version)
            response, raw = self._get(version_uri, f"history version {version.source_version}")
            received_at = _after(self.now_fn(), last_received)
            payload = _strict_json_object(raw, f"history version {version.source_version}")
            source_version = payload.get("studyVersion")
            if isinstance(source_version, bool) or source_version != version.source_version:
                raise CollectionError("HISTORY_VERSION_BINDING", f"version {version.source_version}")
            study = _require_study_nct(payload.get("study"), canonical_nct, f"history version {version.source_version}")
            receipt = self._receipt(
                run_id=run_id, nct_id=canonical_nct,
                receipt_suffix=f"version_{version.source_version}", resource_kind="history_version",
                source_version=version.source_version, source_uri=version_uri,
                response=response, raw=raw, received_at=received_at,
            )
            self._archive_receipt(receipt, raw, year, month)
            version_receipts.append(receipt)
            studies_by_version[version.source_version] = study
            last_received = received_at

        roundtrip_response, roundtrip_raw = self._get(index_uri, "history index after")
        roundtrip_received = _after(self.now_fn(), last_received)
        roundtrip_payload = _strict_json_object(roundtrip_raw, "history index after")
        roundtrip_versions = _parse_history_index(roundtrip_payload, canonical_nct, "history index after")
        roundtrip_receipt = self._receipt(
            run_id=run_id, nct_id=canonical_nct, receipt_suffix="index_post",
            resource_kind="history_index", source_version=None, source_uri=index_uri,
            response=roundtrip_response, raw=roundtrip_raw, received_at=roundtrip_received,
        )
        self._archive_receipt(roundtrip_receipt, roundtrip_raw, year, month)
        if [entry.manifest_entry() for entry in roundtrip_versions] != [entry.manifest_entry() for entry in versions]:
            raise CollectionError("HISTORY_INDEX_RACE", canonical_nct)

        run = self._run(
            run_id=run_id, nct_id=canonical_nct, index_receipt=index_receipt,
            index_post_receipt=roundtrip_receipt,
            versions=versions, version_receipts=version_receipts, started_at=started_at,
            finished_floor=roundtrip_received,
        )
        snapshots = tuple(
            self._source_snapshot(
                run_id=run_id, nct_id=canonical_nct, index_receipt=index_receipt,
                version_receipt=version_receipts[version.source_version], version=version,
                study=studies_by_version[version.source_version],
            )
            for version in versions
        )
        snapshot_paths = tuple(self._archive_snapshot(snapshot) for snapshot in snapshots)
        # The run is the complete-chain marker.  Do not make one visible until
        # every private historical source snapshot has passed validation and
        # immutable archival.
        run_path = self._archive_run(run, year, month)
        return HistoryCollectionResult(
            nct_id=canonical_nct,
            run_id=run_id,
            run_path=run_path,
            history_index_receipt=index_receipt,
            history_index_roundtrip_receipt=roundtrip_receipt,
            history_version_receipts=tuple(version_receipts),
            source_snapshots=snapshots,
            source_snapshot_paths=snapshot_paths,
        )

    def collect(self) -> tuple[HistoryCollectionResult, ...]:
        """Collect every configured NCT independently; any one failure aborts."""

        return tuple(self.collect_nct(nct_id) for nct_id in self.config.nct_ids)
