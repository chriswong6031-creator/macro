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
  if (c.op === 'fmtPrice') {
    return { value: fmtPrice(c.v, c.currency) };
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
    {"state": {"availability": "available", "freshness": "live", "session": "bogus", "coverage": "complete"}},
    {"state": {"availability": "available", "freshness": "live", "coverage": "complete"}},  # session absent
    {"coverage": {"requested": 2, "resolved": 1, "live": 1, "delayed": 0, "stale": 0, "missing": 0}},  # resolved+missing != requested
    {"coverage": {"requested": 1, "resolved": 1, "live": 0, "delayed": 0, "stale": 0, "missing": 0}},  # live+delayed+stale != resolved
    {"items": "not-a-list"},
])
def test_malformed_envelope_shapes_are_refused(client_text, mutation):
    out = _run(client_text, [{"op": "validEnvelopeShape", "body": _envelope(**mutation)}])
    assert out[0]["value"] is False


@pytest.mark.parametrize("session", ["regular", "closed", "mixed"])
def test_every_valid_session_value_is_accepted(client_text, session):
    """f3a: `state.session` is validated against exactly {regular, closed,
    mixed} — every member of that set must still pass."""
    body = _envelope(state={"availability": "available", "freshness": "live",
                             "session": session, "coverage": "complete"})
    out = _run(client_text, [{"op": "validEnvelopeShape", "body": body}])
    assert out[0]["value"] is True


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


def test_null_clock_item_is_never_newer_than_a_clocked_prior(client_text):
    """e5: a null-clock incoming item must NOT overwrite a prior that carries
    a real clock — the item we know LESS about must never win."""
    prior = {"AAPL": {"observedAtMs": 1_000, "revision": "rev1", "price": 100, "session": "regular", "freshness": "live"}}
    body = _envelope(items=[_item(observed_at=None, revision="rev2")])
    out = _run(client_text, [{
        "op": "buildCandidateModel", "body": body,
        "orderedSymbols": ["AAPL"], "lastGood": prior,
    }])
    assert out[0]["accepted"] == {}
    assert out[0]["suppressed"] == 1


def test_null_clock_item_is_accepted_when_no_clocked_prior_exists(client_text):
    """e5: a null-clock item is accepted when there is nothing clocked to
    compare it against — no prior at all, or a prior that is itself
    unclocked."""
    body = _envelope(items=[_item(observed_at=None, revision="rev1")])
    out = _run(client_text, [{
        "op": "buildCandidateModel", "body": body,
        "orderedSymbols": ["AAPL"], "lastGood": {},
    }])
    assert "AAPL" in out[0]["accepted"]

    prior_unclocked = {"AAPL": {"observedAtMs": None, "revision": "rev0", "price": 99, "session": "regular", "freshness": "live"}}
    body2 = _envelope(items=[_item(observed_at=None, revision="rev2")])
    out2 = _run(client_text, [{
        "op": "buildCandidateModel", "body": body2,
        "orderedSymbols": ["AAPL"], "lastGood": prior_unclocked,
    }])
    assert out2[0]["accepted"]["AAPL"]["revision"] == "rev2"


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


# ── composeStatus: executed across live/delayed/settled/stale/mixed/partial ─

def test_compose_status_live_regular_complete(client_text):
    out = _run(client_text, [{"op": "composeStatus", "acceptedCount": 5, "totalCount": 5,
                               "freshness": "live", "session": "regular"}])
    assert "Live market pulse" in out[0]["value"][0]
    assert "5/5" in out[0]["value"][0]


def test_compose_status_live_partial(client_text):
    out = _run(client_text, [{"op": "composeStatus", "acceptedCount": 3, "totalCount": 5,
                               "freshness": "live", "session": "regular"}])
    assert "Live prices for" in out[0]["value"][0]
    assert "3/5" in out[0]["value"][0]


