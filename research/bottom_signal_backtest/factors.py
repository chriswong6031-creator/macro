from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd


SECTOR_ETF = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Financials": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Discretionary": "XLY",
    "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}


@dataclass
class SignalConfig:
    weekly_macd_fast: int = 12
    weekly_macd_slow: int = 26
    weekly_macd_signal: int = 9
    stoch_rsi_rsi: int = 14
    stoch_rsi_window: int = 14
    stoch_rsi_k: int = 3
    stoch_rsi_d: int = 3
    oversold_line: float = 20.0
    cross_alignment_days: int = 10
    cooldown_days: int = 20


def read_sector_map(path: str | Path) -> dict[str, dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text())
    return {k.upper(): v for k, v in raw.items() if isinstance(v, dict)}


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]
    cols = {c.lower(): c for c in out.columns}
    rename = {cols[c]: c for c in ["open", "high", "low", "close", "volume"] if c in cols}
    out = out.rename(columns=rename)
    if "high" not in out:
        out["high"] = out["close"]
    if "low" not in out:
        out["low"] = out["close"]
    if "volume" not in out:
        out["volume"] = np.nan
    return out[["close", "high", "low", "volume"]].dropna(subset=["close"])


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = close.ewm(span=fast, adjust=False, min_periods=slow).mean() - close.ewm(
        span=slow, adjust=False, min_periods=slow
    ).mean()
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def stoch_rsi(
    close: pd.Series,
    rsi_n: int = 14,
    stoch_n: int = 14,
    k_n: int = 3,
    d_n: int = 3,
) -> pd.DataFrame:
    rr = rsi(close, rsi_n)
    lo = rr.rolling(stoch_n, min_periods=stoch_n).min()
    hi = rr.rolling(stoch_n, min_periods=stoch_n).max()
    raw = 100 * (rr - lo) / (hi - lo).replace(0, np.nan)
    k = raw.rolling(k_n, min_periods=k_n).mean()
    d = k.rolling(d_n, min_periods=d_n).mean()
    return pd.DataFrame({"rsi": rr, "k": k, "d": d})


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat(
        [(df["high"] - df["low"]).abs(), (df["high"] - prev).abs(), (df["low"] - prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def tf_bars(df: pd.DataFrame, rule: str) -> tuple[pd.DataFrame, pd.Series]:
    groups = []
    known = []
    for _, g in df.resample(rule, label="right", closed="right"):
        if g.empty:
            continue
        groups.append(
            {
                "close": g["close"].iloc[-1],
                "high": g["high"].max(),
                "low": g["low"].min(),
                "volume": g["volume"].sum(min_count=1),
            }
        )
        known.append(g.index[-1])
    bars = pd.DataFrame(groups, index=pd.DatetimeIndex(known))
    return bars, pd.Series(known, index=bars.index)


def events_after_known(known_dates: Iterable[pd.Timestamp], daily_index: pd.DatetimeIndex) -> pd.Series:
    out = pd.Series(False, index=daily_index)
    for known in pd.to_datetime(list(known_dates)):
        j = daily_index.searchsorted(known, side="right")
        if j < len(daily_index):
            out.iloc[j] = True
    return out


def apply_cooldown(events: pd.Series, cooldown_days: int) -> pd.Series:
    out = pd.Series(False, index=events.index)
    last = -10**9
    for i, flag in enumerate(events.fillna(False).to_numpy(dtype=bool)):
        if flag and i - last > cooldown_days:
            out.iloc[i] = True
            last = i
    return out


def completed_weekly_macd_cross(df: pd.DataFrame, cfg: SignalConfig) -> pd.Series:
    weekly, _ = tf_bars(df, "W-FRI")
    m = macd(weekly["close"], cfg.weekly_macd_fast, cfg.weekly_macd_slow, cfg.weekly_macd_signal)
    cross = (m["macd"] > m["signal"]) & (m["macd"].shift(1) <= m["signal"].shift(1))
    return events_after_known(cross.index[cross.fillna(False)], df.index)


def completed_2w_stoch_cross(df: pd.DataFrame, cfg: SignalConfig) -> pd.Series:
    two_w, _ = tf_bars(df, "2W-FRI")
    s = stoch_rsi(two_w["close"], cfg.stoch_rsi_rsi, cfg.stoch_rsi_window, cfg.stoch_rsi_k, cfg.stoch_rsi_d)
    recent_os = (s[["k", "d"]].min(axis=1).rolling(3, min_periods=1).min() < cfg.oversold_line)
    cross = (s["k"] > s["d"]) & (s["k"].shift(1) <= s["d"].shift(1)) & recent_os.shift(1).fillna(False)
    return events_after_known(cross.index[cross.fillna(False)], df.index)


def two_week_stoch_oversold_daily(df: pd.DataFrame, cfg: SignalConfig) -> pd.Series:
    two_w, _ = tf_bars(df, "2W-FRI")
    s = stoch_rsi(two_w["close"], cfg.stoch_rsi_rsi, cfg.stoch_rsi_window, cfg.stoch_rsi_k, cfg.stoch_rsi_d)
    os = (s[["k", "d"]].min(axis=1) < cfg.oversold_line)
    daily = os.reindex(df.index, method="ffill").fillna(False)
    return daily.astype(bool)


def base_signal(df: pd.DataFrame, cfg: SignalConfig) -> pd.Series:
    w = completed_weekly_macd_cross(df, cfg)
    tw = completed_2w_stoch_cross(df, cfg)
    align = cfg.cross_alignment_days
    w_recent = w.rolling(align + 1, min_periods=1).max().astype(bool)
    tw_recent = tw.rolling(align + 1, min_periods=1).max().astype(bool)
    raw = (w & tw_recent) | (tw & w_recent)
    return apply_cooldown(raw, cfg.cooldown_days)


def daily_feature_frame(
    ticker: str,
    df: pd.DataFrame,
    spy: Optional[pd.Series] = None,
    qqq: Optional[pd.Series] = None,
    iwm: Optional[pd.Series] = None,
    sector_etf: Optional[pd.Series] = None,
) -> pd.DataFrame:
    c = df["close"]
    f = pd.DataFrame(index=df.index)
    for n in [20, 30, 60, 120, 252]:
        f[f"dist_{n}d_low"] = c / c.rolling(n, min_periods=max(10, n // 3)).min() - 1
    f["dist_52w_high"] = c / c.rolling(252, min_periods=126).max() - 1
    for n in [50, 100, 200]:
        ma = c.rolling(n, min_periods=max(20, n // 2)).mean()
        f[f"dist_{n}d_ma"] = c / ma - 1
        f[f"{n}d_ma_slope"] = ma / ma.shift(20) - 1
    weekly, _ = tf_bars(df, "W-FRI")
    for n, label in [(10, "10w"), (20, "20w"), (200, "200w")]:
        ma = weekly["close"].rolling(n, min_periods=max(5, n // 2)).mean()
        daily_ma = ma.reindex(df.index, method="ffill")
        f[f"dist_{label}_ma"] = c / daily_ma - 1
        f[f"{label}_ma_slope"] = (ma / ma.shift(8) - 1).reindex(df.index, method="ffill")
    f["atr14"] = atr(df, 14)
    f["signal_low_proxy"] = df["low"].rolling(10, min_periods=3).min().shift(1)
    f["rsi14"] = rsi(c, 14)
    vol20 = df["volume"].rolling(20, min_periods=10).mean()
    f["vol_ratio_20d"] = df["volume"] / vol20
    f["flush_vol_1p5"] = (df["volume"].rolling(10, min_periods=5).max() / vol20) > 1.5
    f["flush_vol_2p0"] = (df["volume"].rolling(10, min_periods=5).max() / vol20) > 2.0
    f["flush_vol_2p5"] = (df["volume"].rolling(10, min_periods=5).max() / vol20) > 2.5
    up_vol = df["volume"].where(c.pct_change() > 0).rolling(10, min_periods=5).sum()
    down_vol = df["volume"].where(c.pct_change() < 0).rolling(10, min_periods=5).sum()
    f["up_down_vol_ratio_10d"] = up_vol / down_vol.replace(0, np.nan)
    prior20 = df["low"].rolling(20, min_periods=10).min().shift(5)
    under = df["low"].rolling(5, min_periods=1).min() < prior20
    f["failed_breakdown_20d"] = under & (c > prior20)
    prior60 = df["low"].rolling(60, min_periods=20).min().shift(10)
    under60 = df["low"].rolling(10, min_periods=1).min() < prior60
    f["failed_breakdown_60d"] = under60 & (c > prior60)
    mid = c.rolling(20, min_periods=20).mean()
    sd = c.rolling(20, min_periods=20).std()
    lower = mid - 2 * sd
    f["bollinger_reclaim"] = (df["low"].rolling(5, min_periods=1).min() < lower) & (c > lower)
    f["rsi_bull_div_40d"] = bullish_divergence(c, f["rsi14"], 40)
    hist = macd(c)["hist"]
    f["macd_hist_bull_div_40d"] = bullish_divergence(c, hist, 40)
    m_bars, _ = tf_bars(df, "ME")
    ms = stoch_rsi(m_bars["close"])
    dwell = monthly_oversold_dwell(ms["d"] < 20)
    f["monthly_stoch_d"] = ms["d"].reindex(df.index, method="ffill")
    f["monthly_os_dwell"] = dwell.reindex(df.index, method="ffill")
    mm = macd(m_bars["close"])
    f["monthly_macd_hist_rising"] = (mm["hist"] > mm["hist"].shift(1)).reindex(df.index, method="ffill")
    for label, bench in [("spy", spy), ("qqq", qqq), ("iwm", iwm), ("sector", sector_etf)]:
        if bench is None:
            continue
        b = bench.reindex(df.index).ffill()
        rs = c / b
        f[f"rs_{label}_20d_slope"] = rs / rs.shift(20) - 1
        f[f"rs_{label}_50d_slope"] = rs / rs.shift(50) - 1
        f[f"rs_{label}_above_20d"] = rs > rs.rolling(20, min_periods=10).mean()
        f[f"rs_{label}_above_50d"] = rs > rs.rolling(50, min_periods=20).mean()
        f[f"rs_{label}_higher_low"] = rs.rolling(20, min_periods=10).min() > rs.rolling(20, min_periods=10).min().shift(20)
    return f


def bullish_divergence(price: pd.Series, osc: pd.Series, window: int = 40) -> pd.Series:
    half = max(10, window // 2)
    p_recent = price.rolling(half, min_periods=half).min()
    p_prior = price.shift(half).rolling(half, min_periods=half).min()
    o_recent = osc.where(price == p_recent).rolling(half, min_periods=1).min()
    o_prior = osc.shift(half).where(price.shift(half) == p_prior).rolling(half, min_periods=1).min()
    return ((p_recent <= p_prior * 1.03) & (o_recent > o_prior)).fillna(False)


def monthly_oversold_dwell(is_os: pd.Series) -> pd.Series:
    vals = []
    count = 0
    for flag in is_os.fillna(False):
        count = count + 1 if flag else 0
        vals.append(count)
    return pd.Series(vals, index=is_os.index)


def benchmark_close(path: str | Path, ticker: str) -> Optional[pd.Series]:
    p = Path(path) / f"{ticker}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    col = "close" if "close" in df.columns else "Close"
    return df[col].sort_index()


def regime_frame(spy: pd.Series) -> pd.DataFrame:
    s = spy.sort_index()
    ma = s.rolling(200, min_periods=100).mean()
    rising = ma > ma.shift(20)
    above = s > ma
    out = pd.DataFrame(index=s.index)
    out["spy_above_200d"] = above
    out["spy_200d_rising"] = rising
    out["market_regime"] = np.select(
        [above & rising, above & ~rising, ~above & rising, ~above & ~rising],
        ["above200_rising", "above200_falling", "below200_rising", "below200_falling"],
        default="unknown",
    )
    return out
