"""tests/test_watchstore_multilist_js.py — the registered multi-list store seam (W1a).

`templates/watchstore.js` used to hold ONE implicit target: a single `wlId` resolved by
"whichever list sorts first" plus a single global `cloudSet`. Under multi-list that shape
is a data-loss machine, because the push is a FULL-MEMBERSHIP diff — it deletes cloud rows
that are absent locally. This file pins the properties that make it safe:

  1. List CRUD is isolated: symbol ops name their list, and an op on list A leaves list B
     byte-identical.
  2. The one-shot local->cloud fold retargets to the list NAMED 'Watchlist' (created if
     absent), and running it twice yields identical state — the marker is written only on
     success and never on an empty local book (both shipped behaviours kept).
  3. NAMED REGRESSION: with two lists, a stale cache of list A can never delete rows of
     list B. Every delete is scoped by `.eq('watchlist_id', <list being pushed>)` and its
     candidate symbols come only from that list's SERVER read — a localStorage cache is a
     render hint, never a delete authority.
  4. The four semantic invariants A-D from the commissioning packet's §0, run against the
     store layer: watchlist writes never touch `portfolio_positions` and vice versa.

Same harness as tests/test_watchlist_books_js.py: the module is a browser IIFE, node-shelled
behind minimal window/document/localStorage stubs with readyState 'loading' so init() never
runs and only the store logic is exercised.
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
WATCHLIST = ROOT / "templates" / "watchlist.js"

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
function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
"""

# ---------------------------------------------------------------------------
# A recording Supabase double.
#
# It models the two tables as real row arrays and REPLAYS the query builder, so a
# delete that forgets its watchlist_id filter genuinely removes the other list's rows
# instead of being caught by an assertion about intent. Every call is also logged in
# `db.ops` so a test can assert on the SHAPE of the statement, not just its effect.
# ---------------------------------------------------------------------------
FAKE_DB = """
function makeDb(seed) {
  var db = {
    tables: {
      watchlists: (seed && seed.watchlists || []).slice(),
      watchlist_symbols: (seed && seed.watchlist_symbols || []).slice(),
      portfolio_positions: (seed && seed.portfolio_positions || []).slice()
    },
    ops: [],
    seq: 0
  };
  function matches(row, filters) {
    return filters.every(function (f) {
      if (f.op === 'eq') return String(row[f.col]) === String(f.val);
      if (f.op === 'in') return f.val.map(String).indexOf(String(row[f.col])) >= 0;
      return true;
    });
  }
  db.client = {
    from: function (table) {
      var filters = [];
      var op = { table: table, filters: filters };
      var api = {
        eq: function (c, v) { filters.push({ op: 'eq', col: c, val: v }); return api; },
        in: function (c, v) { filters.push({ op: 'in', col: c, val: v }); return api; },
        limit: function () { return api; },
        order: function () { return api; },
        single: function () { api.__single = true; return api; },
        select: function (cols) {
          if (op.kind === 'insert' || op.kind === 'update') { op.returning = cols; return api; }
          op.kind = 'select'; db.ops.push(op);
          return api;
        },
        insert: function (rows) {
          op.kind = 'insert';
          op.rows = Array.isArray(rows) ? rows : [rows];
          db.ops.push(op);
          var inserted = op.rows.map(function (r) {
            var row = {};
            Object.keys(r).forEach(function (k) { row[k] = r[k]; });
            if (!row.id) row.id = table + '-' + (++db.seq);
            if (!row.created_at) row.created_at = '2026-08-01T00:00:0' + (db.seq % 10) + '.000Z';
            return row;
          });
          // honour the schema's unique (user_id, name) index on watchlists
          if (table === 'watchlists') {
            var clash = inserted.some(function (r) {
              return db.tables.watchlists.some(function (x) {
                return String(x.user_id) === String(r.user_id) && x.name === r.name;
              });
            });
            if (clash) { op.rejected = '23505'; return api; }
          }
          inserted.forEach(function (r) { db.tables[table].push(r); });
          op.inserted = inserted;
          return api;
        },
        update: function (patch) {
          op.kind = 'update'; op.patch = patch; db.ops.push(op); return api;
        },
        delete: function () { op.kind = 'delete'; db.ops.push(op); return api; },
        then: function (res, rej) { return api.__run().then(res, rej); },
        catch: function (f) { return api.__run().catch(f); },
        __run: function () {
          if (api.__ran) return api.__ran;
          api.__ran = Promise.resolve().then(function () {
            var rows = db.tables[table];
            if (op.kind === 'select') {
              var hit = rows.filter(function (r) { return matches(r, filters); });
              return { data: api.__single ? (hit[0] || null) : hit, error: null };
            }
            if (op.kind === 'insert') {
              if (op.rejected) {
                return { data: null,
                         error: { code: '23505', message: 'duplicate key value' } };
              }
              return { data: api.__single ? op.inserted[0] : op.inserted, error: null };
            }
            if (op.kind === 'update') {
              var upd = [];
              rows.forEach(function (r) {
                if (!matches(r, filters)) return;
                Object.keys(op.patch).forEach(function (k) { r[k] = op.patch[k]; });
                upd.push(r);
              });
              op.affected = upd.length;
              return { data: api.__single ? (upd[0] || null) : upd, error: null };
            }
            if (op.kind === 'delete') {
              var kept = [], gone = [];
              rows.forEach(function (r) { (matches(r, filters) ? gone : kept).push(r); });
              db.tables[table] = kept;
              op.deleted = gone;
              return { data: gone, error: null };
            }
            return { data: [], error: null };
          });
          return api.__ran;
        }
      };
      return api;
    }
  };
  return db;
}
function symbolsOf(db, listId) {
  return db.tables.watchlist_symbols
    .filter(function (r) { return String(r.watchlist_id) === String(listId); })
    .map(function (r) { return r.symbol; }).sort();
}
"""

