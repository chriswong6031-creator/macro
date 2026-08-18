"""Read-only lawful W3 status surface (PR-3D).

Renders accrual/maturity/gap status from the committed W3 store. Does not
compute or print C1-vs-shadow IC, delta, p-values, HAC, confidence intervals,
or a leader. Before the frozen honest-N floor the comparison surface stays
sealed — this script never reaches it.

ZERO AUTHORITY. No rank, gate, size, board, featured, or plan consumer.

Run:  python -m scripts.report_us_prophet_w3
      python -m scripts.report_us_prophet_w3 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import us_prophet_w3 as w3  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="dump the lawful status document as JSON")
    ap.add_argument("--root", default=None,
                    help="optional repo root (tests); default is the live tree")
    args = ap.parse_args()
    root = Path(args.root) if args.root else None
    payload = w3.build_status_surface(root)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return
    text = w3.render_status_text(payload)
    print(text, end="" if text.endswith("\n") else "\n")
    if not payload.get("commissioned"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
