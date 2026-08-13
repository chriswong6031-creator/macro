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
def test_the_defer_predicate_covers_all_three_push_states():
    """THE NAMED BUG. A pull MERGES cloud rows into the local blob (union: cloud wins
    for membership). Inside the push window a removal is still only local, so the merge
    hands the row straight back and the user watches their deletion undo itself.

    WHAT THIS PINS, precisely: the pure predicate the visibilitychange listener consults
    — a truth table over its three inputs — NOT an end-to-end drive of the listener
    (that needs real timers and a live Supabase double, and lives in the store suite's
    territory). It is the predicate that decides, so it is the predicate that is pinned;
    the docstring says so rather than implying coverage this body does not have.

    Three states, because there are three. The debounce TIMER is deleted the moment
    `pushList` is called, so a table over timers+queue alone still let a pull land inside
    the DELETE's round trip and resurrect the row one RTT later — which is why
    `inFlight` is the third column."""
    out = _run(
        "var WSJS = require(%s);\n"
        "var t = WSJS._testHooks;\n"
        "OUT({\n"
        "  timerArmed:  t.pushPendingWith({A: 1}, {}, 0),\n"
        "  queued:      t.pushPendingWith({}, {B: ['X']}, 0),\n"
        "  inFlight:    t.pushPendingWith({}, {}, 1),\n"
        "  settled:     t.pushPendingWith({}, {}, 0),\n"
        "  counterZero: t.inFlight()\n"
        "});" % json.dumps(str(WATCHSTORE))
    )
    assert out["timerArmed"] is True      # a debounce timer is armed -> defer
    assert out["queued"] is True          # a push waiting on its list read -> defer
    assert out["inFlight"] is True        # the DELETE is on the wire -> defer
    assert out["settled"] is False        # nothing pending -> the pull may go
    assert out["counterZero"] == 0        # the counter starts settled


@needs_node
def test_the_in_flight_counter_is_incremented_around_the_push_not_inside_it():
    """The push path is FROZEN in this wave, so the in-flight window is counted by a
    wrapper at the two call sites rather than by editing `pushList`. If that ever moves
    inside, this is the reminder that the freeze was the reason."""
    src = WATCHSTORE.read_text()
    assert "function _trackedPush(listId, tickers)" in src
    assert "_pushInFlight++" in src
    body = src[src.index("function pushList(listId, symbols)"):]
    body = body[:body.index("function setActiveList")]
    assert "_pushInFlight" not in body, "the frozen push path was edited"
    # both schedulers must go through the wrapper, or the window is uncounted again
    assert "_trackedPush(listId, tickers)" in src and "_trackedPush(id, tickers)" in src


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
# 7. the lane renderer actually RENDERS (round-2 blocker B1)
# ===========================================================================
WRI_SHIM = """
global.window = global;
global.document = {
  readyState: 'loading',
  documentElement: { getAttribute: function () { return 'en'; } },
  getElementById: function () { return null; },
  addEventListener: function () {},
  querySelectorAll: function () { return []; }
};
"""

RICH_J = {
    "tech": {"price": 100, "pct_vs_200dma": 18.5, "rsi14": 72},
    "earnings": {"next_date": "2026-08-20"},
    "revisions": {"eps_fwd_4w_pct": -3.1},
    "financials": {"net_debt_to_ebitda": 4.2},
    "positioning": {"short_pct_float": 9.1},
    "smart_money": {"insider_sales_90d": 5},
    "macro_sensitivity": {"rates": {"beta": -0.8}},
}


@needs_node
@pytest.mark.parametrize("payload", [{}, RICH_J], ids=["empty", "rich"])
def test_lane_rows_renders_seven_rows_instead_of_throwing(payload):
    """THE ROUND-2 BLOCKER, pinned.

    `laneRowsHTML` calls `stateToken`, which lived 700 lines away inside the braid-hero
    block. W2 deleted that block and took the function with it, so `WRI.laneRows` threw
    ReferenceError on EVERY call. Its only caller — the portfolio drawer — wraps the
    call in try/catch and falls back to an honest-null line, so the per-name lane read
    shipped 100% dark for every signed-in user while LOOKING like a data gap.

    The lesson generalises past this one symbol: a renderer guarded by a catch cannot be
    verified by reading its caller, because the caller's failure mode is indistinguishable
    from its success-with-no-data mode. So this asserts the OUTPUT, not the absence of an
    exception — a non-empty string carrying all seven lane rows and their state tokens.
    An empty payload is included deliberately: the lanes must still render (as n/a), so a
    future refactor cannot satisfy this by returning '' for thin data."""
    out = _run(
        WRI_SHIM
        + "require(%s);\n"
        "var h = window.WRI.laneRows(J);\n"
        "OUT({len: h.length, rows: (h.match(/wri-lrow/g)||[]).length,\n"
        "     tokens: (h.match(/class=\"st /g)||[]).length,\n"
        "     type: typeof h});"
        % json.dumps(str(ROOT / "templates" / "watchlist_risk.js")),
        {"J": payload},
    )
    assert out["type"] == "string"
    assert out["len"] > 0, "laneRows returned an empty string — the drawer would look like a data gap"
    assert out["rows"] == 7, out
    assert out["tokens"] == 7, out