USER = {"id": "u1"}


def _run(js_body: str, extra: dict | None = None) -> dict:
    globs = "\n".join("var %s = %s;" % (k, json.dumps(v)) for k, v in (extra or {}).items())
    script = SHIM + "\n" + FAKE_DB + "\n" + globs + "\n" + textwrap.dedent(js_body)
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


def _ws(js_body: str, extra: dict | None = None) -> dict:
    return _run("var WS = require(%s);\n%s" % (json.dumps(str(WATCHSTORE)), js_body), extra)


def _wl(js_body: str, extra: dict | None = None) -> dict:
    return _run("var WLT = require(%s);\n%s" % (json.dumps(str(WATCHLIST)), js_body), extra)


# two registered lists belonging to the same owner
TWO_LISTS = {
    "watchlists": [
        {"id": "L-AI", "user_id": "u1", "name": "AI", "position": 0},
        {"id": "L-GOLD", "user_id": "u1", "name": "Gold Miners", "position": 1},
    ],
    "watchlist_symbols": [
        {"id": "s1", "watchlist_id": "L-AI", "symbol": "NVDA", "position": 0},
        {"id": "s2", "watchlist_id": "L-AI", "symbol": "AVGO", "position": 1},
        {"id": "s3", "watchlist_id": "L-GOLD", "symbol": "NEM", "position": 0},
        {"id": "s4", "watchlist_id": "L-GOLD", "symbol": "AEM", "position": 1},
    ],
}


# ===========================================================================
# 1. multi-list CRUD isolation
# ===========================================================================
@needs_node
def test_list_crud_create_rename_delete_round_trip():
    out = _ws(
        """
        var db = makeDb({watchlists: [], watchlist_symbols: []});
        WS._setTestSession(USER, db.client);
        WS.lists.create('Gold Miners').then(function (a) {
          return WS.lists.create('Space').then(function (b) {
            return WS.lists.rename(b.id, 'Space Economy').then(function (r) {
              return WS.lists.remove(a.id).then(function () {
                return WS.lists.refresh().then(function (all) {
                  OUT({created: [a.name, b.name], renamed: r.name,
                       positions: [a.position, b.position],
                       left: all.map(function (l) { return l.name; })});
                });
              });
            });
          });
        });
        """,
        {"USER": USER},
    )
    assert out["created"] == ["Gold Miners", "Space"]
    assert out["positions"] == [0, 1]          # position is assigned, not collided
    assert out["renamed"] == "Space Economy"
    assert out["left"] == ["Space Economy"]    # the deleted list is gone, the other kept


