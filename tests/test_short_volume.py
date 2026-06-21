"""FINRA daily short-volume: collector parse + engine signal."""
from __future__ import annotations

import pandas as pd
import pytest

from collectors.finra_short_volume import _business_days, _parse
from engine.short_volume import load_panel, signal_map

SAMPLE = """Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
20240117|A|252768|9924|403203|B,Q,N
20240117|NVDA|13510815|125613|29647745|B,Q,N
20240117|ZERO|0|0|0|Q
Total Records: 3
"""


def test_parse_drops_header_footer_and_zero_total():
    df = _parse(SAMPLE)
    assert set(df["ticker"]) == {"A", "NVDA"}          # header + footer + ZERO row dropped
    assert {"date", "ticker", "short_vol", "total_vol", "short_ratio"} <= set(df.columns)
    nvda = df[df["ticker"] == "NVDA"].iloc[0]
    assert nvda["short_ratio"] == pytest.approx(13510815 / 29647745, abs=1e-4)
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-17")


def test_parse_empty_on_garbage():
    assert _parse("nonsense\nno pipes here").empty


def _panel(rows):
    return pd.DataFrame(rows, columns=["date", "ticker", "short_vol", "total_vol", "short_ratio"])


def test_signal_map_volume_weighted_trend():
    # baseline (all 6) vw = 1200/6000 = .20; recent(3) vw = 900/3000 = .30
    rows = []
    for i, (sv, tv) in enumerate([(100, 1000)] * 3 + [(300, 1000)] * 3, start=1):
        rows.append((pd.Timestamp(f"2024-01-0{i}"), "AAA", sv, tv, round(sv / tv, 4)))
    sig = signal_map(_panel(rows), recent=3, baseline=20)
    assert "AAA" in sig
    s = sig["AAA"]
    assert s["ratio_recent"] == pytest.approx(0.30, abs=1e-4)
    assert s["ratio_baseline"] == pytest.approx(0.20, abs=1e-4)
    assert s["trend_pp"] == pytest.approx(10.0, abs=0.05)   # building short flow
    assert s["n_days"] == 6
    assert s["asof"] == "2024-01-06"


def test_signal_map_excludes_thin_history():
    rows = [(pd.Timestamp("2024-01-01"), "BBB", 1, 10, 0.1),
            (pd.Timestamp("2024-01-02"), "BBB", 1, 10, 0.1)]   # only 2 days < 3
    assert signal_map(_panel(rows)) == {}


def test_signal_map_empty_inputs():
    assert signal_map(pd.DataFrame()) == {}
    assert signal_map(None) == {} or isinstance(signal_map(None), dict)  # no panel -> {}


def test_load_panel_roundtrip_and_missing(tmp_path):
    assert load_panel(tmp_path / "nope.parquet") is None
    p = tmp_path / "panel.parquet"
    _panel([(pd.Timestamp("2024-01-01"), "AAA", 5, 10, 0.5)]).to_parquet(p)
    got = load_panel(p)
    assert got is not None and list(got["ticker"]) == ["AAA"]


def test_business_days_are_weekdays_newest_first():
    days = _business_days(14)
    assert days == sorted(days, reverse=True)              # newest-first
    assert all(d.weekday() < 5 for d in days)              # no Sat/Sun
    assert len(days) <= 14
