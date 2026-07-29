"""Contract checks for the Macro Dashboard → Terminal full-screen portal."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_overlay_asset_is_paired_and_published_by_the_builder():
    template = _read("templates/terminal_overlay.js")
    assert template == _read("site/terminal_overlay.js")
    assert '"terminal_overlay.js"' in _read("scripts/build_site.py")


def test_theme_opens_terminal_without_replacing_the_dashboard_document():
    for path in ("templates/theme.js", "site/theme.js"):
        code = _read(path)
        assert "terminalEmbedUrl" in code
        assert "'&embed=dashboard'" in code
        assert "terminalExistingUrl" in code
        assert "u.searchParams.set('embed', 'dashboard')" in code
        assert "openTerminal(target.ticker, a, target.url)" in code
        assert "window.MDXTerminalOverlay.open" in code
        assert "e.metaKey || e.ctrlKey || e.shiftKey || e.altKey" in code


def test_programmatic_stock_rows_use_the_same_portal():
    for path in ("templates/stocktable.js", "site/stocktable.js"):
        code = _read(path)
        assert "T.open(row.ticker || '', tr)" in code
        assert "window.location.href" in code  # resilient no-JS/load-error fallback


def test_overlay_has_keyboard_history_accessibility_and_strict_message_guards():
    code = _read("templates/terminal_overlay.js")
    assert "event.key === 'Escape'" in code
    assert "history.pushState" in code
    assert "history.back()" in code
    assert "role', 'dialog'" in code
    assert "aria-modal', 'true'" in code
    assert "event.source !== state.frame.contentWindow" in code
    assert "event.origin !== state.targetOrigin" in code
    assert "Press <kbd>Esc</kbd> to return to Dashboard" in code
    assert "window.MDXTerminalOverlay" in code


def test_overlay_keeps_one_warm_iframe_for_fast_reentry():
    code = _read("templates/terminal_overlay.js")
    assert "if (!state.booted)" in code
    assert "state.frame.src = config.url" in code
    assert "terminal:set-symbol" in code
    assert ".removeChild(state.frame)" not in code
