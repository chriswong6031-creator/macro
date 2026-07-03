"""Tests for the deep A/H premium panel (W01A slice).

Covers:
- premium formula correctness
- missing-leg skip
- tripwire bounds
- full build shape (requires data/hk_ah_panel/ to be built)
- engine/hk_ah panel reader functions
- collector metadata
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


from scripts.build_ah_panel import PREMIUM_LO, PREMIUM_HI, FX_MAX_STALE_DAYS, _tripwire, _build_pair


def _idx(n=300, start="2024-01-01"):
    return pd.bdate_range(start, periods=n)


def test_premium_formula():
    """premium = A_cny / (H_hkd * cny_per_hkd) - 1 must land at ~0.408."""
    idx = _idx()
    h_clos = pd.Series(10.0, index=idx, name="0939.HK")
    a_clos = pd.Series(13.0, index=idx, name="601939.SS")
    usdcny = pd.Series(7.2, index=idx)
    usdhkd = pd.Series(7.8, index=idx)
    cny_per_hkd = (usdcny / usdhkd).rename("close")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        hk_dir = tdp / "hk_stocks"
        china_dir = tdp / "china_stocks"
        hk_dir.mkdir(); china_dir.mkdir()
        pd.DataFrame({"close": h_clos}).to_parquet(hk_dir / "0939.HK.parquet")
        pd.DataFrame({"close": a_clos}).to_parquet(china_dir / "601939.SS.parquet")
        prem = _build_pair("0939.HK", "601939.SS", cny_per_hkd, hk_dir, china_dir)
    assert prem is not None and not prem.empty
    assert abs(float(prem.iloc[-1]) - 0.408) < 0.002


def test_missing_h_leg_returns_none():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        hk_dir = tdp / "hk_stocks"; china_dir = tdp / "china_stocks"
        hk_dir.mkdir(); china_dir.mkdir()
        pd.Series(13.0, index=_idx(), name="601939.SS").to_frame().to_parquet(
            china_dir / "601939.SS.parquet")
        assert _build_pair("0939.HK", "601939.SS", pd.Series(0.92, index=_idx()), hk_dir, china_dir) is None


def test_missing_a_leg_returns_none():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        hk_dir = tdp / "hk_stocks"; china_dir = tdp / "china_stocks"
        hk_dir.mkdir(); china_dir.mkdir()
        pd.Series(10.0, index=_idx(), name="0939.HK").to_frame().to_parquet(
            hk_dir / "0939.HK.parquet")
        assert _build_pair("0939.HK", "601939.SS", pd.Series(0.92, index=_idx()), hk_dir, china_dir) is None


def test_tripwire_clips_lo():
    idx = _idx(10)
    s = pd.Series([-2.0, 0.5, -0.95, 0.3, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6], index=idx)
    out = _tripwire("TEST.HK", s)
    assert out.isna().sum() == 2


def test_tripwire_clips_hi():
    idx = _idx(5)
    s = pd.Series([0.5, 11.0, 0.3, 15.0, 0.2], index=idx)
    out = _tripwire("TEST.HK", s)
    assert out.isna().sum() == 2


def test_tripwire_passes_valid():
    idx = _idx(5)
    s = pd.Series([0.1, 0.5, 1.0, 5.0, 9.9], index=idx)
    out = _tripwire("TEST.HK", s)
    assert out.isna().sum() == 0


PANEL_DIR = ROOT / "data" / "hk_ah_panel"


@pytest.mark.skipif(not PANEL_DIR.exists(), reason="panel not built")
def test_panel_shape():
    panel = pd.read_parquet(PANEL_DIR / "premium.parquet")
    assert panel.shape[1] >= 20, f"Expected >=20 pairs, got {panel.shape[1]}"
    assert panel.shape[0] >= 4000, f"Expected >=4000 dates, got {panel.shape[0]}"
    assert panel.stack().abs().mean() < 5.0, "Values look like percent not fraction"


@pytest.mark.skipif(not PANEL_DIR.exists(), reason="panel not built")
def test_panel_today_has_data():
    panel = pd.read_parquet(PANEL_DIR / "premium.parquet")
    panel.index = pd.to_datetime(panel.index)
    today = pd.Timestamp.today().normalize()
    last_date = panel.index.max()
    assert (today - last_date).days <= 5, f"Panel stale: last date {last_date.date()}"
    last_row = panel.iloc[-1].dropna()
    assert len(last_row) >= 20, f"Too few pairs with data today: {len(last_row)}"


@pytest.mark.skipif(not PANEL_DIR.exists(), reason="panel not built")
def test_pairs_json_structure():
    with open(PANEL_DIR / "pairs.json") as f:
        pairs = json.load(f)
    assert len(pairs) >= 20
    for p in pairs:
        assert "h" in p and "a" in p
        assert "joint_start" in p
        assert "n_days" in p and p["n_days"] > 100


from engine import hk_ah


@pytest.mark.skipif(not PANEL_DIR.exists(), reason="panel not built")
def test_panel_summary_returns_dict():
    summary = hk_ah.panel_summary()
    assert summary is not None
    assert summary["n_pairs_total"] >= 20
    assert summary["n_pairs_today"] >= 20
    assert "depth" in summary
    assert summary["depth"]["pairs_reaching_2015"] >= 15
    assert summary["latest_mean_prem_pct"] is not None


@pytest.mark.skipif(not PANEL_DIR.exists(), reason="panel not built")
def test_panel_equal_weight_basket():
    basket = hk_ah.panel_equal_weight_basket()
    assert basket is not None and not basket.empty
    assert len(basket) >= 4000
    assert float(basket.mean()) > 0


@pytest.mark.skipif(not PANEL_DIR.exists(), reason="panel not built")
def test_panel_pair_premiums_filter():
    df = hk_ah.panel_pair_premiums(h_tickers=["0939.HK", "0857.HK"])
    assert df is not None and not df.empty
    assert set(df.columns).issubset({"0939.HK", "0857.HK"})


@pytest.mark.skipif(not PANEL_DIR.exists(), reason="panel not built")
def test_panel_pair_premiums_since():
    df = hk_ah.panel_pair_premiums(since="2020-01-01")
    assert df is not None
    assert df.index.min() >= pd.Timestamp("2020-01-01")


def test_panel_summary_returns_none_when_no_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(hk_ah.config, "data_dir", lambda: tmp_path)
    assert hk_ah.panel_summary() is None


def test_panel_equal_weight_basket_returns_none_when_no_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(hk_ah.config, "data_dir", lambda: tmp_path)
    assert hk_ah.panel_equal_weight_basket() is None


def test_panel_pair_premiums_returns_none_when_no_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(hk_ah.config, "data_dir", lambda: tmp_path)
    assert hk_ah.panel_pair_premiums() is None


def test_collector_importable():
    from collectors.hk_ah_panel import HkAhPanelAdapter
    adapter = HkAhPanelAdapter()
    assert adapter.name == "hk_ah_panel"
    assert adapter.group == "hk_ah_panel"
    assert adapter.stale_after_days == 5
