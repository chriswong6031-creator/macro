"""Bounded ClinicalTrials.gov v2 evidence collector and replay publisher.

This is the B1 evidence/publication core.  It archives exact page bytes, emits
the frozen B0a receipts/run/source-snapshot contracts, validates one complete
batch from raw bytes, and advances one atomic last-good generation pointer.
It deliberately does not schedule itself or build product/API projections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import time
from typing import Any, Callable, Mapping, Sequence

import requests

from engine.sector_intelligence import (
    ContractError,
    ContractValidationError,
    build_ctgov_publication_context,
    canonical_json_bytes,
    canonical_json_sha256,
    ctgov_query_manifest_sha256,
    receipt_payloads_sha256,
    validate_contract,
    version_receipt_payloads_sha256,
)


API_ROOT = "https://clinicaltrials.gov/api/v2"
RETRYABLE_STATUS_CODES = frozenset((408, 429, 500, 502, 503, 504))
SAFE_RESPONSE_HEADERS = frozenset(
    (
        "content-type",
        "content-length",
        "content-encoding",
        "date",
        "etag",
        "last-modified",
    )
)
REJECTED_HEADER_NAMES = [
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
]
RIGHTS_NOTE = (
    "Private source archive; product use requires ClinicalTrials.gov attribution "
    "and modification disclosure."
)

# The live worker records the exact parser/contract surface that produced a
# batch.  This deliberately avoids pretending that Python dependency wheels are
# locked across every deployment platform; source and schema compatibility are
# the replay-critical B1 boundary.
_CODE_VERSION_INPUTS = (
    "collectors/biocatalyst/clinicaltrials_v2.py",
    "engine/sector_intelligence/contracts.py",
    "contracts/biocatalyst/ctgov_fetch_run.v1.schema.json",
    "contracts/biocatalyst/source_page_receipt.v1.schema.json",
    "contracts/biocatalyst/trial_source_snapshot.v1.schema.json",
)


def current_b1_code_version() -> str:
    """Return the deterministic parser-and-contract digest supported by B1.

    The relative path is hashed alongside each exact byte stream, so swapping
    two identically sized files cannot preserve a misleading version identity.
    This has no network or environment dependency and is safe to call before a
    worker initializes any source or storage client.
    """

    repository_root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for relative in _CODE_VERSION_INPUTS:
        payload_path = repository_root / relative
        try:
            payload = payload_path.read_bytes()
        except OSError as exc:
            raise RuntimeError("B1 code-version input unavailable") from exc
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return f"biocatalyst_b1_sha256:{digest.hexdigest()}"


class CollectionError(RuntimeError):
    """Fail-closed collection or publication error with a bounded error code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ClinicalTrialsV2Config:
    nct_ids: tuple[str, ...]
    user_agent: str
    page_size: int = 100
    page_cap: int = 10
    overlap_seconds: int = 21600
    max_attempts: int = 3
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 45.0
    retry_backoff_seconds: float = 1.0
    max_retry_delay_seconds: float = 30.0
    retry_budget_seconds: float = 120.0
    code_version: str | None = None

    def __post_init__(self) -> None:
        normalized = tuple(sorted(set(self.nct_ids)))
        if normalized != self.nct_ids or not normalized:
            raise ValueError("nct_ids must be a non-empty sorted unique tuple")
        if any(
            len(value) != 11
            or not value.startswith("NCT")
            or not value[3:].isdigit()
            for value in normalized
        ):
            raise ValueError("nct_ids must contain canonical NCT identifiers")
        if not self.user_agent.strip():
            raise ValueError("a descriptive user_agent is required")
        if not 1 <= self.page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        if self.page_cap < 1 or self.max_attempts < 1:
            raise ValueError("page_cap and max_attempts must be positive")
        if min(
            self.retry_backoff_seconds,
            self.max_retry_delay_seconds,
            self.overlap_seconds,
        ) < 0:
            raise ValueError("timeouts, backoff, and overlap cannot be negative")
        if min(
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.retry_budget_seconds,
        ) <= 0:
            raise ValueError("request timeouts and retry budget must be positive")
        supported_version = current_b1_code_version()
        if self.code_version is not None and self.code_version != supported_version:
            raise ValueError("code_version must equal the current B1 parser-and-contract digest")
        object.__setattr__(self, "code_version", supported_version)


@dataclass(frozen=True)
class PublicationResult:
    run_id: str
    run_path: Path
    generation_path: Path
    current_pointer_path: Path | None
    source_snapshot_count: int


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


def _token_hash(token: str | None) -> str | None:
    return hashlib.sha256(token.encode("utf-8")).hexdigest() if token else None


def _exact_json_object(raw: bytes, label: str) -> Mapping[str, Any]:
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
            raise ValueError(
                f"JSON number {value!r} is not losslessly representable as binary64"
            )
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
        raise CollectionError("INVALID_SOURCE_SHAPE", f"{label}: expected an object")
    try:
        canonical_json_bytes(payload)
    except ContractError as exc:
        raise CollectionError("INVALID_SOURCE_JSON", f"{label}: {exc}") from exc
    return payload


def _safe_path(root: Path, object_key: str) -> Path:
    key = PurePosixPath(object_key)
    if key.is_absolute() or ".." in key.parts or not key.parts:
        raise CollectionError("UNSAFE_OBJECT_KEY", object_key)
    root = root.resolve()
    candidate = (root / Path(*key.parts)).resolve()
    try:
        candidate.relative_to(root)
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


def _atomic_pointer_write(path: Path, payload: bytes) -> None:
    """Replace a commit pointer, restoring its prior visible state on failure."""

    previous = path.read_bytes() if path.exists() else None
    try:
        _atomic_write(path, payload)
        if path.read_bytes() != payload:
            raise OSError("pointer readback mismatch")
    except Exception as original:
        try:
            if previous is None:
                path.unlink(missing_ok=True)
                _fsync_directory(path.parent)
                if path.exists():
                    raise OSError("new pointer remained visible after rollback")
            else:
                _atomic_write(path, previous)
                if path.read_bytes() != previous:
                    raise OSError("prior pointer could not be restored")
        except Exception as rollback_error:
            raise CollectionError(
                "POINTER_STATE_UNCERTAIN",
                f"pointer update failed ({original}); rollback failed ({rollback_error})",
            ) from original
        raise


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


