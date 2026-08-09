from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from collectors import china_tushare_spine as spine

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


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


def _seed_reference(store: Path) -> pd.DataFrame:
    mapping = pd.DataFrame([{
        "name": "方大新材", "o_code": "838163.BJ", "n_code": "920163.BJ", "list_date": "2020-07-27",
    }])
    spine._atomic_parquet(store / "reference" / "source_bse_mapping.parquet", mapping)
    state = spine.load_state(store)
    spine._set_unit(
        state, store, "bse_mapping", "all", status="complete", observed_at=NOW.isoformat(),
        row_count=len(mapping), source_row_count=len(mapping),
        partition=store / "reference" / "source_bse_mapping.parquet",
    )
    for (exchange, status), frame in _stock_basic_rows().items():
        path = store / "reference" / "source_stock_basic" / f"{exchange}_{status}.parquet"
        spine._atomic_parquet(path, frame)
        state = spine.load_state(store)
        spine._set_unit(
            state, store, "stock_basic", f"{exchange}:{status}",
            status="empty" if frame.empty else "complete", observed_at=NOW.isoformat(),
            row_count=len(frame), source_row_count=len(frame), partition=path,
        )
    master, _ = spine.compile_security_master(store)
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
        )
    return spine.compile_market_sessions(store, date(2024, 1, 1), date(2024, 1, 3))


def _seed_spine(store: Path) -> pd.DataFrame:
    master = _seed_reference(store)
    _seed_calendar(store)
    return master


def _daily_rows(trade_date: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"ts_code": "600519.SH", "trade_date": trade_date, "open": 10, "high": 11, "low": 9,
         "close": 11, "pre_close": 10, "change": 1, "pct_chg": 10, "vol": 100, "amount": 1000},
        {"ts_code": "000001.SZ", "trade_date": trade_date, "open": 10, "high": 10, "low": 10,
         "close": 10, "pre_close": 10, "change": 0, "pct_chg": 0, "vol": 0, "amount": 0},
    ])


def _daily_basic_rows(trade_date: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"ts_code": code, "trade_date": trade_date, "close": 10, "turnover_rate": 1,
         "turnover_rate_f": 2, "volume_ratio": 1, "pe": 10, "pe_ttm": 11, "pb": 2,
         "ps": 3, "ps_ttm": 3, "dv_ratio": 1, "dv_ttm": 1, "total_share": 100,
         "float_share": 80, "free_share": 60, "total_mv": 1000, "circ_mv": 800,
         "limit_status": 0}
        for code in ("600519.SH", "000001.SZ")
    ])


def _limit_rows(trade_date: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"ts_code": code, "trade_date": trade_date, "pre_close": 10,
         "up_limit": 11, "down_limit": 9}
        for code in ("600519.SH", "000001.SZ")
    ])


def _empty(endpoint: str) -> pd.DataFrame:
    return pd.DataFrame(columns=spine.ENDPOINT_FIELDS[endpoint].split(","))


def test_canonical_identity_suffixes_boards_and_bse_alias():
    sh = spine.canonical_identity("688001.SH")
    assert (sh.ticker, sh.source_ts_code, sh.security_id, sh.board) == (
        "688001.SS", "688001.SH", "CN-XSHG-688001", "star",
    )
    assert spine.canonical_identity("301001.SZ").board == "chinext"
    assert spine.canonical_identity("600519.SS").source_ts_code == "600519.SH"
    bj = spine.canonical_identity("838163.BJ", bse_aliases={"838163.BJ": "920163.BJ"})
    assert (bj.ticker, bj.security_id, bj.board) == ("920163.BJ", "CN-XBSE-920163", "bse")
    assert bj.source_ts_code == "838163.BJ"  # vendor-observed alias is not erased
    with pytest.raises(spine.SpineError, match="canonical SH/SZ/BJ"):
        spine.canonical_identity("00700.HK")


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
    aliases = pd.read_parquet(tmp_path / "reference" / "identity_aliases.parquet")
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
            "ts_code": "900001.SH", "trade_date": "20240102", "open": 1, "high": 1, "low": 1,
            "close": 1, "pre_close": 1, "change": 0, "pct_chg": 0, "vol": 5, "amount": 5,
        }]),
    ], ignore_index=True)
    normal, dropped = spine.normalise_daily_endpoint("daily", frame, "20240102", tmp_path)
    assert dropped == 1
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

    invalid_volume = _daily_rows("20240102")
    invalid_volume["vol"] = invalid_volume["vol"].astype(float)
    invalid_volume.loc[0, "vol"] = float("inf")
    with pytest.raises(spine.SpineError, match="finite and non-negative"):
        spine.normalise_daily_endpoint("daily", invalid_volume, "20240102", tmp_path)


def test_name_history_st_is_inference_and_retains_orphan_identity(tmp_path):
    _seed_reference(tmp_path)
    raw = pd.DataFrame([
        {"ts_code": "600519.SH", "name": "*ST茅台", "start_date": "20110101",
         "end_date": "20111231", "ann_date": "20101231", "change_reason": "ST"},
        {"ts_code": "600999.SH", "name": "旧名", "start_date": "20000101",
         "end_date": None, "ann_date": "20000101", "change_reason": "改名"},
    ])
    out, orphans = spine.normalise_name_history(raw, tmp_path)
    assert orphans == 1
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
    out, dropped = spine.normalise_daily_endpoint("suspend_d", raw, "20240102", tmp_path)
    assert dropped == 0
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
        if endpoint == "trade_cal":
            return _calendar_frame(params["exchange"])
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
        require_token=False, max_requests=30, now=lambda: NOW,
    )
    assert result["requests_made"] == 26
    assert result["capped"] is False
    assert result["manifest_complete"] is True
    assert len(calls) == 26

    def should_not_call(*args, **kwargs):
        raise AssertionError("a completed source unit was queried again")

    resumed = spine.collect(
        start="20240101", end="20240103", store=tmp_path, query=should_not_call,
        require_token=False, max_requests=30, now=lambda: NOW,
    )
    assert resumed["requests_made"] == 0
    assert resumed["manifest_complete"] is True


