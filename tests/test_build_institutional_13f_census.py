from datetime import date
import hashlib
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from engine.institutional_census.aggregate import (
    CensusAccumulator,
    compilation_json_bytes,
    write_compilation,
)
from scripts.build_institutional_13f_census import (
    _bulk_source_cutoff,
    _catalog_has_complete_discovery_coverage,
    _catalog_overlay,
    _confidential_accessions,
    _copy_or_download,
    _matching_existing_receipt,
    _private_bench_matches_receipt,
    _source_descriptor,
    _validate_expected_sha256,
    bulk_url,
    bulk_window,
    latest_completed_period,
)


class Tables:
    def __init__(self, submissions, covers, holdings):
        self.submissions = pd.DataFrame(submissions)
        self.cover_pages = pd.DataFrame(covers)
        holding_counts = {}
        for row in holdings:
            holding_counts[row["accession"]] = holding_counts.get(row["accession"], 0) + 1
        self.summary_pages = pd.DataFrame([
            {
                "accession": row["accession"],
                "table_entry_total": holding_counts.get(row["accession"], 0),
                "is_confidential_omitted": False,
            }
            for row in submissions if row.get("form") in {"13F-HR", "13F-HR/A"}
        ])
        self.holdings = pd.DataFrame(holdings)


def _submission(accession, cik, period, *, form="13F-HR", filing_date="2026-05-10"):
    return {
        "accession": accession, "cik": cik, "period_end": period,
        "form": form, "filing_date": filing_date, "accepted_at": None,
    }


def _cover(accession, *, amendment_type=None):
    return {
        "accession": accession, "filing_manager_name": "Alpha",
        "form_13f_file_number": "028-1", "amendment_type": amendment_type,
    }


def _holding(accession, shares):
    return {
        "accession": accession, "cusip": "111111111", "issuer_name": "Alpha",
        "title_of_class": "COM", "value": shares,
        "shares_or_principal_amount": shares,
        "shares_or_principal_amount_type": "SH", "put_call": None,
        "investment_discretion": "SOLE", "other_manager": None,
        "voting_authority_sole": shares, "voting_authority_shared": 0,
        "voting_authority_none": 0,
    }


def _catalog_holding(accession, shares):
    return {
        "accession": accession, "cusip": "111111111", "figi": None,
        "name_of_issuer": "Alpha", "title_of_class": "COM",
        "value_reported": str(shares), "ssh_prn_amt": str(shares),
        "ssh_prn_type": "SH", "put_call": None,
        "investment_discretion": "SOLE", "other_manager": None,
        "voting_authority_sole": shares, "voting_authority_shared": 0,
        "voting_authority_none": 0,
    }


class _Manifest:
    def __init__(self, period, cutoff):
        self.clocks = SimpleNamespace(
            report_period=period, source_cutoff_at=cutoff,
        )

    def to_json_bytes(self):
        return compilation_json_bytes({
            "period": self.clocks.report_period,
            "cutoff": self.clocks.source_cutoff_at,
        })


def _generation(*, duplicate_shares=100):
    original = "0000000001-26-000001"
    restatement = "0000000001-26-000009"
    common = {
        "filer_cik": "0000000001", "filer_name": "Alpha",
        "report_period": "2026-03-31", "form13f_file_number": "028-1",
        "confidential_omitted": False, "table_entry_total": 1,
        "other_manager_count": 0,
    }
    return SimpleNamespace(
        generation_id="i13fgen_" + "a" * 64,
        manifest=_Manifest("2026-03-31", "2026-08-08T12:00:00Z"),
        filings=(
            {
                **common, "accession": original, "form": "13F-HR",
                "filing_date": "2026-05-10", "accepted_at": "2026-05-10T12:00:00Z",
                "is_amendment": False, "amendment_number": None,
                "amendment_type": None, "report_type": "13F HOLDINGS REPORT",
            },
            {
                **common, "accession": restatement, "form": "13F-HR/A",
                "filing_date": "2026-08-06", "accepted_at": "2026-08-06T12:00:00Z",
                "is_amendment": True, "amendment_number": 1,
                "amendment_type": "RESTATEMENT", "report_type": "13F HOLDINGS REPORT",
            },
        ),
        holdings=(
            _catalog_holding(original, duplicate_shares),
            _catalog_holding(restatement, 150),
        ),
    )


def test_latest_completed_period_stays_on_q1_during_q2_filing_window():
    assert latest_completed_period(date(2026, 8, 8)) == date(2026, 3, 31)
    assert latest_completed_period(date(2026, 8, 15)) == date(2026, 6, 30)


