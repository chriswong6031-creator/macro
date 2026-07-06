"""Oracle W5.1 — Operator Tape Journal CLI.

60-second structured capture for live rotation observations.
Single-writer law: this CLI is the ONLY writer of data/oracle/operator_tape.jsonl.
Do NOT write to hypothesis_inbox.jsonl (that file's single writer is nightly step 14).

Usage
-----
  # Add an observation
  python scripts/oracle_tape.py add \\
      --nodes "XLK,XLC" \\
      --direction in \\
      --note "Tech breaking out of 3-week base, XLC rotating in hard" \\
      --tickers "MSFT,NVDA" \\
      --invalidation "Close below 200d MA on XLK" \\
      --conviction 4

  # List all rows
  python scripts/oracle_tape.py list

  # List only pending (unconverted) rows
  python scripts/oracle_tape.py list --pending

Schema (one JSONL row per observation)
---------------------------------------
  {
    "id":           "tape::<UTC ISO seconds>[::N]",
    "type":         "operator_tape",
    "pit_stamp":    "<UTC ISO 8601>",
    "nodes":        ["XLK", "XLC"],
    "direction":    "in" | "out",
    "note":         "<free text — what the operator sees>",
    "tickers":      ["MSFT", "NVDA"],   # optional, may be []
    "invalidation": "<free text>",       # optional, may be null
    "conviction":   4,                   # optional int 1-5, may be null
    "converted":    null                 # non-null once reviewed/converted
  }

Duplicate-id guard (keep-first): if two adds land in the same UTC second the
second entry gets suffix ::2, third ::3, etc.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TAPE_FILENAME = "operator_tape.jsonl"


def _tape_path(data_dir: Path) -> Path:
    return data_dir / "oracle" / TAPE_FILENAME


def _load_existing_ids(tape_path: Path) -> set[str]:
    """Return the set of all existing row ids (torn-line tolerant)."""
    ids: set[str] = set()
    if not tape_path.exists():
        return ids
    for line in tape_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if "id" in row:
                ids.add(row["id"])
        except (json.JSONDecodeError, Exception):  # noqa: BLE001
            pass
    return ids


def _make_id(pit_iso: str, existing_ids: set[str]) -> str:
    """Generate a keep-first duplicate-safe id.

    Base: tape::<UTC ISO seconds> (drop sub-second precision).
    If already present, suffix with ::2, ::3, ... until unique.
    """
    # Truncate to seconds: "2026-07-05T12:34:56Z" → base
    base = "tape::" + pit_iso[:19].replace(":", "-")
    candidate = base
    n = 2
    while candidate in existing_ids:
        candidate = f"{base}::{n}"
        n += 1
    return candidate


def _load_rows(tape_path: Path) -> list[dict]:
    """Load all rows from operator_tape.jsonl (torn-line tolerant)."""
    rows: list[dict] = []
    if not tape_path.exists():
        return rows
    for line in tape_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except (json.JSONDecodeError, Exception):  # noqa: BLE001
            pass
    return rows


def _snapshot_system_state(nodes: list[str], data_dir: Path) -> dict | None:
    """Capture Oracle's current state for the given nodes from forward_ledger.jsonl.

    Written at tape-add time so the PIT state is permanently recorded even before
    the nightly resolver runs. Returns a dict {node: direction} for all nodes that
    have an active episode as of the latest ledger pit_stamp, or None on any error.

    This field is ADDITIVE to the tape schema — older rows lack it (null treated as
    unresolvable by the resolver, which falls back to ledger reconstruction).

    Single-writer law is preserved: this function only READS the ledger.
    """
    try:
        ledger_path = data_dir / "oracle" / "forward_ledger.jsonl"
        if not ledger_path.exists():
            return None

        # Find the latest pit_stamp in the ledger
        latest_ps = ""
        node_state: dict[str, str] = {}
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ps = str(row.get("pit_stamp", ""))[:10]
            if ps > latest_ps:
                latest_ps = ps
            nd = str(row.get("node", ""))
            direction = str(row.get("direction", ""))
            if nd and direction and ps == latest_ps:
                node_state[nd] = direction

        if not latest_ps:
            return None

        # If latest_ps was updated we may need a second pass (single-pass may miss
        # nodes from earlier stamps). Quick two-pass approach:
        node_state_final: dict[str, str] = {}
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ps = str(row.get("pit_stamp", ""))[:10]
            if ps != latest_ps:
                continue
            nd = str(row.get("node", ""))
            direction = str(row.get("direction", ""))
            if nd and direction:
                node_state_final[nd] = direction

        snapshot = {
            "asof": latest_ps,
            "node_states": {
                node: node_state_final.get(node, "absent")
                for node in nodes
            },
        }
        return snapshot
    except Exception:  # noqa: BLE001
        return None


def _cmd_add(args: argparse.Namespace, data_dir: Path) -> int:
    tape_path = _tape_path(data_dir)
    tape_path.parent.mkdir(parents=True, exist_ok=True)

    # Timestamp (UTC, ISO 8601 with seconds precision)
    now = datetime.now(tz=timezone.utc)
    pit_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    existing_ids = _load_existing_ids(tape_path)
    row_id = _make_id(pit_iso, existing_ids)

    # Parse nodes
    nodes = [n.strip() for n in args.nodes.split(",") if n.strip()]

    # Parse optional tickers
    tickers: list[str] = []
    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    # Parse optional conviction (1-5)
    conviction: int | None = None
    if args.conviction is not None:
        conviction = int(args.conviction)
        if not (1 <= conviction <= 5):
            print(f"ERROR: --conviction must be 1-5, got {conviction}", file=sys.stderr)
            return 1

    # Capture a write-time system_state snapshot for each node from
    # forward_ledger.jsonl — additive field, null-on-error (never blocks add).
    system_state_snapshot: dict | None = _snapshot_system_state(nodes, data_dir)

    row: dict = {
        "id": row_id,
        "type": "operator_tape",
        "pit_stamp": pit_iso,
        "nodes": nodes,
        "direction": args.direction,
        "note": args.note,
        "tickers": tickers,
        "invalidation": args.invalidation if args.invalidation else None,
        "conviction": conviction,
        "converted": None,
        "system_state_snapshot": system_state_snapshot,  # additive; null if unresolvable
    }

    # Append (single-writer: open in append mode)
    with tape_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    print(json.dumps(row, indent=2))
    return 0


def _cmd_list(args: argparse.Namespace, data_dir: Path) -> int:
    tape_path = _tape_path(data_dir)
    rows = _load_rows(tape_path)

    # Filter
    if args.pending:
        rows = [r for r in rows if r.get("converted") is None]

    # Skip schema_note header rows in list output
    rows = [r for r in rows if r.get("type") != "schema_note"]

    if not rows:
        print("No operator tape rows to display.")
        return 0

    label = "PENDING" if args.pending else "ALL"
    print(f"\n=== Operator Tape — {label} ({len(rows)}) ===\n")
    for r in rows:
        pit = str(r.get("pit_stamp", ""))[:19]
        nodes_str = ", ".join(r.get("nodes", []))
        direction = r.get("direction", "?")
        note = r.get("note", "")[:120]
        conv = "  [CONVERTED]" if r.get("converted") is not None else ""
        conviction = r.get("conviction")
        conv_str = f"  conviction={conviction}" if conviction is not None else ""
        print(f"  {pit}  [{direction.upper()}]  nodes={nodes_str}{conv}{conv_str}")
        print(f"    {r.get('id', '?')}")
        print(f"    note: {note}")
        tickers = r.get("tickers", [])
        if tickers:
            print(f"    tickers: {', '.join(tickers)}")
        inv = r.get("invalidation")
        if inv:
            print(f"    invalidation: {inv}")
        print()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Oracle operator tape journal — 60-second observation capture"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- add ---
    add_p = subparsers.add_parser("add", help="Append an observation to the tape")
    add_p.add_argument(
        "--nodes", required=True,
        help="Comma-separated node/sector names (e.g. 'XLK,XLC')"
    )
    add_p.add_argument(
        "--direction", required=True, choices=["in", "out"],
        help="Rotation direction: 'in' (buying in) or 'out' (rotating out)"
    )
    add_p.add_argument(
        "--note", required=True,
        help="What the operator sees (required free text)"
    )
    add_p.add_argument(
        "--tickers", default=None,
        help="Optional comma-separated would-buy tickers (e.g. 'MSFT,NVDA')"
    )
    add_p.add_argument(
        "--invalidation", default=None,
        help="Optional free text: what kills the thesis"
    )
    add_p.add_argument(
        "--conviction", type=int, default=None,
        help="Optional conviction score 1-5"
    )
    add_p.add_argument("--data-dir", type=Path, default=None)

    # --- list ---
    list_p = subparsers.add_parser("list", help="List tape rows")
    list_p.add_argument(
        "--pending", action="store_true", default=False,
        help="Show only unconverted (pending) rows"
    )
    list_p.add_argument("--data-dir", type=Path, default=None)

    args = parser.parse_args()

    from lib import config as _cfg
    data_dir = getattr(args, "data_dir", None) or _cfg.data_dir()

    if args.command == "add":
        return _cmd_add(args, data_dir)
    if args.command == "list":
        return _cmd_list(args, data_dir)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
