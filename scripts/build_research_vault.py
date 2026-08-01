"""Build the Research Vault page -> site/research_vault.html.

RV W3. A flagship, gated vault + feed of third-party institutional research PDFs.
The page is an SSR shell + live client paint:

  • At build time we read ``data/research_vault/catalog.json`` (the snapshot the
    hourly ingest job commits) IF present, and bake it into the page as a
    ``<script id="rv-catalog" type="application/json">`` island — so the feed +
    Top Picks remain crawlable for SEO and available as a network fallback.
  • If the catalog is absent or empty, we bake an empty ``{items:[]}`` and the
    client renders an honest empty state ("No institutional reports are available
    yet"). We NEVER bake fake sample data (house law).
  • On load, ``site/research_vault_app.js`` paints from GET /api/research/catalog
    (hourly-fresh) before revealing interactive data, then drives all interaction
    (feed/lanes/tree/facets/search + the auth-gated pdf.js viewer with quota-metered
    download). A failed live read exposes the bake with an explicit snapshot label.

Fully static + additive: depends on no live JSON at build time, so it can never
break the daily build (a missing catalog degrades to the empty state). Bilingual
(EN/中文) via the same l-en/l-zh spans as the rest of the site.

Usage: python -m scripts.build_research_vault
"""
from __future__ import annotations

import html as _html
import json
import logging
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.research_vault import catalog as catalog_mod  # noqa: E402
from engine.research_vault.sidecar import clean_title  # noqa: E402
from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_research_vault")

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
CATALOG_PATH = ROOT / "data" / "research_vault" / "catalog.json"

_EMPTY_CATALOG = {
    "schema": "research_vault.catalog.v1",
    "generated_at": "",
    "count": 0,
    "institutions": [],
    "items": [],
}

# The public-safe fields we bake per item (mirror engine/research_vault/catalog.py
# _ITEM_FIELDS — body text is NEVER in the catalog, it lives in the search corpus).
_ITEM_FIELDS = (
    "id", "title", "institution", "side", "desk", "published_at",
    "summary_points", "tags", "tickers", "top_pick", "pages", "language",
    "needs_metadata",
)


def load_catalog() -> dict:
    """Load the committed catalog snapshot, or the empty catalog if absent/bad.

    Never raises — a missing or corrupt snapshot degrades to the honest empty
    state rather than wedging the nightly build.
    """
    if not CATALOG_PATH.exists():
        log.info("no committed catalog at %s — baking empty state", CATALOG_PATH)
        return dict(_EMPTY_CATALOG)
    try:
        obj = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(obj, dict) or not isinstance(obj.get("items"), list):
            log.warning("catalog malformed — baking empty state")
            return dict(_EMPTY_CATALOG)
        return obj
    except Exception as e:  # noqa: BLE001 — a bad snapshot must not break the build
        log.warning("catalog read failed (%s) — baking empty state", e)
        return dict(_EMPTY_CATALOG)


def _public_item(item: dict) -> dict:
    pub = {k: item.get(k) for k in _ITEM_FIELDS}
    # Render-side guard: the committed snapshot is data we do not control (the
    # upstream desk truncates its own ticker parentheticals), and it feeds the SSR
    # cards + the JSON island + every /research/ landing page below. Repair here so
    # a stale snapshot can never ship an unbalanced "(" into a public surface.
    pub["title"] = clean_title(pub.get("title")) or (pub.get("title") or "")
    return pub


def _public_catalog(cat: dict) -> dict:
    """Project to the public-safe subset (defensive: drops any stray body text)."""
    items = [_public_item(it) for it in (cat.get("items") or []) if isinstance(it, dict)]
    return {
        "schema": cat.get("schema") or _EMPTY_CATALOG["schema"],
        "generated_at": cat.get("generated_at") or "",
        "count": len(items),
        "institutions": cat.get("institutions") or [],
        "items": items,
    }


_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_STAMP = {"buy": "BUY", "sell": "SELL", "independent": "IND"}


def _e(s) -> str:
    return _html.escape("" if s is None else str(s), quote=True)


def _fmt_date(d: str) -> str:
    if not d or d.count("-") < 2:
        return _e(d)
    y, m, dd = d.split("-")[:3]
    try:
        return f"{_MON[int(m) - 1]} {int(dd)}, {y}"
    except (ValueError, IndexError):
        return _e(d)


