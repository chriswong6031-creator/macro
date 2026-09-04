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
from .qa_exchange import accepted_qa_exchanges_for_transcript
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
    _utc,
    validate_event_workspace,
)
from .events import CompanyEvent, FiscalPeriod
from .identity import IssuerRegistry
from .issuer_profiles import IssuerProfile, apple_profile


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
    transcript: Mapping[str, Any] | None,
    transcript_sha256: str | None = None,
    observed_at: object,
    source_available_at: object,
    collector_rows: Sequence[Mapping[str, Any]] | None = None,
    wire_record_found: bool = False,
    prior_source_sha256: str | None = None,
    prior_lifecycle_state: str | None = None,
    prior_observed_at: object | None = None,
    profile: IssuerProfile | None = None,
) -> dict[str, Any]:
    """Bind one issuer event from identity + 8-K exhibit + (if held) transcript.

    ``prior_source_sha256`` is the previously published exhibit hash.  A new
    hash on the same canonical event walks the lifecycle to ``corrected``.

    ``prior_lifecycle_state`` is the previously published workspace's OWN
    ``lifecycle.state`` (IMCE A5C BLOCKER-1 fix, Opus red-team 2026-08-23):
    when the source hash is UNCHANGED but the prior generation was already
    ``"corrected"``, the corrected transition is re-applied so the state
    STAYS ``"corrected"`` rather than silently walking back to
    ``"complete"``.  Without this, the very next unchanged-source rebuild
    after a correction re-derives the event from scratch (started ->
    complete) and never re-observes that a correction happened — so a
    downstream consumer sampling once per period (like IMCE A5B/A5C) sees a
    transient "corrected" that flips back to "complete" within one
    publication cycle, in which the exact mint the A5C safety law forbids
    could otherwise proceed. ``corrected -> corrected`` is a legal
    self-transition (``events.py``'s ``_TRANSITIONS``).

    ``profile`` supplies the issuer-specific extraction seam (additional
    ``event_fact.v1`` entries from the release body, and transcript claims);
    it defaults to :func:`issuer_profiles.apple_profile` so every pre-A5A
    caller keeps its exact behavior.  ``transcript`` is ``None`` for an issuer
    whose call is not held (e.g. a homebuilder absent from the Terminal tx
    index) — the workspace still publishes, with the transcript recorded as a
    typed absence rather than treated as a refusal.

    IMCE A5C two-clock law (frozen spec C): ``source_available_at`` is the
    SEC acceptance clock — unchanged, always the caller's *source_available_at*
    verbatim.  ``observed_at`` is the ACTUAL time the system FIRST observed
    THIS source revision — real wall-clock at build/fetch time, no longer
    silently rewritten to equal ``source_available_at``.  *observed_at* (the
    parameter) carries the caller's "now" for THIS build attempt;
    *prior_observed_at* is the previously-published workspace's own
    ``lifecycle.observed_at``.  When the newly bound exhibit's source hash is
    UNCHANGED from *prior_source_sha256* AND *prior_observed_at* is
    available, the published ``observed_at`` is the CARRIED-FORWARD prior
    value, never the fresh "now" (C3, first-observation persistence — a
    revision's observed_at is stamped once, at first observation, forever;
    a carried-forward workspace's clocks are never re-stamped). Otherwise
    (a genuinely new/changed revision, or no prior observed_at to carry) the
    fresh *observed_at* is used, matching the pre-A5C default. Either way,
    ``observed_at >= source_available_at`` remains mandatory (C4).
    """
    resolved = registry.resolve_ticker(ticker, asof=asof)
    if resolved is None:
        raise WorkspaceError(f"{ticker} maps to no issuer at {asof}")
    issuer = registry.get(resolved.company_id)
    requested_clock = _utc(observed_at, field_name="observed_at")
    available = _utc(source_available_at, field_name="source_available_at")

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

    if (
        prior_source_sha256
        and prior_observed_at is not None
        and prior_source_sha256 == bound.revision.source_sha256
    ):
        # C3: an unchanged source revision keeps its ORIGINAL observed_at —
        # wall-clock re-build time never advances it.
        clock = _utc(prior_observed_at, field_name="prior_observed_at")
    else:
        clock = requested_clock
    if clock < available:
        raise WorkspaceError("observed_at precedes source_available_at")

    aliases = aliases_for(issuer.company_id, fiscal_period, issuer.tickers_at(asof))
    event_id = aliases.canonical_event_id
    has_transcript = transcript is not None

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
        # F8: the reason names only the sources this event actually has —
        # claiming a transcript was observed on an event with none is a false
        # receipt in the lifecycle record itself.
        reason=(
            "issuer 8-K Item 2.02 and transcript observed" if has_transcript
            else "issuer 8-K Item 2.02 observed; no transcript held"
        ),
        document_ids=(bound.revision.document_id,),
    )
    event = event.apply_transition(
        "complete",
        observed_at=clock,
        source_available_at=available,
        effective_at=available,
        reason=(
            "primary exhibit and transcript revisions available" if has_transcript
            else "primary exhibit revision available; no transcript held"
        ),
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
    elif prior_lifecycle_state == "corrected":
        # A5C BLOCKER-1 fix (Opus red-team, 2026-08-23): sha UNCHANGED, but
        # the prior generation was already corrected — re-apply the SAME
        # corrected transition (binding the same document revision already
        # bound above) so the published state stays "corrected" instead of
        # silently re-deriving "complete" from scratch. See the docstring
        # above for why this matters.
        event = event.apply_transition(
            "corrected",
            observed_at=clock,
            source_available_at=available,
            effective_at=available,
            reason="correction carried forward; source-revision history not yet published",
            document_ids=(bound.revision.document_id,),
        )

    release_doc_id = bound.revision.document_id
    tx_doc_id = f"tx:{aliases.earnings_narrative_keys[0]}"
    segments = list((transcript or {}).get("segments") or [])
    active_profile = profile or apple_profile()

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

    facts.extend(
        active_profile.extract_release_facts(
            bound=bound, document_id=release_doc_id, event_id=event_id, fiscal_period=fiscal_period,
        )
    )

    claims.extend(
        active_profile.extract_transcript_claims(
            segments=segments, document_id=tx_doc_id, body_sha256=transcript_sha256 or "", event_id=event_id,
        )
    )

    qa_exchanges = accepted_qa_exchanges_for_transcript(
        event_id=event_id,
        document_id=tx_doc_id,
        document_sha256=transcript_sha256 or "",
        segments=segments,
        source_available_at=None,
        clock_state="unknown",
    ) if has_transcript else []

    if has_transcript and not qa_exchanges:
        facts.append({
            "schema": "event_fact.v1",
            "fact_id": "fact_questions_count",
            "event_id": event_id,
            "metric": "questions_count",
            "typed_absence": _absence(
                reason="no_span_addressable_evidence",
                subject="questions_count",
                detail="analyst questions are not span-addressable on the held transcript",
                event_id=event_id,
                document_id=tx_doc_id,
            ),
        })
    elif not has_transcript:
        facts.append({
            "schema": "event_fact.v1",
            "fact_id": "fact_questions_count",
            "event_id": event_id,
            "metric": "questions_count",
            "typed_absence": _absence(
                reason="no_transcript",
                subject="questions_count",
                detail="no transcript is held for this event",
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

    # F6: guidance extraction moves behind the IssuerProfile seam — the
    # segment index, literal, and 9.0/11.0 bounds below were Apple-only
    # constructions sitting in generic code.  apple_profile() reproduces this
    # exact block unchanged; a homebuilder profile returns [].
    guidance: list[dict[str, Any]] = list(
        active_profile.extract_guidance(
            segments=segments, document_id=tx_doc_id, body_sha256=transcript_sha256 or "", event_id=event_id,
        )
    )

    # F7: "unstructured Q&A" only makes sense as a warning about a transcript
    # this event actually holds — an event with no transcript at all already
    # says so via fact_questions_count's own typed absence.
    warnings = sorted({
        "slides_absent",
        "consensus_unlicensed",
        "reaction_not_joined",
        *(["questions_count_unstructured"] if has_transcript and not qa_exchanges else []),
        *(["wire_record_not_found"] if not wire_record_found else []),
        *([join_warning] if join_warning else []),
    } & WORKSPACE_WARNINGS)

    public_wire_slug = aliases.public_slugs[0] if aliases.public_slugs else LIVE_PUBLIC_SLUG
    sources = [
        {
            "kind": "issuer_release",
            "document_id": release_doc_id,
            "filing_key": {"cik": cik.zfill(10) if cik.isdigit() else cik, "accession": accession},
            "source_sha256": bound.revision.source_sha256,
            # A5C BLOCKER-1 (1b) — the bound filing's own SEC-assigned FORM
            # ("8-K" vs "8-K/A") was previously bound but dropped before
            # publication; IMCE A5C's fail-closed observation gate needs it
            # as a second durable safety signal (source rows are NOT
            # exact-keyed by validate_event_workspace, and cross-repo
            # preflight confirmed Terminal's normalizeSource() is a
            # permissive picker that ignores unrecognized keys rather than
            # rejecting them — this addition is safe on both sides).
            #
            # NEW-2 fix (Opus red-team round 2, 2026-08-23): deliberately
            # published from the RAW *filing* mapping, NOT from
            # bound.revision.form — bind_release_document (line ~167 above)
            # defaults an empty/missing form to "8-K" for its OWN internal
            # identity/is_amendment purposes (a default this function does
            # not touch — nothing else here reads bound.revision.form or
            # .is_amendment, so decoupling the PUBLISHED value carries no
            # ripple risk). The safety gate downstream must see the form
            # EDGAR actually gave, or see it genuinely absent — never an
            # invented "8-K" standing in for "we don't know". On the real
            # nightly path this is defense-in-depth, not a behavior change:
            # discovery (refresh_event_workspaces._select_newest_results_rows)
            # already pre-filters every candidate to {"8-K", "8-K/A"}, so a
            # genuinely absent form should be unreachable there.
            "form": (str(filing.get("form")) if filing.get("form") else None),
            "url": filing.get("exhibit_url"),
            "receipt_state": "byte_replayed",
        },
        {
            "kind": "transcript",
            "document_id": tx_doc_id,
            "source_sha256": transcript_sha256,
            "receipt_state": "byte_replayed",
        } if has_transcript else {
            "kind": "transcript",
            "document_id": tx_doc_id,
            "receipt_state": "typed_absence",
            "typed_absence": _absence(
                reason="no_transcript",
                subject="transcript",
                detail="no transcript is held for this event",
                event_id=event_id,
                document_id=tx_doc_id,
            ),
        },
        {
            "kind": "public_wire",
            "slug": public_wire_slug,
            "receipt_state": "typed_absence" if not wire_record_found else "address_only",
            "typed_absence": None if wire_record_found else _absence(
                reason="no_source_document",
                subject="public_wire",
                # F6: the receipted 404 date/slug is a genuine historical
                # fact about ONLY the flagship's own slug — reusing it for
                # every other event would be a false receipt (a DHI
                # workspace citing "aapl-2026q3-call-record was 404").  Any
                # other event's own slug has simply never been checked yet.
                detail=(
                    f"{LIVE_PUBLIC_SLUG} was 404 on 2026-08-16" if public_wire_slug == LIVE_PUBLIC_SLUG
                    else f"{public_wire_slug} has not been checked against the public wire"
                ),
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
        "transcript": (
            {"status": "present", "document_id": tx_doc_id}
            if has_transcript
            else {
                "status": "absent",
                "typed_absence": _absence(
                    reason="no_transcript",
                    subject="transcript",
                    detail="no transcript is held for this event",
                    event_id=event_id,
                    document_id=tx_doc_id,
                ),
            }
        ),
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
        "qa_exchanges": qa_exchanges,
    }
    validate_event_workspace({**payload, "generation_id": "0" * 24})
    payload["generation_id"] = ""
    payload["_source_sha256"] = bound.revision.source_sha256
    payload["_aliases"] = aliases.to_payload()
    return payload
