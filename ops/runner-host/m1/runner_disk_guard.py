#!/usr/bin/env python3
"""Fail-closed disk admission for the M1 Actions runner fleet.

The listener is allowed to stay online for a bounded diagnostic canary below the
full-work floor. Heavy work remains refused until both the percentage and free-byte
thresholds are healthy; routing labels provide the second half of that boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


GIB = 1024**3


def tree_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    result = subprocess.run(
        ["du", "-sk", str(path)], text=True, capture_output=True, check=False
    )
    if result.returncode == 0:
        return int(result.stdout.split()[0]) * 1024
    # Fall back to an allocation-independent count if du is unavailable.
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(root) / name).is_symlink()]
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except FileNotFoundError:
                continue
    return total


def snapshot(path: Path) -> dict[str, object]:
    stat = os.statvfs(path)
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bavail * stat.f_frsize
    used_pct = round((1 - free / total) * 100, 2) if total else 100.0
    inode_total = stat.f_files
    inode_free = stat.f_favail
    inode_used_pct = (
        round((1 - inode_free / inode_total) * 100, 2) if inode_total else None
    )
    runner_root = path.resolve()
    emergency = used_pct >= 90 or free < 100 * GIB
    full_refused = emergency or used_pct >= 85 or free < 200 * GIB
    if emergency:
        pressure = "emergency"
    elif used_pct >= 80:
        pressure = "critical"
    elif used_pct >= 70:
        pressure = "warning"
    else:
        pressure = "healthy"
    return {
        "schema": "runner.disk_guard.v1",
        "path": str(runner_root),
        "total_bytes": total,
        "free_bytes": free,
        "used_percent": used_pct,
        "inode_free": inode_free,
        "inode_used_percent": inode_used_pct,
        "work_bytes": tree_bytes(runner_root / "_work"),
        "temp_bytes": tree_bytes(runner_root / "_work" / "_temp"),
        "diag_bytes": tree_bytes(runner_root / "_diag"),
        "pressure": pressure,
        "full_work_allowed": not full_refused,
        "lightweight_allowed": not emergency,
        "thresholds": {
            "warning_used_percent": 70,
            "critical_used_percent": 80,
            "full_refuse_used_percent": 85,
            "full_refuse_free_bytes": 200 * GIB,
            "emergency_used_percent": 90,
            "emergency_free_bytes": 100 * GIB,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=("status", "lightweight", "full"), default="status"
    )
    args = parser.parse_args()
    result = snapshot(args.path)
    print("RUNNER_DISK_GUARD=" + json.dumps(result, sort_keys=True), flush=True)
    if args.mode == "full" and not result["full_work_allowed"]:
        return 78
    if args.mode == "lightweight" and not result["lightweight_allowed"]:
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
