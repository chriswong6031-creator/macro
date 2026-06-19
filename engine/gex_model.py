"""engine/gex_model.py — the rich options / dealer-gamma MODELING layer behind gex.html.

Takes ONE underlying's per-strike option chain (the Cboe delayed feed supplies the
full grid: strike × expiry with exchange-computed greeks, IV, OI, volume, bid/ask)
and produces every view the Options Desk page renders:

  • net-gamma PROFILE curve  — dealer $gamma re-evaluated across a ±spot grid, so the
                               zero-gamma flip and how gamma deepens become visible
  • GEX-by-strike WALLS       — net dealer gamma per strike + the call wall / put wall
  • strike × expiry HEATMAP   — net-gamma / open-interest / volume surfaces
  • vol SMILE + IV TERM        — IV by strike (front expiry) and ATM-IV by expiry
  • EXPECTED MOVE             — IV-implied daily / weekly + the front ATM-straddle move
  • MAX PAIN per expiry, dealer net delta, put/call OI & volume

Reuses engine.gex_engine.compute_gex for the headline regime summary so the page and
the macro overlay never drift. DISPLAY / RESEARCH ONLY — same honest framing as
gex_engine: the dealer long-call / short-put SIGN is an unobservable ASSUMPTION
(robust for indices, fragile for single names where a covered-call ETF or heavy retail
call-buying can flip it); magnet / wall / flip strikes are LEVELS where hedging
concentrates, never targets; the feed is delayed EOD, not live intraday flow. See
LIMITATIONS.md.

Input contract — chain: DataFrame with columns K (strike), T (years to expiry),
is_call (bool), oi (open interest), iv (DECIMAL vol), expiry (datetime), and OPTIONALLY
gamma, delta, volume, bid, ask (used when present, recomputed / skipped otherwise).
spot: float. cfg overrides DEFAULTS.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from engine.gex_engine import compute_gex
from engine.greeks import SQRT2PI, bs_greeks

DEFAULTS = dict(
    contract_multiplier=100.0, pct_move=0.01, r=0.043, q=0.0,
    # the gamma-flip / profile spot grid (re-evaluates dealer gamma across ±span)
    flip_window_pct=0.25, profile_span=0.15, profile_points=81,
    # the per-strike "walls" ladder (aggregated across expiries within the horizon)
    wall_window_pct=0.12, wall_max_strikes=40, max_expiry_days=365,
    # the strike × expiry surface
    heat_window_pct=0.10, heat_max_strikes=26, heat_max_expiries=12,
    # the volatility smile (front expiry) and the IV term structure
    smile_window_pct=0.15, term_max_expiries=12,
    trading_days=252.0,
    # volatility-hole: "coiled" when spot is within this many daily-σ of a wall
    hole_arm_sigma=1.0,
)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _f(x, n=2):
    """Round to n dp, or None for NaN/inf/non-numeric — JSON-safe."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if np.isfinite(v) else None


def _expiry_label(ts) -> str:
    d = pd.Timestamp(ts)
    today = pd.Timestamp(date.today())
    # within ~11 months show "Jun 20"; further out disambiguate the year
    return d.strftime("%b %d") if (d - today).days < 330 else d.strftime("%b %d ’%y")


def _window(chain: pd.DataFrame, spot: float, pct: float, *, need_iv=True) -> pd.DataFrame:
    c = chain[(chain["T"] > 0) & (chain["oi"] > 0)
              & chain["K"].between(spot * (1 - pct), spot * (1 + pct))].copy()
    if need_iv:
        c = c[c["iv"] > 0]
    return c


