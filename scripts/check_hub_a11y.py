#!/usr/bin/env python3
"""Static a11y regression guard for the hub's globe-deck pages.

Detects five classes of accessibility regressions introduced (or silently
reintroduced) by the hub UX program.  All checks are pure-Python / stdlib:
html.parser + re + open(); NO browser, NO external deps — safe for ubuntu CI.

Pages in scope: site/index.html and any other committed page that embeds the
globe deck (detected by presence of the CSS class `gd-stage`).

Checks
------
a) aria-hidden focusable trap
   No naturally-focusable element (button / a / input / select / textarea) or
   element with a positive tabindex is allowed STATICALLY inside an
   aria-hidden="true" subtree.  tabindex="-1" is explicitly excluded (it
   removes the element from tab-order, which is the correct pattern when the
   element must remain hidden from AT).

b) html[lang] + boot-script data-lang presence
   Every in-scope page must:
     • have a lang= attribute on the <html> tag (not empty), AND
     • contain an inline boot <script> in <head> that references "data-lang"
       (the bilingual theme.js pattern that fires before first paint).

c) Light-theme pill contrast override
   The page CSS must contain the rule:
       html[data-theme="light"] .pill { color: color-mix(in srgb, <accent> <N>%, ... }
   where <accent share> N is an integer <= 60.  A higher share risks insufficient
   contrast on the white/light surface.

d) Viewport-fit + safe-area body padding
   • The viewport meta tag must include viewport-fit=cover.
   • The page's body CSS must reference env(safe-area-inset  (any variant) so
     notch/home-indicator padding is handled for edge-to-edge display.

e) theme.js documentElement.lang sync (WCAG 3.1.1 tripwire)
   site/theme.js must contain the string "documentElement.lang" — cheap grep-level
   proof that the WCAG 3.1.1 fix (syncing the html[lang] attribute at runtime) has
   not been silently reverted.

Usage
-----
    python -m scripts.check_hub_a11y [SITE_DIR]   # default: site/
Exit codes: 0 = all checks pass · 1 = one or more violations found.
"""
from __future__ import annotations

import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# ── constants ─────────────────────────────────────────────────────────────────

# HTML void elements (self-closing; never have children)
_VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)

# Naturally focusable tags (absent tabindex="-1")
_FOCUSABLE_TAGS = frozenset("button a input select textarea".split())

# ── check a: aria-hidden focusable trap ───────────────────────────────────────


