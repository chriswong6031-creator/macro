"""Dealer dollar-exposure per contract — ONE formula, every consumer.

Why this module exists
----------------------
On 2026-08-01 a live defect shipped for months because two code paths computed
"the gamma flip" differently and both claimed to be the same object
(``docs/audits/2026-08-01-market-structure-core/gamma-flip-defect-rca.md`` in the
charting-app repo). The lesson generalises: whenever the same quantity is derived
in two places, they drift, and the drift is invisible because both look plausible.

Dealer $ exposure is the most-reused quantity in the options estate — the GEX
ladder, the VEX board, the hub payload, the Terminal's Positioning tab and now the
aggregate-greek history all need it. This module is the single definition. Callers
pass raw per-contract greeks and open interest; they get dollars back.

Units — read before changing anything
-------------------------------------
ThetaData EOD greeks are per-share, in the conventions below. Every formula here
was verified against ``engine/options_hub.compute_gex`` (which now delegates to it)
and against ``engine/gex_engine``:

============  =============================  ==============================
greek         feed convention                exposure returned
============  =============================  ==============================
``gamma``     ∂delta/∂S per $1 of spot       $ of dealer delta per **+1% spot**
``delta``     shares per share               $ of dealer delta (level)
``vanna``     ∂delta/∂σ per 1.00 vol         $ of dealer delta per **+1 vol point**
``charm``     ∂delta/∂t per **year**         $ of dealer delta per **+1 calendar day**
``vega``      ∂price/∂σ per 1.00 vol         $ of dealer value per **+1 vol point**
``theta``     ∂price/∂t per **day**          $ of dealer value per **+1 day**
============  =============================  ==============================

``vega`` and ``theta`` are already in option-price (i.e. dollar-per-share) space,
so they are NOT multiplied by spot. ``gamma``/``vanna``/``charm`` are in delta
(share) space and are, which is the single easiest thing to get wrong here.

Sign convention: dealers are assumed **long calls, short puts** — the house
convention set by ``engine/gex_model``. Positive gamma exposure therefore means a
dealer sells into strength and buys weakness (stabilising); negative means the
reverse. This is an assumption about the market, not a measurement of it; the
Terminal labels anything built on it Tier B per the Market Structure Core
honesty tiering.
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "MULT",
    "PCT_MOVE",
    "VOL_POINT",
    "DAYS_PER_YEAR",
    "MIN_QUOTED_IV",
    "EXPOSURE_UNITS",
    "dealer_exposures",
    "usable_quote",
]

#: Contract multiplier — shares per option contract.
MULT = 100.0

#: One percent of spot, as a fraction. Gamma exposure is quoted per +1% move.
PCT_MOVE = 0.01

#: One volatility point, as a fraction of the 1.00-vol feed convention.
VOL_POINT = 0.01

#: Charm arrives per year; hedging is a daily activity.
DAYS_PER_YEAR = 365.0

#: Below this implied vol a quote is a solver artifact, not a market price.
#:
#: ⚠️ This constant exists because of a measured live defect. On 2026-06-26 the
#: published SPY headline was **net gamma −$1,129bn** — negative $1.1 trillion per
#: 1% move. The whole figure came from ONE contract: the 729 put expiring that
#: session, with spot at 728.99 (dead at-the-money, T→0) and a feed implied vol of
#: **0.0001**. Black-Scholes gamma diverges as σ√T → 0, so the feed reported
#: gamma 198.17 on a $729 underlying. Arithmetically faithful; financially
#: meaningless — an option minutes from expiry imposes no hedging requirement of
#: $1.1tn on anybody.
#:
#: Measured effect of this filter across SPY 2017→2026: it changes nothing on
#: normal sessions (2026-07-30 −8.102 both ways, 2026-07-29 −18.791 both ways) and
#: repairs 21 contaminated sessions of 2,407. On two of them it also flips the
#: SIGN — 2024-03-13 published −104.8bn where the real book was +8.4bn, i.e. the
#: wrong dealer regime, not merely the wrong magnitude.
#:
#: The value matches the ``_MIN_IV`` floor ``options_hub.compute_gex`` already used
#: to decide when to substitute a Black-Scholes gamma for a missing one. The bug
#: was that the floor gated the *fallback* but never the *feed value*, so a
#: degenerate quote passed straight through to the sum.
MIN_QUOTED_IV = 0.005

#: Human-readable per-unit disclosure, keyed by greek. The Terminal renders these
#: verbatim next to every number so "1.4bn" is never shown without its "per what".
EXPOSURE_UNITS = {
    "gamma": "per +1% spot",
    "delta": "level",
    "vanna": "per +1 vol point",
    "charm": "per +1 day",
    "vega": "per +1 vol point",
    "theta": "per +1 day",
}


def usable_quote(iv, oi=None) -> np.ndarray:
    """Mask of contracts whose greeks describe a real hedging requirement.

    Drops rows whose implied vol is missing or below :data:`MIN_QUOTED_IV` — see
    that constant for the live defect this prevents — and, when ``oi`` is given,
    rows with no open interest (nobody holds them, so nobody hedges them).

    Deliberately does NOT filter by expiry or strike. Excluding 0DTE or capping
    the strike window are *product* decisions that change what the number means on
    every ordinary session; this is a data-quality gate that changes only the
    sessions that were already wrong.
    """
    iv_a = np.asarray(iv, dtype=float)
    ok = np.isfinite(iv_a) & (iv_a >= MIN_QUOTED_IV)
    if oi is not None:
        oi_a = np.asarray(oi, dtype=float)
        ok &= np.isfinite(oi_a) & (oi_a > 0)
    return ok


def dealer_exposures(
    *,
    is_call,
    oi,
    spot,
    gamma=None,
    delta=None,
    vanna=None,
    charm=None,
    vega=None,
    theta=None,
) -> dict[str, np.ndarray]:
    """Per-contract dealer dollar exposure for every greek supplied.

    Parameters
    ----------
    is_call : array-like of bool
        True for calls. Drives the long-call/short-put dealer sign.
    oi : array-like of float
        Open interest, contracts. Per the OI timing law this is OI[t-1].
    spot : float or array-like of float
        Underlying price. Pass a scalar for a single-session frame, or an array
        aligned to the other inputs when the frame spans multiple sessions —
        each row must be priced at ITS OWN session's spot, never today's.
    gamma, delta, vanna, charm, vega, theta : array-like of float, optional
        Raw per-share greeks. Any subset may be given; only those supplied appear
        in the result. Non-finite values propagate as NaN rather than being
        silently zeroed — the caller decides whether to drop or impute.

    Returns
    -------
    dict[str, numpy.ndarray]
        Dollar exposures keyed by greek name, in the units documented in
        :data:`EXPOSURE_UNITS`. Dollars, not millions — scaling is presentation.
    """
    sign = np.where(np.asarray(is_call, dtype=bool), 1.0, -1.0)
    oi_a = np.asarray(oi, dtype=float)
    spot_a = np.asarray(spot, dtype=float)
    base = sign * oi_a * MULT

    out: dict[str, np.ndarray] = {}
    if gamma is not None:
        # ∂delta/∂S × S² × 1% → $ of delta the dealer must trade per +1% move.
        out["gamma"] = base * np.asarray(gamma, dtype=float) * spot_a**2 * PCT_MOVE
    if delta is not None:
        out["delta"] = base * np.asarray(delta, dtype=float) * spot_a
    if vanna is not None:
        out["vanna"] = base * np.asarray(vanna, dtype=float) * spot_a * VOL_POINT
    if charm is not None:
        out["charm"] = base * (np.asarray(charm, dtype=float) / DAYS_PER_YEAR) * spot_a
    if vega is not None:
        # Already price-space: no spot factor. Multiplying by spot here is the
        # classic unit bug — it would inflate vega exposure ~700× on SPY.
        out["vega"] = base * np.asarray(vega, dtype=float) * VOL_POINT
    if theta is not None:
        out["theta"] = base * np.asarray(theta, dtype=float)
    return out
