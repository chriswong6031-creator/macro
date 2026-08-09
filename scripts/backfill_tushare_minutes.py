#!/usr/bin/env python3
"""Plan, execute, or verify the bulk historical A-share minute-bar backfill.

``--plan`` is the DEFAULT and is completely offline: no network call, no write, and no
token. It prints every vendor call the backfill would make, the
projected row budget, and the pacing floor.

``--execute`` fails closed before a single byte moves unless a Lane-A ``stk_mins``
TP-0 probe receipt already exists on disk (sequencing law: no bulk backfill before
that endpoint's live access/schema witness).

``--verify`` recomputes the coverage ledger from the store's own bytes and runs the
sampled daily-reconciliation gate.  The gate's only permitted anchor is the spine's
NOMINAL ``daily`` plane; ``china_stocks_raw`` (split-adjusted) is forbidden and is
never silently substituted — an absent daily plane is reported as unavailable, which
is not a pass.

Examples::

    python -m scripts.backfill_tushare_minutes --plan \\
        --universe event-catalog --frequency 1min \\
        --start 2011-01-01 --end 2026-08-07

    python -m scripts.backfill_tushare_minutes --verify --sample-size 100
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from collectors import tushare_minutes_plane as plane

_UNIVERSE_CHOICES = ("event-catalog", "spine", "file")


def _emit(payload: object) -> None:
    print(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def _parse_date(raw: str) -> date:
    value = str(raw).strip()
    if len(value) == 8 and value.isdigit():
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date: {raw!r}") from exc


def _load_universe(args: argparse.Namespace) -> plane.Universe:
    if args.universe == "event-catalog":
        return plane.load_universe_from_event_catalog(args.event_catalog)
    if args.universe == "file":
        if args.universe_file is None:
            raise plane.MinutesPlaneHeld("universe_file_required_for_file_universe")
        return plane.load_universe_from_file(args.universe_file)
    # The full-A universe is DEFERRED: it needs the spine's reference generation to
    # exist and a separate budget ruling.  Failing loudly beats quietly planning a
    # 5,000-name backfill nobody sized.
    raise plane.MinutesPlaneHeld(
        "spine_full_a_universe_is_deferred_see_takeover_lane_b"
    )


def _load_calendar(args: argparse.Namespace) -> plane.SessionCalendar:
    if args.session_source == "spine":
        return plane.load_session_calendar_from_spine(args.spine_store)
    if args.session_source == "event-catalog":
        return plane.load_session_calendar_from_event_catalog(args.event_catalog)
    try:
        return plane.load_session_calendar_from_spine(args.spine_store)
    except plane.MinutesPlaneHeld:
        return plane.load_session_calendar_from_event_catalog(args.event_catalog)


def _build_plan(args: argparse.Namespace) -> plane.BackfillPlan:
    return plane.plan_backfill(
        universe=_load_universe(args),
        calendar=_load_calendar(args),
        frequency=args.frequency,
        start=args.start,
        end=args.end,
        store_root=args.store_root,
        year_scope=args.year_scope,
        manifest=plane.read_manifest(args.store_root),
    )


def _run_plan(args: argparse.Namespace) -> int:
    backfill = _build_plan(args)
    _emit(backfill.as_dict(include_chunks=args.include_chunks))
    return 0


def _run_execute(args: argparse.Namespace) -> int:
    # TP-0 raises before any network call or filesystem mutation and is re-checked
    # inside execute_backfill so direct callers cannot bypass the sequencing law.
    plane.require_tp0_probe_receipt(args.addons_root)
    backfill = _build_plan(args)
    result = plane.execute_backfill(
        backfill,
        store_root=args.store_root,
        addons_root=args.addons_root,
        max_partitions=args.max_partitions,
    )
    _emit(result)
    return 0


def _run_verify(args: argparse.Namespace) -> int:
    daily = None
    daily_state = "not_requested"
    try:
        daily = plane.load_daily_reference(args.spine_store)
        daily_state = "loaded"
    except plane.MinutesPlaneHeld as held:
        daily_state = held.reason_code
    report = plane.verify_store(
        args.store_root, daily=daily, sample_size=args.sample_size
    )
    report["daily_reference_state"] = daily_state
    _emit(report)
    return 0 if report.get("passed") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backfill_tushare_minutes",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--plan",
        dest="mode",
        action="store_const",
        const="plan",
        help="print the chunk plan, call count, and pacing floor (default; offline)",
    )
    mode.add_argument(
        "--execute",
        dest="mode",
        action="store_const",
        const="execute",
        help="run the backfill (TP-0 probe receipt required)",
    )
    mode.add_argument(
        "--verify",
        dest="mode",
        action="store_const",
        const="verify",
        help="recompute the ledger from the store and run the reconciliation gate",
    )
    parser.set_defaults(mode="plan")

    parser.add_argument(
        "--universe",
        choices=_UNIVERSE_CHOICES,
        default="event-catalog",
        help=(
            "event-catalog = distinct tickers in the limit-event catalog (default "
            "backfill order); file = one ticker per line; spine = full-A (deferred)"
        ),
    )
    parser.add_argument("--universe-file", type=Path, default=None)
    parser.add_argument(
        "--frequency", choices=plane.ALLOWED_FREQUENCIES, default="1min"
    )
    parser.add_argument("--start", type=_parse_date, default=_parse_date("2011-01-01"))
    parser.add_argument("--end", type=_parse_date, default=_parse_date("2026-08-07"))
    parser.add_argument(
        "--year-scope",
        choices=("event-years", "all-years"),
        default="event-years",
        help=(
            "event-years (default) plans a ticker-year only when that ticker has a "
            "limit event that year — the battery's actual need; all-years plans the "
            "full cross product"
        ),
    )
    parser.add_argument(
        "--session-source",
        choices=("auto", "spine", "event-catalog"),
        default="auto",
        help="auto prefers the spine's attested session clock, else observed sessions",
    )
    parser.add_argument("--store-root", type=Path, default=plane.DEFAULT_STORE_ROOT)
    parser.add_argument("--spine-store", type=Path, default=plane.DEFAULT_SPINE_STORE)
    parser.add_argument("--addons-root", type=Path, default=plane.DEFAULT_ADDONS_ROOT)
    parser.add_argument(
        "--event-catalog", type=Path, default=plane.DEFAULT_EVENT_CATALOG
    )
    parser.add_argument(
        "--include-chunks",
        action="store_true",
        help="plan mode: emit every chunk request (large)",
    )
    parser.add_argument(
        "--max-partitions",
        type=int,
        default=None,
        help="execute mode: stop after N partitions (supervised first run)",
    )
    parser.add_argument("--sample-size", type=int, default=50)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runners = {"plan": _run_plan, "execute": _run_execute, "verify": _run_verify}
    try:
        return runners[args.mode](args)
    except plane.MinutesPlaneHeld as held:
        payload: dict[str, object] = {
            "status": "held",
            "mode": args.mode,
            "reason_code": held.reason_code,
        }
        if held.reason_code.startswith("tp0_"):
            payload["sequencing_law"] = (
                "TP-0: Lane A's live stk_mins probe receipt must exist under "
                f"{plane.DEFAULT_ADDONS_ROOT}/stk_mins/ before any bulk backfill"
            )
        _emit(payload)
        return 2
    except plane.MinutesPlaneIntegrityError as error:
        _emit({"status": "integrity_error", "mode": args.mode, "error": str(error)})
        return 3


if __name__ == "__main__":
    sys.exit(main())
