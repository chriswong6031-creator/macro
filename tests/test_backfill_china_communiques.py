"""Tests for the curated communiqué backfill — W1.1.

Covers (NO live network — all HTTP mocked or bypassed):
  1. PBoC MPC pagination href extraction from raw HTML
  2. PBoC MPC article href extraction from listing page HTML
  3. PBoC MPC date/quarter/year extraction helpers
  4. Politburo econ filter (_is_politburo_econ)
  5. CEWC filter (_is_cewc)
  6. Meeting date extraction from Chinese text
  7. doc_id generation (deterministic sha256)
  8. Resumability: existing doc_id is skipped
  9. upsert_rows keep-FIRST semantics
  10. Explicit gap row emitted for CEWC 2017
  11. Listing-date parsing from hui12 spans (Bug 1 fix)
  12. Page-range synthesis covers the missing -3 gap (Bug 2 fix)
  13. publish_date lands from listing while meeting_date stays body-derived
  14. Spurious-year rejection: meeting_year anchors on broadcast date (fix a)
  15. Reference-vs-readout discrimination for politburo_econ/cewc (fix b)
  16. Per-meeting dedup: one readout per meeting, earliest date + longest body (fix c)
  17. Local CCTV archive mode: covered days read locally, fallbacks to network
  18. _call_with_timeout: hard ceiling on hung akshare fetches

Run: .venv/bin/python -m pytest tests/test_backfill_china_communiques.py -v
  or: .venv/bin/python -m tests.test_backfill_china_communiques
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

# Make repo root importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.backfill_china_communiques import (  # noqa: E402
    CCTV_YEAR_MAX,
    CCTV_YEAR_MIN,
    PBOC_BASE,
    PBOC_INDEX_URL,
    _PBOC_HREF_RE,
    _archive_day_items,
    _call_with_timeout,
    _cctv_fetch_day,
    _cctv_listing_titles,
    _cctv_scan_dates,
    _cewc_meeting_key,
    _decode_html,
    _is_cewc,
    _is_politburo_econ,
    _listing_may_be_cewc,
    _listing_may_be_politburo_econ,
    _politburo_meeting_key,
    broadcast_meeting_year,
    plausible_meeting_date,
    _parse_listing_entries,
    _pboc_article_hrefs,
    _pboc_fetch_article,
    _pboc_page_urls,
    extract_meeting_date,
    extract_meeting_year,
    extract_quarter,
    fetch_cewc,
    fetch_pboc_mpc,
    fetch_politburo_econ,
    load_existing,
    make_doc_id,
    OUT_PATH,
    save_parquet,
    upsert_rows,
)

# ---------------------------------------------------------------------------
# Fixtures — HTML fragments (no live network)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "data" / "china_communiques"

_PBOC_INDEX_HTML = (FIXTURES_DIR / "pboc_index_page1.html").read_text(encoding="utf-8")
_PBOC_PAGE2_HTML = (FIXTURES_DIR / "pboc_index_page2.html").read_text(encoding="utf-8")
_PBOC_PAGE3_HTML = (FIXTURES_DIR / "pboc_index_page3.html").read_text(encoding="utf-8")
_PBOC_ARTICLE_HTML = (FIXTURES_DIR / "pboc_article_2021q1.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. PBoC pagination URL extraction (with page-range synthesis)
# ---------------------------------------------------------------------------

class TestPbocPaginationHrefs:
    def test_extracts_page2_and_synthesises_page3_from_page4(self) -> None:
        # Page 1 footer lists -2 and -4 only; synthesis must fill -3.
        pages = _pboc_page_urls(_PBOC_INDEX_HTML, PBOC_INDEX_URL)
        # Should produce pages 2, 3, 4 (synthesis fills the gap at 3)
        assert len(pages) == 3
        assert any("af7dde41-2.html" in p for p in pages)
        assert any("af7dde41-3.html" in p for p in pages)  # synthesised gap
        assert any("af7dde41-4.html" in p for p in pages)

    def test_no_duplicates(self) -> None:
        # Page HTML with two identical pagination links
        html_dup = _PBOC_INDEX_HTML.replace(
            '<a href="af7dde41-2.html">2</a>',
            '<a href="af7dde41-2.html">2</a><a href="af7dde41-2.html">next</a>'
        )
        pages = _pboc_page_urls(html_dup, PBOC_INDEX_URL)
        urls_2 = [p for p in pages if "af7dde41-2.html" in p]
        assert len(urls_2) == 1

    def test_no_pages_in_single_page(self) -> None:
        # A listing with no af7dde41-N.html links → empty
        html_no_pages = "<html><body><ul><li>article</li></ul></body></html>"
        pages = _pboc_page_urls(html_no_pages, PBOC_INDEX_URL)
        assert pages == []

    def test_sibling_url_constructed_correctly(self) -> None:
        pages = _pboc_page_urls(_PBOC_INDEX_HTML, PBOC_INDEX_URL)
        # Should be siblings of index.html in the same directory
        expected_base = PBOC_INDEX_URL.rsplit("/", 1)[0]
        assert all(p.startswith(expected_base) for p in pages)
        assert any("af7dde41-2.html" in p for p in pages)

    def test_synthesis_gap_fills_missing_page3(self) -> None:
        """Explicit test: when footer links -2 and -4 but not -3, -3 must be synthesised."""
        html = (
            '<a href="af7dde41-2.html">2</a>'
            '<a href="af7dde41-4.html">4</a>'
        )
        pages = _pboc_page_urls(html, PBOC_INDEX_URL)
        page_nums = {p.rsplit("/", 1)[-1] for p in pages}
        assert "af7dde41-3.html" in page_nums, (
            "Page 3 must be synthesised when footer only links -2 and -4"
        )


# ---------------------------------------------------------------------------
# 2. PBoC article href extraction
# ---------------------------------------------------------------------------

class TestPbocArticleHrefs:
    def test_extracts_all_three_hrefs_from_page1(self) -> None:
        hrefs = _pboc_article_hrefs(_PBOC_INDEX_HTML)
        assert len(hrefs) == 3

    def test_extracts_new_era_href(self) -> None:
        hrefs = _pboc_article_hrefs(_PBOC_INDEX_HTML)
        new_era = [h for h in hrefs if "3870936" in h]
        assert len(new_era) == 2  # 2021Q1 and 2020Q4 both new-era

    def test_extracts_old_era_href(self) -> None:
        hrefs = _pboc_article_hrefs(_PBOC_INDEX_HTML)
        old_era = [h for h in hrefs if "goutongjiaoliu" in h]
        assert len(old_era) == 1

    def test_extracts_hrefs_from_page2(self) -> None:
        hrefs = _pboc_article_hrefs(_PBOC_PAGE2_HTML)
        assert len(hrefs) == 2
        assert all("goutongjiaoliu" in h for h in hrefs)

    def test_no_hrefs_in_empty_page(self) -> None:
        assert _pboc_article_hrefs("<html><body>no articles</body></html>") == []

    def test_deduplication_within_page(self) -> None:
        # Duplicate link in HTML
        html = (
            '<a href="/zhengcehuobisi/125207/3870933/3870936/aabbccdd11223344aabbccdd11223344/index.html">A</a>'
            '<a href="/zhengcehuobisi/125207/3870933/3870936/aabbccdd11223344aabbccdd11223344/index.html">B</a>'
        )
        hrefs = _pboc_article_hrefs(html)
        assert len(hrefs) == 1


# ---------------------------------------------------------------------------
# 3. Date / quarter / year extraction
# ---------------------------------------------------------------------------

class TestDateExtraction:
    def test_meeting_date_from_standard_format(self) -> None:
        text = "中国人民银行货币政策委员会2021年第一季度例会于2021年3月29日在北京召开。"
        assert extract_meeting_date(text) == "2021-03-29"

    def test_meeting_date_none_when_absent(self) -> None:
        assert extract_meeting_date("没有日期的文本") is None

    def test_meeting_date_handles_single_digit_month(self) -> None:
        assert extract_meeting_date("2009年3月15日") == "2009-03-15"

    def test_meeting_date_handles_two_digit_day(self) -> None:
        assert extract_meeting_date("2020年12月18日") == "2020-12-18"

    def test_year_extraction(self) -> None:
        assert extract_meeting_year("2021年第一季度货币政策委员会例会") == 2021

    def test_year_extraction_none(self) -> None:
        assert extract_meeting_year("没有年份") is None

    def test_quarter_extraction_q1(self) -> None:
        assert extract_quarter("2021年第一季度例会") == 1

    def test_quarter_extraction_q2(self) -> None:
        assert extract_quarter("2021年第二季度例会") == 2

    def test_quarter_extraction_q3(self) -> None:
        assert extract_quarter("第三季度货币政策委员会") == 3

    def test_quarter_extraction_q4(self) -> None:
        assert extract_quarter("2020年第四季度货币政策委员会例会") == 4

    def test_quarter_extraction_none(self) -> None:
        assert extract_quarter("没有季度的文本") is None


# ---------------------------------------------------------------------------
# 4. Politburo econ filter
# ---------------------------------------------------------------------------

class TestPolitburoEconFilter:
    def test_passes_with_both_keywords_jingji_xingshi(self) -> None:
        assert _is_politburo_econ(
            "中共中央政治局召开会议 分析研究当前经济形势",
            "7月28日，中共中央政治局召开会议，分析研究当前经济形势和经济工作。"
        )

    def test_passes_with_jingji_gongzuo(self) -> None:
        # December meeting form: 分析研究明年经济工作 (econ keyword via 经济工作)
        assert _is_politburo_econ(
            "中共中央政治局召开会议 分析研究2025年经济工作",
            "中共中央政治局12月6日召开会议，分析研究2025年经济工作。会议强调，要做好明年经济工作。"
        )

    def test_fails_without_zhengzhiju(self) -> None:
        # No 中共中央政治局召开会议 headline → should fail
        assert not _is_politburo_econ(
            "国务院常务会议召开",
            "研究当前经济形势"
        )

    def test_fails_without_economic_keyword(self) -> None:
        # Readout headline + convening phrase, but not an economic meeting
        assert not _is_politburo_econ(
            "中共中央政治局召开会议",
            "中共中央政治局10月28日召开会议，研究外交和安全议题。"
        )

    def test_fails_keyword_in_content_but_title_not_readout(self) -> None:
        # Mention-level match (old over-matching behavior) must now be rejected:
        # the title is not the canonical readout headline.
        assert not _is_politburo_econ(
            "中央召开重要会议",
            "政治局会议分析经济形势"
        )


# ---------------------------------------------------------------------------
# 5. CEWC filter
# ---------------------------------------------------------------------------

class TestCewcFilter:
    def test_passes_with_cewc_keyword(self) -> None:
        assert _is_cewc(
            "中央经济工作会议在北京举行",
            "中央经济工作会议12月15日至16日在北京举行。"
        )

    def test_fails_with_keyword_in_content_only(self) -> None:
        # Mention-level match (old over-matching behavior) must now be rejected:
        # the title is not the canonical readout headline.
        assert not _is_cewc(
            "重要会议召开",
            "中央经济工作会议圆满结束"
        )

    def test_fails_without_cewc_keyword(self) -> None:
        # Politburo econ meeting but not CEWC
        assert not _is_cewc(
            "政治局召开会议分析经济形势",
            "会议分析了当前经济运行情况"
        )

    def test_fails_on_unrelated_content(self) -> None:
        assert not _is_cewc("外交部发言人记者会", "答记者问")

    def test_listing_prescreen_is_permissive(self) -> None:
        # Phase-1 pre-screen accepts truncated/reformatted listing titles
        assert _listing_may_be_cewc("[视频]中央经济工作会议在北")
        assert not _listing_may_be_cewc("国务院常务会议召开")


# ---------------------------------------------------------------------------
# 6. doc_id generation
# ---------------------------------------------------------------------------

class TestDocId:
    def test_deterministic(self) -> None:
        url = "https://www.pbc.gov.cn/test/index.html"
        title = "2021年第一季度货币政策委员会例会"
        assert make_doc_id(url, title) == make_doc_id(url, title)

    def test_different_url_different_id(self) -> None:
        title = "同样的标题"
        id1 = make_doc_id("https://example.com/a", title)
        id2 = make_doc_id("https://example.com/b", title)
        assert id1 != id2

    def test_different_title_different_id(self) -> None:
        url = "https://example.com/a"
        assert make_doc_id(url, "标题一") != make_doc_id(url, "标题二")

    def test_is_hex_64_chars(self) -> None:
        doc_id = make_doc_id("https://example.com/a", "test")
        assert len(doc_id) == 64
        assert all(c in "0123456789abcdef" for c in doc_id)


# ---------------------------------------------------------------------------
# 7. Resumability: existing doc_id is skipped
# ---------------------------------------------------------------------------

class TestResumability:
    def test_known_doc_id_skipped_in_upsert(self) -> None:
        """If a doc_id is already in existing_df, a new row with the same id is dropped."""
        existing = pd.DataFrame([{
            "doc_id": "aabbcc",
            "family": "pboc_mpc",
            "meeting_year": 2021,
            "meeting_quarter": 1,
            "meeting_date": "2021-03-29",
            "publish_date": "2021-03-29",
            "title": "Original title",
            "body": "Original body",
            "body_sha256": hashlib.sha256(b"Original body").hexdigest(),
            "url": "https://www.pbc.gov.cn/test/index.html",
            "source": "pbc.gov.cn",
            "_fetched_at": "2021-03-29T00:00:00Z",
        }])
        new_row = {
            "doc_id": "aabbcc",  # Same doc_id
            "family": "pboc_mpc",
            "meeting_year": 2021,
            "meeting_quarter": 1,
            "meeting_date": "2021-03-29",
            "publish_date": "2021-03-29",
            "title": "Updated title",  # Different title — should be ignored
            "body": "Updated body",
            "body_sha256": hashlib.sha256(b"Updated body").hexdigest(),
            "url": "https://www.pbc.gov.cn/test/index.html",
            "source": "pbc.gov.cn",
            "_fetched_at": "2022-01-01T00:00:00Z",
        }
        result = upsert_rows(existing, [new_row])
        assert len(result) == 1
        # keep-FIRST: original title wins
        assert result.iloc[0]["title"] == "Original title"

    def test_new_doc_id_is_added(self) -> None:
        existing = pd.DataFrame(columns=[
            "doc_id", "family", "meeting_year", "meeting_quarter",
            "meeting_date", "publish_date", "title", "body", "body_sha256",
            "url", "source", "_fetched_at",
        ])
        new_row = {
            "doc_id": "newid123",
            "family": "pboc_mpc",
            "meeting_year": 2020,
            "meeting_quarter": 3,
            "meeting_date": "2020-09-28",
            "publish_date": "2020-09-28",
            "title": "2020年第三季度货币政策委员会例会",
            "body": "会议内容",
            "body_sha256": hashlib.sha256(b"body").hexdigest(),
            "url": "https://www.pbc.gov.cn/test2/index.html",
            "source": "pbc.gov.cn",
            "_fetched_at": "2020-09-28T00:00:00Z",
        }
        result = upsert_rows(existing, [new_row])
        assert len(result) == 1
        assert result.iloc[0]["doc_id"] == "newid123"


# ---------------------------------------------------------------------------
# 8. upsert_rows keep-FIRST semantics
# ---------------------------------------------------------------------------

class TestUpsertRows:
    def _make_row(self, doc_id: str, title: str, family: str = "pboc_mpc") -> dict:
        return {
            "doc_id": doc_id,
            "family": family,
            "meeting_year": 2021,
            "meeting_quarter": 1,
            "meeting_date": "2021-03-29",
            "publish_date": "2021-03-29",
            "title": title,
            "body": "body",
            "body_sha256": hashlib.sha256(b"body").hexdigest(),
            "url": f"https://example.com/{doc_id}",
            "source": "pbc.gov.cn",
            "_fetched_at": "2021-03-29T00:00:00Z",
        }

    def test_no_rows_returns_existing_unchanged(self) -> None:
        existing = pd.DataFrame([self._make_row("abc", "title A")])
        result = upsert_rows(existing, [])
        assert len(result) == 1
        assert result.iloc[0]["doc_id"] == "abc"

    def test_two_new_rows_added(self) -> None:
        existing = pd.DataFrame(columns=[
            "doc_id", "family", "meeting_year", "meeting_quarter",
            "meeting_date", "publish_date", "title", "body", "body_sha256",
            "url", "source", "_fetched_at",
        ])
        result = upsert_rows(existing, [
            self._make_row("id1", "A"),
            self._make_row("id2", "B"),
        ])
        assert len(result) == 2
        assert set(result["doc_id"].tolist()) == {"id1", "id2"}

    def test_first_occurrence_wins_on_collision(self) -> None:
        existing = pd.DataFrame([self._make_row("dup", "First title")])
        result = upsert_rows(existing, [self._make_row("dup", "Second title")])
        assert len(result) == 1
        assert result.iloc[0]["title"] == "First title"


# ---------------------------------------------------------------------------
# 9. Explicit CEWC 2017 gap row
# ---------------------------------------------------------------------------

class TestCewcGapRow:
    def test_gap_2017_emitted_when_not_found(self) -> None:
        """When CCTV returns no CEWC for 2017, an explicit gap row must be added."""
        # Mock listing + fetch + time.sleep so test doesn't sleep through 10 years;
        # curated gov.cn fallbacks are out of scope here (tested separately).
        with patch("scripts.backfill_china_communiques._cctv_listing_titles", return_value=[]), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day", return_value=[]), \
             patch.dict("scripts.backfill_china_communiques.CEWC_GOVCN_FALLBACKS", {}, clear=True), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            session = MagicMock()
            known_ids: set[str] = set()
            rows = fetch_cewc(session, known_ids, limit=None, dry_run=False)

        gap_rows = [r for r in rows if "KNOWN GAP" in r["title"] and "2017" in r["title"]]
        assert len(gap_rows) == 1
        gap = gap_rows[0]
        assert gap["family"] == "cewc"
        assert gap["meeting_year"] == 2017
        assert gap["source"] == "explicit_gap"
        assert gap["meeting_date"] is None
        assert "absent" in gap["body"].lower() or "gap" in gap["body"].lower()

    def test_gap_row_not_duplicated_on_rerun(self) -> None:
        """If the gap row's doc_id is already in known_ids, it is not added again."""
        with patch("scripts.backfill_china_communiques._cctv_listing_titles", return_value=[]), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day", return_value=[]), \
             patch.dict("scripts.backfill_china_communiques.CEWC_GOVCN_FALLBACKS", {}, clear=True), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            session = MagicMock()
            known_ids: set[str] = set()
            rows1 = fetch_cewc(session, known_ids, limit=None, dry_run=False)
            # known_ids now contains the gap doc_id
            rows2 = fetch_cewc(session, known_ids, limit=None, dry_run=False)

        gap_rows_run2 = [r for r in rows2 if "KNOWN GAP" in r.get("title", "")]
        assert len(gap_rows_run2) == 0  # Not added twice