def test_compose_status_delayed_complete_and_partial(client_text):
    complete = _run(client_text, [{"op": "composeStatus", "acceptedCount": 5, "totalCount": 5,
                                    "freshness": "delayed", "session": "regular"}])
    assert "Delayed market pulse" in complete[0]["value"][0]
    partial = _run(client_text, [{"op": "composeStatus", "acceptedCount": 3, "totalCount": 5,
                                   "freshness": "delayed", "session": "mixed"}])
    assert "Delayed prices" in partial[0]["value"][0]


def test_compose_status_stale_uses_unmistakable_stale_language_not_settled(client_text):
    """e2: a genuinely dead feed (freshness stale) must never read as a
    settled close, in EITHER language."""
    out = _run(client_text, [{"op": "composeStatus", "acceptedCount": 5, "totalCount": 5,
                               "freshness": "stale", "session": "regular"}])
    en, zh = out[0]["value"]
    assert "Market pulse has stopped updating" in en
    assert "Settled close" not in en
    assert "行情脉搏已停止更新" in zh
    assert "已收盘结算价" not in zh


def test_compose_status_stale_partial_also_uses_stale_language(client_text):
    out = _run(client_text, [{"op": "composeStatus", "acceptedCount": 2, "totalCount": 5,
                               "freshness": "stale", "session": "mixed"}])
    assert "Market pulse has stopped updating" in out[0]["value"][0]
    assert "2/5" in out[0]["value"][0]


def test_compose_status_closed_settled_read_is_distinct_from_stale(client_text):
    """A genuinely closed regular session's settled print keeps the settled
    wording — proven distinct from the stale case above."""
    out = _run(client_text, [{"op": "composeStatus", "acceptedCount": 5, "totalCount": 5,
                               "freshness": "live", "session": "closed"}])
    assert "Settled close" in out[0]["value"][0]
    assert "stopped updating" not in out[0]["value"][0]


# ── fmtPrice: '$' only for USD, bare number otherwise (h1) ─────────────────

def test_fmt_price_usd_gets_the_dollar_glyph(client_text):
    out = _run(client_text, [{"op": "fmtPrice", "v": 227.98, "currency": "USD"}])
    assert out[0]["value"] == "$227.98"


@pytest.mark.parametrize("currency", [None, "EUR", "", "usd"])
def test_fmt_price_never_guesses_a_glyph_for_non_usd_or_absent_currency(client_text, currency):
    out = _run(client_text, [{"op": "fmtPrice", "v": 227.98, "currency": currency}])
    assert out[0]["value"] == "227.98"
    assert "$" not in out[0]["value"]


