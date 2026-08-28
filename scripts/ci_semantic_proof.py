#!/usr/bin/env python3
"""Canonical, dependency-free law for CI semantic proof.

Transport jobs report bounded raw observations.  This module is the only place
that turns those observations into causality, validates the final artifact, or
matches later descendant evidence.  It deliberately knows nothing about GitHub
API clients, product code, or pack scheduling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


PLAN_SCHEMA = "ci.pack_plan.v2"
FRAGMENT_SCHEMA = "ci.semantic_fragment.v1"
EVIDENCE_SCHEMA = "ci.semantic_evidence.v1"

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_PROOF_ID = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")
_PYTEST_ATOM = re.compile(r"^(FAILED|ERROR)\s+([^\s]+)(?:\s+-\s+(.*))?$")
_ANNOTATION = re.compile(r"^::error(?:\s+([^:]*))?::(.*)$")
_MAX_DETAIL_BYTES = 1024
_MAX_JSON_BYTES = 8 * 1024 * 1024
_LOGICAL_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")

_PLAN_DOCUMENT_KEYS = {
    "schema",
    "workflow_run_id",
    "workflow",
    "event",
    "role",
    "tested_tree_sha",
    "subject_head_sha",
    "base_sha",
    "authority_changed",
    "changed_from",
    "scope_mode",
    "reason",
    "scope_summary",
    "legacy_job_count",
    "eligible_job_count",
    "eligible_jobs",
    "skipped_job_count",
    "skipped_jobs",
    "packs",
    "nonempty_pack_indices",
    "matrix",
    "has_work",
    "semantic_jobs",
    "plan_sha256",
    "changed_files_sha256",
    "changed_files_count",
}
_PLAN_PACK_KEYS = {"index", "weight", "jobs"}
_PLAN_SEMANTIC_JOB_KEYS = {
    "logical_job_id",
    "pack_index",
    "job_exec_sha256",
    "steps",
}
_PLAN_SEMANTIC_STEP_KEYS = {"proof_id", "step_spec_sha256"}


class SemanticProofError(ValueError):
    """Semantic evidence is malformed, contradictory, or identity-mismatched."""


def _bounded_text(value: object, limit: int = _MAX_DETAIL_BYTES) -> str:
    text = " ".join(str(value).replace("\x00", "").split())
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= limit:
        return text
    suffix = b"...[truncated]"
    return (encoded[: max(0, limit - len(suffix))] + suffix).decode(
        "utf-8", "ignore"
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _strict_json_load(path: Path) -> Any:
    try:
        if path.stat().st_size > _MAX_JSON_BYTES:
            raise SemanticProofError(
                f"semantic JSON exceeds {_MAX_JSON_BYTES} byte bound: {path}"
            )
        return parse_semantic_json(path.read_bytes())
    except SemanticProofError:
        raise
    except OSError as exc:
        raise SemanticProofError(f"cannot read {path}: {exc}") from exc


def parse_semantic_json(raw: bytes | str) -> Mapping[str, Any]:
    """Strict UTF-8/object decoder shared by every artifact consumer."""
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SemanticProofError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        text = raw.decode("utf-8", "strict") if isinstance(raw, bytes) else raw
        value = json.loads(text, object_pairs_hook=reject_duplicate)
        return _object(value, "semantic JSON")
    except SemanticProofError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticProofError(f"semantic JSON is malformed: {exc}") from exc


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticProofError(f"{label} must be a JSON object")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SemanticProofError(f"{label} must be a JSON array")
    return value


def _string(value: object, label: str, *, nonempty: bool = True) -> str:
    if type(value) is not str or (nonempty and not value):
        raise SemanticProofError(f"{label} must be a{' non-empty' if nonempty else ''} string")
    return value


def _sha(value: object, label: str, *, size: int) -> str:
    text = _string(value, label).lower()
    pattern = _SHA40 if size == 40 else _SHA64
    if not pattern.fullmatch(text):
        raise SemanticProofError(f"{label} must be a lowercase {size}-hex digest")
    return text


def normalize_proof_id(value: object) -> str:
    text = unicodedata.normalize("NFC", _string(value, "proof_id"))
    text = " ".join(text.split())
    if not _PROOF_ID.fullmatch(text):
        raise SemanticProofError("proof_id is empty, too long, or contains controls")
    return text


def _logical_job_id(value: object, label: str = "logical_job_id") -> str:
    text = _string(value, label)
    if not _LOGICAL_JOB_ID.fullmatch(text):
        raise SemanticProofError(f"{label} is not a safe stable logical-job ID")
    return text


def effective_proof_id(step: Mapping[str, Any]) -> str:
    """Return explicit proof_id, else the normalized non-empty display name."""
    if not isinstance(step, Mapping):
        raise SemanticProofError("semantic step must be an object")
    source = step.get("proof_id") if "proof_id" in step else step.get("name")
    return normalize_proof_id(source)


def step_spec_sha256(step: Mapping[str, Any]) -> str:
    """Digest execution semantics without conflating them with display identity."""
    if type(step.get("run")) is not str or not step["run"]:
        raise SemanticProofError("semantic step must have a non-empty run command")
    execution = {"run": step["run"]}
    # Preserve any future execution-relevant keys without hashing presentation.
    for key in ("env", "if", "shell", "timeout-minutes", "working-directory"):
        if key in step:
            execution[key] = step[key]
    return canonical_sha256(execution)


def job_exec_sha256(
    *,
    dependency_install_command: str | None,
    timeout_minutes: object,
    runner_contract: str,
) -> str:
    return canonical_sha256(
        {
            "dependency_install_command": dependency_install_command,
            "timeout_minutes": timeout_minutes,
            "runner_contract": runner_contract,
        }
    )


class FailureAtomCollector:
    """Incrementally retain only bounded stable failure atoms."""

    def __init__(self, *, max_bytes: int, max_atoms: int, max_line_bytes: int):
        if min(max_bytes, max_atoms, max_line_bytes) < 1:
            raise SemanticProofError("failure collector bounds must be positive")
        self.max_bytes = max_bytes
        self.max_atoms = max_atoms
        self.max_line_bytes = max_line_bytes
        self._accepted_bytes = 0
        self._atoms: set[str] = set()
        self._incomplete = False

    def feed(self, raw: bytes | str, *, truncated: bool = False) -> None:
        data = raw.encode("utf-8", "replace") if isinstance(raw, str) else bytes(raw)
        overlong = truncated or len(data) > self.max_line_bytes
        data = data[: self.max_line_bytes]
        text = data.decode("utf-8", "replace").rstrip("\r\n")
        if overlong:
            # A recognized atom whose unseen tail differs must never compare
            # equal merely because the transport retained the same prefix.
            # Ordinary long progress lines remain irrelevant and spend no
            # semantic budget.
            if text.startswith(("FAILED ", "ERROR ", "::error")):
                self._incomplete = True
            return
        pytest_match = _PYTEST_ATOM.fullmatch(text)
        if pytest_match:
            kind, nodeid, reason = pytest_match.groups()
            atom = f"pytest:{kind.lower()}:{_bounded_text(nodeid, 768)}"
            if reason:
                # Different assertions/exceptions inside one broad pytest
                # invocation must not collapse merely because the nodeid is the
                # same. Keep only a bounded digest of the normalized summary.
                atom += ":reason=" + hashlib.sha256(
                    _bounded_text(reason, 768).encode("utf-8")
                ).hexdigest()
            self._accept_atom(atom)
            return
        annotation = _ANNOTATION.fullmatch(text)
        if not annotation:
            return
        metadata, message = annotation.groups()
        fields: dict[str, str] = {}
        for item in (metadata or "").split(","):
            key, separator, value = item.partition("=")
            if separator:
                fields[key.strip().lower()] = value.strip()
        title = _bounded_text(fields.get("title", ""), 256)
        # The pack wrapper merely repeats an exit code and has no causal identity.
        if title.startswith("legacy-job-"):
            return
        normalized = _bounded_text(message, 768)
        if not title and not normalized:
            return
        stable = {"title": title, "message": normalized}
        atom = "github_error:" + canonical_sha256(stable)
        self._accept_atom(atom)

    def _accept_atom(self, atom: str) -> None:
        """Bound retained atom bytes; benign streamed output spends no budget."""
        if atom in self._atoms:
            return
        if len(self._atoms) >= self.max_atoms:
            self._incomplete = True
            return
        size = len(atom.encode("utf-8"))
        if self._accepted_bytes + size > self.max_bytes:
            self._incomplete = True
            return
        self._atoms.add(atom)
        self._accepted_bytes += size

    def signature(self) -> dict[str, Any] | None:
        if not self._atoms or self._incomplete:
            return None
        atoms = sorted(self._atoms)[: self.max_atoms]
        return {"atoms": atoms, "sha256": canonical_sha256(atoms)}


@dataclass(frozen=True)
class LoadedSemanticEvidence:
    mode: str
    evidence: Mapping[str, Any] | None


@dataclass(frozen=True)
class SemanticUnit:
    logical_job_id: str
    proof_id: str
    classification: str
    outcome: str
    pack_index: int
    step_spec_sha256: str
    job_exec_sha256: str
    failure_signature: object
    detail: str | None
    base_sha: str
    head_sha: str


@dataclass(frozen=True)
class SemanticGateVerdict:
    clear: bool
    blocking: tuple[SemanticUnit, ...]
    inherited: tuple[SemanticUnit, ...]
    passed: tuple[SemanticUnit, ...]
    infrastructure_blocking: bool


@dataclass(frozen=True)
class DescendantWitness:
    workflow_run_id: int | str
    tested_tree_sha: str
    old_step_spec_sha: str
    witness_step_spec_sha: str
    contract_changed: bool


_STEP_OUTCOMES = {
    "passed",
    "failed",
    "timed_out",
    "not_run_prior_failure",
    "infrastructure_blocked",
}
_CLASSIFICATIONS = {
    "passed",
    "inherited_base",
    "pr_regression",
    "pr_ci_contract_change",
    "unknown",
    "main_failure",
}
_INFRASTRUCTURE_OUTCOMES = {
    "passed",
    "unknown",
    "dependency_failed",
    "runner_startup_failed",
    "missing",
    "planner_failure",
    "planner_configuration_failure",
    "missing_pack_fragment",
    "authority_self_excuse_refused",
    "timed_out",
    "unavailable",
    # Used only to express a sibling failure while proving a descendant PASS.
    "unrelated_red",
}


def _infrastructure_row(
    value: object,
    label: str,
    *,
    allow_positions: bool,
) -> dict[str, Any]:
    row = _object(value, label)
    allowed = {"outcome", "detail"}
    if allow_positions:
        allowed.update({"pack_index", "pack_indices"})
    if set(row) - allowed:
        raise SemanticProofError(f"{label} contains unsupported fields")
    outcome = _string(row.get("outcome"), f"{label} outcome")
    if outcome not in _INFRASTRUCTURE_OUTCOMES:
        raise SemanticProofError(f"{label} outcome {outcome!r} is unsupported")
    normalized: dict[str, Any] = {"outcome": outcome}
    if "detail" in row:
        detail = _string(row.get("detail"), f"{label} detail", nonempty=False)
        normalized["detail"] = _bounded_text(detail)
    if "pack_index" in row:
        pack_index = row.get("pack_index")
        if type(pack_index) is not int or pack_index < 0:
            raise SemanticProofError(f"{label} pack_index is invalid")
        normalized["pack_index"] = pack_index
    if "pack_indices" in row:
        pack_indices = _array(row.get("pack_indices"), f"{label} pack_indices")
        if (
            len(pack_indices) > 256
            or any(type(index) is not int or index < 0 for index in pack_indices)
            or pack_indices != sorted(set(pack_indices))
        ):
            raise SemanticProofError(f"{label} pack_indices is invalid")
        normalized["pack_indices"] = pack_indices
    return normalized


def _same_failure(left: object, right: object) -> bool:
    left_signature = _failure_signature(left, "head failure_signature")
    right_signature = _failure_signature(right, "base failure_signature")
    if left_signature is None or right_signature is None:
        return False
    return _canonical_bytes(left_signature) == _canonical_bytes(right_signature)


def _failure_signature(value: object, label: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    signature = _object(value, label)
    if set(signature) != {"atoms", "sha256"}:
        raise SemanticProofError(f"{label} must contain exactly atoms and sha256")
    atoms = _array(signature.get("atoms"), f"{label} atoms")
    if not (1 <= len(atoms) <= 64):
        raise SemanticProofError(f"{label} must contain 1..64 atoms")
    normalized: list[str] = []
    for atom in atoms:
        text = _string(atom, f"{label} atom")
        if len(text.encode("utf-8")) > 1024 or any(
            unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            for character in text
        ):
            raise SemanticProofError(f"{label} atom is unsafe or too long")
        normalized.append(text)
    if normalized != sorted(set(normalized)):
        raise SemanticProofError(f"{label} atoms must be sorted and unique")
    receipt = _sha(signature.get("sha256"), f"{label} sha256", size=64)
    if receipt != canonical_sha256(normalized):
        raise SemanticProofError(f"{label} digest mismatch")
    return {"atoms": normalized, "sha256": receipt}


def _base_step(replay: Mapping[str, Any], proof_id: str) -> Mapping[str, Any] | None:
    steps = replay.get("steps")
    if not isinstance(steps, list):
        return None
    found = [step for step in steps if isinstance(step, Mapping) and step.get("proof_id") == proof_id]
    if len(found) > 1:
        raise SemanticProofError(f"base replay duplicates proof_id {proof_id!r}")
    return found[0] if found else None


def _validate_base_replay(
    value: object,
    *,
    expected_base_sha: str,
) -> Mapping[str, Any]:
    replay = _object(value, "exact-base replay")
    if replay.get("tested_tree_sha") != expected_base_sha:
        raise SemanticProofError("exact-base replay tree identity mismatch")
    if "job_present" not in replay:
        if set(replay) != {"tested_tree_sha", "outcome", "detail"}:
            raise SemanticProofError("unavailable exact-base replay has unsupported fields")
        if replay.get("outcome") not in {"unavailable", "timed_out"}:
            raise SemanticProofError("unavailable exact-base replay outcome is invalid")
        detail = _string(replay.get("detail"), "exact-base replay detail")
        if detail != _bounded_text(detail):
            raise SemanticProofError("exact-base replay detail is not bounded/canonical")
        return replay
    if replay.get("job_present") is False:
        if set(replay) != {"tested_tree_sha", "job_present"}:
            raise SemanticProofError("absent-job exact-base replay has unsupported fields")
        return replay
    if replay.get("job_present") is not True:
        raise SemanticProofError("exact-base replay job_present must be boolean")
    if set(replay) != {
        "tested_tree_sha",
        "job_present",
        "logical_job_id",
        "job_exec_sha256",
        "infrastructure",
        "steps",
    }:
        raise SemanticProofError("exact-base replay has missing or unsupported fields")
    _logical_job_id(replay.get("logical_job_id"), "exact-base logical_job_id")
    _sha(replay.get("job_exec_sha256"), "exact-base job_exec_sha256", size=64)
    infrastructure = _infrastructure_row(
        replay.get("infrastructure"),
        "exact-base infrastructure",
        allow_positions=False,
    )
    if dict(replay["infrastructure"]) != infrastructure:
        raise SemanticProofError("exact-base infrastructure is not canonical")
    raw_steps = _array(replay.get("steps"), "exact-base steps")
    if not raw_steps or len(raw_steps) > 4096:
        raise SemanticProofError("exact-base replay has an invalid step count")
    seen: set[str] = set()
    for raw_step in raw_steps:
        step = _object(raw_step, "exact-base step")
        if set(step) - {
            "proof_id",
            "step_spec_sha256",
            "outcome",
            "failure_signature",
            "detail",
        } or not {
            "proof_id",
            "step_spec_sha256",
            "outcome",
            "failure_signature",
        }.issubset(step):
            raise SemanticProofError("exact-base step has missing or unsupported fields")
        proof_id = normalize_proof_id(step.get("proof_id"))
        if step.get("proof_id") != proof_id or proof_id in seen:
            raise SemanticProofError("exact-base proof identities are noncanonical or duplicated")
        seen.add(proof_id)
        _sha(step.get("step_spec_sha256"), "exact-base step_spec_sha256", size=64)
        if step.get("outcome") not in _STEP_OUTCOMES:
            raise SemanticProofError("exact-base step outcome is invalid")
        _failure_signature(
            step.get("failure_signature"),
            f"exact-base {proof_id} failure_signature",
        )
        if step.get("outcome") == "passed" and step.get("failure_signature") is not None:
            raise SemanticProofError("passed exact-base proof carries a failure signature")
        if "detail" in step:
            detail = _string(step.get("detail"), f"exact-base {proof_id} detail", nonempty=False)
            if detail != _bounded_text(detail):
                raise SemanticProofError("exact-base step detail is not bounded/canonical")
    return replay


def classify_head_failure(
    *,
    logical_job_id: str,
    head_job_exec_sha256: str,
    head_step: Mapping[str, Any],
    expected_base_sha: str,
) -> tuple[str, str]:
    """Apply CEO V2 exact-base Cases A-I to one raw failing head step."""
    replay_value = head_step.get("base_replay")
    if not isinstance(replay_value, Mapping):
        return "unknown", "exact-base replay is absent or unavailable"
    replay = _validate_base_replay(
        replay_value,
        expected_base_sha=expected_base_sha,
    )
    if replay.get("job_present") is False:
        return "pr_ci_contract_change", "logical job is absent on exact base"
    if replay.get("job_present") is not True:
        return "unknown", _bounded_text(replay.get("detail") or "exact-base replay unavailable")
    if replay.get("logical_job_id") != logical_job_id:
        raise SemanticProofError("base replay logical-job identity mismatch")
    if replay["infrastructure"]["outcome"] != "passed":
        return "unknown", "exact-base logical-job infrastructure did not pass"
    base_job_digest = replay.get("job_exec_sha256")
    if base_job_digest != head_job_exec_sha256:
        return "unknown", "logical-job execution/dependency contract differs on base"
    proof_id = _string(head_step.get("proof_id"), "head proof_id")
    base_step = _base_step(replay, proof_id)
    if base_step is None:
        return "pr_ci_contract_change", "semantic proof is absent on exact base"
    if base_step.get("step_spec_sha256") != head_step.get("step_spec_sha256"):
        return "pr_ci_contract_change", "semantic step execution spec differs on exact base"
    base_outcome = base_step.get("outcome")
    if base_outcome == "passed":
        return "pr_regression", "same semantic proof passes on exact base"
    if base_outcome in {"not_run_prior_failure", "infrastructure_blocked", "timed_out"}:
        return "unknown", "exact base did not reach a comparable semantic failure"
    if base_outcome != "failed":
        return "unknown", "exact-base outcome is not comparable"
    head_signature = head_step.get("failure_signature")
    base_signature = base_step.get("failure_signature")
    if head_signature is None or base_signature is None:
        return "unknown", "one or both failure signatures are unavailable"
    if not _same_failure(head_signature, base_signature):
        return "unknown", "head and exact-base failure signatures differ"
    return "inherited_base", "same non-empty failure signature reproduced on exact base"


def _expected_plan(plan: Mapping[str, Any]) -> tuple[dict[tuple[str, str], dict[str, Any]], set[int]]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise SemanticProofError(f"plan schema must be {PLAN_SCHEMA}")
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    packs: set[int] = set()
    job_ids: set[str] = set()
    semantic_jobs = _array(plan.get("semantic_jobs"), "plan semantic_jobs")
    if len(semantic_jobs) > 4096:
        raise SemanticProofError("plan contains too many semantic jobs")
    for raw_job in semantic_jobs:
        job = _object(raw_job, "plan semantic job")
        if set(job) != _PLAN_SEMANTIC_JOB_KEYS:
            raise SemanticProofError(
                "plan semantic job has missing or unsupported fields"
            )
        job_id = _logical_job_id(job.get("logical_job_id"))
        if job_id in job_ids:
            raise SemanticProofError(f"plan duplicates logical job {job_id!r}")
        job_ids.add(job_id)
        pack_index = job.get("pack_index")
        if type(pack_index) is not int or pack_index < 0:
            raise SemanticProofError("pack_index must be a non-negative integer")
        packs.add(pack_index)
        job_digest = _sha(job.get("job_exec_sha256"), "job_exec_sha256", size=64)
        local: set[str] = set()
        raw_steps = _array(job.get("steps"), f"{job_id} steps")
        if not raw_steps or len(raw_steps) > 4096:
            raise SemanticProofError(f"plan {job_id} has an invalid step count")
        for raw_step in raw_steps:
            step = _object(raw_step, "plan semantic step")
            if set(step) != _PLAN_SEMANTIC_STEP_KEYS:
                raise SemanticProofError(
                    "plan semantic step has missing or unsupported fields"
                )
            proof_id = normalize_proof_id(step.get("proof_id"))
            if proof_id in local:
                raise SemanticProofError(f"plan duplicates {job_id}/{proof_id}")
            local.add(proof_id)
            key = (job_id, proof_id)
            expected[key] = {
                "logical_job_id": job_id,
                "proof_id": proof_id,
                "pack_index": pack_index,
                "job_exec_sha256": job_digest,
                "step_spec_sha256": _sha(
                    step.get("step_spec_sha256"), "step_spec_sha256", size=64
                ),
            }
    return expected, packs


def _identity(plan: Mapping[str, Any]) -> dict[str, Any]:
    role = _string(plan.get("role"), "role")
    if role not in {"pr_head", "main"}:
        raise SemanticProofError("role must be pr_head or main")
    event = _string(plan.get("event"), "event")
    if (role, event) not in {("pr_head", "pull_request"), ("main", "workflow_dispatch")}:
        raise SemanticProofError(f"role/event combination {role}/{event} is not authoritative")
    workflow_run_id = _string(str(plan.get("workflow_run_id", "")), "workflow_run_id")
    if not workflow_run_id.isdecimal() or int(workflow_run_id) < 1:
        raise SemanticProofError("workflow_run_id must be a positive decimal integer")
    workflow = _string(plan.get("workflow"), "workflow")
    if workflow != "ci":
        raise SemanticProofError("workflow must be ci")
    identity = {
        "workflow_run_id": workflow_run_id,
        "workflow": workflow,
        "event": event,
        "role": role,
        "tested_tree_sha": _sha(plan.get("tested_tree_sha"), "tested_tree_sha", size=40),
        "subject_head_sha": _sha(plan.get("subject_head_sha"), "subject_head_sha", size=40),
        "base_sha": _sha(plan.get("base_sha"), "base_sha", size=40),
        "plan_sha256": _sha(plan.get("plan_sha256"), "plan_sha256", size=64),
    }
    if "changed_from" in plan:
        if role == "pr_head":
            if plan.get("changed_from") != identity["base_sha"]:
                raise SemanticProofError("PR changed_from must equal exact base_sha")
        elif plan.get("changed_from") is not None or not (
            identity["tested_tree_sha"]
            == identity["subject_head_sha"]
            == identity["base_sha"]
        ):
            raise SemanticProofError(
                "main identity requires one tree/head/base SHA and changed_from=null"
            )
    return identity


def plan_hash_payload_from_document(plan_source: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild exactly the runner's v2 plan-hash payload from its publication."""
    plan = _object(plan_source, "plan")
    if set(plan) != _PLAN_DOCUMENT_KEYS:
        raise SemanticProofError("plan has missing or unsupported fields")
    identity = _identity(plan)
    if plan.get("schema") != PLAN_SCHEMA:
        raise SemanticProofError(f"plan schema must be {PLAN_SCHEMA}")
    authority_changed = plan.get("authority_changed")
    if type(authority_changed) is not bool:
        raise SemanticProofError("plan authority_changed must be boolean")
    changed_from = plan.get("changed_from")
    if changed_from is not None:
        changed_from = _sha(changed_from, "changed_from", size=40)
    scope_mode = _string(plan.get("scope_mode"), "scope_mode")
    if scope_mode not in {"active", "shadow", "off"}:
        raise SemanticProofError("scope_mode must be active, shadow, or off")
    changed_digest = plan.get("changed_files_sha256")
    if changed_digest != "":
        changed_digest = _sha(changed_digest, "changed_files_sha256", size=64)
    changed_count = plan.get("changed_files_count")
    if type(changed_count) is not int or changed_count < 0:
        raise SemanticProofError("changed_files_count must be a non-negative integer")
    if changed_digest == "" and changed_count != 0:
        raise SemanticProofError(
            "an absent changed-file digest must carry changed_files_count=0"
        )
    _string(plan.get("reason"), "reason")
    _string(plan.get("scope_summary"), "scope_summary")
    eligible_jobs = _array(plan.get("eligible_jobs"), "eligible_jobs")
    if len(eligible_jobs) > 4096:
        raise SemanticProofError("eligible_jobs exceeds the bounded job count")
    if any(type(job_id) is not str or not job_id for job_id in eligible_jobs):
        raise SemanticProofError("eligible_jobs must contain non-empty strings")
    if len(eligible_jobs) != len(set(eligible_jobs)):
        raise SemanticProofError("eligible_jobs contains duplicates")
    eligible_count = plan.get("eligible_job_count")
    if type(eligible_count) is not int or eligible_count != len(eligible_jobs):
        raise SemanticProofError("eligible_job_count disagrees with eligible_jobs")
    skipped_jobs = _array(plan.get("skipped_jobs"), "skipped_jobs")
    if (
        any(type(job_id) is not str or not job_id for job_id in skipped_jobs)
        or len(skipped_jobs) != len(set(skipped_jobs))
        or set(eligible_jobs) & set(skipped_jobs)
    ):
        raise SemanticProofError("skipped_jobs is malformed or overlaps eligible_jobs")
    skipped_count = plan.get("skipped_job_count")
    if type(skipped_count) is not int or skipped_count != len(skipped_jobs):
        raise SemanticProofError("skipped_job_count disagrees with skipped_jobs")
    legacy_count = plan.get("legacy_job_count")
    if (
        type(legacy_count) is not int
        or legacy_count != len(eligible_jobs) + len(skipped_jobs)
    ):
        raise SemanticProofError("legacy_job_count disagrees with job inventories")
    raw_packs = _array(plan.get("packs"), "packs")
    if not raw_packs or len(raw_packs) > 256:
        raise SemanticProofError("packs must contain 1..256 entries")
    pack_jobs: list[list[str]] = []
    pack_weights: list[int] = []
    for expected_index, raw_pack in enumerate(raw_packs):
        pack = _object(raw_pack, "pack")
        if set(pack) != _PLAN_PACK_KEYS:
            raise SemanticProofError("pack has missing or unsupported fields")
        if pack.get("index") != expected_index:
            raise SemanticProofError("pack indices must be contiguous and ordered")
        weight = pack.get("weight")
        if type(weight) is not int or weight < 0:
            raise SemanticProofError("pack weight must be a non-negative integer")
        jobs = _array(pack.get("jobs"), "pack jobs")
        if any(type(job_id) is not str or not job_id for job_id in jobs):
            raise SemanticProofError("pack jobs must be non-empty strings")
        pack_jobs.append(list(jobs))
        pack_weights.append(weight)
    flattened = [job_id for jobs in pack_jobs for job_id in jobs]
    if sorted(flattened) != sorted(eligible_jobs) or len(flattened) != len(set(flattened)):
        raise SemanticProofError("pack jobs do not exactly partition eligible_jobs")
    nonempty = [index for index, jobs in enumerate(pack_jobs) if jobs]
    if plan.get("nonempty_pack_indices") != nonempty:
        raise SemanticProofError("nonempty_pack_indices disagrees with packs")
    if plan.get("matrix") != {"include": [{"pack": index} for index in nonempty]}:
        raise SemanticProofError("matrix disagrees with non-empty packs")
    if type(plan.get("has_work")) is not bool or plan["has_work"] != bool(nonempty):
        raise SemanticProofError("has_work disagrees with non-empty packs")
    semantic_jobs = _array(plan.get("semantic_jobs"), "semantic_jobs")
    pack_by_job = {
        job_id: pack_index
        for pack_index, jobs in enumerate(pack_jobs)
        for job_id in jobs
    }
    semantic_ids: list[str] = []
    for raw_job in semantic_jobs:
        job = _object(raw_job, "semantic job")
        if set(job) != _PLAN_SEMANTIC_JOB_KEYS:
            raise SemanticProofError(
                "semantic job has missing or unsupported fields"
            )
        job_id = _logical_job_id(job.get("logical_job_id"), "semantic logical_job_id")
        semantic_ids.append(job_id)
        if job.get("pack_index") != pack_by_job.get(job_id):
            raise SemanticProofError(
                f"semantic job {job_id!r} disagrees with pack membership"
            )
        raw_steps = _array(job.get("steps"), f"semantic job {job_id} steps")
        if not raw_steps:
            raise SemanticProofError(f"semantic job {job_id!r} has no proof steps")
        for raw_step in raw_steps:
            step = _object(raw_step, f"semantic job {job_id} step")
            if set(step) != _PLAN_SEMANTIC_STEP_KEYS:
                raise SemanticProofError(
                    f"semantic job {job_id!r} step has missing or unsupported fields"
                )
    if semantic_ids != list(eligible_jobs) or len(semantic_ids) != len(set(semantic_ids)):
        raise SemanticProofError(
            "semantic job inventory must exactly equal eligible_jobs in plan order"
        )
    return {
        "schema": PLAN_SCHEMA,
        "workflow_run_id": identity["workflow_run_id"],
        "workflow": identity["workflow"],
        "event": identity["event"],
        "role": identity["role"],
        "tested_tree_sha": identity["tested_tree_sha"],
        "subject_head_sha": identity["subject_head_sha"],
        "base_sha": identity["base_sha"],
        "authority_changed": authority_changed,
        "changed_from": changed_from,
        "scope_mode": scope_mode,
        "changed_files_sha256": changed_digest,
        "pack_count": len(raw_packs),
        "eligible_job_ids": list(eligible_jobs),
        "pack_jobs": pack_jobs,
        "pack_weights": pack_weights,
        "semantic_jobs": [dict(_object(job, "semantic job")) for job in semantic_jobs],
    }


