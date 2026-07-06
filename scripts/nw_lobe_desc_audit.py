"""Audit / regenerate the admin Neural-Web lobe descriptions so they never go stale.

The admin Observatory shows a plain-English description for every Neural Web lobe.
The lobe REGISTRY (list, producer, consumers, freshness) is derived live from
config/synapse.yml, so it is always current. The one hand-curated layer is the
prose (short/full), stored in admin/nw_lobe_descriptions.py. Each entry carries
`src_fp` — a fingerprint of the synapse note it was written from. If a lobe's note
later changes, the fingerprint stops matching and the description is DRIFTED (stale).

Modes:
  --check            List new lobes lacking a description (rendered as auto-summaries)
                     and any DRIFTED descriptions. Exit 1 if any drift (or, with
                     --strict, if anything is missing too). This is the CI guard.
  --update           Regenerate admin/nw_lobe_descriptions.py: keep existing prose,
                     add empty scaffolds for new lobes, drop removed lobes, and
                     re-stamp every src_fp to the CURRENT note (declares "prose now
                     matches the note" — run this AFTER editing prose or adding notes).
  --seed FILE.json   With --update: import prose from a JSON list of
                     {id, short, full} (initial population / bulk refresh).

Usage:
  python scripts/nw_lobe_desc_audit.py --check
  python scripts/nw_lobe_desc_audit.py --update [--seed descriptions.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from admin.neural_web import nw_scoped_lobes, _note_fingerprint  # noqa: E402

MODULE_PATH = ROOT / "admin" / "nw_lobe_descriptions.py"

_HEADER = '''"""Plain-English descriptions for Neural Web lobes (admin Observatory).

AUTO-MANAGED by scripts/nw_lobe_desc_audit.py — do not hand-edit `src_fp`.
Edit a lobe's `short`/`full` prose freely, then run:

    python scripts/nw_lobe_desc_audit.py --update

to re-stamp `src_fp` (the fingerprint of the synapse note the prose describes).

`src_fp` is how the console knows a description is still current: if a lobe's
synapse note changes but this prose isn't refreshed, the fingerprints diverge and
the description is flagged 'stale' in the UI, and tests/test_nw_lobe_descriptions.py
fails CI. A lobe with an empty `short` renders an auto-generated summary until real
prose is written here. Run `--update` (no seed) after adding a lobe or editing prose.
"""
# fmt: off
SCHEMA_VERSION = 1

LOBE_DESCRIPTIONS = {
'''

_FOOTER = "}\n"


def _load_existing() -> dict:
    try:
        from admin.nw_lobe_descriptions import LOBE_DESCRIPTIONS  # noqa: PLC0415
        return dict(LOBE_DESCRIPTIONS)
    except Exception:  # noqa: BLE001
        return {}


def _load_seed(path: str) -> dict:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return {r["id"]: {"short": r.get("short", ""), "full": r.get("full", "")} for r in rows}


def _current_notes() -> dict:
    """{lobe_id: raw_note_string} for every NW-scoped lobe."""
    return {lid: (art.get("notes") or "") for lid, art in nw_scoped_lobes().items()}


def cmd_update(seed_path: str | None) -> int:
    notes = _current_notes()
    existing = _load_existing()
    seed = _load_seed(seed_path) if seed_path else {}

    out: dict[str, dict] = {}
    for lid in sorted(notes):
        prose = seed.get(lid) or existing.get(lid) or {"short": "", "full": ""}
        out[lid] = {
            "short": prose.get("short", ""),
            "full": prose.get("full", ""),
            "src_fp": _note_fingerprint(notes[lid]),
        }

    dropped = sorted(set(existing) - set(notes))
    added = sorted(lid for lid in notes if lid not in existing)

    body = []
    for lid in sorted(out):
        e = out[lid]
        body.append(f"    {json.dumps(lid)}: {{")
        body.append(f"        \"short\": {json.dumps(e['short'], ensure_ascii=False)},")
        body.append(f"        \"full\": {json.dumps(e['full'], ensure_ascii=False)},")
        body.append(f"        \"src_fp\": {json.dumps(e['src_fp'])},")
        body.append("    },")
    MODULE_PATH.write_text(_HEADER + "\n".join(body) + "\n" + _FOOTER, encoding="utf-8")

    scaffolded = sorted(lid for lid, e in out.items() if not e["short"])
    print(f"wrote {MODULE_PATH.relative_to(ROOT)} — {len(out)} lobes "
          f"({len(out) - len(scaffolded)} with prose, {len(scaffolded)} scaffolded)")
    if added:
        print(f"  + added {len(added)}: {', '.join(added)}")
    if dropped:
        print(f"  - dropped {len(dropped)} out-of-scope: {', '.join(dropped)}")
    if scaffolded:
        print(f"  ! {len(scaffolded)} need hand-written prose: {', '.join(scaffolded)}")
    return 0


def cmd_check(strict: bool) -> int:
    notes = _current_notes()
    existing = _load_existing()

    drift, missing, orphan = [], [], []
    for lid, note in notes.items():
        entry = existing.get(lid)
        if not entry or not entry.get("short"):
            missing.append(lid)
        elif entry.get("src_fp") != _note_fingerprint(note):
            drift.append(lid)
    orphan = sorted(set(existing) - set(notes))

    print(f"NW lobes: {len(notes)} · with prose: {len(notes) - len(missing)} · "
          f"drifted: {len(drift)} · missing: {len(missing)} · orphaned: {len(orphan)}")
    if drift:
        print("\nDRIFTED (note changed since prose was written — refresh prose, then --update):")
        for lid in sorted(drift):
            print(f"  • {lid}")
    if missing:
        print("\nMISSING prose (rendered as auto-summaries; add prose in admin/nw_lobe_descriptions.py):")
        for lid in sorted(missing):
            print(f"  • {lid}")
    if orphan:
        print("\nORPHANED (in module but no longer a lobe — run --update to drop):")
        for lid in orphan:
            print(f"  • {lid}")

    fail = bool(drift) or (strict and bool(missing))
    if fail:
        print("\nFIX: refresh prose in admin/nw_lobe_descriptions.py, then run "
              "`python scripts/nw_lobe_desc_audit.py --update`.")
        return 1
    print("\nOK — no drift." + ("" if not missing else f" ({len(missing)} lobes on auto-summaries.)"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit/regenerate NW lobe descriptions.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="report drift/missing (CI guard)")
    g.add_argument("--update", action="store_true", help="regenerate the module + re-stamp fingerprints")
    ap.add_argument("--seed", metavar="FILE.json", help="with --update: import prose from a JSON list")
    ap.add_argument("--strict", action="store_true", help="with --check: also fail on missing prose")
    args = ap.parse_args()
    if args.update:
        return cmd_update(args.seed)
    return cmd_check(args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
