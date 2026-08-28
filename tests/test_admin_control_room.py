"""CCR-R0 Task 8: fixed-origin Control Room embed inside the admin shell."""
from __future__ import annotations

import re
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from admin.server import Handler, _CSP


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "admin" / "static" / "app.js"
STYLES = ROOT / "admin" / "static" / "styles.css"
CONTROL_ROOM_URL = "https://control.mastermind-x.com"


def _function_body(source: str, name: str) -> str:
    match = re.search(rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", source)
    assert match is not None, f"missing function {name}"
    opening = source.index("{", match.start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise AssertionError(f"unbalanced function {name}")


def test_control_room_nav_and_renderer_are_registered_exactly_once():
    """A missing/duplicate route or renderer registration must fail."""
    source = APP_JS.read_text(encoding="utf-8")

    assert len(re.findall(r"(?m)^\s*control_room:\s+NAV_ICO\(", source)) == 1
    assert source.count('["control_room", "Control Room"]') == 1
    assert len(re.findall(r"(?m)^RENDER\.control_room\s*=\s*renderControlRoom;", source)) == 1
    assert len(re.findall(r"(?m)^const CONTROL_ROOM_URL\s*=", source)) == 1


def test_control_room_renderer_uses_only_the_constant_origin_without_an_api_bridge():
    """Dynamic URLs, prefetches, postMessage, or admin-to-child state bridges must fail."""
    source = APP_JS.read_text(encoding="utf-8")
    body = _function_body(source, "renderControlRoom")

    assert f'const CONTROL_ROOM_URL = "{CONTROL_ROOM_URL}";' in source
    assert 'h(\'<div class="control-room-frame-shell"></div>\')' in body
    assert 'document.createElement("iframe")' in body
    assert 'frame.className = "control-room-frame"' in body
    assert "frame.src = CONTROL_ROOM_URL" in body
    assert 'frame.title = "Chairman Control Room"' in body
    assert 'frame.referrerPolicy = "no-referrer"' in body
    assert "shell.appendChild(frame)" in body
    assert "view.appendChild(shell)" in body
    for forbidden in ("api(", "fetch(", "post(", "postMessage", "location", "prompt(", "URLSearchParams", "?"):
        assert forbidden not in body
    prefetch = source.split("const TAB_PREFETCH_PATHS = {", 1)[1].split("};", 1)[0]
    assert "control_room" not in prefetch


def test_admin_response_allows_only_the_fixed_child_frame_and_keeps_anti_framing():
    """The console may host the child but must remain non-embeddable itself."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{httpd.server_address[1]}/", timeout=10
        ) as response:
            headers = dict(response.headers)
            assert response.status == 200
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Content-Security-Policy"] == _CSP
    assert "default-src 'none'" in _CSP
    assert "connect-src 'self'" in _CSP
    assert "base-uri 'none'" in _CSP
    assert "form-action 'self'" in _CSP
    assert "object-src 'none'" in _CSP
    assert "frame-ancestors 'none'" in _CSP
    assert _CSP.count(f"frame-src {CONTROL_ROOM_URL}") == 1


def test_control_room_iframe_fills_desktop_and_narrow_admin_view_without_overflow():
    """Removing width/height constraints or the narrow override must fail."""
    css = STYLES.read_text(encoding="utf-8")
    shell = re.search(r"\.control-room-frame-shell\s*\{([^}]+)\}", css, re.S)
    frame = re.search(r"\.control-room-frame\s*\{([^}]+)\}", css, re.S)
    narrow = re.search(r"@media\s*\(max-width:\s*900px\)\s*\{([^{}]*\.control-room-frame-shell[^{}]*\{[^}]+\}[^{}]*\.control-room-frame[^{}]*\{[^}]+\}|[^{}]*\.control-room-frame-shell\s*,\s*\.control-room-frame\s*\{[^}]+\})", css, re.S)

    assert shell is not None
    assert "width: 100%" in shell.group(1)
    assert "min-height: calc(100vh - 96px)" in shell.group(1)
    assert frame is not None
    for declaration in (
        "display: block",
        "width: 100%",
        "height: calc(100vh - 96px)",
        "min-height: 640px",
        "border: 1px solid var(--border)",
        "border-radius: var(--r-md)",
        "background: var(--bg)",
    ):
        assert declaration in frame.group(1)
    assert narrow is not None
    assert "min-height: calc(100vh - 132px)" in narrow.group(1)
    assert "height: calc(100vh - 132px)" in narrow.group(1)
