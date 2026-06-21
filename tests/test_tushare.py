"""Gated Tushare integration — gating, suffix normalisation, and parser contracts.

These run WITHOUT a token (the CI default): the client must be inert and every collector must
no-op, while the china_extras parsers read whatever parquet is on disk (so the free/keyless
build is never affected and a committed Tushare cache still surfaces)."""
from __future__ import annotations

import pandas as pd

from collectors import tushare_client as tc


# ---- client gating + normalisation (pure) ---------------------------------- #
def test_client_disabled_without_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    assert tc.enabled() is False
    assert tc.token() is None
    # every call is inert when the gate is closed — no network touched
    assert tc.query("daily", ts_code="000001.SZ") is None
    assert tc.snapshot_by_date("daily_basic") == (None, None)
    assert tc.latest_trade_date() is None


def test_suffix_normalisation():
    assert tc.norm_ticker("600519.SH") == "600519.SS"   # Shanghai → repo convention
    assert tc.norm_ticker("000001.SZ") == "000001.SZ"   # Shenzhen unchanged
    assert tc.norm_ticker("430047.BJ") == "430047.BJ"   # Beijing unchanged
    assert tc.norm_ticker("BK0450.DC") == "BK0450.DC"   # Eastmoney sector code untouched
    assert tc.norm_ticker(None) is None


# ---- collector gating (no-op without a token) ------------------------------ #
def test_collectors_noop_without_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    from collectors import (tushare_valuation, tushare_margin, tushare_moneyflow,
                            tushare_chips, tushare_broker, tushare_forecast)
    for mod in (tushare_valuation, tushare_margin, tushare_moneyflow,
                tushare_chips, tushare_broker, tushare_forecast):
        assert mod.refresh() == 0


# ---- parser contracts (read on-disk parquet; degrade to {}/[] when absent) -- #
def test_fundflow_parser_reads_parquet(monkeypatch, tmp_path):
    from engine import china_extras as ce
    monkeypatch.setattr(ce.config, "data_dir", lambda: tmp_path)
    # absent → {}
    assert ce.fundflow() == {}
    d = tmp_path / "tushare"
    d.mkdir(parents=True)
    pd.DataFrame([
        {"ticker": "600519.SS", "name": "贵州茅台", "net_amount": 1000.0,
         "main_net": 800.0, "main_net_rate": 12.0},
        {"ticker": "000001.SZ", "name": "平安银行", "net_amount": -500.0,
         "main_net": -400.0, "main_net_rate": -6.0},
    ]).to_parquet(d / "moneyflow.parquet", index=False)
    ff = ce.fundflow()
    assert set(ff) == {"600519.SS", "000001.SZ"}
    assert ff["600519.SS"]["flow_score"] > 0 and ff["000001.SZ"]["flow_score"] < 0
    assert ff["600519.SS"]["name"] == "贵州茅台"


def test_broker_gold_and_chips_parsers(monkeypatch, tmp_path):
    import json
    from engine import china_extras as ce
    monkeypatch.setattr(ce.config, "data_dir", lambda: tmp_path)
    assert ce.broker_gold() == [] and ce.chips() == {}
    d = tmp_path / "tushare"
    d.mkdir(parents=True)
    pd.DataFrame([
        {"ticker": "300750.SZ", "name": "宁德时代", "n_brokers": 10,
         "brokers": json.dumps(["A", "B"], ensure_ascii=False), "month": "202606"},
        {"ticker": "600519.SS", "name": "贵州茅台", "n_brokers": 3,
         "brokers": json.dumps(["C"], ensure_ascii=False), "month": "202606"},
    ]).to_parquet(d / "broker.parquet", index=False)
    gold = ce.broker_gold()
    assert gold[0]["ticker"] == "300750.SZ" and gold[0]["n_brokers"] == 10   # sorted desc
    pd.DataFrame([{"ticker": "600519.SS", "winner_rate": 88.0, "weight_avg": 1400.0,
                   "cost_50pct": 1380.0}]).to_parquet(d / "chips.parquet", index=False)
    assert ce.chips()["600519.SS"]["winner_rate"] == 88.0


def test_crowding_prefers_tushare_valuation(monkeypatch, tmp_path):
    from engine import china_crowding as cc
    monkeypatch.setattr(cc.config, "data_dir", lambda: tmp_path)
    d = tmp_path / "tushare"
    d.mkdir(parents=True)
    pd.DataFrame([{"ticker": "600519.SS", "pe_pctile": 95.0, "pb_pctile": 92.0},
                  {"ticker": "000001.SZ", "pe_pctile": 5.0, "pb_pctile": 8.0}]
                 ).to_parquet(d / "valuation.parquet", index=False)
    df = cc._valuation_df()
    assert df is not None and "ticker" in df.columns and "pe_pctile" in df.columns
    assert len(df) == 2          # per-NAME frame (not the 1-row whole-A anchor)
