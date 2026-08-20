"""tests/test_portfolio_truth_a1a_js.py — A1A Portfolio Population Truth + State
Authority mutation-red battery.

research/market_os/MASTERMIND_MARKET_OS_ARCHITECTURE_FREEZE_AND_A1A_COMMISSIONING_2026-08-20.md
§6-13 names nine live mechanisms on Macro's Watchlist/Portfolio workspace that let a
Watchlist name, a temporary pasted basket, or a stale local store silently stand in for
the canonical Portfolio. This suite pins the ten restorations §13 lists as required
mutation reds — each test's docstring names the exact revert that turns it red.

templates/market_books.js and templates/watchstore.js are cleanly `require()`-able
(browser IIFEs with a `typeof module` export guard) and are tested BEHAVIORALLY here.
templates/portfolio.js has no such guard and is DOM-heavy (the house pattern for it,
see tests/test_watchlist_workspace_js.py's `_pf_code()`, is a stripped-source regex
pin) — those items are pinned STRUCTURALLY, on the actual shipped source, with an
explicit "mutation check" naming the exact revert.

This is a NEW suite — force-wired by scripts/audit_unrun_tests.py's gate (unlike the
grandfathered-dark tests/test_market_books_js.py and tests/test_portfolio.py).
"""
from __future__ import annotations

import json
import re
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
PORTFOLIO = ROOT / "templates" / "portfolio.js"


