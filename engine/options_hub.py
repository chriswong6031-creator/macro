"""engine/options_hub.py — nightly options analytics payloads for the Options Hub.

Pure, hermetic: given per-contract greeks + OI + EOD frames for one root,
produces the vol/{ROOT} and gex/{ROOT} payload dicts, plus the cross-root
oi_movers and hot_contracts payloads.

DEALER-SIGN CONVENTION (cite engine/gex_engine.py lines 158–163):
  sign = +1 for calls, -1 for puts.
  The DEALER is assumed LONG calls / SHORT puts — this is an unobservable
  assumption (robust for indices, fragile for single names).
  net_gex   = sign * gamma * OI[t-1] * mult * spot^2 * pm
  net_delta = sign * delta * OI[t-1] * mult * spot        (for by_strike rows)
  net_vanna = sign * vanna * OI[t-1] * mult * spot * pm   (scaled same as VEX)
  net_charm = sign * (charm / 365.0) * OI[t-1] * mult * spot  (daily delta drift)

OI TIMING LAW (engine/thetadata_store.py docstring):
  OPRA OI[t] represents end-of-previous-day positions. For any day-t signal,
  use OI[t-1] (shift(1)). Same-day OI is a lookahead bug. This module ONLY
  consumes pre-shifted OI frames (the caller is responsible for the shift).

CONTRACT UPGRADE OBJECTS (PAYLOAD CONTRACT v2):
  * VolPayload: iv_rank_all + coverage_days_all + since_all — full-history
    ATM-IV percentile using the complete greeks date range (not just 252 days).
    Null when < 60 observed sessions.
  * GexPayload.history: last 30 rows from data/polygon_gex/summary_{ROOT}.parquet,
    mapping magnet_up → call_wall, magnet_down → put_wall.  Omitted when absent.
  * options_hub/context.json: cross-root index GEX + fear/greed + sector ETF flows.
  * options_hub/tickers_ctx/{ROOT}.json: tape-flow z-scores from
    data/tape_flow/daily/{ROOT}.parquet; null unless history_n >= 20.
  * options_hub/oi_confirmed.json: previous session's notable contracts ∩ today's
    top ΔOI movers.

DISPLAY-TIER ONLY: nothing here ranks, gates, or advises trades.
Words 'signal' and 'validated' are banned in user-facing strings.
"""
from __future__ import annotations

import logging
from datetime import date as _date
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #
MULT = 100.0   # standard equity option contract multiplier
PM   = 0.01    # 1% move (GEX scaling, matching gex_engine DEFAULTS)

# Number of days to interpolate ATM IV to ("30-day ATM IV")
_IV30_DTE = 30.0

# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _f(x, n: int = 2):
    """Round to n decimals, None for NaN/inf/non-numeric — JSON-safe."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if np.isfinite(v) else None


def _today_str() -> str:
    return str(_date.today())


# --------------------------------------------------------------------------- #
# ATM IV helpers
# --------------------------------------------------------------------------- #

def _atm_iv_for_expiry(grp: pd.DataFrame, spot: float) -> float | None:
    """ATM IV for one expiry group: interpolate the two nearest strikes
    (weight by inverse strike-distance to spot). Returns None when no valid IV.

    Brief spec: 'ATM IV per expiry = IV of strike nearest underlying_price
    (interpolate the two nearest, weight by distance)'.
    """
    valid = grp[grp["implied_vol"].notna() & (grp["implied_vol"] > 0)].copy()
    if valid.empty:
        return None
    valid = valid.copy()
    valid["_dist"] = (valid["strike"].astype(float) - spot).abs()
    valid = valid.sort_values("_dist")
    if len(valid) < 2:
        # only one IV: use it directly
        return float(valid["implied_vol"].iloc[0])
    k0, k1 = valid["_dist"].iloc[0], valid["_dist"].iloc[1]
    iv0, iv1 = float(valid["implied_vol"].iloc[0]), float(valid["implied_vol"].iloc[1])
    if k0 == 0.0:
        return iv0
    # inverse-distance weights
    w0, w1 = 1.0 / k0, 1.0 / k1
    return float((w0 * iv0 + w1 * iv1) / (w0 + w1))


def _iv30_from_term(term_rows: list[dict]) -> float | None:
    """Interpolate ATM IV to 30 DTE from a term structure list
    [{"dte": int, "atm_iv": float, ...}]. Mirrors gex_engine._iv30 logic."""
    pts = [(r["dte"], r["atm_iv"]) for r in term_rows
           if r.get("dte") is not None and r.get("atm_iv") is not None
           and r["atm_iv"] > 0]
    if not pts:
        return None
    pts.sort()
    dtes = [p[0] for p in pts]
    ivs  = [p[1] for p in pts]
    if dtes[0] <= _IV30_DTE <= dtes[-1]:
        return float(np.interp(_IV30_DTE, dtes, ivs))
    # nearest-listed tenor (no extrapolation)
    return ivs[0] if _IV30_DTE < dtes[0] else ivs[-1]


# --------------------------------------------------------------------------- #
# vol payload
# --------------------------------------------------------------------------- #

def compute_vol(
    greeks_df: pd.DataFrame,
    yahoo_closes: pd.Series,
    asof: str,
    root: str,
) -> dict:
    """Build the options_hub/vol/{root} payload from greeks and yahoo history.

    Args:
        greeks_df:    Full multi-year greeks frame for this root (from thetadata_store).
                      Columns: root, expiration, strike, right, date, implied_vol,
                      underlying_price, [delta, gamma, ...].
                      Date column must be string 'YYYY-MM-DD' or datetime-parseable.
        yahoo_closes: pd.Series indexed by date (str or Timestamp), values = adjusted close.
                      Used for rv20 (realised vol) computation.
        asof:         'YYYY-MM-DD' — the reference date (latest available greeks date).
        root:         Option root symbol, e.g. 'SPY'.

    Returns a dict matching the options_hub.vol/v1 schema.
    """
    # ── guard: empty frame (no greeks data for this root) ────────────────────
    if greeks_df is None or greeks_df.empty or "date" not in greeks_df.columns:
        log.warning("options_hub.compute_vol: no greeks frame for %s %s", root, asof)
        return _empty_vol(root, asof)

    # ── normalise dates ──────────────────────────────────────────────────────
    df = greeks_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)

    asof_df = df[df["date"] == asof]
    if asof_df.empty:
        log.warning("options_hub.compute_vol: no greeks rows for %s %s", root, asof)
        return _empty_vol(root, asof)

    # ── spot (underlying_price) ──────────────────────────────────────────────
    spot_vals = asof_df["underlying_price"].dropna()
    if spot_vals.empty:
        spot = float("nan")
    else:
        spot = float(spot_vals.median())

    # ── term structure (ATM IV per expiry) ───────────────────────────────────
    today = pd.Timestamp(asof).date()
    term_rows: list[dict] = []
    for expiration, grp in asof_df.groupby("expiration"):
        exp_dt = pd.Timestamp(expiration).date()
        dte = (exp_dt - today).days
        if dte < 0:
            continue
        atm_iv = _atm_iv_for_expiry(grp, spot)
        if atm_iv is None or atm_iv <= 0:
            continue
        exp_str = str(exp_dt)
        term_rows.append({"dte": dte, "exp": exp_str, "atm_iv": round(atm_iv * 100, 4)})
    term_rows.sort(key=lambda r: r["dte"])

    # ── ATM IV (30d interpolated) ─────────────────────────────────────────────
    atm_iv_30 = _iv30_from_term(term_rows)

    # ── IV rank 252 + full-history iv_rank_all ────────────────────────────────
    history_rows, iv_rank_252, iv_rank_all, coverage_days_all, since_all = (
        _compute_iv_history(df, root, asof, spot)
    )

    # ── realized vol (yahoo log-returns, 20-day) ──────────────────────────────
    rv20 = _rv20(yahoo_closes, asof)

    # ── VRP ───────────────────────────────────────────────────────────────────
    vrp: float | None = None
    if atm_iv_30 is not None and rv20 is not None:
        vrp = round(atm_iv_30 - rv20, 4)

    # ── smile (call/put IV by strike for 2 nearest >=2 DTE expiries) ─────────
    smile_rows = _compute_smile(asof_df, spot, asof)

    # ── coverage ──────────────────────────────────────────────────────────────
    all_dates = sorted(df[df["implied_vol"].notna() & (df["implied_vol"] > 0)]["date"].unique())
    coverage = {
        "n_days": len(all_dates),
        "since": all_dates[0] if all_dates else None,
    }

    return {
        "schema": "options_hub.vol/v1",
        "asof": asof,
        "root": root,
        "iv_rank_252": iv_rank_252,
        # CONTRACT v2: full-history IV rank (null when < 60 observed sessions)
        "iv_rank_all": iv_rank_all,
        "coverage_days_all": coverage_days_all,
        "since_all": since_all,
        "atm_iv": _f(atm_iv_30, 4),
        "iv_52w_hi": _f(max((r["atm_iv"] for r in history_rows), default=None), 4) if history_rows else None,
        "iv_52w_lo": _f(min((r["atm_iv"] for r in history_rows), default=None), 4) if history_rows else None,
        "rv20": _f(rv20, 4),
        "vrp": _f(vrp, 4),
        "term": term_rows,
        "smile": smile_rows,
        "history": history_rows,
        "coverage": coverage,
    }


def _empty_vol(root: str, asof: str) -> dict:
    return {
        "schema": "options_hub.vol/v1",
        "asof": asof,
        "root": root,
        "iv_rank_252": None,
        "iv_rank_all": None,
        "coverage_days_all": 0,
        "since_all": None,
        "atm_iv": None,
        "iv_52w_hi": None,
        "iv_52w_lo": None,
        "rv20": None,
        "vrp": None,
        "term": [],
        "smile": [],
        "history": [],
        "coverage": {"n_days": 0, "since": None},
    }


def _rv20(closes: pd.Series, asof: str) -> float | None:
    """Annualized realized vol from 20 log-returns ending at `asof`."""
    if closes is None or closes.empty:
        return None
    s = closes.copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    s = s[s.index <= pd.Timestamp(asof)]
    if len(s) < 21:
        return None
    s = s.tail(21)
    lr = np.log(s.values[1:] / s.values[:-1])
    rv = float(np.std(lr, ddof=1) * np.sqrt(252) * 100)  # in percent, to match atm_iv %
    return round(rv, 4) if np.isfinite(rv) else None


def _compute_iv_history(
    df: pd.DataFrame,
    root: str,
    asof: str,
    spot_today: float,
) -> tuple[list[dict], float | None, float | None, int, str | None]:
    """Build the last-90-sessions IV history, iv_rank_252, and full-history iv_rank_all.

    Returns:
        (history_rows, iv_rank_252, iv_rank_all, coverage_days_all, since_all)

    iv_rank_252: percentile of today's 30d ATM IV in trailing 252 sessions.
    iv_rank_all: percentile of today's 30d ATM IV in FULL available history.
    Both are null when < 60 observed sessions (per spec).
    coverage_days_all: count of all available IV-data dates.
    since_all: earliest available date with IV data.
    """
    # All dates with greeks available
    valid = df[df["implied_vol"].notna() & (df["implied_vol"] > 0)].copy()
    if valid.empty:
        return [], None, None, 0, None

    all_dates = sorted(valid["date"].unique())
    all_dates_before_asof = [d for d in all_dates if d <= asof]
    if not all_dates_before_asof:
        return [], None, None, 0, None

    # ── per-date ATM IV (30d interp) ─────────────────────────────────────────
    per_date_iv: dict[str, float] = {}
    for d in all_dates_before_asof:
        day_df = valid[valid["date"] == d]
        # need underlying_price for that day
        spot_d = day_df["underlying_price"].dropna()
        spot_val = float(spot_d.median()) if not spot_d.empty else spot_today
        if not np.isfinite(spot_val) or spot_val <= 0:
            continue
        term: list[tuple[float, float]] = []
        for exp, grp in day_df.groupby("expiration"):
            exp_dt = pd.Timestamp(exp).date()
            asof_dt = pd.Timestamp(d).date()
            dte = (exp_dt - asof_dt).days
            if dte <= 0:
                continue
            atm = _atm_iv_for_expiry(grp, spot_val)
            if atm and atm > 0:
                term.append((float(dte), float(atm)))
        if not term:
            continue
        term.sort()
        dtes = [t[0] for t in term]
        ivs  = [t[1] for t in term]
        if dtes[0] <= _IV30_DTE <= dtes[-1]:
            iv30 = float(np.interp(_IV30_DTE, dtes, ivs))
        else:
            iv30 = ivs[0] if _IV30_DTE < dtes[0] else ivs[-1]
        per_date_iv[d] = round(iv30 * 100, 4)

    if not per_date_iv:
        return [], None, None, 0, None

    sorted_dates = sorted(per_date_iv)
    all_before_asof = [d for d in sorted_dates if d <= asof]

    # ── iv_rank_252 ────────────────────────────────────────────────────────────
    # Last 252 sessions ending at asof
    trailing_252 = all_before_asof[-252:]
    iv_rank_252: float | None = None
    if len(trailing_252) >= 60 and asof in per_date_iv:
        today_iv = per_date_iv[asof]
        window_ivs = [per_date_iv[d] for d in trailing_252]
        rank = sum(1 for v in window_ivs if v < today_iv) / len(window_ivs)
        iv_rank_252 = round(rank * 100, 1)

    # ── iv_rank_all — full history ─────────────────────────────────────────────
    iv_rank_all: float | None = None
    coverage_days_all: int = len(all_before_asof)
    since_all: str | None = all_before_asof[0] if all_before_asof else None
    if len(all_before_asof) >= 60 and asof in per_date_iv:
        today_iv = per_date_iv[asof]
        all_ivs = [per_date_iv[d] for d in all_before_asof]
        rank_all = sum(1 for v in all_ivs if v < today_iv) / len(all_ivs)
        iv_rank_all = round(rank_all * 100, 1)

    # ── history: last 90 sessions ─────────────────────────────────────────────
    last_90 = all_before_asof[-90:]
    history_rows: list[dict] = []
    for d in last_90:
        history_rows.append({
            "date": d,
            "iv_rank": None,  # per-point rank not required by spec
            "atm_iv": per_date_iv[d],
            "close": None,  # caller can enrich; omitting avoids a yahoo join here
        })

    return history_rows, iv_rank_252, iv_rank_all, coverage_days_all, since_all


def _compute_smile(asof_df: pd.DataFrame, spot: float, asof: str) -> list[dict]:
    """IV smile for the 2 nearest >=2 DTE expiries.

    Returns list of {exp: str, points: [{strike, call_iv, put_iv}]}.
    """
    today = pd.Timestamp(asof).date()
    valid = asof_df[asof_df["implied_vol"].notna() & (asof_df["implied_vol"] > 0)].copy()
    if valid.empty:
        return []

    # expiries with DTE >= 2 and at least 4 strikes with IV
    exp_info: list[tuple[int, Any]] = []
    for exp, grp in valid.groupby("expiration"):
        exp_dt = pd.Timestamp(exp).date()
        dte = (exp_dt - today).days
        if dte < 2:
            continue
        n_strikes = grp["strike"].nunique()
        if n_strikes >= 4:
            exp_info.append((dte, exp))
    exp_info.sort()

    smile_out: list[dict] = []
    for dte, exp in exp_info[:2]:
        grp = valid[valid["expiration"] == exp]
        exp_dt = pd.Timestamp(exp).date()
        strikes = sorted(grp["strike"].astype(float).unique())
        points = []
        for k in strikes:
            k_grp = grp[grp["strike"].astype(float) == k]
            calls = k_grp[k_grp["right"].str.upper() == "C"]["implied_vol"]
            puts  = k_grp[k_grp["right"].str.upper() == "P"]["implied_vol"]
            call_iv = round(float(calls.mean()) * 100, 4) if not calls.empty and calls.mean() > 0 else None
            put_iv  = round(float(puts.mean()) * 100, 4) if not puts.empty and puts.mean() > 0 else None
            if call_iv is not None or put_iv is not None:
                points.append({"strike": _f(k), "call_iv": call_iv, "put_iv": put_iv})
        if points:
            smile_out.append({"exp": str(exp_dt), "points": points})

    return smile_out


# --------------------------------------------------------------------------- #
# GEX payload
# --------------------------------------------------------------------------- #

def compute_gex(
    greeks_df: pd.DataFrame,
    oi_prev_df: pd.DataFrame,
    asof: str,
    root: str,
) -> dict:
    """Build the options_hub/gex/{root} payload.

    DEALER-SIGN CONVENTION (replicating engine/gex_engine.py lines 158–163):
      sign = +1 for calls, -1 for puts.
      net_gex = sign * gamma * OI[t-1] * MULT * spot^2 * PM
    Per-contract gamma comes from the greeks tier. When absent, a BS fallback
    is used (same as gex_model._dollar_gamma).

    Args:
        greeks_df:  Greeks frame for asof date, with columns including
                    strike, right, expiration, implied_vol, gamma (optional),
                    underlying_price, delta, vanna, charm.
        oi_prev_df: OI frame for t-1 (already shifted by caller), columns:
                    expiration, strike, right, open_interest.
        asof:       'YYYY-MM-DD' reference date.
        root:       Option root symbol.

    Returns a dict matching the options_hub.gex/v1 schema.
    """
    from engine.greeks import bs_greeks as _bs_greeks  # local import for hermetic tests

    _MIN_IV = 0.005

    if greeks_df is None or greeks_df.empty or "date" not in greeks_df.columns:
        return _empty_gex(root, asof)

    g = greeks_df.copy()
    g["date"] = pd.to_datetime(g["date"]).dt.date.astype(str)
    g = g[g["date"] == asof]
    if g.empty:
        return _empty_gex(root, asof)

    # ── spot ────────────────────────────────────────────────────────────────
    spot_vals = g["underlying_price"].dropna()
    spot = float(spot_vals.median()) if not spot_vals.empty else float("nan")
    if not np.isfinite(spot) or spot <= 0:
        return _empty_gex(root, asof)

    # ── merge OI[t-1] ────────────────────────────────────────────────────────
    if oi_prev_df is not None and not oi_prev_df.empty:
        oi = oi_prev_df[["expiration", "strike", "right", "open_interest"]].copy()
        oi["expiration"] = pd.to_datetime(oi["expiration"]).dt.date.astype(str)
        oi["strike"] = oi["strike"].astype(float)
        g["expiration"] = pd.to_datetime(g["expiration"]).dt.date.astype(str)
        g["strike"] = g["strike"].astype(float)
        g = g.merge(oi.rename(columns={"open_interest": "oi_prev"}),
                    on=["expiration", "strike", "right"], how="left")
        g["oi_prev"] = pd.to_numeric(g["oi_prev"], errors="coerce").fillna(0.0)
    else:
        g["oi_prev"] = 0.0

    # Only use contracts with positive OI[t-1]
    g = g[g["oi_prev"] > 0].copy()
    if g.empty:
        return _empty_gex(root, asof)

    # ── prepare fields ────────────────────────────────────────────────────────
    g["is_call"] = g["right"].str.upper() == "C"
    g["K"] = g["strike"].astype(float)
    today = pd.Timestamp(asof).date()
    g["expiry_dt"] = pd.to_datetime(g["expiration"]).dt.date
    g["T"] = (pd.to_datetime(g["expiration"]).dt.date
              .map(lambda e: (e - today).days / 365.0))
    g["T"] = pd.to_numeric(g["T"], errors="coerce").clip(lower=0.0)
    g["iv"] = pd.to_numeric(g.get("implied_vol", pd.Series(np.nan, index=g.index)),
                            errors="coerce")

    # ── gamma (use feed value when present, else BS fallback) ─────────────────
    # This mirrors engine/gex_model._dollar_gamma logic.
    if "gamma" in g.columns:
        raw_gamma = pd.to_numeric(g["gamma"], errors="coerce")
    else:
        raw_gamma = pd.Series(np.nan, index=g.index)
    miss = ~np.isfinite(raw_gamma.to_numpy(dtype=float))
    if miss.any():
        def _bs_g(k, t, s, call):
            s = float(s) if s is not None and np.isfinite(float(s) if s is not None else float("nan")) else float("nan")
            if not np.isfinite(s) or s < _MIN_IV or not (t and t > 0):
                return 0.0
            try:
                return _bs_greeks(spot, float(k), float(t), float(s), bool(call))[1]
            except Exception:  # noqa: BLE001
                return 0.0
        bs_vals = np.array([
            _bs_g(k, t, s, c)
            for k, t, s, c in zip(g["K"], g["T"], g["iv"], g["is_call"])
        ], dtype=float)
        raw_gamma = raw_gamma.copy()
        raw_gamma.values[miss] = bs_vals[miss]
    g["_gamma"] = raw_gamma.astype(float)

    # ── dealer-sign convention (gex_engine lines 158–163) ────────────────────
    sign = np.where(g["is_call"], 1.0, -1.0)
    oi_arr = g["oi_prev"].to_numpy(float)
    k_arr  = g["K"].to_numpy(float)

    g["_net_gex"]   = sign * g["_gamma"] * oi_arr * MULT * spot**2 * PM
    g["_call_gex"]  = np.where(g["is_call"],  g["_net_gex"], 0.0)
    g["_put_gex"]   = np.where(~g["is_call"], g["_net_gex"], 0.0)

    # delta
    if "delta" in g.columns:
        raw_delta = pd.to_numeric(g["delta"], errors="coerce")
    else:
        raw_delta = pd.Series(np.nan, index=g.index)
    g["_net_delta"] = sign * raw_delta * oi_arr * MULT * spot

    # vanna — scale: sign * vanna * OI * MULT * spot * PM (same as VEX in gex_engine)
    if "vanna" in g.columns:
        raw_vanna = pd.to_numeric(g["vanna"], errors="coerce")
    else:
        raw_vanna = pd.Series(np.nan, index=g.index)
    g["_net_vanna"] = sign * raw_vanna * oi_arr * MULT * spot * PM

    # charm — scale: sign * (charm/365) * OI * MULT * spot (same as CEX in gex_engine)
    if "charm" in g.columns:
        raw_charm = pd.to_numeric(g["charm"], errors="coerce")
    else:
        raw_charm = pd.Series(np.nan, index=g.index)
    g["_net_charm"] = sign * (raw_charm / 365.0) * oi_arr * MULT * spot

    # ── headline ──────────────────────────────────────────────────────────────
    net_gex_bn = float(g["_net_gex"].sum() / 1e9)

    # ── gamma flip (nearest zero-crossing of cumulative net_gex across strikes) ──
    gamma_flip = _find_gamma_flip(g, spot)

    # ── walls: max |call_gex| above spot / max |put_gex| below ────────────────
    by_k = g.groupby("K").agg(
        gamma_net=("_net_gex", "sum"),
        gamma_call=("_call_gex", "sum"),
        gamma_put=("_put_gex", "sum"),
        delta_net=("_net_delta", "sum"),
        vanna_net=("_net_vanna", "sum"),
        charm_net=("_net_charm", "sum"),
    ).reset_index()

    above = by_k[(by_k["K"] > spot) & (by_k["gamma_net"] > 0)]
    below = by_k[(by_k["K"] < spot) & (by_k["gamma_net"] < 0)]
    call_wall: float | None = float(above.loc[above["gamma_net"].idxmax(), "K"]) if not above.empty else None
    put_wall: float | None  = float(below.loc[below["gamma_net"].idxmin(), "K"]) if not below.empty else None

    # ── by_strike windowing (CONTRACT: ±20% of spot_ref, cap 160 nearest spot) ──
    by_strike_full_n = int(len(by_k))  # pre-window row count preserved in payload

    # Window: keep only strikes within ±20% of spot
    by_k_win = by_k[((by_k["K"] / spot - 1).abs() <= 0.20)].copy()

    # Cap at 160 rows nearest to spot (sort by distance, take 160, restore strike-asc)
    if len(by_k_win) > 160:
        by_k_win = (
            by_k_win
            .assign(_dist=(by_k_win["K"] - spot).abs())
            .nsmallest(160, "_dist")
            .drop(columns=["_dist"])
            .sort_values("K")
        )

    by_strike_rows = [
        {
            "strike": _f(row.K),
            "gamma_net": _f(row.gamma_net / 1e6, 4),   # $mn, 4dp
            "gamma_call": _f(row.gamma_call / 1e6, 4),
            "gamma_put": _f(row.gamma_put / 1e6, 4),
            "delta_net": _f(row.delta_net / 1e6, 4),
            "vanna_net": _f(row.vanna_net / 1e6, 4),
            "charm_net": _f(row.charm_net / 1e6, 4),
        }
        for row in by_k_win.itertuples()
    ]

    # ── by expiry ─────────────────────────────────────────────────────────────
    by_exp = g.groupby("expiration").agg(
        gamma_net=("_net_gex", "sum"),
        delta_net=("_net_delta", "sum"),
    ).reset_index()
    by_exp["expiration"] = pd.to_datetime(by_exp["expiration"]).dt.date.astype(str)
    by_expiry_rows = [
        {
            "exp": row.expiration,
            "gamma_net": _f(row.gamma_net / 1e6, 4),
            "delta_net": _f(row.delta_net / 1e6, 4),
        }
        for row in by_exp.itertuples()
    ]
    by_expiry_rows.sort(key=lambda r: r["exp"])

    # ── coverage superset (CONTRACT: {n_contracts, asof, oi_date, n_days, since}) ─
    # n_days / since derived from the greeks dates represented in this compute call.
    greeks_dates = sorted(g["date"].unique()) if "date" in g.columns else []
    coverage = {
        "n_contracts": int(len(g)),
        "asof": asof,
        "oi_date": "t-1",  # OI is always t-1 per OI timing law
        "n_days": len(greeks_dates),
        "since": greeks_dates[0] if greeks_dates else asof,
    }

    return {
        "schema": "options_hub.gex/v1",
        "asof": asof,
        "root": root,
        "spot_ref": _f(spot),
        "net_gex_bn": _f(net_gex_bn, 4),
        "gamma_flip": _f(gamma_flip),
        "call_wall": _f(call_wall),
        "put_wall": _f(put_wall),
        "by_strike": by_strike_rows,
        "by_strike_full_n": by_strike_full_n,
        "by_expiry": by_expiry_rows,
        "convention": "dealer-sign per engine/gex_model (long-call/short-put)",
        "coverage": coverage,
        # NOTE: history field is injected by build_options_hub_nightly.py
        # via _attach_gex_history() — it is absent when polygon_gex parquet is missing.
    }


def _empty_gex(root: str, asof: str) -> dict:
    return {
        "schema": "options_hub.gex/v1",
        "asof": asof,
        "root": root,
        "spot_ref": None,
        "net_gex_bn": None,
        "gamma_flip": None,
        "call_wall": None,
        "put_wall": None,
        "by_strike": [],
        "by_strike_full_n": 0,
        "by_expiry": [],
        "convention": "dealer-sign per engine/gex_model (long-call/short-put)",
        "coverage": {"n_contracts": 0, "asof": asof, "oi_date": "t-1", "n_days": 0, "since": asof},
    }


def _find_gamma_flip(g: pd.DataFrame, spot: float) -> float | None:
    """Gamma flip = nearest zero-crossing of cumulative net_gex sorted by strike.

    Returns None if no crossing found (always on one side of gamma regime boundary).
    Mirrors gex_engine._gamma_flip but uses pre-computed per-row _net_gex.
    """
    by_k = (g.groupby("K")["_net_gex"]
             .sum()
             .sort_index()
             .reset_index())
    if len(by_k) < 4:
        return None

    # cumulative sum from lowest strike upward
    by_k["cum"] = by_k["_net_gex"].cumsum()
    crossings = []
    arr = by_k["cum"].to_numpy(float)
    ks  = by_k["K"].to_numpy(float)
    for i in range(len(arr) - 1):
        if arr[i] == 0.0 or (arr[i] < 0) != (arr[i + 1] < 0):
            y0, y1, x0, x1 = arr[i], arr[i + 1], ks[i], ks[i + 1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0) if (y1 - y0) != 0 else x0
            crossings.append(float(cross))
    if not crossings:
        return None
    return min(crossings, key=lambda c: abs(c - spot))


# --------------------------------------------------------------------------- #
# OI movers
# --------------------------------------------------------------------------- #

def compute_oi_movers(
    oi_t: pd.DataFrame,
    oi_t1: pd.DataFrame,
    eod_t: pd.DataFrame,
    asof: str,
    top_n: int = 100,
) -> dict:
    """Build options_hub/oi_movers.json from two consecutive OI sessions.

    OI TIMING LAW: oi_t represents positions as of EOD(asof-1); oi_t1
    represents positions as of EOD(asof-2). Both are the REPORTED values
    (never same-day OI). The delta = oi_t - oi_t1 is fully known at
    market open on asof.

    Args:
        oi_t:   OI frame for t (latest available: OPRA report for asof).
                Columns: expiration, strike, right, root, open_interest.
        oi_t1:  OI frame for t-1. Same schema.
        eod_t:  EOD price frame for asof, for bid/ask mid.
                Columns: expiration, strike, right, bid_eod, ask_eod.
        asof:   'YYYY-MM-DD'.
        top_n:  Max rows in output.

    Returns dict matching options_hub.oi_movers/v1.
    """
    if oi_t is None or oi_t1 is None or oi_t.empty or oi_t1.empty:
        return {"schema": "options_hub.oi_movers/v1", "asof": asof, "movers": []}

    keys = ["expiration", "strike", "right"]

    # normalise
    t = oi_t[keys + ["root", "open_interest"]].copy()
    t1 = oi_t1[keys + ["open_interest"]].copy()
    for df in (t, t1):
        df["expiration"] = pd.to_datetime(df["expiration"]).dt.date.astype(str)
        df["strike"] = df["strike"].astype(float)

    merged = t.merge(
        t1.rename(columns={"open_interest": "oi_prev"}),
        on=keys, how="outer"
    ).fillna(0)
    merged["oi"] = merged["open_interest"].astype(float)
    merged["oi_prev"] = merged["oi_prev"].astype(float)
    merged["d_oi"] = merged["oi"] - merged["oi_prev"]
    merged = merged[merged["d_oi"].abs() > 0]

    # merge mid price from eod
    if eod_t is not None and not eod_t.empty:
        ep = eod_t[keys + ["bid_eod", "ask_eod"]].copy()
        ep["expiration"] = pd.to_datetime(ep["expiration"]).dt.date.astype(str)
        ep["strike"] = ep["strike"].astype(float)
        ep["mid"] = (pd.to_numeric(ep["bid_eod"], errors="coerce") +
                     pd.to_numeric(ep["ask_eod"], errors="coerce")) / 2.0
        merged = merged.merge(ep[keys + ["mid"]], on=keys, how="left")
    else:
        merged["mid"] = np.nan

    # sort by |d_oi|, top N (magnitude-ranked so large OI *reductions* are not
    # dropped by a signed pre-filter — nlargest on signed d_oi would miss them).
    merged = merged.reindex(merged["d_oi"].abs().sort_values(ascending=False).index).head(top_n)

    root_val = str(merged["root"].iloc[0]) if "root" in merged.columns and len(merged) > 0 else ""

    movers = []
    for row in merged.itertuples():
        movers.append({
            "root": root_val,
            "right": str(row.right),
            "exp": str(row.expiration),
            "strike": _f(row.strike),
            "oi": int(row.oi),
            "oi_prev": int(row.oi_prev),
            "d_oi": int(row.d_oi),
            "mid": _f(row.mid) if hasattr(row, "mid") and np.isfinite(row.mid) else None,
        })

    return {
        "schema": "options_hub.oi_movers/v1",
        "asof": asof,
        "movers": movers,
    }


# --------------------------------------------------------------------------- #
# R3 OI suite — oi_time / max_pain / oi_change (Options Superintelligence R3)
# --------------------------------------------------------------------------- #
# Pure, hermetic, mirror the compute_vol/compute_gex conventions. All three read
# the OI tier only (plus EOD mids for oi_change); the OI TIMING LAW applies
# verbatim: the OI parquet for date d carries the OPRA report representing
# end-of-(d-1) positions, so every payload discloses oi_date: "t-1".

_OI_TIME_MONTHS_DEFAULT = 18   # QuantData OI/Time depth (~18 months)
_MAX_PAIN_CURVE_EXPS = 8       # expiries that carry a full intrinsic-value curve
_MAX_PAIN_MAX_EXPS = 60        # cap on the expiries list (SPXW dailies are many)
_MAX_PAIN_CURVE_CAP = 120      # curve strikes cap (nearest window center)
_OI_BY_STRIKE_CAP = 160        # by_strike rows cap (mirrors the gex ±20%/160 law)
_OI_WINDOW_FRAC = 0.20         # ±20% window around center (mirrors gex law)


def _norm_oi_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise an OI frame: expiration → 'YYYY-MM-DD', strike float, right 'C'/'P',
    open_interest numeric (non-positive rows dropped)."""
    sub = df[["expiration", "strike", "right", "open_interest"]].copy()
    sub["expiration"] = pd.to_datetime(sub["expiration"]).dt.date.astype(str)
    sub["strike"] = pd.to_numeric(sub["strike"], errors="coerce")
    sub["right"] = sub["right"].astype(str).str.upper().str[:1]
    sub["open_interest"] = pd.to_numeric(sub["open_interest"], errors="coerce")
    sub = sub[np.isfinite(sub["strike"]) & (sub["open_interest"] > 0)]
    return sub


