"""LIMITED-record port for recent TSX listings (heatmap -> canada_stock dead end gap).

build_canada_library._one() hard-dropped anything under 300 sessions
(scripts/build_canada_library.py:157 pre-fix), so recent TSX listings' heatmap
tile click-throughs landed on canada_stock's "not in library" dead end. The fix
ports build_china_library's _limited_rec / allow_limited idiom universe-wide:
sub-floor names now emit an honest, searchable LIMITED record (identity + listing
date + chart; canada_stock renders the "analysis pending" card) and NEVER enter
scoring/boards/profiles — display-tier accrual without authority.

Run: .venv/bin/python -m pytest tests/test_canada_library_limited.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_view  # noqa: E402
from scripts import build_canada_library as bcal  # noqa: E402

_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "canada_stock.html.j2"


def _series(n: int, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.Series(20 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n))), index=idx)


def test_short_history_emits_limited_record():
    c = _series(154)
    rec = bcal._one("XYZ.TO", c, None, "Test Co", "Energy", allow_limited=True)
    assert rec is not None and rec["limited"] is True
    assert rec["ladder"] == {"state": "LIMITED"}
    assert rec["ticker"] == "XYZ.TO" and rec["tv"] == "TSX:XYZ"
    assert rec["history_days"] == 154
    assert rec["listed"] == str(c.index.min().date())
    assert rec["asof"] == str(c.index.max().date())


def test_short_history_without_allow_limited_still_drops():
    # the US-parity default: callers that never opted in keep the old contract
    assert bcal._one("XYZ.TO", _series(154), None, "T", "S") is None


def test_empty_series_returns_none_even_with_allow_limited():
    empty = pd.Series([float("nan")] * 10, index=pd.bdate_range("2026-01-01", periods=10))
    assert bcal._one("XYZ.TO", empty, None, "T", "S", allow_limited=True) is None


def test_full_history_record_unchanged():
    # >=300 sessions: the full analysis path runs and the record is NOT limited
    rec = bcal._one("RY.TO", _series(400), None, "Royal Bank", "Financial Services",
                    allow_limited=True)
    assert rec is not None and not rec.get("limited")
    assert rec["ladder"].get("state") and rec["ladder"]["state"] != "LIMITED"


def test_fanout_worker_opts_in():
    # the nightly build reaches _one only through _ca_one_task — lock the opt-in there
    bcal._ca_winit(None)
    rec = bcal._ca_one_task(("XYZ.TO", _series(154), None, "N", "Energy"))
    assert rec is not None and rec.get("limited") is True


def test_limited_rec_survives_build_view():
    # main()'s write loop applies stock_view.build_view to EVERY record, limited included
    rec = bcal._limited_rec("XYZ.TO", _series(154), "Test Co", "Energy")
    view = stock_view.build_view(rec, "CA")
    assert isinstance(view, dict) and view.get("schema")


def test_lookup_template_carries_limited_branch():
    # the page must branch on `limited` before ever reading the ladder, and the
    # panels renderLimited hides must exist to hide
    src = _TEMPLATE.read_text()
    assert "renderLimited" in src
    assert "if (d.limited) { renderLimited(d); return; }" in src
    for pid in ('id="panel_deep"', 'id="panel_mtf"', 'id="r_cal_panel"'):
        assert pid in src, f"missing {pid}"
