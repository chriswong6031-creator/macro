"""Cross-sectional equity factor engine tests (engine/equity_factors.py).
Pure-function checks on the winsorized z-score so they run without the EDGAR
cache; one integration check that runs only if a real cache exists.
See research/QUANT_FACTOR_EXPANSION.md."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.equity_factors import _winsor_z, compute_factors  # noqa: E402
from lib import config  # noqa: E402


def test_winsor_z_centers_and_clips() -> None:
    # a tight cluster + one far outlier: the outlier's raw z exceeds the cap
    s = pd.Series([float(x) for x in range(50)] + [10000.0])
    z = _winsor_z(s, 3.0)
    assert abs(z.iloc[:50].mean()) < 1.0              # bulk roughly centered
    assert z.max() <= 3.0 and z.min() >= -3.0         # clipped to the cap
    assert z.iloc[-1] == 3.0                           # far outlier pinned at the cap


def test_winsor_z_handles_degenerate() -> None:
    z = _winsor_z(pd.Series([5.0, 5.0, 5.0]), 3.0)     # zero variance
    assert z.isna().all()
    z2 = _winsor_z(pd.Series([np.inf, 1.0, 2.0, 3.0]), 3.0)  # inf scrubbed
    assert np.isfinite(z2.dropna()).all()


def test_compute_factors_shape_if_cache_present() -> None:
    cache = config.data_dir() / "edgar" / "fundamentals.parquet"
    if not cache.exists():
        return  # no live cache in this environment — pure-function tests cover the math
    r = compute_factors()
    assert r is not None
    assert r["n"] > 100
    assert "value" in r["factors"] and "low_vol" in r["factors"]
    # every leaderboard entry is well-formed
    for x in r["composite_top"][:5]:
        assert {"ticker", "name", "sector", "z"} <= set(x)
    # leadership spreads are finite numbers
    for L in r["leadership"]:
        assert isinstance(L["spread_pct"], float)
    # composite is bounded by the winsor cap on each leg (mean of clipped z's)
    cap = config.load()["edgar"]["factors"]["winsor_z"]
    for x in r["composite_top"] + r["composite_bottom"]:
        assert -cap <= x["z"] <= cap
