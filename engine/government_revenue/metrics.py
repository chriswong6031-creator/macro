"""Deterministic Government Revenue Foresight context payload.

This module intentionally has no predictive or portfolio authority.  It turns official
USAspending observations into auditable company context: lag-aware obligation velocity,
contract funding/backlog arithmetic when ceiling fields exist, modification activity,
concentration, and date-rule recompete candidates.  The output is shaped as one member of
the reusable Vertical Intelligence Workbench family.

Point-in-time contract
----------------------
``effective_at`` is when the government record says an event occurred. ``known_at`` is
when this repository first observed it.  Optional action/snapshot ledgers are filtered on
both clocks for historical ``as_of`` requests.  The legacy monthly obligations frame has
only a collection-level ``known_at`` in ``data/usaspending/_meta.json``; the payload says
so explicitly and never claims that frame is historically replayable before that stamp.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from engine.government_revenue.award_events import build_award_change_events
from engine.government_revenue.entity_resolution import (
    attach_recipient_resolutions,
    build_recipient_resolution_coverage,
    load_recipient_entity_graph,
)
from engine.government_revenue.opportunities import SOURCE_URL as SAM_OPPORTUNITIES_URL
from engine.government_revenue.opportunities import build_opportunity_intelligence
from engine.government_revenue.workspace import build_procurement_workspace

SCHEMA_VERSION = "company_government_revenue.v1"
CONTEXT_CONTRACT = "vertical_intelligence_context.v1"
CATALYST_CONTRACT = "vertical_catalyst_fact.v1"
PROVENANCE_CONTRACT = "vertical_provenance.v1"
REPORTING_LAG_MONTHS = 3
AGGREGATE_FRESHNESS_SLA_DAYS = 35
DETAIL_FRESHNESS_SLA_DAYS = 4
AWARD_EVENT_FRESHNESS_SLA_DAYS = 4
MONTHLY_HISTORY_LIMIT = 24
AWARD_LIMIT = 12
ACTION_LIMIT = 20

# The public award-change lane has a deliberately separate, forward-only
# evidence spine.  Do not substitute the legacy mutable awards/actions tables
# below when any of these artifacts are absent: those tables remain useful for
# descriptive company context, but cannot safely reconstruct event history.
AWARD_EVENT_SNAPSHOTS_FILENAME = "award_event_snapshots.parquet"
AWARD_ACTION_VERSIONS_FILENAME = "award_action_versions.parquet"
AWARD_EVENT_PROJECTION_STATE_FILENAME = "award_event_projection_state.json"
COLLECTION_RECEIPTS_FILENAME = "collection_receipts.jsonl"
RECIPIENT_ENTITY_GRAPH_FILENAME = "recipient_entity_graph.json"
RECIPIENT_RESOLUTION_COVERAGE_FILENAME = "recipient_resolution_coverage.json"
AWARD_EVENT_PROJECTION_STATE_SCHEMA = "government_revenue.award_event_projection_state.v1"
AWARD_EVENT_COVERAGE_MANIFEST_PREFIX = "award-coverage-"
AWARD_EVENT_FORWARD_SCOPE = (
    "receipt-bound forward-only USAspending award-event ledgers; legacy mutable "
    "award/action tables and discovery-query tickers are never event sources or issuer proof"
)
SPENDING_OVER_TIME_URL = "https://api.usaspending.gov/api/v2/search/spending_over_time/"
SPENDING_BY_AWARD_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
AWARD_DETAIL_URL = "https://api.usaspending.gov/api/v2/awards/{award_id}/"
TRANSACTIONS_URL = "https://api.usaspending.gov/api/v2/transactions/"

_AUTHORITY = {
    "tier": "display",
    "context_only": True,
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_add_candidates": False,
    "can_escalate": False,
}


def _root(root: Path | None) -> Path:
    return Path(root).resolve() if root is not None else Path.cwd().resolve()


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _date_iso(value: Any) -> str | None:
    ts = _timestamp(value)
    return ts.date().isoformat() if ts is not None else None


def _instant_iso(value: Any) -> str | None:
    ts = _timestamp(value)
    return ts.isoformat() if ts is not None else None


def _analysis_clock(as_of: str | None) -> tuple[pd.Timestamp, pd.Timestamp]:
    base = _timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC")
    if base is None:
        raise ValueError(f"invalid as_of: {as_of!r}")
    day = base.normalize()
    # An as-of date means information observed through that UTC day.
    return day, day + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)


def _number(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _first_number(row: pd.Series | dict, names: Iterable[str]) -> float | None:
    for name in names:
        if name in row:
            value = _number(row[name])
            if value is not None:
                return value
    return None


def _first_text(row: pd.Series | dict, names: Iterable[str]) -> str | None:
    for name in names:
        if name not in row:
            continue
        value = row[name]
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "nat"}:
            return text
    return None


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return default


def _read_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:  # noqa: BLE001 - a malformed optional rail degrades explicitly
        return pd.DataFrame()


def _read_required_frame(path: Path) -> tuple[pd.DataFrame, str]:
    """Read a dedicated event artifact while preserving absence vs. corruption.

    The normal context rails deliberately degrade to empty data frames.  The
    event projector instead needs a hard boundary: an unreadable forward ledger
    is not equivalent to a verified empty ledger.
    """

    if not path.exists():
        return pd.DataFrame(), "absent"
    try:
        return pd.read_parquet(path), "ready"
    except Exception:  # noqa: BLE001 - public event projection must fail closed
        return pd.DataFrame(), "unreadable"


def _read_required_json(path: Path) -> tuple[Any, str]:
    """Read an immutable-control artifact without silently accepting corruption."""

    if not path.exists():
        return None, "absent"
    try:
        return json.loads(path.read_text(encoding="utf-8")), "ready"
    except (OSError, ValueError, TypeError):
        return None, "unreadable"


def _read_receipt_ledger(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Read the canonical JSONL receipt ledger atomically or reject the whole rail."""

    if not path.exists():
        return [], "absent"
    try:
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                return [], "invalid"
            rows.append(row)
        return rows, "ready"
    except (OSError, ValueError, TypeError):
        return [], "unreadable"


def _strict_bool(value: Any) -> bool | None:
    """Accept only an actual JSON boolean at a governance boundary."""

    return value if isinstance(value, bool) else None


def _coverage_manifest_id(manifest: dict[str, Any]) -> str | None:
    """Recompute the collector's stable coverage-manifest identity.

    This intentionally mirrors the collector's canonical JSON recipe rather
    than treating a manifest label as proof of the bounded collection contract.
    """

    try:
        canonical = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return AWARD_EVENT_COVERAGE_MANIFEST_PREFIX + hashlib.sha256(canonical).hexdigest()


