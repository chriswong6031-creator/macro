#!/usr/bin/env python3
"""Build the evidence pack for the July 2026 market-navigation memo.

The harness is deliberately descriptive.  It captures the current cross-asset
tape, checks the user's midterm-healthcare statistic, describes completed-week
technical states, tests whether technology and healthcare rallies can coexist,
and builds a historical oil-plus-real-yield analogue.  It does not emit a
portfolio score or convert technical states into an autonomous trade signal.

Examples
--------
Refresh the point-in-time Yahoo snapshot and rebuild every artifact::

    python scripts/research/july_2026_market_navigation.py --refresh-live

Rebuild from the committed live-price snapshot::

    python scripts/research/july_2026_market_navigation.py
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


AS_OF = pd.Timestamp("2026-07-13")
LIVE_TICKERS = [
    "SPY",
    "QQQ",
    "RSP",
    "SMH",
    "IGV",
    "XLV",
    "RSPH",
    "XLF",
    "XLP",
    "XLE",
    "MAGS",
    "EWY",
    "XBI",
    "IBB",
    "WM",
    "MCK",
    "GILD",
    "REGN",
    "BMY",
    "VEEV",
    "CME",
    "ICE",
    "CB",
    "PGR",
    "UNH",
    "MSFT",
    "AMZN",
    "META",
    "AAPL",
    "NVDA",
    "GOOGL",
    "MU",
    "WDC",
    "KO",
    "JNJ",
]
WATCHLIST = ["WM", "MCK", "GILD", "REGN", "BMY", "VEEV", "CME"]
ANALOG_ASSETS = ["SPY", "XLV", "XLK", "XLE", "XLF", "XLP"]


def _naive_index(index: Iterable) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(index))
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    return idx.normalize()


def load_local_yahoo(data_root: Path, ticker: str) -> pd.Series:
    path = data_root / "yahoo" / f"{ticker}.parquet"
    if not path.exists():
        return pd.Series(dtype=float, name=ticker)
    frame = pd.read_parquet(path)
    for col in ("close", "close_price", "adj_close"):
        if col in frame:
            series = pd.to_numeric(frame[col], errors="coerce")
            break
    else:
        return pd.Series(dtype=float, name=ticker)
    series.index = _naive_index(series.index)
    return series[~series.index.duplicated(keep="last")].sort_index().dropna().rename(ticker)


def load_fred(data_root: Path, code: str) -> pd.Series:
    path = data_root / "fred" / f"{code}.parquet"
    frame = pd.read_parquet(path)
    series = pd.to_numeric(frame.iloc[:, 0], errors="coerce")
    series.index = _naive_index(series.index)
    return series[~series.index.duplicated(keep="last")].sort_index().dropna().rename(code)


def download_live_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on local runtime
        raise RuntimeError("--refresh-live requires yfinance") from exc

    raw = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        auto_adjust=True,
        actions=False,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("Yahoo returned no live prices")
    if isinstance(raw.columns, pd.MultiIndex):
        level0 = set(map(str, raw.columns.get_level_values(0)))
        level1 = set(map(str, raw.columns.get_level_values(1)))
        if "Close" in level0:
            closes = raw["Close"]
        elif "Close" in level1:
            closes = raw.xs("Close", axis=1, level=1)
        else:
            raise RuntimeError("Yahoo response did not contain Close columns")
    else:
        closes = raw[["Close"]].rename(columns={"Close": tickers[0]})
    closes.index = _naive_index(closes.index)
    closes.columns = [str(c) for c in closes.columns]
    return closes.reindex(columns=tickers).sort_index()


def load_live_snapshot(
    output_dir: Path,
    as_of: pd.Timestamp,
    refresh: bool,
) -> tuple[pd.DataFrame, str]:
    source_path = output_dir / "source_live_adjusted_closes.csv"
    source_label = f"Yahoo Finance auto-adjusted close snapshot through {as_of.date().isoformat()}"
    if refresh:
        live = download_live_prices(
            LIVE_TICKERS,
            start="2023-01-01",
            end=(as_of + pd.Timedelta(days=2)).date().isoformat(),
        )
        live = live.loc[:as_of]
        live.to_csv(source_path, index_label="date")
        validate_live_snapshot(live, as_of)
        return live, source_label
    if source_path.exists():
        live = pd.read_csv(source_path, index_col=0, parse_dates=True)
        live.index = _naive_index(live.index)
        live = live.loc[:as_of]
        validate_live_snapshot(live, as_of)
        return live, source_label
    raise FileNotFoundError(f"{source_path} missing; run once with --refresh-live")


def validate_live_snapshot(live: pd.DataFrame, as_of: pd.Timestamp) -> None:
    """Fail closed when the point-in-time snapshot is incomplete or stale."""
    missing = sorted(set(LIVE_TICKERS) - set(live.columns))
    empty = sorted(ticker for ticker in LIVE_TICKERS if ticker in live and live[ticker].dropna().empty)
    stale: dict[str, str] = {}
    for ticker in LIVE_TICKERS:
        if ticker not in live or live[ticker].dropna().empty:
            continue
        latest = pd.Timestamp(live[ticker].dropna().index[-1]).normalize()
        if (as_of - latest).days > 4:
            stale[ticker] = latest.date().isoformat()
    if missing or empty or stale:
        raise RuntimeError(
            "invalid live-price snapshot: "
            f"missing_columns={missing}, empty_tickers={empty}, stale_tickers={stale}"
        )


def trailing_return(series: pd.Series, sessions: int) -> float:
    series = series.dropna()
    if len(series) <= sessions:
        return math.nan
    return float(series.iloc[-1] / series.iloc[-1 - sessions] - 1.0)


def current_returns(live: pd.DataFrame, source: str) -> pd.DataFrame:
    rows: list[dict] = []
    for ticker in live.columns:
        series = live[ticker].dropna()
        if series.empty:
            continue
        trailing_high = series.tail(252).max()
        mean50 = series.tail(50).mean() if len(series) >= 50 else math.nan
        mean200 = series.tail(200).mean() if len(series) >= 200 else math.nan
        rows.append(
            {
                "ticker": ticker,
                "as_of": series.index[-1].date().isoformat(),
                "close": series.iloc[-1],
                "return_1d": trailing_return(series, 1),
                "return_5d": trailing_return(series, 5),
                "return_10d": trailing_return(series, 10),
                "return_20d": trailing_return(series, 20),
                "return_63d": trailing_return(series, 63),
                "return_126d": trailing_return(series, 126),
                "distance_50d": series.iloc[-1] / mean50 - 1.0 if mean50 else math.nan,
                "distance_200d": series.iloc[-1] / mean200 - 1.0 if mean200 else math.nan,
                "drawdown_252d": series.iloc[-1] / trailing_high - 1.0,
                "source": source,
            }
        )
    return pd.DataFrame(rows).sort_values("ticker")


def weekly_technical_state(series: pd.Series, as_of: pd.Timestamp) -> dict:
    daily = series.dropna().sort_index().loc[:as_of]
    weekly = daily.resample("W-FRI").last()
    # A Friday-labeled week is accepted only when the source snapshot itself
    # reaches that Friday. This deliberately fails conservative on Friday
    # market holidays instead of treating a potentially stale partial week as
    # a completed signal bar.
    weekly = weekly.loc[(weekly.index <= as_of) & (weekly.index <= daily.index.max())]
    if len(weekly) < 30:
        return {}

    ema12 = weekly.ewm(span=12, adjust=False).mean()
    ema26 = weekly.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    change = weekly.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi_low = rsi.rolling(14).min()
    rsi_high = rsi.rolling(14).max()
    stoch_raw = 100 * (rsi - rsi_low) / (rsi_high - rsi_low)
    stoch_k = stoch_raw.rolling(3).mean()
    stoch_d = stoch_k.rolling(3).mean()

    ma10 = weekly.rolling(10).mean()
    ma40 = weekly.rolling(40).mean()
    return {
        "completed_week": weekly.index[-1].date().isoformat(),
        "weekly_close": weekly.iloc[-1],
        "return_4w": weekly.iloc[-1] / weekly.iloc[-5] - 1.0 if len(weekly) >= 5 else math.nan,
        "return_13w": weekly.iloc[-1] / weekly.iloc[-14] - 1.0 if len(weekly) >= 14 else math.nan,
        "macd": macd.iloc[-1],
        "macd_signal": signal.iloc[-1],
        "macd_hist": hist.iloc[-1],
        "macd_hist_prior": hist.iloc[-2],
        "macd_above_signal": bool(macd.iloc[-1] > signal.iloc[-1]),
        "macd_hist_improving": bool(hist.iloc[-1] > hist.iloc[-2]),
        "rsi_14": rsi.iloc[-1],
        "rsi_improving": bool(rsi.iloc[-1] > rsi.iloc[-2]),
        "stoch_rsi_k": stoch_k.iloc[-1],
        "stoch_rsi_d": stoch_d.iloc[-1],
        "stoch_k_above_d": bool(stoch_k.iloc[-1] > stoch_d.iloc[-1]),
        "above_10w": bool(weekly.iloc[-1] > ma10.iloc[-1]),
        "above_40w": bool(weekly.iloc[-1] > ma40.iloc[-1]),
        "method_note": "completed Friday bars only; descriptive state, not a validated entry signal",
    }


def watchlist_technicals(live: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    rows: list[dict] = []
    for ticker in WATCHLIST:
        if ticker not in live:
            continue
        state = weekly_technical_state(live[ticker], as_of)
        if state:
            rows.append({"ticker": ticker, **state})
    return pd.DataFrame(rows)


def exact_permutation_pvalue(values: pd.Series, midterm_mask: pd.Series) -> float:
    frame = pd.DataFrame({"value": values, "midterm": midterm_mask}).dropna()
    x = frame["value"].to_numpy(dtype=float)
    n_midterm = int(frame["midterm"].sum())
    observed = x[frame["midterm"].to_numpy()].mean() - x[~frame["midterm"].to_numpy()].mean()
    exceed = 0
    total = 0
    indices = range(len(x))
    for chosen in itertools.combinations(indices, n_midterm):
        mask = np.zeros(len(x), dtype=bool)
        mask[list(chosen)] = True
        stat = x[mask].mean() - x[~mask].mean()
        exceed += int(abs(stat) >= abs(observed) - 1e-15)
        total += 1
    return exceed / total


def midterm_validation(atlas_dir: Path) -> pd.DataFrame:
    yearly = pd.read_csv(atlas_dir / "election_cycle_yearly_observations.csv")
    expanded_all = yearly[
        (yearly["sample"] == "expanded_1999_2025")
        & (yearly["horizon"] == "jul_dec")
        & (yearly["asset"].isin(["XLV", "SPY", "XLK"]))
    ].copy()
    expanded_all = expanded_all.drop_duplicates(["year", "asset"])
    expanded = expanded_all[expanded_all["phase"] == "midterm"]

    rows: list[dict] = []
    for label, start in [("past_20_years_2006_2022", 2006), ("expanded_2002_2022", 2002)]:
        sample = expanded[(expanded["year"] >= start) & (expanded["year"] <= 2022)]
        for asset, group in sample.groupby("asset"):
            rows.append(
                {
                    "sample": label,
                    "asset": asset,
                    "n": len(group),
                    "mean_return": group["return"].mean(),
                    "median_return": group["return"].median(),
                    "positive_rate": (group["return"] > 0).mean(),
                    "mean_excess_spy": group["excess_spy"].mean(),
                    "excess_hit_rate": (group["excess_spy"] > 0).mean() if asset != "SPY" else math.nan,
                    "interpretation": "small-sample calendar prior; not a standalone trade rule",
                }
            )

    modern_years = expanded_all[
        (expanded_all["year"] >= 2003) & (expanded_all["year"] <= 2025)
    ]
    wide_return = modern_years.pivot(index="year", columns="asset", values="return")
    mask = pd.Series((wide_return.index % 4) == 2, index=wide_return.index)
    xlv_p = exact_permutation_pvalue(wide_return["XLV"], mask)
    excess = wide_return["XLV"] - wide_return["SPY"]
    excess_p = exact_permutation_pvalue(excess, mask)
    rows.append(
        {
            "sample": "2003_2025_exact_permutation",
            "asset": "XLV",
            "n": int(mask.sum()),
            "mean_return": wide_return.loc[mask, "XLV"].mean(),
            "median_return": wide_return.loc[mask, "XLV"].median(),
            "positive_rate": (wide_return.loc[mask, "XLV"] > 0).mean(),
            "mean_excess_spy": excess.loc[mask].mean(),
            "excess_hit_rate": (excess.loc[mask] > 0).mean(),
            "exact_pvalue_absolute_return": xlv_p,
            "exact_pvalue_excess_spy": excess_p,
            "interpretation": "two-sided exact label permutation; unadjusted exploratory p-values",
        }
    )
    return pd.DataFrame(rows)


def technology_healthcare_coexistence(data_root: Path) -> pd.DataFrame:
    panel = pd.concat(
        {ticker: load_local_yahoo(data_root, ticker) for ticker in ["XLK", "XLV", "SPY"]},
        axis=1,
        sort=True,
    )
    monthly = panel.resample("ME").last().pct_change().loc["2013-01-01":"2025-12-31"].dropna()
    xlk_up = monthly["XLK"] > 0
    xlk_strong = monthly["XLK"] >= 0.05
    rows = [
        {
            "sample": "2013_2025_months",
            "metric": "both_XLK_and_XLV_positive_rate_all_months",
            "n": len(monthly),
            "value": ((monthly["XLK"] > 0) & (monthly["XLV"] > 0)).mean(),
        },
        {
            "sample": "2013_2025_months",
            "metric": "XLV_positive_rate_when_XLK_positive",
            "n": int(xlk_up.sum()),
            "value": (monthly.loc[xlk_up, "XLV"] > 0).mean(),
        },
        {
            "sample": "2013_2025_months",
            "metric": "XLV_mean_return_when_XLK_positive",
            "n": int(xlk_up.sum()),
            "value": monthly.loc[xlk_up, "XLV"].mean(),
        },
        {
            "sample": "2013_2025_months",
            "metric": "XLV_mean_excess_when_XLK_positive",
            "n": int(xlk_up.sum()),
            "value": (monthly.loc[xlk_up, "XLV"] - monthly.loc[xlk_up, "XLK"]).mean(),
        },
        {
            "sample": "2013_2025_months",
            "metric": "XLV_excess_hit_rate_when_XLK_positive",
            "n": int(xlk_up.sum()),
            "value": (monthly.loc[xlk_up, "XLV"] > monthly.loc[xlk_up, "XLK"]).mean(),
        },
        {
            "sample": "2013_2025_months",
            "metric": "XLV_positive_rate_when_XLK_at_least_plus_5pct",
            "n": int(xlk_strong.sum()),
            "value": (monthly.loc[xlk_strong, "XLV"] > 0).mean(),
        },
        {
            "sample": "2013_2025_months",
            "metric": "XLV_mean_return_when_XLK_at_least_plus_5pct",
            "n": int(xlk_strong.sum()),
            "value": monthly.loc[xlk_strong, "XLV"].mean(),
        },
        {
            "sample": "2013_2025_months",
            "metric": "XLV_mean_excess_when_XLK_at_least_plus_5pct",
            "n": int(xlk_strong.sum()),
            "value": (
                monthly.loc[xlk_strong, "XLV"] - monthly.loc[xlk_strong, "XLK"]
            ).mean(),
        },
        {
            "sample": "2013_2025_months",
            "metric": "XLV_excess_hit_rate_when_XLK_at_least_plus_5pct",
            "n": int(xlk_strong.sum()),
            "value": (
                monthly.loc[xlk_strong, "XLV"] > monthly.loc[xlk_strong, "XLK"]
            ).mean(),
        },
    ]
    return pd.DataFrame(rows)


def oil_real_yield_analogue(data_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    prices = pd.concat({ticker: load_local_yahoo(data_root, ticker) for ticker in ANALOG_ASSETS}, axis=1)
    prices = prices.dropna(subset=["SPY"])
    macro = pd.concat(
        {
            "wti": load_fred(data_root, "DCOILWTICO"),
            "real_10y": load_fred(data_root, "DFII10"),
        },
        axis=1,
        sort=True,
    ).reindex(prices.index).ffill(limit=10)
    macro["wti_return_21d"] = macro["wti"].pct_change(21)
    macro["real_10y_change_21d_pp"] = macro["real_10y"].diff(21)
    macro["spy_above_200d"] = prices["SPY"] > prices["SPY"].rolling(200).mean()
    raw_dates = macro.index[
        (macro["wti_return_21d"] >= 0.10)
        & (macro["real_10y_change_21d_pp"] >= 0.15)
        & macro["spy_above_200d"]
    ]

    event_dates: list[pd.Timestamp] = []
    last_position = -10_000
    for date in raw_dates:
        position = prices.index.get_loc(date)
        if position - last_position >= 63:
            event_dates.append(date)
            last_position = position

    event_rows: list[dict] = []
    for date in event_dates:
        signal_i = prices.index.get_loc(date)
        entry_i = signal_i + 1
        if entry_i >= len(prices):
            continue
        base = {
            "signal_date": date.date().isoformat(),
            "entry_date": prices.index[entry_i].date().isoformat(),
            "wti_return_21d": macro.at[date, "wti_return_21d"],
            "real_10y_change_21d_pp": macro.at[date, "real_10y_change_21d_pp"],
            "spy_above_200d": True,
        }
        for horizon in (21, 63):
            exit_i = entry_i + horizon
            if exit_i >= len(prices):
                continue
            spy_forward = prices["SPY"].iloc[exit_i] / prices["SPY"].iloc[entry_i] - 1.0
            for asset in ANALOG_ASSETS:
                forward = prices[asset].iloc[exit_i] / prices[asset].iloc[entry_i] - 1.0
                event_rows.append(
                    {
                        **base,
                        "horizon_sessions": horizon,
                        "asset": asset,
                        "forward_return": forward,
                        "forward_excess_spy": forward - spy_forward,
                    }
                )
    events = pd.DataFrame(event_rows)
    summary = (
        events.groupby(["horizon_sessions", "asset"], as_index=False)
        .agg(
            n=("forward_return", "count"),
            mean_forward_return=("forward_return", "mean"),
            median_forward_return=("forward_return", "median"),
            positive_rate=("forward_return", lambda x: (x > 0).mean()),
            mean_excess_spy=("forward_excess_spy", "mean"),
            median_excess_spy=("forward_excess_spy", "median"),
            excess_hit_rate=("forward_excess_spy", lambda x: (x > 0).mean()),
            worst_forward_return=("forward_return", "min"),
        )
        .sort_values(["horizon_sessions", "asset"])
    )
    summary["definition"] = (
        "WTI 21-session return >=10%, real 10y +15bp or more, SPY above 200d; "
        "63-session de-overlap; enter next session after signal; descriptive analogue, no causal claim"
    )
    return events, summary


def build(args: argparse.Namespace) -> None:
    data_root = Path(args.data_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    as_of = pd.Timestamp(args.as_of).normalize()

    live, live_source = load_live_snapshot(output_dir, as_of, args.refresh_live)
    current_returns(live, live_source).to_csv(output_dir / "current_returns.csv", index=False)
    watchlist_technicals(live, as_of).to_csv(output_dir / "watchlist_weekly_technicals.csv", index=False)

    atlas_dir = Path(args.atlas_dir)
    midterm_validation(atlas_dir).to_csv(output_dir / "midterm_healthcare_validation.csv", index=False)
    technology_healthcare_coexistence(data_root).to_csv(
        output_dir / "technology_healthcare_coexistence.csv", index=False
    )
    analogue_events, analogue_summary = oil_real_yield_analogue(data_root)
    analogue_events.to_csv(output_dir / "oil_real_yield_analogue_events.csv", index=False)
    analogue_summary.to_csv(output_dir / "oil_real_yield_analogue_summary.csv", index=False)

    methodology = {
        "schema": 1,
        "as_of": as_of.date().isoformat(),
        "live_price_source": live_source,
        "live_price_basis": "Yahoo Finance auto-adjusted daily closes, captured point in time",
        "live_snapshot_end": max(live.index).date().isoformat(),
        "live_snapshot_sha256": hashlib.sha256(
            (output_dir / "source_live_adjusted_closes.csv").read_bytes()
        ).hexdigest(),
        "completed_week_rule": (
            "Friday-labeled bars at or before as_of whose Friday is present in the source; "
            "conservative on Friday market holidays"
        ),
        "return_basis": "close-to-close adjusted returns",
        "technical_basis_warning": (
            "weekly states use Yahoo auto-adjusted total-return closes and may differ from "
            "TradingView raw-close indicators around distributions"
        ),
        "midterm_window": "prior close before July 1 through final close of December",
        "midterm_warning": "calendar split is exploratory and must not be used as a standalone signal",
        "analogue_warning": (
            "conditional historical description only; thresholds were selected for this question and "
            "were not preregistered or corrected for search; entry is the next session after the "
            "signal close to avoid same-close look-ahead"
        ),
        "authority": "research evidence pack; no production signal or portfolio authority",
    }
    (output_dir / "methodology.json").write_text(json.dumps(methodology, indent=2) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data")
    parser.add_argument(
        "--atlas-dir",
        default="research/artifacts/sp500_nasdaq_regime_rotation_2013_2026",
    )
    parser.add_argument(
        "--output-dir",
        default="research/artifacts/july_2026_market_navigation",
    )
    parser.add_argument("--as-of", default=AS_OF.date().isoformat())
    parser.add_argument("--refresh-live", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    build(parse_args())