def _dollar_gamma(c: pd.DataFrame, spot: float, mult: float, pm: float) -> pd.Series:
    """Unsigned $-gamma per ``pm`` move (gamma·OI·mult·S²·pm) using the feed's
    per-contract gamma where finite, else a Black-Scholes fallback."""
    g = c.get("gamma")
    if g is None:
        g = pd.Series(np.nan, index=c.index)
    miss = ~np.isfinite(g.to_numpy(dtype=float))
    if miss.any():
        bs = [bs_greeks(spot, k, t, s, True)[1]
              for k, t, s in zip(c["K"], c["T"], c["iv"])]
        g = g.copy()
        g.loc[miss] = np.array(bs, dtype=float)[miss.to_numpy()] if hasattr(miss, "to_numpy") else np.array(bs)[miss]
    return g.astype(float) * c["oi"].astype(float) * mult * spot ** 2 * pm


# --------------------------------------------------------------------------- #
# views
# --------------------------------------------------------------------------- #
def gamma_profile(chain: pd.DataFrame, spot: float, cf: dict) -> dict:
    """Net dealer $gamma (in $bn / 1% move) re-evaluated across a ±span spot grid —
    the curve whose zero-crossing is the gamma flip. Mirrors gex_engine._gamma_flip
    but returns the WHOLE curve, not just the crossing, so the page can draw it."""
    c = _window(chain, spot, cf["flip_window_pct"])
    if len(c) < 12 or not (spot > 0):
        return {"spots": [], "gamma_bn": [], "flip": None, "spot": _f(spot)}
    K = c["K"].to_numpy(float); T = c["T"].to_numpy(float)
    sig = c["iv"].to_numpy(float); oi = c["oi"].to_numpy(float)
    sgn = np.where(c["is_call"].to_numpy(bool), 1.0, -1.0)
    r, q, mult, pm = cf["r"], cf["q"], cf["contract_multiplier"], cf["pct_move"]
    sqrtT = np.sqrt(T)
    span = cf["profile_span"]
    grid = spot * np.linspace(1 - span, 1 + span, int(cf["profile_points"]))
    net = np.empty(len(grid))
    for i, Sx in enumerate(grid):
        d1 = (np.log(Sx / K) + (r - q + 0.5 * sig * sig) * T) / (sig * sqrtT)
        gamma = np.exp(-q * T) * np.exp(-0.5 * d1 * d1) / SQRT2PI / (Sx * sig * sqrtT)
        net[i] = float(np.sum(sgn * gamma * oi * mult * Sx * Sx * pm))
    # zero-gamma crossing nearest spot
    flip = None
    cross = []
    for i in range(len(grid) - 1):
        if net[i] == 0 or (net[i] < 0) != (net[i + 1] < 0):
            x0, x1, y0, y1 = grid[i], grid[i + 1], net[i], net[i + 1]
            cross.append(x0 - y0 * (x1 - x0) / (y1 - y0) if y1 != y0 else x0)
    if cross:
        flip = float(min(cross, key=lambda f: abs(f - spot)))
    return {"spots": [round(float(g), 2) for g in grid],
            "gamma_bn": [round(float(v) / 1e9, 4) for v in net],
            "flip": _f(flip), "spot": _f(spot)}


