"""engine/options_stamp.py — point-in-time options-state stamp for the US board ledger.

Part of the Options Alpha program (research/OPTIONS_ALPHA_MASTERPLAN.md, waves W1.3 / W-C).

Given a fire ``(as_of, ticker)`` on ``data/us_board_ledger/retro_grades.parquet`` this
module returns a nullable options-state row from the PINNED positioning stores (ruling A6):

  * ``data/polygon_gex/summary_{SYM}.parquet`` — one row per date (DatetimeIndex), supplies
    ``opt_gamma_regime`` (gamma_regime), ``opt_dist_to_flip_pct`` (dist_to_flip_pct),
    ``opt_wall_up`` (magnet_up), ``opt_wall_down`` (magnet_down), ``opt_iv30`` (iv30).
  * ``data/polygon_gex/chains/{date}.parquet`` — per-contract OI/volume, supplies
    ``opt_doi_slope_5d`` (5-day normalized near-money call-OI slope; null when < 5 prior
    chain days exist) and ``opt_voi_flag`` (today's chain volume > yesterday's OI on ≥1
    near-money contract — a fresh-positioning marker).
  * ``data/options_skew/snapshots.parquet`` — per-ticker/date (date str column, underlying
    str column, skew float), supplies ``opt_skew`` (latest-PIT skew on fire date) and
    ``opt_skew_5d_chg`` (skew change over the prior 5 calendar days of available snapshots).
  * ``data/options_ivspread/snapshots.parquet`` — per-ticker/date, supplies
    ``opt_ivspread_rel`` (latest-PIT ivspread_rel on fire date).
  * ``engine/opex.py`` — calendar-based OPEX tagging (no OI needed), supplies
    ``opt_opex_days`` (trading days to next monthly OPEX, td_to_opex from opex.tag()).
  * Wall distances (derived from summary ``opt_wall_up``/``opt_wall_down`` vs the summary
    spot): ``opt_wall_dist_up_pct`` = (wall_up / spot − 1) × 100, positive = above spot;
    ``opt_wall_dist_down_pct`` = (wall_down / spot − 1) × 100, negative = below spot.
  * ``opt_pin_risk`` (bool): True when OPEX proximity + long gamma + near wall converge
    (``opt_opex_days ≤ 5 AND opt_gamma_regime = 'long' AND
    min(|opt_wall_dist_up_pct|, |opt_wall_dist_down_pct|) ≤ 2%``).

``opt_iv_rank_252`` is created ALWAYS-NULL here (ruling A9): a separate post-merge PR
backfills it once the W1.1 IV-backfill series lands. This module NEVER computes it, even
if ``data/iv_history/`` appears.

PIT DISCIPLINE (hard rule, tested): a stamp for a fire on date ``D`` uses ONLY store data
with an as-of date ``≤ D``. summary rows are selected by the latest index date ``≤ D``;
chain days are the trading days whose ``asof ≤ D``; skew/ivspread rows are selected by the
latest ``date`` column value ``≤ D``; opex uses only the calendar date D. No lookahead.

The ledger's ``as_of`` column is a STRING (``YYYY-MM-DD``); store dates are datetimes.
All comparisons are done on ``date`` objects to avoid tz / ms-precision traps.

Pure, side-effect-free, trivially testable: all heavy readers are injectable so tests
feed synthetic frames without touching disk.
"""
from __future__ import annotations

import datetime as _dt
import glob
import math
import re
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from lib import config