def compute_oi_time(
    oi_all: pd.DataFrame,
    asof: str,
    root: str,
    months: int = _OI_TIME_MONTHS_DEFAULT,
) -> dict:
    """Build options_hub/oi_time/{ROOT}.json — call/put total OI per session.

    Args:
        oi_all: multi-year OI frame for this root (columns: date, expiration,
                strike, right, open_interest). Dates 'YYYY-MM-DD' or parseable.
        asof:   'YYYY-MM-DD' reference date (rows after asof are excluded).
        root:   option root symbol.
        months: history depth (calendar months back from asof).

    Each history row keys by the OI parquet's own session date; per the OI
    timing law that report represents end-of-(date-1) positions — disclosed
    via oi_date: "t-1", never re-shifted here.
    """
    empty = {
        "schema": "options_hub.oi_time/v1",
        "asof": asof,
        "root": root,
        "oi_date": "t-1",
        "window_months": months,
        "history": [],
        "coverage": {"n_days": 0, "since": None},
    }
    if oi_all is None or oi_all.empty or "date" not in oi_all.columns:
        return empty

    df = oi_all.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    cutoff = str((pd.Timestamp(asof) - pd.DateOffset(months=months)).date())
    df = df[(df["date"] >= cutoff) & (df["date"] <= asof)]
    if df.empty:
        return empty

    df["right"] = df["right"].astype(str).str.upper().str[:1]
    df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce").fillna(0.0)

    piv = (df.pivot_table(index="date", columns="right",
                          values="open_interest", aggfunc="sum")
             .fillna(0.0).sort_index())
    call_s = piv["C"] if "C" in piv.columns else pd.Series(0.0, index=piv.index)
    put_s = piv["P"] if "P" in piv.columns else pd.Series(0.0, index=piv.index)

    history = [
        {
            "date": d,
            "call_oi": int(call_s.get(d, 0.0)),
            "put_oi": int(put_s.get(d, 0.0)),
            "total_oi": int(call_s.get(d, 0.0) + put_s.get(d, 0.0)),
        }
        for d in piv.index
    ]
    return {
        "schema": "options_hub.oi_time/v1",
        "asof": asof,
        "root": root,
        "oi_date": "t-1",
        "window_months": months,
        "history": history,
        "coverage": {"n_days": len(history), "since": history[0]["date"] if history else None},
    }


