"""Oracle Reversion-Capture + Drawdown-Asymmetry Screener.

Standalone analysis tool — prints a report and, unless --no-trial-ledger is
passed, appends one row per compound to the reversion trial ledger
(reversion_trial_ledger.jsonl alongside the compounds registry).  This ledger
satisfies W3_SPEC §2 "every screen appends to the trial ledger — mining legal
because counted."  Does NOT touch the tier-1 trial_ledger.jsonl (the 63d
promotion pipeline ledger) or the registry.

METRIC DEFINITION (per entry, window W sessions, time-exit E sessions)
-----------------------------------------------------------------------
From exec date (= next close after trigger t):

  MFE   = max(lvl[s] / lvl[exec] - 1)  over next W sessions   (up-bounce)
  MAE   = min(lvl[s] / lvl[exec] - 1)  over next W sessions   (worst dd)
  ret_exit = lvl[exec+E] / lvl[exec] - 1  (absolute time-exit return)

Exit modes
----------
  time        (default) Fixed E-session exit as above.
  stochrsi2d  Exit on first daily bar (after MIN_HOLD=3 sessions from exec)
              where 2-bar StochRSI %K crosses BELOW %D, capped at 40 sessions.
              ret_exit = price return exec → exit date.

Regime tag (from node's panel row at trigger date t):
  risk_off if spy_above_200d == 0 OR vix_pctile >= 0.70
  else risk_on

Per-compound aggregates
-----------------------
  n               total mature entries
  mean_ret_exit   mean absolute time-exit return
  WR              win-rate = frac(ret_exit > 0)
  mean_MFE        mean maximum-favourable-excursion
  mean_MAE        mean maximum-adverse-excursion  (negative number)
  asym            mean_MFE / |mean_MAE|  (higher is better; upside vs downside)

All six metrics also reported split by regime (risk_on / risk_off).

USAGE
-----
  # Single compound from registry
  python -m scripts.oracle_reversion_screen --compound A1 \\
      --data-dir /path/to/data

  # All compounds in registry
  python -m scripts.oracle_reversion_screen --all-pending \\
      --data-dir /path/to/data --window 25 --exit 21

  # Inline rule (JSON) — no registry entry needed
  python -m scripts.oracle_reversion_screen \\
      --inline-rule '{"col":"washout_w","op":"gt","value":0}' \\
      --inline-id bare_washout \\
      --data-dir /path/to/data

  # Gauntlet mode: run all 6 PASS/FAIL legs on a compound
  python -m scripts.oracle_reversion_screen --gauntlet --compound A15 \\
      --data-dir /path/to/data

  # 2D-StochRSI momentum-top exit
  python -m scripts.oracle_reversion_screen --compound A15 \\
      --exit-mode stochrsi2d --data-dir /path/to/data

INLINE FALLBACK COMPOUNDS (A15, bare_washout)
---------------------------------------------
If the requested compound id is not in the registry, the tool defines it
inline:
  A15 = {"all":[{"col":"washout_w","op":"gt","value":0},
                {"episode_event":{"direction":"out","tier":"onset",
                                  "complex_scope":"opposite",
                                  "within_sessions":20,"min_count":2}}]}
  bare_washout = {"col":"washout_w","op":"gt","value":0}
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("oracle_reversion_screen")

# ---------------------------------------------------------------------------
# Exit-mode type alias
# ---------------------------------------------------------------------------

ExitMode = Literal["time", "stochrsi2d"]

# Constants for StochRSI 2D exit
_STOCHRSI2D_MIN_HOLD: int = 3   # sessions before exit is allowed
_STOCHRSI2D_MAX_HOLD: int = 40  # sessions cap

# ---------------------------------------------------------------------------
# Inline fallback compounds (used when id absent from registry)
# ---------------------------------------------------------------------------

_INLINE_COMPOUNDS: dict[str, dict] = {
    "A15": {
        "id": "A15",
        "name": "Washout + opposite-complex cascade (A15)",
        "universe": {"tier": "s"},
        "entry_rule": {
            "all": [
                {"col": "washout_w", "op": "gt", "value": 0},
                {
                    "episode_event": {
                        "direction": "out",
                        "tier": "onset",
                        "complex_scope": "opposite",
                        "within_sessions": 20,
                        "min_count": 2,
                    }
                },
            ]
        },
    },
    "bare_washout": {
        "id": "bare_washout",
        "name": "Bare washout (washout_w > 0)",
        "universe": {"tier": "s"},
        "entry_rule": {"col": "washout_w", "op": "gt", "value": 0},
    },
}


# ---------------------------------------------------------------------------
# Data loading (reuse oracle_screen's functions)
# ---------------------------------------------------------------------------

def _load_panel(data_dir: Path, tier: str) -> pd.DataFrame:
    from scripts.oracle_screen import _load_panel as _lp
    return _lp(data_dir, tier)


def _load_episodes(data_dir: Path, tier: str) -> pd.DataFrame:
    from scripts.oracle_screen import _load_episodes as _le
    return _le(data_dir, tier)


def _load_spy(data_dir: Path) -> pd.Series | None:
    from scripts.oracle_screen import _load_spy as _ls
    return _ls(data_dir)


def _load_rotation_groups(data_dir: Path) -> dict:
    from scripts.oracle_screen import _load_rotation_groups as _lrg
    return _lrg(data_dir)


# ---------------------------------------------------------------------------
# Regime tag helper
# ---------------------------------------------------------------------------

def _regime_at(row: pd.Series) -> str:
    """Return 'risk_off' or 'risk_on' from a panel row at trigger date t."""
    spy_above = row.get("spy_above_200d", np.nan)
    vix_pct = row.get("vix_pctile", np.nan)
    if not np.isnan(spy_above) and spy_above == 0:
        return "risk_off"
    if not np.isnan(vix_pct) and vix_pct >= 0.70:
        return "risk_off"
    return "risk_on"


# ---------------------------------------------------------------------------
# 2D-StochRSI exit helper
# ---------------------------------------------------------------------------

def _build_stochrsi_2d_exit_index(
    lvl: pd.Series,
    all_dates: pd.DatetimeIndex,
) -> dict[int, int]:
    """Pre-compute the 2D-StochRSI exit position for every possible exec_pos.

    For each exec_pos, the exit is the first daily position >= exec_pos +
    _STOCHRSI2D_MIN_HOLD where the 2D-bar StochRSI %K crosses below %D, capped
    at exec_pos + _STOCHRSI2D_MAX_HOLD.  Returns a dict mapping exec_pos -> exit_pos.

    The 2D bars are non-overlapping 2-session bars computed on the node's
    cumulative price level.  StochRSI K/D is computed on those bars, then
    forward-filled to daily.
    """
    from research.signal_engine.confluence import stoch_rsi_kd

    n = len(all_dates)
    if n < 10:
        return {}

    # Resample daily close to non-overlapping 2-session bars.
    # Use position-based grouping so that bar i covers sessions [2i, 2i+1].
    # We use the pandas integer-position trick: groupby(pos // 2).last()
    # This is deterministic and anchored at session 0, not at a calendar date.
    close_vals = lvl.values  # numpy array
    bar_count = n // 2  # number of complete 2-session bars
    if bar_count < 20:
        # Not enough bars to warm up StochRSI
        return {}

    bar_closes = np.array(
        [close_vals[2 * i + 1] for i in range(bar_count)]
    )
    # Use integer index for the bar series (bar number = i)
    bar_idx = np.arange(bar_count)
    bar_series = pd.Series(bar_closes, index=bar_idx, dtype=float)

    try:
        k_bar, d_bar = stoch_rsi_kd(bar_series)
    except Exception:  # noqa: BLE001
        return {}

    # Forward-fill K and D onto daily positions.
    # Bar i covers daily positions [2i, 2i+1]; its label date is position 2i+1.
    # Each daily position j sees the LAST COMPLETED bar whose end-position <= j.
    # Last completed bar for daily position j: bar_i = (j - 1) // 2 when j >= 1
    # (bar 0 completes at pos 1, bar 1 at pos 3, etc.)
    k_daily_arr = np.full(n, np.nan)
    d_daily_arr = np.full(n, np.nan)

    k_bar_arr = k_bar.values
    d_bar_arr = d_bar.values

    for j in range(1, n):
        bar_i = (j - 1) // 2  # last completed bar index
        if bar_i < len(k_bar_arr):
            k_daily_arr[j] = k_bar_arr[bar_i]
            d_daily_arr[j] = d_bar_arr[bar_i]

    # Detect K-crosses-below-D: K < D AND prev_K >= prev_D
    # crossunder[j] = True if k[j] < d[j] and k[j-1] >= d[j-1]
    crossunder = np.zeros(n, dtype=bool)
    for j in range(1, n):
        kj = k_daily_arr[j]
        dj = d_daily_arr[j]
        kp = k_daily_arr[j - 1]
        dp = d_daily_arr[j - 1]
        if np.isnan(kj) or np.isnan(dj) or np.isnan(kp) or np.isnan(dp):
            continue
        if kj < dj and kp >= dp:
            crossunder[j] = True

    # Build exit_pos lookup for each exec_pos
    exit_map: dict[int, int] = {}
    for exec_pos in range(n):
        min_exit = exec_pos + _STOCHRSI2D_MIN_HOLD
        max_exit = exec_pos + _STOCHRSI2D_MAX_HOLD
        if max_exit >= n:
            max_exit = n - 1
        if min_exit >= n:
            # Cannot exit within data range
            continue

        # Find first crossunder in [min_exit, max_exit]
        found = -1
        for j in range(min_exit, max_exit + 1):
            if j < n and crossunder[j]:
                found = j
                break
        if found == -1:
            # No cross: exit at cap
            found = min(max_exit, n - 1)

        exit_map[exec_pos] = found

    return exit_map


# ---------------------------------------------------------------------------
# Core metric computation (per entry) — REUSABLE HELPER
# ---------------------------------------------------------------------------

def _per_entry_rows(
    entry_dates: dict[str, pd.DatetimeIndex],
    panel: pd.DataFrame,
    window: int,
    exit_sessions: int,
    exit_mode: ExitMode = "time",
) -> list[dict]:
    """Compute per-entry MFE/MAE/ret_exit/regime rows for all nodes.

    This is the SINGLE SOURCE for per-entry metric computation; both the
    screen path and --gauntlet call this helper.

    Parameters
    ----------
    entry_dates : dict mapping node -> DatetimeIndex of trigger dates
    panel       : multi-indexed (node, date) panel DataFrame with 'ret' column
    window      : MFE/MAE window in sessions (always 25 sessions regardless of exit_mode)
    exit_sessions : sessions for time-exit (used only when exit_mode == 'time')
    exit_mode   : 'time' (fixed sessions) or 'stochrsi2d' (momentum-top exit)

    Returns
    -------
    list of dicts with keys:
      node, trigger_date, exec_date, MFE, MAE, ret_exit, regime,
      hold_sessions (only meaningful for stochrsi2d; = exit_sessions for time)
    """
    rows: list[dict] = []

    for node, dates in entry_dates.items():
        try:
            npn = panel.xs(node, level="node")
        except KeyError:
            continue

        if "ret" not in npn.columns:
            continue

        ret_series = npn["ret"].sort_index()
        lvl = (1 + ret_series.fillna(0)).cumprod()
        all_dates = ret_series.index  # sorted DatetimeIndex

        # Pre-compute 2D StochRSI exit map if needed (once per node)
        stochrsi_exit_map: dict[int, int] = {}
        if exit_mode == "stochrsi2d":
            stochrsi_exit_map = _build_stochrsi_2d_exit_index(lvl, all_dates)

        for trigger_t in dates:
            # Execution: next close after trigger
            future = all_dates[all_dates > trigger_t]
            if len(future) == 0:
                continue
            exec_date = future[0]
            exec_pos = all_dates.searchsorted(exec_date, side="left")

            # Outcome window (MFE/MAE): always window sessions regardless of exit_mode
            end_pos = exec_pos + window
            if end_pos >= len(all_dates):
                continue  # not mature

            exec_price = lvl.iat[exec_pos]
            if exec_price == 0 or np.isnan(exec_price):
                continue

            window_prices = lvl.iloc[exec_pos + 1 : exec_pos + window + 1]
            window_rets = window_prices / exec_price - 1

            mfe = float(window_rets.max())
            mae = float(window_rets.min())

            # Exit price depends on exit_mode
            if exit_mode == "time":
                exit_pos = exec_pos + exit_sessions
                if exit_pos >= len(all_dates):
                    continue  # exit not yet reached
                exit_price = lvl.iat[exit_pos]
                if exit_price == 0 or np.isnan(exit_price):
                    continue
                ret_exit = float(exit_price / exec_price - 1)
                hold = exit_sessions
            elif exit_mode == "stochrsi2d":
                if exec_pos not in stochrsi_exit_map:
                    continue  # insufficient data for this exec
                exit_pos = stochrsi_exit_map[exec_pos]
                if exit_pos >= len(all_dates) or exit_pos <= exec_pos:
                    continue
                exit_price = lvl.iat[exit_pos]
                if exit_price == 0 or np.isnan(exit_price):
                    continue
                ret_exit = float(exit_price / exec_price - 1)
                hold = exit_pos - exec_pos
            else:
                raise ValueError(f"Unknown exit_mode: {exit_mode!r}")

            # Regime: read from trigger row (t, not exec)
            if trigger_t in npn.index:
                regime = _regime_at(npn.loc[trigger_t])
            else:
                # Use nearest preceding row
                preceding = npn.index[npn.index <= trigger_t]
                if len(preceding) == 0:
                    regime = "unknown"
                else:
                    regime = _regime_at(npn.loc[preceding[-1]])

            rows.append(
                {
                    "node": node,
                    "trigger_date": trigger_t,
                    "exec_date": exec_date,
                    "MFE": mfe,
                    "MAE": mae,
                    "ret_exit": ret_exit,
                    "regime": regime,
                    "hold_sessions": hold,
                }
            )

    return rows


def _compute_entry_metrics(
    entry_dates: dict[str, pd.DatetimeIndex],
    panel: pd.DataFrame,
    window: int,
    exit_sessions: int,
    exit_mode: ExitMode = "time",
) -> pd.DataFrame:
    """Compute MFE / MAE / ret_exit / regime for each entry across all nodes.

    Returns a DataFrame with columns:
      node, trigger_date, exec_date, MFE, MAE, ret_exit, regime, hold_sessions

    Entries whose outcome window (exec_date + window) is beyond the data end
    are dropped (not mature).
    """
    rows = _per_entry_rows(entry_dates, panel, window, exit_sessions, exit_mode)

    if not rows:
        return pd.DataFrame(
            columns=["node", "trigger_date", "exec_date",
                     "MFE", "MAE", "ret_exit", "regime", "hold_sessions"]
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Aggregate stats
# ---------------------------------------------------------------------------

def _agg_stats(df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate MFE/MAE/ret_exit/WR/asym from an entries dataframe."""
    if df.empty:
        return {
            "n": 0, "mean_ret_exit": np.nan, "WR": np.nan,
            "mean_MFE": np.nan, "mean_MAE": np.nan, "asym": np.nan,
        }
    n = len(df)
    mean_ret_exit = float(df["ret_exit"].mean())
    wr = float((df["ret_exit"] > 0).mean())
    mean_mfe = float(df["MFE"].mean())
    mean_mae = float(df["MAE"].mean())
    abs_mae = abs(mean_mae)
    asym = float(mean_mfe / abs_mae) if abs_mae > 1e-9 else np.nan
    return {
        "n": n,
        "mean_ret_exit": mean_ret_exit,
        "WR": wr,
        "mean_MFE": mean_mfe,
        "mean_MAE": mean_mae,
        "asym": asym,
    }


# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------

def _pct(v: float | None) -> str:
    if v is None or np.isnan(v):
        return "n/a"
    return f"{v*100:+.2f}%"


def _fmt(v: float | None, decimals: int = 2) -> str:
    if v is None or np.isnan(v):
        return "n/a"
    return f"{v:.{decimals}f}"


# ---------------------------------------------------------------------------
# W4.b — Power analysis: MDE@80% + UNDERPOWERED-ACCRUING class
# ---------------------------------------------------------------------------

def _mde_at_80pct(n: int, sigma: float, alpha: float = 0.05) -> float | None:
    """Minimum detectable effect at 80% power (α=0.05, normal approximation).

    Formula (one-sample, one-sided, comparing mean vs 0):
        MDE = (z_alpha + z_power) * sigma / sqrt(n)
    where z_alpha = 1.645 (one-sided α=0.05), z_power = 0.842 (80% power).

    This is the smallest true mean ret_exit that this sample size would detect
    with 80% power at α=0.05.

    Per W4_SPEC.md §W4.b: 'α=0.05, normal approx from observed per-entry σ and n'.
    Reporting ONLY — gates are untouched.

    Returns None if n <= 0 or sigma is non-finite.
    """
    if n <= 0:
        return None
    if sigma is None or not np.isfinite(sigma) or sigma <= 0:
        return None
    # z_alpha = 1.645 (one-sided 5%); z_power = 0.842 (80% power)
    z_alpha: float = 1.645
    z_power: float = 0.842
    return (z_alpha + z_power) * sigma / np.sqrt(n)


