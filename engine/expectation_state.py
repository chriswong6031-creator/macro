"""engine/expectation_state.py — LT-2c: Per-stock expectation-state display block.

DISPLAY-ONLY — horizon_role='hold_thesis'. Every output field carries
_display_only=True and _horizon_role='hold_thesis' (LH-R1 firewall;
G1-DEFERRED ruling 2026-07-06). MUST NOT feed board ordering, alert triage,
top-setups gates, or push floor.

Computes, for the LIVE universe at build time (PIT-as-of-today), per ticker:
  last_event_date   : most recent EDGAR 8-K 2.02 filing_date visible today
  sue_latest        : PIT SUE at today (engine/sue.py construction)
  sue_streak        : consecutive quarters with d_q > 0 (cap 8), at today
  pead_drift_20d    : cumulative stock-minus-market return from last event
                      +1 session up to min(event+20 sessions, today)
                      [DISCLOSED DIVERGENCE from prereg ED-3: benchmark is SPY
                      not the EW sector basket; sector basket deferred (heavy).
                      Display labels say 'vs market'/'stock-minus-market'.
                      _benchmark='SPY' carried in each chip dict.]
  bad_news_absorption : binary, market-relative variant of ED-4 definition
                      from EXPECT_DRIFT_FAMILY_PREREG.md §2 — same logic but
                      momentum condition (cond-3) uses SPY not sector basket
  good_news_hold    : binary, ED-5 definition from EXPECT_DRIFT_FAMILY_PREREG.md §2
                      (no benchmark dependency; unaffected by SPY divergence)

References:
  Pre-registration: research/long_hold/EXPECT_DRIFT_FAMILY_PREREG.md §2
  Program: research/long_hold/LT_EXTERNAL_FOUNDATION_ADJUDICATION.md (LT-2c)
  SUE construction: engine/sue.py (matched identically here)

Performance law: load eps_quarterly/earnings_8k_dates ONCE; vectorize per-ticker
lookups; load price parquets lazily (only for tickers with a qualifying event).
Full-universe pass runs in O(seconds) — NOT on the render hot-path but acceptable
alongside stock_fundamentals.panels().

Callers:
  engine/stock_fundamentals.panels() — wired as `expectation_state` key in the
  per-ticker panel dict, consumed by site/stockdata/<TICKER>.json.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (matching EXPECT_DRIFT_FAMILY_PREREG.md §1 definitions)
# ---------------------------------------------------------------------------
_EVENT_WINDOW_DAYS = 120      # max calendar days before today for a qualifying event
_TOL_YEAR_AGO_DAYS = 50       # calendar tolerance for year-ago quarter match (SUE)
_SUE_MIN_DIFFS = 4            # minimum seasonal diffs to compute SUE
_SUE_VOL_WINDOW = 8           # trailing diffs used for σ (matches sue.py vol_window)
_PEAD_MIN_SESSIONS = 5        # ED-3: minimum elapsed sessions for pead_drift
_PEAD_MAX_SESSIONS = 20       # ED-3: max sessions window
_BNA_POST_SESSIONS = 10       # ED-4: post-event sessions to scan for new lows
_BNA_PRE_SESSIONS = 63        # ED-4: pre-event sessions for min-close baseline
_BNA_MOMENTUM_SESSIONS = 5    # ED-4: sessions for stock-vs-benchmark momentum check
_GNH_REACT_MIN = 0.02         # ED-5: minimum next-session reaction (+2%)
_GNH_HOLD_SESSIONS = 10       # ED-5: sessions to confirm close >= E(f)+1 close


# ---------------------------------------------------------------------------
# SUE helpers — match engine/sue.py _seasonal_diffs exactly
# ---------------------------------------------------------------------------

def _seasonal_diffs(
    period_ends: np.ndarray,
    eps_vals: np.ndarray,
    tol_days: int = _TOL_YEAR_AGO_DAYS,
) -> list[tuple[pd.Timestamp, float]]:
    """[(period_end, d_q = eps_q - eps_{q-4})] for all quarters with a year-ago match.

    Identical to engine/sue.py _seasonal_diffs and
    scripts/research/build_expect_drift_panel._seasonal_diffs_pit.
    """
    out: list[tuple[pd.Timestamp, float]] = []
    pe = period_ends.astype("datetime64[D]")
    for i in range(len(pe)):
        target = pe[i] - np.timedelta64(365, "D")
        best_j, best_gap = -1, tol_days + 1
        for j in range(i):
            gap = abs(int((pe[j] - target) / np.timedelta64(1, "D")))
            if gap <= best_gap:
                best_gap, best_j = gap, j
        if best_j >= 0 and best_gap <= tol_days:
            out.append((pd.Timestamp(pe[i]), float(eps_vals[i] - eps_vals[best_j])))
    return out


def _sue_features_for_ticker(
    ticker_eps: pd.DataFrame,
    asof: pd.Timestamp,
) -> dict[str, Any]:
    """Compute PIT-gated SUE features for one ticker at asof.

    Returns dict with: sue_latest, sue_streak (both None when insufficient data).
    """
    result: dict[str, Any] = {"sue_latest": None, "sue_streak": None}

    # PIT: only rows with asof_date <= asof
    visible = ticker_eps[ticker_eps["asof_date"] <= asof].sort_values("period_end")
    if len(visible) < _SUE_MIN_DIFFS + 2:
        return result

    diffs = _seasonal_diffs(
        visible["period_end"].values,
        visible["eps_q"].values,
    )
    if len(diffs) < _SUE_MIN_DIFFS:
        return result

    recent_diffs = [d for _pe, d in diffs[-_SUE_VOL_WINDOW:]]
    sd = float(pd.Series(recent_diffs).std())
    if not sd or np.isnan(sd) or sd == 0:
        return result

    last_pe, last_d = diffs[-1]
    result["sue_latest"] = float(last_d / sd)

    # sue_streak: consecutive quarters with d_q > 0, counting backward from latest
    streak = 0
    for _pe, d in reversed(diffs):
        if d > 0:
            streak += 1
        else:
            break
    result["sue_streak"] = min(int(streak), 8)

    return result


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------

def _load_close(ticker: str, yahoo_dir: Path) -> pd.Series | None:
    """Load per-ticker close from yahoo/ parquet. Returns None when absent."""
    p = yahoo_dir / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if "close" not in df.columns:
            return None
        s = df["close"].dropna().sort_index()
        return s if len(s) >= 2 else None
    except Exception:  # noqa: BLE001
        return None


def _load_spy_close(yahoo_dir: Path) -> pd.Series | None:
    """Load SPY close series (used as market benchmark fallback)."""
    return _load_close("SPY", yahoo_dir)


# ---------------------------------------------------------------------------
# Feature helpers (ED-3, ED-4, ED-5 per prereg §2)
# ---------------------------------------------------------------------------

def _pead_drift(
    close: pd.Series,
    benchmark_close: pd.Series | None,
    event_date: pd.Timestamp,
    today: pd.Timestamp,
) -> float | None:
    """ED-3 analog for the LIVE display context.

    Cumulative stock-minus-benchmark return from E(f)+1 session to
    min(E(f)+20 sessions, today).  Requires >= 5 elapsed sessions.

    today acts as the upper bound (inclusive — we can see today's close
    for display purposes; PIT logic here is: as-of-today means today's
    data is available).
    """
    if close is None or close.empty:
        return None
    idx = close.index

    # first bar strictly after event_date
    start_pos = int(np.searchsorted(idx.values, np.datetime64(event_date), side="right"))
    if start_pos >= len(idx):
        return None

    # upper bound: include sessions up to and including today (display view)
    end_pos_exclusive = int(
        np.searchsorted(idx.values, np.datetime64(today + pd.Timedelta(days=1)), side="left")
    )
    end_pos = min(start_pos + _PEAD_MAX_SESSIONS, end_pos_exclusive)

    n_sessions = end_pos - start_pos
    if n_sessions < _PEAD_MIN_SESSIONS:
        return None

    window = close.iloc[start_pos:end_pos]
    if len(window) < _PEAD_MIN_SESSIONS:
        return None

    # Guard against zero/NaN at window boundaries
    start_val = float(window.iloc[0])
    end_val = float(window.iloc[-1])
    if not start_val or np.isnan(start_val) or not end_val or np.isnan(end_val):
        return None

    stock_ret = end_val / start_val - 1.0

    # Benchmark: align on same date range
    if benchmark_close is not None and not benchmark_close.empty:
        bm_idx = benchmark_close.index
        bm_start = int(
            np.searchsorted(bm_idx.values, np.datetime64(idx[start_pos]), side="left")
        )
        bm_end = int(
            np.searchsorted(bm_idx.values, np.datetime64(idx[end_pos - 1]), side="right")
        ) - 1
        if (
            0 <= bm_start < len(bm_idx)
            and 0 <= bm_end < len(bm_idx)
            and bm_end >= bm_start
        ):
            bm_start_val = float(benchmark_close.iloc[bm_start])
            bm_end_val = float(benchmark_close.iloc[bm_end])
            if bm_start_val > 0 and not np.isnan(bm_start_val) and not np.isnan(bm_end_val):
                bm_ret = bm_end_val / bm_start_val - 1.0
                return float(stock_ret - bm_ret)

    return float(stock_ret)


def _bad_news_absorption(
    close: pd.Series,
    benchmark_close: pd.Series | None,
    event_date: pd.Timestamp,
    d_q: float | None,
) -> bool | None:
    """ED-4: bad_news_absorption for the LIVE display.

    Conditions (all required):
      1. d_q < 0 at E(f)
      2. No close in the 10 sessions after E(f) below the minimum close
         of the 63 sessions before E(f)
      3. Stock-minus-benchmark return over E(f)+1..E(f)+5 >= 0

    Returns True/False/None (None when insufficient data).
    No PIT cap needed here since event_date is already <= today.
    """
    if close is None or close.empty or d_q is None:
        return None

    # Condition 1
    if d_q >= 0:
        return False

    idx = close.index
    # event position: last bar at or before event_date
    event_pos = int(np.searchsorted(idx.values, np.datetime64(event_date), side="right")) - 1
    if event_pos < 0 or event_pos >= len(idx):
        return None

    # Pre-event min over 63 sessions (including event_pos itself)
    pre_start = max(0, event_pos - _BNA_PRE_SESSIONS + 1)
    pre_window = close.iloc[pre_start:event_pos + 1]
    if len(pre_window) < 5:
        return None
    pre_min = float(pre_window.min())

    # Post-event 10 sessions
    post_start = event_pos + 1
    post_end = min(post_start + _BNA_POST_SESSIONS, len(idx))
    if post_end <= post_start:
        return None
    post_window = close.iloc[post_start:post_end]

    # Condition 2: no close below pre_min
    if float(post_window.min()) < pre_min:
        return False

    # Condition 3: stock-vs-benchmark momentum over E(f)+1..E(f)+5
    mom_end = min(post_start + _BNA_MOMENTUM_SESSIONS, len(idx))
    if mom_end <= post_start:
        return None
    mom_window = close.iloc[post_start:mom_end]
    if len(mom_window) < 1:
        return None

    event_close = float(close.iloc[event_pos])
    if not event_close or np.isnan(event_close):
        return None

    stock_mom = float(mom_window.iloc[-1]) / event_close - 1.0

    if benchmark_close is not None and not benchmark_close.empty:
        bm_idx = benchmark_close.index
        bm_s = int(np.searchsorted(bm_idx.values, np.datetime64(idx[event_pos]), side="right")) - 1
        bm_e = int(np.searchsorted(bm_idx.values, np.datetime64(idx[mom_end - 1]), side="right")) - 1
        if (
            0 <= bm_s < len(bm_idx)
            and 0 <= bm_e < len(bm_idx)
            and bm_e >= bm_s
        ):
            bm_sv = float(benchmark_close.iloc[bm_s])
            bm_ev = float(benchmark_close.iloc[bm_e])
            if bm_sv > 0 and not np.isnan(bm_sv) and not np.isnan(bm_ev):
                excess_mom = stock_mom - (bm_ev / bm_sv - 1.0)
                return bool(excess_mom >= 0)

    return bool(stock_mom >= 0)


def _good_news_hold(
    close: pd.Series,
    event_date: pd.Timestamp,
    d_q: float | None,
) -> bool | None:
    """ED-5: good_news_hold for the LIVE display.

    Conditions (all required):
      1. d_q > 0 at E(f)
      2. close(E(f)+1) / close(E(f)) - 1 >= +2%
      3. close(E(f)+10) >= close(E(f)+1)

    Returns True/False/None (None when insufficient data).
    """
    if close is None or close.empty or d_q is None:
        return None

    # Condition 1
    if d_q <= 0:
        return False

    idx = close.index
    event_pos = int(np.searchsorted(idx.values, np.datetime64(event_date), side="right")) - 1
    if event_pos < 0 or event_pos >= len(idx):
        return None

    # E(f)+1
    if event_pos + 1 >= len(idx):
        return None
    c_event = float(close.iloc[event_pos])
    c_next = float(close.iloc[event_pos + 1])
    if not c_event or np.isnan(c_event) or np.isnan(c_next):
        return None

    # Condition 2
    if c_next / c_event - 1.0 < _GNH_REACT_MIN:
        return False

    # Condition 3: E(f)+10
    pos10 = event_pos + _GNH_HOLD_SESSIONS
    if pos10 >= len(idx):
        return None
    c_10 = float(close.iloc[pos10])
    if np.isnan(c_10):
        return None

    return bool(c_10 >= c_next)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def _dq_at_event(
    ticker_eps: pd.DataFrame,
    asof_date: pd.Timestamp,
) -> float | None:
    """Get the d_q (seasonal surprise) from the most recent visible EPS quarter
    as of asof_date (today).  Matches build_expect_drift_panel._dq_at_event:
    visibility gate uses fire_date (today), not event_date; threshold is
    _SUE_MIN_DIFFS + 1 (>=5 visible rows required).
    """
    visible = ticker_eps[ticker_eps["asof_date"] <= asof_date].sort_values("period_end")
    if len(visible) < _SUE_MIN_DIFFS + 1:
        return None
    diffs = _seasonal_diffs(
        visible["period_end"].values,
        visible["eps_q"].values,
    )
    if not diffs:
        return None
    return diffs[-1][1]


def expectation_states(
    today: date | None = None,
    *,
    data_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Compute per-stock expectation-state display blocks for the LIVE universe.

    Loads eps_quarterly.parquet and earnings_8k_dates.parquet ONCE; loads
    per-ticker price parquets lazily (only tickers with qualifying events).
    Full-universe pass is O(seconds).

    Parameters
    ----------
    today:
        Reference date (PIT as-of). Defaults to date.today().
    data_dir:
        Override for the data directory. Defaults to lib.config.data_dir().

    Returns
    -------
    {ticker: expectation_state_dict}

    Every dict carries:
        last_event_date        str | None    ISO "YYYY-MM-DD"
        sue_latest             float | None
        sue_streak             int | None
        pead_drift_20d         float | None  (market-relative: benchmark=SPY)
        bad_news_absorption    bool | None   (momentum cond uses SPY, not sector)
        good_news_hold         bool | None
        _horizon_role          "hold_thesis"
        _display_only          True
        _version               "v1"
        _benchmark             "SPY"         (disclosed: prereg ED-3/ED-4 define sector-relative)

    Firewall: the returned dicts MUST NOT be consumed by any entry-stack
    scored surface (LH-R1).
    """
    from lib import config as _cfg  # noqa: PLC0415 — deferred for import-time cleanliness

    ref_date = today or date.today()
    ref_ts = pd.Timestamp(ref_date)
    if data_dir is None:
        data_dir = _cfg.data_dir()
    data_dir = Path(data_dir)

    # --- Load core tables once ---
    eps_path = data_dir / "edgar" / "eps_quarterly.parquet"
    e8k_path = data_dir / "edgar" / "earnings_8k_dates.parquet"

    if not eps_path.exists() or not e8k_path.exists():
        log.warning("expectation_states: missing parquets (eps=%s, e8k=%s) — skipping",
                    eps_path.exists(), e8k_path.exists())
        return {}

    try:
        eps_df = pd.read_parquet(eps_path)
        eps_df["period_end"] = pd.to_datetime(eps_df["period_end"])
        eps_df["asof_date"] = pd.to_datetime(eps_df["asof_date"])
        e8k_df = pd.read_parquet(e8k_path)
        # filing_date is a string "YYYY-MM-DD" in this parquet
        e8k_df["filing_date"] = pd.to_datetime(e8k_df["filing_date"])
    except Exception as exc:  # noqa: BLE001
        log.warning("expectation_states: parquet load error (%s) — skipping", exc)
        return {}

    if eps_df.empty or e8k_df.empty:
        return {}

    # --- Yahoo price directory ---
    yahoo_dir = data_dir / "yahoo"
    spy_close = _load_spy_close(yahoo_dir)

    # --- Reference event E(f) per ticker: latest 8K filing_date
    #     that is <= (today - 1 BDay) AND within 120 calendar days of today ---
    cutoff_high = (ref_ts - pd.tseries.offsets.BDay(1)).normalize()
    cutoff_low = (ref_ts - pd.Timedelta(days=_EVENT_WINDOW_DAYS)).normalize()

    # Build per-ticker group for events (filtered to qualifying window)
    e8k_window = e8k_df[
        (e8k_df["filing_date"] >= cutoff_low) &
        (e8k_df["filing_date"] <= cutoff_high)
    ].copy()

    # Latest qualifying event per ticker
    if e8k_window.empty:
        latest_events: dict[str, pd.Timestamp] = {}
    else:
        latest_events = (
            e8k_window.groupby("ticker")["filing_date"]
            .max()
            .to_dict()
        )

    # Index eps by ticker for fast lookups
    eps_by_ticker: dict[str, pd.DataFrame] = {
        tic: grp.reset_index(drop=True)
        for tic, grp in eps_df.groupby("ticker")
    }

    # --- Build output ---
    out: dict[str, dict[str, Any]] = {}
    n_with_event = 0
    n_price_loaded = 0

    for ticker, ticker_eps in eps_by_ticker.items():
        # SUE features: always computed when eps data is available (no event required)
        sue_features = _sue_features_for_ticker(ticker_eps, asof=ref_ts)

        # Event-anchored features: only when a qualifying E(f) exists
        event_date: pd.Timestamp | None = latest_events.get(ticker)
        last_event_date: str | None = None
        pead_drift: float | None = None
        bna: bool | None = None
        gnh: bool | None = None

        if event_date is not None:
            n_with_event += 1
            last_event_date = event_date.strftime("%Y-%m-%d")

            # Load price data for event-anchored features
            close = _load_close(ticker, yahoo_dir)
            if close is not None:
                n_price_loaded += 1
                # Use SPY as benchmark (sector benchmark not available here without
                # the heavy membership.json EW-basket build; SPY is the §1 fallback
                # when sector basket is unavailable — benchmark='market' stamp)
                benchmark = spy_close

                # d_q as of today (ref_ts) — PIT visibility is fire_date not event_date
                # per prereg §2 and build_expect_drift_panel._dq_at_event(fire_date)
                dq = _dq_at_event(ticker_eps, ref_ts)

                pead_drift = _pead_drift(close, benchmark, event_date, ref_ts)
                bna = _bad_news_absorption(close, benchmark, event_date, dq)
                gnh = _good_news_hold(close, event_date, dq)

        # Only emit a chip when we have at least one non-None field (beyond firewall stamps)
        has_any = (
            sue_features.get("sue_latest") is not None
            or sue_features.get("sue_streak") is not None
            or last_event_date is not None
        )
        if not has_any:
            continue

        chip: dict[str, Any] = {
            "last_event_date": last_event_date,
            "sue_latest": sue_features["sue_latest"],
            "sue_streak": sue_features["sue_streak"],
            "pead_drift_20d": pead_drift,
            "bad_news_absorption": bna,
            "good_news_hold": gnh,
            "_horizon_role": "hold_thesis",
            "_display_only": True,
            "_version": "v1",
            # Disclosed divergence from prereg ED-3/ED-4: benchmark is SPY (market)
            # not the EW sector basket.  Prereg §1 defines sector-relative; sector basket
            # build is deferred (heavy membership.json dependency).  pead_drift_20d and
            # bad_news_absorption momentum condition are market-relative variants for all
            # sector-covered names.  Display labels already say 'vs market'/'stock-minus-market'.
            "_benchmark": "SPY",
        }
        # Cast numpy scalars to native Python (json.dumps safety)
        for k, v in chip.items():
            if k.startswith("_"):
                continue
            if isinstance(v, (np.integer,)):
                chip[k] = int(v)
            elif isinstance(v, (np.floating,)):
                chip[k] = float(v) if not np.isnan(v) else None  # type: ignore[assignment]
            elif isinstance(v, float) and np.isnan(v):
                chip[k] = None

        out[ticker] = chip

    log.info(
        "expectation_states: %d tickers built | %d with qualifying event "
        "| %d prices loaded | ref=%s",
        len(out), n_with_event, n_price_loaded, ref_date,
    )
    return out
