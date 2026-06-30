"""Host/system metrics for the VPS the console runs on — CPU load, memory, swap,
disk, uptime. Pure stdlib reads of /proc + os; no privileged calls. Degrades to
{available: False} off-Linux (e.g. local mac dev)."""
from __future__ import annotations

import os
import shutil
import time


def _meminfo() -> dict | None:
    out: dict[str, int] = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                parts = v.strip().split()
                if parts:
                    out[k.strip()] = int(parts[0]) * 1024  # kB → bytes
    except Exception:  # noqa: BLE001
        return None
    return out


def _uptime_s() -> float | None:
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except Exception:  # noqa: BLE001
        return None


def snapshot() -> dict:
    is_linux = os.path.exists("/proc/meminfo")
    try:
        load1, load5, load15 = os.getloadavg()
    except (OSError, AttributeError):
        load1 = load5 = load15 = None
    cpus = os.cpu_count() or 1

    mem = _meminfo() or {}
    mem_block = None
    total, avail = mem.get("MemTotal"), mem.get("MemAvailable")
    if total and avail is not None:
        mem_block = {"total": total, "available": avail, "used": total - avail,
                     "used_pct": round((total - avail) / total * 100, 1)}

    swap_total, swap_free = mem.get("SwapTotal"), mem.get("SwapFree")
    swap_block = None
    if swap_total and swap_free is not None and swap_total > 0:
        swap_block = {"total": swap_total, "used": swap_total - swap_free,
                      "used_pct": round((swap_total - swap_free) / swap_total * 100, 1)}

    du = shutil.disk_usage("/")
    return {
        "available": is_linux,
        "now": int(time.time()),
        "cpu": {
            "count": cpus,
            "load1": load1, "load5": load5, "load15": load15,
            "load1_pct": round(load1 / cpus * 100, 1) if load1 is not None else None,
        },
        "memory": mem_block,
        "swap": swap_block,
        "disk": {"total": du.total, "used": du.used, "free": du.free,
                 "used_pct": round(du.used / du.total * 100, 1)},
        "uptime_s": _uptime_s(),
    }
