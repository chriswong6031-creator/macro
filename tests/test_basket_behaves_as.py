"""RC-R7 dual-membership behaves-as (engine/basket_behaves_as.py).

Network-free: monkeypatch the OHLCV loader so sector_legs._ew_close builds ex-name
composites from synthetic series. NAME is constructed to track basket B's other members
(high return correlation) and NOT basket A's, so behaves_as must resolve to B and flag the
conflict when A and B carry opposite reads.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import basket_behaves_as as bba


@pytest.fixture
def synthetic(monkeypatch):
    """NAME co-moves with the B-cohort (bx1,bx2,bx3) and is ~independent of the A-cohort
    (ax1,ax2,ax3). All series share one calendar."""
    idx = pd.bdate_range("2024-01-02", periods=200)
    rng = np.random.default_rng(42)
    b_factor = rng.normal(0, 0.01, 200)          # the cohort NAME tracks
    a_factor = rng.normal(0, 0.01, 200)          # an unrelated cohort
    noise = lambda: rng.normal(0, 0.003, 200)

    def _lvl(rets):
        return pd.Series(100 * np.cumprod(1 + rets), index=idx)

    series = {
        "NAME": _lvl(b_factor + noise()),         # tracks B
        "bx1": _lvl(b_factor + noise()), "bx2": _lvl(b_factor + noise()),
        "bx3": _lvl(b_factor + noise()), "bx4": _lvl(b_factor + noise()),
        "ax1": _lvl(a_factor + noise()), "ax2": _lvl(a_factor + noise()),
        "ax3": _lvl(a_factor + noise()), "ax4": _lvl(a_factor + noise()),
    }

    def fake_load(ticker):
        s = series.get(ticker)
        return pd.DataFrame({"close": s}) if s is not None else None

    monkeypatch.setattr(bba.basket_index, "_load_member_ohlcv", fake_load)
    monkeypatch.setattr(bba.sector_legs.basket_index, "_load_member_ohlcv", fake_load)
    return series


def _baskets(a_read, b_read):
    """A = home 'basket_a' (members ax*), B = home 'basket_b' (members bx*); NAME in both."""
    a_members = [{"ticker": t} for t in ("NAME", "ax1", "ax2", "ax3", "ax4")]
    b_members = [{"ticker": t} for t in ("NAME", "bx1", "bx2", "bx3", "bx4")]
    return [
        {"basket_id": "basket_a", "label": "Alpha", "label_zh": "阿尔法",
         "class": a_read[0], "regime": {"side": a_read[1]}, "members": a_members},
        {"basket_id": "basket_b", "label": "Beta", "label_zh": "贝塔",
         "class": b_read[0], "regime": {"side": b_read[1]}, "members": b_members},
    ]


def _membership():
    return {"basket_a": {"members": [{"ticker": t} for t in ("NAME", "ax1", "ax2", "ax3", "ax4")]},
            "basket_b": {"members": [{"ticker": t} for t in ("NAME", "bx1", "bx2", "bx3", "bx4")]}}


def test_behaves_as_resolves_to_the_tracked_home(synthetic):
    baskets = _baskets(("late", "avoid"), ("tailwind", "buy"))
    summary = bba.annotate(baskets, _membership())
    assert summary["n_dual"] == 1 and summary["n_annotated"] == 1
    nm = next(m for m in baskets[0]["members"] if m["ticker"] == "NAME")
    ba = nm["behaves_as"]
    assert ba["home_id"] == "basket_b"           # NAME tracks the B cohort
    corr_b = next(h["corr20"] for h in ba["homes"] if h["id"] == "basket_b")
    corr_a = next(h["corr20"] for h in ba["homes"] if h["id"] == "basket_a")
    assert corr_b > corr_a
    assert corr_b > 0.5 and corr_a < 0.5


def test_conflict_flag_true_when_homes_disagree(synthetic):
    baskets = _baskets(("headwind", "avoid"), ("tailwind", "buy"))
    bba.annotate(baskets, _membership())
    nm = next(m for m in baskets[0]["members"] if m["ticker"] == "NAME")
    assert nm["behaves_as"]["conflict"] is True
    # stamped on BOTH home cards
    nm_b = next(m for m in baskets[1]["members"] if m["ticker"] == "NAME")
    assert nm_b["behaves_as"]["home_id"] == "basket_b"


def test_conflict_flag_false_when_homes_agree(synthetic):
    baskets = _baskets(("tailwind", "buy"), ("entry_now", "buy"))
    bba.annotate(baskets, _membership())
    nm = next(m for m in baskets[0]["members"] if m["ticker"] == "NAME")
    assert nm["behaves_as"]["conflict"] is False   # both constructive → no conflict


def test_single_membership_names_untouched(synthetic):
    # NAME only in basket_a → not a dual-member → no behaves_as stamped
    baskets = [{"basket_id": "basket_a", "label": "Alpha", "class": "late",
                "regime": {"side": "avoid"},
                "members": [{"ticker": t} for t in ("NAME", "ax1", "ax2", "ax3")]}]
    summary = bba.annotate(baskets, {"basket_a": {"members": [{"ticker": t} for t in ("NAME", "ax1", "ax2", "ax3")]}})
    assert summary["n_annotated"] == 0
    assert "behaves_as" not in baskets[0]["members"][0]


def test_thin_history_name_dropped(synthetic, monkeypatch):
    # a name with <21 bars can't state a corr → skipped, never raises
    short = pd.DataFrame({"close": pd.Series(range(10), index=pd.bdate_range("2024-01-02", periods=10), dtype=float)})
    orig = bba.basket_index._load_member_ohlcv
    monkeypatch.setattr(bba.basket_index, "_load_member_ohlcv",
                        lambda t: short if t == "NAME" else orig(t))
    baskets = _baskets(("late", "avoid"), ("tailwind", "buy"))
    summary = bba.annotate(baskets, _membership())
    assert summary["n_annotated"] == 0
