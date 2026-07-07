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


_MIN_IV = 0.005   # below this, BS gamma's 1/sigma factor explodes -> treat as no gamma


def _dollar_gamma(c: pd.DataFrame, spot: float, mult: float, pm: float) -> pd.Series:
    """Unsigned $-gamma per ``pm`` move (gamma·OI·mult·S²·pm) using the feed's
    per-contract gamma where finite, else a Black-Scholes fallback.

    A contract the feed left un-priced often has BOTH gamma and IV blank. The BS
    gamma fallback carries a 1/sigma factor, so a missing/near-zero IV (or a sentinel
    like 0.0001) yields a ~2500x near-money gamma spike that becomes the heatmap max
    and corrupts the whole color scale. So an unknown-IV (or non-positive T) contract
    is treated as ZERO gamma — an illiquid no-quote wing carries no measurable dealer
    gamma anyway."""
    g = c.get("gamma")
    if g is None:
        g = pd.Series(np.nan, index=c.index)
    miss = ~np.isfinite(g.to_numpy(dtype=float))
    if miss.any():
        def _bs_g(k, t, s):
            s = float(s) if s is not None and np.isfinite(s) else float("nan")
            if not np.isfinite(s) or s < _MIN_IV or not np.isfinite(t) or t <= 0:
                return 0.0
            return bs_greeks(spot, k, t, s, True)[1]
        bs = np.array([_bs_g(k, t, s) for k, t, s in zip(c["K"], c["T"], c["iv"])], dtype=float)
        g = g.copy()
        g.loc[miss] = bs[miss.to_numpy()] if hasattr(miss, "to_numpy") else bs[miss]
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
    # pass iv as-is (NaN on iv-less wings): _dollar_gamma zeroes any contract whose
    # gamma AND iv are both unknown, instead of the old 0.0001 sentinel that spiked it.
    dg = _dollar_gamma(c, spot, mult, pm)
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


def risk_reversal_25d(chain: pd.DataFrame, spot: float, cf: dict) -> float | None:
    """25-delta risk reversal = (25Δ call IV − 25Δ put IV) in vol points, for the nearest
    liquid expiry. Equity skew is STRUCTURALLY negative, so the LEVEL is display context only —
    the confirmer (engine/gex_confirm) uses its CHANGE, never this number alone. Best-effort:
    returns None when the chain carries no per-contract delta (the lighter compute_gex path)."""
    if chain is None or "delta" not in chain.columns or not (spot and spot > 0):
        return None
    c = chain[(chain["T"] * 365 >= 2) & (chain["oi"] > 0) & chain["iv"].notna()].copy()
    if c.empty or not c["delta"].notna().any():
        return None
    exp = sorted(c["expiry"].unique())[0] if "expiry" in c.columns else None
    g = c[c["expiry"] == exp] if exp is not None else c
    calls = g[g["is_call"]]
    puts = g[~g["is_call"]]
    if calls.empty or puts.empty:
        return None
    # the contract whose delta is closest to +0.25 (call) and −0.25 (put)
    ci = (calls["delta"].astype(float) - 0.25).abs().idxmin()
    pi = (puts["delta"].astype(float) + 0.25).abs().idxmin()
    civ, piv = float(calls.loc[ci, "iv"]), float(puts.loc[pi, "iv"])
    if not (civ > 0 and piv > 0):
        return None
    return round((civ - piv) * 100.0, 2)


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
# derived decision-support signals (DISPLAY-ONLY, qualitative bands, honest)
# --------------------------------------------------------------------------- #
# Coarse strength word-bands shared by every scored level (no decimals reach the
# user-facing word — only the transparent 0-100 score does). gex.js maps the KEY
# to bilingual text, mirroring the language-neutral vol_hole convention.
_STRENGTH_BANDS = ((75, "very_strong"), (55, "strong"), (35, "moderate"),
                   (18, "weak"), (0, "faint"))


def _strength_band(score) -> str | None:
    if score is None:
        return None
    for lo, key in _STRENGTH_BANDS:
        if score >= lo:
            return key
    return "faint"


def _level_strength(net_mn, max_abs_mn, level, spot, daily_abs):
    """Transparent 0-100 strength for a gamma WALL: 70% its share of the heaviest
    wall's $gamma (how much hedging clusters there) + 30% proximity in daily-σ (closer
    walls bite sooner). Returns (score, band, dist_sigma). A wall is where hedging
    concentrates, NOT a guaranteed stop or target — and the dealer sign is fragile for
    single names."""
    if level is None or not max_abs_mn or max_abs_mn <= 0 or not (spot and spot > 0):
        return None, None, None
    share = min(1.0, abs(net_mn) / max_abs_mn) if net_mn is not None else 0.0
    dist_sigma = (abs(level - spot) / daily_abs) if (daily_abs and daily_abs > 0) else None
    prox = max(0.0, min(1.0, 1.0 - dist_sigma / 6.0)) if dist_sigma is not None else 0.5
    score = int(round(100 * (0.70 * share + 0.30 * prox)))
    return score, _strength_band(score), (round(dist_sigma, 1) if dist_sigma is not None else None)


