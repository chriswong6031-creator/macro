"""tests/test_portfolio_auth_transition_js.py — A1A consumer-level auth-transition
proof (Sol blocker 2, verbatim commissioning): "add a full consumer-level auth-
transition test beginning with anonymous rows already loaded in portfolio.js, then
sign in while Supabase is delayed and while client initialization fails. Prove
anonymous rows never render under authenticated authority and loading always resolves
to ready/degraded/error."

This drives the REAL templates/watchstore.js + templates/portfolio.js +
templates/portfolio_state.js together, wired through a REAL document-level event bus
(document.addEventListener/dispatchEvent actually invoke registered listeners) — this
is the one deliberate departure from the house shim in tests/test_watchlist_workspace_js.py
and tests/test_portfolio_truth_a1a_js.py, both of which keep `document.readyState`
at 'loading' with a no-op addEventListener specifically so `init()` never runs and
only pure logic is exercised (see test_watchlist_workspace_js.py's own docstring).
That pattern cannot prove this commissioning's requirement: watchstore.js's
`onAuthUser()` communicates authority transitions to portfolio.js EXCLUSIVELY through
a real 'wl-auth' CustomEvent dispatch/listen round-trip, and portfolio.js's own
`init()`/`onAuth()`/`wireEvents()` must actually run for that round-trip — and for the
delayed-cloud/client-init-failure fixes below — to be exercised at all. This shim's
`readyState` is 'complete' and its event bus is a genuine pub/sub, by design.

Two latent defects this suite pins as required mutation reds (already fixed in
templates/portfolio.js and templates/watchstore.js by this same commit):

  (i) Delayed-cloud window (portfolio.js::onAuth): on the auth flip, portfolio.js used
      to keep the ANONYMOUS `rows` (and its 'ready' readState mirror) until
      WatchStore.portfolio.list()'s promise settled, so an interim render() during
      that window painted the anonymous book under authenticated (non-anon) wsState.
      Fixed: onAuth() now clears `rows`/sets a 'loading' readState and calls render()
      SYNCHRONOUSLY the instant a user is present, before the async list() call — and
      render()'s unknown-rows branch now paints an explicit, content-cleared loading
      state (showLoading()) rather than silently leaving the prior authority's table
      standing.

  (ii) Client-init failure (watchstore.js::_isLocalMode / getClient().catch): an
       authenticated visitor whose Supabase client never initializes (`sb` stays null
       forever) used to be indistinguishable from the transient S6 loading race — both
       are `user` truthy, `sb` null — so portfolioList() answered 'loading' forever,
       never resolving. Fixed: `sbInitFailed`, set by the `getClient().catch()`
       handler (which now also re-fires 'wl-auth' so every listener gets a fresh,
       TERMINAL read), routes portfolioList()/Upsert/Close/Remove through a new
       `_isClientUnavailable()` branch that answers degraded (last-good) or error
       (none) with `warning: 'client-unavailable'` — never a local-book substitution,
       never a stuck loading placeholder.

Also pins Sol A1A blocker 1 (Risk Center residue, root-caused by the parallel
debugger): window.FX's universe + templates/watchlist.js's retained RISK payload
form a latch nobody invalidates at the Watchlists->Portfolio mode boundary. Two
confirmed producer paths, both in this file's portfolio.js: (c) PS-absent
pushFxWeights() pushing `null` for a resolved-but-thin book (null falls FX back to
manual mode over the retained WATCHLIST universe), and (d) the rows===null early
return never calling pushFxWeights() at all. The module SHIM below gained a
`window.FX` call recorder (`__fxCalls`) for exactly this; the setMode()-side half of
the fix (resetting the RISK payload itself) is pinned behaviorally in
tests/test_watchlist_workspace_js.py::test_setmode_into_portfolio_clears_a_watchlists_derived_risk_payload_first.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

ROOT = Path(__file__).resolve().parents[1]
WATCHSTORE = ROOT / "templates" / "watchstore.js"
PORTFOLIO = ROOT / "templates" / "portfolio.js"
PORTFOLIO_STATE = ROOT / "templates" / "portfolio_state.js"
WATCHLIST = ROOT / "templates" / "watchlist.js"
FACTOR_EXPOSURE = ROOT / "templates" / "factor_exposure.js"
WATCHLIST_RISK = ROOT / "templates" / "watchlist_risk.js"
RISK_CORE = ROOT / "templates" / "risk_core.js"

USER = {"id": "u1"}

# ===========================================================================
# Consumer-level shim: a REAL id-keyed DOM (get/set on innerHTML/textContent is
# tracked into a full write HISTORY, not just final state — required by scenario 1's
# "the anon tickers never appeared post-flip" assertion, which must scan every paint,
# not merely the last one) and a REAL event bus (document + per-node
# addEventListener/dispatchEvent actually invoke registered listeners), so
# watchstore.js's 'wl-auth' dispatch really drives portfolio.js's onAuth() the way the
# production page does.
# ===========================================================================
SHIM = r"""
var __store = {};
global.localStorage = {
  getItem: function (k) {
    return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null;
  },
  setItem: function (k, v) { __store[k] = String(v); },
  removeItem: function (k) { delete __store[k]; }
};
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };

