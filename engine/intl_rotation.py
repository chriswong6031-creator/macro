"""engine/intl_rotation.py
=========================
Display-tier port of the China #2634 fast re-rank for the 7 configured
international markets.

Entry point
-----------
    rank(closes, bench, states) -> list[dict]

Returns the rank list, best first. Each dict:
    cc          str
    rank        int   1-based
    score       float
    rs20_pct    float | None   (None when bench is None — uses absolute mom)
    rs5_pct     float | None
    gov         float          state governor multiplier
    ob_penalty  float
    note_en     str | None
    note_zh     str | None

Scoring (frozen per ITR spec):
  - rs20/rs10/rs5 = 20/10/5-session pct change of px/bench ratio * 100
  - when bench is None, use absolute momentum of the price series itself
  - raw = 0.5*rs20 + 0.3*rs10 + 0.2*rs5
  - gov by state: crash/breaking → 0.25, topping → 0.5, downtrend → 0.6, else → 1.0
  - ob_penalty = max(0, ext_pctile - 90) * 0.4 when state ∈ {parabolic, extended,
    topping} and ext_pctile is not None, else 0
  - macd_penalty = 3.0 when macd_cross_date is within 10 sessions AND macd_state ==
    'bear' AND state ∈ {parabolic, extended, topping}, else 0
  - score = gov * raw - ob_penalty - macd_penalty
  - sort descending → rank

NO macro gate (INTL-50 lesson: the uniform macro gate harmed Korea).

DISPLAY-ONLY — not scored into regime, not used in any authority/gate/size signal.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State governor multipliers
# ---------------------------------------------------------------------------
_GOV: dict[str, float] = {
    "crash":     0.25,
    "breaking":  0.25,
    "topping":   0.50,
    "downtrend": 0.60,
}
_GOV_DEFAULT = 1.0

# States where the overbought penalty and MACD penalty are active
_OB_STATES = frozenset({"parabolic", "extended", "topping"})

# MACD penalty magnitude (fixed, per spec)
_MACD_PENALTY = 3.0

# Plain-word notes (one short phrase when gov < 1 or ob_penalty > 0)
_NOTE_GOV: dict[str, tuple[str, str]] = {
    "crash":     ("held back — crash in progress",  "受压制 — 崩跌进行中"),
    "breaking":  ("held back — breaking down",      "受压制 — 正在破位"),
    "topping":   ("held back — turn risk",          "受压制 — 拐点风险"),
    "downtrend": ("held back — downtrend",          "受压制 — 下行趋势"),
}
_NOTE_OB_EN = "overheated — rank capped"
_NOTE_OB_ZH = "过热 — 排名受限"


def _pct_change_n(s: pd.Series, n: int) -> float | None:
    """n-session pct change * 100 from the last value; None when not enough data."""
    s = s.dropna()
    if len(s) <= n:
        return None
    return float((s.iloc[-1] / s.iloc[-1 - n] - 1.0) * 100.0)


def _rs_or_abs(px: pd.Series, bench: pd.Series | None, n: int) -> float | None:
    """n-session pct change of px/bench ratio * 100, or absolute px mom when bench is None."""
    if bench is None:
        return _pct_change_n(px, n)
    px = px.dropna()
    bench = bench.dropna()
    if px.empty or bench.empty:
        return None
    common = px.index.intersection(bench.index)
    if len(common) <= n:
        return None
    ratio = px.reindex(common).ffill() / bench.reindex(common).ffill()
    return _pct_change_n(ratio.dropna(), n)


def _macd_cross_within(macd_cross_date: str | None, last_date: date, n_sessions: int,
                       closes_index: pd.DatetimeIndex) -> bool:
    """Return True when macd_cross_date is within n_sessions trading days of last_date."""
    if macd_cross_date is None:
        return False
    try:
        cross_dt = pd.Timestamp(macd_cross_date).date()
    except Exception:  # noqa: BLE001
        return False
    if cross_dt > last_date:
        return False
    # Count only trading days that exist in the closes index after the cross date
    after_cross = closes_index[closes_index.date >= cross_dt]  # type: ignore[attr-defined]
    return len(after_cross) <= n_sessions


def rank(
    closes: dict[str, pd.Series],
    bench: pd.Series | None,
    states: dict[str, dict],
) -> list[dict]:
    """Score and rank the configured countries.

    Parameters
    ----------
    closes:
        Mapping cc -> price series (the primary index series for each country).
    bench:
        Fresh benchmark series (SPY or ^GSPC, already staleness-checked by the
        caller).  None → absolute momentum used instead of relative strength.
    states:
        Per-country dict from intl_market_state.market_states() — used for the
        governor, overbought-penalty, and MACD-penalty inputs.

    Returns
    -------
    list[dict] sorted descending by score (best rank first).
    """
    rows: list[dict] = []

    for cc, px in closes.items():
        px = px.dropna()
        if len(px) < 6:
            continue

        st = states.get(cc) or {}
        state = st.get("state") or "calm"
        ext_pctile = st.get("ext_pctile")
        macd_cross_date = st.get("macd_cross_date")
        macd_state = st.get("macd_state")
        last_date = px.index[-1].date() if not px.empty else date.today()

        # --- relative-strength or absolute momentum ---
        rs20 = _rs_or_abs(px, bench, 20)
        rs10 = _rs_or_abs(px, bench, 10)
        rs5  = _rs_or_abs(px, bench, 5)

        # Degrade gracefully if some windows unavailable
        rs20 = rs20 or 0.0
        rs10 = rs10 or 0.0
        rs5  = rs5  or 0.0

        raw = 0.5 * rs20 + 0.3 * rs10 + 0.2 * rs5

        # --- state governor ---
        gov = _GOV.get(state, _GOV_DEFAULT)

        # --- overbought penalty ---
        ob_penalty = 0.0
        if state in _OB_STATES and ext_pctile is not None:
            ob_penalty = max(0.0, float(ext_pctile) - 90.0) * 0.4

        # --- MACD penalty ---
        macd_penalty = 0.0
        if (state in _OB_STATES
                and macd_state == "bear"
                and macd_cross_date is not None):
            # Use the closes index for session counting
            closes_idx = px.index.normalize() if hasattr(px.index, "normalize") else px.index
            if _macd_cross_within(macd_cross_date, last_date, 10, closes_idx):
                macd_penalty = _MACD_PENALTY

        score = gov * raw - ob_penalty - macd_penalty

        # --- plain-word note ---
        note_en: str | None = None
        note_zh: str | None = None
        if gov < 1.0 and state in _NOTE_GOV:
            note_en, note_zh = _NOTE_GOV[state]
        if ob_penalty > 0:
            note_en = _NOTE_OB_EN
            note_zh = _NOTE_OB_ZH

        rows.append({
            "cc": cc,
            "score": round(score, 3),
            "rs20_pct": round(rs20, 2) if bench is not None else None,
            "rs5_pct":  round(rs5,  2) if bench is not None else None,
            "gov": gov,
            "ob_penalty": round(ob_penalty, 3),
            "note_en": note_en,
            "note_zh": note_zh,
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    return rows
