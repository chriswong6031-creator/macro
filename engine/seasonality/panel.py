"""Lane 1 — the point-in-time year panel behind the calendar clock.

One instrument's adjusted daily closes become a fixed 365-slot calendar-day
clock, one row per **complete** year.  Everything downstream (canonical curve,
window scanner, selection correction) reads this panel and nothing else, so the
honesty boundary lives here:

* the unit of evidence is one complete year, never one trading day;
* a year enters the panel only if the vendor actually covers it end to end;
* non-trading days carry a zero log return rather than an interpolated one;
* Feb-29's log return is folded into the Feb-28 slot so every year has the same
  365 slots and no year silently loses a session;
* the market-neutral variant subtracts a strictly trailing beta, so no residual
  ever sees a price that had not printed yet.

The vendor's adjustment is its **current vintage** re-applied to all history.
That is not a frozen point-in-time adjustment and the artifact says so
(``is_pit_adjustment: false``); this module cannot repair it, only disclose it.

Pure computation over the committed parquet store — no network.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# --- calendar clock ---------------------------------------------------------

N_SLOTS = 365
YEARS_CAP = 25
MIN_COMPLETE_YEARS = 15

COMPLETE_YEAR_RULE = "first session <= Jan 10 and last session >= Dec 20"
MISSING_SESSION_POLICY = "non_trading_days_carry_zero_log_return"
LEAP_POLICY = "02-29_log_return_added_into_02-28_slot"

FIRST_SESSION_ON_OR_BEFORE = (1, 10)
LAST_SESSION_ON_OR_AFTER = (12, 20)

BETA_WINDOW_SESSIONS = 252
BETA_SOURCE = "pit_trailing_252d_shifted_one_session"

# Days before the start of each month in a 365-day (non-leap) year.
_MONTH_OFFSET = np.array([0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334])


def slot_labels() -> tuple[str, ...]:
    """Return the 365 canonical ``MM-DD`` slot labels, Jan-01 first."""
    origin = date(2001, 1, 1)  # any non-leap year
    return tuple((origin + timedelta(days=i)).strftime("%m-%d") for i in range(N_SLOTS))


def month_slot_bounds(month: int) -> tuple[int, int]:
    """Return the inclusive ``(first_slot, last_slot)`` of a calendar month."""
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1..12, got {month!r}")
    first = int(_MONTH_OFFSET[month - 1])
    last = (int(_MONTH_OFFSET[month]) - 1) if month < 12 else N_SLOTS - 1
    return first, last


def slots_for(index: pd.DatetimeIndex) -> np.ndarray:
    """Map timestamps onto 0..364 calendar-day slots, folding Feb-29 into Feb-28.

    The fold is additive downstream: two sessions can land in slot 58 in a leap
    year whose Feb-29 was a trading day, and both returns are summed there.  No
    session is ever dropped, so a year's total log return is preserved exactly.
    """
    month = np.asarray(index.month, dtype=np.int64)
    day = np.asarray(index.day, dtype=np.int64)
    day = np.where((month == 2) & (day == 29), 28, day)
    return _MONTH_OFFSET[month - 1] + day - 1


# --- loading ----------------------------------------------------------------


def load_adjusted_closes(root: Path, symbol: str) -> pd.Series:
    """Load one symbol's split- and dividend-adjusted daily closes.

    ``close`` is the adjusted series in this store; ``close_price`` is raw and
    is never used here — a raw series would put every split into the seasonal
    curve as a one-day crash.
    """
    path = Path(root) / "data" / "yahoo" / f"{symbol}.parquet"
    frame = pd.read_parquet(path, columns=["close"])
    series = frame["close"].dropna()
    series = series[series > 0.0]
    series.index = pd.DatetimeIndex(series.index).normalize()
    series = series[~series.index.duplicated(keep="last")]
    return series.sort_index()


def daily_log_returns(closes: pd.Series) -> pd.Series:
    """Convert adjusted closes to daily log returns (first session dropped)."""
    return np.log(closes).diff().dropna()


# --- completeness -----------------------------------------------------------


def complete_years(index: pd.DatetimeIndex) -> list[int]:
    """Return the years whose coverage spans the whole year.

    The rule is the one shipped in ``coverage.complete_year_rule`` and is applied
    to the sessions actually in the panel: a year is complete iff its first
    session is on or before Jan 10 and its last session is on or after Dec 20.

    One honest caveat, bounded and disclosed rather than papered over: returns
    are differences, so the very first session of the whole series carries no
    return.  If that session falls on or before Jan 10, its year still counts as
    complete and is short exactly one opening session's return.  Every window
    that starts after the first trading week of that one year is unaffected, and
    the cumulative path is rebased at slot 0 regardless.
    """
    if len(index) == 0:
        return []
    years = np.asarray(index.year, dtype=np.int64)
    month = np.asarray(index.month, dtype=np.int64)
    day = np.asarray(index.day, dtype=np.int64)

    out: list[int] = []
    for year in np.unique(years):
        mask = years == year
        opens_early = bool(
            ((month[mask] == FIRST_SESSION_ON_OR_BEFORE[0]) & (day[mask] <= FIRST_SESSION_ON_OR_BEFORE[1])).any()
        )
        closes_late = bool(
            ((month[mask] == LAST_SESSION_ON_OR_AFTER[0]) & (day[mask] >= LAST_SESSION_ON_OR_AFTER[1])).any()
        )
        if opens_early and closes_late:
            out.append(int(year))
    return out


# --- the panel --------------------------------------------------------------


@dataclass(frozen=True)
class YearPanel:
    """Complete-year log-return paths on the 365-slot calendar clock.

    ``daily[i, s]`` is the summed log return that landed in slot ``s`` of year
    ``years[i]``.  ``cum[i, s]`` is that year's cumulative path rebased so slot
    0 is exactly 0.0, which is what makes a window return the plain difference
    ``cum[i, b] - cum[i, a]``.
    """

    symbol: str
    years: tuple[int, ...]
    daily: np.ndarray  # (n_years, 365)
    cum: np.ndarray  # (n_years, 365), cum[:, 0] == 0.0
    n_years_available: int
    first_available_year: int | None
    last_available_year: int | None
    current_year: int | None
    current_cum: np.ndarray | None  # (last_index + 1,)
    current_last_index: int | None
    last_session: date | None

    @property
    def n_years(self) -> int:
        return len(self.years)


def _fold_year(returns: pd.Series) -> np.ndarray:
    """Sum one year's session returns into the 365 calendar slots."""
    row = np.zeros(N_SLOTS, dtype=np.float64)
    if len(returns) == 0:
        return row
    np.add.at(row, slots_for(pd.DatetimeIndex(returns.index)), returns.to_numpy(dtype=np.float64))
    return row


