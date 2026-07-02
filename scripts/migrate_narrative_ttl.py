"""W3.4 — Narrative TTL / staleness migration.

Stamps every per-entry record in the three narrative families with:
  - as_of      : ISO-8601 date (sourced from the file-level note / version field)
  - ttl_days   : integer (default 90 for 'now' fields per D3_FLAGSHIPS §5.2)
  - archetype_check : optional falsifier-DSL expression or null (null = manual-TTL only)
  - prev_revision   : null (initialised to null; revision tracking starts post-migration)

SAFE: additive only — any field already present is NOT overwritten.
IDEMPOTENT: re-running on an already-migrated file is a no-op.

Migration order:
  1. data/sector_cycles/narratives.price_c4414dcb.json      (sectors + baskets)
  2. data/country_cycles/narratives.price_c4414dcb.json     (sectors + baskets)
  3. data/china_sector_cycles/narratives.json               (sectors + baskets)

Archetype mappings (where a DSL falsifier can act as mechanism-check):
  - Sector 'semis' (smh, b-semis, b-ai_compute): archetype_check → "semis.top_2026.v1"
  - Sector 'housing' (xlre, b-housing): archetype_check → "housing.bubble_peak.v1"
  - Sector 'business cycle' (spy, xlf, b-diversified): archetype_check → "business.cycle_trough.v1"
  - Sector 'energy' (xle, b-energy, b-oil): archetype_check → "oil.regime_shift.v1"
  - Sector 'copper/materials' (xlb, b-copper): archetype_check → "copper.trough_in.v1"
  - Basket 'gold' (b-gold): archetype_check → "gold.bull_intact.v1"
  - Basket 'bitcoin' (b-btc*): archetype_check → "bitcoin.cycle_position.v1"
  - Basket 'credit' (b-credit*, b-bonds*): archetype_check → "credit.spread_regime.v1"
  - Country 'shipping' (b-shipping): archetype_check → "shipping.bdi_cycle.v1"

Usage:
    python -m scripts.migrate_narrative_ttl [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger("migrate_narrative_ttl")

ROOT = config.ROOT
DEFAULT_TTL_DAYS = 90

# ── date extraction ───────────────────────────────────────────────────────────

_DATE_RE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")


def _extract_date(text: str | None) -> str | None:
    """Pull the first ISO date from a free-text string (note/version fields)."""
    if not text:
        return None
    m = _DATE_RE.search(text)
    return m.group(1) if m else None


def _file_date(doc: dict, fname: str) -> str:
    """Best-effort extraction of the authoring date from a narrative file."""
    # sector_cycles / country_cycles: check 'note' field for date
    note = doc.get("note", "")
    d = _extract_date(note)
    if d:
        return d
    # china_sector_cycles: 'version' field "2026-06-28-15y"
    version = doc.get("version", "")
    d = _extract_date(version)
    if d:
        return d
    # last fallback: today
    from datetime import date
    return date.today().isoformat()


# ── archetype check mapping ───────────────────────────────────────────────────
# Maps a series/basket id (lower-case) → falsifier id used as archetype_check.
# The falsifier's DSL is evaluated by falsifier_tripwires._eval_expr; a failing
# check renders "mechanism check failing since {date}" on the overlay.
# Keys are matched as substrings of the series_id (after lower-casing).
_ARCHETYPE_MAP: list[tuple[str, str]] = [
    # Keys are the RAW series/basket id as they appear in the JSON (no "b-" prefix —
    # that prefix is added by the builder when flattening into the NARR map).
    # Matched by exact prefix on the lower-cased series_id.
    # ── commodities / hard assets ─────────────────────────────────
    ("uranium_miners",      "uranium.supply_squeeze.v1"),
    ("critical_minerals",   "copper.trough_in.v1"),
    # ── energy ────────────────────────────────────────────────────
    ("xle",                 "oil.regime_shift.v1"),
    ("energy_complex",      "oil.regime_shift.v1"),
    ("us_sector_energy",    "oil.regime_shift.v1"),
    # ── semis / AI compute ────────────────────────────────────────
    ("ai_semiconductors",   "semis.top_2026.v1"),
    ("memory_storage",      "semis.top_2026.v1"),
    ("semicap_equipment",   "semis.top_2026.v1"),
    ("ai_infra",            "semis.top_2026.v1"),
    # ── housing / real estate ─────────────────────────────────────
    ("xlre",                "housing.bubble_peak.v1"),
    ("housing",             "housing.bubble_peak.v1"),
    ("us_sector_realestate","housing.bubble_peak.v1"),
    # ── credit / fixed income ─────────────────────────────────────
    ("regional_banks",      "credit.spread_regime.v1"),
    ("insurance",           "credit.spread_regime.v1"),
    ("payments_fintech",    "credit.spread_regime.v1"),
    ("us_sector_financials","credit.spread_regime.v1"),
    ("xlf",                 "credit.spread_regime.v1"),
    # ── business cycle / broad market ─────────────────────────────
    ("industrial_distribution", "business.cycle_trough.v1"),
    ("reshoring",           "business.cycle_trough.v1"),
    ("xli",                 "business.cycle_trough.v1"),
    ("us_sector_industrials","business.cycle_trough.v1"),
    # ── shipping (country / thematic) ─────────────────────────────
    # (country_cycles baskets keyed verbatim, no b- prefix)
    ("shipping",            "shipping.bdi_cycle.v1"),
]


def _archetype_for(series_id: str) -> str | None:
    """Return the falsifier id that acts as archetype_check, or None.

    series_id is the RAW key from the JSON (no b- prefix).
    Matched by exact prefix on lower-cased id to handle minor suffix variants."""
    sid = series_id.lower()
    for prefix, fid in _ARCHETYPE_MAP:
        if sid == prefix or sid.startswith(prefix + "_") or sid.startswith(prefix + "-"):
            return fid
    return None


# ── per-entry stamping ────────────────────────────────────────────────────────

def _stamp_entry(entry: dict, series_id: str, as_of: str, *, dry_run: bool = False) -> bool:
    """Add TTL fields to an entry in-place.  Returns True if any field was added or updated.

    Rules:
    - as_of / ttl_days / prev_revision: additive only (skip if key already present)
    - archetype_check: always recomputed from the _ARCHETYPE_MAP so the map stays
      authoritative (allows adding new mappings without a full reset); only counts as
      "changed" if the value differed."""
    changed = False
    # additive-only fields
    for key, default in [
        ("as_of",         as_of),
        ("ttl_days",      DEFAULT_TTL_DAYS),
        ("prev_revision", None),
    ]:
        if key not in entry:
            if not dry_run:
                entry[key] = default
            changed = True
    # archetype_check: always authoritative from map
    new_arch = _archetype_for(series_id)
    if entry.get("archetype_check") != new_arch:
        if not dry_run:
            entry["archetype_check"] = new_arch
        changed = True
    return changed


def _migrate_file(path: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Migrate one narrative file.  Returns (n_entries, n_changed)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    as_of = _file_date(doc, path.name)
    log.info("%s: as_of=%s", path.name, as_of)

    n_entries = 0
    n_changed = 0

    for group in ("sectors", "baskets"):
        for series_id, entry in (doc.get(group) or {}).items():
            if not isinstance(entry, dict):
                continue
            n_entries += 1
            changed = _stamp_entry(entry, series_id, as_of, dry_run=dry_run)
            if changed:
                n_changed += 1

    if n_changed and not dry_run:
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("%s: %d entries, %d stamped%s", path.name, n_entries, n_changed,
             " [DRY RUN]" if dry_run else "")
    return n_entries, n_changed


# ── main ──────────────────────────────────────────────────────────────────────

NARRATIVE_FILES = [
    ROOT / "data" / "sector_cycles"       / "narratives.price_c4414dcb.json",
    ROOT / "data" / "country_cycles"      / "narratives.price_c4414dcb.json",
    ROOT / "data" / "china_sector_cycles" / "narratives.json",
    # china also has an epoch-keyed file; stamp it too if present
    ROOT / "data" / "china_sector_cycles" / "narratives.price_f224a71d.json",
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="Print changes without writing files")
    args = p.parse_args(argv)

    total_entries = total_changed = 0
    for path in NARRATIVE_FILES:
        if not path.exists():
            log.warning("skip missing: %s", path)
            continue
        ne, nc = _migrate_file(path, dry_run=args.dry_run)
        total_entries += ne
        total_changed += nc

    action = "would stamp" if args.dry_run else "stamped"
    log.info("Total: %d entries, %s %d with TTL fields", total_entries, action, total_changed)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
