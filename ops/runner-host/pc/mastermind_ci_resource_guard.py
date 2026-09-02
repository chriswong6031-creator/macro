#!/usr/bin/env python3
"""Refuse a PC CI job before disk pressure or swap/OOM conditions become unsafe."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path


GIB = 1024**3
MIB = 1024**2

EXPECTED_SLICE = "mastermind-ci.slice"
EXPECTED_AGGREGATE_CGROUP = "/mastermind.slice/mastermind-ci.slice"
EXPECTED_LIMITS = {
    "cpu.max": "800000 100000",
    "memory.high": "10737418240",
    "memory.max": "12884901888",
    "memory.swap.max": "2147483648",
}

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


def admission_policy_digest() -> str:
    """Stable identity for the ADMISSION THRESHOLDS, and nothing else.

    Deliberately computed over PREFLIGHT_PROFILES alone. The resource envelope
    (CPUQuota / MemoryHigh / MemoryMax / MemorySwapMax) lives in
    mastermind-ci.slice.template and is NOT an input here: retuning when a
    listener refuses to start and changing the measured envelope are different
    decisions, and a shared identity would make one look like the other.
    """

    canonical = json.dumps(PREFLIGHT_PROFILES, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


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


def is_bound_to_ci_slice(cgroup: str | None) -> bool:
    """Accept exactly one direct service under the real systemd slice chain."""
    if not cgroup or not cgroup.startswith("/") or cgroup.endswith("/") or "//" in cgroup:
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
    """Refuse proof paths that redirect outside the declared cgroup hierarchy."""
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
        "candidate_cgroup": cgroup,
        "aggregate_cgroup": EXPECTED_AGGREGATE_CGROUP,
        "candidate_identity": None,
        "aggregate_identity": None,
        "aggregate_metric_source": "parent_slice",
        "bound": bound,
        "memory_floor_is_guest_wide": True,
        "memory_events": None,
        "pressure_full_avg10": None,
        "cpu_max": None,
        "effective_limits": None,
        "slice_cgroup": None,
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
        # Envelope and aggregate counters live on the SLICE node; a candidate's
        # leaf `.service` cgroup has neither.
        slice_cgroup = EXPECTED_AGGREGATE_CGROUP
        evidence["slice_cgroup"] = slice_cgroup
        nodes = _canonical_cgroup_nodes(cgroup_root, str(cgroup))
        if nodes is None:
            evidence["bound"] = False
            reasons.append(
                "candidate or aggregate cgroup node is symlinked, noncanonical, missing, or outside the fixed parent slice"
            )
            return reasons, evidence
        candidate_node, node = nodes
        evidence["candidate_identity"] = _identity(candidate_node)
        evidence["aggregate_identity"] = _identity(node)
        if evidence["candidate_identity"] is None or evidence["aggregate_identity"] is None:
            reasons.append("missing stable candidate or aggregate cgroup identity")

        # BINDING IS NOT ENFORCEMENT. systemd auto-creates an UNDEFINED slice, so
        # a unit carrying `Slice=mastermind-ci.slice` binds cleanly even when no
        # slice file was ever installed -- it simply inherits no limits. A
        # capacity diagnostic run against an unenforced envelope measures nothing
        # while looking bound and green, which is the exact shape of false proof
        # this guard exists to refuse. Every --require-slice invocation gates on
        # the complete parent tuple. pc-ci-1..3 do not currently opt into that
        # flag, so this proof boundary does not strand today's live slots.
        limits = {
            name: (_read(node / name) or "").strip() or None
            for name in EXPECTED_LIMITS
        }
        evidence["effective_limits"] = limits
        cpu_max = limits["cpu.max"]
        evidence["cpu_max"] = cpu_max
        if require_slice:
            for name, expected in EXPECTED_LIMITS.items():
                if limits[name] != expected:
                    reasons.append(
                        f"aggregate slice {name} is {limits[name]!r}; expected {expected!r}"
                    )
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
            if value is None and ceiling is not None:
                reasons.append(f"aggregate slice {name} is missing or unparseable")
            elif value is not None and (not math.isfinite(value) or value < 0):
                reasons.append(f"aggregate slice {name} full avg10 is invalid")
            elif value is not None:
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
        "admission_policy_version": THRESHOLDS_VERSION,
        "admission_policy_digest": admission_policy_digest(),
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
