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

FRAME REALITY vs THE COMMISSIONING BRIEF (census-first; the delta IS the headline)
  * The brief expected a `signal_date` field on markers. It does NOT exist on this base --
    it ships in unmerged PR #4987, and `OUTAGE_WINDOW_STAMP_AUDIT_2026-08-08.md` is not on
    main either. So knowability is DERIVED here and the derivation is disclosed: a marker's
    `date` is its 3D bucket's OPEN label (`engine/signal_quality` docstring: "labelled by
    the bucket's OPEN date"), so the earliest an actor could act on it is the bucket's LAST
    session. Every cohort test uses that derived knowability date, never the open label.
  * There is no single earnings-date store. The deep history is `data/edgar/
    earnings_8k_dates.parquet` (SEC 8-K Item 2.02, 2004-08-24..2026-07-02) and it STOPS
    2026-07-02 -- before all three operator receipts. The recent window is bridged by
    `data/earnings/earnings.parquet` `next_date`, which retains the July dates only
    because those rows were never refreshed after 2026-06-19. The two sources are
    heterogeneous and every cell prints its source mix.
  * DLB and SPCX -- two of the four requested case receipts -- are NOT in the 240-name
    signals universe at all, so no marker for them can exist. Printed as absent, not
    silently dropped.
  * The measurement window is bounded by PRICE history (`data/baskets/ohlcv` starts
    2014-01-02 for most names), not by earnings coverage.

ANNOUNCEMENT-WINDOW CONVENTION (the reaction day is derived, never assumed)
    A close-to-close "day 0" is wrong for roughly half of all reports, so the reaction
    session is derived per row: EDGAR rows use `acceptance_datetime` (UTC -> ET); bridge
    rows use `next_time` (time-pre-market / time-after-hours). Accepted before the open ->
    the report is in session T. Accepted after the close -> the reaction is session T+1.
    Intraday -> session T. Unknown -> the row is flagged `window_unknown` and every
    headline is reprinted excluding those rows, so the convention's effect stays visible.

STATS GUARDS (binding on every cell)
    n printed on every cell; cells with n < 20 carry `thin: true` and are never used as a
    verdict; per-name-first printed beside pooled so one busy name cannot carry a cohort;
    medians printed beside means so no verdict hangs on a threshold; half-split (by date)
    on every headline; NO pooled top-line that averages cohorts against each other -- the
    contrasts are stated pairwise (A vs C event-anchored, A vs B entry-anchored) and the
    anchors are never mixed; nulls printed as nulls, never as zeros.

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
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Date logic is UTC-pinned (house law); the ET conversions below are explicit offsets.
os.environ.setdefault("TZ", "UTC")

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
            {"date": m["date"], "type": m["type"], "quality": m.get("quality")}
            for m in doc.get("markers", [])
            if m.get("type") in ("buy", "rebuy") and m.get("date")
        ]
        out[path.stem] = rows
    return out


def _et_hour(iso_utc: str) -> float | None:
    """UTC ISO -> ET hour-of-day. Fixed -4 (EDT); reports cluster Jan-Oct so the
    EST/EDT boundary moves at most one hour and never across the 09:30/16:00 edges
    for the after-hours and pre-market clusters this is used to separate."""
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt.astimezone(timezone.utc).hour + dt.astimezone(timezone.utc).minute / 60.0) - 4.0


def load_report_dates(universe: set[str]) -> tuple[dict[str, list[dict]], dict]:
    """Union of the two heterogeneous stores. Each row carries its source + window class."""
    reports: dict[str, list[dict]] = defaultdict(list)
    meta = {"edgar_rows": 0, "bridge_rows": 0, "edgar_names": 0, "bridge_names": 0}

    if EDGAR_8K.exists():
        e = pd.read_parquet(EDGAR_8K)
        e = e[e.ticker.isin(universe)]
        for tkr, fdate, acc in zip(e.ticker, e.filing_date, e.acceptance_datetime):
            hour = _et_hour(str(acc)) if acc else None
            if hour is None:
                window = "unknown"
            elif hour < 9.5:
                window = "pre_open"      # in session T
            elif hour >= 16.0:
                window = "after_close"   # reaction is session T+1
            else:
                window = "intraday"      # in session T
            reports[tkr].append({"date": str(fdate)[:10], "src": "edgar_8k", "window": window})
        meta["edgar_rows"] = int(len(e))
        meta["edgar_names"] = int(e.ticker.nunique())

    if EARNINGS_NEXT.exists():
        p = pd.read_parquet(EARNINGS_NEXT)
        nd = pd.to_datetime(p["next_date"], errors="coerce")
        today = pd.Timestamp("2026-08-08")
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
        meta["bridge_names"] = len(seen_bridge)

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


