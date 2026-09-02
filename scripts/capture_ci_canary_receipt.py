#!/usr/bin/env python3
"""Create a bounded machine-readable receipt from one CI canary pack."""

from __future__ import annotations

import argparse
import contextlib
import datetime as _datetime
import json
import math
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


def load_samples(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def metrics(path: Path | None) -> dict[str, object]:
    """Host-global reduction. Deliberately unchanged by the slice extension so
    P1/P2 receipts stay byte-comparable against P3+ ones."""
    samples = load_samples(path)
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


EXPECTED_CI_SLICE = "mastermind-ci.slice"
EXPECTED_AGGREGATE_CGROUP = "/mastermind.slice/mastermind-ci.slice"
EXPECTED_AGGREGATE_LIMITS = {
    "cpu.max": "800000 100000",
    "memory.high": "10737418240",
    "memory.max": "12884901888",
    "memory.swap.max": "2147483648",
}
REQUIRED_CUMULATIVE_FIELDS = {
    "cpu": {"usage_usec", "nr_periods", "nr_throttled", "throttled_usec"},
    "memory_events": {"high", "max", "oom", "oom_kill"},
    "pids_events": {"max"},
}
REQUIRED_PRESSURE_KINDS = {
    "cpu": {"some", "full"},
    "memory": {"some", "full"},
    "io": {"some", "full"},
}
# Worst-first. One sample outside the slice poisons the whole window: a candidate
# that changed cgroups mid-run has no honest aggregate to report.
_SLICE_STATUS_PRECEDENCE = ("refused", "unavailable", "degraded", "bound")


def _empty_slice_metrics(status: str, reason: str | None, **extra: object) -> dict:
    metrics: dict[str, object] = {
        "status": status,
        "expected_slice": EXPECTED_CI_SLICE,
        "reason": reason,
        "samples": 0,
        "cgroups": [],
        "candidate_cgroups": [],
        "aggregate_cgroup": EXPECTED_AGGREGATE_CGROUP,
        "aggregate_metric_source": "parent_slice",
        "candidate_identity": None,
        "aggregate_identity": None,
        "cpu_max": None,
        "effective_limits": None,
        "cpu_delta": None,
        "memory_events_delta": None,
        "pids_events_delta": None,
        "pressure_total_delta": None,
        "memory_current_peak_bytes": None,
        "memory_swap_peak_bytes": None,
        "memory_peak_bytes_cgroup_lifetime": None,
        "memory_peak_is_run_local": False,
        "pids_current_peak": None,
    }
    metrics.update(extra)
    return metrics


def _keyed_delta(first: Mapping[str, Any] | None, last: Mapping[str, Any] | None):
    """Per-key window delta, or None for a key absent at t0.

    `last - first.get(key, 0)` would present a cgroup LIFETIME TOTAL as a window
    delta whenever the kernel did not expose the field at t0 -- and these are
    exactly the inputs to the acceptance rule
    nr_throttled_delta / nr_periods_delta <= 0.25. Absent is unknown, not zero.
    """
    if not isinstance(first, Mapping) or not isinstance(last, Mapping):
        return None
    delta: dict[str, int | None] = {}
    for key, value in last.items():
        if not isinstance(value, int):
            continue
        previous = first.get(key)
        delta[key] = value - previous if isinstance(previous, int) else None
    return delta


def _peak(values: list[Any]) -> int | None:
    observed = [item for item in values if isinstance(item, int)]
    return max(observed) if observed else None


def _valid_identity(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"device", "inode"}
        and all(
            isinstance(value[key], int)
            and not isinstance(value[key], bool)
            and value[key] >= 0
            for key in ("device", "inode")
        )
    )


def _direct_candidate_cgroup(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("/") or value.endswith("/") or "//" in value:
        return False
    components = [item for item in value.split("/") if item]
    prefix = ["mastermind.slice", "mastermind-ci.slice"]
    return (
        len(components) == 3
        and components[:2] == prefix
        and len(components[2]) > len(".service")
        and components[2].endswith(".service")
        and components[2] not in {".", ".."}
    )


def _valid_cumulative_mapping(value: object, required: set[str]) -> bool:
    return isinstance(value, Mapping) and required.issubset(value) and all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 0
        for item in value.values()
    )


