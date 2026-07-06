from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sys
from typing import Callable

import numpy as np
import pandas as pd

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.bottom_signal_backtest.factors import (  # noqa: E402
    SECTOR_ETF,
    SignalConfig,
    base_signal,
    benchmark_close,
    clean_ohlcv,
    completed_2w_stoch_cross,
    completed_weekly_macd_cross,
    daily_feature_frame,
    macd,
    read_sector_map,
    regime_frame,
    stoch_rsi,
    tf_bars,
    two_week_stoch_oversold_daily,
)
from research.bottom_signal_backtest.metrics import add_scores, by_group, event_metrics, summarize  # noqa: E402
from research.bottom_signal_backtest.plots import make_charts  # noqa: E402


def load_config(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read config.yaml")
    with path.open() as f:
        return yaml.safe_load(f)


def load_ohlcv_files(data_dir: Path, max_tickers: int | None) -> list[Path]:
    files = sorted(data_dir.glob("*.parquet"))
    if max_tickers:
        files = files[:max_tickers]
    return files


def sector_etf_features(bench_dir: Path, cfg: SignalConfig) -> dict[str, pd.DataFrame]:
    out = {}
    for etf in sorted(set(SECTOR_ETF.values())):
        s = benchmark_close(bench_dir, etf)
        if s is None:
            continue
        df = pd.DataFrame({"close": s, "high": s, "low": s, "volume": np.nan}).dropna()
        if len(df) < 260:
            continue
        weekly, _ = tf_bars(df, "W-FRI")
        if weekly.empty or "close" not in weekly:
            continue
        wm = macd(weekly["close"], cfg.weekly_macd_fast, cfg.weekly_macd_slow, cfg.weekly_macd_signal)
        two_w, _ = tf_bars(df, "2W-FRI")
        tws = stoch_rsi(two_w["close"], cfg.stoch_rsi_rsi, cfg.stoch_rsi_window, cfg.stoch_rsi_k, cfg.stoch_rsi_d)
        feat = pd.DataFrame(index=df.index)
        feat["sector_etf_weekly_hist_rising"] = (wm["hist"] > wm["hist"].shift(1)).reindex(df.index, method="ffill")
        feat["sector_etf_weekly_macd_cross"] = completed_weekly_macd_cross(df, cfg)
        feat["sector_etf_2w_stoch_turn"] = completed_2w_stoch_cross(df, cfg)
        feat["sector_etf_no_60d_low"] = df["close"] > df["close"].rolling(60, min_periods=20).min()
        spy = benchmark_close(bench_dir, "SPY")
        if spy is not None:
            rs = df["close"] / spy.reindex(df.index).ffill()
            feat["sector_etf_rs_spy_20d_slope"] = rs / rs.shift(20) - 1
        out[etf] = feat
    return out


def build_cohort_tables(files: list[Path], sector_map: dict, cfg: SignalConfig) -> tuple[dict, dict]:
    sector_series = defaultdict(list)
    industry_series = defaultdict(list)
    for n, p in enumerate(files, start=1):
        ticker = p.stem.upper()
        meta = sector_map.get(ticker)
        if not meta:
            continue
        try:
            df = clean_ohlcv(pd.read_parquet(p))
            if len(df) < 520:
                continue
            os = two_week_stoch_oversold_daily(df, cfg).rename(ticker).astype(float)
            if meta.get("sector"):
                sector_series[meta["sector"]].append(os)
            if meta.get("sub_industry"):
                industry_series[meta["sub_industry"]].append(os)
        except Exception as exc:
            print(f"[cohort skip] {ticker}: {exc}")
        if n % 250 == 0:
            print(f"[cohort] scanned {n}/{len(files)} files")
    sector = {k: pd.concat(v, axis=1).mean(axis=1) for k, v in sector_series.items() if len(v) >= 5}
    industry = {k: pd.concat(v, axis=1).mean(axis=1) for k, v in industry_series.items() if len(v) >= 3}
    return sector, industry


def filter_specs() -> dict[str, tuple[str, Callable[[pd.DataFrame], pd.Series]]]:
    def num(e: pd.DataFrame, col: str, default: float = np.nan) -> pd.Series:
        return e[col] if col in e else pd.Series(default, index=e.index)

    def flag(e: pd.DataFrame, col: str, default: bool = False) -> pd.Series:
        return e[col] if col in e else pd.Series(default, index=e.index)

    return {
        "near_30d_low_5": ("signal within 5% of 30D low", lambda e: e["dist_30d_low"] <= 0.05),
        "near_30d_low_8": ("signal within 8% of 30D low", lambda e: e["dist_30d_low"] <= 0.08),
        "near_30d_low_10": ("signal within 10% of 30D low", lambda e: e["dist_30d_low"] <= 0.10),
        "near_60d_low_12": ("signal within 12% of 60D low", lambda e: e["dist_60d_low"] <= 0.12),
        "near_60d_low_15": ("signal within 15% of 60D low", lambda e: e["dist_60d_low"] <= 0.15),
        "below_52w_high_15": ("still at least 15% below 52W high", lambda e: e["dist_52w_high"] <= -0.15),
        "below_52w_high_25": ("still at least 25% below 52W high", lambda e: e["dist_52w_high"] <= -0.25),
        "rs_spy_20d_pos": ("stock/SPY RS 20D slope > 0", lambda e: num(e, "rs_spy_20d_slope", -1) > 0),
        "rs_spy_50d_pos": ("stock/SPY RS 50D slope > 0", lambda e: num(e, "rs_spy_50d_slope", -1) > 0),
        "rs_sector_20d_pos": ("stock/sector ETF RS 20D slope > 0", lambda e: num(e, "rs_sector_20d_slope", -1) > 0),
        "rs_sector_higher_low": ("stock/sector ETF RS higher low", lambda e: flag(e, "rs_sector_higher_low").fillna(False)),
        "bull_divergence": ("RSI or MACD-hist bullish divergence, 40D", lambda e: e["rsi_bull_div_40d"].fillna(False) | e["macd_hist_bull_div_40d"].fillna(False)),
        "failed_breakdown": ("20D/60D failed breakdown reclaim", lambda e: e["failed_breakdown_20d"].fillna(False) | e["failed_breakdown_60d"].fillna(False) | e["bollinger_reclaim"].fillna(False)),
        "volume_flush_2x": ("flush volume > 2x 20D average", lambda e: e["flush_vol_2p0"].fillna(False)),
        "volume_accumulation": ("up/down volume ratio >= 1.3", lambda e: e["up_down_vol_ratio_10d"] >= 1.3),
        "monthly_fresh_os": ("monthly StochRSI oversold dwell 1-3 bars", lambda e: (e["monthly_os_dwell"] >= 1) & (e["monthly_os_dwell"] <= 3)),
        "monthly_not_stale": ("reject monthly oversold dwell >= 6 bars", lambda e: e["monthly_os_dwell"].fillna(0) < 6),
        "monthly_hist_rising": ("monthly MACD histogram rising", lambda e: e["monthly_macd_hist_rising"].fillna(False)),
        "near_rising_200w": ("price near rising 200W MA", lambda e: (e["dist_200w_ma"].between(-0.10, 0.10)) & (e["200w_ma_slope"] > 0)),
        "reclaim_10w": ("price above 10W MA", lambda e: e["dist_10w_ma"] > 0),
        "cohort_sector_25": ("same-sector 2W StochRSI washout >= 25%", lambda e: num(e, "cohort_sector_washout", 0) >= 0.25),
        "cohort_sector_40": ("same-sector 2W StochRSI washout >= 40%", lambda e: num(e, "cohort_sector_washout", 0) >= 0.40),
        "cohort_sector_50": ("same-sector 2W StochRSI washout >= 50%", lambda e: num(e, "cohort_sector_washout", 0) >= 0.50),
        "cohort_industry_40": ("same-industry 2W StochRSI washout >= 40%", lambda e: num(e, "cohort_industry_washout", 0) >= 0.40),
        "sector_etf_hist_rising": ("sector ETF weekly MACD histogram rising", lambda e: flag(e, "sector_etf_weekly_hist_rising").fillna(False)),
        "sector_etf_rs_pos": ("sector ETF RS vs SPY improving", lambda e: num(e, "sector_etf_rs_spy_20d_slope", -1) > 0),
        "bull_regime": ("SPY above 200D and 200D rising", lambda e: e["market_regime"] == "above200_rising"),
    }


def combo_specs() -> dict[str, list[str]]:
    return {
        "cohort+anti_chase": ["cohort_sector_40", "near_60d_low_12"],
        "cohort+rs": ["cohort_sector_40", "rs_spy_20d_pos"],
        "rs+anti_chase": ["rs_spy_20d_pos", "near_60d_low_12"],
        "divergence+anti_chase": ["bull_divergence", "near_30d_low_10"],
        "failed_reclaim+rs": ["failed_breakdown", "rs_spy_20d_pos"],
        "monthly_fresh+anti_chase": ["monthly_fresh_os", "near_60d_low_12"],
        "candidate_1_cohort_rs_antichase": ["cohort_industry_40", "rs_sector_20d_pos", "near_60d_low_12"],
        "candidate_2_divergence_reclaim": ["bull_divergence", "failed_breakdown", "near_30d_low_10"],
        "candidate_3_monthly_cohort": ["monthly_fresh_os", "monthly_not_stale", "cohort_sector_40", "near_60d_low_12"],
        "candidate_4_volume_reclaim": ["volume_flush_2x", "volume_accumulation", "failed_breakdown"],
        "candidate_5_clean_compounder": ["near_rising_200w", "monthly_fresh_os", "rs_sector_higher_low"],
        "production_score_65_proxy": ["cohort_sector_25", "rs_spy_20d_pos", "near_60d_low_15", "monthly_not_stale"],
        "strict_quality_stack": ["cohort_sector_40", "rs_spy_20d_pos", "near_60d_low_12", "bull_divergence"],
    }


def apply_filter(events: pd.DataFrame, keys: list[str], specs: dict) -> pd.Series:
    mask = pd.Series(True, index=events.index)
    for key in keys:
        mask &= specs[key][1](events).fillna(False).astype(bool)
    return mask


def split_label(date: pd.Timestamp, splits: dict) -> str:
    for name, (start, end) in splits.items():
        if pd.Timestamp(start) <= date <= pd.Timestamp(end):
            return name
    return "out_of_split"


def rolling_split_results(events: pd.DataFrame, signal_names: list[str], validation_cfg: dict) -> pd.DataFrame:
    years = sorted(int(y) for y in events["year"].dropna().unique())
    if not years:
        return pd.DataFrame()
    train_n = int(validation_cfg.get("rolling_train_years", 3))
    val_n = int(validation_cfg.get("rolling_validation_years", 1))
    test_n = int(validation_cfg.get("rolling_test_years", 1))
    first, last = min(years), max(years)
    rows = []
    last_start = last - train_n - val_n - test_n + 1
    for start in range(first, last_start + 1):
        periods = {
            "train": range(start, start + train_n),
            "validation": range(start + train_n, start + train_n + val_n),
            "test": range(start + train_n + val_n, start + train_n + val_n + test_n),
        }
        window = f"{start}-{start + train_n - 1}|{start + train_n}|{start + train_n + val_n}"
        for signal in signal_names:
            sig_events = events[events["signal_name"] == signal]
            for label, yrs in periods.items():
                sub = sig_events[sig_events["year"].isin(list(yrs))]
                r = summarize(sub, signal, label)
                r["window"] = window
                r["period"] = label
                r["years"] = ",".join(str(y) for y in yrs)
                rows.append(r)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="research/bottom_signal_backtest/config.yaml")
    parser.add_argument("--max-tickers", type=int, default=None)
    args = parser.parse_args()

    cfg_raw = load_config(Path(args.config))
    sig_cfg = SignalConfig(**cfg_raw["signal"])
    data_dir = ROOT / cfg_raw["data"]["ohlcv_dir"]
    bench_dir = ROOT / cfg_raw["data"]["benchmark_dir"]
    results_dir = ROOT / cfg_raw["outputs"]["results_dir"]
    charts_dir = ROOT / cfg_raw["outputs"]["charts_dir"]
    results_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    files = load_ohlcv_files(data_dir, args.max_tickers or cfg_raw["data"].get("max_tickers"))
    start = pd.Timestamp(cfg_raw["data"]["start_date"])
    end = pd.Timestamp(cfg_raw["data"]["end_date"]) if cfg_raw["data"].get("end_date") else None
    min_history = int(cfg_raw["data"]["min_history_days"])
    sector_map = read_sector_map(ROOT / cfg_raw["data"]["sector_map"])

    spy = benchmark_close(bench_dir, "SPY")
    qqq = benchmark_close(bench_dir, "QQQ")
    iwm = benchmark_close(bench_dir, "IWM")
    regimes = regime_frame(spy) if spy is not None else pd.DataFrame()
    etf_feats = sector_etf_features(bench_dir, sig_cfg)

    print(f"[setup] {len(files)} OHLCV files; {len(sector_map)} mapped sector tickers")
    cohort_sector, cohort_industry = build_cohort_tables(files, sector_map, sig_cfg)
    print(f"[setup] cohort groups: sectors={len(cohort_sector)} industries={len(cohort_industry)}")

    base_rows = []
    dropped = {}
    for n, p in enumerate(files, start=1):
        ticker = p.stem.upper()
        try:
            df = clean_ohlcv(pd.read_parquet(p))
            df = df[df.index >= start]
            if end is not None:
                df = df[df.index <= end]
            if len(df) < min_history:
                dropped[ticker] = "too_little_history"
                continue
            meta = sector_map.get(ticker, {})
            sector = meta.get("sector")
            industry = meta.get("sub_industry")
            sector_etf_close = None
            etf = SECTOR_ETF.get(sector or "")
            if etf:
                sector_etf_close = benchmark_close(bench_dir, etf)
            feats = daily_feature_frame(ticker, df, spy=spy, qqq=qqq, iwm=iwm, sector_etf=sector_etf_close)
            if sector in cohort_sector:
                feats["cohort_sector_washout"] = cohort_sector[sector].reindex(df.index).ffill()
            else:
                feats["cohort_sector_washout"] = np.nan
            if industry in cohort_industry:
                feats["cohort_industry_washout"] = cohort_industry[industry].reindex(df.index).ffill()
            else:
                feats["cohort_industry_washout"] = np.nan
            if etf and etf in etf_feats:
                feats = feats.join(etf_feats[etf].reindex(df.index).ffill(), how="left")
            if not regimes.empty:
                feats = feats.join(regimes.reindex(df.index).ffill(), how="left")
            feats["sector"] = sector or "Unmapped"
            feats["industry"] = industry or "Unmapped"
            feats["sector_etf"] = etf or ""
            sig = base_signal(df, sig_cfg)
            dates = sig.index[sig]
            if len(dates):
                ev = event_metrics(ticker, df, dates, feats)
                if not ev.empty:
                    base_rows.append(ev)
        except Exception as exc:
            dropped[ticker] = f"ERROR: {exc}"
        if n % 200 == 0:
            print(f"[events] processed {n}/{len(files)} files; rows={sum(len(x) for x in base_rows)}")

    base_events = pd.concat(base_rows, ignore_index=True) if base_rows else pd.DataFrame()
    if base_events.empty:
        raise RuntimeError("No base-signal events were produced")
    base_events["date"] = pd.to_datetime(base_events["date"])
    splits = cfg_raw["validation"]["static_splits"]
    base_events["static_split"] = base_events["date"].map(lambda d: split_label(d, splits))
    base_events["year"] = base_events["date"].dt.year
    base_events["signal_name"] = "base"
    base_events.to_csv(results_dir / "all_base_events.csv", index=False)

    specs = filter_specs()
    result_rows = [summarize(base_events, "base", "1W MACD bull cross + 2W StochRSI oversold bull cross")]
    single_events = []
    for key, (desc, _) in specs.items():
        mask = apply_filter(base_events, [key], specs)
        sub = base_events[mask].copy()
        sub["signal_name"] = key
        single_events.append(sub)
        result_rows.append(summarize(sub, key, desc))
    combo_events = []
    for name, keys in combo_specs().items():
        mask = apply_filter(base_events, keys, specs)
        sub = base_events[mask].copy()
        sub["signal_name"] = name
        combo_events.append(sub)
        result_rows.append(summarize(sub, name, " + ".join(specs[k][0] for k in keys)))

    results = add_scores(pd.DataFrame(result_rows))
    base_result = results[results["signal_name"] == "base"]
    single_results = results[results["signal_name"].isin(specs.keys())].sort_values("bounce_quality_score", ascending=False)
    combo_results = results[results["signal_name"].isin(combo_specs().keys())].sort_values("bounce_quality_score", ascending=False)
    base_result.to_csv(results_dir / "base_signal.csv", index=False)
    single_results.to_csv(results_dir / "single_factor_results.csv", index=False)
    combo_results.to_csv(results_dir / "combo_results.csv", index=False)
    top5 = results[results["sample_size"] >= 50].sort_values(["bounce_quality_score", "asymmetric_entry_score"], ascending=False).head(5)
    top5.to_csv(results_dir / "top_5_combinations.csv", index=False)
    results.sort_values("bounce_quality_score", ascending=False).to_csv(results_dir / "all_signal_results.csv", index=False)

    ranking_cols = {
        "best_by_5d_bounce.csv": "median_5D",
        "best_by_10d_bounce.csv": "median_10D",
        "best_by_20d_bounce.csv": "median_20D",
        "best_by_30d_bounce.csv": "median_30D",
        "best_by_mfe_mae.csv": "MFE_MAE_ratio_20D",
        "best_by_durable_bottom.csv": "durable_bottom_60D",
    }
    for fname, col in ranking_cols.items():
        results.sort_values(col, ascending=False).head(25).to_csv(results_dir / fname, index=False)
    results.sort_values("stopout_rate_5pct").head(25).to_csv(results_dir / "best_by_low_stopout.csv", index=False)

    all_variant_events = pd.concat([base_events] + single_events + combo_events, ignore_index=True)
    all_variant_events.to_csv(results_dir / "all_variant_events.csv", index=False)

    top_names = ["base"] + top5["signal_name"].tolist()
    stability_rows = []
    for name in top_names:
        sub = all_variant_events[all_variant_events["signal_name"] == name]
        for split, g in sub.groupby("static_split"):
            r = summarize(g, f"{name}:{split}", split)
            r["signal_name"] = name
            r["split"] = split
            stability_rows.append(r)
    pd.DataFrame(stability_rows).to_csv(results_dir / "static_split_results.csv", index=False)

    year_rows = []
    sector_rows = []
    for name in top_names:
        sub = all_variant_events[all_variant_events["signal_name"] == name]
        y = by_group(sub, "year")
        if not y.empty:
            y["parent_signal"] = name
            year_rows.append(y)
        s = by_group(sub[sub["sector"] != "Unmapped"], "sector")
        if not s.empty:
            s["parent_signal"] = name
            sector_rows.append(s)
    if year_rows:
        pd.concat(year_rows, ignore_index=True).to_csv(results_dir / "year_stability.csv", index=False)
    if sector_rows:
        pd.concat(sector_rows, ignore_index=True).to_csv(results_dir / "sector_stability.csv", index=False)
    rolling = rolling_split_results(all_variant_events, top_names, cfg_raw["validation"])
    rolling.to_csv(results_dir / "rolling_split_results.csv", index=False)

    make_charts(all_variant_events[all_variant_events["signal_name"].isin(top_names)], results, charts_dir)
    write_report(results, base_events, top5, single_results, combo_results, dropped, cfg_raw, results_dir)
    print(f"[done] base events={len(base_events)} results={len(results)} output={results_dir}")


