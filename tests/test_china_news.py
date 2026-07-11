"""china_news collector tests — pure scoring + registry, no network / no akshare.

Run: .venv/bin/python -m tests.test_china_news
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.china_news import _tone_features  # noqa: E402


def _day(items: list[tuple[str, str]]) -> pd.DataFrame:
    """Build a fixture in news_cctv's (date, title, content) shape."""
    return pd.DataFrame(
        {"date": ["20260618"] * len(items),
         "title": [t for t, _ in items],
         "content": [c for _, c in items]})


def test_tone_sign_and_counts() -> None:
    df = _day([
        ("稳增长持续推进", "经济发展向好，支持就业，利好民生"),   # 6 pos words
        ("防范风险", "下行压力加大，债务违约，警惕衰退"),          # 5 neg words
    ])
    f = _tone_features(df)
    assert f["items"] == 2.0
    assert f["chars"] > 0
    # 6 pos − 5 neg over 2 items -> +0.5; just assert it's net-positive & sane
    assert f["tone"] > 0
    assert abs(f["tone"] - 0.5) < 1e-9


def test_tone_negative_day() -> None:
    df = _day([("危机", "冲突 制裁 紧张 衰退 萎缩 恶化")])
    f = _tone_features(df)
    assert f["items"] == 1.0
    assert f["tone"] < 0          # all risk-words -> negative tone


def test_robust_to_missing_text_columns() -> None:
    # content-only frame (akshare column drift) must not crash and still score text
    df = pd.DataFrame({"content": ["支持改革开放", "无关词语"]})
    f = _tone_features(df)
    assert f["items"] == 2.0 and f["tone"] > 0


def test_empty_text_is_neutral() -> None:
    df = pd.DataFrame({"date": ["20260618"], "title": [""], "content": [""]})
    f = _tone_features(df)
    assert f["tone"] == 0.0 and f["items"] == 1.0


def test_adapter_is_registered_without_akshare() -> None:
    # The whole point of the lazy akshare import: china_news must register even
    # when akshare is absent (as it is in this test env), never silently vanish.
    from scripts.collect import all_adapters
    reg = all_adapters()
    assert "china_news" in reg
    assert reg["china_news"].__name__ == "ChinaNewsAdapter"


def test_fetch_wire_gdelt_empty_success_reason(tmp_path) -> None:
    """When GDELT returns an empty artlist (no_articles from gdelt_client),
    _fetch_wire_gdelt must map it to 'wire_no_headlines', not leak the raw
    'no_articles' token into the template output."""
    from unittest.mock import patch
    from engine.china_news import _fetch_wire_gdelt

    cfg = {
        "wire_cache_ttl_hours": 12,
        "wire_sources": [],  # empty allow-list = accept everything
        "gdelt_max_records": 5,
    }

    with patch("engine.china_news._wire_cache_path", return_value=tmp_path / "no_cache"), \
         patch("engine.gdelt_client.get_articles", return_value=([], "no_articles")), \
         patch("engine.gdelt_client._throttle"):
        items, reason = _fetch_wire_gdelt(cfg)

    assert items == []
    assert reason == "wire_no_headlines", (
        f"Expected 'wire_no_headlines' but got {reason!r}; "
        "'no_articles' token must be remapped before reaching the template"
    )


if __name__ == "__main__":
    tests = [
        test_tone_sign_and_counts,
        test_tone_negative_day,
        test_robust_to_missing_text_columns,
        test_empty_text_is_neutral,
        test_adapter_is_registered_without_akshare,
        test_fetch_wire_gdelt_empty_success_reason,
    ]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print("all china_news collector tests passed")
