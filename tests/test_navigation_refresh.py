from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAV = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
THEME_JS = (ROOT / "templates" / "theme.js").read_text(encoding="utf-8")
SITE_THEME_JS = (ROOT / "site" / "theme.js").read_text(encoding="utf-8")
MARKET_JS = (ROOT / "templates" / "nav_market.js").read_text(encoding="utf-8")
REFRESH_CSS = (ROOT / "templates" / "navigation-refresh.css").read_text(encoding="utf-8")


def media_block_containing(css: str, opener: str, marker: str) -> str:
    """The top-level `@media` block opened by `opener` that contains `marker`.

    Selecting it by CONTENT rather than by position: these tests used to take
    the LAST block of a given kind, which quietly asserted "no one may ever
    append another mobile / reduced-motion block to this stylesheet". Adding
    one (the folded-country sheet, 2026-08-04) broke tests that had nothing to
    do with it. Top-level blocks close on a column-0 `}`; every rule inside is
    indented, so `\\n}` bounds a block exactly.
    """
    blocks: list[str] = []
    idx = 0
    while (i := css.find(opener, idx)) >= 0:
        j = css.find("\n}", i + len(opener))
        blocks.append(css[i: j if j >= 0 else len(css)])
        idx = i + len(opener)
    for block in blocks:
        if marker in block:
            return block
    raise AssertionError(
        f"no `{opener}` block in this stylesheet contains {marker!r} "
        f"({len(blocks)} block(s) searched)"
    )


def research_rail(nav: str) -> str:
    """The Research mega-menu's Explore rail (`<aside class="mega-rail …>` … `</aside>`).

    Sliced by CONTENT so a placement guard can say "not in the rail" instead of
    "not anywhere in the file" — the distinction matters because the Mastermind
    Bot link is legitimate in the Core Research grid and forbidden in the rail.
    """
    start = nav.find('<aside class="mega-rail')
    assert start >= 0, "the Research mega-menu lost its Explore rail"
    end = nav.find("</aside>", start)
    assert end >= 0, "the Explore rail is unclosed"
    return nav[start:end]


def core_research_grid(nav: str) -> str:
    """The Core Research section's `.item-grid`, sliced from its section label."""
    start = nav.find("Core Research")
    assert start >= 0, "the Research mega-menu lost its Core Research section"
    end = nav.find("</section>", start)
    assert end >= 0, "the Core Research section is unclosed"
    return nav[start:end]


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
        "stocks/earnings/index.html",
        "neural_web.html",
        "foresight.html",
        "state_of_themes.html",
        "radar.html",
        "confluence_screener.html",
    ):
        assert f'href="{{{{ NP }}}}{public_page}"' in NAV


def test_mastermind_bot_is_a_core_research_card_marked_pro() -> None:
    """The Bot's THIRD attempt at a nav home — this one in the Core Research grid.

    Twice reverted before (rail card #4078, header pill 2026-08-01), so this pins
    the placement, not just the presence: the card sits in the Core Research grid
    directly after Mastermind Portfolio, because Portfolio is the user's book and
    the Bot is the AI's own — the pair is the reason for the position.
    """
    grid = core_research_grid(NAV)
    assert 'href="https://bot.mastermind-x.com"' in grid

    # Adjacency: Portfolio, then Bot, then Reports. Position IS the design here.
    order = [NAV.find(h) for h in (
        '{{ NP }}watchlist.html"',
        'href="https://bot.mastermind-x.com"',
        '{{ NP }}reports.html"',
    )]
    assert all(i > 0 for i in order), order
    assert order == sorted(order), (
        "Mastermind Bot must sit between Mastermind Portfolio and Research Reports"
    )

    # External, and opened the way the Terminal cross-product link is opened.
    card = grid[grid.find('href="https://bot.mastermind-x.com"'):]
    card = card[:card.find("</a>")]
    assert 'target="_blank"' in card and 'rel="noopener"' in card

    # It must NOT reuse the reverted rail class — nav_market.js:724 deletes it.
    assert "nav-mastermind-cta" not in card

    # Static tier mark, visible to every tier (docs/TIER_PREVIEW_PATTERN.md):
    # the shell is shown to Free, the server gates the payload. Nothing about
    # this badge may become conditional or JS-driven.
    assert '<span class="nm-tier">PRO</span>' in card
    assert ".nm-tier" in REFRESH_CSS
    assert "/api/me" not in card

    # Bilingual, and honest in BOTH languages: this is a paper account, so the
    # ZH side must carry 模拟 and neither side may read as live trading.
    assert "Mastermind Bot" in card
    assert "Mastermind 交易机器人" in card
    assert "The AI’s own paper account — every trade explained" in card
    assert "AI 自己的模拟账户，每笔交易都附理由" in card
    assert "模拟" in card, "the ZH copy must say paper account, not live trading"

    # No translated text in title= (CI-guarded house law) and no emoji glyph —
    # the card draws the house monoline icon like every sibling in this grid.
    assert "title=" not in card
    assert 'class="icon-drawing nm-ic cyan"' in card