def _window_center(spot_ref, fallback) -> float | None:
    """Window center for by_strike/curve trims: spot_ref when finite, else fallback."""
    try:
        v = float(spot_ref)
        if np.isfinite(v) and v > 0:
            return v
    except (TypeError, ValueError):
        pass
    try:
        v = float(fallback)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def compute_max_pain(
    oi_t1: pd.DataFrame,
    asof: str,
    root: str,
    spot_ref: float | None,
    curve_exps: int = _MAX_PAIN_CURVE_EXPS,
    max_exps: int = _MAX_PAIN_MAX_EXPS,
) -> dict:
    """Build options_hub/max_pain/{ROOT}.json — per-expiration max pain from OI[t-1].

    Max pain per expiration = the candidate settle strike minimizing total
    intrinsic value paid out by option writers:
        value(Ks) = Σ_calls OI·max(0, Ks−K) + Σ_puts OI·max(0, K−Ks), × MULT.
    The argmin runs over the expiration's FULL strike set; curves are windowed
    for payload size only (±20% of center, cap, max-pain strike always kept).

    Also carries the OI ladder the Structure tab renders: by_strike call/put OI
    aggregated across upcoming expiries (±20%/160 window per the gex law, uncut
    count disclosed) — expiries[] rows double as OI-by-expiration.

    Args:
        oi_t1:    OI frame for asof (per the OI timing law these are t-1
                  positions). Columns: expiration, strike, right, open_interest.
        asof:     'YYYY-MM-DD' reference date; only expirations > asof are kept.
        spot_ref: reference spot (from the gex payload) — window center and the
                  UI's "max pain vs spot" comparison; None degrades gracefully.
        curve_exps: nearest expiries that carry the intrinsic-value curve.
        max_exps:   cap on the expiries list (nearest first, uncut count disclosed).
    """
    base = {
        "schema": "options_hub.max_pain/v1",
        "asof": asof,
        "root": root,
        "spot_ref": _f(spot_ref),
        "oi_date": "t-1",
        "expiries": [],
        "expiries_full_n": 0,
        "by_strike": [],
        "by_strike_full_n": 0,
        "coverage": {"n_contracts": 0, "asof": asof, "oi_date": "t-1"},
    }
    if oi_t1 is None or oi_t1.empty:
        return base

    sub = _norm_oi_frame(oi_t1)
    sub = sub[sub["expiration"] > asof]
    if sub.empty:
        return base

    today = pd.Timestamp(asof).date()
    exps = sorted(sub["expiration"].unique())
    base["expiries_full_n"] = len(exps)
    exps = exps[:max_exps]

    exp_rows: list[dict] = []
    for i, exp in enumerate(exps):
        grp = sub[sub["expiration"] == exp]
        piv = (grp.pivot_table(index="strike", columns="right",
                               values="open_interest", aggfunc="sum")
                  .fillna(0.0).sort_index())
        ks = piv.index.to_numpy(float)
        if ks.size == 0:
            continue
        c_oi = (piv["C"] if "C" in piv.columns else pd.Series(0.0, index=piv.index)).to_numpy(float)
        p_oi = (piv["P"] if "P" in piv.columns else pd.Series(0.0, index=piv.index)).to_numpy(float)

        # Intrinsic payout at each candidate settle (vectorized outer diff), $.
        call_val = (c_oi[:, None] * np.maximum(0.0, ks[None, :] - ks[:, None])).sum(axis=0) * MULT
        put_val = (p_oi[:, None] * np.maximum(0.0, ks[:, None] - ks[None, :])).sum(axis=0) * MULT
        total = call_val + put_val

        min_v = float(total.min())
        min_idx = np.flatnonzero(total == min_v)
        if len(min_idx) > 1 and spot_ref is not None and np.isfinite(float(spot_ref)):
            pick = min(min_idx, key=lambda j: abs(ks[j] - float(spot_ref)))
        else:
            pick = int(min_idx[0])
        max_pain = float(ks[pick])

        dte = (pd.Timestamp(exp).date() - today).days
        row: dict = {
            "exp": exp,
            "dte": int(dte),
            "max_pain": _f(max_pain),
            "call_oi": int(c_oi.sum()),
            "put_oi": int(p_oi.sum()),
        }

        if i < curve_exps:
            center = _window_center(spot_ref, max_pain)
            keep = np.ones(ks.size, dtype=bool)
            if center is not None and center > 0:
                keep = np.abs(ks / center - 1.0) <= _OI_WINDOW_FRAC
            idxs = np.flatnonzero(keep)
            if idxs.size > _MAX_PAIN_CURVE_CAP and center is not None:
                order = np.argsort(np.abs(ks[idxs] - center))
                idxs = idxs[order[:_MAX_PAIN_CURVE_CAP]]
            keep_set = set(int(j) for j in idxs)
            keep_set.add(int(pick))  # the argmin must always be drawable
            curve = [
                {
                    "strike": _f(ks[j]),
                    "call_value_mn": _f(call_val[j] / 1e6, 2),
                    "put_value_mn": _f(put_val[j] / 1e6, 2),
                    "value_mn": _f(total[j] / 1e6, 2),
                }
                for j in sorted(keep_set)
            ]
            row["curve"] = curve
            row["curve_full_n"] = int(ks.size)

        exp_rows.append(row)

    # ── by_strike OI ladder across ALL upcoming expiries (not just max_exps) ──
    by_k = (sub.pivot_table(index="strike", columns="right",
                            values="open_interest", aggfunc="sum")
               .fillna(0.0).sort_index())
    ks_all = by_k.index.to_numpy(float)
    c_all = (by_k["C"] if "C" in by_k.columns else pd.Series(0.0, index=by_k.index)).to_numpy(float)
    p_all = (by_k["P"] if "P" in by_k.columns else pd.Series(0.0, index=by_k.index)).to_numpy(float)
    by_strike_full_n = int(ks_all.size)

    front_mp = exp_rows[0]["max_pain"] if exp_rows else None
    center = _window_center(spot_ref, front_mp)
    keep = np.ones(ks_all.size, dtype=bool)
    if center is not None and center > 0:
        keep = np.abs(ks_all / center - 1.0) <= _OI_WINDOW_FRAC
    idxs = np.flatnonzero(keep)
    if idxs.size > _OI_BY_STRIKE_CAP and center is not None:
        order = np.argsort(np.abs(ks_all[idxs] - center))
        idxs = np.sort(idxs[order[:_OI_BY_STRIKE_CAP]])
    by_strike = [
        {
            "strike": _f(ks_all[j]),
            "call_oi": int(c_all[j]),
            "put_oi": int(p_all[j]),
        }
        for j in idxs
    ]

    out = dict(base)
    out["expiries"] = exp_rows
    out["by_strike"] = by_strike
    out["by_strike_full_n"] = by_strike_full_n
    out["coverage"] = {"n_contracts": int(len(sub)), "asof": asof, "oi_date": "t-1"}
    return out


