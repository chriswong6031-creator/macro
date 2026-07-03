"""Sector-ignition layer — turn-evidence score per thematic basket (HK / Canada).

Masterplan §5.1. Ranks basket "groups" by TURN evidence (a change signal), NOT by
trailing relative strength (a level signal). The three universal legs:

  breadth_thrust   % of a basket's members that crossed *above* their 20-day moving
                   average within the last 5 sessions (a fresh-participation surge).
  rs_slope_change  the second difference of the basket's 20d log relative-strength vs
                   its benchmark — is relative strength *turning up* (accelerating),
                   not merely high? sign + magnitude.
  mtf_confirm      weekly higher-timeframe confirm: the basket's own level series is not
                   making a lower weekly close (last weekly close >= prior weekly close).

Per market:
  HK  ships WITHOUT a southbound-flow leg (thin history; accrues later). The card copy
      says "narrow market — ignition is context."
  CA  adds a commodity-flip flag for resource-mapped baskets: when the CA cross-asset
      overlay's oil factor is risk-"on" AND the basket is resource-mapped, a small bonus.
      Oil ONLY — gold/copper are NO-GO per the red-team reports.

PURE + TESTABLE: `compute_ignition` takes already-loaded frames and returns a plain dict.
No I/O, no store reads. The builders load the data plane and call in here (mirrors the
engine.baskets_region / engine.baskets_* split).

DISPLAY-ONLY, FORWARD-GRADED, NOT VALIDATED. Nothing here is a buy signal; the score is a
descriptive turn-evidence read whose forward value is graded by engine.ignition_audit and
will not be scored/weighted until those grades mature (first read ~Aug 2026).
"""
from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── leg weights (equal-ish; turn-evidence, not calibrated — display-only) ──────
W_BREADTH = 0.40
W_RS = 0.40
W_MTF = 0.20
COMMODITY_BONUS = 0.10          # CA resource baskets only, additive on top (capped at 1.0)

THRUST_WINDOW = 5               # sessions for the "crossed above 20dma recently" breadth thrust
MA_WINDOW = 20                  # the moving average members must cross
RS_WINDOW = 20                  # relative-strength lookback for the slope-change second difference

# state cutoffs on the 0..1 ignition score
STATE_IGNITING = 0.55           # turning up hard
STATE_RUNNING = 0.35            # positive but not a fresh turn
STATE_FADING = 0.20             # weak / rolling over


def _states_from_score(score: float, rs_turn: float) -> str:
    """Map a 0..1 score + the RS-turn sign into a discrete state.

    igniting : high score AND relative strength is turning up (a fresh thrust)
    running  : decent score but RS not freshly turning (already in motion)
    fading   : low-ish score
    idle     : negligible
    """
    if score >= STATE_IGNITING and rs_turn > 0:
        return "igniting"
    if score >= STATE_RUNNING:
        return "running"
    if score >= STATE_FADING:
        return "fading"
    return "idle"


def _breadth_thrust(member_closes: pd.DataFrame) -> tuple[float | None, int, int]:
    """% of members that newly closed above their 20dma within the last THRUST_WINDOW sessions.

    A member "thrusts" if it was below (or at) its 20dma THRUST_WINDOW+1 sessions ago and is
    above it now — a fresh cross, not a name that has been extended for months. Returns
    (fraction 0..1 | None, n_thrust, n_eligible).
    """
    if member_closes is None or member_closes.empty:
        return None, 0, 0
    closes = member_closes.sort_index()
    if len(closes) < MA_WINDOW + THRUST_WINDOW + 2:
        return None, 0, 0
    ma = closes.rolling(MA_WINDOW, min_periods=MA_WINDOW).mean()
    above = closes > ma
    now = above.iloc[-1]
    then = above.iloc[-(THRUST_WINDOW + 1)]
    # eligible = members with a valid MA reading at both endpoints
    eligible = now.notna() & then.notna() & closes.iloc[-1].notna()
    if not eligible.any():
        return None, 0, 0
    thrust = (now.fillna(False) & ~then.fillna(True)) & eligible
    n_elig = int(eligible.sum())
    n_thr = int(thrust.sum())
    return (n_thr / n_elig if n_elig else None), n_thr, n_elig