# ── full-lifecycle DOM harness: e1 (failure path/lastGood expiry) and e3
#    (doFetch(force) abort-and-supersede) EXECUTED, not read from source. ──
#
# A minimal fake document/window/fetch/AbortController — just enough surface
# for the REAL, WHOLE client file (not the IHMP-CONTRACT sub-block) to load
# and run its IIFE unmodified. `Date.now` is monkeypatched so the 15-minute
# lastGood-expiry bound is provable without a real wait. Each fetch() call is
# captured (not auto-resolved) so the test drives resolution/rejection/abort
# in whatever order the scenario needs.
_DOM_PRELUDE = r"""
function makeClassList() {
  var set = new Set();
  return {
    add: function (c) { set.add(c); },
    remove: function (c) { set.delete(c); },
    toggle: function (c, on) {
      if (on === undefined) { if (set.has(c)) { set.delete(c); return false; } set.add(c); return true; }
      if (on) set.add(c); else set.delete(c);
      return on;
    },
    contains: function (c) { return set.has(c); },
  };
}
function makeEl() {
  var attrs = {};
  return {
    _children: [],
    textContent: '',
    hidden: false,
    classList: makeClassList(),
    getAttribute: function (n) { return Object.prototype.hasOwnProperty.call(attrs, n) ? attrs[n] : null; },
    setAttribute: function (n, v) { attrs[n] = String(v); },
    hasAttribute: function (n) { return Object.prototype.hasOwnProperty.call(attrs, n); },
    appendChild: function (c) { this._children.push(c); return c; },
    querySelector: function (sel) { var r = queryAll(this, sel); return r.length ? r[0] : null; },
    querySelectorAll: function (sel) { return queryAll(this, sel); },
  };
}
function elMatches(el, sel) {
  if (sel.charAt(0) === '.') return el.classList && el.classList.contains(sel.slice(1));
  if (sel.charAt(0) === '[' && sel.charAt(sel.length - 1) === ']') {
    return !!(el.hasAttribute && el.hasAttribute(sel.slice(1, -1)));
  }
  return false;
}
function collectMatches(el, sel, out) {
  (el._children || []).forEach(function (c) {
    if (elMatches(c, sel)) out.push(c);
    collectMatches(c, sel, out);
  });
}
function queryAll(root, sel) {
  var out = [];
  collectMatches(root, sel, out);
  return out;
}
function makeCluster(sym, bakedPrice) {
  var cluster = makeEl();
  cluster.setAttribute('data-ihmp-symbol', sym);
  var priceNode = makeEl(); priceNode.setAttribute('data-ihmp-price', '');
  priceNode.textContent = bakedPrice === null ? '' : ('$' + bakedPrice.toFixed(2));
  var absNode = makeEl(); absNode.setAttribute('data-ihmp-abs', ''); absNode.hidden = true;
  var pctNode = makeEl(); pctNode.setAttribute('data-ihmp-pct', ''); pctNode.hidden = true;
  cluster.appendChild(priceNode); cluster.appendChild(absNode); cluster.appendChild(pctNode);
  return cluster;
}

var ROOT_BAR = makeEl();
ROOT_BAR.setAttribute('data-ihmp-root', '');
ROOT_BAR.setAttribute('data-ihmp-availability', '');
ROOT_BAR.setAttribute('data-ihmp-freshness', '');
ROOT_BAR.setAttribute('data-ihmp-session', '');
ROOT_BAR.setAttribute('data-ihmp-coverage', '');
var STATUS_NODE = makeEl(); STATUS_NODE.setAttribute('data-ihmp-status', '');
var STATUS_EN = makeEl(); STATUS_EN.classList.add('l-en');
var STATUS_ZH = makeEl(); STATUS_ZH.classList.add('l-zh');
STATUS_NODE.appendChild(STATUS_EN); STATUS_NODE.appendChild(STATUS_ZH);
var ASOF_NODE = makeEl(); ASOF_NODE.setAttribute('data-ihmp-asof', '');
ASOF_NODE.setAttribute('datetime', '2026-08-31T00:00:00Z');
ASOF_NODE.textContent = '2026-08-31T00:00:00Z';
ROOT_BAR.appendChild(STATUS_NODE);
ROOT_BAR.appendChild(ASOF_NODE);

var SYMS = %(syms)s;
var BAKED = %(baked)s;
var CLUSTERS = {};
SYMS.forEach(function (s) { CLUSTERS[s] = makeCluster(s, (BAKED[s] === undefined ? null : BAKED[s])); });

var DOC_CHILDREN = [ROOT_BAR].concat(SYMS.map(function (s) { return CLUSTERS[s]; }));
var document = {
  hidden: false,
  _children: DOC_CHILDREN,
  querySelector: function (sel) { var r = queryAll(this, sel); return r.length ? r[0] : null; },
  querySelectorAll: function (sel) { return queryAll(this, sel); },
  addEventListener: function () { /* visibilitychange unused by these scenarios */ },
};

function FakeAbortController() {
  var self = this;
  this.signal = {
    aborted: false,
    _cbs: [],
    addEventListener: function (type, cb) { if (type === 'abort') this._cbs.push(cb); },
  };
  this.abort = function () {
    if (self.signal.aborted) return;
    self.signal.aborted = true;
    self.signal._cbs.forEach(function (cb) { cb(); });
  };
}

var window = {
  AbortController: FakeAbortController,
  requestAnimationFrame: function (fn) { setTimeout(fn, 0); },
};

var FETCH_CALLS = [];
function fetch(url, opts) {
  var entry = { url: url, opts: opts };
  var p = new Promise(function (resolve, reject) { entry.resolve = resolve; entry.reject = reject; });
  if (opts && opts.signal) {
    opts.signal.addEventListener('abort', function () {
      var err = new Error('AbortError'); err.name = 'AbortError';
      entry.reject(err);
    });
  }
  FETCH_CALLS.push(entry);
  return p;
}
function okResponse(body) { return { ok: true, json: function () { return Promise.resolve(body); } }; }
function nonOkResponse() { return { ok: false, json: function () { throw new Error('must not be called on a non-ok response'); } }; }

var FAKE_NOW = Date.now();
Date.now = function () { return FAKE_NOW; };

// setInterval/clearInterval are captured, not real — schedule()'s periodic
// tick is invoked MANUALLY from a scenario's tail script (INTERVAL_CALLBACKS[0]())
// instead of waiting a real 60s, so an "ordinary scheduled tick lands mid-flight"
// scenario is provable without a real wait.
var INTERVAL_CALLBACKS = [];
function setInterval(fn) { INTERVAL_CALLBACKS.push(fn); return INTERVAL_CALLBACKS.length; }
function clearInterval() { /* no-op: sufficient for these scenarios */ }

%(client)s
"""