def strike_walls(chain: pd.DataFrame, spot: float, cf: dict) -> dict:
    """Per-strike net dealer gamma (call green / put red) aggregated across expiries
    within the horizon, plus the call wall (largest +gamma strike above spot) and put
    wall (largest -gamma strike below). Also call/put OI & volume per strike for the
    profile chart."""
    maxT = cf["max_expiry_days"] / 365.0
    c = _window(chain, spot, cf["wall_window_pct"])
    c = c[c["T"] <= maxT]
    if c.empty:
        return {"by_strike": [], "call_wall": None, "put_wall": None,
                "largest_oi": None, "max_abs_mn": 0}
    mult, pm = cf["contract_multiplier"], cf["pct_move"]
    dg = _dollar_gamma(c, spot, mult, pm)                       # unsigned $gamma
    sign = np.where(c["is_call"], 1.0, -1.0)
    c = c.assign(_net=sign * dg, _absdg=dg.abs(),
                 _coi=np.where(c["is_call"], c["oi"], 0.0),
                 _poi=np.where(~c["is_call"], c["oi"], 0.0),
                 _cv=np.where(c["is_call"], c.get("volume", 0.0), 0.0),
                 _pv=np.where(~c["is_call"], c.get("volume", 0.0), 0.0))
    g = c.groupby("K").agg(net=("_net", "sum"), absdg=("_absdg", "sum"),
                           coi=("_coi", "sum"), poi=("_poi", "sum"),
                           cv=("_cv", "sum"), pv=("_pv", "sum")).reset_index()
    # keep the structurally biggest strikes, then present high→low
    g = g.sort_values("absdg", ascending=False).head(int(cf["wall_max_strikes"]))
    g = g.sort_values("K", ascending=False)
    # walls: heaviest POSITIVE gamma above spot, heaviest NEGATIVE below
    above = g[(g["K"] > spot) & (g["net"] > 0)]
    below = g[(g["K"] < spot) & (g["net"] < 0)]
    call_wall = float(above.loc[above["net"].idxmax(), "K"]) if not above.empty else None
    put_wall = float(below.loc[below["net"].idxmin(), "K"]) if not below.empty else None
    g["_oi"] = g["coi"] + g["poi"]
    largest_oi = float(g.loc[g["_oi"].idxmax(), "K"]) if g["_oi"].max() > 0 else None
    mx = float(g["net"].abs().max()) or 1.0
    rows = [{"K": _f(r.K), "net_mn": round(float(r.net) / 1e6, 2),
             "pct": round(float(r.net) / mx * 100, 1),
             "call_oi": int(r.coi), "put_oi": int(r.poi),
             "call_vol": int(r.cv), "put_vol": int(r.pv)}
            for r in g.itertuples()]
    return {"by_strike": rows, "call_wall": _f(call_wall), "put_wall": _f(put_wall),
            "largest_oi": _f(largest_oi), "max_abs_mn": round(mx / 1e6, 2)}


def surface(chain: pd.DataFrame, spot: float, cf: dict) -> dict:
    """strike × expiry matrices for the heatmaps: net dealer gamma ($mn), open
    interest, and volume. Columns = the nearest expiries with real OI; rows = the
    strikes carrying the most total $gamma in the window (presented high→low)."""
    c = _window(chain, spot, cf["heat_window_pct"], need_iv=False)
    if c.empty:
        return {"strikes": [], "expiries": [], "days": [],
                "z_gex": [], "z_oi": [], "z_vol": [], "gex_max": 0, "oi_max": 0, "vol_max": 0}
    c = c[c["iv"].fillna(0) >= 0]  # keep all; gamma fallback handles iv-less wings
    mult, pm = cf["contract_multiplier"], cf["pct_move"]
    dg = _dollar_gamma(c.assign(iv=c["iv"].fillna(0.0001)), spot, mult, pm)
    sign = np.where(c["is_call"], 1.0, -1.0)
    c = c.assign(_net=sign * dg, _absdg=dg.abs())
    # expiry columns: nearest N by date among those with meaningful OI
    exp_oi = c.groupby("expiry")["oi"].sum().sort_index()
    exp_oi = exp_oi[exp_oi > exp_oi.max() * 0.01]
    exps = list(exp_oi.index[: int(cf["heat_max_expiries"])])
    if not exps:
        return {"strikes": [], "expiries": [], "days": [],
                "z_gex": [], "z_oi": [], "z_vol": [], "gex_max": 0, "oi_max": 0, "vol_max": 0}
    c = c[c["expiry"].isin(exps)]
    # strike rows: the heaviest total-$gamma strikes (fallback to OI when gamma flat)
    by_k = c.groupby("K").agg(absdg=("_absdg", "sum"), oi=("oi", "sum"))
    rank = by_k["absdg"] if by_k["absdg"].sum() > 0 else by_k["oi"]
    strikes = sorted(rank.sort_values(ascending=False)
                     .head(int(cf["heat_max_strikes"])).index, reverse=True)
    today = pd.Timestamp(date.today())
    vol_col = "volume" if "volume" in c.columns else None
    z_gex, z_oi, z_vol = [], [], []
    for k in strikes:
        rg, ro, rv = [], [], []
        for e in exps:
            cell = c[(c["K"] == k) & (c["expiry"] == e)]
            if cell.empty:
                rg.append(None); ro.append(None); rv.append(None)
            else:
                rg.append(round(float(cell["_net"].sum()) / 1e6, 2))
                ro.append(int(cell["oi"].sum()))
                rv.append(int(cell[vol_col].sum()) if vol_col else None)
        z_gex.append(rg); z_oi.append(ro); z_vol.append(rv)
    flat = lambda zz: [abs(v) for r in zz for v in r if v is not None]
    gmax = max(flat(z_gex), default=0); omax = max(flat(z_oi), default=0)
    vmax = max(flat(z_vol), default=0)
    return {"strikes": [_f(k) for k in strikes],
            "expiries": [_expiry_label(e) for e in exps],
            "days": [int((pd.Timestamp(e) - today).days) for e in exps],
            "z_gex": z_gex, "z_oi": z_oi, "z_vol": z_vol,
            "gex_max": round(gmax, 2), "oi_max": omax, "vol_max": vmax}


