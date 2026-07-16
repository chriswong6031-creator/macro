"""China News powerhouse — pure-function contracts (network-free).

Mirrors tests/test_china_news_engine.py: the deterministic theme gate, CJK-safe event
keying, keep-FIRST accrual, source tiering, basket tagging, and the never-raise public
API. No network — fixtures are inline dicts.
"""
from __future__ import annotations

import pandas as pd

from collectors import china_news_wire as wire
from engine import china_news_intel as ni


# ---- theme classification (geopolitics now split china_geo / global_geo) ---- #
def test_classify_theme_buckets():
    assert ni.classify_theme("央行降准释放流动性 LPR下调") == "monetary"
    assert ni.classify_theme("美国加征关税 贸易战升级") == "trade"
    assert ni.classify_theme("台海局势紧张") == "china_geo"
    assert ni.classify_theme("以色列与伊朗冲突升级") == "global_geo"   # demoted, not china_geo
    assert ni.classify_theme("国产替代加速 信创落地") == "industrial_policy"
    assert ni.classify_theme("今天天气不错适合散步") is None


# ---- ticker flagging (the 2,373-name map) ---------------------------------- #
def test_tag_tickers_longest_match():
    assert ni.tag_tickers("贵州茅台一季度业绩预增") == ["600519.SS"]
    multi = ni.tag_tickers("中信证券与北方稀土午后大涨")
    assert "600030.SS" in multi and "600111.SS" in multi
    assert ni.tag_tickers("美联储加息预期升温") == []


# ---- cn_defense anchor gate (kills the 8/8 Mid-East false positives) -------- #
def test_cn_defense_requires_china_anchor():
    assert "cn_defense" not in ni.tag_baskets("以色列军方发射导弹击中加沙")   # foreign war
    assert "cn_defense" in ni.tag_baskets("中国军工航天领域取得重大突破")      # China-anchored


def test_basket_ids_subset_of_membership():
    from engine import china_basket_spine as sp
    ours = {b[0] for b in ni.CN_BASKETS}
    assert ours <= set(sp.basket_ids())          # no dead baskets (cn_property dropped)
    assert "cn_property" not in ours


# ---- importance scoring ----------------------------------------------------- #
def test_importance_policy_surprise_outranks_fluff():
    hi = ni.importance_score(1, "LPR@2026-06-20", "2026-06-20", "monetary", 1, "央行降准降息", 0)
    lo = ni.importance_score(3, "", "2026-06-20", "markets", 0, "某公司日常公告", 0)
    assert hi > lo
    assert ni.importance_band(hi)[0] == "High"
    assert ni.importance_band(lo)[0] == "Routine"


def test_is_surprise_and_time_decay():
    assert ni.is_surprise("LPR@2026-06-20", "2026-06-20") is True
    assert ni.is_surprise("LPR@2026-06-20", "2026-06-19") is False
    assert ni.is_surprise("", "2026-06-20") is False
    fresh = ni.importance_score(1, "", "2026-06-20", "monetary", 0, "x", 0)
    stale = ni.importance_score(1, "", "2026-06-20", "monetary", 0, "x", 96)
    assert fresh > stale          # time decay


def test_item_sentiment_sign():
    assert ni._item_sentiment("增长 改革 利好") > 0
    assert ni._item_sentiment("风险 危机 衰退") < 0
    assert ni._item_sentiment("某中性公告") == 0.0


# ---- near-dup clustering ---------------------------------------------------- #
def test_cluster_events_merges_near_dups():
    recs = [
        {"title": "央行降准0.5个百分点", "theme": "monetary", "source_tier": 2,
         "first_seen_utc": "2026-06-20T01:00:00Z", "seendate": "2026-06-20"},
        {"title": "央行宣布降准0.5个百分点", "theme": "monetary", "source_tier": 1,
         "first_seen_utc": "2026-06-20T02:00:00Z", "seendate": "2026-06-20"},
        {"title": "A股午后拉升", "theme": "markets", "source_tier": 3,
         "first_seen_utc": "2026-06-20T03:00:00Z", "seendate": "2026-06-20"},
    ]
    cl = ni.cluster_events(recs)
    assert len(cl) == 2                                   # the two 降准 stories merge
    merged = [c for c in cl if c["dup_count"] > 1][0]
    assert merged["source_tier"] == 1                     # representative = best source tier


def test_narrative_buckets_precede_generic():
    # 制裁 appears in both geo-ish and fiscal lexicons; order must favor the distinctive one
    assert ni.classify_theme("出口管制 实体清单") == "trade"


# ---- basket tagging -------------------------------------------------------- #
def test_tag_baskets():
    tags = ni.tag_baskets("半导体国产替代 芯片 算力 大模型")
    assert "cn_semis" in tags and "cn_ai_compute" in tags
    assert ni.tag_baskets("闲聊八卦") == []


# ---- event id + CJK normalization ------------------------------------------ #
def test_event_id_stable_across_punctuation_and_space():
    a = ni.event_id("央行降准", "em")
    b = ni.event_id("央行  降准！", "em")
    assert a == b
    assert a != ni.event_id("央行加息", "em")


