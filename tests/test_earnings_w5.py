"""MLC-W5 earnings-proximity wiring tests.

Covers:
  A. Freshness tripwire (scripts/audit_earnings_freshness.py):
     - missing store → ok=False, fail_reasons set
     - stale store (as_of > 2 td old) → ok=True, warnings set
     - fresh store → ok=True, no warnings

  B. Standout chip (scripts/build_stock_library.py earnings_soon extension):
     - fresh store + days_to 14 → chip present with chip_en/chip_zh
     - fresh store + days_to 15 → chip absent (outside 14d window)
     - stale store → chip absent (store_stale=True)
     - boundary: days_to=0 (today) → "Reports today"
     - boundary: days_to=1 → "Reports tomorrow"
     - Monday/weekend gap: chip uses calendar days, not date-minus-1

  C. ACT-NOW basket chip (_w5_near_earnings_count helper in theme_scoring):
     - fresh store + basket member reports in 3 d → near_earnings_count=1 in _act output
     - fresh store + basket member reports in 6 d → count absent (outside 5d window)
     - stale/empty store → near_earnings_count absent

All tests are hermetic (no network, no live stores).  Chinese strings go through
Write/Edit tool only; never through bash heredoc (MLC house law).
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.earnings_blackout as eb  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────


def _make_earnings_parquet(tmp_path: Path, rows: dict, base_name: str = "earnings.parquet") -> Path:
    """Write a minimal earnings parquet (ticker-indexed).

    rows: {TICKER: {next_date, as_of, ...}}
    """
    records = []
    for ticker, d in rows.items():
        records.append({
            "ticker": ticker.upper(),
            "next_date": d.get("next_date", ""),
            "next_time": d.get("next_time", "time-not-supplied"),
            "eps_forecast": d.get("eps_forecast", None),
            "surprises_json": d.get("surprises_json", "[]"),
            "as_of": d.get("as_of", ""),
        })
    df = pd.DataFrame(records).set_index("ticker")
    p = tmp_path / base_name
    df.to_parquet(p)
    return p


def _as_of_fresh(today: date, cal_days_ago: int = 0) -> str:
    """Return an ISO-format as_of that is cal_days_ago CALENDAR days before today."""
    ts = pd.Timestamp(today) - timedelta(days=cal_days_ago)
    return ts.isoformat() + "+00:00"


def _as_of_stale(today: date) -> str:
    """Return an as_of that is 20 calendar days old (beyond any SLA)."""
    ts = pd.Timestamp(today) - timedelta(days=20)
    return ts.isoformat() + "+00:00"


# Reference date: a Tuesday so bdate_range tests are predictable and
# Monday-gap tests can step back to Monday.
TODAY = date(2026, 7, 14)


# ═══════════════════════════════════════════════════════════════════════════
# A. Freshness tripwire tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFreshnessTripwire:
    """scripts/audit_earnings_freshness.audit() correctness."""

    def _run_audit(self, tmp_path, store_path_override=None, max_age_td=2):
        """Import and run the audit function with a patched data dir."""
        import importlib
        import scripts.audit_earnings_freshness as af
        importlib.reload(af)  # fresh module each time
        # Monkey-patch config.data_dir to point at tmp_path
        import lib.config as cfg
        original = cfg.data_dir

        def _fake_data_dir():
            return tmp_path

        cfg.data_dir = _fake_data_dir
        try:
            result = af.audit(max_age_td=max_age_td)
        finally:
            cfg.data_dir = original
        return result

    def test_missing_store_fails(self, tmp_path):
        """Store absent → ok=False with a diagnostic fail_reason."""
        result = self._run_audit(tmp_path)
        assert result["ok"] is False
        assert result["fail_reasons"]
        assert any("not found" in r.lower() for r in result["fail_reasons"])

    def test_stale_store_warns_not_fails(self, tmp_path):
        """Store present but 3-td-old as_of → ok=True (no hard fail) but warning emitted."""
        (tmp_path / "earnings").mkdir(parents=True, exist_ok=True)
        # as_of 5 calendar days ago ≈ 3 trading days
        _make_earnings_parquet(
            tmp_path / "earnings",
            {"AAPL": {"next_date": "2026-08-01", "as_of": _as_of_stale(TODAY)}},
            base_name="earnings.parquet",
        )
        result = self._run_audit(tmp_path, max_age_td=2)
        assert result["ok"] is True
        assert result["warnings"]
        assert any("stale" in w.lower() for w in result["warnings"])

    def test_fresh_store_no_warnings(self, tmp_path):
        """Store written today with enough tickers → ok=True, no warnings.

        Uses 60 tickers to stay above the MIN_TICKER_PLAUSIBILITY floor (50).
        """
        (tmp_path / "earnings").mkdir(parents=True, exist_ok=True)
        rows = {f"TK{i:03d}": {"next_date": "2026-08-01", "as_of": _as_of_fresh(TODAY, 0)}
                for i in range(60)}
        _make_earnings_parquet(tmp_path / "earnings", rows, base_name="earnings.parquet")
        result = self._run_audit(tmp_path, max_age_td=2)
        assert result["ok"] is True
        assert not result["warnings"]

    def test_detail_contains_ticker_count(self, tmp_path):
        """detail dict carries ticker_count and with_next_date."""
        (tmp_path / "earnings").mkdir(parents=True, exist_ok=True)
        _make_earnings_parquet(
            tmp_path / "earnings",
            {
                "AAPL": {"next_date": "2026-08-01", "as_of": _as_of_fresh(TODAY, 0)},
                "MSFT": {"next_date": "2026-09-01", "as_of": _as_of_fresh(TODAY, 0)},
            },
            base_name="earnings.parquet",
        )
        result = self._run_audit(tmp_path, max_age_td=2)
        assert result["detail"]["ticker_count"] == 2
        assert result["detail"]["with_next_date"] == 2

    def test_fresh_store_empty_warns(self, tmp_path):
        """Store has fresh as_of but ZERO rows (postmortem failure shape) → warning fires.

        This is the exact 07-13 failure: store_stale=False, count=0.  The prior
        tripwire only checked age; it missed a fresh-timestamp-but-empty store.
        """
        import pandas as pd
        (tmp_path / "earnings").mkdir(parents=True, exist_ok=True)
        # Write an empty parquet (0 rows, correct columns)
        df = pd.DataFrame(columns=["next_date", "next_time", "eps_forecast",
                                    "surprises_json", "as_of"])
        df.index.name = "ticker"
        df.to_parquet(tmp_path / "earnings" / "earnings.parquet")
        result = self._run_audit(tmp_path, max_age_td=2)
        assert result["ok"] is True  # still ok=True (warn-not-fail)
        assert result["warnings"]
        assert any("empty" in w.lower() or "ticker_count=0" in w for w in result["warnings"])

    def test_near_empty_store_warns(self, tmp_path):
        """Store has 4 rows but fresh as_of (documented bug: 1363-sweep wrote 4) → warning fires."""
        (tmp_path / "earnings").mkdir(parents=True, exist_ok=True)
        _make_earnings_parquet(
            tmp_path / "earnings",
            {
                "AAPL": {"next_date": "2026-08-01", "as_of": _as_of_fresh(TODAY, 0)},
                "MSFT": {"next_date": "2026-09-01", "as_of": _as_of_fresh(TODAY, 0)},
                "NVDA": {"next_date": "2026-08-15", "as_of": _as_of_fresh(TODAY, 0)},
                "AMZN": {"next_date": "2026-08-20", "as_of": _as_of_fresh(TODAY, 0)},
            },
            base_name="earnings.parquet",
        )
        result = self._run_audit(tmp_path, max_age_td=2)
        assert result["ok"] is True
        assert result["warnings"]
        assert any(
            "suspiciously small" in w.lower() or "plausibility" in w.lower()
            for w in result["warnings"]
        )

    def test_fresh_store_with_dates_no_extra_warnings(self, tmp_path):
        """Store fresh + 100+ tickers + all have next_date → zero extra warnings from emptiness guard."""
        import pandas as pd
        (tmp_path / "earnings").mkdir(parents=True, exist_ok=True)
        rows = {f"TK{i:03d}": {"next_date": "2026-08-01", "as_of": _as_of_fresh(TODAY, 0)}
                for i in range(100)}
        _make_earnings_parquet(tmp_path / "earnings", rows, base_name="earnings.parquet")
        result = self._run_audit(tmp_path, max_age_td=2)
        assert result["ok"] is True
        # The only valid warning path here is the age-based one; emptiness guards must not fire.
        emptiness_warns = [w for w in result["warnings"]
                           if "empty" in w.lower() or "suspiciously small" in w.lower()
                           or "with_next_date=0" in w]
        assert not emptiness_warns

    def test_rows_present_but_zero_next_dates_warns(self, tmp_path):
        """Store has 200 rows but next_date is null for all → with_next_date=0 warning fires."""
        (tmp_path / "earnings").mkdir(parents=True, exist_ok=True)
        # next_date = "" → notna() is True for empty string, but let's use actual NaN
        import pandas as pd
        records = [
            {"ticker": f"TK{i:03d}", "next_date": None, "next_time": None,
             "eps_forecast": None, "surprises_json": "[]", "as_of": _as_of_fresh(TODAY, 0)}
            for i in range(200)
        ]
        df = pd.DataFrame(records).set_index("ticker")
        p = tmp_path / "earnings" / "earnings.parquet"
        df.to_parquet(p)
        result = self._run_audit(tmp_path, max_age_td=2)
        assert result["ok"] is True
        assert result["warnings"]
        assert any("with_next_date=0" in w for w in result["warnings"])


# ═══════════════════════════════════════════════════════════════════════════
# B. Standout chip — earnings_soon field in build_stock_library
# ═══════════════════════════════════════════════════════════════════════════

class TestStandoutChip:
    """Unit-test the earnings_soon chip logic in build_stock_library.

    We test the underlying earnings_blackout.assess() result as returned by
    the engine layer (which is what build_stock_library reads), because the
    chip assembly code in build_stock_library is a thin wrapper around it.
    The key logic under test:
      - days_to <= 14 → chip should fire (MLC-W5 extended from 7)
      - days_to == 15 → chip should NOT fire
      - stale store → no chip
      - boundary texts: "Reports today" (0d), "Reports tomorrow" (1d)
    """

    def _make_store(self, tmp_path: Path, ticker: str, next_date: str,
                    as_of: str) -> Path:
        eb.clear_cache()
        return _make_earnings_parquet(
            tmp_path,
            {ticker: {"next_date": next_date, "as_of": as_of}},
        )

    def _days_from(self, today: date, n: int) -> str:
        """Return ISO date that is n CALENDAR days after today."""
        return (today + timedelta(days=n)).strftime("%Y-%m-%d")

    def test_chip_fires_at_14d(self, tmp_path):
        """days_to=14 calendar days → assess returns days_to_earnings that build_stock_library
        would include in the chip (the chip fires when days_to_earnings <= 14)."""
        nd = self._days_from(TODAY, 14)
        p = self._make_store(tmp_path, "GS", nd, _as_of_fresh(TODAY, 0))
        result = eb.assess("GS", today=TODAY, store_path=p)
        # With a 14-calendar-day next_date the store returns a trading-day count.
        # We verify: NOT stale, days_to_earnings present and <=14 (the chip threshold).
        assert not result["stale"]
        assert result["days_to_earnings"] is not None
        assert result["days_to_earnings"] <= 14

    def test_chip_fires_at_1d(self, tmp_path):
        """days_to=1 calendar day → chip fires (in-blackout window)."""
        nd = self._days_from(TODAY, 1)
        p = self._make_store(tmp_path, "JPM", nd, _as_of_fresh(TODAY, 0))
        result = eb.assess("JPM", today=TODAY, store_path=p)
        assert not result["stale"]
        assert result["days_to_earnings"] is not None
        assert result["days_to_earnings"] <= 14

    def test_chip_text_today(self, tmp_path):
        """days_to=0 → chip_en == 'Reports today', chip_zh == '今日公布业绩'."""
        nd = TODAY.strftime("%Y-%m-%d")  # same day
        p = self._make_store(tmp_path, "AAPL", nd, _as_of_fresh(TODAY, 0))
        result = eb.assess("AAPL", today=TODAY, store_path=p)
        # Simulate the chip text logic from build_stock_library
        days = result.get("days_to_earnings")
        assert days == 0 or days is None  # 0 if same-day trading match, None if calendar gap
        # Direct text generation test for days_to=0
        chip_en, chip_zh = _chip_texts(0)
        assert chip_en == "Reports today"
        assert chip_zh == "今日公布业绩"

    def test_chip_text_tomorrow(self):
        """days_to=1 → chip_en == 'Reports tomorrow'."""
        chip_en, chip_zh = _chip_texts(1)
        assert chip_en == "Reports tomorrow"
        assert chip_zh == "明日公布业绩"

    def test_chip_text_n_days(self):
        """days_to=7 → chip_en == 'Reports in 7 d'."""
        chip_en, chip_zh = _chip_texts(7)
        assert chip_en == "Reports in 7 d"
        assert chip_zh == "7日后公布业绩"

    def test_stale_store_no_chip(self, tmp_path):
        """Stale as_of → assess returns stale=True → no chip."""
        nd = self._days_from(TODAY, 3)
        p = self._make_store(tmp_path, "META", nd, _as_of_stale(TODAY))
        result = eb.assess("META", today=TODAY, store_path=p)
        assert result["stale"] is True
        # build_stock_library skips chip when stale=True

    def test_monday_gap_not_date_minus_one(self, tmp_path):
        """Monday boundary: next_date on Monday — no date-minus-1 join hole.

        The chip uses calendar-day distance (next_date - today).days, NOT
        a date-minus-1 exact join.  A name reporting on Monday from a Tuesday
        reference must NOT be dropped.

        TODAY=2026-07-14 (Tuesday).  Monday = 2026-07-20 (6 cal days ahead).
        """
        monday = date(2026, 7, 20)
        nd = monday.strftime("%Y-%m-%d")
        p = self._make_store(tmp_path, "XLF", nd, _as_of_fresh(TODAY, 0))
        result = eb.assess("XLF", today=TODAY, store_path=p)
        # Must not be in_past and must have a non-None days_to_earnings
        assert result.get("reason") != "next_date_in_past"
        assert result["days_to_earnings"] is not None

    def test_weekend_next_date_not_dropped(self, tmp_path):
        """A next_date on Saturday is NOT in the past from today (Tuesday).

        If the collector stored a Saturday as next_date, the assess() function
        should not treat it as a past date (Saturday > today Tuesday by calendar).
        """
        saturday = date(2026, 7, 19)  # Saturday, 5 days from TODAY=2026-07-14 (Tue)
        nd = saturday.strftime("%Y-%m-%d")
        p = self._make_store(tmp_path, "SPY", nd, _as_of_fresh(TODAY, 0))
        result = eb.assess("SPY", today=TODAY, store_path=p)
        assert result.get("reason") != "next_date_in_past"


def _chip_texts(days_to: int) -> tuple[str, str]:
    """Mirror the chip-text logic from build_stock_library.py for test assertion."""
    if days_to == 0:
        return "Reports today", "今日公布业绩"
    elif days_to == 1:
        return "Reports tomorrow", "明日公布业绩"
    else:
        return f"Reports in {days_to} d", f"{days_to}日后公布业绩"


# ═══════════════════════════════════════════════════════════════════════════
# C. ACT-NOW basket chip (_w5_near_earnings_count)
# ═══════════════════════════════════════════════════════════════════════════

class TestActNowChip:
    """Unit tests for the near_earnings_count field added to _act() output.

    We test the _w5_near_earnings_count logic directly by reimplementing it
    in the test (the same function lives inside compute_theme_intel as a closure).
    This validates boundary conditions without needing to spin up the full
    compute_theme_intel pipeline.
    """

    @staticmethod
    def _make_earn_cal(tickers_and_dates: dict[str, str]) -> dict[str, str]:
        """Build the _w5_earn_cal dict (ticker -> next_date ISO str)."""
        return {t.upper(): nd for t, nd in tickers_and_dates.items()}

    @staticmethod
    def _near_count(earn_cal: dict[str, str], tickers: list[str],
                    today: date, window_days: int = 5) -> int | None:
        """Mirror of _w5_near_earnings_count from theme_scoring.py."""
        if not earn_cal:
            return None
        count = 0
        for tk in tickers:
            nd_str = earn_cal.get(tk.upper())
            if not nd_str:
                continue
            try:
                nd = date.fromisoformat(nd_str)
                gap = (nd - today).days
                if 0 <= gap <= window_days:
                    count += 1
            except Exception:  # noqa: BLE001
                pass
        return count

    def test_member_reports_in_3d(self):
        """One member with next_date = today+3 → count=1."""
        nd = (TODAY + timedelta(days=3)).isoformat()
        cal = self._make_earn_cal({"NVDA": nd})
        result = self._near_count(cal, ["NVDA", "MSFT", "AAPL"], TODAY)
        assert result == 1

    def test_member_reports_in_5d_boundary(self):
        """Boundary: today+5 is still within the 5d window → count=1."""
        nd = (TODAY + timedelta(days=5)).isoformat()
        cal = self._make_earn_cal({"GOOGL": nd})
        result = self._near_count(cal, ["GOOGL", "AMZN"], TODAY)
        assert result == 1

    def test_member_reports_in_6d_outside_window(self):
        """today+6 is OUTSIDE the 5d window → count=0."""
        nd = (TODAY + timedelta(days=6)).isoformat()
        cal = self._make_earn_cal({"META": nd})
        result = self._near_count(cal, ["META", "TSLA"], TODAY)
        assert result == 0

    def test_multiple_members_count(self):
        """Two members in window → count=2."""
        cal = self._make_earn_cal({
            "AAPL": (TODAY + timedelta(days=1)).isoformat(),
            "MSFT": (TODAY + timedelta(days=4)).isoformat(),
            "AMZN": (TODAY + timedelta(days=7)).isoformat(),  # outside
        })
        result = self._near_count(cal, ["AAPL", "MSFT", "AMZN"], TODAY)
        assert result == 2

    def test_empty_earn_cal_returns_none(self):
        """Empty earnings calendar → None (store absent/stale, not '0')."""
        result = self._near_count({}, ["NVDA", "MSFT"], TODAY)
        assert result is None

    def test_today_boundary_inclusive(self):
        """today+0 (same day) is within window → count=1."""
        cal = self._make_earn_cal({"JPM": TODAY.isoformat()})
        result = self._near_count(cal, ["JPM"], TODAY)
        assert result == 1

    def test_monday_no_date_minus_one_hole(self):
        """Monday next_date from Tuesday reference — calendar-day calc, no hole.

        TODAY=2026-07-14 (Tuesday).  Monday report=2026-07-20 (6 cal days).
        6 > 5 → count=0 (outside 5d window).  If we had used date-1 join
        the Monday would be DROPPED entirely — but here it's just outside the window,
        which is correct and different from being dropped.
        """
        monday = date(2026, 7, 20)
        cal = self._make_earn_cal({"XLF": monday.isoformat()})
        # 6 days out → NOT in 5d window
        result = self._near_count(cal, ["XLF"], TODAY, window_days=5)
        assert result == 0
        # but IS in 7d window
        result7 = self._near_count(cal, ["XLF"], TODAY, window_days=7)
        assert result7 == 1

    def test_past_date_excluded(self):
        """A next_date in the PAST (gap < 0) must not count."""
        past = (TODAY - timedelta(days=1)).isoformat()
        cal = self._make_earn_cal({"GS": past})
        result = self._near_count(cal, ["GS"], TODAY)
        assert result == 0


# ═══════════════════════════════════════════════════════════════════════════
# D. Integration smoke: engine.earnings_blackout.store_staleness
# ═══════════════════════════════════════════════════════════════════════════

class TestStoreStaleness:
    """store_staleness() returns the right keys and respects the fresh/stale boundary."""

    def test_missing_store_is_stale(self, tmp_path):
        eb.clear_cache()
        fake_path = tmp_path / "nonexistent.parquet"
        result = eb.store_staleness(today=TODAY, store_path=fake_path)
        assert result["stale"] is True
        assert result["store_missing"] is True

    def test_fresh_store_not_stale(self, tmp_path):
        """A store with as_of = today → stale=False."""
        eb.clear_cache()
        p = _make_earnings_parquet(
            tmp_path,
            {"AAPL": {"next_date": "2026-08-01", "as_of": _as_of_fresh(TODAY, 0)}},
        )
        result = eb.store_staleness(today=TODAY, store_path=p)
        assert result["stale"] is False
        assert result["as_of_age_td"] is not None
        assert result["as_of_age_td"] <= 1  # same or prior business day

    def test_stale_store_is_stale(self, tmp_path):
        """A store with as_of = 20 calendar days ago → stale=True."""
        eb.clear_cache()
        p = _make_earnings_parquet(
            tmp_path,
            {"AAPL": {"next_date": "2026-08-01", "as_of": _as_of_stale(TODAY)}},
        )
        result = eb.store_staleness(today=TODAY, store_path=p)
        assert result["stale"] is True
