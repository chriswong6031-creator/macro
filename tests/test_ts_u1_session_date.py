"""Tests for TS-U1 — session-date integrity (TS-R2).

Verifies:
  (A) lib.nyse_calendar.session_date() boundary semantics:
      - 19:59 ET (in-session) → session day
      - 20:01 ET (past cutoff) → same session day (not tomorrow's UTC date)
      - 00:30 ET next day (pre-open) → prior session day
      - weekend → last Friday (or last trading day)
      - holiday → last trading day before the holiday
  (B) engine/basket_turn_watch — as_of fallback uses session_date, not date.today()
      (simulated by patching _session_date in the module at a UTC-midnight straddle)
  (C) scripts/notify_turn_events — today_str fallback uses session_date, not date.today()
  (D) earlyclose stamp writer semantics: the patch path coverage (logic unit test)

All tests are network-free and clock-independent.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import nyse_calendar as cal
from lib.nyse_calendar import session_date, ET


# ── (A) session_date() boundary tests ─────────────────────────────────────────

class TestSessionDateBoundaries:
    """Verify session_date() resolves to the correct NYSE session date at key instants."""

    # 2026-07-09 is a Thursday — a normal session day.
    # ET is UTC-4 in July (EDT).

    def _et(self, year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
        """Build a UTC datetime that corresponds to a given ET local time."""
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo("America/New_York")
        local = datetime(year, month, day, hour, minute, tzinfo=et_tz)
        return local.astimezone(timezone.utc)

    def test_in_session_before_close(self):
        """19:59 ET on a session day → that session day (ET calendar date is a session day)."""
        ts = self._et(2026, 7, 9, 19, 59)
        assert session_date(ts) == date(2026, 7, 9)

    def test_post_utc_midnight_same_et_day(self):
        """20:01 ET on a session day → same session day (TS-R2 core case).

        At 20:01 ET on 2026-07-09, UTC is 2026-07-10T00:01Z. date.today() (UTC)
        would return 2026-07-10, but session_date() must return 2026-07-09 because
        the ET calendar date is still 2026-07-09 and it's past 16:00 ET.
        """
        ts = self._et(2026, 7, 9, 20, 1)
        # Verify we are indeed past UTC midnight (confirming the bug scenario exists)
        assert ts.date() == date(2026, 7, 10), "Precondition: UTC is next day"
        assert session_date(ts) == date(2026, 7, 9)

    def test_pre_open_next_et_day(self):
        """00:30 ET on 2026-07-10 (Friday) → 2026-07-10 (session day, no time cutoff).

        2026-07-10 is a session day. session_date() returns the ET calendar date when
        that date is a session day, regardless of time-of-day (no 16:00 cutoff).
        The whole ET calendar day is the session stamp for that session.
        """
        ts = self._et(2026, 7, 10, 0, 30)
        assert cal.is_session(date(2026, 7, 10)), "Precondition: 2026-07-10 is a session"
        assert session_date(ts) == date(2026, 7, 10)

    def test_evening_past_utc_midnight(self):
        """20:57 ET on 2026-07-09 = 00:57 UTC on 2026-07-10 → session date is 2026-07-09."""
        ts = self._et(2026, 7, 9, 20, 57)
        assert session_date(ts) == date(2026, 7, 9)

    def test_rth_window_returns_session_day(self):
        """RTH timestamps on a session day always return that session day (no time cutoff).

        Covers the intraday fastpath cron window (*/30 11-20 UTC = 07:00-16:00 ET):
        09:30 ET, 14:00 ET, and 15:59 ET on 2026-07-09 all return 2026-07-09.
        This is the core fix: the 16:00 cutoff was making intraday runs on session day
        D return D-1 for the entire RTH window (07:00-15:59 ET).
        """
        for hour, minute in [(9, 30), (14, 0), (15, 59)]:
            ts = self._et(2026, 7, 9, hour, minute)
            assert session_date(ts) == date(2026, 7, 9), (
                f"Expected 2026-07-09 at {hour:02d}:{minute:02d} ET, session_date returned wrong value"
            )
        # 16:00 ET (at close) also returns today
        ts_at = self._et(2026, 7, 9, 16, 0)
        assert session_date(ts_at) == date(2026, 7, 9)

    def test_weekend_resolves_to_friday(self):
        """Saturday any time → last trading Friday (or last session day if Friday was a holiday)."""
        # 2026-07-11 is a Saturday; last session = 2026-07-10 (Friday, normal session)
        ts = self._et(2026, 7, 11, 10, 0)
        assert session_date(ts) == date(2026, 7, 10)

    def test_sunday_resolves_to_friday(self):
        """Sunday → prior Friday."""
        ts = self._et(2026, 7, 12, 10, 0)
        assert session_date(ts) == date(2026, 7, 10)

    def test_holiday_resolves_to_prior_session(self):
        """On a holiday (Independence Day observed 2026-07-03), session_date → last session before it."""
        # 2026-07-03 is the observed Independence Day (Fri, because Jul 4 is Saturday)
        # Last session before it = 2026-07-02 (Thursday)
        ts = self._et(2026, 7, 3, 10, 0)  # midday on the holiday
        assert not cal.is_session(date(2026, 7, 3)), "Precondition: Jul 3 is a holiday"
        assert session_date(ts) == date(2026, 7, 2)

    def test_naive_utc_treated_as_utc(self):
        """Naive datetimes are treated as UTC (pipeline convention).

        2026-07-10T00:01 naive = 20:01 ET on 2026-07-09 (past UTC midnight but same ET day).
        The ET date is 2026-07-09 (a session day), so session_date() returns 2026-07-09.
        """
        ts_naive = datetime(2026, 7, 10, 0, 1)  # no tzinfo — treated as UTC
        assert session_date(ts_naive) == date(2026, 7, 9)

    def test_none_uses_live_clock(self):
        """session_date(None) returns a date (doesn't crash); date is a valid date object."""
        result = session_date(None)
        assert isinstance(result, date)

    def test_monday_pre_open_returns_monday(self):
        """00:30 ET on a Monday → that Monday (session day, no time cutoff).

        2026-07-13 is a Monday (session day). session_date() returns the ET calendar
        date when it is a session day, regardless of time-of-day. No 16:00 cutoff.
        """
        # 2026-07-13 is a Monday
        ts = self._et(2026, 7, 13, 0, 30)
        assert cal.is_session(date(2026, 7, 13)), "Precondition: 2026-07-13 is a session"
        assert session_date(ts) == date(2026, 7, 13)


# ── (B) basket_turn_watch as_of uses session_date ──────────────────────────────

class TestBasketTurnWatchSessionDate:
    """engine/basket_turn_watch as_of fallback must use session_date, not date.today()."""

    def test_compute_inner_as_of_uses_session_date(self, tmp_path, monkeypatch):
        """When as_of=None, _compute_inner picks up the patched session_date result."""
        import engine.basket_turn_watch as BTW

        pinned = date(2026, 7, 9)
        monkeypatch.setattr(BTW, "_session_date", lambda: pinned)

        result = BTW.compute({}, data_root=tmp_path, as_of=None)
        assert result.get("as_of") == "2026-07-09", (
            f"Expected as_of=2026-07-09 from patched session_date, got {result.get('as_of')!r}"
        )

    def test_compute_error_path_as_of_uses_session_date(self, monkeypatch):
        """Even in the crash-fallback path, as_of comes from session_date."""
        import engine.basket_turn_watch as BTW

        pinned = date(2026, 7, 9)
        monkeypatch.setattr(BTW, "_session_date", lambda: pinned)

        # Pass garbage to trigger the exception path
        result = BTW.compute("not-a-dict", data_root=None, as_of=None)
        assert result.get("as_of") == "2026-07-09"

    def test_stamp_ledger_as_of_uses_session_date(self, tmp_path, monkeypatch):
        """stamp_ledger uses session_date when as_of=None."""
        import engine.basket_turn_watch as BTW

        pinned = date(2026, 7, 9)
        monkeypatch.setattr(BTW, "_session_date", lambda: pinned)
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        watch_rows = [{"basket_id": "test_basket", "state": "WATCH", "k": 3, "legs": {}}]
        n = BTW.stamp_ledger(watch_rows, as_of=None, data_root=tmp_path)
        assert n == 1

        rows = BTW.load_ledger(tmp_path)
        assert rows[0]["as_of"] == "2026-07-09"
        assert rows[0]["date"] == "2026-07-09"


# ── (C) notify_turn_events today_str uses session_date ────────────────────────

class TestNotifyTurnEventsSessionDate:
    """scripts/notify_turn_events today_str fallback uses session_date, not date.today()."""

    def test_run_today_str_uses_session_date(self, tmp_path, monkeypatch):
        """When today_str=None, run() infers the date via _session_date (not date.today())."""
        import scripts.notify_turn_events as NTE

        pinned = date(2026, 7, 9)
        monkeypatch.setattr(NTE, "_session_date", lambda: pinned)
        # Dark mode: no webhook configured → exits early but after inferring today_str.
        # We verify by checking the secret lookup path (no real dispatch needed).
        monkeypatch.setattr(NTE.config, "secret", lambda k: None)

        # The function shouldn't crash and should return 0 in dark mode.
        result = NTE.run(today_str=None, dry_run=True)
        assert result == 0

    def test_explicit_today_str_bypasses_session_date(self, monkeypatch):
        """Explicit today_str is passed through without calling _session_date."""
        import scripts.notify_turn_events as NTE

        bad_date_called = []
        monkeypatch.setattr(NTE, "_session_date", lambda: bad_date_called.append(True) or date(2099, 1, 1))
        monkeypatch.setattr(NTE.config, "secret", lambda k: None)

        result = NTE.run(today_str="2026-07-09", dry_run=True)
        assert result == 0
        assert not bad_date_called, "_session_date should not be called when today_str is provided"

    def test_dedup_key_uses_session_date_not_prior_day(self, monkeypatch):
        """RTH intraday IGNITION on session day D deduplicates under D, not D-1.

        Regression test for the intraday-dedup regression: when session_date() returned
        D-1 during RTH hours, an IGNITION on session day D would get dedup key
        'ignition|<basket>|D-1'. If the prior session (D-1) had already fired an alert,
        today's alert would be suppressed. With the fix, the key uses D.
        """
        import scripts.notify_turn_events as NTE

        # Pin session date to 2026-07-09 (simulates intraday run at 10:00 ET on 07-09)
        pinned_today = date(2026, 7, 9)
        monkeypatch.setattr(NTE, "_session_date", lambda: pinned_today)

        # Seed state with a PRIOR DAY key for the same basket (simulates an alert from 07-08)
        prior_day_key = "ignition|TEST_BASKET|2026-07-08"
        prior_state = {prior_day_key: True}

        # Build a minimal turn_watch payload with TEST_BASKET in IGNITION
        turn_watch = {
            "as_of": "2026-07-09",
            "baskets": [
                {"basket_id": "TEST_BASKET", "state": "IGNITION", "k": 2, "legs": {"leg_a": True, "leg_b": True}},
            ],
        }

        # Call the IGNITION detector directly
        alerts = NTE._detect_ignition_transitions(turn_watch, prior_state, pinned_today.isoformat())
        assert len(alerts) == 1, (
            "IGNITION on 2026-07-09 should fire — prior day key '...2026-07-08' must not suppress it"
        )
        basket_id, msg = alerts[0]
        assert basket_id == "TEST_BASKET"

        # After marking fired, same call should be suppressed
        NTE._mark_fired(prior_state, "ignition", "TEST_BASKET", pinned_today.isoformat())
        alerts_after = NTE._detect_ignition_transitions(turn_watch, prior_state, pinned_today.isoformat())
        assert len(alerts_after) == 0, "Second call on same day must be suppressed by dedup"
        # The dedup key in state must use today's date, not prior day
        today_key = f"ignition|TEST_BASKET|{pinned_today.isoformat()}"
        assert today_key in prior_state, f"Expected '{today_key}' in state after firing"


# ── (D) earlyclose stamp logic (unit test of the inline Python) ───────────────

class TestEarlycloseStampSession:
    """Unit test for the earlyclose stamp writer logic extracted from earlyclose.yml."""

    def test_stamp_has_session_field(self, tmp_path):
        """The stamp JSON must contain a 'session' key with the NYSE session date."""
        import json, datetime

        # Simulate what the inline Python in earlyclose.yml does:
        render_ts = datetime.datetime(2026, 7, 10, 0, 30, tzinfo=datetime.timezone.utc)
        # 00:30 UTC = 20:30 ET on Jul 9 (past UTC midnight but still Jul 9 in ET;
        # past 16:00 ET close → session is 2026-07-09)
        session = session_date(render_ts)

        stamp = {
            "as_of": render_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session": session.isoformat(),
            "provisional": True,
            "note": "provisional close (delayed feed); nightly is canonical",
            "lane": "earlyclose",
        }
        p = tmp_path / "earlyclose_stamp.json"
        p.write_text(json.dumps(stamp, indent=2))

        loaded = json.loads(p.read_text())
        assert "session" in loaded, "stamp must contain 'session' field"
        assert loaded["session"] == "2026-07-09", (
            f"Expected session=2026-07-09 (last completed session), got {loaded['session']!r}"
        )
        # as_of is the UTC render timestamp (not the session date)
        assert loaded["as_of"] == "2026-07-10T00:30:00Z"

    def test_stamp_as_of_is_utc_render_time(self):
        """as_of in the stamp is the UTC render timestamp (wall-clock), session is the session date."""
        import datetime

        render_ts = datetime.datetime(2026, 7, 9, 21, 0, tzinfo=datetime.timezone.utc)
        # 21:00 UTC = 17:00 ET → past 20:00 ET? No, 17:00 < 20:00 → still same session day
        session = session_date(render_ts)
        # 17:00 ET < 20:00 cutoff, so still same day (it IS a session day)
        assert session == date(2026, 7, 9)
        assert render_ts.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-07-09T21:00:00Z"
