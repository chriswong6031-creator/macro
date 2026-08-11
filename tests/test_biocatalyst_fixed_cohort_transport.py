"""Hermetic bounded-transport tests for the dark B1S2a fixed-cohort lane.

No test performs real network I/O: every source conversation goes through an
injected fake transport, and the one real requests-based transport is exercised
against a recording fake session with an explicit, test-local gate environment.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path
from typing import Any

import pytest
import requests

import collectors.biocatalyst.clinicaltrials_fixed_cohort as transport_module
from collectors.biocatalyst.clinicaltrials_discovery import DiscoveryResponse
from collectors.biocatalyst.clinicaltrials_fixed_cohort import (
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_MAX_RUN_BYTES,
    FIXED_COHORT_FIELDS_PARAM,
    FIXED_COHORT_TRANSPORT_CONTRACT_ID,
    FIXED_COHORT_TRANSPORT_GATE_ENV,
    MAX_ATTEMPTS,
    MAX_CONNECT_TIMEOUT_SECONDS,
    MAX_READ_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
    MAX_RETRY_BUDGET_SECONDS,
    MAX_RUN_BYTES,
    BoundedFixedCohortHttpTransport,
    ClinicalTrialsFixedCohortTransportRun,
    FixedCohortRunQuarantine,
    FixedCohortRunSuccess,
    FixedCohortTransportError,
    FixedCohortTransportLimits,
    build_fixed_cohort_transport_run,
    fixed_cohort_query_params,
    fixed_cohort_transport_run_semantic_issues,
    read_capped_stream,
    require_transport_gate,
    transport_gate_enabled,
    validate_fixed_cohort_transport_run,
)
from engine.biocatalyst.fixed_cohort import build_fixed_cohort
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    canonical_json_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "biocatalyst"
FIXTURE_PREFIX = "ctgov_fixed_cohort_transport_"
COHORT_NCT_IDS = ["NCT00000001", "NCT00000002", "NCT00000003"]
NOW = datetime(2026, 8, 3, 8, 30, tzinfo=timezone.utc)
GATE_ON = {FIXED_COHORT_TRANSPORT_GATE_ENV: "1"}


class ScriptedTransport:
    """A strict fake: any extra fetch or wrong path is an immediate test fault."""

    def __init__(self, responses: list[tuple[str, DiscoveryResponse]]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, tuple[tuple[str, str], ...], dict[str, str]]] = []

    def get(self, path: str, *, params, headers) -> DiscoveryResponse:
        self.calls.append((path, params, dict(headers)))
        if not self._responses:
            raise AssertionError(f"unexpected extra source fetch for {path}")
        expected_path, response = self._responses.pop(0)
        if path != expected_path:
            raise AssertionError(f"expected {expected_path}, received {path}")
        return response


class IncrementingClock:
    """A deterministic aware clock with a positive retrieval interval."""

    def __init__(self) -> None:
        self._ticks = 0

    def __call__(self) -> datetime:
        value = NOW + timedelta(microseconds=self._ticks)
        self._ticks += 1
        return value


class RecordingResponse:
    """A fake streamed HTTP response that counts its own close calls."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: tuple[bytes, ...] = (),
        close_error: BaseException | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = {"Content-Type": "application/json"} if headers is None else headers
        self._chunks = chunks
        self._close_error = close_error
        self.closes = 0
        self.chunk_sizes: list[int] = []
        self.bytes_yielded = 0

    def iter_content(self, chunk_size: int):
        self.chunk_sizes.append(chunk_size)
        for chunk in self._chunks:
            self.bytes_yielded += len(chunk)
            yield chunk

    def close(self) -> None:
        self.closes += 1
        if self._close_error is not None:
            raise self._close_error


class RecordingSession:
    """A fake session that records exactly how the transport called it."""

    def __init__(self, responses: list[Any]) -> None:
        self.trust_env = True
        self.proxies = {"https": "http://proxy.invalid"}
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append({"url": url, **kwargs})
        if not self._responses:
            raise AssertionError(f"unexpected extra source request for {url}")
        outcome = self._responses.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / f"{FIXTURE_PREFIX}{name}.v1.json").read_bytes()


