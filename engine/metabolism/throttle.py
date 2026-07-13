"""engine.metabolism.throttle — Operator throttle variables (Metabolism V10).

Reads METAB_INTENSITY and METAB_PACE from the environment on every call
(no caching) so that workflow-injected env overrides are always honoured.

Rulings:
    R-V10-1: METAB_* are operator-only knobs; loop-authored code never sets them.
              Intensity/pace scale *within* immutable budget caps — never past them.
    R-V10-2: Absent/invalid variable values resolve to today's behaviour exactly
              (normal intensity, single pace, all keys). A misconfiguration can
              never brick the loop.

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

_VALID_PACES = frozenset({"single", "2x", "4x"})
_DEFAULT_PACE = "single"

_PACE_EXTRA: dict[str, int] = {
    "single": 0,
    "2x": 1,
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

    Reads env METAB_PACE in {"single","2x","4x"}; invalid/absent -> "single".
    NEVER raises.
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

    single->0, 2x->1, 4x->3. Pass p=None to read from env. NEVER raises.
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