@needs_node
def test_duplicate_list_name_adopts_the_existing_row_instead_of_failing():
    """The schema carries a unique (user_id, name) index. Two tabs (or Macro and the
    Terminal) racing the same create must converge on ONE list, not blow up the caller."""
    out = _ws(
        """
        var db = makeDb({watchlists: [{id: 'L1', user_id: 'u1', name: 'AI', position: 0}]});
        WS._setTestSession(USER, db.client);
        WS.lists.create('AI').then(function (row) {
          OUT({id: row && row.id, rows: db.tables.watchlists.length});
        }, function (e) { OUT({err: String(e)}); });
        """,
        {"USER": USER},
    )
    assert out["id"] == "L1"     # adopted the existing row
    assert out["rows"] == 1      # and did NOT create a second one


@needs_node
def test_symbol_ops_are_isolated_between_lists():
    """Invariant: an add/remove on list A leaves list B byte-identical."""
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        var before = symbolsOf(db, 'L-GOLD');
        WS.symbols.list('L-AI').then(function () {
          return WS.symbols.add('L-AI', 'GOOGL').then(function () {
            return WS.symbols.remove('L-AI', 'AVGO').then(function () {
              OUT({ai: symbolsOf(db, 'L-AI'),
                   goldBefore: before, goldAfter: symbolsOf(db, 'L-GOLD')});
            });
          });
        });
        """,
        {"USER": USER, "SEED": TWO_LISTS},
    )
    assert out["ai"] == ["GOOGL", "NVDA"]
    assert out["goldAfter"] == out["goldBefore"] == ["AEM", "NEM"]


@needs_node
def test_per_list_caches_use_distinct_keys_and_do_not_bleed():
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        WS.symbols.list('L-AI').then(function () {
          return WS.symbols.list('L-GOLD').then(function () {
            OUT({keys: [WS.cacheKey('L-AI'), WS.cacheKey('L-GOLD')],
                 ai: WS.cacheRead('L-AI').order,
                 gold: WS.cacheRead('L-GOLD').order,
                 stored: Object.keys(__store).filter(function (k) {
                   return k.indexOf('mdash.wl.') === 0; }).sort()});
          });
        });
        """,
        {"USER": USER, "SEED": TWO_LISTS},
    )
    assert out["keys"] == ["mdash.wl.L-AI.v1", "mdash.wl.L-GOLD.v1"]
    assert out["ai"] == ["NVDA", "AVGO"]
    assert out["gold"] == ["NEM", "AEM"]
    assert out["stored"] == ["mdash.wl.L-AI.v1", "mdash.wl.L-GOLD.v1"]
    # the anonymous store is not one of them
    assert "mdash.watchlist.v1" not in out["stored"]