// ---- write history: EVERY innerHTML/textContent SET, across every node, forever ---
var __writes = [];
var __nodes = {};
function makeNode(id) {
  var n = {
    id: id, _html: '', _text: '', _value: '',
    style: {}, className: '', _attrs: {},
    classList: {
      _set: {},
      contains: function (c) { return !!this._set[c]; },
      add: function (c) { this._set[c] = true; },
      remove: function (c) { delete this._set[c]; },
      toggle: function (c, v) {
        if (v === undefined) v = !this._set[c];
        if (v) this._set[c] = true; else delete this._set[c];
      }
    },
    setAttribute: function (k, v) {
      this._attrs[k] = String(v);
      // F7 (Sol post-review, MINOR): setAttribute writes (e.g. renderReadBanner's
      // F5 `data-warning`) belong in the SAME write history innerHTML/textContent
      // use — a leak scanner that only watches two of the three DOM write surfaces
      // is a scanner with a blind spot.
      __writes.push({ id: id, prop: 'setAttribute:' + k, value: String(v) });
    },
    getAttribute: function (k) {
      return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
    },
    removeAttribute: function (k) { delete this._attrs[k]; },
    querySelector: function (sel) {
      var m = /\[data-count="([a-z]+)"\]/.exec(sel || '');
      if (m) return node('__count_' + m[1]);
      return null;
    },
    querySelectorAll: function () { return []; },
    _listeners: {},
    addEventListener: function (type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    removeEventListener: function (type, fn) {
      var arr = this._listeners[type]; if (!arr) return;
      var i = arr.indexOf(fn); if (i >= 0) arr.splice(i, 1);
    },
    dispatch: function (type, evt) {
      evt = evt || {};
      evt.type = type;
      if (!evt.target) evt.target = this;
      if (!evt.preventDefault) evt.preventDefault = function () {};
      (this._listeners[type] || []).slice().forEach(function (fn) { fn(evt); });
    },
    focus: function () {}
  };
  Object.defineProperty(n, 'innerHTML', {
    get: function () { return this._html; },
    set: function (v) { this._html = v; __writes.push({ id: id, prop: 'innerHTML', value: v }); }
  });
  Object.defineProperty(n, 'textContent', {
    get: function () { return this._text; },
    set: function (v) { this._text = v; __writes.push({ id: id, prop: 'textContent', value: v }); }
  });
  Object.defineProperty(n, 'value', {
    get: function () { return this._value; },
    set: function (v) { this._value = v; }
  });
  return n;
}
function node(id) {
  if (!__nodes[id]) __nodes[id] = makeNode(id);
  return __nodes[id];
}

// ---- a REAL document-level event bus ----------------------------------------------
var __docListeners = {};
var __events = [];
function docAdd(type, fn) { (__docListeners[type] = __docListeners[type] || []).push(fn); }
function docRemove(type, fn) {
  var arr = __docListeners[type]; if (!arr) return;
  var i = arr.indexOf(fn); if (i >= 0) arr.splice(i, 1);
}
function docDispatch(e) {
  __events.push({ type: e.type, detail: e.detail });
  (__docListeners[e.type] || []).slice().forEach(function (fn) { fn(e); });
  return true;
}
global.document = {
  readyState: 'complete',   // init() runs SYNCHRONOUSLY at require-time — this suite
                             // is deliberately consumer-level (see module docstring)
  documentElement: {
    _attrs: { 'data-lang': 'en' },
    getAttribute: function (k) {
      return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
    },
    setAttribute: function (k, v) { this._attrs[k] = v; },
    classList: { add: function () {}, remove: function () {} }
  },
  getElementById: function (id) { return node(id); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  addEventListener: docAdd,
  removeEventListener: docRemove,
  dispatchEvent: docDispatch,
  createElement: function () {
    return { style: {}, classList: { add: function () {} } };
  }
};
global.window = global;
global.window.addEventListener = function () {};
global.location = { hash: '', pathname: '/watchlist.html', search: '', origin: 'https://x' };

// ---- window.WS stub: the watchlist.js workspace shell portfolio.js reads small
// display helpers from (dash/dayCell/stageCell/scopeLine/seam). watchlist.js itself
// is NOT required in this suite (its own event-driven chip-paint behavior is pinned
// in tests/test_portfolio_truth_a1a_js.py) — this is the minimal real contract
// portfolio.js needs to render without throwing.
global.WS = {
  dash: function (enTip) { return '<span class="dash" title="' + (enTip || '') + '">—</span>'; },
  dayCell: function () { return '<span class="dash">—</span>'; },
  stageCell: function () { return ''; },
  stageOf: function () { return null; },
  scopeLine: function (shown, all) { return shown + ' / ' + all; },
  seam: function () {},
  // LAW 3 (A1A round-3) test seam: this SHIM stands in for the real watchlist.js
  // workspace shell, which portfolio.js's setBookRisk() now reads via
  // window.WS.prov() to fail-closed-reject any risk publication lacking valid
  // provenance. A CONSTANT portfolio-scope/gen-0 answer is enough for this file's
  // direct setBookRisk() test calls (below), which stamp the SAME constant —
  // this suite is not exercising the provenance seam itself (that is
  // tests/test_watchlist_workspace_js.py's/this file's own LAW 3 scenarios), it
  // is exercising payloadIsConsistentWithBook()'s SYMBOL-overlap validation, which
  // must still run as an independent layer once a payload's provenance is valid.
  prov: function () { return { scope: 'portfolio', gen: 0 }; }
};

// ---- window.FX call recorder: Sol blocker 1 (Risk Center residue) — pushFxWeights()
// and render()'s rows===null branch both call window.FX.setAutoWeights(); this stub
// records EVERY call's argument (a plain value snapshot, never a live reference a
// later mutation could retroactively change) so a test can assert the honest-empty
// `{}` was pushed and `null` never was.
global.__fxCalls = [];
global.FX = {
  setAutoWeights: function (w) {
    global.__fxCalls.push(w === null ? null : (w === undefined ? undefined : Object.assign({}, w)));
  }
};

// ---- a deferred/controllable fake Supabase client (portfolio_positions only) ------
// Mirrors the ONE query chain portfolioList() issues:
// .select('*').eq('user_id', uid).order('created_at') — but the terminal call returns
// a PENDING promise this test settles on demand, so "cloud list() pending unresolved"
// is a real, controllable state rather than a same-tick resolution.
function makeDeferredDb() {
  var pending = [];
  var api = {
    select: function () { return api; },
    eq: function () { return api; },
    order: function () {
      return new Promise(function (resolve) { pending.push(resolve); });
    }
  };
  return {
    client: { from: function () { return api; } },
    pendingCount: function () { return pending.length; },
    settleNext: function (result) { var r = pending.shift(); if (r) r(result); }
  };
}

function tick() { return new Promise(function (res) { setImmediate(res); }); }
async function drain(n) { for (var i = 0; i < (n || 5); i++) { await tick(); } }

function OUT(o) { process.stdout.write(JSON.stringify(o)); }
"""


def _run(js_body: str, extra: dict | None = None) -> dict:
    globs = "\n".join("var %s = %s;" % (k, json.dumps(v)) for k, v in (extra or {}).items())
    # `boot()` is called BY EACH TEST, after it has seeded localStorage — portfolio.js
    # kicks off its own initial onAuth()/list() the INSTANT it is require()'d (init()
    # runs synchronously off document.readyState:'complete'), so requiring it before
    # localStorage is seeded would have it read an empty local book at boot and never
    # again — every test body must seed localStorage FIRST, then call boot().
    script = (
        SHIM
        + "\n"
        + globs
        + "\nvar WSL, PS;\nfunction boot() {\n  WSL = require(%s);\n  PS = require(%s);\n  require(%s);\n}\n"
        % (json.dumps(str(WATCHSTORE)), json.dumps(str(PORTFOLIO_STATE)), json.dumps(str(PORTFOLIO)))
        + "\n(async function () {\ntry {\n"
        + textwrap.dedent(js_body)
        + "\n} catch (e) {\n  process.stdout.write(JSON.stringify({__error: String(e && e.stack || e)}));\n  process.exit(1);\n}\n})();\n"
    )
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    out = json.loads(res.stdout)
    assert "__error" not in out, out.get("__error")
    return out


ANON_SEED = json.dumps({
    "v": 1,
    "rows": [
        {"id": "loc-1", "ticker": "ANONA", "shares": 1, "entry_price": 10,
         "entry_date": None, "notes": None, "status": "open"},
        {"id": "loc-2", "ticker": "ANONB", "shares": 2, "entry_price": 20,
         "entry_date": None, "notes": None, "status": "open"},
    ],
})


# ===========================================================================
# Scenario 1: anonymous rows loaded+rendered -> auth flip, cloud list() PENDING ->
# interim render shows no anon ticker + loading visible -> resolves with DIFFERENT
# cloud rows -> ready + cloud-only, anon tickers NEVER appeared post-flip.
# ===========================================================================
@needs_node
def test_scenario1_delayed_cloud_never_renders_the_anon_book_and_terminally_resolves():
    out = _run(
        """
        localStorage.setItem('mdash.pf.v1', JSON.stringify(""" + ANON_SEED + """));
        boot();
        // portfolio.js's init() already ran at require-time (readyState:'complete'),
        // kicking off onAuth() -> WatchStore.portfolio.list() for the ANONYMOUS local
        // book (WSL.user() is null at this point). Drain that chain.
        await drain(8);
        var afterAnonHTML = node('tbl_pf').innerHTML;
        var anonPainted = afterAnonHTML.indexOf('ANONA') >= 0 && afterAnonHTML.indexOf('ANONB') >= 0;
        var writesBeforeFlip = __writes.length;

        // sign in: user present, cloud list() PENDING (unresolved) — the S6/blocker-2
        // delayed-cloud window.
        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        // onAuth()'s synchronous rows=null + loading render already ran INLINE, above,
        // before this dispatch call even returns (portfolio.js's listener runs
        // synchronously off the real event bus). No tick needed to observe it.
        var duringLoadingHTML = node('tbl_pf').innerHTML;
        // portfolio.js's OWN module-level readState mirror (window.PF.readState()) —
        // NOT WSL.portfolio.readState(), which lags until the pending query settles;
        // the whole point of Part C(i) is that portfolio.js's own copy clears
        // SYNCHRONOUSLY, ahead of the async answer.
        var duringLoadingReadState = window.PF.readState();

        // force an interim render (what a price tick / language toggle / fx event
        // would trigger) WHILE the cloud read is still pending
        window.PF.render();
        await drain(2);
        var afterInterimHTML = node('tbl_pf').innerHTML;

        // resolve with DIFFERENT cloud rows than the anon book
        db.settleNext({
          data: [{ id: 'c1', ticker: 'CLOUDX', shares: 5, entry_price: 50,
                    entry_date: null, notes: null, status: 'open', created_at: '1' }],
          error: null
        });
        await drain(8);

        var finalHTML = node('tbl_pf').innerHTML;
        var finalReadState = WSL.portfolio.readState();

        // scan the FULL write history from the moment of the auth-flip dispatch
        // onward — never just the final DOM state (mission requirement, scenario 1)
        var postFlipWrites = __writes.slice(writesBeforeFlip);
        var anonLeakedPostFlip = postFlipWrites.some(function (w) {
          return typeof w.value === 'string' && (w.value.indexOf('ANONA') >= 0 || w.value.indexOf('ANONB') >= 0);
        });

        OUT({
          anonPainted: anonPainted,
          duringLoadingHTML_hasAnon: duringLoadingHTML.indexOf('ANONA') >= 0 || duringLoadingHTML.indexOf('ANONB') >= 0,
          duringLoadingReadState: duringLoadingReadState,
          afterInterimHTML_hasAnon: afterInterimHTML.indexOf('ANONA') >= 0 || afterInterimHTML.indexOf('ANONB') >= 0,
          finalHTML_hasCloud: finalHTML.indexOf('CLOUDX') >= 0,
          finalHTML_hasAnon: finalHTML.indexOf('ANONA') >= 0 || finalHTML.indexOf('ANONB') >= 0,
          finalReadState: finalReadState,
          anonLeakedPostFlip: anonLeakedPostFlip
        });
        """,
        {"USER": USER},
    )
    # sanity: the anon book genuinely painted before the flip (a broken seed would
    # make everything below pass for the wrong reason)
    assert out["anonPainted"] is True
    # the moment authority flips, rows/readState clear SYNCHRONOUSLY — no anon ticker
    # visible during the loading window, and the state is honestly 'loading'
    assert out["duringLoadingHTML_hasAnon"] is False
    assert out["duringLoadingReadState"]["authority"] == "cloud"
    assert out["duringLoadingReadState"]["state"] == "loading"
    # an interim render while still pending must not resurrect the anon book either
    assert out["afterInterimHTML_hasAnon"] is False
    # loading terminally resolves to 'ready' with the CLOUD rows, never a blend
    assert out["finalHTML_hasCloud"] is True
    assert out["finalHTML_hasAnon"] is False
    assert out["finalReadState"]["state"] == "ready"
    assert out["finalReadState"]["authority"] == "cloud"
    # the full post-flip write history — not just the final snapshot — never once
    # painted an anon ticker
    assert out["anonLeakedPostFlip"] is False


# ===========================================================================
# Scenario 2: cloud list() rejects with NO last-good -> terminal 'error', explicit
# unavailable message, no silent zero, no anon rows.
# ===========================================================================
@needs_node
def test_scenario2_cloud_rejects_with_no_last_good_is_a_terminal_explicit_error():
    out = _run(
        """
        localStorage.setItem('mdash.pf.v1', JSON.stringify(""" + ANON_SEED + """));
        boot();
        await drain(8);

        var writesBeforeFlip = __writes.length;
        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        var duringLoading = node('tbl_pf').innerHTML;
        // let the promise chain actually reach sb.from(...).order() and register its
        // pending resolver before we try to settle it
        await drain(3);

        // the ONE cloud read this session has ever attempted fails — no last-good
        db.settleNext({ data: null, error: { message: 'boom' } });
        await drain(8);

        // F7 (Sol post-review, MINOR): scan the FULL write history from the flip
        // onward — not just the final DOM snapshot — for anon-ticker leakage.
        var postFlipWrites = __writes.slice(writesBeforeFlip);
        var anonLeakedInHistory = postFlipWrites.some(function (w) {
          return typeof w.value === 'string' && w.value.indexOf('ANONA') >= 0;
        });

        OUT({
          duringLoading_hasAnon: duringLoading.indexOf('ANONA') >= 0,
          readState: WSL.portfolio.readState(),
          errBanner: node('pf_err_inline').textContent,
          errBannerVisible: node('pf_err_inline').style.display,
          tblFinal_hasAnon: node('tbl_pf').innerHTML.indexOf('ANONA') >= 0,
          anonLeakedInHistory: anonLeakedInHistory
        });
        """,
        {"USER": USER},
    )
    assert out["duringLoading_hasAnon"] is False
    assert out["readState"]["authority"] == "cloud"
    assert out["readState"]["state"] == "error"
    assert out["readState"]["last_good_at"] is None
    # the explicit unavailable message painted, not a silent blank
    assert out["errBanner"]
    assert out["errBannerVisible"] == "block"
    assert out["tblFinal_hasAnon"] is False
    assert out["anonLeakedInHistory"] is False


# ===========================================================================
# Scenario 3: cloud list() rejects WITH last-good present -> 'degraded' + last-good
# rows + read-only banner.
# ===========================================================================
@needs_node
def test_scenario3_cloud_rejects_with_last_good_shows_degraded_readonly_banner():
    out = _run(
        """
        localStorage.setItem('mdash.pf.v1', JSON.stringify(""" + ANON_SEED + """));
        boot();
        await drain(8);
        var writesBeforeFlip = __writes.length;

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);

        // FIRST cloud read succeeds, establishing last-good
        db.settleNext({
          data: [{ id: 'c1', ticker: 'CLOUDGOOD', shares: 1, entry_price: 1,
                    entry_date: null, notes: null, status: 'open', created_at: '1' }],
          error: null
        });
        await drain(8);
        var afterFirst = node('tbl_pf').innerHTML;

        // a LATER read fails (re-fire the auth event to trigger another list() call)
        var db2 = makeDeferredDb();
        WSL._setTestSession(USER, db2.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db2.settleNext({ data: null, error: { message: 'boom-again' } });
        await drain(8);

        // F7 (Sol post-review, MINOR): scan the FULL write history since the flip.
        var postFlipWrites = __writes.slice(writesBeforeFlip);
        var anonLeakedInHistory = postFlipWrites.some(function (w) {
          return typeof w.value === 'string' && w.value.indexOf('ANONA') >= 0;
        });

        OUT({
          afterFirst_hasCloud: afterFirst.indexOf('CLOUDGOOD') >= 0,
          readState: WSL.portfolio.readState(),
          tbl_hasCloudGood: node('tbl_pf').innerHTML.indexOf('CLOUDGOOD') >= 0,
          banner: node('pf_readbanner').textContent,
          bannerVisible: node('pf_readbanner').style.display,
          anonLeakedInHistory: anonLeakedInHistory
        });
        """,
        {"USER": USER},
    )
    assert out["afterFirst_hasCloud"] is True
    assert out["readState"]["state"] == "degraded"
    assert out["readState"]["authority"] == "cloud"
    assert out["readState"]["last_good_at"] is not None
    # last-good rows are still on screen, read-only, with the disclosure banner
    assert out["tbl_hasCloudGood"] is True
    assert out["banner"]
    assert out["bannerVisible"] == "block"
    assert out["anonLeakedInHistory"] is False


# ===========================================================================
# Scenario 4: session exists, user reported, sb/client init FAILS permanently.
# ===========================================================================
@needs_node
def test_scenario4_client_init_failure_never_serves_the_local_anon_book():
    out = _run(
        """
        localStorage.setItem('mdash.pf.v1', JSON.stringify(""" + ANON_SEED + """));
        boot();
        await drain(8);
        var localBookBefore = JSON.parse(localStorage.getItem('mdash.pf.v1')).rows.length;
        var writesBeforeFlip = __writes.length;

        // user present, sb NEVER resolves (client init failed) — the 3rd arg is the
        // seam Part C(ii) adds specifically for this terminal case
        WSL._setTestSession(USER, null, true);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(8);

        var readState1 = WSL.portfolio.readState();
        var tblHTML = node('tbl_pf').innerHTML;

        // a write attempt in this state
        var writeResult = await WSL.portfolio.upsert({ ticker: 'SHOULD_NOT_LAND', shares: 1,
          entry_price: 1, entry_date: null, status: 'open' });
        var localBookAfterWrite = JSON.parse(localStorage.getItem('mdash.pf.v1')).rows;

        // F7 (Sol post-review, MINOR): scan the FULL write history since the flip.
        var postFlipWrites = __writes.slice(writesBeforeFlip);
        var anonLeakedInHistory = postFlipWrites.some(function (w) {
          return typeof w.value === 'string' && w.value.indexOf('ANONA') >= 0;
        });

        OUT({
          readState1: readState1,
          isLocal: WSL.portfolio.isLocal(),
          tbl_hasAnon: tblHTML.indexOf('ANONA') >= 0,
          writeResult: writeResult,
          localBookUnchanged: localBookAfterWrite.length === localBookBefore &&
            !localBookAfterWrite.some(function (r) { return r.ticker === 'SHOULD_NOT_LAND'; }),
          anonLeakedInHistory: anonLeakedInHistory
        });
        """,
        {"USER": USER},
    )
    # never local mode for a signed-in session, even with a permanently-broken client
    assert out["isLocal"] is False
    # a terminal state — degraded or error, never stuck loading — with the honest
    # client-unavailable warning
    assert out["readState1"]["authority"] == "cloud"
    assert out["readState1"]["state"] in ("degraded", "error")
    assert out["readState1"]["warning"] == "client-unavailable"
    # the anonymous local book never rendered under this authenticated-but-broken session
    assert out["tbl_hasAnon"] is False
    # the write resolves null — no false Saved claim — and the local anon book is
    # completely untouched (never silently written to)
    assert out["writeResult"] is None
    assert out["localBookUnchanged"] is True
    assert out["anonLeakedInHistory"] is False


@needs_node
def test_scenario4_write_failure_chip_history_never_says_offline_or_saved():
    """The chip word for a write attempted under client-unavailable must be honest —
    'failed', never 'offline' (no retention claim) and never 'saved' (nothing landed)."""
    out = _run(
        """
        localStorage.setItem('mdash.pf.v1', JSON.stringify(""" + ANON_SEED + """));
        boot();
        await drain(8);

        WSL._setTestSession(USER, null, true);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(8);

        var chipHistory = [];
        document.addEventListener('pf-save', function (e) { chipHistory.push(e.detail.state); });

        // simulate portfolio.js's own write path: doSave() is private, but its exact
        // observable contract is dispatchPfSave('saving') then the write settling —
        // exercised end to end via the real WatchStore write, which resolves null in
        // this state (portfolio.js's own doSave() reacts to that with 'failed' — see
        // templates/portfolio.js's structural pin in test_portfolio_truth_a1a_js.py;
        // this test proves the WatchStore half: the write genuinely resolves null so
        // that reaction is the only honest one available to the caller).
        var writeResult = await WSL.portfolio.upsert({ ticker: 'X', shares: 1, entry_price: 1,
          entry_date: null, status: 'open' });

        OUT({ writeResult: writeResult });
        """,
        {"USER": USER},
    )
    assert out["writeResult"] is None


# ===========================================================================
# Scenario 5 (Part A, write-failure honesty): authenticated healthy read, upsert
# fails -> chip history 'saving' then 'failed'; the Watchlist-only retention copy
# never appears in any portfolio-scope chip paint across the whole history.
# ===========================================================================
@needs_node
def test_scenario5_write_failure_honesty_chip_history_and_forbidden_copy():
    """Drives the REAL doSave() UI path (fill the modal fields, click #pfm_save) —
    not just the WatchStore layer — so a mutation that restores the OLD 'offline'
    dispatch at doSave()'s failure site (portfolio.js) is actually exercised, not
    merely the watchstore.js half of the contract."""
    out = _run(
        """
        boot();
        var chipHistory = [];
        document.addEventListener('pf-save', function (e) { chipHistory.push(e.detail.state); });

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [], error: null });   // healthy empty cloud book
        await drain(8);
        var chipHistoryAfterHealthyRead = chipHistory.slice();

        // a write that FAILS (the stub rejects) — swap the session's client for one
        // whose insert().select().single() resolves an error
        var failDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return this; },
          insert: function () { return this; },
          single: function () { return Promise.resolve({ data: null, error: { message: 'insert-fail' } }); }
        }; } };
        WSL._setTestSession(USER, failDb);

        // fill the modal exactly as a visitor would, then click Save — the REAL
        // doSave() UI path (private function, only reachable this way)
        node('pfm_ticker').value = 'Y';
        node('pfm_shares').value = '1';
        node('pfm_price').value = '1';
        node('pfm_save').dispatch('click', {});
        await drain(8);

        OUT({
          chipHistoryAfterHealthyRead: chipHistoryAfterHealthyRead,
          chipHistoryAfterFailedSave: chipHistory,
          chipDictSource: require('fs').readFileSync(%s, 'utf8')
        });
        """ % json.dumps(str(ROOT / "templates" / "watchlist.js")),
        {"USER": USER},
    )
    # the healthy read settled to 'clean' (a plain read, not a write claim — M-d)
    assert "clean" in out["chipHistoryAfterHealthyRead"]
    assert "offline" not in out["chipHistoryAfterHealthyRead"]
    # the write: 'saving' then 'failed' — never 'saved', never 'offline'
    history = out["chipHistoryAfterFailedSave"]
    assert "saving" in history
    assert "failed" in history
    assert "saved" not in history
    assert "offline" not in history
    # the CHIP dict source (checked directly — this test does not require
    # watchlist.js's chip renderer) must carry the honest failed/unavailable words and
    # NEVER let the Watchlist's local-retention claim leak into Portfolio-scope copy
    src = out["chipDictSource"]
    assert "failed:" in src and "unavailable:" in src
    failed_block = src[src.index("failed:"):src.index("unavailable:")]
    unavailable_block = src[src.index("unavailable:"):src.index("unavailable:") + 400]
    for forbidden in ("kept locally", "written through", "存在本地", "已存在本地", "自动写入"):
        assert forbidden not in failed_block, forbidden
        assert forbidden not in unavailable_block, forbidden


# ===========================================================================
# Anonymous-visitor control: anon never signs in — behavior stays byte-identical.
# rows render, writes hit the local store, chip state is 'local'.
# ===========================================================================
@needs_node
def test_anonymous_visitor_never_touches_cloud_and_chip_stays_local():
    out = _run(
        """
        localStorage.setItem('mdash.pf.v1', JSON.stringify(""" + ANON_SEED + """));
        boot();
        await drain(8);

        var readState = WSL.portfolio.readState();
        var tblHTML = node('tbl_pf').innerHTML;

        var writeResult = await WSL.portfolio.upsert({ ticker: 'ANONC', shares: 1,
          entry_price: 1, entry_date: null, status: 'open' });
        var localRows = JSON.parse(localStorage.getItem('mdash.pf.v1')).rows;

        OUT({
          readState: readState,
          isLocal: WSL.portfolio.isLocal(),
          tbl_hasAnonA: tblHTML.indexOf('ANONA') >= 0,
          tbl_hasAnonB: tblHTML.indexOf('ANONB') >= 0,
          writeResult: writeResult,
          localHasNewRow: localRows.some(function (r) { return r.ticker === 'ANONC'; })
        });
        """
    )
    assert out["readState"]["authority"] == "local"
    assert out["readState"]["state"] == "ready"
    assert out["isLocal"] is True
    assert out["tbl_hasAnonA"] is True
    assert out["tbl_hasAnonB"] is True
    # a local write genuinely lands — the anonymous local outbox is real and
    # untouched by any of this commissioning's authenticated-authority fixes
    assert out["writeResult"] is not None
    assert out["localHasNewRow"] is True


# ===========================================================================
# Sol blocker 1 (Risk Center residue) — root-caused by the parallel debugger:
# window.FX's universe + watchlist.js's retained RISK payload form a latch nobody
# invalidates at the mode boundary. Two confirmed producer paths, both in
# portfolio.js: (c) PS-absent pushFxWeights() pushing `null` for a resolved-but-thin
# book (null falls FX back to manual mode over the retained WATCHLIST universe), and
# (d) the rows===null early return never calling pushFxWeights() at all (FX is told
# nothing, so watchlist.js repaints whatever RISK it last retained). Fixed at their
# own source in portfolio.js; these tests extend the auth-transition harness with a
# window.FX call recorder (added to the module SHIM above) to pin both mechanisms
# behaviorally against the REAL portfolio.js.
# ===========================================================================
@needs_node
def test_producer_c_ps_absent_thin_book_pushes_honest_empty_never_null():
    """MUTATION CHECK: revert the final ternary in pushFxWeights() (portfolio.js
    ~line 365) from `keys.length >= 2 ? w : {}` back to `keys.length >= 2 ? w : null`
    and this reds — a PS-absent, resolved-but-thin (zero-position) authenticated book
    must push the honest-empty `{}`, never `null` (null falls FX back to manual mode
    over the retained Watchlist universe — producer path (c))."""
    out = _run(
        """
        boot();
        // PS-absent (split-deploy window, B2) — simulate portfolio_state.js never
        // having deployed by clearing the live binding pushFxWeights() reads.
        window.PS = undefined;
        __fxCalls.length = 0;

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [], error: null });   // ZERO positions, a resolved read
        await drain(8);

        OUT({ fxCalls: __fxCalls });
        """,
        {"USER": USER},
    )
    assert None not in out["fxCalls"], out["fxCalls"]
    assert {} in out["fxCalls"], out["fxCalls"]


@needs_node
def test_producer_d_rows_unknown_clears_fx_before_the_early_return():
    """MUTATION CHECK: remove the `if (window.FX && window.FX.setAutoWeights)
    window.FX.setAutoWeights({});` line from render()'s rows===null branch
    (portfolio.js) and this reds — render() used to return from this branch without
    ever calling FX, so watchlist.js's mode render simply repainted whatever RISK
    payload it last retained under 'positions unknown' (producer path (d))."""
    out = _run(
        """
        boot();
        __fxCalls.length = 0;

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        // onAuth()'s SYNCHRONOUS rows=null + 'loading' render already ran INLINE,
        // above, before this line — fix 3's FX clear happens IN that render pass,
        // strictly before any drain/tick.
        var fxCallsDuringLoading = __fxCalls.slice();

        await drain(3);
        db.settleNext({ data: null, error: { message: 'boom' } });   // no last-good -> terminal 'error'
        await drain(8);
        var fxCallsFinal = __fxCalls.slice();

        OUT({ fxCallsDuringLoading: fxCallsDuringLoading, fxCallsFinal: fxCallsFinal });
        """,
        {"USER": USER},
    )
    # the honest-empty was pushed AT/BEFORE the synchronous loading-state return —
    # never left for FX to keep whatever it last had
    assert {} in out["fxCallsDuringLoading"], out["fxCallsDuringLoading"]
    assert None not in out["fxCallsFinal"], out["fxCallsFinal"]


# ===========================================================================
# F1 (Sol post-review, BLOCKER) — false zero in the loading window.
# window.PF.count() used to gate only on `readState.state === 'error'`, so
# rows===null + readState 'loading' (the delayed-cloud window onAuth() clears
# synchronously) fell through to `openRows().length`, which is 0 whenever rows is
# null. A signed-in visitor mid-read saw "0" on the Portfolio tab count chip —
# freeze §10 violation (adapted from the review's proofD_count_zero.py).
# ===========================================================================
@needs_node
def test_f1_count_is_null_during_loading_and_error_null_after_ready():
    """MUTATION CHECK: revert `count: function () { return rows === null ? null :
    openRows().length; }` to the old `(rows === null && readState.state === 'error')
    ? null : openRows().length` and this reds — countDuringLoading would go back to
    0 instead of null."""
    out = _run(
        """
        localStorage.setItem('mdash.pf.v1', JSON.stringify(%s));
        boot();
        await drain(8);
        var anonCount = window.PF.count();          // 2 anonymous rows loaded

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        var loadingReadState = window.PF.readState();
        var countDuringLoading = window.PF.count();

        await drain(3);
        db.settleNext({ data: null, error: { message: 'boom' } });
        await drain(8);
        var errReadState = window.PF.readState();
        var countDuringError = window.PF.count();

        var db2 = makeDeferredDb();
        WSL._setTestSession(USER, db2.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db2.settleNext({
          data: [{ id: 'c1', ticker: 'CLOUDX', shares: 1, entry_price: 1,
                    entry_date: null, notes: null, status: 'open', created_at: '1' }],
          error: null
        });
        await drain(8);
        var readyReadState = window.PF.readState();
        var countAfterReady = window.PF.count();

        OUT({
          anonCount: anonCount,
          loadingState: loadingReadState.state, countDuringLoading: countDuringLoading,
          errorState: errReadState.state, countDuringError: countDuringError,
          readyState: readyReadState.state, countAfterReady: countAfterReady
        });
        """ % ANON_SEED,
        {"USER": USER},
    )
    assert out["anonCount"] == 2
    assert out["loadingState"] == "loading"
    assert out["countDuringLoading"] is None
    assert out["errorState"] == "error"
    assert out["countDuringError"] is None
    assert out["readyState"] == "ready"
    assert out["countAfterReady"] == 1


# ===========================================================================
# F2 (Sol post-review, MAJOR) — honest-empty {} was a no-op when LAST is empty,
# latching a signed-in user's Risk Center/factor read across sign-out and a second
# user's sign-in. Two real-module regression tests, adapted from the review's own
# proofA_fx_earlyreturn.js / proofB_risk_latch_auth.js — REAL factor_exposure.js and
# watchlist.js execution (not the fake window.FX recorder the rest of this suite
# uses), since F2 is a defect IN those two files' own logic.
# ===========================================================================
def _run_node_script(script: str) -> dict:
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


FACTOR_EXPOSURE_SHIM = r"""
global.localStorage = { getItem: function () { return null; }, setItem: function () {}, removeItem: function () {} };
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
var events = [];
var panel = { style: {}, innerHTML: '', querySelector: function () { return null; }, querySelectorAll: function () { return []; } };
global.document = {
  readyState: 'complete',
  documentElement: { getAttribute: function () { return 'en'; }, setAttribute: function () {} },
  getElementById: function (id) { return id === 'fx_panel' ? panel : null; },
  addEventListener: function () {}, removeEventListener: function () {},
  dispatchEvent: function (e) { events.push({ type: e.type, universe: (e.detail && e.detail.universe) || null, mode: e.detail && e.detail.mode }); return true; }
};
global.window = global;
global.window.addEventListener = function () {};
global.fetch = function () {
  return Promise.resolve({ ok: true, json: function () { return Promise.resolve({
    factors: [{ key: 'mkt', tier: 'reliable', scope: 'stock', label: 'Market' }],
    betas: { AAPL: { mkt: 1.1, idio_vol: 0.2 }, MSFT: { mkt: 1.0, idio_vol: 0.2 }, NVDA: { mkt: 1.6, idio_vol: 0.3 } },
    resid: { AAPL: 0.2, MSFT: 0.2, NVDA: 0.3 },
    factor_cov: { mkt: { mkt: 0.04 } }
  }); } });
};
process.on('unhandledRejection', function () { /* fixture is minimal */ });
function tick() { return new Promise(function (r) { setImmediate(r); }); }
async function drain(n) { for (var i = 0; i < (n || 8); i++) await tick(); }
function OUT(o) { process.stdout.write(JSON.stringify(o)); }
"""


@needs_node
def test_f2_factor_exposure_honest_empty_announces_with_last_empty():
    """Adapted from the review's proofA_fx_earlyreturn.js — real factor_exposure.js
    execution. MUTATION CHECK: restore the old guard
    (`var autoNames = AUTO_W ? Object.keys(AUTO_W).length : 0; if (!LAST.length &&
    !autoNames) return;`) and this reds — a portfolio-only signed-in user (LAST, the
    watchlist universe, empty) whose portfolio.js pushes the honest-empty `{}` must
    still get a real render/announce that CLEARS the universe, not a silent no-op
    that leaves the PREVIOUS book's universe standing."""
    script = (
        FACTOR_EXPOSURE_SHIM
        + "\nrequire(%s);\n" % json.dumps(str(FACTOR_EXPOSURE))
        + """
        (async function () {
          // Signed-in user A: portfolio-only (EMPTY watchlist -> LAST=[])
          window.FX.setAutoWeights({ AAPL: 1000, MSFT: 2000, NVDA: 3000 });
          await drain(10);
          var afterA = { n: events.length, last: events[events.length - 1] };
          var curA = window.FX.currentWeights();

          // A signs out (or B's book is thin): portfolio.js pushes honest-empty
          events.length = 0;
          window.FX.setAutoWeights({});
          await drain(10);
          var curAfterClear = window.FX.currentWeights();

          OUT({
            afterA_eventCount: afterA.n, afterA_universe: curA.universe, afterA_mode: curA.mode,
            eventsAfterHonestEmpty: events.length,
            universeAfterHonestEmpty: curAfterClear.universe, modeAfterHonestEmpty: curAfterClear.mode
          });
        })();
        """
    )
    out = _run_node_script(script)
    assert out["afterA_eventCount"] == 1
    assert sorted(out["afterA_universe"]) == ["AAPL", "MSFT", "NVDA"]
    assert out["afterA_mode"] == "auto"
    # the {} clear must fire a real announce, and the universe must actually clear
    assert out["eventsAfterHonestEmpty"] == 1
    assert out["universeAfterHonestEmpty"] == []
    assert out["modeAfterHonestEmpty"] == "auto"


WATCHLIST_RISK_LATCH_SHIM = r"""
var __store = {};
global.localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; },
  setItem: function (k, v) { __store[k] = String(v); }, removeItem: function (k) { delete __store[k]; }
};
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
var docL = {};
var __writes = [];
var nodes = {};
function node(id) {
  if (!nodes[id]) {
    var n = {
      id: id, _html: '', _text: '', style: {}, className: '', _attrs: {},
      classList: { contains: function () { return false; }, toggle: function () {}, add: function () {}, remove: function () {} },
      setAttribute: function (k, v) { this._attrs[k] = v; },
      getAttribute: function (k) { return this._attrs[k] != null ? this._attrs[k] : null; },
      querySelector: function () { return null; }, querySelectorAll: function () { return []; },
      addEventListener: function () {}
    };
    Object.defineProperty(n, 'innerHTML', {
      get: function () { return this._html; },
      set: function (v) { this._html = v; __writes.push({ id: id, value: v }); }
    });
    Object.defineProperty(n, 'textContent', {
      get: function () { return this._text; },
      set: function (v) { this._text = v; __writes.push({ id: id, value: v }); }
    });
    nodes[id] = n;
  }
  return nodes[id];
}
global.document = {
  readyState: 'complete',
  documentElement: {
    _a: {},
    getAttribute: function (k) { return k === 'data-lang' ? 'en' : (this._a[k] || null); },
    setAttribute: function (k, v) { this._a[k] = v; },
    classList: { add: function () {}, remove: function () {} }
  },
  getElementById: function (id) { return node(id); },
  querySelector: function () { return null; }, querySelectorAll: function () { return []; },
  addEventListener: function (t, f) { (docL[t] = docL[t] || []).push(f); },
  removeEventListener: function () {},
  dispatchEvent: function (e) { (docL[e.type] || []).slice().forEach(function (f) { f(e); }); return true; },
  createElement: function () { return { style: {}, classList: { add: function () {} } }; }
};
global.window = global;
global.window.addEventListener = function () {};
global.location = { hash: '', pathname: '/watchlist.html', search: '', origin: 'https://x' };
node('rc_tabs').querySelectorAll = function () { return []; };
window.SD = {};        // signed-in shell
window.RiskCore = {};  // renderRiskCenter takes the REAL path, not the anon lockshell
function OUT(o) { process.stdout.write(JSON.stringify(o)); }
"""


@needs_node
def test_f2_wl_auth_identity_change_resets_risk_full_a_signout_b_sequence():
    """Adapted from the review's proofB_risk_latch_auth.js — real watchlist.js
    execution, extended to a FULL A(sign-in)->signout->B(sign-in) sequence driven
    entirely through real 'wl-auth' events (not direct setRisk() calls, so this
    exercises the actual production sequencing: RISK is only ever populated AFTER
    a real wl-auth has established the identity that produced it), plus a
    langchange republish to prove A's content cannot resurface that way either.

    MUTATION CHECK: delete the `document.addEventListener('wl-auth', ...)` RISK-
    reset block from watchlist.js's wireEvents() and this reds — A's content
    survives into B's session.

    LAW 3 mechanical accommodation (A1A round-3): setRisk() now rejects any
    payload without provenance matching the CURRENT scope+generation (Sol P0,
    fail-closed). This direct setRisk() call stamps `prov: window.WS.prov()`,
    read at the moment of the call, so it is accepted exactly as a real producer's
    publication would be — the assertions below are unchanged and still pin the
    wl-auth identity-reset behavior, not the new provenance seam."""
    script = (
        WATCHLIST_RISK_LATCH_SHIM
        + "\nvar pfCountVal = 3;\nwindow.PF = { count: function () { return pfCountVal; }, render: function () {} };\n"
        + "\nvar WLT = require(%s);\n" % json.dumps(str(WATCHLIST))
        + """
        WLT.setMode('portfolio', false);

        // user A signs in for real (through the actual wl-auth round-trip)
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: { id: 'userA' } } }));
        window.WS.setRisk({
          shares: { USERA_NVDA: 0.62 },
          concHTML: '<p>USERA_NVDA carries 62% of your risk</p>',
          rcTabs: { conc: '<p>USERA_NVDA carries 62% of your risk</p>' },
          labHTML: '', seamItems: null, coverage: null, headline: 'USERA_NVDA 62%',
          prov: window.WS.prov()
        });
        var whileA = node('rc_body').innerHTML;
        var writesBeforeSignOut = __writes.length;

        // A signs out
        pfCountVal = 0;
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: null } }));
        var afterSignOutDom = node('rc_body').innerHTML;

        // user B signs in on the same browser, still in Portfolio mode
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: { id: 'userB' } } }));
        var afterUserBAuthDom = node('rc_body').innerHTML;

        // any ordinary repaint B's session triggers — a langchange republish
        document.dispatchEvent(new CustomEvent('langchange', {}));
        var afterLangchangeDom = node('rc_body').innerHTML;

        // scan the FULL write history from before sign-out onward — never just final state
        var postSignOutWrites = __writes.slice(writesBeforeSignOut);
        var aLeakedPostSignOut = postSignOutWrites.some(function (w) {
          return typeof w.value === 'string' && w.value.indexOf('USERA_NVDA') >= 0;
        });

        OUT({
          mode: window.WS.mode(),
          whileA_showsA: whileA.indexOf('USERA_NVDA') >= 0,
          afterSignOut_showsA: afterSignOutDom.indexOf('USERA_NVDA') >= 0,
          afterUserBAuth_showsA: afterUserBAuthDom.indexOf('USERA_NVDA') >= 0,
          afterLangchange_showsA: afterLangchangeDom.indexOf('USERA_NVDA') >= 0,
          aLeakedPostSignOut: aLeakedPostSignOut
        });
        """
    )
    out = _run_node_script(script)
    assert out["mode"] == "portfolio"
    assert out["whileA_showsA"] is True
    assert out["afterSignOut_showsA"] is False
    assert out["afterUserBAuth_showsA"] is False
    assert out["afterLangchange_showsA"] is False
    assert out["aLeakedPostSignOut"] is False


# ===========================================================================
# F3 (Sol post-review, MAJOR) — anon write failure claimed the ACCOUNT-scoped
# 'failed' copy ("The write to your account failed…") for a visitor with no
# account. Adapted from the review's proofC_anon_write_failure.py.
# ===========================================================================
@needs_node
def test_f3_anon_write_failure_dispatches_failed_local_never_account_copy():
    """MUTATION CHECK: revert dispatchWriteFailure() to plain
    `dispatchPfSave('failed')` (dropping the authority check) and this reds —
    chipHistory would carry 'failed' (the account-scoped word) instead of
    'failed_local' for an anonymous quota/private-mode write failure."""
    out = _run(
        """
        // anonymous visitor (no user() ever set). Storage READS work, WRITES throw —
        // Safari private mode / quota exceeded. This is exactly pfWrite()'s catch.
        localStorage.setItem('mdash.pf.v1', JSON.stringify({v:1, rows:[]}));
        boot();
        await drain(8);
        var isLocal = WSL.portfolio.isLocal();
        var authority = WSL.portfolio.readState().authority;

        localStorage.setItem = function () { throw new Error('QuotaExceededError'); };

        var chipHistory = [];
        document.addEventListener('pf-save', function (e) { chipHistory.push(e.detail.state); });

        // the REAL doSave() UI path an anonymous visitor takes
        node('pfm_ticker').value = 'AAPL';
        node('pfm_shares').value = '1';
        node('pfm_price').value = '1';
        node('pfm_save').dispatch('click', {});
        await drain(8);

        OUT({ isLocal: isLocal, authority: authority, chipHistory: chipHistory });
        """
    )
    assert out["isLocal"] is True
    assert out["authority"] == "local"
    assert out["chipHistory"] == ["saving", "failed_local"]
    assert "failed_local" in out["chipHistory"]
    assert "failed" not in [s for s in out["chipHistory"] if s != "failed_local"]


@needs_node
def test_f3_signed_in_write_failure_still_dispatches_the_account_failed_word():
    """The authority guard must not over-fire: a genuine CLOUD-authority write
    failure still gets the account-scoped 'failed' word, never 'failed_local'."""
    out = _run(
        """
        boot();
        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [], error: null });
        await drain(8);

        var failDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return this; }, insert: function () { return this; },
          single: function () { return Promise.resolve({ data: null, error: { message: 'insert-fail' } }); }
        }; } };
        WSL._setTestSession(USER, failDb);

        var chipHistory = [];
        document.addEventListener('pf-save', function (e) { chipHistory.push(e.detail.state); });
        node('pfm_ticker').value = 'Y';
        node('pfm_shares').value = '1';
        node('pfm_price').value = '1';
        node('pfm_save').dispatch('click', {});
        await drain(8);

        OUT({ chipHistory: chipHistory });
        """,
        {"USER": USER},
    )
    assert "failed" in out["chipHistory"]
    assert "failed_local" not in out["chipHistory"]


# ===========================================================================
# F4 (Sol post-review, MAJOR) — a failed-write chip disclosure was overwritten by
# the next unrelated background read (visibilitychange/'pf-folded' refetch ->
# pfChipStateFor(rs) -> 'clean' "Nothing has changed since"), silently erasing the
# one signal telling the visitor their change did not land.
# ===========================================================================
@needs_node
def test_f4_failed_chip_is_sticky_across_a_background_read_then_clears_on_success():
    """MUTATION CHECK: drop the `writeState === 'failed'` consult from the top of
    pfChipStateFor() and this reds — the background reload (driven here via the
    real 'pf-folded' listener, the same one visibilitychange's refetch and a fold
    completion use) would downgrade the chip to 'clean'."""
    out = _run(
        """
        boot();
        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [], error: null });
        await drain(8);

        var chipHistory = [];
        document.addEventListener('pf-save', function (e) { chipHistory.push(e.detail.state); });

        // a write that FAILS
        var failDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return this; }, insert: function () { return this; },
          single: function () { return Promise.resolve({ data: null, error: { message: 'insert-fail' } }); }
        }; } };
        WSL._setTestSession(USER, failDb);
        node('pfm_ticker').value = 'Y';
        node('pfm_shares').value = '1';
        node('pfm_price').value = '1';
        node('pfm_save').dispatch('click', {});
        await drain(8);
        var chipAfterFailure = chipHistory.slice();

        // a background reload — the exact production trigger for this bug: a plain
        // (non-afterWrite) SUCCESSFUL read must not clear the failure disclosure.
        // Wired through the real 'pf-folded' listener (`reload()` with no args),
        // the same reload() visibilitychange's 60s refetch calls.
        var healthyDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return Promise.resolve({ data: [], error: null }); }
        }; } };
        WSL._setTestSession(USER, healthyDb);
        document.dispatchEvent(new CustomEvent('pf-folded', {}));
        await drain(8);
        var chipAfterBackgroundRead = chipHistory.slice();

        // a SUBSEQUENT successful write clears the sticky failure
        var okDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return Promise.resolve({ data: [], error: null }); },
          insert: function () { return this; },
          single: function () { return Promise.resolve({
            data: { id: 'ok1', ticker: 'Y', shares: 1, entry_price: 1, entry_date: null,
                     notes: null, status: 'open', created_at: '1' },
            error: null
          }); }
        }; } };
        WSL._setTestSession(USER, okDb);
        node('pfm_save').dispatch('click', {});
        await drain(8);
        var chipAfterSuccess = chipHistory.slice();

        OUT({
          chipAfterFailure: chipAfterFailure,
          chipAfterBackgroundRead: chipAfterBackgroundRead,
          chipAfterSuccess: chipAfterSuccess
        });
        """,
        {"USER": USER},
    )
    assert out["chipAfterFailure"][-1] == "failed"
    # the background read may re-affirm 'failed' (a legitimate re-dispatch of the
    # SAME sticky word) but must NEVER downgrade to 'clean' or 'saved' — scan every
    # word appended by the background read, not just the last one
    newWords = out["chipAfterBackgroundRead"][len(out["chipAfterFailure"]):]
    assert all(w == "failed" for w in newWords), out["chipAfterBackgroundRead"]
    assert out["chipAfterBackgroundRead"][-1] == "failed"
    # a subsequent successful write DOES clear it, dispatching 'saved'
    assert out["chipAfterSuccess"][-1] == "saved"


# ===========================================================================
# F6 (Sol post-review, MAJOR) — "loading always resolves" was false: theme.js's
# SDK promise (getSupabaseClient) can pend forever (a stalled connection fires
# neither onload nor onerror), and the PostgREST read itself had no deadline.
# Both async gates in watchstore.js are now bounded by a deadline (default 12s,
# shortened here via the _setCloudDeadlineMs() test seam).
# ===========================================================================
@needs_node
def test_f6_never_settling_client_promise_resolves_terminal_within_deadline():
    """MUTATION CHECK: remove the `Promise.race([clientPromise, clientDeadline.promise])`
    wrapping (racing the bare `clientPromise` directly, as before F6) and this
    reds — a client promise that never settles would leave readState stuck at
    'loading' forever instead of resolving degraded/error within the shortened
    deadline."""
    out = _run(
        """
        boot();
        process.on('unhandledRejection', function () {});
        window.getSupabaseClient = function () { return new Promise(function () {}); };  // never settles
        WSL._setCloudDeadlineMs(50);
        WSL.onAuthUser(USER);
        await drain(2);
        var duringWait = WSL.portfolio.readState();
        await new Promise(function (r) { setTimeout(r, 120); });
        var afterTimeout = WSL.portfolio.readState();
        OUT({ duringWait: duringWait, afterTimeout: afterTimeout });
        """,
        {"USER": USER},
    )
    assert out["duringWait"]["state"] == "loading"
    assert out["afterTimeout"]["authority"] == "cloud"
    assert out["afterTimeout"]["state"] in ("degraded", "error")
    assert out["afterTimeout"]["warning"] == "client-timeout"


@needs_node
def test_f6_client_late_settle_after_timeout_reconciles_to_ready():
    """A client promise that eventually DOES resolve, after this file's own timeout
    already declared it unavailable, must still correct the state — not be
    silently discarded."""
    out = _run(
        """
        boot();
        process.on('unhandledRejection', function () {});
        var resolveClient;
        window.getSupabaseClient = function () {
          return new Promise(function (res) { resolveClient = res; });
        };
        WSL._setCloudDeadlineMs(50);
        WSL.onAuthUser(USER);
        await new Promise(function (r) { setTimeout(r, 120); });
        var afterTimeout = WSL.portfolio.readState();

        // the real client finally resolves, late
        resolveClient({ from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return Promise.resolve({ data: [], error: null }); }
        }; } });
        await drain(10);
        var afterLateSettle = WSL.portfolio.readState();

        OUT({ afterTimeout: afterTimeout, afterLateSettle: afterLateSettle });
        """,
        {"USER": USER},
    )
    assert out["afterTimeout"]["warning"] == "client-timeout"
    assert out["afterLateSettle"]["state"] == "ready"
    assert out["afterLateSettle"]["warning"] is None


@needs_node
def test_f6_never_settling_read_resolves_terminal_within_deadline():
    """MUTATION CHECK: remove the `Promise.race([readPromise, readDeadline.promise])`
    wrapping in watchstore.js's portfolioList() (racing the bare `readPromise`
    directly) and this reds — a read that never settles would leave the caller's
    promise pending forever instead of resolving degraded/error within the
    shortened deadline."""
    out = _run(
        """
        boot();
        WSL._setCloudDeadlineMs(50);
        var neverSettleDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return new Promise(function () {}); }  // never settles
        }; } };
        WSL._setTestSession(USER, neverSettleDb);
        WSL.portfolio.list().then(function (rows) {
          OUT({ rows: rows, readState: WSL.portfolio.readState() });
        });
        """,
        {"USER": USER},
    )
    assert out["rows"] is None
    assert out["readState"]["authority"] == "cloud"
    assert out["readState"]["state"] == "error"
    assert out["readState"]["warning"] == "read-timeout"


@needs_node
def test_f6_read_late_settle_after_timeout_reconciles_to_ready():
    """A read that eventually DOES resolve, after this file's own timeout already
    declared it unknown, must still correct pfReadState for the NEXT reader —
    the exact same code path an on-time read uses."""
    out = _run(
        """
        boot();
        WSL._setCloudDeadlineMs(50);
        var resolveOrder;
        var lateDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return new Promise(function (res) { resolveOrder = res; }); }
        }; } };
        WSL._setTestSession(USER, lateDb);
        var firstResult = await WSL.portfolio.list();
        var afterTimeout = WSL.portfolio.readState();

        resolveOrder({ data: [], error: null });
        await drain(10);
        var afterLateSettle = WSL.portfolio.readState();

        OUT({ firstResult: firstResult, afterTimeout: afterTimeout, afterLateSettle: afterLateSettle });
        """,
        {"USER": USER},
    )
    assert out["firstResult"] is None
    assert out["afterTimeout"]["warning"] == "read-timeout"
    assert out["afterLateSettle"]["state"] == "ready"
    assert out["afterLateSettle"]["warning"] is None


# ===========================================================================
# F7 (Sol post-review, MINOR) — test integrity.
# (i) the wl-auth re-fire chain in watchstore.js's getClient().catch() was UNPINNED:
# every client-init test in this suite hand-dispatches 'wl-auth' via _setTestSession
# rather than driving the REAL onAuthUser()/getClient() chain, so deleting the
# re-fire left every prior test green. This test drives the REAL chain end to end —
# no hand-dispatch anywhere.
# ===========================================================================
@needs_node
def test_f7_getclient_reject_refires_wl_auth_through_the_real_chain_no_hand_dispatch():
    """MUTATION CHECK: delete the `document.dispatchEvent(new CustomEvent('wl-auth',
    ...))` re-fire line from watchstore.js's `clientFailed()` (getClient().catch()
    path) and this reds — portfolio.js's readState would stay stuck at the FIRST
    (pre-rejection) 'loading' answer forever, because nothing ever tells it to
    re-read. This test never calls document.dispatchEvent('wl-auth', ...) itself —
    the ENTIRE transition is driven by the real onAuthUser()/getClient() chain."""
    out = _run(
        """
        boot();
        process.on('unhandledRejection', function () {});
        window.getSupabaseClient = function () { return Promise.reject(new Error('SDK blocked')); };
        // the ONE real entry point — onAuthUser() is what a real sign-in calls;
        // everything downstream (the first 'wl-auth', getClient(), the catch, the
        // re-fired 'wl-auth', portfolio.js's onAuth() re-reading through
        // portfolioList()) is the REAL production chain, not a hand-dispatch.
        WSL.onAuthUser(USER);
        await drain(10);
        var readState = WSL.portfolio.readState();
        var pfReadState = window.PF.readState();
        OUT({ readState: readState, pfReadState: pfReadState });
        """,
        {"USER": USER},
    )
    assert out["readState"]["authority"] == "cloud"
    assert out["readState"]["state"] in ("degraded", "error")
    assert out["readState"]["warning"] == "client-unavailable"
    # portfolio.js's OWN mirror (window.PF.readState()) only updates because the
    # re-fired 'wl-auth' actually reached its listener — proof the chain is real
    assert out["pfReadState"]["state"] in ("degraded", "error")


# ===========================================================================
# Harness non-vacuity follow-on (found via the browser after-proof re-run, Sol
# post-review): portfolio.js's pushFxWeights() and the rows===null branch's FX
# clear both used to push AUTO_W regardless of which workspace tab was active —
# an honest-empty {} push (F2's own fix) is still a NON-null AUTO_W, so it
# permanently locked factor_exposure.js into 'auto' mode with nothing in it,
# silently blanking the Watchlists tab's OWN fx-weights panel even while the
# reader was looking at it. Both call sites now gate on window.WS.mode().
# ===========================================================================
@needs_node
def test_pushfxweights_never_pushes_while_watchlists_tab_is_active():
    """MUTATION CHECK: delete the `pushMode` gate from pushFxWeights() (portfolio.js)
    and this reds — a render pass that happens to fire while window.WS.mode()
    reports 'watchlists' must push NOTHING to FX, honest-empty or otherwise."""
    out = _run(
        """
        boot();
        window.WS.mode = function () { return 'watchlists'; };
        __fxCalls.length = 0;

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [], error: null });   // zero positions, resolved
        await drain(8);

        OUT({ fxCalls: __fxCalls });
        """,
        {"USER": USER},
    )
    assert out["fxCalls"] == [], out["fxCalls"]


@needs_node
def test_pushfxweights_still_pushes_when_ws_mode_is_absent_or_portfolio():
    """The gate must default to allowing the push when window.WS.mode is absent
    (an isolated test harness, or watchlist.js not on the page — every EXISTING
    behavior this suite's other tests rely on) — not silently go quiet everywhere."""
    out = _run(
        """
        boot();
        __fxCalls.length = 0;

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [], error: null });
        await drain(8);

        OUT({ fxCalls: __fxCalls });
        """,
        {"USER": USER},
    )
    assert {} in out["fxCalls"], out["fxCalls"]


# ===========================================================================
# N1 (Sol post-review, MAJOR, freeze §5 — inverse of blocker 1) — watchlist_risk.js
# publish() forwards EVERY payload to window.PF.setBookRisk() with no mode/universe
# guard. Adapted from the review's proofF_bookrisk_crossmode.py / proofF2_copy.py.
# ===========================================================================
@needs_node
def test_n1_foreign_watchlist_keyed_payload_never_repaints_portfolio_surfaces():
    """MUTATION CHECK: delete the `payloadIsConsistentWithBook` guard from
    setBookRisk() (portfolio.js) and this reds — a WATCHLIST-keyed payload would
    repaint tbl_pf/pf_scope/pf_rowcount/ws_book_* /ws_att* even though none of its
    names are in the portfolio's own open rows."""
    out = _run(
        """
        boot();
        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        // a real signed-in portfolio: AAPL + MSFT, both sized and priced
        db.settleNext({ data: [
          { id:'p1', ticker:'AAPL', shares:10, entry_price:100, entry_date:null, notes:null, status:'open', created_at:'1' },
          { id:'p2', ticker:'MSFT', shares:5,  entry_price:200, entry_date:null, notes:null, status:'open', created_at:'2' }
        ], error:null });
        await drain(10);
        var writesBefore = __writes.length;

        // EXACTLY what watchlist_risk.js's publish() does when the reader is on
        // the Watchlists tab under this branch (F2 made FX announce the WATCHLIST
        // universe there for real) — a payload keyed to the WATCHLIST's names.
        window.PF.setBookRisk({
          shares: { WLONLY_TSLA: 0.71, WLONLY_META: 0.29 },
          covered: { WLONLY_TSLA: 1, WLONLY_META: 1 },
          bets: null, modeledN: 2, regime: '', concHTML: '', rcTabs: null, labHTML: '',
          // LAW 3 mechanical accommodation: valid (portfolio-scope, matching the
          // SHIM's constant gen) provenance, so this call reaches
          // payloadIsConsistentWithBook() — the SYMBOL-overlap layer this test
          // actually pins — rather than being rejected earlier for scope alone.
          prov: { scope: 'portfolio', gen: 0 }
        });
        await drain(4);
        var writesAfter = __writes.length;
        var tbl = node('tbl_pf').innerHTML;

        // switching back to Portfolio explicitly forces a repaint — must never
        // show the foreign payload's stale state
        window.PF.render();
        await drain(4);
        var tblAfterSwitchBack = node('tbl_pf').innerHTML;

        OUT({
          portfolioRowsPresent: tbl.indexOf('AAPL') >= 0 && tbl.indexOf('MSFT') >= 0,
          setBookRiskRepainted: writesAfter > writesBefore,
          aaplStillCoveredAfterWatchlistPayload: tbl.indexOf('AAPL') >= 0,
          tableAfterSwitchBack_hasAAPL: tblAfterSwitchBack.indexOf('AAPL') >= 0
        });
        """,
        {"USER": USER},
    )
    assert out["portfolioRowsPresent"] is True
    assert out["setBookRiskRepainted"] is False
    assert out["aaplStillCoveredAfterWatchlistPayload"] is True
    assert out["tableAfterSwitchBack_hasAAPL"] is True


@needs_node
def test_n1_foreign_payload_never_produces_the_false_coverage_sentence():
    """MUTATION CHECK: same as above — with the guard removed, this reds because
    a fully-modeled 2-position book would show 'positions sit outside the risk
    model' after a watchlist-keyed payload lands."""
    out = _run(
        """
        boot();
        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [
          { id:'p1', ticker:'AAPL', shares:10, entry_price:100, entry_date:null, notes:null, status:'open', created_at:'1' },
          { id:'p2', ticker:'MSFT', shares:5,  entry_price:200, entry_date:null, notes:null, status:'open', created_at:'2' }
        ], error:null });
        await drain(10);
        // a genuine PORTFOLIO-derived payload first (valid provenance — LAW 3
        // mechanical accommodation, matching the SHIM's constant window.WS.prov())
        window.PF.setBookRisk({ shares: { AAPL: 0.6, MSFT: 0.4 }, covered: { AAPL: 1, MSFT: 1 },
                                 bets: null, modeledN: 2, regime: '', concHTML: '', rcTabs: null, labHTML: '',
                                 prov: { scope: 'portfolio', gen: 0 } });
        await drain(3);
        var covPortfolio = node('ws_book_coverage').innerHTML;

        // now the WATCHLIST-derived payload (same valid provenance, so this
        // reaches payloadIsConsistentWithBook()'s symbol-overlap rejection, not
        // LAW 3's earlier scope gate — the mechanism this test actually pins)
        window.PF.setBookRisk({ shares: { WLONLY_TSLA: 0.71, WLONLY_META: 0.29 },
                                 covered: { WLONLY_TSLA: 1, WLONLY_META: 1 },
                                 bets: null, modeledN: 2, regime: '', concHTML: '', rcTabs: null, labHTML: '',
                                 prov: { scope: 'portfolio', gen: 0 } });
        await drain(3);
        OUT({
          coverage_portfolioPayload: covPortfolio,
          coverage_watchlistPayload: node('ws_book_coverage').innerHTML
        });
        """,
        {"USER": USER},
    )
    assert "outside the risk model" not in out["coverage_watchlistPayload"]
    # the rejected payload leaves the coverage line UNCHANGED from before the attempt
    assert out["coverage_watchlistPayload"] == out["coverage_portfolioPayload"]


@needs_node
def test_n1_empty_payload_is_still_accepted_as_a_clear():
    """The validation must not become so strict it also blocks the honest S3/F2
    'nothing to weight' signal — an empty payload (no per-name keys at all) is
    always a legitimate clear."""
    out = _run(
        """
        boot();
        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [
          { id:'p1', ticker:'AAPL', shares:10, entry_price:100, entry_date:null, notes:null, status:'open', created_at:'1' }
        ], error:null });
        await drain(10);
        var writesBefore = __writes.length;
        window.PF.setBookRisk({ shares: {}, covered: {}, bets: null, modeledN: 0,
                                 regime: '', concHTML: '', rcTabs: null, labHTML: '',
                                 // LAW 3: valid provenance — this test is pinning the
                                 // empty-payload early-accept INSIDE
                                 // payloadIsConsistentWithBook(), which only runs once
                                 // the provenance gate itself has already passed.
                                 prov: { scope: 'portfolio', gen: 0 } });
        await drain(4);
        OUT({ repainted: __writes.length > writesBefore });
        """,
        {"USER": USER},
    )
    assert out["repainted"] is True


@needs_node
def test_n1_mode_boundary_reset_prevents_stale_foreign_payload_on_switch_back():
    """Drives the boundary reset via the REAL watchlist.js setMode() chain
    (requires watchlist.js too, unlike the other N1 tests which call
    window.PF.setBookRisk() directly) — proves resetBookRisk() is actually wired
    into the mode-entry boundary, not just present as an unused function.

    MUTATION CHECK: delete the `window.PF.resetBookRisk()` call from setMode()'s
    `enteringPortfolio` branch (templates/watchlist.js) and this reds."""
    script = (
        WATCHLIST_RISK_LATCH_SHIM
        + "\nvar pfCountVal = 2;\n"
        + "\nvar WLT = require(%s);\n" % json.dumps(str(WATCHLIST))
        + "\nvar PORTFOLIO_SRC = require('fs').readFileSync(%s, 'utf8');\n" % json.dumps(str(PORTFOLIO))
        + """
        // a minimal real portfolio.js consumer stand-in is unnecessary here — this
        // test only needs to prove the CALL happens, via a spy on window.PF.
        var resetCalls = 0;
        window.PF = { count: function () { return pfCountVal; }, render: function () {},
                       resetBookRisk: function () { resetCalls++; } };
        WLT.setMode('watchlists', false);
        var callsAfterWatchlists = resetCalls;
        WLT.setMode('portfolio', false);
        OUT({ callsAfterWatchlists: callsAfterWatchlists, callsAfterPortfolio: resetCalls });
        """
    )
    out = _run_node_script(script)
    # entering watchlists does NOT touch portfolio.js's own book-risk latch
    assert out["callsAfterWatchlists"] == 0
    # entering portfolio DOES reset it
    assert out["callsAfterPortfolio"] == 1


# ===========================================================================
# N2 (Sol post-review, MAJOR, re-opens F3) — sticky-failed leaks across identity.
# writeState was never reset by onAuth(), and pfChipStateFor's sticky branch sat
# BEFORE the authority guard — a signed-in write failure's account-scoped 'failed'
# leaked onto the NEXT identity's first read. Adapted from proofG_sticky_failed_leak.py.
# ===========================================================================
@needs_node
def test_n2_signout_after_a_failed_write_never_shows_the_account_scoped_chip():
    """proofG scenario d2. MUTATION CHECK: drop the writeState reset from onAuth()
    (portfolio.js) and this reds — the anonymous chip after sign-out would still
    read 'failed' instead of 'local'."""
    out = _run(
        """
        boot();
        var chip = [];
        document.addEventListener('pf-save', function (e) { chip.push(e.detail.state); });

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [], error: null });
        await drain(8);

        var failDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; }, order: function () { return this; },
          insert: function () { return this; },
          single: function () { return Promise.resolve({ data: null, error: { message: 'insert-fail' } }); }
        }; } };
        WSL._setTestSession(USER, failDb);
        node('pfm_ticker').value = 'Y'; node('pfm_shares').value = '1'; node('pfm_price').value = '1';
        node('pfm_save').dispatch('click', {});
        await drain(8);
        var afterFailure = chip.slice();

        chip.length = 0;
        WSL._setTestSession(null, null);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: null } }));
        await drain(10);

        OUT({ afterFailure: afterFailure, afterSignOut: chip.slice(),
              anonAuthority: WSL.portfolio.readState().authority });
        """,
        {"USER": USER},
    )
    assert out["afterFailure"][-1] == "failed"
    assert out["anonAuthority"] == "local"
    assert "failed" not in out["afterSignOut"]
    assert out["afterSignOut"] == ["local"]


@needs_node
def test_n2_second_user_first_healthy_read_never_inherits_the_prior_users_failed_chip():
    """proofG scenario d3. MUTATION CHECK: same as above."""
    out = _run(
        """
        boot();
        var chip = [];
        document.addEventListener('pf-save', function (e) { chip.push(e.detail.state); });

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [], error: null });
        await drain(8);

        var failDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; }, order: function () { return this; },
          insert: function () { return this; },
          single: function () { return Promise.resolve({ data: null, error: { message: 'insert-fail' } }); }
        }; } };
        WSL._setTestSession(USER, failDb);
        node('pfm_ticker').value = 'Z'; node('pfm_shares').value = '1'; node('pfm_price').value = '1';
        node('pfm_save').dispatch('click', {});
        await drain(8);

        chip.length = 0;
        var dbB = makeDeferredDb();
        WSL._setTestSession(USER_B, dbB.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER_B } }));
        await drain(3);
        dbB.settleNext({ data: [], error: null });
        await drain(10);

        OUT({ afterUserB: chip.slice() });
        """,
        {"USER": USER, "USER_B": {"id": "userB"}},
    )
    assert "failed" not in out["afterUserB"]
    assert out["afterUserB"] == ["clean"]


@needs_node
def test_n2_anons_own_local_write_failure_still_shows_sticky_failed_local():
    """The reorder must not throw out the honest half: an anonymous visitor's OWN
    LOCAL write failure is still sticky (failed_local), never silently cleared by
    an unrelated background read while still local authority."""
    out = _run(
        """
        localStorage.setItem('mdash.pf.v1', JSON.stringify({v:1, rows:[]}));
        boot();
        await drain(8);

        var realSet = localStorage.setItem;
        localStorage.setItem = function () { throw new Error('QuotaExceededError'); };
        var chip = [];
        document.addEventListener('pf-save', function (e) { chip.push(e.detail.state); });
        node('pfm_ticker').value = 'AAPL'; node('pfm_shares').value = '1'; node('pfm_price').value = '1';
        node('pfm_save').dispatch('click', {});
        await drain(8);
        var afterFailure = chip.slice();

        // restore storage and trigger an unrelated background reload — must NOT
        // downgrade the sticky failed_local to 'local'
        localStorage.setItem = realSet;
        chip.length = 0;
        document.dispatchEvent(new CustomEvent('pf-folded', {}));
        await drain(8);

        OUT({ afterFailure: afterFailure, afterBackgroundRead: chip.slice() });
        """
    )
    assert out["afterFailure"][-1] == "failed_local"
    assert "failed_local" in out["afterBackgroundRead"] or out["afterBackgroundRead"] == []


@needs_node
def test_n2_reorder_isolated_stale_writestate_via_background_reload_without_fresh_wlauth():
    """Isolates the reorder half of N2 from the writeState-reset half: forces
    watchstore's underlying authority to flip to 'local' WITHOUT dispatching a
    fresh 'wl-auth' event (so onAuth()'s identity-reset never runs), then drives
    a plain background reload() (via 'pf-folded', which does not reset
    writeState) — the ONLY thing that can suppress the stale account-scoped
    'failed' here is pfChipStateFor's authority-guard-first ordering.

    MUTATION CHECK: revert pfChipStateFor() to check the sticky writeState
    BEFORE the authority guard and this reds."""
    out = _run(
        """
        boot();
        var chip = [];
        document.addEventListener('pf-save', function (e) { chip.push(e.detail.state); });

        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [], error: null });
        await drain(8);

        var failDb = { from: function () { return {
          select: function () { return this; }, eq: function () { return this; }, order: function () { return this; },
          insert: function () { return this; },
          single: function () { return Promise.resolve({ data: null, error: { message: 'insert-fail' } }); }
        }; } };
        WSL._setTestSession(USER, failDb);
        node('pfm_ticker').value = 'Y'; node('pfm_shares').value = '1'; node('pfm_price').value = '1';
        node('pfm_save').dispatch('click', {});
        await drain(8);
        var afterFailure = chip.slice();

        // flip watchstore's underlying authority to anonymous WITHOUT a fresh
        // 'wl-auth' dispatch — onAuth()'s identity-reset (the OTHER half of N2)
        // never runs for this transition
        WSL._setTestSession(null, null);
        chip.length = 0;
        document.dispatchEvent(new CustomEvent('pf-folded', {}));
        await drain(8);

        OUT({ afterFailure: afterFailure, afterBackgroundReload: chip.slice() });
        """,
        {"USER": USER},
    )
    assert out["afterFailure"][-1] == "failed"
    assert "failed" not in out["afterBackgroundReload"]


# ===========================================================================
# N3 (Sol post-review, MINOR) — stale deadline timer. clientFailed's late-settle
# guard was uid-only, so a sign-out then a sign-in of the SAME uid let session 1's
# client-gate timer fire into session 2's state (~30% early terminal + a spurious
# offline pill). Adapted from proofI_deadline_races.py's C2 scene.
# ===========================================================================
@needs_node
def test_n3_stale_deadline_timer_from_a_prior_same_uid_session_never_fires():
    """MUTATION CHECK: revert clientReady()/clientFailed() to the uid-only guard
    (`if ((user && user.id) !== uidAtCall) return;`, dropping the `authEpoch`
    check) and this reds — session 1's 200ms timer would still land its terminal
    'error'/'client-timeout' state into session 2 at ~142ms, well before session
    2's own deadline."""
    out = _run(
        """
        boot();
        process.on('unhandledRejection', function () {});
        var hung = new Promise(function () {});                  // never settles, shared
        window.getSupabaseClient = function () { return hung; }; // theme.js caches _sbLoading
        WSL._setCloudDeadlineMs(200);
        WSL.onAuthUser(USER);                                     // session 1, timer T1 @200ms
        await new Promise(function (r) { setTimeout(r, 60); });
        WSL.onAuthUser(null);                                     // sign out
        await new Promise(function (r) { setTimeout(r, 20); });
        WSL.onAuthUser(USER);                                     // session 2 @~80ms, timer T2 @280ms
        await new Promise(function (r) { setTimeout(r, 140); });  // ~220ms total: T1 fired, T2 has NOT
        OUT({ session2ReadStateWhenT1Fired: WSL.portfolio.readState() });
        """,
        {"USER": USER},
    )
    # T1 (session 1's timer) must NOT have landed into session 2 — session 2's own
    # read is still honestly 'loading' at this point (its own 200ms has not elapsed)
    assert out["session2ReadStateWhenT1Fired"]["state"] == "loading"
    assert out["session2ReadStateWhenT1Fired"]["warning"] is None


# ===========================================================================
# N5 (Sol post-review, NIT) — factor_exposure.js hid the panel without clearing
# its innerHTML, leaving the prior book's factor bars sitting in the hidden DOM.
# ===========================================================================
@needs_node
def test_n5_hiding_the_fx_panel_also_clears_its_innerhtml():
    """MUTATION CHECK: drop the `panel.innerHTML = '';` clears from render()'s two
    hide sites (factor_exposure.js) and this reds — the panel would still contain
    the PRIOR (3-name) book's factor bars after it is hidden for a thin (1-name)
    book."""
    script = (
        FACTOR_EXPOSURE_SHIM
        + "\nrequire(%s);\n" % json.dumps(str(FACTOR_EXPOSURE))
        + """
        (async function () {
          // a real 3-name book — panel renders and gets real content
          window.FX.setAutoWeights({ AAPL: 1000, MSFT: 2000, NVDA: 3000 });
          await drain(10);
          var htmlAfterRealBook = panel.innerHTML;
          var displayAfterRealBook = panel.style.display;

          // now a THIN (1-name) book — aggregate() reports ok:false, panel hides
          window.FX.setAutoWeights({ AAPL: 1000 });
          await drain(10);

          OUT({
            htmlAfterRealBook_nonEmpty: htmlAfterRealBook.length > 0,
            displayAfterRealBook: displayAfterRealBook,
            displayAfterThinBook: panel.style.display,
            htmlAfterThinBook: panel.innerHTML
          });
        })();
        """
    )
    out = _run_node_script(script)
    assert out["htmlAfterRealBook_nonEmpty"] is True
    assert out["displayAfterRealBook"] == "block"
    assert out["displayAfterThinBook"] == "none"
    assert out["htmlAfterThinBook"] == ""


# ===========================================================================
# A1A ROUND 3 (frozen spec FROZEN_SPEC_R3.md, Sol's 2026-08-21 P0) — auth-
# generation binding (LAW 1), consumer request-generation guard (LAW 2), risk
# provenance (LAW 3), client terminality (LAW 4). Sol rejected round-2 acceptance
# with an executed reproduction (scratchpad dbg2/) showing user A's late-
# resolving read painting A's private rows under user B, a deferred risk
# republish repainting a watchlist-derived Risk Center read into a zero-position
# Portfolio, and two client-init paths leaving loading permanently unresolved.
# ===========================================================================

# ---------------------------------------------------------------------------
# T-D1a/b/c — LAW 1 (watchstore.js): every Portfolio operation binds to the
# auth epoch captured AT ENTRY; a stale-epoch resolution mutates nothing and
# answers null, never the resolved rows.
# ---------------------------------------------------------------------------
@needs_node
def test_d1a_late_resolving_read_under_a_stale_identity_never_touches_state_or_degrades_into_it():
    """T-D1a (frozen spec LAW 1a; Sol's exact P0 scenario). A's cloud read is
    PENDING when A signs out and B signs in and readies; only THEN does A's
    stale read resolve, carrying A's PRIVATE row. Assert pfReadState (which
    folds in pfLastGoodCloud's bookkeeping) is byte-identical before and after
    A's late resolution — then prove B's NEXT read failing degrades to B's OWN
    last-good, never A's rows.

    MUTATION CHECK: remove the `if (authEpoch !== epochAtCall) return null;`
    guard from portfolioList()'s readPromise .then handler (watchstore.js) and
    this reds — A's row lands in pfLastGoodCloud under B's session, and B's next
    FAILED read then degrade-serves A's private AAAA_PRIVATE_A row as B's own
    last-good."""
    out = _run(
        """
        boot();
        var A = { id: 'user-A' }, B = { id: 'user-B' };
        var dbA = makeDeferredDb(), dbB = makeDeferredDb();

        WSL.onAuthUser(A);
        WSL._setTestSession(A, dbA.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: A } }));
        await drain(5);

        // A signs out; B signs in and readies — A's read is STILL pending
        WSL.onAuthUser(null);
        WSL.onAuthUser(B);
        WSL._setTestSession(B, dbB.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: B } }));
        await drain(5);
        dbB.settleNext({ data: [{ id: 'b1', ticker: 'BBBB_OWNED_B', shares: 5, entry_price: 50,
                                    entry_date: null, notes: null, status: 'open', created_at: '1' }],
                          error: null });
        await drain(8);
        var beforeLate = WSL.portfolio.readState();

        // A's OLD read now resolves, with A's PRIVATE row
        dbA.settleNext({ data: [{ id: 'a1', ticker: 'AAAA_PRIVATE_A', shares: 100, entry_price: 10,
                                    entry_date: null, notes: null, status: 'open', created_at: '1' }],
                          error: null });
        await drain(10);
        var afterLate = WSL.portfolio.readState();
        var domAfterLate = node('tbl_pf').innerHTML;

        // B's NEXT read fails -> degraded fallback must serve B's OWN last-good,
        // never A's rows (re-fire 'wl-auth' with the SAME identity, the house
        // pattern scenario3 already uses to trigger "a LATER read")
        var dbB2 = makeDeferredDb();
        WSL._setTestSession(B, dbB2.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: B } }));
        await drain(3);
        dbB2.settleNext({ data: null, error: { message: 'network down' } });
        await drain(8);

        OUT({
          beforeLate: beforeLate, afterLate: afterLate,
          domAfterLate_hasA: domAfterLate.indexOf('AAAA_PRIVATE_A') >= 0,
          degradedReadState: WSL.portfolio.readState(),
          degradedDom_hasB: node('tbl_pf').innerHTML.indexOf('BBBB_OWNED_B') >= 0,
          degradedDom_hasA: node('tbl_pf').innerHTML.indexOf('AAAA_PRIVATE_A') >= 0
        });
        """
    )
    assert out["beforeLate"] == out["afterLate"], (
        "A's late resolution mutated pfReadState/pfLastGoodCloud under B's session")
    assert out["domAfterLate_hasA"] is False
    assert out["degradedReadState"]["state"] == "degraded"
    assert out["degradedReadState"]["last_good_at"] == out["beforeLate"]["last_good_at"]
    assert out["degradedDom_hasB"] is True
    assert out["degradedDom_hasA"] is False


@needs_node
def test_f4_stale_epoch_read_rejection_never_touches_state_under_the_new_identity():
    """F4 (adversarial review, MINOR — T-D1a extra leg, the ordinary .catch
    path). Same shape as T-D1a, but A's stale `order()` call itself REJECTS
    (a genuine promise rejection — a network-level failure, not the Supabase
    `{data,error}` convention, which the readPromise .then handler's OWN epoch
    guard already intercepts before ever inspecting `.error`, so it cannot
    reach .catch() at all under a stale epoch) after the epoch flip. readState()
    and portfolioOk must be byte-identical before and after — the stale
    rejection must not flip portfolioOk or warn under B's identity either.

    MUTATION CHECK: remove the `if (authEpoch !== epochAtCall) return null;`
    guard from portfolioList()'s readPromise .catch handler (watchstore.js,
    M2) and this reds — A's rejected read flips portfolioOk to false and
    mutates pfReadState under B's session."""
    out = _run(
        """
        boot();
        var A = { id: 'user-A' }, B = { id: 'user-B' };
        var dbA = { _p: [], from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return new Promise(function (r, j) { dbA._p.push({ res: r, rej: j }); }); }
        }; } };
        var dbB = makeDeferredDb();

        WSL.onAuthUser(A);
        WSL._setTestSession(A, dbA);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: A } }));
        await drain(5);

        WSL.onAuthUser(null);
        WSL.onAuthUser(B);
        WSL._setTestSession(B, dbB.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: B } }));
        await drain(5);
        dbB.settleNext({ data: [{ id: 'b1', ticker: 'BBBB_OWNED_B', shares: 5, entry_price: 50,
                                    entry_date: null, notes: null, status: 'open', created_at: '1' }],
                          error: null });
        await drain(8);
        var beforeLate = WSL.portfolio.readState();
        var okBefore = window.WatchStore.portfolioOk();

        // A's OLD `order()` call now genuinely REJECTS
        dbA._p[0].rej(new Error('A read boom'));
        await drain(10);
        var afterLate = WSL.portfolio.readState();
        var okAfter = window.WatchStore.portfolioOk();

        OUT({ pendingCount: dbA._p.length, beforeLate: beforeLate, afterLate: afterLate,
              okBefore: okBefore, okAfter: okAfter });
        """
    )
    assert out["pendingCount"] == 1, "sanity: A's read genuinely reached order() and registered pending"
    assert out["okBefore"] is True
    assert out["okAfter"] is True, "A's stale REJECTED read flipped portfolioOk under B's session"
    assert out["beforeLate"] == out["afterLate"], (
        "A's stale rejection mutated pfReadState under B's session")


@needs_node
def test_f4_stale_epoch_read_timeout_never_touches_state_under_the_new_identity():
    """F4 (adversarial review, MINOR — T-D1a extra leg, the read-timeout race
    path). A's read never settles at all; its own per-call deadline (shortened
    via `_setCloudDeadlineMs`) elapses AFTER A signs out and B signs in and
    readies. readState() must be byte-identical before and after the deadline
    fires — the timed-out call answering under a LATER identity must never
    claim last-good rows that may belong to the previous identity.

    MUTATION CHECK: remove the `if (authEpoch !== epochAtCall) return null;`
    guard from the read-timeout race's .catch handler (watchstore.js, M3) and
    this reds — A's stale timeout overwrites pfReadState under B's session."""
    out = _run(
        """
        boot();
        WSL._setCloudDeadlineMs(20);
        var A = { id: 'user-A' }, B = { id: 'user-B' };
        var dbA = makeDeferredDb(), dbB = makeDeferredDb();

        WSL.onAuthUser(A);
        WSL._setTestSession(A, dbA.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: A } }));
        await drain(5);
        // A's read is issued and left PENDING FOREVER -- its own 20ms deadline
        // will fire on its own, well after the identity flip below.

        WSL.onAuthUser(null);
        WSL.onAuthUser(B);
        WSL._setTestSession(B, dbB.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: B } }));
        await drain(5);
        dbB.settleNext({ data: [{ id: 'b1', ticker: 'BBBB_OWNED_B', shares: 5, entry_price: 50,
                                    entry_date: null, notes: null, status: 'open', created_at: '1' }],
                          error: null });
        await drain(8);
        var beforeTimeout = WSL.portfolio.readState();

        // wait well past A's shortened 20ms deadline
        await new Promise(function (r) { setTimeout(r, 150); });
        await drain(10);
        var afterTimeout = WSL.portfolio.readState();

        OUT({ beforeTimeout: beforeTimeout, afterTimeout: afterTimeout });
        """
    )
    assert out["beforeTimeout"] == out["afterTimeout"], (
        "A's stale read-timeout mutated pfReadState under B's session: %r vs %r"
        % (out["beforeTimeout"], out["afterTimeout"]))


@needs_node
def test_d1b_stale_consumer_then_resolution_is_fully_discarded():
    """T-D1b (frozen spec LAW 2, portfolio.js's consumer request-generation
    guard). Two overlapping reload() calls (both via the real 'pf-folded' event,
    the same public trigger test_n2_* already uses) — the OLDER settles LAST,
    with genuinely different data. Its .then handler must mutate NOTHING:
    portfolio.js's own readState mirror, the DOM, count, the chip dispatch
    history and the FX push chain must all be byte-identical to right after the
    newer call settled.

    MUTATION CHECK: remove the `if (gen !== loadGen) return;` guard from
    reload()'s .then handler (portfolio.js) and this reds — the stale OLDER
    call's data (STALE_OLDER_ROW) repaints over the newer call's answer."""
    out = _run(
        """
        boot();
        var db = { _p: [], from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return new Promise(function (r) { db._p.push(r); }); }
        }; } };
        function settleAt(i, result) { var r = db._p[i]; db._p[i] = null; if (r) r(result); }

        WSL._setTestSession(USER, db);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        settleAt(0, { data: [{ id: 'c0', ticker: 'INITIAL', shares: 1, entry_price: 1,
          entry_date: null, notes: null, status: 'open', created_at: '0' }], error: null });
        await drain(8);

        var chipHistory = [];
        document.addEventListener('pf-save', function (e) { chipHistory.push(e.detail.state); });
        var fxCallsBefore = __fxCalls.length;

        // call #1 (OLDER) via a real 'pf-folded' background refetch -> reload()
        document.dispatchEvent(new CustomEvent('pf-folded', {}));
        await drain(3);
        // call #2 (NEWER) -- a second 'pf-folded' BEFORE #1 resolves
        document.dispatchEvent(new CustomEvent('pf-folded', {}));
        await drain(3);
        var pendingAfterBoth = db._p.filter(function (x) { return x; }).length;

        // index 0 was already consumed by the initial signed-in read above, so
        // index 1 is call #1 (OLDER, the FIRST 'pf-folded') and index 2 is call
        // #2 (NEWER, the SECOND 'pf-folded') — resolve the NEWER (index 2) FIRST
        settleAt(2, { data: [{ id: 'c2', ticker: 'NEWER_ROW', shares: 2, entry_price: 2,
          entry_date: null, notes: null, status: 'open', created_at: '2' }], error: null });
        await drain(8);
        var afterNewer = {
          dom: node('tbl_pf').innerHTML, count: window.PF.count(),
          chipLen: chipHistory.length, fxLen: __fxCalls.length,
          pfReadState: window.PF.readState()
        };

        // resolve the OLDER (STALE) call (index 1) LAST — must change NOTHING
        settleAt(1, { data: [{ id: 'c1', ticker: 'STALE_OLDER_ROW', shares: 9, entry_price: 9,
          entry_date: null, notes: null, status: 'open', created_at: '1' }], error: null });
        await drain(8);
        var afterStale = {
          dom: node('tbl_pf').innerHTML, count: window.PF.count(),
          chipLen: chipHistory.length, fxLen: __fxCalls.length,
          pfReadState: window.PF.readState()
        };

        OUT({ pendingAfterBoth: pendingAfterBoth, afterNewer: afterNewer, afterStale: afterStale });
        """,
        {"USER": USER},
    )
    assert out["pendingAfterBoth"] == 2, "sanity: both overlapping reload() calls issued a real pending read"
    assert "NEWER_ROW" in out["afterNewer"]["dom"]
    # the stale, later-settling OLDER call must change nothing at all
    assert out["afterStale"]["dom"] == out["afterNewer"]["dom"]
    assert "STALE_OLDER_ROW" not in out["afterStale"]["dom"]
    assert out["afterStale"]["count"] == out["afterNewer"]["count"]
    assert out["afterStale"]["chipLen"] == out["afterNewer"]["chipLen"]
    assert out["afterStale"]["fxLen"] == out["afterNewer"]["fxLen"]
    assert out["afterStale"]["pfReadState"] == out["afterNewer"]["pfReadState"]


@needs_node
def test_d1b_stale_consumer_catch_resolution_is_fully_discarded():
    """T-D1b, the .catch half. watchstore.js's own list() is architected to
    NEVER reject (every internal failure resolves gracefully to a degraded/
    error read-state answer, per the module's own "never propagate a raw
    rejection" design) — so portfolio.js's own reload().catch() cannot be
    reached through the real watchstore.js at all; it is defensive belt-and-
    braces code. This test therefore stubs `window.WatchStore.portfolio.list`
    directly (AFTER boot()'s own initial anonymous-book read, which uses the
    REAL implementation) to get full control over resolve/reject timing, and
    proves LAW 2's SAME gen guard on the .catch handler independently of LAW 1a.

    Same overlapping-reload() shape as the .then test above — the OLDER call
    REJECTS after the newer one has already succeeded — the stale rejection
    must not downgrade readState/dispatch a read-unavailable/repaint anything.

    MUTATION CHECK: remove the `if (gen !== loadGen) return;` guard from
    reload()'s .catch handler (portfolio.js) and this reds — the stale OLDER
    rejection flips portfolio.js's own readState mirror to 'error' after the
    newer call had already established 'ready'."""
    out = _run(
        """
        boot();
        await drain(8);   // let boot()'s own initial (anonymous) list() settle first

        var pending = [];
        window.WatchStore.portfolio.list = function () {
          return new Promise(function (res, rej) { pending.push({ res: res, rej: rej }); });
        };
        window.WatchStore.portfolio.readState = function () {
          return { authority: 'cloud', state: 'ready', last_good_at: null, warning: null };
        };

        document.dispatchEvent(new CustomEvent('pf-folded', {}));   // call #1 (OLDER) -> pending[0]
        await drain(3);
        document.dispatchEvent(new CustomEvent('pf-folded', {}));   // call #2 (NEWER) -> pending[1]
        await drain(3);

        // resolve the NEWER call FIRST
        pending[1].res([{ id: 'c2', ticker: 'NEWER_ROW', shares: 2, entry_price: 2,
          entry_date: null, notes: null, status: 'open', created_at: '2' }]);
        await drain(8);
        var afterNewer = { dom: node('tbl_pf').innerHTML, pfReadState: window.PF.readState() };

        // REJECT the OLDER (STALE) call LAST
        pending[0].rej(new Error('stale-older-failure'));
        await drain(8);
        var afterStale = { dom: node('tbl_pf').innerHTML, pfReadState: window.PF.readState() };

        OUT({ pendingCount: pending.length, afterNewer: afterNewer, afterStale: afterStale });
        """,
        {"USER": USER},
    )
    assert out["pendingCount"] == 2, "sanity: both overlapping reload() calls issued a real pending list() call"
    assert "NEWER_ROW" in out["afterNewer"]["dom"]
    assert out["afterNewer"]["pfReadState"]["state"] != "error"
    assert out["afterStale"]["dom"] == out["afterNewer"]["dom"]
    assert out["afterStale"]["pfReadState"] == out["afterNewer"]["pfReadState"]


@needs_node
def test_f5_stale_onauth_resolution_via_a_real_wl_auth_double_fire_is_discarded():
    """F5 (adversarial review, MINOR — a T-D1b variant driven through onAuth(),
    not reload()). T-D1b's own tests exercise reload()'s gen guard (triggered
    via the public 'pf-folded' background-refetch event); onAuth() is the
    OTHER LAW 2 call site (triggered by 'wl-auth', including the S6 double-
    fire the house test suite already documents — the SAME identity's client
    resolving after the FIRST 'wl-auth' already ran onAuth() once). Two
    overlapping onAuth() calls via a real S6-style wl-auth double-fire (the
    SAME user re-dispatched, exactly as watchstore.js's clientReady()/
    clientFailed() do) — the OLDER settles LAST, with different data — must
    change nothing.

    MUTATION CHECK: remove the `if (gen !== loadGen) return;` guard from
    onAuth()'s .then handler (portfolio.js, M8) and this reds — the stale
    OLDER call's data (STALE_OLDER_ROW) repaints over the newer call's
    answer."""
    out = _run(
        """
        boot();
        var db = { _p: [], from: function () { return {
          select: function () { return this; }, eq: function () { return this; },
          order: function () { return new Promise(function (r) { db._p.push(r); }); }
        }; } };
        function settleAt(i, result) { var r = db._p[i]; db._p[i] = null; if (r) r(result); }

        WSL._setTestSession(USER, db);
        // call #0: the FIRST wl-auth (a real sign-in) -> onAuth() -> index 0
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        settleAt(0, { data: [{ id: 'c0', ticker: 'INITIAL', shares: 1, entry_price: 1,
          entry_date: null, notes: null, status: 'open', created_at: '0' }], error: null });
        await drain(8);

        var chipHistory = [];
        document.addEventListener('pf-save', function (e) { chipHistory.push(e.detail.state); });
        var fxCallsBefore = __fxCalls.length;

        // call #1 (OLDER) via a real S6-style wl-auth RE-FIRE (same user,
        // exactly as watchstore.js's clientReady() re-dispatches once `sb`
        // resolves) -> index 1
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        // call #2 (NEWER) -- a SECOND re-fire before #1 resolves -> index 2
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        var pendingAfterBoth = db._p.filter(function (x) { return x; }).length;

        // resolve the NEWER call (index 2) FIRST
        settleAt(2, { data: [{ id: 'c2', ticker: 'NEWER_ROW', shares: 2, entry_price: 2,
          entry_date: null, notes: null, status: 'open', created_at: '2' }], error: null });
        await drain(8);
        var afterNewer = {
          dom: node('tbl_pf').innerHTML, count: window.PF.count(),
          chipLen: chipHistory.length, fxLen: __fxCalls.length,
          pfReadState: window.PF.readState()
        };

        // resolve the OLDER (STALE) call (index 1) LAST -- must change NOTHING
        settleAt(1, { data: [{ id: 'c1', ticker: 'STALE_OLDER_ROW', shares: 9, entry_price: 9,
          entry_date: null, notes: null, status: 'open', created_at: '1' }], error: null });
        await drain(8);
        var afterStale = {
          dom: node('tbl_pf').innerHTML, count: window.PF.count(),
          chipLen: chipHistory.length, fxLen: __fxCalls.length,
          pfReadState: window.PF.readState()
        };

        OUT({ pendingAfterBoth: pendingAfterBoth, afterNewer: afterNewer, afterStale: afterStale });
        """,
        {"USER": USER},
    )
    assert out["pendingAfterBoth"] == 2, "sanity: both overlapping onAuth() calls issued a real pending read"
    assert "NEWER_ROW" in out["afterNewer"]["dom"]
    assert out["afterStale"]["dom"] == out["afterNewer"]["dom"]
    assert "STALE_OLDER_ROW" not in out["afterStale"]["dom"]
    assert out["afterStale"]["count"] == out["afterNewer"]["count"]
    assert out["afterStale"]["chipLen"] == out["afterNewer"]["chipLen"]
    assert out["afterStale"]["fxLen"] == out["afterNewer"]["fxLen"]
    assert out["afterStale"]["pfReadState"] == out["afterNewer"]["pfReadState"]


@needs_node
def test_d1c_pending_upsert_at_signout_then_signin_aborts_the_continuation():
    """T-D1c (frozen spec LAW 1b, upsert). A's upsert is issued (the
    `_portfolioGuard().then()` continuation has NOT run yet — no await) when A
    signs out and B signs in. MUTATION CHECK: remove the
    `if (authEpoch !== epochAtCall) return null;` guard from portfolioUpsert()'s
    continuation (watchstore.js) and this reds — the row gets BUILT and the fake
    sb records a post-flip insert call (with `uidAtCall` still protecting the
    row's `user_id`, this is A's data landing under B's live session; with the
    `uidAtCall` substitution also reverted, it is worse — A's data attributed to
    B outright)."""
    out = _run(
        """
        boot();
        var A = { id: 'user-A' }, B = { id: 'user-B' };
        var inserted = [];
        var api = {
          select: function () { return api; }, eq: function () { return api; },
          order: function () { return Promise.resolve({ data: [], error: null }); },
          insert: function (row) { inserted.push(JSON.parse(JSON.stringify(row))); return api; },
          single: function () { return Promise.resolve({ data: { id: 'srv1' }, error: null }); }
        };
        var db = { from: function () { return api; } };

        WSL.onAuthUser(A);
        WSL._setTestSession(A, db);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: A } }));
        await drain(5);

        // A issues the write — NO await — then signs out; B signs in, before the
        // _portfolioGuard().then() continuation has had a chance to run
        var upsertP = WSL.portfolio.upsert({ ticker: 'A_WRITE', shares: 1,
          entry_price: 1, entry_date: null, status: 'open' });
        WSL.onAuthUser(null);
        WSL.onAuthUser(B);
        WSL._setTestSession(B, db);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: B } }));
        await drain(10);

        var upsertResult = await upsertP;
        OUT({
          upsertResult: upsertResult,
          insertedCount: inserted.length,
          portfolioOk: window.WatchStore.portfolioOk()
        });
        """
    )
    assert out["upsertResult"] is None
    assert out["insertedCount"] == 0, "A's stale write built a row under B's identity"
    assert out["portfolioOk"] is True


@needs_node
def test_d1c_pending_close_and_remove_at_signout_then_signin_abort_the_continuation():
    """T-D1c (frozen spec LAW 1b, "same for close/remove"). Identical shape to
    the upsert case above, for portfolioClose() and portfolioRemove().

    MUTATION CHECK: remove the epoch guard from either continuation
    (watchstore.js) and the corresponding assertion below reds — the fake sb
    records a post-flip update/delete call."""
    out = _run(
        """
        boot();
        var A = { id: 'user-A' }, B = { id: 'user-B' };
        var updated = [], removedCount = 0;
        var closeApi = {
          eq: function () { return closeApi; },
          update: function (row) { updated.push(JSON.parse(JSON.stringify(row))); return closeApi; },
          select: function () { return closeApi; },
          single: function () { return Promise.resolve({ data: { id: 'srv1' }, error: null }); }
        };
        var removeApi = {
          eq: function () { return removeApi; },
          delete: function () { return removeApi; },
          then: function (onFulfilled) {
            removedCount++;
            return Promise.resolve({ data: null, error: null }).then(onFulfilled);
          }
        };
        var dbClose = { from: function () { return closeApi; } };
        var dbRemove = { from: function () { return removeApi; } };

        // ---- close() ----
        WSL.onAuthUser(A);
        WSL._setTestSession(A, dbClose);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: A } }));
        await drain(5);
        var closeP = WSL.portfolio.close('pos-1');
        WSL.onAuthUser(null);
        WSL.onAuthUser(B);
        WSL._setTestSession(B, dbClose);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: B } }));
        await drain(10);
        var closeResult = await closeP;

        // ---- remove(), same shape, fresh identity pair ----
        var A2 = { id: 'user-A2' }, B2 = { id: 'user-B2' };
        WSL.onAuthUser(A2);
        WSL._setTestSession(A2, dbRemove);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: A2 } }));
        await drain(5);
        var removeP = WSL.portfolio.remove('pos-2');
        WSL.onAuthUser(null);
        WSL.onAuthUser(B2);
        WSL._setTestSession(B2, dbRemove);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: B2 } }));
        await drain(10);
        var removeResult = await removeP;

        OUT({
          closeResult: closeResult, updatedCount: updated.length,
          removeResult: removeResult, removedCount: removedCount
        });
        """
    )
    assert out["closeResult"] is None
    assert out["updatedCount"] == 0, "A's stale close() built an update call under B's identity"
    assert out["removeResult"] is None
    assert out["removedCount"] == 0, "A's stale remove() issued a delete call under B's identity"


# ---------------------------------------------------------------------------
# T-D2/T-D2b/T-D2c — LAW 3 (watchlist.js + watchlist_risk.js + factor_exposure.js
# + portfolio.js): risk publications carry provenance minted at the source;
# consumers reject stale/wrong-scope publications fail-closed.
# ---------------------------------------------------------------------------
LAW3_SHIM = r"""
var __store = {};
global.localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; },
  setItem: function (k, v) { __store[k] = String(v); }, removeItem: function (k) { delete __store[k]; }
};
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
var __docListeners = {};
var __writes = [];
var nodes = {};
function node(id) {
  if (!nodes[id]) {
    var n = {
      id: id, _html: '', _text: '', style: {}, className: '', _attrs: {},
      classList: { contains: function () { return false; }, toggle: function () {}, add: function () {}, remove: function () {} },
      setAttribute: function (k, v) { this._attrs[k] = v; },
      getAttribute: function (k) { return this._attrs[k] != null ? this._attrs[k] : null; },
      querySelector: function () { return null; }, querySelectorAll: function () { return []; },
      addEventListener: function () {}
    };
    Object.defineProperty(n, 'innerHTML', {
      get: function () { return this._html; },
      set: function (v) { this._html = v; __writes.push({ id: id, value: v }); }
    });
    Object.defineProperty(n, 'textContent', {
      get: function () { return this._text; },
      set: function (v) { this._text = v; __writes.push({ id: id, value: v }); }
    });
    nodes[id] = n;
  }
  return nodes[id];
}
global.document = {
  readyState: 'complete',
  documentElement: {
    _a: {},
    getAttribute: function (k) { return this._a[k] != null ? this._a[k] : null; },
    setAttribute: function (k, v) { this._a[k] = v; },
    classList: { add: function () {}, remove: function () {} }
  },
  getElementById: function (id) { return node(id); },
  querySelector: function () { return null; }, querySelectorAll: function () { return []; },
  addEventListener: function (t, f) { (__docListeners[t] = __docListeners[t] || []).push(f); },
  removeEventListener: function () {},
  dispatchEvent: function (e) { (__docListeners[e.type] || []).slice().forEach(function (f) { f(e); }); return true; },
  createElement: function () { return { style: {}, classList: { add: function () {} } }; }
};
global.window = global;
global.window.addEventListener = function () {};
global.location = { hash: '', pathname: '/watchlist.html', search: '', origin: 'https://x' };
global.MutationObserver = function () { return { observe: function () {} }; };
node('rc_tabs').querySelectorAll = function () { return []; };
window.SD = {};        // signed-in shell — renderRiskCenter()'s gate
window.RiskCore = null;   // populated for real by requiring risk_core.js

// ---- the factor artifact fetch() would serve, CONTROLLABLE (held pending) ------
var __factorFetchResolvers = [];
var MODEL = {
  factors: [{ key: 'mkt', label: 'Market', tier: 'core' }, { key: 'rates', label: 'Rates', tier: 'core' }],
  betas: {
    WLONLY_ALPHA: { mkt: 1.20, rates: -0.30, idio_vol: 0.20 },
    WLONLY_BETA:  { mkt: 0.90, rates: 0.40, idio_vol: 0.25 },
    PF_AAPL: { mkt: 1.10, rates: -0.10, idio_vol: 0.20 },
    PF_MSFT: { mkt: 1.00, rates: -0.05, idio_vol: 0.18 }
  },
  factor_cov: { mkt: { mkt: 0.0400, rates: 0.0020 }, rates: { mkt: 0.0020, rates: 0.0100 } }
};
global.fetch = function (url) {
  if (String(url).indexOf('factor_betas.json') >= 0) {
    return new Promise(function (resolve) {
      __factorFetchResolvers.push(function () {
        resolve({ ok: true, json: function () { return Promise.resolve(MODEL); } });
      });
    });
  }
  return Promise.resolve({ ok: false, json: function () { return Promise.resolve(null); } });
};
function settleFactorFetch() { var r = __factorFetchResolvers.shift(); if (r) r(); }

var __pfCount = 2;
var __setBookRiskCalls = [];
window.PF = {
  count: function () { return __pfCount; },
  render: function () {},
  setBookRisk: function (p) { __setBookRiskCalls.push(p); },
  resetBookRisk: function () {}
};
window.MB = {
  presentBooks: function () { return ['us']; }, modeledOnly: function (s) { return s; },
  marketOf: function () { return 'us'; }, refresh: function () {}, setFact: function () {},
  inActive: function () { return true; }, isModeled: function () { return true; },
  getBook: function () { return 'all'; }
};

function tick() { return new Promise(function (r) { setImmediate(r); }); }
async function drain(n) { for (var i = 0; i < (n || 8); i++) await tick(); }
function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
function OUT(o) { process.stdout.write(JSON.stringify(o)); }
"""


@needs_node
def test_d2_deferred_republish_across_the_mode_boundary_is_rejected_then_a_fresh_publish_is_accepted():
    """T-D2 (frozen spec LAW 3, republishTabs self-check + setRisk consumer
    rejection). Seed a provenance-stamped LAST_READ in Watchlists mode,
    scheduleTabRefresh() (via the real WRI.noteJson hydration entry point),
    then setMode('portfolio') on a zero-position book BEFORE the deferred
    rAF/setTimeout fires. RISK must stay the reset default. Then a FRESH
    portfolio-scope publish at the current generation must be ACCEPTED — the
    guard must not dead-end legitimate publications (non-vacuity).

    MUTATION CHECK: remove the provenance self-check from republishTabs()
    (watchlist_risk.js) — or the `payload.prov.gen === wsGen` check from
    setRisk() (watchlist.js) — and this reds: the watchlist-derived tickers
    reappear in a zero-position Portfolio's rc_body."""
    script = (
        LAW3_SHIM
        + "\nrequire(%s);\n" % json.dumps(str(RISK_CORE))
        + "var WLT = require(%s);\n" % json.dumps(str(WATCHLIST))
        + "var WRIM = require(%s);\n" % json.dumps(str(WATCHLIST_RISK))
        + """
        (async function () {
          WLT.setMode('watchlists', false);

          // seed LAST_READ via the REAL derivation path, watchlist-scoped
          var wlWeights = { universe: ['WLONLY_ALPHA', 'WLONLY_BETA'],
                             wmap: { WLONLY_ALPHA: 60000, WLONLY_BETA: 40000 },
                             mode: 'manual', prov: window.WS.prov() };
          document.dispatchEvent(new CustomEvent('fx-weights', { detail: wlWeights }));
          settleFactorFetch();   // resolves the ONE shared factor_betas.json fetch
          await drain(15);
          // setRisk() only PAINTS rc_body while mode==='portfolio' (existing law,
          // unrelated to LAW 3) — the first publish happens in watchlists mode, so
          // the seed check reads window.PF.setBookRisk's spy (called
          // UNCONDITIONALLY by publish(), regardless of mode) rather than the DOM.
          var firstPublishShares = __setBookRiskCalls.length
            ? Object.keys(__setBookRiskCalls[__setBookRiskCalls.length - 1].shares || {})
            : [];
          var domAfterFirstPublish = node('rc_body').innerHTML;

          // a hydration wave arms scheduleTabRefresh — the REAL entry point
          window.WRI.noteJson('WLONLY_ALPHA', { earnings: { next: '2026-09-01' } });

          // SYNCHRONOUSLY switch into Portfolio (zero positions) before the
          // deferred republish fires
          __pfCount = 0;
          WLT.setMode('portfolio', false);
          var domAfterSwitch = node('rc_body').innerHTML;

          // flush the deferred rAF/setTimeout(16) republishTabs()
          await sleep(60);
          await drain(10);
          var domAfterFlush = node('rc_body').innerHTML;

          // fresh portfolio-scope derivation at the CURRENT generation
          var pfWeights = { universe: ['PF_AAPL', 'PF_MSFT'],
                             wmap: { PF_AAPL: 5000, PF_MSFT: 3000 },
                             mode: 'auto', prov: window.WS.prov() };
          document.dispatchEvent(new CustomEvent('fx-weights', { detail: pfWeights }));
          await drain(15);
          var domAfterFreshPublish = node('rc_body').innerHTML;

          OUT({
            mode: window.WS.mode(),
            firstPublishShares: firstPublishShares,
            domAfterSwitch_hasWL: domAfterSwitch.indexOf('WLONLY') >= 0,
            domAfterFlush_hasWL: domAfterFlush.indexOf('WLONLY') >= 0,
            domAfterFreshPublish_hasPF: domAfterFreshPublish.indexOf('PF_AAPL') >= 0
          });
        })();
        """
    )
    out = _run_node_script(script)
    assert out["mode"] == "portfolio"
    # sanity: the first (watchlist-scope) publish genuinely reached window.PF (the
    # WIDER of the two consumers, called unconditionally regardless of mode) — a
    # broken seed would make the rest pass vacuously
    assert "WLONLY_ALPHA" in out["firstPublishShares"], out["firstPublishShares"]
    assert out["domAfterSwitch_hasWL"] is False
    assert out["domAfterFlush_hasWL"] is False
    # non-vacuity: a fresh, correctly-stamped publish in the new mode IS accepted
    assert out["domAfterFreshPublish_hasPF"] is True


@needs_node
def test_d2b_recomputebook_fetch_deferred_closure_rejects_a_boundary_crossing_publish():
    """T-D2b (frozen spec LAW 3, recomputeBook's self-check — the WIDEST replay
    window, reaching BOTH consumers). Dispatch fx-weights in Watchlists mode
    while the factor_betas.json fetch is HELD PENDING, cross the mode boundary
    (setMode('portfolio')), THEN settle the fetch: the captured weights are
    stale by the time recomputeBook's `.then()` runs. The publish must be
    aborted entirely — window.PF.setBookRisk (the WIDER of the two consumers,
    called unconditionally by publish()) must never see it. Then a fresh post-
    boundary derivation publishes and is accepted (non-vacuity).

    MUTATION CHECK: remove the self-check block from recomputeBook()'s
    `loadData().then(...)` closure (watchlist_risk.js) and this reds — the
    stale WLONLY-keyed payload reaches window.PF.setBookRisk (harmlessly
    rejected there too by LAW 3's OWN consumer-side gate in portfolio.js, but
    watchlist.js's setRisk() would also see it if window.PF were absent — the
    self-check is what stops it from EVER being built, not merely from EVER
    being painted)."""
    script = (
        LAW3_SHIM
        + "\nrequire(%s);\n" % json.dumps(str(RISK_CORE))
        + "var WLT = require(%s);\n" % json.dumps(str(WATCHLIST))
        + "var WRIM = require(%s);\n" % json.dumps(str(WATCHLIST_RISK))
        + """
        (async function () {
          WLT.setMode('watchlists', false);
          var genInWatchlists = window.WS.prov().gen;

          // dispatch fx-weights WHILE THE FETCH IS STILL PENDING — the module's
          // bootstrap init() already has ONE pending .then() on this same fetch
          // (harmless: it self-rejects via the gen:-1 fail-closed stamp)
          var staleWeights = { universe: ['WLONLY_ALPHA', 'WLONLY_BETA'],
                                wmap: { WLONLY_ALPHA: 60000, WLONLY_BETA: 40000 },
                                mode: 'manual', prov: { scope: 'watchlist', gen: genInWatchlists } };
          document.dispatchEvent(new CustomEvent('fx-weights', { detail: staleWeights }));
          await drain(5);   // let recomputeBook register its .then() on loadData()

          // cross the boundary WHILE the fetch is still pending
          __pfCount = 0;
          WLT.setMode('portfolio', false);
          var genAfterSwitch = window.WS.prov().gen;

          var setBookRiskCallsBefore = __setBookRiskCalls.length;

          // NOW settle the fetch — the captured `staleWeights` are stale
          settleFactorFetch();
          await drain(15);

          OUT({
            genInWatchlists: genInWatchlists, genAfterSwitch: genAfterSwitch,
            mode: window.WS.mode(),
            rcBody_afterStaleSettle: node('rc_body').innerHTML,
            setBookRiskCallsAfterStaleSettle: __setBookRiskCalls.length - setBookRiskCallsBefore
          });
        })();
        """
    )
    out = _run_node_script(script)
    assert out["genAfterSwitch"] != out["genInWatchlists"], (
        "sanity: the mode switch must actually bump the generation")
    assert out["mode"] == "portfolio"
    # the stale publish never even reached window.PF.setBookRisk — aborted at
    # recomputeBook's self-check, not merely rejected downstream
    assert out["setBookRiskCallsAfterStaleSettle"] == 0
    assert "WLONLY" not in out["rcBody_afterStaleSettle"]


@needs_node
def test_d2c_consumer_rejection_is_provenance_based_not_overlap_based():
    """T-D2c (frozen spec LAW 3, setBookRisk consumer rejection — exact-ticker-
    overlap does NOT excuse a stale generation; Sol: "symbol overlap alone is
    not provenance"). Also proves a stale-gen EMPTY payload is still rejected —
    payloadIsConsistentWithBook()'s "empty payload is consistent" answer is a
    boolean PREDICATE (true = "not inconsistent with the book"), never a
    controlling early-return of setBookRisk() itself, so it cannot wave a
    stale-gen empty payload through on its own; the provenance check is what
    actually rejects it, and it must be PRESENT (source order between the two
    guards is not independently load-bearing in this shape, since
    payloadIsConsistentWithBook never short-circuits the function on TRUE).

    MUTATION CHECK: remove the provenance check block from setBookRisk()
    (portfolio.js) entirely and BOTH assertions below red — the exact-ticker-
    match payload AND the stale-gen empty payload are both waved through on
    payloadIsConsistentWithBook()'s symbol-overlap logic alone."""
    out = _run(
        """
        boot();
        var db = makeDeferredDb();
        WSL._setTestSession(USER, db.client);
        document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: USER } }));
        await drain(3);
        db.settleNext({ data: [
          { id:'p1', ticker:'AAPL', shares:10, entry_price:100, entry_date:null, notes:null, status:'open', created_at:'1' },
          { id:'p2', ticker:'MSFT', shares:5,  entry_price:200, entry_date:null, notes:null, status:'open', created_at:'2' }
        ], error:null });
        await drain(10);
        var writesBefore = __writes.length;

        // EXACT ticker match with the book, but a STALE gen (the SHIM's
        // window.WS.prov() answers gen 0)
        window.PF.setBookRisk({ shares: { AAPL: 0.6, MSFT: 0.4 }, covered: { AAPL: 1, MSFT: 1 },
                                 bets: null, modeledN: 2, regime: '', concHTML: '<p>STALE_GEN_MARKER</p>',
                                 rcTabs: null, labHTML: '', prov: { scope: 'portfolio', gen: 1 } });
        await drain(4);
        var afterStaleGen = { repainted: __writes.length > writesBefore, tbl: node('tbl_pf').innerHTML };

        // the SAME payload, current gen -> accepted
        var writesBefore2 = __writes.length;
        window.PF.setBookRisk({ shares: { AAPL: 0.6, MSFT: 0.4 }, covered: { AAPL: 1, MSFT: 1 },
                                 bets: null, modeledN: 2, regime: '', concHTML: '<p>VALID_GEN_MARKER</p>',
                                 rcTabs: null, labHTML: '', prov: { scope: 'portfolio', gen: 0 } });
        await drain(4);
        var afterValidGen = { repainted: __writes.length > writesBefore2 };

        // a stale-gen EMPTY payload -- the prov check must run BEFORE the
        // empty-payload early-accept
        var writesBefore3 = __writes.length;
        window.PF.setBookRisk({ shares: {}, covered: {}, bets: null, modeledN: 0,
                                 regime: '', concHTML: '', rcTabs: null, labHTML: '',
                                 prov: { scope: 'portfolio', gen: 1 } });
        await drain(4);
        var afterStaleEmpty = { repainted: __writes.length > writesBefore3 };

        OUT({ afterStaleGen: afterStaleGen, afterValidGen: afterValidGen, afterStaleEmpty: afterStaleEmpty });
        """,
        {"USER": USER},
    )
    assert out["afterStaleGen"]["repainted"] is False, (
        "an exact-ticker-match payload with a stale gen was accepted — overlap is not provenance")
    assert out["afterValidGen"]["repainted"] is True
    assert out["afterStaleEmpty"]["repainted"] is False, (
        "a stale-gen EMPTY payload was waved through the empty-payload early-accept")


@needs_node
def test_f2_wl_auth_boundary_invalidates_the_retained_fx_latch_before_a_post_boundary_rerender():
    """F2 (adversarial review, MAJOR — reviewer's executed proof, probe_regen.js).
    Two independent leak mechanisms across the SAME wl-auth identity boundary,
    each closed by a DIFFERENT half of the fix:

    LEG 1 (closed by the NEW `window.FX.setAutoWeights({})` clear): LAW 3's mint
    reads window.WS.prov() LIVE at factor_exposure.js's render() time, and
    render() reads AUTO_W LIVE too — so a POST-boundary RE-RENDER
    (window.FX.refresh(), reachable via the lang-btn click listener at
    factor_exposure.js's bottom) over a PRE-boundary AUTO_W latch mints the
    CURRENT (post-boundary) gen and is ACCEPTED: provenance binds the MOMENT of
    derivation, not the DATA. AUTO_W (portfolio.js's dollar-weighted push) is a
    retained latch nothing invalidated at the wl-auth boundary before this fix.
    This leg is INSENSITIVE to `wsGen++` alone — the mint always reads whatever
    gen is CURRENT at render time, bumped or not, so a plain re-render never
    carries a stale captured gen to compare against.

    LEG 2 (closed by `wsGen++`): a publish CAPTURED (its provenance read) BEFORE
    the boundary, delivered to setRisk() AFTER it — modelling any in-flight
    publish whose closure grabbed `window.WS.prov()` pre-boundary (a deferred
    republishTabs(), a recomputeBook() mid-fetch, etc. — LAW 3's OTHER self-
    checks already pin those specific channels; this leg isolates the RAW
    consumer-side gen comparison itself). setRisk()'s consumer check compares
    the CAPTURED (pre-boundary) gen against the CURRENT gen — if the boundary
    never bumped wsGen, the captured gen still equals the current one and the
    stale publish is wrongly accepted. This leg calls `setRisk()` directly,
    synchronously, right after the flip — before the wl-auth listener's OWN
    `window.FX.setAutoWeights({})` clear can trigger its own async recompute
    and null LAST_READ as an (unrelated) side effect, which would otherwise
    mask whether `wsGen++` itself did anything. This leg is INSENSITIVE to the
    FX clear alone — it never touches AUTO_W or LAST_READ.

    Both legs drive the REAL risk_core.js + watchlist.js + factor_exposure.js +
    watchlist_risk.js chain.

    MUTATION CHECK: remove `wsGen++` from the wl-auth identity-change listener
    (watchlist.js) and LEG 2 reds (the captured pre-boundary gen still matches
    the unbumped current one, so the stale publish is accepted). Remove the NEW
    `window.FX.setAutoWeights({})` clear (leaving `wsGen++` in place) and LEG 1
    reds (the retained AUTO_W re-mints under the new gen on the very next re-
    render, exactly as the reviewer's probe demonstrated) — either mutation
    reds this test."""
    script = (
        LAW3_SHIM
        + "\nrequire(%s);\n" % json.dumps(str(RISK_CORE))
        + "var WLT = require(%s);\n" % json.dumps(str(WATCHLIST))
        + "require(%s);\n" % json.dumps(str(FACTOR_EXPOSURE))
        + "var WRIM = require(%s);\n" % json.dumps(str(WATCHLIST_RISK))
        + """
        (async function () {
          // ---- LEG 1: plain re-render over a retained AUTO_W latch ----------
          document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: { id: 'user-A' } } }));
          WLT.setMode('portfolio', false);
          window.FX.setAutoWeights({ PF_AAPL: 5000, PF_MSFT: 3000 });
          await drain(6); settleFactorFetch(); settleFactorFetch(); await drain(25);
          var rcA = node('rc_body').innerHTML;

          // identity flip to user B -- the wl-auth boundary. Nothing re-pushes
          // a book for B: AUTO_W still holds user A's dollar weights.
          document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: { id: 'user-B' } } }));
          node('rc_body')._html = '';
          __setBookRiskCalls.length = 0;

          // a plain re-render -- exactly what the lang-btn click listener does,
          // NOT a fresh FX.setAutoWeights() push
          window.FX.refresh();
          await drain(6); settleFactorFetch(); settleFactorFetch(); await drain(25);

          var lastPublish = __setBookRiskCalls[__setBookRiskCalls.length - 1] || {};
          var leg1PublishedNames = Object.keys(lastPublish.shares || {});
          var leg1_rcBody_hasPFAAPL = node('rc_body').innerHTML.indexOf('PF_AAPL') >= 0;

          // ---- LEG 2: a DEFERRED republish scheduled before, fired after ----
          // fresh identities (C/D) so this leg starts from a clean LAST_READ,
          // independent of leg 1's history.
          document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: { id: 'user-C' } } }));
          window.FX.setAutoWeights({ PF_AAPL: 5000, PF_MSFT: 3000 });
          await drain(6); settleFactorFetch(); settleFactorFetch(); await drain(25);
          // C's genuine, CURRENT provenance -- captured BEFORE the boundary,
          // exactly like a real in-flight publish's closure would capture it.
          var staleProv = window.WS.prov();

          // identity flip to D -- the boundary. `staleProv` above must now be
          // stale for D's session. Note: the wl-auth listener's OWN
          // `window.FX.setAutoWeights({})` clear (unmutated by the M15 probe
          // below) ALSO triggers an async recompute that nulls LAST_READ on its
          // own -- driving this leg through a genuinely SCHEDULED
          // republishTabs() would therefore be blind to the M15 mutation
          // specifically (the FX-clear's side effect masks it). Calling
          // setRisk() directly, synchronously, right after the flip -- before
          // that async recompute's microtask even runs -- isolates EXACTLY
          // what `wsGen++` protects: a publish captured before the boundary,
          // arriving after it.
          document.dispatchEvent(new CustomEvent('wl-auth', { detail: { user: { id: 'user-D' } } }));
          node('rc_body')._html = '';
          window.WS.setRisk({
            shares: { PF_AAPL: 0.6 }, concHTML: '<p>PF_AAPL carries the risk</p>',
            rcTabs: { conc: '<p>PF_AAPL carries the risk</p>' }, labHTML: '',
            seamItems: null, coverage: null, headline: null,
            prov: staleProv
          });
          var leg2_rcBody_hasPFAAPL = node('rc_body').innerHTML.indexOf('PF_AAPL') >= 0;

          OUT({
            rcA_hasPFAAPL: rcA.indexOf('PF_AAPL') >= 0,
            leg1PublishedNames: leg1PublishedNames,
            leg1_rcBody_hasPFAAPL: leg1_rcBody_hasPFAAPL,
            leg2_rcBody_hasPFAAPL: leg2_rcBody_hasPFAAPL
          });
        })();
        """
    )
    out = _run_node_script(script)
    assert out["rcA_hasPFAAPL"] is True, "sanity: A's book genuinely painted before the flip"
    assert out["leg1PublishedNames"] == [], (
        "LEG 1: A's retained AUTO_W book re-published under B's generation via a plain "
        "re-render: %r" % out["leg1PublishedNames"])
    assert out["leg1_rcBody_hasPFAAPL"] is False, (
        "LEG 1: A's book painted into B's Risk Center via a post-boundary re-render")
    assert out["leg2_rcBody_hasPFAAPL"] is False, (
        "LEG 2: C's pre-boundary-captured provenance was accepted under D's session")


@needs_node
def test_f1_legitimate_portfolio_push_reaches_rc_body_through_the_real_producer_chain():
    """F1 (adversarial review, MAJOR — the PRODUCER half of LAW 3 had ZERO
    coverage). Every other LAW 3 test in this suite either hand-mints
    `prov: window.WS.prov()` in a stub FX (T-D2/T-D2b) or manipulates setRisk/
    setBookRisk directly (T-D2c) — none of them drive the REAL mint site,
    factor_exposure.js's CUR assignment, end to end. A silent regression there
    (the mint stops stamping prov at all, or watchlist_risk.js stops carrying it
    through) leaves every OTHER LAW 3 test green — they all supply their own
    prov by hand — while production breaks completely: the failure mode is a
    PERMANENTLY EMPTY Risk Center, because setRisk()/setBookRisk() fail-closed-
    reject every real payload the same way they correctly reject a forged one.

    setMode('portfolio') -> a real FX.setAutoWeights() push -> settle the real
    factor_betas.json fetch -> the derivation must reach both consumers and
    paint rc_body with a real portfolio ticker. A SECOND leg then clears
    rc_body by hand and drives a REAL deferred republish (the hydration-wave
    path, scheduleTabRefresh/republishTabs) — that path reads FROM
    watchlist_risk.js's own `LAST_READ.prov`, a SEPARATE carry from the
    `out.prov` stamp the immediate publish above already proves, so it is the
    only leg that can catch a regression in that specific carry.

    MUTATION CHECK (all four independently red this test — see EVIDENCE for the
    paste of each): X5 (factor_exposure.js's BOTH CUR-assignment prov stamps
    removed) and X6 (currentWeights() stops forwarding CUR.prov) both red the
    FIRST leg (rc_body never paints at all). M16 (the single normal-resolution
    prov stamp removed) also reds the first leg. M17 (watchlist_risk.js's
    LAST_READ stops carrying weights.prov) leaves the FIRST leg green — `out.
    prov` is a separate stamp — but reds the SECOND leg: the deferred republish
    can no longer prove its own provenance to itself and silently no-ops."""
    script = (
        LAW3_SHIM
        + "\nrequire(%s);\n" % json.dumps(str(RISK_CORE))
        + "var WLT = require(%s);\n" % json.dumps(str(WATCHLIST))
        + "require(%s);\n" % json.dumps(str(FACTOR_EXPOSURE))
        + "var WRIM = require(%s);\n" % json.dumps(str(WATCHLIST_RISK))
        + """
        (async function () {
          WLT.setMode('portfolio', false);
          window.FX.setAutoWeights({ PF_AAPL: 5000, PF_MSFT: 3000 });
          await drain(6); settleFactorFetch(); settleFactorFetch(); await drain(25);
          var rcBody = node('rc_body').innerHTML;
          var setBookRiskNames = Object.keys((__setBookRiskCalls[__setBookRiskCalls.length - 1] || {}).shares || {});

          // LEG 2: clear rc_body by hand, then drive a REAL deferred republish
          // (the hydration-wave path) at the SAME generation -- it must
          // re-populate rc_body by successfully checking its OWN LAST_READ.prov
          // against the current gen, never by re-deriving anything.
          node('rc_body')._html = '';
          window.WRI.noteJson('PF_AAPL', { earnings: { next: '2026-09-01' } });
          await sleep(60);
          await drain(15);
          var rcBodyAfterRepublish = node('rc_body').innerHTML;

          OUT({ rcBody: rcBody, setBookRiskNames: setBookRiskNames, rcBodyAfterRepublish: rcBodyAfterRepublish });
        })();
        """
    )
    out = _run_node_script(script)
    assert "PF_AAPL" in out["rcBody"] or "PF_MSFT" in out["rcBody"], (
        "a real portfolio push through the real producer chain never painted rc_body: %r"
        % out["rcBody"][:200])
    assert "PF_AAPL" in out["setBookRiskNames"], out["setBookRiskNames"]
    assert "PF_AAPL" in out["rcBodyAfterRepublish"] or "PF_MSFT" in out["rcBodyAfterRepublish"], (
        "a real deferred republish at the SAME generation never re-populated rc_body: %r"
        % out["rcBodyAfterRepublish"][:200])


# ---------------------------------------------------------------------------
# T-D3a/T-D3b — LAW 4 (watchstore.js): client resolution always reaches a
# terminal state — no getSupabaseClient factory, and a synchronous throw from
# calling it, both route through the SAME terminal path a rejected/timed-out
# client uses.
# ---------------------------------------------------------------------------
@needs_node
def test_d3a_missing_client_factory_reaches_a_terminal_state_not_stuck_loading():
    """T-D3a (frozen spec LAW 4a). window.getSupabaseClient is entirely absent.
    Before this fix the `if (!getClient)` branch returned WITHOUT ever setting
    sbInitFailed, leaving `_isCloudLoading()` (not `_isClientUnavailable()`)
    true for the rest of the session — portfolioList() answered 'loading'
    forever, and no second 'wl-auth' ever rescued a listener holding that
    transient answer.

    MUTATION CHECK: revert the `if (!getClient) { ... }` branch to the old bare
    `setPill('offline'); warnOnce(...); return;` (dropping the clientFailed()
    call) and this reds — readState stays 'loading', list() never terminally
    resolves, and only ONE 'wl-auth' ever fires."""
    out = _run(
        """
        boot();
        delete window.getSupabaseClient;
        var wlAuthCount = 0;
        document.addEventListener('wl-auth', function () { wlAuthCount++; });
        WSL.onAuthUser(USER);
        await drain(10);

        var readState = WSL.portfolio.readState();
        var listResult = await WSL.portfolio.list();
        await drain(5);

        OUT({ readState: readState, listResult: listResult, wlAuthCount: wlAuthCount });
        """,
        {"USER": USER},
    )
    assert out["readState"]["state"] in ("degraded", "error")
    assert out["readState"]["authority"] == "cloud"
    assert out["readState"]["warning"] == "client-unavailable"
    assert out["listResult"] is None   # no last-good -> honest error, never []
    # the FIRST 'wl-auth' fires synchronously inside onAuthUser's signed-in
    # branch; the terminal path must re-fire a SECOND one so every listener
    # holding that transient answer resolves
    assert out["wlAuthCount"] >= 2


@needs_node
def test_d3b_synchronous_getclient_throw_reaches_the_same_terminal_state_no_uncaught_exception():
    """T-D3b (frozen spec LAW 4b). getSupabaseClient() throws SYNCHRONOUSLY —
    before this fix that escaped onAuthUser() entirely (past the Promise.race
    .catch, which can only see a REJECTED promise, never a synchronous throw)
    and landed uncaught in the caller (window.MDXAuth.onChange's callback has
    no try/catch of its own).

    MUTATION CHECK: replace `Promise.resolve(getClient())` with a bare
    `getClient()` call (dropping the try/catch, watchstore.js) and this reds —
    the exception escapes onAuthUser() synchronously instead of being caught
    and routed through clientFailed()."""
    out = _run(
        """
        boot();
        window.getSupabaseClient = function () { throw new TypeError('supabase factory exploded'); };
        var escaped = null;
        try { WSL.onAuthUser(USER); } catch (e) { escaped = String(e && e.name); }
        await drain(10);

        var readState = WSL.portfolio.readState();
        var listResult = await WSL.portfolio.list();
        await drain(5);

        OUT({ escaped: escaped, readState: readState, listResult: listResult });
        """,
        {"USER": USER},
    )
    assert out["escaped"] is None, "the synchronous throw escaped onAuthUser() uncaught"
    assert out["readState"]["state"] in ("degraded", "error")
    assert out["readState"]["warning"] == "client-unavailable"
    assert out["listResult"] is None
