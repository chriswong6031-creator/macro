"""Tests for collectors/china_omo.py — the PBOC open-market bulletin tape (W3 CNH).

Pure/offline surface only — NO network. Every parser is pinned against the REAL
pages captured from www.pbc.gov.cn on 2026-07-27 and committed under
tests/fixtures/china_omo/, so a CMS drift breaks a test instead of silently
emptying the store.

Covers:
  - column/landing list extraction across BOTH href quote styles, with the
    column-index links (which carry no document id) excluded
  - all four detail formats parsed to their exact printed numbers
  - the full-width ［2026］第5号 bulletin-number variant
  - multi-tenor result tables and the no-table narrative fallback
  - date-range EXPANSION on pre-announcements (one row per operation day) and the
    NaN rate that 量价分离 tenders legitimately carry
  - events.jsonl rows are kind="omo_observed" / provenance="pboc_bulletin" —
    NEVER "omo_mlf", which is the synthetic FR007-z namespace — and the append is
    hash-deduped, so a re-run adds nothing
  - the 20-detail cap and the wall-clock guard both surface as n_deferred
  - corrupt-store abort, atomic write, first_seen preserved through a correction

Storage is redirected to tmp_path (monkeypatched lib.config.data_dir) and the event
ledger to a monkeypatched lib.config.ROOT, so no tracked file is ever dirtied.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_omo as co  # noqa: E402
from lib import config  # noqa: E402

_FIX = Path(__file__).resolve().parent / "fixtures" / "china_omo"
_TS = "2026-07-27T12:00:00+00:00"

_TRADE_COL_URL = co.COLUMNS[0]["url"]
_ANN_COL_URL = co.COLUMNS[1]["url"]
_OUTRIGHT_COL_URL = co.COLUMNS[2]["url"]
_MLF_COL_URL = co.COLUMNS[3]["url"]
_LANDING_URL = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/index.html"


def _fx(name: str) -> str:
    return _FIX.joinpath(name).read_bytes().decode("utf-8")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Redirect the operations store AND the events ledger into tmp_path."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    return tmp_path


def _events(root: Path) -> list[dict]:
    p = root / "data" / "china_policy_transmission" / "events.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# --------------------------------------------------------------------------- #
# list pages — both quote styles, no column-index links
# --------------------------------------------------------------------------- #

class TestExtractEntries:
    def test_trade_column_yields_every_bulletin(self):
        entries = co.extract_entries(_fx("trade_col.html"), _TRADE_COL_URL)
        assert len(entries) == 20
        first = entries[0]
        assert first["title"] == "公开市场业务交易公告 [2026]第143号"
        assert first["list_date"] == "2026-07-27"
        assert first["url"].endswith("/125475/2026072709025211011/index.html")
        assert first["url"].startswith("https://www.pbc.gov.cn/")   # relative href resolved

    def test_every_entry_carries_a_list_date(self):
        entries = co.extract_entries(_fx("trade_col.html"), _TRADE_COL_URL)
        assert all(len(e["list_date"]) == 10 for e in entries)
        # newest first, as the CMS prints them
        assert [e["list_date"] for e in entries] == sorted(
            (e["list_date"] for e in entries), reverse=True)

    def test_column_index_links_are_not_entries(self):
        # …/125475/index.html has no document id; treating it as a bulletin would put
        # the column page itself into the store on the very first night.
        entries = co.extract_entries(_fx("trade_col.html"), _TRADE_COL_URL)
        assert not any(e["url"].endswith("/125475/index.html") for e in entries)
        assert all("/index.html" in e["url"] for e in entries)

    def test_landing_page_spans_five_columns(self):
        entries = co.extract_entries(_fx("landing_list.html"), _LANDING_URL)
        assert len(entries) == 20
        cols = {e["url"].rsplit("/", 3)[1] for e in entries}
        # The landing page carries THREE of the four polled columns (交易公告 125475,
        # 业务公告 125469, 买断式逆回购 5492845) plus two we do not poll (央票 125472,
        # 国库现金 125481). MLF lives under a different path (125437/125446/125873) and
        # is NOT reachable from this page — which is why the collector polls the four
        # column pages directly instead of crawling the landing.
        assert {"125475", "125469", "5492845"} <= cols
        assert {"125472", "125481"} <= cols

    def test_single_quoted_sidebar_links_are_read_but_not_mistaken_for_entries(self):
        # The landing page's sidebar column links use SINGLE-quoted hrefs. The regex
        # must consume them (otherwise a greedy match spans into the next tag) yet
        # none of them is an entry, because none carries a document id.
        html = _fx("landing_list.html")
        assert "href='/zhengcehuobisi/125207/125213/125431/125475/index.html'" in html
        entries = co.extract_entries(html, _LANDING_URL)
        assert not any(e["url"].endswith("125431/125475/index.html") for e in entries)

    def test_single_quoted_entry_href_is_parsed(self):
        html = ("<a href='/zhengcehuobisi/125207/125213/125431/125475/"
                "2026072709025211011/index.html'>公开市场业务交易公告 [2026]第143号</a>"
                "<span class=\"hui12\">2026-07-27</span>")
        entries = co.extract_entries(html, _TRADE_COL_URL)
        assert len(entries) == 1
        assert entries[0]["list_date"] == "2026-07-27"

    def test_bare_unquoted_entry_href_is_parsed(self):
        html = ("<a href=/zhengcehuobisi/125207/125213/125431/125475/"
                "2026072709025211011/index.html>公开市场业务交易公告 [2026]第143号</a>")
        assert len(co.extract_entries(html, _TRADE_COL_URL)) == 1

    def test_unnumbered_mlf_titles_survive(self):
        # REGRESSION GUARD: an entry filter that requires a 第N号 number drops the whole
        # MLF column — its bulletins are titled '2026年7月中期借贷便利招标公告'.
        entries = co.extract_entries(_fx("mlf_col.html"), _MLF_COL_URL)
        assert len(entries) == 4
        assert entries[0]["title"] == "2026年7月中期借贷便利招标公告"
        assert entries[0]["list_date"] == "2026-07-23"
        assert all(co.bulletin_no(e["title"]) == "" for e in entries)

    def test_urls_dedupe_keep_first(self):
        html = ('<a href="/zhengcehuobisi/1/2/3/20260727000000001/index.html">第一次</a>'
                '<a href="/zhengcehuobisi/1/2/3/20260727000000001/index.html">重复</a>')
        entries = co.extract_entries(html, _TRADE_COL_URL)
        assert len(entries) == 1 and entries[0]["title"] == "第一次"

    def test_empty_and_garbage_pages_degrade(self):
        assert co.extract_entries("", _TRADE_COL_URL) == []
        assert co.extract_entries("<html><body>no links</body></html>", _TRADE_COL_URL) == []


# --------------------------------------------------------------------------- #
# bulletin numbers + tenor arithmetic
# --------------------------------------------------------------------------- #

class TestBulletinNo:
    def test_ascii_brackets(self):
        assert co.bulletin_no("公开市场业务交易公告 [2026]第143号") == "2026-143"

    def test_full_width_brackets(self):
        # 公开市场业务公告 prints ［2026］第5号 with FULL-WIDTH brackets.
        assert co.bulletin_no("中国人民银行公开市场业务公告［2026］第5号") == "2026-5"

    def test_outright_variant(self):
        assert co.bulletin_no("公开市场买断式逆回购招标公告 [2026]第14号") == "2026-14"

    def test_unnumbered_title_is_empty_not_an_error(self):
        assert co.bulletin_no("2026年7月中期借贷便利招标公告") == ""
        assert co.bulletin_no("") == ""


class TestTenorDays:
    @pytest.mark.parametrize("label,days", [
        ("7天", 7.0), ("14天", 14.0), ("隔夜", 1.0),
        ("1年", 365.0), ("1年期", 365.0),
        ("6个月（184天）", 184.0),     # the bulletin's own arithmetic wins
        ("6个月(184天)", 184.0),       # ASCII parens variant
        ("6个月", 180.0),              # no printed day count → ×30 convention
        ("3个月", 90.0), ("91天", 91.0),
    ])
    def test_known_labels(self, label, days):
        assert co.tenor_days(label) == days

    def test_unparseable_label_is_nan_not_a_crash(self):
        assert math.isnan(co.tenor_days("不明期限"))
        assert math.isnan(co.tenor_days(""))
        assert math.isnan(co.tenor_days(None))


# --------------------------------------------------------------------------- #
# detail parsers — pinned to the captured bulletins
# --------------------------------------------------------------------------- #

class TestParseTrade:
    def test_bulletin_143_exact_numbers(self):
        rows = co.parse_trade(_fx("trade_143.html"), "2026-07-27")
        assert len(rows) == 1
        r = rows[0]
        assert r["op_date"] == "2026-07-27"
        assert r["kind"] == "reverse_repo"
        assert r["tenor_label"] == "7天" and r["tenor_days"] == 7.0
        assert r["rate_pct"] == 1.40
        assert r["bid_bn"] == 3255.0 and r["awarded_bn"] == 3255.0
        assert r["amount_bn"] == 3255.0

    def test_bulletin_142_exact_numbers(self):
        r = co.parse_trade(_fx("trade_142.html"), "2026-07-24")[0]
        assert (r["op_date"], r["tenor_days"], r["rate_pct"], r["amount_bn"]) == (
            "2026-07-24", 7.0, 1.40, 890.0)

    def test_span_split_cells_are_rejoined(self):
        # The CMS renders the rate as <span>1.</span><span>40</span> and the tenor as
        # <span>7</span><span>天</span>. Collapsing whitespace instead of removing it
        # yields "1. 40" and "7 天", i.e. rate 1.0 and an unparseable tenor.
        assert "1.</span>" in _fx("trade_143.html")
        r = co.parse_trade(_fx("trade_143.html"), "2026-07-27")[0]
        assert r["rate_pct"] == 1.40 and r["tenor_label"] == "7天"

    def test_multi_tenor_table_yields_one_row_per_tenor(self):
        html = """<div id="zoom"><p>2026年7月27日中国人民银行开展逆回购操作。</p>
        <table><tr><td>期限</td><td>操作利率</td><td>投标量</td><td>中标量</td></tr>
        <tr><td>7天</td><td>1.40%</td><td>3255亿元</td><td>3255亿元</td></tr>
        <tr><td>14天</td><td>1.55%</td><td>1000亿元</td><td>800亿元</td></tr>
        </table></div>"""
        rows = co.parse_trade(html, "2026-07-27")
        assert [(r["tenor_label"], r["tenor_days"], r["rate_pct"], r["awarded_bn"])
                for r in rows] == [("7天", 7.0, 1.40, 3255.0), ("14天", 14.0, 1.55, 800.0)]
        assert all(r["op_date"] == "2026-07-27" for r in rows)

    def test_multi_price_auction_reads_the_weighted_average_rate(self):
        """REVIEW F10 — a 利率招标 result table prints THREE rate columns.

        最高 / 最低 / 加权平均中标利率, in that order. Taking the leftmost 利率 header
        publishes the HIGHEST accepted bid as the operation's rate — the tail of the
        auction dressed up as the policy rate.
        """
        html = """<div id="zoom"><p>2026年7月27日中国人民银行开展逆回购操作。</p>
        <table><tr><td>期限</td><td>最高中标利率</td><td>最低中标利率</td>
        <td>加权平均中标利率</td><td>投标量</td><td>中标量</td></tr>
        <tr><td>91天</td><td>1.68%</td><td>1.45%</td><td>1.51%</td>
        <td>5000亿元</td><td>3000亿元</td></tr></table></div>"""
        r = co.parse_trade(html, "2026-07-27")[0]
        assert r["rate_pct"] == 1.51
        assert r["bid_bn"] == 5000.0 and r["awarded_bn"] == 3000.0

    def test_a_total_row_is_never_stored_as_a_tenor(self):
        """REVIEW F10 — the 合计 footer sums the tenors above it.

        Stored as a tenor it becomes a phantom operation that double-counts the whole
        table (and, keyed on tenor_label, a permanent one).
        """
        html = """<div id="zoom"><p>2026年7月27日中国人民银行开展逆回购操作。</p>
        <table><tr><td>期限</td><td>操作利率</td><td>投标量</td><td>中标量</td></tr>
        <tr><td>7天</td><td>1.40%</td><td>6000亿元</td><td>5000亿元</td></tr>
        <tr><td>14天</td><td>1.55%</td><td>4000亿元</td><td>3000亿元</td></tr>
        <tr><td>合计</td><td></td><td>10000亿元</td><td>8000亿元</td></tr>
        </table></div>"""
        rows = co.parse_trade(html, "2026-07-27")
        assert [r["tenor_label"] for r in rows] == ["7天", "14天"]
        assert sum(r["awarded_bn"] for r in rows) == 8000.0

    def test_table_without_a_bid_column_still_parses(self):
        html = """<div id="zoom"><p>2026年7月27日开展逆回购操作。</p>
        <table><tr><td>期限</td><td>中标利率</td><td>中标量</td></tr>
        <tr><td>7天</td><td>1.40%</td><td>3255亿元</td></tr></table></div>"""
        r = co.parse_trade(html, "2026-07-27")[0]
        assert r["rate_pct"] == 1.40 and r["awarded_bn"] == 3255.0
        assert math.isnan(r["bid_bn"])
        assert r["amount_bn"] == 3255.0     # falls back to 中标量

    def test_narrative_fallback_when_no_table(self):
        html = ('<div id="zoom"><p>2026年7月27日中国人民银行以固定利率、数量招标方式'
                '开展了3255亿元7天期逆回购操作。</p></div>')
        r = co.parse_trade(html, "2026-07-27")[0]
        assert r["op_date"] == "2026-07-27"
        assert r["amount_bn"] == 3255.0
        assert r["tenor_label"] == "7天" and r["tenor_days"] == 7.0

    def test_unexpected_text_is_empty_not_an_exception(self):
        assert co.parse_trade("<div id='zoom'><p>今日无操作</p></div>", "2026-07-27") == []
        assert co.parse_trade("", "") == []
        assert co.parse_trade(None, "") == []


class TestParseAnnouncement:
    def test_bulletin_5_expands_the_date_range(self):
        rows = co.parse_announcement(_fx("ann_5.html"), "2026-07-24")
        assert [(r["op_date"], r["amount_bn"]) for r in rows] == [
            ("2026-07-29", 6000.0),
            ("2026-07-30", 6000.0),
            ("2026-07-31", 6000.0),
            ("2026-08-03", 3000.0),
        ]

    def test_every_row_is_an_overnight_preannouncement(self):
        rows = co.parse_announcement(_fx("ann_5.html"), "2026-07-24")
        assert all(r["kind"] == "reverse_repo_preannounce" for r in rows)
        assert all(r["tenor_label"] == "隔夜" and r["tenor_days"] == 1.0 for r in rows)

    def test_rate_is_nan_because_the_bulletin_states_none(self):
        # 量价分离: a fixed-rate tender whose rate is not printed. A 0.0 here would be
        # a claim the PBOC never made.
        rows = co.parse_announcement(_fx("ann_5.html"), "2026-07-24")
        assert all(math.isnan(r["rate_pct"]) for r in rows)
        assert co.count_nulls(rows) == 4

    def test_the_year_comes_from_the_list_date_not_the_clock(self):
        rows = co.parse_announcement(_fx("ann_5.html"), "2027-07-24")
        assert rows[0]["op_date"] == "2027-07-29"

    def test_december_announcement_rolls_january_into_the_next_year(self):
        html = ('<div id="zoom"><p>中国人民银行将在1月2日开展隔夜逆回购操作。'
                '1月2日开展3000亿元。</p></div>')
        rows = co.parse_announcement(html, "2026-12-28")
        assert rows[0]["op_date"] == "2027-01-02"

    def test_january_announcement_rolls_december_into_the_previous_year(self):
        """REVIEW F11 — the roll must be SYMMETRIC.

        A January bulletin referring back to a 12月30日 operation is the mirror of the
        December→January case; with only the forward roll it lands eleven months in
        the FUTURE, which is worse than the defect the forward roll was added for.
        """
        html = ('<div id="zoom"><p>中国人民银行于12月30日开展隔夜逆回购操作。'
                '12月30日开展3000亿元。</p></div>')
        rows = co.parse_announcement(html, "2027-01-05")
        assert rows[0]["op_date"] == "2026-12-30"

    def test_both_roll_directions_are_pinned_on_the_helper(self):
        assert co._dated(1, 2, 2026, "2026-12-28") == "2027-01-02"    # +1y
        assert co._dated(12, 30, 2027, "2027-01-05") == "2026-12-30"  # -1y
        assert co._dated(7, 29, 2026, "2026-07-24") == "2026-07-29"   # no roll
        assert co._dated(1, 5, 2026, "2026-06-30") == "2026-01-05"    # 5 months back: no roll

    def test_same_month_announcement_does_not_roll(self):
        html = ('<div id="zoom"><p>将在7月29日开展隔夜逆回购操作。7月29日开展3000亿元。</p></div>')
        assert co.parse_announcement(html, "2026-07-24")[0]["op_date"] == "2026-07-29"

    def test_document_signature_year_is_the_fallback(self):
        # No list date available → the bulletin's own CJK-numeral signature supplies
        # the year. Never our clock.
        assert co.document_year("二〇二六年七月二十四日", "") == 2026
        assert co.document_year("2026年7月24日", "") == 2026
        assert co.document_year("无年份", "") is None

    def test_yearless_document_yields_no_dated_rows(self):
        html = '<div id="zoom"><p>7月29日开展6000亿元。</p></div>'
        assert co.parse_announcement(html, "") == []

    def test_unexpected_text_is_empty_not_an_exception(self):
        assert co.parse_announcement("<div id='zoom'>特此通知。</div>", "2026-07-24") == []
        assert co.parse_announcement("", "") == []


class TestParseOutright:
    def test_bulletin_14_exact_numbers(self):
        rows = co.parse_outright(_fx("outright_14.html"), "2026-07-14")
        assert len(rows) == 1
        r = rows[0]
        assert r["op_date"] == "2026-07-15"        # the OPERATION date, not the 07-14 signature
        assert r["amount_bn"] == 14000.0
        assert r["tenor_days"] == 184.0            # from （184天）, not 6×30
        assert r["tenor_label"] == "6个月"
        assert r["maturity_date"] == "2027-01-15"
        assert r["kind"] == "outright_repo_tender"

    def test_rate_is_nan_on_a_rate_discovered_tender(self):
        r = co.parse_outright(_fx("outright_14.html"), "2026-07-14")[0]
        assert math.isnan(r["rate_pct"])

    def test_the_signature_date_is_never_mistaken_for_the_operation_date(self):
        assert "2026年7月14日" in _fx("outright_14.html").replace(" ", "")
        assert co.parse_outright(_fx("outright_14.html"), "2026-07-14")[0]["op_date"] != "2026-07-14"

    def test_unexpected_text_is_empty_not_an_exception(self):
        assert co.parse_outright("<div id='zoom'>公告</div>", "2026-07-14") == []
        assert co.parse_outright("", "") == []


class TestParseMlf:
    def test_july_tender_exact_numbers(self):
        rows = co.parse_mlf(_fx("mlf_jul.html"), "2026-07-23")
        assert len(rows) == 1
        r = rows[0]
        assert r["op_date"] == "2026-07-24"
        assert r["amount_bn"] == 5000.0
        assert r["tenor_days"] == 365.0
        assert r["kind"] == "mlf_tender"
        assert math.isnan(r["rate_pct"])

    def test_unexpected_text_is_empty_not_an_exception(self):
        assert co.parse_mlf("<div id='zoom'>招标公告</div>", "2026-07-23") == []
        assert co.parse_mlf("", "") == []


class TestZoomExtraction:
    def test_zoom_body_is_isolated_from_page_chrome(self):
        zoom = co.zoom_html(_fx("trade_143.html"))
        assert "3255" in zoom
        assert "关闭窗口" not in zoom       # the surrounding CMS chrome stays out

    def test_nested_divs_do_not_truncate_the_body(self):
        html = '<div id="zoom"><div class="inner">A</div>TAIL</div>AFTER'
        assert co.zoom_html(html) == '<div class="inner">A</div>TAIL'

    def test_absent_zoom_is_empty(self):
        assert co.zoom_html("<div>no zoom here</div>") == ""


# --------------------------------------------------------------------------- #
# row assembly
# --------------------------------------------------------------------------- #

_TRADE_ENTRY = {"url": "https://www.pbc.gov.cn/x/2026072709025211011/index.html",
                "title": "公开市场业务交易公告 [2026]第143号",
                "list_date": "2026-07-27"}
_ANN_ENTRY = {"url": "https://www.pbc.gov.cn/x/2026072413564746531/index.html",
              "title": "中国人民银行公开市场业务公告［2026］第5号",
              "list_date": "2026-07-24"}
_OUTRIGHT_ENTRY = {"url": "https://www.pbc.gov.cn/x/2026071416335097398/index.html",
                   "title": "公开市场买断式逆回购招标公告 [2026]第14号",
                   "list_date": "2026-07-14"}
_MLF_ENTRY = {"url": "https://www.pbc.gov.cn/x/2026072318022895816/index.html",
              "title": "2026年7月中期借贷便利招标公告",
              "list_date": "2026-07-23"}


def _trade_rows():
    return co.build_rows(_TRADE_ENTRY, "trade", _fx("trade_143.html"), _TS)


class TestBuildRows:
    def test_canonical_columns_and_stamps(self):
        row = _trade_rows()[0]
        assert set(row) == set(co._OPS_COLUMNS)
        assert row["provenance"] == "pboc_bulletin"
        assert row["column"] == "trade"
        assert row["bulletin_no"] == "2026-143"
        assert row["announce_date"] == "2026-07-27"
        assert row["first_seen"] == _TS and row["fetched_at"] == _TS

    def test_announcement_rows_carry_the_bulletin_identity(self):
        rows = co.build_rows(_ANN_ENTRY, "announcement", _fx("ann_5.html"), _TS)
        assert len(rows) == 4
        assert {r["bulletin_no"] for r in rows} == {"2026-5"}
        assert {r["column"] for r in rows} == {"announcement"}
        assert {r["announce_date"] for r in rows} == {"2026-07-24"}

    def test_mlf_rows_accept_an_empty_bulletin_number(self):
        row = co.build_rows(_MLF_ENTRY, "mlf", _fx("mlf_jul.html"), _TS)[0]
        assert row["bulletin_no"] == "" and row["kind"] == "mlf_tender"

    def test_unknown_column_yields_nothing(self):
        assert co.build_rows(_TRADE_ENTRY, "not_a_column", _fx("trade_143.html"), _TS) == []


class TestCountNulls:
    def test_a_complete_result_bulletin_has_no_core_nulls(self):
        assert co.count_nulls(_trade_rows()) == 0

    def test_preannouncement_rates_are_counted(self):
        rows = co.build_rows(_ANN_ENTRY, "announcement", _fx("ann_5.html"), _TS)
        assert co.count_nulls(rows) == 4       # four unstated rates, printed not hidden

    def test_tender_rate_is_counted(self):
        rows = co.build_rows(_OUTRIGHT_ENTRY, "outright", _fx("outright_14.html"), _TS)
        assert co.count_nulls(rows) == 1


# --------------------------------------------------------------------------- #
# events.jsonl — kind namespace + hash dedup
# --------------------------------------------------------------------------- #

class TestBuildEvent:
    def test_kind_is_omo_observed_never_omo_mlf(self):
        for entry, column, fixture in (
                (_TRADE_ENTRY, "trade", "trade_143.html"),
                (_ANN_ENTRY, "announcement", "ann_5.html"),
                (_OUTRIGHT_ENTRY, "outright", "outright_14.html"),
                (_MLF_ENTRY, "mlf", "mlf_jul.html")):
            ev = co.build_event(co.build_rows(entry, column, _fx(fixture), _TS))
            assert ev is not None, fixture
            # W3 gate 10: "omo_mlf" is engine/china_policy_transmission's SYNTHETIC
            # FR007-z namespace. An OBSERVED bulletin must never land in it — least of
            # all the MLF tender, which is the one most tempting to mis-file.
            assert ev["kind"] == "omo_observed"
            assert ev["kind"] != "omo_mlf"
            assert ev["provenance"] == "pboc_bulletin"
            assert ev["source"] == "pboc"

    def test_row_conforms_to_the_documented_ledger_shape(self):
        """REVIEW F17 — events.jsonl rows carry sectors + phrase_diff_ref.

        Every seeded row in data/china_policy_transmission/events.jsonl has them, so a
        short row from this collector would make each consumer branch on where the row
        came from. A PBOC operation states neither, hence [] and None — the honest
        empties, not absent keys.
        """
        ev = co.build_event(_trade_rows())
        assert set(ev) == {"ts", "source", "kind", "title", "url", "sectors",
                           "phrase_diff_ref", "provenance", "_hash"}
        assert ev["sectors"] == [] and ev["phrase_diff_ref"] is None

    def test_hash_is_the_engines_own_key(self):
        from engine.china_policy_transmission import _event_hash
        ev = co.build_event(_trade_rows())
        assert ev["_hash"] == _event_hash(ev["ts"], "pboc", "omo_observed", ev["title"])

    def test_ts_is_the_operation_date(self):
        assert co.build_event(_trade_rows())["ts"] == "2026-07-27"
        ann = co.build_rows(_ANN_ENTRY, "announcement", _fx("ann_5.html"), _TS)
        assert co.build_event(ann)["ts"] == "2026-07-29"     # first announced operation

    def test_title_carries_a_compact_zh_summary(self):
        ev = co.build_event(_trade_rows())
        assert ev["title"].startswith("公开市场业务交易公告 [2026]第143号 — ")
        assert "3255亿元" in ev["title"] and "1.40%" in ev["title"]

    def test_summary_of_a_multi_day_preannouncement(self):
        """REVIEW F19: identical clauses COLLAPSE and the distinct one is never hidden.

        The old head-of-three slice printed '6000亿元' three times and pushed the ONE
        figure that differs (the 3000亿元 fourth day) behind '等4笔' — repetition that
        also rode into the events.jsonl title.
        """
        rows = co.build_rows(_ANN_ENTRY, "announcement", _fx("ann_5.html"), _TS)
        summary = co.summarise(rows)
        assert summary == "隔夜逆回购(预告) 6000亿元×3、隔夜逆回购(预告) 3000亿元"
        assert "3000亿元" in summary                       # the distinct clause is SHOWN
        assert "6000亿元、隔夜逆回购(预告) 6000亿元" not in summary   # never repeated
        assert "等" not in summary                         # nothing is hidden to hide

    def test_summary_keeps_a_tail_marker_only_past_four_distinct_clauses(self):
        rows = [{"kind": "reverse_repo", "tenor_label": f"{d}天", "amount_bn": 100.0 * d,
                 "rate_pct": float("nan")} for d in (1, 7, 14, 28, 91)]
        summary = co.summarise(rows)
        assert summary.endswith("等5笔")                   # 5 distinct clauses > cap of 4
        assert "91天" not in summary                       # the head is a head
        assert co.summarise(rows[:4]).endswith("28天逆回购 2800亿元")   # 4 fits whole

    def test_empty_and_other_kinds_produce_no_event(self):
        assert co.build_event([]) is None
        assert co.build_event([{"kind": "other", "op_date": "2026-07-27"}]) is None
        assert co.build_event([{"kind": "reverse_repo", "op_date": "", "announce_date": ""}]) is None


class TestAppendEvents:
    def test_rows_land_in_the_ledger(self, store):
        ev = co.build_event(_trade_rows())
        assert co.append_events([ev]) == 1
        rows = _events(store)
        assert len(rows) == 1 and rows[0]["kind"] == "omo_observed"

    def test_second_run_is_idempotent(self, store):
        ev = co.build_event(_trade_rows())
        assert co.append_events([ev]) == 1
        assert co.append_events([ev]) == 0      # hash dedup
        assert len(_events(store)) == 1

    def test_empty_list_writes_nothing(self, store):
        assert co.append_events([]) == 0
        assert _events(store) == []


# --------------------------------------------------------------------------- #
# store — append-only + dedup keep-LAST
# --------------------------------------------------------------------------- #

class TestOperationsStore:
    def test_empty_write_is_zero(self, store):
        assert co.write_operations([]) == 0

    def test_new_rows_land(self, store):
        assert co.write_operations(_trade_rows()) == 1
        assert len(co.load_operations()) == 1

    def test_columns_are_canonical(self, store):
        co.write_operations(_trade_rows())
        stored = pd.read_parquet(co._ops_path())
        for col in co._OPS_COLUMNS:
            assert col in stored.columns, f"missing column: {col}"

    def test_load_returns_schema_when_absent(self, store):
        df = co.load_operations()
        assert df.empty and list(df.columns) == list(co._OPS_COLUMNS)

    def test_one_bulletin_four_operation_days_is_four_rows(self, store):
        rows = co.build_rows(_ANN_ENTRY, "announcement", _fx("ann_5.html"), _TS)
        assert co.write_operations(rows) == 4
        assert len(co.load_operations()) == 4

    def test_rewriting_the_same_bulletin_is_not_new_rows(self, store):
        co.write_operations(_trade_rows())
        assert co.write_operations(_trade_rows()) == 0
        assert len(co.load_operations()) == 1

    def test_a_corrected_amount_updates_keep_last(self, store):
        co.write_operations(_trade_rows())
        corrected = _trade_rows()
        corrected[0]["amount_bn"] = 3300.0
        corrected[0]["fetched_at"] = "2026-07-28T12:00:00+00:00"
        assert co.write_operations(corrected) == 0
        stored = co.load_operations()
        assert len(stored) == 1 and stored.iloc[0]["amount_bn"] == 3300.0

    def test_first_seen_survives_a_value_correction(self, store):
        co.write_operations(_trade_rows())
        later = "2026-08-30T12:00:00+00:00"
        corrected = _trade_rows()
        corrected[0]["amount_bn"] = 3300.0
        corrected[0]["fetched_at"] = later
        corrected[0]["first_seen"] = later
        co.write_operations(corrected)
        stored = co.load_operations()
        assert stored.iloc[0]["fetched_at"] == later     # last observed advances
        assert stored.iloc[0]["first_seen"] == _TS       # first observed does not

    def test_corrupt_store_aborts_the_append_untouched(self, store):
        co.write_operations(_trade_rows())
        corrupt = b"PAR1 this is not a parquet file"
        co._ops_path().write_bytes(corrupt)
        rows = co.build_rows(_ANN_ENTRY, "announcement", _fx("ann_5.html"), _TS)
        assert co.write_operations(rows) == 0
        assert co._ops_path().read_bytes() == corrupt    # left for manual recovery

    def test_write_is_atomic_no_tmp_residue(self, store):
        assert co.write_operations(_trade_rows()) == 1
        leftovers = [p.name for p in co._ops_path().parent.iterdir()
                     if p.name != co._ops_path().name]
        assert leftovers == []

    def test_stored_urls_is_the_diff_set(self, store):
        assert co.stored_urls() == set()
        co.write_operations(_trade_rows())
        assert co.stored_urls() == {_TRADE_ENTRY["url"]}


# --------------------------------------------------------------------------- #
# refresh() — cap / guard / degrade
# --------------------------------------------------------------------------- #

_COL_FIXTURES = {
    _TRADE_COL_URL: "trade_col.html",
    _ANN_COL_URL: "landing_list.html",     # the 业务公告 entries live on it too
    _OUTRIGHT_COL_URL: "landing_list.html",
    _MLF_COL_URL: "mlf_col.html",
}


def _wire(monkeypatch, detail_for=None, columns=None, clock=None, fail=()):
    """Serve fixtures instead of HTTP. Returns the list of URLs requested."""
    calls: list[str] = []
    cols = columns if columns is not None else _COL_FIXTURES

    def _get(_session, url):
        calls.append(url)
        if url in fail:
            raise IOError("boom")
        if url in cols:
            return _fx(cols[url])
        return _fx(detail_for or "trade_143.html")

    monkeypatch.setattr(co, "_get", _get)
    if clock is not None:
        monkeypatch.setattr(co, "_clock", clock)
    return calls


class TestRefresh:
    def test_every_column_failing_is_a_runtime_error(self, store, monkeypatch):
        _wire(monkeypatch, fail=set(_COL_FIXTURES))
        with pytest.raises(RuntimeError, match="every one of the"):
            co.refresh()

    def test_one_dead_column_does_not_sink_the_night(self, store, monkeypatch):
        _wire(monkeypatch, columns={_TRADE_COL_URL: "trade_col.html"},
              fail={_ANN_COL_URL, _OUTRIGHT_COL_URL, _MLF_COL_URL})
        s = co.refresh()
        assert s["columns_polled"] == 1
        assert s["n_failed"] == 3
        assert s["n_new"] > 0

    def test_the_twenty_detail_cap_defers_the_remainder(self, store, monkeypatch):
        # trade_col alone lists 20 bulletins; the four polled columns together offer
        # more, so the cap must bite and the overflow must be LEDGERED, not dropped.
        calls = _wire(monkeypatch)
        s = co.refresh()
        details = [u for u in calls if u not in _COL_FIXTURES]
        assert len(details) == co._DETAIL_CAP == 20
        assert s["n_fetched"] == 20
        assert s["n_deferred"] > 0

    def test_the_backlog_drains_night_by_night(self, store, monkeypatch):
        # 20 trade bulletins behind a cap of 8: 8 + 8 + 4, and nothing is lost on the
        # way. Only the trade column is wired so every detail parses (the cap, not a
        # parse failure, is what this test is about).
        monkeypatch.setattr(co, "_DETAIL_CAP", 8)
        _wire(monkeypatch, columns={_TRADE_COL_URL: "trade_col.html"},
              fail={_ANN_COL_URL, _OUTRIGHT_COL_URL, _MLF_COL_URL})
        nights = [co.refresh() for _ in range(3)]
        assert [n["n_fetched"] for n in nights] == [8, 8, 4]
        assert [n["n_deferred"] for n in nights] == [12, 4, 0]
        assert len(co.load_operations()) == 20      # every bulletin eventually landed

    def test_a_quiet_night_writes_nothing_and_does_not_crash(self, store, monkeypatch):
        _wire(monkeypatch, columns={_TRADE_COL_URL: "trade_col.html"},
              fail={_ANN_COL_URL, _OUTRIGHT_COL_URL, _MLF_COL_URL})
        co.refresh()
        s = co.refresh()          # nothing new upstream → a clean 0-row night
        assert s == {"n_new": 0, "n_fetched": 0, "n_failed": 3, "n_nulls": 0,
                     "n_deferred": 0, "n_store_abort": 0, "columns_polled": 1}

    def test_an_unreadable_store_halts_the_night_before_any_fetch(self, store, monkeypatch):
        """REVIEW F8 — the abort must come FIRST, not after the night's work.

        write_operations() already refused to append onto an unreadable store, but the
        refusal fired at the END: 24 upstream fetches were spent, the URL diff ran
        against an EMPTY known-set (so every bulletin looked new, every night), and
        events.jsonl gained rows for bulletins the store never received — a permanent
        ledger/tape divergence that no later run repairs.
        """
        co.write_operations(_trade_rows())
        corrupt = b"PAR1 this is not a parquet file"
        co._ops_path().write_bytes(corrupt)
        before_events = len(_events(store))

        calls = _wire(monkeypatch)
        s = co.refresh()

        assert calls == []                                  # nothing was fetched at all
        assert s["n_store_abort"] == 1
        assert s == {"n_new": 0, "n_fetched": 0, "n_failed": 0, "n_nulls": 0,
                     "n_deferred": 0, "n_store_abort": 1, "columns_polled": 0}
        assert co._ops_path().read_bytes() == corrupt       # left for manual recovery
        assert len(_events(store)) == before_events         # the ledger did not move

    def test_the_abort_reaches_the_sentinel_frame(self, store, monkeypatch):
        co._ops_path().parent.mkdir(parents=True, exist_ok=True)
        co._ops_path().write_bytes(b"PAR1 garbage")
        _wire(monkeypatch)
        sentinel = co.ChinaOmoAdapter().fetch()["refresh"]
        assert sentinel["n_store_abort"].iloc[0] == 1.0
        assert sentinel["n_fetched"].iloc[0] == 0.0
        assert not co.ChinaOmoAdapter().validate("refresh", sentinel).empty

    def test_wall_clock_guard_stops_and_defers(self, store, monkeypatch):
        ticks = iter([0.0] * 3 + [co._BUDGET_S + 1.0] * 200)
        _wire(monkeypatch, clock=lambda: next(ticks))
        s = co.refresh()
        assert s["n_fetched"] <= 3
        assert s["n_deferred"] > 0        # everything unfetched is owed, not lost

    def test_a_cross_listed_bulletin_is_fetched_once(self, store, monkeypatch):
        # The landing fixture is served for BOTH the announcement and outright columns,
        # so every one of its bulletins appears twice in the polled set. Fetching it
        # twice would burn two cap slots and let fetch order decide the row's `column`
        # provenance; the first listing wins instead.
        calls = _wire(monkeypatch, detail_for="ann_5.html",
                      columns={_ANN_COL_URL: "landing_list.html",
                               _OUTRIGHT_COL_URL: "landing_list.html"},
                      fail={_TRADE_COL_URL, _MLF_COL_URL})
        co.refresh()
        details = [u for u in calls if u not in _COL_FIXTURES]
        assert len(details) == len(set(details)) == 20
        assert set(co.load_operations()["column"]) == {"announcement"}

    def test_newest_bulletins_are_fetched_first(self, store, monkeypatch):
        calls = _wire(monkeypatch)
        co.refresh()
        details = [u for u in calls if u not in _COL_FIXTURES]
        assert details[0].endswith("/2026072709025211011/index.html")   # 143号, 07-27

    def test_events_are_appended_once_per_bulletin(self, store, monkeypatch):
        _wire(monkeypatch, columns={_TRADE_COL_URL: "trade_col.html"},
              fail={_ANN_COL_URL, _OUTRIGHT_COL_URL, _MLF_COL_URL})
        co.refresh()
        rows = _events(store)
        assert len(rows) == 20                       # one event per bulletin, not per tenor
        assert {r["kind"] for r in rows} == {"omo_observed"}
        assert {r["provenance"] for r in rows} == {"pboc_bulletin"}

    def test_a_rerun_appends_no_duplicate_events(self, store, monkeypatch):
        _wire(monkeypatch, columns={_TRADE_COL_URL: "trade_col.html"},
              fail={_ANN_COL_URL, _OUTRIGHT_COL_URL, _MLF_COL_URL})
        co.refresh()
        before = len(_events(store))
        co.refresh()
        assert len(_events(store)) == before

    def test_an_unparseable_bulletin_is_counted_not_stored(self, store, monkeypatch):
        """REVIEW F16 — a parse failure is a FAILURE, not a null.

        n_nulls answers "how many fields did the bulletins not state"; a document that
        parsed to nothing has no fields at all. Folding it into n_nulls made a night of
        unprinted rates and a night of broken parsing the same number.
        """
        _wire(monkeypatch, detail_for="mlf_col.html",     # a list page, not a bulletin
              columns={_TRADE_COL_URL: "trade_col.html"},
              fail={_ANN_COL_URL, _OUTRIGHT_COL_URL, _MLF_COL_URL})
        s = co.refresh()
        assert s["n_fetched"] == 20 and s["n_new"] == 0
        assert s["n_failed"] == 23         # 3 dead columns + 20 unparseable documents
        assert s["n_nulls"] == 0           # no ROWS were stored, so no fields are null
        assert co.load_operations().empty

    def test_n_nulls_counts_unstated_fields_only(self, store, monkeypatch):
        """The positive half of F16: real rows with a real coverage gap."""
        _wire(monkeypatch, detail_for="ann_5.html",
              columns={_ANN_COL_URL: "landing_list.html"},
              fail={_TRADE_COL_URL, _OUTRIGHT_COL_URL, _MLF_COL_URL})
        monkeypatch.setattr(co, "_DETAIL_CAP", 1)
        s = co.refresh()
        # one bulletin → four pre-announced operations, each with an unstated rate
        assert s["n_fetched"] == 1 and s["n_new"] == 4
        assert s["n_nulls"] == 4 and s["n_failed"] == 3

    def test_a_failing_detail_does_not_stop_the_run(self, store, monkeypatch):
        entries = co.extract_entries(_fx("trade_col.html"), _TRADE_COL_URL)
        _wire(monkeypatch, columns={_TRADE_COL_URL: "trade_col.html"},
              fail={_ANN_COL_URL, _OUTRIGHT_COL_URL, _MLF_COL_URL, entries[0]["url"]})
        s = co.refresh()
        assert s["n_fetched"] == 19 and s["n_failed"] == 4


# --------------------------------------------------------------------------- #
# adapter contract
# --------------------------------------------------------------------------- #

class TestAdapter:
    def test_sentinel_frame_shape(self, store, monkeypatch):
        _wire(monkeypatch)
        frames = co.ChinaOmoAdapter().fetch()
        sentinel = frames["refresh"]
        assert list(sentinel.columns) == ["n_new", "n_fetched", "n_failed", "n_nulls",
                                          "n_deferred", "n_store_abort", "columns_polled"]
        assert sentinel["n_store_abort"].iloc[0] == 0.0    # a healthy night says so
        # tz-NAIVE DatetimeIndex: validate() calls pd.to_datetime(df.index), and a
        # tz-aware index makes store.upsert's combine_first raise.
        assert isinstance(sentinel.index, pd.DatetimeIndex)
        assert sentinel.index.tz is None
        assert all(sentinel[c].dtype.kind == "f" for c in sentinel.columns)
        assert not co.ChinaOmoAdapter().validate("refresh", sentinel).empty

    def test_group_prefix_routes_to_the_asia_lane(self):
        assert co.ChinaOmoAdapter.group.startswith("china")
        assert co.ChinaOmoAdapter.stale_after_days == 5

    def test_adapter_is_registered_and_stays_serial(self):
        from scripts.collect import _CONCURRENT_HOSTS, all_adapters
        assert "china_omo" in all_adapters()
        # www.pbc.gov.cn is shared with the serial china_official_corpora adapter —
        # moving this into a concurrent host group would break ≤1 req/s/host.
        assert "china_omo" not in _CONCURRENT_HOSTS
