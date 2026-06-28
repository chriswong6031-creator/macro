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


def test_history_collector_noop_without_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    from collectors import tushare_history as th
    assert th.refresh() == 0
    # _flow_value sums 超大单 + 大单 rates (the live-leg definition), falls back to net rate
    class R:  # noqa: D401 — tiny stand-in for an itertuples row
        buy_elg_amount_rate, buy_lg_amount_rate, net_amount_rate = 3.0, 2.0, 9.0
    assert th._flow_value(R()) == 5.0
    class R2:
        buy_elg_amount_rate = buy_lg_amount_rate = None
        net_amount_rate = 7.0
    assert th._flow_value(R2()) == 7.0


# ---- validation families for the new gated legs ---------------------------- #
def test_validation_has_fundflow_chips_sign_priors():
    from engine import china_validation as cv
    assert cv._SIGN_EXPECTED["fundflow"] == 1     # inflow → continuation
    assert cv._SIGN_EXPECTED["chips"] == -1       # euphoric win-rate → contrarian


def test_hist_cross_sections_reads_parquet(monkeypatch, tmp_path):
    from engine import china_validation as cv
    monkeypatch.setattr(cv.config, "data_dir", lambda: tmp_path)
    assert cv._hist_cross_sections("flow_hist", "flow") == {}     # absent → {}
    d = tmp_path / "tushare"
    d.mkdir(parents=True)
    rows = [{"ticker": f"{600000+i}.SS", "date": dt, "flow": float(i - 6)}
            for dt in ("20250106", "20250113") for i in range(12)]
    pd.DataFrame(rows).to_parquet(d / "flow_hist.parquet", index=False)
    xs = cv._hist_cross_sections("flow_hist", "flow")
    assert len(xs) == 2 and all(len(s) == 12 for s in xs.values())


def test_validate_all_includes_new_families(monkeypatch, tmp_path):
    """fundflow + chips appear in the scorecard, degrading to `accruing` with no history."""
    from engine import china_validation as cv
    monkeypatch.setattr(cv.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(cv, "_panel", lambda: None)       # no price panel → families go accruing
    monkeypatch.setattr(cv, "_bench_close", lambda: None)
    out = cv.validate_all()
    fams = out.get("families", {})
    assert "fundflow" in fams and "chips" in fams
    assert fams["fundflow"]["status"] == "accruing" and fams["fundflow"]["sign_expected"] == 1


def test_flow_leg_zeroed_when_fundflow_proven_wrong_sign(monkeypatch):
    """The whole point: a proven wrong-sign fundflow family drops the `flow` convergence weight to 0."""
    from engine import china_signal_lab as sl
    assert sl._VAL_FAMILY["flow"] == "fundflow"
    monkeypatch.setattr(sl, "load_validation", lambda: {
        "fundflow": {"mean_ic": -0.04, "t_hac": -3.5, "n_obs": 300, "sign_ok": False, "proven": False}})
    w = sl.leg_weights_for("altdata")
    assert w.get("flow", 0) == 0.0
    assert sum(w.values()) > 0.99      # renormalized over the surviving legs


# ---- follow-up: sector-flow radar pair --------------------------------------- #
def test_sector_flow_signal_deadband():
    from engine import china_radar as cr
    boards = {"银行": 5.0, "煤炭": -4.0, "半导体": 0.5}
    assert cr._sector_flow_signal("银行", boards)["dir"] == 1
    assert cr._sector_flow_signal("煤炭", boards)["dir"] == -1
    assert cr._sector_flow_signal("半导体", boards)["dir"] == 0     # within ±1.0 deadband → silent
    assert cr._sector_flow_signal("不存在", boards) is None
    # the map points at boards that exist in the 东财 industry feed (exact names)
    assert ("512800.SS", "Banks", "银行", "银行") in cr._SECTOR_FLOW_MAP


def test_sector_flow_boards_reads_parquet(monkeypatch, tmp_path):
    from engine import china_radar as cr
    monkeypatch.setattr(cr, "store", cr.store)   # keep store; only patch the data dir via config
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    (tmp_path / "tushare").mkdir(parents=True)
    pd.DataFrame([{"sector_code": "BK0001.DC", "name": "银行", "net_amount_rate": 5.0, "content_type": "行业"},
                  {"sector_code": "BK0002.DC", "name": "天津板块", "net_amount_rate": 9.0, "content_type": "地域"}]
                 ).to_parquet(tmp_path / "tushare" / "moneyflow_sector.parquet", index=False)
    b = cr._sector_flow_boards()
    assert b.get("银行") == 5.0 and "天津板块" not in b      # 行业 only (地域 excluded)


# ---- follow-up: earnings-guidance signal + validation family ------------------ #
def test_guidance_score_sign_and_magnitude():
    from collectors import tushare_forecast as tf
    assert tf._guidance_score("预增", 40, 60) == 1.0          # positive type, big Δ → +1
    assert tf._guidance_score("预减", 40, 60) == -1.0         # sign from TYPE, magnitude from |Δ|
    assert 0 < tf._guidance_score("略增", None, None) <= 0.5  # directional but no magnitude → base only
    assert tf._guidance_score("其他", 10, 20) is None         # unmapped/neutral type


def test_forecast_guidance_parser(monkeypatch, tmp_path):
    from engine import china_extras as ce
    monkeypatch.setattr(ce.config, "data_dir", lambda: tmp_path)
    assert ce.forecast_guidance() == {}
    d = tmp_path / "tushare"
    d.mkdir(parents=True)
    pd.DataFrame([
        {"ticker": "600519.SS", "type": "预增", "p_change_min": 40.0, "p_change_max": 60.0,
         "guidance_score": 1.0, "ann_date": "20260415"},
        {"ticker": "000002.SZ", "type": "首亏", "p_change_min": -200.0, "p_change_max": -150.0,
         "guidance_score": -1.0, "ann_date": "20260415"},
    ]).to_parquet(d / "forecast.parquet", index=False)
    g = ce.forecast_guidance()
    assert g["up"][0]["ticker"] == "600519.SS" and g["down"][0]["ticker"] == "000002.SZ"
    assert ce.GUIDANCE_LABELS["预增"][0] == "Sharp rise"
    # sign-filtered: ▲up only positive, ▼down only negative, even on a tiny universe (no cross-contamination)
    assert all(r["guidance_score"] > 0 for r in g["up"]) and all(r["guidance_score"] < 0 for r in g["down"])


def test_guidance_family_in_validation(monkeypatch, tmp_path):
    from engine import china_validation as cv
    monkeypatch.setattr(cv.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(cv, "_panel", lambda: None)
    monkeypatch.setattr(cv, "_bench_close", lambda: None)
    out = cv.validate_all()
    assert "guidance" in out["families"]
    assert out["families"]["guidance"]["sign_expected"] == 1
    assert cv._SIGN_EXPECTED["guidance"] == 1


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
