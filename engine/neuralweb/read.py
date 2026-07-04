"""engine.neuralweb.read — consumer helper for the Neural Web world_state bus.

PUBLIC API
----------
load_world_state(root=None, *, require_fresh_regime=True) -> dict | None
    Read data/neuralweb/world_state.json and return it, or None if:
      - the file is missing or corrupt, OR
      - require_fresh_regime=True (the default) AND the committed world_state's
        regime.asof is older than the current data/regime/latest.json asof —
        the staleness guard that prevents a consumer from reading a world_state
        that pre-dates a regime recompute that happened after the last
        world_state build.

get(ws, dotted_path, default=None)
    Cheap dotted-path extractor: get(ws, 'regime.quad') avoids KeyError chains.

DESIGN (W1 PR2, adjudicated)
-----------------------------
Correctness beats elegance.  During the migration era, a consumer must NEVER
silently read a world_state that pre-dates the raw stores it replaced.  The
staleness guard enforces this at the consumer boundary: if regime/latest.json
has been updated (its asof is newer than world_state.regime.asof) the helper
returns None and the caller falls back to its legacy read path.  This is not
an error — it is the design.

Cheap path: at most two JSON reads (world_state + latest.json freshness check).
No arithmetic, no signal computation.

FALLBACK CONTRACT
-----------------
Every caller must retain its legacy read path and call it when this helper
returns None.  The pattern:

    ws = load_world_state()
    if ws is not None:
        quad = get(ws, "regime.quad")
    else:
        # legacy read
        ...
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Canonical location relative to any repo root
_WS_REL = Path("data") / "neuralweb" / "world_state.json"
_REG_REL = Path("data") / "regime" / "latest.json"


def _repo_root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    # engine/neuralweb/read.py → ../../.. = repo root
    return Path(__file__).resolve().parent.parent.parent


def _read_json(p: Path) -> dict | None:
    """Read and parse JSON; return None on any failure."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.debug("neuralweb.read: unreadable json %s — %s", p, exc)
        return None


def load_world_state(
    root: Path | str | None = None,
    *,
    require_fresh_regime: bool = True,
) -> dict | None:
    """Read and return data/neuralweb/world_state.json, or None.

    Parameters
    ----------
    root:
        Repo root path override.  Defaults to three levels above this file.
    require_fresh_regime:
        If True (the default), compare world_state.regime.asof against
        data/regime/latest.json.asof.  If the latest.json asof is NEWER
        (i.e. a regime recompute has happened since the last world_state
        build), return None so the caller falls back to the raw store.
        This is the staleness guard for the migration era.

    Returns
    -------
    dict | None
        The parsed world_state payload, or None on any failure or staleness.
    """
    repo = _repo_root(root)
    ws = _read_json(repo / _WS_REL)
    if ws is None:
        log.debug("neuralweb.read: world_state absent or corrupt — using legacy path")
        return None

    if require_fresh_regime:
        reg_path = repo / _REG_REL
        if reg_path.exists():
            reg = _read_json(reg_path)
            if reg is not None:
                reg_asof = reg.get("asof") or ""
                ws_regime_asof = (ws.get("regime") or {}).get("asof") or ""
                if reg_asof and ws_regime_asof and reg_asof != ws_regime_asof:
                    log.debug(
                        "neuralweb.read: staleness guard fired — "
                        "latest.json.asof=%s > world_state.regime.asof=%s; "
                        "using legacy path",
                        reg_asof,
                        ws_regime_asof,
                    )
                    return None

    return ws


def get(ws: dict | None, dotted_path: str, default: Any = None) -> Any:
    """Extract a value from *ws* using a dotted key path.

    Example::

        quad = get(ws, "regime.quad")
        vix  = get(ws, "vol.vix")

    Returns *default* (None by default) if *ws* is None, the path does not
    exist, or any intermediate node is not a dict.
    """
    if ws is None:
        return default
    cur: Any = ws
    for part in dotted_path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
        if cur is None:
            return default
    return cur
