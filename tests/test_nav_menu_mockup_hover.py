from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_CSS = (ROOT / "templates" / "navigation-refresh.css").read_text(
    encoding="utf-8"
)
SITE_CSS = (ROOT / "site" / "navigation-refresh.css").read_text(encoding="utf-8")


def test_template_and_site_refresh_css_stay_identical():
    assert TEMPLATE_CSS == SITE_CSS


def test_exact_menus_suppress_the_legacy_aurora_layer():
    selector = """.nav-dd-menu.mega-menu :is(a, button):is(
  .mega-item,
  .nav-market-item,
  .rail-link,
  .nav-market-rail-item,
  .nav-rail-item
)::before"""
    assert selector in TEMPLATE_CSS
    assert ")::after {" in TEMPLATE_CSS
    assert "content: none;" in TEMPLATE_CSS


def test_main_and_rail_hovers_keep_the_mockup_treatment():
    assert (
        ".nav-dd-menu.mega-menu :is(a, button):is("
        ".mega-item, .nav-market-item):hover {"
    ) in TEMPLATE_CSS
    assert "background: var(--mock-surface-hover);" in TEMPLATE_CSS
    assert """.nav-dd-menu.mega-menu :is(a, button):is(
  .rail-link,
  .nav-market-rail-item,
  .nav-rail-item
):hover {""" in TEMPLATE_CSS
    assert "color: var(--mock-blue-deep);" in TEMPLATE_CSS
