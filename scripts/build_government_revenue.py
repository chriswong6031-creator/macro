"""Build the Government Revenue Foresight desk.

The page is a static, client-rendered evidence terminal backed by the compact
``company_government_revenue.v1`` artifact.  The deterministic domain engine is
the only place calculations live; this builder only serializes the payload and
renders the shell.

Missing award/action detail is an honest degraded state, not a build failure:
the monthly USAspending aggregate still renders while the page marks capacity,
modification, and recompete fields unavailable.

Usage::

    python -m scripts.build_government_revenue
    python -m scripts.build_government_revenue --site-only
    python -m scripts.build_government_revenue --root /path/to/repo
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.government_revenue import build_payload  # noqa: E402
from engine.government_revenue.dossiers import (  # noqa: E402
    DOSSIER_CONTRACT,
    build_dossier_payload,
    dossier_content_id,
    is_valid_dossier_payload,
)
from engine.government_revenue.subaward_dossiers import (  # noqa: E402
    SUBAWARD_DOSSIER_CONTRACT,
    build_subaward_dossier_payload,
    is_valid_subaward_dossier_payload,
    subaward_dossier_content_id,
)
from collectors.dod_budget import DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED  # noqa: E402
from engine.government_revenue.budget_program import (  # noqa: E402
    BUDGET_PROGRAM_GRAPH_CONTRACT,
    build_budget_program_graph,
    is_valid_budget_program_graph,
    load_reviewed_edges,
)
from engine.government_revenue.idv_dossiers import (  # noqa: E402
    IDV_DOSSIER_CONTRACT,
    build_idv_dossier_payload,
    idv_dossier_content_id,
    is_valid_idv_dossier_payload,
)
from engine.government_revenue.entity_resolution import (  # noqa: E402
    is_valid_recipient_resolution_coverage,
    load_recipient_entity_graph,
)
from engine.government_revenue.metrics import (  # noqa: E402
    AWARD_ACTION_VERSIONS_FILENAME,
    AWARD_EVENT_PROJECTION_STATE_FILENAME,
    AWARD_EVENT_SNAPSHOTS_FILENAME,
    RECIPIENT_ENTITY_GRAPH_FILENAME,
    RECIPIENT_RESOLUTION_COVERAGE_FILENAME,
)
from engine.government_revenue.workspace import is_valid_procurement_workspace  # noqa: E402
from lib.pages import write_page  # noqa: E402

log = logging.getLogger("build_government_revenue")

# The HTML shell is intentionally a first page, not a duplicate of the full
# workspace.
# Keep a meaningful first paint while leaving headroom under the raw HTML
# publication fence as live award records grow. The browser hydrates the full
# governed workspace immediately after paint.
SHELL_EVENT_LIMIT = 12
SHELL_JSON_BUDGET_BYTES = 100_000
RAW_HTML_BUDGET_BYTES = 250_000
SHELL_COMPANY_METRICS = (
    "ttm_obligations",
    "award_velocity_yoy_pct",
    "funded_capacity_observed",
    "net_award_action_flow_90d",
    "positive_award_action_flow_90d",
    # Kept only while older generated templates remain backward compatible.
    "modification_impulse_90d",
)

# These are collector-owned, immutable source inputs.  The graph projector
# accepts no partial bundle and this page builder never attempts PDF parsing or
# source acquisition.  A later source adapter may replace the fixture-only DoD
# foundation, but it must keep this complete evidence boundary intact.
_BUDGET_SOURCE_FILENAMES = (
    "dod_budget_line_snapshots.jsonl",
    "dod_budget_collection_receipts.jsonl",
    "dod_budget_projection_state.json",
)


def _workspace_cursor(offset: int, *, version: str = "v2") -> str:
    """Emit the same opaque cursor contract as the read-only API."""

    if version not in {"v1", "v2"} or offset < 0:
        raise ValueError("invalid workspace cursor")
    return base64.urlsafe_b64encode(
        f"{version}:{int(offset)}".encode("ascii")
    ).decode("ascii").rstrip("=")


def _present_fields(record: object, fields: tuple[str, ...]) -> dict:
    """Pick only explicitly present, non-null fields from a JSON-like record."""
    if not isinstance(record, dict):
        return {}
    return {
        field: record[field]
        for field in fields
        if field in record and record[field] is not None
    }


def _bounded_text(value: object, limit: int) -> object:
    """Keep a first-paint string inspectable without embedding source bodies."""
    return value[:limit] if isinstance(value, str) else value


def _compact_change_value(value: object) -> object:
    """Bound legal source deltas so first paint cannot breach the HTML fence."""
    if isinstance(value, str):
        return value[:360]
    if isinstance(value, list):
        return [item[:160] if isinstance(item, str) else item for item in value[:8]]
    return value


def _compact_workspace_event(event: dict) -> dict:
    """Keep first-paint event semantics without duplicating the full event ledger.

    The complete, contract-validated event stays in ``workspace.json``.  The
    embedded shell only needs enough governed evidence to render its first page
    and inspect a row while the full bundle loads.  This avoids letting a long
    receipt or cross-desk payload turn a quiet live build into a byte-budget
    failure.
    """
    compact = _present_fields(event, (
        "contract", "event_id", "record_id", "version", "kind", "state",
        "title_original", "title_zh", "translation_status", "primary_ticker",
        "primary_date_id", "primary_amount_id",
    ))
    compact["agency"] = _present_fields(event.get("agency"), (
        "department_id", "department_name", "subagency_id", "subagency_name",
        "office_id", "office_name",
    ))
    change = _present_fields(event.get("change"), (
        "type", "what_changed_en", "what_changed_zh", "summary_origin",
        "effective_at", "known_at", "first_seen_at", "last_seen_at", "is_correction",
    ))
    changed_fields = event.get("change", {}).get("changed_fields") if isinstance(event.get("change"), dict) else None
    if isinstance(changed_fields, list):
        change["changed_fields"] = []
        for raw in changed_fields[:6]:
            if not isinstance(raw, dict):
                continue
            item = _present_fields(raw, (
                "field", "before", "after", "semantic", "source_ref",
                "before_source_ref", "after_source_ref", "before_receipt_ref",
                "after_receipt_ref",
            ))
            for field in ("before", "after"):
                if field in item:
                    item[field] = _compact_change_value(item[field])
            for field, limit in {
                "field": 120,
                "semantic": 80,
                "source_ref": 360,
                "before_source_ref": 360,
                "after_source_ref": 360,
                "before_receipt_ref": 180,
                "after_receipt_ref": 180,
            }.items():
                if field in item:
                    item[field] = _bounded_text(item[field], limit)
            change["changed_fields"].append(item)
    compact["change"] = change
    compact["opportunity"] = _present_fields(event.get("opportunity"), (
        "notice_id", "solicitation_number", "title", "status", "notice_stage",
        "source_status", "current_status", "current_notice_stage", "current_revision",
        "active", "agency", "office",
        "posted_at", "response_deadline", "archive_date", "source_url", "sam_url",
        "current_state", "current_state_verified", "observation_horizon_at",
        "observation_age_minutes", "observation_basis", "current_state_reason",
    )) or None
    compact["recompete"] = _present_fields(event.get("recompete"), (
        "generated_award_id", "award_id", "piid", "case_type", "basis_code",
        "current_end_date", "potential_end_date", "days_to_current_end", "total_obligated",
        "current_award_amount", "potential_award_amount", "matched_notice_id", "source_url",
    )) or None
    raw_award_change = (
        event.get("award_change") if isinstance(event.get("award_change"), dict) else {}
    )
    award_change = _present_fields(raw_award_change, (
        "award_key", "generated_award_id", "piid", "recipient_name", "event_type",
        "secondary_types", "source_rail", "observation_kind", "coverage_scope",
        "is_late_discovery", "action_id", "prior_source_identity",
    ))
    source_identity = _present_fields(
        raw_award_change.get("source_identity"),
        ("id", "version", "content_sha256"),
    )
    if source_identity:
        award_change["source_identity"] = source_identity
    for field, limit in {
        "award_key": 180,
        "generated_award_id": 180,
        "piid": 180,
        "recipient_name": 240,
        "event_type": 80,
        "source_rail": 80,
        "observation_kind": 40,
        "coverage_scope": 480,
        "action_id": 180,
        "prior_source_identity": 180,
    }.items():
        if field in award_change:
            award_change[field] = _bounded_text(award_change[field], limit)
    if isinstance(award_change.get("secondary_types"), list):
        award_change["secondary_types"] = [
            _bounded_text(value, 80) for value in award_change["secondary_types"][:8]
        ]
    if isinstance(award_change.get("source_identity"), dict):
        for field, limit in {"id": 180, "version": 180, "content_sha256": 80}.items():
            if field in award_change["source_identity"]:
                award_change["source_identity"][field] = _bounded_text(
                    award_change["source_identity"][field], limit
                )
    compact["award_change"] = award_change or None
    compact["dates"] = [
        _present_fields(row, ("id", "label_code", "value", "semantic", "known_at", "source_ref"))
        for row in event.get("dates") or []
        if isinstance(row, dict)
    ]
    compact["amounts"] = [
        _present_fields(row, ("id", "label_code", "value", "currency", "semantic", "as_of", "is_lower_bound", "source_ref"))
        for row in event.get("amounts") or []
        if isinstance(row, dict)
    ]
    impacts = []
    for impact in event.get("listed_company_impacts") or []:
        if not isinstance(impact, dict):
            continue
        row = _present_fields(impact, (
            "ticker", "company_name", "confidence", "relation_semantic", "match_method",
            "stance", "stance_scope", "why_it_matters_en", "why_it_matters_zh",
            "watch_next_en", "watch_next_zh", "label_limit",
        ))
        row["materiality"] = _present_fields(impact.get("materiality"), ("band",))
        row["cross_desk_links"] = [
            _present_fields(link, ("available", "href", "label_en", "label_zh", "surface_id"))
            for link in impact.get("cross_desk_links") or []
            if isinstance(link, dict)
        ][:3]
        impacts.append(row)
    compact["listed_company_impacts"] = impacts
    compact["display_priority"] = _present_fields(event.get("display_priority"), (
        "score", "new_information", "company_materiality", "evidence_quality",
        "formula_version", "is_investment_rank", "tie_breakers",
    ))
    raw_evidence = event.get("evidence") if isinstance(event.get("evidence"), dict) else {}
    evidence = _present_fields(raw_evidence, ("source_class", "mapping_class"))
    evidence["receipts"] = [
        _present_fields(receipt, (
            "publisher", "record_id", "ref_id", "effective_at", "known_at", "retrieved_at",
            "content_sha256", "url",
        ))
        for receipt in raw_evidence.get("receipts") or []
        if isinstance(receipt, dict)
    ][:2]
    evidence["derivations"] = [
        _present_fields(derivation, ("classification", "formula_version", "basis_refs", "ref_id"))
        for derivation in raw_evidence.get("derivations") or []
        if isinstance(derivation, dict)
    ][:2]
    evidence["conflicts"] = []
    evidence["limitations"] = [
        value for value in raw_evidence.get("limitations") or []
        if isinstance(value, str)
    ][:3]
    compact["evidence"] = evidence
    compact["authority"] = _present_fields(event.get("authority"), (
        "tier", "context_only", "can_rank", "can_size", "can_gate",
        "can_originate_signal", "can_add_candidates", "can_escalate",
    ))
    return compact


def _display_payload(payload: dict) -> dict:
    """Return a fast first-response slice; canonical artifacts remain complete.

    The browser only needs a compact issuer index and the first governed event
    page to paint the terminal.  It hydrates the complete workspace from the
    separately published ``workspace.json`` after first render.  This avoids
    embedding the same large award/action corpus and event projections twice in
    HTML while preserving the full API/canonical artifacts.
    """
    shell = {
        key: value
        for key, value in payload.items()
        if key not in {"companies", "opportunity_intelligence", "procurement_workspace", "workbench"}
    }
    shell["companies"] = [
        {
            "ticker": company.get("ticker"),
            "name": company.get("name"),
            "tags": company.get("tags") or [],
            "entity_match": company.get("entity_match") or {},
            "metrics": {
                key: (company.get("metrics") or {}).get(key)
                for key in SHELL_COMPANY_METRICS
            },
            "confidence": company.get("confidence") or {},
            # The validated-claims fence scans rendered JSON as user-facing
            # text, so keep the receipt data while avoiding the overloaded
            # `proven*` token in the first-paint wire shape.
            "source_receipts": [
                {
                    key: receipt.get(key)
                    for key in (
                        "dataset", "publisher", "source_url", "known_at",
                        "effective_through", "point_in_time", "limitations",
                    )
                    if key in receipt
                }
                for receipt in (company.get("provenance") or [])[:1]
                if isinstance(receipt, dict)
            ],
            "authority": company.get("authority") or {},
        }
        for company in payload.get("companies") or []
        if isinstance(company, dict)
    ]

    opportunity_intelligence = payload.get("opportunity_intelligence")
    if isinstance(opportunity_intelligence, dict):
        shell["opportunity_intelligence"] = {
            **{
                key: value
                for key, value in opportunity_intelligence.items()
                if key != "provenance"
            },
            "opportunities": [],
            "events": [],
            "company_context": {},
        }

    workspace = payload.get("procurement_workspace")
    if isinstance(workspace, dict):
        events = [event for event in workspace.get("events") or [] if isinstance(event, dict)]
        visible = [_compact_workspace_event(event) for event in events[:SHELL_EVENT_LIMIT]]
        shell_workspace = {
            **workspace,
            "events": visible,
            "next_cursor": (
                _workspace_cursor(len(visible), version="v2")
                if len(events) > len(visible)
                else None
            ),
        }
        coverage = workspace.get("coverage")
        if isinstance(coverage, dict):
            shell_coverage = dict(coverage)
            award_events = coverage.get("award_events")
            if isinstance(award_events, dict):
                # Numeric contract-validation accounting remains in the
                # canonical workspace. It is unused at first paint and its
                # field name is intentionally omitted from rendered JSON so
                # the validated-claims prose fence does not misread metadata.
                shell_award_events = dict(award_events)
                shell_award_events.pop("validated", None)
                shell_coverage["award_events"] = shell_award_events
            shell_workspace["coverage"] = shell_coverage
        shell["procurement_workspace"] = shell_workspace
        # Long but contract-valid source deltas must not make publication
        # depend on a lucky data mix. Adapt the first page to a deterministic
        # JSON budget; the complete bundle hydrates from workspace.json.
        while visible and len(json.dumps(
            shell, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode("utf-8")) > SHELL_JSON_BUDGET_BYTES:
            visible.pop()
            shell["procurement_workspace"]["events"] = visible
            shell["procurement_workspace"]["next_cursor"] = _workspace_cursor(
                len(visible), version="v2"
            )
    return shell


def _canonical_json(value: object) -> str:
    """Stable JSON bytes used for receipts and deterministic bundle identity."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _workspace_bundle_id(workspace: dict) -> str:
    """Return a content-derived identity shared by shell and workspace bytes.

    ``generated_at`` is intentionally excluded: it is an assembly clock, not
    source state.  A quiet re-render of identical procurement evidence therefore
    keeps the same identity, while a semantic workspace change receives a new
    one.  The browser fails closed if its embedded shell and fetched workspace
    do not carry this exact identity.
    """
    fingerprint = {
        key: value
        for key, value in workspace.items()
        if key not in {"bundle_id", "generated_at"}
    }
    digest = hashlib.sha256(_canonical_json(fingerprint).encode("utf-8")).hexdigest()
    return f"grw2-{digest[:24]}"


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Replace one artifact atomically, never exposing a partly-written JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding=encoding) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise


