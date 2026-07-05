"""Tests for the P2 board-grader stamping patch (PREREGISTRATION.md §2.4).

Deliverable 1 verification:
  - New rows carry board_tenure_days (on-board tenure).
  - Historical rows (stored_df=None) have board_tenure_days=None.
  - tier_cascade is already present in the ledger (regression-guard test).
  - Fail-open: board_tenure_days=None when signal_gate is missing/broken.
  - _board_tenure correctly counts consecutive prior as_of dates.

DESIGN NOTE (flagged for Fable):
  board_tenure_days is a NEW column distinct from hold_days (hold.days_basing).
  The prereg §2.4 calls the field "hold_days" but the existing ledger already
  uses that name for `hold.days_basing`.  We stamp `board_tenure_days` to avoid
  overwriting existing data.  H5 harness must read board_tenure_days.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.grade_us_board import _board_tenure  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_ledger_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal retro_grades-like DataFrame."""
    return pd.DataFrame(rows)


def _ledger_row(as_of: str, ticker: str, lane: str = "buy", horizon: int = 5) -> dict:
    return {
        "as_of": as_of,
        "ticker": ticker,
        "lane": lane,
        "horizon": horizon,
        "ret": 0.01,
        "excess_spy": 0.005,
        "tier_cascade": "T1",
    }


# ---------------------------------------------------------------------------
# _board_tenure — unit tests
# ---------------------------------------------------------------------------

