#!/usr/bin/env python3
"""Write bounded, non-secret host resource samples for a CI canary.

Also emits AGGREGATE cgroup-v2 evidence for the one CI-only slice. Once four CI
candidates share a single enforced envelope, host-global numbers stop being
evidence: they cannot distinguish "CI stayed inside its budget" from "the guest
happened to be quiet", and they say nothing at all about whether the renderer
stayed outside the slice.

Each candidate therefore derives its OWN cgroup from /proc/self/cgroup and must
bind as one direct service under the immutable
``/mastermind.slice/mastermind-ci.slice/<unit>.service`` hierarchy. Aggregate
counters and limits are read only from the parent slice node. A
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
EXPECTED_AGGREGATE_CGROUP = "/mastermind.slice/mastermind-ci.slice"

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
_REQUIRED_KEYED_FIELDS = {
    "cpu": {"usage_usec", "nr_periods", "nr_throttled", "throttled_usec"},
    "memory_events": {"high", "max", "oom", "oom_kill"},
    "pids_events": {"max"},
}
_REQUIRED_PRESSURE_KINDS = {
    "cpu": {"some", "full"},
    "memory": {"some", "full"},
    "io": {"some", "full"},
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


def expected_slice_chain(slice_name: str = EXPECTED_SLICE) -> list[str]:
    """The cgroup component chain systemd creates for a slice unit name.

    systemd treats `-` in a slice name as a PATH SEPARATOR, so
    `mastermind-ci.slice` is a child of an implicit `mastermind.slice` and lives
    at /mastermind.slice/mastermind-ci.slice/. Discovered on the real host
    2026-09-02 when a correctly configured pc-ci-1 was refused exit 78 and could
    not start: the previous matcher required the slice at component 0.
    """

    stem = slice_name[: -len(".slice")] if slice_name.endswith(".slice") else slice_name
    parts = stem.split("-")
    return ["-".join(parts[: i + 1]) + ".slice" for i in range(len(parts))]


def _is_bound_to_ci_slice(cgroup: str) -> bool:
    """Accept exactly one direct service below the real systemd slice chain."""

    if not cgroup.startswith("/") or cgroup.endswith("/") or "//" in cgroup:
        return False
    components = [item for item in cgroup.split("/") if item]
    if any(item in {"..", "."} for item in components):
        return False
    chain = expected_slice_chain(EXPECTED_SLICE)
    # Anchored on the FULL systemd-derived parent chain: this accepts the real
    # /mastermind.slice/mastermind-ci.slice/<unit>.service while still refusing
    # /user.slice/user-1000.slice/mastermind-ci.slice/... and every other nested
    # look-alike, which is what anchoring was introduced to stop.
    if components[: len(chain)] != chain or len(components) != len(chain) + 1:
        return False
    service = components[-1]
    return len(service) > len(".service") and service.endswith(".service")


def _identity(path: Path) -> dict[str, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {"device": stat.st_dev, "inode": stat.st_ino}


def _canonical_cgroup_nodes(cgroup_root: Path, cgroup: str) -> tuple[Path, Path] | None:
    root = Path(cgroup_root)
    candidate = root / cgroup.lstrip("/")
    aggregate = root / EXPECTED_AGGREGATE_CGROUP.lstrip("/")
    if root.is_symlink() or candidate.is_symlink() or aggregate.is_symlink():
        return None
    try:
        canonical_root = root.resolve(strict=True)
        if candidate.resolve(strict=True) != canonical_root / cgroup.lstrip("/"):
            return None
        if aggregate.resolve(strict=True) != canonical_root / EXPECTED_AGGREGATE_CGROUP.lstrip("/"):
            return None
    except OSError:
        return None
    return candidate, aggregate


def _empty_slice_sample(status: str, cgroup: str | None, reason: str | None) -> dict:
    return {
        "status": status,
        "expected_slice": EXPECTED_SLICE,
        "cgroup": cgroup,
        "candidate_cgroup": cgroup,
        "aggregate_cgroup": EXPECTED_AGGREGATE_CGROUP,
        "candidate_identity": None,
        "aggregate_identity": None,
        "aggregate_metric_source": "parent_slice",
        "reason": reason,
        "cpu": None,
        "cpu_max": None,
        "memory": None,
        "memory_events": None,
        "pids": None,
        "pids_events": None,
        "pressure": None,
        "limits": None,
        "slice_cgroup": None,
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

    # Membership is the CANDIDATE's; the aggregate evidence is the SLICE's.
    # cgroup-v2 puts CPUQuota/MemoryMax and the summed counters on the slice
    # node, while a candidate's leaf `.service` carries only its own usage and
    # no ceilings at all (measured on the host 2026-09-02: the slice node had
    # cpu.max "800000 100000", the leaf had none). Reading the leaf and calling
    # it aggregate would report one candidate's numbers as the whole envelope.
    slice_cgroup = EXPECTED_AGGREGATE_CGROUP
    nodes = _canonical_cgroup_nodes(cgroup_root, cgroup)
    if nodes is None:
        return _empty_slice_sample(
            "refused",
            cgroup,
            "candidate or aggregate cgroup node is symlinked, noncanonical, missing, or outside the fixed parent slice",
        )
    candidate_node, node = nodes
    sample = _empty_slice_sample("bound", cgroup, None)
    sample["slice_cgroup"] = slice_cgroup
    sample["candidate_identity"] = _identity(candidate_node)
    sample["aggregate_identity"] = _identity(node)
    if sample["candidate_identity"] is None or sample["aggregate_identity"] is None:
        return _empty_slice_sample(
            "degraded", cgroup, "missing stable candidate or aggregate cgroup identity"
        )
    sample["memory"] = {"current": None, "peak": None, "swap_current": None}
    sample["pids"] = {"current": None}
    for name, (group, key) in _SLICE_INT_FILES.items():
        sample[group][key] = _read_int(node / name)
    for name, key in _SLICE_KEYED_FILES.items():
        sample[key] = _read_keyed(node / name)
    raw_max = _read_text(node / "cpu.max")
    sample["cpu_max"] = raw_max.strip() if raw_max is not None else None
    sample["limits"] = {
        "cpu.max": sample["cpu_max"],
        "memory.high": (_read_text(node / "memory.high") or "").strip() or None,
        "memory.max": (_read_text(node / "memory.max") or "").strip() or None,
        "memory.swap.max": (_read_text(node / "memory.swap.max") or "").strip() or None,
    }
    pressure: dict[str, dict[str, dict[str, float]]] = {}
    for name, key in _SLICE_PRESSURE_FILES.items():
        parsed = _read_pressure(node / name)
        if parsed is not None:
            pressure[key] = parsed
    sample["pressure"] = pressure or None

    # Bound but blind. Every acceptance threshold in the plan is computed from
    # cpu.stat, memory.current and memory.events, so if ANY of the three is
    # unreadable the window cannot answer the questions it exists to answer.
    # This was an `and` first: a slice with only memory.current readable
    # reported `bound` with every acceptance counter None, which an acceptance
    # check for "zero memory.events delta" reads as satisfied.
    missing = [
        name
        for name, value in (
            ("cpu.stat", sample["cpu"]),
            ("memory.current", sample["memory"]["current"]),
            ("memory.events", sample["memory_events"]),
        )
        if value is None
    ]
    for field, required in _REQUIRED_KEYED_FIELDS.items():
        value = sample[field]
        if not isinstance(value, dict) or not required.issubset(value):
            missing.append(f"{field} required keys")
    for resource, required_kinds in _REQUIRED_PRESSURE_KINDS.items():
        resource_pressure = (sample["pressure"] or {}).get(resource)
        if not isinstance(resource_pressure, dict):
            missing.append(f"{resource}.pressure required keys")
            continue
        for kind in required_kinds:
            values = resource_pressure.get(kind)
            if not isinstance(values, dict) or "total" not in values:
                missing.append(f"{resource}.pressure {kind}.total")
    if missing:
        sample["status"] = "degraded"
        sample["reason"] = (
            f"unreadable or missing required aggregate evidence under "
            f"{slice_cgroup}: {missing}"
        )
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
