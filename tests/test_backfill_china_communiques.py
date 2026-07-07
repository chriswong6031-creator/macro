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

Run: .venv/bin/python -m pytest tests/test_backfill_china_communiques.py -v
  or: .venv/bin/python -m tests.test_backfill_china_communiques
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

# Make repo root importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.backfill_china_communiques import (  # noqa: E402
    PBOC_BASE,
    PBOC_INDEX_URL,
    _PBOC_HREF_RE,
    _cctv_fetch_day,
    _cctv_listing_titles,
    _decode_html,
    _is_cewc,
    _is_politburo_econ,
    _listing_may_be_politburo_econ,
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
        assert _is_politburo_econ(
            "政治局召开会议部署明年经济工作",
            "会议强调，要做好明年经济工作。"
        )

    def test_fails_without_zhengzhiju(self) -> None:
        # No 政治局 → should fail
        assert not _is_politburo_econ(
            "国务院常务会议召开",
            "研究当前经济形势"
        )

    def test_fails_without_economic_keyword(self) -> None:
        # Has 政治局 but not economic keyword
        assert not _is_politburo_econ(
            "政治局召开会议",
            "研究外交和安全形势"
        )

    def test_passes_keyword_in_content_not_title(self) -> None:
        assert _is_politburo_econ(
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

    def test_passes_with_keyword_in_content(self) -> None:
        assert _is_cewc(
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
        # Mock listing + fetch + time.sleep so test doesn't sleep through 10 years
        with patch("scripts.backfill_china_communiques._cctv_listing_titles", return_value=[]), \
             patch("scripts.backfill_china_communiques._cctv_fetch_day", return_value=[]), \
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


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
