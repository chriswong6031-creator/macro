"""tests/test_intelligence_hub_market_pulse_client.py — executes the pure
envelope-validation / candidate-ordering / coverage contract lifted from
``site/assets/js/intelligence-hub-market-pulse.js`` (between the
``IHMP-CONTRACT-BEGIN``/``END`` markers) under node, proving the atomicity
and ordering laws (freeze §9/§13) by EXECUTION rather than by reading the
source — the same idiom ``tests/test_live_breadth_js_contract.py`` uses for
``templates/live.js::applyBreadth``.

The remaining DOM/lifecycle responsibilities that the pure contract cannot
exercise on its own (target discovery, one-fetch-per-refresh, RAF-atomic
paint, hidden-tab pause/resume, the live-prices setting, and that this
controller never touches an intelligence rank/score/stage node) are proven
by static source assertions, matching
``tests/test_dossier_live_quote_surface.py``'s established methodology for
this exact class of route-scoped controller.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLIENT_PATH = ROOT / "site" / "assets" / "js" / "intelligence-hub-market-pulse.js"

_BEGIN = "/* IHMP-CONTRACT-BEGIN"
_END = "/* IHMP-CONTRACT-END */"


@pytest.fixture(scope="module")
def client_text() -> str:
    if not CLIENT_PATH.exists():
        pytest.skip("site/ is not checked out in this sparse worktree")
    return CLIENT_PATH.read_text(encoding="utf-8")


def _contract(client_text: str) -> str:
    a = client_text.index(_BEGIN)
    b = client_text.index(_END)
    assert a < b, f"{_BEGIN} must precede {_END}"
    return client_text[a:b]


_HARNESS = r"""
%(contract)s

function toMap(obj) {
  var m = new Map();
  Object.keys(obj || {}).forEach(function (k) { m.set(k, obj[k]); });
  return m;
}
function fromMap(m) {
  var o = {};
  m.forEach(function (v, k) { o[k] = v; });
  return o;
}

