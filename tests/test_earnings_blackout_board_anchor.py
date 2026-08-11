"""Regression: the W1.5 earnings gate is anchored to the BOARD SESSION, not the host clock.

THE BUG (proven, measured 2026-08-10).  scripts/build_stock_library.py called
``earnings_blackout.assess()`` / ``store_staleness()`` with no ``today=``, so the
engine defaulted to ``date.today()`` — the RENDER HOST's local date.  Across 16 board
commits stamped at one identical as_of=2026-08-07, every UTC-7 host produced 78 buy
rows while every UTC+8 host past local midnight produced 81: three names carrying a
2026-08-10 earnings date were admitted through the ``next_date_in_past`` fail-open,
a one-sided lookahead into a POST-as_of event.  Board membership was a function of
which machine rendered it.

THE FIX under test.  ``_apply_earnings_blackout_gate`` threads a ``board_session``
date (derived by ``_eb_board_session_date`` from alpha.json's as_of, falling back to
the last close session) into every engine call, so membership is a pure function of
the board's own inputs.

Every test here freezes the host clock via a ``date`` subclass monkeypatched into
engine.earnings_blackout, and pins the board session explicitly — nothing reads the
real wall clock, so the suite passes at any hour in any timezone (CI runs UTC).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.earnings_blackout as eb  # noqa: E402
from scripts.build_stock_library import (  # noqa: E402
    _apply_earnings_blackout_gate,
    _eb_board_session_date,
)

# ── the board's own session (a Friday) + the three fixture names ────────────
BOARD_SESSION = date(2026, 8, 7)
HOST_ON_SESSION = date(2026, 8, 7)     # render host agrees with the board
HOST_PAST_EARNINGS = date(2026, 8, 11) # host rolled past AAA's 2026-08-10 print

# AAA: 1 trading day after the board session  -> inside the k=3 window
# BBB: 35 trading days out                    -> comfortably outside it
# CCC: 2 sessions BEFORE the board session    -> next_date_in_past even when anchored
_ROWS = {
    "AAA": "2026-08-10",
    "BBB": "2026-09-25",
    "CCC": "2026-08-05",
}
_AS_OF = "2026-08-07T00:30:00+00:00"  # age 0 td at the board session => store fresh


# ── helpers ────────────────────────────────────────────────────────────────

def _make_store(tmp_path: Path) -> Path:
    """Write the synthetic earnings parquet in the collector's real schema."""
    records = [
        {"ticker": tk, "next_date": nd, "next_time": "time-after-hours",
         "eps_forecast": None, "surprises_json": "[]", "as_of": _AS_OF}
        for tk, nd in _ROWS.items()
    ]
    df = pd.DataFrame(records).set_index("ticker")
    p = tmp_path / "earnings.parquet"
    df.to_parquet(p)
    return p


def _fake_date_cls(host_date: date):
    """A ``date`` subclass whose ``today()`` is frozen at host_date.

    engine.earnings_blackout does ``from datetime import date``, so monkeypatching
    the module attribute intercepts every ``date.today()`` the engine performs.
    """
    class _FakeDate(date):
        @classmethod
        def today(cls) -> date:
            return host_date

    return _FakeDate


def _freeze_host(monkeypatch, host_date: date) -> None:
    monkeypatch.setattr(eb, "date", _fake_date_cls(host_date))


def _inputs():
    """Fresh gate inputs — rebuilt per call because the gate mutates row_by_t."""
    buyable = [(tk, {"composite_z": 1.0}, "aligned") for tk in sorted(_ROWS)]
    row_by_t = {tk: {"ticker": tk} for tk in _ROWS}
    return buyable, [], row_by_t


@pytest.fixture(autouse=True)
def _clean_calendar():
    """Inject a holiday-free calendar around the fixture dates; restore after.

    clear_cache() drops the injected calendar AND the store cache, so it runs on both
    edges — a leaked calendar would silently retune every other test's td distances.
    """
    eb.clear_cache()
    eb.set_td_calendar(pd.bdate_range("2026-07-01", "2026-09-30"))
    yield
    eb.clear_cache()


# ── 1. Membership is identical on both sides of the host-clock rollover ─────

