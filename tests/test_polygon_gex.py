"""Polygon options-OI accrual: chain parsing, pagination, and the raw+summary store.

The collector is display/research-only; these tests pin the parse filters (OI>0,
strike/expiry window, NaN-iv preservation), the snapshot pagination + apiKey
re-attachment, and that accrue() writes the date-partitioned raw chain plus a
compute_gex summary — and is a clean no-op without a key.

AD-1C0 (2026-08-19) extends this file: per-symbol failure-REASON classification,
the census `snapshot()` now returns alongside its DataFrame, the auth
short-circuit probe, the health-verdict/receipt-sidecar first-writer quality
rule in accrue(), and the collectors/base.py secret sanitizer.
"""
from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd
import pytest
import requests

from collectors.base import Adapter, safe_exc_text
from collectors.polygon_options import (
    AUTH_SHORT_CIRCUIT_PROBE,
    REASON_CODES,
    PolygonOptions,
    _classify_exception,
    parse_chain,
)
from lib import config

ASOF = pd.Timestamp("2026-06-15")


def _contract(strike, exp, ctype, oi, iv=0.25, gamma=0.01):
    out = {"details": {"strike_price": strike, "expiration_date": exp,
                       "contract_type": ctype, "ticker": f"O:X{ctype[0].upper()}{strike}"},
           "open_interest": oi, "day": {"volume": 7}}
    if iv is not None:
        out["implied_volatility"] = iv
    if gamma is not None:
        out["greeks"] = {"gamma": gamma, "delta": 0.5}
    return out


def test_parse_chain_filters():
    spot = 100.0
    results = [
        _contract(100, "2026-07-15", "call", 500),       # keep
        _contract(105, "2026-07-15", "put", 0),          # drop: OI 0
        _contract(140, "2026-07-15", "call", 100),       # drop: outside +/-30% window
        _contract(100, "2099-01-01", "call", 100),       # drop: beyond max_expiry_days
        _contract(100, "2026-01-01", "call", 100),       # drop: expired (before asof)
        _contract(98, "2026-07-15", "put", 300, iv=None, gamma=None),  # keep, NaN iv
    ]
    df = parse_chain(results, "X", spot, ASOF, window_pct=0.30, max_expiry_days=400)
    assert len(df) == 2
    assert set(df["K"]) == {100.0, 98.0}
    assert (df["oi"] > 0).all()
    assert df.loc[df["K"] == 98.0, "iv"].isna().all()         # wing NaN preserved
    assert df.loc[df["K"] == 100.0, "iv"].iloc[0] == 0.25
    for col in ("underlying", "expiry", "T", "is_call", "oi", "spot", "asof"):
        assert col in df.columns
    assert (df["T"] > 0).all()


def test_parse_chain_empty_guards():
    assert parse_chain([], "X", 100.0, ASOF, window_pct=0.3, max_expiry_days=400).empty
    assert parse_chain([_contract(100, "2026-07-15", "call", 10)], "X", 0.0, ASOF,
                       window_pct=0.3, max_expiry_days=400).empty


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def test_get_paginates_and_attaches_key(monkeypatch):
    client = PolygonOptions()
    client.key = "TESTKEY"
    calls = []

    pages = iter([
        _Resp({"results": [{"a": 1}], "next_url": "https://api.polygon.io/next?cursor=abc"}),
        _Resp({"results": [{"a": 2}]}),
    ])

    def fake_get(url, **kw):
        calls.append((url, kw.get("params", {})))
        return next(pages)

    monkeypatch.setattr(client, "http_get", fake_get)
    out = client._get("/v3/snapshot/options/SPY", {"limit": 250})
    assert [r["a"] for r in out] == [1, 2]
    # apiKey attached on the first call and re-attached on the cursor follow-up
    assert calls[0][1]["apiKey"] == "TESTKEY"
    assert calls[1][0] == "https://api.polygon.io/next?cursor=abc"
    assert calls[1][1] == {"apiKey": "TESTKEY"}


