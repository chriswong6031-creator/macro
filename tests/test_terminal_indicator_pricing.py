"""Cross-surface guards for the Terminal indicator entitlement copy."""
from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from scripts.build_public_pages import plans_view_model
from scripts.build_site import _plans_view_model


ROOT = Path(__file__).resolve().parents[1]


def _access() -> dict:
    catalog = yaml.safe_load((ROOT / "config" / "plans.yml").read_text())
    return catalog["terminal_indicators"]


def test_both_plans_builders_receive_the_indicator_access_contract():
    expected = _access()
    assert plans_view_model()["terminal_indicators"] == expected
    assert _plans_view_model()["terminal_indicators"] == expected


def test_landing_and_onboarding_compare_show_each_tier_access():
    """The landing cards and the matrix must both quote the SAME ladder as plans.yml.

    The card bullets were cut to their nouns on 2026-07-31 (operator: "too much
    information") and the module count is now the only bolded thing in the list, so
    these pins carry the <b> — matching the shipping markup, not a paraphrase of it.
    Candle Painter moved off the card entirely; the matrix still names it, which is
    where the last two assertions look.
    """
    access = _access()
    for rel in ("templates/index.html", "site/index.html"):
        page = (ROOT / rel).read_text()
        assert "Advanced indicator modules" in page
        assert f"Terminal charting — {access['core_count']} core indicators" in page
        assert f"<b>{access['access']['insider']} of {access['advanced_total']}</b> advanced modules" in page
        assert f"<b>All {access['access']['pro']}</b> advanced modules" in page
        assert f"{access['access']['free']} / {access['advanced_total']}" in page
        assert f"{access['access']['insider']} / {access['advanced_total']}" in page
        assert f"All {access['access']['pro']}" in page
        assert "Candle Painter" in page

    for rel in ("templates/onboard.js", "site/onboard.js"):
        compare = (ROOT / rel).read_text()
        assert (
            f'{{ l: ["Advanced indicator modules", "高级指标模块"], '
            f'v: [["{access["access"]["free"]} / {access["advanced_total"]}", '
            f'"{access["access"]["free"]} / {access["advanced_total"]}"], '
            f'["{access["access"]["insider"]} / {access["advanced_total"]}", '
            f'"{access["access"]["insider"]} / {access["advanced_total"]}"], '
            f'["All {access["access"]["pro"]}", "全部 {access["access"]["pro"]} 个"]] }}'
        ) in compare


def test_rendered_plans_page_names_the_indicator_ladder():
    access = _access()
    vm = plans_view_model()
    page = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=True,
    ).get_template("plans.html.j2").render(
        generated_utc="test",
        currency=vm["currency"],
        insider=vm["insider"],
        pro=vm["pro"],
        founding=vm["founding"],
        terminal_indicators=vm["terminal_indicators"],
    )
    assert "Advanced indicator modules" in page
    assert f"{access['core_count']} " in page and "core indicators" in page
    assert f"{access['access']['free']} / {access['advanced_total']}" in page
    assert f"{access['access']['insider']} / {access['advanced_total']}" in page
    assert f'<span class="l-zh">全部</span> {access["access"]["pro"]}<small' in page


def test_market_terminal_showcase_uses_the_current_indicator_contract():
    access = _access()
    page = (ROOT / "site" / "products" / "market-terminal.html").read_text()

    assert "Five complementary systems.<br>One clearer technical workflow." in page
    assert f"complete {access['advanced_total']}-module library" in page
    assert "All five, complete · Available in Pro" in page
    assert "Essential unlocks a curated selection" in page
    assert "Structure Core" in page
    assert "Trend Waves" in page
    assert "Pulse Oscillator" in page
    assert "RSI Ultimate" in page
    assert "MACD Ultimate" in page
    assert "TP1–TP6" in page
    assert "complementary systems you can combine" in page
    assert "Essential + Pro modules · one example combination" in page
    assert 'data-aria-zh="选择工作流阶段"' in page
    assert "../plans.html#pricing-matrix" in page
    assert "mt-access-ladder" not in page
    assert f"{access['core_count']} core +" not in page
    assert "Seventeen built in" not in page
    assert "17 indicators in the picker" not in page
    assert "five coordinated systems" not in page.lower()
    assert "before the move is already mature" not in page