def test_bulk_package_is_filing_month_window_not_report_period_label():
    assert bulk_window(date(2026, 3, 31)) == (date(2026, 3, 1), date(2026, 5, 31))
    assert bulk_window(date(2025, 12, 31)) == (date(2025, 12, 1), date(2026, 2, 28))
    assert bulk_url(date(2026, 3, 31)).endswith("/01mar2026-31may2026_form13f.zip")
    assert bulk_url(date(2025, 12, 31)).endswith("/01dec2025-28feb2026_form13f.zip")


def test_confidential_omission_is_excluded_from_comparable_action_cohort():
    tables = SimpleNamespace(summary_pages=pd.DataFrame([
        {"accession": "0000000001-26-000001", "is_confidential_omitted": True},
        {"accession": "0000000002-26-000001", "is_confidential_omitted": False},
        {"accession": "0000000003-26-000001", "is_confidential_omitted": pd.NA},
    ]))
    assert _confidential_accessions(tables) == {"0000000001-26-000001"}


def test_catalog_only_late_restatement_replaces_bulk_original_through_cutoff(tmp_path):
    original = "0000000001-26-000001"
    current = Tables(
        [_submission(original, "1", "2026-03-31")],
        [_cover(original)],
        [_holding(original, 100)],
    )
    baseline_accession = "0000000001-25-000001"
    baseline = Tables(
        [_submission(
            baseline_accession, "1", "2025-12-31", filing_date="2026-02-10"
        )],
        [_cover(baseline_accession)],
        [_holding(baseline_accession, 100)],
    )
    overlay = _catalog_overlay(
        current,
        _generation(),
        period_end="2026-03-31",
        source_cutoff_at="2026-08-07T00:00:00Z",
    )
    assert overlay.descriptor["catalog_only_filings"] == 1
    assert overlay.descriptor["bulk_duplicate_filings_verified"] == 1
    # A fresh cutoff is not a completeness claim.  This synthetic generation
    # carries no continuous EDGAR index-coverage receipt, so the late
    # restatement is applied while latest_known remains conservative.
    assert overlay.descriptor["latest_known"] is False

    with CensusAccumulator(tmp_path / "census.sqlite") as census:
        census.ingest(
            "current", current, period_end="2026-03-31",
            supplemental_tables=(overlay.tables,),
        )
        census.ingest("baseline", baseline, period_end="2025-12-31")
        result = census.compile(ticker_by_cusip={"111111111": "AAA"})
    assert result.public_summary["coverage"]["current_amendments"] == 1
    assert result.public_summary["leaders"]["broadening"][0]["ticker"] == "AAA"
    assert result.public_summary["leaders"]["broadening"][0]["adding_filers"] == 1


def test_catalog_duplicate_conflict_fails_instead_of_overwriting_bulk():
    original = "0000000001-26-000001"
    current = Tables(
        [_submission(original, "1", "2026-03-31")],
        [_cover(original)],
        [_holding(original, 100)],
    )
    with pytest.raises(RuntimeError, match="holding conflict"):
        _catalog_overlay(
            current,
            _generation(duplicate_shares=101),
            period_end="2026-03-31",
            source_cutoff_at="2026-08-07T00:00:00Z",
        )


def test_catalog_latest_known_requires_explicit_continuous_index_coverage():
    generation = _generation()
    generation.payloads = {
        "coverage_json": compilation_json_bytes({
            "schema": "institutional_13f.catalog_coverage/v1",
            "report_period": "2026-03-31",
            "historical_index_coverage_complete": True,
            "run_failure_count": 0,
            "backlog_accessions": 0,
        })
    }
    assert _catalog_has_complete_discovery_coverage(generation) is True

    generation.payloads["coverage_json"] = compilation_json_bytes({
        "schema": "institutional_13f.catalog_coverage/v1",
        "report_period": "2026-03-31",
        "historical_index_coverage_complete": True,
        "run_failure_count": 0,
        "backlog_accessions": 1,
    })
    assert _catalog_has_complete_discovery_coverage(generation) is False


