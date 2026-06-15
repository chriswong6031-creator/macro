"""Per-name A/H premium engine test (engine/hk_ah.ah_by_ticker).

Pure-function check on the computed-premium derivation with synthetic price frames:
premium = (A_cny / (H_hkd * cny_per_hkd) - 1) * 100, keyed by H-share ticker, with the
own-history percentile. CONTEXT, not a signal (cross-market valuation gauge)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import hk_ah  # noqa: E402


def _wire(monkeypatch, tmp_path, pairs, names, h, a, cny, hkd):
    monkeypatch.setattr(hk_ah.config, "load", lambda: {"hk": {"ah_pairs": pairs, "names": names}})
    monkeypatch.setattr(hk_ah.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(hk_ah.pd, "read_parquet", lambda p: h)
    monkeypatch.setattr(hk_ah.store, "read", lambda g, n: {
        ("china_search", "closes"): a, ("china", "CNY=X"): cny, ("hk", "HKD=X"): hkd,
    }.get((g, n)))


def test_ah_by_ticker_computes_premium(monkeypatch, tmp_path):
    idx = pd.bdate_range("2024-01-01", periods=300)
    h = pd.DataFrame({"0939.HK": 10.0}, index=idx)        # HKD
    a = pd.DataFrame({"601939.SS": 13.0}, index=idx)      # CNY
    cny = pd.DataFrame({"close": 7.2}, index=idx)         # USDCNY
    hkd = pd.DataFrame({"close": 7.8}, index=idx)         # USDHKD
    _wire(monkeypatch, tmp_path, {"0939.HK": "601939.SS"}, {"0939.HK": "CCB"}, h, a, cny, hkd)
    out = hk_ah.ah_by_ticker()
    assert "0939.HK" in out
    b = out["0939.HK"]
    # cny_per_hkd = 7.2/7.8 = 0.9231; H_in_cny = 9.231; premium = (13/9.231 - 1)*100
    assert b["premium_pct"] == pytest.approx(40.8, abs=0.2)
    assert b["a"] == "601939.SS" and b["name"] == "CCB"
    assert b["pctile"] == 100                              # constant series -> current is the max
    assert b["chg_1y"] == 0.0                              # >252 obs, flat premium


def test_ah_by_ticker_empty_without_pairs(monkeypatch, tmp_path):
    monkeypatch.setattr(hk_ah.config, "load", lambda: {"hk": {}})
    assert hk_ah.ah_by_ticker() == {}


def test_ah_by_ticker_skips_unmatched_pair(monkeypatch, tmp_path):
    idx = pd.bdate_range("2024-01-01", periods=300)
    h = pd.DataFrame({"0939.HK": 10.0}, index=idx)
    a = pd.DataFrame({"601939.SS": 13.0}, index=idx)
    cny = pd.DataFrame({"close": 7.2}, index=idx)
    hkd = pd.DataFrame({"close": 7.8}, index=idx)
    # pair points at an A ticker not present in a_closes -> skipped, empty result
    _wire(monkeypatch, tmp_path, {"9999.HK": "600000.SS"}, {}, h, a, cny, hkd)
    assert hk_ah.ah_by_ticker() == {}
