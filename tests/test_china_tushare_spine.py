from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

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


def _seed_reference(
    store: Path, *, drop_stock_basic_ts_code: str | Sequence[str] | None = None,
) -> pd.DataFrame:
    """Seed the reference generation.

    ``drop_stock_basic_ts_code`` removes one or more ts_codes from the seeded
    stock_basic witness before the security master compiles -- used to prove
    T3's replay-invariance claim (DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION):
    a security absent from the CURRENT stock_basic snapshot but observed
    trading historically must not change the historical exact universe.
    """
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
    stock_basic_rows = _stock_basic_rows()
    if drop_stock_basic_ts_code is not None:
        drop_codes = (
            {drop_stock_basic_ts_code} if isinstance(drop_stock_basic_ts_code, str)
            else set(drop_stock_basic_ts_code)
        )
        stock_basic_rows = {
            key: frame[~frame["ts_code"].isin(drop_codes)].reset_index(drop=True)
            for key, frame in stock_basic_rows.items()
        }
    for (exchange, status), frame in stock_basic_rows.items():
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


def _seed_pit_day(store: Path, trade_date: str, *, extra_rows: pd.DataFrame | None = None) -> None:
    """Seed one bak_basic PIT day.

    ``extra_rows`` appends additional raw bak_basic rows (e.g. a ticker the
    current stock_basic witness has never carried) before normalising --
    used by T9 to build an end-to-end store containing witness-missing
    securities.
    """
    raw = _bak_rows(trade_date)
    if extra_rows is not None:
        raw = pd.concat([raw, extra_rows], ignore_index=True)
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
        witness_missing_row_count=int(normal.landed_a.get(
            "current_stock_basic_witness_missing", pd.Series(dtype=bool),
        ).sum()),
        request_receipts=[_request_receipt(
            "bak_basic", trade_date, store, frame=raw, params={"trade_date": trade_date},
        )],
    )


def _seed_spine(
    store: Path, *, drop_stock_basic_ts_code: str | Sequence[str] | None = None,
) -> pd.DataFrame:
    master = _seed_reference(store, drop_stock_basic_ts_code=drop_stock_basic_ts_code)
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


def _full_calendar_frame(exchange: str, start_compact: str, end_compact: str) -> pd.DataFrame:
    """A vendor trade_cal response covering every calendar day in [start, end],
    with every day marked open and an exact-adjacency pretrade_date (every
    day's previous session is the immediately preceding calendar day) so
    ``compile_market_sessions`` accepts the synthesized clock unmodified.
    """
    start = spine._parse_date(start_compact)
    end = spine._parse_date(end_compact)
    days = pd.date_range(start, end, freq="D")
    return pd.DataFrame([
        {
            "exchange": exchange,
            "cal_date": day.strftime("%Y%m%d"),
            "is_open": 1,
            "pretrade_date": (day - pd.Timedelta(days=1)).strftime("%Y%m%d"),
        }
        for day in days
    ])


def test_collect_calendars_writes_each_unit_to_its_own_year_partition(tmp_path):
    """Regression pin for the leaked-`year` defect: a multi-year calendar
    collection must land each unit's rows in ITS OWN year partition, never
    a neighboring year's file (the corruption exposed by canary run
    32921678076: SSE 2023's rows were written into year=2024.parquet).
    """
    def fake(endpoint, fields="", **params):
        assert endpoint == "trade_cal"
        return _full_calendar_frame(
            params["exchange"], params["start_date"], params["end_date"],
        )

    collector = spine.TushareAShareSpineCollector(tmp_path, query=fake, now=lambda: NOW)
    assert collector.collect_calendars(date(2023, 1, 1), date(2024, 1, 2)) is True

    year_2023 = pd.read_parquet(
        tmp_path / "reference" / "trade_calendar" / "year=2023.parquet",
    )
    year_2024 = pd.read_parquet(
        tmp_path / "reference" / "trade_calendar" / "year=2024.parquet",
    )
    # No cross-year pollution: each partition holds only its own year's dates.
    assert set(year_2023["cal_date"].astype(str).str[:4]) == {"2023"}
    assert set(year_2024["cal_date"].astype(str).str[:4]) == {"2024"}
    assert len(year_2023) == len(spine.CALENDAR_EXCHANGES) * 365
    assert len(year_2024) == len(spine.CALENDAR_EXCHANGES) * 2

    state = spine.load_state(tmp_path)
    units = [
        f"{exchange}:20230101:20231231" for exchange in spine.CALENDAR_EXCHANGES
    ] + [
        f"{exchange}:20240101:20240102" for exchange in spine.CALENDAR_EXCHANGES
    ]
    for unit in units:
        assert spine._unit_done(state, tmp_path, "trade_cal", unit) is True


def test_collect_calendars_writer_and_verifier_derive_the_same_partition(tmp_path):
    """`_expected_unit_partition_path` (the verifier) must agree with the
    partition the writer actually recorded for every collected unit --
    the invariant that lets `_set_unit`/`_unit_artifact_receipt` certify a
    unit without raising `SpineError: ... partition path disagrees with
    its unit`.
    """
    def fake(endpoint, fields="", **params):
        return _full_calendar_frame(
            params["exchange"], params["start_date"], params["end_date"],
        )

    collector = spine.TushareAShareSpineCollector(tmp_path, query=fake, now=lambda: NOW)
    assert collector.collect_calendars(date(2023, 1, 1), date(2024, 1, 2)) is True

    state = spine.load_state(tmp_path)
    units = state["units"]["trade_cal"]
    assert len(units) == 4
    for unit, record in units.items():
        expected = spine._expected_unit_partition_path(tmp_path, "trade_cal", unit, record)
        recorded = spine._contained_store_path(tmp_path, record["partition"])
        assert expected is not None
        assert expected.resolve(strict=False) == recorded.resolve(strict=False)


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


def _non_canonical_stock_basic_row(**overrides: Any) -> dict:
    """A T-prefixed legacy vendor code -- independently classifiable, run 32914960162's row."""
    row = {
        "ts_code": "T600018.SS", "symbol": "600018", "name": "早期退市样本",
        "area": "上海", "industry": "工业", "market": "主板", "exchange": "SSE",
        "curr_type": "CNY", "list_status": "D", "list_date": "19940101",
        "delist_date": "19990101", "is_hs": "N",
    }
    row.update(overrides)
    return row


def _unknown_noncanonical_stock_basic_row(**overrides: Any) -> dict:
    """A non-canonical code matching no known pattern -- genuinely unknown."""
    row = {
        "ts_code": "XX12345.Q", "symbol": "12345", "name": "未知样本",
        "area": "上海", "industry": "工业", "market": "主板", "exchange": "SSE",
        "curr_type": "CNY", "list_status": "D", "list_date": "19940101",
        "delist_date": "19990101", "is_hs": "N",
    }
    row.update(overrides)
    return row


def test_stock_basic_t_family_non_canonical_identity_known_excluded_not_fatal():
    """A T-prefixed legacy vendor code is known_excluded, not quarantined, not a crash."""
    columns = spine.ENDPOINT_FIELDS["stock_basic"].split(",")
    stock = _stock_basic_rows()[("SSE", "D")].copy()
    contaminated = pd.concat(
        [stock, pd.DataFrame([_non_canonical_stock_basic_row()], columns=columns)],
        ignore_index=True,
    )
    known_excluded, quarantined = spine._validate_response_binding(
        "stock_basic", contaminated, {"exchange": "SSE", "list_status": "D"},
    )
    assert known_excluded == [1]
    assert quarantined == []


