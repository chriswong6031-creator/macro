#!/usr/bin/env python3
"""CI lint: any desk brief rendering a conviction badge must carry a provenance PASSPORT (#41).

Audit #41: desk cards and the Calibration Hub display precise-looking conviction badges whose
measured basis is n=0 — indistinguishable from an earned number. The fix (Masterplan §W4) is a
SHARED render helper + a build check, not per-page patches. engine.passport is the helper; this
is the check.

Invariant enforced: every rendered desk-brief JSON (schema in _DESK_SCHEMAS) that surfaces a
directional conviction MUST include a top-level ``passport`` block whose ``state`` is one of
engine.passport.STATES. A cold desk then renders ``accruing · n=0`` instead of a bare
conviction word that reads as validated. New desk briefs are held to this immediately; the
handful of pre-existing artifacts that predate the passport are grandfathered in
``LEGACY_NO_PASSPORT`` — a list that only SHRINKS as builders adopt engine.passport.

Run:  python3 scripts/check_badge_passport.py site      # lint (exit 1 on a new offender)
      python3 scripts/check_badge_passport.py site --list
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Desk-brief schemas that carry a directional conviction badge. The passport contract applies
# to these; other conviction-bearing artifacts (per-name anticipation cones etc.) are governed
# by their own provenance markers and are out of scope for this ratchet.
_DESK_SCHEMAS = ("ai_desk", "policy_intent", "stock_desk", "narrative_brain",
                 "thematic_desk", "demand_chain", "radar_desk")
_VALID_STATES = ("measured", "accruing", "unfitted", "stale", "prior")


def _is_desk_brief(d: dict) -> bool:
    sch = str(d.get("schema", ""))
    if not any(sch.startswith(s) for s in _DESK_SCHEMAS):
        return False
    # it renders a conviction badge iff it has theses w/ conviction OR a top-level conviction.
    theses = d.get("theses") or []
    has_conv = any(isinstance(t, dict) and t.get("conviction") for t in theses)
    return has_conv or bool(d.get("conviction"))


def _has_passport(d: dict) -> bool:
    p = d.get("passport")
    return isinstance(p, dict) and p.get("state") in _VALID_STATES


def scan(site_dir: Path) -> tuple[set[str], set[str]]:
    """(desk_briefs, offenders) — offenders render conviction with no valid passport."""
    briefs, offenders = set(), set()
    for p in sorted(site_dir.rglob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:  # noqa: BLE001 — non-JSON / partial file, skip
            continue
        if not isinstance(d, dict) or not _is_desk_brief(d):
            continue
        rel = p.relative_to(_ROOT).as_posix()
        briefs.add(rel)
        if not _has_passport(d):
            offenders.add(rel)
    return briefs, offenders


# Frozen 2026-07-01: desk briefs that predate the passport helper. Adopting engine.passport in
# the builder (add ``brief["passport"] = passport_from_spine(...)`` ) removes the file here.
# THIS LIST ONLY SHRINKS.
LEGACY_NO_PASSPORT = frozenset({
    "site/policy_intent.json",
})


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    args = [a for a in argv if not a.startswith("-")]
    site_dir = Path(args[0]) if args else (_ROOT / "site")
    if not site_dir.is_absolute():
        site_dir = _ROOT / site_dir
    if not site_dir.exists():
        print(f"OK: site dir {site_dir} absent (nothing rendered yet).")
        return 0

    briefs, offenders = scan(site_dir)
    if "--list" in argv:
        print(f"{len(briefs)} desk brief(s); {len(offenders)} without a valid passport:")
        for f in sorted(offenders):
            grand = " (grandfathered)" if f in LEGACY_NO_PASSPORT else " *** NEW ***"
            print(f"  {f}{grand}")
        return 0

    new = offenders - LEGACY_NO_PASSPORT
    stale = LEGACY_NO_PASSPORT - offenders
    rc = 0
    if new:
        print("FAIL: these desk briefs render a conviction badge with NO provenance passport (#41).",
              file=sys.stderr)
        print("Add brief['passport'] = engine.passport.passport_from_spine(f'desk:{name}', ...) so a",
              file=sys.stderr)
        print("cold desk renders 'accruing · n=0' instead of a bare conviction that reads as earned:",
              file=sys.stderr)
        for f in sorted(new):
            print(f"  {f}", file=sys.stderr)
        rc = 1
    if stale:
        print("NOTE: these grandfathered briefs now carry a passport — prune them from "
              "LEGACY_NO_PASSPORT so the ratchet stays tight:", file=sys.stderr)
        for f in sorted(stale):
            print(f"  {f}", file=sys.stderr)
        rc = 1
    if rc == 0:
        print(f"OK: every desk brief carries a passport ({len(briefs)} checked, "
              f"{len(LEGACY_NO_PASSPORT)} grandfathered).")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
