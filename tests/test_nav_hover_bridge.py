import hashlib
import re
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
START_HTML = (ROOT / "site" / "start.html").read_text(encoding="utf-8")
MACRO_HTML = (ROOT / "site" / "macro.html").read_text(encoding="utf-8")

# The cache-buster the theme.js -> account.js -> nav_market.js chain is pinned
# to, and a digest of the payload that key is responsible for busting. They MUST
# move together -- see test_nav_release_key_moves_with_the_payload_it_busts.
NAV_RELEASE_KEY = "20260810-stocks-hub-movers"
NAV_PAYLOAD_DIGEST = "5a2095a9"


def _payload_digest() -> str:
    """First 8 hex of sha256 over the two assets fetched at the fixed key.

    The key is redacted out of each body before hashing, so bumping the key does
    not perturb the digest -- the two constants stay independent and a bump is
    one edit, not a chase. theme.js is deliberately excluded: it is referenced
    from HTML, so optimize_assets.py content-hashes it and it self-busts.
    """
    digest = hashlib.sha256()
    for text in (TEMPLATE_JS, TEMPLATE_ACCOUNT_JS):
        digest.update(re.sub(r"\d{8}-[\w-]+", "<KEY>", text).encode("utf-8"))
    return digest.hexdigest()[:8]


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


def test_earnings_wire_runtime_bridge_backfills_only_stale_core_research_menus() -> None:
    bridge = TEMPLATE_JS.split("function ensureEarningsWireCard(menu)", 1)[1].split(
        "function enhanceResearchMenu(links)", 1
    )[0]
    enhance = TEMPLATE_JS.split("function enhanceResearchMenu(links)", 1)[1].split(
        "/* ---- preference", 1
    )[0]

    # The static template remains authoritative; the runtime only fills the
    # deployment gap for old rendered pages and then sees the static card.
    assert "menu.querySelector('[data-nav-file=\"earnings_wire\"]')" in bridge
    assert "/(?:Core Research|核心研究)/" in bridge
    assert "data-nav-file', 'earnings_wire'" in bridge
    assert "mega-item nm-feat" in bridge
    assert "icon-drawing nm-ic cyan" in bridge
    assert "MOCKUP_ICON_PATHS.earnings_wire" in bridge
    assert "Earnings Wire" in bridge
    assert "财报情报线" in bridge
    assert "Verified calls, weekly intelligence and company context" in bridge
    assert "已核验电话会、每周情报与公司语境" in bridge
    assert "prefixOf(dropdown) : '') + 'stocks/earnings/index.html'" in bridge
    assert "fileOf(cards[j]) === 'fundamental_forensics.html'" in bridge

    # Backfill runs before the one-time mockup normalization guard, so repeated
    # calls remain safe while a newer static render simply skips the insertion.
    assert enhance.index("ensureEarningsWireCard(menu);") < enhance.index(
        "data-mockup-exact"
    )


def test_primary_public_dashboards_ship_the_static_earnings_wire_card() -> None:
    marker = 'data-nav-file="earnings_wire" href="stocks/earnings/index.html"'
    for html in (START_HTML, MACRO_HTML):
        assert html.count(marker) == 1
        assert "Earnings Wire" in html
        assert "财报情报线" in html


def test_hover_gap_release_uses_fresh_immutable_asset_chain() -> None:
    assert f"account.js?v={NAV_RELEASE_KEY}" in TEMPLATE_THEME_JS
    assert f"account.js?v={NAV_RELEASE_KEY}" in SITE_THEME_JS
    assert f"nav_market.js?v={NAV_RELEASE_KEY}" in TEMPLATE_ACCOUNT_JS
    for stale in (
        "20260730-exact6",
        "20260730-exact7",
        "20260731-folded2",
        "20260801-crossfade",
        "20260806-zh-megamenu",
        "20260803-onemenu",
        "20260806-us-confluence",
        "20260807-post-sweep",
        "20260807-mm-icons",
        "20260808-zh-natural",
        "20260809-market-memory",
    ):
        assert stale not in TEMPLATE_THEME_JS
        assert stale not in SITE_THEME_JS
        assert stale not in TEMPLATE_ACCOUNT_JS


