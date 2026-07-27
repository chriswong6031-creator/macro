#!/usr/bin/env python3
"""Outcome-blind feasibility census for PSS-SR3.

This module deliberately has no outcome loader, trough metric, forward-return
calculation, or import from an outcome-bearing research harness.  It may inspect
only information observable through each proposed action close:

* subject and same-sector peer OHLC;
* prior-only ATR;
* shifted trailing new-low breadth used to form the stress anchor;
* subject recovery/hold geometry; and
* peer recovery from each peer's own same-anchor formation low.

The printed grid is a construction/coverage census, not an outcome trial.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PANEL_PQ = ROOT / "data/research/ptt_w1_panel.parquet"
OHLCV_DIR = ROOT / "data/baskets/ohlcv"
SECTOR_MAP_PQ = ROOT / "data/breadth/ticker_sectors.parquet"

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

PATH_MAX = 30
SUBJECT_PERSISTENCE = 3
SUBJECT_HOLD_ATR = 0.50
SUBJECT_RECOVERY_ATR = 1.00
SUBJECT_MAX_ATR = 1.75
SUBJECT_BREACH_ATR = 0.50
OUTCOME_COMPLETENESS_ONLY = 63

PEER_PERSISTENCE = 3
PEER_RECOVERY_ATR_GRID = (0.25, 0.50, 0.75)
PEER_PARTICIPATION_GRID = (0.50, 0.60, 0.70)
PEER_TREND_LOOKBACK_GRID = (3, 5)
JOINT_RECOVERY_ATR = 0.50
JOINT_PARTICIPATION_GRID = (0.40, 0.50, 0.60)

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


@dataclass(frozen=True)
class RecoveryPath:
    """Observable anchor-to-held-recovery path with no outcome fields."""

    sym: str
    sector: str
    anchor: int
    confirm: int
    action: int
    atr: float
    reference_low: float
    anchor_breadth: float
    peer_peak: float
    close_depth_atr: float
    delay: int
    peer_recovery_min: dict[str, float]


def clean_index(frame: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    frame = frame.copy()
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def load_ohlcv(sym: str) -> pd.DataFrame:
    frame = clean_index(pd.read_parquet(OHLCV_DIR / f"{sym}.parquet"))
    return frame[["open", "high", "low", "close"]].astype(float)


def atr14_prior(frame: pd.DataFrame) -> pd.Series:
    prior_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prior_close).abs(),
            (frame["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(ATR_WINDOW, min_periods=ATR_WINDOW).mean().shift(1)


def greedy_anchors(candidate: np.ndarray) -> np.ndarray:
    accepted: list[int] = []
    next_allowed = 0
    for index in np.flatnonzero(np.asarray(candidate, dtype=bool)):
        if index >= next_allowed:
            accepted.append(int(index))
            next_allowed = int(index) + ANCHOR_COOLDOWN + 1
    return np.asarray(accepted, dtype=int)


def ex_self_breadth(
    new_low: pd.DataFrame,
    valid: pd.DataFrame,
    sym: str,
) -> tuple[pd.Series, pd.Series]:
    numerator = new_low.sum(axis=1) - new_low[sym].astype(int)
    denominator = valid.sum(axis=1) - valid[sym].astype(int)
    breadth = numerator / denominator.where(denominator > 0)
    return breadth.astype(float), denominator.astype(float)


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
    if value <= 10:
        return "d1"
    if value <= 20:
        return "d2"
    return "d3"


def distance_band(value: float) -> str:
    if value < 1.25:
        return "x1"
    if value < 1.50:
        return "x2"
    return "x3"


def sector_frames(
    names: list[str],
) -> tuple[pd.DatetimeIndex, dict[str, pd.DataFrame], list[str]]:
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
    values: set[pd.Timestamp] = set()
    for frame in loaded.values():
        values.update(frame.index[frame.index >= pd.Timestamp("2018-01-01")])
    index = pd.DatetimeIndex(sorted(values))
    return index, {sym: frame.reindex(index) for sym, frame in loaded.items()}, missing


def first_subject_recovery(
    close: np.ndarray,
    low: np.ndarray,
    anchor: int,
    atr_anchor: float,
    reference_low: float,
) -> int | None:
    """First observable three-session held recovery, capped near the low."""

    confirm = anchor + FORMATION_DAYS - 1
    latest = min(len(close) - 1, confirm + PATH_MAX)
    start = confirm + SUBJECT_PERSISTENCE - 1
    for action in range(start, latest + 1):
        window = slice(action - SUBJECT_PERSISTENCE + 1, action + 1)
        closes = close[window]
        lows = low[window]
        if not np.isfinite(closes).all() or not np.isfinite(lows).all():
            continue
        if np.min(closes) < reference_low + SUBJECT_HOLD_ATR * atr_anchor:
            continue
        if np.min(lows) < reference_low - SUBJECT_BREACH_ATR * atr_anchor:
            continue
        depth = (close[action] - reference_low) / atr_anchor
        if SUBJECT_RECOVERY_ATR <= depth <= SUBJECT_MAX_ATR:
            return action
    return None


def peer_recovery_minima(
    close: pd.DataFrame,
    low: pd.DataFrame,
    atr: pd.DataFrame,
    sym: str,
    anchor: int,
    action: int,
) -> tuple[dict[str, float] | None, str]:
    """Persistent affirmative peer recovery from peer-specific formation lows."""

    confirm = anchor + FORMATION_DAYS - 1
    peer_reference = low.iloc[anchor : confirm + 1].min(axis=0)
    peer_atr = atr.iloc[anchor]
    valid_reference = (
        peer_reference.notna()
        & peer_atr.notna()
        & peer_atr.gt(0)
    )
    valid_reference.loc[sym] = False
    if int(valid_reference.sum()) < PEER_MIN:
        return None, "peer_reference_count"

    minima: dict[str, float] = {}
    start = action - PEER_PERSISTENCE + 1
    for distance in PEER_RECOVERY_ATR_GRID:
        breadth_values: list[float] = []
        threshold = peer_reference + distance * peer_atr
        for position in range(start, action + 1):
            valid = valid_reference & close.iloc[position].notna()
            if int(valid.sum()) < PEER_MIN:
                return None, "peer_action_count"
            recovered = close.iloc[position].ge(threshold) & valid
            breadth_values.append(float(recovered.sum() / valid.sum()))
        minima[f"level_{distance:.2f}"] = float(min(breadth_values))

    joint_threshold = peer_reference + JOINT_RECOVERY_ATR * peer_atr
    for lookback in PEER_TREND_LOOKBACK_GRID:
        breadth_values = []
        for position in range(start, action + 1):
            prior_position = position - lookback
            if prior_position < 0:
                return None, "peer_trend_history"
            valid = (
                valid_reference
                & close.iloc[position].notna()
                & close.iloc[prior_position].notna()
            )
            if int(valid.sum()) < PEER_MIN:
                return None, "peer_action_count"
            recovered = (
                close.iloc[position].ge(joint_threshold)
                & close.iloc[position].gt(close.iloc[prior_position])
                & valid
            )
            breadth_values.append(float(recovered.sum() / valid.sum()))
        minima[f"joint_{lookback}"] = float(min(breadth_values))
    return minima, "ok"


def build_paths(
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
            {sym: frame["close"] for sym, frame in data.items()},
            index=index,
        )
        low = pd.DataFrame(
            {sym: frame["low"] for sym, frame in data.items()},
            index=index,
        )
        atr = pd.DataFrame(
            {sym: atr14_prior(frame) for sym, frame in data.items()},
            index=index,
        )
        prior_low = close.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).min()
        valid = close.notna() & prior_low.notna()
        new_low = close.le(prior_low) & valid

        for sym in sorted(data):
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

            sym_close = close[sym].to_numpy(dtype=float)
            sym_low = low[sym].to_numpy(dtype=float)
            sym_atr = atr[sym].to_numpy(dtype=float)
            breadth_array = breadth.to_numpy(dtype=float)
            peer_count_array = peer_count.to_numpy(dtype=float)

            for anchor in anchors:
                anchor = int(anchor)
                confirm = anchor + FORMATION_DAYS - 1
                if confirm >= len(index):
                    counts["incomplete_formation"] += 1
                    continue
                formation = slice(anchor, confirm + 1)
                if np.any(peer_count_array[formation] < PEER_MIN):
                    counts["formation_peer_count"] += 1
                    continue
                values = np.asarray(
                    [
                        sym_atr[anchor],
                        np.nanmin(sym_low[formation]),
                        breadth_array[anchor],
                        np.nanmax(breadth_array[formation]),
                    ],
                    dtype=float,
                )
                if not np.isfinite(values).all() or values[0] <= 0:
                    counts["invalid_formation"] += 1
                    continue
                atr_anchor, reference_low, anchor_breadth, peer_peak = values
                action = first_subject_recovery(
                    sym_close,
                    sym_low,
                    anchor,
                    float(atr_anchor),
                    float(reference_low),
                )
                if action is None:
                    counts["no_subject_recovery"] += 1
                    continue
                if action + OUTCOME_COMPLETENESS_ONLY >= len(index):
                    counts["incomplete_horizon"] += 1
                    continue
                minima, reason = peer_recovery_minima(
                    close,
                    low,
                    atr,
                    sym,
                    anchor,
                    action,
                )
                if minima is None:
                    counts[reason] += 1
                    continue
                date = index[action]
                close_depth = float(
                    (sym_close[action] - reference_low) / atr_anchor
                )
                row: dict[str, object] = {
                    "sym": sym,
                    "sector": sector,
                    "anchor_date": index[anchor],
                    "formation_confirm": index[confirm],
                    "date": date,
                    "month": str(date)[:7],
                    "era": era_name(date),
                    "atr_anchor": float(atr_anchor),
                    "reference_low": float(reference_low),
                    "anchor_breadth": float(anchor_breadth),
                    "peer_peak": float(peer_peak),
                    "delay": int(action - confirm),
                    "close_depth_atr": close_depth,
                    "severity_band": severity_band(float(peer_peak)),
                    "delay_band": delay_band(int(action - confirm)),
                    "distance_band": distance_band(close_depth),
                }
                for key, value in minima.items():
                    row[f"peer_recovery_min_{key}"] = value
                rows.append(row)
                counts["complete_paths"] += 1

            census[sym] = {
                "sym": sym,
                "sector": sector,
                "status": "eligible" if len(anchors) else "no_oos_anchor",
                **dict(counts),
            }
            if processed % 100 == 0:
                print(
                    f"processed {processed}/{len(ticker_sector)} names; "
                    f"complete paths={len(rows):,}",
                    flush=True,
                )

    paths = pd.DataFrame(rows)
    if len(paths):
        paths = paths.sort_values(
            ["date", "sector", "sym", "anchor_date"]
        ).reset_index(drop=True)
    census_frame = pd.DataFrame(census.values()).fillna(0)
    return paths, census_frame


def equal_weight_stratified_distance(
    tape: pd.DataFrame,
    label: str,
) -> tuple[float, int, int]:
    keys = ["sector", "month", "severity_band", "delay_band"]
    effects: list[float] = []
    retained = 0
    for _, group in tape.groupby(keys, observed=True):
        treatment = group[group[label]]
        control = group[~group[label]]
        if len(treatment) < 2 or len(control) < 2:
            continue
        effects.append(
            float(
                treatment["close_depth_atr"].median()
                - control["close_depth_atr"].median()
            )
        )
        retained += len(group)
    return (
        float(np.mean(effects)) if effects else np.nan,
        len(effects),
        retained,
    )


def summarize_variant(
    paths: pd.DataFrame,
    distance: float,
    floor: float,
) -> dict[str, object]:
    value_column = f"peer_recovery_min_level_{distance:.2f}"
    label = "_treatment"
    work = paths.copy()
    work[label] = work[value_column].ge(floor)
    treatment = work[work[label]]
    treatment_counts = treatment.groupby("sym", observed=True).size()
    tape = (
        work.sort_values(["date", "anchor_date", "sym"])
        .drop_duplicates(["sym", "month"], keep="first")
        .copy()
    )
    era_stats: dict[str, object] = {}
    for era in ("DEV", "VAL", "FWD"):
        era_tape = tape[tape["era"].eq(era)]
        distance_effect, strata, retained = equal_weight_stratified_distance(
            era_tape,
            label,
        )
        era_stats[f"{era.lower()}_share"] = (
            float(era_tape[label].mean()) if len(era_tape) else np.nan
        )
        era_stats[f"{era.lower()}_strata"] = strata
        era_stats[f"{era.lower()}_retained"] = retained
        era_stats[f"{era.lower()}_distance_diff"] = distance_effect

    h1 = tape[
        tape["date"].between("2022-01-01", "2022-06-30")
    ]
    autumn = tape[
        tape["date"].between("2022-09-01", "2022-11-30")
    ]
    sector_counts = treatment.groupby("sector", observed=True).size()
    return {
        "shape": "level",
        "peer_distance": distance,
        "trend_lookback": 0,
        "floor": floor,
        "paths": len(work),
        "treatments": len(treatment),
        "controls": len(work) - len(treatment),
        "treatment_names": int(treatment["sym"].nunique()),
        "names_ge3": int((treatment_counts >= 3).sum()),
        "h1_share": float(h1[label].mean()) if len(h1) else np.nan,
        "autumn_share": (
            float(autumn[label].mean()) if len(autumn) else np.nan
        ),
        "max_sector_share": (
            float(sector_counts.max() / sector_counts.sum())
            if len(sector_counts)
            else np.nan
        ),
        **era_stats,
    }


def summarize_joint_variant(
    paths: pd.DataFrame,
    lookback: int,
    floor: float,
) -> dict[str, object]:
    value_column = f"peer_recovery_min_joint_{lookback}"
    label = "_treatment"
    work = paths.copy()
    work[label] = work[value_column].ge(floor)
    treatment = work[work[label]]
    treatment_counts = treatment.groupby("sym", observed=True).size()
    tape = (
        work.sort_values(["date", "anchor_date", "sym"])
        .drop_duplicates(["sym", "month"], keep="first")
        .copy()
    )
    era_stats: dict[str, object] = {}
    for era in ("DEV", "VAL", "FWD"):
        era_tape = tape[tape["era"].eq(era)]
        distance_effect, strata, retained = equal_weight_stratified_distance(
            era_tape,
            label,
        )
        era_stats[f"{era.lower()}_share"] = (
            float(era_tape[label].mean()) if len(era_tape) else np.nan
        )
        era_stats[f"{era.lower()}_strata"] = strata
        era_stats[f"{era.lower()}_retained"] = retained
        era_stats[f"{era.lower()}_distance_diff"] = distance_effect

    h1 = tape[tape["date"].between("2022-01-01", "2022-06-30")]
    autumn = tape[tape["date"].between("2022-09-01", "2022-11-30")]
    sector_counts = treatment.groupby("sector", observed=True).size()
    return {
        "shape": "joint",
        "peer_distance": JOINT_RECOVERY_ATR,
        "trend_lookback": lookback,
        "floor": floor,
        "paths": len(work),
        "treatments": len(treatment),
        "controls": len(work) - len(treatment),
        "treatment_names": int(treatment["sym"].nunique()),
        "names_ge3": int((treatment_counts >= 3).sum()),
        "h1_share": float(h1[label].mean()) if len(h1) else np.nan,
        "autumn_share": (
            float(autumn[label].mean()) if len(autumn) else np.nan
        ),
        "max_sector_share": (
            float(sector_counts.max() / sector_counts.sum())
            if len(sector_counts)
            else np.nan
        ),
        **era_stats,
    }


def summarize_final_nested(paths: pd.DataFrame) -> dict[str, object]:
    """Final mechanism comparison: active majority vs stale level majority."""

    level = paths["peer_recovery_min_level_0.50"].ge(0.50)
    active = paths["peer_recovery_min_joint_5"].ge(0.50)
    work = paths[level].copy()
    work["_treatment"] = active[level].to_numpy(dtype=bool)
    treatment = work[work["_treatment"]]
    control = work[~work["_treatment"]]
    treatment_counts = treatment.groupby("sym", observed=True).size()
    tape = (
        work.sort_values(["date", "anchor_date", "sym"])
        .drop_duplicates(["sym", "month"], keep="first")
        .copy()
    )
    era_stats: dict[str, object] = {}
    for era in ("DEV", "VAL", "FWD"):
        era_tape = tape[tape["era"].eq(era)]
        distance_effect, strata, retained = equal_weight_stratified_distance(
            era_tape,
            "_treatment",
        )
        era_stats[f"{era.lower()}_share"] = (
            float(era_tape["_treatment"].mean())
            if len(era_tape)
            else np.nan
        )
        era_stats[f"{era.lower()}_strata"] = strata
        era_stats[f"{era.lower()}_retained"] = retained
        era_stats[f"{era.lower()}_distance_diff"] = distance_effect

    h1 = tape[tape["date"].between("2022-01-01", "2022-06-30")]
    autumn = tape[tape["date"].between("2022-09-01", "2022-11-30")]
    sector_counts = treatment.groupby("sector", observed=True).size()
    return {
        "shape": "FINAL_NESTED",
        "peer_distance": JOINT_RECOVERY_ATR,
        "trend_lookback": 5,
        "floor": 0.50,
        "paths": len(work),
        "treatments": len(treatment),
        "controls": len(control),
        "weak_excluded": int((~level).sum()),
        "treatment_names": int(treatment["sym"].nunique()),
        "names_ge3": int((treatment_counts >= 3).sum()),
        "h1_share": float(h1["_treatment"].mean()) if len(h1) else np.nan,
        "autumn_share": (
            float(autumn["_treatment"].mean()) if len(autumn) else np.nan
        ),
        "max_sector_share": (
            float(sector_counts.max() / sector_counts.sum())
            if len(sector_counts)
            else np.nan
        ),
        **era_stats,
    }


def print_summary(paths: pd.DataFrame, census: pd.DataFrame) -> None:
    print("\nOUTCOME-BLIND PATH CENSUS")
    print(f"paths={len(paths):,}; names={paths['sym'].nunique():,}")
    print("statuses:")
    print(census["status"].value_counts().sort_index().to_string())

    print("\nPERSISTENT PEER-RECOVERY DISTRIBUTIONS")
    quantiles = [0.10, 0.25, 0.50, 0.75, 0.90]
    for distance in PEER_RECOVERY_ATR_GRID:
        column = f"peer_recovery_min_level_{distance:.2f}"
        values = paths[column].quantile(quantiles)
        rendered = ", ".join(
            f"q{int(q * 100)}={values.loc[q]:.3f}" for q in quantiles
        )
        print(f"distance={distance:.2f} ATR: {rendered}")
    for lookback in PEER_TREND_LOOKBACK_GRID:
        column = f"peer_recovery_min_joint_{lookback}"
        values = paths[column].quantile(quantiles)
        rendered = ", ".join(
            f"q{int(q * 100)}={values.loc[q]:.3f}" for q in quantiles
        )
        print(
            f"joint distance={JOINT_RECOVERY_ATR:.2f} ATR, "
            f"trend={lookback}d: {rendered}"
        )

    rows = [
        summarize_variant(paths, distance, floor)
        for distance in PEER_RECOVERY_ATR_GRID
        for floor in PEER_PARTICIPATION_GRID
    ]
    rows.extend(
        summarize_joint_variant(paths, lookback, floor)
        for lookback in PEER_TREND_LOOKBACK_GRID
        for floor in JOINT_PARTICIPATION_GRID
    )
    summary = pd.DataFrame(rows)
    percent_columns = [
        "h1_share",
        "autumn_share",
        "max_sector_share",
        "dev_share",
        "val_share",
        "fwd_share",
    ]
    for column in percent_columns:
        summary[column] = (100.0 * summary[column]).round(1)
    for column in (
        "dev_distance_diff",
        "val_distance_diff",
        "fwd_distance_diff",
    ):
        summary[column] = summary[column].round(3)
    print("\nVARIANT CENSUS — NO OUTCOME VALUES")
    print(summary.to_string(index=False))
    nested = pd.DataFrame([summarize_final_nested(paths)])
    for column in percent_columns:
        nested[column] = (100.0 * nested[column]).round(1)
    for column in (
        "dev_distance_diff",
        "val_distance_diff",
        "fwd_distance_diff",
    ):
        nested[column] = nested[column].round(3)
    print("\nFINAL NESTED MECHANISM CENSUS — NO OUTCOME VALUES")
    print(nested.to_string(index=False))


def load_universe() -> dict[str, str]:
    panel = pd.read_parquet(PANEL_PQ, columns=["sym", "eligible"])
    eligible = set(
        panel.loc[panel["eligible"].astype(bool), "sym"].dropna().astype(str)
    )
    mapping = pd.read_parquet(
        SECTOR_MAP_PQ,
        columns=["ticker", "sector"],
    ).drop_duplicates("ticker", keep="last")
    mapping = mapping[
        mapping["ticker"].astype(str).isin(eligible)
        & mapping["sector"].astype(str).isin(SECTORS)
    ]
    return dict(
        zip(
            mapping["ticker"].astype(str),
            mapping["sector"].astype(str),
            strict=False,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assert-no-outcomes",
        action="store_true",
        help="Retained as an explicit audit flag; this module is outcome-blind.",
    )
    return parser.parse_args()


def main() -> None:
    parse_args()
    ticker_sector = load_universe()
    paths, census = build_paths(ticker_sector)
    if not len(paths):
        raise SystemExit("no complete outcome-blind paths")
    forbidden = {
        "mae",
        "prox",
        "w5",
        "called",
        "tail10",
        "tdt",
        "rebound8_first",
        "breach_first",
        "forward_return",
    }
    overlap = forbidden.intersection(paths.columns)
    if overlap:
        raise RuntimeError(f"outcome columns present: {sorted(overlap)}")
    print_summary(paths, census)


if __name__ == "__main__":
    main()
