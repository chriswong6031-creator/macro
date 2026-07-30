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
EXPECTED_PUBLIC_RESEARCH_DESTINATIONS = {
    "intelligence_hub.html",
    "reports.html",
    "research_vault.html",
    "neural_web.html",
    "foresight.html",
    "state_of_themes.html",
    "radar.html",
    "confluence_screener.html",
    "smart_money.html",
    "etfs.html",
    "cycle.html",
    "macro_context.html",
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
    # The Jinja partial is the sole source of truth. Rendered site pages are
    # refreshed by the post-merge render workflow and can intentionally lag in a
    # source PR, so this contract should not pin the previous generated menu.
    html = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    research = _research_menu(html)
    public_grid = research.split('<aside class="mega-rail', 1)[0]
    destinations = set(
        re.findall(r'href="\{\{ NP \}\}([^"]+)"', public_grid)
    )

    assert "submenu-icon" not in research
    assert destinations == EXPECTED_PUBLIC_RESEARCH_DESTINATIONS
    assert public_grid.count('class="icon-drawing nm-ic') == 12
    assert public_grid.count('<svg viewBox="0 0 48 48">') == 12
    assert "research-icon" not in public_grid
    assert '<span class="nm-ic">' not in research


def test_jinja_nav_partial_preserves_research_icon_markup_on_rerender() -> None:
    partial = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    research = _research_menu(partial)
    public_grid = research.split('<aside class="mega-rail', 1)[0]

    assert public_grid.count('class="icon-drawing nm-ic') == 12
    assert public_grid.count('<svg viewBox="0 0 48 48">') == 12
    assert "research-icon" not in public_grid
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

    # Crypto is intentionally composed inside the exact Other Assets mega-menu
    # at runtime, so the fresh template no longer emits a duplicate top-level
    # Crypto dropdown or its four legacy mask icons.
    assert families == EXPECTED_ICON_FAMILIES - {"allocation", "bitcoin"}
    assert menu.count('class="submenu-icon ') == 61
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