def _response(
    body: bytes,
    *,
    status_code: int = 200,
    content_type: str = "application/json; charset=utf-8",
    content_encoding: str = "identity",
    content_length: str | None = "exact",
) -> DiscoveryResponse:
    headers = {"Content-Type": content_type, "Content-Encoding": content_encoding}
    if content_length == "exact":
        headers["Content-Length"] = str(len(body))
    elif content_length is not None:
        headers["Content-Length"] = content_length
    return DiscoveryResponse(status_code=status_code, headers=headers, body=body)


def _cohort(nct_ids: list[str] | None = None) -> dict[str, Any]:
    return build_fixed_cohort(
        COHORT_NCT_IDS if nct_ids is None else nct_ids,
        provenance={"kind": "hermetic_fixture", "fixture_id": "ctgov_fixed_cohort_transport"},
        repo_root=ROOT,
    )


def _happy_responses(studies: str = "studies") -> list[tuple[str, DiscoveryResponse]]:
    version = _fixture("version")
    page = _fixture(studies)
    return [
        ("/version", _response(version)),
        ("/studies", _response(page)),
        ("/version", _response(version)),
    ]


def _runner(
    responses: list[tuple[str, DiscoveryResponse]],
    *,
    cohort: dict[str, Any] | None = None,
    limits: FixedCohortTransportLimits | None = None,
) -> tuple[ClinicalTrialsFixedCohortTransportRun, ScriptedTransport]:
    transport = ScriptedTransport(responses)
    runner = ClinicalTrialsFixedCohortTransportRun(
        cohort=_cohort() if cohort is None else cohort,
        transport=transport,
        limits=FixedCohortTransportLimits() if limits is None else limits,
        now_fn=IncrementingClock(),
        repo_root=ROOT,
    )
    return runner, transport


def _assert_quarantine(result: object, code: str) -> FixedCohortRunQuarantine:
    assert isinstance(result, FixedCohortRunQuarantine)
    assert result.state == "quarantined"
    assert result.error_code == code
    assert result.returned_nct_ids == ()
    return result


# ---------------------------------------------------------------------------
# membership authority
# ---------------------------------------------------------------------------


def test_membership_authority_is_the_validated_cohort_and_committed_registry_only() -> None:
    cohort = _cohort()
    runner, transport = _runner(_happy_responses(), cohort=cohort)

    result = runner.run()

    assert isinstance(result, FixedCohortRunSuccess)
    assert runner.requested_nct_ids == tuple(COHORT_NCT_IDS)
    assert runner.query_id == ",".join(COHORT_NCT_IDS)
    assert cohort["source_registry_ref"] == "config/biocatalyst_sources.yml"
    assert result.query_params == (
        ("query.id", ",".join(COHORT_NCT_IDS)),
        ("fields", FIXED_COHORT_FIELDS_PARAM),
        ("format", "json"),
        ("pageSize", "4"),
        ("countTotal", "true"),
    )
    assert fixed_cohort_query_params(cohort) == result.query_params
    assert transport.calls[1][1] == result.query_params
    assert result.returned_nct_ids == tuple(COHORT_NCT_IDS)


def test_page_size_reserves_one_sentinel_slot_without_widening_membership() -> None:
    nct_ids = [f"NCT{value:08d}" for value in range(1, 26)]
    cohort = _cohort(nct_ids)

    params = dict(fixed_cohort_query_params(cohort))
    limits = FixedCohortTransportLimits().json_limits()

    assert params["pageSize"] == "26"
    assert limits.page_size == 26
    assert limits.max_page_records == 25
    assert limits.max_records == 26
    assert cohort["nct_ids"] == nct_ids


def test_an_unvalidated_or_tampered_cohort_is_refused_before_any_request() -> None:
    tampered = _cohort()
    tampered["nct_ids"] = [*COHORT_NCT_IDS, "NCT00000009"]
    transport = ScriptedTransport([])

    with pytest.raises(FixedCohortTransportError) as caught:
        ClinicalTrialsFixedCohortTransportRun(
            cohort=tampered, transport=transport, now_fn=IncrementingClock(), repo_root=ROOT
        )

    assert caught.value.code == "INVALID_FIXED_COHORT"
    assert transport.calls == []


