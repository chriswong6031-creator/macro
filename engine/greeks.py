"""Black-Scholes greeks (dividend-adjusted) shared by the options engines.

Factored out so the crypto (Deribit) and equity/index (Cboe GEX) layers share ONE
finite-difference-verified implementation (see tests/test_gex_engine.py). Greeks are
per-contract, per-unit-underlying; charm is returned per YEAR (the aggregator scales
to per-day). r, q default to 0 (the crypto convention used by collectors/deribit.py);
the equity GEX engine passes a short rate + dividend yield. `sigma` (iv) is a DECIMAL
(0.15, not 15).
"""
from __future__ import annotations

import math

SQRT2 = math.sqrt(2.0)
SQRT2PI = math.sqrt(2.0 * math.pi)


def ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def npdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT2PI


def _d1d2(S, K, T, sigma, r, q):
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    return d1, d1 - sigma * sqrtT, sqrtT


def bs_greeks(S, K, T, sigma, is_call, r=0.0, q=0.0):
    """(delta, gamma, vanna, charm). charm is per YEAR (= d delta / d calendar-time
    = -d delta / dT). gamma & vanna are call/put-identical; delta & charm differ by
    type. Returns NaNs on degenerate inputs (non-positive S/K/T/sigma)."""
    if not (S > 0 and K > 0 and T > 0 and sigma > 0):
        nan = float("nan")
        return nan, nan, nan, nan
    d1, d2, sqrtT = _d1d2(S, K, T, sigma, r, q)
    eqT = math.exp(-q * T)
    pdf = npdf(d1)
    gamma = eqT * pdf / (S * sigma * sqrtT)
    vanna = -eqT * pdf * d2 / sigma                      # d delta / d sigma
    # charm = d delta / d t (calendar) = -d delta / dT
    common = eqT * pdf * (2.0 * (r - q) * T - d2 * sigma * sqrtT) / (2.0 * T * sigma * sqrtT)
    if is_call:
        delta = eqT * ncdf(d1)
        charm = q * eqT * ncdf(d1) - common
    else:
        delta = eqT * (ncdf(d1) - 1.0)
        charm = -q * eqT * ncdf(-d1) - common
    return delta, gamma, vanna, charm
