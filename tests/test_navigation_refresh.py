from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAV = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
THEME_JS = (ROOT / "templates" / "theme.js").read_text(encoding="utf-8")
SITE_THEME_JS = (ROOT / "site" / "theme.js").read_text(encoding="utf-8")
MARKET_JS = (ROOT / "templates" / "nav_market.js").read_text(encoding="utf-8")
REFRESH_CSS = (ROOT / "templates" / "navigation-refresh.css").read_text(encoding="utf-8")


def test_public_research_menu_is_product_focused() -> None:
    for internal_page in (
        "measurement.html",
        "crossasset.html",
        "signal_lab.html",
        "tech_lab.html",
        "macro_signals.html",
        "factors.html",
        "committee.html",
    ):
        assert f'href="{{{{ NP }}}}{internal_page}"' not in NAV

    for public_page in (
        "intelligence_hub.html",
        "reports.html",
        "research_vault.html",
        "neural_web.html",
        "foresight.html",
        "state_of_themes.html",
        "radar.html",
        "confluence_screener.html",
    ):
        assert f'href="{{{{ NP }}}}{public_page}"' in NAV


def test_approved_mockup_is_the_navigation_source_of_truth() -> None:
    for copy in (
        "Your complete market command center",
        "Search every published research note",
        "What’s strengthening and fading now",
        "Today’s strongest confirmed setups",
        "Growth, inflation and liquidity now",
    ):
        assert copy in NAV

    assert 'class="icon-drawing' in NAV
    assert "APPROVED MOCKUP — SOURCE-OF-TRUTH PORT" in REFRESH_CSS
    for marker in (
        "grid-template-columns: minmax(0, 1fr) 245px",
        "grid-template-columns: 62px minmax(0, 1fr)",
        "min-height: 78px",
        "width: 58px",
        "height: 58px",
        "font-size: 15px",
        "font-weight: 650",
        "width: 276px",
    ):
        assert marker in REFRESH_CSS

    assert "MOCKUP_ICON_PATHS" in MARKET_JS
    assert "MOCKUP_RESEARCH_DESCRIPTION_BY_FILE" in MARKET_JS
    assert "legacy CSS-mask icon library" in MARKET_JS
    assert "{{ t('Crypto', '加密') }}" not in NAV
    assert "removeLegacyCryptoMenu(links)" in MARKET_JS
    for label in ("Bitcoin Overview", "Allocation Strategy", "BTC Strategy"):
        assert label in MARKET_JS


def test_global_cycles_uses_accessible_in_panel_drill() -> None:
    assert "data-nav-drill-open" in NAV
    assert "data-nav-drill-panel" in NAV
    assert "data-nav-drill-back" in NAV
    assert 'aria-expanded="false"' in NAV
    assert "initNavDrills()" in THEME_JS


def test_market_folding_reuses_canonical_menu_dom() -> None:
    assert "foldTarget.appendChild(toSubmenu(countries[k]))" in MARKET_JS
    assert "intlMenu.querySelector(':scope > .nav-market-rail')" in MARKET_JS
    assert "enhanceMarketMenus(links)" in MARKET_JS
    assert "MARKET_MENU" in MARKET_JS
    assert "MMXMarkets.current" in MARKET_JS
    assert "mmx-markets-change" in MARKET_JS
    assert "currentPreference.enabled.slice()" in MARKET_JS
    assert "data-nav-drill-open" in MARKET_JS


def test_search_is_profile_aware_animated_and_status_rich() -> None:
    for marker in (
        "MMXMarkets.current",
        "mmx-markets-change",
        "popularRows",
        "TURN SIGNALED",
        "TOP WATCH",
        "COUNTERTREND BOUNCE",
        "data-stock-logo",
        "data-search-page",
        "animated_nav_search",
    ):
        assert marker in THEME_JS

    assert ".nav-search.ticker-search.open { width: 340px; }" in REFRESH_CSS
    assert "@keyframes nrFanIn" in REFRESH_CSS
    assert "html:not([data-theme=\"light\"])" in REFRESH_CSS
    assert "@media (prefers-reduced-motion: reduce)" in REFRESH_CSS


def test_search_waits_for_refresh_css_on_stale_rendered_pages() -> None:
    """Static assets deploy before the full HTML render; that skew must stay safe."""
    for marker in (
        "ensureNavSearchCss",
        "navigation-refresh.css",
        "data-nav-css-wait",
        "if (!ensureNavSearchCss(box)) return",
        "data-ticker-search-ready",
        "ensureNavLogoAssets",
        "stock-logos.js",
        "logo_config.js",
    ):
        assert marker in THEME_JS
    assert 'link[rel="stylesheet"][href*="navigation-refresh.css"]' in THEME_JS
    assert "!link.hasAttribute('data-nav-refresh-runtime')" in THEME_JS
    assert "box.style.visibility = 'hidden'" in THEME_JS
    assert "if (loaded) initNavSearch()" in THEME_JS


