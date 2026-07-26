"""build_research_pages.py — per-report SEO landing pages (RV programmatic SEO).

For every report in the vault catalog we generate ``site/research/<slug>.html``: a
lightweight, crawlable landing page that surfaces the report's TITLE, institution,
date, rating, tickers/themes, a ONE-LINE public snippet and the public FIRST-PAGES
EXCERPT — with the full summary + the original PDF behind the Pro gate. JSON-LD
(``Article`` with ``isAccessibleForFree:false`` + ``hasPart``) marks the page as
paywalled so Google indexes the public part without it counting as cloaking (the
sanctioned news/research paywall pattern); the excerpt sits OUTSIDE ``.rr-gate``,
so that markup stays truthful.

The play: when someone Googles an exact report title, our dedicated page is a
precise match — and usually the only host — so we rank; they land on the teaser +
a paywall and some convert. The excerpt widens that to EXACT-QUOTE searches: a
reader who Googles a sentence a news blog lifted from the PDF matches our page
too. Its text comes from ``data/research_vault/excerpts.json``, a snapshot the
hourly ingest commits (engine/research_vault/excerpt.py) precisely so this render
never needs R2. Also emits a ``/research/index.html`` crawl hub and merges
``/research/`` entries into ``site/sitemap.xml`` (preserving every other section,
exactly like build_ticker_pages does for ``/stocks/``).

Called at the end of ``build_research_vault.build()`` so it rides the nightly vault
build — no extra workflow/dag step. Fully static + additive: a missing/empty
catalog yields zero pages and never breaks the build. Source-only; the nightly's
optimize_assets pass does the ?v/externalise post-processing on the emitted files.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# The id->URL derivation lives in a jinja2-free leaf module so non-rendering
# consumers (engine/chronicle/adapters.py, whose CI lane installs no jinja2) can
# reproduce the published URL without importing this renderer. Re-exported under
# the historical private names so every call site below is unchanged.
from engine.research_vault.slugs import (
    report_slug as _slug,
    report_title as _title,
    slug_map,  # noqa: F401 — re-export: scripts/build_research_vault.py + tests call rp.slug_map
)

log = logging.getLogger("build_research_pages")

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"
RESEARCH_DIR = SITE / "research"
SITEMAP = SITE / "sitemap.xml"
EXCERPTS = ROOT / "data" / "research_vault" / "excerpts.json"

# Render-side re-cap on the published excerpt. engine/research_vault/excerpt.py
# already caps at 4200 when it derives, but excerpts.json is committed repo data
# that a human could hand-edit — this bounds what a bad/edited snapshot can push
# outside the paywall, with a little headroom so a legitimate snapshot is never
# clipped by rounding.
EXCERPT_RENDER_CAP = 4600

try:  # canonical base ("https://www.mastermind-x.com"), trailing slash stripped
    from lib.seo import SITE_BASE as _SITE_BASE  # noqa: E402
    CANONICAL_BASE = _SITE_BASE.rstrip("/")
except Exception:  # noqa: BLE001 — never let a missing import break the build
    CANONICAL_BASE = "https://www.mastermind-x.com"

_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_STAMP = {"buy": ("BUY", "buy"), "sell": ("SELL", "sell"), "independent": ("IND", "indep")}
_EMPTY_XML = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>')


def _e(s) -> str:
    return _html.escape("" if s is None else str(s), quote=True)


def _fmt_date(iso: str) -> str:
    """'2026-07-24T…' -> 'Jul 24, 2026'; blank/garbage -> ''."""
    d = (iso or "").split("T")[0]
    if not d or d.count("-") < 2:
        return ""
    y, m, dd = d.split("-")[:3]
    try:
        return f"{_MON[int(m) - 1]} {int(dd)}, {y}"
    except (ValueError, IndexError):
        return ""


def _monogram(inst: str) -> str:
    inst = (inst or "").strip()
    if not inst or inst == "Unknown":
        return "?"
    parts = [p for p in inst.replace(".", " ").split() if p]
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _clean(s: str) -> str:
    """Strip markdown emphasis + collapse whitespace for a plain-text snippet."""
    s = re.sub(r"[*_`]+", "", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _trunc(s: str, n: int) -> str:
    s = _clean(s)
    if len(s) <= n:
        return s
    return s[:n].rsplit(" ", 1)[0].rstrip(" ,;:·—-") + "…"


def _norm(item: dict) -> dict:
    inst = (item.get("institution") or "Unknown").strip() or "Unknown"
    side = (item.get("side") or "independent").lower()
    pts = [p for p in (item.get("summary_points") or []) if _clean(p)]
    stamp_txt, stamp_cls = _STAMP.get(side, ("IND", "indep"))
    return {
        "id": item.get("id") or "",
        "title": _title(item) or "Untitled research",
        "inst": inst,
        "mono": _monogram(inst),
        "side": side,
        "stamp": stamp_txt,
        "stamp_cls": stamp_cls,
        "desk": item.get("desk") or "",
        "pub_iso": (item.get("published_at") or ""),
        "date_disp": _fmt_date(item.get("published_at") or ""),
        "pages": item.get("pages") or 0,
        "tags": [t for t in (item.get("tags") or []) if t][:6],
        "tickers": [t for t in (item.get("tickers") or []) if t][:6],
        "teaser": _trunc(pts[0], 220) if pts else "",
        "n_points": len(pts),
    }


def _related(cur: dict, all_norm: list[dict], slug_by_id: dict[str, str]) -> list[dict]:
    """Up to 4 related reports: same institution first, then shared tags."""
    out, seen = [], {cur["id"]}
    for r in all_norm:
        if r["id"] in seen or r["inst"] != cur["inst"]:
            continue
        seen.add(r["id"]); out.append(r)
        if len(out) >= 4:
            break
    if len(out) < 4:
        tagset = set(cur["tags"])
        for r in all_norm:
            if r["id"] in seen or not (tagset & set(r["tags"])):
                continue
            seen.add(r["id"]); out.append(r)
            if len(out) >= 4:
                break
    return [{"title": r["title"], "inst": r["inst"], "slug": slug_by_id[r["id"]]} for r in out]


def _jsonld(n: dict, canonical: str, meta_desc: str) -> str:
    obj = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": n["title"][:110],
        "author": {"@type": "Organization", "name": n["inst"]},
        "publisher": {
            "@type": "Organization", "name": "Mastermind",
            "logo": {"@type": "ImageObject", "url": f"{CANONICAL_BASE}/apple-touch-icon.png"},
        },
        "description": meta_desc,
        "url": canonical,
        "isAccessibleForFree": False,
        "hasPart": {
            "@type": "WebPageElement",
            "isAccessibleForFree": False,
            "cssSelector": ".rr-gate",
        },
    }
    if n["pub_iso"]:
        obj["datePublished"] = n["pub_iso"]
    if n["tickers"]:
        obj["about"] = [{"@type": "Corporation", "tickerSymbol": t} for t in n["tickers"]]
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


# ---------------------------------------------------------------------------
# public first-pages excerpts (committed hourly by scripts/ingest_research.py)
# ---------------------------------------------------------------------------

def _cap_paras(paras: list[str]) -> list[str]:
    """Truncate a paragraph list so its total stays under EXCERPT_RENDER_CAP."""
    out: list[str] = []
    total = 0
    for p in paras:
        if total + len(p) > EXCERPT_RENDER_CAP:
            break
        out.append(p)
        total += len(p)
    if not out and paras:                     # one oversized paragraph: hard-slice
        out = [paras[0][:EXCERPT_RENDER_CAP]]
    return out


def _load_excerpts() -> dict[str, list[str]]:
    """id -> public excerpt paragraphs, from the committed snapshot.

    Returns ``{}`` on ANY failure — missing file (the normal state before the
    first hourly run commits one), bad JSON, wrong shape. An absent snapshot must
    render exactly today's page, so this can never be a build dependency.
    Shape is validated rather than trusted: the file is repo data.
    """
    try:
        raw = json.loads(EXCERPTS.read_text(encoding="utf-8"))
        blob = raw.get("excerpts") if isinstance(raw, dict) else None
        if not isinstance(blob, dict):
            return {}
        out: dict[str, list[str]] = {}
        for k, v in blob.items():
            if not isinstance(k, str) or not isinstance(v, list):
                continue
            paras = _cap_paras([p for p in v if isinstance(p, str) and p.strip()])
            if paras:
                out[k] = paras
        return out
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001 — never let the snapshot break the build
        log.warning("research pages: excerpts snapshot unusable (%s) — rendering without", exc)
        return {}


# ---------------------------------------------------------------------------
# sitemap merge — preserve every non-/research/ url, replace /research/ block
# ---------------------------------------------------------------------------

def prune_stale(keep: set[str], names: list[str], max_share: float = 0.34) -> list[str]:
    """Which of ``names`` to delete so ``site/research/`` holds only ``keep``.

    A page's filename is ``slug(title)-<id suffix>.html``, so correcting a report's
    title MOVES its page: without a prune, the old URL survives as a second live
    copy of the same report under the wrong title — the exact string these pages
    exist to stop competing with. Pages are fully re-rendered from the catalog on
    every run, so anything not in ``keep`` is unreachable.

    Guard: a wipe that large is a truncated catalog, not 20 renamed reports, so a
    prune touching more than ``max_share`` of the directory is refused wholesale
    (the caller logs it). Pure — the caller does the unlinking.
    """
    stale = sorted(n for n in names if n.endswith(".html") and n not in keep)
    if not stale or not names:
        return []
    if len(stale) > max(1, int(len(names) * max_share)):
        return []
    return stale


def build_sitemap(existing_xml: str, entries: list[dict]) -> str:
    kept = [ln for ln in existing_xml.splitlines()
            if not (ln.strip().startswith("<url>") and "/research/" in ln)]
    base = "\n".join(kept).rstrip()
    if base.endswith("</urlset>"):
        base = base[: -len("</urlset>")].rstrip()
    parts = [base]
    for e in entries:
        row = f'  <url><loc>{_e(e["loc"])}</loc>'
        if e.get("lastmod"):
            row += f'<lastmod>{_e(e["lastmod"])}</lastmod>'
        row += f'<changefreq>{e.get("changefreq", "weekly")}</changefreq>'
        row += f'<priority>{e.get("priority", 0.5)}</priority></url>'
        parts.append(row)
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# stale-page prune
# ---------------------------------------------------------------------------

def _prune_stale(keep: set[str]) -> int:
    """Delete ``site/research/*.html`` whose slug is no longer in the catalog.

    A report whose title is repaired can land on a new slug, and the builder only
    ever WRITES — so the old file would survive as a self-canonical near-duplicate
    of its own replacement: nothing links to it (the sitemap and crawl hub are
    rebuilt from ``keep``) yet Google still holds both. The directory is
    exclusively ours, so anything outside ``keep`` is by definition unpublished.

    Bounded on purpose: if the catalog would orphan more than a quarter of the
    directory we refuse and warn instead. A degraded/partial catalog must never be
    able to mass-delete live pages — the pages are cheap to regenerate, an
    unexplained de-indexing is not.
    """
    try:
        present = {p.name for p in RESEARCH_DIR.glob("*.html")}
    except OSError:  # directory vanished mid-build — nothing to prune
        return 0
    stale = sorted(present - keep)
    if not stale:
        return 0
    if len(stale) > max(4, len(present) // 4):
        # Bare print, NOT a logger call: GitHub only parses a workflow command when
        # "::" STARTS the line, and this module's logging format prefixes every
        # record ("WARNING ::warning ..."), which silently drops the annotation.
        print(f"::warning title=research_pages::refusing to prune {len(stale)}/{len(present)} "
              f"/research/ pages — catalog looks partial (first: {', '.join(stale[:5])})",
              flush=True)
        return 0
    for name in stale:
        try:
            (RESEARCH_DIR / name).unlink()
        except OSError as exc:  # noqa: PERF203 — per-file, never fatal
            log.warning("research pages: could not prune %s (%s)", name, exc)
    log.info("research pages: pruned %d stale page(s): %s", len(stale), ", ".join(stale))
    return len(stale)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build(catalog: dict | None = None) -> int:
    """Render every report landing page + the crawl hub + merge the sitemap.

    ``catalog`` is the public catalog dict (as build_research_vault projects it);
    if None we read the committed snapshot. Returns the number of pages written.
    """
    if catalog is None:
        try:
            from scripts.build_research_vault import _public_catalog, load_catalog
            catalog = _public_catalog(load_catalog())
        except Exception as exc:  # noqa: BLE001
            log.warning("research pages: catalog load failed (%s) — skipping", exc)
            return 0

    items = [it for it in (catalog.get("items") or []) if isinstance(it, dict) and it.get("id")]
    if not items:
        log.info("research pages: empty catalog — no report pages to build")
        return 0

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=True, trim_blocks=True, lstrip_blocks=True)
    tmpl = env.get_template("research_report.html.j2")
    idx_tmpl = env.get_template("research_index.html.j2")

    all_norm = [_norm(it) for it in items]
    seen: set[str] = set()
    slug_by_id: dict[str, str] = {}
    for n, it in zip(all_norm, items):
        s = (it.get("slug") or "").strip()          # reuse the vault build's slug if injected
        slug_by_id[n["id"]] = s or _slug(n["title"], n["id"], seen)
        seen.add(slug_by_id[n["id"]])

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    from lib.pages import write_page  # noqa: PLC0415

    excerpts = _load_excerpts()                 # {} when the snapshot is absent
    sitemap_entries: list[dict] = []
    written = 0
    for n in all_norm:
        slug = slug_by_id[n["id"]]
        canonical = f"{CANONICAL_BASE}/research/{slug}.html"
        date_bit = f" · {n['date_disp']}" if n["date_disp"] else ""
        meta_desc = _trunc(
            f"{n['inst']} institutional research{date_bit}. "
            f"{n['teaser'] or 'Read the full report on Mastermind.'}", 158)
        page = tmpl.render(
            n=n, canonical=canonical, meta_desc=meta_desc,
            jsonld_str=_jsonld(n, canonical, meta_desc),
            related=_related(n, all_norm, slug_by_id),
            excerpt_paras=excerpts.get(n["id"]) or [],
            site_base=CANONICAL_BASE,
        )
        write_page(RESEARCH_DIR / f"{slug}.html", page)
        written += 1
        sitemap_entries.append({
            "loc": canonical,
            "lastmod": (n["pub_iso"].split("T")[0] or None) if n["pub_iso"] else None,
            "changefreq": "weekly", "priority": 0.5,
        })

    # crawl hub: /research/index.html — links to every report, grouped by desk
    by_inst: dict[str, list[dict]] = {}
    for n in all_norm:
        by_inst.setdefault(n["inst"], []).append(
            {"title": n["title"], "slug": slug_by_id[n["id"]], "date_disp": n["date_disp"]})
    groups = [{"inst": k, "reports": v} for k, v in
              sorted(by_inst.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    idx_html = idx_tmpl.render(groups=groups, total=len(all_norm),
                               canonical=f"{CANONICAL_BASE}/research/index.html",
                               site_base=CANONICAL_BASE)
    write_page(RESEARCH_DIR / "index.html", idx_html)
    _prune_stale({f"{s}.html" for s in slug_by_id.values()} | {"index.html"})
    sitemap_entries.insert(0, {
        "loc": f"{CANONICAL_BASE}/research/index.html",
        "lastmod": None, "changefreq": "daily", "priority": 0.6})

    # drop pages whose report has been retitled (new slug) or left the catalog —
    # otherwise the old URL stays live under the stale title (see prune_stale).
    try:
        keep = {f"{s}.html" for s in slug_by_id.values()} | {"index.html"}
        names = [p.name for p in RESEARCH_DIR.glob("*.html")]
        orphans = [n for n in names if n not in keep]
        stale = prune_stale(keep, names)
        for name in stale:
            (RESEARCH_DIR / name).unlink()
        if stale:
            log.info("research pages: pruned %d stale page(s): %s", len(stale),
                     ", ".join(stale[:5]) + ("…" if len(stale) > 5 else ""))
        elif orphans:
            # Bare print: an annotation behind logging's "%(levelname)s " prefix
            # never parses as one.
            print(f"::warning title=research pages::refusing to prune {len(orphans)} "
                  f"stale /research/ page(s) — too many for one run; the catalog may "
                  f"be short. Left in place.")
    except Exception as exc:  # noqa: BLE001 — a stale file never breaks the build
        log.warning("research pages: prune failed (%s)", exc)

    # merge into the real sitemap (preserving /stocks/ and everything else)
    try:
        existing = SITEMAP.read_text(encoding="utf-8") if SITEMAP.exists() else _EMPTY_XML
        SITEMAP.write_text(build_sitemap(existing, sitemap_entries), encoding="utf-8")
        log.info("research pages: sitemap updated (%d /research/ entries)", len(sitemap_entries))
    except Exception as exc:  # noqa: BLE001 — bare print: see the prune block above
        print(f"::warning title=sitemap::research sitemap merge failed: {exc}", flush=True)

    log.info("research pages: wrote %d report pages + index", written)
    return written


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
