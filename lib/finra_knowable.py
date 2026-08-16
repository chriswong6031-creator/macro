"""When a FINRA short-interest settlement became KNOWABLE — one definition, two callers.

WHY THIS MODULE EXISTS (2026-08-14). The publication lag used to live as the
literal ``10`` in two places — ``_SI_KNOWABLE_LAG_DAYS`` in
``engine/neuralweb/context_api.py`` and ``KNOWABLE_LAG_DAYS`` in
``scripts/backfill_finra_short_interest.py`` — pinned together by a drift test.
Both carried the same comment calling 10 CALENDAR days "the deliberately
conservative floor". That claim was false three ways, all measured:

  1. Its own cited FINRA schedule example refutes it. The comment reads
     "settlement Jan 15 -> due Jan 20 6pm ET -> published Jan 27". Jan 15 to
     Jan 27 is **12 calendar days** — already two days past the constant that
     the same sentence called conservative.

  2. Against the exchange calendar the constant lands EARLY on every settlement
     the repo actually holds (8 sessions after settlement vs settlement + 10
     calendar days):

         settlement    +10 calendar    8 sessions    early by
         2026-06-30    2026-07-10      2026-07-13    3 days
         2026-07-15    2026-07-25      2026-07-27    2 days
         2026-07-31    2026-08-10      2026-08-12    2 days

     The 3-day gap on the June settlement is the observed Independence Day
     closure (2026-07-03) — exactly the kind of thing calendar arithmetic
     cannot see and session arithmetic cannot miss.

  3. ``data/finra/short_interest_history.parquet`` carries a ``capture_date``
     column — the collector's own run date, one vintage per settlement — and
     the derived +10-calendar date precedes it on every settlement in the
     store: 06-30 captured 07-22, 07-15 captured 08-06, 07-31 captured 08-13.
     On the 07-31 settlement the retired rule declared the row knowable on
     08-10, THREE DAYS BEFORE our collector could have seen it.

An under-waiting derived lag manufactures look-ahead at exactly the publication
boundary — the one place a short-interest study is most likely to be read as
predictive. Eight NYSE sessions dominates the FINRA schedule example in every
year 2015-2026 where Jan 15 is a session (it resolves to Jan 28, one day past
the cited Jan 27 publication), so "conservative" becomes a true claim rather
than the false one the retired comment made.

Having ONE definition imported by both call sites is the point: the two-constant
mirror is deleted, so drift is structurally impossible rather than drift-tested.

CONTRACT. ``knowable_date`` is stdlib-only rule arithmetic over
``lib/nyse_calendar`` (no pandas at import time, no data dependency); it never
raises and degrades to a calendar-day fallback that is chosen to err LATE. The
``knowable_series`` twin exists because the panel store is ~3.87M rows over ~205
unique settlement dates and the render budget is law: session arithmetic is
computed over the UNIQUE settlements and mapped back, never per row.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from lib.nyse_calendar import sessions_between

# Plain messages only — never a '::' prefix through a logger
# (see tests/test_gh_annotation_line_start.py).
log = logging.getLogger(__name__)

#: NYSE sessions after settlement before a FINRA short-interest figure is treated
#: as knowable. FINRA reports positions on the second business day after
#: settlement and disseminates on the following schedule date; 8 sessions clears
#: the cited "Jan 15 -> Jan 27" example in every year it can be evaluated, and
#: clears the collector's own observed capture dates on all three settlements the
#: committed history store holds.
KNOWABLE_LAG_SESSIONS = 8

#: Calendar-day fallback, used ONLY when the session calendar cannot answer.
#: It must be >= the widest 8-session span so the fallback errs LATE, never
#: early: measured over every day 2015-01-01..2035-12-31, the widest span from a
#: date to its 8th following session is exactly 14 calendar days (worst case
#: 2015-12-21, whose 8th session is 2016-01-04 across both Christmas and New
#: Year). ``tests/test_finra_knowable.py`` pins that property.
KNOWABLE_LAG_FALLBACK_DAYS = 14

#: Search horizon for the session scan. 34 calendar days comfortably covers 8
#: sessions plus weekends and the longest holiday stretch (widest observed span
#: is 14 days), while bounding the scan so a calendar surprise cannot spin.
_HORIZON_DAYS = 34


def knowable_date(settlement: date) -> date:
    """The date a settlement's short interest became knowable.

    The ``KNOWABLE_LAG_SESSIONS``-th NYSE session STRICTLY AFTER ``settlement``.
    Falls back to ``settlement + KNOWABLE_LAG_FALLBACK_DAYS`` when the calendar
    cannot answer — the fallback is >= the widest session span, so a degraded
    answer waits longer than the real one rather than shorter.

    Deliberately NOT ``lib.nyse_calendar.session_n_forward``: that helper returns
    None when ``first`` is not itself a session, and a settlement date is not
    guaranteed to be one (FINRA settles on the 15th and month-end, which land on
    weekends and holidays). ``sessions_between(settlement + 1d, ...)`` is
    equivalent when the settlement IS a session and still defined when it is not.

    Never raises (this feeds ``engine/neuralweb/context_api.py``, whose
    CI-runner safety law is that no query path may raise).
    """
    try:
        sess = sessions_between(settlement + timedelta(days=1),
                                settlement + timedelta(days=_HORIZON_DAYS))
        if len(sess) >= KNOWABLE_LAG_SESSIONS:
            return sess[KNOWABLE_LAG_SESSIONS - 1]
        log.debug("finra_knowable: only %d session(s) within %dd of %s — "
                  "using the %dd calendar fallback",
                  len(sess), _HORIZON_DAYS, settlement, KNOWABLE_LAG_FALLBACK_DAYS)
    except Exception as exc:  # noqa: BLE001 — a calendar surprise must not raise here
        log.debug("finra_knowable: session scan failed for %s (%s) — "
                  "using the %dd calendar fallback",
                  settlement, exc, KNOWABLE_LAG_FALLBACK_DAYS)
    return settlement + timedelta(days=KNOWABLE_LAG_FALLBACK_DAYS)


def knowable_series(settlements):
    """Vectorised ``knowable_date`` over a column of settlement dates.

    Returns a datetime64 ``pd.Series`` aligned to the input's index. pandas is
    imported lazily so ``knowable_date`` stays a stdlib-only import for callers
    that only need the scalar.

    COMPUTED OVER ``factorize``'d UNIQUES, never per row. The panel store is
    ~3.87M rows spanning ~205 unique settlement dates, so a per-row session scan
    would be ~19,000x the work for the same answer — and this runs on the render
    path, where the budget is law.

    NaT IN, NaT OUT (fail-closed). An unparseable/absent settlement date maps to
    NaT rather than to some default, so the row stays invisible to the
    ``knowable_date <= date_ts`` gate: an undated settlement must never become
    knowable on a date we cannot justify.
    """
    import numpy as np
    import pandas as pd

    s = settlements if isinstance(settlements, pd.Series) else pd.Series(list(settlements))
    s = pd.to_datetime(s, errors="coerce")
    if len(s):
        s = s.dt.normalize()

    codes, uniques = pd.factorize(s)          # NaT -> code -1, absent from uniques
    mapped = [np.datetime64(knowable_date(pd.Timestamp(u).date()), "ns") for u in uniques]
    # Sentinel at the tail: numpy's negative indexing turns factorize's -1 NaT
    # code into this slot, so the NaT round-trip needs no per-row branch.
    lookup = np.array(mapped + [np.datetime64("NaT", "ns")], dtype="datetime64[ns]")
    return pd.Series(lookup[codes], index=s.index)
