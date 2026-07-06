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

    # ── IV rank 252 ───────────────────────────────────────────────────────────
    history_rows, iv_rank_252 = _compute_iv_history(df, root, asof, spot)

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


def _compute_iv_history(df: pd.DataFrame, root: str, asof: str, spot_today: float) -> tuple[list[dict], float | None]:
    """Build the last-90-sessions IV history and compute iv_rank_252.

    Returns (history_rows, iv_rank_252).
    iv_rank_252 = percentile of today's 30d-interpolated ATM IV in trailing 252 sessions.
    Null if <60 observed sessions (per spec).
    """
    # All dates with greeks available
    valid = df[df["implied_vol"].notna() & (df["implied_vol"] > 0)].copy()
    if valid.empty:
        return [], None

    all_dates = sorted(valid["date"].unique())
    all_dates_before_asof = [d for d in all_dates if d <= asof]
    if not all_dates_before_asof:
        return [], None

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
        return [], None

    sorted_dates = sorted(per_date_iv)

    # ── iv_rank_252 ────────────────────────────────────────────────────────────
    # Last 252 sessions ending at asof
    trailing_252 = [d for d in sorted_dates if d <= asof][-252:]
    iv_rank_252: float | None = None
    if len(trailing_252) >= 60 and asof in per_date_iv:
        today_iv = per_date_iv[asof]
        window_ivs = [per_date_iv[d] for d in trailing_252]
        rank = sum(1 for v in window_ivs if v < today_iv) / len(window_ivs)
        iv_rank_252 = round(rank * 100, 1)

    # ── history: last 90 sessions ─────────────────────────────────────────────
    last_90 = [d for d in sorted_dates if d <= asof][-90:]
    history_rows: list[dict] = []
    for d in last_90:
        history_rows.append({
            "date": d,
            "iv_rank": None,  # per-point rank not required by spec
            "atm_iv": per_date_iv[d],
            "close": None,  # caller can enrich; omitting avoids a yahoo join here
        })

    return history_rows, iv_rank_252


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
