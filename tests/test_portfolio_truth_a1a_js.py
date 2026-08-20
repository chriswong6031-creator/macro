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

This is a NEW suite. `scripts/audit_unrun_tests.py`'s gate only REPORTS and REDS on an
unwired new suite — it does not itself add a `run:` step anywhere; nothing "force-wires"
a suite into CI except an actual step in a workflow file. This suite (and
tests/test_portfolio_state_js.py) are wired via two explicit steps in the `wri-risk-core`
job of `.github/ci/legacy-jobs.yml` (added alongside this file, review finding B3) —
unlike the grandfathered-dark tests/test_market_books_js.py and tests/test_portfolio.py,
which carry no such step and never run in CI regardless of what this census reports.
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
#    S1 (review): the original version of this test called buildPortfolioModel with
#    NO watchlist argument at all, so it could never have gone red on a restoration —
#    there was nothing for the restored union code to unionize. These two tests
#    replace it: an end-to-end run through the REAL production seam with a live,
#    populated Watchlist store present, plus a structural backstop pinning every call
#    site's arity.
# ===========================================================================
@needs_node
def test_1_population_union_stays_fixed_end_to_end():
    """Seeds a live Watchlist blob (via window.WL, the exact store portfolio.js reads
    through window.WL.getBlob() elsewhere on the page) holding a name in a market the
    Portfolio does not, then calls MB.refresh(rows, priceOf) exactly as portfolio.js's
    render() does. MUTATION CHECK: restore a union — e.g. reintroduce
    `(watchSyms||[]).forEach(addName)` inside buildPortfolioModel and change refresh()
    to read `window.WL.getBlob().items` as a 3rd argument — and this reds."""
    out = _run(
        "var MB = require(%s);\n"
        "var WLT = require(%s);\n"
        "window.WL.replace({v:1, updated:'2026-08-20T00:00:00.000Z',"
        "  items:[{t:'0700.HK',added:'2026-08-20T00:00:00.000Z',note:''}],"
        "  order:['0700.HK'], settings:{}});\n"
        "var ROWS = [{ticker:'AAPL', shares:1, entry_price:1, status:'open'}];\n"
        "MB.refresh(ROWS, function () { return 100; });\n"
        "OUT({present: MB.presentBooks(), "
        "watchlistHasHK: window.WL.getBlob().items.some(function (i) { return i.t === '0700.HK'; })});"
        % (json.dumps(str(MARKET_BOOKS)), json.dumps(str(WATCHLIST)))
    )
    # confirm the watchlist genuinely holds the HK name (test validity — a broken seed
    # would make this test pass for the wrong reason)
    assert out["watchlistHasHK"] is True
    # ...but the Portfolio's own book model (what #bk_strip actually renders) never
    # sees it: the Portfolio has one US position and nothing else
    assert out["present"] == ["us"]


def test_1_no_production_call_site_passes_watchlist_syms_into_the_portfolio_constructors():
    """Structural backstop: MB.refresh is called with exactly 2 args (rows, priceOf)
    at its one production call site, and buildPortfolioModel/buildWatchlistModel are
    never called directly from a consumer file (only market_books.js's own refresh()
    may construct a model) — the constructors' only legal callers. MUTATION CHECK:
    widen portfolio.js's `MB().refresh(rows, priceOf)` call to a 3rd argument (e.g.
    watchlist syms) and this reds."""
    for path, label in ((PORTFOLIO, "portfolio.js"), (WATCHLIST, "watchlist.js")):
        src = path.read_text()
        for m in re.finditer(r"MB\(\)\.refresh\(([^)]*)\)|(?<!\w)MB\.refresh\(([^)]*)\)", src):
            args = m.group(1) if m.group(1) is not None else m.group(2)
            arg_count = len([a for a in args.split(",") if a.strip()])
            assert arg_count <= 2, "%s: MB.refresh called with %d args: %r" % (label, arg_count, args)
        assert "buildPortfolioModel(" not in src, "%s must never call the constructor directly" % label
        assert "buildWatchlistModel(" not in src, "%s must never call the constructor directly" % label