class ClinicalTrialsV2Collector:
    """Collect and replay one explicit, bounded ClinicalTrials.gov universe."""

    def __init__(
        self,
        *,
        private_root: Path,
        public_root: Path,
        config: ClinicalTrialsV2Config,
        session: requests.Session | None = None,
        now_fn: Callable[[], datetime] = _utc_now,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        retry_now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.private_root = Path(private_root).resolve()
        self.public_root = Path(public_root).resolve()
        if (
            self.private_root == self.public_root
            or self.private_root.is_relative_to(self.public_root)
            or self.public_root.is_relative_to(self.private_root)
        ):
            raise ValueError(
                "private_root and public_root must be disjoint non-ancestor paths"
            )
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

    @staticmethod
    def _response_bytes(response: Any) -> bytes:
        encoding = str(response.headers.get("Content-Encoding", "")).strip().lower()
        if encoding not in {"", "identity"}:
            raise CollectionError(
                "UNSUPPORTED_CONTENT_ENCODING",
                f"expected identity response, received {encoding!r}",
            )
        return bytes(response.content)

    def _get(self, path: str, params: Sequence[tuple[str, str]] = ()) -> Any:
        url = f"{API_ROOT}{path}"
        last_error: Exception | None = None
        retry_started = self.monotonic_fn()
        for attempt in range(self.config.max_attempts):
            remaining_before_request = self.config.retry_budget_seconds - (
                self.monotonic_fn() - retry_started
            )
            if remaining_before_request <= 0:
                break
            connect_timeout = min(
                self.config.connect_timeout_seconds, remaining_before_request / 2
            )
            read_timeout = min(
                self.config.read_timeout_seconds,
                remaining_before_request - connect_timeout,
            )
            timeout = (connect_timeout, read_timeout)
            try:
                response = self.session.get(
                    url,
                    params=list(params),
                    headers=self.request_headers,
                    timeout=timeout,
                    allow_redirects=False,
                )
                status = int(response.status_code)
                if status in RETRYABLE_STATUS_CODES:
                    raise requests.HTTPError(f"HTTP {status}", response=response)
                if status != 200:
                    raise CollectionError(
                        "UNEXPECTED_HTTP_STATUS",
                        f"GET {path} returned HTTP {status}; redirects are disabled",
                    )
                return response
            except requests.RequestException as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                retryable = status in RETRYABLE_STATUS_CODES or status is None
                if not retryable or attempt + 1 == self.config.max_attempts:
                    break
                local_delay = self.config.retry_backoff_seconds * (2**attempt)
                server_delay = self._retry_after_seconds(
                    getattr(exc, "response", None)
                )
                delay = max(local_delay, server_delay)
                remaining = self.config.retry_budget_seconds - (
                    self.monotonic_fn() - retry_started
                )
                # Retry-After is a lower bound. Never cap it and contact the
                # source earlier than requested.
                if (
                    server_delay > self.config.max_retry_delay_seconds
                    or delay > self.config.max_retry_delay_seconds
                    or delay > remaining
                ):
                    break
                self.sleep_fn(delay)
        raise CollectionError("HTTP_REQUEST_FAILED", f"GET {path}: {last_error}")

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
            return max(
                0.0,
                (retry_at.astimezone(timezone.utc) - _as_utc(self.retry_now_fn())).total_seconds(),
            )
        except (TypeError, ValueError, OverflowError):
            return 0.0

    def _version_receipt(
        self,
        *,
        run_id: str,
        year: str,
        month: str,
        phase: str,
        response: Any,
        raw: bytes,
        source_timestamp: str,
        api_version: str,
        received_at: datetime,
    ) -> dict[str, Any]:
        """Render one sanitized, hash-bound immutable ``/version`` receipt."""

        if phase not in {"before", "after"}:
            raise CollectionError("INVALID_SOURCE_VERSION", "invalid version receipt phase")
        digest = hashlib.sha256(raw).hexdigest()
        return {
            "receipt_id": (
                f"ctgov_version_receipt_{run_id.removeprefix('ctgov_run_')}_{phase}"
            ),
            "run_id": run_id,
            "source_id": "clinicaltrials_gov_v2",
            "phase": phase,
            "receipt_object_key": (
                "biocatalyst/receipts/clinicaltrials/version/"
                f"{year}/{month}/{run_id}/{phase}.json"
            ),
            "request": {
                "method": "GET",
                "path": "/version",
                "headers": {
                    "accept": self.request_headers["Accept"],
                    "accept-encoding": self.request_headers["Accept-Encoding"],
                    "user-agent": self.request_headers["User-Agent"],
                },
            },
            "response": {
                "status_code": int(response.status_code),
                "headers": self._response_headers(response),
                "exact_response_sha256": digest,
                "raw_response_object_key": (
                    "biocatalyst/raw/clinicaltrials/v2/version/"
                    f"{year}/{month}/{run_id}/{phase}/{digest}.json"
                ),
                "byte_count": len(raw),
                "received_at": _iso(received_at),
            },
            "source_dataset_timestamp_raw": source_timestamp,
            "source_api_version": api_version,
            "sanitization": {
                "raw_pagination_tokens_stored_in_receipt": False,
                "credentials_stored_in_receipt": False,
                "rejected_header_names": REJECTED_HEADER_NAMES,
            },
            "transaction_from": _iso(received_at),
            "transaction_to": None,
        }

    def _archive_version_and_receipt(
        self, receipt: Mapping[str, Any], raw: bytes
    ) -> None:
        _write_immutable(
            _safe_path(self.private_root, receipt["response"]["raw_response_object_key"]),
            raw,
        )
        _write_immutable(
            _safe_path(self.private_root, receipt["receipt_object_key"]),
            canonical_json_bytes(receipt) + b"\n",
        )

    def _archive_failed_fetch(
        self,
        *,
        run_id: str,
        year: str,
        month: str,
        endpoint: str,
        attempt: str,
        response: Any,
        raw: bytes,
        received_at: datetime,
        failure_code: str,
    ) -> None:
        """Retain malformed HTTP-200 source bytes without minting a receipt.

        A failed fetch is evidence of an upstream behavior, but not a successful
        source page.  Its raw body and bounded incident therefore live under a
        separate private namespace which cannot be confused with run receipts.
        """

        if endpoint not in {"version", "studies"} or not re.fullmatch(
            r"(?:before|after|[0-9]+)", attempt
        ):
            raise CollectionError("FAILED_FETCH_ARCHIVE_INVALID", "unsafe failed-fetch label")
        digest = hashlib.sha256(raw).hexdigest()
        raw_key = (
            "biocatalyst/raw/clinicaltrials/v2/failed-fetch/"
            f"{year}/{month}/{run_id}/{endpoint}/{attempt}/{digest}.bin"
        )
        incident_key = (
            "biocatalyst/incidents/clinicaltrials/"
            f"{year}/{month}/{run_id}.failed_fetch_{endpoint}_{attempt}_{digest[:16]}.json"
        )
        _write_immutable(_safe_path(self.private_root, raw_key), raw)
        incident = {
            "contract_id": "biocatalyst_failed_fetch_incident.v1",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "endpoint": endpoint,
            "attempt": attempt,
            "status_code": int(response.status_code),
            "exact_response_sha256": digest,
            "raw_response_object_key": raw_key,
            "byte_count": len(raw),
            "response_headers": self._response_headers(response),
            "received_at": _iso(received_at),
            "failure_code": failure_code,
        }
        _write_immutable(
            _safe_path(self.private_root, incident_key), canonical_json_bytes(incident) + b"\n"
        )

    def _version(
        self,
        *,
        run_id: str,
        year: str,
        month: str,
        phase: str,
        started_at: datetime,
    ) -> tuple[str, str, dict[str, Any]]:
        """Fetch, strictly parse, and retain an exact CT.gov ``/version`` probe."""

        response = self._get("/version")
        received_at = _after(self.now_fn(), started_at)
        raw = bytes(response.content)
        try:
            raw = self._response_bytes(response)
            payload = _exact_json_object(raw, "/version")
            timestamp = payload.get("dataTimestamp")
            api_version = payload.get("apiVersion")
            if not isinstance(timestamp, str) or not timestamp:
                raise CollectionError("INVALID_SOURCE_VERSION", "missing dataTimestamp")
            if not re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                r"(?:Z|[+-][0-9]{2}:[0-9]{2})?",
                timestamp,
            ):
                raise CollectionError("INVALID_SOURCE_VERSION", "invalid dataTimestamp")
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as exc:
                raise CollectionError("INVALID_SOURCE_VERSION", "invalid dataTimestamp") from exc
            if not isinstance(api_version, str) or not api_version:
                raise CollectionError("INVALID_SOURCE_VERSION", "missing apiVersion")
            receipt = self._version_receipt(
                run_id=run_id,
                year=year,
                month=month,
                phase=phase,
                response=response,
                raw=raw,
                source_timestamp=timestamp,
                api_version=api_version,
                received_at=received_at,
            )
            self._archive_version_and_receipt(receipt, raw)
            return timestamp, api_version, receipt
        except CollectionError as exc:
            self._archive_failed_fetch(
                run_id=run_id,
                year=year,
                month=month,
                endpoint="version",
                attempt=phase,
                response=response,
                raw=raw,
                received_at=received_at,
                failure_code=exc.code,
            )
            raise

    def _query_manifest(self) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "api_root": API_ROOT,
            "request_path": "/studies",
            "base_query_params": {
                "query.id": ",".join(self.config.nct_ids),
                "format": "json",
                "pageSize": str(self.config.page_size),
                "countTotal": "true",
            },
            "configured_nct_ids": list(self.config.nct_ids),
            "query_sha256": "",
            "hash_scope": "canonical_manifest_excluding_query_sha256",
            "page_size": self.config.page_size,
            "overlap_seconds": self.config.overlap_seconds,
            "page_cap": self.config.page_cap,
        }
        manifest["query_sha256"] = ctgov_query_manifest_sha256(manifest)
        return manifest

    @staticmethod
    def _base_query_params(
        manifest: Mapping[str, Any],
    ) -> tuple[tuple[str, str], ...]:
        # One deterministic CSV expression; pagination appends only pageToken.
        params = manifest["base_query_params"]
        return (
            ("query.id", params["query.id"]),
            ("format", params["format"]),
            ("pageSize", params["pageSize"]),
            ("countTotal", params["countTotal"]),
        )

    @staticmethod
    def _run_id(started_at: datetime, query_hash: str) -> str:
        stamp = _iso(started_at).replace("-", "").replace(":", "").replace(".", "")
        return f"ctgov_run_{stamp}_{query_hash[:12]}"

    @staticmethod
    def _response_headers(response: Any) -> dict[str, str]:
        lowered = {str(key).lower(): str(value) for key, value in response.headers.items()}
        return {key: lowered[key] for key in sorted(SAFE_RESPONSE_HEADERS) if key in lowered}

    def _receipt(
        self,
        *,
        run_id: str,
        year: str,
        month: str,
        ordinal: int,
        query_hash: str,
        request_token: str | None,
        response: Any,
        raw: bytes,
        page: Mapping[str, Any],
        source_timestamp: str,
        api_version: str,
        received_at: datetime,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(raw).hexdigest()
        next_token = page.get("nextPageToken")
        if next_token is not None and (not isinstance(next_token, str) or not next_token):
            raise CollectionError("INVALID_PAGE_TOKEN", f"page {ordinal}")
        studies = page.get("studies")
        if not isinstance(studies, list) or any(not isinstance(item, dict) for item in studies):
            raise CollectionError("INVALID_SOURCE_SHAPE", f"page {ordinal} studies")
        receipt_id = f"ctgov_receipt_{run_id.removeprefix('ctgov_run_')}_{ordinal}"
        return {
            "contract_id": "source_page_receipt.v1",
            "schema_version": "1.0.0",
            "receipt_id": receipt_id,
            "run_id": run_id,
            "source_id": "clinicaltrials_gov_v2",
            "page_ordinal": ordinal,
            "receipt_object_key": (
                f"biocatalyst/receipts/clinicaltrials/{year}/{month}/{run_id}/{ordinal}.json"
            ),
            "request": {
                "method": "GET",
                "path": "/studies",
                "query_sha256": query_hash,
                "page_token_sha256": _token_hash(request_token),
                "headers": {
                    "accept": self.request_headers["Accept"],
                    "accept-encoding": self.request_headers["Accept-Encoding"],
                    "user-agent": self.request_headers["User-Agent"],
                },
            },
            "response": {
                "status_code": int(response.status_code),
                "headers": self._response_headers(response),
                "exact_response_sha256": digest,
                "raw_response_object_key": (
                    "biocatalyst/raw/clinicaltrials/v2/pages/"
                    f"{year}/{month}/{run_id}/{ordinal}/{digest}.json"
                ),
                "byte_count": len(raw),
                "study_count": len(studies),
                "next_page_token_sha256": _token_hash(next_token),
                "received_at": _iso(received_at),
            },
            "source_dataset_timestamp_raw": source_timestamp,
            "source_api_version": api_version,
            "sanitization": {
                "raw_pagination_tokens_stored_in_receipt": False,
                "credentials_stored_in_receipt": False,
                "rejected_header_names": REJECTED_HEADER_NAMES,
            },
            "transaction_from": _iso(received_at),
            "transaction_to": None,
        }

    def _archive_page_and_receipt(
        self, receipt: Mapping[str, Any], raw: bytes
    ) -> None:
        raw_path = _safe_path(
            self.private_root, receipt["response"]["raw_response_object_key"]
        )
        receipt_path = _safe_path(self.private_root, receipt["receipt_object_key"])
        _write_immutable(raw_path, raw)
        _write_immutable(receipt_path, canonical_json_bytes(receipt) + b"\n")

    def _run_object_key(self, run_id: str, year: str, month: str) -> str:
        return f"biocatalyst/runs/clinicaltrials/{year}/{month}/{run_id}.json"

    def _incident_path(
        self, run_id: str, year: str, month: str, suffix: str
    ) -> Path:
        return _safe_path(
            self.private_root,
            f"biocatalyst/incidents/clinicaltrials/{year}/{month}/{run_id}.{suffix}.json",
        )

    def _write_run(self, run: Mapping[str, Any], year: str, month: str) -> Path:
        validate_contract(run)
        path = _safe_path(
            self.private_root, self._run_object_key(run["run_id"], year, month)
        )
        _write_immutable(path, canonical_json_bytes(run) + b"\n")
        return path

    def _failed_run(
        self,
        *,
        run_id: str,
        manifest: Mapping[str, Any],
        started_at: datetime,
        receipts: Sequence[Mapping[str, Any]],
        raw_by_receipt: Mapping[str, bytes],
        source_before: str | None,
        source_after: str | None,
        api_version: str | None,
        api_version_after: str | None,
        version_evidence: Mapping[str, Any] | None,
        watermark_before: str | None,
        pages_attempted: int,
        code: str,
        terminal_pagination: bool,
    ) -> dict[str, Any]:
        finished = _after(self.now_fn(), started_at)
        fetched = sum(receipt["response"]["study_count"] for receipt in receipts)
        unique_nct_ids: set[str] = set()
        for receipt in receipts:
            page = _exact_json_object(
                raw_by_receipt[receipt["receipt_id"]], "failed-run archived page"
            )
            for study in page.get("studies", ()):
                try:
                    unique_nct_ids.add(self._nct_id(study))
                except CollectionError:
                    continue
        if code == "SOURCE_CHANGED_MID_RUN":
            run_state = "quarantined"
            completeness_state = "source_changed_mid_run"
        elif code == "COUNT_MISMATCH":
            run_state = "quarantined"
            completeness_state = "count_mismatch"
        elif code in {
            "ARCHIVE_READBACK_MISMATCH",
            "CONTRACT_VALIDATION_FAILED",
            "DIVERGENT_DUPLICATE",
            "IMMUTABLE_OBJECT_COLLISION",
            "INVALID_SOURCE_JSON",
            "INVALID_SOURCE_VERSION",
            "INVALID_STUDY_IDENTITY",
            "INVALID_SOURCE_SHAPE",
            "INVALID_PAGE_TOKEN",
            "PAGE_CAP_EXHAUSTED",
            "PAGINATION_CYCLE",
            "UNSUPPORTED_CONTENT_ENCODING",
            "UNEXPECTED_HTTP_STATUS",
        }:
            run_state = "quarantined"
            completeness_state = "source_invariant_failed"
        else:
            run_state = "failed"
            completeness_state = "page_incomplete"
        return {
            "contract_id": "ctgov_fetch_run.v1",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "source_id": "clinicaltrials_gov_v2",
            "mode": "canary_poll",
            "query_manifest": dict(manifest),
            "started_at": _iso(started_at),
            "finished_at": _iso(finished),
            "source_dataset_timestamp_before_raw": source_before,
            "source_dataset_timestamp_after_raw": source_after,
            "source_api_version": api_version,
            "source_api_version_after": api_version_after,
            "receipt_refs": [receipt["receipt_id"] for receipt in receipts],
            "terminal_receipt_ref": (
                receipts[-1]["receipt_id"] if terminal_pagination and receipts else None
            ),
            "receipt_payloads_sha256": receipt_payloads_sha256(receipts),
            "published_source_record_refs": [],
            "counts": {
                "configured": len(self.config.nct_ids),
                "pages_attempted": pages_attempted,
                "pages_succeeded": len(receipts),
                "studies_fetched": fetched,
                "studies_unique": len(unique_nct_ids),
                "studies_duplicate": fetched - len(unique_nct_ids),
                "studies_published": 0,
                "errors": 1,
            },
            "run_state": run_state,
            "completeness_state": completeness_state,
            "watermark_before": watermark_before,
            "watermark_after": watermark_before,
            "parser_version": "clinicaltrials_v2_parser.v1",
            "code_version": self.config.code_version,
            "error_codes": [code],
            "transaction_from": _iso(_after(self.now_fn(), finished)),
            "transaction_to": None,
            **({"version_evidence": dict(version_evidence)} if version_evidence is not None else {}),
        }

    @staticmethod
    def _nct_id(study: Mapping[str, Any]) -> str:
        try:
            value = study["protocolSection"]["identificationModule"]["nctId"]
        except (KeyError, TypeError) as exc:
            raise CollectionError("INVALID_STUDY_IDENTITY", "missing NCT ID") from exc
        if not isinstance(value, str):
            raise CollectionError("INVALID_STUDY_IDENTITY", "non-string NCT ID")
        return value

    @staticmethod
    def _last_update(study: Mapping[str, Any]) -> str | None:
        try:
            value = study["protocolSection"]["statusModule"][
                "lastUpdatePostDateStruct"
            ]["date"]
        except (KeyError, TypeError):
            return None
        return value if isinstance(value, str) else None

    def _source_snapshots(self, context: Any) -> list[dict[str, Any]]:
        receipts = {receipt["receipt_id"]: receipt for receipt in context.receipts}
        run = context.run
        snapshots: list[dict[str, Any]] = []
        seen_nct_ids: set[str] = set()
        for receipt_id, study_index, study in context.indexed_studies():
            receipt = receipts[receipt_id]
            nct_id = self._nct_id(study)
            # Raw-run validation has already proved that duplicate bodies agree.
            # Retain the first page/index occurrence so one NCT yields one snapshot.
            if nct_id in seen_nct_ids:
                continue
            seen_nct_ids.add(nct_id)
            digest = canonical_json_sha256(study)
            source_time = self._last_update(study)
            retrieved = receipt["response"]["received_at"]
            transaction = run["finished_at"]
            snapshots.append(
                {
                    "contract_id": "trial_source_snapshot.v1",
                    "schema_version": "1.0.0",
                    "source_snapshot_id": (
                        f"ctgov_snapshot_{nct_id}_{run['run_id'].removeprefix('ctgov_run_')}_{digest}"
                    ),
                    "nct_id": nct_id,
                    "source_id": "clinicaltrials_gov_v2",
                    "source_record_ref": f"src:ctgov:{nct_id}:sha256:{digest}",
                    "run_ref": run["run_id"],
                    "page_receipt_ref": receipt_id,
                    "source_page_study_index": study_index,
                    "source_uri": f"https://clinicaltrials.gov/study/{nct_id}",
                    "raw_object_key": (
                        f"biocatalyst/raw/clinicaltrials/v2/{nct_id}/{digest}.json"
                    ),
                    "exact_response_sha256": receipt["response"]["exact_response_sha256"],
                    "canonical_content_sha256": digest,
                    "hash_scope": "canonical_json_entire_study",
                    "object_key_policy": "sort_lexicographically",
                    "array_order_policy": "preserve_source_order",
                    "canonicalizer_version": "canonical_json.v1",
                    "source_schema_version": "ctgov_api_v2",
                    "license_class": "us_government_source_facts",
                    "rights_note": RIGHTS_NOTE,
                    "canonical_study": study,
                    "source_dataset_timestamp_raw": receipt[
                        "source_dataset_timestamp_raw"
                    ],
                    "source_last_update_posted_at": source_time,
                    "source_published_at": source_time,
                    "source_effective_at": None,
                    "retrieved_at": retrieved,
                    "first_seen_at": retrieved,
                    "valid_from": None,
                    "valid_to": None,
                    "coverage_class": "current_only",
                    "transaction_from": transaction,
                    "transaction_to": None,
                }
            )
        snapshots.sort(key=lambda item: item["nct_id"])
        return snapshots

    def _archive_snapshots(self, snapshots: Sequence[Mapping[str, Any]]) -> None:
        for snapshot in snapshots:
            raw_path = _safe_path(self.private_root, snapshot["raw_object_key"])
            _write_immutable(raw_path, canonical_json_bytes(snapshot["canonical_study"]))
            evidence_key = (
                "biocatalyst/source_snapshots/clinicaltrials/"
                f"{snapshot['nct_id']}/{snapshot['source_snapshot_id']}.json"
            )
            _write_immutable(
                _safe_path(self.private_root, evidence_key),
                canonical_json_bytes(snapshot) + b"\n",
            )

    @staticmethod
    def _public_source_state(snapshot: Mapping[str, Any]) -> dict[str, Any]:
        """Build the allowlisted read DTO; private provenance never crosses roots."""

        return {
            "contract_id": "biocatalyst_trial_source_state.v1",
            "schema_version": "1.0.0",
            "nct_id": snapshot["nct_id"],
            "source_snapshot_id": snapshot["source_snapshot_id"],
            "source_record_ref": snapshot["source_record_ref"],
            "canonical_content_sha256": snapshot["canonical_content_sha256"],
            "source_uri": snapshot["source_uri"],
            "source_dataset_timestamp_raw": snapshot[
                "source_dataset_timestamp_raw"
            ],
            "source_last_update_posted_at": snapshot[
                "source_last_update_posted_at"
            ],
            "source_published_at": snapshot["source_published_at"],
            "retrieved_at": snapshot["retrieved_at"],
            "coverage_class": snapshot["coverage_class"],
            "license_class": snapshot["license_class"],
            "source_attribution": "ClinicalTrials.gov",
            "modification_disclosure": (
                "BioCatalyst parsed and normalized this source-state reference."
            ),
        }

    def _publication_manifest(
        self, run: Mapping[str, Any], public_states: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        entries = [
            {
                "nct_id": state["nct_id"],
                "source_snapshot_id": state["source_snapshot_id"],
                "source_record_ref": state["source_record_ref"],
                "public_state_sha256": canonical_json_sha256(state),
            }
            for state in public_states
        ]
        payload: dict[str, Any] = {
            "manifest_version": "biocatalyst_publication.v1",
            "hash_scope": "canonical_manifest_excluding_manifest_sha256",
            "run_id": run["run_id"],
            "query_sha256": run["query_manifest"]["query_sha256"],
            "source_dataset_timestamp_raw": run[
                "source_dataset_timestamp_before_raw"
            ],
            "entries": entries,
        }
        payload["manifest_sha256"] = canonical_json_sha256(payload)
        return payload

    def _publish_generation(
        self,
        run: Mapping[str, Any],
        snapshots: Sequence[Mapping[str, Any]],
        *,
        advance_pointer: bool = True,
    ) -> tuple[Path, Path | None]:
        generations = self.public_root / (
            "generations" if advance_pointer else "replay_generations"
        )
        generations.mkdir(parents=True, exist_ok=True)
        final = generations / run["run_id"]
        stage = generations / f".{run['run_id']}.{os.getpid()}.stage"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        try:
            public_states = [self._public_source_state(snapshot) for snapshot in snapshots]
            for state in public_states:
                _atomic_write(
                    stage / f"{state['nct_id']}.json",
                    canonical_json_bytes(state) + b"\n",
                )
            manifest = self._publication_manifest(run, public_states)
            _atomic_write(
                stage / "publication_manifest.json",
                canonical_json_bytes(manifest) + b"\n",
            )
            _fsync_directory(stage)
            if final.exists():
                if {item.name for item in final.iterdir()} != {
                    item.name for item in stage.iterdir()
                }:
                    raise CollectionError("REPLAY_DIVERGENCE", str(final))
                for candidate in stage.iterdir():
                    retained = final / candidate.name
                    if not retained.exists() or retained.read_bytes() != candidate.read_bytes():
                        raise CollectionError("REPLAY_DIVERGENCE", str(candidate))
                shutil.rmtree(stage)
            else:
                os.replace(stage, final)
                _fsync_directory(generations)
            if not advance_pointer:
                return final, None
            pointer = {
                "generation": run["run_id"],
                "manifest_sha256": manifest["manifest_sha256"],
            }
            current = self.public_root / "current.json"
            _atomic_pointer_write(current, canonical_json_bytes(pointer) + b"\n")
            return final, current
        finally:
            if stage.exists():
                shutil.rmtree(stage)

    def _finish_publication(
        self,
        *,
        run: Mapping[str, Any],
        receipts: Sequence[Mapping[str, Any]],
        raw_by_receipt: Mapping[str, bytes],
        run_path: Path,
        persist_run: bool = False,
        advance_pointer: bool = True,
    ) -> PublicationResult:
        context = build_ctgov_publication_context(run, receipts, raw_by_receipt)
        snapshots = self._source_snapshots(context)
        context.validate_source_snapshots(snapshots)
        self._archive_snapshots(snapshots)
        if persist_run:
            started = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
            run_path = self._write_run(
                run, f"{started.year:04d}", f"{started.month:02d}"
            )
        generation, current = self._publish_generation(
            run, snapshots, advance_pointer=advance_pointer
        )
        return PublicationResult(
            run_id=run["run_id"],
            run_path=run_path,
            generation_path=generation,
            current_pointer_path=current,
            source_snapshot_count=len(snapshots),
        )

    def collect(self, *, watermark_before: str | None = None) -> PublicationResult:
        started = _as_utc(self.now_fn())
        manifest = self._query_manifest()
        run_id = self._run_id(started, manifest["query_sha256"])
        year, month = f"{started.year:04d}", f"{started.month:02d}"
        receipts: list[dict[str, Any]] = []
        raw_by_receipt: dict[str, bytes] = {}
        source_before: str | None = None
        source_after: str | None = None
        api_version: str | None = None
        api_version_after: str | None = None
        version_receipt_before: dict[str, Any] | None = None
        version_receipt_after: dict[str, Any] | None = None
        pages_attempted = 0
        terminal_pagination = False
        try:
            source_before, api_version, version_receipt_before = self._version(
                run_id=run_id,
                year=year,
                month=month,
                phase="before",
                started_at=started,
            )
            token: str | None = None
            seen_tokens: set[str] = set()
            for ordinal in range(self.config.page_cap):
                pages_attempted += 1
                params = self._base_query_params(manifest)
                if token is not None:
                    params = (*params, ("pageToken", token))
                response = self._get(manifest["request_path"], params)
                received = _after(self.now_fn(), started)
                raw = bytes(response.content)
                try:
                    raw = self._response_bytes(response)
                    page = _exact_json_object(raw, f"/studies page {ordinal}")
                    receipt = self._receipt(
                        run_id=run_id,
                        year=year,
                        month=month,
                        ordinal=ordinal,
                        query_hash=manifest["query_sha256"],
                        request_token=token,
                        response=response,
                        raw=raw,
                        page=page,
                        source_timestamp=source_before,
                        api_version=api_version,
                        received_at=received,
                    )
                    validate_contract(receipt)
                    self._archive_page_and_receipt(receipt, raw)
                except (CollectionError, ContractValidationError) as exc:
                    failure_code = (
                        exc.code if isinstance(exc, CollectionError) else "CONTRACT_VALIDATION_FAILED"
                    )
                    self._archive_failed_fetch(
                        run_id=run_id,
                        year=year,
                        month=month,
                        endpoint="studies",
                        attempt=str(ordinal),
                        response=response,
                        raw=raw,
                        received_at=received,
                        failure_code=failure_code,
                    )
                    raise
                receipts.append(receipt)
                raw_by_receipt[receipt["receipt_id"]] = raw
                next_token = page.get("nextPageToken")
                if next_token is None:
                    terminal_pagination = True
                    break
                next_hash = _token_hash(next_token)
                if next_hash in seen_tokens or next_token == token:
                    raise CollectionError("PAGINATION_CYCLE", f"page {ordinal}")
                seen_tokens.add(next_hash)
                token = next_token
            else:
                raise CollectionError("PAGE_CAP_EXHAUSTED", str(self.config.page_cap))

            source_after, api_version_after, version_receipt_after = self._version(
                run_id=run_id,
                year=year,
                month=month,
                phase="after",
                started_at=started,
            )
            if source_before != source_after or api_version != api_version_after:
                raise CollectionError(
                    "SOURCE_CHANGED_MID_RUN",
                    f"before={source_before}/{api_version} after={source_after}/{api_version_after}",
                )
            finished = _after(self.now_fn(), started)
            transaction = _after(self.now_fn(), finished)

            unique_hashes: dict[str, set[str]] = {}
            fetched = 0
            for receipt in receipts:
                page = _exact_json_object(raw_by_receipt[receipt["receipt_id"]], "archived page")
                for study in page["studies"]:
                    fetched += 1
                    nct_id = self._nct_id(study)
                    unique_hashes.setdefault(nct_id, set()).add(canonical_json_sha256(study))
            divergent = [nct for nct, hashes in unique_hashes.items() if len(hashes) != 1]
            if divergent:
                raise CollectionError("DIVERGENT_DUPLICATE", ",".join(sorted(divergent)))
            if set(unique_hashes) != set(self.config.nct_ids):
                raise CollectionError(
                    "COUNT_MISMATCH",
                    "terminal pages do not exactly cover the configured NCT universe",
                )
            refs = sorted(
                f"src:ctgov:{nct}:sha256:{next(iter(hashes))}"
                for nct, hashes in unique_hashes.items()
            )
            run = {
                "contract_id": "ctgov_fetch_run.v1",
                "schema_version": "1.0.0",
                "run_id": run_id,
                "source_id": "clinicaltrials_gov_v2",
                "mode": "canary_poll",
                "query_manifest": manifest,
                "started_at": _iso(started),
                "finished_at": _iso(finished),
                "source_dataset_timestamp_before_raw": source_before,
                "source_dataset_timestamp_after_raw": source_after,
                "source_api_version": api_version,
                "source_api_version_after": api_version_after,
                "version_evidence": {
                    "hash_scope": "canonical_version_receipts_before_after",
                    "version_receipt_payloads_sha256": version_receipt_payloads_sha256(
                        (version_receipt_before, version_receipt_after)
                    ),
                    "before": version_receipt_before,
                    "after": version_receipt_after,
                },
                "receipt_refs": [item["receipt_id"] for item in receipts],
                "terminal_receipt_ref": receipts[-1]["receipt_id"],
                "receipt_payloads_sha256": receipt_payloads_sha256(receipts),
                "published_source_record_refs": refs,
                "counts": {
                    "configured": len(self.config.nct_ids),
                    "pages_attempted": pages_attempted,
                    "pages_succeeded": len(receipts),
                    "studies_fetched": fetched,
                    "studies_unique": len(unique_hashes),
                    "studies_duplicate": fetched - len(unique_hashes),
                    "studies_published": len(unique_hashes),
                    "errors": 0,
                },
                "run_state": "complete",
                "completeness_state": "reconciled",
                "watermark_before": watermark_before,
                "watermark_after": _iso(transaction),
                "parser_version": "clinicaltrials_v2_parser.v1",
                "code_version": self.config.code_version,
                "error_codes": [],
                "transaction_from": _iso(transaction),
                "transaction_to": None,
            }
            run_path = _safe_path(
                self.private_root, self._run_object_key(run_id, year, month)
            )
            return self._finish_publication(
                run=run,
                receipts=receipts,
                raw_by_receipt=raw_by_receipt,
                run_path=run_path,
                persist_run=True,
            )
        except Exception as exc:
            if isinstance(exc, CollectionError):
                code = exc.code
            elif isinstance(exc, ContractValidationError):
                code = "CONTRACT_VALIDATION_FAILED"
            else:
                code = "COLLECTION_FAILED"
            failed = self._failed_run(
                run_id=run_id,
                manifest=manifest,
                started_at=started,
                receipts=receipts,
                raw_by_receipt=raw_by_receipt,
                source_before=source_before,
                source_after=source_after,
                api_version=api_version,
                api_version_after=api_version_after,
                version_evidence=(
                    {
                        "hash_scope": "canonical_version_receipts_before_after",
                        "version_receipt_payloads_sha256": version_receipt_payloads_sha256(
                            (version_receipt_before, version_receipt_after)
                        ),
                        "before": version_receipt_before,
                        "after": version_receipt_after,
                    }
                    if version_receipt_before is not None and version_receipt_after is not None
                    else None
                ),
                watermark_before=watermark_before,
                pages_attempted=pages_attempted,
                code=code,
                terminal_pagination=terminal_pagination,
            )
            completed_path = _safe_path(
                self.private_root, self._run_object_key(run_id, year, month)
            )
            if completed_path.exists():
                incident_path = self._incident_path(
                    run_id, year, month, "publication_failure"
                )
                pointer_generation: str | None = None
                pointer_state = "absent"
                current_path = self.public_root / "current.json"
                if current_path.exists():
                    try:
                        current_payload = _exact_json_object(
                            current_path.read_bytes(), "current publication pointer"
                        )
                        pointer_generation = current_payload.get("generation")
                        pointer_state = (
                            "advanced"
                            if pointer_generation == run_id
                            else "prior_generation"
                        )
                    except CollectionError:
                        pointer_state = "unreadable"
                incident = {
                    "run_id": run_id,
                    "failure_code": code,
                    "recorded_at": failed["transaction_from"],
                    "current_pointer_state": pointer_state,
                    "current_pointer_generation": pointer_generation,
                }
                _write_immutable(
                    incident_path, canonical_json_bytes(incident) + b"\n"
                )
            else:
                self._write_run(failed, year, month)
                if code == "SOURCE_CHANGED_MID_RUN":
                    details_path = self._incident_path(
                        run_id, year, month, "source_drift"
                    )
                    details = {
                        "run_id": run_id,
                        "source_dataset_timestamp_before_raw": source_before,
                        "source_dataset_timestamp_after_raw": source_after,
                        "source_api_version_before": api_version,
                        "source_api_version_after": api_version_after,
                    }
                    _write_immutable(
                        details_path, canonical_json_bytes(details) + b"\n"
                    )
            raise

    def _validate_replay_version_evidence(self, run: Mapping[str, Any]) -> None:
        """Re-open the two immutable /version probes before an offline replay."""

        evidence = run.get("version_evidence")
        if not isinstance(evidence, Mapping) or set(evidence) != {
            "hash_scope", "version_receipt_payloads_sha256", "before", "after"
        }:
            raise CollectionError("VERSION_EVIDENCE_MISSING", str(run.get("run_id")))
        before = evidence.get("before")
        after = evidence.get("after")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise CollectionError("VERSION_EVIDENCE_INVALID", str(run.get("run_id")))
        if (
            evidence.get("hash_scope") != "canonical_version_receipts_before_after"
            or evidence.get("version_receipt_payloads_sha256")
            != version_receipt_payloads_sha256((before, after))
        ):
            raise CollectionError("VERSION_EVIDENCE_INVALID", str(run.get("run_id")))
        try:
            started = datetime.fromisoformat(str(run["started_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError) as exc:
            raise CollectionError("VERSION_EVIDENCE_INVALID", str(run.get("run_id"))) from exc
        if started.tzinfo is None:
            raise CollectionError("VERSION_EVIDENCE_INVALID", str(run.get("run_id")))
        started = started.astimezone(timezone.utc)
        year, month = f"{started.year:04d}", f"{started.month:02d}"
        run_id = run.get("run_id")
        if not isinstance(run_id, str):
            raise CollectionError("VERSION_EVIDENCE_INVALID", "missing run id")
        for phase, receipt in (("before", before), ("after", after)):
            expected_key = (
                "biocatalyst/receipts/clinicaltrials/version/"
                f"{year}/{month}/{run_id}/{phase}.json"
            )
            receipt_path = _safe_path(self.private_root, expected_key)
            try:
                retained = _exact_json_object(receipt_path.read_bytes(), expected_key)
            except OSError as exc:
                raise CollectionError("VERSION_EVIDENCE_INVALID", expected_key) from exc
            if (
                dict(receipt) != retained
                or receipt.get("receipt_object_key") != expected_key
                or receipt.get("receipt_id")
                != f"ctgov_version_receipt_{run_id.removeprefix('ctgov_run_')}_{phase}"
                or receipt.get("run_id") != run_id
                or receipt.get("phase") != phase
            ):
                raise CollectionError("VERSION_EVIDENCE_INVALID", expected_key)
            request = receipt.get("request")
            if not isinstance(request, Mapping) or request.get("method") != "GET" or request.get("path") != "/version" or request.get("headers") != {
                "accept": "application/json",
                "accept-encoding": "identity",
                "user-agent": self.config.user_agent,
            }:
                raise CollectionError("VERSION_EVIDENCE_INVALID", expected_key)
            response = receipt.get("response")
            digest = response.get("exact_response_sha256") if isinstance(response, Mapping) else None
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise CollectionError("VERSION_EVIDENCE_INVALID", expected_key)
            raw_key = (
                "biocatalyst/raw/clinicaltrials/v2/version/"
                f"{year}/{month}/{run_id}/{phase}/{digest}.json"
            )
            if not isinstance(response, Mapping) or response.get("status_code") != 200 or response.get("raw_response_object_key") != raw_key:
                raise CollectionError("VERSION_EVIDENCE_INVALID", expected_key)
            try:
                raw = _safe_path(self.private_root, raw_key).read_bytes()
            except OSError as exc:
                raise CollectionError("VERSION_EVIDENCE_INVALID", raw_key) from exc
            if hashlib.sha256(raw).hexdigest() != digest or response.get("byte_count") != len(raw):
                raise CollectionError("VERSION_EVIDENCE_INVALID", raw_key)
            payload = _exact_json_object(raw, raw_key)
            expected_timestamp = run.get(
                "source_dataset_timestamp_before_raw" if phase == "before" else "source_dataset_timestamp_after_raw"
            )
            expected_version = run.get(
                "source_api_version" if phase == "before" else "source_api_version_after"
            )
            if (
                payload.get("dataTimestamp") != expected_timestamp
                or payload.get("apiVersion") != expected_version
                or receipt.get("source_dataset_timestamp_raw") != expected_timestamp
                or receipt.get("source_api_version") != expected_version
            ):
                raise CollectionError("VERSION_EVIDENCE_INVALID", raw_key)
        if (
            run.get("source_dataset_timestamp_before_raw")
            != run.get("source_dataset_timestamp_after_raw")
            or run.get("source_api_version") != run.get("source_api_version_after")
        ):
            raise CollectionError("VERSION_EVIDENCE_INVALID", str(run_id))

    def replay(self, run_path: Path) -> PublicationResult:
        """Replay and publish a complete run using only immutable local evidence."""

        supplied_path = Path(run_path)
        try:
            lexical_path = Path(os.path.abspath(supplied_path))
            resolved_root = self.private_root.resolve(strict=True)
            resolved_path = supplied_path.resolve(strict=True)
            resolved_path.relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise CollectionError("RUN_NOT_REPLAYABLE", str(supplied_path)) from exc
        # Requiring lexical and resolved identity rejects a symlink at any
        # component, including an in-root alias to otherwise valid evidence.
        if supplied_path.is_symlink() or lexical_path != resolved_path or not resolved_path.is_file():
            raise CollectionError("RUN_NOT_REPLAYABLE", str(supplied_path))
        run = _exact_json_object(resolved_path.read_bytes(), str(resolved_path))
        if run.get("run_state") != "complete":
            raise CollectionError("RUN_NOT_REPLAYABLE", str(run.get("run_id")))
        try:
            started = datetime.fromisoformat(str(run["started_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError) as exc:
            raise CollectionError("RUN_NOT_REPLAYABLE", str(run.get("run_id"))) from exc
        run_id = run.get("run_id")
        if started.tzinfo is None or not isinstance(run_id, str):
            raise CollectionError("RUN_NOT_REPLAYABLE", str(run_id))
        started = started.astimezone(timezone.utc)
        expected_run_path = _safe_path(
            self.private_root,
            "biocatalyst/runs/clinicaltrials/"
            f"{started.year:04d}/{started.month:02d}/{run_id}.json",
        )
        if resolved_path != expected_run_path:
            raise CollectionError("RUN_NOT_REPLAYABLE", str(run_id))
        if run.get("code_version") != self.config.code_version:
            raise CollectionError("UNSUPPORTED_CODE_VERSION", str(run.get("run_id")))
        self._validate_replay_version_evidence(run)
        receipts: list[Mapping[str, Any]] = []
        raw_by_receipt: dict[str, bytes] = {}
        for receipt_id in run["receipt_refs"]:
            ordinal = len(receipts)
            started = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
            key = (
                "biocatalyst/receipts/clinicaltrials/"
                f"{started.year:04d}/{started.month:02d}/{run['run_id']}/{ordinal}.json"
            )
            receipt = _exact_json_object(
                _safe_path(self.private_root, key).read_bytes(), receipt_id
            )
            if receipt.get("receipt_id") != receipt_id:
                raise CollectionError("RECEIPT_ID_MISMATCH", receipt_id)
            raw = _safe_path(
                self.private_root, receipt["response"]["raw_response_object_key"]
            ).read_bytes()
            receipts.append(receipt)
            raw_by_receipt[receipt_id] = raw
        return self._finish_publication(
            run=run,
            receipts=receipts,
            raw_by_receipt=raw_by_receipt,
            run_path=resolved_path,
            advance_pointer=False,
        )
