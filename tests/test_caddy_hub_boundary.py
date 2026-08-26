"""Self-tests for the production Caddy topology guard over ``/api/hub/prophet``
(``scripts/check_caddy_hub_boundary.py``, B1 Day-6 AMENDMENT clause F,
DEC:B1-PROPHET-PUBLIC-SPLIT).

``_hub_prophet_authorized`` (app/prophet_lab.py) denies the internal-only hub
route unless the caller is loopback AND carries no ``X-MM-Peer`` header. That
guard is only as good as the topology fact it relies on: every edge-facing
``reverse_proxy ... 127.0.0.1:8000`` block either stamps ``X-MM-Peer`` (so a
public request always carries it) or rewrites the caller's path to something
fixed and non-hub (so the caller's own path can never select the hub route).
These tests prove the shipped Caddyfile satisfies that today, prove the
checker actually REJECTS the shape clause F is worried about (a bare, unstamped
``reverse_proxy ... 127.0.0.1:8000`` — the "future generic block" that could
otherwise silently bypass the hub guard), and tie the classification directly
to the real ``_hub_prophet_authorized`` property it depends on.

Run: python -m pytest tests/test_caddy_hub_boundary.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_caddy_hub_boundary import (
    REPO_ROOT,
    SAFE_FIXED_REWRITE,
    SAFE_PEER_STAMPED,
    UNSAFE,
    classify_backend_proxies,
)

CADDYFILE_PATH = REPO_ROOT / "app" / "deploy" / "Caddyfile"


# ---------------------------------------------------------------------------
# The shipped production Caddyfile — must classify all-safe, and the exact
# proxy COUNT is pinned so a silently-dropped block is caught rather than
# passing vacuously.
# ---------------------------------------------------------------------------
def test_shipped_caddyfile_has_exactly_seven_backend_proxies_all_safe() -> None:
    text = CADDYFILE_PATH.read_text(encoding="utf-8")
    proxies = classify_backend_proxies(text)

    assert len(proxies) == 7, (
        f"expected exactly 7 :8000 backend reverse_proxy blocks, found {len(proxies)}: {proxies}\n"
        "If this is a deliberate topology change, update the pinned count here — do not just "
        "delete the assertion, that is exactly the vacuous pass clause F exists to prevent."
    )
    unsafe = [p for p in proxies if p.classification == UNSAFE]
    assert unsafe == [], f"shipped Caddyfile has UNSAFE backend proxy block(s): {unsafe}"

    peer_stamped = [p for p in proxies if p.classification == SAFE_PEER_STAMPED]
    fixed_rewrite = [p for p in proxies if p.classification == SAFE_FIXED_REWRITE]
    assert len(peer_stamped) == 2, peer_stamped
    assert len(fixed_rewrite) == 5, fixed_rewrite
    assert len(peer_stamped) + len(fixed_rewrite) == 7


def test_shipped_caddyfile_line_numbers_match_known_blocks() -> None:
    """Pins WHICH lines classify which way, so a future edit that moves a
    block without preserving its safety property shows up as a line-number
    diff a reviewer will actually look at."""
    text = CADDYFILE_PATH.read_text(encoding="utf-8")
    proxies = {p.line: p.classification for p in classify_backend_proxies(text)}
    assert proxies == {
        121: SAFE_PEER_STAMPED,
        146: SAFE_PEER_STAMPED,
        348: SAFE_FIXED_REWRITE,
        357: SAFE_FIXED_REWRITE,
        390: SAFE_FIXED_REWRITE,
        428: SAFE_FIXED_REWRITE,
        770: SAFE_FIXED_REWRITE,
    }


# ---------------------------------------------------------------------------
# NON-VACUITY / mutation tests — the checker must actually be able to fail.
# ---------------------------------------------------------------------------
def test_generic_unstamped_block_is_rejected_unsafe() -> None:
    """This is exactly clause F's worry: 'a future generic reverse_proxy
    :8000 block cannot silently bypass the hub guard'."""
    caddy = (
        "example.com {\n"
        "\treverse_proxy /* 127.0.0.1:8000 {\n"
        "\t}\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert len(proxies) == 1
    assert proxies[0].classification == UNSAFE
    assert proxies[0].reasons


def test_placeholder_rewrite_does_not_count_as_a_fixed_rewrite() -> None:
    """A `rewrite` whose target is a placeholder re-emits the CALLER's path, so
    the caller still selects the upstream route. Accepting it as
    SAFE_FIXED_REWRITE would be a silent bypass of the hub guard — the exact
    thing clause F asks this check to make impossible."""
    for target in ("{http.request.uri}", "{path}", "{uri}"):
        caddy = (
            "example.com {\n"
            "\treverse_proxy /* 127.0.0.1:8000 {\n"
            f"\t\trewrite {target}\n"
            "\t}\n"
            "}\n"
        )
        proxies = classify_backend_proxies(caddy)
        assert len(proxies) == 1, target
        assert proxies[0].classification == UNSAFE, target
        assert proxies[0].reasons, target


def test_a_peer_stamp_still_saves_a_block_that_also_has_a_placeholder_rewrite() -> None:
    """The peer stamp alone is sufficient: the request arrives at :8000 carrying
    X-MM-Peer, so `_hub_prophet_authorized` denies it whatever the path is."""
    caddy = (
        "example.com {\n"
        "\treverse_proxy /* 127.0.0.1:8000 {\n"
        "\t\trewrite {http.request.uri}\n"
        "\t\theader_up X-MM-Peer {remote_host}\n"
        "\t}\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert len(proxies) == 1
    assert proxies[0].classification == SAFE_PEER_STAMPED


def test_bare_directive_with_no_block_at_all_is_rejected_unsafe() -> None:
    caddy = (
        "example.com {\n"
        "\treverse_proxy 127.0.0.1:8000\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert len(proxies) == 1
    assert proxies[0].classification == UNSAFE
    assert proxies[0].has_header_up_peer is False
    assert proxies[0].rewrite_targets == ()


def test_rewrite_into_the_hub_path_is_rejected_even_though_it_has_a_rewrite() -> None:
    caddy = (
        "example.com {\n"
        "\treverse_proxy /leak/* 127.0.0.1:8000 {\n"
        "\t\tmethod GET\n"
        "\t\trewrite /api/hub/prophet\n"
        "\t}\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert len(proxies) == 1
    p = proxies[0]
    assert p.classification == UNSAFE
    assert p.rewrite_targets == ("/api/hub/prophet",)
    assert any("/api/hub/" in r for r in p.reasons)


def test_rewrite_into_the_hub_path_is_unsafe_even_with_a_peer_stamp_present() -> None:
    """The 'additionally FAIL' clause is unconditional — belt-and-suspenders
    even for a block that also stamps the peer header."""
    caddy = (
        "example.com {\n"
        "\treverse_proxy /weird/* 127.0.0.1:8000 {\n"
        "\t\trewrite /api/hub/prophet\n"
        "\t\theader_up X-MM-Peer {remote_host}\n"
        "\t}\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert proxies[0].classification == UNSAFE


# ---------------------------------------------------------------------------
# Sanctioned shapes pass.
# ---------------------------------------------------------------------------
def test_peer_stamped_block_passes() -> None:
    caddy = (
        "example.com {\n"
        "\treverse_proxy /api/* 127.0.0.1:8000 {\n"
        "\t\theader_up X-MM-Peer {remote_host}\n"
        "\t}\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert proxies[0].classification == SAFE_PEER_STAMPED


def test_fixed_rewrite_block_passes() -> None:
    caddy = (
        "example.com {\n"
        "\treverse_proxy /gate/* 127.0.0.1:8000 {\n"
        "\t\tmethod GET\n"
        "\t\trewrite /api/gate/check\n"
        "\t}\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert proxies[0].classification == SAFE_FIXED_REWRITE


def test_localhost_and_ipv6_loopback_hosts_are_also_recognized() -> None:
    caddy = (
        "example.com {\n"
        "\treverse_proxy /a/* localhost:8000 {\n"
        "\t\theader_up X-MM-Peer {remote_host}\n"
        "\t}\n"
        "\treverse_proxy /b/* [::1]:8000 {\n"
        "\t\theader_up X-MM-Peer {remote_host}\n"
        "\t}\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert len(proxies) == 2
    assert all(p.classification == SAFE_PEER_STAMPED for p in proxies)


def test_a_non_backend_reverse_proxy_is_not_counted() -> None:
    """A reverse_proxy to some other port/host must not pollute the count —
    only :8000 loopback targets are this route's backend."""
    caddy = (
        "example.com {\n"
        "\treverse_proxy /admin/* 127.0.0.1:8787 {\n"
        "\t\theader_up X-Admin-Client-IP {remote_host}\n"
        "\t}\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert proxies == []


def test_nested_braces_inside_a_block_do_not_break_block_boundary_detection() -> None:
    """handle_response {}-nesting inside a real reverse_proxy block (as seen
    in the shipped Caddyfile's regwall/paywall/gate blocks) must not fool the
    brace-depth scan into closing the block early or late."""
    caddy = (
        "example.com {\n"
        "\treverse_proxy 127.0.0.1:8000 {\n"
        "\t\tmethod GET\n"
        "\t\trewrite /api/regwall/check\n"
        "\t\t@rallow status 2xx\n"
        "\t\thandle_response @rallow {\n"
        "\t\t}\n"
        "\t}\n"
        "\treverse_proxy /elsewhere/* 127.0.0.1:9999\n"
        "}\n"
    )
    proxies = classify_backend_proxies(caddy)
    assert len(proxies) == 1
    assert proxies[0].classification == SAFE_FIXED_REWRITE
    assert proxies[0].rewrite_targets == ("/api/regwall/check",)


# ---------------------------------------------------------------------------
# main() exit-code contract.
# ---------------------------------------------------------------------------
def test_main_exits_zero_on_the_shipped_caddyfile() -> None:
    from scripts.check_caddy_hub_boundary import main

    assert main(["--root", str(REPO_ROOT)]) == 0


def test_main_exits_nonzero_on_a_synthetic_unsafe_caddyfile(tmp_path: Path) -> None:
    from scripts.check_caddy_hub_boundary import main

    caddy_path = tmp_path / "Caddyfile"
    caddy_path.write_text(
        "example.com {\n\treverse_proxy /* 127.0.0.1:8000 {\n\t}\n}\n",
        encoding="utf-8",
    )
    assert main(["--caddyfile", str(caddy_path)]) == 1


def test_main_exits_nonzero_when_no_backend_proxies_are_found(tmp_path: Path) -> None:
    """A silently-emptied Caddyfile must not pass vacuously."""
    from scripts.check_caddy_hub_boundary import main

    caddy_path = tmp_path / "Caddyfile"
    caddy_path.write_text("example.com {\n\trespond \"hi\"\n}\n", encoding="utf-8")
    assert main(["--caddyfile", str(caddy_path)]) == 1


# ---------------------------------------------------------------------------
# Tie the topology guard to the REAL app-level property it depends on:
# loopback peer + absent X-MM-Peer is denied by _hub_prophet_authorized.
# Same request-stub style as tests/test_prophet_lab_api.py.
# ---------------------------------------------------------------------------
fastapi = pytest.importorskip("fastapi", reason="prophet_lab guard tests need fastapi")
pytest.importorskip("starlette", reason="prophet_lab guard tests need starlette")

from starlette.requests import Request  # noqa: E402

import app.prophet_lab as prophet_lab_api  # noqa: E402


def _hub_request(*, client_host: str | None, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/hub/prophet",
        "raw_path": b"/api/hub/prophet",
        "query_string": b"",
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in (headers or {}).items()
        ],
        "client": (client_host, 51000) if client_host is not None else None,
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    return Request(scope)


def test_loopback_peer_carrying_the_edge_stamped_header_is_denied() -> None:
    """This is the property the whole Caddy topology guard exists to protect:
    a request that looks loopback but carries X-MM-Peer (i.e. it came through
    the /api/* proxy, which ALWAYS stamps that header) must be denied, even
    though the bare TCP peer alone cannot tell it apart from a direct call."""
    request = _hub_request(client_host="127.0.0.1", headers={"x-mm-peer": "203.0.113.7"})
    assert prophet_lab_api._hub_prophet_authorized(request) is False  # noqa: SLF001


def test_loopback_peer_with_no_peer_header_is_authorized() -> None:
    request = _hub_request(client_host="127.0.0.1")
    assert prophet_lab_api._hub_prophet_authorized(request) is True  # noqa: SLF001
