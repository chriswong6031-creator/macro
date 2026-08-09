"""CONTINUATION-WATCH cohort for the China Prophet board (shadow accrual, no display).

Program of record: ``research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md``
§2.7 (evidence) and §5 W-C (charter).

THE COHORT THIS EXISTS TO MEASURE
---------------------------------
The era-runner funnel (§2.7, top-150 runners) splits caught 88 (59%) /
eligible_missed 45 (30%) / **never_eligible 17 (11%)**.  That last group is the
one the detector family *structurally cannot admit*: the SHALLOWEST charts
(median drawdown −27% vs −40% for the eligible-missed, trailing-63 −11%),
blocked by the buy-filter's counter-trend / no-200-reclaim leg.  Their median era
return was **+18.7%**.  §2.7's reading is explicit — 11% says CN needs a
CONTINUATION DOOR as a complement, not a rebuild.

You cannot build that door on 17 in-era names.  So this lane opens no door: it
logs, nightly, the names that WOULD be its candidates, under their own board
definition, and lets a forward record accrue until there is something to
adjudicate.  Per house epistemics a display-tier/shadow-tier accrual ships
freely and a null never blocks it.

THE RULE (frozen here; do not tune in the builder)
--------------------------------------------------
A candidate is a scored CN name where ALL of:

  1. the ``signal_gate`` verdict is INELIGIBLE, and its reason names the
     counter-trend / 200-reclaim family — the exact block §2.7 attributes the
     never-eligible cohort to.  The strings come from the ``CT_*`` constants in
     ``engine.signal_quality`` ("counter-trend, no 200-reclaim/hold", "... held
     but no 200-reclaim", "... reclaimed 200 but no next-bar hold"), reaching
     the verdict via ``engine.signal_gate.verdict`` as "buy blocked by
     filter: ...";
  2. close > the 50-session mean — the "already trending" half of a
     continuation shape, which is what separates this cohort from the washout
     cohort ``china_reversal_watch`` already logs;
  3. trailing-63 return > 0 — the shallow-chart / positive-drift half.

Ranked by trailing-63 DESC, capped at 30/night.

WHAT THIS LANE IS NOT
---------------------
Not a buy list, not a shelf, not a surface.  It has no display in the codebase.
This module READS nothing: it returns rows, and the nightly CN builder appends
them to the shared board store owned by ``engine.china_standout_track`` under
``board_definition = "cn_continuation_watch_v1"``, which
``china_standout_track.WATCH_DEFINITIONS`` excludes from headline-grade
resolution, so an append ORDER can never flip ``grade()`` onto it.  §2.12's
standing warning applies to whatever is eventually built on this record: a
member-level door must beat the MEASURED null (naive member fresh-prints after a
theme upgrade, −1.46pp vs −1.06 baseline), not merely show a positive cell.
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

BOARD_DEFINITION = "cn_continuation_watch_v1"
LANE = "continuation_watch"

#: Nightly cap (masterplan §5 W-C plumbing spec).
CAP = 30
#: "Already trending" test window, in sessions.
MA_WINDOW = 50
#: Trailing-return window, in sessions — the §2.7 cohort statistic (trail-63).
TRAIL_WINDOW = 63

#: Substrings that identify the counter-trend / 200-reclaim block family in a
#: gate verdict reason.  Sourced from ``engine.signal_quality``'s ``CT_*``
#: constants — NOT invented here; tests/test_china_continuation_watch.py drives
#: the live filter and asserts every one of them still lands in this tuple.
#:
#: ``signal_quality.HOLD_FAIL`` ("failed next-bar hold") is deliberately absent:
#: it is the block for a name that failed ONLY the next-bar hold — the main
#: branch, plus the reclaim_veto=False counter-trend branch — neither of which
#: tests a reclaim, so neither is the §2.7 block.
#:
#: ``reclaim-and-hold`` is the RETIRED pre-#4583 spelling of that same hold-only
#: block, corrected because it named a reclaim it never evaluated
#: (research/cn_prophet_audit/CN_RECLAIM_HOLD_AUDIT.md §10/§11).  The live engine
#: can no longer emit it, so this entry matches nothing; THE RULE above is
#: frozen, so it is pinned as dead rather than tuned out.
BLOCK_REASON_MARKERS: tuple[str, ...] = (
    "counter-trend", "200-reclaim", "reclaim-and-hold",
)


def is_trend_blocked(verdict: dict | None) -> bool:
    """True iff a ``signal_gate`` verdict is INELIGIBLE for a family reason.

    Eligibility is checked FIRST and independently: ``_buy_filter``'s PASSING
    counter-trend string ("held confirmation (counter-trend)") also contains a
    marker, and admitting an eligible name here would put a live buy-shelf row
    into a watch cohort.
    """
    if not isinstance(verdict, dict):
        return False
    if verdict.get("eligible"):
        return False
    reason = str(verdict.get("reason") or "").lower()
    return any(m in reason for m in BLOCK_REASON_MARKERS)


def measure(daily_close: object) -> dict | None:
    """Continuation geometry for one name, or None when it fails the shape.

    Returns ``{price, ma50, vs_ma50, trail_63}`` (``vs_ma50``/``trail_63`` as
    fractions) only when close > MA50 AND trail-63 > 0.  Windows follow the
    audit's own convention (``research/cn_prophet_audit/v1_loser_audit.py:83,90``
    — ``c0/hist.iloc[-1-n]-1`` and ``c0/hist.iloc[-n:].mean()-1``) so the
    numbers here and in the loser/miss telemetry mean the same thing.  Never
    raises.
    """
    try:
        c = pd.to_numeric(pd.Series(daily_close), errors="coerce").dropna()
        if len(c) <= TRAIL_WINDOW:          # need bar -1-63 to exist
            return None
        price = float(c.iloc[-1])
        ma = float(c.iloc[-MA_WINDOW:].mean())
        base = float(c.iloc[-1 - TRAIL_WINDOW])
        if not (price > 0 and ma > 0 and base > 0):
            return None
        trail = price / base - 1.0
        if price <= ma or trail <= 0:
            return None
        return {"price": round(price, 4), "ma50": round(ma, 4),
                "vs_ma50": round(price / ma - 1.0, 4), "trail_63": round(trail, 4)}
    except Exception as exc:  # noqa: BLE001 — a watch lane never breaks a build
        log.debug("china_continuation_watch: measure failed (%s)", exc)
        return None


def select(rows: list[dict], close_by_ticker: dict, *, cap: int = CAP) -> list[dict]:
    """The night's continuation candidates, ranked trail-63 DESC and capped.

    ``rows`` are scored CN candidate rows (``china_board_rank.enrich_and_score_rows``
    output); ``close_by_ticker`` maps ticker -> daily close series.  Output rows
    carry ``board_definition``/``lane`` so ``china_standout_track.append_board``
    stamps the watch cohort rather than the headline one.  Never raises.
    """
    out: list[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if not is_trend_blocked(r.get("signal")):
            continue
        ticker = str(r.get("ticker") or "")
        if not ticker:
            continue
        c = close_by_ticker.get(ticker)
        if c is None:
            continue
        m = measure(c)
        if not m:
            continue
        out.append({
            "ticker": ticker,
            "name": r.get("name"),
            "sector": r.get("sector"),
            "price": m["price"],
            "lane": LANE,
            "board_definition": BOARD_DEFINITION,
            "continuation": {
                **m,
                "blocked_reason": str((r.get("signal") or {}).get("reason") or ""),
            },
        })
    out.sort(key=lambda x: -float(x["continuation"]["trail_63"]))
    return out[: max(0, int(cap))]
