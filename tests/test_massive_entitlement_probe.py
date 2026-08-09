"""Vendor-entitlement probe — scripts/massive_entitlement_probe.

The probe's whole job is to answer "what can this key do" in a form we can COMMIT, so the
parts worth pinning are the ones that would silently publish a wrong or unsafe answer:

  * verdict mapping — 403 (plan refusal) and 401 (bad key) must never collapse into each
    other, and an ambiguous 404/429 must never be recorded as a False entitlement;
  * key scrubbing — this repo is public and ``requests`` embeds the request URL in its
    exception text.  A planted fake key must reach neither the manifest nor stdout;
  * transport shape — the key rides an ``Authorization: Bearer`` header, never an
    ``apiKey`` query param (query strings leak into logs, proxies, and exception strings);
  * the depth ladder — the derived history depth is what the masterplan will cite, and it
    is an inference over three probes, so it gets its own table test;
  * evidence discipline — evidence is tiny scalar markers, never a response body slice.

No network: the HTTP layer is a stub session, and the WS battery is exercised through its
injected-library seam.

Run: python3 -m pytest tests/test_massive_entitlement_probe.py -q
"""

from __future__ import annotations

import json

import pytest

from scripts import massive_entitlement_probe as mep

FAKE_KEY = "FAKEKEY_abcdefghijklmnop12345"       # >=20 [A-Za-z0-9_] chars, like a real one


# --------------------------------------------------------------------------- stub HTTP
class _FakeResponse:
    def __init__(self, status: int, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class _FakeSession:
    """Records every call so a test can assert on URL/params/headers after the fact."""

    def __init__(self, handler):
        self.headers: dict[str, str] = {}
        self.calls: list[dict] = []
        self._handler = handler

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}),
                           "headers": dict(self.headers), "timeout": timeout})
        out = self._handler(url, params, len(self.calls))
        if isinstance(out, BaseException):
            raise out
        return out


def _prober(handler, key: str | None = FAKE_KEY) -> mep.RestProber:
    return mep.RestProber(key, base_url="https://api.example.test",
                          timeout=1.0, session=_FakeSession(handler))


# --------------------------------------------------------------------------- verdicts
@pytest.mark.parametrize("status,expected", [
    (200, "entitled"),
    (403, "not_entitled"),      # Polygon NOT_AUTHORIZED — the plan does not cover it
    (404, "ambiguous"),         # endpoint absent/renamed, NOT a refusal
    (429, "ambiguous"),         # throttled — says nothing about entitlement
    (401, "error"),             # a KEY problem, never reportable as a plan downgrade
    (500, "error"),
    (503, "error"),
])
def test_verdict_for_status_maps_each_class(status, expected):
    assert mep.verdict_for_status(status) == expected


@pytest.mark.parametrize("status,expected", [
    (200, "entitled"), (403, "not_entitled"), (404, "ambiguous"), (500, "error"),
])
def test_probe_records_status_and_verdict(status, expected):
    p = _prober(lambda url, params, n: _FakeResponse(status, {"results": []}))
    p.probe("x", "/v3/thing")
    rec = p.results["x"]
    assert rec["http_status"] == status
    assert rec["verdict"] == expected
    assert set(rec) == {"http_status", "verdict", "evidence"}


def test_body_level_not_authorized_overrides_a_200():
    """Polygon sometimes declares refusal in the BODY; the body wins over the code."""
    p = _prober(lambda url, params, n: _FakeResponse(200, {"status": "NOT_AUTHORIZED"}))
    p.probe("x", "/v3/thing")
    assert p.results["x"]["verdict"] == "not_entitled"
    assert p.results["x"]["evidence"]["body_status"] == "NOT_AUTHORIZED"


