from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from collectors import china_tushare_spine as spine

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
GENERATION = "ref-test-generation-0001"


@pytest.fixture(autouse=True)
def _enable_synthetic_technical_readiness(monkeypatch):
    """Synthetic collectors exercise mechanics; production stays fail-closed."""
    # Synthetic request functions exercise collector mechanics without network.
    # Production remains fail-closed until a scalable range-shard plan is reviewed.
    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", True)


def _request_receipt(
    endpoint: str,
    unit: str,
    store: Path | None = None,
    *,
    frame: pd.DataFrame | None = None,
    params: dict | None = None,
    status: str | None = None,
) -> dict:
    fields = spine.ENDPOINT_FIELDS.get(endpoint, "").split(",")
    response = frame if frame is not None else pd.DataFrame(columns=fields)
    request_contract = {
        "endpoint": endpoint,
        "fields": fields,
        "params": dict(sorted((params or {}).items())),
        "unit": unit,
    }
    digest = hashlib.sha256(spine._canonical_json_bytes(request_contract)).hexdigest()
    receipt = {
        "request_id": digest,
        "endpoint": endpoint,
        "unit": unit,
        "request_contract_sha256": digest,
        "response_status": status or ("accepted_empty" if response.empty else "accepted"),
        "fields": fields,
        "params": request_contract["params"],
        "observed_at": NOW.isoformat(),
        "response_row_count": len(response),
        "response_columns": list(response.columns),
        "response_semantic_sha256": spine._raw_response_semantic_sha256(response),
    }
    if store is not None:
        path = spine._request_receipt_path(store, endpoint, unit, digest)
        spine._atomic_json(path, receipt)
        receipt["path"] = path.relative_to(store).as_posix()
    return receipt






def _stock_basic_rows() -> dict[tuple[str, str], pd.DataFrame]:
    columns = spine.ENDPOINT_FIELDS["stock_basic"].split(",")
    empty = lambda: pd.DataFrame(columns=columns)
    rows = {(exchange, status): empty() for exchange in spine.EXCHANGES for status in spine.LIST_STATUSES}
    rows[("SSE", "L")] = pd.DataFrame([{
        "ts_code": "600519.SS", "symbol": "600519", "name": "贵州茅台", "area": "贵州",
        "industry": "白酒", "market": "主板", "exchange": "SSE", "curr_type": "CNY",
        "list_status": "L", "list_date": "20010827", "delist_date": None, "is_hs": "H",
    }], columns=columns)
    rows[("SZSE", "L")] = pd.DataFrame([{
        "ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "area": "深圳",
        "industry": "银行", "market": "主板", "exchange": "SZSE", "curr_type": "CNY",
        "list_status": "L", "list_date": "19910403", "delist_date": None, "is_hs": "S",
    }], columns=columns)
    rows[("BSE", "L")] = pd.DataFrame([{
        "ts_code": "920163.BJ", "symbol": "920163", "name": "方大新材", "area": "河北",
        "industry": "建材", "market": "北交所", "exchange": "BSE", "curr_type": "CNY",
        "list_status": "L", "list_date": "20200727", "delist_date": None, "is_hs": "N",
    }], columns=columns)
    rows[("SSE", "D")] = pd.DataFrame([{
        "ts_code": "600001.SS", "symbol": "600001", "name": "已退样本", "area": "上海",
        "industry": "工业", "market": "主板", "exchange": "SSE", "curr_type": "CNY",
        "list_status": "D", "list_date": "19901219", "delist_date": "20200101", "is_hs": "N",
    }], columns=columns)
    return rows


def _fund_basic_rows() -> dict[str, pd.DataFrame]:
    columns = spine.ENDPOINT_FIELDS["fund_basic"].split(",")
    rows = {status: pd.DataFrame(columns=columns) for status in spine.FUND_STATUSES}
    rows["L"] = pd.DataFrame([{
        "ts_code": "510300.SS", "name": "沪深300ETF", "management": "样本基金",
        "custodian": "样本银行", "fund_type": "股票型", "found_date": "20120101",
        "due_date": None, "list_date": "20120528", "issue_date": "20120501",
        "delist_date": None, "issue_amount": 1, "m_fee": 0.5, "c_fee": 0.1,
        "duration_year": None, "p_value": 1, "min_amount": 0.1, "exp_return": None,
        "benchmark": "沪深300", "status": "L", "invest_type": "被动指数型",
        "type": "契约型开放式", "trustee": "", "purc_startdate": "20120528",
        "redm_startdate": "20120528", "market": "E",
    }], columns=columns)
    return rows


def _seed_reference(store: Path) -> pd.DataFrame:
    mapping = pd.DataFrame([{
        "name": "方大新材", "o_code": "838163.BJ", "n_code": "920163.BJ", "list_date": "2020-07-27",
    }])
    mapping_path = spine._reference_source_path(store, GENERATION, "bse_mapping")
    spine._atomic_parquet(mapping_path, mapping)
    state = spine.load_state(store)
    spine._set_unit(
        state, store, "bse_mapping", f"{GENERATION}:all",
        status="complete", observed_at=NOW.isoformat(),
        row_count=len(mapping), source_row_count=len(mapping),
        partition=mapping_path, request_receipts=[_request_receipt(
            "bse_mapping", f"{GENERATION}:all", store, frame=mapping,
        )],
        generation_id=GENERATION,
    )
    for (exchange, status), frame in _stock_basic_rows().items():
        source_unit = f"{exchange}:{status}"
        path = spine._reference_source_path(store, GENERATION, "stock_basic", source_unit)
        spine._atomic_parquet(path, frame)
        state = spine.load_state(store)
        spine._set_unit(
            state, store, "stock_basic", f"{GENERATION}:{source_unit}",
            status="empty" if frame.empty else "complete", observed_at=NOW.isoformat(),
            row_count=len(frame), source_row_count=len(frame), partition=path,
            request_receipts=[_request_receipt(
                "stock_basic", f"{GENERATION}:{source_unit}", store, frame=frame,
                params={"exchange": exchange, "list_status": status},
            )],
            generation_id=GENERATION,
        )
    for status, frame in _fund_basic_rows().items():
        path = spine._reference_source_path(store, GENERATION, "fund_basic", status)
        spine._atomic_parquet(path, frame)
        state = spine.load_state(store)
        spine._set_unit(
            state, store, "fund_basic", f"{GENERATION}:{status}",
            status="empty" if frame.empty else "complete", observed_at=NOW.isoformat(),
            row_count=0, source_row_count=len(frame),
            known_excluded_row_count=len(frame), partition=path,
            request_receipts=[_request_receipt(
                "fund_basic", f"{GENERATION}:{status}", store, frame=frame,
                params={"market": "E", "status": status},
            )],
            generation_id=GENERATION,
        )
    master, _ = spine.compile_security_master(store, GENERATION)
    spine._promote_reference_generation(store, GENERATION)
    state = spine.load_state(store)
    state["reference_generation"] = {
        "current_id": GENERATION, "staging_id": None, "status": "complete",
    }
    spine._atomic_json(store / "collection_state.json", state)
    return master


def _calendar_frame(exchange: str, open_second: bool = True) -> pd.DataFrame:
    return pd.DataFrame([
        {"exchange": exchange, "cal_date": "20240101", "is_open": 0, "pretrade_date": "20231229"},
        {"exchange": exchange, "cal_date": "20240102", "is_open": 1, "pretrade_date": "20231229"},
        {"exchange": exchange, "cal_date": "20240103", "is_open": int(open_second),
         "pretrade_date": "20240102"},
    ])


def _seed_calendar(store: Path) -> pd.DataFrame:
    path = store / "reference" / "trade_calendar" / "year=2024.parquet"
    for exchange in spine.CALENDAR_EXCHANGES:
        frame = spine._normalise_calendar(
            _calendar_frame(exchange), exchange, date(2024, 1, 1), date(2024, 1, 3),
        )
        spine._upsert_partition(path, frame, keys=spine.KEY_COLUMNS["trade_calendar"])
        state = spine.load_state(store)
        spine._set_unit(
            state, store, "trade_cal", f"{exchange}:20240101:20240103",
            status="complete", observed_at=NOW.isoformat(), row_count=len(frame),
            source_row_count=len(frame), partition=path,
            request_receipts=[_request_receipt(
                "trade_cal", f"{exchange}:20240101:20240103", store, frame=frame,
                params={"exchange": exchange, "start_date": "20240101", "end_date": "20240103"},
            )],
        )
    return spine.compile_market_sessions(store, date(2024, 1, 1), date(2024, 1, 3))


def _bak_rows(trade_date: str) -> pd.DataFrame:
    columns = spine.ENDPOINT_FIELDS["bak_basic"].split(",")
    rows = []
    for code, name, list_date in (
        ("600519.SH", "贵州茅台", "20010827"),
        ("000001.SZ", "平安银行", "19910403"),
        ("920163.BJ", "方大新材", "20211115"),
    ):
        row = {column: None for column in columns}
        row.update({
            "trade_date": trade_date, "ts_code": code, "name": name,
            "industry": "样本", "area": "样本", "list_date": list_date,
            "float_share": 1, "total_share": 1, "total_assets": 1,
            "liquid_assets": 1, "fixed_assets": 1, "holder_num": 1,
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def _seed_pit_day(store: Path, trade_date: str) -> None:
    raw = _bak_rows(trade_date)
    normal = spine.normalise_bak_basic(raw, trade_date, store)
    parsed = spine._parse_date(trade_date)
    path = spine._pit_partition(store, parsed)
    spine._replace_partition_units(
        path, normal.landed_a, keys=spine.KEY_COLUMNS["bak_basic"],
        unit_column="trade_date", units=[parsed.isoformat()],
    )
    state = spine.load_state(store)
    spine._set_unit(
        state, store, "bak_basic", trade_date, status="complete",
        observed_at=NOW.isoformat(), row_count=len(normal.landed_a),
        source_row_count=len(raw), partition=path,
        request_receipts=[_request_receipt(
            "bak_basic", trade_date, store, frame=raw, params={"trade_date": trade_date},
        )],
    )


def _seed_spine(store: Path) -> pd.DataFrame:
    master = _seed_reference(store)
    _seed_calendar(store)
    for trade_date in ("20240102", "20240103"):
        _seed_pit_day(store, trade_date)
    return master


def _daily_rows(trade_date: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"ts_code": "600519.SH", "trade_date": trade_date, "open": 10, "high": 11, "low": 9,
         "close": 11, "pre_close": 10, "change": 1, "pct_chg": 10, "vol": 100, "amount": 1000},
        {"ts_code": "000001.SZ", "trade_date": trade_date, "open": 10, "high": 10, "low": 10,
         "close": 10, "pre_close": 10, "change": 0, "pct_chg": 0, "vol": 0, "amount": 0},
    ])


