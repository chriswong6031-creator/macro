"""engine/rotation_universe.py — cross-sector rotation universe resolver (Rotation Events v2).

Loads config/rotation_universe.json (or a passed-in dict) and resolves each series
spec to a daily close Series. Three kinds:

  • etf             — basket_index._load_member_ohlcv(ticker)["close"]
  • basket_composite — sector_legs._basket_close(basket, membership) (EW consolidated_candle,
                       pit=False). This is the MANDATORY MAG7 path — MAGS ETF is rejected.
  • ticker_ew       — sector_legs._ew_close(tickers)

Hard invariant: any spec naming ticker "MAGS" raises ValueError (Constraint 7 defense).
MIN_BARS=300: series shorter than this are dropped with a disclosed coverage warning.

resolve_all(universe) memoizes basket composite results by key so mag7 is resolved once.

Also provides:
  momentum_stack(closes, bench)  — mom5/10/20/60 + SPY-relative rs_n + accel10
  _confirm_transition(signal_arr, confirm_days)  — 2-session hysteresis gate
  PARAMS_V2                      — all v2 detector parameters (canonical)
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

import numpy as np
import pandas as pd

from engine import basket_index, sector_legs
from lib import config

log = logging.getLogger(__name__)

MIN_BARS = 300   # mirror sector_legs.MIN_BARS — thin series dropped with warning

# ------------------------------------------------------------------ parameters ----

PARAMS_V2: dict = {
    # momentum
    "mom_windows": [5, 10, 20, 60],
    "accel_lag": 5,
    # family B — into_strength
    "into_off_low_min": 0.08,          # receiver must be ≥8% off its 40d low
    "into_rel_lead": 0.05,             # receiver SPY-relative 20d return ≥5pp
    "into_ratio_chg_min": 0.05,        # ratio 20d change ≥5% (OR 20d high)
    "into_breadth_min": 0.65,          # receiver breadth above-50d ≥65%
    "into_breadth_rise_len": 5,        # ...and rising over 5 sessions
    # family C — donor_state / contagion_bleed
    "bleed_low_lookback": 40,          # at 40d low (with 1% tolerance)
    "bleed_low_tol": 1.01,             # close <= min(last 40) * 1.01
    "bleed_rs20_max": -0.03,           # donor SPY-relative 20d return ≤ −3pp
    # family D — correlation_regime_break
    "corr_win": 10,                    # rolling correlation window
    "corr_prior_lag": 7,               # lag for computing corr rise
    "corr_raw_level": 0.45,            # raw corr current ≥ 0.45
    "corr_raw_rise": 0.25,             # raw corr rose ≥ 0.25 over the lag
    "corr_resid_rise": 0.20,           # SPY-residual corr rose ≥ 0.20 (idio regime change)
    "corr_base_max": 0.30,             # 20d baseline corr was ≤ 0.30 (was diversifying)
    "both_fell_min": 3,                # ≥3 of last 10 sessions both fell together
    "both_fell_window": 10,
    "attribution_beta_win": 60,        # SPY beta estimation window (days)
    "attribution_L": 7,                # idiosyncratic 7-session window for attribution
    # family E — health / lifecycle
    "lapse_warn": 2,                   # lapse_count ≥ 2 → weakening
    "neg_warn": 2,                     # neg_run ≥ 2 → weakening
    "lapse_run": 5,                    # close after N consecutive non-firing sessions
    "ratio_exit_run": 3,               # close after N consecutive negative-slope sessions
    "ttl_sessions": 20,                # hard time-to-live
    "lockout_sessions": 15,            # closed pair re-fire lockout (v2: 15 vs v1: 10)
    "confirm_days": 2,                 # 2-session hysteresis on every family transition
    # coldstart
    "start_backscan": 12,
    "coldstart_backscan": 15,
}


# ------------------------------------------------------------------ universe I/O ----

def load_universe(path=None) -> dict:
    """Load config/rotation_universe.json (or a custom path). Raises on missing/corrupt."""
    if path is None:
        path = config.ROOT / "config" / "rotation_universe.json"
    return json.loads(open(path).read())


# ------------------------------------------------------------------ series resolver ----

def resolve_series(spec: dict, membership: dict) -> tuple[pd.Series | None, dict]:
    """Resolve one series spec to a daily close Series + coverage meta.

    spec: one entry from universe["series"], e.g.:
      {"key":"xlk","kind":"etf","ticker":"XLK",...}
      {"key":"mag7_basket","kind":"basket_composite","basket":"mag7",...}

    Hard rejects:
      - any spec with ticker == "MAGS" raises ValueError (Constraint 7 defense)
      - series shorter than MIN_BARS dropped with a coverage warning

    Returns (series_or_None, meta_dict).
    """
    ticker = spec.get("ticker", "")
    if ticker.upper() == "MAGS":
        raise ValueError(
            "rotation_universe: spec names ticker MAGS — forbidden (Constraint 7). "
            "Use basket_composite kind with basket='mag7' instead."
        )

    kind = spec.get("kind", "etf")
    key = spec.get("key", "?")

    if kind == "etf":
        df = basket_index._load_member_ohlcv(ticker)
        if df is None or "close" not in df:
            log.warning("rotation_universe: etf %s not found — dropped", ticker)
            return None, {"key": key, "kind": kind, "ticker": ticker, "error": "not_found"}
        s = df["close"].dropna()
        meta = {"key": key, "kind": kind, "ticker": ticker, "n_bars": len(s)}

    elif kind == "basket_composite":
        basket = spec.get("basket")
        if not basket:
            log.warning("rotation_universe: basket_composite %s has no basket key — dropped", key)
            return None, {"key": key, "kind": kind, "error": "no_basket_key"}
        s, bm = sector_legs._basket_close(basket, membership)
        meta = {"key": key, "kind": kind, "basket": basket, **bm,
                "n_bars": len(s) if s is not None else 0}
        if s is None:
            log.warning("rotation_universe: basket_composite %s (%s) resolved None — dropped",
                        key, basket)
            return None, meta

    elif kind == "ticker_ew":
        tickers = spec.get("tickers", [])
        if not tickers:
            log.warning("rotation_universe: ticker_ew %s has no tickers — dropped", key)
            return None, {"key": key, "kind": kind, "error": "no_tickers"}
        s, em = sector_legs._ew_close(tickers)
        meta = {"key": key, "kind": kind, "tickers": tickers, **em,
                "n_bars": len(s) if s is not None else 0}
        if s is None:
            log.warning("rotation_universe: ticker_ew %s resolved None — dropped", key)
            return None, meta

    else:
        log.warning("rotation_universe: unknown kind %r for key %s — dropped", kind, key)
        return None, {"key": key, "kind": kind, "error": f"unknown_kind_{kind}"}

    # MIN_BARS check — same rule as sector_legs.leg_close
    if len(s) < MIN_BARS:
        log.warning(
            "rotation_universe: series %s has only %d bars (<%d MIN_BARS) — dropped; "
            "coverage gap disclosed",
            key, len(s), MIN_BARS,
        )
        meta["thin_history"] = len(s)
        return None, meta

    return s, meta


def resolve_all(universe: dict) -> dict:
    """Resolve every series in universe["series"] to closes; memoize basket composites.

    Returns:
      {series_key: pd.Series} for each successfully resolved series.
      Also populates the bench key from universe["bench"].

    Basket composite results are memoized by basket name so mag7 is built once
    even when multiple specs reference it.
    """
    membership = sector_legs.load_membership()
    basket_cache: dict[str, tuple[pd.Series | None, dict]] = {}

    closes: dict[str, pd.Series] = {}
    meta_out: dict[str, dict] = {}

    # resolve bench first (SPY)
    bench_spec = universe.get("bench", {})
    bench_key = bench_spec.get("key", "spy")
    bench_s, bench_meta = resolve_series(bench_spec, membership)
    if bench_s is not None:
        closes[bench_key] = bench_s
    meta_out[bench_key] = bench_meta

    for spec in universe.get("series", []):
        key = spec.get("key")
        if not key:
            continue

        # memoize basket composites by basket name
        if spec.get("kind") == "basket_composite":
            bname = spec.get("basket", key)
            if bname not in basket_cache:
                basket_cache[bname] = resolve_series(spec, membership)
            s, meta = basket_cache[bname]
            meta_out[key] = {**meta, "key": key}
        else:
            s, meta = resolve_series(spec, membership)
            meta_out[key] = meta

        if s is not None:
            closes[key] = s

    return closes, meta_out


# ------------------------------------------------------------------ momentum stack ----

def momentum_stack(closes: dict[str, pd.Series], bench_key: str = "spy") -> dict[str, pd.DataFrame]:
    """Compute the momentum stack per series: mom5/10/20/60, SPY-relative rs_n, accel10.

    Returns {series_key: DataFrame(mom5, mom10, mom20, mom60, rs5, rs10, rs20, rs60, accel10)}.
    """
    bench = closes.get(bench_key)
    out: dict[str, pd.DataFrame] = {}

    for key, s in closes.items():
        if key == bench_key:
            continue
        rows: dict = {}
        for w in PARAMS_V2["mom_windows"]:
            rows[f"mom{w}"] = s.pct_change(w)
            if bench is not None:
                b = bench.reindex(s.index).ffill()
                rows[f"rs{w}"] = rows[f"mom{w}"] - b.pct_change(w)
            else:
                rows[f"rs{w}"] = rows[f"mom{w}"]
        # accel10 = 2·mom5 − mom10  (positive = accelerating)
        if "mom5" in rows and "mom10" in rows:
            rows["accel10"] = 2 * rows["mom5"] - rows["mom10"]
        out[key] = pd.DataFrame(rows, index=s.index)

    return out


# ------------------------------------------------------------------ hysteresis ----

def _confirm_transition(signal_series: pd.Series, confirm_days: int = 2) -> pd.Series:
    """2-session hysteresis: a candidate state must hold confirm_days consecutive
    sessions before the output flips to True. Mirrors regime_vector._apply_hysteresis
    semantics (a boolean signal must be True for confirm_days straight).

    Input:  boolean Series (True = condition holds this session)
    Output: boolean Series (True = condition confirmed for ≥ confirm_days consecutive)
    """
    s = signal_series.astype(bool)
    # rolling min over confirm_days: True iff all sessions in the window are True
    confirmed = s.rolling(confirm_days, min_periods=confirm_days).min().fillna(False).astype(bool)
    return confirmed