# ---------------------------------------------------------------------------
# 10. Decode helper (charset)
# ---------------------------------------------------------------------------

class TestDecodeHtml:
    def test_utf8_passthrough(self) -> None:
        html = "<html><body>你好世界</body></html>"
        result = _decode_html(html.encode("utf-8"), "text/html; charset=utf-8")
        assert "你好世界" in result

    def test_gb2312_decoded_as_gb18030(self) -> None:
        text = "货币政策委员会例会"
        content = text.encode("gb18030")
        result = _decode_html(content, "text/html; charset=gb2312")
        assert "货币政策委员会例会" in result

    def test_meta_charset_fallback(self) -> None:
        html = b'<html><head><meta charset="gb2312"></head><body>\xbb\xf5\xb1\xd2</body></html>'
        # Should not crash even if decoding is imperfect
        result = _decode_html(html)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 11. Short-form listing title coverage (Finding 1)
# ---------------------------------------------------------------------------

class TestPolitburoShortTitleCoverage:
    """Verify that real short-form politburo listing titles are not silently dropped.

    Real Xinwen Lianbo listing titles are frequently '中共中央政治局召开会议 习近平主持'
    — the economic keyword appears only in the body.  The two-phase filter must use the
    permissive pre-screen (_listing_may_be_politburo_econ) at Phase 1 and only apply
    the strict filter at Phase 2, so such items are never silently dropped.
    """

    def test_strict_filter_fails_short_title(self) -> None:
        """Confirm the strict filter returns False for short-form title (no econ keyword)."""
        short_title = "中共中央政治局召开会议 习近平主持"
        assert not _is_politburo_econ(short_title, "")

    def test_permissive_prefetch_passes_short_title(self) -> None:
        """The listing pre-screen should pass short-form titles that contain 政治局."""
        short_title = "中共中央政治局召开会议 习近平主持"
        assert _listing_may_be_politburo_econ(short_title)

    def test_permissive_prefetch_fails_unrelated_title(self) -> None:
        """Titles without 政治局 are correctly rejected by the pre-screen."""
        assert not _listing_may_be_politburo_econ("外交部发言人记者会")
        assert not _listing_may_be_politburo_econ("国务院常务会议")

    def test_short_title_day_gets_full_fetch(self) -> None:
        """When a listing has only a short-form title, a full body fetch IS triggered
        and the strict filter is applied to the full content at Phase 2.

        This test mocks _cctv_listing_titles to return a short-form title only,
        and _cctv_fetch_day to return a realistic item with the econ keyword in body.
        The resulting row must be collected.
        """
        short_title = "中共中央政治局召开会议 习近平主持"
        full_body_item = {
            "title": short_title,
            "content": (
                "7月28日，中共中央政治局召开会议，分析研究当前经济形势和经济工作。"
                "习近平主持会议。会议认为，今年以来经济形势总体向好。"
            ),
        }

        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   return_value=[(short_title, "http://cctv.com/some/url")]), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   return_value=[full_body_item]), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            session = MagicMock()
            known_ids: set[str] = set()
            rows = fetch_politburo_econ(session, known_ids, limit=None, dry_run=False)

        # Must have captured the meeting — it would have been silently dropped
        # by the old code that applied filter_fn(title, "") at Phase 1.
        real_rows = [r for r in rows if r["family"] == "politburo_econ"]
        assert len(real_rows) >= 1, (
            "Short-form listing title resulted in zero rows — the meeting was silently dropped. "
            "The Phase-1 pre-screen must use _listing_may_be_politburo_econ, not _is_politburo_econ."
        )

    def test_short_title_body_only_item_rejected_if_no_econ_keyword(self) -> None:
        """A short-form listing title triggers a fetch, but if body also lacks the econ
        keyword the strict Phase-2 filter correctly rejects it (not a false positive)."""
        short_title = "中共中央政治局召开会议 习近平主持"
        non_econ_item = {
            "title": short_title,
            "content": "会议研究外交和安全议题。",
        }

        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   return_value=[(short_title, "http://cctv.com/some/url")]), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   return_value=[non_econ_item]), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            session = MagicMock()
            known_ids: set[str] = set()
            rows = fetch_politburo_econ(session, known_ids, limit=None, dry_run=False)

        assert len(rows) == 0, "Non-econ politburo meeting should be rejected at Phase 2"


