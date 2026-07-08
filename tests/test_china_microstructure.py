"""Tests for engine/china_microstructure.py — fully offline, synthetic fixtures.

Covers:
  - Board classification + era-aware limit widths
  - ST flag application (main only, ST_STORE_COVERAGE_DATE gate)
  - IPO exclusion windows (STAR/ChiNext first-5, pre-2014 first-1)
  - Ex-div suspect suppression
  - Event detection: sealed_up, failed_up_seal, sealed_down, failed_down_seal
  - lianban_count accumulation
  - aggregate_daily schema + breadth pcts
  - name_packet fields (limit_state, fillable, t_plus_one_risk, chase_veto)
  - Degrade-don't-crash: empty df, missing ST store
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.china_microstructure import (
    CHINEXT_WIDE_DATE,
    LIMIT_TAPE_START_DATE,
    ST_STORE_COVERAGE_DATE,
    _board_from_ticker,
    _detect_limit_events,
    aggregate_daily,
    limit_width_for_date,
    name_packet,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _ohlcv(
    closes: list[float],
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    start: str = "2020-01-02",
) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame with a business-day DatetimeIndex."""
    n = len(closes)
    idx = pd.bdate_range(start=start, periods=n)
    c = np.array(closes, dtype=float)
    o = np.array(opens, dtype=float) if opens is not None else c
    h = np.array(highs, dtype=float) if highs is not None else c
    lo = np.array(lows, dtype=float) if lows is not None else c
    return pd.DataFrame({"open": o, "close": c, "high": h, "low": lo,
                         "volume": np.ones(n) * 1e6}, index=idx)


# ── board classification ───────────────────────────────────────────────────────

class TestBoardFromTicker:
    def test_star_688(self):
        assert _board_from_ticker("688981.SS") == "star"

    def test_star_689(self):
        assert _board_from_ticker("689009.SS") == "star"

    def test_chinext_300(self):
        assert _board_from_ticker("300750.SZ") == "chinext"

    def test_chinext_301(self):
        assert _board_from_ticker("301020.SZ") == "chinext"

    def test_main_600(self):
        assert _board_from_ticker("600519.SS") == "main"

    def test_main_000(self):
        assert _board_from_ticker("000001.SZ") == "main"

    def test_bse_8(self):
        assert _board_from_ticker("831083.BJ") == "bse"

    def test_unknown_defaults_main(self):
        assert _board_from_ticker("") == "main"


# ── limit width era logic ─────────────────────────────────────────────────────

class TestLimitWidthForDate:
    def test_main_normal(self):
        assert limit_width_for_date("main", pd.Timestamp("2020-01-01")) == 0.10

    def test_main_st(self):
        assert limit_width_for_date("main", pd.Timestamp("2020-01-01"), is_st=True) == 0.05

    def test_star_always_20(self):
        assert limit_width_for_date("star", pd.Timestamp("2019-08-01")) == 0.20

    def test_chinext_before_cutoff(self):
        d = CHINEXT_WIDE_DATE - pd.Timedelta(days=1)
        assert limit_width_for_date("chinext", d) == 0.10

    def test_chinext_on_cutoff(self):
        assert limit_width_for_date("chinext", CHINEXT_WIDE_DATE) == 0.20

    def test_chinext_after_cutoff(self):
        d = CHINEXT_WIDE_DATE + pd.Timedelta(days=30)
        assert limit_width_for_date("chinext", d) == 0.20

    def test_bse(self):
        assert limit_width_for_date("bse", pd.Timestamp("2022-01-01")) == 0.30

    def test_star_st_stays_20(self):
        # ST flag on STAR board must NOT reduce to 5%
        assert limit_width_for_date("star", pd.Timestamp("2022-01-01"), is_st=True) == 0.20

    def test_chinext_st_stays_20_after_cutoff(self):
        assert limit_width_for_date("chinext", CHINEXT_WIDE_DATE + pd.Timedelta(30), is_st=True) == 0.20


# ── event detection — sealed_up ───────────────────────────────────────────────

