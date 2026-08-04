"""W4 — the earnings feed must be trustworthy AND catalyst-aware.

PROPHET_US_TREND_INTELLIGENCE masterplan §W4.  The 2026-08-03 case this pins:

    PLTR's row held the RIGHT date — next_date=2026-08-03, the day it reported — and
    the one earnings consumer in the pick chain still no-opped on it.  The row's
    as_of was 2026-06-19, 30 trading days old, so ``earnings_blackout.assess``
    applied its fail-open law (row_stale -> in_blackout=False) and said nothing.
    1,361 of 1,364 rows were in that state.  The veto was not wrong; it was silent.

Three defects, three fixes, one test file:

1. **Starvation.**  The budgeted surprise-history drip took the ALPHABETICAL head of
   the stale set (``sorted(cal)[:max_new]``).  With REFRESH_DAYS=7 re-staling the head
   every week, the queue frontier stalls at ~REFRESH_DAYS x max_new names and the tail
   of the alphabet is never dripped at all.  ``drip_order`` makes it oldest-first.
2. **Silence.**  Nothing graded the SHARE of the store that had aged past the veto's
   own 10-session trust line.  ``assess_staleness`` does, and
   ``_emit_staleness_annotation`` pages with a line-start ``::warning``.
3. **No catalyst context.**  Board rows carried a proximity chip and nothing else.
   ``engine.earnings_catalyst`` adds ``days_to_report`` / ``reports_within_7`` /
   ``stale`` and a post-earnings ``earnings_reaction``.

TIER: everything here is DISPLAY (masterplan §0 G0.1).  The blackout veto's semantics —
fail-open included — are deliberately unchanged, and ``test_veto_semantics_untouched``
pins that.

Hermetic: no network, no live stores, no wall-clock dependence (every call takes an
explicit ``today``).

Run: .venv/bin/python -m pytest tests/test_earnings_w4_feed.py -q
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import collectors.equity_earnings as ee  # noqa: E402
from engine import earnings_blackout as eb  # noqa: E402
from engine import earnings_catalyst as ec  # noqa: E402

# A Monday, and the day PLTR reported in the case above.
CASE_DAY = date(2026, 8, 3)


def _stamp(d: date) -> str:
    return f"{d.isoformat()}T02:00:00+00:00"


# ═══════════════════════════════════════════════════════════════════════════
# 1. ROTATION — the budget must reach every name
# ═══════════════════════════════════════════════════════════════════════════

class TestDripRotation:

    def test_never_dripped_names_sort_ahead_of_every_dated_one(self):
        stamps = {"AAA": _stamp(date(2026, 7, 1)), "BBB": None, "CCC": _stamp(date(2026, 6, 1))}
        assert ee.drip_order(["AAA", "BBB", "CCC"], stamps) == ["BBB", "CCC", "AAA"]

    def test_order_is_oldest_stamp_first_not_alphabetical(self):
        """The whole bug in one assertion: alphabetical order is NOT rotation."""
        stamps = {"AAA": _stamp(date(2026, 8, 1)),    # freshest, alphabetically first
                  "MMM": _stamp(date(2026, 7, 1)),
                  "ZZZ": _stamp(date(2026, 6, 1))}    # oldest, alphabetically last
        assert ee.drip_order(["AAA", "MMM", "ZZZ"], stamps) == ["ZZZ", "MMM", "AAA"]

    def test_ties_break_on_ticker_so_a_set_input_is_deterministic(self):
        stamps = {t: _stamp(date(2026, 7, 1)) for t in ("QQQ", "AAA", "MMM")}
        assert ee.drip_order({"QQQ", "AAA", "MMM"}, stamps) == ["AAA", "MMM", "QQQ"]
        assert ee.drip_order({"MMM", "QQQ", "AAA"}, stamps) == ["AAA", "MMM", "QQQ"]

    def test_unreadable_stamp_is_treated_as_never_dripped(self):
        """Fail-safe direction: an unparseable stamp buys a front-of-queue re-fetch,
        never a permanent seat at the back."""
        stamps = {"AAA": _stamp(date(2026, 7, 1)), "JUNK": "not-a-date",
                  "NAN": float("nan")}
        head = ee.drip_order(["AAA", "JUNK", "NAN"], stamps)[:2]
        assert set(head) == {"JUNK", "NAN"}

    def test_accepts_the_store_column_as_a_pandas_series(self):
        col = pd.Series({"AAA": _stamp(date(2026, 8, 1)), "ZZZ": _stamp(date(2026, 6, 1))})
        assert ee.drip_order(["AAA", "ZZZ"], col) == ["ZZZ", "AAA"]

    def test_no_name_is_starved_across_a_full_rotation(self):
        """REGRESSION — the defect, simulated.

        Production shape: ~1,500 names, max_new=120/night, REFRESH_DAYS=7.  Under the
        old alphabetical rule the frontier stalls at (REFRESH_DAYS + 1) x max_new = 960
        names — on night 9 the head from night 1 re-stales and, still sorting first,
        takes the budget back.  The remaining ~540 names are never dripped, ever, and
        nothing in the store shows it: the cheap calendar sweep keeps re-stamping their
        `as_of` nightly while their surprise history stays empty.
        Under oldest-first every name is served within ceil(N / budget) nights.
        """
        names = [f"TK{i:04d}" for i in range(1500)]
        budget, refresh_days = 120, 7

        def _simulate(order_fn, nights):
            last: dict[str, date | None] = {t: None for t in names}
            day = date(2026, 1, 1)
            for _ in range(nights):
                stale = [t for t in names
                         if last[t] is None or (day - last[t]).days > refresh_days]
                for t in order_fn(stale, last)[:budget]:
                    last[t] = day
                day += timedelta(days=1)
            return last

        alphabetical = _simulate(lambda s, _last: sorted(s), nights=40)
        rotated = _simulate(
            lambda s, last: ee.drip_order(
                s, {t: (_stamp(d) if d else None) for t, d in last.items()}),
            nights=40)

        never_alpha = [t for t, d in alphabetical.items() if d is None]
        never_rot = [t for t, d in rotated.items() if d is None]
        assert len(never_alpha) == 1500 - (refresh_days + 1) * budget == 540, (
            "the simulation no longer reproduces the starvation it exists to pin "
            f"({len(never_alpha)} names starved) — re-check budget/refresh clock")
        assert never_rot == [], (
            f"{len(never_rot)} names were never dripped under oldest-first rotation")

    def test_fetch_earnings_drips_the_oldest_first(self, monkeypatch, tmp_path):
        """End-to-end through fetch_earnings: the cap goes to the oldest stamps."""
        universe = {f"TK{i:03d}" for i in range(6)}
        cal = {t: {"next_date": "2026-08-14", "next_time": "time-after-hours",
                   "eps_forecast": 1.0} for t in sorted(universe)}
        # TK000/TK001 (alphabetically first) are the FRESHEST surprise stamps;
        # TK004/TK005 are the oldest. A budget of 2 must pick the latter.
        existing = pd.DataFrame([
            {"ticker": t, "next_date": "2026-05-01", "next_time": None,
             "eps_forecast": None, "surprises_json": json.dumps([{"qtr": "Q1"}]),
             "surprises_as_of": _stamp(date(2026, 1, 1) + timedelta(days=100 - 10 * i)),
             "as_of": _stamp(date(2026, 4, 1))}
            for i, t in enumerate(sorted(universe))
        ]).set_index("ticker")
        existing.to_parquet(tmp_path / "earnings.parquet")

        seen: list[str] = []
        monkeypatch.setattr(ee, "_calendar_sweep", lambda s, u: ({t: dict(cal[t]) for t in u}, False))
        monkeypatch.setattr(ee, "_surprises", lambda s, sym: seen.append(sym) or [])
        monkeypatch.setattr(ee, "_universe", lambda: set(universe))
        monkeypatch.setattr(ee, "_cache_path", lambda: tmp_path / "earnings.parquet")
        monkeypatch.setattr(ee.time, "sleep", lambda *_a, **_k: None)

        ee.fetch_earnings(max_new=2)
        assert seen == ["TK005", "TK004"], f"budget went to {seen}, not the oldest stamps"


# ═══════════════════════════════════════════════════════════════════════════
# 2. STALENESS ALARM
# ═══════════════════════════════════════════════════════════════════════════

def _store(rows: dict[str, tuple[str | None, str | None]]) -> pd.DataFrame:
    """{ticker: (next_date, as_of)} -> the store's frame shape."""
    return pd.DataFrame(
        [{"ticker": t, "next_date": nd, "as_of": ao} for t, (nd, ao) in rows.items()]
    ).set_index("ticker")


