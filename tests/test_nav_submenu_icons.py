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
# OIP W1 nav regroup (research/options_estate/W1_DESIGN_SPEC.md §1.2): Options &
# Flow's flyout shrinks from 9 rows (trigger + gex + options_screener + movers +
# flow_desk + intraday_flow + flow_leaders + darkpool + market_structure) to 6
# (trigger + options.html + gex.html [now carrying the freed submenu-icon-dashboard]
# + intraday_flow + darkpool + market_structure) — options_screener/flow_desk/
# flow_leaders leave the flyout (URLs stay live forever with their own banner) and
# Daily Movers relocates into the United States group (same submenu-icon-stocks,
# net zero on that family). submenu-icon-leader was flow_leaders' ONLY user
# anywhere in this menu, so it drops out of EXPECTED_ICON_FAMILIES entirely rather
# than staying in the emitted-minus set below (unlike allocation/bitcoin, which
# are used elsewhere, just not in THIS rendered menu). Net count verified against
# the real re-rendered template, not hand-counted: 61 -> 59.
#
# Sector Intelligence consolidation (2026-08, nav 4 -> 2): the Thematic Baskets,
# Subsector Rotation and Confluence entries fold into the merged Sector
# Intelligence page, and two merged entries replace them — 5 submenu-icon spans
# removed, 2 added, net -3, so 59 -> 56. Counted off the diff of the real
# _navlinks.html.j2, not by hand. EXPECTED_EMITTED_ICON_FAMILIES is unchanged on
# purpose: submenu-icon-baskets / -rotation / -confluence each still have at
# least one other user in this menu, so no FAMILY leaves the set — only the
# per-span count moves. If a family ever does drop out, the families assertion
# above fails first and this comment is the place to say why.
EXPECTED_EMITTED_ICON_FAMILIES = EXPECTED_ICON_FAMILIES - {"allocation", "bitcoin"}
EXPECTED_EMITTED_ICON_COUNT = 56
LEGACY_SUBMENU_MARKS = (
    "📊", "📈", "📶", "🧠", "🧺", "🌀", "💫", "🎛", "📰", "🚨",
    "🧲", "🌊", "🏆", "🌑", "🏗", "📡", "🔥", "🔬", "🛰", "🏛",
    "⚡", "🧭", "🔄", "₿", "◎", "🛢", "💱",
)
EXPECTED_PUBLIC_RESEARCH_DESTINATIONS = {
    "fundamental_forensics.html",
    "intelligence_hub.html",
    "reports.html",
    "research_vault.html",
    "neural_web.html",
    "foresight.html",
    "state_of_themes.html",
    "radar.html",
    "confluence_screener.html",
    "stock_seasonality.html",
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


def _submenu_families(menu: str) -> set[str]:
    return {
        name.removeprefix("submenu-icon-")
        for name in re.findall(
            r'class="submenu-icon (submenu-icon-[a-z]+)"',
            menu,
        )
    }


def _drawn_icon_families() -> set[str]:
    """Families product-nav-icons.css actually draws.

    A `submenu-icon-<family>` class with no rule in the stylesheet still lays
    out its 16px box, so the row ships with a blank gap where the icon belongs.
    The stylesheet — not this module's hand-maintained constants — is the
    honest authority on which families a menu may reference.
    """
    css = (ROOT / "templates" / "product-nav-icons.css").read_text(encoding="utf-8")
    return {
        name.removeprefix(".submenu-icon-")
        for name in re.findall(r"\.submenu-icon-[a-z]+", css)
    }


def test_requested_submenu_icons_are_all_drawn_by_the_stylesheet() -> None:
    """Every icon the nav partial references must have a stylesheet rule.

    Deliberately a TEMPLATE-vs-CSS contract, never a rendered-page one. The
    predecessor of this test read the RENDERED site/macro.html and asserted it
    equalled the constants above, which made it unsatisfiable inside any nav PR:
    render.yml's region_of() maps `templates/*` to scope `all` (line 473), so a
    nav edit re-renders site/*.html only AFTER merge — inside the source PR the
    partial is new while the ~3.5k committed pages still carry the previous nav.
    Measured 2026-07-30 against #4123, which drops flow_leaders from the Options
    flyout: the partial no longer emits submenu-icon-leader, every shipped page
    still does, and the old assertion failed on `leader` for a PR that was
    correct. The exact emitted set stays pinned — render-independently — by
    test_jinja_nav_partial_preserves_submenu_icon_markup_on_rerender below.

    Both inputs here move in the SAME commit, so this covers the authoring bug
    nothing else caught: adding a row with a new icon family and forgetting the
    stylesheet, which ships a blank gap in the menu.
    """
    partial = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    menu = _requested_menu(partial)
    drawn = _drawn_icon_families()

    assert drawn, "product-nav-icons.css defines no .submenu-icon-* rules at all"
    undrawn = _submenu_families(menu) - drawn
    assert not undrawn, (
        "nav partial references icon families with no product-nav-icons.css "
        f"rule, so they ship as blank gaps: {sorted(undrawn)}"
    )


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
    assert public_grid.count('class="icon-drawing nm-ic') == 14
    assert public_grid.count('<svg viewBox="0 0 48 48">') == 14
    assert "research-icon" not in public_grid
    assert '<span class="nm-ic">' not in research


def test_jinja_nav_partial_preserves_research_icon_markup_on_rerender() -> None:
    partial = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    research = _research_menu(partial)
    public_grid = research.split('<aside class="mega-rail', 1)[0]

    assert public_grid.count('class="icon-drawing nm-ic') == 14
    assert public_grid.count('<svg viewBox="0 0 48 48">') == 14
    assert "research-icon" not in public_grid
    assert '<span class="nm-ic">' not in partial


def test_jinja_nav_partial_preserves_submenu_icon_markup_on_rerender() -> None:
    partial = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    menu = _requested_menu(partial)
    families = _submenu_families(menu)

    # Crypto is intentionally composed inside the exact Other Assets mega-menu
    # at runtime, so the fresh template no longer emits a duplicate top-level
    # Crypto dropdown or its four legacy mask icons.
    assert families == EXPECTED_EMITTED_ICON_FAMILIES
    assert menu.count('class="submenu-icon ') == EXPECTED_EMITTED_ICON_COUNT
    assert not any(mark in menu for mark in LEGACY_SUBMENU_MARKS)


def test_all_rendered_menus_preserve_custom_icon_markup() -> None:
    """Post-render drift audit over the SHIPPED pages.

    Every assertion here has to survive the render lag described on
    test_requested_submenu_icons_are_all_drawn_by_the_stylesheet: a nav PR
    leaves these pages a full generation behind until the post-merge scope=all
    render catches up. So this pins only what holds at every point in that lag —
    a floor, not an exact count, and membership in the stylesheet rather than
    equality with the current partial's set.
    """
    drawn = _drawn_icon_families()
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
        # A shipped page may lag the partial, but never reference an icon the
        # stylesheet does not draw — that is a blank gap in front of a user.
        undrawn = _submenu_families(submenu) - drawn
        assert not undrawn, f"{page}: undrawn icon families {sorted(undrawn)}"

    assert rendered >= 3000
