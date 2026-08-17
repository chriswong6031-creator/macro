"""``event_workspace.v1`` — compact earnings payload + sibling publication.

E1 publishes this object under ``company_intelligence/event_workspaces/`` with
the same marker-last immutable-generation discipline as ``write_generation``.
It does not mutate the closed v1 teaser maps.

Authority is ``context_only``.  Nothing here ranks, sizes, gates, or feeds
Prophet.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

from .contracts import (
    ContractError,
    canonical_json_bytes,
    iso_timestamp,
)
from .documents import (
    TypedAbsence,
    text_span,
)
from .event_id_adapter import EventAliasIndex, aliases_for
from .events import AUTHORITY, CompanyEvent, FiscalPeriod
from .identity import IssuerIdentity, IssuerRegistry, ListingAlias, company_id_for_cik
from ..earnings_release.binding import BoundRelease, bind_release_document
from ..earnings_release.filing_key import (
    FilingIdentityError,
    FilingKey as ReleaseFilingKey,
    filing_key_from_8k_row,
)
from ..earnings_release.receipts import replay_receipt


WORKSPACE_SCHEMA = "event_workspace.v1"
MANIFEST_SCHEMA = "event_workspace_manifest.v1"
PROCESSOR_VERSION = "event_workspace/1.0.0"
NEST = "event_workspaces"
AUTHORITY = AUTHORITY

PROPHET_FLAGS = {
    "may_rank": False,
    "may_size": False,
    "may_gate": False,
    "prophet_authority": False,
}

WORKSPACE_KEYS = (
    "schema",
    "event_id",
    "aliases",
    "issuer",
    "fiscal_period",
    "lifecycle",
    "completeness",
    "facts",
    "deltas",
    "guidance",
    "claims",
    "sources",
    "warnings",
    "generation_id",
    "generated_at",
    "authority",
    "prophet_flags",
    "claim_citations_pending",
    "qa_exchanges",
)

MANIFEST_KEYS = (
    "schema",
    "generation_id",
    "generated_at",
    "status",
    "event_count",
    "files",
    "aliases",
    "authority",
    "warnings",
)

WORKSPACE_WARNINGS = frozenset({
    "wire_record_not_found",
    "collector_filing_unjoinable",
    "consensus_unlicensed",
    "slides_absent",
    "reaction_not_joined",
    "questions_count_unstructured",
})

_GENERATION_RE = re.compile(r"^[0-9a-f]{24,64}$")
_EVENT_ID_RE = re.compile(r"^evt_cik\d{10}_\d{4}(?:q[1-4]|fy)_[a-z0-9]+$")

# Flagship AAPL FY2026 Q3 — real issuer/SEC identity.  Not a synthetic CIK.
AAPL_CIK = "0000320193"
AAPL_ACCESSION = "0000320193-26-000018"
AAPL_CALL_DATE = date(2026, 7, 30)
AAPL_PERIOD_END = date(2026, 6, 27)
FLAGSHIP_EVENT_ID = "evt_cik0000320193_2026q3_results"
LIVE_CIE_ALIAS = "cie_98e318c37ec1a2a1f83c45e1"
LIVE_NARRATIVE_ALIAS = "AAPL/2026Q3"
LIVE_PUBLIC_SLUG = "aapl-2026q3-call-record"

_GLANCE_SPANS: tuple[tuple[str, int, str, str, str], ...] = (
    # fact_id, segment_index, unique literal, kind, metric
    ("claim_revenue_lede", 2, "$109.4 billion in revenue, up 16%", "numeric", "revenue"),
    ("claim_iphone_yoy", 5, "up 22% from a year ago", "numeric", "iphone_revenue_yoy_pct"),
    ("claim_mac_yoy", 6, "growing an impressive 29%", "numeric", "mac_revenue_yoy_pct"),
    ("claim_services_revenue", 11, "$30.7 billion", "numeric", "services_revenue"),
    ("claim_install_base", 17, "over two and a half billion", "numeric", "active_devices"),
    ("claim_demand_vs_supply", 55, "remarkably better than we thought", "quote", "demand_vs_supply"),
    ("claim_memory_flood", 65, "100-year flood", "quote", "memory"),
    ("claim_fx_headwind", 26, "two and a half percentage points to the year-over-year total company growth rate", "numeric", "fx_yoy_headwind"),
)


class WorkspaceError(ContractError):
    """The workspace payload or its publication contract cannot be trusted."""


def _utc(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    else:
        text = str(value or "").strip()
        if not text:
            raise WorkspaceError(f"{field_name} is required")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_mapping(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkspaceError(f"{name} must be an object")
    return dict(value)


def _require_exact_keys(item: Mapping[str, Any], keys: Sequence[str], *, name: str) -> None:
    if set(item) != set(keys):
        raise WorkspaceError(f"{name} keys mismatch")


def apple_issuer() -> IssuerIdentity:
    """Real EDGAR identity for Apple Inc. as of the FY2026 Q3 print."""
    return IssuerIdentity(
        company_id=company_id_for_cik(AAPL_CIK),
        display_name="Apple Inc.",
        fiscal_year_end_month=9,
        reporting_currency="USD",
        listings=(
            ListingAlias(
                ticker="AAPL",
                mic="XNAS",
                share_class="common",
                trading_currency="USD",
                is_primary=True,
            ),
        ),
        external_ids={"cik": AAPL_CIK},
    )


def apple_registry() -> IssuerRegistry:
    return IssuerRegistry([apple_issuer()])


def flagship_fiscal_period() -> FiscalPeriod:
    return FiscalPeriod(year=2026, quarter=3, calendar_end=AAPL_PERIOD_END)


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(body)
    try:
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _unique_utf8_span(text: str, literal: str) -> tuple[int, int] | None:
    raw = text.encode("utf-8")
    needle = literal.encode("utf-8")
    start = raw.find(needle)
    if start < 0:
        return None
    if raw.find(needle, start + 1) >= 0:
        return None
    return start, start + len(needle)


def _transcript_sha256(raw_bytes: bytes) -> str:
    return sha256(raw_bytes).hexdigest()


def _absence(
    *,
    reason: str,
    subject: str,
    detail: str,
    event_id: str,
    document_id: str | None = None,
) -> dict[str, Any]:
    return TypedAbsence(
        reason=reason,
        subject=subject,
        detail=detail,
        event_id=event_id,
        document_id=document_id,
    ).to_payload()


def _span_payload_from_transcript(
    *,
    document_id: str,
    body_sha256: str,
    segment_index: int,
    segment: Mapping[str, Any],
    literal: str,
) -> dict[str, Any] | None:
    text = str(segment.get("text") or "")
    bounds = _unique_utf8_span(text, literal)
    if bounds is None:
        return None
    start, end = bounds
    span = text_span(
        document_id=document_id,
        document_version=1,
        body_sha256=body_sha256,
        segment_index=segment_index,
        segment_text=text,
        start_byte=start,
        end_byte=end,
        text=literal,
        speaker=segment.get("speaker"),
        role=segment.get("role") or None,
        rights_profile="rp_public_primary_v1",
    )
    return span.to_payload()


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


def _lifecycle_payload(event: CompanyEvent) -> dict[str, Any]:
    return {
        "state": event.state,
        "observed_at": _iso(event.observed_at) if event.observed_at else None,
        "source_available_at": (
            _iso(event.source_available_at) if event.source_available_at else None
        ),
    }


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
    # Keep the empty generation_id for the writer to stamp.  Re-validate after stamp.
    payload["generation_id"] = ""
    payload["_source_sha256"] = bound.revision.source_sha256
    payload["_aliases"] = aliases.to_payload()
    return payload


def validate_event_workspace(payload: object) -> None:
    item = _require_mapping(payload, name="event_workspace")
    _require_exact_keys(item, WORKSPACE_KEYS, name="event_workspace")
    if item.get("schema") != WORKSPACE_SCHEMA:
        raise WorkspaceError("event_workspace schema mismatch")
    if not _EVENT_ID_RE.fullmatch(str(item.get("event_id") or "")):
        raise WorkspaceError("event_workspace event_id is not canonical")
    if item.get("authority") != AUTHORITY:
        raise WorkspaceError("event_workspace authority must be context_only")
    flags = _require_mapping(item.get("prophet_flags"), name="prophet_flags")
    if flags != PROPHET_FLAGS:
        raise WorkspaceError("event_workspace prophet flags must all be false")
    if not isinstance(item.get("claim_citations_pending"), bool):
        raise WorkspaceError("claim_citations_pending must be derived bool")
    if iso_timestamp(item.get("generated_at")) is None:
        raise WorkspaceError("generated_at missing")
    if not _GENERATION_RE.fullmatch(str(item.get("generation_id") or "")):
        raise WorkspaceError("invalid generation_id")
    warnings = item.get("warnings")
    if (
        not isinstance(warnings, list)
        or warnings != sorted(set(warnings))
        or any(value not in WORKSPACE_WARNINGS for value in warnings)
    ):
        raise WorkspaceError("event_workspace warnings invalid")
    for name in ("facts", "deltas", "guidance", "claims", "sources", "aliases", "qa_exchanges"):
        if not isinstance(item.get(name), list):
            raise WorkspaceError(f"{name} must be a list")
    for delta in item["deltas"]:
        if not isinstance(delta, Mapping):
            raise WorkspaceError("delta must be an object")
        if delta.get("basis_match") is True:
            raise WorkspaceError("basis_match true is not minted in E1 without a licensed consensus")
        if "beat" in delta or "miss" in delta or "beat_miss" in delta:
            raise WorkspaceError("beat/miss is forbidden unless basis_match is true")


def validate_workspace_manifest(payload: object) -> None:
    item = _require_mapping(payload, name="event_workspace_manifest")
    _require_exact_keys(item, MANIFEST_KEYS, name="event_workspace_manifest")
    if item.get("schema") != MANIFEST_SCHEMA:
        raise WorkspaceError("workspace manifest schema mismatch")
    if not _GENERATION_RE.fullmatch(str(item.get("generation_id") or "")):
        raise WorkspaceError("invalid manifest generation_id")
    if iso_timestamp(item.get("generated_at")) is None:
        raise WorkspaceError("manifest generated_at missing")
    if item.get("authority") != AUTHORITY:
        raise WorkspaceError("workspace manifest authority must be context_only")
    if item.get("status") not in {"ready", "degraded", "partial", "empty"}:
        raise WorkspaceError("invalid workspace manifest status")
    event_count = item.get("event_count")
    if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count < 0:
        raise WorkspaceError("manifest event_count must be a nonnegative integer")
    files = _require_mapping(item.get("files"), name="manifest.files")
    if len(files) != event_count:
        raise WorkspaceError("manifest event_count must match files")
    for name, block in files.items():
        if (
            not isinstance(name, str)
            or not name.startswith("workspaces/")
            or not name.endswith(".json")
            or ".." in name.split("/")
        ):
            raise WorkspaceError("manifest file path is unsafe")
        event_id = name[len("workspaces/"):-len(".json")]
        if not _EVENT_ID_RE.fullmatch(event_id):
            raise WorkspaceError("manifest file is not a canonical event workspace")
        block_map = _require_mapping(block, name=f"manifest file {name}")
        if set(block_map) != {"bytes", "sha256"}:
            raise WorkspaceError("manifest file receipt keys mismatch")
        digest = str(block_map.get("sha256") or "")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise WorkspaceError("manifest file sha256 invalid")
        size = block_map.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise WorkspaceError("manifest file bytes invalid")
    aliases = _require_mapping(item.get("aliases"), name="manifest.aliases")
    for legacy, canonical in aliases.items():
        if not isinstance(legacy, str) or not isinstance(canonical, str):
            raise WorkspaceError("manifest aliases must be strings")
        if not _EVENT_ID_RE.fullmatch(canonical):
            raise WorkspaceError("manifest alias does not resolve to a canonical event")
    warnings = item.get("warnings")
    if not isinstance(warnings, list) or warnings != sorted(set(warnings)):
        raise WorkspaceError("manifest warnings invalid")


def _strip_private(workspace: Mapping[str, Any]) -> dict[str, Any]:
    return {key: workspace[key] for key in WORKSPACE_KEYS}


def _generation_identity(
    workspaces: Mapping[str, Mapping[str, Any]],
    generated_at: str,
) -> str:
    pre_id = {
        event_id: {key: payload[key] for key in WORKSPACE_KEYS if key != "generation_id"}
        for event_id, payload in sorted(workspaces.items())
    }
    return sha256(canonical_json_bytes({
        "generated_at": generated_at,
        "workspaces": pre_id,
    })).hexdigest()[:24]


def write_workspace_generation(
    out_dir: Path,
    workspaces: Mapping[str, Mapping[str, Any]],
    *,
    generated_at: str | None = None,
    status: str = "ready",
) -> Path:
    """Write immutable workspace objects, then atomically advance the nest marker.

    ``out_dir`` is the Company Intelligence product prefix
    (``company_intelligence/``).  Objects land under ``event_workspaces/``.
    """
    if not workspaces:
        raise WorkspaceError("write_workspace_generation requires at least one workspace")
    stamped: dict[str, dict[str, Any]] = {}
    generated = generated_at or next(iter(workspaces.values())).get("generated_at")
    if not generated:
        generated = _iso(datetime.now(timezone.utc))
    cleaned = {
        event_id: _strip_private(payload)
        for event_id, payload in workspaces.items()
    }
    generation_id = _generation_identity(cleaned, str(generated))
    alias_map: dict[str, str] = {}
    for event_id, payload in cleaned.items():
        if event_id != payload.get("event_id"):
            raise WorkspaceError("workspace map key must equal event_id")
        row = dict(payload)
        row["generation_id"] = generation_id
        row["generated_at"] = str(generated)
        validate_event_workspace(row)
        stamped[event_id] = row
        alias_map[event_id] = event_id
        for alias in row.get("aliases") or []:
            alias_map[str(alias)] = event_id
        private = workspaces[event_id]
        extra = private.get("_aliases") if isinstance(private, Mapping) else None
        if isinstance(extra, Mapping):
            for group in (
                extra.get("company_intelligence_ids") or [],
                extra.get("earnings_narrative_keys") or [],
                extra.get("public_slugs") or [],
            ):
                for alias in group:
                    alias_map[str(alias)] = event_id

    nest = Path(out_dir) / NEST
    generation_dir = nest / "generations" / generation_id
    file_blocks: dict[str, dict[str, Any]] = {}
    for event_id in sorted(stamped):
        relative = f"workspaces/{event_id}.json"
        path = generation_dir / relative
        body = canonical_json_bytes(stamped[event_id])
        if path.exists() and path.read_bytes() != body:
            raise WorkspaceError(f"immutable generation collision: {path}")
        if not path.exists():
            _atomic_write(path, body)
        file_blocks[relative] = {
            "bytes": len(body),
            "sha256": sha256(body).hexdigest(),
        }

    manifest = {
        "aliases": dict(sorted(alias_map.items())),
        "authority": AUTHORITY,
        "event_count": len(stamped),
        "files": dict(sorted(file_blocks.items())),
        "generated_at": str(generated),
        "generation_id": generation_id,
        "schema": MANIFEST_SCHEMA,
        "status": status,
        "warnings": [],
    }
    # Re-order to MANIFEST_KEYS.
    manifest = {key: manifest[key] for key in MANIFEST_KEYS}
    validate_workspace_manifest(manifest)
    manifest_body = canonical_json_bytes(manifest)
    immutable_manifest_path = generation_dir / "manifest.json"
    if immutable_manifest_path.exists() and immutable_manifest_path.read_bytes() != manifest_body:
        raise WorkspaceError(f"immutable generation collision: {immutable_manifest_path}")
    if not immutable_manifest_path.exists():
        _atomic_write(immutable_manifest_path, manifest_body)
    _atomic_write(nest / "manifest.json", manifest_body)
    return generation_dir


def resolve_workspace_event_id(event_id: object, aliases: Mapping[str, str]) -> str:
    """Resolve a canonical id or published alias through the generation manifest."""
    text = str(event_id or "").strip()
    if not text:
        raise WorkspaceError("event_id is required")
    if text in aliases:
        return str(aliases[text])
    if _EVENT_ID_RE.fullmatch(text):
        return text
    raise WorkspaceError(f"unresolved event id: {text}")


def index_from_workspace(payload: Mapping[str, Any]) -> EventAliasIndex:
    extra = payload.get("_aliases")
    if isinstance(extra, Mapping) and extra.get("canonical_event_id"):
        aliases = aliases_for(
            extra["company_id"],
            FiscalPeriod(
                year=int(extra["fiscal_period"]["year"]),
                quarter=extra["fiscal_period"].get("quarter"),
            ),
            extra.get("tickers") or (),
        )
    else:
        aliases = aliases_for(
            payload["issuer"]["company_id"],
            FiscalPeriod(
                year=int(payload["fiscal_period"]["year"]),
                quarter=payload["fiscal_period"].get("quarter"),
            ),
            [
                listing["ticker"]
                for listing in payload.get("issuer", {}).get("listings") or []
            ],
        )
    index = EventAliasIndex()
    index.register(aliases)
    return index
