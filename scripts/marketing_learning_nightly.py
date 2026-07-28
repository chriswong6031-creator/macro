"""scripts/marketing_learning_nightly.py — the XG-W6 nightly step.

ONE nightly step, three ordered actions:

    1. ``labels.consolidate``  — advance the tracked labels ledger + scorecard
                                 from the LIVE metrics poll, the reply desk's
                                 host store, and the gitignored intraday spool.
    2. ``health_monitor.run``  — evaluate every account, run the network
                                 tripwire, write health.json, trip halts.
    3. report                  — one JSON blob for the nightly log.

**Order is load-bearing.** The health card is a READ of the labels store, so
running it first would grade yesterday's corpus and call it today's health.

**Nightly is the sole advancer.** Everything under
``data/marketing/learning/`` is written here and only here (plus the operator's
own halt-clear and rule-rollback actions through the admin). Intraday writers
touch ``data/marketing/learning_host/`` and nothing else.

DARK-SAFE. With no telemetry, no reply store and no host spool this is a clean
no-op that writes an empty-but-valid ledger and exits 0 — most runners will
never have anything to consolidate.

Usage:
    python -m scripts.marketing_learning_nightly
    python -m scripts.marketing_learning_nightly --dry-run     # evaluate, write nothing
    python -m scripts.marketing_learning_nightly --no-halts    # consolidate + evaluate,
                                                               # never trip a halt
    MARKETING_LEARNING_ENABLED=0 python -m scripts.marketing_learning_nightly  # skip

Exit code is always 0 unless the step itself crashed: a nightly that cannot
advance a learning ledger must not fail the render.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("marketing_learning_nightly")


def _code_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_cfg(root: Path) -> dict:
    try:
        import yaml  # noqa: PLC0415

        return yaml.safe_load((root / "config" / "marketing.yml").read_text(
            encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("config load failed (%s) — using documented defaults", exc)
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="XG-W6 nightly: consolidate labels, evaluate account health."
    )
    parser.add_argument("--root", default=None,
                        help="Repo root (default: derived from script location)")
    parser.add_argument("--store", default=None,
                        help="Reply desk host-state root (default: "
                             "MASTERMIND_REPLY_DESK_DIR or ~/.mastermind/reply_desk)")
    parser.add_argument("--dry-run", action="store_true",
                        help="evaluate health without writing the halt registry")
    parser.add_argument("--no-halts", dest="no_halts", action="store_true",
                        help="never trip a halt this run (evaluation only)")
    parser.add_argument("--now", default=None, help="ISO override for determinism")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    sys.path.insert(0, str(_code_root()))

    from engine.marketing import health_monitor as _health  # noqa: PLC0415
    from engine.marketing import labels as _labels  # noqa: PLC0415

    root = Path(args.root) if args.root else _code_root()
    cfg = _load_cfg(root)
    now = datetime.now(timezone.utc)
    if args.now:
        try:
            now = datetime.fromisoformat(str(args.now).replace("Z", "+00:00"))
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
        except ValueError:
            log.warning("bad --now %r; using wall clock", args.now)

    # 1. Labels first — health reads what this writes.
    consolidated = _labels.consolidate(now=now, root=root, store=args.store, cfg=cfg)
    if consolidated.get("skipped"):
        # Bare print at line start: a logger prefixes the annotation and GitHub
        # silently drops it (house law).
        print(f"::notice title=learning::labels consolidation skipped "
              f"({consolidated['skipped']})", flush=True)
    else:
        print(
            f"marketing_learning: labels tracked_before="
            f"{consolidated.get('tracked_before', 0)} host={consolidated.get('host', 0)} "
            f"harvested_posts={consolidated.get('harvested_posts', 0)} "
            f"harvested_replies={consolidated.get('harvested_replies', 0)} "
            f"tracked_after={consolidated.get('tracked_after', 0)} "
            f"cells={consolidated.get('cells', 0)}",
            flush=True,
        )
        if not consolidated.get("tracked_after"):
            print(
                "::notice title=learning::no label rows yet — the metrics poll is "
                "dark without BUFFER_TOKEN and the reply desk has sent nothing. The "
                "scorecard is a valid empty artifact, not a failure.",
                flush=True,
            )

    # 2. Health + tripwire.
    apply_halts = not (args.dry_run or args.no_halts)
    report = _health.run(now=now, root=root, store=args.store, cfg=cfg,
                         apply_halts=apply_halts)
    print(
        f"marketing_learning: health accounts={len(report.get('accounts') or [])} "
        f"tripwire={'TRIPPED' if (report.get('network_tripwire') or {}).get('tripped') else 'clear'} "
        f"halted={report.get('halted') or []} "
        f"tripped_this_run={report.get('tripped_this_run') or []} "
        f"apply_halts={apply_halts}",
        flush=True,
    )
    for card in report.get("accounts") or []:
        if card.get("warns"):
            print(
                f"::notice title=account-health::{card['account']} — "
                f"{', '.join(card['warns'])} (surfaced, not halted; see the admin "
                "health panel)",
                flush=True,
            )

    print(json.dumps({"labels": consolidated,
                      "health": {"halted": report.get("halted"),
                                 "tripped_this_run": report.get("tripped_this_run"),
                                 "tripwire": (report.get("network_tripwire") or {}
                                              ).get("tripped")}},
                     ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
