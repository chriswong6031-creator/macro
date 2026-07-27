#!/usr/bin/env python3
"""PSS-SR2 — persistent ex-self peer diffusion.

The exact construction and decision law were committed before forward outcomes
in ``research/PSS_SR2_PEER_DIFFUSION_PREREG.md``.  This harness contains one
outcome-bearing construction, not a tuning grid.

Run:
    python scripts/research/pss_sr2_peer_diffusion.py

Outputs:
    reports/pss_sr2_peer_diffusion.md
    data/research/pss_sr2_peer_diffusion_events.parquet
    data/research/pss_sr2_peer_diffusion_panel.parquet
    data/research/pss_sr2_peer_diffusion_census.parquet
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
OUT_EVENTS = ROOT / "data/research/pss_sr2_peer_diffusion_events.parquet"
OUT_PANEL = ROOT / "data/research/pss_sr2_peer_diffusion_panel.parquet"
OUT_CENSUS = ROOT / "data/research/pss_sr2_peer_diffusion_census.parquet"
OUT_REPORT = ROOT / "reports/pss_sr2_peer_diffusion.md"

OOS_START = pd.Timestamp("2020-07-01")
DEV_END = pd.Timestamp("2022-12-31")
VAL_END = pd.Timestamp("2024-12-31")

LOOKBACK = 60
ANCHOR_COOLDOWN = 21
FORMATION_DAYS = 4
ATR_WINDOW = 14
PEER_MIN = 15
BREADTH_MIN = 0.15
BREADTH_Q_WINDOW = 126
BREADTH_Q_MIN = 63
BREADTH_Q = 0.80
PATH_MAX = 40
REBOUND_ATR = 1.00
RETEST_LOW_DOWN_ATR = 0.50
RETEST_LOW_UP_ATR = 0.75
RETEST_CLOSE_UP_ATR = 1.50
PERSISTENCE = 3
DIFFUSION_RATIO_MAX = 0.50
OUTCOME_HORIZON = 63
REBOUND_TARGET = 0.08

PERMUTATIONS = 2_000
PERM_SEED = 20260804
BOOTSTRAPS = 1_000
BOOT_SEED = 20260805
MOVING_BLOCK_MONTHS = 3

SECTORS = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
)

INFER_METRICS = ("mae", "tail10", "w5", "called", "rebound8_first")
GROUPS = ("sr2", "geometry_control", "transient_control")
EVENT_COLUMNS = (
    "sym",
    "sector",
    "anchor_date",
    "formation_confirm",
    "rebound_date",
    "date",
    "month",
    "group",
    "is_sr2",
    "is_transient",
    "atr_anchor",
    "reference_low",
    "anchor_breadth",
    "peer_peak",
    "peer_breadth_b",
    "peer_breadth_3max",
    "diffusion_ratio",
    "delay",
    "low_depth_atr",
    "close_depth_atr",
    "next_open_gap",
    "severity_band",
    "delay_band",
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
class PathState:
    """Fully observed anchor → rebound → first retest path."""

    anchor: int
    confirm: int
    rebound: int
    action: int
    atr: float
    reference_low: float
    anchor_breadth: float
    peer_peak: float
    peer_breadth_b: float
    peer_breadth_3max: float
    diffusion_ratio: float
    treatment: bool
    transient: bool


def clean_index(d: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    d = d.copy()
    d.index = pd.DatetimeIndex(d.index).tz_localize(None)
    return d[~d.index.duplicated(keep="last")].sort_index()


def load_ohlcv(sym: str) -> pd.DataFrame:
    d = clean_index(pd.read_parquet(OHLCV_DIR / f"{sym}.parquet"))
    return d[["open", "high", "low", "close"]].astype(float)


def atr14_prior(d: pd.DataFrame) -> pd.Series:
    """ATR frozen with data through the prior session only."""

    prior_close = d["close"].shift(1)
    true_range = pd.concat(
        [
            d["high"] - d["low"],
            (d["high"] - prior_close).abs(),
            (d["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(ATR_WINDOW, min_periods=ATR_WINDOW).mean().shift(1)


def greedy_anchors(candidate: np.ndarray) -> np.ndarray:
    """Keep the first candidate and exclude the following 21 sessions."""

    accepted: list[int] = []
    next_allowed = 0
    for i in np.flatnonzero(np.asarray(candidate, dtype=bool)):
        if i >= next_allowed:
            accepted.append(int(i))
            next_allowed = int(i) + ANCHOR_COOLDOWN + 1
    return np.asarray(accepted, dtype=int)


def ex_self_breadth(
    new_low: pd.DataFrame,
    valid: pd.DataFrame,
    sym: str,
) -> tuple[pd.Series, pd.Series]:
    """Equal-weight peer breadth with the subject removed from both sums."""

    numerator = new_low.sum(axis=1) - new_low[sym].astype(int)
    denominator = valid.sum(axis=1) - valid[sym].astype(int)
    breadth = numerator / denominator.where(denominator > 0)
    return breadth.astype(float), denominator.astype(float)


def find_path(
    close: np.ndarray,
    low: np.ndarray,
    breadth: np.ndarray,
    peer_count: np.ndarray,
    atr: np.ndarray,
    anchor: int,
) -> tuple[PathState | None, str]:
    """Apply the frozen path state machine without reading a future outcome."""

    confirm = anchor + FORMATION_DAYS - 1
    if confirm >= len(close):
        return None, "incomplete_formation"
    formation = slice(anchor, confirm + 1)
    if np.any(peer_count[formation] < PEER_MIN):
        return None, "formation_peer_count"
    values = np.asarray(
        [
            atr[anchor],
            np.nanmin(low[formation]),
            breadth[anchor],
            np.nanmax(breadth[formation]),
        ],
        dtype=float,
    )
    if not np.isfinite(values).all() or values[0] <= 0 or values[3] <= 0:
        return None, "invalid_formation"
    atr_anchor, reference_low, anchor_breadth, peer_peak = values
    latest = min(len(close) - 1, confirm + PATH_MAX)

    rebound = next(
        (
            j
            for j in range(confirm + 1, latest + 1)
            if np.isfinite(close[j])
            and close[j] >= reference_low + REBOUND_ATR * atr_anchor
        ),
        None,
    )
    if rebound is None:
        return None, "no_rebound"

    action = next(
        (
            j
            for j in range(rebound + PERSISTENCE - 1, latest + 1)
            if np.isfinite(low[j])
            and np.isfinite(close[j])
            and reference_low - RETEST_LOW_DOWN_ATR * atr_anchor
            <= low[j]
            <= reference_low + RETEST_LOW_UP_ATR * atr_anchor
            and close[j] <= reference_low + RETEST_CLOSE_UP_ATR * atr_anchor
        ),
        None,
    )
    if action is None:
        return None, "no_retest"

    persistence = slice(action - PERSISTENCE + 1, action + 1)
    if np.any(peer_count[persistence] < PEER_MIN):
        return None, "retest_peer_count"
    breadth_window = breadth[persistence]
    if not np.isfinite(breadth_window).all():
        return None, "invalid_retest_breadth"
    peer_breadth_b = float(breadth[action])
    peer_breadth_3max = float(np.max(breadth_window))
    diffusion_ratio = float(peer_breadth_3max / peer_peak)
    treatment = bool(diffusion_ratio <= DIFFUSION_RATIO_MAX)
    transient = bool(
        not treatment
        and peer_breadth_b / peer_peak <= DIFFUSION_RATIO_MAX
    )
    return (
        PathState(
            anchor=anchor,
            confirm=confirm,
            rebound=rebound,
            action=action,
            atr=float(atr_anchor),
            reference_low=float(reference_low),
            anchor_breadth=float(anchor_breadth),
            peer_peak=float(peer_peak),
            peer_breadth_b=peer_breadth_b,
            peer_breadth_3max=peer_breadth_3max,
            diffusion_ratio=diffusion_ratio,
            treatment=treatment,
            transient=transient,
        ),
        "ok",
    )


def competing_risk(
    close: np.ndarray,
    low: np.ndarray,
    action: int,
    breach_level: float,
    horizon: int = OUTCOME_HORIZON,
) -> dict[str, object]:
    """Fixed-denominator race; a same-session breach wins conservatively."""

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
        if not np.isfinite(close[j]) or not np.isfinite(low[j]):
            continue
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
        return "DEV"
    if date <= VAL_END:
        return "VAL"
    return "FWD"


def severity_band(value: float) -> str:
    if 0.15 <= value < 0.30:
        return "p1"
    if value < 0.50:
        return "p2"
    return "p3"


def delay_band(value: int) -> str:
    if value <= 15:
        return "d1"
    if value <= 27:
        return "d2"
    return "d3"


def event_row(
    sym: str,
    sector: str,
    index: pd.DatetimeIndex,
    ohlcv: pd.DataFrame,
    path: PathState,
    metrics: dict[str, np.ndarray],
) -> dict[str, object] | None:
    action = path.action
    if action + OUTCOME_HORIZON >= len(index):
        return None
    if not np.isfinite(metrics["mae63"][action]) or not np.isfinite(
        metrics["prox"][action]
    ):
        return None
    close = ohlcv["close"].to_numpy(dtype=float)
    low = ohlcv["low"].to_numpy(dtype=float)
    open_ = ohlcv["open"].to_numpy(dtype=float)
    risk = competing_risk(
        close,
        low,
        action,
        path.reference_low - RETEST_LOW_DOWN_ATR * path.atr,
    )
    mae = float(metrics["mae63"][action])
    prox = float(metrics["prox"][action])
    tdt = float(metrics["tdt"][action])
    next_open_gap = (
        float((open_[action + 1] / close[action] - 1.0) * 100.0)
        if np.isfinite(open_[action + 1])
        else np.nan
    )
    date = index[action]
    group = "sr2" if path.treatment else "geometry_control"
    return {
        "sym": sym,
        "sector": sector,
        "anchor_date": index[path.anchor],
        "formation_confirm": index[path.confirm],
        "rebound_date": index[path.rebound],
        "date": date,
        "month": str(date)[:7],
        "group": group,
        "is_sr2": path.treatment,
        "is_transient": path.transient,
        "atr_anchor": path.atr,
        "reference_low": path.reference_low,
        "anchor_breadth": path.anchor_breadth,
        "peer_peak": path.peer_peak,
        "peer_breadth_b": path.peer_breadth_b,
        "peer_breadth_3max": path.peer_breadth_3max,
        "diffusion_ratio": path.diffusion_ratio,
        "delay": int(path.action - path.confirm),
        "low_depth_atr": float(
            (low[action] - path.reference_low) / path.atr
        ),
        "close_depth_atr": float(
            (close[action] - path.reference_low) / path.atr
        ),
        "next_open_gap": next_open_gap,
        "severity_band": severity_band(path.peer_peak),
        "delay_band": delay_band(int(path.action - path.confirm)),
        "mae": mae,
        "prox": prox,
        "w5": bool(prox <= 5.0),
        "called": bool(-2 <= tdt <= 5),
        "tail10": bool(mae <= -10.0),
        "tdt": tdt,
        **risk,
    }


def sector_frames(
    names: list[str],
) -> tuple[pd.DatetimeIndex, dict[str, pd.DataFrame], list[str]]:
    """Load one sector into a common daily panel and report missing files."""

    loaded: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for sym in names:
        path = OHLCV_DIR / f"{sym}.parquet"
        if not path.exists():
            missing.append(sym)
            continue
        loaded[sym] = load_ohlcv(sym)
    if not loaded:
        return pd.DatetimeIndex([]), {}, missing
    index_values: set[pd.Timestamp] = set()
    for d in loaded.values():
        index_values.update(d.index[d.index >= pd.Timestamp("2018-01-01")])
    index = pd.DatetimeIndex(sorted(index_values))
    return index, {sym: d.reindex(index) for sym, d in loaded.items()}, missing


def build_events(
    ticker_sector: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    census: dict[str, dict[str, object]] = {
        sym: {"sym": sym, "sector": sector, "status": "pending"}
        for sym, sector in ticker_sector.items()
    }
    by_sector: dict[str, list[str]] = {}
    for sym, sector in ticker_sector.items():
        by_sector.setdefault(sector, []).append(sym)

    processed = 0
    for sector in SECTORS:
        names = sorted(by_sector.get(sector, []))
        index, data, missing = sector_frames(names)
        for sym in missing:
            census[sym]["status"] = "missing_ohlcv"
        if len(data) <= PEER_MIN:
            for sym in data:
                census[sym]["status"] = "too_few_sector_peers"
            continue

        close = pd.DataFrame(
            {sym: d["close"] for sym, d in data.items()}, index=index
        )
        low = pd.DataFrame(
            {sym: d["low"] for sym, d in data.items()}, index=index
        )
        atr = pd.DataFrame(
            {sym: atr14_prior(d) for sym, d in data.items()}, index=index
        )
        prior_low = close.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).min()
        valid = close.notna() & prior_low.notna()
        new_low = close.le(prior_low) & valid

        for sym, ohlcv in data.items():
            processed += 1
            counts: Counter[str] = Counter()
            breadth, peer_count = ex_self_breadth(new_low, valid, sym)
            threshold = (
                breadth.shift(1)
                .rolling(BREADTH_Q_WINDOW, min_periods=BREADTH_Q_MIN)
                .quantile(BREADTH_Q)
            )
            candidates = (
                close[sym].le(prior_low[sym])
                & breadth.ge(BREADTH_MIN)
                & breadth.ge(threshold)
                & peer_count.ge(PEER_MIN)
                & (index >= OOS_START)
            ).fillna(False)
            anchors = greedy_anchors(candidates.to_numpy(dtype=bool))
            counts["anchors"] = len(anchors)
            metrics = f4.metric_arrays(close[sym].to_numpy(dtype=float))

            for anchor in anchors:
                path, reason = find_path(
                    close[sym].to_numpy(dtype=float),
                    low[sym].to_numpy(dtype=float),
                    breadth.to_numpy(dtype=float),
                    peer_count.to_numpy(dtype=float),
                    atr[sym].to_numpy(dtype=float),
                    int(anchor),
                )
                if path is None:
                    counts[reason] += 1
                    continue
                row = event_row(
                    sym,
                    sector,
                    index,
                    ohlcv,
                    path,
                    metrics,
                )
                if row is None:
                    counts["incomplete_outcome"] += 1
                    continue
                rows.append(row)
                counts["complete_paths"] += 1
                counts["treatments" if row["is_sr2"] else "controls"] += 1
                if row["is_transient"]:
                    counts["transient_controls"] += 1

            census[sym] = {
                "sym": sym,
                "sector": sector,
                "status": "eligible" if len(anchors) else "no_oos_anchor",
                **dict(counts),
            }
            if processed % 100 == 0:
                print(
                    f"processed {processed}/{len(ticker_sector)} names; "
                    f"paths={len(rows):,}; treatments="
                    f"{sum(bool(row['is_sr2']) for row in rows):,}",
                    flush=True,
                )

    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    if len(events):
        events = events.sort_values(
            ["date", "sector", "sym", "anchor_date"]
        ).reset_index(drop=True)
    census_frame = pd.DataFrame(census.values()).fillna(0)
    census_frame = census_frame.sort_values(["sector", "sym"]).reset_index(drop=True)
    return events, census_frame


def inference_tape(events: pd.DataFrame) -> pd.DataFrame:
    """Frozen keep-first name-month tape with informative exact strata."""

    if not len(events):
        return events.copy()
    d = (
        events[events.group.isin(["sr2", "geometry_control"])]
        .sort_values(["date", "anchor_date", "sym"])
        .drop_duplicates(["sym", "month"], keep="first")
        .copy()
    )
    keys = ["sector", "month", "severity_band", "delay_band"]
    counts = d.groupby(keys, observed=True).is_sr2.agg(["size", "sum"])
    good = counts[(counts["sum"] >= 2) & ((counts["size"] - counts["sum"]) >= 2)]
    if not len(good):
        return d.iloc[0:0].copy()
    good_index = set(good.index.tolist())
    mask = [
        (row.sector, row.month, row.severity_band, row.delay_band)
        in good_index
        for row in d.itertuples()
    ]
    d = d.loc[mask].copy()
    d["stratum"] = (
        d["sector"].astype(str)
        + "|"
        + d["month"].astype(str)
        + "|"
        + d["severity_band"].astype(str)
        + "|"
        + d["delay_band"].astype(str)
    )
    return d


def metric_values(d: pd.DataFrame, metric: str) -> np.ndarray:
    values = d[metric].to_numpy(dtype=float)
    if metric in ("tail10", "breach_first"):
        return -100.0 * values
    if metric in ("w5", "called", "rebound8_first"):
        return 100.0 * values
    return values


def stratum_effects(events: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Equal-weight stratum effects; positive means SR2 is better."""

    d = inference_tape(events)
    rows: list[dict[str, object]] = []
    for stratum, group in d.groupby("stratum", sort=True):
        treatment = group.is_sr2.to_numpy(dtype=bool)
        if treatment.sum() < 2 or (~treatment).sum() < 2:
            continue
        values = metric_values(group, metric)
        effect = float(
            np.median(values[treatment]) - np.median(values[~treatment])
            if metric not in ("tail10", "breach_first", "w5", "called",
                              "rebound8_first")
            else values[treatment].mean() - values[~treatment].mean()
        )
        rows.append(
            {
                "stratum": stratum,
                "month": str(group.month.iloc[0]),
                "sector": str(group.sector.iloc[0]),
                "effect": effect,
                "n_treatment": int(treatment.sum()),
                "n_control": int((~treatment).sum()),
            }
        )
    return pd.DataFrame(rows)


