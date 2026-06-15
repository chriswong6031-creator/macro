"""Tests for the macro at-a-glance surfacing — market-snapshot tiles + VIX monitor.

Pure functions over a synthetic feature frame (no network, no real data needed).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_site import market_tiles, vix_monitor  # noqa: E402


def _by_level(f):
    return {t["level"]: t for t in market_tiles(f)}


def test_tiles_raw_sign_and_rate_format():
    idx = pd.bdate_range("2024-01-01", periods=4)
    f = pd.DataFrame({
        "SPY": [100, 100, 100, 101.0],     # up   -> pos
        "QQQ": [50, 50, 50, 49.0],         # down -> neg
        "vix": [20, 20, 20, 18.0],         # down -> neg (coloured by raw sign)
        "us10y": [4.0, 4.0, 4.0, 4.0],     # flat -> muted, with a % suffix
        "oil": [80, 80, 80, 78.0],         # down -> neg
    }, index=idx)
    t = _by_level(f)
    assert t["101.00"]["tone"] == "pos"
    assert t["49.00"]["tone"] == "neg"
    assert t["18.00"]["tone"] == "neg"
    assert t["78.00"]["tone"] == "neg"
    assert "4.00%" in t and t["4.00%"]["tone"] == "muted"


def test_tiles_skip_short_series():
    idx = pd.bdate_range("2024-01-01", periods=4)
    f = pd.DataFrame({"SPY": [1, 2, 3, 4.0], "vix": [None, None, None, 20.0]}, index=idx)
    assert len(market_tiles(f)) == 1            # vix has <2 points -> dropped


def test_vix_monitor_regime_bands():
    idx = pd.bdate_range("2024-01-01", periods=40)

    def regime(level):
        f = pd.DataFrame({"vix": [level] * 40, "vix_ratio": [0.9] * 40}, index=idx)
        return str(vix_monitor(f)["regime"])

    assert "low" in regime(12)
    assert "normal" in regime(17)
    assert "elevated" in regime(25)
    assert "high fear" in regime(35)


def test_vix_monitor_term_structure_and_fields():
    idx = pd.bdate_range("2024-01-01", periods=40)
    f = pd.DataFrame({"vix": list(range(10, 50)), "vix_ratio": [1.1] * 40}, index=idx)
    vm = vix_monitor(f)
    assert "backwardation" in str(vm["rword"])
    assert 0.0 <= vm["pctile"] <= 100.0
    assert vm["last"] == 49 and vm["prev"] == 48
    assert vm["hi"] == 49 and vm["lo"] == 20   # 30-day window = last 30 of 40 (starts at 20)


def test_vix_monitor_none_without_vix():
    f = pd.DataFrame({"SPY": [1.0, 2.0]}, index=pd.bdate_range("2024-01-01", periods=2))
    assert vix_monitor(f) is None
