"""engine/prophet_lab/response.py — assembles the ``prophet.lab_board/v1`` payload.

The single orchestration point: reads every source through the injectable
roots in ``sources.py``, then calls each pure board builder in ``boards.py``
and wraps the six boards in the frozen response envelope (LAB-0 §5) —
generation/source health, the all-false authority block, and the boards
themselves.  Nothing here writes anything; this module has no ``open(...,
"w")`` and no store mutation of any kind.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.prophet_lab import boards, sources
from engine.prophet_lab.contracts import (
    ALL_FALSE_AUTHORITY,
    BOARD_ALL_EARLY,
    BOARD_C1,
    BOARD_C2A,
    BOARD_C2_VARIANTS,
    BOARD_DEFINITIONS,
    BOARD_G0,
    BOARD_G0_C2A_INTERSECTION,
    SCHEMA_LAB_BOARD,
)


@dataclass(frozen=True)
class LabRoots:
    """Every injectable filesystem root the Lab projection reads.

    A ``None`` field degrades gracefully to an empty/absent source (see each
    ``sources.py`` reader's own docstring) rather than raising — a missing
    root is a health-note fact, never a 500. ``radar_spool_dir`` is now only
    the LOCAL FALLBACK half of the read ladder (day-2 commissioning prep,
    LAB-0 §6): ``sources.resolve_radar_spool`` tries R2 first (when
    credentials exist) and only reads this directory when R2 is not
    configured or fails with no fallback available.

    ``radar_spool_source_label`` (review S2, cheap half) is not a filesystem
    root at all: it is a short label naming WHICH env var/path the caller
    (``app/prophet_lab.py``) resolved ``radar_spool_dir`` from — kept purely
    as an operator diagnostic (``health.radar_spool_local_dir_env``, below).
    It no longer drives ``health.radar_spool_source`` — that field now names
    the actual BACKEND that served the read (``"r2"``/``"local"``/
    ``"unconfigured"``, from ``SpoolReadResult.backend``), per LAB-0 §6's
    explicit requirement that the health block say which transport resolved,
    not which local-dir env var would apply if the local dir were used.
    """

    radar_spool_dir: Path | str | None = None
    radar_spool_source_label: str = "unconfigured"
    radar_state_dir: Path | str | None = None
    prophet_index_path: Path | str | None = None
    enrichment_library_root: Path | str | None = None
    observation_baseline_path: Path | str | None = None


def _generated_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_lab_response(roots: LabRoots) -> dict[str, Any]:
    """The full ``GET /api/prophet/lab/v1`` payload."""
    spool_result = sources.resolve_radar_spool(roots.radar_spool_dir)
    envelopes = spool_result.envelopes
    events, first_observed_at = sources.extract_events(envelopes)
    episode_result = sources.read_live_episodes(roots.radar_state_dir)
    episodes = episode_result.episodes
    index = sources.read_prophet_index(roots.prophet_index_path)
    plans_by_ticker = sources.index_plans_by_ticker(index)
    library = sources.build_enrichment_library(roots.enrichment_library_root)
    baseline_result = sources.read_observation_baseline(roots.observation_baseline_path)
    raw_baseline = baseline_result.baseline

    # Review S1, fail CLOSED: a baseline that exists but whose coverage the
    # spool cannot actually verify (a gap between the claimed start and the
    # oldest evidence we can see) is treated as ABSENT for classification —
    # `raw_baseline` is kept separately so `generation.baseline_started_at`
    # can still report what was configured, while `effective_baseline` (the
    # one that actually reaches every board builder) is `None` whenever
    # coverage is unverified, which the existing "no baseline -> everything
    # retrospective_seed" rule (observation.py) already enforces.
    coverage_verified = sources.baseline_coverage_verified(envelopes, raw_baseline)
    effective_baseline = raw_baseline if coverage_verified else None

    sparks: dict[str, str] = {}
    common: dict[str, Any] = {
        "first_observed_at": first_observed_at,
        "baseline": effective_baseline,
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

    # Review S5: per-board availability, distinct from "genuinely empty".
    c1_availability: dict[str, Any] = {"available": episode_result.available}
    if not episode_result.available:
        c1_availability["reason"] = episode_result.reason
    board_availability = {
        BOARD_G0: {"available": True},
        BOARD_C1: dict(c1_availability),
        BOARD_C2A: {"available": True},
        BOARD_C2_VARIANTS: {"available": True},
        BOARD_G0_C2A_INTERSECTION: {"available": True},
        BOARD_ALL_EARLY: {
            "available": True,
            "components": {
                "g0": {"available": True},
                "c1": dict(c1_availability),
                "c2_variants": {"available": True},
            },
        },
    }

    # Review S4/S7: read OUTCOMES, not is_dir() alone — a schema-drifted spool
    # that silently parses to zero envelopes is now visible as
    # `radar_envelopes_skipped > 0` rather than indistinguishable from "empty
    # and clean". `radar_spool_source` (day-2 commissioning prep, LAB-0 §6)
    # now names the actual BACKEND that served the read ("r2"/"local"/
    # "unconfigured"), not which local-dir env var would apply.
    newest_envelope = sources.latest_envelope(envelopes)
    pack = newest_envelope.get("pack") if isinstance(newest_envelope, dict) else None
    pack = pack if isinstance(pack, dict) else {}
    generation = {
        "generated_at": _generated_at(),
        "latest_pass_ts": newest_envelope.get("pass_ts") if newest_envelope else None,
        "pack_as_of": pack.get("as_of"),
        "pack_hash": pack.get("pack_hash"),
        "baseline_started_at": (raw_baseline or {}).get("baseline_started_at"),
        "baseline_coverage_verified": coverage_verified,
    }

    health = {
        "radar_spool_configured": spool_result.configured,
        "radar_spool_readable": spool_result.readable,
        "radar_spool_source": spool_result.backend,
        # Operator diagnostic only (review S2's original cheap-half meaning):
        # which env var/path WOULD supply the local-fallback directory,
        # independent of whether the backend that actually served this read
        # was "r2" or "local".
        "radar_spool_local_dir_env": roots.radar_spool_source_label,
        "radar_envelopes_read": len(envelopes),
        "radar_envelopes_skipped": spool_result.envelopes_skipped,
        "radar_events_seen": len(events),
        "radar_episode_ledger_available": episode_result.available,
        "prophet_index_readable": bool(index),
        "prophet_plans_indexed": sum(len(v) for v in plans_by_ticker.values()),
        "enrichment_library_available": bool(library is not None and getattr(library, "available", False)),
        "observation_baseline_present": raw_baseline is not None,
        "observation_baseline_coverage_verified": coverage_verified,
    }
    # Fail-closed and VISIBLE (LAB-0 §6): an R2 credential/permission/network
    # failure must never look like an empty-and-clean spool. Set even when a
    # local fallback salvaged the read (`backend=="local"` with `.error`
    # still present) so the underlying R2 problem is never silently hidden
    # by a fallback that happened to work.
    if spool_result.error:
        health["radar_spool_error"] = spool_result.error
    # Review round 2, S4: a malformed marker (e.g. a naive/unparseable
    # baseline_started_at) is distinguishable by NAME from a spool-coverage
    # gap or a simply-unconfigured baseline -- both of which otherwise read
    # as the same "not verified" from this block alone.
    if baseline_result.error:
        health["observation_baseline_error"] = baseline_result.error

    return {
        "schema": SCHEMA_LAB_BOARD,
        "generation": generation,
        "health": health,
        "authority": dict(ALL_FALSE_AUTHORITY),
        "board_definitions": dict(BOARD_DEFINITIONS),
        "board_availability": board_availability,
        "boards": board_rows,
    }


__all__ = ["LabRoots", "build_lab_response"]