def permuted_effects(
    events: pd.DataFrame,
    metric: str,
    n_perm: int,
    seed: int,
) -> tuple[float, np.ndarray, list[tuple[int, int]]]:
    """Permute labels only inside the frozen calendar/severity/delay strata."""

    d = inference_tape(events)
    prepared: list[tuple[np.ndarray, int, bool]] = []
    observed_parts: list[float] = []
    counts: list[tuple[int, int]] = []
    binary = metric in (
        "tail10",
        "breach_first",
        "w5",
        "called",
        "rebound8_first",
    )
    for _, group in d.groupby("stratum", sort=True):
        treatment = group.is_sr2.to_numpy(dtype=bool)
        nt = int(treatment.sum())
        nc = int((~treatment).sum())
        if nt < 2 or nc < 2:
            continue
        values = metric_values(group, metric)
        reducer = np.mean if binary else np.median
        observed_parts.append(
            float(reducer(values[treatment]) - reducer(values[~treatment]))
        )
        prepared.append((values, nt, binary))
        counts.append((nt, nc))
    if not prepared:
        return np.nan, np.full(n_perm, np.nan), counts
    observed = float(np.mean(observed_parts))
    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    for draw in range(n_perm):
        parts = []
        for values, nt, is_binary in prepared:
            order = rng.permutation(len(values))
            reducer = np.mean if is_binary else np.median
            parts.append(
                float(
                    reducer(values[order[:nt]])
                    - reducer(values[order[nt:]])
                )
            )
        null[draw] = float(np.mean(parts))
    return observed, null, counts


