"""CCR-R0 Task 7: fail-closed Caddy boundary for the remote Control Room."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CADDY = ROOT / "app" / "deploy" / "Caddyfile"


def _site_block(text: str, host: str) -> str:
    """Return one literal host block using the Caddyfile's balanced braces."""
    match = re.search(rf"(?m)^{re.escape(host)}\s*\{{", text)
    assert match is not None, f"missing Caddy host: {host}"
    assert len(re.findall(rf"(?m)^{re.escape(host)}\s*\{{", text)) == 1
    start = match.start()
    opening = text.index("{", match.start())
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unbalanced Caddy host block: {host}")


def _control_block() -> str:
    return _site_block(CADDY.read_text(encoding="utf-8"), "control.mastermind-x.com")


def _adapted_control_execution_labels() -> list[str]:
    """Return security-relevant handlers in Caddy's real adapted order."""
    result = subprocess.run(
        ["caddy", "adapt", "--config", str(CADDY), "--pretty"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(result.stdout)
    site = None
    for server in document["apps"]["http"]["servers"].values():
        for route in server.get("routes", []):
            if any(
                "control.mastermind-x.com" in matcher.get("host", [])
                for matcher in route.get("match", [])
            ):
                site = route
                break
        if site is not None:
            break
    assert site is not None, "adapted config omitted the Control Room host"

    labels: list[str] = []

    def walk(routes: list[dict]) -> None:
        for route in routes:
            matchers = route.get("match", [])
            for handler in route.get("handle", []):
                kind = handler.get("handler")
                if kind == "subroute":
                    walk(handler.get("routes", []))
                    continue
                if kind == "static_response":
                    if any("/healthz" in matcher.get("path", []) for matcher in matchers):
                        labels.append("health_404")
                    elif any("not" in matcher for matcher in matchers):
                        labels.append("mutation_405")
                    continue
                if kind != "reverse_proxy":
                    continue
                if handler.get("rewrite", {}).get("uri") == "/api/control-room/auth-check":
                    labels.append("auth_proxy")
                    continue
                if any(
                    upstream.get("dial") == "unix//run/mastermind-control-room/remote.sock"
                    for upstream in handler.get("upstreams", [])
                ):
                    labels.append("unix_proxy")

    walk([site])
    return labels


def test_control_room_authenticates_once_before_the_only_unix_origin():
    """Removing/reordering the auth subrequest or adding a second origin must fail."""
    block = _control_block()

    assert block.count("reverse_proxy 127.0.0.1:8000 {") == 1
    assert block.count("rewrite /api/control-room/auth-check") == 1
    assert block.count("reverse_proxy unix//run/mastermind-control-room/remote.sock {") == 1
    assert block.index("rewrite /api/control-room/auth-check") < block.index(
        "reverse_proxy unix//run/mastermind-control-room/remote.sock {"
    )
    assert re.search(r"@operator\s+status\s+2xx", block)
    assert re.search(r"handle_response\s+@operator\s*\{\s*\}", block)
    assert "127.0.0.1:8787" not in block
    assert not re.search(r"reverse_proxy\s+(?:127\.0\.0\.1|localhost|\[::1\]):\d+", block.replace("127.0.0.1:8000", ""))


def test_control_room_refuses_health_and_mutation_before_origin():
    """Health and mutation-shaped requests must never reach auth or projection."""
    block = _control_block()

    assert "@health path /healthz" in block
    assert "respond @health 404" in block
    assert "@mutation not method GET HEAD" in block
    assert "respond @mutation 405" in block
    route = block.index("route {")
    auth = block.index("rewrite /api/control-room/auth-check")
    assert route < block.index("respond @health 404") < auth
    assert route < block.index("respond @mutation 405") < auth
    assert "rewrite /healthz" not in block


def test_control_room_adapted_order_refuses_health_and_mutation_before_origin():
    """Caddy directive sorting must not move either refusal behind a proxy."""
    assert _adapted_control_execution_labels() == [
        "health_404",
        "mutation_405",
        "auth_proxy",
        "unix_proxy",
    ]


def test_control_room_socket_hop_strips_every_browser_and_forged_identity_header():
    """No browser credential or caller-supplied identity proof may cross the socket."""
    block = _control_block()
    socket = block[block.index("reverse_proxy unix//run/mastermind-control-room/remote.sock {") :]

    for name in (
        "Cookie",
        "Authorization",
        "X-CCR-Token",
        "X-Authenticated-User",
        "X-Original-Uri",
        "X-Original-Method",
        "X-Forwarded-For",
        "X-Forwarded-Host",
        "X-Forwarded-Proto",
    ):
        assert f"header_up -{name}" in socket
    assert "header_up Host control.mastermind-x.com" in socket


def test_control_room_responses_are_private_embeddable_only_by_admin_and_not_cached():
    """A broadened frame/cache/CORS policy or XFO conflict must fail."""
    block = _control_block()

    assert 'Cache-Control "private, no-store"' in block
    assert 'Vary "Cookie"' in block
    assert 'Strict-Transport-Security "max-age=31536000"' in block
    assert 'X-Content-Type-Options "nosniff"' in block
    assert 'X-Robots-Tag "noindex, nofollow, noarchive"' in block
    csp = re.search(r'Content-Security-Policy "([^"]+)"', block)
    assert csp is not None
    assert csp.group(1) == (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; object-src 'none'; "
        "frame-ancestors https://admin.mastermind-x.com"
    )
    assert "-X-Frame-Options" in block
    assert not re.search(r"(?m)^\s*X-Frame-Options\b", block)
    assert "Access-Control-Allow" not in block
    assert "stale-if-error" not in block.lower()
    assert "file_server" not in block
    assert "try_files" not in block
