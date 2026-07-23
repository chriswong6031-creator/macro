"""Content inventory, offline broken-link check, and a live-site uptime probe."""
from __future__ import annotations

import re
import time

from . import config_store
from .paths import ROOT, SITE

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None  # type: ignore

# strip script/style first so JS string literals don't masquerade as links
_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HREF_RE = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def inventory() -> dict:
    """Every deployed *.html page with size + mtime age (newest-first)."""
    if not SITE.is_dir():
        return {"total_pages": 0, "total_kb": 0, "pages": []}
    pages = []
    now = time.time()
    total = 0
    for p in sorted(SITE.rglob("*.html")):
        try:
            sz = p.stat().st_size
            age = (now - p.stat().st_mtime) / 3600.0
        except OSError:
            continue
        total += sz
        pages.append({
            "name": str(p.relative_to(SITE)),
            "kb": round(sz / 1024, 1),
            "age_hours": round(age, 1),
        })
    pages.sort(key=lambda x: x["age_hours"])
    return {
        "total_pages": len(pages),
        "total_kb": round(total / 1024, 1),
        "total_mb": round(total / 1024 / 1024, 2),
        "pages": pages,
    }


# Repo-root templates/ — a page whose .j2 (or plain .html) template lives here is
# built by CI at render time, so it's "absent locally, present on the deployed site"
# rather than a genuinely broken link.
_TEMPLATES = ROOT / "templates"


def _ci_built(target) -> bool:
    """True if the missing target maps to a CI-built template (templates/<stem>.html.j2
    or templates/<stem>.html) — i.e. absent locally but rendered on the live site."""
    stem = target.name[:-len(".html")] if target.name.lower().endswith(".html") else target.name
    return ((_TEMPLATES / f"{stem}.html.j2").exists()
            or (_TEMPLATES / f"{stem}.html").exists())


# Whole local tree is ~3k pages; these are offline file reads off the hot path, so the
# default ceiling covers everything (only a runaway tree would truncate). `truncated`
# lets the UI say "scanned N of M" honestly when the cap ever does bite.

# A full scan reads+parses ~3k pages (~17s) and blocks the single-threaded server, but the
# result only changes when the site/ tree does. Cache it, keyed on a cheap tree signature
# (html-file count + newest mtime) — statting files is far cheaper than reading every one,
# so a repeat panel load returns instantly instead of re-running the crawl.
_link_cache: dict = {}  # (max_pages, count, max_mtime) -> result dict


def _tree_sig(max_pages: int):
    """Cheap cache key: (max_pages, html-file count, newest mtime) over site/. Stat-only —
    no file reads — so any add/remove/edit of a page flips the key and forces a rescan."""
    count = 0
    newest = 0.0
    for p in SITE.rglob("*.html"):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        count += 1
        if m > newest:
            newest = m
    return (max_pages, count, newest)


def link_check(max_pages: int = 10000) -> dict:
    """Cached wrapper around the offline nav-integrity scan (see `_link_check`).

    The scan reads+parses the whole local tree (~17s); here we return a memoized result
    whenever the site/ tree signature (page count + newest mtime) is unchanged, so repeat
    panel loads are near-instant instead of re-running the crawl on the single-threaded
    server. Returns the identical dict `_link_check` produces.
    """
    if not SITE.is_dir():
        return _link_check(max_pages)
    key = _tree_sig(max_pages)
    cached = _link_cache.get(key)
    if cached is not None:  # tree unchanged -> reuse
        return cached
    result = _link_check(max_pages)
    _link_cache.clear()  # only the current tree state is ever relevant; bound the dict
    _link_cache[key] = result
    return result


def _link_check(max_pages: int = 10000) -> dict:
    """Offline page-to-page nav-integrity check: internal links to a `.html` page that
    doesn't exist in the local site/ tree (the '404 nav link' class). Scans real markup
    only (script/style stripped); external / anchor / data links and non-HTML asset
    references (JSON/CSS/JS/images, many of which are runtime-generated) are skipped.

    Targets whose CI template exists (templates/<stem>.html.j2|.html) are absent locally
    but rendered on the deployed site, so they're split into `ci_built` (a count + sample)
    rather than counted as broken.

    NOTE: reflects THIS checkout's site/ tree — non-templated pages absent locally will
    show as broken here but may exist on the deployed site. Use the uptime probe for live.
    """
    if not SITE.is_dir():
        return {"total_pages": 0, "checked_pages": 0, "truncated": False,
                "broken": [], "count": 0, "ci_built": [], "ci_built_count": 0}
    all_pages = sorted(SITE.rglob("*.html"))
    total = len(all_pages)
    truncated = total > max_pages
    broken = []
    ci_built = []
    checked = 0
    for p in all_pages[:max_pages]:
        try:
            html = _SCRIPT_RE.sub("", p.read_text(errors="ignore"))
        except Exception:  # noqa: BLE001
            continue
        checked += 1
        seen = set()
        for raw in _HREF_RE.findall(html):
            link = raw.split("#")[0].split("?")[0].strip()
            if (not link or link in seen
                    or link.startswith(("http://", "https://", "//", "mailto:",
                                        "tel:", "data:", "javascript:"))):
                continue
            seen.add(link)
            if not link.lower().endswith(".html"):
                continue                      # only page-to-page nav integrity
            target = (p.parent / link).resolve()
            if target.exists():
                continue
            row = {"page": str(p.relative_to(SITE)), "link": link}
            (ci_built if _ci_built(target) else broken).append(row)
    return {
        "total_pages": total,
        "checked_pages": checked,
        "truncated": truncated,
        "broken": broken[:300],
        "count": len(broken),
        "ci_built": ci_built[:300],
        "ci_built_count": len(ci_built),
    }


def uptime() -> dict:
    """Probe the live site_url (config notify.site_url)."""
    url = config_store.get_value("notify.site_url") or ""
    if not url:
        return {"ok": False, "url": None, "error": "notify.site_url not set in config.yml"}
    if requests is None:
        return {"ok": False, "url": url, "error": "requests not installed"}
    target = url.rstrip("/") + "/index.html"
    t0 = time.time()
    try:
        r = requests.get(target, timeout=12, headers={"User-Agent": "macro-admin-uptime"})
        return {
            "ok": r.status_code == 200,
            "url": target,
            "status": r.status_code,
            "ms": round((time.time() - t0) * 1000),
            "bytes": len(r.content),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "url": target, "error": str(e),
                "ms": round((time.time() - t0) * 1000)}