def test_stock_basic_unknown_non_canonical_identity_stays_quarantined():
    """A non-T-family non-canonical code is genuinely unknown -- quarantined, not a crash."""
    columns = spine.ENDPOINT_FIELDS["stock_basic"].split(",")
    stock = _stock_basic_rows()[("SSE", "D")].copy()
    contaminated = pd.concat(
        [stock, pd.DataFrame([_unknown_noncanonical_stock_basic_row()], columns=columns)],
        ignore_index=True,
    )
    known_excluded, quarantined = spine._validate_response_binding(
        "stock_basic", contaminated, {"exchange": "SSE", "list_status": "D"},
    )
    assert known_excluded == []
    assert quarantined == [1]


def test_stock_basic_non_canonical_row_still_binds_request_literals():
    """A quarantine-eligible row still fails closed on a cross-wired response."""
    columns = spine.ENDPOINT_FIELDS["stock_basic"].split(",")
    wrong_exchange = pd.DataFrame(
        [_non_canonical_stock_basic_row(exchange="SZSE")], columns=columns,
    )
    with pytest.raises(spine.SpineError, match="requested exchange"):
        spine._validate_response_binding(
            "stock_basic", wrong_exchange, {"exchange": "SSE", "list_status": "D"},
        )

    wrong_status = pd.DataFrame(
        [_non_canonical_stock_basic_row(list_status="L")], columns=columns,
    )
    with pytest.raises(spine.SpineError, match="requested list_status"):
        spine._validate_response_binding(
            "stock_basic", wrong_status, {"exchange": "SSE", "list_status": "D"},
        )


def test_stock_basic_schema_mismatch_stays_fatal_even_with_a_non_canonical_row():
    columns = spine.ENDPOINT_FIELDS["stock_basic"].split(",")
    contaminated = pd.DataFrame([_non_canonical_stock_basic_row()], columns=columns)
    with pytest.raises(spine.SpineError, match="schema"):
        spine._validate_response_binding(
            "stock_basic", contaminated.drop(columns="symbol"),
            {"exchange": "SSE", "list_status": "D"},
        )


def test_stock_basic_all_canonical_response_reports_zero_non_canonical_and_stays_fatal_on_other_defects():
    stock = _stock_basic_rows()[("SSE", "L")].copy()
    known_excluded, quarantined = spine._validate_response_binding(
        "stock_basic", stock, {"exchange": "SSE", "list_status": "L"},
    )
    assert known_excluded == []
    assert quarantined == []

    bad_currency = stock.copy()
    bad_currency.loc[0, "curr_type"] = "USD"
    with pytest.raises(spine.SpineError, match="non-CNY"):
        spine._validate_response_binding(
            "stock_basic", bad_currency, {"exchange": "SSE", "list_status": "L"},
        )


def _reference_collector_for_contaminated_sse_d(tmp_path: Path, contaminated_row: dict):
    columns = spine.ENDPOINT_FIELDS["stock_basic"].split(",")
    basic = _stock_basic_rows()
    basic[("SSE", "D")] = pd.concat(
        [basic[("SSE", "D")], pd.DataFrame([contaminated_row], columns=columns)],
        ignore_index=True,
    )

    def fake(endpoint, fields="", **params):
        if endpoint == "bse_mapping":
            return pd.DataFrame([{
                "name": "方大新材", "o_code": "838163.BJ", "n_code": "920163.BJ",
                "list_date": "20200727",
            }])
        if endpoint == "stock_basic":
            return basic[(params["exchange"], params["list_status"])].copy()
        if endpoint == "fund_basic":
            return _fund_basic_rows()[params["status"]].copy()
        raise AssertionError(f"unexpected endpoint in reference-only test: {endpoint}")

    return spine.TushareAShareSpineCollector(tmp_path, query=fake, now=lambda: NOW)


def test_stock_basic_t_family_end_to_end_known_excluded_and_master_exclusion(tmp_path):
    """Full collect_reference -> compile_security_master path for run 32914960162's row.

    A T-family row is independently classifiable: it lands known_excluded
    (not quarantined_unknown), so the unit's zero-quarantine equation
    balances and _unit_done is satisfied for it -- the gate itself is
    untouched, but this observed legacy family no longer trips it, and the
    staging generation now promotes (unlike a genuinely unknown shape).
    """
    collector = _reference_collector_for_contaminated_sse_d(
        tmp_path, _non_canonical_stock_basic_row(),
    )
    # The call itself must not raise -- this is the exact scenario that crashed
    # the reference stage in run 32914960162.
    ready = collector.collect_reference()
    assert ready is True

    staging = collector.state["reference_generation"]["current_id"]
    assert staging
    assert collector.state["reference_generation"]["staging_id"] is None

    contaminated_unit = collector.state["units"]["stock_basic"][f"{staging}:SSE:D"]
    assert contaminated_unit["status"] == "complete"
    assert contaminated_unit["source_row_count"] == 2
    assert contaminated_unit["row_count"] == 1
    assert contaminated_unit["known_excluded_row_count"] == 1
    assert contaminated_unit["quarantined_unknown_row_count"] == 0
    assert contaminated_unit["source_accounting_complete"] is True
    assert (
        contaminated_unit["source_row_count"]
        == contaminated_unit["row_count"]
        + contaminated_unit["known_excluded_row_count"]
        + contaminated_unit["quarantined_unknown_row_count"]
    )
    contaminated_receipt = contaminated_unit["request_receipts"][0]
    assert contaminated_receipt["known_excluded_noncanonical_row_count"] == 1
    assert contaminated_receipt["non_canonical_identity_row_count"] == 1

    # _unit_done's zero-quarantine gate is untouched -- it is now satisfied
    # because this observed legacy family is classifiable, not because the
    # gate moved.
    assert spine._unit_done(collector.state, tmp_path, "stock_basic", f"{staging}:SSE:D") is True

    clean_unit = collector.state["units"]["stock_basic"][f"{staging}:SSE:L"]
    assert clean_unit["known_excluded_row_count"] == 0
    assert clean_unit["quarantined_unknown_row_count"] == 0
    clean_receipt = clean_unit["request_receipts"][0]
    assert clean_receipt["known_excluded_noncanonical_row_count"] == 0
    assert clean_receipt["non_canonical_identity_row_count"] == 0

    master, _ = spine.compile_security_master(tmp_path, staging)
    assert "T600018.SS" not in set(master["source_ts_code"])
    assert "T600018.SS" not in set(master["ticker"])
    # The normal rows in the same contaminated unit, and every other unit,
    # still land.
    assert "600001.SS" in set(master["ticker"])
    assert "600519.SS" in set(master["ticker"])
    assert "000001.SZ" in set(master["ticker"])
    assert "920163.BJ" in set(master["ticker"])

    classifications = spine._read_parquet_strict(
        spine._reference_derived_path(tmp_path, "instrument_classification.parquet", staging)
    )
    known_excluded_rows = classifications[
        (classifications["scope_classification"] == "known_out_of_scope")
        & (classifications["ticker"] == "T600018.SS")
    ]
    assert known_excluded_rows["ticker"].tolist() == ["T600018.SS"]
    assert known_excluded_rows["source_ts_code"].tolist() == ["T600018.SS"]
    assert known_excluded_rows["classification_source"].tolist() == [
        "official_A_code_scheme_excludes_T_prefixed_legacy_vendor_code",
    ]
    assert classifications[
        classifications["scope_classification"] == "quarantined_unknown"
    ].empty


