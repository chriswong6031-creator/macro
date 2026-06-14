"""Pure-function tests for the term-structure carry-context leaf (no network)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import commodity_carry_context as cc  # noqa: E402


def test_historical_pctile_ranks_within_distribution():
    hist = pd.Series(np.linspace(-0.20, 0.20, 1000))   # symmetric around 0
    mid = cc.historical_pctile(0.0, hist)
    assert mid is not None
    assert 45 <= mid["deep_pctile"] <= 55          # ~median
    assert mid["extreme"] is False
    assert mid["deep_years"] >= 3                   # 1000 obs / 252 ≈ 4y
    hi = cc.historical_pctile(0.18, hist)
    assert hi["deep_pctile"] >= 90 and hi["extreme"] is True
    lo = cc.historical_pctile(-0.18, hist)
    assert lo["deep_pctile"] <= 10 and lo["extreme"] is True


def test_historical_pctile_guards():
    assert cc.historical_pctile(None, pd.Series([1, 2, 3])) is None
    assert cc.historical_pctile(0.0, None) is None
    assert cc.historical_pctile(0.0, pd.Series(np.arange(50))) is None   # too short
    # inf/nan are dropped, not crashed on
    s = pd.Series([0.1, np.inf, -np.inf, np.nan] + list(np.linspace(-0.1, 0.1, 300)))
    out = cc.historical_pctile(0.0, s)
    assert out is not None and 0 <= out["deep_pctile"] <= 100


def test_caveat_bilingual_and_honest():
    for k in ("en", "zh"):
        assert k in cc.CARRY_CAVEAT and len(cc.CARRY_CAVEAT[k]) > 20
    # the whole point: carry is NOT a directional buy signal
    assert "≠" in cc.CARRY_CAVEAT["en"]
    assert "mean-reversion" in cc.CARRY_CAVEAT["en"].lower()


def test_eia_history_and_deep_context_degrade_gracefully(monkeypatch):
    # when the cache is absent, both degrade to None (never raise)
    monkeypatch.setattr(cc, "_EIA_CACHE", Path("/nonexistent/eia.parquet"))
    assert cc.eia_roll_yield_history() is None
    assert cc.deep_oil_context(2.6) is None


def test_deep_context_with_real_cache_if_present():
    # if the committed EIA dataset exists, today's roll yield must rank cleanly
    hist = cc.eia_roll_yield_history()
    if hist is None:
        return   # cache not present in this checkout — skip silently
    assert len(hist) > 5000                      # ~38y of daily obs
    ctx = cc.deep_oil_context(2.6)               # +2.6%/yr backwardation
    assert ctx is not None and 0 <= ctx["deep_pctile"] <= 100
    assert ctx["deep_years"] >= 30
