from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from engine.institutional_census.aggregate import (
    CensusAccumulator,
    PUBLIC_MAX_BYTES,
    classify_manager_name,
    compilation_json_bytes,
    infer_common_share_factor,
    is_structural_holder_discontinuity,
    load_ticker_map,
    write_compilation,
)


class Tables:
    def __init__(self, submissions, covers, holdings):
        self.submissions = pd.DataFrame(submissions)
        self.cover_pages = pd.DataFrame(covers)
        self.holdings = pd.DataFrame(holdings)


def _submission(accession: str, cik: str, period: str, form: str = "13F-HR") -> dict:
    return {
        "accession": accession,
        "filing_date": "2026-05-10" if period == "2026-03-31" else "2026-02-10",
        "form": form,
        "cik": cik,
        "period_end": period,
        "accepted_at": None,
    }


def _cover(accession: str, name: str, file_number: str, *, amendment_type=None) -> dict:
    return {
        "accession": accession,
        "filing_manager_name": name,
        "form_13f_file_number": file_number,
        "is_amendment": amendment_type is not None,
        "amendment_type": amendment_type,
    }


def _holding(accession: str, cusip: str, shares: int, issuer: str) -> dict:
    return {
        "accession": accession,
        "cusip": cusip,
        "issuer_name": issuer,
        "value": shares,
        "shares_or_principal_amount": shares,
        "shares_or_principal_amount_type": "SH",
        "put_call": None,
    }


def test_completed_quarter_projection_never_treats_pending_or_notice_as_exit(tmp_path):
    baseline = Tables(
        [
            _submission("0000000001-26-000001", "0000000001", "2025-12-31"),
            _submission("0000000002-26-000001", "0000000002", "2025-12-31"),
            _submission("0000000003-26-000001", "0000000003", "2025-12-31"),
        ],
        [
            _cover("0000000001-26-000001", "Alpha Capital", "028-1"),
            _cover("0000000002-26-000001", "Beta Capital", "028-2"),
            _cover("0000000003-26-000001", "Pending Capital", "028-3"),
        ],
        [
            _holding("0000000001-26-000001", "111111111", 100, "Alpha Inc"),
            _holding("0000000002-26-000001", "222222222", 50, "Beta Inc"),
            _holding("0000000003-26-000001", "333333333", 80, "Pending Inc"),
        ],
    )
    current = Tables(
        [
            _submission("0000000001-26-000002", "0000000001", "2026-03-31"),
            _submission("0000000002-26-000002", "0000000002", "2026-03-31"),
            _submission("0000000004-26-000001", "0000000004", "2026-03-31", "13F-NT"),
        ],
        [
            _cover("0000000001-26-000002", "Alpha Capital", "028-1"),
            _cover("0000000002-26-000002", "Beta Capital", "028-2"),
            _cover("0000000004-26-000001", "Notice Capital", "028-4"),
        ],
        [_holding("0000000001-26-000002", "111111111", 110, "Alpha Inc")],
    )

    with CensusAccumulator(tmp_path / "census.sqlite") as census:
        census.ingest("current", current, period_end="2026-03-31")
        census.ingest("baseline", baseline, period_end="2025-12-31")
        result = census.compile(
            ticker_by_cusip={
                "111111111": {"ticker": "AAA", "name": "Alpha"},
                "222222222": {"ticker": "BBB", "name": "Beta"},
                "333333333": {"ticker": "CCC", "name": "Pending"},
            },
            sector_by_ticker={"AAA": "Technology", "BBB": "Industrials", "CCC": "Energy"},
            generated_at="2026-06-01T12:00:00Z",
        )

    public = result.public_summary
    assert public["coverage"]["current_original_filings"] == 2
    assert public["coverage"]["baseline_original_filings"] == 3
    assert public["coverage"]["paired_filings"] == 2
    assert public["coverage"]["current_notice_filers"] == 1
    assert [row["ticker"] for row in public["leaders"]["broadening"]] == ["AAA"]
    assert [row["ticker"] for row in public["leaders"]["narrowing"]] == ["BBB"]
    # The baseline-only pending filer is not part of the paired cohort.
    assert "CCC" not in json.dumps(public)
    assert result.research_bench["status"] == "screened_not_promoted"
    assert result.research_bench["eligible_count"] == 0
    assert result.receipt["public_bytes"] <= PUBLIC_MAX_BYTES
    assert '"accession' not in json.dumps(public, sort_keys=True).casefold()