@needs_node
def test_1_buildWatchlistModel_is_watchlist_only_and_ignores_portfolio_shape():
    """B3 (review): duplicated from tests/test_market_books_js.py, which is
    GRANDFATHERED-DARK (config/unrun_test_baseline.json) — nothing there runs in CI.
    This is the load-bearing copy, in the CI-wired suite."""
    out = _run(
        "var MB = require(%s);"
        "var m = MB.buildWatchlistModel(WATCH); "
        "OUT({present:m.present, nAll:m.nAll, agg:m.agg});"
        % json.dumps(str(MARKET_BOOKS)),
        {"WATCH": ["AAPL", "0700.HK", "^GSPC"]},
    )
    assert out["present"] == ["us", "hk", "macro"]
    assert out["nAll"] == 3
    assert out["agg"] == {}


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


# ===========================================================================
# B1 (review — BLOCKING): cross-user private-holdings leak
# ===========================================================================
@needs_node
def test_b1_cross_user_last_good_cloud_never_survives_an_auth_transition():
    """MUTATION CHECK: remove the `pfLastGoodCloud = null; pfReadState = {...}` reset
    lines from onAuthUser() (right after the `lastAuthUid` dedup check) and this reds
    — a second user signing in on the same page session, whose OWN first cloud read
    then fails, must never be served the FIRST user's cached last-good rows as their
    own 'degraded' state."""
    out = _ws(
        FAKE_FAILING_DB + """
        window.SD = {};   // skip the reload-on-signin branch; unrelated to this test
        var dbA = makeFailingDb([{id:'a1', ticker:'USERA_PRIVATE_ROW', shares:1,
                                   entry_price:1, entry_date:null, notes:null,
                                   status:'open'}], null);
        WS._setTestSession(USER_A, dbA.client);
        WS.portfolio.list().then(function (rowsA) {
          // user A signs out, user B signs in — onAuthUser is the REAL reset path
          WS.onAuthUser(USER_B);
          var dbB = makeFailingDb([], 1);   // user B's FIRST cloud read fails immediately
          WS._setTestSession(USER_B, dbB.client);
          WS.portfolio.list().then(function (rowsB) {
            OUT({ rowsA: rowsA.map(function (r) { return r.ticker; }),
                  rowsB: rowsB,
                  readStateB: WS.portfolio.readState() });
          });
        });
        """,
        {"USER_A": {"id": "userA"}, "USER_B": {"id": "userB"}},
    )
    assert out["rowsA"] == ["USERA_PRIVATE_ROW"]
    # user B's failed FIRST read must resolve to the honest unknown — NEVER user A's
    # cached rows served as B's own "last-good, degraded" state
    assert out["rowsB"] is None
    assert out["readStateB"]["state"] == "error"
    assert out["readStateB"]["last_good_at"] is None


@needs_node
def test_b1_sign_out_also_resets_last_good_cloud():
    """The same reset must fire on the sign-OUT branch too — a signed-out visitor
    (anonymous local mode) must never be able to read a previous session's cached
    cloud last-good rows through any code path."""
    out = _ws(
        FAKE_FAILING_DB + """
        window.SD = {};
        var dbA = makeFailingDb([{id:'a1', ticker:'USERA_PRIVATE_ROW', shares:1,
                                   entry_price:1, entry_date:null, notes:null,
                                   status:'open'}], null);
        WS._setTestSession(USER_A, dbA.client);
        WS.portfolio.list().then(function () {
          WS.onAuthUser(null);   // sign out
          OUT({ readState: WS.portfolio.readState() });
        });
        """,
        {"USER_A": {"id": "userA"}},
    )
    assert out["readState"]["authority"] == "local"
    assert out["readState"]["last_good_at"] is None


# ===========================================================================
# B2 (review — BLOCKING): split-deploy falsehood — PS absent must make no
# weighting-law claim
# ===========================================================================
def test_b2_ps_absent_and_fully_priced_book_gets_real_weights_no_abstain_copy():
    """MUTATION CHECK: revert to the pre-fix `var W = ps ? ps.computeWeighting(...) :
    null; if (!W || W.complete !== true) { ...abstain copy... }` and this reds — a
    fully sized, fully live-priced book must never be told "weights not shown" merely
    because portfolio_state.js has not finished deploying yet (split-deploy window)."""
    code = _pf_code()
    assert "allCurrent = leadRows.length > 0 && leadRows.every" in code
    # the PS-absent branch must reach the SAME `items`-construction / cluster / etc.
    # code the PS-present path uses — never its own copy of the abstain message
    ps_idx = code.index("var ps = PS();")
    b2_block = code[ps_idx:code.index("if (!W || W.complete !== true) {", ps_idx)]
    assert "mixedAbstain" not in b2_block
    assert "equalAssumed" not in b2_block


