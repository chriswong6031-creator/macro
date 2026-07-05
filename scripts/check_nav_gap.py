#!/usr/bin/env python3
"""Static guard: the shared nav menu must never jam against the viewport top.

The site menu bar (`<nav class="site-nav">`, emitted by `_site_nav.html.j2`/
`_navlinks.html.j2`, or the self-contained `<div class="topbar">` vector family)
carries NO built-in top gap in theme.css — `.site-nav { margin: 0 auto 16px }`
has a zero TOP margin on purpose. The breathing room above the menu comes entirely
from the host page giving `<body>` a top padding (the dominant convention:
`body { margin:0; padding: 18-26px }`).

That coupling is fragile: every time a NEW page sets `body { padding: 0 ... }`
(common when the author wants full-bleed content) — or forgets a `body{margin:0}`
reset and only inherits the 8px UA margin — the menu slams against the very top
of the viewport with no padding. It has happened repeatedly (subsector_rotation,
sector_central, sector_cycles, sector_heatmap, markets, …) and each was fixed by
hand after it shipped. See PR #471 ("restore top padding above menu header").

This guard measures the *declared* top gap of every menu-bearing page from its
own CSS cascade (inline `<style>` + linked LOCAL stylesheets + the menu element's
`style=` attribute) and fails if it falls below MIN_GAP_PX. It runs both as a
pre-merge PR check (ci.yml) and as a pre-deploy gate (pages.yml), so a jammed
menu is caught BEFORE it reaches users instead of after.

Usage:
    python -m scripts.check_nav_gap [SITE_DIR]   # default: site/
Exit codes: 0 = all clean · 1 = jammed menu(s) found.
"""
from __future__ import annotations

import os
import re
import sys

# A menu with less declared breathing room than this (px) above the bar reads as
# "no padding". Healthy pages sit at 18-26px; the jammed ones at 0-8px. 14px is a
# comfortable floor between the two populations.
MIN_GAP_PX = 14

# Only pages that actually carry the shared dropdown menu are in scope.
_MENU_MARKER = "nav-dd-menu"

# A declaration whose length is calc()/%/var()/keyword — present but unmeasurable.
# We never want to FALSE-fail such a page, so an unmeasurable gap is assumed fine.
_UNMEASURABLE = "unmeasurable"

# Opening tag of the menu bar: the first element whose class list contains
# `site-nav` or `topbar`.
_NAVBAR_RE = re.compile(
    r"<(?P<tag>\w+)\b[^>]*\bclass\s*=\s*[\"'][^\"']*\b(?P<kind>site-nav|topbar)\b[^\"']*[\"'][^>]*>",
    re.IGNORECASE,
)
_STYLE_ATTR_RE = re.compile(r"\bstyle\s*=\s*[\"'](?P<v>[^\"']*)[\"']", re.IGNORECASE)
# <link rel=stylesheet href=...> and <style>...</style>, scanned together so the
# cascade is built in true document order.
_CSS_SOURCE_RE = re.compile(
    r"<link\b[^>]*\brel\s*=\s*[\"']?stylesheet[\"']?[^>]*>"
    r"|<style\b[^>]*>(?P<css>.*?)</style>",
    re.IGNORECASE | re.DOTALL,
)
_HREF_RE = re.compile(r"\bhref\s*=\s*[\"'](?P<h>[^\"']+)[\"']", re.IGNORECASE)
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# Top-level `selector { decls }` (run AFTER @media/@supports blocks are stripped,
# so there is no brace nesting left to trip the non-greedy decls body).
_RULE_RE = re.compile(r"(?P<sel>[^{}]+)\{(?P<decls>[^{}]*)\}", re.DOTALL)
_ATBLOCK_RE = re.compile(r"@(?:media|supports|container)\b[^{]*\{", re.IGNORECASE)

_css_cache: dict[str, str] = {}


def _read_css(path: str) -> str:
    if path not in _css_cache:
        try:
            _css_cache[path] = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            _css_cache[path] = ""
    return _css_cache[path]