def _invalid_bound_observation(item: Mapping[str, Any]) -> str | None:
    if item.get("expected_slice") != EXPECTED_CI_SLICE:
        return "slice observation names the wrong expected slice"
    if item.get("aggregate_metric_source") != "parent_slice":
        return "aggregate metrics are not explicitly sourced from the parent slice"
    if item.get("aggregate_cgroup") != EXPECTED_AGGREGATE_CGROUP:
        return "aggregate cgroup is missing or not the fixed parent slice"
    if item.get("cgroup") != item.get("candidate_cgroup") or not _direct_candidate_cgroup(item.get("candidate_cgroup")):
        return "candidate cgroup is missing, mixed, or not an exact direct service"
    if not _valid_identity(item.get("candidate_identity")):
        return "candidate cgroup identity is missing or malformed"
    if not _valid_identity(item.get("aggregate_identity")):
        return "aggregate cgroup identity is missing or malformed"
    if item.get("limits") != EXPECTED_AGGREGATE_LIMITS:
        return "aggregate parent limits are missing, malformed, or drifted"
    for field, required in REQUIRED_CUMULATIVE_FIELDS.items():
        if not _valid_cumulative_mapping(item.get(field), required):
            return f"{field} cumulative evidence is missing or malformed"
    pressure = item.get("pressure")
    if not isinstance(pressure, Mapping):
        return "pressure cumulative evidence is missing or malformed"
    for resource, required_kinds in REQUIRED_PRESSURE_KINDS.items():
        kinds = pressure.get(resource)
        if not isinstance(kinds, Mapping):
            return "pressure cumulative evidence is malformed"
        if not required_kinds.issubset(kinds):
            return "pressure cumulative evidence is missing required kinds"
        for kind in required_kinds:
            values = kinds.get(kind)
            if not isinstance(values, Mapping):
                return "pressure cumulative evidence is malformed"
            total = values.get("total")
            if (
                not isinstance(total, (int, float))
                or isinstance(total, bool)
                or not math.isfinite(total)
                or total < 0
            ):
                return "pressure cumulative evidence is malformed"
    return None


def _counter_decreased(first: Mapping[str, Any], last: Mapping[str, Any]) -> bool:
    for field in ("cpu", "memory_events", "pids_events"):
        before, after = first.get(field), last.get(field)
        if isinstance(before, Mapping) and isinstance(after, Mapping):
            for key, value in after.items():
                if isinstance(value, int) and isinstance(before.get(key), int) and value < before[key]:
                    return True
    before_pressure, after_pressure = first.get("pressure"), last.get("pressure")
    if isinstance(before_pressure, Mapping) and isinstance(after_pressure, Mapping):
        for resource, kinds in after_pressure.items():
            base = before_pressure.get(resource)
            if not isinstance(kinds, Mapping) or not isinstance(base, Mapping):
                continue
            for kind, values in kinds.items():
                prior_values = base.get(kind)
                if not isinstance(values, Mapping) or not isinstance(prior_values, Mapping):
                    continue
                current, previous = values.get("total"), prior_values.get("total")
                if isinstance(current, (int, float)) and isinstance(previous, (int, float)) and current < previous:
                    return True
    return False


