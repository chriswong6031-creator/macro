"""Reconcile two completed SEC 13F bulk windows into bounded census projections.

The SEC bulk ZIP is a filing-month window, not a report-period snapshot.  The
compiler filters the requested period explicitly, retains amendments/notices in
coverage, and compares only paired original filers.  Raw ZIPs and the private
research bench remain outside Git; the only public artifact is the capped JSON
summary consumed by ``build_smart_money``.
"""
from __future__ import annotations

import argparse
import calendar
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.institutional_census.aggregate import (  # noqa: E402
    CensusAccumulator,
    compilation_json_bytes,
    load_ticker_map,
    write_compilation,
)
from engine.institutional_census.catalog import (  # noqa: E402
    HARD_MAX_CATALOG_POINTER_BYTES,
    PublishedCatalogGeneration,
    load_catalog_generation,
)
from engine.institutional_census.models import (  # noqa: E402
    COVERAGE_SCHEMA,
    canonical_json_bytes,
    catalog_pointer_key,
    decode_canonical_json,
    normalize_utc,
    utc_datetime,
)
from engine.institutional_census.sec_sources import (  # noqa: E402
    read_bulk_package,
    validate_bulk_invariants,
)
from engine.institutional_census.reconciliation import publish_bulk_revision  # noqa: E402
from engine.institutional_census.storage import build_institutional_13f_store  # noqa: E402
from engine.fund_intelligence import load_classifications  # noqa: E402
from lib import config  # noqa: E402

SEC_BULK_ROOT = "https://www.sec.gov/files/structureddata/data/form-13f-data-sets"
MAX_BULK_ZIP_BYTES = 256 * 1024 * 1024
PRODUCER_VERSION = "institutional-13f-census/1.1.0"
COMPILATION_INPUTS_SCHEMA = "institutional_13f.compilation_inputs/v1"
_DEDICATED_STORE_ENV = (
    "INSTITUTIONAL_13F_R2_ENDPOINT",
    "INSTITUTIONAL_13F_R2_ACCESS_KEY_ID",
    "INSTITUTIONAL_13F_R2_SECRET_ACCESS_KEY",
    "INSTITUTIONAL_13F_R2_BUCKET",
)


@dataclass(frozen=True)
class CatalogOverlay:
    tables: Any
    descriptor: dict[str, Any]
    excluded_accessions: frozenset[str]


@dataclass(frozen=True)
class AcquiredBulkSource:
    path: Path
    sha256: str
    byte_length: int
    acquisition_mode: str
    final_url: str | None
    operator_source: str | None

    @property
    def official_sec_https(self) -> bool:
        return bool(self.final_url and _is_sec_https(self.final_url))


def _quarter_end_before(value: date) -> date:
    ends = [date(value.year, month, calendar.monthrange(value.year, month)[1]) for month in (3, 6, 9, 12)]
    earlier = [item for item in ends if item < value]
    if earlier:
        return earlier[-1]
    return date(value.year - 1, 12, 31)


def _previous_quarter(period: date) -> date:
    return _quarter_end_before(period)


def _deadline(period: date) -> date:
    """45th day after quarter end, advanced across weekends/federal holidays."""
    due = period + timedelta(days=45)
    try:
        import pandas as pd
        from pandas.tseries.holiday import USFederalHolidayCalendar

        holidays = set(USFederalHolidayCalendar().holidays(start=due, end=due + timedelta(days=7)).date)
    except Exception:  # pragma: no cover - pandas is pinned in production.
        holidays = set()
    while due.weekday() >= 5 or due in holidays:
        due += timedelta(days=1)
    return due


def latest_completed_period(today: date) -> date:
    candidate = _quarter_end_before(today + timedelta(days=1))
    while _deadline(candidate) >= today:
        candidate = _previous_quarter(candidate)
    return candidate


def bulk_window(period: date) -> tuple[date, date]:
    start = period.replace(day=1)
    month_index = start.year * 12 + (start.month - 1) + 2
    end_year, end_month_zero = divmod(month_index, 12)
    end_month = end_month_zero + 1
    end = date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])
    return start, end


def bulk_url(period: date) -> str:
    start, end = bulk_window(period)
    filename = f"{start:%d%b%Y}-{end:%d%b%Y}_form13f.zip".lower()
    return f"{SEC_BULK_ROOT}/{filename}"