# ── nullable stamp schema (ruling A6/A9; W-C additions 2026-07-05; W-OVC 2026-07-17) ─
# Order is the canonical column order for the ledger schema-union.
STAMP_COLS: list[str] = [
    "opt_gamma_regime",          # str: 'long'|'short' (summary gamma_regime)
    "opt_dist_to_flip_pct",      # float: dist_to_flip_pct
    "opt_wall_up",               # float: magnet_up (call/upside wall level)
    "opt_wall_down",             # float: magnet_down (put/downside wall level)
    "opt_iv30",                  # float: iv30
    "opt_iv_rank_252",           # float: ALWAYS NULL here (A9 — post-merge PR backfills)
    "opt_doi_slope_5d",          # float: 5d normalized near-money call-OI slope (null if <5 prior days)
    "opt_voi_flag",              # bool: today's vol > yesterday's OI on ≥1 near-money contract
    # W-C additions (2026-07-05) — new buckets S-IVSPREAD-F/S-SKEW_DECEL/S-TOP_RISK/S-PIN_RISK/S-VOI2
    "opt_ivspread_rel",          # float: call-put IV spread (rel, from ivspread snapshots); PIT ≤ as_of
    "opt_skew",                  # float: 30d OTM put IV minus ATM call IV (from skew snapshots); PIT ≤ as_of
    "opt_skew_5d_chg",           # float: opt_skew change over prior 5 calendar days of available snapshots
    "opt_opex_days",             # int: trading days to next monthly OPEX (td_to_opex from opex.tag())
    "opt_pin_risk",              # bool: opex_days<=5 AND gamma='long' AND min wall dist <=2% (S-PIN_RISK)
    "opt_wall_dist_up_pct",      # float: (wall_up/spot - 1)*100 — positive = how far above spot
    "opt_wall_dist_down_pct",    # float: (wall_down/spot - 1)*100 — negative = how far below spot
    # W-OVC additions (2026-07-17) — S-VANNA-RELIEF / S-FRONT-CHARM gate primitives
    "opt_vanna_relief",          # bool: iv30_5d_chg < 0 AND vanna_hedge_5d in top cross-sectional tercile
                                 #       per as_of (holdability / de-escalation state; caution-only RO-3)
    "opt_front7_charm_share",    # float: |charm| OI-weighted notional share for expiries ≤7 calendar days
                                 #        as fraction of total board; null when chain absent; S-FRONT-CHARM
    "opt_root_class",            # str: index_etf | sector_etf | industry_etf | single_name (display context)
                                 #      mandatory alongside opt_front7_charm_share (ETF sign era-unstable)
]

# Coverage-gated columns: these require an external data store (polygon_gex, skew snapshots,
# ivspread snapshots) to be non-null.  opt_opex_days is EXCLUDED because it is computed from
# a local calendar (engine/opex.py) and will be non-null on virtually every valid business date
# regardless of whether any options store has coverage for the ticker.
#
# The stamp_ledger retry gate (scripts/stamp_options_state.py) uses STAMP_COVERAGE_COLS — NOT
# STAMP_COLS — to decide whether a row is "unstamped" and eligible for future re-stamping.
# This preserves the W1.3 design: rows with only calendar-derived columns (opt_opex_days) remain
# fully retryable when GEX/skew/ivspread coverage later arrives.
# opt_opex_days: excluded because it is calendar-derived (non-null on every business date).
# opt_root_class: excluded because it is taxonomy-derived from the ticker alone (non-null
#   for every ticker; equivalent to opt_opex_days in that it needs no data store).
STAMP_COVERAGE_COLS: list[str] = [
    c for c in STAMP_COLS if c not in ("opt_opex_days", "opt_root_class")
]

# every stamp starts as all-None so a name with no options coverage yields a clean null row
_NULL_STAMP: dict = {c: None for c in STAMP_COLS}

# near-money band (fraction of spot) for the chain-derived signals
_NEAR_MONEY_FRAC = 0.10
# window length for the ΔOI slope: today + 5 prior trading snapshots = 6 points
_DOI_WINDOW = 6
# roots with a numeric suffix (e.g. AAPL1) are corporate-action-adjusted — never mis-parse
_ADJUSTED_ROOT = re.compile(r"\d$")


def _summary_dir() -> Path:
    return config.data_dir() / "polygon_gex"


def _chains_dir() -> Path:
    return config.data_dir() / "polygon_gex" / "chains"


def _as_date(x) -> _dt.date | None:
    """Coerce a string/date/Timestamp to a plain date, or None."""
    if x is None:
        return None
    if isinstance(x, _dt.date) and not isinstance(x, _dt.datetime):
        return x
    try:
        return pd.Timestamp(x).date()
    except (ValueError, TypeError):
        return None


# ── injectable readers (default = disk; tests pass fakes) ────────────────────
def _default_read_summary(ticker: str) -> pd.DataFrame | None:
    p = _summary_dir() / f"summary_{ticker}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:  # noqa: BLE001 — a corrupt per-name store must not break the whole pass
        return None


