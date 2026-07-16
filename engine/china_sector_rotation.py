"""
engine/china_sector_rotation.py
================================
Display-tier rotation re-rank for the 16 China sector ETF cards.

Computes a ``rotation_score`` that blends multi-timeframe relative-strength
momentum, a cycle-state governor, an overbought penalty (max of the sector's
own ETF oscillators AND the corresponding Shenwan index series), and a
MACD-cross demotion that is gated by short-term momentum so a stale bearish
cross does not bury a turning-up sector.

Entry point
-----------
    score_and_rank(cards, closes, bench) -> list[dict]

The returned list is SORTED ascending by rotation_rank (best = 1).
Each card dict gets these new keys added:
    rotation_rank   int   1..N
    rotation_score  float 1dp
    rsi_2w          float | None
    rsi_1m          float | None
    stochk_2w       float | None   already 0-100
    macd_x1w        bool
    macd_x2w        bool
    ob_etf          float 0-1      OB from sector ETF oscillators
    ob_index        float 0-1      OB from Shenwan sector index oscillators
    ob              float 0-1      max(ob_etf, ob_index)
    ob_demote       float
    cross_demote    float
    granularity     float (h)   narrow=1.0, broad=0.4, default=0.7
    mom5            float
    mom10           float
    state_adj       int

DISPLAY-ONLY — not scored into regime, not used in any authority/gate/size signal.

Indicator functions read .iloc[-1] snapshots of causal (non-lookahead) series.
Monthly and weekly resamples drop the incomplete trailing bar so rsi_1m /
weekly-MACD reflect completed periods only.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from engine.canon import rsi, stoch_rsi_kd
from engine.cycles import _tf_state, LADDER
from engine.htf_durability import _biweekly_close
from engine.china_sector_index import SECTOR_SW, sw_close

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MODULE-LEVEL CONSTANTS (tune here, no magic numbers in code below)
# ---------------------------------------------------------------------------

# Granularity (homogeneity) weight — governs how hard overbought readings can
# demote a sector.  Narrow sectors (single-theme ETFs) have concentrated, clean
# oscillator signals → weight = 1.0 (full trust).  Broad basket ETFs have mixed
# constituents → oscillator signals are diffuse → discount to 0.4.
NARROW_SECTORS: frozenset[str] = frozenset({
    "Semiconductors",
    "Innovative Drugs",
    "Baijiu & Liquor",
    "Coal",
    "Defense & Military",
    "Solar & Photovoltaic",
    "Real Estate",
    "Banks",
    "Securities & Brokers",
})
BROAD_SECTORS: frozenset[str] = frozenset({
    "Technology",
    "Healthcare",
    "Consumer Staples",
    "Nonferrous Metals",
    "Automobiles",
    "Media",
    "New-Energy Vehicle",
})
GRANULARITY_NARROW: float = 1.0   # trust oscillators fully — single-theme
GRANULARITY_BROAD: float = 0.4    # discount — mixed-basket noise
GRANULARITY_DEFAULT: float = 0.7  # anything not hand-tagged

# OB penalty cap — maximum point deduction even when OB=1 and h=1.
OB_MAX_PENALTY: float = 25.0

# MACD cross demotion: bearish cross on the 1-week or 2-week timeframe.
# base_cross = 12 pts for 1W cross + 18 pts for 2W cross.
CROSS_DEMOTE_1W: float = 12.0
CROSS_DEMOTE_2W: float = 18.0

# REFINEMENT 1 — if fast-RS momentum CONTRADICTS the cross (mom10 > 0, tape
# still rising), scale back the demotion.  A bearish MACD cross against rising
# 10-day relative-strength is likely stale or a whipsaw — penalising a
# turning-up sector for it is too harsh.  Set to 1.0 to disable gating.
CROSS_CONTRADICTED_MULT: float = 0.25

# Rotation score weights
SCORE_MOM20_W: float = 1.0
SCORE_MOM10_W: float = 0.4
SCORE_MOM5_W: float = 0.6

# Minimum bar counts before an indicator is considered settledd and included.
# Monthly MACD needs ~40 bars; RSI is usable from ~n+1 bars but we want the
# rolling window to have settled past startup effects.
MIN_BARS_BIWEEKLY_RSI: int = 20    # 14 bars minimum for rsi(14); 20 is safer
MIN_BARS_MONTHLY_RSI: int = 20     # same logic on monthly
MIN_BARS_TF_STATE: int = 40        # _tf_state itself requires >=40

# Minimum RS ratio bars for mom5/mom10 fast RS computation
MIN_BARS_MOM5: int = 7
MIN_BARS_MOM10: int = 12

# ---------------------------------------------------------------------------
# Fast-momentum gate for unconfirmed states (FIX 2)
# ---------------------------------------------------------------------------
# A 1-week pop inside COUNTERTREND BOUNCE / DECLINE / TOP WATCH / ROLLING
# OVER is likely a dead-cat bounce, not a rotation candidate.  Apply this
# multiplier to fast_bonus > 0 when the cycle state is NOT in the confirmed-up
# set below.  Negative fast_bonus always counts fully.
FAST_UNCONFIRMED_MULT: float = 0.3

# States where a positive fast_bonus is taken at face value (sector has a
# cycle framework that supports the short-term momentum).
# BOTTOM WATCH and CONFIRMING TURN are intentionally excluded: they are
# dir=down / caution pre-turn states where a 1-week pop is exactly the
# unconfirmed bounce this gate exists to discount.
_FAST_CONFIRMED_STATES: frozenset[str] = frozenset({
    "FRESH BUY",
    "TURN SIGNALED",
    "RALLY ON",
})

# ---------------------------------------------------------------------------
# State-governor lookup table — exact UPPERCASE keys (FIX 1)
# ---------------------------------------------------------------------------
# Keys MUST match the exact strings emitted by engine.cycles.ladder_state()
# (the LADDER list).  Case-insensitive comparison at call time.
# Order matters only for documentation; the dict lookup is case-folded.
#
# CONFIRMING TURN interpretation: this is a daily bottoming setup inside a
# BEARISH higher-timeframe regime — the daily cycle signals a potential turn
# but the weekly investor cycle has NOT confirmed.  engine.cycles.LADDER_SCORE
# gives it -15 (caution, weaker than COUNTERTREND BOUNCE's -25).  For
# rotation purposes it is a mild POSITIVE (+4): the daily signal is actionable
# for nimble/high-risk traders and the sector has a turn in progress, making
# it a better rotation candidate than confirmed bearish states.  It is NOT a
# topping confirmation — that would be TOP WATCH or ROLLING OVER.
_STATE_GOVS: dict[str, int] = {
    "FRESH BUY":          +8,
    "TURN SIGNALED":      +5,
    # +1 (was +4): cycles.py LADDER_SCORE treats CONFIRMING TURN as -15
    # (weekly-unconfirmed buy-safety); for ROTATION candidacy we keep it
    # mildly positive (a turn in progress beats confirmed-bearish states) —
    # documented divergence from LADDER_SCORE.
    "CONFIRMING TURN":    +1,
    "BOTTOM WATCH":       +2,
    "RALLY ON":           +3,
    "TOP WATCH":          -5,
    "COUNTERTREND BOUNCE":-4,
    "ROLLING OVER":       -7,
    "DECLINE":            -8,
}

# Positive control: assert every LADDER state is explicitly mapped.
# This fires at import time so a future cycles.py ladder extension surfaces
# immediately as an ImportError (missing key → KeyError → mapped to 0 silently
# in _state_adj; the assert here prevents silent fall-through).
_UNMAPPED = frozenset(LADDER) - frozenset(_STATE_GOVS)
assert not _UNMAPPED, (
    f"china_sector_rotation: unmapped ladder states — add to _STATE_GOVS: {_UNMAPPED}"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _granularity(name: str) -> float:
    """Return h (homogeneity weight) for a sector by name."""
    if name in NARROW_SECTORS:
        return GRANULARITY_NARROW
    if name in BROAD_SECTORS:
        return GRANULARITY_BROAD
    return GRANULARITY_DEFAULT


def _state_adj(state: Optional[str]) -> int:
    """Map a cycle state string to a rotation-score governor (+/- points).

    Uses exact case-insensitive lookup against the UPPERCASE keys in
    _STATE_GOVS (which are the real strings emitted by cycles.ladder_state).
    Returns 0 for any unrecognised state (e.g. None / empty).
    """
    key = str(state or "").strip().upper()
    return _STATE_GOVS.get(key, 0)


def _sector_oscillators(
    ticker: str,
    closes: pd.DataFrame,
) -> dict:
    """
    Compute overbought oscillator inputs from the sector's OWN ETF series.

    Returns a dict with keys:
        rsi_2w, rsi_1m, stochk_2w   (float | None)
        macd_x1w, macd_x2w           (bool)
        macd_pos_1w                  (bool | None)
        null_components              (list[str])   for coverage reporting
    """
    out: dict = {
        "rsi_2w": None,
        "rsi_1m": None,
        "stochk_2w": None,
        "macd_x1w": False,
        "macd_x2w": False,
        "macd_pos_1w": None,
        "null_components": [],
    }

    if ticker not in closes.columns:
        out["null_components"].append("ticker_missing")
        return out

    px = closes[ticker].dropna()
    if len(px) < 40:
        out["null_components"].append("series_short")
        return out

    # -- Biweekly (2W) series — PIT-safe -----------------------------------
    try:
        bw = _biweekly_close(px)
    except Exception as e:
        out["null_components"].append(f"biweekly_err:{e}")
        bw = pd.Series(dtype=float)

    # RSI on biweekly bars
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

    # StochRSI-K on biweekly bars — stoch_rsi_kd already returns 0-100
    if len(bw) >= MIN_BARS_BIWEEKLY_RSI:
        try:
            k_series, _d = stoch_rsi_kd(bw)
            v = k_series.iloc[-1]
            if pd.notna(v):
                # Clip to [0, 100] in case of floating-point out-of-range
                out["stochk_2w"] = float(np.clip(v, 0.0, 100.0))
            else:
                out["null_components"].append("stochk_2w_nan")
        except Exception as e:
            out["null_components"].append(f"stochk_err:{e}")
    # (no else — already handled by biweekly_short above)

    # _tf_state on biweekly: macd_x2w
    if len(bw) >= MIN_BARS_TF_STATE:
        try:
            tfs_2w = _tf_state(bw)
            out["macd_x2w"] = bool(tfs_2w.get("macd_cross_dn", False))
        except Exception as e:
            out["null_components"].append(f"tf_2w_err:{e}")
    else:
        out["null_components"].append("biweekly_tf_short")

    # -- Monthly series — drop incomplete trailing month (FIX 5) -----------
    # Data-anchored: drop the trailing ME bar iff its stamp is beyond the last
    # actual daily close (ME stamp > px.index[-1] means the month is not yet
    # closed in daily data).  Wall-clock comparisons can drop a valid completed
    # bar early in the new month when daily data has already advanced.
    try:
        monthly_raw = px.resample("ME").last().dropna()
        if len(monthly_raw) > 0 and monthly_raw.index[-1] > px.index[-1]:
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

    # -- Weekly series — macd_x1w and macd_pos_1w --------------------------
    # Drop incomplete trailing week (current week not yet closed) (FIX 5)
    try:
        weekly_raw = px.resample("W-FRI").last().dropna()
        # W-FRI stamps each bar on the Friday; if today is before that Friday
        # the bar is still open.  A trailing bar whose stamp is in the future
        # relative to today is incomplete.
        if len(weekly_raw) > 0 and weekly_raw.index[-1] > today:
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
            # macd_pos for the OB-MACD component (True if histogram > 0 this bar)
            pos = tfs_1w.get("macd_pos")
            if pos is not None:
                out["macd_pos_1w"] = bool(pos)
        except Exception as e:
            out["null_components"].append(f"tf_1w_err:{e}")
    else:
        out["null_components"].append("weekly_tf_short")

    return out


def _ob_score(osc: dict) -> tuple[float, list[str]]:
    """
    Compute the composite overbought score [0, 1] from oscillator readings.

    Components (each clipped to [0, 1] before averaging):
        ob_rsi2w  = clip((rsi_2w  - 50) / 40, 0, 1)
        ob_rsi1m  = clip((rsi_1m  - 50) / 40, 0, 1)
        ob_stoch  = clip((stochk_2w - 50) / 45, 0, 1)
        ob_macd   = 0.5 if weekly MACD histogram is positive, else 0

    NULL components are EXCLUDED from the mean (no imputation) — a sector
    with fewer available oscillators gets a more uncertain but unbiased OB.

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
    """
    Compute OB score [0, 1] directly from a price series (FIX 3 helper).

    Used to evaluate the Shenwan index series with the same oscillator logic
    as the ETF, but WITHOUT the MACD-pos component (MACD cross detection is
    kept on the ETF as the tradeable instrument; index adds RSI/StochRSI only).

    Returns 0.0 on any failure or insufficient data.
    """
    try:
        if px is None or len(px) < 40:
            return 0.0

        components: list[float] = []

        # Biweekly RSI (2W)
        bw = _biweekly_close(px)
        if len(bw) >= MIN_BARS_BIWEEKLY_RSI:
            r2w = rsi(bw, 14)
            v = r2w.iloc[-1]
            if pd.notna(v):
                components.append(float(np.clip((float(v) - 50.0) / 40.0, 0.0, 1.0)))

        # StochRSI-K biweekly
        if len(bw) >= MIN_BARS_BIWEEKLY_RSI:
            k_series, _ = stoch_rsi_kd(bw)
            v = k_series.iloc[-1]
            if pd.notna(v):
                components.append(float(np.clip((float(np.clip(v, 0.0, 100.0)) - 50.0) / 45.0, 0.0, 1.0)))

        # Monthly RSI — drop incomplete trailing month (data-anchored: see FIX 5)
        monthly_raw = px.resample("ME").last().dropna()
        if len(monthly_raw) > 0 and monthly_raw.index[-1] > px.index[-1]:
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


