"""Adversarial offline tests for the W1B.5 option-OI availability probe."""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import subprocess
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Any, Self

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from engine.neuralweb import market_memory_option_oi_observation as option_oi

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config/market_memory_option_oi_source.v1.json"
LICENSE_PATH = ROOT / "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md"
PROBE_SCHEMA_PATH = (
    ROOT / "contracts/market_memory/option_oi_probe_receipt.v1.schema.json"
)
SOURCE_SCHEMA_PATH = (
    ROOT / "contracts/market_memory/spy_option_oi_source_observation.v1.schema.json"
)
TOKEN = "unit-secret-token-123456"
COMPLETED_AT = "2026-08-10T19:00:00.123456Z"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _git_blob_oid(body: bytes) -> str:
    framed = f"blob {len(body)}\0".encode("ascii") + body
    return hashlib.sha1(framed).hexdigest()


def _result(
    ticker: str, open_interest: object = 17, *, include_oi: bool = True
) -> dict:
    value: dict[str, Any] = {
        "details": {
            "ticker": ticker,
            "contract_type": "call",
            "shares_per_contract": 100,
        },
        "greeks": {"gamma": 0.01},
    }
    if include_oi:
        value["open_interest"] = open_interest
    return value


def _payload(*, next_url: object = "present") -> dict:
    value: dict[str, Any] = {
        "status": "OK",
        "request_id": "safe-request-id",
        "results": [
            _result("O:SPY260821C00600000", 1_234_567),
            _result("O:SPY1260821P00500000", None),
            _result("O:SPYADJUSTED", include_oi=False),
        ],
    }
    if next_url == "present":
        value["next_url"] = (
            "https://api.massive.com/v3/snapshot/options/SPY?"
            "limit=250&cursor=safe-cursor"
        )
    elif next_url is not ...:
        value["next_url"] = next_url
    return value


def _http_response(
    payload: object | None = None,
    *,
    body: bytes | None = None,
    status: int = 200,
    url: str = option_oi.SOURCE_URL,
    headers_extra: tuple[tuple[str, str], ...] = (),
    completed_at: str = COMPLETED_AT,
) -> option_oi.HttpResponse:
    entity = (
        _canonical(_payload() if payload is None else payload) if body is None else body
    )
    return option_oi.HttpResponse(
        status=status,
        url=url,
        headers=(
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(entity))),
            *headers_extra,
        ),
        body=entity,
        response_body_completed_at=completed_at,
    )


class ScriptedFetcher:
    def __init__(self, response: option_oi.HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
    ) -> option_oi.HttpResponse:
        self.calls.append((method, url, dict(headers)))
        return self.response


def _fetched(
    payload: object | None = None,
    *,
    body: bytes | None = None,
    completed_at: str = COMPLETED_AT,
    headers: tuple[tuple[str, str], ...] | None = None,
) -> option_oi.FetchedOptionOiResponse:
    entity = (
        _canonical(_payload() if payload is None else payload) if body is None else body
    )
    selected = (
        (("content-type", "application/json"), ("content-length", str(len(entity))))
        if headers is None
        else headers
    )
    return option_oi.FetchedOptionOiResponse(
        status=200,
        url=option_oi.SOURCE_URL,
        selected_headers=selected,
        body=entity,
        response_body_completed_at=completed_at,
    )


def _pinned_sources(**changes: object) -> option_oi.PinnedOptionOiSources:
    config_body = CONFIG_PATH.read_bytes()
    license_body = LICENSE_PATH.read_bytes()
    value = option_oi.PinnedOptionOiSources(
        pinned_commit="1" * 40,
        source_config_body=config_body,
        license_record_body=license_body,
        git_blob_oids=(
            ("option_oi_source_config", _git_blob_oid(config_body)),
            ("massive_entitlement_record", _git_blob_oid(license_body)),
        ),
    )
    return replace(value, **changes)


def _inputs(
    payload: object | None = None,
    *,
    fetched: option_oi.FetchedOptionOiResponse | None = None,
    sources: option_oi.PinnedOptionOiSources | None = None,
) -> option_oi.PinnedOptionOiInputs:
    return option_oi.PinnedOptionOiInputs(
        fetched_response=_fetched(payload) if fetched is None else fetched,
        pinned_sources=_pinned_sources() if sources is None else sources,
    )


