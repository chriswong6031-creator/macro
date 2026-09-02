"""The deliberately public Intelligence Hub Market Pulse batch route.

``GET /api/intelligence-hub/market-pulse?symbols=NVDA,AAPL,MSFT`` is the ONE
public batch projection the Intelligence Hub roster controller calls. It
makes exactly one loopback ``view=regular`` request to the Terminal Quote Hub
per incoming call, never falls back to the default/full view, and refuses
(503) rather than strips-and-continues on any upstream contract violation
(an ``ext*`` field anywhere in a returned row).

Access is DELIBERATELY PUBLIC (see app/intelligence_hub_market_pulse.py's
module docstring for the decision) — this file's very first test proves an
anonymous, unauthenticated client can use the route.
"""
from __future__ import annotations

import urllib.error
import urllib.request

import pytest

pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app import intelligence_hub_market_pulse as market_pulse_api  # noqa: E402
from app.main import app  # noqa: E402

NOW = 1787871758.0 + 5


def _valid_row(sym: str, **overrides) -> dict:
    row = {
        "sym": sym, "last": 100.0, "prevClose": 95.0, "chg": 5.263157894736842,
        "ts": NOW, "live": True, "basis": "REALTIME", "marketSession": "regular",
        "regularSession": "rth", "regularSessionDate": "2026-08-31",
    }
    row.update(overrides)
    return row


class _AutoRows(dict):
    """Auto-vivifies a valid default row for any symbol on first access —
    lets a test mutate `fake_hub.rows["AAPL"]["extPrice"] = ...` without a
    setup step."""

    def __missing__(self, sym):
        row = _valid_row(sym)
        self[sym] = row
        return row


class FakeHub:
    def __init__(self):
        self.calls = 0
        self.last_query: dict = {}
        self.last_symbols: list[str] = []
        self.rows = _AutoRows()
        self.omitted: set[str] = set()
        self.raise_error: Exception | None = None

    def fetch(self, symbols):
        self.calls += 1
        self.last_symbols = list(symbols)
        self.last_query = {"view": "regular"}
        if self.raise_error is not None:
            raise self.raise_error
        return {s: dict(self.rows[s]) for s in symbols if s not in self.omitted}


@pytest.fixture()
def fake_hub(monkeypatch) -> FakeHub:
    hub = FakeHub()
    monkeypatch.setattr(market_pulse_api, "_fetch_hub_quotes", hub.fetch)
    return hub


@pytest.fixture()
def client() -> TestClient:
    market_pulse_api._reset_rate_limit_for_tests()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    market_pulse_api._reset_rate_limit_for_tests()


# ── deliberate public access ────────────────────────────────────────────────

def test_route_is_reachable_without_authentication(client, fake_hub):
    """No cookie, no bearer token, no api key — this route is deliberately
    public (see the module docstring's access decision)."""
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.status_code == 200
    assert r.status_code not in (401, 403)


def test_response_is_never_cached(client, fake_hub):
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert "no-store" in r.headers.get("Cache-Control", "")


# ── one Terminal call, regular view, no fallback ────────────────────────────

def test_route_uses_one_regular_view_upstream_call(client, fake_hub):
    symbols = ",".join(f"T{i:02d}" for i in range(58))
    response = client.get(f"/api/intelligence-hub/market-pulse?symbols={symbols}")
    assert response.status_code == 200
    assert fake_hub.calls == 1
    assert fake_hub.last_query["view"] == "regular"
    assert fake_hub.last_symbols == [f"T{i:02d}" for i in range(58)]


def test_upstream_failure_is_503_never_a_fallback_call(client, fake_hub):
    fake_hub.raise_error = OSError("connection refused")
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.status_code == 503
    assert fake_hub.calls == 1  # never retried


def test_regular_view_ext_field_leak_is_503(client, fake_hub):
    fake_hub.rows["AAPL"]["extPrice"] = 201.0
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.status_code == 503
    assert r.json() == {"detail": "quote_projection_unavailable"}


@pytest.mark.parametrize(
    "ext_key", ["extPrice", "extChg", "extTs", "extSession", "extSource", "extBasis"],
)
def test_every_extended_field_leak_is_refused(client, fake_hub, ext_key):
    fake_hub.rows["AAPL"][ext_key] = "poison"
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.status_code == 503


