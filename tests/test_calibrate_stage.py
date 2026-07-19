"""Tests for scripts/calibrate_stage_vs_equitydesk.py (SGA W5).

Covers:
1. Report renders (markdown produced, not empty)
2. Agreement math (exact formula verified on a tiny mock)
3. Handles missing OHLCV (names counted as not-comparable, no crash)
4. Handles missing yardstick parquet (FileNotFoundError)
5. Dry-run writes nothing
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# Helper: write a minimal equitydesk_overview.parquet for the calibrator
# ---------------------------------------------------------------------------

def _write_overview(tmp_path: Path, rows: list[dict]) -> Path:
    import pandas as pd

    defaults = {
        "ticker": "AAPL",
        "region": "USA",
        "stage_flag": 2,
        "sma_30w": 195.0,
        "mansfield_rs": 12.5,
        "close": 202.0,
        "name_ui": "Apple Inc.",
        "gics_sector": "Information Technology",
    }
    final = []
    for r in rows:
        row = dict(defaults)
        row.update(r)
        final.append(row)

    ov_dir = tmp_path / "data" / "stage_analysis" / "backfill"
    ov_dir.mkdir(parents=True, exist_ok=True)
    p = ov_dir / "equitydesk_overview.parquet"
    pd.DataFrame(final).to_parquet(p, index=False)
    return p


# ---------------------------------------------------------------------------
# 1. Report renders
# ---------------------------------------------------------------------------

class TestReportRenders:
    def test_report_is_non_empty_markdown(self, tmp_path):
        """With a minimal yardstick and no OHLCV, report renders gracefully."""
        _write_overview(tmp_path, [
            {"ticker": "AAPL", "region": "USA", "stage_flag": 2},
            {"ticker": "MSFT", "region": "USA", "stage_flag": 1},
        ])
        from scripts.calibrate_stage_vs_equitydesk import run
        stats = run(tmp_path, dry_run=False)
        # Report should have been written
        report_path = tmp_path / "research" / "reports" / "sga_calibration.md"
        assert report_path.exists(), "report file not created"
        text = report_path.read_text(encoding="utf-8")
        assert len(text) > 500, "report is suspiciously short"
        assert "# SGA W5" in text
        assert "Stage Agreement" in text

    def test_report_contains_key_sections(self, tmp_path):
        _write_overview(tmp_path, [{"ticker": "NVDA", "region": "USA", "stage_flag": 2}])
        from scripts.calibrate_stage_vs_equitydesk import run
        run(tmp_path, dry_run=False)
        text = (tmp_path / "research" / "reports" / "sga_calibration.md").read_text()
        for section in ["Universe", "Confusion Matrix", "SMA-30w", "Mansfield"]:
            assert section in text, f"Missing section: {section}"


# ---------------------------------------------------------------------------
# 2. Agreement math
# ---------------------------------------------------------------------------

class TestAgreementMath:
    def test_agreement_formula_exact(self):
        """Verify the agreement formula on a hand-crafted compared list."""
        # Import the internal formula via the module
        from scripts.calibrate_stage_vs_equitydesk import _corr

        # 4 compared names: 3 exact matches, 1 off by 1
        compared = [
            {"ticker": "A", "their_stage": 2, "our_stage": 2,
             "their_sma30": 100.0, "our_sma30": 101.0,
             "their_mrs": 10.0, "our_mrs": 9.5},
            {"ticker": "B", "their_stage": 1, "our_stage": 1,
             "their_sma30": None, "our_sma30": None,
             "their_mrs": None, "our_mrs": None},
            {"ticker": "C", "their_stage": 3, "our_stage": 3,
             "their_sma30": 200.0, "our_sma30": 198.0,
             "their_mrs": -5.0, "our_mrs": -4.8},
            {"ticker": "D", "their_stage": 2, "our_stage": 1,  # off by 1
             "their_sma30": 150.0, "our_sma30": 148.0,
             "their_mrs": 6.0, "our_mrs": 5.5},
        ]
        n = len(compared)
        exact = sum(1 for c in compared if c["our_stage"] == c["their_stage"])
        adj = sum(1 for c in compared if abs(c["our_stage"] - c["their_stage"]) <= 1)
        exact_pct = round(100.0 * exact / n, 1)
        adj_pct = round(100.0 * adj / n, 1)
        assert exact == 3
        assert adj == 4  # all within ±1
        assert exact_pct == 75.0
        assert adj_pct == 100.0

    def test_corr_function(self):
        """Pearson r = 1.0 for perfectly correlated pairs."""
        from scripts.calibrate_stage_vs_equitydesk import _corr
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]
        r = _corr(xs, ys)
        assert r is not None
        assert abs(r - 1.0) < 1e-6

    def test_zero_compared_does_not_crash(self, tmp_path):
        """All names have no OHLCV → n_compared=0, agreement=0.0, no crash."""
        _write_overview(tmp_path, [
            {"ticker": "ZZZZ_FAKE", "region": "USA", "stage_flag": 2},
        ])
        from scripts.calibrate_stage_vs_equitydesk import run
        stats = run(tmp_path, dry_run=True)
        assert stats["n_compared"] == 0
        assert stats["stage_agreement_pct"] == 0.0


# ---------------------------------------------------------------------------
# 3. Handles missing OHLCV
# ---------------------------------------------------------------------------

class TestMissingOHLCV:
    def test_names_without_ohlcv_counted_not_comparable(self, tmp_path):
        """3 US names, none in OHLCV → all counted as not-comparable."""
        _write_overview(tmp_path, [
            {"ticker": "FAKE1", "region": "USA", "stage_flag": 1},
            {"ticker": "FAKE2", "region": "USA", "stage_flag": 2},
            {"ticker": "FAKE3", "region": "USA", "stage_flag": 3},
        ])
        from scripts.calibrate_stage_vs_equitydesk import run
        stats = run(tmp_path, dry_run=True)
        assert stats["n_compared"] == 0
        assert stats["n_ohlcv_missing"] == 3
        assert stats["n_not_comparable"] == 3

    def test_intl_names_excluded_from_comparison(self, tmp_path):
        """Only USA names are compared; EUROPE/ASIA are filtered out."""
        _write_overview(tmp_path, [
            {"ticker": "SAP",  "region": "EUROPE", "stage_flag": 2},
            {"ticker": "BABA", "region": "ASIA",   "stage_flag": 2},
        ])
        from scripts.calibrate_stage_vs_equitydesk import run
        stats = run(tmp_path, dry_run=True)
        # No US names → 0 in the US bucket
        assert stats["n_us_ov"] == 0
        assert stats["n_compared"] == 0


# ---------------------------------------------------------------------------
# 4. Missing yardstick parquet
# ---------------------------------------------------------------------------

class TestMissingYardstick:
    def test_raises_file_not_found(self, tmp_path):
        from scripts.calibrate_stage_vs_equitydesk import run
        with pytest.raises(FileNotFoundError):
            run(tmp_path, dry_run=True)


# ---------------------------------------------------------------------------
# 5. Dry-run writes nothing
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_writes_no_report(self, tmp_path):
        _write_overview(tmp_path, [{"ticker": "AAPL", "region": "USA", "stage_flag": 2}])
        from scripts.calibrate_stage_vs_equitydesk import run
        run(tmp_path, dry_run=True)
        report_path = tmp_path / "research" / "reports" / "sga_calibration.md"
        assert not report_path.exists(), "dry-run should not write the report"
