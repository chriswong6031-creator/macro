"""LIMITED-record port for recent international listings (search dead end fix).

2026-07-12: intl_stock's search universe reads the same panel the library builds from,
but scripts/build_intl_library.py (line ~105, now removed) hard-dropped anything under
300 sessions, so recent listings hit intl_stock's NOT-IN-LIBRARY dead end. The fix ports
build_stock_library's _limited_rec / allow_limited idiom universe-wide: sub-floor names
now emit an honest, searchable LIMITED record (identity + listing date + chart; intl_stock
renders the "analysis pending" card) and NEVER enter scoring/standouts/profiles —
display-tier accrual without authority. Intl charts from site/intlohlc/ which
emit_close_only builds off the index, so limited names get charts for free once indexed.

Run: .venv/bin/python -m pytest tests/test_intl_library_limited.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_view  # noqa: E402
from scripts import build_intl_library as bil  # noqa: E402

_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "intl_stock.html.j2"


def _series(n: int, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.Series(20 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n))), index=idx)


def test_short_history_emits_limited_record():
    c = _series(154)
    rec = bil._one("7203.T", c, "Toyota", "Consumer Cyclical", "🇯🇵", "Japan",
                   allow_limited=True)
    assert rec is not None and rec["limited"] is True
    assert rec["ladder"] == {"state": "LIMITED"}
    assert rec["ticker"] == "7203.T" and rec["tv"] == "TSE:7203"
    assert rec["history_days"] == 154
    assert rec["listed"] == str(c.index.min().date())
    assert rec["asof"] == str(c.index.max().date())
    # intl-specific fields: flag and market must be carried
    assert rec["flag"] == "🇯🇵"
    assert rec["market"] == "Japan"


def test_short_history_without_allow_limited_still_drops():
    # the US-parity default: callers that never opted in keep the old contract
    assert bil._one("7203.T", _series(154), "Toyota", "Consumer Cyclical", "🇯🇵", "Japan") is None


def test_empty_series_returns_none_even_with_allow_limited():
    empty = pd.Series([float("nan")] * 10, index=pd.bdate_range("2026-01-01", periods=10))
    assert bil._one("7203.T", empty, "Toyota", "Consumer Cyclical", "🇯🇵", "Japan",
                    allow_limited=True) is None


def test_full_history_record_unchanged():
    # >=300 sessions: the full analysis path runs and the record is NOT limited
    rec = bil._one("7203.T", _series(400), "Toyota", "Consumer Cyclical", "🇯🇵", "Japan",
                   allow_limited=True)
    assert rec is not None and not rec.get("limited")
    assert rec["ladder"].get("state") and rec["ladder"]["state"] != "LIMITED"


def test_fanout_worker_opts_in():
    # the nightly build reaches _one only through _intl_one_task — lock the opt-in there
    # (intl has no initializer, unlike CN; items carry all context)
    rec = bil._intl_one_task(("7203.T", _series(154), "Toyota", "Consumer Cyclical", "🇯🇵", "Japan"))
    assert rec is not None and rec.get("limited") is True


def test_limited_rec_carries_flag_and_market():
    # index row shape: {"t","n","s","st","fl","mk"} — limited rec must supply fl+mk
    rec = bil._limited_rec("7203.T", _series(154), "Toyota", "Consumer Cyclical", "🇯🇵", "Japan")
    assert rec["flag"] == "🇯🇵"
    assert rec["market"] == "Japan"
    assert rec["limited"] is True
    assert rec["ladder"] == {"state": "LIMITED"}


def test_limited_rec_survives_build_view():
    # main()'s write loop applies stock_view.build_view to EVERY record, limited included
    rec = bil._limited_rec("7203.T", _series(154), "Toyota", "Consumer Cyclical", "🇯🇵", "Japan")
    view = stock_view.build_view(rec, "INTL")
    assert isinstance(view, dict) and view.get("schema")


def test_lookup_template_carries_limited_branch():
    # the page must branch on `limited` before ever reading the ladder, and the
    # panels renderLimited hides must exist to hide
    src = _TEMPLATE.read_text()
    assert "renderLimited" in src
    assert "if (d.limited) { renderLimited(d); return; }" in src
    for pid in ('id="panel_deep"', 'id="panel_mtf"', 'id="r_cal_panel"'):
        assert pid in src, f"missing {pid}"