@needs_node
def test_every_exported_WRI_helper_is_callable():
    """The same deletion could have orphaned any of the exported helpers, and each one is
    reached through a try/catch somewhere. Call the whole surface."""
    out = _run(
        WRI_SHIM
        + "require(%s);\n"
        "var r = {};\n"
        "r.laneRead = typeof window.WRI.laneRead(J);\n"
        "r.roleBadge = typeof window.WRI.roleBadge(window.WRI.laneRead(J));\n"
        "r.laneRows = typeof window.WRI.laneRows(J);\n"
        "r.chainRows = typeof window.WRI.chainRows('NVDA');\n"
        "window.WRI.noteJson('NVDA', J);\n"
        "r.noteJson = 'ok';\n"
        "OUT(r);" % json.dumps(str(ROOT / "templates" / "watchlist_risk.js")),
        {"J": RICH_J},
    )
    assert out["laneRead"] == "object"
    assert out["laneRows"] == "string"
    assert out["chainRows"] == "string"
    assert out["noteJson"] == "ok"
    assert out["roleBadge"] in ("object", "string")   # null or a badge


# ===========================================================================
# 8. the store contract W2 must not have moved
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


# ===========================================================================
# 9. the CI-runnable half of the browser gate (round-2 item 6)
#
# The full 33-assertion gate needs a browser and is committed at
# mockups/refs/psi/workspace/crops/impl/verify_w2_workspace.py, run by hand. A
# `pytest.importorskip("playwright")` here would SKIP in the packs and report green
# while proving nothing (house trap: ci-packs-install-minimal-deps-not-requirements),
# so everything checkable WITHOUT a browser is asserted here against the template and
# the shipped source instead.
# ===========================================================================
TEMPLATE = ROOT / "templates" / "watchlist.html.j2"
PORTFOLIO = ROOT / "templates" / "portfolio.js"

# The pack's install line for the job that runs this file (.github/ci/legacy-jobs.yml,
# `wri-risk-core`): `pip install pytest pandas numpy pyarrow pyyaml`. NOTHING in this
# file may import outside that set — see test_this_suite_imports_nothing_the_pack_lacks.
PACK_DEPS = {"pytest", "pandas", "numpy", "pyarrow", "yaml"}


@pytest.fixture(scope="module")
def template() -> str:
    """The template SOURCE, deliberately not a Jinja render.

    An earlier version of this fixture rendered the .j2 through the real builder
    context, which meant importing jinja2 — a package the pack running this suite does
    not install. Locally that passed; on CI the six tests below ERRORed at fixture setup
    and the step exited 1. Reading the source is not a workaround for that: every
    assertion here is about literal content (an id, an attribute, a selector, a word),
    and against the SOURCE they are strictly stronger — a `title=` behind a Jinja
    conditional is invisible to one rendering and caught here.

    The one thing a render would additionally cover — copy injected by the `t()` macro —
    is covered directly by test_the_t_macro_emits_no_title_attribute below."""
    return TEMPLATE.read_text()


def test_the_account_sync_panel_is_gone_from_the_markup(template):
    """Gate row: the header chip is the ONLY sync disclosure."""
    # not merely `id="..."` — the whole token, so a stray reference in a comment or a
    # leftover selector is caught too
    for dead in ("wl_auth", "wl_syncpill", "wl_signin", "wl_signout",
                 "wl_account", "wl_authbox", "wl_who"):
        assert dead not in template, dead
    assert 'id="ws_savechip"' in template


