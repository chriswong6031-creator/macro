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


@needs_node
def test_flagship_dark_regression_a_full_book_with_an_empty_watchlist_gets_a_factor_read():
    """DEFECT 1, the worst of them — now pinned at the mechanism instead of at a caller.

    `FX.setAutoWeights` bailed on `!LAST.length`, and `LAST` is the WATCHLIST. But the
    AUTO path's universe is `Object.keys(AUTO_W)` — `render()` never reads `LAST` at all
    when auto weights are set. So a signed-in account with a full portfolio and an EMPTY
    watchlist stored weights that were never resolved, never announced and never reached
    RiskCore: every position read "Not covered" and the Book Seam's risk rail went dark
    for exactly the user the page exists for.

    W2 could not touch factor_exposure.js, so it worked around this from portfolio.js by
    seeding the universe with the book's own names, and pinned THAT ordering here. W3
    fixed the guard, so the workaround is gone and this test moved with it: it now drives
    the real path — `setAutoWeights` alone, with `LAST` empty — and asserts the weights
    reach the world as an `fx-weights` event. Behavioural, so it cannot pass by matching
    a source string that no longer has to exist.

    MUTATION CHECK: restore `if (!p || !LAST.length) return;` in factor_exposure.js and
    this reds (announced: false, universe: [])."""
    fx = ROOT / "templates" / "factor_exposure.js"
    betas = {
        "AAPL": {"mkt": 1.0, "growth": 0.5, "idio_vol": 0.25},
        "MSFT": {"mkt": 0.9, "growth": 0.4, "idio_vol": 0.22},
        "NVDA": {"mkt": 1.3, "growth": 0.9, "idio_vol": 0.40},
    }
    model = {
        "factors": [{"key": "mkt", "label": "Market", "tier": "high"},
                    {"key": "growth", "label": "Growth / Tech", "tier": "high"}],
        "factor_cov": {"mkt": {"mkt": 0.03, "growth": 0.0},
                       "growth": {"mkt": 0.0, "growth": 0.02}},
        "betas": betas,
    }
    out = _run(
        """
        var __panel = { style: {}, innerHTML: '',
          querySelectorAll: function () { return []; }, querySelector: function () { return null; } };
        document.getElementById = function (id) { return id === 'fx_panel' ? __panel : null; };
        // the model arrives by fetch in the browser; hand it over the same promise shape
        global.fetch = function () {
          return Promise.resolve({ ok: true, json: function () { return Promise.resolve(MODEL); } });
        };
        require(%s);
        // THE CASE: the watchlist is empty, so FX.update was never called with a name.
        // Only the portfolio's own dollar weights arrive.
        window.FX.setAutoWeights({ AAPL: 15000, MSFT: 12000, NVDA: 20000 });
        setTimeout(function () {
          var ann = null;
          for (var i = 0; i < __events.length; i++) {
            if (__events[i].type === 'fx-weights') ann = __events[i].detail;
          }
          OUT({ announced: !!ann,
                mode: ann && ann.mode,
                universe: ann ? ann.universe.slice().sort() : [],
                panelShown: __panel.style.display });
        }, 30);
        """ % json.dumps(str(fx)),
        {"MODEL": model},
    )
    assert out["announced"], (
        "the auto weights never left factor_exposure.js — the empty-watchlist guard is back"
    )
    assert out["mode"] == "auto", out
    assert out["universe"] == ["AAPL", "MSFT", "NVDA"], out
    # and the panel actually resolved a read rather than hiding itself
    assert out["panelShown"] == "block", out


def test_portfolio_no_longer_carries_the_retired_fx_seeding_workaround():
    """The companion to the test above. Two independent guarantees of one property is how
    a mechanism fix goes untested: with the seeding call still in place, `LAST` is never
    empty in production and the guard above is never the thing carrying the case. The
    workaround is retired deliberately, so its absence is pinned deliberately."""
    import re

    src = PORTFOLIO.read_text()
    body = src[src.index("function pushFxWeights"):src.index("function pushFxWeights") + 1800]
    # the comment that RECORDS the retirement names the retired call; a scan that cannot
    # tell code from prose would fail on its own documentation
    code = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    code = re.sub(r"//[^\n]*", "", code)
    assert "FX.update(keys)" not in code, (
        "the W2 seeding workaround is back — factor_exposure.js's auto-path guard is then "
        "dead code and the regression it fixes is untested in production"
    )
    assert "FX.setAutoWeights(" in code


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


