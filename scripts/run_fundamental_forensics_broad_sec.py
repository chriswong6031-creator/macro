"""Incremental broad SEC source-plane poll for Filing Forensics (FF-1).

Scheduled invocation is incremental only. Recovery is an explicit
workflow_dispatch path. Partial polls persist successful issuer evidence but
exit non-zero and do not advance the latest-complete census head.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.edgar_forensics import _user_agent  # noqa: E402
from engine.fundamental_forensics.broad_sec_store import (  # noqa: E402
    BroadSecError,
    PollClocks,
    UNIVERSE_RELATIVE_PATH,
    live_fetchers,
    open_store,
    run_broad_sec_poll,
)
from engine.fundamental_forensics.models import canonical_json  # noqa: E402
from lib import config  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(
    argv: list[str] | None = None,
    *,
    now: Callable[[], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("incremental", "recovery"), default="incremental")
    parser.add_argument("--recovery-from", default=None, help="ISO-8601 Z stale vintage; recovery only")
    parser.add_argument("--universe", type=Path, default=None)
    parser.add_argument("--repo-root", type=Path, default=config.ROOT)
    parser.add_argument("--local-store", type=Path, default=None)
    parser.add_argument("--scratch-root", type=Path, default=None)
    parser.add_argument("--poll-started-at", default=None)
    parser.add_argument("--poll-completed-at", default=None)
    parser.add_argument("--recorded-at", default=None)
    parser.add_argument("--selection-cutoff-at", default=None)
    parser.add_argument("--user-agent", default=None)
    args = parser.parse_args(argv)

    if args.mode == "recovery" and not args.recovery_from:
        print("recovery mode requires --recovery-from", file=sys.stderr)
        return 1
    if args.mode == "incremental" and args.recovery_from:
        print("incremental mode refuses --recovery-from", file=sys.stderr)
        return 1

    clock = now or _utc_now
    poll_started_at = args.poll_started_at or clock()
    selection_cutoff_at = args.selection_cutoff_at or poll_started_at
    repo_root = args.repo_root.resolve()
    universe = args.universe or (repo_root / UNIVERSE_RELATIVE_PATH)
    scratch = args.scratch_root or Path("/tmp/ff-broad-sec-scratch")
    scratch.mkdir(parents=True, exist_ok=True)

    try:
        store = open_store(args.local_store)
        fetch_submissions, fetch_companyfacts = live_fetchers(
            user_agent=args.user_agent or _user_agent(repo_root),
            scratch_root=scratch,
        )
        result = run_broad_sec_poll(
            store=store,
            universe_path=universe,
            fetch_submissions=fetch_submissions,
            fetch_companyfacts=fetch_companyfacts,
            clocks=PollClocks(
                poll_started_at=poll_started_at,
                selection_cutoff_at=selection_cutoff_at,
                recovery_from=args.recovery_from,
                recorded_at=args.recorded_at,
                poll_completed_at=args.poll_completed_at,
            ),
            now=clock,
            mode=args.mode,
            repo_root=repo_root,
        )
    except BroadSecError as exc:
        print(json.dumps({"status": "failed", "reason_code": exc.reason_code, "detail": exc.detail}))
        return 1

    print(canonical_json(result.receipt), end="")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
