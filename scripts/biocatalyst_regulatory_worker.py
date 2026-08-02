"""Dark-by-default B4A Drugs@FDA worker control plane.

This is deliberately separate from ``scripts/biocatalyst_worker.py``.  It has
its own reserved future state root, lock, service and timer identity, and refuses any network collection
while the source registry marks Drugs@FDA as unreviewed.  B4A therefore proves
replay/pointer mechanics with synthetic fixtures without creating a second B1
or B2 writer or a public product API.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

import yaml


class RegulatoryWorkerConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegulatoryWorkerPlan:
    enabled: bool
    state_root: Path
    source_registry: Path


def _enabled(value: str | None) -> bool:
    if value in {None, "", "0", "false", "False"}:
        return False
    if value == "1":
        return True
    raise RegulatoryWorkerConfigError("BIOCATALYST_REGULATORY_ENABLED must be 0 or 1")


def _registry_allows_production(path: Path) -> bool:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        source = payload["sources"]["drugs_at_fda"]
    except (OSError, TypeError, KeyError, yaml.YAMLError) as exc:
        raise RegulatoryWorkerConfigError("cannot read Drugs@FDA source registry") from exc
    required = {
        "source_id": "drugs_at_fda",
        "rights_state": "review_required_before_b4",
        "production_ingest_allowed": False,
        "public_projection": "blocked_until_review",
    }
    if any(source.get(key) != value for key, value in required.items()):
        raise RegulatoryWorkerConfigError("Drugs@FDA registry is not in the reviewed dark state")
    return bool(source["production_ingest_allowed"])


def load_environment(environ: Mapping[str, str] | None = None) -> RegulatoryWorkerPlan:
    values = os.environ if environ is None else environ
    repository_root = Path(__file__).resolve().parents[1]
    registry = Path(values.get("BIOCATALYST_SOURCE_REGISTRY", repository_root / "config/biocatalyst_sources.yml"))
    state_root = Path(values.get("BIOCATALYST_REGULATORY_STATE_ROOT", "/var/lib/macro-biocatalyst-regulatory/state"))
    enabled = _enabled(values.get("BIOCATALYST_REGULATORY_ENABLED"))
    allowed = _registry_allows_production(registry)
    if enabled and not allowed:
        raise RegulatoryWorkerConfigError("Drugs@FDA production ingestion is blocked by source registry")
    return RegulatoryWorkerPlan(enabled=enabled, state_root=state_root, source_registry=registry)


def main() -> int:
    plan = load_environment()
    if not plan.enabled:
        return 0
    # No true branch exists until an explicit source-rights advancement ships.
    raise RegulatoryWorkerConfigError("no B4A production collection path is installed")


if __name__ == "__main__":
    raise SystemExit(main())
