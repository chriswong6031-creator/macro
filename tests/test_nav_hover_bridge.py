from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CSS = (ROOT / "templates" / "navigation-refresh.css").read_text(
    encoding="utf-8"
)
SITE_CSS = (ROOT / "site" / "navigation-refresh.css").read_text(encoding="utf-8")
TEMPLATE_JS = (ROOT / "templates" / "nav_market.js").read_text(encoding="utf-8")
SITE_JS = (ROOT / "site" / "nav_market.js").read_text(encoding="utf-8")
TEMPLATE_THEME_JS = (ROOT / "templates" / "theme.js").read_text(encoding="utf-8")
SITE_THEME_JS = (ROOT / "site" / "theme.js").read_text(encoding="utf-8")
TEMPLATE_ACCOUNT_JS = (ROOT / "templates" / "account.js").read_text(encoding="utf-8")
SITE_ACCOUNT_JS = (ROOT / "site" / "account.js").read_text(encoding="utf-8")


def test_market_menus_are_click_owned_while_research_keeps_hover_bridge() -> None:
    assert "function bindClickMarketDropdowns(links)" in TEMPLATE_JS
    assert "data-nav-click-market" in TEMPLATE_JS
    assert "nav-click-open" in TEMPLATE_JS
    assert "aria-haspopup" in TEMPLATE_JS
    assert "trigger.setAttribute('aria-expanded', wasOpen ? 'false' : 'true')" in TEMPLATE_JS
    assert "if (dd.parentElement !== links) return;" in TEMPLATE_JS
    assert "closeClickMarketMenus(links)" in TEMPLATE_JS

    # Research retains the deliberate trigger-to-panel hover bridge. Market
    # menus explicitly opt out before any pointer listeners are attached.
    assert "function bindHoverSafeDropdowns(links)" in TEMPLATE_JS
    assert "data-nav-hover-safe" in TEMPLATE_JS
    assert "if (dd.classList.contains('nav-market-dd')) return;" in TEMPLATE_JS
    assert "window.innerWidth > 900 && fineHover.matches" in TEMPLATE_JS
    assert "function hoverGraceMs()" in TEMPLATE_JS
    assert "menuRect.top - triggerRect.bottom" in TEMPLATE_JS
    assert "Math.min(1000, Math.max(420, 360 + Math.round(gap * 8)))" in TEMPLATE_JS
    assert "}, hoverGraceMs());" in TEMPLATE_JS
    assert "menu.addEventListener('pointerenter', openMenu)" in TEMPLATE_JS
    assert "menu.addEventListener('pointerleave', closeMenuSoon)" in TEMPLATE_JS

    assert ".nav-dd.nav-hover-open > .nav-dd-menu" in TEMPLATE_CSS
    assert ".nav-dd.nav-hover-open > .nav-dd-menu.nav-mega" in TEMPLATE_CSS
    assert "transform: translateY(0);" in TEMPLATE_CSS

    assert ".nav-market-dd:not(.nav-click-open):hover > .nav-market-menu" in TEMPLATE_CSS
    assert ".nav-market-dd.nav-click-open > .nav-market-menu" in TEMPLATE_CSS
    assert "pointer-events: none;" in TEMPLATE_CSS
    assert "pointer-events: auto;" in TEMPLATE_CSS

    # The approved menu geometry is unchanged; only its interaction owner
    # changes from hover to a deliberate click.
    assert "top: calc(100% + 7px)" not in TEMPLATE_CSS


def test_research_hover_and_market_click_animations_have_stable_owners() -> None:
    hover_rule = TEMPLATE_CSS.split(
        ".site-nav .nav-dd:hover > .nav-dd-menu.mega-menu,", 1
    )[1].split("}", 1)[0]
    assert "display: grid;" in hover_rule
    assert "animation:" not in hover_rule

    persistent_open_rule = TEMPLATE_CSS.split(
        ".site-nav .nav-dd.nav-hover-open > .nav-dd-menu.mega-menu,", 1
    )[1].split("}", 1)[0]
    assert "animation: mockupMenuSwap" in persistent_open_rule

    market_click_rule = TEMPLATE_CSS.split(
        ".site-nav .nav-links > .nav-market-dd.nav-click-open > .nav-market-menu,", 1
    )[1].split("}", 1)[0]
    assert "animation: mockupMenuSwap" in market_click_rule
    assert "(prefers-reduced-motion: reduce)" in TEMPLATE_CSS


def test_folded_country_rows_and_header_have_non_overlapping_layout() -> None:
    assert "grid-template-columns: 22px minmax(0, 1fr)" in TEMPLATE_CSS
    assert "gap: 10px;" in TEMPLATE_CSS
    assert (
        ".nav-dd-menu.mega-menu.nav-market-drill-panel > .nav-market-main "
        "{ padding-top: 72px; }"
    ) in TEMPLATE_CSS
    assert (
        ".nav-dd-menu.mega-menu.nav-market-drill-panel > .nav-market-main "
        "{ padding-top: 0; }"
    ) in TEMPLATE_CSS


def test_hover_gap_assets_remain_byte_identical() -> None:
    assert TEMPLATE_CSS == SITE_CSS
    assert TEMPLATE_JS == SITE_JS
    assert TEMPLATE_ACCOUNT_JS == SITE_ACCOUNT_JS


def test_hover_gap_release_uses_fresh_immutable_asset_chain() -> None:
    assert "account.js?v=20260731-click1" in TEMPLATE_THEME_JS
    assert "account.js?v=20260731-click1" in SITE_THEME_JS
    assert "nav_market.js?v=20260731-click1" in TEMPLATE_ACCOUNT_JS
    assert "20260730-exact6" not in TEMPLATE_THEME_JS
    assert "20260730-exact6" not in SITE_THEME_JS
    assert "20260730-exact6" not in TEMPLATE_ACCOUNT_JS
    assert "20260730-exact7" not in TEMPLATE_THEME_JS
    assert "20260730-exact7" not in SITE_THEME_JS
    assert "20260730-exact7" not in TEMPLATE_ACCOUNT_JS


def test_nested_pages_resolve_market_nav_from_theme_asset_root() -> None:
    """Every nested estate must load the one shared market-menu runtime."""
    for source in (TEMPLATE_THEME_JS, SITE_THEME_JS):
        assert "document.currentScript" in source
        assert 'script[src$="theme.js"],script[src*="theme.js?"]' in source
        assert "var _mmSharedAssetRoot" in source
        assert "new URL('.', _mmThemeScript" in source
        assert source.count("var pfx = _mmSharedAssetRoot;") == 3
        assert "location.pathname.indexOf('/sectors/')" not in source
        assert "s.src = pfx + 'account.js?v=20260731-click1'" in source