def _fast_rs(ticker: str, closes: pd.DataFrame, bench: str) -> tuple[float, float]:
    """
    5-day and 10-day relative-strength momentum of the sector vs benchmark.

    ratio = closes[ticker] / closes[bench]   (aligned on common dates)
    momN = ratio.pct_change(N).iloc[-1] * 100

    Returns (mom5, mom10); falls back to 0.0 if data is too short.
    """
    mom5 = 0.0
    mom10 = 0.0

    # Guard: identical ticker and bench → ratio is constant, dup-column ValueError
    if ticker == bench:
        return mom5, mom10

    if ticker not in closes.columns or bench not in closes.columns:
        return mom5, mom10

    aligned = closes[[ticker, bench]].dropna()
    if aligned.empty:
        return mom5, mom10

    ratio = aligned[ticker] / aligned[bench]

    if len(ratio) >= MIN_BARS_MOM5:
        v = ratio.pct_change(5).iloc[-1]
        if pd.notna(v):
            mom5 = float(v * 100)

    if len(ratio) >= MIN_BARS_MOM10:
        v = ratio.pct_change(10).iloc[-1]
        if pd.notna(v):
            mom10 = float(v * 100)

    return mom5, mom10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_and_rank(
    cards: list[dict],
    closes: pd.DataFrame,
    bench: str,
) -> list[dict]:
    """
    Augment each sector card dict with rotation fields and return the list
    sorted by rotation_rank ascending (rank 1 = strongest current rotation).

    Parameters
    ----------
    cards :
        Per-sector dicts from build_china._sector_cards().  Expected keys:
        ticker, name, mom20, mom60, state, rank (old 60-day RS rank).
    closes :
        Wide daily DataFrame from engine.china_inputs.china_closes().
        Columns include each sector ETF ticker and the benchmark.
    bench :
        RS benchmark ticker, e.g. '510300.SS' (CSI 300 ETF).

    Returns
    -------
    list[dict]
        Same cards, each augmented with rotation fields, sorted ascending by
        rotation_rank.  The 60d RS rank is preserved as ``rank60``; ``rank``
        is overwritten with ``rotation_rank`` so downstream consumers see the
        new order.

    Notes
    -----
    * DISPLAY-ONLY — never touches any authority/gate/size signal.
    * PIT-safe: indicator functions read .iloc[-1] snapshots of causal series;
      monthly/weekly resamples drop the incomplete trailing bar.
    """
    if not cards:
        return cards

    coverage_log: list[str] = []
    scored: list[dict] = []

    for card in cards:
        ticker = card.get("ticker", "")
        name = card.get("name", "")
        mom20 = float(card.get("mom20") or 0.0)
        mom60 = float(card.get("mom60") or 0.0)
        state = card.get("state") or ""

        # ---- Fast RS momentum (own ETF vs benchmark) ---------------------
        mom5, mom10 = _fast_rs(ticker, closes, bench)

        # ---- Per-sector oscillators (own ETF series) ---------------------
        osc = _sector_oscillators(ticker, closes)

        rsi_2w = osc["rsi_2w"]
        rsi_1m = osc["rsi_1m"]
        stochk_2w = osc["stochk_2w"]
        macd_x1w = osc["macd_x1w"]
        macd_x2w = osc["macd_x2w"]

        null_comps = osc["null_components"]
        if null_comps:
            coverage_log.append(f"  {name} ({ticker}): {', '.join(null_comps)}")

        # ---- OB composite score from ETF ---------------------------------
        ob_etf, _included = _ob_score(osc)

        # ---- OB composite score from Shenwan sector index (FIX 3) -------
        # Use max(ob_etf, ob_index) so that a still-elevated sector index
        # catches sectors where the ETF has cooled but the underlying is hot.
        # MACD-cross detection stays on the ETF (tradeable instrument only).
        # Guarded: sw_close() is I/O in the render-critical path; any failure
        # falls back to ob_index=0.0 (ob degrades to ob_etf only).
        ob_index: float = 0.0
        try:
            sw_code = SECTOR_SW.get(name)
            if sw_code:
                px_idx = sw_close(sw_code)
                if px_idx is not None and len(px_idx) >= 40:
                    ob_index = _ob_score_from_series(px_idx)
        except Exception as _e:
            log.warning("china_sector_rotation: sw_close failed for %s (%s); ob_index=0", name, _e)
        ob = max(ob_etf, ob_index)

        # ---- Granularity (homogeneity) weight ----------------------------
        h = _granularity(name)

        # ---- State governor ----------------------------------------------
        sadj = _state_adj(state)

        # ---- Fast-momentum gate: kill dead-cat bounces (FIX 2) -----------
        # A 1-week pop inside bearish cycle states (COUNTERTREND BOUNCE,
        # DECLINE, TOP WATCH, ROLLING OVER) is likely a dead-cat bounce, not
        # a rotation candidate.  Only allow positive fast_bonus at face value
        # when the cycle framework supports the move.
        fast_bonus = SCORE_MOM10_W * mom10 + SCORE_MOM5_W * mom5
        state_upper = str(state).strip().upper()
        if fast_bonus > 0 and state_upper not in _FAST_CONFIRMED_STATES:
            fast_bonus *= FAST_UNCONFIRMED_MULT

        # ---- OB demotion penalty -----------------------------------------
        ob_demote = ob * OB_MAX_PENALTY * h

        # ---- MACD cross demotion (Refinement 1: gated by fast RS) --------
        # A bearish MACD cross is a genuine laggard signal but can be stale
        # if short-term RS is already turning back up (mom10 > 0).  When the
        # tape CONTRADICTS the cross, we scale back to CROSS_CONTRADICTED_MULT
        # so we don't bury a recovering sector.
        base_cross = (
            (CROSS_DEMOTE_1W if macd_x1w else 0.0)
            + (CROSS_DEMOTE_2W if macd_x2w else 0.0)
        )
        if base_cross > 0:
            if mom10 > 0:
                # Fast momentum contradicts the cross → attenuate demotion
                cross_demote = base_cross * CROSS_CONTRADICTED_MULT
            else:
                # Momentum confirms the bearish cross → apply full demotion
                cross_demote = base_cross
        else:
            cross_demote = 0.0

        # ---- Rotation score ----------------------------------------------
        # mom20 is used at full weight as a medium-term trend anchor.
        # fast_bonus replaces the raw mom10+mom5 terms (already state-gated).
        rotation_score = (
            SCORE_MOM20_W * mom20
            + fast_bonus
            + sadj
            - ob_demote
            - cross_demote
        )

        new_card = dict(card)  # shallow copy — preserve all existing keys
        new_card.update({
            "rotation_score": round(rotation_score, 1),
            "rsi_2w":    round(rsi_2w, 1) if rsi_2w is not None else None,
            "rsi_1m":    round(rsi_1m, 1) if rsi_1m is not None else None,
            "stochk_2w": round(stochk_2w, 1) if stochk_2w is not None else None,
            "macd_x1w":  macd_x1w,
            "macd_x2w":  macd_x2w,
            "ob_etf":    round(ob_etf, 3),
            "ob_index":  round(ob_index, 3),
            "ob":        round(ob, 3),
            "ob_demote": round(ob_demote, 2),
            "cross_demote": round(cross_demote, 1),
            "granularity":  h,
            "mom5":      round(mom5, 2),
            "mom10":     round(mom10, 2),
            "state_adj": sadj,
            # Preserve 60d RS rank for display context
            "rank60":    card.get("rank"),
        })
        scored.append(new_card)

    if coverage_log:
        log.debug(
            "china_sector_rotation oscillator coverage — null components:\n%s",
            "\n".join(coverage_log),
        )

    # ---- Stable sort: rotation_score DESC, mom20 DESC as tiebreaker ------
    scored.sort(
        key=lambda c: (-(c["rotation_score"] or 0.0), -(c.get("mom20") or 0.0))
    )

    # Assign rotation_rank (1 = best) and overwrite `rank` for downstream
    for i, c in enumerate(scored, 1):
        c["rotation_rank"] = i
        c["rank"] = i  # downstream consumers read `rank` — now rotation rank

    return scored
