"""tests/test_watchlist_books_js.py — the two localStorage stores behind the books UI.

Covers the cross-tab / re-login invariants that gate the Portfolio Command Center:

  1. `mergeInto` (templates/watchlist.js) stays IDEMPOTENT. A merge that changes
     nothing must not bump `updated` and must not re-persist — otherwise two open tabs
     ping-pong writes forever, each tab's write retriggering the other's storage
     handler (the watchlist "spasm": constant re-render + re-fetch). This invariant was
     described in a code comment but never had a test; it does now.

  2. The anonymous local portfolio book (templates/watchstore.js) does real CRUD, obeys
     the same no-op-write discipline, and folds into the account EXACTLY ONCE on
     sign-in — with the marker written only on SUCCESS, so a failed fold is retried
     next session instead of silently dropping the visitor's book.

Both modules are browser IIFEs; we node-shell them behind minimal window/document/
localStorage stubs (document.readyState = 'loading' so their DOM init never runs and
only the pure store logic is exercised).
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
WATCHLIST = ROOT / "templates" / "watchlist.js"
WATCHSTORE = ROOT / "templates" / "watchstore.js"

# Minimal browser surface. readyState 'loading' means each module's init() waits for a
# DOMContentLoaded that never fires — the public store seams are assigned before that,
# so we get the logic without any DOM.
SHIM = """
var __sets = [];
var __store = {};
global.localStorage = {
  getItem: function (k) {
    return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null;
  },
  setItem: function (k, v) { __sets.push(k); __store[k] = String(v); },
  removeItem: function (k) { delete __store[k]; }
};
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
global.document = {
  readyState: 'loading',
  documentElement: {
    getAttribute: function () { return 'en'; },
    classList: { add: function () {}, remove: function () {} }
  },
  getElementById: function () { return null; },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  addEventListener: function () {},
  removeEventListener: function () {},
  dispatchEvent: function () { return true; },
  createElement: function () { return { style: {}, classList: { add: function () {} } }; }
};
global.window = global;
global.window.addEventListener = function () {};
global.location = { hash: '', pathname: '/watchlist.html', search: '', origin: 'https://x' };
function OUT(o) { process.stdout.write(JSON.stringify(o)); }
// `persist` is debounced 200ms, so the only honest way to count writes is to let the
// timer flush first. Comparing `updated` strings does NOT work: two merges in the same
// millisecond produce an identical ISO stamp, which makes a naive equality check pass
// whether or not the guard is doing anything.
function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
"""


def _run(js_body: str, extra: dict | None = None) -> dict:
    globs = "\n".join("var %s = %s;" % (k, json.dumps(v)) for k, v in (extra or {}).items())
    script = SHIM + "\n" + globs + "\n" + textwrap.dedent(js_body)
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


def _wl(js_body: str, extra: dict | None = None) -> dict:
    return _run("require(%s);\n%s" % (json.dumps(str(WATCHLIST)), js_body), extra)


def _ws(js_body: str, extra: dict | None = None) -> dict:
    return _run("var WS = require(%s);\n%s" % (json.dumps(str(WATCHSTORE)), js_body), extra)


# ===========================================================================
# 1. mergeInto idempotence — the #storage ping-pong regression
# ===========================================================================
PEER = {
    "v": 1,
    "updated": "2026-08-01T00:00:00.000Z",
    "items": [{"t": "AAPL", "added": "2026-07-01T00:00:00.000Z", "note": ""},
              {"t": "NVDA", "added": "2026-07-02T00:00:00.000Z", "note": ""}],
    "order": ["AAPL", "NVDA"],
    "settings": {"sort": "order", "buySoonOnly": False},
}


@needs_node
def test_merge_is_idempotent_and_does_not_republish():
    """First merge adopts the peer doc (a real change -> exactly one write). The SECOND
    merge of the identical doc must be a total no-op — no additional write, so no storage
    event goes back to the peer tab and the ping-pong cannot sustain."""
    out = _wl(
        """
        window.WL.merge(PEER);
        wait(400).then(function () {
          var w1 = __sets.length;               // the first merge's persist has flushed
          var n2 = window.WL.merge(PEER);       // identical doc -> must do nothing
          return wait(400).then(function () {
            OUT({w1: w1, w2: __sets.length, secondMergeAdded: n2,
                 items: window.WL.getBlob().items.map(function (i) { return i.t; }).sort()});
          });
        });
        """,
        {"PEER": PEER},
    )
    assert out["items"] == ["AAPL", "NVDA"]
    assert out["secondMergeAdded"] == 0
    assert out["w1"] == 1, "the first merge should persist exactly once"
    assert out["w2"] == out["w1"], (
        "a no-op merge re-persisted — this is the #storage ping-pong regression"
    )


@needs_node
def test_merge_of_a_genuinely_different_peer_does_persist():
    """The guard must not be so eager that a REAL change is dropped — otherwise cross-tab
    sync silently stops working and the idempotence test above would still be green."""
    out = _wl(
        """
        window.WL.merge(PEER);
        wait(400).then(function () {
          var w1 = __sets.length;
          var added = window.WL.merge(OTHER);
          return wait(400).then(function () {
            OUT({added: added, w1: w1, w2: __sets.length,
                 items: window.WL.getBlob().items.map(function (i) { return i.t; }).sort()});
          });
        });
        """,
        {"PEER": PEER, "OTHER": {
            "v": 1, "updated": "2026-08-02T00:00:00.000Z",
            "items": [{"t": "MSFT", "added": "2026-07-03T00:00:00.000Z", "note": ""}],
            "order": ["MSFT"], "settings": {"sort": "order", "buySoonOnly": False}}},
    )
    assert out["added"] == 1
    assert out["w2"] > out["w1"], "a genuine peer change must still persist"
    assert out["items"] == ["AAPL", "MSFT", "NVDA"]


@needs_node
def test_merge_keeps_earliest_added_and_is_still_idempotent():
    out = _wl(
        """
        window.WL.merge(PEER);
        window.WL.merge(EARLIER);
        wait(400).then(function () {
          var w1 = __sets.length;
          window.WL.merge(EARLIER);            // replay -> no-op
          return wait(400).then(function () {
            var aapl = window.WL.getBlob().items.filter(
              function (i) { return i.t === 'AAPL'; })[0];
            OUT({added: aapl.added, w1: w1, w2: __sets.length});
          });
        });
        """,
        {"PEER": PEER, "EARLIER": {
            "v": 1, "updated": "2026-08-03T00:00:00.000Z",
            "items": [{"t": "AAPL", "added": "2026-01-01T00:00:00.000Z", "note": ""}],
            "order": ["AAPL"], "settings": {"sort": "order", "buySoonOnly": False}}},
    )
    assert out["added"] == "2026-01-01T00:00:00.000Z"   # earliest wins
    assert out["w2"] == out["w1"]                       # replaying it writes nothing


# ===========================================================================
# 2. the anonymous local portfolio book
# ===========================================================================
@needs_node
def test_local_book_is_active_when_signed_out():
    out = _ws("OUT({isLocal: WS.portfolio.isLocal()});")
    assert out["isLocal"] is True


@needs_node
def test_local_crud_round_trip():
    out = _ws(
        """
        WS.portfolio.upsert({ticker:'AAPL', shares:10, entry_price:200,
                             entry_date:'2026-01-01', status:'open'})
          .then(function (a) {
            return WS.portfolio.upsert({ticker:'0700.HK', shares:100, entry_price:400,
                                        entry_date:'2026-02-01', status:'open'})
              .then(function () { return a; });
          })
          .then(function (a) {
            // edit the first row in place
            return WS.portfolio.upsert({id:a.id, ticker:'AAPL', shares:25, entry_price:200,
                                        entry_date:'2026-01-01', status:'open'})
              .then(function () { return a; });
          })
          .then(function (a) {
            return WS.portfolio.list().then(function (rows) {
              return WS.portfolio.remove(a.id).then(function () {
                return WS.portfolio.list().then(function (after) {
                  OUT({
                    afterEdit: rows.map(function (r) { return r.ticker + ':' + r.shares; }).sort(),
                    idPrefixed: /^loc-/.test(a.id),
                    afterRemove: after.map(function (r) { return r.ticker; }),
                    numeric: typeof rows[0].shares === 'number'
                  });
                });
              });
            });
          });
        """
    )
    assert out["idPrefixed"] is True
    assert out["afterEdit"] == ["0700.HK:100", "AAPL:25"]   # edit replaced, not appended
    assert out["afterRemove"] == ["0700.HK"]
    assert out["numeric"] is True


@needs_node
def test_local_write_is_a_no_op_when_nothing_changed():
    """Same discipline as the watchlist blob: rewriting identical rows must not touch
    localStorage, so a re-render can never start a storage-event cascade."""
    out = _ws(
        """
        var rows = [{id:'loc-1', ticker:'AAPL', shares:10, entry_price:200,
                     entry_date:'2026-01-01', notes:null, status:'open'}];
        WS.pfWrite(rows);
        var afterFirst = __sets.length;
        WS.pfWrite(rows);
        var afterSecond = __sets.length;
        WS.pfWrite([{id:'loc-1', ticker:'AAPL', shares:11, entry_price:200,
                     entry_date:'2026-01-01', notes:null, status:'open'}]);
        OUT({first: afterFirst, noOpWrites: afterSecond - afterFirst,
             realWrites: __sets.length - afterSecond});
        """
    )
    assert out["first"] == 1
    assert out["noOpWrites"] == 0     # identical content -> no write
    assert out["realWrites"] == 1     # a genuine change still persists


# ---------------------------------------------------------------------------
# the one-shot fold
# ---------------------------------------------------------------------------
LOCAL_TWO = [
    {"id": "loc-1", "ticker": "AAPL", "shares": 10, "entry_price": 200,
     "entry_date": "2026-01-01", "notes": None, "status": "open"},
    {"id": "loc-2", "ticker": "0700.HK", "shares": 100, "entry_price": 400,
     "entry_date": "2026-02-01", "notes": None, "status": "open"},
]

# a Supabase-shaped stub: .from().select().eq() is thenable, .from().insert() is thenable
FAKE_SB = """
function fakeSb(selectRes, insertRes, seen) {
  return {
    from: function () {
      return {
        select: function () { return { eq: function () { return Promise.resolve(selectRes); } }; },
        insert: function (rows) { seen.inserted = rows; return Promise.resolve(insertRes); }
      };
    }
  };
}
"""


@needs_node
def test_fold_inserts_once_then_clears_and_marks():
    out = _ws(
        FAKE_SB + """
        WS.pfWrite(LOCAL);
        var seen = {};
        WS._setTestSession({id: 'u1'}, fakeSb({data: []}, {error: null}, seen));
        WS.foldLocalPortfolio().then(function () {
          var marked = localStorage.getItem('mdash.watchstore.pf_folded.v1');
          var left = WS.pfRead().rows.length;
          // a second sign-in must NOT re-insert
          seen.inserted = null;
          return WS.foldLocalPortfolio().then(function () {
            OUT({marked: marked, leftAfterFold: left,
                 insertedTickers: (seen.insertedFirst || []).length,
                 secondPassInserted: seen.inserted});
          });
        });
        """.replace("seen.insertedFirst", "seen.inserted"),
        {"LOCAL": LOCAL_TWO},
    )
    assert out["marked"] == "1"
    assert out["leftAfterFold"] == 0          # local rows cleared after a successful fold
    assert out["secondPassInserted"] is None  # marker short-circuits the second fold


@needs_node
def test_fold_dedupes_against_rows_the_account_already_has():
    out = _ws(
        FAKE_SB + """
        WS.pfWrite(LOCAL);
        var seen = {};
        // the account already holds the AAPL row (same ticker + entry_date + shares)
        WS._setTestSession({id: 'u1'}, fakeSb(
          {data: [{ticker: 'AAPL', entry_date: '2026-01-01', shares: 10}]},
          {error: null}, seen));
        WS.foldLocalPortfolio().then(function () {
          OUT({inserted: (seen.inserted || []).map(function (r) { return r.ticker; })});
        });
        """,
        {"LOCAL": LOCAL_TWO},
    )
    assert out["inserted"] == ["0700.HK"]     # AAPL is not duplicated


@needs_node
def test_fold_does_not_mark_on_error_so_it_retries_next_session():
    """The trap this guards: marking the one-shot as done when the insert FAILED would
    silently discard the visitor's whole book — they sign in, the rows never arrive, and
    the marker stops it ever being tried again."""
    out = _ws(
        FAKE_SB + """
        WS.pfWrite(LOCAL);
        var seen = {};
        WS._setTestSession({id: 'u1'},
          fakeSb({data: []}, {error: {message: 'rls denied'}}, seen));
        WS.foldLocalPortfolio().then(function () {
          OUT({marked: localStorage.getItem('mdash.watchstore.pf_folded.v1'),
               rowsKept: WS.pfRead().rows.map(function (r) { return r.ticker; }).sort()});
        });
        """,
        {"LOCAL": LOCAL_TWO},
    )
    assert out["marked"] is None                       # NOT marked
    assert out["rowsKept"] == ["0700.HK", "AAPL"]      # nothing lost


@needs_node
def test_fold_does_not_consume_the_one_shot_on_an_empty_local_book():
    """Signing in on a fresh device (nothing local yet) must not burn the one-shot —
    otherwise a book built later never folds. Same trap the watchlist fold documents."""
    out = _ws(
        FAKE_SB + """
        var seen = {};
        WS._setTestSession({id: 'u1'}, fakeSb({data: []}, {error: null}, seen));
        WS.foldLocalPortfolio().then(function () {
          OUT({marked: localStorage.getItem('mdash.watchstore.pf_folded.v1')});
        });
        """
    )
    assert out["marked"] is None


@needs_node
def test_fold_plan_is_pure_and_idempotent():
    out = _ws(
        """
        var plan1 = WS.pfFoldPlan(LOCAL, []);
        var plan2 = WS.pfFoldPlan(LOCAL, plan1);       // after inserting, nothing is left
        var dupes = WS.pfFoldPlan(LOCAL.concat(LOCAL), []);
        OUT({first: plan1.map(function (r) { return r.ticker; }),
             second: plan2.map(function (r) { return r.ticker; }),
             dupes: dupes.map(function (r) { return r.ticker; })});
        """,
        {"LOCAL": LOCAL_TWO},
    )
    assert out["first"] == ["AAPL", "0700.HK"]
    assert out["second"] == []                          # replaying plans nothing
    assert out["dupes"] == ["AAPL", "0700.HK"]          # a duplicated local batch inserts once


@needs_node
def test_fold_key_distinguishes_rows_that_differ_in_shares_or_date():
    out = _ws(
        """
        OUT({
          same: WS.pfKey({ticker:'AAPL', entry_date:'2026-01-01', shares:10}) ===
                WS.pfKey({ticker:'aapl', entry_date:'2026-01-01', shares:'10'}),
          diffShares: WS.pfKey({ticker:'AAPL', entry_date:'2026-01-01', shares:10}) !==
                      WS.pfKey({ticker:'AAPL', entry_date:'2026-01-01', shares:11}),
          diffDate: WS.pfKey({ticker:'AAPL', entry_date:'2026-01-01', shares:10}) !==
                    WS.pfKey({ticker:'AAPL', entry_date:'2026-03-01', shares:10})
        });
        """
    )
    assert out["same"] is True          # case + numeric-string normalised
    assert out["diffShares"] is True
    assert out["diffDate"] is True
