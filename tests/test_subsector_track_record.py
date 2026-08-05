"""Unit tests for engine.subsector_track_record — the forward outcome ledger."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from engine import subsector_track_record as S


def _payload(subs, emerging, fading):
    return {"subsectors": subs, "highlights": {"emerging": emerging, "fading": fading}}


def test_snapshot_idempotent(tmp_path):
    pay = _payload([{"key": "a", "name": "A", "theme": "T", "emerging_score": 2.0,
                     "rs_mom": 1.0, "accel": 3.0, "quadrant": "improving"}],
                   ["a"], [])
    mm = {"a": ["NVDA", "AAPL", "MSFT"]}
    assert S.snapshot(pay, mm, today="2026-06-28", root=tmp_path) == 1
    assert S.snapshot(pay, mm, today="2026-06-28", root=tmp_path) == 0   # same day → no dupes
    rows = [json.loads(x) for x in (tmp_path / "data/subsector_rotation/snapshots.jsonl").read_text().splitlines()]
    assert rows[0]["stage"] == "emerging" and rows[0]["lean"] == 1 and rows[0]["members"] == ["NVDA", "AAPL", "MSFT"]


def test_accruing_when_empty(tmp_path):
    tr = S.compute(today="2026-06-28", root=tmp_path)
    assert tr["verdict"] == "accruing" and tr["any_matured"] is False and tr["n_snapshots"] == 0
    assert tr["is_context_only"] is True


def _fake_prices(monkeypatch):
    # entry = 100 for everyone; exit encodes the move via a per-ticker table.
    exit_px = {"W": 110.0, "L": 90.0, "SPY": 100.0}   # W up 10%, L down 10%, SPY flat
    monkeypatch.setattr(S, "_covers", lambda t, root, end: True)
    monkeypatch.setattr(S, "_level_asof", lambda t, root, start: 100.0)
    monkeypatch.setattr(S, "_close_at", lambda t, root, end: exit_px.get(t[0] if t != "SPY" else "SPY", 100.0))


def _write_rows(tmp_path, rows):
    p = tmp_path / "data/subsector_rotation/snapshots.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_maturation_grades_calls(tmp_path, monkeypatch):
    _fake_prices(monkeypatch)
    d0 = (date(2026, 6, 28) - timedelta(days=30)).isoformat()
    rows = [
        # emerging with WINNER members → fwd>0 → HIT
        {"date": d0, "key": "e_hit", "name": "Ehit", "theme": "T", "score": 2.5, "lean": 1,
         "stage": "emerging", "members": ["W1", "W2", "W3"]},
        # emerging with LOSER members → fwd<0 → MISS (false judgement → error ledger)
        {"date": d0, "key": "e_miss", "name": "Emiss", "theme": "T", "score": 2.0, "lean": 1,
         "stage": "emerging", "members": ["L1", "L2", "L3"]},
        # fading with LOSER members → fwd<0 → HIT (correctly called the roll-over)
        {"date": d0, "key": "f_hit", "name": "Fhit", "theme": "T", "score": -1.0, "lean": -1,
         "stage": "fading", "members": ["L4", "L5", "L6"]},
        # too few priceable members → unscored (members table prices all, but only 2 → < _MIN_PRICED)
        {"date": d0, "key": "thin", "name": "Thin", "theme": "T", "score": 0.1, "lean": 0,
         "stage": "neutral", "members": ["W9", "W8"]},
    ]
    _write_rows(tmp_path, rows)
    tr = S.compute(today="2026-06-28", root=tmp_path)
    h21 = tr["horizons"]["21"]
    assert h21["n_matured"] == 3                                  # the 2-member 'thin' is dropped
    bs = h21["by_stage"]
    assert bs["emerging"]["n"] == 2 and bs["emerging"]["hit_rate"] == 0.5   # 1 hit / 1 miss
    assert bs["fading"]["n"] == 1 and bs["fading"]["hit_rate"] == 1.0
    # the falsified emerging call is logged in the error ledger
    misses = {m["key"] for m in tr["recent_misses"]}
    assert "e_miss" in misses and "e_hit" not in misses
    # still no significance on a tiny sample → not 'validated'
    assert tr["verdict"] in ("measuring", "accruing")


def test_horizon_gating(tmp_path, monkeypatch):
    _fake_prices(monkeypatch)
    # a call only 7 days old: matures at 5d, not at 21d.
    d0 = (date(2026, 6, 28) - timedelta(days=7)).isoformat()
    _write_rows(tmp_path, [{"date": d0, "key": "e", "name": "E", "theme": "T", "score": 1.0,
                            "lean": 1, "stage": "emerging", "members": ["W1", "W2", "W3"]}])
    tr = S.compute(today="2026-06-28", root=tmp_path)
    assert tr["horizons"]["5"]["n_matured"] == 1
    assert tr["horizons"]["21"]["n_matured"] == 0


# --------------------------------------------------------------------------- #
# SESSION STAMPING (calendar-asof audit 2026-08-05)
#
# The nightly runs ~22:30 UTC seven nights a week against an END-OF-DAY board, so the
# Saturday and Sunday passes re-read Friday's unchanged numbers. Stamped from the clock
# they slipped past the (date,key) idempotency below and appended a full fresh row set
# per weekend night, which compute() then graded as extra independent IC days.
#
# Pinned weekday dates only — a fixture that reads the wall clock is a scheduled failure.
# 2026-07-10 Fri (session) · 2026-07-11 Sat · 2026-07-12 Sun.
# --------------------------------------------------------------------------- #
_FRI, _SAT, _SUN = "2026-07-10", "2026-07-11", "2026-07-12"


def _one_sub(key="a"):
    return _payload([{"key": key, "name": "A", "theme": "T", "emerging_score": 2.0,
                      "rs_mom": 1.0, "accel": 3.0, "quadrant": "improving"}], [key], [])


def test_weekend_snapshot_dedupes_against_the_friday_it_redescribes(tmp_path):
    """A Saturday re-read of Friday's board must be a NO-OP, not a second row set."""
    pay, mm = _one_sub(), {"a": ["NVDA", "AAPL", "MSFT"]}
    assert S.snapshot(pay, mm, today=_FRI, root=tmp_path) == 1
    p = tmp_path / "data/subsector_rotation/snapshots.jsonl"
    before = p.read_bytes()

    assert S.snapshot(pay, mm, today=_SAT, root=tmp_path) == 0, "Saturday re-fetch"
    assert S.snapshot(pay, mm, today=_SUN, root=tmp_path) == 0, "Sunday re-fetch"

    assert p.read_bytes() == before, "the weekend passes must not touch the ledger"
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    assert [r["date"] for r in rows] == [_FRI]


