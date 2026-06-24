"""Per-basket CROWDING / EXHAUSTION texture — DISPLAY-ONLY, asymmetric (down-size only).

The "is this theme getting late / overcrowded?" read for the Narrative-Rotation page.
A composite of the legs the crowding literature supports, each z-scored vs the basket's
OWN ~3y history (the cross-section of ~15 baskets is far too thin to z-score across):

  comovement   mean pairwise correlation of member RESIDUAL returns (126d), z vs own
               history. Rising co-movement = coordinated theme buying / a crowded trade
               that will unwind together (Lou-Polk "comomentum").
  rs_stretch   how far the basket's relative-strength-vs-SPY line sits in its own
               trailing-year range (percentile → pseudo-z). High = the theme has already
               run a long way (late, by construction the top of a momentum rank).
  extension    median own-history extension z of the LIVE members + the % that are
               'parabolic' (ext_z>=2, engine.extension's validated radioactive per-name
               flag). The fragility TEXTURE of the constituents.

  short_int    basket-mean days-to-cover (latest FINRA snapshot) — CONTEXT ONLY, never in
               the composite (no point-in-time history, cannot be back-tested).

HONESTY (this is the whole point of the module living separate from any score):
  * Phase-0 (scripts/thematic_rotation_phase0.py) finds basket-AGGREGATE extension has
    NO forward-drawdown edge (Spearman ~0.07 on 27y of sectors) — the parabolic→crash
    link is a PER-NAME effect that diversifies away at the basket level. So crowding here
    is TEXTURE, never a basket-timing or drawdown forecast.
  * The composite is used ASYMMETRICALLY: it only ever DOWN-SIZES a held theme (raises the
    bar / trims weight). It NEVER fades, never shorts, never up-sizes at low crowding
    (Sokolovski: crowding doubles crash *probability*; AQR: contrarian crowding-timing is
    "deceptively difficult"). It is never a scoring leg (invariant test).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CROWDED_Z = 1.0           # composite z above this flags 'crowded' (down-size territory)
COMOVE_WIN = 126          # residual co-movement window
RS_PCTILE_WIN = 252       # trailing-year window for the RS-stretch percentile
_UNIFORM_SD = 0.2887      # sd of U(0,1) — maps a percentile to a pseudo-z


def _mean_pairwise_corr(rw: pd.DataFrame) -> float | None:
    """Mean off-diagonal correlation of a member-returns window. Drops all-NaN and
    zero-variance (halted) members first so one constant column can't NaN the matrix."""
    rw = rw.dropna(axis=1, thresh=int(len(rw) * 0.8))
    rw = rw.loc[:, rw.std(numeric_only=True) > 0]
    if rw.shape[1] < 3 or len(rw) < 20:
        return None
    c = rw.corr().to_numpy()
    n = c.shape[0]
    off = (np.nansum(c) - np.trace(c)) / (n * (n - 1))
    return float(off) if np.isfinite(off) else None


def _window_mean_corr(A: np.ndarray, lo: int, hi: int,
                      resid: pd.DataFrame) -> float | None:
    """Mean off-diagonal correlation of A[lo:hi] — a numpy fast path equivalent to
    _mean_pairwise_corr(resid.iloc[lo:hi]). Where the kept members have no internal NaN
    (the common case in a recent window), the mean pairwise correlation is computed in
    O(members) via the standardised-sum identity  1ᵀRλ1 = (1/(w−1))·Σ_t (Σ_i z_{t,i})²
    instead of forming the full O(members²) correlation matrix. The rare window with
    scattered NaNs among kept members falls back to the EXACT pandas pairwise-complete
    path, so the output is identical to the original to floating-point precision."""
    w = hi - lo
    if w < 20:
        return None
    W = A[lo:hi]
    keep = (~np.isnan(W)).sum(axis=0) >= int(w * 0.8)      # == dropna(axis=1, thresh=int(w*0.8))
    if keep.sum() < 3:
        return None
    Wk = W[:, keep]
    with np.errstate(invalid="ignore"):
        sd = np.nanstd(Wk, axis=0, ddof=1)                 # == drop zero-variance members
    nz = sd > 0
    if nz.sum() < 3:
        return None
    Wk = Wk[:, nz]
    if np.isnan(Wk).any():                                 # scattered NaN → exact pairwise fallback
        return _mean_pairwise_corr(resid.iloc[lo:hi])
    n = Wk.shape[1]
    Z = (Wk - Wk.mean(axis=0)) / sd[nz]                    # standardise each kept column
    rs = Z.sum(axis=1)                                     # per-day cross-member sum
    off = (float(rs @ rs) / (w - 1) - n) / (n * (n - 1))   # (1ᵀRλ1 − n) / (n²−n)
    return float(off) if np.isfinite(off) else None


