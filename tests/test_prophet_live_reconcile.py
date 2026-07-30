"""tests/test_prophet_live_reconcile.py — the nightly forward ledger (P0 D4).

This ledger is the entire evidence base for the §5/§6 promotion gauntlet and for the
operator's "acting at the intraday cross beats the graded next-close fill" question,
so the three ways it could quietly lie are all pinned here:

  * the FILL CONVENTION must be ``engine.grading``'s, not a lookalike. A ledger whose
    fill is the same-day close would flatter every row by one session of drift and
    would be un-comparable with the track record.
  * MERGING must be union + field-wise newest-non-null. A maturing fill written on a
    later night must not erase what the event night already knew, and running twice
    must change nothing (the frozen-replay lesson: a re-bake that moves numbers is
    indistinguishable from a bug).
  * ``confirmed`` must be None when unknown, never False. "Tonight's pack did not
    carry this name" and "tonight's gate rejected it" are different claims and the
    second one is the whole measurement.

SOLE-WRITER LAW (G0.2) is asserted structurally: the R2 spool is read-only here, and
the only path this module writes is ``data/prophet_live/forward.parquet``.

Clock is injected everywhere (``--now`` / ``now=``) and the price fixtures carry their
own pinned index, so nothing in this file can rot against a wall-clock gate.
"""
from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.reconcile_prophet_live as R  # noqa: E402
from engine.grading import fill_index  # noqa: E402
from engine.prophet_live import r2io  # noqa: E402

#: Every session in this file is at or after R.LEDGER_FLOOR_SESSION — rows before the
#: floor are never accrued (B4), so pre-floor fixture dates would silently test nothing.
NOW = datetime(2026, 8, 4, 22, 30, tzinfo=timezone.utc)
#: A pinned session grid: weekdays from Mon 2026-07-27 onward.
IDX = pd.bdate_range("2026-07-27", periods=15)
D0 = "2026-08-03"        # the event session (a Monday)
D1 = "2026-08-04"        # the next session — the official fill bar
DPREV = "2026-07-31"     # the session before D0


def _series(start: float = 100.0) -> pd.Series:
    return pd.Series([start + i for i in range(len(IDX))], index=IDX, dtype=float)


def _event(ticker="AAA", kind="forming", price=105.0, session=D0, passes=2, frm="near",
           ts=None, entered="cross"):
    """A hand-built event row.

    Deliberately does NOT carry ``session_phase``: injecting a field here is how the
    round-trip assertion went green while the producer emitted nothing (the renamed-
    sentinel class). ``test_the_ledger_row_carries_the_producers_session_phase`` drives
    the REAL producer instead.
    """
    return {"ticker": ticker, "kind": kind, "ts": ts or f"{session}T14:05:00Z",
            "price": price, "quote_age_min": 3.0, "passes": passes, "from": frm,
            "entered": entered, "session_et": session, "pack_as_of": DPREV}


def _verdicts(mapping: dict[str, bool], basis: str = "pack"):
    """A ``verdicts_for(session, tickers)`` stub with a fixed answer."""
    return lambda session, tickers: ({t: v for t, v in mapping.items() if t in tickers},
                                     basis)


# ─────────────────────────────────────────────────────────────────────────────
# The fill convention
# ─────────────────────────────────────────────────────────────────────────────

def test_next_close_is_the_bar_strictly_after_the_event_session():
    s = _series()
    px, day = R.next_close(s, D0)
    # Not the event bar, and not two bars out: exactly engine.grading's fill.
    assert day == D1
    assert px == float(s.loc[pd.Timestamp(D1)])
    assert px != float(s.loc[pd.Timestamp(D0)])


def test_next_close_matches_engine_grading_fill_index_exactly():
    """One grader law: this ledger and grade_us_board must agree on "the fill"."""
    s = _series()
    for day in (str(d.date()) for d in IDX[:-1]):
        px, fday = R.next_close(s, day)
        loc = fill_index(s, pd.Timestamp(day))
        assert loc is not None
        assert px == float(s.iloc[loc])
        assert fday == str(pd.Timestamp(s.index[loc]).date())


def test_an_unmatured_fill_is_none_not_the_last_bar():
    """Frozen-until-matured: the final session has no bar after it yet."""
    s = _series()
    last = str(IDX[-1].date())
    assert R.next_close(s, last) == (None, None)
    assert fill_index(s, pd.Timestamp(last)) is None


def test_close_on_returns_none_for_a_non_session_date():
    s = _series()
    assert R.close_on(s, D0) == float(s.loc[pd.Timestamp(D0)])
    assert R.close_on(s, "2026-07-26") is None          # a Sunday
    assert R.close_on(None, D0) is None