def _fmt_datetime(pub: str) -> str:
    """'Jul 24, 2026 · 10:08 UTC' — the desk's source publish time (published_at),
    shown in UTC. Mirrors the client's ``fmtWhen`` exactly so the SSR baseline and
    the hydrated card read identically. Degrades to date-only when no time is present."""
    date = (pub or "").split("T")[0]
    base = _fmt_date(date)
    if pub and "T" in pub:
        hm = pub.split("T")[1][:5]
        if len(hm) == 5 and hm[2] == ":":
            return f"{base} · {_e(hm)} UTC"
    return base


def _logo_for(inst: str) -> str:
    inst = (inst or "").strip()
    if not inst or inst == "Unknown":
        return "?"
    parts = [p for p in inst.replace(".", " ").split() if p]
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _title_link(x: dict) -> str:
    """Plain report title for the anonymous SSR preview.

    The hydrated Pro feed restores the interactive viewer link. Keeping the
    no-JS public baseline plain ensures its three summaries cannot open a report.
    """
    return _e(x.get("title"))


def _ssr_card(x: dict) -> str:
    """A crawlable, static Latest-lane card (SEO + instant paint). The client
    re-renders the full interactive feed on hydrate; this is the no-JS baseline.
    English content only (report text is the analyst's source language); the page
    chrome around it stays bilingual via the template's l-en/l-zh spans."""
    inst = (x.get("institution") or "Unknown").strip() or "Unknown"
    side = (x.get("side") or "independent").lower()
    stamp_cls = "buy" if side == "buy" else ("sell" if side == "sell" else "indep")
    stamp = _STAMP.get(side, "IND")
    desk = x.get("desk") or ""
    top = bool(x.get("top_pick"))
    needs = bool(x.get("needs_metadata"))
    pts = x.get("summary_points") or []
    tags = x.get("tags") or []

    desk_bits = f'<span class="rep-sep">·</span><span class="rep-desk">{_e(desk)}</span>' if desk else (
        '<span class="rep-sep">·</span><span class="backfill">institution to be confirmed</span>' if needs else "")
    pin = '<span class="rep-pin"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6 4.6 2.3 7.4-6.3-4.6L5.7 21l2.3-7.4-6-4.6h7.6z"/></svg>Highlighted</span>' if top else ""
    if pts:
        pts_html = '<ul class="rep-points">' + "".join(f"<li>{_e(p)}</li>" for p in pts[:4]) + "</ul>"
    else:
        pts_html = '<ul class="rep-points pend"><li>Summary pending — full report available to read.</li></ul>'
    tags_html = "".join(f'<span class="rep-tag">{_e(t)}</span>' for t in tags)
    cal = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>'
    cls = "rep glass" + (" pick" if top else "") + (" needs" if needs else "")
    return (
        f'<article class="{cls}" data-id="{_e(x.get("id"))}">'
        f'<div class="rep-top">'
        f'<span class="rep-logo">{_e(_logo_for(inst))}</span>'
        f'<span class="rep-unread" aria-hidden="true"></span>'
        f'<span class="rep-inst">{_e(inst)}</span>{desk_bits}'
        f'<span class="stamp {stamp_cls}"><span class="dt"></span>{stamp}</span>{pin}'
        f'</div>'
        f'<h3>{_title_link(x)}</h3>{pts_html}'
        f'<div class="rep-foot"><div class="rep-meta">'
        f'<span class="rep-date">{cal}{_fmt_datetime(x.get("published_at"))}</span>'
        f'<span class="rep-tags">{tags_html}</span></div></div>'
        f'</article>'
    )


def _preview_items(items: list[dict], limit: int = 3) -> list[dict]:
    """Latest reports with real summaries, filled from the latest rows if needed."""
    ready = [
        item for item in items
        if any(str(point or "").strip() for point in (item.get("summary_points") or []))
    ]
    preview = ready[:limit]
    selected = {str(item.get("id") or "") for item in preview}
    if len(preview) < limit:
        preview.extend(
            item for item in items
            if str(item.get("id") or "") not in selected
        )
    return preview[:limit]


