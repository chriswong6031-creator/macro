#!/usr/bin/env python3
"""Refuse a PC CI job before disk pressure or swap/OOM conditions become unsafe."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


GIB = 1024**3
MIB = 1024**2

EXPECTED_SLICE = "mastermind-ci.slice"

# Guard thresholds are versioned SEPARATELY from the slice ceilings in
# mastermind-ci.slice.template. Retuning when a listener refuses to start is an
# operational decision; changing CPUQuota/MemoryMax is a measured resource
# decision. Sharing one version for both would make a threshold tweak read as a
# change to the envelope itself.
THRESHOLDS_VERSION = "mastermind.ci_resource_guard_thresholds.v1"

PREFLIGHT_PROFILES = {
    # Steady state for pc-ci-1..3 today: unchanged from the accepted P2 guard.
    "steady": {
        "memory_available_min_bytes": 4 * GIB,
        "swap_used_max_bytes": None,
        "psi_full_avg10_max": None,
    },
    # Stricter gate before a four-slot diagnostic, from the frozen plan
    # preconditions. Deliberately harder than steady state: the point is to
    # refuse starting a four-wide run on a guest that is already strained,
    # where the result would measure the strain rather than the capacity.
    "four-slot-canary": {
        "memory_available_min_bytes": 20 * GIB,
        "swap_used_max_bytes": 512 * MIB,
        "psi_full_avg10_max": 0.10,
    },
}


def _read(path: Path) -> str | None:
    """None means the kernel does not expose the field; never treated as zero."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_keyed(path: Path) -> dict[str, int] | None:
    raw = _read(path)
    if raw is None:
        return None
    values: dict[str, int] = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) == 2:
            try:
                values[fields[0]] = int(fields[1])
            except ValueError:
                continue
    return values or None


def _read_full_avg10(path: Path) -> float | None:
    raw = _read(path)
    if raw is None:
        return None
    for line in raw.splitlines():
        fields = line.split()
        if fields and fields[0] == "full":
            for item in fields[1:]:
                key, _, value = item.partition("=")
                if key == "avg10":
                    try:
                        return float(value)
                    except ValueError:
                        return None
    return None


def candidate_cgroup(proc_self_cgroup: Path = Path("/proc/self/cgroup")) -> str | None:
    raw = _read(proc_self_cgroup)
    if raw is None:
        return None
    for line in raw.splitlines():
        if line.startswith("0::"):
            return line[3:].strip() or None
    return None


def is_bound_to_ci_slice(cgroup: str | None) -> bool:
    """Exact ANCHORED match: the candidate sits directly under the slice root.

    Component-anywhere matching accepted a nested look-alike such as
    /user.slice/user-1000.slice/mastermind-ci.slice/evil.service, and an
    unnormalised `..` let a forged cgroup assemble fully "bound" evidence from a
    directory outside the slice entirely. A systemd top-level slice always
    produces /mastermind-ci.slice/<unit>.service, so anchoring costs nothing.
    """
    if not cgroup:
        return False
    components = [item for item in cgroup.split("/") if item]
    if any(item in {"..", "."} for item in components):
        return False
    if len(components) < 2 or components[0] != EXPECTED_SLICE:
        return False
    return any(item.endswith(".service") for item in components[1:])


def slice_reasons(
    cgroup_root: Path,
    cgroup: str | None,
    profile: str,
    memory_available_bytes: int,
    swap_used_bytes: int,
    *,
    require_slice: bool,
) -> tuple[list[str], dict]:
    """Aggregate-slice half of the prestart refusal decision.

    The memory floor is read GUEST-WIDE on purpose. The renderer lives outside
    this slice, so a slice-local memory read would show a nearly idle cgroup
    while the guest itself is starved -- and would happily admit a CI job that
    then starves the renderer. Slice evidence is used for what only it can
    answer: whether CI's own envelope is already throttling, swapping or
    OOM-killing.
    """

    thresholds = PREFLIGHT_PROFILES.get(profile) or PREFLIGHT_PROFILES["steady"]
    bound = is_bound_to_ci_slice(cgroup)
    evidence: dict[str, object] = {
        "thresholds_version": THRESHOLDS_VERSION,
        "profile": profile,
        "expected_slice": EXPECTED_SLICE,
        "cgroup": cgroup,
        "bound": bound,
        "memory_floor_is_guest_wide": True,
        "memory_events": None,
        "pressure_full_avg10": None,
        "cpu_max": None,
    }
    reasons: list[str] = []

    if require_slice and not bound:
        reasons.append(
            f"candidate cgroup {cgroup!r} is not a .service under /{EXPECTED_SLICE}"
        )

    floor = thresholds["memory_available_min_bytes"]
    if floor is not None and memory_available_bytes < floor:
        reasons.append(
            f"guest memory available below {floor // GIB} GiB "
            f"({memory_available_bytes // MIB} MiB)"
        )
    swap_ceiling = thresholds["swap_used_max_bytes"]
    if swap_ceiling is not None and swap_used_bytes > swap_ceiling:
        reasons.append(
            f"swap in use above {swap_ceiling // MIB} MiB "
            f"({swap_used_bytes // MIB} MiB)"
        )

    if bound:
        node = Path(cgroup_root) / str(cgroup).lstrip("/")

        # BINDING IS NOT ENFORCEMENT. systemd auto-creates an UNDEFINED slice, so
        # a unit carrying `Slice=mastermind-ci.slice` binds cleanly even when no
        # slice file was ever installed -- it simply inherits no limits. A
        # capacity diagnostic run against an unenforced envelope measures nothing
        # while looking bound and green, which is the exact shape of false proof
        # this guard exists to refuse. Only the stricter profile gates on it:
        # pc-ci-1..3 run today with no slice installed at all, and refusing them
        # here would strand every live slot.
        raw_cpu_max = _read(node / "cpu.max")
        cpu_max = raw_cpu_max.strip() if raw_cpu_max is not None else None
        evidence["cpu_max"] = cpu_max
        if thresholds["psi_full_avg10_max"] is not None:
            if cpu_max is None or cpu_max.split()[:1] == ["max"]:
                reasons.append(
                    f"slice cpu.max is {cpu_max!r}: the envelope is unenforced, so a "
                    "capacity diagnostic here would measure nothing"
                )

        # memory.events is EVIDENCE, never a gate. Every field is cumulative over
        # the slice's lifetime, and cgroup-v2 defines `high` as MemoryHigh
        # reclaim, `max` as "usage was ABOUT TO go over max" (reclaim attempted),
        # and `oom` as "allocation was ABOUT TO fail" -- none of them is a kill.
        # `oom_kill` is a real kill, but it is cumulative too, so this guard
        # cannot distinguish one three weeks ago from one a second ago.
        #
        # Gating a start on ANY of them therefore strands the slot permanently
        # after a single transient event: with Restart=always, RestartSec=5 and
        # StartLimitIntervalSec=0 the unit enters an unbounded ~305s refuse loop
        # that never reaches `failed`, so nothing alerts. That is the same
        # failure the `high` reasoning already rejected, and it applies verbatim
        # to the other three.
        #
        # The plan's "zero high/max/oom/oom_kill DELTA" is a per-run acceptance
        # criterion over one window, owned by
        # capture_ci_canary_receipt.slice_metrics, which has both endpoints and
        # can subtract. A prestart gate has only a lifetime total and must not
        # pretend otherwise.
        evidence["memory_events"] = _read_keyed(node / "memory.events")
        ceiling = thresholds["psi_full_avg10_max"]
        pressure: dict[str, float] = {}
        for name, key in (("memory.pressure", "memory"), ("io.pressure", "io")):
            value = _read_full_avg10(node / name)
            if value is not None:
                pressure[key] = value
        evidence["pressure_full_avg10"] = pressure or None
        if ceiling is not None:
            for key, value in sorted(pressure.items()):
                if value >= ceiling:
                    reasons.append(
                        f"slice {key} pressure full avg10 {value} at or above {ceiling}"
                    )

    return reasons, evidence