@needs_node
def test_a_cache_write_preserves_local_notes_that_the_schema_cannot_hold():
    """Notes stay local by ruling — `watchlist_symbols` has no note column. A sync must
    therefore never erase a note the user typed against a symbol that is still present."""
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        localStorage.setItem('mdash.wl.L-AI.v1', JSON.stringify({
          v: 1, updated: '2026-08-01T00:00:00.000Z',
          items: [{t: 'NVDA', added: '2026-07-01T00:00:00.000Z', note: 'core position'}],
          order: ['NVDA'], settings: {sort: 'order'}
        }));
        WS.symbols.list('L-AI').then(function () {
          var c = WS.cacheRead('L-AI');
          var nvda = c.items.filter(function (i) { return i.t === 'NVDA'; })[0];
          OUT({note: nvda && nvda.note, added: nvda && nvda.added,
               order: c.order, settings: c.settings});
        });
        """,
        {"USER": USER, "SEED": TWO_LISTS},
    )
    assert out["note"] == "core position"
    assert out["added"] == "2026-07-01T00:00:00.000Z"
    assert out["order"] == ["NVDA", "AVGO"]
    assert out["settings"] == {"sort": "order"}


# ===========================================================================
# 2. fold retarget + run-twice idempotency
# ===========================================================================
LOCAL_BLOB = {
    "v": 1,
    "updated": "2026-08-01T00:00:00.000Z",
    "items": [{"t": "AAPL", "added": "2026-07-01T00:00:00.000Z", "note": ""},
              {"t": "MSFT", "added": "2026-07-02T00:00:00.000Z", "note": ""}],
    "order": ["AAPL", "MSFT"],
    "settings": {},
}

# stub the WL seam the fold reads its local book from
WL_STUB = """
function installWL(blob) {
  global.window.WL = {
    getBlob: function () { return blob; },
    merge: function () { return 0; }
  };
}
"""


@needs_node
def test_fold_targets_the_list_named_watchlist_not_whatever_sorts_first():
    """The retarget this wave ships. The account's FIRST list is 'Default' (the Terminal
    seeds one); the previous `.order(position).limit(1)` resolution folded the visitor's
    local book into it. The fold now lands in the list NAMED 'Watchlist' — created if
    absent — and 'Default' is left exactly as it was (server-only lists are kept)."""
    out = _ws(
        WL_STUB + """
        installWL(BLOB);
        var db = makeDb({watchlists: [{id: 'L-DEF', user_id: 'u1', name: 'Default', position: 0}],
                         watchlist_symbols: [
                           {id: 'd1', watchlist_id: 'L-DEF', symbol: 'SPY', position: 0}]});
        WS._setTestSession(USER, db.client);
        WS.pull().then(function () {
          var st = WS._testState();
          var created = db.tables.watchlists.filter(function (l) { return l.name === 'Watchlist'; })[0];
          OUT({primaryName: (db.tables.watchlists.filter(function (l) {
                 return String(l.id) === String(st.primaryId); })[0] || {}).name,
               createdWatchlist: !!created,
               defaultUntouched: symbolsOf(db, 'L-DEF'),
               folded: created ? symbolsOf(db, created.id) : null,
               marker: localStorage.getItem('mdash.watchstore.folded.v1')});
        });
        """,
        {"USER": USER, "BLOB": LOCAL_BLOB},
    )
    assert out["primaryName"] == "Watchlist"
    assert out["createdWatchlist"] is True
    assert out["defaultUntouched"] == ["SPY"]      # the pre-existing list is not touched
    assert out["folded"] == ["AAPL", "MSFT"]
    assert out["marker"] == "1"


@needs_node
def test_fold_retarget_is_a_no_op_for_an_account_macro_itself_created():
    """The shipped auto-create already NAMED that first list 'Watchlist' — so for the
    common (Macro-only) account the retarget resolves to the identical row."""
    out = _ws(
        WL_STUB + """
        installWL(BLOB);
        var db = makeDb({watchlists: [{id: 'L-W', user_id: 'u1', name: 'Watchlist', position: 0}],
                         watchlist_symbols: []});
        WS._setTestSession(USER, db.client);
        WS.pull().then(function () {
          OUT({primaryId: WS._testState().primaryId,
               listRows: db.tables.watchlists.length,
               folded: symbolsOf(db, 'L-W')});
        });
        """,
        {"USER": USER, "BLOB": LOCAL_BLOB},
    )
    assert out["primaryId"] == "L-W"    # adopted, not re-created
    assert out["listRows"] == 1
    assert out["folded"] == ["AAPL", "MSFT"]


@needs_node
def test_fold_run_twice_yields_identical_state():
    """The packet's run-twice gate. A second pull (re-login, tab focus, second device
    session) must plan nothing: identical rows, identical list set, no duplicates."""
    out = _ws(
        WL_STUB + """
        installWL(BLOB);
        var db = makeDb({watchlists: [], watchlist_symbols: []});
        WS._setTestSession(USER, db.client);
        function snapshot() {
          return JSON.stringify({
            lists: db.tables.watchlists.map(function (l) { return [l.name, l.position]; }).sort(),
            syms: db.tables.watchlist_symbols.map(function (r) {
              return [r.watchlist_id, r.symbol]; }).sort()
          });
        }
        WS.pull().then(function () {
          var first = snapshot();
          var insertsAfterFirst = db.ops.filter(function (o) { return o.kind === 'insert'; }).length;
          return WS.pull().then(function () {
            OUT({first: first, second: snapshot(),
                 symbolRows: db.tables.watchlist_symbols.length,
                 listRows: db.tables.watchlists.length,
                 extraInserts: db.ops.filter(function (o) {
                   return o.kind === 'insert'; }).length - insertsAfterFirst});
          });
        });
        """,
        {"USER": USER, "BLOB": LOCAL_BLOB},
    )
    assert out["first"] == out["second"]   # identical state, byte for byte
    assert out["symbolRows"] == 2          # AAPL + MSFT once
    assert out["listRows"] == 1            # 'Watchlist' created once
    assert out["extraInserts"] == 0        # the second pass writes nothing at all


@needs_node
def test_fold_does_not_consume_the_one_shot_on_an_empty_local_book():
    """Kept behaviour: signing in on a fresh device must not burn the one-shot, or a
    book built later never folds."""
    out = _ws(
        WL_STUB + """
        installWL({v: 1, updated: '', items: [], order: [], settings: {}});
        var db = makeDb({watchlists: [], watchlist_symbols: []});
        WS._setTestSession(USER, db.client);
        WS.pull().then(function () {
          OUT({marker: localStorage.getItem('mdash.watchstore.folded.v1'),
               symbolRows: db.tables.watchlist_symbols.length});
        });
        """,
        {"USER": USER},
    )
    assert out["marker"] is None
    assert out["symbolRows"] == 0


@needs_node
def test_fold_is_not_marked_when_the_insert_fails_so_it_retries():
    """Kept behaviour: marking a FAILED fold as done silently discards the visitor's
    whole list. Reproduced here by making the symbol insert error."""
    out = _ws(
        WL_STUB + """
        installWL(BLOB);
        var db = makeDb({watchlists: [{id: 'L-W', user_id: 'u1', name: 'Watchlist', position: 0}],
                         watchlist_symbols: []});
        var realFrom = db.client.from;
        db.client.from = function (table) {
          var api = realFrom(table);
          if (table === 'watchlist_symbols') {
            var realInsert = api.insert;
            api.insert = function (rows) {
              realInsert(rows);
              return { then: function (f) { return Promise.resolve(f({error: {message: 'rls denied'}})); },
                       catch: function () { return Promise.resolve(); } };
            };
          }
          return api;
        };
        WS._setTestSession(USER, db.client);
        WS.pull().then(function () {
          OUT({marker: localStorage.getItem('mdash.watchstore.folded.v1')});
        });
        """,
        {"USER": USER, "BLOB": LOCAL_BLOB},
    )
    assert out["marker"] is None


# ===========================================================================
# 3. NAMED REGRESSION — a stale cache of list A can never delete rows of list B
# ===========================================================================
@needs_node
def test_stale_cache_of_one_list_can_never_delete_another_lists_rows():
    """THE regression this wave exists to prevent.

    Setup is the worst realistic case: a stale localStorage cache for list A claims
    symbols that list B also holds, and the user then edits list B down to nothing.
    The push must delete exactly B's own rows and leave A untouched — and every delete
    statement must carry `.eq('watchlist_id', <B>)`.

    The Supabase double replays filters against real row arrays, so an unscoped delete
    would genuinely remove A's rows here rather than merely failing an assertion."""
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        // a stale cache for list A that even claims list B's symbols
        localStorage.setItem('mdash.wl.L-AI.v1', JSON.stringify({
          v: 1, updated: '2026-01-01T00:00:00.000Z',
          items: [{t: 'NVDA'}, {t: 'AVGO'}, {t: 'NEM'}, {t: 'AEM'}],
          order: ['NVDA', 'AVGO', 'NEM', 'AEM'], settings: {}
        }));
        // read ONLY list B, then push an empty membership at it
        WS.symbols.list('L-GOLD').then(function () {
          return WS.symbols.push('L-GOLD', []).then(function (r) {
            var deletes = db.ops.filter(function (o) { return o.kind === 'delete'; });
            OUT({
              result: r,
              ai: symbolsOf(db, 'L-AI'),
              gold: symbolsOf(db, 'L-GOLD'),
              deleteScopes: deletes.map(function (o) {
                var eq = o.filters.filter(function (f) {
                  return f.op === 'eq' && f.col === 'watchlist_id'; });
                return {table: o.table, scoped: eq.map(function (f) { return f.val; }),
                        symbols: (o.filters.filter(function (f) {
                          return f.op === 'in' && f.col === 'symbol'; })[0] || {}).val};
              })
            });
          });
        });
        """,
        {"USER": USER, "SEED": TWO_LISTS},
    )
    assert out["ai"] == ["AVGO", "NVDA"], "list A lost rows to list B's push"
    assert out["gold"] == []
    assert out["result"] == {"inserted": 0, "deleted": 2}
    assert len(out["deleteScopes"]) == 1
    scope = out["deleteScopes"][0]
    assert scope["table"] == "watchlist_symbols"
    assert scope["scoped"] == ["L-GOLD"], "delete was not scoped to the list being pushed"
    assert sorted(scope["symbols"]) == ["AEM", "NEM"], "delete reached beyond list B's rows"


@needs_node
def test_a_list_that_was_never_read_is_never_diffed():
    """No server read means no delete authority. A push at an unread list is a no-op
    rather than "everything in the cloud is absent locally, delete it all"."""
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        localStorage.setItem('mdash.wl.L-AI.v1', JSON.stringify({
          v: 1, items: [{t: 'NVDA'}], order: ['NVDA'], settings: {}}));
        WS.symbols.push('L-AI', []).then(function (r) {
          OUT({result: r, ai: symbolsOf(db, 'L-AI'),
               deletes: db.ops.filter(function (o) { return o.kind === 'delete'; }).length});
        });
        """,
        {"USER": USER, "SEED": TWO_LISTS},
    )
    assert out["result"] is None
    assert out["ai"] == ["AVGO", "NVDA"]   # untouched
    assert out["deletes"] == 0


