"""Thin CLI wrapper: build the CHF causal feature inventory artifact.

Usage
-----
    python -m scripts.build_causal_inventory [--root REPO_ROOT]

Exit codes
----------
0 — artifact written (partial gaps are printed but do not cause non-zero exit).
1 — total failure to write the artifact.

The caller may wrap with:
    || echo "::warning::build_causal_inventory failed (non-fatal)"
so CI continues even if this step fails.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.causal_inventory import build_inventory  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_causal_inventory")

_OUTPUT_PATH = Path("data") / "neuralweb" / "causal_feature_inventory.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build data/neuralweb/causal_feature_inventory.json from NW stores."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (default: auto-detected from script location).",
    )
    args = parser.parse_args(argv)

    root = args.root if args.root is not None else Path(__file__).resolve().parent.parent

    try:
        payload = build_inventory(root=root)
    except OSError as exc:
        log.error("causal_inventory: FAILED — %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        log.error("causal_inventory: unexpected error — %s", exc)
        return 1

    # Write artifact
    out_path = root / _OUTPUT_PATH
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        log.error("causal_inventory: could not write %s — %s", out_path, exc)
        return 1

    # Report gaps
    gaps: list[str] = payload.get("gap_notes") or []
    if gaps:
        print(f"causal_inventory: PARTIAL — {len(gaps)} gap(s):")
        for g in gaps:
            print(f"  - {g}")
    else:
        print("causal_inventory: all sources read OK — no gaps")

    feature_count: int = payload.get("feature_count", 0)
    asof: str = payload.get("asof", "?")
    print(
        f"causal_inventory OK — features={feature_count} "
        f"gaps={len(gaps)} asof={asof}"
    )
    print(f"written: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
