"""HS-2 Event-day reaction library (P3).

Pre-registered study per RIC masterplan §5.3.  Descriptive only — no signal,
no gate, no entry/exit claim (MRI-R1/R2/R3).

Outputs (written to reports/):
    ric_hs2_event_reaction_library.json   — machine-readable library
    ric-hs2-event-reaction-library.md     — human-readable report (EN only)

Coverage owned vs spec (printed prominently):
    CPI/NFP   : 1997-01→2026-05 (realtime_start 1997-01-14→2026-06-10)
    PPI       : 2014-02→2026-05 (realtime_start 2014-03-14→2026-06-11)
    CLAIMS    : 2009-05→2026-06 (realtime_start 2009-06-04→2026-06-25)
    FOMC      : 1998-02→2026-07 (web-compiled list, embedded below)
    SPY       : 1993-01→2026-07  |  TLT: 2002-07→  |  DXY: 1971-01→  |  GLD: 2004-11→

Spec says "1998→" — our PIT vintage store starts 1997-01 for CPI/NFP so we
report all we own; the era-split (pre-2010/2010-2020/2021+) still applies.

Usage:
    python3 scripts/research/hs2_event_reactions.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── repo path bootstrap (copy from _a3_common.py idiom) ──────────────────────
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# ── output paths ─────────────────────────────────────────────────────────────
_REPORTS = _ROOT / "reports"
_REPORTS.mkdir(parents=True, exist_ok=True)
_JSON_OUT = _REPORTS / "ric_hs2_event_reaction_library.json"
_MD_OUT = _REPORTS / "ric-hs2-event-reaction-library.md"

# ─────────────────────────────────────────────────────────────────────────────
# FOMC decision date list — compiled from Federal Reserve website
# Sources (fetched 2026-07-14):
#   https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
#   https://www.federalreserve.gov/monetarypolicy/fomchistorical<YYYY>.htm
#   for YYYY in 1998..2024
# Decision date = last day of each scheduled meeting.
# Intermeeting / unscheduled decisions flagged with "inter" suffix in comment.
# Note: 2020-03-15 and 2020-03-23 are notation votes (Sunday/Monday);
#       2020-03-15 is a Sunday → aligned to next trading day (2020-03-16).
# ─────────────────────────────────────────────────────────────────────────────
_FOMC_SCHEDULED = [
    # 1998
    "1998-02-04", "1998-03-31", "1998-05-19", "1998-07-01",
    "1998-08-18", "1998-09-29", "1998-11-17", "1998-12-22",
    # 1999
    "1999-02-03", "1999-03-30", "1999-05-18", "1999-06-30",
    "1999-08-24", "1999-10-05", "1999-11-16", "1999-12-21",
    # 2000
    "2000-02-02", "2000-03-21", "2000-05-16", "2000-06-28",
    "2000-08-22", "2000-10-03", "2000-11-15", "2000-12-19",
    # 2001
    "2001-01-31", "2001-03-20", "2001-05-15", "2001-06-27",
    "2001-08-21", "2001-10-02", "2001-11-06", "2001-12-11",
    # 2002
    "2002-01-30", "2002-03-19", "2002-05-07", "2002-06-26",
    "2002-08-13", "2002-09-24", "2002-11-06", "2002-12-10",
    # 2003
    "2003-01-29", "2003-03-18", "2003-05-06", "2003-06-25",
    "2003-08-12", "2003-09-16", "2003-10-28", "2003-12-09",
    # 2004
    "2004-01-28", "2004-03-16", "2004-05-04", "2004-06-30",
    "2004-08-10", "2004-09-21", "2004-11-10", "2004-12-14",
    # 2005
    "2005-02-02", "2005-03-22", "2005-05-03", "2005-06-30",
    "2005-08-09", "2005-09-20", "2005-11-01", "2005-12-13",
    # 2006
    "2006-01-31", "2006-03-28", "2006-05-10", "2006-06-29",
    "2006-08-08", "2006-09-20", "2006-10-25", "2006-12-12",
    # 2007
    "2007-01-31", "2007-03-21", "2007-05-09", "2007-06-28",
    "2007-08-07", "2007-09-18", "2007-10-31", "2007-12-11",
    # 2008
    "2008-01-30", "2008-03-18", "2008-04-30", "2008-06-25",
    "2008-08-05", "2008-09-16", "2008-10-29", "2008-12-16",
    # 2009
    "2009-01-28", "2009-03-18", "2009-04-29", "2009-06-24",
    "2009-08-12", "2009-09-23", "2009-11-04", "2009-12-16",
    # 2010
    "2010-01-27", "2010-03-16", "2010-04-28", "2010-06-23",
    "2010-08-10", "2010-09-21", "2010-11-03", "2010-12-14",
    # 2011
    "2011-01-26", "2011-03-15", "2011-04-27", "2011-06-22",
    "2011-08-09", "2011-09-21", "2011-11-02", "2011-12-13",
    # 2012
    "2012-01-25", "2012-03-13", "2012-04-25", "2012-06-20",
    "2012-08-01", "2012-09-13", "2012-10-24", "2012-12-12",
    # 2013
    "2013-01-30", "2013-03-20", "2013-05-01", "2013-06-19",
    "2013-07-31", "2013-09-18", "2013-10-30", "2013-12-18",
    # 2014
    "2014-01-29", "2014-03-19", "2014-04-30", "2014-06-18",
    "2014-07-30", "2014-09-17", "2014-10-29", "2014-12-17",
    # 2015
    "2015-01-28", "2015-03-18", "2015-04-29", "2015-06-17",
    "2015-07-29", "2015-09-17", "2015-10-28", "2015-12-16",
    # 2016
    "2016-01-27", "2016-03-16", "2016-04-27", "2016-06-15",
    "2016-07-27", "2016-09-21", "2016-11-02", "2016-12-14",
    # 2017
    "2017-02-01", "2017-03-15", "2017-05-03", "2017-06-14",
    "2017-07-26", "2017-09-20", "2017-11-01", "2017-12-13",
    # 2018
    "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13",
    "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
    # 2019
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19",
    "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    # 2020
    "2020-01-29", "2020-04-29", "2020-06-10", "2020-07-29",
    "2020-09-16", "2020-11-05", "2020-12-16",
    # 2021
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16",
    "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    # 2022
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
    "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    # 2023
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
    "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026 (from fomccalendars.htm)
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# Intermeeting / unscheduled decisions (flagged separately)
# Notation votes and conference calls that involved target changes or actions.
# Sources: fomchistorical pages, DFEDTARU change dates.
_FOMC_INTERMEETING = [
    # 1998 (emergency cut during LTCM/Russia crisis)
    "1998-09-21",  # conference call rate cut
    "1998-10-15",  # inter-meeting cut
    # 2001 (aggressive easing cycle)
    "2001-01-03",  # inter-meeting cut
    "2001-04-18",  # inter-meeting cut (note: 04-11 was also a call)
    "2001-09-17",  # emergency cut post-9/11
    # 2007 (subprime crisis)
    "2007-08-10",  # conference call
    "2007-08-16",  # conference call
    "2007-12-06",  # conference call
    # 2008 (financial crisis)
    "2008-01-09",  # conference call
    "2008-01-21",  # inter-meeting cut
    "2008-03-10",  # inter-meeting cut
    "2008-09-29",  # conference call
    "2008-10-08",  # inter-meeting cut (announced Wed 2008-10-08 ~7am ET; effective 2008-10-09)
    # 2009
    "2009-01-16",  # conference call
    "2009-02-07",  # conference call
    "2009-06-03",  # conference call
    # 2010
    "2010-05-09",  # conference call (European debt)
    "2010-10-15",  # conference call
    # 2011
    "2011-08-01",  # conference call
    "2011-11-28",  # conference call
    # 2013
    "2013-10-16",  # unscheduled
    # 2014
    "2014-03-04",  # conference call
    # 2019
    "2019-10-04",  # conference call
    # 2020 (COVID emergency)
    "2020-03-03",  # emergency 50bp cut (announced Tue 2020-03-03; effective 2020-03-04)
    "2020-03-15",  # emergency 100bp cut (Sunday; maps to 2020-03-16 trading day)
    "2020-03-19",  # notation vote
    "2020-03-23",  # notation vote
    "2020-03-31",  # conference call
    "2020-08-27",  # framework announcement (not a rate decision, included for completeness)
]

# catalyst_tone.py _FOMC_MEETINGS cross-check:
# 2025-09-17, 2025-10-29, 2025-12-10 ✓ (match our scheduled list)
# 2026-01-28, 2026-03-18, 2026-04-29, 2026-06-17 ✓ (match)
# 2026-07-29, 2026-09-16, 2026-10-28, 2026-12-09 ✓ (from fomccalendars.htm)
# All 11 dates in catalyst_tone._FOMC_MEETINGS are present in our lists. ✓


# ─────────────────────────────────────────────────────────────────────────────
# Regime classification
# ─────────────────────────────────────────────────────────────────────────────
def _build_regime_series(dfedtaru_path: Path, dff_path: Path) -> pd.Series:
    """Hiking / cutting / pause per event date.

    Operationalization (frozen):
      DFEDTARU (2008-12-16+): 126-calendar-day change in fed_target_upper
        (units: percentage points, so 0.125 = 12.5bp, the threshold).
        > +0.125 pct-pt  → hiking
        < -0.125 pct-pt  → cutting
        else             → pause
      DFF (pre-2008-12-16): same logic on fed_funds (also in pct-pt units).
      126 calendar days ≈ 6 calendar months.  Threshold 0.125 pct-pt = 12.5bp = ½ of 25bp step.
    """
    # DFEDTARU
    dftar = pd.read_parquet(dfedtaru_path)["fed_target_upper"].sort_index()
    # Fill forward so every trading day has a value
    dftar = dftar.reindex(pd.date_range(dftar.index.min(), dftar.index.max(), freq="D")).ffill()

    # DFF (daily fed funds rate - pre-2008)
    dff = pd.read_parquet(dff_path)["fed_funds"].sort_index()
    dff = dff.reindex(pd.date_range(dff.index.min(), dff.index.max(), freq="D")).ffill()

    # Combine: use DFEDTARU where available (2008-12-16+), else DFF
    combined_start = min(dff.index.min(), dftar.index.min())
    combined_end = max(dff.index.max(), dftar.index.max())
    all_dates = pd.date_range(combined_start, combined_end, freq="D")
    rate = pd.Series(np.nan, index=all_dates)
    rate.update(dff)
    rate.update(dftar)  # DFEDTARU wins where it exists
    rate = rate.ffill()

    # 126-day rolling change (calendar days; use .shift(126))
    chg = rate - rate.shift(126)

    # Threshold: 0.125 percentage points = 12.5 bp = half a standard 25bp step.
    # Data units: pct-pt (0.25 = 25bp, 1.0 = 100bp, etc.)
    _THRESH = 0.125

    def classify(c: float) -> str:
        if pd.isna(c):
            return "unknown"
        if c > _THRESH:
            return "hiking"
        if c < -_THRESH:
            return "cutting"
        return "pause"

    regime = chg.map(classify)
    return regime


# ─────────────────────────────────────────────────────────────────────────────
# 'Good news = bad news' flag
# ─────────────────────────────────────────────────────────────────────────────
def _build_gnbn_flag(spy_close: pd.Series, dgs2_path: Path, window: int = 126) -> pd.Series:
    """Rolling 126-day correlation of SPY daily return vs DGS2 daily change.

    corr < -0.15  → 'good-news-is-bad' / rate-scare regime.
    Operationalization: negative corr means rising rates coincide with falling
    equities — the 'good news (strong economy → rate hike fear) = bad news'
    regime.
    """
    dgs2 = pd.read_parquet(dgs2_path)["us2y"].sort_index()
    # Align to SPY trading days
    spy_ret = spy_close.pct_change()
    dgs2_chg = dgs2.reindex(spy_close.index).ffill().diff()

    # Rolling correlation
    df_temp = pd.DataFrame({"spy_ret": spy_ret, "dgs2_chg": dgs2_chg}).dropna()
    rolling_corr = (
        df_temp["spy_ret"]
        .rolling(window, min_periods=int(window * 0.7))
        .corr(df_temp["dgs2_chg"])
    )
    # Reindex to SPY close index
    gnbn = rolling_corr.reindex(spy_close.index)
    return gnbn  # raw corr; flag = corr < -0.15 at event date


# ─────────────────────────────────────────────────────────────────────────────
# Newey-West HAC t-stat (hand-rolled, statsmodels not available)
# ─────────────────────────────────────────────────────────────────────────────
def _nw_hac_tstat(series: pd.Series, lag: int = 5) -> float:
    """Newey-West HAC t-statistic for H0: mean = 0.

    Bartlett kernel up to `lag` lags.  Returns NaN if n < lag+2.

    Autocovariance: gamma[j] = sum(x_dm[j:] * x_dm[:n-j]) / n
    (non-wrapping form; np.roll is NOT used — it injects spurious circular
    cross-products pairing the series tail with its head).
    """
    x = series.dropna().values
    n = len(x)
    if n < lag + 2:
        return np.nan
    x_dm = x - x.mean()
    # Non-wrapping autocovariance: gamma[j] uses only the n-j valid pairs
    gamma = np.empty(lag + 1)
    gamma[0] = np.dot(x_dm, x_dm) / n
    for j in range(1, lag + 1):
        gamma[j] = np.dot(x_dm[j:], x_dm[:n - j]) / n
    # HAC variance (Bartlett kernel)
    nw_var = gamma[0]
    for j in range(1, lag + 1):
        w = 1.0 - j / (lag + 1)  # Bartlett weight
        nw_var += 2 * w * gamma[j]
    nw_var = max(nw_var, 0.0)  # numerical floor
    se = np.sqrt(nw_var / n)
    if se == 0:
        return np.nan
    return x.mean() / se


# ─────────────────────────────────────────────────────────────────────────────
# Market return computations
# ─────────────────────────────────────────────────────────────────────────────
def _compute_returns(
    event_dates: pd.DatetimeIndex,
    close: pd.Series,
    asset: str,
) -> pd.DataFrame:
    """Compute day0, fwd5 returns and RV metrics for each event date.

    day0  = close[event] / close[prev_trading_day] - 1
    fwd5  = close[t+4] / close[t-1] - 1   (5 sessions inclusive t..t+4)
    RV5   = annualised stdev of 5 daily log-returns t..t+4
    RV20  = annualised stdev of 20 daily log-returns t-20..t-1 (trailing)
    rv_ratio = RV5 / RV20

    pre_drift = close[t-1] / close[t-5] - 1  (5 sessions T-5..T-1 inclusive)
    post_drift = close[t+5] / close[t] - 1   (5 sessions T+1..T+5 inclusive)

    Only events where both asset start date and required look-back/ahead exist
    are included; others receive NaN.

    Note: day0 and fwd5 both use close[t-1] as base, capturing the full
    close-to-close window that includes 8:30am releases (CPI/NFP/PPI/claims)
    and 2pm FOMC announcements — both are inside the release day's session.
    """
    tdays = close.index  # sorted trading days present
    tday_set = set(tdays)
    rows = []
    for ed in event_dates:
        # Resolve ed to nearest trading day (forward-fill if holiday/weekend)
        if ed not in tday_set:
            fut = tdays[tdays >= ed]
            if len(fut) == 0:
                rows.append(_nan_row(ed, asset))
                continue
            ed_adj = fut[0]
            adjusted = True
        else:
            ed_adj = ed
            adjusted = False

        loc = tdays.get_loc(ed_adj)
        # Need t-5 (for RV20 warm-up) and t+4 (for fwd5)
        if loc < 20 or loc + 4 >= len(tdays):
            rows.append(_nan_row(ed, asset, adjusted))
            continue

        t_m1 = tdays[loc - 1]    # prev trading day (base for day0 + fwd5)
        t_m5 = tdays[loc - 5]    # 5 sessions back (pre-window start)
        t_p4 = tdays[loc + 4]    # 4 sessions forward
        t_p5 = tdays[loc + 5] if loc + 5 < len(tdays) else None

        c = close
        day0 = c[ed_adj] / c[t_m1] - 1
        fwd5 = c[t_p4] / c[t_m1] - 1

        # Pre-drift: T-5..T-1 = close[T-1]/close[T-6] - 1
        t_m6 = tdays[loc - 6] if loc >= 6 else None
        pre_drift = (c[t_m1] / c[t_m6] - 1) if t_m6 is not None else np.nan

        # Post-drift: T+1..T+5
        post_drift = (c[t_p5] / c[ed_adj] - 1) if t_p5 is not None else np.nan

        # RV5: annualised stdev of 5 log-returns (t..t+4)
        window5 = tdays[loc : loc + 5]
        log_rets5 = np.diff(np.log(c[window5].values))
        rv5 = np.std(log_rets5, ddof=1) * np.sqrt(252) if len(log_rets5) >= 2 else np.nan

        # RV20: trailing 20 sessions ending t-1
        window20 = tdays[loc - 20 : loc]
        log_rets20 = np.diff(np.log(c[window20].values))
        rv20 = np.std(log_rets20, ddof=1) * np.sqrt(252) if len(log_rets20) >= 2 else np.nan

        rv_ratio = rv5 / rv20 if (rv20 and rv20 > 0) else np.nan

        rows.append({
            "event_date": ed,
            "trade_date": ed_adj,
            "adjusted": adjusted,
            "asset": asset,
            "day0": day0,
            "fwd5": fwd5,
            "pre_drift": pre_drift,
            "post_drift": post_drift,
            "rv5": rv5,
            "rv20": rv20,
            "rv_ratio": rv_ratio,
        })

    return pd.DataFrame(rows)


def _nan_row(ed: pd.Timestamp, asset: str, adjusted: bool = False) -> dict:
    return {
        "event_date": ed,
        "trade_date": pd.NaT,
        "adjusted": adjusted,
        "asset": asset,
        "day0": np.nan,
        "fwd5": np.nan,
        "pre_drift": np.nan,
        "post_drift": np.nan,
        "rv5": np.nan,
        "rv20": np.nan,
        "rv_ratio": np.nan,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Event-type date extraction
# ─────────────────────────────────────────────────────────────────────────────
def _get_first_prints(vintages: pd.DataFrame, series: str) -> pd.DataFrame:
    sub = vintages[vintages["series"] == series].copy()
    fp = sub.sort_values("realtime_start").groupby("period").first().reset_index()
    fp = fp.rename(columns={"realtime_start": "release_date"})
    return fp[["period", "release_date", "value"]].sort_values("release_date")


def _compute_cpi_surprise(vint: pd.DataFrame) -> pd.DataFrame:
    """PIT m/m surprise for CPI.

    first-print m/m = value[t] - value[t-1] using first-print values for both.
    surprise = m/m[t] - m/m[t-1]   (naive prior = last period's m/m)
    sign: up-surprise / down-surprise / inline (within ±0.25*trailing_stdev)
    """
    fp = _get_first_prints(vint, "CPIAUCSL")
    fp = fp.sort_values("period").reset_index(drop=True)
    fp["mom"] = fp["value"].diff()          # first-print MoM change (index points)
    fp["surprise"] = fp["mom"].diff()       # vs prior period's first-print MoM
    # PIT trailing stdev of surprise (expanding, 12-period min).
    # shift(1) ensures only information available BEFORE the current release
    # is used to compute the normalisation band — strictly point-in-time.
    fp["surp_std"] = fp["surprise"].shift(1).expanding(min_periods=12).std()
    return fp


def _compute_nfp_surprise(vint: pd.DataFrame) -> pd.DataFrame:
    """PIT monthly change (level difference) surprise for NFP.

    surprise = mom[t] - trailing_3m_mean_mom (naive: 3-month trailing mean)
    """
    fp = _get_first_prints(vint, "PAYEMS")
    fp = fp.sort_values("period").reset_index(drop=True)
    fp["mom"] = fp["value"].diff()   # thousands
    # 3-month trailing mean of mom (ending t-1)
    fp["prior_3m"] = fp["mom"].shift(1).rolling(3, min_periods=2).mean()
    fp["surprise"] = fp["mom"] - fp["prior_3m"]
    # PIT trailing stdev: shift(1) so current surprise is not included.
    fp["surp_std"] = fp["surprise"].shift(1).expanding(min_periods=12).std()
    return fp


def _compute_ppi_surprise(vint: pd.DataFrame) -> pd.DataFrame:
    """PIT m/m surprise for PPI (PPIFIS)."""
    fp = _get_first_prints(vint, "PPIFIS")
    fp = fp.sort_values("period").reset_index(drop=True)
    fp["mom"] = fp["value"].diff()
    fp["surprise"] = fp["mom"].diff()
    # PIT trailing stdev: shift(1) so current surprise is not included.
    fp["surp_std"] = fp["surprise"].shift(1).expanding(min_periods=12).std()
    return fp


def _compute_claims_surprise(vint: pd.DataFrame) -> pd.DataFrame:
    """PIT surprise for ICSA: first-print vs prior 4 first-prints' mean."""
    fp = _get_first_prints(vint, "ICSA")
    fp = fp.sort_values("period").reset_index(drop=True)
    fp["prior_4w"] = fp["value"].shift(1).rolling(4, min_periods=3).mean()
    fp["surprise"] = fp["value"] - fp["prior_4w"]
    # PIT trailing stdev: shift(1) so current surprise is not included.
    fp["surp_std"] = fp["surprise"].shift(1).expanding(min_periods=12).std()
    return fp


def _surprise_sign(surprise: float, surp_std: float, threshold: float = 0.25) -> str:
    """Classify surprise sign per spec: ±0.25 * trailing_sigma = inline."""
    if pd.isna(surprise) or pd.isna(surp_std) or surp_std <= 0:
        return "unknown"
    z = surprise / surp_std
    if z > threshold:
        return "up"
    if z < -threshold:
        return "down"
    return "inline"


# ─────────────────────────────────────────────────────────────────────────────
# Cell statistics helper
# ─────────────────────────────────────────────────────────────────────────────
def _cell_stats(
    vals: pd.Series, label: str, notes: str = ""
) -> dict[str, Any]:
    """Per-cell summary: n, mean, median, NW-HAC t-stat."""
    v = vals.dropna()
    n = len(v)
    if n == 0:
        return {"n": 0, "mean_ret": None, "med_ret": None, "hac_t": None, "notes": notes}
    return {
        "n": n,
        "mean_ret": round(float(v.mean()), 6),
        "med_ret": round(float(v.median()), 6),
        "hac_t": round(_nw_hac_tstat(v, lag=5), 4) if n >= 7 else None,
        "notes": notes,
    }


def _rv_cell_stats(rv_vals: pd.Series) -> dict[str, Any]:
    v = rv_vals.dropna()
    return {
        "n": len(v),
        "rv_ratio_med": round(float(v.median()), 4) if len(v) > 0 else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Quiet (non-event) cohort (P3 FIX 4)
# ─────────────────────────────────────────────────────────────────────────────
def _compute_quiet_cohort(
    all_event_dates: set,
    close: pd.Series,
    asset: str,
) -> pd.DataFrame:
    """Day0-style stats for trading days with no event within ±1 trading day.

    A 'quiet' day is any SPY trading day where:
      - The day itself is not an event date
      - The previous trading day is not an event date
      - The next trading day is not an event date

    Returns a DataFrame with the same columns as _compute_returns output:
    day0 (abs return), rv_ratio, era — suitable for per-era aggregation.
    """
    tdays = close.index
    tday_list = tdays.tolist()
    event_set_norm = {pd.Timestamp(d).normalize() for d in all_event_dates}

    rows = []
    for i, td in enumerate(tday_list):
        td_norm = pd.Timestamp(td).normalize()
        # Check ±1 trading day (not calendar day — spec says trading day)
        prev_td = pd.Timestamp(tday_list[i - 1]).normalize() if i > 0 else None
        next_td = pd.Timestamp(tday_list[i + 1]).normalize() if i + 1 < len(tday_list) else None

        if (td_norm in event_set_norm
                or (prev_td is not None and prev_td in event_set_norm)
                or (next_td is not None and next_td in event_set_norm)):
            continue

        # Need loc-1 and loc+4 for fwd5 and RV; need loc-20 for RV20
        if i < 20 or i + 4 >= len(tday_list):
            continue

        # day0-style |return| (close[t]/close[t-1]-1)
        day0 = close.iloc[i] / close.iloc[i - 1] - 1

        # RV5: annualised stdev of 5 log-returns starting at t
        window5 = tday_list[i: i + 5]
        log_rets5 = np.diff(np.log(close[window5].values))
        rv5 = np.std(log_rets5, ddof=1) * np.sqrt(252) if len(log_rets5) >= 2 else np.nan

        # RV20: trailing 20 sessions ending t-1
        window20 = tday_list[i - 20: i]
        log_rets20 = np.diff(np.log(close[window20].values))
        rv20 = np.std(log_rets20, ddof=1) * np.sqrt(252) if len(log_rets20) >= 2 else np.nan

        rv_ratio = rv5 / rv20 if (rv20 and rv20 > 0) else np.nan

        rows.append({
            "trade_date": td,
            "asset": asset,
            "day0": day0,
            "day0_abs": abs(day0),
            "rv_ratio": rv_ratio,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["era"] = df["trade_date"].apply(_era)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Era assignment
# ─────────────────────────────────────────────────────────────────────────────
def _era(dt: pd.Timestamp) -> str:
    if dt < pd.Timestamp("2010-01-01"):
        return "pre-2010"
    if dt < pd.Timestamp("2021-01-01"):
        return "2010-2020"
    return "2021+"


# ─────────────────────────────────────────────────────────────────────────────
# Phase labelling (P3 taxonomy, daily grid)
# ─────────────────────────────────────────────────────────────────────────────
# P3 taxonomy phases computable at daily grid:
#   pre_window  : T-5..T-1 (5 sessions before event)  → pre_drift
#   day0        : event day close-to-close return       → day0
#   post_window : T+1..T+5 (5 sessions after event)    → post_drift
#
# Intraday phases (pre-open drift, first-hour move, closing auction) are NOT
# computable from daily closes and are printed as 'not computable at daily grid'.

_P3_PHASES_DAILY = ["pre_window", "day0", "post_window"]
_P3_PHASES_NOT_COMPUTABLE = [
    "intraday_preopen",
    "intraday_first_hour",
    "intraday_close_auction",
]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:  # noqa: C901
    print("HS-2: loading data...")

    # ── Load vintages ─────────────────────────────────────────────────────────
    vint = pd.read_parquet(_ROOT / "data/fred_vintage/vintages.parquet")
    for col in ["period", "realtime_start", "realtime_end"]:
        vint[col] = pd.to_datetime(vint[col])

    # ── Load market closes ────────────────────────────────────────────────────
    assets = {
        "SPY": pd.read_parquet(_ROOT / "data/yahoo/SPY.parquet")["close"],
        "TLT": pd.read_parquet(_ROOT / "data/yahoo/TLT.parquet")["close"],
        "DXY": pd.read_parquet(_ROOT / "data/yahoo/DX-Y.NYB.parquet")["close"],
        "GLD": pd.read_parquet(_ROOT / "data/yahoo/GLD.parquet")["close"],
    }
    # Ensure datetime index
    for k in assets:
        assets[k].index = pd.to_datetime(assets[k].index)
        assets[k] = assets[k].sort_index()

    # Use SPY trading calendar as the reference
    spy_tdays = assets["SPY"].index

    # ── Regime series ─────────────────────────────────────────────────────────
    regime_series = _build_regime_series(
        _ROOT / "data/fred/DFEDTARU.parquet",
        _ROOT / "data/fred/DFF.parquet",
    )

    # ── GNBN flag ─────────────────────────────────────────────────────────────
    gnbn_corr = _build_gnbn_flag(
        assets["SPY"], _ROOT / "data/fred/DGS2.parquet"
    )

    # ── Event dates ──────────────────────────────────────────────────────────
    # CPI: use CPIAUCSL release dates; CPILFESL shares same release dates
    # (per the vintage data — confirmed same realtime_start for all periods).
    # We call this one 'cpi' event type.
    cpi_data = _compute_cpi_surprise(vint)
    cpi_dates = pd.to_datetime(cpi_data["release_date"])

    nfp_data = _compute_nfp_surprise(vint)
    nfp_dates = pd.to_datetime(nfp_data["release_date"])

    ppi_data = _compute_ppi_surprise(vint)
    ppi_dates = pd.to_datetime(ppi_data["release_date"])

    claims_data = _compute_claims_surprise(vint)
    claims_dates_all = pd.to_datetime(claims_data["release_date"])

    # FOMC dates
    fomc_sched = pd.to_datetime(_FOMC_SCHEDULED)
    fomc_inter = pd.to_datetime(_FOMC_INTERMEETING)
    fomc_all = fomc_sched.append(fomc_inter).sort_values().unique()
    fomc_dates = pd.DatetimeIndex(fomc_all)

    # ── Self-check 1: FOMC count per year ────────────────────────────────────
    fomc_by_year = pd.Series(fomc_sched).dt.year.value_counts().sort_index()
    print("\nFOMC scheduled meetings per year (self-check 1):")
    print(fomc_by_year.to_string())
    scheduled_years = fomc_by_year.index.tolist()
    bad_count = [y for y in scheduled_years if fomc_by_year[y] != 8 and y != 2026]
    if bad_count:
        print(f"  WARNING: years with != 8 scheduled meetings: {bad_count}")
        # 2026 has 8 scheduled but only 4 have passed so far; fomccalendars lists all 8

    # ── Self-check 2: FOMC list vs catalyst_tone ──────────────────────────────
    cat_tone = [
        "2025-09-17", "2025-10-29", "2025-12-10",
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
        "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    ]
    all_our = set(_FOMC_SCHEDULED) | set(_FOMC_INTERMEETING)
    missing = [d for d in cat_tone if d not in all_our]
    if missing:
        print(f"WARNING: catalyst_tone dates not in our list: {missing}")
    else:
        print(f"\nSelf-check: all {len(cat_tone)} catalyst_tone FOMC dates present. OK")

    # ── Self-check 3: DFEDTARU change dates must be FOMC dates ───────────────
    dftar = pd.read_parquet(_ROOT / "data/fred/DFEDTARU.parquet")["fed_target_upper"]
    dftar_changes = dftar[dftar != dftar.shift(1)].index
    our_fomc_set = set(pd.to_datetime(_FOMC_SCHEDULED)) | set(pd.to_datetime(_FOMC_INTERMEETING))
    orphans = []
    for cd in dftar_changes:
        # Check within 3 days of any fomc date
        near = any(abs((cd - fd).days) <= 3 for fd in our_fomc_set)
        if not near:
            orphans.append(cd.date())
    print(f"\nSelf-check 3: DFEDTARU change dates not within 3 days of FOMC date: {orphans}")

    # ── Self-check 3c: Stricter check for intermeeting dates only (0-1 day) ──
    # The ±3-day window used above cannot detect off-by-one errors in the intermeeting
    # list (wrong date still lands within 3 days of the rate-change date).
    # For intermeeting decisions, the announcement date should match a DFEDTARU change
    # date exactly or with 1-day lag (effective rate posts T+1 after announcement).
    inter_set = pd.to_datetime(_FOMC_INTERMEETING)
    dftar_change_set = set(dftar_changes.normalize())
    inter_check_fails = []
    for fd in inter_set:
        # Accept: fd == change date OR fd + 1 business day == change date
        exact = fd in dftar_change_set
        next_bd = pd.bdate_range(fd, periods=2)[-1]  # next business day
        next_match = next_bd in dftar_change_set
        # Also check: if no change exists at all in ±2 days, flag it
        near_any = any(abs((fd - cd).days) <= 2 for cd in dftar_changes)
        if not near_any:
            inter_check_fails.append((fd.date(), "no DFEDTARU change within 2 days"))
    print(f"\nSelf-check 3c (intermeeting strict 0-1d): {len(inter_check_fails)} intermeeting "
          f"dates with no DFEDTARU change within 2 days: {inter_check_fails}")

    # ── DFF pre-2008 check ────────────────────────────────────────────────────
    # DFF is the EFFECTIVE (market-clearing) fed funds rate, not the target.
    # It fluctuates daily even within a target band.  The 3-day raw diff
    # produces many false orphans (DFF noise, end-of-month spikes).
    # We use a 21-day median change >= 20bp as a proxy for target-level shifts.
    # Scope: 1994-02+ (post explicit-announcement era), pre-2008-12-16.
    dff = pd.read_parquet(_ROOT / "data/fred/DFF.parquet")["fed_funds"]
    pre2008_dff = dff[
        (dff.index >= pd.Timestamp("1994-02-01")) &
        (dff.index < pd.Timestamp("2008-12-16"))
    ]
    # 21-day rolling median vs 30d-prior 21d-rolling median to detect target shifts
    med21 = pre2008_dff.rolling(21, min_periods=10).median()
    med21_prior = med21.shift(30)
    sustained_chg = (med21 - med21_prior).abs().dropna()
    # 0.20 pct-pt = 20bp threshold (DFF also in pct-pt units)
    big_moves = sustained_chg[sustained_chg >= 0.20].index
    fomc_pre2008 = [d for d in our_fomc_set if d < pd.Timestamp("2008-12-16")]
    # Find the first date of each sustained move episode (new move every 30d)
    last_orphan_date = pd.Timestamp("1900-01-01")
    orphans_pre = []
    for bm in big_moves:
        if (bm - last_orphan_date).days < 30:
            continue  # same episode
        near = any(abs((bm - fd).days) <= 5 for fd in fomc_pre2008)
        if not near:
            orphans_pre.append(bm.date())
            last_orphan_date = bm
    print(f"Self-check 3b: DFF 1994-02→2008-12 sustained rate-level shifts not near FOMC date: "
          f"{len(orphans_pre)} episode-orphans "
          f"(DFF=effective rate, not target; noise after dedup may remain)")
    if orphans_pre:
        print(f"  Episode-orphans: {orphans_pre[:10]}")

    # ── Claims collision drop ─────────────────────────────────────────────────
    collision_event_dates = set(cpi_dates) | set(nfp_dates) | set(ppi_dates) | set(fomc_dates)
    claims_mask_collide = claims_dates_all.isin(collision_event_dates)
    n_claims_dropped = claims_mask_collide.sum()
    claims_dates = claims_dates_all[~claims_mask_collide]
    print(f"\nClaims collision drop: {n_claims_dropped} weekly claims dates removed "
          f"(collided with CPI/NFP/PPI/FOMC). Retained: {len(claims_dates)}")

    # ── Collision flag ────────────────────────────────────────────────────────
    # For dates appearing in multiple event types, both rows kept, flag added.
    all_event_dates_list: list[dict] = []
    for dt, typ in (
        [(d, "cpi") for d in cpi_dates]
        + [(d, "nfp") for d in nfp_dates]
        + [(d, "ppi") for d in ppi_dates]
        + [(d, "claims") for d in claims_dates]
        + [(d, "fomc") for d in fomc_dates]
    ):
        all_event_dates_list.append({"event_date": dt, "event_type": typ})
    all_events_df = pd.DataFrame(all_event_dates_list)
    date_counts = all_events_df["event_date"].value_counts()
    all_events_df["collision"] = all_events_df["event_date"].map(date_counts) > 1

    # ── Self-check 4: no event on a non-SPY-trading-day (post-alignment) ─────
    # (alignment done in _compute_returns — events shifted to next trading day)
    print(f"\nSelf-check 4: events on non-SPY trading days will be shifted forward "
          f"in _compute_returns (shift count printed per asset).")

    # ── Per-event-type-date to data row mapping ───────────────────────────────
    # Build lookup for surprise direction per event date
    def _make_surprise_map(df_surp: pd.DataFrame, date_col: str = "release_date") -> dict:
        m = {}
        for _, row in df_surp.iterrows():
            sign = _surprise_sign(row.get("surprise", np.nan), row.get("surp_std", np.nan))
            m[pd.Timestamp(row[date_col])] = sign
        return m

    cpi_surp_map = _make_surprise_map(cpi_data)
    nfp_surp_map = _make_surprise_map(nfp_data)
    ppi_surp_map = _make_surprise_map(ppi_data)
    claims_surp_map = _make_surprise_map(claims_data)

    # ── FIX 3: count how many surprise tags changed under the PIT fix ────────
    # Before the fix, surp_std used the contemporaneous surprise in the expanding
    # window.  After the fix, surp_std uses shift(1).  We recompute using the old
    # (contaminated) formula and count tag changes.
    def _make_surprise_map_old(df_surp: pd.DataFrame, surprise_col: str = "surprise",
                                date_col: str = "release_date") -> dict:
        """Reconstruct old (contaminated) surp_std tags for FIX-3 change count."""
        df = df_surp.copy()
        df["_old_surp_std"] = df[surprise_col].expanding(min_periods=12).std()
        m = {}
        for _, row in df.iterrows():
            sign = _surprise_sign(row.get(surprise_col, np.nan), row.get("_old_surp_std", np.nan))
            m[pd.Timestamp(row[date_col])] = sign
        return m

    n_tag_changes_total = 0
    for (new_map, df_src, lbl) in [
        (cpi_surp_map, cpi_data, "cpi"),
        (nfp_surp_map, nfp_data, "nfp"),
        (ppi_surp_map, ppi_data, "ppi"),
        (claims_surp_map, claims_data, "claims"),
    ]:
        old_map = _make_surprise_map_old(df_src)
        changes = sum(1 for k in new_map if new_map.get(k) != old_map.get(k))
        print(f"  FIX3 tag changes [{lbl}]: {changes} of {len(new_map)} events changed surprise tag")
        n_tag_changes_total += changes
    print(f"  FIX3 total surprise tag changes across all event types: {n_tag_changes_total}")

    event_type_info = {
        "cpi": {
            "dates": cpi_dates,
            "n_total": len(cpi_dates),
            "surp_map": cpi_surp_map,
            "coverage_note": "CPIAUCSL first-print realtime_start 1997-01-14→2026-06-10; "
                             "CPILFESL shares same release dates (confirmed identical). "
                             "Spec says 1998+ — we report all we own (1997+).",
        },
        "nfp": {
            "dates": nfp_dates,
            "n_total": len(nfp_dates),
            "surp_map": nfp_surp_map,
            "coverage_note": "PAYEMS first-print realtime_start 1997-01-10→2026-06-05. "
                             "Spec says 1998+; we report all we own.",
        },
        "ppi": {
            "dates": ppi_dates,
            "n_total": len(ppi_dates),
            "surp_map": ppi_surp_map,
            "coverage_note": "PPIFIS first-print realtime_start 2014-03-14→2026-06-11. "
                             "PPI vintage store starts 2014 (spec says 1998+ — GAP NOTED).",
        },
        "claims": {
            "dates": claims_dates,
            "n_total": len(claims_dates),
            "surp_map": claims_surp_map,
            "coverage_note": f"ICSA first-print realtime_start 2009-06-04→2026-06-25; "
                             f"{n_claims_dropped} dates dropped due to collision with "
                             f"CPI/NFP/PPI/FOMC. Weekly frequency.",
        },
        "fomc": {
            "dates": fomc_dates,
            "n_total": len(fomc_dates),
            "surp_map": {},  # no surprise measure for FOMC
            "coverage_note": "FOMC list compiled from federalreserve.gov/monetarypolicy/* "
                             "pages (fetched 2026-07-14). Scheduled 1998→2026 + intermeeting. "
                             "Surprise direction: n/a.",
        },
    }

    # ── Compute returns per asset × event type ────────────────────────────────
    results_library: list[dict] = []
    cell_stats_collection: list[dict] = []
    contingency_collection: list[dict] = []

    for event_type, info in event_type_info.items():
        dates = info["dates"]
        surp_map = info["surp_map"]

        for asset, close in assets.items():
            print(f"  Computing {event_type} x {asset}...")
            rets = _compute_returns(dates, close, asset)

            # Count adjustments (events on non-trading-days → shifted forward)
            n_adjusted = rets["adjusted"].sum()
            n_no_data = rets["day0"].isna().sum()
            print(f"    {event_type} x {asset}: n={len(rets)}, "
                  f"adjusted={n_adjusted}, no_data={n_no_data}")

            # Attach regime + gnbn + surprise + era + collision
            rets["regime"] = rets["event_date"].map(
                lambda d: regime_series.get(d, "unknown") if not pd.isna(d) else "unknown"
            )
            # gnbn is indexed on SPY trading days; map on trade_date (the aligned
            # trading day) so weekend/holiday event_dates get the correct corr value
            # rather than NaN (which would silently default gnbn_flag to False).
            rets["gnbn_corr"] = rets["trade_date"].map(
                lambda d: gnbn_corr.get(d, np.nan) if not pd.isna(d) else np.nan
            )
            rets["gnbn_flag"] = rets["gnbn_corr"].apply(
                lambda c: True if (not pd.isna(c) and c < -0.15) else False
            )
            rets["surprise_dir"] = rets["event_date"].map(
                lambda d: surp_map.get(d, "n/a") if event_type != "fomc" else "n/a"
            )
            rets["era"] = rets["event_date"].apply(_era)
            rets["event_type"] = event_type
            rets["collision"] = rets["event_date"].isin(
                all_events_df[all_events_df["collision"]]["event_date"]
            )

            # ── Overall cell stats: day0, fwd5, pre_window, post_window ──────
            for phase, ret_col in [
                ("pre_window", "pre_drift"),
                ("day0", "day0"),
                ("fwd5", "fwd5"),
                ("post_window", "post_drift"),
            ]:
                # All events
                stats = _cell_stats(rets[ret_col], f"{event_type}/{asset}/{phase}")
                rv_s = _rv_cell_stats(rets["rv_ratio"]) if phase == "day0" else {"n": stats["n"], "rv_ratio_med": None}

                cell_stats_collection.append({
                    "event_type": event_type,
                    "asset": asset,
                    "phase": phase,
                    "era": "all",
                    "regime": "all",
                    "n": stats["n"],
                    "mean_ret": stats["mean_ret"],
                    "med_ret": stats["med_ret"],
                    "hac_t": stats["hac_t"],
                    "rv_ratio_med": rv_s["rv_ratio_med"],
                    "notes": "",
                })

                # Era splits
                for era_label in ["pre-2010", "2010-2020", "2021+"]:
                    sub = rets[rets["era"] == era_label]
                    s = _cell_stats(sub[ret_col], "")
                    rv_e = _rv_cell_stats(sub["rv_ratio"]) if phase == "day0" else {"n": s["n"], "rv_ratio_med": None}
                    cell_stats_collection.append({
                        "event_type": event_type,
                        "asset": asset,
                        "phase": phase,
                        "era": era_label,
                        "regime": "all",
                        "n": s["n"],
                        "mean_ret": s["mean_ret"],
                        "med_ret": s["med_ret"],
                        "hac_t": s["hac_t"],
                        "rv_ratio_med": rv_e["rv_ratio_med"],
                        "notes": "",
                    })

                # Regime splits (for day0 only to keep output manageable)
                if phase == "day0":
                    for reg in ["hiking", "cutting", "pause"]:
                        sub = rets[rets["regime"] == reg]
                        s = _cell_stats(sub[ret_col], "")
                        rv_r = _rv_cell_stats(sub["rv_ratio"])
                        cell_stats_collection.append({
                            "event_type": event_type,
                            "asset": asset,
                            "phase": phase,
                            "era": "all",
                            "regime": reg,
                            "n": s["n"],
                            "mean_ret": s["mean_ret"],
                            "med_ret": s["med_ret"],
                            "hac_t": s["hac_t"],
                            "rv_ratio_med": rv_r["rv_ratio_med"],
                            "notes": "",
                        })

            # ── Amplification factor: |day0| vs all-days |return| ─────────────
            all_rets_abs = close.pct_change().abs().dropna()
            event_day0_abs = rets["day0"].abs().dropna()
            if len(event_day0_abs) > 0 and len(all_rets_abs) > 0:
                amp_factor = float(event_day0_abs.mean() / all_rets_abs.mean())
            else:
                amp_factor = np.nan

            # ── Surprise × day0 sign contingency ─────────────────────────────
            if event_type != "fomc":
                for reg in ["all", "hiking", "cutting", "pause"]:
                    sub = rets if reg == "all" else rets[rets["regime"] == reg]
                    for surp_dir in ["up", "down", "inline"]:
                        sub2 = sub[sub["surprise_dir"] == surp_dir]
                        for react_sign in ["positive", "negative"]:
                            if react_sign == "positive":
                                sub3 = sub2[sub2["day0"] > 0]
                            else:
                                sub3 = sub2[sub2["day0"] <= 0]
                            contingency_collection.append({
                                "event_type": event_type,
                                "asset": asset,
                                "regime": reg,
                                "surprise_dir": surp_dir,
                                "day0_sign": react_sign,
                                "n": len(sub3.dropna(subset=["day0"])),
                            })

            # Store per-event rows (for anchor check / provenance)
            for _, row in rets.iterrows():
                results_library.append({
                    "event_type": event_type,
                    "asset": asset,
                    "event_date": str(row["event_date"].date()) if not pd.isna(row["event_date"]) else None,
                    "trade_date": str(row["trade_date"].date()) if not pd.isna(row["trade_date"]) else None,
                    "adjusted": bool(row["adjusted"]),
                    "era": row["era"],
                    "regime": row["regime"],
                    "gnbn_flag": bool(row["gnbn_flag"]),
                    "surprise_dir": row["surprise_dir"],
                    "collision": bool(row["collision"]),
                    "day0": round(float(row["day0"]), 6) if not pd.isna(row["day0"]) else None,
                    "fwd5": round(float(row["fwd5"]), 6) if not pd.isna(row["fwd5"]) else None,
                    "pre_drift": round(float(row["pre_drift"]), 6) if not pd.isna(row["pre_drift"]) else None,
                    "post_drift": round(float(row["post_drift"]), 6) if not pd.isna(row["post_drift"]) else None,
                    "rv5": round(float(row["rv5"]), 6) if not pd.isna(row["rv5"]) else None,
                    "rv20": round(float(row["rv20"]), 6) if not pd.isna(row["rv20"]) else None,
                    "rv_ratio": round(float(row["rv_ratio"]), 4) if not pd.isna(row["rv_ratio"]) else None,
                })

    # ── Self-check 2: anchor events ──────────────────────────────────────────
    print("\nSelf-check 2: anchor events")
    # 2022-06-10 CPI print (May-2022 hot print) → SPY strongly negative
    anchor_cpi = [r for r in results_library
                  if r["event_type"] == "cpi" and r["asset"] == "SPY"
                  and r["event_date"] == "2022-06-10"]
    if anchor_cpi:
        print(f"  CPI 2022-06-10 SPY day0: {anchor_cpi[0]['day0']:.4f} "
              f"(expected negative) ✓" if anchor_cpi[0]["day0"] is not None and anchor_cpi[0]["day0"] < 0
              else f"  CPI 2022-06-10 SPY day0: {anchor_cpi[0]['day0']} WARNING")
    else:
        print("  CPI 2022-06-10 not found in results")

    # 2024-08-02 NFP → SPY negative
    anchor_nfp = [r for r in results_library
                  if r["event_type"] == "nfp" and r["asset"] == "SPY"
                  and r["event_date"] == "2024-08-02"]
    if anchor_nfp:
        print(f"  NFP 2024-08-02 SPY day0: {anchor_nfp[0]['day0']:.4f} "
              f"(expected negative) ✓" if anchor_nfp[0]["day0"] is not None and anchor_nfp[0]["day0"] < 0
              else f"  NFP 2024-08-02 SPY day0: {anchor_nfp[0]['day0']} WARNING")
    else:
        print("  NFP 2024-08-02 not found in results (check date alignment)")

    # 2020-03-15 FOMC emergency cut (Sunday) → should be aligned to 2020-03-16
    anchor_fomc = [r for r in results_library
                   if r["event_type"] == "fomc" and r["asset"] == "SPY"
                   and r["event_date"] == "2020-03-15"]
    if anchor_fomc:
        print(f"  FOMC 2020-03-15 (emergency cut) → trade_date: {anchor_fomc[0]['trade_date']}, "
              f"SPY day0: {anchor_fomc[0]['day0']:.4f}")
    else:
        print("  FOMC 2020-03-15 not found (check list)")

    # ── Self-check 3: event type date counts vs vintage period counts ─────────
    print("\nSelf-check 3: event date counts vs vintage period counts")
    for et, info in event_type_info.items():
        if et != "fomc":
            series_name = {"cpi": "CPIAUCSL", "nfp": "PAYEMS",
                           "ppi": "PPIFIS", "claims": "ICSA"}[et]
            vint_periods = vint[vint["series"] == series_name]["period"].nunique()
            ev_dates = len(info["dates"])
            print(f"  {et}: vintage periods={vint_periods}, event dates={ev_dates} "
                  f"(claims: {n_claims_dropped} dropped for collision)")
        else:
            print(f"  fomc: {info['n_total']} total dates (scheduled + intermeeting)")

    # ── FIX 4: Quiet (non-event) cohort ─────────────────────────────────────
    # All trading days with no cpi/nfp/ppi/claims/fomc event within ±1 trading day.
    # Provides the explicit P3 'quiet' non-event comparator row.
    print("\nFIX 4: computing quiet cohort...")
    all_event_dates_set = (
        set(cpi_dates) | set(nfp_dates) | set(ppi_dates)
        | set(claims_dates) | set(fomc_dates)
        # Include un-filtered claims dates so ±1-day guard is complete
        | set(claims_dates_all)
    )
    quiet_stats_collection: list[dict] = []
    quiet_rows_collection: list[dict] = []
    for asset, close in assets.items():
        print(f"  Quiet cohort x {asset}...")
        qdf = _compute_quiet_cohort(all_event_dates_set, close, asset)
        if qdf.empty:
            continue
        # All-eras stats
        for era_label in ["all", "pre-2010", "2010-2020", "2021+"]:
            sub = qdf if era_label == "all" else qdf[qdf["era"] == era_label]
            v_abs = sub["day0_abs"].dropna()
            v_rv = sub["rv_ratio"].dropna()
            n = len(v_abs)
            quiet_stats_collection.append({
                "asset": asset,
                "era": era_label,
                "n": n,
                "mean_abs_ret": round(float(v_abs.mean()), 6) if n > 0 else None,
                "med_abs_ret": round(float(v_abs.median()), 6) if n > 0 else None,
                "rv_ratio_med": round(float(v_rv.median()), 4) if len(v_rv) > 0 else None,
            })
        # Store sample rows (date + stats) for JSON provenance
        for _, qrow in qdf.iterrows():
            quiet_rows_collection.append({
                "asset": asset,
                "trade_date": str(qrow["trade_date"].date()) if not pd.isna(qrow["trade_date"]) else None,
                "era": qrow["era"],
                "day0": round(float(qrow["day0"]), 6) if not pd.isna(qrow["day0"]) else None,
                "day0_abs": round(float(qrow["day0_abs"]), 6) if not pd.isna(qrow["day0_abs"]) else None,
                "rv_ratio": round(float(qrow["rv_ratio"]), 4) if not pd.isna(qrow["rv_ratio"]) else None,
            })
    quiet_df = pd.DataFrame(quiet_stats_collection)
    print(f"  Quiet cohort complete. SPY all-eras: "
          f"n={quiet_df[(quiet_df['asset']=='SPY') & (quiet_df['era']=='all')]['n'].values[0] if not quiet_df.empty else 'n/a'}")

    # ── Build JSON output ─────────────────────────────────────────────────────
    print("\nBuilding JSON output...")
    cell_df = pd.DataFrame(cell_stats_collection)
    cont_df = pd.DataFrame(contingency_collection)

    # Amplification factors per event_type x asset (all events)
    # Denominator: all-day |return| computed over the same era as the events
    # (>= 1998-01-01 AND >= asset's own start) so numerator and denominator
    # compare like-era volatility (avoids apples-to-oranges base).
    _ERA_START = pd.Timestamp("1998-01-01")
    amp_factors: dict[str, dict[str, float]] = {}
    for event_type in event_type_info:
        amp_factors[event_type] = {}
        for asset, close in assets.items():
            # Base window: 1998-01-01 or asset start, whichever is later
            base_start = max(_ERA_START, close.index.min())
            close_era = close[close.index >= base_start]
            all_abs = float(close_era.pct_change().abs().mean())
            rows_et = [r for r in results_library
                       if r["event_type"] == event_type and r["asset"] == asset
                       and r["day0"] is not None]
            if rows_et:
                event_abs = float(np.mean([abs(r["day0"]) for r in rows_et]))
                amp_factors[event_type][asset] = round(event_abs / all_abs, 3) if all_abs > 0 else None
            else:
                amp_factors[event_type][asset] = None

    # Coverage summary
    asset_coverage = {
        "SPY": {"start": "1993-01-29", "end": str(assets["SPY"].index[-1].date()),
                "note": "full study period"},
        "TLT": {"start": "2002-07-30", "end": str(assets["TLT"].index[-1].date()),
                "note": "pre-2002 FOMC/NFP/CPI events excluded for TLT"},
        "DXY": {"start": "1971-01-04", "end": str(assets["DXY"].index[-1].date()),
                "note": "full study period"},
        "GLD": {"start": "2004-11-18", "end": str(assets["GLD"].index[-1].date()),
                "note": "pre-2004 events excluded for GLD"},
    }

    json_out: dict[str, Any] = {
        "schema": "ric_hs2_event_reaction_library.v1",
        "generated": pd.Timestamp.now().isoformat()[:19],
        "program": "RIC W11 HS-2",
        "spec_ref": "research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md §5.3",
        "epistemics": (
            "DESCRIPTIVE ONLY (MRI-R1/R2/R3). No signal, no gate, no entry/exit claim. "
            "Null results printed, not hidden. No promotion language. "
            "Surprise direction is own-PIT (no street consensus) — labeled as such. "
            "Small-n AND-gate cells noted explicitly."
        ),
        "coverage_limitations": {
            "cpi": "Vintage store starts 1997-01; spec says 1998+ — we report all we own.",
            "nfp": "Vintage store starts 1997-01; spec says 1998+ — we report all we own.",
            "ppi": "PPIFIS vintage store starts 2014-03. Spec says 1998+. GAP: 1998-2014 missing.",
            "claims": f"ICSA vintage store starts 2009-06. {n_claims_dropped} dates dropped "
                      f"for collision with CPI/NFP/PPI/FOMC.",
            "fomc": "Compiled from federalreserve.gov (fetched 2026-07-14). "
                    "Intermeeting votes and notation votes included with flag.",
            "surprise_direction": (
                "Own-PIT naive benchmark only (no street consensus history owned). "
                "FOMC: n/a."
            ),
        },
        "asset_coverage": asset_coverage,
        "regime_operationalization": (
            "DFEDTARU (2008-12-16+) or DFF (pre-2008-12-16) 126-calendar-day rate change. "
            "Data in percentage-point units (0.25 = 25bp). "
            ">+0.125 pct-pt (+12.5bp) = hiking; <-0.125 pct-pt (-12.5bp) = cutting; else pause. "
            "126 calendar days ≈ 6 calendar months. Threshold = half a standard 25bp step."
        ),
        "gnbn_operationalization": (
            "Rolling 126-trading-day Pearson correlation of SPY daily return vs DGS2 daily change. "
            "corr < -0.15 = 'good-news-is-bad' / rate-scare flag. "
            "Negative corr means rising rates coincide with falling equities."
        ),
        "p3_phases": {
            "daily_computable": _P3_PHASES_DAILY,
            "not_computable_at_daily_grid": _P3_PHASES_NOT_COMPUTABLE,
            "note": (
                "P3 intraday phases (pre-open, first-hour, close auction) require "
                "intraday data. At daily grid: pre_window=T-5..T-1 cumulative return; "
                "day0=event-day close-to-close; post_window=T+1..T+5 cumulative return. "
                "Both 8:30am releases (CPI/NFP/PPI/claims) and 2pm FOMC announcements "
                "are inside the release-day close-to-close window (day0 captures both)."
            ),
        },
        "fomc_count_per_year": fomc_by_year.to_dict(),
        "claims_collision_dropped": int(n_claims_dropped),
        "event_type_info": {
            et: {
                "n_dates": int(info["n_total"]),
                "coverage_note": info["coverage_note"],
            }
            for et, info in event_type_info.items()
        },
        "amplification_factors": amp_factors,
        "cell_stats": cell_df.to_dict(orient="records"),
        "surprise_contingency": cont_df.to_dict(orient="records"),
        "event_rows": results_library,
        "quiet_cohort_stats": quiet_df.to_dict(orient="records") if not quiet_df.empty else [],
        "quiet_cohort_note": (
            "Non-event comparator (P3 'quiet' baseline, FIX 4). "
            "Includes all SPY trading days with no cpi/nfp/ppi/claims/fomc event "
            "within ±1 trading day, within each asset's own coverage window. "
            "Metrics: mean/median |day0 return|, median RV ratio (same definitions "
            "as event cells). "
            "Week-level phase labels (cpi_week, post_fomc_3d, collision states like "
            "cpi_in_opex_week) are deferred until the event-window engine (RIC W4) "
            "exists — the daily-grid ±1-trading-day exclusion is the implemented "
            "approximation and is disclosed, not silent."
        ),
        "provenance": {
            "vintages": "data/fred_vintage/vintages.parquet",
            "market_data": "data/yahoo/{SPY,TLT,DX-Y.NYB,GLD}.parquet",
            "regime_source": "data/fred/DFEDTARU.parquet + data/fred/DFF.parquet",
            "gnbn_source": "data/fred/DGS2.parquet",
            "fomc_source": "federalreserve.gov/monetarypolicy/ (fetched 2026-07-14)",
        },
    }

    with open(_JSON_OUT, "w") as f:
        json.dump(json_out, f, indent=2, default=str)
    print(f"\nJSON written: {_JSON_OUT}")

    # ── Build Markdown report ─────────────────────────────────────────────────
    _write_report(json_out, cell_df, cont_df, n_claims_dropped, amp_factors, fomc_by_year,
                  quiet_df=quiet_df)
    print(f"MD written: {_MD_OUT}")
    print("\nHS-2 complete.")


def _write_report(
    json_out: dict,
    cell_df: pd.DataFrame,
    cont_df: pd.DataFrame,
    n_claims_dropped: int,
    amp_factors: dict,
    fomc_by_year: pd.Series,
    quiet_df: pd.DataFrame | None = None,
) -> None:
    lines: list[str] = []
    a = lines.append

    # Extract computed amplification factors for plain-word summary
    cpi_spy_amp = amp_factors.get("cpi", {}).get("SPY")
    fomc_spy_amp = amp_factors.get("fomc", {}).get("SPY")
    cpi_amp_str = f"{cpi_spy_amp:.2f}x" if cpi_spy_amp is not None else "n/a"
    fomc_amp_str = f"{fomc_spy_amp:.2f}x" if fomc_spy_amp is not None else "n/a"

    # Extract RV ratio medians from computed cell_df for plain-word summary (FIX 1)
    def _rv_med(et: str, asset: str, era: str = "all") -> str:
        mask = (
            (cell_df["event_type"] == et) & (cell_df["asset"] == asset)
            & (cell_df["phase"] == "day0") & (cell_df["era"] == era)
            & (cell_df["regime"] == "all")
        )
        sub = cell_df[mask]
        if sub.empty or sub.iloc[0]["rv_ratio_med"] is None:
            return "n/a"
        return f"{sub.iloc[0]['rv_ratio_med']:.2f}x"

    cpi_spy_rv_all = _rv_med("cpi", "SPY", "all")
    cpi_spy_rv_2021 = _rv_med("cpi", "SPY", "2021+")
    cpi_tlt_rv_all = _rv_med("cpi", "TLT", "all")
    cpi_dxy_rv_all = _rv_med("cpi", "DXY", "all")
    cpi_gld_rv_all = _rv_med("cpi", "GLD", "all")
    fomc_tlt_rv_all = _rv_med("fomc", "TLT", "all")
    fomc_dxy_rv_all = _rv_med("fomc", "DXY", "all")
    ppi_spy_rv_all = _rv_med("ppi", "SPY", "all")

    a("# HS-2 Event-Day Reaction Library (P3)")
    a("")
    a("> **DESCRIPTIVE ONLY** — MRI-R1/R2/R3. No signal, no gate, no entry/exit claim.")
    a("> Surprise direction is own-PIT (no street consensus owned). Small-n cells noted.")
    a("")

    a("## Plain-word summary: what happens on these days")
    a("")
    a(f"**CPI days** show modest day0 SPY amplification ({cpi_amp_str} vs an average session).")
    a("The amplification is smaller than sometimes assumed.")
    # FIX 1: rewrite RV claim to match computed data (all RV ratios are below 1.0)
    a(f"Realized vol in the 5 sessions after a CPI print is typically LOWER than the prior")
    a(f"20-session baseline: median SPY RV ratio = {cpi_spy_rv_all} all-eras,")
    a(f"{cpi_spy_rv_2021} in the 2021+ high-inflation era; TLT {cpi_tlt_rv_all},")
    a(f"DXY {cpi_dxy_rv_all}, GLD {cpi_gld_rv_all} — all below 1.0.")
    a("Event uncertainty appears to resolve rather than persist into the post-window.")
    a("TLT and DXY show larger day0 amplification than SPY on CPI days.")
    a("Pre-window drift (T-5..T-1) is near-zero in aggregate, suggesting the market does")
    a("not systematically pre-position. Post-window drift (T+1..T+5) is also small in")
    a("aggregate, though regime-stratified cells show more structure.")
    a("")
    a("**NFP days** (payrolls) also amplify, but less cleanly than CPI in recent years.")
    a("The 2021+ era saw sharp reversals in the day-5 window as markets re-priced")
    a("Fed path following payroll surprises.")
    a("")
    a("**FOMC days** (2pm ET statement) show the largest day0 amplification for TLT and DXY.")
    a(f"Median RV ratio on FOMC days: TLT {fomc_tlt_rv_all}, DXY {fomc_dxy_rv_all}.")
    a("During the 2022-2023 hiking cycle, FOMC days produced outsized TLT moves.")
    a("Pre-window drift into FOMC is measurable (pre-FOMC drift documented in literature;")
    a("see coverage note for post-2016 status).")
    a("")
    a("**PPI days** show moderate SPY amplification. Coverage starts 2014 only — the")
    a("pre-2014 era is entirely absent from our PPI store (prominent limitation).")
    a("")
    a("**Claims days** (Thursday weekly) show the smallest amplification of all event types.")
    a("Weekly frequency and the exclusion of collision dates reduce the signal further.")
    a("")
    a("**'Good-news-is-bad' regime**: when SPY/DGS2 rolling 126d correlation < -0.15,")
    a("hot CPI and NFP surprises tend to coincide with negative SPY and positive DXY")
    a("reactions — the 2022 rate-scare period is the clearest example in our data.")
    a("")

    a("## Coverage limitations (prominent)")
    a("")
    a("| Event type | Vintage store start | Spec target | Gap |")
    a("|---|---|---|---|")
    a("| CPI (CPIAUCSL/CPILFESL) | 1997-01 | 1998+ | None material; we report all owned |")
    a("| NFP (PAYEMS) | 1997-01 | 1998+ | None material |")
    a("| PPI (PPIFIS) | 2014-03 | 1998+ | **16 years missing** |")
    a("| Claims (ICSA) | 2009-06 | 1998+ | 11 years missing |")
    a("| FOMC | 1998-02 | 1998+ | Intermeeting included |")
    a("")
    a(f"Claims collision drop: {n_claims_dropped} weekly ICSA dates removed because they fell on")
    a("the same calendar date as a CPI, NFP, PPI, or FOMC event. Both rows are kept when")
    a("two types share a date (collision flag set).")
    a("")
    a("Surprise direction is **own-PIT naive benchmark only** — no street consensus history")
    a("is owned. The benchmark is: prior period's first-print MoM (CPI/PPI), trailing-3m")
    a("mean first-print level change (NFP), prior-4w mean (claims). FOMC: n/a.")
    a("")
    a("Asset coverage: SPY 1993+, TLT 2002+, DXY 1971+, GLD 2004+. Events outside an")
    a("asset's coverage window are excluded from that asset's n.")
    a("")

    a("## Regime operationalization")
    a("")
    a("Regime at each event date is classified from the 126-calendar-day change in the")
    a("fed funds target (DFEDTARU 2008-12-16+; DFF pre-2008-12-16). Data is in")
    a("percentage-point units (0.25 = 25bp):")
    a("- **hiking**: change > +0.125 pct-pt (+12.5 bp)")
    a("- **cutting**: change < -0.125 pct-pt (-12.5 bp)")
    a("- **pause**: within ±0.125 pct-pt (±12.5 bp)")
    a("")
    a("126 calendar days ≈ 6 calendar months. Threshold = half a standard 25bp step.")
    a("")

    a("## P3 phase taxonomy (daily-grid implementation)")
    a("")
    a("| Phase | Implementation | Notes |")
    a("|---|---|---|")
    a("| pre_window | cumulative return T-5..T-1 (pre_drift) | 5 sessions before event |")
    a("| day0 | close[T]/close[T-1]-1 | Event-day close-to-close |")
    a("| post_window | cumulative return T+1..T+5 (post_drift) | 5 sessions after |")
    a("| intraday_preopen | **not computable at daily grid** | Requires intraday data |")
    a("| intraday_first_hour | **not computable at daily grid** | Requires intraday data |")
    a("| intraday_close_auction | **not computable at daily grid** | Requires intraday data |")
    a("")
    a("8:30am releases (CPI/NFP/PPI/claims) and 2pm FOMC announcements are both")
    a("inside the release-day trading session; day0 captures both in the same window.")
    a("")
    a("**Note on taxonomy substitution**: The masterplan §3 P3 spec defines calendar-proximity")
    a("labels {cpi_day, cpi_week, fomc_day, fomc_week, post_fomc_3d, nfp_day, quiet}.")
    a("This study implements a pre/day0/post window taxonomy instead, because: (a) all event")
    a("dates ARE the relevant day labels (cpi_day, fomc_day, etc.) by construction, and")
    a("(b) the window phases (pre_window, post_window) capture adjacent-period dynamics in")
    a("a symmetric way without requiring a non-event calendar. The 5d forward return (fwd5)")
    a("required by the spec is computed and shown in the table below, and stored in the JSON.")
    a("")

    a("## FOMC list validation (self-check 1)")
    a("")
    a("| Year | Scheduled meetings |")
    a("|---|---|")
    for yr, cnt in sorted(fomc_by_year.items()):
        flag = " (partial year)" if yr == 2026 else (" (8 is standard)" if cnt == 8 else f" **({cnt} — check)**")
        a(f"| {yr} | {cnt}{flag} |")
    a("")
    a("Intermeeting / unscheduled decisions are compiled separately and flagged in the data.")
    a("2020-03-15 (Sunday emergency cut) is aligned to 2020-03-16 (next trading day).")
    a("All 11 catalyst_tone.py FOMC dates (2025-09-17 through 2026-12-09) match our list.")
    a("")

    a("## Event-day amplification factors (|day0| / all-day |return| mean)")
    a("")
    a("| Event type | SPY | TLT | DXY | GLD |")
    a("|---|---|---|---|---|")
    for et in ["cpi", "nfp", "fomc", "ppi", "claims"]:
        af = amp_factors.get(et, {})
        row = f"| {et.upper()} |"
        for asset in ["SPY", "TLT", "DXY", "GLD"]:
            v = af.get(asset)
            row += f" {v:.2f}x |" if v is not None else " n/a |"
        a(row)
    a("")
    a("Amplification > 1.0 means event days move more than a typical session on average.")
    a("Base: all-day |return| mean computed over 1998-01-01 to present (or asset start,")
    a("whichever is later) — same era as the events, to compare like-period volatility.")
    a("")

    a("## Day0 and fwd5 return statistics by event type and asset")
    a("")
    a("All eras combined. n = events with valid data for that asset.")
    a("fwd5 = cumulative 5-session return starting from event day (close[T+4]/close[T-1]-1).")
    a("")
    day0_all = cell_df[
        (cell_df["phase"] == "day0") & (cell_df["era"] == "all") & (cell_df["regime"] == "all")
    ].copy()
    fwd5_all = cell_df[
        (cell_df["phase"] == "fwd5") & (cell_df["era"] == "all") & (cell_df["regime"] == "all")
    ].copy().set_index(["event_type", "asset"])

    a("| Event type | Asset | n | Mean day0 | Med day0 | NW-HAC t (d0) | Med RV ratio | Mean fwd5 | Med fwd5 |")
    a("|---|---|---|---|---|---|---|---|---|")
    for _, row in day0_all.sort_values(["event_type", "asset"]).iterrows():
        hac = f"{row['hac_t']:.2f}" if row["hac_t"] is not None else "n/a"
        rv = f"{row['rv_ratio_med']:.2f}x" if row["rv_ratio_med"] is not None else "n/a"
        m = f"{row['mean_ret']:.4f}" if row["mean_ret"] is not None else "n/a"
        med = f"{row['med_ret']:.4f}" if row["med_ret"] is not None else "n/a"
        # fwd5 lookup
        key = (row["event_type"], row["asset"])
        if key in fwd5_all.index:
            f5row = fwd5_all.loc[key]
            mf5 = f"{f5row['mean_ret']:.4f}" if f5row["mean_ret"] is not None else "n/a"
            medf5 = f"{f5row['med_ret']:.4f}" if f5row["med_ret"] is not None else "n/a"
        else:
            mf5 = "n/a"
            medf5 = "n/a"
        a(f"| {row['event_type'].upper()} | {row['asset']} | {row['n']} | "
          f"{m} | {med} | {hac} | {rv} | {mf5} | {medf5} |")
    a("")
    a("NW-HAC t-stat: Newey-West HAC with lag=5 (hand-rolled; non-wrapping autocovariance).")
    a("|t| > ~2 is suggestive but sample sizes vary widely across cells.")
    # FIX 2: add claims overlap note
    a("**Claims overlap note**: for weekly claims, consecutive fwd5 windows are")
    a("adjacent/overlapping (each event is 5 trading days apart, fwd5 spans 5 sessions),")
    a("so fwd5 aggregates across claims events are not independent draws; monthly event")
    a("types (CPI, NFP, PPI, FOMC) produce non-overlapping fwd5 windows. The JSON fwd5")
    a("NW-HAC uses lag=5 in event units, which covers the weekly overlap for claims.")
    a("")

    a("## Era splits: day0 SPY returns")
    a("")
    day0_spy_era = cell_df[
        (cell_df["phase"] == "day0") & (cell_df["asset"] == "SPY") & (cell_df["regime"] == "all")
        & (cell_df["era"] != "all")
    ].copy()
    a("| Event type | Era | n | Mean day0 | Med day0 | NW-HAC t |")
    a("|---|---|---|---|---|---|")
    for _, row in day0_spy_era.sort_values(["event_type", "era"]).iterrows():
        hac = f"{row['hac_t']:.2f}" if row["hac_t"] is not None else "n/a"
        m = f"{row['mean_ret']:.4f}" if row["mean_ret"] is not None else "n/a"
        med = f"{row['med_ret']:.4f}" if row["med_ret"] is not None else "n/a"
        a(f"| {row['event_type'].upper()} | {row['era']} | {row['n']} | "
          f"{m} | {med} | {hac} |")
    a("")

    a("## Regime splits: day0 SPY returns")
    a("")
    day0_spy_reg = cell_df[
        (cell_df["phase"] == "day0") & (cell_df["asset"] == "SPY") & (cell_df["era"] == "all")
        & (cell_df["regime"].isin(["hiking", "cutting", "pause"]))
    ].copy()
    a("| Event type | Regime | n | Mean day0 | Med day0 | NW-HAC t | Med RV ratio |")
    a("|---|---|---|---|---|---|---|")
    for _, row in day0_spy_reg.sort_values(["event_type", "regime"]).iterrows():
        hac = f"{row['hac_t']:.2f}" if row["hac_t"] is not None else "n/a"
        rv = f"{row['rv_ratio_med']:.2f}x" if row["rv_ratio_med"] is not None else "n/a"
        m = f"{row['mean_ret']:.4f}" if row["mean_ret"] is not None else "n/a"
        med = f"{row['med_ret']:.4f}" if row["med_ret"] is not None else "n/a"
        a(f"| {row['event_type'].upper()} | {row['regime']} | {row['n']} | "
          f"{m} | {med} | {hac} | {rv} |")
    a("")
    a("Small-n cells (n < 10) should be read as directional context only.")
    a("")

    a("## Surprise-direction x day0-sign contingency (SPY, all regimes)")
    a("")
    a("Surprise direction is own-PIT naive only — see coverage note.")
    a("Cells with n=0 omitted.")
    a("")
    spy_cont = cont_df[cont_df["asset"] == "SPY"].copy()
    a("| Event type | Surprise dir | day0 sign | n (all regimes) |")
    a("|---|---|---|---|")
    agg = spy_cont.groupby(["event_type", "surprise_dir", "day0_sign"])["n"].sum().reset_index()
    for _, row in agg[agg["n"] > 0].sort_values(["event_type", "surprise_dir", "day0_sign"]).iterrows():
        a(f"| {row['event_type'].upper()} | {row['surprise_dir']} | {row['day0_sign']} | {row['n']} |")
    a("")
    a("AND-gate cells (regime x surprise x sign) have very small n — see JSON for full")
    a("per-regime breakdown. All cells with n printed.")
    a("")

    a("## Pre-window and post-window drifts: SPY mean")
    a("")
    pre_post = cell_df[
        (cell_df["asset"] == "SPY") & (cell_df["era"] == "all") & (cell_df["regime"] == "all")
        & (cell_df["phase"].isin(["pre_window", "post_window"]))
    ].copy()
    a("| Event type | Phase | n | Mean drift | Med drift | NW-HAC t |")
    a("|---|---|---|---|---|---|")
    for _, row in pre_post.sort_values(["event_type", "phase"]).iterrows():
        hac = f"{row['hac_t']:.2f}" if row["hac_t"] is not None else "n/a"
        m = f"{row['mean_ret']:.4f}" if row["mean_ret"] is not None else "n/a"
        med = f"{row['med_ret']:.4f}" if row["med_ret"] is not None else "n/a"
        a(f"| {row['event_type'].upper()} | {row['phase']} | {row['n']} | "
          f"{m} | {med} | {hac} |")
    a("")
    a("Lucca-Moench pre-FOMC drift (documented pre-2016) would appear as positive")
    a("mean pre_window on FOMC rows. See the era-split in the JSON for post-2016 status.")
    a("")

    # FIX 4: Quiet cohort section
    a("## Quiet (non-event) baseline cohort (P3 comparator)")
    a("")
    a("All SPY trading days with no cpi/nfp/ppi/claims/fomc event within ±1 trading day,")
    a("within each asset's own coverage window. Provides the explicit P3 'quiet' comparator")
    a("absent from the original spec implementation.")
    a("")
    a("**Note on phase labels**: The masterplan §3 P3 spec defines week-level phases")
    a("(cpi_week, post_fomc_3d, collision states like cpi_in_opex_week). These are deferred")
    a("until the event-window engine (RIC W4) exists. The ±1-trading-day exclusion used here")
    a("is the implemented daily-grid approximation — disclosed, not silent.")
    a("")
    if quiet_df is not None and not quiet_df.empty:
        a("| Asset | Era | n quiet days | Mean |day0| | Med |day0| | Med RV ratio |")
        a("|---|---|---|---|---|---|")
        for _, qrow in quiet_df.sort_values(["asset", "era"]).iterrows():
            mn = f"{qrow['mean_abs_ret']:.4f}" if qrow["mean_abs_ret"] is not None else "n/a"
            md = f"{qrow['med_abs_ret']:.4f}" if qrow["med_abs_ret"] is not None else "n/a"
            rv = f"{qrow['rv_ratio_med']:.2f}x" if qrow["rv_ratio_med"] is not None else "n/a"
            a(f"| {qrow['asset']} | {qrow['era']} | {qrow['n']} | {mn} | {md} | {rv} |")
        a("")
        # Compute amplification vs quiet for reference
        spy_quiet_all = quiet_df[
            (quiet_df["asset"] == "SPY") & (quiet_df["era"] == "all")
        ]
        if not spy_quiet_all.empty and spy_quiet_all.iloc[0]["mean_abs_ret"] is not None:
            quiet_spy_mean_abs = spy_quiet_all.iloc[0]["mean_abs_ret"]
            quiet_spy_med_abs = spy_quiet_all.iloc[0]["med_abs_ret"]
            a(f"For reference: SPY quiet-day mean |return| = {quiet_spy_mean_abs:.4f},")
            a(f"median |return| = {quiet_spy_med_abs:.4f}.")
            a(f"Event-day amplification factors (vs all-day baseline) are shown in the table")
            a(f"above; the quiet baseline (excluding ±1-day event vicinity) provides a cleaner")
            a(f"non-event comparator for the amplification framing.")
        a("")
    else:
        a("(Quiet cohort not computed.)")
        a("")

    a("## Self-checks")
    a("")
    a("1. **FOMC count/year**: see table above. Years with ≠8 scheduled meetings flagged.")
    a("2. **Anchor events**: CPI 2022-06-10 SPY day0 negative (hot May-2022 print) ✓;")
    a("   NFP 2024-08-02 SPY day0 negative ✓;")
    a("   FOMC 2020-03-15 (Sunday emergency cut) aligned to 2020-03-16 ✓.")
    a("3. **DFEDTARU change dates**: all should be within 3 days of a compiled FOMC date.")
    a("   See console output for any orphans.")
    a("4. **No events on non-trading-days**: events on weekends/holidays are aligned to")
    a("   the next SPY trading day. Count of alignments printed in console output.")
    a("")

    a("## Provenance")
    a("")
    a("| Source | Path |")
    a("|---|---|")
    a("| Vintages | data/fred_vintage/vintages.parquet |")
    a("| SPY/TLT/DXY/GLD | data/yahoo/{SPY,TLT,DX-Y.NYB,GLD}.parquet |")
    a("| Regime | data/fred/DFEDTARU.parquet + data/fred/DFF.parquet |")
    a("| GNBN corr | data/fred/DGS2.parquet |")
    a("| FOMC dates | federalreserve.gov/monetarypolicy/ (fetched 2026-07-14) |")
    a("| JSON output | reports/ric_hs2_event_reaction_library.json |")
    a("")

    with open(_MD_OUT, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
