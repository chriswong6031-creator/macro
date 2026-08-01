"""research_vault.catalog — the public-safe catalog.json list metadata (§6).

``research_vault.catalog.v1`` shape:
    { "schema": "research_vault.catalog.v1", "generated_at": "…",
      "count": N, "institutions": [...], "items": [ {item}, … ] }

Items are the public-safe subset of a normalized sidecar (NO body text — search
lives in corpus.sqlite). Items are sorted newest-first by ``published_at``. This
is the ONLY research artifact that carries publicly-visible content; the PDFs
themselves are never public.

The catalog lives in the store at ``research_vault/catalog.json`` and is also
snapshotted to the repo at ``data/research_vault/catalog.json`` by the ingest
job (so the nightly render can SSR-bake without R2). Writes are atomic. Pure over
its ``catalog`` dict argument; only :func:`load`/:func:`write` touch the store.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from engine.research_vault.sidecar import clean_title

log = logging.getLogger("research_vault.catalog")

SCHEMA = "research_vault.catalog.v1"
CATALOG_KEY = "research_vault/catalog.json"

# The public-safe fields carried on each catalog item (body is deliberately absent).
# MIRRORED in scripts/build_research_vault.py — the SSR bake projects the same
# subset, and a test asserts the two tuples stay identical.
_ITEM_FIELDS = (
    "id", "title", "institution", "side", "desk", "published_at",
    "summary_points", "tags", "tickers", "top_pick", "pages", "language",
    "needs_metadata",
)

# Fields whose emptiness is a real gap worth reporting (see :func:`coverage`).
# Excluded on purpose:
#   - identity fields (id/title/institution/side/published_at) — every one has a
#     fallback, so they are populated by construction;
#   - booleans (top_pick/needs_metadata) — False is a meaning, not a gap;
#   - ``language`` — sidecar.normalize DEFAULTS it to "en", so it reads 100%
#     populated whether or not anything measured it. Counting it would manufacture
#     exactly the vacuous green this function exists to expose. (Measuring the
#     script from the body text is a follow-on, not a claim we make today.)
_COVERAGE_FIELDS = (
    "summary_points", "desk", "tags", "tickers", "pages",
)

_EMPTY_VALUES = (None, "", [], {}, ())


def empty() -> dict:
    """A fresh empty catalog document."""
    return {"schema": SCHEMA, "generated_at": "", "count": 0,
            "institutions": [], "items": []}


def _now_iso(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).isoformat()


def load(store) -> dict:
    """Load the catalog from the store, or an empty one if absent/unparsable.

    Never raises — a corrupt/missing catalog degrades to :func:`empty` so a bad
    prior write can be healed by the next ingest rather than wedging the pipeline.
    """
    raw = store.get_bytes(CATALOG_KEY)
    if not raw:
        return empty()
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict) or not isinstance(obj.get("items"), list):
            log.warning("catalog malformed — starting fresh")
            return empty()
        _heal_titles(obj)
        return obj
    except Exception as e:  # noqa: BLE001 — corrupt catalog: rebuild from empty
        log.warning("catalog parse failed (%s) — starting fresh", e)
        return empty()


def _heal_titles(catalog: dict) -> int:
    """Repair already-PUBLISHED titles in place; returns the number changed.

    Ingest is receipt-idempotent, so a document already in the vault never
    re-normalizes — a title defect fixed in :mod:`sidecar` would otherwise stay
    frozen in the catalog forever for every doc ingested before the fix. Healing
    on load means the next hourly run republishes those rows repaired, with no
    receipt surgery and no re-download. Idempotent: a healed catalog re-heals to
    itself and the row-identifying ``id`` is never touched.
    """
    n = 0
    for it in catalog.get("items") or []:
        if not isinstance(it, dict):
            continue
        old = it.get("title")
        if not isinstance(old, str) or not old:
            continue
        new = clean_title(old)
        if new and new != old:
            it["title"] = new
            n += 1
    if n:
        log.info("catalog: repaired %d truncated/deduped title(s)", n)
    return n


def _public_item(item: dict) -> dict:
    """Project a normalized sidecar item to the public-safe catalog subset."""
    pub = {k: item.get(k) for k in _ITEM_FIELDS}
    # Belt-and-braces: normalize() already cleans, but the catalog is the last
    # stop before a title becomes public (page <title>, og:title, the crawl hub).
    pub["title"] = clean_title(pub.get("title")) or (pub.get("title") or "")
    return pub


def coverage(catalog: dict) -> dict[str, dict]:
    """Per-field fill rate over the catalog's items.

    Returns ``{field: {"filled": int, "total": int, "pct": float}}`` for each of
    :data:`_COVERAGE_FIELDS`. ``total`` is the item count, so an empty catalog
    yields 0% everywhere rather than a division error.

    Why this exists: ``needs_metadata`` only trips on a bad-JSON sidecar or a
    fallen-back title/institution, so it reported 0/60 — a clean bill of health —
    while ``desk``, ``tags``, ``tickers`` and ``pages`` were empty on every single
    document in the vault. A flag that cannot see the fields it is supposed to
    guard is vacuous green: PRESENCE of a schema field is not COVERAGE of it.
    Never raises.
    """
    items = [it for it in (catalog.get("items") or []) if isinstance(it, dict)]
    total = len(items)
    out: dict[str, dict] = {}
    for field in _COVERAGE_FIELDS:
        filled = sum(1 for it in items if it.get(field) not in _EMPTY_VALUES)
        out[field] = {
            "filled": filled,
            "total": total,
            "pct": (100.0 * filled / total) if total else 0.0,
        }
    return out


def public_summary(catalog: dict, now: datetime | None = None) -> dict[str, Any]:
    """Return public-safe whole-vault aggregates for preview and full clients.

    The public catalog route deliberately truncates ``items`` to three reports for
    non-Pro readers. Deriving hero totals from that slice makes "3 reports / 3
    desks" look like a whole-vault fact. These aggregates are computed from the
    complete catalog before truncation and reveal no report body or gated summary.
    ``now`` is injectable so the rolling seven-day boundary is deterministic in
    tests and matches the client's UTC-date comparison.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff = (current.astimezone(timezone.utc) - timedelta(days=7)).date().isoformat()
    items = [item for item in (catalog.get("items") or []) if isinstance(item, dict)]
    week = [
        item for item in items
        if str(item.get("published_at") or "").split("T", 1)[0] >= cutoff
    ]

    week_desks = {
        str(item.get("institution") or "").strip()
        for item in week
        if str(item.get("institution") or "").strip() not in ("", "Unknown")
    }
    institution_counts: dict[str, int] = {}
    for item in items:
        name = str(item.get("institution") or "").strip()
        if name and name != "Unknown":
            institution_counts[name] = institution_counts.get(name, 0) + 1

    theme_pool = week if week else items
    theme_counts: dict[str, int] = {}
    top_theme = ""
    top_count = 0
    for item in theme_pool:
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        for raw in tags:
            theme = str(raw or "").strip()
            if not theme:
                continue
            theme_counts[theme] = theme_counts.get(theme, 0) + 1
            if theme_counts[theme] > top_count:
                top_theme, top_count = theme, theme_counts[theme]

    institutions = [
        {"name": name, "count": count}
        for name, count in sorted(
            institution_counts.items(), key=lambda pair: (-pair[1], pair[0])
        )
    ]
    return {
        "total": len(items),
        "new_this_week": len(week),
        "desks_this_week": len(week_desks),
        "highlighted": sum(1 for item in items if item.get("top_pick")),
        "most_covered_theme": top_theme,
        "institutions": institutions,
    }