def _daily_basic_rows(trade_date: str) -> pd.DataFrame:
    rows = pd.DataFrame([
        {"ts_code": code, "trade_date": trade_date,
         "close": 11 if code == "600519.SH" else 10, "turnover_rate": 1,
         "turnover_rate_f": 2, "volume_ratio": 1, "pe": 10, "pe_ttm": 11, "pb": 2,
         "ps": 3, "ps_ttm": 3, "dv_ratio": 1, "dv_ttm": 1, "total_share": 100,
         "float_share": 80, "free_share": 60, "total_mv": 1000, "circ_mv": 800,
         "limit_status": 2 if code == "600519.SH" else 0}
        for code in ("600519.SH", "000001.SZ")
    ])
    return rows[spine.ENDPOINT_FIELDS["daily_basic"].split(",")]


def _limit_rows(trade_date: str) -> pd.DataFrame:
    rows = pd.DataFrame([
        {"ts_code": code, "trade_date": trade_date, "pre_close": 10,
         "up_limit": 11, "down_limit": 9}
        for code in ("600519.SH", "000001.SZ")
    ])
    return rows[spine.ENDPOINT_FIELDS["stk_limit"].split(",")]


def _empty(endpoint: str) -> pd.DataFrame:
    return pd.DataFrame(columns=spine.ENDPOINT_FIELDS[endpoint].split(","))


def test_canonical_identity_suffixes_boards_and_bse_alias():
    sh = spine.canonical_identity("688001.SH")
    assert (sh.ticker, sh.source_ts_code, sh.security_id, sh.board) == (
        "688001.SS", "688001.SH", "CN-XSHG-688001", "star",
    )
    assert spine.canonical_identity("301001.SZ").board == "chinext"
    assert spine.canonical_identity("309901.SZ").board == "chinext"
    assert spine.canonical_identity("600519.SS").source_ts_code == "600519.SH"
    bj = spine.canonical_identity("838163.BJ", bse_aliases={"838163.BJ": "920163.BJ"})
    assert (bj.ticker, bj.security_id, bj.board) == ("920163.BJ", "CN-XBSE-920163", "bse")
    assert bj.source_ts_code == "838163.BJ"  # vendor-observed alias is not erased
    with pytest.raises(spine.SpineError, match="canonical SH/SZ/BJ"):
        spine.canonical_identity("00700.HK")
    with pytest.raises(spine.SpineError, match="920 family"):
        spine._normalise_bse_mapping(pd.DataFrame([{
            "name": "bad alias", "o_code": "838163.BJ",
            "n_code": "830001.BJ", "list_date": "20200727",
        }]))


def test_a_share_limit_bounds_are_decimal_half_up_not_python_round():
    bounds = spine.a_share_limit_price_bounds("2.05", "0.10")
    assert bounds.upper == Decimal("2.26")
    assert bounds.lower == Decimal("1.85")
    assert (bounds.upper_cents, bounds.lower_cents) == (226, 185)
    # These exact half-cent cases are both wrong under binary float + bankers round.
    assert round(2.05 * 1.10, 2) == 2.25
    assert round(2.05 * 0.90, 2) == 1.84


def test_a_share_limit_bounds_enforce_one_tick_move_and_low_price_floor():
    one_cent = spine.a_share_limit_price_bounds("0.01", "0.10")
    assert (one_cent.upper_cents, one_cent.lower_cents) == (2, 1)
    two_cents = spine.a_share_limit_price_bounds("0.02", "0.10")
    assert (two_cents.upper_cents, two_cents.lower_cents) == (3, 1)
    with pytest.raises(spine.SpineError, match="quote tick"):
        spine.a_share_limit_price_bounds("2.055", "0.10")


def test_security_master_lifecycle_and_alias_provenance(tmp_path):
    master = _seed_reference(tmp_path)
    by_ticker = master.set_index("ticker")
    assert set(master["exchange"]) == {"SSE", "SZSE", "BSE"}
    assert by_ticker.loc["600001.SS", "effective_to"] == "2020-01-01"
    # NEEQ list date is not misrepresented as A-share/BSE eligibility.
    assert by_ticker.loc["920163.BJ", "list_date"] == "2020-07-27"
    assert by_ticker.loc["920163.BJ", "effective_from"] == "2021-11-15"
    aliases = pd.read_parquet(spine._reference_derived_path(
        tmp_path, "identity_aliases.parquet",
    ))
    old = aliases[aliases["alias_ticker"] == "838163.BJ"].iloc[0]
    assert old["canonical_ticker"] == "920163.BJ"
    assert old["alias_kind"] == "bse_old_code"


def test_calendar_requires_full_calendar_days_and_sse_szse_equality(tmp_path):
    _seed_reference(tmp_path)
    path = tmp_path / "reference" / "trade_calendar" / "year=2024.parquet"
    sse = spine._normalise_calendar(
        _calendar_frame("SSE"), "SSE", date(2024, 1, 1), date(2024, 1, 3),
    )
    szse = spine._normalise_calendar(
        _calendar_frame("SZSE", open_second=False), "SZSE", date(2024, 1, 1), date(2024, 1, 3),
    )
    spine._upsert_partition(path, sse, keys=spine.KEY_COLUMNS["trade_calendar"])
    spine._upsert_partition(path, szse, keys=spine.KEY_COLUMNS["trade_calendar"])
    with pytest.raises(spine.SpineError, match="open-session calendars disagree"):
        spine.compile_market_sessions(tmp_path, date(2024, 1, 1), date(2024, 1, 3))

    missing = _calendar_frame("SSE").iloc[:-1]
    with pytest.raises(spine.SpineError, match="calendar-day coverage mismatch"):
        spine._normalise_calendar(missing, "SSE", date(2024, 1, 1), date(2024, 1, 3))


def test_daily_normalisation_preserves_source_volume_truth_and_exact_session(tmp_path):
    _seed_spine(tmp_path)
    frame = pd.concat([
        _daily_rows("20240102"),
        pd.DataFrame([{
            "ts_code": "838163.BJ", "trade_date": "20240102", "open": 5, "high": 5, "low": 5,
            "close": 5, "pre_close": 5, "change": 0, "pct_chg": 0, "vol": 10, "amount": 50,
        }, {
            "ts_code": "510300.SH", "trade_date": "20240102", "open": 1, "high": 1, "low": 1,
            "close": 1, "pre_close": 1, "change": 0, "pct_chg": 0, "vol": 5, "amount": 5,
        }, {
            "ts_code": "900901.SH", "trade_date": "20240102", "open": 1, "high": 1, "low": 1,
            "close": 1, "pre_close": 1, "change": 0, "pct_chg": 0, "vol": 5, "amount": 5,
        }, {
            "ts_code": "600999.SH", "trade_date": "20240102", "open": 1, "high": 1, "low": 1,
            "close": 1, "pre_close": 1, "change": 0, "pct_chg": 0, "vol": 5, "amount": 5,
        }]),
    ], ignore_index=True)
    normalised = spine.normalise_daily_endpoint("daily", frame, "20240102", tmp_path)
    normal = normalised.landed_a
    assert len(normalised.known_excluded) == 2
    assert set(normalised.known_excluded["raw_ts_code"]) == {"510300.SH", "900901.SH"}
    b_share = normalised.known_excluded.set_index("raw_ts_code").loc["900901.SH"]
    assert b_share["classification_source"] == "SSE_security_code_900xxx_B_share"
    assert len(normalised.quarantined_unknown) == 1
    assert normalised.quarantined_unknown.iloc[0]["raw_ts_code"] == "600999.SH"
    assert set(normal["ticker"]) == {"600519.SS", "000001.SZ", "920163.BJ"}
    assert normal.set_index("ticker").loc["600519.SS", "source_ts_code"] == "600519.SH"
    assert bool(normal.set_index("ticker").loc["600519.SS", "positive_volume"]) is True
    assert bool(normal.set_index("ticker").loc["000001.SZ", "positive_volume"]) is False
    assert normal.set_index("ticker").loc["920163.BJ", "source_ts_code"] == "838163.BJ"
    assert normal.set_index("ticker").loc["600519.SS", "close_cents"] == 1100
    assert set(normal["price_source_basis"]) == {"tushare.daily_unadjusted_nominal"}
    assert set(normal["market_session_position"]) == {0}
    with pytest.raises(spine.SpineError, match="off-calendar"):
        spine.normalise_daily_endpoint("daily", frame, "20240101", tmp_path)

    bak = _bak_rows("20240102")
    bak_b = bak.iloc[[0]].assign(ts_code="200012.SZ", name="南玻B")
    bak_result = spine.normalise_bak_basic(
        pd.concat([bak, bak_b], ignore_index=True), "20240102", tmp_path,
    )
    assert len(bak_result.landed_a) == 3
    assert bak_result.known_excluded["raw_ts_code"].tolist() == ["200012.SZ"]
    assert bak_result.quarantined_unknown.empty


def test_pit_collector_accounts_and_binds_legitimate_b_share_exclusion(tmp_path):
    _seed_reference(tmp_path)
    _seed_calendar(tmp_path)
    raw = pd.concat([
        _bak_rows("20240102"),
        _bak_rows("20240102").iloc[[0]].assign(ts_code="200012.SZ", name="南玻B"),
    ], ignore_index=True)

    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda *args, **kwargs: raw.copy(),
        now=lambda: NOW, max_requests=2,
    )
    assert collector.collect_pit_universe(date(2024, 1, 2), date(2024, 1, 2)) is True
    state = spine.load_state(tmp_path)
    record = state["units"]["bak_basic"]["20240102"]
    assert (
        record["source_row_count"], record["landed_a_row_count"],
        record["known_excluded_row_count"], record["quarantined_unknown_row_count"],
    ) == (4, 3, 1, 0)
    assert record["source_accounting_complete"] is True
    assert spine._unit_done(state, tmp_path, "bak_basic", "20240102") is True
    excluded = pd.read_parquet(spine._classification_partition(
        tmp_path, "known_excluded", "bak_basic", date(2024, 1, 2),
    ))
    assert excluded["raw_ts_code"].tolist() == ["200012.SZ"]