def _run_lifecycle(client_text, *, syms, baked, tail_js, timeout=15):
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError("node is required to execute the IHMP lifecycle harness")
        pytest.skip("node not available (local only)")
    src = (_DOM_PRELUDE % {
        "syms": json.dumps(syms), "baked": json.dumps(baked), "client": client_text,
    }) + "\n" + tail_js
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ihmp_lifecycle.js"
        path.write_text(src)
        run = subprocess.run([node, str(path)], capture_output=True, text=True,
                              check=False, timeout=timeout)
    assert run.returncode == 0, run.stdout + run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


_VALID_ENVELOPE_ITEM = (
    "{symbol:'AAPL', price:250.0, change_abs:5.0, change_pct:2.0, currency:'USD', "
    "session:'regular', freshness:'live', observed_at:'2026-08-31T14:31:00Z', "
    "received_at:null, published_at:'2026-08-31T14:31:10Z', "
    "regular_session_date:'2026-08-31', revision:'rev1'}"
)
_VALID_ENVELOPE = (
    "{schema:'intelligence_hub.market_pulse.v1', projection:'intelligence_hub.market_pulse', "
    "snapshot_id:'s1', generated_at:'2026-08-31T14:31:10Z', source_owner:'terminal-market-data', "
    "source_view:'regular', state:{availability:'available', freshness:'live', session:'regular', "
    "coverage:'complete'}, coverage:{requested:1, resolved:1, live:1, delayed:0, stale:0, missing:0}, "
    f"items:[{_VALID_ENVELOPE_ITEM}], errors:[]}}"
)


def test_non_ok_response_sets_stopped_status_with_no_false_live(client_text):
    """e1: a non-ok response must set an explicit degraded status — never a
    silent return — and must never leave/paint a 'live' freshness claim."""
    tail = """
    setTimeout(function () {
      FETCH_CALLS[0].resolve(nonOkResponse());
      setTimeout(function () {
        console.log(JSON.stringify({
          availability: ROOT_BAR.getAttribute('data-ihmp-availability'),
          freshness: ROOT_BAR.getAttribute('data-ihmp-freshness'),
          statusEn: STATUS_EN.textContent,
          statusZh: STATUS_ZH.textContent,
          priceText: CLUSTERS['AAPL'].querySelector('[data-ihmp-price]').textContent,
        }));
      }, 20);
    }, 20);
    """
    out = _run_lifecycle(client_text, syms=["AAPL"], baked={"AAPL": 200.0}, tail_js=tail)
    assert out["freshness"] != "live"
    assert out["availability"] == "unavailable"
    assert "stopped updating" in out["statusEn"]
    assert "已停止更新" in out["statusZh"]
    assert out["priceText"] == "$200.00"  # baked value never blanked