def _atm_iv(g: pd.DataFrame, spot: float):
    """ATM IV for one expiry: mean of the call & put IV nearest spot."""
    gv = g[(g["iv"] > 0)]
    if gv.empty:
        return None
    near = gv.loc[(gv["K"] - spot).abs().idxmin(), "K"]
    at = gv[gv["K"] == near]
    return float(at["iv"].mean())


def _max_pain(g: pd.DataFrame):
    strikes = np.sort(g["K"].unique())
    if not len(strikes):
        return None
    calls, puts = g[g["is_call"]], g[~g["is_call"]]
    pain = []
    for P in strikes:
        cc = (calls["oi"] * (P - calls["K"]).clip(lower=0)).sum()
        pp = (puts["oi"] * (puts["K"] - P).clip(lower=0)).sum()
        pain.append(cc + pp)
    return float(strikes[int(np.argmin(pain))])


def _straddle_move(g: pd.DataFrame, spot: float):
    """Front ATM-straddle implied 1σ move (call mid + put mid at the nearest strike),
    using bid/ask when present else last/theo. Returns (abs, pct) or (None, None)."""
    if not {"bid", "ask"}.issubset(g.columns):
        return None, None
    near = g.loc[(g["K"] - spot).abs().idxmin(), "K"]
    at = g[g["K"] == near]
    c = at[at["is_call"]]; p = at[~at["is_call"]]
    if c.empty or p.empty:
        return None, None
    def mid(row):
        b, a = float(row["bid"].iloc[0] or 0), float(row["ask"].iloc[0] or 0)
        m = (b + a) / 2 if (b > 0 and a > 0) else max(b, a)
        return m
    strad = mid(c) + mid(p)
    if strad <= 0:
        return None, None
    return float(strad), float(strad / spot * 100)


def iv_term(chain: pd.DataFrame, spot: float, cf: dict) -> list[dict]:
    """ATM-IV term structure: per expiry the ATM IV, the IV-implied move, the
    straddle-implied move, and max pain."""
    c = chain[(chain["T"] > 0) & (chain["oi"] > 0)].copy()
    out = []
    today = pd.Timestamp(date.today())
    for e, g in c.groupby("expiry"):
        atm = _atm_iv(g, spot)
        if atm is None:
            continue
        T = float(g["T"].iloc[0])
        sa, sp = _straddle_move(g, spot)
        out.append({"expiry": _expiry_label(e),
                    "days": int((pd.Timestamp(e) - today).days),
                    "atm_iv": round(atm * 100, 2),
                    "move_pct": round(atm * np.sqrt(max(T, 1e-6)) * 100, 2),
                    "straddle_pct": _f(sp), "max_pain": _f(_max_pain(g))})
    out.sort(key=lambda r: r["days"])
    return out[: int(cf["term_max_expiries"])]


