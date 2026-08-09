from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq
import pytest
import yaml

from collectors import tushare_addons as addons
from scripts import collect_tushare_addons as cli

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = ZoneInfo("Asia/Shanghai")
HISTORICAL_NOW = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
LICENSE_REFERENCE = "ab" * 32


@pytest.fixture(autouse=True)
def provision_synthetic_license_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        addons.LICENSE_AUTHORITY_ENV,
        addons.LICENSE_AUTHORITY_GATE_VALUE,
    )
    monkeypatch.setenv(addons.LICENSE_AUTHORITY_REFERENCE_ENV, LICENSE_REFERENCE)


def minute_frame(*, high: float = 10.2, trade_date: str = "2026-08-07") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "600519.SH",
                "trade_time": f"{trade_date} 09:31:00",
                "open": 10.0,
                "close": 10.1,
                "high": high,
                "low": 9.9,
                "vol": 1_000,
                "amount": 10_050,
            },
            {
                "ts_code": "600519.SH",
                "trade_time": f"{trade_date} 09:32:00",
                "open": 10.1,
                "close": 10.15,
                "high": 10.2,
                "low": 10.0,
                "vol": 800,
                "amount": 8_100,
            },
        ]
    )


def minute_clock_frame(clock: str) -> pd.DataFrame:
    frame = minute_frame().iloc[[0]].copy()
    frame.loc[:, "trade_time"] = f"2026-08-07 {clock}"
    return frame


def premarket_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "20260807",
                "ts_code": "000001.SZ",
                "total_share": 19_405_918.20,
                "float_share": 19_405_755.61,
                "pre_close": 10.0,
                "up_limit": 11.0,
                "down_limit": 9.0,
            }
        ]
    )


def auction_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260810",
                "vol": 10_000,
                "price": 10.1,
                "amount": 101_000,
                "pre_close": 10.0,
                "turnover_rate": 0.02,
                "volume_ratio": 1.2,
                "float_share": 19_405_755.61,
            }
        ]
    )


