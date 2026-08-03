"""Hermetic capacity and transport tests for the dark CT.gov discovery walker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

import collectors.biocatalyst.clinicaltrials_discovery as discovery_module
from collectors.biocatalyst.clinicaltrials_discovery import (
    DISCOVERY_FIELDS_PARAM,
    MAX_CONTAINER_ITEMS,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_PAGE_CAP,
    MAX_PAGE_SIZE,
    MAX_RECORD_BYTES,
    MAX_RECORDS,
    MAX_RESPONSE_BYTES,
    MAX_STRING_BYTES,
    MAX_TOKEN_BYTES,
    MAX_TOTAL_RESPONSE_BYTES,
    MAX_USER_AGENT_BYTES,
    MAX_WINDOW_DAYS,
    ClinicalTrialsDiscoveryWalker,
    DiscoveryConfig,
    DiscoveryLimits,
    DiscoveryQuarantine,
    DiscoveryResponse,
    DiscoverySuccess,
    DiscoveryWindow,
    discovery_base_query_params,
)
from engine.biocatalyst.discovery import build_discovery_scope, reconcile_discovery_run


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "biocatalyst"
NOW = datetime(2026, 8, 3, 8, 30, tzinfo=timezone.utc)


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


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def _json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _response(
    body: bytes,
    *,
    status_code: int = 200,
    content_type: str = "application/json; charset=utf-8",
    content_encoding: str = "identity",
    content_length: str | None = None,
) -> DiscoveryResponse:
    headers = {"Content-Type": content_type, "Content-Encoding": content_encoding}
    if content_length is not None:
        headers["Content-Length"] = content_length
    return DiscoveryResponse(status_code=status_code, headers=headers, body=body)


def _study(nct_id: str, date_value: str, **extra: Any) -> dict[str, Any]:
    status = {"lastUpdatePostDateStruct": {"date": date_value}} | extra
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id},
            "statusModule": status,
        }
    }


def _config(**limit_overrides: Any) -> DiscoveryConfig:
    limits = DiscoveryLimits(
        page_size=limit_overrides.pop("page_size", 1),
        page_cap=limit_overrides.pop("page_cap", 3),
        max_records=limit_overrides.pop("max_records", 3),
        max_response_bytes=limit_overrides.pop("max_response_bytes", 4_096),
        max_total_response_bytes=limit_overrides.pop("max_total_response_bytes", 16_384),
        max_record_bytes=limit_overrides.pop("max_record_bytes", 4_096),
        max_token_bytes=limit_overrides.pop("max_token_bytes", 128),
        max_string_bytes=limit_overrides.pop("max_string_bytes", 128),
        **limit_overrides,
    )
    return DiscoveryConfig(
        window=DiscoveryWindow("2026-08-01", "2026-08-03"),
        limits=limits,
        user_agent="MastermindX-BioCatalyst/discovery-test (ops@example.invalid)",
    )


def _walker(responses: list[tuple[str, DiscoveryResponse]], **limits: Any) -> tuple[ClinicalTrialsDiscoveryWalker, ScriptedTransport]:
    transport = ScriptedTransport(responses)
    return ClinicalTrialsDiscoveryWalker(config=_config(**limits), transport=transport, now_fn=IncrementingClock()), transport


def _assert_quarantine(result: object, code: str) -> DiscoveryQuarantine:
    assert isinstance(result, DiscoveryQuarantine)
    assert result.state == "quarantined"
    assert result.error_code == code
    assert result.candidates == ()
    return result


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page_size": MAX_PAGE_SIZE + 1},
        {"page_cap": MAX_PAGE_CAP + 1},
        {"max_records": MAX_RECORDS + 1},
        {"page_size": MAX_PAGE_SIZE, "max_page_records": MAX_PAGE_SIZE + 1},
        {
            "max_response_bytes": MAX_RESPONSE_BYTES + 1,
            "max_total_response_bytes": MAX_TOTAL_RESPONSE_BYTES,
        },
        {"max_total_response_bytes": MAX_TOTAL_RESPONSE_BYTES + 1},
        {"max_record_bytes": MAX_RECORD_BYTES + 1},
        {"max_token_bytes": MAX_TOKEN_BYTES + 1},
        {"max_string_bytes": MAX_STRING_BYTES + 1},
        {"max_json_depth": MAX_JSON_DEPTH + 1},
        {"max_json_nodes": MAX_JSON_NODES + 1},
        {"max_container_items": MAX_CONTAINER_ITEMS + 1},
    ],
)
def test_reviewed_hard_ceilings_reject_every_inflatable_discovery_limit(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        DiscoveryLimits(**kwargs)


@pytest.mark.parametrize("user_agent", ["MastermindX\r\nInjected: true", "x" * (MAX_USER_AGENT_BYTES + 1)])
def test_user_agent_is_bounded_and_header_safe(user_agent: str) -> None:
    with pytest.raises(ValueError):
        DiscoveryConfig(window=DiscoveryWindow("2026-08-01", "2026-08-03"), user_agent=user_agent)


def test_window_and_capacity_envelope_reject_invalid_or_unfinishable_config() -> None:
    with pytest.raises(ValueError):
        DiscoveryWindow("2026-08-04", "2026-08-03")
    with pytest.raises(ValueError):
        DiscoveryWindow("2026-08-01", "2026-13-03")
    with pytest.raises(ValueError, match="366-day"):
        DiscoveryWindow("2025-01-01", "2026-01-02")
    assert MAX_WINDOW_DAYS == 366
    with pytest.raises(ValueError, match="page_size multiplied"):
        DiscoveryLimits(page_size=2, page_cap=2, max_records=3)


def test_new_module_has_no_default_network_session_storage_or_publication_entrypoint() -> None:
    source = inspect.getsource(discovery_module)
    assert "import requests" not in source
    assert "requests." not in source
    for forbidden_entrypoint in ("requests", "Session", "publish", "storage", "app", "worker", "main"):
        assert not hasattr(discovery_module, forbidden_entrypoint)
    signature = inspect.signature(ClinicalTrialsDiscoveryWalker)
    assert signature.parameters["transport"].default is inspect.Parameter.empty


def test_exact_pagination_query_adapter_and_replay_are_hermetic_and_deterministic() -> None:
    version = _fixture("ctgov_discovery_version.v1.json")
    first = _fixture("ctgov_discovery_page_1.v1.json")
    second = _fixture("ctgov_discovery_page_2.v1.json")
    responses = [
        ("/version", _response(version, content_length=str(len(version)))),
        ("/studies", _response(first, content_length=str(len(first)))),
        ("/studies", _response(second, content_length=str(len(second)))),
        ("/version", _response(version, content_length=str(len(version)))),
    ]
    walker, transport = _walker(responses)

    result = walker.walk()

    assert isinstance(result, DiscoverySuccess)
    assert result.state == "complete"
    assert result.query_params == (
        ("filter.advanced", "AREA[LastUpdatePostDate]RANGE[2026-08-01,2026-08-03]"),
        ("fields", DISCOVERY_FIELDS_PARAM),
        ("format", "json"),
        ("pageSize", "1"),
        ("countTotal", "true"),
    )
    assert discovery_base_query_params(_config()) == result.query_params
    assert [call[0] for call in transport.calls] == ["/version", "/studies", "/studies", "/version"]
    assert transport.calls[1][1] == result.query_params
    assert transport.calls[2][1] == (*result.query_params, ("pageToken", "fixture-next-token"))
    assert all(call[2]["Accept-Encoding"] == "identity" for call in transport.calls)
    assert [item.nct_id for item in result.candidates] == ["NCT00000001", "NCT00000002"]
    assert [item.selection_field_date for item in result.candidates] == ["2026-08-01", "2026-08-02"]
    assert result.counters.pages_attempted == 2
    assert result.counters.pages_accepted == 2
    assert result.counters.records_seen == 2
    assert result.counters.version_probes == 2
    assert "fixture-next-token" not in repr(result)

    pages, before, after = result.engine_reconciliation_inputs()
    assert list(pages[0]) == [
        "page_ordinal",
        "response_sha256",
        "byte_count",
        "received_at",
        "request_page_token_sha256",
        "next_page_token_sha256",
        "total_count",
        "records",
    ]
    assert pages[0]["records"] == [
        {
            "nct_id": "NCT00000002",
            "canonical_content_sha256": result.pages[0].records[0].canonical_study_sha256,
            "last_update_posted_date": "2026-08-02",
        }
    ]
    assert before == {
        "data_timestamp_raw": "2026-08-03T08:00:00",
        "api_version": "2.0.5",
        "retrieved_at": "2026-08-03T08:30:00.000001Z",
    }
    assert after == {
        "data_timestamp_raw": "2026-08-03T08:00:00",
        "api_version": "2.0.5",
        "retrieved_at": "2026-08-03T08:30:00.000004Z",
    }
    assert "fixture-next-token" not in repr((pages, before, after))
    scope = build_discovery_scope(**walker.config.engine_scope_kwargs())
    assert scope["source_query"] == {
        "api_root": "https://clinicaltrials.gov/api/v2",
        "request_path": "/studies",
        "response_format": "json",
        "count_total": True,
        "page_size": walker.config.limits.page_size,
        "page_record_cap": walker.config.limits.max_page_records,
        "page_cap": walker.config.limits.page_cap,
        "per_page_byte_cap": walker.config.limits.max_response_bytes,
        "total_byte_cap": walker.config.limits.max_total_response_bytes,
        "record_cap": walker.config.limits.max_records,
        "record_byte_cap": walker.config.limits.max_record_bytes,
        "token_byte_cap": walker.config.limits.max_token_bytes,
        "string_byte_cap": walker.config.limits.max_string_bytes,
        "json_depth_cap": walker.config.limits.max_json_depth,
        "json_node_cap": walker.config.limits.max_json_nodes,
        "json_container_item_cap": walker.config.limits.max_container_items,
        "minimal_fields": [
            "protocolSection.identificationModule.nctId",
            "protocolSection.statusModule.lastUpdatePostDateStruct.date",
        ],
    }
    reconciled = reconcile_discovery_run(
        scope=scope,
        run_id="ctgov_discovery_run_hermetic_integration",
        pages=pages,
        source_version_before=before,
        source_version_after=after,
        started_at=result.retrieval_started_at,
        finished_at=result.retrieval_finished_at,
        transaction_from=result.retrieval_finished_at,
    )
    assert reconciled["run_state"] == "complete"
    assert reconciled["scope"] == scope
    assert [row["nct_id"] for row in reconciled["deduplicated_records"]] == [
        "NCT00000001",
        "NCT00000002",
    ]
    batch = result.adapter_batch()
    assert batch.candidates == result.candidates
    assert "not a global" in batch.coverage_scope
    assert not hasattr(result, "publish")

    replay, replay_transport = _walker(
        [
            ("/version", _response(version)),
            ("/studies", _response(first)),
            ("/studies", _response(second)),
            ("/version", _response(version)),
        ]
    )
    replayed = replay.walk()
    assert replayed == result
    assert len(replay_transport.calls) == 4


def test_source_version_race_is_quarantined_with_no_partial_candidate_batch() -> None:
    before = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    after = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:01:00"})
    page = _json({"studies": [_study("NCT00000001", "2026-08-01")], "totalCount": 1})
    walker, transport = _walker(
        [("/version", _response(before)), ("/studies", _response(page)), ("/version", _response(after))]
    )

    result = _assert_quarantine(walker.walk(), "SOURCE_CHANGED_MID_RUN")

    assert result.counters.pages_attempted == 1
    assert result.counters.records_seen == 1
    assert [call[0] for call in transport.calls] == ["/version", "/studies", "/version"]


def test_success_path_refuses_a_zero_or_backwards_retrieval_clock() -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    page = _json({"studies": [_study("NCT00000001", "2026-08-01")], "totalCount": 1})
    transport = ScriptedTransport(
        [("/version", _response(version)), ("/studies", _response(page)), ("/version", _response(version))]
    )
    walker = ClinicalTrialsDiscoveryWalker(
        config=_config(),
        transport=transport,
        now_fn=lambda: NOW,
    )

    result = _assert_quarantine(walker.walk(), "NON_MONOTONIC_RETRIEVAL_CLOCK")

    assert result.retrieval_started_at == result.retrieval_finished_at
    assert result.candidates == ()


def test_api_version_only_race_and_invalid_source_version_quarantine() -> None:
    before = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    after = _json({"apiVersion": "2.0.6", "dataTimestamp": "2026-08-03T08:00:00"})
    page = _json({"studies": [_study("NCT00000001", "2026-08-01")], "totalCount": 1})
    walker, _ = _walker(
        [("/version", _response(before)), ("/studies", _response(page)), ("/version", _response(after))]
    )
    _assert_quarantine(walker.walk(), "SOURCE_CHANGED_MID_RUN")

    invalid = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03"})
    walker, _ = _walker([("/version", _response(invalid))])
    _assert_quarantine(walker.walk(), "INVALID_SOURCE_VERSION")


@pytest.mark.parametrize(
    ("study", "code"),
    [
        ({"protocolSection": {"identificationModule": {"nctId": "NCT00000001"}}}, "MISSING_DISCOVERY_FIELDS"),
        (_study("NCT00000001", "2026-08-04"), "SELECTION_DATE_OUT_OF_RANGE"),
    ],
)
def test_missing_or_out_of_scope_source_selection_fields_quarantine(study: dict[str, Any], code: str) -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    page = _json({"studies": [study], "totalCount": 1})
    walker, _ = _walker([("/version", _response(version)), ("/studies", _response(page))])

    _assert_quarantine(walker.walk(), code)


@pytest.mark.parametrize(
    ("first_study", "second_study", "code"),
    [
        (
            _study("NCT00000001", "2026-08-01"),
            _study("NCT00000001", "2026-08-01"),
            "DUPLICATE_NCT_ID_SAME_PAYLOAD",
        ),
        (
            _study("NCT00000001", "2026-08-01"),
            _study("NCT00000001", "2026-08-02"),
            "DUPLICATE_NCT_ID_CONFLICTING_PAYLOAD",
        ),
    ],
)
def test_duplicate_source_native_nct_ids_are_quarantined(
    first_study: dict[str, Any], second_study: dict[str, Any], code: str
) -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    first = _json({"studies": [first_study], "nextPageToken": "next", "totalCount": 2})
    second = _json({"studies": [second_study], "totalCount": 2})
    walker, _ = _walker(
        [("/version", _response(version)), ("/studies", _response(first)), ("/studies", _response(second))]
    )

    _assert_quarantine(walker.walk(), code)


def test_duplicate_page_content_and_total_count_inconsistency_are_quarantined() -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    repeated = _json(
        {"studies": [_study("NCT00000001", "2026-08-01")], "nextPageToken": "loop", "totalCount": 2}
    )
    walker, _ = _walker(
        [("/version", _response(version)), ("/studies", _response(repeated)), ("/studies", _response(repeated))]
    )
    _assert_quarantine(walker.walk(), "DUPLICATE_PAGE_CONTENT")

    first = _json(
        {"studies": [_study("NCT00000001", "2026-08-01")], "nextPageToken": "next", "totalCount": 2}
    )
    changed_total = _json({"studies": [_study("NCT00000002", "2026-08-02")], "totalCount": 3})
    walker, _ = _walker(
        [("/version", _response(version)), ("/studies", _response(first)), ("/studies", _response(changed_total))]
    )
    _assert_quarantine(walker.walk(), "TOTAL_COUNT_MISMATCH")


@pytest.mark.parametrize(
    ("total_count", "limits", "code"),
    [
        (True, {}, "INVALID_TOTAL_COUNT"),
        (-1, {}, "INVALID_TOTAL_COUNT"),
        (4, {"max_records": 3}, "TOTAL_COUNT_CAP_EXCEEDED"),
    ],
)
def test_invalid_or_over_capacity_source_total_count_quarantines(
    total_count: object, limits: dict[str, Any], code: str
) -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    page = _json({"studies": [_study("NCT00000001", "2026-08-01")], "totalCount": total_count})
    walker, _ = _walker([("/version", _response(version)), ("/studies", _response(page))], **limits)

    _assert_quarantine(walker.walk(), code)


def test_pagination_cycle_and_terminal_count_contradiction_are_quarantined() -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    first = _json(
        {"studies": [_study("NCT00000001", "2026-08-01")], "nextPageToken": "loop", "totalCount": 3}
    )
    second = _json(
        {"studies": [_study("NCT00000002", "2026-08-02")], "nextPageToken": "loop", "totalCount": 3}
    )
    walker, _ = _walker(
        [("/version", _response(version)), ("/studies", _response(first)), ("/studies", _response(second))]
    )
    _assert_quarantine(walker.walk(), "PAGINATION_CYCLE")

    terminal_too_early = _json({"studies": [_study("NCT00000001", "2026-08-01")], "totalCount": 2})
    walker, _ = _walker([("/version", _response(version)), ("/studies", _response(terminal_too_early))])
    _assert_quarantine(walker.walk(), "TERMINAL_PAGE_CONTRADICTION")


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (_response(b"{}", status_code=503), "UNEXPECTED_HTTP_STATUS"),
        (_response(b"{}", content_type="text/html"), "UNEXPECTED_CONTENT_TYPE"),
        (_response(b"{}", content_encoding="gzip"), "UNSUPPORTED_CONTENT_ENCODING"),
        (_response(b"{malformed"), "INVALID_SOURCE_JSON"),
        (_response(b'{"apiVersion":"2","apiVersion":"2"}'), "INVALID_SOURCE_JSON"),
    ],
)
def test_transport_and_malformed_payload_faults_quarantine(response: DiscoveryResponse, code: str) -> None:
    walker, _ = _walker([("/version", response)])

    _assert_quarantine(walker.walk(), code)


@pytest.mark.parametrize(
    ("content_length", "code"),
    [("not-a-number", "INVALID_CONTENT_LENGTH"), ("999", "CONTENT_LENGTH_MISMATCH")],
)
def test_content_length_faults_quarantine(content_length: str, code: str) -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    walker, _ = _walker([("/version", _response(version, content_length=content_length))])

    _assert_quarantine(walker.walk(), code)


@pytest.mark.parametrize(
    ("page", "limits", "code"),
    [
        (
            _json({"studies": [_study("NCT00000001", "2026-08-01"), _study("NCT00000002", "2026-08-02")], "totalCount": 2}),
            {},
            "PAGE_RECORD_CAP_EXCEEDED",
        ),
        (
            _json({"studies": [_study("NCT00000001", "2026-08-01", briefTitle="x" * 512)], "totalCount": 1}),
            {"max_record_bytes": 64, "max_string_bytes": 1_024},
            "RECORD_BYTE_CAP_EXCEEDED",
        ),
        (
            _json({"studies": [_study("NCT00000001", "2026-08-01")], "nextPageToken": "too-long", "totalCount": 2}),
            {"max_token_bytes": 3},
            "PAGE_TOKEN_BYTE_CAP_EXCEEDED",
        ),
        (
            _json({"studies": [_study("NCT00000001", "2026-08-01", briefTitle="x" * 129)], "totalCount": 1}),
            {"max_string_bytes": 128},
            "STRING_BYTE_CAP_EXCEEDED",
        ),
    ],
)
def test_page_record_token_and_string_capacity_faults_quarantine(
    page: bytes, limits: dict[str, Any], code: str
) -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    walker, _ = _walker([("/version", _response(version)), ("/studies", _response(page))], **limits)

    _assert_quarantine(walker.walk(), code)


def test_byte_caps_are_checked_before_json_parse_or_downstream_state() -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    oversized_page = b"{" + (b" " * 512) + b"}"
    walker, _ = _walker(
        [("/version", _response(version)), ("/studies", _response(oversized_page))],
        max_response_bytes=256,
        max_total_response_bytes=512,
    )

    result = _assert_quarantine(walker.walk(), "RESPONSE_BYTE_CAP_EXCEEDED")

    assert result.counters.records_seen == 0
    assert result.counters.pages_accepted == 0
    assert result.candidates == ()


def test_cumulative_total_byte_cap_quarantines_before_the_overflow_page_is_accepted() -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    first = _json(
        {"studies": [_study("NCT00000001", "2026-08-01")], "nextPageToken": "next-1", "totalCount": 3}
    )
    second = _json(
        {"studies": [_study("NCT00000002", "2026-08-02")], "nextPageToken": "next-2", "totalCount": 3}
    )
    third = _json({"studies": [_study("NCT00000003", "2026-08-03")], "totalCount": 3})
    walker, _ = _walker(
        [
            ("/version", _response(version)),
            ("/studies", _response(first)),
            ("/studies", _response(second)),
            ("/studies", _response(third)),
        ],
        max_response_bytes=512,
        max_total_response_bytes=512,
    )

    result = _assert_quarantine(walker.walk(), "TOTAL_RESPONSE_BYTE_CAP_EXCEEDED")

    assert result.counters.pages_accepted == 2
    assert result.counters.records_seen == 2


@pytest.mark.parametrize(
    ("page", "limits", "code"),
    [
        (
            _json(
                {
                    "studies": [
                        _study(
                            "NCT00000001",
                            "2026-08-01",
                            deeply_nested={"a": {"b": {"c": {"d": {"e": "x"}}}}},
                        )
                    ],
                    "totalCount": 1,
                }
            ),
            {"max_json_depth": 5},
            "JSON_DEPTH_CAP_EXCEEDED",
        ),
        (
            _json({"studies": [_study("NCT00000001", "2026-08-01")], "totalCount": 1}),
            {"max_json_nodes": 8},
            "JSON_NODE_CAP_EXCEEDED",
        ),
        (
            _json(
                {
                    "studies": [
                        _study("NCT00000001", "2026-08-01", extra_one="a", extra_two="b")
                    ],
                    "totalCount": 1,
                }
            ),
            {"max_container_items": 2},
            "JSON_CONTAINER_CAP_EXCEEDED",
        ),
    ],
)
def test_json_depth_node_and_container_caps_quarantine(
    page: bytes, limits: dict[str, Any], code: str
) -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    walker, _ = _walker([("/version", _response(version)), ("/studies", _response(page))], **limits)

    _assert_quarantine(walker.walk(), code)


def test_zero_result_terminal_page_is_a_complete_empty_discovery_scope() -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    page = _json({"studies": [], "totalCount": 0})
    walker, transport = _walker(
        [("/version", _response(version)), ("/studies", _response(page)), ("/version", _response(version))]
    )

    result = walker.walk()

    assert isinstance(result, DiscoverySuccess)
    assert result.candidates == ()
    assert result.pages[0].records == ()
    assert result.counters.records_seen == 0
    assert [call[0] for call in transport.calls] == ["/version", "/studies", "/version"]


def test_hostile_transport_cannot_make_extra_page_request_after_cap_or_terminal() -> None:
    version = _json({"apiVersion": "2.0.5", "dataTimestamp": "2026-08-03T08:00:00"})
    first = _json(
        {"studies": [_study("NCT00000001", "2026-08-01")], "nextPageToken": "next", "totalCount": 2}
    )
    capped, capped_transport = _walker(
        [("/version", _response(version)), ("/studies", _response(first))], page_cap=1, max_records=2
    )
    _assert_quarantine(capped.walk(), "TOTAL_COUNT_PAGINATION_CAP_EXCEEDED")
    assert [call[0] for call in capped_transport.calls] == ["/version", "/studies"]

    terminal = _json({"studies": [_study("NCT00000001", "2026-08-01")], "totalCount": 1})
    completed, terminal_transport = _walker(
        [("/version", _response(version)), ("/studies", _response(terminal)), ("/version", _response(version))]
    )
    outcome = completed.walk()
    assert isinstance(outcome, DiscoverySuccess)
    assert [call[0] for call in terminal_transport.calls] == ["/version", "/studies", "/version"]
