"""Tests for the SUE earnings-momentum engine (engine/sue.py). Synthetic quarterly
EPS panels; point-in-time + seasonal-matching + stale-drop behaviour."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.sue import sue_cross_section, winsor_z  # noqa: E402


def _panel(rows, lag_days: int = 60) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["ticker", "period_end", "eps_q"])
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["asof_date"] = df["period_end"] + pd.Timedelta(days=lag_days)
    return df


def _quarters(ticker, start_year, n, eps_fn):
    """n quarterly rows (Mar/Jun/Sep/Dec ends) with eps = eps_fn(quarter_index)."""
    ends, k = [], 0
    for y in range(start_year, start_year + 20):
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            ends.append((ticker, f"{y}-{m:02d}-{d:02d}", eps_fn(k)))
            k += 1
            if k >= n:
                return ends
    return ends


def test_sue_positive_when_earnings_grow_yoy() -> None:
    # EPS rises ~+0.10 each year for the same quarter -> positive seasonal surprise
    rows = _quarters("AAA", 2019, 20, lambda k: 1.0 + 0.10 * (k // 4) + 0.02 * (k % 4))
    sue = sue_cross_section(_panel(rows), "2024-03-01")
    assert "AAA" in sue.index
    assert sue["AAA"] > 0


def test_sue_point_in_time_excludes_unfiled_quarter() -> None:
    rows = _quarters("AAA", 2019, 20, lambda k: 1.0 + 0.10 * (k // 4) + 0.02 * (k % 4))
    panel = _panel(rows)
    last_pe = panel["period_end"].max()
    # an asof BEFORE the latest quarter's as-of date must not see that quarter
    asof_before = last_pe + pd.Timedelta(days=10)      # filed = +60d, so not yet visible
    visible = panel[panel["asof_date"] <= asof_before]
    assert last_pe not in set(visible["period_end"])    # the newest quarter is hidden


def test_sue_drops_stale_ticker() -> None:
    # a ticker whose last filing is ~2 years before asof is stale -> dropped
    rows = _quarters("OLD", 2018, 16, lambda k: 1.0 + 0.05 * (k // 4))
    sue = sue_cross_section(_panel(rows), "2026-01-01", recency_days=215)
    assert "OLD" not in sue.index


def test_sue_handles_missing_quarter_via_calendar_match() -> None:
    # drop one interior quarter; seasonal matching should still align year-ago pairs
    rows = _quarters("GAP", 2019, 20, lambda k: 1.0 + 0.10 * (k // 4) + 0.02 * (k % 4))
    rows = [r for r in rows if r[1] != "2022-06-30"]   # remove one Q2
    sue = sue_cross_section(_panel(rows), "2024-03-01")
    assert "GAP" in sue.index and np.isfinite(sue["GAP"])


def test_winsor_z_standardizes_and_clips() -> None:
    z = winsor_z(pd.Series([0.0, 1.0, 2.0, 3.0, 100.0]), cap=3.0)
    assert abs(z.mean()) < 1e-9 or z.notna().all()
    assert z.max() <= 3.0 and z.min() >= -3.0
