"""US-news i18n hygiene render tests for dashboard.html.j2 (macro.html + us_stocks.html).

Mirrors tests/test_china_news_page_render.py for the US side.  The legacy
news & catalysts accordion (the one surface that embedded raw
``importance_reasons`` strings and de-underscored channel slugs in both
language spans) was False-gated by audit INT-07/09dt and is now deleted; the
live US-news surfaces are the sx-news-v2 island face and the dlg-news dialog.
These tests pin the doctrine-Law-2 invariants on the WHOLE rendered page so a
future surface can't reintroduce the leak:

* internal scorer strings (``importance_reasons``) never render — they stay
  machine-only in the payload;
* raw channel slugs never render — the dominant-channel read maps through the
  engine's bilingual CHANNEL_LABEL payload dict as an l-en/l-zh toggle pair;
* payloads cached before the engine shipped ``channel_label`` degrade to
  de-underscored words, never to the raw slug.

Reuses the synthetic view-model + env from test_dashboard_template_render so
the render call stays byte-identical to scripts/build_site.py's.
"""
from __future__ import annotations

import sys
from pathlib import Path

from engine.macro_news import CHANNEL_LABEL, TIER_LABEL

# reuse the dashboard render fixture regardless of pytest's import mode
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_dashboard_template_render import _base_vm, _env  # noqa: E402


def _head(rank: int) -> dict:
    return {
        "title": f"Fed signals patience on cuts {rank}",
        "title_zh": f"美联储对降息保持耐心 {rank}",
        "theme": "monetary",
        "url": "https://example.com/story",
        "pub_date": "2026-07-16",
        "seendate": "2026-07-16T09:00:00Z",
        "domain": "reuters.com",
        "source_name": "Reuters",
        "source_tier": "tier1",
        "importance": "high",
        "importance_score": 88,
        "importance_reasons": ["tier-1 macro term", "dashboard core theme"],
        "channels": ["fiscal_trade", "capital_return"],
        "tickers": ["SPY"],
    }


def _macro_news(**overrides) -> dict:
    payload = {
        "schema": "macro_news.v1",
        "headlines": [_head(i) for i in range(3)],
        "n_kept": 3,
        "n_raw": 40,
        "synthesis": {
            "high_impact_count": 3,
            "dominant_channel": "energy",
            "read": "3 high-impact items; dominant channel energy",
        },
        # the real engine dicts, exactly like the live payload
        "channel_label": CHANNEL_LABEL,
        "tier_label": TIER_LABEL,
    }
    payload.update(overrides)
    return payload


def _render(mode: str = "macro", **news_overrides) -> str:
    vm = _base_vm()
    vm["macro_news"] = _macro_news(**news_overrides)
    return _env().get_template("dashboard.html.j2").render(**vm, mode=mode)


def test_internal_scorer_strings_never_render():
    html = _render()
    assert "tier-1 macro term" not in html
    assert "dashboard core theme" not in html
    # the retired accordion's tell-tale prefixes must never come back
    assert "Flagged:" not in html
    assert "入选：" not in html


def test_raw_channel_slugs_never_render():
    html = _render()
    assert "fiscal_trade" not in html
    assert "capital_return" not in html


def test_dominant_channel_maps_through_engine_labels():
    html = _render()
    # engine CHANNEL_LABEL['energy'] == ('energy', '能源') → l-en/l-zh pair
    assert "dominant: <strong>energy</strong>" in html
    assert "主导：<strong>能源</strong>" in html


def test_dominant_channel_degrades_without_label_dict():
    """Payloads cached before the engine shipped channel_label: de-underscore,
    never the raw slug."""
    html = _render(
        channel_label=None,
        synthesis={
            "high_impact_count": 1,
            "dominant_channel": "pipeline_flow",
            "read": "1 high-impact item",
        },
    )
    assert "pipeline_flow" not in html
    assert "pipeline flow" in html


def test_stocks_mode_holds_the_same_invariants():
    html = _render(mode="stocks")
    assert "tier-1 macro term" not in html
    assert "fiscal_trade" not in html