def _rel_series(level: pd.Series, bench: pd.Series) -> pd.Series | None:
    """Basket level / benchmark level, aligned + forward-filled to the basket's index."""
    if level is None or bench is None:
        return None
    lvl = pd.Series(level).dropna()
    bch = pd.Series(bench).reindex(lvl.index).ffill()
    rel = lvl / bch
    rel = rel.replace([np.inf, -np.inf], np.nan).dropna()
    return rel if len(rel) > RS_WINDOW * 2 + 2 else None


def _rs_slope_change(level: pd.Series, bench: pd.Series) -> tuple[float | None, float | None]:
    """Second difference (curvature) of 20d log relative strength.

    slope_now  = log(rel_t / rel_{t-RS_WINDOW})          (current 20d RS momentum)
    slope_prev = log(rel_{t-RS_WINDOW} / rel_{t-2*RS_WINDOW})
    change     = slope_now - slope_prev                  (>0 = RS accelerating up = a turn)

    Returns (normalized_change 0..1 | None, raw_change | None). The normalization is a soft
    tanh squash so a modest positive curvature maps near the top of the leg without letting
    one outlier dominate.
    """
    rel = _rel_series(level, bench)
    if rel is None:
        return None, None
    r = rel.to_numpy(dtype=float)
    if len(r) < 2 * RS_WINDOW + 1:
        return None, None
    try:
        slope_now = math.log(r[-1] / r[-1 - RS_WINDOW])
        slope_prev = math.log(r[-1 - RS_WINDOW] / r[-1 - 2 * RS_WINDOW])
    except (ValueError, ZeroDivisionError):
        return None, None
    change = slope_now - slope_prev
    # squash: 5% curvature over the window ≈ a strong turn. tanh keeps it in (-1,1); map to 0..1.
    norm = (math.tanh(change / 0.05) + 1.0) / 2.0
    return norm, change


def _mtf_confirm(level: pd.Series) -> tuple[float | None, bool | None]:
    """Weekly higher-timeframe confirm: the last completed weekly close is not lower than the
    prior weekly close (no fresh weekly breakdown). Returns (leg 0/0.5/1 | None, ok | None).

    We resample the basket's own daily level to weekly (Friday) closes and compare the two most
    recent completed weeks. 1.0 = weekly up, 0.5 = flat, 0.0 = weekly down.
    """
    if level is None:
        return None, None
    s = pd.Series(level).dropna()
    if len(s) < 15 or not isinstance(s.index, pd.DatetimeIndex):
        return None, None
    wk = s.resample("W-FRI").last().dropna()
    if len(wk) < 3:
        return None, None
    last, prev = float(wk.iloc[-1]), float(wk.iloc[-2])
    if last > prev:
        return 1.0, True
    if last == prev:
        return 0.5, True
    return 0.0, False


