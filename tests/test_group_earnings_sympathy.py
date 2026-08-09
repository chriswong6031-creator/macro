"""Earnings-sympathy math + the append-only sympathy ledger (Group Reads W-GR2).

The ratio is the one stat in this wave that cannot be eyeballed, so it is pinned on a
hand-built fixture where the answer is arithmetic rather than judgment: every quiet
session moves each member exactly +1%, every member report day moves them exactly +/-3%,
so the correct ratio is 3.0 and nothing else.

The fixture is deliberately MAJORITY report days. That is what makes the baseline-exclusion
assertion bite: the median is a robust statistic, so a contaminated baseline built from a
window with only a handful of report days still reads 1% and the bug hides. With 24 report
days against 16 quiet ones a baseline that forgets to exclude them reads 3% and the ratio
collapses to 1.0 — a mutation run confirms this test goes red for exactly that edit, while
the end-to-end suite does not.
"""
from __future__ import annotations

import builtins
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

from engine import group_earnings as ge
from lib import config

MEMBERS = list("ABCDEF")
N_SESSIONS = 40
QUIET = 0.01
EVENT = 0.03


def _sessions(n: int = N_SESSIONS) -> pd.DatetimeIndex:
    return pd.bdate_range(start="2026-01-05", periods=n)


def _fixture(report_positions: list[int], reporters: list[list[str]],
             signs: list[int | None], n: int = N_SESSIONS):
    """(adj, events, sessions) for a hand-specified event schedule.

    adj[t, s] = EVENT on any session some member reports into (signed by that day's
    surprise sign) and QUIET everywhere else — so the pooled event median is EVENT and the
    uncontaminated baseline median is QUIET, by construction."""
    sessions = _sessions(n)
    adj = pd.DataFrame(QUIET, index=sessions, columns=MEMBERS, dtype=float)
    events: dict[str, list[dict]] = {t: [] for t in MEMBERS}
    for pos, day_reporters, sign in zip(report_positions, reporters, signs):
        adj.iloc[pos] = EVENT if (sign is None or sign >= 0) else -EVENT
        for t in day_reporters:
            events[t].append({"event_date": sessions[pos], "surprise_pct":
                              None if sign is None else float(sign)})
    return adj, events, sessions


