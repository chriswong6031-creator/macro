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
import math
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
from lib import config, nyse_calendar

ASOF = pd.Timestamp("2026-06-15")


def _mock_baskets(monkeypatch, members=("PLACEHOLDER",)):
    """Every accrue() test below runs against the REAL config.yml, whose
    polygon.gex.include_baskets is True — so without this, B2's universe-
    degradation gate (AD-1C0 review) fires on EVERY test that doesn't
    explicitly exercise it, since a fresh tmp_path never has a real
    data/baskets/membership.json. Tests that specifically test B2 mock
    baskets_universe() to return [] themselves instead of calling this."""
    monkeypatch.setattr(eou, "baskets_universe", lambda: list(members))


def _patch_include_baskets(monkeypatch, value: bool):
    """N1: override polygon.gex.include_baskets for one test without touching
    the real (lru_cache'd) config.load() result in place — shallow-copies just
    the nested dicts on the path being changed."""
    real_load = config.load

    def _patched():
        c = dict(real_load())
        polygon = dict(c["polygon"])
        gx = dict(polygon["gex"])
        gx["include_baskets"] = value
        polygon["gex"] = gx
        c["polygon"] = polygon
        return c

    monkeypatch.setattr(config, "load", _patched)


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
                # F2 (AD-1C0.1 boundary review): the ticker carries a C/P
                # marker, matching Polygon's real per-contract ticker (which
                # differs between a call and a put at the same strike) --
                # without it, the same-book proof's ticker-preferring join
                # key would collide a call and a put into one identity.
                rows.append(dict(underlying=sym, strike_ticker=f"O:{sym}{k}{'C' if call else 'P'}",
                                 expiry=ASOF + pd.Timedelta(days=30), K=float(k),
                                 T=30 / 365, is_call=call, oi=1000.0, iv=0.25,
                                 gamma=0.01, delta=0.5, volume=10.0, spot=spot, asof=ASOF))
    return pd.DataFrame(rows)


# F1 (AD-1C0.1 boundary review): non-dyadic (odd-cent) strikes -- the case
# where a STORED chain's float64->float32 downcast (_compact()) and a fresh
# CANDIDATE's un-downcast float64 land on different values for what is
# actually the same contract, if the same-book proof ever compares them
# asymmetrically.
_ODD_STRIKES = (100.01, 100.03, 123.45, 187.67, 55.13, 77.77, 99.99, 142.86,
                163.21, 171.43, 12.34, 23.56, 34.78, 45.91, 56.13, 67.35,
                78.57, 89.79, 111.11, 122.22, 133.33, 144.44)


def _raw_odd_strikes(symbols=("SPY",), oi=1000.0, spot=100.0):
    """Same shape as _raw(), but with _ODD_STRIKES instead of the integer
    80..120 grid -- _raw()'s dyadic strikes are exactly representable in
    float32, which masks any float32/float64 asymmetry in the same-book
    proof entirely regardless of whether the stored side was compacted."""
    rows = []
    for sym in symbols:
        for k in _ODD_STRIKES:
            for call in (True, False):
                rows.append(dict(underlying=sym, strike_ticker=f"O:{sym}{k}{'C' if call else 'P'}",
                                 expiry=ASOF + pd.Timedelta(days=30), K=float(k),
                                 T=30 / 365, is_call=call, oi=float(oi), iv=0.25,
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
    # AD-1C0.1 amendment 1 (Sol review 4989933857): the capture lease now
    # governs first writes too, so an explicit `_now` inside the lease for
    # this session is required — the real wall clock (this suite's default)
    # is nowhere near 2026-06-15 and would otherwise be refused outright.
    res = bpg.accrue(ASOF.date(), _now=SAME_DAY_NOW)
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

    # AD-1C0: the health-receipt sidecar is written next to the chain. B3
    # trigger-2's write-ahead sequence means a real write is TWO entries — a
    # "write_pending" appended before to_parquet, then the final "wrote".
    receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
    assert [a["decision"] for a in receipt["attempts"]] == ["write_pending", "wrote"]
    assert receipt["attempts"][-1]["decision"] == "wrote"

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
    # AD-1C0.1 amendment 1: first writes are now lease-gated too — see the
    # note in test_accrue_writes_raw_and_summary.
    res = bpg.accrue(ASOF.date(), _now=SAME_DAY_NOW)
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
    # AD-1C0.1 amendment 1: first writes are now lease-gated too — an
    # in-lease `_now` is required to reach the fetch (and thus the malformed
    # return) at all; see the note in test_accrue_writes_raw_and_summary.
    with pytest.raises(TypeError):
        bpg.accrue(ASOF.date(), _now=SAME_DAY_NOW)


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
        # workers=1: serial, deterministic call order. gex.symbols=["ANCHOR0"]
        # (n_anchors=1): snapshot() now reads its probe's n_anchors split from
        # THIS config (N3), so pin it small — any n_anchors from 0 up to
        # len(symbols)-2 yields the identical last-2 tail these tests were
        # already written against, since symbols[n_anchors:][-2:] ==
        # symbols[-2:] for any such split. Tests that specifically exercise
        # the n_anchors split override this per-test.
        client.cfg = {**client.cfg, "workers": 1,
                     "gex": {**client.cfg["gex"], "symbols": ["ANCHOR0"]}}
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

    # ── N3 (AD-1C0 round 2): the probe must not degenerate to all-ETF when
    # baskets are off ──────────────────────────────────────────────────────

    def test_probe_tail_uses_the_single_name_subset_when_nonempty(self):
        symbols = ["SPY", "QQQ", "IWM", "DIA", "NVDA"] + [f"STK{i}" for i in range(20)]
        # n_anchors=5 -> single_name_subset is the 20 STK basket tickers.
        assert _auth_probe_symbols(symbols, n_anchors=5) == symbols[:3] + symbols[-2:]

    def test_probe_tail_falls_back_to_positions_4_5_when_baskets_off(self):
        symbols = ["SPY", "QQQ", "IWM", "DIA", "NVDA", "AAPL", "TSLA", "AMD"]
        # n_anchors == len(symbols) -> baskets off, no single-name subset at all.
        assert _auth_probe_symbols(symbols, n_anchors=len(symbols)) == (
            symbols[:3] + symbols[4:6])
        assert _auth_probe_symbols(symbols, n_anchors=len(symbols)) == (
            ["SPY", "QQQ", "IWM", "NVDA", "AAPL"])

    def test_baskets_off_etf_scoped_403_does_not_abort(self, monkeypatch):
        """The integration path: with baskets OFF, PolygonOptions.snapshot()
        reads n_anchors from client.cfg["gex"]["symbols"] itself — n_anchors
        == len(symbols) here (no baskets appended) — so the probe tail must
        fall back to positions 4-5 (NVDA/AAPL) rather than re-picking more
        ETF anchors from the true tail of the (anchors-only) universe."""
        client = self._client()
        anchors = ["SPY", "QQQ", "IWM", "DIA", "NVDA", "AAPL", "TSLA", "AMD"]
        client.cfg = {**client.cfg, "gex": {**client.cfg["gex"], "symbols": anchors}}
        symbols = list(anchors)   # baskets off: the resolved universe IS the anchors

        def fake_one_chain(sym, asof):
            if sym in ("SPY", "QQQ", "IWM"):        # ETF-scoped 403 (the front 3)
                return None, "auth_or_entitlement_failure"
            return pd.DataFrame({"underlying": [sym], "K": [1.0]}), None

        monkeypatch.setattr(client, "_one_chain", fake_one_chain)
        raw, census = client.snapshot(symbols, ASOF.date())
        assert census["aborted_early"] is False, (
            "positions 4-5 (NVDA/AAPL) succeeding must disable the short "
            "circuit even with baskets off and the front 3 ETFs 403ing")
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


# M6/N4/N5 (AD-1C0 adversarial review, round 2) — repro case D plus the
# reviewer's follow-up leak shapes. N5 ruling: sanitizer test theater — one
# sk_-prefixed value covered 7/8 original rows through the TOKEN-PREFIX pass
# alone, silently NOT exercising the shape-specific passes each row claims to
# test. Every row below uses a secret value with NO sk_/pk_ prefix — so it can
# ONLY be caught by the pass that shape actually targets — EXCEPT
# "key_in_path_segment", which deliberately KEEPS the prefixed value: it is
# the one shape (a bare path segment, no adjacent keyword at all) that only
# _TOKEN_PREFIX_RE can catch, and it is what keeps that pass under live test
# coverage. Flip-verified by hand (see the packet): deleting _CRED_JSON_RE
# fails double_quoted_json_body/single_quoted_json_body/header_name_credential;
# deleting _BEARER_RE fails bearer_header_repr.
_NONPREFIXED_SECRET = "hunter2SECRETVALUE"
_PREFIXED_SECRET = "sk_live_TOPSECRET"

_LEAK_CASES = {
    "bearer_header_repr":
        f"401 Unauthorized: {{'Authorization': 'Bearer {_NONPREFIXED_SECRET}'}}",
    "key_in_path_segment":                                        # pins _TOKEN_PREFIX_RE
        f"403 Client Error for url: https://vendor.example/api/v1/"
        f"{_PREFIXED_SECRET}/chain",
    "url_encoded_assignment":
        f"403 for url: https://x/y%3FapiKey%3D{_NONPREFIXED_SECRET}",
    "alt_param_name_access_key":
        f"403 for url: https://x/y?access_key={_NONPREFIXED_SECRET}",
    "alt_param_name_bare_key":
        f"403 for url: https://x/y?key={_NONPREFIXED_SECRET}",
    "password_param":
        f"403 for url: https://x/y?password={_NONPREFIXED_SECRET}",
    "space_separated_mention":
        f"auth failed with api_key {_NONPREFIXED_SECRET}",
    "double_quoted_json_body":
        f'{{"error":"bad token","apiKey":"{_NONPREFIXED_SECRET}"}}',
    "single_quoted_json_body":                                    # N4(i)
        f"{{'error':'bad token','apiKey':'{_NONPREFIXED_SECRET}'}}",
    "header_name_credential":                                     # N4(ii)
        f"Headers: {{'X-API-Key': '{_NONPREFIXED_SECRET}'}}",
    "basic_auth_netloc":                                          # N4(iii)
        f"Connection failed: https://user:{_NONPREFIXED_SECRET}@vendor.example/api",
}

_LEAK_SECRETS = {name: (_PREFIXED_SECRET if name == "key_in_path_segment"
                        else _NONPREFIXED_SECRET)
                 for name in _LEAK_CASES}


class TestSanitizerLeakShapes:
    @pytest.mark.parametrize("case", sorted(_LEAK_CASES), ids=sorted(_LEAK_CASES))
    def test_every_repro_d_row_is_redacted(self, case):
        secret = _LEAK_SECRETS[case]
        out = safe_exc_text(requests.HTTPError(_LEAK_CASES[case]))
        assert secret not in out, (case, out)

    def test_only_one_row_relies_on_the_token_prefix_pass(self):
        """N5 sanity check: every OTHER row's secret value must not itself
        start with sk_/pk_ — otherwise a row claiming to test its own
        shape-specific pass could silently pass via _TOKEN_PREFIX_RE instead,
        exactly the theater N5 found."""
        for case, secret in _LEAK_SECRETS.items():
            if case == "key_in_path_segment":
                continue
            assert not secret.startswith(("sk_", "pk_")), (case, secret)

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
    # AD-1C0.1 amendment 1: first writes are now lease-gated too — an
    # in-lease `_now` per session is required; see the note in
    # test_accrue_writes_raw_and_summary.
    res1 = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
    assert res1["census"]["requested_underlyings"] == 2
    assert res1["census"]["coverage_pct"] == 0.5

    monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"S{i}" for i in range(20)])
    raw20 = _raw(tuple(f"S{i}" for i in range(15)))
    all20 = [f"S{i}" for i in range(20)]
    monkeypatch.setattr(bpg, "PolygonOptions",
                        lambda: _FakeClient(raw20, census=_census(raw20, all20)))
    res2 = bpg.accrue(date(2026, 6, 16),
                      _now=datetime(2026, 6, 16, 19, 0, tzinfo=nyse_calendar.ET))
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
    # AD-1C0.1 amendment 1: first writes are now lease-gated too; see the
    # note in test_accrue_writes_raw_and_summary.
    res = bpg.accrue(ASOF.date(), _now=SAME_DAY_NOW)
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


