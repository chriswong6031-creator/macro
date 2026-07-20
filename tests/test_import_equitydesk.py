"""Tests for scripts/import_equitydesk_full.py.

Uses a tiny synthetic fixture under tests/fixtures/ed_mini/ that mirrors
the real EquityDesk JSON shape.  The importer is patched to point at the
fixture directory and a fresh tmp output dir so it never touches the real
data/stage_analysis/backfill/ tree (MM_DATA_GUARD compliance).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixture directory
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ed_mini"


def _make_fixtures() -> None:
    """Create the minimal synthetic fixture files (idempotent)."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # overview_combined_table.json — 3 rows
    overview = [
        {
            "id": "aaa",
            "ticker": "AAPL",
            "region": "N.Amer",
            "name_ui": "Apple Inc",
            "gics_industry": "Technology Hardware",
            "gics_sub_industry": "Technology Hardware, Storage & Peripherals",
            "gics_industry_group": "Tech Hardware & Equipment",
            "gics_sector": "Information Technology",
            "tradingview_code": "NASDAQ:AAPL",
            "sata_score": 8.5,
            "sata_change_1w": 0.2,
            "stage_flag": "2X",
            "stage_detailed": "2X Bullish",
            "weeks_in_stage": 12,
            "mansfield_rs": 1.15,
            "mansfield_rs_change": 0.05,
            "atr_14w": 8.4,
            "industry_percentile": 82.0,
            "sub_industry_percentile": 78.0,
            "industry_bucket": "A",
            "atr_ext": 1.2,
            "close": 195.0,
            "sma_30w": 182.0,
            "stage_date": "2026-07-14",
            "earnings_call_sent": 26,
            "earnings_call_perf": 3,
            "earnings_call_combined": 29,
            "call_date": "2026-05-01",
            "analysts_count": 12,
            "questions_count": 28,
            "positive_highlights": "Strong services growth",
            "negative_highlights": "iPhone unit declines",
            "earnings_call_pop": 4.5,
            "combined_rating": 87.0,
            "level1_tags": "[\"services\",\"ai\"]",
            "level2_tags": "[\"iphone\",\"app_store\"]",
            "created_at": "2026-07-14T00:00:00Z",
            "updated_at": "2026-07-14T00:00:00Z",
            "as_of_date": "2026-07-14",
        },
        {
            "id": "bbb",
            "ticker": "MSFT",
            "region": "N.Amer",
            "name_ui": "Microsoft Corp",
            "gics_industry": "Systems Software",
            "gics_sub_industry": "Systems Software",
            "gics_industry_group": "Software & Services",
            "gics_sector": "Information Technology",
            "tradingview_code": "NASDAQ:MSFT",
            "sata_score": 7.8,
            "sata_change_1w": -0.1,
            "stage_flag": "2X",
            "stage_detailed": "2X Catch",
            "weeks_in_stage": 3,
            "mansfield_rs": 0.98,
            "mansfield_rs_change": 0.02,
            "atr_14w": 10.2,
            "industry_percentile": 70.0,
            "sub_industry_percentile": 65.0,
            "industry_bucket": "B",
            "atr_ext": 0.5,
            "close": 430.0,
            "sma_30w": 415.0,
            "stage_date": "2026-07-14",
            "earnings_call_sent": 24,
            "earnings_call_perf": 2,
            "earnings_call_combined": 26,
            "call_date": "2026-04-29",
            "analysts_count": 15,
            "questions_count": 32,
            "positive_highlights": "Azure growth acceleration",
            "negative_highlights": "Capex guidance raised",
            "earnings_call_pop": 2.1,
            "combined_rating": 80.0,
            "level1_tags": "[\"cloud\",\"ai\"]",
            "level2_tags": "[\"azure\",\"copilot\"]",
            "created_at": "2026-07-14T00:00:00Z",
            "updated_at": "2026-07-14T00:00:00Z",
            "as_of_date": "2026-07-14",
        },
        {
            "id": "ccc",
            "ticker": "GOOGL",
            "region": "N.Amer",
            "name_ui": "Alphabet Inc",
            "gics_industry": "Interactive Media & Services",
            "gics_sub_industry": "Interactive Media & Services",
            "gics_industry_group": "Media & Entertainment",
            "gics_sector": "Communication Services",
            "tradingview_code": "NASDAQ:GOOGL",
            "sata_score": 6.2,
            "sata_change_1w": 0.5,
            "stage_flag": "1X",
            "stage_detailed": "1X",
            "weeks_in_stage": 5,
            "mansfield_rs": 0.85,
            "mansfield_rs_change": -0.08,
            "atr_14w": 9.1,
            "industry_percentile": 60.0,
            "sub_industry_percentile": 55.0,
            "industry_bucket": "C",
            "atr_ext": -0.3,
            "close": 178.0,
            "sma_30w": 180.0,
            "stage_date": "2026-07-14",
            "earnings_call_sent": 22,
            "earnings_call_perf": -1,
            "earnings_call_combined": 21,
            "call_date": "2026-04-29",
            "analysts_count": 14,
            "questions_count": 25,
            "positive_highlights": "Search stable",
            "negative_highlights": "YouTube ad weakness",
            "earnings_call_pop": -1.2,
            "combined_rating": 65.0,
            "level1_tags": "[\"advertising\",\"ai\"]",
            "level2_tags": "[\"search\",\"youtube\"]",
            "created_at": "2026-07-14T00:00:00Z",
            "updated_at": "2026-07-14T00:00:00Z",
            "as_of_date": "2026-07-14",
        },
    ]
    (FIXTURES_DIR / "overview_combined_table.json").write_text(
        json.dumps(overview), encoding="utf-8"
    )

    # stageanalysis_stock_sata_stage_rs_ui_all_data.json — 2 rows
    stage = [
        {
            "id": "s1",
            "ticker": "AAPL",
            "tickerb": "AAPL:US",
            "ticker_tradingview": "NASDAQ:AAPL",
            "region": "N.Amer",
            "name_ui": "Apple Inc",
            "date": "2026-07-14",
            "sata_score": 8.5,
            "sata_score_prev": 8.3,
            "sata_change_1w": 0.2,
            "stage_flag": "2X",
            "stage_detailed": "2X Bullish",
            "weeks_in_stage": 12,
            "is_stage2_start": False,
            "breakout_confirmed": True,
            "stage_changed": False,
            "rs_ratio": 1.15,
            "rs_trend_52w": "up",
            "mansfield_rs": 1.15,
            "mansfield_rs_change": 0.05,
            "mansfield_rs_change_rel": 0.04,
            "atr_14w": 8.4,
            "atr_ext": 1.2,
            "close": 195.0,
            "sma_30w": 182.0,
            "week_end": "2026-07-14",
            "industry_id": "IT_HW",
            "industry_name": "Technology Hardware",
            "industry_percentile": 82.0,
            "industry_label": "Leader",
            "industry_bucket": "A",
            "sub_industry_id": "IT_HW_ST",
            "sub_industry_name": "Tech Hardware, Storage & Peripherals",
            "sub_industry_percentile": 78.0,
            "sub_industry_label": "Leader",
            "sub_industry_bucket": "A",
            "gics_industry": "Technology Hardware, Storage & Peripherals",
            "gics_sub_industry": "Technology Hardware, Storage & Peripherals",
            "data_as_of_date": "2026-07-14",
            "created_at": "2026-07-14T00:00:00Z",
            "updated_at": "2026-07-14T00:00:00Z",
        },
        {
            "id": "s2",
            "ticker": "MSFT",
            "tickerb": "MSFT:US",
            "ticker_tradingview": "NASDAQ:MSFT",
            "region": "N.Amer",
            "name_ui": "Microsoft Corp",
            "date": "2026-07-14",
            "sata_score": 7.8,
            "sata_score_prev": 7.9,
            "sata_change_1w": -0.1,
            "stage_flag": "2X",
            "stage_detailed": "2X Catch",
            "weeks_in_stage": 3,
            "is_stage2_start": True,
            "breakout_confirmed": False,
            "stage_changed": True,
            "rs_ratio": 0.98,
            "rs_trend_52w": "flat",
            "mansfield_rs": 0.98,
            "mansfield_rs_change": 0.02,
            "mansfield_rs_change_rel": 0.02,
            "atr_14w": 10.2,
            "atr_ext": 0.5,
            "close": 430.0,
            "sma_30w": 415.0,
            "week_end": "2026-07-14",
            "industry_id": "SW",
            "industry_name": "Systems Software",
            "industry_percentile": 70.0,
            "industry_label": "Above Average",
            "industry_bucket": "B",
            "sub_industry_id": "SW_SYS",
            "sub_industry_name": "Systems Software",
            "sub_industry_percentile": 65.0,
            "sub_industry_label": "Above Average",
            "sub_industry_bucket": "B",
            "gics_industry": "Systems Software",
            "gics_sub_industry": "Systems Software",
            "data_as_of_date": "2026-07-14",
            "created_at": "2026-07-14T00:00:00Z",
            "updated_at": "2026-07-14T00:00:00Z",
        },
    ]
    (FIXTURES_DIR / "stageanalysis_stock_sata_stage_rs_ui_all_data.json").write_text(
        json.dumps(stage), encoding="utf-8"
    )
    # weekly view identical for fixture purposes
    (FIXTURES_DIR / "stageanalysis_stock_sata_stage_rs_ui_all_data_weekly_view.json").write_text(
        json.dumps(stage), encoding="utf-8"
    )

    # earnings_call_data.json — 2 rows (includes text cols)
    ec = [
        {
            "id": "e1",
            "document_ticker": "AAPL",
            "company_ticker": "AAPL US",
            "company_name": "Apple Inc",
            "fiscal_quarter": 2,
            "fiscal_year": 2026,
            "call_date": "2026-05-01",
            "gics_sector": "Information Technology",
            "gics_industry_group": "Technology Hardware & Equipment",
            "gics_industry": "Technology Hardware, Storage & Peripherals",
            "gics_subindustry": "Technology Hardware, Storage & Peripherals",
            "earnings_call_sent": 26,
            "earnings_call_perf": 3,
            "earnings_call_combined": 29,
            "earnings_call_pop": 4.5,
            "call_positivity_score": 9,
            "management_confidence_score": 9,
            "analyst_criticism_score": 1,
            "future_outlook_score": 9,
            "revenue_growth": 5.1,
            "eps_growth": 8.2,
            "gross_margin": 46.3,
            "positive_highlights": "Services revenue hit record",
            "negative_highlights": "iPhone unit declines",
            "key_quote": "We are investing heavily in AI",
            "level1_tags": "[\"services\",\"ai\"]",
            "level2_tags": "[\"iphone\",\"app_store\"]",
            "file_path": None,
            "summary": "Strong quarter driven by services.",
            "unified_analysis": {"meta": {"sector": "IT"}, "tags": ["services"]},
            "created_at": "2026-05-02T00:00:00Z",
            "updated_at": "2026-05-02T00:00:00Z",
        },
        {
            "id": "e2",
            "document_ticker": "MSFT",
            "company_ticker": "MSFT US",
            "company_name": "Microsoft Corp",
            "fiscal_quarter": 3,
            "fiscal_year": 2026,
            "call_date": "2026-04-29",
            "gics_sector": "Information Technology",
            "gics_industry_group": "Software & Services",
            "gics_industry": "Systems Software",
            "gics_subindustry": "Systems Software",
            "earnings_call_sent": 24,
            "earnings_call_perf": 2,
            "earnings_call_combined": 26,
            "earnings_call_pop": 2.1,
            "call_positivity_score": 8,
            "management_confidence_score": 8,
            "analyst_criticism_score": 2,
            "future_outlook_score": 8,
            "revenue_growth": 13.5,
            "eps_growth": 18.0,
            "gross_margin": 70.1,
            "positive_highlights": "Azure grew 35%",
            "negative_highlights": "Capex elevated",
            "key_quote": "AI is becoming embedded in everything",
            "level1_tags": "[\"cloud\",\"ai\"]",
            "level2_tags": "[\"azure\",\"copilot\"]",
            "file_path": None,
            "summary": "Azure driving upside.",
            "unified_analysis": {"meta": {"sector": "IT"}, "tags": ["cloud"]},
            "created_at": "2026-04-30T00:00:00Z",
            "updated_at": "2026-04-30T00:00:00Z",
        },
    ]
    (FIXTURES_DIR / "earnings_call_data.json").write_text(
        json.dumps(ec), encoding="utf-8"
    )

    # industry_flows.json — 2 rows
    flows = [
        {
            "id": "f1",
            "region": "N.Amer",
            "as_of_date": "2026-07-14",
            "lookback_start_date": "2026-06-14",
            "lookback_days": 30,
            "industry_id": "IT_HW",
            "industry_name": "Technology Hardware",
            "n": 42,
            "rs_chg_4w_base_n": 40,
            "sata_mean": 7.2,
            "rs_chg_4w_median": 0.12,
            "rs_chg_1w_median": 0.03,
            "breadth_4w_pct": 0.62,
            "stage2_stage4_ratio": 4.5,
            "stage2_count": 27,
            "stage4_count": 6,
            "fresh_stage2_count": 4,
            "fresh_stage4_count": 1,
            "fresh_stage2_pct": 0.09,
            "fresh_stage4_pct": 0.02,
            "stage2_median_age_wks": 10,
            "state": "accumulation",
            "turn_flag": False,
            "formula_version": "v1",
            "created_at": "2026-07-14T00:00:00Z",
        },
    ]
    (FIXTURES_DIR / "industry_flows.json").write_text(
        json.dumps(flows), encoding="utf-8"
    )

    # stageanalysis_industry_ranks_weekly.json — 1 row
    ranks = [
        {
            "region": "N.Amer",
            "industry_id": "IT_HW",
            "industry_name": "Technology Hardware",
            "as_of_date": "2026-07-14",
            "score": 8.1,
            "rank": 3,
            "bucket": "A",
            "z_rsroc": 1.2,
            "z_mom": 0.9,
            "industry_percentile": 82.0,
            "created_at": "2026-07-14T00:00:00Z",
        },
    ]
    (FIXTURES_DIR / "stageanalysis_industry_ranks_weekly.json").write_text(
        json.dumps(ranks), encoding="utf-8"
    )

    # company_generated_info.json — 1 row
    research = [
        {
            "id": "r1",
            "tickerb": "AAPL:US",
            "ticker_ui": "AAPL",
            "ticker_fmp": "AAPL",
            "summary_thesis_answer": "Apple is a dominant consumer tech platform.",
            "claude_reasoning_analysis": "Strong moat via ecosystem lock-in.",
            "openai_reasoning_analysis": "Consistent capital return + services runway.",
            "gemini_reasoning_research_url": "https://example.com/aapl",
            "model_used": "claude-3-5-sonnet",
            "tier": "pro",
            "response_type": "full",
            "full_openai_response": "Long text...",
            "created_at": "2026-07-01T00:00:00Z",
            "updated_at": "2026-07-01T00:00:00Z",
        },
    ]
    (FIXTURES_DIR / "company_generated_info.json").write_text(
        json.dumps(research), encoding="utf-8"
    )

    # ticker_mappings.json — 1 row
    tickers = [
        {
            "id": "t1",
            "tickerb": "AAPL:US",
            "company_name": "Apple Inc",
            "country": "US",
            "exchange": "NASDAQ",
            "currency": "USD",
            "security_type": "stock",
            "isin": "US0378331005",
            "country_iso2": "US",
            "ticker_tradingview": "NASDAQ:AAPL",
            "ticker_fmp": "AAPL",
            "name_fmp": "Apple Inc.",
            "ticker_reuters": "AAPL.O",
            "gics_sector": "Information Technology",
            "gics_sector_code": "45",
            "gics_industry_group": "Tech Hardware & Equipment",
            "gics_industry_group_code": "4520",
            "gics_industry": "Technology Hardware, Storage & Peripherals",
            "gics_industry_code": "452020",
            "gics_sub_industry": "Technology Hardware, Storage & Peripherals",
            "gics_sub_industry_code": "45202030",
            "ticker_ui": "AAPL",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    ]
    (FIXTURES_DIR / "ticker_mappings.json").write_text(
        json.dumps(tickers), encoding="utf-8"
    )

    # Intentionally absent: subindustry_flows.json — tests missing-file skip


# Create fixtures once at module import
_make_fixtures()


# ---------------------------------------------------------------------------
# Helper: run the importer against the fixture dir + a tmp output dir
# ---------------------------------------------------------------------------

def _run_importer(tmp_path: Path) -> dict:
    """Run the importer, return the manifest dict."""
    import importlib
    import scripts.import_equitydesk_full as imp

    # Reload to pick up env patches cleanly (module is already imported)
    import importlib
    importlib.reload(imp)

    # Patch module-level constants
    imp.BACKFILL_SRC = FIXTURES_DIR
    imp.SEED_DIR = tmp_path
    imp.MANIFEST_PATH = tmp_path / "_manifest.json"

    # Reset manifest and run
    imp.main()

    with open(tmp_path / "_manifest.json") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestImporterBasic:
    """The importer runs without raising and produces expected output."""

    def test_importer_runs_without_error(self, tmp_path):
        """Importer completes without raising an exception."""
        manifest = _run_importer(tmp_path)
        assert isinstance(manifest, dict)
        assert len(manifest) > 0

    def test_overview_parquet_not_produced(self, tmp_path):
        """The orphan overview.parquet is NO LONGER written (item 11): the engines
        read the W5 yardstick equitydesk_overview.parquet from a different importer;
        this importer must not ship a second, unread overview seed."""
        manifest = _run_importer(tmp_path)
        dest = tmp_path / "overview.parquet"
        assert not dest.exists(), "orphan overview.parquet should not be written"
        assert "overview" not in manifest

    def test_stage_daily_parquet_col_subset(self, tmp_path):
        """stage_daily.parquet keeps required columns from the stage table."""
        _run_importer(tmp_path)
        dest = tmp_path / "stage_daily.parquet"
        assert dest.exists()
        df = pd.read_parquet(dest)
        assert len(df) == 2
        # Required columns that exist in fixture
        for col in ["ticker", "region", "name_ui", "sata_score", "stage_flag",
                    "stage_detailed", "weeks_in_stage", "mansfield_rs", "atr_ext"]:
            assert col in df.columns, f"Missing col: {col}"
        # 'id' should NOT be in the output (not in _STAGE_COLS)
        assert "id" not in df.columns

    def test_missing_file_skip_no_crash(self, tmp_path):
        """Importer skips files not present in the fixture dir (subindustry_flows)."""
        # subindustry_flows.json was intentionally not created in ed_mini
        assert not (FIXTURES_DIR / "subindustry_flows.json").exists()
        manifest = _run_importer(tmp_path)
        # Should still complete; subindustry_flows simply absent from manifest
        assert "subindustry_flows" not in manifest
        # But other tables succeeded
        assert "stage_daily" in manifest

    def test_earnings_col_subset_and_text_split(self, tmp_path):
        """earnings_calls.parquet has required numeric cols; text cols in text parquet."""
        _run_importer(tmp_path)
        num_dest = tmp_path / "earnings_calls.parquet"
        txt_dest = tmp_path / "earnings_calls_text.parquet"
        assert num_dest.exists()
        assert txt_dest.exists()

        df_num = pd.read_parquet(num_dest)
        assert "earnings_call_sent" in df_num.columns
        assert "earnings_call_perf" in df_num.columns
        assert "earnings_call_combined" in df_num.columns
        assert "call_positivity_score" in df_num.columns
        # Text cols should NOT be in the numeric seed
        assert "summary" not in df_num.columns
        assert "unified_analysis" not in df_num.columns

        df_txt = pd.read_parquet(txt_dest)
        assert "summary" in df_txt.columns

    def test_manifest_shape(self, tmp_path):
        """_manifest.json has the right structure for each entry."""
        manifest = _run_importer(tmp_path)
        for name, entry in manifest.items():
            assert "rows" in entry, f"Missing 'rows' in manifest[{name!r}]"
            assert "cols" in entry, f"Missing 'cols' in manifest[{name!r}]"
            assert "source_file" in entry, f"Missing 'source_file' in manifest[{name!r}]"
            assert "imported_utc" in entry, f"Missing 'imported_utc' in manifest[{name!r}]"
            assert entry["imported_utc"] is None, "imported_utc must be null"
            assert isinstance(entry["cols"], list)
            assert isinstance(entry["rows"], int)

    def test_empty_json_file_no_crash(self, tmp_path):
        """Importer does not crash when a JSON file contains an empty list."""
        import scripts.import_equitydesk_full as imp
        import importlib
        importlib.reload(imp)

        # Write an empty list to one of the files
        empty_dir = tmp_path / "src"
        empty_dir.mkdir()
        shutil.copytree(str(FIXTURES_DIR), str(empty_dir), dirs_exist_ok=True)
        (empty_dir / "industry_flows.json").write_text("[]")

        out_dir = tmp_path / "out"
        out_dir.mkdir()

        imp.BACKFILL_SRC = empty_dir
        imp.SEED_DIR = out_dir
        imp.MANIFEST_PATH = out_dir / "_manifest.json"

        imp.main()

        manifest_path = out_dir / "_manifest.json"
        assert manifest_path.exists()
        with open(manifest_path) as fh:
            manifest = json.load(fh)
        # industry_flows skipped (empty list)
        assert "industry_flows" not in manifest
        # a non-empty table still present
        assert "stage_daily" in manifest

    def test_research_col_subset(self, tmp_path):
        """research.parquet keeps only the required research columns."""
        _run_importer(tmp_path)
        dest = tmp_path / "research.parquet"
        assert dest.exists()
        df = pd.read_parquet(dest)
        assert "tickerb" in df.columns
        assert "summary_thesis_answer" in df.columns
        assert "claude_reasoning_analysis" in df.columns
        # full_openai_response should NOT be present (not in _RESEARCH_COLS)
        assert "full_openai_response" not in df.columns
