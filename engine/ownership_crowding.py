"""Ownership-crowding hazard lens for the Smart Money v2 Ownership Intelligence Desk.

DISPLAY-ONLY CONTEXT — never a score, never a signal input.

Prior (engine/crowding.py Phase-0): the price-only crowded+extended flag showed NO
forward-return underperformance (only a marginal, statistically-weak worse forward
drawdown ≈ 0.6pp over 3m, |t|≈ 2.3 at 63d but not robust across both halves). The
short-interest leg has no point-in-time history in our store and cannot be back-tested.
This module's crowding_tier is therefore a HAZARD / DE-ESCALATION read, not an edge.

Rulings that constrain this module:
  SM2-R3: No composite across 13F/insider/short/options axes at any grain. `days_to_exit`
    derives ONLY from aggregate tracked shares + ADV. `crowding_tier` derives ONLY from
    `days_to_exit`. No function may accept both a 13F metric and a short-derived metric
    (days_to_cover, si_change_pct) as combined inputs producing a single number.
  SM2-R4: Live context column only, stamped `settlement_date`. ADV sourced from
    `data/finra/short_interest.parquet.avg_daily_vol` (stamped accordingly), with
    fallback to 30d mean of `data/yahoo/<T>.parquet` volume; absent → null-honest None.
  SM2-R9: This module is `engine/ownership_crowding.py`. `engine/crowding.py` (per-stock
    fragility flag) already exists and must NOT be touched. Reuse the
    `days_to_exit_at_10pct_adv` semantics from that file's lineage.

PIT LAW: `adv_shares` accepts an `as_of` cutoff so no bar AFTER the anchor is read.
  A unit test in tests/test_ownership_crowding.py asserts this property.

Cost-basis band: labeled 'implied avg entry (quarter-end proxy)', NEVER 'cost basis'.
  13F value_usd and shares are reported at the quarter-END close, not the actual
  purchase price. The implied price per share is a quarter-end mark-to-market proxy,
  not the fund's actual acquisition price.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_FINRA_SHORT_INTEREST_PATH = ("finra", "short_interest.parquet")
_YAHOO_PATH = "yahoo"

# Quintile boundaries for days-to-exit crowd tier (in trading days).
# Calibrated roughly to ≈20 ADV (low), ≈40 ADV (mod), ≈80 ADV (elevated).
# Quintile labels derive from the distribution of the LIVE dataset; these are
# static thresholds used in the absence of a full distribution reference.
_LOW_MAX_DAYS = 20.0
_ELEVATED_MIN_DAYS = 40.0


# --------------------------------------------------------------------------- #
# ADV helpers                                                                   #
# --------------------------------------------------------------------------- #

def adv_shares(ticker: str, as_of: str | None = None) -> dict | None:
    """Average daily volume in shares for `ticker`, with source provenance.

    PRIMARY: data/finra/short_interest.parquet column `avg_daily_vol`.
      - If `as_of` is set and the settlement_date on the FINRA record is AFTER `as_of`,
        the record is excluded (PIT law: no data after the anchor).
    FALLBACK: 30-session mean of data/yahoo/<ticker>.parquet `volume`.
      - Only sessions up to and including `as_of` are used when `as_of` is set.
    Returns None when neither source is available.

    Return dict: {adv: float, source: 'finra'|'yahoo', settlement_date: str|None}

    PIT GUARANTEE: when `as_of` is supplied, no data point timestamped after that date
    contributes to the returned ADV. Tests in tests/test_ownership_crowding.py assert
    that a post-anchor volume bar cannot influence the anchored result.
    """
    as_of_ts = pd.Timestamp(as_of) if as_of else None

    # Primary: FINRA short interest avg_daily_vol
    try:
        p = config.data_dir() / _FINRA_SHORT_INTEREST_PATH[0] / _FINRA_SHORT_INTEREST_PATH[1]
        if p.exists():
            df = pd.read_parquet(p)
            if ticker in df.index:
                row = df.loc[ticker]
                settle_raw = (row.get("settlement_date") if hasattr(row, "get")
                              else row["settlement_date"] if "settlement_date" in df.columns
                              else None)
                settle_str = str(settle_raw) if settle_raw is not None else None
                adv_val = float(row["avg_daily_vol"])
                # PIT check: exclude this record if settlement is after the anchor
                skip = False
                if as_of_ts is not None and settle_str:
                    try:
                        if pd.Timestamp(settle_str) > as_of_ts:
                            skip = True
                    except Exception:
                        pass
                if not skip and adv_val > 0:
                    return {"adv": adv_val, "source": "finra",
                            "settlement_date": settle_str}
    except Exception:  # noqa: BLE001
        log.debug("FINRA short interest read failed for %s", ticker, exc_info=True)

    # Fallback: 30-session mean from yahoo volume
    try:
        p = config.data_dir() / _YAHOO_PATH / f"{ticker}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if "volume" not in df.columns:
                return None
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            # PIT: restrict to sessions at or before as_of
            if as_of_ts is not None:
                df = df[df.index <= as_of_ts]
            vol = df["volume"].dropna().tail(30)
            if len(vol) == 0:
                return None
            adv_val = float(vol.mean())
            if adv_val > 0:
                return {"adv": adv_val, "source": "yahoo", "settlement_date": None}
    except Exception:  # noqa: BLE001
        log.debug("Yahoo volume read failed for %s", ticker, exc_info=True)

    return None


# --------------------------------------------------------------------------- #
# Core crowding metrics (pure given inputs)                                     #
# --------------------------------------------------------------------------- #

def days_to_exit(agg_shares: float | None, adv: float | None) -> float | None:
    """Aggregate tracked shares / ADV = days-to-liquidate at 100% of ADV.

    Returns None (null-honest) when either input is absent — never imputed.

    SM2-R9: reuses the days_to_exit_at_10pct_adv lineage from engine/crowding.py;
    this variant uses 100% ADV (not 10%) because we are measuring the desk's
    aggregate position against ADV, not a single fund's position at a conservative
    participation rate. The denominator is caller-controlled so the % assumption
    is transparent.
    """
    if agg_shares is None or adv is None:
        return None
    if adv <= 0 or agg_shares < 0:
        return None
    return round(float(agg_shares) / float(adv), 1)


def crowding_tier(dte: float | None,
                  universe_values: list[float] | None = None) -> str:
    """Crowding tier from days_to_exit ALONE (SM2-R3).

    When `universe_values` is provided (list of days_to_exit for all names in the
    desk universe), the tier is the quintile of `dte` in that distribution:
      - bottom 40%  -> 'low'
      - middle 40%  -> 'moderate'
      - top 20%     -> 'elevated'
    When `universe_values` is absent, the static thresholds are used:
      - dte < 20    -> 'low'
      - 20 <= dte < 40 -> 'moderate'
      - dte >= 40   -> 'elevated'
    dte is None -> 'unavailable'

    NOTE: this function ONLY accepts days_to_exit and a distribution reference.
    It does NOT accept any 13F metric, short interest metric, or any other axis.
    That is the SM2-R3 no-fusion guard — kept as API design.
    """
    if dte is None:
        return "unavailable"
    if universe_values:
        valid = sorted(v for v in universe_values if v is not None)
        n = len(valid)
        if n >= 5:
            p40 = valid[int(0.40 * n)]
            p80 = valid[int(0.80 * n)]
            if dte < p40:
                return "low"
            if dte >= p80:
                return "elevated"
            return "moderate"
    # Static thresholds fallback
    if dte < _LOW_MAX_DAYS:
        return "low"
    if dte >= _ELEVATED_MIN_DAYS:
        return "elevated"
    return "moderate"


def implied_entry_band(holder_rows: list[dict],
                       latest_close: float | None) -> dict | None:
    """Implied average entry price band from 13F quarter-end value/shares proxies.

    For each holder row with both `value_usd` and `shares` > 0, computes the
    implied price per share (value_usd / shares). This is the QUARTER-END mark-to-
    market proxy, labeled explicitly as such — it is NOT cost basis.

    Returns:
      {p25, p50, p75, n_underwater, n, label}
    or None when fewer than 2 priced holder rows exist.

    `n_underwater`: count of holders whose implied entry > latest_close (the position
    is currently under the quarter-end implied mark — a loose crowding-fragility read).
    None when latest_close is absent.
    """
    prices = []
    for h in holder_rows:
        val = h.get("value_usd")
        sh = h.get("shares")
        if val and sh and float(val) > 0 and float(sh) > 0:
            prices.append(float(val) / float(sh))
    if len(prices) < 2:
        return None
    prices_s = pd.Series(prices)
    p25 = round(float(prices_s.quantile(0.25)), 4)
    p50 = round(float(prices_s.quantile(0.50)), 4)
    p75 = round(float(prices_s.quantile(0.75)), 4)
    n_underwater = None
    if latest_close is not None and latest_close > 0:
        n_underwater = int(sum(1 for p in prices if p > latest_close))
    return {
        "p25": p25, "p50": p50, "p75": p75,
        "n_underwater": n_underwater, "n": len(prices),
        "label": "implied avg entry (quarter-end proxy)",
    }
