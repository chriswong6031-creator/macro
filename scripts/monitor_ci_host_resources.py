#!/usr/bin/env python3
"""Write bounded, non-secret host resource samples for a CI canary.

Also emits AGGREGATE cgroup-v2 evidence for the one CI-only slice. Once four CI
candidates share a single enforced envelope, host-global numbers stop being
evidence: they cannot distinguish "CI stayed inside its budget" from "the guest
happened to be quiet", and they say nothing at all about whether the renderer
stayed outside the slice.

Each candidate therefore derives its OWN cgroup from /proc/self/cgroup and must
bind to the immutable ``/mastermind-ci.slice/<unit>.service`` hierarchy. A
candidate still sitting in ``system.slice``, in a foreign slice, or with
unreadable slice files produces an explicit ``refused``/``degraded`` sample with
no metric values at all — never a host-global substitute. A green produced from
the wrong cgroup is worse than a missing green, because downstream it reads as
proof.

Kernel fields that are absent are reported as ``None`` and are never collapsed
into ``0``; ``memory.peak`` is a cgroup-LIFETIME high-water mark, not a
run-local peak, and the receipt reducer labels it as such.

This stays a self-contained stdlib-only script: the canary copies it alone into
a trusted-control directory outside the untrusted candidate checkout, exactly
like scripts/select_ci_canary_packs.py and scripts/resolve_ci_canary_ref.py, so
it must never import a sibling module.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path


EXPECTED_SLICE = "mastermind-ci.slice"

_SLICE_INT_FILES = {
    "memory.current": ("memory", "current"),
    "memory.peak": ("memory", "peak"),
    "memory.swap.current": ("memory", "swap_current"),
    "pids.current": ("pids", "current"),
}
_SLICE_KEYED_FILES = {
    "cpu.stat": "cpu",
    "memory.events": "memory_events",
    "pids.events": "pids_events",
}
_SLICE_PRESSURE_FILES = {
    "cpu.pressure": "cpu",
    "memory.pressure": "memory",
    "io.pressure": "io",
}

running = True


def stop(_signum: int, _frame: object) -> None:
    global running
    running = False


def meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        name, raw = line.split(":", 1)
        result[name] = int(raw.strip().split()[0]) * 1024
    return result


def cpu_times() -> tuple[int, int]:
    fields = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()
    values = [int(item) for item in fields[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return idle, sum(values)


def _read_text(path: Path) -> str | None:
    """Return file text, or None when the kernel does not expose the field.

    None means UNAVAILABLE and is never collapsed into 0 downstream.
    """

    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_int(path: Path) -> int | None:
    raw = _read_text(path)
    if raw is None:
        return None
    raw = raw.strip()
    # cgroup writes the literal "max" for an unset ceiling; that is not a count.
    if not raw or raw == "max":
        return None
    try:
        return int(raw.split()[0])
    except ValueError:
        return None


def _read_keyed(path: Path) -> dict[str, int] | None:
    raw = _read_text(path)
    if raw is None:
        return None
    values: dict[str, int] = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            values[fields[0]] = int(fields[1])
        except ValueError:
            continue
    return values or None


def _read_pressure(path: Path) -> dict[str, dict[str, float]] | None:
    raw = _read_text(path)
    if raw is None:
        return None
    values: dict[str, dict[str, float]] = {}
    for line in raw.splitlines():
        fields = line.split()
        if not fields:
            continue
        kind = fields[0]
        parsed: dict[str, float] = {}
        for item in fields[1:]:
            if "=" not in item:
                continue
            key, _, value = item.partition("=")
            try:
                parsed[key] = float(value)
            except ValueError:
                continue
        if parsed:
            values[kind] = parsed
    return values or None


def candidate_cgroup(proc_self_cgroup: Path) -> str | None:
    """Read this candidate's own cgroup-v2 path from /proc/self/cgroup."""

    raw = _read_text(proc_self_cgroup)
    if raw is None:
        return None
    for line in raw.splitlines():
        # cgroup v2 unified hierarchy is always the "0::" line.
        if line.startswith("0::"):
            path = line[3:].strip()
            return path or None
    return None