def test_zero_capture_emits_a_line_start_error_annotation(tmp_path, monkeypatch, capsys):
    """A total zero-capture must ALARM, not just file a receipt.

    Regression pin for the 2026-08-13→08-26 outage: the vendor key went
    401/403, every night filed a correct `nothing_captured`/`failed` receipt,
    and the lane stayed dark thirteen days because this branch only called
    log.warning(). capsys (not caplog) is deliberate — a logger cannot produce
    a GitHub annotation, so asserting on log records would re-green the exact
    defect. The `startswith("::")` check pins the DEFECT (Actions drops an
    annotation that does not start its line), never the wording."""
    import scripts.build_polygon_gex as bpg
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _mock_baskets(monkeypatch)
    census = {
        "attempted_underlyings": 5, "successful_underlyings": 0,
        "failure_reasons": {"auth_or_entitlement_failure": 5},
        "failure_examples": {"auth_or_entitlement_failure": ["SPY", "QQQ", "IWM"]},
        "aborted_early": True,
    }
    monkeypatch.setattr(bpg, "PolygonOptions",
                        lambda: _FakeClient(pd.DataFrame(), census=census))
    bpg.accrue(ASOF.date(), _now=SAME_DAY_NOW)

    ann = [ln for ln in capsys.readouterr().out.splitlines()
           if ln.startswith("::error title=polygon-accrual-dark::")]
    assert len(ann) == 1, "zero-capture must emit exactly one line-start ::error"
    # The dominant reason is the operator's whole diagnosis — without it the
    # alarm says "dark" but not "your vendor key is rejected".
    assert "auth_or_entitlement_failure" in ann[0]


def test_dominant_failure_reason_is_deterministic_on_ties():
    """Ties break on the code NAME so one outage renders one stable message."""
    import scripts.build_polygon_gex as bpg
    assert bpg._dominant_failure_reason({}) is None
    assert bpg._dominant_failure_reason({"failure_reasons": {}}) is None
    # A zero count is not a failure — it must never win the max().
    assert bpg._dominant_failure_reason(
        {"failure_reasons": {"no_spot": 0}}) is None
    assert bpg._dominant_failure_reason(
        {"failure_reasons": {"no_spot": 1, "auth_or_entitlement_failure": 7}}
    ) == "auth_or_entitlement_failure"
    tie = {"failure_reasons": {"vendor_or_network_error": 3, "no_spot": 3}}
    assert bpg._dominant_failure_reason(tie) == "vendor_or_network_error"
    assert bpg._dominant_failure_reason(tie) == "vendor_or_network_error"


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


def _entry(decision, health, successful, coverage_pct, requested=100, rows=None):
    """`rows` (C1, AD-1C0 round 4) is deliberately OMITTED by default — a
    write_pending entry with no "rows" field is the forward-safety
    "unverifiable" case. Tests exercising the VERIFIED-match path must pass
    the real raw row count explicitly (42 rows per symbol from _raw: 21
    strikes x calls+puts)."""
    out = {
        "capture_instant": "2026-06-14T21:00:00+00:00",
        "requested_underlyings": requested,
        "attempted_underlyings": requested,
        "successful_underlyings": successful,
        "coverage_pct": coverage_pct,
        "failure_reasons": {},
        "decision": decision,
        "health": health,
    }
    if rows is not None:
        out["rows"] = rows
    return out


# The AD-1C0.1 capture-lease/same-book-proof tests need an explicit `_now` —
# the real wall clock would make every "replaced_partial" expectation below
# flip to "skipped_outside_lease" the moment this suite runs on any date
# other than 2026-06-15. 19:00 ET on 2026-06-15 is safely past the 17:00 ET
# close+settle buffer, so nyse_calendar.expected_last_session resolves it to
# session 2026-06-15 ITSELF (a time inside the close-to-settle window, e.g.
# 16:xx ET, would resolve one session EARLIER — the lease's prong (a) reads
# that as "a different session", which is correct AD-1C0.1 behavior but
# would wrongly fail every fixture below that predates the lease and only
# ever cared about the ET CALENDAR date matching).
SAME_DAY_NOW = datetime(2026, 6, 15, 19, 0, tzinfo=nyse_calendar.ET)


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
        # AD-1C0.1: the stored chain's symbols must OVERLAP the replacement
        # candidate's (same-book proof) — U0..U49 matches the receipt's "50
        # successful" and is a subset of the new capture below, so the two
        # naturally share contracts with identical OI (fixed at 1000.0 by
        # _raw()), satisfying the proof without the test needing to know its
        # internals.
        _write_chain_file(tmp_path, "2026-06-15", symbols=tuple(f"U{i}" for i in range(50)))
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
        # AD-1C0.1: overlap the stored symbols with the replacement candidate
        # (same-book proof) — see the sibling test above for why.
        _write_chain_file(tmp_path, "2026-06-15", symbols=tuple(f"U{i}" for i in range(50)))
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
        # B3 trigger-2 write-ahead: the real write is TWO entries
        # (write_pending, then wrote); the two no-op re-runs are one each.
        assert len(receipt["attempts"]) == 4
        assert [a["decision"] for a in receipt["attempts"]] == [
            "write_pending", "wrote", "skipped_already_healthy", "skipped_already_healthy"]

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


# ═══════════ AD-1C0.1 — the bounded capture LEASE + same-book PROOF ═════════
#
# Sol's FROZEN SPEC (Option B, 2026-08-20) replaces the retired M7 same-ET-day
# predicate (_et_calendar_date / "skipped_wrong_day") with a bounded overnight
# LEASE (_within_capture_lease) plus an OI-intersection SAME-BOOK PROOF
# (_same_book_overlap), evaluated on TOP of the existing strictly-better
# quality prongs. The matrix below is the Sol-mandated §4 time-boundary suite.
#
# All instants are constructed directly in ET (nyse_calendar.ET) for
# readability — _within_capture_lease/expected_last_session accept any
# tzinfo and convert internally, so this is equivalent to (and clearer than)
# hand-converting to UTC.

LEASE_SESSION = date(2026, 8, 21)      # a plain Friday session, no holiday nearby
LEASE_FRI_EVENING = datetime(2026, 8, 21, 21, 0, tzinfo=nyse_calendar.ET)   # normal close evening
LEASE_SAT_0040 = datetime(2026, 8, 22, 0, 40, tzinfo=nyse_calendar.ET)      # post-midnight, in-lease
LEASE_SAT_0259 = datetime(2026, 8, 22, 2, 59, tzinfo=nyse_calendar.ET)      # boundary: passes
LEASE_SAT_0330 = datetime(2026, 8, 22, 3, 30, tzinfo=nyse_calendar.ET)      # boundary: fails
LEASE_SAT_1000 = datetime(2026, 8, 22, 10, 0, tzinfo=nyse_calendar.ET)      # Saturday mid-morning
LEASE_SUN_1200 = datetime(2026, 8, 23, 12, 0, tzinfo=nyse_calendar.ET)      # Sunday
LEASE_MON_0800 = datetime(2026, 8, 24, 8, 0, tzinfo=nyse_calendar.ET)       # Monday pre-open

HOLIDAY_SESSION = date(2026, 11, 25)   # Wednesday ahead of the Thanksgiving holiday
HOLIDAY_THU_0200 = datetime(2026, 11, 26, 2, 0, tzinfo=nyse_calendar.ET)    # inside the holiday, in-lease
HOLIDAY_FRI_0800 = datetime(2026, 11, 27, 8, 0, tzinfo=nyse_calendar.ET)    # early-close Fri, out-of-lease
HOLIDAY_FRI_1430 = datetime(2026, 11, 27, 14, 30, tzinfo=nyse_calendar.ET)  # early-close, pre-settle
HOLIDAY_FRI_1800 = datetime(2026, 11, 27, 18, 0, tzinfo=nyse_calendar.ET)   # early-close, post-settle

# STORED matches the receipt entries below ("50 successful of 100 requested")
# AND is a subset of every "strictly better" candidate raw frame used below,
# so the two naturally share contracts with IDENTICAL OI (_raw() fixes
# oi=1000.0 for every contract) — the same-book proof passes without any
# test needing to hand-construct an overlap.
STORED = tuple(f"U{i}" for i in range(50))


def _raw_with_oi_override(symbols, overrides, spot=100.0):
    """_raw()'s output with specific contracts' OI overridden. `overrides`
    maps (underlying, K, is_call) -> new oi value — the same-book PROOF
    mismatch tests need to change exactly one shared contract's OI while
    leaving every other contract identical to a plain _raw() capture."""
    df = _raw(symbols, spot=spot)
    for (sym, k, is_call), new_oi in overrides.items():
        mask = (df["underlying"] == sym) & (df["K"] == k) & (df["is_call"] == is_call)
        assert mask.any(), f"override target {(sym, k, is_call)} not found in _raw() output"
        df.loc[mask, "oi"] = new_oi
    return df


