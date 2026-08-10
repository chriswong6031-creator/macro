#!/usr/bin/env python3
"""Publish the receipt-bound Government Revenue candidate projection.

This module is deliberately the only writer for the Government Revenue
research-candidate ledger and its current public projection.  Candidate
construction itself lives in :mod:`engine.government_revenue.candidates` and
is pure.  This boundary validates the immutable sources, preserves the prior
ledger byte-for-byte, appends only new observations, and binds the resulting
generation to a state and publication-status receipt.

Usage::

    python -m scripts.build_government_revenue_candidates \
        --generated-at 2026-08-03T07:00:00+00:00
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import sys
from pathlib import Path
import tempfile
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.government_revenue.candidates import (
    HISTORICAL_SUPPRESSION_APPLICATION_CONTRACT,
    HISTORICAL_SUPPRESSION_CONFIG_PATH,
    HISTORICAL_SUPPRESSION_SOURCE_PREFIX,
    ISSUANCE_CORRECTION_APPLICATION_CONTRACT,
    ISSUANCE_CORRECTION_CONFIG_PATH,
    ISSUANCE_CORRECTION_SOURCE_PREFIX,
    build_candidate_observations,
    build_candidate_queue,
    candidate_historical_suppression_activation,
    candidate_historical_suppression_entry,
    candidate_issuance_correction_activation,
    candidate_issuance_correction_entry,
    candidate_latest_semantic_sha256,
    candidate_queue_content_id,
    historical_suppression_entry_key,
    issuance_correction_entry_key,
    is_valid_candidate_payload,
    is_valid_candidate_queue,
    load_candidate_historical_suppression_manifest,
    load_candidate_issuance_correction_manifest,
    validate_candidate_reviewed_history_binding,
)  # noqa: E402
from engine.government_revenue.entity_resolution import load_recipient_entity_graph  # noqa: E402
from engine.government_revenue.workspace import is_valid_procurement_workspace  # noqa: E402
from scripts import build_government_revenue  # noqa: E402


STATE_CONTRACT = "government_revenue.candidate_projection_state.v1"
STATUS_CONTRACT = "government_revenue.candidate_projection_status.v1"
SCHEMA_VERSION = "1.0.0"
DATA_DIRECTORY = Path("data/government_revenue")
PUBLIC_DIRECTORY = Path("site/government-revenue-data")
LEDGER_FILENAME = "candidate_ledger.jsonl"
QUEUE_FILENAME = "candidate_queue.json"
STATE_FILENAME = "candidate_projection_state.json"
STATUS_FILENAME = "candidate_projection_status.json"
PUBLIC_QUEUE_FILENAME = "candidates.json"

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
_STATE_FIELDS = {
    "contract",
    "schema_version",
    "generated_at",
    "as_of",
    "known_at",
    "queue_content_id",
    "latest_sha256",
    "workspace_bundle_id",
    "workspace_sha256",
    "recipient_graph_id",
    "recipient_graph_digest",
    "ledger",
}
_STATUS_FIELDS = {
    "contract",
    "schema_version",
    "status",
    "generated_at",
    "as_of",
    "known_at",
    "queue_content_id",
    "candidate_count",
    "mapping_backlog_count",
    "latest_sha256",
    "workspace_bundle_id",
    "recipient_graph_id",
    "recipient_graph_digest",
    "ledger_sha256",
    "ledger_byte_count",
    "ledger_line_count",
    "source_health",
    "authority",
}
_LEDGER_STATE_FIELDS = {
    "sha256",
    "byte_count",
    "line_count",
    "prior_sha256",
    "prior_byte_count",
    "prior_line_count",
    "append_count",
}

__all__ = [
    "CandidateProjectionError",
    "CandidateProjectionInputs",
    "LedgerSnapshot",
    "load_candidate_ledger",
    "project_candidate_artifacts",
    "validate_candidate_projection_inputs",
    "verify_candidate_artifacts",
]


class CandidateProjectionError(ValueError):
    """A source, lineage, or publication binding is not safe to project."""


@dataclass(frozen=True)
class LedgerSnapshot:
    """Canonical ledger bytes plus the decoded immutable observations."""

    raw: bytes
    observations: tuple[dict[str, Any], ...]

    @property
    def sha256(self) -> str:
        return sha256(self.raw).hexdigest()

    @property
    def byte_count(self) -> int:
        return len(self.raw)

    @property
    def line_count(self) -> int:
        return len(self.observations)


@dataclass(frozen=True)
class CandidateProjectionInputs:
    """Verified immutable source material used by one frozen projection run."""

    latest: dict[str, Any]
    workspace: dict[str, Any]
    recipient_graph: dict[str, Any]
    latest_sha256: str
    workspace_bundle_id: str
    workspace_sha256: str
    recipient_graph_id: str
    recipient_graph_digest: str
    historical_suppression_manifest: dict[str, Any] | None
    historical_suppression_sha256: str | None
    issuance_correction_manifest: dict[str, Any] | None
    issuance_correction_sha256: str | None
    generated_at: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CandidateProjectionError("value cannot be represented as canonical JSON") from exc


def _canonical_bytes(value: Any) -> bytes:
    return _canonical_json(value).encode("utf-8")


def _workspace_semantic_sha256(workspace: Mapping[str, Any]) -> str:
    """Bind evidence semantics without treating assembly time as source state."""
    fingerprint = {
        key: value
        for key, value in workspace.items()
        if key != "generated_at"
    }
    return sha256(_canonical_bytes(fingerprint)).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _instant(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CandidateProjectionError(f"{label} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateProjectionError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CandidateProjectionError(f"{label} must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _normalized_instant(value: Any, *, label: str) -> str:
    return _instant(value, label=label).isoformat()


def _read_json_object(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        decoded = raw.decode("utf-8")
        parsed = json.loads(decoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateProjectionError(f"{label} is missing or malformed: {path}") from exc
    if not isinstance(parsed, dict):
        raise CandidateProjectionError(f"{label} must be a JSON object")
    return raw, parsed


def _require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateProjectionError(f"{label} must be a non-empty string")
    return value.strip()


def _queue_content_id(queue: Mapping[str, Any]) -> str:
    """Read the queue content identifier across the W9A schema rename.

    The queue contract originally exposed ``queue_content_id``.  The canonical
    public docket calls this content-addressed value ``content_id``.  Accepting
    either keeps the writer coupled to the final engine/schema pair, while a
    document carrying both must agree exactly.
    """
    content_id = queue.get("content_id")
    legacy_id = queue.get("queue_content_id")
    if content_id is not None and legacy_id is not None and content_id != legacy_id:
        raise CandidateProjectionError("candidate queue content identifiers disagree")
    result = content_id if content_id is not None else legacy_id
    result = _require_text(result, label="candidate queue content id")
    if not result.startswith("grcq1-") or len(result) != len("grcq1-") + 24:
        raise CandidateProjectionError("candidate queue content id is invalid")
    return result


def _validate_authority(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or dict(value) != _AUTHORITY:
        raise CandidateProjectionError(f"{label} must retain display-only all-false authority")
    return dict(value)


def _validate_canonical_latest_workspace(
    root: Path,
    *,
    generated_at: str,
) -> tuple[dict[str, Any], dict[str, Any], str, str, str]:
    canonical_dir = root / DATA_DIRECTORY
    _latest_raw, latest = _read_json_object(canonical_dir / "latest.json", label="canonical latest")
    _workspace_raw, workspace = _read_json_object(
        canonical_dir / "workspace.json", label="canonical workspace"
    )
    try:
        build_government_revenue._validate_payload(latest)
    except (TypeError, ValueError) as exc:
        raise CandidateProjectionError("canonical latest is not a valid Government Revenue generation") from exc
    if (
        workspace.get("schema_version") != "government_procurement_workspace.v2"
        or workspace.get("event_contract") != "government_procurement_event.v2"
        or not is_valid_procurement_workspace(workspace)
    ):
        raise CandidateProjectionError("canonical workspace is not a valid procurement workspace")
    embedded = latest.get("procurement_workspace")
    if not isinstance(embedded, Mapping) or _canonical_json(dict(embedded)) != _canonical_json(workspace):
        raise CandidateProjectionError("canonical latest/workspace semantic binding mismatch")
    bundle_id = _require_text(workspace.get("bundle_id"), label="workspace bundle_id")
    if bundle_id != build_government_revenue._workspace_bundle_id(workspace):
        raise CandidateProjectionError("canonical workspace bundle identity mismatch")
    frozen = _instant(generated_at, label="generated_at")
    for label, value in (
        ("canonical latest known_at", latest.get("known_at")),
        ("canonical workspace known_at", workspace.get("known_at")),
    ):
        if _instant(value, label=label) > frozen:
            raise CandidateProjectionError(f"{label} is after the frozen generated_at clock")
    return (
        latest,
        workspace,
        bundle_id,
        _workspace_semantic_sha256(workspace),
        candidate_latest_semantic_sha256(latest),
    )


def validate_candidate_projection_inputs(
    root: Path = _repo_root(),
    *,
    generated_at: str,
) -> CandidateProjectionInputs:
    """Load and validate the exact source generation before any output write.

    A degraded award-event freshness state remains a valid *source health*
    observation.  An absent/malformed source document or a non-strict reviewed
    recipient graph is not an empty candidate result and therefore fails.
    """
    root = root.resolve()
    normalized_generated_at = _normalized_instant(generated_at, label="generated_at")
    latest, workspace, bundle_id, workspace_sha, latest_sha = _validate_canonical_latest_workspace(
        root,
        generated_at=normalized_generated_at,
    )
    _graph_raw, recipient_graph = _read_json_object(
        root / DATA_DIRECTORY / "recipient_entity_graph.json",
        label="reviewed recipient graph",
    )
    loaded = load_recipient_entity_graph(recipient_graph, as_of=latest.get("as_of"))
    if loaded.get("status") != "ready":
        errors = loaded.get("errors")
        suffix = f": {', '.join(str(item) for item in errors)}" if isinstance(errors, list) else ""
        raise CandidateProjectionError(f"reviewed recipient graph is not strict-ready{suffix}")
    graph_id = _require_text(loaded.get("graph_id"), label="recipient graph_id")
    graph_digest = _require_text(loaded.get("graph_digest"), label="recipient graph digest")
    if len(graph_digest) != 64 or any(character not in "0123456789abcdef" for character in graph_digest):
        raise CandidateProjectionError("recipient graph digest is invalid")
    graph_known_at = _instant(loaded.get("graph_known_at"), label="recipient graph known_at")
    if graph_known_at > _instant(normalized_generated_at, label="generated_at"):
        raise CandidateProjectionError("recipient graph known_at is after the frozen generated_at clock")
    try:
        suppression = load_candidate_historical_suppression_manifest(root)
    except ValueError as exc:
        raise CandidateProjectionError("historical candidate suppression manifest is invalid") from exc
    try:
        correction = load_candidate_issuance_correction_manifest(root)
    except ValueError as exc:
        raise CandidateProjectionError("candidate issuance correction manifest is invalid") from exc
    return CandidateProjectionInputs(
        latest=latest,
        workspace=workspace,
        recipient_graph=recipient_graph,
        latest_sha256=latest_sha,
        workspace_bundle_id=bundle_id,
        workspace_sha256=workspace_sha,
        recipient_graph_id=graph_id,
        recipient_graph_digest=graph_digest,
        historical_suppression_manifest=(suppression[0] if suppression else None),
        historical_suppression_sha256=(suppression[1] if suppression else None),
        issuance_correction_manifest=(correction[0] if correction else None),
        issuance_correction_sha256=(correction[1] if correction else None),
        generated_at=normalized_generated_at,
    )


def _observation_key(row: Mapping[str, Any], *, label: str) -> tuple[str, str]:
    """Return one candidate observation's graph-independent identity.

    ``observation_id`` folds in the reviewed-graph digest, so it moves whenever
    the graph is re-curated -- a re-serialized or merely extended graph made
    every frozen row re-present as unseen, and the append-only writer then
    refused the whole projection, permanently.  What actually identifies an
    observation is the hypothesis and the moment it became knowable:
    ``candidate_id`` (family, issuer, event) is stable across every later graph
    generation, and ``known_at`` is what distinguishes a genuine re-observation
    from a restatement.  Both halves are load-bearing: keying on
    ``candidate_id`` alone would collapse the published observation history --
    ``/candidate/{id}/history`` -- to its first row forever.
    """
    return (
        _require_text(row.get("candidate_id"), label=f"{label} candidate_id"),
        _require_text(row.get("known_at"), label=f"{label} known_at"),
    )


def _ledger_by_observation_key(ledger: LedgerSnapshot) -> dict[tuple[str, str], dict[str, Any]]:
    """Index immutable history by graph-independent observation identity."""
    return {
        _observation_key(row, label="candidate ledger row"): row
        for row in ledger.observations
    }


def _latest_ledger_observations(ledger: LedgerSnapshot) -> dict[str, dict[str, Any]]:
    """Index the most recent recorded observation of each candidate."""
    latest: dict[str, dict[str, Any]] = {}
    for row in sorted(
        ledger.observations,
        key=lambda value: (str(value.get("known_at") or ""), str(value.get("observation_id") or "")),
    ):
        latest[row["candidate_id"]] = row
    return latest


def _bound_ledger_observation(
    row: Mapping[str, Any],
    *,
    by_observation_key: Mapping[tuple[str, str], dict[str, Any]],
    latest_by_candidate: Mapping[str, dict[str, Any]],
    label: str,
) -> dict[str, Any] | None:
    """Return the immutable row a projected candidate must publish.

    Normally that is the observation with this exact clock.  A re-curation can
    also hand the current run a clock the ledger never recorded and cannot
    record -- one that moved *behind* the frozen writer clock, which the
    anti-backfill law will not append.  History is the authority there, so the
    already-recorded observation of the same hypothesis is published rather than
    failing the run over a graph edit.
    """
    candidate_id, _known_at = _observation_key(row, label=label)
    exact = by_observation_key.get((candidate_id, _known_at))
    selected = exact if exact is not None else latest_by_candidate.get(candidate_id)
    if selected is None:
        return None
    try:
        projected_source_key = historical_suppression_entry_key(
            candidate_historical_suppression_entry(row)
        )
        ledger_source_key = historical_suppression_entry_key(
            candidate_historical_suppression_entry(selected)
        )
    except ValueError as exc:
        raise CandidateProjectionError(
            f"{label} has no immutable source identity"
        ) from exc
    if projected_source_key != ledger_source_key:
        raise CandidateProjectionError(
            f"{label} source identity differs from the immutable ledger row"
        )
    return selected


def _ledger_from_bytes(raw: bytes, *, label: str) -> LedgerSnapshot:
    if not raw:
        return LedgerSnapshot(raw=b"", observations=())
    if not raw.endswith(b"\n"):
        raise CandidateProjectionError(f"{label} must end with one canonical JSONL newline")
    if b"\r" in raw:
        raise CandidateProjectionError(f"{label} must use LF-only canonical JSONL")
    lines = raw[:-1].split(b"\n")
    if not lines or any(not line for line in lines):
        raise CandidateProjectionError(f"{label} contains an empty JSONL row")
    observations: list[dict[str, Any]] = []
    observation_ids: set[str] = set()
    observation_keys: set[tuple[str, str]] = set()
    for index, line in enumerate(lines, start=1):
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CandidateProjectionError(f"{label} row {index} is malformed JSON") from exc
        if not isinstance(value, dict) or not is_valid_candidate_payload(value):
            raise CandidateProjectionError(f"{label} row {index} violates the candidate contract")
        if line != _canonical_bytes(value):
            raise CandidateProjectionError(f"{label} row {index} is not canonical JSON")
        observation_id = _require_text(value.get("observation_id"), label=f"{label} row {index} observation_id")
        if observation_id in observation_ids:
            raise CandidateProjectionError(f"{label} has a duplicate observation_id")
        observation_ids.add(observation_id)
        # One row per hypothesis per moment it was knowable.  A candidate may be
        # observed many times -- that history is a published surface -- but a
        # re-serialized reviewed graph is not one of those moments.
        observation_key = _observation_key(value, label=f"{label} row {index}")
        if observation_key in observation_keys:
            raise CandidateProjectionError(f"{label} has a duplicate candidate observation")
        observation_keys.add(observation_key)
        observations.append(value)
    return LedgerSnapshot(raw=raw, observations=tuple(observations))


def load_candidate_ledger(path: Path) -> LedgerSnapshot:
    """Load every prior ledger row, rejecting any non-canonical or invalid row."""
    try:
        raw = path.read_bytes() if path.exists() else b""
    except OSError as exc:
        raise CandidateProjectionError(f"candidate ledger is unavailable: {path}") from exc
    return _ledger_from_bytes(raw, label="candidate ledger")


def _validate_ledger_state_binding(state: Mapping[str, Any], ledger: LedgerSnapshot) -> None:
    if set(state) != _STATE_FIELDS:
        raise CandidateProjectionError("candidate projection state has an invalid field set")
    if state.get("contract") != STATE_CONTRACT or state.get("schema_version") != SCHEMA_VERSION:
        raise CandidateProjectionError("candidate projection state has an invalid contract")
    _normalized_instant(state.get("generated_at"), label="candidate projection state generated_at")
    _normalized_instant(state.get("as_of"), label="candidate projection state as_of")
    _normalized_instant(state.get("known_at"), label="candidate projection state known_at")
    _queue_content_id({"content_id": state.get("queue_content_id")})
    _require_text(state.get("latest_sha256"), label="candidate projection state latest_sha256")
    _require_text(state.get("workspace_bundle_id"), label="candidate projection state workspace_bundle_id")
    _require_text(state.get("workspace_sha256"), label="candidate projection state workspace_sha256")
    _require_text(state.get("recipient_graph_id"), label="candidate projection state recipient_graph_id")
    _require_text(state.get("recipient_graph_digest"), label="candidate projection state recipient_graph_digest")
    state_ledger = state.get("ledger")
    if not isinstance(state_ledger, Mapping) or set(state_ledger) != _LEDGER_STATE_FIELDS:
        raise CandidateProjectionError("candidate projection state ledger receipt is invalid")
    for field in ("sha256", "prior_sha256"):
        value = state_ledger.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise CandidateProjectionError(f"candidate projection state {field} is invalid")
    for field in ("byte_count", "line_count", "prior_byte_count", "prior_line_count", "append_count"):
        value = state_ledger.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise CandidateProjectionError(f"candidate projection state {field} is invalid")
    if (
        state_ledger["sha256"] != ledger.sha256
        or state_ledger["byte_count"] != ledger.byte_count
        or state_ledger["line_count"] != ledger.line_count
    ):
        raise CandidateProjectionError("candidate ledger does not match its prior projection state")
    prior_byte_count = state_ledger["prior_byte_count"]
    prior_line_count = state_ledger["prior_line_count"]
    if prior_byte_count > ledger.byte_count or prior_line_count > ledger.line_count:
        raise CandidateProjectionError("candidate projection state prior prefix exceeds the ledger")
    prefix = ledger.raw[:prior_byte_count]
    if sha256(prefix).hexdigest() != state_ledger["prior_sha256"]:
        raise CandidateProjectionError("candidate ledger prior prefix does not match projection state")
    if _ledger_from_bytes(prefix, label="candidate ledger prior prefix").line_count != prior_line_count:
        raise CandidateProjectionError("candidate projection state prior line count is invalid")
    if state_ledger["append_count"] != ledger.line_count - prior_line_count:
        raise CandidateProjectionError("candidate projection state append count is invalid")


def _load_prior_ledger_and_state(
    root: Path,
) -> tuple[LedgerSnapshot, dict[str, Any] | None, dict[str, Any] | None]:
    canonical_dir = root / DATA_DIRECTORY
    ledger_path = canonical_dir / LEDGER_FILENAME
    state_path = canonical_dir / STATE_FILENAME
    queue_path = canonical_dir / QUEUE_FILENAME
    ledger = load_candidate_ledger(ledger_path)
    if not state_path.exists():
        if ledger.line_count or queue_path.exists():
            raise CandidateProjectionError("candidate projection has no state receipt")
        return ledger, None, None
    if not ledger_path.exists():
        raise CandidateProjectionError("candidate projection state exists but candidate ledger is absent")
    if not queue_path.exists():
        raise CandidateProjectionError("candidate projection state exists but candidate queue is absent")
    state_raw, state = _read_json_object(state_path, label="candidate projection state")
    queue_raw, queue = _read_json_object(queue_path, label="prior candidate queue")
    _validate_ledger_state_binding(state, ledger)
    if (
        not is_valid_candidate_queue(queue)
        or _queue_content_id(queue) != state.get("queue_content_id")
    ):
        raise CandidateProjectionError("prior candidate queue is detached from projection state")
    try:
        validate_candidate_reviewed_history_binding(
            queue,
            state,
            root=root,
            allow_exact_legacy_predecessor=True,
            allow_exact_incident_predecessor=True,
            issued_observations=ledger.observations,
            queue_raw_sha256=sha256(queue_raw).hexdigest(),
            projection_state_raw_sha256=sha256(state_raw).hexdigest(),
        )
    except ValueError as exc:
        raise CandidateProjectionError(
            "prior candidate reviewed-history binding is invalid"
        ) from exc
    return ledger, state, queue


def _current_projection(
    inputs: CandidateProjectionInputs,
) -> tuple[list[dict[str, Any]], dict[str, Any], str, dict[str, Any]]:
    """Build current pure observations and refuse queue/authority drift."""
    observations = build_candidate_observations(
        inputs.latest,
        inputs.recipient_graph,
        generated_at=inputs.generated_at,
    )
    if not isinstance(observations, list):
        raise CandidateProjectionError("candidate observation engine returned a non-list")
    observation_ids: set[str] = set()
    for index, observation in enumerate(observations, start=1):
        if not isinstance(observation, dict) or not is_valid_candidate_payload(observation):
            raise CandidateProjectionError(f"current candidate observation {index} violates the candidate contract")
        observation_id = _require_text(
            observation.get("observation_id"),
            label=f"current candidate observation {index} id",
        )
        if observation_id in observation_ids:
            raise CandidateProjectionError("current candidate observations duplicate an observation_id")
        observation_ids.add(observation_id)
        observation_known_at = observation.get("known_at")
        if observation_known_at is None and isinstance(observation.get("clocks"), Mapping):
            # Retain a narrow compatibility bridge for an already-persisted
            # pre-W9A draft row while the final contract exposes known_at at
            # the top level.
            observation_known_at = observation["clocks"].get("known_at")
        if _instant(observation_known_at, label=f"current candidate observation {index} known_at") > _instant(
            inputs.generated_at, label="generated_at"
        ):
            raise CandidateProjectionError("current candidate observation is after the frozen generated_at clock")
        _validate_authority(observation.get("authority"), label=f"current candidate observation {index} authority")
    queue = build_candidate_queue(
        inputs.latest,
        inputs.recipient_graph,
        generated_at=inputs.generated_at,
    )
    if not isinstance(queue, dict) or not is_valid_candidate_queue(queue):
        raise CandidateProjectionError("current candidate queue violates its contract")
    queue_content_id = _queue_content_id(queue)
    # ``content_id`` is the final W9A field name.  Recompute it at the writer
    # boundary rather than trusting a self-consistent serialized queue.
    if "content_id" in queue:
        try:
            expected_content_id = candidate_queue_content_id(queue)
        except ValueError as exc:
            raise CandidateProjectionError("current candidate queue content id cannot be recomputed") from exc
        if queue_content_id != expected_content_id:
            raise CandidateProjectionError("current candidate queue content id is detached from its payload")
    _validate_authority(queue.get("authority"), label="current candidate queue authority")
    if (
        _normalized_instant(
            queue.get("generated_at"), label="current candidate queue generated_at"
        )
        != inputs.generated_at
    ):
        raise CandidateProjectionError("current candidate queue drifted from the frozen generated_at clock")
    queue_candidates = queue.get("candidates")
    backlog = queue.get("mapping_backlog")
    recently_matured = queue.get("recently_matured", [])
    if (
        not isinstance(queue_candidates, list)
        or not isinstance(backlog, list)
        or not isinstance(recently_matured, list)
    ):
        raise CandidateProjectionError(
            "current candidate queue is missing candidates, mapping backlog, or recently matured rows"
        )
    if any(not isinstance(row, dict) for row in backlog):
        raise CandidateProjectionError("current candidate queue contains a malformed mapping backlog row")
    candidate_by_id = {row["observation_id"]: row for row in observations}
    queue_by_id = {
        row.get("observation_id"): row
        for row in queue_candidates
        if isinstance(row, Mapping)
    }
    if len(queue_by_id) != len(queue_candidates) or set(queue_by_id) != set(candidate_by_id):
        raise CandidateProjectionError("candidate queue is not the current exact-observation projection")
    for observation_id, observation in candidate_by_id.items():
        if (
            not isinstance(queue_by_id.get(observation_id), Mapping)
            or _canonical_json(queue_by_id[observation_id]) != _canonical_json(observation)
        ):
            raise CandidateProjectionError("candidate queue altered a current exact observation")
    # Mapping backlog is deliberately a separate discovery surface.  It cannot
    # acquire an observation identity or issuer-attribution assertion en route
    # to the candidate ledger.
    for index, row in enumerate(backlog, start=1):
        if "observation_id" in row or row.get("issuer_attribution") != "not_asserted":
            raise CandidateProjectionError(f"mapping backlog row {index} is being promoted as a candidate")
    counts = queue.get("counts")
    if not isinstance(counts, Mapping):
        raise CandidateProjectionError("current candidate queue counts are invalid")
    if counts.get("total") != len(queue_candidates) or counts.get("mapping_needed") != len(backlog):
        raise CandidateProjectionError("current candidate queue counts disagree with its rows")
    health = _queue_source_health(queue)
    if health["recipient_graph_status"] != "ready":
        raise CandidateProjectionError("candidate queue did not retain the strict recipient graph")
    _assert_candidate_source_binding(queue, inputs=inputs)
    return observations, queue, queue_content_id, health


def _queue_source_health(queue: Mapping[str, Any]) -> dict[str, Any]:
    source_health = queue.get("freshness")
    if not isinstance(source_health, Mapping):
        raise CandidateProjectionError("candidate queue source health is invalid")
    return {
        "status": _require_text(source_health.get("status"), label="candidate source health status"),
        "award_events_status": _require_text(
            source_health.get("award_events_status"), label="candidate source award event status"
        ),
        "recipient_graph_status": _require_text(
            source_health.get("recipient_graph_status"), label="candidate source recipient graph status"
        ),
    }


def _assert_candidate_source_binding(
    queue: Mapping[str, Any],
    *,
    inputs: CandidateProjectionInputs,
    issued_observation_ids: frozenset[str] = frozenset(),
) -> None:
    """Bind exact rows and backlog provenance to this complete source view.

    A candidate frozen into the ledger by an earlier generation keeps the
    reviewed-graph generation it was issued under: the ledger is append-only, so
    re-binding it to today's digest would be rewriting history rather than
    recording it.  ``issued_observation_ids`` names exactly those rows.  Every
    row this generation introduces -- and the queue document, its source content
    IDs, and the whole mapping backlog -- stays bound to the current graph.
    """
    source_content_ids = queue.get("source_content_ids")
    required_content_ids = {
        f"latest-sha256:{inputs.latest_sha256}",
        f"graph-sha256:{inputs.recipient_graph_digest}",
        inputs.workspace_bundle_id,
    }
    if (
        not isinstance(source_content_ids, list)
        or not required_content_ids.issubset(set(source_content_ids))
    ):
        raise CandidateProjectionError("candidate queue is not bound to every source input")
    for collection_name in ("candidates", "recently_matured"):
        rows = queue.get(collection_name, [])
        if not isinstance(rows, list):
            raise CandidateProjectionError(f"candidate queue {collection_name} is invalid")
        for index, row in enumerate(rows, start=1):
            resolution = row.get("issuer_resolution_ref") if isinstance(row, Mapping) else None
            artifact_ids = row.get("artifact_content_ids") if isinstance(row, Mapping) else None
            label = f"candidate queue {collection_name} row {index}"
            detached = f"{label} is detached from the reviewed graph"
            if not isinstance(resolution, Mapping) or not isinstance(artifact_ids, list):
                raise CandidateProjectionError(detached)
            if row.get("observation_id") in issued_observation_ids:
                graph_id = _require_text(resolution.get("graph_id"), label=f"{label} graph_id")
                graph_digest = _require_text(
                    resolution.get("graph_digest"), label=f"{label} graph_digest"
                )
            else:
                graph_id = inputs.recipient_graph_id
                graph_digest = inputs.recipient_graph_digest
            if (
                resolution.get("graph_id") != graph_id
                or resolution.get("graph_digest") != graph_digest
                or f"graph-sha256:{graph_digest}" not in artifact_ids
            ):
                raise CandidateProjectionError(detached)
    for index, row in enumerate(queue.get("mapping_backlog") or [], start=1):
        artifact_ids = row.get("source_artifact_content_ids") if isinstance(row, Mapping) else None
        if (
            not isinstance(artifact_ids, list)
            or f"latest-sha256:{inputs.latest_sha256}" not in artifact_ids
            or f"graph-sha256:{inputs.recipient_graph_digest}" not in artifact_ids
        ):
            raise CandidateProjectionError(
                f"candidate queue mapping backlog row {index} is detached from its source generation"
            )


def _assert_queue_ledger_binding(queue: Mapping[str, Any], ledger: LedgerSnapshot) -> None:
    """Ensure every projected exact candidate exactly matches immutable history."""
    by_observation_key = _ledger_by_observation_key(ledger)
    latest_by_candidate = _latest_ledger_observations(ledger)
    for collection_name in ("candidates", "recently_matured"):
        rows = queue.get(collection_name, [])
        if not isinstance(rows, list):
            raise CandidateProjectionError(f"candidate queue {collection_name} is invalid")
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping) or not is_valid_candidate_payload(row):
                raise CandidateProjectionError(
                    f"candidate queue {collection_name} row {index} violates the candidate contract"
                )
            ledger_row = _bound_ledger_observation(
                row,
                by_observation_key=by_observation_key,
                latest_by_candidate=latest_by_candidate,
                label=f"candidate queue {collection_name} row {index}",
            )
            if ledger_row is None:
                raise CandidateProjectionError(
                    f"candidate queue {collection_name} is not bound to the candidate ledger"
                )
            if _canonical_json(dict(row)) != _canonical_json(ledger_row):
                raise CandidateProjectionError(
                    f"candidate queue {collection_name} differs from its immutable ledger observation"
                )


def _candidate_counts(
    candidates: Sequence[Mapping[str, Any]],
    backlog: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "total": len(candidates),
        "exact_linked": len(candidates),
        "mapping_needed": len(backlog),
        "by_family": dict(
            sorted(Counter(row["candidate_family"] for row in candidates).items())
        ),
        "by_state": dict(
            sorted(Counter(row["candidate_state"] for row in candidates).items())
        ),
        "by_freshness": dict(
            sorted(Counter(row["freshness"]["status"] for row in candidates).items())
        ),
        "by_exact_link_status": {
            "exact_linked": len(candidates),
            "mapping_needed": len(backlog),
        },
    }


def _prior_suppression_receipt(queue: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    coverage = queue.get("coverage") if isinstance(queue, Mapping) else None
    receipt = (
        coverage.get("historical_candidate_suppression")
        if isinstance(coverage, Mapping)
        else None
    )
    if receipt is not None and not isinstance(receipt, Mapping):
        raise CandidateProjectionError("prior candidate suppression receipt is malformed")
    return receipt


def _prior_correction_receipt(queue: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    coverage = queue.get("coverage") if isinstance(queue, Mapping) else None
    receipt = (
        coverage.get("historical_candidate_issuance_correction")
        if isinstance(coverage, Mapping)
        else None
    )
    if receipt is not None and not isinstance(receipt, Mapping):
        raise CandidateProjectionError("prior candidate issuance correction is malformed")
    return receipt


def _match_historical_suppressions(
    *,
    inputs: CandidateProjectionInputs,
    unseen: Sequence[dict[str, Any]],
    issued_source_keys: frozenset[tuple[str, ...]],
    prior_state: Mapping[str, Any] | None,
    prior_queue: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split unseen observations into appendable and exactly reviewed withheld rows."""
    manifest = inputs.historical_suppression_manifest
    manifest_sha256 = inputs.historical_suppression_sha256
    correction_manifest = inputs.issuance_correction_manifest
    if correction_manifest is not None:
        if manifest is None or manifest_sha256 is None:
            raise CandidateProjectionError(
                "candidate issuance correction lacks its original reviewed manifest"
            )
        if _prior_suppression_receipt(prior_queue) is not None:
            raise CandidateProjectionError(
                "candidate issuance correction cannot follow a non-issuance receipt"
            )
        correction_keys = {
            issuance_correction_entry_key(entry)
            for entry in correction_manifest["entries"]
        }
        prior_frozen_at = (
            _instant(
                prior_state.get("generated_at"),
                label="prior candidate projection generated_at",
            )
            if prior_state is not None
            else None
        )
        appendable: list[dict[str, Any]] = []
        unknown_historical_ids: list[str] = []
        for row in unseen:
            known_at = _instant(
                row.get("known_at"), label="new candidate observation known_at"
            )
            try:
                stable_key = historical_suppression_entry_key(
                    candidate_historical_suppression_entry(row)
                )
            except ValueError as exc:
                raise CandidateProjectionError(
                    "new candidate observation has no stable correction identity"
                ) from exc
            if stable_key in correction_keys:
                continue
            if prior_frozen_at is not None and known_at <= prior_frozen_at:
                unknown_historical_ids.append(
                    _require_text(
                        row.get("observation_id"),
                        label="new candidate observation id",
                    )
                )
            else:
                appendable.append(row)
        if unknown_historical_ids:
            raise CandidateProjectionError(
                "new candidate observation is not forward of the prior frozen "
                "generated_at clock: " + ", ".join(sorted(unknown_historical_ids))
            )
        return appendable, []
    prior_receipt = _prior_suppression_receipt(prior_queue)
    if prior_receipt is not None and manifest is None:
        raise CandidateProjectionError(
            "activated historical suppression manifest is no longer present"
        )
    if manifest is None:
        manifest_by_key: dict[tuple[str, ...], dict[str, Any]] = {}
    else:
        manifest_by_key = {
            historical_suppression_entry_key(entry): entry
            for entry in manifest["entries"]
        }
    previously_activated = bool(
        prior_receipt is not None
        and prior_receipt.get("manifest_sha256") == manifest_sha256
    )
    if prior_receipt is not None and not previously_activated:
        raise CandidateProjectionError(
            "historical suppression manifest changed after activation"
        )
    if manifest is not None and not previously_activated:
        predecessor = manifest["predecessor"]
        if (
            prior_state is None
            or prior_queue is None
            or prior_state.get("generated_at")
            != predecessor["projection_generated_at"]
            or prior_queue.get("content_id") != predecessor["queue_content_id"]
        ):
            raise CandidateProjectionError(
                "historical suppression manifest does not match the exact predecessor generation"
            )

    prior_frozen_at = (
        _instant(
            prior_state.get("generated_at"),
            label="prior candidate projection generated_at",
        )
        if prior_state is not None
        else None
    )
    appendable: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    unknown_historical_ids: list[str] = []
    for row in unseen:
        candidate_id = _require_text(
            row.get("candidate_id"), label="new candidate observation candidate_id"
        )
        known_at = _instant(
            row.get("known_at"), label="new candidate observation known_at"
        )
        try:
            current_entry = candidate_historical_suppression_entry(row)
            stable_key = historical_suppression_entry_key(current_entry)
        except ValueError as exc:
            raise CandidateProjectionError(
                "new candidate observation has no stable suppression identity"
            ) from exc
        if stable_key in issued_source_keys:
            continue
        reviewed_entry = manifest_by_key.get(stable_key)
        if reviewed_entry is not None:
            comparable = dict(current_entry)
            if previously_activated:
                # The reviewed graph publication clock may move; the immutable
                # event/source identity may not.  Preserve the first observed
                # clock in the reviewed receipt instead of minting a new rule.
                comparable["observed_known_at"] = reviewed_entry["observed_known_at"]
            if comparable != reviewed_entry:
                raise CandidateProjectionError(
                    "historical suppression source identity changed for " + candidate_id
                )
            if not previously_activated and (
                prior_frozen_at is None or known_at > prior_frozen_at
            ):
                raise CandidateProjectionError(
                    "new historical suppression entry is not behind the predecessor clock"
                )
            suppressed.append(row)
            continue
        if prior_frozen_at is not None and known_at <= prior_frozen_at:
            unknown_historical_ids.append(
                _require_text(
                    row.get("observation_id"),
                    label="new candidate observation id",
                )
            )
        else:
            appendable.append(row)

    if unknown_historical_ids:
        raise CandidateProjectionError(
            "new candidate observation is not forward of the prior frozen "
            "generated_at clock: " + ", ".join(sorted(unknown_historical_ids))
        )
    if manifest is not None and not previously_activated:
        matched_keys = [
            historical_suppression_entry_key(
                candidate_historical_suppression_entry(row)
            )
            for row in suppressed
        ]
        if (
            len(matched_keys) != len(set(matched_keys))
            or sorted(matched_keys) != sorted(manifest_by_key)
        ):
            raise CandidateProjectionError(
                "historical suppression activation is not an exact manifest/row bijection"
            )
    return appendable, suppressed


