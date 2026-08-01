"""All-region theme-detail cycle records built from the equal-weight level matrix."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.build_theme_detail import _cycle_from_chart


def test_cycle_from_chart_builds_compact_record():
    idx = pd.bdate_range("2023-01-02", periods=750)
    x = np.arange(len(idx), dtype=float)
    values = 100.0 * np.exp(0.0004 * x + 0.12 * np.sin(x / 45.0))
    chart = {
        "dates": [d.strftime("%Y-%m-%d") for d in idx],
        "baskets": {"gold_miners": values.tolist()},
    }
    rec = _cycle_from_chart(
        chart,
        "gold_miners",
        {"name": "Gold Miners", "name_zh": "黄金矿业"},
    )
    assert rec is not None
    assert len(rec["price"]) > 50
    assert rec["basis"] == "equal_weight_close"
    assert rec["now"]["phase"] in rec["phases"]
    assert rec["xDomain"][1] > rec["today"]