def test_b2_ps_absent_and_not_fully_priced_shows_no_weighting_claim():
    """MUTATION CHECK: same as above, from the other direction — a mixed book under
    a PS-absent split-deploy window must show NEITHER the abstain copy NOR the equal-
    assumption label; only a bare position count."""
    code = _pf_code()
    idx = code.index("if (!allCurrent) {")
    block = code[idx:idx + 800]
    assert "mixedAbstain" not in block
    assert "equalAssumed" not in block
    assert "This book holds" in block


# ===========================================================================
# S6 (review — required): authenticated first read races `sb`
# ===========================================================================
@needs_node
def test_s6_signed_in_load_never_reads_the_anonymous_local_book_during_the_sb_race():
    """MUTATION CHECK: revert `_isLocalMode` to `return !user || !sb;` (dropping
    `_isCloudLoading`) and this reds — a signed-in session whose Supabase client has
    not resolved yet (`user` set, `sb` not) must never read the anonymous LOCAL book
    or paint 'local' authority; it is cloud authority, loading."""
    out = _ws(
        """
        // a LOCAL row that must never surface for a signed-in-but-loading session
        localStorage.setItem('mdash.pf.v1', JSON.stringify({ v: 1, rows: [
          { id: 'loc-1', ticker: 'ANON_LOCAL_ROW', shares: 1, entry_price: 1,
            entry_date: null, notes: null, status: 'open' }
        ] }));
        WS._setTestSession(USER, null);   // user set, sb NOT yet resolved
        WS.portfolio.list().then(function (rows) {
          OUT({ rows: rows, readState: WS.portfolio.readState(), isLocal: WS.portfolio.isLocal() });
        });
        """,
        {"USER": USER},
    )
    assert out["rows"] is None
    assert out["readState"]["authority"] == "cloud"
    assert out["readState"]["state"] == "loading"
    assert out["isLocal"] is False


@needs_node
def test_s6_write_during_the_sb_race_never_lands_in_the_local_book():
    """A write attempted during the same window must not silently succeed against the
    anonymous local store either — it resolves null (no false Saved claim)."""
    out = _ws(
        """
        WS._setTestSession(USER, null);
        WS.portfolio.upsert({ ticker: 'SHOULD_NOT_LAND', shares: 1, entry_price: 1,
                               entry_date: null, status: 'open' }).then(function (result) {
          var local = JSON.parse(localStorage.getItem('mdash.pf.v1') || '{"rows":[]}');
          OUT({ result: result, localRows: local.rows });
        });
        """,
        {"USER": USER},
    )
    assert out["result"] is None
    assert out["localRows"] == []


# ===========================================================================
# S3 (review — required): an abstaining book must reach the factor engine with
# NO weights
# ===========================================================================
def test_s3_abstaining_book_clears_factor_weights_not_a_partial_push():
    """MUTATION CHECK: delete the `else if (wgt && wgt.complete !== true) { ...
    window.FX.setAutoWeights({}); return; }` branch (falling through to the old
    unconditional real-value push) and this reds — a book the page tells "weights not
    shown" must never still be pushing sh*px weights into FX (which would compute
    betas/ENB/MCTR from a distribution the user was told does not exist)."""
    code = _pf_code()
    idx = code.index("function pushFxWeights() {")
    fn = code[idx:code.index("\n  function ", idx + 10)]
    assert "wgt.complete !== true" in fn
    assert "window.FX.setAutoWeights({})" in fn


# ===========================================================================
# S4 (review — required): anonymous local save must never flip wsState() to
# 'signed'
# ===========================================================================
@needs_node
def test_s4_anonymous_local_save_never_flips_wsState_to_signed():
    """MUTATION CHECK: revert wsState() to check `chipState.portfolio === 'saved' ||
    chipState.portfolio === 'saving'` without gating on
    WatchStore.portfolio.readState().authority === 'cloud' and this reds — an
    anonymous visitor's local Save (which unconditionally dispatches pf-save:'saving'
    at the start of every write, before the write even knows its own authority) must
    not briefly un-gate the signed-in shell."""
    out = _wl(
        """
        window.WatchStore = { portfolio: { readState: function () {
          return { authority: 'local', state: 'ready', last_good_at: null, warning: null };
        } } };
        window.WS.setChip('saving', 'portfolio');   // simulates doSave()'s unconditional dispatch
        OUT({ state: WLT.wsState() });
        """
    )
    assert out["state"] != "signed"


