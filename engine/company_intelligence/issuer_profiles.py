"""Per-issuer extraction profiles for ``event_workspace.v1`` (IMCE A5A).

``event_workspace_build.build_event_workspace`` is generic: identity, filing
binding, GAAP figure extraction (``engine.earnings_release.figures``),
lifecycle, and publication all apply the same way to every issuer.  The one
place a real issuer difference belongs is FACT/CLAIM EXTRACTION — what to read
out of the release body and (if held) the transcript — and that seam is what
this module owns.  An :class:`IssuerProfile` bundles exactly two callables:

* ``extract_release_facts`` — additional ``event_fact.v1`` entries read out of
  the bound Exhibit 99.1 body (or its typed absence).
* ``extract_transcript_claims`` — ``event_claim.v1`` entries read out of the
  held earnings-call transcript (or its typed absence).

No generic code branches on ticker (E3C prior-art law — see
``engine/company_intelligence/event_workspace_build.py``).  ``apple_profile()``
reproduces the pre-A5A ``_GLANCE_SPANS`` transcript-claims behavior with zero
output change; the four homebuilder profiles below are new for A5A.

Every homebuilder's registered CIK is sourced from the accreting
``data/edgar/ticker_cik_ledger.json`` ledger (as of ``origin/main`` pin
``0e57b06d8e23``: DHI 882184, PHM 822416, KBH 795266, TOL 794170) and frozen
into code here — identity is code, not a runtime ``data/`` dependency.  Each
issuer's primary-listing MIC and ``fiscal_year_end_month`` were verified
against that issuer's own SEC ``submissions`` JSON (``exchanges`` /
``fiscalYearEnd`` fields); the exact receipts are quoted in the PR body.

Homebuilder fact extraction never infers a missing figure from prose and
never derives one figure from another by arithmetic (docket law, restated in
the A5A commission).  Every numeric fact is read out of a literal, uniquely
addressable span in the release body via the SAME byte-replayable receipt
machinery ``engine.earnings_release.figures`` already uses for GAAP figures
(``engine.earnings_release.receipts.receipt_for_literal``), scoped to the
containing disclosure block or table cell so that a repeated number elsewhere
in a long release cannot collide with it.  Where a fact is not present, or not
uniquely locatable, the profile emits a :class:`TypedAbsence` from the closed
``ABSENCE_REASONS`` vocabulary instead of guessing.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping, Sequence

from ..earnings_release.binding import BoundRelease
from ..earnings_release.receipts import ReceiptError, SpanReceipt, receipt_for_literal
from ..fundamental_forensics.disclosure_diff import BlockKind, DisclosureBlock
from .documents import text_span
from .event_workspace import _absence, _span_payload_from_transcript
from .identity import IssuerIdentity, ListingAlias, company_id_for_cik


# ─────────────────────────────────────────────────────────────────────────────
# Issuer identity.
#
# CIKs: data/edgar/ticker_cik_ledger.json @ origin/main 0e57b06d8e23 —
#   "DHI": 882184, "PHM": 822416, "KBH": 795266, "TOL": 794170.
# MIC + fiscal_year_end_month: each issuer's SEC submissions JSON
# (https://data.sec.gov/submissions/CIK<cik>.json), `exchanges` and
# `fiscalYearEnd` fields, fetched 2026-08-22 — receipts quoted in the PR body:
#   DHI: exchanges=["NYSE"], fiscalYearEnd="0930" (September)
#   PHM: exchanges=["NYSE"], fiscalYearEnd="1231" (December)
#   KBH: exchanges=["NYSE"], fiscalYearEnd="1130" (November)
#   TOL: exchanges=["NYSE"], fiscalYearEnd="1031" (October)
# NYSE's MIC is XNYS.
# ─────────────────────────────────────────────────────────────────────────────

DHI_CIK = "0000882184"
PHM_CIK = "0000822416"
KBH_CIK = "0000795266"
TOL_CIK = "0000794170"

HOMEBUILDER_TICKERS: tuple[str, ...] = ("DHI", "PHM", "KBH", "TOL")


def dhi_issuer() -> IssuerIdentity:
    return IssuerIdentity(
        company_id=company_id_for_cik(DHI_CIK),
        display_name="D.R. Horton, Inc.",
        fiscal_year_end_month=9,
        reporting_currency="USD",
        listings=(
            ListingAlias(ticker="DHI", mic="XNYS", share_class="common", trading_currency="USD", is_primary=True),
        ),
        external_ids={"cik": DHI_CIK},
    )


def phm_issuer() -> IssuerIdentity:
    return IssuerIdentity(
        company_id=company_id_for_cik(PHM_CIK),
        display_name="PulteGroup, Inc.",
        fiscal_year_end_month=12,
        reporting_currency="USD",
        listings=(
            ListingAlias(ticker="PHM", mic="XNYS", share_class="common", trading_currency="USD", is_primary=True),
        ),
        external_ids={"cik": PHM_CIK},
    )


def kbh_issuer() -> IssuerIdentity:
    return IssuerIdentity(
        company_id=company_id_for_cik(KBH_CIK),
        display_name="KB Home",
        fiscal_year_end_month=11,
        reporting_currency="USD",
        listings=(
            ListingAlias(ticker="KBH", mic="XNYS", share_class="common", trading_currency="USD", is_primary=True),
        ),
        external_ids={"cik": KBH_CIK},
    )


def tol_issuer() -> IssuerIdentity:
    return IssuerIdentity(
        company_id=company_id_for_cik(TOL_CIK),
        display_name="Toll Brothers, Inc.",
        fiscal_year_end_month=10,
        reporting_currency="USD",
        listings=(
            ListingAlias(ticker="TOL", mic="XNYS", share_class="common", trading_currency="USD", is_primary=True),
        ),
        external_ids={"cik": TOL_CIK},
    )


_HOMEBUILDER_ISSUER_FACTORIES: dict[str, Callable[[], IssuerIdentity]] = {
    "DHI": dhi_issuer,
    "PHM": phm_issuer,
    "KBH": kbh_issuer,
    "TOL": tol_issuer,
}


# ``production_registry()`` (apple_issuer() + the four constructors above)
# lives in ``event_workspace.py`` per the A5A file ownership split; it does a
# deferred import of this module to avoid a module-load cycle (this module
# imports private helpers from ``event_workspace`` for the Apple profile).


# ─────────────────────────────────────────────────────────────────────────────
# IssuerProfile — the generic/issuer-specific extraction seam.
# ─────────────────────────────────────────────────────────────────────────────

ReleaseFactExtractor = Callable[..., list[dict[str, Any]]]
TranscriptClaimExtractor = Callable[..., list[dict[str, Any]]]


@dataclass(frozen=True)
class IssuerProfile:
    """Two callables; nothing here inspects ``ticker`` to change behavior.

    ``extract_release_facts(*, bound, document_id, event_id)`` returns
    additional ``event_fact.v1`` entries.

    ``extract_transcript_claims(*, segments, document_id, body_sha256,
    event_id)`` returns ``event_claim.v1`` entries (``[]`` when the issuer's
    profile does not read the transcript, e.g. a homebuilder with no held
    call).
    """

    ticker: str
    extract_release_facts: ReleaseFactExtractor
    extract_transcript_claims: TranscriptClaimExtractor


# ─────────────────────────────────────────────────────────────────────────────
# Apple profile — the pre-A5A ``_GLANCE_SPANS`` transcript-claims behavior,
# moved here unchanged.  Output is byte-identical to before A5A.
# ─────────────────────────────────────────────────────────────────────────────

_AAPL_GLANCE_SPANS: tuple[tuple[str, int, str, str, str], ...] = (
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


def _apple_extract_release_facts(**_kwargs: Any) -> list[dict[str, Any]]:
    return []


def _apple_extract_transcript_claims(
    *,
    segments: Sequence[Mapping[str, Any]],
    document_id: str,
    body_sha256: str,
    event_id: str,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for fact_id, index, literal, kind, metric in _AAPL_GLANCE_SPANS:
        if index >= len(segments):
            payload = None
            segment: Mapping[str, Any] = {}
        else:
            segment = segments[index]
            payload = _span_payload_from_transcript(
                document_id=document_id,
                body_sha256=body_sha256,
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
                    document_id=document_id,
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
    return claims


def apple_profile() -> IssuerProfile:
    return IssuerProfile(
        ticker="AAPL",
        extract_release_facts=_apple_extract_release_facts,
        extract_transcript_claims=_apple_extract_transcript_claims,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Homebuilder release-fact extraction — shared receipt/absence plumbing.
# ─────────────────────────────────────────────────────────────────────────────

def _release_span_payload(*, document_id: str, bound: BoundRelease, receipt: SpanReceipt) -> dict[str, Any]:
    span = text_span(
        document_id=document_id,
        document_version=1,
        body_sha256=bound.revision.source_sha256,
        segment_index=0,
        segment_text=bound.source,
        start_byte=receipt.byte_start,
        end_byte=receipt.byte_end,
        text=receipt.span_text,
        rights_profile="rp_public_primary_v1",
    )
    return span.to_payload()


def _fact_present(
    *,
    fact_id: str,
    event_id: str,
    metric: str,
    value: Any,
    unit: str | None,
    period: str | None,
    basis: str,
    document_id: str,
    bound: BoundRelease,
    receipt: SpanReceipt,
) -> dict[str, Any]:
    return {
        "schema": "event_fact.v1",
        "fact_id": fact_id,
        "event_id": event_id,
        "metric": metric,
        "value": value,
        "unit": unit,
        "period": period,
        "basis": basis,
        "source_span": _release_span_payload(document_id=document_id, bound=bound, receipt=receipt),
    }


def _fact_absent(*, fact_id: str, event_id: str, metric: str, detail: str, document_id: str) -> dict[str, Any]:
    return {
        "schema": "event_fact.v1",
        "fact_id": fact_id,
        "event_id": event_id,
        "metric": metric,
        "typed_absence": _absence(
            reason="no_span_addressable_evidence",
            subject=metric,
            detail=detail,
            event_id=event_id,
            document_id=document_id,
        ),
    }


def _literal_receipt(bound: BoundRelease, *, search_start: int, search_end: int, literal: str) -> SpanReceipt | None:
    try:
        return receipt_for_literal(
            source=bound.source,
            source_sha256=bound.revision.source_sha256,
            search_start=search_start,
            search_end=search_end,
            literal=literal,
        )
    except ReceiptError:
        return None


def _find_paragraph_containing(blocks: Sequence[DisclosureBlock], needle: str) -> DisclosureBlock | None:
    lower = needle.lower()
    for block in blocks:
        if lower in block.text.lower():
            return block
    return None


def _find_table_after_heading(blocks: Sequence[DisclosureBlock], heading: str) -> DisclosureBlock | None:
    lower = heading.lower()
    for block in blocks:
        if block.kind is BlockKind.TABLE and block.table is not None and block.table.rows:
            probe = " ".join(cell.text for row in block.table.rows[:3] for cell in row)
            if lower in probe.lower():
                return block
    return None


def _find_row_by_label(blocks: Sequence[DisclosureBlock], label: str):
    lower = label.strip().lower()
    for block in blocks:
        if block.kind is BlockKind.TABLE and block.table is not None:
            for row in block.table.rows:
                if row and row[0].text.strip().lower() == lower:
                    return row
    return None


def _nonblank_cells(row) -> list:
    return [cell for cell in row if cell.text.strip() not in ("", "$")]


def _period_label(fiscal_period: Any) -> str | None:
    calendar_end = getattr(fiscal_period, "calendar_end", None)
    return calendar_end.isoformat() if calendar_end else None


# ─────────────────────────────────────────────────────────────────────────────
# DHI — cancellation rate = cancelled sales orders / gross sales orders.
# Verified against DHI's real FY2026 Q3 8-K, accession 0000882184-26-000092
# (filed 2026-07-21), Exhibit 99.1 — see tests/fixtures/company_intelligence.
# ─────────────────────────────────────────────────────────────────────────────

_DHI_NET_ORDERS_RE = re.compile(
    r"Net sales orders (?:totaled|of) ([\d,]+) homes with an order value of \$[\d.,]+ (?:billion|million)"
)
_DHI_CANCELLATION_RE = re.compile(
    r"cancellation rate \(([^)]+)\) for the quarter was (\d+(?:\.\d+)?)% compared to (\d+(?:\.\d+)?)% "
    r"in the prior year quarter"
)


def _dhi_extract_release_facts(*, bound: BoundRelease, document_id: str, event_id: str, **kwargs: Any) -> list[dict[str, Any]]:
    fiscal_period = kwargs.get("fiscal_period")
    period = _period_label(fiscal_period)
    blocks = bound.document.blocks
    facts: list[dict[str, Any]] = []

    # (i) net_orders current period.
    para = _find_paragraph_containing(blocks, "net sales orders")
    current_fact: dict[str, Any] | None = None
    if para is not None:
        match = _DHI_NET_ORDERS_RE.search(para.text)
        if match is not None:
            receipt = _literal_receipt(
                bound, search_start=para.source_span.char_start, search_end=para.source_span.char_end,
                literal=match.group(0),
            )
            if receipt is not None:
                current_fact = _fact_present(
                    fact_id="fact_net_orders_current", event_id=event_id, metric="net_orders",
                    value=int(match.group(1).replace(",", "")), unit="homes", period=period,
                    basis="DHI quarterly net sales orders (homes), as disclosed in Exhibit 99.1",
                    document_id=document_id, bound=bound, receipt=receipt,
                )
    facts.append(current_fact or _fact_absent(
        fact_id="fact_net_orders_current", event_id=event_id, metric="net_orders",
        detail="net sales orders is not uniquely addressable in Exhibit 99.1", document_id=document_id,
    ))

    # (ii) net_orders same-basis prior-year comparator — the NET SALES ORDERS
    # table's unlabeled total row, homes column, prior-year quarter.
    prior_fact: dict[str, Any] | None = None
    table_block = _find_table_after_heading(blocks, "NET SALES ORDERS")
    if table_block is not None and table_block.table.rows:
        total_row = table_block.table.rows[-1]
        cells = _nonblank_cells(total_row)
        if len(cells) >= 3:
            cell = cells[2]
            receipt = _literal_receipt(
                bound, search_start=cell.source_span.char_start, search_end=cell.source_span.char_end,
                literal=cell.text,
            )
            if receipt is not None:
                try:
                    value = int(cell.text.replace(",", ""))
                except ValueError:
                    value = None
                if value is not None:
                    prior_fact = _fact_present(
                        fact_id="fact_net_orders_prior_year", event_id=event_id, metric="net_orders",
                        value=value, unit="homes", period="prior_year_same_quarter",
                        basis="DHI same-quarter-prior-year net sales orders (homes), as disclosed in Exhibit 99.1",
                        document_id=document_id, bound=bound, receipt=receipt,
                    )
    facts.append(prior_fact or _fact_absent(
        fact_id="fact_net_orders_prior_year", event_id=event_id, metric="net_orders",
        detail="prior-year same-quarter net sales orders total is not uniquely addressable in Exhibit 99.1",
        document_id=document_id,
    ))

    # (iii)/(iv)/(v) cancellation rate current, prior-year comparator, and the
    # stated denominator convention — all three cite the same disclosure
    # sentence.
    cancel_para = _find_paragraph_containing(blocks, "cancellation rate")
    match = _DHI_CANCELLATION_RE.search(cancel_para.text) if cancel_para is not None else None
    if cancel_para is not None and match is not None:
        denom_text, current_pct, prior_pct = match.group(1), match.group(2), match.group(3)
        current_lit, prior_lit = f"{current_pct}%", f"{prior_pct}%"
        current_receipt = _literal_receipt(
            bound, search_start=cancel_para.source_span.char_start, search_end=cancel_para.source_span.char_end,
            literal=current_lit,
        )
        prior_receipt = _literal_receipt(
            bound, search_start=cancel_para.source_span.char_start, search_end=cancel_para.source_span.char_end,
            literal=prior_lit,
        )
        denom_receipt = _literal_receipt(
            bound, search_start=cancel_para.source_span.char_start, search_end=cancel_para.source_span.char_end,
            literal=denom_text,
        )
    else:
        current_receipt = prior_receipt = denom_receipt = None
        current_pct = prior_pct = denom_text = None

    basis_text = "cancelled sales orders divided by gross sales orders (DHI convention)"
    facts.append(
        _fact_present(
            fact_id="fact_cancellation_rate_current", event_id=event_id, metric="cancellation_rate",
            value=float(current_pct), unit="percent", period=period, basis=basis_text,
            document_id=document_id, bound=bound, receipt=current_receipt,
        )
        if current_receipt is not None
        else _fact_absent(
            fact_id="fact_cancellation_rate_current", event_id=event_id, metric="cancellation_rate",
            detail="cancellation rate is not present or not uniquely addressable in Exhibit 99.1",
            document_id=document_id,
        )
    )
    facts.append(
        _fact_present(
            fact_id="fact_cancellation_rate_prior_year", event_id=event_id, metric="cancellation_rate",
            value=float(prior_pct), unit="percent", period="prior_year_same_quarter", basis=basis_text,
            document_id=document_id, bound=bound, receipt=prior_receipt,
        )
        if prior_receipt is not None
        else _fact_absent(
            fact_id="fact_cancellation_rate_prior_year", event_id=event_id, metric="cancellation_rate",
            detail="prior-year cancellation rate is not present or not uniquely addressable in Exhibit 99.1",
            document_id=document_id,
        )
    )
    facts.append(
        _fact_present(
            fact_id="fact_cancellation_rate_denominator", event_id=event_id, metric="cancellation_rate_basis",
            value=denom_text, unit=None, period=None, basis=basis_text,
            document_id=document_id, bound=bound, receipt=denom_receipt,
        )
        if denom_receipt is not None
        else _fact_absent(
            fact_id="fact_cancellation_rate_denominator", event_id=event_id, metric="cancellation_rate_basis",
            detail="the stated cancellation denominator convention is not present in Exhibit 99.1",
            document_id=document_id,
        )
    )
    return facts


def dhi_profile() -> IssuerProfile:
    return IssuerProfile(
        ticker="DHI",
        extract_release_facts=_dhi_extract_release_facts,
        extract_transcript_claims=lambda **_kwargs: [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# PHM — net new orders by region table; PulteGroup's EX-99.1 press release
# does not always disclose a cancellation rate (verified: its FY2026 Q2 8-K,
# accession 0000822416-26-000034, carries none — a genuine typed absence, not
# a missed pattern).
# ─────────────────────────────────────────────────────────────────────────────

_PHM_CANCELLATION_RE = re.compile(r"cancellation rate[^.]*was (\d+(?:\.\d+)?)%,? compared to (\d+(?:\.\d+)?)%")


def _phm_section_total_row(table_block: DisclosureBlock, section_label: str):
    rows = table_block.table.rows
    in_section = False
    for row in rows:
        first = row[0].text.strip() if row else ""
        if not in_section:
            if first.lower() == section_label.lower():
                in_section = True
            continue
        if first == "" and any(cell.text.strip() not in ("", "$") for cell in row):
            return row
    return None


def _phm_extract_release_facts(*, bound: BoundRelease, document_id: str, event_id: str, **kwargs: Any) -> list[dict[str, Any]]:
    fiscal_period = kwargs.get("fiscal_period")
    period = _period_label(fiscal_period)
    blocks = bound.document.blocks
    facts: list[dict[str, Any]] = []

    table_block = _find_paragraph_table(blocks, "Net new orders - units")
    current_fact = prior_fact = None
    if table_block is not None:
        total_row = _phm_section_total_row(table_block, "Net new orders - units")
        if total_row is not None:
            cells = _nonblank_cells(total_row)
            if len(cells) >= 2:
                for idx, fact_id, basis_label, period_label in (
                    (0, "fact_net_orders_current", "PulteGroup quarterly net new orders (homes), as disclosed in Exhibit 99.1", period),
                    (1, "fact_net_orders_prior_year", "PulteGroup same-quarter-prior-year net new orders (homes), as disclosed in Exhibit 99.1", "prior_year_same_quarter"),
                ):
                    cell = cells[idx]
                    receipt = _literal_receipt(
                        bound, search_start=cell.source_span.char_start, search_end=cell.source_span.char_end,
                        literal=cell.text,
                    )
                    if receipt is None:
                        continue
                    try:
                        value = int(cell.text.replace(",", ""))
                    except ValueError:
                        continue
                    fact = _fact_present(
                        fact_id=fact_id, event_id=event_id, metric="net_orders", value=value, unit="homes",
                        period=period_label, basis=basis_label, document_id=document_id, bound=bound, receipt=receipt,
                    )
                    if idx == 0:
                        current_fact = fact
                    else:
                        prior_fact = fact
    facts.append(current_fact or _fact_absent(
        fact_id="fact_net_orders_current", event_id=event_id, metric="net_orders",
        detail="net new orders is not uniquely addressable in Exhibit 99.1", document_id=document_id,
    ))
    facts.append(prior_fact or _fact_absent(
        fact_id="fact_net_orders_prior_year", event_id=event_id, metric="net_orders",
        detail="prior-year same-quarter net new orders total is not uniquely addressable in Exhibit 99.1",
        document_id=document_id,
    ))

    cancel_para = _find_paragraph_containing(blocks, "cancellation rate")
    match = _PHM_CANCELLATION_RE.search(cancel_para.text) if cancel_para is not None else None
    basis_text = "PulteGroup cancellation rate convention, as stated in Exhibit 99.1"
    if cancel_para is not None and match is not None:
        current_receipt = _literal_receipt(
            bound, search_start=cancel_para.source_span.char_start, search_end=cancel_para.source_span.char_end,
            literal=f"{match.group(1)}%",
        )
        prior_receipt = _literal_receipt(
            bound, search_start=cancel_para.source_span.char_start, search_end=cancel_para.source_span.char_end,
            literal=f"{match.group(2)}%",
        )
    else:
        current_receipt = prior_receipt = None
    for fact_id, receipt, value, period_label, detail in (
        (
            "fact_cancellation_rate_current", current_receipt,
            float(match.group(1)) if match else None, period,
            "cancellation rate is not disclosed in this Exhibit 99.1 (PulteGroup does not always state one)",
        ),
        (
            "fact_cancellation_rate_prior_year", prior_receipt,
            float(match.group(2)) if match else None, "prior_year_same_quarter",
            "prior-year cancellation rate is not disclosed in this Exhibit 99.1",
        ),
    ):
        facts.append(
            _fact_present(
                fact_id=fact_id, event_id=event_id, metric="cancellation_rate", value=value, unit="percent",
                period=period_label, basis=basis_text, document_id=document_id, bound=bound, receipt=receipt,
            )
            if receipt is not None
            else _fact_absent(fact_id=fact_id, event_id=event_id, metric="cancellation_rate", detail=detail, document_id=document_id)
        )
    facts.append(_fact_absent(
        fact_id="fact_cancellation_rate_denominator", event_id=event_id, metric="cancellation_rate_basis",
        detail="the stated cancellation denominator convention is not disclosed in this Exhibit 99.1",
        document_id=document_id,
    ) if current_receipt is None else _fact_absent(
        fact_id="fact_cancellation_rate_denominator", event_id=event_id, metric="cancellation_rate_basis",
        detail="PulteGroup's cancellation rate sentence does not state an explicit denominator convention in this Exhibit 99.1",
        document_id=document_id,
    ))
    return facts


def _find_paragraph_table(blocks: Sequence[DisclosureBlock], row_label: str) -> DisclosureBlock | None:
    """A table block located by an exact row label rather than a heading probe."""
    lower = row_label.strip().lower()
    for block in blocks:
        if block.kind is BlockKind.TABLE and block.table is not None:
            for row in block.table.rows:
                if row and row[0].text.strip().lower() == lower:
                    return block
    return None


def phm_profile() -> IssuerProfile:
    return IssuerProfile(
        ticker="PHM",
        extract_release_facts=_phm_extract_release_facts,
        extract_transcript_claims=lambda **_kwargs: [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# KBH — cancellation rate = percentage of gross orders.
# ─────────────────────────────────────────────────────────────────────────────

_KBH_CANCELLATION_RE = re.compile(
    r"cancellation rate as a percentage of gross orders was (\d+(?:\.\d+)?)%,? compared to (\d+(?:\.\d+)?)%"
)


def _kbh_total_row_after_label(blocks: Sequence[DisclosureBlock], section_label: str):
    lower = section_label.strip().lower()
    for block in blocks:
        if block.kind is not BlockKind.TABLE or block.table is None:
            continue
        in_section = False
        for row in block.table.rows:
            first = row[0].text.strip() if row else ""
            if not in_section:
                if first.lower() == lower:
                    in_section = True
                continue
            if first.strip().lower() == "total":
                return row
        # keep scanning subsequent table blocks if this one had no section
    return None


def _kbh_extract_release_facts(*, bound: BoundRelease, document_id: str, event_id: str, **kwargs: Any) -> list[dict[str, Any]]:
    fiscal_period = kwargs.get("fiscal_period")
    period = _period_label(fiscal_period)
    blocks = bound.document.blocks
    facts: list[dict[str, Any]] = []

    total_row = _kbh_total_row_after_label(blocks, "Net orders:")
    current_fact = prior_fact = None
    if total_row is not None:
        cells = [cell for cell in total_row[1:] if cell.text.strip() not in ("", "$")]
        if len(cells) >= 2:
            for idx, fact_id, basis_label, period_label in (
                (0, "fact_net_orders_current", "KB Home quarterly net orders (homes), as disclosed in Exhibit 99.1", period),
                (1, "fact_net_orders_prior_year", "KB Home same-quarter-prior-year net orders (homes), as disclosed in Exhibit 99.1", "prior_year_same_quarter"),
            ):
                cell = cells[idx]
                receipt = _literal_receipt(
                    bound, search_start=cell.source_span.char_start, search_end=cell.source_span.char_end,
                    literal=cell.text,
                )
                if receipt is None:
                    continue
                try:
                    value = int(cell.text.replace(",", ""))
                except ValueError:
                    continue
                fact = _fact_present(
                    fact_id=fact_id, event_id=event_id, metric="net_orders", value=value, unit="homes",
                    period=period_label, basis=basis_label, document_id=document_id, bound=bound, receipt=receipt,
                )
                if idx == 0:
                    current_fact = fact
                else:
                    prior_fact = fact
    facts.append(current_fact or _fact_absent(
        fact_id="fact_net_orders_current", event_id=event_id, metric="net_orders",
        detail="net orders is not uniquely addressable in Exhibit 99.1", document_id=document_id,
    ))
    facts.append(prior_fact or _fact_absent(
        fact_id="fact_net_orders_prior_year", event_id=event_id, metric="net_orders",
        detail="prior-year same-quarter net orders total is not uniquely addressable in Exhibit 99.1",
        document_id=document_id,
    ))

    cancel_para = _find_paragraph_containing(blocks, "cancellation rate as a percentage of gross orders")
    match = _KBH_CANCELLATION_RE.search(cancel_para.text) if cancel_para is not None else None
    basis_text = "cancellation rate as a percentage of gross orders (KB Home convention)"
    if cancel_para is not None and match is not None:
        current_receipt = _literal_receipt(
            bound, search_start=cancel_para.source_span.char_start, search_end=cancel_para.source_span.char_end,
            literal=f"{match.group(1)}%",
        )
        prior_receipt = _literal_receipt(
            bound, search_start=cancel_para.source_span.char_start, search_end=cancel_para.source_span.char_end,
            literal=f"{match.group(2)}%",
        )
        denom_receipt = _literal_receipt(
            bound, search_start=cancel_para.source_span.char_start, search_end=cancel_para.source_span.char_end,
            literal="as a percentage of gross orders",
        )
    else:
        current_receipt = prior_receipt = denom_receipt = None
    for fact_id, receipt, value, period_label, metric, detail in (
        (
            "fact_cancellation_rate_current", current_receipt, float(match.group(1)) if match else None, period,
            "cancellation_rate", "cancellation rate is not present or not uniquely addressable in Exhibit 99.1",
        ),
        (
            "fact_cancellation_rate_prior_year", prior_receipt, float(match.group(2)) if match else None,
            "prior_year_same_quarter", "cancellation_rate",
            "prior-year cancellation rate is not present or not uniquely addressable in Exhibit 99.1",
        ),
        (
            "fact_cancellation_rate_denominator", denom_receipt, "as a percentage of gross orders" if match else None,
            None, "cancellation_rate_basis",
            "the stated cancellation denominator convention is not present in Exhibit 99.1",
        ),
    ):
        facts.append(
            _fact_present(
                fact_id=fact_id, event_id=event_id, metric=metric, value=value,
                unit=("percent" if metric == "cancellation_rate" else None), period=period_label, basis=basis_text,
                document_id=document_id, bound=bound, receipt=receipt,
            )
            if receipt is not None
            else _fact_absent(fact_id=fact_id, event_id=event_id, metric=metric, detail=detail, document_id=document_id)
        )
    return facts


def kbh_profile() -> IssuerProfile:
    return IssuerProfile(
        ticker="KBH",
        extract_release_facts=_kbh_extract_release_facts,
        extract_transcript_claims=lambda **_kwargs: [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOL — primary convention is signed contracts in the quarter; the
# beginning-quarter-backlog cancellation measure is a mandatory sensitivity
# fact carried alongside it (frozen spec item 4(vi)).
# ─────────────────────────────────────────────────────────────────────────────

_TOL_UNITS_RE = re.compile(r"([\d,]+) units")


def _tol_extract_release_facts(*, bound: BoundRelease, document_id: str, event_id: str, **kwargs: Any) -> list[dict[str, Any]]:
    fiscal_period = kwargs.get("fiscal_period")
    period = _period_label(fiscal_period)
    blocks = bound.document.blocks
    facts: list[dict[str, Any]] = []

    row = _find_row_by_label(blocks, "Net Signed Contracts")
    current_fact = prior_fact = None
    if row is not None:
        cells = [cell for cell in row[1:] if cell.text.strip() != ""]
        if len(cells) >= 2:
            for idx, fact_id, basis_label, period_label in (
                (0, "fact_net_orders_current", "Toll Brothers quarterly net signed contracts (units), as disclosed in Exhibit 99.1", period),
                (1, "fact_net_orders_prior_year", "Toll Brothers same-quarter-prior-year net signed contracts (units), as disclosed in Exhibit 99.1", "prior_year_same_quarter"),
            ):
                cell = cells[idx]
                units_match = _TOL_UNITS_RE.search(cell.text)
                if units_match is None:
                    continue
                literal = units_match.group(0)
                receipt = _literal_receipt(
                    bound, search_start=cell.source_span.char_start, search_end=cell.source_span.char_end,
                    literal=literal,
                )
                if receipt is None:
                    continue
                fact = _fact_present(
                    fact_id=fact_id, event_id=event_id, metric="net_orders",
                    value=int(units_match.group(1).replace(",", "")), unit="homes", period=period_label,
                    basis=basis_label, document_id=document_id, bound=bound, receipt=receipt,
                )
                if idx == 0:
                    current_fact = fact
                else:
                    prior_fact = fact
    facts.append(current_fact or _fact_absent(
        fact_id="fact_net_orders_current", event_id=event_id, metric="net_orders",
        detail="net signed contracts is not uniquely addressable in Exhibit 99.1", document_id=document_id,
    ))
    facts.append(prior_fact or _fact_absent(
        fact_id="fact_net_orders_prior_year", event_id=event_id, metric="net_orders",
        detail="prior-year same-quarter net signed contracts is not uniquely addressable in Exhibit 99.1",
        document_id=document_id,
    ))

    basis_text = "quarterly cancellations as a percentage of signed contracts in the quarter (Toll Brothers primary convention)"
    cancel_row = _find_row_by_label(blocks, "Quarterly Cancellations as a Percentage of Signed Contracts in Quarter")
    current_receipt = prior_receipt = None
    if cancel_row is not None:
        cells = [cell for cell in cancel_row[1:] if cell.text.strip() not in ("", "%")]
        if len(cells) >= 2:
            current_receipt = _literal_receipt(
                bound, search_start=cells[0].source_span.char_start, search_end=cells[0].source_span.char_end,
                literal=cells[0].text,
            )
            prior_receipt = _literal_receipt(
                bound, search_start=cells[1].source_span.char_start, search_end=cells[1].source_span.char_end,
                literal=cells[1].text,
            )
    for fact_id, receipt, cell_text, period_label, detail in (
        (
            "fact_cancellation_rate_current", current_receipt, cells[0].text if cancel_row is not None and current_receipt else None,
            period, "quarterly cancellation-as-percentage-of-signed-contracts is not present in Exhibit 99.1",
        ),
        (
            "fact_cancellation_rate_prior_year", prior_receipt, cells[1].text if cancel_row is not None and prior_receipt else None,
            "prior_year_same_quarter", "prior-year quarterly cancellation-as-percentage-of-signed-contracts is not present in Exhibit 99.1",
        ),
    ):
        facts.append(
            _fact_present(
                fact_id=fact_id, event_id=event_id, metric="cancellation_rate", value=float(cell_text),
                unit="percent", period=period_label, basis=basis_text, document_id=document_id, bound=bound,
                receipt=receipt,
            )
            if receipt is not None
            else _fact_absent(fact_id=fact_id, event_id=event_id, metric="cancellation_rate", detail=detail, document_id=document_id)
        )
    facts.append(_fact_present(
        fact_id="fact_cancellation_rate_denominator", event_id=event_id, metric="cancellation_rate_basis",
        value="signed contracts in quarter", unit=None, period=None, basis=basis_text,
        document_id=document_id, bound=bound, receipt=current_receipt,
    ) if current_receipt is not None else _fact_absent(
        fact_id="fact_cancellation_rate_denominator", event_id=event_id, metric="cancellation_rate_basis",
        detail="the stated cancellation denominator convention is not present in Exhibit 99.1", document_id=document_id,
    ))

    # (vi) TOL only: beginning-quarter-backlog cancellation sensitivity fact.
    backlog_row = _find_row_by_label(blocks, "Quarterly Cancellations as a Percentage of Beginning-Quarter Backlog")
    backlog_basis = "quarterly cancellations as a percentage of beginning-quarter backlog (Toll Brothers sensitivity convention)"
    backlog_receipt = None
    backlog_value = None
    if backlog_row is not None:
        cells = [cell for cell in backlog_row[1:] if cell.text.strip() not in ("", "%")]
        if cells:
            backlog_receipt = _literal_receipt(
                bound, search_start=cells[0].source_span.char_start, search_end=cells[0].source_span.char_end,
                literal=cells[0].text,
            )
            backlog_value = cells[0].text if backlog_receipt is not None else None
    facts.append(
        _fact_present(
            fact_id="fact_cancellation_rate_beginning_backlog_sensitivity", event_id=event_id,
            metric="cancellation_rate_sensitivity", value=float(backlog_value), unit="percent", period=period,
            basis=backlog_basis, document_id=document_id, bound=bound, receipt=backlog_receipt,
        )
        if backlog_receipt is not None
        else _fact_absent(
            fact_id="fact_cancellation_rate_beginning_backlog_sensitivity", event_id=event_id,
            metric="cancellation_rate_sensitivity",
            detail="the beginning-quarter-backlog cancellation sensitivity measure is not present in Exhibit 99.1",
            document_id=document_id,
        )
    )
    return facts


def tol_profile() -> IssuerProfile:
    return IssuerProfile(
        ticker="TOL",
        extract_release_facts=_tol_extract_release_facts,
        extract_transcript_claims=lambda **_kwargs: [],
    )


_HOMEBUILDER_PROFILE_FACTORIES: dict[str, Callable[[], IssuerProfile]] = {
    "DHI": dhi_profile,
    "PHM": phm_profile,
    "KBH": kbh_profile,
    "TOL": tol_profile,
}


def issuer_for_ticker(ticker: str) -> IssuerIdentity | None:
    """The registered :class:`IssuerIdentity` for one of the four homebuilders.

    ``None`` for AAPL (use :func:`event_workspace.apple_issuer` directly) and
    for any unknown ticker.  Acquisition needs the CIK and
    ``fiscal_year_end_month`` before an event's fiscal period can be derived
    from a discovered filing's ``report_date``, which is why this is exposed
    separately from :func:`profile_for_ticker`.
    """
    factory = _HOMEBUILDER_ISSUER_FACTORIES.get(str(ticker or "").strip().upper())
    return factory() if factory is not None else None


def profile_for_ticker(ticker: str) -> IssuerProfile | None:
    """The registered profile for *ticker*, or ``None`` for an unknown ticker.

    ``"AAPL"`` resolves to :func:`apple_profile`; unknown tickers (including
    LEN and NVR, deliberately not added this wave) resolve to ``None`` so a
    caller can fail closed rather than silently defaulting to Apple's profile.
    """
    normalized = str(ticker or "").strip().upper()
    if normalized == "AAPL":
        return apple_profile()
    factory = _HOMEBUILDER_PROFILE_FACTORIES.get(normalized)
    return factory() if factory is not None else None


__all__ = [
    "DHI_CIK",
    "PHM_CIK",
    "KBH_CIK",
    "TOL_CIK",
    "HOMEBUILDER_TICKERS",
    "IssuerProfile",
    "apple_profile",
    "dhi_issuer",
    "phm_issuer",
    "kbh_issuer",
    "tol_issuer",
    "dhi_profile",
    "phm_profile",
    "kbh_profile",
    "tol_profile",
    "issuer_for_ticker",
    "profile_for_ticker",
]