def test_daily_and_exact_limit_quotes_fail_closed_off_tick_or_partial(tmp_path):
    _seed_spine(tmp_path)
    off_tick_daily = _daily_rows("20240102")
    off_tick_daily["high"] = off_tick_daily["high"].astype(float)
    off_tick_daily.loc[0, "high"] = 11.005
    with pytest.raises(spine.SpineError, match="quote tick"):
        spine.normalise_daily_endpoint("daily", off_tick_daily, "20240102", tmp_path)

    off_tick_limit = _limit_rows("20240102")
    off_tick_limit["up_limit"] = off_tick_limit["up_limit"].astype(float)
    off_tick_limit.loc[0, "up_limit"] = 11.005
    with pytest.raises(spine.SpineError, match="quote tick"):
        spine.normalise_daily_endpoint("stk_limit", off_tick_limit, "20240102", tmp_path)

    partial_limit = _limit_rows("20240102")
    partial_limit.loc[0, "down_limit"] = None
    with pytest.raises(spine.SpineError, match="both upper/lower"):
        spine.normalise_daily_endpoint("stk_limit", partial_limit, "20240102", tmp_path)

    unchanged_upper = _limit_rows("20240102")
    unchanged_upper.loc[0, "up_limit"] = unchanged_upper.loc[0, "pre_close"]
    with pytest.raises(spine.SpineError, match="ordering"):
        spine.normalise_daily_endpoint("stk_limit", unchanged_upper, "20240102", tmp_path)

    one_tick_floor = _limit_rows("20240102")
    one_tick_floor[["pre_close", "down_limit", "up_limit"]] = one_tick_floor[[
        "pre_close", "down_limit", "up_limit",
    ]].astype(float)
    one_tick_floor.loc[0, ["pre_close", "down_limit", "up_limit"]] = [0.01, 0.01, 0.02]
    floored = spine.normalise_daily_endpoint(
        "stk_limit", one_tick_floor, "20240102", tmp_path,
    ).landed_a
    floor_row = floored.set_index("ticker").loc["600519.SS"]
    assert floor_row["pre_close_cents"] == floor_row["down_limit_cents"] == 1
    assert floor_row["up_limit_cents"] == 2

    invalid_volume = _daily_rows("20240102")
    invalid_volume["vol"] = invalid_volume["vol"].astype(float)
    invalid_volume.loc[0, "vol"] = float("inf")
    with pytest.raises(spine.SpineError, match="finite numeric"):
        spine.normalise_daily_endpoint("daily", invalid_volume, "20240102", tmp_path)

    off_tick_basic = _daily_basic_rows("20240102")
    off_tick_basic["close"] = off_tick_basic["close"].astype(float)
    off_tick_basic.loc[0, "close"] = 11.005
    with pytest.raises(spine.SpineError, match="quote tick"):
        spine.normalise_daily_endpoint("daily_basic", off_tick_basic, "20240102", tmp_path)

    invalid_status = _daily_basic_rows("20240102")
    invalid_status.loc[0, "limit_status"] = 7
    with pytest.raises(spine.SpineError, match="documented domain"):
        spine.normalise_daily_endpoint("daily_basic", invalid_status, "20240102", tmp_path)


def test_response_schema_and_request_binding_fail_closed():
    stock = _stock_basic_rows()[("SSE", "L")].copy()
    spine._validate_response_binding(
        "stock_basic", stock, {"exchange": "SSE", "list_status": "L"},
    )
    with pytest.raises(spine.SpineError, match="schema"):
        spine._validate_response_binding(
            "stock_basic", stock.drop(columns="symbol"),
            {"exchange": "SSE", "list_status": "L"},
        )
    crossed_status = stock.copy()
    crossed_status.loc[:, "list_status"] = "D"
    with pytest.raises(spine.SpineError, match="list_status"):
        spine._validate_response_binding(
            "stock_basic", crossed_status, {"exchange": "SSE", "list_status": "L"},
        )
    future_chinext = stock.copy()
    future_chinext.loc[0, ["ts_code", "symbol", "exchange", "market"]] = [
        "309901.SZ", "309901", "SZSE", "创业板",
    ]
    spine._validate_response_binding(
        "stock_basic", future_chinext, {"exchange": "SZSE", "list_status": "L"},
    )
    future_chinext.loc[0, "market"] = "主板"
    with pytest.raises(spine.SpineError, match="official board code range"):
        spine._validate_response_binding(
            "stock_basic", future_chinext,
            {"exchange": "SZSE", "list_status": "L"},
        )

    calendar = _calendar_frame("SSE")
    with pytest.raises(spine.SpineError, match="requested exchange"):
        spine._validate_response_binding(
            "trade_cal", calendar,
            {"exchange": "SZSE", "start_date": "20240101", "end_date": "20240103"},
        )
    with pytest.raises(spine.SpineError, match="trade_date"):
        spine._validate_response_binding(
            "daily", _daily_rows("20240103"), {"trade_date": "20240102"},
        )

    name = pd.DataFrame([{
        "ts_code": "600519.SH", "name": "贵州茅台", "start_date": "20200101",
        "end_date": None, "ann_date": "20250101", "change_reason": "改名",
    }], columns=spine.ENDPOINT_FIELDS["namechange"].split(","))
    with pytest.raises(spine.SpineError, match="announcement anchor"):
        spine._validate_response_binding(
            "namechange", name, {"start_date": "20240101", "end_date": "20241231"},
        )


def test_rejected_response_receipt_preserves_observed_rows_columns_and_hash(tmp_path):
    malformed = pd.DataFrame([{"ts_code": "600519.SH", "trade_date": "20240102"}])
    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda *args, **kwargs: malformed.copy(),
        now=lambda: NOW,
    )
    with pytest.raises(spine.SpineError, match="schema"):
        collector._call("daily", "20240102", trade_date="20240102")
    receipt_path = next((tmp_path / "receipts" / "requests" / "daily").rglob("*.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["response_status"] == "rejected_contract"
    assert receipt["response_row_count"] == 1
    assert receipt["response_columns"] == ["ts_code", "trade_date"]
    assert receipt["response_semantic_sha256"] == spine._raw_response_semantic_sha256(malformed)


def test_name_history_st_is_inference_and_classifies_every_source_row(tmp_path):
    _seed_reference(tmp_path)
    raw = pd.DataFrame([
        {"ts_code": "600519.SH", "name": "*ST茅台", "start_date": "20110101",
         "end_date": "20111231", "ann_date": "20101231", "change_reason": "ST"},
        {"ts_code": "600999.SH", "name": "旧名", "start_date": "20000101",
         "end_date": None, "ann_date": "20000101", "change_reason": "改名"},
        {"ts_code": "900901.SH", "name": "B股旧名", "start_date": "20000101",
         "end_date": None, "ann_date": "20000101", "change_reason": "改名"},
    ])
    normal = spine.normalise_name_history(raw, tmp_path, "2024-08-09")
    out = normal.landed_a
    assert normal.source_row_count == len(raw)
    assert normal.quarantined_unknown["raw_ts_code"].tolist() == ["600999.SH"]
    assert normal.known_excluded["raw_ts_code"].tolist() == ["900901.SH"]
    assert out.loc[out["ticker"] == "600519.SS", "is_st_name"].iloc[0]
    assert set(out["st_provenance"]) == {"namechange_name_inference_partial"}


def test_full_day_suspension_normalises_vendor_nan_timing_to_empty(tmp_path):
    _seed_spine(tmp_path)
    raw = pd.DataFrame([{
        "ts_code": "600519.SH",
        "trade_date": "20240102",
        "suspend_timing": float("nan"),
        "suspend_type": "S",
    }])
    result = spine.normalise_daily_endpoint("suspend_d", raw, "20240102", tmp_path)
    out = result.landed_a
    assert result.known_excluded.empty and result.quarantined_unknown.empty
    assert out.iloc[0]["suspend_timing"] == ""
    assert out.iloc[0]["suspend_type"] == "S"


def test_daily_collection_resumes_and_records_legitimate_empty_days(tmp_path):
    _seed_spine(tmp_path)
    calls: list[tuple[str, str]] = []

    def fake(endpoint, fields="", **params):
        trade_date = params["trade_date"]
        calls.append((endpoint, trade_date))
        if endpoint == "daily":
            return _daily_rows(trade_date)
        if endpoint == "daily_basic":
            return _daily_basic_rows(trade_date)
        if endpoint == "stk_limit":
            return _limit_rows(trade_date)
        return _empty(endpoint)

    first = spine.TushareAShareSpineCollector(
        tmp_path, query=fake, now=lambda: NOW, max_requests=20,
    )
    first.collect_daily(date(2024, 1, 2), date(2024, 1, 3), spine.DEFAULT_ENDPOINTS)
    assert len(calls) == 10
    state = spine.load_state(tmp_path)
    assert state["units"]["suspend_d"]["20240102"]["status"] == "empty"
    assert state["units"]["stock_st"]["20240103"]["status"] == "empty"
    daily = pd.read_parquet(tmp_path / "daily" / "year=2024" / "month=01" / "part.parquet")
    assert len(daily) == 4

    second_calls: list[tuple[str, str]] = []
    second = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda endpoint, **params: second_calls.append((endpoint, params.get("trade_date"))),
        now=lambda: NOW, max_requests=20,
    )
    second.collect_daily(date(2024, 1, 2), date(2024, 1, 3), spine.DEFAULT_ENDPOINTS)
    assert second_calls == []
    assert len(pd.read_parquet(
        tmp_path / "daily" / "year=2024" / "month=01" / "part.parquet"
    )) == 4


def test_unknown_source_rows_are_quarantined_and_block_completion(tmp_path):
    _seed_spine(tmp_path)
    base = _daily_rows("20240102")
    fund = base.iloc[[0]].assign(ts_code="510300.SH")
    unknown = base.iloc[[0]].assign(ts_code="600999.SH")
    raw = pd.concat([base, fund, unknown], ignore_index=True)

    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda *args, **kwargs: raw.copy(), now=lambda: NOW,
        max_requests=5,
    )
    collector.collect_daily(date(2024, 1, 2), date(2024, 1, 2), ("daily",))

    state = spine.load_state(tmp_path)
    record = state["units"]["daily"]["20240102"]
    assert record["status"] == "failed"
    assert record["source_accounting_complete"] is True
    assert (
        record["source_row_count"], record["landed_a_row_count"],
        record["known_excluded_row_count"], record["quarantined_unknown_row_count"],
    ) == (4, 2, 1, 1)
    excluded = pd.read_parquet(spine._classification_partition(
        tmp_path, "known_excluded", "daily", date(2024, 1, 2),
    ))
    quarantined = pd.read_parquet(spine._classification_partition(
        tmp_path, "quarantined_unknown", "daily", date(2024, 1, 2),
    ))
    assert excluded["raw_ts_code"].tolist() == ["510300.SH"]
    assert quarantined["raw_ts_code"].tolist() == ["600999.SH"]
    summary = spine._state_unit_summary(
        state, "daily", ["20240102"], tmp_path,
    )
    assert summary["complete"] is False
    assert summary["quarantined_unknown_row_count"] == 1
    assert summary["source_accounting_equations_hold"] is True


