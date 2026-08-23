#!/usr/bin/env python3
"""Deterministic, read-only inspection edge for W1-A datapoints.

This is deliberately not a query language or public API.  It accepts one
explicit entity, registered fields, audience/use labels, and an optional
knowledge cutoff; all source selection remains inside the fixed runtime.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import json
from pathlib import Path
import sys
from typing import Any, TextIO


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.intelligence_workspace.contracts import (  # noqa: E402
    CONSUMER_USES,
    DatapointContractError,
    canonical_json_bytes,
)
from engine.intelligence_workspace.registry import FROZEN_FIELD_IDS  # noqa: E402
from engine.intelligence_workspace.resolver import (  # noqa: E402
    AdapterContractError,
    DatapointResolver,
    RequestValidationError,
)


class CliUsageError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="resolve_datapoints.py",
        description="Resolve registered W1-A owner facts without writes or persistence.",
    )
    entity = parser.add_mutually_exclusive_group(required=True)
    entity.add_argument("--symbol", help="Current security symbol alias")
    entity.add_argument("--security-id", help="Canonical Data OS SEC:* identity")
    entity.add_argument("--industry-id", help="Exact current Stage USA industry identity")
    parser.add_argument(
        "--field",
        dest="field_ids",
        action="append",
        required=True,
        choices=FROZEN_FIELD_IDS,
        help="Registered field ID; repeat for multiple fields",
    )
    parser.add_argument("--audience", choices=("internal", "subscriber"), default="internal")
    parser.add_argument(
        "--consumer-use",
        choices=tuple(sorted(CONSUMER_USES)),
        default="query",
    )
    parser.add_argument("--requested-as-of", help="Timezone-bearing RFC3339 knowledge cutoff")
    return parser


def _default_resolver_factory() -> DatapointResolver:
    # Import only when the production runtime is requested.  Hermetic callers
    # inject a factory and cannot select modules or paths through CLI arguments.
    from engine.intelligence_workspace.runtime import build_runtime

    return build_runtime()


def _request(args: argparse.Namespace) -> dict[str, Any]:
    if args.symbol is not None:
        entity = {"type": "security", "symbol": args.symbol}
    elif args.security_id is not None:
        entity = {"type": "security", "id": args.security_id}
    else:
        entity = {"type": "industry", "id": args.industry_id}
    request: dict[str, Any] = {
        "entities": [entity],
        "field_ids": list(args.field_ids),
        "audience": args.audience,
        "consumer_use": args.consumer_use,
    }
    if args.requested_as_of is not None:
        request["requested_as_of"] = args.requested_as_of
    return request


def _write_json(stream: TextIO, payload: object) -> None:
    stream.write(canonical_json_bytes(payload).decode("utf-8"))
    stream.write("\n")


def main(
    argv: Sequence[str] | None = None,
    resolver_factory: Callable[[], DatapointResolver] = _default_resolver_factory,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    try:
        args = _parser().parse_args(list(argv) if argv is not None else None)
        resolver = resolver_factory()
        envelopes = resolver.resolve(_request(args))
        _write_json(out, list(envelopes))
        return 0
    except (CliUsageError, DatapointContractError, RequestValidationError, AdapterContractError) as exc:
        _write_json(
            err,
            {
                "error": {
                    "message": str(exc),
                    "type": type(exc).__name__,
                }
            },
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
