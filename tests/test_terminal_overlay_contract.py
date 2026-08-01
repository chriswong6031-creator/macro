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


def test_overlay_has_keyboard_accessibility_and_strict_message_guards():
    code = _read("templates/terminal_overlay.js")
    assert "event.key === 'Escape'" in code
    assert "history.pushState" not in code
    assert "history.back()" not in code
    assert "The Terminal is an overlay, not a navigation" in code
    assert "role', 'dialog'" in code
    assert "aria-modal', 'true'" in code
    assert "event.source !== state.frame.contentWindow" in code
    assert "event.origin !== state.targetOrigin" in code
    assert "Press <kbd>Esc</kbd> to return to Dashboard" in code
    assert "window.MDXTerminalOverlay" in code


def test_overlay_keeps_desktop_warm_but_remounts_mobile_with_a_new_iframe_node():
    code = _read("templates/terminal_overlay.js")
    assert "if (!state.booted)" in code
    assert "frame.src = initialUrl" in code
    assert "terminal:set-symbol" in code
    assert "function shouldRemountFrame()" in code
    assert "window.matchMedia('(max-width: 700px)')" in code
    assert "/iPad|iPhone|iPod/.test(ua)" in code
    assert "if (!state.open && remount && state.frame) destroyFrame()" in code
    assert "function createFrame(initialUrl)" in code
    assert "function destroyFrame()" in code
    assert "state.frame = null" in code
    assert "old.parentNode.removeChild(old)" in code


def test_mobile_reopen_uses_a_fresh_document_and_defers_webkit_teardown():
    code = _read("templates/terminal_overlay.js")
    assert "function freshMobileLaunchUrl(raw)" in code
    assert "url.searchParams.set('_mm_launch'" in code
    assert "Date.now().toString(36) + '-' + state.launchSerial" in code
    assert "var launchUrl = remount ? freshMobileLaunchUrl(config.url) : config.url" in code
    assert "var frame = ensureFrame(launchUrl)" in code
    assert "old.classList.add('mmto-retiring-frame')" in code
    assert "old.style.display = 'none'" in code
    assert "old.src = 'about:blank'" not in code
    teardown = code.index("old.classList.add('mmto-retiring-frame')")
    deferred_remove = code.index("setTimeout(function ()", teardown)
    remove = code.index("old.parentNode.removeChild(old)", deferred_remove)
    assert teardown < deferred_remove < remove


def test_iframe_load_has_a_bounded_fail_open_path():
    code = _read("templates/terminal_overlay.js")
    assert "var FRAME_LOAD_FALLBACK_MS = 6000;" in code
    assert "var REPEAT_FRAME_LOAD_FALLBACK_MS = 2500;" in code
    assert "var HARD_LAUNCH_FALLBACK_MS = 9000;" in code
    assert "scheduleFrameLoadFallback(frame);" in code
    assert "scheduleFrameLoadFallback(frame, HARD_LAUNCH_FALLBACK_MS);" in code
    assert "state: 'frame-load-fallback'" in code
    assert "clearTimeout(state.frameLoadFallbackTimer)" in code


def test_overlay_restores_the_exact_dashboard_position_without_smooth_scroll():
    code = _read("templates/terminal_overlay.js")
    assert "state.scrollX = window.scrollX" in code
    assert "state.scrollY = window.scrollY" in code
    assert "document.documentElement.style.scrollBehavior = 'auto'" in code
    assert "window.scrollTo(restoreX, restoreY)" in code
    assert "requestAnimationFrame(restorePosition)" in code
    assert "focus({ preventScroll: true })" in code


def test_mobile_animation_avoids_transformed_or_clipped_iframe_ancestors():
    code = _read("templates/terminal_overlay.js")
    assert "@media(max-width:700px)" in code
    assert "clip-path:none!important;transform:none!important" in code
    assert ".mmto-frame{opacity:1!important;transform:none!important;transition:none!important}" in code


def test_close_reveals_dashboard_immediately_without_an_opaque_exit_frame():
    code = _read("templates/terminal_overlay.js")
    assert "var CLOSE_ANIMATION_MS = 300;" in code
    assert "#mm-terminal-overlay.is-closing{visibility:visible;pointer-events:none;background:transparent}" in code
    assert "if (remount) {" in code
    assert "destroyFrame();\n      unlockDashboard();\n      return;" in code
    assert "transition-duration:.16s,.28s,.28s" in code
    assert "}, CLOSE_ANIMATION_MS);" in code
    assert "}, 650);" not in code


def test_loader_is_medium_on_first_open_and_visual_ready_on_repeats():
    code = _read("templates/terminal_overlay.js")
    assert "var FIRST_LOADER_MS = 900;" in code
    assert "var REPEAT_LOADER_MS = 0;" in code
    assert "state.completedLaunches ? REPEAT_LOADER_MS : FIRST_LOADER_MS" in code
    assert "state.loadingStartedAt = Date.now()" in code
    assert "Math.max(0, minimum - elapsed)" in code
    assert "beginLoading(root)" in code
    assert "finishReady(data)" in code


def test_loader_reveals_on_chart_paint_not_react_shell_mount():
    code = _read("templates/terminal_overlay.js")
    assert "data.type === 'terminal:visual-ready'" in code
    assert "data.type === 'terminal:ready'" in code
    assert "scheduleShellFallback(data)" in code
    assert "data.type === 'terminal:symbol-ready'" in code
    visual_branch = code.index("data.type === 'terminal:visual-ready'")
    mark_ready = code.index("markReady(data)", visual_branch)
    shell_branch = code.index("data.type === 'terminal:ready'", mark_ready)
    assert mark_ready < shell_branch
