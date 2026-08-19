"""Flagship UI contracts for Government Revenue Foresight."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from scripts import build_government_revenue

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates" / "government_revenue.html.j2").read_text(encoding="utf-8")
BRIEFCASE = (ROOT / "templates" / "government-revenue-briefcase.js").read_text(encoding="utf-8")
BRIEFCASE_UI = (ROOT / "templates" / "government-revenue-briefcase-ui.js").read_text(encoding="utf-8")
CANDIDATE_RADAR = (ROOT / "templates" / "government-revenue-candidate-radar.js").read_text(encoding="utf-8")
CANDIDATE_RADAR_SITE = (ROOT / "site" / "government-revenue-candidate-radar.js").read_text(encoding="utf-8")
SITE_PATH = ROOT / "site" / "government_revenue.html"
SITE = SITE_PATH.read_text(encoding="utf-8")
WORKSPACE_PATH = ROOT / "site" / "government-revenue-data" / "workspace.json"
HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")


def _page_runtime_js() -> str:
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", TEMPLATE, re.S)
    runtime = next((block for block in blocks if "__hydrateGovernmentWorkspace" in block), None)
    assert runtime is not None, "Government Revenue page runtime is missing"
    return runtime


def _run_runtime(
    tmp_path: Path,
    payload: dict,
    full_workspace: dict,
    now_ms: int,
    candidate_rows: list[dict] | None = None,
    mapping_backlog_total: int = 0,
    mapping_backlog_tickers: list[str] | None = None,
    mapping_backlog_states: dict[str, str] | None = None,
    exact_candidate_availability: str = "available",
    candidate_status: str = "ok",
    fetch_status: int = 200,
    ticker_routes: list[str] | None = None,
    location_search: str = "",
    lang: str = "en",
) -> dict:
    """Run the page's real IIFE against a deliberately tiny browser DOM stub."""
    page_runtime = _page_runtime_js()
    script = textwrap.dedent(
        """
        var PAYLOAD = %(payload)s;
        var FULL_WORKSPACE = %(full_workspace)s;
        var NOW_MS = %(now_ms)s;
        var CANDIDATE_ROWS = %(candidate_rows)s;
        var CANDIDATE_BACKLOG = %(candidate_backlog)s;
        var CANDIDATE_BACKLOG_TICKERS = %(candidate_backlog_tickers)s;
        var CANDIDATE_BACKLOG_STATES = %(candidate_backlog_states)s;
        var EXACT_CANDIDATE_AVAILABILITY = %(exact_candidate_availability)s;
        var CANDIDATE_STATUS = %(candidate_status)s;
        var FETCH_STATUS = %(fetch_status)s;
        var TICKER_ROUTES = %(ticker_routes)s;
        var LOCATION_SEARCH = %(location_search)s;
        var LANG = %(lang)s;
        var fetchCalls = 0;
        function makeElement(){
          var listeners = {};
          var classes = new Set();
          return {
            textContent:'', innerHTML:'', hidden:false, disabled:false, value:'', className:'', tabIndex:0,
            dataset:{}, style:{},
            addEventListener:function(name, fn){(listeners[name]=listeners[name]||[]).push(fn)},
            fire:function(name, event){(listeners[name]||[]).forEach(function(fn){fn.call(this,event||{target:this})},this)},
            setAttribute:function(name,value){this[name]=String(value)},
            getAttribute:function(name){return this[name] == null ? null : String(this[name])},
            querySelectorAll:function(){return[]}, querySelector:function(){return null}, closest:function(){return null},
            focus:function(){}, blur:function(){},
            classList:{add:function(){},remove:function(){},toggle:function(){},contains:function(){return false}}
          };
        }
        var nodeStore = {};
        function node(id){if(!nodeStore[id])nodeStore[id]=makeElement();return nodeStore[id]}
        node('gov-data').textContent = JSON.stringify(PAYLOAD);
        node('workspaceDegraded').hidden = true;
        node('workspaceRetry').hidden = true;
        node('workspaceUnlock').hidden = true;
        var docListeners = {};
        var document = {
          documentElement:{getAttribute:function(name){return name==='data-lang'?LANG:'en'}}, activeElement:null,
          getElementById:node, querySelectorAll:function(){return[]},
          addEventListener:function(name, fn){(docListeners[name]=docListeners[name]||[]).push(fn)},
          dispatchEvent:function(){return true}
        };
        var location = {href:'https://example.test/government_revenue.html'+LOCATION_SEARCH, pathname:'/government_revenue.html', search:LOCATION_SEARCH, hash:''};
        var history = {replaceState:function(){}};
        var navigator = {clipboard:null};
        var window = {location:location, history:history, navigator:navigator, innerWidth:1440};
        if(CANDIDATE_ROWS!==null)window.createGovernmentRevenueCandidateRadar=function(api){return {
          load:function(){api.onRows(CANDIDATE_ROWS,{status:CANDIDATE_STATUS,total:CANDIDATE_ROWS.length,mapping_backlog_total:CANDIDATE_BACKLOG,mapping_backlog_tickers:CANDIDATE_BACKLOG_TICKERS,mapping_backlog_states:CANDIDATE_BACKLOG_STATES,freshness:{exact_candidate_availability:EXACT_CANDIDATE_AVAILABILITY}});return Promise.resolve(CANDIDATE_ROWS)},
          refresh:function(){return this.load()}, render:function(){}, invalidate:function(){}, state:function(){return 'ok'}, crosschecks:function(){return ''}
        }};
        var fetch = function(){fetchCalls += 1; return Promise.resolve({ok:FETCH_STATUS >= 200 && FETCH_STATUS < 300,status:FETCH_STATUS,json:function(){return Promise.resolve(FULL_WORKSPACE)}})};
        function CustomEvent(name, init){this.type=name;this.detail=init&&init.detail}
        %(page_runtime)s
        function bannerSnapshot(){
          return {hidden:node('workspaceDegraded').hidden, copy:node('workspaceDegradedCopy').textContent,
                  retryHidden:node('workspaceRetry').hidden, unlockHidden:node('workspaceUnlock').hidden,
                  state:node('workspaceDegraded').dataset.state || null};
        }
        setTimeout(function(){
          var initial = bannerSnapshot();
          node('workspaceRetry').fire('click');
          setTimeout(function(){
            var runtime = window.__governmentRevenueRuntime;
            var freshness = runtime.effectiveFreshnessState(PAYLOAD, PAYLOAD.procurement_workspace, NOW_MS);
            var tickerStates=TICKER_ROUTES===null?null:TICKER_ROUTES.map(function(ticker){return runtime.tickerRailState(ticker)});
            var tickerRoutes=TICKER_ROUTES===null?null:TICKER_ROUTES.map(function(ticker){return runtime.openTickerFilmstrip(ticker)});
            var afterRetry = bannerSnapshot();
            // Everything below is language-sensitive, so snapshot it BEFORE the
            // langchange re-render swaps the whole desk into Chinese.
            var result = {initial:initial, afterRetry:afterRetry,
              fetchCalls:fetchCalls, freshness:freshness,
              bundlesMatch:runtime.workspaceBundleMatches(PAYLOAD.procurement_workspace, FULL_WORKSPACE),
              rows:runtime.workspaceRows(), tickerStates:tickerStates, tickerRoutes:tickerRoutes,
              selection:runtime.currentSelection(), inspectorHtml:node('inspector').innerHTML,
              queueHtml:node('queueList').innerHTML, queueSummary:node('queueSummary').textContent,
              filmstripHtml:node('companyFilmstrip').innerHTML,
              agencyFilterHtml:node('agencyFilter').innerHTML,
              agencyNames:runtime.agencyNames(),
              workspaceComplete:runtime.workspaceIsComplete(PAYLOAD.procurement_workspace)};
            LANG = 'zh';
            var langError = null;
            try { (docListeners['langchange']||[]).forEach(function(fn){fn({type:'langchange'})}); }
            catch (e) { langError = String(e && e.message || e); }
            result.afterLangChange = bannerSnapshot();
            result.afterLangChange.error = langError;
            result.zhFilmstripHtml = node('companyFilmstrip').innerHTML;
            process.stdout.write(JSON.stringify(result));
          }, 8);
        }, 8);
        """
    ) % {
        "payload": json.dumps(payload),
        "full_workspace": json.dumps(full_workspace),
        "now_ms": now_ms,
        "candidate_rows": json.dumps(candidate_rows) if candidate_rows is not None else "null",
        "candidate_backlog": json.dumps(mapping_backlog_total),
        "candidate_backlog_tickers": json.dumps(mapping_backlog_tickers or []),
        "candidate_backlog_states": json.dumps(mapping_backlog_states or {}),
        "exact_candidate_availability": json.dumps(exact_candidate_availability),
        "candidate_status": json.dumps(candidate_status),
        "fetch_status": json.dumps(fetch_status),
        "ticker_routes": json.dumps(ticker_routes) if ticker_routes is not None else "null",
        "location_search": json.dumps(location_search),
        "lang": json.dumps(lang),
        "page_runtime": page_runtime,
    }
    path = tmp_path / "government_revenue_runtime.js"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"node failed:\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"
    assert result.stdout.strip(), f"runtime emitted no result; stderr:\n{result.stderr}"
    return json.loads(result.stdout)