# ---------------------------------------------------------------------------
# 12. PBoC pagination hash flexibility (Finding 3)
# ---------------------------------------------------------------------------

class TestPbocPaginationHashFlexibility:
    """Verify _pboc_page_urls handles any 8-hex-char prefix, not just 'af7dde41'."""

    def test_discovers_known_hash_af7dde41(self) -> None:
        """Original known hash still works."""
        html = '<a href="af7dde41-2.html">2</a>'
        pages = _pboc_page_urls(html, PBOC_INDEX_URL)
        assert len(pages) == 1
        assert "af7dde41-2.html" in pages[0]

    def test_discovers_alternative_hash(self) -> None:
        """If CMS redeploys with a different hash prefix, pagination is still discovered."""
        html = '<a href="deadbeef-2.html">2</a><a href="deadbeef-3.html">3</a>'
        pages = _pboc_page_urls(html, PBOC_INDEX_URL)
        assert len(pages) == 2
        assert any("deadbeef-2.html" in p for p in pages)
        assert any("deadbeef-3.html" in p for p in pages)

    def test_non_hex_prefix_not_matched(self) -> None:
        """A non-8-hex-char prefix does not match (no false positives)."""
        # 'zzzzzzzz' is not hex; 'abcde123' is only 8 chars and IS hex — use 7
        html = '<a href="abcdefg-2.html">2</a>'  # 7-char prefix — not a valid hex8
        pages = _pboc_page_urls(html, PBOC_INDEX_URL)
        assert len(pages) == 0

    def test_returns_empty_when_no_pagination_hrefs(self) -> None:
        """Single-page listing with no pagination returns empty list."""
        pages = _pboc_page_urls("<html><body>no pages</body></html>", PBOC_INDEX_URL)
        assert pages == []

    def test_no_duplicates_with_alternative_hash(self) -> None:
        """Duplicate hrefs with alternative hash are deduplicated."""
        html = (
            '<a href="deadbeef-2.html">2</a>'
            '<a href="deadbeef-2.html">next</a>'
        )
        pages = _pboc_page_urls(html, PBOC_INDEX_URL)
        assert len(pages) == 1


# ---------------------------------------------------------------------------
# 13. Listing-date parsing from hui12 spans (Bug 1 fix)
# ---------------------------------------------------------------------------

