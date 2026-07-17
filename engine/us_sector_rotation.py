"""
engine/us_sector_rotation.py
=============================
Display-tier fast rotation score for the 11 SPDR sector ETFs and the named US
thematic baskets on the sector_central board.

Ported from engine/china_sector_rotation.py (#2634), adapted for the US universe
under XSR-R2.  Key adaptations:

1. Benchmark: SPY from data/yahoo store (via engine.inputs.yahoo_closes).
2. Universe: 11 SPDR ETFs + named baskets from data/baskets/membership.json.
3. Anti-aggregate-poisoning OB term: OB penalty = max(ob_of_etf,
   ob_of_ew_member_composite), so a sector whose cap-weights corrected (JNJ/LLY
   in XLV) cannot mask mid-cap strength.  For the fast-RS legs, EW composite
   closes are used where member data is available (ETF is fallback).
4. Cycle/timing states: read from data/sector_cycles/forward_log.parquet
   (column: timing_state).  Mapping documented in _STATE_GOVS below.
5. `today` NameError in source fixed: use series.index[-1] as data-anchored
   weekly cutoff (same logic as the monthly branch in the source).
6. Forward ledger appender gates on COLLECT_LANE=nightly (canonical
   ledger_lane_armed idiom from engine/ignition_audit.py, #2693).
7. Output: per-instrument rows returned as list[dict] + JSON writer to
   data/us_sector_rotation/latest.json.

DISPLAY-ONLY — re-orders display surfaces; feeds no gate, size, score, or
calibrated key.  Never raises on data absence — missing series degrade
gracefully with stale_flags.

Entry point
-----------
    score_and_rank(records, closes, bench, states) -> list[dict]

    Records is a list of dicts with at least: key, kind, ticker, basket_id,
    name.  The function returns the list sorted ascending by rotation_rank
    (rank 1 = strongest).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timezone, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from engine.canon import rsi, stoch_rsi_kd
from engine.htf_durability import _biweekly_close
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MODULE-LEVEL CONSTANTS
# ---------------------------------------------------------------------------

# 11 SPDR sector ETFs — the core of the US board
SPDR_ETFS: list[str] = [
    "XLK", "XLV", "XLP", "XLU", "XLF",
    "XLE", "XLI", "XLY", "XLB", "XLRE", "XLC",
]

# Benchmark ticker (yahoo store)
BENCH: str = "SPY"

# Granularity (homogeneity) weight — same concept as China:
# Narrow = single-theme (concentrated oscillator signals, full trust).
# Broad = mixed-basket (diffuse, discount).
# Default for anything not hand-tagged.
NARROW_SECTORS: frozenset[str] = frozenset({
    "XLE",    # Energy — concentrated commodity-price sector
    "XLRE",   # Real Estate — single REIT theme
    "XLU",    # Utilities — single regulated-utility theme
    "XLB",    # Materials — mining/chemicals concentration
})
BROAD_SECTORS: frozenset[str] = frozenset({
    "XLK",    # Technology — wide sub-theme mix
    "XLF",    # Financials — banks + insurance + real-estate finance
    "XLI",    # Industrials — defense + transport + capital goods
    "XLY",    # Consumer Discretionary — retail + autos + hotels
})
GRANULARITY_NARROW: float = 1.0
GRANULARITY_BROAD: float = 0.4
GRANULARITY_DEFAULT: float = 0.7

# OB penalty cap — maximum point deduction
OB_MAX_PENALTY: float = 25.0

# MACD cross demotion (1W and 2W bearish cross)
CROSS_DEMOTE_1W: float = 12.0
CROSS_DEMOTE_2W: float = 18.0

# When fast-RS contradicts a bearish cross (mom10 > 0), attenuate demotion
CROSS_CONTRADICTED_MULT: float = 0.25

# Rotation score weights — faithful port from China
SCORE_MOM20_W: float = 1.0
SCORE_MOM10_W: float = 0.4
SCORE_MOM5_W: float = 0.6

# Minimum bar counts
MIN_BARS_BIWEEKLY_RSI: int = 20
MIN_BARS_MONTHLY_RSI: int = 20
MIN_BARS_TF_STATE: int = 40
MIN_BARS_MOM5: int = 7
MIN_BARS_MOM10: int = 12

# Fast-momentum gate for unconfirmed states.
# A 1-week pop inside bearish cycle states is likely a dead-cat bounce — attenuate.
FAST_UNCONFIRMED_MULT: float = 0.3

# States where positive fast_bonus is taken at face value
_FAST_CONFIRMED_STATES: frozenset[str] = frozenset({
    "FRESH BUY",
    "TURN SIGNALED",
    "RALLY ON",
})

# ---------------------------------------------------------------------------
# State-governor lookup table
# ---------------------------------------------------------------------------
# Keys MUST match the exact strings in data/sector_cycles/forward_log.parquet
# (column: timing_state).  Verified against the forward_log unique values:
# BOTTOM WATCH, COUNTERTREND BOUNCE, TURN SIGNALED, RALLY ON, TOP WATCH,
# DECLINE, ROLLING OVER, FRESH BUY  (8 states; no CONFIRMING TURN in US log).
#
# CONFIRMING TURN is defined for completeness — if the US log ever emits it,
# the mapping matches China's rationale (+1: turn in progress > confirmed-bearish).
#
# Adjustment range mirrors China exactly (−8 to +8) so scoring is comparable.
_STATE_GOVS: dict[str, int] = {
    "FRESH BUY":            +8,    # cycle confirmed-buy, highest conviction up
    "TURN SIGNALED":        +5,    # momentum turn, unconfirmed but directional
    "CONFIRMING TURN":      +1,    # daily bottom in weekly-bearish regime (see China note)
    "BOTTOM WATCH":         +2,    # near cycle low, pre-turn, mild positive
    "RALLY ON":             +3,    # uptrend in progress
    "TOP WATCH":            -5,    # topping process starting
    "COUNTERTREND BOUNCE":  -4,    # bear-market rally, do not trust
    "ROLLING OVER":         -7,    # trend deteriorating
    "DECLINE":              -8,    # confirmed downtrend, strongest bearish signal
}

# ---------------------------------------------------------------------------
# Ledger-lane gate (canonical from engine/ignition_audit.py, #2693)
# ---------------------------------------------------------------------------

def _ledger_lane_armed() -> bool:
    """True only when running on a nightly ledger-advancing lane.

    House law: nightly is the SOLE advancer of forward ledgers.
    Off-lane invocations (render lanes, intraday, re-render) compute scores
    and return but MUST NOT append to the forward log.
    """
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


# ---------------------------------------------------------------------------
# EW member composite close builder
# ---------------------------------------------------------------------------

def _ew_member_close(basket_id: str, membership: dict, stock_closes: pd.DataFrame,
                     idx: pd.DatetimeIndex) -> Optional[pd.Series]:
    """Build an equal-weight close LEVEL series for a basket from its members.

    Uses point-in-time dated membership (a member counts only within
    [added, removed)).  Returns None if fewer than 3 members have data.

    Anti-aggregate-poisoning: this gives us the EW view that is independent
    of cap-weight distortions inside the ETF.
    """
    members = membership.get("baskets", {}).get(basket_id, {}).get("members", [])
    if not members:
        return None

    present = [m["ticker"] for m in members if m["ticker"] in stock_closes.columns]
    if len(present) < 3:
        return None

    rets = stock_closes[present].pct_change()
    mask = pd.DataFrame(False, index=idx, columns=present)
    for m in members:
        t = m["ticker"]
        if t not in present:
            continue
        a = idx >= pd.Timestamp(m["added"])
        if m.get("removed"):
            a = a & (idx < pd.Timestamp(m["removed"]))
        mask[t] = a

    ew = rets.where(mask).mean(axis=1)
    first = ew.first_valid_index()
    if first is None:
        return None

    lvl = pd.Series(np.nan, index=idx)
    lvl.loc[first:] = (1.0 + ew.loc[first:].fillna(0.0)).cumprod()
    return lvl


# ---------------------------------------------------------------------------
# Internal helpers (ported from china_sector_rotation.py)
# ---------------------------------------------------------------------------

def _granularity(ticker: str) -> float:
    """Return h (homogeneity weight) for a sector ETF by ticker."""
    if ticker in NARROW_SECTORS:
        return GRANULARITY_NARROW
    if ticker in BROAD_SECTORS:
        return GRANULARITY_BROAD
    return GRANULARITY_DEFAULT


def _state_adj(state: Optional[str]) -> int:
    """Map a timing_state string to a rotation-score governor (+/- points).

    Case-insensitive lookup against _STATE_GOVS.  Returns 0 for None/empty
    or any unrecognised state (unknown-state fallback is safe — display-tier).
    """
    key = str(state or "").strip().upper()
    return _STATE_GOVS.get(key, 0)


def _sector_oscillators(px: pd.Series) -> dict:
    """Compute overbought oscillator inputs from a price series.

    Returns a dict with keys:
        rsi_2w, rsi_1m, stochk_2w   (float | None)
        macd_x1w, macd_x2w           (bool)
        macd_pos_1w                  (bool | None)
        null_components              (list[str])
    """
    from engine.cycles import _tf_state

    out: dict = {
        "rsi_2w": None,
        "rsi_1m": None,
        "stochk_2w": None,
        "macd_x1w": False,
        "macd_x2w": False,
        "macd_pos_1w": None,
        "null_components": [],
    }

    if px is None or len(px) < 40:
        out["null_components"].append("series_short")
        return out

    px = px.dropna()
    if len(px) < 40:
        out["null_components"].append("series_short_dropna")
        return out

    # Data-anchored cutoff: the last real close in the series
    # (fixes the 'today' NameError present in china_sector_rotation.py)
    series_end = px.index[-1]

    # -- Biweekly (2W) series ------------------------------------------------
    try:
        bw = _biweekly_close(px)
    except Exception as e:
        out["null_components"].append(f"biweekly_err:{e}")
        bw = pd.Series(dtype=float)

    if len(bw) >= MIN_BARS_BIWEEKLY_RSI:
        try:
            r2w = rsi(bw, 14)
            v = r2w.iloc[-1]
            if pd.notna(v):
                out["rsi_2w"] = float(v)
            else:
                out["null_components"].append("rsi_2w_nan")
        except Exception as e:
            out["null_components"].append(f"rsi_2w_err:{e}")
    else:
        out["null_components"].append("biweekly_short")

    if len(bw) >= MIN_BARS_BIWEEKLY_RSI:
        try:
            k_series, _d = stoch_rsi_kd(bw)
            v = k_series.iloc[-1]
            if pd.notna(v):
                out["stochk_2w"] = float(np.clip(v, 0.0, 100.0))
            else:
                out["null_components"].append("stochk_2w_nan")
        except Exception as e:
            out["null_components"].append(f"stochk_err:{e}")

    if len(bw) >= MIN_BARS_TF_STATE:
        try:
            tfs_2w = _tf_state(bw)
            out["macd_x2w"] = bool(tfs_2w.get("macd_cross_dn", False))
        except Exception as e:
            out["null_components"].append(f"tf_2w_err:{e}")
    else:
        out["null_components"].append("biweekly_tf_short")

    # -- Monthly series — drop incomplete trailing month (data-anchored) -----
    try:
        monthly_raw = px.resample("ME").last().dropna()
        if len(monthly_raw) > 0 and monthly_raw.index[-1] > series_end:
            monthly = monthly_raw.iloc[:-1]
        else:
            monthly = monthly_raw
    except Exception as e:
        out["null_components"].append(f"monthly_err:{e}")
        monthly = pd.Series(dtype=float)

    if len(monthly) >= MIN_BARS_MONTHLY_RSI:
        try:
            r1m = rsi(monthly, 14)
            v = r1m.iloc[-1]
            if pd.notna(v):
                out["rsi_1m"] = float(v)
            else:
                out["null_components"].append("rsi_1m_nan")
        except Exception as e:
            out["null_components"].append(f"rsi_1m_err:{e}")
    else:
        out["null_components"].append("monthly_short")

    # -- Weekly series — drop incomplete trailing week (data-anchored) -------
    try:
        weekly_raw = px.resample("W-FRI").last().dropna()
        # Use series_end (last real close) instead of wall-clock today.
        # A W-FRI bar stamped beyond the last real daily close is incomplete.
        if len(weekly_raw) > 0 and weekly_raw.index[-1] > series_end:
            weekly = weekly_raw.iloc[:-1]
        else:
            weekly = weekly_raw
    except Exception as e:
        out["null_components"].append(f"weekly_err:{e}")
        weekly = pd.Series(dtype=float)

    if len(weekly) >= MIN_BARS_TF_STATE:
        try:
            tfs_1w = _tf_state(weekly)
            out["macd_x1w"] = bool(tfs_1w.get("macd_cross_dn", False))
            pos = tfs_1w.get("macd_pos")
            if pos is not None:
                out["macd_pos_1w"] = bool(pos)
        except Exception as e:
            out["null_components"].append(f"tf_1w_err:{e}")
    else:
        out["null_components"].append("weekly_tf_short")

    return out


def _ob_score(osc: dict) -> tuple[float, list[str]]:
    """Composite overbought score [0, 1] from oscillator readings.

    Components:
        ob_rsi2w  = clip((rsi_2w  - 50) / 40, 0, 1)
        ob_rsi1m  = clip((rsi_1m  - 50) / 40, 0, 1)
        ob_stoch  = clip((stochk_2w - 50) / 45, 0, 1)
        ob_macd   = 0.5 if weekly MACD histogram is positive, else 0

    NULL components are excluded from the mean.
    Returns (ob_score, list_of_included_component_names).
    """
    components: list[float] = []
    included: list[str] = []

    r2w = osc.get("rsi_2w")
    if r2w is not None:
        components.append(float(np.clip((r2w - 50.0) / 40.0, 0.0, 1.0)))
        included.append("rsi2w")

    r1m = osc.get("rsi_1m")
    if r1m is not None:
        components.append(float(np.clip((r1m - 50.0) / 40.0, 0.0, 1.0)))
        included.append("rsi1m")

    sk = osc.get("stochk_2w")
    if sk is not None:
        components.append(float(np.clip((sk - 50.0) / 45.0, 0.0, 1.0)))
        included.append("stoch")

    pos = osc.get("macd_pos_1w")
    if pos is not None:
        components.append(0.5 if pos else 0.0)
        included.append("macd_pos")

    ob = float(np.mean(components)) if components else 0.0
    return ob, included


def _ob_score_from_series(px: pd.Series) -> float:
    """Compute OB score [0, 1] from a price series (for EW composite).

    Same as the ETF path but without the MACD-pos component (MACD cross
    detection stays on the ETF as the tradeable instrument).
    """
    try:
        if px is None or len(px) < 40:
            return 0.0
        px = px.dropna()
        if len(px) < 40:
            return 0.0
        series_end = px.index[-1]
        components: list[float] = []

        bw = _biweekly_close(px)
        if len(bw) >= MIN_BARS_BIWEEKLY_RSI:
            r2w = rsi(bw, 14)
            v = r2w.iloc[-1]
            if pd.notna(v):
                components.append(float(np.clip((float(v) - 50.0) / 40.0, 0.0, 1.0)))
            k_series, _ = stoch_rsi_kd(bw)
            v = k_series.iloc[-1]
            if pd.notna(v):
                components.append(float(np.clip((float(np.clip(v, 0.0, 100.0)) - 50.0) / 45.0, 0.0, 1.0)))

        monthly_raw = px.resample("ME").last().dropna()
        if len(monthly_raw) > 0 and monthly_raw.index[-1] > series_end:
            monthly = monthly_raw.iloc[:-1]
        else:
            monthly = monthly_raw
        if len(monthly) >= MIN_BARS_MONTHLY_RSI:
            r1m = rsi(monthly, 14)
            v = r1m.iloc[-1]
            if pd.notna(v):
                components.append(float(np.clip((float(v) - 50.0) / 40.0, 0.0, 1.0)))

        return float(np.mean(components)) if components else 0.0
    except Exception:
        return 0.0


def _fast_rs(px: pd.Series, bench: pd.Series) -> tuple[float, float]:
    """5-day and 10-day relative-strength momentum vs benchmark.

    ratio = px / bench (aligned on common dates)
    momN = ratio.pct_change(N).iloc[-1] * 100

    Returns (mom5, mom10); falls back to 0.0 if data is too short or stale.
    Stale series flag: returns (0.0, 0.0) with stale noted by the caller.
    """
    mom5 = 0.0
    mom10 = 0.0

    if px is None or bench is None:
        return mom5, mom10

    aligned = pd.concat([px, bench], axis=1, sort=False).dropna()
    if aligned.empty:
        return mom5, mom10

    ratio = aligned.iloc[:, 0] / aligned.iloc[:, 1]

    if len(ratio) >= MIN_BARS_MOM5:
        v = ratio.pct_change(5).iloc[-1]
        if pd.notna(v):
            mom5 = float(v * 100)

    if len(ratio) >= MIN_BARS_MOM10:
        v = ratio.pct_change(10).iloc[-1]
        if pd.notna(v):
            mom10 = float(v * 100)

    return mom5, mom10


def _mom20(px: pd.Series, bench: pd.Series) -> float:
    """20-day relative-strength momentum (primary anchor, same as China mom20)."""
    if px is None or bench is None:
        return 0.0
    aligned = pd.concat([px, bench], axis=1, sort=False).dropna()
    if len(aligned) < 22:
        return 0.0
    ratio = aligned.iloc[:, 0] / aligned.iloc[:, 1]
    v = ratio.pct_change(20).iloc[-1]
    return float(v * 100) if pd.notna(v) else 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_and_rank(
    records: list[dict],
    etf_closes: pd.DataFrame,
    bench_series: pd.Series,
    timing_states: dict[str, str],
    stock_closes: Optional[pd.DataFrame] = None,
    membership: Optional[dict] = None,
    asof: Optional[str] = None,
) -> list[dict]:
    """Compute rotation scores and return records sorted by rotation_rank.

    Parameters
    ----------
    records :
        List of instrument dicts with at least:
        key (str), kind ('sector'|'basket'), ticker (str|None),
        basket_id (str|None), name (str).
    etf_closes :
        Wide DataFrame of ETF closes (from yahoo_closes()); must contain all
        SPDR tickers and SPY.
    bench_series :
        SPY close series (pd.Series), aligned to etf_closes.index.
    timing_states :
        Dict mapping id → timing_state string.
        E.g. {'xlv': 'RALLY ON', 'b-us_sector_health': 'RALLY ON'}.
    stock_closes :
        Optional: wide DataFrame of individual stock closes (from
        equity_factors._closes()). Used for EW-member composite OB and fast-RS.
        When None, the ETF is used for all OB and RS terms.
    membership :
        Optional: parsed membership.json dict.  Required to use EW composites.
    asof :
        Optional ISO date string for the forward-log entry timestamp.

    Returns
    -------
    list[dict]
        Each record augmented with rotation fields, sorted ascending by
        rotation_rank (1 = strongest).
    """
    if not records:
        return records

    if asof is None:
        asof = str(bench_series.dropna().index[-1].date()) if bench_series is not None and not bench_series.dropna().empty else str(date.today())

    idx = etf_closes.index if stock_closes is None else stock_closes.index
    if not isinstance(idx, pd.DatetimeIndex):
        idx = pd.DatetimeIndex(idx)

    coverage_log: list[str] = []
    scored: list[dict] = []

    for rec in records:
        key = rec.get("key", "")
        kind = rec.get("kind", "sector")
        ticker = rec.get("ticker") or ""
        basket_id = rec.get("basket_id") or rec.get("id") or ""
        name = rec.get("name", ticker or basket_id)

        stale_flags: list[str] = []

        # ---- Resolve the primary price series (ETF or proxy ticker) --------
        etf_px: Optional[pd.Series] = None
        if ticker and ticker in etf_closes.columns:
            etf_px = etf_closes[ticker].dropna()
            if len(etf_px) < MIN_BARS_MOM10:
                stale_flags.append(f"etf_short({ticker})")
                etf_px = None
        elif ticker:
            stale_flags.append(f"etf_missing({ticker})")

        # ---- Resolve EW member composite close (for OB and fast RS) --------
        ew_px: Optional[pd.Series] = None
        # Map basket_id → membership key
        mem_key = basket_id.replace("b-", "").replace("us_sector_", "us_sector_")
        # Try the direct basket_id with b- prefix stripped
        if stock_closes is not None and membership is not None:
            candidate_keys = [
                basket_id.lstrip("b-") if basket_id.startswith("b-") else basket_id,
                basket_id,
            ]
            for mk in candidate_keys:
                lvl = _ew_member_close(mk, membership, stock_closes, idx)
                if lvl is not None and not lvl.dropna().empty:
                    ew_px = lvl.dropna()
                    break
            if ew_px is None:
                stale_flags.append(f"ew_member_null({basket_id})")

        # ---- Primary close for fast-RS and mom20 ---------------------------
        # Use EW composite when available (anti-poisoning innovation);
        # ETF is fallback.
        primary_px = ew_px if ew_px is not None else etf_px

        # ---- mom20 (primary anchor) ----------------------------------------
        m20 = _mom20(primary_px, bench_series) if primary_px is not None else 0.0

        # ---- Fast RS (5d/10d) from primary px vs SPY -----------------------
        mom5, mom10 = _fast_rs(primary_px, bench_series) if primary_px is not None else (0.0, 0.0)

        # ---- ETF oscillators (OB composite from ETF) -----------------------
        ob_etf = 0.0
        macd_x1w = False
        macd_x2w = False
        osc: dict = {"null_components": []}
        if etf_px is not None and len(etf_px) >= 40:
            osc = _sector_oscillators(etf_px)
            ob_etf, _ = _ob_score(osc)
            macd_x1w = osc["macd_x1w"]
            macd_x2w = osc["macd_x2w"]
        else:
            stale_flags.append("ob_etf_null")
        null_comps = osc.get("null_components", [])
        if null_comps:
            coverage_log.append(f"  {name} ({ticker}): {', '.join(null_comps)}")

        # ---- EW-member OB (anti-JNJ/LLY-poisoning: FIX 3 port) -----------
        # max(ob_etf, ob_ew) so a still-elevated EW composite catches sectors
        # where the ETF has cooled (cap-weight distortion) but members haven't.
        ob_ew = 0.0
        if ew_px is not None and len(ew_px) >= 40:
            ob_ew = _ob_score_from_series(ew_px)
        ob = max(ob_etf, ob_ew)

        # ---- Granularity weight --------------------------------------------
        h = _granularity(ticker) if kind == "sector" else GRANULARITY_DEFAULT

        # ---- Timing-state governor -----------------------------------------
        # Look up by: basket_id (e.g. 'b-us_sector_health'), then by ticker
        # (lowercased, e.g. 'xlv'), then by key.
        state = (
            timing_states.get(basket_id)
            or timing_states.get(basket_id.lstrip("b-"))
            or timing_states.get(key)
            or timing_states.get(ticker.lower() if ticker else "")
            or None
        )
        sadj = _state_adj(state)

        # ---- Fast-momentum gate (dead-cat bounce damping) ------------------
        fast_bonus = SCORE_MOM10_W * mom10 + SCORE_MOM5_W * mom5
        state_upper = str(state or "").strip().upper()
        if fast_bonus > 0 and state_upper not in _FAST_CONFIRMED_STATES:
            fast_bonus *= FAST_UNCONFIRMED_MULT

        # ---- OB demotion ---------------------------------------------------
        ob_demote = ob * OB_MAX_PENALTY * h

        # ---- MACD cross demotion (gated by fast RS) -----------------------
        base_cross = (
            (CROSS_DEMOTE_1W if macd_x1w else 0.0)
            + (CROSS_DEMOTE_2W if macd_x2w else 0.0)
        )
        if base_cross > 0:
            cross_demote = base_cross * CROSS_CONTRADICTED_MULT if mom10 > 0 else base_cross
        else:
            cross_demote = 0.0

        # ---- Rotation score ------------------------------------------------
        rotation_score = (
            SCORE_MOM20_W * m20
            + fast_bonus
            + sadj
            - ob_demote
            - cross_demote
        )

        new_rec = dict(rec)
        new_rec.update({
            "rotation_score":   round(rotation_score, 1),
            "rank":             None,          # filled after sorting
            "rotation_rank":    None,
            "components": {
                "mom20":         round(m20, 2),
                "fast_rs":       round(fast_bonus, 2),
                "mom5_raw":      round(mom5, 2),
                "mom10_raw":     round(mom10, 2),
                "governor":      sadj,
                "ob_penalty":    round(ob_demote, 2),
                "macd_demotion": round(cross_demote, 1),
            },
            "state_used":       state,
            "ob_etf":           round(ob_etf, 3),
            "ob_ew":            round(ob_ew, 3),
            "ob":               round(ob, 3),
            "macd_x1w":         macd_x1w,
            "macd_x2w":         macd_x2w,
            "stale_flags":      stale_flags,
            "asof":             asof,
        })
        scored.append(new_rec)

    if coverage_log:
        log.debug(
            "us_sector_rotation oscillator coverage — null components:\n%s",
            "\n".join(coverage_log),
        )

    # Stable sort: rotation_score DESC, mom20 DESC as tiebreaker
    scored.sort(
        key=lambda c: (
            -(c["rotation_score"] or 0.0),
            -(c["components"]["mom20"] or 0.0),
        )
    )

    for i, c in enumerate(scored, 1):
        c["rotation_rank"] = i
        c["rank"] = i

    return scored


# ---------------------------------------------------------------------------
# Convenience loader — build inputs from the live data stores
# ---------------------------------------------------------------------------

def load_inputs(asof: Optional[str] = None) -> tuple[
    list[dict],           # records
    pd.DataFrame,         # etf_closes
    pd.Series,            # bench_series (SPY)
    dict[str, str],       # timing_states
    Optional[pd.DataFrame],  # stock_closes
    Optional[dict],          # membership
]:
    """Load all inputs needed to call score_and_rank from live data stores.

    asof: optional ISO date string to slice closes up to that date (for replay).
    """
    from engine.inputs import yahoo_closes
    from engine.equity_factors import _closes as stock_closes_fn

    # ---- ETF closes --------------------------------------------------------
    etf_close_df = yahoo_closes()
    if asof:
        etf_close_df = etf_close_df[etf_close_df.index <= pd.Timestamp(asof)]

    bench = etf_close_df["SPY"].dropna() if "SPY" in etf_close_df.columns else pd.Series(dtype=float)

    # ---- Stock closes for EW composites ------------------------------------
    try:
        sc = stock_closes_fn("broad")
        if asof:
            sc = sc[sc.index <= pd.Timestamp(asof)]
    except Exception as e:
        log.warning("us_sector_rotation: stock_closes failed: %s", e)
        sc = None

    # ---- Membership --------------------------------------------------------
    try:
        mem_path = config.data_dir() / "baskets" / "membership.json"
        with open(mem_path) as f:
            membership = json.load(f)
    except Exception as e:
        log.warning("us_sector_rotation: membership.json failed: %s", e)
        membership = None

    # ---- Timing states from forward_log.parquet ---------------------------
    timing_states: dict[str, str] = {}
    try:
        fwd_path = config.data_dir() / "sector_cycles" / "forward_log.parquet"
        fwd = pd.read_parquet(fwd_path)
        fwd["date"] = pd.to_datetime(fwd["date"])
        if asof:
            fwd = fwd[fwd["date"] <= pd.Timestamp(asof)]
        # Keep most-recent row per id
        if not fwd.empty:
            latest_fwd = fwd.sort_values("date").groupby("id").last().reset_index()
            for _, row in latest_fwd.iterrows():
                ts = row.get("timing_state")
                if pd.notna(ts):
                    timing_states[str(row["id"])] = str(ts)
    except Exception as e:
        log.warning("us_sector_rotation: forward_log failed: %s", e)

    # ---- Build records list ------------------------------------------------
    # Sector ETFs come first
    records: list[dict] = []
    sector_id_map = {
        "XLK": ("xlk", "Technology", "b-us_sector_tech"),
        "XLV": ("xlv", "Health Care", "b-us_sector_health"),
        "XLP": ("xlp", "Consumer Staples", "b-us_sector_staples"),
        "XLU": ("xlu", "Utilities", "b-us_sector_utilities"),
        "XLF": ("xlf", "Financials", "b-us_sector_financials"),
        "XLE": ("xle", "Energy", "b-us_sector_energy"),
        "XLI": ("xli", "Industrials", "b-us_sector_industrials"),
        "XLY": ("xly", "Consumer Discretionary", "b-us_sector_discretionary"),
        "XLB": ("xlb", "Materials", "b-us_sector_materials"),
        "XLRE": ("xlre", "Real Estate", "b-us_sector_realestate"),
        "XLC": ("xlc", "Communication Services", "b-us_sector_comm"),
    }
    for etf, (sid, sname, bid) in sector_id_map.items():
        records.append({
            "key":       sid,
            "id":        sid,
            "kind":      "sector",
            "ticker":    etf,
            "basket_id": bid,
            "name":      sname,
        })

    # Named baskets from calls.parquet (kind='basket')
    try:
        calls_path = config.data_dir() / "sector_central" / "calls.parquet"
        calls = pd.read_parquet(calls_path)
        if asof:
            calls = calls[calls["date"] <= asof]
        # Most-recent row per basket id
        basket_calls = calls[calls["kind"] == "basket"].copy()
        if not basket_calls.empty:
            latest_calls = basket_calls.sort_values("date").groupby("id").last().reset_index()
            for _, row in latest_calls.iterrows():
                bid = str(row["id"])
                # Skip the b-us_sector_* entries — those are covered by ETF path
                if "us_sector" in bid:
                    continue
                records.append({
                    "key":       bid,
                    "id":        bid,
                    "kind":      "basket",
                    "ticker":    str(row.get("ticker") or ""),
                    "basket_id": bid,
                    "name":      str(row.get("name") or bid),
                })
    except Exception as e:
        log.warning("us_sector_rotation: calls.parquet failed: %s", e)

    return records, etf_close_df, bench, timing_states, sc, membership


# ---------------------------------------------------------------------------
# Forward-log appender (ledger-gated)
# ---------------------------------------------------------------------------

def _append_forward_log(scored: list[dict], root: Optional[Path] = None) -> int:
    """Append one row per instrument to the forward log.

    Gated on _ledger_lane_armed(): off-lane calls no-op and return 0.
    Idempotent by (asof, key).

    Returns number of rows appended.
    """
    if not _ledger_lane_armed():
        log.debug("us_sector_rotation: forward_log append skipped (not on nightly lane)")
        return 0

    base = config.data_dir() if root is None else (Path(root) / "data")
    log_path = base / "us_sector_rotation" / "forward_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing to deduplicate by (asof, key)
    existing: set[tuple[str, str]] = set()
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            try:
                row = json.loads(line)
                existing.add((row.get("asof", ""), row.get("key", "")))
            except Exception:
                pass

    written = 0
    with open(log_path, "a") as f:
        for rec in scored:
            key = (rec.get("asof", ""), rec.get("key", ""))
            if key in existing:
                continue
            row = {
                "asof":           rec.get("asof"),
                "key":            rec.get("key"),
                "kind":           rec.get("kind"),
                "name":           rec.get("name"),
                "rotation_rank":  rec.get("rotation_rank"),
                "rotation_score": rec.get("rotation_score"),
                "state_used":     rec.get("state_used"),
                "components":     rec.get("components"),
                "stale_flags":    rec.get("stale_flags"),
                "ts":             datetime.now(timezone.utc).isoformat(),
            }
            f.write(json.dumps(row, default=str) + "\n")
            existing.add(key)
            written += 1

    if written:
        log.info("us_sector_rotation: appended %d rows to forward_log.jsonl", written)
    return written


# ---------------------------------------------------------------------------
# JSON writer
# ---------------------------------------------------------------------------

def write_latest(scored: list[dict], root: Optional[Path] = None) -> Path:
    """Write data/us_sector_rotation/latest.json.

    Returns the path written.  Display-tier only — never gates anything.
    """
    base = config.data_dir() if root is None else (Path(root) / "data")
    out_dir = base / "us_sector_rotation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "latest.json"

    payload = {
        "asof":      scored[0]["asof"] if scored else None,
        "ts":        datetime.now(timezone.utc).isoformat(),
        "authority": "DISPLAY-ONLY — re-orders display surfaces; feeds no gate, size, score, or calibrated key.",
        "instruments": scored,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    log.info("us_sector_rotation: wrote %s (%d instruments)", out_path, len(scored))
    return out_path


# ---------------------------------------------------------------------------
# Main compute entry point
# ---------------------------------------------------------------------------

def compute_and_write(asof: Optional[str] = None) -> list[dict]:
    """Load inputs, compute scores, write outputs, return scored list.

    This is the nightly/render entry point.  Off-lane renders write latest.json
    but do not append to the forward ledger.

    asof: optional ISO date string (for replay; if None, uses latest data).
    """
    records, etf_closes, bench, timing_states, stock_closes, membership = load_inputs(asof=asof)

    scored = score_and_rank(
        records=records,
        etf_closes=etf_closes,
        bench_series=bench,
        timing_states=timing_states,
        stock_closes=stock_closes,
        membership=membership,
        asof=asof,
    )

    write_latest(scored)
    _append_forward_log(scored)

    return scored
