"""Contract tests for the authenticated Research Tools SPA directory."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "admin" / "static" / "app.js"
STYLES_CSS = ROOT / "admin" / "static" / "styles.css"
CADDY = ROOT / "app" / "deploy" / "Caddyfile"

TOOLS = (
    ("committee.html", "Neural Web Deep View"),
    ("measurement.html", "Calibration Lab"),
    ("crossasset.html", "Cross-Asset Diagnostics"),
    ("signal_lab.html", "Signal Lab"),
    ("tech_lab.html", "Technical Lab"),
    ("macro_signals.html", "Macro Signals"),
    ("factors.html", "Factors &amp; Seasonality"),
)


def _source() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _renderer(source: str) -> str:
    return source.split("RENDER.research_tools = () => {", 1)[1].split(
        "/* ---- EXPERIMENTS", 1
    )[0]


def test_research_tools_is_a_first_class_sidebar_route():
    source = _source()
    assert "research_tools: NAV_ICO(" in source
    assert '{ label: "Research", items: [["research_tools", "Research Tools"]] }' in source
    assert "RENDER.research_tools = () => {" in source


def test_research_tools_renderer_is_static_and_makes_no_api_call():
    renderer = _renderer(_source())
    assert "api(" not in renderer
    assert "fetch(" not in renderer
    assert "post(" not in renderer


def test_all_internal_surfaces_are_secure_new_tab_links():
    renderer = _renderer(_source())
    links = re.findall(
        r'<a class="rt-card[^"]*" href="([^"]+)" target="_blank" rel="noopener">',
        renderer,
    )
    assert links == [
        f"https://admin.mastermind-x.com/research-tools/{path}"
        for path, _ in TOOLS
    ]
    for _, label in TOOLS:
        assert f"<strong>{label}</strong>" in renderer


def test_internal_surfaces_are_admin_host_only():
    caddy = CADDY.read_text(encoding="utf-8")
    assert "handle_path /research-tools/*" in caddy
    assert "forward_auth 127.0.0.1:8787" in caddy
    assert "uri /api/auth-check" in caddy
    never_site = caddy.split("@never_site {", 1)[1].split("}", 1)[0]
    for path, _ in TOOLS:
        assert f"/{path}" in never_site


def test_research_copy_and_responsive_styles_keep_the_internal_boundary_clear():
    renderer = _renderer(_source())
    styles = STYLES_CSS.read_text(encoding="utf-8")
    assert "Internal diagnostics and proprietary methods" in renderer
    assert "Hidden from public navigation" in renderer
    assert renderer.count("<svg") >= 16
    assert "@media (max-width: 700px)" in styles
    assert ".rt-grid" in styles
