"""Render tests for china_news.html.j2 chip i18n hygiene.

The glance surface must never show raw channel/tier slugs (pboc_liquidity,
china_native) or internal scorer strings ("native Chinese financial source",
"tier-1 China macro term", "wire-flagged high impact") — channels and source
tiers render through the engine's bilingual label dicts as l-en/l-zh toggle
pairs, and importance_reasons stay machine-only in the payload.
"""
from __future__ import annotations

from pathlib import Path

import jinja2

from engine.china_news import CHANNEL_LABEL, THEME_LABEL, TIER_LABEL

ROOT = Path(__file__).resolve().parent.parent


def _env() -> jinja2.Environment:
    """Mirror scripts/build_china.py's Jinja env (same loader path)."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
        autoescape=False,
    )
    try:
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    return env


def _head(rank: int) -> dict:
    return {
        "title": f"央行开展逆回购操作 {rank}",
        "title_zh": f"央行开展逆回购操作 {rank}",
        "title_en": f"PBOC conducts reverse repo operations {rank}",
        "summary": "财政部公布中央财政支持普惠金融发展。",
        "summary_zh": "财政部公布中央财政支持普惠金融发展。",
        "summary_en": "MOF announces central fiscal support for inclusive finance.",
        "theme": "monetary",
        "url": "https://example.com/story",
        "time": "2026-07-16 09:00",
        "source_name": "华尔街见闻",
        "source_tier": "china_native",
        "importance": "high",
        "importance_score": 88,
        "importance_reasons": ["native Chinese financial source", "tier-1 China macro term"],
        "channels": ["pboc_liquidity", "fiscal_trade"],
        "tickers": ["512880.SS"],
    }


def _vm() -> dict:
    heads = [_head(i) for i in range(3)]
    return {
        "asof": "2026-07-16",
        "event_strip": [],
        "calendar": [],
        "china_news": {
            "tone": None,
            "news": {
                "headlines": heads,
                "n_official": 1, "n_cn_wire": 22, "n_news_rss": 1, "n_wire": 1,
                "n_kept": 3, "n_raw": 40,
                "synthesis": {
                    "high_impact_count": 3,
                    "avg_importance": 84.0,
                    "top_channels": [{"name": "pboc_liquidity", "count": 3,
                                      "label_en": "PBOC & liquidity", "label_zh": "央行与流动性"}],
                    "top_tickers": [{"ticker": "512880.SS", "count": 3}],
                    "source_mix": [{"tier": "china_native", "count": 22},
                                   {"tier": "official", "count": 1},
                                   {"tier": "global_wire", "count": 1}],
                    "dominant_channel": "pboc_liquidity",
                    "dominant_theme": "monetary",
                    "read": "3 high-impact China items; dominant channel PBOC & liquidity",
                    "read_zh": "3 条中国高影响信息；主导渠道：央行与流动性",
                },
            },
            "theme_label": THEME_LABEL,
            "channel_label": CHANNEL_LABEL,
            "tier_label": TIER_LABEL,
            "disclaimer": "Context only.", "disclaimer_zh": "仅供参考。",
        },
    }


def _render(**overrides) -> str:
    vm = _vm()
    vm.update(overrides)
    return _env().get_template("china_news.html.j2").render(**vm)


def test_internal_scorer_strings_never_render():
    html = _render()
    assert "native Chinese financial source" not in html
    assert "tier-1 China macro term" not in html
    assert "wire-flagged high impact" not in html
    assert "market-sensitive term" not in html


def test_source_tier_slug_never_renders_as_chip_text():
    html = _render()
    # neither the headline chip suffix ("华尔街见闻 · china_native") nor the
    # synthesis source-mix row may show the raw tier slug
    assert "china_native" not in html
    assert "global_wire" not in html
    # the source-mix row shows the bilingual tier label instead
    assert "Chinese financial press" in html
    assert "中国财经媒体" in html


def test_channel_chips_are_bilingual_toggle_pairs():
    html = _render()
    # chip text is the l-en/l-zh pair, never the raw slug
    assert ">pboc_liquidity<" not in html
    assert ">fiscal_trade<" not in html
    assert "PBOC & liquidity" in html
    assert "央行与流动性" in html
    assert "财政与贸易" in html


def test_raw_slugs_stay_searchable_and_labels_join_them():
    html = _render()
    # data-search keeps the raw slug for machine search AND gains the visible
    # bilingual label text so what the user sees on a chip is findable
    assert "pboc_liquidity" in html          # inside data-search only
    assert "pboc & liquidity" in html        # lowered label in data-search
    assert "512880.SS" in html               # ticker chips unchanged


def test_importance_band_word_toggles():
    html = _render()
    assert '<span class="l-en">high</span><span class="l-zh">高</span>' in html


def test_quiet_tape_payload_renders():
    # the real empty state: panel() returned a payload with zero kept headlines
    # (a fully-None payload never reaches the template — build_china.py skips
    # the page render when panel() returns None)
    vm = _vm()
    vm["china_news"]["news"]["headlines"] = []
    vm["china_news"]["news"]["synthesis"] = {}
    html = _env().get_template("china_news.html.j2").render(**vm)
    assert "宏观新闻流较安静" in html