@needs_node
def test_switching_the_active_list_never_pushes_the_old_blob_at_the_new_list():
    """A switch that carried the previous list's membership across would be the
    full-diff wipe wearing a different hat."""
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        WS.symbols.list('L-AI').then(function () {
          return WS.lists.setActive('L-GOLD').then(function () {
            OUT({active: WS.lists.activeId(),
                 ai: symbolsOf(db, 'L-AI'), gold: symbolsOf(db, 'L-GOLD'),
                 writes: db.ops.filter(function (o) {
                   return o.kind === 'insert' || o.kind === 'delete'; }).length});
          });
        });
        """,
        {"USER": USER, "SEED": TWO_LISTS},
    )
    assert out["active"] == "L-GOLD"
    assert out["ai"] == ["AVGO", "NVDA"]
    assert out["gold"] == ["AEM", "NEM"]
    assert out["writes"] == 0


@needs_node
def test_push_carries_its_target_through_the_debounce():
    """The blob is bound to a list at ENQUEUE time. Before this wave the target was read
    from a module global at FIRE time, so a switch inside the 600ms window redirected the
    push at the wrong list. Two lists are also debounced independently — a push to B must
    not cancel a pending push to A."""
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        Promise.all([WS.symbols.list('L-AI'), WS.symbols.list('L-GOLD')]).then(function () {
          WS.lists.setActive('L-AI');
          // enqueue against A, then immediately switch the active list to B
          window.WLCloud.push({items: [{t: 'NVDA'}]}, 'L-AI');
          window.WLCloud.push({items: [{t: 'NEM'}, {t: 'AEM'}, {t: 'GOLD'}]}, 'L-GOLD');
          return WS.lists.setActive('L-GOLD').then(function () {
            return wait(900).then(function () {
              OUT({ai: symbolsOf(db, 'L-AI'), gold: symbolsOf(db, 'L-GOLD')});
            });
          });
        });
        """,
        {"USER": USER, "SEED": TWO_LISTS},
    )
    # A's push (drop AVGO) landed on A; B's push (add GOLD) landed on B. Neither cancelled
    # the other, and neither was redirected by the active-list switch.
    assert out["ai"] == ["NVDA"]
    assert out["gold"] == ["AEM", "GOLD", "NEM"]


