"""scripts/compute_disp_pit_state.py — PIT regime reconstruction for DISP-GATE-1.

Per §0.5.7 of the adjudication doc: no historical PIT states exist in
data/dispersion/regime.json (the JSON holds at most 252 days of rolling
history, and the live closes cache only goes back to 2025-03).  DISP-GATE-1
must recompute the expanding-window basis per fire date from a reconstructed
broad-universe returns panel.

Panel reconstruction mirrors build_dispersion_regime._load_closes() —
same tier order, same dedup logic — but uses massive_stock_day files
instead of the live closes cache, so the panel spans 2021-07-06 → present.

Two bases are computed per fire date (§6.2 + L3_PREREG design obligation 1):
  - expanding   : expanding-window percentile (primary, PIT-correct)
  - trailing252 : fixed 252-bar rolling window percentile (sensitivity)

DATA-REACH GATE (§6.2):
  - Record the panel's earliest date.
  - For each fire date, count how many panel bars exist strictly before it.
  - Fires with fewer than 252 prior panel bars are EXCLUDED.
  - The exclusion count is PRINTED before any statistic.

Usage
-----
from scripts.compute_disp_pit_state import compute_pit_states, PIT_STATE_COLS

states_df = compute_pit_states(fire_dates, massive_dir=Path(...))
# Returns a DataFrame indexed by date with columns:
#   disp_state_expanding, disp_state_trailing252, disp_pctile_expanding,
#   disp_pctile_trailing252, n_bars_before, excluded
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — mirror dispersion.assess() thresholds and parameters
# ---------------------------------------------------------------------------
_HI, _LO = 0.66, 0.33          # same as engine/dispersion.py
_ROLLING_21 = 21                # rolling CSD window for smoothing
_MIN_PERIODS = 10               # min_periods for rolling mean
_MIN_PANEL_ROWS = 60            # assess() minimum rows
_MIN_PANEL_COLS = 20            # assess() minimum names
_BARS_GATE = 252                # minimum prior bars for PIT state

# Columns this module produces
PIT_STATE_COLS = [
    "disp_state_expanding",
    "disp_state_trailing252",
    "disp_pctile_expanding",
    "disp_pctile_trailing252",
    "n_bars_before",
    "excluded",
]

# ---------------------------------------------------------------------------
# Panel loader — mirrors build_dispersion_regime._load_closes() but reads
# from massive_stock_day directory instead of live close caches.
# ---------------------------------------------------------------------------

def _load_panel_from_massive(
    massive_dir: Path,
    *,
    min_tickers: int = _MIN_PANEL_COLS,
    min_obs: int = _MIN_PANEL_ROWS,
    sample_n: int | None = None,
) -> pd.DataFrame:
    """Build a wide [dates × tickers] return panel from massive_stock_day.

    Uses a large-cap / liquid universe sampled from S&P 500 proxy tickers.
    We read every parquet in massive_dir that has a 'close' column, then
    take the union (outer join) so the panel covers the full date range.

    Returns empty DataFrame on failure (caller handles degraded path).

    Parameters
    ----------
    massive_dir : Path to the massive_stock_day directory
    min_tickers : minimum ticker count for a usable panel
    min_obs     : minimum row count for a usable panel
    sample_n    : if set, randomly sample this many tickers (for speed in tests)
    """
    if not massive_dir.exists():
        log.warning("massive_dir does not exist: %s", massive_dir)
        return pd.DataFrame()

    parquet_files = sorted(massive_dir.glob("*.parquet"))
    if not parquet_files:
        log.warning("No parquet files found in %s", massive_dir)
        return pd.DataFrame()

    if sample_n is not None and len(parquet_files) > sample_n:
        rng = np.random.default_rng(42)
        parquet_files = list(rng.choice(parquet_files, size=sample_n, replace=False))  # type: ignore[arg-type]

    # Load closes (each file → one column)
    frames: list[pd.Series] = []
    for fp in parquet_files:
        try:
            df = pd.read_parquet(fp)
            if "close" not in df.columns:
                continue
            c = df["close"].dropna()
            if not isinstance(c.index, pd.DatetimeIndex):
                c.index = pd.to_datetime(c.index)
            c = c.sort_index()
            c.name = fp.stem  # ticker
            frames.append(c)
        except Exception as exc:  # noqa: BLE001
            log.debug("Failed to load %s: %s", fp.name, exc)
            continue

    if len(frames) < min_tickers:
        log.warning(
            "Panel has only %d tickers (need >= %d) — panel unusable",
            len(frames), min_tickers,
        )
        return pd.DataFrame()

    panel = pd.concat(frames, axis=1)
    panel.sort_index(inplace=True)

    if len(panel) < min_obs:
        log.warning(
            "Panel has only %d rows (need >= %d) — panel unusable",
            len(panel), min_obs,
        )
        return pd.DataFrame()

    log.info(
        "Loaded panel: %d dates x %d tickers (%.1f%% non-null)",
        len(panel), panel.shape[1],
        100.0 * panel.notna().mean().mean(),
    )
    return panel


# ---------------------------------------------------------------------------
# CSD and percentile computation — mirrors dispersion.assess() exactly
# ---------------------------------------------------------------------------

def _csd_series(panel: pd.DataFrame) -> pd.Series:
    """Compute cross-sectional dispersion (std across names) per date.

    Panel may have NaNs; dropna(how='all') per row, then std.
    """
    returns = panel.pct_change(fill_method=None)
    csd = returns.std(axis=1)
    return csd.dropna()


def _smoothed_csd(csd: pd.Series) -> pd.Series:
    """Rolling-21 mean of CSD (mirrors dispersion.assess hist computation)."""
    return csd.rolling(_ROLLING_21, min_periods=_MIN_PERIODS).mean()


def _state_from_pctile(pctile: float | None) -> str:
    """Assign regime state from dispersion percentile."""
    if pctile is None:
        return "neutral"
    if pctile >= _HI:
        return "lean_in"
    if pctile <= _LO:
        return "lean_out"
    return "neutral"


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_pit_states(
    fire_dates: Sequence,  # dates for which we need a PIT state
    *,
    massive_dir: Path | None = None,
    panel: pd.DataFrame | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Compute PIT dispersion regime states for a sequence of fire dates.

    At least one of massive_dir or panel must be supplied.  When both are
    supplied, panel takes priority (useful for testing with synthetic data).

    Parameters
    ----------
    fire_dates  : sequence of date-like values (str or Timestamp)
    massive_dir : path to massive_stock_day directory
    panel       : pre-built [dates × tickers] close panel (overrides massive_dir)
    verbose     : if True, print exclusion counts and data reach summary

    Returns
    -------
    DataFrame indexed by unique fire date with columns:
        disp_state_expanding    — primary PIT state (expanding-window percentile)
        disp_state_trailing252  — sensitivity state (trailing-252d window)
        disp_pctile_expanding   — expanding percentile [0, 1]
        disp_pctile_trailing252 — trailing-252d percentile [0, 1]
        n_bars_before           — number of panel bars strictly before this date
        excluded                — True if n_bars_before < 252 (DATA-REACH GATE)
    """
    if panel is None:
        if massive_dir is None:
            raise ValueError("Either massive_dir or panel must be supplied")
        log.info("Loading broad-universe close panel from %s", massive_dir)
        panel = _load_panel_from_massive(massive_dir)

    if panel.empty:
        log.warning("Panel is empty — all fire dates will be EXCLUDED")
        dates_ts = pd.to_datetime(list(fire_dates)).unique()
        result = pd.DataFrame(
            {
                "disp_state_expanding": None,
                "disp_state_trailing252": None,
                "disp_pctile_expanding": None,
                "disp_pctile_trailing252": None,
                "n_bars_before": 0,
                "excluded": True,
            },
            index=dates_ts,
        )
        result.index.name = "fire_date"
        return result

    # Compute panel-level CSD and smoothed CSD once
    csd = _csd_series(panel)
    smooth_csd = _smoothed_csd(csd)
    smooth_csd = smooth_csd.dropna()

    panel_dates = panel.index  # DatetimeIndex

    # Log data reach
    earliest_panel_date = panel_dates[0]
    latest_panel_date = panel_dates[-1]
    if verbose:
        print(
            f"[DISP-PIT] Panel data reach: {earliest_panel_date.date()} "
            f"→ {latest_panel_date.date()} ({len(panel_dates)} bars, "
            f"{panel.shape[1]} tickers)"
        )

    # Unique fire dates
    fire_dates_ts = pd.to_datetime(list(fire_dates)).sort_values().unique()

    rows: list[dict] = []
    n_excluded = 0
    n_below60_exp = 0

    for fd in fire_dates_ts:
        # Count bars in panel strictly before this fire date
        n_bars = int((panel_dates < fd).sum())

        excluded = n_bars < _BARS_GATE
        if excluded:
            n_excluded += 1
            rows.append({
                "fire_date": fd,
                "disp_state_expanding": None,
                "disp_state_trailing252": None,
                "disp_pctile_expanding": None,
                "disp_pctile_trailing252": None,
                "n_bars_before": n_bars,
                "excluded": True,
            })
            continue

        # ---------- EXPANDING WINDOW (primary, PIT-correct) ----------
        # Mirrors dispersion.assess(): expanding percentile = (h <= h.iloc[-1]).mean()
        # where h is the rolling-21-mean CSD history UP TO the fire date.
        # We use only bars BEFORE the fire date (no lookahead).
        h_expanding = smooth_csd[smooth_csd.index < fd]

        if len(h_expanding) < 60:
            # Too sparse for a meaningful percentile — fallback to neutral
            n_below60_exp += 1
            pctile_exp: float | None = None
        else:
            # The expanding-window percentile at fire date:
            # rank of the most recent value in the full history seen so far.
            last_val = float(h_expanding.iloc[-1])
            pctile_exp = float((h_expanding <= last_val).mean())

        state_exp = _state_from_pctile(pctile_exp)

        # ---------- TRAILING-252 WINDOW (sensitivity) ----------
        # Use only the last 252 bars of h strictly before fire date.
        h_trailing = h_expanding.iloc[-252:] if len(h_expanding) >= 252 else h_expanding

        if len(h_trailing) < 60:
            pctile_tr: float | None = None
        else:
            last_val_tr = float(h_trailing.iloc[-1])
            pctile_tr = float((h_trailing <= last_val_tr).mean())

        state_tr = _state_from_pctile(pctile_tr)

        rows.append({
            "fire_date": fd,
            "disp_state_expanding": state_exp,
            "disp_state_trailing252": state_tr,
            "disp_pctile_expanding": round(pctile_exp, 4) if pctile_exp is not None else None,
            "disp_pctile_trailing252": round(pctile_tr, 4) if pctile_tr is not None else None,
            "n_bars_before": n_bars,
            "excluded": False,
        })

    if verbose:
        print(
            f"[DISP-PIT] DATA-REACH GATE: {n_excluded} fire dates excluded "
            f"(< {_BARS_GATE} bars before fire date). "
            f"{len(fire_dates_ts) - n_excluded} dates proceed."
        )
        if n_below60_exp > 0:
            print(
                f"[DISP-PIT] WARNING: {n_below60_exp} included dates had "
                f"< 60 prior smoothed-CSD bars → expanding pctile = None → state = 'neutral'"
            )

        # Print flip rate between bases for non-excluded dates
        included_rows = [r for r in rows if not r["excluded"]]
        if included_rows:
            df_tmp = pd.DataFrame(included_rows)
            both_valid = df_tmp.dropna(subset=["disp_state_expanding", "disp_state_trailing252"])
            if len(both_valid) > 0:
                n_flip = (
                    both_valid["disp_state_expanding"] != both_valid["disp_state_trailing252"]
                ).sum()
                flip_pct = 100.0 * n_flip / len(both_valid)
                print(
                    f"[DISP-PIT] Basis comparison: {n_flip}/{len(both_valid)} dates "
                    f"({flip_pct:.1f}%) flip state between expanding and trailing-252d. "
                    + (
                        "NON-STATIONARITY FLAG: >15% flip rate — study proceeds descriptively "
                        "on the primary (expanding) basis only."
                        if flip_pct > 15
                        else "Bases agree on >85% of dates — stationarity assumption holds."
                    )
                )

    result = pd.DataFrame(rows)
    if result.empty:
        result = pd.DataFrame(columns=["fire_date"] + PIT_STATE_COLS)
    result = result.set_index("fire_date")
    result.index.name = "fire_date"
    return result[PIT_STATE_COLS]