def _rebase(daily: np.ndarray) -> np.ndarray:
    """Cumulative path with slot 0 pinned to 0.0 (the docket's ``path_y(0)``)."""
    cumulative = np.cumsum(daily, axis=-1)
    return cumulative - np.take(cumulative, [0], axis=-1)


def build_year_panel(
    returns: pd.Series,
    *,
    symbol: str,
    cap: int = YEARS_CAP,
) -> YearPanel:
    """Fold a daily log-return series into the capped complete-year panel.

    The most recent ``cap`` complete years enter the panel; the count actually
    available is carried separately so the artifact can say how much history was
    left on the floor rather than quietly implying there was none.
    """
    index = pd.DatetimeIndex(returns.index)
    available = complete_years(index)
    years_in_index = np.asarray(index.year, dtype=np.int64)

    # The completeness rule was written for VENDOR COVERAGE of a year that is over.
    # Applied unchanged to the year in progress it admits it from Dec 20, so for the
    # last ~10 sessions of every December a truncated year would join the historical
    # evidence base (its Dec 21-31 slots reading as flat zero returns) AND the
    # "you are here" overlay would vanish, because the year is no longer partial.
    # A year is only evidence once it has actually finished.
    if available and len(index):
        last_year = int(years_in_index.max())
        if available[-1] == last_year and index.max() < pd.Timestamp(last_year, 12, 31):
            available = available[:-1]

    kept = available[-cap:] if cap else list(available)

    rows = [_fold_year(returns[years_in_index == year]) for year in kept]
    daily = np.asarray(rows, dtype=np.float64).reshape(len(kept), N_SLOTS)

    current_year: int | None = None
    current_cum: np.ndarray | None = None
    current_last_index: int | None = None
    if len(index):
        last_year = int(years_in_index.max())
        if last_year not in available:
            tail = returns[years_in_index == last_year]
            if len(tail):
                folded = _fold_year(tail)
                last_index = int(slots_for(pd.DatetimeIndex(tail.index)).max())
                current_year = last_year
                current_cum = _rebase(folded)[: last_index + 1]
                current_last_index = last_index

    return YearPanel(
        symbol=symbol,
        years=tuple(kept),
        daily=daily,
        cum=_rebase(daily),
        n_years_available=len(available),
        first_available_year=available[0] if available else None,
        last_available_year=available[-1] if available else None,
        current_year=current_year,
        current_cum=current_cum,
        current_last_index=current_last_index,
        last_session=index.max().date() if len(index) else None,
    )


