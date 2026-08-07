"""Tests for scripts/heal_cn_beijing_tickers.heal_file — the Beijing re-key repair.

The mapper fix (#4590) stops NEW corruption; this script re-keys rows already written.
It has had to run twice: the first heal merged at 02:15 on 2026-08-05 and the nightly
asia collect lane, already checked out from the pre-heal tree, committed at 02:27 and
reverted it on china_lhb/detail.parquet + events.parquet. By the time anyone looked, the
08-06/08-07 collections had appended CORRECT ``.BJ`` rows on top, so the stores held both
keys at once — and the script's original blanket "ABORT if any .BJ row exists" guard made
it refuse to run at exactly the moment it was needed.

What is pinned here is the narrow widening that unblocks it. A `.BJ` row is only a
problem when a healed key actually LANDS on one, and such a row is dropped rather than
relabelled ONLY under four checkable preconditions. Each precondition gets a test that
fails if it is removed — the abort cases are the teeth.

Pure/offline: every case builds its own parquet under tmp_path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.heal_cn_beijing_tickers as heal  # noqa: E402

REL = "store.parquet"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Write a frame to tmp_path/store.parquet and point the script's ROOT at it."""
    monkeypatch.setattr(heal, "ROOT", tmp_path)

    def _write(rows):
        df = pd.DataFrame(rows)
        df.to_parquet(tmp_path / REL, index=False)
        return tmp_path / REL

    return _write


def _read(path):
    return pd.read_parquet(path)


# --- the plain label-only path (unchanged behaviour) -------------------------------- #
def test_relabels_and_keeps_every_row_when_no_bj_rows_exist(store):
    p = store([
        {"date": "2026-08-01", "ticker": "920002.SS", "v": 1},
        {"date": "2026-08-01", "ticker": "920003.SZ", "v": 2},
        {"date": "2026-08-01", "ticker": "600000.SS", "v": 3},
        {"date": "2026-08-01", "ticker": "900001.SS", "v": 4},
    ])
    n, note = heal.heal_file(REL, None, "date", write=True)
    out = _read(p)
    assert n == 2, note
    assert len(out) == 4, "a label rewrite must not move the row count"
    assert list(out["ticker"]) == ["920002.BJ", "920003.BJ", "600000.SS", "900001.SS"]


def test_shanghai_b_shares_are_never_touched(store):
    """900xxx.SS is a real Shanghai B-share. The regex must not reach it."""
    store([{"date": "d", "ticker": t, "v": 0}
           for t in ("900001.SS", "900932.SS", "900957.SS", "920045.SS")])
    heal.heal_file(REL, None, "date", write=True)
    got = list(_read(heal.ROOT / REL)["ticker"])
    assert got == ["900001.SS", "900932.SS", "900957.SS", "920045.BJ"]


def test_second_run_is_a_no_op(store):
    p = store([{"date": "2026-08-01", "ticker": "920002.SS", "v": 1}])
    heal.heal_file(REL, None, "date", write=True)
    first = _read(p)
    n, note = heal.heal_file(REL, None, "date", write=True)
    assert (n, note) == (0, "clean")
    assert _read(p).equals(first)


# --- the widening: `.BJ` rows present, but no key collision ------------------------- #
def test_bj_rows_present_without_a_collision_still_heal(store):
    """THE REGRESSION. china_lhb/detail.parquet looked exactly like this — 510 stale rows
    plus 28 correct `.BJ` rows on later dates, no overlapping key. The old guard aborted
    on the mere presence of the `.BJ` rows and left the store dirty."""
    p = store([
        {"date": "2026-08-01", "ticker": "920002.SS", "v": 1},   # stale, no twin
        {"date": "2026-08-06", "ticker": "920777.BJ", "v": 2},   # correct, different key
    ])
    n, note = heal.heal_file(REL, None, "date", write=True)
    out = _read(p)
    assert n == 1, note
    assert len(out) == 2, "no twin exists, so nothing may be dropped"
    assert set(out["ticker"]) == {"920002.BJ", "920777.BJ"}


# --- the widening: a genuine stale/live twin --------------------------------------- #
def test_stale_twin_is_dropped_and_the_live_row_survives(store):
    """china_lhb/events.parquet held 28 of these: one (date, company) recorded under both
    the dead key and the live one. Relabelling alone would mint a duplicate."""
    p = store([
        {"date": "2026-07-31", "ticker": "920117.SS", "v": "stale"},
        {"date": "2026-07-31", "ticker": "920117.BJ", "v": "live"},
        {"date": "2026-07-31", "ticker": "600000.SS", "v": "other"},
    ])
    n, note = heal.heal_file(REL, None, "date", write=True)
    out = _read(p)
    assert n == 1, note
    assert len(out) == 2, "the twin pair must collapse to one row"
    assert list(out["v"]) == ["live", "other"], "keep-LAST: the newer .BJ row wins"
    assert not out.duplicated(subset=["date", "ticker"]).any()


