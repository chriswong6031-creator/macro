#!/usr/bin/env python3
"""Refuse a PC CI job before disk pressure or swap/OOM conditions become unsafe."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


GIB = 1024**3


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
    reasons: list[str] = []
    if used_pct >= 85 or free < 100 * GIB:
        reasons.append("critical disk pressure")
    if available < 4 * GIB:
        reasons.append("less than 4 GiB memory available")
    if swap_used_pct >= 50 and available < 8 * GIB:
        reasons.append("swap thrash risk")
    result = {
        "schema": "mastermind.ci_resource_guard.v1",
        "path": str(args.path.resolve()),
        "cpu_count": os.cpu_count(),
        "load_average": list(os.getloadavg()),
        "disk_free_bytes": free,
        "disk_used_percent": round(used_pct, 2),
        "memory_available_bytes": available,
        "swap_used_percent": round(swap_used_pct, 2),
        "allowed": not reasons,
        "reasons": reasons,
    }
    print("CI_RESOURCE_GUARD=" + json.dumps(result, sort_keys=True), flush=True)
    refusal_backoff(reasons, args.refusal_backoff_seconds)
    return 0 if not reasons else 78


if __name__ == "__main__":
    raise SystemExit(main())
