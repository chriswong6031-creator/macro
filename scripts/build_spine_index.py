"""scripts/build_spine_index.py — Neural Web W2 CLI: build and write the spine index.

Calls engine.neuralweb.query.write_index, prints one-line stats (rows per ledger,
total, gaps), and exits:
  0 — on success (even with partial gaps from missing sources)
  1 — only on write failure

Usage
-----
    python -m scripts.build_spine_index
    python -m scripts.build_spine_index --root /path/to/repo
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running as a standalone script from the repo root.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("build_spine_index")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Neural Web W2 — build spine query index")
    ap.add_argument("--root", default=None, help="Repo root (default: auto-detect)")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else None

    try:
        from engine.neuralweb.query import write_index  # noqa: PLC0415
        stats = write_index(root)
    except Exception as e:  # noqa: BLE001
        log.error("build_spine_index: write_index failed: %s", e)
        return 1

    # Print one-line summary
    per_ledger = stats.get("per_ledger", {})
    total      = stats.get("total_rows", 0)
    gaps       = stats.get("gap_count", 0)
    out_path   = stats.get("output_path", "?")

    parts = ", ".join(f"{k}={v}" for k, v in sorted(per_ledger.items()))
    log.info(
        "spine-index written: total=%d rows | %s | gap_notes=%d | path=%s",
        total, parts or "no ledgers", gaps, out_path,
    )
    print(
        f"spine-index: total={total} rows | {parts or 'no ledgers'} | "
        f"gap_notes={gaps} | {out_path}"
    )

    if gaps:
        gap_details = stats.get("gaps", {})
        for adapter, notes in gap_details.items():
            for note in notes:
                log.info("  gap [%s]: %s", adapter, note)

    return 0


if __name__ == "__main__":
    sys.exit(main())
