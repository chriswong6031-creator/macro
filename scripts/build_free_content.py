"""scripts/build_free_content.py — MastermindX public acquisition builder.

Renders content/seo/{products,blog,learn,pages,tools}/*.md +
templates/seo_*.html.j2
into committed site/ output.  Deterministic: same inputs => identical bytes.

Ownership: B1 (this file) per content/seo/CONTRACT.md §2.  The HAND_AUTHORED
frozenset carves out the flagship product pages: their .md front-matter still
drives hub cards / related links / clusters, but their HTML is source, so this
builder neither writes nor drift-checks nor orphan-checks those files.

Usage:
    python3 -m scripts.build_free_content           # full build
    python3 -m scripts.build_free_content --check   # validate + render to tmp,
                                                    # compare against site/ output
                                                    # (exit 1 on drift)

A full build writes this builder's own output.  The committed pages are that
output PLUS the render lanes' post-render sweeps (externalize_css lifts the big
inline <style> into site/assets/css/<hash>.css; optimize_assets adds ?v= stamps,
defer and preload hints; inject_wh_banner adds the alert ticker in daily.yml
only — the data-base shim is injected here at write time via lib.pages.write_page,
per that module's "ALL builders must write site/**/*.html through this").  So a
plain build leaves site/ mid-pipeline: run the sweeps, or let a render lane do
it, before judging the diff.  --check replays them over its temp render so it
compares like against like (see _check_mode).
"""
from __future__ import annotations

import argparse
import email.utils
import json
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from lib.pages import HAND_AUTHORED_PAGES, write_page  # noqa: E402
from lib.seo import (  # noqa: E402
    BRAND_NAME,
    BRAND_RESEARCH_NAME,
    SITE_BASE,
    page_url,
)

_CONTENT_DIR = _REPO / "content" / "seo"
_TEMPLATES_DIR = _REPO / "templates"
_SITE_DIR = _REPO / "site"
# Live-target validation always resolves against the committed repo site/,
# regardless of where a render is being written (tests patch _SITE_DIR).
_LIVE_SITE_DIR = _REPO / "site"
_ALLOWED_EXTERNAL_CTAS: frozenset[str] = frozenset({
    "https://app.mastermind-x.com",
    "https://app.mastermind-x.com/terminal?signup=1",
})

# Flagship product pages whose HTML BYTES are hand-authored source files rather
# than generator output (operator-ordered redesign 2026-07-28) — like
# site/index.html, the committed page IS the source and nothing derives it.
# Their content/seo/products/*.md front-matter is still LOADED and consumed: the
# products/index.html hub cards, related.products resolution, cluster wiring and
# the slug->title map every other page draws from all read it.
# Only the WRITE changes — render_all skips the output file for these rels.
# --check therefore exempts them from the drift compare (nothing is rendered to
# compare) and, load-bearingly, from the D5 orphan walk: "not produced by this
# build" is the normal, correct state of a hand-authored page, not a defect.
# Defined in lib.pages so scripts/externalize_css can skip the same pages from
# ONE source of truth without importing this module (and its jinja2 dependency);
# re-exported under the local name the rest of this file and its tests use.
HAND_AUTHORED: frozenset[str] = HAND_AUTHORED_PAGES

# ---------------------------------------------------------------------------
# CONTRACT §1 URL map — all paths the builder owns
# ---------------------------------------------------------------------------

# Section §1 canonical URL paths (root-relative) — used to validate related.*
_URL_MAP: frozenset[str] = frozenset({
    "/products/index.html",
    "/products/market-terminal.html",
    "/products/mastermind-ai.html",
    "/products/market-dashboards.html",
    "/products/crypto-intelligence.html",
    "/tools/index.html",
    "/tools/calculators/position-size.html",
    "/tools/calculators/risk-reward.html",
    "/tools/calculators/trade-profit.html",
    "/tools/calculators/compounding.html",
    "/tools/calculators/cagr.html",
    "/tools/calculators/drawdown-recovery.html",
    "/tools/calculators/retirement.html",
    "/tools/calculators/roi.html",
    "/tools/calculators/dividend.html",
    "/tools/calculators/dollar-cost-averaging.html",
    "/tools/calculators/rule-of-72.html",
    "/tools/calculators/percentage-gain-loss.html",
    "/tools/calculators/savings-goal.html",
    "/tools/calculators/inflation.html",
    "/tools/calculators/net-worth.html",
    "/tools/calculators/options-profit.html",
    "/tools/calculators/stock-average.html",
    "/tools/calculators/margin.html",
    "/tools/calculators/forex-pip-value.html",
    "/tools/calculators/short-selling.html",
    "/tools/calculators/covered-call.html",
    "/tools/calculators/stop-loss-take-profit.html",
    "/tools/calculators/kelly-criterion.html",
    "/tools/calculators/sharpe-ratio.html",
    "/tools/calculators/portfolio-rebalancing.html",
    "/tools/calculators/risk-of-ruin.html",
    "/tools/spreadsheets/trading-journal.html",
    "/assets/downloads/mastermind-trading-journal.xlsx",
    "/learn/index.html",
    "/learn/technical/52-week-highs.html",
    "/learn/technical/rsi.html",
    "/learn/technical/macd.html",
    "/learn/technical/vwap-anchored-vwap.html",
    "/learn/technical/market-breadth.html",
    "/learn/risk/position-sizing.html",
    "/learn/risk/risk-reward-expectancy.html",
    "/learn/ownership/insider-filings-form-4.html",
    "/learn/options/zero-dte-regime.html",
    "/learn/options/market-makers-middleman.html",
    "/learn/options/open-interest-limits.html",
    "/learn/options/dealer-hedging-mechanics.html",
    "/learn/options/gamma-regimes.html",
    "/learn/options/charm-and-time-drift.html",
    "/learn/options/gamma-flip-levels.html",
    "/blog/index.html",
    "/blog/the-math-of-losing-streaks.html",
    "/blog/why-a-50-percent-loss-needs-a-100-percent-gain.html",
    "/blog/win-rate-is-overrated.html",
    "/blog/congress-trades-are-not-realtime-signals.html",
    "/blog/how-to-keep-a-trading-journal.html",
    "/blog/compound-growth-for-traders.html",
    "/blog/feed.xml",
    "/about-research.html",
    "/privacy.html",
    "/terms.html",
    "/disclaimer.html",
})

# valid track values (CONTRACT §3)
_VALID_TRACKS: frozenset[str] = frozenset({"technical", "risk", "ownership", "options"})

