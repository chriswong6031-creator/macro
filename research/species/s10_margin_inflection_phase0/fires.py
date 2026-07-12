"""S10 Margin-Inflection Reclaim Phase-0 — fire detection.

Implements EXACTLY the construction registered in W5_S10_PREREG.md.

Two variants (the registered 2-trial grid):
  trial 1: gross margin = gross_profit / revenue
  trial 2: operating margin = op_income / revenue

Fire logic (PIT-clean):
  1. For each (ticker, turn-quarter q3): direction-change predicate holds.
  2. Fire date = first trading day d >= filed(q3), within 63-td window,
     where BOTH washout_ctx AND price_reclaim hold.
  3. One fire per (ticker, turn-quarter). Entry fill = next bar after d.

PIT discipline: filter EDGAR to filed <= eval-date BEFORE computing any margin.
K5 assertion: every fire satisfies filed(q3) <= fire_date.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

# Registered window constants
FIRE_WINDOW_TD  = 63   # trading-day window after filed(q3) to search for a fire
RECLAIM_LOOKBACK = 63  # trailing trading days for the washout-trough low
RECLAIM_PCT     = 1.05 # price >= 1.05 × trailing 63-td min

# Era: fires from 2010-01-01 onward (sector exclusions may push first practical fire later)
ERA_START = pd.Timestamp("2010-01-01")


# ── Margin helpers ────────────────────────────────────────────────────────

def _gross_margin(row: pd.Series) -> float | None:
    rev = row.get("revenue")
    gp  = row.get("gross_profit")
    if rev is None or gp is None or pd.isna(rev) or pd.isna(gp):
        return None
    if float(rev) <= 0:
        return None
    return float(gp) / float(rev)


def _op_margin(row: pd.Series) -> float | None:
    rev = row.get("revenue")
    oi  = row.get("op_income")
    if rev is None or oi is None or pd.isna(rev) or pd.isna(oi):
        return None
    if float(rev) <= 0:
        return None
    return float(oi) / float(rev)


MARGIN_FNS = {
    "gross":     _gross_margin,
    "operating": _op_margin,
}


# ── Direction-change predicate ────────────────────────────────────────────

def _direction_change(margins: list[float]) -> bool:
    """Return True iff the last 4 margins satisfy the direction-change predicate.

    q0=margins[-4], q1=margins[-3], q2=margins[-2], q3=margins[-1]
    Requires:
      m(q1) - m(q0) < 0   AND   m(q2) - m(q1) < 0   (>=2 quarters deterioration)
      m(q3) - m(q2) > 0                               (first improvement)

    STRICT sign predicate — no threshold searched.
    Returns False if fewer than 4 values available.
    """
    if len(margins) < 4:
        return False
    q0, q1, q2, q3 = margins[-4], margins[-3], margins[-2], margins[-1]
    return (q1 - q0 < 0) and (q2 - q1 < 0) and (q3 - q2 > 0)


def _direction_flat_or_down(margins: list[float]) -> bool:
    """Return True iff last 4 margins satisfy the comparator predicate.

    Comparator: margin NOT turning at q3.
    m(q3) - m(q2) <= 0, with q2 present (4 quarters required).
    """
    if len(margins) < 4:
        return False
    q2, q3 = margins[-2], margins[-1]
    return (q3 - q2) <= 0


# ── Price-reclaim condition ────────────────────────────────────────────────

def _reclaim_ok(close_series: pd.Series, eval_date: pd.Timestamp) -> bool:
    """True iff close_t >= 1.05 × min(close over trailing 63 trading days).

    close_series: full price series, already sliced to <= eval_date at call site.
    eval_date: the candidate fire date d.
    """
    # Locate eval_date position
    pos = close_series.index.searchsorted(eval_date, side="right") - 1
    if pos < 0:
        return False
    close_t = float(close_series.iloc[pos])
    if not np.isfinite(close_t) or close_t <= 0:
        return False
    start = max(0, pos - RECLAIM_LOOKBACK + 1)
    window = close_series.iloc[start: pos + 1]
    if window.empty:
        return False
    trough = float(window.min())
    if trough <= 0:
        return False
    return close_t >= RECLAIM_PCT * trough


# ── Washout arming ────────────────────────────────────────────────────────

def _washout_at(close_series: pd.Series, eval_date: pd.Timestamp) -> bool | None:
    """Call engine.coiled.washout_ctx on close_series sliced to eval_date.

    Returns True/False/None.
    """
    try:
        from engine.coiled import washout_ctx
        sliced = close_series[close_series.index <= eval_date]
        return washout_ctx(sliced)
    except Exception as exc:
        log.debug("washout_ctx error for eval_date=%s: %s", eval_date, exc)
        return None


# ── Calendar helpers ──────────────────────────────────────────────────────

def _trading_days_after(start_date: pd.Timestamp, price_index: pd.DatetimeIndex,
                         window: int = FIRE_WINDOW_TD) -> list[pd.Timestamp]:
    """Return the next `window` trading days on price_index on/after start_date."""
    pos = price_index.searchsorted(start_date, side="left")
    end = min(pos + window, len(price_index))
    return list(price_index[pos:end])


# ── Per-ticker fire detection ─────────────────────────────────────────────

def detect_fires_for_ticker(
    ticker: str,
    edgar_ticker: pd.DataFrame,
    close_series: pd.Series,
    margin_type: Literal["gross", "operating"],
    is_comparator: bool = False,
) -> list[dict]:
    """Detect all fires for one ticker under one margin variant.

    edgar_ticker: rows for this ticker from statements_quarterly,
                  already filtered to the ticker.
    close_series: full price series (DatetimeIndex, dividend-adjusted close).
    margin_type: 'gross' or 'operating'.
    is_comparator: if True, use the comparator predicate (NOT turning).

    Returns list of fire-event dicts.
    """
    margin_fn = MARGIN_FNS[margin_type]

    if edgar_ticker.empty or close_series is None or close_series.empty:
        return []

    close_clean = close_series.dropna().sort_index()
    if len(close_clean) < 308:  # washout_ctx minimum
        return []

    # Sort by period_end for rolling window
    et = edgar_ticker.sort_values("period_end").copy()

    # We iterate over each possible q3 position in the EDGAR rows.
    # PIT discipline: at each candidate q3, we restrict the EDGAR slice
    # to rows where filed <= eval_date.

    # Build list of (period_end, filed, margin_value) from the full series.
    # Note: we do NOT filter by eval_date here — we use the FULL ticker history
    # to enumerate candidate q3s, then enforce PIT in the fire-window loop.
    margin_col: list[tuple] = []  # (period_end, filed, margin_val)
    for _, row in et.iterrows():
        m = margin_fn(row)
        if m is not None and np.isfinite(m):
            margin_col.append((row["period_end"], row["filed"], m))

    if len(margin_col) < 4:
        return []

    fired_turns: set = set()  # (ticker, period_end_of_q3) — one fire per turn-quarter
    fires = []

    # Slide a 4-quarter window over all consecutive quarters
    for i in range(3, len(margin_col)):
        q0_end, q0_filed, m0 = margin_col[i - 3]
        q1_end, q1_filed, m1 = margin_col[i - 2]
        q2_end, q2_filed, m2 = margin_col[i - 1]
        q3_end, q3_filed, m3 = margin_col[i]

        margins = [m0, m1, m2, m3]

        if is_comparator:
            if not _direction_flat_or_down(margins):
                continue
        else:
            if not _direction_change(margins):
                continue

        # Era filter: q3_filed must be within era
        if q3_filed < ERA_START:
            continue

        turn_key = (ticker, q3_end)
        if turn_key in fired_turns:
            continue

        # Fire-window search: first trading day d in [q3_filed, q3_filed + 63 td)
        # where BOTH washout AND reclaim hold.
        candidates = _trading_days_after(q3_filed, close_clean.index, FIRE_WINDOW_TD)
        if not candidates:
            continue

        fire_date = None
        for d in candidates:
            # K5: must satisfy d >= q3_filed
            if d < q3_filed:
                continue

            # PIT check: at date d, q3 must have been filed
            if q3_filed > d:
                continue

            # Washout arming (series sliced to d)
            wash = _washout_at(close_clean, d)
            if wash is not True:
                continue

            # Price reclaim (series sliced to d)
            if not _reclaim_ok(close_clean, d):
                continue

            fire_date = d
            break

        if fire_date is None:
            continue

        # K5 assertion: filed(q3) <= fire_date
        assert q3_filed <= fire_date, (
            f"K5 VIOLATION: {ticker} q3_filed={q3_filed.date()} > fire_date={fire_date.date()}"
        )

        # Entry fill = next bar strictly after fire_date
        fill_pos = close_clean.index.searchsorted(fire_date, side="right")
        if fill_pos >= len(close_clean):
            continue
        fill_date = close_clean.index[fill_pos]
        fill_px   = float(close_clean.iloc[fill_pos])

        # K5 assertion: fill_date > fire_date
        assert fill_date > fire_date, (
            f"K5 VIOLATION: fill_date={fill_date.date()} not > fire_date={fire_date.date()}"
        )

        fired_turns.add(turn_key)

        fires.append({
            "ticker":        ticker,
            "margin_type":   margin_type,
            "is_comparator": is_comparator,
            "q3_end":        q3_end,
            "q3_filed":      q3_filed,
            "fire_date":     fire_date,
            "fill_date":     fill_date,
            "fill_px":       fill_px,
            "m0":            m0,
            "m1":            m1,
            "m2":            m2,
            "m3":            m3,
        })

    return fires


# ── Comparator construction ───────────────────────────────────────────────

def detect_comparator_fires_for_ticker(
    ticker: str,
    edgar_ticker: pd.DataFrame,
    close_series: pd.Series,
    margin_type: Literal["gross", "operating"],
) -> list[dict]:
    """Disjoint comparator: washout+reclaim events where margin is NOT turning.

    Identical construction (same universe, era, 63-day window, next-bar fill)
    but uses _direction_flat_or_down instead of _direction_change.
    A fire is in the comparator iff: m(q3) - m(q2) <= 0 AND q2 present AND
    washout AND reclaim both hold in the 63-day window.
    """
    return detect_fires_for_ticker(
        ticker=ticker,
        edgar_ticker=edgar_ticker,
        close_series=close_series,
        margin_type=margin_type,
        is_comparator=True,
    )
