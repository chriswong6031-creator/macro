"""cn_newswires — pure-parser contracts + cached fetch + page/intel integration.

Fixtures are trimmed REAL payloads (live-probed 2026-07-10) from the three vendors'
keyless JSON endpoints. No network: parsers are pure; fetch paths are monkeypatched.
"""
from __future__ import annotations

import json

from engine import cn_newswires as nw

# --------------------------------------------------------------------------- #
# trimmed real payloads
# --------------------------------------------------------------------------- #
WSCN_PAYLOAD = {
    "code": 20000,
    "data": {"items": [
        {"title": "", "content_text": "卡塔尔称伊朗与美国落实谅解备忘录很重要。（半岛电视台）",
         "display_time": 1783685831, "uri": "https://wallstreetcn.com/livenews/3132073",
         "id": 3132073, "score": 1, "channels": ["global-channel"]},
        {"title": "", "content_text": "【央行公告】央行今日开展1000亿元7天逆回购操作，中标利率持平。",
         "display_time": 1783685900, "uri": "https://wallstreetcn.com/livenews/3132099",
         "id": 3132099, "score": 2, "channels": ["global-channel"]},
    ]},
}

JIN10_JS = (
    'var newest = ['
    '{"id":"20260710201418","time":"2026-07-10 20:14:18","type":0,"important":1,'
    '"data":{"pic":"","title":"","source":"",'
    '"content":"【知情人士：卡塔尔代表已抵达伊朗 开展紧急斡旋】金十数据7月10日讯，据路透社报道，卡塔尔谈判代表已抵达伊朗。",'
    '"source_link":""}},'
    '{"id":"20260710201355","time":"2026-07-10 20:13:55","type":1,'
    '"data":{"pic":"chart.png","content":""}},'
    '{"id":"20260710201348","time":"2026-07-10 20:13:48","type":0,"important":0,'
    '"data":{"title":null,"content":"俄罗斯国家原子能公司：伊朗布什尔核电站首批6名员工已开始返回核电站。","source_link":""}}'
    '];'
)

GLH_PAYLOAD = {
    "statusCode": 200,
    "result": [
        {"id": 2547236, "title": "",
         "content": "格隆汇7月10日｜国际原子能机构总干事格罗西：我们正在监测伊朗布什尔核电站的情况，并呼吁各方保持克制。",
         "createTime": 1783685797, "link": None, "stockList": None},
    ],
}

_CONTRACT_KEYS = {"title", "summary", "time", "url", "source", "source_name",
                  "domain", "source_lang", "wire_important"}


# --------------------------------------------------------------------------- #
# per-source parsers
# --------------------------------------------------------------------------- #
def test_parse_wallstreetcn_contract_and_bracket_title():
    items = nw.parse_wallstreetcn(WSCN_PAYLOAD)
    assert len(items) == 2
    assert all(_CONTRACT_KEYS <= set(it) for it in items)
    plain, bracketed = items
    assert plain["title"].startswith("卡塔尔称")
    assert plain["source_lang"] == "zh" and plain["domain"] == "wallstreetcn.com"
    assert plain["wire_important"] is False
    # 【标题】 bracket becomes the title; score>=2 flags vendor-important
    assert bracketed["title"] == "央行公告"
    assert bracketed["summary"].startswith("央行今日")
    assert bracketed["wire_important"] is True
    # epoch -> tz-aware ISO the page ranker can parse for freshness
    assert plain["time"].endswith("+00:00") and plain["time"].startswith("2026-")


def test_parse_jin10_skips_non_text_and_stamps_beijing_tz():
    items = nw.parse_jin10(JIN10_JS)
    assert len(items) == 2                      # type==1 chart row dropped
    first, second = items
    assert first["title"] == "知情人士：卡塔尔代表已抵达伊朗 开展紧急斡旋"
    assert first["wire_important"] is True
    assert first["time"] == "2026-07-10T20:14:18+08:00"
    assert first["url"] == "https://flash.jin10.com/detail/20260710201418"
    assert second["wire_important"] is False
    assert all(it["source"] == "jin10" and it["source_name"] == "金十数据" for it in items)


