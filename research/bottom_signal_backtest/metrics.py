from __future__ import annotations

import numpy as np
import pandas as pd


HORIZONS = [5, 10, 20, 30]


def event_metrics(ticker: str, df: pd.DataFrame, signal_dates: pd.DatetimeIndex, features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    idx = df.index
    for date in signal_dates:
        if date not in idx:
            continue
        i = idx.get_loc(date)
        if not isinstance(i, (int, np.integer)):
            continue
        if i + max(HORIZONS) >= len(idx):
            continue
        entry = float(df["close"].iloc[i])
        if not np.isfinite(entry) or entry <= 0:
            continue
        feat = features.reindex([date]).iloc[0] if date in features.index else pd.Series(dtype=float)
        signal_low = feat.get("signal_low_proxy", np.nan)
        if not np.isfinite(signal_low):
            signal_low = float(df["low"].iloc[max(0, i - 10):i + 1].min())
        atr14 = feat.get("atr14", np.nan)
        row = {
            "ticker": ticker,
            "date": date,
            "entry": entry,
            "signal_low": signal_low,
            "atr14": atr14,
        }
        for h in HORIZONS:
            win = df.iloc[i + 1 : i + h + 1]
            if len(win) < h:
                continue
            row[f"ret_{h}d"] = float(win["close"].iloc[-1] / entry - 1)
            row[f"mfe_{h}d"] = float(win["high"].max() / entry - 1)
            row[f"mae_{h}d"] = float(win["low"].min() / entry - 1)
            row[f"stop_entry_5_before_{h}d"] = bool((win["low"] <= entry * 0.95).any())
            row[f"stop_entry_8_before_{h}d"] = bool((win["low"] <= entry * 0.92).any())
            row[f"stop_signal_low_before_{h}d"] = bool((win["low"] <= signal_low).any())
            row[f"stop_signal_low_3_before_{h}d"] = bool((win["low"] <= signal_low * 0.97).any())
            row[f"stop_signal_low_5_before_{h}d"] = bool((win["low"] <= signal_low * 0.95).any())
            if np.isfinite(atr14):
                row[f"stop_atr1_before_{h}d"] = bool((win["low"] <= signal_low - atr14).any())
                row[f"stop_atr1p5_before_{h}d"] = bool((win["low"] <= signal_low - 1.5 * atr14).any())
        for h in [20, 30, 60]:
            win = df.iloc[i + 1 : min(len(df), i + h + 1)]
            row[f"new_low_{h}d"] = bool(len(win) and (win["low"] < signal_low).any())
        win30 = df.iloc[i + 1 : min(len(df), i + 31)]
        win60 = df.iloc[i + 1 : min(len(df), i + 61)]
        row["durable_bottom_30d"] = bool(len(win30) >= 30 and not (win30["low"] < signal_low * 0.97).any())
        row["durable_bottom_60d"] = bool(len(win60) >= 60 and not (win60["low"] < signal_low * 0.95).any())
        fail_low = df.iloc[i + 1 : min(len(df), i + 61)]["low"] < signal_low
        row["time_to_new_low"] = int(np.argmax(fail_low.to_numpy()) + 1) if fail_low.any() else np.nan
        for col, val in feat.items():
            row[col] = val
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(events: pd.DataFrame, signal_name: str, filters: str = "") -> dict:
    row = {"signal_name": signal_name, "filters": filters, "sample_size": int(len(events))}
    if events.empty:
        return row
    for h in HORIZONS:
        r = events[f"ret_{h}d"].dropna()
        row[f"median_{h}D"] = r.median()
        row[f"mean_{h}D"] = r.mean()
        row[f"win_rate_{h}D"] = (r > 0).mean()
        for p in [10, 25, 50, 75, 90]:
            row[f"ret_{h}D_p{p}"] = r.quantile(p / 100) if len(r) else np.nan
        row[f"median_MFE_{h}D"] = events[f"mfe_{h}d"].median()
        row[f"median_MAE_{h}D"] = events[f"mae_{h}d"].median()
    mfe = events["mfe_20d"].median()
    mae = events["mae_20d"].median()
    row["median_MFE_20D"] = mfe
    row["median_MAE_20D"] = mae
    row["MFE_MAE_ratio_20D"] = mfe / abs(mae) if pd.notna(mae) and mae != 0 else np.nan
    row["stopout_rate_5pct"] = events["stop_entry_5_before_20d"].mean()
    row["stopout_rate_8pct"] = events["stop_entry_8_before_20d"].mean()
    for h in HORIZONS:
        row[f"stopout_rate_5pct_{h}D"] = events[f"stop_entry_5_before_{h}d"].mean()
    row["new_low_rate_30D"] = events["new_low_30d"].mean()
    row["new_low_rate_60D"] = events["new_low_60d"].mean()
    row["durable_bottom_30D"] = events["durable_bottom_30d"].mean()
    row["durable_bottom_60D"] = events["durable_bottom_60d"].mean()
    row["median_distance_from_60D_low"] = events["dist_60d_low"].median()
    row["median_distance_from_30D_low"] = events["dist_30d_low"].median()
    row["extension_penalty"] = events[["dist_20d_low", "dist_30d_low", "dist_60d_low", "dist_50d_ma"]].clip(lower=0).mean(axis=1).median()
    for x in [0.05, 0.08, 0.10, 0.15, 0.20]:
        row[f"prob_MFE20_ge_{int(x*100)}pct"] = (events["mfe_20d"] >= x).mean()
    for x in [-0.03, -0.05, -0.08, -0.10]:
        row[f"prob_MAE20_le_{int(abs(x)*100)}pct"] = (events["mae_20d"] <= x).mean()
    row["median_time_to_new_low_if_failed"] = events["time_to_new_low"].dropna().median()
    return row


def add_scores(results: pd.DataFrame) -> pd.DataFrame:
    out = results.copy()
    if out.empty:
        return out
    specs = {
        "median_5D": 0.15,
        "median_10D": 0.20,
        "median_20D": 0.20,
        "median_30D": 0.10,
        "MFE_MAE_ratio_20D": 0.20,
        "durable_bottom_60D": 0.15,
        "stopout_rate_5pct": -0.20,
        "new_low_rate_60D": -0.20,
        "extension_penalty": -0.15,
    }
    asym = {
        "MFE_MAE_ratio_20D": 0.30,
        "durable_bottom_60D": 0.20,
        "median_MAE_20D": 0.20,
        "median_distance_from_60D_low": -0.15,
        "median_20D": 0.15,
        "extension_penalty": -0.25,
    }
    out["bounce_quality_score"] = _weighted_z(out, specs)
    out["asymmetric_entry_score"] = _weighted_z(out, asym)
    return out


def _weighted_z(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    score = pd.Series(0.0, index=df.index)
    for col, weight in weights.items():
        if col not in df:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        sd = s.std(ddof=0)
        z = (s - s.mean()) / sd if pd.notna(sd) and sd else 0
        score = score + weight * z
    return 50 + 15 * score


def by_group(events: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    if group_col not in events or events.empty:
        return pd.DataFrame()
    for val, sub in events.groupby(group_col, dropna=True):
        rows.append(summarize(sub, str(val), group_col))
    return pd.DataFrame(rows)
