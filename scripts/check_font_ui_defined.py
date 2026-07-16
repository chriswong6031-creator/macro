#!/usr/bin/env python3
"""Font-UI definition guard for standalone templates (PR #2647 recurrence tripwire).

The bug class: a page whose body-level CSS sets `font-family: var(--font-ui)`
but neither links theme.css (which defines the token) nor defines `--font-ui`
locally renders the ENTIRE page in the browser default serif (Times). An
undefined custom property makes the font-family declaration
invalid-at-computed-value -> unset -> inherit from the UA default. The #2195
sweep introduced exactly this on 6 template families; #2647 fixed them with a
local :root definition + the _interfonts.html.j2 include (commodities.html.j2
precedent).

All checks are pure-Python / stdlib: re + open(); NO browser, NO external
deps — safe for ubuntu CI.

Files in scope: templates/*.html.j2, excluding partials (basename starting
with `_`). A partial referencing var(--font-ui) is allowed — the token
resolves at host-page level — and only emits a warning-level note.

Checks
------
a) body-level var(--font-ui) coverage
   For every non-partial template whose body{} CSS sets the font via
   `font-family:` or the `font:` shorthand referencing var(--font-ui), the
   template must either:
     • link theme.css — a <link rel="stylesheet"> whose href attribute points
       at theme.css (matching the href VALUE, never the bare string
       "theme.css": CSS comments mention theme.css and defeat naive greps), OR
     • define `--font-ui:` locally (a definition, i.e. `--font-ui:` outside
       var(...) usage), in comment-stripped text.
   Neither present = HARD violation.

b) _interfonts include (warning only)
   A template that passes via a local `--font-ui:` definition should also
   include _interfonts.html.j2 so the self-hosted Inter @font-face blocks
   actually load — otherwise the token resolves to whatever system fallback
   follows Inter in the stack. Missing include = warning, not a failure.

Usage
-----
    python -m scripts.check_font_ui_defined [TEMPLATES_DIR]   # default: templates/
Exit codes: 0 = all checks pass (warnings allowed) · 1 = violations found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ── comment stripping ─────────────────────────────────────────────────────────

# CSS/JS block comments and HTML comments both hide text that must not count
# as a definition or a body rule (and "theme.css" inside a CSS comment must
# never satisfy the link check — though the link check matches href= values,
# stripping keeps every downstream regex honest).
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Jinja tags inside a style block would otherwise unbalance the flat brace
# scan (a single {{ … }} inside body{} suppresses EVERY rule match in the
# sheet — a total-scan false negative, not a one-rule truncation).
_JINJA_TAG_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)


def strip_comments(text: str) -> str:
    """Remove CSS/JS block comments and HTML comments."""
    return _HTML_COMMENT_RE.sub("", _CSS_COMMENT_RE.sub("", text))


def strip_jinja(text: str) -> str:
    """Replace Jinja {{ … }} / {% … %} tags with a space (avoids token welds)."""
    return _JINJA_TAG_RE.sub(" ", text)


# ── check: body-level var(--font-ui) usage ────────────────────────────────────

# Flat CSS rule scan: selector{declarations}. Declaration blocks in the
# templates do not nest; @media wrappers realign because the block part
# cannot contain braces, so the scan recovers at the inner rule.
_CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")

# `body` as an element selector token: start-of-selector or after a
# combinator/whitespace/list-comma, not part of a longer ident (excludes
# tbody, .body-x). Type selectors are case-insensitive per the CSS spec.
_BODY_TOKEN_RE = re.compile(r"(?:^|[\s>+~,])body(?![\w-])", re.IGNORECASE)

# font-family: or the font: shorthand (excludes font-size, -webkit-font-smoothing
# etc. because the optional -family must be followed directly by the colon).
_FONT_DECL_RE = re.compile(r"\bfont(?:-family)?\s*:\s*([^;{}]*)", re.IGNORECASE)

# var() is case-insensitive as a function name; the custom property name is
# NOT (--FONT-UI would be a different — equally undefined — token, kept out
# of scope deliberately: theme.css only ever defines lowercase --font-ui).
_VAR_FONT_UI_RE = re.compile(r"[vV][aA][rR]\(--font-ui(?![\w-])")


def _block_sets_font_ui(block: str) -> bool:
    """True if a declaration block sets font/font-family via var(--font-ui)."""
    for m in _FONT_DECL_RE.finditer(block):
        value = re.sub(r"\s+", "", m.group(1))
        if _VAR_FONT_UI_RE.search(value):
            return True
    return False


def uses_body_font_ui(text: str) -> bool:
    """True if comment-stripped text has a body{} rule fonted via var(--font-ui)."""
    for m in _CSS_RULE_RE.finditer(text):
        selector, block = m.group(1), m.group(2)
        if _BODY_TOKEN_RE.search(selector) and _block_sets_font_ui(block):
            return True
    return False


# ── check: theme.css stylesheet link ──────────────────────────────────────────

_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_REL_STYLESHEET_RE = re.compile(r"""\brel\s*=\s*["']stylesheet["']""", re.IGNORECASE)
# href VALUE whose final path segment is theme.css (optionally ?query) —
# matches href="theme.css" and href="../theme.css", not href="dark_theme.css".
_HREF_THEME_RE = re.compile(
    r"""\bhref\s*=\s*["'](?:[^"']*/)?theme\.css(?:\?[^"']*)?["']""", re.IGNORECASE
)


def links_theme_css(text: str) -> bool:
    """True if a <link rel="stylesheet"> tag's href attribute points at theme.css."""
    for m in _LINK_TAG_RE.finditer(text):
        tag = m.group(0)
        if _REL_STYLESHEET_RE.search(tag) and _HREF_THEME_RE.search(tag):
            return True
    return False


# ── check: local --font-ui definition ─────────────────────────────────────────

# A definition is `--font-ui:` — usage is always `var(--font-ui)` or
# `var(--font-ui, fallback)`, never followed by a colon. The lookbehind guards
# against a pathological `var(--font-ui:` anyway. Case-sensitive: custom
# property names are case-sensitive, and theme.css defines lowercase.
_FONT_UI_DEF_RE = re.compile(r"(?<!var\()--font-ui\s*:")


def defines_font_ui(text: str) -> bool:
    """True if comment-stripped text contains a --font-ui: definition."""
    return bool(_FONT_UI_DEF_RE.search(text))


# ── check: _interfonts include ────────────────────────────────────────────────

_INTERFONTS_RE = re.compile(r"\{%-?\s*include\s+[\"']_interfonts\.html\.j2[\"']")


def includes_interfonts(text: str) -> bool:
    """True if the template includes the _interfonts.html.j2 partial."""
    return bool(_INTERFONTS_RE.search(text))


# ── runner ────────────────────────────────────────────────────────────────────


def run_checks(templates_dir: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (violations, warnings) as lists of (path, message) tuples."""
    violations: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []

    root = Path(templates_dir)
    for path in sorted(root.glob("*.html.j2")):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            violations.append((str(path), f"could not read file: {exc}"))
            continue

        if path.name.startswith("_"):
            # Partials resolve var(--font-ui) at host-page level — allowed.
            if "var(--font-ui" in strip_comments(raw):
                warnings.append(
                    (
                        str(path),
                        "partial references var(--font-ui) — allowed (resolves at "
                        "host page level), but every host must define the token",
                    )
                )
            continue

        text = strip_comments(raw)
        # Jinja tags are stripped for the CSS-facing scans only — the
        # interfonts check below must still SEE the {% include %} tag.
        css_text = strip_jinja(text)
        if not uses_body_font_ui(css_text):
            continue

        has_theme = links_theme_css(css_text)
        has_local = defines_font_ui(css_text)
        if not has_theme and not has_local:
            violations.append(
                (
                    str(path),
                    "body-level CSS sets font via var(--font-ui) but the template "
                    'neither links theme.css (<link rel="stylesheet" href=…theme.css>) '
                    "nor defines --font-ui: locally — the undefined custom property "
                    "makes font-family invalid-at-computed-value -> unset, and the "
                    "whole page renders in the browser default serif (Times). Fix "
                    "pattern (#2647): local :root --font-ui definition + "
                    '{% include "_interfonts.html.j2" %} (commodities.html.j2 precedent)',
                )
            )
        elif has_local and not has_theme and not includes_interfonts(text):
            warnings.append(
                (
                    str(path),
                    "defines --font-ui locally but does not include "
                    "_interfonts.html.j2 — the self-hosted Inter @font-face blocks "
                    "will not load, so the token falls through to system fonts",
                )
            )

    return violations, warnings


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    templates_dir = argv[0] if argv else "templates"

    if not Path(templates_dir).is_dir():
        print(
            f"check_font_ui_defined: FAIL — templates dir '{templates_dir}' not found",
            file=sys.stderr,
        )
        return 1

    violations, warnings = run_checks(templates_dir)

    for location, msg in warnings:
        print(f"warning: {location}: {msg}")

    if violations:
        print(
            f"check_font_ui_defined: FAIL — {len(violations)} violation(s) found:\n",
            file=sys.stderr,
        )
        for location, msg in violations:
            print(f"  {location}: {msg}", file=sys.stderr)
        print(
            "\nFix each violation before merging. "
            "See scripts/check_font_ui_defined.py docstring for the fix pattern.",
            file=sys.stderr,
        )
        return 1

    print(
        "check_font_ui_defined: OK — every template with a body-level "
        "var(--font-ui) rule links theme.css or defines the token locally"
        + (f" ({len(warnings)} warning(s))" if warnings else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
