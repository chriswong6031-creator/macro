"""tests/test_backfill_ticker_reuse_floor.py — ROOT_HISTORY_FLOOR.

OPRA reissues a symbol once its previous holder delists, and ThetaData serves
both eras under the one root. SPCX lists expirations continuously from 2021, but
everything before 2026-06-12 belongs to a SPAC ETF that delisted in 2026-04 —
not to Space Exploration Technologies. Backfilling from DEFAULT_START would have
merged two unrelated companies' option chains into a single file that then reads
as one continuous position history.

This is the options-side twin of the OHLC contamination already guarded on the
terminal's ingest lane (drop_stale_ticker_history / TICKER_REUSE_DATES).

Pinned here:
  - the floor exists for SPCX and sits on the relisting date;
  - year-chunking from the floor never emits a pre-floor slice;
  - unfloored roots are completely unaffected.
"""
from __future__ import annotations

from datetime import date

from scripts.backfill_thetadata_eod import (
    DEFAULT_START,
    ROOT_HISTORY_FLOOR,
    _year_chunks,
)


def _default_start_date() -> date:
    return date(int(DEFAULT_START[:4]), int(DEFAULT_START[4:6]),
                int(DEFAULT_START[6:8]))


def test_spcx_is_floored_at_its_relisting_date():
    assert ROOT_HISTORY_FLOOR["SPCX"] == date(2026, 6, 12)


def test_floor_is_later_than_the_default_start_or_it_would_do_nothing():
    assert ROOT_HISTORY_FLOOR["SPCX"] > _default_start_date()


def test_chunks_from_the_floor_never_reach_the_previous_holders_era():
    """The SPAC ETF traded under SPCX until 2026-04 — no chunk may touch it."""
    start = max(_default_start_date(), ROOT_HISTORY_FLOOR["SPCX"])
    chunks = _year_chunks(start, date(2026, 8, 6))
    assert chunks, "a floored root must still have work to do"
    assert min(cs for cs, _ in chunks) == date(2026, 6, 12)
    assert all(cs >= date(2026, 6, 12) for cs, _ in chunks)
    assert all(cs.year >= 2026 for cs, _ in chunks)


def test_an_unfloored_root_keeps_the_full_default_history():
    """The floor is opt-in per root; everything else is untouched."""
    assert "SPY" not in ROOT_HISTORY_FLOOR
    start = max(_default_start_date(), ROOT_HISTORY_FLOOR.get("SPY",
                                                             _default_start_date()))
    assert start == _default_start_date()
    chunks = _year_chunks(start, date(2026, 8, 6))
    assert min(cs for cs, _ in chunks) == _default_start_date()


def test_a_floor_after_the_end_date_yields_no_work_rather_than_a_bad_slice():
    start = max(_default_start_date(), ROOT_HISTORY_FLOOR["SPCX"])
    assert _year_chunks(start, date(2026, 1, 1)) == []