def authoritative_plan_sha256(plan_source: Mapping[str, Any]) -> str:
    return canonical_sha256(plan_hash_payload_from_document(plan_source))


def _verify_plan_digest(plan: Mapping[str, Any]) -> None:
    published = _sha(plan.get("plan_sha256"), "plan_sha256", size=64)
    computed = authoritative_plan_sha256(plan)
    if published != computed:
        raise SemanticProofError(
            f"authoritative plan digest mismatch: published {published}, computed {computed}"
        )


_ATTRIBUTED_CLASSIFICATIONS = {
    "inherited_base",
    "pr_regression",
    "pr_ci_contract_change",
    "main_failure",
}


def _step_representation_error(
    job_id: str, step: Mapping[str, Any], role: str
) -> str | None:
    """Mirror the evidence step invariants so one bad unit cannot void a run.

    ``_validate_evidence`` refuses the whole document, and the CLI then replaces
    it with an empty-``jobs`` planner failure.  Every passing sibling job loses
    its evidence that way, so no session can mint a descendant PASS for anything
    in the run.  Detecting the same faults here lets the aggregate keep the jobs
    it can classify and charge the fault to the one job it concerns.
    """
    proof_id = step.get("proof_id")
    outcome = step.get("outcome")
    classification = step.get("classification")
    if outcome not in _STEP_OUTCOMES:
        return f"invalid outcome for {job_id}/{proof_id}"
    if classification not in _CLASSIFICATIONS:
        return f"invalid classification for {job_id}/{proof_id}"
    if (outcome == "passed") != (classification == "passed"):
        return f"evidence outcome/classification mismatch for {job_id}/{proof_id}"
    if classification in _ATTRIBUTED_CLASSIFICATIONS and outcome != "failed":
        return f"evidence classification requires a failure for {job_id}/{proof_id}"
    if role == "main" and classification not in {"passed", "main_failure", "unknown"}:
        return f"main evidence contains a PR-only classification for {job_id}/{proof_id}"
    if role == "pr_head" and classification == "main_failure":
        return f"PR evidence contains a main-only classification for {job_id}/{proof_id}"
    if outcome == "passed" and step.get("failure_signature") is not None:
        return f"passed semantic proof carries a failure signature for {job_id}/{proof_id}"
    return None


