"""Read/write the Brain guest-access knob from the admin console.

The knob (anonymous free Fast lane on/off + per-day cap) lives in an UNTRACKED JSON file so
the operator can toggle it without a deploy — the gateway re-reads it within a short TTL
(engine/neuralweb/brain_gateway.py:_guest_cfg). This module resolves the SAME path the
gateway does and writes it atomically (tmp + os.replace) so a concurrent reader never sees a
half-written file.

Resolution order (identical to the gateway): BRAIN_GUEST_CFG env override → <repo>/admin/
brain_guest_access.json. Absent/malformed on read → the fail-closed default (access OFF).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import paths

DEFAULT = {"enabled": False, "daily_limit": 30}
LIMIT_LO = 1
LIMIT_HI = 500


def config_path() -> Path:
    """The active config path (env override → <repo>/admin/brain_guest_access.json)."""
    override = os.environ.get("BRAIN_GUEST_CFG", "").strip()
    if override:
        return Path(override)
    return paths.ROOT / "admin" / "brain_guest_access.json"


def read() -> dict:
    """Current knob state + resolved path + existence. Never raises.

    Returns {"enabled": bool, "daily_limit": int, "path": str, "exists": bool}.
    Missing/malformed file → the fail-closed default (enabled False), exists reflects reality.
    """
    p = config_path()
    enabled = DEFAULT["enabled"]
    daily_limit = DEFAULT["daily_limit"]
    exists = p.exists()
    if exists:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                enabled = bool(raw.get("enabled", False))
                daily_limit = _clamp(raw.get("daily_limit", DEFAULT["daily_limit"]))
        except Exception:  # noqa: BLE001 — a bad file reads as the default, never crashes the panel
            pass
    return {"enabled": enabled, "daily_limit": daily_limit, "path": str(p), "exists": exists}


def write(enabled: bool, daily_limit: int) -> dict:
    """Validate + atomically persist the knob. Returns {"ok": True, ...read()} or {"ok": False, "error"}."""
    if not isinstance(enabled, bool):
        return {"ok": False, "error": "enabled must be a boolean"}
    if isinstance(daily_limit, bool) or not isinstance(daily_limit, int):
        return {"ok": False, "error": "daily_limit must be an integer"}
    if not (LIMIT_LO <= daily_limit <= LIMIT_HI):
        return {"ok": False, "error": f"daily_limit must be between {LIMIT_LO} and {LIMIT_HI}"}

    p = config_path()
    payload = {"enabled": enabled, "daily_limit": daily_limit}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)   # atomic on the same filesystem — readers never see a partial file
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"write failed: {exc}"}
    out = {"ok": True}
    out.update(read())
    return out


def _clamp(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return DEFAULT["daily_limit"]
    return max(LIMIT_LO, min(LIMIT_HI, n))
