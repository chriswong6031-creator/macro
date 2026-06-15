"""Additive A-share context-block engine tests (engine/china_extras.py).

Pure-function checks on the derivations from the collector caches: analyst rating
bucketing + forward P/E, earnings next/last selection, valuation-percentile pass-through,
and margin financing trend + % of cap. All CONTEXT, never a scored signal
(research/CHINA_HK_STOCK_SIGNALS.md) — these tests assert shape/derivation only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_extras as ce  # noqa: E402


def _point(monkeypatch, tmp_path):
    monkeypatch.setattr(ce.config, "data_dir", lambda: tmp_path)


def _write(tmp_path, group, name, df):
    d = tmp_path / group
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / name, index=False)


def test_rating_buckets():
    assert ce._rating(8, 1, 1)[0] == "Buy"          # net 0.7
    assert ce._rating(2, 6, 2)[0] == "Hold"         # net 0
    assert ce._rating(0, 1, 5)[0] == "Reduce"       # net -0.83
    assert ce._rating(0, 0, 0) is None              # no coverage


def test_analyst_consensus_forward_pe(monkeypatch, tmp_path):
    _point(monkeypatch, tmp_path)
    yr = pd.Timestamp.now().year
    payload = {"reports": 10, "buy": 7, "overweight": 2, "neutral": 1,
               "underweight": 0, "sell": 0,
               "eps": {str(yr): 5.0, str(yr + 1): 6.25}}
    _write(tmp_path, "china_analyst", "forecast.parquet",
           pd.DataFrame([{"ticker": "600000.SS", "payload": json.dumps(payload)}]))
    out = ce.analyst_consensus({"600000.SS": 50.0})
    b = out["600000.SS"]
    assert b["buy"] == 9 and b["hold"] == 1 and b["sell"] == 0   # 买入+增持 merged
    assert b["rating"] == "Buy"
    assert b["fy1"] == yr and b["eps_fy1"] == 5.0
    assert b["fwd_pe_fy1"] == 10.0                               # 50 / 5
    assert b["fwd_pe_fy2"] == 8.0                                # 50 / 6.25


def test_analyst_consensus_needs_coverage_or_eps(monkeypatch, tmp_path):
    _point(monkeypatch, tmp_path)
    payload = {"reports": 0, "buy": 0, "overweight": 0, "neutral": 0,
               "underweight": 0, "sell": 0, "eps": {}}
    _write(tmp_path, "china_analyst", "forecast.parquet",
           pd.DataFrame([{"ticker": "000001.SZ", "payload": json.dumps(payload)}]))
    assert ce.analyst_consensus({}) == {}


def test_earnings_next_and_last(monkeypatch, tmp_path):
    _point(monkeypatch, tmp_path)
    _write(tmp_path, "china_earnings", "calendar.parquet", pd.DataFrame([
        {"ticker": "600519.SS", "next_date": None, "last_date": "2026-04-25",
         "period": None, "asof": "2026-06-15"},
        {"ticker": "300750.SZ", "next_date": "2026-08-29", "last_date": "2026-04-16",
         "period": "20260630", "asof": "2026-06-15"},
    ]))
    out = ce.earnings_calendar()
    assert out["600519.SS"] == {"next_date": None, "last_date": "2026-04-25"}
    assert out["300750.SZ"]["next_date"] == "2026-08-29"


def test_valuation_percentile_passthrough(monkeypatch, tmp_path):
    _point(monkeypatch, tmp_path)
    payload = {"pe": {"v": 19.2, "pctile": 1.0, "lo": 18.4, "hi": 57.0, "n": 913}}
    _write(tmp_path, "china_valuation", "percentiles.parquet",
           pd.DataFrame([{"ticker": "600519.SS", "payload": json.dumps(payload)}]))
    out = ce.valuation_percentile()
    assert out["600519.SS"]["pe"]["pctile"] == 1.0


def test_margin_positioning_change_and_pct_cap(monkeypatch, tmp_path):
    _point(monkeypatch, tmp_path)
    _write(tmp_path, "china_margin_detail", "detail.parquet", pd.DataFrame([
        {"ticker": "000001.SZ", "fin_balance": 50.0e8, "fin_balance_prior": 53.4e8,
         "date": "2026-06-12", "prior_date": "2026-05-15", "asof": "2026-06-15"},
    ]))
    out = ce.margin_positioning({"000001.SZ": 2000.0})   # mktcap 2000亿
    b = out["000001.SZ"]
    assert b["fin_balance_yi"] == 50.0
    assert b["chg_pct"] == -6.4                            # (50/53.4 - 1)*100
    assert b["pct_mcap"] == 2.5                            # 50 / 2000 * 100


def test_all_empty_when_caches_missing(monkeypatch, tmp_path):
    _point(monkeypatch, tmp_path)
    assert ce.analyst_consensus({}) == {}
    assert ce.earnings_calendar() == {}
    assert ce.valuation_percentile() == {}
    assert ce.margin_positioning({}) == {}
