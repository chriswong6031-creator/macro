#!/usr/bin/env python3
"""Build the Calibration Hub — the unified observability surface for the self-improving
AI suite (engine.calibration_hub). Writes data/calibration/summary.json + site/calibration.html.

Display-only; reads the Phase-C scorers' track records + the Trial Ledger. Run after the
desk scorers in the daily build so the surface reflects the freshest track records.

Run: python -m scripts.build_calibration
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import calibration_hub  # noqa: E402


def main() -> int:
    s = calibration_hub.run(persist=True)
    lp = s["loops"]
    print(f"[built] site/calibration.html — {lp['live']}/{lp['total']} desk loops live, "
          f"{s['trial_ledger']['total_families']} trial families")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