def test_approved_mockup_is_the_navigation_source_of_truth() -> None:
    for copy in (
        "Your complete market command center",
        "Search every published research note",
        "Verified calls, weekly intelligence and company context",
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
        "width: 300px",
    ):
        assert marker in REFRESH_CSS

    assert "MOCKUP_ICON_PATHS" in MARKET_JS
    assert "MOCKUP_RESEARCH_DESCRIPTION_BY_FILE" in MARKET_JS
    assert "legacy CSS-mask icon library" in MARKET_JS
    assert "{{ t('Crypto', '加密') }}" not in NAV
    assert "removeLegacyCryptoMenu(links)" in MARKET_JS
    for label in ("Crypto Intelligence", "Bitcoin Vector", "Allocation"):
        assert label in MARKET_JS
    assert 'aria-label="{{ t(' not in NAV


def test_global_cycles_uses_accessible_in_panel_drill() -> None:
    assert "data-nav-drill-open" in NAV
    assert "data-nav-drill-panel" in NAV
    assert "data-nav-drill-back" in NAV
    assert 'aria-expanded="false"' in NAV
    assert "data-nav-drill-panel inert" in NAV
    assert "initNavDrills()" in THEME_JS
    assert "panel.toggleAttribute('inert', !isOpen)" in THEME_JS
    assert "panel.setAttribute('inert', '')" in THEME_JS


def test_settings_close_is_not_overridden_by_gear_focus() -> None:
    """Returning focus to the gear must preserve a deliberate popover close."""
    for source in (THEME_JS, SITE_THEME_JS):
        assert (
            '.nav-settings:focus-within '
            '.nav-settings-btn[aria-expanded="true"] + .settings-pop'
        ) in source
        assert ".nav-settings:not(.settings-dismissed):hover .settings-pop" in source
        assert '.nav-settings:focus-within .settings-pop' not in source

        focusin = source.split("wrap.addEventListener('focusin'", 1)[1].split(
            "wrap.addEventListener('focusout'", 1
        )[0]
        # Pointer focus occurs before click, so one explicit pointer-intent flag
        # keeps click as the sole toggle while Tab focus still opens directly.
        assert "var _gearPointerDown = false;" in source
        assert "gear.addEventListener('pointerdown'" in source
        assert "_gearPointerDown = false;" in source
        assert "if (isOpen() || wrap.contains(e.relatedTarget)) return;" in focusin
        assert "if (e.target === gear && _gearPointerDown) return;" in focusin
        assert "open();" in focusin
        assert "wrap.classList.add('settings-dismissed');" in source
        assert "wrap.classList.remove('settings-dismissed');" in source
        assert "wrap.addEventListener('mouseenter'" in source


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

    assert ".nav-search.ticker-search.open { width: 300px; }" in REFRESH_CSS
    assert "@keyframes nrFanIn" in REFRESH_CSS
    assert "html:not([data-theme=\"light\"])" in REFRESH_CSS
    assert "@media (prefers-reduced-motion: reduce)" in REFRESH_CSS


def test_search_uses_volume_rank_and_controlled_saas_motion() -> None:
    assert "Number(a.v || a.vol || 0)" in THEME_JS
    assert "Highest-volume names from the latest session" in THEME_JS
    assert "pending === 0 || input.value.trim()" in THEME_JS
    assert "@keyframes mockupCardSettle" in REFRESH_CSS
    assert "@keyframes mockupResultSettle" in REFRESH_CSS
    assert "filter: blur(" not in REFRESH_CSS.split("@keyframes mockupCardSettle", 1)[1].split("@keyframes mockupMenuSwap", 1)[0]
    assert "closeSearch();" in THEME_JS.split("function go(x)", 1)[1].split("function rank(", 1)[0]
    assert "document.body.classList.add('nav-search-focus')" in THEME_JS
    assert "document.body.classList.remove('nav-search-focus')" in THEME_JS
    assert ".ticker-symbol," in REFRESH_CSS
    assert "text-overflow: ellipsis;" in REFRESH_CSS
    approved = REFRESH_CSS.split("APPROVED MOCKUP — SOURCE-OF-TRUTH PORT", 1)[1]
    assert "translate(62px, -31px)" not in approved
    assert 'font: 720 11px/1 -apple-system' in approved
    assert 'font: 680 12px/1 -apple-system' in approved