def _apply_historical_suppression_receipt(
    queue: Mapping[str, Any],
    *,
    inputs: CandidateProjectionInputs,
    suppressed: Sequence[Mapping[str, Any]],
    prior_queue: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Remove only exact reviewed rows and disclose the bounded non-issuance."""
    manifest = inputs.historical_suppression_manifest
    manifest_sha256 = inputs.historical_suppression_sha256
    if manifest is None or manifest_sha256 is None:
        if suppressed:
            raise CandidateProjectionError("suppressed candidate rows have no reviewed manifest")
        return deepcopy(dict(queue))
    manifest_by_key = {
        historical_suppression_entry_key(entry): entry
        for entry in manifest["entries"]
    }
    suppressed_key_rows = [
        historical_suppression_entry_key(
            candidate_historical_suppression_entry(row)
        )
        for row in suppressed
    ]
    if len(suppressed_key_rows) != len(set(suppressed_key_rows)):
        raise CandidateProjectionError(
            "suppressed candidate rows duplicate a stable source identity"
        )
    suppressed_keys = set(suppressed_key_rows)
    prior_receipt = _prior_suppression_receipt(prior_queue)
    if prior_receipt is None:
        if suppressed_keys != set(manifest_by_key):
            raise CandidateProjectionError(
                "historical suppression first activation lacks the exact full source bijection"
            )
        try:
            activation = candidate_historical_suppression_activation(
                manifest,
                manifest_sha256,
                activated_at=inputs.generated_at,
            )
        except ValueError as exc:
            raise CandidateProjectionError(
                "historical suppression activation proof is invalid"
            ) from exc
    else:
        prior_activation = prior_receipt.get("activation")
        if not isinstance(prior_activation, Mapping):
            raise CandidateProjectionError(
                "prior candidate suppression lacks its durable activation proof"
            )
        activation = deepcopy(dict(prior_activation))
    bound = deepcopy(dict(queue))
    for collection_name in ("candidates", "recently_matured"):
        rows = bound.get(collection_name)
        if not isinstance(rows, list):
            raise CandidateProjectionError(
                f"candidate queue {collection_name} is invalid"
            )
        bound[collection_name] = [
            row
            for row in rows
            if historical_suppression_entry_key(
                candidate_historical_suppression_entry(row)
            )
            not in suppressed_keys
        ]
    candidates = bound["candidates"]
    backlog = bound.get("mapping_backlog")
    if not isinstance(backlog, list):
        raise CandidateProjectionError("candidate queue mapping backlog is invalid")
    bound["counts"] = _candidate_counts(candidates, backlog)
    matched_entries = [
        deepcopy(manifest_by_key[key]) for key in sorted(suppressed_keys)
    ]
    receipt = {
        "contract": HISTORICAL_SUPPRESSION_APPLICATION_CONTRACT,
        "manifest_sha256": manifest_sha256,
        "policy": "exact_source_identity_only",
        "decision": "do_not_backfill",
        "predecessor_queue_content_id": manifest["predecessor"]["queue_content_id"],
        "prior_frozen_at": manifest["predecessor"]["projection_generated_at"],
        "manifest_entry_count": len(manifest["entries"]),
        "matched_count": len(matched_entries),
        "inactive_count": len(manifest["entries"]) - len(matched_entries),
        "entries": matched_entries,
        "activation": activation,
    }
    coverage = bound.get("coverage")
    if not isinstance(coverage, dict):
        raise CandidateProjectionError("candidate queue coverage is invalid")
    coverage["historical_candidate_suppression"] = receipt
    source_content_ids = bound.get("source_content_ids")
    if not isinstance(source_content_ids, list):
        raise CandidateProjectionError("candidate queue source content ids are invalid")
    source_content_ids.append(HISTORICAL_SUPPRESSION_SOURCE_PREFIX + manifest_sha256)
    bound["source_content_ids"] = sorted(set(source_content_ids))
    freshness = bound.get("freshness")
    if not isinstance(freshness, dict):
        raise CandidateProjectionError("candidate queue freshness is invalid")
    if candidates:
        freshness["exact_candidate_availability"] = "available"
        freshness["reason"] = (
            "Forward-eligible exact candidates are available; "
            f"{len(matched_entries)} reviewed historical source row(s) were withheld without issuance."
        )
    elif matched_entries:
        freshness["exact_candidate_availability"] = "withheld_historical"
        freshness["reason"] = (
            f"{len(matched_entries)} exact historical source row(s) were reviewed and withheld "
            "by the anti-backfill boundary; no forward-eligible candidate was observed."
        )
    limitations = bound.get("limitations")
    if not isinstance(limitations, list):
        raise CandidateProjectionError("candidate queue limitations are invalid")
    limitations.append(
        "Reviewed historical suppressions are exact source-bound non-issuance receipts; they never append, retime, rank, size, gate, signal, add, or escalate a candidate."
    )
    bound["content_id"] = candidate_queue_content_id(bound)
    if not is_valid_candidate_queue(bound):
        raise CandidateProjectionError(
            "candidate queue is invalid after historical suppression disclosure"
        )
    return bound


def _issuance_correction_rows(
    *,
    inputs: CandidateProjectionInputs,
    prior: LedgerSnapshot,
    prior_queue: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    manifest = inputs.issuance_correction_manifest
    manifest_sha256 = inputs.issuance_correction_sha256
    if manifest is None or manifest_sha256 is None:
        return []
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(prior.observations) < len(entries):
        raise CandidateProjectionError("candidate issuance correction ledger prefix is absent")
    rows = [deepcopy(row) for row in prior.observations[: len(entries)]]
    if [candidate_issuance_correction_entry(row) for row in rows] != entries:
        raise CandidateProjectionError(
            "candidate issuance correction differs from the immutable ledger prefix"
        )
    prior_receipt = _prior_correction_receipt(prior_queue)
    if (
        prior_receipt is not None
        and prior_receipt.get("manifest_sha256") != manifest_sha256
    ):
        raise CandidateProjectionError(
            "candidate issuance correction manifest changed after activation"
        )
    return rows


def _apply_issuance_correction_receipt(
    queue: Mapping[str, Any],
    *,
    inputs: CandidateProjectionInputs,
    corrected_rows: Sequence[Mapping[str, Any]],
    prior_queue: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Quarantine exact issued rows while preserving their immutable ledger bytes."""
    manifest = inputs.issuance_correction_manifest
    manifest_sha256 = inputs.issuance_correction_sha256
    if manifest is None or manifest_sha256 is None:
        if corrected_rows:
            raise CandidateProjectionError(
                "candidate issuance correction rows have no reviewed manifest"
            )
        return deepcopy(dict(queue))
    entries = [dict(entry) for entry in manifest["entries"]]
    if [candidate_issuance_correction_entry(row) for row in corrected_rows] != entries:
        raise CandidateProjectionError(
            "candidate issuance correction is not an exact incident-ledger bijection"
        )
    prior_receipt = _prior_correction_receipt(prior_queue)
    if prior_receipt is None:
        try:
            activation = candidate_issuance_correction_activation(
                manifest,
                manifest_sha256,
                activated_at=inputs.generated_at,
            )
        except ValueError as exc:
            raise CandidateProjectionError(
                "candidate issuance correction activation proof is invalid"
            ) from exc
    else:
        prior_activation = prior_receipt.get("activation")
        if not isinstance(prior_activation, Mapping):
            raise CandidateProjectionError(
                "prior candidate issuance correction lacks its activation proof"
            )
        activation = deepcopy(dict(prior_activation))
    corrected_keys = {
        issuance_correction_entry_key(entry) for entry in entries
    }
    bound = deepcopy(dict(queue))
    for collection_name in ("candidates", "recently_matured"):
        rows = bound.get(collection_name)
        if not isinstance(rows, list):
            raise CandidateProjectionError(
                f"candidate queue {collection_name} is invalid"
            )
        bound[collection_name] = [
            row
            for row in rows
            if historical_suppression_entry_key(
                candidate_historical_suppression_entry(row)
            )
            not in corrected_keys
        ]
    candidates = bound["candidates"]
    recently_matured = bound["recently_matured"]
    backlog = bound.get("mapping_backlog")
    if not isinstance(backlog, list):
        raise CandidateProjectionError("candidate queue mapping backlog is invalid")
    bound["counts"] = _candidate_counts(candidates, backlog)
    incident = manifest["incident"]
    original_review = manifest["original_review"]
    receipt = {
        "contract": ISSUANCE_CORRECTION_APPLICATION_CONTRACT,
        "manifest_sha256": manifest_sha256,
        "incident_id": incident["incident_id"],
        "original_review_manifest_sha256": original_review["manifest_sha256"],
        "policy": "exact_issued_source_identity_only",
        "decision": "quarantine_erroneous_historical_issuance",
        "issued_queue_content_id": incident["issued_queue_content_id"],
        "issued_projection_generated_at": incident[
            "issued_projection_generated_at"
        ],
        "issued_ledger_sha256": incident["issued_ledger_sha256"],
        "issued_ledger_byte_count": incident["issued_ledger_byte_count"],
        "issued_ledger_line_count": incident["issued_ledger_line_count"],
        "entry_count": len(entries),
        "matched_issued_count": len(entries),
        "quarantined_count": len(entries),
        "entries": deepcopy(entries),
        "activation": activation,
    }
    coverage = bound.get("coverage")
    if not isinstance(coverage, dict):
        raise CandidateProjectionError("candidate queue coverage is invalid")
    if "historical_candidate_suppression" in coverage:
        raise CandidateProjectionError(
            "candidate issuance correction cannot claim historical non-issuance"
        )
    coverage["historical_candidate_issuance_correction"] = receipt
    source_content_ids = bound.get("source_content_ids")
    if not isinstance(source_content_ids, list):
        raise CandidateProjectionError("candidate queue source content ids are invalid")
    if any(
        isinstance(value, str)
        and value.startswith(HISTORICAL_SUPPRESSION_SOURCE_PREFIX)
        for value in source_content_ids
    ):
        raise CandidateProjectionError(
            "candidate issuance correction cannot retain a non-issuance source id"
        )
    source_content_ids.append(ISSUANCE_CORRECTION_SOURCE_PREFIX + manifest_sha256)
    bound["source_content_ids"] = sorted(set(source_content_ids))
    freshness = bound.get("freshness")
    if not isinstance(freshness, dict):
        raise CandidateProjectionError("candidate queue freshness is invalid")
    active_rows = [*candidates, *recently_matured]
    if active_rows:
        freshness["exact_candidate_availability"] = "available"
        freshness["reason"] = (
            f"Forward-eligible exact candidates are available. {len(entries)} historical rows "
            "issued contrary to the prior reviewed do-not-backfill decision remain "
            "in the immutable audit ledger and are quarantined from active surfaces."
        )
    else:
        freshness[
            "exact_candidate_availability"
        ] = "quarantined_historical_issuance"
        freshness["reason"] = (
            f"No forward-eligible candidate was observed. {len(entries)} historical rows issued "
            "contrary to the prior reviewed do-not-backfill decision remain in the "
            "immutable audit ledger and are quarantined from active candidate surfaces "
            "by an exact correction receipt."
        )
    limitations = bound.get("limitations")
    if not isinstance(limitations, list):
        raise CandidateProjectionError("candidate queue limitations are invalid")
    limitations.append(
        "The exact corrected rows remain in the immutable audit ledger but are excluded from active candidate, Prophet, ranking, sizing, gating, signal, candidate-add, and escalation surfaces."
    )
    bound["content_id"] = candidate_queue_content_id(bound)
    if not is_valid_candidate_queue(bound):
        raise CandidateProjectionError(
            "candidate queue is invalid after issuance-correction disclosure"
        )
    return bound


def _queue_bound_to_immutable_ledger(
    queue: Mapping[str, Any], ledger: LedgerSnapshot
) -> tuple[dict[str, Any], str]:
    """Replace current rows with their immutable issuance rows and re-address queue.

    Candidate observations contain ``generated_at``, and their
    ``observation_id`` additionally folds in the reviewed-graph digest.  A later
    run therefore rediscovers a known candidate with a new envelope clock and,
    after any curation edit, a new observation identity as well.  The ledger is
    the historical authority for the *candidate*, so the current queue retains
    the issuance row rather than silently retiming or re-issuing it.  First-seen
    candidates are already present in ``ledger`` because the caller appended
    their canonical rows first.
    """
    bound = deepcopy(dict(queue))
    by_observation_key = _ledger_by_observation_key(ledger)
    latest_by_candidate = _latest_ledger_observations(ledger)
    for collection_name in ("candidates", "recently_matured"):
        rows = bound.get(collection_name, [])
        if not isinstance(rows, list):
            raise CandidateProjectionError(f"candidate queue {collection_name} is invalid")
        rebound_rows: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping):
                raise CandidateProjectionError(
                    f"candidate queue {collection_name} row {index} is invalid"
                )
            ledger_row = _bound_ledger_observation(
                row,
                by_observation_key=by_observation_key,
                latest_by_candidate=latest_by_candidate,
                label=f"candidate queue {collection_name} row {index}",
            )
            if ledger_row is None:
                raise CandidateProjectionError(
                    f"candidate queue {collection_name} is not bound to the candidate ledger"
                )
            rebound_rows.append(deepcopy(ledger_row))
        bound[collection_name] = rebound_rows
    if "content_id" not in bound:
        raise CandidateProjectionError("candidate queue lacks the canonical content_id field")
    try:
        bound["content_id"] = candidate_queue_content_id(bound)
    except ValueError as exc:
        raise CandidateProjectionError("candidate queue content id cannot be recomputed") from exc
    if not is_valid_candidate_queue(bound):
        raise CandidateProjectionError("candidate queue is invalid after immutable-ledger binding")
    content_id = _queue_content_id(bound)
    _assert_queue_ledger_binding(bound, ledger)
    return bound, content_id


