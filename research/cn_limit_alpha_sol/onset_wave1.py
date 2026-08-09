#!/usr/bin/env python3
"""Wave-1 CN first-board ONSET research packet (O1 core + O3 challenger).

This runner is deliberately independent of every active Claude Wave-1 lane.  It derives its
panel from nominal ``data/china_stocks_raw/*.parquet`` and a completeness-pinned observed-session
reference (600519.SS).  It is deterministic, context/display-only, and has no live authority.

Clock contract
--------------
* Features are frozen at the exact market session D-1 close.
* The target is the exact common-calendar successor D.  A halt/missing ticker bar on D remains
  an explicit ``missing_halted`` event=0/no-fill/cash=0 candidate in the primary denominator;
  the code never jumps to that ticker's later resumption.
* An auction order may fill only when D open is more than 0.2% below the reconstructed upper
  limit.  At/within the cushion is ``queue_required_no_fill``.
* A D purchase exits no earlier than the exact D+1 open.  Missing exit bars never jump.  Only an
  observed lower-limit-locked open may carry session-by-session to a later exact session.

The full-pop forward seed is honest prospective state only: signal features from the latest
observed close, a future entry session, pending outcome, and three-way fillability.  Retrospective
panel rows are never written into that seed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Iterable, Iterator, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "china_stocks_raw"
SESSION_REF = RAW_DIR / "600519.SS.parquet"
ST_SNAPSHOT = ROOT / "data" / "china_st" / "st_snapshot.parquet"
ZT_POOL = ROOT / "data" / "china_zt_pool" / "pool.parquet"
OUT_JSON = ROOT / "research" / "cn_limit_alpha_sol" / "ONSET_W1_RECEIPT_2026-08-08.json"
OUT_MD = ROOT / "research" / "cn_limit_alpha_sol" / "ONSET_W1_RECEIPT_2026-08-08.md"
OUT_SEED = ROOT / "research" / "cn_limit_alpha_sol" / "ONSET_W1_FORWARD_SEED_2026-08-08.jsonl"

MODEL_VERSION = "cn-onset-w1-sol-2026-08-08.v1"
FORWARD_MODEL_NAMES = (
    "O1_five_axis", "O1_fixed_equal_rank_blend", "O3_washout_transition",
)
EXPECTED_FORWARD_MODEL_VERSIONS = frozenset(
    f"{MODEL_VERSION}:{name}" for name in FORWARD_MODEL_NAMES
)
ANALYSIS_END = "2026-08-07"
CALENDAR_COMPLETENESS_ANCHORS = ("2011-01-04", "2014-12-25", ANALYSIS_END)
EXPECTED_FROZEN_SESSION_COUNT = 3_786
CALENDAR_CONSENSUS_MIN_NAMES = 50
EXPECTED_REFERENCE_POSITIVE_VOLUME_SESSIONS = 3_780
EXPECTED_ANALYSIS_ZERO_VOLUME_ROWS = 133_854
PROSPECTIVE_SEED_SIGNAL_DATE = "2026-08-07"
PROSPECTIVE_SEED_ENTRY_SESSION = "2026-08-10"
LEDGER_JSONL_MAX_SESSIONS = 10
TOLERANT_CUSHION = 0.002
HORIZONS = (1, 3, 5)
TOP_K = (10, 20, 50)
COST_BPS = (0, 30, 60, 100)
MAX_LOWER_CARRY = 20
PURGE_SESSIONS = 10
BATCH_ROWS = 100_000

FEATURE_NAMES = (
    "vol_z20",
    "runup_5",
    "gap_pct",
    "dist_52w_low",
    "consec_up_days",
    "drawdown_20",
    "ma200_dist",
    "reversal_3",
    "washout_x_runup",
    "below_ma200_x_vol",
    "reversal_x_vol",
)
O1_COLS = tuple(range(5))
O3_COLS = tuple(range(len(FEATURE_NAMES)))

# Fixed domain clipping, declared before measurement.  This contains split/corporate-action
# pathologies without learning winsorization thresholds from the replay blocks.
CLIP_BOUNDS = np.asarray([
    (-10.0, 10.0),   # vol_z20
    (-0.80, 2.00),   # runup_5
    (-0.35, 0.35),   # gap_pct
    (0.00, 8.00),    # distance from 52w low
    (0.00, 20.0),    # consecutive up days
    (-0.95, 0.00),   # 20d drawdown
    (-0.90, 4.00),   # distance from MA200
    (0.00, 2.00),    # 3d reversal from local low
    (-1.00, 1.00),   # washout x run-up
    (-10.0, 10.0),   # below-MA200 x volume z
    (-10.0, 10.0),   # reversal x volume z
], dtype=np.float64)

BOARD_NAMES = {0: "main", 1: "chinext", 2: "star"}
ERA_NAMES = {0: "main_10", 1: "chinext_10", 2: "chinext_20", 3: "star_20"}
TARGET_STATE_NAMES = {0: "observed", 1: "missing_halted", 2: "invalid_corporate_action"}
FILL_STATE_NAMES = {0: "fillable_daily_proxy", 1: "queue_required_no_fill", 2: "missing_unknown"}
TERMINAL_FILLABILITY = {
    "fillable_daily_proxy", "queue_required_no_fill", "missing_halted_no_fill",
}
EXIT_STATE_NAMES = {
    0: "resolved_scheduled_open",
    1: "queue_cash",
    2: "missing_cash",
    3: "resolved_after_lower_limit_carry",
    4: "unresolved_lower_limit_carry",
}

SPLIT_NAMES = {0: "outside_or_purged", 1: "train_2011_2019", 2: "calibration_2020_2023",
               3: "historical_replay_after_common_prior", 4: "vendor_audit"}

CONFIG = {
    "authority": "context_display_only",
    "analysis_as_of": ANALYSIS_END,
    "observed_session_clock": "600519.SS_index_complete_2011_plus_anchor_pinned",
    "session_clock_validation": "set_identical_to_raw_index_support_at_least_50_names_no_volume_filter",
    "future_entry_calendar": "frozen_2026_08_10_seed_only_recurring_authoritative_calendar_unbuilt_fail_closed",
    "entry_clock": "score_after_D_minus_1_close_order_D_open",
    "outcome_clock": "exact_common_calendar_successor_D",
    "missing_target_primary": "event_zero_no_fill_cash_zero",
    "candidate_eligibility": "active_nonboard_exact_D_minus_1_bar_all_five_axes_complete_no_future_outcome_filter",
    "limit_definition_primary": "tolerant_close_ge_round2_prev_x_1_plus_width_x_0.998",
    "limit_definition_sensitivity": "strict_close_ge_round2_prev_x_1_plus_width",
    "queue_rule": "D_open_ge_upper_limit_x_0.998_is_no_fill",
    "exit_rule": "D_plus_H_exact_open_lower_limit_carry_only",
    "features": list(FEATURE_NAMES),
    "o1_columns": [FEATURE_NAMES[i] for i in O1_COLS],
    "o3_columns": [FEATURE_NAMES[i] for i in O3_COLS],
    "sector_heat": "excluded_historical_membership_lookahead",
    "splits": {
        "train": ["2011-01-01", "2019-12-31"],
        "calibration": ["2020-01-01", "2023-12-31"],
        "locked_replay": ["2024-01-02", "2026-06-12"],
        "vendor_audit": ["2026-06-15", "2026-08-07"],
        "purged_tail_sessions_each_preceding_block": PURGE_SESSIONS,
        "stress_2015": ["2015-01-01", "2015-12-31"],
    },
    "model": {"kind": "fixed_l2_logistic_newton", "l2": 1e-3, "max_iter": 8,
              "calibration": "platt_on_2020_2023_main", "seed": 20260808},
    "date_block_bootstrap": {"block_sessions": 10, "replicates": 1000, "seed": 20260808},
    "cost_bps_round_trip": list(COST_BPS),
    "horizons_next_open": list(HORIZONS),
    "max_lower_limit_carry_sessions": MAX_LOWER_CARRY,
    "clip_bounds": {name: list(map(float, bound)) for name, bound in zip(FEATURE_NAMES, CLIP_BOUNDS)},
}

UNTESTED_VARIANTS = [
    "recurring nightly probability advancement and grading integration; only contract helpers and one honest seed are built",
    "probability or expected-edge thresholds that permit cash/no-trade days instead of forcing daily top-K names",
    "point-in-time regime-conditioned exposure or a lagged-ecology probability offset",
    "two-archetype washout-versus-momentum mixture for the observed run-up/gap U-shapes",
    "fixed-capital multi-session sleeve allocation for H3/H5 with exit-date PnL attribution",
    "authoritative annual SSE/SZSE future-session calendar for recurring ledger advancement",
    "normalized monthly Parquet probability/grade partitions beyond the capped ten-session JSONL bridge",
    "a production forward runner that loads frozen fitted parameters, discovers the dynamic latest-complete observed session, and never refits nightly or imports the frozen research panel/calendar path",
    "pre-close and intraday near-limit onset entries",
    "actual auction queue depth, order priority, partial fills, and first-5-minute execution",
    "historically complete ST membership, BSE, delisted names, and missing small-cap OHLCV",
    "point-in-time THS concept/sector heat and leader-follower relay",
    "news class, filing surprise, fair-value distance, and A/H/N uncapped rerating oracles",
    "free-float turnover, seal-wall normalization, first-touch time, and seal-break/reseal entries",
    "tree/boosting, survival/hazard, nested feature selection, and family-wise promotion tests",
    "live slippage, commissions, stamp duty, capacity, theme caps, and book-level dependence",
    "exit at close, trailing stops, close-seal state machines, and limit-down release reversal",
    "prospective calibration beyond the single honest seed; ten graded sessions are still required",
]


class IntegrityError(RuntimeError):
    """A deterministic research or forward-ledger contract was violated."""


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _day(value: str | date | pd.Timestamp) -> np.int32:
    return np.datetime64(str(value)[:10], "D").astype(np.int32)


def _iso(day_value: int | np.integer) -> str:
    return str(np.datetime64(int(day_value), "D"))


def board_from_ticker(ticker: str) -> str:
    code = ticker.split(".")[0]
    if code.startswith(("688", "689")):
        return "star"
    if code.startswith(("300", "301", "302")):
        return "chinext"
    if code.startswith(("8", "4", "92")):
        return "bse"
    return "main"


def width_for(board: str, day_values: np.ndarray) -> np.ndarray:
    if board == "star":
        return np.full(len(day_values), 0.20, dtype=np.float64)
    if board == "chinext":
        return np.where(day_values >= _day("2020-08-24"), 0.20, 0.10).astype(np.float64)
    if board == "bse":
        return np.full(len(day_values), 0.30, dtype=np.float64)
    return np.full(len(day_values), 0.10, dtype=np.float64)


def era_code_for(board: str, day_values: np.ndarray) -> np.ndarray:
    if board == "main":
        return np.zeros(len(day_values), dtype=np.uint8)
    if board == "chinext":
        return np.where(day_values >= _day("2020-08-24"), 2, 1).astype(np.uint8)
    return np.full(len(day_values), 3, dtype=np.uint8)


def consecutive_up(close: np.ndarray) -> np.ndarray:
    out = np.zeros(len(close), dtype=np.float32)
    streak = 0
    for i in range(1, len(close)):
        streak = streak + 1 if np.isfinite(close[i]) and np.isfinite(close[i - 1]) and close[i] > close[i - 1] else 0
        out[i] = streak
    return out


def compute_features(frame: pd.DataFrame) -> np.ndarray:
    """Five frozen O1 axes plus six preregistered O3 base/interaction axes."""
    raw_volume = pd.to_numeric(frame["volume"], errors="coerce").astype(float)
    observed = raw_volume > 0
    # A vendor placeholder row with zero volume is a halt/missing observation, not a frozen
    # price/volume feature.  Mask its nominal prices too so a later signal cannot quietly use a
    # forward-filled halt print in run-up, gap, low-distance, or reversal geometry.
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float).where(observed)
    open_ = pd.to_numeric(frame["open"], errors="coerce").astype(float).where(observed)
    volume = raw_volume.where(observed)

    vprev = volume.shift(1)
    vmean = vprev.rolling(20, min_periods=15).mean()
    vstd = vprev.rolling(20, min_periods=15).std(ddof=0)
    vol_z = (volume - vmean) / vstd.replace(0.0, np.nan)
    runup = close / close.shift(5) - 1.0
    gap = open_ / close.shift(1) - 1.0
    dist_low = close / close.rolling(252, min_periods=120).min() - 1.0
    up_days = consecutive_up(close.to_numpy(dtype=float))

    drawdown = close / close.rolling(20, min_periods=15).max() - 1.0
    ma200_dist = close / close.rolling(200, min_periods=120).mean() - 1.0
    reversal = close / close.rolling(3, min_periods=3).min() - 1.0
    washout_runup = (-drawdown.clip(upper=0.0)) * runup
    below_ma_vol = (-ma200_dist.clip(upper=0.0)) * vol_z
    reversal_vol = reversal * vol_z

    out = np.column_stack([
        vol_z.to_numpy(), runup.to_numpy(), gap.to_numpy(), dist_low.to_numpy(), up_days,
        drawdown.to_numpy(), ma200_dist.to_numpy(), reversal.to_numpy(),
        washout_runup.to_numpy(), below_ma_vol.to_numpy(), reversal_vol.to_numpy(),
    ]).astype(np.float32)
    for col, (lo, hi) in enumerate(CLIP_BOUNDS):
        out[:, col] = np.clip(out[:, col], lo, hi)
    return out


def limit_arrays(frame: pd.DataFrame, board: str, days: np.ndarray) -> dict[str, np.ndarray]:
    close = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
    open_ = pd.to_numeric(frame["open"], errors="coerce").to_numpy(dtype=float)
    volume = pd.to_numeric(frame["volume"], errors="coerce").to_numpy(dtype=float)
    prev = np.roll(close, 1)
    prev[0] = np.nan
    widths = width_for(board, days)
    upper = np.round(prev * (1.0 + widths), 2)
    lower = np.round(prev * (1.0 - widths), 2)
    price_valid = (np.isfinite(close) & np.isfinite(open_) & np.isfinite(prev)
                   & (close > 0) & (open_ > 0) & (prev > 0))
    positive_volume = np.isfinite(volume) & (volume > 0)
    valid = price_valid & positive_volume
    exdiv = valid & (np.abs(open_ - prev) / prev > widths * 1.5)
    tolerant = valid & ~exdiv & (close >= upper * (1.0 - TOLERANT_CUSHION))
    strict = valid & ~exdiv & (close >= upper)
    return {"close": close, "open": open_, "volume": volume, "prev": prev,
            "width": widths, "upper": upper, "lower": lower, "price_valid": price_valid,
            "positive_volume": positive_volume, "valid": valid, "exdiv": exdiv,
            "tolerant": tolerant, "strict": strict}


def exact_row_index(raw_days: np.ndarray, wanted_day: int) -> int | None:
    pos = int(np.searchsorted(raw_days, wanted_day))
    return pos if pos < len(raw_days) and int(raw_days[pos]) == int(wanted_day) else None


def simulate_exit(
    *, raw_days: np.ndarray, calendar_days: np.ndarray, day_to_calendar_pos: dict[int, int],
    limits: dict[str, np.ndarray], entry_open: float, target_day: int, horizon: int,
) -> tuple[float, np.uint8, np.uint8]:
    """Return (gross_return_or_zero, exit_state, lower_limit_carry_sessions).

    Missing exact sessions never jump to a later ticker bar.  Carry is permitted only after an
    observed scheduled open is at/within 0.2% of that day's lower limit; every carried session
    must then also be observed exactly.
    """
    target_pos = day_to_calendar_pos.get(int(target_day))
    if target_pos is None or target_pos + horizon >= len(calendar_days):
        return 0.0, np.uint8(2), np.uint8(0)
    # A multi-session horizon cannot hop over a halt and call a later resumption the requested
    # D+H exit.  Every intervening common session must have an exact ticker bar.  This check is
    # deliberately separate from the lower-limit carry loop below: only an *observed* locked
    # scheduled exit may initiate carry.
    for intermediate_pos in range(target_pos + 1, target_pos + horizon):
        raw_pos = exact_row_index(raw_days, int(calendar_days[intermediate_pos]))
        if raw_pos is None or not bool(limits["valid"][raw_pos]):
            return 0.0, np.uint8(2), np.uint8(0)
    cal_pos = target_pos + horizon
    carry = 0
    while cal_pos < len(calendar_days) and carry <= MAX_LOWER_CARRY:
        wanted = int(calendar_days[cal_pos])
        raw_pos = exact_row_index(raw_days, wanted)
        if raw_pos is None or not bool(limits["valid"][raw_pos]):
            return 0.0, np.uint8(2), np.uint8(carry)
        open_value = float(limits["open"][raw_pos])
        lower = float(limits["lower"][raw_pos])
        if not np.isfinite(open_value) or not np.isfinite(lower) or lower <= 0:
            return 0.0, np.uint8(2), np.uint8(carry)
        locked = open_value <= lower * (1.0 + TOLERANT_CUSHION)
        if not locked:
            state = 0 if carry == 0 else 3
            return open_value / entry_open - 1.0, np.uint8(state), np.uint8(carry)
        carry += 1
        cal_pos += 1
    return 0.0, np.uint8(4), np.uint8(min(carry, 255))


@dataclass
class Panel:
    dates: np.ndarray
    ticker_id: np.ndarray
    board: np.ndarray
    era: np.ndarray
    x: np.ndarray
    y_tolerant: np.ndarray
    y_strict: np.ndarray
    target_state: np.ndarray
    fill_state: np.ndarray
    gross_returns: np.ndarray
    exit_state: np.ndarray
    carry_sessions: np.ndarray
    tickers: list[str]

    def __len__(self) -> int:
        return len(self.dates)

    @property
    def nbytes(self) -> int:
        return int(sum(a.nbytes for a in (
            self.dates, self.ticker_id, self.board, self.era, self.x, self.y_tolerant,
            self.y_strict, self.target_state, self.fill_state, self.gross_returns,
            self.exit_state, self.carry_sessions,
        )))


def _empty_chunk() -> dict[str, np.ndarray]:
    return {
        "dates": np.empty(0, dtype=np.int32), "ticker_id": np.empty(0, dtype=np.uint16),
        "board": np.empty(0, dtype=np.uint8), "era": np.empty(0, dtype=np.uint8),
        "x": np.empty((0, len(FEATURE_NAMES)), dtype=np.float32),
        "y_tolerant": np.empty(0, dtype=bool), "y_strict": np.empty(0, dtype=bool),
        "target_state": np.empty(0, dtype=np.uint8), "fill_state": np.empty(0, dtype=np.uint8),
        "gross_returns": np.empty((0, len(HORIZONS)), dtype=np.float32),
        "exit_state": np.empty((0, len(HORIZONS)), dtype=np.uint8),
        "carry_sessions": np.empty((0, len(HORIZONS)), dtype=np.uint8),
    }


def extract_ticker(
    frame: pd.DataFrame, *, ticker: str, ticker_id: int, board: str,
    calendar_days: np.ndarray, day_to_calendar_pos: dict[int, int],
    panel_start: int, panel_end: int,
) -> tuple[dict[str, np.ndarray], dict | None, dict[str, int]]:
    """Extract exact-clock candidates for one ticker without future-resolution conditioning."""
    stats = {"raw_rows": int(len(frame)), "feature_incomplete": 0, "candidate_rows": 0,
             "missing_target": 0, "missing_target_absent": 0,
             "missing_target_zero_volume": 0, "missing_target_invalid_price": 0,
             "invalid_target": 0, "observed_target": 0,
             "zero_volume_signal_rows_excluded": 0}
    required = {"open", "close", "high", "low", "volume"}
    if frame.empty or not required.issubset(frame.columns):
        return _empty_chunk(), None, stats
    frame = frame.loc[:, sorted(required)].copy()
    frame.index = pd.to_datetime(frame.index, errors="coerce")
    frame = frame[~frame.index.isna()].sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    if len(frame) < 2:
        return _empty_chunk(), None, stats
    raw_days = frame.index.to_numpy(dtype="datetime64[D]").astype(np.int32)
    features = compute_features(frame)
    limits = limit_arrays(frame, board, raw_days)

    cal_pos = np.searchsorted(calendar_days, raw_days)
    signal_is_session = (cal_pos < len(calendar_days)) & (calendar_days[np.minimum(cal_pos, len(calendar_days) - 1)] == raw_days)
    feature_ok = np.isfinite(features).all(axis=1)
    ipo_window = 5 if board in {"chinext", "star"} else (1 if raw_days[0] < _day("2014-01-01") else 0)
    row_no = np.arange(len(frame))
    eligible_signal = (signal_is_session & feature_ok & limits["valid"]
                       & (row_no >= ipo_window) & ~limits["tolerant"] & ~limits["exdiv"])
    stats["feature_incomplete"] = int((signal_is_session & ~feature_ok).sum())
    stats["zero_volume_signal_rows_excluded"] = int(
        (signal_is_session & ~limits["positive_volume"]).sum()
    )

    # Every eligible D-1 close creates a candidate at its exact calendar successor D, whether or
    # not this ticker prints a D bar.  This is the load-bearing no-resolution-conditioning rule.
    candidate_i: list[int] = []
    target_days: list[int] = []
    for i in np.flatnonzero(eligible_signal):
        cp = int(cal_pos[i])
        if cp + 1 >= len(calendar_days):
            continue
        target_day = int(calendar_days[cp + 1])
        if panel_start <= target_day <= panel_end:
            candidate_i.append(int(i))
            target_days.append(target_day)
    if not candidate_i:
        latest = _latest_feature_row(ticker, board, raw_days, features, limits, eligible_signal, calendar_days)
        return _empty_chunk(), latest, stats

    idx = np.asarray(candidate_i, dtype=np.int64)
    target = np.asarray(target_days, dtype=np.int32)
    n = len(idx)
    target_state = np.full(n, 1, dtype=np.uint8)
    fill_state = np.full(n, 2, dtype=np.uint8)
    y_tol = np.zeros(n, dtype=bool)
    y_strict = np.zeros(n, dtype=bool)
    returns = np.zeros((n, len(HORIZONS)), dtype=np.float32)
    exit_state = np.full((n, len(HORIZONS)), 2, dtype=np.uint8)
    carry = np.zeros((n, len(HORIZONS)), dtype=np.uint8)

    for k, (signal_i, target_day) in enumerate(zip(idx, target)):
        target_i = exact_row_index(raw_days, int(target_day))
        if target_i is None:
            stats["missing_target"] += 1
            stats["missing_target_absent"] += 1
            continue
        if not bool(limits["positive_volume"][target_i]):
            stats["missing_target"] += 1
            stats["missing_target_zero_volume"] += 1
            continue
        if not bool(limits["price_valid"][target_i]):
            stats["missing_target"] += 1
            stats["missing_target_invalid_price"] += 1
            continue
        if bool(limits["exdiv"][target_i]):
            target_state[k] = 2
            stats["invalid_target"] += 1
            continue
        target_state[k] = 0
        stats["observed_target"] += 1
        y_tol[k] = bool(limits["tolerant"][target_i])
        y_strict[k] = bool(limits["strict"][target_i])
        entry_open = float(limits["open"][target_i])
        queue = entry_open >= float(limits["upper"][target_i]) * (1.0 - TOLERANT_CUSHION)
        if queue:
            fill_state[k] = 1
            exit_state[k, :] = 1
            continue
        fill_state[k] = 0
        for h_idx, horizon in enumerate(HORIZONS):
            gross, state, carried = simulate_exit(
                raw_days=raw_days, calendar_days=calendar_days,
                day_to_calendar_pos=day_to_calendar_pos, limits=limits,
                entry_open=entry_open, target_day=int(target_day), horizon=horizon,
            )
            returns[k, h_idx] = gross
            exit_state[k, h_idx] = state
            carry[k, h_idx] = carried

    stats["candidate_rows"] = n
    board_code = {"main": 0, "chinext": 1, "star": 2}[board]
    chunk = {
        "dates": target,
        "ticker_id": np.full(n, ticker_id, dtype=np.uint16),
        "board": np.full(n, board_code, dtype=np.uint8),
        "era": era_code_for(board, target),
        "x": features[idx].astype(np.float32, copy=False),
        "y_tolerant": y_tol,
        "y_strict": y_strict,
        "target_state": target_state,
        "fill_state": fill_state,
        "gross_returns": returns,
        "exit_state": exit_state,
        "carry_sessions": carry,
    }
    latest = _latest_feature_row(ticker, board, raw_days, features, limits, eligible_signal, calendar_days)
    return chunk, latest, stats


def _latest_feature_row(
    ticker: str, board: str, raw_days: np.ndarray, features: np.ndarray,
    limits: dict[str, np.ndarray], eligible_signal: np.ndarray, calendar_days: np.ndarray,
) -> dict | None:
    latest_day = int(calendar_days[-1])
    pos = exact_row_index(raw_days, latest_day)
    if pos is None or not bool(eligible_signal[pos]):
        return None
    return {"ticker": ticker, "board": board, "era": ERA_NAMES[int(era_code_for(board, np.asarray([latest_day]))[0])],
            "signal_day": latest_day, "x": features[pos].astype(np.float32)}


def _concat_chunks(chunks: list[dict[str, np.ndarray]], tickers: list[str]) -> Panel:
    keys = list(_empty_chunk())
    values = {key: np.concatenate([c[key] for c in chunks], axis=0) for key in keys}
    return Panel(tickers=tickers, **values)


def validate_calendar_days(days: np.ndarray) -> None:
    """Fail closed on known omissions in the frozen 2011+ observed-session clock."""
    if len(days) == 0 or bool(np.any(np.diff(days) <= 0)):
        raise IntegrityError("observed CN session reference is empty/non-monotonic")
    if bool(np.any(pd.DatetimeIndex(days.astype("datetime64[D]")).dayofweek >= 5)):
        raise IntegrityError("observed CN session reference contains a weekend")
    missing = [anchor for anchor in CALENDAR_COMPLETENESS_ANCHORS
               if not bool(np.any(days == _day(anchor)))]
    if missing:
        raise IntegrityError(f"observed CN session reference misses completeness anchors: {missing}")
    frozen = days[(days >= _day("2011-01-01")) & (days <= _day(ANALYSIS_END))]
    if len(frozen) != EXPECTED_FROZEN_SESSION_COUNT:
        raise IntegrityError(
            "observed CN session reference frozen count mismatch: "
            f"actual={len(frozen)} expected={EXPECTED_FROZEN_SESSION_COUNT}"
        )


def validate_calendar_consensus(reference_days: np.ndarray, consensus_days: np.ndarray) -> dict:
    missing = np.setdiff1d(consensus_days, reference_days)
    extra = np.setdiff1d(reference_days, consensus_days)
    if len(missing) or len(extra):
        raise IntegrityError(
            "observed reference/market-support consensus mismatch: "
            f"missing={[_iso(d) for d in missing]} extra={[_iso(d) for d in extra]}"
        )
    return {
        "missing_from_reference": int(len(missing)),
        "extra_in_reference": int(len(extra)),
        "set_identical": True,
    }


def load_calendar() -> np.ndarray:
    if not SESSION_REF.exists():
        raise IntegrityError(f"missing observed CN session reference: {SESSION_REF}")
    frame = pd.read_parquet(SESSION_REF)
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise IntegrityError("observed CN session reference is not date indexed")
    idx = frame.index.tz_localize(None) if frame.index.tz is not None else frame.index
    days = idx.normalize().unique().sort_values().to_numpy(dtype="datetime64[D]").astype(np.int32)
    days = days[days <= _day(ANALYSIS_END)]
    validate_calendar_days(days)
    return days


def load_current_st() -> set[str]:
    if not ST_SNAPSHOT.exists():
        return set()
    frame = pd.read_parquet(ST_SNAPSHOT)
    return set(frame["ticker"].astype(str)) if "ticker" in frame.columns else set()


def source_overlap(raw_files: Sequence[Path]) -> dict:
    raw = {p.stem for p in raw_files}
    if not ZT_POOL.exists():
        return {"zt_pool_distinct_tickers": 0, "raw_overlap": 0, "missing_ohlcv": 0,
                "overlap_pct": None, "status": "zt_pool_missing"}
    pool = pd.read_parquet(ZT_POOL, columns=["ticker"])
    zt = set(pool["ticker"].astype(str))
    overlap = len(zt & raw)
    return {"zt_pool_distinct_tickers": len(zt), "raw_overlap": overlap,
            "missing_ohlcv": len(zt - raw), "overlap_pct": round(100.0 * overlap / len(zt), 2) if zt else None,
            "status": "quantified_universe_limit"}


def volume_census(frame: pd.DataFrame) -> tuple[int, int]:
    if "volume" not in frame.columns:
        return 0, int(len(frame))
    volume = pd.to_numeric(frame["volume"], errors="coerce").to_numpy(dtype=float)
    return int((volume == 0).sum()), int((~np.isfinite(volume) | (volume <= 0)).sum())


def add_raw_census(stats: dict, frame: pd.DataFrame) -> None:
    zero, unavailable = volume_census(frame)
    stats["files_census_read"] += 1
    stats["raw_rows_censused_all_discovered"] += len(frame)
    stats["raw_zero_volume_rows_all_discovered"] += zero
    stats["raw_nonpositive_or_missing_volume_rows_all_discovered"] += unavailable
    days = pd.to_datetime(frame.index, errors="coerce").to_numpy(dtype="datetime64[D]")
    volume = (pd.to_numeric(frame["volume"], errors="coerce").to_numpy(dtype=float)
              if "volume" in frame.columns else np.full(len(frame), np.nan))
    analysis_window = ((days >= np.datetime64("2011-01-01", "D"))
                       & (days <= np.datetime64(ANALYSIS_END, "D")))
    stats["raw_rows_censused_analysis_window"] += int(analysis_window.sum())
    stats["raw_zero_volume_rows_analysis_window"] += int(
        (analysis_window & (volume == 0)).sum()
    )
    stats["raw_nonpositive_or_missing_volume_rows_analysis_window"] += int(
        (analysis_window & (~np.isfinite(volume) | (volume <= 0))).sum()
    )
    for anchor in CALENDAR_COMPLETENESS_ANCHORS:
        hit = days == np.datetime64(anchor, "D")
        stats["calendar_anchor_support"][anchor]["raw_rows"] += int(hit.sum())
        stats["calendar_anchor_support"][anchor]["positive_volume_rows"] += int(
            (hit & np.isfinite(volume) & (volume > 0)).sum()
        )
    day_int = days.astype(np.int32)
    start = stats["_calendar_support_start"]
    support = stats["_calendar_index_support"]
    in_window = (day_int >= start) & (day_int <= _day(ANALYSIS_END))
    observed_offsets = np.unique(day_int[in_window] - start)
    np.add.at(support, observed_offsets, 1)


def build_panel() -> tuple[Panel, list[dict], dict]:
    started = time.monotonic()
    calendar_days = load_calendar()
    cal_map = {int(d): i for i, d in enumerate(calendar_days)}
    raw_files = sorted(RAW_DIR.glob("*.parquet"))
    st_set = load_current_st()
    chunks: list[dict[str, np.ndarray]] = []
    latest_rows: list[dict] = []
    tickers: list[str] = []
    file_digests: list[tuple[str, str]] = []
    support_start = int(_day("2011-01-01"))
    support_span = int(_day(ANALYSIS_END)) - support_start + 1
    stats = {
        "files_discovered": len(raw_files), "files_read": 0, "files_error": 0,
        "files_bse_excluded": 0, "files_current_st_excluded": 0, "files_thin": 0,
        "raw_rows_read": 0, "feature_incomplete_rows": 0, "candidate_rows": 0,
        "target_observed": 0, "target_missing_halted": 0, "target_invalid_corporate_action": 0,
        "errors": [],
        "current_st_snapshot_names": len(st_set),
        "files_census_read": 0, "files_census_error": 0, "raw_rows_censused_all_discovered": 0,
        "raw_zero_volume_rows_all_discovered": 0,
        "raw_nonpositive_or_missing_volume_rows_all_discovered": 0,
        "raw_rows_censused_analysis_window": 0,
        "raw_zero_volume_rows_analysis_window": 0,
        "raw_nonpositive_or_missing_volume_rows_analysis_window": 0,
        "zero_volume_signal_rows_excluded": 0,
        "target_missing_absent": 0, "target_zero_volume_missing": 0,
        "target_invalid_price_missing": 0,
        "calendar_anchor_support": {
            anchor: {"raw_rows": 0, "positive_volume_rows": 0}
            for anchor in CALENDAR_COMPLETENESS_ANCHORS
        },
        "_calendar_support_start": support_start,
        "_calendar_index_support": np.zeros(support_span, dtype=np.uint16),
    }
    panel_start, panel_end = _day("2011-01-01"), _day("2026-08-07")
    for path in raw_files:
        ticker = path.stem
        board = board_from_ticker(ticker)
        if board == "bse":
            stats["files_bse_excluded"] += 1
            try:
                census = pd.read_parquet(path, columns=["volume"])
                add_raw_census(stats, census)
            except Exception as exc:  # noqa: BLE001 — census failure is explicit in receipt
                stats["files_census_error"] += 1
                stats["errors"].append({"file": path.name, "stage": "excluded_volume_census",
                                        "error": f"{type(exc).__name__}: {exc}"})
            continue
        if ticker in st_set:
            stats["files_current_st_excluded"] += 1
            try:
                census = pd.read_parquet(path, columns=["volume"])
                add_raw_census(stats, census)
            except Exception as exc:  # noqa: BLE001 — census failure is explicit in receipt
                stats["files_census_error"] += 1
                stats["errors"].append({"file": path.name, "stage": "excluded_volume_census",
                                        "error": f"{type(exc).__name__}: {exc}"})
            continue
        try:
            digest = file_hash(path)
            frame = pd.read_parquet(path)
            stats["files_read"] += 1
            stats["raw_rows_read"] += int(len(frame))
            add_raw_census(stats, frame)
            file_digests.append((ticker, digest))
            if len(frame) < 2:
                stats["files_thin"] += 1
                continue
            ticker_id = len(tickers)
            tickers.append(ticker)
            chunk, latest, local = extract_ticker(
                frame, ticker=ticker, ticker_id=ticker_id, board=board,
                calendar_days=calendar_days, day_to_calendar_pos=cal_map,
                panel_start=panel_start, panel_end=panel_end,
            )
            chunks.append(chunk)
            if latest is not None:
                latest_rows.append(latest)
            stats["feature_incomplete_rows"] += local["feature_incomplete"]
            stats["candidate_rows"] += local["candidate_rows"]
            stats["target_observed"] += local["observed_target"]
            stats["target_missing_halted"] += local["missing_target"]
            stats["target_invalid_corporate_action"] += local["invalid_target"]
            stats["zero_volume_signal_rows_excluded"] += local["zero_volume_signal_rows_excluded"]
            stats["target_missing_absent"] += local["missing_target_absent"]
            stats["target_zero_volume_missing"] += local["missing_target_zero_volume"]
            stats["target_invalid_price_missing"] += local["missing_target_invalid_price"]
        except Exception as exc:  # noqa: BLE001 — receipt records exact file failures
            stats["files_error"] += 1
            stats["errors"].append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})
    if not chunks:
        raise IntegrityError("no usable raw ticker files")
    support = stats.pop("_calendar_index_support")
    stats.pop("_calendar_support_start")
    if stats["raw_zero_volume_rows_analysis_window"] != EXPECTED_ANALYSIS_ZERO_VOLUME_ROWS:
        raise IntegrityError(
            "2011+ zero-volume census changed: "
            f"actual={stats['raw_zero_volume_rows_analysis_window']} "
            f"expected={EXPECTED_ANALYSIS_ZERO_VOLUME_ROWS}"
        )
    consensus_days = (support_start
                      + np.flatnonzero(support >= CALENDAR_CONSENSUS_MIN_NAMES)).astype(np.int32)
    frozen_reference = calendar_days[(calendar_days >= _day("2011-01-01"))
                                     & (calendar_days <= _day(ANALYSIS_END))]
    if len(consensus_days) != EXPECTED_FROZEN_SESSION_COUNT:
        raise IntegrityError(
            "raw-index consensus frozen count mismatch: "
            f"actual={len(consensus_days)} expected={EXPECTED_FROZEN_SESSION_COUNT}"
        )
    consensus_match = validate_calendar_consensus(frozen_reference, consensus_days)
    reference = pd.read_parquet(SESSION_REF, columns=["volume"])
    reference_days = pd.to_datetime(reference.index).to_numpy(dtype="datetime64[D]").astype(np.int32)
    reference_volume = pd.to_numeric(reference["volume"], errors="coerce").to_numpy(dtype=float)
    reference_window = (reference_days >= _day("2011-01-01")) & (reference_days <= _day(ANALYSIS_END))
    reference_positive = int((reference_window & np.isfinite(reference_volume)
                              & (reference_volume > 0)).sum())
    if reference_positive != EXPECTED_REFERENCE_POSITIVE_VOLUME_SESSIONS:
        raise IntegrityError(
            "600519 positive-volume diagnostic changed: "
            f"actual={reference_positive} expected={EXPECTED_REFERENCE_POSITIVE_VOLUME_SESSIONS}"
        )
    stats["calendar_consensus_validation"] = {
        "support_rule": f"raw_index_presence_at_least_{CALENDAR_CONSENSUS_MIN_NAMES}_names",
        "consensus_sessions": int(len(consensus_days)),
        "reference_sessions": int(len(frozen_reference)),
        "missing_from_600519_reference": consensus_match["missing_from_reference"],
        "extra_in_600519_reference": consensus_match["extra_in_reference"],
        "set_identical": consensus_match["set_identical"],
        "reference_positive_volume_sessions": reference_positive,
        "reference_zero_or_missing_volume_sessions": int(len(frozen_reference) - reference_positive),
        "volume_filter_applied_to_market_clock": False,
    }
    panel = _concat_chunks(chunks, tickers)
    stats["panel_nbytes"] = panel.nbytes
    stats["panel_mib"] = round(panel.nbytes / 1024 / 1024, 2)
    stats["runtime_panel_sec"] = round(time.monotonic() - started, 3)
    stats["source_manifest_hash"] = canonical_hash(file_digests + [
        (str(SESSION_REF.relative_to(ROOT)), file_hash(SESSION_REF)),
        (str(ST_SNAPSHOT.relative_to(ROOT)), file_hash(ST_SNAPSHOT)) if ST_SNAPSHOT.exists() else ("st", "missing"),
        (str(ZT_POOL.relative_to(ROOT)), file_hash(ZT_POOL)) if ZT_POOL.exists() else ("zt_pool", "missing"),
    ])
    stats["raw_ticker_hashes_count"] = len(file_digests)
    stats["calendar_receipt"] = {
        "source": str(SESSION_REF.relative_to(ROOT)),
        "source_hash": file_hash(SESSION_REF),
        "sessions_2011_through_as_of": int(((calendar_days >= _day("2011-01-01"))
                                             & (calendar_days <= _day(ANALYSIS_END))).sum()),
        "first": _iso(calendar_days[0]), "last": _iso(calendar_days[-1]),
        "completeness_anchors": list(CALENDAR_COMPLETENESS_ANCHORS),
        "all_completeness_anchors_present": True,
        "consensus_validation": stats["calendar_consensus_validation"],
    }
    stats["zt_pool_universe_limit"] = source_overlap(raw_files)
    return panel, latest_rows, stats


def split_codes(dates: np.ndarray, calendar_days: np.ndarray) -> tuple[np.ndarray, dict]:
    """Frozen blocks with a ten-session purged tail on every block preceding another."""
    codes = np.zeros(len(dates), dtype=np.uint8)
    ranges = {
        1: (_day("2011-01-01"), _day("2019-12-31")),
        2: (_day("2020-01-01"), _day("2023-12-31")),
        3: (_day("2024-01-02"), _day("2026-06-12")),
        4: (_day("2026-06-15"), _day("2026-08-07")),
    }
    purge_receipt: dict[str, list[str]] = {}
    for code, (start, end) in ranges.items():
        codes[(dates >= start) & (dates <= end)] = code
        if code < 4:
            block_sessions = calendar_days[(calendar_days >= start) & (calendar_days <= end)]
            purged = block_sessions[-PURGE_SESSIONS:]
            codes[np.isin(dates, purged)] = 0
            purge_receipt[SPLIT_NAMES[code]] = [_iso(d) for d in purged]
    return codes, {"rule": "last_10_common_sessions_removed_from_each_preceding_block",
                   "dates": purge_receipt}


@dataclass
class Scaler:
    mean: np.ndarray
    std: np.ndarray

    def transform(self, x: np.ndarray, columns: Sequence[int]) -> np.ndarray:
        cols = np.asarray(columns, dtype=int)
        return (x[:, cols].astype(np.float64) - self.mean) / self.std

    def receipt(self, columns: Sequence[int]) -> dict:
        return {"features": [FEATURE_NAMES[i] for i in columns],
                "mean": self.mean.tolist(), "std": self.std.tolist()}


def fit_scaler(x: np.ndarray, mask: np.ndarray, columns: Sequence[int]) -> Scaler:
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        raise IntegrityError("empty scaler fit population")
    sums = np.zeros(len(columns), dtype=np.float64)
    sums2 = np.zeros(len(columns), dtype=np.float64)
    n = 0
    for start in range(0, len(idx), BATCH_ROWS):
        batch = x[idx[start:start + BATCH_ROWS]][:, columns].astype(np.float64)
        sums += batch.sum(axis=0)
        sums2 += np.square(batch).sum(axis=0)
        n += len(batch)
    mean = sums / n
    var = np.maximum(sums2 / n - mean * mean, 1e-8)
    return Scaler(mean=mean, std=np.sqrt(var))


@dataclass
class LogisticModel:
    name: str
    columns: tuple[int, ...]
    scaler: Scaler
    beta: np.ndarray
    calibration: np.ndarray
    iterations: int

    def raw_logit(self, x: np.ndarray) -> np.ndarray:
        z = self.scaler.transform(x, self.columns)
        return self.beta[0] + z @ self.beta[1:]

    def probability(self, x: np.ndarray, calibrated: bool = True) -> np.ndarray:
        logit = self.raw_logit(x)
        if calibrated:
            logit = self.calibration[0] + self.calibration[1] * logit
        return sigmoid(logit)

    def receipt(self) -> dict:
        payload = {
            "name": self.name, "columns": [FEATURE_NAMES[i] for i in self.columns],
            "scaler": self.scaler.receipt(self.columns), "beta": self.beta.tolist(),
            "platt_intercept_slope": self.calibration.tolist(), "iterations": self.iterations,
            "l2": CONFIG["model"]["l2"],
        }
        payload["model_hash"] = canonical_hash(payload)
        return payload


@dataclass
class EqualRankModel:
    """Frozen equal-weight train-CDF rank comparator with a calibration-only probability map."""

    name: str
    columns: tuple[int, ...]
    knots: np.ndarray
    calibration: np.ndarray

    def raw_logit(self, x: np.ndarray) -> np.ndarray:
        ranks = np.column_stack([
            np.searchsorted(self.knots[:, j], x[:, col], side="right") / len(self.knots)
            for j, col in enumerate(self.columns)
        ])
        raw = np.clip(np.mean(ranks, axis=1), 1e-6, 1 - 1e-6)
        return np.log(raw / (1.0 - raw))

    def probability(self, x: np.ndarray, calibrated: bool = True) -> np.ndarray:
        logit = self.raw_logit(x)
        if calibrated:
            logit = self.calibration[0] + self.calibration[1] * logit
        return sigmoid(logit)

    def receipt(self) -> dict:
        payload = {
            "name": self.name,
            "features": [FEATURE_NAMES[i] for i in self.columns],
            "rank_reference": "main_train_2011_2019_101_quantile_grid",
            "weights": [1.0 / len(self.columns)] * len(self.columns),
            "knots": {
                FEATURE_NAMES[col]: self.knots[:, j].tolist()
                for j, col in enumerate(self.columns)
            },
            "calibration": self.calibration.tolist(),
        }
        payload["model_hash"] = canonical_hash(payload)
        return payload


def sigmoid(value: np.ndarray | float) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    return 1.0 / (1.0 + np.exp(-np.clip(arr, -35.0, 35.0)))


def fit_logistic(
    x: np.ndarray, y: np.ndarray, mask: np.ndarray, columns: Sequence[int], *, name: str,
    l2: float = 1e-3, max_iter: int = 8,
) -> LogisticModel:
    idx = np.flatnonzero(mask)
    if len(idx) == 0 or int(y[idx].sum()) == 0:
        raise IntegrityError(f"empty/no-event logistic fit: {name}")
    scaler = fit_scaler(x, mask, columns)
    p0 = float(np.clip(y[idx].mean(), 1e-6, 1 - 1e-6))
    beta = np.zeros(len(columns) + 1, dtype=np.float64)
    beta[0] = math.log(p0 / (1.0 - p0))
    iterations = 0
    for iteration in range(max_iter):
        grad = np.zeros_like(beta)
        hess = np.zeros((len(beta), len(beta)), dtype=np.float64)
        for start in range(0, len(idx), BATCH_ROWS):
            rows = idx[start:start + BATCH_ROWS]
            z = scaler.transform(x[rows], columns)
            design = np.column_stack([np.ones(len(rows)), z])
            prob = sigmoid(design @ beta)
            error = prob - y[rows].astype(np.float64)
            grad += design.T @ error
            weight = np.clip(prob * (1.0 - prob), 1e-8, None)
            hess += design.T @ (design * weight[:, None])
        n = float(len(idx))
        grad /= n
        hess /= n
        penalty = np.eye(len(beta), dtype=np.float64) * l2
        penalty[0, 0] = 0.0
        grad += penalty @ beta
        hess += penalty + np.eye(len(beta)) * 1e-9
        step = np.linalg.solve(hess, grad)
        beta -= np.clip(step, -2.0, 2.0)
        iterations = iteration + 1
        if float(np.max(np.abs(step))) < 1e-7:
            break
    return LogisticModel(name=name, columns=tuple(columns), scaler=scaler, beta=beta,
                         calibration=np.asarray([0.0, 1.0]), iterations=iterations)


def fit_two_parameter_logistic(logit: np.ndarray, y: np.ndarray, max_iter: int = 50) -> np.ndarray:
    """Stable two-parameter logistic fit using damped Newton with an exact line search ruler.

    The earlier clipped-step Newton prototype could bounce between two parameter vectors and
    return its zero-slope initialization.  This implementation works directly on the two
    sufficient-statistic columns and accepts a step only when the logaddexp objective decreases.
    """
    finite = np.isfinite(logit)
    z = np.clip(logit[finite].astype(np.float64), -25.0, 25.0)
    outcome = y[finite].astype(np.float64)
    if len(z) == 0 or outcome.sum() == 0 or outcome.sum() == len(outcome):
        return np.asarray([0.0, 1.0])
    base = float(np.clip(outcome.mean(), 1e-6, 1 - 1e-6))
    beta = np.asarray([math.log(base / (1 - base)), 0.0])
    if float(np.std(z)) < 1e-12:
        return beta

    def objective(candidate: np.ndarray) -> float:
        eta = candidate[0] + candidate[1] * z
        return float(np.mean(np.logaddexp(0.0, eta) - outcome * eta))

    for _ in range(max_iter):
        eta = beta[0] + beta[1] * z
        prob = sigmoid(eta)
        error = prob - outcome
        grad = np.asarray([error.mean(), np.mean(error * z)])
        weight = np.clip(prob * (1 - prob), 1e-8, None)
        hess = np.asarray([
            [weight.mean(), np.mean(weight * z)],
            [np.mean(weight * z), np.mean(weight * z * z)],
        ]) + np.eye(2) * 1e-10
        step = np.linalg.solve(hess, grad)
        current = objective(beta)
        directional = float(grad @ step)
        scale = 1.0
        accepted = False
        while scale >= 2.0 ** -20:
            candidate = beta - scale * step
            if objective(candidate) <= current - 1e-4 * scale * directional:
                accepted = True
                break
            scale *= 0.5
        if not accepted:
            break
        beta = candidate
        if float(np.max(np.abs(scale * step))) < 1e-8:
            break
    return beta


def calibrate_model(model: LogisticModel, x: np.ndarray, y: np.ndarray, mask: np.ndarray) -> LogisticModel:
    idx = np.flatnonzero(mask)
    calibration = fit_two_parameter_logistic(model.raw_logit(x[idx]), y[idx])
    model.calibration = calibration
    return model


def score_panel(
    model: LogisticModel | EqualRankModel, x: np.ndarray, calibrated: bool = True,
) -> np.ndarray:
    out = np.empty(len(x), dtype=np.float32)
    for start in range(0, len(x), BATCH_ROWS):
        out[start:start + BATCH_ROWS] = model.probability(
            x[start:start + BATCH_ROWS], calibrated=calibrated
        ).astype(np.float32)
    return out


def safe_log_loss(y: np.ndarray, p: np.ndarray) -> float:
    clipped = np.clip(p.astype(np.float64), 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(clipped) + (1 - y) * np.log(1 - clipped)))


def calibration_summary(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict:
    clipped = np.clip(p.astype(np.float64), 1e-8, 1 - 1e-8)
    edges = np.linspace(0.0, 1.0, bins + 1)
    which = np.minimum(np.searchsorted(edges, clipped, side="right") - 1, bins - 1)
    cells = []
    ece = 0.0
    for b in range(bins):
        mask = which == b
        if not mask.any():
            continue
        pred = float(clipped[mask].mean())
        actual = float(y[mask].mean())
        n = int(mask.sum())
        ece += n / len(y) * abs(pred - actual)
        cells.append({"bin": b, "n": n, "predicted": pred, "actual": actual})
    logits = np.log(clipped / (1 - clipped))
    if int(y.sum()) in {0, len(y)}:
        intercept: float | None = None
        slope: float | None = None
        fit_status = "degenerate_constant_outcome_not_estimated"
    else:
        line = fit_two_parameter_logistic(logits, y)
        intercept, slope = float(line[0]), float(line[1])
        fit_status = ("degenerate_constant_logit" if float(np.std(logits)) < 1e-12
                      else "estimated")
    return {"ece_10": float(ece), "intercept": intercept, "slope": slope,
            "fit_method": "damped_newton_logaddexp_line_search", "fit_status": fit_status,
            "bins": cells}


def probability_metrics(y: np.ndarray, p: np.ndarray, base_probability: float) -> dict:
    if len(y) == 0:
        return {"n": 0}
    base_probability = float(np.clip(base_probability, 1e-9, 1 - 1e-9))
    base = np.full(len(y), base_probability, dtype=np.float64)
    brier = float(np.mean(np.square(p.astype(np.float64) - y)))
    base_brier = float(np.mean(np.square(base - y)))
    logloss = safe_log_loss(y, p)
    base_logloss = safe_log_loss(y, base)
    return {
        "n": int(len(y)), "events": int(y.sum()), "event_rate": float(y.mean()),
        "base_probability_frozen_from_calibration": base_probability,
        "brier": brier, "base_brier": base_brier, "brier_improvement": base_brier - brier,
        "log_loss": logloss, "base_log_loss": base_logloss,
        "log_loss_improvement": base_logloss - logloss,
        "calibration": calibration_summary(y, p),
    }


def cash_book_return(
    fill_state: np.ndarray, gross_return: np.ndarray, exit_state: np.ndarray, cost_bps: int,
) -> np.ndarray:
    """All candidates remain in the denominator; queue/missing/unresolved are cash=0."""
    out = np.zeros(len(fill_state), dtype=np.float64)
    resolved = (fill_state == 0) & np.isin(exit_state, [0, 3])
    out[resolved] = gross_return[resolved].astype(np.float64) - cost_bps / 10_000.0
    return out


def month_block_bootstrap_mean(
    daily_values: np.ndarray, daily_dates: np.ndarray, *, replicates: int = 1000,
    seed: int = 20260808,
) -> dict:
    """Resample whole calendar-month blocks; never pretend name-rows are independent."""
    values = np.asarray(daily_values, dtype=np.float64)
    dates = np.asarray(daily_dates, dtype=np.int32)
    if len(values) == 0 or len(values) != len(dates):
        return {"status": "empty", "replicates": 0}
    labels = np.asarray([_iso(day)[:7] for day in dates])
    months = list(dict.fromkeys(labels.tolist()))
    block_sums = np.asarray([values[labels == month].sum() for month in months])
    block_counts = np.asarray([(labels == month).sum() for month in months], dtype=np.float64)
    rng = np.random.default_rng(seed)
    sampled = rng.integers(0, len(months), size=(replicates, len(months)))
    estimates = block_sums[sampled].sum(axis=1) / block_counts[sampled].sum(axis=1)
    q = np.quantile(estimates, [0.025, 0.5, 0.975])
    return {
        "status": "estimated", "method": "calendar_month_blocks_resampled_with_replacement",
        "months": len(months), "replicates": replicates, "seed": seed,
        "point": float(values.mean()), "p2_5": float(q[0]), "median": float(q[1]),
        "p97_5": float(q[2]),
    }


def _position_release_day(
    panel: Panel, row: int, horizon_index: int, horizon: int,
    calendar_days: np.ndarray, calendar_pos: dict[int, int],
) -> int | None:
    """None means no fill; a far-future sentinel means filled but no proved exact exit."""
    if int(panel.fill_state[row]) != 0:
        return None
    state = int(panel.exit_state[row, horizon_index])
    if state not in {0, 3}:
        return int(np.iinfo(np.int32).max)
    entry_pos = calendar_pos[int(panel.dates[row])]
    release_pos = entry_pos + horizon + int(panel.carry_sessions[row, horizon_index])
    if release_pos >= len(calendar_days):
        return int(np.iinfo(np.int32).max)
    return int(calendar_days[release_pos])


def event_overlap_diagnostics(
    panel: Panel, chosen_by_date: Sequence[np.ndarray], dates: Sequence[int],
    horizon_index: int, horizon: int, calendar_days: np.ndarray,
) -> dict:
    """Quantify duplicate lots in the event-cohort ruler; do not repair it into a portfolio."""
    calendar_pos = {int(day): i for i, day in enumerate(calendar_days)}
    active: dict[int, list[int]] = {}
    overlaps = 0
    overlap_dates = 0
    max_lots = 0
    for day, chosen in zip(dates, chosen_by_date):
        for ticker in list(active):
            active[ticker] = [release for release in active[ticker] if release > int(day)]
            if not active[ticker]:
                del active[ticker]
        date_overlaps = 0
        for row in chosen:
            ticker = int(panel.ticker_id[row])
            if active.get(ticker):
                overlaps += 1
                date_overlaps += 1
            release = _position_release_day(
                panel, int(row), horizon_index, horizon, calendar_days, calendar_pos
            )
            if release is not None:
                active.setdefault(ticker, []).append(release)
                max_lots = max(max_lots, len(active[ticker]))
        overlap_dates += int(date_overlaps > 0)
    total = sum(len(rows) for rows in chosen_by_date)
    return {
        "selected_event_rows": int(total), "overlapping_reselection_rows": int(overlaps),
        "overlap_rate": float(overlaps / total) if total else 0.0,
        "dates_with_overlap": int(overlap_dates),
        "max_concurrent_lots_same_ticker": int(max_lots),
        "status": ("H1_EVENT_DIAGNOSTIC_USE_SEQUENTIAL_BOOK_FOR_PORTFOLIO" if horizon == 1
                   else "EVENT_LEVEL_OVERLAPPING_COHORT_DIAGNOSTIC_NOT_A_CAPITAL_BOOK"),
    }


def sequential_h1_fixed_sleeve_selection(
    panel: Panel, ranked_by_date: Sequence[np.ndarray], dates: Sequence[int], k: int,
    calendar_days: np.ndarray,
) -> tuple[list[np.ndarray], dict]:
    """Select a no-duplicate H1 book with K capital sleeves and exact-open releases."""
    calendar_pos = {int(day): i for i, day in enumerate(calendar_days)}
    active: dict[int, int] = {}
    chosen_by_date: list[np.ndarray] = []
    duplicate_rows_skipped = 0
    unavailable_sleeves = 0
    underfilled_days = 0
    for day, ranked in zip(dates, ranked_by_date):
        # A position scheduled to exit at today's open releases before today's explicitly ordered
        # auction entry.  Lower-limit carried/unresolved positions remain active.
        active = {ticker: release for ticker, release in active.items() if release > int(day)}
        capacity = max(0, k - len(active))
        unavailable_sleeves += k - capacity
        chosen: list[int] = []
        for row_raw in ranked:
            if len(chosen) >= capacity:
                break
            row = int(row_raw)
            ticker = int(panel.ticker_id[row])
            if ticker in active:
                duplicate_rows_skipped += 1
                continue
            chosen.append(row)
        chosen_array = np.asarray(chosen, dtype=np.int64)
        chosen_by_date.append(chosen_array)
        underfilled_days += int(len(chosen_array) < k)
        for row in chosen_array:
            release = _position_release_day(panel, int(row), 0, 1, calendar_days, calendar_pos)
            if release is not None:
                active[int(panel.ticker_id[row])] = release
    return chosen_by_date, {
        "fixed_capital_sleeves": k, "duplicate_rows_skipped": duplicate_rows_skipped,
        "unavailable_sleeve_days": unavailable_sleeves, "underfilled_dates": underfilled_days,
        "positions_still_open_at_block_end": int(len(active)),
        "unresolved_exit_positions_at_block_end": int(
            sum(release == int(np.iinfo(np.int32).max) for release in active.values())
        ),
        "same_open_exit_then_reentry": "explicitly_allowed_release_before_new_auction_order",
        "no_duplicate_ticker_asserted": True,
    }


def topk_metrics(
    panel: Panel, mask: np.ndarray, probability: np.ndarray, y: np.ndarray,
    calendar_days: np.ndarray,
) -> dict:
    sub = np.flatnonzero(mask)
    if len(sub) == 0:
        return {}
    order = np.lexsort((panel.ticker_id[sub], panel.dates[sub]))
    sub = sub[order]
    dates = panel.dates[sub]
    boundaries = np.r_[0, np.flatnonzero(np.diff(dates)) + 1, len(sub)]
    result: dict[str, dict] = {}
    for k in TOP_K:
        daily_precision: list[float] = []
        daily_base: list[float] = []
        selected_all: list[np.ndarray] = []
        ranked_by_date: list[np.ndarray] = []
        selected_counts: list[int] = []
        selected_dates: list[int] = []
        for left, right in zip(boundaries[:-1], boundaries[1:]):
            rows = sub[left:right]
            ranked = rows[np.lexsort((panel.ticker_id[rows], -probability[rows]))]
            chosen = ranked[:min(k, len(ranked))]
            ranked_by_date.append(ranked)
            selected_all.append(chosen)
            selected_counts.append(len(chosen))
            selected_dates.append(int(panel.dates[rows[0]]))
            daily_precision.append(float(y[chosen].mean()) if len(chosen) else 0.0)
            daily_base.append(float(y[rows].mean()))
        chosen = np.concatenate(selected_all)
        entry_fill = panel.fill_state[chosen]
        block = {
            "k": k, "dates": len(daily_precision), "selected_rows": int(len(chosen)),
            "mean_names_selected_per_date": float(np.mean(selected_counts)),
            "day_weighted_precision": float(np.mean(daily_precision)),
            "day_weighted_base_rate": float(np.mean(daily_base)),
            "day_weighted_lift": (float(np.mean(daily_precision) / np.mean(daily_base))
                                  if np.mean(daily_base) > 0 else None),
            "fill_funnel": {
                "fillable_daily_proxy": int((entry_fill == 0).sum()),
                "queue_required_no_fill": int((entry_fill == 1).sum()),
                "missing_unknown": int((entry_fill == 2).sum()),
                "fill_rate": float((entry_fill == 0).mean()),
            },
            "return_ruler_status": {
                "H1": "portfolio_claims_use_sequential_fixed_K_sleeve_book_only",
                "H3_H5": "event_level_overlapping_cohort_diagnostics_no_capital_book_claim",
            },
            "event_level_cohort_returns": {},
            "event_level_overlap_diagnostics": {},
        }
        for h_idx, horizon in enumerate(HORIZONS):
            exit_s = panel.exit_state[chosen, h_idx]
            gross = panel.gross_returns[chosen, h_idx]
            h = {
                "status": ("EVENT_LEVEL_DIAGNOSTIC_H1_SEQUENTIAL_BOOK_PRINTED_SEPARATELY"
                           if horizon == 1 else
                           "EVENT_LEVEL_OVERLAPPING_COHORT_DIAGNOSTIC_NOT_A_CAPITAL_BOOK"),
                "lower_limit_carry_count": int((exit_s == 3).sum()),
                "missing_or_unresolved_count": int(np.isin(exit_s, [2, 4]).sum()),
                "filled_resolved_count": int(((entry_fill == 0) & np.isin(exit_s, [0, 3])).sum()),
                "cost_grid": {},
            }
            resolved = (entry_fill == 0) & np.isin(exit_s, [0, 3])
            h["filled_only_mean_gross"] = float(gross[resolved].mean()) if resolved.any() else None
            for cost in COST_BPS:
                joint = cash_book_return(entry_fill, gross, exit_s, cost)
                # Day-weighted joint book: every selected name participates; cash zeros remain.
                daily: list[float] = []
                offset = 0
                for count in selected_counts:
                    daily.append(float(joint[offset:offset + count].mean()) if count else 0.0)
                    offset += count
                daily_array = np.asarray(daily, dtype=np.float64)
                wealth = np.cumprod(1.0 + daily_array)
                running_peak = np.maximum.accumulate(np.r_[1.0, wealth])
                drawdown = np.r_[1.0, wealth] / running_peak - 1.0
                h["cost_grid"][str(cost)] = {
                    "pooled_all_candidate_mean": float(joint.mean()),
                    "day_weighted_all_candidate_mean": float(np.mean(daily)),
                    "cumulative_compounded_return": float(wealth[-1] - 1.0),
                    "max_drawdown": float(drawdown.min()),
                    "calendar_month_block_bootstrap": month_block_bootstrap_mean(
                        daily_array, np.asarray(selected_dates, dtype=np.int32)
                    ),
                }
            horizon_key = f"H{horizon}_next_open"
            block["event_level_cohort_returns"][horizon_key] = h
            block["event_level_overlap_diagnostics"][horizon_key] = event_overlap_diagnostics(
                panel, selected_all, selected_dates, h_idx, horizon, calendar_days
            )

        sequential, sequential_state = sequential_h1_fixed_sleeve_selection(
            panel, ranked_by_date, selected_dates, k, calendar_days
        )
        sequential_chosen = np.concatenate(sequential)
        sequential_counts = [len(rows) for rows in sequential]
        sequential_fill = panel.fill_state[sequential_chosen]
        sequential_exit = panel.exit_state[sequential_chosen, 0]
        sequential_gross = panel.gross_returns[sequential_chosen, 0]
        sequential_resolved = ((sequential_fill == 0)
                               & np.isin(sequential_exit, [0, 3]))
        sequential_block = {
            **sequential_state,
            "status": "FIXED_K_SLEEVE_NO_DUPLICATE_SELECTION_ENTRY_COHORT_RETURN_PROXY",
            "selected_order_rows": int(len(sequential_chosen)),
            "mean_orders_per_date": float(np.mean(sequential_counts)),
            "fill_funnel": {
                "fillable_daily_proxy": int((sequential_fill == 0).sum()),
                "queue_required_no_fill": int((sequential_fill == 1).sum()),
                "missing_unknown": int((sequential_fill == 2).sum()),
                "fill_rate_of_orders": (float((sequential_fill == 0).mean())
                                         if len(sequential_fill) else None),
            },
            "lower_limit_carry_count": int((sequential_exit == 3).sum()),
            "missing_or_unresolved_count": int(np.isin(sequential_exit, [2, 4]).sum()),
            "filled_resolved_count": int(sequential_resolved.sum()),
            "filled_only_mean_gross": (float(sequential_gross[sequential_resolved].mean())
                                       if sequential_resolved.any() else None),
            "cost_grid": {},
        }
        for cost in COST_BPS:
            joint = cash_book_return(sequential_fill, sequential_gross, sequential_exit, cost)
            daily: list[float] = []
            offset = 0
            for count in sequential_counts:
                # Fixed K is the capital denominator.  A held, unavailable, rejected, or missing
                # sleeve contributes zero under the frozen daily proxy instead of implicit leverage.
                daily.append(float(joint[offset:offset + count].sum() / k))
                offset += count
            daily_array = np.asarray(daily, dtype=np.float64)
            wealth = np.cumprod(1.0 + daily_array)
            running_peak = np.maximum.accumulate(np.r_[1.0, wealth])
            drawdown = np.r_[1.0, wealth] / running_peak - 1.0
            sequential_block["cost_grid"][str(cost)] = {
                "day_weighted_fixed_sleeve_mean": float(daily_array.mean()),
                "cumulative_compounded_return": float(wealth[-1] - 1.0),
                "max_drawdown": float(drawdown.min()),
                "calendar_month_block_bootstrap": month_block_bootstrap_mean(
                    daily_array, np.asarray(selected_dates, dtype=np.int32)
                ),
            }
        block["sequential_H1_fixed_K_sleeve_book"] = sequential_block
        result[f"top_{k}"] = block
    return result


def base_probability(y: np.ndarray, mask: np.ndarray, fallback: float) -> float:
    values = y[mask]
    return float(values.mean()) if len(values) else fallback


def evaluation_groups(panel: Panel, split: np.ndarray) -> dict[str, np.ndarray]:
    groups: dict[str, np.ndarray] = {}
    for code, split_name in SPLIT_NAMES.items():
        if code == 0:
            continue
        for era_code, era_name in ERA_NAMES.items():
            mask = (split == code) & (panel.era == era_code)
            if mask.any():
                groups[f"{split_name}:{era_name}"] = mask
    stress = ((panel.dates >= _day("2015-01-01")) & (panel.dates <= _day("2015-12-31"))
              & (panel.era == 0))
    if stress.any():
        groups["stress_2015_in_sample_descriptive:main_10"] = stress
    return groups


def date_blocks(panel: Panel, mask: np.ndarray, p_o1: np.ndarray, p_o3: np.ndarray) -> list[dict]:
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return []
    labels = np.asarray([f"{_iso(d)[:4]}Q{(int(_iso(d)[5:7]) - 1) // 3 + 1}" for d in panel.dates[idx]])
    out = []
    for label in sorted(set(labels)):
        rows = idx[labels == label]
        y = panel.y_tolerant[rows]
        out.append({"block": label, "n": int(len(rows)), "events": int(y.sum()),
                    "event_rate": float(y.mean()),
                    "o1_brier": float(np.mean(np.square(p_o1[rows] - y))),
                    "o3_brier": float(np.mean(np.square(p_o3[rows] - y)))})
    return out


def date_block_bootstrap(
    panel: Panel, mask: np.ndarray, probabilities: dict[str, np.ndarray], base: float,
    *, block_sessions: int = 10, replicates: int = 1000, seed: int = 20260808,
) -> dict:
    """Deterministic non-overlapping date-block bootstrap of day-weighted score improvement."""
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return {"n": 0}
    idx = idx[np.lexsort((panel.ticker_id[idx], panel.dates[idx]))]
    dates = panel.dates[idx]
    boundaries = np.r_[0, np.flatnonzero(np.diff(dates)) + 1, len(idx)]
    y = panel.y_tolerant
    base = float(np.clip(base, 1e-9, 1 - 1e-9))
    base_log = lambda values: -(values * math.log(base) + (1 - values) * math.log(1 - base))
    daily: dict[str, dict[str, list[float]]] = {
        name: {"brier_improvement": [], "log_loss_improvement": []}
        for name in probabilities
    }
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        rows = idx[left:right]
        outcome = y[rows].astype(np.float64)
        base_brier = np.square(base - outcome)
        base_loss = base_log(outcome)
        for name, probability in probabilities.items():
            predicted = np.clip(probability[rows].astype(np.float64), 1e-9, 1 - 1e-9)
            daily[name]["brier_improvement"].append(
                float(np.mean(base_brier - np.square(predicted - outcome)))
            )
            model_loss = -(outcome * np.log(predicted) + (1 - outcome) * np.log(1 - predicted))
            daily[name]["log_loss_improvement"].append(float(np.mean(base_loss - model_loss)))

    n_dates = len(boundaries) - 1
    blocks = [np.arange(start, min(start + block_sessions, n_dates))
              for start in range(0, n_dates, block_sessions)]
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(blocks), size=(replicates, len(blocks)))
    result: dict[str, object] = {
        "method": "nonoverlapping_common-session_blocks_resampled_with_replacement",
        "block_sessions": block_sessions, "replicates": replicates, "seed": seed,
        "dates": n_dates, "blocks": len(blocks), "models": {},
    }
    for name, metrics in daily.items():
        model_out: dict[str, dict] = {}
        for metric_name, values_raw in metrics.items():
            values = np.asarray(values_raw, dtype=np.float64)
            block_sums = np.asarray([values[block].sum() for block in blocks])
            block_counts = np.asarray([len(block) for block in blocks], dtype=np.float64)
            estimates = block_sums[draws].sum(axis=1) / block_counts[draws].sum(axis=1)
            q = np.quantile(estimates, [0.025, 0.5, 0.975])
            model_out[metric_name] = {
                "day_weighted_point": float(values.mean()),
                "bootstrap_p2_5": float(q[0]), "bootstrap_median": float(q[1]),
                "bootstrap_p97_5": float(q[2]),
            }
        result["models"][name] = model_out
    return result


def by_name_distribution(
    panel: Panel, mask: np.ndarray, probability: np.ndarray, base: float,
) -> dict:
    """Distributional by-name diagnostic; avoids turning replay winners into a ticker screen."""
    idx = np.flatnonzero(mask)
    if len(idx) == 0:
        return {"names": 0}
    idx = idx[np.lexsort((panel.dates[idx], panel.ticker_id[idx]))]
    names = panel.ticker_id[idx]
    boundaries = np.r_[0, np.flatnonzero(np.diff(names)) + 1, len(idx)]
    counts: list[int] = []
    rates: list[float] = []
    improvements: list[float] = []
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        rows = idx[left:right]
        outcome = panel.y_tolerant[rows].astype(np.float64)
        predicted = probability[rows].astype(np.float64)
        counts.append(len(rows))
        rates.append(float(outcome.mean()))
        improvements.append(float(np.mean(np.square(base - outcome) - np.square(predicted - outcome))))
    quantile_levels = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
    return {
        "names": len(counts), "ticker_listing_suppressed": "diagnostic_not_a_replay_winner_screen",
        "quantiles": quantile_levels,
        "candidate_rows": np.quantile(counts, quantile_levels).tolist(),
        "event_rate": np.quantile(rates, quantile_levels).tolist(),
        "brier_improvement": np.quantile(improvements, quantile_levels).tolist(),
    }


# ── Forward full-population probability/grade contract ────────────────────────

PROBABILITY_KEY = (
    "signal_date", "ticker", "model_version", "limit_definition", "entry_rule",
)
GRADE_KEY = PROBABILITY_KEY + ("grade_kind", "horizon")
SNAPSHOT_KEY = (
    "signal_date", "model_version", "limit_definition", "entry_rule", "universe_id",
)
PROBABILITY_REQUIRED = {
    *PROBABILITY_KEY, "decision_available_at", "entry_session", "probability", "era", "board",
    "universe_id", "universe_size", "config_hash", "source_hash", "definition_hash",
    "model_hash", "fillable_state", "selection_state", "selection_rank", "outcome_state",
    "authority",
}
GRADE_COMMON_REQUIRED = {
    *GRADE_KEY, "entry_session", "graded_at", "authority", "event_outcome",
}
EVENT_GRADE_REQUIRED = {
    *GRADE_COMMON_REQUIRED, "fill_decided_at", "entry_fill_state", "event_state",
}
EXECUTION_GRADE_REQUIRED = {
    *GRADE_COMMON_REQUIRED, "fill_decided_at", "entry_fill_state", "exit_state",
    "scheduled_exit_session", "realized_exit_session", "gross_return", "net_return_bps_grid",
    "book_contribution_return",
}


def _row_key(row: dict, fields: Sequence[str]) -> tuple:
    missing = [field for field in fields if field not in row]
    if missing:
        raise IntegrityError(f"ledger key fields missing: {missing}")
    return tuple(row[field] for field in fields)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise IntegrityError(f"invalid JSONL {path}:{line_no}: {exc}") from exc
    return rows


def atomic_write_jsonl(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(_json_bytes(row).decode("utf-8") + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _is_sha256(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def _validate_probability_store(rows: Sequence[dict], *, label: str) -> dict[tuple, dict]:
    """Validate complete, expected-model snapshots and return the stable-key index."""
    by_key: dict[tuple, dict] = {}
    snapshot_sets: dict[tuple, dict[str, list[dict]]] = {}
    for row in rows:
        missing = sorted(PROBABILITY_REQUIRED - set(row))
        if missing:
            raise IntegrityError(f"{label} probability row missing fields: {missing}")
        key = _row_key(row, PROBABILITY_KEY)
        if key in by_key:
            raise IntegrityError(f"duplicate probability key in {label}: {key}")
        by_key[key] = row
        if row["authority"] != "context_display_only":
            raise IntegrityError(f"invalid probability authority: {row['authority']}")
        if isinstance(row["probability"], bool) or not isinstance(row["probability"], (int, float)):
            raise IntegrityError("probability must be a JSON number")
        probability = float(row["probability"])
        if not math.isfinite(probability) or not 0.0 < probability < 1.0:
            raise IntegrityError("probability must be finite and strictly between zero and one")
        if row["model_version"] not in EXPECTED_FORWARD_MODEL_VERSIONS:
            raise IntegrityError(f"unexpected forward model_version: {row['model_version']}")
        if row["fillable_state"] != "unknown_pending":
            raise IntegrityError("immutable probability fillability must stay unknown_pending")
        if row["outcome_state"] != "pending":
            raise IntegrityError("probability rows are immutable pre-grade state and must stay pending")
        if row["selection_state"] not in {"selected_top20", "not_selected_no_fire"}:
            raise IntegrityError(f"invalid selection_state: {row['selection_state']}")
        if not isinstance(row["universe_size"], int) or isinstance(row["universe_size"], bool) \
                or row["universe_size"] <= 0:
            raise IntegrityError("universe_size must be a positive integer")
        if not isinstance(row["selection_rank"], int) or isinstance(row["selection_rank"], bool) \
                or not 1 <= row["selection_rank"] <= row["universe_size"]:
            raise IntegrityError("selection_rank is outside the declared universe")
        expected_selection = ("selected_top20" if row["selection_rank"] <= 20
                              else "not_selected_no_fire")
        if row["selection_state"] != expected_selection:
            raise IntegrityError("selection_state contradicts the immutable selection_rank")
        for hash_field in ("universe_id", "config_hash", "source_hash", "definition_hash",
                           "model_hash"):
            if not _is_sha256(row[hash_field]):
                raise IntegrityError(f"{hash_field} is not a lowercase SHA-256 digest")
        snapshot_id = (row["signal_date"], row["limit_definition"], row["entry_rule"])
        snapshot_sets.setdefault(snapshot_id, {}).setdefault(row["model_version"], []).append(row)

    for snapshot_id, models in snapshot_sets.items():
        if set(models) != EXPECTED_FORWARD_MODEL_VERSIONS:
            raise IntegrityError(
                f"snapshot expected model set mismatch {snapshot_id}: "
                f"got={sorted(models)} expected={sorted(EXPECTED_FORWARD_MODEL_VERSIONS)}"
            )
        reference_tickers: list[str] | None = None
        reference_entry: str | None = None
        for model_version in sorted(models):
            group = models[model_version]
            sizes = {row["universe_size"] for row in group}
            tickers = sorted(row["ticker"] for row in group)
            if len(sizes) != 1 or len(group) != int(next(iter(sizes))) \
                    or len(tickers) != len(set(tickers)):
                raise IntegrityError(
                    f"incomplete/non-unique full-pop snapshot {snapshot_id}/{model_version}: "
                    f"rows={len(group)} sizes={sorted(sizes)} unique_tickers={len(set(tickers))}"
                )
            expected_universe_id = canonical_hash({
                "signal_date": snapshot_id[0], "tickers": tickers,
            })
            if {row["universe_id"] for row in group} != {expected_universe_id}:
                raise IntegrityError(
                    f"universe_id does not recompute for {snapshot_id}/{model_version}"
                )
            entry_sessions = {row["entry_session"] for row in group}
            if len(entry_sessions) != 1:
                raise IntegrityError(f"entry_session is inconsistent inside snapshot {snapshot_id}")
            entry_session = next(iter(entry_sessions))
            if reference_tickers is not None and tickers != reference_tickers:
                raise IntegrityError(f"model populations differ inside snapshot {snapshot_id}")
            if reference_entry is not None and entry_session != reference_entry:
                raise IntegrityError(f"model entry sessions differ inside snapshot {snapshot_id}")
            reference_tickers = tickers
            reference_entry = entry_session
    return by_key


def append_probability_snapshot(path: Path, rows: Sequence[dict], *, lane: str) -> int:
    """Full-pop keep-first append contract for a caller in the (unwired) nightly lane."""
    if lane != "nightly":
        raise IntegrityError("probability ledger may advance only in lane='nightly'")
    incoming = [dict(row) for row in rows]
    _validate_probability_store(incoming, label="incoming")
    existing = load_jsonl(path)
    by_key = _validate_probability_store(existing, label="existing") if existing else {}
    additions: list[dict] = []
    for row in incoming:
        key = _row_key(row, PROBABILITY_KEY)
        prior = by_key.get(key)
        if prior is not None:
            if canonical_hash(prior) != canonical_hash(row):
                # entry_session is deliberately payload, not identity: a calendar correction is
                # an attempted mutation of the same prediction and cannot create a second row.
                raise IntegrityError(f"keep-first probability mutation refused: {key}")
            continue
        additions.append(row)
    combined = [*existing, *additions]
    _validate_probability_store(combined, label="combined")
    sessions = {row["signal_date"] for row in combined}
    if len(sessions) > LEDGER_JSONL_MAX_SESSIONS:
        raise IntegrityError(
            "JSONL bridge session cap exceeded; migrate to normalized monthly Parquet "
            f"before session {len(sessions)}"
        )
    if additions:
        atomic_write_jsonl(path, combined)
    return len(additions)


def append_probability_grades(
    probability_path: Path, grade_path: Path, rows: Sequence[dict], *, lane: str,
    observed_calendar_days: np.ndarray,
) -> int:
    """Nightly-only grade append kept physically and semantically separate from probabilities."""
    if lane != "nightly":
        raise IntegrityError("probability grades may advance only in lane='nightly'")
    probability_rows = load_jsonl(probability_path)
    probabilities = _validate_probability_store(probability_rows, label="probability store")
    observed = np.asarray(observed_calendar_days, dtype=np.int32)
    if len(observed) == 0 or bool(np.any(np.diff(observed) <= 0)):
        raise IntegrityError("grade requires a nonempty monotonic observed market-session index")
    observed_pos = {int(day): i for i, day in enumerate(observed)}
    existing = load_jsonl(grade_path)
    by_key: dict[tuple, dict] = {}

    def validate_grade(row: dict, *, label: str) -> tuple:
        grade_kind = row.get("grade_kind")
        required = (EVENT_GRADE_REQUIRED if grade_kind == "event" else
                    EXECUTION_GRADE_REQUIRED if grade_kind == "execution_return" else None)
        if required is None:
            raise IntegrityError(f"invalid grade_kind in {label}: {grade_kind}")
        missing = sorted(required - set(row))
        if missing:
            raise IntegrityError(f"{label} grade row missing fields: {missing}")
        if row["authority"] != "context_display_only":
            raise IntegrityError(f"invalid grade authority: {row['authority']}")
        probability_key = _row_key(row, PROBABILITY_KEY)
        probability_row = probabilities.get(probability_key)
        if probability_row is None:
            raise IntegrityError(f"grade has no immutable probability row: {probability_key}")
        if row["entry_session"] != probability_row["entry_session"]:
            raise IntegrityError("grade entry_session contradicts immutable probability payload")
        if row["entry_fill_state"] not in TERMINAL_FILLABILITY:
            raise IntegrityError(f"grade has invalid terminal fillability: {row['entry_fill_state']}")
        if not isinstance(row["event_outcome"], bool):
            raise IntegrityError("grade event_outcome must be boolean")
        try:
            signal_pos = observed_pos[int(_day(row["signal_date"]))]
            entry_pos = observed_pos[int(_day(row["entry_session"]))]
        except KeyError as exc:
            raise IntegrityError(f"grade clock is not an exact observed market session: {exc}") from exc
        if entry_pos != signal_pos + 1:
            raise IntegrityError("grade entry_session is not the exact observed successor of signal_date")
        if grade_kind == "event":
            if row["horizon"] != "EVENT_D":
                raise IntegrityError("event grades must use horizon='EVENT_D'")
            if row["event_state"] not in {
                "observed_event", "observed_non_event", "missing_halted_non_event",
            }:
                raise IntegrityError(f"invalid event_state: {row['event_state']}")
        else:
            if probability_row["selection_state"] != "selected_top20":
                raise IntegrityError("execution/return grade is allowed only for a selected order")
            horizon_text = str(row["horizon"])
            if horizon_text not in {f"H{h}_next_open" for h in HORIZONS}:
                raise IntegrityError(f"invalid execution grade horizon: {horizon_text}")
            horizon = int(horizon_text.removeprefix("H").split("_", 1)[0])
            try:
                scheduled_pos = observed_pos[int(_day(row["scheduled_exit_session"]))]
            except KeyError as exc:
                raise IntegrityError(
                    f"grade clock is not an exact observed market session: {exc}"
                ) from exc
            if scheduled_pos != entry_pos + horizon:
                raise IntegrityError(
                    "scheduled_exit_session is not the exact observed horizon successor"
                )
            if row["realized_exit_session"] is not None:
                realized_day = int(_day(row["realized_exit_session"]))
                if realized_day not in observed_pos or observed_pos[realized_day] < scheduled_pos:
                    raise IntegrityError(
                        "realized_exit_session is invalid/before the scheduled observed exit"
                    )
            expected_cost_keys = {str(cost) for cost in COST_BPS}
            if not isinstance(row["net_return_bps_grid"], dict) \
                    or set(row["net_return_bps_grid"]) != expected_cost_keys:
                raise IntegrityError("execution net-return grid must cover the frozen cost ruler")
            try:
                book_contribution = float(row["book_contribution_return"])
            except (TypeError, ValueError) as exc:
                raise IntegrityError("book_contribution_return must be numeric") from exc
            if not math.isfinite(book_contribution):
                raise IntegrityError("book_contribution_return must be finite")
            if row["entry_fill_state"] != "fillable_daily_proxy":
                expected_exit_state = (
                    "not_entered_queue_no_fill"
                    if row["entry_fill_state"] == "queue_required_no_fill"
                    else "not_entered_missing_halted_no_fill"
                )
                if row["gross_return"] is not None:
                    raise IntegrityError("selected-but-unfilled gross_return must be null, not flat")
                if row["realized_exit_session"] is not None:
                    raise IntegrityError("selected-but-unfilled row cannot have a realized exit")
                if row["exit_state"] != expected_exit_state:
                    raise IntegrityError(
                        "selected-but-unfilled row lacks its terminal no-fill exit_state"
                    )
                if book_contribution != 0.0:
                    raise IntegrityError("selected-but-unfilled book contribution must be cash zero")
                if any(value is not None for value in row["net_return_bps_grid"].values()):
                    raise IntegrityError("selected-but-unfilled conditional net returns must be null")
            else:
                if row["gross_return"] is None:
                    if book_contribution != 0.0:
                        raise IntegrityError("unresolved filled position must contribute cash zero")
                    if any(value is not None for value in row["net_return_bps_grid"].values()):
                        raise IntegrityError("unresolved filled conditional net returns must be null")
                else:
                    try:
                        gross_return = float(row["gross_return"])
                        net_returns = [
                            float(value) for value in row["net_return_bps_grid"].values()
                        ]
                    except (TypeError, ValueError) as exc:
                        raise IntegrityError("filled execution returns must be numeric") from exc
                    if not math.isfinite(gross_return) \
                            or not all(map(math.isfinite, net_returns)):
                        raise IntegrityError("filled execution returns must be finite")
                    if not math.isclose(book_contribution, gross_return, abs_tol=1e-12):
                        raise IntegrityError(
                            "resolved fill gross book contribution must equal gross_return"
                        )
        return _row_key(row, GRADE_KEY)

    for row in existing:
        key = validate_grade(row, label="existing")
        if key in by_key:
            raise IntegrityError(f"duplicate grade key in existing store: {key}")
        by_key[key] = row
    additions: list[dict] = []
    seen_incoming: set[tuple] = set()
    for row_raw in rows:
        row = dict(row_raw)
        key = validate_grade(row, label="incoming")
        if key in seen_incoming:
            raise IntegrityError(f"duplicate grade key in incoming rows: {key}")
        seen_incoming.add(key)
        prior = by_key.get(key)
        if prior is not None:
            if canonical_hash(prior) != canonical_hash(row):
                raise IntegrityError(f"keep-first grade mutation refused: {key}")
            continue
        by_key[key] = row
        additions.append(row)

    # Once a snapshot is event-graded, every emitted probability in that snapshot must receive
    # exactly one event grade.  Execution/return rows remain sparse and selected-order-only.
    event_snapshot_ids = {
        (row["signal_date"], row["limit_definition"], row["entry_rule"])
        for row in rows if row.get("grade_kind") == "event"
    }
    for snapshot_id in event_snapshot_ids:
        expected = {
            key for key, probability_row in probabilities.items()
            if (probability_row["signal_date"], probability_row["limit_definition"],
                probability_row["entry_rule"]) == snapshot_id
        }
        graded = {
            key[:len(PROBABILITY_KEY)] for key in by_key
            if key[len(PROBABILITY_KEY)] == "event"
            and (key[0], key[3], key[4]) == snapshot_id
        }
        if graded != expected:
            raise IntegrityError(
                f"event grade coverage incomplete for {snapshot_id}: "
                f"graded={len(graded)} expected={len(expected)}"
            )
    if additions:
        atomic_write_jsonl(grade_path, [*existing, *additions])
    return len(additions)


def frozen_seed_entry_session(after_day: int) -> int:
    """Return only the construction-map-pinned seed session; recurring future logic fails closed."""
    if int(after_day) != int(_day(PROSPECTIVE_SEED_SIGNAL_DATE)):
        raise IntegrityError(
            "no authoritative annual exchange calendar is wired for recurring advancement"
        )
    return _day(PROSPECTIVE_SEED_ENTRY_SESSION)


def build_forward_seed(
    latest_rows: list[dict], models: Sequence[LogisticModel | EqualRankModel], *, config_hash: str,
    source_hash: str,
) -> list[dict]:
    if not latest_rows:
        return []
    signal_days = {int(row["signal_day"]) for row in latest_rows}
    if len(signal_days) != 1:
        raise IntegrityError(f"prospective seed spans multiple signal dates: {signal_days}")
    signal_day = signal_days.pop()
    entry_day = frozen_seed_entry_session(signal_day)
    tickers = sorted(row["ticker"] for row in latest_rows)
    universe_id = canonical_hash({"signal_date": _iso(signal_day), "tickers": tickers})
    definition_hash = canonical_hash({
        "limit_definition": "tolerant_0.2pct_primary",
        "entry_clock": CONFIG["entry_clock"],
        "outcome_clock": CONFIG["outcome_clock"],
        "queue_rule": CONFIG["queue_rule"],
        "exit_rule": CONFIG["exit_rule"],
    })
    rows: list[dict] = []
    for model in models:
        model_receipt = model.receipt()
        # Rank separately inside each board/era while retaining every eligible name.
        scored: list[tuple[dict, float]] = []
        for raw in latest_rows:
            probability = float(model.probability(np.asarray([raw["x"]]))[0])
            scored.append((raw, probability))
        rank_by_ticker: dict[str, int] = {}
        for era in sorted({raw["era"] for raw, _ in scored}):
            group = [(raw, p) for raw, p in scored if raw["era"] == era]
            group.sort(key=lambda pair: (-pair[1], pair[0]["ticker"]))
            for rank, (raw, _) in enumerate(group, 1):
                rank_by_ticker[raw["ticker"]] = rank
        for raw, probability in sorted(scored, key=lambda pair: pair[0]["ticker"]):
            rank = rank_by_ticker[raw["ticker"]]
            rows.append({
                "artifact_kind": "honest_prospective_seed_not_live_history",
                "signal_date": _iso(signal_day),
                "decision_available_at": f"{_iso(signal_day)}T15:00:00+08:00",
                "entry_session": _iso(entry_day),
                "entry_rule": "opening_auction_order_queue_cushion_0.2pct",
                "ticker": raw["ticker"], "board": raw["board"], "era": raw["era"],
                "probability": probability, "model_version": f"{MODEL_VERSION}:{model.name}",
                "limit_definition": "tolerant_0.2pct_primary", "universe_id": universe_id,
                "universe_size": len(latest_rows), "config_hash": config_hash,
                "source_hash": source_hash, "definition_hash": definition_hash,
                "model_hash": model_receipt["model_hash"],
                "fillable_state": "unknown_pending", "selection_rank": rank,
                "selection_state": "selected_top20" if rank <= 20 else "not_selected_no_fire",
                "outcome_state": "pending", "authority": "context_display_only",
                "entry_calendar_source": "construction_map_pinned_2026_08_10_seed_only_not_recurring_authority",
                "packet_receipt_date": "2026-08-08",
            })
    keys = [_row_key(row, PROBABILITY_KEY) for row in rows]
    if len(keys) != len(set(keys)):
        raise IntegrityError("prospective seed contains duplicate probability keys")
    return rows


def _group_base(panel: Panel, split: np.ndarray, era_code: int, y: np.ndarray) -> float:
    calibration = (split == 2) & (panel.era == era_code)
    train = (split == 1) & (panel.era == era_code)
    fallback = float(y[split == 2].mean()) if (split == 2).any() else float(y.mean())
    return base_probability(y, calibration if calibration.any() else train, fallback)


def fit_equal_rank_blend(
    panel: Panel, train_mask: np.ndarray, calibration_mask: np.ndarray,
) -> tuple[np.ndarray, EqualRankModel]:
    """Five equal-weight train-CDF ranks, mapped to probability on calibration only."""
    train_idx = np.flatnonzero(train_mask)
    quantiles = np.linspace(0.0, 1.0, 101)
    knots = np.column_stack([
        np.quantile(panel.x[train_idx, col].astype(np.float64), quantiles)
        for col in O1_COLS
    ])
    model = EqualRankModel(
        name="O1_fixed_equal_rank_blend", columns=O1_COLS, knots=knots,
        calibration=np.asarray([0.0, 1.0]),
    )
    cal_idx = np.flatnonzero(calibration_mask)
    model.calibration = fit_two_parameter_logistic(
        model.raw_logit(panel.x[cal_idx]), panel.y_tolerant[cal_idx]
    )
    probability = score_panel(model, panel.x)
    return probability, model


def univariate_fixed_bins(panel: Panel, train_mask: np.ndarray,
                          groups: dict[str, np.ndarray]) -> dict:
    """Train-frozen deciles for each O1 axis; every bin prints, including nonlinear tails."""
    train_idx = np.flatnonzero(train_mask)
    output: dict[str, dict] = {}
    for col in O1_COLS:
        feature = FEATURE_NAMES[col]
        edges = np.quantile(panel.x[train_idx, col].astype(np.float64), np.linspace(0, 1, 11))
        internal = edges[1:-1]
        feature_out = {"train_edges": edges.tolist(), "groups": {}}
        for key, mask in groups.items():
            # Print the frozen replay/audit/2015 cells; train/cal cells are already model-fit receipts.
            if not ("historical_replay" in key or "vendor_audit" in key or key.startswith("stress_2015")):
                continue
            idx = np.flatnonzero(mask)
            values = panel.x[idx, col]
            bins = np.searchsorted(internal, values, side="right")
            base = float(panel.y_tolerant[idx].mean()) if len(idx) else 0.0
            cells = []
            for bin_no in range(10):
                rows = idx[bins == bin_no]
                rate = float(panel.y_tolerant[rows].mean()) if len(rows) else None
                cells.append({"bin": bin_no, "n": int(len(rows)),
                              "events": int(panel.y_tolerant[rows].sum()),
                              "rate": rate, "lift_vs_group_base": (rate / base if rate is not None and base > 0 else None)})
            feature_out["groups"][key] = {"base_rate": base, "bins": cells}
        output[feature] = feature_out
    return output


def base_ladder(panel: Panel, split: np.ndarray) -> dict:
    out: dict[str, dict] = {}
    for era_code, era_name in ERA_NAMES.items():
        out[era_name] = {}
        for code in (1, 2, 3, 4):
            mask = (split == code) & (panel.era == era_code)
            if not mask.any():
                continue
            out[era_name][SPLIT_NAMES[code]] = {
                "n": int(mask.sum()), "tolerant_events": int(panel.y_tolerant[mask].sum()),
                "tolerant_rate": float(panel.y_tolerant[mask].mean()),
                "strict_events": int(panel.y_strict[mask].sum()),
                "strict_rate": float(panel.y_strict[mask].mean()),
                "missing_halted_rate": float((panel.target_state[mask] == 1).mean()),
            }
    return out


def build_receipt(panel: Panel, latest_rows: list[dict], source_stats: dict,
                  calendar_days: np.ndarray) -> tuple[dict, list[dict]]:
    started = time.monotonic()
    split, purge = split_codes(panel.dates, calendar_days)
    train_main = (split == 1) & (panel.era == 0)
    calibration_main = (split == 2) & (panel.era == 0)
    if int(train_main.sum()) == 0 or int(calibration_main.sum()) == 0:
        raise IntegrityError("frozen main train/calibration blocks are empty")

    o1 = fit_logistic(panel.x, panel.y_tolerant, train_main, O1_COLS, name="O1_five_axis")
    o3 = fit_logistic(panel.x, panel.y_tolerant, train_main, O3_COLS, name="O3_washout_transition")
    calibrate_model(o1, panel.x, panel.y_tolerant, calibration_main)
    calibrate_model(o3, panel.x, panel.y_tolerant, calibration_main)
    p_o1 = score_panel(o1, panel.x)
    p_o3 = score_panel(o3, panel.x)
    p_o1_raw = score_panel(o1, panel.x, calibrated=False)
    p_o3_raw = score_panel(o3, panel.x, calibrated=False)
    p_rank, rank_model = fit_equal_rank_blend(panel, train_main, calibration_main)

    groups_out: dict[str, dict] = {}
    groups = evaluation_groups(panel, split)
    for key, mask in groups.items():
        era_code = int(panel.era[np.flatnonzero(mask)[0]])
        stress = key.startswith("stress_2015")
        o1_prob = p_o1_raw if stress else p_o1
        o3_prob = p_o3_raw if stress else p_o3
        if stress:
            # The 2015 slice is in-sample descriptive, but its comparator must still avoid a
            # future 2020-23 base rate.  Use the same 2011-19 fit population as the raw logits.
            stress_reference = (split == 1) & (panel.era == era_code)
            base_tol = float(panel.y_tolerant[stress_reference].mean())
            base_strict = float(panel.y_strict[stress_reference].mean())
        else:
            base_tol = _group_base(panel, split, era_code, panel.y_tolerant)
            base_strict = _group_base(panel, split, era_code, panel.y_strict)
        idx = np.flatnonzero(mask)
        observed = mask & (panel.target_state == 0)
        block = {
            "honesty_label": ("in_sample_descriptive_no_future_calibration" if stress else
                              key.split(":", 1)[0]),
            "population": {
                "n": int(mask.sum()),
                "observed_D": int((panel.target_state[idx] == 0).sum()),
                "missing_halted_D": int((panel.target_state[idx] == 1).sum()),
                "invalid_corporate_action_D": int((panel.target_state[idx] == 2).sum()),
            },
            "tolerant_primary": {
                "O1": probability_metrics(panel.y_tolerant[idx], o1_prob[idx], base_tol),
                "O3": probability_metrics(panel.y_tolerant[idx], o3_prob[idx], base_tol),
            },
            "strict_sensitivity_same_scores": {
                "O1": probability_metrics(panel.y_strict[idx], o1_prob[idx], base_strict),
                "O3": probability_metrics(panel.y_strict[idx], o3_prob[idx], base_strict),
            },
            "observed_D_only_sensitivity": {},
            "transport_status": (
                "locally_fit_and_calibrated_main" if era_code == 0 else
                "main_fit_main_calibration_transport_not_locally_calibrated"
            ),
        }
        if era_code == 3:
            block["transport_status"] += ":STAR_descriptive_only"
        if not stress:
            block["tolerant_primary"]["fixed_equal_rank_blend"] = probability_metrics(
                panel.y_tolerant[idx], p_rank[idx], base_tol
            )
            block["strict_sensitivity_same_scores"]["fixed_equal_rank_blend"] = probability_metrics(
                panel.y_strict[idx], p_rank[idx], base_strict
            )
        observed_idx = np.flatnonzero(observed)
        if len(observed_idx):
            obs_base = float(panel.y_tolerant[observed_idx].mean())
            block["observed_D_only_sensitivity"] = {
                "O1": probability_metrics(panel.y_tolerant[observed_idx], o1_prob[observed_idx], obs_base),
                "O3": probability_metrics(panel.y_tolerant[observed_idx], o3_prob[observed_idx], obs_base),
            }
            if not stress:
                block["observed_D_only_sensitivity"]["fixed_equal_rank_blend"] = probability_metrics(
                    panel.y_tolerant[observed_idx], p_rank[observed_idx], obs_base
                )
        # Top-K/return rulers are printed for replay, vendor audit, and 2015 stress; train/cal are
        # probability-fit receipts only to keep the packet/resource surface bounded.
        if stress or "historical_replay" in key or "vendor_audit" in key:
            block["topk_O1_tolerant"] = topk_metrics(
                panel, mask, o1_prob, panel.y_tolerant, calendar_days
            )
            block["topk_O3_tolerant"] = topk_metrics(
                panel, mask, o3_prob, panel.y_tolerant, calendar_days
            )
            if not stress:
                block["topk_fixed_equal_rank_tolerant"] = topk_metrics(
                    panel, mask, p_rank, panel.y_tolerant, calendar_days
                )
        groups_out[key] = block

    main_replay = groups_out.get("historical_replay_after_common_prior:main_10", {})
    main_audit = groups_out.get("vendor_audit:main_10", {})
    chinext_replay = groups_out.get("historical_replay_after_common_prior:chinext_20", {})
    o1_metric = main_replay.get("tolerant_primary", {}).get("O1", {})
    o3_metric = main_replay.get("tolerant_primary", {}).get("O3", {})

    def h1_sleeve_cell(block: dict, model_key: str, cost: int) -> dict:
        return (block.get(model_key, {}).get("top_20", {})
                .get("sequential_H1_fixed_K_sleeve_book", {}).get("cost_grid", {})
                .get(str(cost), {}))

    def event_cohort_cell(
        block: dict, model_key: str, horizon: int, cost: int,
    ) -> dict:
        return (block.get(model_key, {}).get("top_20", {})
                .get("event_level_cohort_returns", {}).get(f"H{horizon}_next_open", {})
                .get("cost_grid", {}).get(str(cost), {}))

    def robustly_positive(cell: dict) -> bool:
        bootstrap = cell.get("calendar_month_block_bootstrap", {})
        return bool(cell.get("day_weighted_fixed_sleeve_mean", -math.inf) > 0
                    and bootstrap.get("p2_5", -math.inf) > 0)

    o1_replay_cell = h1_sleeve_cell(main_replay, "topk_O1_tolerant", 60)
    o1_audit_cell = h1_sleeve_cell(main_audit, "topk_O1_tolerant", 60)
    o1_chinext_cell = h1_sleeve_cell(chinext_replay, "topk_O1_tolerant", 60)
    o3_replay_cell = h1_sleeve_cell(main_replay, "topk_O3_tolerant", 60)
    o3_audit_cell = h1_sleeve_cell(main_audit, "topk_O3_tolerant", 60)
    o3_chinext_cell = h1_sleeve_cell(chinext_replay, "topk_O3_tolerant", 60)
    rank_replay_h1_cell = h1_sleeve_cell(main_replay, "topk_fixed_equal_rank_tolerant", 60)
    rank_audit_h1_cell = h1_sleeve_cell(main_audit, "topk_fixed_equal_rank_tolerant", 60)
    rank_replay_h5_cell = event_cohort_cell(
        main_replay, "topk_fixed_equal_rank_tolerant", 5, 30
    )
    rank_audit_h5_cell = event_cohort_cell(
        main_audit, "topk_fixed_equal_rank_tolerant", 5, 30
    )

    o1_trade_go = bool(
        o1_metric.get("brier_improvement", 0) > 0
        and main_audit.get("tolerant_primary", {}).get("O1", {}).get("brier_improvement", 0) > 0
        and all(robustly_positive(cell) for cell in (
            o1_replay_cell, o1_audit_cell, o1_chinext_cell,
        ))
    )
    o3_survives = bool(
        o3_metric.get("brier", math.inf) < o1_metric.get("brier", -math.inf)
        and all(robustly_positive(cell) for cell in (
            o3_replay_cell, o3_audit_cell, o3_chinext_cell,
        ))
    )

    def flat_book_evidence(
        prefix: str, cell: dict, mean_key: str = "day_weighted_fixed_sleeve_mean",
    ) -> dict[str, float | None]:
        bootstrap = cell.get("calendar_month_block_bootstrap", {})
        return {
            f"{prefix}_mean": cell.get(mean_key),
            f"{prefix}_month_block_p2_5": bootstrap.get("p2_5"),
            f"{prefix}_month_block_p97_5": bootstrap.get("p97_5"),
            f"{prefix}_max_drawdown": cell.get("max_drawdown"),
        }

    univariate_receipt = univariate_fixed_bins(panel, train_main, groups)
    replay_univariate_key = "historical_replay_after_common_prior:main_10"

    def univariate_lift(feature: str, bin_no: int) -> float | None:
        cell = univariate_receipt[feature]["groups"][replay_univariate_key]["bins"][bin_no]
        return cell["lift_vs_group_base"]

    config_hash = canonical_hash(CONFIG)
    models: list[LogisticModel | EqualRankModel] = [o1, rank_model, o3]
    seed = build_forward_seed(latest_rows, models, config_hash=config_hash,
                              source_hash=source_stats["source_manifest_hash"])
    _validate_probability_store(seed, label="generated honest seed")
    seed_jsonl_bytes = sum(len(_json_bytes(row)) + 1 for row in seed)
    source_stats = dict(source_stats)
    source_stats.pop("runtime_panel_sec", None)  # tracked receipt must be byte-deterministic
    source_stats["candidate_rows"] = int(len(panel))
    source_stats["candidate_rows_by_target_state"] = {
        TARGET_STATE_NAMES[code]: int((panel.target_state == code).sum()) for code in TARGET_STATE_NAMES
    }
    source_stats["candidate_rows_by_board_era"] = {
        name: int((panel.era == code).sum()) for code, name in ERA_NAMES.items()
    }
    source_stats["candidate_exit_states_by_horizon"] = {
        f"H{horizon}_next_open": {
            EXIT_STATE_NAMES[state]: int((panel.exit_state[:, h_idx] == state).sum())
            for state in EXIT_STATE_NAMES
        }
        for h_idx, horizon in enumerate(HORIZONS)
    }
    source_stats["file_accounting"] = {
        "discovered_paths": source_stats["files_discovered"],
        "excluded_before_open_current_st": source_stats["files_current_st_excluded"],
        "excluded_before_open_bse": source_stats["files_bse_excluded"],
        "parquet_opened_and_read": source_stats["files_read"],
        "processing_errors": source_stats["files_error"],
        "volume_census_paths_read": source_stats["files_census_read"],
        "volume_census_errors": source_stats["files_census_error"],
        "current_run_balances": (
            source_stats["files_discovered"]
            == source_stats["files_current_st_excluded"]
            + source_stats["files_bse_excluded"]
            + source_stats["files_read"]
        ),
    }
    source_stats["current_st_policy"] = (
        f"current snapshot contains {source_stats['current_st_snapshot_names']} ST tickers; "
        f"{source_stats['files_current_st_excluded']} overlap nominal raw and are excluded across "
        "all dates; historical former-ST membership is unavailable, so residual historical ST "
        "contamination cannot be ruled out and no ST inference is made"
    )

    receipt = {
        "schema_version": "cn_onset_wave1_receipt.v1",
        "receipt_date": "2026-08-08",
        "authority": "context_display_only_no_rank_size_gate_trade_recommendation",
        "independence": "nominal_raw_and_current_engine_conventions_only_no_active_claude_wave1_output",
        "config": CONFIG, "config_hash": config_hash,
        "source_receipt": source_stats, "purge_receipt": purge,
        "models": {model.name: model.receipt() for model in models},
        "board_era_base_ladder": base_ladder(panel, split),
        "univariate_frozen_deciles": univariate_receipt,
        "groups": groups_out,
        "date_blocks": {
            "main_locked_replay": date_blocks(panel, (split == 3) & (panel.era == 0), p_o1, p_o3),
            "main_vendor_audit": date_blocks(panel, (split == 4) & (panel.era == 0), p_o1, p_o3),
        },
        "date_block_bootstrap": {
            "main_locked_replay": date_block_bootstrap(
                panel, (split == 3) & (panel.era == 0),
                {"fixed_equal_rank_blend": p_rank, "O1": p_o1, "O3": p_o3},
                _group_base(panel, split, 0, panel.y_tolerant),
            ),
            "main_vendor_audit": date_block_bootstrap(
                panel, (split == 4) & (panel.era == 0),
                {"fixed_equal_rank_blend": p_rank, "O1": p_o1, "O3": p_o3},
                _group_base(panel, split, 0, panel.y_tolerant),
            ),
        },
        "by_name_distribution": {
            "main_locked_replay_O1": by_name_distribution(
                panel, (split == 3) & (panel.era == 0), p_o1,
                _group_base(panel, split, 0, panel.y_tolerant),
            ),
            "main_locked_replay_O3": by_name_distribution(
                panel, (split == 3) & (panel.era == 0), p_o3,
                _group_base(panel, split, 0, panel.y_tolerant),
            ),
            "main_vendor_audit_O1": by_name_distribution(
                panel, (split == 4) & (panel.era == 0), p_o1,
                _group_base(panel, split, 0, panel.y_tolerant),
            ),
            "main_vendor_audit_O3": by_name_distribution(
                panel, (split == 4) & (panel.era == 0), p_o3,
                _group_base(panel, split, 0, panel.y_tolerant),
            ),
        },
        "forward_ledger_contract": {
            "probability_key": list(PROBABILITY_KEY), "grade_key": list(GRADE_KEY),
            "probability_required": sorted(PROBABILITY_REQUIRED),
            "event_grade_required": sorted(EVENT_GRADE_REQUIRED),
            "execution_grade_required": sorted(EXECUTION_GRADE_REQUIRED),
            "expected_model_versions": sorted(EXPECTED_FORWARD_MODEL_VERSIONS),
            "required_caller_lane": "nightly", "append_grade_separation": True,
            "implementation_status": "CONTRACT_AND_ONE_HONEST_SEED_ONLY",
            "recurring_nightly_advancer": "UNBUILT_UNTESTED",
            "grader_integration": "UNBUILT_UNTESTED_NO_FABRICATED_GRADES",
            "production_runner_contract": "UNBUILT_MUST_LOAD_FROZEN_PARAMETERS_WITH_DYNAMIC_LATEST_COMPLETE_OBSERVED_SESSION_NEVER_REFIT_OR_IMPORT_FROZEN_RESEARCH_BUILDERS",
            "future_entry_calendar": "FROZEN_2026_08_10_SEED_ONLY_RECURRING_AUTHORITY_UNBUILT_FAIL_CLOSED",
            "grade_calendar": "exact_observed_market_session_index_required_by_helper",
            "storage_mode": "JSONL_CAPPED_TEN_SESSION_BRIDGE",
            "jsonl_max_snapshot_sessions": LEDGER_JSONL_MAX_SESSIONS,
            "seed_jsonl_bytes": seed_jsonl_bytes,
            "estimated_ten_session_jsonl_bytes": seed_jsonl_bytes * LEDGER_JSONL_MAX_SESSIONS,
            "normalized_monthly_parquet_partitions": "UNBUILT_UNTESTED",
            "keep_first_mutation_policy": "contradiction_raises_integrity_error",
            "stable_prediction_identity": "signal_date+ticker+model_version+limit_definition+entry_rule; entry_session_is_immutable_payload",
            "grade_semantics": "one_event_grade_per_probability; execution_return_grades_per_horizon_selected_orders_only; selected_unfilled_gross_is_null_and_book_contribution_is_zero",
            "complete_population": "selected_and_not_selected_no_fire_rows",
            "pre_entry_fillability": "unknown_pending",
            "terminal_three_way_fillability": sorted(TERMINAL_FILLABILITY),
            "prospective_seed_rows": len(seed),
            "prospective_seed_signal_date": seed[0]["signal_date"] if seed else None,
            "prospective_seed_entry_session": seed[0]["entry_session"] if seed else None,
            "retrospective_rows_seeded": 0,
        },
        "ore_ledger": {
            "O1_five_axis": {
                "measured": "fixed-L2 logistic over five D-1 name-local axes; tolerant D first-board; exact-calendar missing as competing zero; D-open queue rule; forced-daily top-K; H1/H3/H5 exact opens",
                "verdict": ("CONTEXT_ONLY_SURVIVES_NOT_PROMOTED" if o1_trade_go else
                            "NO_GO_FOR_THIS_FIXED_L2_FILLABLE_TRADE_RULE_CONTEXT_MODEL_RETAINED"),
                "adjudication_rule": "positive Brier improvement in main replay+vendor and positive lower 2.5% month-block bound for top20 H1/60bp in main replay, main vendor, and ChiNext-20 transport",
                "evidence": {
                    **flat_book_evidence("main_replay_top20_H1_60bp", o1_replay_cell),
                    **flat_book_evidence("main_vendor_top20_H1_60bp", o1_audit_cell),
                    **flat_book_evidence("chinext20_replay_top20_H1_60bp", o1_chinext_cell),
                },
                "remaining_untested": UNTESTED_VARIANTS,
            },
            "O1_fixed_equal_rank_blend": {
                "measured": "equal 20% train-frozen percentile ranks for the five O1 axes, main-calibration probability map, sequential fixed-20-sleeve H1 book; H5 is event-cohort diagnostic only",
                "verdict": "KILL_THIS_FIXED_EQUAL_RANK_H1_BOOK_ONLY_H5_EVENT_SEAM_NONPORTFOLIO_AND_VENDOR_UNSTABLE",
                "adjudication_rule": "strategy verdict uses sequential no-duplicate fixed-sleeve H1 only; H5 cannot support a portfolio claim",
                "evidence": {
                    **flat_book_evidence("main_replay_top20_H1_60bp", rank_replay_h1_cell),
                    **flat_book_evidence("main_vendor_top20_H1_60bp", rank_audit_h1_cell),
                    **flat_book_evidence(
                        "main_replay_EVENT_COHORT_top20_H5_30bp", rank_replay_h5_cell,
                        mean_key="day_weighted_all_candidate_mean",
                    ),
                    **flat_book_evidence(
                        "main_vendor_EVENT_COHORT_top20_H5_30bp", rank_audit_h5_cell,
                        mean_key="day_weighted_all_candidate_mean",
                    ),
                },
                "remaining_untested": UNTESTED_VARIANTS,
            },
            "O1_univariate_U_shape_ore": {
                "measured": "train-frozen single-feature deciles; both runup_5 and gap_pct have elevated lowest and highest locked-replay deciles",
                "verdict": "ORE_SEAM_RETAINED_NOT_A_TRADE_RULE_TWO_ARCHETYPE_MIXTURE_UNTESTED",
                "evidence": {
                    "runup_5_bin0_lift": univariate_lift("runup_5", 0),
                    "runup_5_bin9_lift": univariate_lift("runup_5", 9),
                    "gap_pct_bin0_lift": univariate_lift("gap_pct", 0),
                    "gap_pct_bin9_lift": univariate_lift("gap_pct", 9),
                },
                "evidence_format": "lift_multiple",
                "remaining_untested": [
                    "two-archetype washout-versus-momentum mixture with separately frozen gates",
                    *UNTESTED_VARIANTS,
                ],
            },
            "O3_washout_transition": {
                "measured": "O1 plus frozen drawdown/MA200/reversal bases and runup/volume interactions under the same forced-daily top-K ruler",
                "verdict": ("CHALLENGER_SURVIVES_CONTEXT_ONLY" if o3_survives else
                            "KILL_THIS_FIXED_O3_CHALLENGER_ONLY"),
                "adjudication_rule": "lower Brier than O1 plus positive lower 2.5% month-block bound for top20 H1/60bp in main replay, main vendor, and ChiNext-20 transport",
                "evidence": {
                    **flat_book_evidence("main_replay_top20_H1_60bp", o3_replay_cell),
                    **flat_book_evidence("main_vendor_top20_H1_60bp", o3_audit_cell),
                    **flat_book_evidence("chinext20_replay_top20_H1_60bp", o3_chinext_cell),
                },
                "remaining_untested": [
                    "alternative washout horizons and nonlinear transition bins",
                    "point-in-time reversal membership and catalyst-conditioned base transition",
                    *UNTESTED_VARIANTS,
                ],
            },
        },
        "limitations": [
            "survivorship-biased curated raw store; delisted/missing small caps absent",
            "historical ST membership unavailable; current-ST exclusion cannot heal former-ST rows",
            "five-axis complete-case eligibility excludes early-history/incomplete feature rows; the source receipt quantifies those rows",
            "daily OHLC cannot observe auction queue, partial fill, first-touch, or intraday exit",
            "the observed-session clock is set-attested to a >=50-name raw-index consensus, but is not an official exchange master calendar",
            "missing or zero-volume exact sessions are primary event-zero/cash-zero competing states; observed-only is sensitivity",
            "2015 stress is in-sample descriptive and is not an independent confirmation",
            "replay follows common-prior sign exposure and is never labelled unseen test",
            "strict definition is evaluated with tolerant-trained scores as sensitivity, not a second tuned model",
            "sector heat excluded because current sector membership applied historically leaks",
            "H3/H5 returns are overlapping event-cohort diagnostics, not capital books; a fixed-capital multi-session sleeve remains unbuilt",
            "H1 fixed-sleeve returns are attributed to entry cohorts; any lower-limit carry count must be read beside the compounding proxy",
            "forward seed is one honest ungraded snapshot, not prospective performance history",
            "recurring nightly probability advancement and grading are not wired; helpers only enforce the contract when called",
            "frozen research builders stop at 2026-08-07 and are forbidden as a recurring runner; a future runner must load frozen parameters against a dynamically discovered latest-complete observed session without refitting",
        ],
        "untested_variants": UNTESTED_VARIANTS,
    }
    # Runtime is console-only.  Hash is over deterministic tracked content.
    receipt["receipt_hash"] = canonical_hash(receipt)
    print(f"ONSET receipt/model phase: {time.monotonic() - started:.1f}s", flush=True)
    return receipt, seed


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{100.0 * value:.3f}%"


def _num(value: float | None, digits: int = 4) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def render_markdown(receipt: dict) -> str:
    source = receipt["source_receipt"]
    overlap = source["zt_pool_universe_limit"]
    groups = receipt["groups"]
    main_replay = groups.get("historical_replay_after_common_prior:main_10", {})
    main_audit = groups.get("vendor_audit:main_10", {})
    lines = [
        "# CN limit-move ONSET Wave-1 — O1 core and O3 challenger",
        "",
        "**Date:** 2026-08-08",
        "**Authority:** context / display / audit only — no rank, sizing, gate, or trade recommendation",
        f"**Receipt hash:** `{receipt['receipt_hash']}`",
        "",
        "## Verdict",
        "",
    ]
    for name, ore in receipt["ore_ledger"].items():
        lines.extend([
            f"### {name}", "",
            f"- **Verdict:** `{ore['verdict']}`",
            f"- **Measured construction:** {ore['measured']}",
            "- This verdict closes only the measured construction; its remaining variants are preserved below.",
            "",
        ])
        if ore.get("adjudication_rule"):
            lines.append(f"- **Adjudication rule:** {ore['adjudication_rule']}")
        if ore.get("evidence"):
            for evidence_name, evidence_value in ore["evidence"].items():
                formatted = (_num(evidence_value, 3) + "×"
                             if ore.get("evidence_format") == "lift_multiple"
                             else _pct(evidence_value))
                lines.append(f"- `{evidence_name}`: **{formatted}**")
            lines.append("")
    lines.extend([
        "## Frozen clock and denominator",
        "",
        "- Every candidate is frozen after the exact common-calendar D−1 close.",
        "- D is the exact next observed market session from the completeness-pinned `600519.SS` index. The clock must include 2014-12-25 and the other frozen anchors; the incomplete Shanghai Composite file is not used.",
        "- A missing/halted or zero-volume D bar remains in the primary denominator as event=0, no fill, and cash return=0; it never jumps to a later ticker resumption.",
        "- D open at/within 0.2% of the reconstructed upper limit is queue-required and receives no fill.",
        "- A D purchase exits no earlier than exact D+1/D+3/D+5 open. A missing intervening or scheduled session is cash=0 and never jumps to a resumption; only an observed lower-limit-locked scheduled open may carry one exact session at a time.",
        "- Sector heat is excluded from the core because current sector membership applied backward is historical lookahead.",
        "",
        "## Source and universe receipt",
        "",
        f"- Discovered **{source['files_discovered']:,}** parquet paths. Before opening, excluded **{source['files_current_st_excluded']:,}** current-ST overlap and **{source['files_bse_excluded']:,}** BSE paths; then opened/read **{source['files_read']:,}** with **{source['files_error']:,}** processing errors. Accounting balance: **{str(source['file_accounting']['current_run_balances']).lower()}**.",
        f"- Observed clock: `{source['calendar_receipt']['source']}` with **{source['calendar_receipt']['sessions_2011_through_as_of']:,}** sessions from 2011 through {ANALYSIS_END}; completeness anchors present: **{str(source['calendar_receipt']['all_completeness_anchors_present']).lower()}**.",
        f"- Clock consensus: the >=50-name raw-index support set has **{source['calendar_consensus_validation']['consensus_sessions']:,}** sessions and is set-identical to 600519 (**{source['calendar_consensus_validation']['missing_from_600519_reference']}** missing / **{source['calendar_consensus_validation']['extra_in_600519_reference']}** extra). 600519 itself has positive volume on **{source['calendar_consensus_validation']['reference_positive_volume_sessions']:,}** sessions and zero/missing volume on **{source['calendar_consensus_validation']['reference_zero_or_missing_volume_sessions']:,}** genuine sessions; reference volume is explicitly not a market-clock filter.",
        f"- Volume census across **{source['files_census_read']:,}** discovered files: the frozen 2011+ analysis window contains **{source['raw_rows_censused_analysis_window']:,}** raw rows, including **{source['raw_zero_volume_rows_analysis_window']:,}** exact zero-volume rows and **{source['raw_nonpositive_or_missing_volume_rows_analysis_window']:,}** nonpositive/missing-volume rows. The lifetime files contain **{source['raw_rows_censused_all_discovered']:,}** rows / **{source['raw_zero_volume_rows_all_discovered']:,}** zero-volume placeholders; that pre-2011 tail is outside this analysis. Zero-volume D−1 signal rows excluded: **{source['zero_volume_signal_rows_excluded']:,}**; zero-volume D targets retained as missing/no-fill: **{source['target_zero_volume_missing']:,}**.",
        f"- The current-ST snapshot contains **{source['current_st_snapshot_names']:,}** names, but only **{source['files_current_st_excluded']:,}** exists in nominal raw. Former-ST history remains unavailable.",
        f"- Full candidate denominator: **{source['candidate_rows']:,}** rows; panel footprint **{source['panel_mib']:.1f} MiB**.",
        f"- D−1 session rows lacking at least one frozen feature: **{source['feature_incomplete_rows']:,}**; they are excluded by the predeclared complete-case eligibility rule, not by a future outcome.",
        f"- D states: observed positive-volume **{source['candidate_rows_by_target_state']['observed']:,}**; missing/halted/zero-volume **{source['candidate_rows_by_target_state']['missing_halted']:,}** (absent **{source['target_missing_absent']:,}**, zero-volume **{source['target_zero_volume_missing']:,}**, invalid-price **{source['target_invalid_price_missing']:,}**); invalid corporate-action proxy **{source['candidate_rows_by_target_state']['invalid_corporate_action']:,}**.",
        f"- Quantified universe limit: zt_pool has **{overlap['zt_pool_distinct_tickers']:,}** distinct names; only **{overlap['raw_overlap']:,}** overlap nominal OHLCV (**{overlap['overlap_pct']:.2f}%**); **{overlap['missing_ohlcv']:,}** are missing OHLCV.",
        f"- Source manifest hash: `{source['source_manifest_hash']}`.",
        "",
        "## Board / era base ladder",
        "",
        "| Board era | Block | N | Tolerant rate | Strict rate | Missing/halted D |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for era, blocks in receipt["board_era_base_ladder"].items():
        for block, cell in blocks.items():
            lines.append(
                f"| {era} | {block} | {cell['n']:,} | {_pct(cell['tolerant_rate'])} | "
                f"{_pct(cell['strict_rate'])} | {_pct(cell['missing_halted_rate'])} |"
            )

    lines.extend(["", "## Main-board probability results", "",
                  "The replay block is explicitly `historical_replay_after_common_prior`, never an unseen test.", "",
                  "| Block | Comparator | N | Brier Δ vs base | Log-loss Δ vs base | ECE | Cal. intercept | Cal. slope |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"])
    comparator_labels = {
        "fixed_equal_rank_blend": "O1 fixed equal-rank blend",
        "O1": "O1 fixed-L2 logistic",
        "O3": "O3 fixed-L2 washout challenger",
    }
    for label, block in (("Locked replay", main_replay), ("Vendor audit", main_audit)):
        for model_name in ("fixed_equal_rank_blend", "O1", "O3"):
            metric = block.get("tolerant_primary", {}).get(model_name, {})
            if not metric:
                continue
            lines.append(
                f"| {label} | {comparator_labels[model_name]} | {metric['n']:,} | {_num(metric['brier_improvement'], 6)} | "
                f"{_num(metric['log_loss_improvement'], 6)} | {_num(metric['calibration']['ece_10'], 6)} | "
                f"{_num(metric['calibration']['intercept'], 4)} | {_num(metric['calibration']['slope'], 4)} |"
            )

    lines.extend(["", "Calibration slope/intercept uses damped Newton with a logaddexp objective and backtracking line search; degenerate outcomes are labelled instead of reported as a trusted zero slope."])

    lines.extend(["", "## Date-block probability uncertainty", "",
                  "Ten-session common-date blocks are resampled with replacement; intervals are day-weighted, never name-row IID.", "",
                  "| Block | Model | Brier Δ point | Bootstrap 2.5% | Bootstrap 97.5% |",
                  "|---|---|---:|---:|---:|"])
    for block_key, block_label in (("main_locked_replay", "Locked replay"),
                                    ("main_vendor_audit", "Vendor audit")):
        boot = receipt["date_block_bootstrap"][block_key]
        for model_name in ("fixed_equal_rank_blend", "O1", "O3"):
            cell = boot["models"][model_name]["brier_improvement"]
            lines.append(
                f"| {block_label} | {comparator_labels[model_name]} | "
                f"{_num(cell['day_weighted_point'], 6)} | {_num(cell['bootstrap_p2_5'], 6)} | "
                f"{_num(cell['bootstrap_p97_5'], 6)} |"
            )

    o1_model = receipt["models"]["O1_five_axis"]
    o3_model = receipt["models"]["O3_washout_transition"]
    lines.extend(["", "## Frozen fixed-L2 coefficients", "",
                  f"Both fits use L2={o1_model['l2']}; the O1 probability map is calibrated only on 2020–23 main-board rows.", "",
                  "| Term | O1 fixed-L2 beta | O3 fixed-L2 beta |",
                  "|---|---:|---:|"])
    o1_beta = dict(zip(["intercept", *o1_model["columns"]], o1_model["beta"]))
    o3_beta = dict(zip(["intercept", *o3_model["columns"]], o3_model["beta"]))
    for term in ["intercept", *o3_model["columns"]]:
        lines.append(
            f"| {term} | {_num(o1_beta.get(term), 6)} | {_num(o3_beta.get(term), 6)} |"
        )

    lines.extend(["", "## Five-axis univariate ore", "",
                  "All ten train-frozen bins are printed below so a multivariate headline cannot hide a reversal-shaped seam.", "",
                  "| Feature | Locked-replay bin lifts 0→9 | Bin counts 0→9 |",
                  "|---|---|---|"])
    univariate = receipt["univariate_frozen_deciles"]
    replay_key = "historical_replay_after_common_prior:main_10"
    for feature in [FEATURE_NAMES[i] for i in O1_COLS]:
        cell = univariate[feature]["groups"].get(replay_key)
        if not cell:
            continue
        lifts = ", ".join(
            f"{bucket['bin']}:{_num(bucket['lift_vs_group_base'], 3)}×" for bucket in cell["bins"]
        )
        counts = ", ".join(f"{bucket['bin']}:{bucket['n']:,}" for bucket in cell["bins"])
        lines.append(f"| {feature} | {lifts} | {counts} |")

    lines.extend(["", "## H1 sequential fixed-sleeve book ruler", "",
                  "The H1 book uses K fixed capital sleeves, exits before optional same-open re-entry, forbids duplicate held tickers, and keeps unavailable, queue, no-fill, missing, and unresolved sleeves as cash=0. Filled-only means are diagnostics, not the expectancy headline.", "",
                  "This ruler forces K names on every eligible date. Probability/expected-edge thresholds with cash/no-trade days and point-in-time regime-conditioned exposure remain untested constructions.", "",
                  "| Model | Block | Sleeves | Orders | Order fill rate | H1 gross fixed-sleeve | H1 net 60bp fixed-sleeve | Month-block 95% CI | H1 max DD @60bp | Held-duplicate rows skipped | Unavailable sleeve-days |",
                  "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for model_key, model_label in (
        ("topk_fixed_equal_rank_tolerant", "O1 fixed equal-rank"),
        ("topk_O1_tolerant", "O1 fixed-L2"),
        ("topk_O3_tolerant", "O3 fixed-L2"),
    ):
        for label, block in (("Locked replay", main_replay), ("Vendor audit", main_audit)):
            top = block.get(model_key, {}).get("top_20", {})
            if not top:
                continue
            h1 = top["sequential_H1_fixed_K_sleeve_book"]
            net60 = h1["cost_grid"]["60"]
            interval = net60["calendar_month_block_bootstrap"]
            lines.append(
                f"| {model_label} | {label} | 20 | {h1['selected_order_rows']:,} | "
                f"{_pct(h1['fill_funnel']['fill_rate_of_orders'])} | "
                f"{_pct(h1['cost_grid']['0']['day_weighted_fixed_sleeve_mean'])} | "
                f"{_pct(net60['day_weighted_fixed_sleeve_mean'])} | "
                f"[{_pct(interval['p2_5'])}, {_pct(interval['p97_5'])}] | "
                f"{_pct(net60['max_drawdown'])} | "
                f"{h1['duplicate_rows_skipped']:,} | {h1['unavailable_sleeve_days']:,} |"
            )

    lines.extend([
        "", "## Event-cohort overlap diagnostics", "",
        "H1/H3/H5 rows below are event cohorts. H3/H5 overlap capital and can reselect an already-held ticker, so they are not portfolio returns and never drive a strategy verdict.", "",
        "| Model | Block | Horizon | Event rows | Overlapping reselections | Overlap rate | Dates with overlap | Max concurrent same-name lots |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ])
    for model_key, model_label in (
        ("topk_fixed_equal_rank_tolerant", "O1 fixed equal-rank"),
        ("topk_O1_tolerant", "O1 fixed-L2"),
        ("topk_O3_tolerant", "O3 fixed-L2"),
    ):
        for label, block in (("Locked replay", main_replay), ("Vendor audit", main_audit)):
            top = block.get(model_key, {}).get("top_20", {})
            for horizon in HORIZONS:
                overlap_cell = top.get("event_level_overlap_diagnostics", {}).get(
                    f"H{horizon}_next_open", {}
                )
                if not overlap_cell:
                    continue
                lines.append(
                    f"| {model_label} | {label} | H{horizon} | "
                    f"{overlap_cell['selected_event_rows']:,} | "
                    f"{overlap_cell['overlapping_reselection_rows']:,} | "
                    f"{_pct(overlap_cell['overlap_rate'])} | "
                    f"{overlap_cell['dates_with_overlap']:,} | "
                    f"{overlap_cell['max_concurrent_lots_same_ticker']:,} |"
                )

    rank_ore = receipt["ore_ledger"]["O1_fixed_equal_rank_blend"]["evidence"]
    lines.extend([
        "",
        "The fixed equal-rank top-20 H5/30bp **event-cohort diagnostic** has a replay-only seam "
        f"({_pct(rank_ore['main_replay_EVENT_COHORT_top20_H5_30bp_mean'])}) that reverses sharply "
        f"in the vendor audit ({_pct(rank_ore['main_vendor_EVENT_COHORT_top20_H5_30bp_mean'])}). "
        "Because cohorts overlap capital, this is not portfolio evidence; the cross-tail reversal also rejects promotion from the diagnostic seam.",
    ])

    lines.extend(["", "## ChiNext and STAR honesty labels", ""])
    for key, block in groups.items():
        if key.endswith(("chinext_10", "chinext_20", "star_20")) and ("historical_replay" in key or "vendor_audit" in key):
            metric = block["tolerant_primary"]["O1"]
            lines.append(
                f"- `{key}` — **{block['transport_status']}**; N={metric['n']:,}, event rate={_pct(metric['event_rate'])}, "
                f"O1 Brier Δ={_num(metric['brier_improvement'], 6)}."
            )

    ledger = receipt["forward_ledger_contract"]
    lines.extend([
        "", "## Forward ledger seed and contract", "",
        f"- Honest prospective seed: **{ledger['prospective_seed_rows']:,}** full-pop model/name rows from signal date **{ledger['prospective_seed_signal_date']}** for entry session **{ledger['prospective_seed_entry_session']}**.",
        "- Every eligible name is emitted, including unselected/no-fire rows. Fillability is `unknown_pending` until the D auction.",
        "- Terminal fillability is exactly three-way: `fillable_daily_proxy`, `queue_required_no_fill`, or `missing_halted_no_fill`.",
        "- Probability identity is stable across calendar corrections: `signal_date+ticker+model_version+limit_definition+entry_rule`; `entry_session` is immutable payload. A corrected entry date therefore raises a keep-first mutation instead of appending a duplicate.",
        "- Probability and grade helpers are separate and reject non-nightly caller labels, non-context authority, non-finite/boundary probabilities, an unexpected model family, malformed existing stores, or a non-recomputable universe ID.",
        "- Event grades are full-population (`EVENT_D`, one per probability). Execution/return grades are separate per H1/H3/H5 and permitted only for selected orders; an unfilled order has `gross_return=null`, null conditional net returns, an explicit terminal no-fill state, and `book_contribution_return=0`—never a fabricated flat trade.",
        "- The one Aug-10 entry session is frozen by the construction map. Recurring advancement fails closed until an authoritative annual SSE/SZSE calendar is wired; grading requires the exact observed market-session index.",
        f"- JSONL is a capped **{ledger['jsonl_max_snapshot_sessions']}-session bridge**: this seed is **{ledger['seed_jsonl_bytes'] / 1024 / 1024:.2f} MiB**, implying about **{ledger['estimated_ten_session_jsonl_bytes'] / 1024 / 1024:.2f} MiB** at the cap. Normalized monthly Parquet probability/grade partitions remain unbuilt.",
        "- **No recurring nightly advancer or grader is wired in this packet.** This is a contract plus one honest seed only; there are no fabricated grades and no claim of recurring advancement.",
        "- A future production runner must load these frozen fitted parameters, discover a dynamic latest-complete observed session, and fail closed on future-calendar ambiguity. It must not import the analysis-end-pinned research builders or refit nightly.",
        "- Retrospective rows seeded as prospective history: **0**.",
        "", "## Limitations", "",
    ])
    lines.extend([f"- {item}" for item in receipt["limitations"]])
    lines.extend(["", "## UNTESTED VARIANTS", ""])
    lines.extend([f"- {item}" for item in receipt["untested_variants"]])
    lines.append("")
    return "\n".join(lines)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def run(out_json: Path = OUT_JSON, out_md: Path = OUT_MD, out_seed: Path = OUT_SEED) -> dict:
    started = time.monotonic()
    calendar = load_calendar()
    panel, latest, source = build_panel()
    overlap = source["zt_pool_universe_limit"]
    overlap["task_pinned_expected"] = {"zt_pool_distinct_tickers": 1770, "raw_overlap": 514,
                                       "missing_ohlcv": 1256, "overlap_pct": 29.04}
    overlap["matches_task_pin"] = all(overlap.get(k) == v for k, v in overlap["task_pinned_expected"].items())
    receipt, seed = build_receipt(panel, latest, source, calendar)
    atomic_write_text(out_json, json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2,
                                           allow_nan=False) + "\n")
    atomic_write_text(out_md, render_markdown(receipt))
    atomic_write_jsonl(out_seed, seed)
    print(
        f"ONSET complete: rows={len(panel):,} seed={len(seed):,} "
        f"json={out_json} md={out_md} elapsed={time.monotonic() - started:.1f}s",
        flush=True,
    )
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, default=OUT_JSON)
    parser.add_argument("--markdown", type=Path, default=OUT_MD)
    parser.add_argument("--seed", type=Path, default=OUT_SEED)
    args = parser.parse_args(argv)
    run(args.json, args.markdown, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