def test_matching_receipt_proves_actual_artifact_bytes_and_rejects_corruption(tmp_path):
    current_accession = "0000000001-26-000001"
    baseline_accession = "0000000001-25-000001"
    current = Tables(
        [_submission(current_accession, "1", "2026-03-31")],
        [_cover(current_accession)],
        [_holding(current_accession, 110)],
    )
    baseline = Tables(
        [_submission(
            baseline_accession, "1", "2025-12-31", filing_date="2026-02-10"
        )],
        [_cover(baseline_accession)],
        [_holding(baseline_accession, 100)],
    )
    inputs = {"schema": "institutional_13f.compilation_inputs/v1", "stable": True}
    with CensusAccumulator(tmp_path / "census.sqlite") as census:
        census.ingest("current", current, period_end="2026-03-31")
        census.ingest("baseline", baseline, period_end="2025-12-31")
        result = census.compile(
            ticker_by_cusip={"111111111": "AAA"},
            generated_at="2026-08-08T12:00:00Z",
            compilation_inputs=inputs,
        )
    from engine.institutional_census.research_bench import (
        build_institutional_13f_research_store,
        publish_private_research_bench,
    )

    research_store = build_institutional_13f_research_store(
        local_dir=tmp_path / "private"
    )
    published = publish_private_research_bench(
        research_store,
        bench=result.research_bench,
        current_period="2026-03-31",
        baseline_period="2025-12-31",
        source_cutoff_at="2026-08-08T12:00:00Z",
        published_at="2026-08-08T12:00:00Z",
        producer_version="institutional-13f-census-test/1.0.0",
    )
    result.receipt["private_research_bench"] = published.receipt()
    public = tmp_path / "public.json"
    bench = tmp_path / "bench.json"
    receipt = tmp_path / "receipt.json"
    write_compilation(
        result,
        public_path=public,
        research_bench_path=bench,
        receipt_path=receipt,
    )
    kwargs = {
        "public_path": public,
        "research_bench_path": bench,
        "receipt_path": receipt,
        "current_period": "2026-03-31",
        "baseline_period": "2025-12-31",
        "compilation_id": result.receipt["compilation_id"],
    }
    assert _matching_existing_receipt(**kwargs) == result.receipt
    # Identical stable inputs still no-op on a later scheduler day; wall time is
    # not part of the caller-supplied compilation identity.
    assert _matching_existing_receipt(**kwargs) == result.receipt

    # A fresh Actions checkout removes the ignored local bench.  The verified
    # private pointer is authoritative enough to prove the same exact bytes and
    # preserve the cheap no-op path.
    bench.unlink()
    durable_kwargs = {**kwargs, "research_store": research_store}
    assert _matching_existing_receipt(**durable_kwargs) == result.receipt
    assert _private_bench_matches_receipt(research_store, result.receipt)
    empty_research_store = build_institutional_13f_research_store(
        local_dir=tmp_path / "empty-private"
    )
    assert _matching_existing_receipt(
        **{**kwargs, "research_store": empty_research_store}
    ) is None

    corrupted = json.loads(public.read_bytes())
    corrupted["generated_at"] = "2026-08-09T12:00:00Z"
    public.write_bytes(compilation_json_bytes(corrupted))
    assert _matching_existing_receipt(**durable_kwargs) is None


def test_operator_file_source_is_not_relabelled_as_official_sec_acquisition(tmp_path):
    source = tmp_path / "seed.zip"
    source.write_bytes(b"PK\x03\x04operator seed")
    acquired = _copy_or_download(source.as_posix(), tmp_path / "cached.zip")
    assert acquired.acquisition_mode == "operator_file"
    assert acquired.final_url is None
    with pytest.raises(RuntimeError, match="expected SHA-256 attestation"):
        _validate_expected_sha256(
            acquired, None, label="current", publication_required=True
        )
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    assert _validate_expected_sha256(
        acquired, expected, label="current", publication_required=True
    ) == expected
    descriptor = _source_descriptor(
        acquired=acquired,
        official_reference_url=(
            "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
            "01mar2026-31may2026_form13f.zip"
        ),
        filing_window_cutoff_at="2026-05-29T21:30:00Z",
        expected_sha256=None,
    )
    assert descriptor["url"] == "operator-supplied-file"
    assert descriptor["acquisition_mode"] == "operator_file"
    assert descriptor["official_source_status"] == "operator_supplied_unattested"
    assert "seed.zip" not in json.dumps(descriptor)


def test_bulk_cutoff_uses_sec_final_business_day_1730_eastern_rule():
    # May 31, 2026 is Sunday; the final represented business-day cutoff is
    # Friday May 29 at 17:30 EDT (21:30 UTC), not calendar-month midnight.
    assert _bulk_source_cutoff(date(2026, 3, 31)) == "2026-05-29T21:30:00Z"
    # February 28, 2026 is Saturday and New York is still on standard time.
    assert _bulk_source_cutoff(date(2025, 12, 31)) == "2026-02-27T22:30:00Z"


def test_sec_redirect_must_end_on_https_sec_domain(tmp_path):
    class Response:
        headers = {"Content-Type": "application/zip"}
        url = "https://attacker.invalid/copied.zip"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def raise_for_status(self):
            return None

        def iter_content(self, _size):
            yield b"PK\x03\x04copied"

    with pytest.raises(RuntimeError, match="escaped sec.gov"):
        _copy_or_download(
            "https://www.sec.gov/files/source.zip",
            tmp_path / "cached.zip",
            fetch=lambda *_args, **_kwargs: Response(),
        )