class TestListingDateParsing:
    """_parse_listing_entries extracts (href, publish_date) pairs from a listing page."""

    def test_extracts_date_from_hui12_span(self) -> None:
        """hui12 span with valid YYYY-MM-DD adjacent to article link is captured."""
        html = """
        <table><tr><td>
          <font><a href="/zhengcehuobisi/125207/3870933/3870936/db112f50a19144d1ab7ac217a69f2fa5/index.html">
            2021年第一季度货币政策委员会例会
          </a></font><span class="hui12">2021-03-31</span>
        </td></tr></table>
        """
        entries = _parse_listing_entries(html)
        assert len(entries) == 1
        href, pub = entries[0]
        assert "db112f50" in href
        assert pub == "2021-03-31"

    def test_missing_hui12_span_returns_none(self) -> None:
        """Entry without a hui12 span yields publish_date=None (not a crash)."""
        html = """
        <table><tr><td>
          <font><a href="/goutongjiaoliu/113456/113469/2025092212542380264/index.html">
            2009年第一季度货币政策委员会例会
          </a></font>
        </td></tr></table>
        """
        entries = _parse_listing_entries(html)
        assert len(entries) == 1
        href, pub = entries[0]
        assert "2025092212542380264" in href
        assert pub is None

    def test_malformed_hui12_date_returns_none(self) -> None:
        """hui12 span with bad content (not YYYY-MM-DD) yields None, not a crash."""
        html = """
        <table><tr><td>
          <font><a href="/zhengcehuobisi/125207/3870933/3870936/aabbccdd11223344aabbccdd11223344/index.html">title</a></font>
          <span class="hui12">not-a-date</span>
        </td></tr></table>
        """
        entries = _parse_listing_entries(html)
        assert len(entries) == 1
        _, pub = entries[0]
        assert pub is None

    def test_parses_page1_fixture_correctly(self) -> None:
        """Page1 fixture: two entries have hui12 dates, one does not."""
        entries = _parse_listing_entries(_PBOC_INDEX_HTML)
        assert len(entries) == 3
        dates = [pub for _, pub in entries]
        # Two entries with dates, one without
        non_null = [d for d in dates if d is not None]
        null_count = sum(1 for d in dates if d is None)
        assert len(non_null) == 2
        assert null_count == 1
        assert "2021-03-31" in non_null
        assert "2020-12-28" in non_null

    def test_deduplication_no_repeated_hrefs(self) -> None:
        """Duplicate anchors in HTML yield only one entry per href."""
        html = """
        <table>
          <tr><td><a href="/zhengcehuobisi/125207/3870933/3870936/db112f50a19144d1ab7ac217a69f2fa5/index.html">A</a>
          <span class="hui12">2021-03-31</span></td></tr>
          <tr><td><a href="/zhengcehuobisi/125207/3870933/3870936/db112f50a19144d1ab7ac217a69f2fa5/index.html">B (dup)</a>
          <span class="hui12">2021-03-31</span></td></tr>
        </table>
        """
        entries = _parse_listing_entries(html)
        assert len(entries) == 1

    def test_invalid_date_values_rejected(self) -> None:
        """YYYY-MM-DD pattern that is not a real calendar date is rejected."""
        html = """
        <table><tr><td>
          <font><a href="/zhengcehuobisi/125207/3870933/3870936/ffffffffffffffffffffffffffffffff/index.html">title</a></font>
          <span class="hui12">2021-13-45</span>
        </td></tr></table>
        """
        entries = _parse_listing_entries(html)
        assert len(entries) == 1
        _, pub = entries[0]
        assert pub is None, "Month=13 or day=45 should be rejected as invalid date"


# ---------------------------------------------------------------------------
# 14. Page-range synthesis covers the missing -3 gap (Bug 2 fix)
# ---------------------------------------------------------------------------

class TestPageRangeSynthesis:
    """fetch_pboc_mpc must synthesise page 3 when footer only links -2 and -4."""

    def _make_mock_response(self, html_content: str, encoding: str = "utf-8"):
        """Helper: fake requests response object."""
        mock_resp = MagicMock()
        mock_resp.content = html_content.encode(encoding)
        mock_resp.headers = {"content-type": f"text/html; charset={encoding}"}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_synthesis_generates_page3_url(self) -> None:
        """_pboc_page_urls with footer linking -2 and -4 must produce 3 pages (2,3,4)."""
        html = '<a href="af7dde41-2.html">2</a><a href="af7dde41-4.html">4</a>'
        pages = _pboc_page_urls(html, PBOC_INDEX_URL)
        filenames = {p.rsplit("/", 1)[-1] for p in pages}
        assert "af7dde41-2.html" in filenames
        assert "af7dde41-3.html" in filenames, "Gap at page 3 must be synthesised"
        assert "af7dde41-4.html" in filenames
        assert len(filenames) == 3

    def test_fetch_pboc_mpc_fetches_synthesised_page(self) -> None:
        """When fetch_pboc_mpc runs, it must attempt to fetch the synthesised page 3
        even though page 1's footer only links pages 2 and 4 (not 3)."""
        # Build minimal page HTMLs: page1 footer → -2 and -4 (gap at -3)
        page1_html = _PBOC_INDEX_HTML  # fixture has -2 and -4 in footer
        # Page 2: links to -3 and -4 in its footer (extending discovery)
        page2_html = _PBOC_PAGE2_HTML
        # Pages 3 and 4: minimal, no new hrefs
        empty_page_html = """<html><body><table></table>
        <div class="pages"><a href="af7dde41-2.html">2</a></div></body></html>"""

        fetched_urls: list[str] = []

        def fake_get(url: str, **kwargs):
            fetched_urls.append(url)
            if "af7dde41-2.html" in url:
                return self._make_mock_response(page2_html)
            elif "af7dde41-3.html" in url:
                return self._make_mock_response(empty_page_html)
            elif "af7dde41-4.html" in url:
                return self._make_mock_response(empty_page_html)
            else:
                # index.html
                return self._make_mock_response(page1_html)

        mock_session = MagicMock()
        mock_session.get.side_effect = fake_get

        with patch("scripts.backfill_china_communiques._pboc_fetch_article", return_value=None), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            fetch_pboc_mpc(mock_session, known_ids=set(), limit=0, dry_run=False)

        page3_fetched = any("af7dde41-3.html" in u for u in fetched_urls)
        assert page3_fetched, (
            f"Page 3 (synthesised gap) was never fetched. Fetched URLs: {fetched_urls}"
        )


# ---------------------------------------------------------------------------
# 15. publish_date from listing, meeting_date stays body-derived
# ---------------------------------------------------------------------------

class TestPublishDateFromListing:
    """_pboc_fetch_article: listing_publish_date takes precedence over body-extracted date."""

    def _make_session(self, html: str, encoding: str = "utf-8") -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.content = html.encode(encoding)
        mock_resp.headers = {"content-type": f"text/html; charset={encoding}"}
        mock_resp.raise_for_status = MagicMock()
        session = MagicMock()
        session.get.return_value = mock_resp
        return session

    def test_listing_publish_date_used_when_provided(self) -> None:
        """When listing_publish_date is passed, publish_date in the row equals that value."""
        session = self._make_session(_PBOC_ARTICLE_HTML)
        href = "/zhengcehuobisi/125207/3870933/3870936/db112f50a19144d1ab7ac217a69f2fa5/index.html"
        with patch("scripts.backfill_china_communiques.time.sleep"):
            row = _pboc_fetch_article(session, href, listing_publish_date="2021-03-31")
        assert row is not None
        assert row["publish_date"] == "2021-03-31"

    def test_meeting_date_stays_body_derived(self) -> None:
        """Even with listing_publish_date provided, meeting_date is still from body text."""
        session = self._make_session(_PBOC_ARTICLE_HTML)
        href = "/zhengcehuobisi/125207/3870933/3870936/db112f50a19144d1ab7ac217a69f2fa5/index.html"
        with patch("scripts.backfill_china_communiques.time.sleep"):
            row = _pboc_fetch_article(session, href, listing_publish_date="2021-03-31")
        assert row is not None
        # The fixture body contains "2021年3月29日" — body-extracted meeting date
        assert row["meeting_date"] == "2021-03-29"
        # publish_date and meeting_date are different — listing date vs meeting date
        assert row["publish_date"] != row["meeting_date"]

    def test_fallback_to_body_date_when_listing_date_absent(self) -> None:
        """When listing_publish_date is None, publish_date falls back to body-extracted date."""
        session = self._make_session(_PBOC_ARTICLE_HTML)
        href = "/zhengcehuobisi/125207/3870933/3870936/db112f50a19144d1ab7ac217a69f2fa5/index.html"
        with patch("scripts.backfill_china_communiques.time.sleep"):
            row = _pboc_fetch_article(session, href, listing_publish_date=None)
        assert row is not None
        # Without listing date, publish_date falls back to meeting_date (body-extracted)
        assert row["publish_date"] == row["meeting_date"]

    def test_publish_date_none_when_both_absent(self) -> None:
        """No listing date + no body date → publish_date is None."""
        # Article HTML with no Chinese date in body
        html_no_date = """<html><body>
        <title>货币政策委员会例会</title>
        <div class="zoom1">
          <p>中国人民银行货币政策委员会第一季度例会在北京召开。</p>
        </div></body></html>"""
        session = self._make_session(html_no_date)
        href = "/zhengcehuobisi/125207/3870933/3870936/aaaa1234bbbb5678cccc9012dddd3456/index.html"
        with patch("scripts.backfill_china_communiques.time.sleep"):
            row = _pboc_fetch_article(session, href, listing_publish_date=None)
        assert row is not None
        assert row["publish_date"] is None
        assert row["meeting_date"] is None


