#!/usr/bin/env python3
"""Reproduce the 2013-2026 S&P 500 / Nasdaq regime-rotation study.

The study uses the repo's Yahoo store and its ``close`` column, which is the
split- and dividend-adjusted total-return series.  SPY and QQQ are investable
proxies for the S&P 500 and Nasdaq-100; they are not the cash indexes.

Outputs are descriptive research artifacts, not promoted trading signals:

* annual index and sector scoreboards;
* ex-post regime-span return/leadership cards;
* sector month-of-year and election-cycle diagnostics;
* a causal weekly 12/26/9 MACD event study and timing strategy;
* an as-of snapshot for the latest available market and macro data.

Run from the repository root with the repo virtual environment, for example:

    .venv/bin/python scripts/research/sp500_nasdaq_regime_rotation_study.py

The regime boundaries were selected ex post to describe economically coherent
legs.  They must not be read as dates that were knowable in advance.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from pandas.tseries.holiday import GoodFriday, Holiday, nearest_workday
from scipy import stats


INDEX_TICKERS = ["SPY", "QQQ", "RSP", "IWM", "SMH", "HYG", "TLT", "_VIX"]
SECTOR_TICKERS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"]
CORE_DEFENSIVES = ["XLV", "XLP", "XLU"]
ALL_TICKERS = INDEX_TICKERS + SECTOR_TICKERS

SECTOR_NAMES = {
    "XLB": "Materials",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLK": "Technology",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLV": "Health Care",
    "XLY": "Consumer Discretionary",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

FRED_SERIES = {
    "DGS10": "us10y",
    "DGS2": "us2y",
    "DFF": "fed_funds",
    "CPIAUCSL": "headline_cpi",
    "PCEPILFE": "core_pce",
    "UNRATE": "unemployment_rate",
    "PAYEMS": "payrolls",
    "BAMLH0A0HYM2": "hy_oas",
    "BAMLC0A0CM": "ig_oas",
    "DCOILWTICO": "wti_crude",
    "T10Y2Y": "spread_2s10s",
    "NFCI": "nfci",
    "VIXCLS": "vix_close",
}


@dataclass(frozen=True)
class RegimeSpan:
    start: str
    end: str
    regime: str
    rotation: str


# Boundaries are descriptive/ex-post.  Adjoining spans intentionally share the
# observed turning-point close so each card measures that complete market leg.
REGIME_SPANS = [
    RegimeSpan("2013-01-02", "2013-05-21", "QE-supported recovery", "health + domestic cyclicals"),
    RegimeSpan("2013-05-21", "2013-06-24", "taper tantrum", "rate-sensitive defensives sold"),
    RegimeSpan("2013-06-24", "2013-12-31", "growth confidence / risk-on normalization", "industrials + discretionary + Nasdaq"),
    RegimeSpan("2014-01-02", "2014-02-03", "global and EM growth scare", "utilities + health preservation"),
    RegimeSpan("2014-02-03", "2014-06-30", "falling yields plus oil's last advance", "energy/materials + utilities barbell"),
    RegimeSpan("2014-06-30", "2014-10-15", "global-growth concern and oil collapse", "staples/health over commodities"),
    RegimeSpan("2014-10-15", "2014-12-31", "policy reassurance and cheaper-energy tailwind", "consumer/industrial rebound; energy lags"),
    RegimeSpan("2015-01-02", "2015-05-21", "slow-growth quality rally", "health + discretionary + technology"),
    RegimeSpan("2015-05-21", "2015-08-17", "sideways index / commodity deterioration", "utilities and consumers over energy/materials"),
    RegimeSpan("2015-08-17", "2015-09-29", "China devaluation / global-volatility shock", "utilities/staples preserve"),
    RegimeSpan("2015-09-29", "2015-12-31", "relief rebound into first Fed hike", "growth/quality rebound"),
    RegimeSpan("2016-01-04", "2016-02-11", "China/oil panic and credit fear", "utilities/staples over banks and beta"),
    RegimeSpan("2016-02-11", "2016-06-23", "commodity bottom and global reflation", "energy/materials/real estate"),
    RegimeSpan("2016-06-23", "2016-07-08", "Brexit shock and rapid recovery", "utilities/real estate/health"),
    RegimeSpan("2016-07-08", "2016-11-07", "yields bottom / reflation rebuild", "financials + technology over bond proxies"),
    RegimeSpan("2016-11-07", "2016-12-30", "post-election reflation / deregulation", "financials/energy/industrials"),
    RegimeSpan("2017-01-03", "2017-09-08", "Goldilocks synchronized growth", "technology + health; energy lags"),
    RegimeSpan("2017-09-08", "2017-12-29", "tax reform and late-year reflation", "financials/energy/industrials"),
    RegimeSpan("2018-01-02", "2018-01-26", "tax-cut growth melt-up", "growth and financial beta"),
    RegimeSpan("2018-01-26", "2018-04-02", "volatility shock / rate fear / trade escalation", "utilities/real estate preserve"),
    RegimeSpan("2018-04-02", "2018-09-20", "strong U.S. earnings and growth", "discretionary/health/technology"),
    RegimeSpan("2018-09-20", "2018-12-24", "Fed/trade tightening and growth scare", "classic defensive preservation"),
    RegimeSpan("2018-12-24", "2018-12-31", "oversold policy-reassessment bounce", "beta/growth rebound"),
    RegimeSpan("2019-01-02", "2019-04-30", "Fed pivot and broad rebound", "technology/industrials/discretionary"),
    RegimeSpan("2019-04-30", "2019-08-30", "trade escalation / yield-curve scare", "real estate/utilities/staples"),
    RegimeSpan("2019-08-30", "2019-12-31", "Fed cuts and trade stabilization", "technology/financials/health"),
    RegimeSpan("2020-01-02", "2020-02-19", "late-cycle secular growth / falling-yield barbell", "technology + utilities/real estate"),
    RegimeSpan("2020-02-19", "2020-03-23", "COVID liquidity and recession crash", "staples/health relative preservation"),
    RegimeSpan("2020-03-23", "2020-08-31", "policy support / reopening / work-from-home boom", "technology/discretionary/communications"),
    RegimeSpan("2020-08-31", "2020-10-30", "growth consolidation / election uncertainty", "temporary utilities rotation"),
    RegimeSpan("2020-10-30", "2020-12-31", "vaccine and reopening trade", "energy/financials"),
    RegimeSpan("2021-01-04", "2021-05-07", "reopening / fiscal impulse / rising inflation", "energy/financials/materials"),
    RegimeSpan("2021-05-07", "2021-09-02", "Delta concern and falling yields", "real estate/technology/health"),
    RegimeSpan("2021-09-02", "2021-10-04", "inflation and yield shock", "energy; rate-sensitive defensives fail"),
    RegimeSpan("2021-10-04", "2021-12-31", "earnings-led year-end rally / taper", "technology/real estate/discretionary"),
    RegimeSpan("2022-01-03", "2022-03-08", "inflation / invasion / first-hike pricing", "energy and low-duration defensives"),
    RegimeSpan("2022-03-08", "2022-06-16", "accelerated tightening / earnings compression", "energy; staples preserve"),
    RegimeSpan("2022-06-16", "2022-08-16", "peak-inflation hope / bear-market rally", "discretionary/technology"),
    RegimeSpan("2022-08-16", "2022-10-12", "Jackson Hole / higher-real-yield reset", "energy; health/staples preserve"),
    RegimeSpan("2022-10-12", "2022-12-30", "inflation-peak / soft-landing hopes", "industrials/utilities/materials"),
    RegimeSpan("2023-01-03", "2023-02-02", "disinflation risk-on", "communications/discretionary/technology"),
    RegimeSpan("2023-02-02", "2023-05-31", "regional-bank stress plus AI breakout", "technology/communications; financials lag"),
    RegimeSpan("2023-05-31", "2023-07-31", "breadth broadening / soft landing", "energy/discretionary/materials"),
    RegimeSpan("2023-07-31", "2023-10-27", "higher-for-longer yield shock", "energy preserves; real estate/consumer lag"),
    RegimeSpan("2023-10-27", "2023-12-29", "Fed-pivot / rate-relief rally", "real estate/financials/discretionary"),
    RegimeSpan("2024-01-02", "2024-03-28", "AI earnings plus reflation broadening", "communications/energy/industrials"),
    RegimeSpan("2024-03-28", "2024-07-10", "AI concentration and power-demand theme", "technology/communications/utilities"),
    RegimeSpan("2024-07-10", "2024-09-17", "mega-cap unwind / rate-cut rotation", "real estate/utilities/industrials"),
    RegimeSpan("2024-09-17", "2024-11-05", "post-cut risk-on", "communications/discretionary/technology"),
    RegimeSpan("2024-11-05", "2024-12-31", "post-election growth / deregulation", "discretionary/communications/financials"),
    RegimeSpan("2025-01-02", "2025-02-19", "soft-landing broadening", "financials/materials/communications"),
    RegimeSpan("2025-02-19", "2025-04-08", "tariff shock and growth downgrade", "defensive preservation"),
    RegimeSpan("2025-04-08", "2025-06-30", "tariff pause / de-escalation and AI rebound", "technology/industrials/communications"),
    RegimeSpan("2025-06-30", "2025-10-29", "AI and power-capex rally", "technology plus power infrastructure"),
    RegimeSpan("2025-10-29", "2025-12-31", "mega-cap pause / health and breadth rebound", "health/financials/materials"),
    RegimeSpan("2026-01-02", "2026-03-30", "energy/inflation/geopolitical risk", "energy/materials/utilities over technology"),
    RegimeSpan("2026-03-30", "2026-06-02", "AI reacceleration / risk-on melt-up", "technology/semiconductors"),
    RegimeSpan("2026-06-02", "2026-07-10", "technology consolidation / broadening pulse", "health/financials/industrials; incomplete handoff"),
]

CROSS_YEAR_BRIDGES = [
    RegimeSpan("2018-12-24", "2019-04-30", "Fed-pivot recovery from the Q4 2018 low", "technology/industrials/discretionary"),
    RegimeSpan("2020-10-30", "2021-05-07", "vaccine-to-reopening reflation", "energy/financials/materials over duration"),
    RegimeSpan("2023-10-27", "2024-03-28", "rate-relief rally into AI/reflation broadening", "real estate/financials/growth, then energy/industrials"),
    RegimeSpan("2024-11-05", "2025-02-19", "post-election growth into soft-landing broadening", "financials/communications/materials"),
]


def _naive_index(index: Iterable) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(index))
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    return idx


def load_yahoo_panel(
    data_root: Path,
    value_col: str = "close",
    tickers: Iterable[str] = ALL_TICKERS,
) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for ticker in tickers:
        path = data_root / "yahoo" / f"{ticker}.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        frame = pd.read_parquet(path)
        if value_col not in frame:
            raise KeyError(f"{path}: column {value_col!r} missing")
        s = pd.to_numeric(frame[value_col], errors="coerce")
        s.index = _naive_index(s.index)
        series[ticker] = s[~s.index.duplicated(keep="last")].sort_index()
    return pd.concat(series, axis=1, sort=True).sort_index()


def load_fred_series(data_root: Path, code: str, value_col: str) -> pd.Series:
    path = data_root / "fred" / f"{code}.parquet"
    if not path.exists():
        return pd.Series(dtype=float, name=value_col)
    frame = pd.read_parquet(path)
    col = value_col if value_col in frame.columns else frame.columns[0]
    s = pd.to_numeric(frame[col], errors="coerce")
    s.index = _naive_index(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna().rename(value_col)


def endpoint_return(series: pd.Series, start: str | pd.Timestamp, end: str | pd.Timestamp) -> float:
    window = series.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()
    if len(window) < 2:
        return math.nan
    return float(window.iloc[-1] / window.iloc[0] - 1.0)


def period_return_with_prior_close(series: pd.Series, start: str | pd.Timestamp, end: str | pd.Timestamp) -> float:
    s = series.dropna().sort_index()
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    prior = s.loc[s.index < start_ts]
    inside = s.loc[start_ts:end_ts]
    if prior.empty or inside.empty:
        return math.nan
    return float(inside.iloc[-1] / prior.iloc[-1] - 1.0)


def max_drawdown(series: pd.Series, start: str | pd.Timestamp, end: str | pd.Timestamp, include_prior: bool = False) -> float:
    s = series.dropna().sort_index()
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    inside = s.loc[start_ts:end_ts]
    if inside.empty:
        return math.nan
    if include_prior:
        prior = s.loc[s.index < start_ts]
        if not prior.empty:
            inside = pd.concat([prior.tail(1), inside])
    return float((inside / inside.cummax() - 1.0).min())


def first_valid_date(series: pd.Series) -> pd.Timestamp | None:
    s = series.dropna()
    return None if s.empty else pd.Timestamp(s.index[0])


def equal_weight_daily_index(panel: pd.DataFrame, tickers: list[str], name: str) -> pd.Series:
    """Daily-rebalanced equal-weight total-return index with complete inputs."""
    returns = panel[tickers].pct_change(fill_method=None).mean(axis=1, skipna=False)
    index = (1.0 + returns).cumprod()
    return index.rename(name)


def annual_scoreboard(panel: pd.DataFrame, end_year: int) -> pd.DataFrame:
    rows: list[dict] = []
    for year in range(2013, end_year + 1):
        start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31")
        row: dict[str, object] = {"year": year, "complete_year": bool(end <= panel.index.max())}
        for ticker in ["SPY", "QQQ"]:
            row[f"{ticker.lower()}_return"] = period_return_with_prior_close(panel[ticker], start, end)
            row[f"{ticker.lower()}_max_drawdown"] = max_drawdown(panel[ticker], start, end, include_prior=True)
        sector_returns: dict[str, float] = {}
        for ticker in SECTOR_TICKERS:
            inception = first_valid_date(panel[ticker])
            # Do not rank an ETF in its partial launch year.
            if inception is None or inception > start + pd.Timedelta(days=10):
                continue
            value = period_return_with_prior_close(panel[ticker], start, end)
            if np.isfinite(value):
                sector_returns[ticker] = value
        ranked = sorted(sector_returns.items(), key=lambda kv: kv[1], reverse=True)
        row["rank_universe_n"] = len(ranked)
        row["rank_universe"] = ";".join(t for t, _ in ranked)
        row["leaders"] = "; ".join(f"{t} {v:.4f}" for t, v in ranked[:3])
        row["laggards"] = "; ".join(f"{t} {v:.4f}" for t, v in ranked[-3:])
        for ticker, value in sector_returns.items():
            row[f"{ticker.lower()}_return"] = value
        rows.append(row)
    return pd.DataFrame(rows)


def regime_span_cards(panel: pd.DataFrame, spans: list[RegimeSpan] | None = None) -> pd.DataFrame:
    spans = REGIME_SPANS if spans is None else spans
    rows: list[dict] = []
    for i, span in enumerate(spans, 1):
        row: dict[str, object] = {
            "span_id": i,
            "start": span.start,
            "end": span.end,
            "regime": span.regime,
            "rotation_interpretation": span.rotation,
            "boundary_type": "ex_post_descriptive",
            "spy_return": endpoint_return(panel["SPY"], span.start, span.end),
            "qqq_return": endpoint_return(panel["QQQ"], span.start, span.end),
            "spy_max_drawdown": max_drawdown(panel["SPY"], span.start, span.end),
            "qqq_max_drawdown": max_drawdown(panel["QQQ"], span.start, span.end),
        }
        row["qqq_minus_spy"] = row["qqq_return"] - row["spy_return"]
        for ticker in ["RSP", "IWM", "SMH", "HYG", "TLT"]:
            row[f"{ticker.lower()}_return"] = endpoint_return(panel[ticker], span.start, span.end)
        sector_returns: dict[str, float] = {}
        for ticker in SECTOR_TICKERS:
            inception = first_valid_date(panel[ticker])
            if inception is None or inception > pd.Timestamp(span.start):
                continue
            value = endpoint_return(panel[ticker], span.start, span.end)
            if np.isfinite(value):
                sector_returns[ticker] = value
                row[f"{ticker.lower()}_return"] = value
                row[f"{ticker.lower()}_excess_spy"] = value - row["spy_return"]
        ranked = sorted(sector_returns.items(), key=lambda kv: kv[1], reverse=True)
        row["rank_universe_n"] = len(ranked)
        row["rank_universe"] = ";".join(t for t, _ in ranked)
        row["leaders"] = "; ".join(f"{t} {v:.4f}" for t, v in ranked[:3])
        row["laggards"] = "; ".join(f"{t} {v:.4f}" for t, v in ranked[-3:])
        rows.append(row)
    return pd.DataFrame(rows)


def monthly_returns(panel: pd.DataFrame) -> pd.DataFrame:
    monthly = panel.resample("ME").last().pct_change(fill_method=None)
    monthly.index.name = "month_end"
    monthly["DEF"] = equal_weight_daily_index(panel, CORE_DEFENSIVES, "DEF").resample("ME").last().pct_change(fill_method=None)
    monthly["CYCLICAL"] = (
        equal_weight_daily_index(panel, ["XLE", "XLF", "XLI", "XLB"], "CYCLICAL")
        .resample("ME")
        .last()
        .pct_change(fill_method=None)
    )
    return monthly


def quarterly_returns(panel: pd.DataFrame) -> pd.DataFrame:
    quarterly = panel.resample("QE").last().pct_change(fill_method=None)
    quarterly.index.name = "quarter_end"
    quarterly["DEF"] = equal_weight_daily_index(panel, CORE_DEFENSIVES, "DEF").resample("QE").last().pct_change(fill_method=None)
    quarterly["CYCLICAL"] = (
        equal_weight_daily_index(panel, ["XLE", "XLF", "XLI", "XLB"], "CYCLICAL")
        .resample("QE")
        .last()
        .pct_change(fill_method=None)
    )
    return quarterly


def _bh_adjust(pvalues: pd.Series) -> pd.Series:
    valid = pvalues.astype(float).dropna().sort_values()
    if valid.empty:
        return pd.Series(dtype=float)
    m = len(valid)
    return (valid * m / np.arange(1, m + 1)).iloc[::-1].cummin().iloc[::-1].clip(upper=1.0)


def seasonality_table(monthly: pd.DataFrame, start_year: int, end_year: int, sample: str) -> pd.DataFrame:
    assets = ["SPY", "QQQ", "DEF", "XLV", "XLP", "XLU", "XLK", "XLE", "XLF", "XLI"]
    frame = monthly[(monthly.index.year >= start_year) & (monthly.index.year <= end_year)]
    rows: list[dict] = []
    for asset in assets:
        for month in range(1, 13):
            values = frame.loc[frame.index.month == month, asset].dropna()
            spy = frame.loc[values.index, "SPY"]
            excess = values - spy
            se = excess.std(ddof=1) / math.sqrt(len(excess)) if len(excess) > 1 else math.nan
            tstat = excess.mean() / se if se and np.isfinite(se) and se > 0 else math.nan
            pvalue = float(2 * stats.t.sf(abs(tstat), df=len(excess) - 1)) if len(excess) > 1 and np.isfinite(tstat) else math.nan
            rows.append(
                {
                    "sample": sample,
                    "start_year": start_year,
                    "end_year": end_year,
                    "asset": asset,
                    "month": month,
                    "n": len(values),
                    "mean_return": values.mean(),
                    "median_return": values.median(),
                    "positive_rate": (values > 0).mean(),
                    "mean_excess_spy": excess.mean(),
                    "median_excess_spy": excess.median(),
                    "excess_hit_rate": (excess > 0).mean(),
                    "excess_tstat": tstat,
                    "excess_pvalue": pvalue,
                }
            )
    result = pd.DataFrame(rows)
    # Benjamini-Hochberg within each sample/asset across the 12 calendar months.
    result["excess_bh_qvalue_asset"] = math.nan
    for (_, asset), index in result.groupby(["sample", "asset"]).groups.items():
        adjusted = _bh_adjust(result.loc[index, "excess_pvalue"])
        result.loc[adjusted.index, "excess_bh_qvalue_asset"] = adjusted
    # Also adjust the actual cross-asset discovery family.  SPY has zero
    # excess by construction and therefore no p-values.
    result["excess_bh_qvalue_family"] = math.nan
    for _, index in result.groupby("sample").groups.items():
        adjusted = _bh_adjust(result.loc[index, "excess_pvalue"])
        result.loc[adjusted.index, "excess_bh_qvalue_family"] = adjusted
    return result


def conditional_defensive_table(monthly: pd.DataFrame, start_year: int = 2013) -> pd.DataFrame:
    end = min(2025, int(monthly.index.max().year))
    frame = monthly[(monthly.index.year >= start_year) & (monthly.index.year <= end)].copy()
    rows: list[dict] = []
    for state, mask in {"SPY_up_month": frame["SPY"] > 0, "SPY_down_month": frame["SPY"] <= 0}.items():
        for asset in ["DEF", "XLV", "XLP", "XLU", "XLK"]:
            values = frame.loc[mask, asset].dropna()
            excess = values - frame.loc[values.index, "SPY"]
            se = excess.std(ddof=1) / math.sqrt(len(excess)) if len(excess) > 1 else math.nan
            half_width = stats.t.ppf(0.975, len(excess) - 1) * se if np.isfinite(se) else math.nan
            pvalue = float(stats.ttest_1samp(excess, 0.0).pvalue) if len(excess) > 1 else math.nan
            rows.append(
                {
                    "state": state,
                    "asset": asset,
                    "n": len(values),
                    "mean_return": values.mean(),
                    "mean_excess_spy": excess.mean(),
                    "excess_hit_rate": (excess > 0).mean(),
                    "mean_excess_ci_low": excess.mean() - half_width,
                    "mean_excess_ci_high": excess.mean() + half_width,
                    "mean_excess_pvalue": pvalue,
                }
            )
    # Test whether a bad SPY month predicts defensive leadership next month.
    next_def_excess = (frame["DEF"] - frame["SPY"]).shift(-1)
    for state, mask in {"after_SPY_up_month": frame["SPY"] > 0, "after_SPY_down_month": frame["SPY"] <= 0}.items():
        values = next_def_excess.loc[mask].dropna()
        se = values.std(ddof=1) / math.sqrt(len(values)) if len(values) > 1 else math.nan
        half_width = stats.t.ppf(0.975, len(values) - 1) * se if np.isfinite(se) else math.nan
        pvalue = float(stats.ttest_1samp(values, 0.0).pvalue) if len(values) > 1 else math.nan
        rows.append(
            {
                "state": state,
                "asset": "DEF_next_month_excess",
                "n": len(values),
                "mean_return": math.nan,
                "mean_excess_spy": values.mean(),
                "excess_hit_rate": (values > 0).mean(),
                "mean_excess_ci_low": values.mean() - half_width,
                "mean_excess_ci_high": values.mean() + half_width,
                "mean_excess_pvalue": pvalue,
            }
        )
    return pd.DataFrame(rows)


def defensive_beta_decomposition(monthly: pd.DataFrame, start_year: int = 2013) -> pd.DataFrame:
    """Separate ordinary low-beta cushioning from conditional rotation effects."""
    end_year = min(2025, int(monthly.index.max().year))
    frame = monthly.loc[(monthly.index.year >= start_year) & (monthly.index.year <= end_year), ["SPY", "DEF"]].dropna()
    regression = stats.linregress(frame["SPY"], frame["DEF"])
    actual_excess = frame["DEF"] - frame["SPY"]
    model_excess = regression.intercept + (regression.slope - 1.0) * frame["SPY"]
    residual = actual_excess - model_excess
    rows: list[dict] = []
    states = {
        "all_months": pd.Series(True, index=frame.index),
        "SPY_up_month": frame["SPY"] > 0,
        "SPY_down_month": frame["SPY"] <= 0,
    }
    for state, mask in states.items():
        r = residual.loc[mask]
        rows.append(
            {
                "state": state,
                "n": len(r),
                "def_beta_to_spy": regression.slope,
                "monthly_alpha": regression.intercept,
                "r_squared": regression.rvalue**2,
                "observed_mean_excess_spy": actual_excess.loc[mask].mean(),
                "beta_model_mean_excess_spy": model_excess.loc[mask].mean(),
                "conditional_residual_mean": r.mean(),
                "conditional_residual_tstat": float(stats.ttest_1samp(r, 0.0).statistic) if len(r) > 1 else math.nan,
                "conditional_residual_pvalue": float(stats.ttest_1samp(r, 0.0).pvalue) if len(r) > 1 else math.nan,
            }
        )
    return pd.DataFrame(rows)


def election_phase(year: int) -> str:
    return {0: "election", 1: "post_election", 2: "midterm", 3: "pre_election"}[year % 4]


def _horizon_return(series: pd.Series, year: int, horizon: str) -> float:
    windows = {
        "full_year": (f"{year}-01-01", f"{year}-12-31"),
        "apr_oct": (f"{year}-04-01", f"{year}-10-31"),
        "jul_dec": (f"{year}-07-01", f"{year}-12-31"),
        "q2": (f"{year}-04-01", f"{year}-06-30"),
    }
    start, end = windows[horizon]
    return period_return_with_prior_close(series, start, end)


def election_cycle_tables(panel: pd.DataFrame, start_year: int, end_year: int, sample: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    assets = ["SPY", "QQQ", "DEF", "XLV", "XLP", "XLU", "XLK"]
    daily = panel.copy()
    daily["DEF"] = equal_weight_daily_index(panel, CORE_DEFENSIVES, "DEF")
    yearly_rows: list[dict] = []
    for year in range(start_year, end_year + 1):
        for horizon in ["full_year", "apr_oct", "jul_dec", "q2"]:
            spy_return = _horizon_return(daily["SPY"], year, horizon)
            for asset in assets:
                value = _horizon_return(daily[asset], year, horizon)
                yearly_rows.append(
                    {
                        "sample": sample,
                        "year": year,
                        "phase": election_phase(year),
                        "horizon": horizon,
                        "asset": asset,
                        "return": value,
                        "excess_spy": value - spy_return,
                    }
                )
    yearly = pd.DataFrame(yearly_rows)
    agg = (
        yearly.groupby(["sample", "phase", "horizon", "asset"], as_index=False)
        .agg(
            n=("return", "count"),
            mean_return=("return", "mean"),
            median_return=("return", "median"),
            positive_rate=("return", lambda x: float((x > 0).mean())),
            mean_excess_spy=("excess_spy", "mean"),
            excess_hit_rate=("excess_spy", lambda x: float((x > 0).mean())),
        )
    )
    return yearly, agg


def midterm_permutation_tests(yearly: pd.DataFrame, seed: int = 20260712, n_perm: int = 20_000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for (sample, horizon, asset), group in yearly.groupby(["sample", "horizon", "asset"]):
        field = "return" if asset in {"SPY", "QQQ"} else "excess_spy"
        values = group[field].dropna()
        labels = group.loc[values.index, "phase"].eq("midterm").to_numpy()
        data = values.to_numpy(dtype=float)
        if labels.sum() < 2 or (~labels).sum() < 2:
            continue
        observed = float(data[labels].mean() - data[~labels].mean())
        count = 0
        for _ in range(n_perm):
            shuffled = rng.permutation(labels)
            perm = float(data[shuffled].mean() - data[~shuffled].mean())
            count += abs(perm) >= abs(observed)
        rows.append(
            {
                "sample": sample,
                "horizon": horizon,
                "asset": asset,
                "field": field,
                "n_midterm": int(labels.sum()),
                "n_other": int((~labels).sum()),
                "midterm_mean": float(data[labels].mean()),
                "other_mean": float(data[~labels].mean()),
                "midterm_minus_other": observed,
                "permutation_pvalue_two_sided": (count + 1) / (n_perm + 1),
                "n_permutations": n_perm,
            }
        )
    result = pd.DataFrame(rows)
    result["permutation_bh_qvalue_sample"] = math.nan
    for _, index in result.groupby("sample").groups.items():
        adjusted = _bh_adjust(result.loc[index, "permutation_pvalue_two_sided"])
        result.loc[adjusted.index, "permutation_bh_qvalue_sample"] = adjusted
    adjusted = _bh_adjust(result["permutation_pvalue_two_sided"])
    result["permutation_bh_qvalue_global"] = math.nan
    result.loc[adjusted.index, "permutation_bh_qvalue_global"] = adjusted
    return result


def _final_week_complete(series: pd.Series) -> bool:
    """Fail closed on a partial final week while allowing common Friday closures."""
    last_session = series.dropna().index[-1]
    if last_session.weekday() == 4:
        return True
    friday_label = last_session + pd.offsets.Week(weekday=4)
    closure_rules = [
        GoodFriday,
        Holiday("New Year's Day", month=1, day=1, observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
    ]
    for rule in closure_rules:
        if friday_label in rule.dates(friday_label - pd.Timedelta(days=7), friday_label + pd.Timedelta(days=7)):
            return last_session.weekday() == 3
    return False


def weekly_macd(series: pd.Series) -> pd.DataFrame:
    source = series.dropna().sort_index()
    weekly = source.resample("W-FRI").last()
    if len(weekly) and not _final_week_complete(source):
        weekly = weekly.iloc[:-1]
    macd = weekly.ewm(span=12, adjust=False).mean() - weekly.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    state = hist > 0
    cross = state.astype(int).diff()
    trailing_high = weekly.rolling(52, min_periods=26).max()
    delta = weekly.diff()
    avg_gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi14 = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss.replace(0, np.nan))
    recent_rsi_ge70 = rsi14.rolling(4, min_periods=1).max() >= 70
    return pd.DataFrame(
        {
            "price": weekly,
            "macd": macd,
            "signal": signal,
            "histogram": hist,
            "bullish_state": state,
            "cross": cross,
            "distance_from_52w_high": weekly / trailing_high - 1.0,
            "rsi14": rsi14,
            "recent_rsi_ge70": recent_rsi_ge70,
        }
    )


def macd_event_study(panel: pd.DataFrame, start: str = "2013-01-01") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    horizons = {"4w": 20, "8w": 40, "13w": 65, "26w": 130, "52w": 252}
    event_rows: list[dict] = []
    current_rows: list[dict] = []
    for ticker in ["SPY", "QQQ"]:
        daily = panel[ticker].dropna().sort_index()
        macd = weekly_macd(daily)
        events = macd.loc[pd.Timestamp(start) :]
        events = events[events["cross"].abs() == 1]
        for signal_date, event in events.iterrows():
            future_dates = daily.index[daily.index > signal_date]
            if future_dates.empty:
                continue
            entry_date = future_dates[0]
            entry_loc = int(daily.index.get_loc(entry_date))
            direction = "bullish" if event["cross"] > 0 else "bearish"
            zero_bucket = "above_zero" if event["macd"] > 0 else "below_zero"
            near_high = bool(event["distance_from_52w_high"] >= -0.05)
            row: dict[str, object] = {
                "asset": ticker,
                "signal_date": signal_date.date().isoformat(),
                "entry_date": entry_date.date().isoformat(),
                "direction": direction,
                "zero_bucket": zero_bucket,
                "near_52w_high": near_high,
                "signal_price": event["price"],
                "entry_price": daily.iloc[entry_loc],
                "macd": event["macd"],
                "signal": event["signal"],
                "histogram": event["histogram"],
                "distance_from_52w_high": event["distance_from_52w_high"],
                "rsi14": event["rsi14"],
                "recent_rsi_ge70": bool(event["recent_rsi_ge70"]),
            }
            for label, sessions in horizons.items():
                target_loc = entry_loc + sessions
                if target_loc >= len(daily):
                    row[f"forward_return_{label}"] = math.nan
                    row[f"max_drawdown_{label}"] = math.nan
                    continue
                path = daily.iloc[entry_loc : target_loc + 1]
                row[f"forward_return_{label}"] = float(path.iloc[-1] / path.iloc[0] - 1.0)
                row[f"max_drawdown_{label}"] = float((path / path.cummax() - 1.0).min())
            event_rows.append(row)
        latest = macd.iloc[-1]
        last_bull = macd.index[macd["cross"] == 1]
        last_bear = macd.index[macd["cross"] == -1]
        current_rows.append(
            {
                "asset": ticker,
                "as_of": daily.index[-1].date().isoformat(),
                "weekly_label": macd.index[-1].date().isoformat(),
                "week_complete": bool(macd.index[-1] <= daily.index[-1]),
                "price": latest["price"],
                "macd": latest["macd"],
                "signal": latest["signal"],
                "histogram": latest["histogram"],
                "rsi14": latest["rsi14"],
                "histogram_from_13w_peak": float(latest["histogram"] / macd["histogram"].tail(13).max() - 1.0),
                "bullish_state": bool(latest["bullish_state"]),
                "last_bullish_cross": last_bull[-1].date().isoformat() if len(last_bull) else None,
                "last_bearish_cross": last_bear[-1].date().isoformat() if len(last_bear) else None,
            }
        )
    events = pd.DataFrame(event_rows)
    summaries: list[dict] = []
    for asset in ["SPY", "QQQ"]:
        asset_events = events[events["asset"] == asset]
        groups = {
            "bullish_all": asset_events[asset_events["direction"] == "bullish"],
            "bullish_below_zero": asset_events[(asset_events["direction"] == "bullish") & (asset_events["zero_bucket"] == "below_zero")],
            "bearish_all": asset_events[asset_events["direction"] == "bearish"],
            "bearish_above_zero": asset_events[(asset_events["direction"] == "bearish") & (asset_events["zero_bucket"] == "above_zero")],
            "bearish_near_high": asset_events[(asset_events["direction"] == "bearish") & (asset_events["near_52w_high"])],
            "bearish_recent_rsi_ge70": asset_events[(asset_events["direction"] == "bearish") & (asset_events["recent_rsi_ge70"])],
        }
        for group_name, group in groups.items():
            for label in horizons:
                values = group[f"forward_return_{label}"].dropna()
                drawdowns = group[f"max_drawdown_{label}"].dropna()
                summaries.append(
                    {
                        "asset": asset,
                        "event_group": group_name,
                        "horizon": label,
                        "n": len(values),
                        "mean_forward_return": values.mean(),
                        "median_forward_return": values.median(),
                        "positive_rate": (values > 0).mean(),
                        "mean_max_drawdown": drawdowns.mean(),
                        "median_max_drawdown": drawdowns.median(),
                        "inference_note": "descriptive only; forward windows can overlap and are serially dependent",
                    }
                )
        # Ordinary completed weeks are the baseline.  Use the same next-session
        # entry convention and daily-session horizons as the crossover events.
        daily = panel[asset].dropna().sort_index()
        ordinary: dict[str, list[float]] = {label: [] for label in horizons}
        ordinary_dd: dict[str, list[float]] = {label: [] for label in horizons}
        for signal_date in weekly_macd(daily).loc[pd.Timestamp(start) :].index:
            future_dates = daily.index[daily.index > signal_date]
            if future_dates.empty:
                continue
            entry_loc = int(daily.index.get_loc(future_dates[0]))
            for label, sessions in horizons.items():
                target_loc = entry_loc + sessions
                if target_loc >= len(daily):
                    continue
                path = daily.iloc[entry_loc : target_loc + 1]
                ordinary[label].append(float(path.iloc[-1] / path.iloc[0] - 1.0))
                ordinary_dd[label].append(float((path / path.cummax() - 1.0).min()))
        for label in horizons:
            values = pd.Series(ordinary[label], dtype=float)
            drawdowns = pd.Series(ordinary_dd[label], dtype=float)
            summaries.append(
                {
                    "asset": asset,
                    "event_group": "unconditional_weekly",
                    "horizon": label,
                    "n": len(values),
                    "mean_forward_return": values.mean(),
                    "median_forward_return": values.median(),
                    "positive_rate": (values > 0).mean(),
                    "mean_max_drawdown": drawdowns.mean(),
                    "median_max_drawdown": drawdowns.median(),
                    "inference_note": "descriptive only; forward windows overlap heavily and are serially dependent",
                }
            )
    return events, pd.DataFrame(summaries), pd.DataFrame(current_rows)


def _performance_stats(
    returns: pd.Series,
    exposure: pd.Series,
    switches: int,
    periods_per_year: int = 252,
) -> dict[str, float | int]:
    r = returns.dropna()
    wealth = (1.0 + r).cumprod()
    wealth_with_start = pd.concat([pd.Series([1.0]), wealth.reset_index(drop=True)], ignore_index=True)
    years = (r.index[-1] - r.index[0]).days / 365.2425 if len(r) > 1 else math.nan
    cagr = wealth.iloc[-1] ** (1.0 / years) - 1.0 if years > 0 else math.nan
    vol = r.std(ddof=1) * math.sqrt(periods_per_year)
    sharpe = r.mean() / r.std(ddof=1) * math.sqrt(periods_per_year) if r.std(ddof=1) > 0 else math.nan
    mdd = (wealth_with_start / wealth_with_start.cummax() - 1.0).min()
    return {
        "total_return": wealth.iloc[-1] - 1.0,
        "cagr": cagr,
        "annualized_volatility": vol,
        "sharpe_zero_rf": sharpe,
        "max_drawdown": mdd,
        "time_in_market": exposure.reindex(r.index).mean(),
        "switches": switches,
        "n_observations": len(r),
        "periods_per_year": periods_per_year,
    }


def _next_session_close_positions(
    signal_series: pd.Series,
    daily_index: pd.DatetimeIndex,
) -> tuple[pd.Series, pd.Series]:
    """Return close-to-close exposure and turnover for next-session-close trades."""
    updates = pd.Series(np.nan, index=daily_index, dtype=float)
    for signal_date, state in signal_series.items():
        future = daily_index[daily_index > signal_date]
        if len(future):
            updates.loc[future[0]] = float(state)
    position_after_close = updates.ffill().fillna(0.0)
    held_for_return = position_after_close.shift(1).fillna(0.0)
    turnover_at_close = position_after_close.diff().abs().fillna(position_after_close.abs())
    return held_for_return, turnover_at_close


def macd_strategy_table(
    return_panel: pd.DataFrame,
    signal_panel: pd.DataFrame | None = None,
    signal_price_basis: str = "adjusted_total_return",
    cash_rate: pd.Series | None = None,
    start: str = "2013-01-01",
    cost_bps: float = 10.0,
    include_buy_hold: bool = True,
) -> pd.DataFrame:
    signal_panel = return_panel if signal_panel is None else signal_panel
    rows: list[dict] = []
    for ticker in ["SPY", "QQQ"]:
        asset = return_panel[ticker].dropna().sort_index().loc[pd.Timestamp(start) :]
        asset_return = asset.pct_change(fill_method=None)
        signal_state = weekly_macd(signal_panel[ticker])["bullish_state"].loc[pd.Timestamp(start) :]
        position, turnover = _next_session_close_positions(signal_state, asset.index)
        zero_cash = pd.Series(0.0, index=asset.index)
        strategies: list[tuple[str, pd.Series, str]] = [("weekly_macd_bull_zero_cash", zero_cash, "zero_yield")]
        if cash_rate is not None and not cash_rate.empty:
            annual_rate = cash_rate.reindex(asset.index).ffill().bfill() / 100.0
            effr_cash = (1.0 + annual_rate).pow(1.0 / 252.0) - 1.0
            strategies.append(("weekly_macd_bull_effr_cash", effr_cash, "effective_federal_funds_rate"))
        for name, cash_return, cash_proxy in strategies:
            timing = position * asset_return + (1.0 - position) * cash_return - turnover * (cost_bps / 10_000.0)
            row = {
                "asset": ticker,
                "strategy": name,
                "signal_price_basis": signal_price_basis,
                "return_price_basis": "adjusted_total_return",
                "execution": "next_trading_session_close_after_weekly_signal",
                "cash_proxy": cash_proxy,
                "cost_bps_per_switch": cost_bps,
            }
            row.update(_performance_stats(timing, position, int((turnover > 0).sum())))
            rows.append(row)
        if include_buy_hold:
            row = {
                "asset": ticker,
                "strategy": "buy_and_hold",
                "signal_price_basis": "not_applicable",
                "return_price_basis": "adjusted_total_return",
                "execution": "continuous",
                "cash_proxy": "not_applicable",
                "cost_bps_per_switch": 0.0,
            }
            row.update(_performance_stats(asset_return, pd.Series(1.0, index=asset.index), 0))
            rows.append(row)
    return pd.DataFrame(rows)


def macd_price_basis_robustness(adjusted_panel: pd.DataFrame, raw_panel: pd.DataFrame, start: str = "2013-01-01") -> pd.DataFrame:
    rows: list[dict] = []
    for ticker in ["SPY", "QQQ"]:
        adjusted = weekly_macd(adjusted_panel[ticker]).loc[pd.Timestamp(start) :]
        raw = weekly_macd(raw_panel[ticker]).loc[pd.Timestamp(start) :]
        for direction, cross_value in [("bullish", 1.0), ("bearish", -1.0), ("all", None)]:
            adj_dates = set(adjusted.index[adjusted["cross"].abs() == 1] if cross_value is None else adjusted.index[adjusted["cross"] == cross_value])
            raw_dates = set(raw.index[raw["cross"].abs() == 1] if cross_value is None else raw.index[raw["cross"] == cross_value])
            union = adj_dates | raw_dates
            rows.append(
                {
                    "asset": ticker,
                    "direction": direction,
                    "adjusted_signal_count": len(adj_dates),
                    "raw_signal_count": len(raw_dates),
                    "exact_date_matches": len(adj_dates & raw_dates),
                    "jaccard_similarity": len(adj_dates & raw_dates) / len(union) if union else math.nan,
                }
            )
    return pd.DataFrame(rows)


def macd_bear_to_bull_episodes(panel: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for asset in ["SPY", "QQQ"]:
        daily = panel[asset].dropna().sort_index()
        asset_events = events[events["asset"] == asset].copy()
        asset_events["signal_date"] = pd.to_datetime(asset_events["signal_date"])
        bears = asset_events[asset_events["direction"] == "bearish"].sort_values("signal_date")
        bulls = asset_events[asset_events["direction"] == "bullish"].sort_values("signal_date")
        for _, bear in bears.iterrows():
            following = bulls[bulls["signal_date"] > bear["signal_date"]]
            if following.empty:
                continue
            bull = following.iloc[0]
            start_date = pd.Timestamp(bear["entry_date"])
            end_date = pd.Timestamp(bull["entry_date"])
            path = daily.loc[start_date:end_date]
            if len(path) < 2:
                continue
            rows.append(
                {
                    "asset": asset,
                    "bearish_signal_date": bear["signal_date"].date().isoformat(),
                    "bearish_entry_date": start_date.date().isoformat(),
                    "next_bullish_signal_date": bull["signal_date"].date().isoformat(),
                    "next_bullish_entry_date": end_date.date().isoformat(),
                    "weeks_out_of_market": (end_date - start_date).days / 7.0,
                    "asset_return_while_out": float(path.iloc[-1] / path.iloc[0] - 1.0),
                    "max_adverse_excursion_from_exit_close": float((path / path.iloc[0] - 1.0).min()),
                    "positive_return_while_out": bool(path.iloc[-1] > path.iloc[0]),
                }
            )
    return pd.DataFrame(rows)


def current_market_snapshot(panel: pd.DataFrame) -> pd.DataFrame:
    end = panel["SPY"].dropna().index[-1]
    rows: list[dict] = []
    for ticker in ["SPY", "QQQ", "RSP", "IWM", "SMH"] + SECTOR_TICKERS + ["HYG", "TLT", "_VIX"]:
        s = panel[ticker].dropna().loc[:end]
        if s.empty:
            continue
        row: dict[str, object] = {"asset": ticker, "as_of": end.date().isoformat(), "price": s.iloc[-1]}
        for label, sessions in {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "12m": 252}.items():
            row[f"return_{label}"] = float(s.iloc[-1] / s.iloc[-sessions - 1] - 1.0) if len(s) > sessions else math.nan
        prior_year = s.loc[s.index < pd.Timestamp(f"{end.year}-01-01")]
        row["return_ytd"] = float(s.iloc[-1] / prior_year.iloc[-1] - 1.0) if not prior_year.empty else math.nan
        row["drawdown_52w"] = float(s.iloc[-1] / s.tail(252).max() - 1.0)
        row["distance_from_50d_ma"] = float(s.iloc[-1] / s.tail(50).mean() - 1.0)
        row["distance_from_200d_ma"] = float(s.iloc[-1] / s.tail(200).mean() - 1.0)
        if ticker in SECTOR_TICKERS:
            spy = panel["SPY"].dropna().loc[:end]
            for label, sessions in {"1m": 21, "3m": 63, "6m": 126}.items():
                row[f"excess_spy_{label}"] = row[f"return_{label}"] - float(spy.iloc[-1] / spy.iloc[-sessions - 1] - 1.0)
        rows.append(row)
    return pd.DataFrame(rows)


def current_macro_snapshot(data_root: Path) -> pd.DataFrame:
    rows: list[dict] = []
    loaded: dict[str, pd.Series] = {}
    for code, name in FRED_SERIES.items():
        s = load_fred_series(data_root, code, name)
        loaded[name] = s
        if s.empty:
            continue
        rows.append({"series": code, "field": name, "as_of": s.index[-1].date().isoformat(), "value": s.iloc[-1], "transform": "level"})
    for name, label in [("headline_cpi", "headline_cpi_yoy"), ("core_pce", "core_pce_yoy")]:
        s = loaded.get(name, pd.Series(dtype=float))
        if len(s) >= 13:
            yoy = s.pct_change(12).dropna()
            rows.append({"series": "derived", "field": label, "as_of": yoy.index[-1].date().isoformat(), "value": yoy.iloc[-1], "transform": "12m_pct_change"})
    payroll = loaded.get("payrolls", pd.Series(dtype=float))
    if len(payroll) >= 2:
        change = payroll.diff().dropna()
        rows.append({"series": "derived", "field": "payroll_change_latest_thousands", "as_of": change.index[-1].date().isoformat(), "value": change.iloc[-1], "transform": "1m_difference"})
    return pd.DataFrame(rows)


def current_breadth_snapshot(data_root: Path) -> pd.DataFrame:
    closes_path = data_root / "breadth" / "_closes_cache.parquet"
    constituents_path = data_root / "breadth" / "constituents.parquet"
    if not closes_path.exists() or not constituents_path.exists():
        return pd.DataFrame()
    closes = pd.read_parquet(closes_path).sort_index()
    closes.index = _naive_index(closes.index)
    constituents = pd.read_parquet(constituents_path)
    constituents.index = constituents.index.astype(str)
    last = closes.iloc[-1]
    mean_50 = closes.tail(50).mean()
    mean_200 = closes.tail(200).mean()
    count_50 = closes.tail(50).count()
    count_200 = closes.tail(200).count()
    # Preserve missingness rather than counting an unavailable current quote or
    # moving average as a stock below trend.  The two valid denominators are
    # exported explicitly because current-member quote coverage can differ.
    above_50 = (last > mean_50).where(last.notna() & (count_50 >= 50))
    above_200 = (last > mean_200).where(last.notna() & (count_200 >= 200))
    frame = pd.DataFrame({"above_50d": above_50, "above_200d": above_200}).join(constituents[["sector"]], how="inner")
    rows = [
        {
            "as_of": closes.index[-1].date().isoformat(),
            "group": "S&P 500 current constituents",
            "n_current_members": len(frame),
            "n_valid_50d": int(frame["above_50d"].notna().sum()),
            "n_valid_200d": int(frame["above_200d"].notna().sum()),
            "pct_above_50d": frame["above_50d"].mean(),
            "pct_above_200d": frame["above_200d"].mean(),
            "membership_basis": "current constituent snapshot; survivorship-bound for historical use",
        }
    ]
    for sector, group in frame.groupby("sector"):
        rows.append(
            {
                "as_of": closes.index[-1].date().isoformat(),
                "group": sector,
                "n_current_members": len(group),
                "n_valid_50d": int(group["above_50d"].notna().sum()),
                "n_valid_200d": int(group["above_200d"].notna().sum()),
                "pct_above_50d": group["above_50d"].mean(),
                "pct_above_200d": group["above_200d"].mean(),
                "membership_basis": "current constituent snapshot",
            }
        )
    return pd.DataFrame(rows)


def write_outputs(repo_root: Path, output_dir: Path) -> None:
    data_root = repo_root / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    panel = load_yahoo_panel(data_root, value_col="close")
    raw_signal_panel = load_yahoo_panel(data_root, value_col="close_price", tickers=["SPY", "QQQ"])
    as_of = panel["SPY"].dropna().index[-1]

    annual_scoreboard(panel, int(as_of.year)).to_csv(output_dir / "annual_index_sector_scoreboard.csv", index=False)
    regime_span_cards(panel).to_csv(output_dir / "regime_rotation_spans.csv", index=False)
    regime_span_cards(panel, CROSS_YEAR_BRIDGES).to_csv(output_dir / "cross_year_regime_bridges.csv", index=False)

    monthly = monthly_returns(panel)
    monthly.loc["2012-12-31":as_of].to_csv(output_dir / "monthly_total_returns.csv")
    quarterly_returns(panel).loc["2012-12-31":as_of].to_csv(output_dir / "quarterly_total_returns.csv")
    modern_end = min(2025, int(as_of.year) - (0 if as_of.month == 12 else 1))
    modern = seasonality_table(monthly, 2013, modern_end, f"modern_2013_{modern_end}")
    expanded = seasonality_table(monthly, 1999, modern_end, f"expanded_1999_{modern_end}")
    pre_modern = seasonality_table(monthly, 1999, 2012, "pre_modern_1999_2012")
    pd.concat([modern, expanded, pre_modern], ignore_index=True).to_csv(output_dir / "sector_month_seasonality.csv", index=False)
    conditional_defensive_table(monthly).to_csv(output_dir / "defensive_contemporaneous_vs_predictive.csv", index=False)
    defensive_beta_decomposition(monthly).to_csv(output_dir / "defensive_beta_decomposition.csv", index=False)

    election_yearly_frames: list[pd.DataFrame] = []
    election_agg_frames: list[pd.DataFrame] = []
    for start_year, end_year, sample in [
        (2013, modern_end, f"modern_2013_{modern_end}"),
        (1999, modern_end, f"expanded_1999_{modern_end}"),
        (1999, 2012, "pre_modern_1999_2012"),
    ]:
        yearly, agg = election_cycle_tables(panel, start_year, end_year, sample)
        election_yearly_frames.append(yearly)
        election_agg_frames.append(agg)
    election_yearly = pd.concat(election_yearly_frames, ignore_index=True)
    election_yearly.to_csv(output_dir / "election_cycle_yearly_observations.csv", index=False)
    pd.concat(election_agg_frames, ignore_index=True).to_csv(output_dir / "election_cycle_phase_summary.csv", index=False)
    midterm_permutation_tests(election_yearly).to_csv(output_dir / "midterm_permutation_tests.csv", index=False)

    macd_events, macd_summary, macd_current = macd_event_study(panel)
    macd_events.to_csv(output_dir / "weekly_macd_events.csv", index=False)
    macd_summary.to_csv(output_dir / "weekly_macd_event_summary.csv", index=False)
    macd_bear_to_bull_episodes(panel, macd_events).to_csv(output_dir / "weekly_macd_bear_to_bull_episodes.csv", index=False)
    dff = load_fred_series(data_root, "DFF", "fed_funds")
    adjusted_strategy = macd_strategy_table(panel, cash_rate=dff)
    raw_signal_strategy = macd_strategy_table(
        panel,
        signal_panel=raw_signal_panel,
        signal_price_basis="raw_close_price",
        cash_rate=dff,
        include_buy_hold=False,
    )
    pd.concat([adjusted_strategy, raw_signal_strategy], ignore_index=True).to_csv(
        output_dir / "weekly_macd_strategy_comparison.csv", index=False
    )
    macd_price_basis_robustness(panel, raw_signal_panel).to_csv(
        output_dir / "weekly_macd_price_basis_robustness.csv", index=False
    )
    macd_current.to_csv(output_dir / "weekly_macd_current_state.csv", index=False)

    current_market_snapshot(panel).to_csv(output_dir / "current_market_snapshot.csv", index=False)
    current_macro_snapshot(data_root).to_csv(output_dir / "current_macro_snapshot.csv", index=False)
    current_breadth_snapshot(data_root).to_csv(output_dir / "current_breadth_snapshot.csv", index=False)

    metadata = {
        "schema_version": 2,
        "generated_from": "repo-local committed data stores",
        "market_data_as_of": as_of.date().isoformat(),
        "price_basis": "data/yahoo/<ticker>.parquet close (split+dividend adjusted total return)",
        "index_proxies": {"S&P 500": "SPY", "Nasdaq-100": "QQQ"},
        "macd": {
            "frequency": "weekly Friday-labeled close",
            "parameters": [12, 26, 9],
            "partial_week_policy": "drop incomplete final bins; allow common Friday market closures after a Thursday final session",
            "event_and_strategy_execution": "next trading session close after completed weekly signal",
            "event_horizons_trading_sessions": {"4w": 20, "8w": 40, "13w": 65, "26w": 130, "52w": 252},
            "event_inference": "descriptive only; overlapping forward windows are serially dependent and no naive IID confidence intervals are reported",
            "strategy_cash_variants": ["zero_yield", "effective_federal_funds_rate"],
            "cost_bps_per_one_way_switch": 10,
            "signal_price_bases": ["adjusted_total_return", "raw_close_price"],
            "strategy_return_price_basis": "adjusted_total_return",
        },
        "defensive_basket": {
            "members": CORE_DEFENSIVES,
            "construction": "equal-weight daily-rebalanced total-return index",
        },
        "seasonality_multiple_testing": {
            "qvalue_asset": "Benjamini-Hochberg across 12 months within each sample/asset",
            "qvalue_family": "Benjamini-Hochberg across all asset-month tests within each sample",
            "samples": [f"modern_2013_{modern_end}", f"expanded_1999_{modern_end}", "pre_modern_1999_2012"],
        },
        "election_permutation": {
            "seed": 20260712,
            "n_permutations": 20000,
            "qvalues": "Benjamini-Hochberg within sample and across the full reported family",
            "exchangeability_caveat": "four-year calendar labels are deterministic; permutation results are exploratory",
        },
        "breadth": {
            "membership": "current constituents only",
            "eligibility_50d": "valid latest observation and 50 valid daily observations",
            "eligibility_200d": "valid latest observation and 200 valid daily observations",
            "historical_use": "prohibited because membership is survivorship-bound",
        },
        "regime_boundaries": "ex-post descriptive; not a real-time signal",
        "sector_inception_caveats": {
            "XLRE": "2015-10-07/08; partial 2015 excluded from annual ranks",
            "XLC": "2018-06-18/19; partial 2018 excluded from annual ranks",
            "GICS_2018": "major names migrated among XLK/XLY/XLC; pre/post sector leadership is not compositionally identical",
        },
        "outputs": sorted(path.name for path in output_dir.glob("*.csv")),
    }
    (output_dir / "methodology.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(metadata['outputs'])} CSV artifacts + methodology.json to {output_dir}")
    print(f"Market data through {as_of.date().isoformat()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research/artifacts/sp500_nasdaq_regime_rotation_2013_2026"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    root = args.repo_root.resolve()
    out = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    write_outputs(root, out)