class _AriaHiddenParser(HTMLParser):
    """Walk the static DOM tree; flag focusable elements inside aria-hidden subtrees."""

    def __init__(self):
        super().__init__()
        # Stack entries: (tag_name, is_aria_hidden_root)
        self._stack: list[tuple[str, bool]] = []
        self.violations: list[str] = []

    def _in_hidden(self) -> bool:
        return any(is_root for _, is_root in self._stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        d = dict(attrs)
        is_hidden_root = d.get("aria-hidden") == "true"

        if self._in_hidden():
            tabindex = (d.get("tabindex") or "").strip()
            # An <a> without href is NOT focusable per spec — skip it
            if tag == "a" and "href" not in d:
                pass
            # Naturally focusable tags are problematic unless they have tabindex="-1"
            elif tag in _FOCUSABLE_TAGS and tabindex != "-1":
                self.violations.append(
                    f"<{tag}> (tabindex={d.get('tabindex', 'absent')!r}) "
                    "is focusable inside aria-hidden=\"true\" subtree"
                )
            # Non-focusable tags with an explicit positive tabindex are also problematic
            elif "tabindex" in d and tabindex not in ("-1", "") and tag not in _FOCUSABLE_TAGS:
                self.violations.append(
                    f"<{tag} tabindex={tabindex!r}> is focusable inside aria-hidden=\"true\" subtree"
                )

        if tag not in _VOID:
            self._stack.append((tag, is_hidden_root))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _VOID:
            return
        # Pop the most-recent matching open tag (handles malformed HTML gracefully)
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                self._stack.pop(i)
                break


def check_a_aria_hidden(html: str) -> list[str]:
    """Return violation strings for focusable elements inside aria-hidden subtrees."""
    parser = _AriaHiddenParser()
    parser.feed(html)
    return parser.violations


# ── check b: html[lang] + boot-script data-lang ──────────────────────────────

_HTML_LANG_RE = re.compile(r"<html\b[^>]*\blang\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
# The boot script must reference data-lang — a string-presence check inside a
# <script> that appears before </head> (no src= attribute).
_BOOT_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
_HEAD_BLOCK_RE = re.compile(r"<head\b[^>]*>(.*?)</head>", re.DOTALL | re.IGNORECASE)


def check_b_lang_boot(html: str) -> list[str]:
    """Return violations for missing html[lang] or absent data-lang boot logic."""
    violations: list[str] = []

    m = _HTML_LANG_RE.search(html)
    if not m or not m.group(1).strip():
        violations.append(
            "<html> element is missing a non-empty lang= attribute "
            "(required for WCAG 3.1.1 / screen-reader language identification)"
        )

    # Look for a boot script inside <head> that contains data-lang
    head_m = _HEAD_BLOCK_RE.search(html)
    head = head_m.group(1) if head_m else html[:5000]  # fallback: first 5 KB
    found_data_lang = False
    for sm in _BOOT_SCRIPT_RE.finditer(head):
        if "data-lang" in sm.group(1):
            found_data_lang = True
            break
    if not found_data_lang:
        violations.append(
            "No inline boot <script> in <head> references \"data-lang\" — "
            "the bilingual language-detection boot logic appears to be missing"
        )
    return violations


# ── check c: light-theme pill contrast override ───────────────────────────────

# Matches: html[data-theme="light"] .pill { color: color-mix(in srgb, var(--accent) N%, ... }
# We capture the accent percentage N.
_PILL_LIGHT_RE = re.compile(
    r'html\[data-theme=["\']light["\']\]\s*\.pill\s*\{[^}]*color\s*:\s*color-mix\s*\(\s*in\s+srgb\s*,\s*var\(--accent\)\s+(\d+)%',
    re.IGNORECASE | re.DOTALL,
)


def check_c_pill_contrast(html: str) -> list[str]:
    """Return violations for missing or over-tinted light-theme pill override."""
    m = _PILL_LIGHT_RE.search(html)
    if not m:
        return [
            "Missing light-theme pill contrast override rule: "
            "html[data-theme=\"light\"] .pill { color: color-mix(in srgb, var(--accent) N%, ...) } "
            "— this rule is required to ensure pill text remains legible on light backgrounds"
        ]
    pct = int(m.group(1))
    if pct > 60:
        return [
            f"Light-theme pill contrast override uses {pct}% accent share "
            f"(found: color-mix(in srgb, var(--accent) {pct}%, ...)) — "
            "must be <= 60% to maintain sufficient text contrast on light backgrounds"
        ]
    return []


# ── check d: viewport-fit + safe-area body padding ───────────────────────────

_VIEWPORT_META_RE = re.compile(
    r'<meta\s[^>]*name\s*=\s*["\']viewport["\'][^>]*content\s*=\s*["\']([^"\']+)["\']'
    r'|<meta\s[^>]*content\s*=\s*["\']([^"\']+)["\']\s*[^>]*name\s*=\s*["\']viewport["\']',
    re.IGNORECASE,
)
_SAFE_AREA_BODY_RE = re.compile(r"body\s*\{[^}]*env\(safe-area-inset", re.DOTALL | re.IGNORECASE)


def check_d_viewport_safe_area(html: str) -> list[str]:
    """Return violations for missing viewport-fit=cover or safe-area body padding."""
    violations: list[str] = []

    meta_m = _VIEWPORT_META_RE.search(html)
    if not meta_m:
        violations.append(
            "No viewport <meta> tag found — cannot verify viewport-fit=cover"
        )
    else:
        content = (meta_m.group(1) or meta_m.group(2) or "")
        if "viewport-fit=cover" not in content:
            violations.append(
                f"viewport <meta> content {content!r} does not include viewport-fit=cover "
                "— required for edge-to-edge display on iOS notch / home-indicator devices"
            )

    if not _SAFE_AREA_BODY_RE.search(html):
        violations.append(
            "body{} CSS block does not reference env(safe-area-inset — "
            "required to pad content away from the notch and home indicator"
        )
    return violations


# ── check e: theme.js documentElement.lang sync ──────────────────────────────


def check_e_theme_js_lang_sync(site_dir: str) -> list[str]:
    """Return violations if site/theme.js is missing documentElement.lang sync."""
    theme_path = os.path.join(site_dir, "theme.js")
    if not os.path.isfile(theme_path):
        return [
            f"{theme_path}: file not found — cannot verify WCAG 3.1.1 "
            "documentElement.lang sync"
        ]
    try:
        src = open(theme_path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return [f"{theme_path}: could not read ({exc})"]

    if "documentElement.lang" not in src:
        return [
            f"{theme_path}: 'documentElement.lang' not found — the WCAG 3.1.1 fix "
            "that syncs the html[lang] attribute at runtime appears to have been reverted"
        ]
    return []


# ── page discovery ────────────────────────────────────────────────────────────

_GD_STAGE_RE = re.compile(r"\bgd-stage\b")


def _find_globe_deck_pages(site_dir: str) -> list[str]:
    """Return paths of all HTML files in site_dir that embed the globe deck."""
    pages: list[str] = []
    for root, _dirs, files in os.walk(site_dir):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            path = os.path.join(root, name)
            try:
                html = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if _GD_STAGE_RE.search(html):
                pages.append(path)
    return sorted(pages)


# ── runner ────────────────────────────────────────────────────────────────────


def run_checks(site_dir: str) -> list[tuple[str, str]]:
    """Return a list of (location, message) violation tuples, empty on clean."""
    all_violations: list[tuple[str, str]] = []

    # Check e is file-level, not per-page.
    for msg in check_e_theme_js_lang_sync(site_dir):
        all_violations.append(("site/theme.js", msg))

    pages = _find_globe_deck_pages(site_dir)
    if not pages:
        # No globe-deck pages found — nothing to check; not a failure.
        return all_violations

    for path in pages:
        try:
            html = open(path, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            all_violations.append((path, f"could not read file: {exc}"))
            continue

        for msg in check_a_aria_hidden(html):
            all_violations.append((path, f"(a) aria-hidden focusable trap: {msg}"))
        for msg in check_b_lang_boot(html):
            all_violations.append((path, f"(b) lang/boot: {msg}"))
        for msg in check_c_pill_contrast(html):
            all_violations.append((path, f"(c) pill contrast: {msg}"))
        for msg in check_d_viewport_safe_area(html):
            all_violations.append((path, f"(d) viewport/safe-area: {msg}"))

    return all_violations


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    site_dir = argv[0] if argv else "site"

    violations = run_checks(site_dir)

    if violations:
        print(
            f"check_hub_a11y: FAIL — {len(violations)} violation(s) found:\n",
            file=sys.stderr,
        )
        for location, msg in violations:
            print(f"  {location}: {msg}", file=sys.stderr)
        print(
            "\nFix each violation before merging. "
            "See scripts/check_hub_a11y.py docstring for fix patterns.",
            file=sys.stderr,
        )
        return 1

    pages_count = len(_find_globe_deck_pages(site_dir))
    print(
        f"check_hub_a11y: OK — {pages_count} globe-deck page(s) clean "
        f"(5 checks: aria-hidden traps, lang boot, pill contrast, "
        f"viewport safe-area, theme.js lang sync)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
