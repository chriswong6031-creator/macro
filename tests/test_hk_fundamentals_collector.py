"""Collector-side tests for collectors/hk_fundamentals.py — the 公司介绍 business
description trimmer that feeds the HK stock-page profile blurb."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import hk_fundamentals as hf  # noqa: E402


def test_trim_desc_caps_sentences():
    # the real shape: a Chinese paragraph split on 。 — keep the lead sentences only
    txt = "腾讯是一家互联网科技公司。腾讯成立于1998年。总部位于深圳。还有更多无关内容。"
    assert hf._trim_desc(txt, max_sentences=2, max_chars=260) == \
        "腾讯是一家互联网科技公司。腾讯成立于1998年。"


def test_trim_desc_stops_before_exceeding_chars():
    # second sentence would blow the cap -> keep just the first
    txt = "甲" * 30 + "。" + "乙" * 30 + "。"
    out = hf._trim_desc(txt, max_sentences=3, max_chars=40)
    assert out == "甲" * 30 + "。"


def test_trim_desc_hard_slices_one_long_sentence():
    # a single over-long sentence (no early 。) is hard-sliced so the card can't overflow
    out = hf._trim_desc("甲" * 500, max_sentences=3, max_chars=100)
    assert out is not None and len(out) == 100


def test_trim_desc_empty():
    assert hf._trim_desc(None) is None
    assert hf._trim_desc("") is None
    assert hf._trim_desc("   ") is None