def vol_smile(chain: pd.DataFrame, spot: float, cf: dict) -> dict:
    """IV by strike for the front liquid expiry (the skew/smile). Picks the nearest
    expiry that is ≥2 days out and carries enough strikes to be meaningful."""
    c = _window(chain, spot, cf["smile_window_pct"])
    if c.empty:
        return {"expiry": None, "days": None, "strikes": [], "call_iv": [], "put_iv": []}
    today = pd.Timestamp(date.today())
    cand = c[c["T"] * 365 >= 2]
    if cand.empty:
        cand = c
    counts = cand.groupby("expiry")["K"].nunique()
    # nearest expiry with ≥6 distinct strikes, else the richest one
    rich = counts[counts >= 6]
    exp = (sorted(rich.index)[0] if not rich.empty
           else counts.sort_values(ascending=False).index[0])
    g = cand[cand["expiry"] == exp]
    ks = sorted(g["K"].unique())
    civ, piv = [], []
    for k in ks:
        cc = g[(g["K"] == k) & g["is_call"]]["iv"]
        pp = g[(g["K"] == k) & ~g["is_call"]]["iv"]
        civ.append(round(float(cc.mean()) * 100, 2) if not cc.empty and cc.mean() > 0 else None)
        piv.append(round(float(pp.mean()) * 100, 2) if not pp.empty and pp.mean() > 0 else None)
    return {"expiry": _expiry_label(exp), "days": int((pd.Timestamp(exp) - today).days),
            "strikes": [_f(k) for k in ks], "call_iv": civ, "put_iv": piv}


def _net_delta_bn(chain: pd.DataFrame, spot: float, cf: dict):
    """Dealer net $delta (long-call / short-put sign) in $bn — positioning context."""
    c = _window(chain, spot, cf["flip_window_pct"], need_iv=False)
    if c.empty or "delta" not in c.columns:
        return None
    d = c["delta"].astype(float)
    if not np.isfinite(d).any():
        return None
    sign = np.where(c["is_call"], 1.0, -1.0)
    nd = float(np.nansum(sign * d * c["oi"].astype(float) * cf["contract_multiplier"] * spot))
    return round(nd / 1e9, 2)


def expected_move(iv30, spot, cf, term) -> dict:
    """IV-implied daily / weekly 1σ move + the front ATM-straddle move (from the
    term structure's first row that carries a straddle)."""
    td = cf["trading_days"]
    em = {"daily_pct": None, "daily_abs": None, "weekly_pct": None, "weekly_abs": None,
          "front": None}
    if iv30 and iv30 > 0 and spot and spot > 0:
        dp = iv30 * np.sqrt(1.0 / td); wp = iv30 * np.sqrt(5.0 / td)
        em.update(daily_pct=round(dp * 100, 2), daily_abs=round(spot * dp, 2),
                  weekly_pct=round(wp * 100, 2), weekly_abs=round(spot * wp, 2))
    for row in term:
        if row.get("straddle_pct"):
            em["front"] = {"expiry": row["expiry"], "days": row["days"],
                           "pct": row["straddle_pct"],
                           "abs": round(spot * row["straddle_pct"] / 100, 2)}
            break
    return em