def test_pct_needs_both_legs():
    assert R._pct(110.0, 100.0) == pytest.approx(10.0)
    assert R._pct(None, 100.0) is None
    assert R._pct(110.0, None) is None
    assert R._pct(110.0, 0.0) is None


# ─────────────────────────────────────────────────────────────────────────────
# The event -> confirmed join
# ─────────────────────────────────────────────────────────────────────────────

def test_confirmed_comes_from_a_verdict_of_the_rows_own_session():
    closes = {"AAA": _series(), "BBB": _series(50.0)}
    rows = R.build_rows([_event("AAA"), _event("BBB")],
                        verdicts_for=_verdicts({"AAA": True, "BBB": False}),
                        closes=closes, now=NOW)
    by = {r["ticker"]: r for r in rows}
    assert by["AAA"]["confirmed"] is True and by["AAA"]["confirmed_basis"] == "pack"
    assert by["BBB"]["confirmed"] is False


def test_confirmed_is_none_when_no_verdict_of_that_vintage_exists():
    """None, not False: "no verdict of this session" is not "the gate rejected it"."""
    rows = R.build_rows([_event("ZZZ")], verdicts_for=_verdicts({"AAA": True}),
                        closes={"ZZZ": _series()}, now=NOW)
    assert rows[0]["confirmed"] is None and rows[0]["confirmed_basis"] is None


def test_row_carries_the_measurement_the_program_exists_for():
    closes = {"AAA": _series()}
    s = closes["AAA"]
    rows = R.build_rows([_event("AAA", price=105.0)],
                        verdicts_for=_verdicts({"AAA": True}), closes=closes, now=NOW)
    r = rows[0]
    assert r["date"] == D0 and r["ticker"] == "AAA" and r["kind"] == "forming"
    assert r["cross_px"] == 105.0
    assert r["close_same_day"] == float(s.loc[pd.Timestamp(D0)])
    assert r["next_close_fill"] == float(s.loc[pd.Timestamp(D1)])
    assert r["next_close_date"] == D1
    # cross vs the OFFICIAL graded fill — the "earlier entry" delta, per event.
    assert r["fill_vs_cross_pct"] == pytest.approx(
        (r["next_close_fill"] / 105.0 - 1.0) * 100.0)
    assert r["close_vs_cross_pct"] == pytest.approx(
        (r["close_same_day"] / 105.0 - 1.0) * 100.0)
    assert r["passes"] == 2 and r["from_state"] == "near" and r["quote_age_min"] == 3.0
    assert r["entered"] == "cross"


def test_the_ledger_row_carries_the_producers_session_phase():
    """Round-trip through the REAL producer, not a fixture that injects the field.

    ``transitions()`` omitted ``session_phase`` from the event row while the artifact
    stamped it in meta, so every ledger row got None — and the covering test passed
    because its own fixture supplied the value. That is the renamed-sentinel /
    disarmed-test class: the assertion described a contract production never met.
    """
    from engine.prophet_live import live_states as LS

    entry = {"state": "near", "center_buyable": False, "as_of_close": 95.0,
             "probed": True, "buyable_in_band": True, "trigger_px": 100.0,
             "band_lo_px": 0.0, "band_hi_px": 109.25}
    cfg = LS.live_cfg(None)
    # 13:27Z is 09:27 ET — a pre-open print, materially different from an 11:00 one.
    for utc_hour, utc_min, expect in ((13, 27, "preopen"), (15, 0, "rth")):
        now = datetime(2026, 8, 3, utc_hour, utc_min, tzinfo=timezone.utc)
        prev = {"state": "near", "passes": 1, "internal": LS.CROSSING_UNCONFIRMED,
                "internal_seen": [LS.CROSSING_UNCONFIRMED]}
        st = LS.name_state(entry, price=101.0, quote_age_min=1.0, prev=prev,
                           now=now, cfg=cfg)
        rows = LS.transitions("AAA", st, prev, now=now)
        assert rows, "the producer emitted no transition to inspect"
        assert rows[0]["session_phase"] == expect, rows[0]
        # ... and it survives the join into the ledger row.
        ev = {**rows[0], "session_et": D0, "pack_as_of": DPREV}
        led = R.build_rows([ev], verdicts_for=_verdicts({"AAA": True}),
                           closes={"AAA": _series()}, now=NOW)
        assert led[0]["session_phase"] == expect