def test_latest_restatement_replaces_original_and_new_holdings_append(tmp_path):
    baseline = Tables(
        [_submission("0000000001-25-000001", "1", "2025-12-31")],
        [_cover("0000000001-25-000001", "Alpha", "028-1")],
        [_holding("0000000001-25-000001", "111111111", 100, "Alpha")],
    )
    current = Tables(
        [
            _submission("0000000001-26-000001", "1", "2026-03-31"),
            _submission("0000000001-26-000002", "1", "2026-03-31", "13F-HR/A"),
            _submission("0000000001-26-000003", "1", "2026-03-31", "13F-HR/A"),
        ],
        [
            _cover("0000000001-26-000001", "Alpha", "028-1"),
            _cover("0000000001-26-000002", "Alpha", "028-1", amendment_type="RESTATEMENT"),
            _cover("0000000001-26-000003", "Alpha", "028-1", amendment_type="NEW HOLDINGS"),
        ],
        [
            _holding("0000000001-26-000001", "111111111", 10, "Alpha"),
            _holding("0000000001-26-000002", "111111111", 120, "Alpha"),
            _holding("0000000001-26-000003", "222222222", 20, "Beta"),
        ],
    )
    with CensusAccumulator(tmp_path / "census.sqlite") as census:
        census.ingest("current", current, period_end="2026-03-31")
        census.ingest("baseline", baseline, period_end="2025-12-31")
        result = census.compile(
            ticker_by_cusip={"111111111": "AAA", "222222222": "BBB"},
            generated_at="2026-06-01T12:00:00Z",
        )
    rows = {row["ticker"]: row for row in result.public_summary["leaders"]["broadening"]}
    assert rows["AAA"]["adding_filers"] == 1
    assert rows["BBB"]["new_filers"] == 1
    assert result.public_summary["coverage"]["current_amendments"] == 2


def test_quality_excluded_accession_cannot_move_breadth(tmp_path):
    baseline = Tables(
        [_submission("0000000001-25-000001", "1", "2025-12-31")],
        [_cover("0000000001-25-000001", "Alpha", "028-1")],
        [_holding("0000000001-25-000001", "111111111", 100, "Alpha")],
    )
    current = Tables(
        [_submission("0000000001-26-000001", "1", "2026-03-31")],
        [_cover("0000000001-26-000001", "Alpha", "028-1")],
        [_holding("0000000001-26-000001", "111111111", 200, "Alpha")],
    )
    with CensusAccumulator(tmp_path / "census.sqlite") as census:
        census.ingest(
            "current", current, period_end="2026-03-31",
            excluded_accessions={"0000000001-26-000001"},
        )
        census.ingest("baseline", baseline, period_end="2025-12-31")
        result = census.compile(ticker_by_cusip={"111111111": "AAA"})
    assert result.public_summary["coverage"]["paired_filings"] == 0
    assert result.public_summary["coverage"]["current_quality_excluded_reports"] == 1
    assert result.public_summary["leaders"]["broadening"] == []


