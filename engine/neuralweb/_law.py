"""engine.neuralweb._law — Authority-gate helpers (R5 §5.1).

Two tiny utilities used by every new R5 world_state composer and the §5.5
authority test wall:

  display_only(d)         — stamps display_only=True on a lobe dict.
  assert_no_authority(p)  — walks a payload; returns a list of violations.

AUTHORITY CONTRACT
------------------
All R5 world_state lobes sit at A0/A1 on the ladder.  Every lobe must carry
display_only=True.  No R5 output may name, touch, or condition any Article-2
surface (alert_triage, board_ordering, top_setups, attention_queue, push_floor)
or expose the five authority booleans in a truthy state.

These helpers are also available for opportunistic migration of existing call
sites, but are not retroactively required of pre-R5 lobes.
"""
from __future__ import annotations

from typing import Any


# Article-2 surface key names — no R5 lobe may carry these
_ARTICLE_2_KEYS = frozenset({
    "alert_triage",
    "board_ordering",
    "top_setups",
    "attention_queue",
    "push_floor",
})

# The five Mastermind authority boolean keys
_AUTHORITY_BOOLEANS = frozenset({
    "can_add_candidates",
    "can_raise_size",
    "can_lower_size",
    "can_block_entry",
    "can_force_exit",
})


def display_only(d: dict) -> dict:
    """Set d['display_only'] = True and return d.

    Used as a terminal decorator inside every R5 lobe composer:
        return display_only({...})
    """
    d["display_only"] = True
    return d


def assert_no_authority(payload: Any, _path: str = "root") -> list[str]:
    """Walk *payload* recursively; return a list of authority violation strings.

    Violations:
    - Any of the five authority booleans present and True.
    - Any non-empty ``scored_path_surfaces`` list.
    - Any Article-2 surface key present at any depth.

    Parameters
    ----------
    payload:
        The object to inspect — dict, list, or scalar.
    _path:
        Internal bookkeeping; callers should leave this as the default.

    Returns
    -------
    list[str]
        Empty list means no violations.
    """
    violations: list[str] = []

    if isinstance(payload, dict):
        for key, val in payload.items():
            loc = f"{_path}.{key}"

            # Five authority booleans — violation only when truthy
            if key in _AUTHORITY_BOOLEANS and val:
                violations.append(f"{loc}: authority boolean is True")

            # Non-empty scored_path_surfaces
            if key == "scored_path_surfaces" and val:
                violations.append(f"{loc}: non-empty scored_path_surfaces={val!r}")

            # Article-2 surface keys — presence alone is a violation
            if key in _ARTICLE_2_KEYS:
                violations.append(f"{loc}: Article-2 surface key present")

            # Recurse
            violations.extend(assert_no_authority(val, loc))

    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            violations.extend(assert_no_authority(item, f"{_path}[{i}]"))

    return violations
