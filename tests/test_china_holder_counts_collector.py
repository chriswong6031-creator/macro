"""Tests for collectors/china_holder_counts.py — 股东户数 retail-concentration tape.

Pure/offline surface only — NO network. The fixture is the REAL RPT_HOLDERNUMLATEST
envelope captured from datacenter-web.eastmoney.com on 2026-07-25 (3 rows, values
byte-faithful, including the 12-decimal HOLDER_NUM_RATIO the vendor actually sends).

Covers:
  - row mapping + date normalisation from the real rows
  - numeric coercion via pd.to_numeric(errors='coerce') and NaN passthrough
    (a vendor null must stay MISSING, never become 0)
  - (code, end_date) dedup keep-LAST resolved by notice_date (a later notice corrects)
  - the early-stop paging rule: a page of all-known keys ends the night
  - transport failure / cap behaviour and the coverage sentinel

Storage is redirected to tmp_path (monkeypatched lib.config.data_dir).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_holder_counts as ch  # noqa: E402
from lib import config  # noqa: E402


# --------------------------------------------------------------------------- #
# REAL captured fixture (datacenter-web.eastmoney.com, 2026-07-25)
# --------------------------------------------------------------------------- #

_PAGE = json.loads("""
{
    "result": {
        "pages": 1845, "count": 5535,
        "data": [
            {
                "SECURITY_CODE": "688475", "SECURITY_NAME_ABBR": "萤石网络",
                "END_DATE": "2026-06-30 00:00:00", "INTERVAL_CHRATE": 5.23811455,
                "AVG_MARKET_CAP": 1295838.09638409, "AVG_HOLD_NUM": 47379.820708742,
                "TOTAL_MARKET_CAP": 21538125000, "TOTAL_A_SHARES": 787500000,
                "HOLD_NOTICE_DATE": "2026-07-25 00:00:00", "HOLDER_NUM": 16621,
                "PRE_HOLDER_NUM": 16731, "HOLDER_NUM_CHANGE": -110,
                "HOLDER_NUM_RATIO": -0.657462195924, "PRE_END_DATE": "2026-03-31 00:00:00"
            },
            {
                "SECURITY_CODE": "603727", "SECURITY_NAME_ABBR": "博迈科",
                "END_DATE": "2026-06-30 00:00:00", "INTERVAL_CHRATE": -9.40619235,
                "AVG_MARKET_CAP": 301949.542352202, "AVG_HOLD_NUM": 17699.269774455,
                "TOTAL_MARKET_CAP": 4806130865.62, "TOTAL_A_SHARES": 281719277,
                "HOLD_NOTICE_DATE": "2026-07-25 00:00:00", "HOLDER_NUM": 15917,
                "PRE_HOLDER_NUM": 20893, "HOLDER_NUM_CHANGE": -4976,
                "HOLDER_NUM_RATIO": -23.816589288278, "PRE_END_DATE": "2026-03-31 00:00:00"
            },
            {
                "SECURITY_CODE": "300999", "SECURITY_NAME_ABBR": "金龙鱼",
                "END_DATE": "2026-07-20 00:00:00", "INTERVAL_CHRATE": 7.0462925,
                "AVG_MARKET_CAP": 1290255.53371841, "AVG_HOLD_NUM": 49378.3212291775,
                "TOTAL_MARKET_CAP": 141666186835.68, "TOTAL_A_SHARES": 5421591536,
                "HOLD_NOTICE_DATE": "2026-07-25 00:00:00", "HOLDER_NUM": 109797,
                "PRE_HOLDER_NUM": 110433, "HOLDER_NUM_CHANGE": -636,
                "HOLDER_NUM_RATIO": -0.575914808074, "PRE_END_DATE": "2026-07-10 00:00:00"
            }
        ]
    },
    "success": true, "code": 0
}
""")

_TS = "2026-07-25T12:00:00+00:00"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


# --------------------------------------------------------------------------- #
# row parsing
# --------------------------------------------------------------------------- #

class TestParseHolderRow:
    def test_real_row_field_by_field(self):
        row = ch.parse_holder_row(_PAGE["result"]["data"][0], _TS)
        assert row["code"] == "688475"
        assert row["name"] == "萤石网络"
        assert row["end_date"] == "2026-06-30"
        assert row["pre_end_date"] == "2026-03-31"
        assert row["notice_date"] == "2026-07-25"
        assert row["holder_num"] == 16621
        assert row["pre_holder_num"] == 16731
        assert row["holder_num_change"] == -110
        assert row["holder_num_ratio"] == pytest.approx(-0.657462195924)
        assert row["total_a_shares"] == 787500000
        assert row["interval_chrate"] == pytest.approx(5.23811455)
        assert row["fetched_at"] == _TS

    def test_non_quarter_end_period_is_kept_as_sent(self):
        # 金龙鱼 discloses on a mid-month cadence; the tape must not force quarter-ends.
        row = ch.parse_holder_row(_PAGE["result"]["data"][2], _TS)
        assert row["end_date"] == "2026-07-20"
        assert row["pre_end_date"] == "2026-07-10"

    def test_missing_fields_degrade(self):
        row = ch.parse_holder_row({}, _TS)
        assert row["code"] == "" and row["end_date"] == ""
        assert row["holder_num"] is None

    def test_parse_page_returns_rows_and_total(self):
        rows, count = ch.parse_page(_PAGE, _TS)
        assert [r["code"] for r in rows] == ["688475", "603727", "300999"]
        assert count == 5535

    def test_parse_page_degrades_on_shape_drift(self):
        assert ch.parse_page({}, _TS) == ([], 0)
        assert ch.parse_page({"result": {"data": None}}, _TS) == ([], 0)


# --------------------------------------------------------------------------- #
# numeric coercion
# --------------------------------------------------------------------------- #

class TestCoerceNumeric:
    def test_numeric_columns_become_numbers(self):
        df = ch.coerce_numeric(pd.DataFrame(
            [ch.parse_holder_row(r, _TS) for r in _PAGE["result"]["data"]]))
        for col in ch._NUMERIC_COLUMNS:
            assert pd.api.types.is_numeric_dtype(df[col]), col
        assert df["holder_num"].tolist() == [16621, 15917, 109797]

    def test_vendor_null_stays_nan_never_zero(self):
        raw = dict(_PAGE["result"]["data"][0])
        raw["HOLDER_NUM"] = None
        raw["HOLDER_NUM_RATIO"] = None
        df = ch.coerce_numeric(pd.DataFrame([ch.parse_holder_row(raw, _TS)]))
        assert pd.isna(df["holder_num"].iloc[0])
        assert pd.isna(df["holder_num_ratio"].iloc[0])
        assert df["holder_num"].iloc[0] != 0

    def test_garbage_string_coerces_to_nan(self):
        raw = dict(_PAGE["result"]["data"][0])
        raw["AVG_HOLD_NUM"] = "--"
        df = ch.coerce_numeric(pd.DataFrame([ch.parse_holder_row(raw, _TS)]))
        assert pd.isna(df["avg_hold_num"].iloc[0])


# --------------------------------------------------------------------------- #
# store: (code, end_date) dedup keep-LAST by notice_date
# --------------------------------------------------------------------------- #

def _row(code, end_date, notice_date, holder_num):
    return ch.parse_holder_row({
        "SECURITY_CODE": code, "SECURITY_NAME_ABBR": "测试",
        "END_DATE": end_date + " 00:00:00", "HOLD_NOTICE_DATE": notice_date + " 00:00:00",
        "PRE_END_DATE": "2026-03-31 00:00:00", "HOLDER_NUM": holder_num,
        "PRE_HOLDER_NUM": 100, "HOLDER_NUM_CHANGE": 1, "HOLDER_NUM_RATIO": 1.0,
        "AVG_HOLD_NUM": 1.0, "AVG_MARKET_CAP": 1.0, "TOTAL_MARKET_CAP": 1.0,
        "TOTAL_A_SHARES": 1.0, "INTERVAL_CHRATE": 1.0,
    }, _TS)


class TestStore:
    def test_rows_land(self, store):
        rows = [ch.parse_holder_row(r, _TS) for r in _PAGE["result"]["data"]]
        assert ch.write_holder_counts(rows) == 3
        assert len(ch.load_holder_counts()) == 3

    def test_empty_write(self, store):
        assert ch.write_holder_counts([]) == 0

    def test_later_notice_corrects_the_same_period(self, store):
        ch.write_holder_counts([_row("688475", "2026-06-30", "2026-07-25", 16621)])
        assert ch.write_holder_counts(
            [_row("688475", "2026-06-30", "2026-07-28", 16500)]) == 0
        stored = ch.load_holder_counts()
        assert len(stored) == 1
        assert stored.iloc[0]["holder_num"] == 16500
        assert stored.iloc[0]["notice_date"] == "2026-07-28"

    def test_an_earlier_notice_never_overwrites_a_later_one(self, store):
        ch.write_holder_counts([_row("688475", "2026-06-30", "2026-07-28", 16500)])
        ch.write_holder_counts([_row("688475", "2026-06-30", "2026-07-25", 16621)])
        stored = ch.load_holder_counts()
        assert len(stored) == 1
        assert stored.iloc[0]["holder_num"] == 16500   # the LATER notice still wins

    def test_a_new_period_for_the_same_name_is_a_new_row(self, store):
        ch.write_holder_counts([_row("688475", "2026-03-31", "2026-04-20", 17000)])
        assert ch.write_holder_counts(
            [_row("688475", "2026-06-30", "2026-07-25", 16621)]) == 1
        assert len(ch.load_holder_counts()) == 2

    def test_same_day_recollect_never_duplicates(self, store):
        rows = [ch.parse_holder_row(r, _TS) for r in _PAGE["result"]["data"]]
        ch.write_holder_counts(rows)
        assert ch.write_holder_counts(rows) == 0
        assert len(ch.load_holder_counts()) == 3

    def test_columns_are_canonical(self, store):
        ch.write_holder_counts([ch.parse_holder_row(_PAGE["result"]["data"][0], _TS)])
        stored = pd.read_parquet(ch._store_path())
        for col in ch._COLUMNS:
            assert col in stored.columns, f"missing column: {col}"

    def test_nan_survives_the_round_trip(self, store):
        raw = dict(_PAGE["result"]["data"][0])
        raw["HOLDER_NUM"] = None
        ch.write_holder_counts([ch.parse_holder_row(raw, _TS)])
        assert pd.isna(ch.load_holder_counts()["holder_num"].iloc[0])


# --------------------------------------------------------------------------- #
# key helpers
# --------------------------------------------------------------------------- #

class TestKeys:
    def test_row_key(self):
        assert ch.row_key(_row("688475", "2026-06-30", "2026-07-25", 1)) == (
            "688475", "2026-06-30")

    def test_known_keys_from_an_empty_store(self):
        assert ch.known_keys(pd.DataFrame(columns=list(ch._COLUMNS))) == set()

    def test_known_keys_from_a_populated_store(self, store):
        ch.write_holder_counts([ch.parse_holder_row(r, _TS)
                                for r in _PAGE["result"]["data"]])
        keys = ch.known_keys(ch.load_holder_counts())
        assert ("688475", "2026-06-30") in keys
        assert ("300999", "2026-07-20") in keys


# --------------------------------------------------------------------------- #
# paging / refresh
# --------------------------------------------------------------------------- #

def _page_of(codes, end_date="2026-06-30", notice="2026-07-25"):
    return {"result": {"pages": 12, "count": 5535, "data": [
        {"SECURITY_CODE": c, "SECURITY_NAME_ABBR": "测试",
         "END_DATE": end_date + " 00:00:00", "HOLD_NOTICE_DATE": notice + " 00:00:00",
         "PRE_END_DATE": "2026-03-31 00:00:00", "HOLDER_NUM": 1000,
         "PRE_HOLDER_NUM": 1010, "HOLDER_NUM_CHANGE": -10, "HOLDER_NUM_RATIO": -1.0,
         "AVG_HOLD_NUM": 1.0, "AVG_MARKET_CAP": 1.0, "TOTAL_MARKET_CAP": 1.0,
         "TOTAL_A_SHARES": 1.0, "INTERVAL_CHRATE": 1.0} for c in codes]}}


class TestRefresh:
    def test_first_run_seeds_until_a_page_adds_nothing_new(self, store, monkeypatch):
        pages = {1: _page_of(["000001", "000002"]),
                 2: _page_of(["000003"]),
                 3: _page_of(["000003"])}          # all-known → stop here
        seen = []

        def fetch(session, page):
            seen.append(page)
            return pages.get(page, _page_of([]))

        monkeypatch.setattr(ch, "_fetch_page", fetch)
        monkeypatch.setattr(ch, "_pace", lambda: None)
        s = ch.refresh()
        assert seen == [1, 2, 3]
        assert s["n_new"] == 3 and s["shard"] == 3
        assert s["universe"] == 5535 and s["n_failed"] == 0

    def test_quiet_night_stops_on_page_one(self, store, monkeypatch):
        ch.write_holder_counts([_row("000001", "2026-06-30", "2026-07-25", 1000)])
        seen = []

        def fetch(session, page):
            seen.append(page)
            return _page_of(["000001"])

        monkeypatch.setattr(ch, "_fetch_page", fetch)
        monkeypatch.setattr(ch, "_pace", lambda: None)
        s = ch.refresh()
        assert seen == [1]                 # page 1 was all-known → no page 2
        assert s["n_new"] == 0             # a quiet night is a SUCCESS
        assert s["n_fetched"] == 1

    def test_empty_page_ends_the_snapshot(self, store, monkeypatch):
        monkeypatch.setattr(ch, "_fetch_page", lambda s, p: _page_of([]))
        monkeypatch.setattr(ch, "_pace", lambda: None)
        s = ch.refresh()
        assert s["n_new"] == 0 and s["shard"] == 1

    def test_page_cap_is_respected(self, store, monkeypatch):
        seen = []

        def fetch(session, page):
            seen.append(page)
            return _page_of([f"{page:06d}"])       # every page brings a new key

        monkeypatch.setattr(ch, "_fetch_page", fetch)
        monkeypatch.setattr(ch, "_pace", lambda: None)
        s = ch.refresh()
        assert seen == list(range(1, ch._PAGE_CAP + 1))
        assert s["shard"] == ch._PAGE_CAP

    def test_wall_clock_guard_keeps_what_it_has(self, store, monkeypatch):
        monkeypatch.setattr(ch, "_fetch_page",
                            lambda s, p: _page_of([f"{p:06d}"]))
        monkeypatch.setattr(ch, "_pace", lambda: None)
        # t0, then two in-budget page checks, then over budget.
        ticks = iter([0.0, 1.0, 2.0] + [ch._BUDGET_S + 1.0] * 20)
        monkeypatch.setattr(ch, "_clock", lambda: next(ticks))
        s = ch.refresh()
        assert s["shard"] == 2 and s["n_new"] == 2

    def test_mid_run_failure_keeps_the_earlier_pages(self, store, monkeypatch):
        def fetch(session, page):
            if page == 1:
                return _page_of(["000001", "000002"])
            raise IOError("HTTP 502")

        monkeypatch.setattr(ch, "_fetch_page", fetch)
        monkeypatch.setattr(ch, "_pace", lambda: None)
        s = ch.refresh()
        assert s["n_failed"] == 1 and s["n_new"] == 2

    def test_total_transport_failure_raises_for_the_breaker(self, store, monkeypatch):
        monkeypatch.setattr(ch, "_fetch_page",
                            lambda s, p: (_ for _ in ()).throw(IOError("refused")))
        monkeypatch.setattr(ch, "_pace", lambda: None)
        with pytest.raises(RuntimeError, match="every page failed"):
            ch.refresh()


# --------------------------------------------------------------------------- #
# URL + adapter
# --------------------------------------------------------------------------- #

class TestUrlAndAdapter:
    def test_url_carries_the_report_name_and_notice_date_sort(self):
        url = ch._page_url(3)
        assert "reportName=RPT_HOLDERNUMLATEST" in url
        assert "sortColumns=HOLD_NOTICE_DATE,SECURITY_CODE" in url
        assert "sortTypes=-1,-1" in url
        assert "pageNumber=3" in url and "pageSize=500" in url
        for col in ("HOLDER_NUM", "PRE_HOLDER_NUM", "HOLDER_NUM_RATIO", "PRE_END_DATE"):
            assert col in url

    def test_sentinel_is_a_coverage_frame_with_a_tz_naive_index(self, store, monkeypatch):
        monkeypatch.setattr(ch, "refresh", lambda: {
            "n_new": 12, "n_fetched": 500, "n_failed": 0, "universe": 5535, "shard": 1})
        sentinel = ch.ChinaHolderCountsAdapter().fetch()["refresh"]
        assert list(sentinel.columns) == [
            "n_new", "n_fetched", "n_failed", "universe", "shard"]
        assert sentinel["universe"].iloc[0] == 5535.0
        for ts in sentinel.index:
            assert ts.tzinfo is None, "tz-aware index breaks store.upsert combine_first"

    def test_adapter_is_asia_lane_with_a_quarterly_staleness_budget(self):
        a = ch.ChinaHolderCountsAdapter()
        assert a.group.startswith("china")
        assert a.stale_after_days == 10
