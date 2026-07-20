"""lib.seo — SEO foundation for the Macro Dashboard static site.

Provides:
  SITE_BASE          — canonical www host (single source of truth)
  page_url(path)     — construct a full canonical URL
  discover_core_pages(site_dir) — discover public site/*.html pages
  build_core_sitemap(existing_xml, site_dir) — regenerate non-/stocks/ sitemap entries
"""
from __future__ import annotations

import re
from pathlib import Path
from datetime import date

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SITE_BASE = "https://www.mastermind-x.com/"

# Apex host (no www) — used only for normalisation; never emit this in new output.
_APEX_HOST = "https://mastermind-x.com/"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def page_url(path: str) -> str:
    """Return the full canonical URL for a site path.

    Examples:
      page_url("")            -> "https://www.mastermind-x.com/"
      page_url("macro.html") -> "https://www.mastermind-x.com/macro.html"
    """
    base = SITE_BASE.rstrip("/")
    if not path:
        return base + "/"
    path = path.lstrip("/")
    return base + "/" + path


# ─────────────────────────────────────────────────────────────────────────────
# Exclusion set — pages NOT included in the core sitemap
# ─────────────────────────────────────────────────────────────────────────────

# Names whose filename starts with one of these prefixes are excluded.
_EXCLUDE_PREFIXES: frozenset[str] = frozenset({
    "_mockup",         # design mockups / prototypes
})

# Exact filenames excluded (without .html extension, for readability).
# Additions: internal-only, test/demo, or noindex pages.
_EXCLUDE_NAMES: frozenset[str] = frozenset({
    # Hard-coded by brief
    "calibration",
    "chat",
    # Internal / operational
    "status",          # VPS status page (noindex in HTML)
    "mastermind",      # AI Brain UI (operator-internal)
    # Lab / staging variants
    "us_stocks_v2",    # staging variant of us_stocks (not the canonical)
    "us_stocks_lab",   # internal lab variant
    "china_stocks_lab",
    "hk_stocks_lab",
    "tech_lab",        # internal technical lab
    "validation_timeline",  # internal validation tracking
    "qa_bottom_sensors",    # internal QA page
    # Per-URL dynamic lookup tools — noncanonical query variants (D12 §10.2)
    "stock",           # generic stock analyzer (lookup tool, no canonical content)
    "intl_stock",      # international stock lookup
    "canada_stock",    # Canadian stock lookup
    # Auth-empty until sign-in — fails the index-worthiness test (D12 §3.3);
    # PR B still ships its social meta; Director may revisit.
    "watchlist",
    # Demo/planning
    "coming-soon",     # placeholder page
    # D12A adjudication 2026-07-20: masterminds, advanced, signal_lab,
    # whitehouse, vector_allocation, measurement are PUBLIC content pages
    # (census + ratified copy table) — deliberately NOT excluded.
})


def _should_exclude(name: str) -> bool:
    """Return True if this HTML filename (without .html) should be excluded."""
    for prefix in _EXCLUDE_PREFIXES:
        if name.startswith(prefix):
            return True
    return name in _EXCLUDE_NAMES


# ─────────────────────────────────────────────────────────────────────────────
# Changefreq / priority rules
# ─────────────────────────────────────────────────────────────────────────────

# Explicit overrides by page name (without .html).  "" = homepage (bare root URL).
_EXPLICIT: dict[str, tuple[str, float]] = {
    "":                 ("daily",   1.0),
    "macro":            ("daily",   0.9),
    "us_stocks":        ("daily",   0.9),
    "china":            ("daily",   0.8),
    "hk":               ("daily",   0.8),
    "markets":          ("weekly",  0.8),
    "cycle":            ("weekly",  0.8),
    "canada":           ("daily",   0.7),
    "bonds":            ("daily",   0.7),
    "forex":            ("daily",   0.7),
    "commodities":      ("daily",   0.7),
    "baskets":          ("daily",   0.7),
    "factors":          ("daily",   0.7),
    "congress_trades":  ("weekly",  0.7),
    "learn":            ("weekly",  0.7),
    "movers":           ("daily",   0.7),
    "methodology":      ("monthly", 0.6),
    "reports":          ("weekly",  0.6),
}