def test_stock_basic_unknown_non_canonical_end_to_end_quarantined_blocks_unit_done(tmp_path):
    """A genuinely unknown non-canonical code stays quarantined and blocks _unit_done."""
    collector = _reference_collector_for_contaminated_sse_d(
        tmp_path, _unknown_noncanonical_stock_basic_row(),
    )
    ready = collector.collect_reference()
    # Quarantined rows keep completeness false (frozen law): the unit -- and
    # therefore the whole staging generation -- never claims to be "done".
    assert ready is False

    staging = collector.state["reference_generation"]["staging_id"]
    assert staging

    contaminated_unit = collector.state["units"]["stock_basic"][f"{staging}:SSE:D"]
    assert contaminated_unit["status"] == "complete"
    assert contaminated_unit["known_excluded_row_count"] == 0
    assert contaminated_unit["quarantined_unknown_row_count"] == 1
    contaminated_receipt = contaminated_unit["request_receipts"][0]
    assert contaminated_receipt["known_excluded_noncanonical_row_count"] == 0
    assert contaminated_receipt["non_canonical_identity_row_count"] == 1

    # The zero-quarantine gate is untouched: a genuinely unknown shape still
    # trips it.
    assert spine._unit_done(collector.state, tmp_path, "stock_basic", f"{staging}:SSE:D") is False

    master, _ = spine.compile_security_master(tmp_path, staging)
    assert "XX12345.Q" not in set(master["ticker"])
    classifications = spine._read_parquet_strict(
        spine._reference_derived_path(tmp_path, "instrument_classification.parquet", staging)
    )
    quarantined_rows = classifications[
        classifications["scope_classification"] == "quarantined_unknown"
    ]
    assert quarantined_rows["ticker"].tolist() == ["XX12345.Q"]


def _non_canonical_fund_basic_row(**overrides: Any) -> dict:
    """A non-6-digit legacy vendor fund code -- run 32918932199's row."""
    row = {
        "ts_code": "1610221.SZ", "name": "样本基金", "management": "样本基金管理",
        "custodian": "样本银行", "fund_type": "股票型", "found_date": "20050101",
        "due_date": None, "list_date": "20050101", "issue_date": "20041201",
        "delist_date": None, "issue_amount": 1, "m_fee": 0.5, "c_fee": 0.1,
        "duration_year": None, "p_value": 1, "min_amount": 0.1, "exp_return": None,
        "benchmark": "样本基准", "status": "L", "invest_type": "被动指数型",
        "type": "契约型开放式", "trustee": "", "purc_startdate": "20050101",
        "redm_startdate": "20050101", "market": "E",
    }
    row.update(overrides)
    return row


def test_fund_basic_non_canonical_identity_not_fatal_and_reported():
    """Run 32918932199's crash: a non-6-digit fund ts_code must not raise, and the
    row's ordinal is reported (quarantined, since it matches no independently
    classifiable family such as the T-prefix one)."""
    columns = spine.ENDPOINT_FIELDS["fund_basic"].split(",")
    fund = pd.DataFrame([_non_canonical_fund_basic_row()], columns=columns)
    known_excluded, quarantined = spine._validate_response_binding(
        "fund_basic", fund, {"market": "E", "status": "L"},
    )
    assert known_excluded == []
    assert quarantined == [0]


def test_fund_basic_non_canonical_row_still_binds_request_literals():
    """The literal market/status binding stays fatal even for a non-canonical row."""
    columns = spine.ENDPOINT_FIELDS["fund_basic"].split(",")
    wrong_market = pd.DataFrame(
        [_non_canonical_fund_basic_row(market="O")], columns=columns,
    )
    with pytest.raises(spine.SpineError, match="requested market/status"):
        spine._validate_response_binding(
            "fund_basic", wrong_market, {"market": "E", "status": "L"},
        )

    wrong_status = pd.DataFrame(
        [_non_canonical_fund_basic_row(status="D")], columns=columns,
    )
    with pytest.raises(spine.SpineError, match="requested market/status"):
        spine._validate_response_binding(
            "fund_basic", wrong_status, {"market": "E", "status": "L"},
        )


def test_fund_basic_call_succeeds_with_non_canonical_row_and_reports_receipt_count(tmp_path):
    """The exact crash from run 32918932199: TushareAShareSpineCollector._call must
    not raise on a well-bound fund_basic response carrying a non-canonical code."""
    fund = pd.DataFrame(
        [_non_canonical_fund_basic_row()], columns=spine.ENDPOINT_FIELDS["fund_basic"].split(","),
    )
    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda *args, **kwargs: fund.copy(), now=lambda: NOW,
    )
    response = collector._call("fund_basic", "ref-test:L", market="E", status="L")
    assert response.frame is not None
    assert response.receipt["response_status"] == "accepted"
    assert response.receipt["known_excluded_noncanonical_row_count"] == 0
    assert response.receipt["non_canonical_identity_row_count"] == 1


def _reference_collector_for_contaminated_fund_l(tmp_path: Path, contaminated_row: dict):
    columns = spine.ENDPOINT_FIELDS["fund_basic"].split(",")
    funds = _fund_basic_rows()
    funds["L"] = pd.concat(
        [funds["L"], pd.DataFrame([contaminated_row], columns=columns)],
        ignore_index=True,
    )

    def fake(endpoint, fields="", **params):
        if endpoint == "bse_mapping":
            return pd.DataFrame([{
                "name": "方大新材", "o_code": "838163.BJ", "n_code": "920163.BJ",
                "list_date": "20200727",
            }])
        if endpoint == "stock_basic":
            return _stock_basic_rows()[(params["exchange"], params["list_status"])].copy()
        if endpoint == "fund_basic":
            return funds[params["status"]].copy()
        raise AssertionError(f"unexpected endpoint in reference-only test: {endpoint}")

    return spine.TushareAShareSpineCollector(tmp_path, query=fake, now=lambda: NOW)