def test_nav_release_key_moves_with_the_payload_it_busts() -> None:
    """A nav asset change must be accompanied by a release-key bump.

    theme.js -> account.js -> nav_market.js is a fixed-URL chain served
    `immutable, max-age=31536000` (Caddyfile @public_versioned). account.js and
    nav_market.js are fetched at this hand-written key, NOT at a content hash --
    optimize_assets.py only stamps refs inside site/**/*.html, never an `s.src`
    built in JS. So a nav change that does not move the key is invisible to every
    returning visitor for a year, while shipping clean to anyone with a cold
    cache -- the most confusing possible failure, because the person verifying it
    in a fresh browser sees the new menu and calls it live.

    That is not hypothetical. #4512 rewrites the market mega menu into Chinese
    (13 -> 131 zh lines in nav_market.js) against this unchanged key, so returning
    visitors in China would have kept the English menu. Four earlier keys in the
    stale list above (exact6, exact7, folded2, crossfade) show the bump is a
    forgettable ritual, and pinning the literal key cannot catch a miss -- that
    assertion fails when you bump the key, not when you forget to.

    So the payload is pinned separately here: touch nav_market.js or account.js
    and this fails, naming the bump you owe.
    """
    assert _payload_digest() == NAV_PAYLOAD_DIGEST, (
        "templates/nav_market.js or templates/account.js changed, but they are "
        f"served `immutable, max-age=31536000` at the fixed key {NAV_RELEASE_KEY!r} "
        "-- returning visitors would keep the year-cached OLD nav menu and never "
        "see this change. Bump the key in templates/theme.js, site/theme.js, "
        "templates/account.js and site/account.js (and NAV_RELEASE_KEY above), "
        f"then set NAV_PAYLOAD_DIGEST = {_payload_digest()!r}. "
        "Both constants move together or the bump did not happen."
    )


def test_trigger_row_carries_an_invisible_hover_bridge() -> None:
    """The 2px inter-trigger gutter and the trigger-to-panel air gap must both
    sit inside a .nav-dd's hover tree, or a horizontal traverse fires
    pointerleave and drops the open panel."""
    # .nav-market-dd / .nav-mega-dd are position:static, so theme.css's
    # `.nav-dd::after` bridge cannot serve them — the zone lives on the link.
    assert (
        ".site-nav .nav-links > .nav-dd > a.nav-link,\n"
        "  .topbar .nav-links > .nav-dd > a.nav-link { position: relative; }"
    ) in TEMPLATE_CSS
    bridge = TEMPLATE_CSS.split(
        ".site-nav .nav-links > .nav-dd > a.nav-link::after,", 1
    )[1].split("}", 1)[0]
    assert "content: \"\";" in bridge
    assert "position: absolute;" in bridge
    # sideways reach closes the gutter; depth is the JS-measured real gap
    assert "left: -3px;" in bridge
    assert "right: -3px;" in bridge
    assert "bottom: calc(0px - var(--nav-bridge, 0px));" in bridge
    assert "root.style.setProperty('--nav-bridge'" in TEMPLATE_JS
    assert "Math.min(24, gap)" in TEMPLATE_JS


def test_switching_menus_cross_fades_over_one_morphing_plate() -> None:
    """Switching triggers must not close-then-reopen. Both panels are pinned to
    one animated height so their chromes read as a single plate, and only the
    contents cross-fade — with a drift that follows the traverse direction."""
    for token in (
        "--nav-open: 150ms",
        "--nav-close: 110ms",
        "--nav-swap: 100ms",
        "--nav-morph: 170ms",
        "--nav-drift: 10px",
    ):
        assert token in TEMPLATE_CSS

    # one plate: both sides of the crossing share the measured height
    plate = TEMPLATE_CSS.split(
        ".site-nav .nav-dd-menu.mega-menu.nav-panel-out,", 1
    )[1].split("}", 1)[0]
    assert "height: var(--nav-plate-h, auto);" in plate
    assert "transition: height var(--nav-morph) var(--nav-ease);" in plate
    assert "opacity: 1;" in plate

    # the incoming panel drops its own chrome so the two never composite
    chrome = TEMPLATE_CSS.split(
        ".site-nav .nav-dd-menu.mega-menu.nav-panel-in.nav-panel-in,", 1
    )[1].split("}", 1)[0]
    assert "background: transparent;" in chrome
    assert "border-color: transparent;" in chrome
    assert "box-shadow: none;" in chrome

    # directional content drift
    assert "transform: translateX(var(--nav-drift));" in TEMPLATE_CSS
    assert "transform: translateX(calc(var(--nav-drift) * -1));" in TEMPLATE_CSS

    # A running animation outranks normal declarations, so the entrance kill
    # must out-specify the entrance rule rather than merely follow it.
    assert (
        ".site-nav .nav-dd.nav-hover-open > .nav-dd-menu.mega-menu.nav-panel-swapped"
    ) in TEMPLATE_CSS

    # the exit is quicker than the entrance and survives display:none
    closing = TEMPLATE_CSS.split(
        ".site-nav .nav-dd-menu.mega-menu.nav-panel-closing,", 1
    )[1].split("}", 1)[0]
    assert "display: grid;" in closing
    assert "visibility: visible;" in closing
    assert "transition: opacity var(--nav-close) ease-out" in closing

    # controller wiring
    for marker in (
        "function crossFade(fromDd, toDd)",
        "function naturalHeight(menu)",
        "root.style.setProperty('--nav-plate-h'",
        "root.style.setProperty('--nav-drift'",
        "order(toDd) > order(fromDd) ? 1 : -1",
        "void incoming.offsetWidth;",
        "prefersReducedMotion()",
    ):
        assert marker in TEMPLATE_JS
    # the measurement must commit its hidden state, or the incoming contents
    # never fade in (the opacity:0 start reads as a transition target).
    measure = TEMPLATE_JS.split("function naturalHeight(menu)", 1)[1].split(
        "\n  }", 1
    )[0]
    assert "void menu.offsetHeight;" in measure