# ===========================================================================
# 7. W3 — the Risk Center's six tabs, over unchanged engines
#
# Packet §0 puts two gate rows on this wave, and both are the kind a crop cannot
# prove: a crop shows one book on one night, and the honest cases (a name the model
# has never heard of, a stress lens that really does converge, a book with no
# earnings calendar at all) are exactly the ones tonight's artifact may not contain.
# So the tabs are built as PURE string builders over a RiskCore result, and the
# fixtures below hand them books chosen to make each claim falsifiable.
# ===========================================================================
RISK_CORE = ROOT / "templates" / "risk_core.js"
WATCHLIST_RISK = ROOT / "templates" / "watchlist_risk.js"


def _rc(js_body: str, extra: dict | None = None, lang: str = "en") -> dict:
    """Seat risk_core + watchlist_risk in the node shell and run `js_body`.

    `RiskCore` lands on the global (the module attaches to `globalThis`), which the
    shim aliases to `window` — the same object the browser gives the render layer, so
    the tab builders take the identical path they take in production."""
    head = """
    document.documentElement.getAttribute = function (a) {
      return a === 'data-lang' ? %s : 'en';
    };
    var RC = require(%s);
    var WR = require(%s);
    /* Tags out, entities in, whitespace collapsed — BOTH languages left interleaved.
       An earlier version tried to drop the l-zh half with a regex; the dual-emit spans
       nest (a zh string carries its own <span class="fig">), so no regex can balance
       them and the "stripped" text silently lost real copy. Assertions are substring
       checks against English phrases, which do not care that the Chinese is still
       there — and leaving it in means a zh-side regression cannot hide behind the
       stripper either. Attribute contents go with their tags, which is deliberate:
       a Tier-2 receipt may name a technical quantity, glance-tier copy may not. */
    function TEXT(h) {
      return String(h || '')
        .replace(/<[^>]+>/g, ' ').replace(/&rsquo;/g, "'").replace(/&amp;/g, '&')
        .replace(/\\s+/g, ' ').trim();
    }
    """ % (json.dumps(lang), json.dumps(str(RISK_CORE)), json.dumps(str(WATCHLIST_RISK)))
    return _run(head + textwrap.dedent(js_body), extra)


# --- the §0 risk-correctness fixture ---------------------------------------
# 8 correlated tech names + GLD + TLT. GLD is deliberately absent from `betas`:
# it is the unmodeled name the coverage gate is about, and on the real nightly
# artifact GLD is in fact absent, so the fixture matches production rather than
# flattering it.
def _fixture_model(stress: bool = False) -> dict:
    tech = {
        "AAPL": 1.00, "MSFT": 0.95, "NVDA": 1.35, "AVGO": 1.25,
        "AMD": 1.40, "GOOGL": 1.05, "META": 1.10, "MU": 1.30,
    }
    betas = {}
    for t, m in tech.items():
        betas[t] = {"mkt": m, "growth": 0.60, "rates": 0.05, "idio_vol": 0.26}
    # TLT: the model's own diversifier — leans AGAINST the market, on rates
    betas["TLT"] = {"mkt": -0.25, "growth": -0.05, "rates": 1.20, "idio_vol": 0.10}
    model = {
        "factors": [{"key": "mkt", "label": "Market"},
                    {"key": "growth", "label": "Growth / Tech"},
                    {"key": "rates", "label": "Rates (duration)"}],
        "factor_cov": {"mkt": {"mkt": 0.030, "growth": 0.0, "rates": 0.0},
                       "growth": {"mkt": 0.0, "growth": 0.020, "rates": 0.0},
                       "rates": {"mkt": 0.0, "growth": 0.0, "rates": 0.010}},
        "betas": betas,
    }
    if stress:
        # worst-quartile days: the market term dominates and the names converge
        model["factor_cov_stress"] = {
            "mkt": {"mkt": 0.400, "growth": 0.0, "rates": 0.0},
            "growth": {"mkt": 0.0, "growth": 0.020, "rates": 0.0},
            "rates": {"mkt": 0.0, "growth": 0.0, "rates": 0.010}}
        model["stress_meta"] = {"available": True}
    return model