def test_thrown_fetch_sets_stopped_status_with_no_false_live(client_text):
    """e1: a rejected fetch (network error) — not just a non-ok response —
    must also degrade, never silently return."""
    tail = """
    setTimeout(function () {
      FETCH_CALLS[0].reject(new Error('network unreachable'));
      setTimeout(function () {
        console.log(JSON.stringify({
          availability: ROOT_BAR.getAttribute('data-ihmp-availability'),
          freshness: ROOT_BAR.getAttribute('data-ihmp-freshness'),
          statusEn: STATUS_EN.textContent,
        }));
      }, 20);
    }, 20);
    """
    out = _run_lifecycle(client_text, syms=["AAPL"], baked={"AAPL": 200.0}, tail_js=tail)
    assert out["freshness"] != "live"
    assert out["availability"] == "unavailable"
    assert "stopped updating" in out["statusEn"]


def test_malformed_envelope_body_sets_stopped_status_with_no_false_live(client_text):
    """e1: an ok:true response whose BODY fails validEnvelopeShape must also
    degrade — malformed is a third failure mode, distinct from non-ok/thrown."""
    tail = """
    setTimeout(function () {
      FETCH_CALLS[0].resolve(okResponse({not: 'a valid envelope'}));
      setTimeout(function () {
        console.log(JSON.stringify({
          availability: ROOT_BAR.getAttribute('data-ihmp-availability'),
          freshness: ROOT_BAR.getAttribute('data-ihmp-freshness'),
          statusEn: STATUS_EN.textContent,
        }));
      }, 20);
    }, 20);
    """
    out = _run_lifecycle(client_text, syms=["AAPL"], baked={"AAPL": 200.0}, tail_js=tail)
    assert out["freshness"] != "live"
    assert out["availability"] == "unavailable"
    assert "stopped updating" in out["statusEn"]


def test_superseded_request_failing_late_does_not_flip_status_to_stopped(client_text):
    """e1/e3: a request superseded by a forced refresh is NOT a failure — if
    it settles (even with an error) after generation has moved on, it must
    not retroactively degrade the CURRENT status."""
    tail = """
    setTimeout(function () {
      window.IntelligenceHubMarketPulse.refresh();  // aborts call 0, issues call 1
      setTimeout(function () {
        var beforeAvail = ROOT_BAR.getAttribute('data-ihmp-availability');
        FETCH_CALLS[0].reject(new Error('AbortError'));  // the superseded call finally settling
        setTimeout(function () {
          console.log(JSON.stringify({
            callCount: FETCH_CALLS.length,
            call0Aborted: FETCH_CALLS[0].opts.signal.aborted,
            beforeAvail: beforeAvail,
            afterAvail: ROOT_BAR.getAttribute('data-ihmp-availability'),
          }));
        }, 20);
      }, 20);
    }, 20);
    """
    out = _run_lifecycle(client_text, syms=["AAPL"], baked={"AAPL": 200.0}, tail_js=tail)
    assert out["callCount"] == 2
    assert out["call0Aborted"] is True
    assert out["afterAvail"] == out["beforeAvail"]


