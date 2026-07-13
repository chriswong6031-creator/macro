"""engine.metabolism.throttle — Operator throttle variables (Metabolism V10/V11).

Reads METAB_INTENSITY and METAB_PACE from the environment on every call
(no caching) so that workflow-injected env overrides are always honoured.

Rulings:
    R-V10-1: METAB_* are operator-only knobs; loop-authored code never sets them.
              Intensity/pace scale *within* immutable budget caps — never past them.
    R-V10-2: Absent/invalid variable values resolve to today's behaviour exactly
              (normal intensity, single pace, all keys). A misconfiguration can
              never brick the loop.

V11 note: _PACE_EXTRA (single/2x/4x → extra-chain-runs-per-day) is kept for
backward compatibility with metabolism-cycle.yml pace gate; it has no new
callers after V11.  The new vocabulary is the LOOPS LADDER accessed via
pace_loops_per_window() — low=1, medium=2, high=3, max=4 loops per 5h window.

NEVER-RAISE CONTRACT: every public function catches all exceptions and returns
the safe fail-open default. Token values are never logged.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Intensity
# ---------------------------------------------------------------------------

INTENSITY_MULT: dict[str, float] = {
    "low": 0.5,
    "normal": 1.0,
    "high": 1.5,
    "max": 2.0,
}

_VALID_INTENSITIES = frozenset(INTENSITY_MULT)
_DEFAULT_INTENSITY = "normal"

_VALID_PACES = frozenset({"single", "2x", "4x", "low", "medium", "high", "max"})
_DEFAULT_PACE = "single"

# Extra chain-runner cycles (legacy V10 API — no production caller since V11).
# Ladder vocab maps analogously to legacy: low->0, medium->1, high->2, max->3.
# This keeps the function consistent even though pace_loops_per_window() is
# the canonical V11 accessor.
_PACE_EXTRA: dict[str, int] = {
    # Legacy tokens
    "single": 0,
    "2x": 1,
    "4x": 3,
    # V11 ladder (analogous mapping)
    "low": 0,
    "medium": 1,
    "high": 2,
    "max": 3,
}

# V11 loops ladder: METAB_PACE vocabulary -> loops per 5-hour window.
# V11 vocab:   low=1, medium=2, high=3, max=4
# Legacy compat: single->1, 2x->2, 4x->3 (kept for metabolism-cycle.yml pace gate)
_PACE_LOOPS: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "max": 4,
    # Legacy tokens (V10 and earlier)
    "single": 1,
    "2x": 2,
    "4x": 3,
}


def intensity() -> str:
    """Return the current intensity setting.

    Reads env METAB_INTENSITY; invalid/absent -> "normal". NEVER raises.
    """
    try:
        raw = os.environ.get("METAB_INTENSITY", "").strip().lower()
        if raw in _VALID_INTENSITIES:
            return raw
        if raw:
            log.warning("throttle.intensity: unknown value %r — defaulting to normal", raw)
        return _DEFAULT_INTENSITY
    except Exception as exc:  # noqa: BLE001
        log.warning("throttle.intensity: error %s — defaulting to normal", exc)
        return _DEFAULT_INTENSITY


def intensity_multiplier() -> float:
    """Return the float multiplier for the current intensity. NEVER raises."""
    try:
        return INTENSITY_MULT[intensity()]
    except Exception as exc:  # noqa: BLE001
        log.warning("throttle.intensity_multiplier: error %s — returning 1.0", exc)
        return 1.0


def pace() -> str:
    """Return the current pace setting.

    Reads env METAB_PACE; valid values are the V11 ladder vocab
    {"low","medium","high","max"} (canonical) and legacy {"single","2x","4x"}
    (accepted for backward compatibility).  The raw value is returned for any
    valid member — no remapping.  Invalid/absent -> "single".  NEVER raises.
    """
    try:
        raw = os.environ.get("METAB_PACE", "").strip().lower()
        if raw in _VALID_PACES:
            return raw
        if raw:
            log.warning("throttle.pace: unknown value %r — defaulting to single", raw)
        return _DEFAULT_PACE
    except Exception as exc:  # noqa: BLE001
        log.warning("throttle.pace: error %s — defaulting to single", exc)
        return _DEFAULT_PACE


def pace_extra_cycles(p: str | None = None) -> int:
    """Return the number of extra chain-runner cycles allowed today.

    Legacy mapping: single->0, 2x->1, 4x->3.
    Ladder mapping: low->0, medium->1, high->2, max->3.

    Note: this daily-extras API has no production caller since V11; it is
    retained for backward compatibility with metabolism-cycle.yml pace gate.
    The canonical V11 accessor is pace_loops_per_window().

    Pass p=None to read from env. NEVER raises.
    """
    try:
        resolved = p if p is not None else pace()
        result = _PACE_EXTRA.get(resolved)
        if result is None:
            log.warning("throttle.pace_extra_cycles: unknown pace %r — returning 0", resolved)
            return 0
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("throttle.pace_extra_cycles: error %s — returning 0", exc)
        return 0


def pace_loops_per_window(p: str | None = None) -> int:
    """Return the number of metabolism loops allowed per 5-hour window.

    V11 LOOPS LADDER (METAB_PACE vocabulary):
        low    → 1 loop per 5h window
        medium → 2 loops per 5h window
        high   → 3 loops per 5h window
        max    → 4 loops per 5h window

    Legacy compat (kept for metabolism-cycle.yml pace gate — no new callers):
        single → 1   (maps to low)
        2x     → 2   (maps to medium)
        4x     → 3   (maps to high)

    Absent or invalid METAB_PACE resolves to 1 (safe minimum). NEVER raises.

    Parameters
    ----------
    p : str | None
        Explicit pace string; None → read from METAB_PACE env var directly
        (bypasses the legacy pace() validator so V11 vocab is accepted).
    """
    try:
        if p is not None:
            resolved = str(p).strip().lower()
        else:
            resolved = os.environ.get("METAB_PACE", "").strip().lower()
        result = _PACE_LOOPS.get(resolved)
        if result is not None:
            return result
        if resolved:
            log.warning(
                "throttle.pace_loops_per_window: unknown pace %r — defaulting to 1",
                resolved,
            )
        return 1
    except Exception as exc:  # noqa: BLE001
        log.warning("throttle.pace_loops_per_window: error %s — returning 1", exc)
        return 1


def describe() -> dict:
    """Return a snapshot dict suitable for logging and the admin panel. NEVER raises."""
    try:
        i = intensity()
        p = pace()
        return {
            "intensity": i,
            "multiplier": INTENSITY_MULT.get(i, 1.0),
            "pace": p,
            "extra_cycles": pace_extra_cycles(p),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("throttle.describe: error %s — returning safe defaults", exc)
        return {
            "intensity": _DEFAULT_INTENSITY,
            "multiplier": 1.0,
            "pace": _DEFAULT_PACE,
            "extra_cycles": 0,
        }