def test_norm_title_keeps_cjk():
    n = ni._norm_title("央行降准 ABC 123！")
    assert "央行降准" in n and "abc" in n and "123" in n


# ---- source tiering -------------------------------------------------------- #
def test_source_tier():
    assert ni.source_tier("rss", "english.news.cn") == 1
    assert ni.source_tier("em", "") == 2
    # W2: delegated to qkernel.source_tier which returns 0 (not allowlisted) for
    # unknown domains; the old module returned 3. Scoring uses `tier or 3` so
    # the effective weight is unchanged (TIER_W.get(int(0 or 3)) == TIER_W[3]).
    assert ni.source_tier("randomblog", "example.com") in (0, 3)


# ---- build_records: gate + dedup + scheduled_ref + baskets ----------------- #
def test_build_records_gates_dedups_and_stamps():
    arts = [
        {"title": "央行下调LPR", "summary": "半导体", "source": "em", "time": "2026-06-20"},
        {"title": "央行下调LPR", "summary": "dup", "source": "em", "time": "2026-06-20"},
        {"title": "闲聊", "summary": "", "source": "em", "time": "2026-06-20"},
    ]
    recs = ni.build_records(arts, {"2026-06-20": "LPR"}, "2026-06-20T00:00:00Z")
    assert len(recs) == 1                       # off-topic dropped + dup collapsed
    r = recs[0]
    assert r["theme"] == "monetary"
    assert r["scheduled_ref"] == "LPR@2026-06-20"
    assert "cn_semis" in r["baskets"]
    assert r["source_tier"] == 2


def test_scheduled_ref_reaction_window_and_channel():
    sched = {"2026-06-20": "LPR"}
    # same-day monetary article -> stamped
    assert ni._scheduled_ref_for("2026-06-20", sched, "monetary") == "LPR@2026-06-20"
    # day-AFTER reaction (release yesterday) -> stamped
    assert ni._scheduled_ref_for("2026-06-21", sched, "monetary") == "LPR@2026-06-20"
    # market-wrap reaction is calendar-explained flow too
    assert ni._scheduled_ref_for("2026-06-20", sched, "markets") == "LPR@2026-06-20"
    # day-BEFORE preview (release tomorrow) can't explain today's flow -> no stamp
    assert ni._scheduled_ref_for("2026-06-19", sched, "monetary") == ""
    # off-channel themes are the headline-shock flow -> never stamped (MN-06):
    # here the stamp feeds importance_score at accrual (+0.30/+0.40 into the
    # keep-FIRST PIT store), so the leak is baked in, not just context.
    for theme in ("tech", "global_geo", "china_geo", "politics", "policy",
                  "trade", "industrial_policy", "fiscal"):
        assert ni._scheduled_ref_for("2026-06-20", sched, theme) == "", theme
    # 2 days away / garbage dates -> no stamp
    assert ni._scheduled_ref_for("2026-06-22", sched, "monetary") == ""
    assert ni._scheduled_ref_for("bad-date", sched, "monetary") == ""
    # own-channel stamps: CPI->inflation, CREDIT->credit, ACTIVITY->growth
    assert ni._scheduled_ref_for("2026-07-09", {"2026-07-09": "CPI"}, "inflation") == "CPI@2026-07-09"
    assert ni._scheduled_ref_for("2026-07-10", {"2026-07-10": "CREDIT"}, "credit") == "CREDIT@2026-07-10"
    assert ni._scheduled_ref_for("2026-07-15", {"2026-07-15": "ACTIVITY"}, "growth") == "ACTIVITY@2026-07-15"
    # but not cross-channel: an inflation article is not CREDIT reaction flow
    assert ni._scheduled_ref_for("2026-07-10", {"2026-07-10": "CREDIT"}, "inflation") == ""


def test_scheduled_ref_channel_map_covers_high_impact():
    """Fail-closed contract: every _HIGH_IMPACT_CAL release type must have a
    channel entry — an unmapped type stamps NOTHING (silently reverting to the
    blanket stamp is the MN-06 bug), so the map must stay in lockstep with the
    calendar gate."""
    missing = ni._HIGH_IMPACT_CAL - set(ni._SCHEDULED_REF_THEMES)
    assert not missing, f"_SCHEDULED_REF_THEMES missing high-impact types: {missing}"
    # unmapped type -> fail closed, no stamp even on a matching-looking theme
    assert ni._scheduled_ref_for("2026-06-20", {"2026-06-20": "TRADE"}, "monetary") == ""


def test_build_records_day_after_reaction_stamped_day_before_not():
    day_after = ni.build_records(
        [{"title": "央行公开市场操作", "summary": "", "source": "em", "time": "2026-06-21"}],
        {"2026-06-20": "LPR"}, "now")
    assert day_after[0]["scheduled_ref"] == "LPR@2026-06-20"   # reaction window
    day_before = ni.build_records(
        [{"title": "央行公开市场操作", "summary": "", "source": "em", "time": "2026-06-19"}],
        {"2026-06-20": "LPR"}, "now")
    assert day_before[0]["scheduled_ref"] == ""                # release tomorrow ≠ today's flow


