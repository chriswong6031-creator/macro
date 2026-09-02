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

import json
import urllib.error
import urllib.request
from collections import deque

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

    def fetch(self, symbols, view):
        self.calls += 1
        self.last_symbols = list(symbols)
        self.last_query = {"view": view}
        if self.raise_error is not None:
            raise self.raise_error
        return {s: dict(self.rows[s]) for s in symbols if s not in self.omitted}


@pytest.fixture()
def fake_hub(monkeypatch) -> FakeHub:
    hub = FakeHub()
    monkeypatch.setattr(market_pulse_api, "_fetch_hub_quotes", hub.fetch)
    # Freeze the route's evaluation clock to match the fixture rows' `ts` —
    # otherwise freshness ages every row into "stale" the instant real wall
    # time drifts past the fixture's fixed timestamp.
    monkeypatch.setattr(market_pulse_api, "_now_epoch_seconds", lambda: NOW)
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


def test_ext_leak_wins_over_sym_mismatch_and_still_503s(client, fake_hub):
    """A row that BOTH leaks an extended field AND carries the wrong `sym`
    must still 503 the whole batch — the ext-leak contract check runs BEFORE
    the sym-mismatch per-symbol skip (freeze review g2), so a leaking
    mismatched row can never be silently downgraded into a per-symbol
    `quote_unavailable` entry in a 200 response."""
    fake_hub.rows["AAPL"] = _valid_row("WRONG", extPrice=1.0)
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
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


@pytest.mark.parametrize("bad", ["../../etc/passwd", "AAPL;DROP", "a" * 40, "AAPL,", ",AAPL", ""])
def test_400_detail_is_a_fixed_opaque_literal_never_the_caller_input(client, fake_hub, bad):
    """Freeze review MINOR a1: the 400 body must never echo caller-supplied
    text, however malformed — a fixed literal only."""
    r = client.get(f"/api/intelligence-hub/market-pulse?symbols={bad}")
    assert r.status_code == 400
    assert r.json() == {"detail": "invalid_symbols"}
    for leaked in ("etc/passwd", "DROP", "a" * 40):
        assert leaked not in r.text


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


def test_many_concurrent_readers_of_the_full_roster_pass_the_peer_bucket(client, fake_hub):
    """b1: the peer bucket is now charged one unit per REQUEST (600/60s), not
    per symbol — many distinct readers (distinct client identities) each
    polling the full 58-name roster must still clear the SHARED peer bucket
    comfortably, the exact workload this route exists to serve."""
    symbols = ",".join(f"T{i:03d}" for i in range(58))
    codes = []
    for i in range(400):  # well under the 600 req/60s peer cap
        r = client.get(
            f"/api/intelligence-hub/market-pulse?symbols={symbols}",
            headers={"EO-Connecting-IP": f"203.0.113.{i % 250}"},
        )
        codes.append(r.status_code)
    assert 429 not in codes


def test_amplification_by_request_count_still_429s_the_peer_bucket(client, fake_hub):
    """b1: a flood of many SMALL requests behind one shared peer identity must
    still 429 once it crosses 600 requests/60s, even though each request's
    low symbol count keeps the (symbol-weighted) per-client bucket nowhere
    near its own limit — proving the peer bucket is charged per-REQUEST, not
    per-symbol."""
    codes = set()
    for i in range(650):
        r = client.get(
            "/api/intelligence-hub/market-pulse?symbols=AAPL",
            headers={"EO-Connecting-IP": f"198.51.100.{i % 250}"},
        )
        codes.add(r.status_code)
        if 429 in codes:
            break
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


def test_malformed_upstream_payload_is_503(client, monkeypatch):
    """Drives the REAL `_fetch_hub_quotes` (its actual two-parameter
    ``(symbols, view)`` signature, not a stand-in double) so this test
    exercises the function's own 'quote hub response was not an object'
    branch — asserting exactly 503, not merely 'some 5xx from some
    exception'."""
    body = json.dumps(["not", "an", "object"]).encode("utf-8")
    opener = _FakeOpener(body)
    monkeypatch.setattr(market_pulse_api, "_NO_REDIRECT_OPENER", opener)
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.status_code == 503


# ── the REAL _fetch_hub_quotes (not the fake_hub double above) ─────────────
#
# fake_hub replaces `_fetch_hub_quotes` wholesale, so it can never prove what
# that function itself puts on the wire. These tests fake only the transport
# opener one layer down, exercising the real function body: URL/query
# construction, the single-call contract, and the loopback assertion.

class _FakeUpstreamResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n: int = -1) -> bytes:
        return self._body[:n] if n and n > 0 else self._body


class _FakeOpener:
    def __init__(self, body: bytes):
        self.body = body
        self.calls: list[str] = []
        self.timeouts: list[float | None] = []

    def open(self, req, timeout=None):
        self.calls.append(req.full_url)
        self.timeouts.append(timeout)
        return _FakeUpstreamResponse(self.body)