def test_a_leak_on_one_symbol_refuses_the_whole_batch_not_just_that_symbol(client, fake_hub):
    """A contract violation is proof the upstream promise was broken, not a
    per-symbol data quality issue — one leaking row invalidates the batch."""
    fake_hub.rows["AAPL"]["extPrice"] = 1.0
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL,MSFT")
    assert r.status_code == 503


# ── order / dedupe / bounds ─────────────────────────────────────────────────

def test_input_order_is_preserved_and_duplicates_are_deduped(client, fake_hub):
    r = client.get("/api/intelligence-hub/market-pulse?symbols=MSFT,AAPL,MSFT,NVDA")
    assert r.status_code == 200
    assert fake_hub.last_symbols == ["MSFT", "AAPL", "NVDA"]
    body = r.json()
    assert [item["symbol"] for item in body["items"]] == ["MSFT", "AAPL", "NVDA"]


def test_zero_symbols_is_400(client, fake_hub):
    assert client.get("/api/intelligence-hub/market-pulse?symbols=").status_code == 400
    assert client.get("/api/intelligence-hub/market-pulse").status_code == 400
    assert fake_hub.calls == 0


def test_more_than_sixty_unique_symbols_is_400(client, fake_hub):
    symbols = ",".join(f"T{i:03d}" for i in range(61))
    r = client.get(f"/api/intelligence-hub/market-pulse?symbols={symbols}")
    assert r.status_code == 400
    assert fake_hub.calls == 0


def test_exactly_sixty_unique_symbols_is_accepted(client, fake_hub):
    symbols = ",".join(f"T{i:03d}" for i in range(60))
    r = client.get(f"/api/intelligence-hub/market-pulse?symbols={symbols}")
    assert r.status_code == 200


@pytest.mark.parametrize("bad", ["../../etc/passwd", "AAPL;DROP", "a" * 40, "AAPL,", ",AAPL"])
def test_an_invalid_member_refuses_the_whole_request_not_a_silent_drop(client, fake_hub, bad):
    r = client.get(f"/api/intelligence-hub/market-pulse?symbols={bad}")
    assert r.status_code == 400
    assert fake_hub.calls == 0


# ── complete / partial / zero usable ────────────────────────────────────────

def test_complete_coverage_when_every_symbol_resolves(client, fake_hub):
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL,MSFT")
    body = r.json()
    assert body["state"]["coverage"] == "complete"
    assert body["coverage"] == {
        "requested": 2, "resolved": 2, "live": 2, "delayed": 0, "stale": 0, "missing": 0,
    }


def test_partial_coverage_keeps_missing_symbols_out_of_items_and_in_errors(client, fake_hub):
    fake_hub.omitted.add("MSFT")
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL,MSFT")
    assert r.status_code == 200
    body = r.json()
    assert body["state"]["coverage"] == "partial"
    assert body["coverage"]["missing"] == 1
    assert [i["symbol"] for i in body["items"]] == ["AAPL"]
    assert body["errors"] == [{"symbol": "MSFT", "code": "quote_unavailable"}]


def test_zero_usable_items_is_503(client, fake_hub):
    fake_hub.omitted.add("AAPL")
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.status_code == 503


# ── exact state arithmetic ───────────────────────────────────────────────────

def test_resolved_plus_missing_equals_requested(client, fake_hub):
    fake_hub.omitted.add("NVDA")
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL,MSFT,NVDA")
    cov = r.json()["coverage"]
    assert cov["resolved"] + cov["missing"] == cov["requested"]


def test_live_plus_delayed_plus_stale_equals_resolved(client, fake_hub):
    fake_hub.rows["AAPL"] = _valid_row("AAPL", live=True, basis="REALTIME", marketSession="regular")
    fake_hub.rows["MSFT"] = _valid_row("MSFT", live=False, basis="DELAYED_15M")
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL,MSFT")
    cov = r.json()["coverage"]
    assert cov["live"] + cov["delayed"] + cov["stale"] == cov["resolved"]
    assert cov["live"] == 1
    assert cov["delayed"] == 1


def test_freshness_state_is_the_conservative_worst_resolved_item(client, fake_hub):
    fake_hub.rows["AAPL"] = _valid_row("AAPL", live=True, basis="REALTIME", marketSession="regular")
    fake_hub.rows["MSFT"] = _valid_row("MSFT", ts=NOW - 100_000)  # ages into stale
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL,MSFT")
    assert r.json()["state"]["freshness"] == "stale"


