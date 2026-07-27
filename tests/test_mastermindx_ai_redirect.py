"""Deployment contract for the redirect-only ``mastermindx.ai`` brand alias."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = (ROOT / "app" / "deploy" / "Caddyfile").read_text(encoding="utf-8")
TARGET = "https://www.mastermind-x.com{uri}"


def _site_block(addresses: str) -> str:
    match = re.search(
        rf"(?m)^{re.escape(addresses)} \{{\n(?P<body>.*?)^\}}\n",
        CADDYFILE,
        flags=re.DOTALL,
    )
    assert match, f"missing Caddy site block: {addresses}"
    return match.group("body")


def test_http_alias_redirects_directly_to_final_canonical_host() -> None:
    body = _site_block("http://mastermindx.ai, http://www.mastermindx.ai")
    assert f"redir {TARGET} permanent" in body


def test_https_alias_redirects_directly_and_keeps_hsts() -> None:
    body = _site_block("mastermindx.ai, www.mastermindx.ai")
    assert f"redir {TARGET} permanent" in body
    assert 'Strict-Transport-Security "max-age=31536000"' in body


def test_alias_never_serves_or_proxies_content() -> None:
    for addresses in (
        "http://mastermindx.ai, http://www.mastermindx.ai",
        "mastermindx.ai, www.mastermindx.ai",
    ):
        body = _site_block(addresses)
        assert "file_server" not in body
        assert "reverse_proxy" not in body
        assert "import mastermind_static" not in body
