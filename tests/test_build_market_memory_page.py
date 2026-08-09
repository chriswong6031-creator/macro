"""Static-shell and integration contracts for the Market Memory product page."""

from __future__ import annotations

from pathlib import Path

from lib import seo
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
    assert "macro states are recomputed today" in html
    assert "recomputed historical episodes" in html
    assert "audited historical episodes" not in html
    assert all(line == line.rstrip() for line in html.splitlines())


def test_rendered_market_memory_artifact_keeps_temporal_disclosures() -> None:
    html = (ROOT / "site" / "market_memory.html").read_text(encoding="utf-8")

    assert "macro states are recomputed today" in html
    assert "recomputed historical episodes" in html
    assert "audited historical episodes" not in html


def test_market_memory_client_uses_only_the_owned_read_api() -> None:
    source = (ROOT / "site" / "market_memory.js").read_text(encoding="utf-8")

    assert "'/api/market-memory/v1'" in source
    assert "request('/macro?limit=6')" in source
    assert "request('/symbol/'" in source
    assert "basisPoints(query.spread_2s10s)" in source
    assert "data.historical_basis" in source
    assert "error.status === 403" in source
    assert "macroRequest: 0" in source
    assert "requestId !== state.macroRequest" in source
    assert "requestId !== state.symbolRequest" in source
    assert "function redactForSignOut()" in source
    assert "state.macroRequest += 1" in source
    assert "state.symbolRequest += 1" in source
    assert "state.macro = null" in source
    assert "state.symbol = null" in source
    assert "if (!user) {" in source
    assert "redactForSignOut();" in source
    assert "退出登录后，此视图中的账户上下文将被清除。" in source
    assert "退出登录后，此视图中的个股上下文将被清除。" in source
    assert "已验证" not in source
    assert 'data-mm-action="signin"' in source
    assert "window.MDXAuth.open('signin')" in source
    assert "window.MDXAuth.onChange" in source
    assert "signin.html" not in source
    assert "konseki" not in source.lower()
    assert "may_train_prophet" not in source


def test_market_memory_assets_are_template_owned_and_byte_identical() -> None:
    for name in ("market_memory.css", "market_memory.js"):
        assert (ROOT / "templates" / name).read_bytes() == (
            ROOT / "site" / name
        ).read_bytes()


def test_market_memory_is_wired_into_build_router_and_navigation() -> None:
    build_source = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    nav_source = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")

    assert "build_market_memory_page" in build_source
    assert "app.market_memory" in app_source
    assert "market_memory.html" in nav_source
    assert "Put today beside comparable episodes" in nav_source
    card_start = nav_source.index('href="{{ NP }}market_memory.html"')
    card_end = nav_source.index("</a>", card_start)
    assert "nm-tier" not in nav_source[card_start:card_end]


def test_market_memory_public_shell_is_discoverable_but_payload_stays_api_owned() -> (
    None
):
    assert seo.is_public_path("/market_memory.html") is True
    names = {name for name, _url, _path in seo.discover_core_pages(ROOT / "site")}
    assert "market_memory" in names

    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    for matcher in ("gate_html", "gate_html_err"):
        block = caddy.split(f"@{matcher} {{", 1)[1].split("}", 1)[0]
        assert "/market_memory.html" in block


def test_market_memory_symbol_reader_uses_bounded_r2_projection() -> None:
    engine_source = (ROOT / "engine" / "neuralweb" / "market_memory.py").read_text(
        encoding="utf-8"
    )
    api_source = (ROOT / "app" / "market_memory.py").read_text(encoding="utf-8")

    assert '"site" / "stockdata"' not in engine_source
    assert "stock_record" in engine_source
    assert "_project_event_atlas" in engine_source
    assert "event_atlas.live_state(" not in engine_source
    assert "from engine import event_atlas" not in engine_source
    assert "R2_PUBLIC_BASE" in api_source
    assert "allow_redirects=False" in api_source
    assert "_MAX_STOCKDATA_BYTES" in api_source


def test_direct_builder_cli_bootstraps_repository_imports() -> None:
    source = (ROOT / "scripts" / "build_market_memory_page.py").read_text(
        encoding="utf-8"
    )

    assert "sys.path.insert(0, str(_REPO_ROOT))" in source
