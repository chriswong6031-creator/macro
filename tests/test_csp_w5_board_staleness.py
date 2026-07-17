"""tests/test_csp_w5_board_staleness.py — CSP-W5 board staleness + pending-buy expiry.

Tests the three helpers added by CSP-W5:
  - _compute_board_staleness: fresh/stale/weekend calendar-aware check
  - _expire_pending_buys:     pending fresh vs pending expired vs confirmed (take)
  - check_surface_freshness:  us_standouts.json now in _ARTIFACTS

US-only.  CN/HK/CA parity is explicitly out of scope (noted in PR body).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import the helpers under test
# ---------------------------------------------------------------------------
from scripts.build_stock_library import (
    _compute_board_staleness,
    _count_trading_sessions_between,
    _expire_pending_buys,
)
import scripts.check_surface_freshness as freshness_mod
from scripts.check_surface_freshness import _ARTIFACTS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv_store(tmp_path: Path, ticker_dates: dict[str, date]) -> Path:
    """Build a minimal data/baskets/ohlcv structure with one parquet per ticker."""
    ohlcv_dir = tmp_path / "baskets" / "ohlcv"
    ohlcv_dir.mkdir(parents=True)
    for ticker, last_date in ticker_dates.items():
        idx = pd.date_range(end=last_date, periods=5, freq="B")
        df = pd.DataFrame({"close": [100.0] * 5}, index=idx)
        df.to_parquet(str(ohlcv_dir / f"{ticker}.parquet"))
    return ohlcv_dir


def _make_pending_row(ticker: str, fire_date: str, tier_cascade: str = "T1") -> dict:
    """Minimal buy row with a pending anticipation signal."""
    return {
        "ticker": ticker,
        "name": ticker,
        "lane": "trend",
        "signal": {
            "tier": "anticipation",
            "sub": "pending",
            "last": {
                "type": "buy",
                "quality": "pending",
                "date": fire_date,
            },
        },
    }


def _make_take_row(ticker: str, take_date: str) -> dict:
    """Minimal buy row with a confirmed take signal."""
    return {
        "ticker": ticker,
        "name": ticker,
        "lane": "trend",
        "signal": {
            "tier": "take",
            "sub": None,
            "last": {
                "type": "buy",
                "quality": "take",
                "date": take_date,
            },
        },
    }


# ---------------------------------------------------------------------------
# _count_trading_sessions_between
# ---------------------------------------------------------------------------

class TestCountTradingSessions:
    def test_same_day_is_zero(self):
        d = date(2026, 7, 15)  # Wednesday — a session day
        assert _count_trading_sessions_between(d, d) == 0

    def test_one_day_later_session(self):
        # 2026-07-15 (Wed) to 2026-07-16 (Thu): 1 session
        assert _count_trading_sessions_between(date(2026, 7, 15), date(2026, 7, 16)) == 1

    def test_crosses_weekend(self):
        # 2026-07-10 (Fri) to 2026-07-13 (Mon): weekend between → 1 session (Mon)
        assert _count_trading_sessions_between(date(2026, 7, 10), date(2026, 7, 13)) == 1

    def test_crosses_long_weekend(self):
        # 2026-07-03 (Fri) to 2026-07-07 (Tue): July 4th holiday (Sat, observed Fri)
        # 2026-07-04 is a Saturday → observed on 2026-07-03 (Fri) is a holiday
        # Sessions strictly after 07-03 through 07-07:
        #   07-04 Sat: weekend
        #   07-05 Sun: weekend
        #   07-06 Mon: session
        #   07-07 Tue: session
        # = 2 sessions
        assert _count_trading_sessions_between(date(2026, 7, 3), date(2026, 7, 7)) == 2

    def test_week_span(self):
        # 2026-07-07 (Tue) to 2026-07-15 (Wed): 6 sessions
        # 07-08 Wed, 07-09 Thu, 07-10 Fri, 07-13 Mon, 07-14 Tue, 07-15 Wed = 6
        assert _count_trading_sessions_between(date(2026, 7, 7), date(2026, 7, 15)) == 6


# ---------------------------------------------------------------------------
# _compute_board_staleness
# ---------------------------------------------------------------------------

class TestComputeBoardStaleness:
    """Calendar-pinned so expected_last_session == 2026-07-16.

    Reference time: 03:00 UTC on 2026-07-17 (Thursday).  At 03:00 UTC the ET
    clock reads 23:00 on 2026-07-16 — after midnight, so 2026-07-17 is the new
    ET calendar day, but the 17:00 ET settle window has NOT been crossed for the
    2026-07-17 session yet, so expected_last_session returns 2026-07-16.

    Verified: lib.nyse_calendar.expected_last_session(datetime(2026,7,17,3,0,utc))
              == date(2026,7,16).
    """

    # 03:00 UTC July 17 → expected session = 2026-07-16 (confirmed above)
    _NOW = datetime(2026, 7, 17, 3, 0, tzinfo=timezone.utc)
    _EXPECTED_SESSION = date(2026, 7, 16)

    def test_fresh_store(self, tmp_path):
        """Store priced through 2026-07-16 (the expected session): not delayed."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 16)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW)
        assert result["price_through"] == "2026-07-16"
        assert result["age_days"] == 0
        assert result["delayed"] is False

    def test_one_session_behind(self, tmp_path):
        """Store priced through 2026-07-15 (1 session behind 07-15→07-16):
        NOT delayed (threshold = 2)."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 15)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW)
        assert result["price_through"] == "2026-07-15"
        assert result["delayed"] is False

    def test_two_sessions_behind_is_delayed(self, tmp_path):
        """Store priced through 2026-07-14 (2 sessions behind: 07-14→07-15, 07-15→07-16):
        delayed = True."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"AAPL": date(2026, 7, 14)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW)
        assert result["price_through"] == "2026-07-14"
        assert result["delayed"] is True

    def test_stale_multiple_tickers_uses_max(self, tmp_path):
        """With mixed dates, price_through is the MAX, not the min."""
        ohlcv_dir = _make_ohlcv_store(tmp_path, {
            "AAPL": date(2026, 7, 16),
            "MSFT": date(2026, 7, 14),
        })
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=self._NOW)
        assert result["price_through"] == "2026-07-16"
        assert result["delayed"] is False

    def test_missing_directory_returns_sentinel(self, tmp_path):
        """Non-existent directory: returns the fail-soft sentinel."""
        result = _compute_board_staleness(ohlcv_dir=tmp_path / "nonexistent", now=self._NOW)
        assert result["price_through"] is None
        assert result["age_days"] is None
        assert result["delayed"] is False

    def test_empty_directory_returns_sentinel(self, tmp_path):
        """Empty directory (no parquets): returns the fail-soft sentinel."""
        empty = tmp_path / "empty"
        empty.mkdir()
        result = _compute_board_staleness(ohlcv_dir=empty, now=self._NOW)
        assert result["price_through"] is None

    def test_weekend_reference_uses_prior_session(self, tmp_path):
        """Reference on Saturday 2026-07-18: expected session = 2026-07-17 (Fri).
        Store priced through that Friday = not delayed."""
        # 2026-07-18 is Saturday; expected_last_session returns 2026-07-17 (Fri)
        now_sat = datetime(2026, 7, 18, 14, 0, tzinfo=timezone.utc)  # 14:00 UTC Saturday
        ohlcv_dir = _make_ohlcv_store(tmp_path, {"SPY": date(2026, 7, 17)})
        result = _compute_board_staleness(ohlcv_dir=ohlcv_dir, now=now_sat)
        assert result["price_through"] == "2026-07-17"
        assert result["delayed"] is False