def _comovement_series(resid: pd.DataFrame, win: int = COMOVE_WIN,
                       step: int = 5) -> pd.Series:
    """Rolling mean-pairwise residual correlation, sampled every `step` days (cheap
    enough to z-score the latest value vs the basket's own history).

    Vectorised: the per-window correlation is computed in numpy (see _window_mean_corr)
    rather than rebuilding a pandas correlation matrix per window — this is the engine's
    dominant per-basket cost and is quadratic in member count, so it dominates the wider
    baskets. Output is identical to the prior per-window _mean_pairwise_corr loop."""
    idx = resid.index
    A = resid.to_numpy(dtype=float)
    n = len(idx)
    pts = {}
    for i in range(win, n, step):
        v = _window_mean_corr(A, i - win, i, resid)
        if v is not None:
            pts[idx[i - 1]] = v
    # always include the very last day so the live read is current (matches resid.iloc[-win:])
    last = _window_mean_corr(A, max(0, n - win), n, resid)
    if last is not None:
        pts[idx[-1]] = last
    return pd.Series(pts).sort_index()


def _z_latest(s: pd.Series, minp: int = 12) -> tuple[float | None, float | None]:
    """(latest value, z of latest vs the series' own history). None if too short."""
    s = s.dropna()
    if len(s) < minp:
        return (float(s.iloc[-1]) if len(s) else None), None
    mu, sd = float(s.iloc[:-1].mean()), float(s.iloc[:-1].std())
    cur = float(s.iloc[-1])
    z = (cur - mu) / sd if sd and np.isfinite(sd) and sd > 0 else None
    return cur, (round(z, 2) if z is not None else None)


def _pct_rank_latest(s: pd.Series, win: int) -> float | None:
    s = s.dropna()
    if len(s) < max(40, win // 4):
        return None
    w = s.tail(win)
    return float((w <= w.iloc[-1]).mean())


def basket_crowding(members_resid: pd.DataFrame, rs: pd.Series,
                    ext_rows: list[dict] | None = None,
                    dtc: list[float] | None = None) -> dict:
    """PURE per-basket crowding read from shared data the caller already built:

      members_resid  date×member MARKET-residual returns, NaN-masked off each member's
                     dated [added, removed) window (so it is PIT-consistent).
      rs             basket EW level / SPY bench level (the relative-strength line).
      ext_rows       engine.extension.extension_signals() rows for the LIVE members
                     (each has ext_z / grade / near_52wh).
      dtc            days-to-cover for the live members (latest snapshot; context only).

    Returns {crowding_z, crowded, legs:{...}, extension:{...}} — DISPLAY-ONLY, asymmetric.
    """
    legs: dict[str, dict] = {}
    leg_z: list[float] = []

    # 1) residual co-movement (comomentum), z vs own history
    if members_resid is not None and members_resid.shape[1] >= 3:
        cs = _comovement_series(members_resid)
        cur, z = _z_latest(cs)
        if cur is not None:
            legs["comovement"] = {"value": round(cur, 3), "z": z,
                                  "label": "Member co-movement (residual)"}
            if z is not None:
                leg_z.append(z)

    # 2) relative-strength stretch — percentile of the RS line in its own trailing year
    if rs is not None and rs.dropna().shape[0] >= 60:
        pct = _pct_rank_latest(rs, RS_PCTILE_WIN)
        if pct is not None:
            z = round((pct - 0.5) / _UNIFORM_SD, 2)        # percentile → pseudo-z
            legs["rs_stretch"] = {"value": round(pct, 2), "z": z,
                                  "label": "Relative-strength stretch (vs own year)"}
            leg_z.append(z)

    # 3) extension texture — median own-history ext_z of live members + % parabolic
    ext = {}
    if ext_rows:
        ezs = [r["ext_z"] for r in ext_rows if r.get("ext_z") is not None]
        if len(ezs) >= 3:
            med = float(np.median(ezs))
            pct_parab = 100.0 * sum(1 for r in ext_rows
                                    if r.get("grade") == "parabolic") / len(ext_rows)
            pct_stretch = 100.0 * sum(1 for r in ext_rows
                                      if r.get("grade") in ("stretched", "parabolic")) / len(ext_rows)
            ext = {"median_ext_z": round(med, 2), "pct_parabolic": round(pct_parab),
                   "pct_stretched": round(pct_stretch), "n": len(ext_rows)}
            legs["extension"] = {"value": round(med, 2), "z": round(med, 2),
                                 "label": "Constituent extension (own-history)"}
            leg_z.append(med)                              # already a z

    # 4) short interest — CONTEXT ONLY, never in the composite (no PIT history)
    if dtc:
        d = [x for x in dtc if x is not None and np.isfinite(x)]
        if d:
            ext["avg_days_to_cover"] = round(float(np.mean(d)), 1)

    crowding_z = round(float(np.mean(leg_z)), 2) if leg_z else None
    return {
        "crowding_z": crowding_z,
        "crowded": bool(crowding_z is not None and crowding_z >= CROWDED_Z),
        "n_legs": len(leg_z),
        "legs": legs,
        "extension": ext,
        "directional": False,            # verdict: display_only, asymmetric down-size
        "use": "size_down_only",
    }
