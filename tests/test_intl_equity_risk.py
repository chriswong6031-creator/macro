"""International equity-risk tests (engine/intl_equity_risk.py) — DISPLAY-ONLY
drawdown-risk gauge + own-history extension grade, injected synthetic indices."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intl_equity_risk as er  # noqa: E402


def _matrix(n: int = 500) -> pd.DataFrame:
    idx = pd.bdate_range("2014-01-01", periods=n)
    rng = np.random.default_rng(7)
    # AA: steady uptrend near highs; BB: deep drawdown / below trend
    aa = 100 * np.cumprod(1 + rng.normal(0.0006, 0.008, n))
    bb = 100 * np.cumprod(1 + rng.normal(0.0006, 0.012, n))
    bb[-60:] = bb[-60] * np.linspace(1.0, 0.72, 60)        # -28% recent drawdown
    return pd.DataFrame({"AA": aa, "BB": bb}, index=idx)


def test_bands_and_bounds():
    out = er.equity_risk_all(_matrix())
    assert set(out) == {"AA", "BB"}
    for cc, r in out.items():
        assert 0 <= r["drawdown_risk"] <= 100
        assert r["drawdown_band"] in {"low", "watch", "elevated", "n/a"}
        assert r["ext_grade"] in {"intrend", "steady", "stretched", "parabolic", "na"}
        assert isinstance(r["bubble_flag"], bool)


def test_drawdown_market_scores_higher():
    out = er.equity_risk_all(_matrix())
    assert out["BB"]["drawdown_risk"] > out["AA"]["drawdown_risk"]
    assert out["BB"]["off_52w_high"] < out["AA"]["off_52w_high"]


def test_empty_matrix():
    assert er.equity_risk_all(pd.DataFrame()) == {}


def test_band_helper():
    assert er._band(None) == "n/a"
    assert er._band(10) == "low"
    assert er._band(45) == "watch"
    assert er._band(80) == "elevated"