# valid family values
_VALID_FAMILIES: frozenset[str] = frozenset(
    {"article", "lesson", "page", "product"}
)

# Track ordering and display labels (CONTRACT §5 / learn hub)
_TRACK_ORDER = ["technical", "risk", "ownership", "options"]
_TRACK_LABELS = {
    "technical": "Technical Analysis",
    "risk": "Risk & Position Management",
    "ownership": "Ownership & Filings",
    "options": "Options & Dealer Positioning",
}

# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────


def _slugify(text: str) -> str:
    """Deterministic h2-id slugify: lowercase, non-alnum -> hyphen, collapse."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _rel_for_depth(depth: int) -> str:
    """Asset prefix to site root: '' at depth 0, '../' per extra level."""
    return "../" * depth


def _depth_of(url_path: str) -> int:
    """Count directory levels below root for a root-relative URL path.

    /blog/slug.html -> depth 1 (blog/ subdir)
    /tools/calculators/slug.html -> depth 2
    /about-research.html -> depth 0 (root)
    """
    parts = url_path.lstrip("/").split("/")
    return max(0, len(parts) - 1)


def _is_hand_authored(rel: Path | str) -> bool:
    """True when this page's bytes are hand-authored source (see HAND_AUTHORED).

    Accepts either a root-relative url_path ("/products/market-terminal.html")
    or a Path relative to the site root, and normalises the separator so a
    native Windows Path still matches the posix keys in the frozenset.
    """
    return str(rel).replace("\\", "/").lstrip("/") in HAND_AUTHORED


def _canonical(url_path: str) -> str:
    """Full canonical URL from root-relative path."""
    return page_url(url_path.lstrip("/"))


def _rfc822(d: date) -> str:
    """Format a date as RFC 822 pubDate string at 12:00:00 GMT."""
    import datetime as _dt_mod
    dt = _dt_mod.datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=_dt_mod.timezone.utc)
    return email.utils.format_datetime(dt, usegmt=True)


def _cdata_safe(text: str) -> str:
    """Wrap text in CDATA, closing any embedded ]]> sequences."""
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


# ─────────────────────────────────────────────────────────────────────────────
# Frontmatter parser
# ─────────────────────────────────────────────────────────────────────────────


def _parse_md(path: Path) -> tuple[dict[str, Any], str]:
    """Split frontmatter + HTML body from a .md file.

    Returns (frontmatter_dict, body_html).
    Raises ValueError on malformed files.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path}: must start with '---' frontmatter fence")
    # find closing ---
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError(f"{path}: frontmatter closing '---' not found")
    fm_text = text[3:end].strip()
    body = text[end + 4:].strip()  # after the closing ---\n
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"{path}: YAML parse error: {e}") from e
    return fm, body


# ─────────────────────────────────────────────────────────────────────────────
# Frontmatter validator (CONTRACT §3)
# ─────────────────────────────────────────────────────────────────────────────


def _validate(fm: dict[str, Any], path: Path, all_slugs: frozenset[str]) -> None:
    """Validate frontmatter against CONTRACT §3.  Raises ValueError on violations."""
    slug = path.stem

    # required keys
    for key in ("slug", "family", "title", "description", "published", "updated"):
        if key not in fm:
            raise ValueError(f"{path}: missing required frontmatter key '{key}'")

    # slug == filename
    if fm["slug"] != slug:
        raise ValueError(
            f"{path}: slug '{fm['slug']}' must match filename '{slug}'"
        )

    # family enum
    if fm["family"] not in _VALID_FAMILIES:
        raise ValueError(
            f"{path}: invalid family '{fm['family']}'; must be one of {sorted(_VALID_FAMILIES)}"
        )

    # track required for lessons
    if fm["family"] == "lesson":
        if "track" not in fm:
            raise ValueError(f"{path}: lessons require 'track' key")
        if fm["track"] not in _VALID_TRACKS:
            raise ValueError(
                f"{path}: invalid track '{fm['track']}'; must be one of {sorted(_VALID_TRACKS)}"
            )
    elif fm["family"] == "product":
        for key in ("product_name", "eyebrow", "order", "workflow"):
            if key not in fm:
                raise ValueError(f"{path}: product pages require '{key}' key")
        order = fm["order"]
        if isinstance(order, bool) or not isinstance(order, int):
            raise ValueError(f"{path}: product order must be an integer")
        if not 1 <= order <= 99:
            raise ValueError(f"{path}: product order must be between 1 and 99")
        workflow = fm["workflow"]
        if not isinstance(workflow, list) or len(workflow) != 3:
            raise ValueError(f"{path}: product workflow must contain exactly 3 steps")
        if any(not str(step).strip() or len(str(step)) > 80 for step in workflow):
            raise ValueError(
                f"{path}: each product workflow step must be 1–80 characters"
            )

    # title length
    title_len = len(str(fm["title"]))
    if title_len > 70:
        raise ValueError(
            f"{path}: title is {title_len} chars (max 70 hard fail; ≤60 preferred)"
        )
    if title_len > 60:
        print(
            f"WARNING {path}: title is {title_len} chars (warn 60–70; trim to ≤60 preferred)",
            file=sys.stderr,
        )

    # description length
    desc_len = len(str(fm["description"]))
    if desc_len < 120 or desc_len > 155:
        raise ValueError(
            f"{path}: description is {desc_len} chars (must be 120–155)"
        )

    # dates must be date objects or parseable strings
    for dkey in ("published", "updated"):
        val = fm[dkey]
        if not isinstance(val, (date, datetime)):
            try:
                datetime.strptime(str(val), "%Y-%m-%d")
            except ValueError:
                raise ValueError(
                    f"{path}: '{dkey}' must be YYYY-MM-DD, got '{val}'"
                )

    # validate related.* slugs / hrefs
    related = fm.get("related") or {}
    for key, slugs in related.items():
        if key == "live":
            # live entries are dicts with href key
            if not isinstance(slugs, list):
                slugs = [slugs]
            for entry in slugs:
                href = entry.get("href", "") if isinstance(entry, dict) else str(entry)
                # a #fragment routes inside the destination page (e.g. the
                # options workspace's mode tabs) — existence is a path question
                base = href.split("#", 1)[0]
                if base not in _URL_MAP and not (
                    _LIVE_SITE_DIR / base.lstrip("/")
                ).exists():
                    raise ValueError(
                        f"{path}: related.live href '{href}' not in §1 URL map and "
                        f"not found in site/"
                    )
        elif key == "calculators":
            # validated at render time against calculators.yml
            pass
        elif key in ("lessons", "articles", "products"):
            if not isinstance(slugs, list):
                slugs = [slugs]
            for s in slugs:
                if key == "lessons":
                    # lessons slugs are track/slug
                    url_path = f"/learn/{s}.html"
                elif key == "articles":
                    url_path = f"/blog/{s}.html"
                else:
                    url_path = f"/products/{s}.html"
                if url_path not in _URL_MAP and s not in all_slugs:
                    raise ValueError(
                        f"{path}: related.{key} slug '{s}' not in §1 URL map"
                    )

    # validate cta href
    cta = fm.get("cta")
    if cta:
        href = cta.get("href", "") if isinstance(cta, dict) else str(cta)
        base = href.split("#", 1)[0]  # fragments route inside the page
        if (
            base not in _URL_MAP
            and href not in _ALLOWED_EXTERNAL_CTAS
            and not (_LIVE_SITE_DIR / base.lstrip("/")).exists()
        ):
            raise ValueError(
                f"{path}: cta.href '{href}' not in §1 URL map, the application "
                "CTA allowlist, or site/"
            )