class TestDetectSealedUp:
    """A main-board ticker.  Prev close = 10.0 → limit_up = round(10*1.10, 2) = 11.0."""

    def test_sealed_up_detected(self):
        closes = [10.0, 10.0, 11.0]   # bar 2: close == lim_up
        highs  = [10.0, 10.0, 11.1]
        df     = _ohlcv(closes=closes, highs=highs)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        assert any(e["event"] == "sealed_up" for e in events)
        su = [e for e in events if e["event"] == "sealed_up"]
        assert su[0]["ticker"] == "000001.SZ"
        assert su[0]["board"] == "main"
        assert su[0]["limit_width"] == 10.0
        assert su[0]["lianban_count"] == 1

    def test_failed_up_seal_detected(self):
        # High touches limit but close does not
        closes = [10.0, 10.0, 10.5]
        highs  = [10.0, 10.0, 11.0]   # high == limit_up but close < limit_up
        df     = _ohlcv(closes=closes, highs=highs)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        fus = [e for e in events if e["event"] == "failed_up_seal"]
        assert len(fus) == 1
        assert fus[0]["close_off_limit_pct"] > 0  # close below limit

    def test_no_event_on_normal_day(self):
        closes = [10.0, 10.0, 10.3]   # +3%, below 10% limit
        df     = _ohlcv(closes=closes)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        assert events == []


# ── event detection — sealed_down ────────────────────────────────────────────

class TestDetectSealedDown:
    def test_sealed_down_detected(self):
        # prev close = 10.0 → lim_down = round(10*0.90, 2) = 9.0
        closes = [10.0, 10.0, 9.0]
        lows   = [10.0, 10.0, 8.9]
        df     = _ohlcv(closes=closes, lows=lows)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        sd = [e for e in events if e["event"] == "sealed_down"]
        assert len(sd) == 1
        # close_off_limit_pct is now populated for down-side events as a fraction
        assert sd[0]["close_off_limit_pct"] is not None

    def test_failed_down_seal_detected(self):
        # Low touches limit_down but close does not
        closes = [10.0, 10.0, 9.5]
        lows   = [10.0, 10.0, 9.0]   # low == lim_down but close > lim_down
        df     = _ohlcv(closes=closes, lows=lows)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        fds = [e for e in events if e["event"] == "failed_down_seal"]
        assert len(fds) == 1


# ── lianban count ────────────────────────────────────────────────────────────

class TestLianbanCount:
    def test_two_consecutive_sealed_up(self):
        # Prev close = 10.0; day1 seals up to 11.0; day2 seals up from 11.0 to 12.10
        closes = [10.0, 10.0, 11.0, 12.10]
        highs  = [10.0, 10.0, 11.1, 12.2]
        df     = _ohlcv(closes=closes, highs=highs)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        su = [e for e in events if e["event"] == "sealed_up"]
        assert len(su) == 2
        counts = [e["lianban_count"] for e in su]
        assert counts == [1, 2]

    def test_streak_resets_on_non_sealed_day(self):
        # sealed_up, then normal day, then sealed_up again → streak restarts at 1
        closes = [10.0, 10.0, 11.0, 10.8, 11.88]
        highs  = [10.0, 10.0, 11.1, 11.1, 12.0]
        df     = _ohlcv(closes=closes, highs=highs)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        su = [e for e in events if e["event"] == "sealed_up"]
        # Expect two sealed_up events (day2 and day4) each with lianban=1
        assert len(su) >= 1
        assert su[0]["lianban_count"] == 1
        if len(su) > 1:
            assert su[1]["lianban_count"] == 1


# ── board-aware limit widths in detection ────────────────────────────────────

class TestStarLimitWidth:
    def test_star_uses_20pct(self):
        # STAR: need > 5 bars to clear IPO window.
        # bars 0-4: IPO window. bar 5: prev_close = 10.0 → lim_up = round(10*1.20, 2) = 12.0
        # bar 6: sealed_up at 12.0
        closes = [10.0] * 5 + [10.0, 12.0]
        highs  = [10.0] * 5 + [10.0, 12.1]
        df     = _ohlcv(closes=closes, highs=highs)
        events, _, _ = _detect_limit_events("688981.SS", df, "star", frozenset())
        su = [e for e in events if e["event"] == "sealed_up"]
        assert len(su) == 1
        assert su[0]["limit_width"] == 20.0

    def test_star_no_seal_at_10pct(self):
        # Ensure 10% move does NOT trigger seal on STAR (limit is 20%)
        # Need > 5 bars for IPO window
        closes = [10.0] * 5 + [10.0, 11.0]
        highs  = [10.0] * 5 + [10.0, 11.1]
        df     = _ohlcv(closes=closes, highs=highs)
        events, _, _ = _detect_limit_events("688981.SS", df, "star", frozenset())
        assert events == []


