#!/usr/bin/env python3
"""PSS-SR1 — stress-matched second-test elasticity.

The frozen design is in ``research/PSS_SR1_STRESS_ELASTICITY_PREREG.md`` and
was committed before this harness was run.  This file intentionally contains
one construction, not an outcome-selected parameter grid.

Run:
    python scripts/research/pss_sr1_stress_elasticity.py

Outputs:
    reports/pss_sr1_stress_elasticity.md
    data/research/pss_sr1_stress_elasticity_events.parquet
    data/research/pss_sr1_stress_elasticity_panel.parquet
    data/research/pss_sr1_stress_elasticity_census.parquet
"""

from __future__ import annotations

import argparse
from collections import Counter
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
OUT_EVENTS = ROOT / "data/research/pss_sr1_stress_elasticity_events.parquet"
OUT_PANEL = ROOT / "data/research/pss_sr1_stress_elasticity_panel.parquet"
OUT_CENSUS = ROOT / "data/research/pss_sr1_stress_elasticity_census.parquet"
OUT_REPORT = ROOT / "reports/pss_sr1_stress_elasticity.md"

OOS_START = pd.Timestamp("2020-07-01")
DEV_END = pd.Timestamp("2022-12-31")
VAL_START = pd.Timestamp("2023-01-01")
VAL_END = pd.Timestamp("2024-12-31")
FWD_START = pd.Timestamp("2025-01-01")

ANCHOR_LOOKBACK = 60
ANCHOR_COOLDOWN = 21
BETA_WINDOW = 126
R2_MIN = 0.35
SECTOR_RETURN_WINDOW = 20
SHOCK_WINDOW = 252
SHOCK_MIN = 126
SHOCK_Q = 0.15
A_START_MAX_DELAY = 3
A_ELASTICITY_MIN = 0.75
B_START_MAX_DELAY = 15
B_STRESS_RATIO_MIN = 0.80
GEOMETRY_ATR_TOL = 0.50
ELASTICITY_RATIO_MAX = 0.50
OUTCOME_HORIZON = 63
REBOUND_TARGET = 0.08

PERMUTATIONS = 2_000
PERM_SEED = 20260802
BOOTSTRAPS = 1_000
BOOT_SEED = 20260803

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

EVENT_GROUPS = ("stress_path", "geometry", "geometry_control", "sr1")
INFER_METRICS = ("mae", "tail10", "w5", "called", "rebound8_first")
EVENT_COLUMNS = (
    "sym",
    "sector",
    "etf",
    "anchor_date",
    "a_start",
    "a_end",
    "a_confirm",
    "rebound_date",
    "b_start",
    "b_end",
    "b_confirm",
    "date",
    "month",
    "pulse_id",
    "group",
    "geometry_hold",
    "is_sr1",
    "beta_anchor",
    "r2_anchor",
    "sector_sigma_anchor",
    "atr_anchor",
    "sector20_anchor",
    "stress_a",
    "stress_b",
    "stress_ratio",
    "elasticity_a",
    "elasticity_b",
    "elasticity_ratio",
    "low_a",
    "low_b",
    "delay",
    "next_open_gap",
    "mae",
    "prox",
    "w5",
    "called",
    "tail10",
    "tdt",
    "rebound8_first",
    "breach_first",
    "unresolved",
    "resolution_day",
)


@dataclass(frozen=True)
class Pulse:
    """A consecutive run of shock days, known only on ``confirm``."""

    start: int
    end: int
    confirm: int


@dataclass(frozen=True)
class AnchorStats:
    beta: float
    r2: float
    sector_sigma: float
    atr: float
    sector20: float


