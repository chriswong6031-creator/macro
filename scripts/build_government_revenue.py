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
from lib.pages import write_page  # noqa: E402

log = logging.getLogger("build_government_revenue")

# The HTML shell is intentionally a first page, not a duplicate of the full
# workspace.  Fifteen governed events keeps the rendered page below the raw
# 250 kB edge budget while still giving the desk a useful first paint.
SHELL_EVENT_LIMIT = 15
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


def _present_fields(record: object, fields: tuple[str, ...]) -> dict:
    """Pick only explicitly present, non-null fields from a JSON-like record."""
    if not isinstance(record, dict):
        return {}
    return {
        field: record[field]
        for field in fields
        if field in record and record[field] is not None
    }


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
        change["changed_fields"] = changed_fields[:8]
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
        if key not in {"companies", "opportunity_intelligence", "procurement_workspace"}
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
            "provenance": (company.get("provenance") or [])[:1],
            "authority": company.get("authority") or {},
        }
        for company in payload.get("companies") or []
        if isinstance(company, dict)
    ]

    opportunity_intelligence = payload.get("opportunity_intelligence")
    if isinstance(opportunity_intelligence, dict):
        shell["opportunity_intelligence"] = {
            **opportunity_intelligence,
            "opportunities": [],
            "events": [],
            "company_context": {},
        }

    workspace = payload.get("procurement_workspace")
    if isinstance(workspace, dict):
        events = [event for event in workspace.get("events") or [] if isinstance(event, dict)]
        visible = [_compact_workspace_event(event) for event in events[:SHELL_EVENT_LIMIT]]
        shell["procurement_workspace"] = {
            **workspace,
            "events": visible,
            "next_cursor": str(len(visible)) if len(events) > len(visible) else None,
        }
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
    return f"grw1-{digest[:24]}"


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
    if not isinstance(workspace, dict) or workspace.get("schema_version") != "government_procurement_workspace.v1":
        raise ValueError("government procurement workspace returned an invalid schema")
    return payload


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

    canonical_dir = root / "data" / "government_revenue"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = canonical_dir / "latest.json"
    workspace = payload.get("procurement_workspace")
    workspace["bundle_id"] = _workspace_bundle_id(workspace)
    workspace_raw = _canonical_json(workspace)
    latest_raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    _atomic_write_text(canonical_dir / "workspace.json", workspace_raw)
    _atomic_write_text(canonical_path, latest_raw)
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
    if not isinstance(workspace, dict) or workspace.get("schema_version") != "government_procurement_workspace.v1":
        raise ValueError("canonical government procurement workspace is invalid")
    embedded = payload.get("procurement_workspace")
    if _canonical_json(embedded) != _canonical_json(workspace):
        raise ValueError("canonical latest/workspace generation mismatch")
    bundle_id = workspace.get("bundle_id")
    if not bundle_id or bundle_id != _workspace_bundle_id(workspace):
        raise ValueError("canonical workspace bundle identity mismatch")
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