def _default_chain_dates() -> list[_dt.date]:
    """Sorted list of available chain snapshot dates (from the filenames)."""
    out: list[_dt.date] = []
    for f in glob.glob(str(_chains_dir() / "*.parquet")):
        stem = Path(f).stem
        d = _as_date(stem)
        if d is not None:
            out.append(d)
    return sorted(out)


def _default_read_chain(d: _dt.date) -> pd.DataFrame | None:
    p = _chains_dir() / f"{d.isoformat()}.parquet"
    if not p.exists():
        return None
    try:
        # only the columns the chain signals need
        return pd.read_parquet(
            p, columns=["underlying", "K", "is_call", "oi", "volume", "spot"]
        )
    except Exception:  # noqa: BLE001
        return None


def _default_read_skew_snapshots() -> pd.DataFrame | None:
    """Load data/options_skew/snapshots.parquet (all dates).

    W-C: supplies opt_skew + opt_skew_5d_chg for S-SKEW_DECEL / S-TOP_RISK buckets.
    Columns we use: date (str), underlying (str), skew (float).
    Returns None if file absent (not on the render path; gitignored R2 store)."""
    p = config.data_dir() / "options_skew" / "snapshots.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p, columns=["date", "underlying", "skew"])
    except Exception:  # noqa: BLE001
        return None


def _default_read_ivspread_snapshots() -> pd.DataFrame | None:
    """Load data/options_ivspread/snapshots.parquet (all dates).

    W-C: supplies opt_ivspread_rel for S-IVSPREAD-F / S-TOP_RISK buckets.
    Columns we use: date (str), underlying (str), ivspread_rel (float).
    Returns None if file absent."""
    p = config.data_dir() / "options_ivspread" / "snapshots.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p, columns=["date", "underlying", "ivspread_rel"])
    except Exception:  # noqa: BLE001
        return None


# ── summary-derived stamp (positioning state at the fire) ────────────────────
def _summary_stamp(as_of: _dt.date, sdf: pd.DataFrame | None) -> dict:
    """Latest summary row with index date ≤ as_of (PIT)."""
    out = {
        "opt_gamma_regime": None, "opt_dist_to_flip_pct": None,
        "opt_wall_up": None, "opt_wall_down": None, "opt_iv30": None,
    }
    if sdf is None or sdf.empty:
        return out
    idx_dates = pd.Index([_as_date(d) for d in sdf.index])
    mask = np.array([d is not None and d <= as_of for d in idx_dates])
    if not mask.any():
        return out
    # the last row on/before as_of
    row = sdf[mask].iloc[-1]

    def _f(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else f

    reg = row.get("gamma_regime")
    out["opt_gamma_regime"] = str(reg) if reg is not None and not (isinstance(reg, float) and math.isnan(reg)) else None
    out["opt_dist_to_flip_pct"] = _f(row.get("dist_to_flip_pct"))
    out["opt_wall_up"] = _f(row.get("magnet_up"))
    out["opt_wall_down"] = _f(row.get("magnet_down"))
    out["opt_iv30"] = _f(row.get("iv30"))
    return out


def _near_money_call_oi(chain: pd.DataFrame, ticker: str) -> float | None:
    """Near-money (±10% of spot) total call OI for one name in one chain snapshot."""
    sub = chain[chain["underlying"] == ticker]
    if sub.empty:
        return None
    spot = sub["spot"].iloc[0]
    try:
        spot = float(spot)
    except (TypeError, ValueError):
        return None
    if not (spot > 0):
        return None
    lo, hi = spot * (1 - _NEAR_MONEY_FRAC), spot * (1 + _NEAR_MONEY_FRAC)
    nm = sub[(sub["K"] >= lo) & (sub["K"] <= hi)]
    calls = nm[nm["is_call"]]
    if calls.empty:
        return None
    return float(calls["oi"].fillna(0).sum())


def _doi_slope_stamp(
    as_of: _dt.date,
    ticker: str,
    chain_dates: list[_dt.date],
    read_chain: Callable[[_dt.date], pd.DataFrame | None],
) -> float | None:
    """5-day normalized near-money call-OI slope over the ``_DOI_WINDOW`` most-recent chain
    snapshots with date ≤ as_of. Needs ≥ 5 prior days (6 points total) or returns None.

    Normalized = OLS slope / mean(series) so it is comparable across names. Positive =
    call-OI accumulating (informed-accumulation proxy, Garleanu-Pedersen-Poteshman)."""
    usable = [d for d in chain_dates if d <= as_of]
    if len(usable) < _DOI_WINDOW:
        return None
    window = usable[-_DOI_WINDOW:]
    series: list[float] = []
    for d in window:
        ch = read_chain(d)
        if ch is None:
            return None
        v = _near_money_call_oi(ch, ticker)
        if v is None:
            return None
        series.append(v)
    y = np.asarray(series, dtype=float)
    mean = float(y.mean())
    if not (mean > 0):
        return None
    x = np.arange(len(y), dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])
    return round(slope / mean, 6)