def test_parse_gelonghui_strips_dateline_prefix():
    items = nw.parse_gelonghui(GLH_PAYLOAD)
    assert len(items) == 1
    it = items[0]
    assert it["title"].startswith("国际原子能机构总干事")     # 格隆汇7月10日｜ stripped
    assert it["url"] == "https://www.gelonghui.com/live/2547236"
    assert it["source_lang"] == "zh"


def test_parsers_degrade_on_garbage():
    assert nw.parse_wallstreetcn({}) == []
    assert nw.parse_wallstreetcn({"data": {"items": ["junk", {"content_text": ""}]}}) == []
    assert nw.parse_jin10("") == []
    assert nw.parse_jin10("var newest = not-json;") == []
    assert nw.parse_gelonghui({"result": None}) == []


def test_split_flash_paths():
    assert nw._split_flash("【标题在这里啊】正文部分。") == ("标题在这里啊", "正文部分。")
    t, s = nw._split_flash("央行今日开展1000亿元逆回购操作。市场利率持平于上日水平。")
    assert t == "央行今日开展1000亿元逆回购操作" and s.startswith("央行今日")
    t, s = nw._split_flash("短句无句号")
    assert t == "短句无句号" and s == ""


# --------------------------------------------------------------------------- #
# cached fetch — never raises, cache round-trips, disabled -> []
# --------------------------------------------------------------------------- #
def test_fetch_all_cache_and_degrade(tmp_path, monkeypatch):
    cfg = {"enabled": True, "sources": ["wallstreetcn"], "max_per_source": 10,
           "cache_dir": str(tmp_path / "wires"), "cache_ttl_hours": 6}
    calls = {"n": 0}

    def fake_fetch_one(name, cap, timeout=15):
        calls["n"] += 1
        return nw.parse_wallstreetcn(WSCN_PAYLOAD, cap)

    monkeypatch.setattr(nw, "_fetch_one", fake_fetch_one)
    first = nw.fetch_all(cfg)
    assert len(first) == 2 and calls["n"] == 1
    # second call is served from the day cache — no refetch
    monkeypatch.setattr(nw, "_fetch_one",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    second = nw.fetch_all(cfg)
    assert second == first and calls["n"] == 1
    assert nw.fetch_all({"enabled": False}) == []


def test_fetch_one_degrades_to_empty(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise OSError("no network in tests")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert nw._fetch_one("wallstreetcn", 10) == []
    assert nw._fetch_one("nonexistent-wire", 10) == []


# --------------------------------------------------------------------------- #
# page-panel integration (engine/china_news.py)
# --------------------------------------------------------------------------- #
def test_page_fetch_cn_wires_maps_to_candidate_shape(monkeypatch):
    from engine import china_news as cn
    monkeypatch.setattr(nw, "fetch_all",
                        lambda cfg=None, today=None: nw.parse_jin10(JIN10_JS))
    items, reason = cn._fetch_cn_wires({"use_cn_json_wires": True})
    assert reason is None and len(items) == 2
    it = items[0]
    assert it["source"] == "cn_wire" and it["source_tier"] == "china_native"
    assert it["source_lang"] == "zh" and it["source_name"] == "金十数据"
    # tier weight: native Chinese financial source (+24) — the page ranker input
    assert cn._source_weight(it["source_tier"], it["source_name"], it["source"])[0] == 24


def test_page_cn_wire_requires_theme_gate():
    """High-volume wires never bypass the macro-theme gate on tier alone."""
    from engine import china_news as cn
    kept = cn.filter_flashes([
        {"title": "某明星综艺节目今晚开播引发热议", "summary": "", "url": "https://flash.jin10.com/detail/1",
         "time": "2026-07-10T20:00:00+08:00", "source": "cn_wire",
         "source_name": "金十数据", "source_tier": "china_native", "source_lang": "zh"},
        {"title": "央行今日开展1000亿元7天逆回购操作 中标利率持平", "summary": "", "url": "https://flash.jin10.com/detail/2",
         "time": "2026-07-10T20:01:00+08:00", "source": "cn_wire",
         "source_name": "金十数据", "source_tier": "china_native", "source_lang": "zh"},
    ], {"max_show": 10, "min_importance_score": 34})
    titles = [h["title"] for h in kept]
    assert any("逆回购" in t for t in titles)
    assert not any("综艺" in t for t in titles)


def test_digest_urls_dropped_and_native_leads():
    from engine import china_news as cn
    # SCMP /plus/ newsletter digest packs multi-story hi-impact terms — must be dropped
    assert cn._is_digest_url("https://www.scmp.com/plus/tech/article/1?utm_source=rss")
    kept = cn.filter_flashes([
        {"title": "Nvidia gets China boost, Iran ceasefire breaks, GDP release",
         "summary": "", "url": "https://www.scmp.com/plus/tech/article/1",
         "time": "2026-07-10T10:00:00+00:00", "source": "news_rss",
         "source_name": "SCMP - China Economy", "source_tier": "global_wire", "source_lang": "en"},
        {"title": "China GDP growth beats expectations in Q2",
         "summary": "", "url": "https://www.scmp.com/economy/article/2",
         "time": "2026-07-10T10:00:00+00:00", "source": "news_rss",
         "source_name": "SCMP - China Economy", "source_tier": "global_wire", "source_lang": "en"},
        {"title": "央行宣布降准0.5个百分点 释放长期资金约1万亿元",
         "summary": "", "url": "https://flash.jin10.com/detail/3",
         "time": "2026-07-10T18:00:00+08:00", "source": "cn_wire",
         "source_name": "金十数据", "source_tier": "china_native", "source_lang": "zh"},
    ], {"max_show": 10, "min_importance_score": 34})
    urls = [h["url"] for h in kept]
    assert "https://www.scmp.com/plus/tech/article/1" not in urls        # digest dead
    assert "https://www.scmp.com/economy/article/2" in urls              # real story kept
    # native_lead: the hero slot is the Chinese-native story
    lead = cn._promote_native_lead(kept)[0]
    assert lead["source_lang"] == "zh" and "降准" in lead["title"]


def test_promote_native_lead_noop_when_no_zh():
    from engine import china_news as cn
    rows = [{"title": "a", "source_lang": "en"}, {"title": "b", "source_lang": "en"}]
    assert cn._promote_native_lead(list(rows)) == rows
    assert cn._promote_native_lead([]) == []


def test_china_anchor_neutralizes_foreign_institutions():
    from engine import china_news as cn
    # foreign central banks / regulators do NOT anchor …
    assert not cn._is_china_anchored("英国央行提议放宽部分银行资本规则")
    assert not cn._is_china_anchored("波兰央行委员Kotecki：有理由考虑今年晚些时候降息")
    assert not cn._is_china_anchored("巴西统计局公布6月CPI环比上涨0.16%")
    # a foreign story borrowing a bare institution token (UK's HM Treasury as
    # 财政部) must not anchor either — weak tokens die in foreign context
    assert not cn._is_china_anchored(
        "英国金融行为监管局（FCA）：英国央行、审慎监管局将开展监管。财政部已将AWS指定为关键第三方机构。")
    # … the Chinese ones (and plain China anchors) DO
    assert cn._is_china_anchored("央行今日开展1000亿元7天逆回购操作")
    assert cn._is_china_anchored("财政部再次紧急预拨8000万元中央自然灾害救灾资金")
    assert cn._is_china_anchored("证监会：依法从严打击各类跨境违法违规行为")
    assert cn._is_china_anchored("China's factory gate prices rise in June")
    # mixed China-vs-foreign story: the strong anchor wins
    assert cn._is_china_anchored("中美经贸磋商：美国财政部代表将访华")


def test_hero_prefers_china_anchored_zh_over_global_relay():
    from engine import china_news as cn
    kept = [
        {"title": "英国央行提议放宽部分银行资本规则", "summary": "", "source_lang": "zh"},
        {"title": "美股三大指数集体收涨", "summary": "", "source_lang": "en"},
        {"title": "央行宣布降准0.5个百分点", "summary": "", "source_lang": "zh"},
    ]
    lead = cn._promote_native_lead(list(kept))[0]
    assert "降准" in lead["title"]                       # anchored zh beats unanchored zh
    # fallback: no anchored zh at all -> best zh still leads
    lead2 = cn._promote_native_lead([kept[1], kept[0]])[0]
    assert lead2["title"].startswith("英国央行")


def test_off_china_wire_relay_ranks_below_china_story():
    from engine import china_news as cn
    hi, _, _ = cn._importance("央行今日开展1000亿元7天逆回购操作", "", "monetary",
                              "china_native", "金十数据", "cn_wire")
    lo, _, reasons = cn._importance("波兰央行委员：有理由考虑今年晚些时候降息", "", "monetary",
                                    "china_native", "金十数据", "cn_wire")
    assert hi > lo
    assert "global macro relay (non-China)" in reasons


def test_cross_wire_near_dup_collapses():
    from engine import china_news as cn
    kept = cn.filter_flashes([
        {"title": "波兰央行委员：有理由考虑今年晚些时候降息 通胀预期回落支持宽松",
         "summary": "", "url": "https://www.gelonghui.com/live/1",
         "time": "2026-07-10T20:00:00+08:00", "source": "cn_wire",
         "source_name": "格隆汇", "source_tier": "china_native", "source_lang": "zh"},
        {"title": "波兰央行委员Kotecki：有理由考虑今年晚些时候降息 通胀预期回落支持宽松",
         "summary": "", "url": "https://flash.jin10.com/detail/2",
         "time": "2026-07-10T20:01:00+08:00", "source": "cn_wire",
         "source_name": "金十数据", "source_tier": "china_native", "source_lang": "zh"},
    ], {"max_show": 10, "min_importance_score": 20})
    assert len(kept) == 1                                # near-dup collapsed, first wins
    assert kept[0]["source_name"] == "格隆汇"


# --------------------------------------------------------------------------- #
# intel-bus integration (engine/china_news_intel.py)
# --------------------------------------------------------------------------- #
def test_intel_json_wires_and_timestamp_quality(monkeypatch):
    from engine import china_news_intel as ni
    monkeypatch.setattr(nw, "fetch_all",
                        lambda cfg=None, today=None: nw.parse_gelonghui(GLH_PAYLOAD))
    items = ni._fetch_json_wires({"use_json_wires": True})
    assert len(items) == 1 and items[0]["source"] == "gelonghui"
    assert ni._fetch_json_wires({"use_json_wires": False}) == []
    # vendor sub-minute stamps are publisher-stated in the qbus PIT contract
    assert ni._timestamp_quality("2026-07-10T20:14:18+08:00", "jin10") == "PUBLISHER_STATED"
    assert ni._timestamp_quality("2026-07-10T20:16:37+00:00", "wallstreetcn") == "PUBLISHER_STATED"
    assert ni._timestamp_quality("2026-07-10 20:14", "em") == "SNAPSHOT_DATE"
    assert ni._timestamp_quality("", "jin10") == "CRAWL_BOUNDED"
    # tier: all three wires resolve tier 2 off the ONE qkernel table
    for src, dom in (("wallstreetcn", "wallstreetcn.com"), ("jin10", "jin10.com"),
                     ("gelonghui", "gelonghui.com")):
        assert ni.source_tier(src, dom) == 2


def test_json_wire_items_survive_build_records():
    """End-to-end shape check: cn_newswires items -> intel build_records rows."""
    from engine import china_news_intel as ni
    raw = nw.parse_wallstreetcn(WSCN_PAYLOAD) + nw.parse_jin10(JIN10_JS)
    recs = ni.build_records(raw, {}, "2026-07-10T13:00:00+00:00")
    assert recs, "at least the 逆回购 monetary flash must pass the theme gate"
    r = next(rec for rec in recs if "逆回购" in (rec["title"] + rec["summary"]))
    assert r["source"] == "wallstreetcn" and r["source_tier"] == 2
    assert r["theme"] == "monetary"
    assert r["seendate"].startswith("2026-")
