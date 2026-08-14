#!/usr/bin/env python3
"""Collect strict packed-CI evidence without inferring failure causation.

``pack`` converts one pack log into the pack object accepted by
``ci_failure_summary.py``. ``run`` reconciles those objects against the exact
planner matrix and emits one complete ``ci.failure_evidence.v1`` document.
Malformed, duplicate, stale, or out-of-matrix evidence is rejected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

if __package__:
    from . import ci_failure_summary as SUMMARY
else:
    import ci_failure_summary as SUMMARY


FAILED_JOBS_MARKER = "CI_PACK_FAILED_JOBS="
MISSING_ARTIFACT_DETAIL = "expected pack record is missing"


class CollectorError(ValueError):
    """Collector input is missing, malformed, contradictory, or stale."""


def _compact(document: Mapping[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"))


def _terminal_outcome(value: object, label: str) -> str:
    if type(value) is not str or value not in SUMMARY.TERMINAL_OUTCOMES:
        raise CollectorError(f"{label} must be a terminal outcome")
    return value


def _pack_index(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise CollectorError(f"{label} must be a non-negative integer")
    return value


def _decode_json(raw: str, label: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CollectorError(
            f"{label} is not valid JSON at line {exc.lineno} column {exc.colno}"
        ) from exc


def _failure(
    logical_job_id: str | None,
    kind: str,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "logical_job_id": logical_job_id,
        "kind": kind,
        "base_reproduced": None,
        "detail": detail,
    }


def _validate_pack_record(record: object, label: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise CollectorError(f"{label} must be an object")
    candidate = dict(record)
    try:
        SUMMARY.validate_evidence(
            {
                "schema": SUMMARY.INPUT_SCHEMA,
                "superseded": False,
                "planner": {"outcome": "success", "detail": None},
                "packs": [candidate],
            }
        )
    except SUMMARY.EvidenceError as exc:
        raise CollectorError(f"{label} is invalid: {exc}") from exc
    return candidate


def _read_pack_log(path: str, outcome: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        if outcome not in SUMMARY.CLEAR_OUTCOMES:
            return ""
        raise CollectorError(f"pack log does not exist: {path}") from exc
    except OSError as exc:
        raise CollectorError(f"cannot read pack log {path!r}: {exc}") from exc


def collect_pack_record(pack_index: int, outcome: str, log: str) -> dict[str, Any]:
    """Build one validated pack record from a terminal outcome and raw log."""
    index = _pack_index(pack_index, "pack index")
    terminal = _terminal_outcome(outcome, "pack outcome")
    markers: list[tuple[int, str]] = []
    for line_number, line in enumerate(log.splitlines(), start=1):
        if line.startswith(FAILED_JOBS_MARKER):
            markers.append((line_number, line[len(FAILED_JOBS_MARKER) :]))
    if len(markers) > 1:
        raise CollectorError("pack log contains more than one CI_PACK_FAILED_JOBS marker")

    failed_ids: list[str] | None = None
    if markers:
        line_number, raw_ids = markers[0]
        decoded = _decode_json(raw_ids, f"failed-jobs marker on line {line_number}")
        if not isinstance(decoded, list):
            raise CollectorError("CI_PACK_FAILED_JOBS value must be a JSON array")
        failed_ids = []
        seen: set[str] = set()
        for position, logical_id in enumerate(decoded):
            if type(logical_id) is not str:
                raise CollectorError(
                    f"CI_PACK_FAILED_JOBS[{position}] must be a logical job id string"
                )
            if logical_id in seen:
                raise CollectorError(
                    f"CI_PACK_FAILED_JOBS contains duplicate logical job id {logical_id!r}"
                )
            seen.add(logical_id)
            failed_ids.append(logical_id)
        failed_ids.sort()

    if terminal in SUMMARY.CLEAR_OUTCOMES:
        if failed_ids is None:
            raise CollectorError(
                f"pack outcome {terminal!r} requires exactly one CI_PACK_FAILED_JOBS marker"
            )
        failures = [_failure(logical_id, "unknown") for logical_id in failed_ids]
    elif failed_ids:
        failures = [_failure(logical_id, "unknown") for logical_id in failed_ids]
    else:
        detail = (
            f"pack outcome {terminal} has no CI_PACK_FAILED_JOBS marker"
            if failed_ids is None
            else f"pack outcome {terminal} reported no logical job ids"
        )
        failures = [_failure(None, "infrastructure", detail)]

    return _validate_pack_record(
        {"pack": index, "outcome": terminal, "failures": failures},
        f"pack {index} record",
    )


def parse_expected_matrix(raw: str) -> list[int]:
    """Parse the planner's exact ``{"include":[{"pack":N}]}`` matrix."""
    decoded = _decode_json(raw, "expected matrix")
    if not isinstance(decoded, Mapping) or set(decoded) != {"include"}:
        raise CollectorError("expected matrix must contain exactly the field 'include'")
    included = decoded["include"]
    if not isinstance(included, list):
        raise CollectorError("expected matrix include must be a list")
    packs: list[int] = []
    seen: set[int] = set()
    for position, item in enumerate(included):
        if not isinstance(item, Mapping) or set(item) != {"pack"}:
            raise CollectorError(
                f"expected matrix include[{position}] must contain exactly the field 'pack'"
            )
        index = _pack_index(item["pack"], f"expected matrix include[{position}].pack")
        if index in seen:
            raise CollectorError(f"expected matrix contains duplicate pack {index}")
        seen.add(index)
        packs.append(index)
    return sorted(packs)


