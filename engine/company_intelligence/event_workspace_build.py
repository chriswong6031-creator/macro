"""Bind issuer 8-K + transcript bytes into ``event_workspace.v1``.

This module is the only E1 file that imports ``engine.earnings_release``.
The published schema, writer, and production reader stay in
``event_workspace.py`` so exclusive CI jobs that statically reach the
reader do not inherit Exhibit 99.1 parsing as a false dependency.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from ..earnings_release.binding import BoundRelease, bind_release_document
from ..earnings_release.filing_key import (
    FilingIdentityError,
    FilingKey as ReleaseFilingKey,
    filing_key_from_8k_row,
)
from ..earnings_release.receipts import replay_receipt
from .documents import text_span
from .event_id_adapter import aliases_for
from .event_workspace import (
    AUTHORITY,
    LIVE_PUBLIC_SLUG,
    PROPHET_FLAGS,
    WORKSPACE_SCHEMA,
    WORKSPACE_WARNINGS,
    WorkspaceError,
    _absence,
    _iso,
    _lifecycle_payload,
    _span_payload_from_transcript,
    _utc,
    validate_event_workspace,
)
from .events import CompanyEvent, FiscalPeriod
from .identity import IssuerRegistry


_GLANCE_SPANS: tuple[tuple[str, int, str, str, str], ...] = (
    ("claim_revenue_lede", 2, "$109.4 billion in revenue, up 16%", "numeric", "revenue"),
    ("claim_iphone_yoy", 5, "up 22% from a year ago", "numeric", "iphone_revenue_yoy_pct"),
    ("claim_mac_yoy", 6, "growing an impressive 29%", "numeric", "mac_revenue_yoy_pct"),
    ("claim_services_revenue", 11, "$30.7 billion", "numeric", "services_revenue"),
    ("claim_install_base", 17, "over two and a half billion", "numeric", "active_devices"),
    ("claim_demand_vs_supply", 55, "remarkably better than we thought", "quote", "demand_vs_supply"),
    ("claim_memory_flood", 65, "100-year flood", "quote", "memory"),
    (
        "claim_fx_headwind",
        26,
        "two and a half percentage points to the year-over-year total company growth rate",
        "numeric",
        "fx_yoy_headwind",
    ),
)


def _span_payload_from_release_figure(
    *,
    document_id: str,
    bound: BoundRelease,
    figure: Any,
) -> dict[str, Any]:
    replay_receipt(figure.receipt, source=bound.source)
    span = text_span(
        document_id=document_id,
        document_version=1,
        body_sha256=bound.revision.source_sha256,
        segment_index=0,
        segment_text=bound.source,
        start_byte=figure.receipt.byte_start,
        end_byte=figure.receipt.byte_end,
        text=figure.receipt.span_text,
        rights_profile="rp_public_primary_v1",
    )
    return span.to_payload()


def _collector_join_status(
    collector_rows: Sequence[Mapping[str, Any]] | None,
    *,
    cik: str,
    accession: str,
    event_id: str,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Join the bound filing on ``(cik, accession)``.  Never on filing_date."""
    if not collector_rows:
        return (
            "unjoinable",
            _absence(
                reason="unjoinable_filing_identity",
                subject="edgar_earnings_8k",
                detail="no collector rows were supplied to join the bound filing",
                event_id=event_id,
            ),
            "collector_filing_unjoinable",
        )
    target = ReleaseFilingKey(cik=cik, accession=accession)
    unjoinable = 0
    for row in collector_rows:
        try:
            key = filing_key_from_8k_row(row)
        except FilingIdentityError:
            unjoinable += 1
            continue
        if key.key == target.key:
            return "joined", None, None
    reason = (
        "legacy collector rows carry no accession and cannot be joined"
        if unjoinable
        else "bound accession is not present in the collector store"
    )
    return (
        "unjoinable",
        _absence(
            reason="unjoinable_filing_identity",
            subject="edgar_earnings_8k",
            detail=reason,
            event_id=event_id,
        ),
        "collector_filing_unjoinable",
    )


