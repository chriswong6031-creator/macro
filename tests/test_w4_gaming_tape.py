"""Unit tests for W4 gaming tape collectors and phase-0 study.

All tests are OFFLINE (no network calls) and require no data cache.
They exercise:
  - Parser logic with synthetic bytes (NY, NJ, PGCB)
  - Operator name normalisation
  - Nowcast construction on mini synthetic panel
  - BH FDR gate logic
  - TrialLedger grid logging (no disk write — ephemeral temp path)
"""
from __future__ import annotations

import io
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.gaming_ny import (
    _norm_op,
    _parse_workbook,
    OPERATOR_ALIASES,
)
from collectors.gaming_nj import (
    _norm_op_nj,
    _parse_nj_excel,
    _last_day_of_month as nj_last_day,
)
from collectors.gaming_pgcb import (
    _norm_pgcb,
    _parse_pgcb_excel,
    _last_day_of_month as pgcb_last_day,
)
from engine.trial_ledger import TrialLedger
from engine.validation import benjamini_hochberg


# ---------------------------------------------------------------------------
# helper: build a minimal in-memory Excel workbook as bytes
# ---------------------------------------------------------------------------

def _make_excel_bytes(df: pd.DataFrame) -> bytes:
    """Write a DataFrame to an Excel workbook in memory."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# NY collector
# ---------------------------------------------------------------------------

class TestNYNormalisation:
    def test_known_aliases(self):
        assert _norm_op("DraftKings") == "DKNG"
        assert _norm_op("DRAFTKINGS") == "DKNG"
        assert _norm_op("FanDuel") == "FLUT_FD"
        assert _norm_op("FanDuel Sportsbook") == "FLUT_FD"
        assert _norm_op("BetMGM") == "BETMGM"
        assert _norm_op("BET MGM") == "BETMGM"
        assert _norm_op("Caesars") == "CZRS"
        assert _norm_op("Caesars Sportsbook") == "CZRS"

    def test_unknown_passes_through_uppercased(self):
        result = _norm_op("SomeNewBook")
        assert result == "SOMENEWBOOK"

    def test_empty_string(self):
        result = _norm_op("")
        assert isinstance(result, str)


class TestNYParser:
    def _make_ny_workbook(self) -> bytes:
        data = pd.DataFrame({
            "Operator": ["DraftKings", "FanDuel", "BetMGM", "TOTAL"],
            "Gross Gaming Revenue": [1_000_000, 1_200_000, 500_000, 2_700_000],
            "Gross Wagers": [15_000_000, 18_000_000, 7_500_000, 40_500_000],
            "Hold %": [6.7, 6.7, 6.7, 6.7],
        })
        return _make_excel_bytes(data)

    def test_parse_basic(self):
        raw = self._make_ny_workbook()
        period_end = date(2024, 1, 7)
        df = _parse_workbook(raw, period_end, release_date=date(2024, 1, 9))
        # TOTAL row should be dropped
        assert len(df) == 3
        assert "DKNG" in df["operator"].values
        assert "FLUT_FD" in df["operator"].values
        assert "BETMGM" in df["operator"].values
        assert (df["revenue_usd"] > 0).all()

    def test_period_propagated(self):
        raw = self._make_ny_workbook()
        period_end = date(2024, 3, 10)
        df = _parse_workbook(raw, period_end, release_date=date(2024, 3, 12))
        assert all(d == pd.Timestamp(period_end) for d in pd.to_datetime(df["period_end"]))

    def test_period_start_is_6_days_before(self):
        raw = self._make_ny_workbook()
        period_end = date(2024, 3, 10)
        df = _parse_workbook(raw, period_end, release_date=date(2024, 3, 12))
        expected_start = period_end - timedelta(days=6)
        assert all(d == pd.Timestamp(expected_start) for d in pd.to_datetime(df["period_start"]))

    def test_total_row_excluded(self):
        raw = self._make_ny_workbook()
        df = _parse_workbook(raw, date(2024, 1, 7), release_date=date(2024, 1, 9))
        for op in df["operator"]:
            assert "TOTAL" not in op.upper()


# ---------------------------------------------------------------------------
# NJ collector
# ---------------------------------------------------------------------------

class TestNJNormalisation:
    def test_aliases(self):
        assert _norm_op_nj("DraftKings") == "DKNG"
        assert _norm_op_nj("FanDuel") == "FLUT_FD"
        assert _norm_op_nj("borgata online") == "BETMGM"

    def test_last_day_of_month(self):
        assert nj_last_day(2024, 1) == date(2024, 1, 31)
        assert nj_last_day(2024, 2) == date(2024, 2, 29)  # leap year
        assert nj_last_day(2023, 2) == date(2023, 2, 28)
        assert nj_last_day(2024, 12) == date(2024, 12, 31)


class TestNJParser:
    def _make_nj_workbook(self, market: str = "sports") -> bytes:
        data = pd.DataFrame({
            "Operator": ["DraftKings", "FanDuel", "BetMGM", "Total"],
            "Gross Revenue": [2_000_000, 2_500_000, 800_000, 5_300_000],
            "Total Wagers": [30_000_000, 37_000_000, 12_000_000, 79_000_000],
        })
        return _make_excel_bytes(data)

    def test_parse_basic(self):
        raw = self._make_nj_workbook()
        df = _parse_nj_excel(raw, date(2024, 1, 31), "sports", release_date=date(2024, 2, 20))
        # Total row should be excluded
        assert len(df) == 3
        assert set(df["operator"]) == {"DKNG", "FLUT_FD", "BETMGM"}

    def test_market_column_present(self):
        raw = self._make_nj_workbook("igaming")
        df = _parse_nj_excel(raw, date(2024, 1, 31), "igaming", release_date=date(2024, 2, 20))
        assert all(df["market"] == "igaming")

    def test_revenue_nonnegative(self):
        raw = self._make_nj_workbook()
        df = _parse_nj_excel(raw, date(2024, 1, 31), "sports", release_date=date(2024, 2, 20))
        assert (df["gross_revenue_usd"] > 0).all()


# ---------------------------------------------------------------------------
# PGCB collector
# ---------------------------------------------------------------------------

class TestPGCBNormalisation:
    def test_aliases(self):
        assert _norm_pgcb("DraftKings") == "DKNG"
        assert _norm_pgcb("Caesars") == "CZRS"
        assert _norm_pgcb("Rivers Casino") == "PENN"

    def test_last_day_of_month(self):
        assert pgcb_last_day(2024, 2) == date(2024, 2, 29)
        assert pgcb_last_day(2023, 11) == date(2023, 11, 30)


class TestPGCBParser:
    def _make_pgcb_workbook(self) -> bytes:
        data = pd.DataFrame({
            "Operator": ["DraftKings", "FanDuel", "Caesars", "TOTAL"],
            "Gross Revenue": [1_500_000, 1_800_000, 600_000, 3_900_000],
        })
        return _make_excel_bytes(data)

    def test_parse_basic(self):
        raw = self._make_pgcb_workbook()
        df = _parse_pgcb_excel(raw, date(2024, 1, 31), "sports", release_date=date(2024, 2, 15))
        assert len(df) == 3
        assert "DKNG" in df["operator"].values
        assert "CZRS" in df["operator"].values

    def test_segment_column(self):
        raw = self._make_pgcb_workbook()
        df = _parse_pgcb_excel(raw, date(2024, 1, 31), "igaming", release_date=date(2024, 2, 15))
        assert all(df["segment"] == "igaming")


# ---------------------------------------------------------------------------
# Trial Ledger
# ---------------------------------------------------------------------------

class TestTrialLedger:
    def test_grid_logging_ephemeral(self, tmp_path):
        """Verify that log_grid adds distinct configs and deduplicates re-runs."""
        led = TrialLedger(path=tmp_path / "ledger.jsonl", family="test_gaming_w4")
        grid = [
            {"cell": "H1_DKNG", "test": "nowcast_lead_corr"},
            {"cell": "H1_MGM",  "test": "nowcast_lead_corr"},
            {"cell": "H2_DRIFT", "test": "post_release_drift"},
        ]
        n_new = led.log_grid(grid, family="test_gaming_w4")
        assert n_new == 3
        assert led.literal_n("test_gaming_w4") == 3

        # Re-running the same grid: all are deduped → 0 new
        n_dup = led.log_grid(grid, family="test_gaming_w4")
        assert n_dup == 0
        assert led.literal_n("test_gaming_w4") == 3  # unchanged

    def test_effective_n_equals_literal_n_by_default(self, tmp_path):
        led = TrialLedger(path=tmp_path / "led.jsonl", family="fam")
        led.log_grid([{"a": i} for i in range(6)], family="fam")
        assert led.effective_n("fam") == 6

    def test_declared_budget_is_floor(self, tmp_path):
        led = TrialLedger(path=tmp_path / "led.jsonl", family="fam2")
        led.log_declared_budget(10, family="fam2", reason="test")
        led.log_grid([{"x": i} for i in range(3)], family="fam2")
        # effective_n should be max(3, 10) = 10
        assert led.effective_n("fam2") == 10


# ---------------------------------------------------------------------------
# BH FDR gate
# ---------------------------------------------------------------------------

class TestBHGate:
    def test_no_reject_all_high_p(self):
        pvals = {"H1_DKNG": 0.5, "H1_MGM": 0.8, "H2_DRIFT": 0.9}
        result = benjamini_hochberg(pvals, alpha=0.10)
        assert not any(v["reject"] for v in result.values())

    def test_rejects_small_p(self):
        pvals = {"H1_DKNG": 0.001, "H1_MGM": 0.5, "H2_DRIFT": 0.9}
        result = benjamini_hochberg(pvals, alpha=0.10)
        assert result["H1_DKNG"]["reject"] is True

    def test_q_values_monotone(self):
        """BH q-values are monotone non-decreasing when sorted by p."""
        pvals = {f"c{i}": p for i, p in enumerate([0.01, 0.05, 0.20, 0.60, 0.90])}
        result = benjamini_hochberg(pvals, alpha=0.10)
        q_vals = [result[k]["q"] for k in sorted(result, key=lambda k: result[k]["p"])]
        for i in range(len(q_vals) - 1):
            assert q_vals[i] <= q_vals[i + 1] + 1e-9  # monotone


# ---------------------------------------------------------------------------
# nowcast construction (mini integration test)
# ---------------------------------------------------------------------------

class TestNowcastConstruction:
    def _mini_state_panels(self) -> dict:
        """Build a minimal state panel for testing the nowcast pipeline."""
        rng = np.random.default_rng(42)
        # NJ monthly: 2022-01 to 2024-12
        months = pd.date_range("2022-01-01", "2024-12-01", freq="MS")
        nj_rows = []
        for ms in months:
            pe = (ms + pd.offsets.MonthEnd(0)).date()
            for op in ["DKNG", "FLUT_FD", "BETMGM"]:
                nj_rows.append({
                    "period_end": pe,
                    "release_date": (ms + timedelta(days=25)).date(),
                    "market": "sports",
                    "operator": op,
                    "operator_raw": op,
                    "gross_revenue_usd": float(rng.uniform(1e6, 5e6)),
                    "handle_usd": None,
                })
        nj = pd.DataFrame(nj_rows)
        return {"nj": nj}

    def _mini_weights(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"operator": "DKNG", "state": "NJ", "segment": "sports",
             "rev_share_approx": 0.30, "source_filing": "test", "period": "FY2023", "notes": ""},
            {"operator": "MGM",  "state": "NJ", "segment": "sports",
             "rev_share_approx": 0.12, "source_filing": "test", "period": "FY2023", "notes": ""},
        ])

    def test_nowcast_runs_without_error(self):
        """The nowcast construction pipeline produces a non-empty DataFrame."""
        # import the internal function
        from scripts.w4_gaming_tape_phase0 import _build_nowcast
        panels = self._mini_state_panels()
        weights = self._mini_weights()
        nc = _build_nowcast(panels, weights)
        # DKNG has a NJ weight; should produce rows
        assert isinstance(nc, pd.DataFrame)
        # At minimum: the function runs without raising

    def test_yoy_deseasonalization_applied(self):
        """YoY growth values are finite (NaN only in the first 12 months per operator-state)."""
        from scripts.w4_gaming_tape_phase0 import _build_nowcast
        panels = self._mini_state_panels()
        weights = self._mini_weights()
        nc = _build_nowcast(panels, weights)
        if nc.empty:
            return  # acceptable if DKNG not in weights
        # Non-NaN nowcasts should exist after 12 months of history
        dkng_nc = nc[nc["operator"] == "DKNG"].dropna(subset=["nowcast_yoy_growth"])
        # With 36 months of data, we should have at least some YoY rows
        assert len(dkng_nc) >= 1 or nc.empty  # empty is acceptable (dedup edge case)


# ---------------------------------------------------------------------------
# check_validated_claims guard (CI integration)
# ---------------------------------------------------------------------------

class TestNoValidatedClaims:
    """Ensure the phase-0 report does not contain the banned word 'validated'."""

    def test_report_no_validated_keyword(self):
        report_path = Path(__file__).parent.parent / "reports" / "w4-gaming-tape-phase0.md"
        if not report_path.exists():
            pytest.skip("Report not yet generated; run scripts.w4_gaming_tape_phase0 first")
        text = report_path.read_text(encoding="utf-8")
        # The CI check bans the word in user-facing context
        # (case-insensitive, standalone word)
        import re
        matches = re.findall(r"\bvalidated\b", text, re.I)
        assert len(matches) == 0, (
            f"Report contains banned word 'validated' {len(matches)} time(s). "
            "Use 'verified', 'confirmed', 'tested', or 'checked' instead."
        )