def _is_underpowered_accruing(
    stats: dict,
    sigma: float | None,
    alpha: float = 0.05,
) -> bool:
    """Return True if this compound leg is UNDERPOWERED-ACCRUING.

    UNDERPOWERED-ACCRUING (W4.b definition):
      - Leg FAILS on CI/placebo grounds
      - All point estimates are in the PASSING direction
      - Power < 50% at the observed effect (i.e. the sample is too small to
        reliably detect even the observed effect)

    'Point estimates in passing direction' means:
      - mean_ret_exit > 0
      - WR > 0 (above zero)
      - asym > 0 (upside > downside)

    'Power < 50%' uses the observed mean_ret_exit as the hypothesized effect:
      achieved_power = P(z > z_alpha - effect/se) where se = sigma/sqrt(n)
      < 0.5 when effect/se < z_alpha, i.e. the standardized effect < 1.645.

    Reporting ONLY — this class does NOT change gate verdicts.
    """
    n = stats.get("n", 0)
    wr = stats.get("WR")
    mean_ret = stats.get("mean_ret_exit")
    asym_v = stats.get("asym")

    if n <= 0:
        return False

    # All point estimates must be in the passing direction (trending toward the
    # FROZEN gate thresholds — consistent with eventually clearing the gate, not
    # merely non-negative).  PREREG gate bars: WR>=0.62, asym>=1.5, ret>=+1.0%.
    # Comparing against gate thresholds prevents genuinely-mediocre signals
    # (sub-threshold WR/asym) from being mislabelled UNDERPOWERED-ACCRUING.
    _GATE_WR: float = 0.62    # FROZEN: ORACLE_REVERSION_GATE_PREREG.md Leg 2
    _GATE_ASYM: float = 1.5   # FROZEN: ORACLE_REVERSION_GATE_PREREG.md Leg 3
    _GATE_RET: float = 0.01   # FROZEN: ORACLE_REVERSION_GATE_PREREG.md Leg 4 (+1.0%)

    wr_passing = (wr is not None and not np.isnan(wr) and wr >= _GATE_WR)
    ret_passing = (mean_ret is not None and not np.isnan(mean_ret) and mean_ret >= _GATE_RET)
    asym_passing = (asym_v is None or np.isnan(asym_v) or asym_v >= _GATE_ASYM)

    if not (wr_passing and ret_passing and asym_passing):
        return False

    # Power < 50% at the observed effect
    if sigma is None or not np.isfinite(sigma) or sigma <= 0 or mean_ret is None:
        return False

    se = sigma / np.sqrt(n)
    if se <= 0:
        return False

    # achieved_power ~ Phi(effect/se - z_alpha); < 50% when effect/se < z_alpha
    z_alpha: float = 1.645
    standardized = float(mean_ret) / se
    return standardized < z_alpha  # power < 50%