def test_ticker_details_returns_the_results_dict(monkeypatch):
    """/v3/reference/tickers/{T} returns ``results`` as ONE dict — it must not
    go through _get, whose list.extend would iterate the dict's keys (that
    mismatch silently nulled the S&P 500 shares reference for four weeks)."""
    client = PolygonOptions()
    client.key = "TESTKEY"
    payload = {"results": {"ticker": "BKNG",
                           "weighted_shares_outstanding": 774_878_436}}
    seen = {}

    def fake_get(url, **kw):
        seen["url"], seen["params"] = url, kw.get("params", {})
        return _Resp(payload)

    monkeypatch.setattr(client, "http_get", fake_get)
    res = client.ticker_details("BKNG")
    assert res["weighted_shares_outstanding"] == 774_878_436
    assert seen["url"].endswith("/v3/reference/tickers/BKNG")
    assert seen["params"]["apiKey"] == "TESTKEY"
    # malformed / list-shaped results degrade to {} rather than leaking a list
    monkeypatch.setattr(client, "http_get",
                        lambda url, **kw: _Resp({"results": [{"a": 1}]}))
    assert client.ticker_details("BKNG") == {}


def _raw(symbols=("SPY",), spot=100.0):
    rows = []
    for sym in symbols:
        for k in range(80, 121, 2):
            for call in (True, False):
                rows.append(dict(underlying=sym, strike_ticker=f"O:{sym}{k}",
                                 expiry=ASOF + pd.Timedelta(days=30), K=float(k),
                                 T=30 / 365, is_call=call, oi=1000.0, iv=0.25,
                                 gamma=0.01, delta=0.5, volume=10.0, spot=spot, asof=ASOF))
    return pd.DataFrame(rows)


def _census(raw, symbols, *, aborted_early=False, failure_reasons=None,
           failure_examples=None):
    """A census matching real snapshot()'s shape for a raw frame that captured
    every one of `symbols` cleanly (the common case for the pre-AD-1C0 tests)."""
    successful = int(raw["underlying"].nunique()) if not raw.empty else 0
    return {
        "attempted_underlyings": len(symbols),
        "successful_underlyings": successful,
        "failure_reasons": failure_reasons or {},
        "failure_examples": failure_examples or {},
        "aborted_early": aborted_early,
    }


class _FakeClient:
    """New-contract fake: snapshot() returns (raw_df, census), same as the real
    PolygonOptions.snapshot() after AD-1C0."""

    def __init__(self, raw, enabled=True, census=None):
        self._raw, self._enabled, self._census = raw, enabled, census

    def enabled(self):
        return self._enabled

    def snapshot(self, symbols, asof):
        census = self._census if self._census is not None else _census(self._raw, symbols)
        return self._raw, census


class _LegacyFakeClient:
    """Back-compat fake: snapshot() returns a BARE DataFrame, the pre-AD-1C0
    contract still used by tests/test_polygon_gex_session_stamps.py's own fake.
    accrue() must synthesize a census for this shape rather than crash."""

    def __init__(self, raw, enabled=True):
        self._raw, self._enabled = raw, enabled

    def enabled(self):
        return self._enabled

    def snapshot(self, symbols, asof):
        return self._raw


def test_accrue_writes_raw_and_summary(tmp_path, monkeypatch):
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bpg, "PolygonOptions", lambda: _FakeClient(_raw(("SPY", "QQQ"))))

    # A `date` is an EXPLICIT session — "store session 2026-06-15" (2026-08-06). A
    # datetime would be an accrual INSTANT and would resolve to the session it describes;
    # midnight UTC 06-15 is 20:00 ET Sunday 06-14, i.e. session 06-12. That path has its
    # own tests in tests/test_polygon_gex_session_stamps.py.
    res = bpg.accrue(ASOF.date())
    assert res["status"] == "ok"
    assert res["underlyings"] == 2
    assert res["session"] == "2026-06-15"
    # AD-1C0: a nonempty capture always carries a health verdict + census, even
    # on the plain happy path.
    assert res["health"] in ("healthy", "partial", "failed")
    assert res["census"]["successful_underlyings"] == 2
    assert res["census"]["aborted_early"] is False

    raw_file = tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet"
    assert raw_file.exists()
    back = pd.read_parquet(raw_file)
    assert set(back["underlying"]) == {"SPY", "QQQ"}

    # AD-1C0: the health-receipt sidecar is written next to the chain, and the
    # first ever attempt for a fresh session is always "wrote".
    receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
    assert len(receipt["attempts"]) == 1
    assert receipt["attempts"][0]["decision"] == "wrote"

    summ = pd.read_parquet(tmp_path / "polygon_gex" / "summary_SPY.parquet")
    assert len(summ) == 1
    assert summ.index[0] == ASOF
    assert summ["gamma_regime"].iloc[0] in ("long", "short")
    assert summ["net_gex_bn"].iloc[0] is not None


