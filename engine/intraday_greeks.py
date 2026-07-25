"""engine/intraday_greeks.py — intraday Black-Scholes greek grids for the Flow-Surface store.

DISPLAY / RESEARCH ONLY. This computes a per-strike dealer-exposure MAP (GEX / DEX /
VEX / CEX surfaces + gamma flip / call-wall / put-wall) from the live options TAPE the
`live_flow` poller already pulls each cycle. It is NOT a signal, a rank, or a validated
edge — it feeds a heat map the Terminal surface pane shades, nothing more. The dealer
long-call / short-put SIGN is the same unobservable ASSUMPTION the EOD engine flags
(engine/gex_engine.py, engine/gex_model.py): robust-ish for indices, fragile for single
names (a covered-call ETF or heavy retail call-buying can flip true positioning), and a
level is where hedging concentrates, never a target.

Why a NEW engine (vs engine/greeks.py + engine/gex_engine.py):
  • engine/greeks.py::bs_greeks takes IV as an INPUT. The EOD path gets IV from the
    Cboe/ThetaData feed. Intraday we hold only the trade tape's per-contract bid/ask, so
    we must SOLVE implied vol from the option mid first (Newton on vega, bounded-bisection
    fallback). That IV solve is the genuinely new piece.
  • The exposure conventions (dealer sign, the GEX/DEX/VEX/CEX formulas, the flip/wall
    definitions) are MIRRORED verbatim from engine/gex_engine.compute_gex (lines that
    compute `gex`/`vex`/`cex`) and engine/gex_model (_net_delta_bn / strike_walls /
    gamma_profile) so intraday and EOD never disagree. We deliberately do NOT re-derive
    them here — the formulas below cite the exact EOD source they clone.
  • Vectorized over the whole cycle's contract set (numpy, no pandas) so a 3-root surface
    cycle stays cheap and this module has no heavy import for CI.

Greek math parity: the closed forms below are the vectorized twins of engine/greeks.py
::bs_greeks (delta, gamma, vanna, charm), which is finite-difference-verified in
tests/test_gex_engine.py. A scalar spot-check test asserts they agree to ~1e-9.

Coverage honesty (CLAUDE.md §Epistemics — honest nulls, no fabrication):
  A greek is computed ONLY for a contract that carries a usable mid quote THIS cycle AND a
  usable prior-day OI. A strike with no such contract contributes 0 to its cell and is
  NOT counted toward coverage. `coverage.greeks` is the fraction of the union strike grid
  that received at least one real contribution — printed, never hidden.

Rate / dividend / multiplier conventions (mirror scripts/build_gex_board.py:151 +
engine/gex_model.DEFAULTS): r=0.043, q=0.0, contract_multiplier=100, pct_move=0.01.
These are the SAME constants the EOD board uses (a fixed short-rate default, not a live
Treasury pull — build_gex_board hardcodes r=0.043).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# ── conventions mirrored from the EOD engine (single source of truth) ───────────────
# engine/gex_model.DEFAULTS + scripts/build_gex_board.py:151 (cfg r/q) — keep in lockstep.
CONTRACT_MULTIPLIER = 100.0
PCT_MOVE = 0.01
DEFAULT_R = 0.043
DEFAULT_Q = 0.0

# IV solver bounds/limits.
IV_LO = 1e-3          # below this BS gamma's 1/sigma factor explodes → treat as no-vol
IV_HI = 5.0           # 500% vol ceiling; a mid implying more is untrustworthy noise
IV_TOL = 1e-6         # price convergence tolerance (option-price units, $)
IV_MAX_NEWTON = 50    # Newton iterations before bisection fallback
IV_MAX_BISECT = 100   # bounded bisection iterations
IV_SEED = 0.30        # initial vol guess (30%)

# Quote-quality guards.
MIN_MID = 0.02        # sub-2¢ mids are unreliable (penny wings) → skip
MIN_EXTRINSIC = 1e-4  # a mid at/below intrinsic value has no time value → IV undefined
MIN_T = 1.0 / (365.0 * 24.0 * 60.0)   # 1 minute in years — floor for T (0DTE late-day)

SQRT2PI = np.sqrt(2.0 * np.pi)


# ── vectorized Black-Scholes (twins of engine/greeks.py::bs_greeks) ─────────────────

def _norm_cdf(x: np.ndarray) -> np.ndarray:
    """Vectorized standard-normal CDF (matches engine/greeks.ncdf via erf)."""
    from scipy.special import erf  # local import; scipy is a repo dep (engine uses it)

    return 0.5 * (1.0 + erf(x / np.sqrt(2.0)))


def _norm_cdf_noscjpy(x: np.ndarray) -> np.ndarray:
    """erf-free normal CDF fallback (Abramowitz-Stegun 7.1.26) if scipy is unavailable.

    Kept so this module never hard-depends on scipy; accuracy ~1e-7 is ample for a
    display heat map. Only used when the scipy import in _norm_cdf raises.
    """
    # A&S 7.1.26 on |x|, then reflect.
    ax = np.abs(x) / np.sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
                - 0.284496736) * t + 0.254829592) * t * np.exp(-ax * ax)
    erf_ax = y
    return 0.5 * (1.0 + np.sign(x) * erf_ax)


def _cdf(x: np.ndarray) -> np.ndarray:
    try:
        return _norm_cdf(x)
    except Exception:  # noqa: BLE001 — scipy missing / any import failure
        return _norm_cdf_noscjpy(x)


def _pdf(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / SQRT2PI


def _d1_d2(S, K, T, sigma, r=DEFAULT_R, q=DEFAULT_Q):
    """(d1, d2, sqrtT) vectorized. S scalar or array-broadcastable; K/T/sigma arrays."""
    sqrtT = np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    return d1, d1 - sigma * sqrtT, sqrtT


def bs_price(S, K, T, sigma, is_call, r=DEFAULT_R, q=DEFAULT_Q):
    """Vectorized Black-Scholes option price (dividend-adjusted).

    Mirrors the pricing implied by engine/greeks._d1d2 conventions. is_call is a bool
    array (True=call). Degenerate inputs propagate as NaN (guarded by callers).
    """
    d1, d2, _ = _d1_d2(S, K, T, sigma, r, q)
    eqT = np.exp(-q * T)
    erT = np.exp(-r * T)
    call = S * eqT * _cdf(d1) - K * erT * _cdf(d2)
    put = K * erT * _cdf(-d2) - S * eqT * _cdf(-d1)
    return np.where(is_call, call, put)


def bs_vega(S, K, T, sigma, r=DEFAULT_R, q=DEFAULT_Q):
    """Vectorized vega dPrice/dSigma (per 1.0 vol, i.e. per 100 vol-points).

    Call/put-identical. Used to drive the Newton IV solve.
    """
    d1, _, sqrtT = _d1_d2(S, K, T, sigma, r, q)
    return S * np.exp(-q * T) * _pdf(d1) * sqrtT


def bs_greeks_vec(S, K, T, sigma, is_call, r=DEFAULT_R, q=DEFAULT_Q):
    """Vectorized (delta, gamma, vanna, charm) — the numpy twin of engine/greeks.bs_greeks.

    charm is per YEAR (= d delta / d calendar-time = −d delta / dT), matching
    engine/greeks.bs_greeks exactly (the aggregator scales charm to per-day, /365, the
    same way engine/gex_engine.compute_gex does). gamma & vanna are call/put-identical;
    delta & charm differ by right. Returns arrays aligned to the inputs.

    Any element with a non-finite / non-positive S,K,T,sigma yields NaN for all four
    greeks (guarded like the scalar version), so callers can mask it out.
    """
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    T = np.asarray(T, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    is_call = np.asarray(is_call, dtype=bool)

    ok = (S > 0) & (K > 0) & (T > 0) & (sigma > 0) & np.isfinite(S) & np.isfinite(K) \
        & np.isfinite(T) & np.isfinite(sigma)
    # Compute on a safe copy (avoid divide-by-zero warnings), then mask.
    Ks = np.where(ok, K, 1.0)
    Ts = np.where(ok, T, 1.0)
    sig = np.where(ok, sigma, 1.0)
    Ss = np.where(ok, S, 1.0) if np.ndim(S) else (S if S > 0 else 1.0)

    d1, d2, sqrtT = _d1_d2(Ss, Ks, Ts, sig, r, q)
    eqT = np.exp(-q * Ts)
    pdf = _pdf(d1)

    gamma = eqT * pdf / (Ss * sig * sqrtT)
    vanna = -eqT * pdf * d2 / sig                       # d delta / d sigma
    common = eqT * pdf * (2.0 * (r - q) * Ts - d2 * sig * sqrtT) / (2.0 * Ts * sig * sqrtT)

    call_delta = eqT * _cdf(d1)
    put_delta = eqT * (_cdf(d1) - 1.0)
    delta = np.where(is_call, call_delta, put_delta)

    call_charm = q * eqT * _cdf(d1) - common
    put_charm = -q * eqT * _cdf(-d1) - common
    charm = np.where(is_call, call_charm, put_charm)

    nan = np.full(np.shape(gamma), np.nan)
    delta = np.where(ok, delta, nan)
    gamma = np.where(ok, gamma, nan)
    vanna = np.where(ok, vanna, nan)
    charm = np.where(ok, charm, nan)
    return delta, gamma, vanna, charm


# ── implied-vol solve from option mid (Newton on vega + bisection fallback) ─────────

def implied_vol_vec(mid, S, K, T, is_call, r=DEFAULT_R, q=DEFAULT_Q):
    """Solve implied vol from an option MID price, vectorized.

    Newton's method seeded at IV_SEED, stepped by (price−mid)/vega, clamped to
    [IV_LO, IV_HI]; any element that fails to converge (vega collapses, or the mid is at
    or below intrinsic value so no positive-vol price matches) falls back to a bounded
    bisection on [IV_LO, IV_HI]. Elements with no bracket (bisection endpoints don't
    straddle the mid) resolve to NaN — an honest "cannot price this quote", never a fake.

    Guards (return NaN, contribute nothing to coverage):
      • sub-MIN_MID mids (penny wings),
      • mids at/below intrinsic value + MIN_EXTRINSIC (no time value → IV undefined),
      • non-positive / non-finite S,K,T.

    Returns an array of IVs (decimal, e.g. 0.18), NaN where unsolved.
    """
    mid = np.asarray(mid, dtype=float)
    S = float(S)
    K = np.asarray(K, dtype=float)
    T = np.asarray(T, dtype=float)
    is_call = np.asarray(is_call, dtype=bool)
    n = mid.shape[0]

    out = np.full(n, np.nan)

    # Intrinsic value (dividend/rate-discounted forward intrinsic is a refinement; plain
    # spot intrinsic is the robust lower bound for "has time value").
    intrinsic = np.where(is_call, np.maximum(S - K, 0.0), np.maximum(K - S, 0.0))

    valid = (
        np.isfinite(mid) & (mid >= MIN_MID)
        & np.isfinite(K) & (K > 0)
        & np.isfinite(T) & (T > 0)
        & (S > 0)
        & (mid > intrinsic + MIN_EXTRINSIC)          # must carry extrinsic value
    )
    if not valid.any():
        return out

    idx = np.where(valid)[0]
    Kv = K[idx]
    Tv = np.maximum(T[idx], MIN_T)
    cv = is_call[idx]
    mv = mid[idx]

    sigma = np.full(idx.shape[0], IV_SEED)
    unconverged = np.ones(idx.shape[0], dtype=bool)

    # ── Newton ──
    for _ in range(IV_MAX_NEWTON):
        if not unconverged.any():
            break
        px = bs_price(S, Kv, Tv, sigma, cv, r, q)
        diff = px - mv
        done = np.abs(diff) < IV_TOL
        unconverged &= ~done
        if not unconverged.any():
            break
        vega = bs_vega(S, Kv, Tv, sigma, r, q)
        # Where vega is too small, Newton is unstable — leave for bisection.
        step_ok = unconverged & (vega > 1e-8)
        sigma = np.where(step_ok, sigma - diff / vega, sigma)
        sigma = np.clip(sigma, IV_LO, IV_HI)

    # Accept Newton solutions that converged.
    conv = ~unconverged
    out[idx[conv]] = sigma[conv]

    # ── bisection fallback for the rest ──
    rem = np.where(unconverged)[0]
    if rem.size:
        Kb = Kv[rem]
        Tb = Tv[rem]
        cb = cv[rem]
        mb = mv[rem]
        lo = np.full(rem.size, IV_LO)
        hi = np.full(rem.size, IV_HI)
        f_lo = bs_price(S, Kb, Tb, lo, cb, r, q) - mb
        f_hi = bs_price(S, Kb, Tb, hi, cb, r, q) - mb
        # Bracketed only where the price is monotone-crossing the mid across [lo,hi].
        bracket = np.isfinite(f_lo) & np.isfinite(f_hi) & (f_lo * f_hi < 0)
        mid_sig = 0.5 * (lo + hi)
        for _ in range(IV_MAX_BISECT):
            mid_sig = 0.5 * (lo + hi)
            f_mid = bs_price(S, Kb, Tb, mid_sig, cb, r, q) - mb
            go_hi = (f_mid * f_lo) > 0            # root is in [mid, hi]
            lo = np.where(go_hi, mid_sig, lo)
            hi = np.where(go_hi, hi, mid_sig)
            f_lo = np.where(go_hi, f_mid, f_lo)
        solved = bracket & (np.abs(hi - lo) < 1e-4)
        out_idx = idx[rem]
        out[out_idx[solved]] = mid_sig[solved]

    return out


# ── put-call-parity spot from the tape (no clean intraday spot exists otherwise) ────

def parity_spot(contracts: list[dict], r=DEFAULT_R, q=DEFAULT_Q) -> float | None:
    """Estimate intraday spot via put-call parity on the cycle's mids, or None.

    The `live_flow` poller has NO clean intraday spot source (it omits the SPY series in
    build_tide_current: "no clean intraday spot source"). Both call and put mids ARE on
    the tape, so parity recovers a live spot from the same quotes that drive the greeks:

        S ≈ (C_mid − P_mid) + K · e^(−(r−q)T)          (q≈0 for these ETFs)

    Computed at the strike whose |C_mid − P_mid| is smallest (the ATM strike, where the
    estimate is least sensitive to a stale leg), for the nearest expiry that has a
    call+put mid pair. Returns None when no paired ATM strike exists this cycle — the
    caller then falls back to prev_close and records spot_source honestly.

    `contracts`: list of {exp_years, strike, right('C'/'P'), mid} dicts.
    """
    # Group paired call/put mids by (exp_years rounded, strike).
    pairs: dict[tuple, dict] = {}
    for c in contracts:
        try:
            T = float(c["exp_years"])
            K = float(c["strike"])
            mid = float(c["mid"])
            right = str(c["right"]).upper()[:1]
        except (TypeError, ValueError, KeyError):
            continue
        if not (T > 0 and K > 0 and np.isfinite(mid) and mid > 0):
            continue
        key = (round(T, 6), K)
        slot = pairs.setdefault(key, {})
        slot[right] = mid

    # Candidate parity estimates from strikes carrying BOTH legs.
    best = None  # (abs(C-P), T, spot)
    for (T, K), legs in pairs.items():
        if "C" not in legs or "P" not in legs:
            continue
        cmid, pmid = legs["C"], legs["P"]
        disc = np.exp(-(r - q) * T)
        spot = (cmid - pmid) + K * disc
        cand = (abs(cmid - pmid), T, float(spot))
        if best is None or (cand[1] < best[1]) or (cand[1] == best[1] and cand[0] < best[0]):
            # Prefer the nearest expiry; within it, the tightest call-put spread (ATM).
            best = cand
    return best[2] if best is not None else None


# ── per-strike dealer exposure aggregation (mirrors gex_engine.compute_gex) ─────────

@dataclass
class GreekGrids:
    """Per-strike dealer-exposure vectors + derived walls, for one root at one stamp.

    strikes : ascending unique strikes present with a usable quote+OI this cycle.
    gex/dex/vex/cex : per-strike net dealer exposure aligned to `strikes` (floats).
    flip / call_wall / put_wall : derived levels (mirror the EOD definitions), or None.
    coverage : fraction of the union strike grid that received a real contribution (0..1).
    spot : the spot used (parity-implied or fallback).
    spot_source : "parity" | "prev_close" | "none".
    n_contracts : number of contracts that contributed a greek this cycle.
    """
    strikes: list[float] = field(default_factory=list)
    gex: list[float] = field(default_factory=list)
    dex: list[float] = field(default_factory=list)
    vex: list[float] = field(default_factory=list)
    cex: list[float] = field(default_factory=list)
    flip: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    coverage: float = 0.0
    spot: float | None = None
    spot_source: str = "none"
    n_contracts: int = 0


def _round_or_none(x, n=6):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if np.isfinite(v) else None


def compute_greek_grids(
    contracts: list[dict],
    *,
    spot: float | None = None,
    spot_fallback: float | None = None,
    r: float = DEFAULT_R,
    q: float = DEFAULT_Q,
    mult: float = CONTRACT_MULTIPLIER,
    pm: float = PCT_MOVE,
    union_strikes: list[float] | None = None,
) -> GreekGrids:
    """Compute per-strike GEX/DEX/VEX/CEX + walls from one cycle's contract quotes.

    contracts: list of per-contract dicts, each:
        {exp_years: float, strike: float, right: 'C'|'P', mid: float, oi: float}
      exp_years = year-fraction to expiry (T); mid = (bid+ask)/2; oi = prior-day OI.

    Exposure formulas — MIRRORED VERBATIM from engine/gex_engine.compute_gex:
        sign  = +1 (call) / −1 (put)                     [dealer long-call / short-put]
        dg    = gamma · oi · mult · S²                   [unsigned $ gamma level]
        GEX   = sign · dg · pm                            [$ per 1% move]        (compute_gex `gex`)
        DEX   = sign · delta · oi · mult · S             [$ delta]              (gex_model._net_delta_bn)
        VEX   = sign · vanna · oi · mult · S · pm         [$ delta / vol-ish]    (compute_gex `vex`)
        CEX   = sign · (charm/365) · oi · mult · S        [$ delta / day]        (compute_gex `cex`)

    Spot: if `spot` is None, parity_spot(contracts) is tried; if that is None too,
    `spot_fallback` (prev_close) is used and spot_source='prev_close'. If neither
    resolves, returns an empty GreekGrids (no fabrication).

    Walls (mirror engine/gex_model.strike_walls + gex_engine._gamma_flip):
        call_wall = strike with the largest POSITIVE net $gamma ABOVE spot,
        put_wall  = strike with the largest |NEGATIVE| net $gamma BELOW spot,
        flip      = the zero-crossing of net-$gamma-by-strike nearest spot (linear interp).

    Coverage: fraction of `union_strikes` (or the strikes seen) that got ≥1 contribution.
    """
    # ── resolve spot ──
    spot_source = "none"
    if spot is not None and np.isfinite(spot) and spot > 0:
        S = float(spot)
        spot_source = "explicit"
    else:
        S = parity_spot(contracts, r=r, q=q)
        if S is not None and S > 0:
            spot_source = "parity"
        elif spot_fallback is not None and np.isfinite(spot_fallback) and spot_fallback > 0:
            S = float(spot_fallback)
            spot_source = "prev_close"
        else:
            return GreekGrids(spot=None, spot_source="none")

    # ── vectorize contracts ──
    Ks, Ts, mids, ois, calls = [], [], [], [], []
    for c in contracts:
        try:
            K = float(c["strike"]); T = float(c["exp_years"])
            mid = float(c["mid"]); oi = float(c.get("oi", 0.0) or 0.0)
            right = str(c["right"]).upper()[:1]
        except (TypeError, ValueError, KeyError):
            continue
        if not (K > 0 and T > 0 and np.isfinite(mid) and mid > 0 and oi > 0):
            continue
        Ks.append(K); Ts.append(T); mids.append(mid); ois.append(oi)
        calls.append(right == "C")

    union = sorted({float(k) for k in (union_strikes or [])}) or None

    if not Ks:
        # No usable contracts; coverage 0 against the union (if any).
        return GreekGrids(spot=_round_or_none(S, 4), spot_source=spot_source,
                          strikes=[], coverage=0.0, n_contracts=0)

    Ks = np.asarray(Ks, float); Ts = np.asarray(Ts, float)
    mids = np.asarray(mids, float); ois = np.asarray(ois, float)
    calls = np.asarray(calls, bool)

    # ── solve IV, compute greeks ──
    iv = implied_vol_vec(mids, S, Ks, Ts, calls, r=r, q=q)
    good = np.isfinite(iv) & (iv >= IV_LO)
    if not good.any():
        return GreekGrids(spot=_round_or_none(S, 4), spot_source=spot_source,
                          strikes=[], coverage=0.0, n_contracts=0)

    Kg = Ks[good]; Tg = Ts[good]; ivg = iv[good]; oig = ois[good]; cg = calls[good]
    delta, gamma, vanna, charm = bs_greeks_vec(S, Kg, Tg, ivg, cg, r=r, q=q)

    sign = np.where(cg, 1.0, -1.0)
    dg = gamma * oig * mult * S * S                     # unsigned $ gamma level
    gex = sign * dg * pm                                # $ per 1% move
    dex = sign * delta * oig * mult * S                 # $ delta
    vex = sign * vanna * oig * mult * S * pm            # $ delta / vol-ish
    cex = sign * (charm / 365.0) * oig * mult * S       # $ delta / day

    # NaNs (degenerate greeks) contribute nothing.
    finite = np.isfinite(gex) & np.isfinite(dex) & np.isfinite(vex) & np.isfinite(cex) \
        & np.isfinite(dg)
    if not finite.any():
        return GreekGrids(spot=_round_or_none(S, 4), spot_source=spot_source,
                          strikes=[], coverage=0.0, n_contracts=0)
    Kg = Kg[finite]; gex = gex[finite]; dex = dex[finite]
    vex = vex[finite]; cex = cex[finite]; dg = dg[finite]

    # ── aggregate per strike ──
    strikes_present = np.unique(Kg)
    # Grid rows aligned to the union of strikes if given, else the strikes present.
    grid_strikes = union if union is not None else [float(k) for k in strikes_present]
    grid_strikes = sorted(set(grid_strikes) | {float(k) for k in strikes_present}) \
        if union is not None else grid_strikes
    row_of = {float(k): i for i, k in enumerate(grid_strikes)}

    n = len(grid_strikes)
    agex = np.zeros(n); adex = np.zeros(n); avex = np.zeros(n); acex = np.zeros(n)
    adg = np.zeros(n)   # net signed $gamma-by-strike for flip/walls (mirrors compute_gex sign·dg)
    contributed = np.zeros(n, dtype=bool)

    # Signed dollar gamma per contract for walls/flip = sign · dg (identical to `gex`/pm,
    # which is exactly compute_gex's `gex` divided back out of the 1%-move scaling).
    signed_dg = gex / pm if pm else gex
    for k, g, d, v, c_, sdg in zip(Kg, gex, dex, vex, cex, signed_dg):
        i = row_of[float(k)]
        agex[i] += g; adex[i] += d; avex[i] += v; acex[i] += c_
        adg[i] += sdg
        contributed[i] = True

    # ── walls + flip (mirror gex_model.strike_walls / gex_engine._gamma_flip) ──
    call_wall = put_wall = flip = None
    ks_arr = np.asarray(grid_strikes, float)
    above = (ks_arr > S) & (adg > 0)
    below = (ks_arr < S) & (adg < 0)
    if above.any():
        call_wall = float(ks_arr[above][np.argmax(adg[above])])
    if below.any():
        put_wall = float(ks_arr[below][np.argmin(adg[below])])
    # Flip: zero-cross of the net signed-$gamma-by-strike profile nearest spot.
    if n >= 2:
        crossings = []
        order = np.argsort(ks_arr)
        ks_s = ks_arr[order]; dg_s = adg[order]
        for i in range(len(ks_s) - 1):
            y0, y1 = dg_s[i], dg_s[i + 1]
            if y0 == 0.0 or (y0 < 0) != (y1 < 0):
                x0, x1 = ks_s[i], ks_s[i + 1]
                x = x0 - y0 * (x1 - x0) / (y1 - y0) if y1 != y0 else x0
                crossings.append(float(x))
        if crossings:
            flip = float(min(crossings, key=lambda x: abs(x - S)))

    # ── coverage: fraction of the grid strikes that received a real contribution ──
    denom = len(grid_strikes) if grid_strikes else 0
    coverage = (float(contributed.sum()) / denom) if denom else 0.0

    return GreekGrids(
        strikes=[float(k) for k in grid_strikes],
        gex=[float(x) for x in agex],
        dex=[float(x) for x in adex],
        vex=[float(x) for x in avex],
        cex=[float(x) for x in acex],
        flip=_round_or_none(flip, 4),
        call_wall=_round_or_none(call_wall, 4),
        put_wall=_round_or_none(put_wall, 4),
        coverage=round(coverage, 4),
        spot=_round_or_none(S, 4),
        spot_source=spot_source,
        n_contracts=int(finite.sum()),
    )
