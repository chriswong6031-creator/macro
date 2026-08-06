"""Admin console adapter for the Macro Thesis Ledger.

TIER: ops/journal.  **ZERO AUTHORITY** — this surface never scores, ranks, gates
or sizes anything.  It reads ``data/macro_thesis/ledger.jsonl`` and renders a
track record OF operator macro synthesis.  Engine contract + the forward/retro
firewall live in :mod:`engine.macro_thesis`.

Sibling of :mod:`admin.trade_memory`, deliberately NOT a change to it: Trade
Memory is per-trade, per-ticker and private-Supabase-backed; this is thesis-grain
across several macro planes and several instruments, stored in a committed
append-only JSONL file.  Different grain, different store, no shared state.

The engine is imported LAZILY inside each function.  ``admin/server.py`` imports
every admin module at startup and the admin core is a stdlib ``http.server`` that
otherwise needs nothing beyond the root deps (see ``admin/requirements.txt``);
pulling pandas in at import time would make the whole console fail to start
wherever pandas is absent.  A missing dependency degrades THIS ONE panel with a
stated reason instead.
"""
from __future__ import annotations

from typing import Any


def _engine():
    """Import the engine on demand.  Returns (module, error_reason)."""
    try:
        from engine import macro_thesis
    except Exception as exc:  # noqa: BLE001 - any import failure degrades one panel
        return None, f"engine.macro_thesis unavailable: {exc}"
    return macro_thesis, None


def status() -> dict[str, Any]:
    engine, reason = _engine()
    return {
        "configured": engine is not None,
        "reason": reason,
        "tier": "ops/journal",
        "authority": (
            "none — a track record OF judgment, never a signal INTO the system. "
            "Never scores, ranks, gates or sizes any product surface."
        ),
        "store": "data/macro_thesis/ledger.jsonl (append-only, committed, keep-first)",
        "firewall": (
            "Forward and retro theses are graded and summarised separately. "
            "Retro rows are curated in hindsight and are never pooled into the "
            "forward track record."
        ),
    }


def panel() -> dict[str, Any]:
    """Graded ledger for the Macro Thesis page: separate forward + retro sections."""
    state = status()
    engine, _ = _engine()
    if engine is None:
        return {"ok": False, **state, "forward": None, "retro": None}
    try:
        graded = engine.grade()
    except Exception as exc:  # noqa: BLE001 - one bad row must not blank the console
        return {"ok": False, **state, "error": str(exc), "forward": None, "retro": None}
    return {
        "ok": True,
        **state,
        "forward": graded["forward"],
        "retro": graded["retro"],
        "planes": sorted(engine.PLANES),
        "directions": sorted(engine.DIRECTIONS),
        "authors": sorted(engine.AUTHORS),
        "entry_classes": sorted(engine.ENTRY_CLASSES),
    }


def register(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate + append one thesis.  Keep-first: an existing id is never overwritten."""
    engine, reason = _engine()
    if engine is None:
        return {"ok": False, "error": reason or "Macro Thesis ledger is unavailable"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "thesis must be an object"}
    try:
        result = engine.register(payload)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"registration failed: {exc}"}
    if not result.get("ok"):
        return result
    return {"ok": True, "thesis_id": result["thesis_id"],
            "title": result["thesis"]["title"],
            "entry_class": result["thesis"]["entry_class"]}
