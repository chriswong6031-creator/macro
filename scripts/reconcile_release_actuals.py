"""Persist verified live official-release facts as immutable scoring receipts."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.release_actuals import load_actual_ledger, reconcile_receipts

DEFAULT_SOURCE = "https://mastermind-x.com/live/release_publications.json"
DEFAULT_OUT = _ROOT / "data" / "release_forecast" / "official_actuals.jsonl"


def _read_payload(source: str, timeout: float = 10.0) -> dict[str, Any]:
    if source.startswith("https://"):
        request = urllib.request.Request(
            source,
            headers={"User-Agent": "Mastermind-Release-Actual-Reconciler/1.0"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise ValueError("release publication payload exceeds 5 MB")
        value = json.loads(body)
    else:
        value = json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("release publication payload is not an object")
    return value


def append_receipts(path: Path, rows: list[dict[str, Any]]) -> int:
    """Durably append receipt rows; caller has already performed idempotency."""
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return len(rows)


def reconcile(source: str, out: Path, timeout: float = 10.0, dry_run: bool = False) -> list[dict[str, Any]]:
    payload = _read_payload(source, timeout=timeout)
    existing = load_actual_ledger(out)
    novel = reconcile_receipts(payload, existing)
    if not dry_run:
        append_receipts(out, novel)
    return novel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        rows = reconcile(args.source, args.out, timeout=args.timeout, dry_run=args.dry_run)
    except Exception as exc:
        print(f"release actual reconciliation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"release actual reconciliation: {len(rows)} new receipt(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