# ---------------------------------------------------------------------------
# 16. Fixture transcript items — CCTV readouts and reference items
# ---------------------------------------------------------------------------
# Realistic news_cctv-shaped items (title/content dicts). Measured live
# 2026-07-06: mention-level filters collected 57 politburo_econ / 130 cewc
# items spanning 1954→2030. These fixtures reproduce the failure modes.

# The real April-2024 politburo econ readout shape, salted with the spurious
# year mentions that broke the old text-derived meeting_year (1954年 historical
# reference, 2030年 forward target).
_POLITBURO_READOUT_ITEM = {
    "title": "中共中央政治局召开会议 分析研究当前经济形势和经济工作 中共中央总书记习近平主持会议",
    "content": (
        "央视网消息（新闻联播）：中共中央政治局4月30日召开会议，分析研究当前经济形势和经济工作。"
        "会议指出，自1954年10月16日第一届会议以来的制度传统必须坚持。"
        "会议强调，锚定2030年远景目标，扎实做好全年经济工作。"
    ),
}

# Reference items: they MENTION the meeting but are not the readout.
_POLITBURO_REFERENCE_ITEMS = [
    {
        "title": "央视快评：贯彻落实中央政治局会议精神",
        "content": "中共中央政治局会议对当前经济形势作出重要判断，各地各部门要抓好经济工作落实。",
    },
    {
        "title": "李强主持召开国务院常务会议",
        "content": "会议传达学习中共中央政治局会议关于经济工作的部署，研究当前经济形势。",
    },
]

# Politburo STANDING COMMITTEE readout — a different meeting type that the
# full-Politburo filter must reject.
_PSC_READOUT_ITEM = {
    "title": "中共中央政治局常务委员会召开会议 研究部署经济工作",
    "content": "中共中央政治局常务委员会5月14日召开会议，研究当前经济形势，部署经济工作。",
}

_CEWC_READOUT_ITEM = {
    "title": "中央经济工作会议在北京举行 习近平发表重要讲话",
    "content": (
        "央视网消息（新闻联播）：中央经济工作会议12月11日至12日在北京举行。"
        "习近平出席会议并发表重要讲话，总结2024年经济工作，部署2025年经济工作。"
    ),
}

_CEWC_REFERENCE_ITEMS = [
    {
        "title": "专家解读中央经济工作会议精神",
        "content": "近日召开的中央经济工作会议提出，明年要坚持稳中求进工作总基调。",
    },
    {
        "title": "各地干部群众认真学习中央经济工作会议精神",
        "content": "中央经济工作会议在各地引发热烈反响，干部群众表示要抓好落实。",
    },
]


def _mock_cctv_day(match_ds: dict[str, list[dict]]):
    """Build (listing_fn, fetch_fn) side-effect pair keyed by date string.

    Days present in match_ds return their items' titles at Phase 1 and the full
    items at Phase 2; all other probed days return a non-matching listing (so
    the empty-listing full-fetch fallback is NOT triggered).
    """
    def listing_fn(session, ds):
        items = match_ds.get(ds)
        if items:
            return [(it["title"], f"http://tv.cctv.com/{ds}") for it in items]
        return [("天气预报", f"http://tv.cctv.com/{ds}/weather")]

    def fetch_fn(ds):
        return list(match_ds.get(ds, []))

    return listing_fn, fetch_fn


# ---------------------------------------------------------------------------
# 17. Fix (a): spurious-year rejection — broadcast date anchors meeting_year
# ---------------------------------------------------------------------------

class TestSpuriousYearRejection:
    """meeting_year must come from the broadcast date, never from transcript text."""

    def test_broadcast_year_within_bounds(self) -> None:
        assert broadcast_meeting_year(date(2024, 4, 30)) == 2024
        assert broadcast_meeting_year(date(2016, 12, 16)) == 2016

    def test_broadcast_year_outside_bounds_rejected(self) -> None:
        assert broadcast_meeting_year(date(2015, 12, 20)) is None
        assert broadcast_meeting_year(date(1954, 10, 16)) is None
        assert broadcast_meeting_year(date(2030, 1, 1)) is None

    def test_bounds_match_cctv_coverage(self) -> None:
        assert CCTV_YEAR_MIN == 2016  # akshare news_cctv coverage starts 2016-02-03
        assert CCTV_YEAR_MAX >= 2026

    def test_historical_year_in_text_rejected(self) -> None:
        """1954年10月16日 in the body must NOT become the meeting date."""
        text = "会议指出，自1954年10月16日第一届会议以来的传统必须坚持。"
        assert plausible_meeting_date(text, date(2024, 4, 30)) == "2024-04-30"

    def test_forward_target_year_in_text_rejected(self) -> None:
        """2030年 forward-target dates must NOT become the meeting date."""
        text = "锚定2030年1月1日实现远景目标。"
        assert plausible_meeting_date(text, date(2024, 4, 30)) == "2024-04-30"

    def test_plausible_extracted_date_accepted(self) -> None:
        """A full-form date within the broadcast window IS accepted."""
        text = "中央经济工作会议于2024年12月11日在北京开幕。"
        assert plausible_meeting_date(text, date(2024, 12, 12)) == "2024-12-11"

    def test_no_date_in_text_falls_back_to_broadcast(self) -> None:
        """Typical readout body dates the meeting without a year (4月30日) —
        no full-form match → broadcast date."""
        text = "中共中央政治局4月30日召开会议，分析研究当前经济形势和经济工作。"
        assert plausible_meeting_date(text, date(2024, 4, 30)) == "2024-04-30"

    def test_scan_derives_year_from_broadcast_not_text(self) -> None:
        """Integration: a readout whose body mentions 1954年 and 2030年 must land
        with meeting_year == broadcast year and meeting_date == broadcast date."""
        listing_fn, fetch_fn = _mock_cctv_day({"20240430": [_POLITBURO_READOUT_ITEM]})
        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   side_effect=listing_fn), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   side_effect=fetch_fn), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            rows = fetch_politburo_econ(MagicMock(), set(), limit=None, dry_run=False)

        assert len(rows) == 1
        row = rows[0]
        assert row["meeting_year"] == 2024, (
            f"meeting_year={row['meeting_year']} — text years (1954/2030) leaked in"
        )
        assert row["meeting_date"] == "2024-04-30"
        assert row["publish_date"] == "2024-04-30"


# ---------------------------------------------------------------------------
# 18. Fix (b): reference-vs-readout discrimination
# ---------------------------------------------------------------------------

class TestReadoutVsReference:
    """Items that merely MENTION the meeting must be rejected; readouts kept."""

    def test_politburo_readout_accepted(self) -> None:
        assert _is_politburo_econ(
            _POLITBURO_READOUT_ITEM["title"], _POLITBURO_READOUT_ITEM["content"]
        )

    def test_politburo_december_readout_accepted(self) -> None:
        assert _is_politburo_econ(
            "中共中央政治局召开会议 分析研究2025年经济工作 中共中央总书记习近平主持会议",
            "中共中央政治局12月9日召开会议，分析研究2025年经济工作。",
        )

    @pytest.mark.parametrize("item", _POLITBURO_REFERENCE_ITEMS)
    def test_politburo_reference_rejected(self, item: dict) -> None:
        assert not _is_politburo_econ(item["title"], item["content"])

    def test_politburo_standing_committee_rejected(self) -> None:
        """PSC readouts (常务委员会) are a different meeting type — must not match."""
        assert not _is_politburo_econ(
            _PSC_READOUT_ITEM["title"], _PSC_READOUT_ITEM["content"]
        )

    def test_cewc_readout_accepted(self) -> None:
        assert _is_cewc(_CEWC_READOUT_ITEM["title"], _CEWC_READOUT_ITEM["content"])

    @pytest.mark.parametrize("item", _CEWC_REFERENCE_ITEMS)
    def test_cewc_reference_rejected(self, item: dict) -> None:
        assert not _is_cewc(item["title"], item["content"])

    def test_scan_keeps_readout_drops_references_same_day(self) -> None:
        """Integration: readout + reference items airing the same day → only the
        readout is collected."""
        day_items = [_CEWC_READOUT_ITEM] + _CEWC_REFERENCE_ITEMS
        listing_fn, fetch_fn = _mock_cctv_day({"20241212": day_items})
        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   side_effect=listing_fn), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   side_effect=fetch_fn), \
             patch.dict("scripts.backfill_china_communiques.CEWC_GOVCN_FALLBACKS", {}, clear=True), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            rows = fetch_cewc(MagicMock(), set(), limit=None, dry_run=False)

        real = [r for r in rows if r["source"] != "explicit_gap"]
        assert len(real) == 1
        assert real[0]["title"] == _CEWC_READOUT_ITEM["title"]
        assert real[0]["meeting_year"] == 2024