class TestMembershipIsHostClockIndependent:
    def test_same_board_on_both_host_dates(self, tmp_path, monkeypatch):
        """The whole point: two hosts straddling AAA's print produce ONE board."""
        p = _make_store(tmp_path)

        _freeze_host(monkeypatch, HOST_ON_SESSION)
        buyable_a, rec_a, rows_a = _inputs()
        out_a = _apply_earnings_blackout_gate(
            buyable_a, rec_a, rows_a, BOARD_SESSION, store_path=p)

        _freeze_host(monkeypatch, HOST_PAST_EARNINGS)
        buyable_b, rec_b, rows_b = _inputs()
        out_b = _apply_earnings_blackout_gate(
            buyable_b, rec_b, rows_b, BOARD_SESSION, store_path=p)

        members_a = [t for t, _, _ in out_a["buyable"]]
        members_b = [t for t, _, _ in out_b["buyable"]]
        assert members_a == members_b, (
            f"board membership moved with the host clock: {members_a} vs {members_b}")
        assert ({t for t, _, _ in out_a["suppressed"]}
                == {t for t, _, _ in out_b["suppressed"]})
        assert out_a["store_stale"] is False and out_b["store_stale"] is False

    def test_upcoming_print_suppressed_on_both_host_dates(self, tmp_path, monkeypatch):
        """AAA prints 1 td after the board session — suppressed regardless of host."""
        p = _make_store(tmp_path)

        for host in (HOST_ON_SESSION, HOST_PAST_EARNINGS):
            _freeze_host(monkeypatch, host)
            buyable, rec, rows = _inputs()
            out = _apply_earnings_blackout_gate(
                buyable, rec, rows, BOARD_SESSION, store_path=p)

            assert "AAA" not in [t for t, _, _ in out["buyable"]], (
                f"host {host}: AAA admitted despite a post-as_of print (lookahead)")
            assert "AAA" in [t for t, _, _ in out["suppressed"]]
            assert out["blackout_map"]["AAA"]["in_blackout"] is True
            assert rows["AAA"]["primary_rejection_reason"] == "event_blackout"

    def test_outside_window_and_past_date_admitted_on_both(self, tmp_path, monkeypatch):
        """BBB (35 td out) and CCC (already reported) stay on the board either way."""
        p = _make_store(tmp_path)

        for host in (HOST_ON_SESSION, HOST_PAST_EARNINGS):
            _freeze_host(monkeypatch, host)
            buyable, rec, rows = _inputs()
            out = _apply_earnings_blackout_gate(
                buyable, rec, rows, BOARD_SESSION, store_path=p)

            members = [t for t, _, _ in out["buyable"]]
            assert members == ["BBB", "CCC"], f"host {host}: unexpected board {members}"
            assert out["blackout_map"]["BBB"]["reason"] == "outside_window"
            # CCC's print predates the board session — fail-open even when anchored.
            assert out["blackout_map"]["CCC"]["reason"] == "next_date_in_past"
            assert "primary_rejection_reason" not in rows["BBB"]
            assert "primary_rejection_reason" not in rows["CCC"]


# ── 2. Counterfactual: the mock bites, and the anchor is what closes the bug ─

class TestUnanchoredCallStillDrifts:
    """Without ``today=`` the engine reads the host clock — the shipped defect.

    This is the control for the class above: it proves the frozen-clock mock is
    actually intercepting date.today(), and that the ONLY thing standing between
    the board and a lookahead admission is the board_session argument.
    """

    def test_bare_assess_admits_after_host_rolls_past(self, tmp_path, monkeypatch):
        p = _make_store(tmp_path)
        _freeze_host(monkeypatch, HOST_PAST_EARNINGS)

        ev = eb.assess("AAA", store_path=p)  # no today= — the pre-fix call shape
        assert ev["in_blackout"] is False
        assert ev["reason"] == "next_date_in_past", (
            "host-clock drift no longer reproduces — this control test is vacuous")

    def test_bare_assess_suppresses_before_host_rolls_past(self, tmp_path, monkeypatch):
        """Same call, earlier host date, opposite verdict: the drift is one-sided."""
        p = _make_store(tmp_path)
        _freeze_host(monkeypatch, HOST_ON_SESSION)

        ev = eb.assess("AAA", store_path=p)  # no today=
        assert ev["in_blackout"] is True
        assert ev["days_to_earnings"] == 1

    def test_anchored_assess_ignores_the_host(self, tmp_path, monkeypatch):
        """With today= pinned, the same two hosts return the same verdict."""
        p = _make_store(tmp_path)
        verdicts = []
        for host in (HOST_ON_SESSION, HOST_PAST_EARNINGS):
            _freeze_host(monkeypatch, host)
            verdicts.append(eb.assess("AAA", today=BOARD_SESSION, store_path=p))
        assert verdicts[0] == verdicts[1]
        assert verdicts[0]["in_blackout"] is True


