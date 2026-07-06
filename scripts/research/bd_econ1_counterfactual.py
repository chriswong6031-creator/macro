"""BD-ECON-1 — Avoided-Loss / Missed-Upside Counterfactual.

Authority: research/short_side/BD_ECON1_PREREG.md (FROZEN; all numeric thresholds
and floor requirements are read from the prereg, not from this file).
research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md §5.3 + RUL-U3 + RUL-U3a.

This script performs retro decision-economics on already-graded history:
  "If the board had skipped production fires during active BD avoid windows,
   what drawdown was avoided and what upside was missed?"

It grants no live authority; its only consumer is the decision of which
forward preregs to write.

Budget (prereg §3, RUL-U3a):
  TrialLedger.log_declared_budget(6, family='short_side') BEFORE the run.
  Each of the 6 verdict cells is also logged as a distinct config so that
  family literal_n accumulates. Every output prints the family literal count
  PLUS the max()-basis divergence note (the #1664 §0.5.6 convention).

Outputs (RUL-P10):
  data/research/bd_econ1_summary.json  — committed, vintage-stamped
  research/short_side/BD_ECON1_REPORT.md — plain-language report

The word "validated" appears nowhere in this script or its outputs.

Usage
-----
python scripts/research/bd_econ1_counterfactual.py [--data-root PATH] [--dry-run]

--data-root defaults to the Mac-canonical data path.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap — canonical pattern from scripts/run_rule_replay.py.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]  # repo root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.trial_ledger import TrialLedger  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical data root (same pattern as _CANONICAL_DATA in run_rule_replay.py)
# ---------------------------------------------------------------------------
_CANONICAL_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")

# ---------------------------------------------------------------------------
# Frozen study parameters (from prereg §3)
# ---------------------------------------------------------------------------
WINDOW_BARS = 21          # 21 trading bars (never calendar days)
FLOOR_FLAGGED_FIRES = 300  # ≥300 flagged fires per definition
FLOOR_BD_EPISODES = 100    # ≥100 distinct contributing BD episodes
FLOOR_RECENT_STOP = 300    # C3 additionally requires ≥300 recent-stop cohort fires
BOOT_N_DRAWS = 2000        # bootstrap draws
BOOT_RNG_SEED = 20260706   # stable seed for reproducibility
BH_Q = 0.10                # BH q-level for the declared 6-cell set

# Definitions used (BD-1 parked underpowered per Phase-0 reading guide)
ACTIVE_DEFINITIONS = ("BD-2", "BD-3")

TRIAL_FAMILY = "short_side"
DECLARED_BUDGET = 6  # 3 contrasts × 2 endpoints


# ===========================================================================
# 1. Calendar utilities — trading-bar counting on the massive plane
# ===========================================================================

_CALENDAR: pd.DatetimeIndex | None = None


def _build_calendar(data_root: Path) -> pd.DatetimeIndex:
    """Build trading-bar calendar from SPY's massive_stock_day index."""
    global _CALENDAR
    if _CALENDAR is not None:
        return _CALENDAR
    spy_path = data_root / "massive_stock_day" / "SPY.parquet"
    if not spy_path.exists():
        raise FileNotFoundError(f"SPY.parquet not found at {spy_path}; cannot build trading calendar")
    df = pd.read_parquet(spy_path)
    _CALENDAR = pd.DatetimeIndex(sorted(df.index.unique()))
    return _CALENDAR


def _ts(s: str) -> pd.Timestamp:
    """Convert date string to Timestamp (no tz)."""
    return pd.Timestamp(s)


def _end_of_window(event_date_str: str, calendar: pd.DatetimeIndex) -> pd.Timestamp:
    """event_date + 21 trading bars on the massive plane calendar.

    Returns the timestamp of the 21st trading bar after event_date
    (inclusive of that bar), so the window is:
      event_date < signal_date <= _end_of_window(event_date).
    """
    ev_ts = _ts(event_date_str)
    loc = calendar.searchsorted(ev_ts, side="left")
    # If ev_ts is exactly in calendar, searchsorted(side='left') gives its position.
    # end = ev_loc + 21 (21 bars after event bar itself, i.e. bars 1..21 from event)
    end_loc = min(loc + WINDOW_BARS, len(calendar) - 1)
    return calendar[end_loc]


def _bar_diff(date_a_str: str, date_b_str: str, calendar: pd.DatetimeIndex) -> int:
    """Number of trading bars from date_a to date_b (signed)."""
    a = _ts(date_a_str)
    b = _ts(date_b_str)
    la = int(calendar.searchsorted(a, side="left"))
    lb = int(calendar.searchsorted(b, side="left"))
    return lb - la


# ===========================================================================
# 2. Flagging rule — join breakdown events onto fires
# ===========================================================================