def _print_compound_report(
    compound_id: str,
    name: str,
    all_stats: dict,
    risk_on_stats: dict,
    risk_off_stats: dict,
    window: int,
    exit_sessions: int,
    exit_mode: ExitMode = "time",
    mean_hold: float | None = None,
) -> None:
    w = 70
    print()
    print("=" * w)
    print(f"  {compound_id}  {name}")
    mode_label = f"exit_mode={exit_mode}"
    if exit_mode == "time":
        print(f"  window={window} sessions, exit={exit_sessions} sessions (absolute returns)")
    else:
        hold_str = f", mean_hold={mean_hold:.1f}s" if mean_hold is not None else ""
        print(f"  window={window} sessions, {mode_label}{hold_str} (absolute returns)")
    print("=" * w)

    def _row(label: str, s: dict) -> None:
        print(
            f"  {label:<12}  "
            f"n={s['n']:<6}  "
            f"ret_exit={_pct(s['mean_ret_exit'])}  "
            f"WR={_fmt(s['WR'], 3)}  "
            f"MFE={_pct(s['mean_MFE'])}  "
            f"MAE={_pct(s['mean_MAE'])}  "
            f"asym={_fmt(s['asym'])}"
        )

    _row("all-regime", all_stats)
    _row("risk_on", risk_on_stats)
    _row("risk_off", risk_off_stats)
    print()


# ---------------------------------------------------------------------------
# GAUNTLET: 6-leg PASS gate
# ---------------------------------------------------------------------------

_GAUNTLET_TIER_SPLITS: dict[str, str] = {
    "s": "2019-12-31",
    "m": "2023-12-31",
}
_DEFAULT_TIER_SPLIT: str = "2019-12-31"


def _is_risk_off_date(panel_row: pd.Series) -> bool:
    """Return True if the panel row represents a risk_off date.

    Mirrors the same definition used in _regime_at:
      risk_off if spy_above_200d == 0 OR vix_pctile >= 0.70
    """
    spy_above = panel_row.get("spy_above_200d", np.nan)
    vix_pct = panel_row.get("vix_pctile", np.nan)
    if not np.isnan(float(spy_above)) and float(spy_above) == 0:
        return True
    if not np.isnan(float(vix_pct)) and float(vix_pct) >= 0.70:
        return True
    return False


def _gauntlet_placebo_regime_matched(
    entries_df: pd.DataFrame,
    panel: pd.DataFrame,
    window: int,
    exit_sessions: int,
    exit_mode: ExitMode,
    operating_regime: str,
    n_draws: int = 500,
    rng_seed: int = 42,
) -> tuple[float, float]:
    """Leg 6’ (single-regime path): regime-matched timing placebo.

    Like _gauntlet_placebo but restricts each node's placebo pool to dates
    where that node was in the OPERATING regime.  This removes regime-beta
    from the placebo — the signal must beat random WITHIN-regime timing.

    operating_regime : 'risk_off' or 'risk_on'
    Returns (real_mean, pctile95).
    """
    rng = np.random.default_rng(rng_seed)
    real_mean = float(entries_df["ret_exit"].mean())

    node_pool: dict[str, np.ndarray] = {}
    node_entry_counts: dict[str, int] = {}

    for node, grp in entries_df.groupby("node"):
        node_entry_counts[node] = len(grp)

        try:
            npn = panel.xs(node, level="node")
        except KeyError:
            continue

        if "ret" not in npn.columns:
            continue

        ret_series = npn["ret"].sort_index()
        lvl = (1 + ret_series.fillna(0)).cumprod()
        all_dates = ret_series.index
        n = len(all_dates)

        # Pre-compute stochrsi exit map if needed
        stochrsi_exit_map: dict[int, int] = {}
        if exit_mode == "stochrsi2d":
            stochrsi_exit_map = _build_stochrsi_2d_exit_index(lvl, all_dates)

        # Build a boolean mask: True where this date is in the operating regime.
        # npn is sorted by date index; we check each date using _is_risk_off_date.
        op_arr = np.zeros(n, dtype=bool)
        for i, dt in enumerate(all_dates):
            if dt in npn.index:
                row = npn.loc[dt]
                is_off = _is_risk_off_date(row)
                op_arr[i] = (is_off if operating_regime == "risk_off" else not is_off)

        outcomes: list[float] = []
        for exec_pos in range(n):
            # Only include positions that are in the operating regime
            if not op_arr[exec_pos]:
                continue

            # Check MFE/MAE window maturity
            if exec_pos + window >= n:
                continue

            exec_price = lvl.iat[exec_pos]
            if exec_price == 0 or np.isnan(exec_price):
                continue

            if exit_mode == "time":
                exit_pos = exec_pos + exit_sessions
                if exit_pos >= n:
                    continue
                exit_price = lvl.iat[exit_pos]
                if exit_price == 0 or np.isnan(exit_price):
                    continue
                outcomes.append(float(exit_price / exec_price - 1))
            elif exit_mode == "stochrsi2d":
                if exec_pos not in stochrsi_exit_map:
                    continue
                exit_pos = stochrsi_exit_map[exec_pos]
                if exit_pos >= n or exit_pos <= exec_pos:
                    continue
                exit_price = lvl.iat[exit_pos]
                if exit_price == 0 or np.isnan(exit_price):
                    continue
                outcomes.append(float(exit_price / exec_price - 1))

        if outcomes:
            node_pool[node] = np.array(outcomes, dtype=float)

    if not node_pool:
        return real_mean, np.nan

    # Run n_draws placebo simulations
    draw_means: list[float] = []
    for _ in range(n_draws):
        total_sum = 0.0
        total_n = 0
        for node, pool in node_pool.items():
            k = node_entry_counts.get(node, 0)
            if k == 0 or len(pool) == 0:
                continue
            sampled = rng.choice(pool, size=k, replace=True)
            total_sum += float(sampled.sum())
            total_n += k
        if total_n > 0:
            draw_means.append(total_sum / total_n)

    if not draw_means:
        return real_mean, np.nan

    pctile95 = float(np.percentile(draw_means, 95))
    return real_mean, pctile95


