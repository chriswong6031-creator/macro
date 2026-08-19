"""engine/prophet_lab/response.py — assembles the ``prophet.lab_board/v1`` payload.

The single orchestration point: reads every source through the injectable
roots in ``sources.py``, then calls each pure board builder in ``boards.py``
and wraps the six boards in the frozen response envelope (LAB-0 §5) —
generation/source health, the all-false authority block, and the boards
themselves.  Nothing here writes anything; this module has no ``open(...,
"w")`` and no store mutation of any kind.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.prophet_lab import boards, sources
from engine.prophet_lab.contracts import (
    ALL_FALSE_AUTHORITY,
    BOARD_ALL_EARLY,
    BOARD_C1,
    BOARD_C2A,
    BOARD_C2_VARIANTS,
    BOARD_G0,
    BOARD_G0_C2A_INTERSECTION,
    SCHEMA_LAB_BOARD,
)


@dataclass(frozen=True)
class LabRoots:
    """Every injectable filesystem root the Lab projection reads.

    A ``None`` field degrades gracefully to an empty/absent source (see each
    ``sources.py`` reader's own docstring) rather than raising — a missing
    root is a health-note fact, never a 500.
    """

    radar_spool_dir: Path | str | None = None
    radar_state_dir: Path | str | None = None
    prophet_index_path: Path | str | None = None
    enrichment_library_root: Path | str | None = None
    observation_baseline_path: Path | str | None = None


def build_lab_response(roots: LabRoots) -> dict[str, Any]:
    """The full ``GET /api/prophet/lab/v1`` payload."""
    envelopes = sources.read_radar_envelopes(roots.radar_spool_dir)
    events, first_observed_at = sources.extract_events(envelopes)
    episodes = sources.read_live_episodes(roots.radar_state_dir)
    index = sources.read_prophet_index(roots.prophet_index_path)
    plans_by_ticker = sources.index_plans_by_ticker(index)
    library = sources.build_enrichment_library(roots.enrichment_library_root)
    baseline = sources.read_observation_baseline(roots.observation_baseline_path)
    sparks: dict[str, str] = {}

    common: dict[str, Any] = {
        "first_observed_at": first_observed_at,
        "baseline": baseline,
        "plans_by_ticker": plans_by_ticker,
        "library": library,
        "sparks": sparks,
    }

    board_rows = {
        BOARD_G0: boards.build_g0_board(events, **common),
        BOARD_C1: boards.build_c1_board(events, episodes=episodes, **common),
        BOARD_C2A: boards.build_c2a_board(events, **common),
        BOARD_C2_VARIANTS: boards.build_c2_variants_board(events, **common),
        BOARD_G0_C2A_INTERSECTION: boards.build_intersection_board(events, **common),
        BOARD_ALL_EARLY: boards.build_all_early_board(events, episodes=episodes, **common),
    }

    health = {
        "radar_spool_readable": bool(roots.radar_spool_dir) and Path(str(roots.radar_spool_dir)).is_dir(),
        "radar_envelopes_read": len(envelopes),
        "radar_events_seen": len(events),
        "radar_episode_ledger_readable": bool(roots.radar_state_dir) and Path(str(roots.radar_state_dir)).is_dir(),
        "prophet_index_readable": bool(index),
        "prophet_plans_indexed": sum(len(v) for v in plans_by_ticker.values()),
        "enrichment_library_available": bool(library is not None and getattr(library, "available", False)),
        "observation_baseline_present": baseline is not None,
    }

    return {
        "schema": SCHEMA_LAB_BOARD,
        "health": health,
        "authority": dict(ALL_FALSE_AUTHORITY),
        "boards": board_rows,
    }


__all__ = ["LabRoots", "build_lab_response"]
