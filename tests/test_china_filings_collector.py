"""Tests for collectors/china_filings.py — metadata-only A-share filing collector.

Pure/offline surface only — no live network. Covers:
  - Category normalizer: each keyword family, priority collisions, no-match
  - classify_kind: letter/reply/attachment + precedence (attachment > reply > letter)
  - _unix_ms_to_iso: valid + malformed inputs
  - _parse_announcement: field mapping, kind propagation
  - Response parsing with a saved JSON fixture (simulated)
  - keep-FIRST dedup on announcementId
  - Empty-day handling (write_filings with zero rows)
  - Summary frame carries a DatetimeIndex (required by base.validate contract)

Storage is redirected to tmp_path so no tracked parquet is ever dirtied.
"""
from __future__ import annotations

import json
import sys
from datetime import timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_filings as cf  # noqa: E402


# --------------------------------------------------------------------------- #
# category normalizer
# --------------------------------------------------------------------------- #

class TestCategorize:
    def test_investigation_keyword(self):
        assert cf.categorize("公司收到证监会立案告知书") == "investigation"

    def test_inquiry_letter_wenxunhan(self):
        assert cf.categorize("关于问询函的回复公告") == "inquiry_letter"

    def test_inquiry_letter_jianguan(self):
        assert cf.categorize("收到深圳证券交易所监管函") == "inquiry_letter"

    def test_inquiry_letter_guanzhu(self):
        assert cf.categorize("收到上交所关注函的说明") == "inquiry_letter"

    def test_delisting_risk(self):
        assert cf.categorize("关于可能退市风险的提示公告") == "delisting_risk"

    def test_restructuring_zhongzu(self):
        assert cf.categorize("关于重大资产重组进展的公告") == "restructuring"

    def test_restructuring_zhongda(self):
        assert cf.categorize("重大资产出售暨关联交易公告") == "restructuring"

    def test_major_contract_zhongbiao(self):
        assert cf.categorize("公司中标政府采购合同公告") == "major_contract"

    def test_major_contract_zhongda_hetong(self):
        assert cf.categorize("签订重大合同公告") == "major_contract"

    def test_earnings_preann_yujian(self):
        assert cf.categorize("2023年年度业绩预告") == "earnings_preann"

    def test_earnings_preann_yuzeng(self):
        assert cf.categorize("预增：归母净利润增长50%") == "earnings_preann"

    def test_earnings_preann_yujian_report(self):
        assert cf.categorize("业绩快报：营业收入同比增长") == "earnings_preann"

    def test_holder_change_down(self):
        assert cf.categorize("持股5%以上股东减持股份计划公告") == "holder_change_down"

    def test_holder_change_up(self):
        assert cf.categorize("董事增持公司股份结果公告") == "holder_change_up"

    def test_buyback(self):
        assert cf.categorize("关于回购公司股份的公告") == "buyback"

    def test_pledge(self):
        assert cf.categorize("股东股权质押公告") == "pledge"

    def test_no_match_returns_other(self):
        assert cf.categorize("关于召开2024年度股东大会的通知") == "other"

    def test_empty_title_returns_other(self):
        assert cf.categorize("") == "other"

    def test_priority_investigation_over_inquiry(self):
        # A title mentioning both 立案 and 问询函 → investigation wins (higher priority)
        assert cf.categorize("收到立案问询函说明") == "investigation"

    def test_priority_inquiry_letter_over_buyback(self):
        # inquiry_letter outranks buyback
        assert cf.categorize("关注函回复：涉及回购事项说明") == "inquiry_letter"

    def test_priority_delisting_over_earnings(self):
        # delisting_risk outranks earnings_preann
        assert cf.categorize("退市业绩预告风险提示") == "delisting_risk"

    def test_priority_holder_change_down_over_up(self):
        # A title with both 减持 and 增持 → holder_change_down wins (listed earlier)
        assert cf.categorize("减持增持计划公告") == "holder_change_down"

    def test_priority_earnings_preann_over_restructuring(self):
        # earnings_preann outranks restructuring per brief priority order
        assert cf.categorize("重组业绩预告公告") == "earnings_preann"

    def test_priority_buyback_over_holder_change_down(self):
        # buyback outranks holder_change_down per brief priority order
        assert cf.categorize("回购减持公告") == "buyback"


