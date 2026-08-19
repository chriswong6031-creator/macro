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
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
import requests

import engine.options_universe as eou
from collectors.base import Adapter, redact_secrets, safe_exc_text
from collectors.polygon_options import (
    AUTH_SHORT_CIRCUIT_PROBE,
    REASON_CODES,
    PolygonOptions,
    _auth_probe_symbols,
    _classify_exception,
    parse_chain,
)
from lib import config

ASOF = pd.Timestamp("2026-06-15")


def _mock_baskets(monkeypatch, members=("PLACEHOLDER",)):
    """Every accrue() test below runs against the REAL config.yml, whose
    polygon.gex.include_baskets is True — so without this, B2's universe-
    degradation gate (AD-1C0 review) fires on EVERY test that doesn't
    explicitly exercise it, since a fresh tmp_path never has a real
    data/baskets/membership.json. Tests that specifically test B2 mock
    baskets_universe() to return [] themselves instead of calling this."""
    monkeypatch.setattr(eou, "baskets_universe", lambda: list(members))


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
    _mock_baskets(monkeypatch)
    monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY", "QQQ"])
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
    # on the plain happy path. m15: exact value, not a tautological "any of the
    # three" — 2 of 2 requested is full coverage, so this must be "healthy".
    assert res["health"] == "healthy"
    assert res["census"]["successful_underlyings"] == 2
    assert res["census"]["requested_underlyings"] == 2
    assert res["census"]["coverage_pct"] == 1.0
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
    _mock_baskets(monkeypatch)
    monkeypatch.setattr(bpg, "PolygonOptions",
                        lambda: _LegacyFakeClient(_raw(("SPY", "QQQ"))))
    res = bpg.accrue(ASOF.date())
    assert res["status"] == "ok"
    assert res["census"]["successful_underlyings"] == 2
    assert res["census"]["aborted_early"] is False