def test_uses_one_shared_product_nav_and_one_elevated_workspace() -> None:
    assert TEMPLATE.count('{% include "_site_nav.html.j2" %}') == 1
    assert '<nav class="site-nav">' not in TEMPLATE
    assert TEMPLATE.count('class="gr-shell"') == 1
    assert SITE.count('<nav class="site-nav">') == 1


def test_delta_first_three_pane_contract_and_modes_are_explicit() -> None:
    assert "grid-template-columns:216px minmax(520px,.95fr) minmax(410px,.75fr)" in TEMPLATE
    assert 'data-mode="changes"' in TEMPLATE
    assert 'data-mode="awards"' in TEMPLATE
    assert 'data-mode="opportunities"' in TEMPLATE
    assert 'data-mode="recompetes"' in TEMPLATE
    assert 'data-mode="budget"' in TEMPLATE
    assert 'id="countBudget"' in TEMPLATE
    assert "state.mode='companies'" in TEMPLATE
    assert "payload.opportunity_intelligence" not in TEMPLATE  # JSON is accessed as DATA.
    assert "DATA.opportunity_intelligence" in TEMPLATE
    assert "DATA.procurement_workspace" in TEMPLATE
    assert r"government_procurement_workspace\.v[12]" in TEMPLATE
    assert "government_procurement_workspace.v2" in TEMPLATE
    assert "WORKSPACE_EVENTS.map" in TEMPLATE
    assert "workspaceEvent:e" in TEMPLATE
    assert "governed display order" in TEMPLATE
    assert "Budget & programs" in TEMPLATE
    assert "createGovernmentRevenueBudget" in (ROOT / "templates" / "government-revenue-dossiers.js").read_text(encoding="utf-8")
    assert "Funding-stage firewall" in (ROOT / "templates" / "government-revenue-dossiers.js").read_text(encoding="utf-8")
    assert "Request evidence is upstream—not funded revenue" in (ROOT / "templates" / "government-revenue-dossiers.js").read_text(encoding="utf-8")
    assert "No budget source observation timestamp is available." in TEMPLATE


def test_candidate_radar_requires_exact_receipt_bound_candidates_and_keeps_company_coverage_separate() -> None:
    implementation = TEMPLATE + CANDIDATE_RADAR
    for marker in (
        'data-mode="candidates"',
        'id="countCandidates"',
        "Candidate Radar",
        "No exact-linked changes yet",
        "Exact change detection unavailable",
        "No candidate or signal was inferred.",
        "Discovery-scope history · mapping needed",
        "Discovery-scope history · issuer path verified",
        "Issuer mapping needed",
        "Issuer path verified",
        'government-revenue-candidate-radar.js',
        "createGovernmentRevenueCandidateRadar",
        "/api/government-revenue/candidates",
        "/api/government-revenue/mapping-backlog",
        "government_revenue_candidate_queue.v1",
        "government_revenue_candidate.v1",
        "government_recipient_resolution.v1",
        "counts.total",
        "mapping_backlog",
        "Exact issuer path",
        "Possible statement channel",
        "Other Mastermind evidence",
        "Research context only. It cannot rank a company",
    ):
        assert marker in implementation

    assert "DATA.companies" not in CANDIDATE_RADAR
    assert "candidate_scope!=='government_revenue_research'" in CANDIDATE_RADAR
    assert "is_neuralweb_trade_candidate!==false" in CANDIDATE_RADAR
    assert "fetchPages" in CANDIDATE_RADAR
    assert "candidate_mapping_generation_drift" in CANDIDATE_RADAR
    assert CANDIDATE_RADAR_SITE == CANDIDATE_RADAR
    assert 'src="government-revenue-candidate-radar.js"' in TEMPLATE


@needs_node
def test_candidate_radar_loads_every_candidate_and_mapping_page(tmp_path: Path) -> None:
    script = textwrap.dedent(
        """
        var window={};
        var calls=[];
        var authority={tier:'display',context_only:true,can_rank:false,can_size:false,can_gate:false,can_originate_signal:false,can_add_candidates:false,can_escalate:false};
        function candidate(){return {contract:'government_revenue_candidate.v1',schema_version:'1.0.0',candidate_id:'grc1-'+('a'.repeat(24)),candidate_scope:'government_revenue_research',is_neuralweb_trade_candidate:false,candidate_family:'new_award',candidate_state:'awaiting_crosscheck',ticker:'NOC',issuer_company_id:'issuer:noc',issuer:{company_name:'Northrop Grumman',ticker:'NOC'},issuer_resolution_ref:{contract:'government_recipient_resolution.v1',graph_id:'graph:test',evidence_refs:['evidence:1']},known_at:'2026-08-02T00:00:00Z',effective_at:'2026-08-01T00:00:00Z',transmission_direction:'possible_positive',event_refs:['event:1'],source_receipt_refs:[{ref_id:'receipt:1'}],ownership_path_refs:['edge:1'],authority:authority};}
        function envelope(items,total,next){return {contract:'government_revenue_candidate_queue.v1',schema_version:'1.0.0',content_id:'grcq1-'+('b'.repeat(24)),authority:authority,items:items,total:total,next_cursor:next,mapping_backlog_total:2,known_at:'2026-08-02T00:00:00Z',as_of:'2026-08-03T00:00:00Z',freshness:{},limitations:[]};}
        window.fetch=function(url){calls.push(url);var mapping=url.indexOf('/mapping-backlog')>-1,cursor=new URL('https://example.test'+url).searchParams.get('cursor');if(mapping)return Promise.resolve({ok:true,json:function(){return Promise.resolve(envelope([{backlog_id:'grmb1-'+('c'.repeat(24)),mapping_state:'mapping_needed',issuer_attribution:'not_asserted',ticker:'LMT'},{backlog_id:'grmb1-'+('d'.repeat(24)),mapping_state:'partial_identifier_coverage',issuer_attribution:'not_asserted',ticker:'RTX'}],2,null))}});var count=cursor?50:100;return Promise.resolve({ok:true,json:function(){return Promise.resolve(envelope(Array.from({length:count},candidate),150,cursor?null:'candidate-page-2'))}})};
        %(candidate_source)s
        var published=null;
        var radar=window.createGovernmentRevenueCandidateRadar({obj:function(x){return !!x&&typeof x==='object'&&!Array.isArray(x)},arr:function(x){return Array.isArray(x)?x:[]},esc:String,text:function(x,f){return x==null?f:String(x)},n:function(x){var v=Number(x);return Number.isFinite(v)?v:null},money:String,date:String,tr:function(en){return en},safeUrl:function(){return''},host:function(){return null},onRows:function(rows,meta){published={rows:rows.length,meta:meta}}});
        radar.load().then(function(){process.stdout.write(JSON.stringify({calls:calls,published:published}))});
        """
    ) % {"candidate_source": CANDIDATE_RADAR}
    path = tmp_path / "candidate_pages.js"
    path.write_text(script, encoding="utf-8")

    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["calls"]) == 3
    assert payload["published"]["rows"] == 150
    assert payload["published"]["meta"]["total"] == 150
    assert payload["published"]["meta"]["mapping_backlog_tickers"] == ["LMT", "RTX"]
    assert payload["published"]["meta"]["mapping_backlog_states"] == {
        "LMT": "mapping_needed",
        "RTX": "partial_identifier_coverage",
    }


def _radar_node_helpers() -> str:
    return (
        "function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)}"
        "function arr(x){return Array.isArray(x)?x:[]}"
        "function text(x,f){return x==null||x===''?(f==null?'':String(f)):String(x)}"
        "function n(x){var v=Number(x);return Number.isFinite(v)?v:null}"
        "var api={obj:obj,arr:arr,esc:String,text:text,n:n,money:String,date:String,"
        "tr:function(en){return en},safeUrl:function(){return''},host:function(){return null}};"
    )


def _run_radar_script(tmp_path: Path, name: str, script: str) -> dict:
    path = tmp_path / name
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


@needs_node
def test_candidate_radar_reports_an_unentitled_lane_as_locked(tmp_path: Path) -> None:
    """PR #5432 made /api/government-revenue/* a paid surface router-wide.

    A 401 before MDXAuth has settled is the entitled race, not a lock. After
    auth is ready, the same 401 is membership. Other HTTP failures stay
    unavailable so an outage cannot render as a sales pitch.
    """

    def run(status: int, *, auth_settled: bool) -> dict:
        script = textwrap.dedent(
            """
            var window={__govrevAuthSettled:%(settled)s};
            window.fetch=function(){return Promise.resolve({ok:false,status:%(status)s,
              json:function(){return Promise.resolve({})}})};
            %(candidate_source)s
            var published=null;
            %(helpers)s
            api.onRows=function(rows,meta){published={rows:rows.length,meta:meta}};
            var radar=window.createGovernmentRevenueCandidateRadar(api);
            radar.load().then(function(){process.stdout.write(JSON.stringify({published:published,state:radar.state()}))});
            """
        ) % {
            "candidate_source": CANDIDATE_RADAR,
            "status": status,
            "settled": "true" if auth_settled else "false",
            "helpers": _radar_node_helpers(),
        }
        return _run_radar_script(tmp_path, f"candidate_locked_{status}_{auth_settled}.js", script)

    for status in (401, 403):
        racing = run(status, auth_settled=False)
        assert racing["state"] == "loading", status
        assert racing["published"]["meta"]["status"] == "loading", status
        assert racing["published"]["rows"] == 0, status

        out = run(status, auth_settled=True)
        assert out["state"] == "locked", status
        assert out["published"]["meta"]["status"] == "locked", status
        assert out["published"]["rows"] == 0, status

    for status in (404, 500, 503):
        out = run(status, auth_settled=True)
        assert out["state"] == "unavailable", status
        assert out["published"]["meta"]["status"] == "unavailable", status