class FakeQuery:
    def __init__(
        self,
        endpoint: str,
        frame: pd.DataFrame,
        *,
        open_by_exchange: dict[str, int] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.frame = frame
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.open_by_exchange = open_by_exchange or {"SSE": 1, "SZSE": 1}

    def __call__(self, api_name: str, **kwargs: object) -> pd.DataFrame | None:
        self.calls.append((api_name, dict(kwargs)))
        if api_name == "trade_cal":
            exchange = str(kwargs["exchange"])
            return pd.DataFrame(
                [
                    {
                        "exchange": exchange,
                        "cal_date": str(kwargs["start_date"]),
                        "is_open": self.open_by_exchange[exchange],
                        "pretrade_date": "20260806",
                    }
                ]
            )
        assert api_name == self.endpoint
        return self.frame.copy()


class SequenceClock:
    def __init__(self, *observations: datetime) -> None:
        self.observations = iter(observations)

    def __call__(self) -> datetime:
        return next(self.observations)


def minute_request() -> addons.PilotRequest:
    return addons.PilotRequest(
        endpoint="stk_mins",
        trade_date="2026-08-07",
        ticker="600519.SH",
        frequency="1min",
    )


def test_plan_is_no_network_no_write_and_blocks_unconfirmed_endpoints(
    tmp_path: Path,
) -> None:
    output = tmp_path / "store"
    plan = addons.pilot_plan(minute_request(), output_root=output)
    assert plan["status"] == "planned_no_network_no_write"
    assert plan["maximum_vendor_calls"] == 3
    assert plan["range_or_bulk_mode"] is False
    assert plan["request"]["ticker"] == "600519.SS"
    assert plan["license_authority_gate"] == {
        "required_for_execute": True,
        "state": "not_evaluated_plan_only",
        "accepted_basis": addons.LICENSE_AUTHORITY_GATE_VALUE,
        "personal_pricing_nonclaim": ("personal_pricing_is_not_a_commercial_use_grant"),
    }
    assert not output.exists()

    for endpoint in ("stk_auction_o", "stk_auction_c"):
        with pytest.raises(addons.CollectionHeld) as held:
            addons.pilot_plan(
                addons.PilotRequest(endpoint=endpoint, trade_date="2026-08-07"),
                output_root=output,
            )
        assert held.value.reason_code.endswith("written_entitlement_confirmation")
    assert not output.exists()


def test_minute_pilot_writes_provenance_receipt_without_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "distinctive-secret-token-never-persist"
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    query = FakeQuery("stk_mins", minute_frame())

    result = addons.collect_pilot(
        minute_request(), output_root=tmp_path, query_fn=query, now=HISTORICAL_NOW
    )

    destination = Path(result.partition_path)
    assert result.status == "written"
    assert destination.relative_to(tmp_path).as_posix() == (
        "stk_mins/by_frequency=1min/by_trade_date=2026-08-07/by_scope=ticker-600519.SS"
    )
    assert {path.name for path in destination.iterdir()} == {
        "part.parquet",
        "receipt.json",
    }
    assert [call[0] for call in query.calls] == ["trade_cal", "trade_cal", "stk_mins"]
    endpoint_params = query.calls[-1][1]
    assert endpoint_params["ts_code"] == "600519.SH"
    assert endpoint_params["freq"] == "1min"
    assert "token" not in endpoint_params

    receipt_bytes = (destination / "receipt.json").read_bytes()
    assert secret.encode() not in receipt_bytes
    receipt = json.loads(receipt_bytes)
    assert receipt["authority"] == "context_display_only"
    access = receipt["access_observation_receipt"]
    assert access["observation"] == "access_observed_at_request_time"
    assert (
        access["observation_basis"] == "valid_nonempty_rows_returned_for_this_request"
    )
    assert access["nonclaims"] == [
        "not_proof_of_purchase",
        "not_proof_of_payment",
        "not_proof_of_license_or_commercial_use_rights",
        "not_proof_of_future_access",
        "not_proof_of_trial_absence",
    ]
    assert receipt["license_authority_gate"] == {
        "gate_state": "satisfied_for_bounded_metadata_only_pilot",
        "accepted_basis": addons.LICENSE_AUTHORITY_GATE_VALUE,
        "authority_reference_sha256": LICENSE_REFERENCE,
        "personal_pricing_nonclaim": ("personal_pricing_is_not_a_commercial_use_grant"),
        "scope_nonclaims": [
            "no_commercial_use_authority",
            "no_product_publication_authority",
            "no_team_sharing_or_redistribution_authority",
            "no_signal_or_strategy_authority",
        ],
    }
    assert receipt["request"]["maximum_vendor_calls"] == 3
    assert receipt["request"]["range_or_bulk_mode"] is False
    assert receipt["request"]["vendor_request_without_token"]["transport"] == "HTTPS"
    assert "token" not in receipt["request"]["vendor_request_without_token"]
    assert (
        "tushare_daily_and_stk_limit"
        in receipt["join_basis_contract"]["required_nominal_history"]
    )
    assert (
        "yahoo_split_adjusted"
        in receipt["join_basis_contract"]["forbidden_nominal_history"]
    )
    assert receipt["exact_session_receipt"]["required_exchanges"] == ["SSE", "SZSE"]
    assert receipt["request_clock"]["observation_point"] == (
        "after_trade_cal_immediately_before_addon_endpoint_request"
    )
    assert (
        access["observed_at_asia_shanghai"]
        == receipt["request_clock"]["observed_at_asia_shanghai"]
    )
    assert receipt["runtime_receipt"]["collector_source_sha256"]
    assert receipt["data_receipt"]["row_count"] == 2
    assert (
        addons.canonical_hash(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        )
        == receipt["receipt_sha256"]
    )

    table = pq.read_table(destination / "part.parquet")
    assert table.schema.metadata[b"endpoint"] == b"stk_mins"
    assert table.column("ticker").to_pylist() == ["600519.SS", "600519.SS"]
    assert table.column("session_segment").to_pylist() == [
        "regular_trading_window",
        "regular_trading_window",
    ]


def test_identical_rerun_is_noop_and_revision_is_keep_first_contradiction(
    tmp_path: Path,
) -> None:
    first_query = FakeQuery("stk_mins", minute_frame())
    first = addons.collect_pilot(
        minute_request(), output_root=tmp_path, query_fn=first_query, now=HISTORICAL_NOW
    )
    destination = Path(first.partition_path)
    before = {
        path.name: path.read_bytes() for path in destination.iterdir() if path.is_file()
    }

    second = addons.collect_pilot(
        minute_request(),
        output_root=tmp_path,
        query_fn=FakeQuery("stk_mins", minute_frame()),
        now=HISTORICAL_NOW,
    )
    after = {
        path.name: path.read_bytes() for path in destination.iterdir() if path.is_file()
    }
    assert second.status == "unchanged"
    assert before == after

    with pytest.raises(addons.CollectorIntegrityError, match="keep-first"):
        addons.collect_pilot(
            minute_request(),
            output_root=tmp_path,
            query_fn=FakeQuery("stk_mins", minute_frame(high=10.3)),
            now=HISTORICAL_NOW,
        )
    assert before == {
        path.name: path.read_bytes() for path in destination.iterdir() if path.is_file()
    }


def test_rehashed_authority_tamper_is_still_rejected(tmp_path: Path) -> None:
    result = addons.collect_pilot(
        minute_request(),
        output_root=tmp_path,
        query_fn=FakeQuery("stk_mins", minute_frame()),
        now=HISTORICAL_NOW,
    )
    receipt_path = Path(result.partition_path) / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["authority"] = "signal_authority"
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = addons.canonical_hash(receipt)
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")

    with pytest.raises(addons.CollectorIntegrityError, match="authority"):
        addons.collect_pilot(
            minute_request(),
            output_root=tmp_path,
            query_fn=FakeQuery("stk_mins", minute_frame()),
            now=HISTORICAL_NOW,
        )


def test_license_gate_fails_before_vendor_call_or_partition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(addons.LICENSE_AUTHORITY_ENV)
    monkeypatch.delenv(addons.LICENSE_AUTHORITY_REFERENCE_ENV)
    query = FakeQuery("stk_mins", minute_frame())

    with pytest.raises(addons.CollectionHeld, match="written_vendor_authorization"):
        addons.collect_pilot(
            minute_request(), output_root=tmp_path, query_fn=query, now=HISTORICAL_NOW
        )

    assert query.calls == []
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_bse_pilots_fail_before_vendor_call_or_partition(tmp_path: Path) -> None:
    query = FakeQuery("stk_mins", minute_frame())
    request = addons.PilotRequest(
        endpoint="stk_mins",
        trade_date="2026-08-07",
        ticker="430047.BJ",
        frequency="1min",
    )

    with pytest.raises(addons.CollectionHeld, match="BSE_pilots_blocked"):
        addons.collect_pilot(
            request, output_root=tmp_path, query_fn=query, now=HISTORICAL_NOW
        )

    assert query.calls == []
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_calendar_and_exact_session_fail_before_partition_mutation(
    tmp_path: Path,
) -> None:
    closed = FakeQuery(
        "stk_mins",
        minute_frame(),
        open_by_exchange={"SSE": 0, "SZSE": 0},
    )
    with pytest.raises(addons.CollectionHeld, match="not_an_open"):
        addons.collect_pilot(
            minute_request(), output_root=tmp_path, query_fn=closed, now=HISTORICAL_NOW
        )
    assert [call[0] for call in closed.calls] == ["trade_cal", "trade_cal"]
    assert list(tmp_path.iterdir()) == []

    wrong_day = FakeQuery("stk_mins", minute_frame(trade_date="2026-08-06"))
    with pytest.raises(addons.CollectorIntegrityError, match="exact session"):
        addons.collect_pilot(
            minute_request(),
            output_root=tmp_path,
            query_fn=wrong_day,
            now=HISTORICAL_NOW,
        )
    assert len(wrong_day.calls) == 3
    assert list(tmp_path.iterdir()) == []


def test_clock_guards_make_no_vendor_call_or_partition(tmp_path: Path) -> None:
    auction_query = FakeQuery("stk_auction", auction_frame())
    with pytest.raises(addons.CollectionHeld, match="outside_documented"):
        addons.collect_pilot(
            addons.PilotRequest(
                endpoint="stk_auction", trade_date="2026-08-10", ticker="000001.SZ"
            ),
            output_root=tmp_path,
            query_fn=auction_query,
            now=datetime(2026, 8, 10, 9, 31, tzinfo=SHANGHAI),
        )
    assert auction_query.calls == []

    minute_query = FakeQuery("stk_mins", minute_frame())
    with pytest.raises(addons.CollectionHeld, match="not_finalized"):
        addons.collect_pilot(
            addons.PilotRequest(
                endpoint="stk_mins",
                trade_date="2026-08-10",
                ticker="600519.SS",
                frequency="1min",
            ),
            output_root=tmp_path,
            query_fn=minute_query,
            now=datetime(2026, 8, 10, 20, 59, tzinfo=SHANGHAI),
        )
    assert minute_query.calls == []
    assert list(tmp_path.iterdir()) == []


def test_auction_rechecks_clock_after_calendars_and_blocks_0930_crossing(
    tmp_path: Path,
) -> None:
    query = FakeQuery("stk_auction", auction_frame())
    clock = SequenceClock(
        datetime(2026, 8, 10, 9, 29, 59, tzinfo=SHANGHAI),
        datetime(2026, 8, 10, 9, 30, 0, tzinfo=SHANGHAI),
    )

    with pytest.raises(addons.CollectionHeld, match="outside_documented"):
        addons.collect_pilot(
            addons.PilotRequest(
                endpoint="stk_auction", trade_date="2026-08-10", ticker="000001.SZ"
            ),
            output_root=tmp_path,
            query_fn=query,
            clock_fn=clock,
        )

    assert [call[0] for call in query.calls] == ["trade_cal", "trade_cal"]
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_auction_receipt_binds_final_pre_request_clock(tmp_path: Path) -> None:
    query = FakeQuery("stk_auction", auction_frame())
    final_clock = datetime(2026, 8, 10, 9, 27, 8, tzinfo=SHANGHAI)
    result = addons.collect_pilot(
        addons.PilotRequest(
            endpoint="stk_auction", trade_date="2026-08-10", ticker="000001.SZ"
        ),
        output_root=tmp_path,
        query_fn=query,
        clock_fn=SequenceClock(
            datetime(2026, 8, 10, 9, 27, 0, tzinfo=SHANGHAI),
            final_clock,
        ),
    )
    receipt = json.loads(
        (Path(result.partition_path) / "receipt.json").read_text(encoding="utf-8")
    )

    assert (
        receipt["request_clock"]["observed_at_asia_shanghai"] == final_clock.isoformat()
    )
    assert (
        receipt["access_observation_receipt"]["observed_at_asia_shanghai"]
        == final_clock.isoformat()
    )


@pytest.mark.parametrize("clock", ["15:05:00", "15:30:00"])
def test_minute_validator_preserves_post_close_boundary_rows(
    tmp_path: Path, clock: str
) -> None:
    result = addons.collect_pilot(
        minute_request(),
        output_root=tmp_path / clock.replace(":", ""),
        query_fn=FakeQuery("stk_mins", minute_clock_frame(clock)),
        now=HISTORICAL_NOW,
    )
    table = pq.read_table(Path(result.partition_path) / "part.parquet")

    assert table.column("session_segment").to_pylist() == ["unclassified_post_close"]


def test_minute_validator_rejects_clock_after_admitted_post_close_window(
    tmp_path: Path,
) -> None:
    query = FakeQuery("stk_mins", minute_clock_frame("15:31:00"))
    with pytest.raises(addons.CollectorIntegrityError, match="admitted A-share clocks"):
        addons.collect_pilot(
            minute_request(),
            output_root=tmp_path,
            query_fn=query,
            now=HISTORICAL_NOW,
        )
    assert [call[0] for call in query.calls] == [
        "trade_cal",
        "trade_cal",
        "stk_mins",
    ]
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_premarket_and_auction_single_ticker_partitions(tmp_path: Path) -> None:
    premarket = addons.collect_pilot(
        addons.PilotRequest(
            endpoint="stk_premarket", trade_date="20260807", ticker="000001.SZ"
        ),
        output_root=tmp_path,
        query_fn=FakeQuery("stk_premarket", premarket_frame()),
        now=HISTORICAL_NOW,
    )
    assert "by_frequency=daily_premarket" in premarket.partition_path

    auction = addons.collect_pilot(
        addons.PilotRequest(
            endpoint="stk_auction", trade_date="2026-08-10", ticker="000001.SZ"
        ),
        output_root=tmp_path,
        query_fn=FakeQuery("stk_auction", auction_frame()),
        now=datetime(2026, 8, 10, 9, 27, tzinfo=SHANGHAI),
    )
    assert "by_frequency=opening_auction" in auction.partition_path
    assert pq.read_table(Path(auction.partition_path) / "part.parquet").num_rows == 1


def test_suspiciously_thin_market_scope_and_partial_bundle_fail_closed(
    tmp_path: Path,
) -> None:
    with pytest.raises(addons.CollectionHeld, match="suspiciously_thin"):
        addons.collect_pilot(
            addons.PilotRequest(endpoint="stk_premarket", trade_date="2026-08-07"),
            output_root=tmp_path,
            query_fn=FakeQuery("stk_premarket", premarket_frame()),
            now=HISTORICAL_NOW,
        )
    assert list(tmp_path.iterdir()) == []

    normalized = addons.normalize_request(minute_request())
    partial = addons.partition_path(tmp_path, normalized)
    partial.mkdir(parents=True)
    (partial / "part.parquet").write_bytes(b"not a parquet")
    with pytest.raises(addons.CollectorIntegrityError, match="partial"):
        addons.collect_pilot(
            minute_request(),
            output_root=tmp_path,
            query_fn=FakeQuery("stk_mins", minute_frame()),
            now=HISTORICAL_NOW,
        )


def test_https_query_keeps_token_out_of_url(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    class Response:
        status_code = 200
        is_redirect = False
        is_permanent_redirect = False

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"code": 0, "data": {"fields": ["value"], "items": [[1]]}}

    def fake_post(url: str, **kwargs: object) -> Response:
        observed["url"] = url
        observed.update(kwargs)
        return Response()

    monkeypatch.setenv("TUSHARE_TOKEN", "paid-secret")
    monkeypatch.setattr(addons.requests, "post", fake_post)
    frame = addons._query_tushare_https(
        "trade_cal", fields="exchange,cal_date", exchange="SSE"
    )
    assert frame is not None and frame.to_dict(orient="records") == [{"value": 1}]
    assert observed["url"] == "https://api.tushare.pro"
    assert "paid-secret" not in str(observed["url"])
    assert observed["json"]["token"] == "paid-secret"
    assert observed["json"]["fields"] == "exchange,cal_date"
    assert observed["json"]["params"] == {"exchange": "SSE"}
    assert observed["timeout"] == 30
    assert observed["allow_redirects"] is False


def test_https_query_rejects_redirect_without_reading_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RedirectResponse:
        status_code = 307
        is_redirect = True
        is_permanent_redirect = True

        def raise_for_status(self) -> None:
            raise AssertionError("redirect must be rejected before status parsing")

        def json(self) -> dict[str, object]:
            raise AssertionError("redirect body must never be parsed")

    observed: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> RedirectResponse:
        observed["url"] = url
        observed.update(kwargs)
        return RedirectResponse()

    monkeypatch.setenv("TUSHARE_TOKEN", " paid-secret-with-space ")
    monkeypatch.setattr(addons.requests, "post", fake_post)

    assert addons._query_tushare_https("trade_cal", exchange="SSE") is None
    assert observed["url"] == "https://api.tushare.pro"
    assert observed["allow_redirects"] is False


def test_cli_defaults_to_plan_and_has_no_range_or_backfill_surface(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parser = cli.build_parser()
    option_strings = {
        option for action in parser._actions for option in action.option_strings
    }
    for subparser_action in parser._subparsers._actions:
        for subparser in (getattr(subparser_action, "choices", None) or {}).values():
            option_strings.update(
                option
                for action in subparser._actions
                for option in action.option_strings
            )
    assert "--start-date" not in option_strings
    assert "--end-date" not in option_strings
    assert "--backfill" not in option_strings

    rc = cli.main(
        [
            "stk_mins",
            "--trade-date",
            "2026-08-07",
            "--ticker",
            "600519.SS",
            "--frequency",
            "1min",
            "--output-root",
            str(tmp_path / "planned"),
        ]
    )
    assert rc == 0
    assert (
        json.loads(capsys.readouterr().out)["status"] == "planned_no_network_no_write"
    )
    assert not (tmp_path / "planned").exists()


def test_cli_failure_receipt_does_not_echo_exception_or_secret(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "vendor-exception-contained-this-secret"

    def fail(*args: object, **kwargs: object) -> addons.PilotResult:
        raise RuntimeError(secret)

    monkeypatch.setattr(cli, "collect_pilot", fail)
    rc = cli.main(
        [
            "stk_mins",
            "--trade-date",
            "2026-08-07",
            "--ticker",
            "600519.SS",
            "--frequency",
            "1min",
            "--output-root",
            str(tmp_path),
            "--execute",
        ]
    )
    payload = capsys.readouterr().out
    assert rc == 4
    assert secret not in payload
    assert json.loads(payload) == {
        "authority": "context_display_only",
        "endpoint": "stk_mins",
        "reason_code": "unexpected_collector_failure",
        "status": "unexpected_failure_fail_closed",
    }


def test_manual_workflow_is_main_only_review_only_and_registered_in_dag() -> None:
    workflow_path = ROOT / ".github/workflows/tushare-addons-pilot.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    job = workflow["jobs"]["pilot"]
    assert "schedule:" not in workflow_text
    assert "push:" not in workflow_text
    assert "refs/heads/main" in job["if"]
    assert "confirm_execute" in job["if"]
    assert "TUSHARE_VENDOR_LICENSE_AUTHORITY" in job["if"]
    assert addons.LICENSE_AUTHORITY_GATE_VALUE in job["if"]
    assert job["permissions"] if "permissions" in job else workflow["permissions"]
    assert "persist-credentials: false" in workflow_text
    assert "actions/upload-artifact@ea165f" in workflow_text
    assert "--execute" in workflow_text
    assert "--start-date" not in workflow_text
    assert "--end-date" not in workflow_text
    assert "stk_auction_o" not in workflow_text
    assert "stk_auction_c" not in workflow_text
    assert "part.parquet" not in workflow_text
    assert 'raw_paid_rows_included"] = False' in workflow_text
    assert 'raw_parquet_included"] = False' in workflow_text
    assert ".strip().encode()" in workflow_text

    steps = {step["name"]: step for step in job["steps"] if "name" in step}
    token_scan = steps["prove review artifact contains no token"]
    upload = steps["upload metadata-only pilot receipt"]
    cleanup = steps["remove isolated paid-data and review directories"]
    assert token_scan["id"] == "token_scan"
    assert "raw_token" in token_scan["run"]
    assert "transport_token" in token_scan["run"]
    assert "steps.token_scan.outcome == 'success'" in upload["if"]
    assert "steps.token_scan.outputs.passed == 'true'" in upload["if"]
    assert str(upload["with"]["path"]).endswith("-review")
    assert cleanup["if"] == "${{ always() }}"
    assert '"$raw"' in cleanup["run"]
    assert '"$review"' in cleanup["run"]

    dag = yaml.safe_load((ROOT / "config/dag.yml").read_text(encoding="utf-8"))
    lanes = [
        lane
        for lane in dag["lanes"]
        if lane["workflow"] == ".github/workflows/tushare-addons-pilot.yml"
    ]
    assert len(lanes) == 1
    assert lanes[0]["job"] == "pilot"
    assert [step["module"] for step in lanes[0]["steps"]] == [
        "scripts.collect_tushare_addons"
    ]