def test_accrue_raises_on_a_snapshot_return_shape_it_does_not_recognize(tmp_path, monkeypatch):
    """m17: snapshot() returning anything other than a (df, census) tuple or a
    bare DataFrame is a hard programming error, not a shape to silently paper
    over — a None/list/string must raise TypeError, never be treated as raw
    chain data (which would crash confusingly deep inside pandas instead)."""
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _mock_baskets(monkeypatch)

    class _WeirdClient:
        def enabled(self):
            return True

        def snapshot(self, symbols, asof):
            return "not a dataframe or a tuple"

    monkeypatch.setattr(bpg, "PolygonOptions", lambda: _WeirdClient())
    with pytest.raises(TypeError):
        bpg.accrue(ASOF.date())


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
        # "Sol's list is 'at least'" (B2 ruling) — universe_resolution_failed is
        # a documented, legitimate RUN-level amendment to the per-symbol set.
        assert REASON_CODES == frozenset({
            "no_spot", "auth_or_entitlement_failure", "rate_limit_or_throttle",
            "vendor_or_network_error", "raw_chain_empty", "parse_or_filter_empty",
            "other_failure", "universe_resolution_failed",
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


# B1 (AD-1C0 adversarial review): parse_chain used to run OUTSIDE the classified
# try/except in _one_chain — one malformed vendor contract (a string strike, a
# bad expiry token, a non-numeric OI) raised straight out and crashed the WHOLE
# snapshot() through ex.map, taking down every OTHER symbol's already-fetched
# result with it. These prove a single bad symbol degrades to (None, reason)
# instead, in BOTH the serial and threaded dispatch paths.

_BAD_STRIKE = [{"details": {"strike_price": "100.0",     # vendor returns a STRING
                            "expiration_date": "2026-07-15",
                            "contract_type": "call", "ticker": "O:BAD"},
               "open_interest": 10, "day": {"volume": 1}}]
_BAD_EXPIRY = [{"details": {"strike_price": 100.0,
                            "expiration_date": "not-a-date",   # unparseable token
                            "contract_type": "call", "ticker": "O:BAD"},
               "open_interest": 10, "day": {"volume": 1}}]
_BAD_OI = [{"details": {"strike_price": 100.0, "expiration_date": "2026-07-15",
                        "contract_type": "call", "ticker": "O:BAD"},
           "open_interest": "not-a-number", "day": {"volume": 1}}]
_GOOD = [{"details": {"strike_price": 100.0, "expiration_date": "2026-07-15",
                      "contract_type": "call", "ticker": "O:GOOD"},
         "open_interest": 10, "day": {"volume": 1}}]


class TestMalformedVendorContractsDoNotCrashTheSnapshot:
    @pytest.mark.parametrize("bad_results,label", [
        (_BAD_STRIKE, "string strike"),
        (_BAD_EXPIRY, "unparseable expiry"),
        (_BAD_OI, "non-numeric OI"),
    ])
    def test_one_chain_classifies_rather_than_raising(self, monkeypatch, bad_results, label):
        client = PolygonOptions()
        client.key = "TESTKEY"
        monkeypatch.setattr(client, "spot", lambda sym: 100.0)
        monkeypatch.setattr(client, "_fetch_raw_results",
                            lambda sym, spot, asof: bad_results)
        df, reason = client._one_chain("BADSYM", date(2026, 6, 15))
        assert df is None, label
        assert reason in REASON_CODES, label

    @pytest.mark.parametrize("workers", [1, 5], ids=["serial", "threaded"])
    def test_one_malformed_symbol_does_not_abort_the_others(self, monkeypatch, workers):
        client = PolygonOptions()
        client.key = "TESTKEY"
        client.cfg = {**client.cfg, "workers": workers}
        monkeypatch.setattr(client, "spot", lambda sym: 100.0)
        monkeypatch.setattr(
            client, "_fetch_raw_results",
            lambda sym, spot, asof: _BAD_STRIKE if sym == "BADSYM" else _GOOD)
        symbols = ["A", "B", "BADSYM", "D", "E", "F"]
        raw, census = client.snapshot(symbols, date(2026, 6, 15))
        assert census["attempted_underlyings"] == 6
        assert census["successful_underlyings"] == 5, (
            "one malformed symbol must not take down the other five")
        assert "BADSYM" not in set(raw["underlying"].astype(str))
        assert set(raw["underlying"].astype(str)) == {"A", "B", "D", "E", "F"}


# ═══════════════ auth short-circuit probe (snapshot()) ═══════════════════════════

class TestAuthShortCircuit:
    """M9 ruling (AD-1C0 review): the probe is a DETERMINISTIC MIXED-CLASS
    sample — first 3 of the universe order + last 2 — not the plain
    symbols[:5] anchors-only prefix, which could never see past an index/ETF-
    scoped entitlement gap to a working single-name tier."""

    def _client(self):
        client = PolygonOptions()
        client.key = "TESTKEY"
        client.cfg = {**client.cfg, "workers": 1}   # serial: deterministic call order
        return client

    def test_probe_set_is_first_3_plus_last_2(self):
        symbols = [f"S{i}" for i in range(10)]
        assert _auth_probe_symbols(symbols) == ["S0", "S1", "S2", "S8", "S9"]

    def test_a_universe_at_or_under_probe_size_probes_everything(self):
        symbols = ["S0", "S1", "S2", "S3"]
        assert _auth_probe_symbols(symbols) == symbols

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
        assert calls == _auth_probe_symbols(symbols), (
            "only the probe set may be attempted")
        assert census["failure_reasons"] == {
            "auth_or_entitlement_failure": AUTH_SHORT_CIRCUIT_PROBE}

    def test_four_of_five_probe_members_failing_auth_does_not_abort(self, monkeypatch):
        client = self._client()
        symbols = [f"S{i}" for i in range(10)]
        probe = _auth_probe_symbols(symbols)
        non_auth_member = probe[-1]     # the ONE probe member with a different failure

        def fake_one_chain(sym, asof):
            if sym == non_auth_member:
                return None, "raw_chain_empty"
            if sym in probe:
                return None, "auth_or_entitlement_failure"
            return pd.DataFrame({"underlying": [sym]}), None

        monkeypatch.setattr(client, "_one_chain", fake_one_chain)
        raw, census = client.snapshot(symbols, ASOF.date())
        assert census["aborted_early"] is False
        assert census["attempted_underlyings"] == 10, (
            "four probe auth failures alone must not truncate the universe")

    def test_a_success_anywhere_in_the_probe_disables_the_short_circuit(self, monkeypatch):
        client = self._client()
        symbols = [f"S{i}" for i in range(10)]
        probe = _auth_probe_symbols(symbols)
        success_sym = probe[0]

        def fake_one_chain(sym, asof):
            if sym == success_sym:
                return pd.DataFrame({"underlying": [sym], "K": [1.0]}), None
            if sym in probe:
                return None, "auth_or_entitlement_failure"
            return pd.DataFrame({"underlying": [sym], "K": [1.0]}), None

        monkeypatch.setattr(client, "_one_chain", fake_one_chain)
        raw, census = client.snapshot(symbols, ASOF.date())
        assert census["aborted_early"] is False
        assert census["attempted_underlyings"] == 10
        assert census["successful_underlyings"] == 6   # success_sym + the 5 non-probe

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

    def test_etf_scoped_403_does_not_abort_when_tail_single_names_succeed(self, monkeypatch):
        """M9's whole point: the OLD anchors-only probe (symbols[:5]) could
        never see past an index/ETF-scoped entitlement gap. Every FRONT anchor
        403s here, but the TAIL single names succeed — the short circuit must
        stand down instead of wrongly declaring the whole key de-entitled."""
        client = self._client()
        symbols = (["SPY", "QQQ", "IWM"] + [f"STK{i}" for i in range(20)]
                  + ["AAPL", "MSFT"])

        def fake_one_chain(sym, asof):
            if sym in ("SPY", "QQQ", "IWM"):
                return None, "auth_or_entitlement_failure"
            return pd.DataFrame({"underlying": [sym], "K": [1.0]}), None

        monkeypatch.setattr(client, "_one_chain", fake_one_chain)
        raw, census = client.snapshot(symbols, ASOF.date())
        assert census["aborted_early"] is False, (
            "the tail single names succeeding must disable the short circuit "
            "even though every front anchor 403'd")
        assert census["attempted_underlyings"] == len(symbols)


# ═══════════════ collectors/base.py secret sanitizer ═════════════════════════════

def test_safe_exc_text_redacts_api_key_and_query_tail():
    exc = requests.HTTPError(
        "403 Client Error: Forbidden for url: https://api.polygon.io/v3/snapshot/"
        "options/AAPL?apiKey=SECRETVALUE123&limit=250")
    out = safe_exc_text(exc)
    assert "SECRETVALUE123" not in out
    assert "apiKey=SECRETVALUE123" not in out
    assert "?apiKey=SECRETVALUE123&limit=250" not in out


# M6 (AD-1C0 adversarial review) — repro case D: every enumerated leak shape the
# original single "name=value" regex missed. Acceptance = every row passes with
# only the synthetic value surviving detection, never the secret itself.
_LEAK_CASES = {
    "bearer_header_repr":
        "401 Unauthorized: {'Authorization': 'Bearer sk_live_TOPSECRET'}",
    "key_in_path_segment":
        "403 Client Error for url: https://vendor.example/api/v1/"
        "sk_live_TOPSECRET/chain",
    "url_encoded_assignment":
        "403 for url: https://x/y%3FapiKey%3Dsk_live_TOPSECRET",
    "alt_param_name_access_key":
        "403 for url: https://x/y?access_key=sk_live_TOPSECRET",
    "alt_param_name_bare_key":
        "403 for url: https://x/y?key=sk_live_TOPSECRET",
    "password_param":
        "403 for url: https://x/y?password=sk_live_TOPSECRET",
    "space_separated_mention":
        "auth failed with api_key sk_live_TOPSECRET",
    "double_quoted_json_body":
        '{"error":"bad token","apiKey":"sk_live_TOPSECRET"}',
}


class TestSanitizerLeakShapes:
    @pytest.mark.parametrize("case", sorted(_LEAK_CASES), ids=sorted(_LEAK_CASES))
    def test_every_repro_d_row_is_redacted(self, case):
        out = safe_exc_text(requests.HTTPError(_LEAK_CASES[case]))
        assert "sk_live_TOPSECRET" not in out, (case, out)
        assert "TOPSECRET" not in out, (case, out)

    def test_redact_secrets_is_the_reusable_string_level_primitive(self):
        # safe_exc_text(exc) is a thin wrapper over redact_secrets(str(exc)) —
        # M5 reuses redact_secrets directly on non-exception text (tracebacks).
        assert redact_secrets("apiKey=SECRETVALUE123") == "apiKey=REDACTED"


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


def test_fetch_result_error_field_is_sanitized(monkeypatch, caplog):
    """M5 (AD-1C0 review): FetchResult.error lands in the TRACKED
    data/run_status.json via collect.py's asdict(r) — a raw credential must
    never reach a COMMITTED file, not just a log line. run_adapter's failure
    branch (base.py) builds `error=f"{type(e).__name__}: {e}"` from the raw
    fetch exception; both the persisted field and the logged traceback must be
    sanitized."""
    from collectors import base as _base
    from collectors.base import Adapter as _Adapter, run_adapter

    class _LeakyAdapter(_Adapter):
        name = "fake_leaky"
        group = "fake"

        def fetch(self, full_history: bool = False):
            raise requests.HTTPError(
                "403 Client Error: Forbidden for url: https://api.polygon.io/v3/"
                "snapshot/options/AAPL?apiKey=SECRETVALUE123")

    # Keep the test hermetic: run_adapter reads the circuit-breaker state from
    # the (fixed-path, non-tmp_path) run_status.json — stub both sides so
    # nothing here touches the real repo's data/.
    monkeypatch.setattr(_base, "_breaker_state", lambda: {})
    monkeypatch.setattr(_base, "_probe_state", lambda: {})

    adapter = _LeakyAdapter()
    with caplog.at_level(logging.ERROR, logger="collectors.base"):
        res = run_adapter(adapter)
    assert res.status == "failed"
    assert res.error is not None
    assert "SECRETVALUE123" not in res.error, res.error
    log_text = "\n".join(caplog.messages)
    assert "SECRETVALUE123" not in log_text, log_text
    assert "?apiKey=" not in log_text, log_text


# ═══════════════ census arithmetic + dynamic denominator ═════════════════════════

def test_census_denominator_is_dynamic_not_hardcoded(tmp_path, monkeypatch):
    """requested_underlyings must always be the CURRENT engine.options_universe.
    gex_symbols() resolution, never a hard-coded constant — proven by mocking it
    at two different sizes across two accruals."""
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _mock_baskets(monkeypatch)

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
    _mock_baskets(monkeypatch)
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
    # m13: zero-capture runs get "nothing_captured", never "skipped_not_better"
    # (that literal is reserved for a real comparison against a stored capture
    # this attempt failed to beat).
    assert receipt["attempts"][-1]["decision"] == "nothing_captured"
    # m10: aborted_early + failure_examples ride along in the receipt too, not
    # just in the in-memory census dict.
    assert receipt["attempts"][-1]["aborted_early"] is True
    assert receipt["attempts"][-1]["failure_examples"] == {
        "auth_or_entitlement_failure": ["A", "B", "C"]}


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


# M7's same-day vintage guard needs an explicit `_now` — the real wall clock
# would make every "replaced_partial" expectation below flip to
# "skipped_wrong_day" the moment this suite runs on any date other than
# 2026-06-15. 20:00 UTC on 2026-06-15 is 16:00 ET (EDT, UTC-4 in June) — the
# session close, and its ET calendar date is 2026-06-15.
SAME_DAY_NOW = datetime(2026, 6, 15, 20, 0, tzinfo=timezone.utc)
# The NEXT calendar day (2026-06-15 is a Monday session; 06-16 is Tuesday) —
# 06-16 12:00 UTC is 08:00 ET 06-16, a different ET calendar date entirely.
WRONG_DAY_NOW = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)


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
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "healthy", 300, 0.95, requested=316)])
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
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
        _mock_baskets(monkeypatch)
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "ok"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "wrote"

    def test_legacy_chain_with_no_receipt_is_immutable(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, "2026-06-15")     # a parquet with NO receipt at all
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "already_present"

        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert len(receipt["attempts"]) == 1
        assert receipt["attempts"][0]["decision"] == "skipped_already_healthy"
        assert receipt["attempts"][0]["health"] == "healthy"

    def test_force_overrides_a_healthy_stored_session(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "healthy", 300, 0.95, requested=316)])
        raw = _raw(("SPY", "QQQ"))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY", "QQQ"])))
        res = bpg.accrue(date(2026, 6, 15), force=True, _now=SAME_DAY_NOW)
        assert res["status"] == "ok"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "forced"

    def test_force_with_a_totally_failed_capture_does_not_mislabel_the_intact_store(
            self, tmp_path, monkeypatch):
        """M12 (AD-1C0 review): a --force run whose new capture is EMPTY must not
        make the store look 'failed' — the parquet is untouched (the zero-capture
        branch returns before any write), so the receipt's zero-capture attempt
        describes the REJECTED attempt, not the store. A reader must be able to
        recover the store's true health via the anchor lookup, not the bare last
        entry."""
        import scripts.build_polygon_gex as bpg
        from scripts.build_polygon_gex import _stored_state_entry
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "healthy", 300, 0.95, requested=316)])
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(pd.DataFrame(), census={
                                "attempted_underlyings": 316, "successful_underlyings": 0,
                                "failure_reasons": {}, "failure_examples": {},
                                "aborted_early": False}))
        res = bpg.accrue(date(2026, 6, 15), force=True, _now=SAME_DAY_NOW)
        assert res["status"] == "empty"
        # the chain parquet is completely untouched
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert set(back["underlying"]) == {"SPY"}
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "nothing_captured"
        assert receipt["attempts"][-1]["health"] == "failed"
        # ... but the anchor lookup still recovers the TRUE (unchanged) store health
        assert _stored_state_entry(receipt["attempts"])["health"] == "healthy"

    def test_partial_replaced_when_coverage_jumps_at_least_10_points(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])
        new_raw = _raw(tuple(f"U{i}" for i in range(65)))     # 65 successful, still < 90%
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "ok"
        assert res["health"] == "partial"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert set(back["underlying"]) == set(f"U{i}" for i in range(65)), (
            "replacement must be a single-vintage overwrite, never a merge")

    def test_partial_replaced_when_the_new_capture_reaches_healthy(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])
        new_raw = _raw(tuple(f"U{i}" for i in range(95)))     # 95% -> healthy
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["health"] == "healthy"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"

    def test_partial_not_replaced_when_the_improvement_is_under_10_points(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])
        new_raw = _raw(tuple(f"U{i}" for i in range(55)))     # +5 successful, +5pt coverage
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
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
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(60)])
        new_raw = _raw(tuple(f"U{i}" for i in range(48)))     # 48 < 50 stored, coverage 0.80
        all_syms = [f"U{i}" for i in range(60)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "already_present"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_not_better"

    def test_receipt_grows_by_one_attempt_per_run_including_noop_runs(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))

        res1 = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res1["status"] == "ok"
        assert res1["health"] == "healthy"     # 1/1 requested -> full coverage
        res2 = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)   # healthy -> immediate skip
        assert res2["status"] == "already_present"
        res3 = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res3["status"] == "already_present"

        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert len(receipt["attempts"]) == 3
        assert [a["decision"] for a in receipt["attempts"]] == [
            "wrote", "skipped_already_healthy", "skipped_already_healthy"]

    def test_health_receipt_write_is_atomic_no_stray_tmp_files(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))
        bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        health_dir = tmp_path / "polygon_gex_health"
        leftovers = [p.name for p in health_dir.iterdir() if p.suffix == ".tmp"]
        assert not leftovers, leftovers
        # the file must be valid JSON at every step, not a half-written tmp
        json.loads((health_dir / "2026-06-15.json").read_text())

    def test_m11_two_concurrent_writers_use_distinct_tmp_names(self, tmp_path, monkeypatch):
        """m11: the tmp filename carries a PID + UUID suffix so two writers for
        the SAME session can never collide on one tmp path (a bare '.tmp'
        suffix, the pre-fix shape, could not make this guarantee)."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        seen_tmp_names: list[str] = []
        orig_write_text = Path.write_text

        def _spy_write_text(self, *a, **kw):
            if ".tmp." in self.name:
                seen_tmp_names.append(self.name)
            return orig_write_text(self, *a, **kw)

        monkeypatch.setattr(Path, "write_text", _spy_write_text)
        bpg._append_health_attempt(date(2026, 6, 15), decision="wrote", health="healthy",
                                   census=_census(_raw(("SPY",)), ["SPY"]), now=SAME_DAY_NOW)
        bpg._append_health_attempt(date(2026, 6, 15), decision="skipped_already_healthy",
                                   health="healthy", census=None, now=SAME_DAY_NOW)
        assert len(seen_tmp_names) == 2
        assert len(set(seen_tmp_names)) == 2, seen_tmp_names
        for name in seen_tmp_names:
            assert f".{os.getpid()}." in name

    def test_atomicity_survives_a_crash_mid_write(self, tmp_path, monkeypatch):
        """m16: a crash injected AFTER the tmp file is written but BEFORE the
        rename must leave the ORIGINAL receipt completely intact — proving the
        atomicity claim by actually breaking the write, not just checking that
        a normal run leaves no litter behind."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "healthy", 10, 1.0, requested=10)])
        original_bytes = (tmp_path / "polygon_gex_health" / "2026-06-15.json").read_bytes()

        real_replace = Path.replace

        def _crash_on_replace(self, target):
            if self.name.startswith("2026-06-15.json.tmp."):
                raise OSError("simulated crash mid-write")
            return real_replace(self, target)

        monkeypatch.setattr(Path, "replace", _crash_on_replace)
        with pytest.raises(OSError):
            bpg._append_health_attempt(date(2026, 6, 15), decision="skipped_already_healthy",
                                       health="healthy", census=None, now=SAME_DAY_NOW)
        # the ORIGINAL file is byte-identical — the crash never touched it
        assert (tmp_path / "polygon_gex_health" / "2026-06-15.json").read_bytes() == original_bytes