# Pattern-based rules (checked in order; first match wins).
_PATTERNS: list[tuple[str, tuple[str, float]]] = [
    ("fund_",     ("weekly",  0.5)),
    ("strategy_", ("weekly",  0.5)),
    ("report_",   ("monthly", 0.6)),
]

# Default for pages not matched above.
_DEFAULT: tuple[str, float] = ("daily", 0.6)


def _freq_priority(name: str) -> tuple[str, float]:
    """Return (changefreq, priority) for a page name (without .html)."""
    if name in _EXPLICIT:
        return _EXPLICIT[name]
    for prefix, val in _PATTERNS:
        if name.startswith(prefix):
            return val
    return _DEFAULT


# ─────────────────────────────────────────────────────────────────────────────
# Core page discovery
# ─────────────────────────────────────────────────────────────────────────────

def discover_core_pages(site_dir: Path) -> list[tuple[str, str, str]]:
    """Return a sorted list of (name_without_ext, loc_url, filename) for public pages.

    Excludes:
      - Anything under site_dir/stocks/ (those are managed by build_ticker_pages)
      - Files matching _EXCLUDE_PREFIXES or _EXCLUDE_NAMES
      - index.html maps to the bare root URL "" (not "index.html")

    Returns list of (name, url, filename) sorted by name, with "" (homepage) first.
    """
    pages: list[tuple[str, str, str]] = []
    for p in sorted(site_dir.glob("*.html")):
        stem = p.stem  # filename without .html
        if _should_exclude(stem):
            continue
        if stem == "index":
            # Homepage maps to bare root
            pages.append(("", page_url(""), p.name))
        else:
            pages.append((stem, page_url(p.name), p.name))

    # Sort: homepage ("") first, then alphabetical
    pages.sort(key=lambda t: ("" if t[0] == "" else t[0]))
    return pages


# ─────────────────────────────────────────────────────────────────────────────
# Core sitemap builder
# ─────────────────────────────────────────────────────────────────────────────

_APEX_RE = re.compile(r"https://mastermind-x\.com/", re.IGNORECASE)


def _normalize_host(text: str) -> str:
    """Replace https://mastermind-x.com/ with https://www.mastermind-x.com/ everywhere."""
    return _APEX_RE.sub(SITE_BASE, text)


def build_core_sitemap(existing_xml: str, site_dir: Path) -> str:
    """Regenerate the core (non-/stocks/) sitemap entries and preserve /stocks/ entries.

    Strategy:
      1. Extract /stocks/ <url> entries from existing_xml (preserving lastmod).
         Normalize any apex-host occurrences in those preserved lines.
      2. Discover all core pages via discover_core_pages().
      3. Emit: XML header + core entries + preserved stocks entries + </urlset>

    Format-compatible with build_ticker_pages.build_sitemap() which:
      - Strips /stocks/ lines from the existing XML
      - Appends new /stocks/ entries
      - Re-emits </urlset>
    So calling build_core_sitemap() first and then build_ticker_pages.build_sitemap()
    on the result preserves core entries and replaces stocks entries correctly.
    Calling build_ticker_pages.build_sitemap() first and then build_core_sitemap()
    also works: core discovery replaces core entries, stocks are preserved verbatim.
    """
    # Extract /stocks/ <url> lines from existing XML, normalizing apex host.
    stocks_lines: list[str] = []
    for line in existing_xml.splitlines():
        stripped = line.strip()
        if stripped.startswith("<url>") and "/stocks/" in stripped:
            stocks_lines.append(_normalize_host(line))

    # Discover core pages and build entries.
    core_entries: list[str] = []
    today = date.today().isoformat()
    for name, url, _filename in discover_core_pages(site_dir):
        freq, pri = _freq_priority(name)
        pri_str = f"{pri:.1f}" if pri == int(pri) else str(pri)
        entry = f"  <url><loc>{url}</loc><lastmod>{today}</lastmod><changefreq>{freq}</changefreq><priority>{pri_str}</priority></url>"
        core_entries.append(entry)

    # Assemble XML.
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    parts.extend(core_entries)
    parts.extend(stocks_lines)
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"