# ---------------------------------------------------------------------------
# _expire_pending_buys
# ---------------------------------------------------------------------------

class TestExpirePendingBuys:
    """Board as_of = 2026-07-17 (Thursday).

    Session counts from fire_date to 2026-07-17:
      fire_date=2026-07-09 (Thu) → 07-10 Fri, 07-13 Mon, 07-14 Tue, 07-15 Wed, 07-16 Thu, 07-17 Thu
                                 = 6 sessions → expired (> 3)
      fire_date=2026-07-14 (Tue) → 07-15 Wed, 07-16 Thu, 07-17 Thu = 3 sessions → NOT expired (= 3)
      fire_date=2026-07-15 (Wed) → 07-16 Thu, 07-17 Thu = 2 sessions → NOT expired
      fire_date=2026-07-16 (Thu) → 07-17 Thu = 1 session → NOT expired
    """
    _ASOF = "2026-07-17"

    def test_fresh_pending_stays_on_buy(self):
        """A pending buy fired today (0 sessions old) stays on buy."""
        row = _make_pending_row("FRESH", "2026-07-17")
        buy_in = [row]
        watch_in = []
        buy_out, watch_out, n = _expire_pending_buys(buy_in, watch_in, self._ASOF)
        assert n == 0
        assert len(buy_out) == 1
        assert buy_out[0]["ticker"] == "FRESH"
        assert len(watch_out) == 0

    def test_exactly_3_sessions_stays_on_buy(self):
        """A pending buy exactly 3 sessions old (= threshold) stays on buy (rule is > 3)."""
        row = _make_pending_row("EXACT3", "2026-07-14")
        buy_in = [row]
        watch_in = []
        buy_out, watch_out, n = _expire_pending_buys(buy_in, watch_in, self._ASOF)
        assert n == 0
        assert len(buy_out) == 1

    def test_expired_pending_demoted_to_watch_lane_in_buy(self):
        """A pending buy > 3 sessions old is demoted to lane='watch' but stays in buy_out.

        The standout board template only renders rows from wide["buy"] / _su.buy.
        Moving expired rows to the separate wide["watch"] data-plane would silently
        drop them from the board.  Instead they stay in buy with lane='watch' so the
        template's _lane_order partition renders them under the Watch sub-heading and
        the pending_expired note fires.
        """
        row = _make_pending_row("OLD", "2026-07-09")  # 6 sessions ago
        buy_in = [row]
        watch_in = []
        buy_out, watch_out, n = _expire_pending_buys(buy_in, watch_in, self._ASOF)
        assert n == 1
        # Demoted row stays in buy_out with lane='watch'
        assert len(buy_out) == 1
        expired_row = buy_out[0]
        assert expired_row["ticker"] == "OLD"
        assert expired_row["pending_expired"] is True
        assert "2026-07-09" in expired_row["pending_expiry_reason"]
        assert "2026-07-09" in expired_row["pending_expiry_reason_zh"]
        assert expired_row["lane"] == "watch"
        # watch_out is the unchanged watch_rows passthrough (empty in this case)
        assert len(watch_out) == 0

    def test_confirmed_take_never_expires(self):
        """A confirmed take signal (quality='take') is never expired, regardless of age."""
        row = _make_take_row("TAKE", "2026-07-01")  # very old, but confirmed
        buy_in = [row]
        watch_in = []
        buy_out, watch_out, n = _expire_pending_buys(buy_in, watch_in, self._ASOF)
        assert n == 0
        assert len(buy_out) == 1
        assert buy_out[0]["ticker"] == "TAKE"

    def test_expired_row_in_buy_watch_rows_passed_through(self):
        """Expired pending rows stay in buy_out (lane='watch'); watch_rows pass through unchanged.

        The wide["watch"] data-plane is a separate list the board template never iterates,
        so expired rows must NOT be moved there.  watch_rows are passed through unchanged.
        """
        expired_row = _make_pending_row("OLD", "2026-07-09")
        existing_watch = [{"ticker": "WATCH1", "lane": "watch", "signal": {}}]
        buy_in = [expired_row]
        buy_out, watch_out, n = _expire_pending_buys(buy_in, existing_watch, self._ASOF)
        assert n == 1
        # Expired row is in buy_out with lane='watch'
        assert buy_out[0]["ticker"] == "OLD"
        assert buy_out[0]["lane"] == "watch"
        assert buy_out[0]["pending_expired"] is True
        # watch_rows are passed through unchanged (not prepended to)
        assert len(watch_out) == 1
        assert watch_out[0]["ticker"] == "WATCH1"

    def test_mixed_buy_rows(self):
        """Fresh + old pending + confirmed: only old pending is demoted to lane='watch'.

        All three rows stay in buy_out; the demoted row has lane='watch' and
        pending_expired=True so the template renders it under the Watch sub-heading.
        """
        rows = [
            _make_pending_row("FRESH", "2026-07-17"),   # 0 sessions — stays as-is
            _make_pending_row("OLD", "2026-07-09"),      # 6 sessions — demoted to watch lane
            _make_take_row("TAKE", "2026-07-01"),        # confirmed — never expires
        ]
        buy_out, watch_out, n = _expire_pending_buys(rows, [], self._ASOF)
        assert n == 1
        buy_tickers = [r["ticker"] for r in buy_out]
        # All three rows remain in buy_out
        assert "FRESH" in buy_tickers
        assert "TAKE" in buy_tickers
        assert "OLD" in buy_tickers
        # The demoted row is tagged correctly
        old_row = next(r for r in buy_out if r["ticker"] == "OLD")
        assert old_row["lane"] == "watch"
        assert old_row["pending_expired"] is True
        # watch_out is the unchanged passthrough (empty in this case)
        assert len(watch_out) == 0

    def test_none_asof_does_nothing(self):
        """None board_asof: no rows are expired (fail-soft)."""
        row = _make_pending_row("OLD", "2026-07-01")
        buy_out, watch_out, n = _expire_pending_buys([row], [], None)
        assert n == 0
        assert len(buy_out) == 1

    def test_missing_fire_date_stays_on_buy(self):
        """A pending row with no fire date (last.date absent) stays on buy."""
        row = {
            "ticker": "NODATE",
            "lane": "trend",
            "signal": {
                "tier": "anticipation",
                "sub": "pending",
                "last": {"type": "buy", "quality": "pending"},
            },
        }
        buy_out, watch_out, n = _expire_pending_buys([row], [], self._ASOF)
        assert n == 0
        assert len(buy_out) == 1

    def test_does_not_mutate_original_buy_list(self):
        """The original buy list items are not mutated (shallow copy is made)."""
        row = _make_pending_row("OLD", "2026-07-09")
        original_lane = row["lane"]
        buy_out, watch_out, n = _expire_pending_buys([row], [], self._ASOF)
        assert n == 1
        # Original row's lane should not have been changed
        assert row["lane"] == original_lane, "original row must not be mutated"

    def test_watch_row_not_expired(self):
        """Rows already on watch (not in buy_rows) are never double-processed."""
        # _expire_pending_buys only processes buy_rows; watch_rows are passed through
        watch_row = _make_pending_row("WATCH_PEND", "2026-07-01")
        buy_out, watch_out, n = _expire_pending_buys([], [watch_row], self._ASOF)
        assert n == 0
        assert len(watch_out) == 1  # watch row passed through unchanged


