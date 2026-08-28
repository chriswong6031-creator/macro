"""Public dossier quote projection — the honesty boundary for a live US price.

The dossier used to bake a nightly price into HTML and print a decorative
"Live" stamp beside it.  On 2026-08-27 that shipped NVDA at $209.66 with a
static ``-$3.39 · -1.59%`` while the measured regular-session close was
$227.98 (+8.74%) — the page claimed "Live" while showing the PREVIOUS close
and a previous-day move.  That is the defect this route exists to make
impossible.

The tests below pin the three properties that keep it impossible:

1. The route never invents freshness.  ``live`` is returned only when the
   upstream quote plane itself asserts a measured realtime row AND that row's
   own timestamp is inside the accepted bound.  A delayed basis, a stale
   timestamp, or a missing clock all fail CLOSED to an honest weaker state.
2. The regular-session move is computed from the regular-session fields only.
   An extended-hours print must never become the regular-session percentage.
3. The projection is allowlisted and debranded.  No vendor name, no raw
   upstream payload, no transport internals reach the browser.
"""
from __future__ import annotations

import urllib.request

import pytest

pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app import dossier_quote as dossier_quote_api  # noqa: E402
from app.main import app  # noqa: E402


# A verbatim capture of the running Quote Hub's reply for NVDA on 2026-08-27
# at 23:22Z (VPS 127.0.0.1:3100/quotes?syms=NVDA).  Keeping the real shape —
# including the fields we deliberately drop — is what makes the debranding and
# allowlist assertions meaningful rather than self-referential.
HUB_NVDA_DELAYED = {
    "NVDA": {
        "sym": "NVDA",
        "last": 227.98,
        "ts": 1787871758,
        "live": False,
        "source": "polygon-snapshot",
        "market": "us",
        "basis": "DELAYED_15M",
        "regularSession": "rth",
        "close": 227.98,
        "prevClose": 209.66,
        "chg": 8.7379566917867,
        "anchor_source": "snapshot",
        "marketSession": "post",
        "open": 222.86,
        "high": 230.47,
        "low": 220.9,
        "vol": 298009663,
        "regularSessionDate": "2026-08-27",
        "asOfMs": 1787871758052.0442,
        "lagMs": 21676.955810546875,
        "extPrice": 226.25,
        "extChg": -0.7588384946047855,
        "extTs": 1787872020,
        "extSession": "post",
        "extSource": "polygon-delayed",
        "extBasis": "DELAYED_15M",
    }
}


def _hub_row(**overrides):
    row = dict(HUB_NVDA_DELAYED["NVDA"])
    row.update(overrides)
    return {"NVDA": row}


@pytest.fixture()
def client() -> TestClient:
    dossier_quote_api._reset_rate_limit_for_tests()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    dossier_quote_api._reset_rate_limit_for_tests()


def _patch_hub(monkeypatch, payload, *, now: float | None = None):
    monkeypatch.setattr(dossier_quote_api, "_read_hub_quotes", lambda sym: payload)
    if now is not None:
        monkeypatch.setattr(dossier_quote_api, "_now_epoch_seconds", lambda: now)


# ── 1. freshness can never be fabricated ────────────────────────────────────

def test_delayed_basis_can_never_report_live(client, monkeypatch) -> None:
    """The exact production row that shipped the defect must not read `live`."""
    _patch_hub(monkeypatch, HUB_NVDA_DELAYED, now=1787871758 + 5)
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["freshness"] == "delayed"
    assert body["freshness"] != "live"


def test_realtime_flag_alone_cannot_produce_live_while_basis_is_delayed(client, monkeypatch) -> None:
    """A truthy `live` flag contradicted by a delayed basis fails closed.

    Two independent upstream assertions must agree.  If they disagree the
    weaker one wins — that is what stops one flipped flag from minting LIVE.
    """
    _patch_hub(monkeypatch, _hub_row(live=True), now=1787871758 + 5)
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["freshness"] == "delayed"


def test_realtime_row_older_than_the_bound_is_not_live(client, monkeypatch) -> None:
    """Even a genuine realtime basis goes stale once its own clock ages out."""
    _patch_hub(
        monkeypatch,
        _hub_row(live=True, basis="REALTIME", marketSession="regular"),
        now=1787871758 + 4000,
    )
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["freshness"] == "stale"


