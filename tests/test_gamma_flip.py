"""Dealer gamma-flip (collectors.deribit._gamma_flip) — synthetic chain, no network.

Verifies the zero-gamma spot finder: the flip lies within the strike range, the
regime label matches the sign of net dealer gamma at spot, and degenerate chains
return None cleanly.

Run: .venv/bin/python -m tests.test_gamma_flip
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from collectors.deribit import _gamma_flip, _bs_delta_gamma  # noqa: E402


def _chain(S, strikes, T=0.08, iv=60.0, call_oi=1.0, put_oi=1.0):
    rows = []
    for K in strikes:
        for is_call, oi in ((True, call_oi), (False, put_oi)):
            _, g = _bs_delta_gamma(S, K, T, iv / 100.0, is_call)
            rows.append({"K": float(K), "T": T, "iv": iv, "is_call": is_call,
                         "oi": float(oi), "gamma": g})
    return pd.DataFrame(rows)


def test_flip_in_range_and_regime_consistent():
    S = 64000.0
    strikes = np.arange(50000, 80001, 2000)
    df = _chain(S, strikes)
    flip, dist, regime = _gamma_flip(df, S)
    assert flip is not None
    assert strikes.min() <= flip <= strikes.max()           # within the strike grid
    assert regime in ("long", "short")
    # distance sign agrees with where spot sits vs flip
    assert (dist >= 0) == (S >= flip)
    # regime agrees with the net-gamma sign at spot (long calls / short puts):
    # call-heavy OI -> positive net gamma near ATM -> long regime
    callheavy = _gamma_flip(_chain(S, strikes, call_oi=5.0, put_oi=1.0), S)
    assert callheavy[2] == "long"


def test_degenerate_returns_none():
    assert _gamma_flip(pd.DataFrame(columns=["K", "T", "iv", "is_call", "oi"]), 64000.0)[0] is None
    # all-zero OI -> not enough usable strikes
    df = _chain(64000.0, [60000, 64000, 68000], call_oi=0.0, put_oi=0.0)
    assert _gamma_flip(df, 64000.0)[0] is None
    assert _gamma_flip(_chain(64000.0, np.arange(50000, 80001, 2000)), 0.0)[0] is None  # bad spot


if __name__ == "__main__":
    for fn in [test_flip_in_range_and_regime_consistent, test_degenerate_returns_none]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all gamma-flip tests passed")