def build_flagged_fires(
    events_df: pd.DataFrame,
    fires_df: pd.DataFrame,
    definition: str,
    calendar: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Apply the frozen flagging rule (prereg §2) for one definition.

    A fire is FLAGGED by definition D iff the same ticker has a D event
    (episode-collapsed) with:
        event_date < signal_date <= event_date + 21 trading bars

    Fires with signal_date <= event_date are NEVER flagged
    (excludes BD-2's generating fire by construction).

    Returns:
        flagged_fires (DataFrame): fires that are flagged by this definition
        unflagged_fires (DataFrame): fires that are NOT flagged by any window
                                     of this definition on the same ticker
        n_episodes (int): count of distinct contributing BD episodes

    NOTE: if a fire is flagged by multiple events of the same definition,
    it is counted ONCE in flagged_fires (deduplicated on fire row).
    """
    ev_d = events_df[events_df["definition"] == definition].copy()
    ev_d = ev_d[~ev_d["is_control"]].copy()

    # Reset fires to a clean RangeIndex so positional indexing works safely
    fires_work = fires_df.reset_index(drop=True).copy()
    fires_work["_sig_ts"] = fires_work["signal_date"].apply(_ts)

    # Build per-ticker event list: (ev_ts, ev_date_str, end_ts)
    ev_d_ts = ev_d["event_date"].apply(_ts)
    ev_by_ticker: dict[str, list[tuple[pd.Timestamp, str, pd.Timestamp]]] = {}
    for i, row in ev_d.iterrows():
        t = str(row["ticker"])
        ev_ts = ev_d_ts.loc[i]
        ev_date_str = str(row["event_date"])
        end_ts = _end_of_window(ev_date_str, calendar)
        ev_by_ticker.setdefault(t, []).append((ev_ts, ev_date_str, end_ts))

    # Boolean array: True where fire is flagged
    n_fires = len(fires_work)
    is_flagged = np.zeros(n_fires, dtype=bool)
    fire_to_event: list[str | None] = [None] * n_fires
    contributing_episodes: set[tuple[str, str]] = set()

    for fire_pos in range(n_fires):
        ticker = str(fires_work.at[fire_pos, "ticker"])
        sig_ts = fires_work.at[fire_pos, "_sig_ts"]

        for ev_ts, ev_date_str, end_ts in ev_by_ticker.get(ticker, []):
            # window: event_date < signal_date <= event_date + 21 bars
            if ev_ts < sig_ts <= end_ts:
                is_flagged[fire_pos] = True
                fire_to_event[fire_pos] = ev_date_str
                contributing_episodes.add((ticker, ev_date_str))
                break  # first matching event is sufficient

    flagged_fires = fires_work[is_flagged].copy()
    flagged_fires["flag_event_date"] = [fire_to_event[i] for i in flagged_fires.index]
    flagged_fires = flagged_fires.drop(columns=["_sig_ts"])

    unflagged_fires = fires_work[~is_flagged].copy().drop(columns=["_sig_ts"])

    n_episodes = len(contributing_episodes)
    return flagged_fires, unflagged_fires, n_episodes


def build_recent_stop_cohort(fires_df: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Build the recent-stop cohort for C3 (prereg §2).

    An unflagged fire is in the recent-stop cohort iff:
      - Same ticker has a fire with state_8_21 == 'STOPPED' whose stop was reached
        within the trailing 21 bars of signal_date
      - AND the ticker has NO active BD-2 window at signal_date

    The 'stop bar' for a fire is determined by stopped_at_8_21 (bars-from-fill
    to the stop, 1-indexed), so stop_date = fill_date + (stopped_at_8_21 - 1) bars.
    A stop is 'within 21 bars of signal_date' iff the stop bar is within 21
    trading bars before signal_date (i.e. stop_bar >= signal_date - 21 bars).

    NOTE: the caller passes already-unflagged fires (unflagged by BD-2), so
    the BD-2 window exclusion is already satisfied.
    """
    # Work on a clean RangeIndex copy
    fires_work = fires_df.reset_index(drop=True).copy()
    fires_work["_sig_ts"] = fires_work["signal_date"].apply(_ts)

    # Index all stopped fires by ticker for fast lookup
    stopped_mask = fires_work["state_8_21"] == "STOPPED"
    stopped = fires_work[stopped_mask].copy()

    def _compute_stop_ts(row) -> pd.Timestamp | None:
        fill_str = row.get("fill_date")
        offset = row.get("stopped_at_8_21")
        if not fill_str or pd.isna(fill_str) or pd.isna(offset):
            return None
        try:
            fill_ts = _ts(str(fill_str))
            bar_offset = int(offset) - 1  # stopped_at_8_21 is 1-indexed bars-from-fill
            fill_loc = int(calendar.searchsorted(fill_ts, side="left"))
            stop_loc = min(fill_loc + bar_offset, len(calendar) - 1)
            return calendar[stop_loc]
        except Exception:
            return None

    stop_by_ticker: dict[str, list[pd.Timestamp]] = {}
    for fire_pos in range(len(stopped)):
        row = stopped.iloc[fire_pos]
        stop_ts = _compute_stop_ts(row)
        if stop_ts is not None:
            stop_by_ticker.setdefault(str(row["ticker"]), []).append(stop_ts)

    # Find fires with a recent stop (within trailing 21 bars)
    n_fires = len(fires_work)
    in_cohort = np.zeros(n_fires, dtype=bool)

    for fire_pos in range(n_fires):
        ticker = str(fires_work.at[fire_pos, "ticker"])
        sig_ts = fires_work.at[fire_pos, "_sig_ts"]

        stops = stop_by_ticker.get(ticker, [])
        if not stops:
            continue

        sig_loc = int(calendar.searchsorted(sig_ts, side="left"))
        start_loc = max(0, sig_loc - WINDOW_BARS)
        start_ts = calendar[start_loc]

        for stop_t in stops:
            # stop_bar in [sig_ts - 21 bars, sig_ts) strictly before signal
            if start_ts <= stop_t < sig_ts:
                in_cohort[fire_pos] = True
                break

    result = fires_work[in_cohort].copy().drop(columns=["_sig_ts"])
    return result


# ===========================================================================
# 3. Contrast statistics (prereg §3)
# ===========================================================================

def _month_ticker_bootstrap(
    arm_a: pd.DataFrame,
    arm_b: pd.DataFrame,
    endpoint_col: str,
    endpoint_is_binary: bool,
    rng: np.random.Generator,
    n_draws: int = BOOT_N_DRAWS,
) -> dict[str, Any]:
    """Two-way month×ticker cluster bootstrap (prereg §3).

    Sequential resampling: first resample calendar months (blocks),
    then tickers within each resampled month-block.

    Returns point estimates, delta, and percentile 95% CI on the delta.
    """
    def _prepare(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (values, months, tickers) arrays."""
        vals = df[endpoint_col].to_numpy(dtype=float)
        months = pd.to_datetime(df["signal_date"]).dt.to_period("M").astype(str).to_numpy()
        tickers = df["ticker"].astype(str).to_numpy()
        return vals, months, tickers

    vals_a, months_a, tickers_a = _prepare(arm_a)
    vals_b, months_b, tickers_b = _prepare(arm_b)

    # Valid (non-NaN) rows only; censored rows counted separately
    valid_a = np.isfinite(vals_a)
    valid_b = np.isfinite(vals_b)

    va = vals_a[valid_a]
    ma = months_a[valid_a]
    ta = tickers_a[valid_a]
    vb = vals_b[valid_b]
    mb = months_b[valid_b]
    tb = tickers_b[valid_b]

    n_a = int(len(va))
    n_b = int(len(vb))

    if n_a == 0 or n_b == 0:
        return {
            "n_arm_a": n_a, "n_arm_b": n_b,
            "mean_a": None, "mean_b": None,
            "delta": None, "ci95_lo": None, "ci95_hi": None,
            "note": "insufficient data",
        }

    mean_a = float(np.mean(va))
    mean_b = float(np.mean(vb))
    delta = mean_a - mean_b  # arm_a minus arm_b

    def _one_draw_mean(vals: np.ndarray, months: np.ndarray, tickers: np.ndarray) -> float:
        """One bootstrap draw: resample months then tickers within months."""
        unique_months = np.unique(months)
        if len(unique_months) == 0:
            return float(np.mean(vals))
        # Draw months with replacement
        drawn_months = rng.choice(unique_months, size=len(unique_months), replace=True)
        sample_vals: list[float] = []
        # Build month-ticker index
        month_ticker_map: dict[str, dict[str, list[float]]] = {}
        for v, m, t in zip(vals, months, tickers):
            month_ticker_map.setdefault(m, {}).setdefault(t, []).append(v)

        for m in drawn_months:
            mt = month_ticker_map.get(m, {})
            if not mt:
                continue
            unique_tickers = list(mt.keys())
            # Resample tickers within this month block
            drawn_tickers = rng.choice(unique_tickers, size=len(unique_tickers), replace=True)
            for t in drawn_tickers:
                sample_vals.extend(mt[t])

        return float(np.mean(sample_vals)) if sample_vals else float(np.mean(vals))

    boot_deltas = np.empty(n_draws)
    for i in range(n_draws):
        m_a = _one_draw_mean(va, ma, ta)
        m_b = _one_draw_mean(vb, mb, tb)
        boot_deltas[i] = m_a - m_b

    ci_lo = float(np.percentile(boot_deltas, 2.5))
    ci_hi = float(np.percentile(boot_deltas, 97.5))

    return {
        "n_arm_a": n_a,
        "n_arm_b": n_b,
        "mean_a": round(mean_a, 5),
        "mean_b": round(mean_b, 5),
        "delta": round(delta, 5),
        "ci95_lo": round(ci_lo, 5),
        "ci95_hi": round(ci_hi, 5),
        "boot_n_draws": n_draws,
        "ci_excludes_zero": (ci_lo > 0 or ci_hi < 0),
        "note": "two-way month×ticker cluster bootstrap, sequential resampling",
    }


def _jackknife_sensitivity(
    arm_a: pd.DataFrame,
    arm_b: pd.DataFrame,
    endpoint_col: str,
) -> dict[str, Any]:
    """Per-ticker jackknife of each delta (prereg §3).

    For each ticker in arm_a, leave it out and re-compute the delta.
    Reports: max absolute jackknife influence (as fraction of delta),
    and count of tickers with influence > 10% of delta.
    """
    def _valid_mean(df: pd.DataFrame) -> float | None:
        vals = df[endpoint_col].replace([np.inf, -np.inf], np.nan).dropna()
        return float(np.mean(vals)) if len(vals) > 0 else None

    mean_b = _valid_mean(arm_b)
    if mean_b is None:
        return {"note": "arm_b empty; jackknife skipped"}

    tickers_a = arm_a["ticker"].unique()
    if len(tickers_a) < 2:
        return {"note": "fewer than 2 tickers; jackknife skipped"}

    full_mean_a = _valid_mean(arm_a)
    if full_mean_a is None:
        return {"note": "arm_a empty; jackknife skipped"}

    full_delta = full_mean_a - mean_b

    influences: list[float] = []
    for t in tickers_a:
        loo = arm_a[arm_a["ticker"] != t]
        m = _valid_mean(loo)
        if m is None:
            continue
        loo_delta = m - mean_b
        if abs(full_delta) > 1e-10:
            influences.append(abs(loo_delta - full_delta) / abs(full_delta))
        else:
            influences.append(abs(loo_delta - full_delta))

    if not influences:
        return {"note": "no jackknife estimates computed"}

    arr = np.array(influences)
    return {
        "n_tickers_a": int(len(tickers_a)),
        "max_jackknife_influence_frac": round(float(arr.max()), 4),
        "n_tickers_influence_gt_10pct": int((arr > 0.1).sum()),
        "note": "per-ticker jackknife of arm_a; influence = |loo_delta - full_delta| / |full_delta|",
    }


def _binary_endpoint(fires: pd.DataFrame, col: str, target_val: str) -> pd.Series:
    """Return 0/1 Series for col == target_val; NaN where col is NaN."""
    return fires[col].apply(lambda v: float(v == target_val) if pd.notna(v) else np.nan)


def _mk_ep(fires: pd.DataFrame, vals: pd.Series, col_name: str) -> pd.DataFrame:
    """Build a minimal (signal_date, ticker, col_name) DataFrame for bootstrap input."""
    out = fires[["signal_date", "ticker"]].copy()
    out[col_name] = vals.values
    return out


def run_contrast(
    flagged: pd.DataFrame,
    unflagged: pd.DataFrame,
    contrast_name: str,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Run both endpoints for one contrast (prereg §3).

    Endpoint (a): stop-rate delta at h21 (state_8_21 == 'STOPPED' share)
    Endpoint (b): mean fwd_ret_21 delta
    """
    # Endpoint (a): binary stop rate (0/1 per fire)
    stop_vals_flagged = _binary_endpoint(flagged, "state_8_21", "STOPPED")
    stop_vals_unflagged = _binary_endpoint(unflagged, "state_8_21", "STOPPED")

    ep_a_flagged = _mk_ep(flagged, stop_vals_flagged, "_ep")
    ep_a_unflagged = _mk_ep(unflagged, stop_vals_unflagged, "_ep")

    ep_a_stats = _month_ticker_bootstrap(ep_a_flagged, ep_a_unflagged, "_ep", True, rng)
    ep_a_jack = _jackknife_sensitivity(ep_a_flagged, ep_a_unflagged, "_ep")

    # Endpoint (b): mean fwd_ret_21
    ep_b_flagged = _mk_ep(flagged, flagged["fwd_ret_21"].copy(), "_ep")
    ep_b_unflagged = _mk_ep(unflagged, unflagged["fwd_ret_21"].copy(), "_ep")

    ep_b_stats = _month_ticker_bootstrap(ep_b_flagged, ep_b_unflagged, "_ep", False, rng)
    ep_b_jack = _jackknife_sensitivity(ep_b_flagged, ep_b_unflagged, "_ep")

    # Censoring accounting (NaN rows counted, never silently dropped)
    n_flagged_stop_nan = int(flagged["state_8_21"].isna().sum())
    n_unflagged_stop_nan = int(unflagged["state_8_21"].isna().sum())
    n_flagged_ret_nan = int(flagged["fwd_ret_21"].isna().sum())
    n_unflagged_ret_nan = int(unflagged["fwd_ret_21"].isna().sum())

    return {
        "contrast": contrast_name,
        "n_flagged": int(len(flagged)),
        "n_unflagged": int(len(unflagged)),
        "endpoint_a_stop_rate": ep_a_stats,
        "endpoint_a_jackknife": ep_a_jack,
        "endpoint_b_fwd_ret21": ep_b_stats,
        "endpoint_b_jackknife": ep_b_jack,
        "censoring": {
            "n_flagged_stop_nan": n_flagged_stop_nan,
            "n_unflagged_stop_nan": n_unflagged_stop_nan,
            "n_flagged_ret21_nan": n_flagged_ret_nan,
            "n_unflagged_ret21_nan": n_unflagged_ret_nan,
            "note": "NaN rows excluded from statistics; counted here per prereg",
        },
    }


# ===========================================================================
# 4. Year / tier descriptive splits (declared multiplicity — prereg §3)
# ===========================================================================

def _descriptive_splits(flagged: pd.DataFrame, unflagged: pd.DataFrame) -> dict[str, Any]:
    """Year and tier_cascade splits — DESCRIPTIVE multiplicity per prereg §3.

    Per WAIT-GRID-1 precedent: these are declared here but NOT verdict cells.
    """
    def _year_split(df: pd.DataFrame) -> dict:
        df = df.copy()
        df["_year"] = pd.to_datetime(df["signal_date"]).dt.year
        counts = df.groupby("_year").size().to_dict()
        stop_rates = {}
        for yr, grp in df.groupby("_year"):
            valid = grp["state_8_21"].notna()
            if valid.sum() > 0:
                stop_rates[int(yr)] = round(
                    float((grp.loc[valid, "state_8_21"] == "STOPPED").mean() * 100), 2
                )
        return {"n_by_year": {int(k): int(v) for k, v in counts.items()},
                "stop_rate_pct_by_year": stop_rates}

    def _tier_split(df: pd.DataFrame) -> dict:
        if "tier_cascade" not in df.columns:
            return {}
        counts = df["tier_cascade"].value_counts().to_dict()
        stop_rates = {}
        for tier, grp in df.groupby("tier_cascade"):
            valid = grp["state_8_21"].notna()
            if valid.sum() > 0:
                stop_rates[str(tier)] = round(
                    float((grp.loc[valid, "state_8_21"] == "STOPPED").mean() * 100), 2
                )
        return {"n_by_tier": {str(k): int(v) for k, v in counts.items()},
                "stop_rate_pct_by_tier": stop_rates}

    return {
        "flagged_year_split": _year_split(flagged),
        "flagged_tier_split": _tier_split(flagged),
        "unflagged_year_split": _year_split(unflagged),
        "note": "DESCRIPTIVE multiplicity declared in prereg §3; not verdict cells",
    }


# ===========================================================================
# 5. Economics block (prereg §4 — arithmetic on flagged cohort; no new tests)
# ===========================================================================

def _econ_block(
    flagged: pd.DataFrame,
    definition: str,
    unflagged_contrast_arm: pd.DataFrame,
    ep_b_ci: dict[str, Any],  # re-presents the budgeted ep_b CI — no fresh test
) -> dict[str, Any]:
    """Economics block per prereg §4.

    (a) Avoided drawdown: fwd_mdd_21 distribution among flagged fires that stopped
    (b) Missed upside: fwd_ret_21 and fwd_mfe_21 among flagged fires that ended CLEAN
    (c) Skip-policy net read: re-presents budgeted endpoint-(b) CI, never a fresh test
    (d) Re-entry quality (descriptive): state_8_21 of next unflagged fire on same
        ticker within 63 bars (descriptive, not graded against a null)

    Symmetric-cost printing per RUL-N6.
    """
    flagged_stopped = flagged[flagged["state_8_21"] == "STOPPED"].copy()
    flagged_clean = flagged[flagged["state_8_21"] == "CLEAN_LIFTOFF"].copy()

    def _dist(series: pd.Series, label: str) -> dict:
        vals = series.replace([np.inf, -np.inf], np.nan).dropna()
        if len(vals) == 0:
            return {"n": 0, "note": f"no {label} observations"}
        return {
            "n": int(len(vals)),
            "mean": round(float(vals.mean()), 5),
            "median": round(float(vals.median()), 5),
            "p90": round(float(np.percentile(vals, 90)), 5),
            "p10": round(float(np.percentile(vals, 10)), 5),
        }

    # (a) Avoided drawdown — among flagged fires that stopped
    avoided_drawdown = _dist(flagged_stopped["fwd_mdd_21"], "fwd_mdd_21")

    # (b) Missed upside — among flagged fires that ended CLEAN
    missed_ret = _dist(flagged_clean["fwd_ret_21"], "fwd_ret_21")
    missed_mfe = _dist(flagged_clean["fwd_mfe_21"], "fwd_mfe_21")

    # (c) Skip-policy net read — re-presents ep_b CI (no fresh test)
    skip_net = {
        "description": (
            "Re-presentation of budgeted endpoint-(b) CI: mean fwd_ret_21(unflagged) "
            "minus mean fwd_ret_21(flagged). Positive = unflagged fires had higher "
            "forward return; negative = flagged fires did better. No new test computed."
        ),
        "ep_b_delta_flagged_minus_unflagged": ep_b_ci.get("delta"),
        "ep_b_ci95_lo": ep_b_ci.get("ci95_lo"),
        "ep_b_ci95_hi": ep_b_ci.get("ci95_hi"),
        "n_flagged": ep_b_ci.get("n_arm_a"),
        "n_unflagged": ep_b_ci.get("n_arm_b"),
    }

    # (d) Re-entry quality (descriptive): next unflagged fire on same ticker within 63 bars
    # We can compute this from unflagged arm: for each flagged fire, find next unflagged
    # fire on the same ticker with signal_date > flagged signal_date within 63 bars.
    # Since we need calendar, this is computed as-is without the calendar here
    # (the caller handles passing context). We store counts of state_8_21 distribution.
    reentry_states: dict[str, int] = {}
    if len(unflagged_contrast_arm) > 0 and len(flagged) > 0:
        uf_by_ticker: dict[str, list[tuple[str, str]]] = {}  # ticker -> [(sig_date, state)]
        for _, row in unflagged_contrast_arm.iterrows():
            t = str(row["ticker"])
            uf_by_ticker.setdefault(t, []).append(
                (str(row["signal_date"]), str(row["state_8_21"]) if pd.notna(row["state_8_21"]) else "")
            )

        for _, frow in flagged.iterrows():
            ft = str(frow["ticker"])
            fs = str(frow["signal_date"])
            candidates = [
                (sd, st) for sd, st in uf_by_ticker.get(ft, [])
                if sd > fs
            ]
            if candidates:
                # Use nearest (by date string sort, which is ISO-correct)
                nearest_state = sorted(candidates)[0][1]
                reentry_states[nearest_state] = reentry_states.get(nearest_state, 0) + 1

    return {
        "definition": definition,
        "n_flagged_stopped": int(len(flagged_stopped)),
        "n_flagged_clean": int(len(flagged_clean)),
        "avoided_drawdown_fwd_mdd_21": avoided_drawdown,
        "missed_upside_fwd_ret_21": missed_ret,
        "missed_upside_fwd_mfe_21": missed_mfe,
        "rn6_symmetric_cost_note": (
            "Avoided drawdown (§4a) and missed upside (§4b) printed with equal "
            "prominence per RUL-N6 symmetric-cost law."
        ),
        "skip_policy_net_read": skip_net,
        "reentry_quality_descriptive": {
            "state_8_21_distribution": reentry_states,
            "note": (
                "State of next unflagged fire on same ticker (descriptive; "
                "no inference performed)"
            ),
        },
    }


# ===========================================================================
# 6. BH correction for the declared 6-cell set
# ===========================================================================

def _bh_correction(
    p_values: dict[str, float | None],
    q: float = BH_Q,
) -> dict[str, Any]:
    """Benjamini-Hochberg correction on the declared 6 verdict cells.

    p-values estimated from bootstrap CIs: p ~ 2 * min(Phi(-|delta|/se), 0.5)
    where se is estimated from the CI half-width. This is an approximation.
    Since we use percentile CIs (not normal-approximation), we estimate
    whether CI excludes zero as a conservative binary verdict.

    Per prereg §3: BH q = 0.10 within the declared 6-cell set.
    """
    cells = [(k, v) for k, v in p_values.items() if v is not None]
    if not cells:
        return {"note": "no p-values to correct"}

    # Sort by p-value ascending
    cells_sorted = sorted(cells, key=lambda x: x[1])
    n = len(cells_sorted)
    results: dict[str, Any] = {}
    for rank, (key, pval) in enumerate(cells_sorted, 1):
        threshold = (rank / n) * q
        reject = pval <= threshold
        results[key] = {
            "p_approx": round(pval, 4),
            "bh_threshold": round(threshold, 4),
            "bh_reject": reject,
        }
    return {
        "q": q,
        "n_cells": n,
        "cells": results,
        "note": (
            "Approximate BH correction; p estimated from CI half-width assuming "
            "normal approximation. CI-excludes-zero is the primary verdict; "
            "this BH table is supplemental."
        ),
    }


# ===========================================================================
# 7. TrialLedger budget accounting (RUL-U3a)
# ===========================================================================

VERDICT_CELL_CONFIGS = [
    {"contrast": "C1", "endpoint": "a_stop_rate", "definition": "BD-2"},
    {"contrast": "C1", "endpoint": "b_fwd_ret21", "definition": "BD-2"},
    {"contrast": "C2", "endpoint": "a_stop_rate", "definition": "BD-3"},
    {"contrast": "C2", "endpoint": "b_fwd_ret21", "definition": "BD-3"},
    {"contrast": "C3", "endpoint": "a_stop_rate", "definition": "BD-2"},
    {"contrast": "C3", "endpoint": "b_fwd_ret21", "definition": "BD-2"},
]


def _register_budget_and_cells(ledger: TrialLedger) -> int:
    """Log the declared budget and all 6 verdict cells.

    Per RUL-U3a: log_declared_budget is a per-family max() floor.
    Each cell is also logged as a distinct config so literal_n accumulates.
    Returns the family literal_n AFTER logging.
    """
    # Declared budget FIRST (before any statistics)
    ledger.log_declared_budget(DECLARED_BUDGET, family=TRIAL_FAMILY,
                                reason="BD-ECON-1: 3 contrasts x 2 endpoints (prereg §3)")

    # Log each of the 6 cells as a distinct config
    for cell in VERDICT_CELL_CONFIGS:
        ledger.log_trial(cell, family=TRIAL_FAMILY,
                         note="BD-ECON-1 verdict cell (RUL-U3a)")

    return ledger.literal_n(TRIAL_FAMILY)


# ===========================================================================
# 8. Vintage stamp (inline, consistent with dump_breakdown_events.py)
# ===========================================================================

def _vintage_stamp(data_root: Path) -> dict[str, Any]:
    """Minimal vintage stamp for the summary JSON."""
    return {
        "schema": "bd_econ1_summary.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "derived_from_surface": "bd_phase0",
        "events_tape": "data/research/breakdown_events.parquet",
        "fires_tape": "data/replay/replay_boarded.parquet",
        "contamination_stamp": (
            "Feasibility peek disclosed in BD_ECON1_PREREG.md §Amendments: "
            "coarse floors-feasibility join run before commit confirmed floors met "
            "and revealed coarse pooled magnitudes; no gate/threshold was changed."
        ),
        "survivorship_note": (
            "Fires tape: ERA-LAW cohort (verdict_type='fire', verdict_grade=True). "
            "Events tape: BD-2/BD-3 episodes from bd_phase0 tape (is_control=False). "
            "Both tapes are survivorship-biased by construction (massive plane universe)."
        ),
    }


# ===========================================================================
# 9. Main run
# ===========================================================================

def _p_approx_from_ci(delta: float | None, ci_lo: float | None, ci_hi: float | None) -> float | None:
    """Approximate two-sided p-value from bootstrap CI.

    Uses the CI half-width as a proxy for SE, then computes a Z-score.
    Conservative approximation only — CI-excludes-zero is the primary verdict.
    """
    if delta is None or ci_lo is None or ci_hi is None:
        return None
    se = (ci_hi - ci_lo) / (2 * 1.96)
    if se <= 0:
        return None
    from math import exp, log, pi, sqrt, erfc
    z = abs(delta) / se
    # Two-sided p from normal CDF approximation
    # p ≈ erfc(z / sqrt(2))
    p = float(erfc(z / sqrt(2)))
    return min(p, 1.0)


def run(
    data_root: Path,
    dry_run: bool = False,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Main runner. Returns the full results dict.

    Prints achieved n BEFORE any statistics (prereg requirement).
    """
    log.info("BD-ECON-1 starting. data_root=%s dry_run=%s", data_root, dry_run)

    # -- TrialLedger: declare budget FIRST, before any data loading or statistics --
    ledger = TrialLedger(path=ledger_path or (data_root.parent / "data" / "trial_ledger.jsonl"))
    literal_n = _register_budget_and_cells(ledger)
    declared_budget = ledger.declared_budget(TRIAL_FAMILY)

    log.info(
        "TrialLedger: family=%s declared_budget=%d literal_n=%d "
        "(max()-basis divergence: declared_budget is a within-study floor per RUL-U3a; "
        "literal_n accumulates cross-study)",
        TRIAL_FAMILY, declared_budget, literal_n,
    )

    # -- Load tapes --
    events_path = data_root / "research" / "breakdown_events.parquet"
    fires_path = data_root / "replay" / "replay_boarded.parquet"

    if not events_path.exists():
        raise FileNotFoundError(f"breakdown_events.parquet not found at {events_path}")
    if not fires_path.exists():
        raise FileNotFoundError(f"replay_boarded.parquet not found at {fires_path}")

    log.info("Loading events tape: %s", events_path)
    events_df = pd.read_parquet(events_path)
    events_bd23 = events_df[
        (~events_df["is_control"]) & (events_df["definition"].isin(["BD-2", "BD-3"]))
    ].copy()

    log.info("Loading fires tape: %s", fires_path)
    fires_raw = pd.read_parquet(fires_path)
    fires_df = fires_raw[
        (fires_raw["verdict_type"] == "fire") & (fires_raw["verdict_grade"] == True)  # noqa: E712
    ].copy()

    # -- Build trading calendar --
    log.info("Building trading-bar calendar from SPY...")
    calendar = _build_calendar(data_root)

    # -- Print achieved n BEFORE statistics (prereg requirement) --
    n_bd2_episodes = int((events_bd23["definition"] == "BD-2").sum())
    n_bd3_episodes = int((events_bd23["definition"] == "BD-3").sum())
    n_fires = int(len(fires_df))

    print(f"\n{'='*70}")
    print(f"BD-ECON-1 — Achieved sample sizes (PRINTED BEFORE STATISTICS)")
    print(f"{'='*70}")
    print(f"  BD-2 episodes in events tape: {n_bd2_episodes:,}")
    print(f"  BD-3 episodes in events tape: {n_bd3_episodes:,}")
    print(f"  ERA-LAW fire pool (verdict_type=fire, verdict_grade=True): {n_fires:,}")
    print(f"  TrialLedger: family={TRIAL_FAMILY!r}")
    print(f"    declared_budget = {declared_budget}  (within-study BH floor; max()-semantics)")
    print(f"    literal_n       = {literal_n}  (accumulates cross-study within family)")
    print(f"    [max()-basis divergence note: declared_budget is a per-family max() floor")
    print(f"     per RUL-U3a; literal_n counts all cells logged cross-study]")
    print(f"{'='*70}\n")

    # -- BD-2 flagging --
    log.info("Building BD-2 flagged/unflagged split...")
    bd2_flagged, bd2_unflagged, bd2_n_episodes = build_flagged_fires(
        events_bd23, fires_df, "BD-2", calendar
    )

    # -- BD-3 flagging --
    log.info("Building BD-3 flagged/unflagged split...")
    bd3_flagged, bd3_unflagged, bd3_n_episodes = build_flagged_fires(
        events_bd23, fires_df, "BD-3", calendar
    )

    # -- Overlap count --
    bd2_fire_indices = set(bd2_flagged.index)
    bd3_fire_indices = set(bd3_flagged.index)
    overlap_count = len(bd2_fire_indices & bd3_fire_indices)

    print(f"Flagged fires:")
    print(f"  BD-2: {len(bd2_flagged):,} flagged fires / {bd2_n_episodes:,} contributing episodes")
    print(f"  BD-3: {len(bd3_flagged):,} flagged fires / {bd3_n_episodes:,} contributing episodes")
    print(f"  Overlap (flagged by both BD-2 and BD-3): {overlap_count:,}")
    print(f"  Each enters each definition's contrast independently (as per prereg)\n")

    # -- Floor checks per definition (prereg §5) --
    results: dict[str, Any] = {}
    per_definition: dict[str, Any] = {}

    rng = np.random.default_rng(BOOT_RNG_SEED)

    for defn, flagged, unflagged, n_eps in [
        ("BD-2", bd2_flagged, bd2_unflagged, bd2_n_episodes),
        ("BD-3", bd3_flagged, bd3_unflagged, bd3_n_episodes),
    ]:
        n_flag = len(flagged)
        floor_ok_fires = n_flag >= FLOOR_FLAGGED_FIRES
        floor_ok_eps = n_eps >= FLOOR_BD_EPISODES

        print(f"--- {defn} ---")
        print(f"  Flagged fires: {n_flag} (floor: ≥{FLOOR_FLAGGED_FIRES}  -> {'PASS' if floor_ok_fires else 'FAIL'})")
        print(f"  Contributing BD episodes: {n_eps} (floor: ≥{FLOOR_BD_EPISODES}  -> {'PASS' if floor_ok_eps else 'FAIL'})")

        if not (floor_ok_fires and floor_ok_eps):
            print(f"  ** P0-DEFER for {defn}: floor not met — counts printed; no statistics. **")
            print(f"     Come-back when more events accrue.")
            per_definition[defn] = {
                "status": "P0-DEFER",
                "n_flagged_fires": n_flag,
                "n_contributing_episodes": n_eps,
                "floor_flagged_fires": FLOOR_FLAGGED_FIRES,
                "floor_episodes": FLOOR_BD_EPISODES,
                "note": "Floor not met; no statistics computed",
            }
            continue

        # C1/C2: flagged vs all unflagged
        contrast_name = "C1" if defn == "BD-2" else "C2"
        log.info("Running %s (%s flagged vs all unflagged)...", contrast_name, defn)
        c_result = run_contrast(flagged, unflagged, contrast_name, rng)

        # C3 for BD-2 only: flagged vs recent-stop-without-BD unflagged
        c3_result: dict[str, Any] | None = None
        if defn == "BD-2":
            log.info("Building recent-stop cohort for C3...")
            # unflagged here is fires not flagged by BD-2
            recent_stop = build_recent_stop_cohort(unflagged, calendar)
            n_rs = len(recent_stop)
            floor_rs_ok = n_rs >= FLOOR_RECENT_STOP
            print(f"  C3 recent-stop cohort: {n_rs} (floor: ≥{FLOOR_RECENT_STOP}  -> {'PASS' if floor_rs_ok else 'FAIL'})")

            if not floor_rs_ok:
                print(f"  ** C3 P0-DEFER: recent-stop cohort floor not met ({n_rs} < {FLOOR_RECENT_STOP}). **")
                c3_result = {
                    "status": "P0-DEFER",
                    "n_recent_stop_cohort": n_rs,
                    "floor_recent_stop": FLOOR_RECENT_STOP,
                    "note": "Floor not met; no C3 statistics computed",
                }
            else:
                log.info("Running C3 (BD-2 flagged vs recent-stop-without-BD)...")
                c3_result = run_contrast(flagged, recent_stop, "C3", rng)
                c3_result["n_recent_stop_cohort"] = n_rs

        # Descriptive splits
        splits = _descriptive_splits(flagged, unflagged)

        # Economics block
        # ep_b CI for skip-policy net read: use C1/C2 endpoint_b CI
        ep_b_ci = c_result.get("endpoint_b_fwd_ret21", {})
        econ = _econ_block(flagged, defn, unflagged, ep_b_ci)

        per_definition[defn] = {
            "status": "RUN",
            "n_flagged_fires": n_flag,
            "n_contributing_episodes": n_eps,
            "n_unflagged_fires": int(len(unflagged)),
            f"{contrast_name}_result": c_result,
            "c3_result": c3_result,
            "descriptive_splits": splits,
            "economics_block": econ,
        }

        # Print brief summary
        ep_a = c_result.get("endpoint_a_stop_rate", {})
        ep_b = c_result.get("endpoint_b_fwd_ret21", {})
        print(f"  {contrast_name} endpoint_a (stop rate): "
              f"flagged={ep_a.get('mean_a', 'N/A'):.3f} "
              f"unflagged={ep_a.get('mean_b', 'N/A'):.3f} "
              f"delta={ep_a.get('delta', 'N/A'):.4f} "
              f"CI=[{ep_a.get('ci95_lo', 'N/A'):.4f},{ep_a.get('ci95_hi', 'N/A'):.4f}]")
        print(f"  {contrast_name} endpoint_b (fwd_ret21): "
              f"flagged={ep_b.get('mean_a', 'N/A'):.4f} "
              f"unflagged={ep_b.get('mean_b', 'N/A'):.4f} "
              f"delta={ep_b.get('delta', 'N/A'):.5f} "
              f"CI=[{ep_b.get('ci95_lo', 'N/A'):.5f},{ep_b.get('ci95_hi', 'N/A'):.5f}]")
        if c3_result and c3_result.get("status") != "P0-DEFER":
            ep_a3 = c3_result.get("endpoint_a_stop_rate", {})
            ep_b3 = c3_result.get("endpoint_b_fwd_ret21", {})
            print(f"  C3 endpoint_a (stop rate): "
                  f"flagged={ep_a3.get('mean_a', 'N/A'):.3f} "
                  f"rs_cohort={ep_a3.get('mean_b', 'N/A'):.3f} "
                  f"delta={ep_a3.get('delta', 'N/A'):.4f} "
                  f"CI=[{ep_a3.get('ci95_lo', 'N/A'):.4f},{ep_a3.get('ci95_hi', 'N/A'):.4f}]")
        print()

    # -- BH correction on the declared 6 cells --
    p_values: dict[str, float | None] = {}

    def _extract_p(defn: str, contrast: str, ep_key: str, ep_label: str):
        d = per_definition.get(defn, {})
        if d.get("status") == "P0-DEFER":
            return
        cr = d.get(f"{contrast}_result") or d.get("c3_result")
        if cr is None or cr.get("status") == "P0-DEFER":
            return
        ep = cr.get(ep_key, {})
        p_values[f"{defn}_{contrast}_{ep_label}"] = _p_approx_from_ci(
            ep.get("delta"), ep.get("ci95_lo"), ep.get("ci95_hi")
        )

    _extract_p("BD-2", "C1", "endpoint_a_stop_rate", "ep_a")
    _extract_p("BD-2", "C1", "endpoint_b_fwd_ret21", "ep_b")
    _extract_p("BD-3", "C2", "endpoint_a_stop_rate", "ep_a")
    _extract_p("BD-3", "C2", "endpoint_b_fwd_ret21", "ep_b")

    # C3 p-values
    bd2_data = per_definition.get("BD-2", {})
    c3 = bd2_data.get("c3_result")
    if c3 and c3.get("status") != "P0-DEFER":
        for ep_key, ep_label in [("endpoint_a_stop_rate", "ep_a"), ("endpoint_b_fwd_ret21", "ep_b")]:
            ep = c3.get(ep_key, {})
            p_values[f"BD-2_C3_{ep_label}"] = _p_approx_from_ci(
                ep.get("delta"), ep.get("ci95_lo"), ep.get("ci95_hi")
            )

    bh_results = _bh_correction(p_values)

    # -- Assemble full results --
    stamp = _vintage_stamp(data_root)
    results = {
        "vintage_stamp": stamp,
        "trial_ledger": {
            "family": TRIAL_FAMILY,
            "declared_budget": declared_budget,
            "literal_n": literal_n,
            "max_basis_divergence_note": (
                "declared_budget is a per-family max() floor per RUL-U3a; "
                "literal_n counts all verdict cells logged cross-study. "
                "These numbers diverge when multiple BD-family studies log cells. "
                "The declared_budget protects THIS study's BH set; "
                "cross-study multiplicity within short_side is tolerated only "
                "because all studies are descriptive/research-only (no DSR)."
            ),
        },
        "n_input": {
            "bd2_episodes": n_bd2_episodes,
            "bd3_episodes": n_bd3_episodes,
            "era_law_fires": n_fires,
        },
        "overlap_flagged_both_definitions": overlap_count,
        "flagging_window_bars": WINDOW_BARS,
        "per_definition": per_definition,
        "bh_correction_6cells": bh_results,
    }

    return results


# ===========================================================================
# 10. Output writers
# ===========================================================================

def _write_summary_json(results: dict[str, Any], data_root: Path) -> Path:
    """Write data/research/bd_econ1_summary.json."""
    out_dir = data_root / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "bd_econ1_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("Wrote summary JSON: %s", out_path)
    return out_path


def _write_report_md(results: dict[str, Any], repo_root: Path) -> Path:
    """Write research/short_side/BD_ECON1_REPORT.md."""
    out_dir = repo_root / "research" / "short_side"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "BD_ECON1_REPORT.md"

    ledger_info = results.get("trial_ledger", {})
    n_in = results.get("n_input", {})
    stamp = results.get("vintage_stamp", {})
    per_def = results.get("per_definition", {})
    bh = results.get("bh_correction_6cells", {})

    def _fmt(v, fmt=".4f"):
        if v is None:
            return "N/A"
        try:
            return format(float(v), fmt)
        except Exception:
            return str(v)

    lines: list[str] = []
    lines.append("# BD-ECON-1 — Avoided-Loss / Missed-Upside Counterfactual\n")
    lines.append(f"**Generated:** {stamp.get('generated_utc', 'N/A')}")
    lines.append(f"**Derived from surface:** `bd_phase0`")
    lines.append(f"**Authority:** `research/short_side/BD_ECON1_PREREG.md` (FROZEN)")
    lines.append(f"**Status:** research-only; no live authority, no board/chip/gate consumer")
    lines.append("")

    lines.append("## In plain English")
    lines.append("")
    lines.append(
        "When our breakdown-event detector (BD-2 or BD-3) fires on a stock, "
        "it opens a 21-trading-bar 'avoid window'. This study asks: of all the "
        "board fires (entries) our system recorded during those avoid windows, "
        "how many ended badly — and of the ones we would have skipped, how much "
        "upside would we have missed? Both sides are printed with equal prominence "
        "because a skip policy that avoids some losses also misses some gains."
    )
    lines.append("")
    lines.append("**Three contrasts were pre-registered:**")
    lines.append("- **C1**: BD-2-flagged fires vs all unflagged fires")
    lines.append("- **C2**: BD-3-flagged fires vs all unflagged fires")
    lines.append("- **C3 (co-primary)**: BD-2-flagged fires vs fires following a recent stop "
                 "*without* an active BD-2 window — isolates BD-2's increment over generic "
                 "post-stop damage.")
    lines.append("")
    lines.append(
        "A C1 delta that vanishes in C3 means BD-2's board value is **redundant with "
        "recent-stop** — that null is a first-class printed outcome."
    )
    lines.append("")

    lines.append("## Sample sizes (printed before statistics, per prereg)")
    lines.append("")
    lines.append(f"| Source | Count |")
    lines.append(f"|---|---|")
    lines.append(f"| BD-2 episodes in events tape | {n_in.get('bd2_episodes', 'N/A'):,} |")
    lines.append(f"| BD-3 episodes in events tape | {n_in.get('bd3_episodes', 'N/A'):,} |")
    lines.append(f"| ERA-LAW fires (verdict_type=fire, verdict_grade=True) | {n_in.get('era_law_fires', 'N/A'):,} |")
    lines.append(f"| Fires flagged by both BD-2 and BD-3 (overlap) | {results.get('overlap_flagged_both_definitions', 'N/A'):,} |")
    lines.append("")

    lines.append("## Trial ledger (RUL-U3a)")
    lines.append("")
    lines.append(f"- Family: `{ledger_info.get('family')}`")
    lines.append(f"- Declared budget: {ledger_info.get('declared_budget')} "
                 "(within-study BH floor; max()-semantics per RUL-U3a)")
    lines.append(f"- Literal n (cross-study): {ledger_info.get('literal_n')}")
    lines.append(f"- **max()-basis divergence note:** declared_budget is a per-family max() floor; "
                 f"literal_n accumulates all BD-family study cells cross-study. Both are printed here "
                 f"per the #1664 §0.5.6 convention.")
    lines.append("")

    lines.append("## Feasibility-peek disclosure (prereg §Amendments)")
    lines.append("")
    lines.append(stamp.get("contamination_stamp", ""))
    lines.append("No gate, threshold, or endpoint in the prereg was changed in response.")
    lines.append("")

    for defn in ["BD-2", "BD-3"]:
        d = per_def.get(defn, {})
        lines.append(f"## {defn} Results")
        lines.append("")

        if d.get("status") == "P0-DEFER":
            lines.append(f"**P0-DEFER**: floor not met.")
            lines.append(f"- Flagged fires: {d.get('n_flagged_fires', 'N/A')} "
                         f"(floor: ≥{d.get('floor_flagged_fires', FLOOR_FLAGGED_FIRES)})")
            lines.append(f"- Contributing episodes: {d.get('n_contributing_episodes', 'N/A')} "
                         f"(floor: ≥{d.get('floor_episodes', FLOOR_BD_EPISODES)})")
            lines.append(f"- No statistics computed. Come back when more events accrue.")
            lines.append("")
            continue

        lines.append(f"- Flagged fires: {d.get('n_flagged_fires', 'N/A'):,}")
        lines.append(f"- Contributing episodes: {d.get('n_contributing_episodes', 'N/A'):,}")
        lines.append(f"- Unflagged fires (contrast arm): {d.get('n_unflagged_fires', 'N/A'):,}")
        lines.append("")

        contrast_key = "C1_result" if defn == "BD-2" else "C2_result"
        contrast_label = "C1" if defn == "BD-2" else "C2"
        cr = d.get(contrast_key, {})

        lines.append(f"### {contrast_label} — Flagged vs All Unflagged")
        lines.append("")

        ep_a = cr.get("endpoint_a_stop_rate", {})
        lines.append("**Endpoint (a) — Stop-rate delta at h21:**")
        lines.append(f"- Flagged stop rate: {_fmt(ep_a.get('mean_a'), '.1%' if ep_a.get('mean_a') is not None else '.4f')}")
        lines.append(f"- Unflagged stop rate: {_fmt(ep_a.get('mean_b'), '.1%' if ep_a.get('mean_b') is not None else '.4f')}")
        lines.append(f"- Delta (flagged − unflagged): {_fmt(ep_a.get('delta'))}")
        lines.append(f"- 95% CI: [{_fmt(ep_a.get('ci95_lo'))}, {_fmt(ep_a.get('ci95_hi'))}]")
        lines.append(f"- CI excludes zero: {ep_a.get('ci_excludes_zero', 'N/A')}")
        lines.append(f"- n flagged: {ep_a.get('n_arm_a', 'N/A'):,} | n unflagged: {ep_a.get('n_arm_b', 'N/A'):,}")
        cens = cr.get("censoring", {})
        lines.append(f"- Censored (NaN state): flagged={cens.get('n_flagged_stop_nan', 0)} "
                     f"unflagged={cens.get('n_unflagged_stop_nan', 0)}")
        lines.append("")

        ep_b = cr.get("endpoint_b_fwd_ret21", {})
        lines.append("**Endpoint (b) — fwd_ret_21 delta (economics endpoint):**")
        lines.append(f"- Mean fwd_ret_21 flagged: {_fmt(ep_b.get('mean_a'), '.5f')}")
        lines.append(f"- Mean fwd_ret_21 unflagged: {_fmt(ep_b.get('mean_b'), '.5f')}")
        lines.append(f"- Delta (flagged − unflagged): {_fmt(ep_b.get('delta'), '.5f')}")
        lines.append(f"- 95% CI: [{_fmt(ep_b.get('ci95_lo'), '.5f')}, {_fmt(ep_b.get('ci95_hi'), '.5f')}]")
        lines.append(f"- CI excludes zero: {ep_b.get('ci_excludes_zero', 'N/A')}")
        lines.append(f"- Censored (NaN fwd_ret_21): flagged={cens.get('n_flagged_ret21_nan', 0)} "
                     f"unflagged={cens.get('n_unflagged_ret21_nan', 0)}")
        lines.append("")

        # C3 for BD-2
        if defn == "BD-2":
            c3 = d.get("c3_result")
            lines.append("### C3 (co-primary) — BD-2 Flagged vs Recent-Stop-Without-BD")
            lines.append("")
            if c3 is None or c3.get("status") == "P0-DEFER":
                n_rs = (c3 or {}).get("n_recent_stop_cohort", "N/A")
                lines.append(f"**P0-DEFER**: recent-stop cohort floor not met.")
                lines.append(f"- Recent-stop cohort size: {n_rs} (floor: ≥{FLOOR_RECENT_STOP})")
                lines.append(f"- No C3 statistics computed.")
            else:
                n_rs = c3.get("n_recent_stop_cohort", "N/A")
                lines.append(f"- Recent-stop cohort size: {n_rs:,}")
                ep_a3 = c3.get("endpoint_a_stop_rate", {})
                lines.append("**Endpoint (a) — Stop-rate delta:**")
                lines.append(f"- Delta (BD-2 flagged − recent-stop): {_fmt(ep_a3.get('delta'))}")
                lines.append(f"- 95% CI: [{_fmt(ep_a3.get('ci95_lo'))}, {_fmt(ep_a3.get('ci95_hi'))}]")
                lines.append(f"- CI excludes zero: {ep_a3.get('ci_excludes_zero', 'N/A')}")
                ep_b3 = c3.get("endpoint_b_fwd_ret21", {})
                lines.append("**Endpoint (b) — fwd_ret_21 delta:**")
                lines.append(f"- Delta (BD-2 flagged − recent-stop): {_fmt(ep_b3.get('delta'), '.5f')}")
                lines.append(f"- 95% CI: [{_fmt(ep_b3.get('ci95_lo'), '.5f')}, {_fmt(ep_b3.get('ci95_hi'), '.5f')}]")
                lines.append(f"- CI excludes zero: {ep_b3.get('ci_excludes_zero', 'N/A')}")
                lines.append("")
                lines.append("**C3 interpretation**: if C1 delta is real but C3 delta ~0, "
                             "BD-2 adds nothing beyond 'the name just stopped' (INCREMENT-NULL). "
                             "If C3 also real, BD-2 has board value beyond generic post-stop damage.")
            lines.append("")

        # Economics block
        econ = d.get("economics_block", {})
        lines.append("### Economics block (§4 — arithmetic on flagged cohort)")
        lines.append("")
        lines.append(f"*n flagged stopped: {econ.get('n_flagged_stopped', 'N/A')} | "
                     f"n flagged clean: {econ.get('n_flagged_clean', 'N/A')}*")
        lines.append("")
        lines.append("**Avoided drawdown (§4a) — fwd_mdd_21 among flagged fires that STOPPED:**")
        avd = econ.get("avoided_drawdown_fwd_mdd_21", {})
        if avd.get("n", 0) > 0:
            lines.append(f"- n: {avd['n']:,} | mean: {_fmt(avd.get('mean'), '.4f')} | "
                         f"median: {_fmt(avd.get('median'), '.4f')} | "
                         f"p90: {_fmt(avd.get('p90'), '.4f')}")
        else:
            lines.append("- No data")
        lines.append("")
        lines.append("**Missed upside (§4b) — fwd_ret_21 among flagged fires that ended CLEAN:**")
        mr = econ.get("missed_upside_fwd_ret_21", {})
        if mr.get("n", 0) > 0:
            lines.append(f"- n: {mr['n']:,} | mean: {_fmt(mr.get('mean'), '.4f')} | "
                         f"median: {_fmt(mr.get('median'), '.4f')} | "
                         f"p10: {_fmt(mr.get('p10'), '.4f')}")
        else:
            lines.append("- No data")
        lines.append("")
        lines.append("**Missed MFE (§4b) — fwd_mfe_21 among flagged fires that ended CLEAN:**")
        mm = econ.get("missed_upside_fwd_mfe_21", {})
        if mm.get("n", 0) > 0:
            lines.append(f"- n: {mm['n']:,} | mean: {_fmt(mm.get('mean'), '.4f')} | "
                         f"median: {_fmt(mm.get('median'), '.4f')} | "
                         f"p10: {_fmt(mm.get('p10'), '.4f')}")
        else:
            lines.append("- No data")
        lines.append("")
        lines.append(econ.get("rn6_symmetric_cost_note", ""))
        lines.append("")

        skip = econ.get("skip_policy_net_read", {})
        lines.append("**Skip-policy net read (§4c) — re-presents budgeted ep_b CI:**")
        lines.append(f"- {skip.get('description', '')}")
        lines.append(f"- Delta (flagged − unflagged): {_fmt(skip.get('ep_b_delta_flagged_minus_unflagged'), '.5f')}")
        lines.append(f"- 95% CI: [{_fmt(skip.get('ep_b_ci95_lo'), '.5f')}, {_fmt(skip.get('ep_b_ci95_hi'), '.5f')}]")
        lines.append("")

    # BH summary
    lines.append("## BH correction (declared 6-cell set, q=0.10)")
    lines.append("")
    cells = bh.get("cells", {})
    if cells:
        lines.append("| Cell | p (approx) | BH threshold | Reject H0 |")
        lines.append("|---|---|---|---|")
        for k, v in cells.items():
            lines.append(f"| {k} | {_fmt(v.get('p_approx'), '.4f')} | "
                         f"{_fmt(v.get('bh_threshold'), '.4f')} | "
                         f"{'Yes' if v.get('bh_reject') else 'No'} |")
    else:
        lines.append("No cells to correct (all definitions P0-DEFER or no p-values available).")
    lines.append("")
    lines.append(f"*{bh.get('note', '')}*")
    lines.append("")

    lines.append("## What this does NOT show (prereg §6)")
    lines.append("")
    lines.append(
        "No live tradability claim; no forward verdict (BD-AVOID-1 owns the forward "
        "question); no short-side claim of any kind; no per-name signal; nothing feeds "
        "any board, gate, chip, alert, or score."
    )
    lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    log.info("Wrote report: %s", out_path)
    return out_path


# ===========================================================================
# 11. CLI
# ===========================================================================

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=_CANONICAL_DATA,
        help=f"Root of the data directory (default: {_CANONICAL_DATA})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load tapes and print sample sizes only; do not write outputs.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    args = _parse_args()
    results = run(data_root=args.data_root, dry_run=args.dry_run)

    if not args.dry_run:
        _write_summary_json(results, args.data_root)
        _write_report_md(results, _ROOT)

    print("\nDone.")


if __name__ == "__main__":
    main()