def _blocked_step(expected: Mapping[str, Any], detail: str) -> dict[str, Any]:
    return {
        "proof_id": expected["proof_id"],
        "step_spec_sha256": expected["step_spec_sha256"],
        "outcome": "infrastructure_blocked",
        "failure_signature": None,
        "classification": "unknown",
        "detail": _bounded_text(detail),
    }


def reconcile_evidence(
    plan_source: Mapping[str, Any],
    fragments: Sequence[Mapping[str, Any]],
    *,
    planner_outcome: str = "success",
    planner_detail: str | None = None,
) -> dict[str, Any]:
    """Reconcile complete raw pack facts into one canonical final artifact."""
    plan = _object(plan_source, "plan")
    if len(fragments) > 256:
        raise SemanticProofError("semantic fragment count exceeds 256")
    _verify_plan_digest(plan)
    identity = _identity(plan)
    expected, expected_packs = _expected_plan(plan)
    authority_changed = plan.get("authority_changed")
    if type(authority_changed) is not bool:
        raise SemanticProofError("plan authority_changed must be boolean")
    seen_packs: set[int] = set()
    seen_units: dict[tuple[str, str], Mapping[str, Any]] = {}
    observed_jobs: dict[str, Mapping[str, Any]] = {}
    infrastructure: list[dict[str, Any]] = []

    if planner_outcome != "success":
        infrastructure.append(
            {"outcome": "planner_failure", "detail": _bounded_text(planner_detail or planner_outcome)}
        )

    for raw_fragment in fragments:
        fragment = _object(raw_fragment, "semantic fragment")
        if fragment.get("schema") != FRAGMENT_SCHEMA:
            raise SemanticProofError(f"fragment schema must be {FRAGMENT_SCHEMA}")
        if set(fragment) != {
            "schema",
            "workflow_run_id",
            "workflow",
            "event",
            "role",
            "tested_tree_sha",
            "subject_head_sha",
            "base_sha",
            "plan_sha256",
            "pack_index",
            "infrastructure",
            "jobs",
        }:
            raise SemanticProofError("fragment has missing or unsupported fields")
        for key, value in identity.items():
            if fragment.get(key) != value:
                raise SemanticProofError(f"fragment {key} does not match authoritative plan")
        pack_index = fragment.get("pack_index")
        if type(pack_index) is not int or pack_index not in expected_packs:
            raise SemanticProofError(f"fragment pack {pack_index!r} is out of plan")
        if pack_index in seen_packs:
            raise SemanticProofError(f"duplicate fragment for pack {pack_index}")
        seen_packs.add(pack_index)
        fragment_infrastructure = _array(
            fragment.get("infrastructure", []), "fragment infrastructure"
        )
        if len(fragment_infrastructure) > 512:
            raise SemanticProofError("fragment contains too many infrastructure rows")
        for item in fragment_infrastructure:
            row = _infrastructure_row(
                item, "fragment infrastructure row", allow_positions=False
            )
            row["pack_index"] = pack_index
            infrastructure.append(row)
        fragment_jobs = _array(fragment.get("jobs"), "fragment jobs")
        if len(fragment_jobs) > 4096:
            raise SemanticProofError("fragment contains too many jobs")
        for raw_job in fragment_jobs:
            job = _object(raw_job, "fragment job")
            if set(job) != {
                "logical_job_id",
                "job_exec_sha256",
                "infrastructure",
                "steps",
            }:
                raise SemanticProofError("fragment job has missing or unsupported fields")
            job_id = _logical_job_id(
                job.get("logical_job_id"), "fragment logical_job_id"
            )
            expected_job_units = [value for key, value in expected.items() if key[0] == job_id]
            if not expected_job_units or expected_job_units[0]["pack_index"] != pack_index:
                raise SemanticProofError(f"fragment job {job_id!r} is out of plan or wrong pack")
            if job_id in observed_jobs:
                raise SemanticProofError(f"duplicate fragment job {job_id!r}")
            observed_jobs[job_id] = job
            if job.get("job_exec_sha256") != expected_job_units[0]["job_exec_sha256"]:
                raise SemanticProofError(f"fragment job digest mismatch for {job_id}")
            fragment_steps = _array(job.get("steps"), f"fragment {job_id} steps")
            if len(fragment_steps) > 4096:
                raise SemanticProofError(f"fragment {job_id} contains too many steps")
            for raw_step in fragment_steps:
                step = _object(raw_step, "fragment semantic step")
                if set(step) - {
                    "proof_id",
                    "step_spec_sha256",
                    "outcome",
                    "failure_signature",
                    "detail",
                    "base_replay",
                } or not {
                    "proof_id",
                    "step_spec_sha256",
                    "outcome",
                    "failure_signature",
                }.issubset(step):
                    raise SemanticProofError(
                        "fragment semantic step has missing or unsupported fields"
                    )
                proof_id = normalize_proof_id(step.get("proof_id"))
                if step.get("proof_id") != proof_id:
                    raise SemanticProofError("fragment proof_id is not canonical")
                key = (job_id, proof_id)
                if key not in expected:
                    raise SemanticProofError(f"unknown semantic proof {job_id}/{proof_id}")
                if key in seen_units:
                    raise SemanticProofError(f"duplicate semantic proof {job_id}/{proof_id}")
                if step.get("step_spec_sha256") != expected[key]["step_spec_sha256"]:
                    raise SemanticProofError(f"fragment step digest mismatch for {job_id}/{proof_id}")
                outcome = step.get("outcome")
                if outcome not in _STEP_OUTCOMES:
                    raise SemanticProofError(f"invalid outcome for {job_id}/{proof_id}")
                _failure_signature(
                    step.get("failure_signature"),
                    f"fragment {job_id}/{proof_id} failure_signature",
                )
                if outcome == "passed" and step.get("failure_signature") is not None:
                    raise SemanticProofError("passed fragment proof carries a failure signature")
                if "detail" in step:
                    detail = _string(
                        step.get("detail"),
                        f"fragment {job_id}/{proof_id} detail",
                        nonempty=False,
                    )
                    if detail != _bounded_text(detail):
                        raise SemanticProofError("fragment detail is not bounded/canonical")
                if "base_replay" in step:
                    if outcome not in {"failed", "timed_out"}:
                        raise SemanticProofError(
                            "only failed/timed-out fragment proofs may carry base replay"
                        )
                    _validate_base_replay(
                        step.get("base_replay"),
                        expected_base_sha=identity["base_sha"],
                    )
                seen_units[key] = step

    missing_packs = sorted(expected_packs - seen_packs)
    if missing_packs:
        infrastructure.append(
            {"outcome": "missing_pack_fragment", "pack_indices": missing_packs}
        )

    jobs_out: list[dict[str, Any]] = []
    by_job: dict[str, list[dict[str, Any]]] = {}
    for key, item in expected.items():
        job_id, proof_id = key
        raw = seen_units.get(key)
        if raw is None:
            detail = (
                f"pack {item['pack_index']} fragment is missing"
                if item["pack_index"] in missing_packs
                else "expected semantic unit is missing from its fragment"
            )
            result = _blocked_step(item, detail)
        else:
            result = {
                "proof_id": proof_id,
                "step_spec_sha256": item["step_spec_sha256"],
                "outcome": raw["outcome"],
                "failure_signature": raw.get("failure_signature"),
            }
            if raw.get("detail") is not None:
                result["detail"] = _bounded_text(raw["detail"])
            if raw["outcome"] == "passed":
                result["classification"] = "passed"
            elif identity["role"] == "main":
                # A step can go dark (not_run_prior_failure / timed_out /
                # infrastructure_blocked) behind an earlier failing step in
                # the same job without itself having failed. Stamping every
                # non-passed main outcome as main_failure violated the
                # validator's outcome=="failed" requirement for that
                # classification, raising SemanticProofError and voiding the
                # entire aggregate to an empty jobs list -- which in turn
                # blocked every session in the fleet from minting a
                # descendant-PASS witness for any job. Mirror the pr_head
                # guard below: only a genuinely failed outcome earns
                # main_failure, everything else is honestly "unknown".
                result["classification"] = (
                    "main_failure" if raw["outcome"] == "failed" else "unknown"
                )
            elif raw["outcome"] == "failed":
                classification, detail = classify_head_failure(
                    logical_job_id=job_id,
                    head_job_exec_sha256=item["job_exec_sha256"],
                    head_step=raw,
                    expected_base_sha=identity["base_sha"],
                )
                result["classification"] = classification
                result["detail"] = detail
            else:
                result["classification"] = "unknown"
                result.setdefault("detail", "semantic proof did not produce a comparable result")
        by_job.setdefault(job_id, []).append(result)

    expected_job_order = [
        _logical_job_id(job.get("logical_job_id"))
        for job in _array(plan.get("semantic_jobs"), "plan semantic_jobs")
    ]
    for job_id in expected_job_order:
        first = next(item for key, item in expected.items() if key[0] == job_id)
        observed = observed_jobs.get(job_id)
        job_infrastructure = (
            _infrastructure_row(
                observed.get("infrastructure", {}),
                "fragment job infrastructure",
                allow_positions=False,
            )
            if observed is not None
            else {"outcome": "missing"}
        )
        jobs_out.append(
            {
                "logical_job_id": job_id,
                "pack_index": first["pack_index"],
                "job_exec_sha256": first["job_exec_sha256"],
                "infrastructure": job_infrastructure,
                "steps": by_job[job_id],
            }
        )

    # Confine an unrepresentable unit to its own job.  The fault stays fully
    # fail-closed there (blocked/unknown step plus a job-level infrastructure
    # failure), and the jobs the classifier could represent survive instead of
    # the run collapsing to an empty jobs list.
    for job in jobs_out:
        job_id = job["logical_job_id"]
        faults: list[str] = []
        for position, step in enumerate(job["steps"]):
            error = _step_representation_error(job_id, step, identity["role"])
            if error is None:
                continue
            faults.append(error)
            item = expected.get((job_id, step.get("proof_id")))
            if item is not None:
                job["steps"][position] = _blocked_step(item, error)
        if faults:
            job["infrastructure"] = {
                "outcome": "planner_configuration_failure",
                "detail": _bounded_text("; ".join(faults)),
            }

    semantic_blocking = any(
        step["classification"] not in {"passed", "inherited_base"}
        for job in jobs_out
        for step in job["steps"]
    )
    infrastructure_blocking = bool(infrastructure) or any(
        str(job["infrastructure"].get("outcome", "passed")) != "passed"
        for job in jobs_out
    )
    # An authority-changing bootstrap PR may still earn a conventional all-pass
    # result under the old gate.  What it may never do is use the new
    # candidate-authored attribution law to excuse one of its own red units.
    self_excuse = bool(
        identity["role"] == "pr_head"
        and authority_changed
        and any(
            step["classification"] == "inherited_base"
            for job in jobs_out
            for step in job["steps"]
        )
    )
    if self_excuse:
        infrastructure.append(
            {
                "outcome": "authority_self_excuse_refused",
                "detail": "candidate changes semantic proof authority",
            }
        )
    status = "failure" if semantic_blocking or infrastructure_blocking or self_excuse else "clear"
    evidence: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        **identity,
        "authority_changed": authority_changed,
        "status": status,
        "jobs": jobs_out,
        "infrastructure": infrastructure,
    }
    evidence["evidence_sha256"] = canonical_sha256(evidence)
    # Never hand back a document the consumers will refuse: an artifact that
    # fails here becomes the CLI's bounded planner failure, which is the same
    # fail-closed outcome as today rather than a silently invalid aggregate.
    _validate_evidence(evidence)
    return evidence