def _wall_hard(by_strike, level, spot):
    """A wall is a 'hard line' (vs OI smeared across neighbours) when its |net $gamma|
    is >= 2x the sum of the two nearest SAME-SIDE strikes."""
    if level is None or not by_strike or not spot:
        return None
    same = [r for r in by_strike if r.get("K") is not None
            and (r["K"] > spot) == (level > spot) and r["K"] != level]
    if not same:
        return None
    same.sort(key=lambda r: abs(r["K"] - level))
    neigh = sum(abs(r.get("net_mn") or 0.0) for r in same[:2])
    wall = next((abs(r.get("net_mn") or 0.0) for r in by_strike if r.get("K") == level), 0.0)
    if neigh <= 0:
        return True
    return bool(wall / neigh >= 2.0)


def _magnet_strength(max_pain, spot, top_oi_share, daily_abs):
    """Pin strength of the max-pain magnet: 70% OI concentration (top_oi_share) + 30%
    proximity. The magnet only genuinely pulls in a calm (long-gamma) regime — the
    tilt suppresses the pin leg in short gamma; the displayed strength stays structural."""
    if max_pain is None or not (spot and spot > 0) or top_oi_share is None:
        return None, None, None
    dist_sigma = (abs(max_pain - spot) / daily_abs) if (daily_abs and daily_abs > 0) else None
    prox = max(0.0, min(1.0, 1.0 - dist_sigma / 6.0)) if dist_sigma is not None else 0.5
    score = int(round(100 * (0.70 * min(1.0, float(top_oi_share)) + 0.30 * prox)))
    return score, _strength_band(score), (round(dist_sigma, 1) if dist_sigma is not None else None)


def _flip_strength(profile, flip):
    """How decisively the gamma curve crosses zero at the flip — a steep crossing is a
    firm regime line, a shallow one is mushy. Normalised against the steepest segment of
    the profile grid, then banded like the walls."""
    if not profile or flip is None:
        return None, None
    spots = profile.get("spots") or []
    gam = profile.get("gamma_bn") or []
    if len(spots) < 3 or len(gam) != len(spots):
        return None, None
    slopes, seg = [], None
    for i in range(len(spots) - 1):
        ds = spots[i + 1] - spots[i]
        if not ds:
            continue
        sl = abs((gam[i + 1] - gam[i]) / ds)
        slopes.append(sl)
        if spots[i] <= flip <= spots[i + 1]:
            seg = sl
    if seg is None or not slopes:
        return None, None
    mx = max(slopes) or 1.0
    score = int(round(100 * min(1.0, seg / mx)))
    return score, _strength_band(score)


def risk_reversal(chain: pd.DataFrame, spot: float, iv30, cf: dict) -> dict | None:
    """Front-expiry 25-delta RISK REVERSAL (25Δ put IV − 25Δ call IV, vol points) — the
    one genuinely directional skew tell. POSITIVE = puts bid (downside fear / protection
    demand); NEGATIVE = calls bid (upside chase). Uses the feed delta where present, else
    a Black-Scholes delta. DISPLAY-ONLY and days-to-weeks: skew is how the market PRICES
    risk, not a forecast — and equity puts are structurally bid, so the 'balanced' band
    is deliberately offset from zero (fear ≥ +3, greed ≤ −1)."""
    c = chain[(chain["T"] > 0) & (chain["oi"] > 0) & (chain["iv"] > 0)].copy()
    if c.empty or not (spot and spot > 0):
        return None
    cand = c[c["T"] * 365 >= 2]
    if cand.empty:
        cand = c
    counts = cand.groupby("expiry")["K"].nunique()
    rich = counts[counts >= 6]
    exp = (sorted(rich.index)[0] if not rich.empty
           else counts.sort_values(ascending=False).index[0])
    g = cand[cand["expiry"] == exp]
    if g["K"].nunique() < 4:
        return None
    d = g.get("delta")
    dd = d.to_numpy(float) if d is not None else np.full(len(g), np.nan)
    miss = ~np.isfinite(dd)
    if miss.any():
        bs = np.array([bs_greeks(spot, k, t, s, bool(cc))[0]
                       for k, t, s, cc in zip(g["K"], g["T"], g["iv"], g["is_call"])])
        dd = np.where(miss, bs, dd)
    g = g.assign(_delta=dd)
    calls, puts = g[g["is_call"]], g[~g["is_call"]]

    def pick(df, target):
        if df.empty or not np.isfinite(df["_delta"]).any():
            return None
        return float(df.loc[(df["_delta"] - target).abs().idxmin(), "iv"])

    civ, piv = pick(calls, 0.25), pick(puts, -0.25)
    if civ is None or piv is None or civ <= 0 or piv <= 0:
        return None
    rr25 = round((piv - civ) * 100.0, 2)                 # vol points
    atm = (iv30 * 100.0) if iv30 else None
    tone = "fear" if rr25 >= 3.0 else "greed" if rr25 <= -1.0 else "balanced"
    today = pd.Timestamp(date.today())
    return {"rr25": rr25, "skew_norm": (round(rr25 / atm, 3) if atm else None),
            "tone": tone, "put_iv25": round(piv * 100, 2), "call_iv25": round(civ * 100, 2),
            "expiry": _expiry_label(exp), "days": int((pd.Timestamp(exp) - today).days),
            "horizon": "days_weeks"}


