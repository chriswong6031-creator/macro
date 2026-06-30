"""systemd service health for the live VPS stack — Caddy, the FastAPI tiers, the
Terminal, the Brain, and this console. Shells out to `systemctl show` for a
structured (key=value) read, never parsing human output. Degrades to
{available: False} when systemctl is missing (local dev)."""
from __future__ import annotations

import shutil
import subprocess

# (unit, human label) — the services that make up the live site.
SERVICES = [
    ("caddy.service", "Caddy — web server / TLS"),
    ("macro-api.service", "macro API — FastAPI :8000"),
    ("admin.service", "Admin console — this panel"),
    ("terminal.service", "Mastermind Terminal — Next.js :3000"),
    ("mastermind.service", "Brain dashboard — :8001"),
]

_PROPS = ("LoadState", "ActiveState", "SubState", "UnitFileState",
          "ExecMainStartTimestamp", "MemoryCurrent", "NRestarts", "Result")


def _show(unit: str) -> dict:
    try:
        out = subprocess.run(
            ["systemctl", "show", unit, "--no-pager",
             "--property=" + ",".join(_PROPS)],
            capture_output=True, text=True, timeout=8)
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}
    d: dict[str, str] = {}
    for line in out.stdout.splitlines():
        k, _, v = line.partition("=")
        d[k] = v
    return d


def status() -> dict:
    if not shutil.which("systemctl"):
        return {"available": False, "services": [],
                "reason": "systemctl not found (not running on the VPS)"}
    rows = []
    for unit, label in SERVICES:
        d = _show(unit)
        active = d.get("ActiveState")
        mem = d.get("MemoryCurrent")
        mem = int(mem) if (mem and mem.isdigit()) else None
        try:
            restarts = int(d.get("NRestarts") or 0)
        except ValueError:
            restarts = 0
        rows.append({
            "unit": unit, "label": label,
            "loaded": d.get("LoadState") == "loaded",
            "active": active, "sub": d.get("SubState"),
            "enabled": d.get("UnitFileState"),
            "ok": active == "active",
            "since": d.get("ExecMainStartTimestamp") or None,
            "memory": mem, "restarts": restarts, "result": d.get("Result"),
        })
    present = [r for r in rows if r["loaded"]]
    return {
        "available": True,
        "services": rows,
        "ok_count": sum(1 for r in rows if r["ok"]),
        "total": len(rows),
        "healthy": bool(present) and all(r["ok"] for r in present),
    }
