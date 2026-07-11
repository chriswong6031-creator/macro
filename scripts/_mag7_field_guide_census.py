"""
Mag-7 Field Guide Census

Produces episode tables, per-name behavior stats, and concurrent-market
summaries for research/MAG7_FIELD_GUIDE.md.

DATA SOURCES
  - Member closes:  data/baskets/ohlcv/{AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA}.parquet
                    (2014-01-02 → 2026-07-08)
  - SPY/SMH/QQQ:   data/yahoo/{SPY,SMH,QQQ}.parquet      (long history)
  - IGV:            data/yahoo/IGV.parquet                 (software proxy)
  - Memory basket:  data/baskets/ohlcv/{MU,WDC,STX}.parquet (SNDK 2025-only, excluded)
  - AI-sw proxy:    data/massive_stock_day/IGV.parquet fallback

CAP-WEIGHT BASIS (fixed representative weights, honest disclosure)
  Uses a fixed representative weights table derived from approximate
  market-cap proportions as of 2024-Q4 (per public reference data).
  This is a convenience approximation — the engine's live CW composite
  uses daily Polygon mktcap references (M7C-R2).  Episodes labeled
  pre-2023 are "retrospective composite" (the Mag-7 as a named cohort
  emerged in 2023; the seven names existed earlier and are back-calculated
  for pattern study only).

EPISODE EXTRACTION
  - CW composite built on inner-join of all 7 members (first common date
    is 2014-01-02 since all 7 have data from that date).
  - Local low: rolling 30-session minimum close (trough).
  - Episode starts at a trough; episode ends at the earliest of:
      (a) a new trough (>30 sessions later) that is lower, OR
      (b) when the CW composite drops >4% from any peak reached, OR
      (c) 30 sessions after the trough if no +8% gain achieved.
  - Qualifying episodes: peak/trough gain ≥ +8% within ≤ 30 sessions.
  - Peak/trough logic:
      * Trough = local min over a 20-session lookback (with ≥5 sessions
        since last trough).
      * Episode peak = max close within 30 sessions from trough.

CONCURRENT MARKET
  For each episode: SPY / SMH / memory-EW(MU,WDC,STX) / IGV returns over
  the same window + 20 and 60 sessions after the episode peak.

BREADTH SHAPE
  Number of 7 members above their 50-day moving average at:
    start of episode, mid-episode (15 sessions), and at peak.

OUTPUTS (printed to stdout, pipe to file or embed in the field guide)
"""

from __future__ import annotations
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
OHLCV = REPO / "data" / "baskets" / "ohlcv"
YAHOO = REPO / "data" / "yahoo"
MSD   = REPO / "data" / "massive_stock_day"

# ---------------------------------------------------------------------------
# Fixed representative cap-weights (2024-Q4 approximation; documented)
# ---------------------------------------------------------------------------
# Source: approximate public-domain market-cap proportions (end-2024).
# NVDA weight reflects its 2024 ascension; TSLA lowest among the seven.
# Change these only with a documented reference and a PR that updates the
# field guide's "Weights basis" section.
FIXED_WEIGHTS: dict[str, float] = {
    "AAPL":  0.240,  # largest by mktcap end-2024
    "NVDA":  0.215,  # #2 after NVDA surge
    "MSFT":  0.195,
    "AMZN":  0.120,
    "GOOGL": 0.105,
    "META":  0.085,
    "TSLA":  0.040,
}
assert abs(sum(FIXED_WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1"

MAG7 = list(FIXED_WEIGHTS.keys())

# Memory basket: SNDK only from 2025-02, excluded here to preserve history
MEMORY_TICKERS = ["MU", "WDC", "STX"]

# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def load_ohlcv(ticker: str, store: Path = OHLCV) -> pd.Series:
    """Return daily close indexed by date (tz-naive)."""
    path = store / f"{ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}")
    df = pd.read_parquet(path)
    s = df["close"].copy()
    s.index = pd.to_datetime(s.index).normalize()
    s.name = ticker
    return s


def load_yahoo(ticker: str) -> pd.Series:
    path = YAHOO / f"{ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing yahoo: {path}")
    df = pd.read_parquet(path)
    s = df["close"].copy()
    s.index = pd.to_datetime(s.index).normalize()
    s.name = ticker
    return s