def test_the_first_cross_is_the_actionable_one_and_the_last_is_also_kept():
    """M6: keeping only the LAST occurrence recorded a 100 entry as a 108 entry.

    A name that forms at 10:00 and re-forms at 15:30 gave the ledger the 15:30 price,
    which is not what a user could have acted on — and the entry-advantage measurement
    is exactly a comparison against that price.
    """
    rows = R.build_rows([_event(price=100.0, ts=f"{D0}T14:00:00Z"),
                         _event(price=104.0, ts=f"{D0}T17:00:00Z"),
                         _event(price=108.0, ts=f"{D0}T19:30:00Z")],
                        verdicts_for=_verdicts({"AAA": True}),
                        closes={"AAA": _series()}, now=NOW)
    assert len(rows) == 1
    r = rows[0]
    assert r["first_px"] == 100.0 and r["first_ts"] == f"{D0}T14:00:00Z"
    assert r["last_px"] == 108.0 and r["last_ts"] == f"{D0}T19:30:00Z"
    assert r["occurrences"] == 3
    # The derived percentages key off the ACTIONABLE price.
    assert r["cross_px"] == 100.0
    assert r["fill_vs_cross_pct"] == pytest.approx(
        (r["next_close_fill"] / 100.0 - 1.0) * 100.0)


def test_out_of_order_spool_objects_still_yield_the_earliest_cross():
    rows = R.build_rows([_event(price=108.0, ts=f"{D0}T19:30:00Z"),
                         _event(price=100.0, ts=f"{D0}T14:00:00Z")],
                        verdicts_for=_verdicts({"AAA": True}),
                        closes={"AAA": _series()}, now=NOW)
    assert rows[0]["first_px"] == 100.0 and rows[0]["last_px"] == 108.0


def test_distinct_kinds_are_distinct_rows():
    rows = R.build_rows([_event(kind="forming"), _event(kind="faded"),
                         _event(kind="crossing_unconfirmed", passes=1)],
                        verdicts_for=_verdicts({"AAA": True}),
                        closes={"AAA": _series()}, now=NOW)
    assert sorted(r["kind"] for r in rows) == ["crossing_unconfirmed", "faded", "forming"]


def test_a_missing_close_series_leaves_the_fill_null_not_zero():
    rows = R.build_rows([_event("NOPRICE")], verdicts_for=_verdicts({}),
                        closes={}, now=NOW)
    r = rows[0]
    assert r["close_same_day"] is None and r["next_close_fill"] is None
    assert r["fill_vs_cross_pct"] is None
    assert r["cross_px"] == 105.0       # what we DID observe is still recorded


def test_events_without_a_session_are_dropped_not_dated_from_the_clock():
    bad = _event()
    bad["session_et"] = None
    assert R.build_rows([bad], verdicts_for=_verdicts({}), closes={}, now=NOW) == []