def summarize(rows: list[dict], key: str) -> dict:
    """One cell. Never returns a bare mean: n, mean, median, win/loser rates, per-name."""
    vals = [r[key] for r in rows if r.get(key) is not None]
    n = len(vals)
    cell = {
        "n": n,
        "n_missing": len(rows) - n,
        "thin": n < THIN_N,
    }
    if n == 0:
        cell.update({"mean": None, "median": None, "win_rate": None,
                     "loser_rate_le_neg3pp": None, "loser_rate_le_0": None,
                     "per_name_first_mean": None})
        return cell
    arr = np.array(vals, dtype=float)
    cell["mean"] = round(float(arr.mean()), 3)
    cell["median"] = round(float(np.median(arr)), 3)
    cell["win_rate"] = round(float((arr > 0).mean()) * 100, 1)
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

    cohort_a: list[dict] = []
    cohort_b: list[dict] = []
    cohort_c: list[dict] = []
    absent_names = [t for t in CASE_RECEIPTS if t not in universe]
    case_rows: dict[str, list[dict]] = defaultdict(list)

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
            """excess vs SPY at each registered rung, anchored at a session position."""
            out = {}
            base, tr0 = price_at(px, ref, anchor_pos)
            sbase, _ = price_at(spy, ref, anchor_pos)
            for h in HORIZONS:
                fwd, tr = price_at(px, ref, anchor_pos + h)
                sfwd, _ = price_at(spy, ref, anchor_pos + h)
                rn, rs = pct(base, fwd), pct(sbase, sfwd)
                out[f"excess_h{h}"] = None if (rn is None or rs is None) else round(rn - rs, 3)
                if tr:
                    truncated_flag.append(True)
            return out

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
                cohort_b.append(row)

        # ---- report-anchored cohorts (A event-anchored, and C)
        for rp, rec in rps:
            if rp < first_pos or rp > last_pos:
                continue
            # reaction session per the derived announcement window
            react_pos = rp + 1 if rec["window"] == "after_close" else rp
            prev, _ = price_at(px, ref, react_pos - 1)
            cur, tr = price_at(px, ref, react_pos)
            reaction = pct(prev, cur)
            tflag2: list = []
            row = {
                "ticker": tkr,
                "report_date": rec["date"],
                "report_src": rec["src"],
                "report_window": rec["window"],
                "window_unknown": rec["window"] == "unknown",
                "reaction_pct": None if reaction is None else round(reaction, 3),
                "anchor_date": rec["date"],
            }
            row.update(measure_from(rp, tflag2))
            row["truncated"] = bool(tr or tflag2)
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
        "program": "ANTICIPATION §6.8(e) EARNINGS IGNITION",
        "tier": "research / display-audit only -- no gate, rank, size, lane or surface changed",
        "a7_note": "purely mechanical; no LLM call of any kind is made by this instrument",
        "definitions": {
            "fresh_confluence": "a buy or rebuy marker in site/signals/<T>.json (transition events)",
            "knowability": ("marker date is the 3D bucket OPEN label; knowability = that "
                            "bucket's LAST session (derived -- signal_date does not exist "
                            "on this base, it ships in unmerged PR #4987)"),
            "reaction_pct": "close(reaction session)/close(prior session)-1, reaction session derived from the announcement window",
            "excess": "name return minus SPY return over the same session span, in pp",
            "loser": f"excess <= {LOSER_PP}pp (STATED); excess <= 0 also printed",
            "win": "excess > 0",
            "horizons": list(HORIZONS),
            "cohort_a": f"buy/rebuy knowable in [T-{PRE_WINDOW}, T-1] sessions before report T",
            "cohort_b": f"buy/rebuy with NO report within +/-{CONTROL_GAP} sessions (entry control)",
            "cohort_c": "report date with NO pre-report confluence (base rate)",
        },
        "coverage": {
            "signals_universe": len(universe),
            "names_with_prices": sum(1 for t in universe if prices_for(t) is not None),
            "edgar_8k": {"rows_in_universe": rep_meta["edgar_rows"],
                         "names": rep_meta["edgar_names"],
                         "note": "SEC 8-K Item 2.02; ENDS 2026-07-02 -- before all three operator receipts"},
            "bridge_next_date": {"rows": rep_meta["bridge_rows"], "names": rep_meta["bridge_names"],
                                 "note": ("data/earnings/earnings.parquet next_date now in the past; "
                                          "retains July dates only because those rows were never "
                                          "refreshed after 2026-06-19")},
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
        },
        "cohort_a_entry_anchored": {
            "n_rows": len(cohort_a),
            "cells": cells(cohort_a, entry_keys),
            "half_split_h5": half_split(cohort_a, "excess_h5"),
            "by_quality": quality_split(cohort_a, entry_keys),
        },
        "cohort_b_entry_control": {
            "n_rows": len(cohort_b),
            "cells": cells(cohort_b, entry_keys),
            "half_split_h5": half_split(cohort_b, "excess_h5"),
            "by_quality": quality_split(cohort_b, entry_keys),
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
            nearest = None
            for p, rec in rep_pos.get(t, []):
                if rec["date"] >= "2026-05-01":
                    nearest = (p, rec)
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
              f"win={cell['win_rate']}% loser<=-3pp={cell['loser_rate_le_neg3pp']}%"
              + ("  THIN" if cell["thin"] else ""))
    ad = results["adverse_tail"]
    print(f"  ADVERSE TAIL n={ad['n']} ({ad['share_of_cohort_a_pct']}% of cohort A)")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