def _validate_evidence(source: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = _object(source, "semantic evidence")
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise SemanticProofError(f"evidence schema must be {EVIDENCE_SCHEMA}")
    expected_top_keys = {
        "schema",
        "workflow_run_id",
        "workflow",
        "event",
        "role",
        "tested_tree_sha",
        "subject_head_sha",
        "base_sha",
        "plan_sha256",
        "authority_changed",
        "status",
        "jobs",
        "infrastructure",
        "evidence_sha256",
    }
    if set(evidence) != expected_top_keys:
        raise SemanticProofError("semantic evidence has missing or unsupported fields")
    identity = _identity(evidence)
    if evidence.get("status") not in {"clear", "failure"}:
        raise SemanticProofError("evidence status must be clear or failure")
    if type(evidence.get("authority_changed")) is not bool:
        raise SemanticProofError("evidence authority_changed must be boolean")
    seen_jobs: set[str] = set()
    jobs = _array(evidence.get("jobs"), "evidence jobs")
    if len(jobs) > 4096:
        raise SemanticProofError("semantic evidence contains too many jobs")
    blocking = False
    inherited = False
    job_infrastructure_blocking = False
    for raw_job in jobs:
        job = _object(raw_job, "evidence job")
        if set(job) != {
            "logical_job_id",
            "pack_index",
            "job_exec_sha256",
            "infrastructure",
            "steps",
        }:
            raise SemanticProofError("evidence job has missing or unsupported fields")
        job_id = _logical_job_id(job.get("logical_job_id"))
        if job_id in seen_jobs:
            raise SemanticProofError(f"evidence duplicates logical job {job_id}")
        seen_jobs.add(job_id)
        if type(job.get("pack_index")) is not int or job["pack_index"] < 0:
            raise SemanticProofError("evidence pack_index must be non-negative integer")
        _sha(job.get("job_exec_sha256"), "job_exec_sha256", size=64)
        job_infrastructure = _infrastructure_row(
            job.get("infrastructure"),
            f"evidence {job_id} infrastructure",
            allow_positions=False,
        )
        if dict(job["infrastructure"]) != job_infrastructure:
            raise SemanticProofError(f"evidence {job_id} infrastructure is not canonical")
        job_infrastructure_blocking |= job_infrastructure["outcome"] != "passed"
        seen_steps: set[str] = set()
        steps = _array(job.get("steps"), f"{job_id} steps")
        if not steps or len(steps) > 4096:
            raise SemanticProofError(f"evidence {job_id} has an invalid step count")
        for raw_step in steps:
            step = _object(raw_step, "evidence step")
            if set(step) - {
                "proof_id",
                "step_spec_sha256",
                "outcome",
                "failure_signature",
                "classification",
                "detail",
            } or not {
                "proof_id",
                "step_spec_sha256",
                "outcome",
                "failure_signature",
                "classification",
            }.issubset(step):
                raise SemanticProofError("evidence step has missing or unsupported fields")
            proof_id = normalize_proof_id(step.get("proof_id"))
            if step.get("proof_id") != proof_id:
                raise SemanticProofError(f"evidence {job_id}/{proof_id} proof_id is not canonical")
            if proof_id in seen_steps:
                raise SemanticProofError(f"evidence duplicates {job_id}/{proof_id}")
            seen_steps.add(proof_id)
            _sha(step.get("step_spec_sha256"), "step_spec_sha256", size=64)
            outcome = step.get("outcome")
            classification = step.get("classification")
            if outcome not in _STEP_OUTCOMES:
                raise SemanticProofError(f"invalid evidence outcome for {job_id}/{proof_id}")
            if classification not in _CLASSIFICATIONS:
                raise SemanticProofError(f"invalid classification for {job_id}/{proof_id}")
            if (outcome == "passed") != (classification == "passed"):
                raise SemanticProofError(
                    f"evidence outcome/classification mismatch for {job_id}/{proof_id}"
                )
            if classification in {
                "inherited_base",
                "pr_regression",
                "pr_ci_contract_change",
                "main_failure",
            } and outcome != "failed":
                raise SemanticProofError(
                    f"evidence classification requires a failure for {job_id}/{proof_id}"
                )
            if identity["role"] == "main" and classification not in {
                "passed",
                "main_failure",
                "unknown",
            }:
                raise SemanticProofError("main evidence contains a PR-only classification")
            if identity["role"] == "pr_head" and classification == "main_failure":
                raise SemanticProofError("PR evidence contains a main-only classification")
            _failure_signature(
                step.get("failure_signature"),
                f"evidence {job_id}/{proof_id} failure_signature",
            )
            if outcome == "passed" and step.get("failure_signature") is not None:
                raise SemanticProofError("passed semantic proof carries a failure signature")
            if "detail" in step:
                detail = _string(
                    step.get("detail"),
                    f"evidence {job_id}/{proof_id} detail",
                    nonempty=False,
                )
                if detail != _bounded_text(detail):
                    raise SemanticProofError("semantic evidence detail is not bounded/canonical")
            blocking |= classification not in {"passed", "inherited_base"}
            inherited |= classification == "inherited_base"
    raw_infrastructure = _array(evidence.get("infrastructure"), "evidence infrastructure")
    if len(raw_infrastructure) > 512:
        raise SemanticProofError("semantic evidence contains too many infrastructure rows")
    for index, raw_row in enumerate(raw_infrastructure):
        normalized = _infrastructure_row(
            raw_row,
            f"evidence infrastructure row {index}",
            allow_positions=True,
        )
        if dict(raw_row) != normalized:
            raise SemanticProofError("semantic evidence infrastructure is not canonical")
    self_excuse = bool(
        identity["role"] == "pr_head"
        and evidence["authority_changed"]
        and inherited
    )
    expected_status = (
        "failure"
        if blocking
        or job_infrastructure_blocking
        or raw_infrastructure
        or self_excuse
        else "clear"
    )
    if evidence["status"] != expected_status:
        raise SemanticProofError("semantic evidence status contradicts its contents")
    receipt = _sha(evidence.get("evidence_sha256"), "evidence_sha256", size=64)
    payload = dict(evidence)
    payload.pop("evidence_sha256", None)
    if canonical_sha256(payload) != receipt:
        raise SemanticProofError("semantic evidence digest mismatch")
    return evidence


def load_semantic_evidence(
    source: Mapping[str, Any] | None,
    *,
    advertised: bool,
    expected_run_id: int | str | None = None,
    expected_subject_head_sha: str | None = None,
    expected_tested_tree_sha: str | None = None,
    expected_base_sha: str | None = None,
    expected_role: str | None = None,
    expected_workflow: str | None = None,
    expected_event: str | None = None,
) -> LoadedSemanticEvidence:
    if source is None:
        if advertised:
            raise SemanticProofError("semantic-era run is missing its advertised final evidence")
        return LoadedSemanticEvidence("legacy_absent", None)
    if not advertised:
        raise SemanticProofError("unadvertised semantic evidence is not authoritative")
    evidence = _validate_evidence(source)
    expected = {
        "workflow_run_id": str(expected_run_id) if expected_run_id is not None else None,
        "subject_head_sha": expected_subject_head_sha,
        "tested_tree_sha": expected_tested_tree_sha,
        "base_sha": expected_base_sha,
        "role": expected_role,
        "workflow": expected_workflow,
        "event": expected_event,
    }
    for key, value in expected.items():
        if value is not None and str(evidence.get(key)) != str(value):
            raise SemanticProofError(f"semantic evidence {key} mismatch")
    return LoadedSemanticEvidence("semantic", evidence)


def _units(evidence: Mapping[str, Any]) -> tuple[SemanticUnit, ...]:
    validated = _validate_evidence(evidence)
    rows: list[SemanticUnit] = []
    for job in validated["jobs"]:
        for step in job["steps"]:
            rows.append(
                SemanticUnit(
                    logical_job_id=job["logical_job_id"],
                    proof_id=step["proof_id"],
                    classification=step["classification"],
                    outcome=step["outcome"],
                    pack_index=job["pack_index"],
                    step_spec_sha256=step["step_spec_sha256"],
                    job_exec_sha256=job["job_exec_sha256"],
                    failure_signature=step.get("failure_signature"),
                    detail=step.get("detail"),
                    base_sha=validated["base_sha"],
                    head_sha=validated["subject_head_sha"],
                )
            )
    return tuple(rows)


def semantic_gate_verdict(evidence: Mapping[str, Any] | None) -> SemanticGateVerdict:
    if evidence is None:
        raise SemanticProofError("semantic gate has no evidence")
    validated = _validate_evidence(evidence)
    units = _units(validated)
    passed = tuple(unit for unit in units if unit.classification == "passed")
    inherited = tuple(unit for unit in units if unit.classification == "inherited_base")
    blocking = tuple(unit for unit in units if unit.classification not in {"passed", "inherited_base"})
    infrastructure_blocking = bool(validated["infrastructure"]) or any(
        str(job["infrastructure"].get("outcome", "passed")) != "passed"
        for job in validated["jobs"]
    )
    clear = (
        validated["status"] == "clear"
        and not blocking
        and not infrastructure_blocking
        and not (
            validated["role"] == "pr_head"
            and validated["authority_changed"]
            and bool(inherited)
        )
    )
    return SemanticGateVerdict(
        clear,
        blocking,
        inherited,
        passed,
        infrastructure_blocking,
    )


def semantic_surface(evidence: Mapping[str, Any]) -> frozenset[tuple[str, str]]:
    return frozenset((unit.logical_job_id, unit.proof_id) for unit in _units(evidence))


def red_semantic_units(evidence: Mapping[str, Any]) -> frozenset[tuple[str, str]]:
    return frozenset(
        (unit.logical_job_id, unit.proof_id)
        for unit in _units(evidence)
        if unit.outcome != "passed"
    )


def main_red_overlap(
    main_evidence: Mapping[str, Any], candidate_evidence: Mapping[str, Any]
) -> frozenset[tuple[str, str]]:
    return red_semantic_units(main_evidence) & semantic_surface(candidate_evidence)


def format_semantic_unit(unit: SemanticUnit) -> str:
    return (
        f"logical job={unit.logical_job_id}; proof id={unit.proof_id}; "
        f"classification={unit.classification}; outcome={unit.outcome}; "
        f"failure signature={unit.failure_signature!r}; base SHA={unit.base_sha}; "
        f"head SHA={unit.head_sha}; transport pack={unit.pack_index}; "
        f"detail={unit.detail or ''}"
    )


def find_descendant_pass_witness(
    logical_job_id: str,
    proof_id: str,
    old_merge_sha: str,
    candidates: Iterable[Mapping[str, Any] | LoadedSemanticEvidence],
    is_ancestor: Callable[[str, str], bool],
    *,
    old_step_spec_sha: str | None = None,
    max_candidates: int = 12,
) -> DescendantWitness | None:
    """Return any bounded ancestry-valid PASS; later red never resurrects it."""
    for index, item in enumerate(candidates):
        if index >= max_candidates:
            break
        evidence = item.evidence if isinstance(item, LoadedSemanticEvidence) else item
        if not isinstance(evidence, Mapping):
            continue
        try:
            validated = _validate_evidence(evidence)
        except SemanticProofError:
            continue
        if validated["role"] != "main":
            continue
        tree = validated["tested_tree_sha"]
        if not is_ancestor(old_merge_sha, tree):
            continue
        for job in validated["jobs"]:
            if job["logical_job_id"] != logical_job_id:
                continue
            for step in job["steps"]:
                if step["proof_id"] == proof_id and step["outcome"] == "passed":
                    old_spec = old_step_spec_sha or ""
                    witness_spec = step["step_spec_sha256"]
                    return DescendantWitness(
                        workflow_run_id=validated["workflow_run_id"],
                        tested_tree_sha=tree,
                        old_step_spec_sha=old_spec,
                        witness_step_spec_sha=witness_spec,
                        contract_changed=bool(old_spec and old_spec != witness_spec),
                    )
    return None


# How many ancestry-valid main artifacts must be readable before their job
# inventory is allowed to answer "no main run will ever emit this job".
# One artifact is a sample, not an inventory: a single truncated or partially
# uploaded main artifact would otherwise declare every job unclearable at once.
MIN_INVENTORY_ARTIFACTS = 2


@dataclass(frozen=True)
class MainRoleInventory:
    """What the main role actually plans, read off main's own artifacts.

    ``job_ids`` is the union of ``logical_job_id`` across the readable
    main-role artifacts, i.e. the jobs main is ELIGIBLE to report on.  It is
    deliberately a union rather than an intersection: a job main ran even once
    in the window can produce a descendant PASS later, so it is clearable.
    """

    job_ids: frozenset[str]
    artifacts: int
    descendant_artifacts: int


def main_role_job_inventory(
    old_merge_sha: str,
    candidates: Iterable[Mapping[str, Any] | LoadedSemanticEvidence],
    is_ancestor: Callable[[str, str], bool],
    *,
    max_candidates: int = 12,
) -> MainRoleInventory:
    """The job set main can report on, from the same bounded artifact window.

    Semantic ELIGIBILITY is role-dependent, and that is the asymmetry this
    exists to expose.  ``ci.yml`` plans the merge gate with ``--gate code`` and
    ``data-health.yml`` runs the ``gate: data`` jobs on its own lane, which
    emits no main-role semantic evidence at all.  A pull-request head planned
    before that split (2026-08-19, W2) therefore froze blocking units for
    ``gate: data`` jobs — measured on PR #5936's head run 32223270543,
    ``house-law-registry`` and ``signal-contract`` — that
    ``find_descendant_pass_witness`` can never match, because no main artifact
    will ever carry those ``logical_job_id``s again.  Waiting for one is not
    slow; it is impossible.

    The ancestry rule is the witness search's own rule, so "eligible" here
    means eligible on the exact main history that could have healed this merge,
    never on some unrelated older lane.
    """
    job_ids: set[str] = set()
    artifacts = 0
    descendant_artifacts = 0
    for index, item in enumerate(candidates):
        if index >= max_candidates:
            break
        evidence = item.evidence if isinstance(item, LoadedSemanticEvidence) else item
        if not isinstance(evidence, Mapping):
            continue
        try:
            validated = _validate_evidence(evidence)
        except SemanticProofError:
            continue
        if validated["role"] != "main":
            continue
        artifacts += 1
        if not is_ancestor(old_merge_sha, validated["tested_tree_sha"]):
            continue
        descendant_artifacts += 1
        for job in validated["jobs"]:
            job_ids.add(job["logical_job_id"])
    return MainRoleInventory(
        frozenset(job_ids), artifacts, descendant_artifacts
    )


def unclearable_units(
    units: Iterable[SemanticUnit],
    inventory: MainRoleInventory,
    *,
    min_descendant_artifacts: int = MIN_INVENTORY_ARTIFACTS,
) -> tuple[SemanticUnit, ...]:
    """Units no future main run can ever clear, or nothing at all.

    Fail-closed by construction: with too few readable descendant artifacts, or
    with an empty inventory, the answer is "unknown", which is spelled as the
    empty tuple — the unit stays blocking exactly as it did before this
    function existed.  Only a job main demonstrably plans WITHOUT this job in
    it can retire a blocking unit.
    """
    if inventory.descendant_artifacts < min_descendant_artifacts:
        return ()
    if not inventory.job_ids:
        return ()
    return tuple(
        unit for unit in units if unit.logical_job_id not in inventory.job_ids
    )


def format_main_eligibility(
    unit: SemanticUnit, inventory: MainRoleInventory
) -> str:
    """One clause telling a session whether waiting on this unit can help."""
    if inventory.descendant_artifacts < MIN_INVENTORY_ARTIFACTS:
        state = "unknown"
    elif unit.logical_job_id in inventory.job_ids:
        state = "yes"
    else:
        state = "no"
    return (
        f"main-eligible={state} "
        f"({inventory.descendant_artifacts} ancestry-valid main artifact(s) of "
        f"{inventory.artifacts} read, {len(inventory.job_ids)} job(s) in main's "
        "eligible inventory)"
    )

def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical_bytes(value) + b"\n")
    temporary.replace(path)


