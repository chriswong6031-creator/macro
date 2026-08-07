"""The landing hub's "What changed" row must explain itself.

``_home_alerts`` has always carried a plain-word explanation (``what``, from
``engine.alerts.ALERT_META``) and a conviction/null note (``edge``, from
``ALERT_CONVICTION``) on every feed row. Until 2026-08-06 ``_g_alerts`` dropped
both on the floor and rendered only the raw engine message, so opening the
newest alert produced ``GEX: net GEX changed sign (net +79bn, spot vs flip
-0.7%)`` and not one word about what that means — while ``hub-welcome.js``
quoted that same headline and told the reader "The evidence is below."

These guards pin the render, not the wording: they assert the explanation and
conviction text reach the HTML, that the newest row is open so the greeter's
pointer lands on something, and that a feed carrying neither still renders.
"""
from __future__ import annotations

import re

from scripts.build_vector import _g_alerts

WHAT = "Dealer gamma (GEX) measures how options hedging pushes the market around."
WHAT_ZH = "做市商 gamma（GEX）衡量期权对冲如何推动市场。"
EDGE = "Medium — changes the volatility backdrop, not the direction."
EDGE_ZH = "中 — 改变的是波动背景，而非方向。"
READ = "GEX: net GEX changed sign (net +79bn, spot vs flip -0.7%)"


def _alert(**over) -> dict:
    row = {
        "source": "macro", "source_label": "Macro Vector", "source_label_zh": "宏观向量",
        "ts": "2026-08-05T00:00:00", "date_only": True, "severity": "medium",
        "type": "gex_flip_cross",
        "headline": "🧲 Options “gravity” flipped — bigger swings more likely",
        "headline_zh": "🧲 期权“引力”反转 — 波动可能加大",
        "detail": READ, "detail_zh": "GEX：净额换向",
        "what": WHAT, "what_zh": WHAT_ZH,
        "edge": EDGE, "edge_zh": EDGE_ZH,
        "link": "macro_context.html#board", "tier": "watch",
        "cta": "Open scorecard →", "cta_zh": "打开记分卡 →",
    }
    row.update(over)
    return row


def test_opened_row_carries_the_plain_word_explanation() -> None:
    html = _g_alerts([_alert()])
    assert WHAT in html, "the alert's plain-word explanation never reached the page"
    assert WHAT_ZH in html, "the zh explanation never reached the page"
    assert '<div class="ha-what">' in html


def test_opened_row_carries_the_conviction_note() -> None:
    html = _g_alerts([_alert()])
    assert EDGE in html and EDGE_ZH in html
    assert '<div class="ha-edge">' in html
    # the conviction line is the honest-null home on this row: it must be labelled,
    # not dropped in as an unattributed sentence
    assert "Conviction:" in html and "可信度：" in html


def test_explanation_precedes_the_raw_measurement() -> None:
    """Meaning first, receipt second — the reader opened the row to learn what
    happened, not to re-read the number that is already on the scorecard."""
    html = _g_alerts([_alert()])
    assert html.index(WHAT) < html.index(EDGE) < html.index(READ)


def test_newest_row_is_open_so_the_greeter_promise_lands() -> None:
    """hub-welcome.js quotes the newest headline and says the evidence is below;
    a collapsed row keeps that promise empty."""
    html = _g_alerts([_alert(), _alert(headline="Second", ts="2026-08-04T00:00:00")])
    rows = re.findall(r"<details class=\"ha-item[^\"]*\"( open)?>", html)
    assert rows and rows[0] == " open", "newest row does not open by default"
    assert all(r == "" for r in rows[1:]), "only the newest row may open by default"


def test_row_without_explanation_still_renders_the_measurement() -> None:
    """The vector/commodity feeds may carry neither field (``forward``/``edge``
    are optional there). The row must degrade to today's shape, not vanish."""
    html = _g_alerts([_alert(what="", what_zh="", edge="", edge_zh="")])
    assert 'class="ha-what"' not in html and 'class="ha-edge"' not in html
    assert READ in html
    assert "macro_context.html#board" in html


def test_missing_zh_falls_back_to_english_not_to_empty() -> None:
    html = _g_alerts([_alert(what_zh="", edge_zh="")])
    # both language spans are always emitted; the zh side must not render blank
    assert html.count(WHAT) == 2, "zh span fell back to empty instead of English"
    assert html.count(EDGE) == 2
