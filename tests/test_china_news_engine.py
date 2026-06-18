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


def test_panel_importable() -> None:
    # the build_china entrypoint just calls cn.panel(); make sure it exists/imports
    assert callable(cn.panel) and callable(cn.policy_tone) and callable(cn.flash_headlines)


if __name__ == "__main__":
    tests = [
        test_classify_theme,
        test_filter_flashes_gate_dedup_recency_topn,
        test_tone_band_thresholds,
        test_tone_stats_numeric,
        test_row_to_item_column_drift,
        test_panel_importable,
    ]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print("all china_news engine tests passed")
