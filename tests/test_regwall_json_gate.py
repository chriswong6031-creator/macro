"""Drift-guard for the JSON registration-wall boundary in app/deploy/Caddyfile.

Pure-text invariant tests — no caddy binary, no network. These assert the SHAPE
of the ``@reg_json`` gate (which paid JSON prefixes are gated, which carve-outs
stay anonymous-fetchable, that the gate is two-stage + private, and that the
error branch fails closed). The *runtime* behaviour of ``/api/regwall/check``
itself (204 allow / 302 deny, kill switch) is covered by ``test_regwall.py`` —
this file only guards the Caddyfile wiring around it from silent drift.

Why this matters: the gated prefixes carry ~1MB of live buy rows
(``/factordata/us_standouts.json``). A well-meaning edit that gates ``/live/``
or ``/prophet/`` here, or that lets the carve-out lists drift apart, or that
lets the outer ``@static`` header clobber the gate's ``private, no-store``,
would either break the public landing or leak paid signals to the shared edge
cache. Each test below pins one of those invariants.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = REPO_ROOT / "app" / "deploy" / "Caddyfile"

# The carve-outs that MUST stay anonymous-fetchable (Terminal ingest pulls
# them with no cookies). This is the single source of truth the three mirrored
# path-lists in the Caddyfile are checked against.
CARVEOUTS = {"/factordata/tech_lab.json", "/factordata/tech_events/*"}
GATED_PREFIXES = {"/factordata/*", "/labdata/*"}


def _read_caddyfile() -> str:
    assert CADDYFILE.is_file(), f"Caddyfile not found at {CADDYFILE}"
    return CADDYFILE.read_text(encoding="utf-8")


def _extract_block(text: str, header: str) -> str:
    """Return the ``{ ... }`` body (braces included) of the first block whose
    opening line starts with ``header`` (e.g. ``@reg_json`` or
    ``handle @reg_json``). Brace-matched, so nested ``route {`` / ``file_server
    {`` blocks are captured whole. Tab-indent agnostic."""
    # Find the header token followed (possibly after whitespace) by an opening
    # brace on the same line. Anchor on a line boundary so ``@reg_json_err``
    # does not match a request for ``@reg_json``.
    pattern = re.compile(
        r"(?m)^[ \t]*" + re.escape(header) + r"[ \t]*\{",
    )
    m = pattern.search(text)
    assert m is not None, f"block {header!r} {{ not found in Caddyfile"
    start = m.end() - 1  # position of the opening brace
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError(f"unbalanced braces after {header!r}")


def _path_tokens(block: str, directive: str) -> set:
    """Collect the whitespace-separated path tokens from every line in ``block``
    that begins with ``directive`` (``path`` or ``not path``). Handles the
    directive appearing once or on multiple lines."""
    tokens: set = set()
    found = False
    # Match a whole line whose content (after indent) starts with the directive
    # as a full word, then capture the remainder.
    line_re = re.compile(
        r"(?m)^[ \t]*" + re.escape(directive) + r"[ \t]+(.+)$"
    )
    for m in line_re.finditer(block):
        found = True
        for tok in m.group(1).split():
            tokens.add(tok)
    assert found, f"directive {directive!r} not found in block"
    return tokens


def test_reg_json_matcher_covers_paid_payloads():
    """@reg_json gates EXACTLY /factordata/* and /labdata/* — nothing more.

    Gating /live/ or /prophet/ here would break the public landing (it fetches
    those cookie-less); asserting set equality stops any extra prefix sneaking
    in."""
    text = _read_caddyfile()
    block = _extract_block(text, "@reg_json")
    assert _path_tokens(block, "path") == GATED_PREFIXES


def test_carveouts_mirrored():
    """The three carve-out lists are byte-for-byte identical.

    @reg_json's `not path`, @reg_json_err's `not path`, and @factordata_public's
    `path` must all equal {tech_lab.json, tech_events/*}. If they drift, either a
    carve-out gets gated (Terminal ingest breaks) or a paid path leaks."""
    text = _read_caddyfile()
    reg = _path_tokens(_extract_block(text, "@reg_json"), "not path")
    err = _path_tokens(_extract_block(text, "@reg_json_err"), "not path")
    pub = _path_tokens(_extract_block(text, "@factordata_public"), "path")
    assert reg == CARVEOUTS, f"@reg_json not-path drifted: {reg}"
    assert err == CARVEOUTS, f"@reg_json_err not-path drifted: {err}"
    assert pub == CARVEOUTS, f"@factordata_public path drifted: {pub}"
    assert reg == err == pub


def test_static_excludes_gated_prefixes():
    """@static excludes the gated prefixes (the edge-cache-leak guard).

    Without this exclusion the outer `header @static` would clobber the gate's
    `private, no-store` and could cache a 302 deny at the shared edge."""
    text = _read_caddyfile()
    block = _extract_block(text, "@static")
    not_path = _path_tokens(block, "not path")
    assert GATED_PREFIXES <= not_path, (
        f"@static must exclude {GATED_PREFIXES}; got not-path tokens {not_path}"
    )


def _strip_comments(block: str) -> str:
    """Drop Caddyfile comment lines (``#`` after optional indent) so directive
    assertions are not fooled by the token appearing in an explanatory comment."""
    return "\n".join(
        ln for ln in block.splitlines() if not re.match(r"^[ \t]*#", ln)
    )


def test_reg_json_handle_two_stage_and_private():
    """handle @reg_json runs BOTH gate stages, is private, carries no ret=."""
    text = _read_caddyfile()
    block = _extract_block(text, "handle @reg_json")
    assert "rewrite /api/gate/check" in block, "stage-1 IP gate missing"
    assert "rewrite /api/regwall/check" in block, "stage-2 regwall missing"
    assert 'Cache-Control "private, no-store"' in block, "not private/no-store"
    # A JSON deny must redirect to a bare /?signin=1 — never carry a ret= back
    # to a raw JSON file — so the original-uri header must be absent here. Check
    # the directives (comments explain the omission and mention the token).
    assert "X-Original-Uri" not in _strip_comments(block), (
        "gated JSON must not carry an X-Original-Uri directive"
    )


def test_reg_json_error_branch_fails_closed():
    """handle @reg_json_err returns a 403 no-store and NEVER serves the file."""
    text = _read_caddyfile()
    block = _extract_block(text, "handle @reg_json_err")
    assert "respond" in block, "error branch must respond, not proxy"
    assert "403" in block, "error branch must return 403"
    assert "no-store" in block, "error 403 must be no-store"
    assert "file_server" not in block, (
        "error branch must NEVER serve the payload (no file_server)"
    )
    # And it must live inside handle_errors, not as a top-level handle.
    errors_block = _extract_block(text, "handle_errors")
    assert "handle @reg_json_err" in errors_block, (
        "@reg_json_err must be inside handle_errors"
    )


def test_public_pages_fetch_nothing_gated():
    """Public pages must fetch NOTHING under the gated prefixes.

    Scan the landing + shared public JS for literal fetch/.src/getJSON targets;
    none may resolve to a factordata/ or labdata/ path. A missing file is a hard
    failure — this boundary test must not silently skip."""
    files = [
        REPO_ROOT / "templates" / "index.html",
        REPO_ROOT / "templates" / "plans.html.j2",
        REPO_ROOT / "templates" / "theme.js",
        REPO_ROOT / "templates" / "live.js",
        REPO_ROOT / "templates" / "onboard.js",
    ]
    # fetch("..."), fetch('...'), fetch(`...`), .src = "...", getJSON("...")
    target_re = re.compile(
        r"""(?:fetch\s*\(\s*|getJSON\s*\(\s*|\.src\s*=\s*)"""
        r"""['"`]([^'"`]+)['"`]"""
    )
    offenders = []
    for path in files:
        assert path.is_file(), (
            f"public boundary file missing: {path} — the fetch-target scan must "
            f"not silently skip a file it is meant to guard"
        )
        text = path.read_text(encoding="utf-8")
        for raw in target_re.findall(text):
            # Normalize: strip a leading ./ or /, drop any query string.
            norm = raw.split("?", 1)[0].split("#", 1)[0]
            norm = norm.lstrip("/")
            if norm.startswith("./"):
                norm = norm[2:]
            if norm.startswith("factordata/") or norm.startswith("labdata/"):
                offenders.append((path.name, raw))
    assert not offenders, (
        f"public page fetches a GATED payload (would break for anon visitors): "
        f"{offenders}"
    )


def test_reg_html_untouched_shape():
    """Cheap collision guard against PR #3387's @reg_html edits.

    @reg_html still exists gating *.html, and @reg_json appears AFTER the
    `handle @reg_html` block and BEFORE @gate_html in file order (documents the
    intended placement). Kept loose — presence + relative order only — so
    changes to @reg_html's not-path list do not break this test."""
    text = _read_caddyfile()
    reg_html = _extract_block(text, "@reg_html")
    assert "path *.html" in reg_html, "@reg_html should still gate *.html"

    handle_reg_html = re.search(r"(?m)^[ \t]*handle @reg_html[ \t]*\{", text)
    reg_json = re.search(r"(?m)^[ \t]*@reg_json[ \t]*\{", text)
    gate_html = re.search(r"(?m)^[ \t]*@gate_html[ \t]*\{", text)
    assert handle_reg_html and reg_json and gate_html
    assert handle_reg_html.start() < reg_json.start() < gate_html.start(), (
        "@reg_json must sit between the handle @reg_html block and @gate_html"
    )
