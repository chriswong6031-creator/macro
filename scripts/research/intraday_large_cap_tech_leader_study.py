"""Phase-0, point-in-time study of intraday large-cap tech leadership.

The preregistration is:
    research/INTRADAY_LARGE_CAP_TECH_LEADER_PREREG.md

This script is deliberately a research runner, not a production ranker.  It reads
the Terminal's external 5-minute JSON archive plus Macro Dashboard's last-known
options summaries, builds cutoff-valid features, and writes descriptive/OOS
tables.  It does not write a live payload or enter any authority path.

Example:
    python -m scripts.research.intraday_large_cap_tech_leader_study \
      --intraday-dir /tmp/large_cap_leader_data/intraday \
      --options-dir data/options_flow \
      --signed-options-dir "/path/to/data/options_tape_signed" \
      --output-dir research/intraday_large_cap_tech_leader_phase0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
    "AVGO", "AMD", "MU", "QCOM", "AMAT", "LRCX", "KLAC", "MRVL",
    "ORCL", "CRM", "ADBE", "PLTR", "NOW", "PANW", "ANET", "IBM",
)
BENCHMARK = "QQQ"
SIGNED_UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD",
)

RTH_START = 9 * 60 + 30
FEATURE_END = 9 * 60 + 40
ENTRY_MINUTE = 9 * 60 + 45
RTH_END = 15 * 60 + 55
PM_START = 4 * 60
PM_END = 9 * 60 + 25
RESCUE_LAST_ENTRY = 14 * 60
EXPECTED_RTH_BARS = 78
# Massive's options day aggregate is published around 11:00 ET on the next
# business day.  At a 09:30/09:45 decision, the most recent provably available
# file is therefore normally two trading sessions old, not yesterday's file.
OPTIONS_AGG_DECISION_LAG = 2

PRICE_FEATURES: tuple[tuple[str, str], ...] = (
    ("prior_resid_1d", "Prior-session beta-adjusted RS"),
    ("prior_resid_5d", "Prior 5-session beta-adjusted RS"),
    ("prior_resid_20d", "Prior 20-session beta-adjusted RS"),
    ("rs_accel_5v20", "5-vs-20-session RS acceleration"),
    ("prior_close_location", "Prior-day close location"),
    ("pm_resid", "Premarket beta-adjusted return"),
    ("pm_rvol20", "Premarket volume / prior-20 median"),
    ("pm_range_pct", "Premarket range / prior close"),
    ("gap_resid", "Opening gap beta-adjusted versus QQQ"),
    ("first15_return", "First-15-minute raw return"),
    ("first15_resid", "First-15-minute beta-adjusted RS"),
    ("rvol15", "First-15-minute time-of-day RVOL"),
    ("opening_dollar_share", "Share of universe opening dollar volume"),
    ("vwap_distance15", "09:40 close distance above session VWAP"),
    ("opening_close_location", "Opening-range close location"),
    ("first15_efficiency", "First-15-minute trend efficiency"),
    ("range_expansion15", "First-15-minute range expansion"),
)

OPTIONS_FEATURES: tuple[tuple[str, str], ...] = (
    ("opt_premium_ratio20", "Last-available gross options premium / prior-20 median (normally T-2)"),
    ("opt_volume_ratio20", "Last-available option volume / prior-20 median (normally T-2)"),
    ("opt_call_volume_share", "Last-available call share of call-plus-put volume (normally T-2)"),
    ("opt_zerodte_share", "Last-available 0DTE volume share (normally T-2)"),
    ("opt_recurrence3", "Last-available three-session unusual-premium recurrence"),
)

SIGNED_FEATURES: tuple[tuple[str, str], ...] = (
    ("signed_gross_ratio20", "Prior-day quote-signed gross premium / prior-20 median"),
    ("signed_net_share", "Prior-day quote-signed net premium / gross premium"),
    ("signed_abs_net_share", "Prior-day absolute quote-signed net premium / gross"),
    ("signed_buy_share", "Prior-day quote-signed buy-premium share"),
    ("signed_delta_share", "Prior-day net delta proxy / total delta-proxy magnitude"),
    ("signed_quality", "Prior-day non-excluded trade share"),
)


@dataclass(frozen=True)
class StudyPaths:
    intraday_dir: Path
    options_dir: Path
    signed_options_dir: Path | None
    output_dir: Path


def _minute_of_day(ts: pd.Series) -> pd.Series:
    return ts.dt.hour * 60 + ts.dt.minute


def _safe_ratio(num: float, den: float) -> float:
    if den is None or not np.isfinite(den) or den == 0:
        return math.nan
    return float(num / den)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _git_head(repo_root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True,
        ).strip()
    except Exception:
        return None


def load_intraday(path: Path, ticker: str) -> pd.DataFrame:
    doc = json.loads(path.read_text())
    rows = doc.get("bars") or []
    if not rows:
        raise ValueError(f"{ticker}: no bars in {path}")
    df = pd.DataFrame(rows, columns=["epoch", "open", "high", "low", "close", "volume"])
    # Terminal contract: ET wall-clock reinterpreted as UTC epoch.  Keeping it
    # timezone-naive after UTC decoding makes hour/minute equal the ET display clock.
    df["ts"] = pd.to_datetime(df["epoch"], unit="s", utc=True).dt.tz_localize(None)
    df["date"] = df["ts"].dt.normalize()
    df["minute"] = _minute_of_day(df["ts"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset=["ts"], keep="last").sort_values("ts")
    df["ticker"] = ticker
    return df.reset_index(drop=True)


def common_full_sessions(bars: Mapping[str, pd.DataFrame]) -> list[pd.Timestamp]:
    full_sets: list[set[pd.Timestamp]] = []
    for ticker, df in bars.items():
        rth = df[(df["minute"] >= RTH_START) & (df["minute"] <= RTH_END)]
        counts = rth.groupby("date")["minute"].nunique()
        full = set(counts[counts == EXPECTED_RTH_BARS].index)
        if not full:
            raise ValueError(f"{ticker}: no complete 78-bar RTH sessions")
        full_sets.append(full)
    return sorted(set.intersection(*full_sets))


def benchmark_market_sessions(df: pd.DataFrame) -> list[pd.Timestamp]:
    """Uncompressed exchange calendar, including valid scheduled half-days."""
    rth = df[(df["minute"] >= RTH_START) & (df["minute"] <= RTH_END)]
    counts = rth.groupby("date")["minute"].nunique()
    return sorted(counts[counts >= 43].index)


def _crosses(values: np.ndarray) -> int:
    signs = np.sign(values)
    signs = signs[signs != 0]
    if len(signs) < 2:
        return 0
    return int(np.sum(signs[1:] != signs[:-1]))


def _rescue_fraction(after: pd.DataFrame) -> float:
    closes = after["close"].to_numpy(dtype=float)
    minutes = after["minute"].to_numpy(dtype=int)
    successes: list[bool] = []
    for i, (minute, entry_close) in enumerate(zip(minutes, closes)):
        if minute > RESCUE_LAST_ENTRY:
            continue
        later = closes[i + 1 :]
        if len(later) == 0:
            continue
        successes.append(bool(np.nanmax(later) >= entry_close * 1.0005))
    return float(np.mean(successes)) if successes else math.nan


def session_row(df: pd.DataFrame, date: pd.Timestamp, ticker: str) -> dict[str, object]:
    day = df[df["date"] == date].sort_values("minute")
    rth = day[(day["minute"] >= RTH_START) & (day["minute"] <= RTH_END)].copy()
    n_rth = int(rth["minute"].nunique())
    # Rolling features are built on QQQ's uncompressed exchange calendar.  A
    # handful of otherwise-healthy ticker sessions miss 1-3 arbitrary vendor
    # bars; retaining them prevents a five-session window from silently skipping
    # a real market day.  Primary outcome dates are still filtered separately to
    # exact 78-bar coverage for every ticker.
    valid_length = n_rth == 43 or 75 <= n_rth <= EXPECTED_RTH_BARS
    if not valid_length:
        raise ValueError(f"{ticker} {date.date()}: unusable regular session ({n_rth} bars)")
    required = {RTH_START, RTH_START + 5, FEATURE_END, ENTRY_MINUTE, int(rth.iloc[-1]["minute"])}
    if n_rth >= 75:
        required.add(RTH_END)
    if not required.issubset(set(rth["minute"])):
        raise ValueError(f"{ticker} {date.date()}: missing required cutoff bar")

    first = rth[rth["minute"].isin((RTH_START, RTH_START + 5, FEATURE_END))].copy()
    after = rth[rth["minute"] >= ENTRY_MINUTE].copy()
    entry = float(after.iloc[0]["open"])
    final = float(rth.iloc[-1]["close"])
    typical = (rth["high"] + rth["low"] + rth["close"]) / 3.0
    rth["cum_vwap"] = (typical * rth["volume"]).cumsum() / rth["volume"].cumsum()
    after = rth[rth["minute"] >= ENTRY_MINUTE].copy()

    first_typical = (first["high"] + first["low"] + first["close"]) / 3.0
    first_vwap = _safe_ratio(
        float((first_typical * first["volume"]).sum()), float(first["volume"].sum()),
    )
    first_open = float(first.iloc[0]["open"])
    first_close = float(first.iloc[-1]["close"])
    first_high = float(first["high"].max())
    first_low = float(first["low"].min())
    first_path = np.r_[first_open, first["close"].to_numpy(dtype=float)]
    first_path_len = float(np.abs(np.diff(first_path)).sum())
    first_eff = _safe_ratio(first_close - first_open, first_path_len)

    after_path = np.r_[entry, after["close"].to_numpy(dtype=float)]
    after_path_len = float(np.abs(np.diff(after_path)).sum())
    after_eff = _safe_ratio(final - entry, after_path_len)
    after_high = float(after["high"].max())
    after_low = float(after["low"].min())

    pm = day[(day["minute"] >= PM_START) & (day["minute"] <= PM_END)].copy()
    if pm.empty:
        pm_last = pm_volume = pm_dollar = pm_high = pm_low = math.nan
    else:
        pm_typical = (pm["high"] + pm["low"] + pm["close"]) / 3.0
        pm_last = float(pm.iloc[-1]["close"])
        pm_volume = float(pm["volume"].sum())
        pm_dollar = float((pm_typical * pm["volume"]).sum())
        pm_high = float(pm["high"].max())
        pm_low = float(pm["low"].min())

    close_minus_vwap = (after["close"] - after["cum_vwap"]).to_numpy(dtype=float)
    return {
        "date": date,
        "ticker": ticker,
        "rth_bar_count": n_rth,
        "rth_bar_coverage": n_rth / EXPECTED_RTH_BARS,
        "session_open": float(rth.iloc[0]["open"]),
        "session_high": float(rth["high"].max()),
        "session_low": float(rth["low"].min()),
        "session_close": final,
        "session_volume": float(rth["volume"].sum()),
        "entry_0945": entry,
        "first15_return": _safe_ratio(first_close, first_open) - 1.0,
        "first15_volume": float(first["volume"].sum()),
        "first15_dollar": float((first_typical * first["volume"]).sum()),
        "first15_range_pct": _safe_ratio(first_high - first_low, first_open),
        "first15_efficiency": first_eff,
        "first15_vwap": first_vwap,
        "vwap_distance15": _safe_ratio(first_close, first_vwap) - 1.0,
        "above_vwap15": bool(first_close > first_vwap),
        "opening_close_location": _safe_ratio(first_close - first_low, first_high - first_low),
        "after_return": _safe_ratio(final, entry) - 1.0,
        "mae": _safe_ratio(after_low, entry) - 1.0,
        "mfe": _safe_ratio(after_high, entry) - 1.0,
        "vwap_hold": float(np.mean(close_minus_vwap > 0)),
        "vwap_crosses": _crosses(close_minus_vwap),
        "trend_efficiency": after_eff,
        "close_location": _safe_ratio(final - after_low, after_high - after_low),
        "rescue_fraction": _rescue_fraction(after),
        "pm_last": pm_last,
        "pm_volume": pm_volume,
        "pm_dollar": pm_dollar,
        "pm_high": pm_high,
        "pm_low": pm_low,
    }


def build_price_panel(bars: Mapping[str, pd.DataFrame], dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for ticker in (*UNIVERSE, BENCHMARK):
        for date in dates:
            records.append(session_row(bars[ticker], date, ticker))
    daily = pd.DataFrame.from_records(records).sort_values(["ticker", "date"])

    def trailing(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()
        g["prev_close"] = g["session_close"].shift(1)
        g["ret_cc"] = g["session_close"].pct_change(fill_method=None)
        true_range = np.maximum.reduce([
            (g["session_high"] - g["session_low"]).to_numpy(dtype=float),
            (g["session_high"] - g["prev_close"]).abs().to_numpy(dtype=float),
            (g["session_low"] - g["prev_close"]).abs().to_numpy(dtype=float),
        ])
        g["true_range_pct"] = true_range / g["prev_close"].to_numpy(dtype=float)
        g["atr20_pct"] = g["true_range_pct"].rolling(20, min_periods=20).mean().shift(1)
        g["first15_vol_med20"] = g["first15_volume"].rolling(20, min_periods=20).median().shift(1)
        g["first15_range_med20"] = g["first15_range_pct"].rolling(20, min_periods=20).median().shift(1)
        g["pm_vol_med20"] = g["pm_volume"].rolling(20, min_periods=20).median().shift(1)
        close_loc = (g["session_close"] - g["session_low"]) / (g["session_high"] - g["session_low"])
        g["prior_close_location"] = close_loc.shift(1)
        g["rvol15"] = g["first15_volume"] / g["first15_vol_med20"]
        g["range_expansion15"] = g["first15_range_pct"] / g["first15_range_med20"]
        g["pm_rvol20"] = g["pm_volume"] / g["pm_vol_med20"]
        g["gap"] = g["session_open"] / g["prev_close"] - 1.0
        g["pm_return"] = g["pm_last"] / g["prev_close"] - 1.0
        g["pm_range_pct"] = (g["pm_high"] - g["pm_low"]) / g["prev_close"]
        return g

    daily = pd.concat(
        [trailing(g) for _, g in daily.groupby("ticker", sort=False)],
        ignore_index=True,
    )

    ret_wide = daily.pivot(index="date", columns="ticker", values="ret_cc").sort_index()
    close_wide = daily.pivot(index="date", columns="ticker", values="session_close").sort_index()
    beta_parts: list[pd.DataFrame] = []
    qret = ret_wide[BENCHMARK]
    qvar = qret.rolling(60, min_periods=40).var().shift(1)
    for ticker in UNIVERSE:
        cov = ret_wide[ticker].rolling(60, min_periods=40).cov(qret).shift(1)
        beta = (cov / qvar).clip(0.50, 2.50)
        beta_parts.append(pd.DataFrame({"date": beta.index, "ticker": ticker, "beta60": beta.values}))
    beta_df = pd.concat(beta_parts, ignore_index=True)
    daily = daily.merge(beta_df, on=["date", "ticker"], how="left")

    q_fields = daily[daily["ticker"] == BENCHMARK][[
        "date", "after_return", "first15_return", "gap", "pm_return",
    ]].rename(columns={
        "after_return": "qqq_after_return",
        "first15_return": "qqq_first15_return",
        "gap": "qqq_gap",
        "pm_return": "qqq_pm_return",
    })
    panel = daily[daily["ticker"].isin(UNIVERSE)].merge(q_fields, on="date", how="left")
    panel["after_resid"] = panel["after_return"] - panel["beta60"] * panel["qqq_after_return"]
    panel["first15_resid"] = panel["first15_return"] - panel["beta60"] * panel["qqq_first15_return"]
    panel["gap_resid"] = panel["gap"] - panel["beta60"] * panel["qqq_gap"]
    panel["pm_resid"] = panel["pm_return"] - panel["beta60"] * panel["qqq_pm_return"]
    panel["opening_dollar_share"] = panel["first15_dollar"] / panel.groupby("date")["first15_dollar"].transform("sum")

    q_close = close_wide[BENCHMARK]
    q_mom1 = qret.shift(1)
    q_mom5 = q_close.shift(1) / q_close.shift(6) - 1.0
    q_mom20 = q_close.shift(1) / q_close.shift(21) - 1.0
    momentum_parts: list[pd.DataFrame] = []
    for ticker in UNIVERSE:
        mom1 = ret_wide[ticker].shift(1)
        mom5 = close_wide[ticker].shift(1) / close_wide[ticker].shift(6) - 1.0
        mom20 = close_wide[ticker].shift(1) / close_wide[ticker].shift(21) - 1.0
        beta = beta_df[beta_df["ticker"] == ticker].set_index("date")["beta60"].reindex(ret_wide.index)
        rs1 = mom1 - beta * q_mom1
        rs5 = mom5 - beta * q_mom5
        rs20 = mom20 - beta * q_mom20
        momentum_parts.append(pd.DataFrame({
            "date": ret_wide.index,
            "ticker": ticker,
            "prior_resid_1d": rs1.values,
            "prior_resid_5d": rs5.values,
            "prior_resid_20d": rs20.values,
            "rs_accel_5v20": (rs5 - 0.25 * rs20).values,
        }))
    panel = panel.merge(pd.concat(momentum_parts, ignore_index=True), on=["date", "ticker"], how="left")
    panel["forgiving"] = (
        (panel["after_resid"] >= 0.005)
        & (panel["mae"] >= -0.50 * panel["atr20_pct"])
        & (panel["vwap_hold"] >= 0.70)
        & (panel["rescue_fraction"] >= 0.75)
    )
    return panel.sort_values(["date", "ticker"]).reset_index(drop=True)


def load_options_features(options_dir: Path, dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    date_index = pd.DatetimeIndex(dates)
    parts: list[pd.DataFrame] = []
    for ticker in UNIVERSE:
        path = options_dir / f"summary_{ticker}.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        raw = pd.read_parquet(path).copy()
        raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
        raw = raw[~raw.index.duplicated(keep="last")].reindex(date_index)
        premium = pd.to_numeric(raw["premium_mn"], errors="coerce")
        volume = pd.to_numeric(raw["volume"], errors="coerce")
        prem_ratio = premium / premium.shift(1).rolling(20, min_periods=20).median()
        vol_ratio = volume / volume.shift(1).rolling(20, min_periods=20).median()
        attn = prem_ratio.ge(1.25).where(prem_ratio.notna())
        recur = attn.astype(float).rolling(3, min_periods=3).sum()
        source_date = pd.Series(date_index, index=date_index).where(premium.notna())
        feature = pd.DataFrame({
            "date": date_index,
            "ticker": ticker,
            "opt_premium_ratio20": prem_ratio.shift(OPTIONS_AGG_DECISION_LAG).values,
            "opt_volume_ratio20": vol_ratio.shift(OPTIONS_AGG_DECISION_LAG).values,
            "opt_call_volume_share": (1.0 / (1.0 + pd.to_numeric(raw["pc_ratio"], errors="coerce"))).shift(OPTIONS_AGG_DECISION_LAG).values,
            "opt_zerodte_share": pd.to_numeric(raw["zerodte_share"], errors="coerce").shift(OPTIONS_AGG_DECISION_LAG).values,
            "opt_recurrence3": recur.shift(OPTIONS_AGG_DECISION_LAG).values,
            "opt_attention": attn.shift(OPTIONS_AGG_DECISION_LAG).values,
            "opt_source_date": source_date.shift(OPTIONS_AGG_DECISION_LAG).values,
        })
        parts.append(feature)
    out = pd.concat(parts, ignore_index=True)
    known = out.dropna(subset=["opt_source_date"])
    if not (known["opt_source_date"] < known["date"]).all():
        raise AssertionError("options look-ahead: source date is not strictly before decision date")
    return out


def load_signed_features(signed_dir: Path, dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    date_index = pd.DatetimeIndex(dates)
    parts: list[pd.DataFrame] = []
    for ticker in SIGNED_UNIVERSE:
        path = signed_dir / f"{ticker}.parquet"
        if not path.exists():
            raise FileNotFoundError(path)
        raw = pd.read_parquet(path).copy()
        raw["date"] = pd.to_datetime(raw["date"]).dt.tz_localize(None).dt.normalize()
        raw = raw.drop_duplicates("date", keep="last").set_index("date").reindex(date_index)
        gross = pd.to_numeric(raw["buy_premium"], errors="coerce") + pd.to_numeric(raw["sell_premium"], errors="coerce")
        delta_magnitude = (
            pd.to_numeric(raw["buy_delta_proxy"], errors="coerce").abs()
            + pd.to_numeric(raw["sell_delta_proxy"], errors="coerce").abs()
        )
        gross_ratio = gross / gross.shift(1).rolling(20, min_periods=20).median()
        net = pd.to_numeric(raw["net_premium"], errors="coerce")
        source_date = pd.Series(date_index, index=date_index).where(gross.notna())
        feature = pd.DataFrame({
            "date": date_index,
            "ticker": ticker,
            "signed_gross_ratio20": gross_ratio.shift(1).values,
            "signed_net_share": (net / gross).shift(1).values,
            "signed_abs_net_share": (net.abs() / gross).shift(1).values,
            "signed_buy_share": (pd.to_numeric(raw["buy_premium"], errors="coerce") / gross).shift(1).values,
            "signed_delta_share": (pd.to_numeric(raw["net_delta_proxy"], errors="coerce") / delta_magnitude).shift(1).values,
            "signed_quality": (1.0 - pd.to_numeric(raw["exclusion_rate"], errors="coerce")).shift(1).values,
            "signed_source_date": source_date.shift(1).values,
        })
        parts.append(feature)
    out = pd.concat(parts, ignore_index=True)
    known = out.dropna(subset=["signed_source_date"])
    if not (known["signed_source_date"] < known["date"]).all():
        raise AssertionError("signed-options look-ahead: source date is not before decision date")
    return out


def complete_dates(panel: pd.DataFrame, universe: Sequence[str], required: Sequence[str]) -> list[pd.Timestamp]:
    needed = len(universe)
    sub = panel[panel["ticker"].isin(universe)]
    good: list[pd.Timestamp] = []
    for date, g in sub.groupby("date"):
        if g["ticker"].nunique() != needed:
            continue
        if g[list(required)].notna().all(axis=None):
            good.append(pd.Timestamp(date))
    return sorted(good)


def add_labels(panel: pd.DataFrame, universe: Sequence[str]) -> pd.DataFrame:
    sub = panel[panel["ticker"].isin(universe)].copy()
    date_rows: list[dict[str, object]] = []
    for date, g in sub.groupby("date", sort=True):
        g = g.sort_values(["after_resid", "ticker"], ascending=[False, True])
        winner = g.iloc[0]
        second = float(g.iloc[1]["after_resid"])
        oracle = float(winner["after_resid"])
        raw_winner = g.sort_values(["after_return", "ticker"], ascending=[False, True]).iloc[0]["ticker"]
        date_rows.append({
            "date": date,
            "winner": winner["ticker"],
            "raw_winner": raw_winner,
            "oracle_resid": oracle,
            "runner_up_resid": second,
            "leader_margin": oracle - second,
            "clear_leader": bool(
                float(winner["after_return"]) >= 0.005
                and oracle >= 0.005
                and oracle - second >= 0.0035
            ),
        })
    out = sub.merge(pd.DataFrame(date_rows), on="date", how="left")
    out["tie_member"] = out["after_resid"] >= out["oracle_resid"] - 0.002
    return out.sort_values(["date", "ticker"]).reset_index(drop=True)


def split_dates(dates: Sequence[pd.Timestamp]) -> dict[str, list[pd.Timestamp]]:
    ordered = sorted(pd.Timestamp(d) for d in dates)
    cut = max(1, int(math.floor(0.60 * len(ordered))))
    return {"full": ordered, "development": ordered[:cut], "holdout": ordered[cut:]}


def week_block_ci(rows: pd.DataFrame, column: str, rng: np.random.Generator, n_boot: int) -> tuple[float, float]:
    clean = rows[["date", column]].dropna()
    if clean.empty:
        return math.nan, math.nan
    clean = clean.copy()
    clean["block"] = pd.to_datetime(clean["date"]).dt.to_period("W-FRI").astype(str)
    arrays = [g[column].to_numpy(dtype=float) for _, g in clean.groupby("block")]
    if len(arrays) < 2:
        v = float(clean[column].mean())
        return v, v
    draws = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        chosen = rng.integers(0, len(arrays), size=len(arrays))
        sample = np.concatenate([arrays[j] for j in chosen])
        draws[i] = float(np.nanmean(sample))
    return float(np.nanquantile(draws, 0.025)), float(np.nanquantile(draws, 0.975))


def bh_qvalues(pvalues: Sequence[float]) -> np.ndarray:
    p = np.asarray(pvalues, dtype=float)
    q = np.full_like(p, np.nan)
    valid = np.where(np.isfinite(p))[0]
    if len(valid) == 0:
        return q
    order = valid[np.argsort(p[valid])]
    ranked = p[order] * len(order) / np.arange(1, len(order) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    q[order] = np.clip(ranked, 0.0, 1.0)
    return q


def feature_atlas(
    labeled: pd.DataFrame,
    features: Sequence[tuple[str, str]],
    dates: Sequence[pd.Timestamp],
    cohort: str,
    segment: str,
    rng: np.random.Generator,
    n_perm: int,
    n_boot: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    date_set = set(dates)
    base = labeled[labeled["date"].isin(date_set)]
    for feature, label in features:
        per_date: list[dict[str, object]] = []
        rank_arrays: list[np.ndarray] = []
        for date, g in base.groupby("date", sort=True):
            if g[feature].isna().any() or len(g) < 2:
                continue
            ranks = g[feature].rank(method="average", pct=True)
            values = g[feature].to_numpy(dtype=float)
            order = np.lexsort((g["ticker"].to_numpy(dtype=str), -values))
            top_idx = int(order[0])
            top3_idx = order[: min(3, len(order))]
            winner_mask = g["ticker"].eq(g["winner"])
            winner_pos = int(np.flatnonzero(winner_mask.to_numpy())[0])
            residual_ranks = g["after_resid"].rank(method="average")
            corr = float(ranks.corr(residual_ranks))
            top_k = int(math.ceil(len(g) / 4.0))
            per_date.append({
                "date": date,
                "winner_pct": float(ranks.iloc[winner_pos]),
                "top_quartile": float(winner_pos in set(int(x) for x in order[:top_k])),
                "top_quartile_baseline": top_k / len(g),
                "top1_exact": float(g.iloc[top_idx]["ticker"] == g.iloc[top_idx]["winner"]),
                "top1_tie": float(bool(g.iloc[top_idx]["tie_member"])),
                "top3": float(winner_pos in set(int(x) for x in top3_idx)),
                "rank_corr": corr,
            })
            rank_arrays.append(ranks.to_numpy(dtype=float))
        metrics = pd.DataFrame(per_date)
        if metrics.empty:
            continue
        observed = float(metrics["winner_pct"].mean())
        null = np.empty(n_perm, dtype=float)
        for i in range(n_perm):
            null[i] = float(np.mean([arr[rng.integers(0, len(arr))] for arr in rank_arrays]))
        p = (1.0 + float(np.sum(null >= observed))) / (n_perm + 1.0)
        top1_lo, top1_hi = week_block_ci(metrics, "top1_exact", rng, n_boot)
        pct_lo, pct_hi = week_block_ci(metrics, "winner_pct", rng, n_boot)
        rows.append({
            "cohort": cohort,
            "segment": segment,
            "feature": feature,
            "label": label,
            "n_sessions": int(len(metrics)),
            "winner_mean_percentile": observed,
            "winner_percentile_ci_low": pct_lo,
            "winner_percentile_ci_high": pct_hi,
            "winner_top_quartile_rate": float(metrics["top_quartile"].mean()),
            "top_quartile_null_rate": float(metrics["top_quartile_baseline"].mean()),
            "top_quartile_enrichment": float(
                metrics["top_quartile"].mean() / metrics["top_quartile_baseline"].mean()
            ),
            "top1_exact": float(metrics["top1_exact"].mean()),
            "top1_exact_ci_low": top1_lo,
            "top1_exact_ci_high": top1_hi,
            "top1_economic_tie": float(metrics["top1_tie"].mean()),
            "top3_recall": float(metrics["top3"].mean()),
            "mean_cross_sectional_rank_corr": float(metrics["rank_corr"].mean()),
            "permutation_p_one_sided": p,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["bh_q"] = bh_qvalues(out["permutation_p_one_sided"].to_numpy(dtype=float))
    return out


def feature_selector(labeled: pd.DataFrame, dates: Sequence[pd.Timestamp], feature: str) -> tuple[dict, dict]:
    selected: dict[pd.Timestamp, str | None] = {}
    top3: dict[pd.Timestamp, list[str]] = {}
    for date, g in labeled[labeled["date"].isin(dates)].groupby("date", sort=True):
        valid = g.dropna(subset=[feature]).sort_values([feature, "ticker"], ascending=[False, True])
        selected[pd.Timestamp(date)] = str(valid.iloc[0]["ticker"]) if not valid.empty else None
        top3[pd.Timestamp(date)] = valid.head(3)["ticker"].astype(str).tolist()
    return selected, top3


def constant_selector(dates: Sequence[pd.Timestamp], ticker: str) -> tuple[dict, dict]:
    return ({pd.Timestamp(d): ticker for d in dates}, {pd.Timestamp(d): [ticker] for d in dates})


def modal_winner(labeled: pd.DataFrame, development_dates: Sequence[pd.Timestamp]) -> str:
    """Freeze the most frequent development winner as a non-uniform baseline."""
    sub = labeled[labeled["date"].isin(development_dates)]
    winners = sub[sub["ticker"] == sub["winner"]]
    counts = winners["ticker"].value_counts()
    if counts.empty:
        raise ValueError("cannot derive modal-winner baseline from an empty development set")
    # Stable alphabetical tie break keeps the preregistered seed irrelevant here.
    max_count = int(counts.max())
    return str(sorted(counts[counts == max_count].index.astype(str))[0])


def pv_selector(
    labeled: pd.DataFrame,
    dates: Sequence[pd.Timestamp],
    sort_feature: str,
    require_options_attention: bool = False,
) -> tuple[dict, dict]:
    selected: dict[pd.Timestamp, str | None] = {}
    top3: dict[pd.Timestamp, list[str]] = {}
    for date, g0 in labeled[labeled["date"].isin(dates)].groupby("date", sort=True):
        g = g0.copy()
        rs_top3 = set(g.sort_values(["first15_resid", "ticker"], ascending=[False, True]).head(3)["ticker"])
        g["pv_k"] = (
            g["ticker"].isin(rs_top3).astype(int)
            + (g["rvol15"] >= 1.20).astype(int)
            + ((g["above_vwap15"]) & (g["opening_close_location"] >= 0.70)).astype(int)
            + (g["first15_efficiency"] >= 0.35).astype(int)
        )
        q = g[g["pv_k"] >= 3]
        if require_options_attention:
            q = q[q["opt_attention"].eq(True)]
        q = q.sort_values([sort_feature, "ticker"], ascending=[False, True])
        selected[pd.Timestamp(date)] = str(q.iloc[0]["ticker"]) if not q.empty else None
        top3[pd.Timestamp(date)] = q.head(3)["ticker"].astype(str).tolist()
    return selected, top3


def evaluate_selector(
    labeled: pd.DataFrame,
    dates: Sequence[pd.Timestamp],
    selected: Mapping[pd.Timestamp, str | None],
    top3: Mapping[pd.Timestamp, Sequence[str]],
    cohort: str,
    segment: str,
    selector: str,
    rng: np.random.Generator,
    n_boot: int,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    date_set = set(pd.Timestamp(d) for d in dates)
    by_date = {pd.Timestamp(d): g for d, g in labeled[labeled["date"].isin(date_set)].groupby("date")}
    for date in sorted(date_set):
        g = by_date.get(date)
        if g is None or g.empty:
            continue
        ticker = selected.get(date)
        if not ticker or ticker not in set(g["ticker"]):
            records.append({"date": date, "called": 0.0, "clear": float(g.iloc[0]["clear_leader"])})
            continue
        row = g[g["ticker"] == ticker].iloc[0]
        records.append({
            "date": date,
            "called": 1.0,
            "clear": float(row["clear_leader"]),
            "exact": float(ticker == row["winner"]),
            "tie": float(bool(row["tie_member"])),
            "top3": float(row["winner"] in set(top3.get(date, []))),
            "selected_resid": float(row["after_resid"]),
            "selected_raw_net10bp": float(row["after_return"] - 0.001),
            "positive_resid": float(row["after_resid"] > 0),
            "regret": float(row["oracle_resid"] - row["after_resid"]),
            "mae": float(row["mae"]),
            "mfe": float(row["mfe"]),
            "vwap_hold": float(row["vwap_hold"]),
            "trend_efficiency": float(row["trend_efficiency"]),
            "rescue_fraction": float(row["rescue_fraction"]),
            "forgiving": float(bool(row["forgiving"])),
        })
    frame = pd.DataFrame(records)
    for col in (
        "exact", "tie", "top3", "selected_resid", "selected_raw_net10bp",
        "positive_resid", "regret", "mae", "mfe", "vwap_hold",
        "trend_efficiency", "rescue_fraction", "forgiving",
    ):
        if col not in frame:
            frame[col] = math.nan
    called = frame[frame["called"] == 1.0]
    clear_called = called[called["clear"] == 1.0]
    exact_lo, exact_hi = week_block_ci(called, "exact", rng, n_boot)
    tie_lo, tie_hi = week_block_ci(called, "tie", rng, n_boot)
    resid_lo, resid_hi = week_block_ci(called, "selected_resid", rng, n_boot)

    def mean(col: str, df: pd.DataFrame = called) -> float:
        return float(df[col].mean()) if not df.empty and col in df else math.nan

    return {
        "cohort": cohort,
        "segment": segment,
        "selector": selector,
        "n_sessions": int(len(frame)),
        "n_called": int(len(called)),
        "coverage": float(len(called) / len(frame)) if len(frame) else math.nan,
        "exact_hit_called": mean("exact"),
        "exact_hit_all": float(called["exact"].sum() / len(frame)) if len(frame) else math.nan,
        "exact_ci_low": exact_lo,
        "exact_ci_high": exact_hi,
        "economic_tie_hit_called": mean("tie"),
        "tie_ci_low": tie_lo,
        "tie_ci_high": tie_hi,
        "top3_recall_called": mean("top3"),
        "clear_sessions_called": int(len(clear_called)),
        "clear_exact_hit_called": mean("exact", clear_called),
        "mean_selected_resid": mean("selected_resid"),
        "selected_resid_ci_low": resid_lo,
        "selected_resid_ci_high": resid_hi,
        "median_selected_resid": float(called["selected_resid"].median()) if not called.empty else math.nan,
        "mean_selected_raw_net10bp": mean("selected_raw_net10bp"),
        "positive_resid_rate": mean("positive_resid"),
        "mean_oracle_regret": mean("regret"),
        "mean_mae": mean("mae"),
        "mean_mfe": mean("mfe"),
        "mean_vwap_hold": mean("vwap_hold"),
        "mean_trend_efficiency": mean("trend_efficiency"),
        "mean_rescue_fraction": mean("rescue_fraction"),
        "forgiving_rate": mean("forgiving"),
    }


def selector_suite(
    labeled: pd.DataFrame,
    dates: Sequence[pd.Timestamp],
    cohort: str,
    segment: str,
    rng: np.random.Generator,
    n_boot: int,
    include_options: bool,
    development_modal_ticker: str,
) -> pd.DataFrame:
    specs: list[tuple[str, tuple[dict, dict]]] = [
        ("ALWAYS_NVDA", constant_selector(dates, "NVDA")),
        ("DEV_MODAL_WINNER", constant_selector(dates, development_modal_ticker)),
        ("PRIOR_DAY_WINNER", feature_selector(labeled, dates, "prior_resid_1d")),
        ("PRIOR_RS5", feature_selector(labeled, dates, "prior_resid_5d")),
        ("PREMARKET_RS", feature_selector(labeled, dates, "pm_resid")),
        ("GAP_RS", feature_selector(labeled, dates, "gap_resid")),
        ("FIRST15_RAW", feature_selector(labeled, dates, "first15_return")),
        ("FIRST15_BETA_RS", feature_selector(labeled, dates, "first15_resid")),
        ("FIRST15_RVOL", feature_selector(labeled, dates, "rvol15")),
        ("OPENING_DOLLAR_SHARE", feature_selector(labeled, dates, "opening_dollar_share")),
        ("PV_CONFIRM_RS", pv_selector(labeled, dates, "first15_resid")),
        ("PV_CONFIRM_RVOL", pv_selector(labeled, dates, "rvol15")),
    ]
    if include_options:
        specs.extend([
            ("OPT_PREMIUM_ANOM", feature_selector(labeled, dates, "opt_premium_ratio20")),
            ("PV_CONFIRM_RS_OPT_ATTN", pv_selector(
                labeled, dates, "first15_resid", require_options_attention=True,
            )),
        ])
    rows = [
        evaluate_selector(labeled, dates, sel, top3, cohort, segment, name, rng, n_boot)
        for name, (sel, top3) in specs
    ]
    return pd.DataFrame(rows)


def winner_census(labeled: pd.DataFrame, dates: Sequence[pd.Timestamp], cohort: str) -> pd.DataFrame:
    sub = labeled[labeled["date"].isin(dates)]
    winners = sub[sub["ticker"] == sub["winner"]]
    rows: list[dict[str, object]] = []
    total = winners["date"].nunique()
    for ticker in sorted(sub["ticker"].unique()):
        w = winners[winners["ticker"] == ticker]
        rows.append({
            "cohort": cohort,
            "ticker": ticker,
            "wins": int(len(w)),
            "win_share": float(len(w) / total) if total else math.nan,
            "clear_wins": int(w["clear_leader"].sum()),
            "forgiving_wins": int(w["forgiving"].sum()),
            "mean_winner_resid": float(w["after_resid"].mean()) if len(w) else math.nan,
            "mean_winner_mae": float(w["mae"].mean()) if len(w) else math.nan,
            "mean_winner_vwap_hold": float(w["vwap_hold"].mean()) if len(w) else math.nan,
            "mean_winner_rescue": float(w["rescue_fraction"].mean()) if len(w) else math.nan,
        })
    return pd.DataFrame(rows)


def robustness_tables(
    panel: pd.DataFrame,
    dates: Sequence[pd.Timestamp],
    rng: np.random.Generator,
    n_boot: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    leave_rows: list[dict[str, object]] = []
    for excluded in (None, *UNIVERSE):
        universe = [t for t in UNIVERSE if t != excluded]
        labeled = add_labels(panel[panel["date"].isin(dates)], universe)
        sel, top3 = feature_selector(labeled, dates, "first15_resid")
        metrics = evaluate_selector(
            labeled, dates, sel, top3, "price", "full", "FIRST15_BETA_RS",
            rng, n_boot,
        )
        leave_rows.append({
            "excluded": excluded or "NONE",
            "n_tickers": len(universe),
            "exact_hit_called": metrics["exact_hit_called"],
            "economic_tie_hit_called": metrics["economic_tie_hit_called"],
            "mean_selected_resid": metrics["mean_selected_resid"],
            "mean_oracle_regret": metrics["mean_oracle_regret"],
        })

    blocks: list[dict[str, object]] = []
    for block_no, block_dates_arr in enumerate(np.array_split(np.array(sorted(dates)), 4), start=1):
        block_dates = [pd.Timestamp(d) for d in block_dates_arr]
        labeled = add_labels(panel[panel["date"].isin(block_dates)], UNIVERSE)
        for name, (sel, top3) in (
            ("FIRST15_BETA_RS", feature_selector(labeled, block_dates, "first15_resid")),
            ("PV_CONFIRM_RS", pv_selector(labeled, block_dates, "first15_resid")),
        ):
            metrics = evaluate_selector(
                labeled, block_dates, sel, top3, "price", f"block_{block_no}", name,
                rng, n_boot,
            )
            blocks.append({
                "block": block_no,
                "start": min(block_dates).date().isoformat(),
                "end": max(block_dates).date().isoformat(),
                "selector": name,
                "n_sessions": metrics["n_sessions"],
                "coverage": metrics["coverage"],
                "exact_hit_called": metrics["exact_hit_called"],
                "economic_tie_hit_called": metrics["economic_tie_hit_called"],
                "mean_selected_resid": metrics["mean_selected_resid"],
                "mean_oracle_regret": metrics["mean_oracle_regret"],
            })
    return pd.DataFrame(leave_rows), pd.DataFrame(blocks)


def event_table(labeled: pd.DataFrame, dates: Sequence[pd.Timestamp]) -> pd.DataFrame:
    sub = labeled[labeled["date"].isin(dates)]
    pv_pick, _ = pv_selector(sub, dates, "first15_resid")
    rs_pick, _ = feature_selector(sub, dates, "first15_resid")
    winners = sub[sub["ticker"] == sub["winner"]].copy()
    winners["first15_rs_pick"] = winners["date"].map(rs_pick)
    winners["pv_confirm_pick"] = winners["date"].map(pv_pick)
    cols = [
        "date", "winner", "raw_winner", "after_return", "after_resid",
        "runner_up_resid", "leader_margin", "clear_leader", "forgiving",
        "mae", "mfe", "vwap_hold", "trend_efficiency", "rescue_fraction",
        "first15_resid", "rvol15", "first15_rs_pick", "pv_confirm_pick",
    ]
    return winners[cols].sort_values("date")


def exploratory_full_day_atlas(
    panel: pd.DataFrame,
    dates: Sequence[pd.Timestamp],
) -> pd.DataFrame:
    """Descriptive current-leader table added after the primary run.

    The primary preregistered label asks which stock wins *after* 09:45.  The
    user's visual idea of "today's leader" is usually prior-close-to-close and
    therefore includes the already-observed overnight gap and opening move.  This
    table answers that different classification question, with no p-values or
    promotion claim.  Its selected post-09:45 returns show whether identifying the
    current leader also left anything tradable.
    """
    sub = panel[panel["date"].isin(dates)].copy()
    sub["full_day_return"] = sub["session_close"] / sub["prev_close"] - 1.0
    rows: list[dict[str, object]] = []
    for segment, segment_dates in split_dates(dates).items():
        seg = sub[sub["date"].isin(segment_dates)]
        for feature, label in PRICE_FEATURES:
            metrics: list[dict[str, float]] = []
            for _, g in seg.groupby("date", sort=True):
                if g[feature].isna().any():
                    continue
                winner_idx = g["full_day_return"].idxmax()
                selected_idx = g[feature].idxmax()
                top3 = set(g.nlargest(3, feature)["ticker"])
                ranks = g[feature].rank(method="average", pct=True)
                selected = g.loc[selected_idx]
                metrics.append({
                    "winner_pct": float(ranks.loc[winner_idx]),
                    "top1": float(selected_idx == winner_idx),
                    "top3": float(g.loc[winner_idx, "ticker"] in top3),
                    "selected_full_day_return": float(selected["full_day_return"]),
                    "selected_after_return": float(selected["after_return"]),
                    "selected_after_resid": float(selected["after_resid"]),
                })
            frame = pd.DataFrame(metrics)
            if frame.empty:
                continue
            rows.append({
                "post_registered_exploratory": True,
                "segment": segment,
                "feature": feature,
                "label": label,
                "n_sessions": int(len(frame)),
                "full_day_winner_mean_percentile": float(frame["winner_pct"].mean()),
                "full_day_top1": float(frame["top1"].mean()),
                "full_day_top3": float(frame["top3"].mean()),
                "mean_selected_full_day_return": float(frame["selected_full_day_return"].mean()),
                "mean_selected_after_return": float(frame["selected_after_return"].mean()),
                "mean_selected_after_resid": float(frame["selected_after_resid"].mean()),
            })
    return pd.DataFrame(rows)


def run(paths: StudyPaths, seed: int, n_perm: int, n_boot: int) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    tickers = (*UNIVERSE, BENCHMARK)
    bars: dict[str, pd.DataFrame] = {}
    input_hashes: dict[str, str] = {}
    for ticker in tickers:
        path = paths.intraday_dir / f"{ticker}.5m.json"
        if not path.exists():
            raise FileNotFoundError(path)
        bars[ticker] = load_intraday(path, ticker)
        input_hashes[f"intraday/{path.name}"] = _sha256(path)
    calendar_sessions = benchmark_market_sessions(bars[BENCHMARK])
    full_sessions = common_full_sessions(bars)
    panel = build_price_panel(bars, calendar_sessions)

    price_required = [
        "beta60", "atr20_pct", "prior_resid_1d", "prior_resid_5d", "prior_resid_20d",
        "first15_resid", "rvol15", "after_resid",
    ]
    outcome_panel = panel[panel["date"].isin(full_sessions)]
    price_dates = complete_dates(outcome_panel, UNIVERSE, price_required)
    if len(price_dates) < 100:
        raise RuntimeError(f"only {len(price_dates)} complete price sessions")
    price = add_labels(panel[panel["date"].isin(price_dates)], UNIVERSE)

    options = load_options_features(paths.options_dir, calendar_sessions)
    for ticker in UNIVERSE:
        path = paths.options_dir / f"summary_{ticker}.parquet"
        input_hashes[f"options/{path.name}"] = _sha256(path)
    panel_opt = panel.merge(options, on=["date", "ticker"], how="left")
    option_dates = complete_dates(
        panel_opt,
        UNIVERSE,
        [*price_required, "opt_premium_ratio20", "opt_volume_ratio20", "opt_call_volume_share", "opt_zerodte_share"],
    )
    options_labeled = add_labels(panel_opt[panel_opt["date"].isin(option_dates)], UNIVERSE)

    signed_labeled: pd.DataFrame | None = None
    signed_dates: list[pd.Timestamp] = []
    if paths.signed_options_dir is not None:
        signed = load_signed_features(paths.signed_options_dir, calendar_sessions)
        for ticker in SIGNED_UNIVERSE:
            path = paths.signed_options_dir / f"{ticker}.parquet"
            input_hashes[f"signed_options/{path.name}"] = _sha256(path)
        panel_signed = panel[panel["ticker"].isin(SIGNED_UNIVERSE)].merge(
            signed, on=["date", "ticker"], how="left",
        )
        signed_dates = complete_dates(
            panel_signed,
            SIGNED_UNIVERSE,
            [*price_required, *(f for f, _ in SIGNED_FEATURES)],
        )
        signed_labeled = add_labels(panel_signed[panel_signed["date"].isin(signed_dates)], SIGNED_UNIVERSE)

    atlas_parts: list[pd.DataFrame] = []
    selector_parts: list[pd.DataFrame] = []
    price_splits = split_dates(price_dates)
    price_modal_ticker = modal_winner(price, price_splits["development"])
    for segment, dates in price_splits.items():
        atlas_parts.append(feature_atlas(
            price, PRICE_FEATURES, dates, "price", segment, rng, n_perm, n_boot,
        ))
        selector_parts.append(selector_suite(
            price, dates, "price", segment, rng, n_boot, include_options=False,
            development_modal_ticker=price_modal_ticker,
        ))
    option_splits = split_dates(option_dates)
    option_modal_ticker = modal_winner(options_labeled, option_splits["development"])
    for segment, dates in option_splits.items():
        atlas_parts.append(feature_atlas(
            options_labeled, OPTIONS_FEATURES, dates, "options_magnitude", segment,
            rng, n_perm, n_boot,
        ))
        selector_parts.append(selector_suite(
            options_labeled, dates, "options_magnitude", segment, rng, n_boot,
            include_options=True, development_modal_ticker=option_modal_ticker,
        ))
    if signed_labeled is not None and signed_dates:
        for segment, dates in split_dates(signed_dates).items():
            atlas_parts.append(feature_atlas(
                signed_labeled, SIGNED_FEATURES, dates, "signed_sensitivity", segment,
                rng, n_perm, n_boot,
            ))

    atlas = pd.concat(atlas_parts, ignore_index=True)
    selectors = pd.concat(selector_parts, ignore_index=True)
    census = pd.concat([
        winner_census(price, price_dates, "price"),
        winner_census(options_labeled, option_dates, "options_magnitude"),
    ], ignore_index=True)
    leave_one_out, blocks = robustness_tables(panel, price_dates, rng, n_boot)
    events = event_table(price, price_dates)
    full_day_exploratory = exploratory_full_day_atlas(panel, price_dates)

    paths.output_dir.mkdir(parents=True, exist_ok=True)
    atlas.to_csv(paths.output_dir / "feature_atlas.csv", index=False, float_format="%.8f")
    selectors.to_csv(paths.output_dir / "selector_metrics.csv", index=False, float_format="%.8f")
    census.to_csv(paths.output_dir / "winner_census.csv", index=False, float_format="%.8f")
    leave_one_out.to_csv(paths.output_dir / "leave_one_out.csv", index=False, float_format="%.8f")
    blocks.to_csv(paths.output_dir / "chronological_blocks.csv", index=False, float_format="%.8f")
    events.to_csv(paths.output_dir / "session_events.csv", index=False, float_format="%.8f")
    full_day_exploratory.to_csv(
        paths.output_dir / "exploratory_full_day_atlas.csv", index=False, float_format="%.8f",
    )

    clear_count = int(price[price["ticker"] == price["winner"]]["clear_leader"].sum())
    forgiving_count = int(panel[
        panel["date"].isin(price_dates) & panel["ticker"].isin(UNIVERSE)
    ]["forgiving"].sum())
    repo_root = Path(__file__).resolve().parents[2]
    manifest: dict[str, object] = {
        "schema": "intraday_large_cap_tech_leader_phase0/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "may_rank": False,
        "may_alert": False,
        "may_size": False,
        "preregistration": "research/INTRADAY_LARGE_CAP_TECH_LEADER_PREREG.md",
        "preregistration_git_head_at_run": _git_head(repo_root),
        "runner": {
            "path": str(Path(__file__).resolve().relative_to(repo_root)),
            "sha256": _sha256(Path(__file__).resolve()),
        },
        "runtime_versions": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "seed": seed,
        "n_permutations": n_perm,
        "n_week_block_bootstraps": n_boot,
        "options_aggregate_decision_lag_sessions": OPTIONS_AGG_DECISION_LAG,
        "options_aggregate_availability_note": (
            "Massive day aggregates publish around 11:00 ET next business day; "
            "09:30/09:45 features use the last provably available file, normally T-2"
        ),
        "development_modal_winner_baselines": {
            "price": price_modal_ticker,
            "options_magnitude": option_modal_ticker,
        },
        "universe": list(UNIVERSE),
        "benchmark": BENCHMARK,
        "signed_sensitivity_universe": list(SIGNED_UNIVERSE),
        "coverage": {
            "raw_common_full_sessions": len(full_sessions),
            "exchange_calendar_sessions": len(calendar_sessions),
            "exchange_calendar_first": min(calendar_sessions).date().isoformat(),
            "exchange_calendar_last": max(calendar_sessions).date().isoformat(),
            "raw_first": min(full_sessions).date().isoformat(),
            "raw_last": max(full_sessions).date().isoformat(),
            "price_complete_sessions": len(price_dates),
            "price_first": min(price_dates).date().isoformat(),
            "price_last": max(price_dates).date().isoformat(),
            "price_holdout_sessions": len(split_dates(price_dates)["holdout"]),
            "options_complete_sessions": len(option_dates),
            "options_first": min(option_dates).date().isoformat() if option_dates else None,
            "options_last": max(option_dates).date().isoformat() if option_dates else None,
            "options_holdout_sessions": len(split_dates(option_dates)["holdout"]) if option_dates else 0,
            "signed_complete_sessions": len(signed_dates),
            "signed_first": min(signed_dates).date().isoformat() if signed_dates else None,
            "signed_last": max(signed_dates).date().isoformat() if signed_dates else None,
            "clear_leader_sessions": clear_count,
            "forgiving_ticker_sessions": forgiving_count,
        },
        "input_sha256": input_hashes,
        "artifacts": [
            "feature_atlas.csv", "selector_metrics.csv", "winner_census.csv",
            "leave_one_out.csv", "chronological_blocks.csv", "session_events.csv",
            "exploratory_full_day_atlas.csv",
        ],
        "limitations": [
            "fixed current universe; survivorship and composition bias remain",
            "historical catalyst and earnings timestamps are not joined",
            "options magnitude is last-available (normally T-2) and non-directional",
            "signed-flow cohort failed its direction-quality gate and is sensitivity only",
            "research result does not authorize a live rank or alert",
            "exploratory full-day table was added after the primary run and receives no inferential claim",
        ],
    }
    (paths.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intraday-dir", type=Path, required=True)
    parser.add_argument("--options-dir", type=Path, default=Path("data/options_flow"))
    parser.add_argument("--signed-options-dir", type=Path)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("research/intraday_large_cap_tech_leader_phase0"),
    )
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--permutations", type=int, default=2000)
    parser.add_argument("--bootstraps", type=int, default=2000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = run(
        StudyPaths(
            intraday_dir=args.intraday_dir,
            options_dir=args.options_dir,
            signed_options_dir=args.signed_options_dir,
            output_dir=args.output_dir,
        ),
        seed=args.seed,
        n_perm=args.permutations,
        n_boot=args.bootstraps,
    )
    print(json.dumps(manifest["coverage"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
