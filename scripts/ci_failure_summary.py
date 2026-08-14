#!/usr/bin/env python3
"""Emit one strict, machine-readable CI failure summary.

This is an evidence normalizer, not a log parser. Pack indices move, and one
logical job can contain both a base failure and a new PR failure. Callers must
therefore describe each failure as logical/infrastructure/flaky/unknown; logical
failures must also say whether that specific failure reproduced on base.

Input (``ci.failure_evidence.v1``)::

    {"schema":"ci.failure_evidence.v1","superseded":false,
     "planner":{"outcome":"success","detail":null},
     "packs":[{"pack":0,"outcome":"failure","failures":[
       {"logical_job_id":"workflow-yaml","kind":"logical",
        "base_reproduced":false,"detail":"new suite is unwired"}]}]}

Valid evidence exits 0, even when it describes a red run. Malformed or
contradictory evidence emits a ``planner_config`` summary and exits 2.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

INPUT_SCHEMA = "ci.failure_evidence.v1"
OUTPUT_SCHEMA = "ci.failure_summary.v1"
CATEGORIES = (
    "pr_caused",
    "inherited_base",
    "infrastructure",
    "flaky_unknown",
    "superseded",
    "planner_config",
)
FAILURE_KINDS = frozenset({"logical", "infrastructure", "flaky", "unknown"})
TERMINAL_OUTCOMES = frozenset(
    {
        "success", "failure", "cancelled", "timed_out", "skipped", "neutral",
        "action_required", "stale", "startup_failure",
    }
)
CLEAR_OUTCOMES = frozenset({"success", "skipped", "neutral"})
SUPERSESSION_OUTCOMES = frozenset({"cancelled", "stale"})

_TOP_KEYS = frozenset({"schema", "superseded", "planner", "packs"})
_PLANNER_KEYS = frozenset({"outcome", "detail"})
_PACK_KEYS = frozenset({"pack", "outcome", "failures"})
_FAILURE_KEYS = frozenset(
    {"logical_job_id", "kind", "base_reproduced", "detail"}
)
_JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}")
_PRIMARY_ORDER = {
    "pr_caused": 0,
    "planner_config": 1,
    "infrastructure": 2,
    "inherited_base": 3,
    "flaky_unknown": 4,
    "superseded": 5,
}
_ACTIONABLE_ORDER = {
    "pr_caused": 0,
    "inherited_base": 1,
    "flaky_unknown": 2,
    "infrastructure": 3,
}


class EvidenceError(ValueError):
    """Input evidence is malformed or contradictory."""


def _object(value: object, label: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != keys:
        parts = []
        if keys - actual:
            parts.append("missing " + ", ".join(sorted(keys - actual)))
        if actual - keys:
            parts.append("unexpected " + ", ".join(sorted(actual - keys)))
        raise EvidenceError(f"{label} fields are invalid: {'; '.join(parts)}")
    return value


def _outcome(value: object, label: str) -> str:
    if type(value) is not str or value not in TERMINAL_OUTCOMES:
        raise EvidenceError(f"{label} must be a terminal outcome")
    return value


def _detail(value: object, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > 1000:
        raise EvidenceError(f"{label} must be a string of at most 1000 characters or null")
    return value


def _logical_job_id(value: object, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not _JOB_ID.fullmatch(value):
        raise EvidenceError(f"{label} must be null or a 1-200 character logical job id")
    return value


def _one_line(value: str, limit: int = 240) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."


def validate_evidence(document: object) -> dict[str, Any]:
    """Return normalized evidence or raise ``EvidenceError``."""
    top = _object(document, "evidence", _TOP_KEYS)
    if top["schema"] != INPUT_SCHEMA:
        raise EvidenceError(f"evidence schema must be {INPUT_SCHEMA!r}")
    if type(top["superseded"]) is not bool:
        raise EvidenceError("evidence superseded must be a boolean")
    superseded = top["superseded"]

    raw_planner = _object(top["planner"], "planner", _PLANNER_KEYS)
    planner = {
        "outcome": _outcome(raw_planner["outcome"], "planner outcome"),
        "detail": _detail(raw_planner["detail"], "planner detail"),
    }
    if not isinstance(top["packs"], list):
        raise EvidenceError("packs must be a list")

    packs: list[dict[str, Any]] = []
    seen_packs: set[int] = set()
    job_packs: dict[str, int] = {}
    seen_failures: set[tuple[object, ...]] = set()
    for position, value in enumerate(top["packs"]):
        raw_pack = _object(value, f"packs[{position}]", _PACK_KEYS)
        index = raw_pack["pack"]
        if type(index) is not int or index < 0:
            raise EvidenceError(f"packs[{position}].pack must be a non-negative integer")
        if index in seen_packs:
            raise EvidenceError(f"pack {index} appears more than once")
        seen_packs.add(index)
        outcome = _outcome(raw_pack["outcome"], f"pack {index} outcome")
        raw_failures = raw_pack["failures"]
        if not isinstance(raw_failures, list):
            raise EvidenceError(f"pack {index} failures must be a list")
        if outcome in CLEAR_OUTCOMES and raw_failures:
            raise EvidenceError(f"pack {index} outcome {outcome!r} cannot carry failures")
        if (
            outcome not in CLEAR_OUTCOMES
            and not raw_failures
            and not (superseded and outcome in SUPERSESSION_OUTCOMES)
        ):
            raise EvidenceError(f"pack {index} outcome {outcome!r} requires failure evidence")

        failures = []
        for failure_position, failure_value in enumerate(raw_failures):
            raw = _object(
                failure_value,
                f"pack {index} failures[{failure_position}]",
                _FAILURE_KEYS,
            )
            kind = raw["kind"]
            if type(kind) is not str or kind not in FAILURE_KINDS:
                raise EvidenceError(f"pack {index} failure kind is invalid")
            job = _logical_job_id(raw["logical_job_id"], f"pack {index} logical_job_id")
            base = raw["base_reproduced"]
            if kind == "logical" and job is None:
                raise EvidenceError(f"pack {index} logical failure requires a logical_job_id")
            if kind == "logical" and type(base) is not bool:
                raise EvidenceError(
                    f"pack {index} logical failure requires boolean base_reproduced evidence"
                )
            if kind != "logical" and base is not None:
                raise EvidenceError(
                    f"pack {index} {kind} failure must set base_reproduced to null"
                )
            detail = _detail(raw["detail"], f"pack {index} failure detail")
            identity = (index, job, kind, base, detail)
            if identity in seen_failures:
                raise EvidenceError(f"pack {index} contains duplicate failure evidence")
            seen_failures.add(identity)
            if job is not None:
                prior = job_packs.setdefault(job, index)
                if prior != index:
                    raise EvidenceError(f"logical job {job!r} appears in packs {prior} and {index}")
            category = (
                "inherited_base" if base else "pr_caused"
            ) if kind == "logical" else (
                "infrastructure" if kind == "infrastructure" else "flaky_unknown"
            )
            failures.append({"logical_job_id": job, "category": category, "detail": detail})
        packs.append({"pack": index, "outcome": outcome, "failures": failures})

    if planner["outcome"] != "success" and packs:
        raise EvidenceError("packs must be empty when the planner did not succeed")
    if superseded and not (
        planner["outcome"] in SUPERSESSION_OUTCOMES
        or any(pack["outcome"] in SUPERSESSION_OUTCOMES for pack in packs)
    ):
        raise EvidenceError("superseded evidence requires a cancelled or stale outcome")
    return {
        "superseded": superseded,
        "planner": planner,
        "packs": sorted(packs, key=lambda item: item["pack"]),
    }


def _record(
    category: str,
    job: str | None = None,
    pack: int | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "logical_job_id": job,
        "pack": pack,
        "detail": None if detail is None else _one_line(detail),
    }


def _summary(
    planner_outcome: str,
    pack_outcomes: Mapping[str, int],
    records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    failures = sorted(
        records,
        key=lambda item: (
            _PRIMARY_ORDER[item["category"]],
            item["pack"] is None,
            -1 if item["pack"] is None else item["pack"],
            item["logical_job_id"] is None,
            item["logical_job_id"] or "",
        ),
    )
    counts = {category: 0 for category in CATEGORIES}
    for failure in failures:
        counts[failure["category"]] += 1
    actionable = sorted(
        (
            failure for failure in failures
            if failure["logical_job_id"] is not None
            and failure["category"] in _ACTIONABLE_ORDER
        ),
        key=lambda item: (
            _ACTIONABLE_ORDER[item["category"]],
            item["pack"] is None,
            -1 if item["pack"] is None else item["pack"],
            item["logical_job_id"],
        ),
    )
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "failure" if failures else "clear",
        "primary_category": failures[0]["category"] if failures else None,
        "first_actionable_failure": actionable[0] if actionable else None,
        "category_counts": counts,
        "planner_outcome": planner_outcome,
        "pack_outcomes": dict(sorted(pack_outcomes.items())),
        "failures": failures,
    }


def classify_evidence(document: object) -> dict[str, Any]:
    """Classify a validated evidence document."""
    evidence = validate_evidence(document)
    planner, packs = evidence["planner"], evidence["packs"]
    outcomes = Counter(pack["outcome"] for pack in packs)
    if evidence["superseded"]:
        cancelled_pack = next(
            (pack["pack"] for pack in packs if pack["outcome"] in SUPERSESSION_OUTCOMES),
            None,
        )
        return _summary(
            planner["outcome"], outcomes,
            [_record("superseded", pack=cancelled_pack,
                     detail="run was cancelled or made stale by a newer head")],
        )
    if planner["outcome"] != "success":
        return _summary(
            planner["outcome"], outcomes,
            [_record("planner_config",
                     detail=planner["detail"] or f"planner outcome was {planner['outcome']}")],
        )
    records = [
        _record(failure["category"], failure["logical_job_id"], pack["pack"], failure["detail"])
        for pack in packs for failure in pack["failures"]
    ]
    return _summary(planner["outcome"], outcomes, records)


def malformed_summary(message: str) -> dict[str, Any]:
    return _summary(
        "invalid", {},
        [_record("planner_config", detail="malformed failure evidence: " + _one_line(message))],
    )


def _read(path: str) -> object:
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise EvidenceError(f"cannot read evidence: {exc}") from exc
    if not raw.strip():
        raise EvidenceError("evidence is empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EvidenceError(
            f"evidence is not valid JSON at line {exc.lineno} column {exc.colno}"
        ) from exc


def _emit(summary: Mapping[str, Any]) -> None:
    print(json.dumps(summary, ensure_ascii=True, separators=(",", ":")), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, help="evidence JSON file, or '-' for stdin")
    args = parser.parse_args(argv)
    try:
        summary = classify_evidence(_read(args.input))
    except EvidenceError as exc:
        _emit(malformed_summary(str(exc)))
        return 2
    _emit(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