# ---------------------------------------------------------------------------
# 19. Fix (c): per-meeting dedup — one readout per meeting
# ---------------------------------------------------------------------------

class TestPerMeetingDedup:
    """A meeting airing across items/days must collapse to ONE row:
    earliest broadcast date; longest body among that date's items."""

    def test_meeting_keys(self) -> None:
        row = {"meeting_year": 2024, "publish_date": "2024-04-30"}
        assert _politburo_meeting_key(row) == (2024, 4)
        assert _cewc_meeting_key(row) == 2024

    def test_cewc_multi_day_multi_item_collapses_to_one(self) -> None:
        short_item = {
            "title": "中央经济工作会议在北京举行",
            "content": "中央经济工作会议12月11日至12日在北京举行。",
        }
        long_item = _CEWC_READOUT_ITEM  # same meeting, fuller body, same day
        rerun_item = {
            "title": "中央经济工作会议在北京举行",
            "content": "中央经济工作会议12月11日至12日在北京举行。会议全文重播。",
        }
        listing_fn, fetch_fn = _mock_cctv_day({
            "20241212": [short_item, long_item],
            "20241213": [rerun_item],  # next-day re-air — later date must lose
        })
        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   side_effect=listing_fn), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   side_effect=fetch_fn), \
             patch.dict("scripts.backfill_china_communiques.CEWC_GOVCN_FALLBACKS", {}, clear=True), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            rows = fetch_cewc(MagicMock(), set(), limit=None, dry_run=False)

        real = [r for r in rows if r["source"] != "explicit_gap"]
        assert len(real) == 1, f"expected 1 readout for the 2024 CEWC, got {len(real)}"
        kept = real[0]
        assert kept["publish_date"] == "2024-12-12", "earliest broadcast date must win"
        assert kept["title"] == long_item["title"], "longest body on that date must win"

    def test_politburo_distinct_meetings_not_merged(self) -> None:
        """April and July meetings of the same year are different meetings —
        both survive dedup; a same-window re-air is dropped."""
        april_item = _POLITBURO_READOUT_ITEM
        july_item = {
            "title": "中共中央政治局召开会议 分析研究当前经济形势和经济工作",
            "content": "中共中央政治局7月30日召开会议，分析研究当前经济形势和经济工作。",
        }
        listing_fn, fetch_fn = _mock_cctv_day({
            "20240429": [april_item],
            "20240430": [april_item],  # re-air within the April window
            "20240730": [july_item],
        })
        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   side_effect=listing_fn), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   side_effect=fetch_fn), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            rows = fetch_politburo_econ(MagicMock(), set(), limit=None, dry_run=False)

        assert len(rows) == 2, f"expected April + July meetings, got {len(rows)}"
        by_month = {int(r["publish_date"][5:7]): r for r in rows}
        assert set(by_month) == {4, 7}
        assert by_month[4]["publish_date"] == "2024-04-29", (
            "earliest broadcast date within the April window must win"
        )


# ---------------------------------------------------------------------------
# 20. Local CCTV archive mode
# ---------------------------------------------------------------------------

_ARCHIVE_COLS = ["date", "order_idx", "title", "content", "fetch_status", "fetched_at"]


def _archive_row(day: str, title: str, content: str, status: str = "ok") -> dict:
    return {"date": day, "order_idx": 0, "title": title, "content": content,
            "fetch_status": status, "fetched_at": "2026-07-06T00:00:00Z"}


class TestArchiveMode:
    """Days covered by the local archive are read locally; everything the
    archive cannot answer falls back to the network path."""

    def _write_month(self, dirpath: Path, month: str, rows: list[dict]) -> None:
        pd.DataFrame(rows, columns=_ARCHIVE_COLS).to_parquet(dirpath / f"{month}.parquet")

    def _scan_cewc(self, days, archive_dir, listing_mock, fetch_mock):
        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   listing_mock), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   fetch_mock), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            return _cctv_scan_dates(
                MagicMock(), set(), iter(days), _is_cewc, "cewc",
                limit=None, dry_run=False,
                listing_prefetch_fn=_listing_may_be_cewc,
                meeting_key_fn=_cewc_meeting_key,
                archive_dir=archive_dir,
            )

    def test_archive_day_short_circuits_network(self, tmp_path: Path) -> None:
        """A covered day must produce the readout with ZERO network calls."""
        self._write_month(tmp_path, "2024-12", [
            _archive_row("2024-12-12", _CEWC_READOUT_ITEM["title"],
                         _CEWC_READOUT_ITEM["content"]),
            _archive_row("2024-12-12", "国际联播快讯", "国际新闻若干。"),
        ])
        listing = MagicMock(side_effect=AssertionError("network listing must not be called"))
        fetch = MagicMock(side_effect=AssertionError("network day-fetch must not be called"))
        rows = self._scan_cewc([date(2024, 12, 12)], tmp_path, listing, fetch)
        assert len(rows) == 1
        assert rows[0]["meeting_year"] == 2024
        assert rows[0]["title"] == _CEWC_READOUT_ITEM["title"]

    def test_missing_month_falls_back_to_network(self, tmp_path: Path) -> None:
        """No month parquet → the day is fetched over the network."""
        listing = MagicMock(return_value=[(_CEWC_READOUT_ITEM["title"], "http://u")])
        fetch = MagicMock(return_value=[_CEWC_READOUT_ITEM])
        rows = self._scan_cewc([date(2024, 12, 12)], tmp_path, listing, fetch)
        assert len(rows) == 1
        assert listing.called and fetch.called

    def test_day_absent_in_month_falls_back(self, tmp_path: Path) -> None:
        """Month file exists but the probed day has no rows → network fallback."""
        self._write_month(tmp_path, "2024-12", [
            _archive_row("2024-12-11", "国内联播快讯", "无关内容。"),
        ])
        listing = MagicMock(return_value=[(_CEWC_READOUT_ITEM["title"], "http://u")])
        fetch = MagicMock(return_value=[_CEWC_READOUT_ITEM])
        rows = self._scan_cewc([date(2024, 12, 12)], tmp_path, listing, fetch)
        assert len(rows) == 1
        assert fetch.called

    def test_stubbed_day_without_match_falls_back(self, tmp_path: Path) -> None:
        """Stub rows lose their titles (CCTV error text) — a stubbed day whose
        intact rows have no match may be hiding the readout → network.
        This is the measured 2019/2022/2024 CEWC failure mode."""
        self._write_month(tmp_path, "2024-12", [
            _archive_row("2024-12-12", "对不起，可能是网络原因或无此页面，请稍后尝试。",
                         "", status="stub"),
            _archive_row("2024-12-12", "国内联播快讯", "无关内容。"),
        ])
        listing = MagicMock(return_value=[(_CEWC_READOUT_ITEM["title"], "http://u")])
        fetch = MagicMock(return_value=[_CEWC_READOUT_ITEM])
        rows = self._scan_cewc([date(2024, 12, 12)], tmp_path, listing, fetch)
        assert len(rows) == 1
        assert fetch.called, "stubbed day without an intact match must force network fallback"

    def test_stub_does_not_block_archive_when_readout_intact(self, tmp_path: Path) -> None:
        """When an intact row IS the readout, stubs on the same day are irrelevant."""
        self._write_month(tmp_path, "2024-12", [
            _archive_row("2024-12-12", _CEWC_READOUT_ITEM["title"],
                         _CEWC_READOUT_ITEM["content"]),
            _archive_row("2024-12-12", "对不起，可能是网络原因或无此页面，请稍后尝试。",
                         "", status="stub"),
        ])
        listing = MagicMock(side_effect=AssertionError("network listing must not be called"))
        fetch = MagicMock(side_effect=AssertionError("network day-fetch must not be called"))
        rows = self._scan_cewc([date(2024, 12, 12)], tmp_path, listing, fetch)
        assert len(rows) == 1

    def test_fully_intact_day_proves_absence(self, tmp_path: Path) -> None:
        """Zero stubs + no match → the archive answers 'no readout' and the
        network is not consulted."""
        self._write_month(tmp_path, "2024-12", [
            _archive_row("2024-12-14", "国内联播快讯", "无关内容。"),
            _archive_row("2024-12-14", "国际联播快讯", "国际新闻。"),
        ])
        listing = MagicMock(side_effect=AssertionError("network listing must not be called"))
        fetch = MagicMock(side_effect=AssertionError("network day-fetch must not be called"))
        rows = self._scan_cewc([date(2024, 12, 14)], tmp_path, listing, fetch)
        assert rows == []

    def test_archive_day_items_unit(self, tmp_path: Path) -> None:
        self._write_month(tmp_path, "2021-04", [
            _archive_row("2021-04-30", "标题A", "内容A"),
            _archive_row("2021-04-30", "标题B", "", status="stub"),
        ])
        # Stubbed day, no strict match among intact rows → None (network)
        assert _archive_day_items(tmp_path, date(2021, 4, 30), lambda t, c: False) is None
        # Stubbed day but intact row matches → intact rows returned
        items = _archive_day_items(tmp_path, date(2021, 4, 30), lambda t, c: t == "标题A")
        assert items == [{"title": "标题A", "content": "内容A"}]
        # Uncovered month → None
        assert _archive_day_items(tmp_path, date(2020, 4, 30), lambda t, c: False) is None