def test_terminal_units_bind_sparse_landed_and_classification_artifacts(tmp_path):
    _seed_spine(tmp_path)
    stock_st = pd.DataFrame([{
        "ts_code": "600519.SH", "name": "ST茅台", "trade_date": "20240102",
        "type": "ST", "type_name": "风险警示",
    }], columns=spine.ENDPOINT_FIELDS["stock_st"].split(","))
    _land_endpoint_day(tmp_path, "stock_st", "20240102", stock_st)
    state = spine.load_state(tmp_path)
    assert spine._unit_done(state, tmp_path, "stock_st", "20240102") is True
    spine._monthly_partition(tmp_path, "stock_st", date(2024, 1, 2)).unlink()
    assert spine._unit_done(state, tmp_path, "stock_st", "20240102") is False

    raw = pd.concat([
        _daily_rows("20240102"),
        _daily_rows("20240102").iloc[[0]].assign(ts_code="510300.SH"),
    ], ignore_index=True)
    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda *args, **kwargs: raw.copy(),
        now=lambda: NOW, max_requests=2,
    )
    collector.collect_daily(date(2024, 1, 2), date(2024, 1, 2), ("daily",))
    state = spine.load_state(tmp_path)
    assert spine._unit_done(state, tmp_path, "daily", "20240102") is True
    classification_path = spine._classification_partition(
        tmp_path, "known_excluded", "daily", date(2024, 1, 2),
    )
    classification_path.unlink()
    assert spine._unit_done(state, tmp_path, "daily", "20240102") is False

    _land_endpoint_day(tmp_path, "daily", "20240103", _daily_rows("20240103"))
    state = spine.load_state(tmp_path)
    assert spine._unit_done(state, tmp_path, "daily", "20240103") is True
    daily_path = spine._monthly_partition(tmp_path, "daily", date(2024, 1, 3))
    tampered = pd.read_parquet(daily_path)
    index = tampered.index[tampered["trade_date"] == "2024-01-03"][0]
    tampered.loc[index, "close_cents"] += 1
    spine._atomic_parquet(daily_path, tampered)
    assert spine._unit_done(state, tmp_path, "daily", "20240103") is False


def test_nonempty_fund_reference_is_bound_as_known_excluded_artifact(tmp_path):
    _seed_reference(tmp_path)
    state = spine.load_state(tmp_path)
    unit = f"{GENERATION}:L"
    record = state["units"]["fund_basic"][unit]
    assert record["landed_a_row_count"] == 0
    assert record["known_excluded_row_count"] == 1
    assert spine._unit_done(state, tmp_path, "fund_basic", unit) is True
    (tmp_path / record["partition"]).unlink()
    assert spine._unit_done(state, tmp_path, "fund_basic", unit) is False


def test_request_receipts_bind_date_ticker_exchange_and_canonical_location(tmp_path):
    _seed_spine(tmp_path)
    _land_endpoint_day(tmp_path, "daily", "20240102", _daily_rows("20240102"))

    def forge(
        embedded: dict, *, params: dict, path: Path | None = None,
    ) -> dict:
        endpoint = embedded["endpoint"]
        unit = embedded["unit"]
        fields = embedded["fields"]
        contract = {
            "endpoint": endpoint, "fields": fields,
            "params": dict(sorted(params.items())), "unit": unit,
        }
        digest = hashlib.sha256(spine._canonical_json_bytes(contract)).hexdigest()
        decoded = {key: value for key, value in embedded.items() if key != "path"}
        decoded.update({
            "params": contract["params"], "request_id": digest,
            "request_contract_sha256": digest,
        })
        target = path or spine._request_receipt_path(tmp_path, endpoint, unit, digest)
        spine._atomic_json(target, decoded)
        return {**decoded, "path": target.relative_to(tmp_path).as_posix()}

    state = spine.load_state(tmp_path)
    daily_record = state["units"]["daily"]["20240102"]
    daily_record["source_row_count"] += 1
    assert spine._unit_done(state, tmp_path, "daily", "20240102") is False

    state = spine.load_state(tmp_path)
    daily_record = state["units"]["daily"]["20240102"]
    wrong_date = forge(
        daily_record["request_receipts"][0], params={"trade_date": "20240103"},
    )
    daily_record["request_receipts"] = [wrong_date]
    assert spine._unit_done(state, tmp_path, "daily", "20240102") is False

    state = spine.load_state(tmp_path)
    daily_record = state["units"]["daily"]["20240102"]
    correct = daily_record["request_receipts"][0]
    displaced_path = tmp_path / "receipts" / "requests" / "daily" / "elsewhere" / (
        f"{correct['request_id']}.json"
    )
    displaced = forge(
        correct, params={"trade_date": "20240102"}, path=displaced_path,
    )
    daily_record["request_receipts"] = [displaced]
    assert spine._unit_done(state, tmp_path, "daily", "20240102") is False

    raw_shard = _daily_rows("20240102").iloc[[0]].copy()
    ticker = "600519.SS"
    shard_unit = f"20240102:{ticker}"
    shard_path = spine._shard_partition(tmp_path, "daily", date(2024, 1, 2), ticker)
    spine._atomic_parquet(shard_path, raw_shard)
    state = spine.load_state(tmp_path)
    spine._set_unit(
        state, tmp_path, "daily_shard", shard_unit, status="complete",
        observed_at=NOW.isoformat(), row_count=1, source_row_count=1,
        partition=shard_path, collection_method="per_ticker_shard",
        request_receipts=[_request_receipt(
            "daily", shard_unit, tmp_path, frame=raw_shard,
            params={"trade_date": "20240102", "ts_code": "600519.SH"},
        )],
    )
    state = spine.load_state(tmp_path)
    shard_record = state["units"]["daily_shard"][shard_unit]
    wrong_ticker = forge(
        shard_record["request_receipts"][0],
        params={"trade_date": "20240102", "ts_code": "000001.SZ"},
    )
    shard_record["request_receipts"] = [wrong_ticker]
    assert spine._unit_done(state, tmp_path, "daily_shard", shard_unit) is False

    state = spine.load_state(tmp_path)
    stock_unit = f"{GENERATION}:SSE:L"
    stock_record = state["units"]["stock_basic"][stock_unit]
    wrong_exchange = forge(
        stock_record["request_receipts"][0],
        params={"exchange": "SZSE", "list_status": "L"},
    )
    stock_record["request_receipts"] = [wrong_exchange]
    assert spine._unit_done(state, tmp_path, "stock_basic", stock_unit) is False


def test_end_to_end_bounded_collection_then_zero_call_resume(monkeypatch, tmp_path):
    monkeypatch.setattr(spine, "CALENDAR_HISTORY_START", date(2024, 1, 1))
    monkeypatch.setattr(spine, "NAME_HISTORY_START_YEAR", 2024)
    basic = _stock_basic_rows()
    calls: list[tuple[str, str]] = []

    def fake(endpoint, fields="", **params):
        calls.append((endpoint, str(params.get("trade_date") or params.get("list_status") or "")))
        if endpoint == "bse_mapping":
            return pd.DataFrame([{
                "name": "方大新材", "o_code": "838163.BJ", "n_code": "920163.BJ",
                "list_date": "20200727",
            }])
        if endpoint == "stock_basic":
            return basic[(params["exchange"], params["list_status"])].copy()
        if endpoint == "fund_basic":
            return _fund_basic_rows()[params["status"]].copy()
        if endpoint == "trade_cal":
            return _calendar_frame(params["exchange"])
        if endpoint == "bak_basic":
            return _bak_rows(params["trade_date"])
        if endpoint == "namechange":
            return _empty("namechange")
        trade_date = params["trade_date"]
        if endpoint == "daily":
            return _daily_rows(trade_date)
        if endpoint == "daily_basic":
            return _daily_basic_rows(trade_date)
        if endpoint == "stk_limit":
            return _limit_rows(trade_date)
        if endpoint == "suspend_d":
            return pd.DataFrame([{
                "ts_code": "920163.BJ", "trade_date": trade_date,
                "suspend_timing": None, "suspend_type": "S",
            }])
        return _empty("stock_st")

    result = spine.collect(
        start="20240101", end="20240103", store=tmp_path, query=fake,
        require_token=False, max_requests=40, now=lambda: NOW,
    )
    assert result["requests_made"] == 31
    assert result["capped"] is False
    assert result["manifest_complete"] is True, json.loads(
        (tmp_path / "completeness_manifest.json").read_text(encoding="utf-8")
    )
    assert len(calls) == 31

    def should_not_call(*args, **kwargs):
        raise AssertionError("a completed source unit was queried again")

    resumed = spine.collect(
        start="20240101", end="20240103", store=tmp_path, query=should_not_call,
        require_token=False, max_requests=40, now=lambda: NOW,
    )
    assert resumed["requests_made"] == 0
    assert resumed["manifest_complete"] is True


def test_documented_row_cap_uses_resumable_ticker_range_campaign(monkeypatch, tmp_path):
    _seed_spine(tmp_path)
    monkeypatch.setitem(spine.SOURCE_ROW_CAPS, "daily", 2)

    def fake(endpoint, fields="", **params):
        trade_date = params.get("trade_date") or params["start_date"]
        whole = _daily_rows(trade_date)
        requested = params.get("ts_code")
        if not requested:
            return whole
        match = whole[whole["ts_code"].map(spine._source_ts_code) == spine._source_ts_code(requested)]
        return match.reset_index(drop=True) if not match.empty else _empty("daily")

    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=fake, now=lambda: NOW,
        max_requests=5,
    )
    collector.collect_daily(date(2024, 1, 2), date(2024, 1, 2), ("daily",))
    record = spine.load_state(tmp_path)["units"]["daily"]["20240102"]
    assert record["status"] == "complete"
    assert record["collection_method"] == "per_ticker_range_shards"
    assert record["expected_ticker_count"] == 3
    assert record["source_accounting_complete"] is True
    state = spine.load_state(tmp_path)
    campaign = state["range_campaigns"]["daily"]
    assert campaign["status"] == "complete"
    # Three canonical tickers plus the historical BSE query alias.
    assert campaign["planned_leaf_count"] == 4
    assert campaign["completed_leaf_count"] == 4
    probe = campaign["cap_probe_receipt"]
    assert probe["response_status"] == "non_authoritative_cap_probe"
    assert probe["receipt_role"] == "discarded_non_authoritative_cap_probe"
    assert probe["discarded_probe_row_count"] == 2
    persisted_probe = json.loads((tmp_path / probe["path"]).read_text(encoding="utf-8"))
    assert persisted_probe == {key: value for key, value in probe.items() if key != "path"}
    request_summary = spine._request_receipts_summary(tmp_path)
    assert request_summary["discarded_non_authoritative_probe_rows"] == 2
    assert request_summary["response_status_counts"]["non_authoritative_cap_probe"] == 1
    summary = spine._state_unit_summary(
        spine.load_state(tmp_path), "daily", ["20240102"], tmp_path,
    )
    accounting = summary["unit_accounting"][0]
    assert accounting["collection_method"] == "per_ticker_range_shards"
    assert accounting["request_bound"] is True
    assert accounting["complete"] is True
    assert len(pd.read_parquet(
        tmp_path / "daily" / "year=2024" / "month=01" / "part.parquet"
    )) == 2

    plan = spine.crs.load_plan(tmp_path, campaign["campaign_id"])
    first_leaf = spine.crs.planned_leaves(plan)[0]
    artifact = next(
        (tmp_path / "source_range_shards" / "daily" / campaign["campaign_id"]).rglob(
            f"{first_leaf.leaf_id}.parquet"
        )
    )
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    assert spine._unit_done(state, tmp_path, "daily", "20240102") is False
    assert spine._state_unit_summary(
        state, "daily", ["20240102"], tmp_path,
    )["unit_accounting"][0]["request_bound"] is False