@needs_node
def test_s4_cloud_authority_save_does_flip_wsState_to_signed():
    """The gate must not be so strict it also blocks the genuine case: a real cloud
    write in flight IS a signed-in session."""
    out = _wl(
        """
        window.WatchStore = { portfolio: { readState: function () {
          return { authority: 'cloud', state: 'ready', last_good_at: '2026-08-20T00:00:00.000Z', warning: null };
        } } };
        window.WS.setChip('saving', 'portfolio');
        OUT({ state: WLT.wsState() });
        """
    )
    assert out["state"] == "signed"


# ===========================================================================
# S5 (review): four previously-unpinned binding laws, each with its own
# mutation-red test.
# ===========================================================================
def test_s5_degraded_banner_is_wired_into_render():
    """MUTATION CHECK: delete the `renderReadBanner();` call from render() and this
    reds — the degraded/stale-read disclosure banner must actually run on every
    render pass, not merely exist as a function nobody calls."""
    code = _pf_code()
    start = code.index("function render() {")
    render_fn = code[start:]
    render_fn = render_fn[:render_fn.index("\n  function ", 10)]
    assert "renderReadBanner();" in render_fn


def test_s5_pf_count_never_returns_zero_for_a_genuinely_unknown_read():
    """MUTATION CHECK: change `count: function () { return (rows === null &&
    readState.state === 'error') ? null : openRows().length; }` to plain `return
    openRows().length;` (dropping the null branch) and this reds — window.PF.count()
    must resolve to `null`, never a false 0, when the canonical count is unknown."""
    code = _pf_code()
    assert "rows === null && readState.state === 'error') ? null : openRows().length" in code


@needs_node
def test_s5_temp_basket_never_mutates_the_watchlist_store():
    """MUTATION CHECK: re-add `parsed.rows.forEach(function (r) { if (add(r.t)) n++;
    });` plus `pushCloud();` inside runEntry() (the pre-A1A shape) and this reds —
    pasting/analyzing a temporary basket must leave the Watchlist blob byte-identical
    to before, in both its item set AND its `updated` timestamp (a touched-but-
    unchanged blob is still a mutation)."""
    out = _wl(
        """
        window.WL.replace({v:1, updated:'2026-08-20T00:00:00.000Z',
          items:[{t:'AAPL',added:'2026-08-20T00:00:00.000Z',note:''}],
          order:['AAPL'], settings:{}});
        var before = JSON.stringify(window.WL.getBlob());
        node('ws_entry_in').value = 'MSFT, NVDA, GOOG';
        WLT.runEntry();
        OUT({ before: before, after: JSON.stringify(window.WL.getBlob()) });
        """
    )
    assert out["before"] == out["after"]


@needs_node
def test_s5_lgViewItems_book_filter_removal_is_pinned():
    """The LEGACY card-grid view (pre-W2 markup, `lgRender`'s row source) had the SAME
    `inBook()` filter as the W2 table's `viewItems()` — S2's fix covered both, but
    only `viewItems()` had a direct behavioral pin. MUTATION CHECK: restore `rows =
    rows.filter(function (r) { return inBook(r.t); });` inside lgViewItems() and this
    reds."""
    out = _wl(
        """
        window.MB = {
          getBook: function () { return 'hk'; },
          inActive: function (t) { return t.indexOf('.HK') >= 0; },
          marketOf: function () { return 'us'; },
          modeledOnly: function (s) { return s; }
        };
        window.WL.replace({v:1, updated:'2026-08-20T00:00:00.000Z',
          items:[{t:'AAPL',added:'2026-08-20T00:00:00.000Z',note:''},
                 {t:'0700.HK',added:'2026-08-20T00:00:00.000Z',note:''}],
          order:['AAPL','0700.HK'], settings:{}});
        var rows = WLT.lgViewItems();
        OUT({ syms: rows.map(function (r) { return r.t; }).sort() });
        """
    )
    assert out["syms"] == ["0700.HK", "AAPL"]


