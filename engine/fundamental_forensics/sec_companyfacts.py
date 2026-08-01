"""Pure SEC Company Facts + Submissions ingestion for the fixture kernel."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Mapping

from .models import (
    FactOccurrence,
    IngestBundle,
    SourceFiling,
    canonical_json,
    decimal_text,
    parse_utc,
    stable_id,
)


def _cik_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Company Facts payload is missing cik")
    try:
        return f"{int(text):010d}"
    except ValueError as exc:
        raise ValueError(f"invalid cik: {value!r}") from exc


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _submission_rows(submissions: Mapping[str, Any]) -> list[dict[str, Any]]:
    recent = ((submissions.get("filings") or {}).get("recent") or {})
    if not isinstance(recent, Mapping):
        raise ValueError("submissions.filings.recent must be an object of column arrays")
    accessions = recent.get("accessionNumber") or []
    if not isinstance(accessions, list):
        raise ValueError("submissions.filings.recent.accessionNumber must be an array")
    rows: list[dict[str, Any]] = []
    for idx, accession in enumerate(accessions):
        row: dict[str, Any] = {}
        for field, values in recent.items():
            row[field] = values[idx] if isinstance(values, list) and idx < len(values) else None
        row["accessionNumber"] = str(accession).strip() if accession is not None else None
        rows.append(row)
    return rows


def _filing_index(entity_cik: str, submissions: Mapping[str, Any]) -> dict[str, SourceFiling]:
    out: dict[str, SourceFiling] = {}
    for row in _submission_rows(submissions):
        accession = row.get("accessionNumber")
        if not accession:
            continue
        accepted_at = parse_utc(row.get("acceptanceDateTime"), field="acceptanceDateTime")
        filing = SourceFiling(
            filing_id=stable_id("filing", entity_cik, accession),
            entity_cik=entity_cik,
            accession=accession,
            form=str(row.get("form")) if row.get("form") else None,
            filing_date=str(row.get("filingDate")) if row.get("filingDate") else None,
            report_date=str(row.get("reportDate")) if row.get("reportDate") else None,
            source_event_at=accepted_at,
            primary_document=(
                str(row.get("primaryDocument")) if row.get("primaryDocument") else None
            ),
            is_xbrl=_optional_bool(row.get("isXBRL")),
            is_inline_xbrl=_optional_bool(row.get("isInlineXBRL")),
        )
        out[accession] = filing
    return out


def ingest_companyfacts(
    companyfacts: Mapping[str, Any],
    submissions: Mapping[str, Any],
    *,
    recorded_at: str | datetime,
) -> IngestBundle:
    """Ingest already-fetched SEC payloads without network or filesystem access.

    Company Facts lacks acceptance timestamps, so accessions are joined to the
    columnar SEC Submissions payload.  Missing joins remain visible but are
    explicitly ineligible for source-event replay.
    """
    recorded = parse_utc(recorded_at, field="recorded_at")
    if recorded is None:  # pragma: no cover - guarded by the required argument
        raise ValueError("recorded_at is required")
    entity_cik = _cik_text(companyfacts.get("cik"))
    entity_name = str(companyfacts.get("entityName") or "").strip()
    filing_by_accession = _filing_index(entity_cik, submissions)

    raw_counts: defaultdict[str, int] = defaultdict(int)
    raw_payloads: dict[str, dict[str, Any]] = {}
    taxonomies = companyfacts.get("facts") or {}
    if not isinstance(taxonomies, Mapping):
        raise ValueError("companyfacts.facts must be an object")

    for taxonomy in sorted(taxonomies):
        concepts = taxonomies[taxonomy] or {}
        if not isinstance(concepts, Mapping):
            continue
        for concept in sorted(concepts):
            units = (concepts[concept] or {}).get("units") or {}
            if not isinstance(units, Mapping):
                continue
            for unit in sorted(units):
                entries = units[unit] or []
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, Mapping) or not entry.get("end"):
                        continue
                    accession = str(entry.get("accn")).strip() if entry.get("accn") else None
                    payload = {
                        "entity_cik": entity_cik,
                        "entity_name": entity_name,
                        "taxonomy": str(taxonomy),
                        "concept": str(concept),
                        "unit": str(unit),
                        "value": decimal_text(entry.get("val")),
                        "period_start": str(entry.get("start")) if entry.get("start") else None,
                        "period_end": str(entry.get("end")),
                        "accession": accession,
                        "form": str(entry.get("form")) if entry.get("form") else None,
                        "filed": str(entry.get("filed")) if entry.get("filed") else None,
                        "reported_fy": _optional_int(entry.get("fy")),
                        "reported_fp": str(entry.get("fp")) if entry.get("fp") else None,
                        "frame": str(entry.get("frame")) if entry.get("frame") else None,
                    }
                    key = canonical_json(payload)
                    raw_counts[key] += 1
                    raw_payloads[key] = payload

    facts: list[FactOccurrence] = []
    used_accessions: set[str] = set()
    for key in sorted(raw_payloads):
        payload = raw_payloads[key]
        accession = payload["accession"]
        filing = filing_by_accession.get(accession) if accession else None
        if accession:
            used_accessions.add(accession)
        source_event_at = filing.source_event_at if filing else None
        fact_id = stable_id("fact", payload)
        facts.append(
            FactOccurrence(
                fact_id=fact_id,
                **payload,
                filing_id=filing.filing_id if filing else None,
                source_event_at=source_event_at,
                recorded_at=recorded,
                pit_eligible=source_event_at is not None,
                source_record_count=raw_counts[key],
            )
        )

    filings = [filing_by_accession[a] for a in used_accessions if a in filing_by_accession]
    filings.sort(key=lambda item: (item.source_event_at is None, item.source_event_at, item.accession))
    facts.sort(key=lambda item: item.fact_id)
    return IngestBundle(
        entity_cik=entity_cik,
        entity_name=entity_name,
        filings=tuple(filings),
        facts=tuple(facts),
    )
