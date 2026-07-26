"""research_vault.slugs — the canonical catalog-id -> published-URL derivation.

Extracted from ``scripts/build_research_pages.py`` so that NON-RENDERING consumers
can derive the same ``/research/<slug>.html`` URL the site builder publishes without
importing a renderer. That builder does ``from jinja2 import Environment`` at module
scope, so importing it just to call ``slug_map`` dragged jinja2 into the dependency
closure of anything that wanted a URL.

Why that mattered (the defect this module exists to remove): ``engine/chronicle/
adapters.py`` imports this derivation to populate each vault event's ``links.site``,
fail-soft. Its CI lane (``chronicle-suite`` in ci.yml) installs only
``pytest pandas numpy pyarrow pyyaml`` — no jinja2 — so the import raised, the
fail-soft swallowed it, and ALL 105 vault events silently emitted
``links.site: null``. The committed store (built where jinja2 exists) and a
minimal-deps rebuild therefore disagreed on 105 events, which made the byte-stable
rebuild gate (masterplan §0 gate 1) unsatisfiable in the very lane meant to enforce
it — a determinism gate that could only ever pass in a fat environment.

Dependency floor is deliberate and load-bearing: stdlib + ``sidecar.clean_title``
(itself stdlib-only). Adding an import here that a minimal-deps lane lacks would
re-introduce exactly that class of environment-dependent bytes. The engine must not
import the renderer — engine imports engine.

``scripts/build_research_pages.py`` re-exports these under its historical private
names (``_slug``/``_title``) so it stays the single source of truth for the URL it
publishes while this module stays the single source of truth for how it is derived.
"""
from __future__ import annotations

import re

from engine.research_vault.sidecar import clean_title


def report_title(item: dict) -> str:
    """The report title as it may become PUBLIC — repaired, never raw.

    The per-report pages put this in ``<title>``, ``og:title``, ``twitter:title``,
    the ``<h1>``, the JSON-LD headline and the crawl-hub link text, so an upstream
    defect here is a defect on the single most SEO-weighted element we ship. The
    catalog is repaired at ingest AND on load (engine/research_vault), but the
    builder also runs straight off a committed snapshot a human could edit — so it
    repairs at the render boundary too, fail-soft, by house rule for public pages.
    ``clean_title`` is slug-stable, so this never moves an indexed URL.
    """
    return clean_title(item.get("title")) or (item.get("title") or "").strip()


def report_slug(title: str, idv: str, seen: set[str]) -> str:
    """``(title, id)`` -> URL slug, mutating ``seen`` to keep a batch collision-free.

    ``seen`` is threaded (not internal) because uniqueness is a property of the
    whole ordered catalog, not of one item — see :func:`slug_map`.
    """
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


def slug_map(items: list[dict]) -> dict[str, str]:
    """id -> URL slug for every catalog item (deterministic).

    Pure function of the ORDERED items list: collision suffixes depend on what came
    before, so callers must pass the catalog in its committed order to reproduce the
    published URLs. Shared with the vault build so its cards can link straight to
    ``research/<slug>.html``.
    """
    seen: set[str] = set()
    out: dict[str, str] = {}
    for it in items:
        idv = it.get("id") or ""
        if idv:
            out[idv] = report_slug(report_title(it), idv, seen)
    return out