def _bundle(payload: object | None = None) -> option_oi.OptionOiObservationBundle:
    return option_oi.project_current_spy_option_oi_observation(_inputs(payload))


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        nested = set().union(*(_all_keys(item) for item in value.values()))
        return set(value).union(nested)
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()


def _run_git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_fetch_is_exactly_one_explicit_bearer_first_page_request() -> None:
    fetcher = ScriptedFetcher(_http_response())

    fetched = option_oi.fetch_current_spy_option_oi_response(
        bearer_token=TOKEN,
        fetcher=fetcher,
    )

    assert len(fetcher.calls) == 1
    method, url, headers = fetcher.calls[0]
    assert method == "GET"
    assert url == "https://api.massive.com/v3/snapshot/options/SPY?limit=250"
    assert headers == {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "MastermindX-MarketMemory-OptionOI/1.0",
    }
    assert fetched.body == _http_response().body
    assert fetched.selected_headers == (
        ("content-type", "application/json"),
        ("content-length", str(len(fetched.body))),
    )
    assert TOKEN.encode() not in repr(fetched).encode()


def test_fetcher_rejects_redirect_compression_partial_and_credential_metadata() -> None:
    cases = [
        _http_response(status=302, headers_extra=(("Location", "https://evil.test"),)),
        _http_response(headers_extra=(("Content-Encoding", "gzip"),)),
        _http_response(headers_extra=(("Content-Range", "bytes 0-99/100"),)),
        _http_response(headers_extra=(("Authorization", f"Bearer {TOKEN}"),)),
        _http_response(headers_extra=(("Set-Cookie", "session=secret"),)),
    ]
    for response in cases:
        with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
            option_oi.fetch_current_spy_option_oi_response(
                bearer_token=TOKEN,
                fetcher=ScriptedFetcher(response),
            )


@pytest.mark.parametrize(
    "url",
    [
        "http://api.massive.com/v3/snapshot/options/SPY?limit=250",
        "https://evil.test/v3/snapshot/options/SPY?limit=250",
        "https://api.massive.com/v3/snapshot/options/SPY?limit=249",
        "https://api.massive.com/v3/snapshot/options/SPY?limit=250&apiKey=secret",
        "https://user:pass@api.massive.com/v3/snapshot/options/SPY?limit=250",
        "https://api.massive.com/v3/snapshot/options/SPY?limit=250#fragment",
    ],
)
def test_fetcher_rejects_any_host_path_query_or_userinfo_drift(url: str) -> None:
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.fetch_current_spy_option_oi_response(
            bearer_token=TOKEN,
            fetcher=ScriptedFetcher(_http_response(url=url)),
        )


def test_fetcher_rejects_token_bytes_in_body_url_and_headers() -> None:
    response_with_body_leak = _http_response(
        {"status": "OK", "results": [_result("O:SPYSAFE", 1)], "leak": TOKEN}
    )
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.fetch_current_spy_option_oi_response(
            bearer_token=TOKEN,
            fetcher=ScriptedFetcher(response_with_body_leak),
        )

    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.fetch_current_spy_option_oi_response(
            bearer_token=TOKEN,
            fetcher=ScriptedFetcher(
                _http_response(headers_extra=(("X-Trace", TOKEN),))
            ),
        )

    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.project_current_spy_option_oi_observation(
            _inputs(
                fetched=_fetched(
                    {
                        "status": "OK",
                        "results": [_result("O:SPYSAFE", 1)],
                        "credential": "unknown-secret",
                    }
                )
            )
        )


@pytest.mark.parametrize(
    "body",
    (
        _canonical({**_payload(), "message": TOKEN}).replace(
            b"unit-secret-token-123456", b"unit-secret-tok\\u0065n-123456"
        ),
        _canonical({**_payload(), "api_key": "unknown-secret"}).replace(
            b"api_key", b"api\\u005fkey"
        ),
        _canonical({**_payload(), "message": TOKEN}).replace(
            b"unit-secret-token-123456", b"unit-secret-tok%65n-123456"
        ),
        _canonical(
            {
                **_payload(),
                "message": "".join(f"%25{ord(char):02X}" for char in TOKEN),
            }
        ),
        _canonical(
            {
                **_payload(),
                "message": base64.urlsafe_b64encode(TOKEN.encode()).decode(),
            }
        ),
    ),
)
def test_fetcher_rejects_json_and_percent_escaped_credential_material(
    body: bytes,
) -> None:
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.fetch_current_spy_option_oi_response(
            bearer_token=TOKEN,
            fetcher=ScriptedFetcher(_http_response(body=body)),
        )