# ── 3. HOLD-skip survives the extraction ────────────────────────────────────

class TestHoldSkipPreserved:
    """An open position is never re-suppressed by the hygiene gate (RUL-4-legal)."""

    @pytest.mark.parametrize("host", [HOST_ON_SESSION, HOST_PAST_EARNINGS])
    def test_launched_hold_keeps_aaa_on_the_board(self, tmp_path, monkeypatch, host):
        p = _make_store(tmp_path)
        _freeze_host(monkeypatch, host)

        buyable, rec, rows = _inputs()
        rows["AAA"]["hold"] = {"state": "launched"}
        out = _apply_earnings_blackout_gate(
            buyable, rec, rows, BOARD_SESSION, store_path=p)

        assert "AAA" in [t for t, _, _ in out["buyable"]], (
            f"host {host}: HOLD-launched name suppressed by the earnings gate")
        assert out["suppressed"] == []
        assert "primary_rejection_reason" not in rows["AAA"]
        # Never assessed at all — the skip fires before assess().
        assert "AAA" not in out["blackout_map"]


# ── 4. Stale store fails open (suppresses NOTHING), anchored the same way ───

class TestStaleStoreFailsOpen:
    def test_stale_store_suppresses_nothing(self, tmp_path, monkeypatch):
        """A board session 30 td after the store's as_of => every name retained."""
        p = _make_store(tmp_path)
        _freeze_host(monkeypatch, HOST_ON_SESSION)

        buyable, rec, rows = _inputs()
        out = _apply_earnings_blackout_gate(
            buyable, rec, rows, date(2026, 9, 21), store_path=p)

        assert out["store_stale"] is True
        assert [t for t, _, _ in out["buyable"]] == sorted(_ROWS)
        assert out["suppressed"] == [] and out["suppressed_r"] == []
        assert out["blackout_map"] == {}


# ── 5. The session-date derivation itself reads no clock ────────────────────

class TestBoardSessionDate:
    _CAL = pd.bdate_range("2026-07-01", "2026-08-07")

    def test_alpha_asof_wins(self):
        assert _eb_board_session_date("2026-08-07", self._CAL) == date(2026, 8, 7)

    def test_alpha_asof_with_time_component(self):
        assert (_eb_board_session_date("2026-08-07T21:05:00+00:00", None)
                == date(2026, 8, 7))

    def test_falls_back_to_last_close_session(self):
        assert _eb_board_session_date(None, self._CAL) == date(2026, 8, 7)

    def test_none_when_no_anchor_available(self):
        assert _eb_board_session_date(None, None) is None
        assert _eb_board_session_date(None, pd.DatetimeIndex([])) is None

    def test_unparseable_asof_falls_through_to_the_calendar(self):
        """A corrupt stamp degrades to the close calendar, NOT to the host clock.

        The anchors are tried in order, not as an either/or: a bad as_of must still
        yield a deterministic session, because the host-clock fallback is the very
        drift this module is fixing.
        """
        assert _eb_board_session_date("not-a-date", self._CAL) == date(2026, 8, 7)

    def test_unparseable_asof_and_no_calendar_returns_none(self):
        """Only when BOTH anchors are unusable does the caller fall back to the clock."""
        assert _eb_board_session_date("not-a-date", None) is None
        assert _eb_board_session_date("not-a-date", pd.DatetimeIndex([])) is None