FIXTURE_WMAP = {"AAPL": 10000, "MSFT": 10000, "NVDA": 10000, "AVGO": 10000,
                "AMD": 10000, "GOOGL": 10000, "META": 10000, "MU": 10000,
                "GLD": 10000, "TLT": 10000}


@needs_node
def test_w3_fixture_tech_concentration_is_visible_and_bets_fall_below_the_name_count():
    """§0 risk-correctness, first two rows. Eight names that share a market and a growth
    exposure must NOT read as eight independent positions, and the surface must say which
    names carry it."""
    out = _rc(
        """
        var b = RC.read(MODEL, WMAP).calm;
        var bets = WR.enbClamp(b.enb, b.held.length);
        OUT({
          held: b.held.length,
          enb: b.enb,
          bets: bets.bets,
          topByRisk: b.rankedPositions.slice(0, 4),
          concText: TEXT(WR.concentrationHTML(b, b.coverage))
        });
        """,
        {"MODEL": _fixture_model(), "WMAP": FIXTURE_WMAP},
    )
    # GLD is unmodeled, so nine names reach the model; the read is over those
    assert out["held"] == 9, out
    # "materially below the ticker count" — eight correlated names plus a hedge
    assert out["bets"] <= 4, out
    assert out["enb"] < out["held"] / 2.0, out
    # the tech block, not TLT, is what carries the risk
    assert "TLT" not in out["topByRisk"], out
    # and the tab names a real holder of it, with a figure
    assert "carries" in out["concText"], out["concText"]
    assert "%" in out["concText"], out["concText"]


@needs_node
def test_w3_fixture_tlt_reads_as_a_diversifier_and_gld_never_enters_the_math():
    """§0 rows three and five, together — they are the same property seen from two sides.

    TLT is IN the model and leans against the book, so it must read as the quiet one.
    GLD is NOT in the model, so it must be named as outside it and must never appear as
    a bar, a pair, or a row anywhere — "no unmodeled ticker silently enters factor math"
    is only proved by looking for it in the OUTPUT, not by trusting the coverage split."""
    out = _rc(
        """
        var b = RC.read(MODEL, WMAP).calm;
        var cov = b.coverage;
        var tabs = {
          conc: WR.concentrationHTML(b, cov),
          corr: WR.correlationHTML(b, cov),
          fact: WR.factorsHTML(b, cov),
          weak: WR.weakLinksHTML(b, cov)
        };
        var text = {}; for (var k in tabs) text[k] = TEXT(tabs[k]);
        OUT({
          unmodeled: cov.unmodeled,
          heldHasGld: b.held.indexOf('GLD') >= 0,
          tltMoney: b.W.TLT, tltRisk: b.mctrShare.TLT,
          text: text,
          weakRaw: tabs.weak
        });
        """,
        {"MODEL": _fixture_model(), "WMAP": FIXTURE_WMAP},
    )
    # --- GLD: outside the model, and provably outside every figure -------------
    assert out["unmodeled"] == ["GLD"], out["unmodeled"]
    assert not out["heldHasGld"], "an unmodeled name reached the factor math"
    for tab, body in out["text"].items():
        if tab == "corr":
            # the pair ladder must not pair a name the model cannot price
            assert "GLD ·" not in body and "· GLD" not in body, (tab, body)
        # every tab that reads the model must NAME it as excluded, never omit it silently
        assert "GLD" in body, (tab, body)
        assert "no read for" in body or "not on this list" in body, (tab, body)

    # --- TLT: the model's own diversifier, and the tab says so -----------------
    assert out["tltRisk"] < out["tltMoney"] / 2.0, (
        "TLT should carry far less risk than money in this fixture: %s vs %s"
        % (out["tltRisk"], out["tltMoney"]))
    weak = out["text"]["weak"]
    assert "TLT" in weak, weak
    assert ("pulling the other way" in weak) or ("quiet one" in weak), weak


