"""Landing information-architecture, brand, and disclosure-nav contracts."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML_PATHS = (ROOT / "templates" / "index.html", ROOT / "site" / "index.html")
CSS_PATHS = (
    ROOT / "templates" / "landing.css",
    ROOT / "site" / "landing.css",
)


def _primary_nav(text: str) -> str:
    start = text.index('<nav class="nav"')
    end = text.index("</nav>", start)
    return text[start:end]


@pytest.mark.parametrize("path", HTML_PATHS)
def test_landing_uses_mastermindx_entity_name(path: Path):
    text = path.read_text(encoding="utf-8")
    assert "<title>MastermindX " in text
    assert '<meta property="og:site_name" content="MastermindX">' in text
    assert '"@type":"Organization","name":"MastermindX"' in text
    assert '"@type":"WebSite","name":"MastermindX"' in text
    assert "MASTERMINDX" in _primary_nav(text)


@pytest.mark.parametrize("path", HTML_PATHS)
def test_primary_nav_has_three_accessible_disclosures(path: Path):
    nav = _primary_nav(path.read_text(encoding="utf-8"))
    triggers = re.findall(
        r'<button class="nav-trigger" id="([^"]+)"[^>]+'
        r'aria-expanded="false" aria-controls="([^"]+)"',
        nav,
    )
    assert len(triggers) == 3
    assert len({trigger_id for trigger_id, _ in triggers}) == 3
    assert len({panel_id for _, panel_id in triggers}) == 3
    for trigger_id, panel_id in triggers:
        panel_match = re.search(
            rf'<div class="nav-panel[^"]*" id="{re.escape(panel_id)}" '
            rf'aria-labelledby="{re.escape(trigger_id)}" hidden>.*?</div>\s*</div>',
            nav,
            flags=re.S,
        )
        assert panel_match
        assert 'role="menu"' not in panel_match.group(0)
        assert 'role="menuitem"' not in panel_match.group(0)


@pytest.mark.parametrize("path", HTML_PATHS)
def test_primary_nav_links_only_to_real_destinations(path: Path):
    nav = _primary_nav(path.read_text(encoding="utf-8"))
    for href in (
        "products/index.html",
        "products/market-terminal.html",
        "products/mastermind-ai.html",
        "products/market-dashboards.html",
        "https://www.mastermind-x.com/research_vault.html",
        "stocks/index.html",
        "tools/index.html",
        "learn/index.html",
        "blog/index.html",
        "support.html",
        "plans.html",
    ):
        assert f'href="{href}"' in nav
    assert 'href="#ai"' not in nav
    assert 'href="#pricing"' not in nav


@pytest.mark.parametrize("path", HTML_PATHS)
def test_mobile_toggle_and_existing_account_actions_remain(path: Path):
    nav = _primary_nav(path.read_text(encoding="utf-8"))
    assert (
        'id="nav-toggle" type="button" aria-expanded="false" '
        'aria-controls="primary-navigation"'
    ) in nav
    assert 'id="nav-login"' in nav
    assert 'href="https://app.mastermind-x.com/terminal?signin=1"' in nav
    assert 'id="nav-cta"' in nav
    assert 'href="https://app.mastermind-x.com/terminal?signup=1"' in nav
    assert 'id="gear-btn"' in nav


@pytest.mark.parametrize("path", HTML_PATHS)
def test_navigation_script_supports_keyboard_and_outside_close(path: Path):
    text = path.read_text(encoding="utf-8")
    controller = text[text.index("const MMX_NAV"):text.index("/* ───── nav settings")]
    for behavior in ("ArrowDown", "ArrowUp", "Escape", "pointerdown", "focusout"):
        assert behavior in controller
    assert "aria-expanded" in controller
    assert "panel.hidden" in controller
    assert "matchMedia('(max-width: 900px)')" in controller


def test_landing_plain_copy_pairs_match():
    assert HTML_PATHS[0].read_bytes() == HTML_PATHS[1].read_bytes()
    assert CSS_PATHS[0].read_bytes() == CSS_PATHS[1].read_bytes()


@pytest.mark.parametrize("path", HTML_PATHS)
def test_chinese_hero_uses_optically_centered_authored_lines(path: Path):
    text = path.read_text(encoding="utf-8")
    start = text.index('<h1 data-adtest-slot="hero_headline"')
    hero = text[start:text.index("</h1>", start)]
    data_zh = re.search(r'data-zh="([^"]+)"', hero)
    assert data_zh
    assert data_zh.group(1).count("zh-line-punct") == 2

    cfg_start = text.index('<script type="application/json" id="mm-adtest">')
    cfg_start = text.index(">", cfg_start) + 1
    cfg = json.loads(text[cfg_start:text.index("</script>", cfg_start)])
    for arm in cfg["arms"]:
        zh = arm["copy"]["hero_headline"]["zh"]
        if "。" in zh:
            assert "zh-line-punct" in zh

    css = CSS_PATHS[0].read_text(encoding="utf-8")
    assert 'html[data-lang="zh"] .cov-copy h1 .zh-line{' in css
    assert 'html[data-lang="zh"] .cov-copy h1 .zh-line-punct{' in css
    assert "transform:translateX(.26em)" in css


def test_mobile_navigation_css_is_an_in_flow_accordion():
    css = CSS_PATHS[0].read_text(encoding="utf-8")
    assert "@media (max-width:900px)" in css
    assert ".nav-links.open{display:flex}" in css
    assert ".nav-panel,.nav-panel-research,.nav-panel-resources{position:static" in css
    assert "max-height:calc(100dvh - 76px)" in css
