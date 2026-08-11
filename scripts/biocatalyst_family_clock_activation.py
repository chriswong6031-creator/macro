#!/usr/bin/env python3
"""Evaluate and, only by explicit operator act, record BioCatalyst clocks.

Preview is read-only and is the default.  Record mode requires the operator to
name the exact set of families expected to open; any difference fails before a
state root is provisioned or a receipt is written.  The activation instant is
also the accrual start and the record time, so opening a clock can never create
backfill.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from engine.biocatalyst.family_clock import (
    CLOCK_CLOSED,
    CLOCK_OPENED,
    FAMILY_POLICY_PATH,
    SOURCE_REGISTRY_PATH,
    FamilyClockError,
    evaluate_family_clocks,
    load_yaml_document,
    o1b_writer_is_available,
    record_family_clock_activations,
)
from engine.biocatalyst.operational_store import (
    DEFAULT_PRODUCTION_STATE_ROOT,
    STORE_META_FILENAME,
    OperationalStore,
    OperationalStoreError,
    provision_operational_store,
)
from engine.sector_intelligence.contracts import (
    ContractValidationError,
    canonical_json_bytes,
)

PROGRAM = "biocatalyst-family-clock-activation"
MODES = ("preview", "record")
EXIT_OK = 0
EXIT_PRECONDITION_FAILED = 2


class ActivationCliError(RuntimeError):
    """One bounded operator-facing failure code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=__doc__,
        allow_abbrev=False,
    )
    parser.add_argument("--mode", choices=MODES, default="preview")
    parser.add_argument(
        "--state-root",
        default=str(DEFAULT_PRODUCTION_STATE_ROOT),
        help="BC-O1a operational root; preview never reads or creates it",
    )
    parser.add_argument(
        "--provision",
        action="store_true",
        help="record only: explicitly provision a missing or empty operational root",
    )
    parser.add_argument(
        "--evaluated-at",
        default=None,
        help="activation instant; canonicalized to a microsecond UTC Z timestamp",
    )
    parser.add_argument(
        "--expected-open-family",
        action="append",
        default=[],
        help="record only: repeat once for every family expected to open",
    )
    return parser


