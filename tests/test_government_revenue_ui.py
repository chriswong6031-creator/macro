"""Flagship UI contracts for Government Revenue Foresight."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "templates" / "government_revenue.html.j2").read_text(encoding="utf-8")
BRIEFCASE = (ROOT / "templates" / "government-revenue-briefcase.js").read_text(encoding="utf-8")
BRIEFCASE_UI = (ROOT / "templates" / "government-revenue-briefcase-ui.js").read_text(encoding="utf-8")
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


def _run_runtime(tmp_path: Path, payload: dict, full_workspace: dict, now_ms: int) -> dict:
    """Run the page's real IIFE against a deliberately tiny browser DOM stub."""
    page_runtime = _page_runtime_js()
    script = textwrap.dedent(
        """
        var PAYLOAD = %(payload)s;
        var FULL_WORKSPACE = %(full_workspace)s;
        var NOW_MS = %(now_ms)s;
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
        var location = {href:'https://example.test/government_revenue.html', pathname:'/government_revenue.html', search:'', hash:''};
        var history = {replaceState:function(){}};
        var navigator = {clipboard:null};
        var window = {location:location, history:history, navigator:navigator, innerWidth:1440};
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
            process.stdout.write(JSON.stringify({initial:initial, afterRetry:{hidden:node('workspaceDegraded').hidden,
              copy:node('workspaceDegradedCopy').textContent, retryHidden:node('workspaceRetry').hidden},
              fetchCalls:fetchCalls, freshness:freshness,
              bundlesMatch:runtime.workspaceBundleMatches(PAYLOAD.procurement_workspace, FULL_WORKSPACE),
              rows:runtime.workspaceRows(), inspectorHtml:node('inspector').innerHTML}));
          }, 8);
        }, 8);
        """
    ) % {
        "payload": json.dumps(payload),
        "full_workspace": json.dumps(full_workspace),
        "now_ms": now_ms,
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
    assert SITE_PATH.stat().st_size <= 250_000


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