def test_zero_title_attributes_in_the_workspace_markup(template):
    """i18n law: translated copy never goes in title=, because an attribute has no room
    for the dual-emit spans the rest of the page uses."""
    import re
    body = template.split("<body>", 1)[1]
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)      # comments are not markup
    hits = re.findall(r'<[^>]*\stitle="[^"]*"', body)
    assert not hits, hits[:3]


def test_the_t_macro_emits_no_title_attribute(template):
    """The one thing a Jinja render would cover that the source does not: copy the `t()`
    macro injects. Pinned directly, so the fixture never needs to render."""
    import re
    m = re.search(r"\{%\s*macro\s+t\(.*?\{%-?\s*endmacro\s*-?%\}", template, re.S)
    assert m, "the t() macro moved — this pin needs to follow it"
    assert "title=" not in m.group(0), m.group(0)


def test_no_banned_glance_tier_vocabulary_in_the_markup(template):
    """Over the WHOLE source, comments included: an internal state name is no more
    welcome in a comment a translator will read than in the copy itself, and the
    template currently contains none of them anywhere."""
    banned = ["ENB", "MCTR", "effective number of bets", "mctrShare",
              "falsifier", "证伪", "validated"]
    hits = [w for w in banned if w.lower() in template.lower()]
    assert not hits, hits


def test_the_stance_set_is_the_descriptive_subset_only():
    """DESIGN_NOTES §7b: Watch / Get ready / No action. "Act" and "Protect gains" read
    as trade instructions on a page showing someone's actual money."""
    src = (ROOT / "templates" / "watchlist.js").read_text() + PORTFOLIO.read_text()
    assert "'Protect gains'" not in src and '"Protect gains"' not in src
    for stance in ("Watch", "Get ready", "No action"):
        assert stance in src, stance


def test_all_four_save_chip_states_are_defined_with_copy_and_a_receipt():
    src = (ROOT / "templates" / "watchlist.js").read_text()
    import re
    block = src[src.index("var CHIP = {"):src.index("var chipState")]
    for state in ("saved", "saving", "local", "offline"):
        assert re.search(r"\b%s:\s*\['is-%s'" % (state, state), block), state
    # each entry is [class, en, zh, tip-en, tip-zh] — five fields, no missing receipt
    for line in re.findall(r"\['is-\w+',(.*?)\]\s*[,}]", block, re.S):
        assert line.count("'") >= 8, line[:60]


# ---- round-2 item 7: regression pins for the defects this PR fixed ---------
def test_page_blank_regression_the_mode_rule_is_scoped_to_the_main_element(template):
    """DEFECT 7. `[data-ws-mode]{display:none}` also matches <html>, which carries the
    same attribute — so the rule blanked the ENTIRE page on first paint. Mutation-tested:
    dropping the `main.ws >` scope re-greens without this."""
    assert "main.ws > [data-ws-mode] { display:none; }" in template
    import re
    # comments are not rules — the explanation of this very bug quotes the bad selector
    css = re.sub(r"/\*.*?\*/", "", template, flags=re.S)
    # no UNSCOPED selector may set display:none on the mode attribute
    for m in re.finditer(r"([^\n{}]*\[data-ws-mode\][^\n{}]*)\{([^}]*)\}", css):
        sel, body = m.group(1), m.group(2)
        if "display:none" in body.replace(" ", ""):
            assert "main.ws" in sel, "unscoped mode rule can blank <html>: %r" % sel.strip()


def test_book_filter_regression_an_empty_model_never_resets_a_persisted_book():
    """DEFECT 2. `refresh()` fell back to All whenever the active book had no members —
    including on first paint, before positions had loaded, and it PERSISTED that reset,
    so the visitor's choice never came back. "We don't know yet" and "that book is gone"
    have to be different answers."""
    out = _run(
        # the module reads the persisted book AT REQUIRE TIME, so the seed must precede it
        "localStorage.setItem('mdash.book.v1', 'hk');\n"
        "var MB = require(%s);\n"
        "MB.refresh([], null, null);\n"                       # first paint: nothing loaded
        "var afterEmpty = { book: MB.getBook(), stored: localStorage.getItem('mdash.book.v1') };\n"
        "MB.refresh(['NVDA'], [{ticker:'0700.HK'},{ticker:'NVDA'}], function(){return 1;});\n"
        "var afterLoad = { book: MB.getBook(), stored: localStorage.getItem('mdash.book.v1') };\n"
        "MB.refresh(['NVDA'], [{ticker:'NVDA'}], function(){return 1;});\n"   # hk genuinely gone
        "var afterGone = { book: MB.getBook(), stored: localStorage.getItem('mdash.book.v1') };\n"
        "OUT({afterEmpty: afterEmpty, afterLoad: afterLoad, afterGone: afterGone});"
        % json.dumps(str(MARKET_BOOKS))
    )
    assert out["afterEmpty"] == {"book": "hk", "stored": "hk"}, out
    assert out["afterLoad"]["book"] == "hk", out
    # ...but a book that really has no members still falls back, or the view is dead
    assert out["afterGone"]["book"] == "all", out


