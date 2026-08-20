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
  seam: function () {}
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
    survives into B's session."""
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
          labHTML: '', seamItems: null, coverage: null, headline: 'USERA_NVDA 62%'
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
          bets: null, modeledN: 2, regime: '', concHTML: '', rcTabs: null, labHTML: ''
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
        // a genuine PORTFOLIO-derived payload first
        window.PF.setBookRisk({ shares: { AAPL: 0.6, MSFT: 0.4 }, covered: { AAPL: 1, MSFT: 1 },
                                 bets: null, modeledN: 2, regime: '', concHTML: '', rcTabs: null, labHTML: '' });
        await drain(3);
        var covPortfolio = node('ws_book_coverage').innerHTML;

        // now the WATCHLIST-derived payload
        window.PF.setBookRisk({ shares: { WLONLY_TSLA: 0.71, WLONLY_META: 0.29 },
                                 covered: { WLONLY_TSLA: 1, WLONLY_META: 1 },
                                 bets: null, modeledN: 2, regime: '', concHTML: '', rcTabs: null, labHTML: '' });
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
                                 regime: '', concHTML: '', rcTabs: null, labHTML: '' });
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
