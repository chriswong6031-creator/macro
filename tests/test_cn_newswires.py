"""cn_newswires — pure-parser contracts + cached fetch + page/intel integration.

Fixtures are trimmed REAL payloads (live-probed 2026-07-10) from the three vendors'
keyless JSON endpoints. No network: parsers are pure; fetch paths are monkeypatched.
The W3 wires (futu, ths) are pinned against the FULL captured payloads committed at
tests/fixtures/cn_newswires/ (live-probed 2026-07-27), not inline excerpts.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine import cn_newswires as nw

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cn_newswires"


def _fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))

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


# --------------------------------------------------------------------------- #
# W3 wires 4/5 — futu (富途牛牛) + ths (同花顺), pinned on the committed captures
# --------------------------------------------------------------------------- #
def test_parse_futu_flash_contract_and_empty_title_fallback():
    items = nw.parse_futu_flash(_fixture("futu_flash.json"))
    assert len(items) == 10                                  # every captured row survives
    assert all(_CONTRACT_KEYS == set(it) for it in items)
    assert all(it["source"] == "futu" and it["source_name"] == "富途牛牛"
               and it["domain"] == "news.futunn.com" for it in items)
    # the wire ships title="" on 9 of 10 rows — the content head IS the headline
    first = items[0]
    assert first["title"] == "美国原油期货结算价为每桶82.61美元，下跌6.70美元，跌幅7.50%"
    assert first["summary"].startswith("美国原油期货结算价")
    assert first["source_lang"] == "zh"
    # epoch-second STRING -> tz-aware ISO the freshness ranker can parse
    assert first["time"] == "2026-07-27T18:33:29+00:00"
    assert first["url"].startswith("https://news.futunn.com/flash/20558030/")
    # the one row that DOES carry a vendor title keeps it (long body stays the summary)
    titled = next(it for it in items if it["title"].startswith("伊拉克政府已就"))
    assert titled["summary"].startswith("当地时间27日晚")


def test_futu_level_flag_is_int_not_string():
    """`level` arrives as a JSON int — an `== "0"` string test would flag all 10 rows.

    The captured page carries level=0 on nine rows and level=1 on exactly one.
    """
    items = nw.parse_futu_flash(_fixture("futu_flash.json"))
    assert sum(it["wire_important"] for it in items) == 1
    assert nw.parse_futu_flash(
        {"data": {"data": {"news": [{"content": "央行开展1000亿元逆回购操作。",
                                     "time": "1785177209", "level": 0}]}}}
    )[0]["wire_important"] is False
    assert nw.parse_futu_flash(
        {"data": {"data": {"news": [{"content": "央行开展1000亿元逆回购操作。",
                                     "time": "1785177209", "level": 1}]}}}
    )[0]["wire_important"] is True


def test_parse_ths_push_contract_and_import_flag():
    items = nw.parse_ths_push(_fixture("ths_push.json"))
    assert len(items) == 20
    assert all(_CONTRACT_KEYS == set(it) for it in items)    # `tag` deliberately dropped
    assert all(it["source"] == "ths" and it["source_name"] == "同花顺"
               and it["domain"] == "10jqka.com.cn" for it in items)
    first = items[0]
    assert first["title"] == "摩根士丹利：投资者在美联储议息会议前增加美元多仓"
    assert first["summary"].startswith("摩根士丹利策略师援引数据称")   # digest -> summary
    assert first["time"] == "2026-07-27T18:41:29+00:00"              # ctime epoch-s
    assert first["url"] == "https://news.10jqka.com.cn/20260728/c678468195.shtml"
    # `import` is a STRING and the captured page carries "0" x19 and "3" x1 — NO "1".
    # An `== "1"` mapping would ship the flag permanently dead and review clean.
    assert sum(it["wire_important"] for it in items) == 1
    flagged = next(it for it in items if it["wire_important"])
    assert flagged["title"].startswith("国际原油期货跌幅扩大")
    assert nw._vendor_flag("0") is False and nw._vendor_flag("") is False
    assert nw._vendor_flag(None) is False and nw._vendor_flag("3") is True


def test_new_wires_degrade_on_garbage():
    for bad in ({}, {"data": None}, {"data": {"data": None}},
                {"data": {"data": {"news": ["junk", {"content": ""}]}}}):
        assert nw.parse_futu_flash(bad) == []
    for bad in ({}, {"data": None}, {"data": {"list": None}},
                {"data": {"list": ["junk", {"title": "", "digest": ""}]}}):
        assert nw.parse_ths_push(bad) == []


def test_ths_source_entry_carries_the_required_referer(monkeypatch):
    """Without the Referer the THS server drops the connection (empty reply, not a
    status code you can see). The per-source header must reach the actual Request."""
    assert nw._SOURCES["ths"]["headers"]["Referer"] == \
        "https://news.10jqka.com.cn/realtimenews.html"

    seen: dict = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(_fixture("ths_push.json")).encode()

    def fake_urlopen(req, timeout=None):
        seen["headers"] = dict(req.headers)
        seen["url"] = req.full_url
        return _Resp()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    items = nw._fetch_one("ths", 80)
    assert len(items) == 20
    # urllib title-cases header keys on the Request object
    assert seen["headers"]["Referer"] == "https://news.10jqka.com.cn/realtimenews.html"
    assert seen["headers"]["User-agent"] == nw._UA        # UA survives the merge
    assert seen["url"] == "https://news.10jqka.com.cn/tapp/news/push/stock"
    # a source WITHOUT per-source headers must NOT inherit the THS Referer
    nw._fetch_one("gelonghui", 80)
    assert "Referer" not in seen["headers"]
    assert seen["headers"]["User-agent"] == nw._UA


def test_config_sources_are_all_registered_wires():
    """Every wire named in config.yml must exist in the registry (and vice-versa for
    the W3 additions) — a config key with no parser degrades to silence, not an error."""
    from lib import config
    names = list((config.load().get("cn_newswires") or {}).get("sources") or [])
    assert {"futu", "ths"} <= set(names)
    assert all(n in nw._SOURCES for n in names), \
        f"config names a wire with no parser: {sorted(set(names) - set(nw._SOURCES))}"


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
    assert it["wire_important"] is True and items[1]["wire_important"] is False
    # tier weight: native Chinese financial source (+24) — the page ranker input
    assert cn._source_weight(it["source_tier"], it["source_name"], it["source"])[0] == 24


def test_wire_important_flag_boosts_importance():
    from engine import china_news as cn
    base, _, _ = cn._importance("央行今日开展1000亿元7天逆回购操作", "", "monetary",
                                "china_native", "金十数据", "cn_wire")
    boosted, _, reasons = cn._importance("央行今日开展1000亿元7天逆回购操作", "", "monetary",
                                         "china_native", "金十数据", "cn_wire",
                                         wire_important=True)
    assert boosted == base + 8
    assert "wire-flagged high impact" in reasons
    # the boost rides BEFORE the off-China damp: a flagged foreign flash stays context
    fb, _, fr = cn._importance("波兰央行委员：有理由考虑今年晚些时候降息", "", "monetary",
                               "china_native", "金十数据", "cn_wire", wire_important=True)
    fu, _, _ = cn._importance("波兰央行委员：有理由考虑今年晚些时候降息", "", "monetary",
                              "china_native", "金十数据", "cn_wire")
    assert fu < fb < base and "global macro relay (non-China)" in fr


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
    # vendor red-flag persists into the PIT record (wscn score>=2 on this fixture)
    assert r["wire_important"] is True


def test_accrue_backfills_wire_important_on_old_schema():
    """Pre-migration parquet rows (no wire_important column) merge cleanly: the
    column materializes as bool with unknown=False, never object-with-NaN."""
    import pandas as pd
    from engine import china_news_intel as ni
    old = pd.DataFrame([{c: "x" for c in ni._COLUMNS if c != "wire_important"}])
    old["event_id"] = "old1"
    recs = ni.build_records(nw.parse_jin10(JIN10_JS), {}, "2026-07-10T13:00:00+00:00")
    merged = ni.accrue(old, recs)
    assert merged["wire_important"].dtype == bool
    assert merged.loc[merged.event_id == "old1", "wire_important"].item() is False
    assert bool(merged["wire_important"].any())      # the flagged jin10 row survived


def test_w3_wires_rank_china_native_on_the_page(monkeypatch):
    """Native-first ranking law: futu/ths must reach the page ranker at the SAME
    china_native tier (+24) as the three W1 wires, not fall through to a default."""
    from engine import china_news as cn
    monkeypatch.setattr(
        nw, "fetch_all",
        lambda cfg=None, today=None: (nw.parse_futu_flash(_fixture("futu_flash.json"))
                                      + nw.parse_ths_push(_fixture("ths_push.json"))))
    items, reason = cn._fetch_cn_wires({"use_cn_json_wires": True})
    assert reason is None and len(items) == 30
    by_name = {it["source_name"] for it in items}
    assert by_name == {"富途牛牛", "同花顺"}
    for it in items:
        assert it["source_tier"] == "china_native" and it["source"] == "cn_wire"
        assert cn._source_weight(it["source_tier"], it["source_name"], it["source"])[0] == 24


def test_w3_wires_are_tier2_publisher_stated_on_the_intel_bus():
    """qbus PIT contract: both new wires carry vendor epoch stamps (sub-minute), and
    both resolve tier 2 off the ONE qkernel table."""
    from engine import china_news_intel as ni
    assert ni._timestamp_quality("2026-07-27T18:33:29+00:00", "futu",
                                 "news.futunn.com") == "PUBLISHER_STATED"
    assert ni._timestamp_quality("2026-07-27T18:41:29+00:00", "ths",
                                 "10jqka.com.cn") == "PUBLISHER_STATED"
    assert ni._timestamp_quality("", "futu", "news.futunn.com") == "CRAWL_BOUNDED"
    for src, dom in (("futu", "news.futunn.com"), ("ths", "10jqka.com.cn")):
        assert ni.source_tier(src, dom) == 2


def test_akshare_futu_ths_rows_keep_their_day_resolution_label():
    """SLUG COLLISION GUARD (kept live after the config change below): _fetch_wires
    strips 'stock_info_global_' to the SAME 'futu'/'ths' slug the direct wires use, so
    a day-resolution akshare row must never be relabelled sub-minute. The domain is
    what separates them, and this stays pinned because the akshare leg is the standing
    CNH-R2 fallback — it is one config line away from being live again."""
    from engine import china_news_intel as ni
    assert ni._timestamp_quality("2026-07-27 18:33", "futu", "") == "SNAPSHOT_DATE"
    assert ni._timestamp_quality("2026-07-27 18:41", "ths", "") == "SNAPSHOT_DATE"


def test_futu_ths_are_not_polled_twice_through_akshare():
    """REVIEW F9 — one vendor, one leg.

    config.yml used to name akshare's stock_info_global_futu / _ths ALONGSIDE the
    direct cn_newswires futu/ths wires. Both legs strip to the same slug, so the bus
    ingested each vendor twice — the akshare copy at day resolution, the direct copy
    at the second — and only the domain field told them apart. The direct wires are
    strictly better (publisher-stated stamps), so the akshare pair is retired to a
    documented CNH-R2 fallback.
    """
    from lib import config
    cfg = config.load()
    wire_sources = (cfg.get("china_news_intel") or {}).get("wire_sources") or []
    stripped = {str(f).replace("stock_info_global_", "") for f in wire_sources}
    assert not ({"futu", "ths"} & stripped), (
        "futu/ths are polled on the direct cn_newswires leg — the akshare copies "
        "duplicate every item into the intel bus")
    assert stripped == {"em", "sina"}
    # the direct leg is the one that carries them, and it still does
    assert {"futu", "ths"} <= set((cfg.get("cn_newswires") or {}).get("sources") or [])


def test_qbus_row_passes_the_domain_into_timestamp_quality():
    """The disambiguation only works if the caller actually forwards the domain."""
    from engine import china_news_intel as ni
    direct = nw.parse_ths_push(_fixture("ths_push.json"))[:2]
    recs = ni.build_records(direct, {}, "2026-07-27T13:00:00+00:00")
    rows = ni._build_qbus_rows(recs, direct, "2026-07-27T13:00:00+00:00")
    assert rows, "the THS fixture must yield at least one theme-gated record"
    assert {r["timestamp_quality"] for r in rows} == {"PUBLISHER_STATED"}
    # the same headline arriving on the akshare leg (no domain) stays day-resolution
    ak_shaped = [{**it, "domain": "", "time": "2026-07-27 18:41"} for it in direct]
    ak_rows = ni._build_qbus_rows(
        ni.build_records(ak_shaped, {}, "2026-07-27T13:00:00+00:00"),
        ak_shaped, "2026-07-27T13:00:00+00:00")
    assert ak_rows and {r["timestamp_quality"] for r in ak_rows} == {"SNAPSHOT_DATE"}


def test_feed_surfaces_wire_important(tmp_path, monkeypatch):
    import pandas as pd
    from datetime import date
    from engine import china_news_intel as ni
    recs = ni.build_records(nw.parse_wallstreetcn(WSCN_PAYLOAD), {}, "2026-07-10T13:00:00+00:00")
    p = tmp_path / "events.parquet"
    ni.accrue(None, recs).to_parquet(p, index=False)
    monkeypatch.setattr(ni, "_events_path", lambda: p)
    fd = ni.feed(today=date(2026, 7, 11))
    assert fd and fd["items"]
    flags = {it["title"]: it["wire_important"] for it in fd["items"]}
    assert any(flags.values()) and all(isinstance(v, bool) for v in flags.values())
