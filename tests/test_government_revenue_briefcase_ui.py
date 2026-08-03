"""Contract tests for the browser-only Government Revenue research briefcase."""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "templates" / "government-revenue-briefcase.js"
SOURCE = MODULE.read_text(encoding="utf-8")
UI_SOURCE = (ROOT / "templates" / "government-revenue-briefcase-ui.js").read_text(encoding="utf-8")
HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")


def _run_node(tmp_path: Path, body: str, initial_state: str | None = None) -> dict:
    """Evaluate the production module inside a tiny browser/localStorage stub."""
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const source = fs.readFileSync(%(module)s, 'utf8');
        const values = {};
        %(initial_state)s
        const localStorage = {
          getItem: (key) => Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null,
          setItem: (key, value) => { values[key] = String(value); },
          removeItem: (key) => { delete values[key]; }
        };
        const window = { localStorage: localStorage };
        global.window = window;
        eval(source);
        const clock = () => '2026-08-02T12:00:00Z';
        const make = () => window.createGovernmentRevenueBriefcase({storage: localStorage, now: clock});
        %(body)s
        """
    ) % {
        "module": json.dumps(str(MODULE)),
        "initial_state": (
            "values['mastermind.government_revenue.briefcase.v1'] = " + json.dumps(initial_state) + ";"
            if initial_state is not None else ""
        ),
        "body": body,
    }
    path = tmp_path / "briefcase_runtime.js"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"node failed:\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"
    assert result.stdout.strip(), f"node emitted no result; stderr:\n{result.stderr}"
    return json.loads(result.stdout)


def _workspace(*events: dict, award_status: str = "ok", bundle: str = "grw2-aaaaaaaaaaaaaaaaaaaaaaaa") -> dict:
    return {
        "schema_version": "government_procurement_workspace.v2",
        "event_contract": "government_procurement_event.v2",
        "bundle_id": bundle,
        "as_of": "2026-08-02",
        "known_at": "2026-08-02T09:00:00Z",
        "generated_at": "2026-08-02T09:01:00Z",
        "authority": {
            "tier": "display", "context_only": True, "can_rank": False, "can_size": False,
            "can_gate": False, "can_originate_signal": False, "can_add_candidates": False,
            "can_escalate": False,
        },
        "freshness": {"status": "ok", "award_events": {"status": award_status}},
        "coverage": {"events_visible": len(events), "event_cap": 500, "facet_scope": "visible bounded workspace events"},
        "limitations": ["Bounded governed workspace cut."],
        "events": list(events),
    }


def _event(event_id: str, kind: str, *, title: str = "Visible governed record", ticker: str = "LMT") -> dict:
    return {
        "contract": "government_procurement_event.v2",
        "event_id": event_id,
        "record_id": "record:" + event_id,
        "version": 1,
        "kind": kind,
        "state": "watch" if kind == "recompete" else "updated",
        "title_original": title,
        "title_zh": None,
        "translation_status": "original",
        "agency": {"department_name": "Department of Defense", "private": "must-not-export"},
        "change": {"type": "recompete_watch_entered", "known_at": "2026-08-02T09:00:00Z"},
        "opportunity": None,
        "recompete": {"case_type": "derived_expiry_watch"} if kind == "recompete" else None,
        "award_change": {"event_type": "obligation", "award_key": "A-1"} if kind == "award_change" else None,
        "dates": [{"id": "current_end_date", "value": "2027-01-01", "private": "never"}],
        "amounts": [{"id": "obligation", "value": 1_000_000, "currency": "USD", "private": "never"}],
        "primary_date_id": "current_end_date",
        "primary_amount_id": "obligation",
        "listed_company_impacts": [{"ticker": ticker, "company_name": "Example Co.", "private": "never"}],
        "primary_ticker": ticker,
        "display_priority": {"score": 75, "is_investment_rank": False, "private": "never"},
        "evidence": {
            "source_class": "official_fact",
            "mapping_class": "deterministic_inference" if kind == "recompete" else "official",
            "receipts": [{"publisher": "USAspending", "record_id": "receipt-1", "url": "https://api.usaspending.gov/award/A-1", "private": "secret"}],
            "derivations": [], "conflicts": [], "limitations": ["Visible public receipt only."],
            "private_raw_receipt": "must-not-export",
        },
        "authority": {
            "tier": "display", "context_only": True, "can_rank": False, "can_size": False,
            "can_gate": False, "can_originate_signal": False, "can_add_candidates": False,
            "can_escalate": False, "private": "must-not-export",
        },
        "private_raw_payload": "must-not-export",
    }


def test_module_is_a_hermetic_browser_seam() -> None:
    assert "createGovernmentRevenueBriefcase" in SOURCE
    assert "government_procurement_local_state.v1" in SOURCE
    assert "government_procurement_export.v1" in SOURCE
    for forbidden in (
        "fetch(", "XMLHttpRequest", "Notification(", "setInterval(", "setTimeout(",
        "navigator.serviceWorker", "supabase", "MDXAuth",
    ):
        assert forbidden not in SOURCE

    assert "mountGovernmentRevenueBriefcaseUI" in UI_SOURCE
    assert "checked only when you open or refresh this page" in UI_SOURCE
    assert "first complete-workspace check establishes a baseline" in UI_SOURCE
    for forbidden in (
        "fetch(", "XMLHttpRequest", "Notification(", "setInterval(", "setTimeout(",
        "navigator.serviceWorker", "supabase", "MDXAuth",
    ):
        assert forbidden not in UI_SOURCE


@needs_node
def test_saved_view_crud_round_trips_exact_filter_contract_and_cascades_alerts(tmp_path: Path) -> None:
    out = _run_node(
        tmp_path,
        """
        const first = make();
        const created = first.createView({name:'  Defense tape  ', filters:{
          mode:'awards', truth:'linked', q:'  radar ', agency:'DoD', ticker:'lmt', ignored:'nope'
        }}).view;
        const changed = first.updateView(created.id, {name:'Revised', filters:{mode:'recompetes', truth:'defense', ticker:'bad/ticker'}}).view;
        const alert = first.createAlert({view_id:changed.id, type:'recompete'}).alert;
        const reloaded = make();
        const afterReload = reloaded.state();
        const deleted = reloaded.deleteView(changed.id);
        process.stdout.write(JSON.stringify({created, changed, alert, afterReload, deleted, afterDelete:reloaded.state()}));
        """,
    )

    assert out["created"]["name"] == "Defense tape"
    assert out["created"]["filters"] == {
        "mode": "awards", "truth": "linked", "q": "radar", "agency": "DoD", "ticker": "LMT"
    }
    assert out["changed"]["filters"] == {
        "mode": "recompetes", "truth": "defense", "q": "", "agency": "", "ticker": ""
    }
    assert out["afterReload"]["contract"] == "government_procurement_local_state.v1"
    assert len(out["afterReload"]["alerts"]) == 1
    assert out["deleted"]["deleted"] is True
    assert out["afterDelete"]["saved_views"] == []
    assert out["afterDelete"]["alerts"] == []
    assert out["afterDelete"]["inbox"] == []


@needs_node
def test_typed_alerts_baseline_then_reconcile_only_when_governed_workspace_is_ready(tmp_path: Path) -> None:
    opportunity_one = _event("govws-opp-1", "opportunity")
    opportunity_two = _event("govws-opp-2", "opportunity")
    award_one = _event("govws-awd-1", "award_change")
    award_two = _event("govws-awd-2", "award_change")
    recompete_one = _event("govws-rec-1", "recompete")
    recompete_two = _event("govws-rec-2", "recompete")
    workspace_one = _workspace(opportunity_one, award_one, recompete_one, award_status="unavailable")
    workspace_two = _workspace(opportunity_one, opportunity_two, award_one, award_two, recompete_one, recompete_two)

    out = _run_node(
        tmp_path,
        """
        const app = make();
        const view = app.createView({name:'All governed changes', filters:{mode:'changes', truth:'all'}}).view;
        const opportunity = app.createAlert({view_id:view.id, type:'opportunity'}).alert;
        const award = app.createAlert({view_id:view.id, type:'award_change'}).alert;
        const recompete = app.createAlert({view_id:view.id, type:'recompete'}).alert;
        const notReady = app.reconcile(WORKSPACE_ONE, {complete:false, bundle_matched:true});
        const first = app.reconcile(WORKSPACE_ONE, {complete:true, bundle_matched:true});
        const afterFirst = app.state();
        const second = app.reconcile(WORKSPACE_TWO, {complete:true, bundle_matched:true});
        process.stdout.write(JSON.stringify({notReady, first, afterFirst, second, inbox:app.listInbox()}));
        """.replace("WORKSPACE_ONE", json.dumps(workspace_one)).replace("WORKSPACE_TWO", json.dumps(workspace_two)),
    )

    assert out["notReady"]["reconciled"] is False
    assert out["notReady"]["reason"] == "workspace_not_ready"
    assert out["first"]["alerts"] == []
    assert len(out["first"]["withheld_alert_ids"]) == 1
    # Opportunity/recompete have a safe first-seen baseline; an unavailable award rail does not.
    state_by_type = {item["type"]: item for item in out["afterFirst"]["alerts"]}
    assert state_by_type["opportunity"]["primed"] is True
    assert state_by_type["recompete"]["primed"] is True
    assert state_by_type["award_change"]["primed"] is False
    # The award type becomes healthy only after its first baseline, so it cannot backfill a fake alert.
    assert {item["type"] for item in out["second"]["alerts"]} == {"opportunity", "recompete"}
    assert any(item["type"] == "recompete" and "not an official recompete date" in item["warning"] for item in out["inbox"])


@needs_node
def test_export_is_governed_allowlisted_and_csv_neutralizes_formula_text(tmp_path: Path) -> None:
    malicious = _event("govws-opp-export", "opportunity", title="=HYPERLINK(\"https://evil.example\")")
    workspace = _workspace(malicious)
    out = _run_node(
        tmp_path,
        """
        const app = make();
        const jsonExport = app.buildJsonExport(WORKSPACE, {mode:'changes', truth:'all', q:'', agency:'', ticker:''});
        const csvExport = app.buildCsvExport(WORKSPACE, {mode:'changes', truth:'all'});
        process.stdout.write(JSON.stringify({jsonExport, csvExport}));
        """.replace("WORKSPACE", json.dumps(workspace)),
    )

    payload = out["jsonExport"]
    serialized = json.dumps(payload)
    assert payload["contract"] == "government_procurement_export.v1"
    assert payload["workspace"]["bundle_id"].startswith("grw2-")
    assert payload["workspace"]["event_contract"] == "government_procurement_event.v2"
    assert payload["query"]["result_scope"] == "current visible governed workspace cut"
    assert payload["records"][0]["event_id"] == "govws-opp-export"
    assert "must-not-export" not in serialized
    assert "private_raw_payload" not in serialized
    assert "private_raw_receipt" not in serialized
    assert out["csvExport"]["contract"] == "government_procurement_export.v1"
    assert out["csvExport"]["media_type"] == "text/csv;charset=utf-8"
    assert "\"'=HYPERLINK(" in out["csvExport"]["content"]
    assert "must-not-export" not in out["csvExport"]["content"]


@needs_node
def test_csv_neutralizes_formula_after_leading_whitespace_or_control_bytes(tmp_path: Path) -> None:
    malicious = _event(
        "govws-opp-export-whitespace",
        "opportunity",
        title="\t\r\n\x01 =HYPERLINK(\"https://evil.example\")",
    )
    workspace = _workspace(malicious)
    out = _run_node(
        tmp_path,
        """
        const app = make();
        const csvExport = app.buildCsvExport(WORKSPACE, {mode:'changes', truth:'all'});
        process.stdout.write(JSON.stringify(csvExport));
        """.replace("WORKSPACE", json.dumps(workspace)),
    )

    # The apostrophe is deliberately before the original bytes: Excel/Sheets see
    # text, while the whitespace/control prefix remains represented in the export.
    assert "'\t\r\n\x01 =HYPERLINK(" in out["content"]


@needs_node
def test_malformed_local_storage_fails_closed_to_empty_state(tmp_path: Path) -> None:
    out = _run_node(
        tmp_path,
        """
        const app = make();
        process.stdout.write(JSON.stringify(app.state()));
        """,
        initial_state='{"contract":"wrong","saved_views":[{"id":"x"}]}',
    )
    assert out == {"contract": "government_procurement_local_state.v1", "saved_views": [], "alerts": [], "inbox": []}


@needs_node
def test_ui_mount_wires_saved_view_and_first_local_baseline(tmp_path: Path) -> None:
    workspace = _workspace(_event("govws-opp-ui", "opportunity"))
    script = textwrap.dedent(
        """
        const fs=require('fs'),values={},listeners={},nodes={};
        function node(id){if(!nodes[id])nodes[id]={id:id,value:id==='alertType'?'opportunity':'',innerHTML:'',textContent:'',className:'',disabled:false,
          addEventListener:function(k,f){listeners[id+':'+k]=f},fire:function(k,e){if(listeners[id+':'+k])listeners[id+':'+k](e||{key:'',preventDefault:function(){}})},focus:function(){}};return nodes[id]}
        const localStorage={getItem:k=>Object.prototype.hasOwnProperty.call(values,k)?values[k]:null,setItem:(k,v)=>{values[k]=String(v)}};
        const document={activeElement:null,getElementById:node,body:{appendChild:function(){}},createElement:function(){return{click:function(){},remove:function(){}}}};
        const window={localStorage:localStorage,document:document};global.window=window;
        eval(fs.readFileSync(%(core)s,'utf8'));eval(fs.readFileSync(%(ui)s,'utf8'));
        var filters={mode:'opportunities',truth:'defense',q:'radar',agency:'Department of Defense',ticker:'LMT'},applied=null,ready=true;
        function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
        var app=window.mountGovernmentRevenueBriefcaseUI({get:node,tr:function(x){return x},esc:esc,text:function(x,fb){return x==null||x===''?(fb||''):String(x)},
          getFilters:function(){return filters},applyFilters:function(value){applied=value},getWorkspace:function(){return %(workspace)s},isWorkspaceReady:function(){return ready},openDrawer:function(){}});
        app.bind();node('savedViewName').value='Defense radar';node('saveView').fire('click');
        filters={mode:'changes',truth:'all',q:'',agency:'',ticker:''};node('savedViewSelect').fire('change');
        node('toggleLocalAlert').fire('click');
        var state=JSON.parse(values['mastermind.government_revenue.briefcase.v1']);
        process.stdout.write(JSON.stringify({available:app.available,applied:applied,state:state,status:node('briefcaseStatus').textContent,toggle:node('toggleLocalAlert').textContent}));
        """
    ) % {
        "core": json.dumps(str(MODULE)),
        "ui": json.dumps(str(ROOT / "templates" / "government-revenue-briefcase-ui.js")),
        "workspace": json.dumps(workspace),
    }
    path = tmp_path / "briefcase_ui_mount.js"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["available"] is True
    assert out["applied"] == {
        "mode": "opportunities", "truth": "defense", "q": "radar",
        "agency": "Department of Defense", "ticker": "LMT",
    }
    assert len(out["state"]["saved_views"]) == 1
    assert out["state"]["alerts"][0]["type"] == "opportunity"
    assert out["state"]["alerts"][0]["primed"] is True
    assert out["state"]["inbox"] == []
    assert "baseline checked" in out["status"]
    assert out["toggle"] == "Disable local alert"
