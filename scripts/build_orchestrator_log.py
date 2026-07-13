"""CLI wrapper for the Neural Web orchestrator run log (W-AI).

Runs in the daily.yml CORTEX job AFTER `build_neuralweb_brief --finalize` so the entry
records the run's final state (cortex status included). Deterministic, no LLM.

    python -m scripts.build_orchestrator_log [--workflow daily]
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one orchestrator run-log entry")
    parser.add_argument("--workflow", default="daily",
                        help="workflow lane recording this run (daily|asia-close|manual)")
    args = parser.parse_args(argv)

    from engine.neuralweb.orchestrator_log import record_run
    result = record_run(workflow=args.workflow)
    entry = result.get("entry") or {}
    print(json.dumps({
        "ok": entry is not None and result.get("published", False),
        "run_date": entry.get("run_date"),
        "summary": entry.get("summary"),
        "review_written": "review" in result,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