# ===========================================================================
# 4. semantic invariants A-D (commissioning packet §0)
# ===========================================================================
BOTH_POPULATIONS = {
    "watchlists": [{"id": "L-AI", "user_id": "u1", "name": "AI", "position": 0}],
    "watchlist_symbols": [
        {"id": "s1", "watchlist_id": "L-AI", "symbol": "NVDA", "position": 0},
    ],
    "portfolio_positions": [
        {"id": "p1", "user_id": "u1", "ticker": "NVDA", "shares": 10,
         "entry_price": 100, "entry_date": "2026-01-01", "notes": None, "status": "open"},
    ],
}


def _pf(db_expr: str = "db") -> str:
    return ("%s.tables.portfolio_positions.map(function (r) { "
            "return [r.ticker, r.status]; })" % db_expr)


@needs_node
def test_invariant_A_adding_to_a_watchlist_leaves_portfolio_positions_unchanged():
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        var before = JSON.stringify(%s);
        WS.symbols.list('L-AI').then(function () {
          return WS.symbols.add('L-AI', 'AAPL').then(function () {
            OUT({before: before, after: JSON.stringify(%s),
                 watchlist: symbolsOf(db, 'L-AI')});
          });
        });
        """ % (_pf(), _pf()),
        {"USER": USER, "SEED": BOTH_POPULATIONS},
    )
    assert out["watchlist"] == ["AAPL", "NVDA"]
    assert out["before"] == out["after"]


@needs_node
def test_invariant_B_adding_a_portfolio_position_changes_no_watchlist_row():
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        var before = JSON.stringify(symbolsOf(db, 'L-AI'));
        WS.portfolio.upsert({ticker: 'MSFT', shares: 5, entry_price: 400,
                             entry_date: '2026-03-01', status: 'open'}).then(function () {
          OUT({before: before, after: JSON.stringify(symbolsOf(db, 'L-AI')),
               portfolio: %s});
        });
        """ % _pf(),
        {"USER": USER, "SEED": BOTH_POPULATIONS},
    )
    assert out["before"] == out["after"] == '["NVDA"]'
    assert sorted(out["portfolio"]) == [["MSFT", "open"], ["NVDA", "open"]]


