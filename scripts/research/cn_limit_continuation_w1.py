"""Deterministic CN limit-up continuation research packet (SOL Wave 1).

This is an offline, display-only measurement runner over nominal daily OHLCV.  It
keeps three clocks separate:

* C0: a true-next-CN-market-session continuation ladder;
* C-AUCTION: a T-close decision submitted for the next official open, with an
  open-at-upper-limit queue treated as *no fill*; and
* C-POSTGAP: a realised-auction-gap probability table only.  Daily OHLCV cannot
  supply a fill-honest 09:30/first-five-minute execution price, so this packet
  never reports a C-POSTGAP strategy return.

The runner streams one ticker at a time and retains only event rows plus daily
aggregates.  It does not write a forward ledger or affect production authority.

Run from the repository root::

    python scripts/research/cn_limit_continuation_w1.py

Outputs are deterministic JSON and Markdown receipts under
``research/cn_limit_alpha_sol/``.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import gc
import hashlib
import json
import logging
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

log = logging.getLogger("cn_limit_continuation_w1")

SCHEMA_VERSION = "cn_limit_continuation_w1/v2"
MODEL_VERSION = "sol_w1_daily_tolerant_common_calendar_fixed_strata_2026-08-08"
RECEIPT_DATE = "2026-08-08"
AUTHORITY = "none_research_display_only"

DEFAULT_RAW_DIR = ROOT / "data" / "china_stocks_raw"
DEFAULT_CALENDAR_PATH = ROOT / "data" / "china" / "000001.SS.parquet"
DEFAULT_ST_PATH = ROOT / "data" / "china_st" / "st_snapshot.parquet"
DEFAULT_ZT_PATH = ROOT / "data" / "china_zt_pool" / "pool.parquet"
DEFAULT_JSON = ROOT / "research" / "cn_limit_alpha_sol" / "W1_CONTINUATION_MEASUREMENT_2026-08-08.json"
DEFAULT_MARKDOWN = ROOT / "research" / "cn_limit_alpha_sol" / "W1_CONTINUATION_MEASUREMENT_2026-08-08.md"

START_DATE = pd.Timestamp("2011-01-01")
END_DATE = pd.Timestamp("2026-08-07")
CHINEXT_WIDE_DATE = pd.Timestamp("2020-08-24")
ST_RULE_CHANGE_DATE = pd.Timestamp("2026-07-06")
MIN_PRIOR_SESSIONS = 60
LIMIT_TOLERANCE = 0.002
BOUNDARY_PURGE_SESSIONS = 10
COST_GRID_BPS = (0, 30, 60, 100)
EXIT_IDS = (
    "tplus1_legal_open",
    "tplus1_legal_close",
    "tplus2_close",
    "tplus4_close",
    "seal_state_next_open",
)

SPLITS: tuple[tuple[str, pd.Timestamp, pd.Timestamp], ...] = (
    ("train_2011_2019", pd.Timestamp("2011-01-01"), pd.Timestamp("2019-12-31")),
    ("calibration_2020_2023", pd.Timestamp("2020-01-01"), pd.Timestamp("2023-12-31")),
    (
        "historical_replay_after_common_prior",
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2026-06-12"),
    ),
    ("vendor_tail_audit", pd.Timestamp("2026-06-15"), pd.Timestamp("2026-08-07")),
)

C_AUCTION_SELECTION_FIELDS = (
    "board_count",
    "one_price_board",
    "board_day_gap_norm",
    "intraday_range_norm",
    "close_location",
    "volume_z20",
    "ecology_state",
    "ecology_soft_score",
    "weekday",
    "calendar_gap_days",
)

UNTESTED_VARIANTS: tuple[str, ...] = (
    "full-market small-cap universe: zt_pool names without local nominal OHLCV are outside this curated slice",
    "historically correct ST and risk-warning membership; all current-snapshot ST intersections are excluded",
    "BSE listings and their 30 percent band",
    "first 60 listed sessions, including registration-era no-limit IPO sessions",
    "pre-close and same-day near-limit executable entries",
    "C-POSTGAP returns using a real 09:30 trade or first-five-minute VWAP",
    "opening-auction matched volume, unmatched imbalance, queue depth, order priority, and partial fills",
    "first-touch time, cumulative sealed minutes, final seal time, and seal-break or reseal entries",
    "PIT THS concept membership, sector concentration, and theme leader-follower topology",
    "PIT seal-wall and LHB participant fields outside their short and currently unreliable vendor windows",
    "free-float shares, capacity, commissions, stamp duty, and slippage outside the stated cost grid",
    "delisted-name-complete history and survivorship-free down-limit release reversals",
    "cross-name portfolio dependence, theme caps, and crowded-factor drawdown",
    "tree, boosting, hazard, and nested-validation models",
    "corporate-action truth beyond the inherited nominal-price open-gap suppression heuristic",
)


def board_from_ticker(ticker: str) -> str:
    """Return the exchange board from the repo's ticker convention."""
    code = str(ticker).upper().split(".")[0]
    if code.startswith(("688", "689")):
        return "star"
    if code.startswith(("300", "301", "302")):
        return "chinext"
    if code.startswith(("8", "4", "92")):
        return "bse"
    return "main"


def limit_width(board: str, trade_date: pd.Timestamp) -> float:
    """Non-ST board width for one date.

    ST is intentionally unsupported by this runner.  The caller removes the
    current ST-snapshot intersection, and the receipt labels unknown historical
    membership as an open data gap.
    """
    if board == "star":
        return 0.20
    if board == "chinext":
        return 0.20 if pd.Timestamp(trade_date) >= CHINEXT_WIDE_DATE else 0.10
    if board == "bse":
        return 0.30
    return 0.10


def board_era(board: str, trade_date: pd.Timestamp) -> str:
    if board == "main":
        return "main_10pct_nonst"
    if board == "chinext":
        return (
            "chinext_20pct_post_2020_08_24"
            if pd.Timestamp(trade_date) >= CHINEXT_WIDE_DATE
            else "chinext_10pct_pre_2020_08_24"
        )
    if board == "star":
        return "star_20pct_descriptive"
    return "bse_30pct_untested"


def market_scope(board: str, trade_date: pd.Timestamp) -> str:
    era = board_era(board, trade_date)
    if board == "main":
        return "main_primary"
    if board == "chinext":
        return "chinext_20_secondary" if "20pct" in era else "chinext_10_secondary_separate_era"
    if board == "star":
        return "star_descriptive"
    return "bse_untested"


def _is_finite_positive(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)) and float(value) > 0)
    except (TypeError, ValueError):
        return False


def tolerant_at_upper(value: float, upper: float) -> bool:
    return _is_finite_positive(value) and _is_finite_positive(upper) and value >= upper * (1 - LIMIT_TOLERANCE)


def tolerant_at_lower(value: float, lower: float) -> bool:
    return _is_finite_positive(value) and _is_finite_positive(lower) and value <= lower * (1 + LIMIT_TOLERANCE)


def assign_split(trade_date: pd.Timestamp) -> str | None:
    d = pd.Timestamp(trade_date).normalize()
    for name, start, end in SPLITS:
        if start <= d <= end:
            return name
    return None


def board_count_bucket(value: Any) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "unknown"
    return str(n) if n <= 4 else "5_plus"


def gap_bucket(value: Any, queue_blocked: bool = False) -> str:
    """Fixed, band-normalised C-POSTGAP buckets; no fitted cut points."""
    if queue_blocked:
        return "upper_limit_queue"
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "missing"
    if not np.isfinite(x):
        return "missing"
    if x <= -0.25:
        return "le_neg_0_25_band"
    if x <= 0:
        return "neg_0_25_to_zero"
    if x <= 0.25:
        return "zero_to_0_25_band"
    if x <= 0.50:
        return "0_25_to_0_50_band"
    if x <= 0.80:
        return "0_50_to_0_80_band"
    return "gt_0_80_band_below_queue"


def geometry_buckets(row: Mapping[str, Any]) -> dict[str, str]:
    def bucket(value: Any, cuts: Sequence[float], labels: Sequence[str]) -> str:
        try:
            x = float(value)
        except (TypeError, ValueError):
            return "missing"
        if not np.isfinite(x):
            return "missing"
        for cut, label in zip(cuts, labels):
            if x <= cut:
                return label
        return labels[-1]

    return {
        "one_price_board": "yes" if bool(row.get("one_price_board")) else "no",
        "board_day_gap_norm": bucket(
            row.get("board_day_gap_norm"),
            (0.0, 0.25, 0.50, math.inf),
            ("nonpositive", "zero_to_0_25", "0_25_to_0_50", "gt_0_50"),
        ),
        "intraday_range_norm": bucket(
            row.get("intraday_range_norm"),
            (0.10, 0.35, 0.70, math.inf),
            ("le_0_10", "0_10_to_0_35", "0_35_to_0_70", "gt_0_70"),
        ),
        "close_location": bucket(
            row.get("close_location"),
            (0.50, 0.80, 0.95, math.inf),
            ("le_0_50", "0_50_to_0_80", "0_80_to_0_95", "gt_0_95"),
        ),
        "volume_z20": bucket(
            row.get("volume_z20"),
            (0.0, 1.0, 2.0, math.inf),
            ("le_zero", "zero_to_one", "one_to_two", "gt_two"),
        ),
    }


@dataclass(frozen=True)
class ExitObservation:
    price: float | None
    date: str | None
    index: int | None
    locked_down_deferrals: int
    reason: str


@dataclass(frozen=True)
class MarketCalendar:
    """Observed common CN session clock and its deterministic adjacency maps."""

    sessions: pd.DatetimeIndex
    successor: Mapping[pd.Timestamp, pd.Timestamp]
    position: Mapping[pd.Timestamp, int]

    @classmethod
    def from_dates(cls, values: Iterable[Any]) -> "MarketCalendar":
        sessions = pd.DatetimeIndex(pd.to_datetime(list(values), errors="coerce")).normalize()
        sessions = sessions[~sessions.isna()].drop_duplicates().sort_values()
        successor = {sessions[i]: sessions[i + 1] for i in range(len(sessions) - 1)}
        position = {date: i for i, date in enumerate(sessions)}
        return cls(sessions=sessions, successor=successor, position=position)


def load_market_calendar(path: Path) -> MarketCalendar:
    """Load the repo-canonical Shanghai Composite observed-session calendar."""
    if not path.exists():
        raise FileNotFoundError(f"CN market-session anchor missing: {path}")
    frame = pd.read_parquet(path)
    calendar = MarketCalendar.from_dates(frame.index)
    if not len(calendar.sessions):
        raise ValueError(f"CN market-session anchor is empty: {path}")
    return calendar