def _gauntlet_placebo(
    entries_df: pd.DataFrame,
    panel: pd.DataFrame,
    window: int,
    exit_sessions: int,
    exit_mode: ExitMode,
    n_draws: int = 500,
    rng_seed: int = 42,
) -> tuple[float, float]:
    """Leg 6: timing placebo (standard / dual-regime path).

    Per node, build the pool of ALL realizable ret_exit outcomes for that node
    (every calendar date in the node's panel that can support a full exit window)
    and sample count-matched draws.  Returns (real_mean, pctile95) where
    pctile95 is the 95th percentile of draw-means across n_draws draws.

    The placebo tests whether the TIMING of entries (not their mere existence)
    contributes to the mean return.
    """
    rng = np.random.default_rng(rng_seed)
    real_mean = float(entries_df["ret_exit"].mean())

    # Build per-node pools of realizable outcomes
    node_pool: dict[str, np.ndarray] = {}
    node_entry_counts: dict[str, int] = {}

    for node, grp in entries_df.groupby("node"):
        node_entry_counts[node] = len(grp)

        try:
            npn = panel.xs(node, level="node")
        except KeyError:
            continue

        if "ret" not in npn.columns:
            continue

        ret_series = npn["ret"].sort_index()
        lvl = (1 + ret_series.fillna(0)).cumprod()
        all_dates = ret_series.index
        n = len(all_dates)

        # Pre-compute stochrsi exit map if needed
        stochrsi_exit_map: dict[int, int] = {}
        if exit_mode == "stochrsi2d":
            stochrsi_exit_map = _build_stochrsi_2d_exit_index(lvl, all_dates)

        outcomes: list[float] = []
        for exec_pos in range(n):
            # Check MFE/MAE window maturity
            if exec_pos + window >= n:
                continue

            exec_price = lvl.iat[exec_pos]
            if exec_price == 0 or np.isnan(exec_price):
                continue

            if exit_mode == "time":
                exit_pos = exec_pos + exit_sessions
                if exit_pos >= n:
                    continue
                exit_price = lvl.iat[exit_pos]
                if exit_price == 0 or np.isnan(exit_price):
                    continue
                outcomes.append(float(exit_price / exec_price - 1))
            elif exit_mode == "stochrsi2d":
                if exec_pos not in stochrsi_exit_map:
                    continue
                exit_pos = stochrsi_exit_map[exec_pos]
                if exit_pos >= n or exit_pos <= exec_pos:
                    continue
                exit_price = lvl.iat[exit_pos]
                if exit_price == 0 or np.isnan(exit_price):
                    continue
                outcomes.append(float(exit_price / exec_price - 1))

        if outcomes:
            node_pool[node] = np.array(outcomes, dtype=float)

    if not node_pool:
        return real_mean, np.nan

    # Run n_draws placebo simulations
    draw_means: list[float] = []
    for _ in range(n_draws):
        total_sum = 0.0
        total_n = 0
        for node, pool in node_pool.items():
            k = node_entry_counts.get(node, 0)
            if k == 0 or len(pool) == 0:
                continue
            sampled = rng.choice(pool, size=k, replace=True)
            total_sum += float(sampled.sum())
            total_n += k
        if total_n > 0:
            draw_means.append(total_sum / total_n)

    if not draw_means:
        return real_mean, np.nan

    pctile95 = float(np.percentile(draw_means, 95))
    return real_mean, pctile95


# ---------------------------------------------------------------------------
# W4.b — kill_requeue writer
# ---------------------------------------------------------------------------

def _write_kill_requeue(
    compound_id: str,
    data_dir: Path,
    n_at_kill: int,
    point_estimates: dict,
    asof: str,
) -> None:
    """Append a row to data/oracle/reversion_kill_requeue.jsonl.

    Per W4_SPEC.md §W4.b:
    - append-only, keep-first by compound_id::killed_at
    - every UNDERPOWERED-ACCRUING fail writes a row
    - requeue_at_n = 2 × n_at_kill (operator must re-screen at 2× the sample)

    NEVER auto-rescreens; this is a reminder only.
    """
    path = data_dir / "oracle" / "reversion_kill_requeue.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    # Keep-first: do not write if this compound already has an entry
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
                if existing.get("compound_id") == compound_id:
                    log.debug(
                        "kill_requeue: %s already has an entry (keep-first law) — skip",
                        compound_id,
                    )
                    return
            except Exception:  # noqa: BLE001
                pass

    row = {
        "compound_id": compound_id,
        "killed_at_asof": asof,
        "n_at_kill": n_at_kill,
        "point_estimates": point_estimates,
        "requeue_at_n": 2 * n_at_kill,
        "note": (
            "UNDERPOWERED-ACCRUING fail. A re-screen at requeue_at_n is a NEW "
            "counted trial (counted-trials law). NEVER auto-rescreens."
        ),
    }
    with path.open("a") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    log.info(
        "kill_requeue: wrote %s (n_at_kill=%d, requeue_at_n=%d)",
        compound_id, n_at_kill, 2 * n_at_kill,
    )