def test_fund_basic_non_canonical_end_to_end_stays_wholesale_known_excluded(tmp_path):
    """Full collect_reference -> compile_security_master path for run 32918932199's row.

    Unlike stock_basic, every fund_basic row -- canonical or not -- is already
    wholesale known_excluded in collect_reference's fund loop
    (row_count=0, known_excluded_row_count=len(frame)), so a non-canonical fund
    code needs no new quarantine slot of its own: the unit's existing
    source_row_count/known_excluded_row_count equation already balances, and
    the call and the compile must simply not crash.
    """
    collector = _reference_collector_for_contaminated_fund_l(
        tmp_path, _non_canonical_fund_basic_row(),
    )
    # The call itself must not raise -- this is the exact scenario that crashed
    # run 32918932199's fund_basic reference stage.
    ready = collector.collect_reference()
    assert ready is True

    staging = collector.state["reference_generation"]["current_id"]
    unit = f"{staging}:L"
    record = collector.state["units"]["fund_basic"][unit]
    assert record["source_row_count"] == 2
    assert record["landed_a_row_count"] == 0
    assert record["known_excluded_row_count"] == 2
    assert record["quarantined_unknown_row_count"] == 0
    assert (
        record["source_row_count"]
        == record["landed_a_row_count"]
        + record["known_excluded_row_count"]
        + record["quarantined_unknown_row_count"]
    )
    receipt = record["request_receipts"][0]
    assert receipt["non_canonical_identity_row_count"] == 1
    assert spine._unit_done(collector.state, tmp_path, "fund_basic", unit) is True

    # compile_security_master must not crash on the raw stored fund frame either
    # (its own fund loop re-parses ts_code independently of _validate_response_binding).
    master, _ = spine.compile_security_master(tmp_path, staging)
    classifications = spine._read_parquet_strict(
        spine._reference_derived_path(tmp_path, "instrument_classification.parquet", staging)
    )
    fund_rows = classifications[classifications["security_class"] == "exchange_fund"]
    assert "1610221.SZ" in set(fund_rows["ticker"])
    assert "1610221.SZ" in set(fund_rows["source_ts_code"])
    assert set(fund_rows["scope_classification"]) == {"known_out_of_scope"}
    non_canonical_source = fund_rows[fund_rows["ticker"] == "1610221.SZ"]
    assert non_canonical_source["classification_source"].tolist() == [
        "tushare.fund_basic_non_canonical_ts_code",
    ]


def _non_canonical_bse_mapping_row(**overrides: Any) -> dict:
    """A non-canonical vendor code in the BSE old-code -> 920-code alias table."""
    row = {
        "name": "样本", "o_code": "1234567.SZ", "n_code": "920163.BJ", "list_date": "20200727",
    }
    row.update(overrides)
    return row


def test_bse_alias_map_non_canonical_row_is_skipped_not_fatal():
    """A non-canonical o_code/n_code in bse_mapping does not crash alias building --
    it simply cannot alias, so it contributes no entry."""
    good = pd.DataFrame([{
        "name": "方大新材", "o_code": "838163.BJ", "n_code": "920163.BJ", "list_date": "20200727",
    }])
    contaminated = pd.concat(
        [good, pd.DataFrame([_non_canonical_bse_mapping_row()])], ignore_index=True,
    )
    aliases = spine._bse_alias_map(contaminated)
    assert aliases == {"838163.BJ": "920163.BJ"}


def test_bse_alias_map_non_bse_venue_still_fatal_for_a_canonical_row():
    """A canonically-parseable row that fails the BSE-venue semantic check stays
    fatal -- the classify-don't-crash treatment only applies to rows that fail
    canonical_identity itself, never to a parseable-but-wrong-venue row."""
    bad_venue = pd.DataFrame([{
        "name": "样本", "o_code": "600519.SH", "n_code": "920163.BJ", "list_date": "20200727",
    }])
    with pytest.raises(spine.SpineError, match="non-BSE row"):
        spine._bse_alias_map(bad_venue)


def test_bse_mapping_non_canonical_row_end_to_end_does_not_crash_reference_or_compile(tmp_path):
    """A non-canonical bse_mapping vendor row must not crash collect_reference (via
    _normalise_bse_mapping's validation call) or compile_security_master's own
    alias-row loop, which re-reads the raw stored bse_mapping parquet directly
    rather than going through _bse_alias_map."""
    def fake(endpoint, fields="", **params):
        if endpoint == "bse_mapping":
            return pd.DataFrame([
                {"name": "方大新材", "o_code": "838163.BJ", "n_code": "920163.BJ",
                 "list_date": "20200727"},
                _non_canonical_bse_mapping_row(),
            ])
        if endpoint == "stock_basic":
            return _stock_basic_rows()[(params["exchange"], params["list_status"])].copy()
        if endpoint == "fund_basic":
            return _fund_basic_rows()[params["status"]].copy()
        raise AssertionError(f"unexpected endpoint in reference-only test: {endpoint}")

    collector = spine.TushareAShareSpineCollector(tmp_path, query=fake, now=lambda: NOW)
    ready = collector.collect_reference()
    assert ready is True

    staging = collector.state["reference_generation"]["current_id"]
    master, alias_frame = spine.compile_security_master(tmp_path, staging)
    # The valid alias still lands; the non-canonical pair contributes nothing.
    assert "838163.BJ" in set(alias_frame["alias_ticker"])
    assert "920163.BJ" in set(master["ticker"])
    assert "1234567.SZ" not in set(alias_frame["alias_ticker"])


def test_daily_ticker_shard_response_crossing_requested_ts_code_stays_fatal():
    """A ticker-shard response for a foreign code IS the request subject (case
    2c in the non-canonical-identity sweep): it must stay fatal even though it
    is a row-level binding check, because a cross-wired response here is
    exactly the cross-wiring detector, never a legitimate non-canonical vendor
    payload shape."""
    with pytest.raises(spine.SpineError, match="crossed the requested ts_code"):
        spine._validate_response_binding(
            "daily", _daily_rows("20240102"),
            {"trade_date": "20240102", "ts_code": "600519.SH"},
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


# --- Mainland session-clock epoch --------------------------------------------
# The axis is frozen at MAINLAND_CALENDAR_EPOCH by DEFINITION, not by the
# absence of a pre-epoch partition on disk.  These pin that distinction: the
# hazard is a landed pre-epoch year silently occupying the low ordinals and
# shifting every session position with no error raised.

def _pre_epoch_calendar_frame(exchange: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"exchange": exchange, "cal_date": "19910101", "is_open": 0, "pretrade_date": "19901231"},
        {"exchange": exchange, "cal_date": "19910102", "is_open": 1, "pretrade_date": "19901231"},
        {"exchange": exchange, "cal_date": "19910103", "is_open": 1, "pretrade_date": "19910102"},
    ])


def _seed_pre_epoch_calendar(store: Path) -> None:
    """Land a pre-epoch partition for BOTH exchanges.

    Both venues are seeded on purpose: an asymmetric seed would be caught by the
    existing SSE/SZSE coverage-equality check, so it would not exercise the
    silent path this guards.
    """
    path = store / "reference" / "trade_calendar" / "year=1991.parquet"
    for exchange in spine.CALENDAR_EXCHANGES:
        frame = spine._normalise_calendar(
            _pre_epoch_calendar_frame(exchange), exchange, date(1991, 1, 1), date(1991, 1, 3),
        )
        spine._upsert_partition(path, frame, keys=spine.KEY_COLUMNS["trade_calendar"])


def test_collection_start_follows_the_frozen_epoch():
    assert spine.MAINLAND_CALENDAR_EPOCH == date(1992, 1, 1)
    assert spine.CALENDAR_HISTORY_START == spine.MAINLAND_CALENDAR_EPOCH
    assert spine.MAINLAND_CALENDAR_EPOCH_DEFINITION == "mainland-joint-complete-v1"
    assert spine.PRE_EPOCH_SOURCE_STATE == "PRE_EPOCH_SOURCE_UNSUPPORTED"


def test_compile_market_sessions_refuses_a_pre_epoch_start(tmp_path):
    _seed_calendar(tmp_path)
    with pytest.raises(spine.SpineError, match="PRE_EPOCH_SOURCE_UNSUPPORTED"):
        spine.compile_market_sessions(tmp_path, date(1991, 1, 1), date(2024, 1, 3))