def test_dropping_a_twin_never_loses_a_beijing_name_day(store):
    """The row goes; the (date, company) observation does not."""
    p = store([
        {"date": "2026-07-31", "ticker": "920117.SS", "v": 1},
        {"date": "2026-07-31", "ticker": "920117.BJ", "v": 2},
        {"date": "2026-08-01", "ticker": "920117.SS", "v": 3},   # no twin on this date
    ])
    heal.heal_file(REL, None, "date", write=True)
    out = _read(p)
    assert set(zip(out["date"], out["ticker"])) == {
        ("2026-07-31", "920117.BJ"), ("2026-08-01", "920117.BJ")}


# --- the teeth: every precondition aborts, and aborts leave the file UNTOUCHED ------ #
# Each case asserts the SPECIFIC reason, not merely that some abort happened. Asserting
# only "it aborted" made these vacuous: deleting a precondition still aborted, because a
# later post-write invariant caught the same frame and produced a different ABORT. The
# reason string is what ties a test to the guard it is supposed to pin.
def _assert_untouched(p, before, n, note, because):
    assert n == 0, f"expected an abort, got {note}"
    assert note.startswith("ABORT"), note
    assert because in note, f"aborted for the WRONG reason — wanted {because!r}, got {note!r}"
    assert _read(p).equals(before), "an aborted heal must not write the file"


def test_collision_without_a_declared_key_aborts(store):
    """No key column means no way to tell a twin from a real second row. Refuse."""
    p = store([
        {"date": "2026-07-31", "ticker": "920117.SS", "v": 1},
        {"date": "2026-07-31", "ticker": "920117.BJ", "v": 2},
    ])
    before = _read(p)
    _assert_untouched(p, before, *heal.heal_file(REL, None, None, write=True),
                      because="declares no unique PIT key")


def test_collision_in_a_store_whose_key_is_already_non_unique_aborts(store):
    """china_preannounce keys by 预测指标, china_buyback by plan, china_lhb/history by
    (date, ticker, reason). Collapsing on (date, ticker) there destroys real rows."""
    p = store([
        {"date": "2026-07-31", "ticker": "920117.SS", "v": 1},
        {"date": "2026-07-31", "ticker": "920117.BJ", "v": 2},
        {"date": "2026-08-01", "ticker": "600000.SS", "v": 3},
        {"date": "2026-08-01", "ticker": "600000.SS", "v": 4},   # legitimate duplicate
    ])
    before = _read(p)
    _assert_untouched(p, before, *heal.heal_file(REL, None, "date", write=True),
                      because="is already non-unique")


def test_stale_row_ordered_after_its_live_twin_aborts(store):
    """The drop is only defensible because it reproduces _drip.append_snapshot's
    keep-LAST. If the stale row is the LAST one, keep-last would have kept IT, and the
    two rules disagree — so the script must not guess."""
    p = store([
        {"date": "2026-07-31", "ticker": "920117.BJ", "v": "live"},
        {"date": "2026-07-31", "ticker": "920117.SS", "v": "stale"},   # stale comes last
    ])
    before = _read(p)
    _assert_untouched(p, before, *heal.heal_file(REL, None, "date", write=True),
                      because="does not precede its .BJ twin")


def test_raw_code_cross_check_aborts_on_disagreement(store):
    """Where the store retains the Eastmoney code, a rewrite that disagrees with it is a
    guess, not a heal."""
    p = store([{"date": "d", "ticker": "920002.SS", "股票代码": "600519", "v": 1}])
    before = _read(p)
    _assert_untouched(p, before, *heal.heal_file(REL, "股票代码", "date", write=True),
                      because="disagree with 股票代码")


# --- --check never writes ---------------------------------------------------------- #
def test_check_mode_reports_without_writing(store):
    p = store([
        {"date": "2026-07-31", "ticker": "920117.SS", "v": 1},
        {"date": "2026-07-31", "ticker": "920117.BJ", "v": 2},
    ])
    before = _read(p)
    n, note = heal.heal_file(REL, None, "date", write=False)
    assert n == 1 and "would rewrite" in note and "twin" in note, note
    assert _read(p).equals(before)


# --- the store table itself --------------------------------------------------------- #
def test_every_store_entry_is_a_triple():
    """The key column was added as a third field; a stale 2-tuple would unpack-crash in
    main() rather than here."""
    for entry in heal.STORES:
        assert len(entry) == 3, entry


@pytest.mark.parametrize("rel", [
    "data/china_lhb/history.parquet",     # keyed (date, ticker, reason)
    "data/china_preannounce/forecast.parquet",
    "data/china_buyback/buyback.parquet",
    "data/china_analyst/forecast.parquet",
    "data/china_unlocks/detail.parquet",
])
def test_stores_with_non_unique_date_ticker_pairs_declare_no_key(rel):
    """These carry several legitimate rows per (date, ticker). Declaring a key for one
    would arm the drop path against real data."""
    keys = {r: k for r, _, k in heal.STORES}
    assert keys[rel] is None, f"{rel} must not declare a unique PIT key"
