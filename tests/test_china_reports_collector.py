"""Tests for collectors/china_reports.py — sell-side rating/TP/EPS revision stream.

Pure/offline surface only — NO network. Fixtures are the REAL /report/list responses
captured from reportapi.eastmoney.com on 2026-07-25 (4 rows from the window page plus
the rating-only slice used to pin the ordinal scale), trimmed to the fields the
collector stores with every value byte-faithful.

Covers:
  - change_class over the whole taxonomy incl. the non-numeric degrade path
  - row mapping from the real rows (ids, dates, ratings, EPS, target-price blanks)
  - dedup keep-LAST on info_code
  - aggregate recomputation from a crafted 2-day store (per-class counts + names/orgs)
  - the true-zero rule: a clean fetch may write a 0-report day, a partial one may not
  - page-cap + transport-failure behaviour of the window pull

Storage is redirected to tmp_path (monkeypatched lib.config.data_dir).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_reports as cr  # noqa: E402
from lib import config  # noqa: E402


# --------------------------------------------------------------------------- #
# REAL captured fixture (reportapi.eastmoney.com, 2026-07-25)
# --------------------------------------------------------------------------- #

_REPORT_PAGE = json.loads("""
{
    "hits": 75, "size": 50, "TotalPage": 2, "pageNo": 1, "currentYear": 2026,
    "data": [
        {
            "title": "国产培养基领军者，创新药BD趋势下有望加速出海",
            "stockName": "奥浦迈", "stockCode": "688293", "orgSName": "华源证券",
            "publishDate": "2026-07-25 00:00:00.000", "infoCode": "AP202607251827337475",
            "predictNextYearEps": "1.79", "predictThisYearEps": "1.13",
            "emRatingValue": "3", "emRatingName": "买入",
            "lastEmRatingValue": "", "lastEmRatingName": "", "ratingChange": 2,
            "indvAimPriceT": "", "indvAimPriceL": "", "market": "SHANGHAI", "count": 1
        },
        {
            "title": "北交所首次覆盖报告：FPC整线“小巨人”深度绑定头部客户",
            "stockName": "锐翔智能", "stockCode": "920178", "orgSName": "开源证券",
            "publishDate": "2026-07-24 00:00:00.000", "infoCode": "AP202607241827321448",
            "predictNextYearEps": "3.26", "predictThisYearEps": "2.45",
            "emRatingValue": "2", "emRatingName": "增持",
            "lastEmRatingValue": "", "lastEmRatingName": "", "ratingChange": 2,
            "indvAimPriceT": "", "indvAimPriceL": "", "market": "BEIJING", "count": 2
        },
        {
            "title": "公司深度报告：国际化动力煤巨头精进不止",
            "stockName": "兖矿能源", "stockCode": "600188", "orgSName": "开源证券",
            "publishDate": "2026-07-24 00:00:00.000", "infoCode": "AP202607241827321441",
            "predictNextYearEps": "2.19", "predictThisYearEps": "1.94",
            "emRatingValue": "3", "emRatingName": "买入",
            "lastEmRatingValue": "3", "lastEmRatingName": "买入", "ratingChange": 3,
            "indvAimPriceT": "", "indvAimPriceL": "", "market": "SHANGHAI", "count": 1
        },
        {
            "title": "扣非业绩超我们预期，看好公司受益于电网的景气度",
            "stockName": "长高电气", "stockCode": "002452", "orgSName": "中邮证券",
            "publishDate": "2026-07-24 00:00:00.000", "infoCode": "AP202607241827321348",
            "predictNextYearEps": "0.7600000000", "predictThisYearEps": "1.1200000000",
            "emRatingValue": "3", "emRatingName": "买入",
            "lastEmRatingValue": "3", "lastEmRatingName": "买入", "ratingChange": 3,
            "indvAimPriceT": "", "indvAimPriceL": "", "market": "SHENZHEN", "count": 2
        }
    ]
}
""")

# The rating-only slice from the same capture: 23 rows carrying lastEmRatingName, of
# which every one was a 买入→买入 maintain (and one 增持→增持). This is the live evidence
# behind "2=增持, 3=买入, higher = more bullish" — and behind NOT reading ratingChange.
_RATING_ROWS = [
    {"stockCode": "600188", "emRatingValue": "3", "lastEmRatingValue": "3", "ratingChange": 3},
    {"stockCode": "002452", "emRatingValue": "3", "lastEmRatingValue": "3", "ratingChange": 3},
    {"stockCode": "002266", "emRatingValue": "2", "lastEmRatingValue": "2", "ratingChange": 3},
]

_TS = "2026-07-25T12:00:00+00:00"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


# --------------------------------------------------------------------------- #
# change_class taxonomy
# --------------------------------------------------------------------------- #

class TestChangeClass:
    def test_upgrade(self):
        # EastMoney ordinal: 3=买入 outranks 2=增持.
        assert cr.change_class("3", "2") == "upgrade"

    def test_downgrade(self):
        assert cr.change_class("2", "3") == "downgrade"

    def test_maintain(self):
        assert cr.change_class("3", "3") == "maintain"

    def test_no_prior_when_the_house_had_no_rating(self):
        assert cr.change_class("3", "") == "no_prior"
        assert cr.change_class("3", None) == "no_prior"

    def test_unrated_when_the_current_report_has_none(self):
        assert cr.change_class("", "2") == "unrated"
        assert cr.change_class(None, "2") == "unrated"

    def test_non_numeric_degrades_and_never_raises(self):
        assert cr.change_class("x", "y") == "unrated"      # current unusable first
        assert cr.change_class("3", "y") == "no_prior"     # only the prior unusable
        assert cr.change_class("", "") == "unrated"

    def test_numeric_variants(self):
        assert cr.change_class(3, 2) == "upgrade"
        assert cr.change_class("3.0", "2.0") == "upgrade"

    def test_live_rating_slice_is_all_maintain(self):
        classes = [cr.change_class(r["emRatingValue"], r["lastEmRatingValue"])
                   for r in _RATING_ROWS]
        assert classes == ["maintain", "maintain", "maintain"]


# --------------------------------------------------------------------------- #
# row parsing (real fixture values)
# --------------------------------------------------------------------------- #

class TestParseReportRow:
    def test_initiation_row(self):
        row = cr.parse_report_row(_REPORT_PAGE["data"][0], _TS,
                                  _REPORT_PAGE["currentYear"])
        assert row["info_code"] == "AP202607251827337475"
        assert row["publish_date"] == "2026-07-25"
        assert row["code"] == "688293" and row["name"] == "奥浦迈"
        assert row["org"] == "华源证券"
        assert row["em_rating"] == "买入" and row["em_rating_value"] == "3"
        assert row["last_em_rating_value"] == ""
        assert row["change_class"] == "no_prior"
        assert row["target_price_t"] == ""          # most CN reports carry no target
        assert row["eps_this"] == "1.13" and row["eps_next"] == "1.79"
        assert row["forecast_year_base"] == "2026"
        assert row["month_count"] == "1"
        assert row["market"] == "SHANGHAI"
        assert row["backfill"] is False
        assert row["fetched_at"] == _TS

    def test_maintain_row(self):
        row = cr.parse_report_row(_REPORT_PAGE["data"][2], _TS, 2026)
        assert row["code"] == "600188"
        assert row["change_class"] == "maintain"
        assert row["last_em_rating"] == "买入"

    def test_vendor_rating_change_code_is_stored_raw_only(self):
        # Stored for audit; the collector's own classification never reads it.
        rows = [cr.parse_report_row(r, _TS, 2026) for r in _REPORT_PAGE["data"]]
        assert [r["rating_change_raw"] for r in rows] == ["2", "2", "3", "3"]
        # Same raw code 2 spans an initiation at 买入 AND one at 增持 → not interpretable.
        assert rows[0]["change_class"] == rows[1]["change_class"] == "no_prior"

    def test_whole_page_maps(self):
        rows = [cr.parse_report_row(r, _TS, 2026) for r in _REPORT_PAGE["data"]]
        assert len(rows) == 4
        assert [r["change_class"] for r in rows] == [
            "no_prior", "no_prior", "maintain", "maintain"]

    def test_missing_fields_degrade(self):
        row = cr.parse_report_row({}, _TS)
        assert row["info_code"] == "" and row["publish_date"] == ""
        assert row["change_class"] == "unrated"

    def test_backfill_rows_are_stamped(self):
        row = cr.parse_report_row(_REPORT_PAGE["data"][0], _TS, 2026, backfill=True)
        assert row["backfill"] is True


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #

class TestReportStore:
    def test_rows_land_and_dedup_keep_last(self, store):
        rows = [cr.parse_report_row(r, _TS, 2026) for r in _REPORT_PAGE["data"]]
        assert cr.write_reports(rows) == 4
        # Same infoCode re-pulled with a target price now populated → CORRECTS.
        corrected = dict(_REPORT_PAGE["data"][0])
        corrected["indvAimPriceT"] = "88.00"
        assert cr.write_reports([cr.parse_report_row(corrected, _TS, 2026)]) == 0
        stored = cr.load_reports()
        assert len(stored) == 4
        hit = stored[stored["info_code"] == "AP202607251827337475"].iloc[0]
        assert hit["target_price_t"] == "88.00"

    def test_empty_write(self, store):
        assert cr.write_reports([]) == 0

    def test_columns_are_canonical(self, store):
        cr.write_reports([cr.parse_report_row(_REPORT_PAGE["data"][0], _TS, 2026)])
        stored = pd.read_parquet(cr._reports_path())
        for col in cr._COLUMNS:
            assert col in stored.columns, f"missing column: {col}"


# --------------------------------------------------------------------------- #
# daily aggregates
# --------------------------------------------------------------------------- #

def _crafted_store() -> pd.DataFrame:
    """A 2-day store spanning every change class, plus one report with a target."""
    def row(info, date, code, org, cur, last, target=""):
        return {**cr.parse_report_row(
            {"infoCode": info, "publishDate": date + " 00:00:00.000", "stockCode": code,
             "orgSName": org, "emRatingValue": cur, "lastEmRatingValue": last,
             "indvAimPriceT": target}, _TS, 2026)}

    return pd.DataFrame([
        row("A1", "2026-07-24", "600188", "开源证券", "3", "2"),          # upgrade
        row("A2", "2026-07-24", "002452", "中邮证券", "2", "3"),          # downgrade
        row("A3", "2026-07-24", "600188", "中邮证券", "3", "3", "42.5"),  # maintain + target
        row("A4", "2026-07-24", "688293", "华源证券", "3", ""),           # no_prior
        row("A5", "2026-07-24", "920178", "华源证券", "", "2"),           # unrated
        row("B1", "2026-07-25", "600188", "开源证券", "3", "3"),          # maintain
    ])


class TestAggregates:
    def test_counts_per_class_and_distinct_names_orgs(self):
        rows = cr.aggregate_rows(_crafted_store(), ["2026-07-24", "2026-07-25"], _TS)
        day = {r["date"]: r for r in rows}
        d0 = day["2026-07-24"]
        assert d0["n_reports"] == 5
        assert d0["n_names"] == 4          # 600188 twice
        assert d0["n_orgs"] == 3
        assert (d0["n_upgrade"], d0["n_downgrade"], d0["n_maintain"],
                d0["n_no_prior"], d0["n_unrated"]) == (1, 1, 1, 1, 1)
        assert d0["n_with_target"] == 1
        assert d0["fetched_at"] == _TS
        assert day["2026-07-25"]["n_reports"] == 1

    def test_true_zero_day_is_written_after_a_clean_fetch(self):
        rows = cr.aggregate_rows(_crafted_store(), ["2026-07-26"], _TS,
                                 allow_true_zero=True)
        assert len(rows) == 1
        assert rows[0]["n_reports"] == 0 and rows[0]["n_names"] == 0

    def test_partial_fetch_never_stamps_a_zero(self):
        # A zero after a capped/failed pull would be OUR truncation, not the market's.
        assert cr.aggregate_rows(_crafted_store(), ["2026-07-26"], _TS,
                                 allow_true_zero=False) == []

    def test_partial_fetch_still_records_days_that_have_rows(self):
        rows = cr.aggregate_rows(_crafted_store(), ["2026-07-25", "2026-07-26"], _TS,
                                 allow_true_zero=False)
        assert [r["date"] for r in rows] == ["2026-07-25"]

    def test_empty_store_with_clean_fetch(self):
        empty = pd.DataFrame(columns=list(cr._COLUMNS))
        rows = cr.aggregate_rows(empty, ["2026-07-25"], _TS)
        assert rows[0]["n_reports"] == 0

    def test_aggregate_store_dedups_on_date_keep_last(self, store):
        cr.write_aggregates([{"date": "2026-07-25", "n_reports": 3, "n_names": 3,
                              "n_orgs": 2, "n_upgrade": 0, "n_downgrade": 0,
                              "n_maintain": 3, "n_no_prior": 0, "n_unrated": 0,
                              "n_with_target": 0, "fetched_at": "a"}])
        cr.write_aggregates([{"date": "2026-07-25", "n_reports": 9, "n_names": 8,
                              "n_orgs": 4, "n_upgrade": 1, "n_downgrade": 0,
                              "n_maintain": 8, "n_no_prior": 0, "n_unrated": 0,
                              "n_with_target": 2, "fetched_at": "b"}])
        agg = cr.load_aggregates()
        assert len(agg) == 1
        assert int(agg.iloc[0]["n_reports"]) == 9   # the later recompute wins


# --------------------------------------------------------------------------- #
# window helpers + paging
# --------------------------------------------------------------------------- #

class TestWindow:
    def test_window_dates_are_inclusive(self):
        assert cr._window_dates("2026-07-22", "2026-07-25") == [
            "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-25"]

    def test_window_spans_the_lookback(self):
        begin, end = cr._window()
        assert cr._window_dates(begin, end).__len__() == cr._WINDOW_DAYS + 1

    def test_page_url_keeps_all_four_page_aliases_in_sync(self):
        url = cr._page_url("2026-07-22", "2026-07-25", 3)
        for alias in ("pageNo=3", "p=3", "pageNum=3", "pageNumber=3"):
            assert alias in url
        assert "beginTime=2026-07-22" in url and "endTime=2026-07-25" in url
        # Redistribution limit: the collector never asks for PDFs/attachments.
        assert "pdf" not in url.lower()


class TestPullWindow:
    def test_stops_at_total_pages(self, monkeypatch):
        seen = []

        def page(session, begin, end, n):
            seen.append(n)
            return {"TotalPage": 2, "currentYear": 2026, "data": _REPORT_PAGE["data"][:1]}

        monkeypatch.setattr(cr, "_fetch_page", page)
        monkeypatch.setattr(cr, "_pace", lambda: None)
        rows, ok, failed, capped = cr._pull_window(None, "a", "b", _TS, cr._clock())
        assert seen == [1, 2]
        assert len(rows) == 2 and ok == 2 and failed == 0 and capped is False

    def test_page_cap_is_loud_not_silent(self, monkeypatch):
        monkeypatch.setattr(cr, "_fetch_page", lambda *a: {
            "TotalPage": 40, "currentYear": 2026, "data": _REPORT_PAGE["data"][:1]})
        monkeypatch.setattr(cr, "_pace", lambda: None)
        rows, ok, failed, capped = cr._pull_window(None, "a", "b", _TS, cr._clock())
        assert ok == cr._PAGE_CAP and capped is True

    def test_transport_failure_on_page_one(self, monkeypatch):
        def dead(*a):
            raise IOError("connection refused")

        monkeypatch.setattr(cr, "_fetch_page", dead)
        monkeypatch.setattr(cr, "_pace", lambda: None)
        rows, ok, failed, capped = cr._pull_window(None, "a", "b", _TS, cr._clock())
        assert rows == [] and ok == 0 and failed == 1

    def test_wall_clock_guard(self, monkeypatch):
        monkeypatch.setattr(cr, "_fetch_page", lambda *a: {
            "TotalPage": 40, "currentYear": 2026, "data": _REPORT_PAGE["data"][:1]})
        monkeypatch.setattr(cr, "_pace", lambda: None)
        ticks = iter([0.0, 1.0] + [cr._BUDGET_S + 1.0] * 20)
        monkeypatch.setattr(cr, "_clock", lambda: next(ticks))
        rows, ok, failed, capped = cr._pull_window(None, "a", "b", _TS, 0.0)
        assert ok == 2 and capped is True and len(rows) == 2


# --------------------------------------------------------------------------- #
# refresh()
# --------------------------------------------------------------------------- #

@pytest.fixture()
def pinned_window(monkeypatch):
    """Pin the trailing window to the fixture's own dates.

    Without this the tests rot the moment `today - 3d` stops covering the captured
    2026-07-24/25 publish dates — the classic fixture-rot failure, not a real defect.
    """
    monkeypatch.setattr(cr, "_window", lambda days=cr._WINDOW_DAYS: ("2026-07-22", "2026-07-25"))


class TestRefresh:
    def test_happy_path_writes_reports_and_aggregates(self, store, pinned_window, monkeypatch):
        monkeypatch.setattr(cr, "_pace", lambda: None)
        monkeypatch.setattr(cr, "_fetch_page", lambda *a: {
            "TotalPage": 1, "currentYear": 2026, "data": _REPORT_PAGE["data"]})
        s = cr.refresh()
        assert s["n_fetched"] == 4 and s["n_new"] == 4
        assert s["universe"] == 4 and s["shard"] == 1 and s["n_failed"] == 0
        agg = cr.load_aggregates()
        # every window date is covered (clean fetch → true zeros allowed)
        assert len(agg) == cr._WINDOW_DAYS + 1
        assert int(agg[agg["date"] == "2026-07-24"]["n_reports"].iloc[0]) == 3

    def test_quiet_day_is_a_success_with_true_zeros(self, store, pinned_window, monkeypatch):
        monkeypatch.setattr(cr, "_pace", lambda: None)
        monkeypatch.setattr(cr, "_fetch_page", lambda *a: {
            "TotalPage": 1, "currentYear": 2026, "data": []})
        s = cr.refresh()
        assert s["n_new"] == 0 and s["n_failed"] == 0
        agg = cr.load_aggregates()
        assert len(agg) == cr._WINDOW_DAYS + 1
        assert set(agg["n_reports"].astype(int)) == {0}

    def test_partial_pull_suppresses_true_zero_rows(self, store, pinned_window, monkeypatch):
        monkeypatch.setattr(cr, "_pace", lambda: None)
        calls = {"n": 0}

        def flaky(session, begin, end, page):
            calls["n"] += 1
            if page == 1:
                return {"TotalPage": 3, "currentYear": 2026,
                        "data": _REPORT_PAGE["data"]}
            raise IOError("HTTP 502")

        monkeypatch.setattr(cr, "_fetch_page", flaky)
        s = cr.refresh()
        assert s["n_failed"] == 1 and s["n_new"] == 4
        agg = cr.load_aggregates()
        # Only the dates that actually carry rows; the empty window days are a GAP.
        assert set(agg["date"]) == {"2026-07-24", "2026-07-25"}

    def test_total_transport_failure_raises_for_the_breaker(self, store, pinned_window,
                                                            monkeypatch):
        monkeypatch.setattr(cr, "_pace", lambda: None)
        monkeypatch.setattr(cr, "_fetch_page",
                            lambda *a: (_ for _ in ()).throw(IOError("refused")))
        with pytest.raises(RuntimeError, match="every page"):
            cr.refresh()


# --------------------------------------------------------------------------- #
# backfill CLI (manual only)
# --------------------------------------------------------------------------- #

class TestBackfill:
    def test_stamps_backfill_true_and_writes_no_aggregates(self, store, monkeypatch):
        monkeypatch.setattr(cr, "_pace", lambda: None)
        monkeypatch.setattr(cr, "_fetch_page", lambda *a: {
            "TotalPage": 1, "currentYear": 2026, "data": _REPORT_PAGE["data"]})
        n = cr.backfill("2026-07-01", "2026-07-14")
        assert n == 4
        stored = cr.load_reports()
        assert bool(stored["backfill"].all())
        assert cr.load_aggregates().empty


# --------------------------------------------------------------------------- #
# adapter sentinel
# --------------------------------------------------------------------------- #

class TestAdapter:
    def test_sentinel_is_a_coverage_frame_with_a_tz_naive_index(self, store, monkeypatch):
        monkeypatch.setattr(cr, "refresh", lambda: {
            "n_new": 4, "n_fetched": 4, "n_failed": 0, "universe": 4, "shard": 1})
        sentinel = cr.ChinaReportsAdapter().fetch()["refresh"]
        assert list(sentinel.columns) == [
            "n_new", "n_fetched", "n_failed", "universe", "shard"]
        for ts in sentinel.index:
            assert ts.tzinfo is None, "tz-aware index breaks store.upsert combine_first"

    def test_adapter_is_asia_lane(self):
        a = cr.ChinaReportsAdapter()
        assert a.group.startswith("china")
        assert a.stale_after_days == 4