def _is_bound_to_ci_slice(cgroup: str) -> bool:
    """Exact COMPONENT match, never a substring.

    `other-mastermind-ci.slice` contains the expected name as a substring and
    must still be refused, and the slice root itself is not a candidate — a
    real candidate always sits in a `.service` unit beneath the slice.
    """

    components = [item for item in cgroup.split("/") if item]
    if EXPECTED_SLICE not in components:
        return False
    index = components.index(EXPECTED_SLICE)
    return any(item.endswith(".service") for item in components[index + 1 :])


def _empty_slice_sample(status: str, cgroup: str | None, reason: str | None) -> dict:
    return {
        "status": status,
        "expected_slice": EXPECTED_SLICE,
        "cgroup": cgroup,
        "reason": reason,
        "cpu": None,
        "cpu_max": None,
        "memory": None,
        "memory_events": None,
        "pids": None,
        "pids_events": None,
        "pressure": None,
    }


def slice_sample(cgroup_root: Path, proc_self_cgroup: Path) -> dict:
    """One aggregate CI-slice observation, or an explicit non-observation.

    Never substitutes host-global metrics for slice metrics.
    """

    cgroup = candidate_cgroup(proc_self_cgroup)
    if cgroup is None:
        return _empty_slice_sample(
            "unavailable", None, "could not read this candidate's cgroup"
        )
    if not _is_bound_to_ci_slice(cgroup):
        return _empty_slice_sample(
            "refused",
            cgroup,
            f"candidate cgroup is not a .service under /{EXPECTED_SLICE}; "
            "refusing to substitute host-global metrics",
        )

    node = Path(cgroup_root) / cgroup.lstrip("/")
    sample = _empty_slice_sample("bound", cgroup, None)
    sample["memory"] = {"current": None, "peak": None, "swap_current": None}
    sample["pids"] = {"current": None}
    for name, (group, key) in _SLICE_INT_FILES.items():
        sample[group][key] = _read_int(node / name)
    for name, key in _SLICE_KEYED_FILES.items():
        sample[key] = _read_keyed(node / name)
    raw_max = _read_text(node / "cpu.max")
    sample["cpu_max"] = raw_max.strip() if raw_max is not None else None
    pressure: dict[str, dict[str, dict[str, float]]] = {}
    for name, key in _SLICE_PRESSURE_FILES.items():
        parsed = _read_pressure(node / name)
        if parsed is not None:
            pressure[key] = parsed
    sample["pressure"] = pressure or None

    # Bound but blind: the hierarchy is right and the evidence is not there.
    # That is a degraded observation, not a passing one.
    if sample["cpu"] is None and sample["memory"]["current"] is None:
        sample["status"] = "degraded"
        sample["reason"] = f"no readable cgroup evidence under {node}"
    return sample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--cgroup-root", type=Path, default=Path("/sys/fs/cgroup"))
    parser.add_argument(
        "--proc-self-cgroup", type=Path, default=Path("/proc/self/cgroup")
    )
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    previous_idle, previous_total = cpu_times()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as handle:
        while running:
            memory = meminfo()
            disk = os.statvfs(args.path)
            idle, total = cpu_times()
            delta_total = total - previous_total
            delta_idle = idle - previous_idle
            cpu_pct = (
                100 * (1 - delta_idle / delta_total) if delta_total > 0 else 0.0
            )
            record = {
                "time": time.time(),
                "cpu_percent": round(cpu_pct, 2),
                "load": list(os.getloadavg()),
                "memory_available_bytes": memory.get("MemAvailable", 0),
                "swap_used_bytes": memory.get("SwapTotal", 0)
                - memory.get("SwapFree", 0),
                "disk_free_bytes": disk.f_bavail * disk.f_frsize,
                "slice": slice_sample(args.cgroup_root, args.proc_self_cgroup),
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            previous_idle, previous_total = idle, total
            time.sleep(max(args.interval, 1.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