def test_offline_projection_rejects_an_escaped_credential_key() -> None:
    body = _canonical({**_payload(), "api_key": "unknown-secret"}).replace(
        b"api_key", b"api\\u005fkey"
    )
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.project_current_spy_option_oi_observation(
            _inputs(fetched=_fetched(body=body))
        )


@pytest.mark.parametrize(
    "token",
    ["", "short", "contains space", "line\nbreak", "é" * 20, None, True],
)
def test_bearer_must_be_explicit_bounded_nonwhitespace_ascii(token: object) -> None:
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.fetch_current_spy_option_oi_response(  # type: ignore[arg-type]
            bearer_token=token,
            fetcher=ScriptedFetcher(_http_response()),
        )


def test_default_transport_disables_ambient_proxy_netrc_redirects_and_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _canonical(_payload())
    observations: dict[str, object] = {}

    class FakeRaw(io.BytesIO):
        def __init__(self) -> None:
            super().__init__(body)
            self.decode_content = True
            self.headers = {
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            }

    class FakeResponse:
        status_code = 200
        url = option_oi.SOURCE_URL
        raw = FakeRaw()

    class FakeSession:
        trust_env = True

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
            observations.update(
                {
                    "trust_env": self.trust_env,
                    "method": method,
                    "url": url,
                    **kwargs,
                }
            )
            return FakeResponse()

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:9999")
    monkeypatch.setenv("NETRC", "/definitely/not/consulted")
    monkeypatch.setattr(option_oi.requests, "Session", FakeSession)

    fetched = option_oi.fetch_current_spy_option_oi_response(bearer_token=TOKEN)

    assert observations["trust_env"] is False
    assert observations["method"] == "GET"
    assert observations["url"] == option_oi.SOURCE_URL
    assert observations["allow_redirects"] is False
    assert observations["stream"] is True
    assert observations["timeout"] == (10, 30)
    assert observations["headers"] == {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "MastermindX-MarketMemory-OptionOI/1.0",
    }
    assert FakeResponse.raw.decode_content is False
    assert fetched.body == body


def test_bounded_raw_reader_rejects_oversize_without_a_second_request() -> None:
    oversized = b"x" * (option_oi.MAX_ENTITY_BYTES + 1)
    fetcher = ScriptedFetcher(_http_response(body=oversized))
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.fetch_current_spy_option_oi_response(
            bearer_token=TOKEN,
            fetcher=fetcher,
        )
    assert len(fetcher.calls) == 1


def test_projection_counts_valid_null_and_absent_without_zero_fill_or_values() -> None:
    bundle = _bundle()
    page = bundle.source_observation["page_observation"]

    assert page == {
        "results_count": 3,
        "unique_vendor_ticker_count": 3,
        "oi_presence_counts": {
            "valid_nonnegative_integer": 1,
            "null": 1,
            "absent": 1,
        },
        "next_url_present": True,
    }
    rendered = bundle.source_observation_bytes
    assert b"1234567" not in rendered
    assert b"O:SPY" not in rendered
    assert b"1234567" in bundle.pinned_inputs.fetched_response.body
    assert b"O:SPY" in bundle.pinned_inputs.fetched_response.body
    assert "observed_at" not in _all_keys(bundle.source_observation)
    assert "open_interest_total" not in _all_keys(bundle.source_observation)
    assert (
        bundle.source_observation["limitations"]["open_interest_values_projected"]
        is False
    )
    assert bundle.source_observation["limitations"]["vendor_tickers_projected"] is False
    assert (
        bundle.source_observation["limitations"]["raw_entity_body_present_in_bundle"]
        is True
    )
    assert (
        bundle.source_observation["limitations"]["raw_entity_body_publicly_exposed"]
        is False
    )


def test_zero_is_valid_but_missing_and_null_are_never_zero_filled() -> None:
    payload = {
        "status": "OK",
        "results": [
            _result("O:SPYZERO", 0),
            _result("O:SPYNULL", None),
            _result("O:SPYMISSING", include_oi=False),
        ],
    }
    counts = _bundle(payload).source_observation["page_observation"][
        "oi_presence_counts"
    ]
    assert counts == {"valid_nonnegative_integer": 1, "null": 1, "absent": 1}