# ---------------------------------------------------------------------------
# 20a2. listing_title provable-absence on stubbed days (PR #1913)
# ---------------------------------------------------------------------------

_ARCHIVE_COLS_LT = ["date", "order_idx", "title", "content", "fetch_status",
                    "fetched_at", "listing_title"]


def _archive_row_lt(day: str, title: str, content: str, status: str = "ok",
                    listing_title: str = "") -> dict:
    """Archive row WITH the listing_title column (post-PR #1913 shard shape)."""
    return {"date": day, "order_idx": 0, "title": title, "content": content,
            "fetch_status": status, "fetched_at": "2026-07-06T00:00:00Z",
            "listing_title": listing_title}


class TestArchiveListingTitleProvableAbsence:
    """PR #1913 records the real listing titles on stub/error rows. A stubbed day
    whose listing titles ALL fail the permissive prescreen proves absence and is
    answered locally; a listing title that passes still forces the network fetch
    (the body is needed); an empty/absent listing_title keeps the conservative
    network fallback. Strictly opt-in per row.
    """

    def _write_month(self, dirpath: Path, month: str, rows: list[dict]) -> None:
        pd.DataFrame(rows, columns=_ARCHIVE_COLS_LT).to_parquet(dirpath / f"{month}.parquet")

    _STUB_TITLE = "对不起，可能是网络原因或无此页面，请稍后尝试。"

    def test_stub_nonmatching_listing_titles_returns_intact_rows(self, tmp_path: Path) -> None:
        """Stub row carries the full listing; no title is a CEWC readout →
        absence provable → intact (ok) rows returned instead of None."""
        listing = "\n".join(["国内联播快讯", "天气预报", "国际时讯"])
        self._write_month(tmp_path, "2024-12", [
            _archive_row_lt("2024-12-12", "国内联播快讯", "无关内容。"),
            _archive_row_lt("2024-12-12", self._STUB_TITLE, "", status="stub",
                            listing_title=listing),
        ])
        items = _archive_day_items(tmp_path, date(2024, 12, 12), _is_cewc,
                                   prefetch_fn=_listing_may_be_cewc)
        assert items == [{"title": "国内联播快讯", "content": "无关内容。"}]

    def test_stub_matching_listing_title_returns_none(self, tmp_path: Path) -> None:
        """A stub row's listing title IS a CEWC readout headline → the body is
        needed → None (network fallback)."""
        listing = "\n".join(["国内联播快讯", "中央经济工作会议在北京举行 习近平出席"])
        self._write_month(tmp_path, "2024-12", [
            _archive_row_lt("2024-12-12", "国内联播快讯", "无关内容。"),
            _archive_row_lt("2024-12-12", self._STUB_TITLE, "", status="stub",
                            listing_title=listing),
        ])
        items = _archive_day_items(tmp_path, date(2024, 12, 12), _is_cewc,
                                   prefetch_fn=_listing_may_be_cewc)
        assert items is None

    def test_stub_empty_listing_title_returns_none(self, tmp_path: Path) -> None:
        """A stub row with an empty listing_title (listing fetch failed) keeps the
        conservative network fallback — the readout might be hidden in the stub."""
        self._write_month(tmp_path, "2024-12", [
            _archive_row_lt("2024-12-12", "国内联播快讯", "无关内容。"),
            _archive_row_lt("2024-12-12", self._STUB_TITLE, "", status="stub",
                            listing_title=""),
        ])
        items = _archive_day_items(tmp_path, date(2024, 12, 12), _is_cewc,
                                   prefetch_fn=_listing_may_be_cewc)
        assert items is None

    def test_partial_empty_listing_title_returns_none(self, tmp_path: Path) -> None:
        """Opt-in is PER ROW: one stub with a title + one stub with an empty
        listing_title → conservative None (cannot prove absence for the empty one)."""
        self._write_month(tmp_path, "2024-12", [
            _archive_row_lt("2024-12-12", "国内联播快讯", "无关内容。"),
            _archive_row_lt("2024-12-12", self._STUB_TITLE, "", status="stub",
                            listing_title="国内联播快讯"),
            _archive_row_lt("2024-12-12", self._STUB_TITLE, "", status="error",
                            listing_title=""),
        ])
        items = _archive_day_items(tmp_path, date(2024, 12, 12), _is_cewc,
                                   prefetch_fn=_listing_may_be_cewc)
        assert items is None

    def test_aligned_per_row_listing_title_matches(self, tmp_path: Path) -> None:
        """Aligned case (row count == listing count): each stub row's single
        listing_title is tested; a matching one forces the network."""
        self._write_month(tmp_path, "2024-12", [
            _archive_row_lt("2024-12-12", self._STUB_TITLE, "", status="stub",
                            listing_title="中央经济工作会议在北京举行 习近平出席"),
            _archive_row_lt("2024-12-12", "国内联播快讯", "无关内容。"),
        ])
        items = _archive_day_items(tmp_path, date(2024, 12, 12), _is_cewc,
                                   prefetch_fn=_listing_may_be_cewc)
        assert items is None

    def test_whole_day_stub_absence_answered_locally(self, tmp_path: Path) -> None:
        """A whole-day stub (zero intact rows) whose full joined listing has no
        readout title proves absence → answered locally (empty list), no network."""
        listing = "\n".join(["国内联播快讯", "天气预报", "国际时讯"])
        self._write_month(tmp_path, "2024-12", [
            _archive_row_lt("2024-12-14", self._STUB_TITLE, "", status="stub",
                            listing_title=listing),
        ])
        items = _archive_day_items(tmp_path, date(2024, 12, 14), _is_cewc,
                                   prefetch_fn=_listing_may_be_cewc)
        assert items == []

    def test_default_prefetch_used_when_none(self, tmp_path: Path) -> None:
        """With no prefetch_fn, the prescreen defaults to filter_fn(title, "").
        A short-form politburo listing title (econ keyword only in the body) is
        passed by the permissive prescreen but NOT by filter_fn(title, "") —
        proving the two differ and that _archive_day_items uses the permissive
        one when supplied."""
        short_title = "中共中央政治局召开会议 习近平主持"
        self._write_month(tmp_path, "2024-04", [
            _archive_row_lt("2024-04-30", self._STUB_TITLE, "", status="stub",
                            listing_title=short_title),
            _archive_row_lt("2024-04-30", "国内联播快讯", "无关内容。"),
        ])
        # Permissive prescreen passes the short title → network fetch (None).
        with_prefetch = _archive_day_items(
            tmp_path, date(2024, 4, 30), _is_politburo_econ,
            prefetch_fn=_listing_may_be_politburo_econ)
        assert with_prefetch is None
        # Strict default filter_fn(title, "") fails the short title → the day
        # would be (wrongly) proven absent; this documents WHY the prefetch is
        # threaded through rather than defaulted.
        default_only = _archive_day_items(
            tmp_path, date(2024, 4, 30), _is_politburo_econ)
        assert default_only == [{"title": "国内联播快讯", "content": "无关内容。"}]


