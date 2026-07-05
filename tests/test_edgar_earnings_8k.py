"""Unit tests for collectors/edgar_earnings_8k.py (Entry-Stack W1).

Tests cover:
  1. tokenize_items — exact comma-split and strip
  2. has_item_202  — exact-token matching (no substring match of "12.02")
  3. _extract_8k_rows — correct row extraction from a submissions 'recent' block
  4. append_and_dedup — dedup logic for the resumable manifest
  5. Manifest skip logic — already-fetched CIKs are skipped on re-run
  6. compute_coverage — PASS/FAIL verdict generation

No live network calls are made anywhere in this test file.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.edgar_earnings_8k as e8k  # noqa: E402


# ---------------------------------------------------------------------------
# tokenize_items
# ---------------------------------------------------------------------------

class TestTokenizeItems:
    def test_two_items(self):
        assert e8k.tokenize_items("2.02,9.01") == ["2.02", "9.01"]

    def test_single_item(self):
        assert e8k.tokenize_items("2.02") == ["2.02"]

    def test_strips_whitespace(self):
        assert e8k.tokenize_items(" 2.02 , 9.01 ") == ["2.02", "9.01"]

    def test_empty_string(self):
        assert e8k.tokenize_items("") == []

    def test_none(self):
        assert e8k.tokenize_items(None) == []

    def test_longer_item_code(self):
        # 12.02 is NOT 2.02 — must remain as its own token
        assert e8k.tokenize_items("12.02,9.01") == ["12.02", "9.01"]

    def test_three_items(self):
        assert e8k.tokenize_items("2.02,7.01,9.01") == ["2.02", "7.01", "9.01"]


# ---------------------------------------------------------------------------
# has_item_202 — exact token matching
# ---------------------------------------------------------------------------

class TestHasItem202:
    def test_exact_match(self):
        assert e8k.has_item_202("2.02") is True

    def test_with_trailing_item(self):
        assert e8k.has_item_202("2.02,9.01") is True

    def test_leading_item(self):
        assert e8k.has_item_202("9.01,2.02") is True

    def test_middle_item(self):
        assert e8k.has_item_202("9.01,2.02,7.01") is True

    def test_no_match(self):
        assert e8k.has_item_202("9.01") is False

    def test_12_02_is_not_a_match(self):
        # Critical: substring match would incorrectly match "12.02"
        assert e8k.has_item_202("12.02,9.01") is False

    def test_2_020_is_not_a_match(self):
        # Edge case token "2.020" should NOT match "2.02"
        assert e8k.has_item_202("2.020,9.01") is False

    def test_empty(self):
        assert e8k.has_item_202("") is False

    def test_none(self):
        assert e8k.has_item_202(None) is False

    def test_whitespace_around_token(self):
        # The tokenizer strips whitespace, so " 2.02 " still matches
        assert e8k.has_item_202(" 2.02 ") is True

    def test_material_items_only_no_202(self):
        # A filing with only material items but NOT 2.02
        assert e8k.has_item_202("1.01,5.02,9.01") is False


# ---------------------------------------------------------------------------
# _extract_8k_rows — parses the 'recent' submissions block
# ---------------------------------------------------------------------------

class TestExtractRows:
    def _make_rec(self, forms, filing_dates, items_list, acceptance_dts=None):
        """Build a minimal submissions 'recent' block."""
        rec = {
            "form": forms,
            "filingDate": filing_dates,
            "items": items_list,
        }
        if acceptance_dts is not None:
            rec["acceptanceDateTime"] = acceptance_dts
        return rec

    def test_basic_extraction(self):
        rec = self._make_rec(
            forms=["8-K", "10-Q"],
            filing_dates=["2023-01-15", "2023-02-01"],
            items_list=["2.02,9.01", ""],
        )
        rows = e8k._extract_8k_rows("AAPL", 320193, rec)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "AAPL"
        assert rows[0]["cik"] == 320193
        assert rows[0]["filing_date"] == "2023-01-15"
        assert rows[0]["items"] == "2.02,9.01"

    def test_8k_a_also_captured(self):
        """8-K/A amendments with Item 2.02 should also be captured."""
        rec = self._make_rec(
            forms=["8-K/A"],
            filing_dates=["2023-02-10"],
            items_list=["2.02"],
        )
        rows = e8k._extract_8k_rows("MSFT", 789019, rec)
        assert len(rows) == 1

    def test_skips_non_202(self):
        rec = self._make_rec(
            forms=["8-K", "8-K"],
            filing_dates=["2023-01-15", "2023-03-20"],
            items_list=["1.01,9.01", "5.02"],
        )
        rows = e8k._extract_8k_rows("AAPL", 320193, rec)
        assert rows == []

    def test_skips_non_8k_forms(self):
        rec = self._make_rec(
            forms=["10-Q", "10-K", "DEF 14A"],
            filing_dates=["2023-01-15", "2023-03-01", "2023-04-01"],
            items_list=["2.02", "2.02", "2.02"],
        )
        rows = e8k._extract_8k_rows("AAPL", 320193, rec)
        assert rows == []

    def test_skips_12_02_not_2_02(self):
        """12.02 must NOT be matched as 2.02 (exact-token law)."""
        rec = self._make_rec(
            forms=["8-K"],
            filing_dates=["2023-01-15"],
            items_list=["12.02,9.01"],
        )
        rows = e8k._extract_8k_rows("AAPL", 320193, rec)
        assert rows == []

    def test_multiple_202_filings(self):
        rec = self._make_rec(
            forms=["8-K", "8-K", "8-K"],
            filing_dates=["2023-01-15", "2023-04-20", "2023-07-18"],
            items_list=["2.02,9.01", "1.01", "2.02"],
        )
        rows = e8k._extract_8k_rows("AAPL", 320193, rec)
        assert len(rows) == 2
        assert rows[0]["filing_date"] == "2023-01-15"
        assert rows[1]["filing_date"] == "2023-07-18"

    def test_acceptance_datetime_stored(self):
        rec = self._make_rec(
            forms=["8-K"],
            filing_dates=["2023-01-15"],
            items_list=["2.02"],
            acceptance_dts=["2023-01-15T21:30:00.000Z"],
        )
        rows = e8k._extract_8k_rows("AAPL", 320193, rec)
        assert len(rows) == 1
        assert rows[0]["acceptance_datetime"] == "2023-01-15T21:30:00.000Z"

    def test_missing_acceptance_datetime_defaults_empty(self):
        """When acceptanceDateTime is absent from the record, default to empty string."""
        rec = self._make_rec(
            forms=["8-K"],
            filing_dates=["2023-01-15"],
            items_list=["2.02"],
            # no acceptance_dts — key not present
        )
        rows = e8k._extract_8k_rows("AAPL", 320193, rec)
        assert rows[0]["acceptance_datetime"] == ""

    def test_empty_record(self):
        rows = e8k._extract_8k_rows("AAPL", 320193, {})
        assert rows == []

    def test_mismatched_lengths_safe(self):
        """If items list is shorter than forms, safe indexing returns ''."""
        rec = {
            "form": ["8-K", "8-K"],
            "filingDate": ["2023-01-15", "2023-04-20"],
            "items": ["2.02"],  # only one item for two forms — safe indexing
        }
        rows = e8k._extract_8k_rows("AAPL", 320193, rec)
        # Only the first row has items "2.02"; second row has items='' so no 2.02
        assert len(rows) == 1
        assert rows[0]["filing_date"] == "2023-01-15"


# ---------------------------------------------------------------------------
# append_and_dedup
# ---------------------------------------------------------------------------

class TestAppendAndDedup:
    def _existing(self, rows):
        return pd.DataFrame(rows, columns=["ticker", "cik", "filing_date",
                                           "acceptance_datetime", "items"])

    def test_appends_new_rows(self):
        existing = self._existing([
            ("AAPL", 320193, "2022-10-28", "", "2.02,9.01"),
        ])
        new_rows = [{"ticker": "AAPL", "cik": 320193, "filing_date": "2023-01-27",
                     "acceptance_datetime": "", "items": "2.02"}]
        result = e8k.append_and_dedup(existing, new_rows)
        assert len(result) == 2

    def test_deduplicates_on_ticker_filing_date(self):
        existing = self._existing([
            ("AAPL", 320193, "2022-10-28", "", "2.02,9.01"),
        ])
        new_rows = [{"ticker": "AAPL", "cik": 320193, "filing_date": "2022-10-28",
                     "acceptance_datetime": "2022-10-28T20:00:00Z", "items": "2.02,9.01"}]
        result = e8k.append_and_dedup(existing, new_rows)
        # Dedup keeps first occurrence
        assert len(result) == 1

    def test_empty_new_rows_returns_existing(self):
        existing = self._existing([
            ("AAPL", 320193, "2022-10-28", "", "2.02"),
        ])
        result = e8k.append_and_dedup(existing, [])
        assert len(result) == 1

    def test_empty_existing_plus_new(self):
        existing = self._existing([])
        new_rows = [{"ticker": "MSFT", "cik": 789019, "filing_date": "2023-01-25",
                     "acceptance_datetime": "", "items": "2.02"}]
        result = e8k.append_and_dedup(existing, new_rows)
        assert len(result) == 1
        assert result.iloc[0]["ticker"] == "MSFT"

    def test_sorted_output(self):
        """Output is sorted by (ticker, filing_date)."""
        existing = self._existing([])
        new_rows = [
            {"ticker": "MSFT", "cik": 789019, "filing_date": "2023-04-20",
             "acceptance_datetime": "", "items": "2.02"},
            {"ticker": "AAPL", "cik": 320193, "filing_date": "2023-01-27",
             "acceptance_datetime": "", "items": "2.02"},
            {"ticker": "AAPL", "cik": 320193, "filing_date": "2022-10-28",
             "acceptance_datetime": "", "items": "2.02"},
        ]
        result = e8k.append_and_dedup(existing, new_rows)
        assert result.iloc[0]["ticker"] == "AAPL"
        assert result.iloc[0]["filing_date"] == "2022-10-28"
        assert result.iloc[2]["ticker"] == "MSFT"


# ---------------------------------------------------------------------------
# Manifest resumability logic
# ---------------------------------------------------------------------------

class TestManifestResumability:
    """Tests for the resumable manifest: already-fetched CIKs are skipped."""

    def _cik_map(self):
        return {"AAPL": 320193, "MSFT": 789019}

    def test_ok_cik_skipped(self, tmp_path, monkeypatch):
        """A CIK with status='ok' in manifest is NOT re-fetched."""
        monkeypatch.setattr(
            e8k, "config",
            type("C", (), {"data_dir": staticmethod(lambda: tmp_path)})(),
        )
        # Pre-populate manifest: AAPL already done
        manifest_data = {
            "320193": {"ticker": "AAPL", "status": "ok", "n_filings": 3,
                       "ts": "2026-07-01T00:00:00+00:00"},
        }
        mf_path = tmp_path / "edgar" / "earnings_8k_dates_manifest.json"
        mf_path.parent.mkdir(parents=True, exist_ok=True)
        mf_path.write_text(e8k.json.dumps(manifest_data))

        fetched_ciks = []

        def fake_fetch(ticker, cik):
            fetched_ciks.append(cik)
            return [], 0  # (rows, n_shards_missing)

        monkeypatch.setattr(e8k, "fetch_earnings_8k_for_cik", fake_fetch)
        monkeypatch.setattr(e8k, "build_cik_map", lambda tickers: self._cik_map())

        # Create a minimal eps_quarterly.parquet
        eps_path = tmp_path / "edgar" / "eps_quarterly.parquet"
        pd.DataFrame({"ticker": ["AAPL", "MSFT"]}).to_parquet(eps_path)

        e8k.run_backfill(force=False)

        # Only MSFT (cik 789019) should be fetched; AAPL (320193) is in manifest as 'ok'
        assert 320193 not in fetched_ciks
        assert 789019 in fetched_ciks

    def test_force_refetches_ok_cik(self, tmp_path, monkeypatch):
        """force=True causes even manifest-'ok' CIKs to be re-fetched."""
        monkeypatch.setattr(
            e8k, "config",
            type("C", (), {"data_dir": staticmethod(lambda: tmp_path)})(),
        )
        manifest_data = {
            "320193": {"ticker": "AAPL", "status": "ok", "n_filings": 3,
                       "ts": "2026-07-01T00:00:00+00:00"},
        }
        mf_path = tmp_path / "edgar" / "earnings_8k_dates_manifest.json"
        mf_path.parent.mkdir(parents=True, exist_ok=True)
        mf_path.write_text(e8k.json.dumps(manifest_data))

        fetched_ciks = []

        def fake_fetch(ticker, cik):
            fetched_ciks.append(cik)
            return [], 0  # (rows, n_shards_missing)

        monkeypatch.setattr(e8k, "fetch_earnings_8k_for_cik", fake_fetch)
        monkeypatch.setattr(e8k, "build_cik_map", lambda tickers: {"AAPL": 320193})

        eps_path = tmp_path / "edgar" / "eps_quarterly.parquet"
        eps_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"ticker": ["AAPL"]}).to_parquet(eps_path)

        e8k.run_backfill(force=True)
        assert 320193 in fetched_ciks


# ---------------------------------------------------------------------------
# compute_coverage
# ---------------------------------------------------------------------------

class TestComputeCoverage:
    def _make_df(self, rows):
        return pd.DataFrame(rows, columns=["ticker", "cik", "filing_date",
                                           "acceptance_datetime", "items"])

    def test_empty_df_fails_gate(self):
        cov = e8k.compute_coverage(pd.DataFrame())
        assert cov["gate_pass"] is False

    def test_pass_verdict(self):
        """900 tickers each with >8y span should PASS."""
        rows = []
        for i in range(900):
            ticker = f"T{i:04d}"
            rows.append((ticker, i + 1, "2010-01-15", "", "2.02"))
            rows.append((ticker, i + 1, "2020-01-15", "", "2.02"))
        df = self._make_df(rows)
        cov = e8k.compute_coverage(df)
        assert cov["gate_pass"] is True
        assert cov["gate_verdict"] == "PASS"
        assert cov["names_ge8y"] == 900

    def test_fail_verdict_insufficient_names(self):
        """Only 700 names with ≥8y — below threshold of 800."""
        rows = []
        for i in range(700):
            ticker = f"T{i:04d}"
            rows.append((ticker, i + 1, "2010-01-15", "", "2.02"))
            rows.append((ticker, i + 1, "2020-01-15", "", "2.02"))
        df = self._make_df(rows)
        cov = e8k.compute_coverage(df)
        assert cov["gate_pass"] is False
        assert cov["gate_verdict"] == "FAIL"

    def test_fail_verdict_insufficient_history(self):
        """800 names but only 5y of history each — below 8y threshold."""
        rows = []
        for i in range(800):
            ticker = f"T{i:04d}"
            rows.append((ticker, i + 1, "2015-01-15", "", "2.02"))
            rows.append((ticker, i + 1, "2019-06-15", "", "2.02"))  # ~4.4y
        df = self._make_df(rows)
        cov = e8k.compute_coverage(df)
        assert cov["gate_pass"] is False

    def test_coverage_counts_totals(self):
        rows = [
            ("AAPL", 1, "2010-01-15", "", "2.02"),
            ("AAPL", 1, "2020-01-15", "", "2.02"),
            ("MSFT", 2, "2015-01-15", "", "2.02"),
            ("MSFT", 2, "2018-01-15", "", "2.02"),  # ~3y only
        ]
        df = self._make_df(rows)
        cov = e8k.compute_coverage(df)
        assert cov["names_total"] == 2
        # AAPL has ~10y, MSFT has ~3y — only AAPL qualifies
        assert cov["names_ge8y"] == 1

    def test_gate_thresholds_in_output(self):
        cov = e8k.compute_coverage(pd.DataFrame())
        assert cov["gate_names_threshold"] == e8k.COVERAGE_GATE_NAMES
        assert cov["gate_years_threshold"] == e8k.COVERAGE_GATE_YEARS


# ---------------------------------------------------------------------------
# Regression: older-shard URL must use /submissions/ path (fix for 404 bug)
# ---------------------------------------------------------------------------

class TestOlderShardURL:
    """Regression tests: the URL built for older-filing shards must contain
    /submissions/ so the SEC EDGAR API returns 200 instead of 404.

    The submissions JSON older-files list returns bare filenames such as
    "CIK0000320193-submissions-001.json" (no leading path component).
    The correct URL is https://data.sec.gov/submissions/<fname>.
    The old buggy code produced https://data.sec.gov/<fname> which 404s.

    These tests do NOT make live network calls.
    """

    def test_older_shard_url_contains_submissions_path(self, monkeypatch):
        """URL passed to _sec_get_json for an older shard must contain /submissions/."""
        fetched_urls: list[str] = []

        def fake_get_json(url):
            fetched_urls.append(url)
            if "submissions-001" in url:
                # Return a minimal (empty) shard so fetch doesn't abort
                return {"form": [], "filingDate": [], "items": []}
            # Primary CIK URL returns a minimal response with one older shard
            return {
                "filings": {
                    "recent": {"form": [], "filingDate": [], "items": []},
                    "files": [{"name": "CIK0000320193-submissions-001.json"}],
                }
            }

        monkeypatch.setattr(e8k, "_sec_get_json", fake_get_json)
        monkeypatch.setattr(e8k.time, "sleep", lambda _: None)

        rows, n_shards_missing = e8k.fetch_earnings_8k_for_cik("AAPL", 320193)

        # At least one URL for the shard must have been constructed
        shard_urls = [u for u in fetched_urls if "submissions-001" in u]
        assert len(shard_urls) >= 1, "No shard URL was fetched"

        for url in shard_urls:
            assert "/submissions/" in url, (
                f"Older-shard URL does not contain /submissions/ — got: {url!r}\n"
                "This would cause a 404 because the SEC serves shards under "
                "https://data.sec.gov/submissions/<fname>, not https://data.sec.gov/<fname>"
            )

    def test_failed_shard_increments_missing_counter(self, monkeypatch):
        """A shard that returns None (404/error) increments n_shards_missing."""

        def fake_get_json(url):
            if "submissions-001" in url:
                return None  # simulated 404
            return {
                "filings": {
                    "recent": {"form": [], "filingDate": [], "items": []},
                    "files": [{"name": "CIK0000789019-submissions-001.json"}],
                }
            }

        monkeypatch.setattr(e8k, "_sec_get_json", fake_get_json)
        monkeypatch.setattr(e8k.time, "sleep", lambda _: None)

        rows, n_shards_missing = e8k.fetch_earnings_8k_for_cik("MSFT", 789019)
        assert n_shards_missing == 1

    def test_successful_shard_zero_missing(self, monkeypatch):
        """When all shards succeed, n_shards_missing is 0."""

        def fake_get_json(url):
            return {
                "filings": {
                    "recent": {"form": [], "filingDate": [], "items": []},
                    "files": [{"name": "CIK0000789019-submissions-001.json"}],
                }
            } if "CIK" in url and "submissions-001" not in url else {
                "form": [], "filingDate": [], "items": []
            }

        monkeypatch.setattr(e8k, "_sec_get_json", fake_get_json)
        monkeypatch.setattr(e8k.time, "sleep", lambda _: None)

        rows, n_shards_missing = e8k.fetch_earnings_8k_for_cik("MSFT", 789019)
        assert n_shards_missing == 0


# ---------------------------------------------------------------------------
# Deterministic same-day dedup (fix 4)
# ---------------------------------------------------------------------------

class TestDeterministicDedup:
    """Same-day dedup retains the row with the earliest acceptance_datetime."""

    def _make_df(self, rows):
        return pd.DataFrame(rows, columns=["ticker", "cik", "filing_date",
                                           "acceptance_datetime", "items"])

    def test_earliest_acceptance_kept_when_existing_is_earlier(self):
        """When existing row has earlier acceptance, it is kept after concat."""
        existing = self._make_df([
            ("AAPL", 320193, "2023-01-27", "2023-01-27T16:00:00.000Z", "2.02,9.01"),
        ])
        new_rows = [{"ticker": "AAPL", "cik": 320193, "filing_date": "2023-01-27",
                     "acceptance_datetime": "2023-01-27T21:30:00.000Z", "items": "2.02"}]
        result = e8k.append_and_dedup(existing, new_rows)
        assert len(result) == 1
        # Earliest acceptance should be kept
        assert result.iloc[0]["acceptance_datetime"] == "2023-01-27T16:00:00.000Z"

    def test_earliest_acceptance_kept_from_new_rows(self):
        """When new row has earlier acceptance, it is kept (existing is later)."""
        existing = self._make_df([
            ("AAPL", 320193, "2023-01-27", "2023-01-27T21:30:00.000Z", "2.02,9.01"),
        ])
        new_rows = [{"ticker": "AAPL", "cik": 320193, "filing_date": "2023-01-27",
                     "acceptance_datetime": "2023-01-27T16:00:00.000Z", "items": "2.02"}]
        result = e8k.append_and_dedup(existing, new_rows)
        assert len(result) == 1
        assert result.iloc[0]["acceptance_datetime"] == "2023-01-27T16:00:00.000Z"

    def test_empty_acceptance_datetime_sorts_last(self):
        """A row with empty acceptance_datetime sorts after one with a real value."""
        existing = self._make_df([
            ("AAPL", 320193, "2023-01-27", "", "2.02"),
        ])
        new_rows = [{"ticker": "AAPL", "cik": 320193, "filing_date": "2023-01-27",
                     "acceptance_datetime": "2023-01-27T16:00:00.000Z", "items": "2.02,9.01"}]
        result = e8k.append_and_dedup(existing, new_rows)
        assert len(result) == 1
        # The non-empty acceptance is earlier lexicographically → should be kept
        assert result.iloc[0]["acceptance_datetime"] == "2023-01-27T16:00:00.000Z"