@pytest.mark.parametrize("invalid", [-1, 1.0, True, "1", [], {}])
def test_projection_rejects_invalid_open_interest_types(invalid: object) -> None:
    payload = {"status": "OK", "results": [_result("O:SPYINVALID", invalid)]}
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        _bundle(payload)


def test_projection_requires_at_least_one_valid_oi() -> None:
    payload = {
        "status": "OK",
        "results": [
            _result("O:SPYNULL", None),
            _result("O:SPYMISSING", include_oi=False),
        ],
    }
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        _bundle(payload)


def test_vendor_tickers_are_unique_but_adjusted_roots_are_not_occ_parsed() -> None:
    payload = {
        "status": "OK",
        "results": [
            _result("O:SPY260821C00600000", 1),
            _result("O:SPY1260821C00600000", 2),
            _result("O:SPYADJUSTED", 3),
        ],
    }
    source = _bundle(payload).source_observation
    assert source["page_observation"]["unique_vendor_ticker_count"] == 3
    assert source["identity"] == {
        "status": "unresolved",
        "vendor_tickers_projected": False,
        "permanent_occ_identity_parsed": False,
        "permanent_contract_identity_assigned": False,
        "adjustment_status": "unresolved",
        "multiplier_parsed": False,
        "gex_computed": False,
    }

    payload["results"][2]["details"]["ticker"] = "O:SPY260821C00600000"
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        _bundle(payload)


def test_spy_endpoint_rejects_a_cross_underlying_vendor_result() -> None:
    payload = {
        "status": "OK",
        "results": [_result("O:AAPL260821C00200000", 1)],
    }
    with pytest.raises(
        option_oi.MarketMemoryOptionOiObservationError,
        match="not a SPY vendor ticker",
    ):
        _bundle(payload)


@pytest.mark.parametrize("count", [0, 251])
def test_results_are_bounded_to_one_complete_first_page(count: int) -> None:
    payload = {
        "status": "OK",
        "results": [_result(f"O:SPY{index:03d}", index) for index in range(count)],
    }
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        _bundle(payload)


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b'{"status":"OK","status":"OK","results":[]}',
        (
            b'{"status":"OK","results":[{"details":{"ticker":"O:SPY"},'
            b'"open_interest":NaN}]}'
        ),
        (
            b'{"status":"OK","results":[{"details":{"ticker":"O:SPY"},'
            b'"open_interest":1}],"other":1e999}'
        ),
    ],
)
def test_projection_rejects_malformed_duplicate_and_nonfinite_json(body: bytes) -> None:
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.project_current_spy_option_oi_observation(
            _inputs(fetched=_fetched(body=body))
        )


def test_duplicate_escaped_credential_key_never_appears_in_traceback() -> None:
    escaped_token = TOKEN.replace("e", r"\u0065")
    body = f'{{"{escaped_token}":1,"{escaped_token}":2}}'.encode()

    try:
        option_oi.project_current_spy_option_oi_observation(
            _inputs(fetched=_fetched(body=body))
        )
    except option_oi.MarketMemoryOptionOiObservationError as exc:
        rendered = "".join(traceback.format_exception(exc))
        assert TOKEN not in rendered
        assert exc.__cause__ is None
    else:
        raise AssertionError("duplicate decoded credential key was accepted")


def test_transport_exception_cannot_echo_authorization_in_traceback() -> None:
    def hostile_transport(
        _method: str, _url: str, headers: dict[str, str]
    ) -> option_oi.HttpResponse:
        raise RuntimeError(f"provider failure for {headers['Authorization']}")

    try:
        option_oi.fetch_current_spy_option_oi_response(
            bearer_token=TOKEN,
            fetcher=hostile_transport,
        )
    except option_oi.MarketMemoryOptionOiObservationError as exc:
        rendered = "".join(traceback.format_exception(exc))
        assert TOKEN not in rendered
        assert "Authorization" not in rendered
        assert exc.__cause__ is None
    else:
        raise AssertionError("hostile transport exception was accepted")


def test_projection_rejects_excessive_json_depth() -> None:
    payload = _payload(next_url=...)
    cursor: dict[str, object] = payload
    for _ in range(40):
        child: dict[str, object] = {}
        cursor["nested"] = child
        cursor = child
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        _bundle(payload)


