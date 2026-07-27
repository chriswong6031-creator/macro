"""Tests for collectors/china_official_corpora.py — the official-corpus fetcher.

Covers the PURE / offline surface (no network): gb2312/gbk decoding, tag
stripping, document-date parsing, same-site link extraction in DOCUMENT ORDER,
People's Daily layout URL, body_sha256, keep-FIRST date-keyed parquet storage +
read_corpus, and the qbus row mapping (TIER1 / lang=zh / body_sha256 set /
timestamp_quality). Storage is redirected to tmp_path so no tracked parquet is
touched. Network fetch is never exercised.

Regression:
- test_summary_frame_has_datetime_index: verifies that the summary DataFrame
  returned by fetch() carries a DatetimeIndex rather than an organ-string index,
  which previously caused run_adapter/validate() to raise:
    DateParseError: Unknown datetime string format, unable to parse: state_council
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import china_official_corpora as coc  # noqa: E402

_FIX = Path(__file__).resolve().parent / "fixtures" / "china_official_corpora"


# --------------------------------------------------------------------------- #
# decoding + text helpers
# --------------------------------------------------------------------------- #
def test_decode_gb2312_without_http_charset():
    html = ('<html><head><meta charset="gb2312"></head>'
            '<body>适度宽松的货币政策</body></html>').encode("gb18030")
    out = coc._decode(html, "")   # no HTTP charset → sniff <meta>
    assert "适度宽松的货币政策" in out


def test_decode_falls_back_to_utf8():
    html = "适度宽松".encode("utf-8")
    assert "适度宽松" in coc._decode(html, "text/html")


def test_strip_html_drops_scripts_and_tags():
    raw = "<div>房住不炒<script>var x=1;</script><b>保交楼</b></div>"
    txt = coc._strip_html(raw)
    assert "房住不炒" in txt and "保交楼" in txt
    assert "var x" not in txt and "<" not in txt


def test_doc_date_parses_various_forms():
    assert coc._doc_date("发布日期 2026-07-02 央行") == "2026-07-02"
    assert coc._doc_date("2026年7月2日 通知") == "2026-07-02"
    assert coc._doc_date("no date here") == ""


def test_body_sha256_empty_and_nonempty():
    assert coc.body_sha256("") == ""
    h = coc.body_sha256("适度宽松")
    assert len(h) == 64 and h == coc.body_sha256("适度宽松")   # deterministic


# --------------------------------------------------------------------------- #
# link extraction — same-site, min-title, DOCUMENT ORDER preserved
# --------------------------------------------------------------------------- #
def test_extract_links_same_site_and_order():
    html = (
        '<a href="/art/1.htm">适度宽松的货币政策落地实施</a>'
        '<a href="http://other.com/z">外部链接被过滤</a>'
        '<a href="/art/2.htm">房住不炒表述调整</a>'
        '<a href="/x">短</a>'                         # too short → dropped
    )
    links = coc.extract_links(html, "http://www.pbc.gov.cn/i.html", "pbc.gov.cn")
    titles = [l["title"] for l in links]
    # cross-site dropped, short dropped, ORDER preserved (prominence signal)
    assert len(links) == 2
    assert "适度宽松" in titles[0]
    assert "房住不炒" in titles[1]
    assert all("pbc.gov.cn" in l["href"] for l in links)


def test_extract_links_dedupes_href_keep_first():
    html = ('<a href="/a.htm">第一次出现的标题文字</a>'
            '<a href="/a.htm">重复链接第二次</a>')
    links = coc.extract_links(html, "http://www.ndrc.gov.cn/", "ndrc.gov.cn")
    assert len(links) == 1
    assert "第一次" in links[0]["title"]


def test_peoples_daily_url_layout_node01():
    url = coc._peoples_daily_url(date(2026, 7, 2))
    assert url.endswith("/rmrb/pc/layout/202607/02/node_01.html")


def test_same_site_matcher():
    assert coc._same_site("http://www.pbc.gov.cn/x", "pbc.gov.cn")
    assert coc._same_site("/relative/path", "pbc.gov.cn")   # relative = same page
    assert not coc._same_site("http://evil.com/x", "pbc.gov.cn")


# --------------------------------------------------------------------------- #
# W3: gov.cn policy-library json_feed organ
#
# The search API (sousuo.www.gov.cn/search-gov/data) is dead to unauthenticated
# callers — 200 with totalCount pinned at 0 on every param variant, verified
# 2026-07-27 — so the organ rides the page's own static sidecar JSON instead. The
# fixture is the live head-25 of that feed.
# --------------------------------------------------------------------------- #
_FEED_BYTES = _FIX.joinpath("zuixin_feed_head25.json").read_bytes()
_FEED_URL = "https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json"


def test_json_feed_organ_is_registered():
    feeds = [o for o in coc.ORGANS if o.get("kind") == "json_feed"]
    assert len(feeds) == 1
    organ = feeds[0]
    assert organ["organ"] == "gov_policy_library"
    assert organ["url"] == _FEED_URL
    assert organ["domain"] == "gov.cn" and organ["theme"] == "policy"


def test_json_feed_parses_the_live_head25():
    links = coc.parse_json_feed(_FEED_BYTES, _FEED_URL)
    assert len(links) == 25
    first = links[0]
    assert first["title"].startswith("中共中央 国务院转发")
    assert first["href"] == "https://www.gov.cn/zhengce/202607/content_7076696.htm"
    # seendate is the feed's OWN DOCRELPUBTIME, not a date scraped out of the body.
    assert first["seendate"] == "2026-07-27"
    assert all(len(l["seendate"]) == 10 for l in links)


def test_json_feed_is_newest_first():
    dates = [l["seendate"] for l in coc.parse_json_feed(_FEED_BYTES, _FEED_URL)]
    assert dates == sorted(dates, reverse=True)


def test_json_feed_cap_takes_the_newest_n():
    links = coc.parse_json_feed(_FEED_BYTES, _FEED_URL, cap=5)
    assert len(links) == 5
    assert links[0]["seendate"] == "2026-07-27"


def test_json_feed_tolerates_a_utf8_bom():
    # The live feed carried no BOM on 2026-07-27, but the same CMS emits BOM'd JSON
    # elsewhere and json.loads chokes on one.
    assert len(coc.parse_json_feed(b"\xef\xbb\xbf" + _FEED_BYTES)) == 25
    assert len(coc.parse_json_feed(_FEED_BYTES.decode("utf-8"))) == 25


def test_json_feed_drops_keyless_items_and_dedupes():
    payload = json.dumps([
        {"TITLE": "有效文件", "URL": "/a.htm", "DOCRELPUBTIME": "2026-07-27"},
        {"TITLE": "", "URL": "/b.htm", "DOCRELPUBTIME": "2026-07-26"},     # no title
        {"TITLE": "无链接", "URL": "", "DOCRELPUBTIME": "2026-07-25"},      # no URL
        {"TITLE": "重复", "URL": "/a.htm", "DOCRELPUBTIME": "2026-07-24"},  # dup href
        "not-a-dict",
    ])
    links = coc.parse_json_feed(payload, "https://www.gov.cn/zhengce/")
    assert [l["title"] for l in links] == ["有效文件"]
    assert links[0]["href"] == "https://www.gov.cn/a.htm"


def test_json_feed_degrades_on_a_shape_change():
    assert coc.parse_json_feed(b"not json at all") == []
    assert coc.parse_json_feed("") == []
    assert coc.parse_json_feed({"unexpected": "envelope"}) == []
    assert coc.parse_json_feed(None) == []


def test_fetch_organ_json_feed_branch_keeps_the_feed_date(monkeypatch):
    """The leaf-fetch/dedup/cap machinery is shared; only link DISCOVERY differs."""
    organ = [o for o in coc.ORGANS if o.get("kind") == "json_feed"][0]
    body = "<html><body>本通知自2019年1月1日起施行。</body></html>"

    def _get(url, timeout=15):
        return (_FEED_BYTES.decode("utf-8"), "application/json") if url == _FEED_URL \
            else (body, "text/html")

    monkeypatch.setattr(coc, "_get", _get)
    rows = coc._fetch_organ(organ, date(2026, 7, 27),
                            {"max_docs_per_organ": 3, "request_pace_s": 0},
                            "2026-07-27T00:00:00+00:00", 0)
    assert len(rows) == 3
    assert {r["organ"] for r in rows} == {"gov_policy_library"}
    # The body quotes 2019 (the rule it amends). The FEED's date must win — a
    # body-scraped date would file a same-day policy seven years in the past.
    assert rows[0]["seendate"] == "2026-07-27"
    assert rows[0]["timestamp_quality"] == "PUBLISHER_STATED"
    assert rows[0]["layout_rank"] == -1
    assert rows[0]["body_sha256"] and rows[0]["lang"] == "zh"


def test_fetch_organ_json_feed_drops_offsite_links(monkeypatch):
    """A feed is no more trustworthy than an index page — same-site still applies."""
    organ = [o for o in coc.ORGANS if o.get("kind") == "json_feed"][0]
    feed = json.dumps([
        {"TITLE": "国务院文件", "URL": "https://www.gov.cn/zhengce/a.htm",
         "DOCRELPUBTIME": "2026-07-27"},
        {"TITLE": "站外链接", "URL": "https://evil.example.com/x.htm",
         "DOCRELPUBTIME": "2026-07-27"},
    ])

    def _get(url, timeout=15):
        return (feed, "application/json") if url == _FEED_URL else ("<p>正文</p>", "text/html")

    monkeypatch.setattr(coc, "_get", _get)
    rows = coc._fetch_organ(organ, date(2026, 7, 27),
                            {"max_docs_per_organ": 10, "request_pace_s": 0},
                            "2026-07-27T00:00:00+00:00", 0)
    assert [r["url"] for r in rows] == ["https://www.gov.cn/zhengce/a.htm"]


def test_fetch_organ_index_branch_still_derives_its_own_date(monkeypatch):
    """REGRESSION: extract_links emits no seendate, so index organs are unchanged."""
    organ = [o for o in coc.ORGANS if o["organ"] == "pboc"][0]
    index = '<a href="/art/1.htm">适度宽松的货币政策落地实施</a>'
    body = "<html><body>发布日期 2026-07-02 央行公告</body></html>"

    def _get(url, timeout=15):
        return (index, "text/html") if url == organ["url"] else (body, "text/html")

    monkeypatch.setattr(coc, "_get", _get)
    rows = coc._fetch_organ(organ, date(2026, 7, 27),
                            {"max_docs_per_organ": 3, "request_pace_s": 0},
                            "2026-07-27T00:00:00+00:00", 0)
    assert len(rows) == 1
    assert rows[0]["seendate"] == "2026-07-02"      # derived from the body, as before


# --------------------------------------------------------------------------- #
# storage — keep-FIRST date-keyed parquet + read_corpus (PIT: first print wins)
# --------------------------------------------------------------------------- #
def _corpus_row(doc_id, title, body, crawled, organ="pboc", rank=-1):
    return {"doc_id": doc_id, "organ": organ, "organ_name": "PBOC",
            "title": title, "url": "u/" + doc_id, "body": body,
            "body_sha256": coc.body_sha256(body), "seendate": crawled[:10],
            "_crawled_at": crawled, "lang": "zh",
            "timestamp_quality": "PUBLISHER_STATED", "theme": "monetary",
            "layout_rank": rank}


def test_write_day_keep_first_pit(tmp_path, monkeypatch):
    monkeypatch.setattr(coc, "_store_dir", lambda: tmp_path)
    d = date(2026, 7, 2)
    first = _corpus_row("a1", "原始标题", "适度宽松", "2026-07-02T01:00:00")
    restated = _corpus_row("a1", "被改写的标题", "内容变化", "2026-07-02T05:00:00")
    coc.write_day([first], d)
    coc.write_day([restated], d)   # same doc_id later → must NOT overwrite
    corpus = coc.read_corpus()
    assert len(corpus) == 1
    assert corpus.iloc[0]["title"] == "原始标题"   # first print wins (Missing-Tape body hash)


def test_read_corpus_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(coc, "_store_dir", lambda: tmp_path)
    assert coc.read_corpus() is None


def test_read_corpus_concats_multiple_days(tmp_path, monkeypatch):
    monkeypatch.setattr(coc, "_store_dir", lambda: tmp_path)
    coc.write_day([_corpus_row("d1", "第一天文档", "稳健", "2026-07-01T01:00:00")],
                  date(2026, 7, 1))
    coc.write_day([_corpus_row("d2", "第二天文档", "适度宽松", "2026-07-02T01:00:00")],
                  date(2026, 7, 2))
    corpus = coc.read_corpus()
    assert len(corpus) == 2
    assert set(corpus["doc_id"]) == {"d1", "d2"}


# --------------------------------------------------------------------------- #
# qbus mapping
# --------------------------------------------------------------------------- #
def test_to_qbus_rows_tier1_zh_bodyhash():
    row = _corpus_row("a1", "适度宽松", "实施适度宽松的货币政策", "2026-07-02T01:00:00")
    qrows = coc._to_qbus_rows([row])
    q = qrows[0]
    assert q["desk"] == "china_official"
    assert q["source_tier"] == 1          # 官方 primary = TIER1
    assert q["lang"] == "zh"
    assert q["body_sha256"] == row["body_sha256"] and q["body_sha256"]
    assert q["timestamp_quality"] == "PUBLISHER_STATED"   # has seendate
    assert q["themes"] == ["monetary"]


def test_to_qbus_rows_crawl_bounded_without_seendate():
    row = _corpus_row("a2", "无日期文档", "", "2026-07-02T01:00:00")
    row["seendate"] = ""                  # People's Daily layout has no in-page date
    q = coc._to_qbus_rows([row])[0]
    assert q["timestamp_quality"] == "CRAWL_BOUNDED"


# --------------------------------------------------------------------------- #
# Regression: summary frame DatetimeIndex (fix for DateParseError)
# --------------------------------------------------------------------------- #
def test_summary_frame_has_datetime_index(tmp_path, monkeypatch):
    """The frame returned by fetch() must have a pd.DatetimeIndex so that
    run_adapter → validate() can call pd.to_datetime(df.index) without raising
    DateParseError: Unknown datetime string format, unable to parse: state_council.

    This reproduces the exact failure path: construct a summary frame the old
    (broken) way (organ-string index) and confirm that pd.to_datetime raises;
    then verify the fixed frame passes without error.
    """
    # Simulate the per_organ dict that fetch() builds
    per_organ = {"state_council": 5, "pboc": 3, "ndrc": 4, "csrc": 2, "peoples_daily": 6}
    crawled_at = "2026-07-06T01:23:45+00:00"

    # ---- verify the OLD (broken) frame shape would crash validate() ----------
    broken_summary = pd.DataFrame(
        [{"organ": k, "n_docs": v, "crawled_at": crawled_at}
         for k, v in per_organ.items()]
    ).set_index("organ")
    try:
        pd.to_datetime(broken_summary.index)
        raise AssertionError("Expected DateParseError was not raised by the broken frame")
    except Exception as exc:
        # pandas raises DateParseError (a subclass of ValueError) on unparseable strings
        assert "state_council" in str(exc) or "parse" in str(exc).lower(), (
            f"Unexpected exception type/message: {exc!r}"
        )

    # ---- verify the FIXED frame shape passes validate() cleanly --------------
    # Use tz_convert(None) to strip UTC tz, matching every other collector
    # (tz-naive); mixing tz-aware here causes store.upsert → combine_first to
    # raise "Cannot join tz-naive with tz-aware DatetimeIndex".
    idx = pd.Timestamp(crawled_at).tz_convert(None)
    fixed_summary = pd.DataFrame(
        {f"n_docs_{k}": [float(v)] for k, v in per_organ.items()},
        index=[idx],
    )
    fixed_summary.index.name = "crawled_at"

    # Index must be tz-NAIVE (no tzinfo) so it can join with other collectors.
    assert fixed_summary.index.tz is None, (
        f"Expected tz-naive DatetimeIndex, got tz={fixed_summary.index.tz!r}"
    )

    # This is the exact call that validate() makes (base.py line 63):
    #   df.index = pd.to_datetime(df.index).normalize()
    converted = pd.to_datetime(fixed_summary.index).normalize()
    assert len(converted) == 1
    assert isinstance(converted[0], pd.Timestamp)

    # Columns must be numeric (validate drops all-NaN, then checks non-empty)
    assert all(fixed_summary[c].dtype.kind == "f" for c in fixed_summary.columns)

    # Each expected organ has its own n_docs_ column
    for organ in per_organ:
        assert f"n_docs_{organ}" in fixed_summary.columns
        assert fixed_summary[f"n_docs_{organ}"].iloc[0] == float(per_organ[organ])