def _planner_failure_evidence(
    detail: object,
    *,
    workflow_run_id: object | None = None,
    workflow: object | None = None,
    event: object | None = None,
    role: object | None = None,
    tested_tree_sha: object | None = None,
    subject_head_sha: object | None = None,
    base_sha: object | None = None,
) -> dict[str, Any]:
    """Materialize a bounded failure even when the plan cannot be loaded.

    The workflow supplies independently bound identity outputs from its exact
    checkout.  When all are present, the failure artifact remains a structurally
    valid ``ci.semantic_evidence.v1`` document and consumers can provenance-bind
    it normally.  The all-zero/unknown fallback exists only for direct or broken
    invocations that cannot provide those facts; it is intentionally rejected by
    strict consumers and therefore can never downgrade to legacy permission.
    """
    zero40 = "0" * 40
    zero64 = "0" * 64
    supplied = (
        workflow_run_id,
        workflow,
        event,
        role,
        tested_tree_sha,
        subject_head_sha,
        base_sha,
    )
    complete_identity = all(value is not None and str(value) for value in supplied)
    evidence: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "workflow_run_id": str(workflow_run_id) if complete_identity else "unknown",
        "workflow": str(workflow) if complete_identity else "ci",
        "event": str(event) if complete_identity else "unknown",
        "role": str(role) if complete_identity else "main",
        "tested_tree_sha": str(tested_tree_sha) if complete_identity else zero40,
        "subject_head_sha": str(subject_head_sha) if complete_identity else zero40,
        "base_sha": str(base_sha) if complete_identity else zero40,
        "plan_sha256": zero64,
        # With no readable plan, a PR cannot prove that its changed-file surface
        # leaves proof authority untouched. Conservatively mark it authority-
        # changing; the infrastructure failure blocks either way.
        "authority_changed": bool(complete_identity and role == "pr_head"),
        "status": "failure",
        "jobs": [],
        "infrastructure": [
            {"outcome": "planner_configuration_failure", "detail": _bounded_text(detail)}
        ],
    }
    evidence["evidence_sha256"] = canonical_sha256(evidence)
    if complete_identity:
        try:
            _validate_evidence(evidence)
        except SemanticProofError as exc:
            return _planner_failure_evidence(
                f"{_bounded_text(detail)}; fallback identity invalid: {exc}"
            )
    return evidence