def test_sessions_before_the_ledger_floor_are_never_accrued():
    """B4: any pre-merge spool object may be a receipt fabrication, not a market pass.

    A fabricated row joined to real closes is indistinguishable from a genuine one
    forever, so the floor is a hard date rather than a judgement call.
    """
    old = _event(session="2026-07-29")
    assert R.LEDGER_FLOOR_SESSION == "2026-07-30"
    assert old["session_et"] < R.LEDGER_FLOOR_SESSION
    assert R.build_rows([old], verdicts_for=_verdicts({"AAA": True}),
                        closes={"AAA": _series()}, now=NOW) == []
    # A session at the floor accrues normally.
    ok = _event(session="2026-07-30")
    assert len(R.build_rows([ok], verdicts_for=_verdicts({"AAA": True}),
                            closes={"AAA": _series()}, now=NOW)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# B3 / M1 — confirmed-vintage discipline. Two REPRODUCED corruptions.
# ─────────────────────────────────────────────────────────────────────────────

def test_a_pack_from_the_wrong_session_never_supplies_confirmed():
    """M1: `load_verdicts` had no as_of check, so a pack-build-failure night graded
    today's events off YESTERDAY's pack via the R2 fallback."""
    closes = {"AAA": _series()}
    # Pack as_of is D1 but the row's session is D0 — the pack route must be refused
    # and the verdict recomputed on the session's own basis instead.
    got, basis = R.session_verdicts(D0, {"AAA"}, closes=closes, pack_as_of=D1,
                                    pack_verdicts={"AAA": True})
    assert basis == "replay"
    # Matching vintage takes the pack directly.
    got2, basis2 = R.session_verdicts(D0, {"AAA"}, closes=closes, pack_as_of=D0,
                                      pack_verdicts={"AAA": True})
    assert basis2 == "pack" and got2 == {"AAA": True}


def test_the_replay_basis_truncates_the_series_through_the_event_session(monkeypatch):
    """The replay must not see bars the session could not have seen."""
    from engine import signal_gate
    seen: dict[str, pd.Series] = {}

    def _gate(tkr, s):
        seen[tkr] = s
        return {"eligible": True, "tier_cascade": "T2"}

    monkeypatch.setattr(signal_gate, "gate", _gate)
    got, basis = R.session_verdicts(D0, {"AAA"}, closes={"AAA": _series()},
                                    pack_as_of=D1, pack_verdicts={})
    assert basis == "replay" and got == {"AAA": True}
    used = seen["AAA"]
    assert str(pd.Timestamp(used.index[-1]).date()) == D0
    assert pd.Timestamp(D1) not in pd.DatetimeIndex(used.index)
    assert len(used) < len(_series())


def test_a_verdict_is_never_restated_by_a_later_night(tmp_path):
    """B3: the default [yesterday, today] window re-processes session D on night D+1.

    Before the fix that second pass re-stamped `confirmed` from the D+1 pack, so every
    re-processed row carried a verdict one session too late — silently, and for every
    row the ledger ever wrote.
    """
    path = tmp_path / "forward.parquet"
    night1 = R.build_rows([_event("AAA")], verdicts_for=_verdicts({"AAA": True}),
                          closes={"AAA": _series()}, now=NOW)
    R.merge_ledger(path, night1).to_parquet(path, index=False)
    assert bool(pd.read_parquet(path).iloc[0]["confirmed"]) is True

    # Night D+1 re-reads the same spool and would answer False for the WRONG session.
    night2 = R.build_rows([_event("AAA")], verdicts_for=_verdicts({"AAA": False}),
                          closes={"AAA": _series()}, now=NOW)
    out = R.merge_ledger(path, night2)
    assert len(out) == 1
    assert bool(out.iloc[0]["confirmed"]) is True, "a later night restated the verdict"


def test_a_null_verdict_can_still_be_filled_in_later(tmp_path):
    """First-wins must not freeze a NULL: an unknown verdict is not an answer."""
    path = tmp_path / "forward.parquet"
    unknown = R.build_rows([_event("AAA")], verdicts_for=_verdicts({}),
                           closes={"AAA": _series()}, now=NOW)
    assert unknown[0]["confirmed"] is None
    R.merge_ledger(path, unknown).to_parquet(path, index=False)
    later = R.build_rows([_event("AAA")], verdicts_for=_verdicts({"AAA": True}),
                         closes={"AAA": _series()}, now=NOW)
    out = R.merge_ledger(path, later)
    assert bool(out.iloc[0]["confirmed"]) is True


def test_an_already_confirmed_session_costs_no_verdict_work(monkeypatch, tmp_path):
    """The replay is the step's only unbounded cost, and FIRST_WINS discards its answer.

    The default window re-processes yesterday's session every night; without this a busy
    day's tickers would run the gate hundreds of times against a 3-minute step cap for a
    value that cannot land.
    """
    path = tmp_path / R.LEDGER_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = R.build_rows([_event("AAA")], verdicts_for=_verdicts({"AAA": True}),
                        closes={"AAA": _series()}, now=NOW)
    R.merge_ledger(path, rows).to_parquet(path, index=False)
    assert R.confirmed_pairs(path) == {(D0, "AAA")}

    calls: list[str] = []
    monkeypatch.setattr(R, "session_verdicts",
                        lambda *a, **kw: calls.append(a[0]) or ({}, "replay"))
    monkeypatch.setattr(R.r2io, "client", lambda: object())
    monkeypatch.setattr(R.r2io, "list_keys",
                        lambda prefix, **kw: [f"{r2io.EVENTS_PREFIX}/{D0}/140505.json"])
    monkeypatch.setattr(R.r2io, "get_json", lambda key, **kw:
                        {"session_et": D0, "events": [_event("AAA")]} if D0 in key
                        else {"as_of": D1, "names": {}})
    monkeypatch.setattr(R, "load_closes", lambda t: {"AAA": _series()})

    assert R.run(tmp_path, now=NOW, sessions=[D0]) == 0
    assert calls == [], "re-derived a verdict that FIRST_WINS would discard"
    # ... and the stored verdict is untouched.
    assert bool(pd.read_parquet(path).iloc[0]["confirmed"]) is True


def test_confirmed_is_in_the_first_wins_set():
    assert "confirmed" in R.FIRST_WINS and "confirmed_basis" in R.FIRST_WINS
    assert "first_ts" in R.FIRST_WINS and "first_px" in R.FIRST_WINS
    assert "cross_px" in R.FIRST_WINS
    # The maturing fields must NOT be first-wins or a fill could never land.
    for col in ("next_close_fill", "next_close_date", "close_same_day"):
        assert col not in R.FIRST_WINS


def test_a_partial_spool_re_read_cannot_rebase_the_cross_price(tmp_path):
    """N2: one unreadable pass object used to put two different entries in one row.

    Night 1 sees the whole session: first cross 100, later re-forms at 108. A re-read
    where only the 15:30 object is readable rebuilt the row from a PARTIAL spool —
    ``first_px`` stayed frozen at 100 (FIRST_WINS) while ``cross_px`` and both derived
    percentages took 108, so a single row carried a 100 entry on a 108 basis with
    ``fill_vs_cross_pct`` flipped in sign. ``maturing_rows`` then re-derived from the
    clobbered value on the following night, making it permanent.
    """
    path = tmp_path / "forward.parquet"
    full = R.build_rows([_event(price=100.0, ts=f"{D0}T14:00:00Z"),
                         _event(price=108.0, ts=f"{D0}T19:30:00Z")],
                        verdicts_for=_verdicts({"AAA": True}),
                        closes={"AAA": _series()}, now=NOW)
    R.merge_ledger(path, full).to_parquet(path, index=False)
    before = pd.read_parquet(path).iloc[0]
    assert before["first_px"] == 100.0 and before["cross_px"] == 100.0
    fill = float(_series().loc[pd.Timestamp(D1)])
    assert before["fill_vs_cross_pct"] == pytest.approx((fill / 100.0 - 1.0) * 100.0)

    # The 14:00 object is now unreadable; only the 19:30 one survives.
    partial = R.build_rows([_event(price=108.0, ts=f"{D0}T19:30:00Z")],
                           verdicts_for=_verdicts({"AAA": True}),
                           closes={"AAA": _series()}, now=NOW)
    assert partial[0]["cross_px"] == 108.0        # the partial read genuinely sees 108
    out = R.merge_ledger(path, partial)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["first_px"] == 100.0
    assert row["cross_px"] == 100.0, "a partial re-read rebased the actionable price"
    # Both percentages are recomputed from the merged base, so the row is self-consistent.
    assert row["fill_vs_cross_pct"] == pytest.approx((fill / 100.0 - 1.0) * 100.0)
    same = float(_series().loc[pd.Timestamp(D0)])
    assert row["close_vs_cross_pct"] == pytest.approx((same / 100.0 - 1.0) * 100.0)

    # ... and the next night's maturing pass re-derives from the frozen base too.
    out.to_parquet(path, index=False)
    matured = R.maturing_rows(path, closes={"AAA": _series()}, now=NOW)
    for u in matured:
        assert u["fill_vs_cross_pct"] == pytest.approx((fill / 100.0 - 1.0) * 100.0)


def test_a_derived_percentage_is_always_a_function_of_the_merged_row(tmp_path):
    """Hand-planted inconsistency: the merge must not carry a stale ratio through."""
    path = tmp_path / "forward.parquet"
    planted = {"date": D0, "ticker": "AAA", "kind": "forming", "cross_px": 100.0,
               "close_same_day": 110.0, "next_close_fill": 120.0,
               "close_vs_cross_pct": -99.0, "fill_vs_cross_pct": -99.0}
    out = R.merge_ledger(path, [planted])
    row = out.iloc[0]
    assert row["close_vs_cross_pct"] == pytest.approx(10.0)
    assert row["fill_vs_cross_pct"] == pytest.approx(20.0)


# ─────────────────────────────────────────────────────────────────────────────
# Merge semantics
# ─────────────────────────────────────────────────────────────────────────────

def test_union_merge_is_idempotent(tmp_path):
    """Running the reconciler twice must not duplicate or move a single row."""
    path = tmp_path / "forward.parquet"
    rows = R.build_rows([_event("AAA"), _event("BBB", kind="faded")],
                        verdicts_for=_verdicts({"AAA": True, "BBB": False}),
                        closes={"AAA": _series(), "BBB": _series(50.0)}, now=NOW)
    first = R.merge_ledger(path, rows)
    first.to_parquet(path, index=False)
    second = R.merge_ledger(path, rows)
    assert len(first) == len(second) == 2
    pd.testing.assert_frame_equal(first, second)
    third = R.merge_ledger(path, rows)
    pd.testing.assert_frame_equal(second, third)


def test_a_maturing_fill_updates_in_place_without_erasing_the_event_night(tmp_path):
    path = tmp_path / "forward.parquet"
    open_row = {"date": D0, "ticker": "AAA", "kind": "forming", "ts": f"{D0}T14:05:00Z",
                "cross_px": 105.0, "quote_age_min": 3.0, "passes": 2,
                "from_state": "near", "pack_as_of": "2026-07-27", "confirmed": True,
                "close_same_day": 108.0, "next_close_fill": None,
                "next_close_date": None, "close_vs_cross_pct": 2.857,
                "fill_vs_cross_pct": None, "reconciled_at": "2026-07-28T22:30:00Z"}
    R.merge_ledger(path, [open_row]).to_parquet(path, index=False)
    assert R.open_rows(path) == [(D0, "AAA")]

    matured = {"date": D0, "ticker": "AAA", "kind": "forming", "next_close_fill": 109.0,
               "next_close_date": D1, "close_same_day": 108.0,
               "reconciled_at": "2026-07-29T22:30:00Z"}
    out = R.merge_ledger(path, [matured])
    assert len(out) == 1
    row = out.iloc[0]
    assert row["next_close_fill"] == 109.0 and row["next_close_date"] == D1
    # Everything the event night knew survives the fill-only update.
    assert row["cross_px"] == 105.0 and row["passes"] == 2
    assert row["from_state"] == "near" and bool(row["confirmed"]) is True
    assert row["ts"] == f"{D0}T14:05:00Z"
    out.to_parquet(path, index=False)
    assert R.open_rows(path) == []


def test_a_later_read_that_lost_the_fill_cannot_erase_it(tmp_path):
    """groupby-last keeps the newest NON-NULL value — updates can only add."""
    path = tmp_path / "forward.parquet"
    full = {"date": D0, "ticker": "AAA", "kind": "forming", "cross_px": 105.0,
            "next_close_fill": 109.0, "next_close_date": D1, "confirmed": True}
    R.merge_ledger(path, [full]).to_parquet(path, index=False)
    blank = {"date": D0, "ticker": "AAA", "kind": "forming", "cross_px": 105.0,
             "next_close_fill": None, "next_close_date": None, "confirmed": None}
    out = R.merge_ledger(path, [blank])
    assert out.iloc[0]["next_close_fill"] == 109.0
    assert out.iloc[0]["next_close_date"] == D1
    assert bool(out.iloc[0]["confirmed"]) is True


def test_maturing_rows_only_reports_what_actually_matured(tmp_path):
    path = tmp_path / "forward.parquet"
    rows = [{"date": D0, "ticker": "AAA", "kind": "forming", "next_close_fill": None},
            {"date": str(IDX[-1].date()), "ticker": "AAA", "kind": "forming",
             "next_close_fill": None}]
    R.merge_ledger(path, rows).to_parquet(path, index=False)
    got = R.maturing_rows(path, closes={"AAA": _series()}, now=NOW)
    assert [g["date"] for g in got] == [D0]         # the last session has no bar after it
    assert got[0]["next_close_fill"] == float(_series().loc[pd.Timestamp(D1)])


def test_a_maturing_fill_fans_out_to_every_kind_row_of_that_pair(tmp_path):
    path = tmp_path / "forward.parquet"
    rows = [{"date": D0, "ticker": "AAA", "kind": k, "next_close_fill": None}
            for k in ("forming", "faded", "confirming_into_close")]
    R.merge_ledger(path, rows).to_parquet(path, index=False)
    updates = R.maturing_rows(path, closes={"AAA": _series()}, now=NOW)
    fanned = R._expand_maturing(path, updates)
    assert sorted(u["kind"] for u in fanned) == ["confirming_into_close", "faded", "forming"]
    out = R.merge_ledger(path, fanned)
    assert out["next_close_fill"].notna().all()


def test_merge_survives_an_unreadable_existing_ledger(tmp_path, capsys):
    path = tmp_path / "forward.parquet"
    path.write_bytes(b"not a parquet file")
    out = R.merge_ledger(path, [{"date": D0, "ticker": "AAA", "kind": "forming"}])
    assert len(out) == 1
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live-reconcile::")


def test_empty_rows_leave_an_existing_ledger_untouched(tmp_path):
    path = tmp_path / "forward.parquet"
    R.merge_ledger(path, [{"date": D0, "ticker": "AAA", "kind": "forming"}]).to_parquet(
        path, index=False)
    out = R.merge_ledger(path, [])
    assert len(out) == 1 and out.iloc[0]["ticker"] == "AAA"


# ─────────────────────────────────────────────────────────────────────────────
# Spool reading
# ─────────────────────────────────────────────────────────────────────────────

def test_spool_sessions_groups_pass_objects_by_et_date(monkeypatch):
    keys = [f"{r2io.EVENTS_PREFIX}/{D0}/100005.json",
            f"{r2io.EVENTS_PREFIX}/{D0}/143005.json",
            f"{r2io.EVENTS_PREFIX}/{D1}/093505.json",
            f"{r2io.EVENTS_PREFIX}/{D1}/notjson.txt",
            f"{r2io.EVENTS_PREFIX}/stray.json"]
    monkeypatch.setattr(R.r2io, "list_keys", lambda prefix, **kw: keys)
    got = R.spool_sessions(s3=object())
    assert sorted(got) == [D0, D1]
    assert got[D0] == sorted(got[D0]) and len(got[D0]) == 2
    assert len(got[D1]) == 1                       # notjson.txt and stray.json dropped
    only = R.spool_sessions(s3=object(), sessions=[D1])
    assert list(only) == [D1]


def test_spool_listing_asks_only_for_the_target_session_prefixes(monkeypatch):
    """m7: the spool grows ~80 objects a session forever.

    Paginating the whole history to pick out two days would list thousands of keys a
    night for nothing.
    """
    asked: list[str] = []
    monkeypatch.setattr(R.r2io, "list_keys",
                        lambda prefix, **kw: asked.append(prefix) or [])
    R.spool_sessions(s3=object(), sessions=[D0, D1])
    assert asked == [f"{r2io.EVENTS_PREFIX}/{D0}/", f"{r2io.EVENTS_PREFIX}/{D1}/"]
    asked.clear()
    R.spool_sessions(s3=object())            # no sessions => the whole prefix, once
    assert asked == [f"{r2io.EVENTS_PREFIX}/"]


def test_pre_floor_sessions_are_dropped_even_if_the_spool_has_them(monkeypatch):
    old = "2026-07-15"
    monkeypatch.setattr(R.r2io, "list_keys", lambda prefix, **kw: [
        f"{r2io.EVENTS_PREFIX}/{old}/100005.json",
        f"{r2io.EVENTS_PREFIX}/{D0}/100005.json"])
    got = R.spool_sessions(s3=object())
    assert list(got) == [D0]


def test_load_events_skips_malformed_rows(monkeypatch):
    obj = {"session_et": D0, "pack_as_of": "2026-07-27",
           "events": [_event(), {"kind": "forming"}, {"ticker": "X"}, "not a dict", None]}
    monkeypatch.setattr(R.r2io, "get_json", lambda key, **kw: obj)
    rows = R.load_events(["k1"], s3=object())
    assert len(rows) == 1 and rows[0]["ticker"] == "AAA"
    assert rows[0]["session_et"] == D0 and rows[0]["_spool_key"] == "k1"


def test_load_verdicts_returns_the_as_of_with_the_verdicts(tmp_path, monkeypatch):
    """M1: the as_of MUST come back, or a caller cannot know which session it describes."""
    import json
    p = tmp_path / "pack.json"
    p.write_text(json.dumps({"as_of": D0,
                             "names": {"AAA": {"center_buyable": True},
                                       "bbb": {"center_buyable": False}}}))
    monkeypatch.setattr(R.r2io, "get_json", lambda key, **kw: None)
    got, as_of = R.load_verdicts(p)
    assert got == {"AAA": True, "BBB": False}      # upper-cased for the join
    assert as_of == D0
    assert R.load_verdicts(None) == ({}, None)


# ─────────────────────────────────────────────────────────────────────────────
# G0.2 — sole writer, and the CLI contract
# ─────────────────────────────────────────────────────────────────────────────

def test_the_only_written_path_is_the_forward_ledger():
    tree = ast.parse((ROOT / "scripts" / "reconcile_prophet_live.py").read_text(
        encoding="utf-8"))
    writes = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr in ("to_parquet", "write_text", "write_bytes", "put_json",
                                  "put_object")]
    # One to_parquet (the ledger). No R2 write of any kind: the spool is read-only here.
    assert [n.func.attr for n in writes] == ["to_parquet"]
    assert R.LEDGER_REL == Path("data") / "prophet_live" / "forward.parquet"
    assert R.KEY == ["date", "ticker", "kind"]


