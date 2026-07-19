"""Tests for scripts/import_equitydesk_backfill.py (SGA W5).

Covers:
1. Join map: document_ticker direct hit
2. Join map: ticker_tradingview fallback
3. Join map: exchange-suffix strip fallback
4. Sentiment normalisation formula boundaries (30→+1, 12→0, -6→-1)
5. Performance normalisation formula boundaries (+12→10, 0→5, -12→0)
6. Tag filtering: only pinned taxonomy tags survive
7. Summary carried into score row
8. Idempotent upsert: second import does not duplicate rows
9. Region split: US vs INTL counted correctly
10. Fail-open: missing src directory returns FileNotFoundError (not a crash)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.import_equitydesk_backfill import (  # noqa: E402
    _build_join_map,
    _clean_ticker,
    _derive_tone_word,
    _norm_confidence,
    _norm_performance,
    _norm_sentiment,
    _clean_tags_eq,
    run,
)


# ---------------------------------------------------------------------------
# Minimal fixture builders
# ---------------------------------------------------------------------------

def _make_overview(rows: list[dict]) -> list[dict]:
    """Pad overview rows with minimum required fields."""
    defaults = {
        "id": 1,
        "ticker": "AAPL",
        "region": "USA",
        "name_ui": "Apple Inc.",
        "gics_sector": "Information Technology",
        "gics_industry": "Technology Hardware",
        "gics_industry_group": "Technology Hardware & Equipment",
        "gics_sub_industry": "Technology Hardware, Storage & Peripherals",
        "tradingview_code": "AAPL",
        "sata_score": 7,
        "stage_flag": 2,
        "weeks_in_stage": 4,
        "mansfield_rs": 12.5,
        "sma_30w": 195.0,
        "close": 202.5,
        "level1_tags": "[]",
        "level2_tags": "[]",
    }
    out = []
    for r in rows:
        row = dict(defaults)
        row.update(r)
        out.append(row)
    return out


def _make_earnings(rows: list[dict]) -> list[dict]:
    """Pad earnings rows with minimum required fields."""
    defaults = {
        "id": 1,
        "company_name": "Apple Inc.",
        "company_ticker": "AAPL",
        "document_ticker": "AAPL",
        "ticker_tradingview": "NASDAQ:AAPL",
        "call_date": "2026-05-01",
        "earnings_call_sent": 18,
        "earnings_call_perf": 6,
        "earnings_call_combined": 24,
        "positive_highlights": "",
        "negative_highlights": "",
        "gics_sector": "Information Technology",
        "gics_industry": "Technology Hardware",
        "gics_industry_group": "Technology Hardware & Equipment",
        "call_positivity_score": 7,
        "management_confidence_score": 8,
        "analyst_criticism_score": 3,
        "future_outlook_score": 7,
        "level1_tags": "[]",
        "level2_tags": "[]",
        "unified_analysis": {
            "meta": {
                "ticker": "AAPL",
                "fiscal_qtr": "2026-Q2",
                "call_date": "2026-05-01",
                "company_name": "Apple Inc.",
                "sector": "Information Technology",
                "section": "",
                "speaker_role": "",
            },
            "call_summary": "Revenue grew 5% YoY, iPhone unit sales in line with estimates.",
            "positive_factors": ["Services revenue up 12% YoY"],
            "negative_factors": ["iPhone China revenue declined 8%"],
            "guidance": {},
            "hot_topics": [],
            "kpi_mentions": [],
            "macro_exposure": [],
            "capital_allocation": [],
            "model_used": "gemini-1.5-pro",
            "prompt_version": "v1.0",
            "schema_ver": "1",
        },
    }
    out = []
    for r in rows:
        row = dict(defaults)
        # deep-merge unified_analysis
        if "unified_analysis" in r:
            ua = dict(defaults["unified_analysis"])
            ua.update(r["unified_analysis"])
            if "meta" in r["unified_analysis"]:
                meta = dict(defaults["unified_analysis"]["meta"])
                meta.update(r["unified_analysis"]["meta"])
                ua["meta"] = meta
            row["unified_analysis"] = ua
            r2 = {k: v for k, v in r.items() if k != "unified_analysis"}
            row.update(r2)
        else:
            row.update(r)
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# 1 & 2 & 3: Join map
# ---------------------------------------------------------------------------

class TestJoinMap:
    def test_direct_document_ticker_hit(self):
        ov = _make_overview([{"ticker": "MSFT", "region": "USA"}])
        er = _make_earnings([{"document_ticker": "MSFT", "ticker_tradingview": "NASDAQ:MSFT"}])
        jmap = _build_join_map(ov, er)
        assert jmap[0] == "MSFT"

    def test_tradingview_fallback(self):
        """document_ticker has exchange suffix that doesn't hit; TV matches."""
        ov = _make_overview([{"ticker": "GOOG", "region": "USA"}])
        er = _make_earnings([{
            "document_ticker": "GOOG.XQ",   # won't hit directly
            "ticker_tradingview": "NASDAQ:GOOG",
        }])
        jmap = _build_join_map(ov, er)
        assert jmap[0] == "GOOG"

    def test_exchange_suffix_strip(self):
        """Both document_ticker and TV miss; cleaned document_ticker matches."""
        ov = _make_overview([{"ticker": "AAPL", "region": "USA"}])
        er = _make_earnings([{
            "document_ticker": "AAPL.US",
            "ticker_tradingview": "XYZXYZ:AAPL2",  # won't match
        }])
        jmap = _build_join_map(ov, er)
        assert jmap[0] == "AAPL"

    def test_no_match_uses_cleaned_document_ticker(self):
        """Non-US name with no overview match: falls back to cleaned dt."""
        ov = _make_overview([{"ticker": "AAPL", "region": "USA"}])
        er = _make_earnings([{
            "document_ticker": "VIMIAN.ST",
            "ticker_tradingview": "OMX:VIMIAN",
        }])
        jmap = _build_join_map(ov, er)
        # Should clean to "VIMIAN" even though it's not in overview
        assert jmap[0] == "VIMIAN"


