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
    ticker_routes: list[str] | None = None,
    location_search: str = "",
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
        var TICKER_ROUTES = %(ticker_routes)s;
        var LOCATION_SEARCH = %(location_search)s;
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
        var document = {
          documentElement:{getAttribute:function(){return'en'}}, activeElement:null,
          getElementById:node, querySelectorAll:function(){return[]},
          addEventListener:function(){}, dispatchEvent:function(){return true}
        };
        var location = {href:'https://example.test/government_revenue.html'+LOCATION_SEARCH, pathname:'/government_revenue.html', search:LOCATION_SEARCH, hash:''};
        var history = {replaceState:function(){}};
        var navigator = {clipboard:null};
        var window = {location:location, history:history, navigator:navigator, innerWidth:1440};
        if(CANDIDATE_ROWS!==null)window.createGovernmentRevenueCandidateRadar=function(api){return {
          load:function(){api.onRows(CANDIDATE_ROWS,{status:'ok',total:CANDIDATE_ROWS.length,mapping_backlog_total:CANDIDATE_BACKLOG,mapping_backlog_tickers:CANDIDATE_BACKLOG_TICKERS,mapping_backlog_states:CANDIDATE_BACKLOG_STATES,freshness:{exact_candidate_availability:EXACT_CANDIDATE_AVAILABILITY}});return Promise.resolve(CANDIDATE_ROWS)},
          refresh:function(){return this.load()}, render:function(){}, invalidate:function(){}, state:function(){return 'ok'}, crosschecks:function(){return ''}
        }};
        var fetch = function(){fetchCalls += 1; return Promise.resolve({ok:true,json:function(){return Promise.resolve(FULL_WORKSPACE)}})};
        function CustomEvent(name, init){this.type=name;this.detail=init&&init.detail}
        %(page_runtime)s
        setTimeout(function(){
          var initial = {hidden:node('workspaceDegraded').hidden, copy:node('workspaceDegradedCopy').textContent,
                         retryHidden:node('workspaceRetry').hidden};
          node('workspaceRetry').fire('click');
          setTimeout(function(){
            var runtime = window.__governmentRevenueRuntime;
            var freshness = runtime.effectiveFreshnessState(PAYLOAD, PAYLOAD.procurement_workspace, NOW_MS);
            var tickerStates=TICKER_ROUTES===null?null:TICKER_ROUTES.map(function(ticker){return runtime.tickerRailState(ticker)});
            var tickerRoutes=TICKER_ROUTES===null?null:TICKER_ROUTES.map(function(ticker){return runtime.openTickerFilmstrip(ticker)});
            process.stdout.write(JSON.stringify({initial:initial, afterRetry:{hidden:node('workspaceDegraded').hidden,
              copy:node('workspaceDegradedCopy').textContent, retryHidden:node('workspaceRetry').hidden},
              fetchCalls:fetchCalls, freshness:freshness,
              bundlesMatch:runtime.workspaceBundleMatches(PAYLOAD.procurement_workspace, FULL_WORKSPACE),
              rows:runtime.workspaceRows(), tickerStates:tickerStates, tickerRoutes:tickerRoutes,
              selection:runtime.currentSelection(), inspectorHtml:node('inspector').innerHTML,
              queueHtml:node('queueList').innerHTML}));
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
        "ticker_routes": json.dumps(ticker_routes) if ticker_routes is not None else "null",
        "location_search": json.dumps(location_search),
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
