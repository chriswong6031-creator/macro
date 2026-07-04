"""S7 RS-Repair Phase-0 — feature computation at fire close t.

All features are strictly causal: computed using only data known at the close
of the fire bar t.  Fill at t+1; forward windows start after t+1.

SPEC §4 features:
  rs_spy_slope20      (close/SPY) 20d change > 0
  rs_sect_slope20     (close/sector-ETF) 20d change > 0
  rs_sect_hl          min(RS[t-19..t]) > min(RS[t-39..t-20])
  rs_cohort_rank_slope20  within-sector RS-rank percentile, 20d change > 0
  rs_low              RS-vs-SPY level in bottom tercile of trailing 252d range
  cohort_frac_w       % same-sector liquid peers with weekly StochRSI D < 30
  loc60_12 / loc60_15 close within 12%/15% of trailing 60d low
  above_10w           close > 10-week MA
  monthly_dwell       consecutive completed monthly StochRSI-D<20 bars (P2 only)

cohort_frac_w requires a cross-sectional weekly StochRSI D panel.  Build it
once as a wide matrix (call build_weekly_d_panel()) then pass it to feature
extraction per fire.

SAME-COMPUTABLE-SUBSET BASELINE: every stratum delta is compared to the subset
of fires for which THAT feature was computable (not the full fire set).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# Indicator helpers (same faithful math as fires.py)
# ──────────────────────────────────────────────────────────────────────────

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, min_periods=span, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _stoch_rsi_d(close: pd.Series) -> pd.Series:
    """Return the StochRSI D series (14/3/3) on the given close series."""
    r = _rsi(close, 14)
    lo = r.rolling(14).min()
    hi = r.rolling(14).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(3).mean()
    return k.rolling(3).mean()


# ──────────────────────────────────────────────────────────────────────────
# Weekly StochRSI D panel builder
# ──────────────────────────────────────────────────────────────────────────

def build_weekly_d_panel(ticker_close_map: dict[str, pd.Series],
                         common_dates: pd.DatetimeIndex | None = None
                         ) -> pd.DataFrame:
    """Build a wide matrix of weekly (W-FRI) StochRSI D values.

    ticker_close_map: {ticker: daily_close_series}
    common_dates: if provided, reindex the output to these weekly dates.

    Returns a DataFrame with weekly dates as index, tickers as columns.
    Used for cohort_frac_w computation.

    The weekly D value on date w is computed on closed weekly bars up to
    and including w (leak-free because weekly bars close on Friday).
    """
    panels = {}
    for ticker, daily in ticker_close_map.items():
        if daily is None or len(daily) < 60:
            continue
        try:
            wk = daily.resample("W-FRI").last().dropna()
            if len(wk) < 40:
                continue
            d = _stoch_rsi_d(wk)
            panels[ticker] = d
        except Exception as exc:
            log.debug("build_weekly_d_panel: %s failed: %s", ticker, exc)

    if not panels:
        return pd.DataFrame()

    panel = pd.DataFrame(panels)
    if common_dates is not None:
        panel = panel.reindex(common_dates, method="ffill")
    return panel


def get_weekly_d_on(weekly_d_panel: pd.DataFrame,
                    ticker: str,
                    fire_date: pd.Timestamp) -> float | None:
    """Look up the most-recently completed weekly StochRSI D for a ticker at fire_date.

    The weekly D known at fire_date is the most recent W-FRI close <= fire_date.
    """
    if ticker not in weekly_d_panel.columns:
        return None
    col = weekly_d_panel[ticker].dropna()
    if col.empty:
        return None
    pos = col.index.searchsorted(fire_date, side="right") - 1
    if pos < 0:
        return None
    return float(col.iloc[pos])


def cohort_frac_w_on(weekly_d_panel: pd.DataFrame,
                     ticker: str,
                     fire_date: pd.Timestamp,
                     sector_of: dict[str, str],
                     liquid_tickers: set[str] | None,
                     d_thresh: float = 30.0,
                     min_peers: int = 5) -> float | None:
    """Fraction of same-sector liquid peers with weekly StochRSI D < d_thresh.

    Reuses the engine/coiled.py cohort_fractions logic (self-exclusion,
    min_peers floor, None when coverage < floor).

    ticker: the fire ticker (excluded from its own peer set)
    liquid_tickers: set of tickers that pass the liquidity floor on fire_date;
                    if None, use all tickers in the panel.
    """
    sector = sector_of.get(ticker)
    if sector is None:
        return None

    peers = [
        t for t, s in sector_of.items()
        if s == sector and t != ticker
        and (liquid_tickers is None or t in liquid_tickers)
        and t in weekly_d_panel.columns
    ]
    if len(peers) < min_peers:
        return None

    # Get weekly D values as of fire_date for all peers
    d_vals = []
    for p in peers:
        d = get_weekly_d_on(weekly_d_panel, p, fire_date)
        if d is not None:
            d_vals.append(d)

    if len(d_vals) < min_peers:
        return None
    return float(np.mean([d < d_thresh for d in d_vals]))


# ──────────────────────────────────────────────────────────────────────────
# Per-fire feature extraction
# ──────────────────────────────────────────────────────────────────────────

def compute_features(
    ticker: str,
    fire_date: pd.Timestamp,
    daily_close: pd.Series,
    spy_close: pd.Series,
    sect_etf_close: pd.Series | None,
    weekly_d_panel: pd.DataFrame,
    sector_of: dict[str, str],
    liquid_tickers_on_date: set[str] | None,
    panel: str = "P1",
) -> dict:
    """Compute all SPEC §4 features for one fire event.

    All values are at the close of fire_date t (strictly causal).
    Returns a dict with feature keys; None means not computable.

    panel: 'P1' or 'P2' (monthly_dwell only on P2).
    """
    feats: dict = {
        "ticker": ticker,
        "fire_date": fire_date,
        "rs_spy_slope20": None,
        "rs_sect_slope20": None,
        "rs_sect_hl": None,
        "rs_cohort_rank_slope20": None,
        "rs_low": None,
        "cohort_frac_w": None,
        "loc60_12": None,
        "loc60_15": None,
        "above_10w": None,
        "monthly_dwell": None,
    }

    # Locate fire_date in daily_close (use last row <= fire_date)
    pos = daily_close.index.searchsorted(fire_date, side="right") - 1
    if pos < 0:
        return feats
    t_close = float(daily_close.iloc[pos])
    if t_close <= 0 or np.isnan(t_close):
        return feats

    # --- RS vs SPY ---
    spy_pos = spy_close.index.searchsorted(fire_date, side="right") - 1
    if spy_pos >= 20:
        rs_spy = daily_close.iloc[: pos + 1] / spy_close.reindex(
            daily_close.index[:pos + 1], method="ffill"
        ).values
        if len(rs_spy) >= 20 and not np.isnan(rs_spy.iloc[-20]):
            slope20 = float(rs_spy.iloc[-1]) - float(rs_spy.iloc[-20])
            feats["rs_spy_slope20"] = int(slope20 > 0)
            # rs_low: level in bottom tercile of trailing 252d range
            if len(rs_spy) >= 252:
                window = rs_spy.iloc[max(0, len(rs_spy) - 252):]
                lo252, hi252 = float(window.min()), float(window.max())
                if hi252 > lo252:
                    pct = (float(rs_spy.iloc[-1]) - lo252) / (hi252 - lo252)
                    feats["rs_low"] = int(pct <= 1 / 3)
                else:
                    feats["rs_low"] = 1  # flat range -> treat as low

    # --- RS vs sector ETF ---
    if sect_etf_close is not None and len(sect_etf_close) > 40:
        common_idx = daily_close.index[:pos + 1].intersection(
            sect_etf_close.index
        )
        if len(common_idx) >= 40:
            rs_sect = (
                daily_close.reindex(common_idx)
                / sect_etf_close.reindex(common_idx)
            )
            rs_sect = rs_sect.dropna()
            if len(rs_sect) >= 20:
                slope20 = float(rs_sect.iloc[-1]) - float(rs_sect.iloc[-20])
                feats["rs_sect_slope20"] = int(slope20 > 0)
                if len(rs_sect) >= 40:
                    recent20 = rs_sect.iloc[-20:]
                    prior20  = rs_sect.iloc[-40:-20]
                    feats["rs_sect_hl"] = int(
                        float(recent20.min()) > float(prior20.min())
                    )

    # --- rs_cohort_rank_slope20 ---
    # Within-sector RS-rank percentile (vs liquid peers), 20d change > 0.
    # Requires weekly D panel to know which peers exist; RS is daily.
    sector = sector_of.get(ticker)
    if sector is not None and spy_pos >= 40:
        rs_rank_slope = _compute_cohort_rank_slope(
            ticker=ticker,
            fire_date=fire_date,
            daily_close=daily_close,
            pos=pos,
            spy_close=spy_close,
            sector=sector,
            sector_of=sector_of,
            liquid_tickers=liquid_tickers_on_date,
        )
        feats["rs_cohort_rank_slope20"] = rs_rank_slope

    # --- cohort_frac_w ---
    feats["cohort_frac_w"] = cohort_frac_w_on(
        weekly_d_panel=weekly_d_panel,
        ticker=ticker,
        fire_date=fire_date,
        sector_of=sector_of,
        liquid_tickers=liquid_tickers_on_date,
        d_thresh=30.0,
    )

    # --- loc60_12 / loc60_15 ---
    if pos >= 60:
        lo60 = float(daily_close.iloc[pos - 60: pos + 1].min())
        if lo60 > 0:
            pct_above = (t_close - lo60) / lo60
            feats["loc60_12"] = int(pct_above <= 0.12)
            feats["loc60_15"] = int(pct_above <= 0.15)

    # --- above_10w ---
    # 10-week MA = ~50 trading days; use 50d rolling mean
    if pos >= 50:
        ma50 = float(daily_close.iloc[max(0, pos - 49): pos + 1].mean())
        feats["above_10w"] = int(t_close > ma50)

    # --- monthly_dwell (P2 only) ---
    if panel == "P2":
        feats["monthly_dwell"] = _compute_monthly_dwell(daily_close, pos)

    return feats


def _compute_cohort_rank_slope(
    ticker: str,
    fire_date: pd.Timestamp,
    daily_close: pd.Series,
    pos: int,
    spy_close: pd.Series,
    sector: str,
    sector_of: dict[str, str],
    liquid_tickers: set[str] | None,
) -> int | None:
    """Compute rs_cohort_rank_slope20 for one fire.

    This is computationally expensive at scale because it needs peer RS time
    series.  For the cross-sectional harness, the caller should pre-build a
    wide RS panel and pass it.  Here we return None if the caller has not
    provided enough context.

    In the full harness (harness.py), this feature is computed from a
    pre-built sector RS panel passed in via features_ctx.  This stub allows
    single-ticker calls to return None safely.
    """
    # Cannot compute without peer close data here; harness.py passes it via
    # a pre-built sector_rs_rank_panel instead of calling compute_features directly.
    return None


def _compute_monthly_dwell(daily_close: pd.Series, pos: int) -> int | None:
    """Consecutive completed monthly StochRSI-D < 20 bars ending at pos.
    Returns None if fewer than 24 monthly bars available."""
    if pos < 200:
        return None
    mo = daily_close.iloc[: pos + 1].resample("ME").last().dropna()
    if len(mo) < 24:
        return None
    d_mo = _stoch_rsi_d(mo)
    # Use only fully completed months (exclude the last if it is the current partial month)
    # Since we resample to ME we get complete months by definition
    d_completed = d_mo.shift(1).dropna()  # prior completed month's D
    if d_completed.empty:
        return None
    # Count consecutive bars ending at the most recent completed month where D < 20
    arr = (d_completed < 20).to_numpy()
    count = 0
    for v in reversed(arr):
        if v:
            count += 1
        else:
            break
    return count


def batch_compute_features(
    fires_df: pd.DataFrame,
    ticker_close_map: dict[str, pd.Series],
    spy_close: pd.Series,
    sect_etf_map: dict[str, pd.Series],
    weekly_d_panel: pd.DataFrame,
    sector_of: dict[str, str],
    liquid_set_by_date: dict[pd.Timestamp, set[str]] | None,
    panel: str = "P1",
    sector_rs_rank_panel: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Compute features for all fires in fires_df.

    fires_df: DataFrame with columns ['ticker', 'fire_date'].
    sector_rs_rank_panel: optional dict[sector -> wide DataFrame of daily RS-rank
        percentiles per ticker].  If provided, rs_cohort_rank_slope20 is computed.

    Returns fires_df with all feature columns appended.
    """
    rows = []
    for _, row in fires_df.iterrows():
        ticker = row["ticker"]
        fire_date = pd.Timestamp(row["fire_date"])
        daily = ticker_close_map.get(ticker)
        if daily is None or daily.empty:
            continue

        # Resolve sector ETF close
        sect = sector_of.get(ticker)
        sect_close = sect_etf_map.get(sect) if sect else None

        # Liquid peers on this date
        if liquid_set_by_date is not None:
            # Use the closest date on or before fire_date
            available = [d for d in liquid_set_by_date if d <= fire_date]
            if available:
                liq = liquid_set_by_date[max(available)]
            else:
                liq = None
        else:
            liq = None

        feats = compute_features(
            ticker=ticker,
            fire_date=fire_date,
            daily_close=daily,
            spy_close=spy_close,
            sect_etf_close=sect_close,
            weekly_d_panel=weekly_d_panel,
            sector_of=sector_of,
            liquid_tickers_on_date=liq,
            panel=panel,
        )

        # Compute rs_cohort_rank_slope20 from pre-built panel if available
        if sector_rs_rank_panel is not None and sect is not None:
            rank_df = sector_rs_rank_panel.get(sect)
            feats["rs_cohort_rank_slope20"] = _rs_rank_slope_from_panel(
                rank_df, ticker, fire_date
            )

        rows.append(feats)

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    # Merge back with original fires_df to preserve all columns
    keys = ["ticker", "fire_date"]
    out = fires_df.copy().reset_index(drop=True)
    feat_cols = [c for c in result.columns if c not in keys]
    result_indexed = result.set_index(keys)
    for col in feat_cols:
        idx = list(zip(out["ticker"], pd.to_datetime(out["fire_date"])))
        out[col] = [
            result_indexed.loc[(t, d), col]
            if (t, d) in result_indexed.index else None
            for t, d in idx
        ]
    return out