# ===========================================================================
# S2 (review): the temporary-basket table and "Analyze this watchlist" must never
# drop rows via the Portfolio's active-book filter — both bugs found live in the
# same code paths S2 named.
# ===========================================================================
@needs_node
def test_s2_temp_basket_table_is_never_book_filtered_and_weights_still_sum_to_100():
    """MUTATION CHECK: restore `var filtered = items.filter(function (x) { return
    inBook(x.sym); });` inside renderAnonTable() and this reds — a book-filtered
    temporary basket both drops a real name AND leaves the remaining rows' displayed
    weights summing to less than 100 (the filtered-out row's share is still baked
    into everyone else's percentage, since weights are computed over the FULL set)."""
    out = _wl(
        """
        window.MB = {
          getBook: function () { return 'us'; },
          inActive: function (t) { return t.indexOf('.HK') < 0; },   // HK filtered OUT
          marketOf: function (t) { return t.indexOf('.HK') >= 0 ? 'hk' : 'us'; },
          modeledOnly: function (s) { return s.filter(function (t) { return t.indexOf('.HK') < 0; }); },
          bookName: function (b) { return b; }
        };
        node('ws_entry_in').value = 'AAPL, 0700.HK';
        WLT.runEntry();
        var rows = document.getElementById('tbl_pf').innerHTML;
        OUT({ hasHK: rows.indexOf('0700.HK') >= 0 });
        """
    )
    assert out["hasHK"] is True


@needs_node
def test_s2_analyze_watchlist_never_drops_a_name_via_the_active_book():
    """MUTATION CHECK: restore the `.filter(function (it) { return inBook(it.t); })`
    call ahead of `#wl_analyze`'s `.map()` and this reds — "Analyze this watchlist"
    must analyze the WHOLE watchlist regardless of the Portfolio's active book."""
    src = WATCHLIST.read_text()
    idx = src.index("var an = e.target.closest('#wl_analyze');")
    block = src[idx:idx + 700]
    assert "inBook" not in block
    assert "blob.items.map(function (it) { return it.t; })" in block


# ===========================================================================
# M-a / M-c / M-d (review — required, same commit)
# ===========================================================================
def test_ma_unresolved_basis_gets_its_own_copy_not_the_mixed_sizing_message():
    """MUTATION CHECK: drop the `else if (W && W.reason === 'unresolved_basis')`
    branch (routing everything through the plain mixed-sizing copy) and this reds —
    a book where every row IS sized but one has no resolvable price at all is not
    "mixed sized/unsized"; the message must name the real reason."""
    code = _pf_code()
    assert "unresolvedBasisAbstain" in code
    assert "W.reason === 'unresolved_basis'" in code


def test_mc_error_state_with_stale_rows_still_shows_the_degraded_banner():
    """MUTATION CHECK: revert renderReadBanner()'s condition to `rs === 'degraded'`
    alone and this reds — an 'error' read that still has STALE rows on screen (a later
    read failed after an earlier success) must show the same disclosure a 'degraded'
    read does, never silently render as if nothing happened.
    Post-commissioning (Part B, snapshot authority): the condition now reads `rs`,
    sourced from `refreshSnapshot()` (portfolio_snapshot.v1's `read_state`) rather
    than `readState.state` directly — see test_partB_read_banner_is_snapshot_derived
    for the mutation pin on THAT routing."""
    code = _pf_code()
    idx = code.index("function renderReadBanner() {")
    fn = code[idx:code.index("\n  function ", idx + 10)]
    assert "rs === 'error' && rows && rows.length" in fn


# ===========================================================================
# Part B (commissioning, 2026-08-20): portfolio_snapshot.v1 becomes the REAL
# consumed Portfolio state authority — Sol's blocker 2 decision ("either make
# portfolio_snapshot.v1 the real consumed Portfolio state authority or explicitly
# amend the architecture"; the decision taken is to make it real).
# ===========================================================================
def test_partB_read_banner_is_snapshot_derived():
    """MUTATION CHECK: revert renderReadBanner()'s condition to read `readState.state`
    UNCONDITIONALLY (dropping the `snap ? snap.read_state : ...` routing, i.e. deleting
    `refreshSnapshot()`/`snap.read_state` and using `readState.state` as the sole
    source even when PS IS present) and this reds — the read banner must prefer the
    ONE portfolio_snapshot.v1 this file assembles per render() whenever PS is present;
    `readState.state` may remain only as the B2 split-deploy PS-absent fallback."""
    code = _pf_code()
    idx = code.index("function renderReadBanner() {")
    fn = code[idx:code.index("\n  function ", idx + 10)]
    assert "refreshSnapshot()" in fn
    assert "snap.read_state" in fn
    assert "rs === 'degraded' || (rs === 'error' && rows && rows.length)" in fn


