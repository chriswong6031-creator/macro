from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ICON_FAMILIES = {
    "alert",
    "allocation",
    "altdata",
    "baskets",
    "bitcoin",
    "commodities",
    "confluence",
    "darkpool",
    "dashboard",
    "event",
    "flow",
    "forex",
    "heatmap",
    "intelligence",
    "leader",
    "narrative",
    "news",
    "options",
    "policy",
    "radar",
    "rebalance",
    "research",
    "rotation",
    "stage",
    "stocks",
    "strategy",
    "structure",
}
LEGACY_SUBMENU_MARKS = (
    "📊", "📈", "📶", "🧠", "🧺", "🌀", "💫", "🎛", "📰", "🚨",
    "🧲", "🌊", "🏆", "🌑", "🏗", "📡", "🔥", "🔬", "🛰", "🏛",
    "⚡", "🧭", "🔄", "₿", "◎", "🛢", "💱",
)
EXPECTED_RESEARCH_ICON_FAMILIES = {
    "alt-data",
    "anticipation",
    "confluence",
    "congress",
    "country-cycles",
    "cross-asset",
    "cycle-intelligence",
    "demand",
    "divergence",
    "factors-seasonality",
    "fed-policy",
    "foresight",
    "fund-flows",
    "global-cycles",
    "impulse",
    "intelligence-hub",
    "ipo",
    "macro-signals",
    "macro-weather",
    "measurement",
    "neural-web",
    "reports",
    "sector-cycles",
    "signal-lab",
    "smart-money",
    "special-situations",
    "technical-lab",
    "themes",
    "transmission",
    "vault",
    "white-house",
}
def _requested_menu(html: str) -> str:
    start = html.index('menu-icon-us')
    end = html.index('<div class="nav-dd nav-mega-dd">', start)
    return html[start:end]


def _research_menu(html: str) -> str:
    start = html.index('<div class="nav-dd nav-mega-dd">')
    return html[start:]


def test_requested_submenus_use_complete_semantic_icon_set() -> None:
    html = (ROOT / "site" / "macro.html").read_text(encoding="utf-8")
    menu = _requested_menu(html)
    families = {
        name.removeprefix("submenu-icon-")
        for name in re.findall(
            r'class="submenu-icon (submenu-icon-[a-z]+)"',
            menu,
        )
    }

    assert families == EXPECTED_ICON_FAMILIES
    assert menu.count('class="submenu-icon ') == 65
    assert not any(mark in menu for mark in LEGACY_SUBMENU_MARKS)


def test_template_and_site_share_the_same_submenu_icon_markup() -> None:
    template = (ROOT / "templates" / "chat.html").read_text(encoding="utf-8")
    site = (ROOT / "site" / "chat.html").read_text(encoding="utf-8")

    assert _requested_menu(template) == _requested_menu(site)


def test_research_mega_menu_uses_complete_semantic_icon_set() -> None:
    html = (ROOT / "site" / "macro.html").read_text(encoding="utf-8")
    research = _research_menu(html)
    families = {
        name.removeprefix("research-icon-")
        for name in re.findall(
            r'class="nm-ic research-icon (research-icon-[a-z-]+)"',
            research,
        )
    }

    assert "submenu-icon" not in research
    assert families == EXPECTED_RESEARCH_ICON_FAMILIES
    assert research.count('class="nm-ic research-icon ') == 31
    assert '<span class="nm-ic">' not in research


def test_jinja_nav_partial_preserves_research_icon_markup_on_rerender() -> None:
    partial = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    families = {
        name.removeprefix("research-icon-")
        for name in re.findall(
            r'class="nm-ic research-icon (research-icon-[a-z-]+)"',
            partial,
        )
    }

    assert families == EXPECTED_RESEARCH_ICON_FAMILIES
    assert partial.count('class="nm-ic research-icon ') == 31
    assert '<span class="nm-ic">' not in partial


def test_jinja_nav_partial_preserves_submenu_icon_markup_on_rerender() -> None:
    partial = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    menu = _requested_menu(partial)
    families = {
        name.removeprefix("submenu-icon-")
        for name in re.findall(
            r'class="submenu-icon (submenu-icon-[a-z]+)"',
            menu,
        )
    }

    assert families == EXPECTED_ICON_FAMILIES
    assert menu.count('class="submenu-icon ') == 65
    assert not any(mark in menu for mark in LEGACY_SUBMENU_MARKS)


def test_all_rendered_menus_preserve_custom_icon_markup() -> None:
    rendered = 0
    for page in (ROOT / "site").rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        if '<div class="nav-dd nav-mega-dd">' not in html:
            continue
        rendered += 1
        submenu = _requested_menu(html)
        research = _research_menu(html)
        assert submenu.count('class="submenu-icon ') >= 51, page
        assert not any(mark in submenu for mark in LEGACY_SUBMENU_MARKS), page
        assert '<span class="nm-ic">' not in research, page
        assert 'class="nm-ic research-icon ' in research, page

    assert rendered >= 3000
