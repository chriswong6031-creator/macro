"""Drift guards for the broad static-data access boundary.

PR #3393 originally protected only ``/factordata`` and ``/labdata``. The
default-deny boundary supersedes that narrow matcher: every non-public asset is
now registration- and entitlement-checked, while the two existing Terminal
ingest carve-outs stay explicit and public.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = REPO_ROOT / "app" / "deploy" / "Caddyfile"
POLICY_FILE = REPO_ROOT / "config" / "site_access.yml"

CARVEOUTS = {"/factordata/tech_lab.json", "/factordata/tech_events/*"}


def _read_caddyfile() -> str:
    return CADDYFILE.read_text(encoding="utf-8")


def _extract_block(text: str, header: str) -> str:
    pattern = re.compile(r"(?m)^[ \t]*" + re.escape(header) + r"[ \t]*\{")
    match = pattern.search(text)
    assert match is not None, f"block {header!r} missing"
    start = match.end() - 1
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unbalanced block {header!r}")


def _path_tokens(block: str) -> set[str]:
    tokens: set[str] = set()
    for match in re.finditer(r"(?m)^[ \t]*(?:not )?path[ \t]+(.+)$", block):
        tokens.update(match.group(1).split())
    return tokens


def _public_policy_tokens() -> set[str]:
    policy = yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))
    result = set(policy["public"]["exact"])
    result.update(prefix.rstrip("/") + "/*" for prefix in policy["public"]["prefixes"])
    return result


def test_broad_asset_matcher_protects_paid_json_and_keeps_only_carveouts_public():
    text = _read_caddyfile()
    exclusions = _path_tokens(_extract_block(text, "@reg_asset"))
    assert CARVEOUTS <= exclusions
    assert "/factordata/*" not in exclusions
    assert "/labdata/*" not in exclusions


def test_terminal_carveouts_match_reviewed_policy():
    text = _read_caddyfile()
    policy_public = _public_policy_tokens()
    public_block = _path_tokens(_extract_block(text, "@factordata_public"))
    assert public_block == CARVEOUTS
    assert CARVEOUTS <= policy_public


def test_broad_asset_handle_runs_both_auth_stages_and_is_private():
    block = _extract_block(_read_caddyfile(), "handle @reg_asset")
    assert "rewrite /api/regwall/check" in block
    assert "rewrite /api/paywall/check" in block
    assert "header_up X-Original-Kind asset" in block
    assert 'Cache-Control "private, no-store"' in block
    assert "file_server" in block


def test_broad_asset_error_branch_fails_closed():
    text = _read_caddyfile()
    block = _extract_block(text, "handle @reg_asset_err")
    assert "503" in block
    assert "private, no-store" in block
    assert "file_server" not in block
    assert "handle @reg_asset_err" in _extract_block(text, "handle_errors")


def test_shared_cache_headers_match_only_reviewed_public_paths():
    text = _read_caddyfile()
    policy_public = _public_policy_tokens()
    for matcher in ("@public_static", "@public_versioned", "@factordata_public"):
        assert _path_tokens(_extract_block(text, matcher)) <= policy_public
    assert re.search(r"(?m)^[ \t]*@static[ \t]*\{", text) is None
    assert re.search(r"(?m)^[ \t]*@versioned[ \t]*\{", text) is None
    assert re.search(r"(?m)^[ \t]*@reg_json[ \t]*\{", text) is None


def test_public_pages_fetch_nothing_under_paid_prefixes():
    files = [
        REPO_ROOT / "templates" / "index.html",
        REPO_ROOT / "templates" / "plans.html.j2",
        REPO_ROOT / "templates" / "theme.js",
        REPO_ROOT / "templates" / "live.js",
        REPO_ROOT / "templates" / "onboard.js",
    ]
    target_re = re.compile(
        r"""(?:fetch\s*\(\s*|getJSON\s*\(\s*|\.src\s*=\s*)"""
        r"""['"`]([^'"`]+)['"`]"""
    )
    offenders = []
    for path in files:
        assert path.is_file(), f"public boundary file missing: {path}"
        for raw in target_re.findall(path.read_text(encoding="utf-8")):
            normalized = raw.split("?", 1)[0].split("#", 1)[0].lstrip("/")
            if normalized.startswith("./"):
                normalized = normalized[2:]
            if normalized.startswith(("factordata/", "labdata/")):
                offenders.append((path.name, raw))
    assert offenders == []


def test_html_registration_matcher_remains_present():
    assert "path *.html" in _extract_block(_read_caddyfile(), "@reg_html")