def _read_record(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CollectorError(f"cannot read pack record {path.name!r}: {exc}") from exc
    if not raw.strip():
        raise CollectorError(f"pack record {path.name!r} is empty")
    return _validate_pack_record(_decode_json(raw, f"pack record {path.name!r}"), path.name)


def collect_run_evidence(
    planner_outcome: str,
    expected_matrix_json: str,
    records_dir: Path,
    *,
    planner_detail: str | None = None,
    superseded: bool = False,
) -> dict[str, Any]:
    """Reconcile pack records against a planner matrix and validate the result."""
    outcome = _terminal_outcome(planner_outcome, "planner outcome")
    expected = parse_expected_matrix(expected_matrix_json)
    if not records_dir.is_dir():
        raise CollectorError(f"records directory does not exist: {records_dir}")

    records: dict[int, dict[str, Any]] = {}
    for path in sorted(records_dir.glob("*.json"), key=lambda item: item.name):
        record = _read_record(path)
        index = record["pack"]
        if index in records:
            raise CollectorError(f"pack {index} appears in more than one record artifact")
        if index not in expected:
            raise CollectorError(f"pack {index} record is outside the expected matrix")
        records[index] = record

    for index in expected:
        if index not in records:
            records[index] = {
                "pack": index,
                "outcome": "startup_failure",
                "failures": [_failure(None, "infrastructure", MISSING_ARTIFACT_DETAIL)],
            }

    document = {
        "schema": SUMMARY.INPUT_SCHEMA,
        "superseded": superseded,
        "planner": {"outcome": outcome, "detail": planner_detail},
        "packs": [records[index] for index in sorted(records)],
    }
    try:
        SUMMARY.validate_evidence(document)
    except SUMMARY.EvidenceError as exc:
        raise CollectorError(f"assembled failure evidence is invalid: {exc}") from exc
    return document


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    pack = commands.add_parser("pack", help="collect one pack record")
    pack.add_argument("--pack-index", required=True, type=int)
    pack.add_argument("--outcome", required=True)
    pack.add_argument("--log", required=True, help="pack log path, or '-' for stdin")

    run = commands.add_parser("run", help="assemble one run evidence document")
    run.add_argument("--planner-outcome", required=True)
    run.add_argument("--planner-detail")
    run.add_argument("--expected-matrix-json", required=True)
    run.add_argument("--records-dir", required=True, type=Path)
    run.add_argument("--superseded", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "pack":
            document = collect_pack_record(
                args.pack_index,
                args.outcome,
                _read_pack_log(args.log, args.outcome),
            )
        else:
            document = collect_run_evidence(
                args.planner_outcome,
                args.expected_matrix_json,
                args.records_dir,
                planner_detail=args.planner_detail,
                superseded=args.superseded,
            )
    except CollectorError as exc:
        print(f"ci evidence collector: {exc}", file=sys.stderr)
        return 2
    print(_compact(document), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