def test_a_measured_fresh_realtime_regular_row_is_the_only_live_case(client, monkeypatch) -> None:
    """The one positive case — proves the guard discriminates, not just refuses."""
    _patch_hub(
        monkeypatch,
        _hub_row(live=True, basis="REALTIME", marketSession="regular"),
        now=1787871758 + 5,
    )
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["freshness"] == "live"
    assert body["session"] == "regular"


def test_a_settled_after_hours_close_is_not_called_stale(client, monkeypatch) -> None:
    """A final regular-session close legitimately stops advancing.

    Upstream stamps `ts` from the vendor's print clock, so hours after the bell
    a correct close is hours old.  Marking it "stale" would send the page back
    to its baked value — reintroducing the very defect this route removes — so
    the staleness bound is session-aware.
    """
    _patch_hub(monkeypatch, HUB_NVDA_DELAYED, now=1787871758 + 5 * 3600)
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["freshness"] == "delayed"
    assert body["session"] == "post"
    assert body["price"] == pytest.approx(227.98)


def test_a_dead_hub_still_fails_closed_outside_regular_hours(client, monkeypatch) -> None:
    """The relaxed after-hours bound must not become "never stale"."""
    _patch_hub(monkeypatch, HUB_NVDA_DELAYED, now=1787871758 + 9 * 24 * 3600)
    assert client.get("/api/dossier-quote/NVDA").json()["freshness"] == "stale"


def test_a_far_future_clock_is_a_fault_not_a_fresh_quote(client, monkeypatch) -> None:
    """A negative age must not sail through both age gates into "live".

    This guard is easy to delete because it reads like a paranoid edge case. It
    is not: a negative age passes `age > bound` (false) AND satisfies
    `age <= _LIVE_MAX_AGE_SECONDS`, so without it any upstream clock fault — a
    timezone slip, or millis stamped into a seconds field — MINTS the one
    verdict this module exists to make unfakeable.
    """
    _patch_hub(
        monkeypatch,
        _hub_row(live=True, basis="REALTIME", marketSession="regular"),
        now=1787871758 - 86_400,
    )
    assert client.get("/api/dossier-quote/NVDA").json()["freshness"] == "stale"


def test_millis_in_the_seconds_field_cannot_read_as_live(client, monkeypatch) -> None:
    """The concrete shape of the clock fault above, using a real magnitude."""
    _patch_hub(
        monkeypatch,
        _hub_row(live=True, basis="REALTIME", marketSession="regular", ts=1787871758_000),
        now=1787871758,
    )
    assert client.get("/api/dossier-quote/NVDA").json()["freshness"] == "stale"


def test_missing_timestamp_fails_closed_rather_than_assuming_fresh(client, monkeypatch) -> None:
    row = _hub_row(live=True, basis="REALTIME", marketSession="regular")
    row["NVDA"].pop("ts")
    _patch_hub(monkeypatch, row, now=1787871758 + 5)
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["freshness"] != "live"


# ── 2. regular-session semantics ────────────────────────────────────────────

def test_regular_session_move_never_uses_the_extended_hours_print(client, monkeypatch) -> None:
    """`extPrice`/`extChg` are a different session and must not leak into the move.

    In the captured row the extended print is DOWN 0.76% while the regular
    session was UP 8.74%.  Rendering the after-hours number as the day move
    would invert the sign the reader acts on.
    """
    _patch_hub(monkeypatch, HUB_NVDA_DELAYED, now=1787871758 + 5)
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["price"] == pytest.approx(227.98)
    assert body["prev_close"] == pytest.approx(209.66)
    assert body["change_pct"] == pytest.approx(8.7379566917867)
    assert body["change_abs"] == pytest.approx(18.32, abs=1e-6)
    # the extended print and its percentage must be absent entirely
    assert body["change_pct"] != pytest.approx(-0.7588384946047855)
    assert 226.25 not in body.values()


def test_change_abs_is_derived_not_read_from_the_percent_field(client, monkeypatch) -> None:
    """`chg` upstream is a PERCENT.  Treating it as dollars is the trap."""
    _patch_hub(monkeypatch, _hub_row(last=120.0, prevClose=100.0, chg=20.0), now=1787871758 + 5)
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["change_abs"] == pytest.approx(20.0)
    assert body["change_pct"] == pytest.approx(20.0)
    # a real discrimination case: same percent, different dollars
    _patch_hub(monkeypatch, _hub_row(last=60.0, prevClose=50.0, chg=20.0), now=1787871758 + 5)
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["change_abs"] == pytest.approx(10.0)
    assert body["change_pct"] == pytest.approx(20.0)