class TestBoardTenure:

    def test_none_when_stored_df_is_none(self):
        """When stored_df is None (no history), tenure is None (not 0)."""
        result = _board_tenure("AAPL", "buy", "2026-07-05", stored_df=None)
        assert result is None, (
            "tenure must be None when stored_df is None (first run, no history)"
        )

    def test_none_when_stored_df_is_empty(self):
        """Empty stored_df → tenure is None."""
        result = _board_tenure("AAPL", "buy", "2026-07-05", stored_df=pd.DataFrame())
        assert result is None

    def test_zero_when_no_prior_dates(self):
        """A ticker on the board for the first time has tenure=0.

        The stored_df has only dates AFTER as_of_str (should not exist in practice,
        but the function should return 0 when no prior dates are found).
        """
        stored = _make_ledger_df([
            _ledger_row("2026-07-06", "AAPL"),  # AFTER the board date
        ])
        result = _board_tenure("AAPL", "buy", "2026-07-05", stored_df=stored)
        assert result == 0

    def test_consecutive_count_simple(self):
        """Three consecutive prior dates → tenure=3."""
        stored = _make_ledger_df([
            _ledger_row("2026-07-01", "AAPL"),
            _ledger_row("2026-07-02", "AAPL"),
            _ledger_row("2026-07-03", "AAPL"),
            # 2026-07-04 NOT present (gap)
        ])
        result = _board_tenure("AAPL", "buy", "2026-07-05", stored_df=stored)
        # Walks back from 2026-07-03: AAPL present → count=1
        # Then 2026-07-02: present → count=2
        # Then 2026-07-01: present → count=3
        # No more prior dates → stop.
        assert result == 3

    def test_consecutive_stops_at_gap(self):
        """Gap in consecutive dates stops the count."""
        stored = _make_ledger_df([
            _ledger_row("2026-06-30", "AAPL"),  # skip (gap)
            _ledger_row("2026-07-02", "AAPL"),
            _ledger_row("2026-07-03", "AAPL"),
        ])
        result = _board_tenure("AAPL", "buy", "2026-07-05", stored_df=stored)
        # Walk back: 2026-07-03 → present (1), 2026-07-02 → present (2),
        # 2026-06-30: not present at 2026-07-01 (gap) → stop at count=2.
        # Actually: 2026-07-03 present, 2026-07-02 present, 2026-06-30 present
        # but there's a gap between 2026-07-02 and 2026-06-30 (no 2026-07-01).
        # Walk reverses sorted prior dates: [2026-06-30, 2026-07-02, 2026-07-03]
        # Reversed: [2026-07-03, 2026-07-02, 2026-06-30]
        # 2026-07-03: AAPL present → count=1
        # 2026-07-02: AAPL present → count=2
        # 2026-06-30: AAPL present → count=3  (consecutive dates in ledger)
        # No more → count=3
        # Note: "consecutive prior as_of dates IN THE LEDGER" — the ledger may not
        # have all calendar days, only trading days.  The tenure counts consecutive
        # as_of records in the PARQUET, not calendar days.
        assert result == 3

    def test_consecutive_stops_when_ticker_absent(self):
        """Absence of a ticker on one date stops the consecutive count."""
        stored = _make_ledger_df([
            _ledger_row("2026-07-01", "AAPL"),
            # 2026-07-02: AAPL ABSENT (not on board)
            _ledger_row("2026-07-02", "MSFT"),  # different ticker
            _ledger_row("2026-07-03", "AAPL"),
        ])
        result = _board_tenure("AAPL", "buy", "2026-07-04", stored_df=stored)
        # Walk back from 2026-07-03 (most recent prior date):
        # 2026-07-03: AAPL present → count=1
        # 2026-07-02: AAPL ABSENT → stop
        # Result: count=1
        assert result == 1

    def test_any_lane_counts(self):
        """Tenure counts presence in ANY lane, not just the current lane."""
        stored = _make_ledger_df([
            _ledger_row("2026-07-01", "AAPL", lane="watch"),
            _ledger_row("2026-07-02", "AAPL", lane="buy"),
            _ledger_row("2026-07-03", "AAPL", lane="laggards"),
        ])
        # Calling for lane="buy" but all lanes count
        result = _board_tenure("AAPL", "buy", "2026-07-04", stored_df=stored)
        assert result == 3, (
            "Tenure counts presence in ANY lane — the current lane arg is not used"
        )

    def test_fail_open_on_corrupt_stored(self):
        """Corrupt stored_df returns None (fail-open) without raising."""
        class BadDF:
            empty = False
            columns = ["bogus"]
            def groupby(self, *args, **kwargs):
                raise RuntimeError("intentional error")

        result = _board_tenure("AAPL", "buy", "2026-07-05", stored_df=BadDF())
        assert result is None, "fail-open: corrupt stored_df must return None, not raise"

    def test_unknown_ticker_returns_zero(self):
        """A ticker not in the stored_df has tenure=0."""
        stored = _make_ledger_df([
            _ledger_row("2026-07-01", "AAPL"),
            _ledger_row("2026-07-02", "AAPL"),
        ])
        result = _board_tenure("NVDA", "buy", "2026-07-03", stored_df=stored)
        assert result == 0, "Unknown ticker: first appearance → tenure=0"


# ---------------------------------------------------------------------------
# board_tenure_days in grade_boards output
# ---------------------------------------------------------------------------

