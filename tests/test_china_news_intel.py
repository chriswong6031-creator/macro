"""China News powerhouse — pure-function contracts (network-free).

Mirrors tests/test_china_news_engine.py: the deterministic theme gate, CJK-safe event
keying, keep-FIRST accrual, source tiering, basket tagging, and the never-raise public
API. No network — fixtures are inline dicts.
"""
from __future__ import annotations

import pandas as pd

from collectors import china_news_wire as wire
from engine import china_news_intel as ni


# ---- theme classification -------------------------------------------------- #
def test_classify_theme_buckets():
    assert ni.classify_theme("央行降准释放流动性 LPR下调") == "monetary"
    assert ni.classify_theme("美国加征关税 贸易战升级") == "trade"
    assert ni.classify_theme("台海局势紧张 军事演习") == "geopolitics"
    assert ni.classify_theme("国产替代加速 信创落地") == "industrial_policy"
    assert ni.classify_theme("今天天气不错适合散步") is None


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
    assert ni.source_tier("randomblog", "example.com") == 3


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


def test_scheduled_ref_window_plus_minus_one_day():
    recs = ni.build_records(
        [{"title": "央行公开市场操作", "summary": "", "source": "em", "time": "2026-06-21"}],
        {"2026-06-20": "LPR"}, "now")
    assert recs[0]["scheduled_ref"] == "LPR@2026-06-20"   # ±1 day match


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


def test_accrue_columns_stable():
    recs = ni.build_records(
        [{"title": "央行降准", "summary": "", "source": "em", "time": "2026-06-20"}],
        {}, "now")
    m = ni.accrue(None, recs)
    assert list(m.columns) == list(ni._COLUMNS)
    assert isinstance(m, pd.DataFrame)
