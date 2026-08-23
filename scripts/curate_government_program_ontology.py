"""Admit a human-reviewed D5 program-ontology worksheet, atomically.

Usage::

    python -m scripts.curate_government_program_ontology \
      --worksheet research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-22-example.json
    python -m scripts.curate_government_program_ontology \
      --worksheet path/to/worksheet.json --check

The worksheet is the frozen ``government_program_ontology_review_worksheet.v1``
contract (freeze SS3.1c). Curate is the ONLY producer of ``review_coverage[]``
rows: one is minted per ``coverage[]`` entry the worksheet declares, atomically
with whatever admissions that pass belongs to. Refusal is two-tier (freeze
SS3.2): an offending candidate ROW is refused with a rejection-ledger entry;
the artifact never gains it. A whole worksheet pass is applied atomically --
every row that admits cleanly lands together with its coverage rows, or (on
an unresolvable failure) nothing is written.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.government_revenue import program_ontology as po  # noqa: E402


DEFAULT_TARGET = _ROOT / "data" / "government_revenue" / "program_ontology.json"

#: Evidence rows are their own worksheet target_kind (freeze SS3.1a) but are
#: never a candidate for the generic per-collection admit loop: they carry no
#: verification_state/identity_disposition, and their admission law is
#: append-only-with-widening rather than "insert if the certified artifact
#: accepts it".
_EVIDENCE_TARGET_KIND = "evidence"
_EVIDENCE_ROW_FIELDS = frozenset({
    "evidence_id", "evidence_class", "sha256", "source_url", "retrieved_from_url",
    "retrieved_at", "known_at", "claim_scopes", "pinned_issuer_host", "pinned_issuer_host_basis",
})

_TARGET_KIND_TO_COLLECTION = {
    "program": "programs",
    "capability": "capabilities",
    "platform": "platforms",
    "role_assertion": "role_assertions",
    "milestone": "milestones",
    "program_capability_link": "program_capability_links",
    "program_event_link": "program_event_links",
    "conflict": "conflicts",
    "override": "overrides",
}
_COLLECTION_ID_KEY = {
    "programs": "id",
    "capabilities": "id",
    "platforms": "id",
    "role_assertions": "id",
    "milestones": "id",
    "program_capability_links": "link_id",
    "program_event_links": "link_id",
    "conflicts": "conflict_id",
    "overrides": "override_id",
}
_LOGICAL_TARGET_KINDS = {"program", "capability", "platform"}
_GRAPH_ID_RE = re.compile(
    r"^program-ontology:(candidate|reviewed):(\d{4}-\d{2}-\d{2}):([a-z0-9]+(?:-[a-z0-9]+)*)$"
)


class CurateError(ValueError):
    """Raised for a worksheet-level defect that admits nothing."""


def _canonical_bytes(graph: dict[str, Any]) -> str:
    return json.dumps(graph, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _empty_skeleton(*, graph_id: str, graph_known_at: str, graph_effective_at: str) -> dict[str, Any]:
    return {
        "contract": po.CONTRACT,
        "schema_version": po.SCHEMA_VERSION,
        "graph_id": graph_id,
        "graph_known_at": graph_known_at,
        "graph_effective_at": graph_effective_at,
        "authority": dict(po.AUTHORITY),
        "evidence": [],
        "programs": [],
        "capabilities": [],
        "platforms": [],
        "program_capability_links": [],
        "role_assertions": [],
        "milestones": [],
        "program_event_links": [],
        "review_coverage": [],
        "conflicts": [],
        "overrides": [],
    }


def _load_base_graph(
    target_path: Path, *, graph_id: str | None, graph_known_at: str | None, graph_effective_at: str | None,
) -> dict[str, Any]:
    if target_path.exists():
        try:
            raw = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise CurateError("existing canonical ontology artifact is unreadable") from exc
        try:
            po.load_program_ontology_graph(raw)
        except po.OntologyInputError as exc:
            raise CurateError(
                "refusing to curate onto an already-uncertified canonical artifact: "
                + ", ".join(exc.errors)
            ) from exc
        return deepcopy(raw)
    if not (graph_id and graph_known_at and graph_effective_at):
        raise CurateError(
            "no canonical artifact exists yet; --graph-id/--graph-known-at/"
            "--graph-effective-at are required to mint one"
        )
    return _empty_skeleton(graph_id=graph_id, graph_known_at=graph_known_at, graph_effective_at=graph_effective_at)


def _forbidden_keys_present(row: dict[str, Any]) -> bool:
    return bool(set(row) & po.FORBIDDEN_INPUT_KEYS)


def _row_dual_scope_predicate(row: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> bool:
    """SS3.1 curate-time predicate: true iff NO pair of DISTINCT evidence refs
    independently supplies (program_identity, role)."""
    refs = [r for r in (row.get("evidence_refs") or []) if r in evidence_by_id]
    program_scope_refs = {
        r for r in refs if "program_identity" in (evidence_by_id[r].get("claim_scopes") or [])
    }
    role_scope_refs = {r for r in refs if "role" in (evidence_by_id[r].get("claim_scopes") or [])}
    for a in program_scope_refs:
        for b in role_scope_refs:
            if a != b:
                return False
    return True


def _admit_evidence_row(working: dict[str, Any], candidate_row: dict[str, Any]) -> str | None:
    """Apply one worksheet evidence admission (freeze SS3.1a). Mutates
    ``working["evidence"]`` in place. Returns an error code on refusal, or
    ``None`` on success (new row or a legal widening).

    Evidence rows are append-only and keyed by ``evidence_id``: a document
    never seen before mints a new row; a document already on file may only
    be resubmitted to WIDEN its ``claim_scopes`` (set-union) -- every other
    field, including ``retrieved_at``/``known_at``, must match byte-for-byte
    (first receipt wins). Any other difference is refused
    ``evidence_receipt_mismatch``, never silently merged or overwritten.
    """
    if not isinstance(candidate_row, dict) or set(candidate_row) - _EVIDENCE_ROW_FIELDS:
        return "worksheet_inconsistent"
    evidence_id = candidate_row.get("evidence_id")
    if not evidence_id:
        return "worksheet_inconsistent"
    evidence_list = working.setdefault("evidence", [])
    for index, existing in enumerate(evidence_list):
        if existing.get("evidence_id") != evidence_id:
            continue
        stripped_existing = {k: v for k, v in existing.items() if k != "claim_scopes"}
        stripped_candidate = {k: v for k, v in candidate_row.items() if k != "claim_scopes"}
        if stripped_existing != stripped_candidate:
            return "evidence_receipt_mismatch"
        merged_scopes = sorted(set(existing.get("claim_scopes") or []) | set(candidate_row.get("claim_scopes") or []))
        if merged_scopes == sorted(existing.get("claim_scopes") or []):
            return None  # byte-identical resubmission -- dedupes idempotently
        evidence_list[index] = {**existing, "claim_scopes": merged_scopes}
        return None
    evidence_list.append(dict(candidate_row))
    return None


def _identity_disposition_ok(
    disposition: str | None, target_kind: str, candidate_row: dict[str, Any], working: dict[str, Any],
) -> str | None:
    """Returns an error code, or ``None`` when the disposition is consistent."""
    if target_kind not in _LOGICAL_TARGET_KINDS:
        return None
    if disposition is None:
        return "worksheet_inconsistent"
    collection = _TARGET_KIND_TO_COLLECTION[target_kind]
    row_id = candidate_row.get("id")
    existing_ids = {row.get("id") for row in working.get(collection, [])}
    if disposition == "same_object_revision":
        if row_id not in existing_ids:
            return "rename_as_new_identity"
    elif disposition == "new_identity":
        if row_id in existing_ids:
            return "worksheet_inconsistent"
    elif disposition == "identity_break":
        if candidate_row.get("succession_reason") != "restructured" or not candidate_row.get("predecessor_id"):
            return "worksheet_inconsistent"
    else:
        return "worksheet_inconsistent"
    return None


def _verify_event_row(
    candidate_row: dict[str, Any], *, workspace_events: dict[str, dict[str, Any]],
    fallback_events: dict[str, dict[str, Any]] | None = None,
) -> str | None:
    """SS3.1b curate-time event verification. Returns an error code, or None.

    ``fallback_events`` (the parquet-rebuilt event set, only ever populated
    by the caller when the workspace's cap is engaged) is consulted ONLY
    when the event is absent from the capped ``workspace_events`` window --
    the workspace's own copy, when present, is always authoritative.
    """
    event_id = candidate_row.get("event_id")
    live_event = workspace_events.get(event_id)
    if live_event is None and fallback_events:
        live_event = fallback_events.get(event_id)
    if live_event is None:
        return "event_not_found"
    if not po.event_hash_agrees(candidate_row, live_event):
        return "event_identity_mismatch"
    return None


def _logical_kind_of(trial: dict[str, Any], target_id: str) -> str | None:
    if any(r.get("id") == target_id for r in trial.get("programs", [])):
        return "program"
    if any(r.get("id") == target_id for r in trial.get("capabilities", [])):
        return "capability"
    if any(r.get("id") == target_id for r in trial.get("platforms", [])):
        return "platform"
    return None


def _referencing_rows_current(trial: dict[str, Any], kind: str, target_id: str) -> list[dict[str, Any]]:
    """Every row still CURRENT in `trial` that references `target_id` as its
    own program_id/capability_id/platform_id/variant_of (freeze SS5's
    retirement-cascade enumeration)."""
    retired = po.override_targets_of(trial.get("overrides") or [])
    referencing: list[dict[str, Any]] = []
    if kind == "program":
        current_platform_ids = po.current_identities(
            trial.get("platforms") or [], id_key="id", analysis_as_of=None, retired_ids=retired,
        )
        for row in trial.get("platforms") or []:
            if row.get("program_id") == target_id and row.get("id") in current_platform_ids:
                referencing.append(row)
        for collection, id_key in (
            ("role_assertions", "id"), ("milestones", "id"),
            ("program_capability_links", "link_id"), ("program_event_links", "link_id"),
        ):
            current_rows = po.current_content_addressed_rows(
                trial.get(collection) or [], id_key=id_key, analysis_as_of=None, retired_ids=retired,
            )
            referencing.extend(row for row in current_rows if row.get("program_id") == target_id)
    elif kind == "capability":
        current_links = po.current_content_addressed_rows(
            trial.get("program_capability_links") or [], id_key="link_id", analysis_as_of=None, retired_ids=retired,
        )
        referencing.extend(row for row in current_links if row.get("capability_id") == target_id)
    elif kind == "platform":
        current_roles = po.current_content_addressed_rows(
            trial.get("role_assertions") or [], id_key="id", analysis_as_of=None, retired_ids=retired,
        )
        referencing.extend(row for row in current_roles if row.get("platform_id") == target_id)
        current_platform_ids = po.current_identities(
            trial.get("platforms") or [], id_key="id", analysis_as_of=None, retired_ids=retired,
        )
        for row in trial.get("platforms") or []:
            if row.get("variant_of") == target_id and row.get("id") in current_platform_ids:
                referencing.append(row)
    return referencing


def _check_retirement_cascade(trial: dict[str, Any], target_row_id: str | None) -> bool:
    """Freeze SS5: retiring a LOGICAL id is refused `retirement_cascade_incomplete`
    unless the same act also retires/supersedes every current row referencing
    that identity. Returns True (cascade complete / rule inapplicable) or False."""
    if not target_row_id:
        return True
    kind = _logical_kind_of(trial, target_row_id)
    if kind is None:
        return True
    return not _referencing_rows_current(trial, kind, target_row_id)


def _check_conflict_resolution(trial: dict[str, Any], target_row_id: str | None) -> bool:
    """Freeze SS5: retiring a `conflicts` row is refused
    `conflict_resolution_incomplete` unless the post-act state restores the
    invariant -- AT MOST ONE current link on the subject for the event/
    capability axes. Returns True (restored / rule inapplicable) or False."""
    if not target_row_id:
        return True
    conflict_row = next(
        (row for row in trial.get("conflicts") or [] if row.get("conflict_id") == target_row_id), None,
    )
    if conflict_row is None:
        return True
    scope = conflict_row.get("scope")
    subject_type = conflict_row.get("subject_type")
    subject_id = conflict_row.get("subject_id")
    retired = po.override_targets_of(trial.get("overrides") or [])
    if scope == "program_event_link" and subject_type == "award_event":
        current_rows = po.current_content_addressed_rows(
            trial.get("program_event_links") or [], id_key="link_id", analysis_as_of=None, retired_ids=retired,
        )
        return sum(1 for row in current_rows if row.get("event_id") == subject_id) <= 1
    if scope == "capability" and subject_type == "program":
        current_rows = po.current_content_addressed_rows(
            trial.get("program_capability_links") or [], id_key="link_id", analysis_as_of=None, retired_ids=retired,
        )
        return sum(1 for row in current_rows if row.get("program_id") == subject_id) <= 1
    return True


def _check_override_cascades(trial: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Run the two SS5 retire_row curate-side invariants over every
    retire_row override in `trial`. Returns (error_codes, offending_ids)."""
    errors: list[str] = []
    offending: list[str] = []
    for override_row in trial.get("overrides") or []:
        if override_row.get("action") != "retire_row":
            continue
        target = override_row.get("target_row_id")
        own_id = override_row.get("override_id")
        if not _check_retirement_cascade(trial, target):
            errors.append("retirement_cascade_incomplete")
            offending.append(own_id)
        if not _check_conflict_resolution(trial, target):
            errors.append("conflict_resolution_incomplete")
            offending.append(own_id)
    return errors, offending


def _load_parquet_fallback_events(
    parquet_dir: Path, *, as_of: str,
) -> dict[str, dict[str, Any]]:
    """Freeze SS3.1b: the workspace's `government_procurement_event.v2`
    collection is a DOCUMENTED capped window -- when the cap is engaged
    (``events_truncated > 0``), an event absent from that window is not
    evidence of nonexistence. Rebuilds the full award-change event set from
    the uncapped raw parquet stores (the same builder the production
    pipeline uses) so curate can still verify identity/hash agreement for an
    event that aged out of the workspace's cache. Offline tooling only --
    pandas/pyarrow are acceptable here, never in the loader.

    Returns ``{}`` (never raises) when either parquet file is absent or
    unreadable -- an empty fallback still correctly falls through to
    ``event_not_found``, exactly like "absent everywhere".
    """
    try:
        import pandas as pd

        from engine.government_revenue.award_events import build_award_change_events
    except ImportError:
        return {}

    snapshots_path = parquet_dir / "award_event_snapshots.parquet"
    actions_path = parquet_dir / "award_actions.parquet"
    try:
        snapshots = pd.read_parquet(snapshots_path) if snapshots_path.exists() else pd.DataFrame()
        actions = pd.read_parquet(actions_path) if actions_path.exists() else pd.DataFrame()
    except (OSError, ValueError) as exc:
        raise CurateError(f"parquet fallback stores are unreadable: {exc}") from exc
    if snapshots.empty and actions.empty:
        return {}
    events = build_award_change_events(snapshots, actions, as_of=as_of, known_at=as_of)
    return {
        event.get("event_id"): event
        for event in events
        if isinstance(event, dict) and event.get("event_id")
    }


def curate_worksheet(
    worksheet_path: Path,
    *,
    target_path: Path = DEFAULT_TARGET,
    graph_id: str | None = None,
    graph_known_at: str | None = None,
    graph_effective_at: str | None = None,
    workspace_events: dict[str, dict[str, Any]] | None = None,
    events_truncated: int = 0,
    parquet_dir: Path | None = None,
    check_only: bool = False,
) -> dict[str, Any]:
    """Admit a worksheet pass. Returns a report: admitted / rejected /
    coverage rows minted, and whether the artifact was written."""
    try:
        worksheet_ref = str(worksheet_path.resolve().relative_to(_ROOT.resolve()))
    except ValueError:
        # Outside the repo (e.g. a tmp_path test fixture) -- fall back to the
        # given path rather than shipping a machine-local absolute one in a
        # published artifact; production worksheets always resolve above.
        worksheet_ref = str(worksheet_path)
    worksheet_bytes = worksheet_path.read_bytes()
    worksheet_sha256 = sha256(worksheet_bytes).hexdigest()
    try:
        worksheet = json.loads(worksheet_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise CurateError("review worksheet is not valid JSON") from exc
    if not isinstance(worksheet, dict):
        raise CurateError("review worksheet must be a JSON object")
    if worksheet.get("contract") != po.WORKSHEET_CONTRACT or worksheet.get("schema_version") != po.WORKSHEET_SCHEMA_VERSION:
        raise CurateError("review worksheet carries the wrong contract/schema_version")
    reviewed_at = worksheet.get("reviewed_at")
    if po.strict_datetime(reviewed_at) is None:
        raise CurateError("review worksheet reviewed_at is not a strict D5 timestamp")
    if not str(worksheet.get("reviewer") or "").strip():
        raise CurateError("review worksheet is missing a reviewer")
    coverage_declared = worksheet.get("coverage") or []
    rows = worksheet.get("rows") or []
    if not isinstance(coverage_declared, list) or not isinstance(rows, list):
        raise CurateError("review worksheet coverage/rows must be arrays")

    # SS3.1b parquet fallback: only ever consulted when the workspace's own
    # capped event window is engaged (events_truncated > 0) -- the cap is
    # not evidence of nonexistence. Loaded once per act, never per row.
    fallback_events: dict[str, dict[str, Any]] | None = None
    if events_truncated > 0 and parquet_dir is not None:
        fallback_events = _load_parquet_fallback_events(parquet_dir, as_of=reviewed_at)

    guard_output_path(target_path)
    working = _load_base_graph(
        target_path, graph_id=graph_id, graph_known_at=graph_known_at, graph_effective_at=graph_effective_at,
    )
    # freeze SS3.0: curate re-mints the graph_id's status segment to
    # `reviewed` on every admission -- a `candidate`-status graph_id must
    # never reach the canonical artifact.
    working["graph_id"] = _reviewed_graph_id(working.get("graph_id"))

    admitted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    admit_candidates: list[dict[str, Any]] = []

    # Evidence admissions/widenings apply FIRST, atomically with everything
    # else in this act (freeze SS3.1's role_assertion clause: "within one
    # curate act, evidence-row updates ... apply FIRST and row admissions
    # are then predicated on the post-update scopes"). This is what makes a
    # role/link admitted in the SAME act as its own supporting evidence see
    # that evidence's claim_scopes when curate checks coverage/dual-scope.
    evidence_admitted = 0
    for row in rows:
        if row.get("action") != "admit" or row.get("target_kind") != _EVIDENCE_TARGET_KIND:
            continue
        candidate_row = row.get("candidate_row")
        if _forbidden_keys_present(candidate_row or {}):
            rejected.append({"row": row, "reason": "forbidden_provenance_key_present"})
            continue
        error = _admit_evidence_row(working, candidate_row)
        if error:
            rejected.append({"row": row, "reason": error})
        else:
            evidence_admitted += 1
    evidence_by_id = {row.get("evidence_id"): row for row in working.get("evidence", [])}

    for row in rows:
        action = row.get("action")
        target_kind = row.get("target_kind")
        if target_kind == _EVIDENCE_TARGET_KIND:
            continue  # already handled above, whichever way it resolved
        if action == "reject":
            rejected.append({"row": row, "reason": row.get("rejection_reason") or "worksheet_rejected"})
            continue
        if action != "admit":
            rejected.append({"row": row, "reason": "worksheet_inconsistent"})
            continue
        candidate_row = row.get("candidate_row")
        if target_kind not in _TARGET_KIND_TO_COLLECTION or not isinstance(candidate_row, dict):
            rejected.append({"row": row, "reason": "worksheet_inconsistent"})
            continue
        if _forbidden_keys_present(candidate_row):
            rejected.append({"row": row, "reason": "forbidden_provenance_key_present"})
            continue
        if candidate_row.get("verification_state") not in po.REVIEW_STATES:
            rejected.append({"row": row, "reason": "worksheet_inconsistent"})
            continue
        if target_kind == "role_assertion":
            evidence_refs_now = candidate_row.get("evidence_refs") or []
            candidate_evidence = {
                ref: evidence_by_id[ref] for ref in evidence_refs_now if ref in evidence_by_id
            }
            computed = _row_dual_scope_predicate(candidate_row, candidate_evidence)
            if bool(candidate_row.get("single_document_dual_scope")) != computed:
                rejected.append({"row": row, "reason": "dual_scope_predicate_mismatch"})
                continue
            if computed and not str(row.get("scope_statement") or "").strip():
                rejected.append({"row": row, "reason": "missing_scope_statement"})
                continue
        if target_kind in _LOGICAL_TARGET_KINDS:
            disposition_error = _identity_disposition_ok(
                row.get("identity_disposition"), target_kind, candidate_row, working,
            )
            if disposition_error:
                rejected.append({"row": row, "reason": disposition_error})
                continue
        if target_kind == "capability":
            # Orphan rule: a capability record needs >=1 citing link in the
            # SAME act (checked once the whole admit batch is known, below).
            pass
        if target_kind == "program_event_link":
            error = _verify_event_row(
                candidate_row, workspace_events=workspace_events or {}, fallback_events=fallback_events,
            )
            if error:
                rejected.append({"row": row, "reason": error})
                continue
        admit_candidates.append({"row": row, "target_kind": target_kind, "candidate_row": candidate_row})

    # Orphan-capability rule: a capability admitted in this act needs >=1
    # citing program_capability_link admitted in the SAME act (or already
    # present with that capability_id).
    admitted_capability_ids = {
        c["candidate_row"].get("id") for c in admit_candidates if c["target_kind"] == "capability"
    }
    cited_capability_ids = {
        c["candidate_row"].get("capability_id") for c in admit_candidates
        if c["target_kind"] == "program_capability_link"
    } | {row.get("capability_id") for row in working.get("program_capability_links", [])}
    for candidate in list(admit_candidates):
        if candidate["target_kind"] == "capability" and candidate["candidate_row"].get("id") not in cited_capability_ids:
            admit_candidates.remove(candidate)
            rejected.append({"row": candidate["row"], "reason": "orphan_capability"})

    # Batch-apply, then greedily remove offending rows until the working
    # artifact certifies (or no candidates remain). This is what makes a
    # worksheet act atomic for the rows that legitimately depend on each
    # other (e.g. a second link + its own clearing conflicts row) while still
    # refusing an individually bad row without sinking the whole pass.
    remaining = list(admit_candidates)
    for _ in range(len(remaining) + 1):
        trial = deepcopy(working)
        for candidate in remaining:
            trial[_TARGET_KIND_TO_COLLECTION[candidate["target_kind"]]].append(candidate["candidate_row"])
        try:
            # Curate-only invariants the loader does not (and must not, per
            # freeze SS3.2 -- these are ADMISSION-time laws) enforce: a
            # retire_row on a logical id needs its cascade complete; a
            # retire_row clearing a conflicts row needs the multiplicity
            # invariant restored. Checked BEFORE the loader call: an
            # incomplete conflict-resolution retirement also trips the
            # loader's OWN generic link_multiplicity_invalid check (the
            # conflict-exemption it grants stops applying to a conflict that
            # is itself now retired) -- the freeze-named diagnosis here is
            # strictly more specific and must win the attribution.
            cascade_errors, cascade_offending = _check_override_cascades(trial)
            if cascade_errors:
                raise po.OntologyInputError(cascade_errors, cascade_offending)
            po.load_program_ontology_graph(trial)
        except po.OntologyInputError as exc:
            offending = set(exc.offending_rows)
            still_bad = [
                c for c in remaining
                if _row_key(c) in offending
            ]
            if not still_bad:
                # Cannot attribute the failure to a specific candidate; refuse
                # every remaining row rather than writing an uncertified graph.
                for candidate in remaining:
                    rejected.append({"row": candidate["row"], "reason": "worksheet_inconsistent"})
                remaining = []
                break
            for candidate in still_bad:
                rejected.append({"row": candidate["row"], "reason": ",".join(sorted(exc.errors))})
            remaining = [c for c in remaining if c not in still_bad]
            continue
        else:
            working = trial
            admitted = remaining
            remaining = []
            break
    else:
        for candidate in remaining:
            rejected.append({"row": candidate["row"], "reason": "worksheet_inconsistent"})

    # Mint review_coverage rows -- curate is the ONLY producer -- one per
    # declared coverage entry, atomically with the admissions above.
    coverage_rows: list[dict[str, Any]] = []
    for entry in coverage_declared:
        scope = entry.get("scope")
        subject_type = entry.get("subject_type")
        subject_id = entry.get("subject_id")
        if scope not in po.COVERAGE_SCOPE_ENUM or subject_type not in po.COVERAGE_SUBJECT_TYPE_ENUM or not subject_id:
            continue
        admitted_count = sum(
            1 for c in admitted
            if _covers(c, scope=scope, subject_type=subject_type, subject_id=subject_id)
        )
        coverage_row = {
            "coverage_id": po.review_coverage_id(
                scope=scope, subject_type=subject_type, subject_id=subject_id,
                worksheet_sha256=worksheet_sha256, known_at=reviewed_at,
            ),
            "scope": scope,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "known_at": reviewed_at,
            "worksheet_ref": worksheet_ref,
            "worksheet_sha256": worksheet_sha256,
            "admitted_count": admitted_count,
        }
        coverage_rows.append(coverage_row)
        working["review_coverage"].append(coverage_row)

    try:
        po.load_program_ontology_graph(working)
    except po.OntologyInputError as exc:
        raise CurateError(
            "worksheet admission produced an uncertifiable artifact: " + ", ".join(exc.errors)
        ) from exc

    if not check_only:
        _atomic_write(target_path, _canonical_bytes(working))

    return {
        "graph_id": working.get("graph_id"),
        "admitted_count": len(admitted) + evidence_admitted,
        "evidence_admitted_count": evidence_admitted,
        "rejected_count": len(rejected),
        "rejected": rejected,
        "coverage_rows_minted": len(coverage_rows),
        "written": not check_only,
    }


def _row_key(candidate: dict[str, Any]) -> str:
    row = candidate["candidate_row"]
    id_key = _COLLECTION_ID_KEY[_TARGET_KIND_TO_COLLECTION[candidate["target_kind"]]]
    return row.get(id_key) or "<candidate>"


def _covers(candidate: dict[str, Any], *, scope: str, subject_type: str, subject_id: str) -> bool:
    row = candidate["candidate_row"]
    target_kind = candidate["target_kind"]
    if subject_type == "program":
        if scope == "program_identity":
            if target_kind == "program":
                return row.get("id") == subject_id
            if target_kind == "platform":
                return row.get("program_id") == subject_id
            return False
        if scope == "capability":
            return target_kind == "program_capability_link" and row.get("program_id") == subject_id
        if scope == "participants":
            return target_kind == "role_assertion" and row.get("program_id") == subject_id
        if scope == "milestones":
            return target_kind == "milestone" and row.get("program_id") == subject_id
        if scope == "program_event_link":
            return target_kind == "program_event_link" and row.get("program_id") == subject_id
    if subject_type == "award_event" and scope == "program_event_link":
        return target_kind == "program_event_link" and row.get("event_id") == subject_id
    return False


def guard_output_path(path: Path) -> Path:
    """Refuse a destination curate has no business writing.

    Unlike the PROPOSE script's identically-named guard (which exists to
    keep discovery output away from the canonical path), curate's whole job
    IS writing the canonical program ontology -- so its guard runs the
    opposite check: the destination must be named exactly like the
    canonical artifact (``program_ontology.json``), refusing a stray/typo
    ``--target`` that would silently publish a differently-named file. The
    directory root is deliberately not pinned here (a caller may legitimately
    retarget within a test/migration tree); the canonical FILENAME is the
    invariant curate exists to protect.
    """
    resolved = path.resolve()
    if resolved.name != DEFAULT_TARGET.name:
        raise ValueError(
            f"curate only writes a file named {DEFAULT_TARGET.name!r}; refusing {path}"
        )
    return resolved


def _reviewed_graph_id(graph_id: str) -> str:
    """Re-mint the graph_id's status segment to `reviewed` on admission
    (freeze SS3.0: "the propose script mints `candidate`, the curate script
    re-mints `reviewed` on admission" -- a `candidate`-status graph_id must
    never reach the canonical artifact). Idempotent on an already-`reviewed`
    graph_id."""
    match = _GRAPH_ID_RE.fullmatch(graph_id or "")
    if not match:
        raise CurateError(f"graph_id does not match the frozen grammar: {graph_id!r}")
    _status, date_part, slug = match.groups()
    return f"program-ontology:reviewed:{date_part}:{slug}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Admit a human-reviewed D5 program-ontology worksheet."
    )
    parser.add_argument("--worksheet", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--graph-id")
    parser.add_argument("--graph-known-at")
    parser.add_argument("--graph-effective-at")
    parser.add_argument("--workspace", type=Path, help="Path to workspace.json for event verification")
    parser.add_argument(
        "--parquet-dir", type=Path, default=None,
        help="Directory holding award_event_snapshots.parquet/award_actions.parquet "
        "(SS3.1b fallback when the workspace's event cap is engaged; defaults to "
        "data/government_revenue/ next to --workspace's usual location)",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    workspace_events: dict[str, dict[str, Any]] = {}
    events_truncated = 0
    if args.workspace and args.workspace.exists():
        workspace_data = json.loads(args.workspace.read_text(encoding="utf-8"))
        for event in workspace_data.get("events", []):
            if isinstance(event, dict) and event.get("event_id"):
                workspace_events[event["event_id"]] = event
        coverage = workspace_data.get("coverage") or {}
        events_truncated = coverage.get("events_truncated") or 0

    report = curate_worksheet(
        args.worksheet,
        target_path=args.target,
        graph_id=args.graph_id,
        graph_known_at=args.graph_known_at,
        graph_effective_at=args.graph_effective_at,
        workspace_events=workspace_events,
        events_truncated=events_truncated,
        parquet_dir=args.parquet_dir or (_ROOT / "data" / "government_revenue"),
        check_only=args.check,
    )
    action = "validated" if args.check else "published"
    print(
        f"program ontology {action}: graph_id={report['graph_id']} "
        f"admitted={report['admitted_count']} rejected={report['rejected_count']} "
        f"coverage_rows={report['coverage_rows_minted']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
