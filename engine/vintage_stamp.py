"""engine/vintage_stamp.py — R3 v1 vintage stamp helper.

Produces the 8-field provenance stamp required by every rule-replay output and any
future study harness that consumes price paths from ``massive_stock_day``.

Per §3.4 of NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md:
  price_plane_id      — identifier for the price data plane used
  adjustment_mode     — how the close series was adjusted (e.g. "split_adjusted_raw")
  universe_as_of      — ISO date string: the date the universe membership was fixed
  frame               — point-in-time basis descriptor (e.g. "pit_massive_era_law")
  survivorship_biased — True if the cohort is pre-2021 (or non-massive)
  coverage_frac       — fraction [0.0, 1.0] of fires with valid price paths
  dead_name_coverage_pct — from data/edgar/_dead_name_coverage.json if present else None
  era_law_cohort      — which cohort split (e.g. "verdict_grade_2021plus")

The result is a plain dict, fully JSON-serializable. Callers that fail to pass a
valid stamp receive a StampRefusal (ValueError subclass) — the contract is: no stamp,
no serialization.

``dead_name_coverage_pct`` reads ``data/edgar/_dead_name_coverage.json`` (key
``"coverage_pct"``) when present; on absence it writes null with
``stamp_degraded=True`` in the returned dict.

Usage::

    from engine.vintage_stamp import vintage_stamp, StampRefusal
    stamp = vintage_stamp(
        price_plane_id="massive_stock_day_v1",
        adjustment_mode="split_adjusted_raw",
        universe_as_of="2026-07-06",
        frame="pit_massive_era_law",
        survivorship_biased=False,
        coverage_frac=0.98,
        dead_name_coverage_pct=None,   # or pass explicitly; None triggers file lookup
        era_law_cohort="verdict_grade_2021plus",
    )
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Sentinel: callers catch this to distinguish "stamp refused" from other errors
# ---------------------------------------------------------------------------
class StampRefusal(ValueError):
    """Raised when a caller tries to serialise replay results without a stamp."""


# ---------------------------------------------------------------------------
# Default location of the dead-name coverage metadata
# ---------------------------------------------------------------------------
def _default_dead_name_path() -> Path:
    """Repo-relative path: engine/ → repo root → data/edgar/_dead_name_coverage.json."""
    return Path(__file__).resolve().parent.parent / "data" / "edgar" / "_dead_name_coverage.json"


def _load_dead_name_coverage(path: Path | None = None) -> tuple[float | None, bool]:
    """Return (coverage_pct, degraded).

    coverage_pct: float (percentage, 0–100) from the JSON file, or None.
    degraded:     True when the file is absent or unreadable.

    Key lookup order (to handle schema evolution):
      1. ``price_coverage_frac`` — v2 schema (fraction, multiply by 100)
      2. ``coverage_frac``       — generic fraction key (multiply by 100)
      3. ``coverage_pct``        — legacy percentage key (use as-is)
    """
    p = path or _default_dead_name_path()
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        # Try fractional keys first (value in [0, 1] → convert to pct)
        for frac_key in ("price_coverage_frac", "coverage_frac"):
            if frac_key in data and data[frac_key] is not None:
                return float(data[frac_key]) * 100.0, False
        # Fallback: legacy percentage key (value already in pct)
        val = data.get("coverage_pct")
        if val is None:
            return None, True
        return float(val), False
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
        return None, True


# ---------------------------------------------------------------------------
# The public stamp builder
# ---------------------------------------------------------------------------
def vintage_stamp(
    price_plane_id: str,
    adjustment_mode: str,
    universe_as_of: str,
    frame: str,
    survivorship_biased: bool,
    coverage_frac: float,
    dead_name_coverage_pct: float | None,
    era_law_cohort: str,
    *,
    _dead_name_path: Path | None = None,
) -> dict[str, Any]:
    """Build and return the 8-field R3 v1 vintage stamp dict.

    Parameters
    ----------
    price_plane_id : str
        Identifier for the price data plane, e.g. "massive_stock_day_v1".
    adjustment_mode : str
        How the close series was adjusted, e.g. "split_adjusted_raw".
    universe_as_of : str
        ISO-8601 date string (e.g. "2026-07-06") for universe membership.
    frame : str
        Point-in-time basis descriptor, e.g. "pit_massive_era_law".
    survivorship_biased : bool
        True when the cohort lacks a delisted-name recall floor (pre-2021 or
        non-massive source).
    coverage_frac : float
        Fraction [0.0, 1.0] of fires with a valid forward price path.
    dead_name_coverage_pct : float | None
        Caller may pass the pre-loaded value; None triggers a file read from
        ``data/edgar/_dead_name_coverage.json``.  Pass ``...`` (Ellipsis) to
        force the file read regardless of the passed value — useful for tests
        that want to see the degraded path.
    era_law_cohort : str
        Cohort split identifier, e.g. "verdict_grade_2021plus".
    _dead_name_path : Path | None
        Override for the dead-name JSON path (test injection point).

    Returns
    -------
    dict
        Fully JSON-serializable stamp dict.  Contains ``stamp_degraded=True``
        when dead-name coverage was unavailable.
    """
    # Validate required string fields
    for name, val in [
        ("price_plane_id", price_plane_id),
        ("adjustment_mode", adjustment_mode),
        ("universe_as_of", universe_as_of),
        ("frame", frame),
        ("era_law_cohort", era_law_cohort),
    ]:
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"vintage_stamp: {name!r} must be a non-empty string, got {val!r}")

    if not isinstance(survivorship_biased, bool):
        raise TypeError(
            f"vintage_stamp: survivorship_biased must be bool, got {type(survivorship_biased).__name__}"
        )

    if not isinstance(coverage_frac, (int, float)) or not (0.0 <= float(coverage_frac) <= 1.0):
        raise ValueError(
            f"vintage_stamp: coverage_frac must be in [0.0, 1.0], got {coverage_frac!r}"
        )

    # Resolve dead_name_coverage_pct
    degraded = False
    if dead_name_coverage_pct is None or dead_name_coverage_pct is ...:
        dead_name_coverage_pct, degraded = _load_dead_name_coverage(_dead_name_path)
    else:
        dead_name_coverage_pct = float(dead_name_coverage_pct)

    stamp: dict[str, Any] = {
        "price_plane_id": price_plane_id,
        "adjustment_mode": adjustment_mode,
        "universe_as_of": universe_as_of,
        "frame": frame,
        "survivorship_biased": survivorship_biased,
        "coverage_frac": float(coverage_frac),
        "dead_name_coverage_pct": dead_name_coverage_pct,
        "era_law_cohort": era_law_cohort,
    }
    if degraded:
        stamp["stamp_degraded"] = True

    return stamp


def require_stamp(stamp: Any) -> dict[str, Any]:
    """Assert that ``stamp`` is a valid vintage stamp dict, or raise StampRefusal.

    Called by ``rule_replay.serialize_results`` before any serialization. A missing
    or structurally incomplete stamp is a hard refusal — the spec mandates this gate.
    """
    REQUIRED = {
        "price_plane_id", "adjustment_mode", "universe_as_of", "frame",
        "survivorship_biased", "coverage_frac", "dead_name_coverage_pct",
        "era_law_cohort",
    }
    if not isinstance(stamp, dict):
        raise StampRefusal(
            "Results cannot be serialized without a valid vintage stamp. "
            f"Got type {type(stamp).__name__!r}; expected a dict from vintage_stamp()."
        )
    missing = REQUIRED - stamp.keys()
    if missing:
        raise StampRefusal(
            f"Results cannot be serialized: vintage stamp is missing required fields: "
            f"{sorted(missing)}. Build one with engine.vintage_stamp.vintage_stamp()."
        )
    return stamp
