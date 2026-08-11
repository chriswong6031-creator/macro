"""Bounded, private, dark HTTP transport for the validated B1S2a fixed cohort.

This module performs exactly one reviewed source conversation for one already
validated ``ctgov_fixed_cohort.v1`` document: ``GET /version``, one bounded
``GET /studies`` for that cohort, then ``GET /version`` again.  Membership comes
solely from ``config/biocatalyst_sources.yml`` plus the validated cohort; no
environment variable can replace, enlarge, or reorder it, and this module reads
exactly one environment name -- the disabled-by-default activation gate.

It deliberately owns no scheduler, worker, installer, storage publication,
projection, API route, issuer/asset mapping, alert, score, or ranking.  Output
is private run/receipt evidence only: an NCT-level reconciliation of what the
source returned against what the fixed cohort declared.  A single failed
invariant produces an empty quarantine receipt rather than partial records.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any

import requests

from collectors.biocatalyst.clinicaltrials_discovery import (
    DiscoveryLimits,
    DiscoveryResponse,
    DiscoveryTransport,
    _check_document_bounds,
    _check_string,
)
from collectors.biocatalyst.clinicaltrials_v2 import (
    API_ROOT,
    RETRYABLE_STATUS_CODES,
    SAFE_RESPONSE_HEADERS,
    CollectionError,
    _exact_json_object,
)
from engine.biocatalyst.fixed_cohort import (
    FIXED_COHORT_CONTROL_REGISTRATION,
    FIXED_COHORT_MAX_NCT_IDS,
    FIXED_COHORT_REGISTRY_REF,
    FIXED_COHORT_SOURCE_ID,
    query_id_byte_issues,
    validate_fixed_cohort,
)
from engine.sector_intelligence.contracts import (
    ContractError,
    ContractRegistry,
    ContractValidationError,
    ValidationIssue,
    canonical_json_bytes,
    canonical_json_sha256,
)


FIXED_COHORT_TRANSPORT_CONTRACT_ID = "ctgov_fixed_cohort_transport_run.v1"
FIXED_COHORT_TRANSPORT_MODE = "dark_fixed_cohort_transport"
FIXED_COHORT_TRANSPORT_GATE_ENV = "BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED"
FIXED_COHORT_TRANSPORT_GATE_DEFAULT = "0"
FIXED_COHORT_REQUEST_PATH = "/studies"
FIXED_COHORT_VERSION_PATH = "/version"
FIXED_COHORT_STUDY_FIELDS = ("protocolSection.identificationModule.nctId",)
FIXED_COHORT_FIELDS_PARAM = ",".join(FIXED_COHORT_STUDY_FIELDS)
FIXED_COHORT_HASH_SCOPE = "canonical_payload_excluding_run_payload_sha256"
FIXED_COHORT_EVIDENCE_CLASS = "private_run_receipt_only"
DEFAULT_USER_AGENT = (
    "MastermindX-BioCatalyst/1.0 (biocatalyst@mastermind-x.com)"
)

# Reviewed hard ceilings.  Defaults sit below every ceiling on purpose; a caller
# may lower them and may never raise one.
MAX_ATTEMPTS = 3
MAX_CONNECT_TIMEOUT_SECONDS = 10.0
MAX_READ_TIMEOUT_SECONDS = 45.0
MAX_RETRY_BUDGET_SECONDS = 120.0
MAX_RETRY_DELAY_SECONDS = 30.0
DEFAULT_MAX_RESPONSE_BYTES = 3 * 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_RUN_BYTES = 16 * 1024 * 1024
MAX_RUN_BYTES = 64 * 1024 * 1024
STREAM_CHUNK_BYTES = 64 * 1024
MAX_REQUEST_PARAMS = 8
MAX_REQUEST_HEADERS = 8
MAX_REQUEST_HEADER_BYTES = 1_024
MAX_RESPONSE_HEADERS = 32
MAX_RESPONSE_HEADER_BYTES = 8_192
MAX_USER_AGENT_BYTES = 512
COHORT_SNAPSHOT_MAX_BYTES = 8 * 1024
MAX_ERROR_CODES = 8

_NCT_ID_RE = re.compile(r"^NCT[0-9]{8}$", re.ASCII)
_VERSION_TIMESTAMP_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})?"
)
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$", re.ASCII)
_REDIRECT_STATUS_CODES = frozenset((301, 302, 303, 307, 308))
_PROHIBITED = (
    "dynamic_cohort_expansion", "live_ingestion", "identity_mapping", "scoring",
    "prediction", "prophet_authority", "neural_web_authority", "ranking",
    "sizing", "alerts",
)
_RUN_STATES = ("complete", "quarantined")


class FixedCohortTransportError(CollectionError):
    """One bounded transport or reconciliation failure with a fixed error code."""


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("clock must return timezone-aware datetimes")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def transport_gate_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether the single reviewed activation gate is explicitly on.

    The gate defaults to off.  Only the exact string ``"1"`` enables network
    I/O; every other value, including ``"true"``, leaves the lane dark.
    """

    values = os.environ if environ is None else environ
    raw = values.get(FIXED_COHORT_TRANSPORT_GATE_ENV, FIXED_COHORT_TRANSPORT_GATE_DEFAULT)
    return isinstance(raw, str) and raw.strip() == "1"


def require_transport_gate(environ: Mapping[str, str] | None = None) -> None:
    """Fail closed with one distinct code unless the activation gate is on."""

    if not transport_gate_enabled(environ):
        raise FixedCohortTransportError(
            "TRANSPORT_DISABLED",
            f"{FIXED_COHORT_TRANSPORT_GATE_ENV} is not set to 1; network I/O is refused",
        )


def require_fixed_cohort_user_agent(user_agent: object) -> str:
    if not isinstance(user_agent, str) or not user_agent.strip():
        raise ValueError("a descriptive user_agent is required")
    encoded = user_agent.encode("utf-8")
    if len(encoded) > MAX_USER_AGENT_BYTES:
        raise ValueError("user_agent exceeds the reviewed byte ceiling")
    if any(ord(value) < 0x20 or ord(value) == 0x7F for value in user_agent):
        raise ValueError("user_agent must not contain control characters")
    return user_agent