def test_environment_variables_cannot_replace_or_enlarge_the_fixed_cohort(monkeypatch) -> None:
    monkeypatch.setenv("BIOCATALYST_FIXED_COHORT_NCTS", "NCT00000009,NCT00000010")
    monkeypatch.setenv("BIOCATALYST_FIXED_COHORT_QUERY_ID", "NCT00000009")
    monkeypatch.setenv("BIOCATALYST_USER_AGENT", "injected/agent")
    runner, transport = _runner(_happy_responses())

    result = runner.run()

    assert isinstance(result, FixedCohortRunSuccess)
    assert result.requested_nct_ids == tuple(COHORT_NCT_IDS)
    assert result.returned_nct_ids == tuple(COHORT_NCT_IDS)
    assert dict(transport.calls[1][1])["query.id"] == ",".join(COHORT_NCT_IDS)
    assert "NCT00000009" not in json.dumps(result.query_params)


def test_the_only_environment_name_this_module_reads_is_the_activation_gate() -> None:
    source = inspect.getsource(transport_module)
    tree = ast.parse(source)
    biocatalyst_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("BIOCATALYST_")
    }

    assert biocatalyst_literals == {FIXED_COHORT_TRANSPORT_GATE_ENV}
    assert source.count("os.environ") == 1
    assert "os.getenv" not in source


# ---------------------------------------------------------------------------
# transport sequence and reconciliation
# ---------------------------------------------------------------------------


def test_one_run_is_exactly_version_then_one_studies_page_then_version() -> None:
    runner, transport = _runner(_happy_responses())

    result = runner.run()

    assert isinstance(result, FixedCohortRunSuccess)
    assert [call[0] for call in transport.calls] == ["/version", "/studies", "/version"]
    assert all(call[2]["Accept-Encoding"] == "identity" for call in transport.calls)
    assert transport.calls[0][1] == ()
    assert result.counters.version_probes == 2
    assert result.counters.page_requests == 1
    assert result.counters.requests_attempted == 3
    assert result.retrieval_finished_at > result.retrieval_started_at


def test_source_version_must_match_before_and_after_or_the_run_fails_closed() -> None:
    page = _fixture("studies")
    runner, _ = _runner(
        [
            ("/version", _response(_fixture("version"))),
            ("/studies", _response(page)),
            ("/version", _response(_fixture("version_advanced"))),
        ]
    )

    _assert_quarantine(runner.run(), "SOURCE_CHANGED_MID_RUN")


@pytest.mark.parametrize(
    "fixture_name, code",
    [
        ("studies_next_page_token", "NEXT_PAGE_TOKEN_PRESENT"),
        ("studies_duplicate_nct", "DUPLICATE_NCT_ID"),
        ("studies_unrequested_nct", "UNREQUESTED_NCT_ID"),
        ("studies_extra_nct", "RETURNED_RECORD_CAP_EXCEEDED"),
        ("studies_missing_nct", "MISSING_COHORT_MEMBER"),
        ("studies_missing_identifier_field", "MISSING_NCT_ID"),
        ("studies_total_count_mismatch", "TOTAL_COUNT_MISMATCH"),
    ],
)
def test_every_hostile_cohort_response_fails_closed_with_no_records(
    fixture_name: str, code: str
) -> None:
    runner, _ = _runner(_happy_responses(studies=fixture_name))

    result = _assert_quarantine(runner.run(), code)

    assert result.requested_nct_ids == tuple(COHORT_NCT_IDS)
    assert result.counters.requests_attempted == 2
    assert result.counters.version_probes == 1


@pytest.mark.parametrize(
    "kwargs, code",
    [
        ({"status_code": 503}, "UNEXPECTED_HTTP_STATUS"),
        ({"content_type": "text/html"}, "UNEXPECTED_CONTENT_TYPE"),
        ({"content_encoding": "gzip"}, "UNSUPPORTED_CONTENT_ENCODING"),
        ({"content_length": "0x10"}, "INVALID_CONTENT_LENGTH"),
        ({"content_length": "99999"}, "CONTENT_LENGTH_MISMATCH"),
    ],
)
def test_response_envelope_is_identity_encoded_json_with_a_canonical_length(
    kwargs: dict[str, Any], code: str
) -> None:
    runner, _ = _runner([("/version", _response(_fixture("version"), **kwargs))])

    _assert_quarantine(runner.run(), code)