_RADAR_QUEUE_FIXTURE = """
var authority={tier:'display',context_only:true,can_rank:false,can_size:false,can_gate:false,can_originate_signal:false,can_add_candidates:false,can_escalate:false};
function candidateRow(){return {contract:'government_revenue_candidate.v1',schema_version:'1.0.0',candidate_id:'grc1-025ab7cfdb7f9735f0e1e575',candidate_scope:'government_revenue_research',is_neuralweb_trade_candidate:false,candidate_family:'new_award',candidate_state:'awaiting_crosscheck',ticker:'IRDM',issuer_company_id:'issuer:irdm',issuer:{company_name:'Iridium Communications',ticker:'IRDM'},issuer_resolution_ref:{contract:'government_recipient_resolution.v1',graph_id:'defense19-v1',evidence_refs:['evidence:1']},known_at:'2026-08-02T00:00:00Z',effective_at:'2026-08-01T00:00:00Z',transmission_direction:'possible_positive',event_refs:['event:1'],source_receipt_refs:[{ref_id:'receipt:1'}],ownership_path_refs:['edge:1'],authority:authority};}
function queueEnvelope(items,total){return {contract:'government_revenue_candidate_queue.v1',schema_version:'1.0.0',content_id:'grcq1-d93ebaf6878402e3be09e490',authority:authority,items:items,candidates:items,total:total,next_cursor:null,mapping_backlog_total:0,mapping_backlog_tickers:[],mapping_backlog_states:{},known_at:'2026-08-02T00:00:00Z',as_of:'2026-08-03T00:00:00Z',freshness:{},limitations:[]};}
"""


@needs_node
def test_candidate_radar_hydrates_cookie_queue_when_bearer_is_401(tmp_path: Path) -> None:
    """Entitled cookie JSON is a live plane even while the bearer API 401s."""
    script = textwrap.dedent(
        """
        var window={__govrevAuthSettled:true};
        %(fixture)s
        window.fetch=function(url){
          if(String(url).indexOf('government-revenue-data/candidates.json')>=0){
            return Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(queueEnvelope([candidateRow()],1))}});
          }
          return Promise.resolve({ok:false,status:401,json:function(){return Promise.resolve({})}});
        };
        %(candidate_source)s
        var published=null;
        %(helpers)s
        api.onRows=function(rows,meta){published={rows:rows.length,ids:rows.map(function(r){return r.id}),meta:meta}};
        var radar=window.createGovernmentRevenueCandidateRadar(api);
        radar.load().then(function(){process.stdout.write(JSON.stringify({published:published,state:radar.state()}))});
        """
    ) % {
        "candidate_source": CANDIDATE_RADAR,
        "helpers": _radar_node_helpers(),
        "fixture": _RADAR_QUEUE_FIXTURE,
    }
    out = _run_radar_script(tmp_path, "candidate_cookie_hydrate.js", script)
    assert out["state"] == "ok"
    assert out["published"]["rows"] == 1
    assert out["published"]["ids"] == ["candidate:grc1-025ab7cfdb7f9735f0e1e575"]
    assert out["published"]["meta"]["status"] == "ok"
    assert "locked" not in json.dumps(out)


@needs_node
def test_candidate_radar_cookie_outage_after_bearer_401_is_unavailable(tmp_path: Path) -> None:
    """Cookie 5xx is a data-plane failure, not a sales pitch, even if bearer 401'd first."""
    script = textwrap.dedent(
        """
        var window={__govrevAuthSettled:true};
        window.fetch=function(url){
          if(String(url).indexOf('government-revenue-data/candidates.json')>=0){
            return Promise.resolve({ok:false,status:500,json:function(){return Promise.resolve({})}});
          }
          return Promise.resolve({ok:false,status:401,json:function(){return Promise.resolve({})}});
        };
        %(candidate_source)s
        var published=null;
        %(helpers)s
        api.onRows=function(rows,meta){published={rows:rows.length,meta:meta}};
        var radar=window.createGovernmentRevenueCandidateRadar(api);
        radar.load().then(function(){process.stdout.write(JSON.stringify({published:published,state:radar.state()}))});
        """
    ) % {
        "candidate_source": CANDIDATE_RADAR,
        "helpers": _radar_node_helpers(),
    }
    out = _run_radar_script(tmp_path, "candidate_cookie_outage.js", script)
    assert out["state"] == "unavailable"
    assert out["published"]["meta"]["status"] == "unavailable"
    assert out["published"]["rows"] == 0


@needs_node
def test_candidate_radar_reloads_after_late_mdxauth_session(tmp_path: Path) -> None:
    """theme.js loads after Radar; the first 401 must not stick as membership."""
    script = textwrap.dedent(
        """
        var window={__govrevAuthSettled:false, token:null, authCbs:[]};
        %(fixture)s
        window.MDXAuth={
          enabled:function(){return true},
          onChange:function(cb){window.authCbs.push(cb)},
          client:function(){return Promise.resolve({auth:{getSession:function(){return Promise.resolve({data:{session:window.token?{access_token:window.token}:null}})}}})}
        };
        window.fetch=function(url, opts){
          var headers=(opts&&opts.headers)||{};
          var bearer=headers.Authorization==='Bearer tok';
          if(String(url).indexOf('/api/government-revenue/')===0 && bearer){
            var mapping=String(url).indexOf('/mapping-backlog')>=0;
            var items=mapping?[]:[candidateRow()];
            return Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(queueEnvelope(items, items.length))}});
          }
          return Promise.resolve({ok:false,status:401,json:function(){return Promise.resolve({})}});
        };
        %(candidate_source)s
        var published=null;
        %(helpers)s
        api.onRows=function(rows,meta){published={rows:rows.length,meta:meta}};
        var radar=window.createGovernmentRevenueCandidateRadar(api);
        radar.load().then(function(){
          var first={published:published,state:radar.state()};
          window.token='tok';
          window.authCbs.forEach(function(cb){cb({id:'user'},'INITIAL_SESSION')});
          return radar.state()==='ok'?Promise.resolve():new Promise(function(resolve){setTimeout(resolve,20)});
        }).then(function(){
          process.stdout.write(JSON.stringify({firstRows:published&&published.rows,firstWasLocked:false,state:radar.state(),rows:published&&published.rows,status:published&&published.meta.status}));
        });
        """
    ) % {
        "candidate_source": CANDIDATE_RADAR,
        "helpers": _radar_node_helpers(),
        "fixture": _RADAR_QUEUE_FIXTURE,
    }
    out = _run_radar_script(tmp_path, "candidate_late_auth.js", script)
    assert out["state"] == "ok"
    assert out["rows"] == 1
    assert out["status"] == "ok"


def test_company_ticker_filmstrip_stays_honest_and_routes_to_the_right_dossier() -> None:
    for marker in (
        'class="company-filmstrip"',
        'id="companyFilmstrip"',
        'role="list"',
        'data-filmstrip-ticker',
        'type="button" class="company-ticker',
        'aria-label="',  # buttons receive a full ticker, state, and destination label at render.
        'Evidence linked',
        'Issuer path verified',
        'Link pending',
        'Company file',
        'overflow-x:auto',
        'max-width:100%',
        '.company-ticker:focus-visible',
        'renderTickerFilmstrip();',
        'openTickerFilmstrip(button.dataset.filmstripTicker)',
    ):
        assert marker in TEMPLATE

    assert 'DATA.companies' in TEMPLATE
    assert 'rowsByMode.candidates.some' in TEMPLATE
    assert 'candidateMeta.mapping_backlog_tickers' in TEMPLATE
    assert ".company-filmstrip{display:block" in TEMPLATE
    assert "state.mode=stateName==='candidate'?'candidates':'companies'" in TEMPLATE
    assert "state.q='';state.agency='';state.truth='all'" in TEMPLATE
    assert "state.ticker=ticker" in TEMPLATE
    assert "renderTickerFilmstrip();syncCounts();populateFilters()" in TEMPLATE


def test_truth_layers_and_investor_inspector_do_not_overclaim() -> None:
    for marker in (
        "Official fact",
        "Observed document revision",
        "Official POP end",
        "Derived issuer link",
        "Derived watch",
        "not a bidder forecast",
        "not an official recompete date",
        "cannot rank a company",
        "What changed",
        "Why it matters",
        "Research stance",
        "Revision diff",
        "Dates & amounts",
        "Company transmission",
        "Evidence & limits",
        "Cross-links",
    ):
        assert marker in TEMPLATE

    assert "can_rank=true" not in TEMPLATE
    assert "win probability" not in TEMPLATE.lower()
    assert "<canvas" not in TEMPLATE
    assert "Display priority is not investment rank" in TEMPLATE
    assert "is_investment_rank: false" in TEMPLATE