def test_flagship_dark_regression_the_book_seeds_the_factor_universe_itself():
    """DEFECT 1, the worst of them. `FX.setAutoWeights` stores its map but returns early
    unless the FX layer already has a ticker list from `FX.update()` — which on this page
    is the WATCHLIST. A user with a full book and an empty watchlist therefore stored
    weights that were never resolved, never announced and never reached RiskCore: every
    position read "Not covered" and the Book Seam's risk rail went dark for exactly the
    user the page exists for.

    Source-level because the ordering is the fix: `update` must be called with the book's
    own names BEFORE `setAutoWeights`, or the guard swallows it again."""
    src = PORTFOLIO.read_text()
    body = src[src.index("function pushFxWeights"):src.index("function pushFxWeights") + 1800]
    iu = body.index("FX.update(keys)")
    isa = body.index("FX.setAutoWeights(")
    assert iu < isa, "FX.update must seed the universe BEFORE setAutoWeights"
    assert "keys.length >= 2 && window.FX.update" in body


def test_seam_segment_cap_is_bounded_and_the_denominators_are_not():
    """DEFECT 5 (round-2). One segment per position overflowed the PAGE at 100 names on
    390px (measured 86px). The rail now folds a disclosed tail — but the brackets and
    both denominators must still be computed over ALL items, or capping would silently
    change what the seam claims."""
    src = (ROOT / "templates" / "watchlist.js").read_text()
    import re
    m = re.search(r"var MAX_SEGS = (\d+);", src)
    assert m, "the cap constant is gone"
    assert 8 <= int(m.group(1)) <= 40, "cap out of the legible range: %s" % m.group(1)
    block = src[src.index("function seam(host, cfg)"):src.index("// ---- book (market) filtering")]
    tot = block[block.index("function total(key)"):block.index("function rail(key)")]
    assert "all.forEach" in tot and "items.forEach" not in tot, \
        "the denominator must be over ALL items, not the capped view"
    cl = block[block.index("function clusterPct(key)"):]
    cl = cl[:cl.index("}")+1]
    assert "all.forEach" in cl, "the bracket must be over ALL items"


def test_share_counts_never_speak_as_money():
    """ROUND-2 item 4. Anonymously there is no price plane, so a share count cannot be
    turned into a position size — "98% of the money sits in F" was printed for a book
    whose largest holding by far was the BRK-A share shown at 0.0%."""
    out = _wl(
        "var p = WL.parseBook('BRK-A 1, F 5000, AAPL 100');\n"
        "OUT({shares: WL.weightsOf(p,'shares').unit, pct: WL.weightsOf(p,'pct').unit,\n"
        "     usd: WL.weightsOf(p,'usd').unit, equal: WL.weightsOf(p,'equal').unit});"
    )
    assert out["shares"] == "shares", "share counts must not be typed as money"
    assert out["pct"] == "money" and out["usd"] == "money" and out["equal"] == "money"
    # and the copy branch actually exists for that unit
    src = (ROOT / "templates" / "watchlist.js").read_text()
    for phrase in ("of the share count", "A share count is not a position size",
                   "股数不等于仓位大小"):
        assert phrase in src, phrase


def test_the_legacy_render_path_survives_for_the_old_markup():
    """BLOCKER B2. site/watchlist.html lags its template by over an hour while the JS
    pairs go live in ~3 minutes, so production WILL serve the OLD markup with this file.
    A workspace-only renderer turns that window into the #5463 husk, silently.

    The end-to-end proof is verify_b2_old_html_new_js.py, which swaps files against LIVE
    production HTML. This pins the seam it depends on."""
    src = (ROOT / "templates" / "watchlist.js").read_text()
    assert "function isLegacyPage()" in src
    assert "if (isLegacyPage()) { lgRender(); return; }" in src
    assert "if (isLegacyPage()) { initLegacy(); return; }" in src
    for fn in ("lgRender", "lgCardHTML", "lgViewItems", "lgWireControls", "lgRenderStarters"):
        assert "function %s(" % fn in src, fn
    ws = WATCHSTORE.read_text()
    assert "if (!chip && !box) return;" in ws, "the dormancy guard is gone again"
    assert "box.style.display = 'flex'" in ws, "the pre-W2 auth panel is left hidden"


