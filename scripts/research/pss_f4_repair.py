#!/usr/bin/env python3
"""PSS-F4R — causal terminality repair for the retained F4 descriptor.

This is an exploratory engineering study, not a retroactive re-registration of
the killed standalone F4 timer.  All available history has already been viewed,
so the output is shadow-research evidence and cannot promote authority.  The
purpose is to build and falsify a causal replacement architecture:

    incumbent arms -> terminality state -> observable rejection -> action

The fixed candidate family separates four information channels:

* price: intraday rejection of a fresh 20-day low;
* terminality: a soft, causal C32-style decline-deceleration state;
* volume: a recent range/volume climax or a down-volume-share reversal;
* context: stock/sector relative-strength repair plus market/sector repair.

F4 downside asymmetry is retained only as an ablation/context condition.  The
study explicitly compares the consensus construction with and without F4 so a
zero-value F4 leg is visible rather than hidden.

No candidate backdates persistence.  ``first_actions`` stamps the first
confirmation day observable at or after an incumbent signal, within 15 trading
days.  Metrics are the existing §7 entry-timing ruler from pss_f4_semivar.

Run:
    python3 scripts/research/pss_f4_repair.py

Outputs:
    reports/pss_f4_repair.md
    data/research/pss_f4_repair_events.parquet
    data/research/pss_f4_repair_panel.parquet
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research import pss_f4_semivar as f4  # noqa: E402


PANEL_PQ = ROOT / "data/research/ptt_w1_panel.parquet"
OHLCV_DIR = ROOT / "data/baskets/ohlcv"
SECTOR_MAP_PQ = ROOT / "data/breadth/ticker_sectors.parquet"
YAHOO_DIR = ROOT / "data/yahoo"
OUT_EVENTS = ROOT / "data/research/pss_f4_repair_events.parquet"
OUT_PANEL = ROOT / "data/research/pss_f4_repair_panel.parquet"
OUT_REPORT = ROOT / "reports/pss_f4_repair.md"

OOS_START = pd.Timestamp("2020-07-01")
DEV_END = pd.Timestamp("2022-12-31")
VAL_START = pd.Timestamp("2023-01-01")
VAL_END = pd.Timestamp("2024-12-31")
FWD_START = pd.Timestamp("2025-01-01")
ACTION_HORIZON = 15
BOOT_SEED = 20260801
DEFAULT_BOOTSTRAPS = 400

SECTOR_ETF = {
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}

CANDIDATES = (
    "r0_price_rejection",
    "r1_terminal_rejection",
    "r2_volume_terminal",
    "r3_context_terminal",
    "r4_consensus",
    "r4_consensus_f4",
    "r5_survival3",
    "r6_terminal_survival3",
    "r7_terminal_survival5",
    "r8_survival_consensus",
    "r8_survival_consensus_f4",
    "r9_structure_break",
    "r10_terminal_structure_break",
    "r11_structure_consensus",
    "r11_structure_consensus_f4",
)

LABELS = {
    "inc": "incumbent",
    "r0_price_rejection": "R0 price rejection",
    "r1_terminal_rejection": "R1 + soft terminality",
    "r2_volume_terminal": "R2 + volume exhaustion",
    "r3_context_terminal": "R3 + relative/systemic repair",
    "r4_consensus": "R4 orthogonal 2-of-3 consensus",
    "r4_consensus_f4": "R4 + F4-stress arm",
    "r5_survival3": "R5 3-day rejection survival",
    "r6_terminal_survival3": "R6 + terminality, 3-day survival",
    "r7_terminal_survival5": "R7 + terminality, 5-day survival",
    "r8_survival_consensus": "R8 survival + orthogonal confirmation",
    "r8_survival_consensus_f4": "R8 + F4-stress arm",
    "r9_structure_break": "R9 rejection → 5-day structure break",
    "r10_terminal_structure_break": "R10 + terminality structure break",
    "r11_structure_consensus": "R11 structure break + orthogonal confirmation",
    "r11_structure_consensus_f4": "R11 + F4-stress arm",
}

MODEL_FEATURES = (
    "f4_q",
    "f4_d3",
    "rvd_d3",
    "low60_dist",
    "roc20",
    "close_location",
    "lower_wick",
    "volume_ratio",
    "range_ratio",
    "down_share3",
    "rs5",
    "market_roc5",
    "sector_roc5",
    "terminal_recent",
    "price_rejection",
    "volume_exhaustion",
    "relative_turn",
    "systemic_repair",
)


@dataclass(frozen=True)
class Context:
    market: pd.Series
    sectors: dict[str, pd.Series]
    ticker_sector: dict[str, str]


def lag(a: np.ndarray, k: int = 1) -> np.ndarray:
    out = np.full(len(a), np.nan)
    if k < len(a):
        out[k:] = a[:-k]
    return out


def rolling_any(a: np.ndarray, n: int) -> np.ndarray:
    return (
        pd.Series(np.asarray(a, dtype=float))
        .rolling(n, min_periods=1)
        .max()
        .fillna(0.0)
        .to_numpy()
        > 0
    )


def rolling_slope(a: np.ndarray, n: int) -> np.ndarray:
    """Trailing OLS slope, using only observations through the current bar."""
    x = np.arange(n, dtype=float)
    x -= x.mean()
    denom = float((x * x).sum())
    return (
        pd.Series(a, dtype=float)
        .rolling(n, min_periods=n)
        .apply(lambda y: float(np.dot(x, y - y.mean()) / denom), raw=True)
        .to_numpy()
    )


def load_yahoo_close(symbol: str) -> pd.Series:
    path = YAHOO_DIR / f"{symbol}.parquet"
    d = pd.read_parquet(path)
    col = "close" if "close" in d.columns else "close_price"
    s = d[col].dropna().astype(float)
    s.index = pd.DatetimeIndex(s.index).tz_localize(None)
    return s[~s.index.duplicated(keep="last")].sort_index()


def load_context() -> Context:
    mapping = pd.read_parquet(SECTOR_MAP_PQ)
    ticker_sector = dict(
        zip(mapping["ticker"].astype(str), mapping["sector"].astype(str), strict=False)
    )
    sectors: dict[str, pd.Series] = {}
    for sector, etf in SECTOR_ETF.items():
        path = YAHOO_DIR / f"{etf}.parquet"
        if path.exists():
            sectors[sector] = load_yahoo_close(etf)
    return Context(
        market=load_yahoo_close("SPY"),
        sectors=sectors,
        ticker_sector=ticker_sector,
    )


def align_context(source: pd.Series, idx: pd.DatetimeIndex) -> np.ndarray:
    """Past-only alignment; no backward fill from a future market observation."""
    return source.reindex(idx, method="ffill").to_numpy(dtype=float)


def repair_state(x: np.ndarray) -> np.ndarray:
    s = pd.Series(x, dtype=float)
    ema5 = s.ewm(span=5, adjust=False, min_periods=5).mean().to_numpy()
    roc5 = s.pct_change(5).to_numpy()
    roc5_floor = (
        pd.Series(roc5).shift(1).rolling(20, min_periods=10).min().to_numpy()
    )
    return np.isfinite(ema5) & (x > ema5) & np.isfinite(roc5_floor) & (
        roc5 > roc5_floor
    )


def feature_arrays(
    ohlcv: pd.DataFrame,
    market_close: np.ndarray,
    sector_close: np.ndarray,
) -> dict[str, np.ndarray]:
    """Build the fixed causal feature blocks for one name."""
    op = ohlcv["open"].to_numpy(dtype=float)
    hi = ohlcv["high"].to_numpy(dtype=float)
    lo = ohlcv["low"].to_numpy(dtype=float)
    c = ohlcv["close"].to_numpy(dtype=float)
    vol = ohlcv["volume"].to_numpy(dtype=float)
    prior_low20 = (
        pd.Series(lo).shift(1).rolling(20, min_periods=20).min().to_numpy()
    )
    prior_high1 = lag(hi)
    fresh_low = np.isfinite(prior_low20) & (lo <= prior_low20)
    bar_range = hi - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        close_location = np.where(bar_range > 0, (c - lo) / bar_range, np.nan)
        lower_wick = np.where(
            bar_range > 0, (np.minimum(op, c) - lo) / bar_range, np.nan
        )
    bullish_rejection = (
        fresh_low
        & (c > op)
        & (close_location >= 0.65)
        & (lower_wick >= 0.20)
    )
    next_day_reclaim = (
        (lag(fresh_low.astype(float)) == 1.0)
        & np.isfinite(prior_high1)
        & (c > prior_high1)
        & (c > op)
    )
    price_rejection = bullish_rejection | next_day_reclaim
    rejection_recent10 = rolling_any(price_rejection, 10)
    prior_high5 = (
        pd.Series(hi).shift(1).rolling(5, min_periods=5).max().to_numpy()
    )
    structure_break = (
        rejection_recent10 & np.isfinite(prior_high5) & (c > prior_high5)
    )
    rejection3 = lag(price_rejection.astype(float), 3) == 1.0
    rejection5 = lag(price_rejection.astype(float), 5) == 1.0
    post_low3 = pd.Series(lo).rolling(3, min_periods=3).min().to_numpy()
    post_low5 = pd.Series(lo).rolling(5, min_periods=5).min().to_numpy()
    survival3 = (
        rejection3
        & (post_low3 >= lag(lo, 3))
        & (c > lag(c, 3))
    )
    survival5 = (
        rejection5
        & (post_low5 >= lag(lo, 5))
        & (c > lag(c, 5))
    )

    close_s = pd.Series(c)
    low60 = close_s.rolling(60, min_periods=60).min().to_numpy()
    roc20 = close_s.pct_change(20).to_numpy()
    roc20_floor = (
        pd.Series(roc20).shift(1).rolling(20, min_periods=20).min().to_numpy()
    )
    low10 = close_s.rolling(10, min_periods=10).min().to_numpy()
    low_slope = rolling_slope(low10, 20)
    soft_terminal = (
        np.isfinite(low60)
        & (c <= 1.05 * low60)
        & np.isfinite(roc20_floor)
        & (roc20 > roc20_floor)
        & np.isfinite(lag(low_slope, 20))
        & (low_slope > lag(low_slope, 20))
    )
    terminal_recent = rolling_any(soft_terminal, 5)
    terminal_recent10 = rolling_any(soft_terminal, 10)
    terminal_recent15 = rolling_any(soft_terminal, 15)

    previous_vol_median = (
        pd.Series(vol).shift(1).rolling(20, min_periods=20).median().to_numpy()
    )
    range_pct = np.where(c > 0, bar_range / c, np.nan)
    previous_range_median = (
        pd.Series(range_pct).shift(1).rolling(20, min_periods=20).median().to_numpy()
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        volume_ratio = vol / previous_vol_median
        range_ratio = range_pct / previous_range_median
    climax = fresh_low & ((volume_ratio >= 1.50) | (range_ratio >= 1.50))
    climax_recent = rolling_any(climax, 5)

    ret = close_s.pct_change().to_numpy()
    down_vol = np.where(ret < 0, vol, 0.0)
    vol3 = pd.Series(vol).rolling(3, min_periods=3).sum().to_numpy()
    down3 = pd.Series(down_vol).rolling(3, min_periods=3).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        down_share3 = down3 / vol3
    pressure_turn = (
        np.isfinite(lag(down_share3, 3))
        & (lag(down_share3, 3) >= 0.60)
        & (down_share3 <= 0.50)
    )
    volume_exhaustion = climax_recent | pressure_turn

    sector = np.asarray(sector_close, dtype=float)
    market = np.asarray(market_close, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        relative = np.log(c / sector)
    rs5 = relative - lag(relative, 5)
    relative_turn = np.isfinite(rs5) & (rs5 > 0) & (rs5 > lag(rs5, 3))
    systemic_repair = repair_state(market) & repair_state(sector)
    market_roc5 = pd.Series(market).pct_change(5).to_numpy()
    sector_roc5 = pd.Series(sector).pct_change(5).to_numpy()

    logret = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])
    rvd20, rvu20 = f4.semivars(logret, 20)
    with np.errstate(invalid="ignore", divide="ignore"):
        asym = np.where(rvu20 > 0, rvd20 / rvu20, np.nan)
    asym_base, asym_hi = f4._trailing_bands(asym, ohlcv.index)
    with np.errstate(invalid="ignore", divide="ignore"):
        f4_q = (asym_hi - asym) / (asym_hi - asym_base)
        f4_d3 = asym / lag(asym, 3) - 1.0
        rvd_d3 = rvd20 / lag(rvd20, 3) - 1.0
        low60_dist = c / low60 - 1.0
    f4_stress = (
        rolling_any(np.isfinite(asym) & np.isfinite(asym_hi) & (asym >= asym_hi), 20)
        & np.isfinite(asym_base)
        & (asym >= asym_base)
    )

    orthogonal_score = (
        volume_exhaustion.astype(np.int8)
        + relative_turn.astype(np.int8)
        + systemic_repair.astype(np.int8)
    )
    terminal_rejection = price_rejection & terminal_recent
    conditions = {
        "r0_price_rejection": price_rejection,
        "r1_terminal_rejection": terminal_rejection,
        "r2_volume_terminal": terminal_rejection & volume_exhaustion,
        "r3_context_terminal": (
            terminal_rejection & relative_turn & systemic_repair
        ),
        "r4_consensus": terminal_rejection & (orthogonal_score >= 2),
        "r5_survival3": survival3,
        "r6_terminal_survival3": survival3 & terminal_recent10,
        "r7_terminal_survival5": survival5 & terminal_recent10,
        "r8_survival_consensus": (
            survival3 & terminal_recent10 & (orthogonal_score >= 1)
        ),
        "r9_structure_break": structure_break,
        "r10_terminal_structure_break": structure_break & terminal_recent15,
        "r11_structure_consensus": (
            structure_break & terminal_recent15 & (orthogonal_score >= 1)
        ),
    }
    return {
        **conditions,
        "r4_consensus_f4": conditions["r4_consensus"],
        "r8_survival_consensus_f4": conditions["r8_survival_consensus"],
        "r11_structure_consensus_f4": conditions["r11_structure_consensus"],
        "f4_stress": f4_stress,
        "soft_terminal": soft_terminal,
        "price_rejection": price_rejection,
        "volume_exhaustion": volume_exhaustion,
        "relative_turn": relative_turn,
        "systemic_repair": systemic_repair,
        "asym": asym,
        "asym_base": asym_base,
        "asym_hi": asym_hi,
        "f4_q": f4_q,
        "f4_d3": f4_d3,
        "rvd_d3": rvd_d3,
        "low60_dist": low60_dist,
        "roc20": roc20,
        "close_location": close_location,
        "lower_wick": lower_wick,
        "volume_ratio": volume_ratio,
        "range_ratio": range_ratio,
        "down_share3": down_share3,
        "rs5": rs5,
        "market_roc5": market_roc5,
        "sector_roc5": sector_roc5,
        "terminal_recent": terminal_recent,
    }


def first_actions(
    watches: np.ndarray, condition: np.ndarray, horizon: int = ACTION_HORIZON
) -> list[tuple[int, int]]:
    """Unique first observable action dates as ``(index, delay)``.

    The function never stamps a day before the confirmation.  Multiple incumbent
    watches resolving on one day collapse to one action with the shortest delay.
    """
    found: dict[int, int] = {}
    n = len(condition)
    for raw_i in np.asarray(watches, dtype=int):
        i = int(raw_i)
        if i < 0 or i >= n:
            continue
        stop = min(n, i + horizon + 1)
        hit = np.flatnonzero(condition[i:stop])
        if not len(hit):
            continue
        j = i + int(hit[0])
        found[j] = min(found.get(j, horizon + 1), j - i)
    return sorted(found.items())


def metric_row(
    sym: str,
    kind: str,
    date: pd.Timestamp,
    i: int,
    delay: int,
    metrics: dict[str, np.ndarray],
) -> dict:
    tdt = float(metrics["tdt"][i])
    mae = float(metrics["mae63"][i])
    prox = float(metrics["prox"][i])
    return {
        "sym": sym,
        "kind": kind,
        "date": date,
        "month": str(date)[:7],
        "delay": int(delay),
        "mae": mae,
        "prox": prox,
        "w5": bool(prox <= 5.0),
        "called": bool(-2 <= tdt <= 5),
        "tail10": bool(mae <= -10.0),
        "tdt": tdt,
    }


def load_ohlcv(sym: str) -> pd.DataFrame:
    d = pd.read_parquet(OHLCV_DIR / f"{sym}.parquet")
    d = d[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    d.index = pd.DatetimeIndex(d.index).tz_localize(None)
    return d[~d.index.duplicated(keep="last")].sort_index()


def build_events(panel: pd.DataFrame, context: Context) -> pd.DataFrame:
    rows: list[dict] = []
    for number, prow in enumerate(panel.itertuples(index=False), 1):
        sym = str(prow.sym)
        path = OHLCV_DIR / f"{sym}.parquet"
        if not path.exists():
            continue
        x = load_ohlcv(sym)
        idx = x.index
        c = x["close"].to_numpy(dtype=float)
        metrics = f4.metric_arrays(c)
        valid = (
            (idx >= OOS_START)
            & np.isfinite(metrics["mae63"])
            & np.isfinite(metrics["prox"])
        )
        market = align_context(context.market, idx)
        sector_name = context.ticker_sector.get(sym)
        sector_source = context.sectors.get(sector_name, context.market)
        sector = align_context(sector_source, idx)
        feat = feature_arrays(x, market, sector)

        rung = str(prow.rung_derived)
        inc_dates = f4.tool_dates(f4.bars_for(x["close"], rung), "S")
        inc = idx.searchsorted(inc_dates)
        inc = inc[(inc < len(idx)) & valid[np.minimum(inc, len(idx) - 1)]]
        inc = np.unique(inc)
        for i in inc:
            rec = metric_row(sym, "inc", idx[i], int(i), 0, metrics)
            for feature in MODEL_FEATURES:
                value = feat[feature][i]
                rec[f"x_{feature}"] = (
                    float(value) if np.isfinite(value) else np.nan
                )
            rows.append(rec)

        for kind in CANDIDATES:
            watches = inc
            if kind in (
                "r4_consensus_f4",
                "r8_survival_consensus_f4",
                "r11_structure_consensus_f4",
            ):
                watches = inc[feat["f4_stress"][inc]]
            for j, delay in first_actions(watches, feat[kind]):
                if valid[j]:
                    rows.append(metric_row(sym, kind, idx[j], j, delay, metrics))
        if number % 100 == 0:
            print(f"processed {number}/{len(panel)} names; rows={len(rows):,}", flush=True)
    return (
        pd.DataFrame(rows)
        .sort_values(["kind", "sym", "date"])
        .reset_index(drop=True)
    )


def per_name(d: pd.DataFrame) -> pd.DataFrame:
    return d.groupby("sym").agg(
        mae=("mae", "median"),
        w5=("w5", "mean"),
        called=("called", "mean"),
        tail10=("tail10", "mean"),
        tdt=("tdt", "median"),
        delay=("delay", "median"),
        n=("date", "size"),
    )


def winsorized_mean(values: pd.Series) -> float:
    """Cross-name robust mean after the required per-name-first collapse."""
    a = values.dropna().to_numpy(dtype=float)
    if not len(a):
        return np.nan
    lo, hi = np.quantile(a, [0.05, 0.95])
    return float(np.clip(a, lo, hi).mean())


def paired_delta(d: pd.DataFrame, candidate: str, baseline: str = "inc") -> dict:
    b = per_name(d[d.kind == baseline]).add_prefix("b_")
    c = per_name(d[d.kind == candidate]).add_prefix("c_")
    z = b.join(c, how="inner")
    if not len(z):
        return {
            "names": 0,
            "mae": np.nan,
            "w5": np.nan,
            "called": np.nan,
            "tail10": np.nan,
            "tdt": np.nan,
        }
    return {
        "names": len(z),
        "mae": winsorized_mean(z.c_mae - z.b_mae),
        "w5": winsorized_mean((z.c_w5 - z.b_w5) * 100),
        "called": winsorized_mean((z.c_called - z.b_called) * 100),
        "tail10": winsorized_mean((z.b_tail10 - z.c_tail10) * 100),
        "tdt": winsorized_mean(z.c_tdt - z.b_tdt),
    }


def absolute_summary(d: pd.DataFrame, candidate: str) -> dict:
    raw = d[d.kind == candidate]
    z = per_name(raw)
    if not len(z):
        return {
            "events": 0,
            "names": 0,
            "names3": 0,
            "mae": np.nan,
            "w5": np.nan,
            "called": np.nan,
            "tail10": np.nan,
            "tdt": np.nan,
            "delay": np.nan,
        }
    return {
        "events": len(raw),
        "names": len(z),
        "names3": int((z.n >= 3).sum()),
        "mae": float(z.mae.median()),
        "w5": float(z.w5.mean() * 100),
        "called": float(z.called.mean() * 100),
        "tail10": float(z.tail10.mean() * 100),
        "tdt": float(z.tdt.median()),
        "delay": float(z.delay.median()),
    }


def bootstrap_delta(
    d: pd.DataFrame,
    candidate: str,
    baseline: str,
    n_boot: int,
    seed_offset: int,
) -> dict[str, tuple[float, float]]:
    x = d[d.kind.isin([baseline, candidate])].copy()
    months = np.array(sorted(x.month.unique()))
    if not len(months):
        return {}
    pieces = {month: x[x.month == month] for month in months}
    rng = np.random.default_rng(BOOT_SEED + seed_offset)
    acc: dict[str, list[float]] = {
        key: [] for key in ("mae", "w5", "called", "tail10", "tdt")
    }
    for _ in range(n_boot):
        draw = rng.choice(months, len(months), replace=True)
        sample = pd.concat([pieces[month] for month in draw], ignore_index=True)
        delta = paired_delta(sample, candidate, baseline)
        for key in acc:
            acc[key].append(delta[key])
    return {
        key: (
            float(np.nanpercentile(values, 2.5)),
            float(np.nanpercentile(values, 97.5)),
        )
        for key, values in acc.items()
    }


def ci_text(ci: tuple[float, float] | None) -> str:
    if not ci or not np.all(np.isfinite(ci)):
        return "[—]"
    return f"[{ci[0]:+.2f}, {ci[1]:+.2f}]"


def era_masks(events: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "DEV 2020H2–2022": events.date <= DEV_END,
        "VAL 2023–2024": events.date.between(VAL_START, VAL_END),
        "FWD 2025+": events.date >= FWD_START,
    }


def build_panel(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for era, mask in era_masks(events).items():
        d = events[mask]
        for kind in ("inc", *CANDIDATES):
            z = per_name(d[d.kind == kind]).reset_index()
            z["era"] = era
            z["kind"] = kind
            rows.append(z)
    return pd.concat(rows, ignore_index=True)


def stress_counts(events: pd.DataFrame, kind: str) -> tuple[int, int]:
    h1 = events[
        (events.kind == kind)
        & events.date.between("2022-01-01", "2022-06-30")
    ]
    near = events[
        (events.kind == kind)
        & events.date.between("2022-09-14", "2022-11-11")
    ]
    return len(h1), len(near)


def render_report(
    events: pd.DataFrame,
    panel: pd.DataFrame,
    n_boot: int,
) -> str:
    lines: list[str] = [
        "# PSS-F4R — causal terminality repair",
        "",
        "Exploratory shadow study. This does **not** reverse the standalone F4 "
        "kill and does not promote authority: all available history was already "
        "visible before this repair wave. The engineering question is whether a "
        "causal multi-stage architecture can improve timing robustness without "
        "backdating persistence.",
        "",
        "## Fixed architecture",
        "",
        "1. The incumbent Stoch-RSI signal at the structure-derived rung arms a "
        f"{ACTION_HORIZON}-trading-day watch.",
        "2. Price timing is an observable rejection of a fresh 20-day intraday low "
        "(bullish rejection bar or next-day reclaim).",
        "3. Soft terminality requires price within 5% of its trailing 60-day close "
        "low, ROC20 off its prior 20-day worst, and the rolling-low slope flattening.",
        "4. Orthogonal blocks are recent range/volume climax or down-volume-share "
        "reversal; stock-vs-sector relative-strength repair; and simultaneous SPY/"
        "sector-ETF repair.",
        "5. R4 requires at least two of those three orthogonal blocks. The F4 "
        "variant additionally restricts the original watch to a causal high-"
        "asymmetry stress state. Actions are stamped only on the confirmation day.",
        "6. R5–R8 add a survival clock: a rejection must remain the low for three "
        "or five completed sessions and price must stand above the rejection close. "
        "R8 then requires at least one orthogonal confirmation. This is causal "
        "post-rejection evidence, never a backdated label.",
        "7. R9–R11 add a break-of-structure clock: after a rejection in the prior "
        "10 sessions, close must exceed the prior five-day high. R10 retains recent "
        "terminality and R11 also requires an orthogonal confirmation.",
        "",
        "Ruler: per-name-first MAE63, within-5%-of-±31td-low (W5), called window "
        "(−2..+5td), MAE≤−10% tail rate, and td-to-trough. Positive paired deltas "
        "mean improvement; for tail rate the sign is inverted so positive is also "
        "better. Inference uses signal-month clustered bootstrap.",
        "",
        f"Universe/event census: {panel.sym.nunique()} names; "
        f"{int((events.kind == 'inc').sum()):,} incumbent events; "
        f"{events.date.min().date()} through {events.date.max().date()}.",
        "",
    ]

    all_ci: dict[tuple[str, str], dict[str, tuple[float, float]]] = {}
    for era_number, (era, mask) in enumerate(era_masks(events).items()):
        d = events[mask]
        lines.extend(
            [
                f"## {era}",
                "",
                "| construction | events | names | ≥3 names | MAE | W5 | called | "
                "tail≤−10 | median tdt | delay |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for kind in ("inc", *CANDIDATES):
            s = absolute_summary(d, kind)
            lines.append(
                f"| {LABELS[kind]} | {s['events']:,} | {s['names']:,} | "
                f"{s['names3']:,} | {s['mae']:+.2f}% | {s['w5']:.1f}% | "
                f"{s['called']:.1f}% | {s['tail10']:.1f}% | {s['tdt']:+.1f}td | "
                f"{s['delay']:.1f}td |"
            )
        lines.extend(
            [
                "",
                "### Paired improvement vs incumbent (95% month-cluster CI)",
                "",
                "| construction | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for candidate_number, kind in enumerate(CANDIDATES):
            ci = bootstrap_delta(
                d,
                kind,
                "inc",
                n_boot,
                seed_offset=era_number * 100 + candidate_number,
            )
            all_ci[(era, kind)] = ci
            lines.append(
                f"| {LABELS[kind]} | {ci_text(ci.get('mae'))} | "
                f"{ci_text(ci.get('w5'))} | {ci_text(ci.get('called'))} | "
                f"{ci_text(ci.get('tail10'))} | {ci_text(ci.get('tdt'))} |"
            )
        lines.append("")

    lines.extend(
        [
            "## F4 incremental ablation",
            "",
            "Each +F4 pair shares its confirmation rule with the non-F4 row; only the "
            "watch arm differs. This isolates whether requiring high downside-"
            "asymmetry stress improves an already-qualified action.",
            "",
            "| pair | era | +F4 − no-F4 ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for pair_number, (base_kind, f4_kind) in enumerate(
        (
            ("r4_consensus", "r4_consensus_f4"),
            ("r8_survival_consensus", "r8_survival_consensus_f4"),
            ("r11_structure_consensus", "r11_structure_consensus_f4"),
        )
    ):
        for era_number, (era, mask) in enumerate(era_masks(events).items()):
            ci = bootstrap_delta(
                events[mask],
                f4_kind,
                base_kind,
                n_boot,
                seed_offset=500 + pair_number * 100 + era_number,
            )
            lines.append(
                f"| {LABELS[base_kind]} | {era} | {ci_text(ci.get('mae'))} | "
                f"{ci_text(ci.get('w5'))} | {ci_text(ci.get('called'))} | "
                f"{ci_text(ci.get('tail10'))} | {ci_text(ci.get('tdt'))} |"
            )

    lines.extend(
        [
            "",
            "## 2022 containment diagnostic",
            "",
            "Raw counts are shown with monthly density because H1 spans six months "
            "while the September–November terminal-low window is approximately two.",
            "",
            "| construction | H1 events | H1/month | terminal-window events | "
            "window/month | density ratio |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for kind in ("inc", *CANDIDATES):
        h1, near = stress_counts(events, kind)
        h1_density = h1 / 6
        near_density = near / 2
        ratio = h1_density / near_density if near_density else np.nan
        lines.append(
            f"| {LABELS[kind]} | {h1:,} | {h1_density:.1f} | {near:,} | "
            f"{near_density:.1f} | {ratio:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Promotion law",
            "",
            "A construction is robust enough for further forward shadowing only if:",
            "",
            "- the lower 95% bound is positive for paired MAE **and** MAE≤−10% tail "
            "improvement in both DEV and VAL;",
            "- W5 or called-window timing improves without relying on a degenerate "
            "small sample;",
            "- it beats its price-only, terminality-only, and F4-removal ablations;",
            "- coverage spans at least 500 names with meaningful repeated events; and",
            "- H1-2022 firing density is materially below the terminal-low window.",
            "",
            "No result in this report is an untouched holdout. A passing exploratory "
            "construction must be frozen and verified prospectively.",
            "",
            "## What was found",
            "",
            "- Immediate rejection/terminality materially improves W5 and called-window "
            "timing, but its median action remains early and MAE/tail improvement is "
            "not stable.",
            "- Three/five-day survival moves median tdt toward the trough and restores "
            "2022 density discrimination, but does not improve forward risk.",
            "- A five-day break of structure gives up W5 and often worsens MAE; it is "
            "confirmation after the useful entry window, not a repair.",
            "- Requiring F4 stress does not improve any matched non-F4 construction. "
            "No hand-built candidate passes the promotion law.",
            "",
            "## Limitations",
            "",
            "- Current-listed-name and current-sector mappings introduce survivor and "
            "classification bias; the sector/market inputs are causal in time but the "
            "universe composition is not point-in-time.",
            "- Yahoo-adjusted closes and local OHLCV are suitable for relative tests, "
            "not executable intraday fills.",
            "- The fixed thresholds are mechanism choices, not optimized cutoffs. This "
            "reduces search freedom but does not turn inspected history into validation.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bootstraps",
        type=int,
        default=DEFAULT_BOOTSTRAPS,
        help="Month-cluster bootstrap draws (default: %(default)s).",
    )
    parser.add_argument(
        "--reuse-events",
        action="store_true",
        help="Reuse the existing event parquet and regenerate summaries/report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel = pd.read_parquet(PANEL_PQ)[["sym", "rung_derived"]].dropna()
    if args.reuse_events and OUT_EVENTS.exists():
        events = pd.read_parquet(OUT_EVENTS)
    else:
        events = build_events(panel, load_context())
        OUT_EVENTS.parent.mkdir(parents=True, exist_ok=True)
        events.to_parquet(OUT_EVENTS, index=False)
    name_panel = build_panel(events)
    name_panel.to_parquet(OUT_PANEL, index=False)
    report = render_report(events, name_panel, max(1, args.bootstraps))
    OUT_REPORT.write_text(report, encoding="utf-8")
    print(f"wrote {OUT_EVENTS.relative_to(ROOT)} ({len(events):,} rows)")
    print(f"wrote {OUT_PANEL.relative_to(ROOT)} ({len(name_panel):,} rows)")
    print(f"wrote {OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