def _setup_stored_partial(tmp_path, monkeypatch, *, session_iso, stored_symbols,
                          universe_n=100):
    """A stored PARTIAL capture for `session_iso`: `stored_symbols` are on
    disk (a real parquet, via _write_chain_file) and the receipt agrees
    (len(stored_symbols) successful of universe_n requested). Returns the
    full universe (list of names) so the caller can build a census/raw frame
    against the same denominator."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    _mock_baskets(monkeypatch)
    universe = [f"U{i}" for i in range(universe_n)]
    monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)
    _write_chain_file(tmp_path, session_iso, symbols=stored_symbols)
    _write_receipt_file(tmp_path, session_iso,
                        [_entry("wrote", "partial", len(stored_symbols),
                                round(len(stored_symbols) / universe_n, 4),
                                requested=universe_n)])
    return universe


class TestAD1C01CaptureLease:
    """Sol's FROZEN SPEC §4 time-boundary matrix (AD-1C0.1, 2026-08-20). Each
    test below is numbered to match the commissioning packet's TESTS list."""

    def test_1_normal_close_evening_first_write(self, tmp_path, monkeypatch):
        """#1: no stored file at all -> any nonempty capture writes, at a
        normal evening capture instant. First-write behavior is UNCHANGED by
        AD-1C0.1 — the lease/proof machinery only ever gates a REPLACEMENT."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))
        res = bpg.accrue(LEASE_SESSION, _now=LEASE_FRI_EVENING)
        assert res["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "wrote"

    def test_2_post_midnight_healthier_capture_with_matching_oi_replaces(
            self, tmp_path, monkeypatch):
        """#2: a long nightly crossing 00:00 ET — partial at 21:00 ET, a
        healthier capture at 00:40 ET (still inside the overnight lease)
        whose overlapping contracts agree on OI -> replaced_partial."""
        import scripts.build_polygon_gex as bpg
        universe = _setup_stored_partial(tmp_path, monkeypatch,
                                         session_iso=LEASE_SESSION.isoformat(),
                                         stored_symbols=STORED)
        new_raw = _raw(tuple(f"U{i}" for i in range(70)))     # +20pt, strictly better
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))
        res = bpg.accrue(LEASE_SESSION, _now=LEASE_SAT_0040)
        assert res["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"

    def test_3_post_midnight_worse_capture_is_rejected_by_the_quality_prong(
            self, tmp_path, monkeypatch):
        """#3: same overnight window, but the new capture is WORSE than the
        stored one -> skipped_not_better. The quality prong is evaluated
        BEFORE the lease, so a worse capture never even reaches it."""
        import scripts.build_polygon_gex as bpg
        universe = _setup_stored_partial(tmp_path, monkeypatch,
                                         session_iso=LEASE_SESSION.isoformat(),
                                         stored_symbols=STORED)
        new_raw = _raw(tuple(f"U{i}" for i in range(30)))     # WORSE: 30 < 50 stored
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))
        res = bpg.accrue(LEASE_SESSION, _now=LEASE_SAT_0040)
        assert res["status"] == "already_present"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_not_better"

    def test_4_post_midnight_oi_disagreement_on_a_shared_contract_is_a_vintage_mismatch(
            self, tmp_path, monkeypatch):
        """#4: a strictly-better, lease-valid capture whose OI DISAGREES with
        the stored capture on one shared contract -> skipped_vintage_mismatch."""
        import scripts.build_polygon_gex as bpg
        universe = _setup_stored_partial(tmp_path, monkeypatch,
                                         session_iso=LEASE_SESSION.isoformat(),
                                         stored_symbols=STORED)
        new_raw = _raw_with_oi_override(
            tuple(f"U{i}" for i in range(70)), {("U5", 100.0, True): 4242.0})
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))
        res = bpg.accrue(LEASE_SESSION, _now=LEASE_SAT_0040)
        assert res["status"] == "already_present"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_vintage_mismatch"
        back = pd.read_parquet(
            tmp_path / "polygon_gex" / "chains" / f"{LEASE_SESSION.isoformat()}.parquet")
        assert set(back["underlying"]) == set(STORED), "the original stored file must be untouched"

    def test_5_disjoint_symbols_below_the_overlap_floor_is_unverifiable(
            self, tmp_path, monkeypatch):
        """#5: a strictly-better, lease-valid capture that shares essentially
        NO contracts with the stored capture -> skipped_unverifiable_vintage
        — there is not enough shared surface to prove OR disprove same-book."""
        import scripts.build_polygon_gex as bpg
        _setup_stored_partial(tmp_path, monkeypatch,
                              session_iso=LEASE_SESSION.isoformat(),
                              stored_symbols=STORED)
        v_universe = [f"V{i}" for i in range(100)]     # entirely different names
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: v_universe)
        new_raw = _raw(tuple(f"V{i}" for i in range(70)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, v_universe)))
        res = bpg.accrue(LEASE_SESSION, _now=LEASE_SAT_0040)
        assert res["status"] == "already_present"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_unverifiable_vintage"

    @pytest.mark.parametrize("label,instant", [
        ("saturday_10am", LEASE_SAT_1000),
        ("sunday_noon", LEASE_SUN_1200),
        ("monday_preopen", LEASE_MON_0800),
    ])
    def test_6_7_8_outside_the_overnight_lease_is_refused(
            self, tmp_path, monkeypatch, label, instant):
        """#6/#7/#8: a strictly-better capture whose capture_instant has
        rolled past the LEASE_END_ET_HOUR:00 boundary — Saturday mid-morning,
        Sunday, or Monday pre-open — is refused as skipped_outside_lease even
        though it is still the SAME resolved session (Friday) and would have
        passed the same-book proof had the lease not already refused it."""
        import scripts.build_polygon_gex as bpg
        universe = _setup_stored_partial(tmp_path, monkeypatch,
                                         session_iso=LEASE_SESSION.isoformat(),
                                         stored_symbols=STORED)
        new_raw = _raw(tuple(f"U{i}" for i in range(70)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))
        res = bpg.accrue(LEASE_SESSION, _now=instant)
        # AD-1C0.1 amendment 1+2 (Sol review 4989933857): the lease is now
        # enforced PRE-FETCH, before client.snapshot() is ever called — the
        # refusal short-circuits with its own "outside_lease" status rather
        # than falling through to the post-fetch "already_present" shape.
        assert res["status"] == "outside_lease", label
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_outside_lease", label
        assert receipt["attempts"][-1]["lease"]["valid"] is False, label
        assert receipt["attempts"][-1]["lease"]["write_kind"] == "replacement", label
        back = pd.read_parquet(
            tmp_path / "polygon_gex" / "chains" / f"{LEASE_SESSION.isoformat()}.parquet")
        assert set(back["underlying"]) == set(STORED), "the original stored file must be untouched"

    def test_9_wall_clock_boundary_0259_passes_0330_fails(self, tmp_path, monkeypatch):
        """#9: the wall-clock boundary is EXCLUSIVE at LEASE_END_ET_HOUR:00 —
        02:59 ET the next calendar day still leases (and, with a matching-OI
        strictly-better capture, replaces); 03:30 ET does not."""
        import scripts.build_polygon_gex as bpg
        # Passing side: 02:59 ET.
        universe = _setup_stored_partial(tmp_path, monkeypatch,
                                         session_iso=LEASE_SESSION.isoformat(),
                                         stored_symbols=STORED)
        new_raw = _raw(tuple(f"U{i}" for i in range(70)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))
        res_pass = bpg.accrue(LEASE_SESSION, _now=LEASE_SAT_0259)
        assert res_pass["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"

        # Failing side: a fresh, isolated stored-partial fixture (a different
        # Friday) captured at 03:30 ET the next calendar day.
        session2 = date(2026, 8, 28)
        universe2 = _setup_stored_partial(tmp_path, monkeypatch,
                                          session_iso=session2.isoformat(),
                                          stored_symbols=STORED)
        new_raw2 = _raw(tuple(f"U{i}" for i in range(70)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw2, census=_census(new_raw2, universe2)))
        instant_0330 = datetime(2026, 8, 29, 3, 30, tzinfo=nyse_calendar.ET)
        res_fail = bpg.accrue(session2, _now=instant_0330)
        # AD-1C0.1 amendment 1+2: pre-fetch refusal now returns its own
        # "outside_lease" status; see test_6_7_8's note.
        assert res_fail["status"] == "outside_lease"
        receipt2 = json.loads(
            (tmp_path / "polygon_gex_health" / f"{session2.isoformat()}.json").read_text())
        assert receipt2["attempts"][-1]["decision"] == "skipped_outside_lease"

    def test_10_holiday_adjacent_lease_endpoint_is_the_next_calendar_day_not_the_next_session(
            self, tmp_path, monkeypatch):
        """#10: a Wednesday session ahead of the Thanksgiving Thursday
        holiday leases only through Thursday (the holiday's OWN calendar
        day) 03:00 ET — a capture inside the holiday's small hours still
        replaces, but the early-close Friday morning capture does not, even
        though it resolves to the SAME Wednesday session. The lease boundary
        is a CALENDAR day, not a next-SESSION day."""
        import scripts.build_polygon_gex as bpg
        session = HOLIDAY_SESSION

        universe = _setup_stored_partial(tmp_path, monkeypatch,
                                         session_iso=session.isoformat(),
                                         stored_symbols=STORED)
        new_raw = _raw(tuple(f"U{i}" for i in range(70)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))
        res_pass = bpg.accrue(session, _now=HOLIDAY_THU_0200)
        assert res_pass["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{session.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"

        # Reset the fixture, then attempt again from early-close Friday
        # morning — resolves to the SAME session (Wed 11-25) but the lease
        # boundary (Thu 11-26 03:00 ET) has already passed; it does NOT roll
        # forward to Friday just because Thursday was a holiday.
        universe2 = _setup_stored_partial(tmp_path, monkeypatch,
                                          session_iso=session.isoformat(),
                                          stored_symbols=STORED)
        new_raw2 = _raw(tuple(f"U{i}" for i in range(70)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw2, census=_census(new_raw2, universe2)))
        res_fail = bpg.accrue(session, _now=HOLIDAY_FRI_0800)
        # AD-1C0.1 amendment 1+2: pre-fetch refusal now returns its own
        # "outside_lease" status; see test_6_7_8's note.
        assert res_fail["status"] == "outside_lease"
        receipt2 = json.loads(
            (tmp_path / "polygon_gex_health" / f"{session.isoformat()}.json").read_text())
        assert receipt2["attempts"][-1]["decision"] == "skipped_outside_lease"

    def test_11_early_close_day_resolution_is_unaffected_by_the_lease_change(
            self, tmp_path, monkeypatch):
        """#11: early closes are NOT modeled by nyse_calendar (the 17:00 ET
        settle boundary is unconditional) — a 14:30 ET capture on an early-
        close session day (the Friday after Thanksgiving) still resolves to
        the PRIOR session, exactly as before AD-1C0.1. Then a normal evening
        (post-settle) capture on THAT day writes normally, as a first write
        for its own session."""
        import scripts.build_polygon_gex as bpg
        resolved = bpg._resolve_session(HOLIDAY_FRI_1430)
        assert resolved == date(2026, 11, 25), (
            "14:30 ET on an early-close day must still resolve to the PRIOR "
            "session — the modeled settle boundary stays 17:00 ET regardless "
            "of the exchange's real (unmodeled) 13:00 ET early close")

        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))
        res = bpg.accrue(HOLIDAY_FRI_1800, _now=HOLIDAY_FRI_1800)
        assert res["status"] == "ok"
        assert res["session"] == "2026-11-27"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-11-27.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "wrote"

    def test_12_healthy_first_capture_stays_immutable_even_at_a_lease_valid_instant(
            self, tmp_path, monkeypatch):
        """#12: a stored HEALTHY session is immutable regardless of whether
        the new attempt's capture_instant would otherwise be lease-valid —
        the healthy-immutable check fires BEFORE the lease/proof machinery
        (and before any fetch) is ever consulted."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, LEASE_SESSION.isoformat(), symbols=("SPY", "QQQ"))
        _write_receipt_file(tmp_path, LEASE_SESSION.isoformat(),
                            [_entry("wrote", "healthy", 2, 1.0, requested=2)])
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(LEASE_SESSION, _now=LEASE_SAT_0040)   # a lease-valid instant
        assert res["status"] == "already_present"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_already_healthy"

    def test_13_force_bypasses_the_lease_and_proof_entirely(self, tmp_path, monkeypatch):
        """#13: --force overrides the lease and the same-book proof exactly
        as it already overrode the strictly-better quality prong — a capture
        OUTSIDE the lease, sharing NOTHING with the stored capture, still
        writes under --force, recorded as decision "forced"."""
        import scripts.build_polygon_gex as bpg
        _setup_stored_partial(tmp_path, monkeypatch,
                              session_iso=LEASE_SESSION.isoformat(),
                              stored_symbols=STORED)
        v_universe = [f"V{i}" for i in range(100)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: v_universe)
        new_raw = _raw(tuple(f"V{i}" for i in range(5)))     # tiny, disjoint, outside-lease
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, v_universe)))
        res = bpg.accrue(LEASE_SESSION, force=True, _now=LEASE_MON_0800)   # outside the lease
        assert res["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "forced"
        back = pd.read_parquet(
            tmp_path / "polygon_gex" / "chains" / f"{LEASE_SESSION.isoformat()}.parquet")
        assert set(back["underlying"]) == set(f"V{i}" for i in range(5))

    def test_14_single_vintage_invariant_and_orphan_cleanup_survive_a_lease_valid_replacement(
            self, tmp_path, monkeypatch):
        """#14: a lease-valid, same-book-proven replacement is still a
        single-vintage OVERWRITE (never a merge) and still triggers the M8
        orphan-summary cleanup for symbols the new vintage drops.

        Session is date(2026, 6, 15) — matching module-level ASOF, which
        _raw() bakes into every row's "asof" column regardless of the
        accrual session passed to accrue() — so the compute_gex summary
        rows land at the expected index."""
        import scripts.build_polygon_gex as bpg
        session = ASOF.date()
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)

        raw1 = _raw(tuple(f"U{i}" for i in range(50)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw1, census=_census(raw1, universe)))
        r1 = bpg.accrue(session, _now=SAME_DAY_NOW)
        assert r1["status"] == "ok" and r1["health"] == "partial"
        summ_u0_before = pd.read_parquet(tmp_path / "polygon_gex" / "summary_U0.parquet")
        assert pd.Timestamp(session) in summ_u0_before.index

        raw2 = _raw(tuple(f"U{i}" for i in range(20, 90)))    # U0..U19 dropped, same OI
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw2, census=_census(raw2, universe)))
        post_midnight = datetime(2026, 6, 16, 0, 40, tzinfo=nyse_calendar.ET)   # in-lease
        r2 = bpg.accrue(session, _now=post_midnight)
        assert r2["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{session.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"

        back = pd.read_parquet(
            tmp_path / "polygon_gex" / "chains" / f"{session.isoformat()}.parquet")
        assert set(back["underlying"]) == set(f"U{i}" for i in range(20, 90)), (
            "replacement must be a single-vintage overwrite, never a merge")

        orphans = []
        for i in range(20):
            p = tmp_path / "polygon_gex" / f"summary_U{i}.parquet"
            if p.exists():
                s = pd.read_parquet(p)
                if pd.Timestamp(session) in s.index:
                    orphans.append(f"U{i}")
        assert not orphans, f"orphaned summary rows from the discarded vintage: {orphans}"


class TestAD1C01BoundaryReviewRepairs:
    """AD-1C0.1 boundary review (2026-08-20): the lease/clock logic held
    every attack; the same-book proof had F1 (MAJOR, dtype asymmetry) + F2
    (identity collision) + F3 (vacuous empty-stored agreement) + F4 (no
    test biting lease prong (a) alone) + F5 (unreadable stored parquet
    untested). F7 (OI float32 lossiness) is covered by F1's fix and
    asserted inline in the F1 tests. F6 (exact-OI strictness) is accepted
    design — no test, see the code comment in _same_book_overlap."""

    def test_f1_odd_cent_strikes_end_to_end_replaces_with_consistent_oi(
            self, tmp_path, monkeypatch):
        """F1 (MAJOR): a REAL accrue()-written stored chain has been through
        _compact()'s float32 downcast of K/oi; the candidate returned by the
        fetch has not. Before the symmetric-coercion fix, an all-odd-cent-
        strike chain's overlap measured 0/44 and every lawful rescue was
        refused as skipped_unverifiable_vintage even though nothing about
        the book had changed. Prove the fix: an all-odd-strike, consistent-
        OI rescue still replaces end to end."""
        import scripts.build_polygon_gex as bpg
        session = ASOF.date()
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)

        raw1 = _raw_odd_strikes(tuple(f"U{i}" for i in range(50)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw1, census=_census(raw1, universe)))
        r1 = bpg.accrue(session, _now=SAME_DAY_NOW)
        assert r1["status"] == "ok" and r1["health"] == "partial"

        # Same OI (1000.0, untouched) on every odd-cent strike -- F7: this is
        # exactly the OI-comparison-survives-the-round-trip assertion, proven
        # by the replacement actually landing rather than a phantom mismatch.
        raw2 = _raw_odd_strikes(tuple(f"U{i}" for i in range(70)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw2, census=_census(raw2, universe)))
        post_midnight = datetime(2026, 6, 16, 0, 40, tzinfo=nyse_calendar.ET)   # in-lease
        r2 = bpg.accrue(session, _now=post_midnight)
        assert r2["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{session.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"

    def test_f1_odd_cent_strikes_oi_drift_is_a_vintage_mismatch(self, tmp_path, monkeypatch):
        """F1/F7: with the symmetric float32 round-trip in place, the proof
        now SEES odd-cent strikes well enough to catch a genuine OI drift on
        one of them -- proving the fix didn't just stop mis-refusing an
        unchanged book, it can still tell a REAL difference apart."""
        import scripts.build_polygon_gex as bpg
        session = ASOF.date()
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)

        raw1 = _raw_odd_strikes(tuple(f"U{i}" for i in range(50)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw1, census=_census(raw1, universe)))
        r1 = bpg.accrue(session, _now=SAME_DAY_NOW)
        assert r1["status"] == "ok"

        raw2 = _raw_odd_strikes(tuple(f"U{i}" for i in range(70)))
        drift_mask = ((raw2["underlying"] == "U5") & (raw2["K"] == _ODD_STRIKES[0])
                     & raw2["is_call"])
        assert drift_mask.any()
        raw2.loc[drift_mask, "oi"] = 4242.0     # ONE odd-cent contract's OI moved
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw2, census=_census(raw2, universe)))
        post_midnight = datetime(2026, 6, 16, 0, 40, tzinfo=nyse_calendar.ET)
        r2 = bpg.accrue(session, _now=post_midnight)
        assert r2["status"] == "already_present"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{session.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_vintage_mismatch"

    def test_f7_oi_near_the_float32_precision_boundary_survives_the_round_trip(
            self, tmp_path):
        """F7: OI values above float32's exact-integer range (~2^24) lose
        precision when the STORED side round-trips through _compact()'s
        float32 downcast at write time. Without the SAME coercion applied
        to the freshly-fetched CANDIDATE side, a real OI of, say,
        16,777,217 compares against the stored (silently rounded to
        16,777,216) value and reads as a genuine disagreement even though
        the vendor reported the identical real OI both times -- a false
        skipped_vintage_mismatch. This is the one case in the whole file
        where the strike/composite-key string comparison does NOT already
        paper over the missing coercion (unlike odd-cent strikes, which
        happen to round-trip through str() identically either way) -- so
        this is the test that actually depends on the explicit F1/F7
        astype("float32") calls, not just their side effects."""
        import scripts.build_polygon_gex as bpg
        big_oi = 16_777_217.0     # 2**24 + 1 -- not exactly representable in float32
        stored_raw = _raw(("SPY",))
        stored_raw["oi"] = big_oi
        p = tmp_path / "c.parquet"
        bpg._compact(stored_raw.copy()).to_parquet(p)
        stored = pd.read_parquet(p)
        # float() first: comparing a bare numpy float32 scalar directly
        # against a Python float can itself downcast the RHS under NEP-50
        # promotion rules and mask the very precision loss this assertion
        # is trying to confirm actually happened.
        assert float(stored["oi"].iloc[0]) != big_oi, (
            "the parquet round-trip must actually have LOST precision here, "
            "or this test isn't exercising the boundary case at all")

        candidate = _raw(("SPY",))
        candidate["oi"] = big_oi      # the vendor reports the SAME real OI, exactly
        agrees, overlap, floor, mismatches, *_ = bpg._same_book_overlap(stored, candidate)
        assert mismatches == 0
        assert agrees is True, (
            "the SAME real-world OI, rounded IDENTICALLY on both sides via "
            "the symmetric float32 cast, must agree -- an asymmetric "
            "comparison against the unrounded candidate would wrongly call "
            f"this a mismatch (overlap={overlap}, floor={floor})")

    def test_f2_order_swapped_duplicate_identity_still_agrees_via_ticker(self):
        """F2: the 4-field composite key (_CONTRACT_KEY_COLS) is not always
        unique -- an adjusted and a standard contract can share underlying/
        expiry/strike/right. Before the fix, drop_duplicates' positional
        "keep first" made a pure ORDER SWAP between two functionally-
        identical captures flip the verdict (reviewer repro: 'standard
        first' paired 1000-vs-1000, 'adjusted first' paired 1000-vs-7 --
        same two rows, opposite answer). With the vendor ticker as the
        PRIMARY key, the two distinctly-ticketed rows are never collapsed
        into one, so both survive and the pairing no longer depends on
        which one happened to come first."""
        import scripts.build_polygon_gex as bpg
        dup = _raw(("SPY",)).iloc[[0]].copy()               # one contract, K=80 call
        dup2 = dup.copy()
        dup2["strike_ticker"] = dup2["strike_ticker"] + "-ADJ"   # a distinct vendor ticker
        dup2["oi"] = 7.0
        standard_first = pd.concat([dup, dup2], ignore_index=True)
        adjusted_first = pd.concat([dup2, dup], ignore_index=True)

        agrees_a, overlap_a, floor_a, mismatches_a, *_ = bpg._same_book_overlap(
            standard_first, adjusted_first)
        agrees_b, overlap_b, floor_b, mismatches_b, *_ = bpg._same_book_overlap(
            adjusted_first, standard_first)
        assert agrees_a is True, (agrees_a, overlap_a, floor_a)
        assert agrees_b is True, (agrees_b, overlap_b, floor_b)
        assert mismatches_a == mismatches_b == 0
        assert overlap_a == overlap_b == 2, "both distinctly-ticketed contracts must survive"

    def test_f3_empty_stored_frame_is_unverifiable_not_vacuously_agreed(self):
        """F3: a stored frame with ZERO rows must never read as "agrees" via
        a vacuous all()-over-nothing pandas default -- that would let the
        same-book proof pass when there is nothing on the stored side to
        prove anything against."""
        import scripts.build_polygon_gex as bpg
        candidate = _raw(("SPY",))
        agrees, overlap, floor, mismatches, *_ = bpg._same_book_overlap(candidate.iloc[0:0], candidate)
        assert agrees is False
        assert overlap == 0
        assert mismatches == 0

    def test_f4_monday_intraday_capture_fails_lease_prong_a_even_though_prong_b_passes(
            self, tmp_path, monkeypatch):
        """F4: prong (b) (capture_instant < LEASE_END_ET_HOUR:00 the next
        calendar day) is satisfied trivially by ANY same-day INTRADAY
        capture, so weekend/boundary scenarios alone never exercise prong
        (a) (expected_last_session(capture_instant) == session) in
        isolation. A Monday 10:00 ET capture attempting to replace that
        SAME Monday's session fails prong (a) alone: at 10:00 ET the 17:00
        ET settle buffer has not passed, so expected_last_session resolves
        to the PRIOR completed session (Friday), not Monday -- even though
        10:00 ET Monday is trivially "before 03:00 ET Tuesday" (prong b).
        Deleting prong (a) must fail this test."""
        import scripts.build_polygon_gex as bpg
        monday = date(2026, 8, 24)
        monday_intraday = datetime(2026, 8, 24, 10, 0, tzinfo=nyse_calendar.ET)
        # Sanity: prong (b) alone would pass -- this instant is nowhere near
        # the next-calendar-day 03:00 ET boundary.
        assert monday_intraday < datetime(2026, 8, 25, 3, 0, tzinfo=nyse_calendar.ET)
        assert bpg._within_capture_lease(monday, monday_intraday) is False

        universe = _setup_stored_partial(tmp_path, monkeypatch,
                                         session_iso=monday.isoformat(),
                                         stored_symbols=STORED)
        new_raw = _raw(tuple(f"U{i}" for i in range(70)))     # strictly better, matching OI
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))
        res = bpg.accrue(monday, _now=monday_intraday)
        # AD-1C0.1 amendment 1+2: pre-fetch refusal now returns its own
        # "outside_lease" status; see test_6_7_8's note.
        assert res["status"] == "outside_lease"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{monday.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_outside_lease"

    def test_f5_unreadable_stored_parquet_is_unverifiable_vintage(self, tmp_path, monkeypatch):
        """F5: a stored chain that EXISTS on disk but cannot be read as a
        parquet (bytes corrupted at rest -- distinct from B3's receipt
        corruption) must degrade the same-book proof to
        skipped_unverifiable_vintage, never crash accrue() and never
        silently trust an unreadable file as a pass."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)

        chains_dir = tmp_path / "polygon_gex" / "chains"
        chains_dir.mkdir(parents=True)
        (chains_dir / f"{LEASE_SESSION.isoformat()}.parquet").write_bytes(
            b"not a real parquet file, just garbage bytes")
        _write_receipt_file(tmp_path, LEASE_SESSION.isoformat(),
                            [_entry("wrote", "partial", 50, 0.50, requested=100)])

        new_raw = _raw(tuple(f"U{i}" for i in range(70)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))
        res = bpg.accrue(LEASE_SESSION, _now=LEASE_SAT_0040)
        assert res["status"] == "already_present"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_unverifiable_vintage"


def _synthetic_book(n, symbol="SYN", oi=1000.0, spot=100.0, key_offset=0):
    """`n` distinct synthetic contracts for `symbol`. Contract identity rides
    entirely on a unique per-row vendor `strike_ticker` keyed off
    `key_offset + j` (j in [0, n)) -- two calls with the SAME key_offset
    produce the SAME identities (a controlled overlap); a key_offset range
    that never intersects another call's range produces entirely DISJOINT
    identities. Needed because the default _raw() 42-contracts/symbol grid
    can't hit an EXACT target contract count -- the overlap-floor regression
    tests need a precise stored/candidate contract count, not just 'a lot of
    contracts'."""
    rows = []
    for j in range(n):
        i = key_offset + j
        rows.append(dict(underlying=symbol, strike_ticker=f"O:{symbol}{i}C",
                         expiry=ASOF + pd.Timedelta(days=30), K=round(50.0 + i * 0.01, 2),
                         T=30 / 365, is_call=True, oi=float(oi), iv=0.25,
                         gamma=0.01, delta=0.5, volume=10.0, spot=spot, asof=ASOF))
    return pd.DataFrame(rows)


def _write_failed_receipt(tmp_path, session_iso, requested=100):
    """A session whose first capture attempt FAILED outright -- a receipt
    exists (recording the failed attempt) but NO chain parquet was ever
    written (a zero-capture run never reaches the parquet write; see the
    `raw.empty` branch in accrue()). Matches Sol's matrix case #1: 'failed
    Friday first capture (no parquet, failed receipt)'."""
    _write_receipt_file(tmp_path, session_iso,
                        [_entry("nothing_captured", "failed", 0, 0.0, requested=requested)])


# ═══ AD-1C0.1 amendments (Sol review 4989933857, 2026-08-21) ══════════════
#
# Sol accepted the Option-B lease architecture but found four load-bearing
# defects: (1) first writes bypassed the lease entirely; (2) the lease was
# tested only AFTER the full vendor fetch; (3) the overlap floor was a
# MAXIMUM of 20, not a minimum; (4) receipts didn't persist the gate
# evidence. The classes below are the commissioning packet's matrix + audit
# coverage for all four.

class TestAD1C01FirstWriteLease:
    """Amendments 1+2: the capture lease now governs FIRST writes exactly as
    it already governed replacements, checked PRE-FETCH. Each test below is
    numbered to match the commissioning packet's Sol-mandated matrix."""

    @pytest.mark.parametrize("label,instant", [
        ("saturday_0400", datetime(2026, 8, 22, 4, 0, tzinfo=nyse_calendar.ET)),
        ("sunday", LEASE_SUN_1200),
        ("monday_preopen", LEASE_MON_0800),
    ])
    def test_1_2_3_failed_friday_capture_then_weekend_preopen_rescue_finds_no_parquet(
            self, tmp_path, monkeypatch, label, instant):
        """#1/#2/#3: Friday's first capture FAILED outright (no parquet at
        all landed, just a "nothing_captured"/"failed" receipt entry) -- a
        Saturday 04:00 ET, Sunday, or Monday 08:00 ET pre-open rescue run
        must ALL be refused by the lease, so no parquet EVER lands for that
        session from any of them -- never filing the CURRENT vendor snapshot
        under the OLD Friday session label (the exact PIT violation the
        pre-amendment code allowed)."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        session_iso = LEASE_SESSION.isoformat()
        _write_failed_receipt(tmp_path, session_iso, requested=1)
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))

        res = bpg.accrue(LEASE_SESSION, _now=instant)

        assert res["status"] == "outside_lease", label
        assert not (tmp_path / "polygon_gex" / "chains" / f"{session_iso}.parquet").exists(), label
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{session_iso}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_outside_lease", label
        assert receipt["attempts"][-1]["lease"]["write_kind"] == "first_write", label

    def test_4_explicit_old_session_date_without_force_is_refused(self, tmp_path, monkeypatch):
        """#4: an explicit --date naming an OLD session (accrue(as_of=<old
        date>)), with no --force, is refused by the lease's own prong (a) --
        expected_last_session(now) never equals a session that closed out
        long ago, so no NEW session-resolution logic was needed to catch
        this: _within_capture_lease already refuses it on its own."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        old_session = date(2026, 1, 5)     # long closed out relative to `now` below
        now = SAME_DAY_NOW                  # resolves to session 2026-06-15
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))

        res = bpg.accrue(old_session, _now=now)

        assert res["status"] == "outside_lease"
        assert not (tmp_path / "polygon_gex" / "chains"
                   / f"{old_session.isoformat()}.parquet").exists()
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{old_session.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_outside_lease"
        assert receipt["attempts"][-1]["lease"]["write_kind"] == "first_write"
        assert receipt["attempts"][-1]["health"] == "absent"

    def test_5_valid_same_evening_first_capture_writes(self, tmp_path, monkeypatch):
        """#5: a normal evening first-write capture instant is well inside
        the lease -- unaffected by amendment 1, still writes."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))

        res = bpg.accrue(LEASE_SESSION, _now=LEASE_FRI_EVENING)

        assert res["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "wrote"
        assert receipt["attempts"][-1]["lease"]["valid"] is True
        assert receipt["attempts"][-1]["lease"]["write_kind"] == "first_write"

    def test_6_valid_post_midnight_first_capture_resolving_to_the_target_session_writes(
            self, tmp_path, monkeypatch):
        """#6: a post-midnight 00:30 ET first capture that still resolves to
        the TARGET session (prong (a) holds) and sits inside the overnight
        lease (prong (b) holds) writes -- the lease's whole point is to NOT
        refuse this lawful case."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))
        post_midnight = datetime(2026, 8, 22, 0, 30, tzinfo=nyse_calendar.ET)

        res = bpg.accrue(LEASE_SESSION, _now=post_midnight)

        assert res["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "wrote"
        assert receipt["attempts"][-1]["lease"]["valid"] is True

    def test_7_force_outside_the_lease_still_writes_but_lease_valid_is_false(
            self, tmp_path, monkeypatch):
        """#7: --force bypasses the pre-fetch gate exactly as it bypasses
        everything else, but the receipt still records the TRUTH -- the
        capture instant really was outside the lease -- via lease.valid ==
        False alongside decision "forced". This IS the explicit forced-
        bypass diagnostic the receipt exists to preserve."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))

        res = bpg.accrue(LEASE_SESSION, force=True, _now=LEASE_MON_0800)

        assert res["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "forced"
        assert receipt["attempts"][-1]["lease"]["valid"] is False
        assert receipt["attempts"][-1]["lease"]["write_kind"] == "first_write"


class TestAD1C01NoFetchOutsideLease:
    """Amendment 2: the pre-fetch gate must refuse BEFORE ever calling
    client.snapshot() -- proven by wiring a client that raises loudly if
    snapshot() is called at all, for both a stored REPLACEABLE partial and a
    missing-file first write."""

    @pytest.mark.parametrize("label,instant", [
        ("saturday", LEASE_SAT_1000),
        ("sunday", LEASE_SUN_1200),
        ("monday_preopen", LEASE_MON_0800),
    ])
    def test_replacement_candidate_spends_no_api_quota_outside_the_lease(
            self, tmp_path, monkeypatch, label, instant):
        import scripts.build_polygon_gex as bpg
        _setup_stored_partial(tmp_path, monkeypatch,
                              session_iso=LEASE_SESSION.isoformat(),
                              stored_symbols=STORED)
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(LEASE_SESSION, _now=instant)

        assert res["status"] == "outside_lease", label
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_outside_lease", label

    @pytest.mark.parametrize("label,instant", [
        ("saturday", LEASE_SAT_1000),
        ("sunday", LEASE_SUN_1200),
        ("monday_preopen", LEASE_MON_0800),
    ])
    def test_first_write_candidate_spends_no_api_quota_outside_the_lease(
            self, tmp_path, monkeypatch, label, instant):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(LEASE_SESSION, _now=instant)

        assert res["status"] == "outside_lease", label
        assert not (tmp_path / "polygon_gex" / "chains"
                   / f"{LEASE_SESSION.isoformat()}.parquet").exists(), label


class TestAD1C01OverlapFloorIsAMinimum:
    """Amendment 3: the same-book proof's required overlap is now
    max(OI_OVERLAP_FLOOR_ABS, ceil(OI_OVERLAP_FLOOR_FRACTION * stored)),
    bounded above by min(len(stored), ...) -- a real floor, never the
    pre-amendment min()-based ceiling capped at 20."""

    def test_small_stored_book_caps_the_floor_at_its_own_size(self):
        """A 4-contract stored partial can only ever demand all 4 shared
        contracts -- the outer min(len(stored), ...) bound, not the 20-
        contract absolute floor."""
        import scripts.build_polygon_gex as bpg
        stored = _synthetic_book(4, symbol="TINY")
        candidate = _synthetic_book(4, symbol="TINY")     # identical -- full overlap
        agrees, overlap, floor, mismatches, *_ = bpg._same_book_overlap(stored, candidate)
        assert floor == 4
        assert overlap == 4
        assert mismatches == 0
        assert agrees is True

    def test_a_1000_contract_book_requires_250_shared_contracts_not_20(
            self, tmp_path, monkeypatch):
        """A 1,000-contract book must NOT pass the proof on just 20 shared
        contracts (the pre-amendment MAXIMUM evidence requirement). Stored:
        1,000 contracts on symbol BIG. Candidate: strictly better on quality
        (adds symbol EXTRA, reaching 2/2 requested = healthy) but shares
        EXACTLY 20 identical contracts with BIG's stored book -- the other
        980 BIG contracts and the 1 EXTRA contract are entirely disjoint.
        required_overlap must be 250 (25% of 1,000, the real floor),
        overlap_contracts must be 20, and the replacement must be REFUSED."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe = ["BIG", "EXTRA"]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)

        stored_big = _synthetic_book(1000, symbol="BIG", key_offset=0)
        chains_dir = tmp_path / "polygon_gex" / "chains"
        chains_dir.mkdir(parents=True)
        stored_big.to_parquet(chains_dir / f"{ASOF.date().isoformat()}.parquet")
        _write_receipt_file(tmp_path, ASOF.date().isoformat(),
                            [_entry("wrote", "partial", 1, 0.5, requested=2)])

        shared = _synthetic_book(20, symbol="BIG", key_offset=0)             # SAME 20 identities
        disjoint_big = _synthetic_book(980, symbol="BIG", key_offset=2000)   # never in stored
        extra = _synthetic_book(1, symbol="EXTRA", key_offset=0)
        candidate = pd.concat([shared, disjoint_big, extra], ignore_index=True)
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(candidate, census=_census(candidate, universe)))

        res = bpg.accrue(ASOF.date(), _now=SAME_DAY_NOW)

        assert res["status"] == "already_present"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{ASOF.date().isoformat()}.json").read_text())
        entry = receipt["attempts"][-1]
        assert entry["decision"] == "skipped_unverifiable_vintage"
        vp = entry["vintage_proof"]
        assert vp["required_overlap"] == 250
        assert vp["overlap_contracts"] == 20
        assert vp["stored_contracts"] == 1000
        assert vp["candidate_contracts"] == 1001
        assert vp["oi_mismatch_count"] == 0     # A4: computed even below the floor


class TestAD1C01ReceiptAudit:
    """Amendment 4: every gate decision persists deterministic lease/overlap
    evidence on the health receipt, so a refusal or authorization can be
    audited after vendor state is gone."""

    def test_a_thin_overlap_refusal_still_reports_its_mismatch_count(self, tmp_path, monkeypatch):
        """(a): a 19-of-20-required refusal must still show the genuine
        oi_mismatch_count computed over its (too-thin) intersection -- never
        gated on overlap >= floor."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe = ["THIN", "EXTRA"]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)

        stored_thin = _synthetic_book(76, symbol="THIN", key_offset=0)   # floor = max(20, 19) = 20
        chains_dir = tmp_path / "polygon_gex" / "chains"
        chains_dir.mkdir(parents=True)
        stored_thin.to_parquet(chains_dir / f"{ASOF.date().isoformat()}.parquet")
        _write_receipt_file(tmp_path, ASOF.date().isoformat(),
                            [_entry("wrote", "partial", 1, 0.5, requested=2)])

        shared = _synthetic_book(19, symbol="THIN", key_offset=0)
        shared.loc[shared.index[:2], "oi"] = 4242.0     # 2 of the 19 shared disagree
        disjoint_thin = _synthetic_book(57, symbol="THIN", key_offset=1000)
        extra = _synthetic_book(1, symbol="EXTRA", key_offset=0)
        candidate = pd.concat([shared, disjoint_thin, extra], ignore_index=True)
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(candidate, census=_census(candidate, universe)))

        res = bpg.accrue(ASOF.date(), _now=SAME_DAY_NOW)

        assert res["status"] == "already_present"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{ASOF.date().isoformat()}.json").read_text())
        entry = receipt["attempts"][-1]
        assert entry["decision"] == "skipped_unverifiable_vintage"
        vp = entry["vintage_proof"]
        assert vp["overlap_contracts"] == 19
        assert vp["required_overlap"] == 20
        assert vp["overlap_contracts"] < vp["required_overlap"]
        assert vp["oi_mismatch_count"] == 2

    def test_b_big_overlap_one_mismatch_reports_oi_mismatch_count_of_one(
            self, tmp_path, monkeypatch):
        """(b): a real single-contract OI drift on an overlap that clears
        the floor reports oi_mismatch_count == 1 with decision
        skipped_vintage_mismatch."""
        import scripts.build_polygon_gex as bpg
        universe = _setup_stored_partial(tmp_path, monkeypatch,
                                         session_iso=LEASE_SESSION.isoformat(),
                                         stored_symbols=STORED)
        new_raw = _raw_with_oi_override(
            tuple(f"U{i}" for i in range(70)), {("U5", 100.0, True): 4242.0})
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))

        res = bpg.accrue(LEASE_SESSION, _now=LEASE_SAT_0040)

        assert res["status"] == "already_present"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        entry = receipt["attempts"][-1]
        assert entry["decision"] == "skipped_vintage_mismatch"
        vp = entry["vintage_proof"]
        assert vp["overlap_contracts"] >= vp["required_overlap"]
        assert vp["oi_mismatch_count"] == 1

    def test_c_replaced_partial_carries_the_full_vintage_proof(self, tmp_path, monkeypatch):
        """(c): a successful replacement's receipt entry carries the
        complete vintage_proof (store_readable + all four counts), not just
        a bare pass/fail, plus a lease dict with valid=True."""
        import scripts.build_polygon_gex as bpg
        universe = _setup_stored_partial(tmp_path, monkeypatch,
                                         session_iso=LEASE_SESSION.isoformat(),
                                         stored_symbols=STORED)
        new_raw = _raw(tuple(f"U{i}" for i in range(70)))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, universe)))

        res = bpg.accrue(LEASE_SESSION, _now=LEASE_SAT_0040)

        assert res["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        entry = receipt["attempts"][-1]
        assert entry["decision"] == "replaced_partial"
        vp = entry["vintage_proof"]
        assert vp["store_readable"] is True
        assert vp["overlap_contracts"] >= vp["required_overlap"]
        assert vp["oi_mismatch_count"] == 0
        assert vp["stored_contracts"] > 0
        assert vp["candidate_contracts"] > 0
        lease = entry["lease"]
        assert lease["valid"] is True
        assert lease["write_kind"] == "replacement"

    def test_d_first_write_refusal_carries_lease_and_absent_health_no_vintage_proof(
            self, tmp_path, monkeypatch):
        """(d): a first-write lease refusal carries the lease dict and
        health == "absent" -- and, because no same-book proof ever ran
        (there was nothing stored to prove against), NO vintage_proof key at
        all."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))

        res = bpg.accrue(LEASE_SESSION, _now=LEASE_MON_0800)

        assert res["status"] == "outside_lease"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        entry = receipt["attempts"][-1]
        assert entry["decision"] == "skipped_outside_lease"
        assert entry["health"] == "absent"
        assert "lease" in entry
        assert entry["lease"]["write_kind"] == "first_write"
        assert entry["lease"]["valid"] is False
        assert "vintage_proof" not in entry


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

    def test_n7_concurrent_recovery_adopts_the_race_winner_instead_of_clobbering(
            self, tmp_path, monkeypatch):
        """N7 (AD-1C0 round 2): if path.replace(corrupt_aside) fails with
        FileNotFoundError, another recoverer most likely already won the race
        — renamed `path` aside and wrote its own fresh receipt there — between
        our failed read and this rename attempt. _recover_corrupt_receipt must
        RE-READ `path` and, if it now parses, ADOPT that content instead of
        clobbering the winner with a duplicate recovery entry."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        health_dir = tmp_path / "polygon_gex_health"
        health_dir.mkdir(parents=True)
        receipt_path = health_dir / "2026-06-15.json"
        receipt_path.write_text('{"session": "2026-06-15", "attemp')   # torn JSON

        winner_attempts = [{
            "capture_instant": "2026-06-15T20:00:00+00:00",
            "requested_underlyings": 10, "attempted_underlyings": 10,
            "successful_underlyings": 10, "coverage_pct": 1.0,
            "failure_reasons": {}, "failure_examples": {}, "aborted_early": False,
            "decision": "receipt_recovered", "health": "unknown_receipt_corrupt",
            "prior_receipt_corrupt": True,
        }]

        real_replace = Path.replace

        def _race_then_fail(self, target):
            if self.name == "2026-06-15.json":
                # Simulate a concurrent recoverer: it wins the race right
                # here, writing its own fresh valid receipt at `path` — our
                # rename then fails because the source inode it expected is
                # gone (already replaced by the winner in a real race; here
                # we just overwrite `path` directly to force the same
                # observable state).
                receipt_path.write_text(
                    json.dumps({"session": "2026-06-15", "attempts": winner_attempts}))
                raise FileNotFoundError("simulated concurrent-recovery race")
            return real_replace(self, target)

        monkeypatch.setattr(Path, "replace", _race_then_fail)

        from scripts.build_polygon_gex import _CorruptReceipt, _recover_corrupt_receipt
        try:
            bpg._read_receipt(date(2026, 6, 15))
            raise AssertionError("expected _CorruptReceipt")
        except _CorruptReceipt as e:
            result = _recover_corrupt_receipt(date(2026, 6, 15), e, SAME_DAY_NOW)

        assert result == winner_attempts, (
            "must adopt the race winner's attempts, not overwrite them")
        final = json.loads(receipt_path.read_text())
        assert final["attempts"] == winner_attempts, (
            "the winner's receipt must survive completely untouched")
        # no NEW corrupt-aside file was created by the loser
        asides = [p for p in health_dir.iterdir() if ".corrupt-" in p.name]
        assert not asides, asides


class TestB3WriteAheadReceipt:
    """B3 trigger-2 ruling (AD-1C0 round 2): a write-ahead receipt entry
    (decision "write_pending", carrying the FULL census/health BEFORE
    to_parquet) makes both crash windows around the parquet write
    self-describing instead of silently reading as legacy-healthy."""

    def test_crash_before_the_parquet_write_leaves_no_trace_next_run_writes_fresh(
            self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        # Simulate: a prior run appended write_pending then crashed BEFORE
        # to_parquet — a receipt exists, but there is NO chain parquet at all.
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("write_pending", "partial", 40, 0.40, requested=100)])
        assert not (tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet").exists()

        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "ok", (
            "a dangling write_pending with NO parquet must not block the next "
            "run — path.exists() gates the whole immutable-skip lookup, and "
            "there is no path yet")
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert set(back["underlying"]) == {"SPY"}
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        # the stale dangling entry stays in history; this run appends its OWN
        # pending+wrote pair after it.
        assert [a["decision"] for a in receipt["attempts"]][-2:] == ["write_pending", "wrote"]

    def test_crash_after_the_parquet_write_reads_the_pending_entrys_own_health(
            self, tmp_path, monkeypatch):
        """The parquet WAS written (a 40% partial capture) and MATCHES the
        pending entry's claim on BOTH underlying nunique AND row count (C1),
        but the FINAL decision entry never landed — the receipt's trailing
        entry is still "write_pending". W1/C1: this is the VERIFIED-MATCH
        case, so the store must read as PARTIAL (the pending entry's own
        health, now verified rather than assumed), never fall through to a
        legacy "healthy" default. This is the exact B3-t2 behavior pinned in
        round 2 — kept green under W1/C1's added verification."""
        import scripts.build_polygon_gex as bpg
        from scripts.build_polygon_gex import _read_receipt, _stored_health
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        # A 40-of-100 chain WAS actually written to disk — 40 symbols x 42
        # rows each (21 strikes x call/put, per _raw) = 1680 rows.
        _write_chain_file(tmp_path, "2026-06-15", symbols=tuple(f"U{i}" for i in range(40)))
        # ...and the receipt's trailing entry (still write_pending — the
        # finalize-entry append never landed) MATCHES it exactly: 40 unique,
        # 1680 rows.
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("write_pending", "partial", 40, 0.40, requested=100,
                                    rows=1680)])
        chain_path = tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet"

        attempts = _read_receipt(date(2026, 6, 15))
        assert _stored_health(attempts, chain_path) == "partial", (
            "a trailing write_pending whose on-disk parquet MATCHES its claim "
            "must read as ITS OWN (verified) health, never a legacy-healthy "
            "default — a 40% capture is not healthy")

        # ... and because it reads as partial, a strictly-better capture may
        # still replace it under the ordinary first-writer quality rule.
        new_raw = _raw(tuple(f"U{i}" for i in range(70)))
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "ok"
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "replaced_partial"
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert back["underlying"].nunique() == 70