def test_build_records_off_channel_theme_not_stamped():
    # MN-06 CN case: a tech headline inside the ACTIVITY window must not get the
    # +0.30 scheduled_ref importance bump at accrual time.
    stamped, unstamped = ni.build_records(
        [{"title": "工业增加值数据公布 经济数据超预期", "summary": "", "source": "em", "time": "2026-07-15"},
         {"title": "华为发布大模型新品 算力芯片受关注", "summary": "", "source": "em", "time": "2026-07-15"}],
        {"2026-07-15": "ACTIVITY"}, "now")
    assert stamped["theme"] == "growth" and stamped["scheduled_ref"] == "ACTIVITY@2026-07-15"
    assert unstamped["theme"] == "tech" and unstamped["scheduled_ref"] == ""


# ---- accrue: append-only, keep-FIRST --------------------------------------- #
def test_accrue_keep_first_idempotent():
    recs = ni.build_records(
        [{"title": "央行降准", "summary": "", "source": "em", "time": "2026-06-20"}],
        {}, "2026-06-20T00:00:00Z")
    m1 = ni.accrue(None, recs)
    # re-ingest same event with a LATER first_seen — must keep the FIRST
    recs2 = ni.build_records(
        [{"title": "央行降准", "summary": "", "source": "em", "time": "2026-06-20"}],
        {}, "2026-06-25T00:00:00Z")
    m2 = ni.accrue(m1, recs2)
    assert len(m1) == len(m2) == 1
    assert m2.iloc[0]["first_seen_utc"] == "2026-06-20T00:00:00Z"


# ---- public API never raises + None-safe ----------------------------------- #
def test_public_api_callable_and_none_safe():
    # these read the live store; must not raise regardless of what's present
    ni.sentiment()
    ni.feed()
    p = ni.panel()
    assert p is None or (p["schema"] == ni.SCHEMA and p["is_context_only"] is True)


# ---- wire collector pure helpers ------------------------------------------- #
def test_wire_tone_sign_and_row_text():
    assert wire._tone("增长 改革 利好", 3) > 0       # all-positive lexicon
    assert wire._tone("风险 危机 衰退", 3) < 0       # all-negative lexicon
    assert wire._tone("", 1) == 0.0
    txt = wire._row_text({"标题": "央行降准", "摘要": "释放流动性", "x": "ignore?no"})
    assert "央行降准" in txt and "释放流动性" in txt


def test_wire_adapter_registers_without_akshare(monkeypatch):
    # adapter must construct even if akshare import would fail at fetch time
    a = wire.ChinaNewsWireAdapter()
    assert a.name == "china_news_wire" and a.group == "china_news"


def test_build_records_strips_title_and_url_from_seendate():
    # a native wire that concatenated "<title> <href>" into the date field must not
    # persist that into seendate; a genuine timestamp must survive untouched.
    recs = ni.build_records([
        {"title": "证监会推动资本市场法治协同建设", "summary": "改革", "source": "cnstock",
         "time": "证监会推动资本市场法治协同建设 https://www.cnstock.com/commonDetail/734410"},
        {"title": "央行开展逆回购操作投放流动性", "summary": "货币", "source": "em",
         "time": "2026-06-20 09:00"},
    ], {}, "2026-06-20T00:00:00+00:00")
    by_title = {r["title"]: r for r in recs}
    assert by_title["证监会推动资本市场法治协同建设"]["seendate"] == ""
    assert by_title["央行开展逆回购操作投放流动性"]["seendate"] == "2026-06-20 09:00"


def test_accrue_columns_stable():
    recs = ni.build_records(
        [{"title": "央行降准", "summary": "", "source": "em", "time": "2026-06-20"}],
        {}, "now")
    m = ni.accrue(None, recs)
    assert list(m.columns) == list(ni._COLUMNS)
    assert isinstance(m, pd.DataFrame)


# ---- generic-noun blocklist (§ticker-generic-noun audit finding) ------------ #
def test_tag_tickers_generic_noun_no_code_no_tag():
    """机器人 appearing generically (no adjacent exchange code) must NOT tag 300024.SZ.
    Audit measured 22/22 false positives from sector-level robotics headlines."""
    # Pure generic usage: 机器人 is the topic, not the company
    assert "300024.SZ" not in ni.tag_tickers("全球机器人产业大会今日在沪开幕")
    assert "300024.SZ" not in ni.tag_tickers("机器人板块午后拉升 多股涨停")
    assert "300024.SZ" not in ni.tag_tickers("人形机器人量产提速 产业链受益")


def test_tag_tickers_generic_noun_with_adjacent_code_tags():
    """机器人(300024) or 机器人300024 adjacent in title must tag 300024.SZ — this is
    the legitimate company-named usage where the code anchors the reference."""
    result = ni.tag_tickers("机器人(300024)一季度净利润增长35%")
    assert "300024.SZ" in result, f"Expected 300024.SZ in {result}"

    result2 = ni.tag_tickers("300024机器人发布年报")
    assert "300024.SZ" in result2, f"Expected 300024.SZ in {result2}"