@dataclass(frozen=True)
class FixedCohortTransportLimits:
    """Hard retry, timeout, and byte limits for one bounded fixed-cohort run."""

    max_attempts: int = MAX_ATTEMPTS
    connect_timeout_seconds: float = MAX_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = MAX_READ_TIMEOUT_SECONDS
    retry_budget_seconds: float = MAX_RETRY_BUDGET_SECONDS
    retry_backoff_seconds: float = 1.0
    max_retry_delay_seconds: float = MAX_RETRY_DELAY_SECONDS
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    max_run_bytes: int = DEFAULT_MAX_RUN_BYTES

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise ValueError("max_attempts must be an integer")
        if not 1 <= self.max_attempts <= MAX_ATTEMPTS:
            raise ValueError(f"max_attempts must be between 1 and {MAX_ATTEMPTS}")
        positive = (
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.retry_budget_seconds,
            self.retry_backoff_seconds,
            self.max_retry_delay_seconds,
            self.max_response_bytes,
            self.max_run_bytes,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("all fixed-cohort transport limits must be positive")
        ceilings = (
            (self.connect_timeout_seconds, MAX_CONNECT_TIMEOUT_SECONDS, "connect_timeout_seconds"),
            (self.read_timeout_seconds, MAX_READ_TIMEOUT_SECONDS, "read_timeout_seconds"),
            (self.retry_budget_seconds, MAX_RETRY_BUDGET_SECONDS, "retry_budget_seconds"),
            (self.max_retry_delay_seconds, MAX_RETRY_DELAY_SECONDS, "max_retry_delay_seconds"),
            (self.max_response_bytes, MAX_RESPONSE_BYTES, "max_response_bytes"),
            (self.max_run_bytes, MAX_RUN_BYTES, "max_run_bytes"),
        )
        for value, ceiling, name in ceilings:
            if value > ceiling:
                raise ValueError(f"{name} exceeds its reviewed hard ceiling")
        if self.max_run_bytes < self.max_response_bytes:
            raise ValueError("max_run_bytes must cover one response")
        if self.connect_timeout_seconds + self.read_timeout_seconds > self.retry_budget_seconds:
            raise ValueError("retry_budget_seconds must cover one full attempt")

    def json_limits(self) -> DiscoveryLimits:
        """Bind the sibling harness's JSON-tree bounds to this byte envelope."""

        return DiscoveryLimits(
            # Request one sentinel slot beyond the largest legal cohort.  The
            # source currently emits nextPageToken when pageSize equals the
            # exact result count, even though no record remains.  The spare
            # slot preserves the fail-closed continuation check without
            # increasing membership: reconciliation below still rejects any
            # record outside the at-most-25 declared identifiers.
            page_size=FIXED_COHORT_MAX_NCT_IDS + 1,
            page_cap=1,
            max_records=FIXED_COHORT_MAX_NCT_IDS + 1,
            max_page_records=FIXED_COHORT_MAX_NCT_IDS,
            max_response_bytes=self.max_response_bytes,
            max_total_response_bytes=self.max_run_bytes,
        )


@dataclass(frozen=True)
class FixedCohortTransportCounters:
    """Exact bounded work counters for one run; bytes include both version probes."""

    requests_attempted: int
    version_probes: int
    page_requests: int
    largest_response_bytes: int
    run_bytes: int


@dataclass
class _MutableCounters:
    requests_attempted: int = 0
    version_probes: int = 0
    page_requests: int = 0
    largest_response_bytes: int = 0
    run_bytes: int = 0

    def freeze(self) -> FixedCohortTransportCounters:
        return FixedCohortTransportCounters(
            requests_attempted=self.requests_attempted,
            version_probes=self.version_probes,
            page_requests=self.page_requests,
            largest_response_bytes=self.largest_response_bytes,
            run_bytes=self.run_bytes,
        )


@dataclass(frozen=True)
class FixedCohortSourceVersion:
    """The source dataset clock; never an event, selection, or product clock."""

    data_timestamp_raw: str
    api_version: str
    retrieved_at: str

    def receipt_payload(self) -> dict[str, str]:
        return {
            "data_timestamp_raw": self.data_timestamp_raw,
            "api_version": self.api_version,
            "retrieved_at": self.retrieved_at,
        }


@dataclass(frozen=True)
class FixedCohortRunSuccess:
    """One exactly reconciled fixed-cohort observation; NCT identifiers only."""

    state: str
    cohort_id: str
    cohort_payload_sha256: str
    query_id: str
    query_params: tuple[tuple[str, str], ...]
    requested_nct_ids: tuple[str, ...]
    returned_nct_ids: tuple[str, ...]
    source_version_before: FixedCohortSourceVersion
    source_version_after: FixedCohortSourceVersion
    retrieval_started_at: str
    retrieval_finished_at: str
    counters: FixedCohortTransportCounters
    max_response_bytes: int
    max_run_bytes: int
    error_codes: tuple[()] = ()


@dataclass(frozen=True)
class FixedCohortRunQuarantine:
    """One bounded failure result.  It never carries partial or raw source records."""

    state: str
    error_code: str
    cohort_id: str
    cohort_payload_sha256: str
    query_id: str
    query_params: tuple[tuple[str, str], ...]
    requested_nct_ids: tuple[str, ...]
    retrieval_started_at: str
    retrieval_finished_at: str
    counters: FixedCohortTransportCounters
    max_response_bytes: int
    max_run_bytes: int
    returned_nct_ids: tuple[()] = ()
    source_version_before: FixedCohortSourceVersion | None = None
    source_version_after: FixedCohortSourceVersion | None = None


FixedCohortRunResult = FixedCohortRunSuccess | FixedCohortRunQuarantine


def _detached_cohort(cohort: object) -> dict[str, Any]:
    """Detach one finite cohort snapshot before validation and membership use.

    A ``dict`` subclass can make ``get`` and ``__getitem__`` disagree, so the
    validated document and the requested membership must be the same plain
    JSON tree.
    """

    try:
        raw = canonical_json_bytes(cohort)
    except Exception as exc:
        raise FixedCohortTransportError(
            "INVALID_FIXED_COHORT", "cohort must be a finite canonical JSON object"
        ) from exc
    if len(raw) > COHORT_SNAPSHOT_MAX_BYTES:
        raise FixedCohortTransportError(
            "INVALID_FIXED_COHORT", "cohort snapshot exceeds the reviewed byte limit"
        )
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise FixedCohortTransportError(
            "INVALID_FIXED_COHORT", "cohort cannot be detached into canonical JSON"
        ) from exc
    if type(parsed) is not dict:
        raise FixedCohortTransportError("INVALID_FIXED_COHORT", "cohort must detach to a JSON object")
    return parsed


def fixed_cohort_query_params(cohort: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Return the one deterministic bounded query this lane is allowed to send.

    ``query.id`` is the cohort's own comma-joined membership.  Nothing widens it:
    there is no filter, no date window, and no continuation parameter.  One
    extra page slot is a source-pagination sentinel, not membership capacity;
    every returned identifier is still reconciled against the fixed cohort.
    """

    nct_ids = cohort["nct_ids"]
    return (
        ("query.id", cohort["query_id"]),
        ("fields", FIXED_COHORT_FIELDS_PARAM),
        ("format", "json"),
        ("pageSize", str(len(nct_ids) + 1)),
        ("countTotal", "true"),
    )


def _close_response(response: Any, *, primary: BaseException | None) -> None:
    """Close one response on every path without ever masking the primary error."""

    try:
        response.close()
    except BaseException as exc:  # noqa: BLE001 - cleanup must not shadow the cause
        if primary is None:
            raise FixedCohortTransportError(
                "RESPONSE_CLOSE_FAILED", f"source response could not be closed: {exc}"
            ) from exc
        # A cleanup failure is strictly less informative than the failure that
        # is already propagating, so the original exception stays authoritative.


def read_capped_stream(response: Any, *, cap: int) -> bytes:
    """Stream at most ``cap + 1`` bytes so an overflow is provable but bounded.

    A hostile single chunk is trimmed to the remaining allowance before it is
    retained, so a multi-gigabyte chunk cannot be materialized in order to
    discover that it is too large.
    """

    if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
        raise ValueError("cap must be a positive integer")
    limit = cap + 1
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=STREAM_CHUNK_BYTES):
        if chunk is None:
            continue
        if not isinstance(chunk, (bytes, bytearray)):
            raise FixedCohortTransportError(
                "MALFORMED_RESPONSE_BODY", "streamed source chunk must be bytes"
            )
        if not chunk:
            continue
        remaining = limit - total
        if len(chunk) > remaining:
            chunk = chunk[:remaining]
        chunks.append(bytes(chunk))
        total += len(chunk)
        if total >= limit:
            break
    return b"".join(chunks)


def _bounded_response_headers(headers: object) -> dict[str, str]:
    if not isinstance(headers, Mapping) or len(headers) > MAX_RESPONSE_HEADERS:
        raise FixedCohortTransportError(
            "MALFORMED_RESPONSE_HEADERS", "source response headers are invalid"
        )
    lowered: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise FixedCohortTransportError(
                "MALFORMED_RESPONSE_HEADERS", "source response headers are invalid"
            )
        if any(ord(item) < 0x20 or ord(item) == 0x7F for item in key + value):
            raise FixedCohortTransportError(
                "MALFORMED_RESPONSE_HEADERS", "source response headers are invalid"
            )
        if len(key.encode("utf-8")) + len(value.encode("utf-8")) > MAX_RESPONSE_HEADER_BYTES:
            raise FixedCohortTransportError(
                "MALFORMED_RESPONSE_HEADERS", "source response headers are invalid"
            )
        lowered[key.lower()] = value
    # Only the reviewed receipt-safe header names cross this boundary; cookies
    # and credentials never do.
    return {key: lowered[key] for key in sorted(SAFE_RESPONSE_HEADERS) if key in lowered}


def _require_request_path(path: object) -> str:
    if not isinstance(path, str) or path not in {
        FIXED_COHORT_VERSION_PATH,
        FIXED_COHORT_REQUEST_PATH,
    }:
        raise FixedCohortTransportError(
            "UNSUPPORTED_REQUEST_PATH", "only the reviewed fixed-cohort paths may be requested"
        )
    return path


def _require_bounded_params(params: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(params, tuple) or len(params) > MAX_REQUEST_PARAMS:
        raise FixedCohortTransportError("MALFORMED_REQUEST_PARAMS", "request params are invalid")
    bounded: list[tuple[str, str]] = []
    for item in params:
        if not isinstance(item, tuple) or len(item) != 2:
            raise FixedCohortTransportError("MALFORMED_REQUEST_PARAMS", "request params are invalid")
        key, value = item
        if not isinstance(key, str) or not isinstance(value, str):
            raise FixedCohortTransportError("MALFORMED_REQUEST_PARAMS", "request params are invalid")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in key + value):
            raise FixedCohortTransportError("MALFORMED_REQUEST_PARAMS", "request params are invalid")
        bounded.append((key, value))
    return tuple(bounded)


def _require_bounded_headers(headers: object) -> dict[str, str]:
    if not isinstance(headers, Mapping) or len(headers) > MAX_REQUEST_HEADERS:
        raise FixedCohortTransportError("MALFORMED_REQUEST_HEADERS", "request headers are invalid")
    bounded: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise FixedCohortTransportError("MALFORMED_REQUEST_HEADERS", "request headers are invalid")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in key + value):
            raise FixedCohortTransportError("MALFORMED_REQUEST_HEADERS", "request headers are invalid")
        if len(key.encode("utf-8")) + len(value.encode("utf-8")) > MAX_REQUEST_HEADER_BYTES:
            raise FixedCohortTransportError("MALFORMED_REQUEST_HEADERS", "request headers are invalid")
        bounded[key] = value
    return bounded


class BoundedFixedCohortHttpTransport:
    """The only real network implementation of the injected transport boundary.

    It refuses to exist, and refuses every request, unless the reviewed
    activation gate is explicitly on.  Redirects, proxy/environment
    inheritance, compression, unbounded reads, and unbounded retries are all
    disabled here rather than left to a caller.
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        limits: FixedCohortTransportLimits = FixedCohortTransportLimits(),
        session: Any | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._environ = environ
        require_transport_gate(environ)
        self.user_agent = require_fixed_cohort_user_agent(user_agent)
        self.limits = limits
        self.session = requests.Session() if session is None else session
        # No proxy, netrc, or CA-bundle environment inheritance may reach this
        # lane, whether the session was constructed here or handed in.
        self.session.trust_env = False
        self.session.proxies = {}
        if getattr(self.session, "trust_env", True) is not False or getattr(self.session, "proxies", None) != {}:
            raise FixedCohortTransportError(
                "UNSAFE_SESSION", "session must disable environment and proxy inheritance"
            )
        self.sleep_fn = sleep_fn
        self.monotonic_fn = monotonic_fn
        self.run_bytes = 0

    def get(
        self,
        path: str,
        *,
        params: tuple[tuple[str, str], ...],
        headers: Mapping[str, str],
    ) -> DiscoveryResponse:
        # Re-checked per request: an environment that changed after construction
        # must not leave a live transport behind.
        require_transport_gate(self._environ)
        request_path = _require_request_path(path)
        query = _require_bounded_params(params)
        request_headers = _require_bounded_headers(headers)
        url = f"{API_ROOT}{request_path}"
        last_error: Exception | None = None
        retry_started = self.monotonic_fn()
        for attempt in range(self.limits.max_attempts):
            remaining = self.limits.retry_budget_seconds - (self.monotonic_fn() - retry_started)
            if remaining <= 0:
                break
            connect_timeout = min(self.limits.connect_timeout_seconds, remaining / 2)
            read_timeout = min(self.limits.read_timeout_seconds, remaining - connect_timeout)
            try:
                return self._attempt(
                    url=url,
                    params=query,
                    headers=request_headers,
                    timeout=(connect_timeout, read_timeout),
                )
            except requests.RequestException as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                retryable = status in RETRYABLE_STATUS_CODES or status is None
                if not retryable or attempt + 1 == self.limits.max_attempts:
                    break
                delay = self.limits.retry_backoff_seconds * (2**attempt)
                budget_left = self.limits.retry_budget_seconds - (
                    self.monotonic_fn() - retry_started
                )
                if delay > self.limits.max_retry_delay_seconds or delay > budget_left:
                    break
                self.sleep_fn(delay)
        raise FixedCohortTransportError(
            "HTTP_REQUEST_FAILED", f"GET {request_path}: {last_error}"
        )

    def _attempt(
        self,
        *,
        url: str,
        params: tuple[tuple[str, str], ...],
        headers: Mapping[str, str],
        timeout: tuple[float, float],
    ) -> DiscoveryResponse:
        response = self.session.get(
            url,
            params=list(params),
            headers=dict(headers),
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
        primary: BaseException | None = None
        try:
            status = response.status_code
            if isinstance(status, bool) or not isinstance(status, int):
                raise FixedCohortTransportError("MALFORMED_HTTP_STATUS", "status code is invalid")
            if status in _REDIRECT_STATUS_CODES:
                raise FixedCohortTransportError(
                    "REDIRECT_NOT_ALLOWED", f"GET returned HTTP {status}; redirects are disabled"
                )
            if status in RETRYABLE_STATUS_CODES:
                raise requests.HTTPError(f"HTTP {status}", response=response)
            if status != 200:
                raise FixedCohortTransportError(
                    "UNEXPECTED_HTTP_STATUS", f"GET returned HTTP {status}"
                )
            header_map = _bounded_response_headers(response.headers)
            encoding = header_map.get("content-encoding", "").strip().lower()
            if encoding not in {"", "identity"}:
                raise FixedCohortTransportError(
                    "UNSUPPORTED_CONTENT_ENCODING", "source response is encoded"
                )
            declared = header_map.get("content-length")
            if declared is not None and (
                re.fullmatch(r"[0-9]{1,10}", declared) is None
                or int(declared) > self.limits.max_response_bytes
            ):
                raise FixedCohortTransportError(
                    "INVALID_CONTENT_LENGTH", "content length is invalid or exceeds cap"
                )
            body = read_capped_stream(response, cap=self.limits.max_response_bytes)
            if len(body) > self.limits.max_response_bytes:
                raise FixedCohortTransportError(
                    "RESPONSE_BYTE_CAP_EXCEEDED", "source response exceeds the reviewed cap"
                )
            if self.run_bytes + len(body) > self.limits.max_run_bytes:
                raise FixedCohortTransportError(
                    "RUN_BYTE_CAP_EXCEEDED", "transport run exceeds the reviewed byte cap"
                )
            self.run_bytes += len(body)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            _close_response(response, primary=primary)
        return DiscoveryResponse(status_code=status, headers=header_map, body=body)


class ClinicalTrialsFixedCohortTransportRun:
    """Run exactly one bounded fixed-cohort conversation through an injected transport.

    The transport argument has no default, so this class cannot reach a network
    on its own; a caller must supply a reviewed, explicitly gated implementation.
    """

    def __init__(
        self,
        *,
        cohort: Mapping[str, Any],
        transport: DiscoveryTransport,
        limits: FixedCohortTransportLimits = FixedCohortTransportLimits(),
        user_agent: str = DEFAULT_USER_AGENT,
        now_fn: Callable[[], datetime] = _utc_now,
        repo_root: Path | str | None = None,
    ) -> None:
        snapshot = _detached_cohort(cohort)
        try:
            # config/biocatalyst_sources.yml plus this document are the only
            # membership authority; validation binds both.
            validate_fixed_cohort(snapshot, repo_root=repo_root)
        except (ContractValidationError, ContractError) as exc:
            raise FixedCohortTransportError(
                "INVALID_FIXED_COHORT", "cohort failed its contract before any request"
            ) from exc
        self.cohort = snapshot
        self.requested_nct_ids: tuple[str, ...] = tuple(snapshot["nct_ids"])
        self.query_id: str = snapshot["query_id"]
        self.cohort_id: str = snapshot["cohort_id"]
        self.cohort_payload_sha256: str = snapshot["cohort_payload_sha256"]
        self.transport = transport
        self.limits = limits
        self.json_limits = limits.json_limits()
        self.user_agent = require_fixed_cohort_user_agent(user_agent)
        self.now_fn = now_fn
        self.query_params = fixed_cohort_query_params(snapshot)
        self._last_clock_value: datetime | None = None
        self.request_headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": self.user_agent,
        }

    def run(self) -> FixedCohortRunResult:
        """Return one exactly reconciled observation or one empty quarantine.

        The reviewed conversation is exactly ``/version``, one ``/studies``, and
        ``/version`` again.  This method never raises source faults to callers
        and never exposes partially reconciled membership.
        """

        counters = _MutableCounters()
        self._last_clock_value = None
        try:
            started_clock = self._clock_now()
            started = _iso(started_clock)
        except Exception:
            return self._quarantine(
                error_code="INVALID_RETRIEVAL_CLOCK",
                started=None,
                counters=counters,
            )
        try:
            version_before = self._fetch_version(counters)
            returned = self._fetch_cohort_page(counters)
            version_after = self._fetch_version(counters)
            if (
                version_before.data_timestamp_raw != version_after.data_timestamp_raw
                or version_before.api_version != version_after.api_version
            ):
                raise FixedCohortTransportError(
                    "SOURCE_CHANGED_MID_RUN", "source version changed during the run"
                )
            finished_clock = self._clock_now()
            if finished_clock <= started_clock:
                raise FixedCohortTransportError(
                    "NON_MONOTONIC_RETRIEVAL_CLOCK",
                    "a successful run must have a positive clock interval",
                )
            return FixedCohortRunSuccess(
                state="complete",
                cohort_id=self.cohort_id,
                cohort_payload_sha256=self.cohort_payload_sha256,
                query_id=self.query_id,
                query_params=self.query_params,
                requested_nct_ids=self.requested_nct_ids,
                returned_nct_ids=returned,
                source_version_before=version_before,
                source_version_after=version_after,
                retrieval_started_at=started,
                retrieval_finished_at=_iso(finished_clock),
                counters=counters.freeze(),
                max_response_bytes=self.limits.max_response_bytes,
                max_run_bytes=self.limits.max_run_bytes,
            )
        except FixedCohortTransportError as exc:
            return self._quarantine(error_code=exc.code, started=started, counters=counters)
        except Exception:
            return self._quarantine(
                error_code="TRANSPORT_OR_HARNESS_FAILURE", started=started, counters=counters
            )

    def _quarantine(
        self,
        *,
        error_code: str,
        started: str | None,
        counters: _MutableCounters,
    ) -> FixedCohortRunQuarantine:
        try:
            finished = _iso(self._clock_now())
        except Exception:
            # A broken reporting clock cannot cause an escape from the empty
            # quarantine boundary; the primary failure stays authoritative.
            finished = started if started is not None else _iso(datetime.min.replace(tzinfo=timezone.utc))
        return FixedCohortRunQuarantine(
            state="quarantined",
            error_code=error_code,
            cohort_id=self.cohort_id,
            cohort_payload_sha256=self.cohort_payload_sha256,
            query_id=self.query_id,
            query_params=self.query_params,
            requested_nct_ids=self.requested_nct_ids,
            retrieval_started_at=started if started is not None else finished,
            retrieval_finished_at=finished,
            counters=counters.freeze(),
            max_response_bytes=self.limits.max_response_bytes,
            max_run_bytes=self.limits.max_run_bytes,
        )

    def _clock_now(self) -> datetime:
        current = _as_utc(self.now_fn())
        if self._last_clock_value is not None and current < self._last_clock_value:
            raise FixedCohortTransportError(
                "NON_MONOTONIC_RETRIEVAL_CLOCK", "retrieval clock moved backwards"
            )
        self._last_clock_value = current
        return current

    def _fetch_version(self, counters: _MutableCounters) -> FixedCohortSourceVersion:
        payload, received_at = self._fetch_json(
            path=FIXED_COHORT_VERSION_PATH, params=(), counters=counters
        )
        counters.version_probes += 1
        timestamp = payload.get("dataTimestamp")
        api_version = payload.get("apiVersion")
        if not isinstance(timestamp, str) or not _VERSION_TIMESTAMP_RE.fullmatch(timestamp):
            raise FixedCohortTransportError("INVALID_SOURCE_VERSION", "invalid source dataTimestamp")
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FixedCohortTransportError(
                "INVALID_SOURCE_VERSION", "invalid source dataTimestamp"
            ) from exc
        if not isinstance(api_version, str) or not api_version:
            raise FixedCohortTransportError("INVALID_SOURCE_VERSION", "invalid source apiVersion")
        _check_string(api_version, self.json_limits)
        return FixedCohortSourceVersion(
            data_timestamp_raw=timestamp,
            api_version=api_version,
            retrieved_at=received_at,
        )

    def _fetch_cohort_page(self, counters: _MutableCounters) -> tuple[str, ...]:
        payload, _ = self._fetch_json(
            path=FIXED_COHORT_REQUEST_PATH, params=self.query_params, counters=counters
        )
        counters.page_requests += 1
        if "nextPageToken" in payload:
            # One page only.  A continuation token means the cohort did not fit
            # the reviewed single-request envelope, which fails closed.
            raise FixedCohortTransportError(
                "NEXT_PAGE_TOKEN_PRESENT", "source offered a continuation token"
            )
        studies = payload.get("studies")
        if not isinstance(studies, list):
            raise FixedCohortTransportError("INVALID_SOURCE_SHAPE", "studies must be a list")
        if len(studies) > len(self.requested_nct_ids):
            raise FixedCohortTransportError(
                "RETURNED_RECORD_CAP_EXCEEDED", "source returned more records than the fixed cohort"
            )
        seen: list[str] = []
        for study in studies:
            nct_id = self._nct_id_from_study(study)
            if nct_id in seen:
                raise FixedCohortTransportError(
                    "DUPLICATE_NCT_ID", "source returned a duplicate NCT identifier"
                )
            seen.append(nct_id)
        total_count = payload.get("totalCount")
        if total_count is not None and (
            isinstance(total_count, bool)
            or not isinstance(total_count, int)
            or total_count != len(seen)
        ):
            raise FixedCohortTransportError(
                "TOTAL_COUNT_MISMATCH", "source totalCount does not match the returned records"
            )
        requested = set(self.requested_nct_ids)
        returned = set(seen)
        if returned - requested:
            raise FixedCohortTransportError(
                "UNREQUESTED_NCT_ID", "source returned an identifier outside the fixed cohort"
            )
        if requested - returned:
            raise FixedCohortTransportError(
                "MISSING_COHORT_MEMBER", "source omitted a declared fixed-cohort member"
            )
        if len(seen) != len(self.requested_nct_ids):
            raise FixedCohortTransportError(
                "COHORT_COUNT_MISMATCH", "returned record count does not match the fixed cohort"
            )
        return tuple(sorted(seen))

    def _nct_id_from_study(self, study: object) -> str:
        if not isinstance(study, Mapping):
            raise FixedCohortTransportError("INVALID_SOURCE_SHAPE", "study must be an object")
        _check_document_bounds(study, self.json_limits)
        try:
            nct_id = study["protocolSection"]["identificationModule"]["nctId"]
        except (KeyError, TypeError) as exc:
            raise FixedCohortTransportError(
                "MISSING_NCT_ID", "source study lacks the requested identifier field"
            ) from exc
        if not isinstance(nct_id, str) or not _NCT_ID_RE.fullmatch(nct_id):
            raise FixedCohortTransportError("INVALID_NCT_ID", "source NCT identifier is invalid")
        return nct_id

    def _fetch_json(
        self,
        *,
        path: str,
        params: tuple[tuple[str, str], ...],
        counters: _MutableCounters,
    ) -> tuple[Mapping[str, Any], str]:
        counters.requests_attempted += 1
        try:
            response = self.transport.get(path, params=params, headers=self.request_headers)
        except Exception as exc:
            raise FixedCohortTransportError(
                "TRANSPORT_FAILURE", "injected transport rejected the request"
            ) from exc
        raw = self._validated_response_body(response, counters)
        received_at = _iso(self._clock_now())
        try:
            payload = _exact_json_object(raw, path)
        except CollectionError as exc:
            raise FixedCohortTransportError(exc.code, "source JSON rejected") from exc
        _check_document_bounds(payload, self.json_limits)
        return payload, received_at

    def _validated_response_body(self, response: object, counters: _MutableCounters) -> bytes:
        if not isinstance(response, DiscoveryResponse):
            raise FixedCohortTransportError(
                "MALFORMED_TRANSPORT_RESPONSE", "transport returned the wrong response type"
            )
        if isinstance(response.status_code, bool) or not isinstance(response.status_code, int):
            raise FixedCohortTransportError("MALFORMED_HTTP_STATUS", "status code is invalid")
        if response.status_code != 200:
            raise FixedCohortTransportError(
                "UNEXPECTED_HTTP_STATUS", "source response is not HTTP 200"
            )
        headers = _bounded_response_headers(response.headers)
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise FixedCohortTransportError("UNEXPECTED_CONTENT_TYPE", "source response is not JSON")
        content_encoding = headers.get("content-encoding", "").strip().lower()
        if content_encoding not in {"", "identity"}:
            raise FixedCohortTransportError(
                "UNSUPPORTED_CONTENT_ENCODING", "source response is encoded"
            )
        declared_length = headers.get("content-length")
        if declared_length is not None and (
            re.fullmatch(r"[0-9]{1,10}", declared_length) is None
            or int(declared_length) > self.limits.max_response_bytes
        ):
            raise FixedCohortTransportError(
                "INVALID_CONTENT_LENGTH", "content length is invalid or exceeds cap"
            )
        if not isinstance(response.body, bytes):
            raise FixedCohortTransportError("MALFORMED_RESPONSE_BODY", "source body must be bytes")
        body = response.body
        if len(body) > self.limits.max_response_bytes:
            raise FixedCohortTransportError(
                "RESPONSE_BYTE_CAP_EXCEEDED", "source response exceeds the reviewed cap"
            )
        if declared_length is not None and int(declared_length) != len(body):
            raise FixedCohortTransportError(
                "CONTENT_LENGTH_MISMATCH", "source content length mismatches the body"
            )
        if counters.run_bytes + len(body) > self.limits.max_run_bytes:
            raise FixedCohortTransportError(
                "RUN_BYTE_CAP_EXCEEDED", "run exceeds the reviewed total byte cap"
            )
        counters.run_bytes += len(body)
        counters.largest_response_bytes = max(counters.largest_response_bytes, len(body))
        return body


def _identity_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return the independently hashed identity payload for one run receipt."""

    return {
        key: value
        for key, value in document.items()
        if key not in {"run_id", "run_payload_sha256"}
    }


def build_fixed_cohort_transport_run(
    result: FixedCohortRunResult,
    *,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Build and validate one private run receipt for a completed transport run.

    The receipt records NCT-level reconciliation evidence only.  It carries no
    issuer, ticker, sponsor, asset, score, rank, size, or alert, and it is not
    a publication, projection, or ledger advance.
    """

    if not isinstance(result, (FixedCohortRunSuccess, FixedCohortRunQuarantine)):
        raise FixedCohortTransportError(
            "MALFORMED_RUN_RESULT", "run receipts are built only from this lane's results"
        )
    quarantined = isinstance(result, FixedCohortRunQuarantine)
    error_codes = [result.error_code] if quarantined else []
    version_before = result.source_version_before
    version_after = result.source_version_after
    document: dict[str, Any] = {
        "contract_id": FIXED_COHORT_TRANSPORT_CONTRACT_ID,
        "schema_version": "1.0.0",
        "source_id": FIXED_COHORT_SOURCE_ID,
        "mode": FIXED_COHORT_TRANSPORT_MODE,
        "cohort_id": result.cohort_id,
        "cohort_payload_sha256": result.cohort_payload_sha256,
        "membership_authority": "fixed_cohort_only",
        "control_registration": FIXED_COHORT_CONTROL_REGISTRATION,
        "source_registry_ref": FIXED_COHORT_REGISTRY_REF,
        "api_root": API_ROOT,
        "request_path": FIXED_COHORT_REQUEST_PATH,
        "version_path": FIXED_COHORT_VERSION_PATH,
        "query_id": result.query_id,
        "requested_nct_ids": list(result.requested_nct_ids),
        "returned_nct_ids": list(result.returned_nct_ids),
        "counts": {
            "requested_nct_ids": len(result.requested_nct_ids),
            "returned_nct_ids": len(result.returned_nct_ids),
            "version_probes": result.counters.version_probes,
            "page_requests": result.counters.page_requests,
        },
        "byte_counts": {
            "largest_response_bytes": result.counters.largest_response_bytes,
            "run_bytes": result.counters.run_bytes,
            "max_response_bytes": result.max_response_bytes,
            "max_run_bytes": result.max_run_bytes,
        },
        "run_state": "quarantined" if quarantined else "complete",
        "reconciliation_state": "not_reconciled" if quarantined else "exact_fixed_cohort_match",
        "error_codes": error_codes,
        "source_version_before": version_before.receipt_payload() if version_before else None,
        "source_version_after": version_after.receipt_payload() if version_after else None,
        "started_at": result.retrieval_started_at,
        "finished_at": result.retrieval_finished_at,
        "transport_gate_env": FIXED_COHORT_TRANSPORT_GATE_ENV,
        "evidence_class": FIXED_COHORT_EVIDENCE_CLASS,
        "authority": "facts_and_context_only",
        "prohibited_claims": list(_PROHIBITED),
        "prohibited_uses": list(_PROHIBITED),
        "hash_scope": FIXED_COHORT_HASH_SCOPE,
    }
    document["run_id"] = (
        f"ctgov_fixed_cohort_transport_run_{canonical_json_sha256(_identity_payload(document))[:24]}"
    )
    document["run_payload_sha256"] = canonical_json_sha256(document)
    validate_fixed_cohort_transport_run(document, repo_root=repo_root)
    return document


def fixed_cohort_transport_run_semantic_issues(
    document: Mapping[str, Any], *, repo_root: Path | str | None = None
) -> list[ValidationIssue]:
    """Return deterministic semantic failures for one B1S2a transport receipt."""

    if not isinstance(document, Mapping):
        return [_issue("$", "fixed_cohort_transport.document", "run receipt must be a JSON object")]
    issues: list[ValidationIssue] = []
    requested = document.get("requested_nct_ids")
    returned = document.get("returned_nct_ids")
    if not isinstance(requested, list) or not 1 <= len(requested) <= FIXED_COHORT_MAX_NCT_IDS:
        issues.append(_issue("$.requested_nct_ids", "fixed_cohort_transport.requested_count", "requested_nct_ids must contain 1-25 identifiers"))
        requested = []
    elif any(not isinstance(value, str) or not _NCT_ID_RE.fullmatch(value) for value in requested):
        issues.append(_issue("$.requested_nct_ids", "fixed_cohort_transport.requested_id", "requested_nct_ids must be canonical ASCII NCT######## identifiers"))
        requested = []
    else:
        if len(set(requested)) != len(requested):
            issues.append(_issue("$.requested_nct_ids", "fixed_cohort_transport.requested_unique", "requested_nct_ids must be unique"))
        if requested != sorted(requested):
            issues.append(_issue("$.requested_nct_ids", "fixed_cohort_transport.requested_order", "requested_nct_ids must be sorted"))
        if document.get("query_id") != ",".join(requested):
            issues.append(_issue("$.query_id", "fixed_cohort_transport.query_binding", "query_id must be the exact comma-join of requested_nct_ids"))
    issues.extend(query_id_byte_issues(document.get("query_id")))
    if not isinstance(returned, list) or any(
        not isinstance(value, str) or not _NCT_ID_RE.fullmatch(value) for value in returned
    ):
        issues.append(_issue("$.returned_nct_ids", "fixed_cohort_transport.returned_id", "returned_nct_ids must be canonical ASCII NCT######## identifiers"))
        returned = []
    else:
        if len(set(returned)) != len(returned):
            issues.append(_issue("$.returned_nct_ids", "fixed_cohort_transport.returned_unique", "returned_nct_ids must be unique"))
        if returned != sorted(returned):
            issues.append(_issue("$.returned_nct_ids", "fixed_cohort_transport.returned_order", "returned_nct_ids must be sorted"))
        if set(returned) - set(requested):
            issues.append(_issue("$.returned_nct_ids", "fixed_cohort_transport.membership", "returned_nct_ids may never exceed the requested fixed cohort"))
    counts = document.get("counts")
    if not isinstance(counts, Mapping):
        issues.append(_issue("$.counts", "fixed_cohort_transport.counts", "counts must be an object"))
        counts = {}
    else:
        if counts.get("requested_nct_ids") != len(requested):
            issues.append(_issue("$.counts.requested_nct_ids", "fixed_cohort_transport.counts", "counts.requested_nct_ids must equal the requested membership size"))
        if counts.get("returned_nct_ids") != len(returned):
            issues.append(_issue("$.counts.returned_nct_ids", "fixed_cohort_transport.counts", "counts.returned_nct_ids must equal the returned membership size"))
    error_codes = document.get("error_codes")
    if not isinstance(error_codes, list) or len(error_codes) > MAX_ERROR_CODES or any(
        not isinstance(code, str) or not _ERROR_CODE_RE.fullmatch(code) for code in error_codes
    ):
        issues.append(_issue("$.error_codes", "fixed_cohort_transport.error_codes", "error_codes must be bounded uppercase codes"))
        error_codes = []
    run_state = document.get("run_state")
    version_before = document.get("source_version_before")
    version_after = document.get("source_version_after")
    if run_state == "complete":
        if list(returned) != list(requested):
            issues.append(_issue("$.returned_nct_ids", "fixed_cohort_transport.reconciliation", "a complete run must return the fixed cohort exactly"))
        if error_codes:
            issues.append(_issue("$.error_codes", "fixed_cohort_transport.error_codes", "a complete run must carry no error codes"))
        if document.get("reconciliation_state") != "exact_fixed_cohort_match":
            issues.append(_issue("$.reconciliation_state", "fixed_cohort_transport.reconciliation", "a complete run must record an exact fixed-cohort match"))
        if counts.get("version_probes") != 2 or counts.get("page_requests") != 1:
            issues.append(_issue("$.counts", "fixed_cohort_transport.sequence", "a complete run is exactly two version probes and one page request"))
        if not isinstance(version_before, Mapping) or not isinstance(version_after, Mapping):
            issues.append(_issue("$.source_version_before", "fixed_cohort_transport.source_version", "a complete run must record both source versions"))
        elif (
            version_before.get("data_timestamp_raw") != version_after.get("data_timestamp_raw")
            or version_before.get("api_version") != version_after.get("api_version")
        ):
            issues.append(_issue("$.source_version_after", "fixed_cohort_transport.source_version", "source version before and after a complete run must match"))
    elif run_state == "quarantined":
        if returned:
            issues.append(_issue("$.returned_nct_ids", "fixed_cohort_transport.quarantine", "a quarantined run must carry no returned identifiers"))
        if not error_codes:
            issues.append(_issue("$.error_codes", "fixed_cohort_transport.quarantine", "a quarantined run must record at least one error code"))
        if document.get("reconciliation_state") != "not_reconciled":
            issues.append(_issue("$.reconciliation_state", "fixed_cohort_transport.quarantine", "a quarantined run is never reconciled"))
    else:
        issues.append(_issue("$.run_state", "fixed_cohort_transport.run_state", f"run_state must be one of {list(_RUN_STATES)}"))
    byte_counts = document.get("byte_counts")
    if not isinstance(byte_counts, Mapping):
        issues.append(_issue("$.byte_counts", "fixed_cohort_transport.byte_counts", "byte_counts must be an object"))
    else:
        largest = byte_counts.get("largest_response_bytes")
        run_bytes = byte_counts.get("run_bytes")
        response_cap = byte_counts.get("max_response_bytes")
        run_cap = byte_counts.get("max_run_bytes")
        numbers = (largest, run_bytes, response_cap, run_cap)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in numbers):
            issues.append(_issue("$.byte_counts", "fixed_cohort_transport.byte_counts", "byte_counts must be non-negative integers"))
        else:
            if response_cap > MAX_RESPONSE_BYTES or run_cap > MAX_RUN_BYTES:
                issues.append(_issue("$.byte_counts", "fixed_cohort_transport.byte_ceiling", "declared byte caps may never exceed the reviewed hard ceilings"))
            if largest > response_cap or run_bytes > run_cap or largest > run_bytes:
                issues.append(_issue("$.byte_counts", "fixed_cohort_transport.byte_cap", "observed bytes must stay within the declared caps"))
    started_at = document.get("started_at")
    finished_at = document.get("finished_at")
    if isinstance(started_at, str) and isinstance(finished_at, str) and finished_at < started_at:
        issues.append(_issue("$.finished_at", "fixed_cohort_transport.clock", "finished_at must not precede started_at"))
    try:
        identity_sha256 = canonical_json_sha256(_identity_payload(document))
        content_sha256 = canonical_json_sha256(
            {key: value for key, value in document.items() if key != "run_payload_sha256"}
        )
    except ContractError:
        return sorted(set(issues + [_issue("$", "fixed_cohort_transport.canonical_payload", "run receipt must be finite canonical JSON")]))
    if document.get("run_id") != f"ctgov_fixed_cohort_transport_run_{identity_sha256[:24]}":
        issues.append(_issue("$.run_id", "fixed_cohort_transport.identity", "run_id must derive from the canonical identity excluding run_id and run_payload_sha256"))
    if document.get("run_payload_sha256") != content_sha256:
        issues.append(_issue("$.run_payload_sha256", "fixed_cohort_transport.hash", "run_payload_sha256 must hash the canonical payload excluding only itself"))
    return sorted(set(issues))


def validate_fixed_cohort_transport_run(
    document: Any, *, repo_root: Path | str | None = None
) -> None:
    """Fail closed unless schema and B1S2a semantic controls both hold."""

    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[2]
    registry = ContractRegistry(root)
    schema_issues = list(registry.issues(FIXED_COHORT_TRANSPORT_CONTRACT_ID, document))
    semantic_issues = (
        fixed_cohort_transport_run_semantic_issues(document, repo_root=root)
        if isinstance(document, Mapping)
        else [_issue("$", "fixed_cohort_transport.document", "run receipt must be a JSON object")]
    )
    issues = tuple(sorted(set(schema_issues + semantic_issues)))
    if issues:
        raise ContractValidationError(FIXED_COHORT_TRANSPORT_CONTRACT_ID, issues)