def test_landed_pre_epoch_partition_never_enters_the_session_axis(tmp_path):
    """A pre-epoch year on disk must not shift a single ordinal."""
    baseline = _seed_calendar(tmp_path)
    assert list(baseline["trade_date"]) == ["2024-01-02", "2024-01-03"]
    assert list(baseline["market_session_position"]) == [0, 1]

    _seed_pre_epoch_calendar(tmp_path)
    recompiled = spine.compile_market_sessions(tmp_path, date(2024, 1, 1), date(2024, 1, 3))

    # Identical axis: the 1991 open sessions are excluded by definition, so
    # ordinal 0 still belongs to 2024-01-02 rather than 1991-01-02.
    assert list(recompiled["trade_date"]) == ["2024-01-02", "2024-01-03"]
    assert list(recompiled["market_session_position"]) == [0, 1]
    assert not (recompiled["trade_date"] < "1992-01-01").any()


def test_compiled_sessions_are_stamped_with_the_epoch_definition(tmp_path):
    sessions = _seed_calendar(tmp_path)
    assert set(sessions["calendar_epoch"]) == {"1992-01-01"}
    assert set(sessions["calendar_epoch_definition"]) == {"mainland-joint-complete-v1"}


def test_epoch_is_frozen_in_source_not_selected_at_runtime():
    """No runtime input may move the epoch."""
    source = Path("collectors/china_tushare_spine.py").read_text(encoding="utf-8")
    assert "MAINLAND_CALENDAR_EPOCH = date(1992, 1, 1)" in source
    # The epoch must never be derived from a store, an argument, or the clock.
    for forbidden in (
        "MAINLAND_CALENDAR_EPOCH =os.environ",
        'MAINLAND_CALENDAR_EPOCH = os.environ',
        "MAINLAND_CALENDAR_EPOCH = min(",
        "MAINLAND_CALENDAR_EPOCH = max(",
    ):
        assert forbidden not in source


def test_pre_epoch_exclusion_is_the_sole_cause_on_contiguous_history(tmp_path, monkeypatch):
    """Isolate the epoch filter from the other calendar guards.

    The 1991-vs-2024 fixture above is DISCONTINUOUS, so the pretrade_date
    adjacency check would also reject it -- that test proves the outcome but not
    the cause.  Real pre-epoch history is contiguous with the epoch year and
    sails past adjacency and both equality checks, which is exactly why the
    silent-ordinal-shift hazard exists.  Here the epoch is moved onto a
    contiguous fixture so nothing but the epoch filter can explain the result.
    """
    _seed_calendar(tmp_path)
    monkeypatch.setattr(spine, "MAINLAND_CALENDAR_EPOCH", date(2024, 1, 3))

    sessions = spine.compile_market_sessions(tmp_path, date(2024, 1, 3), date(2024, 1, 3))

    # 2024-01-02 is an open, contiguous, fully-attested session that every other
    # guard accepts.  Only the epoch keeps it off the axis.
    assert list(sessions["trade_date"]) == ["2024-01-03"]
    assert list(sessions["market_session_position"]) == [0]
    assert set(sessions["calendar_epoch"]) == {"2024-01-03"}


# --- vendor zero-sentinel dates ----------------------------------------------
# bak_basic returns "0" for an unpublished date where stock_basic returns "".
# Found the first time pit_universe ran against the real vendor: one descriptive
# field killed the whole unit.

def test_iso_treats_the_vendor_zero_sentinel_as_a_null_date():
    assert spine._iso("0") is None
    assert spine._iso(0) is None
    assert spine._iso("00000000") is None
    assert spine._iso("  0  ") is None


def test_iso_still_parses_real_dates_including_zero_heavy_ones():
    assert spine._iso("20240102") == "2024-01-02"
    assert spine._iso("1992-01-02") == "1992-01-02"
    # A zero-heavy but genuine date must survive: only an ALL-zero run is a
    # sentinel, and every real year carries a non-zero digit.
    assert spine._iso("20001010") == "2000-10-10"


def test_iso_still_refuses_a_malformed_date_rather_than_nulling_it():
    """The sentinel must not become a swallow-everything branch."""
    for bad in ("202401", "0000-00-00", "not-a-date", "20241301"):
        with pytest.raises(spine.SpineError, match="invalid date"):
            spine._iso(bad)


def test_bak_basic_row_with_a_zero_list_date_still_lands(tmp_path):
    """The row is a valid A-share; one unpublished field may not kill the unit.

    This is the exact shape that broke the first real pit_universe run: a
    `bak_basic` payload carrying list_date "0". Before the sentinel was
    recognised, normalise_bak_basic raised SpineError and took the whole unit
    with it.
    """
    _seed_reference(tmp_path)
    _seed_calendar(tmp_path)
    raw = _bak_rows("20240102")
    raw.loc[raw["ts_code"] == "600519.SH", "list_date"] = "0"

    normal = spine.normalise_bak_basic(raw, "20240102", tmp_path)

    landed = normal.landed_a.set_index("ticker")
    # It lands, with identity and session position intact...
    assert "600519.SS" in landed.index
    assert landed.loc["600519.SS", "market_session_position"] == 0
    # ...and the unpublished field is NULL, never invented. Assert nullness
    # rather than a particular spelling: pandas stores the None as NaN once the
    # column holds real date strings alongside it.
    assert pd.isna(landed.loc["600519.SS", "list_date"])
    # A sibling with a real list_date is untouched.
    assert landed.loc["000001.SZ", "list_date"] == "1991-04-03"
    # Source accounting still balances: nothing was dropped or quarantined.
    assert len(normal.quarantined_unknown) == 0
    assert len(normal.landed_a) == len(raw)


# --- DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION (Sol return-gate 10, T1-T9) ----
#
# Historical PIT construction is source-UNION, not current-stock_basic-
# snapshot intersection: a bak_basic row for a ticker the CURRENT stock_basic
# witness no longer publishes is a legal union member, not an unknown
# disposition.  Fail-closed is preserved exactly where it carries information
# (unparseable keys, non-A identities, and a PIT row that contradicts its own
# master lifecycle window); the current-snapshot omission rate is telemetry,
# never a threshold.


def _bak_row(columns: list[str], trade_date: str, ts_code: str, name: str, **overrides: Any) -> dict:
    row = {column: None for column in columns}
    row.update({
        "trade_date": trade_date, "ts_code": ts_code, "name": name,
        "industry": "样本", "area": "样本", "list_date": "19990101",
        "float_share": 1, "total_share": 1, "total_assets": 1,
        "liquid_assets": 1, "fixed_assets": 1, "holder_num": 1,
    })
    row.update(overrides)
    return row


def test_pit_row_absent_from_current_stock_basic_witness_lands_as_union_member(tmp_path):
    """T1 -- C1: a well-formed A-share bak_basic row whose ticker the CURRENT
    stock_basic snapshot no longer publishes still LANDS as a legal union
    member -- current_stock_basic_witness_missing True, a real identity, a
    market_session_position, zero quarantine, and a balanced source-row
    equation. Mirrors the ruling's own motivating exemplar, 300114.SZ."""
    _seed_reference(tmp_path)
    _seed_calendar(tmp_path)
    columns = spine.ENDPOINT_FIELDS["bak_basic"].split(",")
    raw = pd.DataFrame(
        [_bak_row(columns, "20240102", "300114.SZ", "中航电测")], columns=columns,
    )

    normal = spine.normalise_bak_basic(raw, "20240102", tmp_path)

    assert normal.quarantined_unknown.empty
    assert len(normal.landed_a) == 1
    landed = normal.landed_a.iloc[0]
    assert landed["ticker"] == "300114.SZ"
    assert landed["security_id"] == "CN-XSHE-300114"
    assert bool(landed["current_stock_basic_witness_missing"]) is True
    assert normal.landed_a["current_stock_basic_witness_missing"].dtype == bool
    assert landed["market_session_position"] == 0
    # Balanced source-row equation: source = landed_A + known_excluded + quarantined_unknown.
    assert normal.source_row_count == 1
    assert normal.source_row_count == (
        len(normal.landed_a) + len(normal.known_excluded) + len(normal.quarantined_unknown)
    )