def test_ticker_range_campaign_converges_across_bounded_runs(monkeypatch, tmp_path):
    _seed_spine(tmp_path)
    monkeypatch.setitem(spine.SOURCE_ROW_CAPS, "daily", 2)

    def query(endpoint, fields="", **params):
        trade_date = params.get("trade_date") or params["start_date"]
        whole = _daily_rows(trade_date)
        requested = params.get("ts_code")
        if not requested:
            return whole
        match = whole[
            whole["ts_code"].map(spine._source_ts_code)
            == spine._source_ts_code(requested)
        ]
        return match.reset_index(drop=True) if not match.empty else _empty("daily")

    per_run_calls = []
    for _ in range(3):
        collector = spine.TushareAShareSpineCollector(
            tmp_path, query=query, now=lambda: NOW,
            max_requests=2,
        )
        collector.collect_daily(date(2024, 1, 2), date(2024, 1, 2), ("daily",))
        per_run_calls.append(collector.requests_made)
    assert per_run_calls == [2, 2, 1]
    state = spine.load_state(tmp_path)
    assert spine._unit_done(state, tmp_path, "daily", "20240102") is True
    campaign = state["range_campaigns"]["daily"]
    assert campaign["status"] == "complete"
    assert campaign["completed_leaf_count"] == campaign["planned_leaf_count"] == 4
    plan = spine.crs.load_plan(tmp_path, campaign["campaign_id"])
    assert spine.crs.pending_leaves(tmp_path, plan) == []
    assert "daily_shard" not in state["units"]


def test_dense_endpoint_key_coverage_catches_silent_underfill(tmp_path):
    _seed_spine(tmp_path)
    _land_endpoint_day(tmp_path, "daily", "20240102", _daily_rows("20240102"))
    one_name = _daily_basic_rows("20240102").iloc[:1].copy()
    _land_endpoint_day(tmp_path, "daily_basic", "20240102", one_name)
    coverage = spine._dense_key_coverage_vs_daily(
        tmp_path, "daily_basic", date(2024, 1, 2), date(2024, 1, 2),
    )
    assert coverage["daily_keys"] == 2
    assert coverage["covered_daily_keys"] == 1
    assert coverage["missing_daily_keys"] == 1
    assert coverage["complete"] is False


def _land_endpoint_day(store: Path, endpoint: str, trade_date: str, raw: pd.DataFrame) -> None:
    state = spine.load_state(store)
    if raw.empty:
        spine._set_unit(
            state, store, endpoint, trade_date, status="empty", observed_at=NOW.isoformat(),
            request_receipts=[_request_receipt(
                endpoint, trade_date, store, frame=raw,
                params={"trade_date": trade_date}, status="accepted_empty",
            )],
        )
        return
    normalised = spine.normalise_daily_endpoint(endpoint, raw, trade_date, store)
    normal = normalised.landed_a
    parsed = spine._parse_date(trade_date)
    path = spine._monthly_partition(store, endpoint, parsed)
    spine._replace_partition_units(
        path,
        normal,
        keys=spine.KEY_COLUMNS[endpoint],
        unit_column="trade_date",
        units=[parsed.isoformat()],
    )
    spine._set_unit(
        state, store, endpoint, trade_date, status="complete", observed_at=NOW.isoformat(),
        row_count=len(normal), source_row_count=len(raw),
        known_excluded_row_count=len(normalised.known_excluded),
        quarantined_unknown_row_count=len(normalised.quarantined_unknown), partition=path,
        request_receipts=[_request_receipt(
            endpoint, trade_date, store, frame=raw, params={"trade_date": trade_date},
        )],
    )


def test_canonical_event_substrate_uses_vendor_limits_not_reconstruction(tmp_path):
    _seed_spine(tmp_path)
    daily = _daily_rows("20240102")
    daily[["high", "close", "low"]] = daily[["high", "close", "low"]].astype(float)
    daily.loc[0, ["high", "close"]] = 10.99
    daily.loc[0, "low"] = 9.01
    limits = _limit_rows("20240102")
    limits[["up_limit", "down_limit"]] = limits[["up_limit", "down_limit"]].astype(float)
    limits.loc[0, "up_limit"] = 10.99
    limits.loc[0, "down_limit"] = 9.01
    _land_endpoint_day(tmp_path, "daily", "20240102", daily)
    daily_basic = _daily_basic_rows("20240102")
    daily_basic["close"] = daily_basic["close"].astype(float)
    daily_basic.loc[0, "close"] = 10.99
    _land_endpoint_day(tmp_path, "daily_basic", "20240102", daily_basic)
    _land_endpoint_day(tmp_path, "stk_limit", "20240102", limits)

    receipt = spine.build_canonical_event_substrate(
        tmp_path, date(2024, 1, 2), date(2024, 1, 2),
    )
    assert receipt["ready"] is True
    event = pd.read_parquet(
        tmp_path / "event_daily" / "year=2024" / "month=01" / "part.parquet"
    ).set_index("ticker")
    assert event.loc["600519.SS", "up_limit_cents"] == 1099
    assert event.loc["600519.SS", "touched_up"]
    assert event.loc["600519.SS", "event_price_authority"] == (
        "tushare.daily_unadjusted_plus_stk_limit_exact_daily"
    )
    assert spine.a_share_limit_price_bounds("10.00", "0.10").upper_cents == 1100


def test_event_substrate_rejects_quotes_outside_vendor_bounds(tmp_path):
    _seed_spine(tmp_path)
    limits = _limit_rows("20240102")
    limits[["up_limit", "down_limit"]] = limits[["up_limit", "down_limit"]].astype(float)
    limits.loc[0, ["up_limit", "down_limit"]] = [10.99, 9.01]
    _land_endpoint_day(tmp_path, "daily", "20240102", _daily_rows("20240102"))
    _land_endpoint_day(tmp_path, "daily_basic", "20240102", _daily_basic_rows("20240102"))
    _land_endpoint_day(tmp_path, "stk_limit", "20240102", limits)
    with pytest.raises(spine.SpineError, match="breached vendor-published"):
        spine.build_canonical_event_substrate(
            tmp_path, date(2024, 1, 2), date(2024, 1, 2),
        )


def test_event_substrate_audits_daily_basic_close_and_direction(tmp_path):
    _seed_spine(tmp_path)
    _land_endpoint_day(tmp_path, "daily", "20240102", _daily_rows("20240102"))
    _land_endpoint_day(tmp_path, "stk_limit", "20240102", _limit_rows("20240102"))
    mismatched_close = _daily_basic_rows("20240102")
    mismatched_close.loc[0, ["close", "limit_status"]] = [10, 0]
    _land_endpoint_day(tmp_path, "daily_basic", "20240102", mismatched_close)
    with pytest.raises(spine.SpineError, match="exact-close mismatch"):
        spine.build_canonical_event_substrate(
            tmp_path, date(2024, 1, 2), date(2024, 1, 2),
        )

    wrong_direction = _daily_basic_rows("20240102")
    wrong_direction.loc[1, "limit_status"] = 1
    _land_endpoint_day(tmp_path, "daily_basic", "20240102", wrong_direction)
    with pytest.raises(spine.SpineError, match="direction disagrees"):
        spine.build_canonical_event_substrate(
            tmp_path, date(2024, 1, 2), date(2024, 1, 2),
        )


