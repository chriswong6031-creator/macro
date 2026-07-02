"""Pure-function tests for engine/qkernel.py — no network, no clock.

Covers: bilingual norm_title, event_id/item_id (host discrimination), the merged
source_tier table, recency_weight (injected now), and the shingle/Jaccard/
similarity primitives event_key clustering is built on.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import qkernel as qk  # noqa: E402

_NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# norm_title — bilingual
# --------------------------------------------------------------------------- #
def test_norm_title_latin_collapses_and_lowercases():
    assert qk.norm_title("Fed Holds Rates!!  Steady", "en") == "fed holds rates steady"


def test_norm_title_latin_ascii_bytecompat_with_news_common():
    # pure-ASCII should match news_common.norm_title semantics
    from engine import news_common as nc
    for t in ["Nvidia Beats Q3 Estimates", "APPLE, INC. — new iPhone?", ""]:
        assert qk.norm_title(t, "en") == nc.norm_title(t)


def test_norm_title_cjk_strips_all_whitespace():
    # Chinese has no inter-word spaces: collapse-to-space would corrupt the key.
    out = qk.norm_title("央行 降准  释放 流动性", "zh")
    assert " " not in out
    assert "央行降准释放流动性" == out


def test_norm_title_auto_sniffs_cjk():
    assert qk.norm_title("A股大涨 rally") == qk.norm_title("A股大涨 rally", "cjk")
    assert qk.has_cjk("A股大涨") is True
    assert qk.has_cjk("pure english") is False


def test_norm_title_cjk_cap_60():
    long = "中" * 200
    assert len(qk.norm_title(long, "zh")) == 60


# --------------------------------------------------------------------------- #
# event_id / item_id
# --------------------------------------------------------------------------- #
def test_event_id_stable_and_16char():
    a = qk.event_id("reuters", "https://reuters.com/x", "Fed holds rates")
    b = qk.event_id("reuters", "https://reuters.com/x", "Fed  Holds  Rates!")
    assert a == b and len(a) == 16          # normalization makes these one item


def test_event_id_different_host_different_id():
    # a mirror on a different host is a DISTINCT item (cross-host collapse is
    # event_key's job, not event_id's).
    a = qk.event_id("reuters", "https://reuters.com/x", "Fed holds rates")
    b = qk.event_id("rss", "https://apnews.com/y", "Fed holds rates")
    assert a != b


def test_event_id_falls_back_to_source_when_no_url():
    a = qk.event_id("jin10", "", "央行降准")
    b = qk.event_id("cls", "", "央行降准")
    assert a != b
    assert qk.item_id("jin10", "", "央行降准") == a   # item_id is an alias


# --------------------------------------------------------------------------- #
# source_tier — merged table
# --------------------------------------------------------------------------- #
def test_source_tier_english_wires():
    assert qk.source_tier("reuters.com") == 1
    assert qk.source_tier("finance.yahoo.com") == 3
    assert qk.source_tier("cnbc.com") == 1


def test_source_tier_cn_tokens():
    assert qk.source_tier("", "xinhua") == 1
    assert qk.source_tier("gov.cn") == 1
    assert qk.source_tier("", "jin10") == 2
    assert qk.source_tier("", "em") == 2


def test_source_tier_blocked_and_unknown():
    assert qk.source_tier("tipranks.com") == 0
    assert qk.source_tier("some-random-blog.info") == 0
    assert qk.is_blocked("tipranks.com") is True
    assert qk.is_allowlisted("reuters.com") is True


# --------------------------------------------------------------------------- #
# recency_weight — clock injected
# --------------------------------------------------------------------------- #
def test_recency_weight_now_is_one():
    assert abs(qk.recency_weight(_NOW.isoformat(), _NOW) - 1.0) < 1e-6


def test_recency_weight_half_life():
    from datetime import timedelta
    old = (_NOW - timedelta(hours=36)).isoformat()
    assert abs(qk.recency_weight(old, _NOW, half_life_h=36.0) - 0.5) < 1e-3


def test_recency_weight_unknown_neutral():
    assert qk.recency_weight("not-a-date", _NOW) == 0.4


# --------------------------------------------------------------------------- #
# shingle / jaccard / similarity
# --------------------------------------------------------------------------- #
def test_title_similarity_paraphrase_high():
    s = qk.title_similarity("Fed holds interest rates steady",
                            "Fed holds interest rates steady in June")
    assert s > 0.5


def test_title_similarity_unrelated_low():
    s = qk.title_similarity("Nvidia beats estimates",
                            "OPEC agrees to cut oil output")
    assert s < 0.2


def test_shingles_cjk_language_agnostic():
    # bigram shingles work on Chinese with no tokenizer.
    a = qk.shingles("央行降准释放流动性", "zh")
    b = qk.shingles("央行降准释放大量流动性", "zh")
    assert qk.jaccard(a, b) > 0.4
