"""engine/china_news.py tests — deterministic theme-gate, flash filter, tone math.
No network, no akshare, no store writes.

Run: .venv/bin/python -m tests.test_china_news_engine
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_news as cn  # noqa: E402


def test_classify_theme() -> None:
    assert cn.classify_theme("央行宣布全面降准释放流动性") == "monetary"
    assert cn.classify_theme("11月CPI同比上涨0.2%") == "inflation"
    assert cn.classify_theme("社融数据大超市场预期") == "credit"
    assert cn.classify_theme("国常会部署稳增长一揽子政策") == "policy"
    assert cn.classify_theme("北向资金大幅净流入A股") == "markets"
    assert cn.classify_theme("China economy slows as retail sales miss forecasts") == "growth"
    assert cn.classify_theme("PBOC keeps loan prime rate steady") == "monetary"
    assert cn.classify_theme("Chinese stocks rally as CSI 300 breaks higher") == "markets"
    assert cn.classify_theme("某流量明星演唱会门票售罄") is None   # non-macro -> dropped


def test_filter_flashes_gate_dedup_recency_topn() -> None:
    items = [
        {"title": "央行开展逆回购操作", "summary": "投放流动性", "time": "2026-06-18 09:00", "url": "u1"},
        {"title": "娱乐圈八卦新闻", "summary": "与宏观无关", "time": "2026-06-18 10:00", "url": "u2"},
        {"title": "央行开展逆回购操作", "summary": "重复条目", "time": "2026-06-18 08:00", "url": "u3"},
        {"title": "统计局公布PPI数据", "summary": "工业品价格", "time": "2026-06-18 11:00", "url": "u4"},
    ]
    kept = cn.filter_flashes(items, {"max_show": 12})
    titles = [h["title"] for h in kept]
    assert "娱乐圈八卦新闻" not in titles          # non-macro gated out
    assert titles.count("央行开展逆回购操作") == 1   # deduped
    assert kept[0]["time"] == "2026-06-18 11:00"   # newest-first
    assert kept[0]["theme"] == "inflation" and any(h["theme"] == "monetary" for h in kept)

    assert len(cn.filter_flashes(items, {"max_show": 1})) == 1   # top-N cap


def test_enriched_flashes_importance_channels_and_tickers() -> None:
    items = [{
        "title": "人民银行发布金融统计报告 社融和贷款增长",
        "summary": "信贷扩张支撑银行板块",
        "time": "2026-06-12",
        "url": "https://example.com",
        "source": "official",
        "source_name": "PBoC",
        "source_tier": "official",
    }]
    h = cn.filter_flashes(items, {"max_show": 5})[0]
    assert h["importance"] == "high"
    assert h["importance_score"] >= 70
    assert "pboc_liquidity" in h["channels"]
    assert "credit_impulse" in h["channels"]
    assert "512800.SS" in h["tickers"]
    assert h["related_tickers"]


def test_english_wire_headline_gets_market_tags() -> None:
    items = [{
        "title": "Chinese stocks rally as PBOC liquidity and yuan support lift CSI 300",
        "summary": "",
        "time": "2026-06-20T12:00:00+00:00",
        "url": "https://example.com",
        "source": "gdelt",
        "source_name": "reuters.com",
        "source_tier": "wire",
    }]
    h = cn.filter_flashes(items, {"max_show": 5})[0]
    assert h["theme"] in {"monetary", "markets"}
    assert "pboc_liquidity" in h["channels"]
    assert "yuan" in h["channels"]
    assert "510300.SS" in h["tickers"]
    assert "CNY" in h["tickers"]
    assert "sourcelang:eng" in cn._gdelt_query({})


def test_china_synthesis_summarizes_channels_and_tickers() -> None:
    heads = cn.filter_flashes([{
        "title": "Chinese stocks rally as PBOC liquidity and yuan support lift CSI 300",
        "summary": "",
        "time": "2026-06-20T12:00:00+00:00",
        "url": "https://example.com",
        "source": "gdelt",
        "source_name": "reuters.com",
        "source_tier": "wire",
    }], {"max_show": 5})
    syn = cn._synthesis(heads)
    assert syn["high_impact_count"] >= 0
    assert syn["top_channels"]
    assert syn["top_tickers"]


def test_china_synthesis_top_channels_carry_bilingual_labels() -> None:
    """top_channels entries ship {name, count, label_en, label_zh} so channel
    chips render plain words in both languages (doctrine Law 2 — no raw slugs);
    `name` stays the raw slug for machine consumers."""
    heads = cn.filter_flashes([{
        "title": "Chinese stocks rally as PBOC liquidity and yuan support lift CSI 300",
        "summary": "",
        "time": "2026-06-20T12:00:00+00:00",
        "url": "https://example.com",
        "source": "gdelt",
        "source_name": "reuters.com",
        "source_tier": "wire",
    }], {"max_show": 5})
    syn = cn._synthesis(heads)
    assert syn["top_channels"]
    for ch in syn["top_channels"]:
        assert ch["name"]  # machine slug retained
        assert ch["count"] >= 1
        assert ch["label_en"] and "_" not in ch["label_en"]
        assert ch["label_zh"]
    # mapped slugs get a true ZH twin, not just de-underscored EN
    mapped = [ch for ch in syn["top_channels"] if ch["name"] in cn.CHANNEL_LABEL]
    assert mapped
    assert all(any("一" <= c <= "鿿" for c in ch["label_zh"]) for ch in mapped)
    # unmapped slugs de-underscore instead of leaking raw
    assert cn._slug_label("some_new_channel") == ("some new channel", "some new channel")


def test_china_synthesis_read_is_bilingual_and_deslugged() -> None:
    """read/read_zh are plain-word bilingual twins — no raw channel/tier slugs
    (doctrine Law 2: no untranslated slugs on user-facing surfaces)."""
    heads = cn.filter_flashes([{
        "title": "Chinese stocks rally as PBOC liquidity and yuan support lift CSI 300",
        "summary": "",
        "time": "2026-06-20T12:00:00+00:00",
        "url": "https://example.com",
        "source": "gdelt",
        "source_name": "reuters.com",
        "source_tier": "wire",
    }], {"max_show": 5})
    syn = cn._synthesis(heads)
    assert syn["read"] and "_" not in syn["read"]
    assert syn["read_zh"] and "_" not in syn["read_zh"]
    assert any("一" <= c <= "鿿" for c in syn["read_zh"])
    # source tiers render as plain words, not slug:count pairs
    assert ":" not in syn["read"]
    # structured fields keep raw slugs for machine consumers — unchanged contract
    assert syn["dominant_channel"] in cn.CHANNEL_LABEL
    # theme slugs (channel back-fill path) resolve through THEME_LABEL to real ZH
    assert cn._slug_label("monetary") == cn.THEME_LABEL["monetary"]
    # tier slugs de-slug too, mapped and unmapped alike
    assert cn._tier_label("china_native") == cn.TIER_LABEL["china_native"]
    assert cn._tier_label("brand_new_tier") == ("brand new tier", "brand new tier")
    # empty tape is bilingual too
    empty = cn._synthesis([])
    assert empty["read"] and empty["read_zh"]
    assert any("一" <= c <= "鿿" for c in empty["read_zh"])


def test_chinese_native_story_carries_zh_title_and_priority() -> None:
    items = [{
        "title": "上市公司密集启动增持回购 A股市场情绪回暖",
        "summary": "",
        "time": "2026-06-20T12:00:00+00:00",
        "url": "https://example.com/cn",
        "source": "cn_news_page",
        "source_name": "证券时报",
        "source_tier": "china_native",
        "source_lang": "zh",
    }, {
        "title": "Chinese stocks rally as PBOC liquidity lifts CSI 300",
        "summary": "",
        "time": "2026-06-20T13:00:00+00:00",
        "url": "https://example.com/en",
        "source": "news_rss",
        "source_name": "SCMP - China Economy",
        "source_tier": "global_wire",
        "source_lang": "en",
    }]
    kept = cn.filter_flashes(items, {"max_show": 5})
    assert kept[0]["source_tier"] == "china_native"
    assert kept[0]["title_zh"] == kept[0]["title"]


def test_tone_band_thresholds() -> None:
    assert cn._tone_band({"n": 120, "z": 0.8})[0] == "supportive"
    assert cn._tone_band({"n": 120, "z": -0.8})[0] == "cautious"
    assert cn._tone_band({"n": 120, "z": 0.1})[0] == "steady"
    assert cn._tone_band({"n": 5, "z": 2.0})[0] == "building"   # too little history
    assert cn._tone_band(None)[0] == "unknown"


def test_tone_stats_numeric() -> None:
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    rising = pd.Series([float(i) for i in range(30)], index=idx)
    s = cn._tone_stats(rising, window=90, smooth=5)
    assert s is not None and s["z"] > 0 and s["n"] == 30

    flat = pd.Series([1.0] * 30, index=idx)
    assert cn._tone_stats(flat, window=90, smooth=5)["z"] == 0.0

    assert cn._tone_stats(pd.Series([], dtype=float), 90, 5) is None


def test_row_to_item_column_drift() -> None:
    # akshare may label columns differently; the fuzzy mapper must still resolve them
    row = {"标题": "央行降息", "摘要": "下调政策利率", "发布时间": "2026-06-18 12:00", "链接": "x"}
    it = cn._row_to_item(row)
    assert it["title"] == "央行降息" and it["url"] == "x" and it["time"].startswith("2026")


def test_clean_time_rejects_title_and_url() -> None:
    # the two exact contaminated values reported on .cn-when
    g1 = ("证监会：五方面推动资本市场法治协同建设 "
          "https://www.cnstock.com/commonDetail/734410")
    g2 = ('人民币资产"圈粉"全球 财政部再发50亿欧元主权债券 要闻 · 人民币资产 06-27 '
          "https://www.cnstock.com/commonDetail/735099")
    assert cn._clean_time(g1, "证监会：五方面推动资本市场法治协同建设") == ""
    assert cn._clean_time(g2, '人民币资产"圈粉"全球 财政部再发50亿欧元主权债券') == ""
    # a bare URL with no title context is still rejected
    assert cn._clean_time("https://www.stcn.com/article/detail/3983723.html") == ""
    # genuine timestamps survive verbatim (whitespace-collapsed)
    assert cn._clean_time("2026-06-28 17:04:04") == "2026-06-28 17:04:04"
    assert cn._clean_time("2026-06-24T11:30:04+00:00") == "2026-06-24T11:30:04+00:00"
    assert cn._clean_time("2026-06-18") == "2026-06-18"
    assert cn._clean_time("06-28") == "06-28"
    assert cn._clean_time("") == ""


def test_parse_dateish_never_echoes_raw_input() -> None:
    # the bug: a title+href with no date used to be returned verbatim into `time`
    assert cn._parse_dateish("证监会：五方面推动 https://www.cnstock.com/x/1") == ""
    assert cn._parse_dateish("华泰证券：工业企业利润总体向好 行业分化加剧") == ""
    # a real date still resolves to a clean ISO day
    assert cn._parse_dateish("发布于 2026-06-18 09:00 来源：央行") == "2026-06-18"
    assert cn._parse_dateish("20260611 PPI") == "2026-06-11"


def test_enriched_time_is_clean_for_native_scraped_item() -> None:
    # native-page items historically dumped "<title> <href>" into time
    items = [{
        "title": "证监会：五方面推动资本市场法治协同建设",
        "summary": "",
        "time": ("证监会：五方面推动资本市场法治协同建设 "
                 "https://www.cnstock.com/commonDetail/734410"),
        "url": "https://www.cnstock.com/commonDetail/734410",
        "source": "cn_news_page", "source_name": "上海证券报",
        "source_tier": "china_native", "source_lang": "zh",
    }, {
        "title": "统计局公布5月PPI同比数据 工业品价格走势",
        "summary": "",
        "time": "2026-06-28 17:04:04",
        "url": "https://finance.eastmoney.com/a/1.html",
        "source": "eastmoney", "source_name": "Eastmoney",
        "source_tier": "domestic_wire", "source_lang": "zh",
    }]
    kept = {h["url"]: h for h in cn.filter_flashes(items, {"max_show": 12})}
    scraped = kept["https://www.cnstock.com/commonDetail/734410"]
    clean = kept["https://finance.eastmoney.com/a/1.html"]
    assert scraped["time"] == ""                       # no title / URL leaks through
    assert "http" not in scraped["time"]
    assert clean["time"] == "2026-06-28 17:04:04"      # real timestamp preserved


def test_clean_title_strips_breadcrumb_and_relative_time() -> None:
    # the two exact garbage titles reported on native CN sources (cnstock/yicai)
    g1 = '人民币资产"圈粉"全球 财政部再发50亿欧元主权债券 要闻 · 人民币资产 06-27'
    g2 = "下周外盘看点丨非农如何影响美联储加息… OPEC+月度会议召开。 10分钟前"
    assert cn._clean_title(g1) == '人民币资产"圈粉"全球 财政部再发50亿欧元主权债券'
    assert cn._clean_title(g2) == "下周外盘看点丨非农如何影响美联储加息… OPEC+月度会议召开。"
    # every relative-time / date suffix variant the task calls out
    assert cn._clean_title("央行开展逆回购操作 3小时前") == "央行开展逆回购操作"
    assert cn._clean_title("统计局公布PPI数据 昨天 15:30") == "统计局公布PPI数据"
    assert cn._clean_title("社融数据超预期 今天09:00") == "社融数据超预期"
    assert cn._clean_title("证监会发布新规 06-27 14:05") == "证监会发布新规"
    assert cn._clean_title("发改委部署稳增长 2026-06-27") == "发改委部署稳增长"
    # trailing "section · tail" breadcrumb (stcn-style) — any short label/tail
    assert cn._clean_title("拟收购光通信公司，SpaceX获批 聚焦 · SpaceX") == "拟收购光通信公司，SpaceX获批"
    assert cn._clean_title("创纪录！百亿级私募突破140家 基金 · 私募基金") == "创纪录！百亿级私募突破140家"
    assert cn._clean_title("太空算力真火，创企3个月融资已3轮 产业资讯 · 太空算力") == "太空算力真火，创企3个月融资已3轮"
    # leading section breadcrumb label is stripped from the front
    assert cn._clean_title("要闻 · A股放量上涨北向资金净流入") == "A股放量上涨北向资金净流入"
    # conservative: never touch mid-title text, hyphenated scores, or clean titles
    assert (cn._clean_title("上市公司密集启动增持回购 A股市场情绪回暖")
            == "上市公司密集启动增持回购 A股市场情绪回暖")
    assert cn._clean_title("中国队3-2险胜") == "中国队3-2险胜"   # glued digits kept
    assert cn._clean_title("PBOC keeps loan prime rate steady") == "PBOC keeps loan prime rate steady"
    assert cn._clean_title("") == ""


def test_decode_page_honors_document_charset() -> None:
    # sina's finance pages are served `text/html` with NO HTTP charset, so requests
    # falls back to ISO-8859-1 and r.text mojibakes the CJK (健康中国 -> "å¥åº·ä¸­å½").
    zh = "健康中国 上海自贸 央行开展逆回购操作释放流动性"
    mojibake = "健康中国".encode("utf-8").decode("latin-1")   # the exact reported garbage
    # UTF-8 page, header omits the charset -> must sniff the <meta charset>
    utf8 = ('<html><head><meta charset="utf-8"></head><body>'
            + zh + "</body></html>").encode("utf-8")
    assert zh in cn._decode_page(utf8, "text/html")
    assert mojibake not in cn._decode_page(utf8, "text/html")
    # GB2312/GBK page (the charset the task cites) round-trips via the gb18030 superset
    gbk = ('<html><head><meta http-equiv="Content-Type" '
           'content="text/html; charset=gb2312"></head><body>'
           + zh + "</body></html>").encode("gb18030")
    assert zh in cn._decode_page(gbk, "text/html")
    # an explicit HTTP charset wins over the document
    assert zh in cn._decode_page(zh.encode("utf-8"), "text/html; charset=utf-8")
    # unknown/garbage encoding degrades to replacement chars, never raises
    assert isinstance(cn._decode_page(b"\xff\xfe plain", "text/html; charset=bogus-enc"), str)


def test_concept_nav_links_dropped() -> None:
    # vip.stock.finance.sina.com.cn/mkt/#chgn_* / #gn_* are board-nav hubs, not stories
    assert cn._is_concept_nav_link("https://vip.stock.finance.sina.com.cn/mkt/#chgn_jkzg")
    assert cn._is_concept_nav_link("https://vip.stock.finance.sina.com.cn/mkt/#gn_shzm")
    assert cn._is_concept_nav_link("http://vip.stock.finance.sina.com.cn/mkt#hangye_ZB01")
    # real sina news stories and the section landing page are kept
    assert not cn._is_concept_nav_link(
        "https://finance.sina.com.cn/stock/relnews/cn/2026-06-28/doc-abc.shtml")
    assert not cn._is_concept_nav_link("https://finance.sina.com.cn/stock/")
    assert not cn._is_concept_nav_link("https://vip.stock.finance.sina.com.cn/mkt/#")  # no real board
    assert not cn._is_concept_nav_link("not a url")


def test_panel_importable() -> None:
    # the build_china entrypoint just calls cn.panel(); make sure it exists/imports
    assert callable(cn.panel) and callable(cn.policy_tone) and callable(cn.flash_headlines)


def test_official_pages_write_clean_time(tmp_path: Path = None) -> None:
    """_fetch_official_pages must sanitise `time` at the cache WRITE path, not only at
    read/display time.  Without the write-path guard, a corrupted time value (HTML page
    content leaked into the date field) can persist in the cache until the next TTL cycle.
    This is the audit finding §PIT-write-guard."""
    import json
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    tmp = Path(tempfile.mkdtemp())
    # Minimal cfg that points cache at our tmp dir
    cfg = {
        "official_cache_dir": str(tmp),
        "official_window_days": 45,
        "use_official_pages": True,
    }

    # Build a fake soup <a> whose parent text concatenates the title+href into "when",
    # which is what _parse_dateish used to return verbatim (now returns "" for URLs).
    # We inject it by patching _parse_dateish to deliberately return a contaminated string
    # that _clean_time must strip before the cache write.
    contaminated_time = ("证监会推动资本市场法治协同建设 "
                         "https://www.cnstock.com/commonDetail/734410")

    class FakeA:
        def __init__(self):
            self.attrs = {"href": "/commonDetail/734410"}
            self._text = "证监会推动资本市场法治协同建设"
            self.parent = None
        def get_text(self, sep="", strip=False):  # noqa: D401
            return self._text
        def __getitem__(self, key):
            return self.attrs[key]

    class FakeSoup:
        def find_all(self, tag, **_kw):
            return [FakeA()]

    mock_r = MagicMock()
    mock_r.status_code = 200
    mock_r.text = "<html/>"

    pages = [{"url": "https://www.cnstock.com/", "name": "cnstock", "tier": "official",
               "theme": "policy"}]

    with (patch("engine.china_news._parse_dateish", return_value=contaminated_time),
          patch("engine.china_news.classify_theme", return_value="policy"),
          patch("engine.china_news._clean_title",
                return_value="证监会推动资本市场法治协同建设"),
          patch("engine.china_news._official_cache_path",
                return_value=tmp / "official.json"),
          patch("requests.get", return_value=mock_r),
          patch("bs4.BeautifulSoup", return_value=FakeSoup())):
        items, _ = cn._fetch_official_pages({**cfg, "official_pages": pages})

    # The write-path guard must have stripped the contaminated time before persisting
    cached = json.loads((tmp / "official.json").read_text())
    for item in cached["items"]:
        assert "http" not in item.get("time", ""), (
            f"Contaminated time persisted to cache: {item['time']!r}")
    # The in-memory return value is also clean (it uses the sanitised list)
    for item in items:
        assert "http" not in item.get("time", ""), (
            f"Contaminated time returned from fetch: {item['time']!r}")


if __name__ == "__main__":
    tests = [
        test_classify_theme,
        test_filter_flashes_gate_dedup_recency_topn,
        test_enriched_flashes_importance_channels_and_tickers,
        test_english_wire_headline_gets_market_tags,
        test_china_synthesis_summarizes_channels_and_tickers,
        test_chinese_native_story_carries_zh_title_and_priority,
        test_tone_band_thresholds,
        test_tone_stats_numeric,
        test_row_to_item_column_drift,
        test_clean_time_rejects_title_and_url,
        test_parse_dateish_never_echoes_raw_input,
        test_enriched_time_is_clean_for_native_scraped_item,
        test_clean_title_strips_breadcrumb_and_relative_time,
        test_decode_page_honors_document_charset,
        test_concept_nav_links_dropped,
        test_panel_importable,
        test_official_pages_write_clean_time,
    ]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print("all china_news engine tests passed")