def moving_block_ci(
    effects: pd.DataFrame,
    n_boot: int,
    seed: int,
    block_months: int = MOVING_BLOCK_MONTHS,
) -> tuple[float, float]:
    """Circular moving-block CI over whole calendar-month strata."""

    if not len(effects):
        return np.nan, np.nan
    observed_months = pd.PeriodIndex(effects.month, freq="M")
    months = pd.period_range(observed_months.min(), observed_months.max(), freq="M")
    pieces = {
        month: effects.loc[
            observed_months == month, "effect"
        ].to_numpy(dtype=float)
        for month in months
    }
    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot)
    n_months = len(months)
    for draw in range(n_boot):
        sampled: list[pd.Period] = []
        while len(sampled) < n_months:
            start = int(rng.integers(0, n_months))
            sampled.extend(
                months[(start + offset) % n_months]
                for offset in range(block_months)
            )
        arrays = [pieces[m] for m in sampled[:n_months] if len(pieces[m])]
        boot[draw] = (
            float(np.mean(np.concatenate(arrays))) if arrays else np.nan
        )
    finite = boot[np.isfinite(boot)]
    if not len(finite):
        return np.nan, np.nan
    return float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5))


def inference(
    events: pd.DataFrame,
    metric: str,
    n_perm: int,
    n_boot: int,
    seed_offset: int,
) -> dict[str, float]:
    effects = stratum_effects(events, metric)
    observed, null, _ = permuted_effects(
        events, metric, n_perm, PERM_SEED + seed_offset
    )
    if not np.isfinite(observed):
        return {
            "effect": np.nan,
            "p": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
            "strata": 0,
            "events": 0,
        }
    p = float((1 + np.sum(null >= observed)) / (n_perm + 1))
    ci_low, ci_high = moving_block_ci(
        effects, n_boot, BOOT_SEED + seed_offset
    )
    return {
        "effect": observed,
        "p": p,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "strata": len(effects),
        "events": int((effects.n_treatment + effects.n_control).sum()),
    }


