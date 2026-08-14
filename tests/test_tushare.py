"""Gated Tushare integration — gating, suffix normalisation, and parser contracts.

These run WITHOUT a token (the CI default): the client must be inert and every collector must
no-op, while the china_extras parsers read whatever parquet is on disk (so the free/keyless
build is never affected and a committed Tushare cache still surfaces)."""
from __future__ import annotations

import types

import pandas as pd
import pytest

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


# ---- vendor AUTH rejection: the dark-plane failure mode --------------------- #
# From 2026-07-27 the vendor answered every endpoint with code 40101
# (``您的token不对，请确认。``) — the TUSHARE_TOKEN secret was SET, but its VALUE was
# rejected. query() degrades that to None like any empty snapshot, so every tushare_*
# refresh() returned 0, the china_tushare heartbeat wrote 0.0 (not the -1.0 an exception
# leaves), the adapter reported ok, and run_status / the breaker / every freshness guard
# saw a healthy plane while data/tushare/*.parquet stayed frozen at 2026-07-24 — for ten
# nights (last observed in run 31095457182, asia job 2026-08-06 11:39Z: trade_cal, daily,
# daily_basic and moneyflow_dc all 40101). These pin the loud path.
_REJECT_40101 = {"code": 40101, "msg": "您的token不对，请确认。"}


