#!/usr/bin/env python3
"""Build the W3S Dead Instrument Control Set (operation SI-W3S-DEAD-CONTROL-V1).

Executes the ladder registered in
``research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md``. That file is
the law; this script only runs it and writes receipts. It selects nothing.

Exit status is deliberate and is the machine-readable terminal state:
  0  RESULT                  — >= 5 accepted controls, each with a real compatibility smoke
  3  BLOCKED_NO_LAWFUL_DATA  — fewer than 5 survive the registered screens

A short cohort is NEVER padded, and criteria are NEVER widened here: the registration
requires an explicit Sol act for that, so the honest terminal state is exit 3.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from engine.stock_identity import dead_control  # noqa: E402

MIN_CONTROLS = 5


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=str(_ROOT))
    ap.add_argument("--out", default=None, help="cohort manifest path (default data/stock_identity/control/)")
    ap.add_argument("--no-write", action="store_true", help="screen and report without writing receipts")
    args = ap.parse_args(argv)

    root = Path(args.repo_root)
    cohort = dead_control.build_cohort(root)

    smokes = []
    for c in cohort["accepted"]:
        try:
            smokes.append(dead_control.compatibility_smoke(
                c["ticker"], c["receipt"]["price_plane_id"], root))
        except Exception as e:  # noqa: BLE001 — a failed smoke is a finding, never a crash
            smokes.append({"symbol": c["ticker"], "ok": False, "error": f"{type(e).__name__}: {e}"})
    cohort["compatibility_smoke"] = smokes

    n_ok = sum(1 for s in smokes if s.get("ok"))
    blocked = n_ok < MIN_CONTROLS
    cohort["terminal_state"] = "BLOCKED_NO_LAWFUL_DATA" if blocked else "RESULT"
    cohort["n_compatible"] = n_ok

    if not args.no_write:
        out = Path(args.out) if args.out else root / "data/stock_identity/control/dead_control_cohort.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cohort, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {out}")

    print(f"population={cohort['n_population']} accepted={cohort['n_accepted']} "
          f"compatible={n_ok} terminal_state={cohort['terminal_state']}")
    print("exclusions: " + json.dumps(cohort["exclusions_by_code"], sort_keys=True))
    if blocked:
        # Line-start form is required for GitHub to render this (see CLAUDE.md).
        print(f"::warning title=w3s-dead-control::BLOCKED_NO_LAWFUL_DATA — "
              f"{n_ok} lawful compatible terminated tapes, need {MIN_CONTROLS}", flush=True)
    return 3 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
