"""Adversarial offline tests for the W1B.3B SPY technical projector."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Self

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, ValidationError

from engine.neuralweb import market_memory_technical_observation as technical
from lib import nyse_calendar

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCHEMA_PATH = (
    ROOT / "contracts/market_memory/spy_daily_price_source_observation.v1.schema.json"
)
SNAPSHOT_SCHEMA_PATH = (
    ROOT / "contracts/market_memory/spy_raw_close_ratio_snapshot.v1.schema.json"
)
AUTHORITY_V1 = {
    "tier": "display",
    "horizon_role": "context",
    "context_only": True,
    "proposal_weight": 0,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "may_trade": False,
    "may_originate": False,
    "may_select_options_candidate": False,
    "may_execute": False,
    "may_write_options_episode": False,
    "may_append_outcome": False,
    "may_train_prophet": False,
}
MANIFEST_MODIFIED = "Mon, 10 Aug 2026 01:37:37 GMT"
SPY_MODIFIED = "Mon, 10 Aug 2026 01:32:56 GMT"


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


def _sessions(*, end: date = date(2026, 8, 7), count: int = 41) -> list[date]:
    output: list[date] = []
    cursor = end
    while len(output) < count:
        if technical.is_frozen_v1_xnys_session(cursor):
            output.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(output))


def _frame(*, sessions: list[date] | None = None) -> pd.DataFrame:
    dates = _sessions() if sessions is None else sessions
    closes = [float(100 + index) for index in range(len(dates))]
    return pd.DataFrame(
        {
            "open": [value - 0.25 for value in closes],
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": pd.Series(
                [1_000_000 + index for index in range(len(dates))], dtype="int64"
            ).array,
            "transactions": pd.Series(
                [10_000 + index for index in range(len(dates))], dtype="int64"
            ).array,
        },
        index=pd.DatetimeIndex(dates, name="date"),
    )


def _parquet_bytes(frame: pd.DataFrame, *, row_group_size: int | None = None) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(
        buffer,
        engine="pyarrow",
        index=True,
        row_group_size=row_group_size,
    )
    return buffer.getvalue()


def _manifest(frame: pd.DataFrame) -> dict:
    first = frame.index[0].date()
    last = frame.index[-1].date()
    gaps = [
        (current.date() - previous.date()).days
        for previous, current in zip(frame.index, frame.index[1:])
    ]
    tickers = [f"T{index:03d}.parquet" for index in range(99)] + ["SPY.parquet"]
    files = sorted([*tickers, "_backfill_state.json"])
    return {
        "dir": "massive_stock_day",
        "count": len(files),
        "files": files,
        "store": {
            "store": "massive_stock_day",
            "n_tickers": len(tickers),
            "latest_date": last.isoformat(),
            "updated_at": "2026-08-10T01:35:00.000000+00:00",
            "coverage": {
                "first_day": first.isoformat(),
                "last_day": last.isoformat(),
                "n_processed_days": len(frame),
                "max_missing_run_weekdays": 0,
                "max_missing_run_weekdays_recent": 0,
                "recent_window_bdays": 90,
                "missing_sample": [],
            },
            "anchor": {
                "ticker": "SPY",
                "first": first.isoformat(),
                "last": last.isoformat(),
                "n_rows": len(frame),
                "max_gap_calendar_days": max(gaps),
            },
        },
    }


def _response(
    *,
    url: str,
    body: bytes,
    content_type: str,
    last_modified: str,
    head: bool = False,
    status: int = 200,
    headers_extra: tuple[tuple[str, str], ...] = (),
) -> technical.HttpResponse:
    return technical.HttpResponse(
        status=status,
        url=url,
        headers=(
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("ETag", f'"{hashlib.md5(body).hexdigest()}"'),
            ("Last-Modified", last_modified),
            *headers_extra,
        ),
        body=b"" if head else body,
    )


def _responses(
    *,
    frame: pd.DataFrame | None = None,
    parquet_body: bytes | None = None,
    manifest: dict | None = None,
) -> list[technical.HttpResponse]:
    source_frame = _frame() if frame is None else frame
    spy_body = _parquet_bytes(source_frame) if parquet_body is None else parquet_body
    manifest_body = _canonical(
        _manifest(source_frame) if manifest is None else manifest
    )
    manifest_response = _response(
        url=technical.MANIFEST_URL,
        body=manifest_body,
        content_type="application/json",
        last_modified=MANIFEST_MODIFIED,
    )
    spy_head = _response(
        url=technical.SPY_PARQUET_URL,
        body=spy_body,
        content_type="application/octet-stream",
        last_modified=SPY_MODIFIED,
        head=True,
    )
    spy_get = replace(spy_head, body=spy_body)
    return [manifest_response, spy_head, spy_get, spy_head, manifest_response]


class ScriptedFetcher:
    def __init__(self, responses: list[technical.HttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str]
    ) -> technical.HttpResponse:
        self.calls.append((method, url, dict(headers)))
        if not self.responses:
            raise AssertionError("unexpected source request")
        return self.responses.pop(0)


def _pinned_sources(**changes: object) -> technical.PinnedTechnicalSources:
    bodies = {
        "canary_identity_config": (
            ROOT / "config/market_memory_canary.v1.json"
        ).read_bytes(),
        "xnys_calendar_module": (ROOT / "lib/nyse_calendar.py").read_bytes(),
        "massive_entitlement_record": (
            ROOT / "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md"
        ).read_bytes(),
        "technical_price_basis_contract": (
            ROOT / "config/market_memory_technical_price_basis.v1.json"
        ).read_bytes(),
    }
    value = technical.PinnedTechnicalSources(
        pinned_commit="1" * 40,
        canary_config_body=bodies["canary_identity_config"],
        calendar_module_body=bodies["xnys_calendar_module"],
        license_record_body=bodies["massive_entitlement_record"],
        price_basis_contract_body=bodies["technical_price_basis_contract"],
        git_blob_oids=tuple(
            (role, _git_blob_oid(body)) for role, body in bodies.items()
        ),
    )
    return replace(value, **changes)


def _inputs(
    *,
    responses: list[technical.HttpResponse] | None = None,
    sources: technical.PinnedTechnicalSources | None = None,
) -> technical.PinnedTechnicalInputs:
    fetcher = ScriptedFetcher(_responses() if responses is None else responses)
    fetched = technical.fetch_current_spy_daily_inputs(fetcher=fetcher)
    assert not fetcher.responses
    return technical.PinnedTechnicalInputs(
        fetched=fetched,
        pinned_sources=_pinned_sources() if sources is None else sources,
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()


def _run_git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _source_repo(path: Path) -> str:
    for repo_path in (
        "config/market_memory_canary.v1.json",
        "lib/nyse_calendar.py",
        "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md",
        "config/market_memory_technical_price_basis.v1.json",
    ):
        target = path / repo_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / repo_path).read_bytes())
    _run_git(path, "init", "-q")
    _run_git(path, "config", "user.email", "market-memory@example.invalid")
    _run_git(path, "config", "user.name", "Market Memory Test")
    _run_git(path, "add", "--", "config", "lib", "research")
    _run_git(path, "commit", "-q", "-m", "fixture")
    return _run_git(path, "rev-parse", "HEAD")


def test_fetcher_enforces_exact_stable_transaction_and_identity_encoding() -> None:
    fetcher = ScriptedFetcher(_responses())
    fetched = technical.fetch_current_spy_daily_inputs(fetcher=fetcher)

    assert [(method, url) for method, url, _ in fetcher.calls] == [
        ("GET", technical.MANIFEST_URL),
        ("HEAD", technical.SPY_PARQUET_URL),
        ("GET", technical.SPY_PARQUET_URL),
        ("HEAD", technical.SPY_PARQUET_URL),
        ("GET", technical.MANIFEST_URL),
    ]
    assert all(
        headers["Accept-Encoding"] == "identity" for _, _, headers in fetcher.calls
    )
    expected_etag = f'"{hashlib.md5(fetched.spy_body).hexdigest()}"'
    assert fetcher.calls[2][2]["If-Match"] == expected_etag
    assert all(
        "If-Match" not in headers
        for index, (_, _, headers) in enumerate(fetcher.calls)
        if index != 2
    )
    assert fetched.manifest_headers == (
        ("content-type", "application/json"),
        ("content-length", str(len(fetched.manifest_body))),
        ("etag", f'"{hashlib.md5(fetched.manifest_body).hexdigest()}"'),
        ("last-modified", MANIFEST_MODIFIED),
    )
    assert fetched.spy_headers[2] == (
        "etag",
        expected_etag,
    )


def test_default_transport_disables_env_credentials_redirects_and_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRaw:
        def __init__(self) -> None:
            self.headers = {"Content-Type": "application/json"}
            self.decode_content = True
            self.read_limit: int | None = None

        def read(self, limit: int) -> bytes:
            self.read_limit = limit
            return b"{}"

    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.url = technical.MANIFEST_URL
            self.raw = FakeRaw()

    class FakeSession:
        def __init__(self) -> None:
            self.trust_env = True
            self.calls: list[tuple[str, str, dict[str, object]]] = []
            self.response = FakeResponse()

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
            self.calls.append((method, url, dict(kwargs)))
            return self.response

    session = FakeSession()
    monkeypatch.setattr(technical.requests, "Session", lambda: session)
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": "MastermindX-MarketMemory/1.0",
    }
    response = technical._default_fetcher("GET", technical.MANIFEST_URL, headers)

    assert session.trust_env is False
    assert session.calls == [
        (
            "GET",
            technical.MANIFEST_URL,
            {
                "headers": headers,
                "allow_redirects": False,
                "stream": True,
                "timeout": (10, 30),
            },
        )
    ]
    assert session.response.raw.decode_content is False
    assert session.response.raw.read_limit == 512 * 1024 + 1
    assert response.body == b"{}"


def test_projection_emits_exact_clock_free_raw_ratio_contract() -> None:
    bundle = technical.project_current_spy_raw_close_ratio(_inputs())
    state = bundle.feature_object["state"]

    assert bundle.source_observation_bytes == _canonical(bundle.source_observation)
    assert bundle.feature_object_bytes == _canonical(bundle.feature_object)
    assert bundle.source_observation["schema"] == technical.SOURCE_OBSERVATION_SCHEMA
    assert bundle.feature_object["schema"] == technical.SNAPSHOT_SCHEMA
    assert bundle.source_observation["session"] == "2026-08-07"
    assert bundle.source_observation["transport_policy"] == {
        "transaction": "get_manifest_head_if_match_get_head_manifest_recheck",
        "https_only": True,
        "canonical_host_and_paths": True,
        "redirects_allowed": False,
        "query_allowed": False,
        "compression_allowed": False,
        "strong_single_part_md5_etag_required": True,
        "conditional_get_if_match_required": True,
    }
    assert set(bundle.source_observation["remote_sources"]) == {
        "publish_manifest",
        "spy_daily_parquet",
    }
    assert set(bundle.source_observation["git_sources"]) == {
        "canary_identity_config",
        "xnys_calendar_module",
        "massive_entitlement_record",
        "technical_price_basis_contract",
    }
    assert state == {
        "feature": "price.raw_close_ratio_20_sessions",
        "lookback_sessions": 20,
        "support_observations": 21,
        "start_session": _sessions()[-21].isoformat(),
        "end_session": "2026-08-07",
        "start_close": 120.0,
        "end_close": 140.0,
        "value": 140.0 / 120.0,
    }
    assert bundle.feature_object["price_basis"] == {
        "basis": "provider_documented_unadjusted_flat_file",
        "source_product": "us_stocks_sip/day_aggs_v1",
        "source_contract_role": "technical_price_basis_contract",
        "source_contract_sha256": (
            "ce0244d9c18e3fdcb621c7ced6e3700cb8cb43ff0952b355b82d0542ed6b1be9"
        ),
        "basis_authenticated_by_shape": False,
        "source_session_scope": (
            "provider_daily_aggregate_eligible_trades_full_market_day"
        ),
        "regular_session_close_authenticated": False,
        "xnys_calendar_dates_only": True,
        "raw_unadjusted": True,
        "split_adjusted": False,
        "dividend_adjusted": False,
        "other_corporate_action_adjusted": False,
        "economic_return": False,
        "corporate_action_status": "not_evaluated",
        "split_detection": False,
    }
    assert bundle.source_observation["authority"] == AUTHORITY_V1
    assert bundle.feature_object["authority"] == AUTHORITY_V1
    assert bundle.feature_object["quality"]["training_eligible"] is False
    assert bundle.feature_object["quality"]["promotion_eligible"] is False
    keys = {key.lower() for key in _all_keys(bundle.feature_object)}
    assert {
        "observed_at",
        "available_at",
        "event_time",
        "measurement_end",
        "label",
        "outcome",
        "forward_return",
        "rank",
        "gate",
        "trade",
    }.isdisjoint(keys)
    assert "price.ret_20d" not in bundle.feature_object_bytes.decode("utf-8")


def test_ids_bind_remote_headers_bodies_and_frozen_git_bodies_not_commit_name() -> None:
    first_inputs = _inputs()
    second_inputs = replace(
        first_inputs,
        pinned_sources=replace(first_inputs.pinned_sources, pinned_commit="2" * 40),
    )
    first = technical.project_current_spy_raw_close_ratio(first_inputs)
    second = technical.project_current_spy_raw_close_ratio(second_inputs)

    assert first.source_observation == second.source_observation
    assert first.feature_object == second.feature_object
    source_core = {
        "profile": technical.PROFILE,
        "session": first.source_observation["session"],
        "remote_sources": first.source_observation["remote_sources"],
        "git_source_sha256": {
            role: item["sha256"]
            for role, item in first.source_observation["git_sources"].items()
        },
    }
    assert first.source_observation["source_observation_id"] == (
        "mmtechsrc_" + hashlib.sha256(_canonical(source_core)).hexdigest()
    )
    feature_core = {
        "source_observation_id": first.source_observation["source_observation_id"],
        "transform_version": technical.TRANSFORM_VERSION,
        "semantic_value": first.feature_object["state"],
    }
    assert first.feature_object["snapshot_id"] == (
        "mmtechsnap_" + hashlib.sha256(_canonical(feature_core)).hexdigest()
    )


@pytest.mark.parametrize(
    ("index", "mutation", "message"),
    [
        (
            0,
            lambda response: replace(
                response,
                url=technical.MANIFEST_URL + "?mutable=1",
            ),
            "canonical URL",
        ),
        (
            0,
            lambda response: replace(
                response,
                headers=tuple(
                    (name, "W/" + value if name == "ETag" else value)
                    for name, value in response.headers
                ),
            ),
            "strong lowercase",
        ),
        (
            2,
            lambda response: replace(
                response,
                headers=(*response.headers, ("Content-Encoding", "gzip")),
            ),
            "forbidden compression",
        ),
        (
            2,
            lambda response: replace(
                response,
                headers=(*response.headers, ("ETag", '"0"' * 16)),
            ),
            "duplicate HTTP headers",
        ),
        (
            2,
            lambda response: replace(response, body=response.body + b"x"),
            "body length",
        ),
    ],
)
def test_transport_rejects_redirect_query_weak_etag_compression_duplicates_and_body_lies(
    index: int,
    mutation,
    message: str,
) -> None:
    responses = _responses()
    responses[index] = mutation(responses[index])
    with pytest.raises(technical.MarketMemoryTechnicalObservationError, match=message):
        technical.fetch_current_spy_daily_inputs(fetcher=ScriptedFetcher(responses))


def test_transport_rejects_spy_race_manifest_race_and_publish_order_inversion() -> None:
    spy_race = _responses()
    after = spy_race[3]
    spy_race[3] = replace(
        after,
        headers=tuple(
            (name, '"00000000000000000000000000000000"' if name == "ETag" else value)
            for name, value in after.headers
        ),
    )
    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="changed"
    ):
        technical.fetch_current_spy_daily_inputs(fetcher=ScriptedFetcher(spy_race))

    manifest_race = _responses()
    changed_body = manifest_race[4].body + b" "
    manifest_race[4] = _response(
        url=technical.MANIFEST_URL,
        body=changed_body,
        content_type="application/json",
        last_modified=MANIFEST_MODIFIED,
    )
    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="changed"
    ):
        technical.fetch_current_spy_daily_inputs(fetcher=ScriptedFetcher(manifest_race))

    wrong_order = _responses()
    old = "Mon, 10 Aug 2026 01:30:00 GMT"
    wrong_order[0] = _response(
        url=technical.MANIFEST_URL,
        body=wrong_order[0].body,
        content_type="application/json",
        last_modified=old,
    )
    wrong_order[4] = wrong_order[0]
    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="predates"
    ):
        technical.fetch_current_spy_daily_inputs(fetcher=ScriptedFetcher(wrong_order))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda manifest: manifest.update(dir="wrong"),
        lambda manifest: manifest["files"].remove("SPY.parquet"),
        lambda manifest: manifest["files"].append("SPY.parquet"),
        lambda manifest: manifest["store"]["anchor"].update(ticker="QQQ"),
        lambda manifest: manifest["store"]["anchor"].update(n_rows=5_000),
        lambda manifest: manifest["store"].update(extra="drift"),
    ],
)
def test_manifest_is_strict_and_spy_anchor_is_mandatory(mutate) -> None:
    frame = _frame()
    manifest = _manifest(frame)
    mutate(manifest)
    if len(manifest["files"]) != manifest["count"]:
        manifest["count"] = len(manifest["files"])
        manifest["store"]["n_tickers"] = manifest["count"] - 1
    responses = _responses(frame=frame, manifest=manifest)
    with pytest.raises(technical.MarketMemoryTechnicalObservationError):
        technical.fetch_current_spy_daily_inputs(fetcher=ScriptedFetcher(responses))


def test_parquet_anchor_parity_and_consecutive_21_sessions_fail_closed() -> None:
    frame = _frame()
    gap_frame = frame.drop(frame.index[-2])
    gap_responses = _responses(frame=gap_frame)
    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="last 21 consecutive"
    ):
        technical.project_current_spy_raw_close_ratio(_inputs(responses=gap_responses))

    manifest = _manifest(frame)
    manifest["store"]["anchor"]["last"] = frame.index[-2].date().isoformat()
    with pytest.raises(technical.MarketMemoryTechnicalObservationError):
        technical.fetch_current_spy_daily_inputs(
            fetcher=ScriptedFetcher(_responses(frame=frame, manifest=manifest))
        )


def test_parquet_preflight_rejects_row_group_and_schema_bombs_before_projection() -> (
    None
):
    frame = _frame()
    row_group_bomb = _parquet_bytes(frame, row_group_size=1)
    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="row-group"
    ):
        technical.project_current_spy_raw_close_ratio(
            _inputs(responses=_responses(frame=frame, parquet_body=row_group_bomb))
        )

    renamed = frame.rename(columns={"close": "adjusted_close"})
    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="columns"
    ):
        technical.project_current_spy_raw_close_ratio(
            _inputs(responses=_responses(frame=renamed))
        )


def test_parquet_values_reject_nonfinite_bad_bars_and_noncanonical_dtypes() -> None:
    for mutate, message in (
        (lambda frame: frame.__setitem__("close", float("nan")), "non-finite"),
        (lambda frame: frame.__setitem__("high", 1.0), "high is below"),
        (lambda frame: frame.__setitem__("volume", -1), "negative"),
        (lambda frame: frame.__setitem__("transactions", 1.5), "physical types"),
    ):
        frame = _frame()
        mutate(frame)
        with pytest.raises(
            technical.MarketMemoryTechnicalObservationError, match=message
        ):
            technical.project_current_spy_raw_close_ratio(
                _inputs(responses=_responses(frame=frame))
            )


def test_historical_rows_are_support_only_and_do_not_change_semantic_state() -> None:
    original = technical.project_current_spy_raw_close_ratio(_inputs())
    changed_frame = _frame()
    changed_frame.iloc[0, changed_frame.columns.get_loc("close")] += 0.5
    changed_frame.iloc[0, changed_frame.columns.get_loc("high")] += 0.5
    changed = technical.project_current_spy_raw_close_ratio(
        _inputs(responses=_responses(frame=changed_frame))
    )

    assert changed.feature_object["state"] == original.feature_object["state"]
    assert (
        changed.source_observation["source_observation_id"]
        != (original.source_observation["source_observation_id"])
    )
    assert changed.feature_object["limitations"]["historical_rows_support_only"] is True
    assert changed.feature_object["limitations"]["historical_rows_operational"] is False


def test_frozen_calendar_has_daily_parity_and_reviewed_digest() -> None:
    calendar_body = (ROOT / "lib/nyse_calendar.py").read_bytes()
    assert hashlib.sha256(calendar_body).hexdigest() == (
        "7c9167fd416babb64c3067ae7e6237615011ad79e26d826e57005486496410ce"
    )
    cursor = date(1962, 1, 1)
    end = date(2100, 12, 31)
    while cursor <= end:
        assert technical.is_frozen_v1_xnys_session(cursor) == nyse_calendar.is_session(
            cursor
        )
        cursor += timedelta(days=1)
    with pytest.raises(technical.MarketMemoryTechnicalObservationError, match="1962"):
        technical.is_frozen_v1_xnys_session(date(2101, 1, 1))


def test_frozen_config_calendar_entitlement_and_authority_reject_drift() -> None:
    valid = _pinned_sources()
    for field, message in (
        ("canary_config_body", "canary identity config"),
        ("calendar_module_body", "calendar module"),
        ("license_record_body", "entitlement record"),
        ("price_basis_contract_body", "price-basis contract"),
    ):
        changed_body = getattr(valid, field) + b"\n"
        roles = dict(valid.git_blob_oids)
        role = {
            "canary_config_body": "canary_identity_config",
            "calendar_module_body": "xnys_calendar_module",
            "license_record_body": "massive_entitlement_record",
            "price_basis_contract_body": "technical_price_basis_contract",
        }[field]
        roles[role] = _git_blob_oid(changed_body)
        changed = replace(
            valid,
            **{
                field: changed_body,
                "git_blob_oids": tuple((name, roles[name]) for name in roles),
            },
        )
        with pytest.raises(
            technical.MarketMemoryTechnicalObservationError, match=message
        ):
            technical.project_current_spy_raw_close_ratio(
                replace(_inputs(), pinned_sources=changed)
            )

    source = (
        ROOT / "engine/neuralweb/market_memory_technical_observation.py"
    ).read_text(encoding="utf-8")
    assert "market_memory.AUTHORITY" not in source
    assert "nyse_calendar.is_session" not in source


def test_git_reader_requires_exact_head_tracked_bytes_and_entitlement_file(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    commit = _source_repo(repository)
    sources = technical.read_pinned_technical_sources(
        repository,
        pinned_commit=commit,
    )
    assert dict(sources.git_blob_oids)["massive_entitlement_record"] == _run_git(
        repository,
        "rev-parse",
        f"{commit}:research/licenses/MASSIVE_ENTITLEMENT_RECORD.md",
    )
    assert dict(sources.git_blob_oids)["technical_price_basis_contract"] == _run_git(
        repository,
        "rev-parse",
        f"{commit}:config/market_memory_technical_price_basis.v1.json",
    )

    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="current"
    ):
        technical.read_pinned_technical_sources(repository, pinned_commit="0" * 40)

    entitlement = repository / "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md"
    entitlement.write_bytes(entitlement.read_bytes() + b"\n")
    with pytest.raises(technical.MarketMemoryTechnicalObservationError, match="differ"):
        technical.read_pinned_technical_sources(repository, pinned_commit=commit)

    entitlement.write_bytes(
        (ROOT / "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md").read_bytes()
    )
    entitlement.unlink()
    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="unavailable"
    ):
        technical.read_pinned_technical_sources(repository, pinned_commit=commit)


def test_build_composes_offline_fetch_with_exact_git_pin(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    commit = _source_repo(repository)
    fetcher = ScriptedFetcher(_responses())
    bundle = technical.build_current_spy_raw_close_ratio(
        repository,
        pinned_commit=commit,
        fetcher=fetcher,
    )
    assert bundle.feature_object["session"] == "2026-08-07"
    assert not fetcher.responses


def test_bundle_validation_reprojects_all_raw_evidence_and_returns_detached_copy() -> (
    None
):
    bundle = technical.project_current_spy_raw_close_ratio(_inputs())
    checked = technical.validate_technical_snapshot_bundle(bundle)
    checked.feature_object["state"]["value"] = 999
    assert bundle.feature_object["state"]["value"] != 999

    tampered = copy.deepcopy(bundle)
    tampered.feature_object["state"]["value"] = 999
    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="noncanonical"
    ):
        technical.validate_technical_snapshot_bundle(tampered)

    rebound = copy.deepcopy(bundle)
    rebound.feature_object["state"]["value"] = 999
    rebound = replace(
        rebound,
        feature_object_bytes=_canonical(rebound.feature_object),
    )
    with pytest.raises(
        technical.MarketMemoryTechnicalObservationError, match="reproduce"
    ):
        technical.validate_technical_snapshot_bundle(rebound)


def test_json_schemas_are_meta_valid_exact_and_reject_semantic_drift() -> None:
    bundle = technical.project_current_spy_raw_close_ratio(_inputs())
    source_schema = json.loads(SOURCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    snapshot_schema = json.loads(SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(source_schema)
    Draft202012Validator.check_schema(snapshot_schema)
    Draft202012Validator(source_schema).validate(bundle.source_observation)
    Draft202012Validator(snapshot_schema).validate(bundle.feature_object)

    promoted = copy.deepcopy(bundle.feature_object)
    promoted["authority"]["may_rank"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(snapshot_schema).validate(promoted)
    adjusted = copy.deepcopy(bundle.feature_object)
    adjusted["price_basis"]["split_adjusted"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(snapshot_schema).validate(adjusted)
    unlicensed = copy.deepcopy(bundle.source_observation)
    del unlicensed["git_sources"]["massive_entitlement_record"]
    with pytest.raises(ValidationError):
        Draft202012Validator(source_schema).validate(unlicensed)


def test_last_modified_format_fixture_is_canonical_utc() -> None:
    parsed = datetime(2026, 8, 10, 1, 37, 37, tzinfo=timezone.utc)
    assert format_datetime(parsed, usegmt=True) == MANIFEST_MODIFIED
