"""engine/rebalance_calendar.py — US rebalance & reconstitution calendar (RLT-R1).

Pure-rule calendar over lib.nyse_calendar.  No signal claims, no seasonality
scores (IHM "no seasonal signal" law respected; TOM is dead post-2000 per
NOVEL_IDEAS.md and is NOT revived here).

Emits per-session tags:
  is_quarter_end          — last NYSE session of Mar/Jun/Sep/Dec
  td_to_quarter_end       — signed trading-day distance to the NEAREST QE:
                            0 on the QE day itself; positive = sessions until
                            the next QE; negative = sessions since the last QE
  in_qtr_end_window       — |td_to_quarter_end| <= 3
  is_russell_recon_session — rule: last Friday of June, adjusted if closed;
                            RECON_OVERRIDES wins when present
  in_recon_week           — any session in the same ISO week as the recon day
  is_sp_rebalance_session  — S&P quarterly rebalance = quad-witching 3rd-Friday
                            of Mar/Jun/Sep/Dec (via engine.opex helpers)
  is_month_end_session     — last session of each calendar month

Authority: display/context tier.  may_rank=false, may_gate=false, may_size=false.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from lib.nyse_calendar import is_session, last_session_on_or_before

# ── Constants ────────────────────────────────────────────────────────────────

QUARTER_MONTHS = (3, 6, 9, 12)

# Explicit overrides for Russell reconstitution (rank effective date).
# Rule = last Friday of June, adjusted back if the exchange is closed.
# OVERRIDES WIN over the rule.  Seed: 2020-2026.
# Source: FTSE Russell annual reconstitution announcements.
# 2026 → 2026-06-26 as stated in RLT masterplan.
RECON_OVERRIDES: dict[int, date] = {
    2020: date(2020, 6, 26),
    2021: date(2021, 6, 25),
    2022: date(2022, 6, 24),
    2023: date(2023, 6, 23),
    2024: date(2024, 6, 28),
    2025: date(2025, 6, 27),
    2026: date(2026, 6, 26),  # operator-specified seed (RLT masterplan)
}

# ── Internal helpers ─────────────────────────────────────────────────────────


def _last_session_of_month(year: int, month: int) -> date:
    """Last NYSE session on or before the final calendar day of (year, month)."""
    if month == 12:
        last_cal = date(year, 12, 31)
    else:
        last_cal = date(year, month + 1, 1) - timedelta(days=1)
    return last_session_on_or_before(last_cal)


def _last_friday_of_june(year: int) -> date:
    """Last Friday of June for `year`."""
    # Walk back from June 30
    d = date(year, 6, 30)
    while d.weekday() != 4:  # 4 = Friday
        d -= timedelta(days=1)
    return d


# ── Public calendar builders ─────────────────────────────────────────────────


def quarter_end_sessions(y0: int, y1: int) -> list[date]:
    """Last NYSE session of Mar/Jun/Sep/Dec for years y0..y1 inclusive."""
    result = []
    for y in range(y0, y1 + 1):
        for m in QUARTER_MONTHS:
            result.append(_last_session_of_month(y, m))
    return sorted(set(result))


def russell_recon_sessions(y0: int, y1: int) -> list[date]:
    """Russell reconstitution trade dates (rank effective = next day) for y0..y1.

    Rule: last Friday of June, adjusted back to the nearest session if closed.
    RECON_OVERRIDES dict wins when a year is present.
    """
    result = []
    for y in range(y0, y1 + 1):
        if y in RECON_OVERRIDES:
            d = RECON_OVERRIDES[y]
        else:
            fri = _last_friday_of_june(y)
            d = last_session_on_or_before(fri)
        result.append(d)
    return sorted(set(result))


def sp_rebalance_sessions(index: "pd.DatetimeIndex | list") -> list[date]:
    """S&P quarterly rebalance sessions = quad-witching 3rd-Fridays of Mar/Jun/Sep/Dec.

    Reuses engine.opex.expiration_days — does not duplicate the math.
    Returns only quad-witching days (is_quad=True) as a sorted list of dates.
    """
    import pandas as pd
    from engine.opex import expiration_days  # noqa: PLC0415 — late import avoids circulars

    idx = pd.DatetimeIndex(sorted(set(index)))
    exp = expiration_days(idx)
    # expiration_days returns a Series where the value is is_quad
    quads = [ts.date() for ts, is_quad in exp.items() if is_quad]
    return sorted(quads)


def month_end_sessions(y0: int, y1: int) -> list[date]:
    """Last NYSE session of every calendar month for y0..y1 inclusive."""
    result = []
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            result.append(_last_session_of_month(y, m))
    return sorted(set(result))


# ── Tagger ───────────────────────────────────────────────────────────────────


def _count_sessions_between(d_from: date, d_to: date) -> int:
    """Count NYSE sessions strictly between d_from and d_to (exclusive both ends),
    signed: positive when d_to is after d_from."""
    if d_from == d_to:
        return 0
    sign = 1 if d_to > d_from else -1
    lo, hi = (d_from, d_to) if d_to > d_from else (d_to, d_from)
    n = 0
    cur = lo + timedelta(days=1)
    while cur < hi:
        if is_session(cur):
            n += 1
        cur += timedelta(days=1)
    return sign * n


def _signed_td(d: date, ref: date) -> int:
    """Signed trading-day distance from d to ref.

    Convention: positive = ref is in the FUTURE (d is before ref),
                negative = ref is in the PAST (d is after ref),
                zero     = same day.
    """
    if d == ref:
        return 0
    # Count sessions between d and ref, with sign
    if ref > d:
        n = 0
        cur = d + timedelta(days=1)
        while cur <= ref:
            if is_session(cur):
                n += 1
            cur += timedelta(days=1)
        return n
    else:
        n = 0
        cur = ref + timedelta(days=1)
        while cur <= d:
            if is_session(cur):
                n += 1
            cur += timedelta(days=1)
        return -n


def tag(d: date) -> dict[str, Any]:
    """Tag one NYSE session date with rebalance-calendar flags.

    Calling this once per date is fine; for bulk use build lookup tables instead.
    `d` need not be a trading day; non-sessions get td_to_quarter_end relative
    to the surrounding sessions.

    Returns
    -------
    dict with keys:
      is_quarter_end (bool)
      td_to_quarter_end (int)  positive = days until, negative = days since
      in_qtr_end_window (bool) |td| <= 3
      is_russell_recon_session (bool)
      in_recon_week (bool)
      is_sp_rebalance_session (bool)
      is_month_end_session (bool)
    """
    y = d.year

    # ── Quarter-end ──────────────────────────────────────────────────────────
    qe_set = set(quarter_end_sessions(y - 1, y + 1))
    is_qe = d in qe_set

    # nearest quarter-end in either direction (symmetric +/- window)
    future_qes = sorted(q for q in qe_set if q > d)
    past_qes = sorted((q for q in qe_set if q < d), reverse=True)
    if is_qe:
        td_to_qe = 0
    else:
        candidates = []
        if future_qes:
            candidates.append(_signed_td(d, future_qes[0]))   # positive
        if past_qes:
            candidates.append(_signed_td(d, past_qes[0]))     # negative
        td_to_qe = min(candidates, key=abs) if candidates else 999

    in_qe_window = abs(td_to_qe) <= 3

    # ── Russell recon ────────────────────────────────────────────────────────
    recon_set = set(russell_recon_sessions(y - 1, y + 1))
    is_recon = d in recon_set

    # in_recon_week: any session in the same ISO week as any recon day
    d_iso = d.isocalendar()[:2]  # (year, week)
    in_recon_week = any(r.isocalendar()[:2] == d_iso for r in recon_set)

    # ── S&P rebalance (quad-witching) ────────────────────────────────────────
    # Build a small index around d to keep sp_rebalance_sessions fast
    import pandas as pd
    window_start = date(y, 1, 1)
    window_end = date(y, 12, 31)
    idx = pd.bdate_range(start=window_start, end=window_end)
    sp_set = set(sp_rebalance_sessions(idx))
    is_sp = d in sp_set

    # ── Month-end ────────────────────────────────────────────────────────────
    me_set = set(month_end_sessions(y, y))
    is_me = d in me_set

    return {
        "is_quarter_end": is_qe,
        "td_to_quarter_end": td_to_qe,
        "in_qtr_end_window": in_qe_window,
        "is_russell_recon_session": is_recon,
        "in_recon_week": in_recon_week,
        "is_sp_rebalance_session": is_sp,
        "is_month_end_session": is_me,
    }


def build_tag_frame(sessions: list[date]) -> "pd.DataFrame":
    """Build a DataFrame of calendar tags for a list of session dates.

    More efficient than calling tag() per date: builds lookup tables once.
    """
    import pandas as pd

    if not sessions:
        cols = [
            "is_quarter_end", "td_to_quarter_end", "in_qtr_end_window",
            "is_russell_recon_session", "in_recon_week",
            "is_sp_rebalance_session", "is_month_end_session",
        ]
        return pd.DataFrame(columns=cols)

    y0 = min(s.year for s in sessions)
    y1 = max(s.year for s in sessions)

    qe_set = set(quarter_end_sessions(y0 - 1, y1 + 1))
    recon_set = set(russell_recon_sessions(y0 - 1, y1 + 1))
    me_set = set(month_end_sessions(y0, y1))

    # Build SP set from the full session index
    idx = pd.DatetimeIndex([pd.Timestamp(s) for s in sessions])
    sp_set = set(sp_rebalance_sessions(idx))

    # Recon-week set: all ISO (year, week) pairs of recon days
    recon_iso_weeks = {r.isocalendar()[:2] for r in recon_set}

    rows = []
    for s in sessions:
        is_qe = s in qe_set
        # Signed td to NEAREST quarter-end (symmetric +/- window)
        future_qes = sorted(q for q in qe_set if q > s)
        past_qes = sorted((q for q in qe_set if q < s), reverse=True)
        if is_qe:
            td_qe = 0
        else:
            candidates = []
            if future_qes:
                candidates.append(_signed_td(s, future_qes[0]))   # positive
            if past_qes:
                candidates.append(_signed_td(s, past_qes[0]))     # negative
            td_qe = min(candidates, key=abs) if candidates else 999

        rows.append({
            "date": s,
            "is_quarter_end": is_qe,
            "td_to_quarter_end": td_qe,
            "in_qtr_end_window": abs(td_qe) <= 3,
            "is_russell_recon_session": s in recon_set,
            "in_recon_week": s.isocalendar()[:2] in recon_iso_weeks,
            "is_sp_rebalance_session": s in sp_set,
            "is_month_end_session": s in me_set,
        })

    df = pd.DataFrame(rows).set_index("date")
    return df