# --------------------------------------------------------------------------- #
# classify_kind — inquiry-letter sub-kind
# --------------------------------------------------------------------------- #

class TestClassifyKind:
    def test_letter_is_default(self):
        # Plain inquiry letter title → 'letter'
        assert cf.classify_kind("关于问询函的相关说明") == "letter"

    def test_empty_title_is_letter(self):
        # Empty title falls back to 'letter' (inquiry family default)
        assert cf.classify_kind("") == "letter"

    def test_reply_huihan(self):
        assert cf.classify_kind("关于收到上交所问询函的回函公告") == "reply"

    def test_reply_huifu(self):
        assert cf.classify_kind("关注函回复的公告") == "reply"

    def test_reply_dafu(self):
        assert cf.classify_kind("答复监管函的说明") == "reply"

    def test_attachment_zhuanxiang(self):
        assert cf.classify_kind("关于问询函的专项说明") == "attachment"

    def test_attachment_hexha_yijian(self):
        assert cf.classify_kind("核查意见公告") == "attachment"

    def test_attachment_zhuanxiang_hexha(self):
        assert cf.classify_kind("专项核查意见报告") == "attachment"

    def test_precedence_attachment_over_reply(self):
        # A title with both attachment and reply keywords → attachment wins
        assert cf.classify_kind("关注函回复的专项说明") == "attachment"

    def test_precedence_attachment_over_letter(self):
        # attachment keyword beats plain letter match
        assert cf.classify_kind("问询函核查意见") == "attachment"

    def test_precedence_reply_over_letter(self):
        # reply keyword beats plain letter match (no attachment keyword)
        assert cf.classify_kind("问询函答复") == "reply"

    # --- 复函 fixture (review finding: formal reply letter missing from _KIND_REPLY_KW) ---

    def test_reply_fuhan(self):
        """复函 (formal reply letter) must classify as 'reply'.

        Live data example: "股票交易异常波动问询函的复函-郁敏珺" (4 rows in inquiry.parquet).
        """
        assert cf.classify_kind("股票交易异常波动问询函的复函-郁敏珺") == "reply"

    def test_reply_fuhan_standalone(self):
        """复函 alone → 'reply' (not 'letter' default)."""
        assert cf.classify_kind("复函") == "reply"

    def test_reply_fuhan_precedence_over_letter(self):
        """复函 beats the plain 'letter' default when no attachment keyword present."""
        assert cf.classify_kind("关于问询函的复函") == "reply"

    def test_precedence_attachment_over_fuhan(self):
        """附件 keyword still wins over 复函 (attachment > reply precedence unchanged)."""
        assert cf.classify_kind("关注函复函的专项说明") == "attachment"


# --------------------------------------------------------------------------- #
# _unix_ms_to_iso
# --------------------------------------------------------------------------- #

class TestUnixMsToIso:
    def test_valid_timestamp(self):
        # 2024-01-15 00:00:00 UTC = 1705276800000 ms
        # In Asia/Shanghai that's 2024-01-15T08:00:00+08:00
        result = cf._unix_ms_to_iso(1705276800000)
        assert result.startswith("2024-01-15T08:00:00")
        assert "+08:00" in result

    def test_none_returns_empty(self):
        assert cf._unix_ms_to_iso(None) == ""

    def test_malformed_returns_empty(self):
        assert cf._unix_ms_to_iso("not-a-number") == ""  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# _parse_announcement
# --------------------------------------------------------------------------- #

