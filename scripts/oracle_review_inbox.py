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
TAPE_FILENAME = "operator_tape.jsonl"


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


def _load_tape_rows(tape_path: Path) -> list[dict]:
    """Load pending operator_tape rows (torn-line tolerant; missing file → empty).

    Skips schema_note header rows. Returns only rows with type=='operator_tape'.
    """
    rows: list[dict] = []
    if not tape_path.exists():
        return rows
    for line in tape_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if row.get("type") == "operator_tape":
                rows.append(row)
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


def _print_tape_section(tape_rows: list[dict], pending_only: bool) -> None:
    """Print the operator_tape group, clearly separated from the inbox rows.

    Always additive — shown after the main inbox summary. A missing tape file
    produces no output (caller passes an empty list).
    """
    if pending_only:
        tape_rows = [r for r in tape_rows if r.get("converted") is None]

    if not tape_rows:
        return

    label = "PENDING" if pending_only else "ALL"
    print(f"--- operator_tape ({label}: {len(tape_rows)}) ---\n")
    for r in tape_rows:
        pit = str(r.get("pit_stamp", ""))[:19]
        nodes_str = ", ".join(r.get("nodes", []))
        direction = r.get("direction", "?").upper()
        note = r.get("note", "")[:120]
        conv = "  [CONVERTED]" if r.get("converted") is not None else ""
        conviction = r.get("conviction")
        conv_str = f"  conviction={conviction}" if conviction is not None else ""
        print(f"  {pit}  [{direction}]  nodes={nodes_str}{conv}{conv_str}")
        print(f"    {r.get('id', '?')[:60]}")
        print(f"    {note}")
        tickers = r.get("tickers", [])
        if tickers:
            print(f"    tickers: {', '.join(tickers)}")
        inv = r.get("invalidation")
        if inv:
            print(f"    invalidation: {inv}")
        print()
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
    tape_path = data_dir / "oracle" / TAPE_FILENAME

    rows = _load_inbox_rows(inbox_path)
    # Tape rows loaded separately; missing file is silently tolerated (_load_tape_rows)
    tape_rows = _load_tape_rows(tape_path)

    pending_only = not args.show_all

    if args.output_json:
        # Raw JSON output — inbox rows only (tape has its own CLI: oracle_tape.py list)
        if args.row_type:
            rows = [r for r in rows if r.get("type") == args.row_type]
        if pending_only:
            rows = [r for r in rows if not _is_converted(r)]
        for r in rows:
            print(json.dumps(r))
        return 0

    _print_summary(rows, pending_only=pending_only, type_filter=args.row_type)

    # Show operator tape section below the main inbox (additive, always shown unless
    # a --type filter is active that would exclude it)
    if not args.row_type or args.row_type == "operator_tape":
        _print_tape_section(tape_rows, pending_only=pending_only)

    # Print counts summary line
    by_type: dict[str, int] = defaultdict(int)
    for r in rows:
        if pending_only and _is_converted(r):
            continue
        if args.row_type and r.get("type") != args.row_type:
            continue
        by_type[r.get("type", "unknown")] += 1

    # Include tape pending count in summary
    if not args.row_type or args.row_type == "operator_tape":
        tape_pending = [r for r in tape_rows if r.get("converted") is None] if pending_only else tape_rows
        if tape_pending:
            by_type["operator_tape"] = len(tape_pending)

    print("  Counts by type:", dict(sorted(by_type.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