def test_response_and_run_byte_caps_are_hard_bounded() -> None:
    oversized = [
        ("/version", _response(_fixture("version"))),
        ("/studies", _response(_fixture("studies"), content_length=None)),
    ]
    over_response_cap, _ = _runner(
        oversized, limits=FixedCohortTransportLimits(max_response_bytes=100, max_run_bytes=1_000)
    )
    _assert_quarantine(over_response_cap.run(), "RESPONSE_BYTE_CAP_EXCEEDED")

    over_run_cap, _ = _runner(
        _happy_responses(), limits=FixedCohortTransportLimits(max_response_bytes=250, max_run_bytes=300)
    )
    _assert_quarantine(over_run_cap.run(), "RUN_BYTE_CAP_EXCEEDED")


def test_a_failing_injected_transport_never_escapes_the_empty_quarantine_seam() -> None:
    class ExplodingTransport:
        def get(self, path: str, *, params, headers) -> DiscoveryResponse:
            raise RuntimeError("source refused")

    runner = ClinicalTrialsFixedCohortTransportRun(
        cohort=_cohort(), transport=ExplodingTransport(), now_fn=IncrementingClock(), repo_root=ROOT
    )

    _assert_quarantine(runner.run(), "TRANSPORT_FAILURE")


def test_transport_argument_has_no_default_network_implementation() -> None:
    signature = inspect.signature(ClinicalTrialsFixedCohortTransportRun)
    assert signature.parameters["transport"].default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# the real bounded HTTP transport
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "0", "", "true", "yes", "TRUE", "2"])
def test_gate_defaults_to_disabled_and_refuses_all_network_io(value: str | None) -> None:
    environ = {} if value is None else {FIXED_COHORT_TRANSPORT_GATE_ENV: value}

    assert transport_gate_enabled(environ) is False
    with pytest.raises(FixedCohortTransportError) as caught:
        require_transport_gate(environ)
    assert caught.value.code == "TRANSPORT_DISABLED"

    with pytest.raises(FixedCohortTransportError) as constructed:
        BoundedFixedCohortHttpTransport(session=RecordingSession([]), environ=environ)
    assert constructed.value.code == "TRANSPORT_DISABLED"


def test_gate_flipped_off_after_construction_refuses_the_next_request() -> None:
    environ = dict(GATE_ON)
    session = RecordingSession([RecordingResponse(chunks=(b"{}",))])
    transport = BoundedFixedCohortHttpTransport(session=session, environ=environ)
    environ[FIXED_COHORT_TRANSPORT_GATE_ENV] = "0"

    with pytest.raises(FixedCohortTransportError) as caught:
        transport.get("/version", params=(), headers={"Accept": "application/json"})

    assert caught.value.code == "TRANSPORT_DISABLED"
    assert session.calls == []


def test_real_transport_disables_redirects_proxies_and_environment_inheritance() -> None:
    body = _fixture("version")
    response = RecordingResponse(
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        chunks=(body,),
    )
    session = RecordingSession([response])
    transport = BoundedFixedCohortHttpTransport(session=session, environ=dict(GATE_ON))

    received = transport.get("/version", params=(), headers={"Accept": "application/json"})

    assert isinstance(received, DiscoveryResponse)
    assert received.body == body
    assert session.trust_env is False
    assert session.proxies == {}
    call = session.calls[0]
    assert call["url"] == "https://clinicaltrials.gov/api/v2/version"
    assert call["allow_redirects"] is False
    assert call["stream"] is True
    assert call["timeout"] == (MAX_CONNECT_TIMEOUT_SECONDS, MAX_READ_TIMEOUT_SECONDS)
    assert response.closes == 1


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_real_transport_treats_a_redirect_as_a_terminal_failure(status: int) -> None:
    response = RecordingResponse(status_code=status)
    transport = BoundedFixedCohortHttpTransport(
        session=RecordingSession([response]), environ=dict(GATE_ON)
    )

    with pytest.raises(FixedCohortTransportError) as caught:
        transport.get("/version", params=(), headers={})

    assert caught.value.code == "REDIRECT_NOT_ALLOWED"
    assert response.closes == 1


def test_real_transport_refuses_any_path_outside_the_reviewed_conversation() -> None:
    session = RecordingSession([])
    transport = BoundedFixedCohortHttpTransport(session=session, environ=dict(GATE_ON))

    with pytest.raises(FixedCohortTransportError) as caught:
        transport.get("/studies/NCT00000001", params=(), headers={})

    assert caught.value.code == "UNSUPPORTED_REQUEST_PATH"
    assert session.calls == []