_SAMPLE_ANN = {
    "announcementId": "1234567",
    "secCode": "600519",
    "secName": "贵州茅台",
    "orgId": "9900004938",
    "announcementTitle": "关于回购公司股份的公告",
    "announcementTime": 1705276800000,
    "adjunctUrl": "finalpage/2024-01-15/1234567.PDF",
    "adjunctType": "PDF",
    "announcementType": "00000101|00000402",
}


class TestParseAnnouncement:
    def test_field_mapping(self):
        row = cf._parse_announcement(_SAMPLE_ANN, "sse", "2024-01-15T09:00:00+00:00")
        assert row["announcementId"] == "1234567"
        assert row["sec_code"] == "600519"
        assert row["sec_name"] == "贵州茅台"
        assert row["org_id"] == "9900004938"
        assert row["title"] == "关于回购公司股份的公告"
        assert row["exchange"] == "sse"
        assert row["category"] == "buyback"
        # buyback category → kind is None (only inquiry_letter has non-null kind)
        assert row["kind"] is None
        assert row["announcement_type_raw"] == "00000101|00000402"
        assert row["adjunct_url"] == "finalpage/2024-01-15/1234567.PDF"
        assert row["adjunct_type"] == "PDF"
        assert row["_collected_at"] == "2024-01-15T09:00:00+00:00"
        # publish_ts is a non-empty ISO string
        assert row["publish_ts"].startswith("2024-01-15")

    def test_inquiry_letter_has_kind_letter(self):
        ann = dict(_SAMPLE_ANN)
        ann["announcementTitle"] = "收到上交所关注函的说明"
        row = cf._parse_announcement(ann, "sse", "2024-01-15T09:00:00+00:00")
        assert row["category"] == "inquiry_letter"
        assert row["kind"] == "letter"

    def test_inquiry_letter_has_kind_reply(self):
        ann = dict(_SAMPLE_ANN)
        ann["announcementTitle"] = "关注函回复公告"
        row = cf._parse_announcement(ann, "sse", "2024-01-15T09:00:00+00:00")
        assert row["category"] == "inquiry_letter"
        assert row["kind"] == "reply"

    def test_inquiry_letter_has_kind_attachment(self):
        ann = dict(_SAMPLE_ANN)
        ann["announcementTitle"] = "问询函核查意见"
        row = cf._parse_announcement(ann, "sse", "2024-01-15T09:00:00+00:00")
        assert row["category"] == "inquiry_letter"
        assert row["kind"] == "attachment"

    def test_missing_fields_graceful(self):
        # Minimal announcement dict — no crash
        row = cf._parse_announcement({}, "szse", "2024-01-15T09:00:00+00:00")
        assert row["announcementId"] == ""
        assert row["category"] == "other"
        assert row["kind"] is None
        assert row["publish_ts"] == ""


# --------------------------------------------------------------------------- #
# Response parsing with simulated fixture
# --------------------------------------------------------------------------- #

_FIXTURE_PAGE1 = {
    "totalAnnouncement": 2,
    "totalpages": 1,
    "hasMore": False,
    "announcements": [
        {
            "announcementId": "A001",
            "secCode": "000001",
            "secName": "平安银行",
            "orgId": "ORG1",
            "announcementTitle": "收到问询函的回复",
            "announcementTime": 1705276800000,
            "adjunctUrl": "path/A001.PDF",
            "adjunctType": "PDF",
            "announcementType": "00001234",
        },
        {
            "announcementId": "A002",
            "secCode": "000002",
            "secName": "万科A",
            "orgId": "ORG2",
            "announcementTitle": "2023年度业绩预告",
            "announcementTime": 1705363200000,
            "adjunctUrl": "path/A002.PDF",
            "adjunctType": "PDF",
            "announcementType": "00002345",
        },
    ],
}


