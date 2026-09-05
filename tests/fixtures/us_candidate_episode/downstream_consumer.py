"""Commissioned downstream fixture for one canonical B1 episode reference."""
from __future__ import annotations

from pathlib import Path

from engine.us_candidate_episode import load_candidate_episode_store


def project_episode_reference(store_root: Path) -> list[dict[str, object]]:
    """Consume only the validated HEAD-backed store reader."""
    return [
        {
            "episode_id": row["episode_id"],
            "security_id": row["security_id"],
            "episode_state": row["episode_state"],
        }
        for row in load_candidate_episode_store(store_root)
    ]