def test_workspace_event_semantics_are_rendered_from_the_governed_contract() -> None:
    for marker in (
        "what_changed_en",
        "what_changed_zh",
        "changed_fields",
        "listed_company_impacts",
        "cross_desk_links",
        "evidence||{}).receipts",
        "ev.derivations",
        "ev.limitations",
        "w.authority",
        "Observed document bytes changed",
        "Official USAspending change",
        "Receipt-bound USAspending award or action observation",
        "Official procurement change; public-company transmission remains unresolved",
        "Reviewed issuer link",
        "Resolve the recipient",
        "not reconstructed in the browser",
        "configured defense and technology acquisition universe",
        "government-revenue-data/workspace.json",
        "WORKSPACE.next_cursor",
        "governmentworkspacehydrated",
        "__hydrateGovernmentWorkspace",
        "workspaceBundleMatches",
        "bundle_id",
        "workspaceDegraded",
        "workspaceRetry",
        ".workspace-degraded[hidden]{display:none}",
        "effectiveFreshnessState",
        "freshness_sla_minutes",
        "current_state_verified",
        "observation_age_minutes",
        "events_available_before_cap",
        "facet_scope",
        "Award tape warming or qualified",
        "Award-event rail:",
    ):
        assert marker in TEMPLATE

    assert "Net award action flow (90d)" in TEMPLATE
    assert "net_award_action_flow_90d" in TEMPLATE
    assert "90d modification" not in TEMPLATE


def test_keyboard_url_mobile_and_zero_data_paths_are_first_class() -> None:
    for marker in (
        "ArrowDown|ArrowUp|Home|End|Enter",
        "ArrowRight|ArrowLeft|Home|End",
        "URLSearchParams",
        "history.replaceState",
        "mobile-sheet",
        "prefers-reduced-motion",
        "No opportunities in this cut",
        "Award tape is warming",
        "No expiry watches",
        "No qualifying changes",
        "No rows were invented",
    ):
        assert marker in TEMPLATE


def test_research_briefcase_is_local_auditable_and_workspace_gated() -> None:
    implementation = TEMPLATE + BRIEFCASE + BRIEFCASE_UI
    for marker in (
        'data-sync src="government-revenue-briefcase.js"',
        'data-sync src="government-revenue-briefcase-ui.js"',
        'id="researchBriefcase"',
        'id="savedViewSelect"',
        'id="toggleLocalAlert"',
        'id="localInbox"',
        'id="exportViewJson"',
        'id="exportViewCsv"',
        "currentFilterState",
        "briefcaseWorkspaceReady",
        "briefcaseController.reconcile",
        "complete:true,bundle_matched:true",
        "Alerts are checked only when you open or refresh this page",
        "first complete-workspace check establishes a baseline",
        "Award-change alert baseline withheld",
        "Auditable JSON view exported",
        "Auditable CSV view exported",
    ):
        assert marker in implementation

    for forbidden in (
        "background delivery",
        "email alert",
        "push notification",
        "cross-device sync",
    ):
        assert forbidden not in implementation.lower()


def test_generated_page_contains_the_flagship_markers() -> None:
    for marker in (
        'id="gov-workspace"',
        'id="queueList"',
        'id="inspectorPane"',
        'id="evidenceDrawer"',
        'id="gov-data"',
    ):
        assert marker in SITE


def test_generated_shell_and_workspace_share_a_fail_closed_bundle_id() -> None:
    match = re.search(r'<script id="gov-data" type="application/json">(.*?)</script>', SITE, re.S)
    assert match, "generated page must carry its compact JSON shell"
    shell = json.loads(match.group(1).replace(r"<\/", "</"))
    workspace = json.loads(WORKSPACE_PATH.read_text(encoding="utf-8"))

    prefix = "grw2" if workspace["schema_version"] == "government_procurement_workspace.v2" else "grw1"
    assert re.fullmatch(rf"{prefix}-[a-f0-9]{{24}}", workspace["bundle_id"])
    assert shell["procurement_workspace"]["bundle_id"] == workspace["bundle_id"]


def test_generated_html_stays_inside_the_raw_edge_budget() -> None:
    assert SITE_PATH.stat().st_size <= build_government_revenue.RAW_HTML_BUDGET_BYTES


@needs_node
def test_runtime_company_filmstrip_only_promotes_receipt_linked_tickers(tmp_path: Path) -> None:
    workspace = {
        "schema_version": "government_procurement_workspace.v1",
        "bundle_id": "grw1-" + "a" * 24,
        "total": 0,
        "next_cursor": None,
        "events": [],
        "coverage": {},
        "freshness": {"status": "ok"},
        "limitations": [],
    }
    payload = {
        "companies": [
            {"ticker": "EXACT", "name": "Exact Link Co."},
            {"ticker": "MAPPING", "name": "Pending Link Co."},
            {"ticker": "QUIET", "name": "Coverage Co."},
        ],
        "market": {},
        "freshness": {"status": "ok"},
        "opportunity_intelligence": {"market": {}},
        "procurement_workspace": workspace,
    }
    candidate_rows = [{
        "id": "candidate:exact",
        "kind": "candidate",
        "tickers": ["EXACT"],
        "title": "EXACT · Exact Link Co.",
        "subtitle": "Receipt-bound procurement change",
        "date": "2026-08-01T00:00:00Z",
        "candidate": {},
    }]

    all_backlog = _run_runtime(
        tmp_path,
        payload,
        workspace,
        1_785_548_460_000,
        candidate_rows=candidate_rows,
        mapping_backlog_total=2,
        mapping_backlog_tickers=["MAPPING", "QUIET"],
        mapping_backlog_states={"MAPPING": "mapping_needed", "QUIET": "mapping_needed"},
        ticker_routes=["EXACT", "MAPPING"],
    )
    assert all_backlog["tickerStates"] == ["candidate", "mapping"]
    assert all_backlog["tickerRoutes"] == [
        {"mode": "candidates", "ticker": "EXACT", "selected": "candidate:exact"},
        {"mode": "companies", "ticker": "MAPPING", "selected": "company:MAPPING"},
    ]

    partial_backlog = _run_runtime(
        tmp_path,
        payload,
        workspace,
        1_785_548_460_000,
        candidate_rows=candidate_rows,
        mapping_backlog_total=1,
        mapping_backlog_tickers=["MAPPING"],
        mapping_backlog_states={"MAPPING": "partial_identifier_coverage"},
        ticker_routes=["MAPPING"],
    )
    assert partial_backlog["tickerStates"] == ["verified"]
    assert partial_backlog["tickerRoutes"] == [
        {"mode": "companies", "ticker": "MAPPING", "selected": "company:MAPPING"},
    ]
    assert "Issuer path verified" in partial_backlog["inspectorHtml"]
    assert "not a candidate or signal" in partial_backlog["inspectorHtml"]


@needs_node
def test_runtime_distinguishes_unavailable_change_detection_from_a_quiet_tape(tmp_path: Path) -> None:
    workspace = {
        "schema_version": "government_procurement_workspace.v1",
        "bundle_id": "grw1-" + "a" * 24,
        "total": 0,
        "next_cursor": None,
        "events": [],
        "coverage": {},
        "freshness": {"status": "ok"},
        "limitations": [],
    }
    payload = {
        "companies": [{"ticker": "PLTR", "name": "Palantir Technologies"}],
        "market": {},
        "freshness": {"status": "ok"},
        "opportunity_intelligence": {"market": {}},
        "procurement_workspace": workspace,
    }

    unavailable = _run_runtime(
        tmp_path,
        payload,
        workspace,
        1_785_548_460_000,
        candidate_rows=[],
        exact_candidate_availability="unavailable",
        location_search="?mode=candidates",
    )
    assert "Exact change detection unavailable" in unavailable["queueHtml"]
    assert "No candidate or signal was inferred" in unavailable["queueHtml"]

    quiet = _run_runtime(
        tmp_path,
        payload,
        workspace,
        1_785_548_460_000,
        candidate_rows=[],
        exact_candidate_availability="available",
        location_search="?mode=candidates",
    )
    assert "No exact-linked changes yet" in quiet["queueHtml"]
    assert "Exact change detection unavailable" not in quiet["queueHtml"]

    withheld = _run_runtime(
        tmp_path,
        payload,
        workspace,
        1_785_548_460_000,
        candidate_rows=[],
        exact_candidate_availability="withheld_historical",
        location_search="?mode=candidates",
    )
    assert "Historical exact rows withheld" in withheld["queueHtml"]
    assert "were not issued or backfilled" in withheld["queueHtml"]
    assert "No candidate or signal was inferred" in withheld["queueHtml"]
    assert "no eligible issuer-linked event exists" not in withheld["queueHtml"]

    quarantined = _run_runtime(
        tmp_path,
        payload,
        workspace,
        1_785_548_460_000,
        candidate_rows=[],
        exact_candidate_availability="quarantined_historical_issuance",
        location_search="?mode=candidates",
    )
    assert "Historical issuance quarantined" in quarantined["queueHtml"]
    assert (
        "The eight affected rows remain in the immutable audit ledger but are excluded "
        "from candidate, Prophet, ranking, sizing, gating, and signal surfaces."
        in quarantined["queueHtml"]
    )
    assert "were not issued or backfilled" not in quarantined["queueHtml"]
    assert "历史发布已隔离" in TEMPLATE
    assert (
        "受影响的 8 条记录仍保留在不可变审计账本中，但已从候选、Prophet、排名、仓位、门控与信号界面排除。"
        in TEMPLATE
    )
    assert "Historical issuance quarantined" in SITE


