"""scripts/build_chronicle.py — Thin orchestrator for the Chronicle W0 spine.

Usage:
    python -m scripts.build_chronicle             # incremental nightly append
    python -m scripts.build_chronicle --rebuild    # regenerate events.jsonl +
                                                    # rollups from sources +
                                                    # existing forward ledgers
                                                    # (byte-stable modulo
                                                    # generated_at; never
                                                    # touches state_log.jsonl or
                                                    # earnings_call_events.jsonl)

Mirrors scripts/build_marketing.py's thinness. Never-raise: exits 0 with a
warning message on error so the nightly pipeline continues. Prints the binding
budget measurement (elapsed seconds, masterplan §0 gate 4 — target well under
the 200-minute nightly job cap; expected to be seconds).
"""
from __future__ import annotations

import argparse
import logging
import sys

log = logging.getLogger(__name__)


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(description="Build the Chronicle market-context timeline spine.")
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Regenerate events.jsonl + rollups from sources + existing forward "
             "ledgers (byte-stable modulo generated_at). Never deletes or rewrites "
             "state_log.jsonl or earnings_call_events.jsonl (nightly is their "
             "sole advancer).",
    )
    args = parser.parse_args(argv)

    try:
        from engine.chronicle.governor import build_and_write
        result = build_and_write(rebuild=args.rebuild)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_chronicle: governor import/run failed: %s", exc)
        print(f"chronicle_governor: WARN (never-raise) — {exc}", file=sys.stderr)
        return 0

    if result.get("error"):
        print(f"chronicle_governor: WARN (never-raise) — {result['error']}", file=sys.stderr)
        return 0

    report = result.get("adapter_report") or {}
    per_adapter = " ".join(f"{name}={info.get('count', 0)}" for name, info in sorted(report.items()))
    mode = "rebuild" if result.get("rebuild") else "incremental"
    call_sync = result.get("earnings_call_sync") or {}
    print(
        f"chronicle_governor: ok — mode={mode} "
        f"total={result.get('total_events', 0)} added={result.get('added', 0)} "
        f"state_appended={result.get('state_appended')} "
        f"state_reason={result.get('state_reason')} "
        f"earnings_call_sync={call_sync.get('reason')} "
        f"elapsed_s={result.get('elapsed_s')} [{per_adapter}]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