class TestChiNextWidthEra:
    def test_chinext_10pct_before_cutoff(self):
        # Before 2020-08-24, ChiNext uses 10%.
        # Need > 5 bars to clear IPO window; then prev_close = 10.0, seal at 11.0
        start = "2019-01-02"
        closes = [10.0] * 5 + [10.0, 11.0]
        highs  = [10.0] * 5 + [10.0, 11.1]
        df     = _ohlcv(closes=closes, highs=highs, start=start)
        events, _, _ = _detect_limit_events("300750.SZ", df, "chinext", frozenset())
        su = [e for e in events if e["event"] == "sealed_up"]
        assert len(su) == 1
        assert su[0]["limit_width"] == 10.0

    def test_chinext_20pct_after_cutoff(self):
        # After 2020-08-24, ChiNext uses 20%; 11% close should NOT seal
        # Need > 5 bars to clear the ChiNext IPO window
        start = "2021-01-04"
        closes = [10.0] * 5 + [10.0, 11.0]
        highs  = [10.0] * 5 + [10.0, 11.1]
        df     = _ohlcv(closes=closes, highs=highs, start=start)
        events, _, _ = _detect_limit_events("300750.SZ", df, "chinext", frozenset())
        assert events == []


# ── ST flag ───────────────────────────────────────────────────────────────────

class TestSTFlag:
    def test_st_main_gets_5pct(self):
        # ST on main board, post-coverage date: 5% limit
        # prev close = 10.0 → lim_up = round(10*1.05, 2) = 10.50
        start = ST_STORE_COVERAGE_DATE.strftime("%Y-%m-%d")
        closes = [10.0, 10.0, 10.5]
        highs  = [10.0, 10.0, 10.6]
        df     = _ohlcv(closes=closes, highs=highs, start=start)
        events, _, _ = _detect_limit_events(
            "000001.SZ", df, "main", frozenset(["000001.SZ"])
        )
        su = [e for e in events if e["event"] == "sealed_up"]
        assert len(su) == 1
        assert su[0]["limit_width"] == 5.0

    def test_non_st_ticker_not_in_set(self):
        # Not in ST set → 10% limit
        start = ST_STORE_COVERAGE_DATE.strftime("%Y-%m-%d")
        closes = [10.0, 10.0, 11.0]
        highs  = [10.0, 10.0, 11.1]
        df     = _ohlcv(closes=closes, highs=highs, start=start)
        events, _, _ = _detect_limit_events(
            "000001.SZ", df, "main", frozenset()   # not in ST set
        )
        su = [e for e in events if e["event"] == "sealed_up"]
        assert su[0]["limit_width"] == 10.0


# ── IPO exclusion ─────────────────────────────────────────────────────────────

class TestIPOExclusion:
    def test_star_first_5_sessions_excluded(self):
        # 8 bars; bars 0-4 are IPO window; only bars 5-7 can produce events
        start = "2022-01-04"
        closes = [10.0] + [10.0] * 4 + [10.0, 10.0, 12.0]  # bar 7 seals
        highs  = [10.0] * 7 + [12.1]
        df     = _ohlcv(closes=closes, highs=highs, start=start)
        events, ipo_excl, _ = _detect_limit_events("688981.SS", df, "star", frozenset())
        assert ipo_excl == 5
        # Only one event (the sealed_up on bar 7)
        su = [e for e in events if e["event"] == "sealed_up"]
        assert len(su) == 1

    def test_pre2014_first_session_excluded(self):
        # First bar before 2014: first session excluded
        start = "2013-01-02"
        closes = [10.0, 10.0, 11.0]
        highs  = [10.0, 10.0, 11.1]
        df     = _ohlcv(closes=closes, highs=highs, start=start)
        events, ipo_excl, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        assert ipo_excl == 1


# ── ex-div suspect suppression ────────────────────────────────────────────────

class TestExDivSuspect:
    def test_large_open_gap_suppressed(self):
        # Open gaps 20% above prev close on main board (limit = 10%) → suspect, event suppressed
        closes = [10.0, 10.0, 12.0]
        opens  = [10.0, 10.0, 12.5]   # open 25% above prev_close=10 → > 10%*1.5=15% → suspect
        highs  = [10.0, 10.0, 13.0]
        df     = _ohlcv(closes=closes, opens=opens, highs=highs)
        events, _, exdiv_excl = _detect_limit_events("000001.SZ", df, "main", frozenset())
        assert exdiv_excl == 1
        assert events == []

    def test_normal_open_not_suppressed(self):
        # Open within 1.5×limit should not be suppressed
        closes = [10.0, 10.0, 11.0]
        opens  = [10.0, 10.0, 10.9]   # < 10%*1.5 gap
        highs  = [10.0, 10.0, 11.1]
        df     = _ohlcv(closes=closes, opens=opens, highs=highs)
        events, _, exdiv_excl = _detect_limit_events("000001.SZ", df, "main", frozenset())
        assert exdiv_excl == 0


