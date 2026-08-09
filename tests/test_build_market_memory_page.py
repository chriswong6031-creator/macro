"""Static-shell and integration contracts for the Market Memory product page."""
from __future__ import annotations

from pathlib import Path

from scripts import build_market_memory_page

ROOT = Path(__file__).resolve().parent.parent


def test_market_memory_shell_renders_without_market_data() -> None:
    html = build_market_memory_page.render(ROOT)

    assert "Market Memory" in html
    assert 'id="mm-macro-episodes"' in html
    assert 'id="mm-symbol-form"' in html
    assert 'id="mm-grid-list"' in html
    assert 'src="market_memory.js"' in html
    assert "No ranking · no gating · no sizing · no Prophet training authority" in html
    assert "survivor-biased" in html


def test_market_memory_client_uses_only_the_owned_read_api() -> None:
    source = (ROOT / "site" / "market_memory.js").read_text(encoding="utf-8")

    assert "'/api/market-memory/v1'" in source
    assert "request('/macro?limit=6')" in source
    assert "request('/symbol/'" in source
    assert "basisPoints(query.spread_2s10s)" in source
    assert "error.status === 403" in source
    assert "requestId !== state.symbolRequest" in source
    assert "konseki" not in source.lower()
    assert "may_train_prophet" not in source


def test_market_memory_is_wired_into_build_router_and_navigation() -> None:
    build_source = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    nav_source = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")

    assert "build_market_memory_page" in build_source
    assert "app.market_memory" in app_source
    assert "market_memory.html" in nav_source
    assert "Put today beside comparable episodes" in nav_source
