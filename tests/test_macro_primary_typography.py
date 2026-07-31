"""Regression guards for Macro's proportional primary-font data treatment."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "templates" / "_macro_attio_type.css.j2"
TEMPLATE = ROOT / "templates" / "dashboard.html.j2"
BUILT = ROOT / "site" / "macro.html"


def _built_type_sheet() -> str:
    built = BUILT.read_text(encoding="utf-8")
    hrefs = re.findall(r'href="(assets/css/[0-9a-f]{8}\.css)\?v=[0-9a-f]{8}"', built)
    for href in hrefs:
        css = (ROOT / "site" / href).read_text(encoding="utf-8")
        if "--font-data:" in css:
            return css
    raise AssertionError("Macro primary type sheet is not linked from the built page")


def test_macro_data_role_uses_inter_and_native_san_francisco():
    css = SHEET.read_text(encoding="utf-8")

    assert '--font-data: Inter, "SF Pro Text", "SF Pro Display", -apple-system' in css
    assert "--font-mono: var(--font-data)" in css
    assert "font-family: var(--font-data)" in css
    assert "JetBrains" not in css
    assert "slashed-zero" not in css
    assert '"zero" 1' not in css


def test_macro_ticker_labels_use_inter_display():
    css = SHEET.read_text(encoding="utf-8")

    ticker_rule = css.rsplit(".mx5-mkt-ticker,", 1)[1].split("}", 1)[0]
    assert "font-family: var(--font-display)" in ticker_rule
    assert "font-weight: 600" in ticker_rule


def test_macro_no_longer_preloads_or_ships_jetbrains_mono():
    template = TEMPLATE.read_text(encoding="utf-8")
    built = BUILT.read_text(encoding="utf-8")
    built_css = _built_type_sheet()

    assert "JetBrainsMono" not in template
    assert "JetBrainsMono" not in built
    assert "JetBrains" not in built_css
    assert not (ROOT / "templates" / "fonts" / "JetBrainsMono-100-800.woff2").exists()
    assert not (ROOT / "site" / "fonts" / "JetBrainsMono-100-800.woff2").exists()


def test_built_macro_contains_primary_data_stack():
    built_css = _built_type_sheet()

    assert '--font-data: Inter, "SF Pro Text", "SF Pro Display", -apple-system' in built_css
    assert "--font-mono: var(--font-data)" in built_css
    assert "slashed-zero" not in built_css
    assert '"zero" 1' not in built_css