def test_without_nightly_it_writes_nothing(capsys):
    assert R.main([]) == 0
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live-reconcile::")
    assert "sole writer" in warn[0]


def test_an_unparseable_now_fails_loudly(capsys):
    assert R.main(["--nightly", "--now", "yesterday-ish"]) == 2
    err = [ln for ln in capsys.readouterr().out.splitlines() if "::error" in ln]
    assert err and err[0].startswith("::error title=prophet-live-reconcile::")


def test_no_r2_credentials_accrues_nothing_and_says_so(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(R.r2io, "client", lambda: None)
    assert R.run(tmp_path, now=NOW) == 0
    assert not (tmp_path / R.LEDGER_REL).exists()
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live-reconcile::")


def test_run_writes_the_ledger_end_to_end(monkeypatch, tmp_path):
    obj = {"session_et": D0, "pack_as_of": DPREV, "events": [_event("AAA")]}
    monkeypatch.setattr(R.r2io, "client", lambda: object())
    monkeypatch.setattr(R.r2io, "list_keys",
                        lambda prefix, **kw: [f"{r2io.EVENTS_PREFIX}/{D0}/140505.json"])
    # The pack's as_of IS the event session, so `confirmed` comes from it directly.
    monkeypatch.setattr(R.r2io, "get_json", lambda key, **kw:
                        obj if key.endswith(".json") and D0 in key
                        else {"as_of": D0, "names": {"AAA": {"center_buyable": True}}})
    monkeypatch.setattr(R, "load_closes", lambda t: {"AAA": _series()})

    assert R.run(tmp_path, now=NOW, sessions=[D0]) == 0
    df = pd.read_parquet(tmp_path / R.LEDGER_REL)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["ticker"] == "AAA" and row["kind"] == "forming"
    assert bool(row["confirmed"]) is True and row["confirmed_basis"] == "pack"
    assert row["next_close_fill"] == float(_series().loc[pd.Timestamp(D1)])
    assert row["first_px"] == 105.0 and row["occurrences"] == 1

    # A second identical run changes nothing. The clock is PINNED (now=NOW) — the only
    # per-run field is reconciled_at, so byte-identity is a real claim here rather
    # than an accident of running the two passes inside the same second.
    before = pd.read_parquet(tmp_path / R.LEDGER_REL)
    assert R.run(tmp_path, now=NOW, sessions=[D0]) == 0
    pd.testing.assert_frame_equal(before, pd.read_parquet(tmp_path / R.LEDGER_REL))


def test_dry_run_writes_no_parquet(monkeypatch, tmp_path):
    obj = {"session_et": D0, "events": [_event("AAA")]}
    monkeypatch.setattr(R.r2io, "client", lambda: object())
    monkeypatch.setattr(R.r2io, "list_keys",
                        lambda prefix, **kw: [f"{r2io.EVENTS_PREFIX}/{D0}/140505.json"])
    monkeypatch.setattr(R.r2io, "get_json", lambda key, **kw: obj if D0 in key else {})
    monkeypatch.setattr(R, "load_closes", lambda t: {"AAA": _series()})
    assert R.run(tmp_path, now=NOW, sessions=[D0], dry_run=True) == 0
    assert not (tmp_path / R.LEDGER_REL).exists()


def test_the_default_window_covers_yesterday_and_today_in_et(monkeypatch, tmp_path):
    """A 16:10 ET pass lands after the UTC date rolled; a today-only window loses it."""
    asked: list[list[str] | None] = []
    monkeypatch.setattr(R.r2io, "client", lambda: object())
    monkeypatch.setattr(R, "spool_sessions",
                        lambda **kw: asked.append(kw.get("sessions")) or {})
    monkeypatch.setattr(R, "load_verdicts", lambda *a, **kw: ({}, None))
    # 02:30Z on 2026-08-05 is still 22:30 ET on the 4th.
    R.run(tmp_path, now=datetime(2026, 8, 5, 2, 30, tzinfo=timezone.utc))
    assert asked[0] == [D0, D1]                          # ET date is still the 4th


def test_the_default_window_is_clipped_to_the_ledger_floor(monkeypatch, tmp_path, capsys):
    """A run whose whole window predates the floor accrues nothing and says so."""
    monkeypatch.setattr(R.r2io, "client", lambda: object())
    called: list[int] = []
    monkeypatch.setattr(R, "spool_sessions", lambda **kw: called.append(1) or {})
    assert R.run(tmp_path, now=datetime(2026, 7, 29, 22, 30, tzinfo=timezone.utc)) == 0
    assert called == [], "listed the spool for sessions it may never accrue"
    assert "before the ledger floor" in capsys.readouterr().out


def test_an_unmatured_fill_round_trips_as_null_not_zero(tmp_path):
    """A null fill must read back null. As 0.0 it would enter every mean silently."""
    path = tmp_path / "forward.parquet"
    matured = {"date": D0, "ticker": "AAA", "kind": "forming",
               "next_close_fill": 109.0, "fill_vs_cross_pct": 3.8}
    unmatured = {"date": D1, "ticker": "AAA", "kind": "forming",
                 "next_close_fill": None, "fill_vs_cross_pct": None}
    R.merge_ledger(path, [matured, unmatured]).to_parquet(path, index=False)
    back = pd.read_parquet(path).set_index("date")
    assert back.loc[D0, "next_close_fill"] == 109.0
    assert pd.isna(back.loc[D1, "next_close_fill"])
    assert pd.isna(back.loc[D1, "fill_vs_cross_pct"])
    assert R.open_rows(path) == [(D1, "AAA")]