def compute_oi_change(
    oi_t: pd.DataFrame,
    oi_prev: pd.DataFrame,
    eod_t: pd.DataFrame,
    asof: str,
    prev_date: str | None,
    root: str,
    top_n: int = 50,
) -> dict:
    """Build options_hub/oi_change/{ROOT}.json — top contract-level OI shifts.

    OI TIMING LAW: oi_t (the report for asof) carries end-of-(asof-1) positions;
    oi_prev (the report for prev_date) carries end-of-(prev_date-1) positions.
    The delta is fully known at market open on asof — never same-day OI.

    Rows are |ΔOI|-ranked (magnitude, so large reductions are kept), carry the
    percent change (null when the contract is new — no prev base), the EOD mid,
    and DTE. Expired contracts (exp <= asof) are excluded: their OI going to
    zero is expiry mechanics, not positioning.
    """
    base = {
        "schema": "options_hub.oi_change/v1",
        "asof": asof,
        "root": root,
        "scope": "root",
        "prev_session": prev_date,
        "oi_date": "t-1",
        "rows": [],
        "coverage": {"n_contracts_changed": 0},
    }
    if (oi_t is None or oi_t.empty or oi_prev is None or oi_prev.empty
            or not prev_date):
        return base

    keys = ["expiration", "strike", "right"]
    t = _norm_oi_frame(oi_t)
    t1 = _norm_oi_frame(oi_prev)

    merged = t.merge(
        t1.rename(columns={"open_interest": "oi_prev"}),
        on=keys, how="outer",
    ).fillna(0.0)
    merged["oi"] = merged["open_interest"].astype(float)
    merged["oi_prev"] = merged["oi_prev"].astype(float)
    merged["d_oi"] = merged["oi"] - merged["oi_prev"]
    merged = merged[(merged["d_oi"].abs() > 0) & (merged["expiration"] > asof)]
    n_changed = int(len(merged))
    if merged.empty:
        # Legitimately possible: OPRA occasionally republishes an unchanged
        # vintage (see engine/positioning_persistence same_vintage) — an honest
        # empty beats stale last-good rows wearing today's date.
        out = dict(base)
        out["note"] = "no contract-level OI change vs prev session"
        return out

    # EOD mid (close bid/ask) for context
    if eod_t is not None and not eod_t.empty and "bid_eod" in eod_t.columns:
        ep = eod_t[keys + ["bid_eod", "ask_eod"]].copy()
        ep["expiration"] = pd.to_datetime(ep["expiration"]).dt.date.astype(str)
        ep["strike"] = pd.to_numeric(ep["strike"], errors="coerce")
        ep["right"] = ep["right"].astype(str).str.upper().str[:1]
        ep["mid"] = (pd.to_numeric(ep["bid_eod"], errors="coerce") +
                     pd.to_numeric(ep["ask_eod"], errors="coerce")) / 2.0
        merged = merged.merge(ep[keys + ["mid"]], on=keys, how="left")
    else:
        merged["mid"] = np.nan

    merged = merged.reindex(
        merged["d_oi"].abs().sort_values(ascending=False).index
    ).head(top_n)

    today = pd.Timestamp(asof).date()
    rows: list[dict] = []
    for r in merged.itertuples():
        oi_prev_v = float(r.oi_prev)
        d_oi_v = float(r.d_oi)
        pct = _f(d_oi_v / oi_prev_v * 100.0, 1) if oi_prev_v > 0 else None
        mid_v = getattr(r, "mid", np.nan)
        rows.append({
            "root": root,
            "right": str(r.right),
            "exp": str(r.expiration),
            "dte": int((pd.Timestamp(r.expiration).date() - today).days),
            "strike": _f(r.strike),
            "oi": int(r.oi),
            "oi_prev": int(oi_prev_v),
            "d_oi": int(d_oi_v),
            "d_oi_pct": pct,
            "mid": _f(mid_v) if np.isfinite(mid_v) else None,
        })

    out = dict(base)
    out["rows"] = rows
    out["coverage"] = {"n_contracts_changed": n_changed}
    return out