# ---------------------------------------------------------------------------
# 4: Sentiment normalisation boundaries
# ---------------------------------------------------------------------------

class TestSentimentNorm:
    def test_max_sent_clips_to_1(self):
        result = _norm_sentiment(30)
        assert result is not None
        assert abs(result - 1.0) < 1e-9

    def test_neutral_sent_maps_to_0(self):
        result = _norm_sentiment(12)
        assert result is not None
        assert abs(result) < 1e-9

    def test_min_sent_clips_to_minus_1(self):
        result = _norm_sentiment(-6)
        assert result is not None
        assert abs(result - (-1.0)) < 1e-9

    def test_none_returns_none(self):
        assert _norm_sentiment(None) is None

    def test_midpoint(self):
        # sent=21 → (21-12)/18 = 0.5
        result = _norm_sentiment(21)
        assert result is not None
        assert abs(result - 0.5) < 1e-9

    def test_clip_above_30(self):
        # Above max still clips to 1
        assert _norm_sentiment(50) == 1.0


# ---------------------------------------------------------------------------
# 5: Performance normalisation boundaries
# ---------------------------------------------------------------------------

class TestPerfNorm:
    def test_max_perf_maps_to_10(self):
        result = _norm_performance(12)
        assert result is not None
        assert abs(result - 10.0) < 1e-9

    def test_zero_perf_maps_to_5(self):
        result = _norm_performance(0)
        assert result is not None
        assert abs(result - 5.0) < 1e-9

    def test_min_perf_maps_to_0(self):
        result = _norm_performance(-12)
        assert result is not None
        assert abs(result) < 1e-9

    def test_none_returns_none(self):
        assert _norm_performance(None) is None

    def test_clips_below_minus_12(self):
        assert _norm_performance(-24) == 0.0

    def test_clips_above_12(self):
        assert _norm_performance(24) == 10.0


# ---------------------------------------------------------------------------
# 6: Tag filtering
# ---------------------------------------------------------------------------

class TestTagFiltering:
    def test_pinned_tag_passes(self):
        result = _clean_tags_eq(["guidance_raised", "beat_and_raise"])
        assert "guidance_raised" in result
        assert "beat_and_raise" in result

    def test_unknown_tag_dropped(self):
        result = _clean_tags_eq(["SECTOR_TECH_GROWTH", "some_vendor_tag", "guidance_raised"])
        assert "SECTOR_TECH_GROWTH" not in result
        assert "some_vendor_tag" not in result
        assert "guidance_raised" in result

    def test_empty_input_returns_empty(self):
        assert _clean_tags_eq([]) == []

    def test_all_vendor_tags_drop_to_empty(self):
        result = _clean_tags_eq(["MEGA_CAP", "AI_EXPOSURE", "US_DOMESTIC"])
        assert result == []


# ---------------------------------------------------------------------------
# 7: Summary carried through
# ---------------------------------------------------------------------------

