#!/usr/bin/env python3
"""Write bounded, non-secret host resource samples for a CI canary."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=5.0)
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
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            previous_idle, previous_total = idle, total
            time.sleep(max(args.interval, 1.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