# --- market-neutral variant -------------------------------------------------


def pit_trailing_beta(
    symbol_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    window: int = BETA_WINDOW_SESSIONS,
) -> pd.Series:
    """Trailing beta that only ever sees sessions strictly before its own.

    ``rolling(window)`` at session ``t`` covers ``t-window+1 .. t``; the
    ``shift(1)`` moves it to ``t-window .. t-1``.  Without that shift the
    residual for session ``t`` would be computed with a beta fitted on session
    ``t`` itself — a look-ahead small enough to pass every eyeball test and
    large enough to manufacture a seasonal effect.
    """
    joined = pd.DataFrame({"s": symbol_returns, "m": benchmark_returns}).dropna()
    if len(joined) <= window:
        return pd.Series(dtype=np.float64)
    covariance = joined["s"].rolling(window).cov(joined["m"])
    variance = joined["m"].rolling(window).var()
    beta = (covariance / variance).shift(1)
    return beta.replace([np.inf, -np.inf], np.nan).dropna()


def market_residual_returns(
    symbol_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    window: int = BETA_WINDOW_SESSIONS,
) -> pd.Series:
    """Return ``r_symbol - beta_pit * r_benchmark`` on the shared sessions."""
    beta = pit_trailing_beta(symbol_returns, benchmark_returns, window=window)
    if beta.empty:
        return pd.Series(dtype=np.float64)
    aligned_symbol = symbol_returns.reindex(beta.index)
    aligned_market = benchmark_returns.reindex(beta.index)
    return (aligned_symbol - beta * aligned_market).dropna()


def build_neutral_panel(
    symbol_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    symbol: str,
    keep_years: tuple[int, ...],
    cap: int = YEARS_CAP,
    window: int = BETA_WINDOW_SESSIONS,
) -> YearPanel | None:
    """Build the market-neutral panel, restricted to the raw panel's years.

    Returns ``None`` when the benchmark leg cannot be formed — too little history
    for the beta warm-up, or a residual that is numerically indistinguishable from
    zero, which is what the benchmark regressed on itself produces.
    """
    residual = market_residual_returns(symbol_returns, benchmark_returns, window=window)
    if residual.empty:
        return None
    # A series regressed on itself leaves floating-point dust, not zero: pandas
    # computes rolling cov and rolling var down separate code paths, so beta comes
    # out 1 +/- 1e-16 and the residual is ~1e-16 of noise. Scanned, that dust
    # produces a confident "surviving 20-day season" fitted entirely to rounding
    # error. Refuse it here rather than relying on the caller's symbol check.
    scale = float(symbol_returns.std())
    if not np.isfinite(scale) or float(residual.std()) < 1e-9 * max(scale, 1e-12):
        return None
    panel = build_year_panel(residual, symbol=symbol, cap=cap)
    keep = tuple(year for year in panel.years if year in set(keep_years))
    if not keep:
        return None
    mask = np.array([year in set(keep) for year in panel.years], dtype=bool)
    return YearPanel(
        symbol=symbol,
        years=keep,
        daily=panel.daily[mask],
        cum=panel.cum[mask],
        n_years_available=panel.n_years_available,
        first_available_year=panel.first_available_year,
        last_available_year=panel.last_available_year,
        current_year=None,
        current_cum=None,
        current_last_index=None,
        last_session=panel.last_session,
    )