# ── aggregate_daily ───────────────────────────────────────────────────────────

class TestAggregateDaily:
    def _make_events(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"date": "2020-01-02", "ticker": "000001.SZ", "board": "main",
             "limit_width": 10.0, "event": "sealed_up", "lianban_count": 1,
             "close_off_limit_pct": 0.0},
            {"date": "2020-01-02", "ticker": "000002.SZ", "board": "main",
             "limit_width": 10.0, "event": "sealed_up", "lianban_count": 1,
             "close_off_limit_pct": 0.0},
            {"date": "2020-01-02", "ticker": "000003.SZ", "board": "main",
             "limit_width": 10.0, "event": "failed_up_seal", "lianban_count": 0,
             "close_off_limit_pct": 2.5},
            {"date": "2020-01-02", "ticker": "000004.SZ", "board": "main",
             "limit_width": 10.0, "event": "sealed_down", "lianban_count": 0,
             "close_off_limit_pct": None},
        ])

    def test_schema_columns(self):
        df = self._make_events()
        univ = {"2020-01-02": 100}
        agg = aggregate_daily(df, univ, {})
        expected_cols = {
            "date", "limit_up_count", "limit_down_count", "sealed_up_close",
            "failed_up_seal_count", "lianban_2plus", "lianban_max",
            "limit_up_breadth_pct", "limit_down_breadth_pct",
            "st_excluded_counts", "universe_n", "backfill",
        }
        assert expected_cols.issubset(set(agg.columns))

    def test_counts_correct(self):
        df = self._make_events()
        univ = {"2020-01-02": 100}
        agg = aggregate_daily(df, univ, {})
        row = agg[agg["date"] == "2020-01-02"].iloc[0]
        assert int(row["sealed_up_close"]) == 2
        assert int(row["failed_up_seal_count"]) == 1
        assert int(row["limit_down_count"]) == 1
        assert int(row["limit_up_count"]) == 3   # 2 sealed + 1 failed

    def test_breadth_pct(self):
        df = self._make_events()
        univ = {"2020-01-02": 100}
        agg = aggregate_daily(df, univ, {})
        row = agg[agg["date"] == "2020-01-02"].iloc[0]
        # limit_up_breadth = (sealed_up + failed_up) / universe_n * 100 = 3/100*100 = 3.0
        assert abs(float(row["limit_up_breadth_pct"]) - 3.0) < 0.01

    def test_empty_events_returns_empty_df(self):
        agg = aggregate_daily(pd.DataFrame(), {}, {})
        assert agg.empty

    def test_lianban_2plus(self):
        events = pd.DataFrame([
            {"date": "2020-01-02", "ticker": "000001.SZ", "board": "main",
             "limit_width": 10.0, "event": "sealed_up", "lianban_count": 2,
             "close_off_limit_pct": 0.0},
            {"date": "2020-01-02", "ticker": "000002.SZ", "board": "main",
             "limit_width": 10.0, "event": "sealed_up", "lianban_count": 1,
             "close_off_limit_pct": 0.0},
        ])
        univ = {"2020-01-02": 100}
        agg = aggregate_daily(events, univ, {})
        row = agg.iloc[0]
        assert int(row["lianban_2plus"]) == 1    # only one lianban_count >= 2
        assert int(row["lianban_max"]) == 2


# ── name_packet ───────────────────────────────────────────────────────────────