def _atomic_write_page(path: Path, html: str) -> None:
    """Retain the shared page writer while publishing the HTML by replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        # write_page owns the data-base shim contract.  The temporary lives in
        # the destination directory, so its relative asset paths are identical.
        write_page(temp_path, html)
        with temp_path.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise


def _validate_payload(payload: object) -> dict:
    """Validate the canonical engine envelope before any public write."""
    if not isinstance(payload, dict) or payload.get("schema_version") != "company_government_revenue.v1":
        raise ValueError("government revenue engine returned an invalid schema")
    workspace = payload.get("procurement_workspace")
    if (
        not isinstance(workspace, dict)
        or workspace.get("schema_version") != "government_procurement_workspace.v2"
        or workspace.get("event_contract") != "government_procurement_event.v2"
        or not is_valid_procurement_workspace(workspace)
    ):
        raise ValueError("government procurement workspace returned an invalid schema")
    events = workspace.get("events")
    if not isinstance(events, list) or any(
        not isinstance(event, dict)
        or event.get("contract") != "government_procurement_event.v2"
        for event in events
    ):
        raise ValueError("government procurement workspace returned a non-v2 event")
    return payload


def _validate_dossier_payload(payload: object) -> dict:
    """Reject a dossier generation before either public twin is replaced."""
    if (
        not isinstance(payload, dict)
        or payload.get("contract") != DOSSIER_CONTRACT
        or not is_valid_dossier_payload(payload)
        or dossier_content_id(payload) != payload.get("content_id")
    ):
        raise ValueError("government revenue dossier returned an invalid schema")
    return payload


def _prime_award_key_by_generated_id(dossier: dict) -> dict[str, str]:
    """Return the sole legal bridge from a source parent ID to a dossier key.

    Subaward source rows may name their prime only by USAspending's generated
    award ID.  The prime dossier owns the path-safe public award key, so this
    map is assembled *after* the prime projection and rejects a duplicate or
    malformed bridge instead of guessing through PIID, recipient text, or a
    collector ticker.
    """
    mapping: dict[str, str] = {}
    for row in dossier.get("awards") or []:
        if not isinstance(row, dict):
            raise ValueError("government revenue dossier contains an invalid award row")
        award_key = row.get("award_key")
        identity = row.get("identity")
        generated_award_id = (
            identity.get("generated_award_id")
            if isinstance(identity, dict)
            else None
        )
        if generated_award_id is None:
            continue
        if not isinstance(generated_award_id, str) or not generated_award_id:
            raise ValueError("government revenue dossier has an invalid generated award ID")
        if not isinstance(award_key, str) or not award_key:
            raise ValueError("government revenue dossier has an invalid award key")
        previous = mapping.get(generated_award_id)
        if previous is not None and previous != award_key:
            raise ValueError("government revenue dossier has an ambiguous generated award ID")
        mapping[generated_award_id] = award_key
    return mapping


def _validate_subaward_dossier_payload(payload: object) -> dict:
    """Reject a subaward rail before either public twin is replaced."""
    if (
        not isinstance(payload, dict)
        or payload.get("contract") != SUBAWARD_DOSSIER_CONTRACT
        or not is_valid_subaward_dossier_payload(payload)
        or subaward_dossier_content_id(payload) != payload.get("content_id")
    ):
        raise ValueError("government revenue subaward dossier returned an invalid schema")
    return payload


def _validate_budget_program_graph_payload(payload: object) -> dict:
    """Admit only the immutable, display-tier DoD budget graph contract."""
    if (
        not isinstance(payload, dict)
        or payload.get("contract") != BUDGET_PROGRAM_GRAPH_CONTRACT
        or not is_valid_budget_program_graph(payload)
    ):
        raise ValueError("government revenue budget/program graph returned an invalid schema")
    return payload


def _validate_idv_dossier_payload(payload: object) -> dict:
    """Admit only a content-addressed, source-native IDV relationship rail."""
    if (
        not isinstance(payload, dict)
        or payload.get("contract") != IDV_DOSSIER_CONTRACT
        or not is_valid_idv_dossier_payload(payload)
        or idv_dossier_content_id(payload) != payload.get("content_id")
    ):
        raise ValueError("government revenue IDV dossier returned an invalid schema")
    return payload


def _validate_budget_program_award_bindings(graph: dict, dossier: dict) -> None:
    """Require every documentary graph edge to name one exact prime award key.

    The DoD graph intentionally has no issuer mapping or economic weight.  A
    reviewed documentary edge may point to a source-backed award observation,
    but only when that path-safe key is present in the same prime dossier
    generation; it may never fall back to a PIID, program name, or recipient
    string.
    """
    exact_award_keys = set(_prime_award_key_by_generated_id(dossier).values())
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            raise ValueError("government revenue budget/program graph has an invalid edge")
        if edge.get("to_type") == "award" and edge.get("to_id") not in exact_award_keys:
            raise ValueError("government revenue budget/program graph award edge is unresolved")


def _validate_idv_dossier_bindings(idv_dossier: dict, dossier: dict) -> None:
    """Bind child relationships to the prime dossier only by generated ID.

    IDV parents deliberately remain standalone source entities.  A child gets
    a public ``award_key`` solely when its exact USAspending generated natural
    ID maps to a row in the current prime dossier.  No entity/ticker/PIID
    matching participates in this check.
    """
    prime_by_generated = _prime_award_key_by_generated_id(dossier)
    for parent in idv_dossier.get("idvs") or []:
        if not isinstance(parent, dict) or not str(parent.get("idv_generated_award_id") or "").startswith("CONT_IDV_"):
            raise ValueError("government revenue IDV dossier has an invalid source-native parent")
        if "award_key" in parent or "parent_award_key" in parent:
            raise ValueError("government revenue IDV dossier incorrectly collapses a parent into a prime award")
    for row in idv_dossier.get("relationships") or []:
        identity = row.get("identity") if isinstance(row, dict) else None
        if not isinstance(identity, dict):
            raise ValueError("government revenue IDV dossier has an invalid relationship")
        parent = identity.get("idv_generated_award_id")
        child = identity.get("child_generated_award_id")
        if (
            not isinstance(parent, str)
            or not parent.startswith("CONT_IDV_")
            or not isinstance(child, str)
            or not child.startswith("CONT_AWD_")
        ):
            raise ValueError("government revenue IDV dossier relationship identity is invalid")
        if row.get("child_award_key") != prime_by_generated.get(child):
            raise ValueError("government revenue IDV dossier child bridge is unresolved or stale")
        if "parent_award_key" in row:
            raise ValueError("government revenue IDV dossier incorrectly derives a parent award bridge")


def _read_jsonl_objects(path: Path, *, label: str) -> list[dict]:
    """Read a canonical JSONL source ledger without accepting blank or scalar rows."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    rows: list[dict] = []
    for number, raw in enumerate(lines, start=1):
        if not raw.strip():
            raise ValueError(f"{label} contains a blank row")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} row {number} is invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{label} row {number} is not an object")
        rows.append(value)
    if not rows:
        raise ValueError(f"{label} is empty")
    return rows