def compute_basket_ignition(
    bid: str,
    member_closes: pd.DataFrame | None,
    level: pd.Series | None,
    bench: pd.Series | None,
    *,
    commodity_flip: bool = False,
    resource_mapped: bool = False,
) -> dict:
    """Turn-evidence ignition for ONE basket. Pure.

    member_closes  wide [Date × member-ticker] closes for this basket's members
    level          this basket's EW level Series (daily)
    bench          the benchmark level Series (daily)
    commodity_flip CA only: is the oil overlay factor currently risk-"on"?
    resource_mapped CA only: is this basket in the resource sleeve (energy/materials/gold)?

    Returns {ignition_score (0..1|None), components{...}, state}.
    """
    breadth, n_thr, n_elig = _breadth_thrust(member_closes)
    rs_norm, rs_raw = _rs_slope_change(level, bench)
    mtf, mtf_ok = _mtf_confirm(level)

    legs, wsum = 0.0, 0.0
    if breadth is not None:
        legs += W_BREADTH * breadth
        wsum += W_BREADTH
    if rs_norm is not None:
        legs += W_RS * rs_norm
        wsum += W_RS
    if mtf is not None:
        legs += W_MTF * mtf
        wsum += W_MTF

    if wsum == 0:
        score = None
    else:
        score = legs / wsum          # renormalize over available legs (missing-leg honest)
        if commodity_flip and resource_mapped:
            score = min(1.0, score + COMMODITY_BONUS)

    rs_turn = rs_raw if rs_raw is not None else 0.0
    state = "idle" if score is None else _states_from_score(score, rs_turn)

    return {
        "id": bid,
        "ignition_score": None if score is None else round(float(score), 4),
        "state": state,
        "components": {
            "breadth_thrust": None if breadth is None else round(float(breadth), 4),
            "breadth_n": [n_thr, n_elig],
            "rs_slope_change": None if rs_norm is None else round(float(rs_norm), 4),
            "rs_slope_raw": None if rs_raw is None else round(float(rs_raw), 5),
            "mtf_confirm": None if mtf is None else round(float(mtf), 3),
            "mtf_ok": mtf_ok,
            "commodity_flip": bool(commodity_flip and resource_mapped),
        },
    }


def compute_ignition(
    chart: dict,
    baskets: list[dict],
    member_closes_of,
    *,
    market: str,
    overlay: dict | None = None,
    resource_categories: tuple[str, ...] = (),
) -> dict:
    """Market-level ignition strip. Pure w.r.t. its inputs (all frames passed in).

    chart               the payload's chart dict: {dates:[...], bench:[...], baskets:{bid:[level...]}}
    baskets             the payload's out_baskets list (each: id, name, name_zh, category, ...)
    member_closes_of    callable(basket_dict) -> wide [Date × member] closes | None
    market              'hk' | 'ca'
    overlay             CA cross-asset overlay snapshot (engine.canada_overlay.snapshot()); the
                        oil factor's risk state drives the commodity-flip flag. HK passes None.
    resource_categories basket categories that count as resource-mapped for the commodity flip.

    Returns {market, as_of, has_southbound_leg, items:[...sorted by ignition_score desc]}.
    """
    dates = (chart or {}).get("dates") or []
    if not dates:
        return {"market": market, "as_of": None, "items": [], "has_southbound_leg": False}
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    bench_lvl = pd.Series((chart.get("bench") or []), index=idx, dtype="float64")
    chart_baskets = chart.get("baskets") or {}

    # CA commodity-flip: is the oil overlay factor currently risk-"on"?
    oil_on = False
    if market == "ca" and overlay:
        for f in (overlay.get("factors") or []):
            if f.get("key") == "oil":
                oil_on = (f.get("risk") == "on")
                break

    by_id = {b["id"]: b for b in baskets}
    items = []
    for bid, lvl_list in chart_baskets.items():
        b = by_id.get(bid)
        if b is None:
            continue
        level = pd.Series(lvl_list, index=idx, dtype="float64")
        mc = None
        try:
            mc = member_closes_of(b)
        except Exception as e:  # noqa: BLE001 — additive; a bad basket must not kill the strip
            log.warning("ignition[%s] member closes for %s failed: %s", market, bid, e)
        resource_mapped = bool(b.get("category") in resource_categories)
        ig = compute_basket_ignition(
            bid, mc, level, bench_lvl,
            commodity_flip=oil_on, resource_mapped=resource_mapped,
        )
        ig["name"] = b.get("name", bid)
        ig["name_zh"] = b.get("name_zh", b.get("name", bid))
        ig["category"] = b.get("category")
        ig["resource_mapped"] = resource_mapped
        items.append(ig)

    items.sort(key=lambda x: (x["ignition_score"] is None, -(x["ignition_score"] or 0.0)))
    return {
        "market": market,
        "as_of": dates[-1],
        "has_southbound_leg": False,          # HK & CA both ship without a flow leg (§5.1)
        "commodity_flip_active": bool(oil_on),
        "items": items,
    }
