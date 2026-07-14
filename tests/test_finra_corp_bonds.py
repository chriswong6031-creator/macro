"""CCW-W5 tests: FINRA corporate bond breadth / sentiment / capped-volume collector.

Zero network calls — all HTTP is mocked via unittest.mock.

Covers:
  1. Token flow: _get_token acquires and caches; 1 retry on failure
  2. Absent-creds skip path: returns empty summary, no network calls
  3. Pagination + upsert: _fetch_paged_post pages correctly, frames concatenated
  4. Absent-creds env isolation: adapter skips when ID or SECRET missing
  5. Schema columns: breadth, sentiment, capped-volume store frames have expected columns
  6. Dedup: duplicate (date, productCategory) rows deduplicated to keep-last
  7. Incremental start-date logic: uses last stored date minus lookback
  8. HTTP 204 handling: no-data response stops pagination cleanly
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers: synthetic API response payloads
# ---------------------------------------------------------------------------

def _breadth_row(trade_date: str, category: str = "all securities") -> dict:
    return {
        "tradeReportDate": trade_date,
        "productCategory": category,
        "advances": 5000,
        "declines": 3000,
        "unchanged": 50,
        "totalTrades": 10000,
        "totalVolume": 35000.0,
        "fiftyTwoWeekHigh": 500,
        "fiftyTwoWeekLow": 100,
    }


def _sentiment_row(trade_date: str, category: str = "all securities",
                   trade_type: str = "all securities") -> dict:
    return {
        "tradeReportDate": trade_date,
        "productCategory": category,
        "tradeType": trade_type,
        "totalVolume": 12000.0,
        "totalTrades": 5000,
        "totalTransactions": 8000,
    }


def _capped_row(trade_year: int, trade_month: int, grade: str = "IG",
                flag: str = "N") -> dict:
    return {
        "tradeReportDate": f"{trade_year}-{trade_month:02d}-01",
        "tradeYear": trade_year,
        "tradeMonth": trade_month,
        "gradeCode": grade,
        "144AFlag": flag,
        "totalTradeCount": 15000,
        "totalVolumeQuantity": 50000000.0,
    }


def _make_response(data: Any, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    if status_code == 204:
        mock_resp.json.side_effect = ValueError("no content")
    else:
        mock_resp.json.return_value = data
    mock_resp.raise_for_status.return_value = None
    mock_resp.text = str(data)[:200]
    return mock_resp


def _make_token_response() -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "MOCK_TOKEN_XYZ", "expires_in": 43169}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.finra_corp_bonds import (
    BREADTH_HISTORY_START,
    INCREMENTAL_LOOKBACK_DAYS,
    FinraCorpBondsAdapter,
)


# ---------------------------------------------------------------------------
# 1. Absent-creds skip path
# ---------------------------------------------------------------------------

class TestAbsentCredsSkip:
    def test_skip_when_both_creds_absent(self, monkeypatch):
        """fetch() returns empty summary and logs INFO when no env creds."""
        monkeypatch.delenv("FINRA_API_CLIENT_ID", raising=False)
        monkeypatch.delenv("FINRA_API_CLIENT_SECRET", raising=False)

        adapter = FinraCorpBondsAdapter()
        with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
            result = adapter.fetch()

        mock_post.assert_not_called()
        mock_get.assert_not_called()
        assert "finra_corp_bonds_runs" in result
        assert "skipped" in result["finra_corp_bonds_runs"].columns

    def test_skip_when_id_absent(self, monkeypatch):
        monkeypatch.delenv("FINRA_API_CLIENT_ID", raising=False)
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "dummy_secret")
        adapter = FinraCorpBondsAdapter()
        with patch("requests.post") as mock_post:
            result = adapter.fetch()
        mock_post.assert_not_called()
        assert "finra_corp_bonds_runs" in result

    def test_skip_when_secret_absent(self, monkeypatch):
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "dummy_id")
        monkeypatch.delenv("FINRA_API_CLIENT_SECRET", raising=False)
        adapter = FinraCorpBondsAdapter()
        with patch("requests.post") as mock_post:
            result = adapter.fetch()
        mock_post.assert_not_called()
        assert "finra_corp_bonds_runs" in result


# ---------------------------------------------------------------------------
# 2. Token acquisition: caching + 1 retry
# ---------------------------------------------------------------------------

class TestTokenFlow:
    def test_token_acquired_on_first_call(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "test_id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "test_secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

        adapter = FinraCorpBondsAdapter()
        assert adapter._token is None

        with patch("requests.post", return_value=_make_token_response()):
            tok = adapter._get_token()

        assert tok == "MOCK_TOKEN_XYZ"
        assert adapter._token == "MOCK_TOKEN_XYZ"

    def test_token_cached_on_second_call(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "test_id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "test_secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

        adapter = FinraCorpBondsAdapter()
        import time
        adapter._token = "CACHED_TOKEN"
        adapter._token_expires_at = time.monotonic() + 10000  # not expired

        with patch("requests.post") as mock_post:
            tok = adapter._get_token()

        mock_post.assert_not_called()
        assert tok == "CACHED_TOKEN"

    def test_token_retry_on_first_failure(self, monkeypatch, tmp_path):
        """If first token POST fails, second attempt succeeds."""
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "test_id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "test_secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

        adapter = FinraCorpBondsAdapter()
        fail_resp = MagicMock()
        fail_resp.raise_for_status.side_effect = Exception("connection error")

        with patch("requests.post", side_effect=[Exception("network fail"), _make_token_response()]):
            with patch("time.sleep"):  # suppress the retry sleep
                tok = adapter._get_token()

        assert tok == "MOCK_TOKEN_XYZ"

    def test_token_raises_after_two_failures(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "test_id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "test_secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

        adapter = FinraCorpBondsAdapter()

        with patch("requests.post", side_effect=Exception("fail")):
            with patch("time.sleep"):
                with pytest.raises(RuntimeError, match="token acquisition failed"):
                    adapter._get_token()

    def test_token_never_logged(self, monkeypatch, tmp_path, caplog):
        """Token value must not appear in log output."""
        import logging
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "test_id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "test_secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

        adapter = FinraCorpBondsAdapter()
        with caplog.at_level(logging.DEBUG, logger="collectors.finra_corp_bonds"):
            with patch("requests.post", return_value=_make_token_response()):
                adapter._get_token()

        for record in caplog.records:
            assert "MOCK_TOKEN_XYZ" not in record.getMessage(), \
                f"Token value leaked into log: {record.getMessage()}"


# ---------------------------------------------------------------------------
# 3. Pagination logic: _fetch_paged_post
# ---------------------------------------------------------------------------

class TestPaginationPost:
    def _make_adapter(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "test_id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "test_secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        adapter = FinraCorpBondsAdapter()
        adapter._token = "MOCK_TOKEN"
        import time
        adapter._token_expires_at = time.monotonic() + 10000
        return adapter

    def test_single_page_returned(self, monkeypatch, tmp_path):
        adapter = self._make_adapter(monkeypatch, tmp_path)

        page = [_breadth_row("2026-07-01"), _breadth_row("2026-07-01", "investment grade")]
        mock_resp = _make_response(page)

        with patch("requests.post", return_value=mock_resp), patch("time.sleep"):
            frames = adapter._fetch_paged_post(
                dataset="corporateMarketBreadth",
                date_field="tradeReportDate",
                start_date="2026-07-01",
                end_date="2026-07-01",
            )

        assert len(frames) == 1
        assert len(frames[0]) == 2

    def test_204_response_stops_pagination(self, monkeypatch, tmp_path):
        adapter = self._make_adapter(monkeypatch, tmp_path)

        with patch("requests.post", return_value=_make_response([], 204)), patch("time.sleep"):
            frames = adapter._fetch_paged_post(
                dataset="corporateMarketBreadth",
                date_field="tradeReportDate",
                start_date="2026-07-01",
                end_date="2026-07-01",
            )

        assert frames == []

    def test_multi_window_pagination(self, monkeypatch, tmp_path):
        """A date range >90 days should split into multiple 90-day windows."""
        adapter = self._make_adapter(monkeypatch, tmp_path)

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            body = kwargs.get("json", {})
            filters = body.get("dateRangeFilters", [{}])
            start = filters[0].get("startDate", "")
            # Return one row per window call, 204 for second call within same window
            return _make_response([_breadth_row(start if start else "2026-01-01")])

        with patch("requests.post", side_effect=side_effect), patch("time.sleep"):
            frames = adapter._fetch_paged_post(
                dataset="corporateMarketBreadth",
                date_field="tradeReportDate",
                start_date="2025-01-01",
                end_date="2025-06-01",  # > 90 days → at least 2 windows
            )

        # Should have called for at least 2 windows (Jan-Apr, Apr-Jun)
        assert call_count >= 2
        assert len(frames) >= 2

    def test_page_size_triggers_next_offset(self, monkeypatch, tmp_path):
        """When a page returns PAGE_LIMIT rows, the next offset must be requested."""
        from collectors.finra_corp_bonds import PAGE_LIMIT
        adapter = self._make_adapter(monkeypatch, tmp_path)

        # First call returns PAGE_LIMIT rows; second call (offset=PAGE_LIMIT) returns empty → stop
        full_page = [_breadth_row("2026-07-01")] * PAGE_LIMIT
        empty_page: list = []

        responses = [_make_response(full_page), _make_response(empty_page)]
        call_idx = 0

        def side_effect(*args, **kwargs):
            nonlocal call_idx
            resp = responses[min(call_idx, len(responses) - 1)]
            call_idx += 1
            return resp

        with patch("requests.post", side_effect=side_effect), patch("time.sleep"):
            frames = adapter._fetch_paged_post(
                dataset="corporateMarketBreadth",
                date_field="tradeReportDate",
                start_date="2026-07-01",
                end_date="2026-07-01",
            )

        assert call_idx >= 2, "Expected at least 2 POST calls (page 1 full, page 2 empty)"
        assert len(frames[0]) == PAGE_LIMIT


# ---------------------------------------------------------------------------
# 4. _write_long_parquet: correct columns and dedup in stored parquet
# ---------------------------------------------------------------------------

class TestWriteLongParquet:
    def _make_adapter(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        return FinraCorpBondsAdapter()

    def test_breadth_parquet_has_expected_columns(self, monkeypatch, tmp_path):
        adapter = self._make_adapter(monkeypatch, tmp_path)
        rows = [_breadth_row("2026-07-01", cat)
                for cat in ["all securities", "investment grade", "high yield", "convertibles"]]
        df = pd.DataFrame(rows)
        df["tradeReportDate"] = "2026-07-01"
        n = adapter._write_long_parquet("finra_breadth_test", df,
                                        key_cols=["tradeReportDate", "productCategory"])
        assert n == 4
        saved = pd.read_parquet(tmp_path / "corp_bonds" / "finra_breadth_test.parquet")
        assert "productCategory" in saved.columns
        assert "advances" in saved.columns
        assert "declines" in saved.columns
        assert len(saved) == 4

    def test_sentiment_parquet_has_expected_columns(self, monkeypatch, tmp_path):
        adapter = self._make_adapter(monkeypatch, tmp_path)
        rows = [_sentiment_row("2026-07-01", cat, tt)
                for cat in ["all securities", "high yield"]
                for tt in ["customer buy", "customer sell", "all securities"]]
        df = pd.DataFrame(rows)
        n = adapter._write_long_parquet("finra_sentiment_test", df,
                                        key_cols=["tradeReportDate", "productCategory", "tradeType"])
        saved = pd.read_parquet(tmp_path / "corp_bonds" / "finra_sentiment_test.parquet")
        assert "productCategory" in saved.columns
        assert "tradeType" in saved.columns
        assert "totalVolume" in saved.columns
        assert len(saved) == 6

    def test_capped_volume_parquet_has_key_cols(self, monkeypatch, tmp_path):
        adapter = self._make_adapter(monkeypatch, tmp_path)
        rows = [_capped_row(2023, 12, g, f)
                for g in ["IG", "HY"] for f in ["N", "Y"]]
        df = pd.DataFrame(rows)
        df["tradeReportDate"] = [f"2024-01-01"] * 4
        n = adapter._write_long_parquet("finra_capped_test", df,
                                        key_cols=["tradeReportDate", "gradeCode", "144AFlag"])
        saved = pd.read_parquet(tmp_path / "corp_bonds" / "finra_capped_test.parquet")
        assert "gradeCode" in saved.columns
        assert "144AFlag" in saved.columns
        assert len(saved) == 4


# ---------------------------------------------------------------------------
# 5. Write preserves all rows per date (multi-row-per-date correctness)
# ---------------------------------------------------------------------------

class TestMultiRowPerDate:
    def test_four_categories_preserved(self, monkeypatch, tmp_path):
        """Writing 4 productCategory rows for one date must keep all 4 (not collapse to 1)."""
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        adapter = FinraCorpBondsAdapter()

        categories = ["all securities", "investment grade", "high yield", "convertibles"]
        rows = [_breadth_row("2026-07-01", cat) for cat in categories]
        df = pd.DataFrame(rows)
        n = adapter._write_long_parquet("test_multi", df,
                                        key_cols=["tradeReportDate", "productCategory"])
        saved = pd.read_parquet(tmp_path / "corp_bonds" / "test_multi.parquet")
        assert len(saved) == 4, f"Expected 4 rows (one per category), got {len(saved)}"
        assert set(saved["productCategory"].tolist()) == set(categories)


# ---------------------------------------------------------------------------
# 6. Write upsert: new rows win on same composite key
# ---------------------------------------------------------------------------

class TestWriteUpsert:
    def test_new_wins_on_same_key(self, monkeypatch, tmp_path):
        """Second write with same (date, category) key must keep new value."""
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        adapter = FinraCorpBondsAdapter()

        row_v1 = {**_breadth_row("2026-07-01", "all securities"), "advances": 1000}
        df1 = pd.DataFrame([row_v1])
        adapter._write_long_parquet("test_upsert", df1,
                                    key_cols=["tradeReportDate", "productCategory"])

        row_v2 = {**_breadth_row("2026-07-01", "all securities"), "advances": 9999}
        df2 = pd.DataFrame([row_v2])
        adapter._write_long_parquet("test_upsert", df2,
                                    key_cols=["tradeReportDate", "productCategory"])

        saved = pd.read_parquet(tmp_path / "corp_bonds" / "test_upsert.parquet")
        assert len(saved) == 1
        assert int(saved["advances"].iloc[0]) == 9999

    def test_old_rows_outside_window_kept(self, monkeypatch, tmp_path):
        """Old rows for dates NOT in the new fetch must be preserved."""
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        adapter = FinraCorpBondsAdapter()

        df_old = pd.DataFrame([_breadth_row("2026-01-01", "all securities")])
        adapter._write_long_parquet("test_keep_old", df_old,
                                    key_cols=["tradeReportDate", "productCategory"])

        df_new = pd.DataFrame([_breadth_row("2026-07-01", "all securities")])
        adapter._write_long_parquet("test_keep_old", df_new,
                                    key_cols=["tradeReportDate", "productCategory"])

        saved = pd.read_parquet(tmp_path / "corp_bonds" / "test_keep_old.parquet")
        assert len(saved) == 2
        dates = set(saved["tradeReportDate"].tolist())
        assert "2026-01-01" in dates
        assert "2026-07-01" in dates


# ---------------------------------------------------------------------------
# 7. Dedup logic: duplicate (date, productCategory) → keep-last (inline)
# ---------------------------------------------------------------------------

class TestDedupBreadth:
    def test_dedup_keeps_last(self):
        """Raw frame dedup applied before _write_long_parquet must keep latest row."""
        rows = [
            {**_breadth_row("2026-07-01", "all securities"), "advances": 1000},
            {**_breadth_row("2026-07-01", "all securities"), "advances": 9999},  # keep this
        ]
        df = pd.DataFrame(rows)
        df["tradeReportDate"] = pd.to_datetime(df["tradeReportDate"]).dt.date.astype(str)
        df = (
            df.sort_values("tradeReportDate")
              .drop_duplicates(subset=["tradeReportDate", "productCategory"], keep="last")
              .reset_index(drop=True)
        )
        assert len(df) == 1
        assert df["advances"].iloc[0] == 9999


# ---------------------------------------------------------------------------
# 8. Incremental start-date logic
# ---------------------------------------------------------------------------

class TestIncrementalStart:
    def _make_adapter(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        return FinraCorpBondsAdapter()

    def test_full_history_returns_history_start(self, monkeypatch, tmp_path):
        adapter = self._make_adapter(monkeypatch, tmp_path)
        start = adapter._incremental_start(
            "finra_corporateMarketBreadth", BREADTH_HISTORY_START, full_history=True
        )
        assert start == BREADTH_HISTORY_START

    def test_no_stored_data_returns_history_start(self, monkeypatch, tmp_path):
        adapter = self._make_adapter(monkeypatch, tmp_path)
        # No parquet on disk → _last_stored_date returns None
        start = adapter._incremental_start(
            "finra_corporateMarketBreadth", BREADTH_HISTORY_START, full_history=False
        )
        assert start == BREADTH_HISTORY_START

    def test_with_stored_date_uses_lookback(self, monkeypatch, tmp_path):
        adapter = self._make_adapter(monkeypatch, tmp_path)

        stored_last = date(2026, 7, 10)

        with patch.object(adapter, "_last_stored_date", return_value=stored_last):
            start = adapter._incremental_start(
                "finra_corporateMarketBreadth", BREADTH_HISTORY_START, full_history=False
            )

        expected = (stored_last - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)).isoformat()
        assert start == expected


# ---------------------------------------------------------------------------
# 8b. B1: cappedVolume date derivation always uses tradeYear/tradeMonth
# ---------------------------------------------------------------------------

class TestCappedVolumeDateDerivation:
    """B1 regression: API tradeReportDate is +1-year-corrupt; must derive from tradeYear/tradeMonth."""

    def _make_adapter(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)
        return FinraCorpBondsAdapter()

    def test_api_corrupt_date_overwritten_by_year_month(self, monkeypatch, tmp_path):
        """A raw API row with tradeYear=2023, tradeMonth=1, tradeReportDate='2024-01-01'
        must be stored as tradeReportDate='2023-01-01' (year-month derivation wins)."""
        adapter = self._make_adapter(monkeypatch, tmp_path)

        # Synthetic API row that mimics the observed +1-year shift corruption
        corrupt_row = {
            "tradeReportDate": "2024-01-01",  # API field: +1-year shifted (corrupt)
            "tradeYear": 2023,
            "tradeMonth": 1,
            "gradeCode": "IG",
            "144AFlag": "N",
            "totalTradeCount": 100,
            "totalVolumeQuantity": 1_000_000.0,
        }
        df_api = pd.DataFrame([corrupt_row])

        # Replicate the normalization logic from _collect_capped_volume
        df_api["tradeReportDate"] = (
            df_api["tradeYear"].astype(str)
            + "-"
            + df_api["tradeMonth"].astype(str).str.zfill(2)
            + "-01"
        )

        assert df_api["tradeReportDate"].iloc[0] == "2023-01-01", (
            f"Expected '2023-01-01' but got '{df_api['tradeReportDate'].iloc[0]}'; "
            "the B1 fix must unconditionally derive tradeReportDate from tradeYear/tradeMonth"
        )

    def test_collect_capped_volume_stores_correct_dates(self, monkeypatch, tmp_path):
        """End-to-end via _collect_capped_volume: corrupt API tradeReportDate stored as 2023-01-01."""
        adapter = self._make_adapter(monkeypatch, tmp_path)
        adapter._token = "MOCK"
        import time as _time
        adapter._token_expires_at = _time.monotonic() + 10000

        # Simulate the exact API corruption: tradeYear=2023, tradeMonth=1 → "2024-01-01"
        corrupt_api_rows = [
            {
                "tradeReportDate": "2024-01-01",  # +1-year corrupt from API
                "tradeYear": 2023,
                "tradeMonth": 1,
                "gradeCode": "IG",
                "144AFlag": "N",
                "totalTradeCount": 100,
                "totalVolumeQuantity": 5_000_000.0,
            },
            {
                "tradeReportDate": "2024-01-01",  # same corrupt date for the HY row
                "tradeYear": 2023,
                "tradeMonth": 1,
                "gradeCode": "HY",
                "144AFlag": "N",
                "totalTradeCount": 50,
                "totalVolumeQuantity": 2_000_000.0,
            },
        ]

        with patch("requests.get", return_value=_make_response(corrupt_api_rows)), \
             patch("time.sleep"):
            n = adapter._collect_capped_volume(full_history=True)

        assert n == 2

        saved = pd.read_parquet(tmp_path / "corp_bonds" / "finra_corporatesAndAgenciesCappedVolume.parquet")
        stored_dates = saved["tradeReportDate"].tolist()
        assert all(d == "2023-01-01" for d in stored_dates), (
            f"B1 fix failed: expected all dates to be '2023-01-01' but got {stored_dates}"
        )
        assert "2024-01-01" not in stored_dates, (
            "B1 fix failed: corrupt API date '2024-01-01' leaked into the store"
        )


# ---------------------------------------------------------------------------
# 9. Full fetch() integration (mocked end-to-end)
# ---------------------------------------------------------------------------

class TestFetchIntegration:
    def test_fetch_returns_summary_frame(self, monkeypatch, tmp_path):
        """fetch() with creds present and successful network calls → summary DataFrame."""
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "test_id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "test_secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

        breadth_page = [_breadth_row("2026-07-01", cat) for cat in
                        ["all securities", "investment grade", "high yield", "convertibles"]]
        sentiment_page = [_sentiment_row("2026-07-01", cat, tt)
                          for cat in ["all securities", "investment grade"]
                          for tt in ["all securities", "customer buy", "customer sell",
                                     "affiliate buy", "affiliate sell", "inter-dealer"]]
        capped_page = [_capped_row(2023, 12, g, f)
                       for g in ["IG", "HY", "AGCY"] for f in ["N", "Y"]]

        def post_side_effect(url, **kwargs):
            if "access_token" in url:
                return _make_token_response()
            # corporateMarketBreadth or corporateMarketSentiment POST
            if "corporateMarketBreadth" in url:
                body = kwargs.get("json", {})
                if body.get("dateRangeFilters"):
                    return _make_response(breadth_page)
                return _make_response(breadth_page)
            if "corporateMarketSentiment" in url:
                return _make_response(sentiment_page)
            return _make_response([], 204)

        def get_side_effect(url, **kwargs):
            if "corporatesAndAgenciesCappedVolume" in url:
                return _make_response(capped_page)
            return _make_response([])

        with patch("requests.post", side_effect=post_side_effect), \
             patch("requests.get", side_effect=get_side_effect), \
             patch("time.sleep"):
            result = adapter = FinraCorpBondsAdapter()
            result = adapter.fetch()

        assert "finra_corp_bonds_runs" in result
        summary = result["finra_corp_bonds_runs"]
        assert isinstance(summary, pd.DataFrame)
        # Should not have 'skipped' column (that's the absent-creds path)
        assert "skipped" not in summary.columns

    def test_one_dataset_failure_does_not_kill_run(self, monkeypatch, tmp_path):
        """If breadth fails, sentiment and capped-volume still run."""
        monkeypatch.setenv("FINRA_API_CLIENT_ID", "test_id")
        monkeypatch.setenv("FINRA_API_CLIENT_SECRET", "test_secret")
        monkeypatch.setattr("lib.config.data_dir", lambda: tmp_path)

        adapter = FinraCorpBondsAdapter()
        adapter._token = "MOCK"
        import time as _time
        adapter._token_expires_at = _time.monotonic() + 10000

        sentinel = {}

        original_collect_breadth = adapter._collect_breadth
        original_collect_sentiment = adapter._collect_sentiment
        original_collect_capped = adapter._collect_capped_volume

        def fail_breadth(**kwargs):
            raise RuntimeError("Simulated breadth failure")

        def ok_sentiment(**kwargs):
            sentinel["sentiment"] = True
            return 0

        def ok_capped(**kwargs):
            sentinel["capped"] = True
            return 0

        adapter._collect_breadth = fail_breadth
        adapter._collect_sentiment = ok_sentiment
        adapter._collect_capped_volume = ok_capped

        result = adapter.fetch()

        # Run did not raise; both remaining datasets were called
        assert sentinel.get("sentiment"), "Sentiment was not called after breadth failure"
        assert sentinel.get("capped"), "CappedVolume was not called after breadth failure"
        assert "finra_corp_bonds_runs" in result