@needs_node
def test_runtime_restores_async_candidate_deep_link_selection(tmp_path: Path) -> None:
    workspace = {
        "schema_version": "government_procurement_workspace.v1",
        "bundle_id": "grw1-" + "a" * 24,
        "total": 0,
        "next_cursor": None,
        "events": [],
        "coverage": {},
        "freshness": {"status": "ok"},
        "limitations": [],
    }
    payload = {
        "companies": [
            {"ticker": "ONE", "name": "One Co."},
            {"ticker": "TWO", "name": "Two Co."},
        ],
        "market": {},
        "freshness": {"status": "ok"},
        "opportunity_intelligence": {"market": {}},
        "procurement_workspace": workspace,
    }
    candidates = [
        {"id": "candidate:one", "kind": "candidate", "tickers": ["ONE"], "title": "ONE · One Co.", "subtitle": "First", "candidate": {}},
        {"id": "candidate:two", "kind": "candidate", "tickers": ["TWO"], "title": "TWO · Two Co.", "subtitle": "Second", "candidate": {}},
    ]

    result = _run_runtime(
        tmp_path,
        payload,
        workspace,
        1_785_548_460_000,
        candidate_rows=candidates,
        location_search="?mode=candidates&item=candidate%3Atwo",
    )

    assert result["selection"] == {
        "mode": "candidates",
        "ticker": "",
        "selected": "candidate:two",
        "pending": "",
    }


@needs_node
def test_runtime_does_not_substitute_a_stale_candidate_deep_link(tmp_path: Path) -> None:
    workspace = {
        "schema_version": "government_procurement_workspace.v1",
        "bundle_id": "grw1-" + "a" * 24,
        "total": 0,
        "next_cursor": None,
        "events": [],
        "coverage": {},
        "freshness": {"status": "ok"},
        "limitations": [],
    }
    payload = {
        "companies": [{"ticker": "ONE", "name": "One Co."}],
        "market": {},
        "freshness": {"status": "ok"},
        "opportunity_intelligence": {"market": {}},
        "procurement_workspace": workspace,
    }
    candidates = [{
        "id": "candidate:one",
        "kind": "candidate",
        "tickers": ["ONE"],
        "title": "ONE · One Co.",
        "subtitle": "Current candidate",
        "candidate": {},
    }]

    result = _run_runtime(
        tmp_path,
        payload,
        workspace,
        1_785_548_460_000,
        candidate_rows=candidates,
        location_search="?mode=candidates&item=candidate%3Agone",
    )

    assert result["selection"] == {
        "mode": "candidates",
        "ticker": "",
        "selected": "",
        "pending": "",
    }
    assert "Candidate no longer available" in result["inspectorHtml"]
    assert "candidate:one" not in result["inspectorHtml"]


@needs_node
def test_runtime_ages_quiet_sources_and_exposes_retry_on_bundle_mismatch(tmp_path: Path) -> None:
    shell_workspace = {
        "schema_version": "government_procurement_workspace.v1",
        "bundle_id": "grw1-" + "a" * 24,
        "total": 1,
        "next_cursor": "0",
        "events": [],
        "freshness": {
            "status": "ok",
            "opportunities": {
                "status": "ok",
                "observed_at": "2026-08-01T00:00:00Z",
                "freshness_sla_minutes": 30,
            },
            "recompetes": {"status": "ok"},
        },
        "coverage": {},
        "limitations": [],
    }
    payload = {
        "companies": [],
        "market": {},
        "freshness": {
            "status": "ok",
            "award_events": {
                "status": "partial",
                "observed_at": "2026-08-01T01:00:00Z",
                "freshness_sla_days": 4,
            },
        },
        "opportunity_intelligence": {"market": {}},
        "procurement_workspace": shell_workspace,
    }
    full_workspace = {
        **shell_workspace,
        "bundle_id": "grw1-" + "b" * 24,
        "events": [{}],
    }

    out = _run_runtime(
        tmp_path,
        payload,
        full_workspace,
        1_785_548_460_000,  # 2026-08-01T02:01:00Z; more than 2x the 30m SLA
    )

    assert out["bundlesMatch"] is False
    assert out["initial"]["hidden"] is False
    assert out["initial"]["retryHidden"] is False
    assert "different evidence cut" in out["initial"]["copy"]
    assert out["afterRetry"]["hidden"] is False
    assert out["fetchCalls"] == 2
    assert out["freshness"]["status"] == "stale"
    assert out["freshness"]["aged"] is True


def _locked_shell() -> tuple[dict, dict]:
    """A shell that still needs hydration, plus the full cut it will ask for."""
    shell_workspace = {
        "schema_version": "government_procurement_workspace.v1",
        "bundle_id": "grw1-" + "a" * 24,
        "total": 9,
        "next_cursor": "0",
        "events": [],
        "freshness": {"status": "ok"},
        "coverage": {},
        "limitations": [],
    }
    payload = {
        "companies": [{"ticker": "ACME", "name": "Acme Defense Systems"}],
        "market": {},
        "freshness": {"status": "ok"},
        "opportunity_intelligence": {"market": {}},
        "procurement_workspace": shell_workspace,
    }
    return payload, {**shell_workspace, "next_cursor": None, "events": [{}]}


@needs_node
def test_runtime_reads_an_unentitled_workspace_as_locked_not_as_missing_data(tmp_path: Path) -> None:
    """A 401/403 on the governed payload is an authorization fact, never a data fact.

    site/government-revenue-data/ is default-deny in config/site_access.yml, so the
    ordinary reason a visitor never receives the full workspace is that they are not
    entitled to it — not that the desk failed to build one. The pre-existing default
    arm ("the complete workspace is unavailable") asserted the build fact, and an
    unentitled visitor read it as "there is nothing here" instead of "you cannot see
    this". Pin the distinction at the only place that can make it: the status code.
    """
    payload, full_workspace = _locked_shell()

    for status in (401, 403):
        out = _run_runtime(
            tmp_path, payload, full_workspace, 1_785_548_460_000, fetch_status=status
        )
        banner = out["initial"]
        assert banner["hidden"] is False, status
        assert banner["state"] == "locked", status
        # Reads as locked, and offers the upgrade path...
        assert "part of a membership" in banner["copy"], status
        assert banner["unlockHidden"] is False, status
        # ...rather than a data/build claim the page is in no position to make.
        assert "unavailable" not in banner["copy"], status
        assert "integrity checks" not in banner["copy"], status
        assert "different evidence cut" not in banner["copy"], status
        # Retrying an authorization failure is not the action on offer.
        assert banner["retryHidden"] is True, status

        # The banner is painted with textContent, so — unlike the l-en/l-zh spans
        # around it — it does not follow a language switch by itself. Before the
        # repaint it stayed English for a zh reader through every arm, locked
        # included (caught in a browser, not by this harness).
        zh = out["afterLangChange"]
        assert zh["error"] is None, zh["error"]
        assert zh["state"] == "locked", status
        assert "完整工作区包含在会员权益中。" in zh["copy"], status
        assert "part of a membership" not in zh["copy"], status

    # A genuine transport/server failure keeps the honest degraded wording, keeps
    # Retry, and offers no upgrade — otherwise the new arm would just swallow the
    # old one and every outage would read as a sales pitch.
    degraded = _run_runtime(
        tmp_path, payload, full_workspace, 1_785_548_460_000, fetch_status=503
    )["initial"]
    assert degraded["state"] == "degraded"
    assert "unavailable" in degraded["copy"]
    assert "membership" not in degraded["copy"]
    assert degraded["unlockHidden"] is True
    assert degraded["retryHidden"] is False


@needs_node
def test_runtime_reads_a_locked_candidate_ledger_as_members_only(tmp_path: Path) -> None:
    """/api/government-revenue/* is a paid surface router-wide (PR #5432).

    So the candidate lane's own 401/403 lands in the same trap: "Link status
    unavailable" and "The candidate ledger could not be verified" both assert a
    verification failure where the real cause is entitlement.
    """
    payload, full_workspace = _locked_shell()
    now = 1_785_548_460_000

    rail = _run_runtime(
        tmp_path, payload, full_workspace, now,
        candidate_rows=[], candidate_status="locked", ticker_routes=["ACME"],
    )
    assert rail["tickerStates"] == ["locked"]
    assert "Members only" in rail["filmstripHtml"]
    assert "state-locked" in rail["filmstripHtml"]
    assert "Link status unavailable" not in rail["filmstripHtml"]
    # The rail re-renders on a language switch, so it must carry its zh pair too.
    assert "会员可见" in rail["zhFilmstripHtml"]
    assert "Members only" not in rail["zhFilmstripHtml"]

    desk = _run_runtime(
        tmp_path, payload, full_workspace, now,
        candidate_rows=[], candidate_status="locked", location_search="?mode=candidates",
    )
    assert "Candidate Radar is locked" in desk["queueHtml"]
    assert "part of a membership" in desk["queueHtml"]
    assert "could not be verified" not in desk["queueHtml"]
    assert desk["queueSummary"] == "Candidate ledger locked"
    # The upgrade path, in place of counts that are only zero because we cannot
    # read them — "0 exact candidates" under a lock is a number, not a fact.
    assert 'href="plans.html"' in desk["queueHtml"]
    assert "View membership plans" in desk["queueHtml"]
    assert "exact candidates" not in desk["queueHtml"]

    # The genuine unavailable path is untouched: same shape, different cause.
    # (Kept in two runs because openTickerFilmstrip routes the desk to `companies`,
    # which would replace the candidates empty state before queueHtml is read.)
    down_rail = _run_runtime(
        tmp_path, payload, full_workspace, now,
        candidate_rows=[], candidate_status="unavailable", ticker_routes=["ACME"],
    )
    assert down_rail["tickerStates"] == ["unavailable"]
    assert "Link status unavailable" in down_rail["filmstripHtml"]
    assert "Members only" not in down_rail["filmstripHtml"]

    down_desk = _run_runtime(
        tmp_path, payload, full_workspace, now,
        candidate_rows=[], candidate_status="unavailable", location_search="?mode=candidates",
    )
    assert "could not be verified" in down_desk["queueHtml"]
    assert down_desk["queueSummary"] == "Candidate ledger unavailable"
    assert "plans.html" not in down_desk["queueHtml"]
    assert "Retry candidate ledger" in down_desk["queueHtml"]
    assert "View membership plans" not in down_desk["queueHtml"]