var cases = JSON.parse(process.argv[2]);
var out = cases.map(function (c) {
  if (c.op === 'validEnvelopeShape') {
    return { value: validEnvelopeShape(c.body) };
  }
  if (c.op === 'validItem') {
    return { value: validItem(c.item, new Set(c.requested)) };
  }
  if (c.op === 'buildCandidateModel') {
    var model = buildCandidateModel(c.body, c.orderedSymbols, toMap(c.lastGood));
    return { accepted: fromMap(model.accepted), suppressed: model.suppressed };
  }
  if (c.op === 'worstFreshness') {
    return { value: worstFreshness(toMap(c.accepted)) };
  }
  if (c.op === 'pageSession') {
    return { value: pageSession(toMap(c.accepted)) };
  }
  if (c.op === 'composeStatus') {
    return { value: composeStatus(c.acceptedCount, c.totalCount, c.freshness, c.session) };
  }
  throw new Error('unknown op ' + c.op);
});
console.log(JSON.stringify(out));
"""


def _run(client_text: str, cases: list) -> list:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError(
                "node is required to execute the IHMP client contract, and CI "
                "installs it via actions/setup-node@v4 — its absence means the "
                "setup step moved, which would leave the ordering/atomicity gate "
                "(reactive-projection freeze §9/§13) unproven."
            )
        pytest.skip("node not available to execute the client contract (local only)")
    src = _HARNESS % {"contract": _contract(client_text)}
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ihmp_contract.js"
        path.write_text(src)
        run = subprocess.run([node, str(path), json.dumps(cases)],
                              capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout)


def _item(**over):
    it = {
        "symbol": "AAPL", "price": 227.98, "change_abs": 18.32, "change_pct": 8.74,
        "currency": "USD", "session": "regular", "freshness": "live",
        "observed_at": "2026-08-31T14:31:00Z", "received_at": None,
        "published_at": "2026-08-31T14:31:10Z", "regular_session_date": "2026-08-31",
        "revision": "rev1",
    }
    it.update(over)
    return it


def _envelope(**over):
    body = {
        "schema": "intelligence_hub.market_pulse.v1",
        "projection": "intelligence_hub.market_pulse",
        "snapshot_id": "abc123",
        "generated_at": "2026-08-31T14:31:10Z",
        "source_owner": "terminal-market-data",
        "source_view": "regular",
        "state": {"availability": "available", "freshness": "live", "session": "regular", "coverage": "complete"},
        "coverage": {"requested": 1, "resolved": 1, "live": 1, "delayed": 0, "stale": 0, "missing": 0},
        "items": [_item()],
        "errors": [],
    }
    body.update(over)
    return body


# ── envelope shape validation (executed) ────────────────────────────────────

def test_valid_envelope_passes(client_text):
    out = _run(client_text, [{"op": "validEnvelopeShape", "body": _envelope()}])
    assert out[0]["value"] is True


@pytest.mark.parametrize("mutation", [
    {"schema": "wrong.v1"},
    {"projection": "wrong"},
    {"source_view": "full"},
    {"state": {"availability": "bogus", "freshness": "live", "session": "regular", "coverage": "complete"}},
    {"coverage": {"requested": 2, "resolved": 1, "live": 1, "delayed": 0, "stale": 0, "missing": 0}},  # resolved+missing != requested
    {"coverage": {"requested": 1, "resolved": 1, "live": 0, "delayed": 0, "stale": 0, "missing": 0}},  # live+delayed+stale != resolved
    {"items": "not-a-list"},
])
def test_malformed_envelope_shapes_are_refused(client_text, mutation):
    out = _run(client_text, [{"op": "validEnvelopeShape", "body": _envelope(**mutation)}])
    assert out[0]["value"] is False


def test_source_view_must_be_exactly_regular(client_text):
    out = _run(client_text, [{"op": "validEnvelopeShape", "body": _envelope(source_view="full")}])
    assert out[0]["value"] is False


# ── per-item validation: forbidden fields, unrequested symbols ─────────────

@pytest.mark.parametrize("ext_key", ["extPrice", "extChg", "source", "basis", "anchor_source"])
def test_forbidden_field_on_an_item_is_refused(client_text, ext_key):
    item = _item(**{ext_key: "poison"})
    out = _run(client_text, [{"op": "validItem", "item": item, "requested": ["AAPL"]}])
    assert out[0]["value"] is False


def test_unrequested_symbol_is_refused(client_text):
    out = _run(client_text, [{"op": "validItem", "item": _item(symbol="MSFT"), "requested": ["AAPL"]}])
    assert out[0]["value"] is False


def test_a_valid_item_passes(client_text):
    out = _run(client_text, [{"op": "validItem", "item": _item(), "requested": ["AAPL"]}])
    assert out[0]["value"] is True


# ── buildCandidateModel: ordering, duplicates, partial coverage (executed) ─

def test_partial_response_accepts_present_symbols_only(client_text):
    body = _envelope(items=[_item(symbol="AAPL")])
    out = _run(client_text, [{
        "op": "buildCandidateModel", "body": body,
        "orderedSymbols": ["AAPL", "MSFT"], "lastGood": {},
    }])
    assert list(out[0]["accepted"].keys()) == ["AAPL"]
    assert out[0]["suppressed"] == 0


def test_a_duplicate_response_symbol_only_accepts_the_first(client_text):
    body = _envelope(items=[_item(symbol="AAPL", revision="rev1"), _item(symbol="AAPL", revision="rev2")])
    out = _run(client_text, [{
        "op": "buildCandidateModel", "body": body,
        "orderedSymbols": ["AAPL"], "lastGood": {},
    }])
    assert out[0]["accepted"]["AAPL"]["revision"] == "rev1"


def test_older_source_time_is_suppressed_and_counted(client_text):
    # item's observed_at (2026-08-31T00:00:00Z = 1788134400000ms) is EARLIER
    # than the prior's own observedAtMs — the incoming item is stale.
    prior = {"AAPL": {"observedAtMs": 1788134400000 + 60_000, "revision": "rev1", "price": 100, "session": "regular", "freshness": "live"}}
    older_item = _item(observed_at="2026-08-31T00:00:00Z")
    body = _envelope(items=[older_item])
    out = _run(client_text, [{
        "op": "buildCandidateModel", "body": body,
        "orderedSymbols": ["AAPL"], "lastGood": prior,
    }])
    assert out[0]["accepted"] == {}
    assert out[0]["suppressed"] == 1


def test_newer_source_time_is_accepted(client_text):
    prior = {"AAPL": {"observedAtMs": 1_000, "revision": "rev1", "price": 100, "session": "regular", "freshness": "live"}}
    body = _envelope(items=[_item(observed_at="2026-08-31T14:31:00Z", revision="rev2")])
    out = _run(client_text, [{
        "op": "buildCandidateModel", "body": body,
        "orderedSymbols": ["AAPL"], "lastGood": prior,
    }])
    assert "AAPL" in out[0]["accepted"]
    assert out[0]["accepted"]["AAPL"]["revision"] == "rev2"


def test_equal_time_equal_revision_is_idempotent(client_text):
    ts_ms = 1787788800000  # == 2026-08-27T00:00:00Z
    prior = {"AAPL": {"observedAtMs": ts_ms, "revision": "rev1", "price": 100, "session": "regular", "freshness": "live"}}
    body = _envelope(items=[_item(observed_at="2026-08-27T00:00:00Z", revision="rev1")])
    out = _run(client_text, [{
        "op": "buildCandidateModel", "body": body,
        "orderedSymbols": ["AAPL"], "lastGood": prior,
    }])
    # equal time is not "older", so it is accepted (a harmless repaint)
    assert "AAPL" in out[0]["accepted"]
    assert out[0]["accepted"]["AAPL"]["revision"] == "rev1"


def test_equal_time_changed_revision_is_accepted_as_a_correction(client_text):
    prior = {"AAPL": {"observedAtMs": 1787788800000, "revision": "rev1", "price": 100, "session": "regular", "freshness": "live"}}
    body = _envelope(items=[_item(observed_at="2026-08-27T00:00:00Z", revision="rev2", price=101.0)])
    out = _run(client_text, [{
        "op": "buildCandidateModel", "body": body,
        "orderedSymbols": ["AAPL"], "lastGood": prior,
    }])
    assert out[0]["accepted"]["AAPL"]["revision"] == "rev2"
    assert out[0]["accepted"]["AAPL"]["price"] == 101.0


def test_snapshot_id_never_participates_in_ordering(client_text):
    """buildCandidateModel is never handed snapshot_id at all — the envelope's
    snapshot_id is dropped before this function runs; two builds that differ
    only in snapshot_id (never passed in) produce identical ordering."""
    prior = {"AAPL": {"observedAtMs": 1_000, "revision": "rev1", "price": 100, "session": "regular", "freshness": "live"}}
    body_a = _envelope(snapshot_id="AAAA", items=[_item(observed_at="2026-08-31T14:31:00Z")])
    body_b = _envelope(snapshot_id="ZZZZ", items=[_item(observed_at="2026-08-31T14:31:00Z")])
    out = _run(client_text, [
        {"op": "buildCandidateModel", "body": body_a, "orderedSymbols": ["AAPL"], "lastGood": prior},
        {"op": "buildCandidateModel", "body": body_b, "orderedSymbols": ["AAPL"], "lastGood": prior},
    ])
    assert out[0]["accepted"] == out[1]["accepted"]


def test_malformed_item_never_reaches_accepted_zero_mutation(client_text):
    body = _envelope(items=[_item(price="not-a-number")])
    out = _run(client_text, [{
        "op": "buildCandidateModel", "body": body,
        "orderedSymbols": ["AAPL"], "lastGood": {},
    }])
    assert out[0]["accepted"] == {}


# ── worstFreshness / pageSession (executed) ─────────────────────────────────

def test_worst_freshness_is_conservative(client_text):
    accepted = {
        "AAPL": {"freshness": "live"},
        "MSFT": {"freshness": "stale"},
    }
    out = _run(client_text, [{"op": "worstFreshness", "accepted": accepted}])
    assert out[0]["value"] == "stale"


def test_page_session_is_never_regular_over_a_mix(client_text):
    accepted = {
        "AAPL": {"session": "regular"},
        "MSFT": {"session": "closed"},
    }
    out = _run(client_text, [{"op": "pageSession", "accepted": accepted}])
    assert out[0]["value"] != "regular"


def test_page_session_is_regular_when_every_accepted_item_is(client_text):
    accepted = {"AAPL": {"session": "regular"}, "MSFT": {"session": "regular"}}
    out = _run(client_text, [{"op": "pageSession", "accepted": accepted}])
    assert out[0]["value"] == "regular"


# ── static source assertions (DOM/lifecycle the pure contract cannot see) ──

def test_exposes_the_required_public_surface(client_text):
    assert "window.IntelligenceHubMarketPulse = {" in client_text
    for member in ("refresh:", "pause:", "resume:", "state:"):
        assert member in client_text


def test_target_discovery_maps_every_symbol_to_all_its_nodes(client_text):
    assert "targetsBySymbol.get(sym).push(el)" in client_text
    assert "querySelectorAll('[data-ihmp-symbol]')" in client_text


def test_refuses_activation_above_58_even_though_the_route_caps_at_60(client_text):
    assert "MAX_ROSTER = 58" in client_text
    assert "orderedSymbols.length > MAX_ROSTER" in client_text


def test_one_batch_fetch_per_refresh_guarded_by_inflight(client_text):
    assert client_text.count("fetch(url,") == 1
    assert "if (inFlight) return;" in client_text


def test_stale_local_generation_is_discarded(client_text):
    assert "if (myGeneration !== generation) return;" in client_text


def test_atomic_paint_happens_inside_one_raf(client_text):
    assert client_text.count("requestAnimationFrame(function ()") == 1
    body = client_text[client_text.index("function commit("):]
    body = body[: body.index("\n  }\n")]
    assert "accepted.forEach(function (candidate, sym)" in body


def test_hidden_tab_pauses_and_resume_issues_one_immediate_refresh(client_text):
    listener = client_text[client_text.index("document.addEventListener('visibilitychange'"):]
    listener = listener[: listener.index("});") + 3]
    assert "unschedule();" in listener
    assert "generation++;" in listener
    assert "doFetch();" in listener


def test_live_disabled_setting_makes_zero_requests(client_text):
    assert "localStorage.getItem('liveOff')" in client_text
    doFetch = client_text[client_text.index("function doFetch()"):]
    doFetch = doFetch[: doFetch.index("\n  function schedule")]
    assert "if (!ACTIVE || liveDisabled) return;" in doFetch
    bottom = client_text[client_text.rindex("if (ACTIVE && !liveDisabled)"):]
    assert "schedule();" in bottom and "doFetch();" in bottom


def test_never_touches_an_intelligence_score_stage_or_order_node(client_text):
    """This controller owns [data-ihmp-*] only — proof by absence: it must
    never query or write the selectors intelligence rank/stage/score/entry
    markup uses."""
    for forbidden in (".score", "[data-score", "class=\"stage", "opportunity_score",
                      "entry_gate", ".led-row", ".ecard"):
        assert forbidden not in client_text, forbidden


def test_missing_root_is_a_clean_no_op(client_text):
    assert "if (!ROOT) return;" in client_text
