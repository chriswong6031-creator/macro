"""Fail closed when the committed Government Revenue award-event bundle drifts.

This validator is kept outside the workflow YAML because GitHub rejects a
single ``run:`` scalar near 21,000 characters.  The serialized publish lane
calls it before staging or rebuilding any public Government Revenue artifact.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


def _instant(state: dict, name: str) -> datetime:
    value = state.get(name)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"award-event activation state lacks {name}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit(f"award-event activation state has invalid {name}") from None
    if parsed.tzinfo is None:
        raise SystemExit(f"award-event activation state has timezone-free {name}")
    return parsed


def validate_bundle(state_path: Path, snapshots_path: Path, actions_path: Path) -> None:
    """Validate activation, scope, manifest identity, clocks, and ledger binding."""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit("award-event activation state is unreadable") from exc
    if not isinstance(state, dict):
        raise SystemExit("award-event activation state is not an object")
    if state.get("schema_version") != "government_revenue.award_event_projection_state.v1":
        raise SystemExit("award-event activation state schema is not recognized")
    activation = state.get("activation_state")
    if activation not in {"baseline", "live"}:
        raise SystemExit("award-event activation state is invalid")
    coverage_scope = state.get("coverage_scope")
    if not isinstance(coverage_scope, str) or not coverage_scope.strip():
        raise SystemExit("award-event activation state lacks coverage scope")

    # Bind activation to the exact bounded collection contract, not merely to a
    # non-empty set of files. A query/cap/entity change cannot inherit the old
    # baseline identity or silently replace the last-good public generation.
    manifest = state.get("coverage_manifest")
    manifest_id = state.get("coverage_manifest_id")
    if not isinstance(manifest, dict):
        raise SystemExit("award-event activation state lacks coverage manifest")
    if manifest.get("schema_version") != "government_revenue.award_event_coverage_manifest.v1":
        raise SystemExit("award-event coverage manifest schema is not recognized")
    if manifest.get("coverage_scope") != coverage_scope:
        raise SystemExit("award-event coverage manifest scope does not match activation state")
    if not isinstance(manifest.get("entities"), list) or not manifest["entities"]:
        raise SystemExit("award-event coverage manifest lacks configured entities")
    discovery = manifest.get("award_discovery")
    if not isinstance(discovery, dict) or any(
        not isinstance(discovery.get(field), int) or isinstance(discovery.get(field), bool)
        for field in ("page_size", "max_pages")
    ):
        raise SystemExit("award-event coverage manifest lacks bounded discovery limits")
    canonical_manifest = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    expected_manifest_id = "award-coverage-" + hashlib.sha256(canonical_manifest).hexdigest()
    if not isinstance(manifest_id, str) or manifest_id != expected_manifest_id:
        raise SystemExit("award-event coverage manifest identity does not bind its contents")

    for field in (
        "last_run_was_full_receipt_bound_baseline",
        "bounded_sample_complete",
        "source_exhausted",
        "truncated_by_safety_cap",
        "coverage_manifest_changed_this_run",
    ):
        if not isinstance(state.get(field), bool):
            raise SystemExit(f"award-event activation state lacks boolean {field}")
    if state["source_exhausted"] and state["truncated_by_safety_cap"]:
        raise SystemExit("award-event state cannot be source-exhausted and safety-cap-truncated")

    observed_at = _instant(state, "last_observed_at")
    if activation == "live":
        if _instant(state, "baseline_completed_at") > observed_at:
            raise SystemExit("award-event baseline completion is later than its observation")
        if (
            state["bounded_sample_complete"] is not True
            or state.get("last_run_was_full_receipt_bound_baseline") is not True
        ):
            raise SystemExit("live award-event state lacks a completed bounded receipt-bound baseline")

    # Recompute the collector-owned semantic binding. File presence cannot prove
    # the two append-only ledgers and activation state belong to one generation.
    try:
        import pandas as pd

        from collectors.usaspending_awards import award_event_projection_generation_matches

        snapshots = pd.read_parquet(snapshots_path)
        actions = pd.read_parquet(actions_path)
        if not award_event_projection_generation_matches(state, snapshots, actions):
            raise SystemExit("award-event source ledgers do not match activation generation")
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit("award-event source generation could not be verified") from exc


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        raise SystemExit(
            "usage: validate_government_revenue_award_event_bundle.py "
            "STATE SNAPSHOTS ACTIONS"
        )
    validate_bundle(*(Path(value) for value in args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