@needs_node
def test_invariant_C_removing_from_a_watchlist_keeps_the_portfolio_position():
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        WS.symbols.list('L-AI').then(function () {
          return WS.symbols.remove('L-AI', 'NVDA').then(function () {
            OUT({watchlist: symbolsOf(db, 'L-AI'), portfolio: %s});
          });
        });
        """ % _pf(),
        {"USER": USER, "SEED": BOTH_POPULATIONS},
    )
    assert out["watchlist"] == []
    assert out["portfolio"] == [["NVDA", "open"]]   # the held position survives


@needs_node
def test_invariant_D_closing_a_portfolio_position_keeps_watchlist_membership():
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        WS.portfolio.close('p1').then(function () {
          OUT({watchlist: symbolsOf(db, 'L-AI'), portfolio: %s});
        });
        """ % _pf(),
        {"USER": USER, "SEED": BOTH_POPULATIONS},
    )
    assert out["portfolio"] == [["NVDA", "closed"]]
    assert out["watchlist"] == ["NVDA"]             # attention set is unaffected


@needs_node
def test_a_full_membership_push_never_reaches_portfolio_positions():
    """The diff's delete is the sharpest edge in the module; it must be structurally
    unable to address the other population's table at all."""
    out = _ws(
        """
        var db = makeDb(SEED);
        WS._setTestSession(USER, db.client);
        WS.symbols.list('L-AI').then(function () {
          return WS.symbols.push('L-AI', []).then(function () {
            OUT({tables: db.ops.filter(function (o) { return o.kind === 'delete'; })
                   .map(function (o) { return o.table; }),
                 portfolio: %s});
          });
        });
        """ % _pf(),
        {"USER": USER, "SEED": BOTH_POPULATIONS},
    )
    assert out["tables"] == ["watchlist_symbols"]
    assert out["portfolio"] == [["NVDA", "open"]]


# ===========================================================================
# 5. anonymous / signed-out behaviour is untouched
# ===========================================================================
@needs_node
def test_signed_out_multi_list_calls_are_inert_and_write_nothing():
    out = _ws(
        """
        var errs = [];
        function guard(p) { return p.then(function () { return 'resolved'; },
                                          function (e) { return String(e.message || e); }); }
        Promise.all([
          guard(WS.lists.create('X')),
          guard(WS.lists.refresh()),
          guard(WS.symbols.list('L-AI')),
          guard(WS.symbols.push('L-AI', ['NVDA']))
        ]).then(function (r) {
          OUT({results: r, wrote: __sets.filter(function (k) {
            return k.indexOf('mdash.wl.') === 0; }).length});
        });
        """
    )
    assert out["results"][:3] == ["no-session", "no-session", "no-session"]
    assert out["results"][3] == "resolved"   # push is a silent no-op, never an error
    assert out["wrote"] == 0                 # no per-list cache is created while signed out