class TestStalenessAlarm:

    def test_fresh_store_does_not_warn(self):
        df = _store({f"TK{i}": ("2026-08-20", _stamp(CASE_DAY)) for i in range(50)})
        rep = ee.assess_staleness(df, CASE_DAY)
        assert rep == {"total": 50, "stale": 0, "stale_share": 0.0,
                       "imminent": 0, "imminent_stale": 0, "should_warn": False}

    def test_share_threshold_is_strictly_above_20_percent(self):
        """20/100 stale is exactly at the floor and must NOT warn; 21/100 must."""
        old = _stamp(date(2026, 6, 19))
        far = "2026-11-20"                      # outside the imminent window
        at = {f"TK{i}": (far, old if i < 20 else _stamp(CASE_DAY)) for i in range(100)}
        over = {f"TK{i}": (far, old if i < 21 else _stamp(CASE_DAY)) for i in range(100)}
        assert ee.assess_staleness(_store(at), CASE_DAY)["should_warn"] is False
        assert ee.assess_staleness(_store(over), CASE_DAY)["should_warn"] is True

    def test_one_stale_imminent_row_warns_at_any_share(self):
        """PLTR-class: a single stale row reporting within 5 sessions is one silent
        no-op on the day it mattered, so it alarms on its own."""
        rows = {f"TK{i}": ("2026-11-20", _stamp(CASE_DAY)) for i in range(200)}
        rows["PLTR"] = ("2026-08-03", _stamp(date(2026, 6, 19)))
        rep = ee.assess_staleness(_store(rows), CASE_DAY)
        assert rep["stale"] == 1 and rep["stale_share"] < 0.20
        assert rep["imminent_stale"] == 1 and rep["should_warn"] is True

    def test_stale_age_line_matches_the_vetos_own_trust_line(self):
        """The alarm must grade the same 10-session threshold at which
        earnings_blackout.assess starts failing open, or it grades a different
        question than the one that hurt."""
        assert ee.STALE_AGE_TD == eb._STALE_AGE_TD

    @pytest.mark.parametrize("age_td,expect_stale", [(9, 0), (10, 0), (11, 1)])
    def test_boundary_is_strictly_older_than_ten_sessions(self, age_td, expect_stale):
        sessions = ec.nyse_calendar.sessions_between(date(2026, 6, 1), CASE_DAY)
        as_of = sessions[-1 - age_td]           # exactly age_td sessions before CASE_DAY
        df = _store({"TK": ("2026-11-20", _stamp(as_of))})
        assert ee.assess_staleness(df, CASE_DAY)["stale"] == expect_stale

    def test_unparseable_as_of_counts_stale(self):
        """Cannot be shown fresh -> counts stale. A store that lost its stamps is not
        a store that is up to date."""
        df = _store({"TK": ("2026-11-20", None)})
        assert ee.assess_staleness(df, CASE_DAY)["stale"] == 1

    def test_passed_next_date_is_not_imminent(self):
        df = _store({"TK": ("2026-07-20", _stamp(date(2026, 6, 19)))})
        rep = ee.assess_staleness(df, CASE_DAY)
        assert rep["stale"] == 1 and rep["imminent"] == 0

    def test_empty_store_never_warns(self):
        assert ee.assess_staleness(pd.DataFrame(), CASE_DAY)["should_warn"] is False
        assert ee.assess_staleness(None, CASE_DAY)["should_warn"] is False

    def test_annotation_starts_the_line_and_is_not_logged(self, capsys):
        """House law: GitHub drops an annotation that does not start its line, and
        every builder here logs through a level-prefixing format.  So this must be a
        bare print — asserted on stdout, at position 0 of the line."""
        rows = {f"TK{i}": ("2026-08-05", _stamp(date(2026, 6, 19))) for i in range(30)}
        ee._emit_staleness_annotation(_store(rows), CASE_DAY)
        line = capsys.readouterr().out.strip().splitlines()[0]
        assert line.startswith("::warning title=earnings-staleness::"), line
        assert "30/30" in line and "30 imminent-report rows stale" in line

    def test_annotation_is_silent_on_a_healthy_store(self, capsys):
        df = _store({f"TK{i}": ("2026-08-20", _stamp(CASE_DAY)) for i in range(30)})
        ee._emit_staleness_annotation(df, CASE_DAY)
        assert capsys.readouterr().out == ""

    def test_the_2026_08_03_case_would_have_fired(self, capsys):
        """G0.3 case receipt, reproduced from the store's real shape: 1,361 rows at
        as_of 2026-06-19 with PLTR reporting that very day."""
        rows = {f"TK{i:04d}": ("2026-08-05", _stamp(date(2026, 6, 19))) for i in range(1361)}
        rows.update({t: ("2026-09-01", _stamp(date(2026, 7, 28)))
                     for t in ("AAPL", "NVDA", "JPM")})
        rows["PLTR"] = ("2026-08-03", _stamp(date(2026, 6, 19)))
        rep = ee._emit_staleness_annotation(_store(rows), CASE_DAY)
        assert rep["should_warn"] and rep["stale_share"] > 0.99
        assert rep["imminent_stale"] >= 1
        assert capsys.readouterr().out.startswith("::warning title=earnings-staleness::")