# ─────────────────────────────────────────────────────────────────────────────
# H2 auto-anchor + TOC builder
# ─────────────────────────────────────────────────────────────────────────────


def _anchor_h2s(body_html: str) -> tuple[str, list[dict[str, str]]]:
    """Add id= to every <h2> (no existing id) and return (modified_body, toc).

    toc = list of {id: str, label: str} in document order.
    """
    toc: list[dict[str, str]] = []

    def _replace(m: re.Match) -> str:
        existing_id = m.group(1)  # may be None if no id attr
        text_content = re.sub(r"<[^>]+>", "", m.group(2))  # strip inner tags
        slug = _slugify(text_content)
        toc.append({"id": slug, "label": text_content})
        if existing_id:
            # already has id; keep it but still track in toc
            return m.group(0)
        return f'<h2 id="{slug}">{m.group(2)}</h2>'

    # Match <h2> with optional id="..." attribute
    pattern = re.compile(
        r'<h2(?:\s+id="([^"]+)")?[^>]*>(.*?)</h2>',
        re.IGNORECASE | re.DOTALL,
    )
    new_body = pattern.sub(_replace, body_html)
    return new_body, toc


# ─────────────────────────────────────────────────────────────────────────────
# JSON-LD generator
# ─────────────────────────────────────────────────────────────────────────────