@needs_node
def test_watchlist_js_default_binding_uses_the_anonymous_key_verbatim():
    """`mdash.watchlist.v1` stays the anonymous store: same key, same probe key, same
    unscoped `#wl=` share fragment. Signed-out behaviour is byte-identical."""
    out = _wl(
        """
        OUT({key: window.WL.storageKey(), listId: window.WL.listId(),
             share: window.WL.shareParam()});
        """
    )
    assert out["key"] == "mdash.watchlist.v1"
    assert out["listId"] is None
    assert out["share"] == "wl"


@needs_node
def test_watchlist_js_rebind_switches_key_and_share_scope_without_carrying_state():
    """The three W2.5 seams, exercised. A rebind re-reads from the new list's own cache
    — it must not carry the previous list's items across, which under a full-membership
    diff push would wipe the list being switched to."""
    out = _wl(
        """
        localStorage.setItem('mdash.watchlist.v1', JSON.stringify({
          v: 1, updated: '2026-08-01T00:00:00.000Z',
          items: [{t: 'AAPL', added: '2026-07-01T00:00:00.000Z', note: ''}],
          order: ['AAPL'], settings: {}}));
        localStorage.setItem('mdash.wl.L-AI.v1', JSON.stringify({
          v: 1, updated: '2026-08-02T00:00:00.000Z',
          items: [{t: 'NVDA', added: '2026-07-02T00:00:00.000Z', note: ''}],
          order: ['NVDA'], settings: {}}));
        var anon = window.WL.getBlob().items.map(function (i) { return i.t; });
        window.WL.bindList('L-AI', 'AI');
        var bound = {key: window.WL.storageKey(), share: window.WL.shareParam(),
                     items: window.WL.getBlob().items.map(function (i) { return i.t; })};
        window.WL.bindList(null);
        OUT({anon: anon, bound: bound,
             back: {key: window.WL.storageKey(),
                    items: window.WL.getBlob().items.map(function (i) { return i.t; })}});
        """
    )
    assert out["anon"] == []                      # nothing read yet — init() never ran
    assert out["bound"]["key"] == "mdash.wl.L-AI.v1"
    assert out["bound"]["share"] == "wl.AI"       # share fragment is list-scoped
    assert out["bound"]["items"] == ["NVDA"]      # read from the LIST's cache
    assert out["back"]["key"] == "mdash.watchlist.v1"
    assert out["back"]["items"] == ["AAPL"]       # and back to the anonymous store


@needs_node
def test_a_scoped_share_link_is_not_consumed_by_a_different_list():
    """`#wl.<name>=` is only consumed by the list it was exported from; a bare `#wl=`
    link stays unscoped so every link already in the wild keeps working."""
    out = _wl(
        """
        var payload = Buffer.from(JSON.stringify({
          v: 1, updated: '2026-08-01T00:00:00.000Z',
          items: [{t: 'RKLB', added: '2026-07-01T00:00:00.000Z', note: ''}],
          order: ['RKLB'], settings: {}}), 'utf8').toString('base64');
        function hashFor(h, bind, name) {
          global.location.hash = h;
          global.history = {replaceState: function () { global.location.hash = ''; }};
          window.WL.bindList(bind, name);
          WLT.consumeShareHash();
          return window.WL.getBlob().items.map(function (i) { return i.t; });
        }
        OUT({wrongList: hashFor('#wl.Space=' + payload, 'L-AI', 'AI'),
             rightList: hashFor('#wl.Space=' + payload, 'L-SP', 'Space'),
             legacyBare: hashFor('#wl=' + payload, null, '')});
        """
    )
    assert out["wrongList"] == []                 # left alone, not merged into 'AI'
    assert out["rightList"] == ["RKLB"]           # consumed by its own list
    assert out["legacyBare"] == ["RKLB"]          # unscoped legacy link still works
