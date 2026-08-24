"""A1B Portfolio fast-start acceptance over the real browser modules.

The tests node-shell ``portfolio_import.js`` and ``watchstore.js``. They pin the
commissioned grammar, stable identities, N-row atomic batch shape, exact receipt,
lost-response reconciliation, honest terminal failures, auth-generation binding,
local atomicity, and UUID-preserving anonymous-to-cloud fold. No fixture value is
printed by the product code under test.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "templates" / "portfolio_import.js"
UI = ROOT / "templates" / "portfolio_import_ui.js"
WATCHSTORE = ROOT / "templates" / "watchstore.js"
HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

SHIM = r"""
var __sets = [], __store = {}, __throwSet = false;
global.localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; },
  setItem: function (k, v) { if (__throwSet) throw new Error('storage-denied'); __sets.push(k); __store[k] = String(v); },
  removeItem: function (k) { delete __store[k]; }
};
global.sessionStorage = { getItem:function(){return null;}, setItem:function(){}, removeItem:function(){} };
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
global.document = {
  readyState:'loading', hidden:false,
  documentElement:{ getAttribute:function(){return 'en';}, classList:{add:function(){},remove:function(){}} },
  getElementById:function(){return null;}, querySelector:function(){return null;}, querySelectorAll:function(){return [];},
  addEventListener:function(){}, removeEventListener:function(){}, dispatchEvent:function(){return true;},
  createElement:function(){return {style:{},classList:{add:function(){}}};}
};
global.window = global; window.addEventListener = function(){};
global.location = {hash:'',pathname:'/watchlist.html',search:'',origin:'https://x',reload:function(){}};
function OUT(value) { process.stdout.write(JSON.stringify(value)); }
"""


def _node(body: str, *, store: bool = False) -> dict:
    prefix = SHIM + "\nwindow.PortfolioImport = require(%s);\n" % json.dumps(str(CONTRACT))
    if store:
        prefix += "var WS = require(%s);\n" % json.dumps(str(WATCHSTORE))
    proc = subprocess.run(
        ["node", "-e", prefix + textwrap.dedent(body)],
        text=True,
        capture_output=True,
        timeout=40,
    )
    assert proc.returncode == 0, f"node failed:\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}"
    assert proc.stdout.strip(), f"node returned no receipt; stderr={proc.stderr}"
    return json.loads(proc.stdout)


def _ui_node(body: str, *, lang: str = "en") -> dict:
    source = UI.read_text(encoding="utf-8")
    hook = r"""
  window.__PFI_TEST__ = {
    setDraft: function (rows) {
      draft = { rows: JSON.parse(JSON.stringify(rows)), errors: [] };
      editErrors = []; step = 'review'; saving = false; completed = false; hardBlocked = false;
      render();
    },
    editRow: editRow,
    removeRow: removeRow,
    save: save,
    state: function () {
      return {
        draft: JSON.parse(JSON.stringify(draft)), saving: saving,
        completed: completed, hardBlocked: hardBlocked,
        rowsHtml: el('pfi_rows').innerHTML,
        status: el('pfi_status').textContent,
        saveDisabled: !!el('pfi_save').disabled,
        launchDisabled: !!el('pf_import').disabled
      };
    }
  };
"""
    assert source.rstrip().endswith("})();")
    instrumented = source.rstrip()[:-5] + hook + "})();"
    setup = r"""