# ── 3. allowlist + debrand ──────────────────────────────────────────────────

def test_projection_is_debranded_and_carries_no_upstream_transport(client, monkeypatch) -> None:
    _patch_hub(monkeypatch, HUB_NVDA_DELAYED, now=1787871758 + 5)
    raw = client.get("/api/dossier-quote/NVDA").text.lower()
    for leaked in ("polygon", "yahoo", "webull", "alpaca", "okx", "coinbase", "massive"):
        assert leaked not in raw, f"vendor branding {leaked!r} reached the browser"
    body = client.get("/api/dossier-quote/NVDA").json()
    for dropped in (
        "source", "anchor_source", "extSource", "basis", "extBasis",
        "extPrice", "extChg", "extTs", "asOfMs", "lagMs", "vol",
    ):
        assert dropped not in body


def test_response_is_never_cached(client, monkeypatch) -> None:
    _patch_hub(monkeypatch, HUB_NVDA_DELAYED, now=1787871758 + 5)
    resp = client.get("/api/dossier-quote/NVDA")
    assert "no-store" in resp.headers.get("Cache-Control", "")


# ── 4. input + upstream failure handling ────────────────────────────────────

@pytest.mark.parametrize("bad", ["../../etc/passwd", "NVDA;DROP", "a" * 40, "", "  "])
def test_invalid_ticker_is_refused_before_the_hub_is_called(client, monkeypatch, bad) -> None:
    called = {"n": 0}

    def _boom(sym):
        called["n"] += 1
        raise AssertionError("hub must not be called for an invalid ticker")

    monkeypatch.setattr(dossier_quote_api, "_read_hub_quotes", _boom)
    resp = client.get(f"/api/dossier-quote/{bad}")
    assert resp.status_code in (404, 422)
    assert called["n"] == 0


def test_hub_down_degrades_and_never_yields_a_price(client, monkeypatch) -> None:
    def _down(sym):
        raise OSError("connection refused")

    monkeypatch.setattr(dossier_quote_api, "_read_hub_quotes", _down)
    resp = client.get("/api/dossier-quote/NVDA")
    assert resp.status_code == 503
    assert "live" not in resp.text.lower() or "unavailable" in resp.text.lower()


def test_malformed_hub_payload_is_refused_rather_than_half_rendered(client, monkeypatch) -> None:
    _patch_hub(monkeypatch, {"NVDA": {"sym": "NVDA", "last": "not-a-number"}}, now=1787871758)
    assert client.get("/api/dossier-quote/NVDA").status_code == 503


def test_unknown_symbol_is_a_stable_404(client, monkeypatch) -> None:
    _patch_hub(monkeypatch, {}, now=1787871758)
    assert client.get("/api/dossier-quote/ZZZZ").status_code == 404


def test_hub_row_for_a_different_symbol_is_never_accepted(client, monkeypatch) -> None:
    """A row that names a DIFFERENT symbol must not be painted onto this page.

    Keyed under the requested ticker on purpose.  Asking for /AMD against a
    payload keyed only "NVDA" proves nothing about this guard — the 404 comes
    from the missing key long before the identity check runs, so the check
    could be deleted outright and that test would still pass.
    """
    _patch_hub(monkeypatch, {"NVDA": dict(HUB_NVDA_DELAYED["NVDA"], sym="AMD")}, now=1787871758 + 5)
    assert client.get("/api/dossier-quote/NVDA").status_code == 404


def test_a_row_that_does_not_identify_itself_is_refused(client, monkeypatch) -> None:
    """Identity must be PRESENT, not merely non-contradictory.

    Guarding on `isinstance(row_sym, str) and ...` let a row with no `sym` skip
    the check entirely and publish whatever price it carried.
    """
    anonymous = dict(HUB_NVDA_DELAYED["NVDA"])
    anonymous.pop("sym")
    _patch_hub(monkeypatch, {"NVDA": anonymous}, now=1787871758 + 5)
    assert client.get("/api/dossier-quote/NVDA").status_code == 404