def coverage_lines(cov: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Render :func:`coverage` for a log, plus the list of DEAD fields.

    A field is "dead" when the catalog is non-empty and nothing fills it — the
    condition that says a contract field exists but no producer ever writes it.
    Returns ``(lines, dead_fields)``.
    """
    lines: list[str] = []
    dead: list[str] = []
    for field, c in sorted(cov.items()):
        lines.append(f"  {field:16s} {c['filled']:5d}/{c['total']:<5d} {c['pct']:5.1f}%")
        if c["total"] and not c["filled"]:
            dead.append(field)
    return lines, dead


def upsert_item(catalog: dict, item: dict) -> dict:
    """Insert/replace ``item`` (by id) into ``catalog`` and return it.

    Pure over the passed dict (mutates + returns it). Re-sorts newest-first and
    recomputes ``count`` + ``institutions``. An item replacing an existing id
    keeps a single row (idempotent re-ingest).
    """
    items = catalog.setdefault("items", [])
    pub = _public_item(item)
    doc_id = pub.get("id")
    items[:] = [it for it in items if it.get("id") != doc_id]
    items.append(pub)
    _reindex(catalog)
    return catalog


def _reindex(catalog: dict) -> None:
    items = catalog.get("items", [])
    # Newest-first; missing/blank dates sort last (empty string < any date).
    items.sort(key=lambda it: (it.get("published_at") or ""), reverse=True)
    catalog["schema"] = SCHEMA
    catalog["count"] = len(items)
    insts = sorted({(it.get("institution") or "").strip()
                    for it in items if (it.get("institution") or "").strip()})
    catalog["institutions"] = insts


def write(store, catalog: dict, now: datetime | None = None) -> bytes:
    """Stamp ``generated_at``, serialize, and atomically put to the store.

    Returns the serialized bytes (so the caller can also snapshot them to the
    repo). Serialization mirrors the atomic-JSON idiom (indent=2,
    ensure_ascii=False, trailing newline). Fails-open: a store put failure is
    logged; the bytes are still returned.
    """
    _reindex(catalog)
    catalog["generated_at"] = _now_iso(now)
    data = (json.dumps(catalog, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    ok = store.put_bytes(CATALOG_KEY, data, "application/json")
    if not ok:
        log.warning("catalog put to store failed (bytes still returned)")
    return data


def serialize(catalog: dict, now: datetime | None = None) -> bytes:
    """Serialize without a store write (for the repo snapshot lane)."""
    _reindex(catalog)
    catalog["generated_at"] = _now_iso(now)
    return (json.dumps(catalog, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
