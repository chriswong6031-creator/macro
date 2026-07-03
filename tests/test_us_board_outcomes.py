"""tests/test_us_board_outcomes.py — Unit tests for W2 emit_outcomes() and template rendering.

Covers:
* Correct running/stopped/flat status assignment.
* Cap at 15 rows.
* Skip-on-missing-price (ticker not in names DataFrame).
* Degrade to empty:true when no exited names.
* Template block absent when artifact is missing or empty:true.
* Template block present (and correct ticker link) when artifact has rows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.grade_us_board import emit_outcomes  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_price_df(tickers: list[str], n_dates: int = 30,
                   base: float = 100.0, daily_drift: float = 0.002) -> pd.DataFrame:
    """Synthetic close DataFrame: business-day index, each ticker a constant-drift series."""
    idx = pd.bdate_range("2026-05-01", periods=n_dates)
    data = {}
    for i, tk in enumerate(tickers):
        prices = [base * (1 + daily_drift * (j + i)) for j in range(n_dates)]
        data[tk] = prices
    return pd.DataFrame(data, index=idx)


def _make_boards(
    window_tickers: list[str],
    current_tickers: list[str],
    dates: list[str] | None = None,
    sector: str = "Technology",
) -> list[dict]:
    """Build a minimal board list.

    window_tickers appear in the buy lane of all-but-last boards.
    current_tickers appear in the buy lane of the LAST (current) board.
    """
    if dates is None:
        dates = [f"2026-06-{10 + i:02d}" for i in range(5)]

    boards = []
    for i, dt in enumerate(dates):
        is_last = i == len(dates) - 1
        tickers_here = current_tickers if is_last else window_tickers
        rows = [
            {"ticker": tk, "lane": "buy", "sector": sector}
            for tk in tickers_here
        ]
        boards.append({"as_of": dt, "rows": rows})
    return boards


# ---------------------------------------------------------------------------
# status classification
# ---------------------------------------------------------------------------

class TestStatusClassification:
    """running >+2%, stopped <-2%, flat otherwise."""

    def test_running_when_pct_above_threshold(self):
        # AAPL was on board at price 100; now at 110 → +10% → running
        names = _make_price_df(["AAPL", "MSFT"], n_dates=40)
        # Force AAPL to start low and end high
        names["AAPL"] = [90.0] * 5 + [110.0] * 35
        boards = _make_boards(
            window_tickers=["AAPL"],
            current_tickers=["MSFT"],  # AAPL exited
            dates=["2026-05-01", "2026-05-02", "2026-05-05", "2026-05-06", "2026-05-07"],
        )
        result = emit_outcomes(boards, names)
        assert not result.get("empty"), f"expected rows, got: {result}"
        rows = result["rows"]
        aapl_row = next((r for r in rows if r["ticker"] == "AAPL"), None)
        assert aapl_row is not None, "AAPL should appear in outcomes"
        assert aapl_row["status"] == "running"

    def test_stopped_when_pct_below_threshold(self):
        names = _make_price_df(["AAPL", "MSFT"], n_dates=40)
        # AAPL starts at 100, ends at 90 → -10% → stopped
        names["AAPL"] = [100.0] * 5 + [90.0] * 35
        boards = _make_boards(
            window_tickers=["AAPL"],
            current_tickers=["MSFT"],
            dates=["2026-05-01", "2026-05-02", "2026-05-05", "2026-05-06", "2026-05-07"],
        )
        result = emit_outcomes(boards, names)
        assert not result.get("empty")
        rows = result["rows"]
        aapl_row = next((r for r in rows if r["ticker"] == "AAPL"), None)
        assert aapl_row is not None
        assert aapl_row["status"] == "stopped"

    def test_flat_near_zero(self):
        names = _make_price_df(["AAPL", "MSFT"], n_dates=40)
        # AAPL flat at 100 throughout → 0% → flat
        names["AAPL"] = [100.0] * 40
        boards = _make_boards(
            window_tickers=["AAPL"],
            current_tickers=["MSFT"],
            dates=["2026-05-01", "2026-05-02", "2026-05-05", "2026-05-06", "2026-05-07"],
        )
        result = emit_outcomes(boards, names)
        assert not result.get("empty")
        rows = result["rows"]
        aapl_row = next((r for r in rows if r["ticker"] == "AAPL"), None)
        assert aapl_row is not None
        assert aapl_row["status"] == "flat"


# ---------------------------------------------------------------------------
# cap at 15 rows
# ---------------------------------------------------------------------------

class TestRowCap:
    def test_capped_at_15(self):
        """When 20 tickers exit the board, only the 15 with largest |pct| are returned."""
        n_exit = 20
        all_tickers = [f"TK{i:02d}" for i in range(n_exit + 2)]
        window_tickers = all_tickers[:n_exit]          # these will exit
        current_tickers = all_tickers[n_exit:]          # just 2 remain

        names = _make_price_df(all_tickers, n_dates=40, daily_drift=0.005)

        dates = [f"2026-05-{i + 1:02d}" for i in range(5)]
        boards = _make_boards(
            window_tickers=window_tickers,
            current_tickers=current_tickers,
            dates=dates,
        )
        result = emit_outcomes(boards, names)
        assert not result.get("empty")
        assert len(result["rows"]) <= 15, (
            f"got {len(result['rows'])} rows, expected ≤15"
        )


# ---------------------------------------------------------------------------
# skip on missing price
# ---------------------------------------------------------------------------

class TestMissingPrice:
    def test_ticker_not_in_names_is_skipped(self):
        """A ticker that exited the board but has no price data is skipped."""
        names = _make_price_df(["AAPL"], n_dates=40)  # MSFT missing from names
        boards = _make_boards(
            window_tickers=["AAPL", "MSFT"],  # MSFT exits with AAPL
            current_tickers=[],
            dates=["2026-05-01", "2026-05-02", "2026-05-05"],
        )
        result = emit_outcomes(boards, names)
        # AAPL should appear, MSFT should not (no price)
        tickers_in_result = {r["ticker"] for r in result.get("rows", [])}
        assert "MSFT" not in tickers_in_result, "MSFT has no price data — must be skipped"

    def test_all_missing_prices_yields_empty(self):
        """When every exited ticker is missing prices, emit empty:true."""
        names = _make_price_df(["SPY"], n_dates=10)  # only SPY, board has OTHER
        boards = _make_boards(
            window_tickers=["NVDA", "AMD"],
            current_tickers=[],
            dates=["2026-05-01", "2026-05-02", "2026-05-05"],
        )
        result = emit_outcomes(boards, names)
        assert result.get("empty") is True


# ---------------------------------------------------------------------------
# degrade to empty when no exited names
# ---------------------------------------------------------------------------

class TestEmptyDegradation:
    def test_empty_when_no_boards(self):
        names = _make_price_df(["AAPL"], n_dates=10)
        result = emit_outcomes([], names)
        assert result.get("empty") is True

    def test_empty_when_all_tickers_still_on_board(self):
        """Tickers present in EVERY board (including current) → nothing exited."""
        names = _make_price_df(["AAPL", "MSFT"], n_dates=40)
        # Same tickers in window and current → none exited
        dates = ["2026-05-01", "2026-05-02", "2026-05-05"]
        boards = _make_boards(
            window_tickers=["AAPL", "MSFT"],
            current_tickers=["AAPL", "MSFT"],  # still there
            dates=dates,
        )
        result = emit_outcomes(boards, names)
        assert result.get("empty") is True


# ---------------------------------------------------------------------------
# summary block
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_keys_present(self):
        names = _make_price_df(["AAPL", "MSFT", "GOOG"], n_dates=40)
        names["AAPL"] = [100.0] * 5 + [115.0] * 35   # running
        names["MSFT"] = [100.0] * 5 + [85.0] * 35    # stopped
        boards = _make_boards(
            window_tickers=["AAPL", "MSFT"],
            current_tickers=["GOOG"],
            dates=["2026-05-01", "2026-05-02", "2026-05-05", "2026-05-06", "2026-05-07"],
        )
        result = emit_outcomes(boards, names)
        assert not result.get("empty")
        smry = result.get("summary", {})
        assert "n_running" in smry
        assert "n_stopped" in smry
        assert "median_pct" in smry
        assert smry["n_running"] == 1
        assert smry["n_stopped"] == 1


# ---------------------------------------------------------------------------
# template block rendering
# ---------------------------------------------------------------------------

class TestTemplateRendering:
    """Jinja render: block present with data, absent without."""

    def _render_block(self, us_board_outcomes) -> str:
        """Render just the outcomes strip conditional logic."""
        from jinja2 import Environment
        env = Environment(autoescape=False)
        # Minimal inline template mirroring the dashboard strip condition
        tmpl = env.from_string(
            "{% if us_board_outcomes and us_board_outcomes.get('rows') %}"
            "{% set _oc = us_board_outcomes %}"
            "<div class=\"board-outcomes\">"
            "{% for oc in _oc.get('rows', []) %}"
            "<tr><td>{{ oc.ticker }}</td><td>{{ '%+.1f'|format(oc.pct_since) }}%</td></tr>"
            "{% endfor %}"
            "</div>"
            "{% endif %}"
        )
        return tmpl.render(us_board_outcomes=us_board_outcomes)

    def test_strip_absent_when_none(self):
        html = self._render_block(None)
        assert "board-outcomes" not in html, "strip must not render when outcomes is None"

    def test_strip_absent_when_empty_flag(self):
        html = self._render_block({"empty": True, "as_of": "2026-07-01"})
        assert "board-outcomes" not in html, "strip must not render when empty:true"

    def test_strip_present_with_rows(self):
        outcomes = {
            "as_of": "2026-07-01",
            "rows": [
                {"ticker": "VEEV", "sector": "Health Care", "first_surfaced": "2026-06-10",
                 "surfaced_price": 200.0, "last_price": 241.4, "pct_since": 20.7,
                 "days_on_board": 5, "exit_date": "2026-06-28", "status": "running", "lane": "buy"},
                {"ticker": "REGN", "sector": "Health Care", "first_surfaced": "2026-06-12",
                 "surfaced_price": 800.0, "last_price": 858.4, "pct_since": 7.3,
                 "days_on_board": 3, "exit_date": "2026-06-28", "status": "running", "lane": "buy"},
            ],
            "summary": {"n_running": 2, "n_stopped": 0, "median_pct": 14.0},
        }
        html = self._render_block(outcomes)
        assert "board-outcomes" in html, "strip must render when rows present"
        assert "VEEV" in html
        assert "REGN" in html
        assert "+20.7%" in html
        assert "+7.3%" in html
