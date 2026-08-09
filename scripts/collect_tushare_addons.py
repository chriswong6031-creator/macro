#!/usr/bin/env python3
"""Plan or execute one bounded TuShare add-on pilot collection.

There is deliberately no date-range, ticker-list, or backfill interface.  The
default mode is a dry plan which performs no network call and no write.  A caller
must pass both ``--execute`` and an explicit ``--output-root`` for the single
partition requested on the command line, and execution requires a configured
``TUSHARE_TOKEN``.  Every other fence is technical and cannot be waived: the
two-exchange ``trade_cal`` session check, the per-endpoint collection clock, the
documented row cap, schema validation, and keep-first immutability.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.tushare_addons import (
    ALLOWED_FREQUENCIES,
    AUTHORITY,
    DEFAULT_OUTPUT_ROOT,
    CollectionHeld,
    CollectorIntegrityError,
    PilotRequest,
    collect_pilot,
    pilot_plan,
)


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--trade-date",
        required=True,
        help="one exact SSE/SZSE session (YYYY-MM-DD or YYYYMMDD)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help=(
            "immutable pilot partition root; required explicitly with --execute "
            f"(plan default: {DEFAULT_OUTPUT_ROOT})"
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=("make at most three vendor calls and install one context-only partition"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="endpoint", required=True)

    minutes = subparsers.add_parser("stk_mins", help="one ticker/session/frequency")
    _add_common_arguments(minutes)
    minutes.add_argument(
        "--ticker", required=True, help="one repo-canonical .SS or .SZ ticker"
    )
    minutes.add_argument(
        "--frequency",
        choices=ALLOWED_FREQUENCIES,
        required=True,
        help="one documented TuShare minute frequency",
    )

    premarket = subparsers.add_parser(
        "stk_premarket", help="one exact daily premarket share-capital partition"
    )
    _add_common_arguments(premarket)
    premarket.add_argument(
        "--ticker",
        required=True,
        help="one repo-canonical .SS or .SZ ticker",
    )

    auction = subparsers.add_parser(
        "stk_auction", help="one same-day opening-auction snapshot"
    )
    _add_common_arguments(auction)
    auction.add_argument(
        "--ticker",
        required=True,
        help="one repo-canonical .SS or .SZ ticker",
    )

    for endpoint, description in (
        ("stk_auction_o", "one session's 09:30 opening call-auction bar"),
        ("stk_auction_c", "one session's 15:00 closing call-auction bar"),
    ):
        call_auction = subparsers.add_parser(endpoint, help=description)
        _add_common_arguments(call_auction)
        call_auction.add_argument(
            "--ticker",
            required=True,
            help="one repo-canonical .SS or .SZ ticker",
        )
    return parser


def _request_from_args(args: argparse.Namespace) -> PilotRequest:
    return PilotRequest(
        endpoint=args.endpoint,
        trade_date=args.trade_date,
        ticker=args.ticker,
        frequency=getattr(args, "frequency", None),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request = _request_from_args(args)
    output_root = args.output_root or DEFAULT_OUTPUT_ROOT
    try:
        if not args.execute:
            _emit(pilot_plan(request, output_root=output_root))
            return 0
        if args.output_root is None:
            raise CollectionHeld("execute_requires_explicit_output_root")
        result = collect_pilot(request, output_root=output_root)
        _emit(result.as_dict())
        return 0
    except CollectionHeld as exc:
        _emit(
            {
                "status": "held_fail_closed",
                "reason_code": exc.reason_code,
                "endpoint": args.endpoint,
                "authority": AUTHORITY,
            }
        )
        return 2
    except CollectorIntegrityError:
        _emit(
            {
                "status": "integrity_failure_fail_closed",
                "reason_code": "source_or_immutable_partition_contradiction",
                "endpoint": args.endpoint,
                "authority": AUTHORITY,
            }
        )
        return 3
    except Exception:  # noqa: BLE001 - never echo exception text or credential-bearing state
        _emit(
            {
                "status": "unexpected_failure_fail_closed",
                "reason_code": "unexpected_collector_failure",
                "endpoint": args.endpoint,
                "authority": AUTHORITY,
            }
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
