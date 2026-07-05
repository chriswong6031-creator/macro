"""Liquidity chip — 20-day median dollar-ADV + buildability gauge (W5b).

Display-only; zero rank / gate power.  Computes:
  - adv_dollar_20d_median : 20-session median dollar volume (close × volume),
    using the rolling window from the end of the series.
  - tier               : deep / ok / thin / illiquid (named thresholds below).
  - days_to_build_100k : days at 10 % of ADV to accumulate a $100k clip.
  - days_to_build_1m   : days at 10 % of ADV to accumulate a $1M clip.

Assumption: investor takes at most MAX_ADV_PCT of a day's dollar volume to
avoid moving the market.  A $100k position therefore requires
100_000 / (ADV x MAX_ADV_PCT) trading days.  The same formula applies to $1M.

The $1M and $100k numbers are DISPLAY HEURISTICS -- not position-size advice.
They help users understand whether an idea is even executable at their scale
before they look further.

Thresholds (named constants -- single source of truth):
  TIER_DEEP_THRESHOLD    = 50_000_000   # >= $50M ADV  -> "deep"
  TIER_OK_THRESHOLD      = 10_000_000   # >= $10M ADV  -> "ok"
  TIER_THIN_THRESHOLD    =  1_000_000   # >=  $1M ADV  -> "thin"
  # below TIER_THIN_THRESHOLD           -> "illiquid"

MAX_ADV_PCT: fraction of a day's ADV consumed by the investor (10 %).

All inputs are pandas Series (close and volume from data/stocks/*.parquet or
data/yahoo/*.parquet -- same schema).  Returns None when data is insufficient
(< 5 usable sessions after dropna) so callers can silently skip.
"""
from __future__ import annotations

import pandas as pd

# --------------------------------------------------------------------------- #
#  Tier thresholds -- NAMED CONSTANTS (single source of truth for W5b)        #
# --------------------------------------------------------------------------- #
TIER_DEEP_THRESHOLD: float = 50_000_000.0   # >= $50M  median dollar ADV -> "deep"
TIER_OK_THRESHOLD: float = 10_000_000.0     # >= $10M  median dollar ADV -> "ok"
TIER_THIN_THRESHOLD: float = 1_000_000.0    # >=  $1M  median dollar ADV -> "thin"
# below TIER_THIN_THRESHOLD                                                 -> "illiquid"

# Fraction of a day's ADV the investor is assumed to consume (10 %).
MAX_ADV_PCT: float = 0.10

# Clip sizes in dollars for days-to-build.
CLIP_100K: float = 100_000.0
CLIP_1M: float = 1_000_000.0

# Rolling window (trading sessions).
WINDOW: int = 20

# Minimum usable sessions after dropna.
MIN_SESSIONS: int = 5


def _tier(adv: float) -> str:
    """Map a dollar ADV to a liquidity tier label."""
    if adv >= TIER_DEEP_THRESHOLD:
        return "deep"
    if adv >= TIER_OK_THRESHOLD:
        return "ok"
    if adv >= TIER_THIN_THRESHOLD:
        return "thin"
    return "illiquid"


def _days_to_build(clip: float, adv: float) -> float | None:
    """Trading days to accumulate *clip* dollars at MAX_ADV_PCT of *adv*/day.

    Returns None when adv is zero or negative (undefined).
    """
    capacity_per_day = adv * MAX_ADV_PCT
    if capacity_per_day <= 0:
        return None
    return clip / capacity_per_day


def compute(close: "pd.Series", volume: "pd.Series") -> "dict | None":
    """Return the liquidity chip dict for one stock, or None if insufficient data.

    Parameters
    ----------
    close:
        Daily closing prices (dividend-adjusted; the value is used only to
        compute dollar volume -- any adjustment consistent with *volume* is fine).
    volume:
        Daily share volume (raw; same index as *close*).

    Returns
    -------
    dict with keys:
        adv_dollar_20d_median : float -- 20-session median dollar volume ($)
        tier                  : str   -- "deep" | "ok" | "thin" | "illiquid"
        days_to_build_100k    : float -- days to build a $100k clip at 10% ADV
        days_to_build_1m      : float -- days to build a $1M clip at 10% ADV
    or None when data is insufficient.
    """
    # Align on the shorter tail so we never read beyond either series.
    close_tail = close.tail(WINDOW).dropna()
    volume_tail = volume.tail(WINDOW).dropna()
    common = close_tail.index.intersection(volume_tail.index)
    if len(common) < MIN_SESSIONS:
        return None

    dv = close_tail.loc[common] * volume_tail.loc[common]
    adv = float(dv.median())
    if adv <= 0:
        return None

    tier = _tier(adv)
    dtb_100k = _days_to_build(CLIP_100K, adv)
    dtb_1m = _days_to_build(CLIP_1M, adv)

    return {
        "adv_dollar_20d_median": round(adv, 0),
        "tier": tier,
        "days_to_build_100k": round(dtb_100k, 1) if dtb_100k is not None else None,
        "days_to_build_1m": round(dtb_1m, 1) if dtb_1m is not None else None,
    }
