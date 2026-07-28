"""scripts/marketing_learning_nightly.py — the XG-W6 nightly step.

ONE nightly step, four ordered actions:

    0. ``reply_producer.poll_reply_outcomes``
                               — poll twitterapi.io for outcomes on replies we
                                 SENT, inside the existing reply sub-budget.
    1. ``labels.consolidate``  — advance the tracked labels ledger + scorecard
                                 from the LIVE metrics poll, the reply desk's
                                 host store, and the gitignored intraday spool.
    2. ``health_monitor.run``  — evaluate every account, run the network
                                 tripwire, write health.json, trip halts.
    3. report                  — one JSON blob for the nightly log.

**Order is load-bearing, twice.** Outcomes are polled BEFORE consolidation or
every reply label lags a night behind its own evidence. Health runs AFTER
consolidation because the health card is a READ of the labels store, so grading
first would grade yesterday's corpus and call it today's health.

**Nightly is the sole advancer.** Everything under
``data/marketing/learning/`` is written here and only here (plus the operator's
own halt-clear and rule-rollback actions through the admin). Intraday writers
touch ``data/marketing/learning_host/`` and nothing else.

DARK-SAFE. With no telemetry, no reply store and no host spool this is a clean
no-op that writes an empty-but-valid ledger and exits 0 — most runners will
never have anything to consolidate. At M0 nothing has sent, so the outcome poll
bills nothing.

Usage:
    python -m scripts.marketing_learning_nightly
    # --dry-run: EVALUATE ONLY. No outcome network calls, no labels
    # consolidation, no halt-registry writes. health.json is still written —
    # operator visibility is the point of the flag, not a side effect.
    python -m scripts.marketing_learning_nightly --dry-run
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


def _load_press_cfg(root: Path) -> dict:
    """config/press_sources.yml — carries the twitterapi.io sub-budget the
    outcome poll bills against. Fail-soft: absent means the lane is off."""
    try:
        import yaml  # noqa: PLC0415

        return yaml.safe_load((root / "config" / "press_sources.yml").read_text(
            encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("press config load failed (%s) — outcome polling stays off", exc)
        return {}


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
    from engine.marketing import reply_producer as _reply_producer  # noqa: PLC0415

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

    # 0. Poll outcomes on replies we SENT, before consolidating — otherwise the
    #    labels harvested a line below would carry last night's outcomes and
    #    every reply label would lag a full day behind the evidence.
    #
    #    At M0 the sent set is empty, so this bills nothing and returns an
    #    honest no-op. It is wired anyway because reply labels have no other
    #    source: reply_discovery.poll_outcomes and reply_queue.record_outcome
    #    both shipped in XG-W4 with no caller between them, which left every
    #    reply label permanently null and the parent adjustment inert.
    #    NEVER-RAISE at this boundary. The poll is the only step here that
    #    touches the network, and it runs FIRST — so an unhandled twitterapi.io
    #    hiccup would take label consolidation and the health report down with
    #    it. The step would still exit 0 (daily.yml wraps it), which is the bad
    #    version: a silent night where the ledgers simply did not advance.
    try:
        outcomes = _reply_producer.poll_reply_outcomes(
            cfg=cfg, press_cfg=_load_press_cfg(root), root=root, store=args.store,
            now=now, offline=bool(args.dry_run),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("outcome poll failed: %s", exc, exc_info=True)
        print(f"::warning title=learning::reply outcome poll failed ({exc}) — "
              "labels and health still advance below; outcomes retry tomorrow",
              flush=True)
        outcomes = {"error": str(exc)}
    print(
        f"marketing_learning: reply outcomes sent_in_window={outcomes.get('sent', 0)} "
        f"polled={outcomes.get('polled', 0)} recorded={outcomes.get('recorded', 0)} "
        f"author_replied={outcomes.get('author_replied', 0)} "
        f"spend={outcomes.get('spend') or {}}"
        + (f" — {outcomes['note']}" if outcomes.get("note") else ""),
        flush=True,
    )

    # 1. Labels — health reads what this writes.
    if args.dry_run:
        # The documented semantics: --dry-run EVALUATES, it does not advance a
        # tracked ledger. Calling consolidate() here would write labels.jsonl and
        # scorecard.json, which is the opposite of a dry run.
        consolidated = {"skipped": "dry_run"}
        print("::notice title=learning::--dry-run — labels NOT consolidated "
              "(no tracked-ledger writes); health is evaluated below and the "
              "halt registry is left alone", flush=True)
    else:
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
    # The roster comes from CONFIG, not from whoever happens to have telemetry:
    # a desk that posted nothing is the desk most worth a look, and deriving the
    # roster from label rows would drop it out of health.json entirely instead
    # of reporting "unmeasured".
    report = _health.run(now=now, root=root, store=args.store, cfg=cfg,
                         accounts=_health.roster(cfg, root=root) or None,
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