def test_manifest_hashes_coverage_ore_and_schema(monkeypatch, tmp_path):
    _seed_spine(tmp_path)
    monkeypatch.setattr(spine, "CALENDAR_HISTORY_START", date(2024, 1, 1))
    monkeypatch.setattr(spine, "NAME_HISTORY_START_YEAR", 2024)
    state = spine.load_state(tmp_path)
    spine._set_unit(
        state, tmp_path, "namechange", "2024:20240103", status="empty",
        observed_at=NOW.isoformat(),
        request_receipts=[_request_receipt(
            "namechange", "2024:20240103", tmp_path, frame=_empty("namechange"),
            params={"start_date": "20240101", "end_date": "20240103"},
        )],
    )
    for compact in ("20240102", "20240103"):
        _land_endpoint_day(tmp_path, "daily", compact, _daily_rows(compact))
        _land_endpoint_day(tmp_path, "daily_basic", compact, _daily_basic_rows(compact))
        _land_endpoint_day(tmp_path, "stk_limit", compact, _limit_rows(compact))
        # The BSE name is missing from daily and is exactly accounted for as suspended.
        _land_endpoint_day(tmp_path, "suspend_d", compact, pd.DataFrame([{
            "ts_code": "920163.BJ", "trade_date": compact,
            "suspend_timing": None, "suspend_type": "S",
        }]))
        _land_endpoint_day(tmp_path, "stock_st", compact, _empty("stock_st"))

    manifest = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 3), spine.DEFAULT_ENDPOINTS,
        generated_at=NOW.isoformat(),
    )
    schema_path = Path(__file__).parents[1] / "contracts" / "cn_tushare_a_share_spine_manifest.v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
    # No cap fired here, so this run only witnesses the null branch; the populated
    # rangeCampaignSummary is proved by its own test below.
    assert manifest["range_campaigns"] == {
        endpoint: None for endpoint in spine.DENSE_ENDPOINTS
    }
    identity = manifest["manifest_identity_sha256"]
    unsigned = dict(manifest)
    unsigned.pop("manifest_identity_sha256")
    unsigned.pop("generated_at")
    assert identity == hashlib.sha256(spine._canonical_json_bytes(unsigned)).hexdigest()
    assert manifest["complete"] is True
    assert manifest["daily_security_coverage"]["eligible_security_observations"] == 6
    assert manifest["daily_security_coverage"]["daily_security_observations"] == 4
    assert manifest["daily_security_coverage"]["positive_volume_observations"] == 2
    assert manifest["daily_security_coverage"]["unexplained_missing_observations"] == 0
    assert len(manifest["reference"]["source_artifacts"]) == 17
    assert manifest["canonical_event_substrate"]["ready"] is True
    assert manifest["canonical_event_substrate"]["row_count"] == 4
    assert manifest["contracts"]["price_limit"]["canonical_storage"] == "integer CNY cents"
    assert "pre-2016 exact daily ST membership" in manifest["ore_ledger"]["not_tested"]
    compliance = manifest["contracts"]["compliance"]
    assert compliance == {
        "status": "CHAIRMAN_VERIFIED_PRIVATE / SATISFIED",
        "evidence_scope": "confidential_outside_coding_scope_nda_privacy",
        "runtime_gate": False,
    }
    assert "authorization" not in manifest and "authorization_ready" not in manifest
    assert manifest["reference"]["instrument_classification"]["rows"] == 5
    fund_summary = manifest["reference"]["source_units"]["fund_basic"]
    assert fund_summary["source_row_count"] == 1
    assert fund_summary["landed_A_row_count"] == 0
    assert fund_summary["known_excluded_row_count"] == 1
    for endpoint in (spine.PIT_UNIVERSE_ENDPOINT, *spine.DEFAULT_ENDPOINTS):
        assert manifest["endpoints"][endpoint]["coverage_pct"] == 100.0
        assert manifest["endpoints"][endpoint]["duplicate_key_rows"] == 0
    omitted_argument = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 3),
        ("daily", "stk_limit", "suspend_d", "stock_st"),
        generated_at=NOW.isoformat(),
    )
    assert set(omitted_argument["endpoints"]) == {
        spine.PIT_UNIVERSE_ENDPOINT, *spine.DEFAULT_ENDPOINTS,
    }
    assert omitted_argument["complete"] is True  # landed daily_basic remains a required receipt
    published = json.loads((tmp_path / "completeness_manifest.json").read_text(encoding="utf-8"))
    assert published == omitted_argument == manifest

    later = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 3), spine.DEFAULT_ENDPOINTS,
        generated_at="2026-08-09T12:00:00+00:00",
    )
    assert later["generated_at"] != manifest["generated_at"]
    assert later["manifest_identity_sha256"] == manifest["manifest_identity_sha256"]

    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", False)
    foundation_only = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 3), spine.DEFAULT_ENDPOINTS,
        generated_at=NOW.isoformat(),
    )
    assert foundation_only["bulk_historical_backfill_ready"] is False
    assert foundation_only["complete"] is False
    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", True)


def test_populated_range_campaign_summary_matches_manifest_schema(monkeypatch, tmp_path):
    """A live campaign is the only witness the rangeCampaigns $def is honest."""
    _seed_spine(tmp_path)
    monkeypatch.setattr(spine, "CALENDAR_HISTORY_START", date(2024, 1, 1))
    monkeypatch.setattr(spine, "NAME_HISTORY_START_YEAR", 2024)
    monkeypatch.setitem(spine.SOURCE_ROW_CAPS, "daily", 2)

    def fake(endpoint, fields="", **params):
        trade_date = params.get("trade_date") or params["start_date"]
        whole = _daily_rows(trade_date)
        requested = params.get("ts_code")
        if not requested:
            return whole
        match = whole[
            whole["ts_code"].map(spine._source_ts_code)
            == spine._source_ts_code(requested)
        ]
        return match.reset_index(drop=True) if not match.empty else _empty("daily")

    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=fake, now=lambda: NOW,
        max_requests=20,
    )
    collector.collect_daily(date(2024, 1, 2), date(2024, 1, 2), ("daily",))

    manifest = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 2), spine.DEFAULT_ENDPOINTS,
        generated_at=NOW.isoformat(),
    )
    schema_path = (
        Path(__file__).parents[1]
        / "contracts" / "cn_tushare_a_share_spine_manifest.v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)

    summary = manifest["range_campaigns"]["daily"]
    assert summary is not None
    assert manifest["range_campaigns"]["daily_basic"] is None
    assert manifest["range_campaigns"]["stk_limit"] is None
    assert summary["status"] == "complete"
    assert summary["cap_probe_count"] == 1
    assert summary["cap_probe_receipt"]["response_status"] == (
        "non_authoritative_cap_probe"
    )
    assert summary["terminal_campaign_receipt"]["status"] == "complete"
    assert summary["all_day_receipts_bound"] is True
    assert summary["source_accounting_complete"] is True
    # The paid raw payload never reaches the manifest; only receipts do.
    assert "rows" not in summary["cap_probe_receipt"]
    cap_fallback = manifest["contracts"]["cap_fallback"]
    assert cap_fallback["split_rule"] == summary["split_rule"]
    assert cap_fallback["live_canary_complete"] is False
    assert cap_fallback["live_canary_required_for_promotion"] is True


def test_underfilled_pit_and_matching_underfilled_daily_cannot_certify_full_a(
    monkeypatch, tmp_path,
):
    _seed_spine(tmp_path)
    monkeypatch.setattr(spine, "CALENDAR_HISTORY_START", date(2024, 1, 1))
    monkeypatch.setattr(spine, "NAME_HISTORY_START_YEAR", 2024)
    state = spine.load_state(tmp_path)
    spine._set_unit(
        state, tmp_path, "namechange", "2024:20240103", status="empty",
        observed_at=NOW.isoformat(),
        request_receipts=[_request_receipt(
            "namechange", "2024:20240103", tmp_path, frame=_empty("namechange"),
            params={"start_date": "20240101", "end_date": "20240103"},
        )],
    )
    for compact in ("20240102", "20240103"):
        parsed = spine._parse_date(compact)
        pit_path = spine._pit_partition(tmp_path, parsed)
        pit = pd.read_parquet(pit_path)
        pit = pit[
            ~((pit["trade_date"].astype(str) == parsed.isoformat())
              & (pit["ticker"].astype(str) == "920163.BJ"))
        ].reset_index(drop=True)
        spine._atomic_parquet(pit_path, pit)
        state = spine.load_state(tmp_path)
        day_rows = int((pit["trade_date"].astype(str) == parsed.isoformat()).sum())
        raw_underfilled = _bak_rows(compact)
        raw_underfilled = raw_underfilled[
            raw_underfilled["ts_code"] != "920163.BJ"
        ].reset_index(drop=True)
        spine._set_unit(
            state, tmp_path, "bak_basic", compact, status="complete",
            observed_at=NOW.isoformat(), row_count=day_rows, source_row_count=day_rows,
            partition=pit_path,
            request_receipts=[_request_receipt(
                "bak_basic", compact, tmp_path, frame=raw_underfilled,
                params={"trade_date": compact},
            )],
        )
        _land_endpoint_day(tmp_path, "daily", compact, _daily_rows(compact))
        _land_endpoint_day(tmp_path, "daily_basic", compact, _daily_basic_rows(compact))
        _land_endpoint_day(tmp_path, "stk_limit", compact, _limit_rows(compact))
        _land_endpoint_day(tmp_path, "suspend_d", compact, _empty("suspend_d"))
        _land_endpoint_day(tmp_path, "stock_st", compact, _empty("stock_st"))

    manifest = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 3), spine.DEFAULT_ENDPOINTS,
        generated_at=NOW.isoformat(),
    )
    reconciliation = manifest["pit_lifecycle_reconciliation"]
    assert reconciliation["lifecycle_missing_from_pit_count"] == 2
    assert reconciliation["complete"] is False
    assert manifest["daily_security_coverage"]["eligible_security_observations"] == 6
    assert manifest["daily_security_coverage"]["unexplained_missing_observations"] == 2
    assert manifest["complete"] is False


def test_missing_token_and_dry_run_are_network_free_and_do_not_expose_secret(monkeypatch, tmp_path):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    result = spine.collect(start="20240101", end="20240103", store=tmp_path)
    assert result["no_op"] is True and result["requests_made"] == 0
    assert list(tmp_path.iterdir()) == []
    dry = spine.collect(start="20240101", end="20240103", store=tmp_path, dry_run=True)
    assert dry["network_calls"] == 0 and dry["writes"] == 0
    assert "token" not in json.dumps(dry).lower()


def test_foundation_only_operational_gate_precedes_store_and_network(monkeypatch, tmp_path):
    """The surviving pre-network gate is technical readiness, nothing else."""
    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", False)
    store = tmp_path / "private-store"
    calls: list[str] = []

    with pytest.raises(spine.SpineError, match="foundation-only"):
        spine.collect(
            start="20240101", end="20240103", store=store,
            query=lambda endpoint, **kwargs: calls.append(endpoint),
            require_token=False,
        )
    assert calls == []
    assert not store.exists()


# ---------------------------------------------------------------------------
# The bounded canary window.  The bulk gate waits on canary evidence, so the
# canary must be runnable BEFORE the gate opens -- otherwise the promotion
# sequence is circular.  These tests pin that it is real, hard-bounded, and
# still cannot exercise the unproven scalable path.
# ---------------------------------------------------------------------------


def test_canary_window_runs_while_the_bulk_gate_is_still_closed(monkeypatch, tmp_path):
    """The evidence-gathering path is not blocked by the gate it feeds."""
    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", False)
    store = tmp_path / "private-store"
    result = spine.collect(
        start="20240102", end="20240103", store=store, max_requests=4,
        canary=True, require_token=False,
        query=lambda endpoint, **kwargs: None,
    )
    assert result["canary"] is True
    assert result["bulk_historical_backfill_ready"] is False
    assert result["dry_run"] is False and result["no_op"] is False
    # It really ran: the private store exists and the collector was constructed.
    assert store.exists()


def test_canary_refuses_bulk_budgets_and_oversized_windows(monkeypatch, tmp_path):
    """Hard ceilings are checked before any store or network use."""
    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", False)
    store = tmp_path / "private-store"
    calls: list[str] = []
    query = lambda endpoint, **kwargs: calls.append(endpoint)

    with pytest.raises(spine.SpineError, match="never bulk runs"):
        spine.collect(
            start="20240102", end="20240103", store=store, max_requests=4,
            canary=True, allow_bulk=True, require_token=False, query=query,
        )
    with pytest.raises(spine.SpineError, match=r"canary max_requests must be 1\.\."):
        spine.collect(
            start="20240102", end="20240103", store=store,
            max_requests=spine.CANARY_MAX_REQUESTS + 1,
            canary=True, require_token=False, query=query,
        )
    with pytest.raises(spine.SpineError, match="canary range is capped"):
        spine.collect(
            start="20240102", end="20240131", store=store, max_requests=4,
            canary=True, require_token=False, query=query,
        )
    assert calls == []
    assert not store.exists()