def test_a_non_regular_session_print_is_refused(client, monkeypatch) -> None:
    """`regularSession` is the hub's positive evidence that `last` is an RTH print."""
    _patch_hub(monkeypatch, _hub_row(regularSession="post"), now=1787871758 + 5)
    assert client.get("/api/dossier-quote/NVDA").status_code == 503


def test_the_live_bound_is_the_documented_one_not_the_stale_bound(client, monkeypatch) -> None:
    """Pins _LIVE_MAX_AGE_SECONDS itself, which is a documented decision.

    Relaxing 120s to the 900s staleness bound used to pass the whole suite, so
    the headline claim — "deliberately tighter than upstream's generous 15-minute
    per-name bound" — was enforced by nothing.  300s is inside 900 and outside
    120: it must read `delayed`.
    """
    _patch_hub(
        monkeypatch,
        _hub_row(live=True, basis="REALTIME", marketSession="regular"),
        now=1787871758 + 300,
    )
    assert client.get("/api/dossier-quote/NVDA").json()["freshness"] == "delayed"


@pytest.mark.parametrize("basis", ["15M", "IEX_ONLY", "SOMETHING_NEW", ""])
def test_an_unrecognised_basis_is_not_proven_realtime(client, monkeypatch, basis) -> None:
    """The screen is an allowlist.  A denylist of delayed-looking words is
    fail-OPEN: `15M` and `IEX_ONLY` contain none of them and both read live."""
    _patch_hub(
        monkeypatch,
        _hub_row(live=True, basis=basis, marketSession="regular"),
        now=1787871758 + 5,
    )
    assert client.get("/api/dossier-quote/NVDA").json()["freshness"] == "delayed"


def test_a_percent_that_contradicts_the_price_pair_is_replaced(client, monkeypatch) -> None:
    """Upstream's percent and our derived dollar move are two DIFFERENT sources.

    The hub picks its anchor at runtime.  When they disagree the page renders a
    correct dollar move beside a percent from another session — "+$18.32 ·
    -0.76%", green, both wrong together.  One internally consistent pair beats a
    more authoritative number that contradicts its neighbour.
    """
    _patch_hub(monkeypatch, _hub_row(chg=-0.7588384946047855), now=1787871758 + 5)
    body = client.get("/api/dossier-quote/NVDA").json()
    assert body["change_abs"] == pytest.approx(18.32, abs=1e-6)
    assert body["change_pct"] == pytest.approx(8.7379566917867, abs=1e-6)


def test_the_hub_base_must_be_loopback() -> None:
    """A remote hub would turn a bounded projection into an egress path."""
    dossier_quote_api._assert_loopback("http://127.0.0.1:3100")
    dossier_quote_api._assert_loopback("http://localhost:3100")
    for remote in ("http://evil.example.com:3100", "http://10.0.0.5:3100", "http://[::2]:3100"):
        with pytest.raises(ValueError):
            dossier_quote_api._assert_loopback(remote)


def test_a_misconfigured_hub_disables_only_this_route(monkeypatch, client) -> None:
    """A bad env var must not be able to take the whole API down.

    As an import-time assertion this raised during `app.main` import and killed
    every unrelated route — billing, auth, paywall — over a dossier price.
    Per-request it is a 503 here and nothing anywhere else.
    """
    monkeypatch.setattr(dossier_quote_api, "_HUB_BASE", "http://evil.example.com")
    assert client.get("/api/dossier-quote/NVDA").status_code == 503
    # an unrelated route on the same app is untouched
    assert client.get("/api/company-intelligence/NVDA").status_code != 500


def test_a_redirecting_hub_is_refused_not_followed() -> None:
    """`urlopen` follows redirects; a 302 would republish a third party's price."""
    import urllib.error

    handler = dossier_quote_api._NoRedirects()
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(
            urllib.request.Request("http://127.0.0.1:3100/quotes"),
            None, 302, "Found", {}, "http://elsewhere.example/",
        )


def test_rate_limit_refuses_a_flood(client, monkeypatch) -> None:
    _patch_hub(monkeypatch, HUB_NVDA_DELAYED, now=1787871758 + 5)
    codes = {client.get("/api/dossier-quote/NVDA").status_code for _ in range(200)}
    assert 429 in codes
