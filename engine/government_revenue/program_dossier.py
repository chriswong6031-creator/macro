"""Composed, read-only Program/Platform Dossier read model (D5, freeze SS4).

``government_program_dossier.v1`` owns zero truth. Every rail carries the
owning artifact's ids so the UI can deep-link; the composer joins the D5
reviewed ontology (:mod:`engine.government_revenue.program_ontology`) with
the award-plane workspace freshness block and the identity atlas -- all at
READ time, with no new global supergraph and no copied event/company/budget
truth.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import program_ontology as po


CONTRACT = "government_program_dossier.v1"
SCHEMA_VERSION = "1.0.0"
CONTENT_ID_PREFIX = "gpd1-"

PARTICIPATION_LIMITATION = (
    "Companies on this rail participate in the same program; no commercial "
    "relationship between them is asserted."
)
ALLOCATION_LIMITATION = (
    "Reviewed participation is not a share of revenue. Nothing here "
    "allocates award value to a ticker."
)

LIMITATIONS: tuple[str, ...] = (
    "Program/capability/platform truth is reviewed acquisition-domain "
    "ontology, not budget or contract-value truth.",
    "The awards rail is a pointer to the reviewed program<->event relation; "
    "amounts, dates, and agencies live in the award plane's own artifacts.",
    "Economic relationships between participants are not asserted anywhere "
    "in this bundle.",
)

_STATE_KEY_ONLY_RAILS = ("budget", "economic_relationships")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )


def dossier_content_id(payload: Mapping[str, Any]) -> str:
    """``gpd1-`` + first 24 hex of SHA-256 over canonical JSON, excluding
    ``content_id``/``generated_at`` (freeze SS4; sibling of ``grd1-`` in
    :mod:`engine.government_revenue.dossiers`). Raises rather than shipping a
    null ``content_id`` on a canonicalization failure."""
    try:
        fingerprint = {
            str(key): value for key, value in payload.items()
            if key not in {"content_id", "generated_at"}
        }
        digest = sha256(_canonical_json(fingerprint).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as exc:
        raise ValueError("program dossier payload cannot be represented as canonical JSON") from exc
    return CONTENT_ID_PREFIX + digest[:24]


def _empty_dossier_bundle(*, as_of: str, generated_at: str, ontology_graph_id: str | None) -> dict[str, Any]:
    payload = {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "content_id": "",
        "generated_at": generated_at,
        "as_of": as_of,
        "ontology_graph_id": ontology_graph_id,
        "authority": dict(po.AUTHORITY),
        "dossiers": [],
        "limitations": list(LIMITATIONS),
    }
    payload["content_id"] = dossier_content_id(payload)
    return payload


def _build_atlas_index(atlas: Mapping[str, Any] | None) -> dict[str, list[tuple[str, str | None]]]:
    """entity_id -> [(ticker, public_security.state), ...] reverse-membership
    lookup over the identity atlas's ``issuers[].entities[]`` rows (freeze SS4
    participants rail; the ONLY place issuer identity flows in)."""
    index: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    if not isinstance(atlas, Mapping):
        return index
    for issuer in atlas.get("issuers") or []:
        if not isinstance(issuer, Mapping):
            continue
        ticker = issuer.get("ticker")
        public_security = issuer.get("public_security")
        state = public_security.get("state") if isinstance(public_security, Mapping) else None
        for entity in issuer.get("entities") or []:
            if not isinstance(entity, Mapping):
                continue
            entity_id = entity.get("entity_id")
            if entity_id and ticker:
                index[entity_id].append((ticker, state))
    return index


def _awards_source_state(workspace: Mapping[str, Any] | None) -> str:
    if not isinstance(workspace, Mapping):
        return "source_unavailable"
    freshness = workspace.get("freshness")
    block = freshness.get("award_events") if isinstance(freshness, Mapping) else None
    if not isinstance(block, Mapping):
        return "source_unavailable"
    status = str(block.get("status") or "").strip().lower()
    return {"ok": "current", "partial": "partial", "stale": "stale"}.get(status, "source_unavailable")


def _budget_rail(workspace: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(workspace, Mapping):
        return {"state": "source_unavailable"}
    freshness = workspace.get("freshness")
    block = freshness.get("budget") if isinstance(freshness, Mapping) else None
    failure_state = block.get("failure_state") if isinstance(block, Mapping) else None
    if failure_state in ("projection_missing", "source_unavailable"):
        return {"state": failure_state}
    return {"state": "source_unavailable"}


def _current_platforms_for_program(
    graph: Mapping[str, Any], program_id: str, *, analysis_as_of: datetime | None, at: datetime,
) -> list[dict[str, Any]]:
    retired = po.retired_row_ids(graph.get("overrides") or [], analysis_as_of)
    current_ids = po.current_identities(
        graph.get("platforms") or [], id_key="id", analysis_as_of=analysis_as_of, retired_ids=retired,
    )
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in graph.get("platforms") or []:
        if row.get("program_id") == program_id:
            by_id[row.get("id")].append(row)
    resolved: list[dict[str, Any]] = []
    for platform_id, rows_for_id in by_id.items():
        if platform_id not in current_ids:
            continue
        row = po.resolve_revision(rows_for_id, at=at)
        if row is not None:
            resolved.append(row)
    return resolved


def _latest_platform(
    graph: Mapping[str, Any], program_id: str, *, analysis_as_of: datetime | None, at: datetime,
) -> tuple[str | None, str | None]:
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    for row in _current_platforms_for_program(graph, program_id, analysis_as_of=analysis_as_of, at=at):
        valid_from = po.strict_datetime(row.get("valid_from"))
        valid_to_raw = row.get("valid_to")
        valid_to = None if valid_to_raw is None else po.strict_datetime(valid_to_raw)
        if valid_from is not None and valid_from <= at and (valid_to is None or at < valid_to):
            candidates.append((valid_from, row.get("id") or "", row))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0], item[1]))
    best = candidates[-1][2]
    return best.get("id"), best.get("name")


def _program_identity_rail(
    graph: Mapping[str, Any], program_id: str, *, analysis_as_of: datetime | None, at: datetime,
) -> dict[str, Any]:
    state, _ = po.derive_review_coverage(
        graph, scope="program_identity", subject_type="program", subject_id=program_id, analysis_as_of=analysis_as_of,
    )
    if state != "reviewed":
        return {
            "state": state, "program_id": None, "program_revision": None, "name": None, "phase": None,
            "sponsor_agency": None, "latest_platform_id": None, "latest_platform_name": None, "evidence_refs": [],
        }
    rows_for_id = [row for row in graph.get("programs") or [] if row.get("id") == program_id]
    resolved = po.resolve_revision(rows_for_id, at=at)
    if resolved is None:
        return {
            "state": "not_reviewed", "program_id": None, "program_revision": None, "name": None, "phase": None,
            "sponsor_agency": None, "latest_platform_id": None, "latest_platform_name": None, "evidence_refs": [],
        }
    latest_platform_id, latest_platform_name = _latest_platform(graph, program_id, analysis_as_of=analysis_as_of, at=at)
    return {
        "state": "reviewed",
        "program_id": program_id,
        "program_revision": resolved.get("revision"),
        "name": resolved.get("name"),
        "phase": resolved.get("phase"),
        "sponsor_agency": resolved.get("sponsor_agency"),
        "latest_platform_id": latest_platform_id,
        "latest_platform_name": latest_platform_name,
        "evidence_refs": sorted(resolved.get("evidence_refs") or []),
    }


def _capability_rail(
    graph: Mapping[str, Any], program_id: str, *, analysis_as_of: datetime | None, at: datetime,
) -> dict[str, Any]:
    state, _ = po.derive_review_coverage(
        graph, scope="capability", subject_type="program", subject_id=program_id, analysis_as_of=analysis_as_of,
    )
    if state != "reviewed":
        return {
            "state": state, "capability_id": None, "capability_revision": None, "name": None,
            "need_statement": None, "program_capability_link_id": None, "evidence_refs": [],
        }
    link = po.current_program_capability_link(graph, program_id, analysis_as_of=analysis_as_of)
    if link is None:
        return {
            "state": "not_reviewed", "capability_id": None, "capability_revision": None, "name": None,
            "need_statement": None, "program_capability_link_id": None, "evidence_refs": [],
        }
    capability_id = link.get("capability_id")
    rows_for_id = [row for row in graph.get("capabilities") or [] if row.get("id") == capability_id]
    resolved = po.resolve_revision(rows_for_id, at=at) or {}
    evidence_refs = sorted(set(resolved.get("evidence_refs") or []) | set(link.get("evidence_refs") or []))
    return {
        "state": "reviewed",
        "capability_id": capability_id,
        "capability_revision": resolved.get("revision"),
        "name": resolved.get("name"),
        "need_statement": resolved.get("need_statement"),
        "program_capability_link_id": link.get("link_id"),
        "evidence_refs": evidence_refs,
    }


def _awards_rail(
    graph: Mapping[str, Any] | None, program_id: str, *,
    analysis_as_of: datetime | None, workspace: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_state = _awards_source_state(workspace)
    if graph is None:
        return {
            "source_state": source_state, "link_state": "not_reviewed",
            "program_event_link_ids": [], "event_ids": [],
        }
    retired = po.retired_row_ids(graph.get("overrides") or [], analysis_as_of)
    current_all = po.current_content_addressed_rows(
        graph.get("program_event_links") or [], id_key="link_id", analysis_as_of=analysis_as_of, retired_ids=retired,
    )
    current_for_program = [row for row in current_all if row.get("program_id") == program_id]
    all_for_program_ids = {
        row.get("link_id") for row in graph.get("program_event_links") or [] if row.get("program_id") == program_id
    }
    cited_events = {row.get("event_id") for row in current_for_program}

    conflicted = False
    for conflict in po.visible_rows(graph.get("conflicts") or [], analysis_as_of):
        if conflict.get("scope") != "program_event_link":
            continue
        # A conflict CLEARED via retire_row (freeze SS5) is visible-but-
        # retired and must never block re-derivation -- the same currency
        # law every other retire-aware check in this module already honors.
        if conflict.get("conflict_id") in retired:
            continue
        if conflict.get("subject_type") == "award_event" and conflict.get("subject_id") in cited_events:
            conflicted = True
            break
        if set(conflict.get("candidate_row_ids") or []) & all_for_program_ids:
            conflicted = True
            break

    if conflicted:
        link_state = "conflicted"
    elif current_for_program:
        link_state = "reviewed"
    else:
        link_state, _ = po.derive_review_coverage(
            graph, scope="program_event_link", subject_type="program", subject_id=program_id,
            analysis_as_of=analysis_as_of,
        )

    if link_state != "reviewed":
        # SS4 non-reviewed payload law: for the awards rail the review-gated
        # state is link_state alone -- every other payload key is null/empty
        # when it is not "reviewed". Attribution stays withheld under a
        # declared conflict (or any not_reviewed/reviewed_none state): the
        # typed state IS the content, never a leaked pointer.
        return {
            "source_state": source_state, "link_state": link_state,
            "program_event_link_ids": [], "event_ids": [],
        }
    return {
        "source_state": source_state,
        "link_state": link_state,
        "program_event_link_ids": sorted({row.get("link_id") for row in current_for_program if row.get("link_id")}),
        "event_ids": sorted({e for e in cited_events if e}),
    }


def _participants_rail(
    graph: Mapping[str, Any], program_id: str, *,
    analysis_as_of: datetime | None, at: datetime, atlas_index: Mapping[str, list[tuple[str, str | None]]],
) -> dict[str, Any]:
    state, _ = po.derive_review_coverage(
        graph, scope="participants", subject_type="program", subject_id=program_id, analysis_as_of=analysis_as_of,
    )
    rows: list[dict[str, Any]] = []
    if state == "reviewed":
        retired = po.retired_row_ids(graph.get("overrides") or [], analysis_as_of)
        current = po.current_content_addressed_rows(
            graph.get("role_assertions") or [], id_key="id", analysis_as_of=analysis_as_of, retired_ids=retired,
        )
        for row in current:
            if row.get("program_id") != program_id:
                continue
            valid_to_raw = row.get("valid_to")
            valid_to = None if valid_to_raw is None else po.strict_datetime(valid_to_raw)
            historical = valid_to is not None and valid_to <= at
            entity_id = row.get("entity_id")
            matches = atlas_index.get(entity_id, [])
            if len(matches) == 1:
                ticker, public_security_state = matches[0]
                issuer_path_state = "reviewed"
                public_security = public_security_state
                central_id = f"central:{ticker}"
            else:
                issuer_path_state = "not_asserted"
                public_security = None
                central_id = None
            rows.append({
                "role_assertion_id": row.get("id"),
                "entity_id": entity_id,
                "role": row.get("role"),
                "role_scope": row.get("role_scope"),
                "shared_scope": row.get("shared_scope"),
                "historical": historical,
                "issuer_path_state": issuer_path_state,
                "public_security": public_security,
                "central_id": central_id,
                "evidence_refs": sorted(row.get("evidence_refs") or []),
            })
        rows.sort(key=lambda item: item["role_assertion_id"] or "")
    return {
        "state": state,
        "rows": rows,
        "participation_limitation": PARTICIPATION_LIMITATION,
        "allocation_limitation": ALLOCATION_LIMITATION,
    }


def _milestones_rail(
    graph: Mapping[str, Any], program_id: str, *,
    analysis_as_of: datetime | None, analysis_cutoff: datetime, as_of_date: date,
) -> dict[str, Any]:
    state, _ = po.derive_review_coverage(
        graph, scope="milestones", subject_type="program", subject_id=program_id, analysis_as_of=analysis_as_of,
    )
    rows: list[dict[str, Any]] = []
    if state == "reviewed":
        retired = po.retired_row_ids(graph.get("overrides") or [], analysis_as_of)
        current = po.current_content_addressed_rows(
            graph.get("milestones") or [], id_key="id", analysis_as_of=analysis_as_of, retired_ids=retired,
        )
        for row in current:
            if row.get("program_id") != program_id:
                continue
            valid_to_raw = row.get("valid_to")
            valid_to = None if valid_to_raw is None else po.strict_datetime(valid_to_raw)
            if valid_to is not None and valid_to <= analysis_cutoff:
                continue
            temporal_kind = row.get("temporal_kind")
            if temporal_kind == "date":
                d = po.full_date(row.get("date"))
                if d is not None and d < as_of_date:
                    continue
            else:
                window = row.get("window") or {}
                d = po.full_date(window.get("to"))
                if d is not None and d < as_of_date:
                    continue
            entry: dict[str, Any] = {
                "milestone_id": row.get("id"),
                "kind": row.get("kind"),
                "title": row.get("title"),
                "temporal_kind": temporal_kind,
                "evidence_refs": sorted(row.get("evidence_refs") or []),
            }
            if temporal_kind == "date":
                entry["date"] = row.get("date")
            else:
                entry["window"] = row.get("window")
            rows.append(entry)
        rows.sort(key=lambda item: item["milestone_id"] or "")
    return {"state": state, "rows": rows}


def compose_program_dossier_bundle(
    *,
    ontology_graph: Mapping[str, Any] | None,
    as_of: str,
    generated_at: str | None = None,
    workspace: Mapping[str, Any] | None = None,
    identity_atlas: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose the D5 dossier bundle (freeze SS4).

    ``ontology_graph`` must already be the CERTIFIED, loaded ontology (i.e.
    the result of :func:`program_ontology.load_program_ontology_graph`, or
    ``None`` on absence/refused certification -- callers catch
    :class:`program_ontology.OntologyInputError` themselves per SS4, this
    composer never re-derives certification).
    """
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    if ontology_graph is None:
        return _empty_dossier_bundle(as_of=as_of, generated_at=generated_at, ontology_graph_id=None)

    as_of_date = date.fromisoformat(as_of)
    analysis_cutoff = po.analysis_as_of(as_of)
    at = analysis_cutoff
    atlas_index = _build_atlas_index(identity_atlas)
    retired = po.retired_row_ids(ontology_graph.get("overrides") or [], analysis_cutoff)
    current_program_ids = sorted(po.current_identities(
        ontology_graph.get("programs") or [], id_key="id", analysis_as_of=analysis_cutoff, retired_ids=retired,
    ))

    dossiers = []
    for program_id in current_program_ids:
        dossiers.append({
            "program_id": program_id,
            "program_identity": _program_identity_rail(ontology_graph, program_id, analysis_as_of=analysis_cutoff, at=at),
            "capability": _capability_rail(ontology_graph, program_id, analysis_as_of=analysis_cutoff, at=at),
            "awards": _awards_rail(ontology_graph, program_id, analysis_as_of=analysis_cutoff, workspace=workspace),
            "budget": _budget_rail(workspace),
            "participants": _participants_rail(
                ontology_graph, program_id, analysis_as_of=analysis_cutoff, at=at, atlas_index=atlas_index,
            ),
            "economic_relationships": {"state": "not_asserted"},
            "milestones": _milestones_rail(
                ontology_graph, program_id, analysis_as_of=analysis_cutoff, analysis_cutoff=analysis_cutoff,
                as_of_date=as_of_date,
            ),
        })

    payload = {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "content_id": "",
        "generated_at": generated_at,
        "as_of": as_of,
        "ontology_graph_id": ontology_graph.get("graph_id"),
        "authority": dict(po.AUTHORITY),
        "dossiers": dossiers,
        "limitations": list(LIMITATIONS),
    }
    payload["content_id"] = dossier_content_id(payload)
    return payload


def _program_dossier_validator() -> Any:
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "contracts" / "government_revenue" / "government_program_dossier.v1.schema.json"
    )
    return Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")), format_checker=FormatChecker(),
    )


def is_valid_program_dossier_payload(value: Any) -> bool:
    """Validate a bundle against its schema plus its own content-id law.

    Mirrors ``engine.government_revenue.dossiers.is_valid_dossier_payload`` --
    the site-only render path uses this to verify committed canonical bytes
    before mirroring them, never recomputing the bundle itself.
    """
    if not isinstance(value, Mapping):
        return False
    try:
        if any(_program_dossier_validator().iter_errors(value)):
            return False
        if dossier_content_id(value) != value.get("content_id"):
            return False
    except (TypeError, ValueError, OSError):
        return False
    return True


__all__ = [
    "CONTRACT",
    "SCHEMA_VERSION",
    "CONTENT_ID_PREFIX",
    "PARTICIPATION_LIMITATION",
    "ALLOCATION_LIMITATION",
    "dossier_content_id",
    "compose_program_dossier_bundle",
    "is_valid_program_dossier_payload",
]