def compute_oi_change_cross(
    rows: list[dict],
    asof: str,
    roots_n: int,
    top_n: int = 100,
) -> dict:
    """Cross-root options_hub/oi_change.json: |ΔOI|-top rows merged across roots.

    `rows` are per-root compute_oi_change rows (each already carries its root).
    Same magnitude ranking as oi_movers so large reductions survive the cut.
    """
    ranked = sorted(
        (r for r in (rows or []) if isinstance(r, dict)),
        key=lambda r: abs(r.get("d_oi", 0) or 0),
        reverse=True,
    )
    return {
        "schema": "options_hub.oi_change/v1",
        "asof": asof,
        "scope": "cross_root",
        "oi_date": "t-1",
        "roots_n": int(roots_n),
        "rows": ranked[:top_n],
    }


# --------------------------------------------------------------------------- #
# Hot contracts
# --------------------------------------------------------------------------- #

def compute_hot_contracts(
    eod_frames: dict[str, pd.DataFrame],
    oi_prev_frames: dict[str, pd.DataFrame],
    asof: str,
    top_n_premium: int = 100,
    top_n_volume: int = 50,
) -> dict:
    """Build options_hub/hot_contracts.json from EOD frames across all roots.

    hot = highest gross premium or volume for the session.

    Args:
        eod_frames:      {root: eod_df for asof} — EOD frame with
                         close, volume, bid_eod, ask_eod, expiration, strike, right, root.
        oi_prev_frames:  {root: oi_df for t-1} — for vol_gt_oi flag.
        asof:            'YYYY-MM-DD'.
        top_n_premium:   Max rows for by_premium list.
        top_n_volume:    Max rows for by_volume list.

    Returns dict matching options_hub.hot/v1.
    """
    rows: list[dict] = []

    for root, df in eod_frames.items():
        if df is None or df.empty:
            continue
        df = df.copy()
        df["expiration"] = pd.to_datetime(df["expiration"]).dt.date.astype(str)
        df["strike"] = df["strike"].astype(float)
        df["close"] = pd.to_numeric(df.get("close", pd.Series(np.nan, index=df.index)),
                                    errors="coerce")
        df["volume"] = pd.to_numeric(df.get("volume", pd.Series(np.nan, index=df.index)),
                                     errors="coerce").fillna(0)
        # gross premium = close * volume * MULT (proxy for day premium)
        df["premium"] = df["close"] * df["volume"] * MULT

        # oi_prev for vol_gt_oi flag
        oi_prev = oi_prev_frames.get(root)
        if oi_prev is not None and not oi_prev.empty:
            oi = oi_prev[["expiration", "strike", "right", "open_interest"]].copy()
            oi["expiration"] = pd.to_datetime(oi["expiration"]).dt.date.astype(str)
            oi["strike"] = oi["strike"].astype(float)
            df = df.merge(oi.rename(columns={"open_interest": "oi_prev"}),
                          on=["expiration", "strike", "right"], how="left")
            df["oi_prev"] = pd.to_numeric(df.get("oi_prev", pd.Series(np.nan, index=df.index)),
                                          errors="coerce")
        else:
            df["oi_prev"] = np.nan

        for row in df.itertuples():
            prem = getattr(row, "premium", 0)
            vol  = getattr(row, "volume", 0)
            if not np.isfinite(prem) or prem <= 0:
                continue
            oi_prev_val = getattr(row, "oi_prev", np.nan)
            vol_gt_oi = (bool(vol > oi_prev_val)
                         if (np.isfinite(vol) and np.isfinite(oi_prev_val) and oi_prev_val > 0)
                         else None)
            rows.append({
                "root": root,
                "right": str(row.right),
                "exp": str(row.expiration),
                "strike": _f(row.strike),
                "premium": _f(prem, 0),
                "vol": int(vol),
                "oi_prev": int(oi_prev_val) if np.isfinite(oi_prev_val) else None,
                "vol_gt_oi": vol_gt_oi,
                "close": _f(getattr(row, "close", None)),
            })

    if not rows:
        return {
            "schema": "options_hub.hot/v1",
            "asof": asof,
            "by_premium": [],
            "by_volume": [],
        }

    all_df = pd.DataFrame(rows)
    by_prem = (all_df.nlargest(top_n_premium, "premium")
               .to_dict(orient="records"))
    by_vol  = (all_df.nlargest(top_n_volume, "vol")
               .to_dict(orient="records"))

    return {
        "schema": "options_hub.hot/v1",
        "asof": asof,
        "by_premium": by_prem,
        "by_volume":  by_vol,
    }


