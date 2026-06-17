#!/usr/bin/env python3
"""Static syntax guard for the inline JavaScript in the committed site HTML.

A single malformed inline `<script>` (e.g. `var DISP = ;` — an empty template
variable that slips through as a JS *syntax error*) aborts the whole page IIFE
before it wires load/render, so the page renders BLANK with no server error.
The dashboard's HTML is a committed artifact that the daily build does not
always regenerate, so a stale-corrupt page can be carried forward by an
unrelated PR and ship silently (this has happened twice — see
templates/stock.html.j2's `var DISP` line and PRs #152 / #155).

This script extracts every executable inline script from `site/**/*.html` and
runs `node --check` on it. It exits non-zero if any block fails to parse, so it
can gate the Pages deploy (a failed guard keeps the last-good site live instead
of shipping a blank page) and flag offending PRs.

External (`src=`) scripts and non-JS data blocks (`type="application/json"`
etc.) are skipped — only classic/module inline JS is parsed.

Usage:
    python -m scripts.check_inline_js [SITE_DIR]   # default: site/
Exit codes: 0 = all clean · 1 = syntax error(s) found · 2 = node unavailable.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

# <script ...attrs...>body</script>, non-greedy body, case-insensitive tag.
_SCRIPT_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.DOTALL | re.IGNORECASE)
_TYPE_RE = re.compile(r"""type\s*=\s*["']?\s*([^"'\s>]+)""", re.IGNORECASE)
# `type` values that the browser executes as JavaScript (empty/absent == classic JS).
_JS_TYPES = {"", "text/javascript", "application/javascript", "text/ecmascript", "module"}


def _is_executable_js(attrs: str) -> bool:
    """True only for inline classic/module scripts the browser runs as JS."""
    if re.search(r"\bsrc\s*=", attrs, re.IGNORECASE):
        return False  # external script — not our content to check
    m = _TYPE_RE.search(attrs)
    typ = (m.group(1).lower() if m else "")
    return typ in _JS_TYPES


def _extract_blocks(html: str):
    """Yield (start_line, is_module, body) for each executable inline script."""
    for m in _SCRIPT_RE.finditer(html):
        attrs, body = m.group("attrs"), m.group("body")
        if not body.strip() or not _is_executable_js(attrs):
            continue
        start_line = html.count("\n", 0, m.start("body")) + 1
        is_module = bool(re.search(r"""type\s*=\s*["']?\s*module""", attrs, re.IGNORECASE))
        yield start_line, is_module, body


def _check_block(body: str, is_module: bool):
    """Return None if the script parses, else (node_line:int|None, message)."""
    suffix = ".mjs" if is_module else ".js"
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as f:
        f.write(body)
        path = f.name
    try:
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        if r.returncode == 0:
            return None
        err = (r.stderr.strip() or "syntax error").splitlines()
        # node's first line is `<file>:<line>`; pull the line number so we can map
        # it back to the real position in the HTML file.
        node_line = None
        m = re.search(re.escape(path) + r":(\d+)", r.stderr)
        if m:
            node_line = int(m.group(1))
        # the SyntaxError line is the most useful single message.
        msg = next((ln for ln in err if "Error:" in ln), err[-1]).strip()
        return node_line, msg
    finally:
        os.unlink(path)


def find_bad_scripts(site_dir: str = "site"):
    """Return a list of (file, line, error) for every malformed inline script."""
    html_files = []
    for root, _dirs, files in os.walk(site_dir):
        for name in files:
            if name.endswith(".html"):
                html_files.append(os.path.join(root, name))
    html_files.sort()

    tasks = []  # (file, start_line, is_module, body)
    for path in html_files:
        try:
            html = open(path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError) as e:  # unreadable file is itself a problem
            tasks.append((path, 0, False, None))
            continue
        for start_line, is_module, body in _extract_blocks(html):
            tasks.append((path, start_line, is_module, body))

    bad: list[tuple[str, int, str]] = []
    with ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 2))) as pool:
        futures = {}
        for path, body_line, is_module, body in tasks:
            if body is None:
                bad.append((path, body_line, "could not read file as UTF-8"))
                continue
            futures[pool.submit(_check_block, body, is_module)] = (path, body_line)
        for fut, (path, body_line) in futures.items():
            res = fut.result()
            if res is not None:
                node_line, msg = res
                # map node's line within the snippet back to the HTML file line:
                # the snippet's line 1 sits on the file line where the body begins.
                file_line = body_line + (node_line - 1) if node_line else body_line
                bad.append((path, file_line, msg))
    bad.sort()
    return bad


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    site_dir = argv[0] if argv else "site"

    if shutil.which("node") is None:
        print("check_inline_js: ERROR — `node` not found on PATH; cannot verify inline JS.", file=sys.stderr)
        return 2

    bad = find_bad_scripts(site_dir)
    if bad:
        print(f"check_inline_js: FAIL — {len(bad)} inline script block(s) with syntax errors:\n", file=sys.stderr)
        for path, line, err in bad:
            print(f"  {path}:{line}  {err}", file=sys.stderr)
        print(
            "\nA broken inline script renders the page BLANK. Fix the source "
            "(usually a template variable rendered empty) and re-commit.",
            file=sys.stderr,
        )
        return 1
    print(f"check_inline_js: OK — all inline scripts under {site_dir}/ parse cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