def test_watchstore_is_dormant_on_a_page_with_neither_sync_host():
    """committee.html loads watchstore.js and has never touched a list. W2 deleted the
    `if (!box) return;` guard that kept it dormant, making it a full cloud participant —
    MDXAuth wiring, an unrequested one-time reload, and a reachable list-creation path."""
    out = _run(
        "var calls = [];\n"
        "global.document.getElementById = function () { return null; };\n"
        "global.window.SUPABASE_CFG = {url: 'https://x.supabase.co', anonKey: 'k'};\n"
        "global.window.MDXAuth = {\n"
        "  onChange: function () { calls.push('onChange'); },\n"
        "  hasSession: function () { calls.push('hasSession'); return true; },\n"
        "  open: function () {}, signOut: function () {} };\n"
        "global.window.getSupabaseClient = function () { calls.push('client'); return Promise.resolve({}); };\n"
        "global.document.readyState = 'complete';\n"
        "require(%s);\n"
        "setTimeout(function () { OUT({calls: calls}); }, 40);"
        % json.dumps(str(WATCHSTORE))
    )
    assert out["calls"] == [], "watchstore joined a cloud session with no sync host: %s" % out


# ===========================================================================
# 10. the suite must run in the environment that actually runs it
# ===========================================================================
def test_this_suite_imports_nothing_the_pack_lacks():
    """THE CI-ONLY FAILURE, pinned as a class rather than as one symbol.

    The packs install a MINIMAL dependency set, not requirements.txt — for the job that
    runs this file, `pip install pytest pandas numpy pyarrow pyyaml`. A test that reaches
    outside it passes on a developer machine (where the whole world is installed) and
    ERRORs on CI, which is the most expensive shape of failure: green where it is cheap
    to notice, red where it is not.

    That is exactly what happened. A fixture here rendered the template through Jinja to
    assert against the output, importing `jinja2` — not in the list — so six tests
    ERRORed at setup and the step exited 1 while the local run said 227 passed. The
    fixture now reads the template source, which needed no dependency and is the stronger
    assertion anyway.

    Pinning the SYMBOL would have been the small lesson. The class is: this file's import
    surface is part of its contract with the runner. `pyyaml` is in the pack's list for
    the same reason, recorded in the job's own comment."""
    import ast
    import sys

    tree = ast.parse(Path(__file__).read_text())
    stdlib = getattr(sys, "stdlib_module_names", set())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if not top or top in stdlib or top in PACK_DEPS or top == "__future__":
                continue
            offenders.append(name)
    assert not offenders, (
        "these imports are not in the pack's install set %s — they pass locally and "
        "ERROR on CI: %s" % (sorted(PACK_DEPS), sorted(set(offenders))))


def test_the_pack_dep_list_matches_the_job_that_runs_this_file():
    """PACK_DEPS above is a copy of a list that lives in the workflow. A copy that can
    drift is worse than no copy, so it is checked against the source of truth."""
    import re

    wf = (ROOT / ".github" / "ci" / "legacy-jobs.yml").read_text()
    job = wf[wf.index("  wri-risk-core:"):]
    job = job[:job.index("\n  house-law-registry:")] if "\n  house-law-registry:" in job else job
    assert "tests/test_watchlist_workspace_js.py" in job, \
        "this suite is no longer run by wri-risk-core — PACK_DEPS is pinned to the wrong job"
    m = re.search(r"run: pip install ([^\n]+)", job)
    assert m, "the install line moved"
    installed = {d.strip() for d in m.group(1).split()}
    # pyyaml imports as `yaml`; keep the mapping explicit rather than clever
    normalised = {"pyyaml": "yaml"}
    installed = {normalised.get(d, d) for d in installed}
    assert installed == PACK_DEPS, (
        "the job's install set moved; update PACK_DEPS deliberately. "
        "job=%s PACK_DEPS=%s" % (sorted(installed), sorted(PACK_DEPS)))