def _ledger_state(
    *,
    inputs: CandidateProjectionInputs,
    queue: Mapping[str, Any],
    queue_content_id: str,
    prior: LedgerSnapshot,
    ledger: LedgerSnapshot,
    append_count: int,
) -> dict[str, Any]:
    return {
        "contract": STATE_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "generated_at": inputs.generated_at,
        "as_of": _normalized_instant(queue.get("as_of"), label="candidate queue as_of"),
        "known_at": _normalized_instant(queue.get("known_at"), label="candidate queue known_at"),
        "queue_content_id": queue_content_id,
        "latest_sha256": inputs.latest_sha256,
        "workspace_bundle_id": inputs.workspace_bundle_id,
        "workspace_sha256": inputs.workspace_sha256,
        "recipient_graph_id": inputs.recipient_graph_id,
        "recipient_graph_digest": inputs.recipient_graph_digest,
        "ledger": {
            "sha256": ledger.sha256,
            "byte_count": ledger.byte_count,
            "line_count": ledger.line_count,
            "prior_sha256": prior.sha256,
            "prior_byte_count": prior.byte_count,
            "prior_line_count": prior.line_count,
            "append_count": append_count,
        },
    }


def _projection_status(
    *,
    inputs: CandidateProjectionInputs,
    queue: Mapping[str, Any],
    queue_content_id: str,
    ledger: LedgerSnapshot,
    source_health: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = queue.get("candidates")
    backlog = queue.get("mapping_backlog")
    if not isinstance(candidates, list) or not isinstance(backlog, list):
        raise CandidateProjectionError("candidate queue cannot supply publication counts")
    return {
        "contract": STATUS_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        # Publication integrity is independent from upstream source freshness.
        # A valid zero-candidate projection is a successful, honest artifact.
        "status": "ok",
        "generated_at": inputs.generated_at,
        "as_of": _normalized_instant(queue.get("as_of"), label="candidate queue as_of"),
        "known_at": _normalized_instant(queue.get("known_at"), label="candidate queue known_at"),
        "queue_content_id": queue_content_id,
        "candidate_count": len(candidates),
        "mapping_backlog_count": len(backlog),
        "latest_sha256": inputs.latest_sha256,
        "workspace_bundle_id": inputs.workspace_bundle_id,
        "recipient_graph_id": inputs.recipient_graph_id,
        "recipient_graph_digest": inputs.recipient_graph_digest,
        "ledger_sha256": ledger.sha256,
        "ledger_byte_count": ledger.byte_count,
        "ledger_line_count": ledger.line_count,
        "source_health": dict(source_health),
        "authority": dict(_AUTHORITY),
    }


def _atomic_write_bytes(path: Path, raw: bytes) -> None:
    """Atomically replace one artifact after all generation checks have passed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _artifact_paths(root: Path) -> dict[str, Path]:
    canonical_dir = root / DATA_DIRECTORY
    return {
        "ledger": canonical_dir / LEDGER_FILENAME,
        "queue": canonical_dir / QUEUE_FILENAME,
        "state": canonical_dir / STATE_FILENAME,
        "status": canonical_dir / STATUS_FILENAME,
        "public_queue": root / PUBLIC_DIRECTORY / PUBLIC_QUEUE_FILENAME,
    }


def _validate_status_binding(
    status: Mapping[str, Any],
    *,
    inputs: CandidateProjectionInputs,
    queue: Mapping[str, Any],
    queue_content_id: str,
    ledger: LedgerSnapshot,
) -> None:
    if set(status) != _STATUS_FIELDS:
        raise CandidateProjectionError("candidate projection status has an invalid field set")
    if (
        status.get("contract") != STATUS_CONTRACT
        or status.get("schema_version") != SCHEMA_VERSION
        or status.get("status") != "ok"
    ):
        raise CandidateProjectionError("candidate projection status has an invalid contract")
    for clock in ("as_of", "known_at", "generated_at"):
        if status.get(clock) != queue.get(clock):
            raise CandidateProjectionError("candidate projection status clock mismatch")
        _normalized_instant(status.get(clock), label=f"candidate projection status {clock}")
    if (
        status.get("queue_content_id") != queue_content_id
        or status.get("latest_sha256") != inputs.latest_sha256
        or status.get("workspace_bundle_id") != inputs.workspace_bundle_id
        or status.get("recipient_graph_id") != inputs.recipient_graph_id
        or status.get("recipient_graph_digest") != inputs.recipient_graph_digest
        or status.get("ledger_sha256") != ledger.sha256
        or status.get("ledger_byte_count") != ledger.byte_count
        or status.get("ledger_line_count") != ledger.line_count
    ):
        raise CandidateProjectionError("candidate projection status binding mismatch")
    _validate_authority(status.get("authority"), label="candidate projection status authority")
    if status.get("source_health") != _queue_source_health(queue):
        raise CandidateProjectionError("candidate projection status source health mismatch")
    candidates = queue.get("candidates")
    backlog = queue.get("mapping_backlog")
    if (
        not isinstance(candidates, list)
        or not isinstance(backlog, list)
        or status.get("candidate_count") != len(candidates)
        or status.get("mapping_backlog_count") != len(backlog)
    ):
        raise CandidateProjectionError("candidate projection status count mismatch")


def verify_candidate_artifacts(
    root: Path = _repo_root(),
    *,
    mirror_public: bool = False,
    require_historical_suppression_manifest: bool = False,
) -> dict[str, Any]:
    """Verify one persisted candidate generation without advancing any clocks.

    Generic render/site-only callers use this read-only fence.  With
    ``mirror_public=True`` it can repair a missing/stale public half *only*
    after the canonical queue, ledger, state, status, and their current source
    bindings have all passed.  It never rebuilds observations or appends a
    ledger row.
    """
    root = root.resolve()
    if require_historical_suppression_manifest:
        try:
            if load_candidate_historical_suppression_manifest(root) is None:
                raise ValueError("candidate suppression manifest is required")
        except ValueError as exc:
            raise CandidateProjectionError(
                "candidate historical suppression manifest is invalid"
            ) from exc
    paths = _artifact_paths(root)
    exists = {name: path.exists() for name, path in paths.items()}
    if not any(exists.values()):
        return {"status": "absent"}
    canonical_names = ("ledger", "queue", "state", "status")
    if not all(exists[name] for name in canonical_names):
        raise CandidateProjectionError("candidate projection rail is partial")
    if not mirror_public and not exists["public_queue"]:
        raise CandidateProjectionError("candidate projection public twin is absent")

    queue_raw, queue = _read_json_object(paths["queue"], label="canonical candidate queue")
    _state_raw, state = _read_json_object(paths["state"], label="candidate projection state")
    _status_raw, status = _read_json_object(paths["status"], label="candidate projection status")
    ledger = load_candidate_ledger(paths["ledger"])
    if not is_valid_candidate_queue(queue):
        raise CandidateProjectionError("canonical candidate queue violates its contract")
    queue_content_id = _queue_content_id(queue)
    if "content_id" not in queue:
        raise CandidateProjectionError("canonical candidate queue lacks content_id")
    try:
        if candidate_queue_content_id(queue) != queue_content_id:
            raise CandidateProjectionError("canonical candidate queue content id is detached")
    except ValueError as exc:
        raise CandidateProjectionError("canonical candidate queue content id cannot be recomputed") from exc
    _validate_authority(queue.get("authority"), label="canonical candidate queue authority")
    _validate_ledger_state_binding(state, ledger)
    state_generated_at = _normalized_instant(
        state.get("generated_at"), label="candidate projection state generated_at"
    )
    inputs = validate_candidate_projection_inputs(root, generated_at=state_generated_at)
    current_observations = build_candidate_observations(
        inputs.latest,
        inputs.recipient_graph,
        generated_at=inputs.generated_at,
    )
    if not isinstance(current_observations, list):
        raise CandidateProjectionError(
            "current candidate observation engine returned a non-list"
        )
    for clock in ("as_of", "known_at", "generated_at"):
        if state.get(clock) != queue.get(clock):
            raise CandidateProjectionError("candidate projection state clock mismatch")
    if (
        state.get("queue_content_id") != queue_content_id
        or state.get("latest_sha256") != inputs.latest_sha256
        or state.get("workspace_bundle_id") != inputs.workspace_bundle_id
        or state.get("workspace_sha256") != inputs.workspace_sha256
        or state.get("recipient_graph_id") != inputs.recipient_graph_id
        or state.get("recipient_graph_digest") != inputs.recipient_graph_digest
    ):
        raise CandidateProjectionError("candidate projection state source binding mismatch")
    # Rows the persisted generation did not append were issued under an earlier
    # reviewed-graph generation and keep it.  ``_validate_ledger_state_binding``
    # has already proved this prefix against the ledger's own bytes.
    _assert_candidate_source_binding(
        queue,
        inputs=inputs,
        issued_observation_ids=frozenset(
            row["observation_id"]
            for row in ledger.observations[: state["ledger"]["prior_line_count"]]
        ),
    )
    try:
        validate_candidate_reviewed_history_binding(
            queue,
            state,
            root=root,
            allow_exact_legacy_predecessor=True,
            allow_exact_incident_predecessor=False,
            current_observations=current_observations,
            issued_observations=ledger.observations,
            require_manifest=require_historical_suppression_manifest,
            queue_raw_sha256=sha256(queue_raw).hexdigest(),
            projection_state_raw_sha256=sha256(_state_raw).hexdigest(),
        )
    except ValueError as exc:
        raise CandidateProjectionError(
            "candidate reviewed-history binding is invalid"
        ) from exc
    _assert_queue_ledger_binding(queue, ledger)
    counts = queue.get("counts")
    candidates = queue.get("candidates")
    backlog = queue.get("mapping_backlog")
    if (
        not isinstance(counts, Mapping)
        or not isinstance(candidates, list)
        or not isinstance(backlog, list)
        or counts.get("total") != len(candidates)
        or counts.get("exact_linked") != len(candidates)
        or counts.get("mapping_needed") != len(backlog)
    ):
        raise CandidateProjectionError("candidate queue count mismatch")
    for index, row in enumerate(backlog, start=1):
        if not isinstance(row, Mapping) or "observation_id" in row or row.get("issuer_attribution") != "not_asserted":
            raise CandidateProjectionError(f"candidate queue mapping backlog row {index} is invalid")
    _validate_status_binding(
        status,
        inputs=inputs,
        queue=queue,
        queue_content_id=queue_content_id,
        ledger=ledger,
    )

    if mirror_public:
        _atomic_write_bytes(paths["public_queue"], queue_raw)
    try:
        public_raw = paths["public_queue"].read_bytes()
    except OSError as exc:
        raise CandidateProjectionError("candidate projection public twin is unavailable") from exc
    if public_raw != queue_raw:
        raise CandidateProjectionError("candidate projection canonical/public queue twins differ")
    return {
        "status": "ok",
        "generated_at": state["generated_at"],
        "as_of": state["as_of"],
        "known_at": state["known_at"],
        "queue_content_id": queue_content_id,
        "candidate_count": len(candidates),
        "mapping_backlog_count": len(backlog),
        "ledger": dict(state["ledger"]),
    }


def project_candidate_artifacts(
    root: Path = _repo_root(),
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Append unseen candidate observations and atomically publish one generation.

    This is the public writer entrypoint.  It performs every source, prior
    ledger, lineage, queue, and authority validation before it touches an
    output path.  ``generated_at`` is intentionally caller supplied so the
    serialized live lane and tests share one immutable run clock.
    """
    root = root.resolve()
    inputs = validate_candidate_projection_inputs(root, generated_at=generated_at)
    prior, prior_state, prior_queue = _load_prior_ledger_and_state(root)
    observations, queue, queue_content_id, source_health = _current_projection(inputs)
    # An observation is new when its hypothesis and its knowable moment are new --
    # never merely because the reviewed graph was re-curated underneath it.  A
    # candidate already in the ledger stays exactly where it is, so a graph edit
    # cannot re-present frozen history as unseen and then have it refused by the
    # anti-backfill gate below for being older than the run that published it.
    seen_observations = set(_ledger_by_observation_key(prior))
    issued_source_keys = frozenset(
        historical_suppression_entry_key(
            candidate_historical_suppression_entry(row)
        )
        for row in prior.observations
    )
    unseen = [
        row
        for row in observations
        if _observation_key(row, label="current candidate observation") not in seen_observations
    ]
    if prior_state is not None:
        prior_frozen_at = _instant(
            prior_state.get("generated_at"),
            label="prior candidate projection generated_at",
        )
        current_frozen_at = _instant(inputs.generated_at, label="generated_at")
        if current_frozen_at < prior_frozen_at:
            raise CandidateProjectionError(
                "candidate projection generated_at cannot move backward"
            )
    appended, suppressed = _match_historical_suppressions(
        inputs=inputs,
        unseen=unseen,
        issued_source_keys=issued_source_keys,
        prior_state=prior_state,
        prior_queue=prior_queue,
    )
    corrected_rows: list[dict[str, Any]] = []
    if inputs.issuance_correction_manifest is not None:
        corrected_rows = _issuance_correction_rows(
            inputs=inputs,
            prior=prior,
            prior_queue=prior_queue,
        )
        queue = _apply_issuance_correction_receipt(
            queue,
            inputs=inputs,
            corrected_rows=corrected_rows,
            prior_queue=prior_queue,
        )
    else:
        queue = _apply_historical_suppression_receipt(
            queue,
            inputs=inputs,
            suppressed=suppressed,
            prior_queue=prior_queue,
        )
    queue_content_id = _queue_content_id(queue)
    append_raw = b"".join(_canonical_bytes(row) + b"\n" for row in appended)
    ledger = _ledger_from_bytes(prior.raw + append_raw, label="next candidate ledger")
    queue, queue_content_id = _queue_bound_to_immutable_ledger(queue, ledger)
    _assert_candidate_source_binding(
        queue,
        inputs=inputs,
        issued_observation_ids=frozenset(row["observation_id"] for row in prior.observations),
    )
    queue_raw = _canonical_bytes(queue)
    state = _ledger_state(
        inputs=inputs,
        queue=queue,
        queue_content_id=queue_content_id,
        prior=prior,
        ledger=ledger,
        append_count=len(appended),
    )
    _validate_ledger_state_binding(state, ledger)
    try:
        validate_candidate_reviewed_history_binding(
            queue,
            state,
            root=root,
            allow_exact_legacy_predecessor=False,
            allow_exact_incident_predecessor=False,
            current_observations=observations,
            issued_observations=ledger.observations,
            require_exact_activation=bool(
                inputs.historical_suppression_manifest is not None
                and inputs.issuance_correction_manifest is None
                and _prior_suppression_receipt(prior_queue) is None
            ),
            require_manifest=bool(
                inputs.historical_suppression_manifest is not None
                or inputs.issuance_correction_manifest is not None
            ),
        )
    except ValueError as exc:
        raise CandidateProjectionError(
            "candidate reviewed-history binding is invalid"
        ) from exc
    status = _projection_status(
        inputs=inputs,
        queue=queue,
        queue_content_id=queue_content_id,
        ledger=ledger,
        source_health=source_health,
    )
    if set(status) != _STATUS_FIELDS or status["authority"] != _AUTHORITY:
        raise CandidateProjectionError("candidate projection status contract is invalid")
    state_raw = _canonical_bytes(state)
    status_raw = _canonical_bytes(status)

    canonical_dir = root / DATA_DIRECTORY
    public_dir = root / PUBLIC_DIRECTORY
    ledger_path = canonical_dir / LEDGER_FILENAME
    queue_path = canonical_dir / QUEUE_FILENAME
    state_path = canonical_dir / STATE_FILENAME
    status_path = canonical_dir / STATUS_FILENAME
    public_queue_path = public_dir / PUBLIC_QUEUE_FILENAME
    # Do not replace an unchanged ledger.  This is stronger than merely writing
    # identical bytes: every pre-existing byte keeps its inode-level history.
    if not ledger_path.exists() or append_raw:
        _atomic_write_bytes(ledger_path, ledger.raw)
    _atomic_write_bytes(queue_path, queue_raw)
    _atomic_write_bytes(state_path, state_raw)
    _atomic_write_bytes(status_path, status_raw)
    _atomic_write_bytes(public_queue_path, queue_raw)
    try:
        if queue_path.read_bytes() != public_queue_path.read_bytes():
            raise CandidateProjectionError("canonical/public candidate queue twins differ after publication")
    except OSError as exc:
        raise CandidateProjectionError(
            "canonical/public candidate queue twins are unavailable after publication"
        ) from exc
    return {
        "status": "ok",
        "generated_at": inputs.generated_at,
        "as_of": state["as_of"],
        "known_at": state["known_at"],
        "queue_content_id": queue_content_id,
        "candidate_count": status["candidate_count"],
        "mapping_backlog_count": status["mapping_backlog_count"],
        "append_count": len(appended),
        "suppressed_historical_count": len(suppressed),
        "quarantined_issuance_count": len(corrected_rows),
        "ledger": dict(state["ledger"]),
        "paths": {
            "ledger": str(ledger_path),
            "queue": str(queue_path),
            "state": str(state_path),
            "status": str(status_path),
            "public_queue": str(public_queue_path),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_repo_root(), help="repository root")
    parser.add_argument(
        "--generated-at",
        default=_now_iso(),
        help="frozen ISO-8601 writer clock (default: current UTC instant)",
    )
    args = parser.parse_args(argv)
    print(_canonical_json(project_candidate_artifacts(args.root, generated_at=args.generated_at)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