# ---------------------------------------------------------------------------
# Build composites
# ---------------------------------------------------------------------------

def build_cw_composite(member_closes: pd.DataFrame) -> pd.Series:
    """Cap-weighted composite on inner-join.  Pre-2023 labeled retrospective."""
    closes = member_closes.dropna(how="any")
    w = np.array([FIXED_WEIGHTS[t] for t in closes.columns])
    w = w / w.sum()  # re-normalize in case subset
    # Rebased to 100 at first date
    base = closes.iloc[0]
    rebased = closes / base * 100
    cw = (rebased * w).sum(axis=1)
    cw.name = "MAG7_CW"
    return cw


def build_ew_composite(tickers: list[str], store: Path = OHLCV) -> pd.Series:
    closes = pd.concat(
        [load_ohlcv(t, store) for t in tickers if (store / f"{t}.parquet").exists()],
        axis=1,
    ).dropna(how="any")
    if closes.empty:
        return pd.Series(dtype=float)
    base = closes.iloc[0]
    rebased = closes / base * 100
    ew = rebased.mean(axis=1)
    ew.name = "EW_" + "_".join(tickers)
    return ew


# ---------------------------------------------------------------------------
# DMA helper
# ---------------------------------------------------------------------------

def above_50dma(close_series: pd.Series) -> pd.Series:
    """Boolean: close > 50-day SMA."""
    return close_series > close_series.rolling(50, min_periods=30).mean()


# ---------------------------------------------------------------------------
# Episode extraction
# ---------------------------------------------------------------------------

def find_troughs(cw: pd.Series, lookback: int = 20, min_gap: int = 5) -> list[int]:
    """
    Troughs: positions where CW is the minimum of the previous `lookback`
    sessions (inclusive of self), with at least `min_gap` sessions between
    consecutive troughs.
    """
    arr = cw.values
    n = len(arr)
    troughs = []
    last = -min_gap - 1
    for i in range(lookback, n):
        window = arr[i - lookback : i + 1]
        if arr[i] == window.min() and (i - last) >= min_gap:
            troughs.append(i)
            last = i
    return troughs