def test_accrue_no_key_is_noop(tmp_path, monkeypatch):
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bpg, "PolygonOptions", lambda: _FakeClient(_raw(), enabled=False))

    res = bpg.accrue(ASOF.date())
    assert res["status"] == "no_key"
    assert not (tmp_path / "polygon_gex").exists()


def test_accrue_synthesizes_a_census_for_a_legacy_bare_dataframe_snapshot(tmp_path, monkeypatch):
    """Back-compat: a fake whose snapshot() returns a BARE DataFrame (the
    pre-AD-1C0 contract — the exact shape tests/test_polygon_gex_session_stamps.py's
    own fake still uses) must not crash accrue(); a best-effort census is
    synthesized instead."""
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(bpg, "PolygonOptions",
                        lambda: _LegacyFakeClient(_raw(("SPY", "QQQ"))))
    res = bpg.accrue(ASOF.date())
    assert res["status"] == "ok"
    assert res["census"]["successful_underlyings"] == 2
    assert res["census"]["aborted_early"] is False


# ═══════════════ reason-code classification (_classify_exception) ═══════════════

def _http_error(status_code, message=None):
    resp = type("Resp", (), {"status_code": status_code})()
    return requests.HTTPError(message or f"{status_code} Client Error", response=resp)


class TestClassifyException:
    def test_401_is_auth_or_entitlement_failure(self):
        assert _classify_exception(_http_error(401)) == "auth_or_entitlement_failure"

    def test_403_is_auth_or_entitlement_failure(self):
        assert _classify_exception(_http_error(403)) == "auth_or_entitlement_failure"

    def test_403_not_authorized_body_is_auth_or_entitlement_failure(self):
        exc = _http_error(403, "403 Client Error: NOT_AUTHORIZED for url: https://x")
        assert _classify_exception(exc) == "auth_or_entitlement_failure"

    def test_429_is_rate_limit_or_throttle(self):
        assert _classify_exception(_http_error(429)) == "rate_limit_or_throttle"

    def test_other_http_error_is_vendor_or_network_error(self):
        assert _classify_exception(_http_error(500)) == "vendor_or_network_error"
        assert _classify_exception(_http_error(404)) == "vendor_or_network_error"

    def test_connection_error_is_vendor_or_network_error(self):
        assert (_classify_exception(requests.exceptions.ConnectionError("boom"))
                == "vendor_or_network_error")

    def test_timeout_is_vendor_or_network_error(self):
        assert (_classify_exception(requests.exceptions.Timeout("slow"))
                == "vendor_or_network_error")

    def test_unrelated_exception_is_other_failure(self):
        assert _classify_exception(ValueError("weird")) == "other_failure"

    def test_reason_codes_is_the_frozen_set(self):
        assert REASON_CODES == frozenset({
            "no_spot", "auth_or_entitlement_failure", "rate_limit_or_throttle",
            "vendor_or_network_error", "raw_chain_empty", "parse_or_filter_empty",
            "other_failure",
        })


# ═══════════════ per-symbol failure roots (_one_chain) ═══════════════════════════

