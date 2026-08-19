"""Tests for the macro at-a-glance surfacing — market-snapshot tiles + VIX monitor.

Pure functions over a synthetic feature frame (no network, no real data needed).
"""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

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


# --------------------------------------------------------------------------- #
# vix_monitor() carries CURATED bilingual twins (regime/rword), per the house
# idiom where the producer owns the Chinese and the template renders bare. The
# t() nesting guard (engine/i18n.py) raises on a twin-inside-a-twin, so a
# template that re-wraps one of these fields kills the whole render — this is
# what took engine-render down on 2026-08-19 (td(_vix.regime) at
# macro_signals.html.j2:492). These two tests pin both halves of the contract.
# --------------------------------------------------------------------------- #

def test_vix_monitor_emits_curated_twins_not_plain_slugs():
    """The producer owns the zh — a plain slug here would silently drop Chinese,
    since 'low'/'elevated'/'high fear'/'backwardation'/'contango' are NOT in LEX."""
    from engine.i18n import t

    idx = pd.bdate_range("2024-01-01", periods=40)
    f = pd.DataFrame({"vix": [17.0] * 40, "vix_ratio": [1.1] * 40}, index=idx)
    vm = vix_monitor(f)
    for field, zh in (("regime", "正常"), ("rword", "倒挂")):
        rendered = str(vm[field])
        assert 'class="l-en"' in rendered and 'class="l-zh"' in rendered, field
        assert zh in rendered, f"{field} lost its curated Chinese"
        # ...and re-wrapping that twin is exactly what the guard must reject.
        with pytest.raises(ValueError, match="already contains"):
            t(vm[field])


def test_macro_signals_renders_vix_twins_bare():
    """Regression: no t()/td() wrap around a vix_monitor twin in the template."""
    src = (Path(__file__).resolve().parent.parent
           / "templates" / "macro_signals.html.j2").read_text(encoding="utf-8")
    offenders = re.findall(r"\b(?:t|td)\(\s*_?vix\.(?:regime|rword)\b", src)
    assert not offenders, (
        "macro_signals.html.j2 re-wraps a vix_monitor twin in t()/td(); "
        f"the i18n nesting guard will fail the render: {offenders}"
    )