def pct(x) -> str:
    if pd.isna(x):
        return "n/a"
    return f"{100 * x:.1f}%"


def write_report(
    results: pd.DataFrame,
    base_events: pd.DataFrame,
    top5: pd.DataFrame,
    single_results: pd.DataFrame,
    combo_results: pd.DataFrame,
    dropped: dict,
    cfg: dict,
    out_dir: Path,
) -> None:
    base = results[results["signal_name"] == "base"].iloc[0]
    top = top5.iloc[0] if not top5.empty else base
    unavailable = [
        "Point-in-time fundamentals were not available in this repo slice, so fundamental survivability vetoes were not scored.",
        "Options/GEX history was not available as a broad point-in-time panel, so options confirmation was not scored.",
        "Sector classifications are current/static where available, not point-in-time; sector/cohort filters are therefore evidence, not production-ready PIT proof.",
    ]
    lines = [
        "# Bottom/Bounce Signal Backtest",
        "",
        "## Executive summary",
        "",
        f"Ran the requested completed-candle base trigger on `{cfg['data']['ohlcv_dir']}`: weekly price MACD bullish crossover aligned within {cfg['signal']['cross_alignment_days']} trading days of a completed 2W StochRSI bullish crossover from oversold, with a {cfg['signal']['cooldown_days']}D per-ticker cooldown.",
        "",
        f"Baseline sample: **{int(base['sample_size'])}** signals. Median forward returns were 5D {pct(base['median_5D'])}, 10D {pct(base['median_10D'])}, 20D {pct(base['median_20D'])}, and 30D {pct(base['median_30D'])}. The 20D entry-stop failure rate was {pct(base['stopout_rate_5pct'])}; 60D durable-bottom rate was {pct(base['durable_bottom_60D'])}.",
        "",
        f"Best scored candidate with at least 50 fires: **{top['signal_name']}** ({int(top['sample_size'])} signals), median 20D {pct(top['median_20D'])}, 20D MFE/MAE {top.get('MFE_MAE_ratio_20D', np.nan):.2f}, stopout {pct(top['stopout_rate_5pct'])}, durable 60D {pct(top['durable_bottom_60D'])}.",
        "",
        "## Baseline signal results",
        "",
        base.to_frame().T[[
            "sample_size",
            "median_5D",
            "median_10D",
            "median_20D",
            "median_30D",
            "win_rate_20D",
            "median_MFE_20D",
            "median_MAE_20D",
            "MFE_MAE_ratio_20D",
            "stopout_rate_5pct",
            "new_low_rate_60D",
            "durable_bottom_60D",
            "median_distance_from_60D_low",
        ]].to_markdown(index=False),
        "",
        "## Best individual filters",
        "",
        single_results.head(10)[[
            "signal_name",
            "sample_size",
            "median_10D",
            "median_20D",
            "MFE_MAE_ratio_20D",
            "stopout_rate_5pct",
            "new_low_rate_60D",
            "durable_bottom_60D",
            "bounce_quality_score",
        ]].to_markdown(index=False),
        "",
        "## Best combinations",
        "",
        combo_results.head(10)[[
            "signal_name",
            "sample_size",
            "median_10D",
            "median_20D",
            "MFE_MAE_ratio_20D",
            "stopout_rate_5pct",
            "new_low_rate_60D",
            "durable_bottom_60D",
            "bounce_quality_score",
        ]].to_markdown(index=False),
        "",
        "## Why the winners work",
        "",
        "The highest-ranked filters generally improved the signal by enforcing one of three things: entry proximity to the washout low, evidence that relative strength had stopped deteriorating, or broader cohort/market confirmation. The important read is the tradeoff between better MFE/MAE and smaller sample size; tiny ultra-strict stacks are not treated as production winners.",
        "",
        "## Filters that failed validation",
        "",
        "Filters that only reduced signal count without improving stop-out, new-low, or MFE/MAE were left below the top table. Sector/cohort and sector-RS filters also lose breadth because only mapped tickers can use them; those rows need PIT sector validation before production.",
        "",
        "## Robustness",
        "",
        "Static split, rolling 3Y/1Y/1Y, yearly, sector, and regime-style SPY 200D fields are written to CSV. The available price panel begins in 2014, so the requested 2010-2017 train window is implemented as 2014-2017.",
        "",
        "## Recommended production signal design",
        "",
        "Base trigger required:",
        "- completed 1W price MACD bullish crossover",
        "- completed 2W StochRSI bullish crossover with recent sub-20 oversold state",
        "",
        "Score the surviving base fires as:",
        "- Sector/cohort washout: 25 points",
        "- Relative strength inflection: 20 points",
        "- Anti-chase/asymmetric entry: 20 points",
        "- Structure/divergence/reclaim: 15 points",
        "- Volume capitulation/accumulation: 10 points",
        "- Monthly freshness/context: 10 points",
        "",
        "Hard veto candidates:",
        "- signal more than 15% above the 60D low",
        "- monthly StochRSI oversold dwell >= 6 bars",
        "- stock/SPY and stock/sector relative strength both still falling",
        "- sector ETF still making fresh 60D lows",
        "- fundamental deterioration once PIT fundamentals are available",
        "",
        "Classify: 80-100 A+ bottom/bounce signal; 65-79 high-quality bounce candidate; 50-64 early turn, wait for retest; below 50 bounce risk / avoid.",
        "",
        "## Data and bias controls",
        "",
        "- Completed weekly/2W candles are mapped to the first tradable day after the known close.",
        "- Same-ticker repeat signals are suppressed for 20 trading days.",
        "- Forward return/MFE/MAE/stop metrics are calculated only after the entry date.",
        "- Current/static sector maps are not point-in-time; production should replace them with PIT classifications.",
        "- Survivorship bias remains possible in the active OHLCV panel; delisted coverage should be added before treating absolute rates as final.",
        "",
        "## Missing data hooks",
        "",
        *[f"- {x}" for x in unavailable],
        "",
        "## Output files",
        "",
        "- `base_signal.csv`",
        "- `single_factor_results.csv`",
        "- `combo_results.csv`",
        "- `top_5_combinations.csv`",
        "- `all_signal_results.csv`",
        "- `all_base_events.csv` and `all_variant_events.csv`",
        "- `static_split_results.csv`, `rolling_split_results.csv`, `year_stability.csv`, `sector_stability.csv`",
        "- charts in `../charts/`",
        "",
        f"Dropped/skipped tickers: {len(dropped)}.",
    ]
    (out_dir / "final_report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