def test_next_url_is_validated_but_only_presence_is_retained() -> None:
    present = _bundle(_payload(next_url="present"))
    absent = _bundle(_payload(next_url=...))
    explicit_null = _bundle(_payload(next_url=None))

    assert present.probe_receipt["pagination"]["next_url_present"] is True
    assert absent.probe_receipt["pagination"]["next_url_present"] is False
    assert explicit_null.probe_receipt["pagination"]["next_url_present"] is False
    assert b"https://api.massive.com/v3/snapshot/options/SPY?" not in (
        present.probe_receipt_bytes
    )
    assert b"safe-cursor" not in present.probe_receipt_bytes
    assert b"safe-cursor" not in present.source_observation_bytes
    assert b"safe-cursor" in present.pinned_inputs.fetched_response.body


@pytest.mark.parametrize(
    "next_url",
    [
        "http://api.massive.com/v3/snapshot/options/SPY?cursor=x",
        "https://evil.test/v3/snapshot/options/SPY?cursor=x",
        "https://api.massive.com/v3/snapshot/options/SPY?cursor=x&apiKey=secret",
        "https://api.massive.com/v3/snapshot/options/SPY?limit=249&cursor=x",
        "https://api.massive.com/v3/snapshot/options/SPY?cursor=x&cursor=y",
        "https://api.massive.com/v3/snapshot/options/SPY?cursor=Bearer%20secret",
        "https://user:pass@api.massive.com/v3/snapshot/options/SPY?cursor=x",
    ],
)
def test_next_url_rejects_credentials_and_continuation_boundary_drift(
    next_url: str,
) -> None:
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        _bundle(_payload(next_url=next_url))


def test_completeness_temporal_and_authority_are_hard_fenced() -> None:
    bundle = _bundle()
    source = bundle.source_observation

    expected_completeness = {
        "page_complete": True,
        "continuation_followed": False,
        "intentionally_bounded": True,
        "chain_complete": False,
        "contract_universe_complete": False,
        "atomic_chain_snapshot_verified": False,
    }
    assert source["completeness"] == expected_completeness
    assert bundle.probe_receipt["pagination"] == {
        "next_url_present": True,
        "next_url_projected": False,
        **expected_completeness,
    }
    assert source["available_at"] == COMPLETED_AT
    assert source["temporal"]["available_at_basis"] == "response_body_completed_at"
    assert source["temporal"]["event_time"] is None
    assert source["temporal"]["measurement_time"] is None
    assert source["temporal"]["freshness"] == "unverifiable"
    assert source["temporal"]["calendar_used"] is False
    assert source["routing"] == {
        "replay_eligible": False,
        "trusted_input_eligible": False,
        "public_api_eligible": False,
        "options_episode_eligible": False,
        "prophet_eligible": False,
    }
    assert all(
        value is False
        for key, value in source["authority"].items()
        if key.startswith("may_")
    )


def test_provider_basis_is_qualitative_and_has_no_measurement_calendar_inference() -> (
    None
):
    source = _bundle().source_observation
    assert source["provider_claim"] == {
        "documentation_url": (
            "https://massive.com/docs/rest/options/snapshots/option-chain-snapshot"
        ),
        "reviewed_at": "2026-08-10",
        "open_interest_basis": "end_of_last_trading_day",
        "classification": "qualitative_only",
        "claim_authenticated_by_response": False,
        "measurement_date_available": False,
        "publication_date_available": False,
        "publication_timestamp_available": False,
        "publication_sla_available": False,
    }
    assert source["temporal"]["expected_measurement_session_inferred"] is False
    assert source["temporal"]["expected_measurement_date_inferred"] is False
    assert "session" not in source
    assert "measurement_date" not in source