class TestW1VerifiedWriteAhead:
    """W1 ruling (AD-1C0 round 3): either half of B3-t2 alone was
    insufficient — a trailing write_pending could still be TRUSTED even
    though the parquet it describes was never actually written (to_parquet
    failed/killed on a REPLACEMENT, leaving the OLD parquet paired with a NEW
    trailing pending entry) or was torn (truncated bytes at the real path).
    (a) atomic parquet writes make torn files at the real path impossible.
    (b) the trailing-write_pending anchor is VERIFIED against the actual
    on-disk parquet before being trusted."""

    def test_a_failed_write_on_a_replacement_leaves_the_old_parquet_intact_and_unverified(
            self, tmp_path, monkeypatch):
        """Simulates ENOSPC (or any to_parquet failure) on a replaced_partial
        run: the OLD parquet must survive byte-for-byte (atomic write never
        touched the real path), and the resulting trailing write_pending must
        NOT be trusted — _stored_health must read unknown_write_interrupted,
        not the pending entry's own (unverified, and wrong) claim."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15", symbols=tuple(f"U{i}" for i in range(40)))
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 40, 0.40, requested=100)])
        chain_path = tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet"
        old_bytes = chain_path.read_bytes()

        new_raw = _raw(tuple(f"U{i}" for i in range(70)))     # strictly better
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))

        real_to_parquet = pd.DataFrame.to_parquet

        def _boom(self, *a, **kw):
            raise OSError("simulated ENOSPC")

        monkeypatch.setattr(pd.DataFrame, "to_parquet", _boom)
        with pytest.raises(OSError):
            bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)

        # the OLD parquet is completely untouched
        assert chain_path.read_bytes() == old_bytes
        # no orphaned tmp parquet left behind by the failed atomic write
        leftovers = [p.name for p in chain_path.parent.iterdir() if ".tmp." in p.name]
        assert not leftovers, leftovers

        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "write_pending"
        # the trailing write_pending is NOT trusted -- verification against
        # the (unchanged, still-40) parquet shows unknown_write_interrupted
        # because the pending entry's OWN claim (70) does not match what is
        # actually on disk (40).
        from scripts.build_polygon_gex import _read_receipt, _stored_health
        attempts = _read_receipt(date(2026, 6, 15))
        assert _stored_health(attempts, chain_path) == "unknown_write_interrupted"

        # a next same-day run re-fetches (not immutable) and may replace, once
        # to_parquet is no longer failing.
        monkeypatch.setattr(pd.DataFrame, "to_parquet", real_to_parquet)
        res2 = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res2["status"] == "ok"
        back = pd.read_parquet(chain_path)
        assert back["underlying"].nunique() == 70

    def test_a_truncated_parquet_is_unreadable_and_reads_as_zero_stored_success(
            self, tmp_path, monkeypatch):
        """Simulates a torn/truncated file directly at the real path (e.g. a
        pre-W1-era file, or any other source of corruption at rest) paired
        with a trailing write_pending — garbage bytes make the parquet
        unreadable, so verification must treat it as 0 successful, never the
        pending entry's claim."""
        from scripts.build_polygon_gex import _stored_health
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        chains_dir = tmp_path / "polygon_gex" / "chains"
        chains_dir.mkdir(parents=True)
        chain_path = chains_dir / "2026-06-15.parquet"
        chain_path.write_bytes(b"not a real parquet file, just garbage bytes")
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("write_pending", "partial", 40, 0.40, requested=100)])

        from scripts.build_polygon_gex import _read_receipt, _stored_state_entry
        attempts = _read_receipt(date(2026, 6, 15))
        assert _stored_health(attempts, chain_path) == "unknown_write_interrupted"
        anchor = _stored_state_entry(attempts, chain_path)
        assert anchor["successful_underlyings"] == 0, (
            "an unreadable parquet must report 0 stored success, not the "
            "pending entry's unverified claim")
        assert anchor["coverage_pct"] == 0.0

    def test_atomic_write_uses_os_replace_and_leaves_no_tmp_parquet(self, tmp_path, monkeypatch):
        """(a) sanity: a NORMAL successful write leaves no tmp parquet behind
        and the real path is the final, complete file."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "ok"
        chains_dir = tmp_path / "polygon_gex" / "chains"
        names = [p.name for p in chains_dir.iterdir()]
        assert names == ["2026-06-15.parquet"], names


class TestC1TwoFieldVerificationMatch:
    """C1 ruling (AD-1C0 round 4): underlying nunique ALONE can COLLIDE — a
    forced re-capture of a totally DIFFERENT symbol set that happens to claim
    the SAME count as what's on disk would pass a nunique-only check and
    mislabel a stale store healthy. Verification now requires BOTH nunique
    AND total row count to match, and treats a write_pending entry with no
    "rows" field at all as unverifiable (forward safety)."""

    def test_the_reviewer_repro_shape_nunique_collision_is_caught_by_rows(
            self, tmp_path, monkeypatch):
        """40 U*-named symbols on disk (1680 rows, per _raw's 42 rows/symbol).
        A FORCED capture claims 40 DIFFERENT V*-named symbols — same COUNT,
        but built with only 1 row per symbol (40 total, not 1680) — and its
        write fails (simulated ENOSPC). A nunique-only check would read
        40 == 40 and call the phantom capture's health safe; the row-count
        mismatch (40 claimed vs 1680 actual) must catch it instead."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15", symbols=tuple(f"U{i}" for i in range(40)))
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 40, 0.40, requested=100)])
        chain_path = tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet"
        old_bytes = chain_path.read_bytes()

        v_symbols = tuple(f"V{i}" for i in range(40))
        new_raw = pd.DataFrame([
            dict(underlying=sym, strike_ticker=f"O:{sym}100",
                expiry=ASOF + pd.Timedelta(days=30), K=100.0, T=30 / 365,
                is_call=True, oi=1000.0, iv=0.25, gamma=0.01, delta=0.5,
                volume=10.0, spot=100.0, asof=ASOF)
            for sym in v_symbols
        ])
        assert new_raw["underlying"].nunique() == 40      # the COLLIDING count
        assert len(new_raw) == 40                          # but NOT 1680 rows

        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))

        def _boom(self, *a, **kw):
            raise OSError("simulated ENOSPC")

        monkeypatch.setattr(pd.DataFrame, "to_parquet", _boom)
        with pytest.raises(OSError):
            bpg.accrue(date(2026, 6, 15), force=True, _now=SAME_DAY_NOW)

        # the OLD parquet is completely untouched
        assert chain_path.read_bytes() == old_bytes

        from scripts.build_polygon_gex import _read_receipt, _stored_health
        attempts = _read_receipt(date(2026, 6, 15))
        pending = attempts[-1]
        assert pending["decision"] == "write_pending"
        assert pending["successful_underlyings"] == 40     # matches on-disk nunique...
        assert pending["rows"] == 40                        # ...but NOT on-disk rows (1680)
        assert _stored_health(attempts, chain_path) == "unknown_write_interrupted", (
            "nunique alone (40 == 40) would wrongly say 'match' -- the row-"
            "count mismatch must catch the collision and refuse to call this "
            "stale store healthy")

    def test_a_write_pending_entry_with_no_rows_field_is_unverifiable(self, tmp_path):
        """Forward safety: a write_pending entry from before the "rows" field
        existed (or any caller that omits it) must degrade exactly like a
        verification failure — never trusted at face value even if its
        underlying nunique happens to match."""
        from scripts.build_polygon_gex import _stored_health
        d = tmp_path / "polygon_gex" / "chains"
        d.mkdir(parents=True)
        _raw(tuple(f"U{i}" for i in range(40))).to_parquet(d / "2026-06-15.parquet")
        chain_path = d / "2026-06-15.parquet"
        # no "rows" key at all -- the pre-C1 shape.
        attempts = [_entry("write_pending", "partial", 40, 0.40, requested=100)]
        assert "rows" not in attempts[-1]
        assert _stored_health(attempts, chain_path) == "unknown_write_interrupted"


