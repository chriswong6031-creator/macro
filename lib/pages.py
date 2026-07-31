"""Site page writing — every builder that emits site/**/*.html goes through
write_page() so each page carries the data-base fetch shim even when a builder
runs standalone (its documented usage, e.g. `python -m scripts.build_baskets`)
outside the full render pipeline.

The shim (templates/data_base.js) reroutes the heavy per-ticker OHLC +
search-library fetches to R2 when window.DATA_BASE is set; empty -> no-op. It
must load FIRST, before any page code runs a data fetch, so it goes at the TOP
of <head>, non-deferred, with a depth-aware src prefix ("../" per directory
under site/). Without write-time injection, committing a standalone builder's
output silently strips the tag and regresses the R2 rerouting (nearly shipped
in #1045). scripts/inject_data_base.py — the CI post-render step — imports
inject_text() from here and remains the idempotent safety net for any page
that slips past this path.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from lib import config

log = logging.getLogger("pages")

DBASE_MARKER = "data-dbase"
_HEAD_RE = re.compile(r"<head[^>]*>", re.IGNORECASE)

# Site-relative pages whose BYTES are hand-authored source, not build output
# (operator-ordered flagship redesign 2026-07-28) — like site/index.html, the
# committed file IS the source and no generator derives it.
# Lives HERE, not in the builder, because two independent consumers need the
# same fact and neither can import the other cheaply: scripts/build_free_content
# (skips the write; exempts them from its drift + D5 orphan checks, re-exported
# there as HAND_AUTHORED) and scripts/externalize_css (skips the post-render
# inline-<style> lift that would otherwise rewrite committed bytes every render).
# A module-level import of build_free_content from the sweep is NOT an option:
# it pulls jinja2, which the ci-main-heartbeat template-site-sync pack that runs
# tests/test_externalize_css.py deliberately does not install.
# Paths are posix, anchored at the site root — a sub-directory page that merely
# shares a basename is an ordinary page and stays swept.
HAND_AUTHORED_PAGES: frozenset[str] = frozenset({
    "products/market-terminal.html",
    "products/mastermind-ai.html",
    "products/market-dashboards.html",
})

# --- rendered ticker universe (cross-page dead-link filter) ------------------
# WHICH stocks/<TICKER>.html pages exist is decided nightly by DATA, not by a
# template: build_ticker_pages walks membership.parquet and then drops any
# ticker with no stockdata blob, a `limited` profile, or fewer than three
# substantive sections. 2,842 tickers are membership-active; 1,666 get a page.
#
# Every other surface that links a symbol draws from a WIDER source — peer cards
# from factordata/factors.json, the movers board from the heatmap, the crypto
# rails shelf from baskets/membership.json — so each can name a symbol that
# never got a page. scripts/check_site_asset_refs.py measured 47 such targets
# carrying 211 dead links the first time anyone looked: 197 peer cards over 35
# symbols, 12 movers rows/chips, 2 crypto tiles.
#
# The predicate here is deliberately "a page SHIPS for this ticker", not "this
# ticker passes the render gate". It is what the reader experiences and what the
# guard checks; it needs no cross-builder copy of a four-stage gate that keeps
# moving; and it stays correct the next time that gate changes.
#
# Callers snapshot this ONCE per run and pass the set down. build_ticker_pages
# must snapshot BEFORE its own loop starts writing, so the answer cannot depend
# on how far through the alphabet the loop has got. Nothing ever prunes
# site/stocks/, so the pre-run set is a SUBSET of what ships afterwards: a
# ticker whose page is brand new tonight goes unlinked for one night rather than
# being linked to a 404, and picks up its links on the next render.


def _committed_ticker_pages(stocks_dir: Path) -> set[str]:
    """Ticker pages git tracks that this checkout does not hold.

    Reading the filter off the VISIBLE pages alone is only sound when the tree
    holds everything that ships. A lane whose checkout is partial — a sparse
    cone, a scoped render, an interrupted sync — sees fewer pages than
    production serves, and would then silently un-link every peer/movers/crypto
    symbol whose page merely was not fetched. That is the same shape that
    deleted a live stylesheet in #3988/#4042, pointed the other way: not a 404,
    but a site-wide quiet loss of navigation.

    Returns the empty set when there is no committed baseline to consult (no git
    checkout, no git binary, path outside the repo): nothing can then be
    committed-but-absent, so the on-disk scan is complete by definition. An
    ABSENT baseline is not an unreadable one — it must not disable the filter.
    """
    # Absolute, so the pathspec still means the same directory after `cwd`
    # walks up to the nearest one that exists (the partial-checkout case).
    stocks_dir = stocks_dir.resolve()
    cwd = stocks_dir
    while not cwd.is_dir() and cwd != cwd.parent:
        cwd = cwd.parent
    if not cwd.is_dir():
        return set()
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--", str(stocks_dir)],
            cwd=str(cwd), capture_output=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:  # noqa: BLE001
        log.debug("rendered_ticker_pages: no git baseline (%s)", e)
        return set()
    if proc.returncode != 0:
        return set()
    names = proc.stdout.decode("utf-8", "replace").split("\0")
    return {
        PurePosixPath(n).stem for n in names
        if n.endswith(".html") and PurePosixPath(n).stem != "index"
    }


def rendered_ticker_pages(site_dir: Path) -> frozenset[str]:
    """Tickers that have a `stocks/<TICKER>.html` page in the shipped tree.

    Union of what is on disk and what is committed-but-absent, so the answer is
    "does this page ship", not "did this checkout happen to fetch it".
    """
    stocks_dir = Path(site_dir) / "stocks"
    on_disk = {p.stem for p in stocks_dir.glob("*.html") if p.stem != "index"}
    return frozenset(on_disk | _committed_ticker_pages(stocks_dir))


# --- asset optimization (content-hash cache-busting + defer) -----------------
# A post-render sweep (scripts/optimize_assets.py) rewrites every local .js/.css
# reference to carry a ?v=<content-hash> query and marks non-critical <script>s
# `defer`, so the edge can cache them `immutable` (see app/deploy/Caddyfile) and
# the browser stops blocking the main thread on synchronous script execution.
# Kept here beside inject_text() because both are page-string post-processors.
_OPEN_TAG_RE = re.compile(r"<(script|link)\b([^>]*)>", re.IGNORECASE)
_SRC_ATTR_RE = re.compile(r'\b(src|href)\s*=\s*"([^"]*)"', re.IGNORECASE)
_HAS_DEFER_ASYNC_RE = re.compile(r"\b(defer|async)\b", re.IGNORECASE)
_MODULE_RE = re.compile(r'\btype\s*=\s*"module"', re.IGNORECASE)
_SCHEME_RE = re.compile(r"[a-zA-Z][\w+.-]*:")  # http:, https:, data:, mailto: ...
# Our OWN stamp, and only ours: `?v=<8 lowercase hex>` with nothing else in the
# query. A ref wearing this is re-hashed when the file behind it changed; any
# other query (a hand-written ?v=3, ?foo=bar, a fragment) is still left alone.
_OUR_STAMP_RE = re.compile(r"^([^?#]+)\?v=[0-9a-f]{8}$")
# Re-stamping is only safe on the tag that actually LOADS the asset. A
# `<link rel="preload">` hint mirrors a URL owned elsewhere (preload_css_text
# copies it from the stylesheet, or from an @import that this sweep never
# rewrites) — bumping the hint alone would turn it into a second cache key and
# double-fetch the file instead of deduping it.
_REL_ATTR_RE = re.compile(r'\brel\s*=\s*"([^"]*)"', re.IGNORECASE)


def _is_local_asset(url: str) -> bool:
    """True for a same-origin relative ref (no scheme, not protocol-relative)."""
    return bool(url) and not url.startswith("//") and not _SCHEME_RE.match(url)


def optimize_assets_text(text: str, hash_for: Callable[[str], Optional[str]]) -> str:
    """Rewrite local .js/.css refs in `text` for cache-busting + non-blocking JS.

    For each ``<script src=…>`` / ``<link href=…>`` pointing at a same-origin
    ``.js``/``.css`` file:
      * append ``?v=<hash>`` (from ``hash_for(url)``) so the edge can cache it
        ``immutable`` — a content change yields a new URL, never a stale hit;
      * add ``defer`` to scripts (keeps them off the critical path) unless they
        are ``async``/``type=module`` or the data-base shim (``data-dbase``),
        which must stay blocking at the top of <head> before any fetch.

    Stable, not frozen: a ref already wearing OUR stamp (``?v=<8 hex>`` and
    nothing else) is RE-hashed, so a re-run after the file changed yields the new
    URL. Re-running against unchanged files is still a no-op, and ``defer``/
    ``async`` scripts are not re-marked. Any other query (a hand-written
    ``?v=3``, ``?foo=bar``) or a fragment is left exactly as authored.
    ``hash_for`` returns ``None`` when the asset can't be hashed (missing on
    disk) — the ref is then left as-is but a script still gets ``defer``.

    Re-stamping is the whole point at the edge: ``app/deploy/Caddyfile`` serves
    versioned requests ``immutable, max-age=1y``, so a stamp that never moves
    pins every returning visitor to the bytes that file had when the page was
    first rendered.
    """
    def _rewrite(m: "re.Match[str]") -> str:
        kind = m.group(1).lower()
        attrs = m.group(2)
        if DBASE_MARKER in attrs:              # data-base shim: never touch
            return m.group(0)
        am = _SRC_ATTR_RE.search(attrs)
        if not am:                             # inline <script> / no href
            return m.group(0)
        attr_name, url = am.group(1).lower(), am.group(2)
        if (kind == "script") != (attr_name == "src"):
            return m.group(0)                  # href on <script> etc. — skip
        if not _is_local_asset(url):
            return m.group(0)
        # A ref already wearing OUR stamp is re-hashed, not skipped: `immutable,
        # max-age=1y` at the edge means a frozen stamp pins visitors to the old
        # bytes forever once the file behind it changes. (theme.js was stamped
        # stale on 1,509 pages across four generations of hash before this.)
        # Any other query or a fragment is still left exactly as authored, and
        # only the tag that actually LOADS the asset may be re-stamped.
        rel = _REL_ATTR_RE.search(attrs)
        loads_it = kind == "script" or (rel is not None and "stylesheet" in rel.group(1).lower())
        stamped = _OUR_STAMP_RE.match(url) if loads_it else None
        bare = stamped.group(1) if stamped else url
        low = bare.lower()
        if (not stamped and ("?" in url or "#" in url)) or not (low.endswith(".js") or low.endswith(".css")):
            return m.group(0)                  # foreign query/fragment, or not a hashed asset
        new_attrs = attrs
        h = hash_for(bare)
        if h:
            new_url = f'{am.group(1)}="{bare}?v={h}"'
            new_attrs = new_attrs[: am.start()] + new_url + new_attrs[am.end():]
        if kind == "script" and not _HAS_DEFER_ASYNC_RE.search(new_attrs) and not _MODULE_RE.search(new_attrs):
            new_attrs = new_attrs.rstrip() + " defer"
        return f"<{m.group(1)}{new_attrs}>"

    return _OPEN_TAG_RE.sub(_rewrite, text)


# --- inline CSS externalization ----------------------------------------------
# A post-render sweep (scripts/externalize_css.py) lifts each large inline
# <style> block into a content-hashed external stylesheet linked IN PLACE, so the
# design-system + section CSS caches `immutable` across daily re-renders instead
# of re-shipping inside every 60s-TTL HTML page. In-place <link> (not hoisted)
# preserves BOTH the cascade (rule source order) and the first-paint profile
# (only the pre-existing <head> block blocks paint). Byte-for-byte CSS → no
# render change. Reuses the ?v= immutable rule from optimize_assets — no Caddy
# change. Tiny blocks stay inline (a request isn't worth a few hundred bytes).
_STYLE_BLOCK_RE = re.compile(r"<style\b([^>]*)>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_MEDIA_ATTR_RE = re.compile(r'\bmedia\s*=\s*"([^"]*)"', re.IGNORECASE)
_SVG_TAG_RE = re.compile(r"<svg\b|</svg\s*>", re.IGNORECASE)


def _svg_spans(text: str) -> list[tuple[int, int]]:
    """Top-level ``<svg>…</svg>`` spans in `text` (nesting collapsed via depth
    count; an unclosed ``<svg`` extends to end-of-text). Used to keep SVG-internal
    ``<style>`` blocks inline: an HTML ``<link rel=stylesheet>`` inside foreign
    (SVG) content parses as an inert SVG-namespace element — the sheet never
    loads and the figure renders unstyled (report figures went blank, 2026-07-21)."""
    spans: list[tuple[int, int]] = []
    depth = 0
    start: Optional[int] = None
    for m in _SVG_TAG_RE.finditer(text):
        if not m.group(0).startswith("</"):
            if depth == 0:
                start = m.start()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, m.end()))
                start = None
    if start is not None:
        spans.append((start, len(text)))
    return spans


# --- head preload hints for late-discovered CSS ------------------------------
# Every stylesheet on these pages is render-blocking, so first paint waits for the
# LAST one to arrive — which makes *when the browser learns the URL* as costly as
# the download. Two structural delays put that discovery late:
#
#   1. externalize_css lifts inline <style> in place, so macro.html's 6 biggest
#      sheets (265KB) sit at byte ~48,000 and one at ~109,000 of a 582KB document.
#      The preload scanner only sees bytes that have ARRIVED, so on a cold mobile
#      connection (TCP slow-start) their fetch waits several extra round-trips
#      that the head's own sheets did not.
#   2. theme.css opens with `@import url(product-nav-icons.css)`. An @import is
#      invisible until its parent has downloaded AND begun parsing, so that 33KB
#      sheet is strictly serialized behind 108KB of theme.css — a guaranteed extra
#      round-trip (~460ms at the measured origin TTFB) in front of first paint.
#
# Both are fixed by hoisting DISCOVERY only: emit `<link rel=preload as=style>` in
# <head> for each late URL. The real <link rel=stylesheet>/@import stays exactly
# where it is, so rule order — and therefore the cascade — is untouched; the sheet
# is simply already in the preload cache when the parser reaches it. Same URL +
# same-origin, so the preload and the real reference share a cache entry and the
# byte fetch happens once.
#
# Runs LAST (inside scripts/optimize_assets.py, after ?v= stamping) because a
# preload href that differs from the stylesheet href by so much as a query string
# is a different cache key — it would double-fetch instead of dedupe.
_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_REL_ATTR_RE = re.compile(r'\brel\s*=\s*"([^"]*)"', re.IGNORECASE)
_HREF_ATTR_RE = re.compile(r'\bhref\s*=\s*"([^"]*)"', re.IGNORECASE)
_AS_ATTR_RE = re.compile(r'\bas\s*=\s*"([^"]*)"', re.IGNORECASE)
_CSS_IMPORT_RE = re.compile(
    r"""@import\s+(?:url\(\s*)?["']?([^"')\s;]+)["']?""", re.IGNORECASE
)


def css_imports(css: str) -> list[str]:
    """Relative URLs @import-ed by a stylesheet, in source order. Only leading
    @imports matter for preloading (CSS requires them before any rule), so scan
    just the head of the file — that also keeps an `@import` inside a comment or
    a string deep in a 100KB sheet from producing a bogus preload."""
    out: list[str] = []
    for m in _CSS_IMPORT_RE.finditer(css[:4096]):
        url = m.group(1).strip()
        if url and _is_local_asset(url):
            out.append(url)
    return out


def preload_css_text(text: str, imports_for: Callable[[str], list[str]]) -> str:
    """Add `<link rel=preload as=style>` to <head> for every stylesheet the parser
    would otherwise discover late: those linked from the BODY, and those reached
    via @import from any linked sheet (``imports_for(href) -> [url, …]``, resolved
    relative to that sheet).

    Hints are inserted after the last existing <head> stylesheet so the head's own
    render-blocking sheets keep first claim on bandwidth. Idempotent: a URL already
    preloaded (or already linked in the head) is skipped. Body <link>s inside inline
    <svg> are ignored — they are inert there and never fetched (see _svg_spans)."""
    # Refresh EXISTING stylesheet preloads before deciding which hints are
    # missing. optimize_assets_text deliberately skips rel=preload because a
    # preload mirrors a URL owned by the real stylesheet link; independently
    # re-hashing it could create a second cache key. The old implementation
    # never closed the other half of that contract, though: once a hint existed,
    # it stayed on its old ?v= forever while the real stylesheet advanced.
    #
    # PR #4015 exposed the production shape on 3,263 pages:
    #
    #   preload    navigation-refresh.css?v=88af7a13
    #   stylesheet navigation-refresh.css?v=f38c6288
    #
    # The browser fetched both bodies and the "preload" warmed nothing. Derive
    # each stylesheet preload from the real linked/imported URL, by bare path,
    # so a cache-busting sweep moves the pair together. Only as=style preloads
    # are eligible; image/font/script hints remain untouched.
    desired_by_path: dict[str, str] = {}
    for lm in _LINK_TAG_RE.finditer(text):
        tag = lm.group(0)
        rel_m, href_m = _REL_ATTR_RE.search(tag), _HREF_ATTR_RE.search(tag)
        if not rel_m or not href_m:
            continue
        rels = rel_m.group(1).lower().split()
        href = href_m.group(1)
        if "stylesheet" not in rels or not _is_local_asset(href):
            continue
        desired_by_path[href.split("?", 1)[0].split("#", 1)[0]] = href
        for imp in imports_for(href):
            resolved = _resolve_rel(href, imp)
            desired_by_path[resolved.split("?", 1)[0].split("#", 1)[0]] = resolved

    def _refresh_preload(lm: "re.Match[str]") -> str:
        tag = lm.group(0)
        rel_m = _REL_ATTR_RE.search(tag)
        as_m = _AS_ATTR_RE.search(tag)
        href_m = _HREF_ATTR_RE.search(tag)
        if (
            not rel_m
            or "preload" not in rel_m.group(1).lower().split()
            or not as_m
            or as_m.group(1).lower() != "style"
            or not href_m
        ):
            return tag
        href = href_m.group(1)
        desired = desired_by_path.get(href.split("?", 1)[0].split("#", 1)[0])
        if not desired or desired == href:
            return tag
        return tag[:href_m.start(1)] + desired + tag[href_m.end(1):]

    text = _LINK_TAG_RE.sub(_refresh_preload, text)

    m = _HEAD_RE.search(text)
    if not m:
        return text
    head_close = text.lower().find("</head>", m.end())
    if head_close == -1:
        return text

    svg_spans = _svg_spans(text)
    preloaded: set[str] = set()   # URLs already hinted, anywhere on the page
    head_sheets: set[str] = set()  # URLs the head already links (discovery is early)
    late: list[tuple[str, Optional[str]]] = []  # (url, media) needing a hint
    last_head_sheet_end = m.end()

    for lm in _LINK_TAG_RE.finditer(text):
        tag = lm.group(0)
        rel_m, href_m = _REL_ATTR_RE.search(tag), _HREF_ATTR_RE.search(tag)
        if not rel_m or not href_m:
            continue
        rels = rel_m.group(1).lower().split()
        href = href_m.group(1)
        if "preload" in rels:
            preloaded.add(href)
            continue
        if "stylesheet" not in rels or not _is_local_asset(href):
            continue
        in_head = lm.start() < head_close
        if in_head:
            head_sheets.add(href)
            last_head_sheet_end = max(last_head_sheet_end, lm.end())
        elif not any(a <= lm.start() < b for a, b in svg_spans):
            media_m = _MEDIA_ATTR_RE.search(tag)
            late.append((href, media_m.group(1) if media_m else None))
        # @imports are late no matter WHERE their parent is linked
        for imp in imports_for(href):
            late.append((_resolve_rel(href, imp), None))

    hints, seen = [], set(preloaded)
    for url, media in late:
        if url in seen or url in head_sheets:
            continue
        seen.add(url)
        media_attr = f' media="{media}"' if media else ""
        hints.append(f'<link rel="preload" as="style"{media_attr} href="{url}">')
    if not hints:
        return text
    return text[:last_head_sheet_end] + "\n" + "\n".join(hints) + text[last_head_sheet_end:]


def _resolve_rel(base_href: str, url: str) -> str:
    """Resolve `url` against the DIRECTORY of `base_href` (both page-relative), so
    an @import inside site/theme.css referenced from site/x/y.html as
    "../theme.css" yields "../product-nav-icons.css" — the exact string the browser
    will request, which is what makes the preload dedupe."""
    if url.startswith("/"):
        return url
    base_dir = base_href.split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)
    if len(base_dir) == 1:
        return url
    parts = [p for p in (base_dir[0] + "/" + url).split("/") if p != "."]
    out: list[str] = []
    for p in parts:
        if p == ".." and out and out[-1] != "..":
            out.pop()
        else:
            out.append(p)
    return "/".join(out)


def externalize_css_text(
    text: str, make_href: Callable[[str, int, Optional[str]], Optional[str]]
) -> str:
    """Replace each ``<style>`` block with a ``<link>`` to an external stylesheet.

    ``make_href(css, index, media)`` writes the stylesheet (or dedupes to an
    existing one) and returns the ``<link href>`` — or ``None`` to leave that
    block inline (below a size threshold, or one we choose not to touch).
    ``index`` is the block's 1-based position on the page; ``media`` is its
    ``media`` attribute if any (carried onto the link). The CSS crosses over
    byte-for-byte, so rendering is unchanged. Idempotent: a page already free of
    ``<style>`` blocks is returned untouched. Blocks inside inline ``<svg>``
    elements are NEVER lifted (see ``_svg_spans``) — a ``<link>`` there is inert.
    """
    counter = [0]
    svg_spans = _svg_spans(text)

    def _repl(m: "re.Match[str]") -> str:
        attrs, css = m.group(1), m.group(2)
        counter[0] += 1
        if any(a <= m.start() < b for a, b in svg_spans):
            return m.group(0)  # SVG-internal <style>: must stay inline
        media_m = _MEDIA_ATTR_RE.search(attrs)
        media = media_m.group(1) if media_m else None
        href = make_href(css, counter[0], media)
        if not href:
            return m.group(0)  # left inline
        media_attr = f' media="{media}"' if media else ""
        return f'<link rel="stylesheet"{media_attr} href="{href}">'

    return _STYLE_BLOCK_RE.sub(_repl, text)


# The shim is INLINED, not linked. It has to be a blocking script at the top of
# <head> (it patches window.fetch before any page data fetch), and as an external
# ref that made it the one resource that stalls the HTML parser for a full
# round-trip on every cold visit — ~460ms at the measured origin TTFB, on every
# page of the site, to deliver under 1KB. Unversioned, it also carries
# `max-age=300, must-revalidate` (Caddyfile @public_static), so returning visitors
# pay a revalidation RTT in that same blocking position. Inlined it costs zero
# requests and keeps the ordering guarantee exactly.
#
# Site CSP is `base-uri 'self'; object-src 'none'; frame-ancestors 'none'` — no
# script-src directive, so inline executes. A future nonce migration (noted in the
# Caddyfile) must give this tag a nonce or it silently stops rerouting to R2.
_DBASE_LEAD_COMMENT_RE = re.compile(r"\A\s*/\*.*?\*/\s*", re.DOTALL)
_DBASE_EXTERNAL_TAG_RE = re.compile(
    rf'<script\s+{DBASE_MARKER}\s+src="[^"]*data_base\.js(?:\?[^"]*)?"\s*>\s*</script>',
    re.IGNORECASE,
)
_DBASE_INLINE_TAG_RE = re.compile(
    rf'<script\s+{DBASE_MARKER}\s*>.*?</script>',
    re.IGNORECASE | re.DOTALL,
)
_shim_body_cache: dict[Path, str] = {}


def _shim_body() -> Optional[str]:
    """The shim source to inline, minus its leading block comment (the rationale
    lives in templates/data_base.js and in this module). Stripping only a LEADING
    /*…*/ is safe without a JS parser — nothing can precede it, so it can never be
    inside a string literal. None when unreadable, which makes _tag() fall back to
    the external ref rather than dropping the shim.

    Cached PER SOURCE PATH, not per process. A single global slot also cached the
    *failure*: builder tests patch config.ROOT to a fixture tree with no
    templates/, so the first write_page under such a patch pinned every later page
    write in that process to the external-ref fallback — a red that lands on
    whichever suite happens to run second, far from the test that caused it."""
    src = config.ROOT / "templates" / "data_base.js"
    body = _shim_body_cache.get(src)
    if body is None:
        try:
            raw = src.read_text(encoding="utf-8")
            stripped = _DBASE_LEAD_COMMENT_RE.sub("", raw).strip()
            # A literal </script> in the body would close the tag early. The shim has
            # none today; bail to the external ref rather than emit a broken page.
            body = "" if (not stripped or "</script" in stripped.lower()) else stripped
        except Exception as e:  # noqa: BLE001
            log.warning("data_base.js shim read failed (%s) — falling back to external ref", e)
            body = ""
        _shim_body_cache[src] = body
    return body or None


def _tag(prefix: str) -> str:
    body = _shim_body()
    if body is None:
        return f'<script {DBASE_MARKER} src="{prefix}data_base.js"></script>'
    return f"<script {DBASE_MARKER}>{body}</script>"


def inject_text(text: str, prefix: str = "") -> str:
    """Return `text` with the shim <script> inserted at the TOP of <head> (so it
    runs before any body fetch). Idempotent — an up-to-date inline shim is
    unchanged; a stale inline body is refreshed in place; and a page still
    carrying the OLD external <script src> tag is upgraded in place (same
    position, so ordering is preserved)."""
    tag = _tag(prefix)
    if DBASE_MARKER in text:
        # Upgrade path: pages rendered before inlining (and any page the CI sweep
        # re-visits) carry the external ref. Swap it for the inline body in place.
        # Then refresh an older inline body when templates/data_base.js changes.
        # Without the inline refresh, the safety sweep treated the marker as proof
        # of currency and left thousands of committed pages pinned to a stale
        # fetch wrapper indefinitely.
        if "data_base.js" in text and _shim_body() is not None and _DBASE_EXTERNAL_TAG_RE.search(text):
            return _DBASE_EXTERNAL_TAG_RE.sub(lambda _m: tag, text, count=1)
        inline = _DBASE_INLINE_TAG_RE.search(text)
        if inline and inline.group(0) != tag:
            return text[:inline.start()] + tag + text[inline.end():]
        return text
    m = _HEAD_RE.search(text)
    if m:
        i = m.end()
        return text[:i] + "\n" + tag + text[i:]
    # no <head> — fall back to before </body>, else prepend
    low = text.lower()
    j = low.find("</body>")
    return (text[:j] + tag + "\n" + text[j:]) if j != -1 else tag + "\n" + text


def _site_root() -> Path:
    try:
        return (config.ROOT / config.load()["storage"]["site_dir"]).resolve()
    except Exception:  # noqa: BLE001
        return (config.ROOT / "site").resolve()


def dbase_prefix(path: Path | str) -> str:
    """Depth-aware shim prefix for a page path: "" at site root, "../" per
    directory below it (site/basket/x.html -> "../"). Never raises."""
    p = Path(path)
    try:
        p = p.resolve()
    except Exception:  # noqa: BLE001
        return ""
    try:
        return "../" * (len(p.relative_to(_site_root()).parts) - 1)
    except ValueError:
        # not under the configured site dir (tests, ad-hoc out dirs) — locate the
        # last "site" path component instead; unknown layout -> root-level prefix
        parts = p.parts
        for i in range(len(parts) - 1, -1, -1):
            if parts[i] == "site":
                return "../" * max(0, len(parts) - i - 2)
        return ""


_shim_checked = False


def _ensure_shim_asset() -> None:
    """Once per process, make sure site/data_base.js exists so the injected tag
    never 404s. Copy only when MISSING — refresh copies stay in the CI inject
    step, so a standalone builder run can't dirty a tracked file its sentinel
    doesn't `git add` (see #1026). Never raises."""
    global _shim_checked
    if _shim_checked:
        return
    _shim_checked = True
    try:
        site = _site_root()
        src = config.ROOT / "templates" / "data_base.js"
        dst = site / "data_base.js"
        if src.exists() and site.is_dir() and not dst.exists():
            shutil.copyfile(src, dst)
    except Exception as e:  # noqa: BLE001
        log.warning("data_base.js ensure failed: %s", e)


def write_page(path: Path | str, html: str, *, encoding: str | None = None) -> Path:
    """Write a site HTML page with the data-base shim injected (depth-aware,
    idempotent). ALL builders must write site/**/*.html through this — a raw
    write_text drops the shim whenever the builder runs standalone."""
    p = Path(path)
    p.write_text(inject_text(html, dbase_prefix(p)), encoding=encoding)
    _ensure_shim_asset()
    return p
