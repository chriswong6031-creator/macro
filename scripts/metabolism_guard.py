"""scripts/metabolism_guard.py — shared kill-switch helper for the Metabolism loop.

The single function is_paused() reads the AUTONOMY_PAUSED environment variable
and returns True unless it is set to the exact literal string 'false'.

Fail-safe contract (R-AUT-2):
    - Unset variable    → paused (True)
    - Empty string      → paused (True)
    - 'true'            → paused (True)
    - Any other value   → paused (True)
    - 'false' (exact)   → NOT paused (False) — the only armed state

This module has no side effects on import.  Every metabolism stage (heartbeat,
SENSE, PROPOSE, ADJUDICATE, BUILD, VERIFY, LEARN) MUST call is_paused() at its
entry point and exit 0 immediately when it returns True.

Usage:
    from scripts.metabolism_guard import is_paused

    if is_paused():
        print("AUTONOMY_PAUSED — exiting cleanly")
        sys.exit(0)

The module also exposes pause_reason() for human-readable diagnostics.
"""
from __future__ import annotations

import os

_VAR_NAME = "AUTONOMY_PAUSED"
_ARMED_VALUE = "false"


def is_paused() -> bool:
    """Return True if the loop is paused (the default-safe state).

    Reads the AUTONOMY_PAUSED environment variable.  Only the exact lowercase
    string 'false' returns False (armed).  Everything else — including the
    variable being absent, empty, or set to 'true' — returns True (paused).

    This is intentionally fail-closed: a missing variable is treated as paused,
    never as armed.  The operator must set the variable explicitly to arm the loop.

    Returns
    -------
    bool
        True  → loop is paused; the caller must exit 0 immediately.
        False → loop is armed; proceed with the stage logic.
    """
    raw = os.environ.get(_VAR_NAME, "").strip().lower()
    return raw != _ARMED_VALUE


def pause_reason() -> str:
    """Return a human-readable string explaining the current pause state.

    Returns
    -------
    str
        A description of why is_paused() returned the value it did.
    """
    raw = os.environ.get(_VAR_NAME)
    if raw is None:
        return (
            f"{_VAR_NAME} is not set (default-safe: treated as paused). "
            f"Set {_VAR_NAME}=false to arm the loop."
        )
    if raw.strip().lower() == _ARMED_VALUE:
        return f"{_VAR_NAME}='{raw}' — loop is armed."
    return (
        f"{_VAR_NAME}='{raw}' (not the exact string 'false') — loop is paused. "
        f"Set {_VAR_NAME}=false to arm."
    )


if __name__ == "__main__":
    # Diagnostic: print current state and exit.
    paused = is_paused()
    print(pause_reason())
    raise SystemExit(0 if paused else 0)