class TestOneChainReasons:
    def _client(self):
        client = PolygonOptions()
        client.key = "TESTKEY"
        return client

    def test_spot_returns_none_is_no_spot(self, monkeypatch):
        client = self._client()
        monkeypatch.setattr(client, "spot", lambda sym: None)
        df, reason = client._one_chain("XYZ", ASOF.date())
        assert df is None and reason == "no_spot"

    def test_spot_raising_403_is_auth_or_entitlement_failure(self, monkeypatch):
        client = self._client()
        def _raise(sym):
            raise _http_error(403)
        monkeypatch.setattr(client, "spot", _raise)
        df, reason = client._one_chain("XYZ", ASOF.date())
        assert df is None and reason == "auth_or_entitlement_failure"

    def test_chain_raising_429_is_rate_limit_or_throttle(self, monkeypatch):
        client = self._client()
        monkeypatch.setattr(client, "spot", lambda sym: 100.0)
        def _raise(sym, spot, asof):
            raise _http_error(429)
        monkeypatch.setattr(client, "_fetch_raw_results", _raise)
        df, reason = client._one_chain("XYZ", ASOF.date())
        assert df is None and reason == "rate_limit_or_throttle"

    def test_chain_raising_timeout_is_vendor_or_network_error(self, monkeypatch):
        client = self._client()
        monkeypatch.setattr(client, "spot", lambda sym: 100.0)
        def _raise(sym, spot, asof):
            raise requests.exceptions.Timeout("slow")
        monkeypatch.setattr(client, "_fetch_raw_results", _raise)
        df, reason = client._one_chain("XYZ", ASOF.date())
        assert df is None and reason == "vendor_or_network_error"

    def test_empty_vendor_results_is_raw_chain_empty(self, monkeypatch):
        client = self._client()
        monkeypatch.setattr(client, "spot", lambda sym: 100.0)
        monkeypatch.setattr(client, "_fetch_raw_results", lambda sym, spot, asof: [])
        df, reason = client._one_chain("XYZ", ASOF.date())
        assert df is None and reason == "raw_chain_empty"

    def test_nonempty_raw_emptied_by_the_filter_is_parse_or_filter_empty(self, monkeypatch):
        client = self._client()
        monkeypatch.setattr(client, "spot", lambda sym: 100.0)
        # strike wildly outside the +/-30% window -> parse_chain drops it; raw was nonempty
        far = [{"details": {"strike_price": 100000.0, "expiration_date": "2026-07-15",
                            "contract_type": "call", "ticker": "O:XYZ"},
               "open_interest": 10, "day": {"volume": 1}}]
        monkeypatch.setattr(client, "_fetch_raw_results", lambda sym, spot, asof: far)
        df, reason = client._one_chain("XYZ", ASOF.date())
        assert df is None and reason == "parse_or_filter_empty"

    def test_a_clean_success_returns_the_df_and_no_reason(self, monkeypatch):
        client = self._client()
        monkeypatch.setattr(client, "spot", lambda sym: 100.0)
        good = [{"details": {"strike_price": 100.0, "expiration_date": "2026-07-15",
                             "contract_type": "call", "ticker": "O:XYZ"},
                "open_interest": 10, "day": {"volume": 1}}]
        monkeypatch.setattr(client, "_fetch_raw_results", lambda sym, spot, asof: good)
        df, reason = client._one_chain("XYZ", ASOF.date())
        assert reason is None
        assert not df.empty

    def test_the_secret_never_reaches_the_log_on_a_spot_failure(self, monkeypatch, caplog):
        client = self._client()
        def _raise(sym):
            raise _http_error(
                403, "403 Client Error: Forbidden for url: https://api.polygon.io/v2/"
                     "snapshot/locale/us/markets/stocks/tickers/XYZ?apiKey=SECRETVALUE123")
        monkeypatch.setattr(client, "spot", _raise)
        with caplog.at_level(logging.WARNING, logger="collectors.polygon_options"):
            df, reason = client._one_chain("XYZ", ASOF.date())
        assert reason == "auth_or_entitlement_failure"
        assert "SECRETVALUE123" not in "\n".join(caplog.messages)


# ═══════════════ auth short-circuit probe (snapshot()) ═══════════════════════════

