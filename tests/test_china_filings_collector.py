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
  - P1-R2 (2026-08-22, DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP):
    key_anomaly/normalize_announcement_id/partition_by_key_integrity unit
    coverage, write_filings' typed exclusion + pre-existing-unkeyed
    preservation + LAST_KEY_INTEGRITY/LAST_RUN_OUTCOME folding, and a
    mutation guard proving the exclusion depends on the real partition.

Storage is redirected to tmp_path so no tracked parquet is ever dirtied.
"""
from __future__ import annotations

import json
import sys
from datetime import timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_filings as cf  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_module_globals():
    """collectors.china_filings.LAST_RUN_OUTCOME and LAST_KEY_INTEGRITY are
    process-local module globals (the P1-R1 same-cycle contract and the P1-R2
    key-integrity contract). Any test here that drives fetch() writes them, and
    `monkeypatch` restores patched ATTRIBUTES but never a global a function
    assigned to — so without this fixture a fetch()-driving test LEAKS its
    outcome into every later test in the same process.

    That is not hypothetical: collectors/china_visits.py reads
    LAST_RUN_OUTCOME, so a leaked "both exchanges failed" verdict made
    tests/test_china_intel_hub_visits.py::TestLoadVisitsContext::
    test_after_a_real_refresh_ctx_reflects_it assert status "ok" against a run
    typed "upstream_degraded" — a test that passed alone and failed under the
    default alphabetical collection order, where this file is collected first.
    Caught by an adversarial review 2026-08-22 before it could redden CI.
    tests/test_china_visits_collector.py has carried the same guard since P1-R1.
    """
    cf.LAST_RUN_OUTCOME = None
    cf.LAST_KEY_INTEGRITY = None
    yield
    cf.LAST_RUN_OUTCOME = None
    cf.LAST_KEY_INTEGRITY = None


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

    # ----------------------------------------------------------------- #
    # institutional_visit (P1, RIGHTS-0 §1) — added alongside china_visits.py
    # ----------------------------------------------------------------- #

    def test_institutional_visit_activity_record(self):
        assert cf.categorize("顺网科技：投资者关系活动记录表") == "institutional_visit"

    def test_institutional_visit_specific_object_survey(self):
        assert cf.categorize("关于接待特定对象调研的公告") == "institutional_visit"

    def test_institutional_visit_analyst_meeting(self):
        assert cf.categorize("2026年度分析师会议纪要") == "institutional_visit"

    def test_institutional_visit_results_briefing(self):
        assert cf.categorize("2026年半年度业绩说明会公告") == "institutional_visit"

    def test_institutional_visit_generic_survey_keyword(self):
        assert cf.categorize("机构调研情况登记表") == "institutional_visit"

    def test_institutional_visit_is_lowest_priority_named_category(self):
        # investigation still wins over a title that also mentions 调研
        assert cf.categorize("立案调查暨调研接待公告") == "investigation"
        # inquiry_letter still wins
        assert cf.categorize("问询函回复：调研接待安排说明") == "inquiry_letter"
        # buyback still wins
        assert cf.categorize("回购股份实施结果暨调研接待公告") == "buyback"

    def test_existing_categories_unchanged_by_the_new_bucket(self):
        # Full existing-category regression, single assertion per family —
        # the new institutional_visit entry must not shift any of these.
        assert cf.categorize("公司收到证监会立案告知书") == "investigation"
        assert cf.categorize("关于问询函的回复公告") == "inquiry_letter"
        assert cf.categorize("关于可能退市风险的提示公告") == "delisting_risk"
        assert cf.categorize("2023年年度业绩预告") == "earnings_preann"
        assert cf.categorize("关于重大资产重组进展的公告") == "restructuring"
        assert cf.categorize("公司中标政府采购合同公告") == "major_contract"
        assert cf.categorize("关于回购公司股份的公告") == "buyback"
        assert cf.categorize("股东股权质押公告") == "pledge"
        assert cf.categorize("持股5%以上股东减持股份计划公告") == "holder_change_down"
        assert cf.categorize("董事增持公司股份结果公告") == "holder_change_up"
        assert cf.categorize("关于召开2024年度股东大会的通知") == "other"


# --------------------------------------------------------------------------- #
# classify_kind — inquiry-letter sub-kind
# --------------------------------------------------------------------------- #

class TestClassifyKind:
    def test_exchange_issued_inquiry_is_a_letter(self):
        # A genuine exchange-issued inquiry, or the company's receipt of one.
        assert cf.classify_kind("关于收到上海证券交易所问询函的公告") == "letter"
        assert cf.classify_kind("关于对某公司有关股价波动事项的问询函") == "letter"

    def test_empty_title_is_letter(self):
        # Empty title falls back to 'letter' (inquiry family default)
        assert cf.classify_kind("") == "letter"

    def test_reply_side_explanations_are_not_letters(self):
        """A 说明/意见 filed in ANSWER to an inquiry is not an inquiry.

        Regression this catches: `letter` used to be the fall-through for the
        whole family, so 100 of 140 stored "letters" were reply-side filings and
        the desk published them as unanswered regulatory questions (PR #5975).
        """
        for title in (
            "关于问询函的相关说明",
            "天健会计师事务所关于某公司审核问询函中有关财务事项的说明",
            "某公司独立董事关于年度报告信息披露监管问询函所涉事项的独立董事意见",
            "北京市某律师事务所关于《问询函》相关问题的专项法律意见",
            "董事会审计委员会关于公司问询函所涉问题的相关意见",
        ):
            assert cf.classify_kind(title) == "reply_side", title

    def test_deferral_notice_is_not_a_reply(self):
        """延期回复 announces the reply is POSTPONED — the inverse of a reply.

        Regression this catches: it contains 回复, and all 41 such notices in the
        store were classified `reply`, so the filing saying no reply had been made
        would mark the inquiry answered.
        """
        for verb in ("延期", "延长", "推迟", "顺延"):
            assert cf.classify_kind(f"关于{verb}回复《关于某公司重组的问询函》的公告") == "deferral", verb
        # A genuine inquiry whose SUBJECT concerns a postponement stays a letter.
        assert cf.classify_kind("关于收到上海证券交易所《关于某公司延期复牌事项的问询函》的公告") == "letter"

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
        # A receipt announcement — not a 说明, which is reply-side (see
        # TestClassifyKind.test_reply_side_explanations_are_not_letters).
        ann["announcementTitle"] = "收到上交所关注函的公告"
        row = cf._parse_announcement(ann, "sse", "2024-01-15T09:00:00+00:00")
        assert row["category"] == "inquiry_letter"
        assert row["kind"] == "letter"

    def test_inquiry_reply_side_has_kind_reply_side(self):
        ann = dict(_SAMPLE_ANN)
        ann["announcementTitle"] = "收到上交所关注函的说明"
        row = cf._parse_announcement(ann, "sse", "2024-01-15T09:00:00+00:00")
        assert row["category"] == "inquiry_letter"
        assert row["kind"] == "reply_side"

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
        # P1-R2: a truly ABSENT announcementId key stays None ("missing" per
        # key_anomaly()), never flattened to "" ("empty") — see
        # _parse_announcement's docstring and TestKeyAnomaly below.
        assert row["announcementId"] is None
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


# --------------------------------------------------------------------------- #
# P1-R2 — key_anomaly / normalize_announcement_id (unit table)
# --------------------------------------------------------------------------- #

class TestKeyAnomaly:
    """key_anomaly() classifies a raw announcementId's malformation. Covers
    every FROZEN typed anomaly plus well-formed cases, and proves the helper
    never raises — even on weird non-scalar input."""

    def test_none_is_missing(self):
        assert cf.key_anomaly(None) == "missing"

    def test_empty_string_is_empty(self):
        assert cf.key_anomaly("") == "empty"

    def test_space_is_whitespace(self):
        assert cf.key_anomaly(" ") == "whitespace"

    def test_tab_is_whitespace(self):
        assert cf.key_anomaly("\t") == "whitespace"

    def test_newline_is_whitespace(self):
        assert cf.key_anomaly("\n") == "whitespace"

    def test_ideographic_space_is_whitespace(self):
        assert cf.key_anomaly("　") == "whitespace"

    def test_mixed_whitespace_is_whitespace(self):
        assert cf.key_anomaly(" \t\n　 ") == "whitespace"

    def test_float_nan_is_nan(self):
        assert cf.key_anomaly(float("nan")) == "nan"

    def test_pd_na_is_nan(self):
        assert cf.key_anomaly(pd.NA) == "nan"

    def test_pd_nat_is_nan(self):
        assert cf.key_anomaly(pd.NaT) == "nan"

    def test_np_nan_is_nan(self):
        assert cf.key_anomaly(np.nan) == "nan"

    def test_nan_checked_before_str_coercion(self):
        # str(float('nan')) == 'nan' — a non-empty string that would misread
        # as well-formed if the string branch ran before the NaN check.
        assert cf.key_anomaly(float("nan")) == "nan"
        assert str(float("nan")) == "nan"  # documents WHY ordering matters

    # ---- well-formed cases ----

    def test_normal_id_is_well_formed(self):
        assert cf.key_anomaly("1234567") is None

    def test_int_id_is_well_formed(self):
        assert cf.key_anomaly(1234567) is None

    def test_id_with_surrounding_whitespace_that_strips_to_real_value(self):
        # Non-empty AND strips to a non-empty value — NOT the "whitespace"
        # anomaly (that anomaly is only for strings that strip to "").
        assert cf.key_anomaly(" 1234567 ") is None

    # ---- never raises ----

    def test_never_raises_on_a_list(self):
        # pd.isna() returns an ARRAY (not a scalar bool) for list input —
        # truth-testing that array raises ValueError inside pandas itself.
        # The helper must swallow that, never propagate it.
        assert cf.key_anomaly([1, 2, 3]) is None

    def test_never_raises_on_empty_list(self):
        assert cf.key_anomaly([]) is None

    def test_never_raises_on_a_dict(self):
        assert cf.key_anomaly({"a": 1}) is None

    def test_never_raises_on_a_tuple(self):
        assert cf.key_anomaly(("x", "y")) is None


class TestNormalizeAnnouncementId:
    def test_malformed_forms_normalize_to_empty_string(self):
        for bad in (None, "", " ", "\t", "　", float("nan"), pd.NA, pd.NaT):
            assert cf.normalize_announcement_id(bad) == ""

    def test_well_formed_id_is_stripped(self):
        assert cf.normalize_announcement_id(" 1234567 ") == "1234567"

    def test_well_formed_id_without_whitespace_unchanged(self):
        assert cf.normalize_announcement_id("1234567") == "1234567"

    def test_int_id_normalizes_to_its_string_form(self):
        assert cf.normalize_announcement_id(1234567) == "1234567"

    def test_never_raises_on_an_unstringable_value(self):
        """Both halves of this predicate pair run one import away from the C0
        market-critical Asia lane, where a raise is a lane failure. key_anomaly()
        answers None (well-formed) for any non-string object it cannot call
        NaN-like — including one whose __str__ raises — so the str() coercion
        here is the single throwing path in the pair unless it is guarded. An
        un-stringable key is an absent key, so it normalizes to "".

        MUTATION GUARD: drop the try/except in normalize_announcement_id() and
        this test raises RuntimeError instead of asserting.
        """
        class _Unstringable:
            def __str__(self):
                raise RuntimeError("boom")

        assert cf.normalize_announcement_id(_Unstringable()) == ""


# --------------------------------------------------------------------------- #
# P1-R2 — partition_by_key_integrity
# --------------------------------------------------------------------------- #

class TestPartitionByKeyIntegrity:
    def test_valid_and_missing_split_correctly(self):
        rows = [_make_row("V001"), {**_make_row("V001"), "announcementId": None}]
        well, malformed, counts = cf.partition_by_key_integrity(rows)
        assert len(well) == 1 and well[0]["announcementId"] == "V001"
        assert len(malformed) == 1
        assert counts == {"missing": 1}

    def test_multiple_malformed_rows_counted_individually_not_collapsed(self):
        """The test that dies if the guard is removed: drop_duplicates would
        collapse 3 rows sharing announcementId="" into ONE. This partition
        must report 3, never 1."""
        rows = [
            {**_make_row("X1"), "announcementId": ""},
            {**_make_row("X2"), "announcementId": ""},
            {**_make_row("X3"), "announcementId": ""},
        ]
        well, malformed, counts = cf.partition_by_key_integrity(rows)
        assert well == []
        assert len(malformed) == 3
        assert counts == {"empty": 3}

    def test_absent_anomaly_names_are_omitted_not_zero_valued(self):
        rows = [{**_make_row("Y1"), "announcementId": ""}]
        _, _, counts = cf.partition_by_key_integrity(rows)
        assert "empty" in counts
        assert "missing" not in counts and "nan" not in counts and "whitespace" not in counts

    def test_preserves_input_order_within_each_list(self):
        rows = [
            _make_row("A"), {**_make_row("_"), "announcementId": None},
            _make_row("B"), {**_make_row("_"), "announcementId": ""},
            _make_row("C"),
        ]
        well, malformed, _ = cf.partition_by_key_integrity(rows)
        assert [r["announcementId"] for r in well] == ["A", "B", "C"]

    def test_pure_no_io(self, tmp_path, monkeypatch):
        # No _store_path monkeypatch needed — proves this touches no disk.
        rows = [_make_row("Z1")]
        cf.partition_by_key_integrity(rows)  # must not raise / not need a store


# --------------------------------------------------------------------------- #
# P1-R2 — write_filings typed exclusion + accrued-store protection
# --------------------------------------------------------------------------- #

class TestWriteFilingsKeyIntegrity:
    def test_valid_plus_missing_id_row(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        rows = [_make_row("H001"), {**_make_row("H002"), "announcementId": None}]
        net = cf.write_filings(rows)
        assert net == 1
        stored = cf.load_filings()
        assert list(stored["announcementId"]) == ["H001"]
        assert cf.LAST_KEY_INTEGRITY["excluded_total"] == 1
        assert cf.LAST_KEY_INTEGRITY["excluded_by_type"] == {"missing": 1}

    def test_multiple_missing_ids_prove_no_silent_collapse(self, tmp_path, monkeypatch):
        """At least 3 malformed rows in one batch — the counter must report
        3, never 1 (the drop_duplicates collapse this repair prevents)."""
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        rows = [
            {**_make_row("_"), "announcementId": ""},
            {**_make_row("_"), "announcementId": ""},
            {**_make_row("_"), "announcementId": ""},
        ]
        cf.write_filings(rows)
        assert cf.LAST_KEY_INTEGRITY["excluded_total"] == 3
        assert cf.LAST_KEY_INTEGRITY["excluded_by_type"] == {"empty": 3}
        # Zero well-keyed rows entered the store — none silently survived as "one".
        assert cf.load_filings().empty

    def test_none_id_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        cf.write_filings([{**_make_row("_"), "announcementId": None}])
        assert cf.load_filings().empty
        assert cf.LAST_KEY_INTEGRITY["excluded_by_type"] == {"missing": 1}

    def test_empty_string_id_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        cf.write_filings([{**_make_row("_"), "announcementId": ""}])
        assert cf.load_filings().empty
        assert cf.LAST_KEY_INTEGRITY["excluded_by_type"] == {"empty": 1}

    def test_whitespace_ids_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        rows = [
            {**_make_row("_"), "announcementId": " "},
            {**_make_row("_"), "announcementId": "\t"},
            {**_make_row("_"), "announcementId": "　"},
        ]
        cf.write_filings(rows)
        assert cf.load_filings().empty
        assert cf.LAST_KEY_INTEGRITY["excluded_by_type"] == {"whitespace": 3}

    def test_nan_ids_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        rows = [
            {**_make_row("_"), "announcementId": float("nan")},
            {**_make_row("_"), "announcementId": pd.NA},
            {**_make_row("_"), "announcementId": pd.NaT},
        ]
        cf.write_filings(rows)
        assert cf.load_filings().empty
        assert cf.LAST_KEY_INTEGRITY["excluded_by_type"] == {"nan": 3}

    def test_valid_rows_preserved_beside_malformed_ones(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        rows = [
            _make_row("K001"),
            {**_make_row("_"), "announcementId": ""},
            _make_row("K002"),
        ]
        net = cf.write_filings(rows)
        assert net == 2
        stored = cf.load_filings()
        assert set(stored["announcementId"]) == {"K001", "K002"}

    def test_preexisting_unkeyed_rows_preserved_across_new_batch_write(
        self, tmp_path, monkeypatch
    ):
        """A store already holding 2 unkeyed rows plus a new batch must
        still hold both unkeyed rows afterwards — they are protected
        VERBATIM from the keyed dedup, never silently collapsed."""
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        bad1 = {**_make_row("_", "旧脏数据1"), "announcementId": None}
        bad2 = {**_make_row("_", "旧脏数据2"), "announcementId": "   "}
        seed = pd.DataFrame([bad1, bad2]).reindex(columns=list(cf._COLUMNS))
        seed.to_parquet(tmp_path / "filings.parquet", index=False)

        cf.write_filings([_make_row("Z001", "新公告")])
        stored = cf.load_filings()
        assert len(stored) == 3
        titles = set(stored["title"])
        assert {"旧脏数据1", "旧脏数据2", "新公告"} == titles
        assert cf.LAST_KEY_INTEGRITY["preexisting_unkeyed"] == 2

    def test_net_new_arithmetic_unaffected_by_malformed_rows(self, tmp_path, monkeypatch):
        """A malformed row must never inflate or deflate net_new — it is
        computed off the KEYED frames only."""
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        net1 = cf.write_filings([_make_row("N001")])
        assert net1 == 1
        # Second call: one genuinely new keyed row plus 2 malformed rows.
        net2 = cf.write_filings([
            _make_row("N002"),
            {**_make_row("_"), "announcementId": ""},
            {**_make_row("_"), "announcementId": None},
        ])
        assert net2 == 1   # only N002 is net-new; malformed rows don't count
        assert cf.LAST_KEY_INTEGRITY["excluded_total"] == 2

    def test_clean_write_reports_zeros(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        cf.write_filings([_make_row("C001"), _make_row("C002")])
        assert cf.LAST_KEY_INTEGRITY["excluded_total"] == 0
        assert cf.LAST_KEY_INTEGRITY["excluded_by_type"] == {}
        assert cf.LAST_KEY_INTEGRITY["preexisting_unkeyed"] == 0

    def test_loud_on_exclusion_log_and_annotation(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        cf.write_filings([{**_make_row("_"), "announcementId": ""}])
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.startswith("::")]
        assert lines, f"no line-start GitHub annotation found in stdout: {out!r}"
        assert "china-filings-malformed-announcement-id" in lines[0]

    def test_no_annotation_on_clean_write(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        cf.write_filings([_make_row("Q001")])
        out = capsys.readouterr().out
        assert not any(ln.startswith("::") for ln in out.splitlines())


# --------------------------------------------------------------------------- #
# P1-R2 — LAST_RUN_OUTCOME.key_integrity folding (adapter.fetch())
# --------------------------------------------------------------------------- #

class TestFetchKeyIntegrityFolding:
    def test_key_integrity_present_and_zero_on_clean_fetch(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        adapter = cf.ChinaFilingsAdapter()

        def fake_fetch_exchange(exchange, date_range, session, collected_at):
            return [_make_row("FI001", exchange=exchange)]

        import requests as _requests
        with patch.object(adapter, "_fetch_exchange", side_effect=fake_fetch_exchange):
            with patch.object(_requests, "Session", return_value=MagicMock()):
                adapter.fetch()

        ki = cf.LAST_RUN_OUTCOME["key_integrity"]
        assert ki["excluded_total"] == 0
        assert ki["preexisting_unkeyed"] == 0
        assert cf.LAST_RUN_OUTCOME["ok"] is True

    def test_malformed_key_degrades_ok_via_typed_errors_entry(self, tmp_path, monkeypatch):
        """FAIL-SOFT preserved: malformed keys degrade `ok` to False via a
        typed errors[] entry — fetch() must NOT raise for this reason."""
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        adapter = cf.ChinaFilingsAdapter()

        def fake_fetch_exchange(exchange, date_range, session, collected_at):
            if exchange == "sse":
                return [{**_make_row("_", exchange=exchange), "announcementId": ""}]
            return [_make_row("FI002", exchange=exchange)]

        import requests as _requests
        with patch.object(adapter, "_fetch_exchange", side_effect=fake_fetch_exchange):
            with patch.object(_requests, "Session", return_value=MagicMock()):
                result = adapter.fetch()   # must not raise

        assert "china_filings_summary" in result   # completed normally
        assert cf.LAST_RUN_OUTCOME["ok"] is False
        assert any("key_integrity" in e for e in cf.LAST_RUN_OUTCOME["errors"])
        assert cf.LAST_RUN_OUTCOME["key_integrity"]["excluded_total"] == 1
        # the sibling valid row was still fetched, stored, and returned
        assert "FI002" in set(cf.load_filings()["announcementId"])

    def test_key_integrity_reset_fail_closed_at_fetch_entry(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        cf.LAST_KEY_INTEGRITY = {
            "excluded_total": 99, "excluded_by_type": {}, "preexisting_unkeyed": 0,
            "at": "stale",
        }
        seen: list = []

        def _fetch_exchange(self, exchange, date_range, session, collected_at):
            # Captured before write_filings ever runs — LAST_KEY_INTEGRITY
            # must already be None (fail-closed) by the time exchange fetch
            # logic starts, mirroring LAST_RUN_OUTCOME's own fail-closed proof.
            seen.append(cf.LAST_KEY_INTEGRITY)
            raise IOError("simulated CNInfo outage")
        monkeypatch.setattr(cf.ChinaFilingsAdapter, "_fetch_exchange", _fetch_exchange)
        adapter = cf.ChinaFilingsAdapter()
        with pytest.raises(RuntimeError):
            adapter.fetch()   # both exchanges fail -> "all exchanges failed" branch
        assert seen[0] is None

    def test_all_exchanges_failed_still_carries_zero_key_integrity(self, monkeypatch):
        def _fetch_exchange(self, exchange, date_range, session, collected_at):
            raise IOError("simulated outage")
        monkeypatch.setattr(cf.ChinaFilingsAdapter, "_fetch_exchange", _fetch_exchange)
        adapter = cf.ChinaFilingsAdapter()
        with pytest.raises(RuntimeError):
            adapter.fetch()
        assert cf.LAST_RUN_OUTCOME["key_integrity"]["excluded_total"] == 0
        # Shape stability is the point: every consumer reads one shape.
        assert set(cf.LAST_RUN_OUTCOME["key_integrity"]) == {
            "excluded_total", "excluded_by_type", "preexisting_unkeyed", "at"}

    def test_incomplete_write_folds_in_as_UNKNOWN_not_clean(self, tmp_path, monkeypatch):
        """FAIL-CLOSED: write_filings() failing internally leaves
        LAST_KEY_INTEGRITY None, and `None or zeros` would launder that into a
        CLEAN reading — ok stays True, china_visits stamps coverage and
        advances last_success_utc over a store that was never written, and the
        dossier renders measured_no_event for names whose filings are missing.
        Caught by an adversarial review 2026-08-22.

        MUTATION GUARD: drop the `if LAST_KEY_INTEGRITY is None` branch in
        fetch() and `ok` comes back True here.
        """
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        monkeypatch.setattr(cf, "write_filings", lambda rows: 0)  # never sets the global
        adapter = cf.ChinaFilingsAdapter()

        def fake_fetch_exchange(exchange, date_range, session, collected_at):
            return [_make_row(f"U-{exchange}", exchange=exchange)]

        import requests as _requests
        with patch.object(adapter, "_fetch_exchange", side_effect=fake_fetch_exchange):
            with patch.object(_requests, "Session", return_value=MagicMock()):
                adapter.fetch()   # must not raise — fail-SOFT, just not clean

        assert cf.LAST_RUN_OUTCOME["ok"] is False
        assert any("UNKNOWN" in e for e in cf.LAST_RUN_OUTCOME["errors"])


# --------------------------------------------------------------------------- #
# P1-R2 — an UNREADABLE accrued store must never be silently replaced
# --------------------------------------------------------------------------- #

class TestUnreadableStoreAborts:
    def test_corrupt_store_aborts_the_write_instead_of_truncating_the_tape(
        self, tmp_path, monkeypatch
    ):
        """write_filings() rewrites the ENTIRE accrued tape every night. It
        used to source that rewrite from load_filings(), which swallows a read
        error and answers EMPTY — so a corrupt store read as "no existing
        rows" and the next write REPLACED the whole tape with tonight's batch.
        Measured 2026-08-22 by an adversarial review: a 500-row store became 1
        row, net_new reported 1, and every key-integrity instrument read clean.

        MUTATION GUARD: swap _read_filings_strict() back to load_filings() in
        write_filings() and this test stores 1 row instead of aborting.
        """
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        cf.write_filings([_make_row(f"S{i:03d}") for i in range(50)])
        assert len(cf.load_filings()) == 50

        (tmp_path / "filings.parquet").write_bytes(b"not a parquet file")
        assert cf._read_filings_strict() is None          # present but unreadable

        assert cf.write_filings([_make_row("NEW001")]) == 0   # ABORT, never raises
        # The corrupt file is left untouched for manual recovery — NOT replaced
        # by a 1-row store.
        assert (tmp_path / "filings.parquet").read_bytes() == b"not a parquet file"

    def test_absent_store_is_not_treated_as_unreadable(self, tmp_path, monkeypatch):
        """The strict reader must distinguish "no store yet" (normal first
        run — write proceeds) from "present but corrupt" (abort)."""
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        assert cf._read_filings_strict() is not None
        assert cf.write_filings([_make_row("F001")]) == 1


# --------------------------------------------------------------------------- #
# P1-R2 — the natural key is canonicalized at the write boundary
# --------------------------------------------------------------------------- #

class TestKeyNormalizationAtWriteBoundary:
    def test_padded_and_bare_forms_of_one_id_are_the_same_row(
        self, tmp_path, monkeypatch
    ):
        """Padding that strips to a real value is NOT malformed, so the
        key-integrity partition passes it through — but " 1234567 " and
        "1234567" are two distinct keys to drop_duplicates, so the same filing
        published once with incidental padding would store TWICE and appear
        twice in the dossier's recent-visit list. Caught by an adversarial
        review 2026-08-22.

        MUTATION GUARD: remove the normalize_announcement_id() map in
        write_filings() and this stores 2 rows.
        """
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        cf.write_filings([{**_make_row("_"), "announcementId": " 1234567 "}])
        cf.write_filings([{**_make_row("_"), "announcementId": "1234567"}])
        stored = cf.load_filings()
        assert len(stored) == 1
        assert list(stored["announcementId"]) == ["1234567"]

    def test_unhashable_key_cannot_silently_lose_the_whole_batch(
        self, tmp_path, monkeypatch
    ):
        """key_anomaly() answers None for a non-scalar (a list is not missing,
        NaN, empty or whitespace — the four frozen anomalies), so such a value
        reaches drop_duplicates(subset=["announcementId"]), which raises
        TypeError on an unhashable cell. That raise is caught by
        write_filings' own outer except, which returns 0 — losing the WHOLE
        batch, including every valid sibling row. Normalizing to the string
        form at the write boundary keeps the column hashable.
        """
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        net = cf.write_filings([
            {**_make_row("_"), "announcementId": [1, 2]},
            _make_row("GOOD001"),
        ])
        assert net == 2
        assert "GOOD001" in set(cf.load_filings()["announcementId"])


# --------------------------------------------------------------------------- #
# P1-R2 — mutation guard: write_filings' exclusion depends on the REAL guard
# --------------------------------------------------------------------------- #

class TestKeyIntegrityMutationGuard:
    def test_stub_partition_reporting_all_wellkeyed_lets_malformed_rows_survive(
        self, tmp_path, monkeypatch
    ):
        """MUTATION GUARD: runs the SAME input through the real guard and
        through the pre-repair shape, in one test, and asserts they differ.

        Both halves are required. Asserting only that the stub collapses 3
        rows into 1 is a tautology about the stub — delete
        partition_by_key_integrity from write_filings entirely and that
        assertion still holds, because the stubbed path is the only one the
        test ever exercises. So the real guard is exercised FIRST (3 rows
        sharing announcementId="" -> 0 stored, typed-excluded and counted as
        3), then the guard is mutated away and the same 3 rows are shown to
        collapse into ONE via drop_duplicates — exactly the silent-collapse
        bug DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP describes.
        Weakness caught by an adversarial review 2026-08-22.
        """
        monkeypatch.setattr(cf, "_store_path", lambda: tmp_path / "filings.parquet")
        rows = [
            {**_make_row("_", "标题1"), "announcementId": ""},
            {**_make_row("_", "标题2"), "announcementId": ""},
            {**_make_row("_", "标题3"), "announcementId": ""},
        ]

        # --- the REAL guard: all 3 typed-excluded, counted individually ---
        assert cf.write_filings(list(rows)) == 0
        assert len(cf.load_filings()) == 0
        assert cf.LAST_KEY_INTEGRITY["excluded_total"] == 3
        assert cf.LAST_KEY_INTEGRITY["excluded_by_type"] == {"empty": 3}

        # --- the MUTATION: guard removed, pandas collapses 3 into 1 ---
        monkeypatch.setattr(
            cf, "partition_by_key_integrity",
            lambda rows: (list(rows), [], {}),   # reports every row well-keyed
        )
        cf.write_filings(list(rows))
        assert len(cf.load_filings()) == 1
