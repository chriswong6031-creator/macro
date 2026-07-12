#!/usr/bin/env python3
"""Static syntax guard for the inline JavaScript in the committed site HTML.

A single malformed inline `<script>` (e.g. `var DISP = ;` — an empty template
variable that slips through as a JS *syntax error*) aborts the whole page IIFE
before it wires load/render, so the page renders BLANK with no server error.
The dashboard's HTML is a committed artifact that the daily build does not
always regenerate, so a stale-corrupt page can be carried forward by an
unrelated PR and ship silently (this has happened twice — see
templates/stock.html.j2's `var DISP` line and PRs #152 / #155).

Three checks, per file class:

*.html under the given dirs
  1. every executable inline `<script>` block parses under `node --check`
     (the blank-page class above);
  2. every quoted `on*="..."` event-handler attribute parses under
     `node --check` when wrapped as a function body — the browser compiles
     handlers exactly that way, so this mirrors what a click executes.
     Handlers were previously unchecked: a curly-quote onclick shipped on
     hk.html.j2 (caught only by review, PR #2321), and this check's first
     run over the tree caught a live unescaped-inner-quote onclick on
     china_stocks.html (attribute truncated at the first `"` — SyntaxError
     on every click, same class as the #2234 JS-built-HTML bug);
  3. curly quotes U+2018/U+2019/U+201C/U+201D are a hard error when they
     appear in JS *code position* (outside string literals and comments) in
     a `<script>` block, or anywhere in the RAW source of an `on*=`
     attribute value (entity-escaped display text — `&rsquo;` — stays
     legal). This is the Edit-tool smart-quote contamination class: curly
     quotes used as string DELIMITERS. A blanket ban inside `<script>`
     blocks is deliberately NOT enforced — the shipped site carries 500+
     legitimate curly quotes INSIDE string literals (bilingual display
     copy), so only code-position hits are contamination.

*.j2 under the given dirs (pass `templates` in CI)
  checks 2/3's curly halves ONLY, after stripping Jinja constructs
  ({{..}} / {%..%} / {#..#}, newline-preserving). `node --check` cannot
  parse Jinja placeholders, so broken plain-JS syntax in a .j2 still rides
  until the next render regenerates the site copy — but the curly-quote
  contamination class is caught at PR time instead of at render time.

Not extracted: handlers in unquoted attribute syntax (`onclick=f()`) — none
in the tree; quoted is the house style. `src=` scripts and non-JS data
blocks (`type="application/json"` etc.) are skipped as before.

Usage:
    python -m scripts.check_inline_js [DIR ...]    # default: site/
    python -m scripts.check_inline_js --selftest   # seeded-defect round-trip:
        builds fixtures (curly-quote onclick, broken handler, code-position
        curly script, .j2 curly onclick, clean control) in a temp dir and
        fails RED unless the guard catches every seeded defect and passes
        the clean control.
Exit codes: 0 = all clean · 1 = error(s) found · 2 = node unavailable.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from html import unescape as _html_unescape

# <script ...attrs...>body</script>, non-greedy body, case-insensitive tag.
_SCRIPT_RE = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.DOTALL | re.IGNORECASE)
_TYPE_RE = re.compile(r"""type\s*=\s*["']?\s*([^"'\s>]+)""", re.IGNORECASE)
# `type` values that the browser executes as JavaScript (empty/absent == classic JS).
_JS_TYPES = {"", "text/javascript", "application/javascript", "text/ecmascript", "module"}

# Quoted event-handler attributes. The lookbehind rejects data-onclick / x-on:click
# style names so only real on* handler attributes match.
_HANDLER_RE = re.compile(
    r"""(?<![-\w.:])on[a-z]+\s*=\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)')""",
    re.IGNORECASE,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# Jinja expression/statement/comment blocks; stripped (newline-preserving)
# before scanning .j2 files so template syntax can't false-positive.
_JINJA_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)

_CURLY_SET = {"‘", "’", "“", "”"}
_CURLY_RE = re.compile("[‘’“”]")


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


def _blank_keep_newlines(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def _attr_scan_text(html: str) -> str:
    """The document with <script> bodies and HTML comments blanked out.

    `onclick=` strings also live INSIDE script blocks as JS-built HTML
    fragments (with JS escaping that is not valid standalone) — blanking the
    bodies keeps the handler scan to real markup. Newlines are preserved so
    match offsets still map to file lines.
    """
    html = _SCRIPT_RE.sub(
        lambda m: "<script%s>%s</script>" % (m.group("attrs"), _blank_keep_newlines(m.group("body"))),
        html,
    )
    return _HTML_COMMENT_RE.sub(lambda m: _blank_keep_newlines(m.group(0)), html)


def _strip_jinja(text: str) -> str:
    """Replace Jinja constructs with a `0` placeholder, preserving newlines."""
    return _JINJA_RE.sub(lambda m: "0" + "\n" * m.group(0).count("\n"), text)


def _iter_handlers(scan_text: str):
    """Yield (line, raw_value) for each quoted on*= attribute in scan text."""
    for m in _HANDLER_RE.finditer(scan_text):
        val = m.group("dq") if m.group("dq") is not None else m.group("sq")
        line = scan_text.count("\n", 0, m.start()) + 1
        yield line, val


def _curly_code_offsets(js: str) -> list[int]:
    """Offsets of curly quotes in CODE position (outside strings/comments).

    Minimal state machine over ' " ` strings (backslash escapes honoured),
    // and /* */ comments. An unterminated '/" string resyncs to code at the
    newline (node flags the unterminated string itself). Not modelled: regex
    literals (a curly quote inside one would false-positive — none in the
    tree; write `\\u2018` there instead) and `${}` interpolation inside
    template literals (a curly quote there is missed here, but node --check
    still catches the delimiter class as a syntax error).
    """
    out: list[int] = []
    i, n, state = 0, len(js), None
    while i < n:
        c = js[i]
        if state is None:
            if c in _CURLY_SET:
                out.append(i)
            elif c in "'\"`":
                state = c
            elif c == "/" and i + 1 < n and js[i + 1] in "/*":
                state = "//" if js[i + 1] == "/" else "/*"
                i += 1
        elif state in ("'", '"'):
            if c == "\\":
                i += 1
            elif c == state or c == "\n":
                state = None
        elif state == "`":
            if c == "\\":
                i += 1
            elif c == "`":
                state = None
        elif state == "//":
            if c == "\n":
                state = None
        else:  # "/*"
            if c == "*" and i + 1 < n and js[i + 1] == "/":
                state = None
                i += 1
        i += 1
    return out


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


def _walk_files(dirs: list[str], exts: tuple[str, ...]) -> list[str]:
    found = set()
    for d in dirs:
        for root, _dirs, names in os.walk(d):
            for name in names:
                if name.endswith(exts):
                    found.add(os.path.join(root, name))
    return sorted(found)


def _read(path: str) -> str | None:
    try:
        return open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        return None


def find_bad_scripts(site_dir: str = "site"):
    """Return a list of (file, line, error) for every malformed inline script."""
    tasks = []  # (file, start_line, is_module, body)
    for path in _walk_files([site_dir], (".html",)):
        html = _read(path)
        if html is None:  # unreadable file is itself a problem
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


def find_bad_handlers(dirs: list[str]):
    """(file, line, error) for every on*= handler that fails node --check.

    The value is HTML-unescaped (entities decode before the browser's JS
    parse) and wrapped as a function body, mirroring handler compilation.
    Bodies are deduped before hitting node — the tree has ~2600 handlers but
    only ~100 unique bodies, so the added runtime is a rounding error.
    """
    occurrences: dict[str, list[tuple[str, int]]] = {}
    for path in _walk_files(dirs, (".html",)):
        html = _read(path)
        if html is None:
            continue  # reported by find_bad_scripts
        scan = _attr_scan_text(html)
        for line, raw in _iter_handlers(scan):
            if not raw.strip():
                continue
            body = _html_unescape(raw)
            occurrences.setdefault(body, []).append((path, line))

    bad: list[tuple[str, int, str]] = []
    with ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 2))) as pool:
        futures = {
            pool.submit(_check_block, "function __handler(event){ " + body + "\n}", False): body
            for body in occurrences
        }
        for fut, body in futures.items():
            res = fut.result()
            if res is None:
                continue
            _node_line, msg = res
            for path, line in occurrences[body]:
                bad.append((path, line, "on*= handler: " + msg))
    bad.sort()
    return bad