def test_five_hundred_is_retried_once_then_recorded():
    seen = []

    def handler(url, params, n):
        seen.append(n)
        return _FakeResponse(500 if n == 1 else 200, {"resultsCount": 3})

    p = _prober(handler)
    p.probe("x", "/v3/thing", evidence=mep._ev_aggs)
    assert seen == [1, 2]                                  # exactly one retry
    assert p.results["x"]["verdict"] == "entitled"
    assert p.results["x"]["evidence"]["results_count"] == 3
    assert "error" not in p.results["x"]["evidence"]       # the healed 5xx is not an error


def test_timeout_is_retried_once_then_errors():
    calls = []

    def handler(url, params, n):
        calls.append(n)
        return TimeoutError("read timed out")

    p = _prober(handler)
    p.probe("x", "/v3/thing")
    assert calls == [1, 2]
    assert p.results["x"]["verdict"] == "error"
    assert p.results["x"]["http_status"] is None


# --------------------------------------------------------------------------- transport
def test_key_travels_as_bearer_header_and_never_as_a_query_param():
    p = _prober(lambda url, params, n: _FakeResponse(200, {"results": [{"ticker": "O:X"}]}))
    mep.run_rest_battery(p, probe_day="2026-08-07")

    calls = p.session.calls
    assert len(calls) > 25                                  # the full battery ran
    for c in calls:
        assert c["headers"].get("Authorization") == f"Bearer {FAKE_KEY}"
        assert "apiKey" not in c["params"]
        assert "api_key" not in c["params"]
        assert FAKE_KEY not in c["url"]
        assert FAKE_KEY not in json.dumps(c["params"])


def test_no_auth_header_when_there_is_no_key():
    p = _prober(lambda url, params, n: _FakeResponse(200, {}), key=None)
    p.probe("x", "/v3/thing")
    assert "Authorization" not in p.session.calls[0]["headers"]


# --------------------------------------------------------------------------- scrubbing
def test_scrub_removes_key_url_and_any_long_token():
    dirty = (f"HTTPError: 403 for url: https://api.polygon.io/v2/last/nbbo/AAPL"
             f"?apiKey={FAKE_KEY} (key {FAKE_KEY})")
    clean = mep._scrub(dirty, (FAKE_KEY,))
    assert FAKE_KEY not in clean
    assert "https://" not in clean
    assert "<url>" in clean


def test_a_key_bearing_exception_never_reaches_the_recorded_evidence():
    """requests puts the full URL — query string included — inside its exception text."""
    boom = RuntimeError(
        f"ConnectionError: HTTPSConnectionPool(host='api.polygon.io') url=/v3/trades"
        f"?apiKey={FAKE_KEY}")
    p = _prober(lambda url, params, n: boom)
    p.probe("x", "/v3/trades")
    blob = json.dumps(p.results)
    assert FAKE_KEY not in blob
    assert "<redacted>" in blob
    assert p.results["x"]["verdict"] == "error"


def test_err_keeps_the_exception_class_name_the_token_regex_would_eat():
    """``ConnectionClosedError`` is 21 [A-Za-z0-9_] chars — long enough to look like key
    material to the token regex.  A live run recorded it as ``<token>``, deleting the only
    diagnostic in the record, so the class name is routed around the scrubber."""
    class ConnectionClosedError(Exception):
        pass

    out = mep._err(ConnectionClosedError(f"sent 1008 with key {FAKE_KEY}"), (FAKE_KEY,))
    assert out.startswith("ConnectionClosedError: ")
    assert FAKE_KEY not in out


def test_scrub_still_collapses_a_secret_it_was_never_told_about():
    """Second net: the token regex catches key-shaped material even when the caller
    passed no secrets (a rotated alias, a co-tenant's key echoed by the vendor)."""
    clean = mep._scrub(f"upstream said token={FAKE_KEY} is invalid", ())
    assert FAKE_KEY not in clean
    assert "<token>" in clean


@pytest.mark.parametrize("planted", [
    FAKE_KEY,                               # the whole key
    FAKE_KEY[:16],                          # a truncated fragment is still key material
    FAKE_KEY[-16:],
])
def test_assert_no_key_leak_refuses_key_material(planted):
    with pytest.raises(RuntimeError):
        mep._assert_no_key_leak(json.dumps({"note": f"used {planted}"}), FAKE_KEY)


