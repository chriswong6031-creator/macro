from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.intl_market_confirmation import breadth_snapshot  # noqa: E402


def _rebound_then_fade(end: float, peak: float) -> pd.Series:
    idx = pd.bdate_range("2026-06-26", periods=21)
    values = np.concatenate([
        np.linspace(100.0, peak, 16),
        np.linspace(peak, end, 6)[1:],
    ])
    return pd.Series(values, index=idx)


def test_broad_rebound_and_short_term_fade_are_both_reported():
    peers = {
        "Tech ETF": _rebound_then_fade(115.0, 120.0),
        "Tencent": _rebound_then_fade(118.0, 125.0),
        "Alibaba": _rebound_then_fade(105.0, 110.0),
        "JD.com": _rebound_then_fade(106.0, 108.0),
    }
    out = breadth_snapshot(peers, as_of=pd.Timestamp("2026-07-24"))

    assert out["direction"] == "broad_rebound_fading"
    assert out["windows"]["20d"]["positive"] == 4
    assert out["windows"]["20d"]["available"] == 4
    assert out["windows"]["5d"]["positive"] == 0
    assert "broad rebound" in out["read_en"]
    assert "short-term momentum is fading" in out["read_en"]


def test_stale_peer_is_excluded_instead_of_forward_filled():
    current = _rebound_then_fade(115.0, 120.0)
    stale = current.iloc[:-5]
    out = breadth_snapshot(
        {"Current": current, "Stale": stale},
        as_of=pd.Timestamp("2026-07-24"),
        max_stale_business_days=3,
    )

    assert out["n"] == 1
    assert [row["name"] for row in out["members"]] == ["Current"]


def test_empty_input_fails_open():
    assert breadth_snapshot({}) == {}
