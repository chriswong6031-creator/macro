"""Oracle P9 — Review Inbox CLI.

Lists unconverted hypothesis_inbox.jsonl rows, grouped by type with counts.
This is the batch-pass entry point: a reviewing session opens this to see
what needs conversion to mechanism stories.

Usage
-----
  python scripts/oracle_review_inbox.py [--pending] [--data-dir PATH]

  --pending     List only unconverted rows (converted is None or absent).
                Default: list ALL rows.
  --data-dir    Path to the data directory (default: lib.config.data_dir()).
  --all         List all rows, including already-converted ones.
  --type TYPE   Filter to a specific row type.
  --json        Output raw JSON lines instead of the summary table.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INBOX_FILENAME = "hypothesis_inbox.jsonl"


def _load_inbox_rows(inbox_path: Path) -> list[dict]:
    """Load all rows from hypothesis_inbox.jsonl (torn-line tolerant)."""
    rows: list[dict] = []
    if not inbox_path.exists():
        return rows
    for line in inbox_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except (json.JSONDecodeError, Exception):  # noqa: BLE001
            pass
    return rows


def _is_converted(row: dict) -> bool:
    """Return True if the row has a non-null 'converted' field."""
    v = row.get("converted")
    return v is not None


def _print_summary(rows: list[dict], pending_only: bool, type_filter: str | None) -> None:
    """Print a human-readable summary grouped by type."""
    if type_filter:
        rows = [r for r in rows if r.get("type") == type_filter]
    if pending_only:
        rows = [r for r in rows if not _is_converted(r)]

    if not rows:
        print("No rows to display.")
        return

    # Group by type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_type[r.get("type", "unknown")].append(r)

    total = len(rows)
    print(f"\n=== Oracle Hypothesis Inbox — {'PENDING' if pending_only else 'ALL'} rows ({total}) ===\n")

    for rtype, type_rows in sorted(by_type.items()):
        print(f"  [{rtype}]  count={len(type_rows)}")
        for r in type_rows:
            pit = str(r.get("pit_stamp", ""))[:19]
            detail = r.get("detail_en", r.get("id", ""))[:100]
            conv = "  [CONVERTED]" if _is_converted(r) else ""
            print(f"    {pit}  {r.get('id', '?')[:60]}{conv}")
            print(f"      {detail}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Oracle hypothesis inbox review")
    parser.add_argument("--pending", action="store_true", default=True,
                        help="List unconverted rows only (default: True)")
    parser.add_argument("--all", dest="show_all", action="store_true",
                        help="List all rows including converted")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--type", dest="row_type", default=None,
                        help="Filter to a specific row type")
    parser.add_argument("--json", dest="output_json", action="store_true",
                        help="Output raw JSON lines instead of summary")
    args = parser.parse_args()

    from lib import config as _cfg
    data_dir = args.data_dir or _cfg.data_dir()
    inbox_path = data_dir / "oracle" / INBOX_FILENAME

    rows = _load_inbox_rows(inbox_path)

    pending_only = not args.show_all

    if args.output_json:
        # Raw JSON output
        if args.row_type:
            rows = [r for r in rows if r.get("type") == args.row_type]
        if pending_only:
            rows = [r for r in rows if not _is_converted(r)]
        for r in rows:
            print(json.dumps(r))
        return 0

    _print_summary(rows, pending_only=pending_only, type_filter=args.row_type)

    # Print counts summary line
    by_type: dict[str, int] = defaultdict(int)
    for r in rows:
        if pending_only and _is_converted(r):
            continue
        if args.row_type and r.get("type") != args.row_type:
            continue
        by_type[r.get("type", "unknown")] += 1

    print("  Counts by type:", dict(sorted(by_type.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