def test_navigation_is_content_aware_and_research_rail_matches_mockup() -> None:
    for marker in (
        "initAdaptiveNav",
        "data-nav-layout",
        "directChildrenWidth",
        "mmx-markets-change",
        "needed <= bar.clientWidth ? 'single' : 'stacked'",
    ):
        assert marker in THEME_JS

    assert 'class="nav-mastermind-cta"' not in NAV
    assert 'href="https://bot.mastermind-x.com"' not in NAV
    assert "Cleaner by design" in NAV
    assert "Detailed diagnostics and proprietary labs move to the admin console." in NAV
    shared_chrome = (ROOT / "templates" / "_site_nav.html.j2").read_text(encoding="utf-8")
    assert "mastermind-link" not in shared_chrome


def test_mobile_navigation_is_a_full_height_accordion_with_full_width_search() -> None:
    for marker in (
        "@media (max-width: 900px)",
        "height: 100dvh",
        "position: fixed",
        ".site-nav.has-nav-toggle .nav-search",
        "width: 100%",
        ".nav-mega-item-grid { grid-template-columns: 1fr;",
        ".has-nav-toggle .nav-links .nav-mega.nav-mega .nm-feat",
    ):
        assert marker in REFRESH_CSS

    assert "@media (max-width:900px)" in THEME_JS
    assert "window.innerWidth > 900" in THEME_JS


def test_mobile_ticker_input_does_not_trigger_ios_focus_zoom() -> None:
    final_mobile_rules = REFRESH_CSS.rsplit("@media (max-width: 900px)", 1)[1]
    assert "iOS Safari zooms the page" in final_mobile_rules
    assert (
        ".ticker-search .ticker-input { font-size: 16px; }"
        in final_mobile_rules
    )


def test_search_preserves_chinese_ime_spaces_and_localizes_results() -> None:
    for source in (THEME_JS, SITE_THEME_JS):
        for marker in (
            'maxlength="80"',
            "compositionstart",
            "compositionend",
            "e.isComposing",
            "e.keyCode === 229",
            "normalizeSearch",
            "nameChinese",
            "x.z || x.zh || x.cn || x.name_zh",
            "股票搜索结果",
            "没有匹配的股票代码或公司。",
            "displayName(x)",
            "document.addEventListener('langchange', applySearchLocale)",
        ):
            assert marker in source
        assert "input.value = input.value.toUpperCase().replace" not in source

    ticker_input_rule = REFRESH_CSS.split(
        ".ticker-search .ticker-input {", 1
    )[1].split("}", 1)[0]
    assert "text-transform: none;" in ticker_input_rule
    assert 'html[data-lang="zh"] .ticker-search .search-esc' in REFRESH_CSS


def test_right_edge_asset_flyouts_open_inward_without_desktop_overflow() -> None:
    assert (
        ".site-nav .nav-links > .nav-dd:nth-last-of-type(6) "
        "> .nav-dd-menu:not(.nav-mega)"
    ) in REFRESH_CSS
    edge_selector = (
        ".site-nav .nav-links > .nav-dd:nth-last-of-type(-n + 3) "
        "> .nav-dd-menu:not(.nav-mega)"
    )
    assert edge_selector in REFRESH_CSS
    edge_rule = REFRESH_CSS.split(edge_selector, 1)[1].split("}", 1)[0]
    assert "left: auto;" in edge_rule
    assert "right: 0;" in edge_rule

    selector = (
        ".site-nav .nav-links > .nav-dd:nth-last-of-type(2) "
        ".nav-sub > .nav-dd-menu"
    )
    assert selector in REFRESH_CSS
    rule = REFRESH_CSS.split(selector, 1)[1].split("}", 1)[0]
    assert "left: auto;" in rule
    assert "right: 100%;" in rule
    assert ".site-nav .nav-dd > .nav-dd-menu,\n" in REFRESH_CSS
    assert "display: none;" in REFRESH_CSS.split(
        ".site-nav .nav-dd > .nav-dd-menu,", 1
    )[1].split("}", 1)[0]


def test_neural_web_public_view_exists_and_hides_proprietary_details() -> None:
    page = (ROOT / "templates" / "neural_web.html.j2").read_text(encoding="utf-8")
    assert "Signals do not arrive" in page
    assert "Evidence becomes a decision through three gates" in page
    assert "without exposing the proprietary scoring methods" in page
    assert "committee" not in page.lower()


def test_navigation_assets_remain_paired() -> None:
    # theme.js is intentionally baked with public Supabase config on the site
    # side; its specialized sync contract lives in tests/test_site_assets.py.
    for name in ("navigation-refresh.css", "logo_config.js", "stock-logos.js", "nav_market.js"):
        assert (ROOT / "templates" / name).read_bytes() == (ROOT / "site" / name).read_bytes()


def test_logo_token_is_runtime_only() -> None:
    source_config = (ROOT / "templates" / "logo_config.js").read_text(encoding="utf-8")
    update = (ROOT / "app" / "deploy" / "update.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "deploy-api-secrets.yml").read_text(encoding="utf-8")

    assert "pk_" not in source_config
    owned_runtime = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "templates/stock-logos.js",
            "templates/logo_config.js",
            "app/deploy/update.sh",
        )
    )
    assert not re.search(r"\bsk_[A-Za-z0-9_-]{16,}\b", owned_runtime)
    assert "LOGO_DEV_PUBLISHABLE_KEY" in update
    assert "secrets.LOGO_DEV_PUBLISHABLE_KEY" in workflow
