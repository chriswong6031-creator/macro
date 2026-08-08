"""The T2 event latch: a fired confluence event may never be un-fired.

Pins the 300363.SZ defect — #1 on the 2026-08-05 CN Prophet board, absent from all seven lanes
on 08-06, +20.02% (ChiNext limit) on 08-07 — and the invariance property the session-anchor
suites do NOT cover: bucket-COMPLETION invariance.  #4732/#4799 made the grid invariant to
loaded history DEPTH; the trailing bucket is still incomplete and its known-date still advances,
so a bar that already printed can lose its annotation.

Tests are fixture-driven (a synthetic close series + a tmp_path store), never live data — a
replay over data/china_stocks would assert about whatever today's tape happens to be.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import confluence_latch, confluence_tiers


def _series(n=40, start="2026-06-01"):
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(np.linspace(10.0, 12.0, n), index=idx)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(confluence_latch.config, "data_dir", lambda: tmp_path)
    return tmp_path


def test_absent_store_is_a_noop(store):
    """Forward-only from store birth: with nothing latched, stabilize returns input unchanged."""
    latch = confluence_latch.EventLatch("CN").load()
    s = _series()
    fired = pd.Series([False] * (len(s) - 1) + [True], index=s.index)
    out = latch.stabilize("300363.SZ", fired)
    pd.testing.assert_series_equal(out, fired)


def test_a_fired_bar_survives_a_later_run_that_no_longer_computes_it(store):
    """THE DEFECT.  Run 1 sees the event on its last bar and records it.  Run 2 holds one more
    bar and — because the trailing bucket's known-date advanced — no longer computes that event
    anywhere.  The latch must restore it."""
    s = _series(41)
    run1 = s.iloc[:40]
    w = confluence_latch.EventLatch("CN", record=True).load()
    fired1 = pd.Series([False] * 39 + [True], index=run1.index)   # event on 2026-07-24 (last bar)
    w.stabilize("300363.SZ", fired1)
    assert w.flush() == 1

    # run 2: the same bar now computes False — the erasure — and today's bar is False too
    r = confluence_latch.EventLatch("CN").load()
    fired2 = pd.Series([False] * 41, index=s.index)
    out = r.stabilize("300363.SZ", fired2)

    erased_bar = run1.index[-1]
    assert bool(out.loc[erased_bar]) is True, "latched event was un-fired by a later run"
    assert int(out.sum()) == 1


def test_last_bar_is_always_the_computed_verdict(store):
    """Today's bar is today's verdict — the latch never overrides the as-of bar, or a name could
    never leave the board at all."""
    s = _series(40)
    w = confluence_latch.EventLatch("CN", record=True).load()
    w.stabilize("X.SZ", pd.Series([False] * 39 + [True], index=s.index))
    w.flush()

    # same series, same last bar, but it now computes False -> must stay False
    r = confluence_latch.EventLatch("CN").load()
    out = r.stabilize("X.SZ", pd.Series([False] * 40, index=s.index))
    assert bool(out.iloc[-1]) is False


def test_keep_first_never_revises_a_recorded_bar(store):
    """PIT: the first observation of a bar as the as-of bar wins, matching the published board."""
    s = _series(40)
    w1 = confluence_latch.EventLatch("CN", record=True).load()
    w1.stabilize("X.SZ", pd.Series([False] * 39 + [True], index=s.index))
    w1.flush()
    w2 = confluence_latch.EventLatch("CN", record=True).load()
    w2.stabilize("X.SZ", pd.Series([False] * 40, index=s.index))     # tries to write False
    w2.flush()

    df = pd.read_parquet(confluence_latch._path("CN"))
    row = df[(df.ticker == "X.SZ") & (df.date == str(s.index[-1].date()))]
    assert len(row) == 1
    assert bool(row.fired.iloc[0]) is True, "keep-first was violated"


def test_latch_is_per_ticker(store):
    s = _series(40)
    w = confluence_latch.EventLatch("CN", record=True).load()
    w.stabilize("A.SZ", pd.Series([False] * 39 + [True], index=s.index))
    w.flush()
    r = confluence_latch.EventLatch("CN").load()
    out = r.stabilize("B.SZ", pd.Series([False] * 40, index=s.index))
    assert int(out.sum()) == 0, "A's latched event leaked into B"


def test_cascade_default_is_byte_identical(store):
    """The whole fleet (US/HK/CA and every other caller) must be untouched by this module."""
    s = _series(220)
    base = confluence_tiers.cascade(s, market="CN")
    with_none = confluence_tiers.cascade(s, market="CN", event_latch=None, latch_key="X.SZ")
    assert base == with_none


def test_unreadable_store_degrades_to_empty_not_an_exception(store):
    (store / "confluence_latch").mkdir(parents=True, exist_ok=True)
    (store / "confluence_latch" / "cn_t2.parquet").write_bytes(b"not a parquet")
    latch = confluence_latch.EventLatch("CN").load()          # must not raise
    s = _series(30)
    fired = pd.Series([False] * 29 + [True], index=s.index)
    pd.testing.assert_series_equal(latch.stabilize("X.SZ", fired), fired)
