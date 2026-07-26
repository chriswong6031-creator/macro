"""engine.research_vault.slugs — deterministic report-id -> URL-slug derivation.

Extracted from scripts/build_research_pages.py so that consumers which only need
the slug mapping (engine/chronicle/adapters.py builds each vault event's
``links.site`` from it) can import it WITHOUT dragging in the page renderer's
import closure.

The concrete failure: that adapter's import is FAIL-SOFT, and the renderer
imported jinja2 at module scope. ci.yml's ``chronicle-suite`` installs only
``pytest pandas numpy pyarrow pyyaml`` (replayed by the ci-pack orchestrator),
so there the ImportError was swallowed and every rebuilt vault event carried
``links.site=None`` — a rebuild in that lane produced genuinely different bytes
than a rebuild anywhere jinja2 exists, which reddened the store-vs-rebuild gate.
The committed store was never corrupted (the nightly runner has jinja2; all 105
committed vault events carry a populated link) — the divergence was in the CI
rebuild, which is precisely what a rebuild gate compares against.

Deferring the renderer's jinja2 import into ``build()`` (#3648) fixed that one
dependency. This module closes the class: whatever the renderer imports at
module scope in future, the adapter no longer sees it.

MUST stay stdlib-only (its one relative import, sidecar, is json/re/unicodedata):
anything heavier re-creates exactly the failure this module exists to remove, and
the fail-soft would hide it again. Slugs are public indexed URLs
(``/research/<slug>.html``) — any change here moves them, so the functions are
moved verbatim, not rewritten.
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