class TestAuthShortCircuit:
    def _client(self):
        client = PolygonOptions()
        client.key = "TESTKEY"
        client.cfg = {**client.cfg, "workers": 1}   # serial: deterministic call order
        return client

    def test_five_consecutive_auth_failures_abort_the_rest(self, monkeypatch):
        client = self._client()
        symbols = [f"S{i}" for i in range(10)]
        calls: list[str] = []

        def fake_one_chain(sym, asof):
            calls.append(sym)
            return None, "auth_or_entitlement_failure"

        monkeypatch.setattr(client, "_one_chain", fake_one_chain)
        raw, census = client.snapshot(symbols, ASOF.date())
        assert raw.empty
        assert census["aborted_early"] is True
        assert census["attempted_underlyings"] == AUTH_SHORT_CIRCUIT_PROBE
        assert calls == symbols[:AUTH_SHORT_CIRCUIT_PROBE], (
            "only the first probe-sized batch may be attempted")
        assert census["failure_reasons"] == {
            "auth_or_entitlement_failure": AUTH_SHORT_CIRCUIT_PROBE}

    def test_four_consecutive_auth_failures_do_not_abort(self, monkeypatch):
        client = self._client()
        symbols = [f"S{i}" for i in range(10)]

        def fake_one_chain(sym, asof):
            idx = symbols.index(sym)
            if idx < 4:
                return None, "auth_or_entitlement_failure"
            if idx == 4:
                return None, "raw_chain_empty"       # the 5th is a DIFFERENT failure
            return pd.DataFrame({"underlying": [sym]}), None

        monkeypatch.setattr(client, "_one_chain", fake_one_chain)
        raw, census = client.snapshot(symbols, ASOF.date())
        assert census["aborted_early"] is False
        assert census["attempted_underlyings"] == 10, (
            "four auth failures alone must not truncate the universe")

    def test_a_success_among_the_first_five_disables_the_short_circuit(self, monkeypatch):
        client = self._client()
        symbols = [f"S{i}" for i in range(10)]

        def fake_one_chain(sym, asof):
            idx = symbols.index(sym)
            if idx == 2:
                return pd.DataFrame({"underlying": [sym], "K": [1.0]}), None
            if idx < 5:
                return None, "auth_or_entitlement_failure"
            return pd.DataFrame({"underlying": [sym], "K": [1.0]}), None

        monkeypatch.setattr(client, "_one_chain", fake_one_chain)
        raw, census = client.snapshot(symbols, ASOF.date())
        assert census["aborted_early"] is False
        assert census["attempted_underlyings"] == 10
        assert census["successful_underlyings"] == 6

    def test_a_universe_smaller_than_the_probe_is_never_aborted(self, monkeypatch):
        """Nothing remains to abort when the whole universe is under probe size —
        every symbol is attempted regardless of how they fail."""
        client = self._client()
        symbols = ["S0", "S1", "S2"]
        monkeypatch.setattr(client, "_one_chain",
                            lambda sym, asof: (None, "auth_or_entitlement_failure"))
        raw, census = client.snapshot(symbols, ASOF.date())
        assert census["aborted_early"] is False
        assert census["attempted_underlyings"] == 3


# ═══════════════ collectors/base.py secret sanitizer ═════════════════════════════

def test_safe_exc_text_redacts_api_key_and_query_tail():
    exc = requests.HTTPError(
        "403 Client Error: Forbidden for url: https://api.polygon.io/v3/snapshot/"
        "options/AAPL?apiKey=SECRETVALUE123&limit=250")
    out = safe_exc_text(exc)
    assert "SECRETVALUE123" not in out
    assert "apiKey=SECRETVALUE123" not in out
    assert "?apiKey=SECRETVALUE123&limit=250" not in out


def test_retry_warning_log_line_never_emits_the_raw_api_key(monkeypatch, caplog):
    """The actual leak vector this hardens: `Adapter.http_get`'s retry-warning
    line already strips the query from its own `url` argument
    (``url.split("?")[0]``), but the interpolated EXCEPTION carries the full URL
    — apiKey and all — via `requests`' own error rendering. A synthetic 403 with
    a SECRETVALUE123-style key stands in for a real credential."""
    class _FakeAdapter(Adapter):
        name = "fake_polygon_like"
        group = "fake"

    adapter = _FakeAdapter()

    class _Resp403:
        status_code = 403

        def raise_for_status(self):
            raise requests.HTTPError(
                "403 Client Error: Forbidden for url: https://api.polygon.io/v3/"
                "snapshot/options/AAPL?apiKey=SECRETVALUE123",
                response=self)

    monkeypatch.setattr(requests, "get", lambda *a, **kw: _Resp403())
    with caplog.at_level(logging.WARNING, logger="collectors.base"):
        with pytest.raises(requests.HTTPError):
            adapter.http_get("https://api.polygon.io/v3/snapshot/options/AAPL",
                             retries=1, backoff_base=0.001)
    text = "\n".join(caplog.messages)
    assert "SECRETVALUE123" not in text, text
    assert "?apiKey=" not in text, text


# ═══════════════ census arithmetic + dynamic denominator ═════════════════════════

