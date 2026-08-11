"""Authenticated admin entry point for the private runtime-truth collector."""
from __future__ import annotations

from pathlib import Path

from lib.project_runtime_state import (
    SystemEvidenceReader,
    collect_runtime_state,
    load_topology,
    validate_snapshot,
)

_ROOT = Path(__file__).resolve().parent.parent
_TOPOLOGY = _ROOT / "config" / "production_topology.yml"
_SCHEMA = _ROOT / "contracts" / "runtime" / "mastermind.runtime_state.v1.schema.json"


def snapshot() -> tuple[dict, int]:
    """Collect on demand; return only a bounded reason code when collection fails."""
    evidence_mode = "vps" if Path("/opt/macro").is_dir() else "local"
    try:
        topology = load_topology(_TOPOLOGY)
        state = collect_runtime_state(
            topology,
            reader=SystemEvidenceReader(mode=evidence_mode, repo_root=_ROOT),
            mode="admin",
        )
        validate_snapshot(state, _SCHEMA)
        return state, 200
    except Exception:  # noqa: BLE001 - never return raw exception/error text
        return {
            "schema": "mastermind.runtime_state.error.v1",
            "project_id": "mastermind-x",
            "state": "indeterminate",
            "reason_code": "collection_failed",
        }, 503


__all__ = ["snapshot"]