def clean_index(d: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    d = d.copy()
    d.index = pd.DatetimeIndex(d.index).tz_localize(None)
    return d[~d.index.duplicated(keep="last")].sort_index()


def load_ohlcv(sym: str) -> pd.DataFrame:
    d = pd.read_parquet(OHLCV_DIR / f"{sym}.parquet")
    d = clean_index(d)
    return d[["open", "high", "low", "close"]].dropna()


def load_yahoo_close(symbol: str) -> pd.Series:
    d = clean_index(pd.read_parquet(YAHOO_DIR / f"{symbol}.parquet"))
    column = "close" if "close" in d.columns else "close_price"
    return d[column].dropna().astype(float)


def align_past(source: pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    """Past-only alignment. A future ETF print can never fill an earlier date."""

    return source.reindex(index, method="ffill").to_numpy(dtype=float)


def log_returns(close: np.ndarray) -> np.ndarray:
    out = np.full(len(close), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[1:] = np.log(close[1:] / close[:-1])
    return out


def fresh_low_anchors(close: np.ndarray) -> np.ndarray:
    """Greedy fresh-60-close anchors with the frozen 21-session cooldown."""

    prior = (
        pd.Series(close, dtype=float)
        .shift(1)
        .rolling(ANCHOR_LOOKBACK, min_periods=ANCHOR_LOOKBACK)
        .min()
        .to_numpy()
    )
    candidate = np.flatnonzero(np.isfinite(prior) & (close <= prior))
    accepted: list[int] = []
    next_allowed = 0
    for i in candidate:
        if i >= next_allowed:
            accepted.append(int(i))
            next_allowed = int(i) + ANCHOR_COOLDOWN + 1
    return np.asarray(accepted, dtype=int)


def sector_shocks(sector_close: np.ndarray) -> np.ndarray:
    """Point-in-time sector-shock flags using a shifted trailing quantile."""

    ret = log_returns(sector_close)
    threshold = (
        pd.Series(ret)
        .shift(1)
        .rolling(SHOCK_WINDOW, min_periods=SHOCK_MIN)
        .quantile(SHOCK_Q)
        .to_numpy()
    )
    return np.isfinite(ret) & np.isfinite(threshold) & (ret < 0) & (
        ret <= threshold
    )


def completed_pulses(shock: np.ndarray) -> list[Pulse]:
    """Group shock runs and stamp completion on the first following non-shock."""

    shock = np.asarray(shock, dtype=bool)
    pulses: list[Pulse] = []
    i = 0
    while i < len(shock):
        if not shock[i]:
            i += 1
            continue
        start = i
        while i + 1 < len(shock) and shock[i + 1]:
            i += 1
        end = i
        if end + 1 < len(shock):
            pulses.append(Pulse(start=start, end=end, confirm=end + 1))
        i += 1
    return pulses


def anchor_stats(
    ohlcv: pd.DataFrame,
    sector_close: np.ndarray,
    anchor: int,
) -> AnchorStats | None:
    """Estimate every anchor input exclusively from sessions before the anchor."""

    if anchor < BETA_WINDOW + 1 or anchor < SECTOR_RETURN_WINDOW + 1:
        return None
    stock_ret = log_returns(ohlcv["close"].to_numpy(dtype=float))
    sector_ret = log_returns(sector_close)
    y = stock_ret[anchor - BETA_WINDOW : anchor]
    x = sector_ret[anchor - BETA_WINDOW : anchor]
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() != BETA_WINDOW or np.var(x, ddof=1) <= 0:
        return None
    xv = x[valid]
    yv = y[valid]
    beta = float(np.cov(xv, yv, ddof=1)[0, 1] / np.var(xv, ddof=1))
    fitted = yv.mean() + beta * (xv - xv.mean())
    ss_tot = float(np.sum((yv - yv.mean()) ** 2))
    ss_res = float(np.sum((yv - fitted) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else np.nan
    sigma = float(np.std(xv, ddof=1))

    high = ohlcv["high"].to_numpy(dtype=float)
    low = ohlcv["low"].to_numpy(dtype=float)
    close = ohlcv["close"].to_numpy(dtype=float)
    tr = np.full(len(close), np.nan)
    tr[1:] = np.maximum.reduce(
        [
            high[1:] - low[1:],
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ]
    )
    atr_slice = tr[anchor - 14 : anchor]
    if not np.isfinite(atr_slice).all():
        return None
    atr = float(np.mean(atr_slice))
    sector20 = float(np.exp(np.sum(sector_ret[anchor - 20 : anchor])) - 1.0)
    values = np.asarray([beta, r2, sigma, atr, sector20])
    if not np.isfinite(values).all() or sigma <= 0 or atr <= 0:
        return None
    return AnchorStats(beta, r2, sigma, atr, sector20)


def pulse_measure(
    pulse: Pulse,
    stock_ret: np.ndarray,
    sector_ret: np.ndarray,
    stock_low: np.ndarray,
    stats: AnchorStats,
) -> dict[str, float]:
    rs = float(np.sum(stock_ret[pulse.start : pulse.end + 1]))
    rf = float(np.sum(sector_ret[pulse.start : pulse.end + 1]))
    days = pulse.end - pulse.start + 1
    stress = -rf / (stats.sector_sigma * np.sqrt(days))
    denominator = stats.beta * max(1e-6, -rf)
    elasticity = max(0.0, -rs) / denominator
    return {
        "stock_return": rs,
        "sector_return": rf,
        "stress": float(stress),
        "elasticity": float(elasticity),
        "low": float(np.min(stock_low[pulse.start : pulse.end + 1])),
    }


def find_sequence(
    anchor: int,
    pulses: list[Pulse],
    stock_close: np.ndarray,
    stock_low: np.ndarray,
    stock_ret: np.ndarray,
    sector_ret: np.ndarray,
    stats: AnchorStats,
) -> tuple[dict[str, object] | None, str]:
    """Apply the frozen A → rebound → comparable-B state machine."""

    pulse_a = next(
        (
            pulse
            for pulse in pulses
            if anchor <= pulse.start <= anchor + A_START_MAX_DELAY
        ),
        None,
    )
    if pulse_a is None:
        return None, "no_pulse_a"
    a = pulse_measure(pulse_a, stock_ret, sector_ret, stock_low, stats)
    if not np.isfinite([a["stress"], a["elasticity"]]).all():
        return None, "invalid_pulse_a"
    if a["elasticity"] < A_ELASTICITY_MIN:
        return None, "pulse_a_not_damaging"

    rebound_level = a["low"] + stats.atr
    latest_b_start = pulse_a.confirm + B_START_MAX_DELAY
    for pulse_b in pulses:
        if pulse_b.start <= pulse_a.end:
            continue
        if pulse_b.start > latest_b_start:
            break
        rebound_candidates = np.flatnonzero(
            stock_close[pulse_a.confirm : pulse_b.start] >= rebound_level
        )
        if not len(rebound_candidates):
            continue
        rebound = pulse_a.confirm + int(rebound_candidates[0])
        b = pulse_measure(pulse_b, stock_ret, sector_ret, stock_low, stats)
        if not np.isfinite([b["stress"], b["elasticity"]]).all():
            continue
        if b["stress"] < B_STRESS_RATIO_MIN * a["stress"]:
            continue
        geometry = bool(b["low"] >= a["low"] - GEOMETRY_ATR_TOL * stats.atr)
        elasticity_ratio = (
            float(b["elasticity"] / a["elasticity"])
            if a["elasticity"] > 0
            else np.inf
        )
        treatment = bool(geometry and elasticity_ratio <= ELASTICITY_RATIO_MAX)
        group = (
            "sr1"
            if treatment
            else ("geometry_control" if geometry else "geometry_break")
        )
        return (
            {
                "pulse_a": pulse_a,
                "pulse_b": pulse_b,
                "a": a,
                "b": b,
                "rebound": rebound,
                "geometry": geometry,
                "treatment": treatment,
                "elasticity_ratio": elasticity_ratio,
                "group": group,
            },
            "ok",
        )
    return None, "no_rebound_comparable_b"


def competing_risk(
    close: np.ndarray,
    low: np.ndarray,
    action: int,
    breach_level: float,
    horizon: int = OUTCOME_HORIZON,
) -> dict[str, object]:
    """Fixed-denominator 63-session race; breach wins a same-day tie."""

    if action + horizon >= len(close):
        return {
            "rebound8_first": False,
            "breach_first": False,
            "unresolved": True,
            "resolution_day": np.nan,
        }
    target = close[action] * (1.0 + REBOUND_TARGET)
    for day in range(1, horizon + 1):
        j = action + day
        if low[j] < breach_level:
            return {
                "rebound8_first": False,
                "breach_first": True,
                "unresolved": False,
                "resolution_day": day,
            }
        if close[j] >= target:
            return {
                "rebound8_first": True,
                "breach_first": False,
                "unresolved": False,
                "resolution_day": day,
            }
    return {
        "rebound8_first": False,
        "breach_first": False,
        "unresolved": True,
        "resolution_day": np.nan,
    }


def era_name(date: pd.Timestamp) -> str:
    if date <= DEV_END:
        return "DEV 2020H2–2022"
    if date <= VAL_END:
        return "VAL 2023–2024"
    return "FWD 2025+"


def event_row(
    sym: str,
    sector: str,
    etf: str,
    index: pd.DatetimeIndex,
    ohlcv: pd.DataFrame,
    anchor: int,
    stats: AnchorStats,
    sequence: dict[str, object],
    metrics: dict[str, np.ndarray],
) -> dict[str, object] | None:
    pulse_a = sequence["pulse_a"]
    pulse_b = sequence["pulse_b"]
    assert isinstance(pulse_a, Pulse)
    assert isinstance(pulse_b, Pulse)
    action = pulse_b.confirm
    if action + OUTCOME_HORIZON >= len(index):
        return None
    if not np.isfinite(metrics["mae63"][action]) or not np.isfinite(
        metrics["prox"][action]
    ):
        return None
    a = sequence["a"]
    b = sequence["b"]
    assert isinstance(a, dict)
    assert isinstance(b, dict)
    risk = competing_risk(
        ohlcv["close"].to_numpy(dtype=float),
        ohlcv["low"].to_numpy(dtype=float),
        action,
        float(a["low"]) - GEOMETRY_ATR_TOL * stats.atr,
    )
    tdt = float(metrics["tdt"][action])
    mae = float(metrics["mae63"][action])
    prox = float(metrics["prox"][action])
    next_open_gap = float(
        (ohlcv["open"].iloc[action + 1] / ohlcv["close"].iloc[action] - 1.0)
        * 100.0
    )
    date = index[action]
    return {
        "sym": sym,
        "sector": sector,
        "etf": etf,
        "anchor_date": index[anchor],
        "a_start": index[pulse_a.start],
        "a_end": index[pulse_a.end],
        "a_confirm": index[pulse_a.confirm],
        "rebound_date": index[int(sequence["rebound"])],
        "b_start": index[pulse_b.start],
        "b_end": index[pulse_b.end],
        "b_confirm": date,
        "date": date,
        "month": str(date)[:7],
        "pulse_id": f"{etf}:{index[pulse_b.start].date()}",
        "group": str(sequence["group"]),
        "geometry_hold": bool(sequence["geometry"]),
        "is_sr1": bool(sequence["treatment"]),
        "beta_anchor": stats.beta,
        "r2_anchor": stats.r2,
        "sector_sigma_anchor": stats.sector_sigma,
        "atr_anchor": stats.atr,
        "sector20_anchor": stats.sector20 * 100.0,
        "stress_a": float(a["stress"]),
        "stress_b": float(b["stress"]),
        "stress_ratio": float(b["stress"] / a["stress"]),
        "elasticity_a": float(a["elasticity"]),
        "elasticity_b": float(b["elasticity"]),
        "elasticity_ratio": float(sequence["elasticity_ratio"]),
        "low_a": float(a["low"]),
        "low_b": float(b["low"]),
        "delay": int(action - anchor),
        "next_open_gap": next_open_gap,
        "mae": mae,
        "prox": prox,
        "w5": bool(prox <= 5.0),
        "called": bool(-2 <= tdt <= 5),
        "tail10": bool(mae <= -10.0),
        "tdt": tdt,
        **risk,
    }


def build_events(
    names: list[str],
    ticker_sector: dict[str, str],
    sector_prices: dict[str, pd.Series],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    census_rows: list[dict[str, object]] = []
    for number, sym in enumerate(names, 1):
        count: Counter[str] = Counter()
        sector = ticker_sector.get(sym)
        base = {"sym": sym, "sector": sector or "", "etf": ""}
        if not (OHLCV_DIR / f"{sym}.parquet").exists():
            census_rows.append({**base, "status": "missing_ohlcv"})
            continue
        if sector not in SECTOR_ETF:
            census_rows.append({**base, "status": "missing_sector_map"})
            continue
        etf = SECTOR_ETF[sector]
        base["etf"] = etf
        if etf not in sector_prices:
            census_rows.append({**base, "status": "missing_sector_etf"})
            continue

        ohlcv = load_ohlcv(sym)
        index = ohlcv.index
        if len(index) < BETA_WINDOW + OUTCOME_HORIZON + 10:
            census_rows.append({**base, "status": "short_history"})
            continue
        close = ohlcv["close"].to_numpy(dtype=float)
        low = ohlcv["low"].to_numpy(dtype=float)
        sector_close = align_past(sector_prices[etf], index)
        stock_ret = log_returns(close)
        sector_ret = log_returns(sector_close)
        pulses = completed_pulses(sector_shocks(sector_close))
        metrics = f4.metric_arrays(close)
        anchors = fresh_low_anchors(close)
        anchors = anchors[index[anchors] >= OOS_START]
        count["anchors"] = len(anchors)
        seen_actions: set[int] = set()

        for anchor in anchors:
            stats = anchor_stats(ohlcv, sector_close, int(anchor))
            if stats is None:
                count["invalid_anchor_stats"] += 1
                continue
            if stats.beta <= 0:
                count["beta_nonpositive"] += 1
                continue
            if stats.r2 < R2_MIN:
                count["r2_below_min"] += 1
                continue
            if stats.sector20 >= 0:
                count["sector_not_down"] += 1
                continue
            count["systemic_anchors"] += 1
            sequence, reason = find_sequence(
                int(anchor),
                pulses,
                close,
                low,
                stock_ret,
                sector_ret,
                stats,
            )
            if sequence is None:
                count[reason] += 1
                continue
            pulse_b = sequence["pulse_b"]
            assert isinstance(pulse_b, Pulse)
            if pulse_b.confirm in seen_actions:
                count["duplicate_action"] += 1
                continue
            seen_actions.add(pulse_b.confirm)
            row = event_row(
                sym,
                sector,
                etf,
                index,
                ohlcv,
                int(anchor),
                stats,
                sequence,
                metrics,
            )
            if row is None:
                count["incomplete_outcome"] += 1
                continue
            rows.append(row)
            count["stress_paths"] += 1
            if row["geometry_hold"]:
                count["geometry"] += 1
            if row["group"] == "geometry_control":
                count["geometry_controls"] += 1
            if row["is_sr1"]:
                count["treatments"] += 1

        status = "eligible" if count["anchors"] else "no_oos_anchor"
        census_rows.append({**base, "status": status, **dict(count)})
        if number % 100 == 0:
            print(
                f"processed {number}/{len(names)} names; "
                f"paths={len(rows):,}; treatments="
                f"{sum(bool(row['is_sr1']) for row in rows):,}",
                flush=True,
            )

    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    if len(events):
        events = events.sort_values(["date", "etf", "sym"]).reset_index(drop=True)
    census = pd.DataFrame(census_rows).fillna(0)
    return events, census


def event_subset(events: pd.DataFrame, kind: str) -> pd.DataFrame:
    if kind == "stress_path":
        return events
    if kind == "geometry":
        return events[events.geometry_hold]
    return events[events.group == kind]


def per_name_summary(events: pd.DataFrame, kind: str, era: str) -> pd.DataFrame:
    d = event_subset(events[events.date.map(era_name) == era], kind)
    if not len(d):
        return pd.DataFrame()
    z = (
        d.groupby("sym")
        .agg(
            n=("date", "size"),
            mae=("mae", "median"),
            prox=("prox", "median"),
            w5=("w5", "mean"),
            called=("called", "mean"),
            tail10=("tail10", "mean"),
            tdt=("tdt", "median"),
            rebound8_first=("rebound8_first", "mean"),
            breach_first=("breach_first", "mean"),
            unresolved=("unresolved", "mean"),
            delay=("delay", "median"),
        )
        .reset_index()
    )
    z["era"] = era
    z["kind"] = kind
    return z


def build_panel(events: pd.DataFrame) -> pd.DataFrame:
    pieces = [
        per_name_summary(events, kind, era)
        for era in ("DEV 2020H2–2022", "VAL 2023–2024", "FWD 2025+")
        for kind in EVENT_GROUPS
    ]
    pieces = [piece for piece in pieces if len(piece)]
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def metric_values(d: pd.DataFrame, metric: str) -> np.ndarray:
    values = d[metric].to_numpy(dtype=float)
    if metric in ("tail10", "breach_first"):
        return -100.0 * values
    if metric in ("w5", "called", "rebound8_first"):
        return 100.0 * values
    return values


def pulse_effects(events: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Equal-weight pulse effects; positive always means SR1 is better."""

    d = events[events.group.isin(["sr1", "geometry_control"])].copy()
    rows: list[dict[str, object]] = []
    for pulse_id, group in d.groupby("pulse_id", sort=True):
        treatment = group[group.group == "sr1"]
        control = group[group.group == "geometry_control"]
        if not len(treatment) or not len(control):
            continue
        effect = float(
            metric_values(treatment, metric).mean()
            - metric_values(control, metric).mean()
        )
        rows.append(
            {
                "pulse_id": pulse_id,
                "month": str(group.b_start.iloc[0])[:7],
                "effect": effect,
                "n_treatment": len(treatment),
                "n_control": len(control),
            }
        )
    return pd.DataFrame(rows)


def permuted_effects(
    events: pd.DataFrame,
    metric: str,
    n_perm: int,
    seed: int,
) -> tuple[float, np.ndarray, list[tuple[int, int]]]:
    """Permute labels within pulse while preserving each pulse's label counts."""

    d = events[events.group.isin(["sr1", "geometry_control"])].copy()
    prepared: list[tuple[np.ndarray, int]] = []
    counts: list[tuple[int, int]] = []
    observed_parts: list[float] = []
    for _, group in d.groupby("pulse_id", sort=True):
        treatment = group.group.to_numpy() == "sr1"
        n_treatment = int(treatment.sum())
        n_control = int((~treatment).sum())
        if not n_treatment or not n_control:
            continue
        values = metric_values(group, metric)
        prepared.append((values, n_treatment))
        counts.append((n_treatment, n_control))
        observed_parts.append(
            float(values[treatment].mean() - values[~treatment].mean())
        )
    if not prepared:
        return np.nan, np.full(n_perm, np.nan), counts
    observed = float(np.mean(observed_parts))
    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for draw in range(n_perm):
        parts = []
        for values, n_treatment in prepared:
            order = rng.permutation(len(values))
            treatment = order[:n_treatment]
            control = order[n_treatment:]
            parts.append(float(values[treatment].mean() - values[control].mean()))
        null[draw] = float(np.mean(parts))
    return observed, null, counts


def inference(
    events: pd.DataFrame,
    metric: str,
    n_perm: int,
    n_boot: int,
    seed_offset: int = 0,
) -> dict[str, float]:
    effects = pulse_effects(events, metric)
    observed, null, _ = permuted_effects(
        events, metric, n_perm, PERM_SEED + seed_offset
    )
    if not np.isfinite(observed):
        return {
            "effect": np.nan,
            "p": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
            "pulses": 0,
        }
    p_value = float((1 + np.sum(null >= observed)) / (n_perm + 1))
    months = np.asarray(sorted(effects.month.unique()))
    pieces = {
        month: effects.loc[effects.month == month, "effect"].to_numpy(dtype=float)
        for month in months
    }
    rng = np.random.default_rng(BOOT_SEED + seed_offset)
    boot = np.empty(n_boot)
    for draw in range(n_boot):
        sampled = rng.choice(months, len(months), replace=True)
        boot[draw] = float(np.mean(np.concatenate([pieces[m] for m in sampled])))
    return {
        "effect": observed,
        "p": p_value,
        "ci_low": float(np.percentile(boot, 2.5)),
        "ci_high": float(np.percentile(boot, 97.5)),
        "pulses": len(effects),
    }


def absolute_summary(events: pd.DataFrame, kind: str) -> dict[str, float]:
    d = event_subset(events, kind)
    if not len(d):
        return {
            "events": 0,
            "names": 0,
            "names3": 0,
            "pulses": 0,
            "mae": np.nan,
            "w5": np.nan,
            "called": np.nan,
            "tail10": np.nan,
            "rebound8_first": np.nan,
            "unresolved": np.nan,
            "delay": np.nan,
        }
    # The caller always provides a single era. Collapse binary outcomes per
    # name before any cross-name summary.
    z = (
        d.groupby("sym")
        .agg(
            n=("date", "size"),
            mae=("mae", "median"),
            w5=("w5", "mean"),
            called=("called", "mean"),
            tail10=("tail10", "mean"),
            rebound8_first=("rebound8_first", "mean"),
            unresolved=("unresolved", "mean"),
            delay=("delay", "median"),
        )
        .reset_index()
    )
    return {
        "events": len(d),
        "names": len(z),
        "names3": int((z.n >= 3).sum()),
        "pulses": d.pulse_id.nunique(),
        "mae": float(z.mae.median()),
        "w5": float(z.w5.mean() * 100.0),
        "called": float(z.called.mean() * 100.0),
        "tail10": float(z.tail10.mean() * 100.0),
        "rebound8_first": float(z.rebound8_first.mean() * 100.0),
        "unresolved": float(z.unresolved.mean() * 100.0),
        "delay": float(z.delay.median()),
    }


def f(value: float, digits: int = 2) -> str:
    if not np.isfinite(value):
        return "—"
    return f"{value:+.{digits}f}"


def qualification(
    events: pd.DataFrame,
    results: dict[tuple[str, str], dict[str, float]],
) -> tuple[bool, list[tuple[str, bool, str]]]:
    checks: list[tuple[str, bool, str]] = []
    for era in ("DEV 2020H2–2022", "VAL 2023–2024"):
        for metric in ("mae", "tail10"):
            r = results[(era, metric)]
            passed = bool(
                np.isfinite(r["ci_low"])
                and r["effect"] > 0
                and r["ci_low"] > 0
                and r["p"] <= 0.05
            )
            checks.append(
                (
                    f"{era} {metric} positive lower CI and p≤.05",
                    passed,
                    f"effect={f(r['effect'])}, CI=[{f(r['ci_low'])}, "
                    f"{f(r['ci_high'])}], p={r['p']:.4f}"
                    if np.isfinite(r["p"])
                    else "not estimable",
                )
            )
        timing_ok = any(
            results[(era, metric)]["effect"] > 0 for metric in ("w5", "called")
        )
        rebound_ok = results[(era, "rebound8_first")]["effect"] > 0
        checks.append(
            (
                f"{era} timing and rebound-first improve",
                bool(timing_ok and rebound_ok),
                f"W5={f(results[(era, 'w5')]['effect'])}, "
                f"called={f(results[(era, 'called')]['effect'])}, "
                f"rebound8={f(results[(era, 'rebound8_first')]['effect'])}",
            )
        )

    treatment = events[events.group == "sr1"]
    names = treatment.sym.nunique()
    names3 = int((treatment.groupby("sym").size() >= 3).sum()) if len(treatment) else 0
    coverage_ok = names >= 500 and names3 >= 100
    pulse_counts = {
        era: pulse_effects(events[events.date.map(era_name) == era], "mae").shape[0]
        for era in ("DEV 2020H2–2022", "VAL 2023–2024")
    }
    cluster_ok = all(value >= 30 for value in pulse_counts.values())
    checks.append(
        (
            "Coverage: 500 names, 100 names≥3, 30 informative pulses/era",
            bool(coverage_ok and cluster_ok),
            f"names={names}, names≥3={names3}, pulses={pulse_counts}",
        )
    )

    h1 = treatment[treatment.date.between("2022-01-01", "2022-06-30")]
    autumn = treatment[treatment.date.between("2022-09-01", "2022-11-30")]
    h1_density = len(h1) / 6.0
    autumn_density = len(autumn) / 3.0
    checks.append(
        (
            "H1-2022 monthly density below Sep–Nov 2022",
            h1_density < autumn_density,
            f"{h1_density:.2f}/month vs {autumn_density:.2f}/month",
        )
    )
    fwd_ok = all(
        results[("FWD 2025+", metric)]["effect"] >= 0
        for metric in ("mae", "tail10")
    )
    checks.append(
        (
            "No FWD primary sign reversal",
            bool(fwd_ok),
            f"MAE={f(results[('FWD 2025+', 'mae')]['effect'])}, "
            f"tail={f(results[('FWD 2025+', 'tail10')]['effect'])}",
        )
    )
    return all(item[1] for item in checks), checks


def render_report(
    events: pd.DataFrame,
    census: pd.DataFrame,
    n_perm: int,
    n_boot: int,
) -> tuple[str, bool]:
    eras = ("DEV 2020H2–2022", "VAL 2023–2024", "FWD 2025+")
    results: dict[tuple[str, str], dict[str, float]] = {}
    lines = [
        "# PSS-SR1 — stress-matched second-test elasticity",
        "",
        "Frozen, causal challenge–response test. The construction and decision law "
        "were committed before final outcomes in "
        "`research/PSS_SR1_STRESS_ELASTICITY_PREREG.md`. Positive deltas below "
        "always mean SR1 is better than the disjoint geometry control.",
        "",
        "SR1 remains display/shadow research. Historical qualification could only "
        "authorize a prospective frozen shadow; it cannot change entry, ranking, "
        "or sizing.",
        "",
        "## Construction audit",
        "",
        "- Anchor: fresh prior-60-close low, 21-session cooldown.",
        "- Route: prior-126-session beta > 0, sector R² ≥ 0.35, prior sector "
        "20-session return < 0.",
        "- Pulse A: sector shock cluster begins within three sessions and stock "
        "downside elasticity ≥ 0.75.",
        "- Pulse B: observed after a one-ATR rebound, begins within 15 sessions, "
        "and normalized stress is at least 80% of pulse A.",
        "- Treatment: tested low holds within 0.5 frozen ATR and pulse-B "
        "elasticity is no more than half pulse A. Geometry control holds the same "
        "tested low but does not collapse elasticity.",
        "- Action: pulse-B confirmation close, never its retrospective start.",
        "",
        "## Coverage and outcomes",
        "",
    ]
    for era in eras:
        d = events[events.date.map(era_name) == era]
        lines.extend(
            [
                f"### {era}",
                "",
                "| group | events | names | names ≥3 | sector pulses | MAE63 | "
                "W5 | called | tail≤−10 | rebound8 first | unresolved | delay |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for kind in EVENT_GROUPS:
            s = absolute_summary(d, kind)
            lines.append(
                f"| {kind} | {s['events']:,} | {s['names']:,} | "
                f"{s['names3']:,} | {s['pulses']:,} | {f(s['mae'])}% | "
                f"{f(s['w5'], 1)}% | {f(s['called'], 1)}% | "
                f"{f(s['tail10'], 1)}% | {f(s['rebound8_first'], 1)}% | "
                f"{f(s['unresolved'], 1)}% | {f(s['delay'], 1)}td |"
            )
        lines.extend(
            [
                "",
                "#### SR1 minus geometry-control pulse effects",
                "",
                "| metric | effect | 95% month-block CI | pulse-permutation p | "
                "informative pulses |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for metric_number, metric in enumerate(INFER_METRICS):
            result = inference(
                d,
                metric,
                n_perm,
                n_boot,
                seed_offset=eras.index(era) * 100 + metric_number,
            )
            results[(era, metric)] = result
            p_text = f"{result['p']:.4f}" if np.isfinite(result["p"]) else "—"
            lines.append(
                f"| {metric} | {f(result['effect'])} | "
                f"[{f(result['ci_low'])}, {f(result['ci_high'])}] | "
                f"{p_text} | {int(result['pulses'])} |"
            )
        lines.append("")

    qualified, checks = qualification(events, results)
    lines.extend(
        [
            "## Frozen decision law",
            "",
            "| check | pass | evidence |",
            "|---|:---:|---|",
        ]
    )
    for label, passed, evidence in checks:
        lines.append(f"| {label} | {'YES' if passed else 'NO'} | {evidence} |")

    treatment = events[events.group == "sr1"]
    h1_months = (
        treatment[treatment.date.between("2022-01-01", "2022-06-30")]
        .groupby("month")
        .size()
        .reindex([f"2022-{month:02d}" for month in range(1, 7)], fill_value=0)
    )
    autumn_months = (
        treatment[treatment.date.between("2022-09-01", "2022-11-30")]
        .groupby("month")
        .size()
        .reindex([f"2022-{month:02d}" for month in range(9, 12)], fill_value=0)
    )
    lines.extend(
        [
            "",
            f"**Verdict: {'QUALIFIES FOR PROSPECTIVE SHADOW ONLY' if qualified else 'KILLED'}**.",
            "",
            "## 2022 containment and execution diagnostics",
            "",
            f"- H1-2022 monthly treatments: {h1_months.to_dict()}.",
            f"- Sep–Nov 2022 monthly treatments: {autumn_months.to_dict()}.",
            f"- Next-open gap median / 95th percentile: "
            f"{treatment.next_open_gap.median():+.2f}% / "
            f"{treatment.next_open_gap.quantile(0.95):+.2f}%."
            if len(treatment)
            else "- No treatment execution diagnostics were measurable.",
            "",
            "## Exclusion and path census",
            "",
        ]
    )
    status = census.groupby("status").size().sort_values(ascending=False)
    lines.extend(f"- `{key}`: {int(value):,} names" for key, value in status.items())
    count_columns = [
        column
        for column in census.columns
        if column not in {"sym", "sector", "etf", "status"}
    ]
    lines.extend(
        [
            "",
            "Aggregate anchor/path counters:",
            "",
        ]
    )
    for column in count_columns:
        total = float(pd.to_numeric(census[column], errors="coerce").fillna(0).sum())
        if total:
            lines.append(f"- `{column}`: {int(total):,}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "The gate met every frozen requirement. The only permitted next "
                "step is a versioned, prospective, display-only shadow ledger."
                if qualified
                else "At least one frozen requirement failed. This exact SR1 "
                "construction is not usable and must not be threshold-tuned after "
                "outcomes. Its mechanism-level evidence may inform a genuinely "
                "different preregistered family, but SR1 itself is blocklisted."
            ),
            "",
            f"Inference draws: {n_perm:,} within-pulse permutations "
            f"(base seed {PERM_SEED}); {n_boot:,} month-block bootstraps "
            f"(base seed {BOOT_SEED}).",
            "",
        ]
    )
    return "\n".join(lines), qualified


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--permutations", type=int, default=PERMUTATIONS)
    parser.add_argument("--bootstraps", type=int, default=BOOTSTRAPS)
    parser.add_argument(
        "--reuse-events",
        action="store_true",
        help="Reuse existing events/census and regenerate summaries/report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.reuse_events and OUT_EVENTS.exists() and OUT_CENSUS.exists():
        events = pd.read_parquet(OUT_EVENTS)
        census = pd.read_parquet(OUT_CENSUS)
    else:
        panel = pd.read_parquet(PANEL_PQ)
        names = sorted(panel.sym.dropna().astype(str).unique())
        mapping = pd.read_parquet(SECTOR_MAP_PQ)
        ticker_sector = dict(
            zip(
                mapping.ticker.astype(str),
                mapping.sector.astype(str),
                strict=False,
            )
        )
        sector_prices = {
            etf: load_yahoo_close(etf)
            for etf in sorted(set(SECTOR_ETF.values()))
            if (YAHOO_DIR / f"{etf}.parquet").exists()
        }
        events, census = build_events(names, ticker_sector, sector_prices)
        OUT_EVENTS.parent.mkdir(parents=True, exist_ok=True)
        events.to_parquet(OUT_EVENTS, index=False)
        census.to_parquet(OUT_CENSUS, index=False)
    panel_out = build_panel(events)
    panel_out.to_parquet(OUT_PANEL, index=False)
    report, qualified = render_report(
        events,
        census,
        max(1, args.permutations),
        max(1, args.bootstraps),
    )
    OUT_REPORT.write_text(report, encoding="utf-8")
    print(f"wrote {OUT_EVENTS.relative_to(ROOT)} ({len(events):,} rows)")
    print(f"wrote {OUT_PANEL.relative_to(ROOT)} ({len(panel_out):,} rows)")
    print(f"wrote {OUT_CENSUS.relative_to(ROOT)} ({len(census):,} rows)")
    print(f"wrote {OUT_REPORT.relative_to(ROOT)}")
    print(
        "verdict: "
        + ("QUALIFIES FOR PROSPECTIVE SHADOW ONLY" if qualified else "KILLED")
    )


if __name__ == "__main__":
    main()