class TestM7SameDayVintageGuard:
    """M7 ruling: a partial may be replaced ONLY when the new capture_instant's
    ET calendar date equals the session it is replacing — Saturday/Sunday/
    Monday-preopen re-runs all resolve to Friday's session but are not
    Friday, and must never keep "improving" a session days after its real
    capture window closed."""

    def _setup_partial(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])
        new_raw = _raw(tuple(f"U{i}" for i in range(70)))     # strictly better, +20pt
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))

    def test_same_et_calendar_day_replaces(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        self._setup_partial(tmp_path, monkeypatch)
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "ok"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"

    def test_the_next_et_calendar_day_does_not_replace(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        self._setup_partial(tmp_path, monkeypatch)
        res = bpg.accrue(date(2026, 6, 15), _now=WRONG_DAY_NOW)
        assert res["status"] == "already_present"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_wrong_day"
        # the attempt is RECORDED, not silently dropped
        assert receipt["attempts"][-1]["successful_underlyings"] == 70
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert set(back["underlying"]) == {"SPY"}, "the original stored file must be untouched"

    def test_a_weekend_utc_instant_that_still_resolves_to_the_same_et_day_replaces(
            self, tmp_path, monkeypatch):
        """The guard is about the ET CALENDAR date, not the UTC date — an
        instant just after midnight UTC on 06-16 that is still evening ET on
        06-15 (Monday) must still count as the SAME day."""
        import scripts.build_polygon_gex as bpg
        self._setup_partial(tmp_path, monkeypatch)
        still_monday_et = datetime(2026, 6, 16, 1, 0, tzinfo=timezone.utc)  # 21:00 ET 06-15
        res = bpg.accrue(date(2026, 6, 15), _now=still_monday_et)
        assert res["status"] == "ok"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"


class TestM8OrphanSummaryRows:
    def test_replaced_partial_drops_orphaned_summary_rows(self, tmp_path, monkeypatch):
        """M8 (AD-1C0 review): a replaced_partial write must not leave the OLD
        vintage's successful-but-now-absent symbols with a stale session row in
        their summary_<SYM>.parquet — that row would silently keep describing a
        chain snapshot the single-vintage overwrite just erased."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)

        # Capture 1: U0..U49 (50%, partial) — a real accrue() run so the summary
        # store is populated exactly as production would.
        raw1 = _raw(tuple(f"U{i}" for i in range(50)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw1, census=_census(raw1, universe)))
        r1 = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert r1["status"] == "ok" and r1["health"] == "partial"
        # U0's summary row exists at this session
        summ_u0_before = pd.read_parquet(tmp_path / "polygon_gex" / "summary_U0.parquet")
        assert pd.Timestamp("2026-06-15") in summ_u0_before.index

        # Capture 2: U20..U94 (75 names, +25pt, strictly better) — U0..U19 are
        # DROPPED from the new vintage.
        raw2 = _raw(tuple(f"U{i}" for i in range(20, 95)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw2, census=_census(raw2, universe)))
        r2 = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert r2["status"] == "ok"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"

        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert not any(f"U{i}" in set(back["underlying"].astype(str)) for i in range(20))

        orphans = []
        for i in range(20):
            p = tmp_path / "polygon_gex" / f"summary_U{i}.parquet"
            if p.exists():
                s = pd.read_parquet(p)
                if pd.Timestamp("2026-06-15") in s.index:
                    orphans.append(f"U{i}")
        assert not orphans, f"orphaned summary rows from the discarded vintage: {orphans}"

        # a symbol present in BOTH vintages (U30) keeps its row, refreshed
        summ_u30 = pd.read_parquet(tmp_path / "polygon_gex" / "summary_U30.parquet")
        assert pd.Timestamp("2026-06-15") in summ_u30.index


def _write_empty_membership(tmp_path):
    """B2 is scoped to membership_path.exists() — the file EXISTS but resolves
    to zero members (a genuine incident: corrupted/truncated content, or every
    member marked removed) — NOT merely absent (the ordinary state of a fresh
    test tmp_path, which must NOT trip this gate). Every B2 test writes this
    stub so the gate's precondition is met exactly as intended."""
    d = tmp_path / "baskets"
    d.mkdir(parents=True, exist_ok=True)
    (d / "membership.json").write_text(json.dumps({"baskets": {}}))


class TestB2UniverseResolutionDegradation:
    """B2 ruling (AD-1C0 review): fail CLOSED when include_baskets is true but
    the basket membership universe resolves to ZERO members — the pre-fix
    behaviour graded a collapsed (anchors-only) capture 100% coverage against
    its own wrong denominator, called it healthy, and froze the store there
    forever under the first-writer quality rule."""

    def test_empty_membership_refuses_to_fetch_or_write(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _write_empty_membership(tmp_path)
        monkeypatch.setattr(eou, "baskets_universe", lambda: [])   # the degraded universe
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY", "QQQ", "IWM"])
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "failed"
        assert res["health"] == "failed"
        assert res["census"]["failure_reasons"] == {"universe_resolution_failed": 1}
        assert not (tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet").exists()

        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "nothing_captured"
        assert receipt["attempts"][-1]["failure_reasons"] == {"universe_resolution_failed": 1}

    def test_a_stored_degraded_capture_never_becomes_permanently_immutable(
            self, tmp_path, monkeypatch):
        """The exact repro scenario: night 1 baskets are absent (collapse to 3
        anchors); WITHOUT the B2 gate this used to write a "100% coverage"
        capture, grade it healthy, and freeze forever. WITH the gate, night 1
        refuses to write at all, so the repair run (baskets restored) still has
        a clean 'no stored file' path to write the real capture into."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _write_empty_membership(tmp_path)

        # Night 1: baskets absent.
        monkeypatch.setattr(eou, "baskets_universe", lambda: [])
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY", "QQQ", "IWM"])
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())
        r1 = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert r1["status"] == "failed"
        assert not (tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet").exists()

        # Repair run: baskets restored, full universe, a real capture.
        full_universe = [f"U{i}" for i in range(316)]
        monkeypatch.setattr(eou, "baskets_universe", lambda: full_universe[10:])
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: full_universe)
        raw = _raw(tuple(full_universe[:300]))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, full_universe)))
        r2 = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert r2["status"] == "ok"
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert back["underlying"].nunique() == 300


class TestB2StoreShrinkTripwire:
    """B2 addendum ruling (coordinator, 2026-08-19): the membership-file check
    is deliberately blind to the file being simply ABSENT (the ordinary state
    of a fresh/dev/CI/sparse checkout). That exemption is the reviewer's real
    attack path: an absent membership file in a degraded/sparse/husk checkout
    would sail through unchecked. The store itself — the most recent PRIOR
    session's stamped underlying count — is the self-contained witness that
    closes it."""

    def test_a_large_prior_stored_chain_vs_a_shrunk_universe_refuses(
            self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        # A PRIOR session (the Friday before) stored 300 underlyings.
        _write_chain_file(tmp_path, "2026-06-12", symbols=tuple(f"U{i}" for i in range(300)))
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(10)])
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "failed"
        assert res["census"]["failure_reasons"] == {"universe_resolution_failed": 1}
        assert not (tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet").exists()
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "nothing_captured"
        assert receipt["attempts"][-1]["failure_reasons"] == {"universe_resolution_failed": 1}

    def test_a_mild_prior_shrink_proceeds_normally(self, tmp_path, monkeypatch):
        """12 -> 10 is a legitimate trim (factor 1.2x), well under the 3x
        tripwire threshold — must proceed and write normally, not refuse."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, "2026-06-12", symbols=tuple(f"U{i}" for i in range(12)))
        universe10 = [f"U{i}" for i in range(10)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe10)
        raw = _raw(tuple(universe10))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, universe10)))

        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "ok"
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert back["underlying"].nunique() == 10

    def test_a_fresh_environment_with_no_stored_chains_proceeds(self, tmp_path, monkeypatch):
        """No prior stored chain at all -> no reference -> the tripwire stays
        silent. This is what keeps every pinned unowned fixture (a fresh
        tmp_path, no stored chains before the first accrue()) untouched."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe10 = [f"U{i}" for i in range(10)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe10)
        raw = _raw(tuple(universe10))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, universe10)))

        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "ok"
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert back["underlying"].nunique() == 10


class TestB3CorruptReceiptRecovery:
    """B3 ruling (AD-1C0 review): fail toward IMMUTABILITY but never destroy
    evidence or mislabel a corrupt receipt as healthy."""

    def _corrupt(self, tmp_path, monkeypatch, *, successful=40, requested=100):
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe = [f"U{i}" for i in range(requested)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)
        _write_chain_file(tmp_path, "2026-06-15", symbols=tuple(f"U{i}" for i in range(successful)))
        good_receipt = json.dumps({
            "session": "2026-06-15",
            "attempts": [_entry("wrote", "partial", successful, successful / requested,
                                requested=requested)],
        })
        health_dir = tmp_path / "polygon_gex_health"
        health_dir.mkdir(parents=True, exist_ok=True)
        (health_dir / "2026-06-15.json").write_text(good_receipt[: len(good_receipt) // 2])
        return health_dir

    def test_corrupt_receipt_freezes_the_chain_immutable(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        self._corrupt(tmp_path, monkeypatch)
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "already_present", (
            "PIT protection: a corrupt receipt must freeze the store immutable, "
            "never silently allow a re-fetch/replace")

    def test_the_corrupt_file_is_preserved_aside_never_overwritten(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        health_dir = self._corrupt(tmp_path, monkeypatch)
        corrupt_bytes_before = (health_dir / "2026-06-15.json").read_bytes()
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())
        bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)

        asides = [p for p in health_dir.iterdir() if ".corrupt-" in p.name]
        assert len(asides) == 1, list(health_dir.iterdir())
        assert asides[0].read_bytes() == corrupt_bytes_before, (
            "the preserved copy must be byte-identical to the original corrupt file")

        # a SECOND run now reads the RECOVERED (valid) receipt normally — no new
        # corruption event fires, and the preserved evidence file is untouched.
        bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        asides_after = [p for p in health_dir.iterdir() if ".corrupt-" in p.name]
        assert len(asides_after) == 1, (
            "the corrupt-aside file must never be overwritten by a later run")
        assert asides_after[0].read_bytes() == corrupt_bytes_before

    def test_a_fresh_receipt_is_marked_receipt_recovered_and_never_healthy(
            self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        self._corrupt(tmp_path, monkeypatch)
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())
        bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)

        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][0]["decision"] == "receipt_recovered"
        assert receipt["attempts"][0]["health"] == "unknown_receipt_corrupt"
        assert receipt["attempts"][0]["prior_receipt_corrupt"] is True
        # NOWHERE in the receipt does health read "healthy" — the original B3
        # defect (corruption failing open to a healthy label).
        assert all(a.get("health") != "healthy" for a in receipt["attempts"]), receipt

    def test_the_gate_annotation_is_a_bare_line_start_warning(self, tmp_path, monkeypatch, capsys):
        import scripts.build_polygon_gex as bpg
        self._corrupt(tmp_path, monkeypatch)
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())
        bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        ann = [l for l in capsys.readouterr().out.splitlines() if "::" in l]
        assert ann and all(l.startswith("::") for l in ann), ann
        assert any("polygon-health-receipt" in l for l in ann)

    def test_a_missing_receipt_file_is_not_treated_as_corrupt(self, tmp_path, monkeypatch):
        """Sanity: the ABSENCE of a receipt (a brand-new or legacy session) must
        still be the ordinary rule-4 legacy-healthy path, not a corruption
        recovery — corruption is specifically a PARSE failure of a file that
        DOES exist."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, "2026-06-15")
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "already_present"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][0]["decision"] == "skipped_already_healthy"
        assert not any(".corrupt-" in p.name for p in
                       (tmp_path / "polygon_gex_health").iterdir())


class TestM14UnknownReasonCoercion:
    def test_an_unknown_failure_reason_is_folded_into_other_failure(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        census = {
            "attempted_underlyings": 3, "successful_underlyings": 0,
            "failure_reasons": {"totally_made_up_reason": 3},
            "failure_examples": {"totally_made_up_reason": ["A", "B"]},
            "aborted_early": False,
        }
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(pd.DataFrame(), census=census))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["census"]["failure_reasons"] == {"other_failure": 3}
        assert "totally_made_up_reason" not in res["census"]["failure_reasons"]
        assert res["census"]["failure_examples"]["other_failure"] == ["A", "B"]

    def test_a_mix_of_known_and_unknown_reasons_only_coerces_the_unknown_one(
            self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        census = {
            "attempted_underlyings": 4, "successful_underlyings": 0,
            "failure_reasons": {"auth_or_entitlement_failure": 2, "made_up": 2},
            "failure_examples": {}, "aborted_early": False,
        }
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(pd.DataFrame(), census=census))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["census"]["failure_reasons"] == {
            "auth_or_entitlement_failure": 2, "other_failure": 2}