def test_bak_basic_fail_closed_unparseable_and_non_a_share_rows_still_block(tmp_path):
    """T2 -- fail-closed halves of C1, preserved exactly (must not be
    relaxed by the ruling): an unparseable ts_code and a parseable-but-non-
    A-share identity both still quarantine, and in both cases the
    pit_universe unit is NOT terminal."""
    columns = spine.ENDPOINT_FIELDS["bak_basic"].split(",")
    cases = (
        ("00700.HK", "unparseable ts_code", "bak_basic_unparseable_ts_code"),
        ("510300.SH", "parseable non-A identity", "bak_basic_non_a_share_identity"),
    )
    for bad_code, name, expected_source in cases:
        store = tmp_path / bad_code.replace(".", "_")
        store.mkdir()
        _seed_reference(store)
        _seed_calendar(store)
        raw = pd.concat([
            _bak_rows("20240102"),
            pd.DataFrame([_bak_row(columns, "20240102", bad_code, name)], columns=columns),
        ], ignore_index=True)
        collector = spine.TushareAShareSpineCollector(
            store, query=lambda *args, **kwargs: raw.copy(),
            now=lambda: NOW, max_requests=2,
        )
        assert collector.collect_pit_universe(date(2024, 1, 2), date(2024, 1, 2)) is False
        state = spine.load_state(store)
        assert spine._unit_done(state, store, "bak_basic", "20240102") is False
        record = state["units"]["bak_basic"]["20240102"]
        assert record["status"] == "failed"
        assert record["quarantined_unknown_row_count"] == 1
        assert record["landed_a_row_count"] == 3
        quarantine = pd.read_parquet(spine._classification_partition(
            store, "quarantined_unknown", "bak_basic", date(2024, 1, 2),
        ))
        assert quarantine["classification_source"].tolist() == [expected_source]


def test_replay_invariance_deleting_a_traded_security_from_stock_basic_witness(tmp_path):
    """T3 -- REPLAY-INVARIANCE PROOF, the ruling's own acceptance criterion and
    the most important test in the change. Deleting a security that
    demonstrably TRADED a session from the CURRENT stock_basic witness must
    not change the historical exact universe or the event result -- only
    witness-coverage TELEMETRY may differ.

    run A: the full seeded stock_basic witness.
    run B: identical, except 600519.SS (positive-volume daily row + stk_limit
           evidence on both sessions) is absent from stock_basic.
    """
    def _build(store: Path, *, drop: str | None) -> pd.DataFrame:
        store.mkdir()
        master = _seed_reference(store, drop_stock_basic_ts_code=drop)
        _seed_calendar(store)
        for trade_date in ("20240102", "20240103"):
            _seed_pit_day(store, trade_date)
            _land_endpoint_day(store, "daily", trade_date, _daily_rows(trade_date))
            _land_endpoint_day(store, "daily_basic", trade_date, _daily_basic_rows(trade_date))
            _land_endpoint_day(store, "stk_limit", trade_date, _limit_rows(trade_date))
        return master

    store_a, store_b = tmp_path / "run_a", tmp_path / "run_b"
    master_a = _build(store_a, drop=None)
    master_b = _build(store_b, drop="600519.SS")

    sessions_a = spine._read_parquet_strict(store_a / "reference" / "market_sessions.parquet")
    sessions_b = spine._read_parquet_strict(store_b / "reference" / "market_sessions.parquet")

    # The historical exact universe is IDENTICAL.
    for trade_date in ("2024-01-02", "2024-01-03"):
        eligible_a = spine._eligible_tickers_with_pit(store_a, master_a, trade_date)
        eligible_b = spine._eligible_tickers_with_pit(store_b, master_b, trade_date)
        assert eligible_a == eligible_b
        assert "600519.SS" in eligible_a

    recon_a = spine._pit_lifecycle_reconciliation(
        store_a, master_a, sessions_a, date(2024, 1, 2), date(2024, 1, 3),
    )
    recon_b = spine._pit_lifecycle_reconciliation(
        store_b, master_b, sessions_b, date(2024, 1, 2), date(2024, 1, 3),
    )
    assert recon_a["frozen_union_semantic_sha256"] == recon_b["frozen_union_semantic_sha256"]
    assert recon_a["union_observation_count"] == recon_b["union_observation_count"]
    assert recon_a["complete"] is True
    assert recon_b["complete"] is True

    # The event result is IDENTICAL.
    substrate_a = spine.build_canonical_event_substrate(store_a, date(2024, 1, 2), date(2024, 1, 3))
    substrate_b = spine.build_canonical_event_substrate(store_b, date(2024, 1, 2), date(2024, 1, 3))
    assert substrate_a["ready"] is True and substrate_b["ready"] is True

    def _event_rows(store: Path) -> pd.DataFrame:
        parts = sorted((store / "event_daily").glob("year=*/month=*/part.parquet"))
        frame = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
        return frame.sort_values(["trade_date", "ticker"], kind="stable").reset_index(drop=True)

    event_a = _event_rows(store_a)
    event_b = _event_rows(store_b)
    compare_columns = [
        "trade_date", "ticker", "event_eligible", "touched_up", "sealed_up",
        "touched_down", "sealed_down", "close_cents", "up_limit_cents", "down_limit_cents",
    ]
    pd.testing.assert_frame_equal(
        event_a[compare_columns].reset_index(drop=True),
        event_b[compare_columns].reset_index(drop=True),
    )

    # ONLY witness-coverage metadata differs.
    pit_a = spine._read_parquet_strict(spine._pit_partition(store_a, date(2024, 1, 2)))
    pit_b = spine._read_parquet_strict(spine._pit_partition(store_b, date(2024, 1, 2)))
    pit_a_day = pit_a[pit_a["trade_date"] == "2024-01-02"].set_index("ticker")
    pit_b_day = pit_b[pit_b["trade_date"] == "2024-01-02"].set_index("ticker")
    assert bool(pit_a_day.loc["600519.SS", "current_stock_basic_witness_missing"]) is False
    assert bool(pit_b_day.loc["600519.SS", "current_stock_basic_witness_missing"]) is True
    # witness_missing_row_count (C3, per-unit) and pit_absent_from_master_count
    # (C2, range-level) deliberately count different things and must not be
    # collapsed into one counter: the former is PER SESSION -- 600519.SS is
    # witness-missing once on 2024-01-02 -- while the latter is a
    # (trade_date, ticker) OBSERVATION count accumulated across every
    # requested session in the reconciled range, exactly like its siblings
    # lifecycle_missing_from_pit_count/pit_missing_from_lifecycle_count. Two
    # sessions (2024-01-02, 2024-01-03) each observe 600519.SS witness-missing
    # once, so the range-level count is 2, not 1 -- and current_snapshot_
    # omission_rate's denominator (union_observation_count) is itself an
    # observation count, so the numerator must be an observation count too.
    state_b = spine.load_state(store_b)
    assert state_b["units"]["bak_basic"]["20240102"]["witness_missing_row_count"] == 1
    assert recon_b["pit_absent_from_master_count"] == 2
    assert recon_a["pit_absent_from_master_count"] == 0
    assert recon_b["current_snapshot_omission_rate"] > 0
    assert recon_a["current_snapshot_omission_rate"] == 0.0