@needs_node
def test_w3_stress_tab_can_show_convergence_and_says_so_when_it_does_not():
    """§0 row four. The gate is that the lens CAN show convergence — so the fixture is
    built to converge, and the calm-model control proves the same surface does not claim
    it when it is not there. Both directions, because a tab that only knows how to report
    tightening turns an ordinary book into a missing read."""
    converging = _rc(
        """
        var RR = RC.read(MODEL, WMAP);
        var calm = RR.calm, st = RR.stress;
        OUT({ hasStress: RR.hasStress, diverges: RR.diverges,
              calmEnb: calm.enb, stressEnb: st.enb,
              text: TEXT(WR.stressHTML(RR, calm.coverage)) });
        """,
        {"MODEL": _fixture_model(stress=True), "WMAP": FIXTURE_WMAP},
    )
    assert converging["hasStress"], converging
    assert converging["stressEnb"] < converging["calmEnb"], converging
    assert converging["diverges"], (
        "the fixture was meant to converge hard enough to trip the divergence flag: %s"
        % converging)
    txt = converging["text"]
    assert "tightens" in txt, txt
    # both counts print regardless of which branch the claim took
    assert "on an average day" in txt.lower(), txt
    assert "falling days" in txt.lower(), txt

    # control: no stress block in the model at all -> an honest absence, not a guess
    absent = _rc(
        """
        var RR = RC.read(MODEL, WMAP);
        OUT({ hasStress: RR.hasStress, text: TEXT(WR.stressHTML(RR, RR.calm.coverage)) });
        """,
        {"MODEL": _fixture_model(stress=False), "WMAP": FIXTURE_WMAP},
    )
    assert not absent["hasStress"], absent
    assert "no falling-days lens" in absent["text"], absent["text"]
    assert "tightens" not in absent["text"], absent["text"]


@needs_node
def test_w3_correlation_prints_the_closest_pair_even_when_none_crosses_the_line():
    """The common case on an orthogonalized model with real per-name idio vol: no pair
    reaches 0.70. "No twins" is a finding, and printing the closest pair anyway is what
    stops it reading as "these names are unrelated" — which would be false."""
    out = _rc(
        """
        var b = RC.read(MODEL, WMAP).calm;
        var pairs = [];
        for (var i = 0; i < b.held.length; i++)
          for (var j = i + 1; j < b.held.length; j++)
            pairs.push(b.rho(b.held[i], b.held[j]));
        pairs.sort(function (x, y) { return y - x; });
        OUT({ maxRho: pairs[0], text: TEXT(WR.correlationHTML(b, b.coverage)) });
        """,
        {"MODEL": _fixture_model(), "WMAP": FIXTURE_WMAP},
    )
    assert out["maxRho"] < 0.70, "fixture drifted — it is meant to sit below the line"
    txt = out["text"]
    assert "closest pair" in txt, txt
    assert "0.70" in txt, txt
    # it must NOT claim independence
    assert "unrelated" not in txt and "no correlation" not in txt.lower(), txt


@needs_node
def test_w3_events_tab_never_claims_a_calendar_it_has_not_read():
    """The events read is composed from per-ticker JSON the page has already hydrated.
    Three states, three honest answers: nothing loaded, loaded but no dates ahead, and a
    real calendar. The failure this pins is the middle one reading like the first."""
    nothing = _rc("WR.__setCardJson({}); OUT({ text: TEXT(WR.eventsHTML({ unmodeled: [] })) });")
    assert "arrive with each name" in nothing["text"], nothing["text"]

    no_dates = _rc(
        "WR.__setCardJson({ AAPL: {}, MSFT: { earnings: {} } });"
        " OUT({ text: TEXT(WR.eventsHTML({ unmodeled: [] })) });"
    )
    assert "No reporting dates ahead" in no_dates["text"], no_dates["text"]
    assert "2" in no_dates["text"], "it must say how many names it actually read"

    real = _rc(
        """
        var soon = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
        var far  = new Date(Date.now() + 60 * 86400000).toISOString().slice(0, 10);
        WR.__setCardJson({
          NVDA: { earnings: { next_date: soon, next_time: 'after-hours' } },
          AAPL: { earnings: { next_date: far } },
          TLT:  {}
        });
        OUT({ text: TEXT(WR.eventsHTML({ unmodeled: [] })) });
        """
    )
    assert "NVDA" in real["text"], real["text"]
    assert "within two weeks" in real["text"], real["text"]
    # a name with no calendar is not invented into the list
    assert "TLT" not in real["text"], real["text"]