def test_compact_search_contains_exchange_qualified_tickers() -> None:
    """Long idle examples such as 600519.SS must stay inside the pill."""
    approved = REFRESH_CSS.split("APPROVED MOCKUP — SOURCE-OF-TRUTH PORT", 1)[1]
    search_rule = approved.split(".nav-search.ticker-search {", 1)[1].split("}", 1)[0]
    trigger_rule = approved.split(".ticker-search .search-trigger {", 1)[1].split("}", 1)[0]
    idle_rule = approved.split(".ticker-search .idle-ticker {", 1)[1].split("}", 1)[0]

    assert "width: 128px;" in search_rule
    assert "overflow: hidden;" in trigger_rule
    assert "flex: 1 1 auto;" in idle_rule
    assert "min-width: 0;" in idle_rule
    assert "overflow: hidden;" in idle_rule
    assert "text-overflow: ellipsis;" in idle_rule
    assert "white-space: nowrap;" in idle_rule
    assert "600519.SS" in THEME_JS


def test_top_level_menu_labels_use_regular_weight() -> None:
    approved = REFRESH_CSS.split("APPROVED MOCKUP — SOURCE-OF-TRUTH PORT", 1)[1]
    selector = ".site-nav .nav-links > .nav-dd > a.nav-link,"
    nav_rule = approved.split(selector, 1)[1].split("}", 1)[0]
    assert "font-weight: 450;" in nav_rule
    assert "font-weight: 530;" not in nav_rule


def test_product_header_has_one_page_independent_geometry() -> None:
    assert "body > nav.site-nav" in REFRESH_CSS
    rule = REFRESH_CSS.split("body > nav.site-nav", 1)[1].split("}", 1)[0]
    assert "width: min(1500px, calc(100vw - 32px)) !important;" in rule
    assert (
        "margin-left: calc((100% - min(1500px, calc(100vw - 32px))) / 2) "
        "!important;"
    ) in rule
    assert "transform:" not in rule
    assert "margin: 18px auto 16px !important;" in rule


def test_start_hub_uses_canonical_product_navigation_and_demotes_clock() -> None:
    source = (ROOT / "scripts" / "build_vector.py").read_text(encoding="utf-8")
    assert 'get_template("_site_nav.html.j2")' in source
    assert "+ _hub_product_nav_html()" in source
    assert "'<div class=\"hub-live-meta\">" in source
    assert "'<div class=\"hub-top\">'" not in source

    rendered = (ROOT / "site" / "start.html").read_text(encoding="utf-8")
    assert 'class="site-nav"' in rendered
    assert 'body class="hub-page"' in rendered
    assert 'class="hub-live-meta"' in rendered
    assert 'class="hub-top"' not in rendered


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

    # The two REVERTED Mastermind Bot entries stay reverted. Neither line ever
    # banned the URL — each pinned a specific dead form, and the bare-substring
    # spelling only looked like a URL ban because no live form existed yet:
    #
    #   · the Research-RAIL card (.nav-mastermind-cta, shipped 2026-07-29,
    #     removed 2026-07-30 by #4078). nav_market.js:724 still deletes that
    #     class from the rail at runtime, so re-using the name would make the
    #     entry vanish on every page. The class must stay unused, and the rail
    #     must stay free of the link — the Core Research grid is its home now.
    #   · the sitewide header pill (removed 2026-08-01 as a duplicate of the
    #     native mm_brain.js launcher) — see the shared-chrome check below.
    assert 'class="nav-mastermind-cta"' not in NAV
    assert "https://bot.mastermind-x.com" not in research_rail(NAV), (
        "the Bot link belongs in the Core Research grid, not the Explore rail — "
        "the rail form was reverted by #4078 and nav_market.js still strips it"
    )
    assert "Cleaner by design" in NAV
    assert "Detailed diagnostics and proprietary labs move to the admin console." in NAV
    shared_chrome = (ROOT / "templates" / "_site_nav.html.j2").read_text(encoding="utf-8")
    assert "mastermind-link" not in shared_chrome
    # The header's one external entry is Terminal. theme.js:1492 also strips any
    # `.nav-ctrls a[href*="bot.mastermind-x.com"]` at runtime; the source must not
    # rely on that, so the chrome carries no Bot link of any spelling.
    assert "bot.mastermind-x.com" not in shared_chrome
    assert 'href="https://app.mastermind-x.com"' in shared_chrome


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
    mobile_rules = media_block_containing(
        REFRESH_CSS, "@media (max-width: 900px)", ".ticker-search .ticker-input"
    )
    assert "iOS Safari zooms the page" in mobile_rules
    assert (
        ".ticker-search .ticker-input { font-size: 16px; }"
        in mobile_rules
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