def _award_event_sample_contract(
    event_spine: dict[str, Any],
    projection_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate the declared bounded-sample contract independently of corpus size.

    ``source_exhausted`` is a corpus-coverage fact, not a freshness condition:
    a fresh run may intentionally complete every request in its declared bounded
    manifest while leaving the much larger public source corpus unexhausted.
    A missing flag, failed bounded pass, or manifest mismatch remains
    fail-closed.  ``truncated_by_safety_cap`` is deliberately not an error by
    itself: when the declared manifest intentionally ends at that cap, it is
    explicit corpus-coverage metadata rather than a failed collection.
    """

    names = (
        "bounded_sample_complete",
        "source_exhausted",
        "truncated_by_safety_cap",
    )
    values = {name: _strict_bool(event_spine.get(name)) for name in names}
    manifest_id = event_spine.get("coverage_manifest_id")
    manifest = event_spine.get("coverage_manifest")
    if (
        any(value is None for value in values.values())
        or not isinstance(manifest_id, str)
        or not manifest_id
        or not isinstance(manifest, dict)
        or not manifest
    ):
        return {
            "status": "partial",
            "reason": "ingest award-event spine lacks a complete bounded-sample coverage contract",
            **values,
            "coverage_manifest_id": manifest_id if isinstance(manifest_id, str) else None,
            "coverage_manifest": manifest if isinstance(manifest, dict) else None,
        }
    if _coverage_manifest_id(manifest) != manifest_id:
        return {
            "status": "failed",
            "reason": "ingest award-event coverage manifest does not match its content identity",
            **values,
            "coverage_manifest_id": manifest_id,
            "coverage_manifest": manifest,
        }
    if isinstance(projection_state, dict):
        state_values = {name: _strict_bool(projection_state.get(name)) for name in names}
        state_manifest_id = projection_state.get("coverage_manifest_id")
        state_manifest = projection_state.get("coverage_manifest")
        if (
            any(value is None for value in state_values.values())
            or state_manifest_id != manifest_id
            or state_manifest != manifest
            or state_values != values
        ):
            return {
                "status": "failed",
                "reason": "ingest award-event bounded-sample contract does not match projection state",
                **values,
                "coverage_manifest_id": manifest_id,
                "coverage_manifest": manifest,
            }
    if values["bounded_sample_complete"] is not True:
        reason = "declared bounded award-event sample did not complete"
        status = "partial"
    else:
        # Neither ``source_exhausted`` nor ``truncated_by_safety_cap`` changes
        # the result here.  The former says whether the source corpus ended;
        # the latter says the declared sample stopped at its published cap.
        # Both remain explicit coverage metadata for operators and downstream
        # consumers, while ``bounded_sample_complete`` is the collection gate.
        reason = (
            "declared bounded award-event sample completed at its published cap; "
            "source coverage remains explicit"
            if values["truncated_by_safety_cap"]
            else "declared bounded award-event sample completed and manifest binding verified"
        )
        status = "ok"
    return {
        "status": status,
        "reason": reason,
        **values,
        "coverage_manifest_id": manifest_id,
        "coverage_manifest": manifest,
    }


def _award_event_ingest_health(
    ingest_status: Any,
    *,
    knowledge_cutoff: pd.Timestamp,
    projection_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe collector health without letting a status file create events.

    The immutable state + ledger-generation binding is the event publication
    gate.  This secondary check makes freshness honest about the collector run
    that produced it, while preserving a verified last-good event ledger when a
    later status heartbeat is unavailable.
    """

    if not isinstance(ingest_status, dict):
        return {
            "status": "unverified",
            "reason": "ingest status was not supplied",
            "observed_at": None,
            "visible_at_as_of": False,
        }
    observed_at = _timestamp(ingest_status.get("observed_at"))
    if observed_at is None:
        return {
            "status": "unverified",
            "reason": "ingest status lacks an observation clock",
            "observed_at": None,
            "visible_at_as_of": False,
        }
    if observed_at > knowledge_cutoff:
        return {
            "status": "future_at_asof",
            "reason": "ingest status was not yet known at this as-of cutoff",
            "observed_at": None,
            "visible_at_as_of": False,
        }
    event_spine = ingest_status.get("award_event_spine")
    if not isinstance(event_spine, dict):
        return {
            "status": "unverified",
            "reason": "ingest status does not describe the award-event spine",
            "observed_at": _instant_iso(observed_at),
            "visible_at_as_of": True,
        }
    if event_spine.get("schema_version") != AWARD_EVENT_PROJECTION_STATE_SCHEMA:
        return {
            "status": "failed",
            "reason": "ingest award-event spine schema is not recognized",
            "observed_at": _instant_iso(observed_at),
            "visible_at_as_of": True,
        }
    if isinstance(projection_state, dict):
        expected_activation = projection_state.get("activation_state")
        expected_observed = _instant_iso(projection_state.get("last_observed_at"))
        actual_observed = _instant_iso(event_spine.get("last_observed_at"))
        if (
            event_spine.get("activation_state") != expected_activation
            or not expected_observed
            or actual_observed != expected_observed
        ):
            return {
                "status": "failed",
                "reason": "ingest award-event spine does not match projection state",
                "observed_at": _instant_iso(observed_at),
                "visible_at_as_of": True,
            }
    sample_contract = _award_event_sample_contract(event_spine, projection_state)
    contract_status = str(sample_contract.get("status") or "partial")
    if contract_status != "ok":
        return {
            "status": contract_status,
            "reason": sample_contract.get("reason") or "award-event bounded-sample contract is not verified",
            "observed_at": _instant_iso(observed_at),
            "visible_at_as_of": True,
            **{
                key: sample_contract.get(key)
                for key in (
                    "bounded_sample_complete",
                    "source_exhausted",
                    "truncated_by_safety_cap",
                    "coverage_manifest_id",
                    "coverage_manifest",
                )
            },
        }
    run_state = str(
        ingest_status.get("run_state") or ingest_status.get("status") or ""
    ).strip().lower()
    # The top-level collector run may be ``partial`` solely because the public
    # corpus was intentionally not exhausted.  That is a coverage limitation,
    # not a failure of the declared receipt-bound bounded sample.  Actual
    # failure/staleness still wins, and an unknown heartbeat remains partial.
    if run_state in {"failed", "stale"}:
        status = run_state
    elif run_state == "ok":
        status = "ok"
    elif run_state == "partial":
        status = "ok"
    else:
        status = "partial"
    return {
        "status": status,
        "reason": (
            "declared bounded award-event sample is complete; source exhaustion remains coverage metadata"
            if status == "ok"
            else "collector run failed, aged, or did not provide a usable health state"
        ),
        "observed_at": _instant_iso(observed_at),
        "visible_at_as_of": True,
        "collector_run_status": run_state or None,
        "contract_mode": sample_contract.get("contract_mode") or "manifest",
        **{
            key: sample_contract.get(key)
            for key in (
                "bounded_sample_complete",
                "source_exhausted",
                "truncated_by_safety_cap",
                "coverage_manifest_id",
                "coverage_manifest",
            )
        },
    }


_FORWARD_SNAPSHOT_REQUIRED_COLUMNS = {
    "generated_unique_award_id",
    "award_key",
    "known_at",
    "effective_at",
    "source_field_presence",
    "event_state_sha256",
    "source_receipt_id",
    "source_response_sha256",
    "source_url",
    "receipt_verified",
    "event_eligible",
}
_FORWARD_ACTION_REQUIRED_COLUMNS = {
    "generated_unique_award_id",
    "award_key",
    "action_id",
    "known_at",
    "effective_at",
    "source_field_presence",
    "event_state_sha256",
    "source_receipt_id",
    "source_response_sha256",
    "source_url",
    "receipt_verified",
    "event_eligible",
}


def _forward_receipt_ids(frame: pd.DataFrame) -> set[str]:
    """Return only explicit receipt IDs claimed by a visible forward ledger."""

    if frame.empty or "source_receipt_id" not in frame.columns:
        return set()
    result: set[str] = set()
    for value in frame["source_receipt_id"].tolist():
        rendered = _first_text({"value": value}, ("value",))
        if rendered:
            result.add(rendered)
    return result


def _award_event_projection(
    repo: Path,
    *,
    companies: list[dict[str, Any]],
    as_of_day: pd.Timestamp,
    knowledge_cutoff: pd.Timestamp,
    ingest_status: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Project only the separate receipt-bound, forward award-event spine.

    This never adapts mutable legacy context rows.  A missing/invalid state,
    ledger, or canonical receipt ledger yields an explicit zero-event envelope
    rather than borrowing a discovery-query ticker. There is no shape-based
    legacy bypass: a migration would require its own versioned receipt.
    """

    data_dir = repo / "data" / "government_revenue"
    state_value, state_artifact = _read_required_json(
        data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME
    )
    ingest_health = _award_event_ingest_health(
        ingest_status,
        knowledge_cutoff=knowledge_cutoff,
    )
    loaded_recipient_graph: dict[str, Any] | None = None
    recipient_graph_artifact: str | None = None

    def resolution_context(
        snapshot_frame: pd.DataFrame,
        action_frame: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
        """Attach reviewed exact-ID annotations and report isolated coverage.

        This closure is called only after the source-lane decision has been
        reached. For a live generation that means state, two-ledger generation,
        receipt, and point-in-time verification have already passed. Historical
        checkouts without the receipt-bound triad receive an honest zero-row
        report when a curated graph exists, without synthesizing source rows.
        The graph file is read and admitted exactly once per payload build.
        """

        nonlocal loaded_recipient_graph, recipient_graph_artifact
        if loaded_recipient_graph is None:
            graph_value, recipient_graph_artifact = _read_required_json(
                data_dir / RECIPIENT_ENTITY_GRAPH_FILENAME
            )
            graph_input: Any
            if recipient_graph_artifact == "ready" and isinstance(graph_value, dict):
                graph_input = graph_value
            elif recipient_graph_artifact == "absent":
                graph_input = None
            else:
                # Preserve unreadable/invalid as distinct from an absent
                # curated graph at the strict loader boundary.
                graph_input = []
            loaded_recipient_graph = load_recipient_entity_graph(
                graph_input,
                as_of=knowledge_cutoff.to_pydatetime(),
            )

        # The strict loader already admitted this local normalized view. It has
        # no public graph contract marker, so the resolver consumes it without
        # re-running graph admission per row. No caller-supplied normalized
        # object crosses this boundary: it was created above from the one file
        # read in this closure. Absent/invalid results retain their fail-closed
        # wrapper and contain no resolution graph to traverse.
        annotation_graph: dict[str, Any] = loaded_recipient_graph
        if (
            loaded_recipient_graph.get("status") == "ready"
            and isinstance(loaded_recipient_graph.get("graph"), dict)
        ):
            annotation_graph = loaded_recipient_graph["graph"]

        snapshot_rows = snapshot_frame.to_dict(orient="records")
        action_rows = action_frame.to_dict(orient="records")
        attached_snapshots = attach_recipient_resolutions(
            snapshot_rows,
            annotation_graph,
            as_of=knowledge_cutoff.to_pydatetime(),
        )
        attached_actions = attach_recipient_resolutions(
            action_rows,
            annotation_graph,
            as_of=knowledge_cutoff.to_pydatetime(),
        )
        snapshot_columns = [*snapshot_frame.columns]
        action_columns = [*action_frame.columns]
        if "recipient_resolution" not in snapshot_columns:
            snapshot_columns.append("recipient_resolution")
        if "recipient_resolution" not in action_columns:
            action_columns.append("recipient_resolution")
        annotated_snapshot_frame = pd.DataFrame(
            attached_snapshots,
            columns=snapshot_columns,
        )
        annotated_action_frame = pd.DataFrame(
            attached_actions,
            columns=action_columns,
        )
        # The receipt-bound projection manifest proves a bounded generation,
        # not one synthetic query per ledger. Until the collector publishes
        # exact query accounting for these two independent returned scopes,
        # leave collection counts explicitly unknown instead of inventing 1/1.
        collection = {
            "queries_requested": 0,
            "queries_complete": 0,
            "queries_partial": 0,
            "queries_failed": 0,
        }
        coverage = build_recipient_resolution_coverage(
            attached_snapshots,
            attached_actions,
            loaded_recipient_graph,
            as_of=knowledge_cutoff.to_pydatetime(),
            snapshot_collection=collection,
            action_collection=collection,
            snapshot_amount_field="total_obligation",
            action_amount_field="federal_action_obligation",
        )
        return annotated_snapshot_frame, annotated_action_frame, coverage

    def envelope(
        *,
        status: str,
        availability: str,
        reason: str,
        activation_state: str | None = None,
        observed_at: pd.Timestamp | None = None,
        visible_at_as_of: bool = False,
        coverage_scope: str | None = None,
        snapshots_visible: int = 0,
        actions_visible: int = 0,
        receipt_claims_visible: int = 0,
        receipts_available: int = 0,
        events_visible: int = 0,
        artifacts: dict[str, str] | None = None,
        recipient_resolution_coverage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if recipient_resolution_coverage is None:
            _, _, recipient_resolution_coverage = resolution_context(
                pd.DataFrame(),
                pd.DataFrame(),
            )
        resolved_artifacts = dict(artifacts or {"projection_state": state_artifact})
        resolved_artifacts["recipient_entity_graph"] = str(
            recipient_graph_artifact or "unverified"
        )
        result = {
            "status": status,
            "availability": availability,
            "reason": reason,
            "activation_state": activation_state,
            "known_at": _instant_iso(observed_at) if visible_at_as_of else None,
            "observed_at": _instant_iso(observed_at) if visible_at_as_of else None,
            "visible_at_as_of": bool(visible_at_as_of),
            "freshness_sla_days": AWARD_EVENT_FRESHNESS_SLA_DAYS,
            "coverage_scope": coverage_scope or AWARD_EVENT_FORWARD_SCOPE,
            "scope": AWARD_EVENT_FORWARD_SCOPE,
            "snapshot_versions_visible": int(snapshots_visible),
            "action_versions_visible": int(actions_visible),
            "receipt_claims_visible": int(receipt_claims_visible),
            "collection_receipts_available": int(receipts_available),
            "events_visible": int(events_visible),
            "artifacts": resolved_artifacts,
            "ingest": ingest_health,
            "recipient_resolution_coverage": recipient_resolution_coverage,
            # This separates a successfully observed declared sample from an
            # exhausted USAspending corpus.  Consumers may suppress the event
            # rail when the bounded sample is incomplete, but must not read
            # ``source_exhausted: false`` as a stale collection clock.
            "limitations": [
                "Only receipt-bound forward ledgers may emit award-change events.",
                "Legacy award/action context and discovery-query tickers are excluded from this lane.",
                "Listed-company impacts require a separately asserted exact-ID resolution with evidence.",
            ],
        }
        result.update({
            "bounded_sample_complete": ingest_health.get("bounded_sample_complete"),
            "source_exhausted": ingest_health.get("source_exhausted"),
            "truncated_by_safety_cap": ingest_health.get("truncated_by_safety_cap"),
            "coverage_manifest": ingest_health.get("coverage_manifest"),
            "coverage_manifest_id": ingest_health.get("coverage_manifest_id"),
        })
        return result

    if state_artifact != "ready" or not isinstance(state_value, dict):
        return [], envelope(
            status="unavailable",
            availability=f"projection_state_{state_artifact}",
            reason="award-event projection state is absent or unreadable",
        )
    if state_value.get("schema_version") != AWARD_EVENT_PROJECTION_STATE_SCHEMA:
        return [], envelope(
            status="unavailable",
            availability="projection_state_invalid",
            reason="award-event projection state schema is not recognized",
        )
    activation_state = state_value.get("activation_state")
    if activation_state not in {"baseline", "live"}:
        return [], envelope(
            status="unavailable",
            availability="projection_state_invalid",
            reason="award-event projection state has no valid activation state",
        )
    coverage_scope = _first_text(state_value, ("coverage_scope",))
    observed_at = _timestamp(state_value.get("last_observed_at"))
    if not coverage_scope or observed_at is None:
        return [], envelope(
            status="unavailable",
            availability="projection_state_unverified",
            reason="award-event projection state lacks an auditable coverage scope or observation clock",
            activation_state=activation_state,
        )
    ingest_health = _award_event_ingest_health(
        ingest_status,
        knowledge_cutoff=knowledge_cutoff,
        projection_state=state_value,
    )
    if observed_at > knowledge_cutoff:
        return [], envelope(
            status="partial",
            availability="future_at_asof",
            reason="award-event projection state was not yet known at this as-of cutoff",
            activation_state=activation_state,
            observed_at=observed_at,
            coverage_scope=coverage_scope,
        )

    if activation_state == "baseline":
        return [], envelope(
            status="partial",
            availability="warming",
            reason="receipt-bound baseline is still warming; forward award events are intentionally withheld",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
        )

    baseline_completed_at = _timestamp(state_value.get("baseline_completed_at"))
    if baseline_completed_at is None or baseline_completed_at > observed_at:
        return [], envelope(
            status="unavailable",
            availability="projection_state_unverified",
            reason="live award-event state lacks a completed receipt-bound baseline",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
        )

    snapshot_path = data_dir / AWARD_EVENT_SNAPSHOTS_FILENAME
    action_path = data_dir / AWARD_ACTION_VERSIONS_FILENAME
    receipt_path = data_dir / COLLECTION_RECEIPTS_FILENAME
    snapshots, snapshot_artifact = _read_required_frame(snapshot_path)
    actions, action_artifact = _read_required_frame(action_path)
    receipts, receipt_artifact = _read_receipt_ledger(receipt_path)
    artifact_states = {
        "projection_state": state_artifact,
        "award_event_snapshots": snapshot_artifact,
        "award_action_versions": action_artifact,
        "collection_receipts": receipt_artifact,
    }
    if snapshot_artifact != "ready" or action_artifact != "ready":
        unavailable = "award_event_snapshots" if snapshot_artifact != "ready" else "award_action_versions"
        return [], envelope(
            status="unavailable",
            availability=f"{unavailable}_{artifact_states[unavailable]}",
            reason="one or more dedicated forward event ledgers are absent or unreadable",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
            artifacts=artifact_states,
        )
    if receipt_artifact != "ready":
        return [], envelope(
            status="unavailable",
            availability=f"collection_receipts_{receipt_artifact}",
            reason="canonical collection receipt ledger is absent or unreadable",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
            artifacts=artifact_states,
        )
    if not _FORWARD_SNAPSHOT_REQUIRED_COLUMNS.issubset(snapshots.columns) or not _FORWARD_ACTION_REQUIRED_COLUMNS.issubset(actions.columns):
        return [], envelope(
            status="unavailable",
            availability="forward_ledger_invalid",
            reason="forward event ledger does not carry the required receipt-bound projection fields",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
            receipts_available=len(receipts),
            artifacts=artifact_states,
        )

    # A state marker alone is not enough: a process can fail between the two
    # atomic parquet replacements.  The collector owns the canonical semantic
    # digest recipe, so recompute it over the *full*, unfiltered pair before
    # any point-in-time projection.  This rejects a mixed generation rather
    # than allowing an old live state to bless whichever ledger happened to
    # survive the interrupted write.
    generation_fields = (
        "projection_generation_id",
        "award_event_snapshots_semantic_sha256",
        "award_event_snapshots_row_count",
        "award_action_versions_semantic_sha256",
        "award_action_versions_row_count",
        "projection_semantic_sha256",
    )
    if any(field not in state_value for field in generation_fields):
        artifact_states["projection_generation"] = "unverified"
        return [], envelope(
            status="partial",
            availability="projection_generation_unverified",
            reason="live award-event state lacks a complete two-ledger generation binding",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
            receipts_available=len(receipts),
            artifacts=artifact_states,
        )
    try:
        # Keep this import local: normal context payloads do not need the
        # collector module, while forward event readers must use its exact
        # canonicalization formula rather than a subtly divergent copy.
        from collectors.usaspending_awards import award_event_projection_generation_matches

        generation_matches = award_event_projection_generation_matches(
            state_value,
            snapshots,
            actions,
        )
    except Exception:  # noqa: BLE001 - a failed integrity verifier is not a pass
        artifact_states["projection_generation"] = "verification_failed"
        return [], envelope(
            status="failed",
            availability="projection_generation_verification_failed",
            reason="award-event generation binding could not be verified",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
            receipts_available=len(receipts),
            artifacts=artifact_states,
        )
    if not generation_matches:
        artifact_states["projection_generation"] = "mismatch"
        return [], envelope(
            status="failed",
            availability="projection_generation_mismatch",
            reason="forward event ledgers do not match the live projection generation",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
            receipts_available=len(receipts),
            artifacts=artifact_states,
        )
    artifact_states["projection_generation"] = "verified"

    snapshots_visible = _filter_point_in_time(snapshots, knowledge_cutoff, knowledge_cutoff)
    actions_visible = _filter_point_in_time(actions, knowledge_cutoff, knowledge_cutoff)
    receipt_claims = _forward_receipt_ids(snapshots_visible) | _forward_receipt_ids(actions_visible)
    ledger_receipt_ids = {
        receipt_id
        for row in receipts
        for receipt_id in [_first_text(row, ("receipt_id", "source_receipt_id"))]
        if receipt_id
    }
    if receipt_claims - ledger_receipt_ids:
        return [], envelope(
            status="unavailable",
            availability="receipt_binding_incomplete",
            reason="a visible forward event row lacks its canonical collection receipt",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
            snapshots_visible=len(snapshots_visible),
            actions_visible=len(actions_visible),
            receipt_claims_visible=len(receipt_claims),
            receipts_available=len(receipts),
            artifacts=artifact_states,
        )

    snapshots_annotated, actions_annotated, resolution_coverage = resolution_context(
        snapshots_visible,
        actions_visible,
    )
    artifact_states["recipient_entity_graph"] = str(
        recipient_graph_artifact or "unverified"
    )

    try:
        events = build_award_change_events(
            snapshots_annotated,
            actions_annotated,
            companies=companies,
            source_receipts=receipts,
            as_of=as_of_day.date().isoformat(),
            known_at=knowledge_cutoff,
            effective_as_of=knowledge_cutoff,
        )
    except Exception:  # noqa: BLE001 - public award lane has no best-effort fallback
        return [], envelope(
            status="unavailable",
            availability="projection_rejected_inputs",
            reason="forward award-event inputs could not pass the strict projector",
            activation_state=activation_state,
            observed_at=observed_at,
            visible_at_as_of=True,
            coverage_scope=coverage_scope,
            snapshots_visible=len(snapshots_visible),
            actions_visible=len(actions_visible),
            receipt_claims_visible=len(receipt_claims),
            receipts_available=len(receipts),
            artifacts=artifact_states,
            recipient_resolution_coverage=resolution_coverage,
        )

    ingest_state = str(ingest_health.get("status") or "unverified")
    status = "ok" if ingest_state == "ok" else (
        "failed" if ingest_state == "failed" else "stale" if ingest_state == "stale" else "partial"
    )
    availability = "available" if events else "available_empty"
    if status != "ok":
        availability = f"{availability}_ingest_{ingest_state}"
    return events, envelope(
        status=status,
        availability=availability,
        reason=(
            "receipt-bound forward award-event projection completed"
            if status == "ok"
            else "receipt-bound forward projection completed, but collector health is not fully verified"
        ),
        activation_state=activation_state,
        observed_at=observed_at,
        visible_at_as_of=True,
        coverage_scope=coverage_scope,
        snapshots_visible=len(snapshots_visible),
        actions_visible=len(actions_visible),
        receipt_claims_visible=len(receipt_claims),
        receipts_available=len(receipts),
        events_visible=len(events),
        artifacts=artifact_states,
        recipient_resolution_coverage=resolution_coverage,
    )


def _knowledge_column(frame: pd.DataFrame) -> str | None:
    for col in ("known_at", "first_seen_at", "_first_seen"):
        if col in frame.columns:
            return col
    return None


def _filter_point_in_time(
    frame: pd.DataFrame,
    knowledge_cutoff: pd.Timestamp,
    effective_cutoff: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Keep only facts observable and effective by the requested cutoff.

    Detail/action ledgers are optional, but a row without an immutable
    visibility clock is not usable in a historical reconstruction.  Returning
    it merely because a legacy file omitted the column would turn the latest
    file state into faux historical knowledge.  The same rule applies to an
    explicit effective cutoff: a mutable detail fact without an effective
    event/action clock cannot be placed honestly on an as-of timeline.
    """
    if frame.empty:
        return frame.copy()
    out = frame.copy()
    known_col = _knowledge_column(out)
    if not known_col:
        return out.iloc[0:0].copy()
    known = pd.to_datetime(out[known_col], utc=True, errors="coerce")
    out = out[known.notna() & (known <= knowledge_cutoff)]
    if effective_cutoff is not None:
        effective: pd.Series | None = None
        for col in ("effective_at", "action_date"):
            if col not in out.columns:
                continue
            parsed = pd.to_datetime(out[col], utc=True, errors="coerce")
            effective = parsed if effective is None else effective.fillna(parsed)
        if effective is None:
            return out.iloc[0:0].copy()
        out = out[effective.notna() & (effective <= effective_cutoff)]
    return out.copy()


def _load_entities(repo: Path) -> dict[str, dict]:
    payload = _read_json(repo / "data" / "government_revenue" / "entities.json", {})
    entities = payload.get("entities", {}) if isinstance(payload, dict) else {}
    return entities if isinstance(entities, dict) else {}


def _load_monthly(repo: Path) -> pd.DataFrame:
    frame = _read_frame(repo / "data" / "usaspending" / "obligations.parquet")
    if frame.empty:
        return frame
    out = frame.copy()
    out.index = pd.to_datetime(out.index, utc=True, errors="coerce")
    out = out[~out.index.isna()].sort_index()
    return out.apply(pd.to_numeric, errors="coerce")


def _with_award_identity(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach the stable generated-award-first identity used by PIT ledgers."""
    out = frame.copy()
    generated = out.get("generated_award_id", pd.Series(index=out.index, dtype=object))
    piid = out.get("award_id", pd.Series(index=out.index, dtype=object))
    canonical = generated.where(generated.notna() & generated.astype(str).str.strip().ne(""))
    canonical = canonical.fillna("piid:" + piid.fillna("").astype(str))
    out["_award_identity"] = canonical.astype(str)
    return out


def _exclude_snapshot_backed_awards(
    awards: pd.DataFrame,
    snapshots: pd.DataFrame,
) -> pd.DataFrame:
    """Do not fall back to mutable award rows where a snapshot ledger exists.

    A snapshot observed after the replay/effective cutoff is evidence that the
    current award row may contain future fields.  The absence of a *visible*
    snapshot is not permission to use that mutable row; omit that identity
    until a valid snapshot exists.  Rows with no snapshot ledger remain eligible
    for the normal dual-clock fallback.
    """
    if (
        awards.empty
        or snapshots.empty
        or "ticker" not in awards.columns
        or "ticker" not in snapshots.columns
    ):
        return awards.copy()
    award_keys = _with_award_identity(awards)
    snapshot_keys = _with_award_identity(snapshots)
    backed = set(zip(
        snapshot_keys["ticker"].fillna("").astype(str),
        snapshot_keys["_award_identity"].astype(str),
    ))
    visible = [
        (ticker, identity) not in backed
        for ticker, identity in zip(
            award_keys["ticker"].fillna("").astype(str),
            award_keys["_award_identity"].astype(str),
        )
    ]
    return award_keys.loc[visible].drop(columns=["_award_identity"])


def _overlay_snapshots(
    awards: pd.DataFrame,
    snapshots: pd.DataFrame,
    knowledge_cutoff: pd.Timestamp,
    effective_cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """Reconstruct mutable award state wholly from the latest visible snapshot.

    Starting from the latest mutable award row and overlaying only non-null
    snapshot values leaks fields learned later into historical replays.  Snapshot
    nulls are meaningful here: they mean the field had not yet been observed.
    Only explicit immutable identifiers are joined from the identity ledger.
    """
    if awards.empty or snapshots.empty:
        return awards.copy()
    snaps = _filter_point_in_time(snapshots, knowledge_cutoff, effective_cutoff)
    if snaps.empty or "ticker" not in snaps.columns:
        return awards.copy()

    identities = _with_award_identity(awards)
    snaps = _with_award_identity(snaps)
    order_col = _knowledge_column(snaps) or "snapshot_date"
    order = pd.to_datetime(snaps[order_col], utc=True, errors="coerce")
    snaps = snaps.assign(_snapshot_order=order).sort_values("_snapshot_order")
    latest = snaps.drop_duplicates(["ticker", "_award_identity"], keep="last")

    immutable = [
        column
        for column in ("ticker", "_award_identity", "generated_award_id", "first_seen_at", "award_page_url")
        if column in identities.columns
    ]
    stable = identities[immutable].drop_duplicates(["ticker", "_award_identity"], keep="first")
    snapshot_state = latest.drop(columns=["_snapshot_order"], errors="ignore")
    out = snapshot_state.merge(
        stable,
        on=["ticker", "_award_identity"],
        how="inner",
        suffixes=("", "_identity"),
    )
    for column in ("generated_award_id", "first_seen_at", "award_page_url"):
        identity_column = f"{column}_identity"
        if identity_column in out.columns:
            out[column] = out[identity_column]
            out = out.drop(columns=[identity_column])
    if "last_seen_at" not in out.columns and "known_at" in out.columns:
        out["last_seen_at"] = out["known_at"]
    return out.drop(columns=["_award_identity"], errors="ignore")


def _awards_point_in_time(
    awards: pd.DataFrame,
    snapshots: pd.DataFrame,
    knowledge_cutoff: pd.Timestamp,
    effective_cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """Resolve mutable awards through their daily first-observed snapshots.

    Once snapshots exist, award identity is admitted by ``first_seen_at`` and current
    fields come only from the latest snapshot visible at the cutoff. This avoids losing
    an old award merely because its latest-state row was refreshed after historical
    ``as_of``, while also avoiding leakage from that refreshed state.
    """
    if awards.empty:
        return awards.copy()
    visible_snapshots = _filter_point_in_time(
        snapshots,
        knowledge_cutoff,
        effective_cutoff,
    )
    if visible_snapshots.empty or not {"ticker", "award_id"}.issubset(visible_snapshots.columns):
        fallback = _filter_point_in_time(awards, knowledge_cutoff, effective_cutoff)
        return _exclude_snapshot_backed_awards(fallback, snapshots)
    if "first_seen_at" in awards.columns:
        first_seen = pd.to_datetime(awards["first_seen_at"], utc=True, errors="coerce")
        identities = awards[first_seen.notna() & (first_seen <= knowledge_cutoff)].copy()
    else:
        identities = _filter_point_in_time(awards, knowledge_cutoff, effective_cutoff)
    if identities.empty:
        return identities
    return _overlay_snapshots(
        identities,
        visible_snapshots,
        knowledge_cutoff,
        effective_cutoff,
    )


def _velocity(series: pd.Series, complete_month: pd.Timestamp) -> dict:
    if series is None or series.empty:
        return {
            "ttm_obligations": None,
            "prior_ttm_obligations": None,
            "award_velocity_yoy_pct": None,
            "velocity_basis": "insufficient monthly observations",
            "months_current": 0,
            "months_prior": 0,
        }
    clean = pd.to_numeric(series, errors="coerce")
    clean.index = pd.to_datetime(clean.index, utc=True, errors="coerce")
    clean = clean[~clean.index.isna()].sort_index()
    monthly_index = pd.date_range(end=complete_month, periods=24, freq="MS", tz="UTC")
    window = clean.reindex(monthly_index)
    current, prior = window.iloc[-12:], window.iloc[:12]
    n_current, n_prior = int(current.notna().sum()), int(prior.notna().sum())
    cur_sum = float(current.sum(min_count=1)) if n_current else None
    prev_sum = float(prior.sum(min_count=1)) if n_prior else None
    velocity = None
    if n_current == 12 and n_prior == 12 and prev_sum is not None and prev_sum > 0:
        velocity = 100.0 * (cur_sum - prev_sum) / abs(prev_sum)  # type: ignore[operator]
    return {
        "ttm_obligations": _number(cur_sum),
        "prior_ttm_obligations": _number(prev_sum),
        "award_velocity_yoy_pct": _number(velocity, 1),
        "velocity_basis": (
            "latest 12 complete months versus the same preceding 12 months; "
            f"latest {REPORTING_LAG_MONTHS} reporting months excluded"
        ),
        "months_current": n_current,
        "months_prior": n_prior,
    }


def _concentration(frame: pd.DataFrame, dimension_candidates: Iterable[str]) -> dict | None:
    if frame.empty:
        return None
    dimension = next((c for c in dimension_candidates if c in frame.columns), None)
    if dimension is None:
        return None
    values = frame[dimension].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
    weights = pd.Series(index=frame.index, dtype=float)
    for col in ("total_obligated", "award_amount", "current_award_amount"):
        if col in frame.columns:
            weights = pd.to_numeric(frame[col], errors="coerce").fillna(0.0).clip(lower=0.0)
            break
    total = float(weights.sum())
    if total <= 0:
        return None
    grouped = weights.groupby(values).sum().sort_values(ascending=False)
    shares = grouped / total
    return {
        "basis": dimension,
        "top_name": str(grouped.index[0]),
        "top_share_pct": _number(100.0 * shares.iloc[0], 1),
        "hhi": _number(float((shares**2).sum()), 4),
        "categories": int(len(grouped)),
        "covered_obligations": _number(total),
    }


def _active_awards(frame: pd.DataFrame, as_of_day: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if "end_date" not in frame.columns:
        return frame.copy()
    ends = pd.to_datetime(frame["end_date"], utc=True, errors="coerce")
    return frame[ends.isna() | (ends >= as_of_day)].copy()


def _backlog(frame: pd.DataFrame, as_of_day: pd.Timestamp) -> dict:
    active = _active_awards(frame, as_of_day)
    if active.empty:
        return {
            "funded_backlog": None,
            "total_backlog": None,
            "funded_capacity_observed": None,
            "potential_capacity_observed": None,
            "funding_pct": None,
            "backlog_basis": "no current award records",
            "backlog_scope": "bounded award-detail sample; not company-reported backlog",
            "backlog_is_partial": True,
            "backlog_is_lower_bound": True,
            "awards_visible": 0,
            "awards_with_current_value": 0,
            "awards_with_ceiling": 0,
            "backlog_sample_coverage_pct": None,
        }
    obligated = pd.to_numeric(active.get("total_obligated"), errors="coerce")
    if obligated is None:
        obligated = pd.Series(float("nan"), index=active.index)
    current = pd.to_numeric(active.get("current_award_amount"), errors="coerce")
    if current is None:
        current = pd.Series(float("nan"), index=active.index)
    potential = pd.to_numeric(active.get("potential_award_amount"), errors="coerce")
    if potential is None:
        potential = pd.Series(float("nan"), index=active.index)

    current_mask = obligated.notna() & current.notna()
    ceiling_mask = obligated.notna() & potential.notna()
    funded_backlog = (
        float((current[current_mask] - obligated[current_mask]).clip(lower=0).sum())
        if current_mask.any()
        else None
    )
    total_backlog = (
        float((potential[ceiling_mask] - obligated[ceiling_mask]).clip(lower=0).sum())
        if ceiling_mask.any()
        else None
    )
    current_total = float(current[current_mask].sum()) if current_mask.any() else 0.0
    funded_total = float(obligated[current_mask].sum()) if current_mask.any() else 0.0
    funding_pct = 100.0 * funded_total / current_total if current_total > 0 else None
    basis = (
        "observed funded capacity = current award amount - obligated; observed potential "
        "capacity = all-options amount - obligated; negative residuals floored at zero"
    )
    if not current_mask.any() and not ceiling_mask.any():
        basis = "USAspending award search lacks exercised/current and ceiling values; enrichment required"
    return {
        # Compatibility aliases remain for downstream readers. They are explicitly
        # qualified by scope/coverage and the user-facing product uses the names below.
        "funded_backlog": _number(funded_backlog),
        "total_backlog": _number(total_backlog),
        "funded_capacity_observed": _number(funded_backlog),
        "potential_capacity_observed": _number(total_backlog),
        "funding_pct": _number(funding_pct, 1),
        "backlog_basis": basis,
        "backlog_scope": (
            "bounded USAspending award-detail sample; observed nonnegative residuals only; "
            "not company-reported or GAAP backlog"
        ),
        "backlog_is_partial": True,
        "backlog_is_lower_bound": True,
        "awards_visible": int(len(active)),
        "awards_with_current_value": int(current_mask.sum()),
        "awards_with_ceiling": int(ceiling_mask.sum()),
        "backlog_sample_coverage_pct": _number(100.0 * current_mask.sum() / len(active), 1),
    }


def _modification_metrics(actions: pd.DataFrame, as_of_day: pd.Timestamp) -> dict:
    empty = {
        "net_award_action_flow_90d": None,
        "positive_award_action_flow_90d": None,
        "modification_impulse_90d": None,
        "modifications_net_90d": None,
        "positive_modifications_90d": None,
        "deobligations_90d": None,
        "award_action_flow_basis": "no action records",
        "modification_impulse_basis": "legacy compatibility alias; no action records",
    }
    if actions.empty or "action_date" not in actions.columns:
        return empty
    dates = pd.to_datetime(actions["action_date"], utc=True, errors="coerce")
    amounts = pd.to_numeric(actions.get("federal_action_obligation"), errors="coerce")
    if amounts is None:
        return empty
    recent = amounts[(dates >= as_of_day - pd.Timedelta(days=89)) & (dates <= as_of_day)]
    trailing = amounts[(dates >= as_of_day - pd.Timedelta(days=364)) & (dates <= as_of_day)]
    if recent.empty:
        return empty | {
            "net_award_action_flow_90d": 0.0,
            "positive_award_action_flow_90d": 0.0,
            "modifications_net_90d": 0.0,
            "positive_modifications_90d": 0.0,
            "deobligations_90d": 0.0,
            "award_action_flow_basis": "net 90-day transaction actions / positive trailing-365-day actions",
            "modification_impulse_basis": "legacy alias; includes initial, option, modification, and unclassified actions",
        }
    net = float(recent.fillna(0).sum())
    pos = float(recent[recent > 0].sum())
    deob = float(-recent[recent < 0].sum())
    denom = float(trailing[trailing > 0].sum())
    impulse = 100.0 * net / denom if denom > 0 else None
    return {
        "net_award_action_flow_90d": _number(net),
        "positive_award_action_flow_90d": _number(pos),
        "modification_impulse_90d": _number(impulse, 1),
        "modifications_net_90d": _number(net),
        "positive_modifications_90d": _number(pos),
        "deobligations_90d": _number(deob),
        "award_action_flow_basis": "net 90-day transaction actions / positive trailing-365-day actions",
        "modification_impulse_basis": "legacy alias; includes initial, option, modification, and unclassified actions",
    }


def _award_link(row: pd.Series | dict) -> str:
    direct = _first_text(row, ("award_page_url", "source_award_url"))
    if direct:
        return direct
    generated = _first_text(row, ("generated_award_id", "generated_internal_id"))
    if generated:
        return f"https://www.usaspending.gov/award/{generated}/"
    return SPENDING_BY_AWARD_URL


def _compact_awards(frame: pd.DataFrame, as_of_day: pd.Timestamp) -> list[dict]:
    if frame.empty:
        return []
    work = frame.copy()
    work["_sort_amount"] = pd.to_numeric(
        work.get("total_obligated", work.get("award_amount")), errors="coerce"
    ).fillna(0.0)
    work = work.sort_values(["_sort_amount"], ascending=False).head(AWARD_LIMIT)
    out: list[dict] = []
    for _, row in work.iterrows():
        end = _timestamp(_first_text(row, ("end_date", "period_of_performance_current_end_date")))
        out.append({
            "award_id": _first_text(row, ("award_id", "piid")),
            "generated_award_id": _first_text(row, ("generated_award_id", "generated_internal_id")),
            "recipient_name": _first_text(row, ("recipient_name",)),
            "description": _first_text(row, ("description",)),
            "start_date": _date_iso(_first_text(row, ("start_date",))),
            "end_date": _date_iso(end),
            "status": "active" if end is None or end >= as_of_day else "ended",
            "total_obligated": _first_number(row, ("total_obligated", "award_amount")),
            "current_award_amount": _first_number(row, ("current_award_amount",)),
            "potential_award_amount": _first_number(row, ("potential_award_amount",)),
            "awarding_agency": _first_text(row, ("awarding_agency",)),
            "awarding_sub_agency": _first_text(row, ("awarding_sub_agency",)),
            "program": _first_text(row, ("program", "major_program", "program_acronym", "psc")),
            "naics": _first_text(row, ("naics",)),
            "psc": _first_text(row, ("psc",)),
            "known_at": _instant_iso(_first_text(row, ("known_at", "first_seen_at", "_first_seen"))),
            "effective_at": _date_iso(_first_text(row, ("effective_at", "base_obligation_date", "start_date"))),
            "source_url": _award_link(row),
        })
    return out


def _compact_actions(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    work = frame.copy()
    if "action_date" in work.columns:
        work["_sort_date"] = pd.to_datetime(work["action_date"], utc=True, errors="coerce")
        work = work.sort_values("_sort_date", ascending=False)
    work = work.head(ACTION_LIMIT)
    out: list[dict] = []
    for _, row in work.iterrows():
        out.append({
            "action_id": _first_text(row, ("action_id", "id")),
            "award_id": _first_text(row, ("award_id",)),
            "action_date": _date_iso(_first_text(row, ("action_date", "effective_at"))),
            "modification_number": _first_text(row, ("modification_number",)),
            "action_type": _first_text(row, ("action_type",)),
            "action_type_description": _first_text(row, ("action_type_description",)),
            "federal_action_obligation": _first_number(row, ("federal_action_obligation",)),
            "description": _first_text(row, ("description",)),
            "known_at": _instant_iso(_first_text(row, ("known_at", "first_seen_at", "_first_seen"))),
            "effective_at": _date_iso(_first_text(row, ("effective_at", "action_date"))),
            "source_url": _first_text(row, ("source_url",)) or TRANSACTIONS_URL,
        })
    return out


def _recompetes(frame: pd.DataFrame, as_of_day: pd.Timestamp) -> list[dict]:
    if frame.empty or "end_date" not in frame.columns:
        return []
    work = frame.copy()
    work["_end"] = pd.to_datetime(work["end_date"], utc=True, errors="coerce")
    work["_days"] = (work["_end"] - as_of_day).dt.days
    work = work[(work["_days"] >= 30) & (work["_days"] <= 540)].sort_values("_days")
    out: list[dict] = []
    for _, row in work.head(8).iterrows():
        out.append({
            "award_id": _first_text(row, ("award_id",)),
            "generated_award_id": _first_text(row, ("generated_award_id",)),
            "award_key": _first_text(row, ("award_key", "generated_award_id", "award_id")),
            "end_date": _date_iso(row["_end"]),
            "days_to_end": int(row["_days"]),
            "total_obligated": _first_number(row, ("total_obligated", "award_amount")),
            "awarding_agency": _first_text(row, ("awarding_agency",)),
            "description": _first_text(row, ("description",)),
            "basis": "period-of-performance end date falls 30-540 days ahead; not a predicted solicitation",
            "known_at": _instant_iso(_first_text(row, ("known_at", "first_seen_at", "_first_seen"))),
            "effective_at": _date_iso(_first_text(row, ("last_modified_date", "effective_at", "start_date"))),
            "source_url": _award_link(row),
        })
    return out


def _fact_id(ticker: str, kind: str, effective_at: str | None, evidence: str) -> str:
    raw = f"{ticker}|{kind}|{effective_at or ''}|{evidence}".encode()
    return f"govrev-{hashlib.sha256(raw).hexdigest()[:16]}"


def _catalyst_fact(
    ticker: str,
    kind: str,
    effective_at: str | None,
    known_at: str | None,
    headline: str,
    detail: str,
    value: dict | None,
    evidence_refs: list[str],
    *,
    classification: str = "observed_fact",
) -> dict:
    evidence = "|".join(evidence_refs)
    return {
        "contract": CATALYST_CONTRACT,
        "id": _fact_id(ticker, kind, effective_at, evidence),
        "entity_id": ticker,
        "kind": kind,
        "classification": classification,
        "effective_at": effective_at,
        "known_at": known_at,
        "headline": headline,
        "detail": detail,
        "value": value,
        "evidence_refs": evidence_refs,
        "authority": _AUTHORITY.copy(),
    }


def _catalysts(
    ticker: str,
    metrics: dict,
    actions: list[dict],
    recompetes: list[dict],
    known_at: str | None,
    effective_at: str | None,
) -> list[dict]:
    facts: list[dict] = []
    velocity = metrics.get("award_velocity_yoy_pct")
    ttm = metrics.get("ttm_obligations") or 0.0
    if velocity is not None and abs(float(velocity)) >= 20 and ttm >= 1_000_000:
        direction = "accelerated" if velocity > 0 else "decelerated"
        facts.append(_catalyst_fact(
            ticker, "award_velocity_change", effective_at, known_at,
            f"Reported contract obligations {direction} year over year",
            "Compares two complete trailing 12-month windows after the reporting-lag exclusion.",
            {"amount": velocity, "unit": "percent_yoy"},
            [SPENDING_OVER_TIME_URL],
        ))

    for action in actions:
        amount = action.get("federal_action_obligation")
        if amount is None:
            continue
        threshold = max(5_000_000.0, 0.10 * abs(float(ttm)))
        if abs(float(amount)) < threshold:
            continue
        kind = "large_deobligation" if amount < 0 else "large_contract_action"
        verb = "deobligation" if amount < 0 else "positive contract action"
        facts.append(_catalyst_fact(
            ticker, kind, action.get("effective_at"), action.get("known_at") or known_at,
            f"Large {verb} observed",
            action.get("description") or "USAspending transaction history action.",
            {"amount": amount, "unit": "usd"},
            [action.get("source_url") or TRANSACTIONS_URL],
        ))
        if len(facts) >= 5:
            break

    agency = metrics.get("agency_concentration") or {}
    if (agency.get("top_share_pct") or 0) >= 70:
        facts.append(_catalyst_fact(
            ticker, "agency_concentration", effective_at, known_at,
            "Federal award exposure is concentrated in one awarding agency",
            f"{agency.get('top_name')} represents {agency.get('top_share_pct')}% of covered obligations.",
            {"amount": agency.get("top_share_pct"), "unit": "percent_share"},
            [SPENDING_BY_AWARD_URL],
        ))

    if recompetes:
        first = recompetes[0]
        facts.append(_catalyst_fact(
            ticker, "recompete_window", first.get("end_date"), first.get("known_at") or known_at,
            "Covered award enters a rule-based recompete watch window",
            first.get("basis") or "Period-of-performance end date rule.",
            {"amount": first.get("days_to_end"), "unit": "days_to_end"},
            [first.get("source_url") or SPENDING_BY_AWARD_URL],
            classification="derived_deterministic",
        ))
    return facts[:8]


def _confidence(
    entity: dict,
    velocity: dict,
    awards: pd.DataFrame,
    actions: pd.DataFrame,
    monthly_available: bool,
) -> dict:
    points = 0
    if monthly_available:
        points += 2
    if velocity.get("months_current") == 12 and velocity.get("months_prior") == 12:
        points += 2
    if not awards.empty:
        points += 1
    if not actions.empty:
        points += 1
    match = entity.get("match_confidence", "low")
    points += {"high": 2, "medium": 1}.get(match, 0)
    raw_level = "high" if points >= 7 else "medium" if points >= 4 else "low" if points else "unavailable"
    # Award/detail collection is intentionally bounded in v1. Fresh data is not
    # the same thing as complete data, so the UI confidence may not display as
    # high until a collector reports auditable completeness denominators.
    bounded_detail = bool(not awards.empty or not actions.empty)
    level = "medium" if bounded_detail and raw_level == "high" else raw_level
    limitations = []
    if entity.get("match_method") == "curated_fuzzy_name":
        limitations.append("recipient query is a curated fuzzy-name match; subsidiaries and false positives require UEI validation")
    if awards.empty:
        limitations.append("award-level detail is not yet collected")
    if actions.empty:
        limitations.append("transaction actions are not yet collected")
    if bounded_detail:
        limitations.append("award and action detail is a bounded sample; confidence is capped at medium")
    return {
        "level": level,
        "uncapped_level": raw_level,
        "bounded_sample": bounded_detail,
        "maximum_presentation_level": "medium" if bounded_detail else None,
        "coverage_points": points,
        "components": {
            "entity_match": match,
            "months_current": velocity.get("months_current", 0),
            "months_prior": velocity.get("months_prior", 0),
            "award_records": int(len(awards)),
            "action_records": int(len(actions)),
        },
        "limitations": limitations,
    }


def _latest_known_at(values: Iterable[Any]) -> str | None:
    stamps = [ts for ts in (_timestamp(v) for v in values) if ts is not None]
    return max(stamps).isoformat() if stamps else None


def _freshness_contract(
    *,
    monthly: pd.DataFrame,
    monthly_known_at: Any,
    monthly_visible: bool,
    latest_complete_month: pd.Timestamp,
    ingest_status: Any,
    awards_visible: int,
    actions_visible: int,
    entities_total: int,
    as_of_day: pd.Timestamp,
    knowledge_cutoff: pd.Timestamp,
) -> dict:
    """Separate aggregate, award-detail, and action health without future leakage."""

    def age_days(stamp: pd.Timestamp | None) -> int | None:
        if stamp is None:
            return None
        return max(0, int((as_of_day - stamp.normalize()).days))

    monthly_ts = _timestamp(monthly_known_at)
    monthly_age = age_days(monthly_ts) if monthly_visible else None
    if monthly.empty:
        aggregate_status = "unavailable"
    elif monthly_ts is None:
        aggregate_status = "unverified"
    elif not monthly_visible:
        aggregate_status = "future_at_asof"
    elif monthly_age is not None and monthly_age > AGGREGATE_FRESHNESS_SLA_DAYS:
        aggregate_status = "stale"
    else:
        aggregate_status = "ok"

    aggregate = {
        "status": aggregate_status,
        "known_at": _instant_iso(monthly_known_at) if monthly_visible else None,
        "visible_at_as_of": bool(monthly_visible),
        "age_days": monthly_age,
        "latest_complete_month": latest_complete_month.date().isoformat(),
        "reporting_lag_months": REPORTING_LAG_MONTHS,
        "freshness_sla_days": AGGREGATE_FRESHNESS_SLA_DAYS,
    }

    status_doc = ingest_status if isinstance(ingest_status, dict) else {}
    ingest_ts = _timestamp(status_doc.get("observed_at"))
    ingest_visible = ingest_ts is not None and ingest_ts <= knowledge_cutoff
    ingest_age = age_days(ingest_ts) if ingest_visible else None
    errors = status_doc.get("errors") if ingest_visible else []
    errors = errors if isinstance(errors, list) else []
    rails_doc = status_doc.get("rails") if ingest_visible else {}
    rails_doc = rails_doc if isinstance(rails_doc, dict) else {}
    entities_requested = status_doc.get("entities_requested") if ingest_visible else None
    try:
        entities_requested_n = int(entities_requested) if entities_requested is not None else None
    except (TypeError, ValueError):
        entities_requested_n = None
    complete_entity_pass = (
        entities_requested_n is not None and entities_requested_n >= entities_total
    )

    def legacy_rail_status(stages: set[str], *, require_awards: bool) -> tuple[str, int]:
        rail_errors = sum(
            1 for error in errors
            if isinstance(error, dict) and str(error.get("stage") or "") in stages
        )
        if not status_doc:
            return "unavailable", 0
        if not ingest_visible:
            return "future_at_asof", 0
        if ingest_age is not None and ingest_age > DETAIL_FRESHNESS_SLA_DAYS:
            return "stale", rail_errors
        if rail_errors or not complete_entity_pass:
            return "partial", rail_errors
        if require_awards and int(status_doc.get("awards_seen") or 0) <= 0:
            return "partial", rail_errors
        return "ok", rail_errors

    def rail(name: str) -> dict:
        value = rails_doc.get(name)
        return value if isinstance(value, dict) else {}

    def current_rail_state(name: str) -> str | None:
        value = str(rail(name).get("state") or "").strip().lower()
        return value or None

    def bounded_collection_state(name: str) -> str | None:
        """Return current collection health without relabeling corpus coverage.

        The collector's legacy ``state`` remains an upstream-pagination/corpus
        observation.  When its newer completeness contract is present, a
        planned bounded pass can be fresh even while the wider source is not
        exhausted.  Missing or contradictory new metadata stays partial.
        """

        raw_state = current_rail_state(name)
        value = rail(name)
        completeness = value.get("completeness")
        completeness = completeness if isinstance(completeness, dict) else {}
        fields = (
            "bounded_sample_complete",
            "source_exhausted",
            "truncated_by_safety_cap",
        )
        has_bounded_contract = any(
            field in completeness or field in value for field in fields
        )
        if raw_state in {"failed", "not_requested"}:
            return raw_state
        if not has_bounded_contract:
            return raw_state
        values = {
            field: _strict_bool(completeness.get(field, value.get(field)))
            for field in fields
        }
        if raw_state is None or any(item is None for item in values.values()):
            return "partial"
        if values["bounded_sample_complete"] is True:
            # ``source_exhausted`` deliberately does not participate in the
            # collection-health result; it is retained below as coverage.
            return "complete"
        return "partial"

    def bounded_collection_stamp(name: str) -> pd.Timestamp | None:
        """Use the current observation for a verified planned bounded pass."""

        if (
            bounded_collection_state(name) == "complete"
            and current_rail_state(name) != "complete"
        ):
            return ingest_ts
        stamp = _timestamp(rail(name).get("last_successful_observed_at"))
        return stamp if stamp is not None else ingest_ts

    def combined_v2_status(names: tuple[str, ...]) -> str:
        """Map explicit collector rails to presentation health without inflating coverage."""
        if not status_doc:
            return "unavailable"
        if not ingest_visible:
            return "future_at_asof"
        states = [bounded_collection_state(name) for name in names]
        if not any(states):
            return "unavailable"
        if "failed" in states:
            return "failed"
        if any(state in {"partial", "not_requested", None} for state in states):
            return "partial"
        if any(state not in {"complete"} for state in states):
            return "partial"
        successful_stamps = [bounded_collection_stamp(name) for name in names]
        successful_stamps = [stamp for stamp in successful_stamps if stamp is not None]
        oldest_success = min(successful_stamps) if successful_stamps else ingest_ts
        if oldest_success is None:
            return "unverified"
        if age_days(oldest_success) > DETAIL_FRESHNESS_SLA_DAYS:
            return "stale"
        return "ok"

    def rail_error_count(stages: set[str]) -> int:
        return sum(
            1 for error in errors
            if isinstance(error, dict) and str(error.get("stage") or "") in stages
        )

    if rails_doc:
        detail_status = combined_v2_status(("awards", "award_detail"))
        action_status = combined_v2_status(("awards", "award_detail", "actions"))
        detail_errors = rail_error_count({"awards", "award_detail"})
        action_errors = rail_error_count({"awards", "award_detail", "actions"})
    else:
        detail_status, detail_errors = legacy_rail_status(
            {"awards", "award_detail"}, require_awards=True
        )
        action_status, action_errors = legacy_rail_status(
            {"awards", "award_detail", "actions"}, require_awards=False
        )

    def rail_metadata(names: tuple[str, ...]) -> dict:
        selected = {name: rail(name) for name in names if rail(name)}
        successful = [
            bounded_collection_stamp(name)
            for name in selected
        ]
        successful = [stamp for stamp in successful if stamp is not None]
        def completeness_for(value: dict) -> dict:
            raw = value.get("completeness")
            return raw if isinstance(raw, dict) else {}
        return {
            "collection_state": {
                name: str(value.get("state") or "unavailable") for name, value in selected.items()
            },
            "collection_freshness": {
                name: bounded_collection_state(name) or "unavailable"
                for name in selected
            },
            "last_successful_observed_at": (
                min(successful).isoformat() if successful else None
            ),
            "pages": {
                name: value.get("pages") for name, value in selected.items()
                if isinstance(value.get("pages"), dict)
            },
            "denominators": {
                name: value.get("denominators") for name, value in selected.items()
                if isinstance(value.get("denominators"), dict)
            },
            "completeness": {
                name: value.get("completeness") for name, value in selected.items()
                if isinstance(value.get("completeness"), dict)
            },
            "corpus_coverage": {
                name: {
                    "bounded_sample_complete": completeness_for(value).get(
                        "bounded_sample_complete", value.get("bounded_sample_complete")
                    ),
                    "source_exhausted": completeness_for(value).get(
                        "source_exhausted", value.get("source_exhausted")
                    ),
                    "truncated_by_safety_cap": completeness_for(value).get(
                        "truncated_by_safety_cap", value.get("truncated_by_safety_cap")
                    ),
                }
                for name, value in selected.items()
            },
            "response_receipts": sum(
                int(value.get("response_receipts") or 0) for value in selected.values()
            ),
            "full_usaspending_corpus": False,
        }
    detail = {
        "status": detail_status,
        "observed_at": _instant_iso(ingest_ts) if ingest_visible else None,
        "visible_at_as_of": bool(ingest_visible),
        "age_days": ingest_age,
        "records_visible": int(awards_visible),
        "records_seen": int(status_doc.get("awards_seen") or 0) if ingest_visible else None,
        "records_total": int(status_doc.get("awards_total") or 0) if ingest_visible else None,
        "entities_requested": entities_requested_n,
        "entities_total": int(entities_total),
        "error_count": int(detail_errors),
        "scope": "bounded search and award-detail sample",
        "lookback_days": status_doc.get("lookback_days") if ingest_visible else None,
        "search_limit_per_entity": (
            status_doc.get("award_search_limit_per_entity") if ingest_visible else None
        ),
        "detail_limit_per_entity": (
            status_doc.get("detail_awards_limit_per_entity") if ingest_visible else None
        ),
        "freshness_sla_days": DETAIL_FRESHNESS_SLA_DAYS,
        **rail_metadata(("awards", "award_detail")),
    }
    actions = {
        "status": action_status,
        "observed_at": _instant_iso(ingest_ts) if ingest_visible else None,
        "visible_at_as_of": bool(ingest_visible),
        "age_days": ingest_age,
        "records_visible": int(actions_visible),
        "records_seen": int(status_doc.get("actions_seen") or 0) if ingest_visible else None,
        "records_total": int(status_doc.get("actions_total") or 0) if ingest_visible else None,
        "error_count": int(action_errors),
        "scope": "transactions for the bounded top-award sample",
        "award_limit_per_entity": (
            status_doc.get("detail_awards_limit_per_entity") if ingest_visible else None
        ),
        "freshness_sla_days": DETAIL_FRESHNESS_SLA_DAYS,
        **rail_metadata(("awards", "award_detail", "actions")),
    }

    if aggregate_status == "ok" and detail_status == "ok" and action_status == "ok":
        overall = "ok"
    elif aggregate_status == "stale":
        overall = "stale"
    elif aggregate_status == "unavailable" and detail_status == "unavailable":
        overall = "unavailable"
    elif "failed" in {detail_status, action_status}:
        overall = "partial"
    else:
        overall = "partial"
    visible_known = [monthly_known_at if monthly_visible else None, ingest_ts if ingest_visible else None]
    return {
        "status": overall,
        "known_at": _latest_known_at(visible_known),
        "aggregate": aggregate,
        "award_detail": detail,
        "actions": actions,
    }


def build_payload(root: Path | None = None, as_of: str | None = None) -> dict:
    """Build the compact, display-tier company government-revenue payload."""
    repo = _root(root)
    as_of_day, knowledge_cutoff = _analysis_clock(as_of)
    entities = _load_entities(repo)
    monthly = _load_monthly(repo)
    monthly_meta = _read_json(repo / "data" / "usaspending" / "_meta.json", {})
    monthly_known_at = monthly_meta.get("built") if isinstance(monthly_meta, dict) else None
    monthly_known_ts = _timestamp(monthly_known_at)
    monthly_visible = monthly_known_ts is None or monthly_known_ts <= knowledge_cutoff

    gov_dir = repo / "data" / "government_revenue"
    ingest_status = _read_json(gov_dir / "ingest_status.json", {})
    awards_raw = _read_frame(gov_dir / "awards.parquet")
    actions_raw = _read_frame(gov_dir / "award_actions.parquet")
    snapshots_raw = _read_frame(gov_dir / "award_snapshots.parquet")
    # Both mutable award snapshots and transaction actions must be known by
    # the replay cutoff *and* effective no later than the requested as-of day.
    # ``knowledge_cutoff`` is the inclusive end of that UTC day.
    awards = _awards_point_in_time(
        awards_raw,
        snapshots_raw,
        knowledge_cutoff,
        knowledge_cutoff,
    )
    actions = _filter_point_in_time(actions_raw, knowledge_cutoff, knowledge_cutoff)

    month_start = as_of_day.replace(day=1)
    complete_cutoff = month_start - pd.DateOffset(months=REPORTING_LAG_MONTHS)
    eligible_months = monthly.index[monthly.index <= complete_cutoff] if monthly_visible and not monthly.empty else []
    complete_month = max(eligible_months) if len(eligible_months) else complete_cutoff

    company_payloads: list[dict] = []
    known_values: list[Any] = [
        monthly_known_at,
        ingest_status.get("observed_at") if isinstance(ingest_status, dict) else None,
    ]
    for ticker, entity in entities.items():
        series = monthly[ticker] if monthly_visible and ticker in monthly.columns else pd.Series(dtype=float)
        velocity = _velocity(series, complete_month)
        monthly_rows = []
        if not series.empty:
            history = series[series.index <= complete_month].tail(MONTHLY_HISTORY_LIMIT)
            for month, amount in history.items():
                monthly_rows.append({
                    "month": month.date().isoformat(),
                    "obligations": _number(amount),
                    "effective_at": month.date().isoformat(),
                    "known_at": _instant_iso(monthly_known_at),
                })

        company_awards = awards[awards.get("ticker", pd.Series(dtype=str)).astype(str) == ticker].copy() \
            if not awards.empty and "ticker" in awards.columns else pd.DataFrame()
        company_actions = actions[actions.get("ticker", pd.Series(dtype=str)).astype(str) == ticker].copy() \
            if not actions.empty and "ticker" in actions.columns else pd.DataFrame()
        backlog = _backlog(company_awards, as_of_day)
        modifications = _modification_metrics(company_actions, as_of_day)
        agency_concentration = _concentration(company_awards, ("awarding_agency", "funding_agency"))
        program_concentration = _concentration(
            company_awards, ("program", "major_program", "program_acronym", "psc")
        )
        metrics = velocity | backlog | modifications | {
            "latest_complete_month": complete_month.date().isoformat() if not series.empty else None,
            "agency_concentration": agency_concentration,
            "program_concentration": program_concentration,
        }
        compact_awards = _compact_awards(company_awards, as_of_day)
        compact_actions = _compact_actions(company_actions)
        recompetes = _recompetes(company_awards, as_of_day)
        company_known = _latest_known_at(
            [monthly_known_at]
            + [x.get("known_at") for x in compact_awards]
            + [x.get("known_at") for x in compact_actions]
        )
        known_values.append(company_known)
        facts = _catalysts(
            ticker,
            metrics,
            compact_actions,
            recompetes,
            company_known,
            metrics.get("latest_complete_month"),
        )
        provenance = [
            {
                "contract": PROVENANCE_CONTRACT,
                "dataset": "usaspending_monthly_prime_contract_obligations",
                "publisher": "U.S. Treasury, USAspending.gov",
                "source_url": SPENDING_OVER_TIME_URL,
                "known_at": _instant_iso(monthly_known_at),
                "effective_through": metrics.get("latest_complete_month"),
                "point_in_time": bool(monthly_known_at),
                "limitations": [
                    "three most recent reporting months excluded",
                    "collection-level known_at; legacy monthly rows do not preserve each historical first-seen time",
                    "recipient matching follows the curated entity query",
                ],
            }
        ]
        if not company_awards.empty:
            provenance.append({
                "contract": PROVENANCE_CONTRACT,
                "dataset": "usaspending_prime_contract_awards",
                "publisher": "U.S. Treasury, USAspending.gov",
                "source_url": SPENDING_BY_AWARD_URL,
                "known_at": _latest_known_at(company_awards.get(_knowledge_column(company_awards), [])),
                "effective_through": _date_iso(as_of_day),
                "point_in_time": bool(_knowledge_column(company_awards)),
                "limitations": ["award search amount is obligated value, not necessarily contract ceiling"],
            })
        if not company_actions.empty:
            provenance.append({
                "contract": PROVENANCE_CONTRACT,
                "dataset": "usaspending_award_transaction_history",
                "publisher": "U.S. Treasury, USAspending.gov",
                "source_url": TRANSACTIONS_URL,
                "known_at": _latest_known_at(company_actions.get(_knowledge_column(company_actions), [])),
                "effective_through": _date_iso(as_of_day),
                "point_in_time": bool(_knowledge_column(company_actions)),
                "limitations": ["actions are reported records and can be revised or deobligated later"],
            })

        company_payloads.append({
            "ticker": ticker,
            "name": entity.get("name", ticker),
            "tags": list(entity.get("tags", [])),
            "entity_match": {
                "method": entity.get("match_method", "curated_fuzzy_name"),
                "recipient_search_text": entity.get("recipient_search_text"),
                "aliases": list(entity.get("recipient_aliases", [])),
                "confidence": entity.get("match_confidence", "low"),
            },
            "monthly_obligations": monthly_rows,
            "awards": compact_awards,
            "recent_actions": compact_actions,
            "metrics": metrics,
            "recompete_candidates": recompetes,
            "catalyst_facts": facts,
            "confidence": _confidence(entity, velocity, company_awards, company_actions, bool(monthly_rows)),
            "provenance": provenance,
            "authority": _AUTHORITY.copy(),
        })

    opportunity_intelligence = build_opportunity_intelligence(
        repo,
        company_payloads,
        as_of=as_of_day,
        knowledge_cutoff=knowledge_cutoff,
        freshness_reference=(
            pd.Timestamp.now(tz="UTC") if as_of is None else knowledge_cutoff
        ),
    )
    opportunity_context = opportunity_intelligence.get("company_context") or {}
    for company in company_payloads:
        company["opportunity_candidates"] = list(
            opportunity_context.get(company["ticker"]) or []
        )
    known_values.append(opportunity_intelligence.get("known_at"))
    # The event lane intentionally receives no legacy mutable award/action
    # tables.  It can only emit from the dedicated forward ledgers after a
    # receipt-bound baseline has completed; direct resolution artifacts, if
    # present, are the sole route to a listed-company impact.
    award_events, award_event_freshness = _award_event_projection(
        repo,
        companies=company_payloads,
        as_of_day=as_of_day,
        knowledge_cutoff=knowledge_cutoff,
        ingest_status=ingest_status,
    )
    known_values.append(award_event_freshness.get("known_at"))

    ttm_values = [c["metrics"].get("ttm_obligations") for c in company_payloads]
    valid_ttm = [float(v) for v in ttm_values if v is not None]
    velocities = [c["metrics"].get("award_velocity_yoy_pct") for c in company_payloads]
    accelerating = sum(v is not None and v >= 20 for v in velocities)
    decelerating = sum(v is not None and v <= -20 for v in velocities)
    observed_backlogs = [
        c["metrics"].get("funded_capacity_observed")
        for c in company_payloads
        if c["metrics"].get("funded_capacity_observed") is not None
    ]
    unique_award_capacity = None
    shared_award_count = 0
    if not awards.empty:
        market_awards = awards.copy()
        generated = market_awards.get(
            "generated_award_id", pd.Series(index=market_awards.index, dtype=object)
        )
        piid = market_awards.get("award_id", pd.Series(index=market_awards.index, dtype=object))
        canonical = generated.where(generated.notna() & generated.astype(str).str.strip().ne(""))
        canonical = canonical.fillna(
            market_awards.get("ticker", "").astype(str) + "|piid:" + piid.fillna("").astype(str)
        )
        market_awards["_market_award_key"] = canonical.astype(str)
        shared_award_count = int(
            (
                market_awards.groupby("_market_award_key")["ticker"].nunique()
                > 1
            ).sum()
        ) if "ticker" in market_awards.columns else 0
        market_awards["_has_current"] = pd.to_numeric(
            market_awards.get("current_award_amount"), errors="coerce"
        ).notna()
        unique_awards = market_awards.sort_values("_has_current").drop_duplicates(
            "_market_award_key", keep="last"
        )
        unique_award_capacity = _backlog(unique_awards, as_of_day).get(
            "funded_capacity_observed"
        )
    market = {
        "companies_total": len(company_payloads),
        "companies_with_monthly_obligations": sum(bool(c["monthly_obligations"]) for c in company_payloads),
        "companies_with_award_detail": sum(bool(c["awards"]) for c in company_payloads),
        "companies_with_action_detail": sum(bool(c["recent_actions"]) for c in company_payloads),
        "ttm_obligations": _number(sum(valid_ttm)) if valid_ttm else None,
        "ttm_company_exposure_obligations": _number(sum(valid_ttm)) if valid_ttm else None,
        "obligation_scope": (
            "sum of mapped-company recipient exposure series; shared joint ventures may appear "
            "in more than one parent series; not unique federal spend"
        ),
        "accelerating_companies": int(accelerating),
        "decelerating_companies": int(decelerating),
        "funded_capacity_observed": _number(unique_award_capacity),
        "funded_capacity_company_exposure_sum": (
            _number(sum(observed_backlogs)) if observed_backlogs else None
        ),
        # Compatibility alias; scope remains the bounded observed sample.
        "funded_backlog_observed": _number(unique_award_capacity),
        "capacity_scope": (
            "unique award IDs in the bounded USAspending detail sample; not GAAP backlog"
        ),
        "cross_company_shared_awards": shared_award_count,
        "recompete_watch_count": int(sum(len(c["recompete_candidates"]) for c in company_payloads)),
        "active_opportunities": opportunity_intelligence.get("market", {}).get("active_opportunities", 0),
        "opportunity_amendments_7d": opportunity_intelligence.get("market", {}).get("amendments_7d", 0),
        "opportunity_company_candidate_links": opportunity_intelligence.get("market", {}).get("company_candidate_links", 0),
        "award_velocity_breadth": {
            "accelerating": accelerating,
            "stable": sum(v is not None and -20 < v < 20 for v in velocities),
            "decelerating": decelerating,
            "unavailable": sum(v is None for v in velocities),
            "basis": "descriptive counts using +/-20% YoY bands; not a rank or signal",
        },
        "latest_complete_month": complete_month.date().isoformat() if valid_ttm else None,
    }
    freshness = _freshness_contract(
        monthly=monthly,
        monthly_known_at=monthly_known_at,
        monthly_visible=monthly_visible,
        latest_complete_month=complete_month,
        ingest_status=ingest_status,
        awards_visible=len(awards),
        actions_visible=len(actions),
        entities_total=len(entities),
        as_of_day=as_of_day,
        knowledge_cutoff=knowledge_cutoff,
    )
    detail_freshness = freshness["award_detail"]
    freshness["opportunities"] = opportunity_intelligence.get("freshness", {})
    freshness["award_events"] = award_event_freshness
    payload_known_at = _latest_known_at(known_values)
    vertical_links_by_ticker = {
        company["ticker"]: [{
            "contract": "vertical_link.v1",
            "surface_id": "filing_forensics",
            "label_en": "Filing Forensics",
            "label_zh": "财报取证",
            "href": f"fundamental_forensics.html?symbol={company['ticker']}",
            "entity_type": "ticker",
            "entity_id": company["ticker"],
            "available": True,
        }]
        for company in company_payloads
    }
    procurement_workspace = build_procurement_workspace(
        opportunity_intelligence,
        company_payloads,
        as_of=as_of_day.date().isoformat(),
        known_at=payload_known_at,
        award_freshness=detail_freshness,
        award_events=award_events,
        award_event_freshness=award_event_freshness,
        vertical_links_by_ticker=vertical_links_by_ticker,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "workbench": {
            "id": "government_revenue",
            "category": "defense_procurement",
            "entity_type": "public_company",
            "context_contract": CONTEXT_CONTRACT,
            "catalyst_contract": CATALYST_CONTRACT,
            "provenance_contract": PROVENANCE_CONTRACT,
            "sibling_ready": True,
        },
        "as_of": as_of_day.date().isoformat(),
        "known_at": payload_known_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "publisher": "U.S. Treasury, USAspending.gov",
            "official_api_urls": [
                SPENDING_OVER_TIME_URL,
                SPENDING_BY_AWARD_URL,
                AWARD_DETAIL_URL,
                TRANSACTIONS_URL,
                SAM_OPPORTUNITIES_URL,
            ],
            "reporting_lag_months": REPORTING_LAG_MONTHS,
        },
        "authority": _AUTHORITY.copy(),
        "freshness": freshness,
        "coverage": {
            "entities_mapped": len(entities),
            "companies": len(entities),
            "companies_covered": int(sum(bool(c["monthly_obligations"]) for c in company_payloads)),
            "monthly_series_available": int(sum(t in monthly.columns for t in entities)) if monthly_visible else 0,
            "award_records_visible": int(len(awards)),
            "action_records_visible": int(len(actions)),
            "latest_complete_month": complete_month.date().isoformat() if valid_ttm else None,
            "monthly_collection_known_at": _instant_iso(monthly_known_at),
            "monthly_visible_at_as_of": bool(monthly_visible),
            "detail_ingest_observed_at": detail_freshness.get("observed_at"),
            "detail_ingest_visible_at_as_of": detail_freshness.get("visible_at_as_of"),
            "detail_ingest_status": detail_freshness.get("status"),
            "detail_ingest_error_count": detail_freshness.get("error_count"),
            "award_event_snapshots_visible": award_event_freshness.get("snapshot_versions_visible", 0),
            "award_action_versions_visible": award_event_freshness.get("action_versions_visible", 0),
            "award_event_records_visible": len(award_events),
            "award_event_availability": award_event_freshness.get("availability"),
            "award_event_status": award_event_freshness.get("status"),
            "award_event_bounded_sample_complete": award_event_freshness.get(
                "bounded_sample_complete"
            ),
            "award_event_source_exhausted": award_event_freshness.get("source_exhausted"),
            "award_event_truncated_by_safety_cap": award_event_freshness.get(
                "truncated_by_safety_cap"
            ),
            "award_event_coverage_manifest_id": award_event_freshness.get(
                "coverage_manifest_id"
            ),
            "historical_replay_note": (
                "award actions and snapshots are first-seen ledgers; public award changes use only the "
                "separate receipt-bound forward spine; the legacy monthly frame is only replayable "
                "from its collection-level known_at"
            ),
            "opportunity_records_visible": opportunity_intelligence.get("coverage", {}).get("records_visible", 0),
            "opportunity_revision_records_visible": opportunity_intelligence.get("coverage", {}).get("revision_records_visible", 0),
            "opportunity_documents_visible": opportunity_intelligence.get("coverage", {}).get("documents_visible", 0),
        },
        "market": market,
        "opportunity_intelligence": opportunity_intelligence,
        "procurement_workspace": procurement_workspace,
        "companies": company_payloads,
    }


def ticker_context(payload: dict, ticker: str) -> dict | None:
    """Extract a generic, provenance-carrying context packet for Neural Web/Prophet."""
    symbol = str(ticker).upper().strip()
    company = next((c for c in payload.get("companies", []) if c.get("ticker") == symbol), None)
    if company is None:
        return None
    return {
        "schema_version": CONTEXT_CONTRACT,
        "workbench": payload.get("workbench", {}),
        "as_of": payload.get("as_of"),
        "known_at": payload.get("known_at"),
        "entity": {
            "id": company.get("ticker"),
            "type": "public_company",
            "name": company.get("name"),
            "tags": company.get("tags", []),
        },
        "metrics": company.get("metrics", {}),
        "catalyst_facts": company.get("catalyst_facts", []),
        "recompete_candidates": company.get("recompete_candidates", []),
        "opportunity_candidates": company.get("opportunity_candidates", []),
        "confidence": company.get("confidence", {}),
        "provenance": company.get("provenance", []),
        "authority": _AUTHORITY.copy(),
    }


def load_latest_payload(root: Path | None = None) -> dict | None:
    """Load the built payload from the canonical data path, then its site mirror."""
    repo = _root(root)
    paths = (
        repo / "data" / "government_revenue" / "latest.json",
        repo / "site" / "government-revenue-data" / "latest.json",
        repo / "site" / "government_revenue_data" / "latest.json",
    )
    for path in paths:
        payload = _read_json(path, None)
        if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION:
            return payload
    return None
