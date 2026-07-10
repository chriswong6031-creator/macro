"""scripts/metabolism_verify.py — VERIFY stage entrypoint (A6).

After a proposal's check_by date arrives, re-grades the realized fitness delta
vs the registered contract using engine.metabolism.verify.verify_proposal().

KILL SWITCH: first action is metabolism_guard.is_paused() → clean journaled
no-op + exit 0 when paused.

Usage:
    python -m scripts.metabolism_verify
        --cycle-id <cycle_id>
        --contract-file <path to docket entry JSON>
        [--root /path/to/repo]
        [--today YYYY-MM-DD]
        [--dry-run]

Exit 0 always (NEVER raises).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("metabolism_verify")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Metabolism VERIFY stage (A6)")
    parser.add_argument("--cycle-id", required=True, help="Cycle ID from the journal")
    parser.add_argument("--contract-file", default=None,
                        help="Path to the proposal's fitness contract JSON")
    parser.add_argument("--root", default=None)
    parser.add_argument("--today", default=None, help="Override today's date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build verify record but do not write to disk")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT
    cycle_id = args.cycle_id

    # ── KILL SWITCH (first action, before any work) ────────────────────────
    from scripts.metabolism_guard import is_paused, pause_reason  # type: ignore[import]
    from scripts.metabolism_journal import start_stage, finish_stage  # type: ignore[import]

    if is_paused():
        log.info("metabolism_verify: %s — no-op exit 0", pause_reason())
        finish_stage(
            cycle_id, "verify",
            status="noop_paused",
            note=pause_reason(),
            root=root,
        )
        return 0

    # ── Load contract ──────────────────────────────────────────────────────
    contract: dict = {}
    if args.contract_file:
        try:
            contract = json.loads(Path(args.contract_file).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("metabolism_verify: could not load contract file: %s", exc)
            finish_stage(cycle_id, "verify", status="failed",
                         note=f"contract load error: {exc}", root=root)
            return 0

    # ── Stage start ───────────────────────────────────────────────────────
    start_stage(cycle_id, "verify", root=root)

    # ── Verify ────────────────────────────────────────────────────────────
    try:
        from engine.metabolism.verify import verify_proposal, write_verify_record  # type: ignore[import]

        record = verify_proposal(
            cycle_id=cycle_id,
            contract=contract,
            root=root,
            today=args.today,
        )

        if args.dry_run:
            log.info("metabolism_verify [dry-run]: %s", json.dumps(record, indent=2, default=str))
        else:
            out_path = write_verify_record(record, root)
            log.info("metabolism_verify: wrote %s", out_path)

        action = record.get("triage", {}).get("action", "")
        log.info("metabolism_verify: cycle=%s action=%s classification=%s",
                 cycle_id, action,
                 record.get("triage", {}).get("classification", ""))

        artifact = str(root / "data" / "metabolism" / "verify" / f"{cycle_id}.json")
        finish_stage(cycle_id, "verify", status="done",
                     artifacts=[artifact] if not args.dry_run else [],
                     root=root)

    except Exception as exc:  # noqa: BLE001
        log.error("metabolism_verify: unexpected error: %s", exc)
        finish_stage(cycle_id, "verify", status="failed", note=str(exc), root=root)

    return 0


if __name__ == "__main__":
    sys.exit(main())