def test_assert_no_key_leak_passes_a_clean_manifest():
    text = mep.serialize(mep.build_manifest("POLYGON_API_KEY", "https://api.example.test",
                                            {}, {}, probed_at="2026-08-08T00:00:00Z"))
    mep._assert_no_key_leak(text, FAKE_KEY)     # must not raise


def test_end_to_end_run_leaks_the_key_to_neither_manifest_nor_stdout(
        monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("POLYGON_API_KEY", FAKE_KEY)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    def handler(url, params, n):
        # every probe blows up with the key baked into the message, worst case
        return RuntimeError(f"SSLError for url: {url}?apiKey={FAKE_KEY}")

    monkeypatch.setattr(mep.requests, "Session", lambda: _FakeSession(handler))
    out = tmp_path / "capability_manifest.json"
    rc = mep.main(["--out", str(out), "--skip-ws", "--timeout", "1"])

    text = out.read_text(encoding="utf-8")
    assert FAKE_KEY not in text
    assert FAKE_KEY not in capsys.readouterr().out
    assert json.loads(text)["key_source"] == "POLYGON_API_KEY"   # the NAME, not the value
    assert rc == 0                                               # non-strict tolerates errors


def test_strict_exits_one_when_a_probe_errored(monkeypatch, tmp_path):
    monkeypatch.setenv("POLYGON_API_KEY", FAKE_KEY)
    monkeypatch.setattr(mep.requests, "Session",
                        lambda: _FakeSession(lambda url, params, n: TimeoutError("t")))
    rc = mep.main(["--out", str(tmp_path / "m.json"), "--skip-ws", "--strict",
                   "--timeout", "1"])
    assert rc == 1


# --------------------------------------------------------------------------- manifest
def _rec(verdict: str, **evidence) -> dict:
    return {"http_status": 200, "verdict": verdict, "evidence": dict(evidence)}


def test_manifest_shape_is_the_v1_schema():
    rest = {"last_trade": _rec("entitled"), "last_nbbo": _rec("entitled")}
    ws = {"ws_stocks_realtime": _rec("entitled")}
    m = mep.build_manifest("MASSIVE_API_KEY", "https://api.example.test", rest, ws)

    assert m["schema"] == "massive_capability_manifest.v1"
    assert set(m) == {"schema", "probed_at_utc", "key_source", "base_url", "rest", "ws",
                      "derived"}
    assert m["key_source"] == "MASSIVE_API_KEY"
    assert m["probed_at_utc"].endswith("Z")
    assert set(m["derived"]) == {
        "realtime_trades", "realtime_quotes", "second_aggs", "tick_history_depth",
        "options_entitled", "options_realtime", "indices_entitled", "plan_guess", "notes"}
    assert isinstance(m["derived"]["notes"], list)
    assert isinstance(m["derived"]["plan_guess"], str)


def test_serialize_is_sorted_indented_and_newline_terminated():
    text = mep.serialize(mep.build_manifest("POLYGON_API_KEY", "https://x.test", {}, {},
                                            probed_at="2026-08-08T00:00:00Z"))
    assert text.endswith("}\n")
    assert '\n  "base_url"' in text                       # indent=2
    keys = [k for k in ("base_url", "derived", "key_source", "probed_at_utc", "rest",
                        "schema", "ws")]
    assert [k for k in json.loads(text)] == keys or list(json.loads(text)) == keys
    assert text.index('"base_url"') < text.index('"schema"')   # sort_keys=True


def test_evidence_is_scalar_markers_never_a_response_body():
    body = {"results": [{"ticker": "AAPL", "price": 1.0, "raw": {"deep": [1, 2, 3]}}] * 4,
            "resultsCount": 4}
    p = _prober(lambda url, params, n: _FakeResponse(200, body))
    p.probe("x", "/v2/aggs/x", evidence=mep._ev_aggs)
    ev = p.results["x"]["evidence"]
    assert ev == {"results_count": 4, "non_empty": True}
    assert all(isinstance(v, (int, float, str, bool, type(None))) for v in ev.values())


@pytest.mark.parametrize("payload,expected", [
    ({"results": [1, 2, 3]}, 3),
    ({"results": {"p": 1.0}}, 1),
    ({"tickers": [{"ticker": "AAPL"}], "count": 1}, 1),      # v2 snapshot envelope
    ({"tickers": [], "count": 0}, 0),
    ({"resultsCount": 836}, 836),
    ({"count": 24}, 24),
    ({"status": "OK"}, None),
])
def test_count_reads_every_polygon_result_envelope(payload, expected):
    """The v2 snapshot family answers under ``tickers``, not ``results`` — missing it
    recorded live, entitled snapshots as ``non_empty: false``, which reads as a
    capability gap when it is only an extractor gap."""
    assert mep._count(payload) == expected


def test_snapshot_evidence_is_non_empty_for_the_tickers_envelope():
    ev = mep._ev_results({"tickers": [{"ticker": "AAPL", "day": {"c": 1.0}}], "count": 1})
    assert ev == {"results_count": 1, "non_empty": True}


def test_exchange_evidence_extracts_the_finra_trf_mapping():
    payload = {"results": [{"id": 1, "name": "NYSE"}, {"id": 4, "name": "FINRA/NYSE TRF"},
                           {"id": 10, "name": "Nasdaq"}]}
    ev = mep._ev_exchanges(payload)
    assert ev == {"count": 3, "exchange_id_4_present": True,
                  "exchange_id_4_name": "FINRA/NYSE TRF"}
    assert mep._ev_exchanges({"results": [{"id": 1}]})["exchange_id_4_present"] is False


# --------------------------------------------------------------------------- derivation
@pytest.mark.parametrize("recent,y2015,y2005,expected", [
    (("entitled", True), ("entitled", True), ("entitled", True), "20y+"),
    (("entitled", True), ("entitled", True), ("not_entitled", False), "10y"),
    (("entitled", True), ("not_entitled", False), ("not_entitled", False), "5y"),
    (("entitled", True), ("entitled", False), ("entitled", False), "5y"),   # 200 but empty
    (("not_entitled", False), ("not_entitled", False), ("not_entitled", False), "shallow"),
    (("error", False), ("error", False), ("error", False), "unknown"),
    (("ambiguous", False), ("ambiguous", False), ("ambiguous", False), "unknown"),
])
def test_tick_history_depth_ladder(recent, y2015, y2005, expected):
    rest = {
        "trades_recent": _rec(recent[0], non_empty=recent[1]),
        "trades_2015": _rec(y2015[0], non_empty=y2015[1]),
        "trades_2005": _rec(y2005[0], non_empty=y2005[1]),
    }
    assert mep.derive(rest, {})["tick_history_depth"] == expected


def test_derive_reads_the_realtime_and_options_tells():
    rest = {
        "last_trade": _rec("entitled"), "last_nbbo": _rec("entitled"),
        "aggs_second": _rec("entitled", non_empty=True),
        "trades_recent": _rec("entitled", non_empty=True),
        "trades_2015": _rec("entitled", non_empty=True),
        "trades_2005": _rec("not_entitled", non_empty=False),
        "options_chain_snapshot": _rec("entitled"),
        "indices_snapshot": _rec("not_entitled"),
    }
    d = mep.derive(rest, {"ws_options": _rec("entitled")})
    assert d["realtime_trades"] is True
    assert d["realtime_quotes"] is True
    assert d["second_aggs"] is True
    assert d["tick_history_depth"] == "10y"
    assert d["options_entitled"] is True
    assert d["options_realtime"] is True
    assert d["indices_entitled"] is False
    assert "advanced_or_higher" in d["plan_guess"]


def test_an_undecided_probe_derives_none_never_false():
    """ambiguous/error is 'we do not know', and must not be published as 'not entitled'."""
    rest = {"last_trade": _rec("ambiguous"), "last_nbbo": _rec("error"),
            "aggs_second": _rec("ambiguous"), "indices_snapshot": _rec("error")}
    d = mep.derive(rest, {})
    assert d["realtime_trades"] is None
    assert d["realtime_quotes"] is None
    assert d["second_aggs"] is None
    assert d["indices_entitled"] is None
    assert d["options_entitled"] is None
    assert "unknown" in d["plan_guess"]


def test_delayed_only_plan_reads_as_basic():
    rest = {"last_trade": _rec("not_entitled"), "last_nbbo": _rec("not_entitled"),
            "aggs_minute": _rec("entitled", non_empty=True)}
    d = mep.derive(rest, {})
    assert d["realtime_trades"] is False
    assert "basic_or_delayed" in d["plan_guess"]


def test_options_chain_evidence_flags_greeks_iv_and_open_interest():
    ev = mep._ev_options_chain({"results": [{
        "greeks": {"delta": 0.5}, "implied_volatility": 0.31, "open_interest": 1200,
        "last_quote": {"bid": 1.0}, "last_trade": {"price": 1.1}}]})
    assert ev["has_greeks"] and ev["has_delta"]
    assert ev["has_implied_volatility"] and ev["has_open_interest"]
    assert ev["results_count"] == 1
    ev2 = mep._ev_options_chain({"results": [{}]})
    assert ev2["has_greeks"] is False and ev2["has_open_interest"] is False


# --------------------------------------------------------------------------- misc units
def test_previous_business_day_skips_weekends_and_holidays():
    from datetime import date
    assert mep.previous_business_day(date(2026, 8, 10)) == "2026-08-07"   # Mon -> Fri
    assert mep.previous_business_day(date(2026, 8, 8)) == "2026-08-07"    # Sat -> Fri
    assert mep.previous_business_day(date(2026, 12, 26)) == "2026-12-24"  # skips Christmas
    assert mep.previous_business_day(date(2026, 1, 2)) == "2025-12-31"    # crosses the year


def test_ns_timestamp_converts_to_iso_utc():
    assert mep._ns_to_iso(1_754_600_000_000_000_000).startswith("2025-08-")
    assert mep._ns_to_iso(None) is None
    assert mep._ns_to_iso("nope") is None
    assert mep._ns_to_iso(0) is None


def test_resolve_key_reports_the_env_var_name_not_the_value(monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.setenv("MASSIVE_API_KEY", FAKE_KEY)
    key, label = mep.resolve_key(None)
    assert key == FAKE_KEY and label == "MASSIVE_API_KEY"

    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    assert mep.resolve_key(None) == (None, "none")


def test_ws_probe_without_a_library_is_skipped_never_installed():
    rec = mep.probe_ws("wss://x.test/stocks", "T.AAPL", FAKE_KEY, lib_pair=(None, None))
    assert rec["evidence"] == {"status": "skipped_no_lib"}
    assert rec["verdict"] == "ambiguous"


class _FakeWS:
    """Minimal stand-in for a websockets/websocket-client connection."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.sent: list[dict] = []
        self.closed = False

    def send(self, text):
        self.sent.append(json.loads(text))

    def recv(self, timeout=None):
        if not self._frames:
            raise TimeoutError("no more frames")
        return json.dumps(self._frames.pop(0))

    def settimeout(self, t):
        pass

    def close(self):
        self.closed = True


def _ws_pair(frames):
    ws = _FakeWS(frames)
    lib = type("L", (), {"connect": staticmethod(lambda *a, **k: ws)})
    return ("websockets", lib), ws


def test_ws_auth_success_is_the_entitlement_verdict():
    pair, ws = _ws_pair([
        [{"ev": "status", "status": "connected"}],
        [{"ev": "status", "status": "auth_success"}],
        [{"ev": "status", "status": "success", "message": "subscribed to: T.AAPL"}],
        [{"ev": "T", "sym": "AAPL", "p": 1.0}],
    ])
    rec = mep.probe_ws("wss://x.test/stocks", "T.AAPL", FAKE_KEY, lib_pair=pair,
                       data_wait_s=1.0)
    assert rec["verdict"] == "entitled"
    assert rec["evidence"]["auth_status"] == "auth_success"
    assert rec["evidence"]["data_frames"] == 1
    assert ws.closed
    assert ws.sent[0]["action"] == "auth" and ws.sent[1]["action"] == "subscribe"


def test_ws_auth_failed_is_not_entitled_and_never_subscribes():
    pair, ws = _ws_pair([[{"ev": "status", "status": "auth_failed"}]])
    rec = mep.probe_ws("wss://x.test/stocks", "T.AAPL", FAKE_KEY, lib_pair=pair,
                       data_wait_s=1.0)
    assert rec["verdict"] == "not_entitled"
    assert [s["action"] for s in ws.sent] == ["auth"]


def test_ws_key_is_never_recorded_even_on_a_transport_error():
    def _boom(*a, **k):
        raise RuntimeError(f"handshake failed for wss://x.test?apiKey={FAKE_KEY}")

    pair = ("websockets", type("L", (), {"connect": staticmethod(_boom)}))
    rec = mep.probe_ws("wss://x.test/stocks", "T.AAPL", FAKE_KEY, lib_pair=pair)
    assert rec["verdict"] == "error"
    assert FAKE_KEY not in json.dumps(rec)


def test_ws_policy_violation_after_auth_is_ambiguous_not_a_denial():
    """1008 is Polygon's concurrent-connection ceiling as often as an entitlement refusal,
    and this probe opens four sockets in a row.  Publishing it as ``not_entitled`` would
    put a false capability gap in a manifest the masterplan cites as fact."""
    class ConnectionClosedError(Exception):
        rcvd = type("F", (), {"code": 1008})()

    class _WS(_FakeWS):
        def recv(self, timeout=None):
            if self.sent and self.sent[-1]["action"] == "subscribe":
                raise ConnectionClosedError("received 1008 (policy violation)")
            return super().recv(timeout)

    ws = _WS([[{"ev": "status", "status": "auth_success"}]])
    pair = ("websockets", type("L", (), {"connect": staticmethod(lambda *a, **k: ws)}))
    rec = mep.probe_ws("wss://delayed.test/stocks", "T.AAPL", FAKE_KEY, lib_pair=pair,
                       data_wait_s=1.0)
    assert rec["verdict"] == "ambiguous"
    assert rec["evidence"]["close_code"] == 1008
    assert rec["evidence"]["auth_status"] == "auth_success"
    assert rec["evidence"]["error"].startswith("ConnectionClosedError: ")


def test_ws_battery_pauses_between_clusters(monkeypatch):
    """Without the settle pause the four back-to-back sockets trip the connection cap."""
    naps: list[float] = []
    monkeypatch.setattr(mep, "_ws_lib", lambda: (None, None))
    monkeypatch.setattr("time.sleep", lambda s: naps.append(s))
    out = mep.run_ws_battery(FAKE_KEY, settle_s=1.5)
    assert list(out) == [n for n, _u, _s in mep.WS_CLUSTERS]
    assert naps == [1.5, 1.5, 1.5]                 # between clusters, not before the first


def test_ws_handshake_403_reads_as_not_entitled():
    class _Rejected(Exception):
        status_code = 403

    def _boom(*a, **k):
        raise _Rejected("server rejected WebSocket connection: HTTP 403")

    pair = ("websockets", type("L", (), {"connect": staticmethod(_boom)}))
    rec = mep.probe_ws("wss://x.test/indices", "V.I:SPX", FAKE_KEY, lib_pair=pair)
    assert rec["verdict"] == "not_entitled"
    assert rec["evidence"]["handshake_status"] == 403