def test_weekend_snapshot_still_logs_when_the_session_is_absent(tmp_path):
    """Normalization, not refusal: Friday's fetch failed and Saturday recovered it.

    The rows must still log — dated to the session they actually describe, so the
    board is not lost — which is why the fix normalizes rather than dropping weekend
    calls outright.
    """
    pay, mm = _one_sub(), {"a": ["NVDA", "AAPL", "MSFT"]}
    assert S.snapshot(pay, mm, today=_SAT, root=tmp_path) == 1

    rows = [json.loads(x) for x in
            (tmp_path / "data/subsector_rotation/snapshots.jsonl").read_text().splitlines()]
    assert [r["date"] for r in rows] == [_FRI]
    assert rows[0]["stage"] == "emerging" and rows[0]["members"] == ["NVDA", "AAPL", "MSFT"]


def test_compute_as_of_is_the_session_not_the_calendar_day(tmp_path):
    """A Sunday run reports Friday: there is no session between them to age into."""
    tr = S.compute(today=_SUN, root=tmp_path)
    assert tr["as_of"] == _FRI


def test_compute_maturity_clock_does_not_age_over_a_weekend(tmp_path, monkeypatch):
    """A call 5 sessions old on Friday is not 7 days old because someone ran on Sunday."""
    _fake_prices(monkeypatch)
    # 2026-07-03 is the observed Independence Day holiday; 2026-07-02 (Thu) is the
    # last session before it, exactly 8 calendar days before _SUN and 8 before _FRI.
    _write_rows(tmp_path, [{"date": "2026-07-05", "key": "e", "name": "E", "theme": "T",
                            "score": 1.0, "lean": 1, "stage": "emerging",
                            "members": ["W1", "W2", "W3"]}])
    # the row itself is weekend-dated legacy data; grading it is not this test's point —
    # what matters is that today= normalizes identically from Friday and from Sunday.
    fri = S.compute(today=_FRI, root=tmp_path)
    sun = S.compute(today=_SUN, root=tmp_path)
    assert fri["as_of"] == sun["as_of"] == _FRI
    assert {h: e["n_matured"] for h, e in fri["horizons"].items()} == \
           {h: e["n_matured"] for h, e in sun["horizons"].items()}


def test_unparseable_stamp_passes_through_and_never_raises(tmp_path):
    """degrade-never-raise: a stamp we cannot read is not given an invented session."""
    pay, mm = _one_sub(), {"a": ["NVDA", "AAPL", "MSFT"]}
    assert S.snapshot(pay, mm, today="not-a-date", root=tmp_path) == 1
    rows = [json.loads(x) for x in
            (tmp_path / "data/subsector_rotation/snapshots.jsonl").read_text().splitlines()]
    assert rows[0]["date"] == "not-a-date"

    tr = S.compute(today="not-a-date", root=tmp_path)
    assert tr["verdict"] == "accruing" and tr["compute_error"]


def test_session_stamp_maps_holidays_and_weekends(tmp_path):
    """The helper itself — pinned dates, including a holiday-extended closure."""
    assert S._session_stamp(_FRI) == _FRI                     # session: unchanged
    assert S._session_stamp(_SAT) == _FRI
    assert S._session_stamp(_SUN) == _FRI
    assert S._session_stamp(date(2026, 7, 11)) == _FRI        # date object, not a str
    # 2026-07-04 falls on a Saturday, so Independence Day is observed Fri 2026-07-03;
    # the last session of that week is Thursday 2026-07-02.
    assert S._session_stamp("2026-07-03") == "2026-07-02"
    assert S._session_stamp("2026-07-05") == "2026-07-02"
    # Labor Day 2026 = Mon 2026-09-07 → the prior Friday.
    assert S._session_stamp("2026-09-07") == "2026-09-04"
