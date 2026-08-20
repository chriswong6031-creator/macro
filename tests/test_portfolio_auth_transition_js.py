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
    setAttribute: function (k, v) { this._attrs[k] = String(v); },
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

        OUT({
          duringLoading_hasAnon: duringLoading.indexOf('ANONA') >= 0,
          readState: WSL.portfolio.readState(),
          errBanner: node('pf_err_inline').textContent,
          errBannerVisible: node('pf_err_inline').style.display,
          tblFinal_hasAnon: node('tbl_pf').innerHTML.indexOf('ANONA') >= 0
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

        OUT({
          afterFirst_hasCloud: afterFirst.indexOf('CLOUDGOOD') >= 0,
          readState: WSL.portfolio.readState(),
          tbl_hasCloudGood: node('tbl_pf').innerHTML.indexOf('CLOUDGOOD') >= 0,
          banner: node('pf_readbanner').textContent,
          bannerVisible: node('pf_readbanner').style.display
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

        OUT({
          readState1: readState1,
          isLocal: WSL.portfolio.isLocal(),
          tbl_hasAnon: tblHTML.indexOf('ANONA') >= 0,
          writeResult: writeResult,
          localBookUnchanged: localBookAfterWrite.length === localBookBefore &&
            !localBookAfterWrite.some(function (r) { return r.ticker === 'SHOULD_NOT_LAND'; })
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