def test_panel_choreography_is_killed_by_name_under_reduced_motion() -> None:
    """Repo law: a reduced-motion kill block names its pseudo-elements."""
    from tests.test_navigation_refresh import media_block_containing

    block = media_block_containing(
        TEMPLATE_CSS,
        "@media (prefers-reduced-motion: reduce) {",
        ".site-nav .nav-dd-menu.mega-menu.nav-panel-in",
    )
    for selector in (
        ".site-nav .nav-dd-menu.mega-menu.nav-panel-in",
        ".site-nav .nav-dd-menu.mega-menu.nav-panel-out",
        ".site-nav .nav-dd-menu.mega-menu.nav-panel-closing",
        ".site-nav .nav-dd-menu.mega-menu::before",
        ".site-nav .nav-dd-menu.mega-menu::after",
        ".topbar .nav-dd-menu.mega-menu::before",
        ".topbar .nav-dd-menu.mega-menu::after",
        ".site-nav .nav-links > .nav-dd > a.nav-link::after",
        ".topbar .nav-links > .nav-dd > a.nav-link::after",
    ):
        assert selector in block, selector
    assert "animation: none !important;" in block
    assert "transition-duration: 0s !important;" in block
    assert "animation-duration: 0s !important;" in block


def test_nested_pages_resolve_market_nav_from_theme_asset_root() -> None:
    """Every nested estate must load the one shared market-menu runtime."""
    for source in (TEMPLATE_THEME_JS, SITE_THEME_JS):
        assert "document.currentScript" in source
        assert 'script[src$="theme.js"],script[src*="theme.js?"]' in source
        assert "var _mmSharedAssetRoot" in source
        assert "new URL('.', _mmThemeScript" in source
        assert source.count("var pfx = _mmSharedAssetRoot;") == 3
        assert "location.pathname.indexOf('/sectors/')" not in source
        assert f"s.src = pfx + 'account.js?v={NAV_RELEASE_KEY}'" in source


def test_research_icon_bridge_never_stomps_an_unknown_card() -> None:
    """The Mastermind twins must not wear one glyph (operator report 2026-08-07).

    enhanceResearchMenu's icon leg is a compatibility bridge for LEGACY pages:
    it rewrites a card's icon to the mockup drawing when the card's file is in
    MOCKUP_RESEARCH_ICON_BY_FILE.  Its old fallback — `|| ['dashboard', '']` —
    stomped every UNKNOWN card with the same default square, so the adjacent
    "Mastermind Portfolio" and "Mastermind Bot" cards (and Filing Forensics and
    Stock Seasonality) all rendered byte-identical glyphs and the two Mastermind
    cards read as one product listed twice.  Cards born after the mockup era
    already ship their real icon-drawing markup server-side, so the exact
    normalisation for an unknown card is to leave it alone.
    """
    for source in (TEMPLATE_JS, SITE_JS):
        # the stomp is gone, in the one place it lived
        assert "|| ['dashboard', '']" not in source
        # unknown card => no icon rewrite (the gate rides the map lookup)
        assert "var oldIcon = iconSpec ? item.querySelector('.nm-ic') : null;" in source
        # the two Mastermind cards are KNOWN, each with its own glyph + tint
        assert "'watchlist.html': ['portfolio', 'violet']" in source
        assert "'bot.mastermind-x.com': ['bot', 'cyan']" in source
        # and the glyphs are the template's own drawings, not the dashboard square
        assert "portfolio: '<path class=\"ghost\" d=\"M25 7a17 17 0 0 1 16 16\"/>" in source
        assert "bot: '<path d=\"M17 11V6M24 11V6M31 11V6" in source
        # the two drawings must stay DISTINCT from each other and from the default
        import re as _re
        icons = dict(_re.findall(r"\n    (portfolio|bot): '([^']+)'", source))
        assert icons["portfolio"] != icons["bot"]
        dashboard = _re.search(r"\n    dashboard: '([^']+)'", source).group(1)
        assert icons["portfolio"] != dashboard and icons["bot"] != dashboard