class TestResponseParsing:
    def test_fixture_parses_to_rows(self):
        collected_at = "2024-01-16T00:00:00+00:00"
        rows = [
            cf._parse_announcement(ann, "szse", collected_at)
            for ann in _FIXTURE_PAGE1["announcements"]
        ]
        assert len(rows) == 2
        assert rows[0]["announcementId"] == "A001"
        assert rows[0]["category"] == "inquiry_letter"
        # "收到问询函的回复" has 回复 → kind='reply'
        assert rows[0]["kind"] == "reply"
        assert rows[1]["announcementId"] == "A002"
        assert rows[1]["category"] == "earnings_preann"
        # non-inquiry_letter categories have kind=None
        assert rows[1]["kind"] is None

    def test_empty_announcements_list(self):
        empty_payload = {"totalAnnouncement": 0, "totalpages": 0,
                         "hasMore": False, "announcements": []}
        rows = [
            cf._parse_announcement(ann, "sse", "2024-01-16T00:00:00+00:00")
            for ann in (empty_payload.get("announcements") or [])
        ]
        assert rows == []


# --------------------------------------------------------------------------- #
# Pagination: _fetch_exchange multi-page termination
# --------------------------------------------------------------------------- #

class TestFetchExchangePagination:
    """Verify that _fetch_exchange terminates on totalpages, NOT on hasMore.

    Finding [major]: the old `or not has_more` guard truncated multi-page days
    when CNInfo returned hasMore=False mid-pagination (known endpoint quirk).
    The fix: terminate only when `page_num >= total_pages`.
    """

    def _make_page(
        self,
        page_num: int,
        total_pages: int,
        has_more: bool,
        ann_ids: list[str],
    ) -> dict:
        return {
            "totalAnnouncement": total_pages * len(ann_ids),
            "totalpages": total_pages,
            "hasMore": has_more,
            "announcements": [
                {
                    "announcementId": aid,
                    "secCode": "000001",
                    "secName": "平安银行",
                    "orgId": "ORG1",
                    "announcementTitle": "测试公告",
                    "announcementTime": 1705276800000,
                    "adjunctUrl": "",
                    "adjunctType": "PDF",
                    "announcementType": "",
                }
                for aid in ann_ids
            ],
        }

    def test_multipage_hasMore_false_early_still_collects_all(self, monkeypatch):
        """hasMore=False on page 1 of 3 must NOT truncate — all 3 pages collected."""
        # CNInfo quirk: page 1 says hasMore=False even though totalpages=3.
        pages = [
            self._make_page(1, 3, has_more=False, ann_ids=["P001", "P002"]),
            self._make_page(2, 3, has_more=False, ann_ids=["P003", "P004"]),
            self._make_page(3, 3, has_more=False, ann_ids=["P005", "P006"]),
        ]
        page_iter = iter(pages)

        # Monkeypatch _fetch_page so no real HTTP happens; also suppress _pace.
        monkeypatch.setattr(cf, "_fetch_page", lambda *args, **kw: next(page_iter))
        monkeypatch.setattr(cf, "_pace", lambda: None)

        adapter = cf.ChinaFilingsAdapter()
        # Pass a dummy session — _fetch_page is patched so it's never called.
        rows = adapter._fetch_exchange("sse", "2024-01-15~2024-01-15", None, "t0")

        assert len(rows) == 6
        ids = [r["announcementId"] for r in rows]
        assert ids == ["P001", "P002", "P003", "P004", "P005", "P006"]

    def test_singlepage_hasMore_false_terminates_normally(self, monkeypatch):
        """Single-page day: totalpages=1, hasMore=False — terminates after page 1."""
        pages = [
            self._make_page(1, 1, has_more=False, ann_ids=["Q001", "Q002"]),
        ]
        page_iter = iter(pages)

        monkeypatch.setattr(cf, "_fetch_page", lambda *args, **kw: next(page_iter))
        monkeypatch.setattr(cf, "_pace", lambda: None)

        adapter = cf.ChinaFilingsAdapter()
        rows = adapter._fetch_exchange("szse", "2024-01-15~2024-01-15", None, "t0")

        assert len(rows) == 2

    def test_multipage_hasMore_true_collects_all(self, monkeypatch):
        """Normal multi-page case: hasMore=True, verifies all pages still consumed."""
        pages = [
            self._make_page(1, 2, has_more=True, ann_ids=["R001"]),
            self._make_page(2, 2, has_more=False, ann_ids=["R002"]),
        ]
        page_iter = iter(pages)

        monkeypatch.setattr(cf, "_fetch_page", lambda *args, **kw: next(page_iter))
        monkeypatch.setattr(cf, "_pace", lambda: None)

        adapter = cf.ChinaFilingsAdapter()
        rows = adapter._fetch_exchange("sse", "2024-01-15~2024-01-15", None, "t0")

        assert len(rows) == 2
        assert [r["announcementId"] for r in rows] == ["R001", "R002"]