def test_real_fetch_asks_for_view_regular_exactly_once_no_retry(monkeypatch):
    body = json.dumps({"AAPL": _valid_row("AAPL")}).encode("utf-8")
    opener = _FakeOpener(body)
    monkeypatch.setattr(market_pulse_api, "_NO_REDIRECT_OPENER", opener)
    result = market_pulse_api._fetch_hub_quotes(["AAPL", "MSFT"], view="regular")
    assert len(opener.calls) == 1  # never retried
    assert "view=regular" in opener.calls[0]
    assert result["AAPL"]["sym"] == "AAPL"


def test_real_fetch_never_falls_back_to_full_view(monkeypatch):
    """`view` is a required explicit parameter with no default — a caller
    that omits it is a type error, not a silent full-view fallback."""
    body = json.dumps({"AAPL": _valid_row("AAPL")}).encode("utf-8")
    opener = _FakeOpener(body)
    monkeypatch.setattr(market_pulse_api, "_NO_REDIRECT_OPENER", opener)
    market_pulse_api._fetch_hub_quotes(["AAPL"], view="regular")
    assert all("view=full" not in call and "view=regular" in call for call in opener.calls)
    with pytest.raises(TypeError):
        market_pulse_api._fetch_hub_quotes(["AAPL"])  # type: ignore[call-arg]


def test_real_fetch_is_loopback_only(monkeypatch):
    monkeypatch.setattr(market_pulse_api, "_HUB_BASE", "http://evil.example.com")
    with pytest.raises(ValueError):
        market_pulse_api._fetch_hub_quotes(["AAPL"], view="regular")


def test_the_hub_base_must_be_loopback():
    market_pulse_api._assert_loopback("http://127.0.0.1:3100")
    market_pulse_api._assert_loopback("http://localhost:3100")
    for remote in ("http://evil.example.com:3100", "http://10.0.0.5:3100"):
        with pytest.raises(ValueError):
            market_pulse_api._assert_loopback(remote)


def test_real_fetch_passes_the_configured_timeout_to_the_opener(monkeypatch):
    body = json.dumps({"AAPL": _valid_row("AAPL")}).encode("utf-8")
    opener = _FakeOpener(body)
    monkeypatch.setattr(market_pulse_api, "_NO_REDIRECT_OPENER", opener)
    market_pulse_api._fetch_hub_quotes(["AAPL"], view="regular")
    assert opener.timeouts == [market_pulse_api._HUB_TIMEOUT_SECONDS] == [2.5]


def test_real_fetch_refuses_a_response_over_the_256kib_cap(monkeypatch):
    """The oversized-body bound must be checked against the REAL read, not a
    stand-in — a body over 256KiB must never be decoded."""
    oversized = b"{" + (b'"A":1,' * 50_000) + b'"pad":1}'
    assert len(oversized) > market_pulse_api._HUB_MAX_BYTES
    opener = _FakeOpener(oversized)
    monkeypatch.setattr(market_pulse_api, "_NO_REDIRECT_OPENER", opener)
    with pytest.raises(ValueError, match="exceeded the bounded read size"):
        market_pulse_api._fetch_hub_quotes(["AAPL"], view="regular")


def test_oversized_upstream_body_is_503_through_the_route(client, monkeypatch):
    oversized = b"{" + (b'"A":1,' * 50_000) + b'"pad":1}'
    opener = _FakeOpener(oversized)
    monkeypatch.setattr(market_pulse_api, "_NO_REDIRECT_OPENER", opener)
    r = client.get("/api/intelligence-hub/market-pulse?symbols=AAPL")
    assert r.status_code == 503


# ── bounded identity-cardinality rate-limit store ───────────────────────────

def test_rate_limit_bucket_store_evicts_the_oldest_key_once_bounded():
    """`_RATE_LIMIT_MAX_KEYS` is a bound on the STORE, not merely a number in
    a comment — fill it past capacity and prove the single oldest key (by its
    bucket's own last-seen time) is the one evicted, and the bound holds."""
    market_pulse_api._reset_rate_limit_for_tests()
    buckets = market_pulse_api._rate_limit_buckets
    try:
        for i in range(market_pulse_api._RATE_LIMIT_MAX_KEYS):
            buckets[f"seed:{i}"] = deque([(float(i), 1)])
        assert len(buckets) == market_pulse_api._RATE_LIMIT_MAX_KEYS

        ok = market_pulse_api._book_rate_limit(
            "new-key", units=1, limit=999_999,
            current=float(market_pulse_api._RATE_LIMIT_MAX_KEYS), cutoff=-1e9,
        )
        assert ok is True
        assert "seed:0" not in buckets, "the single oldest key must be evicted"
        assert "seed:1" in buckets, "eviction must not over-evict"
        assert "new-key" in buckets
        assert len(buckets) == market_pulse_api._RATE_LIMIT_MAX_KEYS
    finally:
        market_pulse_api._reset_rate_limit_for_tests()