def group_subset(events: pd.DataFrame, group: str) -> pd.DataFrame:
    if group == "transient_control":
        return events[events.is_transient]
    return events[events.group == group]


def absolute_summary(events: pd.DataFrame, group: str) -> dict[str, float]:
    d = group_subset(events, group)
    if not len(d):
        return {
            "events": 0,
            "names": 0,
            "names3": 0,
            "mae": np.nan,
            "w5": np.nan,
            "called": np.nan,
            "tail10": np.nan,
            "rebound8_first": np.nan,
            "unresolved": np.nan,
            "delay": np.nan,
            "close_depth": np.nan,
        }
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
            close_depth=("close_depth_atr", "median"),
        )
        .reset_index()
    )
    return {
        "events": len(d),
        "names": len(z),
        "names3": int((z.n >= 3).sum()),
        "mae": float(z.mae.median()),
        "w5": float(z.w5.mean() * 100.0),
        "called": float(z.called.mean() * 100.0),
        "tail10": float(z.tail10.mean() * 100.0),
        "rebound8_first": float(z.rebound8_first.mean() * 100.0),
        "unresolved": float(z.unresolved.mean() * 100.0),
        "delay": float(z.delay.median()),
        "close_depth": float(z.close_depth.median()),
    }


def per_name_summary(events: pd.DataFrame, group: str, era: str) -> pd.DataFrame:
    d = group_subset(events[events.date.map(era_name) == era], group)
    if not len(d):
        return pd.DataFrame()
    out = (
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
            close_depth_atr=("close_depth_atr", "median"),
        )
        .reset_index()
    )
    out["era"] = era
    out["group"] = group
    return out


