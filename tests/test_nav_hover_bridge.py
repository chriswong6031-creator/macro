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


def test_top_market_menus_keep_hover_bridge_while_folded_countries_click() -> None:
    # Top-level market and Research menus share the hover-safe gap bridge.
    assert "function bindClickMarketDropdowns(links)" not in TEMPLATE_JS
    assert "data-nav-click-market" not in TEMPLATE_JS
    assert "nav-click-open" not in TEMPLATE_JS
    assert "function bindHoverSafeDropdowns(links)" in TEMPLATE_JS
    assert "data-nav-hover-safe" in TEMPLATE_JS
    assert "if (dd.classList.contains('nav-market-dd')) return;" not in TEMPLATE_JS
    assert "window.innerWidth > 900 && fineHover.matches" in TEMPLATE_JS
    assert "dd.parentElement === links" in TEMPLATE_JS
    assert "!dd.classList.contains('nav-market-drill')" in TEMPLATE_JS
    assert "dd.classList.remove('nav-hover-open')" in TEMPLATE_JS
    assert "function hoverGraceMs()" in TEMPLATE_JS
    assert "menuRect.top - triggerRect.bottom" in TEMPLATE_JS
    assert "Math.min(1000, Math.max(420, 360 + Math.round(gap * 8)))" in TEMPLATE_JS
    assert "}, hoverGraceMs());" in TEMPLATE_JS
    assert "menu.addEventListener('pointerenter', openMenu)" in TEMPLATE_JS
    assert "menu.addEventListener('pointerleave', closeMenuSoon)" in TEMPLATE_JS

    assert ".nav-dd.nav-hover-open > .nav-dd-menu" in TEMPLATE_CSS
    assert ".nav-dd.nav-hover-open > .nav-dd-menu.nav-mega" in TEMPLATE_CSS
    assert ".nav-dd.nav-hover-open > .nav-dd-menu.nav-market-menu" in TEMPLATE_CSS
    assert "transform: translateY(0);" in TEMPLATE_CSS

    # Only countries folded into International are click-to-drill. Their
    # canonical menu remains hidden under hover/focus until .is-open is set by
    # the explicit drill trigger.
    assert "data-nav-drill-open" in TEMPLATE_JS
    assert (
        ".nav-market-rail > .nav-market-drill:not(.is-open) "
        "> .nav-market-drill-panel"
    ) in TEMPLATE_CSS
    assert (
        ".nav-market-rail > .nav-market-drill.is-open > .nav-market-drill-panel"
    ) in TEMPLATE_CSS
    assert "pointer-events: none;" in TEMPLATE_CSS
    assert "pointer-events: auto;" in TEMPLATE_CSS

    # The final state-owned rule must appear after the generic hover bridge so
    # a moved country cannot be reopened by :hover or a stale hover class.
    generic_hover = TEMPLATE_CSS.rfind(
        ".site-nav .nav-dd.nav-hover-open > .nav-dd-menu.nav-market-menu"
    )
    folded_guard = TEMPLATE_CSS.rfind(
        ".nav-market-rail > .nav-market-drill:not(.is-open) "
        "> .nav-market-drill-panel"
    )
    assert generic_hover > -1
    assert folded_guard > generic_hover
    final_guard = TEMPLATE_CSS[folded_guard:].split("}", 1)[0]
    assert "visibility: hidden;" in final_guard
    assert "pointer-events: none;" in final_guard
    assert "animation: none !important;" in final_guard

    # The approved menu geometry remains unchanged.
    assert "top: calc(100% + 7px)" not in TEMPLATE_CSS


def test_top_menu_entrance_animation_cannot_restart_across_hover_gap() -> None:
    hover_rule = TEMPLATE_CSS.split(
        ".site-nav .nav-dd:hover > .nav-dd-menu.mega-menu,", 1
    )[1].split("}", 1)[0]
    assert "display: grid;" in hover_rule
    assert "animation:" not in hover_rule

    persistent_open_rule = TEMPLATE_CSS.split(
        ".site-nav .nav-dd.nav-hover-open > .nav-dd-menu.mega-menu,", 1
    )[1].split("}", 1)[0]
    assert "animation: mockupMenuSwap" in persistent_open_rule
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
    assert "account.js?v=20260731-folded2" in TEMPLATE_THEME_JS
    assert "account.js?v=20260731-folded2" in SITE_THEME_JS
    assert "nav_market.js?v=20260731-folded2" in TEMPLATE_ACCOUNT_JS
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
        assert "s.src = pfx + 'account.js?v=20260731-folded2'" in source