def test_streamed_reads_stop_at_the_cap_plus_one_and_trim_hostile_chunks() -> None:
    hostile = RecordingResponse(chunks=(b"x" * 1_000_000, b"y" * 1_000_000))

    body = read_capped_stream(hostile, cap=8)

    assert body == b"x" * 9
    assert hostile.bytes_yielded == 1_000_000

    exact = RecordingResponse(chunks=(b"abc", b"de"))
    assert read_capped_stream(exact, cap=8) == b"abcde"


def test_a_response_over_the_cap_is_rejected_after_a_bounded_read() -> None:
    response = RecordingResponse(chunks=(b"z" * 5_000,))
    transport = BoundedFixedCohortHttpTransport(
        session=RecordingSession([response]),
        limits=FixedCohortTransportLimits(max_response_bytes=1_024, max_run_bytes=2_048),
        environ=dict(GATE_ON),
    )

    with pytest.raises(FixedCohortTransportError) as caught:
        transport.get("/version", params=(), headers={})

    assert caught.value.code == "RESPONSE_BYTE_CAP_EXCEEDED"
    assert response.closes == 1


def test_cumulative_run_bytes_are_bounded_across_requests_of_one_transport() -> None:
    first = RecordingResponse(chunks=(b"a" * 900,))
    second = RecordingResponse(chunks=(b"b" * 900,))
    transport = BoundedFixedCohortHttpTransport(
        session=RecordingSession([first, second]),
        limits=FixedCohortTransportLimits(max_response_bytes=1_024, max_run_bytes=1_500),
        environ=dict(GATE_ON),
    )

    transport.get("/version", params=(), headers={})
    with pytest.raises(FixedCohortTransportError) as caught:
        transport.get("/version", params=(), headers={})

    assert caught.value.code == "RUN_BYTE_CAP_EXCEEDED"
    assert transport.run_bytes == 900
    assert second.closes == 1


def test_every_response_closes_and_a_close_failure_never_masks_the_primary_error() -> None:
    failing_close = RecordingResponse(status_code=404, close_error=OSError("socket already gone"))
    transport = BoundedFixedCohortHttpTransport(
        session=RecordingSession([failing_close]), environ=dict(GATE_ON)
    )

    with pytest.raises(FixedCohortTransportError) as caught:
        transport.get("/version", params=(), headers={})

    assert caught.value.code == "UNEXPECTED_HTTP_STATUS"
    assert failing_close.closes == 1


def test_a_close_failure_on_an_otherwise_clean_read_is_surfaced_not_swallowed() -> None:
    body = _fixture("version")
    response = RecordingResponse(
        headers={"Content-Type": "application/json"},
        chunks=(body,),
        close_error=OSError("socket already gone"),
    )
    transport = BoundedFixedCohortHttpTransport(
        session=RecordingSession([response]), environ=dict(GATE_ON)
    )

    with pytest.raises(FixedCohortTransportError) as caught:
        transport.get("/version", params=(), headers={})

    assert caught.value.code == "RESPONSE_CLOSE_FAILED"
    assert response.closes == 1