def _even_schedule(n_days: int = 24, n_quiet_first: int = 8):
    """n_days report days, one reporter each, cycling the roster; first half beats, second
    half misses. Report days outnumber quiet ones — see the module docstring."""
    positions = list(range(n_quiet_first, n_quiet_first + n_days))
    reporters = [[MEMBERS[i % len(MEMBERS)]] for i in range(n_days)]
    signs = [1] * (n_days // 2) + [-1] * (n_days - n_days // 2)
    return positions, reporters, signs


# --------------------------------------------------------------------------- #
# the ratio
# --------------------------------------------------------------------------- #
def test_ratio_is_the_pooled_event_median_over_the_quiet_baseline_median():
    adj, events, sessions = _fixture(*_even_schedule())
    block, rows = ge.sympathy(MEMBERS, events, adj, sessions)
    assert block["ratio"] == pytest.approx(EVENT / QUIET)     # 3.0
    assert block["n_events"] == 24
    assert block["n_reporters"] == 6
    assert block["window_q"] == ge.WINDOW_Q
    assert len(rows) == 24


def test_baseline_excludes_every_basket_member_report_day():
    """The decisive check. 24 report days vs 16 quiet: a baseline that kept the report days
    would median to 3% and hand back a ratio of 1.0 — 'these members move no differently
    around earnings', the exact opposite of what the fixture encodes."""
    adj, events, sessions = _fixture(*_even_schedule())
    block, _ = ge.sympathy(MEMBERS, events, adj, sessions)
    assert block["ratio"] != pytest.approx(1.0), "baseline was contaminated by report days"
    assert block["ratio"] == pytest.approx(3.0)

    # and the arithmetic the assertion rests on, spelled out
    report_days = {e["event_date"] for evs in events.values() for e in evs}
    contaminated = float(np.median(adj.abs().to_numpy().ravel()))
    clean = float(np.median(adj.loc[[d for d in sessions if d not in report_days]]
                            .abs().to_numpy().ravel()))
    assert contaminated == pytest.approx(EVENT) and clean == pytest.approx(QUIET)


def test_a_reporter_is_never_in_its_own_sympathy_cohort():
    """Sympathy is about the members that did NOT report. Put a 50% move on the reporter
    alone: if it leaked into the cohort the pooled median would move off EVENT."""
    positions, reporters, signs = _even_schedule()
    adj, events, sessions = _fixture(positions, reporters, signs)
    for pos, day_reporters in zip(positions, reporters):
        adj.iloc[pos, adj.columns.get_loc(day_reporters[0])] = 0.50
    block, rows = ge.sympathy(MEMBERS, events, adj, sessions)
    assert block["ratio"] == pytest.approx(3.0)
    assert {r["n_cohort"] for r in rows} == {len(MEMBERS) - 1}


def test_co_reporters_are_excluded_from_each_others_cohort():
    positions, reporters, signs = _even_schedule()
    reporters = [["A", "B"] if i == 0 else r for i, r in enumerate(reporters)]
    adj, events, sessions = _fixture(positions, reporters, signs)
    _, rows = ge.sympathy(MEMBERS, events, adj, sessions)
    first_day = min(r["event_date"] for r in rows)
    day_rows = [r for r in rows if r["event_date"] == first_day]
    assert {r["reporter_ticker"] for r in day_rows} == {"A", "B"}
    assert {r["n_cohort"] for r in day_rows} == {4}, "a co-reporter stayed in the cohort"


def test_a_day_with_too_few_non_reporters_is_dropped_entirely():
    """MIN_COHORT is 3. Four of six members reporting leaves a cohort of two — that day
    must contribute no event, no row and no move to the pool, rather than a two-name
    'median'."""
    positions, reporters, signs = _even_schedule()
    reporters = [list("ABCD") if i == 0 else r for i, r in enumerate(reporters)]
    adj, events, sessions = _fixture(positions, reporters, signs)
    block, rows = ge.sympathy(MEMBERS, events, adj, sessions)
    dropped = _sessions()[positions[0]].date().isoformat()
    assert all(r["event_date"] != dropped for r in rows)
    assert block["n_events"] == 23        # 24 scheduled, the 4-reporter day dropped


# --------------------------------------------------------------------------- #
# floors
# --------------------------------------------------------------------------- #
def test_below_the_event_floor_the_ratio_nulls_but_the_counts_print():
    adj, events, sessions = _fixture(*_even_schedule(n_days=11))
    block, rows = ge.sympathy(MEMBERS, events, adj, sessions)
    assert block["ratio"] is None
    assert block["n_events"] == 11 and block["n_reporters"] == 6
    assert "n_events>=12" in block["basis"]
    assert rows, "ledger rows are still emitted below the display floor"


def test_below_the_reporter_floor_the_ratio_nulls_even_with_plenty_of_events():
    """20 events, but only three distinct reporters — one name's earnings pattern is not a
    group read, so the ratio refuses on n_reporters alone."""
    positions = list(range(8, 28))
    reporters = [[["A", "B", "C"][i % 3]] for i in range(20)]
    adj, events, sessions = _fixture(positions, reporters, [1] * 20)
    block, _ = ge.sympathy(MEMBERS, events, adj, sessions)
    assert block["n_events"] == 20 and block["n_reporters"] == 3
    assert block["ratio"] is None
    assert "n_reporters>=4" in block["basis"]


def test_a_refused_block_keeps_the_full_key_set():
    adj, events, sessions = _fixture(*_even_schedule(n_days=11))
    block, _ = ge.sympathy(MEMBERS, events, adj, sessions)
    assert set(block) == {"ratio", "n_events", "n_reporters", "window_q", "basis",
                          "directional"}
    assert set(block["directional"]) == {"beat_day_median", "miss_day_median",
                                         "n_beat_days", "n_miss_days"}


def test_too_few_members_refuses_before_any_arithmetic():
    adj, events, sessions = _fixture(*_even_schedule())
    block, rows = ge.sympathy(["A", "B", "C"], events, adj, sessions)
    assert block["ratio"] is None and block["n_events"] == 0 and rows == []


# --------------------------------------------------------------------------- #
# directional split
# --------------------------------------------------------------------------- #
def test_directional_split_medians_the_signed_non_reporter_move():
    adj, events, sessions = _fixture(*_even_schedule())
    block = ge.sympathy(MEMBERS, events, adj, sessions)[0]["directional"]
    assert block["n_beat_days"] == 12 and block["n_miss_days"] == 12
    assert block["beat_day_median"] == pytest.approx(EVENT)
    assert block["miss_day_median"] == pytest.approx(-EVENT)


def test_each_half_of_the_split_nulls_on_its_own_floor():
    """Four beat days and twenty miss days: the miss median publishes, the beat median
    does not, and both counts stay visible."""
    positions = list(range(8, 32))
    reporters = [[MEMBERS[i % 6]] for i in range(24)]
    signs = [1] * 4 + [-1] * 20
    adj, events, sessions = _fixture(positions, reporters, signs)
    d = ge.sympathy(MEMBERS, events, adj, sessions)[0]["directional"]
    assert d["n_beat_days"] == 4 and d["beat_day_median"] is None
    assert d["n_miss_days"] == 20 and d["miss_day_median"] == pytest.approx(-EVENT)
    assert ge.MIN_DIRECTIONAL_DAYS == 5


def test_an_unsigned_report_day_counts_for_the_ratio_but_neither_direction():
    """Most report days in the live store have no consensus attached. They are real events
    — they belong in n_events — but they cannot be called a beat or a miss."""
    positions, reporters, _ = _even_schedule()
    adj, events, sessions = _fixture(positions, reporters, [None] * 24)
    block, rows = ge.sympathy(MEMBERS, events, adj, sessions)
    assert block["n_events"] == 24 and block["ratio"] == pytest.approx(3.0)
    d = block["directional"]
    assert (d["n_beat_days"], d["n_miss_days"]) == (0, 0)
    assert d["beat_day_median"] is None and d["miss_day_median"] is None
    assert all(r["surprise_sign"] is None for r in rows)


def test_a_day_that_is_both_a_beat_and_a_miss_counts_for_neither():
    positions, reporters, signs = _even_schedule()
    reporters = [["A", "B"] if i == 0 else r for i, r in enumerate(reporters)]
    adj, events, sessions = _fixture(positions, reporters, signs)
    events["B"][0]["surprise_pct"] = -1.0          # same day, opposite sign
    d = ge.sympathy(MEMBERS, events, adj, sessions)[0]["directional"]
    assert d["n_beat_days"] == 11, "an ambiguous day was scored as a beat"


# --------------------------------------------------------------------------- #
# reaction-session rule + Item-2.02 tokenisation
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("minutes,offset,why", [
    (20 * 60 + 15, 1, "after-hours print prices the NEXT session"),
    (11 * 60, 0, "pre-open print prices THAT session"),
    (14 * 60 + 29, 0, "one minute inside the cut is still pre-open"),
    (14 * 60 + 30, 1, "the cut itself is after-hours"),
    (None, 1, "an untimed date is treated as after-hours, the modal case"),
])
def test_reaction_session_rule(minutes, offset, why):
    s = _sessions(10)
    assert ge._reaction_session(s, s[3], minutes) == s[3 + offset], why


def test_an_announcement_past_the_last_session_has_no_reaction_session():
    s = _sessions(10)
    assert ge._reaction_session(s, s[-1], 20 * 60) is None


def test_item_202_matching_is_exact_token_never_substring():
    assert ge._has_item_202("2.02,9.01") is True
    assert ge._has_item_202(" 2.02 ") is True
    assert ge._has_item_202("12.02,9.01") is False, "substring match swallowed 12.02"
    assert ge._has_item_202("2.020") is False
    assert ge._has_item_202("") is False
    assert ge._has_item_202(None) is False


CASES_202 = ["2.02,9.01", " 2.02 ", "12.02,9.01", "2.020", "8.01", "", None,
             "9.01,2.02,8.01", "2.02 , 9.01", "112.02", "2.02.1"]


def test_local_202_fallback_agrees_with_the_collectors_definition(monkeypatch):
    """_has_item_202 prefers collectors.edgar_earnings_8k.has_item_202 but falls back to a
    local check, because that module imports `requests` at module scope and a minimal CI
    env may not have it. Comparing the two while the import SUCCEEDS is vacuous — both
    names resolve to the same function — so the import is broken first, which is the only
    way the fallback branch ever executes."""
    try:
        from collectors.edgar_earnings_8k import has_item_202
    except Exception:                                    # pragma: no cover - env dependent
        pytest.skip("collectors.edgar_earnings_8k unimportable in this env")
    expected = {raw: bool(has_item_202(raw)) for raw in CASES_202}

    real_import = builtins.__import__

    def _blocked(name, *a, **kw):
        if name == "collectors.edgar_earnings_8k":
            raise ImportError("simulated missing `requests`")
        return real_import(name, *a, **kw)

    monkeypatch.delitem(sys.modules, "collectors.edgar_earnings_8k", raising=False)
    monkeypatch.setattr(builtins, "__import__", _blocked)
    assert ge._has_item_202("2.02") is True, "the fallback branch did not execute"
    for raw in CASES_202:
        assert ge._has_item_202(raw) is expected[raw], f"fallback drifted on {raw!r}"


# --------------------------------------------------------------------------- #
# the append-only sympathy ledger
# --------------------------------------------------------------------------- #
ROWS = [
    {"basket_id": "b1", "event_date": "2026-05-01", "reporter_ticker": "A",
     "surprise_sign": 1, "n_cohort": 5, "cohort_median_abs_move": 0.021,
     "cohort_median_signed_move": 0.017},
    {"basket_id": "b1", "event_date": "2026-05-08", "reporter_ticker": "B",
     "surprise_sign": -1, "n_cohort": 5, "cohort_median_abs_move": 0.019,
     "cohort_median_signed_move": -0.011},
    {"basket_id": "b2", "event_date": "2026-05-08", "reporter_ticker": "B",
     "surprise_sign": None, "n_cohort": 4, "cohort_median_abs_move": 0.030,
     "cohort_median_signed_move": 0.004},
]


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    return ge.sympathy_ledger_path()


def test_intraday_lanes_do_not_advance_the_ledger(tmp_path, monkeypatch):
    """House law: the nightly is the sole advancer of forward ledgers."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    assert ge.append_sympathy_ledger(ROWS) == 0
    assert not ge.sympathy_ledger_path().exists()


def test_nightly_advance_writes_the_declared_schema(ledger):
    assert ge.append_sympathy_ledger(ROWS) == 3
    df = pd.read_parquet(ledger)
    assert list(df.columns) == ge.LEDGER_COLUMNS
    assert len(df) == 3
    assert df["advanced_at"].notna().all()
    assert df["surprise_sign"].isna().sum() == 1, "an unsigned event lost its null"


def test_re_advancing_identical_inputs_is_a_byte_for_byte_no_op(ledger):
    ge.append_sympathy_ledger(ROWS)
    before = ledger.read_bytes()
    assert ge.append_sympathy_ledger(ROWS) == 0
    assert ledger.read_bytes() == before, "an idempotent advance rewrote the store"


def test_a_second_advance_never_duplicates_a_key(ledger):
    ge.append_sympathy_ledger(ROWS)
    ge.append_sympathy_ledger(ROWS + ROWS)
    df = pd.read_parquet(ledger)
    assert len(df) == 3
    assert not df.duplicated(subset=ge.LEDGER_KEY).any()


def test_existing_rows_are_immutable_when_new_days_arrive(ledger):
    ge.append_sympathy_ledger(ROWS)
    first = pd.read_parquet(ledger).sort_values(ge.LEDGER_KEY).reset_index(drop=True)
    fresh = dict(ROWS[0], event_date="2026-08-07", cohort_median_abs_move=0.044)
    assert ge.append_sympathy_ledger([*ROWS, fresh]) == 1
    after = pd.read_parquet(ledger)
    assert len(after) == 4
    kept = (after[after["event_date"] != "2026-08-07"]
            .sort_values(ge.LEDGER_KEY).reset_index(drop=True))
    pd.testing.assert_frame_equal(first, kept)


def test_a_restated_value_for_an_existing_key_is_refused_not_applied(ledger):
    """Rows are historical facts. A later run that recomputes an old event day differently
    must leave the recorded row alone — the ledger is the record of what was measured, not
    a cache of the current best guess."""
    ge.append_sympathy_ledger(ROWS)
    restated = dict(ROWS[0], cohort_median_abs_move=9.99, surprise_sign=-1, n_cohort=99)
    assert ge.append_sympathy_ledger([restated]) == 0
    df = pd.read_parquet(ledger)
    row = df[(df["basket_id"] == "b1") & (df["event_date"] == "2026-05-01")].iloc[0]
    assert float(row["cohort_median_abs_move"]) == pytest.approx(0.021)
    assert int(row["surprise_sign"]) == 1 and int(row["n_cohort"]) == 5


def test_the_same_event_day_in_two_baskets_is_two_rows(ledger):
    """basket_id is part of the key: the same reporter on the same day yields a different
    cohort in every basket that holds it."""
    ge.append_sympathy_ledger(ROWS)
    df = pd.read_parquet(ledger)
    same_day = df[df["event_date"] == "2026-05-08"]
    assert len(same_day) == 2
    assert set(same_day["basket_id"]) == {"b1", "b2"}


def test_lane_gate_is_the_shared_ledger_lane_definition():
    """One definition of the nightly lane, imported — not a local COLLECT_LANE read."""
    from engine.ledger_lane import nightly_advance_enabled
    assert ge._ledger_advance_enabled is nightly_advance_enabled
    src = pathlib.Path(ge.__file__).read_text()
    assert "COLLECT_LANE" not in src, \
        "group_earnings reads the lane env var directly instead of via ledger_lane"
