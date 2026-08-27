#!/usr/bin/env python3
"""Create a bounded machine-readable receipt from one CI canary pack."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


GROUP = re.compile(r"^::group::([^ ]+) —")
FAILED = "CI_PACK_FAILED_JOBS="
PREWARM = "CI_CACHE_PREWARM="
EXECUTION_TIMING_SCHEMA = "ci.execution_timing.v1"
TIMING_OBSERVATION_KEYS = {
    "logical_job_id",
    "phase",
    "status",
    "started_monotonic_ns",
    "ended_monotonic_ns",
    "duration_ns",
}
TIMING_OBSERVATION_PHASES = {"dependency_install", "test"}
PHASE_MARKERS = {
    "checkout": ("checkout_start", "checkout_end"),
    "executor_setup": ("executor_setup_start", "executor_setup_end"),
    "pack_execution": ("pack_execution_start", "pack_execution_end"),
    "pack_completion": ("job_start", "job_end"),
}
MAX_TIMING_BYTES = 4 * 1024 * 1024
MAX_TIMING_RECORDS = 8_192


def trace2_fetch_seconds(path: Path | None) -> float | None:
    if path is None or not path.exists():
        return None
    command_by_sid: dict[str, str] = {}
    total = 0.0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        sid = str(event.get("sid", ""))
        if event.get("event") == "cmd_name":
            command_by_sid[sid] = str(event.get("name", ""))
        elif event.get("event") == "exit" and command_by_sid.get(sid) == "fetch":
            total += float(event.get("t_abs", 0.0))
    return round(total, 3)


def metrics(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    samples = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not samples:
        return {}
    return {
        "samples": len(samples),
        "cpu_peak_percent": max(item["cpu_percent"] for item in samples),
        "cpu_mean_percent": round(
            sum(item["cpu_percent"] for item in samples) / len(samples), 2
        ),
        "load_peak_1m": max(item["load"][0] for item in samples),
        "memory_available_min_bytes": min(
            item["memory_available_bytes"] for item in samples
        ),
        "swap_used_peak_bytes": max(item["swap_used_bytes"] for item in samples),
        "disk_free_min_bytes": min(item["disk_free_bytes"] for item in samples),
    }


def read_float(path: Path | None) -> float | None:
    if path is None or not path.exists():
        return None
    return float(path.read_text(encoding="utf-8").strip())


def _timing_warning(detail: object) -> None:
    text = " ".join(str(detail).split())[:1_024]
    print(
        "::warning title=ci timing telemetry degraded::" + text,
        flush=True,
    )


def _timing_record(
    identity: Mapping[str, Any],
    *,
    logical_job_id: str | None,
    phase: str,
    status: str,
    started_monotonic_ns: int | None = None,
    ended_monotonic_ns: int | None = None,
) -> dict[str, Any]:
    if status == "observed":
        if (
            type(started_monotonic_ns) is not int
            or type(ended_monotonic_ns) is not int
            or started_monotonic_ns < 0
            or ended_monotonic_ns < started_monotonic_ns
        ):
            raise ValueError(f"invalid monotonic bounds for {phase}")
        duration_ns: int | None = ended_monotonic_ns - started_monotonic_ns
    elif status == "missing":
        started_monotonic_ns = None
        ended_monotonic_ns = None
        duration_ns = None
    else:
        raise ValueError(f"unsupported timing status {status!r}")
    return {
        "schema": EXECUTION_TIMING_SCHEMA,
        **dict(identity),
        "logical_job_id": logical_job_id,
        "phase": phase,
        "status": status,
        "started_monotonic_ns": started_monotonic_ns,
        "ended_monotonic_ns": ended_monotonic_ns,
        "duration_ns": duration_ns,
    }


def _read_phase_markers(path: Path | None) -> dict[str, int]:
    if path is None or not path.is_file():
        raise ValueError("monotonic phase marker file is missing")
    if path.stat().st_size > 16_384:
        raise ValueError("monotonic phase marker file exceeds 16384 bytes")
    markers: dict[str, int] = {}
    expected = {name for pair in PHASE_MARKERS.values() for name in pair}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] not in expected or parts[0] in markers:
            raise ValueError("monotonic phase marker file is malformed")
        try:
            value = int(parts[1])
        except ValueError as exc:
            raise ValueError("monotonic phase marker is not an integer") from exc
        if value < 0:
            raise ValueError("monotonic phase marker is negative")
        markers[parts[0]] = value
    if set(markers) != expected:
        raise ValueError("monotonic phase marker file is incomplete")
    if any(markers[end] < markers[start] for start, end in PHASE_MARKERS.values()):
        raise ValueError("monotonic phase marker bounds are reversed")
    return markers


def _read_timing_observations(
    path: Path | None,
    *,
    selected_jobs: set[str],
) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        raise ValueError("logical-job timing observation file is missing")
    if path.stat().st_size > MAX_TIMING_BYTES:
        raise ValueError("logical-job timing observations exceed the byte bound")
    observations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        if len(observations) >= MAX_TIMING_RECORDS:
            raise ValueError("logical-job timing observations exceed the row bound")
        try:
            observation = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("logical-job timing observations are malformed JSON") from exc
        if not isinstance(observation, dict) or set(observation) != TIMING_OBSERVATION_KEYS:
            raise ValueError("logical-job timing observation has unsupported fields")
        job_id = observation.get("logical_job_id")
        phase = observation.get("phase")
        if job_id not in selected_jobs or phase not in TIMING_OBSERVATION_PHASES:
            raise ValueError("logical-job timing observation is outside the selected pack")
        if observation.get("status") != "observed":
            raise ValueError("logical-job timing observation status is not observed")
        started = observation.get("started_monotonic_ns")
        ended = observation.get("ended_monotonic_ns")
        duration = observation.get("duration_ns")
        if (
            type(started) is not int
            or type(ended) is not int
            or type(duration) is not int
            or started < 0
            or ended < started
            or duration != ended - started
        ):
            raise ValueError("logical-job timing observation has invalid bounds")
        key = (job_id, phase)
        if key in seen:
            raise ValueError("logical-job timing observation is duplicated")
        seen.add(key)
        observations.append(observation)
    if not observations:
        raise ValueError("logical-job timing observation file is empty")
    return observations


def execution_timing_records(
    *,
    plan: Mapping[str, Any],
    pack_index: int,
    runner_kind: str,
    runner_name: str,
    runner_profile: str,
    timing_observations: Path | None,
    phase_monotonic: Path | None,
) -> list[dict[str, Any]]:
    """Enrich optional process facts into one non-authoritative JSONL schema."""
    attempt_raw = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    try:
        attempt = int(attempt_raw)
        if attempt < 1:
            raise ValueError
    except ValueError:
        _timing_warning("workflow run attempt is missing or invalid; using 1")
        attempt = 1
    identity = {
        "repository": os.environ.get("GITHUB_REPOSITORY", "unknown"),
        "workflow_run_id": str(plan.get("workflow_run_id", "unknown")),
        "workflow_run_attempt": attempt,
        "subject_head_sha": plan.get("subject_head_sha"),
        "base_sha": plan.get("base_sha"),
        "tested_tree_sha": plan.get("tested_tree_sha"),
        "plan_sha256": plan.get("plan_sha256"),
        "pack_index": pack_index,
        "runner_kind": runner_kind,
        "runner_name": runner_name,
        "runner_profile": runner_profile,
    }
    packs = plan.get("packs", [])
    selected = next(
        (
            list(pack.get("jobs", []))
            for pack in packs
            if isinstance(pack, dict) and pack.get("index") == pack_index
        ),
        [],
    )
    selected_jobs = {job for job in selected if isinstance(job, str) and job}
    records = [
        _timing_record(
            identity,
            logical_job_id=None,
            phase="queue",
            status="missing",
        )
    ]

    try:
        markers = _read_phase_markers(phase_monotonic)
    except (OSError, ValueError) as exc:
        _timing_warning(exc)
        records.extend(
            _timing_record(
                identity,
                logical_job_id=None,
                phase=phase,
                status="missing",
            )
            for phase in PHASE_MARKERS
        )
    else:
        records.extend(
            _timing_record(
                identity,
                logical_job_id=None,
                phase=phase,
                status="observed",
                started_monotonic_ns=markers[start_name],
                ended_monotonic_ns=markers[end_name],
            )
            for phase, (start_name, end_name) in PHASE_MARKERS.items()
        )

    try:
        observations = _read_timing_observations(
            timing_observations,
            selected_jobs=selected_jobs,
        )
    except (OSError, ValueError) as exc:
        _timing_warning(exc)
        for job_id in selected:
            records.extend(
                _timing_record(
                    identity,
                    logical_job_id=job_id,
                    phase=phase,
                    status="missing",
                )
                for phase in ("dependency_install", "test")
            )
    else:
        seen: set[tuple[str, str]] = set()
        for observation in observations:
            records.append(
                _timing_record(
                    identity,
                    logical_job_id=observation["logical_job_id"],
                    phase=observation["phase"],
                    status="observed",
                    started_monotonic_ns=observation["started_monotonic_ns"],
                    ended_monotonic_ns=observation["ended_monotonic_ns"],
                )
            )
            seen.add((observation["logical_job_id"], observation["phase"]))
        records.extend(
            _timing_record(
                identity,
                logical_job_id=job_id,
                phase=phase,
                status="missing",
            )
            for job_id in selected
            for phase in ("dependency_install", "test")
            if (job_id, phase) not in seen
        )
    return records


def write_execution_timing(path: Path, records: list[Mapping[str, Any]]) -> None:
    """Atomically publish telemetry; failure cannot change the CI verdict."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            "".join(
                json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as exc:
        _timing_warning(f"could not publish execution timing: {exc}")
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--pack", type=int, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--tested-sha", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--runner-kind", required=True)
    parser.add_argument("--runner-name", required=True)
    parser.add_argument("--runner-profile", default="unknown")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace2", type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--checkout-seconds", type=Path)
    parser.add_argument("--dependency-seconds", type=Path)
    parser.add_argument("--test-seconds", type=Path)
    parser.add_argument("--wall-seconds", type=Path)
    parser.add_argument("--cache-before", type=Path)
    parser.add_argument("--cache-after", type=Path)
    parser.add_argument("--workspace-object-bytes", type=int, default=0)
    # Materialization-receipt amendment (2026-08-25, #6351 live-incident
    # addendum): split the shared-cache prewarm phase's own wall time out of
    # `checkout_seconds` (which otherwise mixes prewarm + candidate
    # materialization into one number), and carry a reference to the raw
    # semantic fragment this same pack invocation emitted alongside the
    # receipt so a reader can cross-check receipt identity against fragment
    # identity without re-deriving it. Both are optional: hosted-control has
    # no prewarm phase and older invocations pass neither flag.
    parser.add_argument("--prewarm-seconds", type=Path)
    parser.add_argument("--fragment", type=Path)
    parser.add_argument("--timing-observations", type=Path)
    parser.add_argument("--phase-monotonic", type=Path)
    parser.add_argument("--timing-output", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    expected = next(
        pack["jobs"] for pack in plan["packs"] if int(pack["index"]) == args.pack
    )
    executed: list[str] = []
    failed: list[str] = []
    prewarm: dict[str, object] | None = None
    for line in args.log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = GROUP.match(line)
        if match and match.group(1) not in executed:
            executed.append(match.group(1))
        if line.startswith(FAILED):
            failed = json.loads(line[len(FAILED) :])
        if line.startswith(PREWARM):
            prewarm = json.loads(line[len(PREWARM) :])
    fragment_schema = None
    fragment_plan_sha256 = None
    if args.fragment is not None and args.fragment.exists():
        fragment_document = json.loads(args.fragment.read_text(encoding="utf-8"))
        fragment_schema = fragment_document.get("schema")
        fragment_plan_sha256 = fragment_document.get("plan_sha256")
    receipt = {
        "schema": "ci.selfhosted_canary_receipt.v2",
        "runner_kind": args.runner_kind,
        "runner_name": args.runner_name,
        "tested_sha": args.tested_sha,
        "base_sha": args.base_sha,
        "pack": args.pack,
        "plan_sha256": plan["plan_sha256"],
        "logical_jobs": expected,
        "executed_jobs": sorted(executed),
        "failed_jobs": failed,
        "exit_code": args.exit_code,
        "result": "passed" if args.exit_code == 0 else "failed",
        "prewarm": prewarm,
        "prewarm_seconds": read_float(args.prewarm_seconds),
        "origin_fetch_seconds": trace2_fetch_seconds(args.trace2),
        "checkout_seconds": read_float(args.checkout_seconds),
        "dependency_seconds": read_float(args.dependency_seconds),
        "test_seconds": read_float(args.test_seconds),
        "wall_seconds": read_float(args.wall_seconds),
        "cache_bytes_before": read_float(args.cache_before),
        "cache_bytes_after": read_float(args.cache_after),
        "workspace_object_bytes": args.workspace_object_bytes,
        "resources": metrics(args.metrics),
        # Fragment reference (D, #6351): not the fragment's full body — that
        # travels as its own artifact and is what `compare_ci_canary_receipts.py`
        # diffs byte-for-byte — just enough to cross-check this receipt was
        # captured from the same pack invocation that minted it.
        "fragment_schema": fragment_schema,
        "fragment_plan_sha256": fragment_plan_sha256,
    }
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("CI_CANARY_RECEIPT=" + json.dumps(receipt, sort_keys=True), flush=True)
    if args.timing_output is not None:
        write_execution_timing(
            args.timing_output,
            execution_timing_records(
                plan=plan,
                pack_index=args.pack,
                runner_kind=args.runner_kind,
                runner_name=args.runner_name,
                runner_profile=args.runner_profile,
                timing_observations=args.timing_observations,
                phase_monotonic=args.phase_monotonic,
            ),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
