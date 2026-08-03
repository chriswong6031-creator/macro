"""Hermetic, dark-only ClinicalTrials.gov v2 discovery transport harness.

This module intentionally owns *no* live HTTP client, scheduler, credential,
storage, publication, API, or activation path.  It makes the source-side
pagination and capacity contract executable against an injected transport so a
later, separately reviewed collector can consume a small candidate batch.  A
candidate is an NCT ID plus the source's ``LastUpdatePostDate`` selection field;
it is not an issuer, security, event, clinical conclusion, or completeness claim.

The existing explicit-NCT canary collector remains the canonical live transport
implementation.  This harness reuses its strict JSON and error semantics while
remaining impossible to run against the network unless a future caller supplies
its own reviewed transport implementation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import re
from typing import Any, Protocol

from collectors.biocatalyst.clinicaltrials_v2 import (
    API_ROOT,
    CollectionError,
    _exact_json_object,
)
from engine.sector_intelligence import canonical_json_bytes


DISCOVERY_SOURCE_ID = "clinicaltrials_gov_v2"
DISCOVERY_REQUEST_PATH = "/studies"
DISCOVERY_MODE = "dark_discovery_harness"
DISCOVERY_SELECTION_FIELD = "LastUpdatePostDate"
DISCOVERY_STUDY_FIELDS = (
    "protocolSection.identificationModule.nctId",
    "protocolSection.statusModule.lastUpdatePostDateStruct.date",
)
DISCOVERY_FIELDS_PARAM = ",".join(DISCOVERY_STUDY_FIELDS)
_NCT_ID_RE = re.compile(r"NCT[0-9]{8}")
_VERSION_TIMESTAMP_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})?"
)
MAX_PAGE_SIZE = 1_000
MAX_PAGE_CAP = 2_048
MAX_RECORDS = 200_000
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 256 * 1024
MAX_TOKEN_BYTES = 512
MAX_STRING_BYTES = 4_096
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MAX_CONTAINER_ITEMS = 10_000
MAX_USER_AGENT_BYTES = 512
MAX_RESPONSE_HEADERS = 32
MAX_RESPONSE_HEADER_BYTES = 8_192
MAX_WINDOW_DAYS = 366


class DiscoveryError(CollectionError):
    """A source or capacity failure that must produce no candidate batch."""


@dataclass(frozen=True)
class DiscoveryWindow:
    """Inclusive source-selection dates, distinct from source and retrieval clocks."""

    start_date: str
    end_date: str

    def __post_init__(self) -> None:
        start = _require_date(self.start_date, "selection start date")
        end = _require_date(self.end_date, "selection end date")
        if start > end:
            raise ValueError("selection start_date must not be after end_date")
        if (end - start).days + 1 > MAX_WINDOW_DAYS:
            raise ValueError("selection window exceeds the reviewed 366-day ceiling")

    @property
    def advanced_filter(self) -> str:
        return (
            f"AREA[{DISCOVERY_SELECTION_FIELD}]RANGE["
            f"{self.start_date},{self.end_date}]"
        )


@dataclass(frozen=True)
class DiscoveryLimits:
    """Hard source-input limits.  Defaults remain deliberately conservative."""

    page_size: int = 100
    page_cap: int = 50
    max_records: int = 5_000
    max_page_records: int | None = None
    max_response_bytes: int = 2_000_000
    max_total_response_bytes: int = 16_000_000
    max_record_bytes: int = 64_000
    max_token_bytes: int = MAX_TOKEN_BYTES
    max_string_bytes: int = MAX_STRING_BYTES
    max_json_depth: int = 64
    max_json_nodes: int = 20_000
    max_container_items: int = 2_000

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= MAX_PAGE_SIZE:
            raise ValueError("page_size must be between 1 and 1000")
        if not 1 <= self.page_cap <= MAX_PAGE_CAP:
            raise ValueError("page_cap must be between 1 and 2048")
        if not 1 <= self.max_records <= MAX_RECORDS:
            raise ValueError("max_records must be between 1 and 200000")
        page_records = self.page_size if self.max_page_records is None else self.max_page_records
        if not 1 <= page_records <= self.page_size:
            raise ValueError("max_page_records must be between 1 and page_size")
        object.__setattr__(self, "max_page_records", page_records)
        positive = (
            self.max_response_bytes,
            self.max_total_response_bytes,
            self.max_record_bytes,
            self.max_token_bytes,
            self.max_string_bytes,
            self.max_json_depth,
            self.max_json_nodes,
            self.max_container_items,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("all discovery capacity limits must be positive")
        if self.max_total_response_bytes < self.max_response_bytes:
            raise ValueError("max_total_response_bytes must cover one response")
        if self.max_records < self.max_page_records:
            raise ValueError("max_records must cover one page")
        if self.page_size * self.page_cap > self.max_records:
            raise ValueError("page_size multiplied by page_cap must not exceed max_records")
        ceilings = (
            (self.max_response_bytes, MAX_RESPONSE_BYTES, "max_response_bytes"),
            (self.max_total_response_bytes, MAX_TOTAL_RESPONSE_BYTES, "max_total_response_bytes"),
            (self.max_record_bytes, MAX_RECORD_BYTES, "max_record_bytes"),
            (self.max_token_bytes, MAX_TOKEN_BYTES, "max_token_bytes"),
            (self.max_string_bytes, MAX_STRING_BYTES, "max_string_bytes"),
            (self.max_json_depth, MAX_JSON_DEPTH, "max_json_depth"),
            (self.max_json_nodes, MAX_JSON_NODES, "max_json_nodes"),
            (self.max_container_items, MAX_CONTAINER_ITEMS, "max_container_items"),
        )
        for value, ceiling, name in ceilings:
            if value > ceiling:
                raise ValueError(f"{name} exceeds its reviewed hard ceiling")


@dataclass(frozen=True)
class DiscoveryConfig:
    """Pure configuration for the source selection and capacity envelope."""

    window: DiscoveryWindow
    limits: DiscoveryLimits = DiscoveryLimits()
    user_agent: str = "MastermindX-BioCatalyst/discovery-harness"

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise ValueError("a descriptive user_agent is required")
        try:
            encoded = self.user_agent.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("user_agent must be valid UTF-8") from exc
        if len(encoded) > MAX_USER_AGENT_BYTES:
            raise ValueError("user_agent exceeds the reviewed byte ceiling")
        if any(ord(value) < 0x20 or ord(value) == 0x7F for value in self.user_agent):
            raise ValueError("user_agent must not contain control characters")

    def engine_scope_kwargs(self) -> dict[str, object]:
        """Bind the pure engine scope to this exact transport envelope.

        Keeping this as plain keyword data avoids importing the sibling engine
        or creating an execution path.  A future reviewed caller must still
        explicitly construct and validate the scope before reconciling a run.
        """

        return {
            "selection_start_date": self.window.start_date,
            "selection_end_date": self.window.end_date,
            "page_size": self.limits.page_size,
            "page_record_cap": self.limits.max_page_records,
            "page_cap": self.limits.page_cap,
            "per_page_byte_cap": self.limits.max_response_bytes,
            "total_byte_cap": self.limits.max_total_response_bytes,
            "record_cap": self.limits.max_records,
            "record_byte_cap": self.limits.max_record_bytes,
            "token_byte_cap": self.limits.max_token_bytes,
            "string_byte_cap": self.limits.max_string_bytes,
            "json_depth_cap": self.limits.max_json_depth,
            "json_node_cap": self.limits.max_json_nodes,
            "json_container_item_cap": self.limits.max_container_items,
        }


@dataclass(frozen=True)
class DiscoveryResponse:
    """One already-received, identity-encoded transport response.

    The walker deliberately accepts bytes only.  It does not decompress, follow
    redirects, retry, or create a session; a future activation review must own
    those concerns separately.
    """

    status_code: int
    headers: Mapping[str, str]
    body: bytes


class DiscoveryTransport(Protocol):
    """Narrow injected transport boundary; no default network implementation exists."""

    def get(
        self,
        path: str,
        *,
        params: tuple[tuple[str, str], ...],
        headers: Mapping[str, str],
    ) -> DiscoveryResponse: ...


@dataclass(frozen=True)
class DiscoveryCounters:
    """Exact bounded work counters; response bytes include the two version probes."""

    pages_attempted: int
    pages_accepted: int
    records_seen: int
    response_bytes: int
    decoded_json_bytes: int
    version_probes: int


@dataclass(frozen=True)
class DiscoveryCandidate:
    """Minimal source-native discovery output; no full study document is retained."""

    nct_id: str
    selection_field_date: str
    canonical_study_sha256: str


@dataclass(frozen=True)
class DiscoverySourceVersion:
    """The source dataset clock, never an event or selection-field clock."""

    data_timestamp_raw: str
    api_version: str
    retrieved_at: str

    def engine_payload(self) -> dict[str, str]:
        return {
            "data_timestamp_raw": self.data_timestamp_raw,
            "api_version": self.api_version,
            "retrieved_at": self.retrieved_at,
        }


@dataclass(frozen=True)
class DiscoveryPage:
    """Bounded page metadata and minimal records for the pure engine boundary."""

    page_ordinal: int
    response_sha256: str
    byte_count: int
    received_at: str
    request_page_token_sha256: str | None
    next_page_token_sha256: str | None
    total_count: int
    records: tuple[DiscoveryCandidate, ...]

    def engine_payload(self) -> dict[str, object]:
        return {
            "page_ordinal": self.page_ordinal,
            "response_sha256": self.response_sha256,
            "byte_count": self.byte_count,
            "received_at": self.received_at,
            "request_page_token_sha256": self.request_page_token_sha256,
            "next_page_token_sha256": self.next_page_token_sha256,
            "total_count": self.total_count,
            "records": [
                {
                    "nct_id": item.nct_id,
                    "canonical_content_sha256": item.canonical_study_sha256,
                    "last_update_posted_date": item.selection_field_date,
                }
                for item in self.records
            ],
        }


@dataclass(frozen=True)
class DiscoveryAdapterBatch:
    """Small explicit handoff for a later pure discovery-control engine.

    This is a data-only boundary, intentionally not a storage/publication hook.
    ``coverage_scope`` describes only this source query attempt; it never claims
    a global ClinicalTrials.gov universe, historical completeness, deletion, or
    event time.
    """

    source_id: str
    mode: str
    api_root: str
    request_path: str
    selection_field: str
    selection_start_date: str
    selection_end_date: str
    source_dataset_timestamp: str
    retrieved_at: str
    coverage_scope: str
    candidates: tuple[DiscoveryCandidate, ...]


@dataclass(frozen=True)
class DiscoverySuccess:
    state: str
    query_params: tuple[tuple[str, str], ...]
    source_dataset_timestamp: str
    source_api_version: str
    source_version_before: DiscoverySourceVersion
    source_version_after: DiscoverySourceVersion
    retrieval_started_at: str
    retrieval_finished_at: str
    counters: DiscoveryCounters
    candidates: tuple[DiscoveryCandidate, ...]
    pages: tuple[DiscoveryPage, ...]

    def adapter_batch(self) -> DiscoveryAdapterBatch:
        """Return the only supported downstream handoff for this dark harness."""

        return DiscoveryAdapterBatch(
            source_id=DISCOVERY_SOURCE_ID,
            mode=DISCOVERY_MODE,
            api_root=API_ROOT,
            request_path=DISCOVERY_REQUEST_PATH,
            selection_field=DISCOVERY_SELECTION_FIELD,
            selection_start_date=_selection_date_from_params(self.query_params, 0),
            selection_end_date=_selection_date_from_params(self.query_params, 1),
            source_dataset_timestamp=self.source_dataset_timestamp,
            retrieved_at=self.retrieval_finished_at,
            coverage_scope=(
                "bounded current-state source query only; not a global or historical "
                "ClinicalTrials.gov completeness claim"
            ),
            candidates=self.candidates,
        )

    def engine_reconciliation_inputs(
        self,
    ) -> tuple[tuple[dict[str, object], ...], dict[str, str], dict[str, str]]:
        """Expose only the sibling engine's declared no-I/O reconciliation shape.

        The engine owns scope/run/coverage contracts and any future durable
        consumer.  This harness owns merely validated, token-redacted source
        pages and before/after source-version observations.
        """

        return (
            tuple(item.engine_payload() for item in self.pages),
            self.source_version_before.engine_payload(),
            self.source_version_after.engine_payload(),
        )


@dataclass(frozen=True)
class DiscoveryQuarantine:
    """One bounded failure result.  It never carries partial records or raw input."""

    state: str
    error_code: str
    query_params: tuple[tuple[str, str], ...]
    retrieval_started_at: str
    retrieval_finished_at: str
    counters: DiscoveryCounters
    candidates: tuple[()] = ()


DiscoveryResult = DiscoverySuccess | DiscoveryQuarantine


@dataclass
class _MutableCounters:
    pages_attempted: int = 0
    pages_accepted: int = 0
    records_seen: int = 0
    response_bytes: int = 0
    decoded_json_bytes: int = 0
    version_probes: int = 0

    def freeze(self) -> DiscoveryCounters:
        return DiscoveryCounters(
            pages_attempted=self.pages_attempted,
            pages_accepted=self.pages_accepted,
            records_seen=self.records_seen,
            response_bytes=self.response_bytes,
            decoded_json_bytes=self.decoded_json_bytes,
            version_probes=self.version_probes,
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("clock must return timezone-aware datetimes")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _require_date(value: object, label: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError(f"{label} must be an ISO calendar date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO calendar date") from exc


def discovery_base_query_params(config: DiscoveryConfig) -> tuple[tuple[str, str], ...]:
    """Return the source's deterministic, bounded discovery query.

    Page tokens are deliberately excluded here and can only be appended by the
    walker after validating a prior page.
    """

    return (
        ("filter.advanced", config.window.advanced_filter),
        ("fields", DISCOVERY_FIELDS_PARAM),
        ("format", "json"),
        ("pageSize", str(config.limits.page_size)),
        ("countTotal", "true"),
    )


def _selection_date_from_params(params: tuple[tuple[str, str], ...], index: int) -> str:
    advanced = dict(params).get("filter.advanced", "")
    match = re.fullmatch(
        r"AREA\[LastUpdatePostDate\]RANGE\[([0-9]{4}-[0-9]{2}-[0-9]{2}),"
        r"([0-9]{4}-[0-9]{2}-[0-9]{2})\]",
        advanced,
    )
    if match is None:
        raise RuntimeError("discovery query invariant violated")
    return match.group(index + 1)


class ClinicalTrialsDiscoveryWalker:
    """Walk a bounded discovery query through an injected, hermetic transport."""

    def __init__(
        self,
        *,
        config: DiscoveryConfig,
        transport: DiscoveryTransport,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.config = config
        self.transport = transport
        self.now_fn = now_fn
        self._last_clock_value: datetime | None = None
        self.request_headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": config.user_agent,
        }

    def walk(self) -> DiscoveryResult:
        """Return a complete candidate batch or one empty quarantine result.

        This method neither raises source faults to callers nor exposes partially
        collected records.  Unexpected transport/fake failures are likewise
        quarantined using a fixed code without retaining exception text.
        """

        self._last_clock_value = None
        started_clock = self._clock_now()
        started = _iso(started_clock)
        query_params = discovery_base_query_params(self.config)
        counters = _MutableCounters()
        try:
            version_before = self._fetch_version(counters)
            candidates_by_id: dict[str, DiscoveryCandidate] = {}
            accepted_pages: list[DiscoveryPage] = []
            seen_page_hashes: set[str] = set()
            seen_token_hashes: set[str] = set()
            expected_total: int | None = None
            token: str | None = None
            terminal = False

            for ordinal in range(self.config.limits.page_cap):
                counters.pages_attempted += 1
                params = query_params if token is None else (*query_params, ("pageToken", token))
                page = self._fetch_page(params=params, counters=counters, ordinal=ordinal)
                raw_hash = page[0]
                payload = page[1]
                raw_byte_count = page[2]
                received_at = page[3]
                if raw_hash in seen_page_hashes:
                    raise DiscoveryError("DUPLICATE_PAGE_CONTENT", "source page content repeated")
                seen_page_hashes.add(raw_hash)

                total_count = _require_total_count(payload.get("totalCount"))
                if expected_total is None:
                    expected_total = total_count
                    if expected_total > self.config.limits.max_records:
                        raise DiscoveryError("TOTAL_COUNT_CAP_EXCEEDED", "source total exceeds record cap")
                    if expected_total > self.config.limits.page_cap * self.config.limits.page_size:
                        raise DiscoveryError(
                            "TOTAL_COUNT_PAGINATION_CAP_EXCEEDED",
                            "source total cannot fit the configured page envelope",
                        )
                elif total_count != expected_total:
                    raise DiscoveryError("TOTAL_COUNT_MISMATCH", "source total changed between pages")

                studies = payload.get("studies")
                if not isinstance(studies, list):
                    raise DiscoveryError("INVALID_SOURCE_SHAPE", "studies must be a list")
                if len(studies) > self.config.limits.max_page_records:
                    raise DiscoveryError("PAGE_RECORD_CAP_EXCEEDED", "source page exceeds page record cap")
                if counters.records_seen + len(studies) > self.config.limits.max_records:
                    raise DiscoveryError("RECORD_CAP_EXCEEDED", "source records exceed record cap")
                counters.records_seen += len(studies)

                page_records: list[DiscoveryCandidate] = []
                for study in studies:
                    candidate = self._candidate_from_study(study)
                    prior = candidates_by_id.get(candidate.nct_id)
                    if prior is not None:
                        code = (
                            "DUPLICATE_NCT_ID_SAME_PAYLOAD"
                            if prior.canonical_study_sha256 == candidate.canonical_study_sha256
                            else "DUPLICATE_NCT_ID_CONFLICTING_PAYLOAD"
                        )
                        raise DiscoveryError(code, "source returned a duplicate NCT identifier")
                    candidates_by_id[candidate.nct_id] = candidate
                    page_records.append(candidate)

                next_token = _next_token(payload.get("nextPageToken"), self.config.limits)
                accepted_pages.append(
                    DiscoveryPage(
                        page_ordinal=ordinal,
                        response_sha256=raw_hash,
                        byte_count=raw_byte_count,
                        received_at=received_at,
                        request_page_token_sha256=(
                            hashlib.sha256(token.encode("utf-8")).hexdigest()
                            if token is not None
                            else None
                        ),
                        next_page_token_sha256=(
                            hashlib.sha256(next_token.encode("utf-8")).hexdigest()
                            if next_token is not None
                            else None
                        ),
                        total_count=total_count,
                        records=tuple(page_records),
                    )
                )
                if next_token is None:
                    terminal = True
                    if expected_total != counters.records_seen:
                        raise DiscoveryError(
                            "TERMINAL_PAGE_CONTRADICTION",
                            "terminal source page does not reconcile totalCount",
                        )
                    break
                if not studies or counters.records_seen >= expected_total:
                    raise DiscoveryError(
                        "TERMINAL_PAGE_CONTRADICTION",
                        "source supplied a continuation token after terminal evidence",
                    )
                token_hash = hashlib.sha256(next_token.encode("utf-8")).hexdigest()
                if token_hash in seen_token_hashes or next_token == token:
                    raise DiscoveryError("PAGINATION_CYCLE", "source pagination token repeated")
                seen_token_hashes.add(token_hash)
                token = next_token
                counters.pages_accepted += 1
            if not terminal:
                raise DiscoveryError("PAGE_CAP_EXHAUSTED", "source did not reach a terminal page")
            counters.pages_accepted += 1

            version_after = self._fetch_version(counters)
            if (
                version_before.data_timestamp_raw != version_after.data_timestamp_raw
                or version_before.api_version != version_after.api_version
            ):
                raise DiscoveryError("SOURCE_CHANGED_MID_RUN", "source version changed during walk")
            if expected_total is None or expected_total != len(candidates_by_id):
                raise DiscoveryError("TERMINAL_PAGE_CONTRADICTION", "final source count is inconsistent")

            finished_clock = self._clock_now()
            if finished_clock <= started_clock:
                raise DiscoveryError(
                    "NON_MONOTONIC_RETRIEVAL_CLOCK",
                    "successful retrieval must have a positive clock interval",
                )
            finished = _iso(finished_clock)
            return DiscoverySuccess(
                state="complete",
                query_params=query_params,
                source_dataset_timestamp=version_before.data_timestamp_raw,
                source_api_version=version_before.api_version,
                source_version_before=version_before,
                source_version_after=version_after,
                retrieval_started_at=started,
                retrieval_finished_at=finished,
                counters=counters.freeze(),
                candidates=tuple(sorted(candidates_by_id.values(), key=lambda item: item.nct_id)),
                pages=tuple(accepted_pages),
            )
        except DiscoveryError as exc:
            return self._quarantine(
                error_code=exc.code,
                query_params=query_params,
                started=started,
                counters=counters,
            )
        except Exception:
            return self._quarantine(
                error_code="TRANSPORT_OR_HARNESS_FAILURE",
                query_params=query_params,
                started=started,
                counters=counters,
            )

    def _quarantine(
        self,
        *,
        error_code: str,
        query_params: tuple[tuple[str, str], ...],
        started: str,
        counters: _MutableCounters,
    ) -> DiscoveryQuarantine:
        try:
            finished = _iso(self._clock_now())
        except Exception:
            # The primary failure remains authoritative; a broken reporting clock
            # cannot cause an escape from the empty quarantine boundary.
            finished = started
        return DiscoveryQuarantine(
            state="quarantined",
            error_code=error_code,
            query_params=query_params,
            retrieval_started_at=started,
            retrieval_finished_at=finished,
            counters=counters.freeze(),
        )

    def _clock_now(self) -> datetime:
        current = _as_utc(self.now_fn())
        if self._last_clock_value is not None and current < self._last_clock_value:
            raise DiscoveryError(
                "NON_MONOTONIC_RETRIEVAL_CLOCK",
                "retrieval clock moved backwards",
            )
        self._last_clock_value = current
        return current

    def _fetch_version(self, counters: _MutableCounters) -> DiscoverySourceVersion:
        payload, received_at = self._fetch_json(path="/version", params=(), counters=counters)
        counters.version_probes += 1
        timestamp = payload.get("dataTimestamp")
        api_version = payload.get("apiVersion")
        if not isinstance(timestamp, str) or not _VERSION_TIMESTAMP_RE.fullmatch(timestamp):
            raise DiscoveryError("INVALID_SOURCE_VERSION", "invalid source dataTimestamp")
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DiscoveryError("INVALID_SOURCE_VERSION", "invalid source dataTimestamp") from exc
        if not isinstance(api_version, str) or not api_version:
            raise DiscoveryError("INVALID_SOURCE_VERSION", "invalid source apiVersion")
        _check_string(api_version, self.config.limits)
        return DiscoverySourceVersion(
            data_timestamp_raw=timestamp,
            api_version=api_version,
            retrieved_at=received_at,
        )

    def _fetch_page(
        self,
        *,
        params: tuple[tuple[str, str], ...],
        counters: _MutableCounters,
        ordinal: int,
    ) -> tuple[str, Mapping[str, Any], int, str]:
        payload, raw_hash, byte_count, received_at = self._fetch_json(
            path=DISCOVERY_REQUEST_PATH,
            params=params,
            counters=counters,
            page_ordinal=ordinal,
        )
        _check_document_bounds(payload, self.config.limits)
        return raw_hash, payload, byte_count, received_at

    def _fetch_json(
        self,
        *,
        path: str,
        params: tuple[tuple[str, str], ...],
        counters: _MutableCounters,
        page_ordinal: int | None = None,
    ) -> tuple[Mapping[str, Any], str, int, str] | tuple[Mapping[str, Any], str]:
        try:
            response = self.transport.get(path, params=params, headers=self.request_headers)
        except Exception as exc:
            raise DiscoveryError("TRANSPORT_FAILURE", "injected transport rejected request") from exc
        raw = self._validated_response_body(response, counters)
        received_at = _iso(self._clock_now())
        label = path if page_ordinal is None else f"/studies page {page_ordinal}"
        try:
            payload = _exact_json_object(raw, label)
        except CollectionError as exc:
            raise DiscoveryError(exc.code, "source JSON rejected") from exc
        if page_ordinal is None and path == "/version":
            _check_document_bounds(payload, self.config.limits)
            return payload, received_at
        return payload, hashlib.sha256(raw).hexdigest(), len(raw), received_at

    def _validated_response_body(
        self, response: object, counters: _MutableCounters
    ) -> bytes:
        if not isinstance(response, DiscoveryResponse):
            raise DiscoveryError("MALFORMED_TRANSPORT_RESPONSE", "transport returned wrong response type")
        if isinstance(response.status_code, bool) or not isinstance(response.status_code, int):
            raise DiscoveryError("MALFORMED_HTTP_STATUS", "status code is invalid")
        if response.status_code != 200:
            raise DiscoveryError("UNEXPECTED_HTTP_STATUS", "source response is not HTTP 200")
        if not isinstance(response.headers, Mapping) or len(response.headers) > MAX_RESPONSE_HEADERS:
            raise DiscoveryError("MALFORMED_RESPONSE_HEADERS", "response headers are invalid")
        headers: dict[str, str] = {}
        for key, value in response.headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise DiscoveryError("MALFORMED_RESPONSE_HEADERS", "response headers are invalid")
            if any(ord(item) < 0x20 or ord(item) == 0x7F for item in key + value):
                raise DiscoveryError("MALFORMED_RESPONSE_HEADERS", "response headers are invalid")
            if len(key.encode("utf-8")) + len(value.encode("utf-8")) > MAX_RESPONSE_HEADER_BYTES:
                raise DiscoveryError("MALFORMED_RESPONSE_HEADERS", "response headers are invalid")
            headers[key.lower()] = value
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise DiscoveryError("UNEXPECTED_CONTENT_TYPE", "source response is not JSON")
        content_encoding = headers.get("content-encoding", "").strip().lower()
        if content_encoding not in {"", "identity"}:
            raise DiscoveryError("UNSUPPORTED_CONTENT_ENCODING", "source response is encoded")
        declared_length = headers.get("content-length")
        if declared_length is not None and (
            re.fullmatch(r"[0-9]{1,10}", declared_length) is None
            or int(declared_length) > self.config.limits.max_response_bytes
        ):
            raise DiscoveryError("INVALID_CONTENT_LENGTH", "content length is invalid or exceeds cap")
        if not isinstance(response.body, bytes):
            raise DiscoveryError("MALFORMED_RESPONSE_BODY", "source body must be bytes")
        body = response.body
        if len(body) > self.config.limits.max_response_bytes:
            raise DiscoveryError("RESPONSE_BYTE_CAP_EXCEEDED", "source response exceeds cap")
        if declared_length is not None and int(declared_length) != len(body):
            raise DiscoveryError("CONTENT_LENGTH_MISMATCH", "source content length mismatches body")
        if counters.response_bytes + len(body) > self.config.limits.max_total_response_bytes:
            raise DiscoveryError("TOTAL_RESPONSE_BYTE_CAP_EXCEEDED", "source walk exceeds byte cap")
        counters.response_bytes += len(body)
        # Content-Encoding is identity-only, so received and decoded JSON bytes
        # are the same exact quantity.  Keep the latter explicit for consumers.
        counters.decoded_json_bytes += len(body)
        return body

    def _candidate_from_study(self, study: object) -> DiscoveryCandidate:
        if not isinstance(study, Mapping):
            raise DiscoveryError("INVALID_SOURCE_SHAPE", "study must be an object")
        _check_document_bounds(study, self.config.limits)
        try:
            nct_id = study["protocolSection"]["identificationModule"]["nctId"]
            selection_date = study["protocolSection"]["statusModule"]["lastUpdatePostDateStruct"]["date"]
        except (KeyError, TypeError) as exc:
            raise DiscoveryError("MISSING_DISCOVERY_FIELDS", "source study lacks requested discovery fields") from exc
        if not isinstance(nct_id, str) or not _NCT_ID_RE.fullmatch(nct_id):
            raise DiscoveryError("INVALID_NCT_ID", "source NCT identifier is invalid")
        _check_string(nct_id, self.config.limits)
        if not isinstance(selection_date, str):
            raise DiscoveryError("INVALID_SELECTION_DATE", "selection date is invalid")
        _check_string(selection_date, self.config.limits)
        try:
            selected = _require_date(selection_date, "source selection date")
        except ValueError as exc:
            raise DiscoveryError("INVALID_SELECTION_DATE", "selection date is invalid") from exc
        if not _require_date(self.config.window.start_date, "selection start date") <= selected <= _require_date(
            self.config.window.end_date, "selection end date"
        ):
            raise DiscoveryError("SELECTION_DATE_OUT_OF_RANGE", "source selection date is outside query range")
        canonical = canonical_json_bytes(study)
        if len(canonical) > self.config.limits.max_record_bytes:
            raise DiscoveryError("RECORD_BYTE_CAP_EXCEEDED", "source record exceeds cap")
        return DiscoveryCandidate(
            nct_id=nct_id,
            selection_field_date=selection_date,
            canonical_study_sha256=hashlib.sha256(canonical).hexdigest(),
        )


def _require_total_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DiscoveryError("INVALID_TOTAL_COUNT", "source totalCount is invalid")
    return value


def _next_token(value: object, limits: DiscoveryLimits) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise DiscoveryError("INVALID_PAGE_TOKEN", "source page token is invalid")
    encoded = value.encode("utf-8")
    if len(encoded) > limits.max_token_bytes:
        raise DiscoveryError("PAGE_TOKEN_BYTE_CAP_EXCEEDED", "source page token exceeds cap")
    return value


def _check_string(value: str, limits: DiscoveryLimits) -> None:
    if len(value) > limits.max_string_bytes:
        raise DiscoveryError("STRING_BYTE_CAP_EXCEEDED", "source string exceeds cap")
    if len(value.encode("utf-8")) > limits.max_string_bytes:
        raise DiscoveryError("STRING_BYTE_CAP_EXCEEDED", "source string exceeds cap")


def _check_document_bounds(document: object, limits: DiscoveryLimits) -> None:
    """Bound JSON tree traversal before record-level canonicalization/output."""

    stack: list[tuple[object, int]] = [(document, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > limits.max_json_nodes:
            raise DiscoveryError("JSON_NODE_CAP_EXCEEDED", "source JSON has too many nodes")
        if depth > limits.max_json_depth:
            raise DiscoveryError("JSON_DEPTH_CAP_EXCEEDED", "source JSON is too deep")
        if isinstance(value, str):
            _check_string(value, limits)
        elif isinstance(value, Mapping):
            if len(value) > limits.max_container_items:
                raise DiscoveryError("JSON_CONTAINER_CAP_EXCEEDED", "source object has too many fields")
            for key, child in value.items():
                if not isinstance(key, str):
                    raise DiscoveryError("INVALID_SOURCE_SHAPE", "JSON object key is invalid")
                _check_string(key, limits)
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            if len(value) > limits.max_container_items:
                raise DiscoveryError("JSON_CONTAINER_CAP_EXCEEDED", "source array has too many items")
            for child in value:
                stack.append((child, depth + 1))