def build_event_workspace(
    *,
    registry: IssuerRegistry,
    ticker: str,
    asof: date,
    fiscal_period: FiscalPeriod,
    exhibit_body: str,
    filing: Mapping[str, Any],
    transcript: Mapping[str, Any],
    transcript_sha256: str,
    observed_at: object,
    source_available_at: object,
    collector_rows: Sequence[Mapping[str, Any]] | None = None,
    wire_record_found: bool = False,
    prior_source_sha256: str | None = None,
) -> dict[str, Any]:
    """Bind one issuer event from identity + 8-K exhibit + transcript.

    ``prior_source_sha256`` is the previously published exhibit hash.  A new
    hash on the same canonical event walks the lifecycle to ``corrected``.
    """
    resolved = registry.resolve_ticker(ticker, asof=asof)
    if resolved is None:
        raise WorkspaceError(f"{ticker} maps to no issuer at {asof}")
    issuer = registry.get(resolved.company_id)
    clock = _utc(observed_at, field_name="observed_at")
    available = _utc(source_available_at, field_name="source_available_at")
    if clock < available:
        raise WorkspaceError("observed_at precedes source_available_at")

    accession = str(filing.get("accession") or "")
    cik = str(filing.get("cik") or issuer.cik)
    bound = bind_release_document(
        cik=cik,
        accession=accession,
        body=exhibit_body,
        form=str(filing.get("form") or "8-K"),
        filing_date=filing.get("filing_date") or "",
        acceptance_datetime=filing.get("acceptance_datetime") or "",
        report_date=filing.get("report_date") or "",
        exhibit_url=str(filing.get("exhibit_url") or "") or None,
    )
    aliases = aliases_for(issuer.company_id, fiscal_period, issuer.tickers_at(asof))
    event_id = aliases.canonical_event_id

    security_ids = issuer.security_ids_at(asof)
    event = CompanyEvent.create(
        company_id=issuer.company_id,
        fiscal_period=fiscal_period,
        security_ids=security_ids,
        scheduled_at=available,
    )
    event = event.apply_transition(
        "started",
        observed_at=clock,
        source_available_at=available,
        effective_at=available,
        reason="issuer 8-K Item 2.02 and transcript observed",
        document_ids=(bound.revision.document_id,),
    )
    event = event.apply_transition(
        "complete",
        observed_at=clock,
        source_available_at=available,
        effective_at=available,
        reason="primary exhibit and transcript revisions available",
    )
    if prior_source_sha256 and prior_source_sha256 != bound.revision.source_sha256:
        event = event.apply_transition(
            "corrected",
            observed_at=clock,
            source_available_at=available,
            effective_at=available,
            reason="source_sha256 changed; document revision restates the original",
            document_ids=(bound.revision.document_id,),
        )

    release_doc_id = bound.revision.document_id
    tx_doc_id = f"tx:{aliases.earnings_narrative_keys[0]}"
    segments = list(transcript.get("segments") or [])

    facts: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    revenue_figure = bound.figures.figure("revenue", basis="gaap")
    if revenue_figure is not None:
        facts.append({
            "schema": "event_fact.v1",
            "fact_id": "fact_revenue_gaap",
            "event_id": event_id,
            "metric": "revenue",
            "value": revenue_figure.value,
            "unit": revenue_figure.units,
            "period": revenue_figure.period_end,
            "basis": revenue_figure.basis,
            "source_span": _span_payload_from_release_figure(
                document_id=release_doc_id, bound=bound, figure=revenue_figure
            ),
        })
    else:
        facts.append({
            "schema": "event_fact.v1",
            "fact_id": "fact_revenue_gaap",
            "event_id": event_id,
            "metric": "revenue",
            "typed_absence": _absence(
                reason="no_span_addressable_evidence",
                subject="revenue",
                detail="Exhibit 99.1 did not yield a GAAP revenue figure",
                event_id=event_id,
                document_id=release_doc_id,
            ),
        })

    for fact_id, index, literal, kind, metric in _GLANCE_SPANS:
        if index >= len(segments):
            payload = None
            segment: Mapping[str, Any] = {}
        else:
            segment = segments[index]
            payload = _span_payload_from_transcript(
                document_id=tx_doc_id,
                body_sha256=transcript_sha256,
                segment_index=index,
                segment=segment,
                literal=literal,
            )
        if payload is None:
            claims.append({
                "schema": "event_claim.v1",
                "claim_id": fact_id,
                "text": literal,
                "kind": kind,
                "metric": metric,
                "typed_absence": _absence(
                    reason="no_span_addressable_evidence",
                    subject=metric,
                    detail=f"literal {literal!r} is not uniquely addressable in the transcript",
                    event_id=event_id,
                    document_id=tx_doc_id,
                ),
            })
            continue
        claims.append({
            "schema": "event_claim.v1",
            "claim_id": fact_id,
            "text": literal,
            "kind": kind,
            "metric": metric,
            "speaker": segment.get("speaker"),
            "role": segment.get("role") or None,
            "evidence_spans": [payload],
            "source_span": payload,
        })

    facts.append({
        "schema": "event_fact.v1",
        "fact_id": "fact_questions_count",
        "event_id": event_id,
        "metric": "questions_count",
        "typed_absence": _absence(
            reason="no_span_addressable_evidence",
            subject="questions_count",
            detail=(
                "analyst role is empty on the held transcript; 14 is overlay "
                "history, not a structured Q&A count"
            ),
            event_id=event_id,
            document_id=tx_doc_id,
        ),
    })

    join_status, join_absence, join_warning = _collector_join_status(
        collector_rows, cik=cik, accession=accession, event_id=event_id
    )

    consensus_absence = _absence(
        reason="missing_source",
        subject="consensus",
        detail="consensus is unlicensed for this estate; no beat/miss is emitted",
        event_id=event_id,
    )
    current = None
    if revenue_figure is not None:
        current = {
            "value": revenue_figure.value,
            "unit": revenue_figure.units,
            "basis": revenue_figure.basis,
        }
    deltas = [{
        "schema": "metric_delta.v1",
        "metric": "revenue",
        "current": current,
        "prior": _absence(
            reason="no_span_addressable_evidence",
            subject="revenue_prior",
            detail="prior-period revenue is not bound as a same-table companion in this wave",
            event_id=event_id,
            document_id=release_doc_id,
        ),
        "consensus": consensus_absence,
        "basis_match": False,
    }]

    guidance: list[dict[str, Any]] = []
    if len(segments) > 26:
        guide_literal = "grow between 9%-11% year-over-year"
        guide_span = _span_payload_from_transcript(
            document_id=tx_doc_id,
            body_sha256=transcript_sha256,
            segment_index=26,
            segment=segments[26],
            literal=guide_literal,
        )
        if guide_span is not None:
            guidance.append({
                "schema": "guidance_item.v1",
                "metric": "revenue_yoy_pct",
                "low": 9.0,
                "high": 11.0,
                "unit": "percent",
                "horizon": "FY2026 Q4",
                "status": "introduced",
                "source_span": guide_span,
            })

    warnings = sorted({
        "slides_absent",
        "consensus_unlicensed",
        "reaction_not_joined",
        "questions_count_unstructured",
        *(["wire_record_not_found"] if not wire_record_found else []),
        *([join_warning] if join_warning else []),
    } & WORKSPACE_WARNINGS)

    sources = [
        {
            "kind": "issuer_release",
            "document_id": release_doc_id,
            "filing_key": {"cik": cik.zfill(10) if cik.isdigit() else cik, "accession": accession},
            "source_sha256": bound.revision.source_sha256,
            "url": filing.get("exhibit_url"),
            "receipt_state": "byte_replayed",
        },
        {
            "kind": "transcript",
            "document_id": tx_doc_id,
            "source_sha256": transcript_sha256,
            "receipt_state": "byte_replayed",
        },
        {
            "kind": "public_wire",
            "slug": aliases.public_slugs[0] if aliases.public_slugs else LIVE_PUBLIC_SLUG,
            "receipt_state": "typed_absence" if not wire_record_found else "address_only",
            "typed_absence": None if wire_record_found else _absence(
                reason="no_source_document",
                subject="public_wire",
                detail=f"{LIVE_PUBLIC_SLUG} was 404 on 2026-08-16",
                event_id=event_id,
            ),
        },
    ]
    if join_absence is not None:
        sources.append({
            "kind": "edgar_collector",
            "receipt_state": "typed_absence",
            "join_status": join_status,
            "typed_absence": join_absence,
        })

    pending_claims = []
    for claim in claims:
        pending_claims.append(bool(claim.get("source_span")) and not claim.get("typed_absence"))
    claim_pending = True if not claims else any(not has for has in pending_claims)

    completeness = {
        "release": {"status": "present", "document_id": release_doc_id},
        "filing": {
            "status": "bound",
            "filing_key": {
                "cik": f"{bound.revision.filing_key.cik:010d}",
                "accession": bound.revision.filing_key.accession,
            },
        },
        "transcript": {"status": "present", "document_id": tx_doc_id},
        "slides": {
            "status": "absent",
            "typed_absence": _absence(
                reason="no_source_document",
                subject="slides",
                detail="no presentation body is held for this event",
                event_id=event_id,
            ),
        },
        "consensus": {"status": "unlicensed", "typed_absence": consensus_absence},
        "reaction": {"status": "not_joined"},
    }

    listing_payload = [
        listing.to_payload()
        for listing in issuer.listings_at(asof)
    ]
    payload = {
        "schema": WORKSPACE_SCHEMA,
        "event_id": event_id,
        "aliases": [
            *aliases.company_intelligence_ids,
            *aliases.earnings_narrative_keys,
            *aliases.public_slugs,
        ],
        "issuer": {
            "company_id": issuer.company_id,
            "display_name": issuer.display_name,
            "listings": listing_payload,
        },
        "fiscal_period": fiscal_period.to_payload(),
        "lifecycle": _lifecycle_payload(event),
        "completeness": completeness,
        "facts": facts,
        "deltas": deltas,
        "guidance": guidance,
        "claims": claims,
        "sources": sources,
        "warnings": warnings,
        "generation_id": "",
        "generated_at": _iso(clock),
        "authority": AUTHORITY,
        "prophet_flags": dict(PROPHET_FLAGS),
        "claim_citations_pending": claim_pending,
        "qa_exchanges": [],
    }
    validate_event_workspace({**payload, "generation_id": "0" * 24})
    payload["generation_id"] = ""
    payload["_source_sha256"] = bound.revision.source_sha256
    payload["_aliases"] = aliases.to_payload()
    return payload