def _voi_flag_stamp(
    as_of: _dt.date,
    ticker: str,
    chain_dates: list[_dt.date],
    read_chain: Callable[[_dt.date], pd.DataFrame | None],
) -> bool | None:
    """Vol>OI fresh-positioning marker: True if, on the most-recent chain snapshot ≤ as_of,
    at least one near-money contract has today's volume > YESTERDAY's open interest.

    Requires the current + one prior snapshot; None when unavailable. Uses prior-day OI so
    the comparison is genuinely 'fresh volume against pre-existing positioning' (not vol vs
    same-day OI, which trivially includes the new trades)."""
    usable = [d for d in chain_dates if d <= as_of]
    if len(usable) < 2:
        return None
    today_d, prev_d = usable[-1], usable[-2]
    today = read_chain(today_d)
    prev = read_chain(prev_d)
    if today is None or prev is None:
        return None
    t = today[today["underlying"] == ticker]
    p = prev[prev["underlying"] == ticker]
    if t.empty or p.empty:
        return None
    try:
        spot = float(t["spot"].iloc[0])
    except (TypeError, ValueError):
        return None
    if not (spot > 0):
        return None
    lo, hi = spot * (1 - _NEAR_MONEY_FRAC), spot * (1 + _NEAR_MONEY_FRAC)
    t_nm = t[(t["K"] >= lo) & (t["K"] <= hi)].copy()
    if t_nm.empty:
        return None
    # prior-day OI keyed by (K, is_call) so we compare like contracts
    p_oi = (
        p.assign(_k=p["K"].round(4))
        .groupby(["_k", "is_call"])["oi"].sum()
    )
    t_nm["_k"] = t_nm["K"].round(4)
    fresh = False
    for _, r in t_nm.iterrows():
        vol = r.get("volume")
        try:
            vol = float(vol)
        except (TypeError, ValueError):
            continue
        prior_oi = p_oi.get((r["_k"], r["is_call"]))
        # prior OI of 0 (or missing) with real volume = brand-new positioning → fresh
        prior_oi = float(prior_oi) if prior_oi is not None else 0.0
        if vol > prior_oi and vol > 0:
            fresh = True
            break
    return bool(fresh)


# ── W-C: skew/ivspread/opex/wall-dist stamps ────────────────────────────────
# These are PIT-disciplined reads from the W-C snapshot stores.  They mirror the
# summary-derived stamp pattern: latest row with date ≤ as_of, null on absence.