def extract_episodes(
    cw: pd.Series,
    member_df: pd.DataFrame,
    min_gain: float = 0.08,
    max_sessions: int = 30,
    trough_lookback: int = 20,
) -> list[dict]:
    """
    For each trough, look forward up to max_sessions for a peak.
    Episode qualifies if (peak - trough) / trough >= min_gain.
    """
    troughs_idx = find_troughs(cw, lookback=trough_lookback, min_gap=5)
    episodes = []

    for ti in troughs_idx:
        trough_date = cw.index[ti]
        trough_val  = cw.iloc[ti]
        window_end  = min(ti + max_sessions, len(cw) - 1)
        window      = cw.iloc[ti : window_end + 1]
        peak_offset = window.values.argmax()
        peak_idx    = ti + peak_offset
        peak_date   = cw.index[peak_idx]
        peak_val    = cw.iloc[peak_idx]
        gain        = (peak_val - trough_val) / trough_val

        if gain < min_gain:
            continue
        if peak_offset == 0:
            continue  # peak is at trough — degenerate

        # Breadth: number above 50dma at start, mid, peak
        mid_idx = ti + max(1, peak_offset // 2)
        mid_idx = min(mid_idx, len(cw) - 1)

        def breadth_at(idx: int) -> int:
            date = cw.index[idx]
            if date not in member_df.index:
                return -1
            row = member_df.loc[date]
            # Need 50dma per name up to this date
            count = 0
            for col in member_df.columns:
                sub = member_df[col].loc[:date]
                if len(sub) < 30:
                    continue
                sma50 = sub.rolling(50, min_periods=30).mean().iloc[-1]
                if sub.iloc[-1] > sma50:
                    count += 1
            return count

        breadth_start = breadth_at(ti)
        breadth_mid   = breadth_at(mid_idx)
        breadth_peak  = breadth_at(peak_idx)

        # Per-member returns over episode
        trough_prices = member_df.loc[trough_date] if trough_date in member_df.index else None
        peak_prices   = member_df.loc[peak_date]   if peak_date   in member_df.index else None
        member_rets = {}
        if trough_prices is not None and peak_prices is not None:
            for col in member_df.columns:
                if pd.notna(trough_prices[col]) and pd.notna(peak_prices[col]) and trough_prices[col] > 0:
                    member_rets[col] = (peak_prices[col] - trough_prices[col]) / trough_prices[col]

        # Identify leaders (top-2) and who led
        sorted_members = sorted(member_rets.items(), key=lambda x: -x[1])
        leaders  = [k for k, v in sorted_members[:2]] if len(sorted_members) >= 2 else []
        laggards = [k for k, v in sorted_members[-2:]] if len(sorted_members) >= 2 else []

        episodes.append({
            "ep_id":          len(episodes) + 1,
            "trough_date":    trough_date.strftime("%Y-%m-%d"),
            "peak_date":      peak_date.strftime("%Y-%m-%d"),
            "duration_sess":  peak_offset,
            "gain_pct":       round(gain * 100, 1),
            "breadth_start":  breadth_start,
            "breadth_mid":    breadth_mid,
            "breadth_peak":   breadth_peak,
            "leaders":        leaders,
            "laggards":       laggards,
            "member_rets":    {k: round(v * 100, 1) for k, v in member_rets.items()},
            "trough_idx":     ti,
            "peak_idx":       peak_idx,
        })

    return episodes


# ---------------------------------------------------------------------------
# Concurrent market stats
# ---------------------------------------------------------------------------

def concurrent_stats(
    ep: dict,
    cw: pd.Series,
    spy: pd.Series,
    smh: pd.Series,
    memory_ew: pd.Series,
    igv: pd.Series,
) -> dict:
    """Compute concurrent and post-episode returns for SPY, SMH, MEM, IGV."""

    def safe_ret(series: pd.Series, from_date: str, to_date: str) -> float | None:
        try:
            d0 = pd.Timestamp(from_date)
            d1 = pd.Timestamp(to_date)
            # Find nearest available dates
            valid = series.index[(series.index >= d0) & (series.index <= d1)]
            if len(valid) < 2:
                return None
            p0 = series.loc[valid[0]]
            p1 = series.loc[valid[-1]]
            if p0 <= 0:
                return None
            return round((p1 - p0) / p0 * 100, 1)
        except Exception:
            return None

    def post_ret(series: pd.Series, from_date: str, n_sessions: int) -> float | None:
        try:
            d0 = pd.Timestamp(from_date)
            valid = series.index[series.index >= d0]
            if len(valid) < n_sessions + 1:
                return None
            p0 = series.loc[valid[0]]
            pn = series.loc[valid[n_sessions]]
            if p0 <= 0:
                return None
            return round((pn - p0) / p0 * 100, 1)
        except Exception:
            return None

    t = ep["trough_date"]
    p = ep["peak_date"]

    result = {
        "ep_spy_ep":    safe_ret(spy, t, p),
        "ep_smh_ep":    safe_ret(smh, t, p),
        "ep_mem_ep":    safe_ret(memory_ew, t, p),
        "ep_igv_ep":    safe_ret(igv, t, p),
        "ep_spy_p20":   post_ret(spy,       p, 20),
        "ep_spy_p60":   post_ret(spy,       p, 60),
        "ep_smh_p20":   post_ret(smh,       p, 20),
        "ep_smh_p60":   post_ret(smh,       p, 60),
        "ep_mem_p20":   post_ret(memory_ew, p, 20),
        "ep_mem_p60":   post_ret(memory_ew, p, 60),
        "ep_igv_p20":   post_ret(igv,       p, 20),
        "ep_igv_p60":   post_ret(igv,       p, 60),
        "ep_cw_p20":    post_ret(cw,        p, 20),
        "ep_cw_p60":    post_ret(cw,        p, 60),
    }
    return result


# ---------------------------------------------------------------------------
# Per-name behavior: rolling drawdown, 50/200dma crossings, big-move events
# ---------------------------------------------------------------------------

def per_name_stats(ticker: str, close: pd.Series) -> dict:
    sma50  = close.rolling(50,  min_periods=30).mean()
    sma200 = close.rolling(200, min_periods=120).mean()
    roll_max = close.cummax()
    dd = (close - roll_max) / roll_max

    above50  = close > sma50
    above200 = close > sma200

    # Biggest single-session drops
    daily_ret = close.pct_change()
    worst5 = daily_ret.nsmallest(5)
    best5  = daily_ret.nlargest(5)

    # Months of ≥+30% vs ≥-30% drawdown from 52-week high
    wk52_high = close.rolling(252, min_periods=120).max()
    dd_52wk = (close - wk52_high) / wk52_high
    deep_dd = (dd_52wk <= -0.30).sum()

    return {
        "ticker":       ticker,
        "max_dd":       round(dd.min() * 100, 1),
        "days_above_50dma":  int(above50.sum()),
        "days_above_200dma": int(above200.sum()),
        "pct_above_50dma":   round(above50.mean() * 100, 1),
        "pct_above_200dma":  round(above200.mean() * 100, 1),
        "worst_day":    round(worst5.iloc[0] * 100, 2),
        "worst_day_date": worst5.index[0].strftime("%Y-%m-%d"),
        "best_day":     round(best5.iloc[0] * 100, 2),
        "best_day_date": best5.index[0].strftime("%Y-%m-%d"),
        "days_deep_dd": int(deep_dd),
    }


# ---------------------------------------------------------------------------
# Resolution pattern: what happened after each episode peak?
# ---------------------------------------------------------------------------

def resolution_pattern(ep: dict, cw: pd.Series) -> str:
    """
    Classify the 20-session post-peak behavior of the CW composite.
    broadened  : CW continued higher ≥ +3%
    chopped    : CW ±3% range
    rolled_over: CW fell ≥ -4%
    """
    peak_idx = ep["peak_idx"]
    look_end = min(peak_idx + 20, len(cw) - 1)
    if look_end <= peak_idx:
        return "data_end"
    peak_val  = cw.iloc[peak_idx]
    next20_max = cw.iloc[peak_idx : look_end + 1].max()
    next20_min = cw.iloc[peak_idx : look_end + 1].min()
    fwd20      = (cw.iloc[look_end] - peak_val) / peak_val * 100
    if next20_min / peak_val - 1 <= -0.04:
        return "rolled_over"
    elif fwd20 >= 3.0:
        return "broadened"
    elif abs(fwd20) < 3.0 and (next20_max / peak_val - 1) < 3.0:
        return "chopped"
    else:
        return "mixed"


# ---------------------------------------------------------------------------
# Printing helpers
# ---------------------------------------------------------------------------

SEP = "-" * 100


def pct(v: float | None) -> str:
    if v is None:
        return "  n/a"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def print_episode_table(
    episodes: list[dict],
    concurrent: list[dict],
    resolutions: list[str],
) -> None:
    print()
    print("=" * 100)
    print("EPISODE TABLE — Mag-7 CW Composite runs ≥ +8% within ≤ 30 sessions (2015→2026-07-08)")
    print(f"{'#':>2} {'Trough':>12} {'Peak':>12} {'Dur':>4} {'Gain':>6}  "
          f"{'BrdSt':>5} {'BrdMd':>5} {'BrdPk':>5}  "
          f"{'Leaders (top-2)':>20}  {'Laggards (bot-2)':>20}  "
          f"{'SPY_ep':>7} {'SMH_ep':>7} {'MEM_ep':>7} {'IGV_ep':>7}  "
          f"{'Res-20':>11}")
    print(SEP)

    for ep, conc, res in zip(episodes, concurrent, resolutions):
        is_retro = ep["trough_date"] < "2023-01-01"
        retro_mark = "*" if is_retro else " "
        leaders_str  = "+".join(ep["leaders"])  if ep["leaders"]  else "n/a"
        laggards_str = "+".join(ep["laggards"]) if ep["laggards"] else "n/a"
        print(
            f"{ep['ep_id']:>2}{retro_mark} {ep['trough_date']:>12} {ep['peak_date']:>12} "
            f"{ep['duration_sess']:>4} {pct(ep['gain_pct']):>6}  "
            f"{ep['breadth_start']:>5} {ep['breadth_mid']:>5} {ep['breadth_peak']:>5}  "
            f"{leaders_str:>20}  {laggards_str:>20}  "
            f"{pct(conc['ep_spy_ep']):>7} {pct(conc['ep_smh_ep']):>7} "
            f"{pct(conc['ep_mem_ep']):>7} {pct(conc['ep_igv_ep']):>7}  "
            f"{res:>11}"
        )

    print()
    print("* = pre-2023 RETROSPECTIVE COMPOSITE (composition-honesty label; Mag-7 as a")
    print("    named cohort emerged in 2023; seven names existed earlier as individual stocks).")
    print("  BrdSt/BrdMd/BrdPk = # of 7 members above their 50dma at episode start/mid/peak.")
    print("  Res-20 = 20-session post-peak resolution of the CW composite.")
    print("  SPY/SMH/MEM/IGV = return over the SAME episode window (trough→peak).")
    print()


def print_member_return_detail(episodes: list[dict]) -> None:
    print()
    print("=" * 100)
    print("PER-MEMBER RETURN DETAIL by episode")
    header = f"{'#':>2} {'Trough':>12} {'AAPL':>7} {'MSFT':>7} {'NVDA':>7} {'AMZN':>7} {'GOOGL':>7} {'META':>7} {'TSLA':>7}"
    print(header)
    print("-" * len(header))
    for ep in episodes:
        mr = ep["member_rets"]
        is_retro = ep["trough_date"] < "2023-01-01"
        retro_mark = "*" if is_retro else " "
        row = (
            f"{ep['ep_id']:>2}{retro_mark} {ep['trough_date']:>12}  "
            f"{pct(mr.get('AAPL')):>7} {pct(mr.get('MSFT')):>7} {pct(mr.get('NVDA')):>7} "
            f"{pct(mr.get('AMZN')):>7} {pct(mr.get('GOOGL')):>7} {pct(mr.get('META')):>7} "
            f"{pct(mr.get('TSLA')):>7}"
        )
        print(row)


def print_post_episode_concurrent(episodes: list[dict], concurrent: list[dict]) -> None:
    print()
    print("=" * 100)
    print("POST-EPISODE (20s / 60s after peak): CW, SPY, SMH, MEMORY, IGV")
    print(f"{'#':>2} {'Peak':>12}  {'CW_p20':>7} {'CW_p60':>7}  {'SPY_p20':>8} {'SPY_p60':>8}  "
          f"{'SMH_p20':>8} {'SMH_p60':>8}  {'MEM_p20':>8} {'MEM_p60':>8}  {'IGV_p20':>8} {'IGV_p60':>8}")
    print(SEP)
    for ep, conc in zip(episodes, concurrent):
        is_retro = ep["trough_date"] < "2023-01-01"
        retro_mark = "*" if is_retro else " "
        print(
            f"{ep['ep_id']:>2}{retro_mark} {ep['peak_date']:>12}  "
            f"{pct(conc['ep_cw_p20']):>7} {pct(conc['ep_cw_p60']):>7}  "
            f"{pct(conc['ep_spy_p20']):>8} {pct(conc['ep_spy_p60']):>8}  "
            f"{pct(conc['ep_smh_p20']):>8} {pct(conc['ep_smh_p60']):>8}  "
            f"{pct(conc['ep_mem_p20']):>8} {pct(conc['ep_mem_p60']):>8}  "
            f"{pct(conc['ep_igv_p20']):>8} {pct(conc['ep_igv_p60']):>8}"
        )
    print()
    print("n/a = insufficient post-peak data in the store (close to store end-date).")


def print_per_name_stats(stats_list: list[dict], store_end: str) -> None:
    print()
    print("=" * 100)
    print(f"PER-NAME BEHAVIOR STATS (2015-01-01 → {store_end}, baskets/ohlcv)")
    print(f"{'Name':>5} {'MaxDD':>7} {'%>50d':>7} {'%>200d':>8} {'WorstDay':>9} {'WrstDate':>12} {'BestDay':>8} {'BestDate':>12} {'DaysDD>30':>10}")
    print("-" * 90)
    for s in stats_list:
        print(
            f"{s['ticker']:>5} {pct(s['max_dd']):>7} {s['pct_above_50dma']:>6.1f}% {s['pct_above_200dma']:>7.1f}%  "
            f"{s['worst_day']:>8.2f}% {s['worst_day_date']:>12}  "
            f"{s['best_day']:>7.2f}% {s['best_day_date']:>12}  "
            f"{s['days_deep_dd']:>9}"
        )


def print_decoupling_episodes(
    member_df: pd.DataFrame,
    smh: pd.Series,
    memory_ew: pd.Series,
    cw: pd.Series,
) -> None:
    """
    Print key identified decoupling episodes: periods where Mag-7 CW diverged
    strongly from SMH or memory, or where NVDA decoupled from peers.
    Focus on 2021→ where all stores overlap.
    """
    print()
    print("=" * 100)
    print("DECOUPLING EPISODES — Notable divergences (SMH vs Mag-7, NVDA vs peers)")
    print()

    # 2022 bear: check all-member drawdowns
    print("--- 2022 BEAR (calendar year 2022) ---")
    for col in member_df.columns:
        sub = member_df[col].loc["2022-01-01":"2022-12-31"]
        if len(sub) < 10:
            continue
        ret = (sub.iloc[-1] - sub.iloc[0]) / sub.iloc[0] * 100
        print(f"  {col}: {pct(ret)}")
    spy_sub = cw.loc["2022-01-01":"2022-12-31"]
    if len(spy_sub) > 0:
        spy_ret = (spy_sub.iloc[-1] - spy_sub.iloc[0]) / spy_sub.iloc[0] * 100
        print(f"  MAG7_CW: {pct(spy_ret)}")

    # 2023 AI bull
    print()
    print("--- 2023 AI BULL (full year 2023) ---")
    for col in member_df.columns:
        sub = member_df[col].loc["2023-01-01":"2023-12-31"]
        if len(sub) < 10:
            continue
        ret = (sub.iloc[-1] - sub.iloc[0]) / sub.iloc[0] * 100
        print(f"  {col}: {pct(ret)}")

    # 2024 broadening
    print()
    print("--- 2024 (full year 2024) ---")
    for col in member_df.columns:
        sub = member_df[col].loc["2024-01-01":"2024-12-31"]
        if len(sub) < 10:
            continue
        ret = (sub.iloc[-1] - sub.iloc[0]) / sub.iloc[0] * 100
        print(f"  {col}: {pct(ret)}")

    # 2026 memory melt-up + reversal
    print()
    print("--- 2026 MEMORY MELT-UP (2026-01-01 → store end) ---")
    print("  Memory basket (MU/WDC/STX) 2026 YTD:")
    if len(memory_ew) > 0:
        sub_m = memory_ew.loc["2026-01-01":]
        if len(sub_m) >= 2:
            ret_m = (sub_m.iloc[-1] - sub_m.iloc[0]) / sub_m.iloc[0] * 100
            print(f"  MEM_EW YTD: {pct(ret_m)}")
    print("  Mag-7 CW 2026 YTD:")
    sub_cw = cw.loc["2026-01-01":]
    if len(sub_cw) >= 2:
        ret_cw = (sub_cw.iloc[-1] - sub_cw.iloc[0]) / sub_cw.iloc[0] * 100
        print(f"  MAG7_CW YTD: {pct(ret_cw)}")
    print()

    # 06-26 → store-end run (the live exhibit from MAG7_COMMAND_MASTERPLAN)
    print("--- LIVE EXHIBIT: 06-26-2026 → 07-02-2026 (store end) ---")
    print("  Per MAG7_COMMAND_MASTERPLAN §0 incident of record:")
    print("  MAGS (Roundhill ETF, traded reference):  $61.60 → ~$67 (+~9% by 07-10)")
    print("  Operator-verified: SMH −3.2% over same window (generals decoupled from semis)")
    for col in member_df.columns:
        sub = member_df[col].loc["2026-06-26":"2026-07-08"]
        if len(sub) < 2:
            print(f"  {col}: insufficient rows in store")
            continue
        ret = (sub.iloc[-1] - sub.iloc[0]) / sub.iloc[0] * 100
        print(f"  {col}: {pct(ret)}")
    sub_cw_live = cw.loc["2026-06-26":"2026-07-08"]
    if len(sub_cw_live) >= 2:
        ret = (sub_cw_live.iloc[-1] - sub_cw_live.iloc[0]) / sub_cw_live.iloc[0] * 100
        print(f"  MAG7_CW: {pct(ret)}")
    if len(memory_ew) > 0:
        sub_m = memory_ew.loc["2026-06-26":"2026-07-02"]
        if len(sub_m) >= 2:
            ret = (sub_m.iloc[-1] - sub_m.iloc[0]) / sub_m.iloc[0] * 100
            print(f"  MEM_EW (MU/WDC/STX): {pct(ret)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== MAG-7 FIELD GUIDE CENSUS ===")
    print(f"Script: scripts/_mag7_field_guide_census.py")
    print(f"As-of: baskets/ohlcv last bar 2026-07-08 (per store inspection)")
    print(f"       massive_stock_day last bar 2026-07-02 (SMH/IGV/SPY via yahoo: 2026-07-08)")
    print()
    print("CAP-WEIGHT BASIS (fixed representative weights — 2024-Q4 approximation):")
    for t, w in FIXED_WEIGHTS.items():
        print(f"  {t}: {w:.3f}")
    print("  (Engine uses live Polygon mktcap; these weights are for field-guide description only)")
    print()

    # --- Load member closes ---
    member_closes = pd.concat([load_ohlcv(t) for t in MAG7], axis=1)
    # Restrict to 2015+ (pre-2015 META had gaps; 2015 start gives a full decade)
    member_closes = member_closes.loc["2015-01-01":]
    member_closes = member_closes.dropna(how="any")
    print(f"Member close panel: {member_closes.index[0].date()} → {member_closes.index[-1].date()}"
          f" ({len(member_closes)} trading sessions)")

    # --- CW composite ---
    cw = build_cw_composite(member_closes)
    print(f"CW composite: range {cw.min():.1f} → {cw.max():.1f} (rebased 100 at {cw.index[0].date()})")

    # --- Reference series ---
    spy = load_yahoo("SPY")
    smh = load_yahoo("SMH")
    igv = load_yahoo("IGV")
    memory_ew = build_ew_composite(MEMORY_TICKERS, OHLCV)
    print(f"SPY: {spy.index[0].date()} → {spy.index[-1].date()}")
    print(f"SMH: {smh.index[0].date()} → {smh.index[-1].date()}")
    print(f"IGV: {igv.index[0].date()} → {igv.index[-1].date()}")
    print(f"Memory EW ({'/'.join(MEMORY_TICKERS)}): "
          f"{memory_ew.index[0].date()} → {memory_ew.index[-1].date()} "
          f"(SNDK excluded — live only from 2025-02; NTAP excluded — different category)")

    # --- Episode extraction ---
    print()
    print("Extracting episodes (CW composite ≥ +8% within ≤ 30 sessions from local trough)...")
    episodes = extract_episodes(cw, member_closes, min_gain=0.08, max_sessions=30)
    print(f"Episodes found: {len(episodes)}")
    if not episodes:
        print("WARNING: no episodes found — check data or thresholds")
        return

    # --- Concurrent stats ---
    concurrent = []
    resolutions = []
    for ep in episodes:
        conc = concurrent_stats(ep, cw, spy, smh, memory_ew, igv)
        concurrent.append(conc)
        resolutions.append(resolution_pattern(ep, cw))

    # --- Print tables ---
    print_episode_table(episodes, concurrent, resolutions)
    print_member_return_detail(episodes)
    print_post_episode_concurrent(episodes, concurrent)

    # --- Per-name stats ---
    store_end = member_closes.index[-1].strftime("%Y-%m-%d")
    stats_list = []
    for t in MAG7:
        close = member_closes[t].loc["2015-01-01":]
        stats_list.append(per_name_stats(t, close))
    print_per_name_stats(stats_list, store_end)

    # --- Decoupling episodes ---
    print_decoupling_episodes(member_closes, smh, memory_ew, cw)

    # --- Summary counts ---
    retro = sum(1 for ep in episodes if ep["trough_date"] < "2023-01-01")
    live  = len(episodes) - retro
    broad = sum(1 for ep in episodes if ep.get("breadth_peak", 0) >= 5)
    print()
    print("=" * 100)
    print(f"SUMMARY: {len(episodes)} qualifying episodes total "
          f"({retro} retrospective pre-2023 / {live} post-2023 named-cohort era)")
    print(f"  Broad episodes (≥5/7 members above 50dma at peak): {broad}")
    print(f"  Narrow episodes (<5/7): {len(episodes) - broad}")

    roll_over = resolutions.count("rolled_over")
    broadened  = resolutions.count("broadened")
    chopped    = resolutions.count("chopped")
    mixed      = resolutions.count("mixed")
    data_end   = resolutions.count("data_end")
    print(f"  Post-peak resolution: rolled_over={roll_over}, broadened={broadened}, "
          f"chopped={chopped}, mixed={mixed}, data_end={data_end}")

    # Leader frequency
    from collections import Counter
    leader_count: Counter = Counter()
    for ep in episodes:
        for ldr in ep.get("leaders", []):
            leader_count[ldr] += 1
    print()
    print("  Leader frequency (times in top-2 by episode contribution):")
    for t, cnt in leader_count.most_common():
        print(f"    {t}: {cnt}")

    print()
    print("LIMITS AND HONEST NULLS (see MAG7_FIELD_GUIDE.md §LIMITS)")
    print("  - N = small; patterns described, not claimed as statistically reliable.")
    print("  - Pre-2023 episodes are retrospective composites — composition honesty required.")
    print("  - Cap-weights are fixed representative approximations, not daily mktcap series.")
    print("  - SNDK excluded from memory EW (only live since 2025-02); NTAP excluded (storage, not DRAM).")
    print("  - Store ends 2026-07-08 (baskets/ohlcv); the 06-26→07-08 live run is partially")
    print("    observable in-store; operator-confirmed extension to 07-10 per MAG7_COMMAND §0.")
    print("  - Post-episode data (p20, p60) for episodes near the store end will show n/a.")


if __name__ == "__main__":
    import sys as _sys
    _wd = Path(__file__).resolve().parent.parent
    _sys.path.insert(0, str(_wd))
    try:
        from lib import procutil
        _USE_HARD_EXIT = True
    except ImportError:
        _USE_HARD_EXIT = False

    main()

    if _USE_HARD_EXIT:
        procutil.hard_exit(0)
    else:
        import sys, os
        sys.stdout.flush()
        os._exit(0)