def test_documented_row_cap_fails_closed_without_partial_partition(tmp_path):
    _seed_spine(tmp_path)
    frame = pd.DataFrame({
        "ts_code": ["600519.SH"] * spine.SOURCE_ROW_CAPS["daily"],
        "trade_date": ["20240102"] * spine.SOURCE_ROW_CAPS["daily"],
    })
    collector = spine.TushareAShareSpineCollector(
        tmp_path, query=lambda *args, **kwargs: frame, now=lambda: NOW, max_requests=5,
    )
    collector.collect_daily(date(2024, 1, 2), date(2024, 1, 2), ("daily",))
    record = spine.load_state(tmp_path)["units"]["daily"]["20240102"]
    assert record["status"] == "failed"
    assert record["reason"] == "documented_source_row_cap_reached"
    assert not (tmp_path / "daily").exists()


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
        )
        return
    normal, dropped = spine.normalise_daily_endpoint(endpoint, raw, trade_date, store)
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
        row_count=len(normal), source_row_count=len(raw), dropped_row_count=dropped, partition=path,
    )


def test_canonical_event_substrate_uses_vendor_limits_not_reconstruction(tmp_path):
    _seed_spine(tmp_path)
    daily = _daily_rows("20240102")
    limits = _limit_rows("20240102")
    limits[["up_limit", "down_limit"]] = limits[["up_limit", "down_limit"]].astype(float)
    limits.loc[0, "up_limit"] = 10.99
    limits.loc[0, "down_limit"] = 9.01
    _land_endpoint_day(tmp_path, "daily", "20240102", daily)
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


def test_manifest_hashes_coverage_ore_and_schema(monkeypatch, tmp_path):
    _seed_spine(tmp_path)
    monkeypatch.setattr(spine, "CALENDAR_HISTORY_START", date(2024, 1, 1))
    monkeypatch.setattr(spine, "NAME_HISTORY_START_YEAR", 2024)
    state = spine.load_state(tmp_path)
    spine._set_unit(
        state, tmp_path, "namechange", "2024", status="empty", observed_at=NOW.isoformat(),
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
    identity = manifest["manifest_identity_sha256"]
    unsigned = dict(manifest)
    unsigned.pop("manifest_identity_sha256")
    assert identity == hashlib.sha256(spine._canonical_json_bytes(unsigned)).hexdigest()
    assert manifest["complete"] is True
    assert manifest["daily_security_coverage"]["eligible_security_observations"] == 6
    assert manifest["daily_security_coverage"]["daily_security_observations"] == 4
    assert manifest["daily_security_coverage"]["positive_volume_observations"] == 2
    assert manifest["daily_security_coverage"]["unexplained_missing_observations"] == 0
    assert len(manifest["reference"]["source_artifacts"]) == 14
    assert manifest["canonical_event_substrate"]["ready"] is True
    assert manifest["canonical_event_substrate"]["row_count"] == 4
    assert manifest["contracts"]["price_limit"]["canonical_storage"] == "integer CNY cents"
    assert "pre-2016 exact daily ST membership" in manifest["ore_ledger"]["not_tested"]
    for endpoint in spine.DEFAULT_ENDPOINTS:
        assert manifest["endpoints"][endpoint]["coverage_pct"] == 100.0
        assert manifest["endpoints"][endpoint]["duplicate_key_rows"] == 0
    omitted_argument = spine.build_completeness_manifest(
        tmp_path, date(2024, 1, 2), date(2024, 1, 3),
        ("daily", "stk_limit", "suspend_d", "stock_st"),
        generated_at=NOW.isoformat(),
    )
    assert set(omitted_argument["endpoints"]) == set(spine.DEFAULT_ENDPOINTS)
    assert omitted_argument["complete"] is True  # landed daily_basic remains a required receipt
    published = json.loads((tmp_path / "completeness_manifest.json").read_text(encoding="utf-8"))
    assert published == omitted_argument == manifest


def test_missing_token_and_dry_run_are_network_free_and_do_not_expose_secret(monkeypatch, tmp_path):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    result = spine.collect(start="20240101", end="20240103", store=tmp_path)
    assert result["no_op"] is True and result["requests_made"] == 0
    assert list(tmp_path.iterdir()) == []
    dry = spine.collect(start="20240101", end="20240103", store=tmp_path, dry_run=True)
    assert dry["network_calls"] == 0 and dry["writes"] == 0
    assert "token" not in json.dumps(dry).lower()


def test_receipt_fails_before_hashing_configured_token_bytes(monkeypatch, tmp_path):
    secret = "synthetic-paid-credential-never-log"
    monkeypatch.setenv("TUSHARE_TOKEN", secret)
    path = tmp_path / "collection_state.json"
    path.write_bytes(f'{{"escaped":"{secret}"}}'.encode())
    with pytest.raises(spine.SpineError, match="configured credential bytes found") as excinfo:
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