def _sellable_open(
    opens: np.ndarray,
    lowers: np.ndarray,
    dates: pd.DatetimeIndex,
    start_date: pd.Timestamp | None,
    market_calendar: MarketCalendar,
    date_to_index: Mapping[pd.Timestamp, int],
) -> ExitObservation:
    """First exact-market-session open not queued at lower limit.

    A missing ticker bar is an unresolved halt/data state.  It is never skipped
    in favour of the next later ticker observation.
    """
    deferrals = 0
    current = start_date
    while current is not None:
        j = date_to_index.get(current)
        if j is None:
            return ExitObservation(
                None,
                str(current.date()),
                None,
                deferrals,
                "missing_bar_halt_or_data_missing",
            )
        if not _is_finite_positive(opens[j]) or not _is_finite_positive(lowers[j]):
            return ExitObservation(
                None, str(current.date()), j, deferrals, "target_price_missing"
            )
        if tolerant_at_lower(float(opens[j]), float(lowers[j])):
            deferrals += 1
            current = market_calendar.successor.get(current)
            continue
        return ExitObservation(float(opens[j]), str(dates[j].date()), j, deferrals, "official_open")
    return ExitObservation(None, None, None, deferrals, "calendar_right_censored")


def _fixed_exit(
    *,
    opens: np.ndarray,
    closes: np.ndarray,
    lowers: np.ndarray,
    dates: pd.DatetimeIndex,
    target_date: pd.Timestamp | None,
    price_field: str,
    market_calendar: MarketCalendar,
    date_to_index: Mapping[pd.Timestamp, int],
) -> ExitObservation:
    if target_date is None:
        return ExitObservation(None, None, None, 0, "calendar_right_censored")
    target_index = date_to_index.get(target_date)
    if target_index is None:
        return ExitObservation(
            None,
            str(target_date.date()),
            None,
            0,
            "missing_bar_halt_or_data_missing",
        )
    if price_field == "open":
        return _sellable_open(
            opens, lowers, dates, target_date, market_calendar, date_to_index
        )
    if not _is_finite_positive(closes[target_index]) or not _is_finite_positive(lowers[target_index]):
        return ExitObservation(None, None, None, 0, "target_price_missing")
    if tolerant_at_lower(float(closes[target_index]), float(lowers[target_index])):
        carried = _sellable_open(
            opens,
            lowers,
            dates,
            market_calendar.successor.get(target_date),
            market_calendar,
            date_to_index,
        )
        return ExitObservation(
            carried.price,
            carried.date,
            carried.index,
            carried.locked_down_deferrals + 1,
            "close_lower_limit_carry_to_open" if carried.price is not None else carried.reason,
        )
    return ExitObservation(
        float(closes[target_index]),
        str(dates[target_index].date()),
        target_index,
        0,
        "official_close",
    )


def _seal_state_exit(
    *,
    opens: np.ndarray,
    lowers: np.ndarray,
    sealed_up: np.ndarray,
    dates: pd.DatetimeIndex,
    entry_date: pd.Timestamp,
    market_calendar: MarketCalendar,
    date_to_index: Mapping[pd.Timestamp, int],
) -> tuple[ExitObservation, int]:
    """Hold through exact-session sealed closes; exit exact next sellable open."""
    sealed_holds = 0
    current: pd.Timestamp | None = entry_date
    while current is not None:
        j = date_to_index.get(current)
        if j is None:
            return (
                ExitObservation(
                    None,
                    str(current.date()),
                    None,
                    0,
                    "missing_bar_halt_or_data_missing",
                ),
                sealed_holds,
            )
        if bool(sealed_up[j]):
            sealed_holds += 1
            current = market_calendar.successor.get(current)
            continue
        exit_date = market_calendar.successor.get(current)
        if exit_date is None:
            return ExitObservation(None, None, None, 0, "calendar_right_censored"), sealed_holds
        return (
            _sellable_open(
                opens, lowers, dates, exit_date, market_calendar, date_to_index
            ),
            sealed_holds,
        )
    return ExitObservation(None, None, None, 0, "calendar_right_censored"), sealed_holds


def _advance_market_session(
    market_calendar: MarketCalendar,
    start_date: pd.Timestamp,
    steps: int,
) -> pd.Timestamp | None:
    current: pd.Timestamp | None = start_date
    for _ in range(steps):
        if current is None:
            break
        current = market_calendar.successor.get(current)
    return current


def _return_payload(
    entry_price: float,
    exit_obs: ExitObservation,
    highs: np.ndarray,
    lows: np.ndarray,
    entry_index: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "exit_date": exit_obs.date,
        "exit_price": exit_obs.price,
        "exit_reason": exit_obs.reason,
        "locked_down_deferrals": exit_obs.locked_down_deferrals,
        "gross_return": None,
        "mfe": None,
        "mae": None,
    }
    if exit_obs.price is None or exit_obs.index is None or not _is_finite_positive(entry_price):
        return payload
    payload["gross_return"] = float(exit_obs.price / entry_price - 1.0)
    window_hi = highs[entry_index : exit_obs.index + 1]
    window_lo = lows[entry_index : exit_obs.index + 1]
    finite_hi = window_hi[np.isfinite(window_hi)]
    finite_lo = window_lo[np.isfinite(window_lo)]
    if len(finite_hi):
        payload["mfe"] = float(finite_hi.max() / entry_price - 1.0)
    if len(finite_lo):
        payload["mae"] = float(finite_lo.min() / entry_price - 1.0)
    return payload


def _volume_z20(volume: pd.Series) -> pd.Series:
    mean = volume.rolling(20, min_periods=20).mean()
    std = volume.rolling(20, min_periods=20).std(ddof=0).replace(0, np.nan)
    return (volume - mean) / std


