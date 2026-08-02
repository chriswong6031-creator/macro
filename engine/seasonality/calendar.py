"""Lane 2 — the canonical curve and its small-multiple views.

Two house laws are enforced structurally rather than by comment:

1. **Never average raw price levels across years.** Every aggregate here is
   computed in log-return space over the rebased cumulative paths; the only way
   to get a price level out of this module is :func:`rebase_to_100`, which
   exponentiates a *single* already-aggregated log path.
2. **The independence unit is one complete year.** Every view bucket is first
   collapsed to one number per year, and only then aggregated across years, so
   every ``n`` this module publishes is a year count.  Aggregating the sessions
   directly would report ``n`` in the hundreds for the same evidence.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd

from .panel import N_SLOTS, YearPanel, month_slot_bounds

MAX_TRADING_DAY_OF_MONTH = 23
WEEKDAYS = (0, 1, 2, 3, 4)  # Monday .. Friday


def canonical_paths(panel: YearPanel) -> dict[str, np.ndarray]:
    """Return the median / p20 / p80 / mean log-cumulative paths.

    These are the strand field's ink and band.  They are log-cumulative, not
    prices: the frontend rebases for display so that the aggregation and the
    presentation cannot drift apart.
    """
    if panel.n_years == 0:
        empty = np.zeros(N_SLOTS, dtype=np.float64)
        return {"median": empty, "p20": empty.copy(), "p80": empty.copy(), "mean_log": empty.copy()}
    return {
        "median": np.median(panel.cum, axis=0),
        "p20": np.percentile(panel.cum, 20.0, axis=0),
        "p80": np.percentile(panel.cum, 80.0, axis=0),
        "mean_log": panel.cum.mean(axis=0),
    }


def rebase_to_100(log_path: Sequence[float] | np.ndarray) -> np.ndarray:
    """Turn ONE aggregated log-cumulative path into a display path at 100."""
    return 100.0 * np.exp(np.asarray(log_path, dtype=np.float64))


# --- per-year bucket aggregates --------------------------------------------


def _summarise(per_year: np.ndarray) -> dict[str, float | int]:
    """Collapse one bucket's per-year values into the published view entry."""
    values = np.asarray(per_year, dtype=np.float64)
    values = values[np.isfinite(values)]
    n = int(values.size)
    if n == 0:
        return {"mean": 0.0, "median": 0.0, "up_share": 0.0, "n": 0}
    return {
        "mean": round(float(values.mean()), 6),
        "median": round(float(np.median(values)), 6),
        "up_share": round(float((values > 0.0).sum() / n), 4),
        "n": n,
    }


def month_view(panel: YearPanel) -> list[dict]:
    """Twelve entries, each summarising one calendar month across years."""
    out: list[dict] = []
    for month in range(1, 13):
        first, last = month_slot_bounds(month)
        per_year = (
            panel.daily[:, first : last + 1].sum(axis=1)
            if panel.n_years
            else np.zeros(0, dtype=np.float64)
        )
        out.append({"k": month, **_summarise(per_year)})
    return out


def _per_year_bucket_sums(
    returns: pd.Series,
    years: Iterable[int],
    bucket: np.ndarray,
    keys: Sequence[int],
) -> dict[int, np.ndarray]:
    """Sum returns by ``bucket`` within each year, keeping years as the unit."""
    index = pd.DatetimeIndex(returns.index)
    year_of = np.asarray(index.year, dtype=np.int64)
    values = returns.to_numpy(dtype=np.float64)
    out: dict[int, list[float]] = {key: [] for key in keys}
    for year in years:
        mask = year_of == year
        if not mask.any():
            continue
        year_bucket = bucket[mask]
        year_values = values[mask]
        for key in keys:
            hit = year_bucket == key
            if hit.any():
                out[key].append(float(year_values[hit].sum()))
    return {key: np.asarray(vals, dtype=np.float64) for key, vals in out.items()}


def weekday_view(returns: pd.Series, years: Sequence[int]) -> list[dict]:
    """Five entries (Mon..Fri): each weekday's annual contribution, by year."""
    index = pd.DatetimeIndex(returns.index)
    buckets = np.asarray(index.weekday, dtype=np.int64)
    sums = _per_year_bucket_sums(returns, years, buckets, WEEKDAYS)
    return [{"k": weekday, **_summarise(sums[weekday])} for weekday in WEEKDAYS]


def trading_day_of_month_bucket(index: pd.DatetimeIndex) -> np.ndarray:
    """Rank each session within its own calendar month, 1-based."""
    frame = pd.DataFrame({"y": index.year, "m": index.month}, index=index)
    rank = frame.groupby(["y", "m"]).cumcount().to_numpy() + 1
    return rank.astype(np.int64)


def trading_day_of_month_view(returns: pd.Series, years: Sequence[int]) -> list[dict]:
    """Up to 23 entries: the k-th trading day's annual contribution, by year."""
    index = pd.DatetimeIndex(returns.index)
    buckets = trading_day_of_month_bucket(index)
    keys = tuple(range(1, MAX_TRADING_DAY_OF_MONTH + 1))
    sums = _per_year_bucket_sums(returns, years, buckets, keys)
    return [{"k": key, **_summarise(sums[key])} for key in keys if sums[key].size]


def build_views(panel: YearPanel, returns: pd.Series) -> dict[str, list[dict]]:
    """The three small-multiple views, all on the one-complete-year unit."""
    years = panel.years
    return {
        "month": month_view(panel),
        "weekday": weekday_view(returns, years),
        "trading_day_of_month": trading_day_of_month_view(returns, years),
    }