@needs_node
def test_w3_coverage_honesty_states_market_coverage_and_never_totals_two_currencies():
    """§0 coverage-honesty row. With positions in more than one market the tabs must say
    which market their figures describe AND state that the currencies are never summed —
    the single sentence that stops a reader inferring a portfolio total that does not
    exist. Driven through `MB.presentBooks`, the same seam the page uses."""
    out = _rc(
        """
        window.MB = {
          isModeled: function (t) { return !/\\.(HK|SS|TO)$/.test(t) && t !== 'GC=F'; },
          presentBooks: function () { return ['us', 'hk', 'cn']; },
          getBook: function () { return 'all'; }
        };
        OUT({ multi: TEXT(WR.coverageFoot({ unmodeled: ['GC=F'] })) });
        """
    )
    txt = out["multi"]
    assert "US-listed" in txt, txt
    assert "never added into one number across currencies" in txt, txt
    # the unsupported symbol is named, not dropped
    assert "GC=F" in txt, txt
    assert "no read for" in txt, txt

    single = _rc(
        """
        window.MB = { isModeled: function () { return true; },
                      presentBooks: function () { return ['us']; },
                      getBook: function () { return 'all'; } };
        OUT({ t: TEXT(WR.coverageFoot({ unmodeled: [] })) });
        """
    )
    assert single["t"] == "", "a single-market book with full coverage needs no disclaimer"


@needs_node
def test_w3_factor_grouping_caveat_is_surfaced_where_the_grouping_is_displayed():
    """packet §8-W3: the one permitted risk_core.js act was to surface `factorBets`'
    diagonal-only approximation honestly WHERE IT IS DISPLAYED — not to change it. The
    consequence is user-visible (the group a name is filed under can name a different
    force from the book-level ranking), so the disclosure lives in the rendered copy."""
    out = _rc(
        """
        var b = RC.read(MODEL, WMAP).calm;
        OUT({ text: TEXT(WR.factorsHTML(b, b.coverage)) });
        """,
        {"MODEL": _fixture_model(), "WMAP": FIXTURE_WMAP},
    )
    txt = out["text"]
    assert "one force at a time" in txt, txt
    assert "filed under the larger one" in txt, txt
    # and the engine still carries the reason in source, pointing at this surface
    src = RISK_CORE.read_text()
    assert "DIAGONAL" in src and "factorsHTML" in src, "the engine-side note lost its pointer"


@needs_node
def test_w3_scenario_lab_states_its_default_and_stays_descriptive():
    """§14 A4 / WRI-R3. The lab describes; it never advises. And the default size is
    STATED — production shipped $10,000 into an unlabelled box, which is how a round
    number becomes a suggestion by accident."""
    out = _rc(
        """
        WR.__setModel(MODEL, WMAP, 'calm');
        OUT({
          intro: TEXT(WR.labIntroHTML()),
          dflt: WR.W4_DEFAULT_DOLLARS,
          modeled: TEXT(WR.scenarioHTML('NVDA', 10000)),
          unmodeled: TEXT(WR.scenarioHTML('GC=F', 10000)),
          empty: TEXT(WR.scenarioHTML('', 10000))
        });
        """,
        {"MODEL": _fixture_model(), "WMAP": FIXTURE_WMAP},
    )
    assert out["dflt"] == 10000, out["dflt"]
    intro = out["intro"]
    assert "$10,000" in intro, intro
    assert "not a suggested size" in intro, intro
    assert "not drawn from your book" in intro, intro

    # an unmodeled candidate gets no numbers invented for it
    un = out["unmodeled"]
    assert "no read for" in un, un
    assert "%" not in un, un
    assert out["empty"].startswith("Name a position"), out["empty"]

    # descriptive, and it says so
    mod = out["modeled"]
    assert "would" in mod, mod
    assert "not a recommendation" in mod, mod


