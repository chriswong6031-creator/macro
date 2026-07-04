"""Oracle dark tilt — maps onset-tier episode nodes to a bounded [-1, 1] tilt dict.

GATED by config.yml key oracle.tilt_enabled (default false).
When the gate is OFF this module has NO import side effects on stock scoring.

API
---
oracle_theme_tilt(oracle_state, cfg=None) -> dict[str, float]
    Maps active episode nodes to a tilt in [-1, 1].
    Returns an EMPTY dict when the gate is off.

The tilt dict is compatible with engine.spotlight.theme_tilt consumers:
  positive  → tailwind for names in that sector/theme (in-episode node)
  negative  → headwind (out-episode node)
  clamped   → [-1, 1]

R4 binding: tilt_enabled stays False (default) until Phase-0 survival is registered.
The two-sided regression test (tests/test_oracle_tilt.py) verifies:
  (a) flag OFF → engine.stock_score output byte-identical on a fixture (no oracle
      import side effects beyond this module existing)
  (b) flag ON with a fixture tilt → _axis_tailwind shifts by the expected clamped
      amount for ≥1 member.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# Tilt magnitude by episode tier.  onset is smallest (lowest certainty).
_TIER_TILT: dict[str, float] = {
    "onset": 0.20,
    "confirmed": 0.45,
    "undeniable": 0.60,
}

# Maximum absolute tilt — never exceeds this regardless of tier.
_MAX_TILT = 0.60


def _is_gate_on(cfg: dict | None) -> bool:
    """Read oracle.tilt_enabled from config dict.  Default = False (R4)."""
    if cfg is None:
        try:
            from lib import config as _lib_cfg
            cfg = _lib_cfg.load()
        except Exception:  # noqa: BLE001
            return False
    oracle_cfg = cfg.get("oracle") if isinstance(cfg, dict) else None
    if not isinstance(oracle_cfg, dict):
        return False
    return bool(oracle_cfg.get("tilt_enabled", False))


def oracle_theme_tilt(
    oracle_state: dict | None,
    cfg: dict | None = None,
) -> dict[str, float]:
    """Map active episode nodes → tilt in [-1, 1].

    Parameters
    ----------
    oracle_state : dict | None
        Payload from engine.oracle.live.build_oracle_state().
    cfg : dict | None
        Parsed config.yml dict.  Reads oracle.tilt_enabled.
        Loads from lib.config if None.

    Returns
    -------
    dict[str, float]
        {node: tilt} — empty dict when gate is OFF or no active episodes.
    """
    if not _is_gate_on(cfg):
        return {}
    if not oracle_state:
        return {}

    _tier_rank = {"undeniable": 3, "confirmed": 2, "onset": 1}
    best: dict[str, tuple[int, float]] = {}  # node → (rank, tilt)

    for ep in (oracle_state.get("active_episodes") or []):
        node = ep.get("node")
        if not node:
            continue
        direction = ep.get("direction", "")
        tier = ep.get("tier", "onset")
        rank = _tier_rank.get(tier, 0)
        base = _TIER_TILT.get(tier, 0.20)
        # in = positive tilt (money flowing in), out = negative (flowing out)
        raw = base if direction == "in" else -base
        tilt = max(-_MAX_TILT, min(_MAX_TILT, raw))

        existing = best.get(node)
        if existing is None or rank > existing[0]:
            best[node] = (rank, tilt)

    return {node: round(v[1], 4) for node, v in best.items()}


def oracle_tilt_by_etf(cfg: dict | None = None, state_path=None) -> dict[str, float]:
    """{sector ETF → tilt} from ACTIVE Tier-S episodes — the map the stock-library
    spotlight context consumes (scripts/build_stock_library._spotlight_for).

    Empty dict when the gate (oracle.tilt_enabled) is OFF, when the oracle state
    payload is absent, or on any error — flag OFF must leave stock scoring
    byte-identical (R5 two-sided contract; tests enforce both sides)."""
    if not _is_gate_on(cfg):
        return {}
    try:
        import json
        from pathlib import Path
        if state_path is None:
            from lib import config as _lib_cfg
            site = _lib_cfg.ROOT / _lib_cfg.load()["storage"]["site_dir"]
            state_path = Path(site) / "basketdata" / "oracle_state.json"
        state = json.loads(Path(state_path).read_text())
    except Exception:  # noqa: BLE001 — degrade, never break scoring
        return {}
    tilts = oracle_theme_tilt(state, cfg)
    try:
        from engine.spotlight import GICS_TO_ETF
        etfs = set(GICS_TO_ETF.values())
    except Exception:  # noqa: BLE001
        etfs = {"XLK", "XLV", "XLF", "XLY", "XLC", "XLI", "XLP", "XLE", "XLU", "XLRE", "XLB"}
    return {node: t for node, t in tilts.items() if node in etfs}