def _rs_rank_slope_from_panel(
    rank_panel: pd.DataFrame | None,
    ticker: str,
    fire_date: pd.Timestamp,
) -> int | None:
    """Compute rs_cohort_rank_slope20 from a pre-built rank panel.

    rank_panel: wide DataFrame, index=trading dates, columns=tickers.
    Values = within-sector RS-rank percentile (0..1) at that date.
    """
    if rank_panel is None or ticker not in rank_panel.columns:
        return None
    col = rank_panel[ticker].dropna()
    if col.empty:
        return None
    pos = col.index.searchsorted(fire_date, side="right") - 1
    if pos < 20:
        return None
    slope20 = float(col.iloc[pos]) - float(col.iloc[pos - 20])
    return int(slope20 > 0)


def build_sector_rs_rank_panel(
    ticker_close_map: dict[str, pd.Series],
    spy_close: pd.Series,
    sector_of: dict[str, str],
    liquid_tickers: set[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Build within-sector RS-rank percentile panels for all sectors.

    For each trading date, the RS-rank percentile of each ticker is its
    rank among liquid peers in the same sector (RS = close/SPY level).

    Returns dict[sector -> wide DataFrame (dates × tickers)].
    """
    # Build daily RS (close / SPY) for all tickers
    # Align to a common trading date calendar
    if spy_close is None or spy_close.empty:
        return {}

    # Gather sectors
    sectors: dict[str, list[str]] = {}
    for ticker, sect in sector_of.items():
        if sect and (liquid_tickers is None or ticker in liquid_tickers):
            if ticker in ticker_close_map:
                sectors.setdefault(sect, []).append(ticker)

    result: dict[str, pd.DataFrame] = {}
    for sect, tickers in sectors.items():
        if len(tickers) < 5:
            continue
        # Build RS series for each ticker
        rs_cols = {}
        for t in tickers:
            daily = ticker_close_map.get(t)
            if daily is None or daily.empty:
                continue
            # Align to spy index
            rs = (daily / spy_close.reindex(daily.index, method="ffill")).dropna()
            if len(rs) >= 20:
                rs_cols[t] = rs

        if len(rs_cols) < 5:
            continue

        rs_panel = pd.DataFrame(rs_cols)

        # Compute rolling rank percentile: at each date, rank each ticker
        # among those with non-NaN RS, using a rolling 252d window is too
        # expensive; use the current cross-section rank instead
        def _rank_row(row: pd.Series) -> pd.Series:
            valid = row.dropna()
            if len(valid) < 3:
                return pd.Series(np.nan, index=row.index)
            ranks = valid.rank(pct=True)
            return ranks.reindex(row.index)

        rank_panel = rs_panel.apply(_rank_row, axis=1)
        result[sect] = rank_panel

    return result