def test_session_state_is_regular_only_when_every_resolved_item_is_regular(client, fake_hub):
    fake_hub.rows["AAPL"] = _valid_row("AAPL", marketSession="regular", regularSession="rth")
    fake_hub.rows["MSFT"] = _valid_row("MSFT", marketSession="regular", regularSession="rth")
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL,MSFT")
    assert r.json()["state"]["session"] == "regular"


def test_session_state_is_never_regular_over_a_mix(client, fake_hub):
    fake_hub.rows["AAPL"] = _valid_row("AAPL", marketSession="regular", regularSession="rth")
    fake_hub.rows["MSFT"] = _valid_row(
        "MSFT", marketSession="overnight", regularSession="closed", live=False, basis="DELAYED_15M",
    )
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL,MSFT")
    assert r.json()["state"]["session"] in ("mixed", "closed")
    assert r.json()["state"]["session"] != "regular"


def test_source_view_is_always_regular(client, fake_hub):
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.json()["source_view"] == "regular"


# ── debranding ───────────────────────────────────────────────────────────────

def test_no_provider_source_basis_or_anchor_reaches_the_response(client, fake_hub):
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    raw = r.text.lower()
    for leaked in ("polygon", "yahoo", "webull", "alpaca", "okx", "coinbase", "massive", "realtime", "delayed_15m"):
        assert leaked not in raw, f"vendor/basis leak: {leaked!r}"
    for item in r.json()["items"]:
        for dropped in ("source", "basis", "anchor_source"):
            assert dropped not in item


# ── no server sequence / cursor / correction store ──────────────────────────

def test_envelope_carries_no_sequence_or_cursor_field(client, fake_hub):
    body = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL").json()
    for forbidden in ("sequence", "seq", "cursor", "correction"):
        assert forbidden not in body


def test_snapshot_id_is_opaque_identity_only_and_varies_per_request(client, fake_hub):
    body1 = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL").json()
    body2 = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL").json()
    assert body1["snapshot_id"] != body2["snapshot_id"]


# ── symbol-weighted rate limit ───────────────────────────────────────────────

def test_normal_58_symbol_60_second_cadence_passes(client, fake_hub):
    symbols = ",".join(f"T{i:03d}" for i in range(58))
    codes = []
    for _ in range(4):  # steady refresh + a manual/resume margin
        codes.append(client.get(f"/api/intelligence-hub/market-pulse?symbols={symbols}").status_code)
    assert 429 not in codes


def test_amplification_is_refused(client, fake_hub):
    symbols = ",".join(f"T{i:03d}" for i in range(58))
    codes = {
        client.get(f"/api/intelligence-hub/market-pulse?symbols={symbols}").status_code
        for _ in range(60)
    }
    assert 429 in codes


def test_an_invalid_request_never_spends_rate_budget(client, fake_hub):
    for _ in range(50):
        client.get("/api/intelligence-hub/market-pulse?symbols=..%2F..%2Fetc")
    # the whole 58-name budget must still be available afterwards
    symbols = ",".join(f"T{i:03d}" for i in range(58))
    assert client.get(f"/api/intelligence-hub/market-pulse?symbols={symbols}").status_code == 200


# ── redirect / timeout / oversize / malformed upstream ───────────────────────

def test_a_redirecting_hub_is_refused_not_followed():
    handler = market_pulse_api._NoRedirects()
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(
            urllib.request.Request("http://127.0.0.1:3100/quotes"),
            None, 302, "Found", {}, "http://elsewhere.example/",
        )


def test_malformed_upstream_payload_is_503(client, fake_hub, monkeypatch):
    monkeypatch.setattr(market_pulse_api, "_fetch_hub_quotes", lambda syms: "not-an-object")
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.status_code in (500, 503)


def test_the_hub_base_must_be_loopback():
    market_pulse_api._assert_loopback("http://127.0.0.1:3100")
    market_pulse_api._assert_loopback("http://localhost:3100")
    for remote in ("http://evil.example.com:3100", "http://10.0.0.5:3100"):
        with pytest.raises(ValueError):
            market_pulse_api._assert_loopback(remote)