def _strip_at_blocks(css: str) -> str:
    """Drop @media/@supports/@container blocks so only base (always-on) rules
    remain. The base rule is the conservative floor for the top gap — a media
    query can only add space on some viewports, never remove the base guarantee."""
    out, i = [], 0
    while True:
        m = _ATBLOCK_RE.search(css, i)
        if not m:
            out.append(css[i:])
            break
        out.append(css[i:m.start()])
        depth, j = 1, m.end()  # walk to the matching close brace
        while j < len(css) and depth:
            depth += 1 if css[j] == "{" else (-1 if css[j] == "}" else 0)
            j += 1
        i = j
    return "".join(out)


def _px(value: str):
    """First length in a value -> px float, or _UNMEASURABLE for calc/%/var/keyword."""
    value = value.strip().split("!")[0].strip()  # drop !important
    m = re.match(r"(-?\d*\.?\d+)\s*(px|rem|em)?\b", value)
    if not m:
        return _UNMEASURABLE
    num = float(m.group(1))
    unit = m.group(2) or ("px" if num == 0 else "")
    if unit == "px":
        return num
    if unit in ("rem", "em"):
        return num * 16.0  # ~root font-size; good enough for a floor check
    return _UNMEASURABLE


def _top_of_shorthand(value: str):
    """Top value of a `margin`/`padding` shorthand (1-4 tokens; top is token 0)."""
    toks = value.strip().split()
    return _px(toks[0]) if toks else _UNMEASURABLE


def _last_compound(selector: str) -> str:
    """Right-most compound selector (what the rule actually targets)."""
    parts = re.split(r"[>+~\s]+", selector.strip())
    return parts[-1] if parts else ""


def _split_selector_list(selectors: str) -> list[str]:
    """Split a selector list on top-level commas only.

    Functional pseudo-classes such as :is(.a, .b) contain commas that are part
    of one selector. Treating those as selector-list separators can make a
    descendant rule look like it directly targets body.
    """
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in selectors:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
        if ch == "," and depth == 0:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
            continue
        buf.append(ch)
    s = "".join(buf).strip()
    if s:
        out.append(s)
    return out


def _decls_top(decls: str):
    """(padding_top, margin_top) declared by a rule body. Each is a px float,
    _UNMEASURABLE, or None when the property is not set in this rule. A `padding`
    or `margin` shorthand counts as setting the top (it resets the longhand)."""
    pad = mar = None
    for prop, val in re.findall(r"([a-zA-Z-]+)\s*:\s*([^;]+)", decls):
        p = prop.strip().lower()
        if p == "padding":
            pad = _top_of_shorthand(val)
        elif p == "padding-top":
            pad = _px(val)
        elif p == "margin":
            mar = _top_of_shorthand(val)
        elif p == "margin-top":
            mar = _px(val)
    return pad, mar


def _targets(last: str, kind: str) -> set[str]:
    """Which tracked elements this right-most compound selector targets."""
    out = set()
    if re.match(r"body([.#:\[]|$)", last):
        out.add("body")
    if re.search(r"\." + re.escape(kind) + r"(?![\w-])", last):  # `.site-nav`, `nav.site-nav`
        out.add("navbar")
    return out


def _accumulate(css: str, kind: str, body: dict, navbar: dict) -> None:
    """Fold one CSS string's base rules into the running cascade for `body` and
    the menu-bar element. Later calls (= later in document order) win per-property."""
    css = _strip_at_blocks(_COMMENT_RE.sub("", css))
    for rule in _RULE_RE.finditer(css):
        sels = rule.group("sel")
        if "." + kind not in sels and "body" not in sels:
            continue
        tgts: set[str] = set()
        for sel in _split_selector_list(sels):
            tgts |= _targets(_last_compound(sel), kind)
        if not tgts:
            continue
        pad, mar = _decls_top(rule.group("decls"))
        for name, store in (("body", body), ("navbar", navbar)):
            if name in tgts:
                if pad is not None:
                    store["pad"] = pad
                if mar is not None:
                    store["mar"] = mar


