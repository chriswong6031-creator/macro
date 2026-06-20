"""Small extension: China news theme classification — additional cases.
No network. Complements tests/test_china_news_engine.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_news as cn  # noqa: E402


def test_classify_theme_tech():
    # "华为发布新芯片 国产替代" -> "tech" (芯片 and 国产替代 are tech keywords)
    assert cn.classify_theme("华为发布新芯片 国产替代") == "tech"


def test_classify_theme_politics():
    # "习近平 中美外交" -> "politics" (习近平 and 外交 are politics keywords)
    assert cn.classify_theme("习近平 中美外交") == "politics"


def test_classify_theme_markets():
    # "A股 券商涨停" -> "markets" (A股 and 券商 are markets keywords)
    assert cn.classify_theme("A股 券商涨停") == "markets"


def test_classify_theme_monetary():
    # "央行降准100个基点" -> "monetary"
    assert cn.classify_theme("央行降准100个基点") == "monetary"


def test_classify_theme_inflation():
    # "CPI同比下降0.1%" -> "inflation"
    assert cn.classify_theme("CPI同比下降0.1%") == "inflation"


def test_classify_theme_none_for_offmacro():
    # Pure entertainment headline — no macro keywords
    assert cn.classify_theme("某流量明星最新演唱会巡演公告") is None


def test_classify_theme_tech_ai():
    # "人工智能算力大模型" hits tech keywords (人工智能 is NOT in the list, but 算力 and 大模型 are)
    result = cn.classify_theme("国内算力需求激增 大模型训练成本下降")
    assert result == "tech"


def test_classify_theme_growth():
    # GDP/PMI -> growth
    assert cn.classify_theme("GDP增速超预期 PMI连续三月扩张") == "growth"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
