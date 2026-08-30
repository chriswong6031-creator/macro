"""Regression contract for Intelligence Hub ticker → Terminal routing.

The Hub is a nightly-generated page.  Its ticker labels are intentionally emitted as
plain ``.tk`` spans by the renderer, so the durable integration belongs in the shared
``templates/theme.js`` runtime: on ``body.page-hub`` it promotes inert ticker spans to
canonical ``stock.html#TICKER`` anchors.  The existing Terminal controller then owns
prefetch, iframe overlay opening, analytics, modified-click semantics, and the
``MM_TERMINAL=false`` analyzer fallback.

These tests are source-contract tests on purpose.  They guard the canonical shared
runtime rather than generated ``site/intelligence_hub.html`` bytes, which are replaced
by the engine render throughout the day.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "templates" / "theme.js"
HUB = ROOT / "site" / "intelligence_hub.html"


def _theme() -> str:
    return THEME.read_text(encoding="utf-8")


def _hub() -> str:
    return HUB.read_text(encoding="utf-8")


def test_hub_tickers_are_promoted_to_canonical_terminal_analyzer_links() -> None:
    """The shared runtime must make inert Hub .tk labels routable by terminalTarget()."""
    src = _theme()

    assert "function initHubTerminalTickerLinks()" in src
    assert "classList.contains('page-hub')" in src
    assert "querySelectorAll('.tk')" in src
    assert "mm-terminal-ticker-link" in src
    assert "stock.html#" in src
    assert "encodeURIComponent(ticker)" in src


def test_hub_ticker_promotion_preserves_existing_interactive_controls() -> None:
    """Never nest a new ticker anchor inside an existing link/button/control."""
    src = _theme()

    assert "a,button,input,select,textarea,[role=\"button\"],[role=\"link\"]" in src


def test_hub_ticker_promotion_accepts_dot_symbols_and_rejects_prose() -> None:
    """BRK.B is a real Hub symbol; arbitrary text must not become a stock route."""
    src = _theme()
    hub = _hub()

    assert '<span class="tk">BRK.B</span>' in hub
    assert "/^[A-Z0-9][A-Z0-9.-]{0,15}$/" in src


def test_hub_does_not_define_a_second_terminal_iframe_controller() -> None:
    """The repair must reuse terminalTarget/openTerminal instead of inventing another overlay."""
    src = _theme()

    # Exactly one canonical overlay-opening callsite remains in the shared controller.
    assert src.count("openTerminal(target.ticker, a, target.url)") == 1