def test_canary_cannot_start_the_unproven_range_campaign(monkeypatch, tmp_path):
    """A documented row cap refuses inside a canary instead of going scalable."""
    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", False)
    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda endpoint, **kwargs: None, now=lambda: NOW,
        max_requests=4, canary=True,
    )
    assert collector.canary is True
    with pytest.raises(spine.SpineError, match="ticker-range campaign stays refused"):
        collector._activate_range_campaign(
            "daily", date(2024, 1, 2), date(2024, 1, 3),
            trigger_unit="2024-01-02", cap_probe_receipt={},
        )


def test_canary_collector_rejects_a_budget_above_the_ceiling(monkeypatch, tmp_path):
    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", False)
    with pytest.raises(spine.SpineError, match="canary window is capped"):
        spine.TushareAShareSpineCollector(
            tmp_path, query=lambda endpoint, **kwargs: None, now=lambda: NOW,
            max_requests=spine.CANARY_MAX_REQUESTS + 1, canary=True,
        )


def test_canary_is_not_a_promotion_and_leaves_the_bulk_gate_shut(monkeypatch, tmp_path):
    """Running a canary must never flip or imply the bulk gate."""
    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", False)
    store = tmp_path / "private-store"
    spine.collect(
        start="20240102", end="20240103", store=store, max_requests=2,
        canary=True, require_token=False, query=lambda endpoint, **kwargs: None,
    )
    assert spine.BULK_HISTORICAL_BACKFILL_READY is False
    # and the ordinary (non-canary) path is still refused afterwards
    with pytest.raises(spine.SpineError, match="foundation-only"):
        spine.collect(
            start="20240102", end="20240103", store=store, max_requests=2,
            require_token=False, query=lambda endpoint, **kwargs: None,
        )


def test_backfill_workflow_offers_plan_canary_and_gated_backfill():
    """The lane's modes match the executable sequence, not a circular one."""
    lane = Path(spine.__file__).resolve().parents[1] / ".github" / "workflows" / "tushare-spine-backfill.yml"
    text = lane.read_text(encoding="utf-8")
    assert "options: [plan, canary, backfill]" in text
    assert "ARGS+=(--canary)" in text
    assert "ARGS+=(--dry-run)" in text
    # backfill stays the gated one; nothing in the lane flips the gate or
    # smuggles a bulk budget into the collector (a prose mention is fine).
    assert "BULK_HISTORICAL_BACKFILL_READY = True" not in text
    assert "ARGS+=(--allow-bulk)" not in text


def test_backfill_lane_defaults_are_canary_safe():
    """`mode=canary` with untouched inputs must not fail on its own default.

    The lane shipped `max_requests: "50"` against a 12-request canary ceiling, so
    the documented operator path -- pick `canary`, press Run -- died before the
    first request. That is a trap, not a gate: the gate is `collect()` refusing a
    real over-ask, and it still does.
    """
    lane = Path(spine.__file__).resolve().parents[1] / ".github" / "workflows" / "tushare-spine-backfill.yml"
    text = lane.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    inputs = parsed[True]["workflow_dispatch"]["inputs"]
    default = int(inputs["max_requests"]["default"])
    assert 0 < default <= spine.CANARY_MAX_REQUESTS, (
        f"lane default {default} exceeds the canary ceiling "
        f"{spine.CANARY_MAX_REQUESTS}"
    )
    # The ceiling has one home: the lane reads it from the collector rather than
    # carrying a second copy that can drift upward.
    assert "s.CANARY_MAX_REQUESTS" in text
    # The clamp only ever shrinks, and only in canary mode.
    assert '[ "$MODE" = "canary" ] && [ "$MAX_REQUESTS" -gt "$CANARY_MAX_REQUESTS" ]' in text
    assert 'MAX_REQUESTS="$CANARY_MAX_REQUESTS"' in text
    # Nothing in the lane raises the ceiling.
    assert "CANARY_MAX_REQUESTS=" not in text.replace('CANARY_MAX_REQUESTS="$(python', "")


def test_private_store_path_cannot_escape_into_stageable_repo_locations(tmp_path):
    repo = Path(spine.__file__).resolve().parents[1]
    with pytest.raises(spine.SpineError, match="outside the repository"):
        spine._validate_private_store_path(repo / "data" / "cn_spine2")
    legacy = repo / "data" / "china_tushare_spine" / "private-generation"
    assert spine._validate_private_store_path(legacy) == legacy.resolve()
    assert spine._validate_private_store_path(tmp_path) == tmp_path.resolve()




def test_active_year_name_history_refreshes_and_orphans_gate(tmp_path, monkeypatch):
    _seed_reference(tmp_path)
    monkeypatch.setattr(spine, "NAME_HISTORY_START_YEAR", 2024)

    def query(endpoint, fields="", **params):
        assert endpoint == "namechange"
        return pd.DataFrame([{
            "ts_code": "600519.SH", "name": f"name-as-of-{params['end_date']}",
            "start_date": "20240101", "end_date": None,
            "ann_date": params["end_date"], "change_reason": "改名",
        }], columns=fields.split(","))

    first = spine.TushareAShareSpineCollector(
        tmp_path, query=query, now=lambda: NOW, max_requests=5,
    )
    first.collect_name_history(date(2024, 6, 30))
    second = spine.TushareAShareSpineCollector(
        tmp_path, query=query, now=lambda: NOW, max_requests=5,
    )
    second.collect_name_history(date(2024, 8, 9))
    history = pd.read_parquet(spine._name_partition(tmp_path, 2024))
    assert history["name"].tolist() == ["name-as-of-20240809"]
    state = spine.load_state(tmp_path)
    assert {"2024:20240630", "2024:20240809"}.issubset(state["units"]["namechange"])

    orphan_frame = pd.DataFrame([{
        "ts_code": "600999.SH", "name": "orphan", "start_date": "20240101",
        "end_date": None, "ann_date": "20240810", "change_reason": "改名",
    }], columns=spine.ENDPOINT_FIELDS["namechange"].split(","))
    orphan_collector = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda *args, **kwargs: orphan_frame.copy(),
        now=lambda: NOW, max_requests=5,
    )
    orphan_collector.collect_name_history(date(2024, 8, 10))
    orphan_record = spine.load_state(tmp_path)["units"]["namechange"]["2024:20240810"]
    assert orphan_record["status"] == "failed"
    assert orphan_record["unmatched_master_row_count"] == 1
    assert orphan_record["source_row_count"] == 1
    assert orphan_record["landed_a_row_count"] == 0
    assert orphan_record["quarantined_unknown_row_count"] == 1
    assert orphan_record["source_accounting_complete"] is True
    quarantine = pd.read_parquet(spine._classification_partition(
        tmp_path, "quarantined_unknown", "namechange", date(2024, 8, 10),
    ))
    assert quarantine["raw_ts_code"].tolist() == ["600999.SH"]


def test_interrupted_reference_refresh_never_moves_current_generation(tmp_path):
    _seed_reference(tmp_path)
    pointer_path = tmp_path / "reference" / "current_generation.json"
    before = json.loads(pointer_path.read_text(encoding="utf-8"))

    def query(endpoint, fields="", **params):
        assert endpoint == "bse_mapping"
        return pd.DataFrame([{
            "name": "方大新材", "o_code": "838163.BJ", "n_code": "920163.BJ",
            "list_date": "20200727",
        }], columns=fields.split(","))

    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=query, now=lambda: NOW, max_requests=1,
    )
    with pytest.raises(spine.RequestBudgetExhausted):
        collector.collect_reference(refresh=True)
    after = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert after == before
    state = spine.load_state(tmp_path)
    assert state["reference_generation"]["staging_id"] != before["generation_id"]


def test_reference_pointer_detects_tamper_and_collector_pins_one_verified_generation(
    monkeypatch, tmp_path,
):
    _seed_spine(tmp_path)
    calls = 0
    original = spine._reference_generation_semantic_sha256

    def counted(store, generation_id):
        nonlocal calls
        calls += 1
        return original(store, generation_id)

    monkeypatch.setattr(spine, "_reference_generation_semantic_sha256", counted)
    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda *args, **kwargs: _empty("daily"),
        now=lambda: NOW, max_requests=1,
    )
    assert calls == 1
    spine.normalise_daily_endpoint(
        "daily", _daily_rows("20240102"), "20240102", tmp_path,
        collector.reference_generation,
    )
    spine.normalise_daily_endpoint(
        "daily_basic", _daily_basic_rows("20240102"), "20240102", tmp_path,
        collector.reference_generation,
    )
    assert calls == 1

    master_path = spine._reference_derived_path(
        tmp_path, "security_master.parquet", collector.reference_generation,
    )
    tampered = pd.read_parquet(master_path)
    tampered.loc[0, "name"] = "tampered"
    spine._atomic_parquet(master_path, tampered)
    with pytest.raises(spine.SpineError, match="semantic hash does not match"):
        spine._current_reference_generation(tmp_path)


def test_response_semantic_identity_is_order_independent():
    first = pd.DataFrame([
        {"ts_code": "600519.SH", "name": "贵州茅台"},
        {"ts_code": "000001.SZ", "name": "平安银行"},
    ])
    reordered = first.iloc[::-1][["name", "ts_code"]].reset_index(drop=True)
    assert spine._raw_response_semantic_sha256(first) == spine._raw_response_semantic_sha256(
        reordered
    )


def test_decoded_secret_scan_blocks_compressed_values_before_write_and_after_read(
    monkeypatch, tmp_path,
):
    secret = "synthetic-paid-credential-never-log"
    path = tmp_path / "compressed.parquet"
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    spine._atomic_parquet(path, pd.DataFrame([{"opaque": secret}]))
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    with pytest.raises(spine.SpineError, match="decoded artifact values") as excinfo:
        spine._read_parquet_strict(path)
    assert secret not in str(excinfo.value)

    blocked = tmp_path / "blocked.parquet"
    with pytest.raises(spine.SpineError, match="decoded artifact values") as excinfo:
        spine._atomic_parquet(blocked, pd.DataFrame([{"opaque": secret}]))
    assert secret not in str(excinfo.value)
    assert not blocked.exists()

    category = pd.DataFrame({
        "category": pd.Categorical(["safe"], categories=["safe", secret]),
    })
    with pytest.raises(spine.SpineError, match="decoded artifact values"):
        spine._atomic_parquet(tmp_path / "category.parquet", category)
    indexed = pd.DataFrame(
        {"safe": [1]},
        index=pd.CategoricalIndex(
            pd.Categorical(["safe"], categories=["safe", secret]), name="identity",
        ),
    )
    with pytest.raises(spine.SpineError, match="decoded artifact values"):
        spine._atomic_parquet(tmp_path / "index.parquet", indexed)
    attributed = pd.DataFrame({"safe": [1]})
    attributed.attrs["vendor_metadata"] = {"credential": secret}
    with pytest.raises(spine.SpineError, match="decoded artifact values"):
        spine._atomic_parquet(tmp_path / "attrs.parquet", attributed)
    assert not (tmp_path / "attrs.parquet").exists()


