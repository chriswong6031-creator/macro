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

NOW = datetime(2026, 7, 29, 22, 30, tzinfo=timezone.utc)
#: A pinned session grid: Mon 2026-07-27 .. Fri 2026-07-31, then the following week.
IDX = pd.bdate_range("2026-07-20", periods=15)
D0 = "2026-07-28"        # the event session
D1 = "2026-07-29"        # the next session — the official fill bar


def _series(start: float = 100.0) -> pd.Series:
    return pd.Series([start + i for i in range(len(IDX))], index=IDX, dtype=float)


def _event(ticker="AAA", kind="forming", price=105.0, session=D0, passes=2, frm="near"):
    return {"ticker": ticker, "kind": kind, "ts": f"{session}T14:05:00Z", "price": price,
            "quote_age_min": 3.0, "passes": passes, "from": frm,
            "session_et": session, "pack_as_of": "2026-07-27"}


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

def test_confirmed_comes_from_tonights_real_verdict():
    closes = {"AAA": _series(), "BBB": _series(50.0)}
    rows = R.build_rows([_event("AAA"), _event("BBB")],
                        verdicts={"AAA": True, "BBB": False}, closes=closes, now=NOW)
    by = {r["ticker"]: r for r in rows}
    assert by["AAA"]["confirmed"] is True
    assert by["BBB"]["confirmed"] is False


def test_confirmed_is_none_when_the_pack_did_not_carry_the_name():
    """None, not False: "not in tonight's pack" is not "the gate rejected it"."""
    rows = R.build_rows([_event("ZZZ")], verdicts={"AAA": True},
                        closes={"ZZZ": _series()}, now=NOW)
    assert rows[0]["confirmed"] is None


def test_row_carries_the_measurement_the_program_exists_for():
    closes = {"AAA": _series()}
    s = closes["AAA"]
    rows = R.build_rows([_event("AAA", price=105.0)], verdicts={"AAA": True},
                        closes=closes, now=NOW)
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


def test_the_last_occurrence_of_a_kind_wins_within_a_session():
    """A name that forms twice in a day contributes one `forming` row, the later one."""
    rows = R.build_rows([_event(price=101.0), _event(price=109.0)],
                        verdicts={"AAA": True}, closes={"AAA": _series()}, now=NOW)
    assert len(rows) == 1 and rows[0]["cross_px"] == 109.0


def test_distinct_kinds_are_distinct_rows():
    rows = R.build_rows([_event(kind="forming"), _event(kind="faded"),
                         _event(kind="crossing_unconfirmed", passes=1)],
                        verdicts={"AAA": True}, closes={"AAA": _series()}, now=NOW)
    assert sorted(r["kind"] for r in rows) == ["crossing_unconfirmed", "faded", "forming"]


def test_a_missing_close_series_leaves_the_fill_null_not_zero():
    rows = R.build_rows([_event("NOPRICE")], verdicts={}, closes={}, now=NOW)
    r = rows[0]
    assert r["close_same_day"] is None and r["next_close_fill"] is None
    assert r["fill_vs_cross_pct"] is None
    assert r["cross_px"] == 105.0       # what we DID observe is still recorded


def test_events_without_a_session_are_dropped_not_dated_from_the_clock():
    bad = _event()
    bad["session_et"] = None
    assert R.build_rows([bad], verdicts={}, closes={}, now=NOW) == []


# ─────────────────────────────────────────────────────────────────────────────
# Merge semantics
# ─────────────────────────────────────────────────────────────────────────────

def test_union_merge_is_idempotent(tmp_path):
    """Running the reconciler twice must not duplicate or move a single row."""
    path = tmp_path / "forward.parquet"
    rows = R.build_rows([_event("AAA"), _event("BBB", kind="faded")],
                        verdicts={"AAA": True, "BBB": False},
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


def test_load_events_skips_malformed_rows(monkeypatch):
    obj = {"session_et": D0, "pack_as_of": "2026-07-27",
           "events": [_event(), {"kind": "forming"}, {"ticker": "X"}, "not a dict", None]}
    monkeypatch.setattr(R.r2io, "get_json", lambda key, **kw: obj)
    rows = R.load_events(["k1"], s3=object())
    assert len(rows) == 1 and rows[0]["ticker"] == "AAA"
    assert rows[0]["session_et"] == D0 and rows[0]["_spool_key"] == "k1"


def test_load_verdicts_reads_center_buyable_from_the_pack(tmp_path, monkeypatch):
    import json
    p = tmp_path / "pack.json"
    p.write_text(json.dumps({"names": {"AAA": {"center_buyable": True},
                                       "bbb": {"center_buyable": False}}}))
    monkeypatch.setattr(R.r2io, "get_json", lambda key, **kw: None)
    got = R.load_verdicts(p)
    assert got == {"AAA": True, "BBB": False}      # upper-cased for the join
    assert R.load_verdicts(None) == {}


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
    obj = {"session_et": D0, "pack_as_of": "2026-07-27", "events": [_event("AAA")]}
    monkeypatch.setattr(R.r2io, "client", lambda: object())
    monkeypatch.setattr(R.r2io, "list_keys",
                        lambda prefix, **kw: [f"{r2io.EVENTS_PREFIX}/{D0}/140505.json"])
    monkeypatch.setattr(R.r2io, "get_json", lambda key, **kw:
                        obj if key.endswith(".json") and D0 in key
                        else {"names": {"AAA": {"center_buyable": True}}})
    monkeypatch.setattr(R, "load_closes", lambda t: {"AAA": _series()})

    assert R.run(tmp_path, now=NOW, sessions=[D0]) == 0
    df = pd.read_parquet(tmp_path / R.LEDGER_REL)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["ticker"] == "AAA" and row["kind"] == "forming"
    assert bool(row["confirmed"]) is True
    assert row["next_close_fill"] == float(_series().loc[pd.Timestamp(D1)])

    # A second identical run changes nothing (frozen-replay discipline).
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
    monkeypatch.setattr(R, "load_verdicts", lambda *a, **kw: {})
    R.run(tmp_path, now=datetime(2026, 7, 30, 2, 30, tzinfo=timezone.utc))
    assert asked[0] == ["2026-07-28", "2026-07-29"]      # ET date is still the 29th


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
