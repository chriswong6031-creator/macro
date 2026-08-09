from __future__ import annotations

import json
import subprocess
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
# Each entry states something the data itself cannot support, regardless of who
# ordered the collection.
EPISTEMIC_NONCLAIMS = [
    "context_only_not_signal_authority",
    "no_fillability_or_execution_claim",
    "no_complete_historical_backfill_claim",
    "post_close_rows_are_unclassified_not_a_completeness_claim",
    "no_level2_order_book_or_queue_position",
]
ACCESS_NONCLAIMS = [
    "not_proof_of_future_access",
    "not_a_completeness_claim_for_the_session",
]


@pytest.fixture(autouse=True)
def configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured TUSHARE_TOKEN is the only execution prerequisite."""
    monkeypatch.setenv("TUSHARE_TOKEN", "synthetic-test-token")


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


def auction_oc_frame(*, trade_date: str = "20260807") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": trade_date,
                "close": 10.1,
                "open": 10.0,
                "high": 10.15,
                "low": 9.95,
                "vol": 10_000,
                "amount": 100_500,
                "vwap": 10.05,
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
            requested = str(kwargs["start_date"])
            prior = pd.Timestamp(requested) - pd.Timedelta(days=1)
            return pd.DataFrame(
                [
                    {
                        "exchange": exchange,
                        "cal_date": requested,
                        "is_open": self.open_by_exchange[exchange],
                        "pretrade_date": prior.strftime("%Y%m%d"),
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


def test_plan_is_no_network_no_write_and_names_the_operative_authority(
    tmp_path: Path,
) -> None:
    output = tmp_path / "store"
    plan = addons.pilot_plan(minute_request(), output_root=output)
    assert plan["status"] == "planned_no_network_no_write"
    assert plan["maximum_vendor_calls"] == 3
    assert plan["range_or_bulk_mode"] is False
    assert plan["request"]["ticker"] == "600519.SS"
    assert plan["collection_provenance"] == {
        "basis": "operator_ordered_wiring",
        "reference": "research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md",
    }
    assert plan["execute_requirements"]["tushare_token_configured"] is True
    assert plan["execute_requirements"]["technical_fences"] == [
        "two_exchange_trade_cal_session_agreement",
        "per_endpoint_collection_clock",
        "documented_row_cap",
        "exact_session_and_ticker_containment",
        "schema_and_domain_validation",
        "keep_first_immutability",
    ]
    assert not output.exists()


def test_no_endpoint_is_blocked_unconfirmed_after_the_auction_oc_admission(
    tmp_path: Path,
) -> None:
    """The o/c hold is released; the receipt key stays so readers see the state."""
    assert dict(addons.BLOCKED_UNCONFIRMED_ENDPOINTS) == {}
    output = tmp_path / "store"
    for endpoint in ("stk_auction_o", "stk_auction_c"):
        plan = addons.pilot_plan(
            addons.PilotRequest(
                endpoint=endpoint, trade_date="2026-08-07", ticker="000001.SZ"
            ),
            output_root=output,
        )
        assert plan["blocked_unconfirmed_endpoints"] == {}
        assert plan["declared_access_context"] == (
            "operator_attested_2026-08-09_takeover_doc"
        )
    assert not output.exists()


def test_admitted_auction_oc_contracts_pin_their_official_documents() -> None:
    documents = {"stk_auction_o": 353, "stk_auction_c": 354}
    for endpoint, document_id in documents.items():
        contract = addons.ENDPOINTS[endpoint]
        assert contract.document_id == document_id
        assert contract.document_url.endswith(f"doc_id={document_id}")
        assert contract.contract_source == "official_doc_page"
        # Docs 353/354 publish this exact output field list, in this order.
        assert contract.vendor_fields == (
            "ts_code",
            "trade_date",
            "close",
            "open",
            "high",
            "low",
            "vol",
            "amount",
            "vwap",
        )
        assert contract.max_rows == 10_000
        units = {field.name: field.unit for field in contract.output_schema}
        # Neither doc states a unit for 成交量/成交额, so the schema must disclose
        # the gap rather than assert shares/CNY the minute contract can assert.
        assert "no unit" in str(units["volume"])
        assert "no unit" in str(units["amount"])
        assert units["close"] == "CNY/share"


def test_default_output_root_is_gitignored() -> None:
    expected = ROOT / "data/tushare_addons"
    assert Path(addons.DEFAULT_OUTPUT_ROOT).resolve() == expected.resolve()
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "data/tushare_addons/probe/part.parquet"],
        cwd=ROOT,
        check=False,
    )
    assert ignored.returncode == 0


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
    assert access["nonclaims"] == ACCESS_NONCLAIMS
    assert receipt["collection_provenance"] == {
        "basis": "operator_ordered_wiring",
        "reference": "research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md",
    }
    assert receipt["nonclaims"] == EPISTEMIC_NONCLAIMS
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


def test_execution_requires_a_configured_token_and_makes_no_call_without_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Token presence is the only execution prerequisite -- and it fails closed."""
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    with pytest.raises(addons.CollectionHeld, match="TUSHARE_TOKEN_absent"):
        addons.collect_pilot(minute_request(), output_root=tmp_path, now=HISTORICAL_NOW)

    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_no_authorization_env_var_gates_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No env var may gate this collector: only the technical fences bind.

    The pilot foundation once carried a separate authorization gate. It was
    removed by operator ruling (2026-08-09), so a run with a configured token and
    a hostile environment must still collect normally.
    """
    for stale in (
        "TUSHARE_VENDOR_LICENSE_AUTHORITY",
        "TUSHARE_VENDOR_LICENSE_AUTHORITY_SHA256",
    ):
        monkeypatch.setenv(stale, "definitely-not-a-valid-value")

    result = addons.collect_pilot(
        minute_request(),
        output_root=tmp_path,
        query_fn=FakeQuery("stk_mins", minute_frame()),
        now=HISTORICAL_NOW,
    )

    assert result.status == "written"
    source = (ROOT / "collectors/tushare_addons.py").read_text(encoding="utf-8")
    assert "TUSHARE_VENDOR_LICENSE_AUTHORITY" not in source
    assert "allowlist" not in source.lower()


def test_receipt_records_plain_provenance_and_epistemic_nonclaims_only(
    tmp_path: Path,
) -> None:
    result = addons.collect_pilot(
        minute_request(),
        output_root=tmp_path,
        query_fn=FakeQuery("stk_mins", minute_frame()),
        now=HISTORICAL_NOW,
    )
    receipt = json.loads(
        (Path(result.partition_path) / "receipt.json").read_text(encoding="utf-8")
    )

    assert receipt["collection_provenance"] == {
        "basis": "operator_ordered_wiring",
        "reference": "research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md",
    }
    assert receipt["nonclaims"] == EPISTEMIC_NONCLAIMS
    access = receipt["access_observation_receipt"]
    assert access["observation"] == "access_observed_at_request_time"
    assert access["nonclaims"] == ACCESS_NONCLAIMS
    # No licensing conclusion is asserted in either direction.
    blob = json.dumps(receipt, ensure_ascii=False).lower()
    assert "license" not in blob
    assert "attestation" not in blob


def test_altered_provenance_is_a_keep_first_contradiction(tmp_path: Path) -> None:
    result = addons.collect_pilot(
        minute_request(),
        output_root=tmp_path,
        query_fn=FakeQuery("stk_mins", minute_frame()),
        now=HISTORICAL_NOW,
    )
    receipt_path = Path(result.partition_path) / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["collection_provenance"] = {"basis": "self_authorized", "reference": "x"}
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = addons.canonical_hash(receipt)
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")

    with pytest.raises(addons.CollectorIntegrityError, match="provenance"):
        addons.collect_pilot(
            minute_request(),
            output_root=tmp_path,
            query_fn=FakeQuery("stk_mins", minute_frame()),
            now=HISTORICAL_NOW,
        )


@pytest.mark.parametrize(
    ("endpoint", "frequency"),
    [
        ("stk_auction_o", "opening_call_auction"),
        ("stk_auction_c", "closing_call_auction"),
    ],
)
def test_auction_oc_pilots_write_partitions_and_preserve_a_no_trade_auction(
    tmp_path: Path, endpoint: str, frequency: str
) -> None:
    query = FakeQuery(endpoint, auction_oc_frame())
    result = addons.collect_pilot(
        addons.PilotRequest(
            endpoint=endpoint, trade_date="2026-08-07", ticker="000001.SZ"
        ),
        output_root=tmp_path / endpoint,
        query_fn=query,
        now=HISTORICAL_NOW,
    )

    assert result.status == "written"
    assert f"by_frequency={frequency}" in result.partition_path
    assert [call[0] for call in query.calls] == ["trade_cal", "trade_cal", endpoint]
    endpoint_params = query.calls[-1][1]
    assert endpoint_params["trade_date"] == "20260807"
    assert endpoint_params["ts_code"] == "000001.SZ"
    # ts_type is a stk_auction (doc 369) parameter and must not leak to o/c.
    assert "ts_type" not in endpoint_params

    table = pq.read_table(Path(result.partition_path) / "part.parquet")
    assert table.schema.metadata[b"endpoint"] == endpoint.encode()
    assert table.column("vwap").to_pylist() == [10.05]
    assert table.column("volume").to_pylist() == [10_000.0]

    # A session that draws no matched order is preserved as null prices, never
    # fabricated and never rejected as an integrity failure.
    empty = auction_oc_frame()
    for column in ("open", "high", "low", "close", "vwap"):
        empty.loc[:, column] = float("nan")
    empty.loc[:, "vol"] = 0
    empty.loc[:, "amount"] = 0
    quiet = addons.collect_pilot(
        addons.PilotRequest(
            endpoint=endpoint, trade_date="2026-08-07", ticker="000001.SZ"
        ),
        output_root=tmp_path / f"{endpoint}-quiet",
        query_fn=FakeQuery(endpoint, empty),
        now=HISTORICAL_NOW,
    )
    quiet_table = pq.read_table(Path(quiet.partition_path) / "part.parquet")
    assert quiet_table.column("close").to_pylist() == [None]
    assert quiet_table.column("volume").to_pylist() == [0.0]


@pytest.mark.parametrize("endpoint", ["stk_auction_o", "stk_auction_c"])
def test_auction_oc_rejects_incoherent_ohlc_without_writing(
    tmp_path: Path, endpoint: str
) -> None:
    frame = auction_oc_frame()
    frame.loc[:, "low"] = 99.0
    query = FakeQuery(endpoint, frame)

    with pytest.raises(addons.CollectorIntegrityError, match="OHLC"):
        addons.collect_pilot(
            addons.PilotRequest(
                endpoint=endpoint, trade_date="2026-08-07", ticker="000001.SZ"
            ),
            output_root=tmp_path,
            query_fn=query,
            now=HISTORICAL_NOW,
        )
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("endpoint", ["stk_auction_o", "stk_auction_c"])
def test_auction_oc_has_no_hold_on_history_but_holds_an_unpublished_session(
    tmp_path: Path, endpoint: str
) -> None:
    """Docs 353/354 say 每天盘后更新, so only the CURRENT session is held."""
    request = addons.PilotRequest(
        endpoint=endpoint, trade_date="2026-08-10", ticker="000001.SZ"
    )
    query = FakeQuery(endpoint, auction_oc_frame(trade_date="20260810"))

    with pytest.raises(addons.CollectionHeld, match="not_yet_published"):
        addons.collect_pilot(
            request,
            output_root=tmp_path,
            query_fn=query,
            now=datetime(2026, 8, 10, 16, 29, tzinfo=SHANGHAI),
        )
    assert query.calls == []

    published = addons.collect_pilot(
        request,
        output_root=tmp_path,
        query_fn=FakeQuery(endpoint, auction_oc_frame(trade_date="20260810")),
        now=datetime(2026, 8, 10, 16, 30, tzinfo=SHANGHAI),
    )
    assert published.status == "written"

    # A deep-history session is admitted with no clock objection at all.
    historical = addons.collect_pilot(
        addons.PilotRequest(
            endpoint=endpoint, trade_date="2023-03-01", ticker="000001.SZ"
        ),
        output_root=tmp_path,
        query_fn=FakeQuery(endpoint, auction_oc_frame(trade_date="20230301")),
        now=datetime(2026, 8, 10, 0, 1, tzinfo=SHANGHAI),
    )
    assert "by_trade_date=2023-03-01" in historical.partition_path


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


def test_vendor_response_bse_row_fails_without_partition(tmp_path: Path) -> None:
    frame = premarket_frame()
    frame.loc[:, "ts_code"] = "430047.BJ"
    query = FakeQuery("stk_premarket", frame)

    with pytest.raises(addons.CollectionHeld, match="BSE_rows_blocked"):
        addons.collect_pilot(
            addons.PilotRequest(
                endpoint="stk_premarket",
                trade_date="2026-08-07",
                ticker="000001.SZ",
            ),
            output_root=tmp_path,
            query_fn=query,
            now=HISTORICAL_NOW,
        )

    assert [call[0] for call in query.calls] == [
        "trade_cal",
        "trade_cal",
        "stk_premarket",
    ]
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


@pytest.mark.parametrize("endpoint", sorted(addons.ENDPOINTS))
def test_all_library_pilots_require_one_ticker_before_vendor_call(
    tmp_path: Path, endpoint: str
) -> None:
    query = FakeQuery(endpoint, minute_frame())
    with pytest.raises(addons.CollectionHeld, match="require_one_ticker"):
        addons.collect_pilot(
            addons.PilotRequest(
                endpoint=endpoint,
                trade_date="2026-08-07",
                frequency="1min" if endpoint == "stk_mins" else None,
            ),
            output_root=tmp_path,
            query_fn=query,
            now=HISTORICAL_NOW,
        )
    assert query.calls == []
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_partial_bundle_fails_closed(tmp_path: Path) -> None:

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
    endpoint_parsers = next(
        action.choices for action in parser._actions if getattr(action, "choices", None)
    )
    # Every admitted library contract must be reachable from the CLI, and the CLI
    # must not offer an endpoint the library has no contract for.
    assert set(endpoint_parsers) == set(addons.ENDPOINTS)
    for endpoint_parser in endpoint_parsers.values():
        ticker_action = next(
            action for action in endpoint_parser._actions if action.dest == "ticker"
        )
        assert ticker_action.required is True

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


def test_cli_execute_requires_explicit_output_root_before_collection(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> addons.PilotResult:
        raise AssertionError("collector must not run without explicit output root")

    monkeypatch.setattr(cli, "collect_pilot", forbidden)
    rc = cli.main(
        [
            "stk_mins",
            "--trade-date",
            "2026-08-07",
            "--ticker",
            "600519.SS",
            "--frequency",
            "1min",
            "--execute",
        ]
    )

    assert rc == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == (
        "execute_requires_explicit_output_root"
    )


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
    # No authorization env var may gate this lane -- the main-ref pin plus the
    # explicit dispatch confirmation are the whole gate (operator ruling 2026-08-09).
    assert "TUSHARE_VENDOR_LICENSE_AUTHORITY" not in workflow_text
    assert job["permissions"] if "permissions" in job else workflow["permissions"]
    assert "persist-credentials: false" in workflow_text
    assert "actions/upload-artifact@ea165f" in workflow_text
    assert "--execute" in workflow_text
    assert "--start-date" not in workflow_text
    assert "--end-date" not in workflow_text
    # The hosted review lane was deliberately not widened to the newly admitted
    # o/c endpoints: it stays a three-endpoint witness lane, and the o/c probes run
    # locally against a gitignored root.
    assert "stk_auction_o" not in workflow_text
    assert "stk_auction_c" not in workflow_text
    assert "part.parquet" not in workflow_text
    assert 'raw_paid_rows_included"] = False' in workflow_text
    assert 'raw_parquet_included"] = False' in workflow_text
    assert ".strip().encode()" in workflow_text

    steps = {step["name"]: step for step in job["steps"] if "name" in step}
    token_scan = steps["prove review artifact contains no token"]
    raw_cleanup = steps["remove isolated paid-data directory before upload"]
    upload = steps["upload metadata-only pilot receipt"]
    cleanup = steps["remove remaining isolated run directories"]
    assert token_scan["id"] == "token_scan"
    assert "raw_token" in token_scan["run"]
    assert "transport_token" in token_scan["run"]
    assert raw_cleanup["id"] == "raw_cleanup"
    assert raw_cleanup["if"] == "${{ always() }}"
    assert '/bin/rm -rf -- "$raw"' in raw_cleanup["run"]
    assert 'test ! -e "$raw"' in raw_cleanup["run"]
    assert "steps.token_scan.outcome == 'success'" in upload["if"]
    assert "steps.token_scan.outputs.passed == 'true'" in upload["if"]
    assert "steps.raw_cleanup.outcome == 'success'" in upload["if"]
    assert "steps.raw_cleanup.outputs.passed == 'true'" in upload["if"]
    assert str(upload["with"]["path"]).endswith("-review")
    step_names = [step.get("name") for step in job["steps"]]
    assert step_names.index("remove isolated paid-data directory before upload") < (
        step_names.index("upload metadata-only pilot receipt")
    )
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