def test_census_denominator_is_dynamic_not_hardcoded(tmp_path, monkeypatch):
    """requested_underlyings must always be the CURRENT engine.options_universe.
    gex_symbols() resolution, never a hard-coded constant — proven by mocking it
    at two different sizes across two accruals."""
    import engine.options_universe as eou
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY", "QQQ"])
    raw2 = _raw(("SPY",))
    monkeypatch.setattr(bpg, "PolygonOptions",
                        lambda: _FakeClient(raw2, census=_census(raw2, ["SPY", "QQQ"])))
    res1 = bpg.accrue(date(2026, 6, 15))
    assert res1["census"]["requested_underlyings"] == 2
    assert res1["census"]["coverage_pct"] == 0.5

    monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"S{i}" for i in range(20)])
    raw20 = _raw(tuple(f"S{i}" for i in range(15)))
    all20 = [f"S{i}" for i in range(20)]
    monkeypatch.setattr(bpg, "PolygonOptions",
                        lambda: _FakeClient(raw20, census=_census(raw20, all20)))
    res2 = bpg.accrue(date(2026, 6, 16))
    assert res2["census"]["requested_underlyings"] == 20
    assert res2["census"]["coverage_pct"] == 0.75


def test_accrue_zero_capture_reports_empty_status_with_health_and_census(tmp_path, monkeypatch):
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    census = {
        "attempted_underlyings": 5, "successful_underlyings": 0,
        "failure_reasons": {"auth_or_entitlement_failure": 5},
        "failure_examples": {"auth_or_entitlement_failure": ["A", "B", "C"]},
        "aborted_early": True,
    }
    monkeypatch.setattr(bpg, "PolygonOptions",
                        lambda: _FakeClient(pd.DataFrame(), census=census))
    res = bpg.accrue(ASOF.date())
    assert res["status"] == "empty"
    assert res["health"] == "failed"
    assert res["census"]["failure_reasons"] == {"auth_or_entitlement_failure": 5}
    assert res["census"]["aborted_early"] is True
    chains_dir = tmp_path / "polygon_gex" / "chains"
    assert not list(chains_dir.glob("*.parquet"))
    receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
    assert receipt["attempts"][-1]["health"] == "failed"
    assert receipt["attempts"][-1]["decision"] == "skipped_not_better"


# ═══════════════ health verdict boundary (SOURCE_HEALTH_FLOOR = 0.90) ════════════

class TestHealthVerdict:
    def test_exactly_the_floor_is_healthy(self):
        import scripts.build_polygon_gex as bpg
        assert bpg._health_verdict(0.90, 100) == "healthy"

    def test_just_under_the_floor_is_partial(self):
        import scripts.build_polygon_gex as bpg
        assert bpg._health_verdict(0.8999, 100) == "partial"

    def test_zero_rows_is_failed_regardless_of_coverage_pct(self):
        import scripts.build_polygon_gex as bpg
        assert bpg._health_verdict(1.0, 0) == "failed"

    def test_full_coverage_with_rows_is_healthy(self):
        import scripts.build_polygon_gex as bpg
        assert bpg._health_verdict(1.0, 50) == "healthy"


# ═══════════════ first-writer QUALITY RULE (health receipt decision matrix) ══════

def _write_chain_file(tmp_path, session_iso, symbols=("SPY",)):
    d = tmp_path / "polygon_gex" / "chains"
    d.mkdir(parents=True, exist_ok=True)
    _raw(symbols).to_parquet(d / f"{session_iso}.parquet")


def _write_receipt_file(tmp_path, session_iso, attempts):
    d = tmp_path / "polygon_gex_health"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session_iso}.json").write_text(
        json.dumps({"session": session_iso, "attempts": attempts}))


def _entry(decision, health, successful, coverage_pct, requested=100):
    return {
        "capture_instant": "2026-06-14T21:00:00+00:00",
        "requested_underlyings": requested,
        "attempted_underlyings": requested,
        "successful_underlyings": successful,
        "coverage_pct": coverage_pct,
        "failure_reasons": {},
        "decision": decision,
        "health": health,
    }


class _NoFetchClient:
    """Fails the test loudly if snapshot() is ever called — for asserting the
    immutable-skip path spends no API quota."""

    def enabled(self):
        return True

    def snapshot(self, symbols, asof):
        raise AssertionError("snapshot() must not be called for an immutable session")