class TestC2AtomicityCrashInjection:
    """C2 ruling (AD-1C0 round 4): half (a) — atomic parquet writes — shipped
    with no crash-injection test that actually DISTINGUISHES _atomic_to_parquet
    from a naive direct df.to_parquet(path) call. to_parquet is monkeypatched
    to write REAL bytes to whatever path it is CALLED WITH, then raise. With
    the atomic writer that call target is the TMP path (garbage lands there,
    then gets unlinked by the except-cleanup) — the REAL path's old bytes must
    survive byte-for-byte. A naive direct call would be invoked WITH the real
    path, so the garbage would land there instead."""

    def test_a_mid_write_crash_leaves_the_real_path_byte_identical_and_no_tmp_residue(
            self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(100)])
        _write_chain_file(tmp_path, "2026-06-15", symbols=tuple(f"U{i}" for i in range(40)))
        _write_receipt_file(tmp_path, "2026-06-15",
                            [_entry("wrote", "partial", 40, 0.40, requested=100)])
        chain_path = tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet"
        old_bytes = chain_path.read_bytes()

        new_raw = _raw(tuple(f"U{i}" for i in range(70)))     # strictly better
        all_syms = [f"U{i}" for i in range(100)]
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, all_syms)))

        def _write_garbage_then_raise(self, target, *a, **kw):
            # This is the DISTINGUISHING move: real bytes actually land at
            # whatever path to_parquet was called with. Atomic -> that path
            # is the tmp file. Naive/reverted -> that path IS `path` itself.
            Path(target).write_bytes(b"GARBAGE-MID-WRITE-CRASH")
            raise OSError("simulated crash mid-write")

        monkeypatch.setattr(pd.DataFrame, "to_parquet", _write_garbage_then_raise)
        with pytest.raises(OSError):
            bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)

        # (a) atomicity: the real path's OLD bytes survive byte-for-byte --
        # if _atomic_to_parquet is reverted to a direct df.to_parquet(path)
        # call, the garbage bytes above would have landed AT `path` and this
        # assertion fails.
        assert chain_path.read_bytes() == old_bytes, (
            "the real path must be byte-identical to before the crash — a "
            "direct (non-atomic) to_parquet call would have corrupted it "
            "with the injected garbage bytes")
        # cleanup-and-reraise: no tmp parquet residue survives -- if the
        # `tmp.unlink(missing_ok=True)` cleanup in _atomic_to_parquet's except
        # clause is removed, the garbage tmp file leaks here.
        leftovers = [p.name for p in chain_path.parent.iterdir() if ".tmp." in p.name]
        assert not leftovers, (
            f"no tmp parquet residue may survive the crash: {leftovers}")