class _Resp:
    """requests.Response stand-in — the vendor answers HTTP 200 even when it rejects you."""

    def __init__(self, body: dict, *, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.is_redirect = 300 <= status_code < 400
        self.is_permanent_redirect = status_code in {301, 308}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


@pytest.fixture
def vendor(monkeypatch):
    """A configured token + a controllable vendor; mutate ``vendor["body"]`` to change the reply."""
    monkeypatch.setenv("TUSHARE_TOKEN", "not-a-real-credential")
    monkeypatch.setattr(tc, "_auth_error", None)     # no latch leaking in from another test
    monkeypatch.setattr(tc, "_last_call", {})        # no throttle sleeps
    box = {"body": dict(_REJECT_40101)}
    monkeypatch.setattr(tc.requests, "post", lambda *a, **k: _Resp(box["body"]))
    return box


def test_paid_token_transport_is_https_and_redirects_are_disabled(vendor, monkeypatch):
    observed = {}

    def _post(url, **kwargs):
        observed["url"] = url
        observed["kwargs"] = kwargs
        return _Resp({"code": 0, "data": {"fields": ["ts_code"], "items": [["600519.SH"]]}})

    monkeypatch.setattr(tc.requests, "post", _post)
    assert tc.query("daily", trade_date="20260807") is not None
    assert observed["url"] == "https://api.tushare.pro"
    assert observed["kwargs"]["allow_redirects"] is False
    assert observed["kwargs"]["json"]["token"] == "not-a-real-credential"


def test_redirect_and_vendor_message_fail_closed_without_credential_echo(vendor, monkeypatch, caplog):
    token_text = "not-a-real-credential"
    monkeypatch.setattr(
        tc.requests,
        "post",
        lambda *a, **k: _Resp({"code": 0}, status_code=307),
    )
    assert tc.query("daily") is None
    assert token_text not in caplog.text

    caplog.clear()
    vendor["body"] = {"code": 40101, "msg": f"rejected token={token_text}"}
    monkeypatch.setattr(tc.requests, "post", lambda *a, **k: _Resp(vendor["body"]))
    assert tc.query("daily") is None
    assert token_text not in caplog.text
    assert token_text not in str(tc.last_auth_error())

    caplog.clear()

    def _raise_with_credential(*args, **kwargs):
        raise RuntimeError(f"request payload contained token={token_text}")

    monkeypatch.setattr(tc.requests, "post", _raise_with_credential)
    assert tc.query("daily") is None
    assert token_text not in caplog.text


def _adapter_with(monkeypatch, counts: dict[str, int]):
    """ChinaTushareAdapter whose sub-modules are stubs that go through the REAL client.

    Each stub's refresh() makes a genuine ``tc.query`` call (so the vendor's 40101 reaches it
    exactly as it does nightly) and then reports the row count this test wants — the real
    collectors would touch data/ and the network, and cannot be made to land rows without
    writing parquet into the repo.
    """
    from collectors import china_tushare as ct

    def _import(dotted: str):
        name = dotted.rsplit(".", 1)[-1]
        mod = types.ModuleType(dotted)
        mod.refresh = lambda _n=counts.get(name, 0), _api=f"api_{name}": (
            tc.query(_api, trade_date="20260806"), _n)[1]
        return mod

    monkeypatch.setattr(ct, "importlib", types.SimpleNamespace(import_module=_import))
    return ct.ChinaTushareAdapter()


def test_auth_rejection_raises_and_annotates(vendor, monkeypatch, capsys):
    """40101 everywhere + zero rows → RuntimeError + a line-start ::error, not a healthy heartbeat."""
    adapter = _adapter_with(monkeypatch, {})           # every module returns 0, as in the outage
    # token present ⇒ NOT an expected_failure, so run_adapter records 'failed' and the breaker counts it
    assert getattr(adapter, "expected_failure", None) is None
    with pytest.raises(RuntimeError) as excinfo:
        adapter.fetch()
    detail = str(excinfo.value)
    assert "40101" in detail and "TUSHARE_TOKEN" in detail and "tushare.pro" in detail
    # the annotation must START its line — through a logger GitHub silently drops it
    ann = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::error")]
    assert len(ann) == 1, f"expected exactly one line-start ::error annotation, got {ann}"
    assert "title=tushare-auth-rejected" in ann[0] and "40101" in ann[0]


def test_partial_rows_do_not_raise(vendor, monkeypatch, capsys):
    """A latched rejection with SOME module still landing rows is a warning, never a failed night."""
    adapter = _adapter_with(monkeypatch, {"tushare_valuation": 4200})
    out = adapter.fetch()                              # must not raise
    assert tc.last_auth_error()["code"] == 40101       # the vendor did reject — still latched
    assert out["run_log"]["tushare_valuation"].iloc[0] == 4200.0
    assert "::error" not in capsys.readouterr().out


def test_auth_latch_clears_on_the_next_success(vendor):
    """query()'s return contract is unchanged; the latch records the cause and self-heals."""
    assert tc.query("daily_basic", trade_date="20260806") is None    # still None — no caller changes
    err = tc.last_auth_error()
    assert err["code"] == 40101 and err["api_name"] == "daily_basic"
    assert err["msg"] == "credential rejected by vendor"
    assert err is not tc._auth_error, "last_auth_error() must hand back a copy, not the latch"
    # the credential is restored (re-copied or the account healed) → the very next authenticated
    # round-trip clears the latch, no restart. Deliberately not "regenerates": the 07-27 outage
    # began with a secret nobody had touched since 07-02, so recovery need not involve a new token.
    vendor["body"] = {"code": 0, "data": {"fields": ["ts_code"], "items": [["600519.SH"]]}}
    df = tc.query("daily_basic", trade_date="20260807")
    assert df is not None and df["ts_code"].iloc[0] == "600519.SS"
    assert tc.last_auth_error() is None


def test_successful_empty_response_can_be_distinguished_when_requested(vendor):
    """Event collectors need to checkpoint a real zero-row day without treating errors as empty."""
    vendor["body"] = {"code": 0, "data": {"fields": ["ts_code", "trade_date"], "items": []}}
    assert tc.query("suspend_d", trade_date="20260807") is None  # legacy contract
    empty = tc.query("suspend_d", trade_date="20260807", _return_empty=True,
                     fields="ts_code,trade_date")
    assert empty is not None and empty.empty
    assert list(empty.columns) == ["ts_code", "trade_date"]


@pytest.mark.parametrize("malformed", [
    {"code": 0},
    {"code": 0, "data": None},
    {"code": 0, "data": {}},
    {"code": 0, "data": {"fields": [], "items": []}},
    {"code": 0, "data": {"fields": ["ts_code"]}},
    {"code": 0, "data": {"fields": ["ts_code"], "items": None}},
    {"code": 0, "data": {"fields": ["ts_code"], "items": [{"ts_code": "x"}]}},
    {"code": 0, "data": {"fields": ["ts_code"], "items": [["x", "y"]]}},
    [],
])
def test_return_empty_rejects_malformed_code_zero_payloads(vendor, malformed):
    """A code-0 shell is not evidence of a real, schema-bound empty response."""
    vendor["body"] = malformed
    assert tc.query(
        "suspend_d", trade_date="20260807", _return_empty=True,
        fields="ts_code,trade_date",
    ) is None


def test_rate_limit_and_entitlement_are_not_auth_errors(vendor):
    """DELIBERATELY NARROW: 40203 (throttle / above-tier) must not read as a dead credential —
    report_rc is throttled by design every single night."""
    vendor["body"] = {"code": 40203, "msg": "抱歉，您没有接口访问权限"}
    assert tc.query("report_rc", start_date="20260806") is None
    assert tc.last_auth_error() is None
    assert tc._AUTH_CODES == frozenset({40101})


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


# ---- the accrual grid: fresh at the head, and phase-stable ------------------ #
def _write_closes(tmp_path, n_days: int):
    """A china_search close panel with `n_days` business-day rows."""
    d = tmp_path / "china_search"
    d.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range("2024-01-01", periods=n_days, name="Date")
    pd.DataFrame({"600519.SS": range(n_days)}, index=idx).to_parquet(d / "closes.parquet")
    return idx


def test_grid_newest_is_the_newest_close(monkeypatch, tmp_path):
    """The head of the grid must BE the last close. It used to be `idx[-260:][::5]`, whose
    newest kept element is always position -5 — so the flow page printed an as-of 4 trading
    days behind the southbound card beside it, every day, structurally."""
    from collectors import tushare_history as th
    monkeypatch.setattr(th.config, "data_dir", lambda: tmp_path)
    idx = _write_closes(tmp_path, 400)
    grid = th._grid_dates()
    assert grid[-1] == idx[-1].strftime("%Y%m%d")                    # zero lag, not 4 days
    assert grid[-1] != list(idx[-260:][::5])[-1].strftime("%Y%m%d")  # the old slice's answer
    assert grid == [d.strftime("%Y%m%d") for d in idx[-th._GRID_DAYS:]]   # contiguous, in order
    assert len(grid) == th._GRID_DAYS == len(set(grid))


def test_grid_has_no_stride_phase_to_drift(monkeypatch, tmp_path):
    """A tail-anchored stride has no fixed origin: every build shifted the whole grid one
    trading day, so the append-only store accreted all five phases and became daily anyway.
    A contiguous grid is phase-free — consecutive builds differ by exactly the new bar."""
    from collectors import tushare_history as th
    monkeypatch.setattr(th.config, "data_dir", lambda: tmp_path)
    seen = []
    for n in (400, 401, 402):
        idx = _write_closes(tmp_path, n)
        grid = th._grid_dates()
        assert grid[-1] == idx[-1].strftime("%Y%m%d")   # head tracks the panel, always
        seen.append(set(grid))
    # each build adds exactly one date and drops exactly one — no phase, no re-sampling
    for a, b in zip(seen, seen[1:]):
        assert len(b - a) == 1 and len(a - b) == 1


def test_grid_short_panel_and_missing_panel(monkeypatch, tmp_path):
    """Shorter-than-grid panels return everything they have; an absent panel returns []."""
    from collectors import tushare_history as th
    monkeypatch.setattr(th.config, "data_dir", lambda: tmp_path)
    assert th._grid_dates() == []                       # no closes.parquet at all
    idx = _write_closes(tmp_path, 30)
    grid = th._grid_dates()
    assert len(grid) == 30 and grid[-1] == idx[-1].strftime("%Y%m%d")


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


def test_report_rc_accrues_across_windows(monkeypatch, tmp_path):
    """report_rc history is the point (module docstring): a later trailing-30d fetch must APPEND
    to the store, not overwrite it — rows collected by earlier runs survive, and a re-fetched
    report keeps its first-seen row. REGRESSION: a bare rc.to_parquet(OUT_RC) fails this."""
    from collectors import tushare_forecast as tf
    monkeypatch.setattr(tf, "OUT", tmp_path / "forecast.parquet")
    monkeypatch.setattr(tf, "OUT_HIST", tmp_path / "forecast_hist.parquet")
    monkeypatch.setattr(tf, "OUT_RC", tmp_path / "report_rc.parquet")
    monkeypatch.setattr(tf.tc, "enabled", lambda: True)

    def rc_row(code, rdate, eps):
        return {"ts_code": code, "report_date": rdate, "org_name": "中金公司",
                "author_name": "王明", "quarter": "2026Q4", "report_title": "深度报告",
                "eps": eps, "rating": "买入"}

    windows = iter([
        pd.DataFrame([rc_row("600519.SH", "20260601", 10.0),
                      rc_row("000001.SZ", "20260620", 1.2)]),
        # shifted window: 600519's June report has scrolled out of the trailing 30d; 000001's row
        # is re-fetched with a revised eps (same identity key); one brand-new July row appears
        pd.DataFrame([rc_row("000001.SZ", "20260620", 9.9),
                      rc_row("300750.SZ", "20260715", 3.3)]),
    ])
    monkeypatch.setattr(tf.tc, "query",
                        lambda api, *a, **kw: next(windows) if api == "report_rc" else None)

    tf.refresh()
    assert len(pd.read_parquet(tf.OUT_RC)) == 2
    tf.refresh()
    got = pd.read_parquet(tf.OUT_RC)
    # window-1 rows survived the window-2 write; the new row appended; the overlap didn't double
    assert set(got["ticker"]) == {"600519.SH", "000001.SZ", "300750.SZ"} and len(got) == 3
    # keep-first: the re-fetched overlapping report kept its first-seen payload
    assert got.loc[got["ticker"] == "000001.SZ", "eps"].item() == 1.2


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