def _pf_code() -> str:
    """portfolio.js with comments stripped (the house pattern for structural pins on
    this DOM-heavy, non-module-exported file — see test_watchlist_workspace_js.py)."""
    src = re.sub(r"/\*.*?\*/", "", PORTFOLIO.read_text(), flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


# ===========================================================================
# node harness — shared with tests/test_watchlist_workspace_js.py &
# tests/test_watchstore_multilist_js.py (mutable id-keyed DOM node stubs, so a
# render pass's writes into a specific element are actually observable)
# ===========================================================================
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
var __nodes = {};
function node(id) {
  if (!__nodes[id]) __nodes[id] = {
    id: id, innerHTML: '', textContent: '', style: {}, className: '',
    _attrs: {},
    classList: { contains: function () { return false; }, toggle: function () {},
                 add: function () {}, remove: function () {} },
    setAttribute: function (k, v) { this._attrs[k] = v; },
    getAttribute: function (k) { return this._attrs[k] != null ? this._attrs[k] : null; },
    querySelector: function (sel) {
      // supports the one shape this suite needs: '[data-count="pf"]' etc.
      var m = /\\[data-count="([a-z]+)"\\]/.exec(sel || '');
      if (m) return node('__count_' + m[1]);
      return null;
    },
    querySelectorAll: function () { return []; },
    addEventListener: function () {},
    value: ''
  };
  return __nodes[id];
}
global.document = {
  readyState: 'loading',
  documentElement: {
    _attrs: {},
    getAttribute: function (k) { return this._attrs[k] != null ? this._attrs[k] : 'en'; },
    setAttribute: function (k, v) { this._attrs[k] = v; },
    classList: { add: function () {}, remove: function () {} }
  },
  getElementById: function (id) { return node(id); },
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
function OUT(o){ process.stdout.write(JSON.stringify(o)); }
"""


def _run(js_body: str, extra: dict | None = None) -> dict:
    globs = "\n".join("var %s = %s;" % (k, json.dumps(v)) for k, v in (extra or {}).items())
    script = SHIM + "\n" + globs + "\n" + textwrap.dedent(js_body)
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


def _wl(js_body: str, extra: dict | None = None) -> dict:
    return _run("var WLT = require(%s);\n%s" % (json.dumps(str(WATCHLIST)), js_body), extra)


def _ws(js_body: str, extra: dict | None = None) -> dict:
    return _run("var WS = require(%s);\n%s" % (json.dumps(str(WATCHSTORE)), js_body), extra)


# A fake Supabase client whose `portfolio_positions` select can be told to fail. Mirrors
# the shape tests/test_watchstore_multilist_js.py's makeDb chain replays, minimal to the
# one query portfolioList() issues: .select('*').eq('user_id', uid).order('created_at').
FAKE_FAILING_DB = """
function makeFailingDb(rowsOnSuccess, failFrom) {
  var calls = 0;
  return {
    client: {
      from: function (table) {
        var api = {
          select: function () { return api; },
          eq: function () { return api; },
          order: function () {
            calls++;
            if (failFrom != null && calls >= failFrom) {
              return Promise.resolve({ data: null, error: { message: 'boom' } });
            }
            return Promise.resolve({ data: (rowsOnSuccess || []).slice(), error: null });
          }
        };
        return api;
      }
    }
  };
}
"""
USER = {"id": "u1"}


# ===========================================================================
# 1. restore population union (market_books.js::buildPortfolioModel)
#    — full behavioral coverage lives in tests/test_market_books_js.py
#      (test_buildPortfolioModel_never_admits_a_watchlist_only_name); referenced
#      here so the ten-item battery is enumerable from one file.
# ===========================================================================
@needs_node
def test_1_population_union_stays_fixed_in_market_books():
    out = _run(
        "var MB = require(%s);"
        "var m = MB.buildPortfolioModel(ROWS, function(){ return 100; });"
        "OUT({present: m.present, hasHK: '0700.HK' in (m.members.hk || {})});"
        % json.dumps(str(MARKET_BOOKS)),
        {"ROWS": [{"ticker": "AAPL", "shares": 1, "entry_price": 1, "status": "open"}]},
    )
    assert out["present"] == ["us"]
    assert out["hasHK"] is False


@needs_node
def test_1b_temporary_basket_carries_the_frozen_label_every_time_it_renders():
    """A1A frozen copy (§11), verbatim: 'Temporary basket — not saved to your
    Portfolio.' Live-browser verification (2026-08-20) caught a real regression here:
    a LEFTOVER duplicate `eyebrow.innerHTML = te('This book', ...)` line further down
    renderAnonBook() silently overwrote the badge-carrying assignment on every non-
    abstaining path (equal/sized weighting) — the abstaining path was unaffected,
    which is why the node suite's abstain-only coverage never caught it. This pins
    the EQUAL-WEIGHTED path specifically, where the duplicate lived.
    MUTATION CHECK: re-add `var eyebrow = el('ws_book_eyebrow'); if (eyebrow)
    eyebrow.innerHTML = te('This book', '这本账簿');` right before `var sub = ...` in
    the non-abstain branch and this reds."""
    out = _wl(
        """
        window.SD = undefined;
        WLT.setMode('portfolio', false);
        node('ws_entry_in').value = 'AAPL, MSFT, NVDA';
        WLT.runEntry();
        OUT({ eyebrow: node('ws_book_eyebrow').innerHTML });
        """
    )
    assert "Temporary basket" in out["eyebrow"]
    assert "not saved to your Portfolio" in out["eyebrow"]


# ===========================================================================
# 2. restore Watchlist count fallback (watchlist.js::pfCount)
# ===========================================================================
@needs_node
def test_2_pfCount_never_falls_back_to_the_watchlist_blob_length():
    """MUTATION CHECK: replace the final `return null;` with `return blob.items.length;`
    (the pre-A1A shape) and this reds — a 5-name Watchlist with window.PF absent must
    read as unavailable (null), never as '5 positions'."""
    out = _wl(
        """
        window.WL.replace({v:1, updated:'2026-08-20T00:00:00.000Z',
          items:[{t:'AAPL',added:'2026-08-20T00:00:00.000Z',note:''},
                 {t:'MSFT',added:'2026-08-20T00:00:00.000Z',note:''},
                 {t:'NVDA',added:'2026-08-20T00:00:00.000Z',note:''},
                 {t:'GOOG',added:'2026-08-20T00:00:00.000Z',note:''},
                 {t:'AMZN',added:'2026-08-20T00:00:00.000Z',note:''}],
          order:['AAPL','MSFT','NVDA','GOOG','AMZN'], settings:{}});
        OUT({count: window.WS.pfCount()});
        """
    )
    assert out["count"] is None


@needs_node
def test_2_pfCount_reads_window_PF_when_present_never_the_watchlist():
    out = _wl(
        """
        window.WL.replace({v:1, updated:'2026-08-20T00:00:00.000Z',
          items:[{t:'AAPL',added:'2026-08-20T00:00:00.000Z',note:''},
                 {t:'MSFT',added:'2026-08-20T00:00:00.000Z',note:''}],
          order:['AAPL','MSFT'], settings:{}});
        window.PF = { count: function () { return 0; } };
        OUT({count: window.WS.pfCount()});
        """
    )
    # 2 Watchlist names, 0 canonical Portfolio positions — the Portfolio count is 0,
    # never 2
    assert out["count"] == 0


# ===========================================================================
# 3. restore the `<2` state branch (portfolio.js::renderBookRead)
# ===========================================================================
def test_3_zero_and_one_position_are_distinct_branches():
    """MUTATION CHECK: collapse the two branches back into `if (open.length < 2) {`
    and this reds — 0 and 1 open positions must be handled by separate `===`
    branches, not one `<2`."""
    code = _pf_code()
    assert "open.length === 0" in code
    assert "open.length === 1" in code
    assert "open.length < 2" not in code


def test_3_one_position_branch_shows_no_relationship_or_cluster_read():
    """The one-position branch must return before any cluster/relationship code runs
    — i.e. it must not fall through into the `leadRows`/`computeWeighting`/`clusterSet`
    machinery below it."""
    code = _pf_code()
    one_branch = code[code.index("if (open.length === 1)"):]
    one_branch = one_branch[:one_branch.index("if (open.length === 1)", 1) if
                             one_branch.count("if (open.length === 1)") > 1 else
                             one_branch.index("var byBook = {}")]
    assert "clusterSet" not in one_branch
    assert "return;" in one_branch


# ===========================================================================
# 4. restore average-filling missing sizes (watchlist.js::weightsOf)
#    — full behavioral coverage lives in tests/test_watchlist_workspace_js.py
#      (test_a_partially_sized_book_abstains_rather_than_average_filling)
# ===========================================================================
@needs_node
def test_4_temp_basket_abstains_on_mixed_sizing_never_average_fills():
    out = _wl("var p = WLT.parseBook('AAPL 60, MSFT 20, NVDA'); OUT(WLT.weightsOf(p, 'pct'));")
    assert out["abstain"] is True
    assert all(i["money"] is None for i in out["items"])


# ===========================================================================
# 5. restore mixed actual/equal fallback in one distribution (portfolio.js
#    ::renderBookRead's `items` construction)
# ===========================================================================
def test_5_canonical_book_read_never_blends_a_computed_value_with_an_equal_fallback():
    """MUTATION CHECK: restore `money: (leadTot > 0 && v != null) ? v / leadTot * 100 :
    100 / byBook[lead]` and this reds — an unsized row used to get an equal-split
    fallback blended into the SAME distribution as rows with a real computed value.
    The fix routes through computeWeighting and only builds `items` when it reports
    `complete === true` (one basis for the whole set)."""
    code = _pf_code()
    assert "100 / byBook[lead]" not in code
    assert "computeWeighting(leadRows" in code
    assert "W.complete !== true" in code
    assert "W.weights[r.ticker]" in code


# ===========================================================================
# 6. restore cloud-to-local fallback (watchstore.js::portfolioList)
# ===========================================================================
@needs_node
def test_6_authenticated_cloud_failure_never_substitutes_the_local_book():
    """MUTATION CHECK: restore `.catch(function (err) { ...; return pfLocalList(); })`
    and this reds — an authenticated visitor whose cloud read fails must never see the
    anonymous local book's rows silently substituted in."""
    out = _ws(
        FAKE_FAILING_DB + """
        // seed a LOCAL row that must NEVER surface once the visitor is authenticated
        var raw = { v: 1, rows: [{id:'loc-1', ticker:'LOCALONLY', shares:1, entry_price:1,
                             entry_date:null, notes:null, status:'open'}] };
        localStorage.setItem('mdash.pf.v1', JSON.stringify(raw));
        var db = makeFailingDb([], 1);   // fails on the very first (and only) call
        WS._setTestSession(USER, db.client);
        WS.portfolio.list().then(function (rows) {
          OUT({ rows: rows, readState: WS.portfolio.readState() });
        });
        """,
        {"USER": USER},
    )
    assert out["rows"] is None                          # explicit unknown, never []
    assert out["readState"]["authority"] == "cloud"
    assert out["readState"]["state"] == "error"
    # LOCALONLY must appear NOWHERE in the answer
    assert "LOCALONLY" not in json.dumps(out)


@needs_node
def test_6_degraded_cloud_read_preserves_last_good_rows_not_local():
    out = _ws(
        FAKE_FAILING_DB + """
        var db = makeFailingDb([{id:'p1', ticker:'AAPL', shares:10, entry_price:100,
                                  entry_date:null, notes:null, status:'open'}], 2);
        WS._setTestSession(USER, db.client);
        WS.portfolio.list().then(function (first) {
          return WS.portfolio.list().then(function (second) {
            OUT({ first: first, second: second, readState: WS.portfolio.readState() });
          });
        });
        """,
        {"USER": USER},
    )
    assert [r["ticker"] for r in out["first"]] == ["AAPL"]
    # the SECOND call fails, but returns the SAME last-good rows, not [] and not null
    assert [r["ticker"] for r in out["second"]] == ["AAPL"]
    assert out["readState"]["state"] == "degraded"
    assert out["readState"]["authority"] == "cloud"
    assert out["readState"]["last_good_at"] is not None


@needs_node
def test_6_authenticated_write_never_silently_routes_local_after_a_read_failure():
    """The specific fork Turn 6 named: a failed READ used to flip `portfolioOk` false,
    and `_isLocalMode()` included `!portfolioOk` — so every WRITE after that first
    failure silently went to the anonymous local book too, for the rest of the
    session. isLocal() must stay false for a signed-in session regardless."""
    out = _ws(
        FAKE_FAILING_DB + """
        var db = makeFailingDb([], 1);
        WS._setTestSession(USER, db.client);
        WS.portfolio.list().then(function () {
          OUT({ isLocal: WS.portfolio.isLocal() });
        });
        """,
        {"USER": USER},
    )
    assert out["isLocal"] is False


def test_6_the_first_load_path_shares_the_same_fix_as_reload():
    """portfolio.js has TWO paths that read WatchStore.portfolio.list() — reload()
    (after a save/remove) and onAuth() (the FIRST load, on init and every 'wl-auth'
    transition). Both must carry the SAME correction; fixing only reload() and
    leaving onAuth() with `rows = newRows || []` would mean the very first paint of a
    degraded/errored authenticated session could never show the read-state banner —
    exactly the gap this test pins.
    MUTATION CHECK: revert onAuth()'s body to `rows = newRows || [];` (dropping the
    readState/dispatchPfSave/`newRows === null` handling) and this reds."""
    code = _pf_code()
    start = code.index("function onAuth()")
    on_auth = code[start:]
    # cut at the NEXT top-level (2-space indented) function declaration — the naive
    # "function " search matches the inner `.then(function (newRows) {` callback first
    on_auth = on_auth[:on_auth.index("\n  function ", 10)]
    assert "rows = newRows || []" not in on_auth
    assert "newRows === null" in on_auth
    assert "readState" in on_auth
    assert "dispatchPfSave" in on_auth


# ===========================================================================
# 7. let Watchlist save drive Portfolio save (watchlist.js chip scope)
# ===========================================================================
@needs_node
def test_7_watchlist_save_state_never_moves_the_portfolio_mode_chip():
    """MUTATION CHECK: revert `setChip` to its pre-A1A single-state shape (no `scope`
    param, one shared `chipState` string) and this reds — a Watchlist sync state would
    then paint the SAME chip the Portfolio tab reads, even though no Portfolio write
    happened. `window.WS.setChip` is exactly what the real `ws-save`/`pf-save`
    listeners call (watchlist.js wires them 1:1 to their scope), so calling it directly
    here exercises the identical function the production event handlers invoke."""
    out = _wl(
        """
        WLT.setMode('portfolio', false);
        window.WS.setChip('saved', 'watchlists');     // simulates a ws-save event
        var afterWl = node('ws_savechip').className;
        window.WS.setChip('saving', 'portfolio');      // simulates a pf-save event
        var afterPf = node('ws_savechip').className;
        OUT({ afterWl: afterWl, afterPf: afterPf });
        """
    )
    # a Watchlist 'saved' state must NOT paint the Portfolio-mode chip as saved
    assert "is-saved" not in out["afterWl"]
    # a Portfolio-scoped state DOES move it
    assert "is-saving" in out["afterPf"]


@needs_node
def test_7_portfolio_save_state_never_moves_the_watchlists_mode_chip():
    out = _wl(
        """
        WLT.setMode('watchlists', false);
        window.WS.setChip('saved', 'portfolio');
        var afterPf = node('ws_savechip').className;
        window.WS.setChip('saving', 'watchlists');
        var afterWl = node('ws_savechip').className;
        OUT({ afterPf: afterPf, afterWl: afterWl });
        """
    )
    assert "is-saved" not in out["afterPf"]
    assert "is-saving" in out["afterWl"]


@needs_node
def test_7_the_ws_save_and_pf_save_listeners_are_wired_to_their_own_scope():
    """Structural backstop for the two tests above: confirms the actual production
    wiring (not just the function `setChip` accepts a scope) routes each event to its
    own scope string, so a future refactor cannot silently reunite them."""
    src = WATCHLIST.read_text()
    assert re.search(r"addEventListener\('ws-save'.*?setChip\([^)]*'watchlists'\)",
                      src, re.S)
    assert re.search(r"addEventListener\('pf-save'.*?setChip\([^)]*'portfolio'\)",
                      src, re.S)


# ===========================================================================
# 8. restore top-half cluster fallback (portfolio.js::renderBookRead)
# ===========================================================================
def test_8_no_source_cluster_means_no_cluster_role_at_all():
    """MUTATION CHECK: restore `: (i < Math.ceil(items.length / 2) ? 'cluster' : '')`
    and this reds — absent a publisher-named cluster, NO row may be marked 'cluster'
    (no role, no bracket, no coloring, no caption)."""
    code = _pf_code()
    assert "Math.ceil(items.length / 2)" not in code
    # the only role assignment left is gated behind an actual clusterSet
    assert "if (clusterSet) {" in code
    idx = code.index("if (clusterSet) {")
    block = code[idx:idx + 400]
    assert "clusterSet[x.sym]" in block


# ===========================================================================
# 9. apply the Portfolio market filter to Watchlists (watchlist.js viewItems/
#    lgViewItems)
# ===========================================================================
@needs_node
def test_9_watchlist_rows_stay_visible_regardless_of_the_active_book():
    """MUTATION CHECK: restore `rows = rows.filter(function (r) { return inBook(r.t);
    });` inside viewItems() and this reds — selecting a book in the Portfolio toolbar
    must never shorten the Watchlist table (§11: 'A1A shows every selected Watchlist
    name')."""
    out = _wl(
        """
        window.MB = {
          getBook: function () { return 'hk'; },       // active book = Hong Kong
          inActive: function (t) { return t.indexOf('.HK') >= 0; },
          marketOf: function () { return 'us'; },
          modeledOnly: function (s) { return s; }
        };
        window.WL.replace({v:1, updated:'2026-08-20T00:00:00.000Z',
          items:[{t:'AAPL',added:'2026-08-20T00:00:00.000Z',note:''},
                 {t:'0700.HK',added:'2026-08-20T00:00:00.000Z',note:''}],
          order:['AAPL','0700.HK'], settings:{}});
        var rows = WLT.viewItems();
        OUT({ syms: rows.map(function (r) { return r.t; }).sort() });
        """
    )
    assert out["syms"] == ["0700.HK", "AAPL"]


@needs_node
def test_9_watchlist_facts_total_is_never_book_filtered():
    out = _wl(
        """
        window.MB = {
          getBook: function () { return 'hk'; }, inActive: function (t) { return t === '0700.HK'; },
          marketOf: function () { return 'us'; }, modeledOnly: function (s) { return s; }
        };
        window.WL.replace({v:1, updated:'2026-08-20T00:00:00.000Z',
          items:[{t:'AAPL',added:'2026-08-20T00:00:00.000Z',note:''},
                 {t:'0700.HK',added:'2026-08-20T00:00:00.000Z',note:''}],
          order:['AAPL','0700.HK'], settings:{}});
        WLT.renderWatchlist();
        OUT({ facts: node('wl_facts').innerHTML });
        """
    )
    assert "2" in out["facts"]


# ===========================================================================
# 10. combine facts across authority modes (local rows shown under cloud
#     authority) — watchstore.js authority law, end to end
# ===========================================================================
@needs_node
def test_10_anonymous_and_authenticated_reads_never_share_one_answer():
    """The authority law (§10) is a hard partition: anonymous always reads the local
    book, authenticated always reads (or explicitly fails on) the cloud book — the two
    must never combine into one fact. MUTATION CHECK: any change that makes
    portfolioList's cloud branch fall through to pfLocalList() on ANY condition other
    than `_isLocalMode()` being true for a genuinely signed-out session reds this."""
    anon = _ws(
        """
        var raw = { v: 1, rows: [{id:'loc-1', ticker:'LOCALNAME', shares:1, entry_price:1,
                             entry_date:null, notes:null, status:'open'}] };
        localStorage.setItem('mdash.pf.v1', JSON.stringify(raw));
        WS.portfolio.list().then(function (rows) {
          OUT({ tickers: rows.map(function (r) { return r.ticker; }),
                readState: WS.portfolio.readState() });
        });
        """
    )
    assert anon["tickers"] == ["LOCALNAME"]
    assert anon["readState"]["authority"] == "local"

    cloud = _ws(
        FAKE_FAILING_DB + """
        var raw = { v: 1, rows: [{id:'loc-1', ticker:'LOCALNAME', shares:1, entry_price:1,
                             entry_date:null, notes:null, status:'open'}] };
        localStorage.setItem('mdash.pf.v1', JSON.stringify(raw));
        var db = makeFailingDb([{id:'p1', ticker:'CLOUDNAME', shares:1, entry_price:1,
                                  entry_date:null, notes:null, status:'open'}], null);
        WS._setTestSession(USER, db.client);
        WS.portfolio.list().then(function (rows) {
          OUT({ tickers: rows.map(function (r) { return r.ticker; }),
                readState: WS.portfolio.readState() });
        });
        """,
        {"USER": USER},
    )
    assert cloud["tickers"] == ["CLOUDNAME"]
    assert cloud["readState"]["authority"] == "cloud"
    # the local book's row never leaks into the authenticated cloud answer
    assert "LOCALNAME" not in cloud["tickers"]