def refusal_backoff(reasons: list[str], seconds: int, *, sleep=time.sleep) -> None:
    """Bound unsafe-host retries without delaying an allowed listener start."""
    if reasons and seconds:
        sleep(seconds)


def meminfo(path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, raw = line.split(":", 1)
        values[name] = int(raw.strip().split()[0]) * 1024
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument(
        "--refusal-backoff-seconds",
        type=int,
        default=0,
        choices=range(0, 3601),
        metavar="0..3600",
        help="wait before returning refusal status 78 (default: no wait)",
    )
    parser.add_argument(
        "--require-slice",
        action="store_true",
        help=(
            "refuse unless this candidate is bound to a .service under "
            f"/{EXPECTED_SLICE}; set by any unit that declares Slice="
        ),
    )
    parser.add_argument(
        "--preflight-profile",
        choices=sorted(PREFLIGHT_PROFILES),
        default="steady",
        help="threshold profile; four-slot-canary is the stricter pre-diagnostic gate",
    )
    parser.add_argument("--cgroup-root", type=Path, default=Path("/sys/fs/cgroup"))
    parser.add_argument(
        "--proc-self-cgroup", type=Path, default=Path("/proc/self/cgroup")
    )
    args = parser.parse_args()
    disk = os.statvfs(args.path)
    total = disk.f_blocks * disk.f_frsize
    free = disk.f_bavail * disk.f_frsize
    used_pct = (1 - free / total) * 100 if total else 100.0
    memory = meminfo()
    available = memory.get("MemAvailable", 0)
    swap_total = memory.get("SwapTotal", 0)
    swap_free = memory.get("SwapFree", 0)
    swap_used_pct = (
        (1 - swap_free / swap_total) * 100 if swap_total else 0.0
    )
    swap_used = swap_total - swap_free
    reasons: list[str] = []
    if used_pct >= 85 or free < 100 * GIB:
        reasons.append("critical disk pressure")
    if swap_used_pct >= 50 and available < 8 * GIB:
        reasons.append("swap thrash risk")
    # The memory floor, swap ceiling and every slice-aware gate live in
    # slice_reasons so the threshold profile is the single place they are set.
    slice_refusals, slice_evidence = slice_reasons(
        cgroup_root=args.cgroup_root,
        cgroup=candidate_cgroup(args.proc_self_cgroup),
        profile=args.preflight_profile,
        memory_available_bytes=available,
        swap_used_bytes=swap_used,
        require_slice=args.require_slice,
    )
    reasons.extend(slice_refusals)
    result = {
        "schema": "mastermind.ci_resource_guard.v1",
        "path": str(args.path.resolve()),
        "cpu_count": os.cpu_count(),
        "load_average": list(os.getloadavg()),
        "disk_free_bytes": free,
        "disk_used_percent": round(used_pct, 2),
        "memory_available_bytes": available,
        "swap_used_percent": round(swap_used_pct, 2),
        "swap_used_bytes": swap_used,
        "ci_slice": slice_evidence,
        "allowed": not reasons,
        "reasons": reasons,
    }
    print("CI_RESOURCE_GUARD=" + json.dumps(result, sort_keys=True), flush=True)
    refusal_backoff(reasons, args.refusal_backoff_seconds)
    return 0 if not reasons else 78


if __name__ == "__main__":
    raise SystemExit(main())