def test_pit_row_contradicting_master_lifecycle_window_still_blocks(tmp_path):
    """T4 -- fail-closed half of C2, must not be forgotten: a PIT row for a
    ticker that IS in the security master, but whose own lifecycle window
    does not cover the observed trade_date, is an unresolved source
    contradiction and keeps blocking -- unlike a witness-missing row."""
    _seed_reference(tmp_path)
    _seed_calendar(tmp_path)
    _seed_pit_day(tmp_path, "20240102")

    master = spine._read_parquet_strict(
        spine._reference_derived_path(tmp_path, "security_master.parquet", GENERATION),
    ).copy()
    # 600519.SS is a legitimate PIT observation on 2024-01-02, but its OWN
    # master lifecycle window is set to have closed before that date -- a
    # genuine unresolved source contradiction, not a witness-missing case.
    master.loc[master["ticker"] == "600519.SS", "effective_to"] = "2020-01-01"

    sessions = spine._read_parquet_strict(tmp_path / "reference" / "market_sessions.parquet")
    recon = spine._pit_lifecycle_reconciliation(
        tmp_path, master, sessions, date(2024, 1, 2), date(2024, 1, 2),
    )
    assert recon["pit_lifecycle_window_conflict_count"] == 1
    assert recon["pit_lifecycle_window_conflict_sample"] == [
        {"trade_date": "2024-01-02", "ticker": "600519.SS"},
    ]
    assert recon["pit_absent_from_master_count"] == 0
    assert recon["complete"] is False


def test_pit_only_ticker_survives_into_name_history_and_daily_endpoints(tmp_path):
    """T5 -- C5 proof (not a rebuild): a PIT-only, witness-missing ticker is
    accepted by name_history and by a daily endpoint, proving the
    survivorship filter is not recreated one stage later."""
    _seed_reference(tmp_path, drop_stock_basic_ts_code="600519.SS")
    _seed_calendar(tmp_path)
    _seed_pit_day(tmp_path, "20240102")

    pit = spine._read_parquet_strict(spine._pit_partition(tmp_path, date(2024, 1, 2)))
    landed = pit.set_index("ticker").loc["600519.SS"]
    assert bool(landed["current_stock_basic_witness_missing"]) is True

    daily_normal = spine.normalise_daily_endpoint(
        "daily", _daily_rows("20240102"), "20240102", tmp_path,
    )
    assert "600519.SS" in set(daily_normal.landed_a["ticker"])
    assert daily_normal.quarantined_unknown.empty

    namechange_raw = pd.DataFrame([{
        "ts_code": "600519.SH", "name": "贵州茅台", "start_date": "20240101",
        "end_date": None, "ann_date": "20240101", "change_reason": "更名",
    }])
    name_normal = spine.normalise_name_history(namechange_raw, tmp_path, "20240102")
    assert "600519.SS" in set(name_normal.landed_a["ticker"])
    assert name_normal.quarantined_unknown.empty


def test_pit_only_ticker_without_trading_evidence_is_not_event_eligible(tmp_path):
    """T6 -- ruling's clause 5: a PIT-observed row WITHOUT authority-grade
    trading evidence remains source-accounted (it still lands in the joined
    event substrate) but is NOT promoted to event-eligible."""
    _seed_reference(tmp_path, drop_stock_basic_ts_code="600519.SS")
    _seed_calendar(tmp_path)
    _seed_pit_day(tmp_path, "20240102")

    # 600519.SS (witness-missing, PIT-only) trades flat with zero volume;
    # 000001.SZ carries the up-limit touch instead, so every limit_status/
    # direction audit in build_canonical_event_substrate stays internally
    # consistent.
    daily = pd.DataFrame([
        {"ts_code": "600519.SH", "trade_date": "20240102", "open": 10, "high": 10, "low": 10,
         "close": 10, "pre_close": 10, "change": 0, "pct_chg": 0, "vol": 0, "amount": 0},
        {"ts_code": "000001.SZ", "trade_date": "20240102", "open": 10, "high": 11, "low": 9,
         "close": 11, "pre_close": 10, "change": 1, "pct_chg": 10, "vol": 100, "amount": 1000},
    ])
    daily_basic = pd.DataFrame([
        {"ts_code": code, "trade_date": "20240102",
         "close": 11 if code == "000001.SZ" else 10, "turnover_rate": 1,
         "turnover_rate_f": 2, "volume_ratio": 1, "pe": 10, "pe_ttm": 11, "pb": 2,
         "ps": 3, "ps_ttm": 3, "dv_ratio": 1, "dv_ttm": 1, "total_share": 100,
         "float_share": 80, "free_share": 60, "total_mv": 1000, "circ_mv": 800,
         "limit_status": 2 if code == "000001.SZ" else 0}
        for code in ("600519.SH", "000001.SZ")
    ])[spine.ENDPOINT_FIELDS["daily_basic"].split(",")]
    limits = _limit_rows("20240102")

    _land_endpoint_day(tmp_path, "daily", "20240102", daily)
    _land_endpoint_day(tmp_path, "daily_basic", "20240102", daily_basic)
    _land_endpoint_day(tmp_path, "stk_limit", "20240102", limits)

    substrate = spine.build_canonical_event_substrate(tmp_path, date(2024, 1, 2), date(2024, 1, 2))
    assert substrate["ready"] is True
    event = pd.read_parquet(
        tmp_path / "event_daily" / "year=2024" / "month=01" / "part.parquet"
    ).set_index("ticker")
    assert "600519.SS" in event.index  # source-accounted
    row = event.loc["600519.SS"]
    assert bool(row["positive_volume"]) is False
    assert bool(row["source_limits_present"]) is True
    assert bool(row["event_eligible"]) is False


def test_current_snapshot_omission_rate_is_telemetry_never_a_threshold(tmp_path):
    """T7 -- C3: no threshold exists on the omission rate. A store whose
    omission rate is HIGH still reaches complete when nothing else is
    wrong -- the omission rate is telemetry, never a completion gate."""
    _seed_reference(tmp_path, drop_stock_basic_ts_code=["600519.SS", "000001.SZ"])
    _seed_calendar(tmp_path)
    _seed_pit_day(tmp_path, "20240102")

    master = spine._read_parquet_strict(
        spine._reference_derived_path(tmp_path, "security_master.parquet", GENERATION),
    )
    sessions = spine._read_parquet_strict(tmp_path / "reference" / "market_sessions.parquet")
    recon = spine._pit_lifecycle_reconciliation(
        tmp_path, master, sessions, date(2024, 1, 2), date(2024, 1, 2),
    )
    # 2 of the 3 PIT tickers are witness-missing this session: a high rate.
    assert recon["pit_absent_from_master_count"] == 2
    assert recon["current_snapshot_omission_rate"] == pytest.approx(2 / 3)
    assert recon["pit_lifecycle_window_conflict_count"] == 0
    assert recon["complete"] is True
    # No threshold constant exists anywhere on the module (a MAX_OMISSION_RATE
    # would smuggle the survivorship filter back in as a tunable).
    assert not any("OMISSION" in name and "RATE" in name for name in dir(spine))


