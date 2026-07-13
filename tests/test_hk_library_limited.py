"""LIMITED-record port for recent HK listings (heatmap to hk_lookup coverage gap).

2026-07-12: HK heatmap tiles and the hk_lookup search read the same panel, but
scripts/build_hk_library.py _one() hard-dropped anything under 300 sessions
(line ~259 before this fix), so recent listings' tile click-throughs hit
hk_lookup's NOT-IN-LIBRARY dead end. The fix ports build_stock_library's
_limited_rec / allow_limited idiom universe-wide: sub-floor names now emit an
honest, searchable LIMITED record (identity + listing date + chart; hk_lookup
renders the "analysis pending" card) and NEVER enter scoring/boards/profiles —
display-tier accrual without authority.

HK-specific: the limited rec carries a `chart` dict (inline close series) because
HKEX data is login-gated on TradingView's free embed — the chart draws from our
stored prices and must survive even on thin history.

Run: .venv/bin/python -m pytest tests/test_hk_library_limited.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_view  # noqa: E402
from scripts import build_hk_library as bhl  # noqa: E402

_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "hk_lookup.html.j2"


def _series(n: int, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.Series(20 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n))), index=idx)


def test_short_history_emits_limited_record():
    c = _series(154)
    rec = bhl._one("1024.HK", c, None, "Test Co", "Technology", allow_limited=True)
    assert rec is not None and rec["limited"] is True
    assert rec["ladder"] == {"state": "LIMITED"}
    assert rec["ticker"] == "1024.HK" and rec["tv"] == "HKEX:1024"
    assert rec["history_days"] == 154
    assert rec["listed"] == str(c.index.min().date())
    assert rec["asof"] == str(c.index.max().date())


def test_short_history_without_allow_limited_still_drops():
    # the US/CN-parity default: callers that never opted in keep the old contract
    assert bhl._one("1024.HK", _series(154), None, "T", "S") is None


def test_empty_series_returns_none_even_with_allow_limited():
    empty = pd.Series([float("nan")] * 10, index=pd.bdate_range("2026-01-01", periods=10))
    assert bhl._one("9988.HK", empty, None, "T", "S", allow_limited=True) is None


def test_full_history_record_unchanged():
    # >=300 sessions: the full analysis path runs and the record is NOT limited
    rec = bhl._one("0700.HK", _series(400), None, "Tencent", "Technology",
                   allow_limited=True)
    assert rec is not None and not rec.get("limited")
    assert rec["ladder"].get("state") and rec["ladder"]["state"] != "LIMITED"


def test_fanout_worker_opts_in():
    # the nightly build reaches _one only through _hk_one_task — lock the opt-in there
    bhl._hk_winit(None)
    rec = bhl._hk_one_task(("1024.HK", _series(154), None, "N", "Tech"))
    assert rec is not None and rec.get("limited") is True


def test_limited_rec_survives_build_view():
    # main()'s glob pass applies stock_view.build_view to EVERY record with a
    # ladder key, limited included — the view must not crash on thin records
    rec = bhl._limited_rec("1024.HK", _series(154), "Test Co", "Technology")
    view = stock_view.build_view(rec, "HK")
    assert isinstance(view, dict) and view.get("schema")


def test_limited_rec_carries_chart():
    # HK-specific: the limited rec must carry a truthy chart dict with equal-length
    # t/c lists — hk_lookup draws its price chart from d.chart inline (HKEX is
    # login-gated on TradingView's free embed)
    rec = bhl._limited_rec("1024.HK", _series(154), "Test Co", "Technology")
    ch = rec.get("chart")
    assert ch and isinstance(ch, dict)
    assert "t" in ch and "c" in ch
    assert len(ch["t"]) == len(ch["c"]) and len(ch["t"]) > 0


def test_lookup_template_carries_limited_branch():
    # the page must branch on `limited` before ever reading the ladder, and the
    # panels renderLimited hides must exist to hide
    src = _TEMPLATE.read_text()
    assert "renderLimited" in src
    assert "if (d.limited) { renderLimited(d); return; }" in src
    for pid in ('id="panel_deep"', 'id="panel_mtf"', 'id="panel_cal"'):
        assert pid in src, f"missing {pid}"