class TestN1ForceBypassesUniverseGates:
    """N1 ruling (AD-1C0 round 2): baskets OFF is a documented operator
    revert — never a silent collapse — so the shrink tripwire must be scoped
    to include_baskets=true only, and --force must bypass BOTH universe gates
    entirely (the wedge it exists to escape)."""

    def test_a_documented_baskets_off_revert_proceeds_despite_a_large_prior_chain(
            self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _patch_include_baskets(monkeypatch, False)
        # A large PRIOR session (300 names) is on disk — under the OLD
        # unconditional shrink check this would have permanently wedged any
        # future include_baskets:false revert.
        _write_chain_file(tmp_path, "2026-06-12", symbols=tuple(f"U{i}" for i in range(300)))
        anchors10 = [f"U{i}" for i in range(10)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: anchors10)
        raw = _raw(tuple(anchors10))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, anchors10)))

        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "ok", res
        back = pd.read_parquet(tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet")
        assert back["underlying"].nunique() == 10

    def test_an_include_baskets_true_collapse_is_still_refused(self, tmp_path, monkeypatch):
        """Contrast case: with include_baskets TRUE, the identical shrink
        scenario must still be refused — this is the genuine collapse the
        tripwire exists to catch."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, "2026-06-12", symbols=tuple(f"U{i}" for i in range(300)))
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(10)])
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())
        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "failed"
        assert res["census"]["failure_reasons"] == {"universe_resolution_failed": 1}

    def test_force_overrides_the_universe_gate_with_decision_forced(self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _write_empty_membership(tmp_path)             # a membership-degraded scenario
        monkeypatch.setattr(eou, "baskets_universe", lambda: [])
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY", "QQQ", "IWM"])
        raw = _raw(("SPY", "QQQ", "IWM"))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY", "QQQ", "IWM"])))

        res = bpg.accrue(date(2026, 6, 15), force=True, _now=SAME_DAY_NOW)
        assert res["status"] == "ok", res
        receipt = json.loads((tmp_path / "polygon_gex_health" / "2026-06-15.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "forced"


class TestN2ReceiptAwareShrinkReference:
    def test_a_partial_night_s_receipt_still_arms_the_tripwire(self, tmp_path, monkeypatch):
        """N2 ruling (AD-1C0 round 2): a prior night that only captured a
        PARTIAL chain (20 of 375) must not disarm the reference — the
        receipt's own requested_underlyings (375) is still a valid witness of
        how big the universe used to be, even though the chain parquet itself
        only has 20 names."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        # Prior night: chain captured only 20 (a genuine partial), but the
        # receipt recorded what was actually REQUESTED that night: 375.
        _write_chain_file(tmp_path, "2026-06-12", symbols=tuple(f"U{i}" for i in range(20)))
        _write_receipt_file(tmp_path, "2026-06-12",
                            [_entry("wrote", "partial", 20, 20 / 375, requested=375)])

        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: [f"U{i}" for i in range(10)])
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(date(2026, 6, 15), _now=SAME_DAY_NOW)
        assert res["status"] == "failed"
        assert res["census"]["failure_reasons"] == {"universe_resolution_failed": 1}
        assert not (tmp_path / "polygon_gex" / "chains" / "2026-06-15.parquet").exists()

    def test_a_legacy_chain_with_no_receipt_falls_back_to_the_captured_count(
            self, tmp_path, monkeypatch):
        """A prior session's chain with NO receipt at all (legacy) uses only
        its captured underlying count — unchanged prior behavior."""
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
        assert res["status"] == "ok", (
            "12 captured (no receipt) vs 10 resolved is a mild 1.2x trim, "
            "well under the 3x tripwire")


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