def _cli_reconcile(args: argparse.Namespace) -> int:
    try:
        plan = _object(_strict_json_load(Path(args.plan)), "plan")
        fragments: list[Mapping[str, Any]] = []
        directory = Path(args.fragments_dir)
        if directory.exists():
            for path in sorted(directory.glob("*.json")):
                fragments.append(_object(_strict_json_load(path), f"fragment {path.name}"))
        evidence = reconcile_evidence(
            plan,
            fragments,
            planner_outcome=args.planner_outcome,
            planner_detail=args.planner_detail,
        )
        _write_json(Path(args.output), evidence)
        print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
        return 0 if semantic_gate_verdict(evidence).clear else 1
    except Exception as exc:  # ensure red runs still expose one bounded artifact
        evidence = _planner_failure_evidence(
            exc,
            workflow_run_id=args.fallback_workflow_run_id,
            workflow=args.fallback_workflow,
            event=args.fallback_event,
            role=args.fallback_role,
            tested_tree_sha=args.fallback_tested_tree_sha,
            subject_head_sha=args.fallback_subject_head_sha,
            base_sha=args.fallback_base_sha,
        )
        _write_json(Path(args.output), evidence)
        print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
        return 2


def _cli_validate(args: argparse.Namespace) -> int:
    try:
        evidence = _object(_strict_json_load(Path(args.input)), "semantic evidence")
        loaded = load_semantic_evidence(evidence, advertised=True)
        verdict = semantic_gate_verdict(loaded.evidence)
        print(
            json.dumps(
                {"schema": EVIDENCE_SCHEMA, "status": "clear" if verdict.clear else "failure"},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0 if verdict.clear else 1
    except Exception as exc:
        print(f"semantic evidence invalid: {_bounded_text(exc)}", file=__import__("sys").stderr)
        return 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    reconcile = subparsers.add_parser("reconcile", help="build final evidence from plan and fragments")
    reconcile.add_argument("--plan", required=True)
    reconcile.add_argument("--fragments-dir", required=True)
    reconcile.add_argument("--output", required=True)
    reconcile.add_argument("--planner-outcome", default="success")
    reconcile.add_argument("--planner-detail")
    reconcile.add_argument("--fallback-workflow-run-id")
    reconcile.add_argument("--fallback-workflow")
    reconcile.add_argument("--fallback-event")
    reconcile.add_argument("--fallback-role", choices=("pr_head", "main"))
    reconcile.add_argument("--fallback-tested-tree-sha")
    reconcile.add_argument("--fallback-subject-head-sha")
    reconcile.add_argument("--fallback-base-sha")
    validate = subparsers.add_parser("validate", help="validate one final evidence document")
    validate.add_argument("--input", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "reconcile":
        return _cli_reconcile(args)
    return _cli_validate(args)


if __name__ == "__main__":
    raise SystemExit(main())