def slice_metrics(samples: list[Mapping[str, Any]]) -> dict:
    """Reduce aggregate CI-slice samples into one bounded receipt section.

    Fail-closed by construction: aggregate numbers are reported ONLY when every
    sample in the window was cleanly bound to the expected slice. A refused,
    degraded, unavailable or absent window yields its status and no numbers, so
    a downstream acceptance threshold can never be evaluated against evidence
    that did not actually come from the CI slice.
    """

    if not samples:
        return _empty_slice_metrics(
            "absent", "no aggregate CI-slice evidence in this metrics stream"
        )
    observations = [
        sample.get("slice")
        for sample in samples
        if isinstance(sample, Mapping) and isinstance(sample.get("slice"), Mapping)
    ]
    if not observations:
        # Either no run at all, or a pre-slice P1/P2 metrics file. Absent is the
        # honest answer; it is not a passing observation.
        return _empty_slice_metrics(
            "absent", "no aggregate CI-slice evidence in this metrics stream"
        )
    if len(observations) != len(samples):
        return _empty_slice_metrics(
            "refused",
            "every host sample in a slice window must carry a slice mapping",
            samples=len(observations),
        )

    sample_times = [sample.get("time") for sample in samples]
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        for value in sample_times
    ) or any(later <= earlier for earlier, later in zip(sample_times, sample_times[1:])):
        return _empty_slice_metrics(
            "refused", "aggregate samples are not strictly time ordered", samples=len(observations)
        )

    statuses = {str(item.get("status")) for item in observations}
    cgroups = sorted(
        {str(item.get("cgroup")) for item in observations if item.get("cgroup")}
    )
    candidate_cgroups = sorted(
        {str(item.get("candidate_cgroup")) for item in observations if item.get("candidate_cgroup")}
    )
    # Anything that is not exactly "bound" is non-bound. This scanned a fixed
    # whitelist first, so a sample carrying any other status string was invisible
    # and the window resolved to "bound" -- leaking foreign host numbers into
    # aggregate fields and falsifying this docstring.
    unbound = statuses - {"bound"}
    if unbound:
        worst = next(
            (status for status in _SLICE_STATUS_PRECEDENCE if status in unbound),
            "unavailable",
        )
    elif len(cgroups) > 1:
        # All samples bound, but not to the SAME cgroup: the candidate moved
        # mid-run, so first/last deltas would straddle two different cgroups.
        return _empty_slice_metrics(
            "refused",
            f"window spans {len(cgroups)} distinct cgroups {cgroups}; "
            "no honest aggregate exists across a mid-run cgroup change",
            samples=len(observations),
            cgroups=cgroups,
        )
    else:
        worst = "bound"
    if worst != "bound":
        reason = next(
            (
                str(item.get("reason"))
                for item in observations
                if item.get("status") == worst and item.get("reason")
            ),
            f"aggregate CI-slice evidence is {worst}",
        )
        return _empty_slice_metrics(
            worst, reason, samples=len(observations), cgroups=cgroups
        )

    for item in observations:
        invalid = _invalid_bound_observation(item)
        if invalid is not None:
            return _empty_slice_metrics(
                "refused", invalid, samples=len(observations), cgroups=cgroups,
                candidate_cgroups=candidate_cgroups,
            )
    candidate_identities = {json.dumps(item.get("candidate_identity"), sort_keys=True) for item in observations}
    aggregate_identities = {json.dumps(item.get("aggregate_identity"), sort_keys=True) for item in observations}
    aggregate_cgroups = {item.get("aggregate_cgroup") for item in observations}
    limit_snapshots = {json.dumps(item.get("limits"), sort_keys=True) for item in observations}
    if (
        len(candidate_cgroups) != 1
        or len(candidate_identities) != 1
        or len(aggregate_identities) != 1
        or aggregate_cgroups != {EXPECTED_AGGREGATE_CGROUP}
        or len(limit_snapshots) != 1
    ):
        return _empty_slice_metrics(
            "refused", "candidate, parent identity, or envelope changed within the window",
            samples=len(observations), cgroups=cgroups, candidate_cgroups=candidate_cgroups,
        )
    if any(
        _counter_decreased(previous, current)
        for previous, current in zip(observations, observations[1:])
    ):
        return _empty_slice_metrics(
            "refused", "aggregate cumulative counter decreased",
            samples=len(observations), cgroups=cgroups,
        )

    first, last = observations[0], observations[-1]
    pressure_delta: dict[str, dict[str, int]] = {}
    first_pressure = first.get("pressure") or {}
    last_pressure = last.get("pressure") or {}
    if isinstance(first_pressure, Mapping) and isinstance(last_pressure, Mapping):
        for resource, kinds in last_pressure.items():
            if not isinstance(kinds, Mapping):
                continue
            base = first_pressure.get(resource) or {}
            deltas = {}
            for kind, values in kinds.items():
                if not isinstance(values, Mapping) or "total" not in values:
                    continue
                # Same rule as _keyed_delta: a resource absent at t0 has an
                # unknown delta, not a delta equal to its lifetime total.
                previous = (base.get(kind) or {}).get("total")
                deltas[kind] = (
                    int(values["total"]) - int(previous)
                    if isinstance(previous, (int, float))
                    else None
                )
            if deltas:
                pressure_delta[resource] = deltas

    return {
        "status": "bound",
        "expected_slice": EXPECTED_CI_SLICE,
        "reason": None,
        "samples": len(observations),
        "cgroups": cgroups,
        "candidate_cgroups": candidate_cgroups,
        "aggregate_cgroup": EXPECTED_AGGREGATE_CGROUP,
        "aggregate_metric_source": "parent_slice",
        "candidate_identity": last.get("candidate_identity"),
        "aggregate_identity": last.get("aggregate_identity"),
        "cpu_max": last.get("cpu_max"),
        "effective_limits": last.get("limits"),
        "cpu_delta": _keyed_delta(first.get("cpu"), last.get("cpu")),
        "memory_events_delta": _keyed_delta(
            first.get("memory_events"), last.get("memory_events")
        ),
        "pids_events_delta": _keyed_delta(
            first.get("pids_events"), last.get("pids_events")
        ),
        "pressure_total_delta": pressure_delta or None,
        "memory_current_peak_bytes": _peak(
            [(item.get("memory") or {}).get("current") for item in observations]
        ),
        "memory_swap_peak_bytes": _peak(
            [(item.get("memory") or {}).get("swap_current") for item in observations]
        ),
        # cgroup lifetime, NOT this run's peak — the counter is only reset by a
        # privileged ceremony, which this carrier does not perform.
        "memory_peak_bytes_cgroup_lifetime": _peak(
            [(item.get("memory") or {}).get("peak") for item in observations]
        ),
        "memory_peak_is_run_local": False,
        "pids_current_peak": _peak(
            [(item.get("pids") or {}).get("current") for item in observations]
        ),
    }