class TestSummaryField:
    def test_summary_in_score_row(self, tmp_path):
        src = tmp_path / "backfill"
        src.mkdir()
        ov_data = _make_overview([{"ticker": "AAPL", "region": "USA"}])
        er_data = _make_earnings([{
            "document_ticker": "AAPL",
            "unified_analysis": {
                "call_summary": "Apple beat on services, guided well above consensus.",
            },
        }])
        (src / "overview.json").write_text(
            json.dumps(ov_data), encoding="utf-8"
        )
        (src / "earnings.json").write_text(
            json.dumps(er_data), encoding="utf-8"
        )
        stats = run(src, tmp_path, dry_run=False)
        # scores.parquet should have been written
        scores_path = tmp_path / "data" / "earnings_calls" / "scores.parquet"
        assert scores_path.exists(), "scores.parquet not created"
        import pandas as pd
        df = pd.read_parquet(scores_path)
        assert "summary" in df.columns
        row = df[df["ticker"] == "AAPL"].iloc[0]
        assert row["summary"] and "services" in str(row["summary"])


# ---------------------------------------------------------------------------
# 8: Idempotent upsert
# ---------------------------------------------------------------------------

class TestIdempotentUpsert:
    def test_second_import_does_not_duplicate(self, tmp_path):
        src = tmp_path / "backfill"
        src.mkdir()
        ov_data = _make_overview([{"ticker": "MSFT", "region": "USA"}])
        er_data = _make_earnings([{"document_ticker": "MSFT"}])
        (src / "overview.json").write_text(json.dumps(ov_data), encoding="utf-8")
        (src / "earnings.json").write_text(json.dumps(er_data), encoding="utf-8")
        # First import
        run(src, tmp_path, dry_run=False)
        # Second import
        run(src, tmp_path, dry_run=False)
        import pandas as pd
        scores_path = tmp_path / "data" / "earnings_calls" / "scores.parquet"
        df = pd.read_parquet(scores_path)
        # Keyed (ticker, quarter, year, source) — should have exactly 1 row
        msft_rows = df[(df["ticker"] == "MSFT") & (df["source"] == "equitydesk_backfill")]
        assert len(msft_rows) == 1, f"Expected 1 MSFT row, got {len(msft_rows)}"


# ---------------------------------------------------------------------------
# 9: Region split
# ---------------------------------------------------------------------------

class TestRegionSplit:
    def test_region_counts_reported(self, tmp_path):
        src = tmp_path / "backfill"
        src.mkdir()
        ov_data = _make_overview([
            {"ticker": "AAPL", "region": "USA"},
            {"ticker": "SAP",  "region": "EUROPE"},
            {"ticker": "BABA", "region": "ASIA"},
        ])
        er_data = _make_earnings([])  # no earnings rows needed for this test
        (src / "overview.json").write_text(json.dumps(ov_data), encoding="utf-8")
        (src / "earnings.json").write_text(json.dumps(er_data), encoding="utf-8")
        stats = run(src, tmp_path, dry_run=True)
        rc = stats["region_counts"]
        assert rc.get("USA", 0) == 1
        assert rc.get("EUROPE", 0) == 1
        assert rc.get("ASIA", 0) == 1

    def test_stats_dict_keys_present(self, tmp_path):
        src = tmp_path / "backfill"
        src.mkdir()
        ov_data = _make_overview([{"ticker": "AAPL", "region": "USA"}])
        er_data = _make_earnings([])
        (src / "overview.json").write_text(json.dumps(ov_data), encoding="utf-8")
        (src / "earnings.json").write_text(json.dumps(er_data), encoding="utf-8")
        stats = run(src, tmp_path, dry_run=True)
        for key in ["overview_rows", "earnings_rows", "region_counts",
                    "us_earnings_total", "us_earnings_matched", "us_join_rate",
                    "scores_seeded", "tag_match_rate"]:
            assert key in stats, f"Missing stats key: {key}"


# ---------------------------------------------------------------------------
# 10: Fail-open on missing src
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_missing_src_raises_file_not_found(self, tmp_path):
        bad_src = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError):
            run(bad_src, tmp_path, dry_run=True)

    def test_dry_run_writes_no_files(self, tmp_path):
        src = tmp_path / "backfill"
        src.mkdir()
        ov_data = _make_overview([{"ticker": "AAPL", "region": "USA"}])
        er_data = _make_earnings([{"document_ticker": "AAPL"}])
        (src / "overview.json").write_text(json.dumps(ov_data), encoding="utf-8")
        (src / "earnings.json").write_text(json.dumps(er_data), encoding="utf-8")
        run(src, tmp_path, dry_run=True)
        # No parquet files should have been written
        assert not (tmp_path / "data" / "earnings_calls" / "scores.parquet").exists()
        assert not (tmp_path / "data" / "stage_analysis" / "backfill" / "equitydesk_overview.parquet").exists()