def _gap_for_page(path: str):
    """Return (declared_top_gap_px, navbar_kind) for a menu page, or None if the
    page carries no shared menu (out of scope). gap == -1 means the menu markup is
    present but no .site-nav/.topbar wrapper was found (a structural problem)."""
    html = open(path, encoding="utf-8", errors="replace").read()
    if _MENU_MARKER not in html:
        return None
    # Detect the menu bar in MARKUP only — `<style>`/`<script>` blocks and HTML
    # comments can contain `<nav class="site-nav">` as documentation text (e.g.
    # _vector_polish's migration note) and must not be mistaken for the real bar.
    markup = re.sub(r"<style\b[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    markup = re.sub(r"<script\b[^>]*>.*?</script>", "", markup, flags=re.DOTALL | re.IGNORECASE)
    markup = re.sub(r"<!--.*?-->", "", markup, flags=re.DOTALL)
    nm = _NAVBAR_RE.search(markup)
    if not nm:
        return (-1.0, "?")
    kind = nm.group("kind").lower()

    body = {"pad": None, "mar": None}
    navbar = {"pad": None, "mar": None}

    page_dir = os.path.dirname(path)
    for m in _CSS_SOURCE_RE.finditer(html):  # CSS sources in document order
        if m.group("css") is not None:  # inline <style>
            _accumulate(m.group("css"), kind, body, navbar)
            continue
        hm = _HREF_RE.search(m.group(0))  # linked stylesheet
        if not hm:
            continue
        href = hm.group("h").split("?")[0]
        if href.startswith(("http://", "https://", "//", "data:")):
            continue
        _accumulate(_read_css(os.path.normpath(os.path.join(page_dir, href))), kind, body, navbar)

    # The menu element's own inline style attribute wins over stylesheet rules.
    sa = _STYLE_ATTR_RE.search(nm.group(0))
    if sa:
        pad, mar = _decls_top(sa.group("v"))
        if pad is not None:
            navbar["pad"] = pad
        if mar is not None:
            navbar["mar"] = mar

    # Sum the offsets that push the menu down from the viewport top. An
    # unmeasurable contribution (calc/%/var) means a custom layout we can't judge
    # statically — assume it provides enough room rather than false-fail.
    gap = 0.0
    for store in (body, navbar):
        for key in ("pad", "mar"):
            v = store[key]
            if v == _UNMEASURABLE:
                return (float(MIN_GAP_PX), kind)
            if isinstance(v, (int, float)):
                gap += v
    return (gap, kind)


def find_jammed(site_dir: str = "site"):
    """Return [(file, gap_px, kind)] for every menu page whose top gap < MIN_GAP."""
    files = []
    for root, _dirs, names in os.walk(site_dir):
        for n in names:
            if n.endswith(".html"):
                files.append(os.path.join(root, n))
    files.sort()
    jammed = []
    for path in files:
        res = _gap_for_page(path)
        if res is None:
            continue
        gap, kind = res
        if gap < MIN_GAP_PX:
            jammed.append((path, gap, kind))
    return jammed


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    site_dir = argv[0] if argv else "site"

    jammed = find_jammed(site_dir)
    if jammed:
        print(
            f"check_nav_gap: FAIL — {len(jammed)} page(s) render the nav menu jammed "
            f"against the viewport top (< {MIN_GAP_PX}px of breathing room):\n",
            file=sys.stderr,
        )
        for path, gap, kind in jammed:
            shown = "no .site-nav/.topbar wrapper" if gap < 0 else f"{gap:.0f}px gap"
            print(f"  {path}  ({kind}: {shown})", file=sys.stderr)
        print(
            "\nThe .site-nav menu bar has no built-in top gap — it relies on the host "
            "page's `body` top padding.\nFix: give the page `body { margin:0; padding-top: 24px }` "
            "(or add the top to its existing\nbody padding shorthand). Pages styled by cycle.css "
            "inherit the gap from cycle.css's body rule.",
            file=sys.stderr,
        )
        return 1
    print(f"check_nav_gap: OK — every menu page under {site_dir}/ keeps a ≥{MIN_GAP_PX}px top gap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