def test_store_writer_lock_is_single_process_fail_closed(tmp_path):
    store = tmp_path / "spine"
    with (
        spine.spine_store_lock(store),
        pytest.raises(spine.SpineError, match="writer lock"),
        spine.spine_store_lock(store),
    ):
        pass


def test_parquet_atomic_promotion_scans_serialized_bytes_and_decoded_roundtrip(
    monkeypatch, tmp_path,
):
    secret = "synthetic-paid-credential-never-log"
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    target = tmp_path / "serialized-secret.parquet"

    def poisoned_write(self, path, **kwargs):
        Path(path).write_bytes(secret.encode("utf-8"))

    monkeypatch.setattr(pd.DataFrame, "to_parquet", poisoned_write)
    with pytest.raises(spine.SpineError, match="credential bytes"):
        spine._atomic_parquet(target, pd.DataFrame({"safe": [1]}))
    assert not target.exists()

    monkeypatch.undo()
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    original_read = pd.read_parquet

    def poisoned_read(path, *args, **kwargs):
        frame = original_read(path, *args, **kwargs)
        frame.attrs["vendor_metadata"] = secret
        return frame

    monkeypatch.setattr(pd, "read_parquet", poisoned_read)
    with pytest.raises(spine.SpineError, match="decoded artifact values"):
        spine._atomic_parquet(target, pd.DataFrame({"safe": [1]}))
    assert not target.exists()


def test_receipt_fails_before_hashing_configured_token_bytes(monkeypatch, tmp_path):
    secret = "synthetic-paid-credential-never-log"
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    path = tmp_path / "collection_state.json"
    path.write_bytes(f'{{"escaped":"{secret}"}}'.encode())
    with pytest.raises(spine.SpineError, match="configured credential bytes found") as excinfo:
        spine._json_file_receipt(path, tmp_path)
    assert secret not in str(excinfo.value)

    escaped = "".join(f"\\u{ord(character):04x}" for character in secret)
    path.write_text(f'{{"escaped":"{escaped}"}}', encoding="utf-8")
    with pytest.raises(spine.SpineError, match="decoded artifact values") as excinfo:
        spine._json_file_receipt(path, tmp_path)
    assert secret not in str(excinfo.value)


def test_unlimited_or_large_request_budget_requires_explicit_bulk_opt_in(tmp_path):
    with pytest.raises(spine.SpineError, match="safety ceiling"):
        spine.collect(start="20240101", end="20240103", store=tmp_path,
                      max_requests=0, require_token=False, query=lambda *a, **k: None)
    with pytest.raises(spine.SpineError, match="safety ceiling"):
        spine.collect(start="20240101", end="20240103", store=tmp_path,
                      max_requests=101, require_token=False, query=lambda *a, **k: None)


def test_corrupt_existing_partition_is_never_overwritten(tmp_path):
    path = tmp_path / "daily" / "year=2024" / "month=01" / "part.parquet"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not parquet")
    with pytest.raises(spine.SpineError, match="unreadable existing spine partition"):
        spine._upsert_partition(path, pd.DataFrame([{"trade_date": "2024-01-02", "ticker": "600519.SS"}]),
                                keys=["trade_date", "ticker"])
    assert path.read_bytes() == b"not parquet"


def test_exact_day_replacement_removes_vendor_tombstone_without_harming_other_day(tmp_path):
    _seed_spine(tmp_path)
    for compact in ("20240102", "20240103"):
        _land_endpoint_day(tmp_path, "suspend_d", compact, pd.DataFrame([{
            "ts_code": "600519.SH",
            "trade_date": compact,
            "suspend_timing": None,
            "suspend_type": "S",
        }]))
    path = tmp_path / "suspend_d" / "year=2024" / "month=01" / "part.parquet"
    rows, revised = spine._replace_partition_units(
        path,
        pd.DataFrame(),
        keys=spine.KEY_COLUMNS["suspend_d"],
        unit_column="trade_date",
        units=["2024-01-02"],
    )
    assert (rows, revised) == (1, 0)
    remaining = pd.read_parquet(path)
    assert remaining["trade_date"].tolist() == ["2024-01-03"]


# ---------------------------------------------------------------------------
# Anti-resurrection guards for the Chairman TuShare compliance override.
#
# DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE nulled the private
# license-document authorization subsystem.  Compliance is settled privately and
# is outside coding scope; these tests fail if any of it returns, under its own
# name or a rename, so a later session cannot quietly re-introduce a gate that
# demands confidential documents.
# ---------------------------------------------------------------------------

_LICENSE_GATE_IDENTIFIERS = (
    "AuthorizationGrant",
    "AUTHORIZATION_SCHEMA_VERSION",
    "AUTHORIZATION_TRUST_SCHEMA_VERSION",
    "AUTHORIZATION_REQUIRED_SCOPE",
    "AUTHORIZATION_RECORDED_SCOPE",
    "CODE_REVIEWED_AUTHORIZATION_TRUST_ALLOWLIST_SHA256",
    "load_authorization_grant",
    "_persist_authorization_grant",
    "_load_persisted_authorization",
    "_validate_public_authorization_trust",
    "_authorization_claim_sha256",
    "_verified_authorization_document",
    "_authorization_path",
    "_authorization_trust_path",
)

# Vocabulary that only appears when a license-document custody gate exists.
# Deliberately excludes ordinary vendor access words ("vendor_unavailable_or_
# unlicensed", entitlement-gap observations) that remain legitimate technical
# signals about endpoint access.
_LICENSE_GATE_VOCABULARY = (
    "authorization_receipt",
    "authorization-receipt",
    "authorization_trust_allowlist",
    "authorization-trust-allowlist",
    "grant_document_sha256",
    "grant_document_path",
    "written_authorization",
    "written authorization",
    "entitlement_chain",
    "vendor_delegation_document",
    "vendor_entitlement_document",
    "trust_allowlist_sha256",
    "cn_tushare_written_authorization",
)


def test_license_document_authorization_identifiers_cannot_return():
    """No removed license-gate symbol may exist on the spine module again."""
    present = sorted(name for name in _LICENSE_GATE_IDENTIFIERS if hasattr(spine, name))
    assert present == [], (
        "TuShare license-document authorization symbols reappeared: "
        f"{present}. Compliance is CHAIRMAN_VERIFIED_PRIVATE / SATISFIED and is "
        "outside coding scope (DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE)."
    )


def test_spine_source_carries_no_license_document_gate_vocabulary():
    """Source-level guard: catches a rename that re-adds the same mechanism."""
    source = Path(spine.__file__).read_text(encoding="utf-8").lower()
    found = sorted({token for token in _LICENSE_GATE_VOCABULARY if token in source})
    assert found == [], (
        f"license-document gate vocabulary reappeared in the spine source: {found}"
    )


def test_spine_ast_defines_no_license_document_gate_callable():
    """AST guard: no function/class/assignment may re-mint the removed gate."""
    import ast

    tree = ast.parse(Path(spine.__file__).read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = {node.name}
        elif isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = {node.target.id}
        else:
            continue
        for name in names:
            lowered = name.lower()
            if "authorization" in lowered or "trust_allowlist" in lowered:
                offenders.append(name)
    assert offenders == [], (
        f"spine re-declared a license-document authorization construct: {sorted(offenders)}"
    )


def test_collect_rejects_license_document_arguments():
    """The callable surface must not accept receipt/allowlist arguments again."""
    import inspect

    forbidden = {"authorization_receipt", "authorization_trust_allowlist", "authorization"}
    assert set(inspect.signature(spine.collect).parameters) & forbidden == set()
    assert set(
        inspect.signature(spine.TushareAShareSpineCollector.__init__).parameters
    ) & forbidden == set()

    with pytest.raises(TypeError):
        spine.collect(
            start="20240101", end="20240103", dry_run=True,
            authorization_receipt=Path("/nonexistent/receipt.json"),
        )


def test_cli_parser_exposes_no_license_document_flags(monkeypatch, capsys):
    """`--authorization-*` must be an unknown flag, not an accepted no-op."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "china_tushare_spine", "--start", "20240101", "--dry-run",
            "--authorization-receipt", "/tmp/receipt.json",
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        spine._main()
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "unrecognized arguments: --authorization-receipt" in err
    assert "--authorization" not in err.split("error:")[0]  # not offered in usage


def test_bounded_collection_needs_no_license_document(monkeypatch, tmp_path):
    """A normal bounded run proceeds with no license artifact anywhere."""
    monkeypatch.setattr(spine, "BULK_HISTORICAL_BACKFILL_READY", True)
    store = tmp_path / "private-store"
    result = spine.collect(start="20240101", end="20240103", store=store, dry_run=True)
    assert result["dry_run"] is True and result["network_calls"] == 0
    assert not any(store.glob("**/authorization*"))


def test_manifest_publishes_only_the_settled_compliance_status(tmp_path):
    """Manifest states the fact and nothing about private evidence."""
    manifest = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 3), spine.DEFAULT_ENDPOINTS,
        generated_at=NOW.isoformat(),
    )
    assert manifest["contracts"]["compliance"] == {
        "status": "CHAIRMAN_VERIFIED_PRIVATE / SATISFIED",
        "evidence_scope": "confidential_outside_coding_scope_nda_privacy",
        "runtime_gate": False,
    }
    blob = json.dumps(manifest).lower()
    for token in _LICENSE_GATE_VOCABULARY:
        assert token not in blob, f"manifest leaked license-gate field: {token}"


def test_bulk_readiness_gate_is_documented_as_technical_only():
    """`BULK_HISTORICAL_BACKFILL_READY` must never be re-titled a licensing gate."""
    source = Path(spine.__file__).read_text(encoding="utf-8")
    marker = "BULK_HISTORICAL_BACKFILL_READY = False"
    assert marker in source
    preamble = source.split(marker)[0].rsplit("\n\n", 1)[-1].lower()
    assert "technical readiness gate" in preamble
    assert "not a licensing gate" in preamble
    # The shipped default must stay False.  Read it from source, not from the
    # module attribute: the autouse fixture flips the runtime value so synthetic
    # collectors can exercise mechanics.
    assert "BULK_HISTORICAL_BACKFILL_READY = True" not in source