def test_retry_attempts_and_budget_are_hard_bounded() -> None:
    sleeps: list[float] = []
    ticks = iter([0.0, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
    retryable = requests.HTTPError("HTTP 503", response=RecordingResponse(status_code=503))
    session = RecordingSession([retryable, retryable, retryable, retryable])
    transport = BoundedFixedCohortHttpTransport(
        session=session,
        sleep_fn=sleeps.append,
        monotonic_fn=lambda: next(ticks),
        environ=dict(GATE_ON),
    )

    with pytest.raises(FixedCohortTransportError) as caught:
        transport.get("/version", params=(), headers={})

    assert caught.value.code == "HTTP_REQUEST_FAILED"
    assert len(session.calls) == MAX_ATTEMPTS
    assert sleeps == [1.0, 2.0]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": MAX_ATTEMPTS + 1},
        {"connect_timeout_seconds": MAX_CONNECT_TIMEOUT_SECONDS + 1},
        {"read_timeout_seconds": MAX_READ_TIMEOUT_SECONDS + 1},
        {"retry_budget_seconds": MAX_RETRY_BUDGET_SECONDS + 1},
        {"max_response_bytes": MAX_RESPONSE_BYTES + 1, "max_run_bytes": MAX_RUN_BYTES},
        {"max_run_bytes": MAX_RUN_BYTES + 1},
        {"max_response_bytes": 4_096, "max_run_bytes": 1_024},
        {"max_attempts": 0},
        {"retry_budget_seconds": 1.0},
    ],
)
def test_reviewed_hard_ceilings_reject_every_inflatable_transport_limit(
    kwargs: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        FixedCohortTransportLimits(**kwargs)


def test_default_limits_sit_at_or_below_every_reviewed_ceiling() -> None:
    limits = FixedCohortTransportLimits()

    assert limits.max_attempts == MAX_ATTEMPTS == 3
    assert limits.connect_timeout_seconds == 10.0
    assert limits.read_timeout_seconds == 45.0
    assert limits.retry_budget_seconds == 120.0
    assert limits.max_response_bytes == DEFAULT_MAX_RESPONSE_BYTES == 3 * 1024 * 1024
    assert limits.max_run_bytes == DEFAULT_MAX_RUN_BYTES == 16 * 1024 * 1024
    assert MAX_RESPONSE_BYTES == 8 * 1024 * 1024
    assert MAX_RUN_BYTES == 64 * 1024 * 1024


# ---------------------------------------------------------------------------
# private run receipt evidence
# ---------------------------------------------------------------------------


def test_complete_run_receipt_is_contract_valid_private_evidence() -> None:
    runner, _ = _runner(_happy_responses())
    result = runner.run()

    document = build_fixed_cohort_transport_run(result, repo_root=ROOT)

    assert ContractRegistry(ROOT).issues(FIXED_COHORT_TRANSPORT_CONTRACT_ID, document) == ()
    assert fixed_cohort_transport_run_semantic_issues(document, repo_root=ROOT) == []
    assert document["run_state"] == "complete"
    assert document["reconciliation_state"] == "exact_fixed_cohort_match"
    assert document["requested_nct_ids"] == COHORT_NCT_IDS
    assert document["returned_nct_ids"] == COHORT_NCT_IDS
    assert document["error_codes"] == []
    assert document["evidence_class"] == "private_run_receipt_only"
    assert document["authority"] == "facts_and_context_only"
    assert document["transport_gate_env"] == FIXED_COHORT_TRANSPORT_GATE_ENV
    assert "scoring" in document["prohibited_uses"]
    assert document["counts"] == {
        "requested_nct_ids": 3,
        "returned_nct_ids": 3,
        "version_probes": 2,
        "page_requests": 1,
    }


def test_receipt_byte_caps_come_from_the_run_that_produced_it() -> None:
    limits = FixedCohortTransportLimits(max_response_bytes=4_096, max_run_bytes=8_192)
    runner, _ = _runner(_happy_responses(), limits=limits)

    document = build_fixed_cohort_transport_run(runner.run(), repo_root=ROOT)

    assert document["byte_counts"]["max_response_bytes"] == 4_096
    assert document["byte_counts"]["max_run_bytes"] == 8_192
    assert document["byte_counts"]["largest_response_bytes"] == len(_fixture("studies"))
    assert document["byte_counts"]["run_bytes"] == (
        2 * len(_fixture("version")) + len(_fixture("studies"))
    )


def test_quarantined_run_receipt_records_the_failure_and_no_membership() -> None:
    runner, _ = _runner(_happy_responses(studies="studies_missing_nct"))
    result = runner.run()

    document = build_fixed_cohort_transport_run(result, repo_root=ROOT)

    assert ContractRegistry(ROOT).issues(FIXED_COHORT_TRANSPORT_CONTRACT_ID, document) == ()
    assert fixed_cohort_transport_run_semantic_issues(document, repo_root=ROOT) == []
    assert document["run_state"] == "quarantined"
    assert document["reconciliation_state"] == "not_reconciled"
    assert document["returned_nct_ids"] == []
    assert document["error_codes"] == ["MISSING_COHORT_MEMBER"]


def _rebind(document: dict[str, Any]) -> dict[str, Any]:
    document["run_id"] = (
        "ctgov_fixed_cohort_transport_run_"
        + canonical_json_sha256(
            {
                key: value
                for key, value in document.items()
                if key not in {"run_id", "run_payload_sha256"}
            }
        )[:24]
    )
    document["run_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in document.items() if key != "run_payload_sha256"}
    )
    return document


def _valid_document() -> dict[str, Any]:
    runner, _ = _runner(_happy_responses())
    return build_fixed_cohort_transport_run(runner.run(), repo_root=ROOT)


def _assert_rejected(document: dict[str, Any], code: str) -> None:
    with pytest.raises(ContractValidationError) as caught:
        validate_fixed_cohort_transport_run(document, repo_root=ROOT)
    assert code in {issue.code for issue in caught.value.issues}


def test_receipt_identity_and_payload_hashes_must_bind_their_own_content() -> None:
    document = _valid_document()
    document["query_id"] = ",".join(COHORT_NCT_IDS[:2])
    _assert_rejected(deepcopy(document), "fixed_cohort_transport.identity")

    tampered = _valid_document()
    tampered["run_payload_sha256"] = "0" * 64
    _assert_rejected(tampered, "fixed_cohort_transport.hash")


def test_a_receipt_may_never_report_membership_the_cohort_did_not_request() -> None:
    document = _valid_document()
    document["returned_nct_ids"] = [*COHORT_NCT_IDS, "NCT00000009"]
    document["counts"]["returned_nct_ids"] = 4

    _assert_rejected(_rebind(document), "fixed_cohort_transport.membership")


def test_a_complete_receipt_may_not_carry_error_codes_or_a_short_return() -> None:
    with_error = _valid_document()
    with_error["error_codes"] = ["MISSING_COHORT_MEMBER"]
    _assert_rejected(_rebind(with_error), "fixed_cohort_transport.error_codes")

    short = _valid_document()
    short["returned_nct_ids"] = COHORT_NCT_IDS[:2]
    short["counts"]["returned_nct_ids"] = 2
    _assert_rejected(_rebind(short), "fixed_cohort_transport.reconciliation")


def test_a_complete_receipt_requires_two_matching_source_versions() -> None:
    drifted = _valid_document()
    drifted["source_version_after"]["data_timestamp_raw"] = "2026-08-04T08:00:00"
    _assert_rejected(_rebind(drifted), "fixed_cohort_transport.source_version")

    absent = _valid_document()
    absent["source_version_before"] = None
    _assert_rejected(_rebind(absent), "fixed_cohort_transport.source_version")


def test_declared_byte_caps_in_a_receipt_may_never_exceed_the_reviewed_ceilings() -> None:
    document = _valid_document()
    document["byte_counts"]["max_response_bytes"] = MAX_RESPONSE_BYTES
    document["byte_counts"]["run_bytes"] = MAX_RUN_BYTES + 1

    with pytest.raises(ContractValidationError):
        validate_fixed_cohort_transport_run(_rebind(document), repo_root=ROOT)


def test_a_quarantined_receipt_may_not_claim_reconciliation() -> None:
    runner, _ = _runner(_happy_responses(studies="studies_duplicate_nct"))
    document = build_fixed_cohort_transport_run(runner.run(), repo_root=ROOT)
    document["reconciliation_state"] = "exact_fixed_cohort_match"

    _assert_rejected(_rebind(document), "fixed_cohort_transport.quarantine")


# ---------------------------------------------------------------------------
# lane boundary
# ---------------------------------------------------------------------------


def test_module_exposes_no_worker_storage_publication_or_route_entrypoint() -> None:
    source = inspect.getsource(transport_module)

    for forbidden in ("publish", "storage", "app", "worker", "main", "router"):
        assert not hasattr(transport_module, forbidden)
    assert "if __name__" not in source
    for forbidden_text in (
        "APIRouter",
        "fastapi",
        "boto3",
        "r2",
        "argparse",
        "open(",
        "write_bytes",
        "write_text",
        "prophet_score",
        "publish_",
    ):
        assert forbidden_text not in source


def test_hostile_fixture_family_is_canonical_json_with_one_terminal_lf() -> None:
    fixtures = sorted(FIXTURE_ROOT.glob(f"{FIXTURE_PREFIX}*.v1.json"))

    assert len(fixtures) >= 9
    for fixture in fixtures:
        raw = fixture.read_bytes()
        assert raw.endswith(b"\n")
        assert not raw[:-1].endswith(b"\n")
        payload = json.loads(raw.decode("utf-8"))
        assert isinstance(payload, dict)
        assert "sponsor" not in raw.decode("utf-8").lower()