def _article_jsonld(fm: dict[str, Any], canonical: str) -> str:
    """Return the Article JSON-LD payload (bare JSON — seo_base's jsonld block
    wraps it in the <script type="application/ld+json"> tag)."""
    published = fm["published"]
    updated = fm["updated"]
    if isinstance(published, (date, datetime)):
        published_str = published.isoformat() if isinstance(published, date) else published.date().isoformat()
    else:
        published_str = str(published)
    if isinstance(updated, (date, datetime)):
        updated_str = updated.isoformat() if isinstance(updated, date) else updated.date().isoformat()
    else:
        updated_str = str(updated)

    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": str(fm["title"]),
        "description": str(fm["description"]),
        "datePublished": published_str,
        "dateModified": updated_str,
        "author": {
            "@type": "Organization",
            "name": BRAND_RESEARCH_NAME,
        },
        "publisher": {
            "@type": "Organization",
            "name": BRAND_NAME,
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _product_jsonld(fm: dict[str, Any], canonical: str) -> str:
    """Return product-page JSON-LD without invented offers or reviews."""
    data = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": str(fm["title"]),
        "description": str(fm["description"]),
        "url": canonical,
        "isPartOf": {
            "@type": "WebSite",
            "name": BRAND_NAME,
            "url": SITE_BASE,
        },
        "mainEntity": {
            "@type": "SoftwareApplication",
            "name": str(fm["product_name"]),
            "applicationCategory": "FinanceApplication",
            "operatingSystem": "Web browser",
            "url": canonical,
        },
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Breadcrumb builder
# ─────────────────────────────────────────────────────────────────────────────


def _breadcrumbs(fm: dict[str, Any], url_path: str) -> list[dict[str, str | None]]:
    """Build breadcrumb list per CONTRACT §5.

    Returns list of {label, href} where the last item has href=None (current).
    """
    crumbs: list[dict[str, str | None]] = [{"label": "Home", "href": "/"}]

    family = fm["family"]
    if family == "article":
        crumbs.append({"label": "Blog", "href": "/blog/index.html"})
        crumbs.append({"label": fm["title"], "href": None})
    elif family == "lesson":
        track = fm["track"]
        crumbs.append({"label": "Learn", "href": "/learn/index.html"})
        crumbs.append(
            {"label": _TRACK_LABELS.get(track, track.title()), "href": f"/learn/{track}/"}
        )
        crumbs.append({"label": fm["title"], "href": None})
    elif family == "page":
        # tools spreadsheet or about-research
        if "/tools/" in url_path:
            crumbs.append({"label": "Tools", "href": "/tools/index.html"})
        crumbs.append({"label": fm["title"], "href": None})
    elif family == "product":
        crumbs.append({"label": "Platform", "href": "/products/index.html"})
        crumbs.append({"label": fm["product_name"], "href": None})

    return crumbs


# ─────────────────────────────────────────────────────────────────────────────
# Related resolver
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_related(
    fm: dict[str, Any],
    slug_title_map: dict[str, str],
    calc_map: dict[str, dict],
) -> dict[str, list[dict[str, str]]]:
    """Resolve related.* slugs to {href, title} lists per CONTRACT §5."""
    raw = fm.get("related") or {}
    resolved: dict[str, list[dict[str, str]]] = {}

    for key, items in raw.items():
        if key == "live":
            if not isinstance(items, list):
                items = [items]
            resolved["live"] = [
                {
                    "href": (e.get("href") if isinstance(e, dict) else str(e)),
                    "title": (e.get("label") if isinstance(e, dict) else str(e)),
                }
                for e in items
            ]
        elif key == "calculators":
            if not isinstance(items, list):
                items = [items]
            entries = []
            for s in items:
                if s in calc_map:
                    entries.append({
                        "href": f"/tools/calculators/{s}.html",
                        "title": calc_map[s].get("title", s),
                    })
            resolved["calculators"] = entries
        elif key == "lessons":
            if not isinstance(items, list):
                items = [items]
            entries = []
            for s in items:
                title = slug_title_map.get(s, s)
                entries.append({"href": f"/learn/{s}.html", "title": title})
            resolved["lessons"] = entries
        elif key == "articles":
            if not isinstance(items, list):
                items = [items]
            entries = []
            for s in items:
                title = slug_title_map.get(s, s)
                entries.append({"href": f"/blog/{s}.html", "title": title})
            resolved["articles"] = entries
        elif key == "products":
            if not isinstance(items, list):
                items = [items]
            entries = []
            for s in items:
                title = slug_title_map.get(s, s)
                entries.append({"href": f"/products/{s}.html", "title": title})
            resolved["products"] = entries

    return resolved


# ─────────────────────────────────────────────────────────────────────────────
# Content loader
# ─────────────────────────────────────────────────────────────────────────────


def _to_date(val: Any) -> date:
    """Convert YAML date/datetime/string to date."""
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return datetime.strptime(str(val), "%Y-%m-%d").date()


def load_content() -> tuple[list[dict], dict[str, dict]]:
    """Load and validate all .md files.  Returns (pages_list, calc_registry).

    pages_list: list of dicts with keys: fm, body_html, url_path, output_path
    calc_registry: dict slug -> calculator metadata (may be empty)
    """
    # Collect all slugs first (for cross-reference validation)
    all_slugs: set[str] = set()
    md_files: list[tuple[Path, str]] = []  # (path, url_path)

    # products
    products_dir = _CONTENT_DIR / "products"
    if products_dir.exists():
        for p in sorted(products_dir.glob("*.md")):
            all_slugs.add(p.stem)
            md_files.append((p, f"/products/{p.stem}.html"))

    # blog
    blog_dir = _CONTENT_DIR / "blog"
    if blog_dir.exists():
        for p in sorted(blog_dir.glob("*.md")):
            all_slugs.add(p.stem)
            md_files.append((p, f"/blog/{p.stem}.html"))

    # learn
    learn_dir = _CONTENT_DIR / "learn"
    if learn_dir.exists():
        for p in sorted(learn_dir.rglob("*.md")):
            track = p.parent.name
            all_slugs.add(f"{track}/{p.stem}")
            all_slugs.add(p.stem)
            md_files.append((p, f"/learn/{track}/{p.stem}.html"))

    # pages (about-research.md etc.)
    pages_dir = _CONTENT_DIR / "pages"
    if pages_dir.exists():
        for p in sorted(pages_dir.glob("*.md")):
            # about-research.md -> /about-research.html
            all_slugs.add(p.stem)
            md_files.append((p, f"/{p.stem}.html"))

    # tools
    tools_dir = _CONTENT_DIR / "tools"
    if tools_dir.exists():
        for p in sorted(tools_dir.glob("*.md")):
            # trading-journal.md -> /tools/spreadsheets/trading-journal.html
            all_slugs.add(p.stem)
            md_files.append((p, f"/tools/spreadsheets/{p.stem}.html"))

    frozen_slugs = frozenset(all_slugs)

    # Load calculators.yml
    calc_registry: dict[str, dict] = {}
    calc_yml = _CONTENT_DIR / "calculators.yml"
    if calc_yml.exists():
        try:
            raw = yaml.safe_load(calc_yml.read_text(encoding="utf-8")) or []
            for entry in raw:
                slug = entry.get("slug", "")
                if slug:
                    calc_registry[slug] = entry
        except yaml.YAMLError as e:
            print(f"WARNING: calculators.yml parse error: {e}", file=sys.stderr)
    else:
        print(
            "NOTE: content/seo/calculators.yml not found; calculator cards will be skipped",
            file=sys.stderr,
        )

    pages: list[dict] = []
    product_orders: dict[int, Path] = {}
    for md_path, url_path in md_files:
        fm, body_html = _parse_md(md_path)
        _validate(fm, md_path, frozen_slugs)
        if fm["family"] == "product":
            order = fm["order"]
            if order in product_orders:
                raise ValueError(
                    f"{md_path}: product order {order} duplicates "
                    f"{product_orders[order]}"
                )
            product_orders[order] = md_path

        # D4: CONTRACT §3 forbids <script in content bodies
        if re.search(r"<script", body_html, re.IGNORECASE):
            raise ValueError(
                f"{md_path}: body fragment contains '<script' — "
                "CONTRACT §3 forbids scripts in content bodies"
            )

        # auto-anchor h2s and build toc
        body_html, toc = _anchor_h2s(body_html)

        pages.append({
            "fm": fm,
            "body_html": body_html,
            "toc": toc,
            "url_path": url_path,
            "source_path": md_path,
        })

    return pages, calc_registry


# ─────────────────────────────────────────────────────────────────────────────
# Template context builder
# ─────────────────────────────────────────────────────────────────────────────


def _build_page_ctx(
    page: dict,
    slug_title_map: dict[str, str],
    calc_map: dict[str, dict],
) -> dict[str, Any]:
    """Build the full template context dict for an article/lesson/page."""
    fm = page["fm"]
    url_path = page["url_path"]
    depth = _depth_of(url_path)
    canonical = _canonical(url_path)

    published = _to_date(fm["published"])
    updated = _to_date(fm["updated"])

    # JSON-LD for editorial and product families
    jsonld_extra = ""
    if fm["family"] in ("article", "lesson"):
        jsonld_extra = _article_jsonld(fm, canonical)
    elif fm["family"] == "product":
        jsonld_extra = _product_jsonld(fm, canonical)

    # D2: include track in page dict so lesson eyebrow renders
    # seo_article.html.j2 gates on page.family=='lesson' and page.track;
    # the template maps track key to display labels via its own TRACK_LABEL dict,
    # so we pass the raw track key (technical/risk/ownership) directly.
    page_dict: dict[str, Any] = {
        "slug": fm["slug"],
        "family": fm["family"],
        "title": fm["title"],
        "description": fm["description"],
        "canonical": canonical,
        "url_path": url_path,
        "published": published,
        "updated": updated,
        "breadcrumbs": _breadcrumbs(fm, url_path),
        "track": fm.get("track"),  # D2: track for lesson eyebrow
        "product_name": fm.get("product_name"),
        "eyebrow": fm.get("eyebrow"),
        "workflow": fm.get("workflow") or [],
    }

    # D3: section for nav aria-current
    if fm["family"] == "article":
        page_dict["section"] = "blog"
    elif fm["family"] == "lesson":
        page_dict["section"] = "learn"
    elif fm["family"] == "page":
        if "/tools/" in url_path:
            page_dict["section"] = "tools"
        # about-research: no section (no nav highlight)
    elif fm["family"] == "product":
        page_dict["section"] = "products"

    related = _resolve_related(fm, slug_title_map, calc_map)
    cta = fm.get("cta")

    return {
        "rel": _rel_for_depth(depth),
        "page": page_dict,
        "site": {"base": SITE_BASE, "brand": BRAND_NAME},
        "body_html": page["body_html"],
        "toc": page["toc"],
        "related": related,
        "cta": cta,
        "jsonld_extra": jsonld_extra,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Hub context builders
# ─────────────────────────────────────────────────────────────────────────────


def _hub_items(pages: list[dict], family: str) -> list[dict]:
    """Sorted (published desc, slug) hub item dicts."""
    items = []
    for p in pages:
        fm = p["fm"]
        if fm["family"] != family:
            continue
        items.append({
            "title": fm["title"],
            "description": fm["description"],
            "url_path": p["url_path"],
            "published": _to_date(fm["published"]),
            "track": fm.get("track", ""),
            "cluster": fm.get("cluster", ""),
            "order": fm.get("order", 999),
            "product_name": fm.get("product_name", ""),
            "eyebrow": fm.get("eyebrow", ""),
            "workflow": fm.get("workflow") or [],
        })
    if family == "product":
        items.sort(key=lambda x: (x["order"], x["url_path"]))
    else:
        # sort: published desc, then slug
        items.sort(key=lambda x: (-x["published"].toordinal(), x["url_path"]))
    return items


def _products_hub_ctx(pages: list[dict]) -> dict[str, Any]:
    url_path = "/products/index.html"
    return {
        "rel": _rel_for_depth(_depth_of(url_path)),
        "page": {
            "slug": "products-index",
            "family": "hub",
            "section": "products",
            "title": "Market Intelligence Platform",
            "description": "Explore MastermindX: browser charting, nightly market "
                           "dashboards, stock dossiers, institutional research "
                           "and a context-aware AI assistant.",
            "canonical": _canonical(url_path),
            "url_path": url_path,
            "breadcrumbs": [
                {"label": "Home", "href": "/"},
                {"label": "Platform", "href": None},
            ],
        },
        "site": {"base": SITE_BASE, "brand": BRAND_NAME},
        "items": _hub_items(pages, "product"),
    }


def _blog_hub_ctx(pages: list[dict]) -> dict[str, Any]:
    items = _hub_items(pages, "article")
    url_path = "/blog/index.html"
    depth = _depth_of(url_path)
    canonical = _canonical(url_path)
    return {
        "rel": _rel_for_depth(depth),
        "page": {
            "slug": "blog-index",
            "family": "hub",
            "section": "blog",  # D3
            "title": "Blog",
            "description": "Plain-English trading education: position sizing, "
                           "risk, and how the math behind every trade works.",
            "canonical": canonical,
            "url_path": url_path,
            "breadcrumbs": [
                {"label": "Home", "href": "/"},
                {"label": "Blog", "href": None},
            ],
        },
        "site": {"base": SITE_BASE, "brand": BRAND_NAME},
        "items": items,
    }


def _learn_hub_ctx(pages: list[dict]) -> dict[str, Any]:
    url_path = "/learn/index.html"
    depth = _depth_of(url_path)
    canonical = _canonical(url_path)

    # Build tracks dict
    lessons_by_track: dict[str, list[dict]] = {t: [] for t in _TRACK_ORDER}
    for p in pages:
        fm = p["fm"]
        if fm["family"] != "lesson":
            continue
        track = fm.get("track", "")
        if track in lessons_by_track:
            lessons_by_track[track].append({
                "title": fm["title"],
                "description": fm["description"],
                "url_path": p["url_path"],
                "published": _to_date(fm["published"]),
                "cluster": fm.get("cluster", ""),
            })

    # Sort each track by published desc, slug
    for track in lessons_by_track:
        lessons_by_track[track].sort(
            key=lambda x: (-x["published"].toordinal(), x["url_path"])
        )

    tracks = [
        {
            "key": t,
            "label": _TRACK_LABELS[t],
            "lessons": lessons_by_track[t],
        }
        for t in _TRACK_ORDER
    ]

    flagship = {
        "title": "Gamma Weather — dealer positioning field manual",
        "url_path": "/learn.html",
        "href": "/learn.html",
    }

    return {
        "rel": _rel_for_depth(depth),
        "page": {
            "slug": "learn-index",
            "family": "hub",
            "section": "learn",  # D3
            "title": "Learning Center",
            "description": "Structured lessons on technical analysis, position "
                           "sizing, and reading insider filings — practical skills "
                           "for active traders.",
            "canonical": canonical,
            "url_path": url_path,
            "breadcrumbs": [
                {"label": "Home", "href": "/"},
                {"label": "Learning Center", "href": None},
            ],
        },
        "site": {"base": SITE_BASE, "brand": BRAND_NAME},
        "tracks": tracks,
        "flagship": flagship,
        "items": _hub_items(pages, "lesson"),
    }


def _tools_hub_ctx(calc_registry: dict[str, dict]) -> dict[str, Any]:
    url_path = "/tools/index.html"
    depth = _depth_of(url_path)
    canonical = _canonical(url_path)

    if calc_registry:
        items = [
            {
                "slug": slug,
                "title": entry.get("title", slug),
                "description": entry.get("description", ""),
                "blurb": entry.get("blurb", ""),
                "url_path": f"/tools/calculators/{slug}.html",
                "cluster": entry.get("cluster", ""),
            }
            for slug, entry in calc_registry.items()
        ]
        # registry (YAML file) order is the display order — position-size
        # leads deliberately; dict insertion order keeps this deterministic
    else:
        items = []

    return {
        "rel": _rel_for_depth(depth),
        "page": {
            "slug": "tools-index",
            "family": "hub",
            "section": "tools",  # D3
            "title": "Tools",
            "description": "Free trading calculators and spreadsheets: position "
                           "sizing, risk/reward, compounding, drawdown recovery "
                           "and more.",
            "canonical": canonical,
            "url_path": url_path,
            "breadcrumbs": [
                {"label": "Home", "href": "/"},
                {"label": "Tools", "href": None},
            ],
        },
        "site": {"base": SITE_BASE, "brand": BRAND_NAME},
        "items": items,
        "calc_registry": calc_registry,
    }


# ─────────────────────────────────────────────────────────────────────────────
# RSS feed builder
# ─────────────────────────────────────────────────────────────────────────────


def _build_rss(pages: list[dict]) -> str:
    """Build RSS 2.0 feed XML for blog articles, sorted published desc."""
    articles = [
        p for p in pages if p["fm"]["family"] == "article"
    ]
    articles.sort(key=lambda p: _to_date(p["fm"]["published"]).toordinal(), reverse=True)

    items_xml: list[str] = []
    for p in articles:
        fm = p["fm"]
        canonical = _canonical(p["url_path"])
        pub_date = _rfc822(_to_date(fm["published"]))
        item = (
            "    <item>\n"
            f"      <title>{_cdata_safe(str(fm['title']))}</title>\n"
            f"      <link>{canonical}</link>\n"
            f"      <description>{_cdata_safe(str(fm['description']))}</description>\n"
            f"      <pubDate>{pub_date}</pubDate>\n"
            f"      <guid isPermaLink=\"true\">{canonical}</guid>\n"
            "    </item>"
        )
        items_xml.append(item)

    channel_link = page_url("blog/index.html")
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{BRAND_RESEARCH_NAME} Blog</title>\n"
        f"    <link>{channel_link}</link>\n"
        f"    <description>Plain-English trading education from {BRAND_RESEARCH_NAME}.</description>\n"
        f'    <atom:link href="{page_url("blog/feed.xml")}" rel="self" type="application/rss+xml"/>\n'
        + "\n".join(items_xml)
        + "\n  </channel>\n</rss>\n"
    )
    return feed


# ─────────────────────────────────────────────────────────────────────────────
# Renderer
# ─────────────────────────────────────────────────────────────────────────────


# Required templates (from CONTRACT §2)
_REQUIRED_TEMPLATES = [
    "seo_base.html.j2",
    "seo_products_index.html.j2",
    "seo_product.html.j2",
    "seo_tools_index.html.j2",
    "seo_learn_index.html.j2",
    "seo_blog_index.html.j2",
    "seo_article.html.j2",
]

# Calculator slug -> template name mapping (CONTRACT §1)
_CALC_TEMPLATES = [
    "position_size",
    "risk_reward",
    "trade_profit",
    "compounding",
    "cagr",
    "drawdown_recovery",
    "retirement",
    "roi",
    "dividend",
    "dollar_cost_averaging",
    "rule_of_72",
    "percentage_gain_loss",
    "savings_goal",
    "inflation",
    "net_worth",
    "options_profit",
    "stock_average",
    "margin",
    "forex_pip_value",
    "short_selling",
    "covered_call",
    "stop_loss_take_profit",
    "kelly_criterion",
    "sharpe_ratio",
    "portfolio_rebalancing",
    "risk_of_ruin",
]


def _check_templates(env: Environment) -> list[str]:
    """Return list of missing required template names."""
    missing = []
    for name in _REQUIRED_TEMPLATES:
        try:
            env.get_template(name)
        except TemplateNotFound:
            missing.append(name)
    return missing


def _output_path(url_path: str, out_dir: Path) -> Path:
    """Convert a root-relative URL path to an output filesystem path."""
    rel = url_path.lstrip("/")
    return out_dir / rel


def _strip_line_end_whitespace(text: str) -> str:
    """Remove indentation left behind by optional Jinja product blocks.

    Splitting on the literal newline preserves the template's final newline
    while keeping the established rendering of the older estate templates
    byte-for-byte unchanged.
    """

    return "\n".join(line.rstrip() for line in text.split("\n"))


def render_all(out_dir: Path) -> None:
    """Load all content and render to out_dir.

    Exits with code 2 if required templates are missing.
    Exits with code 1 on content validation failures.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
        keep_trailing_newline=True,
    )

    # Check required templates
    missing = _check_templates(env)
    if missing:
        print(
            "ERROR: required templates missing — cannot render:\n"
            + "\n".join(f"  templates/{t}" for t in missing),
            file=sys.stderr,
        )
        sys.exit(2)

    # Load content
    pages, calc_registry = load_content()

    if not pages:
        print(
            "NOTE: No content files found in content/seo/; "
            "skipping render (no .md files yet)",
            file=sys.stderr,
        )
        # Still need to render hubs + feed if templates exist
        # Return early — no content to render

    # Build slug->title map for related resolution
    slug_title_map: dict[str, str] = {}
    for p in pages:
        fm = p["fm"]
        slug_title_map[fm["slug"]] = fm["title"]
        if fm["family"] == "lesson":
            track_slug = f"{fm['track']}/{fm['slug']}"
            slug_title_map[track_slug] = fm["title"]

    # ---- Render individual article/lesson/page files ----
    for page in pages:
        fm = page["fm"]
        url_path = page["url_path"]
        if _is_hand_authored(url_path):
            # Hand-authored flagship: its .md still fed slug_title_map above and
            # still feeds _products_hub_ctx / related resolution below, so the
            # page stays in `pages` — we skip only the write, before the output
            # directory is even touched, so nothing half-processed is left for
            # the externalize_css / optimize_assets sweeps to pick up.
            continue
        out_path = _output_path(url_path, out_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ctx = _build_page_ctx(page, slug_title_map, calc_registry)

        # pick template
        tmpl_name = (
            "seo_product.html.j2"
            if fm["family"] == "product"
            else "seo_article.html.j2"
        )
        try:
            tmpl = env.get_template(tmpl_name)
        except TemplateNotFound:
            print(f"ERROR: template '{tmpl_name}' not found", file=sys.stderr)
            sys.exit(2)

        html = tmpl.render(**ctx)
        if fm["family"] == "product":
            html = _strip_line_end_whitespace(html)
        # write_page, not write_text — the seo_* templates carry no data-base
        # shim, so a raw write ships these pages pointed at Pages instead of R2
        # outside the render lane's inject_data_base sweep. NOTE: this target
        # comes from _output_path(), whose ".html" lives in the content
        # frontmatter rather than in any source literal — no static guard can see
        # it, so the committed-page tripwire in tests/test_site_shim.py is the
        # only backstop for this one. Keep it on write_page.
        write_page(out_path, html, encoding="utf-8")

    # ---- Render hubs ----
    # Products hub
    try:
        products_tmpl = env.get_template("seo_products_index.html.j2")
        products_ctx = _products_hub_ctx(pages)
        products_out = out_dir / "products" / "index.html"
        products_out.parent.mkdir(parents=True, exist_ok=True)
        write_page(
            products_out,
            _strip_line_end_whitespace(products_tmpl.render(**products_ctx)),
            encoding="utf-8",
        )
    except TemplateNotFound:
        print(
            "ERROR: template 'seo_products_index.html.j2' not found",
            file=sys.stderr,
        )
        sys.exit(2)

    # Blog hub
    try:
        blog_tmpl = env.get_template("seo_blog_index.html.j2")
        blog_ctx = _blog_hub_ctx(pages)
        blog_out = out_dir / "blog" / "index.html"
        blog_out.parent.mkdir(parents=True, exist_ok=True)
        write_page(blog_out, blog_tmpl.render(**blog_ctx), encoding="utf-8")
    except TemplateNotFound:
        print("ERROR: template 'seo_blog_index.html.j2' not found", file=sys.stderr)
        sys.exit(2)

    # Learn hub
    try:
        learn_tmpl = env.get_template("seo_learn_index.html.j2")
        learn_ctx = _learn_hub_ctx(pages)
        learn_out = out_dir / "learn" / "index.html"
        learn_out.parent.mkdir(parents=True, exist_ok=True)
        write_page(learn_out, learn_tmpl.render(**learn_ctx), encoding="utf-8")
    except TemplateNotFound:
        print("ERROR: template 'seo_learn_index.html.j2' not found", file=sys.stderr)
        sys.exit(2)

    # Tools hub
    try:
        tools_tmpl = env.get_template("seo_tools_index.html.j2")
        tools_ctx = _tools_hub_ctx(calc_registry)
        tools_out = out_dir / "tools" / "index.html"
        tools_out.parent.mkdir(parents=True, exist_ok=True)
        write_page(tools_out, tools_tmpl.render(**tools_ctx), encoding="utf-8")
    except TemplateNotFound:
        print("ERROR: template 'seo_tools_index.html.j2' not found", file=sys.stderr)
        sys.exit(2)

    # ---- Render calculator pages ----
    # Calculator templates live at templates/calculators/<slug>.html.j2
    calc_tmpl_dir = _TEMPLATES_DIR / "calculators"
    if calc_registry and calc_tmpl_dir.exists():
        # cluster -> ordered slugs, for sibling "Keep going" links (SEO internal
        # linking; registry order is display order so this is deterministic)
        _by_cluster: dict[str, list[str]] = {}
        for _s, _e in calc_registry.items():
            _by_cluster.setdefault(_e.get("cluster", ""), []).append(_s)
        for slug, entry in calc_registry.items():
            tmpl_name = f"calculators/{slug.replace('-', '_')}.html.j2"
            try:
                calc_tmpl = env.get_template(tmpl_name)
            except TemplateNotFound:
                print(
                    f"NOTE: calculator template '{tmpl_name}' not found; skipping {slug}",
                    file=sys.stderr,
                )
                continue

            url_path = f"/tools/calculators/{slug}.html"
            depth = _depth_of(url_path)
            canonical = _canonical(url_path)

            # D1: build related rail and cta from registry's related_lesson
            related_lesson_slug = entry.get("related_lesson", "")  # e.g. "risk/position-sizing"
            lesson_href = f"/learn/{related_lesson_slug}.html" if related_lesson_slug else ""
            lesson_title = slug_title_map.get(related_lesson_slug, related_lesson_slug)

            calc_related: dict[str, Any] = {}
            # sibling calculators from the same cluster (up to 3) — internal
            # linking that fills the "Keep going" rail even when there is no
            # matching lesson
            cluster = entry.get("cluster", "")
            siblings = [s for s in _by_cluster.get(cluster, []) if s != slug][:3]
            if siblings:
                calc_related["calculators"] = [
                    {"href": f"/tools/calculators/{s}.html",
                     "title": calc_registry[s].get("title", s)}
                    for s in siblings
                ]
            if lesson_href:
                calc_related["lessons"] = [{"href": lesson_href, "title": lesson_title}]
            # Always include trading journal as a live link
            calc_related["live"] = [
                {"href": "/tools/spreadsheets/trading-journal.html",
                 "title": "Free trading journal spreadsheet"}
            ]

            # Every calculator page carries a "next step" — it is the only
            # conversion surface on a free estate page. A matching lesson wins;
            # otherwise fall back to the product itself (11 of 26 registry
            # entries carry a related_lesson, and no honest lesson exists for
            # the rest — inventing one would be fake internal linking).
            if lesson_href:
                calc_cta: dict[str, str] = {
                    "href": lesson_href,
                    "label": f"Read the lesson: {lesson_title}",
                }
            else:
                calc_cta = {
                    "href": "/index.html",
                    "label": "Open the dashboard",
                    "label_zh": "打开仪表盘",
                }

            calc_ctx: dict[str, Any] = {
                "rel": _rel_for_depth(depth),
                "page": {
                    "slug": slug,
                    "family": "calculator",
                    "section": "tools",  # D1 + D3: section for nav active state
                    "title": entry.get("title", slug),
                    "description": entry.get("description", ""),
                    "canonical": canonical,
                    "url_path": url_path,
                    "breadcrumbs": [
                        {"label": "Home", "href": "/"},
                        {"label": "Tools", "href": "/tools/index.html"},
                        {"label": entry.get("title", slug), "href": None},
                    ],
                },
                "site": {"base": SITE_BASE, "brand": BRAND_NAME},
                "registry": entry,
                # D1: related rail and cta; no toc for calculators (CONTRACT §5)
                "related": calc_related,
                "cta": calc_cta,
                "toc": None,
            }
            calc_out = out_dir / "tools" / "calculators" / f"{slug}.html"
            calc_out.parent.mkdir(parents=True, exist_ok=True)
            write_page(calc_out, calc_tmpl.render(**calc_ctx), encoding="utf-8")

    # ---- RSS feed ----
    rss = _build_rss(pages)
    rss_out = out_dir / "blog" / "feed.xml"
    rss_out.parent.mkdir(parents=True, exist_ok=True)
    rss_out.write_text(rss, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# --check mode: render to tmp, byte-compare with site/
# ─────────────────────────────────────────────────────────────────────────────

# The committed estate pages are NOT this builder's raw output — the render
# lanes run idempotent post-render sweeps over site/ after every builder
# (render.yml: inject_data_base -> externalize_css -> optimize_assets; daily.yml
# runs inject_wh_banner first). A raw byte-compare therefore diffs a pre-image
# against a post-image and can never go green, which is exactly how this check
# rotted unnoticed. So --check replays the same deterministic sweeps over the
# temp render before comparing — like against like.
#
# wh_banner is the one sweep we cannot replay: only daily.yml runs it, so
# whether a page carries the tag depends on which lane last touched it (the
# three legal pages from #3592 have been through render.yml but not daily.yml
# yet). It is a marker-guarded additive tag that changes nothing else, so it is
# stripped from both sides instead.
_WHB_TAG_RE = re.compile(r"[ \t]*<script[^>]*\bdata-whb\b[^>]*></script>\n?")
_EXTERNALIZED_CSS_SUBDIR = ("assets", "css")

# optimize_assets stamps `?v=<hash of the referenced file>`. For shared assets
# (theme.css, theme.js, …) that hash tracks a file this builder does not own, so
# any PR touching theme.css would turn every estate page red here until a render
# lane re-stamped them — a false positive on someone else's change. The stamp is
# lane-owned and self-healing, so the comparison keeps its *presence* (and the
# defer/preload rewrites around it) but drops its value. The content hash in an
# `assets/css/<hash>.css` FILENAME is estate CSS and stays compared exactly.
_ASSET_STAMP_RE = re.compile(r"\?v=[0-9a-f]+")


def _comparable(text: str) -> str:
    """Project a page into the space this builder is accountable for."""
    return _ASSET_STAMP_RE.sub("?v=", _WHB_TAG_RE.sub("", text))


def _normalize_like_render_lane(tmp_site: Path) -> None:
    """Replay the render lane's post-render sweeps over a temp site tree.

    Mirrors .github/workflows/render.yml. Each sweep is idempotent and never
    raises; optimize_assets/externalize_css need the real .css/.js next to the
    pages to content-hash, so the caller seeds those first.
    """
    from scripts.externalize_css import externalize
    from scripts.inject_data_base import inject as inject_data_base
    from scripts.optimize_assets import optimize

    inject_data_base(tmp_site)   # no-op: write_page already injected at write time
    externalize(tmp_site)
    optimize(tmp_site)


def _seed_hashable_assets(tmp_site: Path) -> set[Path]:
    """Copy site/'s .css/.js next to the temp render; return what was copied.

    optimize_assets stamps `?v=<content-hash>` by hashing the referenced file,
    so the assets the estate pages link (theme.css, theme.js, …) must exist in
    the temp tree or the stamps come out blank and every page reports drift.

    site/assets/css/ is deliberately NOT seeded: those files are externalize_css
    output, so letting the sweep regenerate them from this render turns the
    committed hashed stylesheets into part of what the check verifies.
    """
    seeded: set[Path] = set()
    css_out = Path(*_EXTERNALIZED_CSS_SUBDIR)
    for src in _SITE_DIR.rglob("*"):
        if not src.is_file() or src.suffix not in (".css", ".js"):
            continue
        rel = src.relative_to(_SITE_DIR)
        if css_out in rel.parents:
            continue
        dst = tmp_site / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        seeded.add(rel)
    return seeded


def _check_mode() -> int:
    """Render to a temp dir; compare against committed site/ output.

    Returns 0 if identical, 1 if drift detected.
    """
    with tempfile.TemporaryDirectory() as tmp:
        # Named "site" so lib.pages.dbase_prefix resolves sub-directory depth
        # the same way it does for the real tree.
        tmp_dir = Path(tmp) / "site"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # Render to tmp, then replay the render lane's sweeps so the comparison
        # is post-image against post-image.
        render_all(tmp_dir)
        seeded = _seed_hashable_assets(tmp_dir)
        _normalize_like_render_lane(tmp_dir)

        # Compare against site/ — everything this build produced (the pages, the
        # RSS feed, and the hashed stylesheets externalize_css lifted out of
        # them), but not the assets seeded purely so the sweeps could run.
        drifted: list[str] = []
        for out_path in sorted(tmp_dir.rglob("*")):
            if not out_path.is_file():
                continue
            rel = out_path.relative_to(tmp_dir)
            if rel in seeded:
                continue
            if _is_hand_authored(rel):
                # render_all never writes these, so this arm is normally dead —
                # kept so a future stray write can only be silent, never a red
                # drift report against bytes this builder does not own.
                continue
            site_path = _SITE_DIR / rel
            if not site_path.exists():
                drifted.append(f"MISSING in site/: {rel}")
                continue
            built, committed = out_path.read_bytes(), site_path.read_bytes()
            if built != committed and rel.suffix == ".html":
                built = _comparable(built.decode("utf-8")).encode("utf-8")
                committed = _comparable(committed.decode("utf-8")).encode("utf-8")
            if built != committed:
                drifted.append(f"DIFFERS: {rel}")

        if drifted:
            print(
                "DRIFT DETECTED — rendered output does not match committed site/:",
                file=sys.stderr,
            )
            for d in drifted:
                print(f"  {d}", file=sys.stderr)
            return 1

        # D5: orphan detection — walk committed site subdirs and report any
        # HTML/XML files not produced by this fresh render
        orphans: list[str] = []
        _FREE_DIRS = ["products", "blog", "learn", "tools"]
        _FREE_ROOT_FILES = ["about-research.html", "privacy.html", "terms.html", "disclaimer.html"]

        for sub in _FREE_DIRS:
            committed_sub = _SITE_DIR / sub
            if not committed_sub.exists():
                continue
            for committed_file in sorted(committed_sub.rglob("*")):
                if not committed_file.is_file():
                    continue
                if committed_file.suffix not in (".html", ".xml"):
                    continue
                rel = committed_file.relative_to(_SITE_DIR)
                # HAND_AUTHORED pages are source, not output — the builder is
                # meant not to produce them, so they are never orphans.
                if _is_hand_authored(rel):
                    continue
                rendered = tmp_dir / rel
                if not rendered.exists():
                    orphans.append(f"ORPHAN (not produced by builder): {rel}")

        for fname in _FREE_ROOT_FILES:
            committed_file = _SITE_DIR / fname
            if committed_file.exists():
                rel = Path(fname)
                if _is_hand_authored(rel):
                    continue
                rendered = tmp_dir / rel
                if not rendered.exists():
                    orphans.append(f"ORPHAN (not produced by builder): {rel}")

        if orphans:
            print(
                "ORPHAN FILES DETECTED — committed site/ contains files not produced by this build:",
                file=sys.stderr,
            )
            for o in orphans:
                print(f"  {o}", file=sys.stderr)
            return 1

        rendered_count = sum(
            1
            for p in tmp_dir.rglob("*")
            if p.is_file() and p.relative_to(tmp_dir) not in seeded
        )
        # Name what was NOT verified: the hand-authored pages are outside this
        # check's accountability, so a silent count would read as full coverage.
        print(
            f"OK: {rendered_count} files, all byte-identical with site/; no orphans "
            f"({len(HAND_AUTHORED)} hand-authored page(s) exempt — bytes not owned here)"
        )
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build public acquisition estate (products/blog/learn/tools)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate + render to tmp; exit 1 if site/ output differs.",
    )
    args = parser.parse_args()

    if args.check:
        return _check_mode()

    # Full build into site/
    render_all(_SITE_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