def find_curly_contamination(dirs: list[str]):
    """(file, line, error) for smart-quote contamination in JS surfaces.

    Hard-errors on U+2018/U+2019/U+201C/U+201D in `<script>` CODE position
    and anywhere in the raw source of an on*= attribute value. Runs on both
    .html and .j2 (Jinja-stripped) — for .j2 this is the only PR-time JS
    check we can run, which is exactly where the PR #2321 defect lived.
    """
    bad: list[tuple[str, int, str]] = []
    for path in _walk_files(dirs, (".html", ".j2")):
        text = _read(path)
        if text is None:
            continue
        if path.endswith(".j2"):
            text = _strip_jinja(text)
        for m in _SCRIPT_RE.finditer(text):
            attrs, body = m.group("attrs"), m.group("body")
            if not body.strip() or not _is_executable_js(attrs):
                continue
            for off in _curly_code_offsets(body):
                line = text.count("\n", 0, m.start("body") + off) + 1
                ch = body[off]
                bad.append((path, line,
                            f"curly quote {ch} (U+{ord(ch):04X}) in <script> CODE position — "
                            "smart-quote contamination; JS string delimiters must be ASCII ' or \""))
        scan = _attr_scan_text(text)
        for line, raw in _iter_handlers(scan):
            hits = _CURLY_RE.findall(raw)
            if hits:
                ch = hits[0]
                bad.append((path, line,
                            f"curly quote {ch} (U+{ord(ch):04X}) in on*= attribute — smart-quote "
                            "contamination; use ASCII quotes (entity-escape display text, e.g. &rsquo;)"))
    bad.sort()
    return bad