@needs_node
def test_d1_complete_workspace_hides_compact_loading_banner(tmp_path: Path) -> None:
    events = [
        {
            "contract": "government_procurement_event.v2",
            "event_id": f"govws-complete-{i:02d}",
            "record_id": f"award:CONT_{i:02d}",
            "kind": "award_change",
            "title_original": f"Obligation {i}",
            "agency": {"name": "Department of the Air Force"},
            "change": {
                "type": "obligation",
                "known_at": "2026-08-01T01:00:00Z",
                "what_changed_en": f"Obligation {i}",
                "changed_fields": [],
            },
            "award_change": {
                "award_key": f"CONT_{i:02d}",
                "piid": f"FA{i:04d}",
                "action_id": f"action-{i:04d}",
                "recipient_name": "Acme Defense Systems",
                "event_type": "obligation",
                "source_rail": "usaspending_award_action",
                "is_late_discovery": False,
            },
            "evidence": {"source_class": "official_award_action", "receipts": []},
            "listed_company_impacts": [],
        }
        for i in range(2)
    ]
    workspace = {
        "schema_version": "government_procurement_workspace.v2",
        "bundle_id": "grw2-" + "a" * 24,
        "total": 2,
        "next_cursor": None,
        "events": events,
        "coverage": {"events_visible": 2},
        "freshness": {"status": "ok"},
        "limitations": [],
    }
    payload = {
        "companies": [{"ticker": "IRDM", "name": "Iridium Communications"}],
        "market": {},
        "freshness": {"status": "ok", "opportunities": {"status": "unavailable"}},
        "opportunity_intelligence": {
            "market": {},
            "opportunities": [],
            "events": [],
            "freshness": {"status": "unavailable", "records_visible": 0, "observed_at": None},
        },
        "procurement_workspace": workspace,
    }
    out = _run_runtime(tmp_path, payload, workspace, 1_785_548_460_000)
    assert out["workspaceComplete"] is True
    assert out["initial"]["hidden"] is True
    assert "compact evidence cut" not in (out["initial"]["copy"] or "")
    assert "Members only" not in out["filmstripHtml"]


def _d11_agency_event(event_id: str, agency: dict | str | None, **overrides) -> dict:
    row = {
        "contract": "government_procurement_event.v2",
        "event_id": event_id,
        "record_id": f"award:{event_id}",
        "kind": "award_change",
        "title_original": event_id,
        "agency": agency,
        "change": {
            "type": "obligation",
            "known_at": "2026-08-01T01:00:00Z",
            "what_changed_en": event_id,
            "changed_fields": [],
        },
        "award_change": {
            "award_key": event_id,
            "piid": overrides.pop("piid", "PIID"),
            "action_id": overrides.pop("action_id", "action"),
            "recipient_name": "Acme",
            "event_type": "obligation",
            "source_rail": "usaspending_award_action",
            "is_late_discovery": overrides.pop("is_late_discovery", False),
        },
        "evidence": {"source_class": "official_award_action", "receipts": []},
        "listed_company_impacts": overrides.pop("listed_company_impacts", []),
    }
    row.update(overrides)
    return row


@needs_node
def test_d1_agency_filters_are_human_names_not_python_dicts(tmp_path: Path) -> None:
    workspace = {
        "schema_version": "government_procurement_workspace.v2",
        "bundle_id": "grw2-" + "b" * 24,
        "total": 2,
        "next_cursor": None,
        "events": [
            _d11_agency_event(
                "govws-agency-object",
                {"name": None, "department_name": "Department of the Navy"},
                piid="N00024",
                is_late_discovery=True,
            ),
            _d11_agency_event(
                "govws-agency-repr",
                "{'name': None, 'department_name': None}",
                piid="FA0001",
            ),
        ],
        "coverage": {"events_visible": 2},
        "freshness": {"status": "ok"},
        "limitations": [],
    }
    payload = {
        "companies": [],
        "market": {},
        "freshness": {"status": "ok"},
        "opportunity_intelligence": {"market": {}, "opportunities": []},
        "procurement_workspace": workspace,
    }
    out = _run_runtime(tmp_path, payload, workspace, 1_785_548_460_000)
    html = out["agencyFilterHtml"]
    assert "Department of the Navy" in html
    assert "Unspecified agency" in html
    assert "[object Object]" not in html
    assert "{'name': None" not in html
    assert "{name: None" not in html
    agencies = set(out["agencyNames"])
    assert "Department of the Navy" in agencies
    assert "Unspecified agency" in agencies


@needs_node
def test_d11_agency_labels_preserve_source_semantics(tmp_path: Path) -> None:
    """Semantic preservation, not merely sanitization of `{` / `: None`."""

    workspace = {
        "schema_version": "government_procurement_workspace.v2",
        "bundle_id": "grw2-" + "d" * 24,
        "total": 4,
        "next_cursor": None,
        "events": [
            _d11_agency_event(
                "govws-p00032",
                {
                    "department_name": "Department of Defense",
                    "subagency_name": "Defense Information Systems Agency",
                    "office_name": "TELECOMMUNICATIONS DIVISION- HC1013",
                    "name": "Department of Defense",
                    "subagency": "Defense Information Systems Agency",
                },
                piid="HC101319C0006",
                action_id="CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0",
                is_late_discovery=True,
                listed_company_impacts=[{"ticker": "IRDM"}],
            ),
            _d11_agency_event(
                "govws-nasa",
                {
                    "department_name": "National Aeronautics and Space Administration",
                    "subagency_name": "National Aeronautics and Space Administration",
                    "name": "National Aeronautics and Space Administration",
                },
                piid="NAS8-001",
            ),
            _d11_agency_event(
                "govws-subagency-only",
                {"department_name": None, "subagency_name": "Defense Logistics Agency", "name": None},
                piid="SPM-001",
            ),
            _d11_agency_event(
                "govws-missing",
                {"department_name": None, "name": None, "subagency": None},
                piid="UNK-001",
            ),
        ],
        "coverage": {"events_visible": 4},
        "freshness": {"status": "ok"},
        "limitations": [],
    }
    payload = {
        "companies": [{"ticker": "IRDM", "name": "Iridium Communications"}],
        "market": {},
        "freshness": {"status": "ok", "opportunities": {"status": "unavailable"}},
        "opportunity_intelligence": {
            "market": {},
            "opportunities": [],
            "events": [],
            "freshness": {"status": "unavailable", "records_visible": 0, "observed_at": None},
        },
        "procurement_workspace": workspace,
    }
    out = _run_runtime(tmp_path, payload, workspace, 1_785_548_460_000)
    html = out["agencyFilterHtml"]
    names = out["agencyNames"]
    assert "Department of Defense" in html
    assert "National Aeronautics and Space Administration" in html
    assert "Defense Logistics Agency" in html
    assert "Unspecified agency" in html
    assert names.count("Department of Defense") == 1
    assert names.count("National Aeronautics and Space Administration") == 1
    assert names.count("Defense Logistics Agency") == 1
    assert names.count("Unspecified agency") == 1
    assert "{'id'" not in html
    assert ": None" not in html
    assert "[object Object]" not in html
    assert "{" not in html
    assert "PROJECTION_MISSING" in TEMPLATE
    assert "SOURCE_UNAVAILABLE" in TEMPLATE
    assert out["workspaceComplete"] is True