# --------------------------------------------------------------------------- #
# CONTRACT v2 — GexPayload.history
# --------------------------------------------------------------------------- #

_GEX_HISTORY_ROWS = 30  # CONTRACT: last N rows from polygon_gex summary parquet


def _row_val(row, col: str):
    """Safe column access on a pandas Series row."""
    try:
        v = row[col]
        return None if pd.isna(v) else v
    except (KeyError, TypeError):
        return None


def load_gex_history_v2(root: str, polygon_gex_dir) -> list[dict] | None:
    """Load last 30 rows from data/polygon_gex/summary_{ROOT}.parquet.

    Maps polygon_gex columns:
      magnet_up   -> call_wall   (CONTRACT field name)
      magnet_down -> put_wall    (CONTRACT field name)
      gamma_regime -> regime

    Returns a list of dicts or None when the parquet is absent.
    Each row: {date, net_gex_bn, gamma_flip, call_wall, put_wall, regime}.

    CONTRACT: field is OMITTED from the gex_payload (not set to null) when
    parquet is absent — callers check ``"history" in gex_payload`` before use.
    """
    from pathlib import Path as _Path

    p = _Path(polygon_gex_dir) / f"summary_{root}.parquet"
    if not p.exists():
        log.debug("load_gex_history: %s absent — skipping history", p)
        return None

    try:
        df = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("load_gex_history: failed reading %s — %s", p, exc)
        return None

    if df.empty:
        return []

    tail = df.tail(_GEX_HISTORY_ROWS)
    rows: list[dict] = []
    for idx, row in tail.iterrows():
        date_str = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
        rows.append({
            "date": date_str,
            "net_gex_bn": _f(_row_val(row, "net_gex_bn"), 4),
            "gamma_flip": _f(_row_val(row, "gamma_flip")),
            "call_wall": _f(_row_val(row, "magnet_up")),    # magnet_up → call_wall
            "put_wall": _f(_row_val(row, "magnet_down")),   # magnet_down → put_wall
            "regime": str(row["gamma_regime"]) if "gamma_regime" in df.columns and pd.notna(_row_val(row, "gamma_regime")) else None,
        })
    return rows


# --------------------------------------------------------------------------- #
# CONTRACT v2 — context.json (cross-root index GEX + fear/greed + ETF flows)
# --------------------------------------------------------------------------- #

_CONTEXT_INDEX_ROOTS = ("SPX", "NDX", "RUT", "SPY")


def build_context_payload(
    asof: str,
    gex_latest_path,
    fear_greed_path,
    flows_wide_fn=None,
) -> dict:
    """Build options_hub/context.json per CONTRACT v2.

    Args:
        asof:              'YYYY-MM-DD' reference date.
        gex_latest_path:   Path to data/gex/latest.json.
        fear_greed_path:   Path to site/basketdata/fear_greed.json.
        flows_wide_fn:     Optional callable returning a pd.DataFrame (wide flows frame).
                           If None, engine.etf_flows.flows_wide is used.

    Returns dict with schema 'options_hub.context/v1'.  Every section degrades
    to absent/null on missing input — the function never raises.
    """
    from pathlib import Path as _Path

    out: dict = {
        "schema": "options_hub.context/v1",
        "asof": asof,
    }

    # ── index_gex from data/gex/latest.json ──────────────────────────────────
    try:
        import json as _json
        p = _Path(gex_latest_path)
        if p.exists():
            raw = _json.loads(p.read_text(encoding="utf-8"))
            indices_raw = raw.get("indices", {})
            index_gex: dict = {}
            for sym in _CONTEXT_INDEX_ROOTS:
                entry = indices_raw.get(sym)
                if entry:
                    index_gex[sym] = {
                        "regime": entry.get("regime"),
                        "net_gex_bn": _f(entry.get("net_gex_bn"), 4),
                        "gamma_flip": _f(entry.get("gamma_flip")),
                        "dist_to_flip_pct": _f(entry.get("dist_to_flip_pct"), 4),
                    }
            out["index_gex"] = index_gex
        else:
            log.debug("build_context_payload: gex/latest.json absent at %s", p)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_context_payload: index_gex load failed — %s", exc)

    # ── fear_greed from site/basketdata/fear_greed.json ─────────────────────
    try:
        import json as _json
        p = _Path(fear_greed_path)
        if p.exists():
            raw = _json.loads(p.read_text(encoding="utf-8"))
            out["fear_greed"] = {
                "dial": raw.get("dial"),
                "label_en": raw.get("label_en"),
                "label_zh": raw.get("label_zh"),
            }
        else:
            log.debug("build_context_payload: fear_greed.json absent at %s", p)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_context_payload: fear_greed load failed — %s", exc)

    # ── sector_etf_flows (d1 + w1 windows, creation/redemption proxy) ───────
    try:
        if flows_wide_fn is not None:
            wide = flows_wide_fn()
        else:
            from engine.etf_flows import flows_wide as _fw, SECTOR_TICKERS
            wide = _fw(SECTOR_TICKERS)

        if wide is not None and not wide.empty:
            wide = wide.sort_index()
            # Ensure datetime index
            if not isinstance(wide.index, pd.DatetimeIndex):
                wide.index = pd.to_datetime(wide.index)
            # Filter to dates up to asof
            asof_ts = pd.Timestamp(asof)
            wide = wide[wide.index <= asof_ts]

            sector_etf_flows: dict = {}
            for col in wide.columns:
                ticker = col.replace("_flow_mn", "")
                series = wide[col].dropna()
                if series.empty:
                    continue
                # d1: most recent flow
                d1 = _f(float(series.iloc[-1]), 2) if len(series) >= 1 else None
                # w1: sum of last 5 trading days (proxy for 1-week window)
                w1_n = min(5, len(series))
                w1 = _f(float(series.iloc[-w1_n:].sum()), 2) if w1_n >= 1 else None
                sector_etf_flows[ticker] = {"d1": d1, "w1": w1, "label": "proxy"}
            if sector_etf_flows:
                out["sector_etf_flows"] = sector_etf_flows
        else:
            log.debug("build_context_payload: flows_wide returned no data")
    except Exception as exc:  # noqa: BLE001
        log.warning("build_context_payload: sector_etf_flows load failed — %s", exc)

    return out


