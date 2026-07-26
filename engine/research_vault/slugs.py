"""engine.research_vault.slugs — deterministic report-id -> URL-slug derivation.

Extracted from scripts/build_research_pages.py so that consumers which only
need the slug mapping (engine/chronicle/adapters.py builds each vault event's
``links.site`` from it) can import it WITHOUT dragging in the page renderer's
jinja2 dependency. The chronicle suite runs in a minimal environment
(``pip install pytest pandas numpy pyarrow pyyaml`` — ci.yml chronicle-suite,
replayed verbatim by the ci-pack orchestrator) and the hourly research-ingest
lane regenerates the chronicle store on a light runner with no jinja2 either;
in both, importing the renderer silently degraded every ``links.site`` to None
and broke gate 1's byte-stable rebuild.

MUST stay stdlib-only (sidecar is json/re/unicodedata): anything heavier
re-creates exactly the failure this module exists to remove. Slugs are public
indexed URLs (``/research/<slug>.html``) — any change here moves them, so the
functions are moved verbatim, not rewritten.
"""
from __future__ import annotations

import re

from .sidecar import clean_title


def _slug(title: str, idv: str, seen: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:70].strip("-")
    suffix = re.sub(r"[^a-z0-9]", "", (idv or "").lower())[-6:] or "report"
    slug = f"{base}-{suffix}" if base else f"report-{suffix}"
    # id suffix is already unique per report; guard the rare collision anyway.
    out, i = slug, 2
    while out in seen:
        out = f"{slug}-{i}"
        i += 1
    seen.add(out)
    return out


def _title(item: dict) -> str:
    """The report title as it may become PUBLIC — repaired, never raw.

    These pages put the title in ``<title>``, ``og:title``, ``twitter:title``, the
    ``<h1>``, the JSON-LD headline and the crawl-hub link text, so an upstream
    defect here is a defect on the single most SEO-weighted element we ship. The
    catalog is repaired at ingest AND on load (engine/research_vault), but this
    builder also runs straight off a committed snapshot a human could edit — so
    it repairs at the render boundary too, fail-soft, by house rule for public
    pages. ``clean_title`` is slug-stable, so this never moves an indexed URL.
    """
    return clean_title(item.get("title")) or (item.get("title") or "").strip()


def slug_map(items: list[dict]) -> dict[str, str]:
    """id -> URL slug for every catalog item (deterministic). Shared with the vault
    build so its cards can link straight to ``research/<slug>.html``."""
    seen: set[str] = set()
    out: dict[str, str] = {}
    for it in items:
        idv = it.get("id") or ""
        if idv:
            out[idv] = _slug(_title(it), idv, seen)
    return out