@needs_node
def test_d1_entitled_complete_workspace_does_not_mark_filmstrip_members_only(
    tmp_path: Path,
) -> None:
    payload, full_workspace = _locked_shell()
    payload["procurement_workspace"] = {
        **full_workspace,
        "schema_version": "government_procurement_workspace.v2",
        "bundle_id": "grw2-" + "c" * 24,
        "total": 1,
        "next_cursor": None,
        "events": [
            {
                "contract": "government_procurement_event.v2",
                "event_id": "govws-irdm",
                "record_id": "award:IRDM",
                "kind": "award_change",
                "title_original": "P00032",
                "agency": {"name": "Department of the Air Force"},
                "change": {
                    "type": "obligation",
                    "known_at": "2026-08-01T01:00:00Z",
                    "what_changed_en": "P00032",
                    "changed_fields": [],
                },
                "award_change": {
                    "award_key": "IRDM",
                    "piid": "HC101319C0006",
                    "action_id": "P00032",
                    "recipient_name": "Iridium",
                    "event_type": "obligation",
                    "source_rail": "usaspending_award_action",
                    "is_late_discovery": True,
                },
                "evidence": {"source_class": "official_award_action", "receipts": []},
                "listed_company_impacts": [{"ticker": "IRDM"}],
            }
        ],
    }
    payload["companies"] = [{"ticker": "IRDM", "name": "Iridium Communications"}]
    rail = _run_runtime(
        tmp_path,
        payload,
        payload["procurement_workspace"],
        1_785_548_460_000,
        candidate_rows=[],
        candidate_status="locked",
        ticker_routes=["IRDM"],
        fetch_status=200,
    )
    assert rail["workspaceComplete"] is True
    assert rail["tickerStates"] == ["unavailable"]
    assert "Members only" not in rail["filmstripHtml"]
    assert "Link status unavailable" in rail["filmstripHtml"]


@needs_node
def test_d1_opportunities_and_budget_render_typed_failure_states(tmp_path: Path) -> None:
    payload, full_workspace = _locked_shell()
    payload["freshness"] = {"opportunities": {"status": "unavailable"}}
    payload["opportunity_intelligence"] = {
        "market": {},
        "opportunities": [],
        "freshness": {"status": "unavailable", "records_visible": 0, "observed_at": None},
    }
    opps = _run_runtime(
        tmp_path,
        payload,
        full_workspace,
        1_785_548_460_000,
        location_search="?mode=opportunities",
    )
    assert "SOURCE_UNAVAILABLE" in opps["queueHtml"]
    assert opps["queueSummary"] == "SOURCE_UNAVAILABLE"
    assert "valid empty bid week" in opps["queueHtml"] or "no observation" in opps["queueHtml"].lower() or "SOURCE_UNAVAILABLE" in opps["queueHtml"]

    assert "PROJECTION_MISSING" in TEMPLATE
    assert "SOURCE_UNAVAILABLE" in TEMPLATE
    assert "Retry candidate ledger" in TEMPLATE
    assert "重试候选账本" in TEMPLATE
    assert "Unspecified agency" in TEMPLATE
    assert "未指定机构" in TEMPLATE


def test_locked_arms_are_bilingual_and_keep_translations_out_of_title_attributes() -> None:
    """Every string the locked arms add ships with its zh pair (house law)."""
    implementation = TEMPLATE + CANDIDATE_RADAR
    for english, chinese in (
        ("View membership plans", "查看会员方案"),
        ("Members only", "会员可见"),
        ("Candidate Radar is locked", "候选雷达已锁定"),
        ("Candidate ledger locked", "候选账本已锁定"),
        (
            " governed records. The complete workspace is part of a membership.",
            " 条受治理记录。完整工作区包含在会员权益中。",
        ),
        (
            "The exact-linked candidate ledger is part of a membership.",
            "精确关联候选账本包含在会员权益中。",
        ),
    ):
        assert english in implementation, english
        assert chinese in implementation, chinese

    # Neither locked CTA may smuggle copy into a title= attribute (CI-guarded law).
    for chunk in re.findall(r'title="[^"]*"', implementation):
        assert not re.search(r"[一-鿿]", chunk), chunk

    # The upgrade path is an element, not a string: `workspaceBanner` writes its
    # copy with textContent and so can never carry a link, and the runtime harness
    # auto-creates any id it is asked for — so only the source can prove the anchor
    # ships. (A bare "View membership plans" substring is satisfied by the queue
    # empty state's own link and pins nothing here.)
    assert (
        '<a class="tool-btn" id="workspaceUnlock" href="plans.html" hidden>'
        "{{ t('View membership plans','查看会员方案') }}</a>"
    ) in TEMPLATE

    # The locked arm is a product statement, not an alarm: it must not borrow the
    # warn rung the degraded arm owns. Pin whole declarations — the bare selector
    # `[data-state="locked"]` also matches the dot rule two lines down, so a
    # substring check here goes vacuous the moment either rule exists alone.
    assert (
        '.workspace-degraded[data-state="locked"]{border-bottom-color:'
        "color-mix(in srgb,var(--gr-accent) 38%,var(--gr-line));"
    ) in TEMPLATE
    assert (
        '.workspace-degraded[data-state="locked"] .workspace-degraded-copy '
        "i{background:var(--gr-accent)}"
    ) in TEMPLATE
    assert ".company-ticker.state-locked .company-ticker-state{color:var(--gr-accent)}" in TEMPLATE

    # `hidden` is inert on these buttons without this rule: `.tool-btn` sets an
    # author `display:inline-flex`, which outranks the UA sheet's `[hidden]
    # {display:none}` — the same trap `.workspace-degraded[hidden]` already
    # exists to patch one level up. Verified in a browser: without it the upgrade
    # link stays on screen through every degraded/invalid/bundle-mismatch state,
    # so an outage renders as a sales pitch. No DOM-stub test can see this.
    assert ".workspace-degraded .tool-btn[hidden]{display:none}" in TEMPLATE

    # Falsifier/refutation vocabulary is never front-facing (operator 2026-07-27).
    for banned in ("falsifier", "refuted", "证伪", "Refutation"):
        assert banned not in implementation, banned


@needs_node
def test_runtime_preserves_award_change_kind_and_renders_unmapped_truth(tmp_path: Path) -> None:
    award = {
        "contract": "government_procurement_event.v2",
        "event_id": "govws-award-change-1",
        "record_id": "award:CONT_AWD_001",
        "kind": "award_change",
        "title_original": "New obligation observed — FA1234",
        "agency": {"name": "Department of the Air Force"},
        "change": {
            "type": "obligation",
            "known_at": "2026-08-01T01:00:00Z",
            "what_changed_en": "New obligation observed — FA1234",
            "changed_fields": [{"field": "federal_action_obligation", "before": 0, "after": 12_500_000}],
        },
        "award_change": {
            "award_key": "CONT_AWD_001",
            "piid": "FA1234",
            "action_id": "action-0001",
            "recipient_name": "Acme Defense Systems",
            "event_type": "obligation",
            "source_rail": "usaspending_award_action",
            "is_late_discovery": False,
        },
        "dates": [{"id": "action_date", "value": "2026-07-31", "semantic": "official_action_date"}],
        "amounts": [{"id": "federal_action_obligation", "value": 12_500_000, "semantic": "obligated"}],
        "listed_company_impacts": [],
        "evidence": {"source_class": "official_fact", "receipts": []},
        "authority": {"can_rank": False, "can_size": False},
    }
    workspace = {
        "schema_version": "government_procurement_workspace.v2",
        "event_contract": "government_procurement_event.v2",
        "bundle_id": "grw2-" + "a" * 24,
        "total": 1,
        "next_cursor": None,
        "events": [award],
        "coverage": {"events_visible": 1, "open_opportunities": 0},
        "freshness": {
            "status": "ok",
            "award_events": {
                "status": "partial",
                "observed_at": "2026-08-01T01:00:00Z",
                "freshness_sla_days": 4,
            },
        },
        "limitations": [],
    }
    payload = {
        "companies": [],
        "market": {},
        "freshness": {"status": "ok"},
        "opportunity_intelligence": {"market": {}},
        "procurement_workspace": workspace,
    }

    out = _run_runtime(tmp_path, payload, workspace, 1_785_548_460_000)

    assert out["bundlesMatch"] is True
    assert out["freshness"]["status"] == "ok"
    assert out["freshness"]["award_events"] == "partial"
    assert out["rows"] == [{
        "kind": "award_change",
        "truth": "official",
        "linked": False,
        "defense": True,
        "title": "New obligation observed — FA1234",
    }]
    assert "Official USAspending change" in out["inspectorHtml"]
    assert "Resolve the recipient" in out["inspectorHtml"]
    assert "public-company transmission remains unresolved" in out["inspectorHtml"]


def _discovery_timing_workspace(
    *,
    effective_at: str | None,
    known_at: str | None,
    is_late_discovery: bool,
) -> dict:
    """A snapshot-rail diff event, the shape that hardcodes ``is_late_discovery``.

    ``award_events._project_snapshots`` emits every diff-derived change event with
    ``is_late_discovery=False`` because the flag answers "was this a late FIRST
    discovery", a question a diff cannot be.  The page must therefore read the
    event's own effective->known clock instead of trusting that false.
    """
    change: dict[str, object] = {
        "type": "current_value_changed",
        "what_changed_en": "Award value raised — FA1234",
        "changed_fields": [
            {"field": "current_award_amount", "before": 10_000_000, "after": 12_500_000}
        ],
    }
    if effective_at is not None:
        change["effective_at"] = effective_at
    if known_at is not None:
        change["known_at"] = known_at
    award = {
        "contract": "government_procurement_event.v2",
        "event_id": "govws-award-change-timing",
        "record_id": "award:CONT_AWD_777",
        "kind": "award_change",
        "title_original": "Award value raised — FA1234",
        "agency": {"name": "Department of the Air Force"},
        "change": change,
        "award_change": {
            "award_key": "CONT_AWD_777",
            "piid": "FA1234",
            "recipient_name": "Acme Defense Systems",
            "event_type": "current_value_changed",
            "source_rail": "usaspending_award_snapshot",
            "is_late_discovery": is_late_discovery,
        },
        "dates": [],
        "amounts": [],
        "listed_company_impacts": [],
        "evidence": {"source_class": "official_fact", "receipts": []},
        "authority": {"can_rank": False, "can_size": False},
    }
    return {
        "schema_version": "government_procurement_workspace.v2",
        "event_contract": "government_procurement_event.v2",
        "bundle_id": "grw2-" + "b" * 24,
        "total": 1,
        "next_cursor": None,
        "events": [award],
        "coverage": {"events_visible": 1, "open_opportunities": 0},
        "freshness": {"status": "ok"},
        "limitations": [],
    }


