"""scripts/repair_research_titles.py — heal filename-shaped titles in the COMMITTED
research catalog snapshot, offline.

``engine/research_vault/ingest.py`` repairs these titles on every hourly run, but
it reads and writes the catalog in R2 — so it only heals the repo snapshot the
next time that job runs on a machine with the R2 secrets. This script applies the
SAME resolver (``engine.research_vault.title``) to
``data/research_vault/catalog.json`` using ``data/research_vault/excerpts.json``
as the body text, so the snapshot the nightly render bakes from can be corrected
in a PR without R2 credentials.

The excerpt is the report's cleaned first pages — a subset of the corpus body the
hourly job uses — so this can recover slightly fewer titles than the live pass,
never different ones: both anchor on the same words, and both fall back to the
same cleaned filename. Re-running is a no-op (a repaired title no longer looks
filename-derived).

Usage:
    python -m scripts.repair_research_titles            # rewrite the snapshot
    python -m scripts.repair_research_titles --check    # report only, exit 1 if dirty
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.research_vault import title as title_mod  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "research_vault" / "catalog.json"
EXCERPTS = ROOT / "data" / "research_vault" / "excerpts.json"


def _bodies() -> dict[str, str]:
    """id -> first-pages text, from the committed excerpt snapshot ({} if absent)."""
    try:
        raw = json.loads(EXCERPTS.read_text(encoding="utf-8"))
        blob = raw.get("excerpts") if isinstance(raw, dict) else None
        if not isinstance(blob, dict):
            return {}
        return {k: "\n".join(p for p in v if isinstance(p, str))
                for k, v in blob.items() if isinstance(v, list)}
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        print(f"repair_research_titles: excerpts unusable ({exc}) — cleaning only",
              file=sys.stderr)
        return {}


def repair(catalog: dict, bodies: dict[str, str]) -> list[tuple[str, str, str]]:
    """Repair titles in-place. Returns ``[(id, old, new), …]`` for what changed."""
    changed: list[tuple[str, str, str]] = []
    for item in catalog.get("items") or []:
        old = (item.get("title") or "").strip()
        doc_id = item.get("id") or ""
        if not old or not title_mod.looks_filename_derived(old):
            continue
        new, _src = title_mod.resolve(old, bodies.get(doc_id, ""))
        if new and new != old:
            item["title"] = new
            changed.append((doc_id, old, new))
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair filename-derived research titles")
    ap.add_argument("--check", action="store_true",
                    help="report what would change; exit 1 if anything would")
    a = ap.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    changed = repair(catalog, _bodies())

    for doc_id, old, new in changed:
        print(f"  {doc_id}\n    - {old}\n    + {new}")
    if not changed:
        print("repair_research_titles: nothing to repair")
        return 0
    if a.check:
        print(f"repair_research_titles: {len(changed)} title(s) need repair")
        return 1

    # Byte-for-byte the serialization engine/research_vault/catalog.py writes, so
    # the next hourly snapshot does not churn the file back and forth.
    CATALOG.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print(f"repair_research_titles: repaired {len(changed)} title(s) in {CATALOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
