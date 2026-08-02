"""Equity/index dealer-gamma "magnets" engine — a VOL-REGIME + LEVELS MAP, NOT alpha.

Pure function over a per-strike option chain (the Cboe collector supplies it):
net GEX / VEX / CEX, the gamma-flip (zero-gamma spot, grid-reevaluated like
collectors/deribit._gamma_flip), the gamma regime, magnet strikes (where dealer
hedging concentrates), the charm anchor, ATM IV30, put/call OI and max-pain.

HONEST FRAMING (carried into every consumer, see
LIMITATIONS.md): the dealer long-call / short-put SIGN is an unobservable
assumption — weaker for single names (covered-call ETFs / retail call-buying can
flip true positioning); single-name GEX is fragile to one large non-dealer
position; the FREE Cboe feed is delayed / EOD so it MISSES the 0DTE flow that drives
intraday. Magnet / flip strikes are LEVELS (where hedging concentrates), never
targets. The one falsifiable claim — negative-gamma -> higher forward realized vol —
is checked in scripts/validate_gex.py.

Engine input contract — chain: DataFrame with columns
  K (strike), T (years to expiry), iv (DECIMAL vol), oi (open interest),
  is_call (bool), and optionally expiry. spot: float. cfg overrides DEFAULTS.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.greeks import SQRT2PI, bs_greeks

DEFAULTS = dict(
    contract_multiplier=100.0, pct_move=0.01, strike_window_pct=0.25,
    max_expiry_days=365, near_money_pct=0.10, min_strikes=40,
    conc_share_warn=0.35, r=0.0, q=0.0,
)


def _window(chain: pd.DataFrame, S: float, cfg: dict) -> pd.DataFrame:
    w = cfg["strike_window_pct"]
    maxT = cfg["max_expiry_days"] / 365.0
    return chain[(chain["T"] > 0) & (chain["T"] <= maxT)
                 & chain["K"].between(S * (1 - w), S * (1 + w))
                 & (chain["iv"] > 0) & (chain["oi"] > 0)].copy()


def gamma_profile(c: pd.DataFrame, S: float, cfg: dict):
    """Net dealer gamma RE-PRICED across a ±25% spot grid — the exposure PROFILE.

    This is the category's flagship object (masterplan §4.2 `profile`): exposure as a
    FUNCTION of spot, not merely at it. It is also the single source for the flip —
    ``_gamma_flip`` delegates here so the published curve and the published crossing
    can never disagree (the 2026-08-01 defect family was exactly two derivations of
    one quantity drifting apart).

    Returns ``(grid, net, flips)`` — numpy arrays of trial spots and net dealer gamma
    in dollars per ``pct_move`` at each, plus every zero-crossing (interpolated) —
    or ``(None, None, [])`` when the chain is too thin to re-price.
    """
    g = c.dropna(subset=["K", "T", "iv"])
    if len(g) < 20 or not (S > 0):
        return None, None, []
    K = g["K"].to_numpy(float); T = g["T"].to_numpy(float)
    sig = g["iv"].to_numpy(float); oi = g["oi"].to_numpy(float)
    sgn = np.where(g["is_call"].to_numpy(bool), 1.0, -1.0)
    r, q, mult, pm = cfg["r"], cfg["q"], cfg["contract_multiplier"], cfg["pct_move"]
    sqrtT = np.sqrt(T)
    grid = S * np.linspace(0.75, 1.25, 101)
    net = np.empty(len(grid))
    for i, Sx in enumerate(grid):
        d1 = (np.log(Sx / K) + (r - q + 0.5 * sig * sig) * T) / (sig * sqrtT)
        gamma = np.exp(-q * T) * np.exp(-0.5 * d1 * d1) / SQRT2PI / (Sx * sig * sqrtT)
        net[i] = float(np.sum(sgn * gamma * oi * mult * Sx * Sx * pm))
    flips = []
    for i in range(len(grid) - 1):
        if net[i] == 0.0 or (net[i] < 0) != (net[i + 1] < 0):
            x0, x1, y0, y1 = grid[i], grid[i + 1], net[i], net[i + 1]
            flips.append(float(x0 - y0 * (x1 - x0) / (y1 - y0) if y1 != y0 else x0))
    return grid, net, flips


def _gamma_flip(c: pd.DataFrame, S: float, cfg: dict):
    """Zero-gamma spot via a ±25% spot grid reevaluation (clone of
    collectors/deribit._gamma_flip, with the equity multiplier + r/q). ABOVE flip =
    net long gamma (dealers dampen / pin); BELOW = net short (dealers amplify).
    Returns (flip, signed dist-to-flip %, regime). Thin wrapper over
    ``gamma_profile`` — one grid evaluation, one definition."""
    grid, net, flips = gamma_profile(c, S, cfg)
    if grid is None:
        return None, None, None
    if not flips:
        return None, None, ("long" if net[len(grid) // 2] >= 0 else "short")
    flip = min(flips, key=lambda f: abs(f - S))
    return float(flip), round(100.0 * (S - flip) / S, 2), ("long" if S >= flip else "short")


def _max_pain(c: pd.DataFrame):
    front = c.groupby("expiry")["oi"].sum().idxmax()
    fe = c[c["expiry"] == front]
    strikes = np.sort(fe["K"].unique())
    if not len(strikes):
        return None
    pay = []
    for P in strikes:
        cc = (fe.loc[fe["is_call"], "oi"] * (P - fe.loc[fe["is_call"], "K"]).clip(lower=0)).sum()
        pp = (fe.loc[~fe["is_call"], "oi"] * (fe.loc[~fe["is_call"], "K"] - P).clip(lower=0)).sum()
        pay.append(cc + pp)
    return float(strikes[int(np.argmin(pay))])


def _iv30(c: pd.DataFrame, S: float):
    pts = []
    for _, g in c.groupby("expiry"):
        gv = g[g["iv"] > 0]
        if gv.empty:
            continue
        atm = gv.loc[(gv["K"] - S).abs().idxmin()]
        pts.append((float(atm["T"] * 365.0), float(atm["iv"])))
    if not pts:
        return None
    pts.sort()
    ten = [p[0] for p in pts]; ivs = [p[1] for p in pts]
    if ten[0] <= 30 <= ten[-1]:
        return float(np.interp(30, ten, ivs))
    return ivs[0] if 30 < ten[0] else ivs[-1]   # nearest listed tenor (no extrapolation)


def _pcr(c: pd.DataFrame):
    coi = c.loc[c["is_call"], "oi"].sum()
    poi = c.loc[~c["is_call"], "oi"].sum()
    return float(poi / coi) if coi > 0 else None


# Index products whose gamma regime is at least a market-wide read (still assumption-signed,
# but not a single-name product attribute). Everything else is treated as single-name.
_INDEX_PRODUCTS = frozenset({"SPX", "SPY", "QQQ", "NDX", "IWM", "RUT", "VIX", "DIA", "SPXW"})


def _gamma_regime_passport(symbol: str | None) -> dict:
    """Audit #29: the dealer long-call/short-put SIGN is unobservable from Cboe OI alone, so
    every gamma_regime is assumption-basis. For SINGLE NAMES the regime is additionally a
    near-constant PRODUCT ATTRIBUTE (covered-call ETFs / retail call-buying pin the sign), so
    the forward-RV validator's MIN_PER_BUCKET is structurally unreachable — it is NOT a
    time-varying signal and must never be read as one."""
    is_index = bool(symbol) and str(symbol).upper() in _INDEX_PRODUCTS
    return {
        "basis": "assumption",
        "structurally_constant": (not is_index) if symbol else None,
        "is_index_product": is_index if symbol else None,
        "verdict": "display-only",
        "note": ("dealer long-call/short-put sign is an unobservable assumption; "
                 + ("single-name gamma regime is a near-constant product attribute, not a "
                    "time-varying signal (validator MIN_PER_BUCKET structurally unreachable)"
                    if (symbol and not is_index) else
                    "even for indices SPY vs SPX can contradict same-day — read as assumption, "
                    "not observed")),
    }


def compute_gex(chain: pd.DataFrame, spot: float, cfg: dict | None = None,
                symbol: str | None = None) -> dict:
    """Per-strike chain -> magnets summary dict. Returns a low-confidence / empty
    tier when the chain is too thin to trust. NEVER fabricates. ``symbol`` (optional) lets the
    summary carry a gamma-regime PASSPORT flagging single-name regimes as assumption-signed +
    structurally-constant (audit #29)."""
    cf = {**DEFAULTS, **(cfg or {})}
    if chain is None or len(chain) == 0 or not (spot and spot > 0):
        return {"tier": "no_options", "note": "no listed options / empty chain"}
    c = _window(chain, spot, cf)
    n = int(len(c))
    if n < 6:
        return {"tier": "no_options", "n_strikes": n}
    if "expiry" not in c.columns:
        c["expiry"] = c["T"].round(6)

    g = [bs_greeks(spot, k, t, s, bool(cc), cf["r"], cf["q"])
         for k, t, s, cc in zip(c["K"], c["T"], c["iv"], c["is_call"])]
    c["gamma"] = [x[1] for x in g]
    c["vanna"] = [x[2] for x in g]
    c["charm"] = [x[3] for x in g]

    sign = np.where(c["is_call"], 1.0, -1.0)
    mult, pm = cf["contract_multiplier"], cf["pct_move"]
    dg = c["gamma"] * c["oi"] * mult * spot ** 2          # unsigned $ gamma (level)
    gex = sign * dg * pm                                   # $ / 1% move
    vex = sign * c["vanna"] * c["oi"] * mult * spot * pm   # $ delta / 1 vol pt-ish
    cex = sign * (c["charm"] / 365.0) * c["oi"] * mult * spot  # $ delta / day

    flip, dist, regime = _gamma_flip(c, spot, cf)

    dg_by_k = dg.groupby(c["K"]).sum()
    up = dg_by_k[dg_by_k.index > spot]
    dn = dg_by_k[dg_by_k.index < spot]
    magnet_up = float(up.idxmax()) if not up.empty else None
    magnet_dn = float(dn.idxmax()) if not dn.empty else None
    share = float(dg_by_k.max() / dg_by_k.sum()) if dg_by_k.sum() > 0 else 1.0

    nm = c[(c["K"] - spot).abs() <= spot * cf["near_money_pct"]]
    charm_anchor = None
    if not nm.empty:
        cex_by_k = cex[nm.index].groupby(nm["K"]).sum()
        if not cex_by_k.empty and float(cex_by_k.abs().max()) > 0:
            charm_anchor = float(cex_by_k.abs().idxmax())

    net_cex = float(cex.sum())
    tier = "thin_chain" if (n < cf["min_strikes"] or share > cf["conc_share_warn"]) else "full"

    return {
        "tier": tier, "n_strikes": n, "spot": float(spot),
        "net_gex_bn": float(gex.sum() / 1e9), "net_vex": float(vex.sum()), "net_cex": net_cex,
        "gamma_flip": flip, "dist_to_flip_pct": dist, "gamma_regime": regime,
        "regime_passport": _gamma_regime_passport(symbol),
        "magnet_up": magnet_up, "magnet_down": magnet_dn,
        "charm_anchor": charm_anchor,
        "charm_net_sign": (1 if net_cex > 0 else -1 if net_cex < 0 else 0),
        "iv30": _iv30(c, spot), "put_call_oi_ratio": _pcr(c), "max_pain": _max_pain(c),
        "top_oi_share": round(share, 3),
    }
