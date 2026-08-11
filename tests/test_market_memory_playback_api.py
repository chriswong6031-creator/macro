"""Serving-boundary tests for the private W3A playback catalog."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import pytest

from app import market_memory as api
from engine.neuralweb import market_memory_pit as pit
from engine.neuralweb import market_memory_playback as playback
from engine.neuralweb import market_memory_trusted as trusted
from scripts import initialize_market_memory_w1a as w1a_initializer
from tests.test_market_memory_pit import (
    CAPTURED_AT,
    _api_client,
    _assert_private,
    _fixed_clock,
    _packet,
    _rebuild,
)
from tests.test_market_memory_trusted import _candidate as _trusted_candidate
from tests.test_market_memory_trusted import _capture as _capture_trusted


@pytest.fixture(autouse=True)
def _reset_playback_limits() -> None:
    api._reset_symbol_rate_limit_for_tests()
    yield
    api._reset_symbol_rate_limit_for_tests()


def _catalog_url(packet: dict, **overrides: object) -> str:
    query: dict[str, object] = {
        "subject_id": packet["subject"]["subject_id"],
        "instrument_id": packet["subject"]["instrument_id"],
        "mode": playback.ACTUAL_OUTPUT_MODE,
        "offset": 0,
        "limit": 100,
    }
    query.update(overrides)
    return "/api/market-memory/v1/playback/catalog?" + urlencode(query)


def _stores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, two_packets: bool = False
) -> tuple[dict, dict | None]:
    w1a_root = tmp_path / "w1a"
    trusted_root = tmp_path / "trusted"
    monkeypatch.setenv("MARKET_MEMORY_CONTEXT_STORE_DIR", str(w1a_root))
    monkeypatch.setenv("MARKET_MEMORY_TRUSTED_STORE_DIR", str(trusted_root))
    trusted.initialize_trusted_store(trusted_root)

    first = _packet()
    _fixed_clock(monkeypatch)
    pit.capture_context(w1a_root, first)
    if not two_packets:
        return first, None

    first_event = datetime.fromisoformat(
        first["clocks"]["event_time"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    later_event = (
        (first_event + timedelta(seconds=1))
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    second = _rebuild(first, event_time=later_event)
    _fixed_clock(monkeypatch, CAPTURED_AT + timedelta(seconds=1))
    pit.capture_context(w1a_root, second)
    return first, second


def test_api_catalog_is_private_page_bound_and_resolves_exact_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first, _unused = _stores(monkeypatch, tmp_path)
    client = _api_client()

    response = client.get(_catalog_url(first))

    assert response.status_code == 200
    _assert_private(response)
    payload = response.json()
    assert payload["schema"] == playback.OPERATIONAL_PLAYBACK_CATALOG_SCHEMA
    assert payload["mode"] == playback.ACTUAL_OUTPUT_MODE
    assert payload["selection"]["returned"] == 1
    assert payload["coverage"] == {
        "receipt_index_scan_complete": True,
        "returned_entries_packet_closure_validated": True,
        "off_page_packets_validated": False,
        "captured_opportunity_population_complete": False,
        "historical_coverage_complete": False,
        "cross_store_atomic_snapshot": False,
    }
    assert payload["authority"]["context_only"] is True
    assert payload["authority"]["proposal_weight"] == 0
    assert payload["replay_policy"]["catalog_only"] is True
    assert payload["replay_policy"]["playback_execution_performed"] is False
    assert payload["replay_policy"]["playback_evidence_included"] is False
    assert response.headers["etag"] == f'"{payload["catalog_id"]}"'
    assert response.headers["x-market-memory-catalog-id"] == payload["catalog_id"]
    assert (
        response.headers["x-market-memory-w1a-generation-id"]
        == payload["generations"][0]["generation_id"]
    )
    assert (
        response.headers["x-market-memory-trusted-generation-id"]
        == payload["generations"][1]["generation_id"]
    )

    entry = payload["entries"][0]
    exact = client.get(f"/api/market-memory/v1/context/{entry['context_id']}")
    assert exact.status_code == 200
    assert exact.headers["etag"] == f'"{entry["packet_sha256"]}"'
    assert exact.json()["context"] == first

    serialized = response.text.lower()
    for forbidden in (
        "object_key",
        "source_artifact",
        "/var/lib/",
        '"value"',
        '"label"',
        '"score"',
    ):
        assert forbidden not in serialized


def test_api_catalog_serves_trusted_capture_with_empty_initialized_w1a(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _trusted_candidate(monkeypatch, tmp_path)
    stored = _capture_trusted(candidate)
    w1a_root = tmp_path / "public"
    # Reproduce the production ordering: trusted-v1 already exists while the
    # top-level W1A root is still only a directory with a child profile.
    initialized = w1a_initializer.initialize_w1a_store(w1a_root)
    assert initialized["capture_count"] == 0
    monkeypatch.setenv("MARKET_MEMORY_CONTEXT_STORE_DIR", str(w1a_root))
    monkeypatch.setenv("MARKET_MEMORY_TRUSTED_STORE_DIR", str(candidate.public))
    before = {
        path.relative_to(w1a_root): path.read_bytes()
        for path in w1a_root.rglob("*")
        if path.is_file()
    }

    response = _api_client().get(_catalog_url(stored.packet))

    assert response.status_code == 200
    _assert_private(response)
    payload = response.json()
    assert [row["capture_count"] for row in payload["generations"]] == [0, 1]
    assert payload["selection"]["returned"] == 1
    assert payload["entries"][0]["context_id"] == stored.packet["context_id"]
    assert payload["entries"][0]["capture_provenance"] == [
        {
            "profile": trusted.TRUSTED_STORE_PROFILE,
            "capture_id": stored.capture_receipt["capture_id"],
            "captured_at": stored.capture_receipt["captured_at"],
        }
    ]
    after = {
        path.relative_to(w1a_root): path.read_bytes()
        for path in w1a_root.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_api_catalog_continuation_pins_both_immutable_generations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first, second = _stores(monkeypatch, tmp_path, two_packets=True)
    assert second is not None
    client = _api_client()

    page_one = client.get(_catalog_url(first, limit=1)).json()
    continuation = page_one["selection"]["continuation"]
    assert continuation is not None
    page_two = client.get(
        _catalog_url(
            first,
            offset=continuation["offset"],
            limit=continuation["limit"],
            w1a_generation_id=continuation["w1a_generation_id"],
            trusted_generation_id=continuation["trusted_generation_id"],
        )
    )

    assert page_two.status_code == 200
    _assert_private(page_two)
    payload_two = page_two.json()
    assert payload_two["generations"] == page_one["generations"]
    assert payload_two["selection"]["offset"] == 1
    assert payload_two["selection"]["continuation"] is None
    assert page_one["entries"][0]["query_id"] != payload_two["entries"][0]["query_id"]
    assert page_one["catalog_id"] != payload_two["catalog_id"]


@pytest.mark.parametrize(
    "query",
    [
        {"offset": 1},
        {"w1a_generation_id": "mmgeneration_" + "a" * 64},
        {"unknown": "field"},
        {"offset": "01"},
        {"mode": "operational_pit"},
    ],
)
def test_api_catalog_rejects_nonexact_first_page_queries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    query: dict[str, object],
) -> None:
    first, _unused = _stores(monkeypatch, tmp_path)

    response = _api_client().get(_catalog_url(first, **query))

    assert response.status_code == 400
    _assert_private(response)


def test_api_catalog_rejects_duplicate_query_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first, _unused = _stores(monkeypatch, tmp_path)
    pairs = [
        ("subject_id", first["subject"]["subject_id"]),
        ("subject_id", first["subject"]["subject_id"]),
        ("instrument_id", first["subject"]["instrument_id"]),
        ("mode", playback.ACTUAL_OUTPUT_MODE),
        ("offset", "0"),
        ("limit", "100"),
    ]

    response = _api_client().get(
        "/api/market-memory/v1/playback/catalog?" + urlencode(pairs)
    )

    assert response.status_code == 400
    _assert_private(response)


@pytest.mark.parametrize("status", [401, 403])
def test_api_catalog_auth_fails_before_reader_access(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    first = _packet()

    def forbidden_reader():
        raise AssertionError("playback store must not be opened before entitlement")

    monkeypatch.setattr(api, "_pit_reader", forbidden_reader)
    response = _api_client(denied_status=status).get(_catalog_url(first))

    assert response.status_code == status
    _assert_private(response)


def test_api_catalog_store_failure_is_coarsened_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _packet()

    def broken_reader():
        raise pit.MarketMemoryStoreError("sensitive/private/store/path")

    monkeypatch.setattr(api, "_pit_reader", broken_reader)
    response = _api_client().get(_catalog_url(first))

    assert response.status_code == 503
    assert "sensitive" not in response.text
    assert response.headers["retry-after"] == str(api._SYMBOL_FETCH_BUSY_RETRY_SECONDS)
    _assert_private(response)


def test_api_catalog_has_independent_low_rate_and_concurrency_fences(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first, _unused = _stores(monkeypatch, tmp_path)
    monkeypatch.setattr(api, "_PLAYBACK_USER_LIMIT", 1)
    client = _api_client()

    assert client.get(_catalog_url(first)).status_code == 200
    limited = client.get(_catalog_url(first))
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    _assert_private(limited)

    api._reset_symbol_rate_limit_for_tests()

    class BusySlots:
        def acquire(self, *, blocking: bool) -> bool:
            assert blocking is False
            return False

        def release(self) -> None:
            raise AssertionError("an unacquired playback slot must not be released")

    monkeypatch.setattr(api, "_playback_slots", BusySlots())
    busy = client.get(_catalog_url(first))
    assert busy.status_code == 503
    assert busy.headers["retry-after"] == str(api._SYMBOL_FETCH_BUSY_RETRY_SECONDS)
    _assert_private(busy)


def test_playback_route_is_get_only() -> None:
    route = next(
        row
        for row in api.router.routes
        if row.path == "/api/market-memory/v1/playback/catalog"
    )
    assert route.methods == {"GET"}