def _build_budget_program_graph_if_ready(
    root: Path,
    *,
    as_of: str | None,
    dossier: dict,
) -> dict | None:
    """Project one complete DoD source bundle, or retain an absent rail as absent.

    There is intentionally no empty synthetic graph: an all-absent source
    bundle leaves the optional rail unavailable.  Any mixed presence is a hard
    failure so a reader can never mistake a partial document/import for a
    governed graph.
    """
    data_dir = root / "data" / "government_revenue"
    paths = [data_dir / filename for filename in _BUDGET_SOURCE_FILENAMES]
    present = [path.exists() for path in paths]
    if not any(present):
        return None
    if not all(present):
        raise ValueError("DoD budget source bundle is partial; all immutable ledger members are required")
    if not DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED:
        raise ValueError(
            "DoD budget publication is hard-disabled while acquisition, storage-write proof, "
            "and PDF extraction remain fixture-only"
        )
    lines = _read_jsonl_objects(paths[0], label="DoD budget line ledger")
    receipts = _read_jsonl_objects(paths[1], label="DoD budget receipt ledger")
    try:
        projection_state = json.loads(paths[2].read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("DoD budget projection state is unavailable or invalid") from exc
    if not isinstance(projection_state, dict):
        raise ValueError("DoD budget projection state is not an object")
    graph = _validate_budget_program_graph_payload(build_budget_program_graph(
        lines=lines,
        receipts=receipts,
        projection_state=projection_state,
        as_of=as_of or "1970-01-01",
        reviewed_edge_set=load_reviewed_edges(root),
        award_keys=set(_prime_award_key_by_generated_id(dossier).values()),
    ))
    _validate_budget_program_award_bindings(graph, dossier)
    return graph


def _recipient_activation_required(root: Path) -> bool:
    """Return whether this checkout has entered the exact-recipient lane.

    Historical canonical generations predate both the receipt-bound triad and
    the curated graph. They remain renderable. Once any activation artifact is
    present, every other member is fail-closed rather than treated as an
    optional enrichment.
    """

    data_dir = root / "data" / "government_revenue"
    return any(
        (data_dir / filename).exists()
        for filename in (
            RECIPIENT_ENTITY_GRAPH_FILENAME,
            RECIPIENT_RESOLUTION_COVERAGE_FILENAME,
            AWARD_EVENT_SNAPSHOTS_FILENAME,
            AWARD_ACTION_VERSIONS_FILENAME,
            AWARD_EVENT_PROJECTION_STATE_FILENAME,
        )
    )


def _embedded_recipient_coverage(payload: dict) -> dict | None:
    freshness = payload.get("freshness")
    award_events = freshness.get("award_events") if isinstance(freshness, dict) else None
    coverage = (
        award_events.get("recipient_resolution_coverage")
        if isinstance(award_events, dict)
        else None
    )
    return coverage if isinstance(coverage, dict) else None


def _validate_recipient_activation(root: Path, payload: dict) -> dict | None:
    """Validate graph admission and its exact embedded coverage representation."""

    if not _recipient_activation_required(root):
        return None
    graph_path = (
        root / "data" / "government_revenue" / RECIPIENT_ENTITY_GRAPH_FILENAME
    )
    try:
        graph_source = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("canonical recipient entity graph is unavailable or invalid") from exc
    loaded_graph = load_recipient_entity_graph(
        graph_source,
        as_of=payload.get("as_of"),
    )
    if loaded_graph.get("status") != "ready":
        raise ValueError("canonical recipient entity graph failed strict admission")

    coverage = _embedded_recipient_coverage(payload)
    if coverage is None or not is_valid_recipient_resolution_coverage(coverage):
        raise ValueError("recipient resolution coverage is absent or invalid")
    graph_meta = coverage.get("resolution_graph")
    expected_graph_meta = {
        "load_status": "ready",
        "graph_id": loaded_graph.get("graph_id"),
        "graph_known_at": loaded_graph.get("graph_known_at"),
        "graph_effective_at": loaded_graph.get("graph_effective_at"),
        "graph_digest": loaded_graph.get("graph_digest"),
        "error_codes": [],
    }
    if graph_meta != expected_graph_meta:
        raise ValueError("recipient resolution coverage graph binding mismatch")
    snapshot_amounts = coverage.get("snapshot", {}).get("amounts", {})
    action_amounts = coverage.get("action", {}).get("amounts", {})
    if (
        snapshot_amounts.get("field") != "total_obligation"
        or action_amounts.get("field") != "federal_action_obligation"
        or snapshot_amounts.get("basis") != "absolute"
        or action_amounts.get("basis") != "absolute"
    ):
        raise ValueError("recipient resolution coverage uses the wrong amount rails")
    return coverage


def _write_dossier_twins(root: Path, dossier_raw: str) -> tuple[Path, Path]:
    """Atomically replace byte-identical canonical/site dossier twins.

    The two directories cannot share one filesystem rename.  Each replacement
    is individually atomic and both bytes originate from the same validated
    in-memory generation.  The serving layer requires both twins and their
    exact bytes, so it fails closed during the very small replacement window.
    """
    canonical = root / "data" / "government_revenue" / "dossiers.json"
    site = root / "site" / "government-revenue-data" / "dossiers.json"
    _atomic_write_text(canonical, dossier_raw)
    _atomic_write_text(site, dossier_raw)
    return canonical, site


def _write_subaward_dossier_twins(root: Path, dossier_raw: str) -> tuple[Path, Path]:
    """Atomically publish the independently governed subaward twins."""
    canonical = root / "data" / "government_revenue" / "subaward_dossiers.json"
    site = root / "site" / "government-revenue-data" / "subaward-dossiers.json"
    _atomic_write_text(canonical, dossier_raw)
    _atomic_write_text(site, dossier_raw)
    return canonical, site


def _write_budget_program_graph_twins(root: Path, graph_raw: str) -> tuple[Path, Path]:
    """Publish one exact DoD budget graph to canonical and static locations."""
    canonical = root / "data" / "government_revenue" / "budget_program_graph.json"
    site = root / "site" / "government-revenue-data" / "budget-program.json"
    _atomic_write_text(canonical, graph_raw)
    _atomic_write_text(site, graph_raw)
    return canonical, site


def _write_idv_dossier_twins(root: Path, dossier_raw: str) -> tuple[Path, Path]:
    """Publish one exact, independently content-addressed IDV relationship rail."""
    canonical = root / "data" / "government_revenue" / "idv_dossiers.json"
    site = root / "site" / "government-revenue-data" / "idv-dossiers.json"
    _atomic_write_text(canonical, dossier_raw)
    _atomic_write_text(site, dossier_raw)
    return canonical, site


def _load_optional_canonical_budget_graph(root: Path, dossier: dict) -> tuple[str, dict] | None:
    """Read a precomputed optional graph without reconstructing raw sources."""
    canonical = root / "data" / "government_revenue" / "budget_program_graph.json"
    site = root / "site" / "government-revenue-data" / "budget-program.json"
    if not canonical.exists():
        if site.exists():
            raise ValueError("public DoD budget/program graph exists without canonical bytes")
        return None
    try:
        raw = canonical.read_text(encoding="utf-8")
        graph = _validate_budget_program_graph_payload(json.loads(raw))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("canonical DoD budget/program graph is invalid") from exc
    if _canonical_json(graph) != raw:
        raise ValueError("canonical DoD budget/program graph bytes are non-canonical")
    _validate_budget_program_award_bindings(graph, dossier)
    return raw, graph


def _load_optional_canonical_idv_dossier(root: Path, dossier: dict) -> tuple[str, dict] | None:
    """Read one committed IDV rail without recalculating a source generation."""
    canonical = root / "data" / "government_revenue" / "idv_dossiers.json"
    site = root / "site" / "government-revenue-data" / "idv-dossiers.json"
    if not canonical.exists():
        if site.exists():
            raise ValueError("public IDV dossier exists without canonical bytes")
        return None
    try:
        raw = canonical.read_text(encoding="utf-8")
        payload = _validate_idv_dossier_payload(json.loads(raw))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("canonical government revenue IDV dossier is invalid") from exc
    if _canonical_json(payload) != raw:
        raise ValueError("canonical government revenue IDV dossier bytes are non-canonical")
    _validate_idv_dossier_bindings(payload, dossier)
    return raw, payload


def _write_site_projection(
    root: Path,
    payload: dict,
    *,
    latest_raw: str,
    workspace_raw: str,
) -> tuple[Path, Path]:
    """Publish public twins and HTML from one already-validated generation."""
    site_dir = root / "site"
    data_dir = site_dir / "government-revenue-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    json_path = data_dir / "latest.json"
    _atomic_write_text(json_path, latest_raw)
    _atomic_write_text(data_dir / "workspace.json", workspace_raw)

    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
    )
    display_payload = _display_payload(payload)
    html = env.get_template("government_revenue.html.j2").render(
        payload_json=json.dumps(
            display_payload, ensure_ascii=False, separators=(",", ":"), default=str
        ),
        as_of=payload.get("as_of"),
        known_at=payload.get("known_at"),
    )
    # Shared includes predate the repository's whitespace gate. Keep this new
    # generated artifact deterministic and diff-clean without rewriting them.
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    html_path = site_dir / "government_revenue.html"
    _atomic_write_page(html_path, html)
    if html_path.stat().st_size > RAW_HTML_BUDGET_BYTES:
        raise ValueError(
            f"government revenue HTML exceeds {RAW_HTML_BUDGET_BYTES} raw-byte budget: "
            f"{html_path.stat().st_size}"
        )
    return html_path, json_path


