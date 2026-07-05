#!/usr/bin/env python3
"""Static syntax guard for the standalone JavaScript bundles in the site.

Companion to `check_inline_js.py`. That script only parses inline `<script>`
blocks and deliberately SKIPS external `src=` files — so a syntax error in a
standalone `site/*.js` bundle sails straight past it. That is exactly how
markets.html shipped BROKEN to production for ~2 days: `site/markets_app.js`
carried curly smart-quotes (U+201C/U+201D) used as string delimiters — a hard
JS SyntaxError that aborts the whole module before it wires any charts, so the
page renders with nothing (introduced in PR #1004, repaired in PR #1353). No
guard caught it because the file is loaded via `<script src=...>`.

This script walks `site/**/*.js` and runs `node --check` on every standalone
bundle so that class of regression shows up as a red check BEFORE merge and
aborts the Pages deploy (keeping the last-good site live) instead of shipping a
blank page.

Minified/vendor bundles are excluded — they are third-party artifacts we do not
author and re-checking them is pure noise: `*.min.js`, any `plotly*` file, and
anything under a `vendor/` directory.

Each file is checked first as a classic script and, only if that fails, again as
an ES module — a bundle may legitimately use top-level `import`/`export`/`await`
(valid only in a module), and we must not flag that as an error. A genuine
syntax error (e.g. a smart-quote delimiter) fails in BOTH modes, so it is still
caught.

Usage:
    python -m scripts.check_site_js [SITE_DIR]   # default: site/
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


def _is_excluded(rel_path: str, name: str) -> bool:
    """True for third-party bundles we do not author (skip = pure noise)."""
    if name.endswith(".min.js"):
        return True
    if name.startswith("plotly"):
        return True
    # any `vendor/` directory anywhere in the path
    parts = rel_path.replace("\\", "/").split("/")
    return "vendor" in parts[:-1]


def _node_check(path: str):
    """Run `node --check path`; return (returncode, stderr)."""
    r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    return r.returncode, r.stderr


def _check_file(path: str):
    """Return None if the file parses (as script OR module), else (line, message)."""
    rc, stderr = _node_check(path)
    if rc == 0:
        return None  # valid classic script

    # A bundle may be an ES module (top-level import/export/await), which is a
    # syntax error in classic-script mode but perfectly valid. Retry as a module
    # by copying the exact bytes to a `.mjs` temp file; only a real syntax error
    # fails BOTH modes.
    try:
        src = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        return 0, "could not read file as UTF-8"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as f:
            f.write(src)
            tmp_path = f.name
        mrc, _ = _node_check(tmp_path)
        if mrc == 0:
            return None  # valid as an ES module
    finally:
        if tmp_path:
            os.unlink(tmp_path)

    # Genuine syntax error. Use the script-mode stderr — it was run against the
    # real file, so its `<file>:<line>` header maps straight to the source line.
    lines = (stderr.strip() or "syntax error").splitlines()
    m = re.search(re.escape(path) + r":(\d+)", stderr)
    line = int(m.group(1)) if m else 0
    msg = next((ln for ln in lines if "Error:" in ln), lines[-1]).strip()
    return line, msg


def find_bad_files(site_dir: str = "site"):
    """Return a list of (file, line, error) for every malformed standalone JS bundle."""
    js_files = []
    for root, _dirs, files in os.walk(site_dir):
        for name in files:
            if not name.endswith(".js"):
                continue
            path = os.path.join(root, name)
            if _is_excluded(path, name):
                continue
            js_files.append(path)
    js_files.sort()

    bad: list[tuple[str, int, str]] = []
    with ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 2))) as pool:
        futures = {pool.submit(_check_file, path): path for path in js_files}
        for fut, path in futures.items():
            res = fut.result()
            if res is not None:
                line, msg = res
                bad.append((path, line, msg))
    bad.sort()
    return bad


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    site_dir = argv[0] if argv else "site"

    if shutil.which("node") is None:
        print("check_site_js: ERROR — `node` not found on PATH; cannot verify standalone JS.", file=sys.stderr)
        return 2

    bad = find_bad_files(site_dir)
    if bad:
        print(f"check_site_js: FAIL — {len(bad)} standalone JS bundle(s) with syntax errors:\n", file=sys.stderr)
        for path, line, err in bad:
            print(f"  {path}:{line}  {err}", file=sys.stderr)
        print(
            "\nA broken standalone bundle aborts its module and renders the page "
            "BLANK (loaded via <script src=...>, so the inline-JS guard misses it). "
            "Fix the source and re-commit.",
            file=sys.stderr,
        )
        return 1
    print(f"check_site_js: OK — all standalone JS bundles under {site_dir}/ parse cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