def run_gauntlet(
    compound: dict,
    entries_df: pd.DataFrame,
    panel: pd.DataFrame,
    window: int,
    exit_sessions: int,
    exit_mode: ExitMode,
    data_dir: Path | None = None,
) -> bool:
    """Run the full 6-leg PASS gate on a compound.

    Amendment 1 (frozen 2026-07-05): if the minority regime has < 30 entries,
    takes the SINGLE-REGIME PATH — Leg 4' and Leg 6' (regime-matched placebo)
    replace Leg 4 and Leg 6 for that compound.  Dual-regime compounds (both
    regimes >= 30 entries) take the STANDARD PATH unchanged.

    Prints per-leg PASS/FAIL + numbers; returns True if ALL legs pass.
    """
    compound_id = compound.get("id", "?")
    tier = compound.get("universe", {}).get("tier", "s")

    print()
    print("=" * 70)
    print(f"  GAUNTLET REPORT — {compound_id}  (exit_mode={exit_mode})")
    print("=" * 70)

    if entries_df.empty:
        print("  [ALL LEGS] FAIL — no entries")
        print()
        print("  *** REVERSION GAUNTLET FAIL ***")
        print()
        return False

    all_stats = _agg_stats(entries_df)
    risk_on_stats = _agg_stats(entries_df[entries_df["regime"] == "risk_on"])
    risk_off_stats = _agg_stats(entries_df[entries_df["regime"] == "risk_off"])

    # --- Single-regime detection (Amendment 1) ---
    n_on = risk_on_stats["n"]
    n_off = risk_off_stats["n"]
    _SINGLE_REGIME_THRESHOLD = 30
    if n_on < _SINGLE_REGIME_THRESHOLD or n_off < _SINGLE_REGIME_THRESHOLD:
        # Single-regime path: minority < 30
        if n_on <= n_off:
            operating_regime = "risk_off"
            operating_stats = risk_off_stats
            n_operating = n_off
        else:
            operating_regime = "risk_on"
            operating_stats = risk_on_stats
            n_operating = n_on
        minority_n = min(n_on, n_off)
        single_regime_path = True
        print(
            f"  PATH: SINGLE-REGIME (minority_n={minority_n} < {_SINGLE_REGIME_THRESHOLD})"
            f" — operating_regime={operating_regime}, n_operating={n_operating}"
        )
    else:
        single_regime_path = False
        operating_regime = None
        operating_stats = None
        n_operating = None
        print(f"  PATH: STANDARD dual-regime (n_on={n_on}, n_off={n_off})")

    # --- Leg 1: n >= 100 (unchanged in both paths) ---
    n = all_stats["n"]
    leg1 = n >= 100
    print(f"  Leg 1  n={n} >= 100:                {'PASS' if leg1 else 'FAIL'}")

    # --- Leg 2: WR >= 0.62 (unchanged in both paths) ---
    wr = all_stats["WR"]
    leg2 = not np.isnan(wr) and wr >= 0.62
    print(f"  Leg 2  WR={wr:.3f} >= 0.62:           {'PASS' if leg2 else 'FAIL'}")

    # --- Leg 3: asym >= 1.5 (unchanged in both paths) ---
    asym = all_stats["asym"]
    leg3 = not np.isnan(asym) and asym >= 1.5
    print(f"  Leg 3  asym={asym:.3f} >= 1.5:         {'PASS' if leg3 else 'FAIL'}")

    # --- Leg 4 / Leg 4' ---
    ret_exit_all = all_stats["mean_ret_exit"]
    ret_on = risk_on_stats["mean_ret_exit"]
    ret_off = risk_off_stats["mean_ret_exit"]

    if single_regime_path:
        # Leg 4': ret_exit >= 1% overall AND ret_exit > 0 in OPERATING regime
        #          AND n_operating >= 100. Empty/minority regime is EXEMPT.
        assert operating_stats is not None and n_operating is not None
        ret_operating = operating_stats["mean_ret_exit"]
        leg4_main = not np.isnan(ret_exit_all) and ret_exit_all >= 0.01
        leg4_op = not np.isnan(ret_operating) and ret_operating > 0
        leg4_n_op = n_operating >= 100
        leg4 = leg4_main and leg4_op and leg4_n_op
        print(
            f"  Leg 4' ret_exit={_pct(ret_exit_all)} >= +1.0%"
            f" AND {operating_regime}_ret={_pct(ret_operating)}>0"
            f" AND n_{operating_regime}={n_operating}>=100"
            f"  => {'PASS' if leg4 else 'FAIL'}"
        )
    else:
        # Standard Leg 4: ret_exit >= 1% AND > 0 in BOTH regimes
        leg4_main = not np.isnan(ret_exit_all) and ret_exit_all >= 0.01
        leg4_on = not np.isnan(ret_on) and ret_on > 0
        leg4_off = not np.isnan(ret_off) and ret_off > 0
        leg4 = leg4_main and leg4_on and leg4_off
        print(
            f"  Leg 4  ret_exit={_pct(ret_exit_all)} >= +1.0% "
            f"AND on={_pct(ret_on)}>0 AND off={_pct(ret_off)}>0:  "
            f"{'PASS' if leg4 else 'FAIL'}"
        )

    # --- Leg 5: OOS holdout (unchanged in both paths) ---
    split_str = _GAUNTLET_TIER_SPLITS.get(tier, _DEFAULT_TIER_SPLIT)
    split_date = pd.Timestamp(split_str)

    dev_df = entries_df[entries_df["entry_date"] <= split_date] if "entry_date" in entries_df.columns else entries_df[entries_df["trigger_date"] <= split_date]
    hold_df = entries_df[entries_df["trigger_date"] > split_date]

    dev_stats = _agg_stats(dev_df)
    hold_stats = _agg_stats(hold_df)

    hold_n = hold_stats["n"]
    hold_wr = hold_stats["WR"]
    hold_ret = hold_stats["mean_ret_exit"]
    dev_ret = dev_stats["mean_ret_exit"]

    # Leg 5 conditions
    leg5_n = hold_n >= 100
    leg5_wr = not np.isnan(hold_wr) and hold_wr >= 0.58
    leg5_sign = (
        not np.isnan(hold_ret) and not np.isnan(dev_ret)
        and np.sign(hold_ret) == np.sign(dev_ret)
    )
    leg5 = leg5_n and leg5_wr and leg5_sign
    print(
        f"  Leg 5  OOS holdout (split={split_str}):"
        f" holdout_n={hold_n} >= 100: {'Y' if leg5_n else 'N'},"
        f" WR={hold_wr:.3f} >= 0.58: {'Y' if leg5_wr else 'N'},"
        f" sign match (dev_ret={_pct(dev_ret)}, hold_ret={_pct(hold_ret)}): {'Y' if leg5_sign else 'N'}"
        f"  => {'PASS' if leg5 else 'FAIL'}"
    )

    # --- Leg 6 / Leg 6': timing placebo (p < 0.05) ---
    if single_regime_path:
        assert operating_regime is not None
        log.info(
            "Running Leg 6' regime-matched placebo (500 draws, regime=%s) — this may take ~30s...",
            operating_regime,
        )
        real_mean, pctile95 = _gauntlet_placebo_regime_matched(
            entries_df, panel, window, exit_sessions, exit_mode,
            operating_regime=operating_regime,
        )
        placebo_label = f"Leg 6' Regime-matched placebo ({operating_regime} only, 500 draws)"
    else:
        log.info("Running Leg 6 timing placebo (500 draws) — this may take ~30s...")
        real_mean, pctile95 = _gauntlet_placebo(
            entries_df, panel, window, exit_sessions, exit_mode
        )
        placebo_label = "Leg 6  Timing placebo (500 draws)"

    if np.isnan(pctile95):
        leg6 = False
        p_note = "n/a (could not build placebo pool)"
    else:
        leg6 = real_mean > pctile95
        p_note = f"real={_pct(real_mean)} > p95={_pct(pctile95)}"

    print(
        f"  {placebo_label}: {p_note}"
        f"  => {'PASS' if leg6 else 'FAIL'}"
    )

    all_pass = leg1 and leg2 and leg3 and leg4 and leg5 and leg6

    # --- W4.b: MDE@80% (α=0.05) per leg-verdict ---
    # Compute per-entry standard deviation for the all-regime sample
    sigma: float | None = None
    if not entries_df.empty and "ret_exit" in entries_df.columns:
        ret_vals = entries_df["ret_exit"].dropna()
        if len(ret_vals) > 1:
            sigma = float(ret_vals.std(ddof=1))

    n_all = all_stats["n"]
    mde = _mde_at_80pct(n_all, sigma) if sigma is not None else None
    mde_str = _pct(mde) if mde is not None else "n/a (sigma unavailable)"

    print()
    print(f"  Power context (W4.b — reporting only, gates untouched):")
    print(f"    n={n_all}  sigma={_pct(sigma)}  MDE@80%(α=0.05)={mde_str}")

    if not all_pass:
        # Check UNDERPOWERED-ACCRUING class
        is_up = _is_underpowered_accruing(all_stats, sigma)
        if is_up:
            print(
                f"  *** UNDERPOWERED-ACCRUING — leg FAILed on CI/placebo grounds "
                f"but point estimates all in PASSING direction and power<50% at "
                f"observed effect. Accrue more data before concluding. ***"
            )
            # W4.b: write kill_requeue row if data_dir is available
            if data_dir is not None:
                from datetime import datetime, timezone as _tz
                _asof = datetime.now(_tz.utc).strftime("%Y-%m-%d")
                _point_ests = {
                    "mean_ret_exit": all_stats.get("mean_ret_exit"),
                    "WR": all_stats.get("WR"),
                    "asym": all_stats.get("asym"),
                    "n": n_all,
                }
                _write_kill_requeue(
                    compound.get("id", "?"),
                    data_dir,
                    n_at_kill=n_all,
                    point_estimates=_point_ests,
                    asof=_asof,
                )
        else:
            print(f"  (power class: adequately powered for current n, or estimates not uniformly positive)")

    print()
    if all_pass:
        print("  *** REVERSION GAUNTLET PASS ***")
    else:
        print("  *** REVERSION GAUNTLET FAIL ***")
    print("=" * 70)
    print()

    return all_pass