def test_lastgood_expiry_reverts_every_painted_node_to_baked(client_text):
    """e1: 15 minutes past the last ACCEPTED quote, painted values revert to
    the baked baseline and status shows stopped/stale — proven via a
    monkeypatched clock, not a real 15-minute wait."""
    tail = f"""
    setTimeout(function () {{
      FETCH_CALLS[0].resolve(okResponse({_VALID_ENVELOPE}));
      setTimeout(function () {{
        var afterFirstPaint = CLUSTERS['AAPL'].querySelector('[data-ihmp-price]').textContent;
        FAKE_NOW += 16 * 60 * 1000;   // past the 15-minute bound
        window.IntelligenceHubMarketPulse.refresh();
        setTimeout(function () {{
          console.log(JSON.stringify({{
            afterFirstPaint: afterFirstPaint,
            priceAfterExpiry: CLUSTERS['AAPL'].querySelector('[data-ihmp-price]').textContent,
            availability: ROOT_BAR.getAttribute('data-ihmp-availability'),
            freshness: ROOT_BAR.getAttribute('data-ihmp-freshness'),
            statusEn: STATUS_EN.textContent,
          }}));
        }}, 20);
      }}, 20);
    }}, 20);
    """
    out = _run_lifecycle(client_text, syms=["AAPL"], baked={"AAPL": 200.0}, tail_js=tail)
    assert out["afterFirstPaint"] == "$250.00"     # the live paint actually happened
    assert out["priceAfterExpiry"] == "$200.00"    # reverted to the BAKED value, not blanked
    assert out["availability"] == "unavailable"
    assert out["freshness"] == "stale"
    assert "stopped updating" in out["statusEn"]


def test_doFetch_force_aborts_inflight_and_supersedes(client_text):
    """e3: refresh() while a request is in flight must ABORT it and issue a
    NEW one — not silently no-op until the next scheduled tick. This is the
    exact bug the old `if (inFlight) return;` (checked before the abort)
    caused."""
    tail = """
    setTimeout(function () {
      var before = FETCH_CALLS.length;
      window.IntelligenceHubMarketPulse.refresh();
      console.log(JSON.stringify({
        callsBefore: before,
        callsAfter: FETCH_CALLS.length,
        firstAborted: FETCH_CALLS[0].opts.signal.aborted,
      }));
    }, 20);
    """
    out = _run_lifecycle(client_text, syms=["AAPL"], baked={"AAPL": 200.0}, tail_js=tail)
    assert out["callsBefore"] == 1     # the initial load-time fetch was in flight
    assert out["callsAfter"] == 2      # refresh() issued a SECOND request
    assert out["firstAborted"] is True


def test_ordinary_scheduled_tick_still_drops_itself_while_inflight(client_text):
    """e3 must not regress the unforced case: doFetch(false) — the periodic
    tick installed via schedule()'s setInterval — still no-ops while a
    request is already in flight. `INTERVAL_CALLBACKS[0]()` fires that exact
    callback (schedule() wires `setInterval(function(){doFetch(false);}, ...)`)
    without a real 60s wait."""
    tail = """
    setTimeout(function () {
      var before = FETCH_CALLS.length;
      INTERVAL_CALLBACKS[0]();   // fires the ordinary (unforced) scheduled tick
      console.log(JSON.stringify({
        callsBefore: before,
        callsAfter: FETCH_CALLS.length,
        firstAborted: FETCH_CALLS[0].opts.signal.aborted,
        inFlight: window.IntelligenceHubMarketPulse.state().inFlight,
      }));
    }, 20);
    """
    out = _run_lifecycle(client_text, syms=["AAPL"], baked={"AAPL": 200.0}, tail_js=tail)
    assert out["callsBefore"] == 1
    assert out["callsAfter"] == 1      # the unforced tick issued NO new request
    assert out["firstAborted"] is False
    assert out["inFlight"] is True


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
    assert "doFetch(true);" in listener  # resume is a FORCED refresh (e3)


# e4: the 'liveOff' localStorage toggle was retired repo-wide — live prices
# are always-on per templates/theme.js:3882. No substring pins the absence of
# a branch; `test_exposes_the_required_public_surface` above already proves
# `refresh`/`resume` are reachable unconditionally on ACTIVE.


def test_never_touches_an_intelligence_score_stage_or_order_node(client_text):
    """This controller owns [data-ihmp-*] only — proof by absence: it must
    never query or write the selectors intelligence rank/stage/score/entry
    markup uses."""
    for forbidden in (".score", "[data-score", "class=\"stage", "opportunity_score",
                      "entry_gate", ".led-row", ".ecard"):
        assert forbidden not in client_text, forbidden


def test_missing_root_is_a_clean_no_op(client_text):
    assert "if (!ROOT) return;" in client_text