def _skew_stamp(
    as_of: _dt.date,
    ticker: str,
    skew_df: pd.DataFrame | None,
) -> dict:
    """opt_skew + opt_skew_5d_chg from data/options_skew/snapshots.parquet.

    PIT: only rows with date ≤ as_of used. skew_5d_chg = latest minus the snapshot
    from ≥ 5 calendar days earlier (the earliest qualifying row that is ≥ 5 days back
    from the latest row date); None when fewer than 2 qualifying rows exist.

    Returns a dict with keys opt_skew, opt_skew_5d_chg (both float | None)."""
    out: dict = {"opt_skew": None, "opt_skew_5d_chg": None}
    if skew_df is None or skew_df.empty:
        return out
    sub = skew_df[skew_df["underlying"] == ticker].copy()
    if sub.empty:
        return out
    # PIT filter: date column is a string 'YYYY-MM-DD'
    sub["_d"] = sub["date"].apply(_as_date)
    sub = sub[sub["_d"].apply(lambda d: d is not None and d <= as_of)]
    if sub.empty:
        return out
    sub = sub.sort_values("_d")

    def _f(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else f

    latest = sub.iloc[-1]
    skew_val = _f(latest["skew"])
    out["opt_skew"] = skew_val

    if skew_val is not None and len(sub) >= 2:
        latest_date = latest["_d"]
        # look for a row at least 5 calendar days earlier than the latest snapshot date
        cutoff = latest_date - _dt.timedelta(days=5)
        earlier = sub[sub["_d"] <= cutoff]
        if not earlier.empty:
            prior_skew = _f(earlier.iloc[-1]["skew"])
            if prior_skew is not None:
                out["opt_skew_5d_chg"] = round(skew_val - prior_skew, 6)
    return out


def _ivspread_stamp(
    as_of: _dt.date,
    ticker: str,
    ivspread_df: pd.DataFrame | None,
) -> dict:
    """opt_ivspread_rel from data/options_ivspread/snapshots.parquet.

    PIT: only rows with date ≤ as_of. Returns dict with key opt_ivspread_rel."""
    out: dict = {"opt_ivspread_rel": None}
    if ivspread_df is None or ivspread_df.empty:
        return out
    sub = ivspread_df[ivspread_df["underlying"] == ticker].copy()
    if sub.empty:
        return out
    sub["_d"] = sub["date"].apply(_as_date)
    sub = sub[sub["_d"].apply(lambda d: d is not None and d <= as_of)]
    if sub.empty:
        return out
    sub = sub.sort_values("_d")

    def _f(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else f

    out["opt_ivspread_rel"] = _f(sub.iloc[-1]["ivspread_rel"])
    return out


def _opex_stamp(as_of: _dt.date) -> dict:
    """opt_opex_days from engine/opex.py calendar tags (no OI needed; PIT by construction).

    Returns dict with key opt_opex_days (int | None). Wraps in try/except so a missing
    or malformed calendar never breaks the whole stamp pass."""
    out: dict = {"opt_opex_days": None}
    try:
        from engine import opex as _opex  # local import — avoid circular at module level
        # build a small index spanning today ± 60 days to ensure we have a next-OPEX
        today_ts = pd.Timestamp(as_of)
        idx = pd.date_range(today_ts - pd.offsets.BDay(2), today_ts + pd.offsets.BDay(45), freq="B")
        tagged = _opex.tag(idx)
        row = tagged[tagged.index.date == as_of]
        if row.empty:
            return out
        td_to = row.iloc[0].get("td_to") if hasattr(row.iloc[0], "get") else row.iloc[0]["td_to"]
        if td_to is not None and not (isinstance(td_to, float) and math.isnan(td_to)):
            out["opt_opex_days"] = int(td_to)
    except Exception:  # noqa: BLE001 — opex calc failure must not break stamp pass
        pass
    return out


def _wall_dist_stamp(
    opt_wall_up: float | None,
    opt_wall_down: float | None,
    spot: float | None,
) -> dict:
    """Compute wall distance percentages from already-computed summary wall levels + spot.

    opt_wall_dist_up_pct  = (wall_up / spot - 1) * 100  (positive when wall is above spot)
    opt_wall_dist_down_pct = (wall_down / spot - 1) * 100  (negative when wall is below spot)

    The spot is taken from the summary row's spot column (not chain spot) to stay consistent
    with the GEX model's reference frame.  Returns dict with both keys."""
    out: dict = {"opt_wall_dist_up_pct": None, "opt_wall_dist_down_pct": None}
    if spot is None or not (spot > 0):
        return out
    if opt_wall_up is not None:
        out["opt_wall_dist_up_pct"] = round((opt_wall_up / spot - 1.0) * 100.0, 4)
    if opt_wall_down is not None:
        out["opt_wall_dist_down_pct"] = round((opt_wall_down / spot - 1.0) * 100.0, 4)
    return out


# ── W-OVC stamp functions (2026-07-17) ──────────────────────────────────────

def _default_read_chain_by_date(d: _dt.date) -> pd.DataFrame | None:
    """Read chains/{date}.parquet; returns None if absent or unreadable."""
    p = _chains_dir() / f"{d.isoformat()}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None


def _ovc_from_chain(
    as_of: _dt.date,
    ticker: str,
    chain_dates: list[_dt.date],
    read_chain: Callable[[_dt.date], pd.DataFrame | None],
) -> dict:
    """Compute W-OVC display columns from the chain snapshot on/before as_of.

    Returns dict with keys:
      opt_front7_charm_share  — float | None: |charm|-notional share for ≤7-calendar-day expiries
      opt_root_class          — str: index_etf | sector_etf | industry_etf | single_name

    PIT-disciplined: only the latest chain snapshot with date ≤ as_of is used.
    Null-safe: bs_greeks NaN on bad inputs; those contracts skipped silently.

    This function intentionally does NOT compute opt_vanna_relief (that requires cross-
    sectional tercile ranking across multiple tickers on the same as_of — done in the
    stamp_ledger pass, not here).

    OI TIMING (PIT-clean, matching the frozen study construction):
    The adjudicated study (options_opex_vanna_charm_study.py §340-343) builds front7_abs_charm_share
    from oi_signal = oi.groupby([expiration,strike,right])['open_interest'].shift(1) — prior-day OI
    per contract.  The adjudication §2 PIT-verification certifies the metric as clean precisely
    because of this shift.  This function replicates that construction:

      - Greeks (charm/T/iv) are taken from the CURRENT chain snapshot (usable[-1]) — same-day
        quote-derived inputs, matching the study merge of same-date greeks against shifted OI.
      - OI is taken from the PRIOR chain snapshot (usable[-2]) — pre-trade-day positions that
        do NOT include same-day fire-date trades (look-ahead).

    This matches _voi_flag_stamp's pattern (today chain for volume, prior chain for OI).
    When fewer than 2 usable snapshots exist the metric is null (cannot form prior-day OI).
    """
    # Import here to avoid circular dependency at module level
    from engine.greeks import bs_greeks
    from engine.options_entry_state import _root_class

    out: dict = {"opt_front7_charm_share": None, "opt_root_class": _root_class(ticker)}

    # Need at least 2 usable snapshots: current for greeks, prior for OI
    usable = [d for d in chain_dates if d <= as_of]
    if len(usable) < 2:
        return out
    chain_date = usable[-1]   # current snapshot — provides greeks (T, iv, spot, expiry)
    prev_date = usable[-2]    # prior snapshot — provides OI (pre-fire-day positions)

    cdf = read_chain(chain_date)
    if cdf is None or cdf.empty:
        return out
    prev_cdf = read_chain(prev_date)
    if prev_cdf is None or prev_cdf.empty:
        return out

    # required columns
    required = {"underlying", "K", "T", "iv", "oi", "is_call", "spot", "expiry"}
    if not required.issubset(set(cdf.columns)):
        return out
    if not required.issubset(set(prev_cdf.columns)):
        return out

    sub = cdf[cdf["underlying"] == ticker].copy()
    if sub.empty:
        return out

    # Build prior-OI lookup keyed by (K, is_call) — matching _voi_flag_stamp pattern
    prev_sub = prev_cdf[prev_cdf["underlying"] == ticker].copy()
    if not prev_sub.empty:
        prev_sub["_k"] = pd.to_numeric(prev_sub["K"], errors="coerce").round(4)
        prev_sub["oi"] = pd.to_numeric(prev_sub["oi"], errors="coerce")
        prior_oi_map = (
            prev_sub.dropna(subset=["_k", "oi"])
            .groupby(["_k", "is_call"])["oi"]
            .sum()
        )
    else:
        prior_oi_map = pd.Series(dtype=float)

    for col in ("K", "T", "iv", "spot"):
        sub[col] = pd.to_numeric(sub[col], errors="coerce")
    sub["_k"] = sub["K"].round(4)

    # days to expiry from the chain snapshot date
    def _dte(expiry_val) -> int | None:
        try:
            return (pd.Timestamp(expiry_val).date() - chain_date).days
        except Exception:
            return None

    sub = sub.copy()
    sub["_dte"] = sub["expiry"].apply(_dte)

    _MULT = 100.0
    abs_charm_total = 0.0
    abs_charm_front7 = 0.0

    for _, row in sub.iterrows():
        S, K_, T_, sigma = row["spot"], row["K"], row["T"], row["iv"]
        is_call = bool(row["is_call"])
        dte = row["_dte"]
        # Look up prior-day OI for this contract (keyed by rounded K + is_call)
        prior_oi = prior_oi_map.get((row["_k"], is_call))
        if prior_oi is None:
            continue
        try:
            oi_f = float(prior_oi)
            s_f = float(S)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(oi_f) and oi_f > 0 and math.isfinite(s_f) and s_f > 0):
            continue
        try:
            _delta, _gamma, _vanna, charm = bs_greeks(S, K_, T_, sigma, is_call)
        except Exception:
            continue
        if not math.isfinite(charm):
            continue
        sign = 1.0 if is_call else -1.0
        charm_not = abs(sign * (charm / 365.0) * oi_f * _MULT * s_f)
        abs_charm_total += charm_not
        if dte is not None and 0 <= dte <= 7:
            abs_charm_front7 += charm_not

    if abs_charm_total > 0:
        out["opt_front7_charm_share"] = round(abs_charm_front7 / abs_charm_total, 6)

    return out


def _vanna_hedge_5d_from_summary(
    as_of: _dt.date,
    sdf: pd.DataFrame | None,
) -> float | None:
    """Compute vanna_hedge_5d = −net_vex × iv30_5d_chg from summary frame.

    PIT: uses only rows with index date ≤ as_of. Needs ≥ 6 such rows.
    Returns None when insufficient history, columns absent, or any value non-finite.
    """
    if sdf is None or sdf.empty:
        return None
    if "net_vex" not in sdf.columns or "iv30" not in sdf.columns:
        return None
    idx_dates = [_as_date(d) for d in sdf.index]
    mask = [d is not None and d <= as_of for d in idx_dates]
    usable = sdf[mask]
    if len(usable) < 6:
        return None
    latest = usable.iloc[-1]
    prior = usable.iloc[-6]

    def _f(v) -> float | None:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return None if not math.isfinite(x) else x

    net_vex = _f(latest.get("net_vex"))
    iv30_latest = _f(latest.get("iv30"))
    iv30_prior = _f(prior.get("iv30"))
    if net_vex is None or iv30_latest is None or iv30_prior is None:
        return None
    iv30_5d_chg = iv30_latest - iv30_prior
    return round(-net_vex * iv30_5d_chg, 6)


def _pin_risk_flag(
    opt_opex_days: int | None,
    opt_gamma_regime: str | None,
    opt_wall_dist_up_pct: float | None,
    opt_wall_dist_down_pct: float | None,
) -> bool | None:
    """S-PIN_RISK: True when OPEX proximity + long-gamma + near-wall converge.

    Condition (per pre-registration §4 W-C):
      opt_opex_days <= 5
      AND opt_gamma_regime == 'long'
      AND min(|opt_wall_dist_up_pct|, |opt_wall_dist_down_pct|) <= 2%

    Returns None when any required input is None (cannot evaluate the condition)."""
    if opt_opex_days is None or opt_gamma_regime is None:
        return None
    if opt_wall_dist_up_pct is None and opt_wall_dist_down_pct is None:
        return None
    if not (opt_opex_days <= 5):
        return False
    if opt_gamma_regime != "long":
        return False
    dists = [abs(d) for d in (opt_wall_dist_up_pct, opt_wall_dist_down_pct) if d is not None]
    if not dists:
        return None
    return bool(min(dists) <= 2.0)


def stamp_options_state(
    as_of,
    ticker: str,
    *,
    read_summary: Callable[[str], pd.DataFrame | None] | None = None,
    chain_dates: list[_dt.date] | None = None,
    read_chain: Callable[[_dt.date], pd.DataFrame | None] | None = None,
    skew_df: pd.DataFrame | None = None,
    ivspread_df: pd.DataFrame | None = None,
    _skew_loader: Callable[[], pd.DataFrame | None] | None = None,
    _ivspread_loader: Callable[[], pd.DataFrame | None] | None = None,
) -> dict:
    """Return the nullable options-state stamp for a fire ``(as_of, ticker)``.

    All ``STAMP_COLS`` are always present; any that cannot be computed from PIT data
    are None. ``opt_iv_rank_252`` is ALWAYS None here (ruling A9).

    Readers are injectable for testing; defaults read the pinned disk stores. Adjusted roots
    (numeric-suffixed, e.g. ``AAPL1``) are dropped rather than mis-parsed → all-null stamp.

    Injectable parameters for W-C snapshot stores:
      skew_df       — pre-loaded skew snapshots DataFrame (or None to load from disk)
      ivspread_df   — pre-loaded ivspread snapshots DataFrame (or None to load from disk)
      _skew_loader  — callable that returns the DataFrame (overrides disk default)
      _ivspread_loader — same for ivspread

    The stamp_ledger pass pre-loads these DataFrames once and passes them in to avoid
    re-reading the parquet files for every (as_of, ticker) pair.
    """
    d = _as_date(as_of)
    if d is None or not ticker or _ADJUSTED_ROOT.search(ticker):
        return dict(_NULL_STAMP)

    read_summary = read_summary or _default_read_summary
    read_chain = read_chain or _default_read_chain
    if chain_dates is None:
        chain_dates = _default_chain_dates()

    # W-C snapshot frames: load once from disk if not pre-supplied
    if skew_df is None:
        loader = _skew_loader or _default_read_skew_snapshots
        skew_df = loader()
    if ivspread_df is None:
        loader = _ivspread_loader or _default_read_ivspread_snapshots
        ivspread_df = loader()

    stamp = dict(_NULL_STAMP)
    # W1.3 fields from GEX summary
    summary_s = _summary_stamp(d, read_summary(ticker))
    stamp.update(summary_s)
    stamp["opt_doi_slope_5d"] = _doi_slope_stamp(d, ticker, chain_dates, read_chain)
    stamp["opt_voi_flag"] = _voi_flag_stamp(d, ticker, chain_dates, read_chain)
    # opt_iv_rank_252 stays None by construction (A9)

    # W-C fields: skew / ivspread / opex / wall-dist / pin-risk
    stamp.update(_skew_stamp(d, ticker, skew_df))
    stamp.update(_ivspread_stamp(d, ticker, ivspread_df))
    stamp.update(_opex_stamp(d))

    # wall distances need spot from the summary row (same row as wall levels)
    spot = _spot_from_summary(d, read_summary(ticker))
    stamp.update(_wall_dist_stamp(stamp.get("opt_wall_up"), stamp.get("opt_wall_down"), spot))

    stamp["opt_pin_risk"] = _pin_risk_flag(
        stamp.get("opt_opex_days"),
        stamp.get("opt_gamma_regime"),
        stamp.get("opt_wall_dist_up_pct"),
        stamp.get("opt_wall_dist_down_pct"),
    )

    # W-OVC fields: front7_charm_share, root_class
    # opt_vanna_relief is NOT set here — it requires cross-sectional tercile ranking
    # across all fires on the same as_of, which is done in the stamp_ledger pass.
    ovc_data = _ovc_from_chain(d, ticker, chain_dates, read_chain)
    stamp["opt_front7_charm_share"] = ovc_data.get("opt_front7_charm_share")
    stamp["opt_root_class"] = ovc_data.get("opt_root_class")
    # opt_vanna_relief stays None; stamp_ledger sets it after cross-sectional ranking.
    # stamp["opt_vanna_relief"] is already None from _NULL_STAMP.

    return stamp


def _spot_from_summary(as_of: _dt.date, sdf: pd.DataFrame | None) -> float | None:
    """Extract spot price from the summary frame's 'spot' column (latest PIT row ≤ as_of).

    The GEX summary parquet may or may not carry a spot column; returns None if absent.
    This is used by _wall_dist_stamp to compute wall distances in percentage terms."""
    if sdf is None or sdf.empty:
        return None
    idx_dates = pd.Index([_as_date(d) for d in sdf.index])
    mask = np.array([d is not None and d <= as_of for d in idx_dates])
    if not mask.any():
        return None
    row = sdf[mask].iloc[-1]
    spot = row.get("spot")
    if spot is None:
        return None
    try:
        f = float(spot)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None