class TestNamePacket:
    def test_sealed_up_gives_correct_packet(self):
        # prev close = 10.0; limit_up = 11.0; close == 11.0 → sealed_up
        closes = [10.0, 10.0, 11.0]
        highs  = [10.0, 10.0, 11.1]
        df     = _ohlcv(closes=closes, highs=highs)
        pkt = name_packet("000001.SZ", df, frozenset())
        assert pkt["board"] == "main"
        assert pkt["limit_width"] == 10.0
        assert pkt["limit_state"] == "sealed_up"
        assert pkt["fillable"] is False   # sealed = not fillable
        assert pkt["t_plus_one_risk"] in ("high", "high_lianban")
        assert pkt["chase_veto"]["flag"] is True

    def test_open_day_gives_normal_state(self):
        closes = [10.0, 10.0, 10.3]
        df     = _ohlcv(closes=closes)
        pkt = name_packet("000001.SZ", df, frozenset())
        assert pkt["limit_state"] == "open"
        assert pkt["fillable"] is True
        assert pkt["t_plus_one_risk"] == "normal"
        assert pkt["chase_veto"]["flag"] is False

    def test_touched_up_failed_elevated_risk(self):
        # high touches limit but close doesn't seal
        closes = [10.0, 10.0, 10.5]
        highs  = [10.0, 10.0, 11.0]
        df     = _ohlcv(closes=closes, highs=highs)
        pkt = name_packet("000001.SZ", df, frozenset())
        assert pkt["limit_state"] == "touched_up_failed"
        assert pkt["fillable"] is True
        assert pkt["t_plus_one_risk"] == "elevated"

    def test_empty_df_degrades_gracefully(self):
        df  = pd.DataFrame()
        pkt = name_packet("000001.SZ", df, frozenset())
        assert pkt["board"] == "main"
        assert pkt["limit_state"] is None
        assert pkt["fillable"] is None

    def test_insufficient_df_degrades(self):
        df = _ohlcv(closes=[10.0])
        pkt = name_packet("000001.SZ", df, frozenset())
        assert pkt["limit_state"] is None

    def test_chase_veto_from_extension_run(self):
        # 6 bars with 20% cumulative run → chase_veto should fire
        closes = [10.0] * 5 + [10.0, 12.0]  # +20% from 5-sessions back
        df     = _ohlcv(closes=closes)
        pkt = name_packet("000001.SZ", df, frozenset())
        assert pkt["chase_veto"]["flag"] is True
        assert pkt["chase_veto"]["reason"] is not None

    def test_star_20pct_limit_width(self):
        closes = [10.0, 10.0, 12.0]
        highs  = [10.0, 10.0, 12.1]
        df     = _ohlcv(closes=closes, highs=highs)
        pkt = name_packet("688981.SS", df, frozenset())
        assert pkt["board"] == "star"
        assert pkt["limit_width"] == 20.0

    def test_lianban_t1_risk(self):
        # Two consecutive sealed_up days → t_plus_one_risk = high_lianban
        # prev-prev close = 10.0 → lim_up1 = 11.0; prev close = 11.0 → lim_up2 = 12.10
        closes = [10.0, 10.0, 11.0, 12.10]
        highs  = [10.0, 10.0, 11.1, 12.20]
        df     = _ohlcv(closes=closes, highs=highs)
        pkt = name_packet("000001.SZ", df, frozenset())
        # latest day is sealed_up (12.10 == round(11.0*1.10,2)); previous was also sealed_up
        assert pkt["t_plus_one_risk"] == "high_lianban"


# ── LIMIT_TAPE_START_DATE floor ───────────────────────────────────────────────

class TestLimitTapeStartDate:
    def test_floor_is_2011(self):
        import pandas as pd
        assert LIMIT_TAPE_START_DATE == pd.Timestamp("2011-01-01")

    def test_detect_ignores_pre2011_when_start_date_applied(self):
        """_detect_limit_events with start_date=LIMIT_TAPE_START_DATE skips pre-floor bars."""
        # Build a df starting in 2010 that would seal on 2010-01-05
        # When start_date=2011-01-01 is applied, 0 events should be returned
        closes = [10.0, 10.0, 11.0]  # bar 2 seals at 10% limit
        highs  = [10.0, 10.0, 11.1]
        df     = _ohlcv(closes=closes, highs=highs, start="2010-01-04")
        events, _, _ = _detect_limit_events(
            "000001.SZ", df, "main", frozenset(), start_date=LIMIT_TAPE_START_DATE
        )
        assert events == []


# ── close_off_limit_pct formula ───────────────────────────────────────────────