def _discovery_timing_html(tmp_path: Path, workspace: dict, lang: str = "en") -> str:
    payload = {
        "companies": [],
        "market": {},
        "freshness": {"status": "ok"},
        "opportunity_intelligence": {"market": {}},
        "procurement_workspace": workspace,
    }
    out = _run_runtime(tmp_path, payload, workspace, 1_785_548_460_000, lang=lang)
    return out["inspectorHtml"]


@needs_node
@pytest.mark.parametrize(
    ("lang", "expected", "forbidden"),
    [
        ("en", "Late discovery · 98 days", "Observed in live window"),
        ("zh", "延迟发现 · 98 天", "在实时窗口内观测"),
    ],
)
def test_delayed_publication_diff_event_never_claims_a_live_window(
    tmp_path: Path, lang: str, expected: str, forbidden: str
) -> None:
    """A ~92d delayed-publication gap must not read as a fresh catalyst.

    The 2026-08-13 batch carried May-dated snapshot rows whose diff events all
    hardcode ``is_late_discovery=False``.  The old binary copy turned that
    structural false into a positive freshness assertion in both locales.
    """
    workspace = _discovery_timing_workspace(
        effective_at="2026-05-07T00:00:00Z",
        known_at="2026-08-13T00:00:00Z",
        is_late_discovery=False,
    )

    html = _discovery_timing_html(tmp_path, workspace, lang=lang)

    assert expected in html
    assert forbidden not in html


@needs_node
@pytest.mark.parametrize(
    ("lang", "expected"),
    [("en", "Observed in live window"), ("zh", "在实时窗口内观测")],
)
def test_promptly_observed_change_still_reads_as_a_live_window(
    tmp_path: Path, lang: str, expected: str
) -> None:
    """The live-window claim survives where the clock actually supports it."""
    workspace = _discovery_timing_workspace(
        effective_at="2026-08-11T00:00:00Z",
        known_at="2026-08-13T00:00:00Z",
        is_late_discovery=False,
    )

    html = _discovery_timing_html(tmp_path, workspace, lang=lang)

    assert expected in html
    assert "Late discovery" not in html


@needs_node
@pytest.mark.parametrize(
    ("lang", "expected", "forbidden"),
    [
        ("en", "Timing unconfirmed", "Observed in live window"),
        ("zh", "时点未确认", "在实时窗口内观测"),
    ],
)
def test_unmeasurable_gap_discloses_the_null_instead_of_claiming_freshness(
    tmp_path: Path, lang: str, expected: str, forbidden: str
) -> None:
    """An absent clock is a null to print, never evidence of a live observation."""
    workspace = _discovery_timing_workspace(
        effective_at=None,
        known_at="2026-08-13T00:00:00Z",
        is_late_discovery=False,
    )

    html = _discovery_timing_html(tmp_path, workspace, lang=lang)

    assert expected in html
    assert forbidden not in html


@needs_node
@pytest.mark.parametrize(
    ("lang", "expected"), [("en", "Late discovery"), ("zh", "延迟发现")]
)
def test_engine_late_verdict_outranks_an_unmeasurable_gap(
    tmp_path: Path, lang: str, expected: str
) -> None:
    """``_is_late_discovery`` fails closed on a missing clock; the page must too."""
    workspace = _discovery_timing_workspace(
        effective_at=None,
        known_at=None,
        is_late_discovery=True,
    )

    html = _discovery_timing_html(tmp_path, workspace, lang=lang)

    assert expected in html
    assert "Timing unconfirmed" not in html
    assert "时点未确认" not in html


def test_discovery_timing_threshold_tracks_the_engine_constant() -> None:
    """The page's live-window boundary mirrors the engine's own definition."""
    engine_default = int(
        re.search(
            r"^DEFAULT_LATE_DISCOVERY_DAYS\s*=\s*(\d+)",
            (ROOT / "engine" / "government_revenue" / "award_events.py").read_text(
                encoding="utf-8"
            ),
            re.MULTILINE,
        ).group(1)
    )
    page_default = int(
        re.search(r"var LATE_DISCOVERY_DAYS\s*=\s*(\d+)", TEMPLATE).group(1)
    )

    assert page_default == engine_default


def test_discovery_timing_never_reads_the_hardcoded_flag_alone() -> None:
    """Pin the defect: the cell must not branch on ``is_late_discovery`` at the call site."""
    assert "discoveryTiming(e.change,award)" in TEMPLATE
    assert "award.is_late_discovery?" not in TEMPLATE


# --------------------------------------------------------------------------------------
# D2 Identity Atlas — page-level guards. The runtime/state contracts live in
# tests/test_government_revenue_dossier_ui.py; these pin what the SHIPPED page must
# carry so the section can never be half-wired into the company inspector.
# --------------------------------------------------------------------------------------
DOSSIER_UI_JS = (ROOT / "templates" / "government-revenue-dossiers.js").read_text(encoding="utf-8")
PARITY_CSS_TEXT = (ROOT / "templates" / "government-revenue-parity.css").read_text(encoding="utf-8")


def test_identity_atlas_ships_on_the_company_inspector() -> None:
    """The page must carry the factory, the host and its state inks.

    Asserted against templates/, not the committed site/ page: government_revenue.html
    is a render-lane OUTPUT (a .j2 render, not a plain-copy pair), so it carries the
    previous bake's bytes until the next render — pinning it here would fail on a
    correct PR and pass on a stale one.
    """
    for marker in (
        'data-sync src="government-revenue-dossiers.js"',
        "createGovernmentRevenueIdentityAtlas",
        'id="identityAtlas"',
        "Identity Atlas",
        "身份图谱",
    ):
        assert marker in TEMPLATE, marker
    assert "government-revenue-data/identity-atlas.json" in DOSSIER_UI_JS

    # Exactly one Atlas host — a second would race the first for the same ticker and
    # render two different paths for one company.
    assert TEMPLATE.count('id="identityAtlas"') == 1

    # The section is a sibling of the award book inside the company inspector — not a
    # new page, not a new nav entry, not a new header family.
    assert "identityAtlasSection()+dossierBookSection()" in TEMPLATE
    assert TEMPLATE.count('{% include "_site_nav.html.j2" %}') == 1
    assert "identity_atlas.html" not in TEMPLATE

    # State inks the rail needs, declared once in the page's own CSS home.
    assert ".truth.conflict{color:var(--gr-bad)}" in TEMPLATE
    assert ".truth.historic{color:var(--gr-muted)}" in TEMPLATE
    assert ".atlas-hop.break:after{border-left-style:dashed" in PARITY_CSS_TEXT


def test_identity_atlas_copy_is_bilingual_and_stays_out_of_title_attributes() -> None:
    """House law: EN/ZH twins for every added string; no translated text in title=."""
    implementation = TEMPLATE + DOSSIER_UI_JS
    for english, chinese in (
        ("Identity Atlas", "身份图谱"),
        ("Tracing the identity path", "正在追踪身份路径"),
        ("Reviewed issuer path", "已核验发行人路径"),
        ("Identity unresolved", "身份未解析"),
        ("Listing terminated", "上市已终止"),
        ("Conflict on record", "记录存在冲突"),
        ("Identity path locked", "身份路径已锁定"),
        ("Watch — don’t chase", "观察，不要追高"),
        ("Stand aside", "暂不参与"),
    ):
        assert english in implementation, english
        assert chinese in implementation, chinese

    for chunk in re.findall(r'title="[^"]*"', implementation):
        assert not re.search(r"[一-鿿]", chunk), chunk

    # Falsifier / refutation vocabulary is never front-facing (operator 2026-07-27).
    for banned in ("falsifier", "refuted", "refutation", "Refutation", "证伪"):
        assert banned not in implementation, banned


def test_identity_atlas_never_states_a_trade_instruction() -> None:
    """Display/context only: a stance, never an order (DESIGN_DOCTRINE Law 1 + D2 §3)."""
    atlas_source = DOSSIER_UI_JS.split("createGovernmentRevenueIdentityAtlas")[1].split(
        "global.createGovernmentRevenueBudget"
    )[0]
    assert "It cannot rank a company, size a position or trigger a trade." in atlas_source
    for banned in (
        "Buy now",
        "price target",
        "target price",
        "win probability",
        "bidder score",
        "expected revenue",
    ):
        assert banned not in atlas_source, banned
    # The Atlas has no authority fields of its own and never mints a candidate.
    for banned in ("can_rank", "can_size", "can_gate", "grc1-", "candidate_ledger"):
        assert banned not in atlas_source, banned