@needs_node
def test_w3_no_imperatives_or_internal_vocabulary_in_any_rendered_tab():
    """Glance-tier copy law across the whole W3 surface at once. The banned list is the
    packet's: internal state names, the study/lane vocabulary, and any verb that tells
    someone what to do with their own money."""
    out = _rc(
        """
        var RR = RC.read(MODEL, WMAP);
        var b = RR.calm, cov = b.coverage;
        WR.__setModel(MODEL, WMAP, RR.defaultLens);
        WR.__setCardJson({ NVDA: { earnings: { next_date: '2099-01-15' } } });
        var all = [
          WR.concentrationHTML(b, cov), WR.correlationHTML(b, cov),
          WR.factorsHTML(b, cov), WR.stressHTML(RR, cov),
          WR.eventsHTML(cov), WR.weakLinksHTML(b, cov),
          WR.labIntroHTML(), WR.scenarioHTML('AAPL', 10000)
        ];
        OUT({ raw: all.join('\\n'), text: all.map(TEXT).join(' \\n ') });
        """,
        {"MODEL": _fixture_model(stress=True), "WMAP": FIXTURE_WMAP},
    )
    text = out["text"]
    banned_words = [
        # internal machinery a reader has no name for
        "ENB", "MCTR", "effective number of bets", "idiosyncratic", "Euler",
        "mctrShare", "factorShare", "beta", "variance", "covariance",
        "WRI", "lane", "falsifier", "证伪", "validated",
    ]
    hits = [w for w in banned_words if w.lower() in text.lower()]
    assert not hits, (hits, text[:400])

    # no instruction to do anything with a position
    for verb in ("you should", "consider adding", "consider trimming", "we recommend",
                 "buy ", "sell ", "trim ", "hedge ", "add to your", "reduce your"):
        assert verb.lower() not in text.lower(), (verb, text[:400])

    # tier names may be NAMED, never explained: no title= anywhere in the emitted HTML
    assert "title=" not in out["raw"], "translated copy in a title attribute"


@needs_node
def test_w3_every_tab_emits_both_languages():
    """zh copy is a build output, not a translation pass — every string the tabs emit
    carries both halves of the dual-emit pair, or the page goes half-English under zh."""
    out = _rc(
        """
        var RR = RC.read(MODEL, WMAP);
        var b = RR.calm, cov = b.coverage;
        WR.__setModel(MODEL, WMAP, RR.defaultLens);
        WR.__setCardJson({ NVDA: { earnings: { next_date: '2099-01-15' } } });
        var tabs = {
          conc: WR.concentrationHTML(b, cov), corr: WR.correlationHTML(b, cov),
          fact: WR.factorsHTML(b, cov), strs: WR.stressHTML(RR, cov),
          evt: WR.eventsHTML(cov), weak: WR.weakLinksHTML(b, cov),
          lab: WR.labIntroHTML(), scen: WR.scenarioHTML('AAPL', 10000)
        };
        var counts = {};
        for (var k in tabs) {
          counts[k] = {
            en: (tabs[k].match(/class="l-en"/g) || []).length,
            zh: (tabs[k].match(/class="l-zh"/g) || []).length,
            cjk: /[\\u4e00-\\u9fff]/.test(tabs[k])
          };
        }
        OUT(counts);
        """,
        {"MODEL": _fixture_model(stress=True), "WMAP": FIXTURE_WMAP},
    )
    for tab, c in out.items():
        assert c["en"] > 0, (tab, c)
        assert c["en"] == c["zh"], ("dual-emit is unbalanced — a string lost its zh half",
                                    tab, c)
        assert c["cjk"], ("no Chinese characters emitted at all", tab, c)


@needs_node
def test_w3_tabs_do_not_repeat_each_others_claim():
    """DESIGN_NOTES §5.5, generalised: one dominant idea per tab. The seam already owns
    the cluster claim and Concentration owns the single-name one, so no two tab CLAIMS
    may be the same sentence — a Risk Center where two tabs answer one question is the
    'pile of unrelated cards' the whole revamp exists to remove."""
    out = _rc(
        """
        var RR = RC.read(MODEL, WMAP);
        var b = RR.calm, cov = b.coverage;
        WR.__setCardJson({ NVDA: { earnings: { next_date: '2099-01-15' } } });
        function claim(h) {
          var m = String(h).match(/<p class="rc-claim">([\\s\\S]*?)<\\/p>/);
          return m ? TEXT(m[1]) : '';
        }
        OUT({
          conc: claim(WR.concentrationHTML(b, cov)), corr: claim(WR.correlationHTML(b, cov)),
          fact: claim(WR.factorsHTML(b, cov)), strs: claim(WR.stressHTML(RR, cov)),
          evt: claim(WR.eventsHTML(cov)), weak: claim(WR.weakLinksHTML(b, cov))
        });
        """,
        {"MODEL": _fixture_model(stress=True), "WMAP": FIXTURE_WMAP},
    )
    claims = [v for v in out.values() if v]
    assert len(claims) == 6, out
    assert len(set(claims)) == 6, out
    # concentration owns "carries N% of the risk"; weak links owns the money-vs-risk ratio
    assert "carries" in out["conc"], out["conc"]
    assert "of the money and" in out["weak"], out["weak"]
    assert out["conc"] != out["weak"]