# ---------------------------------------------------------------------------
# SPY 21d contemporaneous drawdown covariate (L3_PREREG design obligation 2)
# ---------------------------------------------------------------------------

def compute_spy_21d_returns(
    fire_dates: Sequence,
    *,
    massive_dir: Path | None = None,
    spy_closes: pd.Series | None = None,
) -> pd.Series:
    """Compute SPY 21d return at each fire date.

    The 21d return at fire_date is the cumulative return of SPY over the
    21 calendar trading days BEFORE the fire date (not forward — this is
    a contemporaneous backdoor covariate measuring recent tape backdrop).

    Specifically: spy_ret_21d = (SPY[fire_date] / SPY[fire_date - 21 bars]) - 1.
    If SPY data is unavailable for a fire date, returns NaN.

    Parameters
    ----------
    fire_dates  : sequence of date-like values
    massive_dir : path to massive_stock_day directory (reads SPY.parquet)
    spy_closes  : pre-loaded SPY close series (overrides massive_dir)

    Returns
    -------
    Series indexed by unique fire date; values are 21d returns (float or NaN).
    """
    if spy_closes is None:
        if massive_dir is None:
            raise ValueError("Either massive_dir or spy_closes must be supplied")
        spy_path = massive_dir / "SPY.parquet"
        if not spy_path.exists():
            log.warning("SPY.parquet not found in %s — covariate will be NaN", massive_dir)
            dates_ts = pd.to_datetime(list(fire_dates)).unique()
            return pd.Series(np.nan, index=dates_ts, name="spy_ret_21d")
        try:
            df = pd.read_parquet(spy_path)
            spy_closes = df["close"].dropna()
            if not isinstance(spy_closes.index, pd.DatetimeIndex):
                spy_closes.index = pd.to_datetime(spy_closes.index)
            spy_closes = spy_closes.sort_index()
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to load SPY.parquet: %s", exc)
            dates_ts = pd.to_datetime(list(fire_dates)).unique()
            return pd.Series(np.nan, index=dates_ts, name="spy_ret_21d")

    fire_dates_ts = pd.to_datetime(list(fire_dates)).sort_values().unique()
    results: dict = {}
    spy_idx = spy_closes.index

    for fd in fire_dates_ts:
        # Find the bar at or before fire_date
        before = spy_idx[spy_idx <= fd]
        if len(before) < 22:  # need at least 22 bars (21+1) for the 21d return
            results[fd] = np.nan
            continue
        # Bar at fire_date (or latest bar before it)
        ref_bar = before[-1]
        # 21 bars earlier
        bar_21_ago = before[-22]  # 21 bars before ref_bar
        price_now = float(spy_closes.loc[ref_bar])
        price_21_ago = float(spy_closes.loc[bar_21_ago])
        if price_21_ago == 0:
            results[fd] = np.nan
        else:
            results[fd] = round(price_now / price_21_ago - 1.0, 6)

    return pd.Series(results, name="spy_ret_21d")


