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


def test_hover_gap_has_pointer_grace_without_geometry_change() -> None:
    assert "function bindHoverSafeDropdowns(links)" in TEMPLATE_JS
    assert "data-nav-hover-safe" in TEMPLATE_JS
    assert "window.innerWidth > 900 && fineHover.matches" in TEMPLATE_JS
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

    # The visible spacing remains the approved mockup spacing; only its
    # interaction lifetime changes.
    assert "top: calc(100% + 7px)" not in TEMPLATE_CSS


def test_hover_gap_assets_remain_byte_identical() -> None:
    assert TEMPLATE_CSS == SITE_CSS
    assert TEMPLATE_JS == SITE_JS
    assert TEMPLATE_ACCOUNT_JS == SITE_ACCOUNT_JS


def test_hover_gap_release_uses_fresh_immutable_asset_chain() -> None:
    assert "account.js?v=20260730-exact8" in TEMPLATE_THEME_JS
    assert "account.js?v=20260730-exact8" in SITE_THEME_JS
    assert "nav_market.js?v=20260730-exact8" in TEMPLATE_ACCOUNT_JS
    assert "20260730-exact6" not in TEMPLATE_THEME_JS
    assert "20260730-exact6" not in SITE_THEME_JS
    assert "20260730-exact6" not in TEMPLATE_ACCOUNT_JS
    assert "20260730-exact7" not in TEMPLATE_THEME_JS
    assert "20260730-exact7" not in SITE_THEME_JS
    assert "20260730-exact7" not in TEMPLATE_ACCOUNT_JS