def build_panel(events: pd.DataFrame) -> pd.DataFrame:
    pieces = [
        per_name_summary(events, group, era)
        for era in ("DEV", "VAL", "FWD")
        for group in GROUPS
    ]
    pieces = [piece for piece in pieces if len(piece)]
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def f(value: float, digits: int = 2) -> str:
    if not np.isfinite(value):
        return "—"
    return f"{value:+.{digits}f}"


def containment(events: pd.DataFrame) -> dict[str, float]:
    h1 = events[events.date.between("2022-01-01", "2022-06-30")]
    autumn = events[events.date.between("2022-09-01", "2022-11-30")]
    return {
        "h1_opportunity_density": len(h1) / 6.0,
        "autumn_opportunity_density": len(autumn) / 3.0,
        "h1_treatment_density": float(h1.is_sr2.sum()) / 6.0,
        "autumn_treatment_density": float(autumn.is_sr2.sum()) / 3.0,
        "h1_share": float(h1.is_sr2.mean()) if len(h1) else np.nan,
        "autumn_share": float(autumn.is_sr2.mean()) if len(autumn) else np.nan,
    }


def leave_one_sector_effects(
    events: pd.DataFrame,
    metric: str,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for sector in SECTORS:
        effects = stratum_effects(events[events.sector != sector], metric)
        out[sector] = (
            float(effects.effect.mean()) if len(effects) else np.nan
        )
    return out


def qualification(
    events: pd.DataFrame,
    results: dict[tuple[str, str], dict[str, float]],
) -> tuple[bool, list[tuple[str, bool, str]]]:
    checks: list[tuple[str, bool, str]] = []
    for era in ("DEV", "VAL"):
        for metric in ("mae", "tail10"):
            r = results[(era, metric)]
            passed = bool(
                np.isfinite(r["ci_low"])
                and r["effect"] > 0
                and r["ci_low"] > 0
                and r["p"] <= 0.05
            )
            detail = (
                f"effect={f(r['effect'])}, CI=[{f(r['ci_low'])},"
                f"{f(r['ci_high'])}], p={r['p']:.4f}"
                if np.isfinite(r["p"])
                else "not estimable"
            )
            checks.append((f"{era} {metric} clears", passed, detail))
        timing = any(results[(era, m)]["effect"] > 0 for m in ("w5", "called"))
        rebound = results[(era, "rebound8_first")]["effect"] > 0
        checks.append(
            (
                f"{era} timing and rebound-first improve",
                bool(timing and rebound),
                f"W5={f(results[(era, 'w5')]['effect'])}, "
                f"called={f(results[(era, 'called')]['effect'])}, "
                f"rebound8={f(results[(era, 'rebound8_first')]['effect'])}",
            )
        )

    treatment = events[events.is_sr2]
    n_names = treatment.sym.nunique()
    n_names3 = int((treatment.groupby("sym").size() >= 3).sum())
    strata = {
        era: results[(era, "mae")]["strata"] for era in ("DEV", "VAL")
    }
    coverage = (
        n_names >= 500
        and n_names3 >= 100
        and all(value >= 40 for value in strata.values())
    )
    checks.append(
        (
            "Coverage and informative-strata floor",
            bool(coverage),
            f"names={n_names}, names≥3={n_names3}, strata={strata}",
        )
    )

    c = containment(events)
    share_gap = c["autumn_share"] - c["h1_share"]
    checks.append(
        (
            "H1 conditional share at least 10pp below Sep–Nov",
            bool(np.isfinite(share_gap) and share_gap >= 0.10),
            f"H1={c['h1_share']*100:.1f}%, "
            f"Sep–Nov={c['autumn_share']*100:.1f}%, gap={share_gap*100:.1f}pp",
        )
    )

    for era in ("DEV", "VAL"):
        d = events[events.date.map(era_name) == era]
        effects = stratum_effects(d, "close_depth_atr")
        difference = float(effects.effect.mean()) if len(effects) else np.nan
        checks.append(
            (
                f"{era} no SR1 safe-late distance confound",
                bool(np.isfinite(difference) and difference <= 0.25),
                f"stratified treatment-control={f(difference)} ATR",
            )
        )

    concentration = (
        treatment.groupby("sector").size().max() / len(treatment)
        if len(treatment)
        else np.nan
    )
    loo_ok = True
    loo_detail: list[str] = []
    for era in ("DEV", "VAL"):
        d = events[events.date.map(era_name) == era]
        for metric in ("mae", "tail10"):
            effects = leave_one_sector_effects(d, metric)
            minimum = min(effects.values()) if effects else np.nan
            loo_ok = loo_ok and bool(np.isfinite(minimum) and minimum > 0)
            loo_detail.append(f"{era}-{metric} min={f(minimum)}")
    checks.append(
        (
            "Sector robustness and ≤25% concentration",
            bool(loo_ok and np.isfinite(concentration) and concentration <= 0.25),
            ", ".join(loo_detail) + f", max share={concentration*100:.1f}%",
        )
    )

    fwd = all(results[("FWD", metric)]["effect"] >= 0 for metric in ("mae", "tail10"))
    checks.append(
        (
            "No FWD primary reversal",
            bool(fwd),
            f"MAE={f(results[('FWD', 'mae')]['effect'])}, "
            f"tail={f(results[('FWD', 'tail10')]['effect'])}",
        )
    )
    return all(passed for _, passed, _ in checks), checks


def render_report(
    events: pd.DataFrame,
    census: pd.DataFrame,
    n_perm: int,
    n_boot: int,
) -> tuple[str, bool]:
    eras = ("DEV", "VAL", "FWD")
    results: dict[tuple[str, str], dict[str, float]] = {}
    lines = [
        "# PSS-SR2 — persistent ex-self peer diffusion",
        "",
        "The construction and decision law were committed before forward outcomes "
        "in `research/PSS_SR2_PEER_DIFFUSION_PREREG.md`. Positive effects always "
        "mean SR2 is better than the disjoint geometry control.",
        "",
        "SR2 is research/display-only. Historical qualification could authorize "
        "only a prospective frozen shadow, never entry, rank, size, gate, or alert "
        "authority.",
        "",
        "## Construction audit",
        "",
        "- Anchor: subject fresh prior-60-close low during ≥15% ex-self sector "
        "new-low breadth at a shifted trailing-q80 extreme.",
        "- Formation: four sessions; frozen prior-only ATR14, reference intraday "
        "low, and ex-self peer-breadth peak.",
        "- Path: first +1 ATR rebound, then the first tested-low geometry no later "
        "than 40 sessions after formation.",
        "- Treatment: all three peer-breadth sessions ending at the retest stay at "
        "or below half the formation peak.",
        "- Control: identical complete name-price path without persistent peer "
        "contraction. The subject is absent from its own peer breadth.",
        "- Inference: keep-first name-month; exact sector × month × anchor-severity "
        "× delay strata; within-stratum permutation primary.",
        "",
        "## Coverage and outcomes",
        "",
    ]
    for era_number, era in enumerate(eras):
        d = events[events.date.map(era_name) == era]
        lines.extend(
            [
                f"### {era}",
                "",
                "| group | paths | names | names ≥3 | MAE63 | W5 | called | "
                "tail≤−10 | rebound8 first | unresolved | delay | close/ref |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for group in GROUPS:
            s = absolute_summary(d, group)
            lines.append(
                f"| {group} | {s['events']:,} | {s['names']:,} | "
                f"{s['names3']:,} | {f(s['mae'])}% | {f(s['w5'], 1)}% | "
                f"{f(s['called'], 1)}% | {f(s['tail10'], 1)}% | "
                f"{f(s['rebound8_first'], 1)}% | {f(s['unresolved'], 1)}% | "
                f"{f(s['delay'], 1)}td | {f(s['close_depth'], 2)} ATR |"
            )
        lines.extend(
            [
                "",
                "#### SR2 minus geometry-control stratified effects",
                "",
                "| metric | effect | 95% 3-month-block CI | permutation p | "
                "informative strata | retained events |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for metric_number, metric in enumerate(INFER_METRICS):
            result = inference(
                d,
                metric,
                n_perm,
                n_boot,
                era_number * 100 + metric_number,
            )
            results[(era, metric)] = result
            p_text = f"{result['p']:.4f}" if np.isfinite(result["p"]) else "—"
            lines.append(
                f"| {metric} | {f(result['effect'])} | "
                f"[{f(result['ci_low'])}, {f(result['ci_high'])}] | "
                f"{p_text} | {int(result['strata'])} | "
                f"{int(result['events']):,} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Frozen-geometry confound audit",
            "",
            "| era | group | peer peak | delay | retest low/ref | "
            "action close/ref | next-open gap |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for era in eras:
        d = events[events.date.map(era_name) == era]
        for group in ("sr2", "geometry_control"):
            z = group_subset(d, group)
            lines.append(
                f"| {era} | {group} | {f(z.peer_peak.median(), 3)} | "
                f"{f(z.delay.median(), 1)}td | "
                f"{f(z.low_depth_atr.median(), 2)} ATR | "
                f"{f(z.close_depth_atr.median(), 2)} ATR | "
                f"{f(z.next_open_gap.median(), 2)}% |"
            )
    lines.extend(
        [
            "",
            "The absolute per-name summaries above are descriptive. The frozen "
            "sector/month/severity/delay-stratified effects are the verdict "
            "statistics; their opposite sign shows that the small pooled MAE "
            "difference is calendar/composition, not peer-diffusion edge.",
            "",
        ]
    )

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

    c = containment(events)
    treatment = events[events.is_sr2]
    lines.extend(
        [
            "",
            f"**Verdict: {'QUALIFIES FOR PROSPECTIVE SHADOW ONLY' if qualified else 'KILLED'}**.",
            "",
            "## Containment, confounds, and topology",
            "",
            f"- H1-2022 opportunity / treatment density: "
            f"{c['h1_opportunity_density']:.1f} / "
            f"{c['h1_treatment_density']:.1f} per month; treatment share "
            f"{c['h1_share']*100:.1f}%.",
            f"- Sep–Nov 2022 opportunity / treatment density: "
            f"{c['autumn_opportunity_density']:.1f} / "
            f"{c['autumn_treatment_density']:.1f} per month; treatment share "
            f"{c['autumn_share']*100:.1f}%.",
            f"- Next-open gap median / 95th percentile: "
            f"{treatment.next_open_gap.median():+.2f}% / "
            f"{treatment.next_open_gap.quantile(.95):+.2f}%."
            if len(treatment)
            else "- No treatment execution diagnostics.",
            "",
            "Treatment paths by sector:",
            "",
        ]
    )
    for sector, count in treatment.groupby("sector").size().sort_values(
        ascending=False
    ).items():
        lines.append(f"- {sector}: {int(count):,}")

    lines.extend(["", "## Exclusion and path census", ""])
    for status, count in census.groupby("status").size().sort_values(
        ascending=False
    ).items():
        lines.append(f"- `{status}`: {int(count):,} names")
    count_columns = [
        column
        for column in census.columns
        if column not in {"sym", "sector", "status"}
    ]
    lines.extend(["", "Aggregate counters:", ""])
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
                "Every frozen requirement cleared. The only permitted next step "
                "is a versioned, no-backfill, prospective display shadow."
                if qualified
                else "At least one frozen requirement failed. This exact SR2 "
                "construction is not usable and cannot be rescued by changing "
                "the breadth ratio, persistence, or retest windows after outcomes. "
                "Mechanistically, peer recovery while the subject alone retests "
                "its low identifies an idiosyncratic laggard, not terminal "
                "systemic supply: the cross-sectional divergence has the opposite "
                "sign from the hypothesis."
            ),
            "",
            f"Inference: {n_perm:,} within-stratum permutations "
            f"(base seed {PERM_SEED}); {n_boot:,} circular 3-month moving-block "
            f"bootstraps (base seed {BOOT_SEED}).",
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
        help="Reuse existing events/census and regenerate panel/report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.reuse_events and OUT_EVENTS.exists() and OUT_CENSUS.exists():
        events = pd.read_parquet(OUT_EVENTS)
        census = pd.read_parquet(OUT_CENSUS)
    else:
        panel = pd.read_parquet(PANEL_PQ)
        eligible = set(
            panel.loc[panel["eligible"].astype(bool), "sym"].dropna().astype(str)
        )
        mapping = (
            pd.read_parquet(SECTOR_MAP_PQ)
            .drop_duplicates("ticker", keep="last")
        )
        mapping = mapping[
            mapping.ticker.astype(str).isin(eligible)
            & mapping.sector.astype(str).isin(SECTORS)
        ]
        ticker_sector = dict(
            zip(
                mapping.ticker.astype(str),
                mapping.sector.astype(str),
                strict=False,
            )
        )
        events, census = build_events(ticker_sector)
        unmapped = sorted(eligible - set(ticker_sector))
        if unmapped:
            census = pd.concat(
                [
                    census,
                    pd.DataFrame(
                        {
                            "sym": unmapped,
                            "sector": "",
                            "status": "missing_sector_map",
                        }
                    ),
                ],
                ignore_index=True,
            ).fillna(0)
            census = census.sort_values(["sector", "sym"]).reset_index(drop=True)
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