def test_ids_are_deterministic_detached_and_commit_independent() -> None:
    first = _bundle()
    second = _bundle()
    alternate_commit = option_oi.project_current_spy_option_oi_observation(
        _inputs(sources=_pinned_sources(pinned_commit="2" * 40))
    )

    assert first.probe_receipt_bytes == second.probe_receipt_bytes
    assert first.source_observation_bytes == second.source_observation_bytes
    assert first.probe_receipt == alternate_commit.probe_receipt
    assert first.source_observation == alternate_commit.source_observation
    assert first.pinned_inputs.pinned_sources.pinned_commit == "1" * 40
    assert alternate_commit.pinned_inputs.pinned_sources.pinned_commit == "2" * 40

    changed_clock = option_oi.project_current_spy_option_oi_observation(
        _inputs(fetched=_fetched(completed_at="2026-08-10T19:00:01.123456Z"))
    )
    assert (
        first.probe_receipt["probe_receipt_id"]
        != changed_clock.probe_receipt["probe_receipt_id"]
    )
    assert (
        first.source_observation["source_observation_id"]
        != changed_clock.source_observation["source_observation_id"]
    )

    detached = first.detached()
    detached.probe_receipt["pagination"]["chain_complete"] = True
    assert first.probe_receipt["pagination"]["chain_complete"] is False


def test_bundle_retains_exact_raw_config_and_license_bytes_and_revalidates() -> None:
    bundle = _bundle()
    validated = option_oi.validate_option_oi_observation_bundle(bundle)

    assert validated.pinned_inputs.fetched_response.body == _fetched().body
    assert (
        validated.pinned_inputs.pinned_sources.source_config_body
        == CONFIG_PATH.read_bytes()
    )
    assert (
        validated.pinned_inputs.pinned_sources.license_record_body
        == LICENSE_PATH.read_bytes()
    )
    assert validated is not bundle
    assert validated.probe_receipt is not bundle.probe_receipt
    assert validated.source_observation is not bundle.source_observation

    tampered = bundle.detached()
    tampered.source_observation["completeness"]["chain_complete"] = True
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.validate_option_oi_observation_bundle(tampered)