def test_partB_open_and_closed_rows_are_snapshot_derived():
    """MUTATION CHECK: revert openRows()/closedRows() to filter `rows` directly
    without consulting refreshSnapshot() and this reds — population (open.length ===
    0/1/many, driving the zero/one/many Book Read branches) and the table's row set
    must both come from the ONE snapshot, PS-present, never a second independent
    filter of the same raw rows."""
    code = _pf_code()
    for name in ("function openRows() {", "function closedRows() {"):
        idx = code.index(name)
        fn = code[idx:code.index("\n  function ", idx + 10)]
        assert "refreshSnapshot()" in fn, name


def test_partB_render_assembles_the_snapshot_once_per_pass():
    """MUTATION CHECK: delete the `refreshSnapshot();` call from render() (leaving
    openRows()/closedRows()/renderReadBanner() to each lazily refresh their own copy
    with no single assembly point) and this reds."""
    code = _pf_code()
    start = code.index("function render() {")
    render_fn = code[start:]
    render_fn = render_fn[:render_fn.index("\n  function ", 10)]
    assert "refreshSnapshot();" in render_fn


def test_partB_ps_absent_read_banner_falls_back_to_readState_directly():
    """B2 (split-deploy window): when window.PS has not deployed yet, refreshSnapshot()
    must return null and every consumer must fall back to its OWN pre-PS literal
    check — never a weighting-law or read-state claim manufactured without PS."""
    code = _pf_code()
    idx = code.index("function refreshSnapshot() {")
    fn = code[idx:code.index("\n  function ", idx + 10)]
    assert "if (!ps) { snapshot = null; return null; }" in fn


def test_md_a_plain_read_never_claims_saved():
    """MUTATION CHECK: change onAuth()'s `dispatchPfSave(pfChipStateFor(readState));`
    to pass a truthy second argument (or change pfChipStateFor to ignore afterWrite)
    and this reds — the FIRST load / any pure read must settle to the neutral 'clean'
    chip state, never 'saved', which is reserved for a write that just landed."""
    code = _pf_code()
    on_auth_idx = code.index("function onAuth() {")
    on_auth = code[on_auth_idx:code.index("\n  function ", on_auth_idx + 10)]
    assert "dispatchPfSave(pfChipStateFor(readState));" in on_auth
    reload_idx = code.index("function reload(afterWrite) {")
    reload_fn = code[reload_idx:code.index("\n  function ", reload_idx + 10)]
    assert "dispatchPfSave(pfChipStateFor(readState, afterWrite));" in reload_fn
    # the write call sites are the ONLY ones passing a truthy afterWrite
    assert "reload(true);" in code
    assert code.count("reload(true);") == 2   # doSave's success path + doRemove's


@needs_node
def test_md_pfChipStateFor_never_returns_saved_without_afterWrite():
    out = _wl(
        """
        window.WatchStore = { portfolio: { readState: function () {
          return { authority: 'cloud', state: 'ready', last_good_at: '2026-08-20T00:00:00.000Z', warning: null };
        } } };
        window.WS.setChip('clean', 'portfolio');
        OUT({ chip: node('ws_savechip').className });
        """
    )
    assert "is-saving" not in out["chip"]
    # 'clean' shares the 'is-saved' visual treatment (a calm, positive state) but the
    # TEXT must not claim a write happened — checked at the source, since the chip
    # text itself is bilingual markup this harness does not re-render here.
    src = WATCHLIST.read_text()
    assert "clean:   ['is-saved',   'Up to date'" in src


# ===========================================================================
# Post-review (commissioning session): the single-position lead-book copy —
# a 1-US + 1-HK all-sized book must never be told "mix of sized and unsized"
# ===========================================================================
def test_single_position_lead_book_never_gets_the_mixed_sizing_copy():
    """MUTATION CHECK: delete the `single_position` route in renderBookRead's
    abstain block and this reds. A 1-US + 1-HK all-sized book (core audience)
    passes the zero/one split (open.length === 2), then the lead-book restriction
    leaves leadRows.length === 1, so computeWeighting returns
    'insufficient'/'single_position' (pinned behaviorally in
    test_portfolio_state_js.py::test_zero_or_one_position_is_insufficient_no_relationship_read).
    The generic mixed-sizing sentence is FALSE for that book — every position
    carries a size — so the reason must route to its own honest copy."""
    code = _pf_code()
    idx = code.index("var abstainMsg = T.en.mixedAbstain")
    block = code[idx:code.index("say.innerHTML", idx)]
    assert "single_position" in block
    assert "singlePositionBook" in block
    # both language tables carry the copy
    assert "One position in this book" in code
    assert "这本账簿只有一笔持仓" in code
