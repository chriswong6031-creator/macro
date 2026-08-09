"""Hard-disabled production shell for share-count v2 ledger retention.

The pure planner, contracts, and injected tests exist, but this command refuses
remote listing or deletion until three release dependencies land: provider-proven
atomic conditional delete, a shared publisher/retention fence, and a capability
boundary that can never write the signed publication head. ``--apply`` also
requires two explicit environment gates, but those gates cannot bypass the
protocol release block.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.capital_structure.share_count_retention import (
    DEFAULT_MAX_OBJECTS,
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGE_SIZE,
    DEFAULT_QUARANTINE_SECONDS,
    ShareCountRetentionError,
)  # noqa: E402


APPLY_ENABLE_ENV = "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_APPLY_ENABLED"
RETENTION_ENABLE_ENV = "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_ENABLED"
DEDICATED_DELETE_ENV_NAMES = (
    "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_R2_ENDPOINT",
    "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_R2_ACCESS_KEY_ID",
    "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_R2_SECRET_ACCESS_KEY",
    "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_R2_BUCKET",
)
RECEIPT_SIGNING_ENV = "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_RECEIPT_HMAC_KEY"


@dataclass(frozen=True)
class DedicatedDeleteConfig:
    endpoint: str
    access_key_id: str
    secret_access_key: str
    bucket: str


def _dedicated_delete_config(environ: Mapping[str, str]) -> DedicatedDeleteConfig:
    """Require exactly the dedicated retention credentials: no shared fallback."""
    values = {name: environ.get(name, "").strip() for name in DEDICATED_DELETE_ENV_NAMES}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ShareCountRetentionError(
            "retention delete credentials are unconfigured; require dedicated " + ", ".join(missing),
        )
    return DedicatedDeleteConfig(
        endpoint=values[DEDICATED_DELETE_ENV_NAMES[0]],
        access_key_id=values[DEDICATED_DELETE_ENV_NAMES[1]],
        secret_access_key=values[DEDICATED_DELETE_ENV_NAMES[2]],
        bucket=values[DEDICATED_DELETE_ENV_NAMES[3]],
    )


def _require_apply_enabled(environ: Mapping[str, str]) -> None:
    if environ.get(RETENTION_ENABLE_ENV) != "true" or environ.get(APPLY_ENABLE_ENV) != "true":
        raise ShareCountRetentionError(
            "retention apply requires both explicit retention and apply enable environment gates",
        )


def _require_released_retention_protocol() -> None:
    raise ShareCountRetentionError(
        "production retention is hard-disabled pending provider-proven conditional delete, "
        "a shared publisher/retention fence, and a verifier-only capability boundary",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform guarded conditional deletes")
    parser.add_argument("--quarantine-seconds", type=int, default=DEFAULT_QUARANTINE_SECONDS)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--max-objects", type=int, default=DEFAULT_MAX_OBJECTS)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    return parser


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    values = os.environ if environ is None else environ
    try:
        if args.apply:
            _require_apply_enabled(values)
        # This release block intentionally runs before reading credentials or
        # creating a remote client. A mistaken workflow-variable flip therefore
        # cannot inject or exercise delete authority.
        _require_released_retention_protocol()
        # Even a dry run reads an untrusted remote listing.  Demand the dedicated
        # retention configuration rather than borrowing the publisher or shared R2
        # credentials merely because no delete will happen in this invocation.
        _dedicated_delete_config(values)
    except ShareCountRetentionError as exc:
        print(f"::error title=share-count-retention::{exc}", file=sys.stderr, flush=True)
        return 2
    return 0  # pragma: no cover - reachable only after the release block is replaced


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