def test_quality_exclusion_quarantines_required_amendment_lineage_atomically(tmp_path):
    baseline = Tables(
        [_submission("0000000001-25-000001", "1", "2025-12-31")],
        [_cover("0000000001-25-000001", "Alpha", "028-1")],
        [_holding("0000000001-25-000001", "111111111", 100, "Alpha")],
    )
    current = Tables(
        [
            _submission("0000000001-26-000001", "1", "2026-03-31"),
            _submission("0000000001-26-000002", "1", "2026-03-31", "13F-HR/A"),
        ],
        [
            _cover("0000000001-26-000001", "Alpha", "028-1"),
            _cover(
                "0000000001-26-000002", "Alpha", "028-1",
                amendment_type="NEW HOLDINGS",
            ),
        ],
        [
            _holding("0000000001-26-000001", "111111111", 100, "Alpha"),
            _holding("0000000001-26-000002", "222222222", 50, "Beta"),
        ],
    )
    with CensusAccumulator(tmp_path / "census.sqlite") as census:
        census.ingest(
            "current", current, period_end="2026-03-31",
            excluded_accessions={"0000000001-26-000001"},
        )
        census.ingest("baseline", baseline, period_end="2025-12-31")
        result = census.compile(
            ticker_by_cusip={"111111111": "AAA", "222222222": "BBB"}
        )
    assert result.public_summary["coverage"]["paired_filings"] == 0
    assert result.public_summary["coverage"]["current_quality_excluded_lineages"] == 1
    assert result.public_summary["leaders"] == {"broadening": [], "narrowing": []}


def test_overlapping_new_holdings_lineage_is_never_summed(tmp_path):
    baseline = Tables(
        [_submission("0000000001-25-000001", "1", "2025-12-31")],
        [_cover("0000000001-25-000001", "Alpha", "028-1")],
        [_holding("0000000001-25-000001", "111111111", 100, "Alpha")],
    )
    current = Tables(
        [
            _submission("0000000001-26-000001", "1", "2026-03-31"),
            _submission("0000000001-26-000002", "1", "2026-03-31", "13F-HR/A"),
        ],
        [
            _cover("0000000001-26-000001", "Alpha", "028-1"),
            _cover(
                "0000000001-26-000002", "Alpha", "028-1",
                amendment_type="NEW HOLDINGS",
            ),
        ],
        [
            _holding("0000000001-26-000001", "111111111", 120, "Alpha"),
            _holding("0000000001-26-000002", "111111111", 120, "Alpha"),
        ],
    )
    with CensusAccumulator(tmp_path / "census.sqlite") as census:
        census.ingest("current", current, period_end="2026-03-31")
        census.ingest("baseline", baseline, period_end="2025-12-31")
        result = census.compile(ticker_by_cusip={"111111111": "AAA"})
    assert result.public_summary["coverage"]["paired_filings"] == 0
    assert result.public_summary["coverage"]["current_overlapping_amendment_lineages"] == 1
    assert result.public_summary["leaders"]["broadening"] == []


def test_common_two_for_one_share_factor_is_quarantined_from_buying_board(tmp_path):
    baseline_submissions = [
        _submission(f"000000000{i}-25-000001", str(i), "2025-12-31")
        for i in (1, 2)
    ]
    current_submissions = [
        _submission(f"000000000{i}-26-000001", str(i), "2026-03-31")
        for i in (1, 2)
    ]
    baseline = Tables(
        baseline_submissions,
        [_cover(row["accession"], f"Manager {i}", f"028-{i}") for i, row in enumerate(baseline_submissions, 1)],
        [_holding(row["accession"], "111111111", 100, "Split Co") for row in baseline_submissions],
    )
    current = Tables(
        current_submissions,
        [_cover(row["accession"], f"Manager {i}", f"028-{i}") for i, row in enumerate(current_submissions, 1)],
        [_holding(row["accession"], "111111111", 200, "Split Co") for row in current_submissions],
    )
    with CensusAccumulator(tmp_path / "census.sqlite") as census:
        census.ingest("current", current, period_end="2026-03-31")
        census.ingest("baseline", baseline, period_end="2025-12-31")
        result = census.compile(ticker_by_cusip={"111111111": "SPLT"})
    assert infer_common_share_factor([2.0, 2.0]) == 2.0
    assert result.public_summary["leaders"] == {"broadening": [], "narrowing": []}
    assert result.public_summary["coverage"]["share_factor_security_exclusions"] == 1


