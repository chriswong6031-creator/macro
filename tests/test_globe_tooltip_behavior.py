"""Regression coverage for the landing-globe country overlays."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_country_tooltips_are_anchored_to_the_globe_stage():
    css_source = (ROOT / "scripts" / "build_vector.py").read_text()
    globe_js = (ROOT / "site" / "globe-deck.js").read_text()

    assert ".gd-tip{position:absolute" in css_source
    assert ".gd-tip{position:fixed" not in css_source
    assert "var gx = W / 2, gy = H / 2;" in globe_js
    assert "x = Math.max(pad, Math.min(x, W - tw - pad));" in globe_js
    assert "y = Math.max(pad, Math.min(y, H - th - pad));" in globe_js


def test_country_tooltips_animate_in_and_out():
    css_source = (ROOT / "scripts" / "build_vector.py").read_text()
    globe_js = (ROOT / "site" / "globe-deck.js").read_text()

    assert ".gd-tip.is-visible" in css_source
    assert "prefers-reduced-motion: reduce){.gd-tip{transition:none}" in css_source
    assert "function revealTip(cc)" in globe_js
    assert "function concealTip(immediate)" in globe_js
    assert "tip.classList.add(\"is-visible\")" in globe_js
    assert "tip.classList.remove(\"is-visible\")" in globe_js


def test_hub_root_paints_the_selected_theme_without_negative_z_escape():
    css_source = (ROOT / "scripts" / "build_vector.py").read_text()

    assert "html{overflow-x:hidden;background:var(--bg);color-scheme:dark}" in css_source
    assert 'html[data-theme="light"]{color-scheme:light}' in css_source
    assert "position:relative;isolation:isolate;overflow-x:hidden" in css_source


def test_mobile_globe_is_touchless_and_scroll_safe():
    css_source = (ROOT / "scripts" / "build_vector.py").read_text()
    globe_js = (ROOT / "site" / "globe-deck.js").read_text()

    assert "@media (hover:none) and (pointer:coarse)" in css_source
    assert ".gd-stage{pointer-events:none}" in css_source
    assert ".gd-canvas{touch-action:pan-y;cursor:default}" in css_source
    assert 'if (e.pointerType === "touch") return;' in globe_js
    assert "if (touchlessMobile) return;" in globe_js
    assert 'matchMedia("(hover: none) and (pointer: coarse)").matches' in globe_js