def test_witness_missing_pit_ticker_without_daily_row_is_coverage_telemetry_not_gap(tmp_path):
    """T8(a) -- C6, half one: a witness-missing PIT ticker with NO daily
    observation does not appear in unexplained_missing_n, appears in
    pit_only_without_daily_n instead, and the coverage receipt still
    reports complete True."""
    _seed_reference(tmp_path, drop_stock_basic_ts_code="600519.SS")
    _seed_calendar(tmp_path)
    _seed_pit_day(tmp_path, "20240102")

    daily = _daily_rows("20240102")
    daily = daily[daily["ts_code"] != "600519.SH"].reset_index(drop=True)
    daily = pd.concat([daily, pd.DataFrame([{
        "ts_code": "920163.BJ", "trade_date": "20240102", "open": 5, "high": 5, "low": 5,
        "close": 5, "pre_close": 5, "change": 0, "pct_chg": 0, "vol": 10, "amount": 50,
    }])], ignore_index=True)
    _land_endpoint_day(tmp_path, "daily", "20240102", daily)
    _land_endpoint_day(tmp_path, "suspend_d", "20240102", _empty("suspend_d"))

    state = spine.load_state(tmp_path)
    coverage = spine.build_daily_security_coverage(
        tmp_path, date(2024, 1, 2), date(2024, 1, 2), state, GENERATION,
    )
    row = coverage.iloc[0]
    assert row["pit_only_without_daily_n"] == 1
    assert row["unexplained_missing_n"] == 0

    manifest = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 2), spine.DEFAULT_ENDPOINTS,
        generated_at=NOW.isoformat(),
    )
    coverage_receipt = manifest["daily_security_coverage"]
    assert coverage_receipt["pit_only_without_daily_observations"] == 1
    assert coverage_receipt["unexplained_missing_observations"] == 0
    assert coverage_receipt["complete"] is True


def test_master_present_lifecycle_eligible_ticker_missing_from_daily_still_blocks(tmp_path):
    """T8(b) -- C6, half two, the narrow-scope proof: only the witness-missing
    class moves. A ticker that IS in the master with a lifecycle window
    covering the date, and is missing from daily, STILL lands in
    unexplained_missing_n and STILL blocks. Without this half, C6 would have
    silently disabled the coverage check."""
    _seed_reference(tmp_path)
    _seed_calendar(tmp_path)
    _seed_pit_day(tmp_path, "20240102")

    daily = _daily_rows("20240102")
    daily = daily[daily["ts_code"] != "600519.SH"].reset_index(drop=True)
    daily = pd.concat([daily, pd.DataFrame([{
        "ts_code": "920163.BJ", "trade_date": "20240102", "open": 5, "high": 5, "low": 5,
        "close": 5, "pre_close": 5, "change": 0, "pct_chg": 0, "vol": 10, "amount": 50,
    }])], ignore_index=True)
    _land_endpoint_day(tmp_path, "daily", "20240102", daily)
    _land_endpoint_day(tmp_path, "suspend_d", "20240102", _empty("suspend_d"))

    state = spine.load_state(tmp_path)
    coverage = spine.build_daily_security_coverage(
        tmp_path, date(2024, 1, 2), date(2024, 1, 2), state, GENERATION,
    )
    row = coverage.iloc[0]
    assert row["pit_only_without_daily_n"] == 0
    assert row["unexplained_missing_n"] == 1

    manifest = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 2), spine.DEFAULT_ENDPOINTS,
        generated_at=NOW.isoformat(),
    )
    coverage_receipt = manifest["daily_security_coverage"]
    assert coverage_receipt["unexplained_missing_observations"] == 1
    assert coverage_receipt["complete"] is False


def test_completeness_manifest_reachable_with_witness_missing_securities(monkeypatch, tmp_path):
    """T9 -- end-to-end: completeness_manifest's `complete` conjunction is
    reachable on a store containing both a witness-missing TRADED security
    and a witness-missing NEVER-TRADED security.
    BULK_HISTORICAL_BACKFILL_READY stays forced True only through the
    autouse `_enable_synthetic_technical_readiness` fixture -- never edited
    directly, never `allow_bulk`, never `mode=backfill`."""
    monkeypatch.setattr(spine, "CALENDAR_HISTORY_START", date(2024, 1, 1))
    monkeypatch.setattr(spine, "NAME_HISTORY_START_YEAR", 2024)

    # 600519.SS: witness-missing but demonstrably TRADED (positive-volume
    # daily + stk_limit evidence, matching the ruling's 300114.SZ exemplar).
    _seed_reference(tmp_path, drop_stock_basic_ts_code="600519.SS")
    _seed_calendar(tmp_path)

    columns = spine.ENDPOINT_FIELDS["bak_basic"].split(",")
    for trade_date in ("20240102", "20240103"):
        # 603361.SS: witness-missing AND NEVER-TRADED (zero shares, no daily
        # row -- the ruling's own 603361.SS "approved but never listed" case).
        never_traded = pd.DataFrame([_bak_row(
            columns, trade_date, "603361.SH", "样本未上市",
            list_date=None, float_share=0, total_share=0, total_assets=0,
            liquid_assets=0, fixed_assets=0, holder_num=0,
        )], columns=columns)
        _seed_pit_day(tmp_path, trade_date, extra_rows=never_traded)
        _land_endpoint_day(tmp_path, "daily", trade_date, _daily_rows(trade_date))
        _land_endpoint_day(tmp_path, "daily_basic", trade_date, _daily_basic_rows(trade_date))
        _land_endpoint_day(tmp_path, "stk_limit", trade_date, _limit_rows(trade_date))
        _land_endpoint_day(tmp_path, "suspend_d", trade_date, pd.DataFrame([{
            "ts_code": "920163.BJ", "trade_date": trade_date,
            "suspend_timing": None, "suspend_type": "S",
        }]))
        _land_endpoint_day(tmp_path, "stock_st", trade_date, _empty("stock_st"))

    state = spine.load_state(tmp_path)
    spine._set_unit(
        state, tmp_path, "namechange", "2024:20240103", status="empty",
        observed_at=NOW.isoformat(),
        request_receipts=[_request_receipt(
            "namechange", "2024:20240103", tmp_path, frame=_empty("namechange"),
            params={"start_date": "20240101", "end_date": "20240103"},
        )],
    )

    manifest = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 3), spine.DEFAULT_ENDPOINTS,
        generated_at=NOW.isoformat(),
    )
    assert manifest["bulk_historical_backfill_ready"] is True
    assert manifest["complete"] is True
    assert manifest["pit_lifecycle_reconciliation"]["pit_absent_from_master_count"] == 4
    assert manifest["pit_lifecycle_reconciliation"]["current_snapshot_omission_rate"] > 0
    assert manifest["daily_security_coverage"]["pit_only_without_daily_observations"] == 2
    assert manifest["daily_security_coverage"]["unexplained_missing_observations"] == 0