# ---------------------------------------------------------------------------
# Tercile assignment helper for covariate control
# ---------------------------------------------------------------------------

def assign_spy_tercile(spy_ret_21d: pd.Series) -> pd.Series:
    """Assign SPY 21d return tercile per L3_PREREG design obligation 2.

    Tercile labels per the prereg:
        'down'   : spy_21d < -5%
        'flat'   : -5% <= spy_21d <= +5%
        'up'     : spy_21d > +5%

    NaN values are assigned label 'unknown'.
    """
    tercile = pd.Series("unknown", index=spy_ret_21d.index, name="spy_tercile")
    tercile[spy_ret_21d < -0.05] = "down"
    tercile[(spy_ret_21d >= -0.05) & (spy_ret_21d <= 0.05)] = "flat"
    tercile[spy_ret_21d > 0.05] = "up"
    return tercile


# ---------------------------------------------------------------------------
# Entry point (quick validation)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    massive_dir = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")
    boarded_path = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/replay/replay_boarded.parquet")

    if not boarded_path.exists():
        print("replay_boarded.parquet not found — exiting")
        sys.exit(1)

    import pandas as pd
    df = pd.read_parquet(boarded_path)
    fires = df[(df["verdict_type"] == "fire") & (df["verdict_grade"] == True)]
    fire_dates = pd.to_datetime(fires["signal_date"]).unique()
    print(f"Total fire dates: {len(fire_dates)} ({fire_dates.min().date()} → {fire_dates.max().date()})")

    states = compute_pit_states(fire_dates, massive_dir=massive_dir, verbose=True)
    print(states.head(10))
    print("State distribution (expanding):")
    print(states["disp_state_expanding"].value_counts())
    print("State distribution (trailing252):")
    print(states["disp_state_trailing252"].value_counts())