def test_pinned_sources_bind_exact_current_git_tip(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    (repository / "config").mkdir(parents=True)
    (repository / "research/licenses").mkdir(parents=True)
    (repository / "config/market_memory_option_oi_source.v1.json").write_bytes(
        CONFIG_PATH.read_bytes()
    )
    (repository / "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md").write_bytes(
        LICENSE_PATH.read_bytes()
    )
    _run_git(repository, "init", "-q")
    _run_git(repository, "config", "user.email", "tests@example.com")
    _run_git(repository, "config", "user.name", "Tests")
    _run_git(repository, "add", "config", "research")
    _run_git(repository, "commit", "-qm", "fixture")
    commit = _run_git(repository, "rev-parse", "HEAD")

    sources = option_oi.read_pinned_option_oi_sources(
        repository,
        pinned_commit=commit,
    )

    assert sources.pinned_commit == commit
    assert sources.source_config_body == CONFIG_PATH.read_bytes()
    assert sources.license_record_body == LICENSE_PATH.read_bytes()
    assert tuple(role for role, _ in sources.git_blob_oids) == (
        "option_oi_source_config",
        "massive_entitlement_record",
    )

    (repository / "config/market_memory_option_oi_source.v1.json").write_text("{}")
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.read_pinned_option_oi_sources(repository, pinned_commit=commit)


def test_source_or_license_drift_fails_before_any_provider_request(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    (repository / "config").mkdir(parents=True)
    (repository / "research/licenses").mkdir(parents=True)
    (repository / "config/market_memory_option_oi_source.v1.json").write_bytes(
        CONFIG_PATH.read_bytes()
    )
    license_path = repository / "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md"
    license_path.write_bytes(LICENSE_PATH.read_bytes())
    _run_git(repository, "init", "-q")
    _run_git(repository, "config", "user.email", "tests@example.com")
    _run_git(repository, "config", "user.name", "Tests")
    _run_git(repository, "add", "config", "research")
    _run_git(repository, "commit", "-qm", "fixture")
    commit = _run_git(repository, "rev-parse", "HEAD")
    license_path.write_text("drifted legal record\n", encoding="utf-8")
    fetcher = ScriptedFetcher(_http_response())

    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.build_current_spy_option_oi_observation(
            repository,
            pinned_commit=commit,
            bearer_token=TOKEN,
            fetcher=fetcher,
        )

    assert fetcher.calls == []


def test_git_subprocess_scopes_safe_directory_to_exact_resolved_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = (tmp_path / "root owned repository").resolve()
    repository.mkdir()
    observed: dict[str, object] = {}

    class Completed:
        stdout = "1" * 40 + "\n"

    def fake_run(command: list[str], **kwargs: object) -> Completed:
        observed["command"] = command
        observed["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr(option_oi.subprocess, "run", fake_run)
    monkeypatch.setenv("GIT_DIR", "/foreign/repository/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/foreign/repository")

    output = option_oi._git(repository, "rev-parse", "HEAD", text=True)

    assert output == "1" * 40 + "\n"
    assert observed["command"] == [
        "git",
        "-c",
        f"safe.directory={repository}",
        "-C",
        str(repository),
        "rev-parse",
        "HEAD",
    ]
    assert "safe.directory=*" not in observed["command"]
    kwargs = dict(observed["kwargs"])
    git_env = kwargs.pop("env")
    assert isinstance(git_env, dict)
    assert not any(key.startswith("GIT_") for key in git_env)
    assert kwargs == {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 30,
    }


def test_frozen_config_and_license_digests_do_not_add_a_new_legal_claim() -> None:
    config_body = CONFIG_PATH.read_bytes()
    license_body = LICENSE_PATH.read_bytes()
    assert hashlib.sha256(config_body).hexdigest() == (
        "f7ae3d0f7c4a3fd41db48a8c7d6263a0e88a52af36943d3f1de40df0c0689898"
    )
    assert hashlib.sha256(license_body).hexdigest() == (
        "82ad971b46d4159739117d3defe19a25a2a24ede45e5e8d28494c5849e757891"
    )
    config = json.loads(config_body)
    assert "license" not in _all_keys(config)
    assert "entitlement" not in _all_keys(config)


def test_schemas_are_valid_and_match_exact_projected_objects() -> None:
    probe_schema = json.loads(PROBE_SCHEMA_PATH.read_text())
    source_schema = json.loads(SOURCE_SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(probe_schema)
    Draft202012Validator.check_schema(source_schema)
    bundle = _bundle()

    Draft202012Validator(
        probe_schema,
        format_checker=FormatChecker(),
    ).validate(bundle.probe_receipt)
    Draft202012Validator(
        source_schema,
        format_checker=FormatChecker(),
    ).validate(bundle.source_observation)

    invalid_probe = copy.deepcopy(bundle.probe_receipt)
    invalid_probe["pagination"]["chain_complete"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(probe_schema).validate(invalid_probe)

    invalid_source = copy.deepcopy(bundle.source_observation)
    invalid_source["routing"]["prophet_eligible"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(source_schema).validate(invalid_source)


def test_receipts_never_retain_bearer_header_next_url_or_credential_bytes() -> None:
    fetcher = ScriptedFetcher(_http_response())
    fetched = option_oi.fetch_current_spy_option_oi_response(
        bearer_token=TOKEN,
        fetcher=fetcher,
    )
    bundle = option_oi.project_current_spy_option_oi_observation(
        option_oi.PinnedOptionOiInputs(fetched, _pinned_sources())
    )
    receipts = bundle.probe_receipt_bytes + bundle.source_observation_bytes

    assert TOKEN.encode() not in receipts
    assert f"Bearer {TOKEN}".encode() not in receipts
    assert b"safe-cursor" not in receipts
    assert b'"Authorization"' not in receipts
    assert b'"next_url"' not in receipts
    assert set(bundle.probe_receipt["response"]["selected_headers"]) <= {
        "content-type",
        "content-length",
    }


def test_content_length_status_provider_status_and_timestamp_are_strict() -> None:
    response = _http_response()
    mismatched_headers = (
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(response.body) + 1)),
    )
    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.fetch_current_spy_option_oi_response(
            bearer_token=TOKEN,
            fetcher=ScriptedFetcher(replace(response, headers=mismatched_headers)),
        )

    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        _bundle({"status": "ERROR", "results": [_result("O:SPYSAFE", 1)]})

    with pytest.raises(option_oi.MarketMemoryOptionOiObservationError):
        option_oi.project_current_spy_option_oi_observation(
            _inputs(fetched=_fetched(completed_at="2026-08-10T19:00:00Z"))
        )


def test_environment_contains_no_implicit_credential_dependency() -> None:
    source = (
        ROOT / "engine/neuralweb/market_memory_option_oi_observation.py"
    ).read_text()
    forbidden = [
        "os.getenv(",
        "os.environ",
        "load_dotenv",
        "netrc(",
        "api_key=",
        "apiKey=",
    ]
    assert all(value not in source for value in forbidden)