class TestFirstWriterQualityRule:
    def test_healthy_stored_session_is_immutable_and_skips_the_fetch(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "healthy", 300, 0.95, requested=316)])
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(date(2026, 6, 15))
        assert res["status"] == "already_present"

        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert len(receipt["attempts"]) == 2
        assert receipt["attempts"][-1]["decision"] == "skipped_already_healthy"
        assert receipt["attempts"][-1]["health"] == "healthy"
        # the carried-forward numbers reflect the stored write, not a fresh capture
        assert receipt["attempts"][-1]["successful_underlyings"] == 300

    def test_no_stored_file_writes_on_any_nonempty_capture(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))
        res = bpg.accrue(date(2026, 6, 15))
        assert res["status"] == "ok"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "wrote"

    def test_legacy_chain_with_no_receipt_is_immutable(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _write_chain_file(tmp_path, "2026-06-15")     # a parquet with NO receipt at all
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(date(2026, 6, 15))
        assert res["status"] == "already_present"

        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert len(receipt["attempts"]) == 1
        assert receipt["attempts"][0]["decision"] == "skipped_already_healthy"
        assert receipt["attempts"][0]["health"] == "healthy"

    def test_force_overrides_a_healthy_stored_session(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "healthy", 300, 0.95, requested=316)])
        raw = _raw(("SPY", "QQQ"))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY", "QQQ"])))
        res = bpg.accrue(date(2026, 6, 15), force=True)
        assert res["status"] == "ok"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "forced"

    def test_partial_replaced_when_coverage_jumps_at_least_10_points(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        import engine.options_universe as eou
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])
        new_raw = _raw(tuple(f"U{i}" for i in range(65)))     # 65 successful, still < 90%
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))
        res = bpg.accrue(date(2026, 6, 15))
        assert res["status"] == "ok"
        assert res["health"] == "partial"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert set(back["underlying"]) == set(f"U{i}" for i in range(65)), (
            "replacement must be a single-vintage overwrite, never a merge")

    def test_partial_replaced_when_the_new_capture_reaches_healthy(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        import engine.options_universe as eou
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])
        new_raw = _raw(tuple(f"U{i}" for i in range(95)))     # 95% -> healthy
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))
        res = bpg.accrue(date(2026, 6, 15))
        assert res["health"] == "healthy"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"

    def test_partial_not_replaced_when_the_improvement_is_under_10_points(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        import engine.options_universe as eou
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])
        new_raw = _raw(tuple(f"U{i}" for i in range(55)))     # +5 successful, +5pt coverage
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))
        res = bpg.accrue(date(2026, 6, 15))
        assert res["status"] == "already_present"
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert len(back) == len(_raw(("SPY",))), "the ORIGINAL stored file must be untouched"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_not_better"

    def test_partial_not_replaced_when_successful_count_does_not_strictly_exceed(
            self, tmp_path, monkeypatch):
        """A smaller, shrunk universe can make coverage_pct LOOK better even with
        FEWER successful underlyings — the rule requires successful_underlyings to
        strictly exceed the stored count regardless of what coverage_pct alone says."""
        import scripts.build_polygon_gex as bpg
        import engine.options_universe as eou
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(60)])
        new_raw = _raw(tuple(f"U{i}" for i in range(48)))     # 48 < 50 stored, coverage 0.80
        all_syms = [f"U{i}" for i in range(60)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))
        res = bpg.accrue(date(2026, 6, 15))
        assert res["status"] == "already_present"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_not_better"

    def test_receipt_grows_by_one_attempt_per_run_including_noop_runs(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        import engine.options_universe as eou
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))

        res1 = bpg.accrue(date(2026, 6, 15))
        assert res1["status"] == "ok"
        assert res1["health"] == "healthy"     # 1/1 requested -> full coverage
        res2 = bpg.accrue(date(2026, 6, 15))    # healthy -> immediate skip, no fetch
        assert res2["status"] == "already_present"
        res3 = bpg.accrue(date(2026, 6, 15))
        assert res3["status"] == "already_present"

        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert len(receipt["attempts"]) == 3
        assert [a["decision"] for a in receipt["attempts"]] == [
            "wrote", "skipped_already_healthy", "skipped_already_healthy"]

    def test_health_receipt_write_is_atomic_no_stray_tmp_files(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        import engine.options_universe as eou
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))
        bpg.accrue(date(2026, 6, 15))
        bpg.accrue(date(2026, 6, 15))
        health_dir = tmp_path / "polygon_gex_health"
        leftovers = [p.name for p in health_dir.iterdir() if p.suffix == ".tmp"]
        assert not leftovers, leftovers
        # the file must be valid JSON at every step, not a half-written tmp
        json.loads((health_dir / "2026-06-15.json").read_text())
