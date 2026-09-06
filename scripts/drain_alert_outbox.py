"""scripts/drain_alert_outbox.py -- entry point for the fired-alert delivery drain.

    python -m scripts.drain_alert_outbox [--dry-run] [--limit N] [--now ISO8601]

Wires ``engine.alert_delivery_drain.drain`` (pure decisions + isolated PostgREST IO)
to ``app.mailer.send_alert`` (the only place that actually touches SMTP). Importing
``app.mailer`` here is lawful at this layer -- the established precedent is
``scripts/freshness_sentinel.py`` importing ``app.mailer``.

Dormant by default: without ``ALERT_DRAIN_ENABLE=1`` in the environment this script
forces ``dry_run=True`` and prints a DORMANT line -- decisions only, no sends, no
writes. This is required, not optional: the F08 architecture freeze section 10 (V4)
mandates a hard privacy/risk review by an opus reviewer before enable, and this packet
is not that review. Precedent: ``app/deploy/macro-entry-radar-pack.service`` ships its
lane dormant behind ``ENTRY_RADAR_LIVE_ENABLE=1``.

No live URL -- this is engine/delivery, off the render path. Proof of life is this
script executing green with ``--dry-run`` against fixture rows in the test suite, plus
a merge readback.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from app import mailer
from engine import alert_delivery_drain as drain_mod


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Drain the fired-alert outbox (off-render).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--now", default=None, help="ISO8601 override, for tests/ops.")
    args = parser.parse_args(argv)

    enabled = (os.environ.get("ALERT_DRAIN_ENABLE") or "").strip() == "1"
    dry_run = args.dry_run or not enabled
    if not enabled:
        print("alert-drain: DORMANT (ALERT_DRAIN_ENABLE unset) -- decisions only, no sends", flush=True)

    now_utc = None
    if args.now:
        s = args.now.replace("Z", "+00:00")
        now_utc = datetime.fromisoformat(s)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

    send_fn = None if dry_run else mailer.send_alert
    result = drain_mod.drain(send_fn=send_fn, now_utc=now_utc, limit=args.limit, dry_run=dry_run)

    if result.read_state == drain_mod.READ_UNAVAILABLE:
        print("::warning title=alert-drain-read-unavailable::"
              "alert_outbox/alert_runs not readable (%s) -- 0 sends, 0 writes"
              % result.error_class, flush=True)

    print("alert-drain: outcome=%s evaluated=%d fired=%d unevaluable=%d deferred=%d "
          "suppressed=%d failed=%d category_unfiltered=%d duplicate=%d receipt_written=%s "
          "run_id=%s"
          % (result.outcome, result.evaluated_n, result.fired_n, result.unevaluable_n,
             result.deferred_n, result.suppressed_n, result.failed_n,
             result.category_unfiltered_n, result.duplicate_n, result.receipt_written,
             result.run_id),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
