"""Entry-Stack Amendment 2 T1a — per-fire insider context panel builder.

Spec: research/ENTRY_STACK_EXPANSION_AMENDMENT2_BY_FABLE.md §B RUL-22/23/26,
      §C4, §D T1.

This is an OFF-PATH research script — NOT wired into the nightly pipeline.
Run manually to produce:
  data/research/insider_fire_context_deep.parquet
  data/research/insider_fire_context_baskets.parquet
  data/research/insider_fire_context_meta.json

PIT discipline (RUL-23): all insider windows are keyed on FILING_DATE ≤ t.
The legal Form-4 filing lag is ≤2 business days after the trade, so
filing_date is the earliest public-knowledge anchor — never trans_date.

Window arithmetic (v1.1 — Amendment 2 RUL-26):
  ALL insider windows (45td buyer, 20td buyer, 756td computable, +15td post)
  use TRADING-DAY counting via searchsorted on the ticker's own price-date
  index (same approach as _build_washout_cache). Where a ticker's price index
  is unavailable, we derive trading days from the union price calendar across
  all loaded tickers (NYSE-approximate — documented in meta). This ensures
  both legs of I1 (washout 45td + buyer 45td) span the same window.

Forms computed per fire (ticker, date t):
  ins_computable        bool: ticker in panel with ≥1 filing in trailing 3y at t
  ins_i3_computable     bool: I3-specific: ticker has ≥1 filing in trailing 3y-td
                               in the FORM-4-ELIGIBLE UNIVERSE (used for I3 base)
  washout_flag          bool: min close/126d_high − 1 ≤ −0.20 over [t-45td, t]
  ins_buyers_45d        int:  distinct open-market buyers (code=P) in [t-45td, t]
  ins_cluster_washout   bool: I1 — washout_flag AND ins_buyers_45d ≥ 2 (filing_date ≤ t)
  ins_cluster_washout_3 bool: I1 sensitivity — same with ≥3 buyers (RUL-26)
  ins_cluster_pre20     bool: I2 — distinct buyers in [t-20td, t] ≥ 2 (PIT)
  ins_cluster_post15    int:  DESCRIPTIVE ONLY — buyers in (t, t+15td] (study-time,
                               NOT a PIT stratum; pit_at_entry=false in meta)
  ins_netusd_mcap_sn_p80 bool: I3 — trailing 6-month net_usd/mcap sector-neutral
                                pctile ≥ 80 vs FORM-4-ELIGIBLE UNIVERSE at t;
                                negative-IC opportunistic filter EXCLUDED
  ins_i3_sector_neutral  bool: True = sector-neutral pctile used, False = universe-wide

Usage:
    cd /path/to/repo
    python scripts/research/build_insider_fire_context.py
    python scripts/research/build_insider_fire_context.py --panel deep
    python scripts/research/build_insider_fire_context.py --smoke    # first 500 fires each
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA           = _REPO_ROOT / "data"
_FIRES_DEEP     = _DATA / "research" / "gate_fires_deep.parquet"
_FIRES_BASKETS  = _DATA / "research" / "gate_fires_baskets.parquet"
_PANEL_DIR      = _DATA / "sec_insider" / "panel"
_FLAT_PANEL     = _DATA / "sec_insider" / "insider_panel.parquet"
_OUT_DEEP       = _DATA / "research" / "insider_fire_context_deep.parquet"
_OUT_BASKETS    = _DATA / "research" / "insider_fire_context_baskets.parquet"
_OUT_META       = _DATA / "research" / "insider_fire_context_meta.json"
_STOCKS_DIR     = _DATA / "stocks"
_BASKETS_OHLCV  = _DATA / "baskets" / "ohlcv"

# ---------------------------------------------------------------------------
# Frozen thresholds (RUL-26; no alternative tested before read)
# ---------------------------------------------------------------------------
_WASHOUT_LOOKBACK_TD  = 45      # trading days back from t for washout window
_WASHOUT_HIGH_WINDOW  = 126     # rolling window for 126d high
_WASHOUT_THRESHOLD    = -0.20   # ≤ −20% drawdown from 126d high = washout_flag
_CLUSTER_WINDOW_45    = 45      # I1: buyer window (filing_date within [t-45, t])
_CLUSTER_WINDOW_20    = 20      # I2: buyer window (filing_date within [t-20, t])
_CLUSTER_POST15       = 15      # descriptive: (t, t+15] — NOT PIT
_CLUSTER_MIN_BUYERS   = 2       # I1/I2 threshold (≥2 distinct buyers)
_CLUSTER_MIN_BUYERS_3 = 3       # I1 sensitivity (≥3 distinct buyers)
_COMPUTABLE_3Y_TD     = 756     # ≈3 years of trading days
_I3_NET_USD_MONTHS    = 6       # trailing 6-month net_usd window for I3
_I3_PERCENTILE        = 80      # sector-neutral pctile ≥ 80 (I3)

# Definition version stamped in output meta
_DEFINITION_VERSION = "v1.2"
_DEFINITION_CHANGELOG = (
    "v1.1 (2026-07-05): M1 — all insider windows converted to trading-day "
    "arithmetic (searchsorted on price index; was calendar days); M2 — I3 "
    "percentile base expanded to Form-4-eligible universe at t, not just "
    "co-firing tickers; m3 — PIT mcap from fundamentals_panel.parquet where "
    "available, close-price proxy as fallback. "
    "v1.2 (2026-07-05): I3 midrank+positive-gate — (a) fire must have "
    "net_usd_mcap > 0 (strict positive gate eliminates non-net-buyers); "
    "(b) percentile now uses midrank (average-rank tie-handling via "
    "scipy.stats.rankdata method='average') instead of weak-inequality mean, "
    "preventing the zero-mass inflation where 61% of zero-net-buy fires "
    "incorrectly flagged >= p80; (c) same fix applied to sector-neutral arm; "
    "(d) self-inclusive midrank (fire included in its own comparison pool, "
    "documented in meta); (e) deleted dead functions _ins_buyers_in_window "
    "(calendar-day resurrection hazard) and _compute_net_usd_mcap_for_ticker "
    "(superseded by vectorized _build_i3_universe_cache)."
)

# Program eras for coverage reporting (RUL-26)
_PROGRAM_ERAS = {
    "2012-2015": (pd.Timestamp("2012-01-01"), pd.Timestamp("2015-12-31")),
    "2016-2019": (pd.Timestamp("2016-01-01"), pd.Timestamp("2019-12-31")),
    "2020-2022": (pd.Timestamp("2020-01-01"), pd.Timestamp("2022-12-31")),
    "2023-2026": (pd.Timestamp("2023-01-01"), pd.Timestamp("2026-12-31")),
}


# ---------------------------------------------------------------------------
# Trading-day calendar helpers (M1 fix)
# ---------------------------------------------------------------------------

def _build_union_calendar(closes: dict[str, "pd.Series"]) -> "pd.DatetimeIndex":
    """Return the union of all trading-day indices across loaded tickers.

    This is used as a fallback NYSE-approximate calendar when a specific
    ticker's price index is unavailable (e.g. basket panel vs deep panel).
    The union of real price dates is a better approximation of NYSE trading
    days than pd.bdate_range (which includes some NYSE holidays) and requires
    no external library.
    """
    if not closes:
        return pd.DatetimeIndex([])
    all_dates: set = set()
    for s in closes.values():
        all_dates.update(s.dropna().index.tolist())
    return pd.DatetimeIndex(sorted(all_dates))


def _td_offset(
    t: "pd.Timestamp",
    n_td: int,
    price_index: "pd.DatetimeIndex | None",
    fallback_calendar: "pd.DatetimeIndex",
    *,
    direction: int = -1,
) -> "pd.Timestamp":
    """Return the date that is `n_td` trading days before (direction=-1) or
    after (direction=+1) `t`, measured on `price_index` (preferred) or
    `fallback_calendar`.

    If neither calendar contains `t`, we snap t to the nearest prior date
    in the calendar before counting. The returned date is a calendar date
    (the actual nth trading day); callers then use it as a filing_date
    threshold (>=/<= on calendar dates as usual).
    """
    cal = price_index if (price_index is not None and len(price_index) > 0) else fallback_calendar
    if len(cal) == 0:
        # Ultimate fallback: approximate with calendar days (1 td ≈ 1.4 cd)
        return t + pd.Timedelta(days=int(n_td * 1.4 * direction))

    # Find position of t in the calendar (snap to prior if t not present)
    pos = cal.searchsorted(t, side="right") - 1
    if pos < 0:
        pos = 0

    target_pos = pos + direction * n_td
    target_pos = max(0, min(target_pos, len(cal) - 1))
    return cal[target_pos]


# ---------------------------------------------------------------------------
# Panel loader — concat panel/ dir; fall back to gitignored flat if fresher
# ---------------------------------------------------------------------------

def _load_insider_panel() -> pd.DataFrame:
    """Load the per-transaction insider panel.

    Preferred source: concat data/sec_insider/panel/*.parquet DIRECTLY.
    This is the only source available on a fresh worktree (the flat
    insider_panel.parquet is gitignored). If the flat file exists and is
    newer than the newest per-quarter file (i.e. it includes an in-progress
    quarter not yet flushed to its own file), use the flat file instead.
    """
    if not _PANEL_DIR.exists():
        raise FileNotFoundError(f"Panel dir not found: {_PANEL_DIR}")

    quarter_files = sorted(_PANEL_DIR.glob("*.parquet"))
    if not quarter_files:
        raise FileNotFoundError(f"No per-quarter parquets under {_PANEL_DIR}")

    # Check if flat file is fresher (intra-quarter data not yet in a per-quarter file)
    if _FLAT_PANEL.exists():
        flat_mtime = _FLAT_PANEL.stat().st_mtime
        newest_q_mtime = max(p.stat().st_mtime for p in quarter_files)
        if flat_mtime > newest_q_mtime:
            log.info("Using flat insider_panel.parquet (fresher than per-quarter files)")
            return pd.read_parquet(_FLAT_PANEL)

    log.info("Concatenating %d per-quarter parquets from %s", len(quarter_files), _PANEL_DIR)
    parts = []
    for p in quarter_files:
        try:
            df = pd.read_parquet(p)
            if not df.empty:
                parts.append(df)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping %s: %s", p.name, exc)

    if not parts:
        raise ValueError("No rows loaded from per-quarter panel files")

    panel = pd.concat(parts, ignore_index=True).sort_values("filing_date").reset_index(drop=True)
    log.info("Panel loaded: %d rows, %d tickers, %s → %s",
             len(panel), panel["ticker"].nunique(),
             panel["filing_date"].min().date(), panel["filing_date"].max().date())
    return panel


# ---------------------------------------------------------------------------
# Price loader (reusing _get_closes pattern from W1-STS runner)
# ---------------------------------------------------------------------------

def _load_closes_deep() -> dict[str, pd.Series]:
    """Load close prices from data/stocks/*.parquet (deep panel)."""
    closes: dict[str, pd.Series] = {}
    if not _STOCKS_DIR.exists():
        log.warning("stocks dir absent: %s", _STOCKS_DIR)
        return closes
    for path in sorted(_STOCKS_DIR.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path, columns=["close"])
            s = df["close"].dropna().sort_index()
            if len(s) >= 50:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.debug("Failed to load %s: %s", path, exc)
    log.info("Deep closes loaded: %d tickers", len(closes))
    return closes


def _load_closes_baskets() -> dict[str, pd.Series]:
    """Load close prices from data/baskets/ohlcv/*.parquet."""
    closes: dict[str, pd.Series] = {}
    if not _BASKETS_OHLCV.exists():
        log.warning("baskets ohlcv dir absent: %s", _BASKETS_OHLCV)
        return closes
    for path in sorted(_BASKETS_OHLCV.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            col = "close" if "close" in df.columns else df.columns[0]
            s = df[col].dropna().sort_index()
            if len(s) >= 50:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.debug("Failed to load %s: %s", path, exc)
    log.info("Baskets closes loaded: %d tickers", len(closes))
    return closes


# ---------------------------------------------------------------------------
# Sector map (reuse entry_strata_phase0 builder)
# ---------------------------------------------------------------------------

def _load_sector_map() -> dict[str, str]:
    try:
        from scripts.research.entry_strata_phase0 import _build_sector_map
        return _build_sector_map()
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load sector map: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Washout flag computation (vectorised per-ticker, searchsorted lookup)
# ---------------------------------------------------------------------------

def _build_washout_cache(
    fires: pd.DataFrame,
    closes: dict[str, pd.Series],
) -> pd.Series:
    """Compute washout_flag for each fire (PIT: only prior bars used).

    washout_flag = 1 if min over d ∈ [t-45td, t] of
                       (close_d / rolling_126d_high_strictly_prior_d − 1) ≤ −0.20.
    Uses the close price up to and including bar t.
    Rolling 126d high is computed strictly on bars prior to each bar d
    (i.e., high = max of close[d-126:d], not including d itself — this is a
    strict look-back, consistent with the "overhead supply" framing).
    """
    cache: dict[str, pd.Series] = {}

    # Precompute the rolling-126d-high series per ticker (shifted by 1 so it
    # never includes the current bar in the high).
    for ticker, close in closes.items():
        c = close.dropna().sort_index()
        if len(c) < _WASHOUT_HIGH_WINDOW + 1:
            continue
        # rolling(126).max() at bar i = max of [i-126, i-1] when we shift by 1
        roll_high = c.shift(1).rolling(_WASHOUT_HIGH_WINDOW, min_periods=_WASHOUT_HIGH_WINDOW).max()
        drawdown = (c / roll_high) - 1.0
        cache[ticker] = drawdown  # indexed by date; NaN where < 126 bars history

    results = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["date"])
        dd = cache.get(ticker)
        if dd is None:
            results.append(None)
            continue
        # Window [t-45td, t] in calendar proximity
        # We take strictly-prior bars by searching the drawdown index
        loc_t = dd.index.searchsorted(t, side="right") - 1
        if loc_t < 0:
            results.append(None)
            continue
        loc_start = max(0, loc_t - _WASHOUT_LOOKBACK_TD + 1)
        window_dd = dd.iloc[loc_start: loc_t + 1]
        valid = window_dd.dropna()
        if len(valid) == 0:
            results.append(None)
            continue
        results.append(bool(float(valid.min()) <= _WASHOUT_THRESHOLD))

    return pd.Series(results, index=fires.index, name="washout_flag")


# ---------------------------------------------------------------------------
# Insider signal helpers (filing_date-keyed, PIT)
# ---------------------------------------------------------------------------

def _build_ticker_index(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Pre-index the panel by ticker for O(1) per-ticker access."""
    log.info("Indexing panel by ticker...")
    idx: dict[str, pd.DataFrame] = {}
    for ticker, grp in panel.groupby("ticker", sort=False):
        idx[str(ticker)] = grp.reset_index(drop=True)
    log.info("Ticker index built: %d tickers", len(idx))
    return idx


# ---------------------------------------------------------------------------
# I3: trailing 6-month net_usd/mcap sector-neutral percentile
# ---------------------------------------------------------------------------

def _pit_close(
    ticker: str,
    t: "pd.Timestamp",
    closes: dict[str, "pd.Series"],
) -> float | None:
    """Return the PIT close price for ticker at t (most recent bar ≤ t)."""
    close = closes.get(ticker)
    if close is None or close.empty:
        return None
    c = close.dropna().sort_index()
    loc = c.index.searchsorted(t, side="right") - 1
    if loc < 0:
        return None
    v = float(c.iloc[loc])
    return v if v > 0 else None


def _pit_shares(
    ticker: str,
    t: "pd.Timestamp",
    shares_panel: "pd.DataFrame | None",
) -> float | None:
    """Return PIT shares outstanding for ticker at t from fundamentals_panel.

    Uses asof_date ≤ t (causal, mirrors insider_phase0 / insider_factor.market_cap).
    Returns None when shares_panel is None or ticker/date not covered.
    """
    if shares_panel is None or shares_panel.empty:
        return None
    avail = shares_panel[
        (shares_panel["ticker"] == ticker) &
        (shares_panel["asof_date"] <= t)
    ]
    if avail.empty:
        return None
    shares = float(avail["shares"].iloc[-1])
    return shares if shares > 0 else None


def _build_i3_universe_cache(
    panel: "pd.DataFrame",
    closes: dict[str, "pd.Series"],
    shares_panel: "pd.DataFrame | None",
    fire_dates: "pd.DatetimeIndex",
    union_cal: "pd.DatetimeIndex",
) -> tuple[dict["pd.Timestamp", dict[str, float]], float]:
    """For each unique fire date t, compute net_usd_6m/mcap for every ticker
    in the Form-4-eligible universe at t (≥1 filing in trailing 3y-td).

    This is the M2 fix: the I3 percentile base is the UNIVERSE at t, not just
    co-firing tickers.

    Vectorized implementation:
    1. Aggregate the panel to (ticker, filing_date) → net_usd at the filing_date level.
    2. For each unique fire date t, window the aggregated panel to [t-6m, t] to get
       trailing net_usd per ticker, then divide by PIT mcap.
    3. For computable check (≥1 filing in trailing 3y-td), pre-compute the last
       filing date per ticker and check against t - 3y-td.

    Returns ({t: {ticker: net_usd_mcap_val}}, fallback_fraction).
    """
    # --- Step 1: Pre-aggregate to (ticker, filing_date) → net_usd_signed ---
    # Vectorized: assign signed_usd (P=+, S=-), groupby ticker+filing_date, sum.
    sub = panel[panel["code"].isin(["P", "S"])][["ticker", "filing_date", "code", "usd"]].copy()
    sub["signed_usd"] = sub["usd"] * sub["code"].map({"P": 1.0, "S": -1.0})
    net_by_tfd = (
        sub.groupby(["ticker", "filing_date"])["signed_usd"]
        .sum()
    )  # MultiIndex (ticker, filing_date) → net_usd

    # Build per-ticker sorted arrays of (filing_date_us, net_usd).
    # Use microseconds as the common unit throughout: pandas datetime64[us] → int64
    # gives microseconds. We normalize all timestamps to microseconds to avoid the
    # datetime64[us] vs nanosecond mismatch (pd.Timestamp.value is ns).
    _US_PER_DAY = 24 * 3600 * 1_000_000  # microseconds per day

    def _to_us(arr_or_ts) -> np.ndarray:
        """Convert datetime array or pd.Timestamp to int64 microseconds."""
        if isinstance(arr_or_ts, pd.Timestamp):
            # pd.Timestamp.value is nanoseconds; divide by 1000
            return np.array([arr_or_ts.value // 1000], dtype=np.int64)
        a = np.asarray(arr_or_ts)
        if np.issubdtype(a.dtype, np.datetime64):
            return a.astype("datetime64[us]").astype("int64")
        return a.astype("int64")

    sorted_events: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ticker, grp in net_by_tfd.groupby(level=0):
        dates_us = _to_us(grp.index.get_level_values("filing_date").values)
        nets = grp.values.astype("float64")
        order = np.argsort(dates_us, stable=True)
        sorted_events[str(ticker)] = (dates_us[order], nets[order])

    # --- Step 2: PIT shares lookup (m3 fix) ---
    # Build a per-ticker list of (asof_date_us, shares) sorted by asof_date
    pit_shares_map: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    n_pit = 0
    n_fallback = 0
    if shares_panel is not None and not shares_panel.empty:
        for ticker, grp in shares_panel.groupby("ticker"):
            grp = grp.sort_values("asof_date")
            pit_shares_map[str(ticker)] = (
                _to_us(grp["asof_date"].values),
                grp["shares"].values.astype("float64"),
            )

    def _get_pit_shares_fast(ticker: str, t_us: int) -> float | None:
        if ticker not in pit_shares_map:
            return None
        asof_arr, shares_arr = pit_shares_map[ticker]
        pos = np.searchsorted(asof_arr, t_us, side="right") - 1
        if pos < 0:
            return None
        v = float(shares_arr[pos])
        return v if v > 0 else None

    # --- Step 3: PIT close lookup (vectorized, per-ticker cache) ---
    # Pre-cache (date_us_arr, close_arr) per ticker for O(log n) lookup
    close_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for ticker, s in closes.items():
        c = s.dropna().sort_index()
        if len(c) > 0:
            close_cache[ticker] = (
                _to_us(c.index.values),
                c.values.astype("float64"),
            )

    def _get_pit_close_fast(ticker: str, t_us: int) -> float | None:
        if ticker not in close_cache:
            return None
        d_arr, c_arr = close_cache[ticker]
        pos = np.searchsorted(d_arr, t_us, side="right") - 1
        if pos < 0:
            return None
        v = float(c_arr[pos])
        return v if v > 0 else None

    # --- Step 4: Build cache — vectorized per-ticker, across all fire dates ---
    # Instead of looping (date → tickers), we loop (ticker → all fire dates) which
    # is much more vectorizable: for each ticker we do a searchsorted sweep over
    # all fire_dates at once.
    unique_dates = sorted(set(fire_dates.tolist()))
    fire_dates_us = np.array([int(_to_us(d)[0]) for d in unique_dates], dtype=np.int64)
    n_dates = len(fire_dates_us)

    log.info("  I3 universe cache: %d unique fire dates × %d panel tickers (vectorized per-ticker)",
             n_dates, len(sorted_events))

    # Pre-compute union_cal in microseconds for 3y-td offset
    union_cal_us = _to_us(union_cal.values) if len(union_cal) > 0 else np.array([], dtype=np.int64)
    _6M_US = int(183 * _US_PER_DAY)  # approximate 6-month lookback in microseconds

    # Pre-compute t_3y_us and t_6m_us for all unique dates at once
    if len(union_cal_us) > 0:
        pos_t_arr = np.searchsorted(union_cal_us, fire_dates_us, side="right") - 1
        pos_3y_arr = np.maximum(0, pos_t_arr - _COMPUTABLE_3Y_TD)
        t_3y_us_arr = union_cal_us[pos_3y_arr]
    else:
        t_3y_us_arr = fire_dates_us - int(_COMPUTABLE_3Y_TD * 1.4 * _US_PER_DAY)
    t_6m_us_arr = fire_dates_us - _6M_US

    # cache[date_index] = {ticker: net_usd_mcap_val}
    # Use list of dicts indexed by date position
    cache_list: list[dict[str, float]] = [{} for _ in range(n_dates)]

    for ticker, (date_arr, net_arr) in sorted_events.items():
        if len(date_arr) == 0:
            continue

        # For each fire date: find [t_3y, t] window → computable check
        # Using searchsorted vectorized over all fire dates
        hi_arr = np.searchsorted(date_arr, fire_dates_us, side="right")
        lo_arr = np.searchsorted(date_arr, t_3y_us_arr, side="left")
        lo6_arr = np.searchsorted(date_arr, t_6m_us_arr, side="left")

        # Find dates where ticker is computable (hi > lo → has filing in 3y window)
        computable_mask = hi_arr > lo_arr
        if not np.any(computable_mask):
            continue

        # For computable dates: compute net_usd_6m
        # We need cumulative sum for fast range sum
        cum_net = np.concatenate(([0.0], np.cumsum(net_arr)))
        # net in [lo6, hi) = cum_net[hi] - cum_net[lo6]
        net_usd_arr = cum_net[hi_arr] - cum_net[lo6_arr]

        # PIT close for this ticker — get the values for all fire dates at once
        if ticker not in close_cache:
            continue
        d_arr_c, c_arr_c = close_cache[ticker]
        close_pos = np.searchsorted(d_arr_c, fire_dates_us, side="right") - 1
        # Clamp to valid range and get close values
        valid_close_mask = close_pos >= 0
        combined_mask = computable_mask & valid_close_mask
        if not np.any(combined_mask):
            continue

        close_pos_valid = np.where(combined_mask, np.maximum(close_pos, 0), 0)
        close_vals = c_arr_c[close_pos_valid]
        close_vals = np.where(combined_mask, close_vals, 0.0)
        positive_close = close_vals > 0
        combined_mask = combined_mask & positive_close
        if not np.any(combined_mask):
            continue

        # PIT shares for this ticker (if available) — also vectorized
        if ticker in pit_shares_map:
            asof_arr_s, shares_arr_s = pit_shares_map[ticker]
            shares_pos = np.searchsorted(asof_arr_s, fire_dates_us, side="right") - 1
            valid_shares = shares_pos >= 0
            shares_pos_clamped = np.where(valid_shares, np.maximum(shares_pos, 0), 0)
            shares_vals = shares_arr_s[shares_pos_clamped]
            shares_vals = np.where(valid_shares & (shares_arr_s[shares_pos_clamped] > 0), shares_vals, np.nan)
            # denom = close × shares where shares available, else close alone
            has_shares = valid_shares & (shares_vals > 0) & combined_mask
            denom_arr = np.where(has_shares, close_vals * shares_vals, close_vals)
            n_pit += int(np.sum(has_shares & combined_mask))
            n_fallback += int(np.sum(~has_shares & combined_mask))
        else:
            denom_arr = close_vals
            n_fallback += int(np.sum(combined_mask))

        denom_arr = np.where(combined_mask, denom_arr, 0.0)
        valid_denom = combined_mask & (denom_arr > 0)
        if not np.any(valid_denom):
            continue

        with np.errstate(divide="ignore", invalid="ignore"):
            net_usd_mcap = np.where(valid_denom, net_usd_arr / np.where(denom_arr != 0, denom_arr, np.nan), np.nan)

        # Write results to cache_list
        for di in np.where(valid_denom)[0]:
            cache_list[di][ticker] = float(net_usd_mcap[di])

    # Convert cache_list → dict keyed by Timestamp
    cache: dict[pd.Timestamp, dict[str, float]] = {
        unique_dates[i]: cache_list[i] for i in range(n_dates)
    }

    total = n_pit + n_fallback
    fallback_frac = n_fallback / max(total, 1)
    log.info("  I3 universe mcap: %d PIT, %d fallback (%.1f%% fallback)",
             n_pit, n_fallback, 100.0 * fallback_frac)
    return cache, fallback_frac


def _midrank_percentile(vals: list[float], fire_val: float) -> float:
    """Return the midrank-based percentile of fire_val within vals (self-inclusive).

    Implementation: fire_val is included in the pool (self-inclusive ranking).
    Midrank = (rank_lo + rank_hi) / (2 * n) where rank_lo is the number of
    values strictly less than fire_val and rank_hi is the number of values ≤
    fire_val, so midrank = (rank_lo + rank_hi) / (2 * n).

    This equals scipy.stats.rankdata(vals, method='average')[fire_pos] / n
    (where fire_pos is the index of fire_val in vals), which handles ties by
    assigning the average of positions. Using it avoids importing scipy.stats
    while matching its output exactly for the percentile computation.

    The key property: a value that ties with many zeros gets midrank ≈ 0.5 *
    zero_fraction, not weak-inequality fraction (≈ zero_fraction). This
    eliminates the inflation where 61% of zero-net-buy fires flagged >= p80.
    """
    arr = np.asarray(vals, dtype=float)
    n = len(arr)
    if n == 0:
        return 0.0
    rank_lo = float(np.sum(arr < fire_val))    # strictly below
    rank_hi = float(np.sum(arr <= fire_val))   # at or below (inclusive)
    midrank = (rank_lo + rank_hi) / (2.0 * n)
    return midrank


def _compute_i3_net_usd_mcap(
    fires: "pd.DataFrame",
    panel: "pd.DataFrame",
    closes: dict[str, "pd.Series"],
    sector_map: dict[str, str],
    union_cal: "pd.DatetimeIndex",
    shares_panel: "pd.DataFrame | None" = None,
) -> tuple["pd.Series", "pd.Series", "pd.Series", float]:
    """Compute I3: trailing 6-month net_usd/mcap sector-neutral pctile ≥ 80.

    M2 fix: percentile is taken against the FORM-4-ELIGIBLE UNIVERSE at t
    (all tickers in the panel computable at t), NOT just co-firing tickers.
    This eliminates the singleton-date artifact where a single fire auto-gets
    pctile=1.0.

    m3 fix: PIT market cap from fundamentals_panel.parquet where available
    (shares × close), falling back to close-price proxy.

    v1.2 fix (midrank + positive gate):
      (a) fire_val must be strictly > 0 (net buyer gate); zero / negative values
          are excluded — I3 requires *concentrated insider buying*, not merely
          avoiding being a net seller.
      (b) Percentile computed via midrank (average-rank tie-handling), not
          weak-inequality mean. Midrank = (count_strictly_below + count_leq) /
          (2 * n). Self-inclusive: fire_val is included in the pool. This
          prevents the zero-mass inflation where the entire ~17% mass at exactly
          zero inflated any zero fire to >= 80th pctile under weak-inequality.
      (c) Same fix applied to the sector-neutral arm.

    Returns (ins_netusd_mcap_sn_p80, ins_i3_sector_neutral, ins_i3_computable,
             mcap_fallback_fraction).
    """
    ticker_idx = _build_ticker_index(panel)
    fire_dates = pd.DatetimeIndex(pd.to_datetime(fires["date"]))

    # Build universe cache (M2 + m3 fix)
    universe_cache, fallback_frac = _build_i3_universe_cache(
        panel, closes, shares_panel, fire_dates, union_cal
    )

    sn_p80_d: dict[Any, bool | None] = {}
    sn_flag_d: dict[Any, bool | None] = {}
    i3_computable_d: dict[Any, bool] = {}

    for idx, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["date"])

        # Universe at t (M2 base)
        date_universe = universe_cache.get(t, {})

        # Is this ticker I3-computable (in the universe at t)?
        i3_computable_d[idx] = ticker in date_universe

        # Fire's own value
        fire_val = date_universe.get(ticker)

        if fire_val is None or len(date_universe) == 0:
            sn_p80_d[idx] = None
            sn_flag_d[idx] = None
            continue

        # v1.2 positive gate: fire must be a net buyer (strict positive)
        # Zero and negative values mean no concentrated insider buying signal.
        if fire_val <= 0:
            sn_p80_d[idx] = False
            sn_flag_d[idx] = None
            continue

        universe_vals = list(date_universe.values())
        fire_sector = sector_map.get(ticker, "")

        # Sector-neutral ranking (M2: peer pool = universe tickers in same sector)
        # v1.2: use midrank (average-rank tie handling) instead of weak-inequality mean
        if fire_sector:
            sector_universe = {
                tkr: val for tkr, val in date_universe.items()
                if sector_map.get(tkr, "") == fire_sector
            }
            if len(sector_universe) >= 3:
                sector_vals = list(sector_universe.values())
                pctile = _midrank_percentile(sector_vals, fire_val)
                sn_p80_d[idx] = pctile >= _I3_PERCENTILE / 100.0
                sn_flag_d[idx] = True
                continue

        # Universe-wide fallback (v1.2: midrank)
        pctile = _midrank_percentile(universe_vals, fire_val)
        sn_p80_d[idx] = pctile >= _I3_PERCENTILE / 100.0
        sn_flag_d[idx] = False

    out_sn_p80 = pd.Series(sn_p80_d, name="ins_netusd_mcap_sn_p80").reindex(fires.index)
    out_sn_flag = pd.Series(sn_flag_d, name="ins_i3_sector_neutral").reindex(fires.index)
    out_i3_comp = pd.Series(i3_computable_d, name="ins_i3_computable").reindex(fires.index)
    return out_sn_p80, out_sn_flag, out_i3_comp, fallback_frac


# ---------------------------------------------------------------------------
# Main per-fire context builder
# ---------------------------------------------------------------------------

def build_context(
    fires: pd.DataFrame,
    panel: pd.DataFrame,
    closes: dict[str, pd.Series],
    sector_map: dict[str, str],
) -> pd.DataFrame:
    """Compute all per-fire insider context columns.

    All windows are filing_date-keyed (RUL-23). All insider windows use
    TRADING-DAY arithmetic (M1 fix): searchsorted on the ticker's price index
    when available, union calendar fallback otherwise. Post-entry column is
    descriptive only (pit_at_entry=false in meta).
    """
    fires = fires.copy()
    log.info("Building context for %d fires...", len(fires))

    # Build union calendar once (fallback when ticker's own price index absent)
    union_cal = _build_union_calendar(closes)
    log.info("  Union calendar: %d trading days (%s → %s)",
             len(union_cal),
             union_cal[0].date() if len(union_cal) else "n/a",
             union_cal[-1].date() if len(union_cal) else "n/a")

    # ------------------------------------------------------------------
    # Step 1: ins_computable — ticker in panel with ≥1 filing in 3y-td at t
    # (M1 fix: 3y-td via trading-day offset on ticker's price index)
    # ------------------------------------------------------------------
    log.info("  Computing ins_computable...")
    ticker_idx = _build_ticker_index(panel)
    computable: list[bool] = []
    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["date"])
        tp = ticker_idx.get(ticker)
        if tp is None:
            computable.append(False)
            continue
        # Use ticker's price index for trading-day offset; fall back to union cal
        price_idx = closes[ticker].index if ticker in closes else None
        t_3y = _td_offset(t, _COMPUTABLE_3Y_TD, price_idx, union_cal, direction=-1)
        has_filing = bool(
            ((tp["filing_date"] >= t_3y) & (tp["filing_date"] <= t)).any()
        )
        computable.append(has_filing)

    fires["ins_computable"] = computable
    log.info("  ins_computable: %d / %d fires have ≥1 filing", sum(computable), len(fires))

    # ------------------------------------------------------------------
    # Step 2: washout_flag
    # ------------------------------------------------------------------
    log.info("  Computing washout_flag...")
    fires["washout_flag"] = _build_washout_cache(fires, closes)
    n_washout = int(fires["washout_flag"].sum())
    log.info("  washout_flag: %d fires (%.1f%%)", n_washout, 100.0 * n_washout / max(len(fires), 1))

    # ------------------------------------------------------------------
    # Step 3: ins_buyers_45d — distinct buyers in [t-45td, t] by filing_date
    # (M1 fix: all windows use trading-day arithmetic via _td_offset)
    # ------------------------------------------------------------------
    log.info("  Computing ins_buyers_45d and cluster columns...")
    buyers_45d: list[int | None] = []
    buyers_20d: list[int | None] = []
    buyers_post15: list[int | None] = []

    for _, row in fires.iterrows():
        ticker = str(row["ticker"])
        t = pd.Timestamp(row["date"])
        tp = ticker_idx.get(ticker)
        if tp is None or not row["ins_computable"]:
            buyers_45d.append(None)
            buyers_20d.append(None)
            buyers_post15.append(None)
            continue

        # Use ticker's own price index for trading-day offsets (M1 fix)
        price_idx = closes[ticker].index if ticker in closes else None
        buys = tp[tp["code"] == "P"]

        # [t-45td, t] — filing_date ≤ t (PIT)
        t_45 = _td_offset(t, _CLUSTER_WINDOW_45, price_idx, union_cal, direction=-1)
        mask_45 = (buys["filing_date"] >= t_45) & (buys["filing_date"] <= t)
        buyers_45d.append(int(buys[mask_45]["rptownercik"].nunique()))

        # [t-20td, t] — PIT
        t_20 = _td_offset(t, _CLUSTER_WINDOW_20, price_idx, union_cal, direction=-1)
        mask_20 = (buys["filing_date"] >= t_20) & (buys["filing_date"] <= t)
        buyers_20d.append(int(buys[mask_20]["rptownercik"].nunique()))

        # (t, t+15td] — DESCRIPTIVE ONLY, NOT PIT
        t_p15 = _td_offset(t, _CLUSTER_POST15, price_idx, union_cal, direction=+1)
        mask_post = (buys["filing_date"] > t) & (buys["filing_date"] <= t_p15)
        buyers_post15.append(int(buys[mask_post]["rptownercik"].nunique()))

    fires["ins_buyers_45d"] = buyers_45d
    fires["_buyers_20d"] = buyers_20d
    fires["_buyers_post15"] = buyers_post15

    # ------------------------------------------------------------------
    # Step 4: I1 — ins_cluster_washout (washout_flag AND buyers_45d ≥ 2)
    # ------------------------------------------------------------------
    w = fires["washout_flag"].fillna(False)
    b45 = fires["ins_buyers_45d"]
    fires["ins_cluster_washout"] = (
        w & b45.notna() & (b45 >= _CLUSTER_MIN_BUYERS)
    )
    fires["ins_cluster_washout_3"] = (
        w & b45.notna() & (b45 >= _CLUSTER_MIN_BUYERS_3)
    )

    # ------------------------------------------------------------------
    # Step 5: I2 — ins_cluster_pre20 (buyers in [t-20, t] ≥ 2, PIT)
    # ------------------------------------------------------------------
    b20 = fires["_buyers_20d"]
    fires["ins_cluster_pre20"] = (
        b20.notna() & (b20 >= _CLUSTER_MIN_BUYERS)
    )

    # ------------------------------------------------------------------
    # Step 6: ins_cluster_post15 — DESCRIPTIVE ONLY (pit_at_entry=false)
    # Column comment embedded in output meta; marked not-PIT throughout.
    # ------------------------------------------------------------------
    fires["ins_cluster_post15"] = fires["_buyers_post15"]

    # ------------------------------------------------------------------
    # Step 7: I3 — ins_netusd_mcap_sn_p80
    # (M2 fix: universe base; m3 fix: PIT mcap)
    # ------------------------------------------------------------------
    log.info("  Computing I3 (net_usd_mcap sector-neutral pctile, universe base)...")
    # Load PIT shares panel if available (m3)
    shares_panel: pd.DataFrame | None = None
    _fundamentals_path = _DATA / "edgar" / "fundamentals_panel.parquet"
    if _fundamentals_path.exists():
        try:
            shares_panel = pd.read_parquet(
                _fundamentals_path, columns=["ticker", "shares", "asof_date"]
            )
            shares_panel["asof_date"] = pd.to_datetime(shares_panel["asof_date"])
            shares_panel = shares_panel.dropna(subset=["shares", "asof_date"]).sort_values("asof_date")
            log.info("  PIT shares panel loaded: %d rows", len(shares_panel))
        except Exception as exc:  # noqa: BLE001
            log.warning("  Could not load fundamentals_panel (will use close proxy): %s", exc)
            shares_panel = None
    else:
        log.info("  fundamentals_panel.parquet absent — using close-price mcap proxy")

    sn_p80, sn_flag, i3_comp, mcap_fallback_frac = _compute_i3_net_usd_mcap(
        fires, panel, closes, sector_map, union_cal, shares_panel
    )
    fires["ins_netusd_mcap_sn_p80"] = sn_p80
    fires["ins_i3_sector_neutral"] = sn_flag
    fires["ins_i3_computable"] = i3_comp
    log.info("  I3 mcap fallback fraction: %.1f%%", 100.0 * mcap_fallback_frac)

    # ------------------------------------------------------------------
    # Drop helper columns, keep spec columns only
    # ------------------------------------------------------------------
    drop_cols = [c for c in ["_buyers_20d", "_buyers_post15"] if c in fires.columns]
    fires = fires.drop(columns=drop_cols)

    # Store mcap_fallback_frac in attrs for the caller to retrieve
    fires.attrs["_mcap_fallback_frac"] = mcap_fallback_frac

    return fires


# ---------------------------------------------------------------------------
# Coverage / count report
# ---------------------------------------------------------------------------

def print_coverage_report(
    panel_name: str,
    result: pd.DataFrame,
    mcap_fallback_frac: float = float("nan"),
) -> dict[str, Any]:
    """Print and return coverage statistics."""
    total = len(result)
    n_computable = int(result["ins_computable"].sum())
    pct_computable = 100.0 * n_computable / max(total, 1)

    # Count positive fires for each form (computable fires only)
    comp = result[result["ins_computable"].fillna(False)]

    def count(col: str) -> int:
        s = comp[col] if col in comp.columns else pd.Series(dtype=bool)
        return int(s.fillna(False).sum())

    n_i1     = count("ins_cluster_washout")
    n_i1_3   = count("ins_cluster_washout_3")
    n_i2     = count("ins_cluster_pre20")
    n_i3     = count("ins_netusd_mcap_sn_p80")
    n_i3comp = int(result["ins_i3_computable"].fillna(False).sum()) if "ins_i3_computable" in result.columns else 0
    n_sn     = int(comp["ins_i3_sector_neutral"].fillna(False).sum()) if "ins_i3_sector_neutral" in comp.columns else 0

    print(f"\n{'='*70}")
    print(f"Panel: {panel_name.upper()}  [definition_version={_DEFINITION_VERSION}]")
    print(f"{'='*70}")
    print(f"Total fires:           {total:>8,}")
    print(f"ins_computable:        {n_computable:>8,}  ({pct_computable:.1f}%)")
    print(f"ins_i3_computable:     {n_i3comp:>8,}  ({100.0*n_i3comp/max(total,1):.1f}%)")
    print(f"I1 (≥2 buyers, wash):  {n_i1:>8,}  ({100.0*n_i1/max(total,1):.1f}%)")
    print(f"I1_3 (≥3 buyers):      {n_i1_3:>8,}  ({100.0*n_i1_3/max(total,1):.1f}%)")
    print(f"I2 (≥2 buyers pre20):  {n_i2:>8,}  ({100.0*n_i2/max(total,1):.1f}%)")
    print(f"I3 (SN net≥p80):       {n_i3:>8,}  ({100.0*n_i3/max(total,1):.1f}%)")
    print(f"I3 sector-neutral:     {n_sn:>8,}  ({100.0*n_sn/max(n_i3comp,1):.1f}% of i3-computable)")
    if not (isinstance(mcap_fallback_frac, float) and mcap_fallback_frac != mcap_fallback_frac):
        print(f"I3 mcap-fallback frac: {mcap_fallback_frac:>8.3f}  ({100.0*mcap_fallback_frac:.1f}% used close proxy)")
    print(f"post15 (descr.):       — (descriptive only, not PIT stratum)")
    print()

    # Per-era breakdown
    era_rows: list[dict[str, Any]] = []
    print(f"{'Era':<12} {'N':>7} {'Comp%':>7} {'I1':>7} {'I1_3':>7} {'I2':>7} {'I3':>7}")
    print("-" * 70)
    dates = pd.to_datetime(result["date"])
    for era_name, (era_start, era_end) in _PROGRAM_ERAS.items():
        era_mask = (dates >= era_start) & (dates <= era_end)
        era_fires = result[era_mask]
        if len(era_fires) == 0:
            continue
        era_comp = era_fires[era_fires["ins_computable"].fillna(False)]
        e_n = len(era_fires)
        e_comp_pct = 100.0 * len(era_comp) / max(e_n, 1)
        e_i1 = int(era_comp["ins_cluster_washout"].fillna(False).sum())
        e_i1_3 = int(era_comp["ins_cluster_washout_3"].fillna(False).sum())
        e_i2 = int(era_comp["ins_cluster_pre20"].fillna(False).sum())
        e_i3 = int(era_comp["ins_netusd_mcap_sn_p80"].fillna(False).sum())
        print(f"{era_name:<12} {e_n:>7,} {e_comp_pct:>6.1f}% {e_i1:>7,} {e_i1_3:>7,} {e_i2:>7,} {e_i3:>7,}")
        era_rows.append({
            "era": era_name,
            "n_fires": e_n,
            "pct_computable": round(e_comp_pct, 2),
            "n_i1": e_i1,
            "n_i1_3": e_i1_3,
            "n_i2": e_i2,
            "n_i3": e_i3,
        })

    print("=" * 70)

    return {
        "panel": panel_name,
        "total_fires": total,
        "n_computable": n_computable,
        "pct_computable": round(pct_computable, 2),
        "n_i1": n_i1,
        "n_i1_3": n_i1_3,
        "n_i2": n_i2,
        "n_i3": n_i3,
        "n_i3_computable": n_i3comp,
        "i3_sector_neutral_frac": round(n_sn / max(n_i3comp, 1), 4),
        "era_breakdown": era_rows,
    }


# ---------------------------------------------------------------------------
# Feature meta JSON (RUL-23 triples)
# ---------------------------------------------------------------------------

def _build_meta(
    deep_stats: dict,
    baskets_stats: dict,
    runtime_deep: float,
    runtime_baskets: float,
    mcap_fallback_frac: float = float("nan"),
) -> dict:
    return {
        "definition_version": _DEFINITION_VERSION,
        "definition_changelog": _DEFINITION_CHANGELOG,
        "built_date": pd.Timestamp.now().isoformat(),
        "frozen_thresholds": {
            "window_basis": "trading_days",
            "washout_lookback_td": _WASHOUT_LOOKBACK_TD,
            "washout_high_window_td": _WASHOUT_HIGH_WINDOW,
            "washout_threshold": _WASHOUT_THRESHOLD,
            "cluster_window_45_td": _CLUSTER_WINDOW_45,
            "cluster_window_20_td": _CLUSTER_WINDOW_20,
            "cluster_post15_td": _CLUSTER_POST15,
            "cluster_min_buyers_i1_i2": _CLUSTER_MIN_BUYERS,
            "cluster_min_buyers_i1_3": _CLUSTER_MIN_BUYERS_3,
            "i3_net_usd_months": _I3_NET_USD_MONTHS,
            "i3_percentile": _I3_PERCENTILE,
            "computable_3y_td": _COMPUTABLE_3Y_TD,
            "i3_universe_base": "form4_eligible_tickers_at_t",
            "i3_ranking_method": "midrank_self_inclusive_positive_gate",
            "i3_positive_gate": "net_usd_mcap_strictly_gt_0",
            "mcap_method": "pit_shares_x_close_with_fallback_to_close_proxy",
            "mcap_fallback_fraction": round(mcap_fallback_frac, 4) if not (
                isinstance(mcap_fallback_frac, float) and
                mcap_fallback_frac != mcap_fallback_frac
            ) else None,
        },
        "columns": {
            "ins_computable": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "Ticker present in Form-4 panel with ≥1 filing of any kind in trailing 3y-td at t. All windows are TRADING-DAY counts (v1.1). Computable_mask basis (Amendment 2 §C2).",
            },
            "ins_i3_computable": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "I3-specific computable flag: ticker is in the Form-4-eligible universe at t used for I3 percentile ranking (≥1 filing in trailing 3y-td AND has net_usd_6m and mcap data). Added in v1.1 (M2 fix).",
            },
            "washout_flag": {
                "source_event_date": "price_date",
                "known_date": "price_date",
                "pit_basis": "close_history_leq_t",
                "pit_at_entry": True,
                "description": "Min (close/rolling126d_high − 1) over [t-45td, t] ≤ −0.20. Uses strictly prior bars for the 126d high (no current-bar lookahead). 45td = trading days.",
            },
            "ins_buyers_45d": {
                "source_event_date": "trans_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "Distinct buyer CIKs (code=P) with filing_date in [t-45td, t]. 45td = trading days (v1.1 M1 fix; was calendar days in v1).",
            },
            "ins_cluster_washout": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "I1: washout_flag AND ins_buyers_45d ≥ 2. Both legs span 45 TRADING DAYS (v1.1 M1 fix). Threshold frozen at registration (RUL-26).",
            },
            "ins_cluster_washout_3": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "I1 sensitivity: washout_flag AND ins_buyers_45d ≥ 3 (RUL-26 pre-registered sensitivity). Both legs span 45 TRADING DAYS (v1.1).",
            },
            "ins_cluster_pre20": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": "I2 PIT stratum: distinct buyers in [t-20td, t] ≥ 2 (filing_date window). 20td = trading days (v1.1 M1 fix).",
            },
            "ins_cluster_post15": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "NOT_PIT_study_time_only",
                "pit_at_entry": False,
                "description": "DESCRIPTIVE ONLY — distinct buyers in (t, t+15td] by filing_date. 15td = trading days (v1.1). This is a STUDY-TIME DESCRIPTIVE, NOT a PIT stratum. NEVER use as a stratum in r1_estimate/grade_fires.",
            },
            "ins_netusd_mcap_sn_p80": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": (
                    "I3: trailing 6-month net_usd/mcap (FDR-survivor construction), "
                    "sector-neutral midrank percentile ≥ 80 at t. UNIVERSE BASE = all Form-4-eligible "
                    "tickers at t (v1.1 M2 fix; was co-firing tickers only in v1). "
                    "v1.2 fix: (a) fire must have net_usd_mcap > 0 (strict positive gate — "
                    "non-net-buyers are excluded, not ranked); (b) percentile uses midrank "
                    "(average-rank tie handling; self-inclusive pool) instead of weak-inequality "
                    "mean — eliminates zero-mass inflation where ~17% zero mass caused 61% of "
                    "zero-net-buy fires to flag >= p80. "
                    "mcap = PIT shares × close where shares available (fundamentals_panel.parquet); "
                    "falls back to close-price proxy (see mcap_fallback_fraction in meta). "
                    "CMP opportunistic filter EXCLUDED (negative-IC prior, RUL-26)."
                ),
            },
            "ins_i3_sector_neutral": {
                "source_event_date": "filing_date",
                "known_date": "filing_date",
                "pit_basis": "filing_date_leq_t",
                "pit_at_entry": True,
                "description": (
                    "Bool: True = sector-neutral midrank pctile used for I3 (≥3 sector peers "
                    "in UNIVERSE at t); False = universe-wide fallback. "
                    "None = fire excluded by positive gate (net_usd_mcap <= 0)."
                ),
            },
        },
        "panels": {
            "deep": {
                "runtime_seconds": round(runtime_deep, 1),
                **deep_stats,
            },
            "baskets": {
                "runtime_seconds": round(runtime_baskets, 1),
                **baskets_stats,
            },
        },
    }


# ---------------------------------------------------------------------------
# Panel runner
# ---------------------------------------------------------------------------

def run_panel(
    panel_name: str,
    fires_path: Path,
    closes: dict[str, pd.Series],
    panel: pd.DataFrame,
    sector_map: dict[str, str],
    out_path: Path,
    *,
    smoke: int | None = None,
) -> tuple[dict[str, Any], float]:
    """Build context for one panel; return (stats_dict, runtime_seconds)."""
    if not fires_path.exists():
        log.error("Fire tape not found: %s", fires_path)
        return {"error": f"fires not found: {fires_path}"}, 0.0

    fires = pd.read_parquet(fires_path)
    log.info("Panel %s: %d fires loaded", panel_name, len(fires))

    if smoke:
        fires = fires.head(smoke)
        log.info("Smoke mode: using first %d fires only", len(fires))

    t0 = time.time()
    result = build_context(fires, panel, closes, sector_map)
    elapsed = time.time() - t0

    mcap_fallback_frac: float = result.attrs.get("_mcap_fallback_frac", float("nan"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(out_path, index=False)
    log.info("Wrote %s (%d rows) in %.1fs", out_path, len(result), elapsed)

    stats = print_coverage_report(panel_name, result, mcap_fallback_frac)
    stats["mcap_fallback_frac"] = (
        round(mcap_fallback_frac, 4)
        if not (isinstance(mcap_fallback_frac, float) and mcap_fallback_frac != mcap_fallback_frac)
        else None
    )
    print(f"  Runtime: {elapsed:.1f}s")

    if elapsed > 1200 and not smoke:
        log.warning("Runtime %.1fs > 20 min warning threshold", elapsed)

    return stats, elapsed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Entry-Stack Amendment 2 T1a — insider fire context panel builder.",
    )
    parser.add_argument(
        "--panel", nargs="+", choices=["deep", "baskets"],
        default=None,
        help="Restrict to named panel(s); default runs all.",
    )
    parser.add_argument(
        "--smoke", type=int, default=None, metavar="N",
        help="Smoke mode: run on first N fires only (default: 500 if --smoke without value).",
    )
    parser.add_argument(
        "--smoke-default", action="store_true",
        help="Quick smoke: first 500 fires per panel.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    smoke_n: int | None = None
    if args.smoke_default:
        smoke_n = 500
    elif args.smoke is not None:
        smoke_n = args.smoke

    panels_to_run = args.panel or ["deep", "baskets"]

    # Load shared resources once
    log.info("Loading insider panel...")
    panel = _load_insider_panel()

    log.info("Loading sector map...")
    sector_map = _load_sector_map()

    panel_configs = []
    if "deep" in panels_to_run:
        log.info("Loading deep close prices...")
        closes_deep = _load_closes_deep()
        panel_configs.append(("deep", _FIRES_DEEP, closes_deep, _OUT_DEEP))
    if "baskets" in panels_to_run:
        log.info("Loading baskets close prices...")
        closes_baskets = _load_closes_baskets()
        panel_configs.append(("baskets", _FIRES_BASKETS, closes_baskets, _OUT_BASKETS))

    deep_stats: dict[str, Any] = {}
    baskets_stats: dict[str, Any] = {}
    runtime_deep = 0.0
    runtime_baskets = 0.0
    # mcap_fallback_frac from whichever panel ran last (deep preferred if both run)
    _mcap_fallback_frac: float = float("nan")

    for panel_name, fires_path, closes, out_path in panel_configs:
        stats, rt = run_panel(
            panel_name, fires_path, closes, panel, sector_map, out_path,
            smoke=smoke_n,
        )
        if panel_name == "deep":
            deep_stats, runtime_deep = stats, rt
            if stats.get("mcap_fallback_frac") is not None:
                _mcap_fallback_frac = float(stats["mcap_fallback_frac"])
        else:
            baskets_stats, runtime_baskets = stats, rt
            if (
                isinstance(_mcap_fallback_frac, float)
                and _mcap_fallback_frac != _mcap_fallback_frac  # still NaN
                and stats.get("mcap_fallback_frac") is not None
            ):
                _mcap_fallback_frac = float(stats["mcap_fallback_frac"])

    # Write meta JSON
    meta = _build_meta(
        deep_stats, baskets_stats, runtime_deep, runtime_baskets, _mcap_fallback_frac
    )
    _OUT_META.write_text(json.dumps(meta, indent=2, default=str))
    log.info("Wrote meta: %s", _OUT_META)

    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