def _user_agent() -> str:
    explicit = os.environ.get("SEC_USER_AGENT", "").strip()
    if explicit:
        return explicit
    try:
        from collectors.edgar import _cfg

        configured = str(_cfg().get("user_agent") or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    return "MastermindX institutional census research longr2512@gmail.com"


def _is_sec_https(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme.lower() == "https" and (
        host == "sec.gov" or host.endswith(".sec.gov")
    )


def _copy_or_download(
    source: str,
    destination: Path,
    *,
    fetch: Any = requests.get,
) -> AcquiredBulkSource:
    parsed = urlparse(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    temporary = destination.with_name(destination.name + ".part")
    if parsed.scheme in {"http", "https"}:
        with fetch(
            source,
            headers={"User-Agent": _user_agent(), "Accept-Encoding": "gzip, deflate"},
            stream=True,
            timeout=(20, 180),
        ) as response:
            response.raise_for_status()
            final_url = str(getattr(response, "url", source) or source)
            if _is_sec_https(source) and not _is_sec_https(final_url):
                raise RuntimeError(
                    f"SEC bulk redirect escaped sec.gov: {source} -> {final_url}"
                )
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if "html" in content_type:
                raise RuntimeError(f"SEC bulk endpoint returned HTML: {source}")
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > MAX_BULK_ZIP_BYTES:
                        raise RuntimeError("SEC bulk package exceeds configured byte ceiling")
                    digest.update(chunk)
                    handle.write(chunk)
        acquisition_mode = (
            "sec_https" if _is_sec_https(final_url)
            else "operator_https" if urlparse(final_url).scheme.lower() == "https"
            else "operator_http"
        )
        operator_source = None if acquisition_mode == "sec_https" else final_url
    else:
        local = Path(source).expanduser().resolve()
        if not local.is_file():
            raise FileNotFoundError(local)
        with local.open("rb") as incoming, temporary.open("wb") as outgoing:
            while chunk := incoming.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BULK_ZIP_BYTES:
                    raise RuntimeError("SEC bulk package exceeds configured byte ceiling")
                digest.update(chunk)
                outgoing.write(chunk)
        final_url = None
        acquisition_mode = "operator_file"
        # Never disclose an absolute workstation path in public projection data.
        operator_source = local.name
    with temporary.open("rb") as handle:
        signature = handle.read(4)
    if size < 4 or signature != b"PK\x03\x04":
        raise RuntimeError(f"source is not a ZIP package: {source}")
    temporary.replace(destination)
    return AcquiredBulkSource(
        path=destination,
        sha256=digest.hexdigest(),
        byte_length=size,
        acquisition_mode=acquisition_mode,
        final_url=final_url,
        operator_source=operator_source,
    )


def _source_descriptor(
    *,
    acquired: AcquiredBulkSource,
    official_reference_url: str,
    filing_window_cutoff_at: str,
    expected_sha256: str | None,
    quality_findings: Counter | None = None,
) -> dict:
    attested = expected_sha256 is not None
    descriptor = {
        "kind": "sec_form13f_bulk_filing_window",
        "url": acquired.final_url or "operator-supplied-file",
        "official_reference_url": official_reference_url,
        "filing_window_cutoff_at": _iso_cutoff(filing_window_cutoff_at),
        "acquisition_mode": acquired.acquisition_mode,
        "official_source_status": (
            "sec_https" if acquired.official_sec_https
            else "expected_sha256_attested" if attested
            else "operator_supplied_unattested"
        ),
        "expected_sha256_attested": attested,
        "sha256": acquired.sha256,
        "byte_length": acquired.byte_length,
        "quality_findings": {},
    }
    if quality_findings:
        descriptor["quality_findings"] = {
            key: count for key, count in sorted(quality_findings.items()) if count
        }
    return descriptor


def _validate_expected_sha256(
    acquired: AcquiredBulkSource,
    expected_sha256: str | None,
    *,
    label: str,
    publication_required: bool,
) -> str | None:
    expected = str(expected_sha256 or "").strip().lower() or None
    if expected is not None and not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError(f"{label} expected SHA-256 is invalid")
    if expected is not None and expected != acquired.sha256:
        raise RuntimeError(f"{label} source does not match expected SHA-256")
    if publication_required and not acquired.official_sec_https and expected is None:
        raise RuntimeError(
            f"{label} bulk evidence publication requires final HTTPS sec.gov acquisition "
            "or an explicit expected SHA-256 attestation"
        )
    return expected


def _assert_package(tables, *, expected_sha: str, expected_bytes: int, label: str):
    if tables.source_sha256 != expected_sha or int(tables.source_bytes) != expected_bytes:
        raise RuntimeError(f"{label} parser source identity does not match acquired bytes")
    findings = validate_bulk_invariants(tables)
    errors = [item for item in findings if item.severity == "error"]
    if errors:
        first = errors[0]
        raise RuntimeError(f"{label} invariant {first.code}: {first.detail}")
    return findings


def _confidential_accessions(tables) -> set[str]:
    import pandas as pd

    frame = tables.summary_pages
    if frame.empty or "is_confidential_omitted" not in frame.columns:
        return set()
    out: set[str] = set()
    for accession, omitted in frame[["accession", "is_confidential_omitted"]].itertuples(index=False, name=None):
        if omitted is not None and not pd.isna(omitted) and bool(omitted):
            out.add(str(accession))
    return out


def _iso_cutoff(value: str | datetime) -> str:
    return normalize_utc(value, field="source_cutoff_at")


def _bulk_source_cutoff(period: date) -> str:
    _start, end = bulk_window(period)
    try:
        import pandas as pd
        from pandas.tseries.holiday import USFederalHolidayCalendar

        holidays = set(
            USFederalHolidayCalendar().holidays(
                start=end - timedelta(days=14), end=end
            ).date
        )
    except Exception:  # pragma: no cover - pandas is pinned in production.
        holidays = set()
    final_business_day = end
    while final_business_day.weekday() >= 5 or final_business_day in holidays:
        final_business_day -= timedelta(days=1)
    cutoff_et = datetime(
        final_business_day.year,
        final_business_day.month,
        final_business_day.day,
        17,
        30,
        tzinfo=ZoneInfo("America/New_York"),
    )
    return cutoff_et.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _manifest_sha256(generation: PublishedCatalogGeneration) -> str:
    return hashlib.sha256(generation.manifest.to_json_bytes()).hexdigest()


def _optional_catalog_generation(store: Any, period: date) -> PublishedCatalogGeneration | None:
    key = catalog_pointer_key(period.isoformat())
    try:
        pointer = store.get_bytes_strict_bounded(key, HARD_MAX_CATALOG_POINTER_BYTES)
    except Exception as exc:  # noqa: BLE001 - an outage is never object absence.
        raise RuntimeError(f"catalog pointer read failed for {period.isoformat()}") from exc
    if pointer is None:
        return None
    if type(pointer) is not bytes or len(pointer) > HARD_MAX_CATALOG_POINTER_BYTES:
        raise RuntimeError(f"catalog pointer read is invalid for {period.isoformat()}")
    # The loader re-reads the current pointer and verifies the manifest plus every
    # content-addressed artifact.  A race therefore resolves to one complete,
    # self-consistent generation rather than the untrusted probe above.
    return load_catalog_generation(store, report_period=period.isoformat())


def _store_is_configured(*, local_store: str | None) -> bool:
    if local_store:
        return True
    configured = [bool(os.environ.get(name)) for name in _DEDICATED_STORE_ENV]
    if any(configured) and not all(configured):
        # Let the strict factory name the exact missing variables.
        return True
    return all(configured)


def _catalog_reference(
    generation: PublishedCatalogGeneration | None,
    *,
    state: str,
) -> dict[str, Any]:
    if generation is None:
        return {
            "state": state,
            "generation_id": None,
            "manifest_sha256": None,
            "catalog_source_cutoff_at": None,
        }
    return {
        "state": "applied",
        "generation_id": generation.generation_id,
        "manifest_sha256": _manifest_sha256(generation),
        "catalog_source_cutoff_at": str(generation.manifest.clocks.source_cutoff_at),
    }


def _catalog_has_complete_discovery_coverage(
    generation: PublishedCatalogGeneration,
) -> bool:
    """Return true only for an explicitly attested continuous index backfill.

    A catalog's source-cutoff clock says how new its retained observations are;
    it does not prove that every intervening EDGAR index was covered.  Rolling
    generations therefore remain useful overlays while this completeness claim
    stays false.  A future historical backfill may set the explicit marker only
    after its index-coverage ledger has no backlog or failures.
    """

    payloads = getattr(generation, "payloads", {})
    payload = (
        payloads.get("coverage_json") if isinstance(payloads, Mapping) else None
    )
    if type(payload) is not bytes:
        return False
    try:
        coverage = decode_canonical_json(payload, label="catalog coverage")
    except Exception:
        return False
    return bool(
        coverage.get("schema") == COVERAGE_SCHEMA
        and coverage.get("report_period")
        == str(generation.manifest.clocks.report_period)
        and coverage.get("historical_index_coverage_complete") is True
        and coverage.get("run_failure_count") == 0
        and coverage.get("backlog_accessions") == 0
    )


def _value(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name not in row:
            continue
        value = row[name]
        if value is None:
            continue
        try:
            if value != value:
                continue
        except (TypeError, ValueError):
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "nat", "<na>", "none"}:
            return value
    return None


def _token(value: Any, *, upper: bool = False) -> str:
    value = _value({"value": value}, "value")
    if value is None:
        return ""
    text = " ".join(str(value).strip().split())
    return text.upper() if upper else text


def _numeric_token(value: Any) -> str:
    value = _value({"value": value}, "value")
    if value is None:
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return _token(value)
    if not number.is_finite():
        return ""
    return format(number.normalize(), "f")


def _holding_identity(row: Mapping[str, Any], *, catalog: bool) -> tuple[str, ...]:
    if catalog:
        return (
            _token(_value(row, "cusip"), upper=True),
            _token(_value(row, "figi"), upper=True),
            _token(_value(row, "name_of_issuer")),
            _token(_value(row, "title_of_class")),
            _numeric_token(_value(row, "value_reported")),
            _numeric_token(_value(row, "ssh_prn_amt")),
            _token(_value(row, "ssh_prn_type"), upper=True),
            _token(_value(row, "put_call"), upper=True),
            _token(_value(row, "investment_discretion"), upper=True),
            _token(_value(row, "other_manager")),
            _numeric_token(_value(row, "voting_authority_sole")),
            _numeric_token(_value(row, "voting_authority_shared")),
            _numeric_token(_value(row, "voting_authority_none")),
        )
    return (
        _token(_value(row, "cusip"), upper=True),
        _token(_value(row, "figi"), upper=True),
        _token(_value(row, "issuer_name", "name_of_issuer")),
        _token(_value(row, "title_of_class")),
        _numeric_token(_value(row, "value", "value_reported")),
        _numeric_token(_value(row, "shares_or_principal_amount", "ssh_prn_amt")),
        _token(_value(row, "shares_or_principal_amount_type", "ssh_prn_type"), upper=True),
        _token(_value(row, "put_call"), upper=True),
        _token(_value(row, "investment_discretion"), upper=True),
        _token(_value(row, "other_manager")),
        _numeric_token(_value(row, "voting_authority_sole")),
        _numeric_token(_value(row, "voting_authority_shared")),
        _numeric_token(_value(row, "voting_authority_none")),
    )


def _catalog_overlay(
    bulk_tables: Any,
    generation: PublishedCatalogGeneration | None,
    *,
    period_end: str,
    source_cutoff_at: str,
    unavailable_state: str = "unavailable",
) -> CatalogOverlay:
    """Adapt verified catalog-only rows without copying the bulk holding table."""
    import pandas as pd

    cutoff = _iso_cutoff(source_cutoff_at)
    empty = SimpleNamespace(
        submissions=pd.DataFrame(),
        cover_pages=pd.DataFrame(),
        summary_pages=pd.DataFrame(),
        holdings=pd.DataFrame(),
    )
    if generation is None:
        descriptor = {
            **_catalog_reference(None, state=unavailable_state),
            "requested_source_cutoff_at": cutoff,
            "catalog_filings_through_cutoff": 0,
            "catalog_only_filings": 0,
            "bulk_duplicate_filings_verified": 0,
            "latest_known": False,
        }
        return CatalogOverlay(empty, descriptor, frozenset())

    if str(generation.manifest.clocks.report_period) != period_end:
        raise RuntimeError("catalog generation belongs to another report period")
    eligible_filings = [
        dict(row) for row in generation.filings
        if str(row.get("report_period") or "") == period_end
        and utc_datetime(str(row.get("accepted_at") or ""), field="catalog accepted_at")
        <= utc_datetime(cutoff, field="source_cutoff_at")
    ]
    catalog_by_accession = {str(row["accession"]): row for row in eligible_filings}
    if len(catalog_by_accession) != len(eligible_filings):
        raise RuntimeError("catalog contains duplicate filing accessions")

    bulk_rows = bulk_tables.submissions.to_dict(orient="records")
    bulk_by_accession = {
        str(row.get("accession") or row.get("accession_number") or ""): row
        for row in bulk_rows
    }
    bulk_covers = {
        str(row.get("accession") or row.get("accession_number") or ""): row
        for row in bulk_tables.cover_pages.to_dict(orient="records")
    }
    bulk_summaries = {
        str(row.get("accession") or row.get("accession_number") or ""): row
        for row in bulk_tables.summary_pages.to_dict(orient="records")
    }
    duplicates = set(catalog_by_accession) & set(bulk_by_accession)
    for accession in sorted(duplicates):
        catalog_row = catalog_by_accession[accession]
        bulk_row = bulk_by_accession[accession]
        comparisons = (
            (_token(_value(catalog_row, "filer_cik")).zfill(10), _token(_value(bulk_row, "cik")).zfill(10)),
            (_token(_value(catalog_row, "form"), upper=True), _token(_value(bulk_row, "form"), upper=True)),
            (_token(_value(catalog_row, "report_period")), _token(_value(bulk_row, "period_end"))),
            (_token(_value(catalog_row, "filing_date")), _token(_value(bulk_row, "filing_date"))),
        )
        if any(left != right for left, right in comparisons):
            raise RuntimeError(f"catalog/bulk filing identity conflict for {accession}")
        bulk_cover = bulk_covers.get(accession, {})
        cover_comparisons = (
            (
                _token(_value(catalog_row, "form13f_file_number"), upper=True),
                _token(_value(bulk_cover, "form_13f_file_number"), upper=True),
            ),
            (
                _token(_value(catalog_row, "amendment_type"), upper=True),
                _token(_value(bulk_cover, "amendment_type"), upper=True),
            ),
        )
        if any(left != right for left, right in cover_comparisons):
            raise RuntimeError(f"catalog/bulk cover-page conflict for {accession}")
        bulk_summary = bulk_summaries.get(accession, {})
        catalog_total = _numeric_token(_value(catalog_row, "table_entry_total"))
        bulk_total = _numeric_token(_value(bulk_summary, "table_entry_total"))
        if catalog_total != bulk_total:
            raise RuntimeError(f"catalog/bulk summary-page conflict for {accession}")

    if duplicates:
        catalog_duplicate_holdings: dict[str, Counter] = {
            accession: Counter() for accession in duplicates
        }
        for raw in generation.holdings:
            accession = str(raw.get("accession") or "")
            if accession in catalog_duplicate_holdings:
                catalog_duplicate_holdings[accession][_holding_identity(raw, catalog=True)] += 1
        bulk_duplicate_holdings: dict[str, Counter] = {
            accession: Counter() for accession in duplicates
        }
        duplicate_frame = bulk_tables.holdings[
            bulk_tables.holdings["accession"].astype(str).isin(duplicates)
        ]
        for raw in duplicate_frame.to_dict(orient="records"):
            accession = str(raw.get("accession") or "")
            bulk_duplicate_holdings[accession][_holding_identity(raw, catalog=False)] += 1
        for accession in sorted(duplicates):
            if catalog_duplicate_holdings[accession] != bulk_duplicate_holdings[accession]:
                raise RuntimeError(f"catalog/bulk holding conflict for {accession}")

    catalog_only = [
        row for accession, row in sorted(catalog_by_accession.items())
        if accession not in duplicates
    ]
    catalog_only_accessions = {str(row["accession"]) for row in catalog_only}
    holdings = [
        {
            "accession": str(raw["accession"]),
            "cusip": raw.get("cusip"),
            "figi": raw.get("figi"),
            "issuer_name": raw.get("name_of_issuer"),
            "title_of_class": raw.get("title_of_class"),
            "value": raw.get("value_reported"),
            "shares_or_principal_amount": raw.get("ssh_prn_amt"),
            "shares_or_principal_amount_type": raw.get("ssh_prn_type"),
            "put_call": raw.get("put_call"),
            "investment_discretion": raw.get("investment_discretion"),
            "other_manager": raw.get("other_manager"),
            "voting_authority_sole": raw.get("voting_authority_sole"),
            "voting_authority_shared": raw.get("voting_authority_shared"),
            "voting_authority_none": raw.get("voting_authority_none"),
        }
        for raw in generation.holdings
        if str(raw.get("accession") or "") in catalog_only_accessions
    ]
    holding_count = Counter(str(row["accession"]) for row in holdings)
    excluded: set[str] = set()
    for filing in catalog_only:
        accession = str(filing["accession"])
        if bool(filing.get("confidential_omitted")):
            excluded.add(accession)
        expected = filing.get("table_entry_total")
        if expected is not None and int(expected) != holding_count[accession]:
            excluded.add(accession)

    submissions = [{
        "accession": str(row["accession"]),
        "filing_date": row.get("filing_date"),
        "form": row.get("form"),
        "cik": row.get("filer_cik"),
        "period_end": row.get("report_period"),
        "accepted_at": row.get("accepted_at"),
    } for row in catalog_only]
    covers = [{
        "accession": str(row["accession"]),
        "filing_manager_name": row.get("filer_name"),
        "form_13f_file_number": row.get("form13f_file_number"),
        "is_amendment": row.get("is_amendment"),
        "amendment_number": row.get("amendment_number"),
        "amendment_type": row.get("amendment_type"),
        "report_type": row.get("report_type"),
    } for row in catalog_only]
    summaries = [{
        "accession": str(row["accession"]),
        "is_confidential_omitted": row.get("confidential_omitted"),
        "table_entry_total": row.get("table_entry_total"),
        "other_included_managers_count": row.get("other_manager_count"),
    } for row in catalog_only]
    tables = SimpleNamespace(
        submissions=pd.DataFrame(submissions),
        cover_pages=pd.DataFrame(covers),
        summary_pages=pd.DataFrame(summaries),
        holdings=pd.DataFrame(holdings),
    )
    catalog_cutoff = str(generation.manifest.clocks.source_cutoff_at)
    descriptor = {
        **_catalog_reference(generation, state="applied"),
        "requested_source_cutoff_at": cutoff,
        "catalog_filings_through_cutoff": len(eligible_filings),
        "catalog_only_filings": len(catalog_only),
        "bulk_duplicate_filings_verified": len(duplicates),
        "latest_known": bool(
            _catalog_has_complete_discovery_coverage(generation)
            and utc_datetime(catalog_cutoff, field="catalog source_cutoff_at")
            >= utc_datetime(cutoff, field="source_cutoff_at")
        ),
    }
    return CatalogOverlay(tables, descriptor, frozenset(excluded))


def _matching_existing_receipt(
    *,
    public_path: str | Path,
    research_bench_path: str | Path,
    receipt_path: str | Path,
    current_period: str,
    baseline_period: str,
    compilation_id: str,
    research_store: Any | None = None,
) -> dict | None:
    try:
        public_bytes = Path(public_path).read_bytes()
        receipt_bytes = Path(receipt_path).read_bytes()
        try:
            bench_bytes = Path(research_bench_path).read_bytes()
        except FileNotFoundError:
            if research_store is None:
                raise
            from engine.institutional_census.research_bench import (
                load_private_research_bench,
            )

            bench_bytes = load_private_research_bench(research_store).payload
        public = json.loads(public_bytes)
        bench = json.loads(bench_bytes)
        receipt = json.loads(receipt_bytes)
        if (
            compilation_json_bytes(public) == public_bytes
            and compilation_json_bytes(bench) == bench_bytes
            and compilation_json_bytes(receipt) == receipt_bytes
            and public.get("schema") == "institutional_13f.census_public/v1"
            and public.get("periods") == {"current": current_period, "baseline": baseline_period}
            and bench.get("schema") == "institutional_13f.research_bench/v1"
            and bench.get("as_of_period") == current_period
            and receipt.get("current_period") == current_period
            and receipt.get("baseline_period") == baseline_period
            and receipt.get("compilation_id") == compilation_id
            and hashlib.sha256(
                compilation_json_bytes(receipt["compilation_inputs"])
            ).hexdigest() == compilation_id
            and receipt.get("public_sha256") == hashlib.sha256(public_bytes).hexdigest()
            and receipt.get("public_bytes") == len(public_bytes)
            and receipt.get("research_bench_sha256") == hashlib.sha256(bench_bytes).hexdigest()
            and receipt.get("research_bench_bytes") == len(bench_bytes)
        ):
            return receipt
    except (
        FileNotFoundError, KeyError, TypeError, ValueError,
        RuntimeError, UnicodeDecodeError, json.JSONDecodeError,
    ):
        return None
    return None


def _institutional_config() -> tuple[dict[str, Any], Path, str]:
    import yaml

    path = Path(config.ROOT) / "config" / "institutional_13f.yml"
    payload = path.read_bytes()
    value = yaml.safe_load(payload)
    if not isinstance(value, dict) or value.get("schema") != "institutional_13f.config/v1":
        raise RuntimeError("institutional 13F config is missing or invalid")
    return value, path, hashlib.sha256(payload).hexdigest()


def _compiler_code_sha256() -> str:
    aggregate_path = Path(sys.modules[CensusAccumulator.__module__].__file__).resolve()
    components = {
        aggregate_path.name: hashlib.sha256(aggregate_path.read_bytes()).hexdigest(),
        Path(__file__).name: hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    return hashlib.sha256(canonical_json_bytes(components)).hexdigest()


def _private_bench_matches_receipt(store: Any, receipt: Mapping[str, Any]) -> bool:
    from engine.institutional_census.research_bench import load_private_research_bench

    try:
        published = load_private_research_bench(store)
        expected = receipt["private_research_bench"]
        return bool(
            published.pointer.current_period == receipt.get("current_period")
            and published.pointer.baseline_period == receipt.get("baseline_period")
            and published.pointer.bench_sha256 == receipt.get("research_bench_sha256")
            and published.pointer.bench_byte_length == receipt.get("research_bench_bytes")
            and expected.get("sha256") == published.pointer.bench_sha256
            and expected.get("byte_length") == published.pointer.bench_byte_length
            and expected.get("source_cutoff_at") == published.pointer.source_cutoff_at
        )
    except (KeyError, TypeError, ValueError, RuntimeError):
        return False


def build(args: argparse.Namespace) -> dict:
    current_period = date.fromisoformat(args.current_period)
    baseline_period = date.fromisoformat(args.baseline_period)
    if _previous_quarter(current_period) != baseline_period:
        raise ValueError("baseline-period must be the quarter immediately before current-period")
    settings, _config_path, config_sha = _institutional_config()
    public_settings = settings["public_summary"]
    minimum_mapping_coverage_pct = float(getattr(
        args,
        "minimum_mapping_coverage_pct",
        public_settings["minimum_mapping_coverage_pct"],
    ))
    overlay_mode = str(getattr(args, "catalog_overlay_mode", "auto"))
    if overlay_mode not in {"auto", "required", "disabled"}:
        raise ValueError("catalog-overlay-mode must be auto, required, or disabled")
    publish_bulk_evidence = bool(getattr(args, "publish_bulk_evidence", False))
    if publish_bulk_evidence and overlay_mode == "disabled":
        raise ValueError("catalog overlay cannot be disabled when the evidence store is in use")

    ticker_map_path = Path(args.ticker_map).expanduser().resolve()
    if not ticker_map_path.is_file():
        raise FileNotFoundError(f"required ticker map is missing: {ticker_map_path}")
    ticker_map_sha = hashlib.sha256(ticker_map_path.read_bytes()).hexdigest()
    ticker_map = load_ticker_map(ticker_map_path)
    if not ticker_map:
        raise RuntimeError("required ticker map contains no eligible US equity resolutions")
    classification_payload = load_classifications()
    if not isinstance(classification_payload, Mapping):
        raise RuntimeError("sector classification map is invalid")
    classification_sha = hashlib.sha256(
        canonical_json_bytes(dict(classification_payload))
    ).hexdigest()
    classifications = {
        key: value for key, value in classification_payload.items() if key != "_meta"
    }

    current_source = args.current_source or bulk_url(current_period)
    baseline_source = args.baseline_source or bulk_url(baseline_period)

    cache_root = Path(args.cache_dir).expanduser().resolve()
    current_acquired = _copy_or_download(
        current_source, cache_root / f"{current_period.isoformat()}.zip"
    )
    baseline_acquired = _copy_or_download(
        baseline_source, cache_root / f"{baseline_period.isoformat()}.zip"
    )
    current_path = current_acquired.path
    baseline_path = baseline_acquired.path
    current_sha = current_acquired.sha256
    baseline_sha = baseline_acquired.sha256
    current_bytes = current_acquired.byte_length
    baseline_bytes = baseline_acquired.byte_length
    current_official_reference = bulk_url(current_period)
    baseline_official_reference = bulk_url(baseline_period)
    current_bulk_cutoff = _bulk_source_cutoff(current_period)
    baseline_bulk_cutoff = _bulk_source_cutoff(baseline_period)
    current_expected_sha = _validate_expected_sha256(
        current_acquired,
        getattr(args, "current_expected_sha256", None),
        label="current",
        publication_required=publish_bulk_evidence,
    )
    baseline_expected_sha = _validate_expected_sha256(
        baseline_acquired,
        getattr(args, "baseline_expected_sha256", None),
        label="baseline",
        publication_required=publish_bulk_evidence,
    )

    store = None
    store_configured = _store_is_configured(local_store=getattr(args, "local_store", None))
    if publish_bulk_evidence or (overlay_mode != "disabled" and store_configured):
        store = build_institutional_13f_store(local_dir=getattr(args, "local_store", None))
    elif overlay_mode == "required":
        raise RuntimeError("catalog overlay is required but no institutional evidence store is configured")

    current_catalog = None
    baseline_catalog = None
    catalog_absence_state = "disabled" if overlay_mode == "disabled" else "unavailable"
    if store is not None and overlay_mode != "disabled":
        current_catalog = _optional_catalog_generation(store, current_period)
        baseline_catalog = _optional_catalog_generation(store, baseline_period)
        if overlay_mode == "required" and (current_catalog is None or baseline_catalog is None):
            raise RuntimeError("catalog overlay is required but a period pointer is unavailable")

    evidence_cutoffs = [
        current_bulk_cutoff,
        baseline_bulk_cutoff,
    ]
    for generation in (current_catalog, baseline_catalog):
        if generation is not None:
            evidence_cutoffs.append(str(generation.manifest.clocks.source_cutoff_at))
    evidence_cutoff = max(
        evidence_cutoffs,
        key=lambda value: utc_datetime(value, field="evidence source cutoff"),
    )
    explicit_cutoff = getattr(args, "source_cutoff_at", None)
    explicit_generated = getattr(args, "generated_at", None)
    source_cutoff_at = _iso_cutoff(explicit_cutoff or explicit_generated or evidence_cutoff)
    generated_at = _iso_cutoff(explicit_generated or source_cutoff_at)
    if generated_at != source_cutoff_at:
        raise ValueError("generated-at must equal source-cutoff-at for deterministic compilation")
    publication_clock = normalize_utc(
        datetime.now(timezone.utc), field="publication clock"
    )

    current_catalog_reference = _catalog_reference(
        current_catalog, state=catalog_absence_state
    )
    baseline_catalog_reference = _catalog_reference(
        baseline_catalog, state=catalog_absence_state
    )
    compiler_parameters = {
        "action_threshold_pct": float(args.action_threshold_pct),
        "max_rows": int(args.max_rows),
        "minimum_mapping_coverage_pct": minimum_mapping_coverage_pct,
        "research_minimum_quarters": int(args.research_minimum_quarters),
        "research_maximum_candidates": int(args.research_maximum_candidates),
    }
    compilation_inputs = {
        "schema": COMPILATION_INPUTS_SCHEMA,
        "producer_version": PRODUCER_VERSION,
        "compiler_code_sha256": _compiler_code_sha256(),
        "config_sha256": config_sha,
        "periods": {
            "current": current_period.isoformat(),
            "baseline": baseline_period.isoformat(),
        },
        "bulk_sources": {
            "current": {
                "url": current_acquired.final_url or "operator-supplied-file",
                "official_reference_url": current_official_reference,
                "filing_window_cutoff_at": current_bulk_cutoff,
                "acquisition_mode": current_acquired.acquisition_mode,
                "expected_sha256": current_expected_sha,
                "sha256": current_sha,
                "byte_length": current_bytes,
            },
            "baseline": {
                "url": baseline_acquired.final_url or "operator-supplied-file",
                "official_reference_url": baseline_official_reference,
                "filing_window_cutoff_at": baseline_bulk_cutoff,
                "acquisition_mode": baseline_acquired.acquisition_mode,
                "expected_sha256": baseline_expected_sha,
                "sha256": baseline_sha,
                "byte_length": baseline_bytes,
            },
        },
        "catalog_overlays": {
            "mode": overlay_mode,
            "source_cutoff_at": source_cutoff_at,
            "current": current_catalog_reference,
            "baseline": baseline_catalog_reference,
        },
        "identifier_map": {
            "sha256": ticker_map_sha,
            "resolved_cusips": len(ticker_map),
        },
        "classification_map": {"sha256": classification_sha},
        "parameters": compiler_parameters,
    }
    if explicit_generated is not None:
        compilation_inputs["explicit_generated_at"] = generated_at
    compilation_id = hashlib.sha256(
        canonical_json_bytes(compilation_inputs)
    ).hexdigest()

    bulk_revision_ids: list[str] = []
    if publish_bulk_evidence:
        assert store is not None
        for path, period, source_url in (
            (
                current_path,
                current_period,
                current_acquired.final_url or current_official_reference,
            ),
            (
                baseline_path,
                baseline_period,
                baseline_acquired.final_url or baseline_official_reference,
            ),
        ):
            window_start, window_end = bulk_window(period)
            revision = publish_bulk_revision(
                store,
                window_start=window_start.isoformat(),
                window_end=window_end.isoformat(),
                source_url=source_url,
                payload=path.read_bytes(),
                retained_at=publication_clock,
                producer_version=PRODUCER_VERSION,
            )
            bulk_revision_ids.append(revision.revision_id)

    research_store = None
    if bool(getattr(args, "publish_research_bench", False)):
        from engine.institutional_census.research_bench import (
            build_institutional_13f_research_store,
        )

        research_store = build_institutional_13f_research_store(
            local_dir=getattr(args, "local_research_store", None)
        )
    if not args.force:
        existing = _matching_existing_receipt(
            public_path=args.public_output,
            research_bench_path=args.research_bench_output,
            receipt_path=args.receipt_output,
            current_period=current_period.isoformat(),
            baseline_period=baseline_period.isoformat(),
            compilation_id=compilation_id,
            research_store=research_store,
        )
        bulk_receipts_match = bool(
            not bulk_revision_ids
            or sorted(existing.get("bulk_revision_ids", []))
            == sorted(bulk_revision_ids)
        ) if existing is not None else False
        if (
            existing is not None
            and bulk_receipts_match
            and (
                research_store is None
                or _private_bench_matches_receipt(research_store, existing)
            )
        ):
            return existing
    database = Path(args.database).expanduser().resolve() if args.database else None
    if database is not None and database.exists():
        raise FileExistsError(f"refusing to overwrite existing compiler database: {database}")

    with CensusAccumulator(database) as census:
        current = read_bulk_package(current_path)
        current_findings = _assert_package(
            current, expected_sha=current_sha, expected_bytes=current_bytes, label="current"
        )
        current_confidential = _confidential_accessions(current)
        current_excluded = {
            item.accession for item in current_findings
            if item.code == "table_entry_total_mismatch" and item.accession
        } | current_confidential
        current_quality_counts = Counter(item.code for item in current_findings)
        current_quality_counts["confidential_omitted"] += len(current_confidential)
        current_overlay = _catalog_overlay(
            current,
            current_catalog,
            period_end=current_period.isoformat(),
            source_cutoff_at=source_cutoff_at,
            unavailable_state=catalog_absence_state,
        )
        current_excluded |= set(current_overlay.excluded_accessions)
        current_quality_counts["rolling_overlay_excluded"] += len(
            current_overlay.excluded_accessions
        )
        current_quality_counts["rolling_overlay_catalog_only"] += int(
            current_overlay.descriptor["catalog_only_filings"]
        )
        census.ingest(
            "current", current, period_end=current_period.isoformat(),
            excluded_accessions=current_excluded,
            supplemental_tables=(current_overlay.tables,),
        )
        del current

        baseline = read_bulk_package(baseline_path)
        baseline_findings = _assert_package(
            baseline, expected_sha=baseline_sha, expected_bytes=baseline_bytes, label="baseline"
        )
        baseline_confidential = _confidential_accessions(baseline)
        baseline_excluded = {
            item.accession for item in baseline_findings
            if item.code == "table_entry_total_mismatch" and item.accession
        } | baseline_confidential
        baseline_quality_counts = Counter(item.code for item in baseline_findings)
        baseline_quality_counts["confidential_omitted"] += len(baseline_confidential)
        baseline_overlay = _catalog_overlay(
            baseline,
            baseline_catalog,
            period_end=baseline_period.isoformat(),
            source_cutoff_at=source_cutoff_at,
            unavailable_state=catalog_absence_state,
        )
        baseline_excluded |= set(baseline_overlay.excluded_accessions)
        baseline_quality_counts["rolling_overlay_excluded"] += len(
            baseline_overlay.excluded_accessions
        )
        baseline_quality_counts["rolling_overlay_catalog_only"] += int(
            baseline_overlay.descriptor["catalog_only_filings"]
        )
        census.ingest(
            "baseline", baseline, period_end=baseline_period.isoformat(),
            excluded_accessions=baseline_excluded,
            supplemental_tables=(baseline_overlay.tables,),
        )
        del baseline

        current_descriptor = _source_descriptor(
            acquired=current_acquired,
            official_reference_url=current_official_reference,
            filing_window_cutoff_at=current_bulk_cutoff,
            expected_sha256=current_expected_sha,
            quality_findings=current_quality_counts,
        )
        current_descriptor["rolling_overlay"] = current_overlay.descriptor
        baseline_descriptor = _source_descriptor(
            acquired=baseline_acquired,
            official_reference_url=baseline_official_reference,
            filing_window_cutoff_at=baseline_bulk_cutoff,
            expected_sha256=baseline_expected_sha,
            quality_findings=baseline_quality_counts,
        )
        baseline_descriptor["rolling_overlay"] = baseline_overlay.descriptor
        latest_known = bool(
            current_overlay.descriptor["latest_known"]
            and baseline_overlay.descriptor["latest_known"]
            and (
                current_acquired.official_sec_https
                or current_expected_sha is not None
            )
            and (
                baseline_acquired.official_sec_https
                or baseline_expected_sha is not None
            )
        )
        compilation = census.compile(
            ticker_by_cusip=ticker_map,
            sector_by_ticker=classifications,
            generated_at=generated_at,
            current_source=current_descriptor,
            baseline_source=baseline_descriptor,
            identifier_resolution={
                "source": "openfigi_cusip_ticker_projection",
                "sha256": ticker_map_sha,
                "resolved_cusips": len(ticker_map),
                "venue_policy": "us_trading_venues_only",
                "temporal_policy": "current_map_not_point_in_time",
            },
            classification_resolution={
                "source": "fund_intelligence_current_classification_map",
                "sha256": classification_sha,
                "temporal_policy": "current_map_not_point_in_time",
            },
            source_cutoff_at=source_cutoff_at,
            latest_known=latest_known,
            action_threshold_pct=args.action_threshold_pct,
            max_rows=args.max_rows,
            minimum_mapping_coverage_pct=minimum_mapping_coverage_pct,
            research_minimum_quarters=args.research_minimum_quarters,
            research_maximum_candidates=args.research_maximum_candidates,
            compilation_inputs=compilation_inputs,
        )

    if bulk_revision_ids:
        compilation.receipt["bulk_revision_ids"] = bulk_revision_ids
    if research_store is not None:
        from engine.institutional_census.research_bench import (
            publish_private_research_bench,
        )

        published_bench = publish_private_research_bench(
            research_store,
            bench=compilation.research_bench,
            current_period=compilation.receipt["current_period"],
            baseline_period=compilation.receipt["baseline_period"],
            source_cutoff_at=source_cutoff_at,
            published_at=publication_clock,
            producer_version=PRODUCER_VERSION,
        )
        compilation.receipt["private_research_bench"] = published_bench.receipt()

    write_compilation(
        compilation,
        public_path=args.public_output,
        research_bench_path=args.research_bench_output,
        receipt_path=args.receipt_output,
    )
    return compilation.receipt


def _parser() -> argparse.ArgumentParser:
    today = datetime.now(timezone.utc).date()
    current = latest_completed_period(today)
    baseline = _previous_quarter(current)
    root = config.ROOT
    settings, _path, _sha = _institutional_config()
    public_settings = settings["public_summary"]
    research_settings = settings["research_bench"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-period", default=current.isoformat())
    parser.add_argument("--baseline-period", default=baseline.isoformat())
    parser.add_argument("--current-source")
    parser.add_argument("--baseline-source")
    parser.add_argument(
        "--current-expected-sha256",
        help="explicit operator attestation for a non-SEC current source",
    )
    parser.add_argument(
        "--baseline-expected-sha256",
        help="explicit operator attestation for a non-SEC baseline source",
    )
    parser.add_argument("--generated-at")
    parser.add_argument(
        "--source-cutoff-at",
        help="explicit inclusive SEC acceptance cutoff; defaults to the latest bound evidence clock",
    )
    parser.add_argument("--cache-dir", default=str(root / "data" / "institutional_13f" / "bulk_cache"))
    parser.add_argument("--database")
    parser.add_argument("--ticker-map", default=str(root / "data" / "openfigi" / "cusip_ticker.parquet"))
    parser.add_argument("--public-output", default=str(root / "data" / "institutional_13f" / "public" / "census_latest.json"))
    parser.add_argument("--research-bench-output", default=str(root / "data" / "institutional_13f" / "research_bench" / "current.json"))
    parser.add_argument("--receipt-output", default=str(root / "data" / "institutional_13f" / "receipts" / "census_latest.json"))
    parser.add_argument(
        "--action-threshold-pct", type=float,
        default=float(public_settings["action_share_change_threshold_pct"]),
    )
    parser.add_argument("--max-rows", type=int, default=int(public_settings["max_security_rows"]))
    parser.add_argument(
        "--minimum-mapping-coverage-pct", type=float,
        default=float(public_settings["minimum_mapping_coverage_pct"]),
    )
    parser.add_argument(
        "--research-minimum-quarters", type=int,
        default=int(research_settings["minimum_quarters_for_scoring"]),
    )
    parser.add_argument(
        "--research-maximum-candidates", type=int,
        default=int(research_settings["maximum_candidates"]),
    )
    parser.add_argument(
        "--catalog-overlay-mode", choices=("auto", "required", "disabled"),
        default="auto",
        help="use each verified rolling catalog pointer when available",
    )
    parser.add_argument("--force", action="store_true", help="rebuild even when the full compilation identity and exact artifacts match")
    parser.add_argument("--publish-bulk-evidence", action="store_true", help="retain both exact SEC ZIP revisions before projection")
    parser.add_argument("--local-store", help="explicit filesystem evidence store; otherwise dedicated R2 environment is required")
    parser.add_argument(
        "--publish-research-bench", action="store_true",
        help="publish the identity-bearing bench only to the dedicated private store",
    )
    parser.add_argument(
        "--local-research-store",
        help="explicit filesystem private-bench store; otherwise dedicated research R2 is required",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt = build(args)
    print(
        f"institutional 13F census {receipt['current_period']} vs "
        f"{receipt['baseline_period']}: {receipt['public_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