def volatility_hole(summary: dict, em: dict, cf: dict) -> dict:
    """Re-express the dealer-gamma map as a "volatility hole" (the DannyTrades framing,
    given a real mechanism). Long gamma = a SUPPRESSIVE band: dealers fade moves so
    price pins between the put-wall floor and call-wall ceiling — the "hole". A daily
    CLOSE beyond a wall flips hedging pro-cyclical and RELEASES the move (the wall is a
    valve, not a target). Short gamma = the "black hole": below the flip dealers hedge
    WITH the move so realized vol EXPANDS and there is no suppressive band until price
    reclaims the flip.

    DISPLAY-ONLY and mechanism-first: a relabeling of gamma_flip / call_wall / put_wall /
    expected_move already on the page (so it can never drift from them), NOT a new data
    source and NOT a backtested edge. Same honest caveats as gex_engine — the dealer
    sign is an assumption (fragile for single names), levels are where hedging
    concentrates, the feed is delayed EOD. Distances are measured in DAILY expected-move
    σ so "near a wall" means the same thing on a $40 ETF and a $900 name.

    Language-neutral (gex.js renders the bilingual labels). States:
      IN_HOLE · COILED_UP · COILED_DOWN · EXPANSION · NONE
    The walls are computed SPOT-relative (call wall strictly above spot, put wall below),
    so a single EOD snapshot always has spot inside the band — a "spot beyond the wall"
    breakout can't be read from one frame. The genuine realized downside release is the
    flip into short gamma (EXPANSION); the COILED states are the armed edges where the
    next daily close decides it. (A true cross-day breakout would need persisted wall
    history — a fast-follow, not this leaf.)
    """
    none = {"state": "NONE", "bias": "neutral", "upper": None, "lower": None,
            "upper_src": None, "lower_src": None, "to_upper_pct": None,
            "to_lower_pct": None, "to_upper_sigma": None, "to_lower_sigma": None,
            "band_width_pct": None, "compression": None, "pos": None}
    spot = summary.get("spot")
    if not spot or spot <= 0:
        return none
    regime = summary.get("regime")                       # "long" / "short" / None
    cw, pw = summary.get("call_wall"), summary.get("put_wall")
    mu, md = summary.get("magnet_up"), summary.get("magnet_down")
    daily = em.get("daily_pct")                          # percent, 1σ/day
    weekly = em.get("weekly_pct")
    arm = float(cf.get("hole_arm_sigma", 1.0))           # "coiled" if within this many σ

    # boundaries: prefer the gamma WALLS, fall back to the heaviest-OI magnets
    upper, upper_src = ((cw, "call_wall") if (cw and cw > spot)
                        else (mu, "magnet_up") if (mu and mu > spot) else (None, None))
    lower, lower_src = ((pw, "put_wall") if (pw and pw < spot)
                        else (md, "magnet_down") if (md and md < spot) else (None, None))

    sig_abs = spot * daily / 100.0 if (daily and daily > 0) else None
    to_upper_pct = round((upper - spot) / spot * 100.0, 2) if upper is not None else None
    to_lower_pct = round((spot - lower) / spot * 100.0, 2) if lower is not None else None
    to_upper_sigma = round((upper - spot) / sig_abs, 2) if (upper is not None and sig_abs) else None
    to_lower_sigma = round((spot - lower) / sig_abs, 2) if (lower is not None and sig_abs) else None

    band_width_pct = (round((upper - lower) / spot * 100.0, 2)
                      if (upper is not None and lower is not None) else None)
    pos = None
    if upper is not None and lower is not None and upper > lower:
        pos = round(min(1.0, max(0.0, (spot - lower) / (upper - lower))), 3)
    # how tight the hole is vs a weekly 1σ move — a narrow, deep hole coils harder
    compression = None
    if band_width_pct is not None and weekly and weekly > 0:
        ratio = band_width_pct / (2.0 * weekly)
        compression = "tight" if ratio <= 1.0 else "normal" if ratio <= 2.0 else "wide"

    # ---- state machine ----
    if regime == "short":
        state, bias = "EXPANSION", "volatile"            # below the flip → the black hole
    else:                                                # long / neutral gamma → suppressive band
        near_up = to_upper_sigma is not None and to_upper_sigma <= arm
        near_dn = to_lower_sigma is not None and to_lower_sigma <= arm
        if near_up and (not near_dn or to_upper_sigma <= to_lower_sigma):
            state, bias = "COILED_UP", "up"              # armed at the ceiling
        elif near_dn:
            state, bias = "COILED_DOWN", "down"          # armed at the floor (close below → expansion)
        elif upper is not None or lower is not None:
            state, bias = "IN_HOLE", "neutral"           # pinned inside the band
        else:
            state, bias = "NONE", "neutral"

    return {"state": state, "bias": bias, "upper": _f(upper), "lower": _f(lower),
            "upper_src": upper_src, "lower_src": lower_src,
            "to_upper_pct": to_upper_pct, "to_lower_pct": to_lower_pct,
            "to_upper_sigma": to_upper_sigma, "to_lower_sigma": to_lower_sigma,
            "band_width_pct": band_width_pct, "compression": compression, "pos": pos}


# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #
def build_model(chain: pd.DataFrame, spot: float, cfg: dict | None = None,
                *, meta: dict | None = None, history: list | None = None) -> dict | None:
    """Full per-underlying payload for gex.html. Returns None when the chain is too
    thin to model. Reuses compute_gex for the headline regime summary, then layers the
    profile / walls / surface / smile / term / expected-move views on top."""
    cf = {**DEFAULTS, **(cfg or {})}
    if chain is None or len(chain) == 0 or not (spot and spot > 0):
        return None
    base = compute_gex(chain[["K", "T", "iv", "oi", "is_call", "expiry"]]
                       if "expiry" in chain.columns else chain[["K", "T", "iv", "oi", "is_call"]],
                       spot, {k: cf[k] for k in ("contract_multiplier", "pct_move", "r", "q",
                                                 "strike_window_pct", "max_expiry_days")
                              if k in cf} | {"strike_window_pct": cf.get("flip_window_pct", 0.25)})
    if base.get("tier") in (None, "no_options"):
        return None

    walls = strike_walls(chain, spot, cf)
    term = iv_term(chain, spot, cf)
    iv30 = base.get("iv30")
    summary = {
        "spot": _f(spot), "regime": base.get("gamma_regime"), "tier": base.get("tier"),
        "net_gex_bn": _f(base.get("net_gex_bn")), "net_vex": _f(base.get("net_vex"), 0),
        "net_cex": _f(base.get("net_cex"), 0), "net_delta_bn": _net_delta_bn(chain, spot, cf),
        "gamma_flip": _f(base.get("gamma_flip")), "dist_to_flip_pct": _f(base.get("dist_to_flip_pct")),
        "magnet_up": _f(base.get("magnet_up")), "magnet_down": _f(base.get("magnet_down")),
        "charm_anchor": _f(base.get("charm_anchor")), "charm_net_sign": base.get("charm_net_sign"),
        "iv30": round(iv30 * 100, 2) if iv30 else None,
        "put_call_oi_ratio": _f(base.get("put_call_oi_ratio")),
        "max_pain": _f(base.get("max_pain")), "n_strikes": base.get("n_strikes"),
        "top_oi_share": _f(base.get("top_oi_share"), 3),
        "call_wall": walls["call_wall"], "put_wall": walls["put_wall"],
        "largest_oi": walls["largest_oi"],
    }
    # volume put/call (a flow tilt the OI ratio misses)
    if "volume" in chain.columns:
        cv = float(chain.loc[chain["is_call"], "volume"].fillna(0).sum())
        pv = float(chain.loc[~chain["is_call"], "volume"].fillna(0).sum())
        summary["put_call_vol_ratio"] = round(pv / cv, 2) if cv > 0 else None

    em = expected_move(iv30, spot, cf, term)
    return {
        "meta": meta or {},
        "summary": summary,
        "expected_move": em,
        "vol_hole": volatility_hole(summary, em, cf),
        "profile": gamma_profile(chain, spot, cf),
        "walls": walls,
        "surface": surface(chain, spot, cf),
        "smile": vol_smile(chain, spot, cf),
        "term": term,
        "history": history or [],
    }
