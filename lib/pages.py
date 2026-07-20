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
from pathlib import Path
from typing import Callable, Optional

from lib import config

log = logging.getLogger("pages")

DBASE_MARKER = "data-dbase"
_HEAD_RE = re.compile(r"<head[^>]*>", re.IGNORECASE)

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

    Idempotent: a ref that already carries a query (manual ``?v=N`` or a prior
    run) is left untouched, and ``defer``/``async`` scripts are not re-marked.
    ``hash_for`` returns ``None`` when the asset can't be hashed (missing on
    disk) — the ref is then left unversioned but a script still gets ``defer``.
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
        low = url.lower()
        if "?" in url or "#" in url or not (low.endswith(".js") or low.endswith(".css")):
            return m.group(0)                  # already-queried or not a hashed asset
        new_attrs = attrs
        h = hash_for(url)
        if h:
            new_url = f'{am.group(1)}="{url}?v={h}"'
            new_attrs = new_attrs[: am.start()] + new_url + new_attrs[am.end():]
        if kind == "script" and not _HAS_DEFER_ASYNC_RE.search(new_attrs) and not _MODULE_RE.search(new_attrs):
            new_attrs = new_attrs.rstrip() + " defer"
        return f"<{m.group(1)}{new_attrs}>"

    return _OPEN_TAG_RE.sub(_rewrite, text)


def _tag(prefix: str) -> str:
    return f'<script {DBASE_MARKER} src="{prefix}data_base.js"></script>'


def inject_text(text: str, prefix: str = "") -> str:
    """Return `text` with the shim <script> inserted at the TOP of <head> (so it
    runs before any body fetch). Idempotent — text already carrying the marker is
    unchanged."""
    if DBASE_MARKER in text:
        return text
    tag = _tag(prefix)
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