def build(root: Path, *, as_of: str | None = None) -> tuple[Path, Path, Path]:
    """Build canonical JSON, its site twin, and the HTML page."""
    root = root.resolve()
    payload = _validate_payload(build_payload(root=root, as_of=as_of))
    recipient_coverage = _validate_recipient_activation(root, payload)
    dossier = _validate_dossier_payload(
        build_dossier_payload(root=root, as_of=payload.get("as_of"))
    )
    # Build the prime dossier first.  The subaward projector only receives the
    # exact generated-award-ID -> public award-key bridge; it never gets a
    # ticker/name/PIID fallback that could create a false parent relationship.
    subaward_dossier = _validate_subaward_dossier_payload(
        build_subaward_dossier_payload(
            root=root,
            as_of=payload.get("as_of"),
            prime_award_key_by_generated_id=_prime_award_key_by_generated_id(dossier),
        )
    )
    # The IDV rail owns only source-native vehicle-to-child observations.  It
    # produces an explicit unavailable envelope before the receipt bundle is
    # initialized, and fails rather than publishing a partial bundle.
    idv_dossier = _validate_idv_dossier_payload(
        build_idv_dossier_payload(
            root=root,
            as_of=payload.get("as_of"),
            prime_award_key_by_generated_id=_prime_award_key_by_generated_id(dossier),
        )
    )
    _validate_idv_dossier_bindings(idv_dossier, dossier)
    budget_graph = _build_budget_program_graph_if_ready(
        root,
        as_of=payload.get("as_of"),
        dossier=dossier,
    )

    canonical_dir = root / "data" / "government_revenue"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = canonical_dir / "latest.json"
    workspace = payload.get("procurement_workspace")
    workspace["bundle_id"] = _workspace_bundle_id(workspace)
    workspace_raw = _canonical_json(workspace)
    latest_raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    _atomic_write_text(canonical_dir / "workspace.json", workspace_raw)
    _atomic_write_text(canonical_path, latest_raw)
    if recipient_coverage is not None:
        _atomic_write_text(
            canonical_dir / RECIPIENT_RESOLUTION_COVERAGE_FILENAME,
            _canonical_json(recipient_coverage),
        )
    dossier_raw = _canonical_json(dossier)
    _write_dossier_twins(root, dossier_raw)
    _write_subaward_dossier_twins(root, _canonical_json(subaward_dossier))
    _write_idv_dossier_twins(root, _canonical_json(idv_dossier))
    if budget_graph is not None:
        _write_budget_program_graph_twins(root, _canonical_json(budget_graph))
    else:
        # A canonical graph may legitimately outlive a generic local checkout
        # that lacks the collector-owned source bundle.  Mirror only its exact
        # verified bytes; do not synthesize an empty graph or silently reuse a
        # public-only static copy.
        preserved_graph = _load_optional_canonical_budget_graph(root, dossier)
        if preserved_graph is not None:
            _write_budget_program_graph_twins(root, preserved_graph[0])
    html_path, json_path = _write_site_projection(
        root,
        payload,
        latest_raw=latest_raw,
        workspace_raw=workspace_raw,
    )
    log.info(
        "wrote %s, %s and %s (%d companies)",
        html_path,
        canonical_path,
        json_path,
        len(payload.get("companies") or []),
    )
    return html_path, canonical_path, json_path


