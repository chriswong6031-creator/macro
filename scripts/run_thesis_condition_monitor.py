"""Entry point for the thesis condition monitor (F11 packet B-F11-1).

    python -m scripts.run_thesis_condition_monitor [--dry-run] [--limit N]
        [--now ISO8601] [--evidence-base URL]

Dormant by default (F08 precedent): only writes real rows when
THESIS_MONITOR_ENABLE=1 is set in the environment; otherwise forces --dry-run.
Imports ONLY engine.thesis_condition_monitor -- never a sender. This step
enqueues rows; scripts/drain_alert_outbox.py (F08) sends them.
Always exits 0: a missing table, missing credentials, or an unmerged
migration is a known deployment state, not a build failure.
"""
from __future__ import annotations

import argparse
import os
import sys

from engine import thesis_condition_monitor as monitor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--now", default=None)
    parser.add_argument("--evidence-base", default=monitor.EVIDENCE_BASE)
    args = parser.parse_args(argv)

    enabled = os.environ.get("THESIS_MONITOR_ENABLE") == "1"
    dry_run = args.dry_run or not enabled
    if not enabled:
        print(
            "thesis-monitor: DORMANT (THESIS_MONITOR_ENABLE unset) — "
            "decisions only, no writes",
            flush=True,
        )

    result = monitor.run(
        now_utc=args.now,
        limit=args.limit,
        dry_run=dry_run,
        evidence_base=args.evidence_base,
    )

    if result.read_state == monitor.READ_UNAVAILABLE:
        # result.enqueued_n reflects rows ACTUALLY written before the failure
        # (a write-phase error can follow real POSTs); never assert "0 writes"
        # when enqueued_n is nonzero. The literal READ_UNAVAILABLE token is
        # printed (not just its error_class) so a log grep for the read-state
        # vocabulary finds this line (META-CEO RULING MINOR-3).
        print(
            "::warning title=thesis-monitor-read-unavailable::"
            "%s (%s) — %d enqueued so far, run incomplete"
            % (monitor.READ_UNAVAILABLE, result.error_class, result.enqueued_n),
            flush=True,
        )

    # Dry-run/dormant reports "planned" (nothing written); a live run reports
    # "enqueued" (rows actually POSTed) -- the two must never share one label.
    written_label = "planned" if dry_run else "enqueued"
    written_n = result.planned_n if dry_run else result.enqueued_n

    print(
        "thesis-monitor: outcome=%s read_state=%s evaluated=%d matched=%d %s=%d "
        "duplicate=%d no_coverage=%d unmappable=%d dry_run=%s run_id=%s"
        % (
            result.outcome,
            result.read_state,
            result.evaluated_n,
            result.matched_n,
            written_label,
            written_n,
            result.duplicate_n,
            result.no_coverage_n,
            result.unmappable_n,
            dry_run,
            result.run_id,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
