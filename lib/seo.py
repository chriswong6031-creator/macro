"""lib.seo — SEO foundation for the Macro Dashboard static site.

Provides:
  SITE_BASE          — canonical www host (single source of truth)
  BRAND_NAME         — public product/entity name
  BRAND_RESEARCH_NAME — organization name used for editorial attribution
  page_url(path)     — construct a full canonical URL
  discover_core_pages(site_dir) — discover unauthenticated public site/*.html pages
  discover_free_pages(site_dir) — discover free-estate sub-family pages
                                  (site/products/, site/blog/, site/learn/*/,
                                  site/tools/, etc.)
  build_core_sitemap(existing_xml, site_dir) — regenerate the public sitemap
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SITE_BASE = "https://www.mastermind-x.com/"
BRAND_NAME = "MastermindX"
BRAND_RESEARCH_NAME = "MastermindX Research"
REPO_ROOT = Path(__file__).resolve().parents[1]
ACCESS_POLICY = REPO_ROOT / "config" / "site_access.yml"

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


@lru_cache(maxsize=1)
def _public_boundary() -> tuple[frozenset[str], tuple[str, ...]]:
    """Return the unauthenticated serving boundary from its source of truth.

    Sitemap eligibility and edge access must never be maintained as separate
    lists. ``config/site_access.yml`` is already CI-checked against Caddy, so
    deriving discovery from it prevents a newly gated page from remaining in
    the sitemap after the access policy changes.
    """
    raw = yaml.safe_load(ACCESS_POLICY.read_text(encoding="utf-8"))
    public = raw.get("public") if isinstance(raw, dict) else None
    if not isinstance(public, dict):
        raise ValueError("site access policy is missing public boundary")
    exact = public.get("exact")
    prefixes = public.get("prefixes")
    if not isinstance(exact, list) or not isinstance(prefixes, list):
        raise ValueError("site access public boundary is malformed")
    return (
        frozenset(str(path) for path in exact),
        tuple(str(prefix) for prefix in prefixes),
    )


def is_public_path(path: str) -> bool:
    """True only when ``path`` is reachable without registration."""
    clean = urlsplit(path).path
    exact, prefixes = _public_boundary()
    return clean in exact or any(clean.startswith(prefix) for prefix in prefixes)


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
    # Utility page reached only from an email link, and only with a signed token
    # (SEE W4). Public so the link works without an account, but indexing it would put
    # a tokenless "unsubscribe" result in front of people who never asked for one, and
    # it has no content a searcher is looking for.
    "unsubscribe",
    # Demo/planning
    "coming-soon",     # placeholder page
    # The serving policy is the final eligibility gate. A page omitted here
    # cannot enter the sitemap unless config/site_access.yml also makes it
    # reachable without registration.
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
    # OEU M-CMD — the canonical options workspace. Like "movers" above, this
    # entry is DORMANT until options.html enters config/site_access.yml's public
    # boundary: discover_core_pages() only emits pages that is_public_path()
    # accepts, so a gated page is correctly kept out of the sitemap. Pinning the
    # priority here means the chartered 0.6 lands the moment the boundary moves,
    # instead of silently riding _DEFAULT.
    "options":          ("daily",   0.6),
    # The entity page (SEO_SUPERCHARGE_MASTERPLAN §0.10). Discovery already picks
    # it up the moment the boundary opens; this pins the two honest facts the
    # default gets wrong. Cadence is MONTHLY — it is prose about who we are, not a
    # desk that reprints nightly, and claiming "daily" on a page that does not
    # change is the kind of small lie a crawler learns to discount. Priority 0.8
    # because for a brand query it is the second-most-useful page on the site.
    "about":            ("monthly", 0.8),
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

def discover_free_pages(site_dir: Path) -> list[tuple[str, str, str, str, float]]:
    """Discover free-estate sub-family HTML pages (blog/, learn/*/, tools/, etc.).

    Returns a sorted list of (rel_path, loc_url, changefreq, filename, priority).

    Families and rules (CONTRACT §9 / MKT-SEO-01..04):
      - site/products/index.html      -> hub (weekly, 0.7)
      - site/products/<slug>.html     -> leaf (monthly, 0.6)
      - site/blog/index.html          -> hub (weekly, 0.7)
      - site/blog/<slug>.html         -> leaf (monthly, 0.6)
      - site/learn/index.html         -> hub (weekly, 0.7)
      - site/learn/<track>/*.html     -> leaf (monthly, 0.6)
      - site/tools/index.html         -> hub (weekly, 0.7)
      - site/tools/calculators/*.html -> leaf (monthly, 0.6)
      - site/tools/spreadsheets/*.html-> leaf (monthly, 0.6)

    feed.xml and non-.html files are never included.
    Hub index.html filenames are preserved in the URL (e.g. /blog/index.html).
    """
    results: list[tuple[str, str, str, str, float]] = []

    # ---- products ----
    products_dir = site_dir / "products"
    if products_dir.is_dir():
        for p in sorted(products_dir.glob("*.html")):
            if p.name == "index.html":
                freq, pri = "weekly", 0.7
            else:
                freq, pri = "monthly", 0.6
            rel = f"products/{p.name}"
            if is_public_path("/" + rel):
                results.append((rel, page_url(rel), freq, p.name, pri))

    # ---- blog ----
    blog_dir = site_dir / "blog"
    if blog_dir.is_dir():
        for p in sorted(blog_dir.glob("*.html")):
            if p.name == "index.html":
                freq, pri = "weekly", 0.7
            else:
                freq, pri = "monthly", 0.6
            rel = f"blog/{p.name}"
            if is_public_path("/" + rel):
                results.append((rel, page_url(rel), freq, p.name, pri))

    # ---- learn ----
    learn_dir = site_dir / "learn"
    if learn_dir.is_dir():
        # hub
        learn_idx = learn_dir / "index.html"
        if learn_idx.exists():
            rel = "learn/index.html"
            if is_public_path("/" + rel):
                results.append((rel, page_url(rel), "weekly", "index.html", 0.7))
        # track subdirectories (one level deep only)
        for track_dir in sorted(learn_dir.iterdir()):
            if not track_dir.is_dir():
                continue
            for p in sorted(track_dir.glob("*.html")):
                rel = f"learn/{track_dir.name}/{p.name}"
                if is_public_path("/" + rel):
                    results.append((rel, page_url(rel), "monthly", p.name, 0.6))

    # ---- tools ----
    tools_dir = site_dir / "tools"
    if tools_dir.is_dir():
        # hub
        tools_idx = tools_dir / "index.html"
        if tools_idx.exists():
            rel = "tools/index.html"
            if is_public_path("/" + rel):
                results.append((rel, page_url(rel), "weekly", "index.html", 0.7))
        # calculators/
        calc_dir = tools_dir / "calculators"
        if calc_dir.is_dir():
            for p in sorted(calc_dir.glob("*.html")):
                rel = f"tools/calculators/{p.name}"
                if is_public_path("/" + rel):
                    results.append((rel, page_url(rel), "monthly", p.name, 0.6))
        # spreadsheets/
        ss_dir = tools_dir / "spreadsheets"
        if ss_dir.is_dir():
            for p in sorted(ss_dir.glob("*.html")):
                rel = f"tools/spreadsheets/{p.name}"
                if is_public_path("/" + rel):
                    results.append((rel, page_url(rel), "monthly", p.name, 0.6))

    return results


def discover_core_pages(site_dir: Path) -> list[tuple[str, str, str]]:
    """Return a sorted list of (name_without_ext, loc_url, filename) for public pages.

    Excludes:
      - Anything under site_dir/stocks/ (those are managed by build_ticker_pages)
      - Any root page outside the unauthenticated public serving boundary
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
            if not (is_public_path("/") or is_public_path("/index.html")):
                continue
            # Homepage maps to bare root
            pages.append(("", page_url(""), p.name))
        else:
            if not is_public_path("/" + p.name):
                continue
            pages.append((stem, page_url(p.name), p.name))

    # Sort: homepage ("") first, then alphabetical
    pages.sort(key=lambda t: ("" if t[0] == "" else t[0]))
    return pages


# ─────────────────────────────────────────────────────────────────────────────
# Core sitemap builder
# ─────────────────────────────────────────────────────────────────────────────

_APEX_RE = re.compile(r"https://mastermind-x\.com/", re.IGNORECASE)
_LOC_RE = re.compile(r"<loc>([^<]+)</loc>", re.IGNORECASE)

# These public page families own their own sitemap merge routines. Preserve
# their honest, data-derived lastmod values while replacing the core/free block.
_PRESERVED_PUBLIC_PAGE_PREFIXES = ("/stocks/", "/research/")


def _normalize_host(text: str) -> str:
    """Replace https://mastermind-x.com/ with https://www.mastermind-x.com/ everywhere."""
    return _APEX_RE.sub(SITE_BASE, text)


def build_core_sitemap(existing_xml: str, site_dir: Path) -> str:
    """Regenerate a sitemap containing only unauthenticated public pages.

    Strategy:
      1. Preserve public /stocks/ and /research/ entries, including their
         source-derived lastmod values, and normalize their canonical host.
      2. Discover all core pages via discover_core_pages().
      3. Emit the public core/free entries plus preserved owned-family entries.

    Format-compatible with build_ticker_pages.build_sitemap() which:
      - Strips /stocks/ lines from the existing XML
      - Appends new /stocks/ entries
      - Re-emits </urlset>
    So calling build_core_sitemap() first and then build_ticker_pages.build_sitemap()
    on the result preserves core entries and replaces stocks entries correctly.
    Calling build_ticker_pages.build_sitemap() first and then build_core_sitemap()
    also works: core discovery replaces core entries, stocks are preserved verbatim.
    """
    # Preserve separately-managed public page families only. Any gated root URL
    # in the old sitemap is intentionally dropped.
    preserved_lines: list[str] = []
    for line in existing_xml.splitlines():
        stripped = line.strip()
        if not stripped.startswith("<url>"):
            continue
        match = _LOC_RE.search(stripped)
        if not match:
            continue
        path = urlsplit(match.group(1)).path
        if (
            any(path.startswith(prefix) for prefix in _PRESERVED_PUBLIC_PAGE_PREFIXES)
            and is_public_path(path)
        ):
            preserved_lines.append(_normalize_host(line))

    # Discover core pages and build entries.
    core_entries: list[str] = []
    for name, url, _filename in discover_core_pages(site_dir):
        freq, pri = _freq_priority(name)
        pri_str = f"{pri:.1f}" if pri == int(pri) else str(pri)
        # Omit lastmod when there is no content-derived timestamp. A truthful
        # omission is preferable to stamping every URL with the build date.
        entry = f"  <url><loc>{url}</loc><changefreq>{freq}</changefreq><priority>{pri_str}</priority></url>"
        core_entries.append(entry)

    # Discover public sub-family pages (products/, blog/, learn/, tools/).
    free_entries: list[str] = []
    for _rel, url, freq, _fname, pri in discover_free_pages(site_dir):
        pri_str = f"{pri:.1f}" if pri == int(pri) else str(pri)
        entry = f"  <url><loc>{url}</loc><changefreq>{freq}</changefreq><priority>{pri_str}</priority></url>"
        free_entries.append(entry)

    # Assemble XML.
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    parts.extend(core_entries)
    parts.extend(free_entries)
    parts.extend(preserved_lines)
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"
