"""Pure-function tests for the physical-balance context leaf (no network).

Covers the seasonal-anomaly z (the calendar-confound fix), days-of-supply, the
composite balance gauge, and — critically — the invariant that this display leaf is
never wired into the commodity scoring path.
"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import commodity_supply_context as sc  # noqa: E402


def _seasonal_weekly(years=7, amp=50.0, base=1000.0, noise_sd=4.0, seed=0):
    """A weekly series with a strong 52-week seasonal cycle + idiosyncratic noise."""
    idx = pd.date_range("2017-01-08", periods=years * 52, freq="W-SUN")
    week = idx.isocalendar().week.to_numpy().astype(float)
    season = amp * np.sin(2 * np.pi * week / 52.0)
    rng = np.random.default_rng(seed)
    return pd.Series(base + season + rng.normal(0, noise_sd, len(idx)), index=idx)


def _at_trough(s):
    """Slice the series to end at the deepest seasonal trough within the last year."""
    season_like = s.rolling(5, center=True, min_periods=1).mean()   # smooth out noise
    asof = season_like.iloc[-52:].idxmin()
    return s.loc[:asof].copy()


def test_seasonal_z_beats_raw_at_a_seasonal_extreme():
    """The whole point: a value sitting ON its seasonal norm at a seasonal LOW reads
    deeply negative on a RAW z (calendar artifact) but ~flat on the seasonal z."""
    s = _at_trough(_seasonal_weekly())
    w = int(s.index[-1].isocalendar().week)
    same_week = s[s.index.isocalendar().week.to_numpy() == w]
    s.iloc[-1] = float(same_week.iloc[:-1].mean())          # force latest onto its week-norm

    raw_z = (s.iloc[-1] - s.mean()) / s.std()
    seas_z = sc.seasonal_z(s)
    assert seas_z is not None
    assert raw_z < -1.0                                      # raw is fooled by the season
    assert abs(seas_z) + 0.5 < abs(raw_z)                   # seasonal anomaly is materially flatter


def test_seasonal_z_flags_a_genuine_draw():
    """A true below-season draw (4σ under the week-norm) reads strongly negative."""
    s = _at_trough(_seasonal_weekly())
    w = int(s.index[-1].isocalendar().week)
    same_week = s[s.index.isocalendar().week.to_numpy() == w]
    s.iloc[-1] = float(same_week.iloc[:-1].mean()) - 4 * 4.0   # 4 * noise_sd below norm
    z = sc.seasonal_z(s)
    assert z is not None and z < -2.5                          # tight


def test_seasonal_z_guards():
    assert sc.seasonal_z(None) is None
    assert sc.seasonal_z(_seasonal_weekly(years=1)) is None        # < 104 weeks
    flat = pd.Series(500.0, index=pd.date_range("2019-01-06", periods=300, freq="W-SUN"))
    assert sc.seasonal_z(flat) is None                              # zero dispersion
    # inf/nan are cleaned, not crashed on
    s = _seasonal_weekly()
    s.iloc[-3:] = [np.inf, np.nan, s.iloc[-1]]
    assert sc.seasonal_z(s) is not None


def test_last_value_is_nan_safe():
    s = pd.Series([1.0, 2.0, np.nan], index=pd.date_range("2020-01-05", periods=3, freq="W"))
    assert sc.last_value(s) == 2.0                                  # trailing NaN dropped
    assert sc.last_value(None) is None
    assert sc.last_value(pd.Series([np.nan, np.nan])) is None


def test_delta_4w():
    idx = pd.date_range("2020-01-05", periods=6, freq="W")
    s = pd.Series([100, 101, 102, 103, 104, 110], index=idx, dtype=float)
    assert sc.delta_4w(s) == 110 - 101                             # latest minus value ~4 weeks (4 intervals) back
    assert sc.delta_4w(None) is None


def test_days_of_supply():
    idx = pd.date_range("2020-01-05", periods=8, freq="W")
    stocks = pd.Series(280_000.0, index=idx)                       # kbbl
    demand = pd.Series(16_000.0, index=idx)                        # kbbl/d
    assert sc.days_of_supply(stocks, demand) == 17.5              # 280000 / 16000
    assert sc.days_of_supply(stocks, None) is None
    assert sc.days_of_supply(stocks, pd.Series(0.0, index=idx)) is None   # non-positive demand


def test_balance_z_and_word():
    assert sc.balance_z({"a": -1.0, "b": -2.0, "c": None}) == -1.5    # None skipped
    assert sc.balance_z({"a": None}) is None
    assert sc.balance_word(-0.8) == "tight"
    assert sc.balance_word(0.9) == "ample"
    assert sc.balance_word(0.1) == "balanced"
    assert sc.balance_word(None) == "n/a"


def test_caveat_is_bilingual_and_non_directional():
    for k in ("en", "zh"):
        assert k in sc.SUPPLY_CAVEAT and len(sc.SUPPLY_CAVEAT[k]) > 20
    assert "≠" in sc.SUPPLY_CAVEAT["en"]                            # balance ≠ direction


def test_leaf_is_never_wired_into_the_scoring_path():
    """Guardrail: physical balance is DISPLAY-ONLY. The commodity scoring/alert modules
    must not import or reference this leaf, and the leaf must not import them."""
    from engine import (commodity_conviction, commodity_alerts,
                         commodity_signals, commodity_mtf)
    for mod in (commodity_conviction, commodity_alerts, commodity_signals, commodity_mtf):
        src = inspect.getsource(mod)
        assert "commodity_supply_context" not in src, f"{mod.__name__} references the display leaf"
    # the leaf must not IMPORT the scoring path (docstrings may mention it for context)
    import_lines = "\n".join(ln for ln in inspect.getsource(sc).splitlines()
                             if ln.strip().startswith(("import ", "from ")))
    for forbidden in ("conviction", "commodity_alerts", "commodity_signals", "commodity_mtf"):
        assert forbidden not in import_lines, f"leaf must not import the scoring path ({forbidden})"