# ---------------------------------------------------------------------------
# check_surface_freshness: us_standouts.json in _ARTIFACTS
# ---------------------------------------------------------------------------

class TestStandoutsSentinelRegistration:
    def test_us_standouts_in_artifacts(self):
        """us_standouts.json must be registered in _ARTIFACTS (FT-R8 CSP-W5)."""
        paths = [spec.path for spec in _ARTIFACTS]
        assert "site/factordata/us_standouts.json" in paths

    def test_sentinel_checks_us_standouts(self, tmp_path, capsys):
        """A stale us_standouts.json emits a ::warning:: annotation."""
        ref_now = datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc)
        expected_session = "2026-07-08"
        # Write all artifacts fresh
        for spec in _ARTIFACTS:
            p = tmp_path / spec.path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"as_of": expected_session}))
        # Poison us_standouts.json specifically
        standouts_path = tmp_path / "site" / "factordata" / "us_standouts.json"
        standouts_path.write_text(json.dumps({"as_of": "2020-01-01"}))
        rc = freshness_mod.run(now=ref_now, root=tmp_path)
        assert rc == 0  # always warn-only
        out = capsys.readouterr().out
        assert "::warning::SURFACE STALE:" in out
        assert "site/factordata/us_standouts.json" in out

    def test_fresh_us_standouts_no_warning(self, tmp_path, capsys):
        """A fresh us_standouts.json generates no warning."""
        ref_now = datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc)
        expected_session = "2026-07-08"
        for spec in _ARTIFACTS:
            p = tmp_path / spec.path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"as_of": expected_session}))
        rc = freshness_mod.run(now=ref_now, root=tmp_path)
        assert rc == 0
        out = capsys.readouterr().out
        assert "::warning::" not in out