def _selftest() -> int:
    """Seeded-defect round-trip: the guard must catch each fixture defect."""
    with tempfile.TemporaryDirectory() as td:
        def w(name: str, content: str) -> None:
            with open(os.path.join(td, name), "w", encoding="utf-8") as f:
                f.write(content)

        # the PR #2321 defect verbatim class: curly quotes as JS string delimiters in onclick
        w("curly_onclick.html", '<button onclick="showTab(‘overview’)">x</button>')
        # plain broken handler JS (unterminated call — also the china_stocks truncated-attr shape)
        w("broken_handler.html", '<button onclick="showTab(">x</button>')
        # curly quote in <script> code position
        w("curly_script.html", "<script>var x = ‘oops’; use(x);</script>")
        # .j2: curly onclick must go red WITHOUT a render (node never sees this file)
        w("curly_tpl.html.j2", '{% if p %}<button onclick="pick(‘a’)">x</button>{% endif %}')
        # clean control: curly INSIDE a JS string literal (legit bilingual display copy),
        # entity-escaped curly in a handler, healthy handler, non-JS data island with curlies
        w("clean.html",
          '<script>var s = "don’t “quote”"; (function(){ return s; })();</script>\n'
          '<button onclick="alert(\'don&rsquo;t\')">ok</button>\n'
          '<script type="application/json">{"x": "‘not js’"}</script>')

        curly = find_curly_contamination([td])
        handlers = find_bad_handlers([td])
        scripts = find_bad_scripts(td)

        def flagged(problems, fname):
            return any(fname in p for p, _l, _m in problems)

        checks = [
            ("curly-quote onclick flagged as contamination", flagged(curly, "curly_onclick.html")),
            ("curly-quote onclick fails node --check", flagged(handlers, "curly_onclick.html")),
            ("broken handler JS fails node --check", flagged(handlers, "broken_handler.html")),
            ("<script> code-position curly flagged", flagged(curly, "curly_script.html")),
            (".j2 curly onclick flagged without a render", flagged(curly, "curly_tpl.html.j2")),
            ("clean control passes every check",
             not any("clean.html" in p for p, _l, _m in curly + handlers + scripts)),
        ]
        ok = True
        for label, passed in checks:
            print(f"  selftest {'PASS' if passed else 'FAIL'} — {label}")
            ok = ok and passed
        if not ok:
            print("check_inline_js: SELFTEST FAIL — the guard no longer catches a seeded defect.",
                  file=sys.stderr)
            return 1
        print("check_inline_js: selftest OK — all seeded defects caught, clean control passes.")
        return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]

    if shutil.which("node") is None:
        print("check_inline_js: ERROR — `node` not found on PATH; cannot verify inline JS.", file=sys.stderr)
        return 2

    if argv and argv[0] == "--selftest":
        return _selftest()

    dirs = argv or ["site"]
    bad: list[tuple[str, int, str]] = []
    for d in dirs:
        bad.extend(find_bad_scripts(d))
    bad.extend(find_bad_handlers(dirs))
    bad.extend(find_curly_contamination(dirs))
    bad.sort()
    if bad:
        print(f"check_inline_js: FAIL — {len(bad)} inline JS problem(s):\n", file=sys.stderr)
        for path, line, err in bad:
            print(f"  {path}:{line}  {err}", file=sys.stderr)
        print(
            "\nA broken inline script renders the page BLANK; a broken on*= handler "
            "throws on every click. Fix the source (template variable rendered empty, "
            "unescaped quotes in an attribute, or smart-quote contamination) and re-commit.",
            file=sys.stderr,
        )
        return 1
    print(f"check_inline_js: OK — inline scripts and on*= handlers under {', '.join(dirs)} parse cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
