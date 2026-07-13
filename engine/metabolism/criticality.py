"""engine.metabolism.criticality — Deterministic lobe criticality evidence (V9 Layer 1).

Profiles EVERY lobe in config/lobe_charters.yml from existing sources of truth only:
  - mastermind_context constants (imported, never copied)
  - synapse.yml external_consumers tags
  - synapse.yml cadence/freshness_sla_hours/consumers/external_consumers
  - lobe_charters.yml tier/lifecycle_state/information_domain/fitness_sensors

INERTNESS GUARANTEE:
    This module writes data/metabolism/lobe_criticality.json (display-tier only).
    It dispatches NOTHING, grants NOTHING, opens NO PR, touches NO lobe roster.
    It never calls an LLM.

SCHEMA: metabolism.criticality.v1

NEVER-RAISE CONTRACT: every public function catches all exceptions, logs, returns safe fallback.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "metabolism.criticality.v1"
STRUCTURAL_BANDS = ("CRITICAL", "HIGH", "STANDARD", "ANCILLARY")

CRITICALITY_PATH = Path("data") / "metabolism" / "lobe_criticality.json"

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "shadow",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path",
        "dispatch", "grant", "pr_open", "lobe_roster_change",
    ],
}


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_mastermind_constants() -> tuple[dict[str, list[str]], tuple[str, ...]]:
    """Import _LOBE_TO_ARTIFACT_IDS and _MARKET_DATA_LOBES from mastermind_context.

    Returns (lobe_to_artifact_ids, market_data_lobes).
    On import failure, returns ({}, ()) — graceful degradation.
    NEVER raises.
    """
    try:
        from engine.neuralweb.mastermind_context import (  # noqa: PLC0415
            _LOBE_TO_ARTIFACT_IDS,
            _MARKET_DATA_LOBES,
        )
        return dict(_LOBE_TO_ARTIFACT_IDS), tuple(_MARKET_DATA_LOBES)
    except Exception as exc:  # noqa: BLE001
        log.warning("criticality: mastermind_context import failed (degrading) — %s", exc)
        return {}, ()


def _load_yaml(path: Path) -> dict | None:
    """Load a YAML file; return None on any error."""
    try:
        import yaml  # noqa: PLC0415
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("criticality: cannot load %s — %s", path, exc)
        return None


def _load_charters(root: Path) -> dict[str, dict]:
    """Load lobe charters; return {} on any error."""
    data = _load_yaml(root / "config" / "lobe_charters.yml")
    if not data:
        return {}
    return (data.get("charters") or {})


def _load_synapse_artifacts(root: Path) -> dict[str, dict]:
    """Load synapse artifact registry; return {} on any error."""
    data = _load_yaml(root / "config" / "synapse.yml")
    if not data:
        return {}
    return (data.get("artifacts") or {})


def _is_loop_managed(charter: dict) -> bool:
    """Return True iff the lobe qualifies as loop-managed.

    Mirror of scripts/metabolism_propose.py _discover_loop_managed_lobes logic:
      - lifecycle_state in ("active", "probation")
      - fitness_sensors is a list of dicts each having "id" and "store" keys
    """
    lc_state = (charter or {}).get("lifecycle_state") or ""
    if lc_state not in ("active", "probation"):
        return False
    sensors = (charter or {}).get("fitness_sensors") or []
    if not isinstance(sensors, list) or not sensors:
        return False
    return all(isinstance(s, dict) and "id" in s and "store" in s for s in sensors)


def _structural_band(evidence: dict) -> str:
    """Apply the structural band ladder (first match wins).

    CRITICAL — nw_core or nw_anchor
    HIGH     — nw_context or consumer_fanout >= 4 or tier in ("scored","confirmer")
    STANDARD — daily cadence and lifecycle_state == "active"
    ANCILLARY — everything else
    """
    if evidence["nw_core"] or evidence["nw_anchor"]:
        return "CRITICAL"
    if (
        evidence["nw_context"]
        or evidence["consumer_fanout"] >= 4
        or evidence["tier"] in ("scored", "confirmer")
    ):
        return "HIGH"
    if evidence["cadence"] == "daily" and evidence["lifecycle_state"] == "active":
        return "STANDARD"
    return "ANCILLARY"


def _profile_lobe(
    lobe_id: str,
    charter: dict,
    synapse_artifacts: dict[str, dict],
    lobe_to_artifact_ids: dict[str, list[str]],
    market_data_lobes: tuple[str, ...],
    # Reverse index: artifact_id -> list of summarizer lobe names that own it
    artifact_to_summarizers: dict[str, list[str]],
) -> dict:
    """Profile a single lobe and return its evidence + structural band."""
    # ── NW core: lobe's own artifact id appears in _LOBE_TO_ARTIFACT_IDS values ──
    # The lobe_id must appear as a VALUE (the artifact id) in any summarizer's list.
    # We check via the reverse map built from _LOBE_TO_ARTIFACT_IDS.
    nw_core = lobe_id in artifact_to_summarizers
    market_data = False
    if nw_core:
        # market_data flag True if any summarizer that backs this artifact is
        # named in _MARKET_DATA_LOBES
        for summarizer_name in artifact_to_summarizers.get(lobe_id, []):
            if summarizer_name in market_data_lobes:
                market_data = True
                break

    # ── Synapse artifact entry for this lobe ──
    art = synapse_artifacts.get(lobe_id) or {}
    external_consumers: list[str] = art.get("external_consumers") or []
    consumers: list[str] = art.get("consumers") or []

    nw_context = "mastermind:context" in external_consumers
    nw_anchor = "mastermind:anchor" in external_consumers
    nw_vendored = "mastermind:vendored" in external_consumers

    consumer_fanout = len(consumers) + len(external_consumers)

    cadence = art.get("cadence") or None
    # Normalize cadence: "daily-engine" and "daily" both count as "daily"
    if cadence and "daily" in str(cadence).lower():
        cadence = "daily"
    freshness_sla_hours = art.get("freshness_sla_hours") or None

    # ── From charter ──
    tier = (charter or {}).get("tier") or "display"
    lifecycle_state = (charter or {}).get("lifecycle_state") or "active"
    information_domain = (charter or {}).get("information_domain") or None
    loop_managed = _is_loop_managed(charter or {})

    evidence = {
        "nw_core": nw_core,
        "market_data": market_data,
        "nw_context": nw_context,
        "nw_anchor": nw_anchor,
        "nw_vendored": nw_vendored,
        "consumer_fanout": consumer_fanout,
        "cadence": cadence,
        "freshness_sla_hours": freshness_sla_hours,
        "tier": tier,
        "information_domain": information_domain,
        "loop_managed": loop_managed,
        "lifecycle_state": lifecycle_state,
    }

    band = _structural_band(evidence)
    return {"structural_band": band, **evidence}


def build_criticality(root: Path | None = None, write: bool = True) -> dict:
    """Profile every lobe in config/lobe_charters.yml and return the criticality artifact.

    Parameters
    ----------
    root : Path | None
        Repo root override for testing.
    write : bool
        If True (default), writes data/metabolism/lobe_criticality.json.

    Returns
    -------
    dict — criticality artifact (schema metabolism.criticality.v1). NEVER raises.
    """
    try:
        return _build_criticality_inner(root=root, write=write)
    except Exception as exc:  # noqa: BLE001
        log.warning("criticality.build_criticality: fatal — %s", exc)
        return {
            "schema": SCHEMA,
            "as_of": _now_date(),
            "generated_by": "metabolism_criticality",
            "lobes": {},
            "counts": {b: 0 for b in STRUCTURAL_BANDS},
            "authority": AUTHORITY_BLOCK,
            "degraded_reason": f"fatal error: {exc}",
        }


def _build_criticality_inner(root: Path | None, write: bool) -> dict:
    """Inner builder — may raise; wrapped by build_criticality."""
    repo = _repo_root(root)

    lobe_to_artifact_ids, market_data_lobes = _load_mastermind_constants()

    # Build reverse index: artifact_id -> list[summarizer_lobe_name]
    # So if _LOBE_TO_ARTIFACT_IDS = {"market": ["world-state"]},
    # then artifact_to_summarizers = {"world-state": ["market"]}
    artifact_to_summarizers: dict[str, list[str]] = {}
    for summarizer_name, art_ids in lobe_to_artifact_ids.items():
        for art_id in (art_ids or []):
            artifact_to_summarizers.setdefault(art_id, []).append(summarizer_name)

    charters = _load_charters(repo)
    synapse_artifacts = _load_synapse_artifacts(repo)

    lobes: dict[str, dict] = {}
    counts: dict[str, int] = {b: 0 for b in STRUCTURAL_BANDS}

    for lobe_id, charter in charters.items():
        try:
            profile = _profile_lobe(
                lobe_id=lobe_id,
                charter=charter or {},
                synapse_artifacts=synapse_artifacts,
                lobe_to_artifact_ids=lobe_to_artifact_ids,
                market_data_lobes=market_data_lobes,
                artifact_to_summarizers=artifact_to_summarizers,
            )
            lobes[lobe_id] = profile
            counts[profile["structural_band"]] = counts.get(profile["structural_band"], 0) + 1
        except Exception as exc:  # noqa: BLE001
            log.warning("criticality: failed to profile lobe %r — %s", lobe_id, exc)
            lobes[lobe_id] = {
                "structural_band": "ANCILLARY",
                "nw_core": False, "market_data": False,
                "nw_context": False, "nw_anchor": False, "nw_vendored": False,
                "consumer_fanout": 0, "cadence": None, "freshness_sla_hours": None,
                "tier": "display", "information_domain": None, "loop_managed": False,
                "lifecycle_state": "active",
                "error": str(exc),
            }
            counts["ANCILLARY"] = counts.get("ANCILLARY", 0) + 1

    artifact: dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _now_date(),
        "generated_by": "metabolism_criticality",
        "lobes": lobes,
        "counts": counts,
        "authority": AUTHORITY_BLOCK,
    }

    if write:
        out_path = repo / CRITICALITY_PATH
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("criticality: wrote %s (%d lobes)", out_path, len(lobes))

    return artifact


def load_criticality(root: Path | None = None) -> dict:
    """Read the criticality artifact from disk.

    Returns {} on any error. NEVER raises.
    """
    try:
        repo = _repo_root(root)
        p = repo / CRITICALITY_PATH
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.debug("criticality.load_criticality: %s", exc)
        return {}