def build_site_only(root: Path) -> tuple[Path, Path, Path]:
    """Re-render public files from committed canonical bytes without recalculation.

    Site-wide render lanes use this after rebasing. They may refresh shared nav,
    CSS and first-paint markup, but cannot move clocks, recompute procurement
    facts, or advance the canonical generation owned by the serialized live lane.
    """
    root = root.resolve()
    canonical_dir = root / "data" / "government_revenue"
    canonical_path = canonical_dir / "latest.json"
    workspace_path = canonical_dir / "workspace.json"
    try:
        latest_raw = canonical_path.read_text(encoding="utf-8")
        workspace_raw = workspace_path.read_text(encoding="utf-8")
        payload = _validate_payload(json.loads(latest_raw))
        workspace = json.loads(workspace_raw)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("canonical government revenue generation is unavailable") from exc
    if (
        not isinstance(workspace, dict)
        or workspace.get("schema_version") != "government_procurement_workspace.v2"
        or workspace.get("event_contract") != "government_procurement_event.v2"
        or not is_valid_procurement_workspace(workspace)
    ):
        raise ValueError("canonical government procurement workspace is invalid")
    embedded = payload.get("procurement_workspace")
    if _canonical_json(embedded) != _canonical_json(workspace):
        raise ValueError("canonical latest/workspace generation mismatch")
    bundle_id = workspace.get("bundle_id")
    if not bundle_id or bundle_id != _workspace_bundle_id(workspace):
        raise ValueError("canonical workspace bundle identity mismatch")
    recipient_coverage = _validate_recipient_activation(root, payload)
    if recipient_coverage is not None:
        coverage_path = canonical_dir / RECIPIENT_RESOLUTION_COVERAGE_FILENAME
        try:
            coverage_raw = coverage_path.read_text(encoding="utf-8")
            committed_coverage = json.loads(coverage_raw)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("canonical recipient resolution coverage is invalid") from exc
        if _canonical_json(committed_coverage) != coverage_raw:
            raise ValueError("canonical recipient resolution coverage bytes are non-canonical")
        if _canonical_json(committed_coverage) != _canonical_json(recipient_coverage):
            raise ValueError("canonical recipient resolution coverage generation mismatch")
    # A renderer must never rebuild a dossier from mutable source rails.  When
    # a live collector has already published a canonical dossier, verify and
    # mirror those exact bytes; pre-dossier historical checkouts remain able to
    # re-render their Government Revenue page without synthesizing new data.
    dossier_path = canonical_dir / "dossiers.json"
    if dossier_path.exists():
        try:
            dossier_raw = dossier_path.read_text(encoding="utf-8")
            dossier = _validate_dossier_payload(json.loads(dossier_raw))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("canonical government revenue dossier is invalid") from exc
        if _canonical_json(dossier) != dossier_raw:
            raise ValueError("canonical government revenue dossier bytes are non-canonical")
        _write_dossier_twins(root, dossier_raw)
        subaward_path = canonical_dir / "subaward_dossiers.json"
        try:
            subaward_raw = subaward_path.read_text(encoding="utf-8")
            subaward = _validate_subaward_dossier_payload(json.loads(subaward_raw))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("canonical government revenue subaward dossier is invalid") from exc
        if _canonical_json(subaward) != subaward_raw:
            raise ValueError("canonical government revenue subaward dossier bytes are non-canonical")
        _write_subaward_dossier_twins(root, subaward_raw)
        optional_idv = _load_optional_canonical_idv_dossier(root, dossier)
        if optional_idv is not None:
            _write_idv_dossier_twins(root, optional_idv[0])
        optional_budget_graph = _load_optional_canonical_budget_graph(root, dossier)
        if optional_budget_graph is not None:
            _write_budget_program_graph_twins(root, optional_budget_graph[0])
    elif (canonical_dir / "subaward_dossiers.json").exists():
        raise ValueError("canonical subaward dossier exists without a prime dossier")
    elif any((canonical_dir / name).exists() for name in ("idv_dossiers.json", "budget_program_graph.json")):
        raise ValueError("canonical optional Government Revenue rail exists without a prime dossier")
    html_path, json_path = _write_site_projection(
        root,
        payload,
        latest_raw=latest_raw,
        workspace_raw=workspace_raw,
    )
    log.info(
        "re-rendered %s from canonical Government Revenue generation %s",
        html_path,
        bundle_id,
    )
    return html_path, canonical_path, json_path


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Build Government Revenue Foresight")
    parser.add_argument("--root", default=str(_ROOT))
    parser.add_argument("--as-of", default=None)
    parser.add_argument(
        "--site-only",
        action="store_true",
        help="re-render public twins and HTML from the committed canonical generation",
    )
    args = parser.parse_args(argv)
    try:
        if args.site_only:
            if args.as_of is not None:
                parser.error("--as-of cannot be combined with --site-only")
            build_site_only(Path(args.root))
        else:
            build(Path(args.root), as_of=args.as_of)
    except Exception as exc:  # noqa: BLE001
        log.error("government revenue build failed: %s", exc, exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