def extract_ticker_events(
    ticker: str,
    frame: pd.DataFrame,
    *,
    start_date: pd.Timestamp = START_DATE,
    end_date: pd.Timestamp = END_DATE,
    min_prior_sessions: int = MIN_PRIOR_SESSIONS,
    market_calendar: MarketCalendar | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Counter], dict[str, Any]]:
    """Return event rows, daily counters, and diagnostics for one nominal OHLCV frame."""
    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{ticker}: missing OHLCV columns {missing}")

    board = board_from_ticker(ticker)
    if board == "bse":
        return [], {}, {"status": "excluded_bse", "rows": len(frame)}

    df = frame.loc[:, ["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index, errors="coerce")).normalize()
    df = df[~df.index.isna()].sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if df.empty:
        return [], {}, {"status": "empty", "rows": 0}

    dates = pd.DatetimeIndex(df.index)
    # Unit callers may omit a calendar, but the production research run always
    # injects the repo-canonical Shanghai Composite clock.  Never use a later
    # ticker row as a substitute for a missing true-next market session.
    clock = market_calendar or MarketCalendar.from_dates(dates)
    calendar_positions = np.array([clock.position.get(d, -1) for d in dates], dtype=int)
    opens = pd.to_numeric(df["open"], errors="coerce").to_numpy(dtype=float)
    highs = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    lows = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    closes = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    volumes = pd.to_numeric(df["volume"], errors="coerce")
    widths = np.array([limit_width(board, d) for d in dates], dtype=float)
    prev_close = np.roll(closes, 1)
    prev_close[0] = np.nan
    uppers = np.round(prev_close * (1.0 + widths), 2)
    lowers = np.round(prev_close * (1.0 - widths), 2)

    finite = (
        np.isfinite(opens)
        & np.isfinite(highs)
        & np.isfinite(lows)
        & np.isfinite(closes)
        & np.isfinite(prev_close)
        & (prev_close > 0)
    )
    age_ok = np.arange(len(df)) >= int(min_prior_sessions)
    in_window = (dates >= start_date) & (dates <= end_date)
    era_ok = np.ones(len(df), dtype=bool)
    # ChiNext's two geometries remain separate; both may be measured, never pooled.
    exdiv_suspect = finite & (np.abs(opens - prev_close) / prev_close > widths * 1.5)
    calendar_ok = calendar_positions >= 0
    eligible = finite & age_ok & in_window & era_ok & ~exdiv_suspect & calendar_ok

    tolerant_sealed_up = eligible & (closes >= uppers * (1.0 - LIMIT_TOLERANCE))
    strict_sealed_up = eligible & (closes >= uppers)
    tolerant_touched_up = eligible & (highs >= uppers * (1.0 - LIMIT_TOLERANCE))
    tolerant_failed_up = tolerant_touched_up & ~tolerant_sealed_up
    tolerant_sealed_down = eligible & (closes <= lowers * (1.0 + LIMIT_TOLERANCE))

    streak = np.zeros(len(df), dtype=int)
    ticker_session_streak = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        if tolerant_sealed_up[i]:
            adjacent_market_session = (
                i > 0
                and calendar_positions[i] >= 0
                and calendar_positions[i - 1] == calendar_positions[i] - 1
            )
            streak[i] = (streak[i - 1] if adjacent_market_session else 0) + 1
            ticker_session_streak[i] = (ticker_session_streak[i - 1] if i else 0) + 1

    volume_z20 = _volume_z20(volumes).to_numpy(dtype=float)
    runup_5 = pd.Series(closes, index=dates).pct_change(5, fill_method=None).to_numpy(dtype=float)
    board_gap_norm = (opens / prev_close - 1.0) / widths
    intraday_range_norm = ((highs - lows) / prev_close) / widths
    ranges = highs - lows
    close_location = np.divide(
        closes - lows,
        ranges,
        out=np.ones_like(closes, dtype=float),
        where=np.isfinite(ranges) & (ranges > 0),
    )
    one_price = (
        np.nanmax(np.column_stack([opens, highs, lows, closes]), axis=1)
        - np.nanmin(np.column_stack([opens, highs, lows, closes]), axis=1)
        <= 0.011
    )

    counters: dict[str, Counter] = {
        "universe_n": Counter(dates[in_window]),
        "sealed_up": Counter(dates[tolerant_sealed_up]),
        "first_board": Counter(dates[tolerant_sealed_up & (streak == 1)]),
        "failed_up": Counter(dates[tolerant_failed_up]),
        "sealed_down": Counter(dates[tolerant_sealed_down]),
    }

    rows: list[dict[str, Any]] = []
    ticker_date_to_i = {date: j for j, date in enumerate(dates)}
    for i in np.flatnonzero(tolerant_sealed_up):
        split = assign_split(dates[i])
        if split is None:
            continue
        expected_next_date = clock.successor.get(dates[i])
        expected_next2_date = clock.successor.get(expected_next_date) if expected_next_date is not None else None
        next_i = ticker_date_to_i.get(expected_next_date) if expected_next_date is not None else None
        next2_i = ticker_date_to_i.get(expected_next2_date) if expected_next2_date is not None else None
        next_available = next_i is not None
        if expected_next_date is None:
            next_session_state = "right_censored_calendar_end"
            next_board = None
            next_board_observed = None
        elif next_available:
            next_session_state = "observed"
            next_board = bool(tolerant_sealed_up[next_i])
            next_board_observed = next_board
        else:
            next_session_state = "no_bar_halt_or_data_missing"
            next_board = False
            next_board_observed = None
        any_board_2 = (
            bool(
                (next_i is not None and tolerant_sealed_up[next_i])
                or (next2_i is not None and tolerant_sealed_up[next2_i])
            )
            if expected_next2_date is not None
            else None
        )
        run_start_i = i - int(streak[i]) + 1
        record: dict[str, Any] = {
            "ticker": ticker,
            "signal_date": str(dates[i].date()),
            "split": split,
            "board": board,
            "board_era": board_era(board, dates[i]),
            "market_scope": market_scope(board, dates[i]),
            "board_count": int(streak[i]),
            "board_count_bucket": board_count_bucket(streak[i]),
            "ticker_session_board_count_sensitivity": int(ticker_session_streak[i]),
            "run_cluster": f"{ticker}:{dates[run_start_i].date()}",
            "date_cluster": str(dates[i].date()),
            "tolerant_sealed_up": True,
            "strict_sealed_up": bool(strict_sealed_up[i]),
            "next_session_available": bool(next_available),
            "next_session_state": next_session_state,
            "next_session_date": str(expected_next_date.date()) if expected_next_date is not None else None,
            "next_observed_ticker_date_sensitivity": (
                str(dates[i + 1].date()) if i + 1 < len(dates) else None
            ),
            "next_board": next_board,
            "next_board_observed_bar_sensitivity": next_board_observed,
            "any_board_within_2_sessions": any_board_2,
            "one_price_board": bool(one_price[i]),
            "board_day_gap_norm": float(board_gap_norm[i]),
            "intraday_range_norm": float(intraday_range_norm[i]),
            "close_location": float(close_location[i]),
            "volume_z20": float(volume_z20[i]) if np.isfinite(volume_z20[i]) else None,
            "runup_5": float(runup_5[i]) if np.isfinite(runup_5[i]) else None,
            "weekday": dates[i].day_name(),
            "calendar_gap_days": (
                int((expected_next_date - dates[i]).days) if expected_next_date is not None else None
            ),
            "entry_gap_norm": None,
            "entry_fill_state": (
                "no_bar_halt_or_data_missing_no_fill"
                if expected_next_date is not None and not next_available
                else (
                    "next_open_price_or_limit_missing_no_fill"
                    if next_available
                    else "next_market_session_not_observed"
                )
            ),
            "entry_price": None,
            "exits": {},
        }
        record.update({f"geometry_{k}": v for k, v in geometry_buckets(record).items()})

        if next_i is not None and _is_finite_positive(opens[next_i]) and _is_finite_positive(uppers[next_i]):
            record["entry_gap_norm"] = float((opens[next_i] / closes[i] - 1.0) / widths[next_i])
            if tolerant_at_upper(float(opens[next_i]), float(uppers[next_i])):
                record["entry_fill_state"] = "open_at_upper_limit_queue_no_fill"
            else:
                record["entry_fill_state"] = "official_open_candidate_fill"
                entry_price = float(opens[next_i])
                record["entry_price"] = entry_price
                exit_specs = {
                    "tplus1_legal_open": (
                        _advance_market_session(clock, expected_next_date, 1),
                        "open",
                    ),
                    "tplus1_legal_close": (
                        _advance_market_session(clock, expected_next_date, 1),
                        "close",
                    ),
                    "tplus2_close": (
                        _advance_market_session(clock, expected_next_date, 2),
                        "close",
                    ),
                    "tplus4_close": (
                        _advance_market_session(clock, expected_next_date, 4),
                        "close",
                    ),
                }
                for exit_id, (target_date, field) in exit_specs.items():
                    obs = _fixed_exit(
                        opens=opens,
                        closes=closes,
                        lowers=lowers,
                        dates=dates,
                        target_date=target_date,
                        price_field=field,
                        market_calendar=clock,
                        date_to_index=ticker_date_to_i,
                    )
                    record["exits"][exit_id] = _return_payload(
                        entry_price, obs, highs, lows, next_i
                    )
                state_obs, sealed_holds = _seal_state_exit(
                    opens=opens,
                    lowers=lowers,
                    sealed_up=tolerant_sealed_up,
                    dates=dates,
                    entry_date=expected_next_date,
                    market_calendar=clock,
                    date_to_index=ticker_date_to_i,
                )
                state_payload = _return_payload(entry_price, state_obs, highs, lows, next_i)
                state_payload["sealed_hold_sessions"] = sealed_holds
                record["exits"]["seal_state_next_open"] = state_payload
        record["postgap_bucket"] = gap_bucket(
            record["entry_gap_norm"],
            record["entry_fill_state"] == "open_at_upper_limit_queue_no_fill",
        )
        rows.append(record)

    diagnostics = {
        "status": "ok",
        "rows": int(len(df)),
        "first_session": str(dates.min().date()),
        "last_session": str(dates.max().date()),
        "eligible_rows": int(eligible.sum()),
        "rows_off_common_calendar": int((~calendar_ok).sum()),
        "rows_off_common_calendar_in_measurement_window": int(
            ((~calendar_ok) & in_window).sum()
        ),
        "exdiv_suspect_rows": int(exdiv_suspect.sum()),
        "tolerant_sealed_up_rows": int(tolerant_sealed_up.sum()),
        "strict_sealed_up_rows": int(strict_sealed_up.sum()),
        "marginal_tolerant_rows": int((tolerant_sealed_up & ~strict_sealed_up).sum()),
        "failed_up_rows": int(tolerant_failed_up.sum()),
    }
    return rows, counters, diagnostics


def _merge_counter(target: Counter, source: Counter) -> None:
    for key, value in source.items():
        target[key] += int(value)


def _build_ecology(
    daily_counters: Mapping[str, Counter],
    events: pd.DataFrame,
    market_sessions: pd.DatetimeIndex | None = None,
) -> pd.DataFrame:
    all_dates = (
        list(market_sessions[(market_sessions >= START_DATE) & (market_sessions <= END_DATE)])
        if market_sessions is not None
        else sorted(daily_counters["universe_n"])
    )
    daily = pd.DataFrame(index=pd.DatetimeIndex(all_dates))
    daily.index.name = "date"
    for name in ("universe_n", "sealed_up", "first_board", "failed_up", "sealed_down"):
        daily[name] = [int(daily_counters[name].get(d, 0)) for d in daily.index]

    cont = events.dropna(subset=["next_session_date", "next_board"]).copy()
    if not cont.empty:
        cont["realised_date"] = pd.to_datetime(cont["next_session_date"])
        cont_n = cont.groupby("realised_date").size()
        cont_success = cont.groupby("realised_date")["next_board"].sum()
        daily["continuation_n"] = cont_n.reindex(daily.index, fill_value=0).astype(int)
        daily["continuation_success"] = cont_success.reindex(daily.index, fill_value=0).astype(int)
    else:
        daily["continuation_n"] = 0
        daily["continuation_success"] = 0

    daily["up_breadth"] = daily["sealed_up"] / daily["universe_n"].replace(0, np.nan)
    daily["down_breadth"] = daily["sealed_down"] / daily["universe_n"].replace(0, np.nan)
    event_total = daily["sealed_up"] + daily["failed_up"]
    daily["failed_share"] = daily["failed_up"] / event_total.replace(0, np.nan)

    for window in (20, 60):
        successes = daily["continuation_success"].rolling(window, min_periods=1).sum()
        trials = daily["continuation_n"].rolling(window, min_periods=1).sum()
        # Fixed Beta(1, 1) shrinkage; no future/full-sample prior enters the signal.
        daily[f"continuation_{window}_shrunk"] = (successes + 1.0) / (trials + 2.0)
        daily[f"up_breadth_{window}"] = daily["up_breadth"].rolling(window, min_periods=5).mean()
        daily[f"failed_share_{window}"] = daily["failed_share"].rolling(window, min_periods=5).mean()

    daily["ecology_soft_score"] = (
        daily["continuation_20_shrunk"]
        - daily["continuation_60_shrunk"]
        + (daily["up_breadth_20"] - daily["up_breadth_60"]).fillna(0.0)
        - (daily["failed_share_20"] - daily["failed_share_60"]).fillna(0.0)
    )
    score = daily["ecology_soft_score"]
    daily["ecology_state"] = np.select(
        [score >= 0.03, score <= -0.03],
        ["hot", "cold"],
        default="neutral",
    )
    return daily.reset_index()


def _last_sessions_in_split(calendar: pd.DatetimeIndex, split_name: str, n: int) -> set[str]:
    match = next((x for x in SPLITS if x[0] == split_name), None)
    if match is None:
        return set()
    _, start, end = match
    dates = calendar[(calendar >= start) & (calendar <= end)]
    return {str(x.date()) for x in dates[-n:]}


def apply_boundary_purge(events: pd.DataFrame, calendar: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Purge the final ten signal sessions of each block before a later block."""
    purge_dates: dict[str, set[str]] = {}
    for split_name, _, _ in SPLITS[:-1]:
        purge_dates[split_name] = _last_sessions_in_split(calendar, split_name, BOUNDARY_PURGE_SESSIONS)
    mask = pd.Series(False, index=events.index)
    counts: dict[str, int] = {}
    for split_name, dates in purge_dates.items():
        hit = events["split"].eq(split_name) & events["signal_date"].isin(dates)
        counts[split_name] = int(hit.sum())
        mask |= hit
    return events.loc[~mask].copy(), {
        "sessions_per_boundary": BOUNDARY_PURGE_SESSIONS,
        "rule": "drop final 10 signal sessions of train, calibration, and locked replay blocks",
        "dates": {k: sorted(v) for k, v in purge_dates.items()},
        "event_rows_removed": counts,
    }


def _json_number(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(x):
        return None
    return int(x) if x.is_integer() else float(x)


def _cluster_interval(values: pd.Series, clusters: pd.Series, *, binary: bool) -> dict[str, Any]:
    frame = pd.DataFrame(
        {"value": pd.to_numeric(values, errors="coerce").astype(float), "cluster": clusters}
    )
    frame = frame.dropna(subset=["value", "cluster"])
    n = len(frame)
    g = int(frame["cluster"].nunique())
    if n == 0:
        return {"clusters": 0, "se": None, "ci95": [None, None]}
    mean = float(frame["value"].mean())
    if g < 2:
        return {"clusters": g, "se": None, "ci95": [None, None]}
    residual_sums = (frame["value"] - mean).groupby(frame["cluster"]).sum()
    variance = (g / (g - 1.0)) * float(np.square(residual_sums).sum()) / float(n * n)
    se = math.sqrt(max(variance, 0.0))
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    if binary:
        lo, hi = max(0.0, lo), min(1.0, hi)
    return {"clusters": g, "se": se, "ci95": [lo, hi]}


def metric_summary(frame: pd.DataFrame, value_col: str, *, binary: bool) -> dict[str, Any]:
    values = pd.to_numeric(frame[value_col], errors="coerce").astype(float)
    valid = values.notna()
    work = frame.loc[valid]
    values = values.loc[valid]
    if values.empty:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "date_cluster": {"clusters": 0, "se": None, "ci95": [None, None]},
            "run_cluster": {"clusters": 0, "se": None, "ci95": [None, None]},
        }
    return {
        "n": int(len(values)),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "p10": float(values.quantile(0.10)),
        "p90": float(values.quantile(0.90)),
        "positive_rate": float((values > 0).mean()) if not binary else None,
        "date_cluster": _cluster_interval(values, work["date_cluster"], binary=binary),
        "run_cluster": _cluster_interval(values, work["run_cluster"], binary=binary),
    }


def _group_records(
    frame: pd.DataFrame,
    group_cols: Sequence[str],
    value_col: str,
    *,
    binary: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for keys, group in frame.groupby(list(group_cols), dropna=False, sort=True):
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        record = {col: (None if pd.isna(val) else val) for col, val in zip(group_cols, key_tuple)}
        record["metric"] = metric_summary(group, value_col, binary=binary)
        rows.append(record)
    return rows


def _flatten_exit_returns(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for event in events.to_dict("records"):
        if event.get("entry_fill_state") != "official_open_candidate_fill":
            continue
        for exit_id, payload in (event.get("exits") or {}).items():
            gross = payload.get("gross_return")
            if gross is None:
                continue
            for cost_bps in COST_GRID_BPS:
                rows.append({
                    "ticker": event["ticker"],
                    "signal_date": event["signal_date"],
                    "date_cluster": event["date_cluster"],
                    "run_cluster": event["run_cluster"],
                    "split": event["split"],
                    "market_scope": event["market_scope"],
                    "board_era": event["board_era"],
                    "board_count_bucket": event["board_count_bucket"],
                    "ecology_state": event.get("ecology_state"),
                    "exit_id": exit_id,
                    "cost_bps": int(cost_bps),
                    "gross_return": float(gross),
                    "net_return": float(gross) - cost_bps / 10_000.0,
                    "locked_down_deferrals": int(payload.get("locked_down_deferrals") or 0),
                    "mfe": payload.get("mfe"),
                    "mae": payload.get("mae"),
                })
    return pd.DataFrame(rows)


def _book_summary(group: pd.DataFrame, exit_id: str, cost_bps: int) -> dict[str, Any]:
    """Candidate-book expectancy with every mature signal in the denominator.

    Rejected queues and missing/halted next-session bars hold cash at zero.  A
    filled signal whose exit is not yet observed is right-censored, not silently
    assigned either zero or a future-resumption return.
    """
    filled = group["entry_fill_state"].eq("official_open_candidate_fill")
    right_censored_entry = group["entry_fill_state"].eq("next_market_session_not_observed")
    gross = group["exits"].map(
        lambda exits: (exits or {}).get(exit_id, {}).get("gross_return")
    )
    gross = pd.to_numeric(gross, errors="coerce")
    resolved_fill = filled & gross.notna()
    matured = ~right_censored_entry & (~filled | resolved_fill)
    work = group.loc[matured].copy()
    work["book_return"] = 0.0
    resolved_index = group.index[resolved_fill]
    work.loc[resolved_index, "book_return"] = gross.loc[resolved_index] - cost_bps / 10_000.0
    conditional = work.loc[resolved_index].copy()
    conditional["net_return"] = work.loc[resolved_index, "book_return"]
    metric = metric_summary(work, "book_return", binary=False)
    conditional_metric = metric_summary(conditional, "net_return", binary=False)
    p_fill = float(len(resolved_index) / len(work)) if len(work) else None
    identity = (
        float(p_fill * conditional_metric["mean"])
        if p_fill is not None and conditional_metric.get("mean") is not None
        else None
    )
    positive = int((conditional.get("net_return", pd.Series(dtype=float)) > 0).sum())
    failure = int((conditional.get("net_return", pd.Series(dtype=float)) <= 0).sum())
    nonfill_states = Counter(
        group.loc[~filled & ~right_censored_entry, "entry_fill_state"].astype(str)
    )
    return {
        "candidate_signals": int(len(group)),
        "mature_candidate_signals": int(len(work)),
        "right_censored_filled_signals": int((filled & gross.isna()).sum()),
        "right_censored_entry_signals": int(right_censored_entry.sum()),
        "resolved_fills": int(len(resolved_index)),
        "p_fill_of_mature_book": p_fill,
        "joint_cash_book_metric": metric,
        "filled_conditional_metric": conditional_metric,
        "p_fill_times_conditional_mean": identity,
        "identity_difference": (
            float(metric["mean"] - identity)
            if metric.get("mean") is not None and identity is not None
            else None
        ),
        "arms": {
            "filled_success": positive,
            "filled_failure_or_flat": failure,
            "not_filled_cash_zero": int((~filled & ~right_censored_entry).sum()),
            "right_censored_filled": int((filled & gross.isna()).sum()),
            "right_censored_entry": int(right_censored_entry.sum()),
            "filled_success_rate_of_mature_book": float(positive / len(work)) if len(work) else None,
            "filled_failure_or_flat_rate_of_mature_book": float(failure / len(work)) if len(work) else None,
        },
        "nonfill_state_counts": dict(sorted(nonfill_states.items())),
    }


def _joint_candidate_book_metrics(
    events: pd.DataFrame,
    group_cols: Sequence[str],
    *,
    exit_ids: Sequence[str] = EXIT_IDS,
    costs_bps: Sequence[int] = COST_GRID_BPS,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for keys, group in events.groupby(list(group_cols), dropna=False, sort=True):
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        keys_record = {
            col: (None if pd.isna(value) else value)
            for col, value in zip(group_cols, key_tuple)
        }
        for exit_id in exit_ids:
            for cost_bps in costs_bps:
                rows.append({
                    **keys_record,
                    "exit_id": exit_id,
                    "cost_bps": int(cost_bps),
                    **_book_summary(group, exit_id, int(cost_bps)),
                })
    return rows


def _locked_replay_stratum_verdicts(
    records: Sequence[Mapping[str, Any]],
    stratum_field: str,
) -> list[dict[str, Any]]:
    """Predeclared cell verdicts; no selection, crossing, or best-cell search."""
    rows: list[dict[str, Any]] = []
    for record in records:
        if (
            record.get("split") != "historical_replay_after_common_prior"
            or record.get("exit_id") != "seal_state_next_open"
            or record.get("cost_bps") != 60
        ):
            continue
        metric = record["joint_cash_book_metric"]
        date_ci = (metric.get("date_cluster") or {}).get("ci95") or [None, None]
        if date_ci[0] is not None and date_ci[0] > 0:
            verdict = "POSITIVE_DATE_CLUSTER_CI_UNADJUSTED_DESCRIPTIVE"
        elif date_ci[1] is not None and date_ci[1] < 0:
            verdict = "NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL"
        else:
            verdict = "INCONCLUSIVE_DATE_CLUSTER_CI"
        rows.append({
            "stratum_field": stratum_field,
            "stratum": record.get(stratum_field),
            "candidate_signals": record["candidate_signals"],
            "mature_candidate_signals": record["mature_candidate_signals"],
            "resolved_fills": record["resolved_fills"],
            "p_fill_of_mature_book": record["p_fill_of_mature_book"],
            "joint_cash_book_metric": metric,
            "verdict": verdict,
        })
    return rows


def _fixed_all_signal_book(
    main_events: pd.DataFrame,
    *,
    construction_id: str,
    stratum_field: str,
    definition: str,
) -> dict[str, Any]:
    records = _joint_candidate_book_metrics(
        main_events,
        ["split", stratum_field],
    )
    return {
        "construction_id": construction_id,
        "status": "fixed_one_dimensional_predeclared_strata_no_cross_search",
        "definition": definition,
        "selection_clock": "all stratum fields available by D close",
        "realised_D_plus_1_gap_is_selection_feature": False,
        "entry_and_cash_rule": (
            "D+1 official-open candidate fill below upper-limit queue; every mature signal in book; "
            "queue/missing/rejected entry cash=0"
        ),
        "exit_ids": list(EXIT_IDS),
        "cost_grid_bps_round_trip": list(COST_GRID_BPS),
        "primary_comparison_for_cell_verdicts": (
            "historical_replay_after_common_prior / seal_state_next_open / 60bp"
        ),
        "joint_candidate_book_metrics": records,
        "locked_replay_seal_state_60bp_cell_verdicts": _locked_replay_stratum_verdicts(
            records, stratum_field
        ),
        "combination_search": "PROHIBITED_NOT_RUN",
    }


def _crowd_clock(events: pd.DataFrame) -> list[dict[str, Any]]:
    """Frozen Friday/holiday-gap by ladder table on observed CN sessions."""
    main = events[events["market_scope"].eq("main_primary")].copy()
    main["friday_flag"] = np.where(main["weekday"].eq("Friday"), "friday", "not_friday")
    main["holiday_gap_flag"] = np.where(
        pd.to_numeric(main["calendar_gap_days"], errors="coerce") >= 4,
        "holiday_gap_ge_4_calendar_days",
        "not_holiday_gap",
    )
    group_cols = ["split", "board_count_bucket", "friday_flag", "holiday_gap_flag"]
    rows: list[dict[str, Any]] = []
    for keys, group in main.groupby(group_cols, dropna=False, sort=True):
        row = {col: value for col, value in zip(group_cols, keys)}
        group = group.copy()
        group["fill_indicator"] = group["entry_fill_state"].eq(
            "official_open_candidate_fill"
        )
        row.update({
            "signals": int(len(group)),
            "inclusive_true_next_session_continuation": metric_summary(group, "next_board", binary=True),
            "observed_bar_only_sensitivity": metric_summary(
                group, "next_board_observed_bar_sensitivity", binary=True
            ),
            "fill_rate_all_signals": float(
                group["fill_indicator"].mean()
            ),
            "fill_metric_all_signals": metric_summary(
                group, "fill_indicator", binary=True
            ),
            "joint_cash_book_seal_state_60bps": _book_summary(
                group, "seal_state_next_open", 60
            ),
        })
        rows.append(row)
    return rows


def _stress_2015(events: pd.DataFrame) -> list[dict[str, Any]]:
    """Predeclared standalone 2015 stress-era view, never hidden in pooled train."""
    dates = pd.to_datetime(events["signal_date"], errors="coerce")
    stress = events[events["market_scope"].eq("main_primary") & dates.dt.year.eq(2015)]
    rows: list[dict[str, Any]] = []
    for board_bucket, group in stress.groupby("board_count_bucket", sort=True):
        group = group.copy()
        group["fill_indicator"] = group["entry_fill_state"].eq(
            "official_open_candidate_fill"
        )
        rows.append({
            "year": 2015,
            "board_count_bucket": board_bucket,
            "signals": int(len(group)),
            "inclusive_true_next_session_continuation": metric_summary(group, "next_board", binary=True),
            "observed_bar_only_sensitivity": metric_summary(
                group, "next_board_observed_bar_sensitivity", binary=True
            ),
            "fill_rate_all_signals": float(
                group["fill_indicator"].mean()
            ),
            "fill_metric_all_signals": metric_summary(
                group, "fill_indicator", binary=True
            ),
            "joint_cash_book_seal_state_0bps": _book_summary(
                group, "seal_state_next_open", 0
            ),
            "joint_cash_book_seal_state_60bps": _book_summary(
                group, "seal_state_next_open", 60
            ),
        })
    return rows


def _fill_funnel(events: pd.DataFrame) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    group_cols = ["market_scope", "split"]
    for keys, group in events.groupby(group_cols, sort=True):
        next_available = group["next_session_available"].fillna(False).astype(bool)
        state_counts = group["next_session_state"].value_counts()
        queue = group["entry_fill_state"].eq("open_at_upper_limit_queue_no_fill")
        filled = group["entry_fill_state"].eq("official_open_candidate_fill")
        exit_counts = Counter()
        locked_deferrals = Counter()
        for exits in group.loc[filled, "exits"]:
            for exit_id, payload in (exits or {}).items():
                if payload.get("gross_return") is not None:
                    exit_counts[exit_id] += 1
                locked_deferrals[exit_id] += int(payload.get("locked_down_deferrals") or 0)
        result.append({
            "market_scope": keys[0],
            "split": keys[1],
            "signals": int(len(group)),
            "next_session_available": int(next_available.sum()),
            "next_session_missing": int((~next_available).sum()),
            "no_bar_halt_or_data_missing": int(
                state_counts.get("no_bar_halt_or_data_missing", 0)
            ),
            "right_censored_calendar_end": int(
                state_counts.get("right_censored_calendar_end", 0)
            ),
            "open_at_upper_limit_queue_no_fill": int(queue.sum()),
            "official_open_candidate_fill": int(filled.sum()),
            "fill_rate_all_signals": float(filled.mean()) if len(group) else None,
            "fill_rate_of_available": float(filled.sum() / next_available.sum()) if next_available.sum() else None,
            "entry_state_counts": {
                str(k): int(v)
                for k, v in group["entry_fill_state"].value_counts().sort_index().items()
            },
            "next_session_state_counts": {
                str(k): int(v) for k, v in state_counts.sort_index().items()
            },
            "exit_observed": dict(sorted(exit_counts.items())),
            "locked_down_deferrals": dict(sorted(locked_deferrals.items())),
        })
    return result


def _construction_results(events: pd.DataFrame) -> dict[str, Any]:
    main_events = events[events["market_scope"].eq("main_primary")].copy()
    c0 = {
        "definition": (
            "tolerant board close on D; outcome is the common CN calendar successor. "
            "A halted/missing ticker bar is retained as no_bar_halt_or_data_missing and no board."
        ),
        "ladder": _group_records(
            events,
            ["market_scope", "board_era", "split", "board_count_bucket"],
            "next_board",
            binary=True,
        ),
        "observed_bar_only_sensitivity": _group_records(
            events[events["next_session_state"].eq("observed")],
            ["market_scope", "board_era", "split", "board_count_bucket"],
            "next_board_observed_bar_sensitivity",
            binary=True,
        ),
        "next_session_competing_states": [
            {
                "market_scope": scope,
                "split": split,
                "state": state,
                "signals": int(len(group)),
            }
            for (scope, split, state), group in events.groupby(
                ["market_scope", "split", "next_session_state"], sort=True
            )
        ],
        "any_board_within_2_sessions": _group_records(
            events,
            ["market_scope", "board_era", "split", "board_count_bucket"],
            "any_board_within_2_sessions",
            binary=True,
        ),
    }

    auction = events[events["entry_fill_state"].eq("official_open_candidate_fill")].copy()
    auction_probability = _group_records(
        auction,
        ["market_scope", "split", "board_count_bucket"],
        "next_board",
        binary=True,
    )
    returns = _flatten_exit_returns(events)
    return_metrics = (
        _group_records(
            returns,
            ["market_scope", "split", "exit_id", "cost_bps"],
            "net_return",
            binary=False,
        )
        if not returns.empty
        else []
    )
    joint_book = _joint_candidate_book_metrics(events, ["market_scope", "split"])

    geometry_rows: list[dict[str, Any]] = []
    for feature in (
        "geometry_one_price_board",
        "geometry_board_day_gap_norm",
        "geometry_intraday_range_norm",
        "geometry_close_location",
        "geometry_volume_z20",
    ):
        subset = auction[auction["market_scope"].eq("main_primary")]
        for record in _group_records(subset, ["split", feature], "next_board", binary=True):
            record["geometry_feature"] = feature.removeprefix("geometry_")
            record["bucket"] = record.pop(feature)
            geometry_rows.append(record)

    ecology_rows = _group_records(
        auction,
        ["market_scope", "split", "ecology_state"],
        "next_board",
        binary=True,
    )

    postgap = events[events["entry_gap_norm"].notna()].copy()
    postgap_probability = _group_records(
        postgap,
        ["market_scope", "split", "postgap_bucket"],
        "next_board",
        binary=True,
    )

    return {
        "C0_TRUE_NEXT_SESSION": c0,
        "C_AUCTION": {
            "decision_available_at": "D close",
            "selection_fields": list(C_AUCTION_SELECTION_FIELDS),
            "realised_D_plus_1_gap_is_selection_feature": False,
            "entry": "D+1 official open only when below tolerant upper-limit queue threshold",
            "fill_funnel": _fill_funnel(events),
            "continuation_probability_after_fill_screen": auction_probability,
            "joint_candidate_book_definition": (
                "Every mature signal is in the denominator; queue/missing/rejected entries hold cash=0. "
                "Reported identity is P(fill) * E(net return | resolved fill)."
            ),
            "joint_candidate_book_metrics": joint_book,
            "filled_conditional_return_metrics": return_metrics,
            "filled_conditional_status": "distribution_of_resolved_fills_not_strategy_expectancy",
            "cost_grid_bps_round_trip": list(COST_GRID_BPS),
        },
        "C_AUCTION_N": _fixed_all_signal_book(
            main_events,
            construction_id="C_AUCTION_N",
            stratum_field="board_count_bucket",
            definition="Primary main-board C-AUCTION rider measured separately by fixed board-count bucket",
        ),
        "C_AUCTION_ONE_PRICE_D_CLOSE": _fixed_all_signal_book(
            main_events,
            construction_id="C_AUCTION_ONE_PRICE_D_CLOSE",
            stratum_field="geometry_one_price_board",
            definition="Main-board C-AUCTION book split by D-close-known one-price-board yes/no",
        ),
        "C_AUCTION_INTRADAY_RANGE_D_CLOSE": _fixed_all_signal_book(
            main_events,
            construction_id="C_AUCTION_INTRADAY_RANGE_D_CLOSE",
            stratum_field="geometry_intraday_range_norm",
            definition="Main-board C-AUCTION book split by fixed D-close-known band-normalised intraday-range bucket",
        ),
        "C_AUCTION_ECOLOGY_D_CLOSE": _fixed_all_signal_book(
            main_events,
            construction_id="C_AUCTION_ECOLOGY_D_CLOSE",
            stratum_field="ecology_state",
            definition="Main-board C-AUCTION book split by causal shrunk ecology state known at D close",
        ),
        "FROZEN_CROWD_CLOCK": {
            "status": "fixed_bin_descriptive",
            "definition": (
                "Observed common-session Friday flag crossed with >=4-calendar-day holiday gap and board-count; "
                "no vendor weekend rows enter."
            ),
            "table": _crowd_clock(events),
        },
        "PREDECLARED_2015_STRESS": {
            "status": "standalone_stress_era_not_pooled_away",
            "table": _stress_2015(events),
        },
        "BOARD_GEOMETRY_CHALLENGERS": {
            "status": "fixed_bucket_descriptive_challengers_not_feature_search",
            "main_primary_next_board_probability": geometry_rows,
        },
        "PIT_SHRUNK_ECOLOGY_CHALLENGER": {
            "status": "soft_descriptive_challenger",
            "definition": "Beta(1,1)-shrunk 20/60-session realised continuation plus lagged-through-D breadth/failure deltas",
            "thresholds": {"hot": ">=0.03", "cold": "<=-0.03", "neutral": "otherwise"},
            "next_board_probability": ecology_rows,
        },
        "C_POSTGAP": {
            "decision_available_at": "D+1 official auction result",
            "measurement": "next-close continuation probability by realised band-normalised gap bucket",
            "probability": postgap_probability,
            "return_metrics_status": "PROHIBITED_NO_FILL_HONEST_DAILY_OHLCV_EXECUTION_PRICE",
            "return_metrics": [],
        },
    }


def _find_metric(
    records: Sequence[Mapping[str, Any]],
    **filters: Any,
) -> Mapping[str, Any] | None:
    for row in records:
        if all(row.get(key) == value for key, value in filters.items()):
            return row.get("metric")
    return None


def _stratified_construction_verdict(
    results: Mapping[str, Any],
    construction_id: str,
    measured: str,
    not_measured: str,
) -> dict[str, Any]:
    cells = results[construction_id]["locked_replay_seal_state_60bp_cell_verdicts"]
    statuses = Counter(row["verdict"] for row in cells)
    if cells and statuses["NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL"] == len(cells):
        verdict = "NEGATIVE_ALL_PRIMARY_ENDPOINT_STRATA_SPECIFIC_ONLY"
    elif statuses["POSITIVE_DATE_CLUSTER_CI_UNADJUSTED_DESCRIPTIVE"]:
        verdict = "MIXED_WITH_POSITIVE_UNADJUSTED_CELLS_NO_PROMOTION"
    else:
        verdict = "MIXED_OR_INCONCLUSIVE_PRIMARY_ENDPOINT_STRATA_NO_GLOBAL_KILL"
    negative_cells = [
        str(row["stratum"])
        for row in cells
        if row["verdict"] == "NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL"
    ]
    return {
        "construction_id": construction_id,
        "verdict": verdict,
        "headline_metric": None,
        "kill_status": (
            "At locked-replay seal-state/60bp only, negative cells: "
            + ", ".join(negative_cells)
            + ". Other exits/costs and unlisted cells are not killed."
            if negative_cells
            else "none"
        ),
        "cell_verdict_counts": dict(sorted(statuses.items())),
        "ore_ledger": {
            "measured": measured,
            "not_measured": not_measured,
            "UNTESTED VARIANTS": list(UNTESTED_VARIANTS),
        },
    }


def _verdicts(results: Mapping[str, Any]) -> list[dict[str, Any]]:
    c0_metric = _find_metric(
        results["C0_TRUE_NEXT_SESSION"]["ladder"],
        market_scope="main_primary",
        split="historical_replay_after_common_prior",
        board_count_bucket="1",
        board_era="main_10pct_nonst",
    )
    auction_row = next(
        (
            row
            for row in results["C_AUCTION"]["joint_candidate_book_metrics"]
            if row.get("market_scope") == "main_primary"
            and row.get("split") == "historical_replay_after_common_prior"
            and row.get("exit_id") == "seal_state_next_open"
            and row.get("cost_bps") == 60
        ),
        None,
    )
    auction_metric = auction_row.get("joint_cash_book_metric") if auction_row else None

    auction_status = "INCONCLUSIVE_SPECIFIC_CONSTRUCTION"
    kill_scope = None
    if auction_metric and auction_metric.get("mean") is not None:
        date_ci = (auction_metric.get("date_cluster") or {}).get("ci95") or [None, None]
        if date_ci[0] is not None and date_ci[0] > 0:
            auction_status = "POSITIVE_CURATED_REPLAY_NO_PROMOTION"
        elif date_ci[1] is not None and date_ci[1] < 0:
            auction_status = "NEGATIVE_SPECIFIC_CONSTRUCTION"
            kill_scope = (
                "Only the unconditioned curated-main candidate book (all signals; nonfills cash=0), "
                "tolerant-board D-close decision / D+1 official-open rider with seal-state-next-open "
                "exit at 60bp in historical replay is killed."
            )

    common_not_tested = list(UNTESTED_VARIANTS)
    verdicts = [
        {
            "construction_id": "C0_TRUE_NEXT_SESSION",
            "verdict": "MEASURED_BASE_RATE_NO_PROMOTION",
            "headline_metric": c0_metric,
            "kill_status": "none",
            "ore_ledger": {
                "measured": (
                    "tolerant close-to-close board continuation on the common CN calendar successor; "
                    "missing/halted bars retained as failures, with observed-bar-only sensitivity"
                ),
                "UNTESTED VARIANTS": common_not_tested,
            },
        },
        {
            "construction_id": "C_AUCTION",
            "verdict": auction_status,
            "headline_metric": auction_metric,
            "kill_status": kill_scope or "none",
            "ore_ledger": {
                "measured": (
                    "official-open candidate fill after a D-close decision, upper-limit queue rejected, "
                    "T+1-valid exits, 0/30/60/100bp, and all-signal cash-book expectancy"
                ),
                "not_measured": "realised gap as a selection feature",
                "UNTESTED VARIANTS": common_not_tested,
            },
        },
        {
            "construction_id": "C_POSTGAP",
            "verdict": "PROBABILITY_ONLY_NO_RETURN_VERDICT",
            "headline_metric": None,
            "kill_status": "none; no daily-OHLCV post-auction return construction was claimed or tested",
            "ore_ledger": {
                "measured": "realised official-auction gap bucket versus next-close board probability",
                "not_measured": "09:30 or first-five-minute executable return",
                "UNTESTED VARIANTS": common_not_tested,
            },
        },
        {
            "construction_id": "BOARD_GEOMETRY_CHALLENGERS",
            "verdict": "DESCRIPTIVE_FIXED_BUCKETS_NO_PROMOTION",
            "headline_metric": None,
            "kill_status": "none",
            "ore_ledger": {
                "measured": "one-price, board-day gap, intraday range, close location, and volume-z fixed buckets",
                "not_measured": "intraday seal path and fitted nonlinear geometry model",
                "UNTESTED VARIANTS": common_not_tested,
            },
        },
        {
            "construction_id": "PIT_SHRUNK_ECOLOGY_CHALLENGER",
            "verdict": "SOFT_DESCRIPTIVE_CHALLENGER_NO_PROMOTION",
            "headline_metric": None,
            "kill_status": "none",
            "ore_ledger": {
                "measured": "causal 20/60-session shrunk continuation/breadth/failure state",
                "not_measured": "PIT sector concentration, theme topology, or exposure sizing",
                "UNTESTED VARIANTS": common_not_tested,
            },
        },
        {
            "construction_id": "FROZEN_CROWD_CLOCK",
            "verdict": "DESCRIPTIVE_FIXED_BINS_NO_PROMOTION",
            "headline_metric": None,
            "kill_status": "none",
            "ore_ledger": {
                "measured": "Friday and >=4-day holiday-gap cross by board count, continuation, fill, and joint cash book",
                "not_measured": "fitted calendar-seasonality interactions or intraday crowding",
                "UNTESTED VARIANTS": common_not_tested,
            },
        },
        {
            "construction_id": "PREDECLARED_2015_STRESS",
            "verdict": "STANDALONE_STRESS_TABLE_NO_PROMOTION",
            "headline_metric": None,
            "kill_status": "none",
            "ore_ledger": {
                "measured": "2015 main-board continuation, fill, and joint cash book by board count",
                "not_measured": "portfolio liquidity/capacity and intraday queue behavior during the 2015 crash",
                "UNTESTED VARIANTS": common_not_tested,
            },
        },
        {
            "construction_id": "VENDOR_DESCRIPTIVE_STRATUM",
            "verdict": "DESCRIPTIVE_VALID_SESSIONS_ONLY_NO_PROMOTION",
            "headline_metric": None,
            "kill_status": "none",
            "ore_ledger": {
                "measured": "seal_fund_yi, failed_seals, and turnover probability strata on valid observed vendor sessions",
                "not_measured": "pre-coverage zeros; clone dates; executable returns; normalized seal-fund intensity",
                "UNTESTED VARIANTS": common_not_tested
                + list(results.get("VENDOR_DESCRIPTIVE_STRATUM", {}).get("UNTESTED VARIANTS", [])),
            },
        },
    ]
    stratified = [
        _stratified_construction_verdict(
            results,
            "C_AUCTION_N",
            "main-board all-signal candidate books by fixed board-count bucket, all five exits and four costs",
            "crossed board-count/geometry/ecology search or post-auction gap selection",
        ),
        _stratified_construction_verdict(
            results,
            "C_AUCTION_ONE_PRICE_D_CLOSE",
            "main-board all-signal candidate books by D-close-known one-price yes/no, all five exits and four costs",
            "intraday queue duration, seal path, and crossed feature combinations",
        ),
        _stratified_construction_verdict(
            results,
            "C_AUCTION_INTRADAY_RANGE_D_CLOSE",
            "main-board all-signal candidate books by fixed D-close intraday-range buckets, all five exits and four costs",
            "fitted range cut points and crossed feature combinations",
        ),
        _stratified_construction_verdict(
            results,
            "C_AUCTION_ECOLOGY_D_CLOSE",
            "main-board all-signal candidate books by causal D-close ecology state, all five exits and four costs",
            "PIT theme topology and crossed ecology/geometry optimisation",
        ),
    ]
    return verdicts[:2] + stratified + verdicts[2:]


def _input_fingerprint(files: Sequence[Path], diagnostics: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {
            "name": p.name,
            "bytes": p.stat().st_size,
            "rows": diagnostics[i].get("rows") if i < len(diagnostics) else None,
        }
        for i, p in enumerate(files)
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_current_st(path: Path) -> tuple[set[str], dict[str, Any]]:
    if not path.exists():
        return set(), {"path": str(path), "status": "missing", "rows": 0, "asof": None}
    frame = pd.read_parquet(path)
    tickers = set(frame.get("ticker", pd.Series(dtype=str)).dropna().astype(str))
    asof = sorted(set(frame.get("asof", pd.Series(dtype=str)).dropna().astype(str)))
    return tickers, {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "status": "current_snapshot_only_not_historical_membership",
        "rows": int(len(frame)),
        "unique_tickers": int(len(tickers)),
        "asof": asof,
    }


def _zt_inventory(path: Path, raw_tickers: set[str]) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    frame = pd.read_parquet(path, columns=["ticker", "date"])
    tickers = set(frame["ticker"].dropna().astype(str))
    overlap = tickers & raw_tickers
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna()
    return {
        "status": "inventory_with_valid-session-descriptive-join",
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "rows": int(len(frame)),
        "unique_tickers": int(len(tickers)),
        "raw_overlap_tickers": int(len(overlap)),
        "raw_overlap_pct": float(len(overlap) / len(tickers) * 100.0) if tickers else None,
        "vendor_tickers_without_raw_ohlcv": int(len(tickers - raw_tickers)),
        "stamped_dates": int(dates.nunique()),
        "first_stamped_date": str(dates.min().date()) if len(dates) else None,
        "last_stamped_date": str(dates.max().date()) if len(dates) else None,
        "limitation": "weekend clones are excluded and missing sessions are never imputed as zero",
    }


def _vendor_descriptive_stratum(
    path: Path,
    events: pd.DataFrame,
    market_calendar: MarketCalendar,
) -> dict[str, Any]:
    """Join only genuinely observed vendor sessions; never manufacture zeros."""
    if not path.exists():
        return {"status": "missing", "path": str(path), "probability_tables": []}
    frame = pd.read_parquet(path)
    required = {"ticker", "date", "asof", "seal_fund_yi", "failed_seals", "turnover_pct"}
    missing = sorted(required - set(frame.columns))
    if missing:
        return {
            "status": "missing_required_columns",
            "missing_columns": missing,
            "probability_tables": [],
        }
    frame = frame.copy()
    frame["date_ts"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["asof_ts"] = pd.to_datetime(frame["asof"], errors="coerce").dt.normalize()
    calendar_set = set(market_calendar.sessions)
    valid_mask = frame["date_ts"].isin(calendar_set)
    clone_dates = sorted(
        str(value.date())
        for value in frame.loc[~valid_mask, "date_ts"].dropna().drop_duplicates()
    )
    valid = frame.loc[valid_mask].copy()
    valid["observation_class"] = np.where(
        valid["asof_ts"] > valid["date_ts"],
        "retrospectively_fetched_not_proven_PIT",
        "same_day_stamp",
    )
    valid["signal_date"] = valid["date_ts"].dt.strftime("%Y-%m-%d")
    valid["ticker"] = valid["ticker"].astype(str)
    event_fields = events[
        [
            "ticker",
            "signal_date",
            "market_scope",
            "split",
            "next_board",
            "date_cluster",
            "run_cluster",
        ]
    ]
    joined = event_fields.merge(valid, on=["ticker", "signal_date"], how="inner", validate="one_to_one")

    def fixed_bucket(series: pd.Series, cuts: Sequence[float], labels: Sequence[str]) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        return pd.cut(numeric, bins=[-math.inf, *cuts, math.inf], labels=labels).astype(str).replace("nan", "missing")

    if not joined.empty:
        joined["seal_fund_yi_bucket"] = fixed_bucket(
            joined["seal_fund_yi"], (0.5, 2.0), ("le_0_5_yi", "0_5_to_2_yi", "gt_2_yi")
        )
        joined["failed_seals_bucket"] = fixed_bucket(
            joined["failed_seals"], (0.0, 2.0), ("zero", "one_to_two", "three_plus")
        )
        joined["turnover_pct_bucket"] = fixed_bucket(
            joined["turnover_pct"], (5.0, 15.0), ("le_5pct", "5_to_15pct", "gt_15pct")
        )
    probability_tables: list[dict[str, Any]] = []
    for field in ("seal_fund_yi", "failed_seals", "turnover_pct"):
        bucket_col = f"{field}_bucket"
        if joined.empty:
            continue
        for record in _group_records(
            joined,
            ["market_scope", "observation_class", bucket_col],
            "next_board",
            binary=True,
        ):
            record["vendor_field"] = field
            record["bucket"] = record.pop(bucket_col)
            probability_tables.append(record)

    valid_dates = pd.DatetimeIndex(valid["date_ts"].dropna().unique()).sort_values()
    if len(valid_dates):
        expected = market_calendar.sessions[
            (market_calendar.sessions >= valid_dates.min())
            & (market_calendar.sessions <= valid_dates.max())
        ]
        missing_observed_sessions = [
            str(value.date()) for value in expected if value not in set(valid_dates)
        ]
    else:
        missing_observed_sessions = []
    retrospective = valid[valid["observation_class"].eq("retrospectively_fetched_not_proven_PIT")]
    return {
        "status": "descriptive_probability_only_no_imputation_no_return_verdict",
        "rows_total": int(len(frame)),
        "valid_observed_session_rows": int(len(valid)),
        "valid_observed_sessions": int(valid["date_ts"].nunique()),
        "excluded_clone_rows": int((~valid_mask).sum()),
        "excluded_clone_dates": clone_dates,
        "missing_sessions_within_vendor_span_no_zero_imputation": missing_observed_sessions,
        "retrospectively_fetched_rows": int(len(retrospective)),
        "retrospectively_fetched_dates": sorted(
            str(value.date()) for value in retrospective["date_ts"].dropna().drop_duplicates()
        ),
        "same_day_rows": int(valid["observation_class"].eq("same_day_stamp").sum()),
        "joined_curated_event_rows": int(len(joined)),
        "seal_fund_status": "absolute_unscaled_amount_not_normalized_by_traded_value_descriptive_only",
        "probability_tables": probability_tables,
        "return_metrics": [],
        "UNTESTED VARIANTS": [
            "normalised seal fund divided by contemporaneous traded value",
            "true PIT vendor capture before the retrospective fetch window",
            "zero-event session confirmation from an independent complete vendor response",
            "vendor-only tickers without local nominal OHLCV continuation labels",
        ],
    }


def run_measurement(
    *,
    raw_dir: Path = DEFAULT_RAW_DIR,
    calendar_path: Path = DEFAULT_CALENDAR_PATH,
    st_path: Path = DEFAULT_ST_PATH,
    zt_path: Path = DEFAULT_ZT_PATH,
    max_files: int | None = None,
) -> dict[str, Any]:
    files = sorted(raw_dir.glob("*.parquet"))
    if max_files is not None:
        files = files[: max(0, int(max_files))]
    if not files:
        raise FileNotFoundError(f"no nominal OHLCV parquet files under {raw_dir}")

    market_calendar = load_market_calendar(calendar_path)

    raw_tickers = {p.stem for p in files}
    current_st, st_inventory = _load_current_st(st_path)
    excluded_current_st = raw_tickers & current_st

    events_rows: list[dict[str, Any]] = []
    daily_counters: dict[str, Counter] = {
        name: Counter() for name in ("universe_n", "sealed_up", "first_board", "failed_up", "sealed_down")
    }
    diagnostics: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    board_files = Counter()
    total_rows = 0

    for ordinal, path in enumerate(files, 1):
        ticker = path.stem
        board = board_from_ticker(ticker)
        board_files[board] += 1
        if ticker in excluded_current_st:
            diagnostics.append({"ticker": ticker, "status": "excluded_current_st", "rows": 0})
            continue
        try:
            frame = pd.read_parquet(path)
            rows, counters, diag = extract_ticker_events(
                ticker, frame, market_calendar=market_calendar
            )
            total_rows += int(diag.get("rows") or 0)
            diagnostics.append({"ticker": ticker, **diag})
            events_rows.extend(rows)
            for name, source in counters.items():
                _merge_counter(daily_counters[name], source)
        except Exception as exc:  # noqa: BLE001 - audit must report every unreadable input
            errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
            diagnostics.append({"ticker": ticker, "status": "error", "rows": 0})
        if ordinal % 100 == 0:
            log.info("processed %d/%d files; %d board-event rows", ordinal, len(files), len(events_rows))
            gc.collect()

    if not events_rows:
        raise RuntimeError("measurement produced no tolerant limit-up events")

    events = pd.DataFrame(events_rows)
    ecology = _build_ecology(daily_counters, events, market_calendar.sessions)
    ecology_join = ecology.set_index(ecology["date"].dt.strftime("%Y-%m-%d"))[
        [
            "continuation_20_shrunk",
            "continuation_60_shrunk",
            "up_breadth_20",
            "up_breadth_60",
            "failed_share_20",
            "failed_share_60",
            "ecology_soft_score",
            "ecology_state",
        ]
    ]
    events = events.join(ecology_join, on="signal_date", rsuffix="_daily")
    calendar = market_calendar.sessions[
        (market_calendar.sessions >= START_DATE) & (market_calendar.sessions <= END_DATE)
    ]
    events_unpurged = len(events)
    events, purge = apply_boundary_purge(events, calendar)

    results = _construction_results(events)
    results["VENDOR_DESCRIPTIVE_STRATUM"] = _vendor_descriptive_stratum(
        zt_path, events, market_calendar
    )
    tolerant_total = sum(int(d.get("tolerant_sealed_up_rows") or 0) for d in diagnostics)
    strict_total = sum(int(d.get("strict_sealed_up_rows") or 0) for d in diagnostics)
    marginal_total = sum(int(d.get("marginal_tolerant_rows") or 0) for d in diagnostics)
    rows_off_common_calendar = sum(
        int(d.get("rows_off_common_calendar") or 0) for d in diagnostics
    )
    rows_off_common_calendar_in_window = sum(
        int(d.get("rows_off_common_calendar_in_measurement_window") or 0)
        for d in diagnostics
    )
    first_dates = [d.get("first_session") for d in diagnostics if d.get("first_session")]
    last_dates = [d.get("last_session") for d in diagnostics if d.get("last_session")]

    receipt: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "receipt_date": RECEIPT_DATE,
        "authority": AUTHORITY,
        "construction_contract": {
            "price_source": "data/china_stocks_raw nominal daily OHLCV",
            "limit_definition": (
                "tolerant sealed-up iff close >= round(prev_close*(1+board_width),2)*(1-0.002); "
                "strict rides beside it"
            ),
            "tolerance_fraction_of_limit_price": LIMIT_TOLERANCE,
            "minimum_prior_sessions": MIN_PRIOR_SESSIONS,
            "session_clock": (
                "data/china/000001.SS.parquet Shanghai Composite observed sessions; the C0 target is "
                "the calendar successor, never the next later ticker row"
            ),
            "missing_next_session_state": (
                "no_bar_halt_or_data_missing is retained in the primary denominator as no continuation; "
                "observed-bar-only is a named sensitivity and entry is no-fill"
            ),
            "ladder_adjacency": (
                "primary 连板 increments only across adjacent common CN market sessions and resets after a missing/halted bar"
            ),
            "exdiv_suppression": "abs(open/prev_close-1) > 1.5*board_width",
            "primary_universe": "curated main-board non-current-ST-intersection names",
            "secondary_universe": "ChiNext 10% and 20% eras reported separately",
            "descriptive_universe": "STAR",
            "untested_universe": "BSE and ST/risk-warning",
            "st_rule_truth": "main-board ST 5% before 2026-07-06, 10% on/after; not applied without PIT membership",
            "entry_clock": "C-AUCTION decision after D close, candidate fill at D+1 official open",
            "fill_rule": "open within tolerant cushion of D+1 upper limit is an unfilled queue",
            "candidate_book_return": (
                "all mature signals in denominator; queue/rejected/missing entries cash=0; "
                "P(fill)*E(net|fill) stated explicitly"
            ),
            "postgap_rule": "realised D+1 gap appears only in probability tables; no strategy return",
            "exits": [
                "entry-relative T+1 legal open",
                "entry-relative T+1 legal close",
                "entry-relative T+2 close",
                "entry-relative T+4 close",
                "next sellable open after first unsealed close",
            ],
            "cost_grid_bps_round_trip": list(COST_GRID_BPS),
            "cluster_inference": "intercept-only date-cluster and board-run-cluster robust 95% intervals",
        },
        "frozen_splits": [
            {
                "id": name,
                "role": {
                    "train_2011_2019": "train",
                    "calibration_2020_2023": "calibration",
                    "historical_replay_after_common_prior": (
                        "locked_test_block_but_labelled_historical_replay_not_virgin"
                    ),
                    "vendor_tail_audit": "vendor_tail_audit",
                }[name],
                "start": str(start.date()),
                "end": str(end.date()),
            }
            for name, start, end in SPLITS
        ],
        "boundary_purge": purge,
        "data_inventory": {
            "raw_files_discovered": int(len(files)),
            "raw_files_read": int(sum(d.get("status") == "ok" for d in diagnostics)),
            "raw_files_error": int(len(errors)),
            "raw_files_excluded_current_st": int(len(excluded_current_st)),
            "raw_files_by_board": dict(sorted(board_files.items())),
            "raw_rows_read": int(total_rows),
            "raw_rows_off_common_cn_session_calendar": int(rows_off_common_calendar),
            "raw_rows_off_common_cn_session_calendar_in_measurement_window": int(
                rows_off_common_calendar_in_window
            ),
            "raw_first_session": min(first_dates) if first_dates else None,
            "raw_last_session": max(last_dates) if last_dates else None,
            "common_cn_session_calendar": {
                "path": (
                    str(calendar_path.relative_to(ROOT))
                    if calendar_path.is_relative_to(ROOT)
                    else str(calendar_path)
                ),
                "source": "Shanghai Composite observed sessions",
                "sessions_total": int(len(market_calendar.sessions)),
                "sessions_in_measurement_window": int(len(calendar)),
                "first_session": str(market_calendar.sessions.min().date()),
                "last_session": str(market_calendar.sessions.max().date()),
            },
            "input_universe_fingerprint": _input_fingerprint(files, diagnostics),
            "read_errors": errors,
            "st_snapshot": st_inventory,
            "zt_pool": _zt_inventory(zt_path, raw_tickers),
            "curated_slice_warning": (
                "The local nominal OHLCV universe is a curated slice. Results do not generalise to the "
                "full 打板 universe or to vendor-observed names without local price history."
            ),
        },
        "event_inventory": {
            "tolerant_sealed_up_detected_before_purge": int(tolerant_total),
            "strict_sealed_up_detected_before_purge": int(strict_total),
            "marginal_tolerant_events_before_purge": int(marginal_total),
            "event_rows_before_boundary_purge": int(events_unpurged),
            "event_rows_measured": int(len(events)),
            "event_rows_by_market_scope": {
                str(k): int(v) for k, v in events["market_scope"].value_counts().sort_index().items()
            },
            "event_rows_by_split": {
                str(k): int(v) for k, v in events["split"].value_counts().sort_index().items()
            },
            "date_clusters": int(events["date_cluster"].nunique()),
            "run_clusters": int(events["run_cluster"].nunique()),
            "next_session_state_counts": {
                str(k): int(v)
                for k, v in events["next_session_state"].value_counts().sort_index().items()
            },
        },
        "results": results,
        "construction_verdicts": _verdicts(results),
        "limitations": [
            "historical replay after a common prior is not a virgin holdout",
            "vendor fields are descriptive only on valid observed sessions; clone dates are excluded and missing sessions are not imputed",
            "nominal yfinance-like bars require a tolerance and corporate-action heuristic",
            "daily bars identify official opens but not queue priority, partial fills, or a 09:30 execution",
            "current ST membership is not historical membership; the family remains untested",
        ],
        "UNTESTED VARIANTS": list(UNTESTED_VARIANTS),
    }
    return receipt


def _pct(value: Any) -> str:
    return "n/a" if value is None else f"{float(value) * 100:.2f}%"


def _metric_line(metric: Mapping[str, Any] | None) -> str:
    if not metric:
        return "n/a"
    date_ci = (metric.get("date_cluster") or {}).get("ci95") or [None, None]
    ci = (
        "n/a"
        if date_ci[0] is None
        else f"[{_pct(date_ci[0])}, {_pct(date_ci[1])}]"
    )
    return f"n={metric.get('n', 0):,}; mean={_pct(metric.get('mean'))}; date-cluster 95% CI={ci}"


def render_markdown(receipt: Mapping[str, Any]) -> str:
    inventory = receipt["data_inventory"]
    event_inventory = receipt["event_inventory"]
    zt = inventory["zt_pool"]
    verdicts = receipt["construction_verdicts"]
    lines = [
        "# CN limit-up continuation — SOL Wave-1 deterministic receipt",
        "",
        f"**Receipt date:** {receipt['receipt_date']}",
        f"**Authority:** `{receipt['authority']}`",
        f"**Model/definition:** `{receipt['model_version']}`",
        "",
        "> Curated-slice warning: this receipt does not describe the full 打板 universe. "
        f"The vendor pool has {zt.get('unique_tickers', 0):,} distinct tickers, but only "
        f"{zt.get('raw_overlap_tickers', 0):,} ({zt.get('raw_overlap_pct', 0):.2f}%) overlap "
        "the local nominal OHLCV slice.",
        "",
        "## Frozen contract",
        "",
        "- `C0`: tolerant board close on D to the common CN calendar successor. A missing/halted ticker bar "
        "stays in the primary denominator as no board; observed-bar-only results are a named sensitivity.",
        "- `C-AUCTION`: features stop at D close. The candidate fill is D+1 official open; an open within "
        "the tolerant upper-limit cushion is an unfilled queue. The realised D+1 gap is not a selection filter.",
        "- `C-POSTGAP`: realised auction gap conditions next-board probability only. There is deliberately no "
        "daily-OHLCV return claim because 09:30/first-five-minute execution is absent.",
        "- T+1 exits begin no earlier than D+2 for a D+1-open entry. Every exit resolves on exact market "
        "sessions; a missing bar is unresolved, and lower-limit carry advances one market session at a time.",
        "- Main board is primary; ChiNext band eras are separate secondary cohorts; STAR is descriptive; "
        "BSE/ST are untested.",
        "",
        "## Data and event inventory",
        "",
        f"- Raw files: {inventory['raw_files_read']:,} read / {inventory['raw_files_discovered']:,} discovered; "
        f"{inventory['raw_files_error']} errors; {inventory['raw_files_excluded_current_st']} current-ST intersections excluded.",
        f"- Raw rows: {inventory['raw_rows_read']:,}; sessions {inventory['raw_first_session']} to {inventory['raw_last_session']}.",
        f"- Tolerant boards: {event_inventory['tolerant_sealed_up_detected_before_purge']:,}; strict boards: "
        f"{event_inventory['strict_sealed_up_detected_before_purge']:,}; marginal tolerance rows: "
        f"{event_inventory['marginal_tolerant_events_before_purge']:,}.",
        f"- Measured after boundary purge: {event_inventory['event_rows_measured']:,} signals, "
        f"{event_inventory['date_clusters']:,} date clusters, {event_inventory['run_clusters']:,} board-run clusters.",
        f"- `china_zt_pool` vendor strata use valid observed sessions only: "
        f"{len(receipt['results']['VENDOR_DESCRIPTIVE_STRATUM'].get('excluded_clone_dates', []))} clone dates "
        "are excluded, missing sessions are not imputed, and retrospective rows are explicitly stamped non-PIT.",
        "",
        "## Construction verdicts",
        "",
    ]
    for verdict in verdicts:
        lines.extend([
            f"### {verdict['construction_id']}",
            "",
            f"- Verdict: **{verdict['verdict']}**",
            f"- Headline: {_metric_line(verdict.get('headline_metric'))}",
            f"- Kill scope: {verdict['kill_status']}",
            f"- Measured: {verdict['ore_ledger'].get('measured')}",
            f"- Not measured: {verdict['ore_ledger'].get('not_measured', 'see ore ledger below')}",
            "",
        ])

    main_funnel = next(
        (
            row
            for row in receipt["results"]["C_AUCTION"]["fill_funnel"]
            if row.get("market_scope") == "main_primary"
            and row.get("split") == "historical_replay_after_common_prior"
        ),
        None,
    )
    lines.extend([
        "## Main historical-replay fill funnel",
        "",
        "| Signals | Exact next bar | Halt/missing | Upper-limit queue | Candidate fills | Fill / all signals |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    if main_funnel:
        lines.append(
            f"| {main_funnel['signals']:,} | {main_funnel['next_session_available']:,} | "
            f"{main_funnel['no_bar_halt_or_data_missing']:,} | "
            f"{main_funnel['open_at_upper_limit_queue_no_fill']:,} | "
            f"{main_funnel['official_open_candidate_fill']:,} | "
            f"{_pct(main_funnel['fill_rate_all_signals'])} |"
        )
    else:
        lines.append("| 0 | 0 | 0 | 0 | 0 | n/a |")

    lines.extend([
        "",
        "The strategy-level return is the joint candidate-book mean with nonfills held at cash=0. "
        "Filled-conditional distributions remain diagnostics, not expectancy.",
        "",
        "## Fixed pre-auction rider books — locked replay primary comparison, seal-state exit, 60bp",
        "",
        "These are separate one-dimensional predeclared strata. The JSON includes every fixed exit and "
        "0/30/60/100bp; this compact table is the seal-state/60bp primary comparison only. No crossed "
        "combination or best-cell tuning was run.",
        "",
        "| Construction | Fixed stratum | Candidates | Mature book | Fill / mature | Joint cash-book mean | Date-cluster 95% CI | Cell verdict |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ])
    for construction_id in (
        "C_AUCTION_N",
        "C_AUCTION_ONE_PRICE_D_CLOSE",
        "C_AUCTION_INTRADAY_RANGE_D_CLOSE",
        "C_AUCTION_ECOLOGY_D_CLOSE",
    ):
        for row in receipt["results"][construction_id][
            "locked_replay_seal_state_60bp_cell_verdicts"
        ]:
            metric = row["joint_cash_book_metric"]
            ci = (metric.get("date_cluster") or {}).get("ci95") or [None, None]
            ci_text = (
                "n/a"
                if ci[0] is None
                else f"[{_pct(ci[0])}, {_pct(ci[1])}]"
            )
            lines.append(
                f"| {construction_id} | {row['stratum']} | {row['candidate_signals']:,} | "
                f"{row['mature_candidate_signals']:,} | {_pct(row['p_fill_of_mature_book'])} | "
                f"{_pct(metric.get('mean'))} | {ci_text} | {row['verdict']} |"
            )

    lines.extend([
        "",
        "## Frozen crowd clock",
        "",
        "| Split | Board | Friday | Holiday gap | Signals | Mature book | Inclusive continuation | Fill / all | Joint seal-state 60bp |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in receipt["results"]["FROZEN_CROWD_CLOCK"]["table"]:
        joint = row["joint_cash_book_seal_state_60bps"]["joint_cash_book_metric"]
        lines.append(
            f"| {row['split']} | {row['board_count_bucket']} | {row['friday_flag']} | "
            f"{row['holiday_gap_flag']} | {row['signals']:,} | "
            f"{joint.get('n', 0):,} | "
            f"{_pct(row['inclusive_true_next_session_continuation'].get('mean'))} | "
            f"{_pct(row['fill_rate_all_signals'])} | {_pct(joint.get('mean'))} |"
        )

    lines.extend([
        "",
        "## Predeclared 2015 standalone stress era",
        "",
        "This table is printed separately so the pooled 2011–2019 train average cannot hide crisis behaviour.",
        "",
        "| Board | Signals | Inclusive continuation | Observed-bar sensitivity | Fill / all | Joint state 0bp | Joint state 60bp |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in receipt["results"]["PREDECLARED_2015_STRESS"]["table"]:
        joint0 = row["joint_cash_book_seal_state_0bps"]["joint_cash_book_metric"]
        joint60 = row["joint_cash_book_seal_state_60bps"]["joint_cash_book_metric"]
        lines.append(
            f"| {row['board_count_bucket']} | {row['signals']:,} | "
            f"{_pct(row['inclusive_true_next_session_continuation'].get('mean'))} | "
            f"{_pct(row['observed_bar_only_sensitivity'].get('mean'))} | "
            f"{_pct(row['fill_rate_all_signals'])} | {_pct(joint0.get('mean'))} | "
            f"{_pct(joint60.get('mean'))} |"
        )

    vendor = receipt["results"]["VENDOR_DESCRIPTIVE_STRATUM"]
    lines.extend([
        "",
        "## Vendor descriptive stratum",
        "",
        f"- Valid observed-session rows: {vendor.get('valid_observed_session_rows', 0):,}; "
        f"excluded clone rows: {vendor.get('excluded_clone_rows', 0):,} across "
        f"{len(vendor.get('excluded_clone_dates', []))} dates.",
        f"- Retrospectively fetched/not-proven-PIT rows: {vendor.get('retrospectively_fetched_rows', 0):,}; "
        f"joined curated event rows: {vendor.get('joined_curated_event_rows', 0):,}.",
        "- Absolute seal fund is unnormalised; all vendor-field verdicts remain descriptive.",
        "",
    ])

    lines.extend([
        "## Honesty notes",
        "",
        "- `historical_replay_after_common_prior` is labelled replay, never unseen test.",
        "- The 0/30/60/100 bp grid is a round-trip friction sensitivity, not a live fill model.",
        "- Date- and board-run-cluster intervals accompany pooled means; clustered names on one board-festival date "
        "are not treated as independent evidence.",
        "- No construction receives ranking, sizing, gating, or trading authority.",
        "",
        "## UNTESTED VARIANTS",
        "",
    ])
    lines.extend(f"- {item}" for item in receipt["UNTESTED VARIANTS"])
    return "\n".join(lines) + "\n"


def write_receipts(receipt: Mapping[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(receipt), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--calendar-path", type=Path, default=DEFAULT_CALENDAR_PATH)
    parser.add_argument("--st-path", type=Path, default=DEFAULT_ST_PATH)
    parser.add_argument("--zt-path", type=Path, default=DEFAULT_ZT_PATH)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--max-files", type=int, default=None, help="debug-only deterministic prefix")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    receipt = run_measurement(
        raw_dir=args.raw_dir,
        calendar_path=args.calendar_path,
        st_path=args.st_path,
        zt_path=args.zt_path,
        max_files=args.max_files,
    )
    write_receipts(receipt, args.output_json, args.output_markdown)
    log.info("wrote %s and %s", args.output_json, args.output_markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