# ---------------------------------------------------------------------------
# Main screen function
# ---------------------------------------------------------------------------

def screen_compound(
    compound: dict,
    data_dir: Path,
    window: int = 25,
    exit_sessions: int = 21,
    exit_mode: ExitMode = "time",
    gauntlet: bool = False,
) -> dict | None:
    """Screen a single compound.  Returns dict of stats or None on error."""
    from engine.oracle.compounds import (
        get_entry_dates,
        augment_panel_with_derived,
    )

    compound_id = compound.get("id", "?")
    name = compound.get("name", "")
    universe = compound.get("universe", {})
    tier = universe.get("tier", "s")

    log.info(
        "Screening %s (tier=%s, W=%d, E=%d, exit_mode=%s, gauntlet=%s)",
        compound_id, tier, window, exit_sessions, exit_mode, gauntlet,
    )

    try:
        panel = _load_panel(data_dir, tier)
        episodes = _load_episodes(data_dir, tier)
    except FileNotFoundError as exc:
        log.error("Data load failed for %s: %s", compound_id, exc)
        return None

    rotation_groups = _load_rotation_groups(data_dir)
    panel = augment_panel_with_derived(panel)

    try:
        entry_dates = get_entry_dates(compound, panel, episodes, rotation_groups)
    except ValueError as exc:
        log.error("Rule validation error for %s: %s", compound_id, exc)
        return None

    if "__blocked__" in entry_dates:
        log.warning("%s BLOCKED — missing columns: %s", compound_id, entry_dates["__blocked__"])
        return None

    total = sum(len(v) for v in entry_dates.values())
    log.info("%s: %d total triggers across %d nodes", compound_id, total, len(entry_dates))

    entries_df = _compute_entry_metrics(entry_dates, panel, window, exit_sessions, exit_mode)

    if entries_df.empty:
        log.warning("%s: no mature entries (all outside data range)", compound_id)
        all_stats = _agg_stats(entries_df)
        risk_on_stats = _agg_stats(pd.DataFrame())
        risk_off_stats = _agg_stats(pd.DataFrame())
    else:
        all_stats = _agg_stats(entries_df)
        risk_on_stats = _agg_stats(entries_df[entries_df["regime"] == "risk_on"])
        risk_off_stats = _agg_stats(entries_df[entries_df["regime"] == "risk_off"])

    mean_hold: float | None = None
    if exit_mode == "stochrsi2d" and not entries_df.empty and "hold_sessions" in entries_df.columns:
        mean_hold = float(entries_df["hold_sessions"].mean())

    _print_compound_report(
        compound_id, name, all_stats, risk_on_stats, risk_off_stats,
        window, exit_sessions, exit_mode=exit_mode, mean_hold=mean_hold,
    )

    if gauntlet:
        run_gauntlet(compound, entries_df, panel, window, exit_sessions, exit_mode,
                     data_dir=data_dir)

    return {
        "compound_id": compound_id,
        "name": name,
        "tier": tier,
        "window": window,
        "exit_sessions": exit_sessions,
        "exit_mode": exit_mode,
        "all": all_stats,
        "risk_on": risk_on_stats,
        "risk_off": risk_off_stats,
        "mean_hold": mean_hold,
    }


# ---------------------------------------------------------------------------
# Trial-ledger writer (W3_SPEC §2 — append-only, one row per screen)
# ---------------------------------------------------------------------------

_FROZEN_GATES = {
    "leg1_n": 100,
    "leg2_wr": 0.62,
    "leg3_asym": 1.5,
    "leg4_ret": 0.01,
}


def _gate_verdicts(stats: dict) -> dict[str, str]:
    """Return per-leg PASS/FAIL verdicts for the four frozen gates."""
    n = stats.get("n", 0) or 0
    wr = stats.get("WR") or 0.0
    asym = stats.get("asym") or 0.0
    ret = stats.get("mean_ret_exit") or 0.0
    return {
        "leg1": "P" if n >= _FROZEN_GATES["leg1_n"] else "F",
        "leg2": "P" if wr >= _FROZEN_GATES["leg2_wr"] else "F",
        "leg3": "P" if asym >= _FROZEN_GATES["leg3_asym"] else "F",
        "leg4": "P" if ret >= _FROZEN_GATES["leg4_ret"] else "F",
    }