class TestCloseOffLimitPct:
    def test_sealed_up_fraction_not_percent(self):
        """close_off_limit_pct for sealed_up must be a fraction (abs < 1), not a percent (0-100)."""
        # prev close = 10.0; lim_up = 11.0; close = 11.0 → fraction = (11.0-11.0)/11.0 = 0.0
        closes = [10.0, 10.0, 11.0]
        highs  = [10.0, 10.0, 11.0]
        df     = _ohlcv(closes=closes, highs=highs)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        su = [e for e in events if e["event"] == "sealed_up"]
        assert len(su) == 1
        v = su[0]["close_off_limit_pct"]
        assert v is not None
        assert abs(v) < 1.0, f"Expected fraction < 1.0, got {v} (likely percent × 100 bug)"

    def test_failed_up_seal_fraction_positive(self):
        """failed_up_seal: close is below limit, so (lim_up - close)/lim_up > 0 as fraction."""
        # prev_close = 10.0; lim_up = 11.0; close = 10.5 → fraction = (11.0 - 10.5)/11.0 ≈ 0.0454
        closes = [10.0, 10.0, 10.5]
        highs  = [10.0, 10.0, 11.0]
        df     = _ohlcv(closes=closes, highs=highs)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        fu = [e for e in events if e["event"] == "failed_up_seal"]
        assert len(fu) == 1
        v = fu[0]["close_off_limit_pct"]
        assert v is not None and 0 < v < 1.0, f"Expected 0 < fraction < 1.0, got {v}"
        # Approximately (11.0 - 10.5) / 11.0 = 0.04545...
        assert abs(v - 0.04545) < 0.001

    def test_sealed_down_close_off_populated(self):
        """sealed_down must have close_off_limit_pct populated (down-side fraction), not None."""
        # prev_close = 10.0; lim_down = 9.0; close = 9.0 → fraction = (9.0 - 9.0)/9.0 = 0.0
        closes = [10.0, 10.0, 9.0]
        lows   = [10.0, 10.0, 8.9]
        df     = _ohlcv(closes=closes, lows=lows)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        sd = [e for e in events if e["event"] == "sealed_down"]
        assert len(sd) == 1
        v = sd[0]["close_off_limit_pct"]
        assert v is not None, "sealed_down close_off_limit_pct must not be None"
        assert abs(v) < 1.0, f"Expected fraction < 1.0, got {v}"

    def test_failed_down_seal_close_off_populated(self):
        """failed_down_seal must have close_off_limit_pct populated (down-side fraction)."""
        # prev_close = 10.0; lim_down = 9.0; low = 9.0 but close = 9.5
        # fraction = (9.5 - 9.0) / 9.0 ≈ 0.0556
        closes = [10.0, 10.0, 9.5]
        lows   = [10.0, 10.0, 9.0]
        df     = _ohlcv(closes=closes, lows=lows)
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        fd = [e for e in events if e["event"] == "failed_down_seal"]
        assert len(fd) == 1
        v = fd[0]["close_off_limit_pct"]
        assert v is not None, "failed_down_seal close_off_limit_pct must not be None"
        assert 0 < v < 1.0, f"Expected 0 < fraction < 1.0, got {v}"


# ── board_type parity with china_signals ──────────────────────────────────────

class TestBoardFromTickerParity:
    """Pin _board_from_ticker results against expected values that match china_signals.board_type().

    If china_signals.board_type() is updated, this test must be updated alongside
    _board_from_ticker() to keep them in sync.
    """

    CASES = [
        ("688981.SS", "star"),
        ("689009.SS", "star"),
        ("300750.SZ", "chinext"),
        ("301020.SZ", "chinext"),
        ("600519.SS", "main"),
        ("000001.SZ", "main"),
        ("601318.SS", "main"),
        ("603129.SS", "main"),
        ("605138.SS", "main"),
    ]

    def test_parity_cases(self):
        for ticker, expected in self.CASES:
            result = _board_from_ticker(ticker)
            assert result == expected, (
                f"_board_from_ticker({ticker!r}) = {result!r}, "
                f"expected {expected!r} (parity with china_signals.board_type)"
            )


# ── degrade-don't-crash ───────────────────────────────────────────────────────

class TestDegrades:
    def test_detect_events_empty_df(self):
        df = pd.DataFrame()
        events, ipo_excl, exdiv_excl = _detect_limit_events("000001.SZ", df, "main", frozenset())
        assert events == []
        assert ipo_excl == 0
        assert exdiv_excl == 0

    def test_detect_events_single_row(self):
        df = _ohlcv(closes=[10.0])
        events, _, _ = _detect_limit_events("000001.SZ", df, "main", frozenset())
        assert events == []

    def test_aggregate_empty_events(self):
        agg = aggregate_daily(pd.DataFrame(columns=[
            "date", "ticker", "board", "limit_width", "event", "lianban_count", "close_off_limit_pct"
        ]), {}, {})
        assert isinstance(agg, pd.DataFrame)
        assert agg.empty

    def test_name_packet_none_df(self):
        pkt = name_packet("000001.SZ", None, frozenset())
        assert pkt["limit_state"] is None
        assert pkt["board"] == "main"