# ---------------------------------------------------------------------------
# 20b. Listing honesty + resumability
# ---------------------------------------------------------------------------

class TestListingHonesty:
    """A soft-error/skeleton listing page (nav links only) must be treated as a
    FAILED listing (→ full-fetch fallback), never as 'no match, skip'."""

    def _make_session(self, html: str) -> MagicMock:
        resp = MagicMock()
        resp.text = html
        resp.raise_for_status = MagicMock()
        session = MagicMock()
        session.get.return_value = resp
        return session

    def test_nav_only_page_returns_empty(self) -> None:
        """Skeleton page: <li><a> nav items without VIDE article hrefs → []."""
        html = """<html><body><ul>
          <li><a href="https://tv.cctv.com/lm/xwlb/">新闻联播</a></li>
          <li><a href="https://www.cctv.com/">央视网</a></li>
        </ul></body></html>"""
        with patch("scripts.backfill_china_communiques.time.sleep"):
            out = _cctv_listing_titles(self._make_session(html), "20180731")
        assert out == [], "nav-only skeleton must be treated as listing failure"

    def test_real_day_page_returns_items(self) -> None:
        html = """<html><body><ul>
          <li><a href="http://tv.cctv.com/2018/07/31/VIDE0EZ4G3dK8xYa.shtml">
            [视频]中共中央政治局召开会议 分析研究当前经济形势和经济工作</a></li>
          <li><a href="http://tv.cctv.com/2018/07/31/VIDEKz9lkEMhvdGN.shtml">[视频]联播快讯</a></li>
          <li><a href="https://tv.cctv.com/lm/xwlb/">新闻联播</a></li>
        </ul></body></html>"""
        with patch("scripts.backfill_china_communiques.time.sleep"):
            out = _cctv_listing_titles(self._make_session(html), "20180731")
        assert len(out) == 2  # nav link dropped, article links kept
        assert any("政治局" in t for t, _ in out)


class TestRerunResumability:
    """A re-run must not re-add an already-collected meeting through a
    DIFFERENT item of the same broadcast (its doc_id is not in known_ids)."""

    def test_known_meeting_day_skipped_entirely(self) -> None:
        listing = MagicMock(side_effect=AssertionError("day must be skipped before listing"))
        fetch = MagicMock(side_effect=AssertionError("day must be skipped before fetch"))
        with patch("scripts.backfill_china_communiques._cctv_listing_titles", listing), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day", fetch), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            rows = _cctv_scan_dates(
                MagicMock(), set(), iter([date(2024, 12, 12)]), _is_cewc, "cewc",
                limit=None, dry_run=False,
                listing_prefetch_fn=_listing_may_be_cewc,
                meeting_key_fn=_cewc_meeting_key,
                known_meeting_keys={2024},
            )
        assert rows == []

    def test_other_item_of_known_meeting_not_readded(self) -> None:
        """Politburo: parquet holds the Apr-29 item; re-scanning Apr-30 (re-air,
        different doc_id) must yield nothing for the (2024, 4) meeting."""
        listing_fn, fetch_fn = _mock_cctv_day({"20240430": [_POLITBURO_READOUT_ITEM]})
        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   side_effect=listing_fn), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   side_effect=fetch_fn), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            rows = fetch_politburo_econ(MagicMock(), set(), limit=None, dry_run=False,
                                        known_meeting_keys={(2024, 4)})
        assert rows == []

    def test_unknown_meeting_still_collected(self) -> None:
        listing_fn, fetch_fn = _mock_cctv_day({"20240430": [_POLITBURO_READOUT_ITEM]})
        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   side_effect=listing_fn), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   side_effect=fetch_fn), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            rows = fetch_politburo_econ(MagicMock(), set(), limit=None, dry_run=False,
                                        known_meeting_keys={(2023, 4), (2024, 7)})
        assert len(rows) == 1
        assert rows[0]["publish_date"] == "2024-04-30"


class TestPolitburoWindows:
    def test_windows_are_month_contained(self) -> None:
        """_politburo_meeting_key identifies meetings by (year, month) — every
        probe window must therefore stay within a single month."""
        from scripts.backfill_china_communiques import _POLITBURO_WINDOWS
        for mo_start, _, mo_end, _ in _POLITBURO_WINDOWS:
            assert mo_start == mo_end


# ---------------------------------------------------------------------------
# 20c. Curated gov.cn fallbacks for CCTV-dead CEWC years
# ---------------------------------------------------------------------------

_GOVCN_PAGE_HTML = """<html><head>
<title>中央经济工作会议在北京举行 习近平李克强作重要讲话_滚动新闻_中国政府网</title>
</head><body><div class="pages_content">
<p>中央经济工作会议12月19日至21日在北京举行。习近平、李克强作重要讲话。</p>
<p>会议总结今年经济工作，分析当前经济形势，部署明年经济工作。""" + ("会议指出，要坚持稳中求进工作总基调。" * 30) + """</p>
</div></body></html>"""


def _govcn_session() -> MagicMock:
    resp = MagicMock()
    resp.content = _GOVCN_PAGE_HTML.encode("utf-8")
    resp.headers = {"content-type": "text/html; charset=utf-8"}
    resp.raise_for_status = MagicMock()
    session = MagicMock()
    session.get.return_value = resp
    return session


class TestGovcnFallback:
    def test_fetch_govcn_readout_builds_row(self) -> None:
        from scripts.backfill_china_communiques import _fetch_govcn_readout
        with patch("scripts.backfill_china_communiques.time.sleep"):
            row = _fetch_govcn_readout(
                _govcn_session(), 2018,
                "https://www.gov.cn/xinwen/2018-12/21/content_5350934.htm")
        assert row is not None
        assert row["family"] == "cewc"
        assert row["source"] == "gov.cn"
        assert row["meeting_year"] == 2018
        assert row["publish_date"] == "2018-12-21"
        assert row["title"].startswith("中央经济工作会议在北京举行")
        assert "中国政府网" not in row["title"]  # site suffix stripped
        assert len(row["body"]) > 500

    def test_fetch_govcn_readout_rejects_non_readout_page(self) -> None:
        """A page that fails the strict readout gate returns None (curation
        names the URL, it does not bypass the filter)."""
        from scripts.backfill_china_communiques import _fetch_govcn_readout
        resp = MagicMock()
        resp.content = "<html><title>页面不存在</title><body><p>404</p></body></html>".encode("utf-8")
        resp.headers = {"content-type": "text/html; charset=utf-8"}
        resp.raise_for_status = MagicMock()
        session = MagicMock()
        session.get.return_value = resp
        with patch("scripts.backfill_china_communiques.time.sleep"):
            row = _fetch_govcn_readout(
                session, 2018, "https://www.gov.cn/xinwen/2018-12/21/content_x.htm")
        assert row is None

    def test_fallback_fills_missing_years_only(self) -> None:
        """fetch_cewc: years already collected (via scan or parquet) are not
        re-fetched from gov.cn; missing curated years are filled; the 2017
        explicit gap marker row coexists with the 2017 gov.cn row."""
        with patch("scripts.backfill_china_communiques._cctv_listing_titles",
                   return_value=[("天气预报", "http://tv.cctv.com/VIDE1.shtml")]), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day",
                   return_value=[]), \
             patch("scripts.backfill_china_communiques.time.sleep"):
            rows = fetch_cewc(_govcn_session(), set(), limit=None, dry_run=False,
                              known_meeting_keys={2016, 2018, 2020, 2021, 2023, 2024, 2025})

        govcn = [r for r in rows if r["source"] == "gov.cn"]
        gaps = [r for r in rows if r["source"] == "explicit_gap"]
        # 2018 known → skipped; 2017/2019/2022 filled from gov.cn
        assert {r["meeting_year"] for r in govcn} == {2017, 2019, 2022}
        # The 2017 CCTV gap marker is emitted alongside the 2017 gov.cn row —
        # the mirror fill must never suppress the gap documentation
        assert len(gaps) == 1 and gaps[0]["meeting_year"] == 2017


# ---------------------------------------------------------------------------
# 21. _call_with_timeout — hard ceiling on hung fetches
# ---------------------------------------------------------------------------

class TestCallWithTimeout:
    def test_returns_value(self) -> None:
        assert _call_with_timeout(lambda x: x + 1, 5.0, 41) == 42

    def test_times_out_on_hang(self) -> None:
        import time as _time
        with pytest.raises(TimeoutError):
            _call_with_timeout(_time.sleep, 0.05, 2)

    def test_propagates_exception(self) -> None:
        def boom() -> None:
            raise ValueError("inner failure")
        with pytest.raises(ValueError, match="inner failure"):
            _call_with_timeout(boom, 5.0)


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