var __elementIds = [
  'dlg-import','pf_import','pfi_status','pfi_errors','pfi_paste_view','pfi_review_view',
  'pfi_title','pfi_intro','pfi_grammar','pfi_paste','pfi_review','pfi_exact','pfi_back',
  'pfi_rows','pfi_count','pfi_save'
];
function classList() {
  var values={};
  return {add:function(k){values[k]=true;},remove:function(k){delete values[k];},contains:function(k){return !!values[k];}};
}
var __elements={};
__elementIds.forEach(function(id){
  __elements[id]={id:id,style:{},className:'',textContent:'',innerHTML:'',placeholder:'',disabled:false,
    classList:classList(),attributes:{},focus:function(){},querySelector:function(){return null;},
    addEventListener:function(){},setAttribute:function(k,v){this.attributes[k]=String(v);},
    getAttribute:function(k){return Object.prototype.hasOwnProperty.call(this.attributes,k)?this.attributes[k]:null;}};
});
global.document={
  readyState:'loading',activeElement:null,
  documentElement:{getAttribute:function(k){return k==='data-lang'?%s:null;},classList:classList()},
  getElementById:function(id){return __elements[id]||null;},
  addEventListener:function(){},dispatchEvent:function(){return true;}
};
window.document=global.document;
global.setTimeout=function(){return 0;};
eval(%s);
""" % (json.dumps(lang), json.dumps(instrumented))
    return _node(setup + "\n" + textwrap.dedent(body))


IDS = [
    "10000000-0000-4000-8000-000000000001",
    "10000000-0000-4000-8000-000000000002",
    "10000000-0000-4000-8000-000000000003",
    "10000000-0000-4000-8000-000000000004",
]


@needs_node
def test_frozen_grammar_preserves_nulls_coverage_and_duplicate_lots():
    out = _node(
        """
        var ids = %s, i = 0;
        var got = PortfolioImport.parse(
          'aapl\\nAAPL 10\\nMSFT 2 400.25\\n0700.HK 3 300 2026-02-28',
          {idFactory:function(){return ids[i++];}, isCovered:function(t){return t !== 'MSFT';}});
        OUT({rows:got.rows, errors:got.errors, valid:PortfolioImport.validate(got.rows)});
        """ % json.dumps(IDS)
    )
    assert out["errors"] == []
    assert [r["id"] for r in out["rows"]] == IDS
    assert out["rows"][0]["shares"] is None
    assert out["rows"][0]["entry_price"] is None
    assert out["rows"][0]["entry_date"] is None
    assert out["rows"][1]["entry_price"] is None
    assert out["rows"][2]["entry_date"] is None
    assert out["rows"][2]["coverage"] == "uncovered"
    assert "duplicate_ticker" in out["rows"][0]["warnings"]
    assert "duplicate_ticker" in out["rows"][1]["warnings"]
    assert out["valid"]["ok"] is True


@needs_node
def test_malformed_numeric_date_and_unsupported_syntax_stay_visible():
    out = _node(
        """
        var i=0, ids=%s;
        var got=PortfolioImport.parse([
          'GOOD', 'AAPL Infinity', 'MSFT NaN 1', 'NVDA 1 nope',
          'TSLA 1 2 2026-02-30', 'CASH', '$1000 AAPL', 'SPY 10%%',
          'QQQ target=25', 'AMD 1 2 2026-01-01 extra'
        ].join('\\n'), {idFactory:function(){return ids[i++];}});
        OUT({rows:got.rows.map(function(r){return r.ticker;}), codes:got.errors.map(function(e){return e.code;}), lines:got.errors.map(function(e){return e.line;})});
        """ % json.dumps(IDS)
    )
    assert out["rows"] == ["GOOD"]
    assert out["lines"] == list(range(2, 11))
    assert out["codes"] == [
        "invalid_shares", "invalid_shares", "invalid_price", "invalid_date",
        "unsupported_cash", "unsupported_dollar_allocation", "unsupported_percentage",
        "unsupported_target_allocation", "too_many_fields",
    ]


@needs_node
def test_review_edit_keeps_uuid_remove_is_explicit_and_owner_is_forbidden():
    out = _node(
        """
        var id=%s;
        var draft=PortfolioImport.parse('AAPL 1', {idFactory:function(){return id;}}).rows;
        var edited=PortfolioImport.edit(draft,id,{ticker:'msft',shares:'2.5',entry_price:'',entry_date:''});
        var removed=PortfolioImport.remove(edited.rows,id);
        var forbidden=PortfolioImport.validate([Object.assign({}, edited.rows[0], {user_id:'caller-owner'})]);
        OUT({id:edited.rows[0].id,ticker:edited.rows[0].ticker,shares:edited.rows[0].shares,
             price:edited.rows[0].entry_price,date:edited.rows[0].entry_date,
             remaining:removed.rows.length,forbidden:forbidden});
        """ % json.dumps(IDS[0])
    )
    assert out == {
        "id": IDS[0], "ticker": "MSFT", "shares": 2.5, "price": None,
        "date": None, "remaining": 0,
        "forbidden": {"ok": False, "code": "caller_owner_forbidden", "index": 0},
    }


@needs_node
def test_real_uuid_factory_and_finite_scientific_numeric_forms():
    out = _node(
        """
        var ids=[]; for(var i=0;i<32;i++) ids.push(PortfolioImport.randomUuid());
        var seq=0, parsed=PortfolioImport.parse('AAA .5 1e2\\nBBB -3 +4.25',
          {idFactory:function(){return ids[seq++];}});
        OUT({allUuid:ids.every(PortfolioImport.isUuid),unique:(new Set(ids)).size,
             errors:parsed.errors,values:parsed.rows.map(function(r){return [r.shares,r.entry_price];})});
        """
    )
    assert out["allUuid"] is True and out["unique"] == 32
    assert out["errors"] == [] and out["values"] == [[0.5, 100], [-3, 4.25]]


LOCAL_BATCH = [
    {"id": IDS[0], "ticker": "AAPL", "shares": None, "entry_price": None,
     "entry_date": None, "notes": None, "status": "open"},
    {"id": IDS[1], "ticker": "AAPL", "shares": None, "entry_price": None,
     "entry_date": None, "notes": None, "status": "open"},
]


@needs_node
def test_local_import_is_one_complete_book_write_and_keeps_duplicates():
    out = _node(
        """
        var before=[{id:'loc-old',ticker:'OLD',shares:1,entry_price:null,entry_date:null,notes:null,status:'open'}];
        WS.pfWrite(before); __sets=[];
        WS.portfolio.importBatch(%s).then(function(result){
          return WS.portfolio.list().then(function(rows){
            OUT({result:result.state,ok:result.ok,writes:__sets.length,ids:rows.map(function(r){return r.id;}),tickers:rows.map(function(r){return r.ticker;})});
          });
        });
        """ % json.dumps(LOCAL_BATCH),
        store=True,
    )
    assert out["ok"] is True and out["result"] == "saved"
    assert out["writes"] == 1
    assert out["ids"] == ["loc-old", IDS[0], IDS[1]]
    assert out["tickers"] == ["OLD", "AAPL", "AAPL"]


@needs_node
def test_local_storage_throw_preserves_previous_book_byte_for_byte():
    out = _node(
        """
        var before=JSON.stringify({v:1,rows:[{id:'loc-old',ticker:'OLD',shares:1,entry_price:null,entry_date:null,notes:null,status:'open'}]});
        __store['mdash.pf.v1']=before; __throwSet=true;
        WS.portfolio.importBatch(%s).then(function(result){
          OUT({ok:result.ok,state:result.state,unchanged:__store['mdash.pf.v1']===before});
        });
        """ % json.dumps(LOCAL_BATCH),
        store=True,
    )
    assert out == {"ok": False, "state": "local_write_failed", "unchanged": True}


@needs_node
def test_local_write_success_with_hostile_verify_mismatch_is_terminal_unknown_without_rollback():
    out = _node(
        """
        var key='mdash.pf.v1';
        var before=JSON.stringify({v:1,rows:[{id:'loc-old',ticker:'OLD',shares:1,entry_price:null,entry_date:null,notes:null,status:'open'}]});
        __store[key]=before;
        var wrote=false, actualGet=localStorage.getItem, actualSet=localStorage.setItem;
        localStorage.setItem=function(k,v){ actualSet(k,v); if(k===key) wrote=true; };
        localStorage.getItem=function(k){
          if(k===key && wrote) return before;
          return actualGet(k);
        };
        WS.portfolio.importBatch(%s).then(function(result){
          OUT({ok:result.ok,state:result.state,effect:result.effect,retryable:result.retryable,
               writeHappened:wrote,writes:__sets.length,storedChanged:__store[key]!==before});
        });
        """ % json.dumps(LOCAL_BATCH),
        store=True,
    )
    assert out == {
        "ok": False,
        "state": "local_verify_failed",
        "effect": "unknown",
        "retryable": False,
        "writeHappened": True,
        "writes": 1,
        "storedChanged": True,
    }


@needs_node
def test_inflight_save_freezes_model_visible_draft_and_exact_payload():
    out = _ui_node(
        """
        var rows=%s.map(function(row){return Object.assign({},row,{coverage:'covered',warnings:[]});});
        var resolveSave, captured=null, editCalls=0, removeCalls=0;
        var realEdit=PortfolioImport.edit, realRemove=PortfolioImport.remove;
        PortfolioImport.edit=function(){editCalls++;return realEdit.apply(null,arguments);};
        PortfolioImport.remove=function(){removeCalls++;return realRemove.apply(null,arguments);};
        var pending=new Promise(function(resolve){resolveSave=resolve;});
        window.WatchStore={portfolio:{importBatch:function(batch){captured=JSON.parse(JSON.stringify(batch));return pending;}}};
        __PFI_TEST__.setDraft(rows);
        var before=__PFI_TEST__.state();
        __PFI_TEST__.save();
        var locked=__PFI_TEST__.state();
        var rowHost={getAttribute:function(){return rows[0].id;}};
        __PFI_TEST__.editRow({value:'MSFT',closest:function(){return rowHost;},getAttribute:function(k){return k==='data-pfi-field'?'ticker':null;}});
        __PFI_TEST__.removeRow(rows[0].id);
        var attacked=__PFI_TEST__.state();
        resolveSave({ok:true,state:'saved',rows:captured});
        Promise.resolve().then(function(){return Promise.resolve();}).then(function(){
          var done=__PFI_TEST__.state();
          OUT({
            inputsLocked:(locked.rowsHtml.match(/<input[^>]* disabled/g)||[]).length,
            removesLocked:(locked.rowsHtml.match(/<button[^>]*data-pfi-remove[^>]* disabled/g)||[]).length,
            modelFrozen:JSON.stringify(before.draft)===JSON.stringify(attacked.draft),
            visibleFrozen:locked.rowsHtml===attacked.rowsHtml,
            exactPayload:JSON.stringify(captured)===JSON.stringify(before.draft.rows),
            editCalls:editCalls,removeCalls:removeCalls,
            completed:done.completed,saveDisabled:done.saveDisabled,
            finalVisibleFrozen:done.rowsHtml===locked.rowsHtml,status:done.status
          });
        });
        """ % json.dumps(LOCAL_BATCH)
    )
    assert out == {
        "inputsLocked": 8,
        "removesLocked": 2,
        "modelFrozen": True,
        "visibleFrozen": True,
        "exactPayload": True,
        "editCalls": 0,
        "removeCalls": 0,
        "completed": True,
        "saveDisabled": True,
        "finalVisibleFrozen": True,
        "status": "Saved. Refreshing your Portfolio…",
    }


@needs_node
@pytest.mark.parametrize(
    ("lang", "message"),
    [
        ("en", "This browser wrote the book, but could not verify the resulting Portfolio. Do not retry here. Reopen Portfolio and verify it before doing anything else."),
        ("zh", "本浏览器已写入账簿，但无法核实保存后的持仓状态。请勿在此重试；先重新打开持仓并核对，再进行其他操作。"),
    ],
)
def test_local_verify_failed_is_hard_blocked_with_honest_en_zh_copy(lang: str, message: str):
    out = _ui_node(
        """
        var rows=%s.map(function(row){return Object.assign({},row,{coverage:'covered',warnings:[]});});
        window.WatchStore={portfolio:{importBatch:function(){return Promise.resolve({ok:false,state:'local_verify_failed',effect:'unknown',retryable:false});}}};
        __PFI_TEST__.setDraft(rows); __PFI_TEST__.save();
        Promise.resolve().then(function(){return Promise.resolve();}).then(function(){OUT(__PFI_TEST__.state());});
        """ % json.dumps(LOCAL_BATCH),
        lang=lang,
    )
    assert out["hardBlocked"] is True
    assert out["saveDisabled"] is True and out["launchDisabled"] is True
    assert out["status"] == message
    assert out["rowsHtml"].count('disabled aria-disabled="true"') == 10


CLOUD_HELPER = r"""
function makeClient(mode, initial) {
  var state=(initial||[]).map(function(r){return Object.assign({},r);}), inserts=[], tables=[];
  function from(table) {
    tables.push(table);
    var action='select', payload=null, filters={}, ids=null, selected='';
    var q={
      select:function(s){selected=s;return q;}, eq:function(k,v){filters[k]=v;return q;},
      in:function(k,v){ids=v.slice();return q;}, order:function(){return q;},
      insert:function(rows){action='insert';payload=rows.map(function(r){return Object.assign({},r);});return q;},
      then:function(resolve,reject){
        Promise.resolve().then(function(){
          if(action==='select'){
            var data=state.filter(function(r){
              return (!filters.user_id || r.user_id===filters.user_id) && (!ids || ids.indexOf(r.id)>=0);
            }).map(function(r){return Object.assign({},r);});
            if(mode==='reread_fail' && inserts.length && !ids) return {data:null,error:{code:'READ_DOWN'}};
            if(mode==='preflight_down' && !inserts.length && ids) return {data:null,error:{code:'READ_DOWN'}};
            if(mode==='lost_reconcile_down' && inserts.length && ids) return {data:null,error:{code:'RECONCILE_DOWN'}};
            return {data:data,error:null};
          }
          inserts.push(payload.map(function(r){return Object.assign({},r);}));
          if(mode==='rejected') return {data:null,error:{code:'CHECK_REJECTED'}};
          if(mode==='auth_flip') { state=state.concat(payload); WS.onAuthUser(null); return {data:payload,error:null}; }
          if(mode==='lost_zero_once' && inserts.length===1) throw new Error('response-lost');
          if(mode==='lost_zero_always') throw new Error('response-lost');
          if(mode==='lost_partial_apply') { state=state.concat(payload.slice(0,1)); throw new Error('response-lost'); }
          if(mode==='lost_reconcile_down') { state=state.concat(payload); throw new Error('response-lost'); }
          state=state.concat(payload);
          if(mode==='lost_apply') throw new Error('response-lost');
          if(mode==='partial_receipt') return {data:payload.slice(0,1),error:null};
          if(mode==='wrong_owner_receipt') return {data:payload.map(function(r){return Object.assign({},r,{user_id:'owner-b'});}),error:null};
          return {data:payload.map(function(r){return Object.assign({},r);}),error:null};
        }).then(resolve,reject);
      }
    }; return q;
  }
  return {from:from,state:function(){return state.slice();},inserts:inserts,tables:tables};
}
function runCloud(mode, initial, batch) {
  var client=makeClient(mode,initial||[]);
  WS._setTestSession({id:'owner-a',email:'a@test'},client,false);
  return WS.portfolio.list().then(function(){
    return WS.portfolio.importBatch(batch).then(function(result){
      return {result:result,calls:client.inserts,state:client.state(),tables:client.tables};
    });
  });
}
"""


def _cloud(mode: str, initial: list[dict] | None = None, batch: list[dict] | None = None) -> dict:
    return _node(
        CLOUD_HELPER + "\nrunCloud(%s,%s,%s).then(OUT);" % (
            json.dumps(mode), json.dumps(initial or []), json.dumps(batch or LOCAL_BATCH)
        ),
        store=True,
    )


@needs_node
def test_cloud_save_is_one_n_row_insert_with_session_owner_and_exact_reread():
    out = _cloud("exact")
    assert out["result"]["ok"] is True and out["result"]["state"] == "saved"
    assert len(out["calls"]) == 1 and len(out["calls"][0]) == 2
    assert {r["user_id"] for r in out["calls"][0]} == {"owner-a"}
    assert [r["id"] for r in out["calls"][0]] == IDS[:2]
    assert all("updated_at" not in r for r in out["calls"][0])
    assert out["tables"] and set(out["tables"]) == {"portfolio_positions"}


@needs_node
def test_lost_response_all_exact_reconciles_without_second_insert():
    out = _cloud("lost_apply")
    assert out["result"]["ok"] is True
    assert len(out["calls"]) == 1
    assert len(out["state"]) == 2


@needs_node
def test_lost_response_zero_retries_once_with_identical_ids():
    out = _cloud("lost_zero_once")
    assert out["result"]["ok"] is True
    assert len(out["calls"]) == 2
    assert [r["id"] for r in out["calls"][0]] == [r["id"] for r in out["calls"][1]] == IDS[:2]
    assert len(out["state"]) == 2


@needs_node
def test_partial_existing_batch_stops_before_insert_mutation_check():
    existing = [dict(LOCAL_BATCH[0], user_id="owner-a")]
    out = _cloud("exact", existing)
    assert out["result"]["ok"] is False and out["result"]["state"] == "some"
    assert out["calls"] == []


@needs_node
def test_same_id_different_semantics_is_a_conflict_before_insert():
    existing = [dict(LOCAL_BATCH[0], user_id="owner-a", shares=999)]
    out = _cloud("exact", existing, [LOCAL_BATCH[0]])
    assert out["result"]["ok"] is False and out["result"]["state"] == "conflict"
    assert out["calls"] == []


@needs_node
def test_partial_receipt_never_claims_saved_or_blind_retries_mutation_check():
    out = _cloud("partial_receipt")
    assert out["result"]["ok"] is False
    assert out["result"]["state"] == "ambiguous_receipt"
    assert len(out["calls"]) == 1


@needs_node
def test_wrong_owner_receipt_never_claims_saved_even_if_owner_read_is_exact():
    out = _cloud("wrong_owner_receipt")
    assert out["result"]["ok"] is False
    assert out["result"]["state"] == "ambiguous_receipt"
    assert len(out["calls"]) == 1


@needs_node
def test_lost_response_partial_reconcile_stops_without_retry():
    out = _cloud("lost_partial_apply")
    assert out["result"]["ok"] is False and out["result"]["state"] == "some"
    assert len(out["calls"]) == 1 and len(out["state"]) == 1


@needs_node
def test_lost_response_unavailable_reconcile_is_effect_unknown_and_no_retry():
    out = _cloud("lost_reconcile_down")
    assert out["result"]["ok"] is False and out["result"]["state"] == "effect_unknown"
    assert out["result"]["retryable"] is False and len(out["calls"]) == 1


@needs_node
def test_unavailable_preflight_is_known_zero_effect_and_retryable():
    out = _cloud("preflight_down")
    assert out["result"] == {
        "ok": False,
        "state": "unavailable",
        "effect": "none",
        "retryable": True,
    }
    assert out["calls"] == []


@needs_node
def test_second_lost_response_after_proven_zero_stops_effect_unknown():
    out = _cloud("lost_zero_always")
    assert out["result"]["ok"] is False and out["result"]["state"] == "effect_unknown"
    assert out["result"]["retryable"] is False and len(out["calls"]) == 2
    assert out["state"] == []


@needs_node
def test_definite_rejection_is_zero_effect_and_retryable_same_draft():
    out = _cloud("rejected")
    assert out["result"]["ok"] is False and out["result"]["state"] == "rejected"
    assert out["state"] == [] and len(out["calls"]) == 1


@needs_node
def test_acknowledged_write_without_authoritative_reread_is_not_saved():
    out = _cloud("reread_fail")
    assert out["result"]["ok"] is False
    assert out["result"]["state"] == "authoritative_reread_failed"
    assert out["result"]["effect"] == "confirmed"
    assert len(out["state"]) == 2


@needs_node
def test_auth_generation_change_suppresses_success_and_never_changes_owner():
    out = _cloud("auth_flip")
    assert out["result"]["ok"] is False and out["result"]["state"] == "stale_auth"
    assert {r["user_id"] for r in out["calls"][0]} == {"owner-a"}


@needs_node
def test_uuid_fold_preserves_two_exact_duplicate_lots_and_is_idempotent():
    out = _node(
        CLOUD_HELPER + """
        var batch=%s, client=makeClient('exact',[]);
        __store['mdash.pf.v1']=JSON.stringify({v:1,rows:batch});
        WS._setTestSession({id:'owner-a',email:'a@test'},client,false);
        WS.portfolio.list().then(function(){ return WS.foldLocalPortfolio(); }).then(function(){
          return WS.foldLocalPortfolio();
        }).then(function(){
          OUT({calls:client.inserts.length,ids:client.state().map(function(r){return r.id;}),
               tickers:client.state().map(function(r){return r.ticker;}),local:__store['mdash.pf.v1']||null,
               marker:__store['mdash.watchstore.pf_folded.v1']||null});
        });
        """ % json.dumps(LOCAL_BATCH),
        store=True,
    )
    assert out["calls"] == 1
    assert out["ids"] == IDS[:2]
    assert out["tickers"] == ["AAPL", "AAPL"]
    assert out["local"] is None and out["marker"] == "1"


def test_page_wires_pure_contract_before_store_and_ui_after_portfolio():
    page = (ROOT / "templates" / "watchlist.html.j2").read_text(encoding="utf-8")
    assert 'id="pf_import"' in page and 'id="dlg-import"' in page
    assert 'src="watchstore.js?v=11"' in page and 'src="portfolio.js?v=10"' in page
    assert 'src="portfolio_import_ui.js?v=2"' in page
    assert page.index('src="portfolio_import.js') < page.index('src="watchstore.js')
    assert page.index('src="portfolio.js') < page.index('src="portfolio_import_ui.js')
    ui = (ROOT / "templates" / "portfolio_import_ui.js").read_text(encoding="utf-8")
    assert "WatchStore.lists" not in ui and "WatchStore.symbols" not in ui


def test_ui_async_review_and_terminal_retry_guards_stay_pinned_mutation_check():
    ui = (ROOT / "templates" / "portfolio_import_ui.js").read_text(encoding="utf-8")
    disabled = "if (button) { button.disabled = true; button.textContent = L('reviewing'); }"
    reenabled = "if (button) button.disabled = false;"
    assert disabled in ui and reenabled in ui
    assert ui.index(disabled) < ui.index(reenabled)
    assert "if (saving || completed || hardBlocked" in ui
    assert "el('pf_import').disabled = true" in ui


def test_narrow_modal_owns_the_viewport_over_the_brain_launcher():
    css = (ROOT / "templates" / "portfolio_import.css").read_text(encoding="utf-8")
    assert "html.mx5-dlg-lock #mmb-boot { visibility:hidden; }" in css


def test_import_assets_have_shipping_site_pairs():
    for name in ("portfolio_import.css", "portfolio_import.js", "portfolio_import_ui.js", "watchstore.js", "portfolio.js"):
        assert (ROOT / "site" / name).read_bytes() == (ROOT / "templates" / name).read_bytes()
    assert (ROOT / "site" / "watchlist.html").is_file()
