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

SCHEMA_VERSION = "cn_limit_continuation_w1/v4"
MODEL_VERSION = "sol_w1_era_aware_traded_ipo_canonical_vendor_2026-08-08"
RECEIPT_DATE = "2026-08-08"
AUTHORITY = "none_research_display_only"

DEFAULT_RAW_DIR = ROOT / "data" / "china_stocks_raw"
DEFAULT_CALENDAR_PATH = ROOT / "data" / "china_stocks_raw" / "600519.SS.parquet"
DEFAULT_ST_PATH = ROOT / "data" / "china_st" / "st_snapshot.parquet"
DEFAULT_ZT_PATH = ROOT / "data" / "china_zt_pool" / "pool.parquet"
DEFAULT_JSON = ROOT / "research" / "cn_limit_alpha_sol" / "W1_CONTINUATION_MEASUREMENT_2026-08-08.json"
DEFAULT_MARKDOWN = ROOT / "research" / "cn_limit_alpha_sol" / "W1_CONTINUATION_MEASUREMENT_2026-08-08.md"

START_DATE = pd.Timestamp("2011-01-01")
END_DATE = pd.Timestamp("2026-08-07")
CHINEXT_WIDE_DATE = pd.Timestamp("2020-08-24")
ST_RULE_CHANGE_DATE = pd.Timestamp("2026-07-06")
MAIN_REGISTRATION_IPO_FIRST5_DATE = pd.Timestamp("2023-04-10")
CHINEXT_REGISTRATION_IPO_FIRST5_DATE = pd.Timestamp("2020-08-24")
STAR_FIRST_LISTING_DATE = pd.Timestamp("2019-07-22")
MIN_PRIOR_SESSIONS = 60
LIMIT_TOLERANCE = 0.002
BOUNDARY_PURGE_SESSIONS = 10
COST_GRID_BPS = (0, 30, 60, 100)
EXPECTED_CALENDAR_SESSIONS = 3_786
RAW_DATE_SUPPORT_CONSENSUS_MIN_NAMES = 50
IPO_RULE_EVIDENCE = {
    "sse_main_first_five_rule": "https://www.sse.com.cn/lawandrules/sselawsrules2025/repeal/rules/c/c_20250612_10824490.shtml",
    "sse_main_registration_onset": "https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20230404_5719112.shtml",
    "szse_main_first_five_rule": "https://docs.static.szse.cn/www/lawrules/rule/allrules/bussiness/W020230217564423808793.pdf",
    "chinext_pre_reform_rule": "https://docs.static.szse.cn/www/aboutus/trends/news/W020180328462965472234.pdf",
    "chinext_reform_mechanics": "https://www.szse.cn/www/investor/index/update/t20200807_580310.html",
    "chinext_registration_onset": "https://www.szse.cn/aboutus/trends/news/t20200821_580924.html",
    "star_first_listing_onset": "https://star.sse.com.cn/star/media/news/c/c_20190719_4866789.shtml",
}
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
    "complete five-axis continuation strata: vol_z20, runup_5, gap_pct, dist_52w_low, and consec_up_days",
    "strict first-touch and intraday seal-path sensitivity beyond the measured strict sealed-close sensitivity",
    "active-ceiling, 3-session acceleration, and leader-failure-shock ecology constructions",
    "N>=3 continuation riders beyond explicitly exploratory descriptive cells",
    "capital/theme/capacity-complete portfolio simulation beyond the frozen self-financing cash-reservation proxy",
    "complete official listing-date master beyond first positive-volume common-session inference",
    "vendor security-master identity beyond the explicit .SH to .SS suffix canonicalization",
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


def canonical_ticker(ticker: Any) -> str:
    """Normalize the repo's Shanghai suffix alias without changing exchange identity."""
    value = str(ticker).strip().upper()
    return f"{value[:-3]}.SS" if value.endswith(".SH") else value