def _parse_timestamp(value: str | None) -> "_datetime.datetime | None":
    """Parse one ISO-8601 instant, or None. Unparseable is unavailable, not zero."""
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return _datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def build_identity_fields(
    execution_profile_id: str | None,
    admission_policy_version: str | None,
    workflow_job_queued_at: str | None,
    runner_job_started_at: str | None,
) -> dict:
    """Forward-compatible receipt identities for later four-slot/elastic evidence.

    Purely additive: the schema stays ci.selfhosted_canary_receipt.v2, no
    existing key changes name or meaning, and a historical P1/P2/P4 receipt
    simply lacks these keys. The comparator's parity allowlist does not read
    them, so hosted-vs-selfhosted comparison is untouched.

    `queue_wait_seconds` is DERIVED, never supplied: it exists only when both
    timestamps are present, parseable and correctly ordered. Absent, unparseable
    or out-of-order all yield None -- never 0, and never a negative duration. An
    observed 0.0 (picked up in the same second) is a real measurement and stays
    distinct from None.

    Queue wait is time BEFORE the runner picked the job up. It is deliberately
    computed from nothing else here, so it can never be folded into the
    checkout / dependency / test / wall execution timings.
    """

    queued = _parse_timestamp(workflow_job_queued_at)
    started = _parse_timestamp(runner_job_started_at)
    queue_wait = None
    if queued is not None and started is not None:
        if queued.tzinfo is None or started.tzinfo is None:
            queue_wait = None
        else:
            delta = (started - queued).total_seconds()
            queue_wait = round(delta, 3) if delta >= 0 else None
    return {
        "execution_profile_id": execution_profile_id,
        "admission_policy_version": admission_policy_version,
        "workflow_job_queued_at": workflow_job_queued_at or None,
        "runner_job_started_at": runner_job_started_at or None,
        "queue_wait_seconds": queue_wait,
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
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ValueError("logical-job timing observations are malformed JSON") from exc
        if not isinstance(observation, dict) or set(observation) != TIMING_OBSERVATION_KEYS:
            raise ValueError("logical-job timing observation has unsupported fields")
        job_id = observation.get("logical_job_id")
        phase = observation.get("phase")
        if not isinstance(job_id, str) or not isinstance(phase, str):
            raise ValueError("logical-job timing observation fields must be strings")
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
    # Forward-compatible identities (Sol ruling 2026-09-01). All optional and
    # null-preserving: C3R-A does not obtain live GitHub job metadata, it only
    # proves the existing receipt contract can carry it truthfully later.
    parser.add_argument("--execution-profile-id", default=None)
    parser.add_argument("--admission-policy-version", default=None)
    parser.add_argument("--workflow-job-queued-at", default=None)
    parser.add_argument("--runner-job-started-at", default=None)
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
        # Aggregate CI-slice evidence (C3R-A). Additive: the host-global
        # "resources" block above is untouched, and the comparator's field
        # allowlist does not read this key, so hosted receipts (which have no
        # mastermind-ci.slice) stay comparable to self-hosted ones.
        "ci_slice": slice_metrics(load_samples(args.metrics)),
        # Fragment reference (D, #6351): not the fragment's full body — that
        # travels as its own artifact and is what `compare_ci_canary_receipts.py`
        # diffs byte-for-byte — just enough to cross-check this receipt was
        # captured from the same pack invocation that minted it.
        "fragment_schema": fragment_schema,
        "fragment_plan_sha256": fragment_plan_sha256,
        **build_identity_fields(
            execution_profile_id=args.execution_profile_id,
            admission_policy_version=args.admission_policy_version,
            workflow_job_queued_at=args.workflow_job_queued_at,
            runner_job_started_at=args.runner_job_started_at,
        ),
    }
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("CI_CANARY_RECEIPT=" + json.dumps(receipt, sort_keys=True), flush=True)
    if args.timing_output is not None:
        try:
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
        except Exception as exc:  # telemetry must not alter the written receipt
            _timing_warning(f"could not generate execution timing: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