# --------------------------------------------------------------------------- #
# Summary frame tz-naive index (review finding — latent break guard)
# --------------------------------------------------------------------------- #

class TestSummaryFrameTzNaive:
    """The summary frame index must be tz-NAIVE.

    Precedent: collectors/china_official_corpora.py:468 uses .tz_convert(None)
    because mixing tz-aware with any tz-naive parquet on disk causes
    store.upsert -> combine_first to raise
    "Cannot join tz-naive with tz-aware DatetimeIndex".
    """

    def test_summary_index_is_tz_naive(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        adapter = cf.ChinaFilingsAdapter()

        def fake_fetch_exchange(exchange, date_range, session, collected_at):
            return [_make_row("TZ001", exchange=exchange)]

        import requests as _requests
        with patch.object(adapter, "_fetch_exchange", side_effect=fake_fetch_exchange):
            with patch.object(_requests, "Session", return_value=MagicMock()):
                result = adapter.fetch()

        summary = result["china_filings_summary"]
        # Index must be tz-naive (tzinfo is None on each Timestamp)
        for ts in summary.index:
            assert ts.tzinfo is None, (
                f"Summary index must be tz-naive; got tzinfo={ts.tzinfo!r}. "
                "Fix: add .tz_convert(None) to pd.Timestamp(collected_at)."
            )


# --------------------------------------------------------------------------- #
# Storage: keep-FIRST dedup + empty-day handling
# --------------------------------------------------------------------------- #

def _make_row(ann_id: str, title: str = "测试公告", exchange: str = "sse") -> dict:
    cat = cf.categorize(title)
    return {
        "announcementId": ann_id,
        "sec_code": "000001",
        "sec_name": "平安银行",
        "org_id": "ORG1",
        "title": title,
        "publish_ts": "2024-01-15T08:00:00+08:00",
        "exchange": exchange,
        "category": cat,
        "kind": cf.classify_kind(title) if cat == "inquiry_letter" else None,
        "announcement_type_raw": "",
        "adjunct_url": "",
        "adjunct_type": "",
        "_collected_at": "2024-01-15T09:00:00+00:00",
    }


class TestStorage:
    def test_write_empty_rows_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        assert cf.write_filings([]) == 0

    def test_write_new_rows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        rows = [_make_row("B001"), _make_row("B002")]
        net = cf.write_filings(rows)
        assert net == 2
        stored = cf.load_filings()
        assert len(stored) == 2

    def test_keep_first_dedup_on_announcement_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        first = _make_row("C001", "原始标题")
        second = _make_row("C001", "重复公告被丢弃")
        cf.write_filings([first])
        cf.write_filings([second])
        stored = cf.load_filings()
        # Only one row; the first write wins
        assert len(stored) == 1
        assert stored.iloc[0]["title"] == "原始标题"

    def test_keep_first_dedup_in_single_batch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        rows = [_make_row("D001", "第一次出现"), _make_row("D001", "第二次重复")]
        net = cf.write_filings(rows)
        stored = cf.load_filings()
        assert len(stored) == 1
        assert stored.iloc[0]["title"] == "第一次出现"

    def test_parquet_has_canonical_columns(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        cf.write_filings([_make_row("E001")])
        stored = pd.read_parquet(tmp_path / "filings.parquet")
        for col in cf._COLUMNS:
            assert col in stored.columns, f"missing column: {col}"

    def test_load_filings_returns_empty_frame_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        df = cf.load_filings()
        assert df.empty
        assert list(df.columns) == list(cf._COLUMNS)


# --------------------------------------------------------------------------- #
# Summary frame DatetimeIndex (required by base.validate contract)
# --------------------------------------------------------------------------- #

class TestSummaryFrameDatetimeIndex:
    """The frame returned by fetch() must carry a pd.DatetimeIndex so that
    run_adapter → validate() can call pd.to_datetime(df.index) without raising.
    """

    def test_summary_has_datetime_index(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        # Redirect storage to tmp_path
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")

        adapter = cf.ChinaFilingsAdapter()

        # Stub _fetch_exchange to return two fixture rows, avoiding real HTTP.
        # requests is lazily imported inside fetch() so we patch it via sys.modules
        # to prevent any real Session from being created.
        rows_sse = [_make_row("F001", "问询函回复", "sse")]
        rows_szse = [_make_row("F002", "业绩预告", "szse")]

        def fake_fetch_exchange(exchange, date_range, session, collected_at):
            return rows_sse if exchange == "sse" else rows_szse

        import requests as _requests  # ensure it's in sys.modules already
        with patch.object(adapter, "_fetch_exchange", side_effect=fake_fetch_exchange):
            with patch.object(_requests, "Session", return_value=MagicMock()):
                result = adapter.fetch(full_history=False)

        assert "china_filings_summary" in result
        summary = result["china_filings_summary"]
        # Must be convertible to DatetimeIndex without raising
        converted = pd.to_datetime(summary.index).normalize()
        assert len(converted) == 1
        assert isinstance(converted[0], pd.Timestamp)
        # All columns must be numeric
        assert all(summary[c].dtype.kind == "f" for c in summary.columns)
        # Exchange columns present
        for ex in cf._EXCHANGES:
            assert f"n_rows_{ex}" in summary.columns

    def test_summary_total_count(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        adapter = cf.ChinaFilingsAdapter()

        rows_sse = [_make_row("G001"), _make_row("G002")]
        rows_szse = [_make_row("G003")]

        def fake_fetch_exchange(exchange, date_range, session, collected_at):
            return rows_sse if exchange == "sse" else rows_szse

        import requests as _requests
        with patch.object(adapter, "_fetch_exchange", side_effect=fake_fetch_exchange):
            with patch.object(_requests, "Session", return_value=MagicMock()):
                result = adapter.fetch()

        summary = result["china_filings_summary"]
        assert summary["n_rows_total"].iloc[0] == 3.0
        assert summary["n_rows_sse"].iloc[0] == 2.0
        assert summary["n_rows_szse"].iloc[0] == 1.0


# --------------------------------------------------------------------------- #
# date_range helper
# --------------------------------------------------------------------------- #

class TestDateRange:
    def test_nightly_range_has_three_days_gap(self):
        adapter = cf.ChinaFilingsAdapter()
        dr = adapter._date_range(full_history=False)
        parts = dr.split("~")
        assert len(parts) == 2
        from datetime import date
        start = date.fromisoformat(parts[0])
        end = date.fromisoformat(parts[1])
        assert (end - start).days == cf._NIGHTLY_LOOKBACK_DAYS

    def test_full_history_range_has_seven_days_gap(self):
        adapter = cf.ChinaFilingsAdapter()
        dr = adapter._date_range(full_history=True)
        parts = dr.split("~")
        from datetime import date
        start = date.fromisoformat(parts[0])
        end = date.fromisoformat(parts[1])
        assert (end - start).days == cf._INITIAL_LOOKBACK_DAYS