def _ssr_feed(catalog: dict) -> str:
    items = catalog.get("items") or []
    if not items:
        return ""  # client renders the honest bilingual empty state
    preview_items = _preview_items(items)
    preview = "".join(_ssr_card(x) for x in preview_items)
    remaining = max(0, len(items) - len(preview_items))
    if not remaining:
        return preview
    gate = (
        '<div class="rv-lockwrap">'
        '<div class="rv-lockghosts" aria-hidden="true">'
        '<article class="rep glass"><div class="rep-top"><span class="rep-logo">PRO</span>'
        '<span class="rep-inst">Institutional desk</span></div>'
        '<h3>Pro research report</h3><ul class="rep-points">'
        '<li>Full summary available with Pro.</li></ul></article>'
        '</div><div class="rv-lockover glass">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<rect x="3" y="11" width="18" height="11" rx="2"/>'
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
        f'<h3><span class="l-en">{remaining} more institutional '
        f'{"report" if remaining == 1 else "reports"}</span>'
        f'<span class="l-zh">还有 {remaining} 篇机构研报</span></h3>'
        '<p><span class="l-en">You’re previewing the latest three summaries. '
        'Upgrade to Pro to open every desk and read the full PDFs.</span>'
        '<span class="l-zh">你正在预览最新三篇摘要。升级 Pro 即可查看全部机构研报并阅读 PDF 全文。</span></p>'
        '<a class="btn upgrade" href="plans.html">'
        '<span class="l-en">Upgrade to Pro</span><span class="l-zh">升级 Pro</span></a>'
        '</div></div>'
    )
    return preview + gate


def render(catalog: dict | None = None) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template("research_vault.html.j2")
    if catalog is None:
        catalog = _public_catalog(load_catalog())
    # The anonymous JSON island carries only the same three reports rendered in
    # the public SSR preview. ``count`` remains the full inventory size so the
    # upgrade wall can state what is locked without embedding later summaries.
    baked_catalog = dict(catalog)
    baked_catalog["items"] = _preview_items(list(catalog.get("items") or []))
    baked_catalog["count"] = len(catalog.get("items") or [])
    baked_catalog["preview"] = True
    baked_catalog["summary"] = catalog_mod.public_summary(catalog)
    # ensure_ascii=False keeps CJK readable; </script> is escaped so a
    # title/summary containing it can't break out of the island.
    catalog_json = json.dumps(baked_catalog, ensure_ascii=False).replace("</", "<\\/")
    ssr_feed = _ssr_feed(catalog)
    return tmpl.render(catalog_json=catalog_json, ssr_feed=ssr_feed)


def build() -> Path:
    catalog = _public_catalog(load_catalog())
    # Inject the per-report slug so the SSR cards + JS island can link straight to
    # the matching research/<slug>.html landing page (shared slug logic with
    # build_research_pages — strong internal linking for the SEO play).
    try:
        from scripts import build_research_pages as _rp
        _smap = _rp.slug_map(catalog["items"])
        for _it in catalog["items"]:
            _it["slug"] = _smap.get(_it.get("id"), "")
    except Exception as exc:  # noqa: BLE001 — links degrade to none; pages still build below
        log.warning("slug injection failed (vault cards lose /research/ links): %s", exc)
        for _it in catalog["items"]:
            _it.setdefault("slug", "")
    page = render(catalog)
    out = config.ROOT / "site" / "research_vault.html"
    write_page(out, page)
    n = page.count('class="rep glass')  # SSR cards (0 when empty → empty state)
    log.info("built %s (%d report cards baked)", out, n)
    # Programmatic SEO: one indexable landing page per report (+ crawl hub +
    # sitemap). Rides this nightly vault build; never fatal to it.
    try:
        from scripts import build_research_pages
        n_pages = build_research_pages.build(catalog)
        if (catalog.get("items") or []) and not n_pages:
            log.warning("catalog has %d items but ZERO report pages were written",
                        len(catalog["items"]))
            # Bare print, NOT log.warning: GitHub Actions parses a workflow command only
            # when the emitted line STARTS with "::warning". This module logs with
            # format "%(levelname)s %(message)s", so log.warning("::warning ...") emits
            # "WARNING ::warning ..." and the annotation is silently dropped.
            print(f"::warning title=research_pages::catalog has "
                  f"{len(catalog['items'])} items but ZERO report pages were written — "
                  f"/research/ SEO pages missing/stale", flush=True)
    except Exception as exc:  # noqa: BLE001 — SEO pages must not break the vault build
        # Fail-soft by law (the vault page ships even if the SEO pages break) but LOUD:
        # full traceback into the builder log + a one-line ::warning that surfaces in
        # the Actions annotations even at rc=0.
        log.warning("research report pages build failed (non-fatal): %s", exc, exc_info=True)
        print(f"::warning title=research_pages::report pages build failed "
              f"(non-fatal, vault page unaffected): {type(exc).__name__}: {exc}", flush=True)
    return out


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