def _append_reversion_trial_ledger(
    ledger_path: Path,
    result: dict,
    grammar_version: str,
) -> None:
    """Append one row to the reversion trial ledger (W3_SPEC §2).

    Idempotent-safe: the ledger is append-only; each run adds a row.
    The row includes enough info for the multiple-comparisons count to be
    machine-verifiable (compound_id + params_hash + screened_at + verdicts).
    """
    import hashlib

    compound_id = result.get("compound_id", "?")
    all_stats = result.get("all", {}) or {}
    n = all_stats.get("n", 0) or 0
    wr = all_stats.get("WR") or None
    asym = all_stats.get("asym") or None
    ret_exit = all_stats.get("mean_ret_exit") or None
    window = result.get("window", 25)
    exit_sessions = result.get("exit_sessions", 21)
    exit_mode = result.get("exit_mode", "time")

    gates = _gate_verdicts(all_stats)
    passed_legs14 = all(v == "P" for v in gates.values())

    # Stable params hash: compound_id + window + exit_sessions + exit_mode + grammar_version
    params_str = f"{compound_id}|{window}|{exit_sessions}|{exit_mode}|{grammar_version}"
    params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:12]

    row = {
        "compound_id": compound_id,
        "screener": "oracle_reversion_screen_v1",
        "grammar_version": grammar_version,
        "params_hash": params_hash,
        "screened_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "window": window,
        "exit_sessions": exit_sessions,
        "exit_mode": exit_mode,
        "n": n,
        "WR": round(wr, 4) if wr is not None else None,
        "asym": round(asym, 4) if asym is not None else None,
        "ret_exit": round(ret_exit, 6) if ret_exit is not None else None,
        "leg1": gates["leg1"],
        "leg2": gates["leg2"],
        "leg3": gates["leg3"],
        "leg4": gates["leg4"],
        "passed_legs14": passed_legs14,
        "disclaimer": "EXPLORATORY — no claim language; counts toward search width",
    }

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_compound(
    compound_id: str,
    registry: list[dict],
    inline_rule_json: str | None = None,
    inline_id: str | None = None,
) -> dict | None:
    """Resolve a compound definition: registry first, then inline fallbacks."""
    # Try registry
    for c in registry:
        if c.get("id") == compound_id:
            return c

    # Try built-in inline fallbacks
    if compound_id in _INLINE_COMPOUNDS:
        log.info("%s not in registry — using built-in inline definition", compound_id)
        return _INLINE_COMPOUNDS[compound_id]

    # Try user-supplied inline rule
    if inline_rule_json and inline_id == compound_id:
        try:
            rule = json.loads(inline_rule_json)
        except json.JSONDecodeError as exc:
            log.error("--inline-rule JSON parse error: %s", exc)
            return None
        return {
            "id": compound_id,
            "name": f"Inline: {compound_id}",
            "universe": {"tier": "s"},
            "entry_rule": rule,
        }

    log.error("Compound '%s' not found in registry or inline fallbacks", compound_id)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Oracle reversion-capture + drawdown-asymmetry screener (read-only)"
    )
    ap.add_argument("--compound", type=str, default=None,
                    help="Compound id to screen (registry or inline fallback)")
    ap.add_argument("--all-pending", action="store_true",
                    help="Screen all compounds in the registry")
    ap.add_argument("--inline-rule", type=str, default=None,
                    help="JSON string for an ad-hoc entry_rule (requires --inline-id)")
    ap.add_argument("--inline-id", type=str, default=None,
                    help="Id to assign to --inline-rule compound")
    ap.add_argument("--data-dir", type=Path, default=None,
                    help="Path to data directory")
    ap.add_argument("--compounds-dir", type=Path, default=None,
                    help="Override path to registry dir (default: <data-dir>/oracle/compounds)")
    ap.add_argument("--window", type=int, default=25,
                    help="MFE/MAE window in sessions (default: 25)")
    ap.add_argument("--exit", dest="exit_sessions", type=int, default=21,
                    help="Time-exit sessions (default: 21; only used with --exit-mode time)")
    ap.add_argument(
        "--exit-mode",
        dest="exit_mode",
        choices=["time", "stochrsi2d"],
        default="time",
        help=(
            "Exit strategy: 'time' (fixed exit_sessions, default) or "
            "'stochrsi2d' (first 2D-StochRSI K-cross-below-D after min-hold=3, "
            "capped at 40 sessions)"
        ),
    )
    ap.add_argument(
        "--gauntlet",
        action="store_true",
        help=(
            "Run the full 6-leg reversion PASS gate (legs 1-4 aggregate, "
            "leg 5 OOS holdout, leg 6 timing placebo)"
        ),
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="No-op flag for interface parity with oracle_screen; this tool is read-only by default")
    ap.add_argument(
        "--no-trial-ledger",
        action="store_true",
        help=(
            "Skip writing to the reversion trial ledger. "
            "Default: each screen appends one row to reversion_trial_ledger.jsonl "
            "alongside registry.jsonl (satisfies W3_SPEC §2 mining-legal count)."
        ),
    )
    args = ap.parse_args()

    # Resolve data directory
    if args.data_dir:
        data_dir = args.data_dir
    else:
        try:
            from lib import config as _cfg
            data_dir = _cfg.data_dir()
        except Exception:
            ap.error("--data-dir is required (lib.config unavailable)")
            return 1

    compounds_dir = args.compounds_dir or (data_dir / "oracle" / "compounds")

    from engine.oracle.compounds import load_registry
    registry = load_registry(compounds_dir)

    # Build target list
    targets: list[dict] = []

    if args.inline_rule and args.inline_id:
        # Ad-hoc inline compound
        try:
            rule = json.loads(args.inline_rule)
        except json.JSONDecodeError as exc:
            log.error("--inline-rule JSON parse error: %s", exc)
            return 1
        targets.append(
            {
                "id": args.inline_id,
                "name": f"Inline: {args.inline_id}",
                "universe": {"tier": "s"},
                "entry_rule": rule,
            }
        )
    elif args.compound:
        c = _resolve_compound(args.compound, registry, args.inline_rule, args.inline_id)
        if c is None:
            return 1
        targets.append(c)
    elif args.all_pending:
        targets = list(registry)
        log.info("all-pending: %d compounds in registry", len(targets))
    else:
        ap.error("Provide --compound <id>, --all-pending, or --inline-rule + --inline-id")
        return 1

    from engine.oracle.compounds import GRAMMAR_VERSION

    ledger_path = compounds_dir / "reversion_trial_ledger.jsonl"
    if not args.no_trial_ledger:
        log.info("Trial-ledger enabled: %s", ledger_path)

    failures: list[str] = []
    for compound in targets:
        try:
            result = screen_compound(
                compound,
                data_dir,
                window=args.window,
                exit_sessions=args.exit_sessions,
                exit_mode=args.exit_mode,
                gauntlet=args.gauntlet,
            )
            if result is None:
                failures.append(compound.get("id", "?"))
            elif not args.no_trial_ledger:
                _append_reversion_trial_ledger(ledger_path, result, GRAMMAR_VERSION)
        except Exception as exc:  # noqa: BLE001
            log.error("screen_compound %s FAILED: %s", compound.get("id"), exc)
            failures.append(compound.get("id", "?"))

    if failures:
        log.error("Failures: %s", failures)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