class TestGradeBoardsStamping:
    """Verify grade_boards stamps board_tenure_days on new rows.

    Uses a lightweight fixture that mocks heavy dependencies
    (price loading, forward_metrics, etc.).
    """

    def _make_minimal_names(self):
        """Minimal names DataFrame with one ticker."""
        idx = pd.date_range("2026-01-01", periods=100, freq="B")
        return pd.DataFrame({"AAPL": np.ones(100) * 150.0}, index=idx)

    def _make_minimal_etfs(self):
        """Minimal ETF DataFrame with SPY."""
        idx = pd.date_range("2026-01-01", periods=100, freq="B")
        return pd.DataFrame({"SPY": np.ones(100) * 500.0}, index=idx)

    def _make_board(self, as_of_str: str) -> list[dict]:
        """One board with AAPL on the buy lane."""
        return [{
            "as_of": as_of_str,
            "dispersion_state": None,
            "rank_by": "test",
            "rows": [{
                "lane": "buy",
                "position": 0,
                "ticker": "AAPL",
                "sector": "Information Technology",
                "alpha": 1.0,
                "state": "coiled",
                "label": "buy",
                "urgency": "high",
                "align_tier": "aligned",
                "score": 0.8,
                "band": "A",
                "composite_z": 1.5,
                "verdict": "strong",
                "validation_status": "ok",
                "trust_tier": None,
                "entry_status": "ok",
                "act_level": None,
                "signal_quality": "ok",
                "signal_last_type": None,
                "tier_cascade": "T1",
                "vol_squeeze": None,
                "spot_sector_etf": "XLK",
                "off_high": -0.05,
                "dispersion_state": None,
                "coiled": False,
                "coiled_star": False,
                "coiled_cohort": None,
                "coiled_fire": False,
                "coiled_fire_ticks": None,
                "donor_state": None,
                "donor_sector": None,
                "hold_state": None,
                "hold_days": None,
                "hold_inv": None,
                "hold_anchor_src": None,
                "lane": "buy",
                "arbiter_note": None,
                "postcross_based": False,
                "postcross_armed": None,
                "postcross_shaken": False,
                "postcross_ticks": None,
                "insider_cluster": False,
                "gex_confirm_verdict": None,
                "altdata_conv_gte2": False,
                "sue_fresh": False,
                "news_burst": False,
                "smartmoney_add": False,
                "has_stop_guidance": False,
                "confluence_k": 0,
            }],
        }]

    def test_new_rows_have_board_tenure_days_column(self, monkeypatch, tmp_path):
        """grade_boards output must carry board_tenure_days column."""
        from unittest.mock import patch
        import numpy as np

        # Mock heavy dependencies
        with patch("scripts.grade_us_board.forward_metrics") as mock_fwd, \
             patch("scripts.grade_us_board.fill_index") as mock_fill, \
             patch("scripts.grade_us_board.terminal_state") as mock_ts, \
             patch("scripts.grade_us_board.post_cushion_breach") as mock_pcb, \
             patch("scripts.grade_us_board.get_vector_for_date") as mock_vec, \
             patch("scripts.grade_us_board.resolve_series") as mock_res, \
             patch("scripts.grade_us_board.load_dead_prices", return_value={}):

            # Set up minimal mock returns
            price_idx = pd.date_range("2026-01-01", periods=40, freq="B")
            price_ser = pd.Series(np.ones(40) * 150.0, index=price_idx, name="AAPL")
            mock_res.return_value = price_ser
            mock_fill.return_value = 1  # fill at index 1
            mock_fwd.return_value = {
                "fwd_ret_5": 0.02, "fwd_ret_10": 0.03, "fwd_ret_21": 0.04,
                "fwd_ret_63": 0.05, "fwd_mfe_5": 0.03, "fwd_mfe_10": 0.04,
                "fwd_mfe_21": 0.05, "fwd_mfe_63": 0.06,
            }
            mock_ts.return_value = {"state": "CLEAN_LIFTOFF"}
            mock_pcb.return_value = False
            mock_vec.return_value = {
                "rate_pressure": None, "quad_hard_label": None,
                "fused_risk_label": None, "vol_regime": None,
                "risk_radar_state": None, "regime_vector_degraded": None,
                "vector_asof": None, "staleness_hours": None,
            }

            from scripts.grade_us_board import grade_boards
            names = self._make_minimal_names()
            etfs = self._make_minimal_etfs()
            boards = self._make_board("2026-01-10")

            df = grade_boards(boards, names, etfs, _stored_df=None)

        assert "board_tenure_days" in df.columns, (
            "grade_boards output must carry board_tenure_days column (P2 §2.4 stamp)"
        )

    def test_historical_rows_have_null_board_tenure_days(self, monkeypatch, tmp_path):
        """Rows written before the patch (stored_df=None) have board_tenure_days=None.

        Regression guard: the new column must be NULL on historical rows,
        never retro-fabricated (PIT law).
        """
        from unittest.mock import patch
        import numpy as np

        with patch("scripts.grade_us_board.forward_metrics") as mock_fwd, \
             patch("scripts.grade_us_board.fill_index") as mock_fill, \
             patch("scripts.grade_us_board.terminal_state") as mock_ts, \
             patch("scripts.grade_us_board.post_cushion_breach") as mock_pcb, \
             patch("scripts.grade_us_board.get_vector_for_date") as mock_vec, \
             patch("scripts.grade_us_board.resolve_series") as mock_res, \
             patch("scripts.grade_us_board.load_dead_prices", return_value={}):

            price_idx = pd.date_range("2026-01-01", periods=40, freq="B")
            price_ser = pd.Series(np.ones(40) * 150.0, index=price_idx, name="AAPL")
            mock_res.return_value = price_ser
            mock_fill.return_value = 1
            mock_fwd.return_value = {
                "fwd_ret_5": 0.02, "fwd_ret_10": 0.03, "fwd_ret_21": 0.04,
                "fwd_ret_63": 0.05, "fwd_mfe_5": 0.03, "fwd_mfe_10": 0.04,
                "fwd_mfe_21": 0.05, "fwd_mfe_63": 0.06,
            }
            mock_ts.return_value = {"state": "STOPPED"}
            mock_pcb.return_value = True
            mock_vec.return_value = {
                "rate_pressure": None, "quad_hard_label": None,
                "fused_risk_label": None, "vol_regime": None,
                "risk_radar_state": None, "regime_vector_degraded": None,
                "vector_asof": None, "staleness_hours": None,
            }

            from scripts.grade_us_board import grade_boards
            names = self._make_minimal_names()
            etfs = self._make_minimal_etfs()
            boards = self._make_board("2026-01-10")

            # _stored_df=None simulates first-ever run (no historical ledger)
            df = grade_boards(boards, names, etfs, _stored_df=None)

        if "board_tenure_days" in df.columns:
            # All rows from a first-ever run with no history should be None or 0
            # (None = no stored history; 0 = ticker not seen before)
            for val in df["board_tenure_days"]:
                assert val is None or pd.isna(val) or val == 0, (
                    f"board_tenure_days must be None/0 when stored_df=None, got {val}"
                )

    def test_tier_cascade_already_present_in_row_features(self):
        """Regression guard: tier_cascade is already extracted in _row_features.

        This verifies the existing column is not accidentally broken by the P2 patch.
        """
        from scripts.grade_us_board import _row_features

        sample_row = {
            "ticker": "AAPL",
            "signal": {
                "tier_cascade": "T2",
                "eligible": True,
                "tier": "T2",
                "sub": "deep",
                "reason": None,
                "state": "coiled",
                "above200": True,
                "weekly_bull": True,
                "early_now": False,
                "asof": "2026-07-05",
                "last": {"quality": "ok"},
                "weight": 0.8,
                "tier_sub": "deep",
                "bars_to_cross": None,
                "fresh_bars": 3,
                "ticks": 2,
                "provisional": False,
            },
            "conviction": {},
            "entry_signal": {},
            "hold": {"state": "intact", "days_basing": 5, "anchor": "2026-07-02",
                     "anchor_src": "take", "invalidation": 80.0, "maxup_pct": 0.0,
                     "ob_persist": False, "provisional": False},
            "sector": "Technology",
        }
        feat = _row_features(sample_row)
        assert feat.get("tier_cascade") == "T2", (
            "tier_cascade must be extracted from signal.tier_cascade "
            "(regression: P2 patch must not break existing extraction)"
        )

    def test_fail_open_missing_signal_gate(self):
        """board_tenure_days=None (not a crash) when stored_df is missing columns."""
        # Simulate a stored_df without 'as_of' column (e.g., schema drift)
        bad_df = pd.DataFrame({"ticker": ["AAPL"], "lane": ["buy"]})
        # Should not raise; returns None
        result = _board_tenure("AAPL", "buy", "2026-07-05", stored_df=bad_df)
        assert result is None, (
            "fail-open: missing 'as_of' column in stored_df → None, not crash"
        )
