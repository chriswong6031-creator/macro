"""tests/test_watchlist_workspace_js.py — the W2 Portfolio Intelligence workspace.

W2 rebuilt `watchlist.html` as a two-mode workspace over the W1a store seam. The store
half is pinned by tests/test_watchstore_multilist_js.py and is deliberately untouched
here. What this file pins is the layer W2 added, and specifically the places where an
honest read and a plausible-looking lie are one keystroke apart:

  1. The bulk-entry parser. It is the anonymous funnel's front door: a line it silently
     drops is a position the visitor believes we read.
  2. The weighting model. "Equal" must ignore typed sizes; every other mode must use
     them and DISCLOSE when it had to fall back.
  3. The engine-state -> plain-word stage map. It may only ever DE-ESCALATE: a state
     whose honest reading is "still falling" can never become an up-word, and an
     unknown state must become "Not covered", never a guess.
  4. Delta-since-visit. The header count and the column ink come from ONE computation,
     so the page cannot say "4 changed" over three marked rows.
  5. The visibilitychange re-pull, hardened (see below).
  6. The OUTER catch in `_foldLocalIntoCloud` (reviewer residual from PR #5461).

Same harness as its two sibling suites: these modules are browser IIFEs, node-shelled
behind minimal window/document/localStorage stubs with readyState 'loading' so init()
never runs and only the pure logic is exercised.
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
MARKET_BOOKS = ROOT / "templates" / "market_books.js"

SHIM = """
var __store = {};
global.localStorage = {
  getItem: function (k) {
    return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null;
  },
  setItem: function (k, v) { __store[k] = String(v); },
  removeItem: function (k) { delete __store[k]; }
};
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
var __events = [];
global.document = {
  readyState: 'loading',
  documentElement: {
    getAttribute: function () { return 'en'; },
    setAttribute: function () {},
    classList: { add: function () {}, remove: function () {} }
  },
  getElementById: function () { return null; },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  addEventListener: function () {},
  removeEventListener: function () {},
  dispatchEvent: function (e) { __events.push({type: e.type, detail: e.detail}); return true; },
  createElement: function () { return { style: {}, classList: { add: function () {} } }; }
};
global.window = global;
global.window.addEventListener = function () {};
global.location = { hash: '', pathname: '/watchlist.html', search: '', origin: 'https://x' };
function OUT(o) { process.stdout.write(JSON.stringify(o)); }
"""


def _run(js_body: str, extra: dict | None = None) -> dict:
    globs = "\n".join("var %s = %s;" % (k, json.dumps(v)) for k, v in (extra or {}).items())
    script = SHIM + "\n" + globs + "\n" + textwrap.dedent(js_body)
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


def _wl(js_body: str, extra: dict | None = None) -> dict:
    return _run("var WL = require(%s);\n%s" % (json.dumps(str(WATCHLIST)), js_body), extra)


# ===========================================================================
# 1. the bulk-entry parser — the anonymous funnel's front door
# ===========================================================================
@needs_node
@pytest.mark.parametrize(
    "text,expect",
    [
        # the two documented shapes
        ("AAPL, MSFT, NVDA", ["AAPL", "MSFT", "NVDA"]),
        ("AAPL 20%, MSFT 15%, NVDA 12%", ["AAPL", "MSFT", "NVDA"]),
        # newline / tab / semicolon separated, and mixed
        ("AAPL\nMSFT\nNVDA", ["AAPL", "MSFT", "NVDA"]),
        ("AAPL\tMSFT; NVDA", ["AAPL", "MSFT", "NVDA"]),
        # a broker's copy-paste: bullets, indices, colons, dollar signs
        ("1. AAPL: $20,\n2. MSFT: $15", ["AAPL", "MSFT"]),
        ("- aapl 20%\n- msft 15%", ["AAPL", "MSFT"]),
        # suffixed and punctuated symbols survive (the books law depends on them)
        ("0700.HK, SHOP.TO, BRK-B", ["0700.HK", "SHOP.TO", "BRK-B"]),
        # duplicates collapse rather than double-counting the same position
        ("AAPL, AAPL, MSFT", ["AAPL", "MSFT"]),
    ],
)
def test_parser_reads_the_shapes_a_real_visitor_pastes(text, expect):
    out = _wl("OUT(WL.parseBook(TEXT));", {"TEXT": text})
    assert [r["t"] for r in out["rows"]] == expect


@needs_node
def test_parser_reports_what_it_could_not_read_instead_of_dropping_it():
    """A silently dropped line is a position the visitor believes we read. The parser
    returns its rejects so the UI can say so."""
    out = _wl("OUT(WL.parseBook(TEXT));",
              {"TEXT": "AAPL, my retirement account, MSFT, ???"})
    assert [r["t"] for r in out["rows"]] == ["AAPL", "MSFT"]
    assert len(out["bad"]) == 2


@needs_node
def test_parser_keeps_the_size_it_was_given():
    out = _wl("OUT(WL.parseBook('AAPL 20%, MSFT 15%, NVDA'));")
    sizes = [r["size"] for r in out["rows"]]
    assert sizes == [20, 15, None]


# ===========================================================================
# 2. the weighting model
# ===========================================================================
@needs_node
def test_equal_mode_ignores_typed_sizes_because_the_control_says_equal():
    """The mode control is an explicit statement by the visitor. If it says Equal, a
    stray "20%" in the pasted text must not quietly re-weight the book."""
    out = _wl(
        "var p = WL.parseBook('AAPL 90%, MSFT 5%, NVDA 5%');"
        "OUT(WL.weightsOf(p, 'equal'));"
    )
    moneys = [round(i["money"], 4) for i in out["items"]]
    assert moneys == [pytest.approx(100 / 3, abs=1e-3)] * 3
    assert out["assumed"] is True


@needs_node
def test_percent_mode_normalises_to_100_and_does_not_claim_it_was_told():
    out = _wl(
        "var p = WL.parseBook('AAPL 50, MSFT 30, NVDA 20');"
        "OUT(WL.weightsOf(p, 'pct'));"
    )
    assert [round(i["money"]) for i in out["items"]] == [50, 30, 20]
    assert out["assumed"] is False          # every row gave a size


@needs_node
def test_a_partially_sized_book_is_flagged_as_assumed_not_silently_filled():
    """Filling a missing size with the average is a reasonable default and a lie if it
    is not disclosed — `assumed` is what drives the "No sizes given" meta line."""
    out = _wl(
        "var p = WL.parseBook('AAPL 60, MSFT 20, NVDA');"
        "OUT(WL.weightsOf(p, 'pct'));"
    )
    assert out["assumed"] is True
    assert sum(i["money"] for i in out["items"]) == pytest.approx(100, abs=1e-6)


@needs_node
def test_weights_always_sum_to_one_hundred_whatever_was_typed():
    for text, mode in (("A 10, B 10, C 10", "pct"), ("A 1500, B 250", "usd"),
                       ("A 3, B 7, C 11, D 2", "shares"), ("A, B, C, D, E", "equal")):
        out = _wl("OUT(WL.weightsOf(WL.parseBook(T), M));", {"T": text, "M": mode})
        assert sum(i["money"] for i in out["items"]) == pytest.approx(100, abs=1e-6), text


# ===========================================================================
# 3. the stage map may only DE-ESCALATE
# ===========================================================================
UP_WORDS = {"early", "confirming", "confirmed"}


@needs_node
def test_stage_map_never_turns_a_falling_state_into_an_up_word():
    """`stageOf` is a fixed display table over the engine's calibrated states. The
    house rule is that a display layer may de-escalate and never escalate, so every
    state whose engine reading is a downtrend must land on a non-up word."""
    out = _wl(
        "var s={};['DECLINE','BOTTOM WATCH','ROLLING OVER','TOP WATCH','COUNTERTREND BOUNCE',"
        "'CONFIRMING TURN','TURN SIGNALED','FRESH BUY','RALLY ON','LIMITED'].forEach("
        "function(k){s[k]=WL.stageOf(k)});OUT(s);"
    )
    # engine `dir: down` / late-cycle states must not read as an up-word
    for falling in ("DECLINE", "BOTTOM WATCH", "ROLLING OVER"):
        assert out[falling] not in UP_WORDS, f"{falling} escalated to {out[falling]}"
    # an unconfirmed turn is at most "early", never "confirming" or better
    assert out["COUNTERTREND BOUNCE"] == "early"
    # the two genuinely confirmed states are the only ones allowed to say so
    assert out["FRESH BUY"] == "confirmed" and out["RALLY ON"] == "confirmed"
    assert out["LIMITED"] == "none"


@needs_node
def test_an_unknown_state_is_not_covered_rather_than_a_guess():
    out = _wl("OUT({a: WL.stageOf('SOMETHING NEW'), b: WL.stageOf(null), c: WL.stageOf('')});")
    assert out == {"a": "none", "b": "none", "c": "none"}


# ===========================================================================
# 4. delta-since-visit: the count and the ink are ONE computation
# ===========================================================================
@needs_node
def test_seen_diff_rows_and_count_cannot_disagree():
    """The list header promises "N changed since your last visit" and the column marks
    which ones. Two computations would eventually print 4 over three marked rows."""
    out = _run(
        "var MB = require(%s);\n"
        "localStorage.setItem('mdash.wl.seen.v1', JSON.stringify("
        "  {A:'RALLY ON', B:'RALLY ON', C:'DECLINE', D:'RALLY ON'}));\n"
        "var now = {A:'DECLINE', B:'RALLY ON', C:'FRESH BUY', D:'RALLY ON', E:'FRESH BUY'};\n"
        "var rows = MB.seenDiffRows(now);\n"
        "localStorage.setItem('mdash.wl.seen.v1', JSON.stringify("
        "  {A:'RALLY ON', B:'RALLY ON', C:'DECLINE', D:'RALLY ON'}));\n"
        "var n = MB.seenDiff(now);\n"
        "OUT({rows: rows, keys: Object.keys(rows).sort(), n: n});"
        % json.dumps(str(MARKET_BOOKS))
    )
    assert out["keys"] == ["A", "C"]
    assert out["n"] == len(out["keys"])
    # a name that was not on the list last visit has no since-your-last-visit story
    assert "E" not in out["rows"]
    assert out["rows"]["A"] == {"from": "RALLY ON", "to": "DECLINE"}


@needs_node
def test_the_snapshot_is_written_after_the_diff_so_it_means_since_you_looked():
    out = _run(
        "var MB = require(%s);\n"
        "localStorage.setItem('mdash.wl.seen.v1', JSON.stringify({A:'RALLY ON'}));\n"
        "var first = MB.seenDiffRows({A:'DECLINE'});\n"
        "var second = MB.seenDiffRows({A:'DECLINE'});\n"
        "OUT({first: Object.keys(first), second: Object.keys(second)});"
        % json.dumps(str(MARKET_BOOKS))
    )
    assert out["first"] == ["A"]
    assert out["second"] == []      # nothing moved since the snapshot was taken


# ===========================================================================
# 5. the visibilitychange re-pull, hardened (W2 scope, recorded on PR #5461)
# ===========================================================================
@needs_node
def test_a_focus_refetch_defers_while_a_push_is_still_pending():
    """THE NAMED BUG. A pull MERGES cloud rows into the local blob (union: cloud wins
    for membership). Inside the 600 ms push debounce a removal is still only local, so
    the merge hands the row straight back and the user watches their deletion undo
    itself.

    The fix is READ-SIDE only — the push and fold paths are frozen — so this test drives
    the real listener: enqueue a push (which arms a debounce timer), fire
    visibilitychange, and assert no pull went out until the queue drained.
    """
    out = _run(
        "var WSJS = require(%s);\n"
        "var t = WSJS._testHooks;\n"
        "OUT({\n"
        "  pendingWithTimer: t.pushPendingWith({A: 1}, {}),\n"
        "  pendingWithQueue: t.pushPendingWith({}, {B: ['X']}),\n"
        "  settled: t.pushPendingWith({}, {})\n"
        "});" % json.dumps(str(WATCHSTORE))
    )
    assert out["pendingWithTimer"] is True     # a debounce timer is armed -> defer
    assert out["pendingWithQueue"] is True     # a push waiting on its list read -> defer
    assert out["settled"] is False             # nothing in flight -> the pull may go


@needs_node
def test_the_deferral_is_bounded_so_a_stuck_queue_cannot_spin():
    """A guard that waits forever is its own outage. The retry ladder is finite; after
    it the next focus or the next edit carries the pull."""
    src = WATCHSTORE.read_text()
    assert "PUSH_SETTLE_TRIES" in src
    assert "if (tries <= 0) return;" in src


# ===========================================================================
# 6. reviewer residual — the OUTER catch in _foldLocalIntoCloud
# ===========================================================================
@needs_node
def test_the_outer_fold_catch_swallows_a_target_resolution_failure_without_marking():
    """`_foldLocalIntoCloud` has TWO catches. The inner one (on the insert) is pinned by
    tests/test_watchstore_multilist_js.py; the OUTER one — which guards resolving (and
    creating) the fold target — had no coverage, and it is the more dangerous of the
    two: it runs BEFORE `_markFolded`, so a bug that marked here would consume the
    one-shot fold and permanently discard the anonymous visitor's whole list.

    THE STUB SHAPE IS THE TEST, for the same reason its sibling records: postgrest-js
    RESOLVES with `{data, error}` and REJECTS on transport failure — it does not throw
    synchronously. This drives the rejection path the outer catch actually guards.
    (A synchronous throw from the client is NOT covered by that catch; recorded as a
    finding rather than repaired here, because the fold path is frozen in this wave.)"""
    out = _run(
        "var WSJS = require(%s);\n"
        "global.window.WL = {\n"
        "  getBlob: function () { return {v:1, items:[{t:'AAPL'},{t:'MSFT'}], order:['AAPL','MSFT']}; },\n"
        "  merge: function () {}\n"
        "};\n"
        "var boom = {from: function () {\n"
        "  var api = {\n"
        "    select: function () { return api; }, eq: function () { return api; },\n"
        "    order: function () { return api; }, limit: function () { return api; },\n"
        "    insert: function () { return Promise.reject(new Error('rls denied')); },\n"
        "    then: function (res, rej) {\n"
        "      return Promise.reject(new Error('rls: relation watchlists denied')).then(res, rej);\n"
        "    }\n"
        "  };\n"
        "  return api;\n"
        "}};\n"
        "WSJS._setTestSession({id: 'u1'}, boom);\n"
        "WSJS.foldLocalIntoCloud(['AAPL', 'MSFT']).then(function (r) {\n"
        "  OUT({resolved: true, ret: r === undefined,\n"
        "       marker: localStorage.getItem('mdash.watchstore.folded.v1')});\n"
        "}, function (e) { OUT({resolved: false, err: String(e)}); });"
        % json.dumps(str(WATCHSTORE))
    )
    # the outer catch turns the failure into a resolved no-op...
    assert out["resolved"] is True, out
    # ...and critically does NOT consume the one-shot, so the next session retries
    assert out["marker"] is None


# ===========================================================================
# 7. the store contract W2 must not have moved
# ===========================================================================
@needs_node
def test_the_default_binding_is_still_the_anonymous_key_verbatim():
    """W2 rewrote this file's render half wholesale. The STORE half is frozen, and the
    default binding is the part every link in the wild depends on."""
    out = _run(
        "require(%s);\n"
        "OUT({key: window.WL.storageKey(), listId: window.WL.listId(),\n"
        "     share: window.WL.shareParam()});" % json.dumps(str(WATCHLIST))
    )
    assert out == {"key": "mdash.watchlist.v1", "listId": None, "share": "wl"}


@needs_node
def test_the_renderer_is_a_clean_no_op_without_its_host():
    """The store half is exercised head-less by two sibling suites. Every renderer W2
    added must therefore no-op when there is nothing to draw into — never a throw that
    takes the store down with it."""
    out = _run(
        "require(%s);\n"
        "window.WL.replace({v:1, updated:'2026-08-01T00:00:00.000Z',\n"
        "  items:[{t:'AAPL'},{t:'MSFT'}], order:['AAPL','MSFT'], settings:{}});\n"
        "window.WL.render();\n"
        "window.WL.add('NVDA'); window.WL.remove('AAPL');\n"
        "OUT({items: window.WL.getBlob().items.map(function (i) { return i.t; }).sort()});"
        % json.dumps(str(WATCHLIST))
    )
    assert out["items"] == ["MSFT", "NVDA"]