def iv_rank(iv30_pct, history) -> dict | None:
    """Where today's IV30 sits in its OWN recent history — a SHORT-window percentile, not
    a true 52-week IV rank (we only persist ~40 trading days). Honest about the small
    sample via n_days + low_confidence. history items carry an 'iv30' field in PERCENT."""
    if iv30_pct is None or not history:
        return None
    xs = [h.get("iv30") for h in history if h.get("iv30") is not None]
    if len(xs) < 5:
        return None
    pct = int(round(100 * sum(1 for v in xs if v < iv30_pct) / len(xs)))
    band = ("rich" if pct >= 80 else "elevated" if pct >= 60 else "normal" if pct >= 40
            else "cheap" if pct >= 20 else "very_cheap")
    return {"rank_pct": pct, "band": band, "n_days": len(xs),
            "low_confidence": len(xs) < 20, "horizon": "days_weeks"}


def directional_tilt(summary: dict, em: dict, skew: dict | None, cf: dict) -> dict:
    """Independent directional LEANS, each carrying its OWN natural horizon — never one
    blended arrow. A blend goes structurally permabearish (charm is ~one-signed and
    equity skew is structurally downside), so we keep the legs SEPARATE and only
    synthesise an honest headline read. DISPLAY-ONLY: leans/tendencies from delayed EOD
    positioning, never a trade and never a target. Language-neutral; gex.js renders the
    bilingual prose + the per-leg horizon pills.

    Legs (each {signal, dir, strength, horizon, ...ctx}):
      charm   → intraday→1-2d hedging drift (dir from charm_net_sign)
      pin     → into the front expiry (only in calm gamma AND when price is near max-pain)
      skew    → days→weeks (25Δ risk-reversal tone)
      regime  → days, while the gamma regime persists (long=mean-revert, short=two-sided)
    """
    legs = []
    spot = summary.get("spot")
    regime = summary.get("regime")
    mp = summary.get("max_pain")
    weekly = (em or {}).get("weekly_pct")
    front_days = (em or {}).get("front", {}).get("days") if (em and em.get("front")) else None

    cs = summary.get("charm_net_sign")
    if cs:
        legs.append({"signal": "charm", "dir": "up" if cs > 0 else "down",
                     "strength": "weak", "horizon": "intraday_days"})

    if mp and spot and spot > 0 and regime != "short":
        dpct = abs(mp - spot) / spot * 100.0
        near = max(2.5, (weekly or 0.0))
        if 0.3 <= dpct <= near:
            legs.append({"signal": "pin", "dir": "pin",
                         "toward": "up" if mp > spot else "down",
                         "strength": "moderate" if dpct <= near / 2 else "weak",
                         "horizon": "into_expiry", "days": front_days, "target": mp})

    if skew and skew.get("tone") and skew["tone"] != "balanced":
        legs.append({"signal": "skew", "dir": "down" if skew["tone"] == "fear" else "up",
                     "strength": "moderate", "horizon": "days_weeks", "rr25": skew.get("rr25")})

    if regime in ("long", "short"):
        legs.append({"signal": "regime",
                     "dir": "mean_revert" if regime == "long" else "two_sided",
                     "strength": "moderate" if regime == "short" else "weak",
                     "horizon": "days_regime"})

    # Weighted, honest synthesis. Skew is the real directional tell (weight 2); the pin
    # is a mild expiry pull (1); charm is weak and ~one-signed (0.5) so it can NEVER
    # headline a direction alone — that was the old permabear bug. regime is non-directional.
    W = {"skew": 2.0, "pin": 1.0, "charm": 0.5}
    dirlegs = [l for l in legs if l["dir"] in ("up", "down")]
    net = sum(W.get(l["signal"], 0.0) * (1 if l["dir"] == "up" else -1) for l in dirlegs)
    has_pin = any(l["signal"] == "pin" for l in legs)
    ups = any(l["dir"] == "up" for l in dirlegs)
    dns = any(l["dir"] == "down" for l in dirlegs)
    if regime == "short":
        read = "volatile"
    elif net >= 1.5:
        read = "agree_up"
    elif net <= -1.5:
        read = "agree_down"
    elif net >= 0.75:
        read = "lean_up"
    elif net <= -0.75:
        read = "lean_down"
    elif ups and dns:
        read = "mixed"
    elif has_pin:
        read = "pinned"
    else:
        read = "balanced"

    # headline horizon = the highest-weight directional leg's horizon (so skew → days-weeks)
    headline = None
    if read in ("agree_up", "agree_down", "lean_up", "lean_down") and dirlegs:
        lead = max(dirlegs, key=lambda l: W.get(l["signal"], 0.0))
        headline = {"dir": lead["dir"], "horizon": lead["horizon"], "signal": lead["signal"]}
    elif read == "pinned":
        pin = next(l for l in legs if l["signal"] == "pin")
        headline = {"dir": "pin", "horizon": "into_expiry", "signal": "pin",
                    "days": pin.get("days")}
    conf = "low" if summary.get("tier") == "thin_chain" else "med"
    return {"legs": legs, "read": read, "headline": headline, "confidence": conf}


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
    # expiry is REQUIRED — the per-expiry views (iv_term / surface / vol_smile / risk_reversal)
    # all groupby("expiry"); both production collectors always emit it (see the input contract).
    if "expiry" not in chain.columns:
        return None
    _sym = (meta or {}).get("key") or (meta or {}).get("symbol")
    base = compute_gex(chain[["K", "T", "iv", "oi", "is_call", "expiry"]],
                       spot, {k: cf[k] for k in ("contract_multiplier", "pct_move", "r", "q",
                                                 "strike_window_pct", "max_expiry_days")
                              if k in cf} | {"strike_window_pct": cf.get("flip_window_pct", 0.25)},
                       symbol=_sym)
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
        "rr_25d": risk_reversal_25d(chain, spot, cf),   # display level; confirmer uses the CHANGE
        # Propagate regime_passport verbatim from gex_engine.compute_gex so that
        # gex_state.compute_gex_state can copy it without rebuilding (avoids basis mismatch).
        "regime_passport": base.get("regime_passport"),
    }
    # volume put/call (a flow tilt the OI ratio misses)
    if "volume" in chain.columns:
        cv = float(chain.loc[chain["is_call"], "volume"].fillna(0).sum())
        pv = float(chain.loc[~chain["is_call"], "volume"].fillna(0).sum())
        summary["put_call_vol_ratio"] = round(pv / cv, 2) if cv > 0 else None

    em = expected_move(iv30, spot, cf, term)
    profile = gamma_profile(chain, spot, cf)

    # ---- scored levels (request: words + strength, not bare numbers) ----------
    by_strike = walls.get("by_strike") or []
    max_abs = walls.get("max_abs_mn")
    daily_abs = em.get("daily_abs")
    net_of = {r["K"]: r["net_mn"] for r in by_strike if r.get("K") is not None}
    cw, pw, mp = walls["call_wall"], walls["put_wall"], summary["max_pain"]
    s_cw = _level_strength(net_of.get(cw), max_abs, cw, spot, daily_abs)
    s_pw = _level_strength(net_of.get(pw), max_abs, pw, spot, daily_abs)
    s_mag = _magnet_strength(mp, spot, base.get("top_oi_share"), daily_abs)
    fl_str, fl_band = _flip_strength(profile, summary["gamma_flip"])
    summary.update(
        call_wall_strength=s_cw[0], call_wall_band=s_cw[1], call_wall_dist_sigma=s_cw[2],
        call_wall_hard=_wall_hard(by_strike, cw, spot),
        put_wall_strength=s_pw[0], put_wall_band=s_pw[1], put_wall_dist_sigma=s_pw[2],
        put_wall_hard=_wall_hard(by_strike, pw, spot),
        magnet_strength=s_mag[0], magnet_band=s_mag[1], magnet_dist_sigma=s_mag[2],
        flip_strength=fl_str, flip_band=fl_band,
    )

    # ---- skew (25Δ risk-reversal) + short-window IV rank ----------------------
    skew = risk_reversal(chain, spot, iv30, cf)
    summary["skew"] = skew
    summary["iv_rank"] = iv_rank(summary["iv30"], history)

    return {
        "meta": meta or {},
        "summary": summary,
        "expected_move": em,
        "vol_hole": volatility_hole(summary, em, cf),
        "tilt": directional_tilt(summary, em, skew, cf),
        "profile": profile,
        "walls": walls,
        "surface": surface(chain, spot, cf),
        "smile": vol_smile(chain, spot, cf),
        "term": term,
        "history": history or [],
    }