def ipo_no_limit_rule(
    board: str,
    first_positive_volume_date: pd.Timestamp | None,
) -> tuple[str, int]:
    """Return the era-aware no-limit regime and traded-session count.

    The ordinal is applied only to positive-volume ticker observations. Raw
    issue-price placeholders and other no-trade rows neither start nor advance
    the listing clock.
    """
    if first_positive_volume_date is None:
        return "no_positive_volume_listing_session", 0
    listing_date = pd.Timestamp(first_positive_volume_date).normalize()
    if board == "main":
        if listing_date >= MAIN_REGISTRATION_IPO_FIRST5_DATE:
            return "main_registration_first_five", 5
        return "main_historical_listing_day_only", 1
    if board == "chinext":
        if listing_date >= CHINEXT_REGISTRATION_IPO_FIRST5_DATE:
            return "chinext_registration_first_five", 5
        return "chinext_pre_reform_listing_day_only", 1
    if board == "star":
        return "star_from_inception_first_five", 5
    return "unsupported_board_no_ipo_rule", 0


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
    """Load the Wave-0-complete observed CN session anchor."""
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
    volumes: np.ndarray,
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
        if not _is_finite_positive(volumes[j]):
            return ExitObservation(
                None,
                str(current.date()),
                j,
                deferrals,
                "zero_volume_halt_or_no_trade",
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
    volumes: np.ndarray,
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
            opens, lowers, volumes, dates, target_date, market_calendar, date_to_index
        )
    if not _is_finite_positive(volumes[target_index]):
        return ExitObservation(
            None,
            str(target_date.date()),
            target_index,
            0,
            "zero_volume_halt_or_no_trade",
        )
    if not _is_finite_positive(closes[target_index]) or not _is_finite_positive(lowers[target_index]):
        return ExitObservation(None, None, None, 0, "target_price_missing")
    if tolerant_at_lower(float(closes[target_index]), float(lowers[target_index])):
        carried = _sellable_open(
            opens,
            lowers,
            volumes,
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
    volumes: np.ndarray,
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
        if not _is_finite_positive(volumes[j]):
            return (
                ExitObservation(
                    None,
                    str(current.date()),
                    j,
                    0,
                    "zero_volume_halt_or_no_trade",
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
                opens,
                lowers,
                volumes,
                dates,
                exit_date,
                market_calendar,
                date_to_index,
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
    # injects the Wave-0-complete common CN clock.  Never use a later
    # ticker row as a substitute for a missing true-next market session.
    clock = market_calendar or MarketCalendar.from_dates(dates)
    calendar_positions = np.array([clock.position.get(d, -1) for d in dates], dtype=int)
    opens = pd.to_numeric(df["open"], errors="coerce").to_numpy(dtype=float)
    highs = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    lows = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    closes = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    volume_series = pd.to_numeric(df["volume"], errors="coerce")
    volumes = volume_series.to_numpy(dtype=float)
    positive_volume = np.isfinite(volumes) & (volumes > 0)
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
    positive_volume_traded_session = positive_volume & calendar_ok
    positive_volume_indices = np.flatnonzero(positive_volume_traded_session)
    first_positive_volume_index = (
        int(positive_volume_indices[0]) if len(positive_volume_indices) else None
    )
    listing_date = (
        dates[first_positive_volume_index]
        if first_positive_volume_index is not None
        else None
    )
    ipo_regime, ipo_no_limit_sessions = ipo_no_limit_rule(board, listing_date)
    traded_session_ordinal = np.full(len(df), -1, dtype=int)
    traded_session_ordinal[positive_volume_traded_session] = np.arange(
        int(positive_volume_traded_session.sum())
    )
    ipo_no_limit = (
        positive_volume_traded_session
        & (traded_session_ordinal >= 0)
        & (traded_session_ordinal < ipo_no_limit_sessions)
    )
    price_eligible_before_calendar = (
        finite & age_ok & in_window & era_ok & ~exdiv_suspect & ~ipo_no_limit
    )
    price_eligible = price_eligible_before_calendar & calendar_ok
    eligible = price_eligible & positive_volume
    off_calendar_eligible = price_eligible_before_calendar & positive_volume & ~calendar_ok
    zero_volume_price_eligible = price_eligible & ~positive_volume
    zero_volume_board_price = zero_volume_price_eligible & (
        closes >= uppers * (1.0 - LIMIT_TOLERANCE)
    )

    tolerant_sealed_up = eligible & (closes >= uppers * (1.0 - LIMIT_TOLERANCE))
    strict_sealed_up = eligible & (closes >= uppers)
    tolerant_touched_up = eligible & (highs >= uppers * (1.0 - LIMIT_TOLERANCE))
    tolerant_failed_up = tolerant_touched_up & ~tolerant_sealed_up
    tolerant_sealed_down = eligible & (closes <= lowers * (1.0 + LIMIT_TOLERANCE))

    streak = np.zeros(len(df), dtype=int)
    strict_streak = np.zeros(len(df), dtype=int)
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
        if strict_sealed_up[i]:
            adjacent_market_session = (
                i > 0
                and calendar_positions[i] >= 0
                and calendar_positions[i - 1] == calendar_positions[i] - 1
            )
            strict_streak[i] = (
                strict_streak[i - 1] if adjacent_market_session else 0
            ) + 1

    volume_z20 = _volume_z20(volume_series.where(volume_series > 0)).to_numpy(dtype=float)
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
        "universe_n": Counter(dates[in_window & calendar_ok & positive_volume]),
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
        next_bar_observed = next_i is not None
        next_available = next_i is not None and bool(positive_volume[next_i])
        if expected_next_date is None:
            next_session_state = "right_censored_calendar_end"
            next_board = None
            next_board_observed = None
        elif next_available:
            next_session_state = "observed_tradable"
            next_board = bool(tolerant_sealed_up[next_i])
            next_board_observed = next_board
        elif next_bar_observed:
            next_session_state = "zero_volume_halt_or_no_trade"
            next_board = False
            next_board_observed = None
        else:
            next_session_state = "no_bar_halt_or_data_missing"
            next_board = False
            next_board_observed = None
        if expected_next_date is None:
            next_strict_board = None
        elif next_available:
            next_strict_board = bool(strict_sealed_up[next_i])
        else:
            next_strict_board = False
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
            "strict_board_count": int(strict_streak[i]) if strict_sealed_up[i] else 0,
            "strict_board_count_bucket": (
                board_count_bucket(strict_streak[i]) if strict_sealed_up[i] else None
            ),
            "next_session_available": bool(next_available),
            "next_session_bar_observed": bool(next_bar_observed),
            "next_session_state": next_session_state,
            "next_session_date": str(expected_next_date.date()) if expected_next_date is not None else None,
            "next_observed_ticker_date_sensitivity": (
                str(dates[i + 1].date()) if i + 1 < len(dates) else None
            ),
            "next_board": next_board,
            "next_strict_board": next_strict_board,
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
                if expected_next_date is not None and not next_bar_observed
                else (
                    "zero_volume_halt_or_no_trade_no_fill"
                    if next_bar_observed and not next_available
                    else (
                        "next_open_price_or_limit_missing_no_fill"
                        if next_available
                        else "next_market_session_not_observed"
                    )
                )
            ),
            "entry_price": None,
            "exits": {},
        }
        record.update({f"geometry_{k}": v for k, v in geometry_buckets(record).items()})

        if next_available and _is_finite_positive(opens[next_i]) and _is_finite_positive(uppers[next_i]):
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
                        volumes=volumes,
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
                    volumes=volumes,
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
        "positive_volume_rows": int(positive_volume.sum()),
        "zero_or_missing_volume_rows": int((~positive_volume).sum()),
        "zero_or_missing_volume_rows_in_measurement_window": int(
            ((~positive_volume) & in_window).sum()
        ),
        "zero_volume_price_eligible_rows_reclassified": int(
            zero_volume_price_eligible.sum()
        ),
        "zero_volume_tolerant_board_price_rows_reclassified": int(
            zero_volume_board_price.sum()
        ),
        "off_calendar_eligible_positive_volume_rows": int(
            off_calendar_eligible.sum()
        ),
        "rows_off_common_calendar": int((~calendar_ok).sum()),
        "rows_off_common_calendar_in_measurement_window": int(
            ((~calendar_ok) & in_window).sum()
        ),
        "exdiv_suspect_rows": int(exdiv_suspect.sum()),
        "raw_first_row_date": str(dates[0].date()),
        "listing_date": str(listing_date.date()) if listing_date is not None else None,
        "listing_date_source": "first_positive_volume_common_market_session_ticker_observation",
        "raw_rows_before_first_positive_volume_session": int(
            first_positive_volume_index or 0
        ),
        "ipo_no_limit_regime": ipo_regime,
        "ipo_no_limit_sessions_applied": int(ipo_no_limit_sessions),
        "ipo_no_limit_rows_quarantined": int((ipo_no_limit & in_window).sum()),
        "ipo_no_limit_positive_volume_dates": [
            str(date.date()) for date in dates[ipo_no_limit]
        ],
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


def _no_duplicate_exit_rows(events: pd.DataFrame, exit_id: str) -> pd.DataFrame:
    """Apply one frozen same-ticker-position state machine for one exit rule."""
    work = events.copy()
    work["entry_date_ts"] = pd.to_datetime(work["next_session_date"], errors="coerce")
    work = work.sort_values(
        ["entry_date_ts", "signal_date", "ticker"], na_position="last", kind="stable"
    )
    active_until: dict[str, pd.Timestamp | None] = {}
    rows: list[dict[str, Any]] = []
    for event in work.to_dict("records"):
        ticker = str(event["ticker"])
        entry_date = pd.to_datetime(event.get("next_session_date"), errors="coerce")
        entry_date = None if pd.isna(entry_date) else pd.Timestamp(entry_date).normalize()
        fill_candidate = event.get("entry_fill_state") == "official_open_candidate_fill"
        right_censored_entry = event.get("entry_fill_state") == "next_market_session_not_observed"
        portfolio_state = "entry_rejected_or_missing_cash_zero"
        gross_book_return: float | None = 0.0
        accepted_fill = False
        overlap_rejected = False
        exit_reason = None
        exit_date: pd.Timestamp | None = None

        if right_censored_entry:
            portfolio_state = "right_censored_entry"
            gross_book_return = None
        elif fill_candidate:
            prior_is_open = ticker in active_until and (
                active_until[ticker] is None
                or entry_date is None
                or entry_date <= active_until[ticker]
            )
            if prior_is_open:
                portfolio_state = "same_ticker_overlap_rejected_cash_zero"
                overlap_rejected = True
            else:
                if ticker in active_until:
                    del active_until[ticker]
                accepted_fill = True
                payload = (event.get("exits") or {}).get(exit_id, {})
                exit_reason = payload.get("exit_reason")
                parsed_exit = pd.to_datetime(payload.get("exit_date"), errors="coerce")
                exit_date = None if pd.isna(parsed_exit) else pd.Timestamp(parsed_exit).normalize()
                gross = _json_number(payload.get("gross_return"))
                if gross is None or exit_date is None:
                    portfolio_state = "accepted_fill_exit_unresolved"
                    gross_book_return = None
                    active_until[ticker] = None
                else:
                    portfolio_state = "accepted_fill_resolved"
                    gross_book_return = float(gross)
                    active_until[ticker] = exit_date

        entry_date_text = str(entry_date.date()) if entry_date is not None else None
        rows.append({
            "ticker": ticker,
            "signal_date": event["signal_date"],
            "entry_date": entry_date_text,
            "date_cluster": entry_date_text,
            "run_cluster": event["run_cluster"],
            "split": event["split"],
            "board_count_bucket": event["board_count_bucket"],
            "entry_fill_state": event["entry_fill_state"],
            "portfolio_state": portfolio_state,
            "accepted_fill": accepted_fill,
            "overlap_rejected": overlap_rejected,
            "gross_book_return": gross_book_return,
            "exit_date": str(exit_date.date()) if exit_date is not None else None,
            "exit_reason": exit_reason,
        })
    return pd.DataFrame(rows)


def _no_duplicate_portfolio_book(events: pd.DataFrame) -> dict[str, Any]:
    """N=1/2 same-ticker sequential-trade/cohort expectancy diagnostic."""
    primary = events[
        events["market_scope"].eq("main_primary")
        & events["board_count_bucket"].isin(["1", "2"])
    ].copy()
    metrics: list[dict[str, Any]] = []
    funnels: list[dict[str, Any]] = []
    for exit_id in EXIT_IDS:
        for split, split_events in primary.groupby("split", sort=True):
            # Each frozen split is an independently initialised evaluation book.
            # Do not let an unresolved training position contaminate calibration.
            group = _no_duplicate_exit_rows(split_events, exit_id)
            states = Counter(group["portfolio_state"].astype(str))
            funnels.append({
                "split": split,
                "exit_id": exit_id,
                "candidate_signals": int(len(group)),
                "official_open_fill_candidates": int(
                    group["entry_fill_state"].eq("official_open_candidate_fill").sum()
                ),
                "accepted_fills": int(group["accepted_fill"].sum()),
                "overlap_rejected_cash_zero": int(group["overlap_rejected"].sum()),
                "portfolio_state_counts": dict(sorted(states.items())),
            })
            for cost_bps in COST_GRID_BPS:
                mature = group["gross_book_return"].notna()
                book = group.loc[mature].copy()
                book["net_book_return"] = pd.to_numeric(
                    book["gross_book_return"], errors="coerce"
                )
                accepted_resolved = book["portfolio_state"].eq("accepted_fill_resolved")
                book.loc[accepted_resolved, "net_book_return"] -= cost_bps / 10_000.0
                row_weighted = metric_summary(book, "net_book_return", binary=False)
                daily = (
                    book.dropna(subset=["entry_date"])
                    .groupby("entry_date", sort=True)["net_book_return"]
                    .mean()
                    .rename("daily_book_return")
                    .reset_index()
                )
                daily["date_cluster"] = daily["entry_date"]
                daily["run_cluster"] = daily["entry_date"]
                date_equal = metric_summary(daily, "daily_book_return", binary=False)
                metrics.append({
                    "split": split,
                    "exit_id": exit_id,
                    "cost_bps": int(cost_bps),
                    "candidate_signals": int(len(group)),
                    "mature_candidate_signals": int(len(book)),
                    "entry_dates": int(daily["entry_date"].nunique()),
                    "accepted_resolved_fills": int(accepted_resolved.sum()),
                    "overlap_rejected_cash_zero": int(
                        group["overlap_rejected"].sum()
                    ),
                    "row_weighted_event_metric": row_weighted,
                    "date_equal_daily_book_metric": date_equal,
                })
    return {
        "construction_id": "C_AUCTION_PRIMARY_N1_N2_NO_DUPLICATE_TICKER_COHORT",
        "population": "main-board N=1/2 only",
        "entry_sequence": "exact common-calendar D+1 entry dates",
        "overlap_rule": (
            "reject a new otherwise-fillable same-ticker entry as cash=0 while a prior position "
            "is open or unresolved; same-date release/entry is conservatively rejected"
        ),
        "portfolio_scope_warning": (
            "SEQUENTIAL_TRADE_COHORT_EXPECTANCY_NOT_IMPLEMENTABLE_PORTFOLIO_RETURN; "
            "cash is not reserved across different tickers in these row/date-equal diagnostics"
        ),
        "metrics": metrics,
        "overlap_rejected_funnel": funnels,
        "UNTESTED VARIANTS": [
            "finite portfolio capital and concurrent cross-ticker position limits",
            "theme/sector caps and auction capacity",
            "same-open sell/buy ordering instead of conservative same-date rejection",
            "partial fills and queue priority",
        ],
    }


def _capital_accounted_split(
    events: pd.DataFrame,
    market_calendar: MarketCalendar,
    *,
    split: str,
    exit_id: str,
    cost_bps: int,
) -> dict[str, Any]:
    split_spec = next(item for item in SPLITS if item[0] == split)
    _, split_start, split_end = split_spec
    sessions = market_calendar.sessions[
        (market_calendar.sessions >= split_start)
        & (market_calendar.sessions <= split_end)
    ]
    subset = events[events["split"].eq(split)].copy()
    subset["entry_date_ts"] = pd.to_datetime(
        subset["next_session_date"], errors="coerce"
    ).dt.normalize()
    mapped_entry = subset["entry_date_ts"].isin(set(sessions))
    by_entry = {
        date: group.sort_values(["ticker", "signal_date"], kind="stable")
        for date, group in subset.loc[mapped_entry].groupby(
            "entry_date_ts", sort=True
        )
    }
    cash = 1.0
    active: dict[str, dict[str, Any]] = {}
    counts = Counter({
        "candidate_signals_unmapped_right_censored_or_off_split": int(
            (~mapped_entry).sum()
        )
    })
    daily_rows: list[dict[str, Any]] = []
    for date in sessions:
        nav_before = cash + sum(float(position["notional"]) for position in active.values())
        day = by_entry.get(date)
        accepted_today: list[dict[str, Any]] = []
        if day is not None:
            counts["candidate_signals"] += int(len(day))
            accepted_tickers_today: set[str] = set()
            for event in day.to_dict("records"):
                if event.get("entry_fill_state") != "official_open_candidate_fill":
                    counts["entry_rejected_or_missing_cash_zero"] += 1
                    continue
                counts["official_open_fill_candidates"] += 1
                ticker = str(event["ticker"])
                if ticker in active or ticker in accepted_tickers_today:
                    counts["same_ticker_overlap_rejected_cash_zero"] += 1
                    continue
                accepted_today.append(event)
                accepted_tickers_today.add(ticker)
        if accepted_today:
            if cash > 0:
                allocation = cash / len(accepted_today)
                cash = 0.0
                for event in accepted_today:
                    ticker = str(event["ticker"])
                    payload = (event.get("exits") or {}).get(exit_id, {})
                    gross = _json_number(payload.get("gross_return"))
                    parsed_exit = pd.to_datetime(payload.get("exit_date"), errors="coerce")
                    exit_date = (
                        None
                        if pd.isna(parsed_exit) or gross is None
                        else pd.Timestamp(parsed_exit).normalize()
                    )
                    active[ticker] = {
                        "notional": float(allocation),
                        "exit_date": exit_date,
                        "net_return": (
                            None
                            if gross is None
                            else float(gross) - cost_bps / 10_000.0
                        ),
                    }
                    counts["accepted_positions"] += 1
                    if exit_date is None:
                        counts["accepted_exit_unresolved"] += 1
            else:
                counts["capital_unavailable_rejected_cash_zero"] += len(
                    accepted_today
                )

        # Conservative phase ordering: same-session exits release proceeds only
        # after that session's opening candidates have been adjudicated.
        realised_pnl = 0.0
        released_notional = 0.0
        for ticker in sorted(list(active)):
            position = active[ticker]
            if position["exit_date"] != date:
                continue
            notional = float(position["notional"])
            net_return = float(position["net_return"])
            realised_pnl += notional * net_return
            released_notional += notional
            cash += notional * (1.0 + net_return)
            counts["resolved_positions"] += 1
            if net_return > 0:
                counts["resolved_success"] += 1
            else:
                counts["resolved_failure_or_flat"] += 1
            del active[ticker]
        nav_after = cash + sum(float(position["notional"]) for position in active.values())
        daily_rows.append({
            "date": str(date.date()),
            "date_cluster": str(date.date()),
            "run_cluster": str(date.date()),
            "daily_realised_return": (
                float(realised_pnl / nav_before) if nav_before > 0 else None
            ),
            "nav_cost_basis": float(nav_after),
            "cash": float(cash),
            "invested_notional": float(nav_after - cash),
            "active_positions": int(len(active)),
            "released_notional": float(released_notional),
        })
    daily = pd.DataFrame(
        daily_rows,
        columns=[
            "date",
            "date_cluster",
            "run_cluster",
            "daily_realised_return",
            "nav_cost_basis",
            "cash",
            "invested_notional",
            "active_positions",
            "released_notional",
        ],
    )
    metric = metric_summary(daily, "daily_realised_return", binary=False)
    if len(daily):
        nav = pd.to_numeric(daily["nav_cost_basis"], errors="coerce")
        peak = nav.cummax()
        drawdown = nav / peak - 1.0
        final_nav = float(nav.iloc[-1])
        annualised = (
            float(final_nav ** (252.0 / len(daily)) - 1.0)
            if final_nav > 0 and len(daily)
            else None
        )
        exposure = daily["invested_notional"] / nav.replace(0, np.nan)
    else:
        final_nav = 1.0
        annualised = None
        drawdown = pd.Series(dtype=float)
        exposure = pd.Series(dtype=float)
    return {
        "split": split,
        "exit_id": exit_id,
        "cost_bps": int(cost_bps),
        "input_candidate_signals": int(len(subset)),
        "initial_nav": 1.0,
        "final_nav_cost_basis": final_nav,
        "cumulative_realised_return": float(final_nav - 1.0),
        "annualised_realised_return": annualised,
        "max_realised_drawdown": (
            float(drawdown.min()) if len(drawdown) else None
        ),
        "mean_invested_fraction": (
            float(exposure.mean()) if len(exposure) else None
        ),
        "max_active_positions": int(daily["active_positions"].max()) if len(daily) else 0,
        "end_active_positions": int(len(active)),
        "end_locked_notional": float(
            sum(float(position["notional"]) for position in active.values())
        ),
        "daily_realised_return_metric": metric,
        "funnel": dict(sorted((str(key), int(value)) for key, value in counts.items())),
    }


def _capital_accounted_portfolio_book(
    events: pd.DataFrame,
    market_calendar: MarketCalendar,
) -> dict[str, Any]:
    primary = events[
        events["market_scope"].eq("main_primary")
        & events["board_count_bucket"].isin(["1", "2"])
    ].copy()
    metrics = [
        _capital_accounted_split(
            primary,
            market_calendar,
            split=split,
            exit_id=exit_id,
            cost_bps=cost_bps,
        )
        for split, _, _ in SPLITS
        for exit_id in EXIT_IDS
        for cost_bps in COST_GRID_BPS
    ]
    return {
        "construction_id": "C_AUCTION_PRIMARY_N1_N2_SELF_FINANCING_PAPER_BOOK",
        "population": "curated main-board N=1/2 only",
        "initial_capital": 1.0,
        "allocation_rule": (
            "within each split, invest all currently available cash equally across that exact entry "
            "date's fillable, non-overlapping tickers; reserve notional until exact exit"
        ),
        "phase_rule": (
            "same-session exits release proceeds after opening-entry adjudication and cannot fund that open"
        ),
        "valuation_rule": (
            "positions remain at entry cost until realised exit because the event receipt does not retain "
            "daily mark-to-market paths"
        ),
        "scope_warning": (
            "self-financing cash-reservation proxy, not a capital/theme/capacity-complete portfolio; "
            "realised-exit NAV understates interim drawdown"
        ),
        "metrics": metrics,
        "UNTESTED VARIANTS": [
            "daily mark-to-market NAV and portfolio-level MFE/MAE",
            "theme/sector exposure caps and cross-name factor dependence",
            "auction capacity, queue priority, and partial fills",
            "alternative frozen sleeve counts or cash-allocation schedules",
        ],
    }


def _locked_replay_stratum_verdicts(
    records: Sequence[Mapping[str, Any]],
    stratum_field: str,
    primary_values: Sequence[str] | None = None,
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
            "population_scope": (
                "primary_n1_n2"
                if primary_values is not None
                and str(record.get(stratum_field)) in set(primary_values)
                else (
                    "exploratory_n3plus"
                    if primary_values is not None
                    else "primary_n1_n2_population"
                )
            ),
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
    primary_values: Sequence[str] | None = None,
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
            records, stratum_field, primary_values
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
            "population_scope": (
                "primary_n1_n2"
                if str(row["board_count_bucket"]) in {"1", "2"}
                else "exploratory_n3plus"
            ),
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
            "population_scope": (
                "primary_n1_n2"
                if str(board_bucket) in {"1", "2"}
                else "exploratory_n3plus"
            ),
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
        exit_unresolved_reasons: dict[str, Counter] = defaultdict(Counter)
        for exits in group.loc[filled, "exits"]:
            for exit_id, payload in (exits or {}).items():
                if payload.get("gross_return") is not None:
                    exit_counts[exit_id] += 1
                else:
                    exit_unresolved_reasons[exit_id][
                        str(payload.get("exit_reason") or "unknown")
                    ] += 1
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
            "zero_volume_halt_or_no_trade": int(
                state_counts.get("zero_volume_halt_or_no_trade", 0)
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
            "exit_unresolved_reasons": {
                exit_id: dict(sorted(counts.items()))
                for exit_id, counts in sorted(exit_unresolved_reasons.items())
            },
            "locked_down_deferrals": dict(sorted(locked_deferrals.items())),
        })
    return result


def _construction_results(
    events: pd.DataFrame,
    market_calendar: MarketCalendar,
) -> dict[str, Any]:
    main_events = events[events["market_scope"].eq("main_primary")].copy()
    main_primary_events = main_events[
        main_events["board_count_bucket"].isin(["1", "2"])
    ].copy()
    main_exploratory_events = main_events[
        ~main_events["board_count_bucket"].isin(["1", "2"])
    ].copy()
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
            events[events["next_session_state"].eq("observed_tradable")],
            ["market_scope", "board_era", "split", "board_count_bucket"],
            "next_board_observed_bar_sensitivity",
            binary=True,
        ),
        "strict_sealed_close_sensitivity": _group_records(
            events[events["strict_sealed_up"]],
            ["market_scope", "board_era", "split", "strict_board_count_bucket"],
            "next_strict_board",
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
        "packet_b_population_scope": {
            "primary": "main-board N=1/2",
            "exploratory": "main-board N>=3",
            "secondary": "ChiNext eras",
            "descriptive": "STAR",
        },
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
    primary_joint_book = _joint_candidate_book_metrics(
        main_primary_events, ["split"]
    )
    exploratory_joint_book = _joint_candidate_book_metrics(
        main_exploratory_events, ["split"]
    )
    strict_joint_book = _joint_candidate_book_metrics(
        events[events["strict_sealed_up"]], ["market_scope", "split"]
    )

    geometry_rows: list[dict[str, Any]] = []
    for feature in (
        "geometry_one_price_board",
        "geometry_board_day_gap_norm",
        "geometry_intraday_range_norm",
        "geometry_close_location",
        "geometry_volume_z20",
    ):
        subset = auction[
            auction["market_scope"].eq("main_primary")
            & auction["board_count_bucket"].isin(["1", "2"])
        ]
        for record in _group_records(subset, ["split", feature], "next_board", binary=True):
            record["geometry_feature"] = feature.removeprefix("geometry_")
            record["bucket"] = record.pop(feature)
            geometry_rows.append(record)

    ecology_rows = _group_records(
        auction[
            auction["market_scope"].eq("main_primary")
            & auction["board_count_bucket"].isin(["1", "2"])
        ],
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
            "primary_n1_n2_fill_funnel": _fill_funnel(main_primary_events),
            "all_board_counts_reference_fill_funnel": _fill_funnel(events),
            "continuation_probability_after_fill_screen": auction_probability,
            "event_level_expectancy_label": (
                "EVENT_LEVEL_CANDIDATE_ROW_EXPECTANCY_NOT_A_PORTFOLIO_RETURN"
            ),
            "joint_candidate_book_definition": (
                "Every mature signal is in the denominator; queue/missing/rejected entries hold cash=0. "
                "Reported identity is P(fill) * E(net return | resolved fill)."
            ),
            "event_level_all_board_counts_reference_metrics": joint_book,
            "event_level_all_board_counts_reference_status": (
                "RETAINED_REFERENCE_NOT_PACKET_B_PRIMARY_NOT_A_PORTFOLIO_RETURN"
            ),
            "primary_n1_n2_event_level_metrics": primary_joint_book,
            "exploratory_n3plus_event_level_metrics": exploratory_joint_book,
            "exploratory_n3plus_status": "EXPLORATORY_NO_PRIMARY_CONSTRUCTION_VERDICT",
            "strict_sealed_close_event_level_sensitivity": strict_joint_book,
            "filled_conditional_return_metrics": return_metrics,
            "filled_conditional_status": "distribution_of_resolved_fills_not_strategy_expectancy",
            "cost_grid_bps_round_trip": list(COST_GRID_BPS),
        },
        "C_AUCTION_PRIMARY_N1_N2_PORTFOLIO": {
            "sequential_trade_cohort_expectancy": _no_duplicate_portfolio_book(
                events
            ),
            "self_financing_paper_book": _capital_accounted_portfolio_book(
                events, market_calendar
            ),
        },
        "C_AUCTION_N": _fixed_all_signal_book(
            main_events,
            construction_id="C_AUCTION_N",
            stratum_field="board_count_bucket",
            definition="Main-board C-AUCTION ladder; N=1/2 primary and N>=3 explicitly exploratory",
            primary_values=["1", "2"],
        ),
        "C_AUCTION_ONE_PRICE_D_CLOSE": _fixed_all_signal_book(
            main_primary_events,
            construction_id="C_AUCTION_ONE_PRICE_D_CLOSE",
            stratum_field="geometry_one_price_board",
            definition="Main-board C-AUCTION book split by D-close-known one-price-board yes/no",
        ),
        "C_AUCTION_INTRADAY_RANGE_D_CLOSE": _fixed_all_signal_book(
            main_primary_events,
            construction_id="C_AUCTION_INTRADAY_RANGE_D_CLOSE",
            stratum_field="geometry_intraday_range_norm",
            definition="Main-board C-AUCTION book split by fixed D-close-known band-normalised intraday-range bucket",
        ),
        "C_AUCTION_ECOLOGY_D_CLOSE": _fixed_all_signal_book(
            main_primary_events,
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
    primary_cells = [
        row for row in cells if row.get("population_scope") != "exploratory_n3plus"
    ]
    exploratory_cells = [
        row for row in cells if row.get("population_scope") == "exploratory_n3plus"
    ]
    statuses = Counter(row["verdict"] for row in primary_cells)
    exploratory_statuses = Counter(row["verdict"] for row in exploratory_cells)
    if (
        primary_cells
        and statuses["NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL"]
        == len(primary_cells)
    ):
        verdict = "NEGATIVE_ALL_PRIMARY_ENDPOINT_STRATA_SPECIFIC_ONLY"
    elif statuses["POSITIVE_DATE_CLUSTER_CI_UNADJUSTED_DESCRIPTIVE"]:
        verdict = "MIXED_WITH_POSITIVE_UNADJUSTED_CELLS_NO_PROMOTION"
    else:
        verdict = "MIXED_OR_INCONCLUSIVE_PRIMARY_ENDPOINT_STRATA_NO_GLOBAL_KILL"
    negative_cells = [
        str(row["stratum"])
        for row in primary_cells
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
        "exploratory_cell_verdict_counts": dict(
            sorted(exploratory_statuses.items())
        ),
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
            for row in results["C_AUCTION"]["primary_n1_n2_event_level_metrics"]
            if row.get("split") == "historical_replay_after_common_prior"
            and row.get("exit_id") == "seal_state_next_open"
            and row.get("cost_bps") == 60
        ),
        None,
    )
    auction_metric = auction_row.get("joint_cash_book_metric") if auction_row else None

    auction_status = "INCONCLUSIVE_EVENT_LEVEL_N1_N2_EXPECTANCY_SPECIFIC_ONLY"
    kill_scope = None
    if auction_metric and auction_metric.get("mean") is not None:
        date_ci = (auction_metric.get("date_cluster") or {}).get("ci95") or [None, None]
        if date_ci[0] is not None and date_ci[0] > 0:
            auction_status = "POSITIVE_EVENT_LEVEL_N1_N2_EXPECTANCY_NO_PROMOTION"
        elif date_ci[1] is not None and date_ci[1] < 0:
            auction_status = "NEGATIVE_EVENT_LEVEL_N1_N2_EXPECTANCY_SPECIFIC_ONLY"
            kill_scope = (
                "Only the N=1/2 main-board event-level candidate-row expectancy with nonfills cash=0, "
                "seal-state-next-open exit at 60bp in historical replay is negative; it is not a "
                "portfolio-return verdict."
            )

    capital_row = next(
        (
            row
            for row in results["C_AUCTION_PRIMARY_N1_N2_PORTFOLIO"][
                "self_financing_paper_book"
            ]["metrics"]
            if row.get("split") == "historical_replay_after_common_prior"
            and row.get("exit_id") == "seal_state_next_open"
            and row.get("cost_bps") == 60
        ),
        None,
    )
    capital_metric = (
        capital_row.get("daily_realised_return_metric") if capital_row else None
    )
    capital_status = "INCONCLUSIVE_SELF_FINANCING_PROXY_NO_PROMOTION"
    capital_kill = "none"
    if capital_metric and capital_metric.get("mean") is not None:
        date_ci = (capital_metric.get("date_cluster") or {}).get("ci95") or [None, None]
        if date_ci[0] is not None and date_ci[0] > 0:
            capital_status = "POSITIVE_SELF_FINANCING_PROXY_NO_PROMOTION"
        elif date_ci[1] is not None and date_ci[1] < 0:
            capital_status = "NEGATIVE_SELF_FINANCING_PROXY_SPECIFIC_ONLY"
            capital_kill = (
                "Only the frozen N=1/2 main-board equal-available-cash, no-duplicate-ticker, "
                "realised-exit-cost-basis paper book with seal-state exit at 60bp in historical replay."
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
                    "N=1/2 primary event-level candidate-row expectancy after a D-close decision, "
                    "plus separately labelled all-N reference and N>=3 exploratory books"
                ),
                "not_measured": "realised gap as a selection feature",
                "UNTESTED VARIANTS": common_not_tested,
            },
        },
        {
            "construction_id": "C_AUCTION_PRIMARY_N1_N2_PORTFOLIO",
            "verdict": capital_status,
            "headline_metric": capital_metric,
            "headline_context": capital_row,
            "kill_status": capital_kill,
            "ore_ledger": {
                "measured": (
                    "self-financing equal-available-cash paper book with same-ticker dedupe, exact "
                    "cash reservation, all five exits, four costs, and daily realised-exit metrics"
                ),
                "not_measured": (
                    "daily mark-to-market NAV, theme/sector constraints, auction capacity, or partial fills"
                ),
                "UNTESTED VARIANTS": common_not_tested
                + list(
                    results["C_AUCTION_PRIMARY_N1_N2_PORTFOLIO"][
                        "self_financing_paper_book"
                    ]["UNTESTED VARIANTS"]
                ),
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
    return verdicts[:3] + stratified + verdicts[3:]


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _raw_content_sha256(files: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def _definition_config_payload() -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "start_date": str(START_DATE.date()),
        "end_date": str(END_DATE.date()),
        "chinext_wide_date": str(CHINEXT_WIDE_DATE.date()),
        "st_rule_change_date": str(ST_RULE_CHANGE_DATE.date()),
        "main_registration_ipo_first5_date": str(
            MAIN_REGISTRATION_IPO_FIRST5_DATE.date()
        ),
        "chinext_registration_ipo_first5_date": str(
            CHINEXT_REGISTRATION_IPO_FIRST5_DATE.date()
        ),
        "star_first_listing_date": str(STAR_FIRST_LISTING_DATE.date()),
        "ipo_listing_clock": "positive_volume_common_market_session_ordinal",
        "vendor_ticker_identity": "uppercase_and_SH_suffix_canonicalized_to_SS",
        "ipo_rule_evidence": IPO_RULE_EVIDENCE,
        "minimum_prior_sessions": MIN_PRIOR_SESSIONS,
        "limit_tolerance": LIMIT_TOLERANCE,
        "boundary_purge_sessions": BOUNDARY_PURGE_SESSIONS,
        "cost_grid_bps": list(COST_GRID_BPS),
        "exit_ids": list(EXIT_IDS),
        "splits": [
            [name, str(start.date()), str(end.date())] for name, start, end in SPLITS
        ],
        "expected_calendar_sessions": EXPECTED_CALENDAR_SESSIONS,
        "raw_date_support_consensus_min_names": RAW_DATE_SUPPORT_CONSENSUS_MIN_NAMES,
        "c_auction_selection_fields": list(C_AUCTION_SELECTION_FIELDS),
        "untested_variants": list(UNTESTED_VARIANTS),
    }


def _input_fingerprint(
    files: Sequence[Path],
    *,
    calendar_path: Path,
    st_path: Path,
    zt_path: Path,
) -> dict[str, Any]:
    """Content-address every input plus executable definition/config state."""
    config_bytes = json.dumps(
        _definition_config_payload(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    components = {
        "raw_ohlcv_content_sha256": _raw_content_sha256(files),
        "calendar_content_sha256": _file_sha256(calendar_path),
        "st_snapshot_content_sha256": _file_sha256(st_path),
        "zt_pool_content_sha256": _file_sha256(zt_path),
        "runner_content_sha256": _file_sha256(Path(__file__).resolve()),
        "definition_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
    }
    combined = hashlib.sha256(
        json.dumps(components, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "algorithm": "sha256_content_addressed_v2",
        "combined_sha256": combined,
        "components": components,
        "zt_pool_snapshot_disclosure": (
            "The hash covers the exact worktree file consumed; clone sessions remain present in this snapshot "
            "but are excluded by observed-calendar identity. No claim is made that a separate repaired "
            "data commit is integrated."
        ),
    }


def _accumulate_raw_support(
    frame: pd.DataFrame,
    date_support: Counter,
    positive_volume_support: Counter,
) -> dict[str, int]:
    dates = pd.DatetimeIndex(pd.to_datetime(frame.index, errors="coerce")).normalize()
    valid_index = ~dates.isna()
    dates = dates[valid_index]
    if len(dates):
        dates = dates.drop_duplicates()
    volume = pd.to_numeric(frame.get("volume", pd.Series(index=frame.index, dtype=float)), errors="coerce")
    volume_values = volume.to_numpy(dtype=float)[valid_index]
    if len(volume_values) != len(dates):
        # Duplicate indices are rare; align to the same keep-last contract as extraction.
        work = pd.DataFrame({"volume": volume_values}, index=pd.DatetimeIndex(pd.to_datetime(frame.index, errors="coerce"))[valid_index].normalize())
        work = work[~work.index.duplicated(keep="last")]
        dates = pd.DatetimeIndex(work.index)
        volume_values = work["volume"].to_numpy(dtype=float)
    positive = np.isfinite(volume_values) & (volume_values > 0)
    date_support.update(dates)
    positive_volume_support.update(dates[positive])
    in_window = (dates >= START_DATE) & (dates <= END_DATE)
    return {
        "rows": int(len(dates)),
        "zero_or_missing_volume_rows": int((~positive).sum()),
        "zero_or_missing_volume_rows_in_measurement_window": int(
            ((~positive) & in_window).sum()
        ),
    }


def _calendar_completeness_audit(
    market_calendar: MarketCalendar,
    date_support: Mapping[pd.Timestamp, int],
    positive_volume_support: Mapping[pd.Timestamp, int],
    *,
    enforce_full_contract: bool,
) -> dict[str, Any]:
    calendar = market_calendar.sessions[
        (market_calendar.sessions >= START_DATE) & (market_calendar.sessions <= END_DATE)
    ]
    calendar_set = set(calendar)
    consensus = {
        date
        for date, count in date_support.items()
        if START_DATE <= date <= END_DATE
        and int(count) >= RAW_DATE_SUPPORT_CONSENSUS_MIN_NAMES
    }
    missing = sorted(consensus - calendar_set)
    extra = sorted(calendar_set - consensus)
    dec24 = pd.Timestamp("2014-12-24")
    dec25 = pd.Timestamp("2014-12-25")
    dec25_is_successor = market_calendar.successor.get(dec24) == dec25
    if enforce_full_contract:
        if len(calendar) != EXPECTED_CALENDAR_SESSIONS:
            raise AssertionError(
                f"calendar has {len(calendar)} sessions, expected {EXPECTED_CALENDAR_SESSIONS}"
            )
        if missing or extra:
            raise AssertionError(
                f"calendar/raw >=50-name consensus mismatch: missing={missing}, extra={extra}"
            )
        if not dec25_is_successor:
            raise AssertionError("2014-12-24 calendar successor must be 2014-12-25")
    return {
        "status": "asserted_set_identical" if enforce_full_contract else "partial_debug_not_asserted",
        "support_threshold_names": RAW_DATE_SUPPORT_CONSENSUS_MIN_NAMES,
        "calendar_sessions": int(len(calendar)),
        "consensus_sessions": int(len(consensus)),
        "missing_consensus_dates": [str(date.date()) for date in missing],
        "extra_calendar_dates": [str(date.date()) for date in extra],
        "dec_24_2014_successor": (
            str(market_calendar.successor.get(dec24).date())
            if market_calendar.successor.get(dec24) is not None
            else None
        ),
        "dec_25_2014_raw_name_support": int(date_support.get(dec25, 0)),
        "dec_25_2014_positive_volume_name_support": int(
            positive_volume_support.get(dec25, 0)
        ),
        "set_identical": not missing and not extra,
    }


def _calendar_anchor_volume_inventory(path: Path) -> dict[str, Any]:
    frame = pd.read_parquet(path)
    if "volume" not in frame.columns:
        return {"status": "volume_column_unavailable"}
    dates = pd.DatetimeIndex(pd.to_datetime(frame.index, errors="coerce")).normalize()
    volumes = pd.to_numeric(frame["volume"], errors="coerce").to_numpy(dtype=float)
    valid = ~dates.isna()
    in_window = valid & (dates >= START_DATE) & (dates <= END_DATE)
    positive = np.isfinite(volumes) & (volumes > 0)
    nonpositive_dates = dates[in_window & ~positive]
    return {
        "status": "index_only_clock_volume_not_used_for_calendar",
        "positive_volume_sessions_in_window": int((in_window & positive).sum()),
        "nonpositive_volume_sessions_in_window": int((in_window & ~positive).sum()),
        "nonpositive_volume_session_dates": [
            str(date.date()) for date in nonpositive_dates
        ],
    }


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


def _zt_inventory(
    path: Path,
    raw_tickers: set[str],
    market_calendar: MarketCalendar,
) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    frame = pd.read_parquet(path, columns=["ticker", "date"])
    frame = frame.copy()
    frame["ticker_raw"] = frame["ticker"].where(frame["ticker"].notna()).astype("string").str.strip().str.upper()
    frame["ticker_canonical"] = frame["ticker_raw"].map(
        lambda value: canonical_ticker(value) if pd.notna(value) else None
    )
    frame["date_ts"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    literal_tickers = set(frame["ticker_raw"].dropna().astype(str))
    tickers = set(frame["ticker_canonical"].dropna().astype(str))
    canonical_raw_tickers = {canonical_ticker(value) for value in raw_tickers}
    literal_overlap = literal_tickers & raw_tickers
    overlap = tickers & canonical_raw_tickers
    dates = frame["date_ts"].dropna()
    valid = frame[frame["date_ts"].isin(set(market_calendar.sessions))]
    valid_raw_overlap = valid["ticker_canonical"].isin(canonical_raw_tickers)
    alias_rows = frame["ticker_raw"].str.endswith(".SH", na=False)
    duplicate_canonical_keys = int(
        frame.duplicated(["ticker_canonical", "date_ts"], keep=False).sum()
    )
    return {
        "status": "canonical_identity_inventory_with_valid_session_descriptive_join",
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "rows": int(len(frame)),
        "literal_unique_tickers": int(len(literal_tickers)),
        "unique_tickers": int(len(tickers)),
        "ticker_alias_rule": "uppercase; .SH is canonicalized to repo-native .SS",
        "sh_alias_rows_normalized": int(alias_rows.sum()),
        "sh_alias_unique_tickers_normalized": int(
            frame.loc[alias_rows, "ticker_raw"].nunique()
        ),
        "literal_to_canonical_unique_name_reduction": int(
            len(literal_tickers) - len(tickers)
        ),
        "canonical_duplicate_ticker_date_rows": duplicate_canonical_keys,
        "literal_raw_overlap_tickers": int(len(literal_overlap)),
        "raw_overlap_tickers": int(len(overlap)),
        "raw_overlap_pct": float(len(overlap) / len(tickers) * 100.0) if tickers else None,
        "vendor_tickers_without_raw_ohlcv": int(len(tickers - canonical_raw_tickers)),
        "valid_observed_session_rows": int(len(valid)),
        "valid_observed_rows_with_raw_ohlcv": int(valid_raw_overlap.sum()),
        "valid_observed_rows_with_raw_ohlcv_pct": (
            float(valid_raw_overlap.mean() * 100.0) if len(valid) else None
        ),
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
    frame["ticker_vendor_raw"] = frame["ticker"].where(frame["ticker"].notna()).astype("string").str.strip().str.upper()
    frame["ticker"] = frame["ticker_vendor_raw"].map(
        lambda value: canonical_ticker(value) if pd.notna(value) else None
    )
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
    canonical_duplicate_rows = int(
        valid.duplicated(["ticker", "signal_date"], keep=False).sum()
    )
    if canonical_duplicate_rows:
        raise AssertionError(
            f"vendor canonical identity produced {canonical_duplicate_rows} duplicate ticker/date rows"
        )
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
    ].copy()
    event_fields["ticker"] = event_fields["ticker"].map(canonical_ticker)
    joined = event_fields.merge(valid, on=["ticker", "signal_date"], how="inner", validate="one_to_one")
    literal_valid = valid.copy()
    literal_valid["ticker"] = literal_valid["ticker_vendor_raw"].astype(str)
    literal_joined = events[
        ["ticker", "signal_date"]
    ].merge(
        literal_valid[["ticker", "signal_date"]],
        on=["ticker", "signal_date"],
        how="inner",
        validate="one_to_one",
    )

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
        "ticker_alias_rule": "uppercase; .SH is canonicalized to repo-native .SS before join",
        "sh_alias_rows_normalized": int(
            valid["ticker_vendor_raw"].str.endswith(".SH", na=False).sum()
        ),
        "canonical_duplicate_ticker_date_rows": canonical_duplicate_rows,
        "literal_joined_curated_event_rows_sensitivity": int(len(literal_joined)),
        "joined_curated_event_rows": int(len(joined)),
        "alias_recovered_join_rows": int(len(joined) - len(literal_joined)),
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
    raw_rows_scanned_for_support = 0
    raw_zero_or_missing_volume_rows = 0
    raw_zero_or_missing_volume_rows_in_window = 0
    raw_date_support: Counter = Counter()
    raw_positive_volume_date_support: Counter = Counter()

    for ordinal, path in enumerate(files, 1):
        ticker = path.stem
        board = board_from_ticker(ticker)
        board_files[board] += 1
        try:
            frame = pd.read_parquet(path)
            support_stats = _accumulate_raw_support(
                frame, raw_date_support, raw_positive_volume_date_support
            )
            raw_rows_scanned_for_support += support_stats["rows"]
            raw_zero_or_missing_volume_rows += support_stats[
                "zero_or_missing_volume_rows"
            ]
            raw_zero_or_missing_volume_rows_in_window += support_stats[
                "zero_or_missing_volume_rows_in_measurement_window"
            ]
            if ticker in excluded_current_st:
                diagnostics.append({
                    "ticker": ticker,
                    "status": "excluded_current_st",
                    "rows": int(support_stats["rows"]),
                })
                continue
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

    enforce_full_calendar = (
        max_files is None and raw_dir.resolve() == DEFAULT_RAW_DIR.resolve()
    )
    calendar_consensus = _calendar_completeness_audit(
        market_calendar,
        raw_date_support,
        raw_positive_volume_date_support,
        enforce_full_contract=enforce_full_calendar,
    )
    off_calendar_eligible = sum(
        int(d.get("off_calendar_eligible_positive_volume_rows") or 0)
        for d in diagnostics
    )
    if off_calendar_eligible:
        raise AssertionError(
            f"{off_calendar_eligible} positive-volume otherwise-eligible rows fall outside the common calendar"
        )

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

    results = _construction_results(events, market_calendar)
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
    zero_volume_price_eligible = sum(
        int(d.get("zero_volume_price_eligible_rows_reclassified") or 0)
        for d in diagnostics
    )
    zero_volume_board_price = sum(
        int(d.get("zero_volume_tolerant_board_price_rows_reclassified") or 0)
        for d in diagnostics
    )
    registration_era_main_diags = [
        d
        for d in diagnostics
        if d.get("status") == "ok"
        and d.get("ipo_no_limit_regime") == "main_registration_first_five"
    ]
    ipo_regime_files = Counter(
        str(d.get("ipo_no_limit_regime"))
        for d in diagnostics
        if d.get("status") == "ok" and d.get("ipo_no_limit_regime")
    )
    ipo_regime_quarantined_rows = Counter()
    for diag in diagnostics:
        if diag.get("status") == "ok" and diag.get("ipo_no_limit_regime"):
            ipo_regime_quarantined_rows[str(diag["ipo_no_limit_regime"])] += int(
                diag.get("ipo_no_limit_rows_quarantined") or 0
            )
    exit_unresolved_reason_counts: dict[str, Counter] = defaultdict(Counter)
    for exits in events.loc[
        events["entry_fill_state"].eq("official_open_candidate_fill"), "exits"
    ]:
        for exit_id, payload in (exits or {}).items():
            if payload.get("gross_return") is None:
                exit_unresolved_reason_counts[exit_id][
                    str(payload.get("exit_reason") or "unknown")
                ] += 1
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
                "data/china_stocks_raw/600519.SS.parquet index only, set-identical to the >=50-name "
                "raw-index consensus over 2011+ (3,786 sessions); the C0 target is the calendar successor"
            ),
            "volume_contract": (
                "positive finite per-ticker volume is mandatory for board signals, observed/tradable "
                "next-session state, fills, fixed exits, seal-state checks, and every lower-limit carry step"
            ),
            "missing_next_session_state": (
                "no_bar_halt_or_data_missing is retained in the primary denominator as no continuation; "
                "observed-bar-only is a named sensitivity and entry is no-fill"
            ),
            "ladder_adjacency": (
                "primary 连板 increments only across adjacent common CN market sessions and resets after a missing/halted bar"
            ),
            "exdiv_suppression": "abs(open/prev_close-1) > 1.5*board_width",
            "ipo_no_limit_window": {
                "clock": (
                    "positive-volume ticker observations on exact common CN market sessions; "
                    "zero-volume issue-price/raw placeholder rows do not start or advance the ordinal"
                ),
                "filter_context": "start/end filtering occurs after the full-frame listing ordinal is computed",
                "main_before_2023_04_10": "positive-volume listing session only",
                "main_on_or_after_2023_04_10": "first five positive-volume traded sessions",
                "chinext_before_2020_08_24": "positive-volume listing session only under the 10 percent era",
                "chinext_on_or_after_2020_08_24": "first five positive-volume traded sessions",
                "star_from_2019_07_22_inception": "first five positive-volume traded sessions",
                "boundary_evidence": IPO_RULE_EVIDENCE,
            },
            "ipo_listing_date_truth": (
                "inferred from the first positive-volume exact-market-session raw observation; "
                "this is not a claim of complete official listing-master coverage"
            ),
            "vendor_ticker_identity": "uppercase; .SH aliases canonicalized to repo-native .SS before coverage and join",
            "primary_universe": "curated main-board non-current-ST-intersection names",
            "secondary_universe": "ChiNext 10% and 20% eras reported separately",
            "descriptive_universe": "STAR",
            "untested_universe": "BSE and ST/risk-warning",
            "st_rule_truth": "main-board ST 5% before 2026-07-06, 10% on/after; not applied without PIT membership",
            "entry_clock": "C-AUCTION decision after D close, candidate fill at D+1 official open",
            "fill_rule": "open within tolerant cushion of D+1 upper limit is an unfilled queue",
            "event_level_candidate_book_expectancy": (
                "EVENT_LEVEL_CANDIDATE_ROW_EXPECTANCY_NOT_A_PORTFOLIO_RETURN; all mature signals "
                "are in the denominator, queue/rejected/missing entries are cash=0, and "
                "P(fill)*E(net|fill) is stated explicitly"
            ),
            "portfolio_proxy": (
                "N=1/2 main only; exact-date same-ticker dedupe plus a separately frozen self-financing "
                "equal-available-cash book that reserves capital until exact exits"
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
            "raw_files_scanned_for_calendar_and_volume_support": int(
                len(files) - len(errors)
            ),
            "raw_files_read": int(sum(d.get("status") == "ok" for d in diagnostics)),
            "raw_files_error": int(len(errors)),
            "raw_files_excluded_current_st": int(len(excluded_current_st)),
            "raw_files_by_board": dict(sorted(board_files.items())),
            "raw_rows_read": int(total_rows),
            "raw_rows_scanned_for_calendar_and_volume_support": int(
                raw_rows_scanned_for_support
            ),
            "raw_zero_or_missing_volume_rows": int(raw_zero_or_missing_volume_rows),
            "raw_zero_or_missing_volume_rows_in_measurement_window": int(
                raw_zero_or_missing_volume_rows_in_window
            ),
            "zero_volume_price_eligible_rows_reclassified": int(
                zero_volume_price_eligible
            ),
            "zero_volume_tolerant_board_price_rows_reclassified": int(
                zero_volume_board_price
            ),
            "off_calendar_eligible_positive_volume_rows": int(off_calendar_eligible),
            "registration_era_main_files_first5_quarantine": int(
                len(registration_era_main_diags)
            ),
            "registration_era_main_no_limit_rows_quarantined": int(
                sum(
                    int(d.get("ipo_no_limit_rows_quarantined") or 0)
                    for d in registration_era_main_diags
                )
            ),
            "ipo_no_limit_clock": {
                "ordinal": "positive-volume observations on the exact common CN market-session clock",
                "raw_issue_price_and_zero_volume_rows_advance_clock": False,
                "start_end_filter_applied_after_listing_context": True,
                "files_by_regime": dict(sorted(ipo_regime_files.items())),
                "quarantined_positive_volume_rows_by_regime": dict(
                    sorted(ipo_regime_quarantined_rows.items())
                ),
                "raw_rows_before_first_positive_volume_session": int(
                    sum(
                        int(d.get("raw_rows_before_first_positive_volume_session") or 0)
                        for d in diagnostics
                    )
                ),
            },
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
                "source": "600519.SS raw index only; per-ticker volume gates remain independent",
                "sessions_total": int(len(market_calendar.sessions)),
                "sessions_in_measurement_window": int(len(calendar)),
                "first_session": str(market_calendar.sessions.min().date()),
                "last_session": str(market_calendar.sessions.max().date()),
                "anchor_volume_inventory": _calendar_anchor_volume_inventory(
                    calendar_path
                ),
                "raw_support_consensus": calendar_consensus,
            },
            "input_provenance": _input_fingerprint(
                files,
                calendar_path=calendar_path,
                st_path=st_path,
                zt_path=zt_path,
            ),
            "read_errors": errors,
            "st_snapshot": st_inventory,
            "zt_pool": _zt_inventory(zt_path, raw_tickers, market_calendar),
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
            "strict_sealed_close_sensitivity_signals": int(
                events["strict_sealed_up"].sum()
            ),
            "exit_unresolved_reason_counts": {
                exit_id: dict(sorted(counts.items()))
                for exit_id, counts in sorted(exit_unresolved_reason_counts.items())
            },
        },
        "results": results,
        "construction_verdicts": _verdicts(results),
        "ore_coverage_ledger": {
            "five_axis_continuation_strata": {
                "status": "UNTESTED_NOT_SILENTLY_KILLED",
                "axes": [
                    "vol_z20",
                    "runup_5",
                    "gap_pct",
                    "dist_52w_low",
                    "consec_up_days",
                ],
            },
            "strict_board_sensitivity": {
                "status": "MEASURED_SEALED_CLOSE_SENSITIVITY",
                "probability_path": "results.C0_TRUE_NEXT_SESSION.strict_sealed_close_sensitivity",
                "event_book_path": "results.C_AUCTION.strict_sealed_close_event_level_sensitivity",
            },
            "ecology_extensions": {
                "status": "UNTESTED_NOT_SILENTLY_KILLED",
                "variants": [
                    "active_ceiling",
                    "three_session_acceleration",
                    "leader_failure_shock",
                ],
            },
            "n3plus": {
                "status": "EXPLORATORY_ONLY_NO_PRIMARY_VERDICT",
                "path": "results.C_AUCTION.exploratory_n3plus_event_level_metrics",
            },
            "portfolio_remaining_constraints": {
                "status": "UNTESTED_BEYOND_FROZEN_CASH_RESERVATION_PROXY",
                "variants": [
                    "daily_mark_to_market",
                    "theme_sector_caps",
                    "auction_capacity",
                    "partial_fills_and_queue_priority",
                ],
            },
        },
        "limitations": [
            "historical replay after a common prior is not a virgin holdout",
            "vendor fields are descriptive only on valid observed sessions; clone dates are excluded and missing sessions are not imputed",
            "nominal yfinance-like bars require a tolerance and corporate-action heuristic",
            "daily bars identify official opens but not queue priority, partial fills, or a 09:30 execution",
            "current ST membership is not historical membership; the family remains untested",
            "IPO listing dates are inferred from first positive-volume common-session raw observations, not a complete official listing master",
            "vendor identity normalization covers the explicit .SH/.SS alias only, not a complete security master",
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
    calendar_inventory = inventory["common_cn_session_calendar"]
    calendar_consensus = calendar_inventory["raw_support_consensus"]
    anchor_volume = calendar_inventory["anchor_volume_inventory"]
    provenance = inventory["input_provenance"]
    zero_volume_exit_reasons = {
        exit_id: int(reasons.get("zero_volume_halt_or_no_trade", 0))
        for exit_id, reasons in event_inventory["exit_unresolved_reason_counts"].items()
    }
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
        "- Positive finite ticker volume is mandatory for signal, next-session tradability, fill, every fixed "
        "exit, every seal-state check, and every lower-limit carry step. Zero volume is halt/no-trade, never fill.",
        "- The IPO clock counts positive-volume observations on exact market sessions, not raw rows. Main listings "
        "from 2023-04-10, ChiNext listings from 2020-08-24, and STAR from inception quarantine five traded sessions; "
        "earlier main/ChiNext listings quarantine listing day only. Start/end filtering retains full listing context.",
        "- Vendor identity is canonicalized before coverage and joining: uppercase `.SH` aliases map to the repo's `.SS` suffix.",
        "- Main board is primary; ChiNext band eras are separate secondary cohorts; STAR is descriptive; "
        "BSE/ST are untested.",
        "",
        "## Data and event inventory",
        "",
        f"- Raw files: {inventory['raw_files_scanned_for_calendar_and_volume_support']:,} scanned for clock/volume support; "
        f"{inventory['raw_files_read']:,} measured; {inventory['raw_files_error']} errors; "
        f"{inventory['raw_files_excluded_current_st']} current-ST intersections excluded from measurement.",
        f"- Measured raw rows: {inventory['raw_rows_read']:,}; all-file support rows: "
        f"{inventory['raw_rows_scanned_for_calendar_and_volume_support']:,}; sessions "
        f"{inventory['raw_first_session']} to {inventory['raw_last_session']}.",
        f"- Common clock: {calendar_consensus['calendar_sessions']:,} sessions; >=50-name raw consensus "
        f"{calendar_consensus['consensus_sessions']:,}; set-identical={calendar_consensus['set_identical']}; "
        f"2014-12-24 successor={calendar_consensus['dec_24_2014_successor']}.",
        f"- 2014-12-25 raw support: {calendar_consensus['dec_25_2014_raw_name_support']:,} names, "
        f"{calendar_consensus['dec_25_2014_positive_volume_name_support']:,} with positive volume. The clock anchor "
        f"has {anchor_volume.get('positive_volume_sessions_in_window', 0):,} positive-volume sessions and "
        f"{anchor_volume.get('nonpositive_volume_sessions_in_window', 0):,} nonpositive placeholders; its index, not volume, defines the clock.",
        f"- Zero/missing-volume census: {inventory['raw_zero_or_missing_volume_rows']:,} raw rows total, "
        f"{inventory['raw_zero_or_missing_volume_rows_in_measurement_window']:,} in-window; "
        f"{inventory['zero_volume_price_eligible_rows_reclassified']:,} otherwise price-eligible rows and "
        f"{inventory['zero_volume_tolerant_board_price_rows_reclassified']:,} tolerant board-price rows were reclassified.",
        f"- Zero-volume downstream states: {event_inventory['next_session_state_counts'].get('zero_volume_halt_or_no_trade', 0):,} "
        f"next sessions; exact-exit unresolved counts {json.dumps(zero_volume_exit_reasons, sort_keys=True)}. "
        f"Off-calendar positive-volume otherwise-eligible rows: {inventory['off_calendar_eligible_positive_volume_rows']:,}.",
        f"- Registration-era main IPO quarantine: {inventory['registration_era_main_files_first5_quarantine']:,} files and "
        f"{inventory['registration_era_main_no_limit_rows_quarantined']:,} in-window positive-volume no-limit observations; "
        "boundary 2023-04-10.",
        f"- IPO traded-session regimes (files): {json.dumps(inventory['ipo_no_limit_clock']['files_by_regime'], sort_keys=True)}; "
        f"raw rows before the first positive-volume session: {inventory['ipo_no_limit_clock']['raw_rows_before_first_positive_volume_session']:,}.",
        f"- Tolerant boards: {event_inventory['tolerant_sealed_up_detected_before_purge']:,}; strict boards: "
        f"{event_inventory['strict_sealed_up_detected_before_purge']:,}; marginal tolerance rows: "
        f"{event_inventory['marginal_tolerant_events_before_purge']:,}.",
        f"- Measured after boundary purge: {event_inventory['event_rows_measured']:,} signals, "
        f"{event_inventory['date_clusters']:,} date clusters, {event_inventory['run_clusters']:,} board-run clusters.",
        f"- `china_zt_pool` vendor strata use valid observed sessions only: "
        f"{len(receipt['results']['VENDOR_DESCRIPTIVE_STRATUM'].get('excluded_clone_dates', []))} clone dates "
        "are excluded, missing sessions are not imputed, and retrospective rows are explicitly stamped non-PIT.",
        f"- Vendor alias reconciliation: {zt.get('literal_unique_tickers', 0):,} literal names become "
        f"{zt.get('unique_tickers', 0):,} canonical names; {zt.get('raw_overlap_tickers', 0):,} overlap raw OHLCV, and "
        f"{zt.get('valid_observed_rows_with_raw_ohlcv', 0):,}/{zt.get('valid_observed_session_rows', 0):,} valid rows have local prices.",
        f"- Content-addressed input/config fingerprint: `{provenance['combined_sha256']}`. "
        f"{provenance['zt_pool_snapshot_disclosure']}",
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
            for row in receipt["results"]["C_AUCTION"]["primary_n1_n2_fill_funnel"]
            if row.get("market_scope") == "main_primary"
            and row.get("split") == "historical_replay_after_common_prior"
        ),
        None,
    )
    lines.extend([
        "## Main N=1/2 historical-replay fill funnel",
        "",
        "| Signals | Exact tradable next bar | Halt/missing bar | Zero-volume no-trade | Upper-limit queue | Candidate fills | Fill / all signals |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ])
    if main_funnel:
        lines.append(
            f"| {main_funnel['signals']:,} | {main_funnel['next_session_available']:,} | "
            f"{main_funnel['no_bar_halt_or_data_missing']:,} | "
            f"{main_funnel['zero_volume_halt_or_no_trade']:,} | "
            f"{main_funnel['open_at_upper_limit_queue_no_fill']:,} | "
            f"{main_funnel['official_open_candidate_fill']:,} | "
            f"{_pct(main_funnel['fill_rate_all_signals'])} |"
        )
    else:
        lines.append("| 0 | 0 | 0 | 0 | 0 | 0 | n/a |")

    lines.extend([
        "",
        "The event-level candidate-row expectancy keeps mature nonfills at cash=0 and explicitly equals "
        "P(fill) × E(net | resolved fill). It is not a portfolio return. Filled-conditional distributions "
        "remain diagnostics. The separately printed self-financing proxy reserves cash until exact exits.",
        "",
        "## N=1/2 overlap and cash-accounting replay — 60bp",
        "",
        "The no-duplicate row/date-equal columns are sequential-trade/cohort expectancy only. The cash-accounted "
        "columns invest available cash equally on each entry date and reserve it through exact exits. They remain "
        "a cost-basis, no-theme/no-capacity proxy—not a capital/theme-complete portfolio.",
        "",
        "| Exit | Accepted resolved | Same-ticker overlap cash | Row-weighted event | Date-equal cohort | Capital unavailable | Final NAV | Cumulative realised | Daily realised mean | Mean invested |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    cohort_book = receipt["results"]["C_AUCTION_PRIMARY_N1_N2_PORTFOLIO"][
        "sequential_trade_cohort_expectancy"
    ]
    capital_book = receipt["results"]["C_AUCTION_PRIMARY_N1_N2_PORTFOLIO"][
        "self_financing_paper_book"
    ]
    for exit_id in EXIT_IDS:
        cohort_row = next(
            (
                row
                for row in cohort_book["metrics"]
                if row["split"] == "historical_replay_after_common_prior"
                and row["exit_id"] == exit_id
                and row["cost_bps"] == 60
            ),
            None,
        )
        capital_row = next(
            row
            for row in capital_book["metrics"]
            if row["split"] == "historical_replay_after_common_prior"
            and row["exit_id"] == exit_id
            and row["cost_bps"] == 60
        )
        capital_funnel = capital_row["funnel"]
        if cohort_row is None:
            lines.append(
                f"| {exit_id} | 0 | 0 | n/a | n/a | "
                f"{capital_funnel.get('capital_unavailable_rejected_cash_zero', 0):,} | "
                f"{capital_row['final_nav_cost_basis']:.4f} | "
                f"{_pct(capital_row['cumulative_realised_return'])} | "
                f"{_pct(capital_row['daily_realised_return_metric'].get('mean'))} | "
                f"{_pct(capital_row['mean_invested_fraction'])} |"
            )
            continue
        lines.append(
            f"| {exit_id} | {cohort_row['accepted_resolved_fills']:,} | "
            f"{cohort_row['overlap_rejected_cash_zero']:,} | "
            f"{_pct(cohort_row['row_weighted_event_metric'].get('mean'))} | "
            f"{_pct(cohort_row['date_equal_daily_book_metric'].get('mean'))} | "
            f"{capital_funnel.get('capital_unavailable_rejected_cash_zero', 0):,} | "
            f"{capital_row['final_nav_cost_basis']:.4f} | "
            f"{_pct(capital_row['cumulative_realised_return'])} | "
            f"{_pct(capital_row['daily_realised_return_metric'].get('mean'))} | "
            f"{_pct(capital_row['mean_invested_fraction'])} |"
        )

    lines.extend([
        "",
        "## Fixed pre-auction rider books — locked replay primary comparison, seal-state exit, 60bp",
        "",
        "These are separate one-dimensional predeclared strata. The JSON includes every fixed exit and "
        "0/30/60/100bp; this compact table is the seal-state/60bp primary comparison only. No crossed "
        "combination or best-cell tuning was run.",
        "",
        "| Construction | Population | Fixed stratum | Candidates | Mature book | Fill / mature | Event-level cash-zero mean | Date-cluster 95% CI | Cell verdict |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
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
                f"| {construction_id} | {row['population_scope']} | {row['stratum']} | {row['candidate_signals']:,} | "
                f"{row['mature_candidate_signals']:,} | {_pct(row['p_fill_of_mature_book'])} | "
                f"{_pct(metric.get('mean'))} | {ci_text} | {row['verdict']} |"
            )

    lines.extend([
        "",
        "## Frozen crowd clock",
        "",
        "| Split | Population | Board | Friday | Holiday gap | Signals | Mature book | Inclusive continuation | Fill / all | Event-level seal-state 60bp |",
        "|---|---|---:|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in receipt["results"]["FROZEN_CROWD_CLOCK"]["table"]:
        joint = row["joint_cash_book_seal_state_60bps"]["joint_cash_book_metric"]
        lines.append(
            f"| {row['split']} | {row['population_scope']} | {row['board_count_bucket']} | {row['friday_flag']} | "
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
        "| Population | Board | Signals | Inclusive continuation | Observed-bar sensitivity | Fill / all | Event-level state 0bp | Event-level state 60bp |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in receipt["results"]["PREDECLARED_2015_STRESS"]["table"]:
        joint0 = row["joint_cash_book_seal_state_0bps"]["joint_cash_book_metric"]
        joint60 = row["joint_cash_book_seal_state_60bps"]["joint_cash_book_metric"]
        lines.append(
            f"| {row['population_scope']} | {row['board_count_bucket']} | {row['signals']:,} | "
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
        f"- Ticker canonicalization recovered {vendor.get('alias_recovered_join_rows', 0):,} joins beyond the "
        f"literal-suffix sensitivity ({vendor.get('literal_joined_curated_event_rows_sensitivity', 0):,} literal joins).",
        "- Absolute seal fund is unnormalised; all vendor-field verdicts remain descriptive.",
        "",
    ])

    lines.extend([
        "## ORE coverage ledger",
        "",
        "| Required construction family | Status | Exact scope |",
        "|---|---|---|",
        "| Five-axis continuation | UNTESTED_NOT_SILENTLY_KILLED | vol_z20, runup_5, gap_pct, dist_52w_low, consec_up_days |",
        "| Strict board definition | MEASURED_SEALED_CLOSE_SENSITIVITY | true-next-session probability and event-level cash-zero book |",
        "| Ecology extensions | UNTESTED_NOT_SILENTLY_KILLED | active ceiling, 3-session acceleration, leader-failure shock |",
        "| N>=3 riders | EXPLORATORY_ONLY_NO_PRIMARY_VERDICT | board-count cells remain visible but cannot drive Packet B |",
        "| Portfolio constraints | UNTESTED_BEYOND_FROZEN_CASH_RESERVATION_PROXY | mark-to-market, theme/sector caps, capacity, partial fills |",
        "",
        "## Honesty notes",
        "",
        "- `historical_replay_after_common_prior` is labelled replay, never unseen test.",
        "- `EVENT_LEVEL_CANDIDATE_ROW_EXPECTANCY_NOT_A_PORTFOLIO_RETURN` is the exact label for cash-zero signal rows; "
        "the no-duplicate date-equal series is cohort expectancy, and only the separate cash-reservation proxy is self-financing.",
        "- The self-financing proxy values open positions at cost until realised exits; interim drawdown, theme concentration, "
        "capacity, and mark-to-market risk remain unmeasured.",
        "- IPO listing dates are inferred from first positive-volume common-session raw observations; no complete official "
        "listing-master claim is made. Vendor identity normalization is limited to the explicit `.SH`/`.SS` alias.",
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