# --------------------------------------------------------------------------- #
# CONTRACT v2 — tickers_ctx/{ROOT}.json
# --------------------------------------------------------------------------- #

_TICKERS_CTX_MIN_HISTORY = 20  # CONTRACT: z null when history_n < this


def build_tickers_ctx(
    root: str,
    asof: str,
    tape_flow_dir,
) -> dict:
    """Build options_hub/tickers_ctx/{ROOT}.json from data/tape_flow/daily/{ROOT}.parquet.

    Returns dict with schema 'options_hub.tickers_ctx/v1'.
    z-scores are null when history_n < 20 (no fake z).
    The function never raises; degrades to absent z-fields on missing input.
    """
    from pathlib import Path as _Path

    base: dict = {
        "schema": "options_hub.tickers_ctx/v1",
        "asof": asof,
        "root": root,
        "history_n": 0,
        "z": {
            "net_signed_premium_z252": None,
            "zerodte_share_z252": None,
            "short_dated_otm_call_share_z252": None,
            "vol_gt_oi_share_z252": None,
            "block_share_z252": None,
        },
    }

    p = _Path(tape_flow_dir) / f"{root}.parquet"
    if not p.exists():
        log.debug("build_tickers_ctx: %s absent", p)
        return base

    try:
        df = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_tickers_ctx: read failed for %s — %s", p, exc)
        return base

    if df.empty:
        return base

    # normalise index to date strings
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = df[df.index <= pd.Timestamp(asof)].sort_index()

    history_n = len(df)
    base["history_n"] = history_n

    if history_n < _TICKERS_CTX_MIN_HISTORY:
        # Per CONTRACT: z null (not fake) when not enough history
        return base

    # Z-score helper: percentile of today's value in full available history.
    # We output a 252-day rolling z for each series (z = (x - mean) / std,
    # but CONTRACT names the fields *_z252 — use 252-day trailing window).
    _Z_WINDOW = 252
    z_fields = {
        "net_signed_premium_z252": "net_signed_premium",
        "zerodte_share_z252": "zerodte_share",
        "short_dated_otm_call_share_z252": "short_dated_otm_call_share",
        "vol_gt_oi_share_z252": "vol_gt_oi_share",
        "block_share_z252": "block_share",
    }
    z_out: dict = {}
    for z_key, col in z_fields.items():
        if col not in df.columns:
            z_out[z_key] = None
            continue
        series = df[col].dropna()
        if len(series) < _TICKERS_CTX_MIN_HISTORY:
            z_out[z_key] = None
            continue
        # Use a trailing 252-day window for mean/std; fall back to full history
        window = series.iloc[-_Z_WINDOW:] if len(series) >= _Z_WINDOW else series
        mu = float(window.mean())
        sigma = float(window.std(ddof=1)) if len(window) > 1 else 0.0
        today_val = float(series.iloc[-1])
        if sigma == 0.0 or not np.isfinite(sigma):
            z_out[z_key] = None
        else:
            z_out[z_key] = _f((today_val - mu) / sigma, 2)

    base["z"] = z_out
    return base


# --------------------------------------------------------------------------- #
# CONTRACT v2 — oi_confirmed.json
# --------------------------------------------------------------------------- #

def build_oi_confirmed(
    asof: str,
    live_flow_out_dir,
    oi_movers_today: dict | None = None,
    top_n: int = 50,
) -> list[dict]:
    """Build options_hub/oi_confirmed.json.

    Contracts that were notable in the PREVIOUS session's poller feed payload
    AND appear in today's top ΔOI movers.

    Strategy:
      1. Load the most recent archived feed payload from data/live_flow_out/
         (either feed_current.json or the most recent archive_YYYYMMDDTHH.json
         whose date-prefix is < asof).
      2. Extract all contracts from root_top_contracts in that feed.
      3. Intersect with today's oi_movers (passed in as oi_movers_today or
         loaded from data/live_flow_out/options_hub/oi_movers.json).
      4. Return [{root, right, exp, strike, prev_premium, delta_oi}].

    Degrades to [] on missing inputs — never raises.
    """
    import json as _json
    from pathlib import Path as _Path

    live_dir = _Path(live_flow_out_dir)

    # ── load previous session's notable contracts ────────────────────────────
    prev_contracts: list[dict] = []
    try:
        # Prefer feed_current.json (written by poller at end of each session)
        feed_path = live_dir / "feed_current.json"
        archive_path: _Path | None = None

        if not feed_path.exists():
            # Fall back to most recent archive_YYYYMMDDTHH.json strictly before asof
            archives = sorted(live_dir.glob("archive_*.json"))
            # key format: archive_YYYYMMDDTHH.json — date prefix is first 8 chars after _
            for a in reversed(archives):
                stem = a.stem  # e.g. "archive_20260704T10"
                parts = stem.split("_", 1)
                if len(parts) < 2:
                    continue
                date_part = parts[1][:8]  # YYYYMMDD
                try:
                    arc_date = str(pd.Timestamp(date_part).date())
                except Exception:  # noqa: BLE001
                    continue
                if arc_date < asof:
                    archive_path = a
                    break

        chosen = feed_path if feed_path.exists() else archive_path
        if chosen is not None and chosen.exists():
            raw = _json.loads(chosen.read_text(encoding="utf-8"))
            rtc = raw.get("root_top_contracts", {})
            for root_sym, contracts in rtc.items():
                for c in (contracts or []):
                    if isinstance(c, dict):
                        prev_contracts.append({
                            "root": root_sym,
                            "right": c.get("right", ""),
                            "exp": str(c.get("expiration", c.get("exp", ""))),
                            "strike": c.get("strike"),
                            "prev_premium": c.get("premium", c.get("gross_premium")),
                        })
        else:
            log.debug("build_oi_confirmed: no feed/archive found in %s", live_dir)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_oi_confirmed: prev-session load failed — %s", exc)
        return []

    if not prev_contracts:
        return []

    # ── load or use today's oi_movers ────────────────────────────────────────
    movers_list: list[dict] = []
    try:
        if oi_movers_today is not None:
            movers_list = oi_movers_today.get("movers", [])
        else:
            oi_path = live_dir / "options_hub" / "oi_movers.json"
            if oi_path.exists():
                movers_list = _json.loads(oi_path.read_text(encoding="utf-8")).get("movers", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("build_oi_confirmed: oi_movers load failed — %s", exc)
        return []

    if not movers_list:
        return []

    # ── intersect on (root, right, exp, strike) key ──────────────────────────
    # Normalise `right` to single-char upper ("C"/"P") on both sides so that
    # mixed conventions ("call"/"put" vs "C"/"P") never silently empty the join.
    def _norm_right(v) -> str:
        return str(v).upper()[:1]

    # Build a lookup from today's oi_movers
    mover_idx: dict[tuple, int] = {}  # key -> d_oi
    for m in movers_list[:top_n]:
        key = (
            str(m.get("root", "")),
            _norm_right(m.get("right", "")),
            str(m.get("exp", "")),
            _f(float(m["strike"]), 2) if m.get("strike") is not None else None,
        )
        mover_idx[key] = int(m.get("d_oi", 0))

    confirmed: list[dict] = []
    for c in prev_contracts:
        right_norm = _norm_right(c.get("right", ""))
        key = (
            str(c.get("root", "")),
            right_norm,
            str(c.get("exp", "")),
            _f(float(c["strike"]), 2) if c.get("strike") is not None else None,
        )
        if key in mover_idx:
            confirmed.append({
                "root": c["root"],
                "right": right_norm,
                "exp": c["exp"],
                "strike": _f(float(c["strike"]), 2) if c.get("strike") is not None else None,
                "prev_premium": _f(c.get("prev_premium"), 2),
                "delta_oi": mover_idx[key],
            })

    return confirmed
