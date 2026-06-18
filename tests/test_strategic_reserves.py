"""Pure-function tests for the strategic-reserves display leaf (no network).

Covers fill/cover/change helpers, the country-row merge (curated + live JODI),
the global aggregate, and — critically — the invariant that this display leaf is
never wired into any scoring path.
"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import strategic_reserves as sr  # noqa: E402


def _monthly(values, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.DataFrame({"level": values, "assess": [1] * len(values)}, index=idx)


def test_fill_pct():
    assert sr.fill_pct(357, 714) == 50.0
    assert sr.fill_pct(None, 714) is None
    assert sr.fill_pct(300, 0) is None
    assert sr.fill_pct(300, None) is None


def test_change_and_pct():
    s = _monthly([100, 110, 90, 120])["level"]
    assert sr.change(s, 1) == 30.0            # 120 - 90
    assert sr.change(s, 3) == 20.0            # 120 - 100
    assert sr.change(None, 1) is None
    assert sr.pct_change(s, 3) == 20.0        # +20% over 3 steps
    # asking for more periods than history clamps to the earliest point, never crashes
    assert sr.change(s, 99) == 20.0


def test_days_of_cover():
    assert sr.days_of_cover(357_000, 16_000) == 22.3   # kbbl / (kbbl/d)
    assert sr.days_of_cover(357_000, 0) is None
    assert sr.days_of_cover(None, 16_000) is None


def test_trend_word():
    assert sr.trend_word(_monthly([100, 101, 103, 110])["level"], months=3) == "rising"
    assert sr.trend_word(_monthly([110, 105, 100, 90])["level"], months=3) == "falling"
    assert sr.trend_word(_monthly([100, 100.2, 99.9, 100.1])["level"], months=3) == "flat"
    assert sr.trend_word(None) == "—"


def test_assess_word():
    assert sr.assess_word(1) == "reported"
    assert sr.assess_word(3) == "estimate"
    assert sr.assess_word(3, lang="zh") == "估算"
    assert sr.assess_word(None) == ""


def test_series_is_nan_and_unit_safe():
    df = _monthly([100.0, np.nan, 120.0])
    s = sr.series(df)
    assert sr.last_value(df) == 120.0          # trailing handled, NaN dropped
    assert len(s) == 2
    assert sr.series(None) is None


def test_global_aggregate():
    m = {"US": _monthly([730_000]), "JP": _monthly([330_000]), "KR": _monthly([100_000])}
    agg = sr.global_aggregate(m)
    assert agg["n_reporting"] == 3
    assert agg["total_mb"] == 1160.0           # (730000+330000+100000)/1000
    assert sr.global_aggregate({})["total_mb"] is None


def test_merge_country_row_us_live_override():
    cfg = {"iso": "US", "name": "United States", "flag": "🇺🇸", "live": "spr",
           "strategic_mb": 413, "strategic_type": "government", "capacity_mb": 714,
           "days_cover": 125, "source": "EIA", "as_of": "2025-12"}
    jodi = _monthly([700_000, 720_000])        # total US crude (incl commercial+SPR)
    row = sr.merge_country_row(cfg, jodi, live_level_mb=349.0)
    assert row["live"] is True
    assert row["strategic_mb"] == 349.0        # live SPR overrides the curated 413
    assert row["fill_pct"] == round(100 * 349 / 714, 1)
    assert row["jodi_total_mb"] == 720.0       # MMbbl
    assert row["jodi_mom_mb"] == 20.0
    assert row["jodi_assess"] == 1


def test_merge_country_row_china_no_jodi():
    cfg = {"iso": "CN", "name": "China", "flag": "🇨🇳", "no_jodi": True,
           "strategic_mb": 360, "total_mb": 1400, "strategic_type": "estimate",
           "source": "EIA est.", "as_of": "2025-12"}
    # even if a JODI frame is passed, no_jodi must suppress the live column
    row = sr.merge_country_row(cfg, _monthly([1, 2, 3]))
    assert row["jodi_total_mb"] is None
    assert row["strategic_mb"] == 360
    assert row["curated_total_mb"] == 1400


def test_caveat_is_bilingual_and_non_directional():
    for k in ("en", "zh"):
        assert k in sr.SPR_CAVEAT and len(sr.SPR_CAVEAT[k]) > 40
    assert "not a price signal" in sr.SPR_CAVEAT["en"]


def _annual(values, start_year=2022):
    idx = pd.to_datetime([f"{start_year + i}-12-31" for i in range(len(values))])
    return pd.Series(values, index=idx, dtype="float64")


def _monthly_flow(values, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="MS")
    return pd.DataFrame({"level": values, "assess": [1] * len(values)}, index=idx)


def test_net_imports_smoothed():
    imp = _monthly_flow([6000, 6200, 6400])     # kbd
    exp = _monthly_flow([3000, 3400, 3800])
    # trailing-window mean of imports − mean of exports
    assert sr.net_imports(imp, exp, window=3) == round((6200) - (3400), 1)
    assert sr.net_imports(imp, None, window=3) == 6200.0   # missing exports -> 0
    assert sr.net_imports(None, exp) is None
    # net exporter -> negative (caller skips import-cover)
    assert sr.net_imports(_monthly_flow([100]), _monthly_flow([500])) == -400.0


def test_merge_country_row_trade_cover():
    cfg = {"iso": "JP", "name": "Japan", "flag": "🇯🇵"}
    crude = _annual([300_000, 330_000])           # kbbl (reused annual helper ok)
    imp = _monthly_flow([2700, 2730])             # kbd
    exp = _monthly_flow([0, 0])
    row = sr.merge_country_row(cfg, crude, jodi_imports=imp, jodi_exports=exp)
    assert row["net_imports_kbd"] == 2715.0       # mean(2700,2730) − 0
    assert row["stock_cover_days"] == sr.days_of_cover(330_000, 2715.0)


def test_gold_value_share():
    assert sr.gold_value_share(100.0, 25.0) == {"value_usd": 75.0, "share_pct": 75.0}
    assert sr.gold_value_share(None, 25.0)["value_usd"] is None
    assert sr.gold_value_share(0.0, 0.0)["value_usd"] is None
    assert sr.gold_value_share(100.0, 120.0)["value_usd"] is None   # negative -> guarded


def test_total_official_tonnes():
    rows = [{"tonnes": 8133.5}, {"tonnes": 2280.0}, {"tonnes": None}]
    assert sr.total_official_tonnes(rows) == 10414.0
    assert sr.total_official_tonnes([]) is None


def test_merge_gold_row_live():
    cfg = {"iso": "USA", "name": "United States", "flag": "🇺🇸", "tonnes": 8133.5,
           "trend": "stable"}
    total = _annual([770.0, 910.0])     # 2022, 2023
    exgold = _annual([220.0, 228.0])
    row = sr.merge_gold_row(cfg, total, exgold)
    assert row["tonnes"] == 8133.5
    assert row["trend_en"] == "stable"
    assert row["value_usd"] == 910.0 - 228.0          # latest gold value
    assert row["share_pct"] == round(100 * 682 / 910, 1)
    # YoY value vs prior year: (910-228)/(770-220) - 1
    assert row["value_yoy_pct"] == round(100 * (682 / 550 - 1), 1)


def test_merge_gold_row_no_wb():
    cfg = {"iso": "TWN", "name": "Taiwan", "flag": "🇹🇼", "tonnes": 423.6,
           "trend": "stable", "no_wb": True}
    row = sr.merge_gold_row(cfg, _annual([1, 2]), _annual([1, 1]))
    assert row["tonnes"] == 423.6
    assert row["value_usd"] is None and row["share_pct"] is None   # suppressed


def test_gold_caveat_bilingual():
    for k in ("en", "zh"):
        assert k in sr.GOLD_CAVEAT and len(sr.GOLD_CAVEAT[k]) > 40
    assert "not a trade signal" in sr.GOLD_CAVEAT["en"]


def test_leaf_is_never_wired_into_a_scoring_path():
    """Guardrail: strategic reserves are DISPLAY-ONLY. The leaf must not import any
    scoring/alert/conviction module."""
    import_lines = "\n".join(ln for ln in inspect.getsource(sr).splitlines()
                             if ln.strip().startswith(("import ", "from ")))
    for forbidden in ("conviction", "alerts", "signals", "master_brain", "axes",
                      "regime", "meta_label"):
        assert forbidden not in import_lines, f"leaf must not import {forbidden}"