def _activation_stamp(value: str | None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    else:
        if not value or value != value.strip():
            raise ActivationCliError("ACTIVATION_TIME_INVALID")
        try:
            parsed = datetime.fromisoformat(
                value[:-1] + "+00:00" if value.endswith("Z") else value
            )
        except ValueError:
            raise ActivationCliError("ACTIVATION_TIME_INVALID") from None
        if parsed.tzinfo is None:
            raise ActivationCliError("ACTIVATION_TIME_INVALID")
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _load_evidence(repo_root: Path) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    policy, policy_sha256 = load_yaml_document(repo_root / FAMILY_POLICY_PATH)
    sources, source_sha256 = load_yaml_document(repo_root / SOURCE_REGISTRY_PATH)
    return policy, policy_sha256, sources, source_sha256


def _expected_open_set(values: Sequence[str], known: set[str]) -> set[str]:
    if not values:
        raise ActivationCliError("EXPECTED_OPEN_FAMILIES_REQUIRED")
    if len(values) != len(set(values)):
        raise ActivationCliError("EXPECTED_OPEN_FAMILIES_DUPLICATE")
    expected = set(values)
    if not expected <= known:
        raise ActivationCliError("EXPECTED_OPEN_FAMILY_UNKNOWN")
    return expected


def _store_for_record(path: Path, *, provision: bool, repo_root: Path) -> OperationalStore:
    if not path.is_absolute() or path.is_symlink():
        raise ActivationCliError("OPERATIONAL_STATE_ROOT_INVALID")
    if path.exists() and not path.is_dir():
        raise ActivationCliError("OPERATIONAL_STATE_ROOT_INVALID")

    meta = path / STORE_META_FILENAME
    if meta.is_symlink():
        raise ActivationCliError("OPERATIONAL_STATE_ROOT_INVALID")
    if path.is_dir() and meta.is_file():
        return OperationalStore(path, repo_root=repo_root)

    if not provision:
        raise ActivationCliError("OPERATIONAL_STATE_ROOT_UNPROVISIONED")
    if path.is_dir() and any(path.iterdir()):
        raise ActivationCliError("OPERATIONAL_STATE_ROOT_OCCUPIED")
    provision_operational_store(path)
    return OperationalStore(path, repo_root=repo_root)


def _summary(
    *,
    mode: str,
    evaluated_at: str,
    policy: dict[str, Any],
    policy_sha256: str,
    source_sha256: str,
    decisions: Sequence[Any],
    receipts: Sequence[Any] = (),
) -> dict[str, Any]:
    opened = sorted(decision.family_id for decision in decisions if decision.opened)
    closed = sorted(
        decision.family_id
        for decision in decisions
        if decision.clock_state == CLOCK_CLOSED
    )
    created_ids = sorted(receipt.record_id for receipt in receipts if receipt.created)
    existing_ids = sorted(receipt.record_id for receipt in receipts if not receipt.created)
    return {
        "action": mode,
        "evaluated_at": evaluated_at,
        "policy_version": policy.get("policy_version"),
        "policy_sha256": policy_sha256,
        "source_registry_sha256": source_sha256,
        "writer_available": True,
        "family_count": len(decisions),
        "opened_family_ids": opened,
        "closed_family_ids": closed,
        "record_count": len(receipts),
        "created_record_count": len(created_ids),
        "created_record_ids": created_ids,
        "existing_record_ids": existing_ids,
        "accrual": "from_evaluated_at_no_backfill",
        "authority": "facts_and_context_only",
    }


def run(
    argv: Sequence[str] | None = None,
    *,
    repo_root: Path | str = _ROOT,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        evaluated_at = _activation_stamp(arguments.evaluated_at)
        root = Path(repo_root).resolve()
        policy, policy_sha256, sources, source_sha256 = _load_evidence(root)
        if not o1b_writer_is_available(repo_root=root):
            raise ActivationCliError("O1B_WRITER_UNAVAILABLE")
        decisions = evaluate_family_clocks(policy, sources, writer_available=True)
        if len(decisions) != 9 or {item.clock_state for item in decisions} - {
            CLOCK_OPENED,
            CLOCK_CLOSED,
        }:
            raise ActivationCliError("FAMILY_CLOCK_EVALUATION_INVALID")

        if arguments.mode == "preview":
            if arguments.provision:
                raise ActivationCliError("PREVIEW_CANNOT_PROVISION")
            summary = _summary(
                mode="preview",
                evaluated_at=evaluated_at,
                policy=policy,
                policy_sha256=policy_sha256,
                source_sha256=source_sha256,
                decisions=decisions,
            )
        else:
            known = {decision.family_id for decision in decisions}
            expected = _expected_open_set(arguments.expected_open_family, known)
            actual = {decision.family_id for decision in decisions if decision.opened}
            if actual != expected:
                raise ActivationCliError("EXPECTED_OPEN_FAMILIES_MISMATCH")
            store = _store_for_record(
                Path(arguments.state_root),
                provision=arguments.provision,
                repo_root=root,
            )
            receipts = record_family_clock_activations(
                store,
                decisions,
                policy_version=policy["policy_version"],
                policy_sha256=policy_sha256,
                evaluated_at=evaluated_at,
                recorded_at=evaluated_at,
            )
            summary = _summary(
                mode="record",
                evaluated_at=evaluated_at,
                policy=policy,
                policy_sha256=policy_sha256,
                source_sha256=source_sha256,
                decisions=decisions,
                receipts=receipts,
            )
    except (
        ActivationCliError,
        FamilyClockError,
        OperationalStoreError,
        ContractValidationError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        code = getattr(exc, "code", "ACTIVATION_PRECONDITION_FAILED")
        print(f"{PROGRAM}: {code}", file=stderr)
        return EXIT_PRECONDITION_FAILED

    stdout.write(canonical_json_bytes(summary).decode("utf-8") + "\n")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