# ═══ AD-1C0.1 review repairs (F1-F4, post-Sol-review, 2026-08-21) ══════════

class TestAD1C01SingleClock:
    """R1 (fixes F1, the two-clock blocker): accrue() must read the accrual
    instant from ONE clock. When the caller passes a datetime `as_of` with
    NO `_now` override, that `as_of` IS the accrual instant by this module's
    own contract (_resolve_session's docstring) -- the session resolution,
    the capture lease, and the receipt's capture_instant must all agree on
    it, never fall back to a separately-sampled `datetime.now()`. Both
    instants below are constructed far from any real wall-clock 'now' this
    suite could run under, so these tests can only pass if accrue() actually
    reads `as_of` as the clock -- a stray `datetime.now()` read anywhere in
    the path would resolve a different session (or a different lease
    verdict) and fail loudly, not coincidentally agree."""

    def test_a_datetime_as_of_with_no_now_writes_its_own_resolved_session(
            self, tmp_path, monkeypatch):
        """(a): an in-lease datetime `as_of` (Friday 21:24 ET), passed with
        NO `_now`, must resolve and write ITS OWN Friday session -- and the
        receipt's capture_instant must equal `as_of` exactly, proving the
        lease check and the session resolution read the same clock."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        friday_evening = datetime(2026, 6, 12, 21, 24, tzinfo=nyse_calendar.ET)  # in-lease
        raw = _raw(("SPY",))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(raw, census=_census(raw, ["SPY"])))

        res = bpg.accrue(friday_evening)   # NO _now override

        assert res["status"] == "ok"
        assert res["session"] == "2026-06-12"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / "2026-06-12.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "wrote"
        assert receipt["attempts"][-1]["capture_instant"] == friday_evening.isoformat(), (
            "the receipt's capture_instant must be the SAME instant as `as_of` "
            "-- a wall-clock fallback would stamp a different (real, current) "
            "instant here instead")

    def test_b_datetime_as_of_with_no_now_outside_lease_writes_nothing(
            self, tmp_path, monkeypatch):
        """(b): an out-of-lease instant for ITS OWN resolved session -- 03:30
        ET Saturday resolves to Friday's session (prong a) but has already
        rolled past the 03:00 ET lease boundary (prong b) -- passed with NO
        `_now`, must be refused using `as_of` as the clock and write
        nothing. This is the single-clock counterpart to (a): both prongs of
        the lease predicate must read the identical instant `as_of` supplies,
        not a wall clock that happens to resolve a different verdict."""
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY"])
        saturday_early = datetime(2026, 6, 13, 3, 30, tzinfo=nyse_calendar.ET)  # outside-lease
        assert bpg._resolve_session(saturday_early) == date(2026, 6, 12), (
            "sanity: this instant must resolve to Friday's session (prong a) "
            "for this test to actually exercise prong b in isolation")
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())

        res = bpg.accrue(saturday_early)   # NO _now override

        assert res["status"] == "outside_lease"
        assert not (tmp_path / "polygon_gex" / "chains" / "2026-06-12.parquet").exists()
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / "2026-06-12.json").read_text())
        assert receipt["attempts"][-1]["decision"] == "skipped_outside_lease"
        assert receipt["attempts"][-1]["capture_instant"] == saturday_early.isoformat()


class TestR2FirstWriteRefusalPreservesTheShrinkReference:
    """R2 (fixes F2, the shrink-tripwire blinding): the pre-fetch outside-
    lease refusal used to mint an ALL-None census on a first write (nothing
    was ever fetched to report a real one) -- but an all-None entry is
    invisible to _store_shrink_reference's receipt scan (it only reads
    entries carrying an int requested_underlyings), so a refused first write
    silently DROPPED the one signal that would have kept the shrink
    tripwire armed at the true universe size. The universe is already
    resolved fetch-free before this gate runs (`symbols = gex_symbols(gx_cfg)`
    happens before the fetch), so recording requested_underlyings here costs
    no extra work and keeps the tripwire honest."""

    def test_a_first_write_refusal_keeps_the_tripwire_armed_at_the_true_universe_size(
            self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)

        # Session N: a genuine partial capture -- 20 of a 375-name universe
        # actually landed, but the receipt still remembers what was
        # REQUESTED that night.
        session_n = "2026-08-14"
        _write_chain_file(tmp_path, session_n, symbols=tuple(f"W{i}" for i in range(20)))
        _write_receipt_file(tmp_path, session_n,
                            [_entry("wrote", "partial", 20, round(20 / 375, 4), requested=375)])

        # Session N+1 (LEASE_SESSION, the next Friday): a REAL first-write
        # outside-lease refusal -- no stored file at all for this session,
        # and the capture instant has rolled well past the overnight lease
        # (Monday pre-open). The universe has NOT actually shrunk (still
        # 375 names) -- only THIS run's own capture never happened.
        universe375 = [f"W{i}" for i in range(375)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe375)
        monkeypatch.setattr(bpg, "PolygonOptions", lambda: _NoFetchClient())
        res_mid = bpg.accrue(LEASE_SESSION, _now=LEASE_MON_0800)
        assert res_mid["status"] == "outside_lease"
        assert not (tmp_path / "polygon_gex" / "chains"
                   / f"{LEASE_SESSION.isoformat()}.parquet").exists()

        # Session N+2: a fresh session with a genuinely small (10-name)
        # resolved universe. Session N's 20-name STORED CHAIN alone is well
        # under 3x10=30 -- the exact "silently passing" shape N2's own
        # docstring warns about. Only the RECEIPT-side signal (375,
        # recorded on N+1's refusal under this repair) still arms the
        # tripwire.
        session_n2 = date(2026, 8, 24)
        universe10 = [f"W{i}" for i in range(10)]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe10)
        res = bpg.accrue(session_n2,
                         _now=datetime(2026, 8, 24, 20, 0, tzinfo=nyse_calendar.ET))

        assert res["status"] == "failed", (
            "the 375-name reference recorded on N+1's first-write refusal "
            "must still arm the shrink tripwire against the genuinely-small "
            "10-name universe -- if the reference had collapsed to the "
            "20-name STORED chain alone, 20 >= 3x10=30 is FALSE and the "
            "tripwire would wrongly stay silent")
        assert res["census"]["failure_reasons"] == {"universe_resolution_failed": 1}
        assert not (tmp_path / "polygon_gex" / "chains"
                   / f"{session_n2.isoformat()}.parquet").exists()


class TestAD1C01ForcedWriteKind:
    """R3 (fixes F3, the forced-overwrite mislabel): write_kind must be
    derived from `existed_before` (whether a stored file was on disk at
    gate time), never from `stored_health` -- `stored_health` stays None on
    EVERY forced run (the block that computes it is guarded by
    `if path.exists() and not force:`), so deriving write_kind from it
    mislabeled a --force overwrite of an EXISTING, healthy capture as a
    "first_write"."""

    def test_forced_overwrite_of_an_existing_capture_is_a_replacement(
            self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        _write_chain_file(tmp_path, LEASE_SESSION.isoformat(), symbols=("SPY", "QQQ"))
        _write_receipt_file(tmp_path, LEASE_SESSION.isoformat(),
                            [_entry("wrote", "healthy", 2, 1.0, requested=2)])
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: ["SPY", "QQQ"])
        new_raw = _raw(("SPY", "QQQ"))
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(new_raw, census=_census(new_raw, ["SPY", "QQQ"])))

        res = bpg.accrue(LEASE_SESSION, force=True, _now=LEASE_FRI_EVENING)

        assert res["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{LEASE_SESSION.isoformat()}.json").read_text())
        entry = receipt["attempts"][-1]
        assert entry["decision"] == "forced"
        assert entry["lease"]["write_kind"] == "replacement", (
            "a forced overwrite of a capture that WAS on disk must be "
            "labelled a replacement, never a first_write -- stored_health "
            "alone cannot tell (it stays None on every forced run)")


class TestAD1C01VintageProofContractCounts:
    """R4 (fixes F4, the non-reproducible floor): vintage_proof.
    stored_contracts/candidate_contracts must record the DEDUPED per-
    contract identity counts _same_book_overlap actually computed
    `required_overlap` from -- not raw parquet/frame ROW counts. A stored
    frame with duplicate contract keys (rows > identities) makes the two
    diverge, so an auditor recomputing required_overlap = min(
    stored_contracts, max(20, ceil(0.25*stored_contracts))) FROM the
    receipt's own fields must reproduce the SAME required_overlap the
    receipt already reports."""

    def test_vintage_proof_records_deduped_identity_counts_not_raw_rows(
            self, tmp_path, monkeypatch):
        import scripts.build_polygon_gex as bpg
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
        _mock_baskets(monkeypatch)
        universe = ["DUP", "EXTRA"]
        monkeypatch.setattr(eou, "gex_symbols", lambda gx_cfg: universe)

        # 500 distinct identities, each duplicated once -> 1000 raw rows but
        # only 500 identities -- exactly the "rows > identities" shape F4
        # targets.
        dup_book = _synthetic_book(500, symbol="DUP", key_offset=0)
        stored = pd.concat([dup_book, dup_book], ignore_index=True)
        chains_dir = tmp_path / "polygon_gex" / "chains"
        chains_dir.mkdir(parents=True)
        stored.to_parquet(chains_dir / f"{ASOF.date().isoformat()}.parquet")
        _write_receipt_file(tmp_path, ASOF.date().isoformat(),
                            [_entry("wrote", "partial", 1, 0.5, requested=2)])

        # Candidate: the SAME 500 DUP identities (also row-duplicated, to
        # exercise the candidate side of the same fix) + a new EXTRA symbol
        # -- strictly better (2/2 requested = healthy) and OI-identical on
        # every shared identity, so the replacement succeeds.
        cand_dup = _synthetic_book(500, symbol="DUP", key_offset=0)
        extra = _synthetic_book(1, symbol="EXTRA", key_offset=0)
        candidate = pd.concat([cand_dup, cand_dup, extra], ignore_index=True)
        monkeypatch.setattr(bpg, "PolygonOptions",
                            lambda: _FakeClient(candidate, census=_census(candidate, universe)))

        res = bpg.accrue(ASOF.date(), _now=SAME_DAY_NOW)

        assert res["status"] == "ok"
        receipt = json.loads(
            (tmp_path / "polygon_gex_health" / f"{ASOF.date().isoformat()}.json").read_text())
        entry = receipt["attempts"][-1]
        assert entry["decision"] == "replaced_partial"
        vp = entry["vintage_proof"]
        assert vp["stored_contracts"] == 500, (
            "must be the DEDUPED identity count (500), not the raw row "
            "count (1000)")
        assert vp["candidate_contracts"] == 501, (
            "must be the DEDUPED identity count (501), not the raw row "
            "count (1001)")
        recomputed_floor = min(vp["stored_contracts"],
                               max(20, math.ceil(0.25 * vp["stored_contracts"])))
        assert recomputed_floor == vp["required_overlap"], (
            "an auditor recomputing the floor from the receipt's OWN fields "
            "must reproduce the SAME required_overlap the receipt reports")