def test_mapping_coverage_fence_fails_closed(tmp_path):
    current = Tables(
        [_submission("0000000001-26-000001", "1", "2026-03-31")],
        [_cover("0000000001-26-000001", "Alpha", "028-1")],
        [
            _holding("0000000001-26-000001", "111111111", 100, "Mapped"),
            _holding("0000000001-26-000001", "222222222", 100, "Unknown"),
        ],
    )
    baseline = Tables(
        [_submission("0000000001-25-000001", "1", "2025-12-31")],
        [_cover("0000000001-25-000001", "Alpha", "028-1")],
        [_holding("0000000001-25-000001", "111111111", 100, "Mapped")],
    )
    with CensusAccumulator(tmp_path / "census.sqlite") as census:
        census.ingest("current", current, period_end="2026-03-31")
        census.ingest("baseline", baseline, period_end="2025-12-31")
        with pytest.raises(RuntimeError, match="mapping coverage"):
            census.compile(
                ticker_by_cusip={"111111111": "AAA"},
                minimum_mapping_coverage_pct=80.0,
            )


def test_write_compilation_is_atomic_and_public_payload_is_bounded(tmp_path):
    tables = Tables(
        [_submission("0000000001-26-000001", "1", "2026-03-31")],
        [_cover("0000000001-26-000001", "Alpha", "028-1")],
        [_holding("0000000001-26-000001", "111111111", 10, "Alpha")],
    )
    baseline = Tables(
        [_submission("0000000001-25-000001", "1", "2025-12-31")],
        [_cover("0000000001-25-000001", "Alpha", "028-1")],
        [_holding("0000000001-25-000001", "111111111", 9, "Alpha")],
    )
    with CensusAccumulator(tmp_path / "db.sqlite") as census:
        census.ingest("current", tables, period_end="2026-03-31")
        census.ingest("baseline", baseline, period_end="2025-12-31")
        result = census.compile(ticker_by_cusip={"111111111": "AAA"})
    public = tmp_path / "public.json"
    bench = tmp_path / "bench.json"
    receipt = tmp_path / "receipt.json"
    write_compilation(
        result, public_path=public, research_bench_path=bench, receipt_path=receipt
    )
    assert json.loads(public.read_text())["schema"] == "institutional_13f.census_public/v1"
    assert json.loads(receipt.read_text())["public_bytes"] <= PUBLIC_MAX_BYTES
    stored_receipt = json.loads(receipt.read_bytes())
    assert public.read_bytes() == compilation_json_bytes(result.public_summary)
    assert bench.read_bytes() == compilation_json_bytes(result.research_bench)
    assert hashlib.sha256(public.read_bytes()).hexdigest() == stored_receipt["public_sha256"]
    assert hashlib.sha256(bench.read_bytes()).hexdigest() == stored_receipt["research_bench_sha256"]
    assert stored_receipt["research_bench_bytes"] == len(bench.read_bytes())
    assert not list(tmp_path.glob("*.tmp"))


def test_manager_classification_is_conservative_and_provenanced():
    assert classify_manager_name("Vanguard Group Inc")[0] == "passive"
    assert classify_manager_name("Northern Trust Corporation")[0] == "custody"
    assert classify_manager_name("A Really Clever Fund")[0] == "unknown"
    assert classify_manager_name("A Really Clever Fund")[1] == "name_pattern_v1"


def test_structural_discontinuity_fence_separates_identifier_break_from_broad_trim():
    assert is_structural_holder_discontinuity(
        holder_delta=354, new_filers=433, exiting_filers=79, activity=1100
    )
    assert not is_structural_holder_discontinuity(
        holder_delta=-330, new_filers=150, exiting_filers=480, activity=1977
    )


def test_ticker_loader_rejects_foreign_resolution_for_retired_us_cusip(tmp_path):
    source = tmp_path / "map.parquet"
    pd.DataFrame([
        {"cusip": "111111111", "ticker": "AAA", "name": "Alpha", "exch": "US", "sec_type": "Common Stock"},
        {"cusip": "222222222", "ticker": "AZNN", "name": "AstraZeneca", "exch": "MM", "sec_type": "Depositary Receipt"},
        {"cusip": "333333333", "ticker": "RSP", "name": "ETF", "exch": "US", "sec_type": "Mutual Fund"},
    ]).to_parquet(source, index=False)
    assert load_ticker_map(source) == {
        "111111111": {
            "ticker": "AAA", "name": "Alpha", "security_type": "Common Stock"
        }
    }
