"""LIMITED-record port for recent A-share listings (heatmap ↔ library coverage gap).

2026-07-12: 46 tickers rendered as fully clickable china_heatmap tiles (built from
the SAME data/china_search panel the library reads) but were absent from
site/chinastockdata/ — build_china_library._one() hard-dropped anything under 300
sessions, so every recent listing's tile click-through landed on a NOT-IN-LIBRARY
dead end (e.g. 301632.SZ @218 bars, 688727.SS @154). The fix ports
build_stock_library's _limited_rec / allow_limited idiom universe-wide: sub-floor
names now emit an honest, searchable LIMITED record (identity + listing date +
chart; china_lookup renders the "analysis pending" card) and NEVER enter
scoring/boards/profiles — display-tier accrual without authority.

Run: .venv/bin/python -m pytest tests/test_china_library_limited.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_view  # noqa: E402
from scripts import build_china_library as bcl  # noqa: E402

_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "china_lookup.html.j2"


def _series(n: int, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.Series(20 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n))), index=idx)


def test_short_history_emits_limited_record():
    c = _series(218)
    rec = bcl._one("301632.SZ", c, None, "Test Co", "Technology", allow_limited=True)
    assert rec is not None and rec["limited"] is True
    assert rec["ladder"] == {"state": "LIMITED"}
    assert rec["ticker"] == "301632.SZ" and rec["tv"] == "SZSE:301632"
    assert rec["history_days"] == 218
    assert rec["listed"] == str(c.index.min().date())
    assert rec["asof"] == str(c.index.max().date())


def test_short_history_without_allow_limited_still_drops():
    # the US-parity default: callers that never opted in keep the old contract
    assert bcl._one("301632.SZ", _series(218), None, "T", "S") is None


def test_empty_series_returns_none_even_with_allow_limited():
    empty = pd.Series([float("nan")] * 10, index=pd.bdate_range("2026-01-01", periods=10))
    assert bcl._one("X.SZ", empty, None, "T", "S", allow_limited=True) is None


def test_full_history_record_unchanged():
    # ≥300 sessions: the full analysis path runs and the record is NOT limited
    rec = bcl._one("601939.SS", _series(400), None, "CCB", "Financial Services",
                   allow_limited=True)
    assert rec is not None and not rec.get("limited")
    assert rec["ladder"].get("state") and rec["ladder"]["state"] != "LIMITED"


def test_fanout_worker_opts_in():
    # the nightly build reaches _one only through _cn_one_task — lock the opt-in there
    bcl._cn_winit(None)
    rec = bcl._cn_one_task(("688727.SS", _series(154), None, "N", "Tech"))
    assert rec is not None and rec.get("limited") is True


def test_limited_rec_survives_build_view():
    # main()'s write loop applies stock_view.build_view to EVERY record, limited included
    rec = bcl._limited_rec("301632.SZ", _series(218), "Test Co", "Technology")
    view = stock_view.build_view(rec, "CN")
    assert isinstance(view, dict) and view.get("schema")


def test_lookup_template_carries_limited_branch():
    # the page must branch on `limited` before ever reading the ladder, and the
    # panels renderLimited hides must exist to hide
    src = _TEMPLATE.read_text()
    assert "renderLimited" in src
    assert "if (d.limited) { renderLimited(d); return; }" in src
    for pid in ('id="panel_deep"', 'id="panel_mtf"', 'id="panel_cal"'):
        assert pid in src, f"missing {pid}"