# ═══════════════════════════════════════════════════════════════════════════
# 3. days_to_report — trading-day math
# ═══════════════════════════════════════════════════════════════════════════

class TestDaysToReport:

    def test_friday_to_monday_is_one_trading_day_across_three_calendar_days(self):
        fri, mon = date(2026, 8, 7), date(2026, 8, 10)
        assert fri.weekday() == 4 and mon.weekday() == 0
        assert (mon - fri).days == 3
        assert ec.trading_days_between(fri, mon) == 1

    def test_weekend_alone_is_zero_trading_days(self):
        fri, sun = date(2026, 8, 7), date(2026, 8, 9)
        assert ec.trading_days_between(fri, sun) == 0

    def test_same_day_is_zero_and_the_past_is_negative(self):
        assert ec.trading_days_between(CASE_DAY, CASE_DAY) == 0
        assert ec.trading_days_between(date(2026, 8, 10), date(2026, 8, 7)) == -1

    def test_holiday_is_not_a_trading_day(self):
        """Thanksgiving 2026 falls on Thursday 11-26; Wed->Fri is ONE session."""
        wed, fri = date(2026, 11, 25), date(2026, 11, 27)
        assert wed.weekday() == 2 and fri.weekday() == 4
        assert ec.trading_days_between(wed, fri) == 1

    def test_weekend_spanning_row_reports_trading_days_not_calendar_days(self):
        """A Friday row looking at the next Monday: days_to_report is the SESSION
        count (1), while the shipped chip stays in calendar days (3)."""
        fri = date(2026, 8, 7)
        f = ec.catalyst_fields("2026-08-10", _stamp(fri), fri)
        assert f["days_to_report"] == 1
        assert f["reports_within_7"] is True and f["stale"] is False
        payload = ec.board_row_fields(
            {"next_date": "2026-08-10", "next_time": "time-pre-market",
             "days_to_earnings": 1, "stale": False, "in_blackout": True}, fri)
        assert payload["earnings_soon"]["days_to"] == 3          # calendar, unchanged
        assert payload["earnings_soon"]["days_to_report"] == 1   # sessions, new

    def test_reports_within_7_boundary(self):
        sessions = ec.nyse_calendar.sessions_between(CASE_DAY, date(2026, 9, 30))
        assert ec.catalyst_fields(sessions[7], _stamp(CASE_DAY), CASE_DAY)["reports_within_7"] is True
        assert ec.catalyst_fields(sessions[8], _stamp(CASE_DAY), CASE_DAY)["reports_within_7"] is False

    def test_a_passed_report_is_negative_and_not_within_7(self):
        f = ec.catalyst_fields("2026-07-30", _stamp(CASE_DAY), CASE_DAY)
        assert f["days_to_report"] < 0 and f["reports_within_7"] is False

    def test_stale_row_nulls_the_countdown_and_says_so(self):
        """PLTR's exact row.  The date was right; the stamp was six weeks old.  A
        countdown printed off that stamp is the confident-but-wrong shape W4 removes."""
        f = ec.catalyst_fields("2026-08-03", _stamp(date(2026, 6, 19)), CASE_DAY)
        assert f == {"days_to_report": None, "reports_within_7": None,
                     "stale": True, "as_of_age_td": 30}

    def test_reports_within_7_is_null_not_false_when_unknown(self):
        """A False would assert 'does not report within 7 days'.  A row stamped six
        weeks ago cannot know that, and the whole W4 complaint is confident silence."""
        assert ec.catalyst_fields("2026-08-03", _stamp(date(2026, 6, 19)),
                                  CASE_DAY)["reports_within_7"] is None

    def test_missing_next_date_nulls_without_claiming_staleness(self):
        f = ec.catalyst_fields(None, _stamp(CASE_DAY), CASE_DAY)
        assert f["days_to_report"] is None and f["stale"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 4. earnings_reaction — the day-0 convention
# ═══════════════════════════════════════════════════════════════════════════

# Mon 07-27 .. Mon 08-03, all sessions. 100 -> 102 -> 104 -> 106 -> 108 (Fri) -> 120 (Mon).
_CLOSES = pd.Series({
    pd.Timestamp("2026-07-27"): 100.0, pd.Timestamp("2026-07-28"): 102.0,
    pd.Timestamp("2026-07-29"): 104.0, pd.Timestamp("2026-07-30"): 106.0,
    pd.Timestamp("2026-07-31"): 108.0, pd.Timestamp("2026-08-03"): 120.0,
})


class TestReactionConvention:

    def test_pre_market_report_is_graded_on_its_own_close(self):
        """Pre-market print on Monday 08-03 -> day0 = 08-03, vs Friday 07-31's close."""
        rx = ec.reaction(date(2026, 8, 3), "time-pre-market", _CLOSES, CASE_DAY)
        assert rx["day0"] == "2026-08-03" and rx["prev_session"] == "2026-07-31"
        assert rx["day0_move_pct"] == pytest.approx((120 / 108 - 1) * 100, abs=0.01)
        assert rx["after_hours"] is False and rx["basis"] == "close_vs_prior_close"

    def test_after_hours_report_is_graded_on_the_NEXT_session(self):
        """After-hours print on Friday 07-31 -> day0 = Monday 08-03 (the first close
        that can contain the news), vs Friday's close."""
        rx = ec.reaction(date(2026, 7, 31), "time-after-hours", _CLOSES, CASE_DAY)
        assert rx["day0"] == "2026-08-03" and rx["prev_session"] == "2026-07-31"
        assert rx["day0_move_pct"] == pytest.approx((120 / 108 - 1) * 100, abs=0.01)
        assert rx["after_hours"] is True

    def test_after_hours_skips_the_weekend_not_just_one_calendar_day(self):
        rx = ec.reaction(date(2026, 7, 31), "time-after-hours", _CLOSES, CASE_DAY)
        assert rx["day0"] == "2026-08-03", "day0 must be the next SESSION, not 08-01"

    def test_unsupplied_time_falls_back_to_the_report_days_own_close(self):
        """PLTR's row carries next_time='time-not-supplied'.  Unknown time is treated
        as already-in-that-close — one rule, no intraday data, no timezone math."""
        rx = ec.reaction(date(2026, 8, 3), "time-not-supplied", _CLOSES, CASE_DAY)
        assert rx["after_hours"] is False and rx["day0"] == "2026-08-03"
        assert rx["day0_move_pct"] == pytest.approx(11.11, abs=0.01)

    def test_a_report_older_than_the_window_attaches_nothing(self):
        assert ec.reaction(date(2026, 7, 20), None, _CLOSES, CASE_DAY) is None

    def test_the_window_boundary_is_five_sessions(self):
        five = ec.nyse_calendar.sessions_between(date(2026, 7, 1), CASE_DAY)[-6]
        six = ec.nyse_calendar.sessions_between(date(2026, 7, 1), CASE_DAY)[-7]
        assert ec.reaction(five, None, _CLOSES, CASE_DAY) is not None
        assert ec.reaction(six, None, _CLOSES, CASE_DAY) is None

    def test_a_future_report_attaches_nothing(self):
        assert ec.reaction(date(2026, 8, 20), None, _CLOSES, CASE_DAY) is None

    def test_missing_price_data_nulls_WITH_disclosure(self):
        """Nulls printed, not hidden: the key is still attached and `basis` names what
        was missing, so a reader is never shown a blank that looks like a zero move."""
        rx = ec.reaction(date(2026, 8, 3), "time-pre-market", None, CASE_DAY)
        assert rx["day0_move_pct"] is None and rx["basis"] == "no_price_data"
        rx2 = ec.reaction(date(2026, 8, 3), "time-pre-market",
                          _CLOSES.drop(pd.Timestamp("2026-08-03")), CASE_DAY)
        assert rx2["day0_move_pct"] is None and rx2["basis"] == "close_missing_for_day0"

    def test_after_hours_print_whose_day0_has_not_traded_yet_discloses(self):
        rx = ec.reaction(CASE_DAY, "time-after-hours", _CLOSES, CASE_DAY)
        assert rx["day0_move_pct"] is None and rx["basis"] == "day0_not_yet_traded"

    def test_report_date_comes_from_next_date_passage_or_surprise_history(self):
        assert ec.latest_report_date("2026-07-30", None, CASE_DAY) == date(2026, 7, 30)
        # a FUTURE next_date is not a report that happened
        assert ec.latest_report_date("2026-08-20", None, CASE_DAY) is None
        # Nasdaq's M/D/YYYY surprise rows parse, and the most recent passed date wins
        assert ec.latest_report_date(
            "2026-07-30", [{"reported": "7/29/2026"}, {"reported": "8/1/2026"}],
            CASE_DAY) == date(2026, 8, 1)


# ═══════════════════════════════════════════════════════════════════════════
# 5. SCHEMA — us_standouts rows carry the new keys, and nothing gates on them
# ═══════════════════════════════════════════════════════════════════════════

_NEW_ROW_KEYS = {"days_to_report", "reports_within_7", "stale"}


class TestBoardRowSchema:

    def _assessment(self, **kw) -> dict:
        base = {"in_blackout": False, "days_to_earnings": 5, "next_date": "2026-08-10",
                "next_time": "time-after-hours", "as_of_age_td": 0, "stale": False,
                "reason": "outside_window"}
        base.update(kw)
        return base

    def test_chip_rows_carry_the_new_catalyst_keys(self):
        es = ec.board_row_fields(self._assessment(), CASE_DAY)["earnings_soon"]
        assert _NEW_ROW_KEYS <= set(es)
        assert es["days_to_report"] == 5 and es["reports_within_7"] is True

    def test_chip_shape_is_otherwise_unchanged(self):
        """The pre-W4 keys must survive byte-identical — W4 ships no surface change."""
        es = ec.board_row_fields(self._assessment(), CASE_DAY)["earnings_soon"]
        assert es["days_to"] == 7                       # calendar days to 08-10
        assert es["next_date"] == "2026-08-10"
        assert es["next_time"] == "after close"         # the display label, not the token
        assert es["in_blackout"] is False
        assert es["chip_en"] == "Reports in 7 d" and es["chip_zh"] == "7日后公布业绩"

    @pytest.mark.parametrize("cal_days,en,zh", [
        (0, "Reports today", "今日公布业绩"),
        (1, "Reports tomorrow", "明日公布业绩"),
        (7, "Reports in 7 d", "7日后公布业绩"),
    ])
    def test_chip_copy_is_pinned_to_the_shipping_function(self, cal_days, en, zh):
        assert ec.chip_texts(cal_days) == (en, zh)

    def test_stale_row_gets_the_DISCLOSURE_shape_and_no_chip(self):
        """The W4 addition.  A stale row now says so — and carries neither `days_to`
        nor chip text, which is exactly why no surface renders it this wave."""
        es = ec.board_row_fields(
            self._assessment(stale=True, days_to_earnings=None, as_of_age_td=30,
                             next_date="2026-08-03"), CASE_DAY)["earnings_soon"]
        assert es["stale"] is True and es["days_to_report"] is None
        assert es["reports_within_7"] is None
        assert "days_to" not in es and "chip_en" not in es and "chip_zh" not in es
        assert es["in_blackout"] is False

    def test_no_chip_beyond_the_14_session_window_but_context_still_ships(self):
        es = ec.board_row_fields(
            self._assessment(days_to_earnings=20, next_date="2026-08-31"),
            CASE_DAY)["earnings_soon"]
        assert "days_to" not in es and es["days_to_report"] == 20

    def test_a_row_whose_freshness_was_never_checked_says_so(self):
        """PLTR's live shape, and the subtlest trap in this wave.

        ``assess`` short-circuits on ``next_date_in_past`` BEFORE it reads as_of, and
        returns ``stale=False, as_of_age_td=None``.  Taking that False at face value
        stamps `stale: false` on a six-week-old row — the W4 complaint recursed.  The
        payload must say `None` (never checked), not `False` (checked and fresh).
        """
        es = ec.board_row_fields(
            self._assessment(next_date="2026-07-31", days_to_earnings=None,
                             as_of_age_td=None, stale=False,
                             reason="next_date_in_past"), CASE_DAY)["earnings_soon"]
        assert es["stale"] is None, "an unchecked row must not claim freshness"
        assert es["as_of_age_td"] is None
        assert es["days_to_report"] == -1        # the recorded date is still a fact

    def test_a_checked_fresh_row_says_false_not_none(self):
        es = ec.board_row_fields(self._assessment(as_of_age_td=2),
                                 CASE_DAY)["earnings_soon"]
        assert es["stale"] is False and es["as_of_age_td"] == 2

    def test_missing_assessment_attaches_nothing(self):
        assert ec.board_row_fields(None, CASE_DAY) == {"earnings_soon": None,
                                                       "earnings_reaction": None}

    def test_reaction_rides_along_on_a_just_reported_row(self):
        payload = ec.board_row_fields(
            self._assessment(next_date="2026-07-31", days_to_earnings=None,
                             reason="next_date_in_past"),
            CASE_DAY, closes=_CLOSES)
        assert payload["earnings_reaction"]["day0"] == "2026-08-03"
        assert payload["earnings_reaction"]["day0_move_pct"] == pytest.approx(11.11, abs=0.01)

    def test_the_contract_registers_both_keys_as_may_be_absent(self):
        from scripts.export_signal_contracts import ARTIFACT_MANIFEST
        entry = next(e for e in ARTIFACT_MANIFEST
                     if e["artifact"] == "site/factordata/us_standouts.json")
        assert entry["schema_version"] == "1.7.0"
        assert {"earnings_reaction", "earnings_soon"} <= set(entry["optional_fields"])
        assert {"earnings_reaction", "earnings_soon"} <= set(entry["schema_item_fields"])
        # optional_fields is the may-be-absent register, NOT a promotion: neither key
        # may claim required status until a committed render proves it always ships.
        assert not ({"earnings_reaction", "earnings_soon"} & set(entry["schema_fields"]))

    def test_the_live_artifact_still_parses_and_keeps_its_lanes(self):
        """The committed board predates this build, so it does NOT yet carry the new
        keys — asserting their presence here would pin an unsatisfiable state.  What we
        CAN pin: the rows W4 touches are shaped as expected and the artifact is intact."""
        p = ROOT / "site" / "factordata" / "us_standouts.json"
        if not p.exists():
            pytest.skip("us_standouts.json not present in this checkout")
        doc = json.loads(p.read_text())
        rows = [r for lane in ("buy", "watch", "laggards", "ran")
                for r in (doc.get(lane) or [])]
        assert rows, "us_standouts has no rows to grade"
        for r in rows:
            es = r.get("earnings_soon")
            if es is not None:
                assert isinstance(es, dict) and "in_blackout" in es


class TestNothingGatesOnTheNewFields:
    """G0.1: display tier means display tier.  These are the mechanical proofs."""

    _SOURCES = ("engine", "scripts", "app", "admin", "lib", "collectors", "templates")

    def _readers(self, field: str) -> set[str]:
        """Files that READ the field off an object — the shape a consumer has.

        Keyed on access syntax (``get("f")`` / ``["f"]`` / ``.f``) rather than on the
        bare word, because the bare word is not evidence: ``earnings_reaction`` is also
        a hot-tape TRIGGER NAME (engine/marketing/hot_tape.py) living in a different
        artifact's vocabulary, and a substring match would flag it forever while
        teaching nothing.  A gate reads a value; a vocabulary entry does not.
        """
        pat = re.compile(r"""(?:get\(\s*['"]%s['"]|\[\s*['"]%s['"]\s*\]|\.%s\b)"""
                         % (field, field, field))
        out = set()
        for d in self._SOURCES:
            for p in (ROOT / d).rglob("*"):
                if p.suffix not in {".py", ".j2", ".js", ".html"} or not p.is_file():
                    continue
                try:
                    text = p.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if pat.search(text):
                    out.add(p.relative_to(ROOT).as_posix())
        return out

    def test_the_reader_probe_can_actually_see_a_reader(self):
        """MUTATION GUARD — a grep that matches nothing passes vacuously.  `days_to`
        IS read (dashboard.html.j2 gates the chip on it), so the probe must find it."""
        assert "templates/dashboard.html.j2" in self._readers("days_to")

    @pytest.mark.parametrize("field", ["days_to_report", "reports_within_7",
                                       "earnings_reaction"])
    def test_only_the_producer_reads_the_new_fields(self, field):
        """The ONLY files allowed to read a W4 field are the module that computes it
        and the builder that attaches it.  A third reader is a consumer, and a consumer
        is how a display field quietly becomes an authority."""
        allowed = {"engine/earnings_catalyst.py", "scripts/build_stock_library.py"}
        assert self._readers(field) <= allowed, (
            f"{field} is read outside the producer: "
            f"{sorted(self._readers(field) - allowed)}")

    def test_the_rank_engine_still_gates_only_on_in_blackout(self):
        """engine/us_board_rank is the one place earnings touches the pick chain.  It
        may read `earnings_soon.in_blackout` and nothing else W4 added."""
        src = (ROOT / "engine" / "us_board_rank.py").read_text()
        assert 'earnings_soon") or {}).get("in_blackout")' in src
        for f in ("days_to_report", "reports_within_7", "earnings_reaction"):
            assert f not in src, f"us_board_rank now reads {f} — that is a promotion"

    def test_veto_semantics_untouched(self, tmp_path):
        """The blackout veto still fails OPEN on a stale row.  W4's answer to that
        silence is the alarm and the `stale` flag — never a change to the verdict."""
        eb.clear_cache()
        p = tmp_path / "earnings.parquet"
        pd.DataFrame([
            {"ticker": "PLTR", "next_date": CASE_DAY.isoformat(),
             "next_time": "time-not-supplied", "eps_forecast": None,
             "surprises_json": "[]", "surprises_as_of": None,
             "as_of": _stamp(date(2026, 6, 19))},
        ]).set_index("ticker").to_parquet(p)
        v = eb.assess("PLTR", today=CASE_DAY, store_path=p)
        eb.clear_cache()
        assert v["in_blackout"] is False and v["stale"] is True
        assert v["reason"] == "row_stale"

    def test_surprise_accessor_is_read_only_and_fail_soft(self, tmp_path):
        eb.clear_cache()
        p = tmp_path / "earnings.parquet"
        pd.DataFrame([
            {"ticker": "AAA", "next_date": "2026-08-10", "next_time": None,
             "eps_forecast": None,
             "surprises_json": json.dumps([{"qtr": "Q2", "reported": "7/29/2026"}]),
             "surprises_as_of": None, "as_of": _stamp(CASE_DAY)},
            {"ticker": "BBB", "next_date": "2026-08-10", "next_time": None,
             "eps_forecast": None, "surprises_json": "not json",
             "surprises_as_of": None, "as_of": _stamp(CASE_DAY)},
        ]).set_index("ticker").to_parquet(p)
        assert eb.surprise_history("aaa", p)[0]["reported"] == "7/29/2026"
        assert eb.surprise_history("BBB", p) == []
        assert eb.surprise_history("NOPE", p) == []
        eb.clear_cache()
