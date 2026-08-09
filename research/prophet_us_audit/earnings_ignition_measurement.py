"""EARNINGS IGNITION — does a fresh buy-confluence just before a report predict the reaction?

RESEARCH TIER. This file MEASURES. It changes no gate, no rank, no size, no lane, no
surface and no config. Nothing here is a promotion and no cell below licenses one.
ANTICIPATION program §6.8(e), `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md`.

THE QUESTION (operator, 2026-08-08; receipts AMZN 2026-07-31, MSFT 2026-07-29, DLB 2026-07-23)
    A fresh buy-confluence appearing within a few sessions BEFORE an earnings report may
    mark anticipatory positioning flow and predict a positive reaction. We measure the
    FOOTPRINT and nothing else — the construction is mechanism-agnostic and no wording
    here or downstream may claim knowledge of anyone's information. Three contrasts:
      A  fresh buy/rebuy confluence knowable in [T-5, T-1] sessions before report date T
      B  same-quality confluence with NO report within +/-10 sessions   (entry control)
      C  report date with NO pre-report confluence                       (base rate)
    The ADVERSE TAIL inside A is the load-bearing cell: does a confluence ever precede a
    negative reaction? A quarter with broad beats confounds this and the split is printed.

KILLS CHECK (matched by RULE TEXT, cited by stable key -- never by row number)
  * `DNR:KILL-CALENDAR-GATED-RISK` -- the closest row, and it binds the FUTURE of this
    work, not this file. It forbids calendar/event-window-gated RISK-RADAR `_SCARES` legs
    at ANY tier, because a Tier-B leg advances state and state sets gross: a laundered
    pre-event conviction dampener. This instrument advances no state, sets no gross,
    touches no risk channel, and emits no leg -- it reads published artifacts and writes
    two research receipts. The row is cited here so the record is unambiguous: any later
    attempt to turn these cells into an event-window-gated risk or sizing channel is
    that row's forbidden construction and needs its own adjudication, not this receipt.
  * `DNR:KILL-OFFHORIZON-VERDICTS` -- verdicts only at registered rungs. Forward cells are
    H=5 and H=10, both on `scripts/grade_us_board.HORIZONS = [5, 10, 21, 63]`. The day-0
    reaction is an event-study REACTION, not a horizon verdict, and is labelled as such.
  * `DNR:KILL-OUTCOME-AUDITION` -- no per-name tool selection by outcome. Every cohort here
    is defined by labels fixed BEFORE the outcome is observable (a marker the engine
    already stamped, and a report date from a filing store). No per-name gate, rank, size
    or tool is chosen from any outcome in this file.
  * `DNR:KILL-PROPHET-POP-MERGE` -- the graded-board population is untouched; this reads
    `site/signals/*.json` and writes nothing any board or ledger consumes.
  * `HOLD-IGNITION-SURFACES` -- NAME COLLISION, DIFFERENT CONSTRUCTION. That row suspends
    the sector/theme Ignition Radar's USER-FACING surfaces (`engine/ignition_radar.py`,
    the us_stocks strip, the Upturn hero). This study builds no surface at all and shares
    no code, no input and no output with it. The shared word is "ignition"; nothing else.

v0.1 AMENDMENT (2026-08-09) -- WHAT AN ADVERSARIAL RE-READ CHANGED
    v0 (2026-08-08) reproduces exactly on re-run, but the audit found real defects in the
    INSTRUMENT. They are corrected here and every headline they moved is named in the
    receipt's before/after table. The data vintage is deliberately UNCHANGED (same signals,
    same price and earnings stores, same hardcoded 2026-08-08 cutoff), so every delta below
    is attributable to the code and not to drift:
      F1  the derived announcement window governed `reaction_pct` but was DROPPED for the
          forward excess -- after-close reports were anchored at close(T), BEFORE the print,
          so H=5/H=10 excess swallowed the reaction jump for ~39% of the report-anchored
          rows. Forward excess is now anchored at the reaction session, like the reaction.
      F2  cohort B (the entry control) was partly manufactured by earnings-store COVERAGE
          HOLES: "no report within +/-10 sessions" is indistinguishable from "we hold no
          report for this name-year". A coverage floor now applies; the unfloored v0
          construction is emitted beside it so the old cell stays inspectable.
      F3  no dispersion was printed, so a null could not be told from an underpowered cell.
          Every headline now carries SE + a 95% interval, and the pairwise contrasts carry
          a difference interval, a t, and a minimum detectable effect.
      F4  EDGAR ALREADY rolls `filing_date` past a post-close acceptance; v0 rolled a
          SECOND time, putting the reaction one session late on 794 of 16,720 rows.
      F5/F7/F8/F11/F12  fixed-offset ET honesty, a "nearest report" loop that took the
          LATEST, a no-op TZ line, same-session confluences silently seated in the base
          rate, and the self-restricted universe -- all corrected or disclosed.
    The kill verdict is re-stated on the corrected instrument, not inherited from v0.

FRAME REALITY vs THE COMMISSIONING BRIEF (census-first; the delta IS the headline)
  * KNOWABILITY IS DERIVED, and as of the v0.1 amendment that is a CHOICE, not a
    constraint. At the 2026-08-08 vintage this run reads, markers carried no `signal_date`
    field, so the brief's expectation could not be met (v0 attributed it to unmerged
    PR #4987; that PR was CLOSED unmerged -- the field actually landed on main in #5071,
    which re-rendered `site/signals/*.json` with `signal_date` on 56,181 of 56,293
    markers). This run holds the 2026-08-08 artifacts so the v0-vs-v0.1 delta stays
    instrument-only, and therefore still DERIVES knowability: a marker's `date` is its 3D
    bucket's OPEN label (`engine/signal_quality` docstring: "labelled by the bucket's OPEN
    date"), so the earliest an actor could act on it is the bucket's LAST session. Every
    cohort test uses that derived date, never the open label.
    THE FOLLOW-UP IS CLOSED, NOT OPEN: the audit diffed derived against stamped knowability
    on the post-#5071 render and they agree on 26,763 of 26,788 comparable markers
    (99.91%); every disagreement is pre-1995, outside this study's 2014+ window. The
    derivation was NOT load-bearing, so re-running on stamped dates is no longer a decisive
    follow-up -- it has been done and it changed nothing.
  * There is no single earnings-date store. The deep history is `data/edgar/
    earnings_8k_dates.parquet` (SEC 8-K Item 2.02, 2004-08-24..2026-07-02) and it STOPS
    2026-07-02 -- before all three operator receipts. The recent window is bridged by
    `data/earnings/earnings.parquet` `next_date`. v0 said those rows "were never refreshed
    after 2026-06-19"; measured, that is true of 152 of the 212 in-universe bridge rows --
    60 carry a later `as_of` (2026-07-28..2026-08-07). The histogram is emitted, not
    summarised. The two sources are heterogeneous and every cell prints its source mix.
  * DLB and SPCX -- two of the four requested case receipts -- are NOT in the 240-name
    signals universe at all, so no marker for them can exist. Printed as absent, not
    silently dropped.
  * PRICE history bounds the window (`data/baskets/ohlcv` starts 2014-01-02 for most
    names) FOR THE 204 NAMES THE 8-K STORE CARRIES. v0 generalised that to "the binding
    constraint, tighter than earnings coverage" -- FALSE for the other 36 of 240 names,
    which hold ZERO 8-K Item 2.02 rows across the whole span (COST, GOOG, IBM, LLY, V,
    XOM and 30 more). For those, earnings coverage is the binding constraint and it binds
    at zero. That is the hole F2's cohort-B floor exists to keep out of the control.
  * THE UNIVERSE IS SELF-RESTRICTED, not data-limited. 240 names is the published
    `site/signals/*.json` inventory; the price store this same instrument reads carries
    2,768 US tickers (sibling study `ignition_standins.py` runs on all of them). The
    thinness of every per-quarter cell below is therefore partly a choice of frame, and a
    later run on the full price universe is a cheap and honest widening -- of the
    UNIVERSE, which is not an outcome-selected quantity. Widening the LEAD WINDOW after
    seeing which receipts fall outside it is the forbidden move, and is still not done.

ANNOUNCEMENT-WINDOW CONVENTION (the reaction day is derived, never assumed)
    A close-to-close "day 0" is wrong for roughly half of all reports, so the reaction
    session is derived per row: EDGAR rows use `acceptance_datetime` (UTC -> ET); bridge
    rows use `next_time` (time-pre-market / time-after-hours). Accepted before the open ->
    the report is in session T. Accepted after the close -> the reaction is session T+1.
    Intraday -> session T. Unknown -> the row is flagged `window_unknown` and every
    headline is reprinted excluding those rows, so the convention's effect stays visible.
    THE WINDOW GOVERNS THE FORWARD CELLS TOO (F1, v0.1). v0 derived the reaction session
    and then threw it away for the H=5/H=10 excess, anchoring those at close(filing_date)
    -- for an after-close print, that is the close BEFORE the market has read the report,
    so the forward excess contained the reaction jump itself. Both are now anchored on the
    reaction session, so the forward cells measure what happens AFTER the report is priced.
    EDGAR HAS ALREADY ROLLED (F4, v0.1). SEC stamps `filing_date` on the next business day
    when acceptance lands after its cutoff, so a post-close acceptance normally arrives
    already dated to the session that first reads it. v0 rolled again on top. The tell is
    exact and needs no heuristic -- acceptance's ET CALENDAR DATE differs from
    `filing_date` -- and it fires on 796 of 16,720 in-universe rows, all in the same
    direction (acceptance strictly earlier; zero rows run the other way).
    THE ET OFFSET IS FIXED AT -4 AND THAT IS WRONG IN WINTER. v0's docstring claimed the
    EDT/EST boundary "never [crosses] the 09:30/16:00 edges"; measured, it does. After the
    EDGAR-roll correction, 48 of 16,720 rows (0.29%) land on the wrong side of the 16:00
    edge under the fixed offset and so carry the wrong reaction session; 473 more move
    only between `pre_open` and `intraday`, which are the same session T and change
    nothing. Both counts are emitted rather than asserted away.

STATS GUARDS (binding on every cell)
    n printed on every cell; cells with n < 20 carry `thin: true` and are never used as a
    verdict; per-name-first printed beside pooled so one busy name cannot carry a cohort;
    medians printed beside means so no verdict hangs on a threshold; half-split (by date)
    on every headline; NO pooled top-line that averages cohorts against each other -- the
    contrasts are stated pairwise (A vs C event-anchored, A vs B entry-anchored) and the
    anchors are never mixed; nulls printed as nulls, never as zeros.
    DISPERSION IS NOT OPTIONAL (F3, v0.1). v0 printed point estimates only, which cannot
    distinguish "no effect" from "not enough data to see one" -- the exact ambiguity a null
    receipt must not leave open. Every cell now carries `se` and `ci95` on its mean and a
    Wilson `ci95` on its win rate, and every pairwise contrast carries the difference, the
    SE of the difference, a t, a 95% interval on the difference, and `mde_80pct` -- the
    smallest true effect this n could have detected 80% of the time. A null is only worth
    reading beside its MDE.
    NO PREREGISTRATION, NO MULTIPLICITY CORRECTION (F10, v0.1). This instrument was written
    after the operator's question, not before, and it prints many cells without controlling
    the family-wise error rate. That is house-legal at RESEARCH tier and it is the reason
    nothing here may be promoted: sibling preregs in this same directory
    (`FRESH_TICKS_EXTENSION_PREREG.md`, `INTAKE_FILTER_PREREG.md`) are what promotion
    looks like. The direction of the finding makes this cheap -- an uncorrected search that
    returns a NULL is not made more null by correction -- but any future claim that a cell
    here is POSITIVE needs its own prereg with the window and the cell fixed in advance.

DEFINITIONS (stated, not implied)
    fresh confluence := a `buy` or `rebuy` marker in `site/signals/<T>.json`. These are
        transition events, so every marker IS a fresh appearance by construction.
        `quality` is stamped by the engine's buy-filter (`engine/signal_quality.py:604`:
        take = passed, block = vetoed, pending = undecidable) and is present on buy/rebuy
        markers only. The PRIMARY cohort is ALL buy/rebuy markers, because the operator's
        own motivating receipt (AMZN 2026-07-31) is a `block` -- restricting to `take`
        would delete the case that generated the hypothesis. Every cell is ALSO split by
        quality so the difference is visible rather than assumed away.
    reaction  := close(reaction_session) / close(prior session) - 1, in percent.
    excess    := name total return minus SPY total return over the same session span, in
        percentage points, at H=5 and H=10 sessions.
    loser     := excess <= -3pp  (STATED; excess <= 0 is ALSO printed, for parity with the
        masterplan §6.6 first run, so neither threshold hides behind the other).
    win       := excess > 0.
    Survivorship: a name whose price series ends before a horizon is NOT dropped -- it is
        liquidated at its last print, kept in the cell, and counted in `n_truncated`.

A7 COMPLIANCE: this instrument is purely mechanical. It makes no LLM call of any kind and
imports no model client. Every number below is arithmetic over committed artifacts.

RUN: python3 research/prophet_us_audit/earnings_ignition_measurement.py
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# NOTE (F8, v0.1): v0 called `os.environ.setdefault("TZ", "UTC")` here with a comment
# claiming it pinned the date logic. It did not, and could not: CPython caches the zone at
# import, and nothing in this file reads local time anyway -- every timestamp is either an
# explicitly-UTC `datetime.now(timezone.utc)`, an aware ISO string converted with an
# explicit offset, or a naive `pd.Timestamp` compared only against other naive timestamps.
# The line was a no-op that read as a guarantee, so it is gone. This instrument is
# TZ-independent by construction, which is a stronger property than the line pretended to
# give it, and `TZ=UTC` on the run line is therefore unnecessary (harmless, but unnecessary).

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from engine import session_anchor  # noqa: E402  the ONE absolute session calendar

SIGNALS_DIR = REPO / "site" / "signals"
OHLCV_DIR = REPO / "data" / "baskets" / "ohlcv"
YAHOO_DIR = REPO / "data" / "yahoo"
EDGAR_8K = REPO / "data" / "edgar" / "earnings_8k_dates.parquet"
EARNINGS_NEXT = REPO / "data" / "earnings" / "earnings.parquet"
OUT_JSON = Path(__file__).resolve().parent / "EARNINGS_IGNITION_MEASUREMENT_2026-08-08.json"

BUCKET_N = 3          # the 3D grid the markers are drawn on
PRE_WINDOW = 5        # cohort A: knowable in [T-5, T-1] sessions
CONTROL_GAP = 10      # cohort B: no report within +/- 10 sessions
HORIZONS = (5, 10)    # registered rungs (grade_us_board.HORIZONS)
LOSER_PP = -3.0       # STATED loser threshold, in percentage points of excess
THIN_N = 20
CASE_RECEIPTS = ("AMZN", "MSFT", "DLB", "SPCX")
Z95 = 1.959964        # two-sided 95%
Z80_POWER = 0.8416    # one-sided 80% power, for the minimum detectable effect

# The measurement window is PINNED, not "today". v0.1 re-reads the SAME window v0 did with
# a corrected instrument -- extending it would confound the instrument delta with new data.
TODAY_CUTOFF = "2026-08-08"


# --------------------------------------------------------------------------- loaders

def load_sessions() -> tuple[pd.DatetimeIndex, dict]:
    ref = session_anchor.reference_sessions("US")
    return ref, {d: i for i, d in enumerate(ref)}


def load_prices(ticker: str) -> pd.Series | None:
    """Close series. baskets/ohlcv primary (deep), yahoo fallback (shallow but wide)."""
    for path, col in ((OHLCV_DIR / f"{ticker}.parquet", "close"),
                      (YAHOO_DIR / f"{ticker}.parquet", "close")):
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception:
            continue
        if col not in df.columns:
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
        return s[~s.index.duplicated(keep="last")].sort_index()
    return None


def load_markers() -> dict[str, list[dict]]:
    """buy/rebuy markers per ticker, from the published signal artifacts."""
    out: dict[str, list[dict]] = {}
    for path in sorted(SIGNALS_DIR.glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except Exception:
            continue
        rows = [
            # `signal_date` is carried but NOT used: knowability stays derived so the
            # v0-vs-v0.1 delta is instrument-only (see definitions.knowability). It is
            # read here purely so `base.signals_markers_with_signal_date` measures the
            # vintage instead of asserting it.
            {"date": m["date"], "type": m["type"], "quality": m.get("quality"),
             "signal_date": m.get("signal_date")}
            for m in doc.get("markers", [])
            if m.get("type") in ("buy", "rebuy") and m.get("date")
        ]
        out[path.stem] = rows
    return out


ET_OFFSET_HOURS = -4  # fixed EDT; see _et_datetime for the disclosed winter error


def _et_datetime(iso_utc: str | None) -> datetime | None:
    """UTC ISO -> a naive ET wall-clock datetime at a FIXED -4 (EDT) offset.

    THE OFFSET IS WRONG IN WINTER AND THE COST IS MEASURED, NOT ASSUMED AWAY (F5, v0.1).
    v0's docstring claimed the EST/EDT boundary "never [crosses] the 09:30/16:00 edges
    for the after-hours and pre-market clusters this is used to separate". That was a
    guarantee the code could not make, and it is false. Against true `America/New_York`
    on this base, and AFTER the EDGAR-roll correction in `classify_window`, 48 of 16,720
    in-universe 8-K rows (0.29%) fall on the wrong side of the 16:00 edge and therefore
    carry the wrong reaction session; 473 more move between `pre_open` and `intraday`,
    which resolve to the SAME session T and change no cell. Both counts are recomputed on
    every run and emitted at `coverage.announcement_window`, so the error can never drift
    silently behind a prose claim again. Fixing the offset outright is a one-line change
    and a deliberate non-goal of this amendment: it would move 48 rows' reaction session
    at the same time as F1/F4 move thousands, and the v0-vs-v0.1 attribution is worth
    more here than the last 0.29%.

    Returns the wall-clock datetime, so callers can read BOTH its hour and its CALENDAR
    DATE. v0 returned an hour only, which is why it could not see the F4 double-roll: a
    UTC timestamp before 04:00 is a PREVIOUS-DAY ET evening acceptance, and as an hour
    alone that arrives as a negative number (e.g. 01:00Z -> -3.0) which v0's `hour < 9.5`
    branch silently read as "pre-open", losing the day.
    """
    if not iso_utc:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_utc).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(hours=ET_OFFSET_HOURS)


def _et_hour(iso_utc: str | None) -> float | None:
    """ET hour-of-day in [0, 24). See `_et_datetime` for the disclosed winter error.

    Unlike v0 this NEVER returns a negative hour: the previous-ET-day case is carried by
    the datetime's calendar date, not smuggled into the hour as a negative number.
    """
    dt = _et_datetime(iso_utc)
    return None if dt is None else dt.hour + dt.minute / 60.0


def classify_window(acceptance_iso: str | None, filing_date: str) -> str:
    """Announcement window for one EDGAR row: pre_open | intraday | after_close | unknown.

    EDGAR HAS ALREADY ROLLED (F4, v0.1). SEC stamps `filing_date` on the next business day
    when acceptance lands after its cutoff, so a post-close acceptance normally arrives
    ALREADY dated to the session that first reads it. v0 classified purely on the hour and
    so rolled a second time -- `after_close` on a filing_date that was itself the roll --
    putting the reaction one session late on 794 of 16,720 in-universe rows (4.75%).
    The tell needs no heuristic: acceptance's ET CALENDAR DATE differs from `filing_date`.
    Measured on this base that fires on 796 rows, every one of them with acceptance
    STRICTLY EARLIER than filing_date and none the other way, so the roll is one-directional
    and the rule cannot invert a correctly-stamped row.
    """
    dt = _et_datetime(acceptance_iso)
    if dt is None:
        return "unknown"
    if dt.date().isoformat() != str(filing_date)[:10]:
        # EDGAR already advanced filing_date past this acceptance: the market reads the
        # print at filing_date's OPEN, so the reaction is session T and NOT T+1.
        return "pre_open"
    hour = dt.hour + dt.minute / 60.0
    if hour >= 16.0:
        return "after_close"   # reaction is session T+1
    if hour < 9.5:
        return "pre_open"      # in session T
    return "intraday"          # in session T


def _classify_window_true_et(acceptance_iso: str | None, filing_date: str) -> str:
    """`classify_window` under TRUE `America/New_York`. Used ONLY to measure what the
    fixed -4 offset costs (see `_et_datetime`); no cell is computed from it."""
    if not acceptance_iso:
        return "unknown"
    try:
        dt = datetime.fromisoformat(str(acceptance_iso).replace("Z", "+00:00"))
    except Exception:
        return "unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    et = dt.astimezone(ZoneInfo("America/New_York"))
    if et.date().isoformat() != str(filing_date)[:10]:
        return "pre_open"
    hour = et.hour + et.minute / 60.0
    if hour >= 16.0:
        return "after_close"
    return "pre_open" if hour < 9.5 else "intraday"


def load_report_dates(universe: set[str]) -> tuple[dict[str, list[dict]], dict]:
    """Union of the two heterogeneous stores. Each row carries its source + window class."""
    reports: dict[str, list[dict]] = defaultdict(list)
    meta = {
        "edgar_rows": 0, "bridge_rows": 0, "edgar_names": 0, "bridge_names": 0,
        "edgar_window_counts": {}, "edgar_roll_already_applied": 0,
        "edgar_roll_direction_acceptance_after_filing_date": 0,
        "fixed_offset_reaction_session_error": 0,
        "fixed_offset_same_session_reclass": 0,
        "bridge_as_of_counts": {},
    }

    if EDGAR_8K.exists():
        e = pd.read_parquet(EDGAR_8K)
        e = e[e.ticker.isin(universe)]
        wcount: dict[str, int] = defaultdict(int)
        for tkr, fdate, acc in zip(e.ticker, e.filing_date, e.acceptance_datetime):
            fd = str(fdate)[:10]
            window = classify_window(acc, fd)
            wcount[window] += 1
            et = _et_datetime(acc)
            if et is not None:
                if et.date().isoformat() < fd:
                    meta["edgar_roll_already_applied"] += 1
                elif et.date().isoformat() > fd:
                    meta["edgar_roll_direction_acceptance_after_filing_date"] += 1
                # F5 disclosure: what the FIXED -4 offset costs against true ET. Measured
                # every run so the prose can never outlive the defect it describes.
                true_w = _classify_window_true_et(acc, fd)
                if true_w != window:
                    if (true_w == "after_close") != (window == "after_close"):
                        meta["fixed_offset_reaction_session_error"] += 1
                    else:
                        meta["fixed_offset_same_session_reclass"] += 1
            reports[tkr].append({"date": fd, "src": "edgar_8k", "window": window})
        meta["edgar_rows"] = int(len(e))
        meta["edgar_names"] = int(e.ticker.nunique())
        meta["edgar_window_counts"] = dict(sorted(wcount.items()))

    if EARNINGS_NEXT.exists():
        p = pd.read_parquet(EARNINGS_NEXT)
        nd = pd.to_datetime(p["next_date"], errors="coerce")
        today = pd.Timestamp(TODAY_CUTOFF)
        as_of = p["as_of"] if "as_of" in p.columns else pd.Series(index=p.index, dtype=object)
        asof_count: dict[str, int] = defaultdict(int)
        seen_bridge = set()
        for tkr, d, t in zip(p.index, nd, p["next_time"]):
            if tkr not in universe or pd.isna(d) or d >= today:
                continue
            t = str(t or "")
            if "pre-market" in t:
                window = "pre_open"
            elif "after-hours" in t:
                window = "after_close"
            else:
                window = "unknown"
            ds = str(d)[:10]
            # never double-count a date the 8-K store already carries
            if any(r["date"] == ds for r in reports.get(tkr, [])):
                continue
            reports[tkr].append({"date": ds, "src": "bridge_next_date", "window": window})
            meta["bridge_rows"] += 1
            seen_bridge.add(tkr)
            asof_count[str(as_of.get(tkr, ""))[:10] or "unstamped"] += 1
        meta["bridge_names"] = len(seen_bridge)
        meta["bridge_as_of_counts"] = dict(sorted(asof_count.items()))

    for tkr in reports:
        reports[tkr].sort(key=lambda r: r["date"])
    return dict(reports), meta


# ------------------------------------------------------------------ knowability + math

def knowable_pos(date_str: str, pos_of: dict, ref: pd.DatetimeIndex) -> int | None:
    """A marker's date is its 3D bucket's OPEN label; it is actionable only at the
    bucket's LAST session. Returns that session's absolute position."""
    d = pd.Timestamp(date_str).normalize()
    p = pos_of.get(d)
    if p is None:
        i = ref.searchsorted(d, side="left")
        if i >= len(ref):
            return None
        p = int(i)
    last = (p // BUCKET_N) * BUCKET_N + (BUCKET_N - 1)
    return last if last < len(ref) else None


def price_at(prices: pd.Series, ref: pd.DatetimeIndex, pos: int) -> tuple[float | None, bool]:
    """Close at/just-before a reference position. Returns (price, truncated)."""
    if pos < 0:
        return None, False
    if pos >= len(ref):
        return (float(prices.iloc[-1]), True) if len(prices) else (None, False)
    d = ref[pos]
    s = prices[prices.index <= d]
    if s.empty:
        return None, False
    truncated = bool(prices.index.max() < d)
    return float(s.iloc[-1]), truncated


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return (b / a - 1.0) * 100.0


def reaction_position(report_pos: int, window: str) -> int:
    """The session the market first PRICES a report. The single anchor both the reaction
    and the forward cells hang from (F1, v0.1) -- v0 had two anchors and only told one of
    them about the announcement window."""
    return report_pos + 1 if window == "after_close" else report_pos


def measure_excess(px: pd.Series, spy: pd.Series, ref: pd.DatetimeIndex,
                   anchor_pos: int, truncated_flag: list) -> dict:
    """Excess vs SPY at each registered rung, anchored at a session position."""
    out: dict[str, float | None] = {}
    base, _ = price_at(px, ref, anchor_pos)
    sbase, _ = price_at(spy, ref, anchor_pos)
    for h in HORIZONS:
        fwd, tr = price_at(px, ref, anchor_pos + h)
        sfwd, _ = price_at(spy, ref, anchor_pos + h)
        rn, rs = pct(base, fwd), pct(sbase, sfwd)
        out[f"excess_h{h}"] = None if (rn is None or rs is None) else round(rn - rs, 3)
        if tr:
            truncated_flag.append(True)
    return out


def build_report_row(tkr: str, report_pos: int, rec: dict, px: pd.Series,
                     spy: pd.Series, ref: pd.DatetimeIndex) -> dict:
    """One report-anchored row: the day-0 reaction AND the forward excess, both anchored
    on the reaction session.

    THIS IS F1. v0 computed `react_pos` from the announcement window, used it for
    `reaction_pct`, and then anchored the forward excess at `report_pos` -- for an
    after-close print that is the close BEFORE the market has read the report, so H=5 and
    H=10 excess contained the reaction jump itself, on ~39% of the report-anchored rows in
    both A and C. A mutation back to `report_pos` here is caught by
    `test_after_close_forward_excess_is_anchored_after_the_print`.
    """
    react_pos = reaction_position(report_pos, rec["window"])
    prev, _ = price_at(px, ref, react_pos - 1)
    cur, tr = price_at(px, ref, react_pos)
    reaction = pct(prev, cur)
    tflag: list = []
    row = {
        "ticker": tkr,
        "report_date": rec["date"],
        "report_src": rec["src"],
        "report_window": rec["window"],
        "window_unknown": rec["window"] == "unknown",
        "reaction_pct": None if reaction is None else round(reaction, 3),
        "reaction_date": str(ref[react_pos])[:10] if 0 <= react_pos < len(ref) else None,
        "anchor_date": rec["date"],
    }
    row.update(measure_excess(px, spy, ref, react_pos, tflag))
    row["truncated"] = bool(tr or tflag)
    return row


def wilson_ci95(k: int, n: int) -> list[float] | None:
    """Wilson score interval for a proportion, in PERCENT. Wilson and not the normal
    approximation because these rates sit near 50% at large n but the quality- and
    quarter-split cells run to n<20, where the normal interval leaves the unit
    interval and reads as a fabricated bound."""
    if n <= 0:
        return None
    p = k / n
    denom = 1.0 + Z95 * Z95 / n
    centre = (p + Z95 * Z95 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / denom
    return [round(100 * (centre - half), 1), round(100 * (centre + half), 1)]


def summarize(rows: list[dict], key: str) -> dict:
    """One cell. Never returns a bare mean: n, mean, median, win/loser rates, per-name.

    F3 (v0.1): also SE and a 95% interval on the mean, and a Wilson 95% on the win rate.
    v0 printed point estimates only, so a reader could not tell a null from an
    underpowered cell -- the single most important distinction in a receipt whose verdict
    IS a null.
    """
    vals = [r[key] for r in rows if r.get(key) is not None]
    n = len(vals)
    cell = {
        "n": n,
        "n_missing": len(rows) - n,
        "thin": n < THIN_N,
    }
    if n == 0:
        cell.update({"mean": None, "median": None, "se": None, "ci95": None,
                     "win_rate": None, "win_rate_ci95": None,
                     "loser_rate_le_neg3pp": None, "loser_rate_le_0": None,
                     "per_name_first_mean": None})
        return cell
    arr = np.array(vals, dtype=float)
    cell["mean"] = round(float(arr.mean()), 3)
    cell["median"] = round(float(np.median(arr)), 3)
    if n > 1:
        se = float(arr.std(ddof=1)) / math.sqrt(n)
        cell["se"] = round(se, 3)
        cell["ci95"] = [round(float(arr.mean()) - Z95 * se, 3),
                        round(float(arr.mean()) + Z95 * se, 3)]
    else:
        cell["se"] = None      # a single observation has no dispersion; do not print 0.0
        cell["ci95"] = None
    cell["win_rate"] = round(float((arr > 0).mean()) * 100, 1)
    cell["win_rate_ci95"] = wilson_ci95(int((arr > 0).sum()), n)
    cell["loser_rate_le_neg3pp"] = round(float((arr <= LOSER_PP).mean()) * 100, 1)
    cell["loser_rate_le_0"] = round(float((arr <= 0).mean()) * 100, 1)
    by_name: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.get(key) is not None:
            by_name[r["ticker"]].append(r[key])
    per_name = [float(np.mean(v)) for v in by_name.values()]
    cell["per_name_first_mean"] = round(float(np.mean(per_name)), 3)
    cell["n_names"] = len(per_name)
    cell["n_truncated"] = sum(1 for r in rows if r.get("truncated"))
    return cell


def half_split(rows: list[dict], key: str) -> dict:
    """Date half-split on the headline -- a sign flip across halves kills a claim."""
    dated = [r for r in rows if r.get(key) is not None and r.get("anchor_date")]
    if len(dated) < 4:
        return {"early": None, "late": None, "sign_stable": None}
    dated.sort(key=lambda r: r["anchor_date"])
    mid = len(dated) // 2
    e = summarize(dated[:mid], key)
    l = summarize(dated[mid:], key)
    stable = None
    if e["mean"] is not None and l["mean"] is not None:
        stable = bool(np.sign(e["mean"]) == np.sign(l["mean"]))
    return {"early": e, "late": l, "sign_stable": stable}


def contrast(rows_a: list[dict], rows_b: list[dict], key: str,
             label_a: str, label_b: str) -> dict:
    """One PAIRWISE difference with its uncertainty and its detection floor (F3, v0.1).

    v0 stated cohort differences as bare point estimates ("reads slightly worse"), which a
    reader cannot distinguish from noise and which cannot be falsified. This emits the
    difference, the SE of the difference (Welch -- the cohorts have wildly unequal n and
    visibly unequal variance), a t, a 95% interval, and `mde_80pct`: the smallest true
    difference these two n's could have detected 80% of the time at alpha=0.05. A null
    whose MDE is larger than any effect worth acting on is UNDERPOWERED, not absent, and
    saying so is the difference between an honest null and a fabricated one.

    NOT a promotion gate and not a prereg: no threshold here selects, ranks or sizes
    anything. `separation` is a printed reading of an interval, not a verdict.
    """
    va = np.array([r[key] for r in rows_a if r.get(key) is not None], dtype=float)
    vb = np.array([r[key] for r in rows_b if r.get(key) is not None], dtype=float)
    out = {"cohorts": f"{label_a} minus {label_b}", "key": key,
           "n_a": int(va.size), "n_b": int(vb.size)}
    if va.size < 2 or vb.size < 2:
        out.update({"mean_a": None, "mean_b": None, "diff": None, "se_diff": None,
                    "t": None, "ci95_diff": None, "mde_80pct": None,
                    "separation": None, "thin": True})
        return out
    ma, mb = float(va.mean()), float(vb.mean())
    se = math.sqrt(va.var(ddof=1) / va.size + vb.var(ddof=1) / vb.size)
    diff = ma - mb
    lo, hi = diff - Z95 * se, diff + Z95 * se
    out.update({
        "mean_a": round(ma, 3), "mean_b": round(mb, 3),
        "diff": round(diff, 3), "se_diff": round(se, 3),
        "t": round(diff / se, 2) if se > 0 else None,
        "ci95_diff": [round(lo, 3), round(hi, 3)],
        "mde_80pct": round((Z95 + Z80_POWER) * se, 3),
        "separation": "indistinguishable (95% interval on the difference spans zero)"
                      if lo <= 0 <= hi else "separated at 95%",
        "thin": bool(va.size < THIN_N or vb.size < THIN_N),
    })
    return out


# ------------------------------------------------------------------------- base pinning

def _git_sha() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or None
    except Exception:
        return None


def base_stamps(universe: set[str], markers: dict[str, list[dict]],
                reports: dict[str, list[dict]], spy: pd.Series) -> dict:
    """Commit + data vintages for this run (v0.1).

    v0 shipped currency claims ("signal_date does not exist on this base", "never
    refreshed after 2026-06-19") with NOTHING in the artifact to date them, so they read
    as permanent facts and were already stale within a day. Anything a later reader might
    check against a moving repo is pinned here.
    """
    marker_dates = [m["date"] for rows in markers.values() for m in rows if m.get("date")]
    report_dates = [r["date"] for rows in reports.values() for r in rows if r.get("date")]
    return {
        "repo_commit_at_run": _git_sha(),
        "repo_commit_note": ("the commit the instrument READ -- i.e. the parent of the "
                             "commit that carries this artifact"),
        "window_cutoff_today": TODAY_CUTOFF,
        "signals_vintage_max_marker_date": max(marker_dates) if marker_dates else None,
        # BUY/REBUY only -- the population this instrument reads. The 56,293 figure quoted
        # in definitions.knowability is ALL marker types across the same artifacts.
        "signals_buy_rebuy_markers_total": len(marker_dates),
        "signals_buy_rebuy_markers_with_signal_date": sum(
            1 for rows in markers.values() for m in rows if m.get("signal_date")),
        "signals_signal_date_note": (
            "0 here is EXPECTED at this vintage and is not a defect: signal_date landed on "
            "main in #5071, which re-rendered site/signals AFTER the 2026-08-08 artifacts "
            "this run deliberately holds. See definitions.knowability."),
        "report_dates_max": max(report_dates) if report_dates else None,
        "prices_last_session": str(spy.index.max())[:10] if spy is not None and len(spy) else None,
        "universe_size": len(universe),
    }


# ---------------------------------------------------------------------------- the build

def main() -> int:
    ref, pos_of = load_sessions()
    markers = load_markers()
    universe = set(markers)
    reports, rep_meta = load_report_dates(universe)

    spy = load_prices("SPY")
    if spy is None:
        print("::error title=earnings-ignition::SPY benchmark unavailable", flush=True)
        return 1

    price_cache: dict[str, pd.Series | None] = {}

    def prices_for(t: str) -> pd.Series | None:
        if t not in price_cache:
            price_cache[t] = load_prices(t)
        return price_cache[t]

    # report positions per name, for the control test and the base-rate cohort
    rep_pos: dict[str, list[tuple[int, dict]]] = {}
    for t, rs in reports.items():
        acc = []
        for r in rs:
            d = pd.Timestamp(r["date"]).normalize()
            i = ref.searchsorted(d, side="left")
            if i < len(ref):
                acc.append((int(i), r))
        rep_pos[t] = sorted(acc)

    # ---- F2: the earnings-store COVERAGE INDEX, which the cohort-B floor reads.
    # "No report within +/-10 sessions" is only a control if the store WOULD have held a
    # report had one existed. For a name-year the store never observed, the same test
    # manufactures a control row out of a data hole. The floor is per NAME-YEAR and not
    # per name-span on purpose: a name whose rows stop in 2018 passes any whole-span test
    # while every marker after 2018 sits in a hole, which is exactly the failure mode.
    reported_name_years: set[tuple[str, int]] = set()
    reports_per_name: dict[str, int] = defaultdict(int)
    for t, rs in reports.items():
        for r in rs:
            reported_name_years.add((t, int(r["date"][:4])))
            reports_per_name[t] += 1
    names_zero_8k = sorted(
        t for t in universe
        if not any(r["src"] == "edgar_8k" for r in reports.get(t, []))
    )
    names_zero_reports_any_source = sorted(t for t in universe if not reports.get(t))

    cohort_a: list[dict] = []
    cohort_b: list[dict] = []          # floored control (F2)
    cohort_b_unfloored: list[dict] = []  # v0's construction, kept inspectable
    cohort_c: list[dict] = []
    absent_names = [t for t in CASE_RECEIPTS if t not in universe]
    case_rows: dict[str, list[dict]] = defaultdict(list)
    same_session_confluence_n = 0

    # earliest priced session per name bounds every window
    for tkr in sorted(universe):
        px = prices_for(tkr)
        if px is None or px.empty:
            continue
        first_pos = int(ref.searchsorted(px.index.min(), side="left"))
        last_pos = int(ref.searchsorted(px.index.max(), side="left"))
        rps = rep_pos.get(tkr, [])
        rep_positions = [p for p, _ in rps]

        def measure_from(anchor_pos: int, truncated_flag: list) -> dict:
            return measure_excess(px, spy, ref, anchor_pos, truncated_flag)

        # ---- marker-anchored cohorts (A entry-anchored rows, and B)
        for m in markers[tkr]:
            kp = knowable_pos(m["date"], pos_of, ref)
            if kp is None or kp < first_pos or kp > last_pos:
                continue
            # nearest report at/after knowability
            nxt = [p for p in rep_positions if kp < p <= kp + PRE_WINDOW]
            near = [p for p in rep_positions if abs(p - kp) <= CONTROL_GAP]
            tflag: list = []
            base_row = {
                "ticker": tkr,
                "marker_date": m["date"],
                "knowable_date": str(ref[kp])[:10],
                "type": m["type"],
                "quality": m.get("quality"),
                "anchor_date": str(ref[kp])[:10],
            }
            if nxt:
                rp = min(nxt)
                rec = next(r for p, r in rps if p == rp)
                row = dict(base_row)
                row.update(measure_from(kp, tflag))
                row["truncated"] = bool(tflag)
                row["report_date"] = rec["date"]
                row["report_src"] = rec["src"]
                row["report_window"] = rec["window"]
                row["lead_sessions"] = int(rp - kp)
                cohort_a.append(row)
                if tkr in CASE_RECEIPTS:
                    case_rows[tkr].append(row)
            elif not near:
                row = dict(base_row)
                row.update(measure_from(kp, tflag))
                row["truncated"] = bool(tflag)
                # F2 COVERAGE FLOOR. Eligible only if the store actually observed this
                # name in this year -- otherwise "no report nearby" is a claim about the
                # STORE, not about the name, and the row is a hole wearing a control's
                # clothes. Both cohorts are kept: the floored one is the control, the
                # unfloored one preserves v0's cell so the correction stays inspectable.
                year = int(str(ref[kp])[:4])
                covered = (tkr, year) in reported_name_years
                row["name_year_covered"] = covered
                cohort_b_unfloored.append(row)
                if covered:
                    cohort_b.append(row)

        # ---- report-anchored cohorts (A event-anchored, and C)
        for rp, rec in rps:
            if rp < first_pos or rp > last_pos:
                continue
            # reaction AND forward excess both anchored on the reaction session (F1)
            row = build_report_row(tkr, rp, rec, px, spy, ref)
            # F11: a marker knowable ON the report session (kp2 == rp) is NOT a PRE-report
            # confluence -- the window is [T-5, T-1] and stays that way -- so such a row
            # falls to C. That is defensible but it seats a same-session confluence inside
            # the "no confluence at all" base rate, so it is counted and C is reprinted
            # without them rather than left implicit.
            row["same_session_confluence"] = any(
                knowable_pos(m["date"], pos_of, ref) == rp for m in markers[tkr]
            )
            pre = [m for m in markers[tkr]
                   if (kp2 := knowable_pos(m["date"], pos_of, ref)) is not None
                   and rp - PRE_WINDOW <= kp2 <= rp - 1]
            if pre:
                row["has_pre_confluence"] = True
                row["marker_date"] = pre[-1]["date"]
                row["quality"] = pre[-1].get("quality")
                row["type"] = pre[-1]["type"]
                kp2 = knowable_pos(pre[-1]["date"], pos_of, ref)
                row["knowable_date"] = str(ref[kp2])[:10]
                row["lead_sessions"] = int(rp - kp2)
                cohort_c.append(row)  # collected then split below
            else:
                row["has_pre_confluence"] = False
                cohort_c.append(row)

    a_event = [r for r in cohort_c if r.get("has_pre_confluence")]
    c_base = [r for r in cohort_c if not r.get("has_pre_confluence")]
    c_base_no_same_session = [r for r in c_base if not r.get("same_session_confluence")]
    same_session_confluence_n = len(c_base) - len(c_base_no_same_session)

    # ------------------------------------------------------------------ adverse tail
    adverse = [r for r in a_event if r.get("reaction_pct") is not None and r["reaction_pct"] < 0]
    adverse.sort(key=lambda r: r["reaction_pct"])

    def cells(rows: list[dict], keys: tuple[str, ...]) -> dict:
        return {k: summarize(rows, k) for k in keys}

    event_keys = ("reaction_pct", "excess_h5", "excess_h10")
    entry_keys = ("excess_h5", "excess_h10")

    def quality_split(rows: list[dict], keys: tuple[str, ...]) -> dict:
        out = {}
        for q in ("take", "block", "pending", None):
            sub = [r for r in rows if r.get("quality") == q]
            if sub:
                out[str(q)] = {"n": len(sub), **cells(sub, keys)}
        return out

    def quarter_split(rows: list[dict], key: str) -> dict:
        out = {}
        buckets: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            d = r.get("anchor_date")
            if not d:
                continue
            ts = pd.Timestamp(d)
            buckets[f"{ts.year}Q{ (ts.month - 1)//3 + 1 }"].append(r)
        for q in sorted(buckets):
            out[q] = summarize(buckets[q], key)
        return out

    results = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "schema_version": "0.1",
        "program": "ANTICIPATION §6.8(e) EARNINGS IGNITION",
        "tier": "research / display-audit only -- no gate, rank, size, lane or surface changed",
        "a7_note": "purely mechanical; no LLM call of any kind is made by this instrument",
        # PIN THE BASE. v0 carried no commit or vintage stamp, so its currency claims
        # (notably "signal_date does not exist on this base") could rot silently into
        # falsehoods with nothing in the artifact to date them. Every such claim in v0.1 is
        # anchored to these stamps.
        "base": base_stamps(universe, markers, reports, spy),
        "amendment": {
            "version": "0.1",
            "date": "2026-08-09",
            "supersedes": "v0 (2026-08-08), same window, same data vintage, corrected instrument",
            "corrections": {
                "F1": "forward excess re-anchored from the report session to the REACTION session",
                "F2": "cohort-B coverage floor (name-year must be observed by the store)",
                "F3": "SE + 95% intervals on every cell; pairwise contrasts with t and MDE",
                "F4": "EDGAR-roll double-count removed from the announcement-window classifier",
                "F5": "fixed -4 ET offset error measured and disclosed rather than asserted away",
                "F7": "case-receipt 'nearest report' took the LATEST; now true nearest",
                "F8": "removed a no-op TZ line that read as a guarantee",
                "F10": "no-prereg / no-multiplicity-correction disclosed",
                "F11": "same-session confluences seated in C are counted and C reprinted without them",
                "F12": "universe disclosed as self-restricted (240 of 2,768 priced names)",
                "F13": "the test file is now wired into CI (it never ran)",
            },
        },
        "definitions": {
            "fresh_confluence": "a buy or rebuy marker in site/signals/<T>.json (transition events)",
            "knowability": ("marker date is the 3D bucket OPEN label; knowability = that "
                            "bucket's LAST session. DERIVED. At the 2026-08-08 vintage this "
                            "run reads, markers carried NO signal_date field; v0 attributed "
                            "that to unmerged PR #4987, which was in fact CLOSED unmerged -- "
                            "the field landed on main in #5071, which re-rendered "
                            "site/signals with signal_date on 56,181 of 56,293 markers. "
                            "The derivation was audited against the stamped field on that "
                            "later render: they agree on 26,763 of 26,788 comparable markers "
                            "(99.91%), every disagreement pre-1995 and outside this study's "
                            "2014+ window. The derivation is therefore NOT load-bearing."),
            "reaction_pct": "close(reaction session)/close(prior session)-1, reaction session derived from the announcement window",
            "excess": ("name return minus SPY return over the same session span, in pp, "
                       "anchored on the REACTION session for report-anchored rows (v0.1 F1) "
                       "and on the knowability date for entry-anchored rows"),
            "loser": f"excess <= {LOSER_PP}pp (STATED); excess <= 0 also printed",
            "win": "excess > 0",
            "horizons": list(HORIZONS),
            "cohort_a": f"buy/rebuy knowable in [T-{PRE_WINDOW}, T-1] sessions before report T",
            "cohort_b": (f"buy/rebuy with NO report within +/-{CONTROL_GAP} sessions AND whose "
                         "name-year is observed by the earnings store (v0.1 F2 coverage floor)"),
            "cohort_c": "report date with NO pre-report confluence (base rate)",
        },
        "coverage": {
            "signals_universe": len(universe),
            "names_with_prices": sum(1 for t in universe if prices_for(t) is not None),
            "universe_is_self_restricted": (
                "240 published site/signals artifacts, NOT a data limit: the same price store "
                "this instrument reads carries 2,768 US tickers (sibling study "
                "ignition_standins.py runs on all of them). Every thin per-quarter cell below "
                "is therefore partly a chosen frame. Widening the UNIVERSE is honest and cheap; "
                "widening the LEAD WINDOW after seeing the receipts is not, and is not done."),
            "edgar_8k": {"rows_in_universe": rep_meta["edgar_rows"],
                         "names": rep_meta["edgar_names"],
                         "names_with_zero_rows": len(names_zero_8k),
                         "names_with_zero_rows_list": names_zero_8k,
                         "note": ("SEC 8-K Item 2.02; ENDS 2026-07-02 -- before all three operator "
                                  "receipts. v0 called price history 'the binding constraint, tighter "
                                  "than earnings coverage'; that is FALSE for the names listed here, "
                                  "which hold zero 8-K rows across the whole span.")},
            "bridge_next_date": {"rows": rep_meta["bridge_rows"], "names": rep_meta["bridge_names"],
                                 "as_of_counts": rep_meta["bridge_as_of_counts"],
                                 "note": ("data/earnings/earnings.parquet next_date now in the past. "
                                          "v0 said these rows 'were never refreshed after 2026-06-19'; "
                                          "measured, that holds for the 2026-06-19 bucket only -- see "
                                          "as_of_counts for the rows carrying a later stamp.")},
            "names_with_zero_reports_any_source": names_zero_reports_any_source,
            "announcement_window": {
                "edgar_window_counts": rep_meta["edgar_window_counts"],
                "edgar_roll_already_applied": rep_meta["edgar_roll_already_applied"],
                "edgar_roll_direction_acceptance_after_filing_date":
                    rep_meta["edgar_roll_direction_acceptance_after_filing_date"],
                "fixed_offset_reaction_session_error": rep_meta["fixed_offset_reaction_session_error"],
                "fixed_offset_same_session_reclass": rep_meta["fixed_offset_same_session_reclass"],
                "note": ("F4: edgar_roll_already_applied rows arrive ALREADY dated to the session "
                         "that reads them; v0 rolled them a second time. F5: the fixed -4 ET offset "
                         "puts fixed_offset_reaction_session_error rows on the wrong side of the "
                         "16:00 edge against true America/New_York; the same_session_reclass rows "
                         "move only between pre_open and intraday, which are the same session T."),
            },
            "cohort_b_coverage_floor": {
                "construction": ("a control marker is eligible only if the earnings store holds >=1 "
                                 "report for that TICKER-YEAR. Per name-year, not per name-span: a "
                                 "name whose rows stop in 2018 passes any whole-span test while every "
                                 "later marker sits in a hole."),
                "n_rows_unfloored_v0": len(cohort_b_unfloored),
                "n_rows_floored": len(cohort_b),
                "n_rows_dropped_as_coverage_holes": len(cohort_b_unfloored) - len(cohort_b),
                "hole_share_of_v0_control_pct": (
                    round(100.0 * (len(cohort_b_unfloored) - len(cohort_b)) / len(cohort_b_unfloored), 1)
                    if cohort_b_unfloored else None),
                "note": ("v0's control answered 'no report within +/-10 sessions', which for an "
                         "unobserved name-year is a statement about the STORE, not the name."),
            },
            "same_session_confluence_in_c": {
                "n": same_session_confluence_n,
                "note": ("markers knowable ON the report session are not PRE-report confluences "
                         "(the window is [T-5, T-1] and is not moved), so they fall to the base "
                         "rate C. Counted here and C reprinted without them below."),
            },
            "case_receipt_names_absent_from_signals": absent_names,
            "price_source": "data/baskets/ohlcv (primary) -> data/yahoo (fallback); SPY benchmark from data/yahoo",
        },
        "cohort_a_event_anchored": {
            "n_rows": len(a_event),
            "cells": cells(a_event, event_keys),
            "half_split_reaction": half_split(a_event, "reaction_pct"),
            "by_quality": quality_split(a_event, event_keys),
            "by_quarter_reaction": quarter_split(a_event, "reaction_pct"),
            "window_known_only": cells([r for r in a_event if not r["window_unknown"]], event_keys),
        },
        "cohort_c_base_rate": {
            "n_rows": len(c_base),
            "cells": cells(c_base, event_keys),
            "half_split_reaction": half_split(c_base, "reaction_pct"),
            "by_quarter_reaction": quarter_split(c_base, "reaction_pct"),
            "window_known_only": cells([r for r in c_base if not r["window_unknown"]], event_keys),
            "excluding_same_session_confluence": {
                "n_rows": len(c_base_no_same_session),
                "cells": cells(c_base_no_same_session, event_keys),
            },
        },
        "cohort_a_entry_anchored": {
            "n_rows": len(cohort_a),
            "cells": cells(cohort_a, entry_keys),
            "half_split_h5": half_split(cohort_a, "excess_h5"),
            "by_quality": quality_split(cohort_a, entry_keys),
        },
        "cohort_b_entry_control": {
            "n_rows": len(cohort_b),
            "coverage_floor": "name-year observed by the earnings store (v0.1 F2)",
            "cells": cells(cohort_b, entry_keys),
            "half_split_h5": half_split(cohort_b, "excess_h5"),
            "by_quality": quality_split(cohort_b, entry_keys),
        },
        "cohort_b_entry_control_unfloored_v0": {
            "note": ("v0's control, WITHOUT the coverage floor. Retained so the correction is "
                     "inspectable rather than asserted. Not the control of record."),
            "n_rows": len(cohort_b_unfloored),
            "cells": cells(cohort_b_unfloored, entry_keys),
            "by_quality": quality_split(cohort_b_unfloored, entry_keys),
        },
        "adverse_tail": {
            "definition": "cohort A (event-anchored) rows whose day-0 reaction was NEGATIVE",
            "n": len(adverse),
            "share_of_cohort_a_pct": (round(100.0 * len(adverse) /
                                            max(1, sum(1 for r in a_event if r.get("reaction_pct") is not None)), 1)
                                      if a_event else None),
            "worst_20": [
                {k: r.get(k) for k in ("ticker", "marker_date", "knowable_date", "report_date",
                                       "report_src", "report_window", "quality", "type",
                                       "lead_sessions", "reaction_pct", "excess_h5", "excess_h10")}
                for r in adverse[:20]
            ],
        },
        "case_receipts": {},
    }

    # ---- F3: the PAIRWISE contrasts, with uncertainty and a detection floor. Anchors are
    # never mixed -- A-vs-C is report-anchored, A-vs-B is entry-anchored -- and there is
    # still NO pooled top-line. These replace v0's bare point-estimate comparisons, which
    # could be read as findings but could not be falsified.
    results["contrasts"] = {
        "note": ("Welch differences with a 95% interval and mde_80pct = the smallest true "
                 "difference this n could detect 80% of the time at alpha=0.05. Read every "
                 "null beside its MDE: a difference smaller than the MDE is UNMEASURED, not "
                 "absent. No threshold here selects, ranks or sizes anything."),
        "event_anchored_A_vs_C": {
            k: contrast(a_event, c_base, k, "A (pre-report confluence)", "C (base rate)")
            for k in event_keys
        },
        "entry_anchored_A_vs_B": {
            k: contrast(cohort_a, cohort_b, k, "A (entry into a report)", "B (floored control)")
            for k in entry_keys
        },
        "entry_anchored_A_vs_B_unfloored_v0": {
            k: contrast(cohort_a, cohort_b_unfloored, k, "A (entry into a report)",
                        "B (v0 unfloored control)")
            for k in entry_keys
        },
    }

    # ---- lead-sensitivity profile INSIDE the chartered window (descriptive only; extending
    # the window after seeing which receipts fall outside it would be `DNR:KILL-OUTCOME-
    # AUDITION`'s construction, so the profile stops at the chartered T-5 and does not search)
    results["cohort_a_by_lead_sessions"] = {
        str(lead): summarize([r for r in a_event if r.get("lead_sessions") == lead], "reaction_pct")
        for lead in range(1, PRE_WINDOW + 1)
    }

    # ---- the four operator receipts, stated against the frame that actually exists
    receipts_2026: dict[str, dict] = {}
    for t in CASE_RECEIPTS:
        if t not in universe:
            continue
        px = prices_for(t)
        recent = [m for m in markers[t] if m["date"] >= "2026-05-01"]
        rows = []
        for m in recent:
            kp = knowable_pos(m["date"], pos_of, ref)
            kd = str(ref[kp])[:10] if kp is not None else None
            # F7 (v0.1): v0 wrote this as a loop that overwrote `nearest` on every match,
            # so on a date-sorted list it returned the LATEST 2026 report, not the nearest.
            # For a name with two 2026 reports that silently reports the wrong lead.
            cands = [(p, rec) for p, rec in rep_pos.get(t, []) if rec["date"] >= "2026-05-01"]
            nearest = (min(cands, key=lambda pr: abs(pr[0] - kp))
                       if (cands and kp is not None) else None)
            lead = None
            if nearest and kp is not None:
                lead = int(nearest[0] - kp)
            rows.append({
                "marker_date": m["date"], "type": m["type"], "quality": m.get("quality"),
                "knowable_date": kd,
                "nearest_2026_report": nearest[1]["date"] if nearest else None,
                "report_src": nearest[1]["src"] if nearest else None,
                "lead_sessions_report_minus_knowable": lead,
                "in_cohort_a": bool(lead is not None and 1 <= lead <= PRE_WINDOW),
            })
        receipts_2026[t] = {"markers_since_2026_05": rows}
    results["operator_receipts_2026"] = {
        "note": ("The 2026 report dates available on this base are BRIDGE FORECASTS stamped "
                 "as_of 2026-06-19, not confirmed filings -- EDGAR, the confirming source, "
                 "stops 2026-07-02. A +/-1 session error in a forecast date is therefore "
                 "possible and every statement below is checked to survive it."),
        "per_name": receipts_2026,
    }

    for t in CASE_RECEIPTS:
        if t in absent_names:
            results["case_receipts"][t] = {
                "status": "ABSENT from the 240-name signals universe -- no marker can exist",
                "reason": "no site/signals/%s.json artifact is published on this base" % t,
                "has_earnings_row": t in {x for x in reports},
            }
            continue
        rows = [r for r in a_event if r["ticker"] == t]
        rows += [r for r in cohort_a if r["ticker"] == t
                 and not any(x.get("report_date") == r.get("report_date") for x in rows)]
        rows.sort(key=lambda r: r.get("report_date") or "")
        results["case_receipts"][t] = {
            "status": "in universe",
            "n_pre_earnings_confluences": len(rows),
            "rows": [
                {k: r.get(k) for k in ("marker_date", "knowable_date", "report_date", "report_src",
                                       "report_window", "quality", "type", "lead_sessions",
                                       "reaction_pct", "excess_h5", "excess_h10", "truncated")}
                for r in rows[-6:]
            ],
        }

    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))

    # ------------------------------------------------------------------------ console
    print(f"universe={len(universe)}  A_event={len(a_event)}  C_base={len(c_base)}  "
          f"A_entry={len(cohort_a)}  B_control={len(cohort_b)}")
    for label, cell in (("A reaction", results["cohort_a_event_anchored"]["cells"]["reaction_pct"]),
                        ("C reaction", results["cohort_c_base_rate"]["cells"]["reaction_pct"]),
                        ("A excess_h5", results["cohort_a_event_anchored"]["cells"]["excess_h5"]),
                        ("C excess_h5", results["cohort_c_base_rate"]["cells"]["excess_h5"]),
                        ("A-entry h5", results["cohort_a_entry_anchored"]["cells"]["excess_h5"]),
                        ("B-entry h5", results["cohort_b_entry_control"]["cells"]["excess_h5"])):
        print(f"  {label:14s} n={cell['n']:6d} mean={cell['mean']} median={cell['median']} "
              f"win={cell['win_rate']}% loser<=-3pp={cell['loser_rate_le_neg3pp']}% "
              f"se={cell['se']} ci95={cell['ci95']}"
              + ("  THIN" if cell["thin"] else ""))
    ad = results["adverse_tail"]
    print(f"  ADVERSE TAIL n={ad['n']} ({ad['share_of_cohort_a_pct']}% of cohort A)")
    for name, block in (("A-vs-C reaction", results["contrasts"]["event_anchored_A_vs_C"]["reaction_pct"]),
                        ("A-vs-C excess_h5", results["contrasts"]["event_anchored_A_vs_C"]["excess_h5"]),
                        ("A-vs-B excess_h5", results["contrasts"]["entry_anchored_A_vs_B"]["excess_h5"])):
        print(f"  {name:18s} diff={block['diff']} se={block['se_diff']} t={block['t']} "
              f"ci95={block['ci95_diff']} mde80={block['mde_80pct']} -> {block['separation']}")
    cf = results["coverage"]["cohort_b_coverage_floor"]
    print(f"  B coverage floor: {cf['n_rows_unfloored_v0']} -> {cf['n_rows_floored']} "
          f"({cf['n_rows_dropped_as_coverage_holes']} holes = {cf['hole_share_of_v0_control_pct']}%)")
    aw = results["coverage"]["announcement_window"]
    print(f"  window: EDGAR already-rolled={aw['edgar_roll_already_applied']} "
          f"fixed-offset session errors={aw['fixed_offset_reaction_session_error']}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
