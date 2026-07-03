"""engine/options_stamp.py — point-in-time options-state stamp for the US board ledger.

Part of the Options Alpha program (research/OPTIONS_ALPHA_MASTERPLAN.md, wave W1.3).

Given a fire ``(as_of, ticker)`` on ``data/us_board_ledger/retro_grades.parquet`` this
module returns a nullable options-state row from the PINNED positioning stores (ruling A6):

  * ``data/polygon_gex/summary_{SYM}.parquet`` — one row per date (DatetimeIndex), supplies
    ``opt_gamma_regime`` (gamma_regime), ``opt_dist_to_flip_pct`` (dist_to_flip_pct),
    ``opt_wall_up`` (magnet_up), ``opt_wall_down`` (magnet_down), ``opt_iv30`` (iv30).
  * ``data/polygon_gex/chains/{date}.parquet`` — per-contract OI/volume, supplies
    ``opt_doi_slope_5d`` (5-day normalized near-money call-OI slope; null when < 5 prior
    chain days exist) and ``opt_voi_flag`` (today's chain volume > yesterday's OI on ≥1
    near-money contract — a fresh-positioning marker).

``opt_iv_rank_252`` is created ALWAYS-NULL here (ruling A9): a separate post-merge PR
backfills it once the W1.1 IV-backfill series lands. This module NEVER computes it, even
if ``data/iv_history/`` appears.

PIT DISCIPLINE (hard rule, tested): a stamp for a fire on date ``D`` uses ONLY store data
with an as-of date ``≤ D``. summary rows are selected by the latest index date ``≤ D``;
chain days are the trading days whose ``asof ≤ D``. No lookahead is possible.

The ledger's ``as_of`` column is a STRING (``YYYY-MM-DD``); store dates are datetimes.
All comparisons are done on ``date`` objects to avoid tz / ms-precision traps.

Pure, side-effect-free, trivially testable: the two heavy readers are injectable so tests
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

# ── nullable stamp schema (ruling A6/A9) ─────────────────────────────────────
# Order is the canonical column order for the ledger schema-union.
STAMP_COLS: list[str] = [
    "opt_gamma_regime",     # str: 'long'|'short' (summary gamma_regime)
    "opt_dist_to_flip_pct",  # float: dist_to_flip_pct
    "opt_wall_up",          # float: magnet_up (call/upside wall level)
    "opt_wall_down",        # float: magnet_down (put/downside wall level)
    "opt_iv30",             # float: iv30
    "opt_iv_rank_252",      # float: ALWAYS NULL here (A9 — post-merge PR backfills)
    "opt_doi_slope_5d",     # float: 5d normalized near-money call-OI slope (null if <5 prior days)
    "opt_voi_flag",         # bool: today's vol > yesterday's OI on ≥1 near-money contract
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


def stamp_options_state(
    as_of,
    ticker: str,
    *,
    read_summary: Callable[[str], pd.DataFrame | None] | None = None,
    chain_dates: list[_dt.date] | None = None,
    read_chain: Callable[[_dt.date], pd.DataFrame | None] | None = None,
) -> dict:
    """Return the nullable options-state stamp for a fire ``(as_of, ticker)``.

    All eight ``STAMP_COLS`` are always present; any that cannot be computed from PIT data
    are None. ``opt_iv_rank_252`` is ALWAYS None here (ruling A9).

    Readers are injectable for testing; defaults read the pinned disk stores. Adjusted roots
    (numeric-suffixed, e.g. ``AAPL1``) are dropped rather than mis-parsed → all-null stamp."""
    d = _as_date(as_of)
    if d is None or not ticker or _ADJUSTED_ROOT.search(ticker):
        return dict(_NULL_STAMP)

    read_summary = read_summary or _default_read_summary
    read_chain = read_chain or _default_read_chain
    if chain_dates is None:
        chain_dates = _default_chain_dates()

    stamp = dict(_NULL_STAMP)
    stamp.update(_summary_stamp(d, read_summary(ticker)))
    stamp["opt_doi_slope_5d"] = _doi_slope_stamp(d, ticker, chain_dates, read_chain)
    stamp["opt_voi_flag"] = _voi_flag_stamp(d, ticker, chain_dates, read_chain)
    # opt_iv_rank_252 stays None by construction (A9)
    return stamp
