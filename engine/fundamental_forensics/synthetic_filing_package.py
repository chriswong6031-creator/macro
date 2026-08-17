"""Synthetic filing-package fixture authoring for FIF tests.

This module is test/fixture-regen support. It is not part of the governed
``packet_builder_digest``: production assembly lives in
``financial_intelligence_packet.py``. Editing this file must not change a
packet's builder identity.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

from .financial_intelligence_packet import (
    FIXTURE_IDENTITY_BASIS,
    FilingPackageFixture,
    EntityInput,
)
from .raw_ledger import (
    FactContext,
    FactEventType,
    FactUnit,
    RawFactLedger,
    RawFactOccurrence,
    SourceIdentity,
    make_raw_fact,
    utc_text,
)


SYNTHETIC_ENTITY_ID = "0000999999"
SYNTHETIC_TICKER = "FIP1"
SYNTHETIC_NAME = "SYNTHETIC FILING PACKAGE CORP"
_USD = FactUnit("USD", ["iso4217:USD"])
_PURE = FactUnit("xbrli:pure", ["xbrli:pure"])

# Restatements are source-published with the FY2024 10-K (2025-02-15) but
# Mastermind records them later. Catalog/mapping/formula rules become
# available at 2026-08-02T00:00:00Z, so the system-recorded restatement
# clock sits after that lane-inception time and before the golden
# recorded cutoff 2026-08-05T12:00:02Z. That is what makes source and
# system clocks independently variable without collapsing into
# "governance unavailable".
RESTATEMENT_RECORDED_AT = "2026-08-04T12:00:00Z"


def build_synthetic_filing_package_fixture() -> FilingPackageFixture:
    """Independent filing-package ledger. Not derived from Company Facts rows."""
    entity = EntityInput(
        entity_id=SYNTHETIC_ENTITY_ID,
        cik=SYNTHETIC_ENTITY_ID,
        ticker=SYNTHETIC_TICKER,
        name=SYNTHETIC_NAME,
        identity_basis=FIXTURE_IDENTITY_BASIS,
    )
    fy2022 = FactContext(
        context_id="c-fy2022",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2022-01-01",
        end="2022-12-31",
    )
    fy2023 = FactContext(
        context_id="c-fy2023",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2023-01-01",
        end="2023-12-31",
    )
    fy2024 = FactContext(
        context_id="c-fy2024",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2024-01-01",
        end="2024-12-31",
    )
    instant_2023 = FactContext(
        context_id="c-i-20231231",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        instant="2023-12-31",
    )
    instant_2024 = FactContext(
        context_id="c-i-20241231",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        instant="2024-12-31",
    )

    k23 = filing(
        accession="0000999999-23-000010",
        document_id="fip1-20221231.htm",
        accepted_at="2023-02-15T16:00:00Z",
        recorded_at="2023-02-15T16:05:00Z",
        filed_at="2023-02-15",
    )
    k24 = filing(
        accession="0000999999-24-000010",
        document_id="fip1-20231231.htm",
        accepted_at="2024-02-15T16:00:00Z",
        recorded_at="2024-02-15T16:05:00Z",
        filed_at="2024-02-15",
    )
    k25 = filing(
        accession="0000999999-25-000010",
        document_id="fip1-20241231.htm",
        accepted_at="2025-02-15T16:00:00Z",
        recorded_at="2025-02-15T16:05:00Z",
        filed_at="2025-02-15",
    )

    fy2022_revenue_a = usd_fact(
        k23, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2022, "1000",
        source_span=(0, 4), source_occurrence_key="fy2022-revenue-span-a",
    )
    fy2022_revenue_b = usd_fact(
        k23, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2022, "1000",
        source_span=(80, 84), source_occurrence_key="fy2022-revenue-span-b",
    )
    fy2022_gp = usd_fact(
        k23, "us-gaap:GrossProfit", fy2022, "480",
        source_span=(8, 11), source_occurrence_key="fy2022-gross-profit",
    )
    fy2023_revenue_original = usd_fact(
        k24, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2023, "1050",
        source_span=(0, 4), source_occurrence_key="fy2023-revenue-original",
    )
    fy2023_gp = usd_fact(
        k24, "us-gaap:GrossProfit", fy2023, "500",
        source_span=(8, 11), source_occurrence_key="fy2023-gross-profit",
    )
    ar_2023_original = usd_fact(
        k24, "us-gaap:AccountsReceivableNetCurrent", instant_2023, "120",
        source_span=(20, 23), source_occurrence_key="ar-2023-original",
    )
    fy2024_revenue = usd_fact(
        k25, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2024, "1120",
        source_span=(0, 4), source_occurrence_key="fy2024-revenue",
    )
    fy2024_gp = usd_fact(
        k25, "us-gaap:GrossProfit", fy2024, "560",
        source_span=(8, 11), source_occurrence_key="fy2024-gross-profit",
    )
    fy2023_gp_restated = usd_fact(
        k25, "us-gaap:GrossProfit", fy2023, "500",
        source_span=(12, 15), source_occurrence_key="fy2023-gross-profit-restated",
        event_type=FactEventType.RESTATEMENT,
        revision_of=fy2023_gp.occurrence_id,
        recorded_at=RESTATEMENT_RECORDED_AT,
    )
    fy2023_revenue_restated = usd_fact(
        k25, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2023, "1060",
        source_span=(40, 44), source_occurrence_key="fy2023-revenue-restated",
        event_type=FactEventType.RESTATEMENT,
        revision_of=fy2023_revenue_original.occurrence_id,
        recorded_at=RESTATEMENT_RECORDED_AT,
    )
    ar_2024 = usd_fact(
        k25, "us-gaap:AccountsReceivableNetCurrent", instant_2024, "155",
        source_span=(20, 23), source_occurrence_key="ar-2024",
    )
    ar_2023_restated = usd_fact(
        k25, "us-gaap:AccountsReceivableNetCurrent", instant_2023, "121",
        source_span=(60, 63), source_occurrence_key="ar-2023-restated",
        event_type=FactEventType.RESTATEMENT,
        revision_of=ar_2023_original.occurrence_id,
        recorded_at=RESTATEMENT_RECORDED_AT,
    )
    customer_count = make_raw_fact(
        source=k25["source"],
        concept_qname="custom:CustomerCount",
        context=instant_2024,
        unit=_PURE,
        raw_token="42",
        parsed_value="42",
        dimensions_known=True,
        decimals="0",
        source_span=(90, 92),
        source_occurrence_key="custom-customer-count",
        accepted_at=k25["accepted_at"],
        recorded_at=k25["recorded_at"],
        event_type=FactEventType.FILED,
    )
    short_term_debt_2024 = usd_fact(
        k25, "us-gaap:ShortTermBorrowings", instant_2024, "10",
        source_span=(200, 202), source_occurrence_key="std-2024",
    )
    long_term_debt_current_2024 = usd_fact(
        k25, "us-gaap:LongTermDebtCurrent", instant_2024, "20",
        source_span=(204, 206), source_occurrence_key="ltdc-2024",
    )
    long_term_debt_2024 = usd_fact(
        k25, "us-gaap:LongTermDebtNoncurrent", instant_2024, "70",
        source_span=(208, 210), source_occurrence_key="ltd-2024",
    )
    cash_2024 = usd_fact(
        k25, "us-gaap:CashAndCashEquivalentsAtCarryingValue", instant_2024, "15",
        source_span=(212, 214), source_occurrence_key="cash-2024",
    )

    events = (
        fy2022_revenue_a,
        fy2022_revenue_b,
        fy2022_gp,
        fy2023_revenue_original,
        fy2023_gp,
        ar_2023_original,
        fy2024_revenue,
        fy2024_gp,
        fy2023_gp_restated,
        fy2023_revenue_restated,
        ar_2024,
        ar_2023_restated,
        customer_count,
        short_term_debt_2024,
        long_term_debt_current_2024,
        long_term_debt_2024,
        cash_2024,
    )
    return FilingPackageFixture(
        entity=entity,
        ledger=RawFactLedger(events),
        filing_metadata=_metadata_for(events, {"23-000010": k23, "24-000010": k24, "25-000010": k25}),
    )


def build_multihop_revenue_fixture() -> FilingPackageFixture:
    """A → B → C revision chain on FY2023 revenue using governed event types."""
    base = build_synthetic_filing_package_fixture()
    fy2023 = FactContext(
        context_id="c-fy2023",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2023-01-01",
        end="2023-12-31",
    )
    hop_c = filing(
        accession="0000999999-26-000010",
        document_id="fip1-2023-amend.htm",
        accepted_at="2026-03-01T16:00:00Z",
        recorded_at="2026-08-04T18:00:00Z",
        filed_at="2026-03-01",
    )
    parent = next(
        event
        for event in base.ledger.events
        if event.source_occurrence_key == "fy2023-revenue-restated"
    )
    third = usd_fact(
        hop_c,
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        fy2023,
        "1070",
        source_span=(0, 4),
        source_occurrence_key="fy2023-revenue-amendment-c",
        event_type=FactEventType.AMENDMENT,
        revision_of=parent.occurrence_id,
        recorded_at="2026-08-04T18:00:00Z",
    )
    events = (*base.ledger.events, third)
    filings = {
        "23-000010": filing(
            accession="0000999999-23-000010",
            document_id="fip1-20221231.htm",
            accepted_at="2023-02-15T16:00:00Z",
            recorded_at="2023-02-15T16:05:00Z",
            filed_at="2023-02-15",
        ),
        "24-000010": filing(
            accession="0000999999-24-000010",
            document_id="fip1-20231231.htm",
            accepted_at="2024-02-15T16:00:00Z",
            recorded_at="2024-02-15T16:05:00Z",
            filed_at="2024-02-15",
        ),
        "25-000010": filing(
            accession="0000999999-25-000010",
            document_id="fip1-20241231.htm",
            accepted_at="2025-02-15T16:00:00Z",
            recorded_at="2025-02-15T16:05:00Z",
            filed_at="2025-02-15",
        ),
        "26-000010": hop_c,
    }
    return FilingPackageFixture(
        entity=base.entity,
        ledger=RawFactLedger(events),
        filing_metadata=_metadata_for(events, filings),
    )


def filing(
    *,
    accession: str,
    document_id: str,
    accepted_at: str,
    recorded_at: str,
    filed_at: str,
    entity_id: str = SYNTHETIC_ENTITY_ID,
) -> dict[str, Any]:
    compact = accession.replace("-", "")
    body = sha256(f"synthetic-filing-package:{accession}:{document_id}".encode("utf-8")).hexdigest()
    return {
        "accession": accession,
        "document_id": document_id,
        "accepted_at": accepted_at,
        "recorded_at": recorded_at,
        "filed_at": filed_at,
        "source": SourceIdentity(
            source="sec-edgar",
            entity_id=entity_id,
            accession=accession,
            document_id=document_id,
            body_sha256=body,
            source_url=(
                f"https://www.sec.gov/Archives/edgar/data/{int(entity_id)}/{compact}/{document_id}"
            ),
        ),
    }


def usd_fact(
    filing_row: Mapping[str, Any],
    concept_qname: str,
    context: FactContext,
    value: str,
    *,
    source_span: tuple[int, int],
    source_occurrence_key: str,
    event_type: FactEventType = FactEventType.FILED,
    revision_of: str | None = None,
    recorded_at: str | None = None,
    accepted_at: str | None = None,
) -> RawFactOccurrence:
    return make_raw_fact(
        source=filing_row["source"],
        concept_qname=concept_qname,
        context=context,
        unit=_USD,
        raw_token=value,
        parsed_value=value,
        dimensions_known=True,
        decimals="0",
        source_span=source_span,
        source_occurrence_key=source_occurrence_key,
        accepted_at=accepted_at or filing_row["accepted_at"],
        recorded_at=recorded_at or filing_row["recorded_at"],
        event_type=event_type,
        revision_of=revision_of,
    )


def _metadata_for(
    events: tuple[RawFactOccurrence, ...],
    filings: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for event in events:
        suffix = event.source.accession.split("-", 1)[-1] if "-" in event.source.accession else ""
        matched = None
        for key, row in filings.items():
            if event.source.accession.endswith(key) or key == suffix:
                matched = row
                break
        if matched is None:
            matched = next(
                row for row in filings.values() if row["accession"] == event.source.accession
            )
        metadata[event.occurrence_id] = {
            "accession": event.source.accession,
            "document_id": event.source.document_id,
            "source_body_sha256": event.source.body_sha256,
            "available_at": utc_text(event.clocks.recorded_at),
            "form": "10-K",
            "filed_at": matched["filed_at"],
        }
    return metadata
