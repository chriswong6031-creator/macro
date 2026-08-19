"""Premium, fail-closed award-book UI contracts for Government Revenue."""
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
DOSSIER_JS = (ROOT / "templates" / "government-revenue-dossiers.js").read_text(encoding="utf-8")
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")


def test_dossier_ui_is_progressive_and_semantically_precise() -> None:
    for marker in (
        'data-sync src="government-revenue-dossiers.js"',
        'id="dossierBook"',
        "Official award book",
        "Stable award identity",
        "generated USAspending award ID",
        "Obligated",
        "Current value",
        "Potential ceiling",
        "Effective at",
        "Known at",
        "Official action tape",
        "Subaward ledger",
        "Count verified",
        "subrecipient",
        "subaward_generation_mismatch",
        "Load more awards",
        "Load more actions",
        "None is GAAP backlog or reported revenue",
        "schema_version!=='1.0.0'",
        "generation_mismatch",
    ):
        assert marker in TEMPLATE or marker in DOSSIER_JS

    assert "win probability" not in DOSSIER_JS.lower()
    assert "bidder score" not in DOSSIER_JS.lower()
    assert "curated_fuzzy_name" not in DOSSIER_JS
    assert TEMPLATE.count('id="dossierBook"') == 1


@needs_node
def test_dossier_runtime_loads_one_generation_and_escapes_source_text(tmp_path: Path) -> None:
    content_id = "grd1-" + "a" * 24
    subaward_content_id = "grsd1-" + "b" * 24
    responses = {
        "/api/government-revenue/dossier/company/LMT": {
            "schema_version": "1.0.0",
            "content_id": content_id,
            "company": {"ticker": "LMT", "action_count": 1},
        },
        "/api/government-revenue/company/LMT/awards?limit=8": {
            "schema_version": "1.0.0",
            "content_id": content_id,
            "source_coverage": {"scope": "bounded official sample"},
            "freshness": {"status": "ok"},
            "results": [
                {
                    "award_key": "award-1",
                    "identity": {"generated_award_id": "CONT_AWD_1", "piid": "PIID-1"},
                    "description": "<img src=x onerror=alert(1)>",
                    "agency": {"awarding": "Department of Defense"},
                    "values": {"obligated": 12_500_000},
                }
            ],
            "next_cursor": None,
            "total": 1,
        },
        "/api/government-revenue/award/award-1": {
            "schema_version": "1.0.0",
            "content_id": content_id,
            "award": {
                "award_key": "award-1",
                "identity": {"generated_award_id": "CONT_AWD_1", "piid": "PIID-1"},
                "description": "Precision interceptor sustainment",
                "recipient": {"name": "Acme Defense"},
                "agency": {"awarding": "Department of Defense"},
                "dates": {
                    "effective_at": "2026-07-31",
                    "known_at": "2026-08-01T01:00:00Z",
                    "end_date": "2027-09-30",
                },
                "values": {
                    "obligated": 12_500_000,
                    "current_award_value": 30_000_000,
                    "ceiling": 90_000_000,
                },
                "source": {"award_page_url": "https://www.usaspending.gov/award/CONT_AWD_1/"},
            },
        },
        "/api/government-revenue/award/award-1/actions?limit=20": {
            "schema_version": "1.0.0",
            "content_id": content_id,
            "results": [
                {
                    "action_id": "action-1",
                    "action_type_description": "New obligation",
                    "effective_at": "2026-07-31",
                    "known_at": "2026-08-01T01:00:00Z",
                    "obligation": 12_500_000,
                }
            ],
            "next_cursor": None,
            "total": 1,
        },
        "/api/government-revenue/award/award-1/subawards?limit=25": {
            "schema_version": "1.0.0",
            "content_id": subaward_content_id,
            "parent_coverage": {
                "status": "ok",
                "collection_state": "complete",
                "reported_count": 1,
                "records_published": 1,
            },
            "results": [
                {
                    "subaward_key": "subaward:one",
                    "identity": {
                        "source_subaward_id": "native-one",
                        "displayed_subaward_number": "display-one",
                    },
                    "subawardee_name": "<script>alert(1)</script>",
                    "description": "Precision component build",
                    "description_truncated": False,
                    "dates": {"action_date": "2026-08-01"},
                    "reported_amount": {"amount": 125_000},
                }
            ],
            "next_cursor": None,
            "total": 1,
        },
        "/api/government-revenue/award/award-1/idv-relationships": {
            "schema_version": "1.0.0",
            "content_id": "griv1-" + "c" * 24,
            "authority": {
                "tier": "display", "context_only": True, "can_rank": False,
                "can_size": False, "can_gate": False, "can_originate_signal": False,
                "can_add_candidates": False, "can_escalate": False,
            },
            "source_coverage": {"status": "ok", "reason": "Exact activity page retained."},
            "selection_provenance": {
                "status": "verified",
                "selection_source": "official_usaspending_idv_discovery",
                "selection_manifest_id": "idvsel1-" + "e" * 24,
                "reviewed_at": "2026-08-01T00:00:00Z",
                "selected_parent_count": 24,
                "scope_hashes": {
                    "recipient_scope_sha256": "a" * 64,
                    "filters_semantic_sha256": "b" * 64,
                    "reviewed_manifest_sha256": None,
                },
            },
            "award_coverage": {
                "status": "observed",
                "exhaustive": False,
                "exact_relationship_count": 1,
                "selected_parent_count": 24,
                "selection_manifest_id": "idvsel1-" + "e" * 24,
                "reason": "Published exact generated-ID relationship observations for this award in the bounded active IDV cut.",
            },
            "relationships": [{
                "relationship_key": "idvrel:" + "d" * 32,
                "child_award_key": "award-1",
                "identity": {
                    "idv_generated_award_id": "CONT_IDV_PARENT_1",
                    "child_generated_award_id": "CONT_AWD_1",
                    "relationship_depth": "direct_child",
                    "parent_piid": "PARENT-PIID",
                    "child_piid": "PIID-1",
                },
                "recipient_name": "Acme Defense",
                "agency": "Department of Defense",
                "dates": {"start_date": "2026-07-31", "potential_end_date": "2027-09-30"},
                "source": {"activity_url": "https://api.usaspending.gov/api/v2/idvs/activity/"},
                "provenance": {"receipt_id": "idv-receipt", "response_sha256": "b" * 64, "source_record_count": 1, "known_at": "2026-08-02T00:00:00Z", "collection_scope_ticker": "LMT", "limitations": ["Relationship only."]},
            }],
            "total": 1,
        },
        "/api/government-revenue/subaward/subaward%3Aone": {
            "schema_version": "1.0.0",
            "content_id": subaward_content_id,
            "subaward": {
                "subaward_key": "subaward:one",
                "identity": {"source_subaward_id": "native-one", "parent_generated_award_id": "CONT_AWD_1"},
                "subawardee_name": "<script>alert(1)</script>",
                "description": "<b>detail</b>",
                "description_truncated": False,
                "dates": {"action_date": "2026-08-01", "known_at": "2026-08-02T00:00:00Z"},
                "reported_amount": {"amount": 125_000},
                "provenance": {"receipt_id": "receipt-1", "response_sha256": "a" * 64, "source_record_count": 1, "limitations": ["stored observation"]},
                "source": {"subaward_url": "https://api.usaspending.gov/api/v2/subawards/", "parent_award_url": "https://www.usaspending.gov/award/CONT_AWD_1/"},
            },
        },
    }
    script = textwrap.dedent(
        """
        var window=globalThis, calls=[], selected='company:LMT', listeners={}, shellModes=[], drawer=null;
        var host={innerHTML:'',insertAdjacentHTML:function(_,x){this.innerHTML+=x},
          querySelectorAll:function(q){if(q==='[data-award-key]'&&this.innerHTML.indexOf('data-award-key')>=0)return[{dataset:{awardKey:'award-1'},addEventListener:function(k,f){listeners[k]=f}}];if(q==='[data-subaward-key]'&&this.innerHTML.indexOf('data-subaward-key')>=0)return[{dataset:{subawardKey:'subaward:one'},addEventListener:function(k,f){listeners.evidence=f}}];if(q==='[data-idv-key]'&&this.innerHTML.indexOf('data-idv-key')>=0)return[{dataset:{idvKey:'idvrel:%(idv_key)s'},addEventListener:function(k,f){listeners.idvEvidence=f}}];return[]},
          querySelector:function(){return null}};
        var responses=%(responses)s;
        window.fetch=function(url){calls.push(url);var value=responses[url];return Promise.resolve({ok:!!value,status:value?200:404,json:function(){return Promise.resolve(value)}})};
        %(dossier_js)s
        function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)}
        function arr(x){return Array.isArray(x)?x:[]}
        function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
        function text(x,fb){return x==null||x===''?(fb==null?'—':fb):String(x)}
        function n(x){var v=Number(x);return Number.isFinite(v)?v:null}
        function money(x){return x==null?'—':'$'+Number(x).toLocaleString('en-US')}
        function date(x){return String(x||'—').slice(0,10)}
        function tr(x){return x}
        function safeUrl(x){try{var u=new URL(String(x));return u.protocol==='https:'?u.href:''}catch(e){return''}}
        function factCell(a,b){return'<div>'+esc(a)+': '+esc(b)+'</div>'}
        var ui=window.createGovernmentRevenueDossier({obj:obj,arr:arr,esc:esc,text:text,n:n,money:money,date:date,tr:tr,safeUrl:safeUrl,factCell:factCell,host:function(){return host},selected:function(){return selected},shellMode:function(open){shellModes.push(open)},openEvidenceDrawer:function(value){drawer=value}});
        ui.loadCompany('LMT');
        setTimeout(function(){var book=host.innerHTML;listeners.click();setTimeout(function(){var detail=host.innerHTML;listeners.idvEvidence();setTimeout(function(){var idvDrawer={title:drawer.title,html:drawer.html};listeners.evidence();setTimeout(function(){process.stdout.write(JSON.stringify({book:book,detail:detail,calls:calls,shellModes:shellModes,idvDrawer:idvDrawer,drawer:{title:drawer.title,html:drawer.html}}))},5)},5)},5)},5);
        """
    ) % {"responses": json.dumps(responses), "dossier_js": DOSSIER_JS, "idv_key": "d" * 32}
    test_path = tmp_path / "dossier_ui.js"
    test_path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(test_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)

    assert "Official award book" in out["book"]
    assert "&lt;img src=x onerror=alert(1)&gt;" in out["book"]
    assert "<img src=x" not in out["book"]
    for marker in (
        "Precision interceptor sustainment",
        "Obligated",
        "Current value",
        "Potential ceiling",
        "Effective at",
        "Known at",
        "Official action tape",
        "New obligation",
        "Subaward ledger",
        "1 verified detail",
        "Reported amount",
        "Precision component build",
        "&lt;script&gt;alert(1)&lt;/script&gt;",
        "Observed IDV relationships",
        "Exact relationship observed",
        "idvsel1-",
        "selected parents 24",
        "non-exhaustive",
        "CONT_IDV_PARENT_1",
        "Direct child of IDV",
        "Relationship-only",
    ):
        assert marker in out["detail"]
    assert "<script>alert(1)</script>" not in out["detail"]
    assert out["shellModes"][-1] is True
    assert out["drawer"]["title"] == "Subaward evidence"
    assert "&lt;b&gt;detail&lt;/b&gt;" in out["drawer"]["html"]
    assert "<b>detail</b>" not in out["drawer"]["html"]
    assert out["idvDrawer"]["title"] == "IDV relationship evidence"
    assert "CONT_IDV_PARENT_1" in out["idvDrawer"]["html"]
    assert "does not establish a vehicle seat, participation, utilization, conversion, award value, revenue, backlog, or issuer attribution" in out["idvDrawer"]["html"]
    assert out["calls"] == list(responses)


def test_dossier_ui_keeps_bounded_idv_non_observation_explicit() -> None:
    for marker in (
        "No exact bridge in this bounded cut",
        "this is not evidence that no IDV relationship exists",
        "Bounded non-observation only—not evidence that this award has no IDV relationship",
        "selection_manifest_id",
        "selected_parent_count",
        "non-exhaustive",
    ):
        assert marker in DOSSIER_JS


@needs_node
def test_dossier_runtime_preserves_award_and_action_evidence_when_subaward_rail_fails(
    tmp_path: Path,
) -> None:
    """A failed optional rail must never erase a verified prime dossier."""
    content_id = "grd1-" + "c" * 24
    responses = {
        "/api/government-revenue/dossier/company/LMT": {
            "schema_version": "1.0.0", "content_id": content_id, "company": {"ticker": "LMT"},
        },
        "/api/government-revenue/company/LMT/awards?limit=8": {
            "schema_version": "1.0.0", "content_id": content_id, "results": [
                {"award_key": "award-1", "identity": {"generated_award_id": "CONT_AWD_1"}, "description": "Prime award"}
            ], "next_cursor": None, "total": 1,
        },
        "/api/government-revenue/award/award-1": {
            "schema_version": "1.0.0", "content_id": content_id, "award": {
                "award_key": "award-1", "identity": {"generated_award_id": "CONT_AWD_1"},
                "description": "Prime award", "recipient": {"name": "Acme"}, "agency": {"awarding": "DoD"},
                "dates": {}, "values": {},
            },
        },
        "/api/government-revenue/award/award-1/actions?limit=20": {
            "schema_version": "1.0.0", "content_id": content_id,
            "results": [{"action_id": "action-1", "action_type_description": "Prime action", "effective_at": "2026-08-01", "obligation": 1}],
            "next_cursor": None, "total": 1,
        },
    }
    script = textwrap.dedent(
        """
        var window=globalThis, listeners={}, selected='company:LMT';
        var host={innerHTML:'',insertAdjacentHTML:function(_,x){this.innerHTML+=x},
          querySelectorAll:function(q){return q==='[data-award-key]'&&this.innerHTML.indexOf('data-award-key')>=0?[{dataset:{awardKey:'award-1'},addEventListener:function(_,f){listeners.award=f}}]:[]},
          querySelector:function(){return null}};
        var responses=%(responses)s;
        window.fetch=function(url){var value=responses[url];return Promise.resolve({ok:!!value,status:value?200:503,json:function(){return Promise.resolve(value)}})};
        %(dossier_js)s
        function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)} function arr(x){return Array.isArray(x)?x:[]}
        function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
        function text(x,fb){return x==null||x===''?(fb==null?'—':fb):String(x)} function n(x){var v=Number(x);return Number.isFinite(v)?v:null}
        function money(x){return x==null?'—':'$'+x} function date(x){return String(x||'—').slice(0,10)} function tr(x){return x} function safeUrl(){return''} function factCell(a,b){return'<div>'+a+b+'</div>'}
        var ui=window.createGovernmentRevenueDossier({obj:obj,arr:arr,esc:esc,text:text,n:n,money:money,date:date,tr:tr,safeUrl:safeUrl,factCell:factCell,host:function(){return host},selected:function(){return selected}});
        ui.loadCompany('LMT'); setTimeout(function(){listeners.award();setTimeout(function(){process.stdout.write(host.innerHTML)},10)},10);
        """
    ) % {"responses": json.dumps(responses), "dossier_js": DOSSIER_JS}
    test_path = tmp_path / "subaward_failure.js"
    test_path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(test_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "Prime award" in result.stdout
    assert "Prime action" in result.stdout
    assert "Subaward ledger unavailable" in result.stdout


@needs_node
def test_dossier_runtime_uses_server_subrecipient_query_and_cursor_page(tmp_path: Path) -> None:
    """Search and pagination are API-bound, rather than browser-side filtering."""
    prime_id, subaward_id = "grd1-" + "d" * 24, "grsd1-" + "e" * 24
    responses = {
        "/api/government-revenue/dossier/company/LMT": {"schema_version": "1.0.0", "content_id": prime_id, "company": {"ticker": "LMT"}},
        "/api/government-revenue/company/LMT/awards?limit=8": {"schema_version": "1.0.0", "content_id": prime_id, "results": [{"award_key": "award-1", "identity": {"generated_award_id": "CONT_AWD_1"}}], "next_cursor": None, "total": 1},
        "/api/government-revenue/award/award-1": {"schema_version": "1.0.0", "content_id": prime_id, "award": {"award_key": "award-1", "identity": {"generated_award_id": "CONT_AWD_1"}, "dates": {}, "values": {}}},
        "/api/government-revenue/award/award-1/actions?limit=20": {"schema_version": "1.0.0", "content_id": prime_id, "results": [], "next_cursor": None, "total": 0},
        "/api/government-revenue/award/award-1/subawards?limit=25": {"schema_version": "1.0.0", "content_id": subaward_id, "parent_coverage": {"status": "ok", "collection_state": "complete", "reported_count": 26, "records_published": 26}, "results": [{"subaward_key": "subaward:one", "identity": {}, "subawardee_name": "Atlas", "dates": {}, "reported_amount": {"amount": 1}}], "next_cursor": "cursor-2", "total": 26},
        "/api/government-revenue/award/award-1/subawards?limit=25&cursor=cursor-2": {"schema_version": "1.0.0", "content_id": subaward_id, "parent_coverage": {"status": "ok", "collection_state": "complete", "reported_count": 26, "records_published": 26}, "results": [{"subaward_key": "subaward:two", "identity": {}, "subawardee_name": "Beacon", "dates": {}, "reported_amount": {"amount": 2}}], "next_cursor": None, "total": 26},
        "/api/government-revenue/award/award-1/subawards?limit=25&subrecipient=Beacon": {"schema_version": "1.0.0", "content_id": subaward_id, "parent_coverage": {"status": "ok", "collection_state": "complete", "reported_count": 26, "records_published": 26}, "results": [{"subaward_key": "subaward:beacon", "identity": {}, "subawardee_name": "Beacon Works", "dates": {}, "reported_amount": {"amount": 3}}], "next_cursor": None, "total": 1},
    }
    script = textwrap.dedent(
        """
        var window=globalThis, listeners={}, calls=[], selected='company:LMT', input={value:'',addEventListener:function(k,f){listeners[k==='input'?'search':'searchKey']=f}};
        var host={innerHTML:'',insertAdjacentHTML:function(_,x){this.innerHTML+=x},
          querySelectorAll:function(q){return q==='[data-award-key]'&&this.innerHTML.indexOf('data-award-key')>=0?[{dataset:{awardKey:'award-1'},addEventListener:function(_,f){listeners.award=f}}]:[]},
          querySelector:function(q){if(q==='[data-subaward-search]'&&this.innerHTML.indexOf('data-subaward-search')>=0)return input;if(q==='[data-subaward-next]'&&this.innerHTML.indexOf('data-subaward-next')>=0)return{addEventListener:function(_,f){listeners.next=f}};return null}};
        var responses=%(responses)s; window.fetch=function(url){calls.push(url);var value=responses[url];return Promise.resolve({ok:!!value,status:value?200:404,json:function(){return Promise.resolve(value)}})};
        %(dossier_js)s
        function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)} function arr(x){return Array.isArray(x)?x:[]}
        function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
        function text(x,fb){return x==null||x===''?(fb==null?'—':fb):String(x)} function n(x){var v=Number(x);return Number.isFinite(v)?v:null}
        function money(x){return x==null?'—':'$'+x} function date(x){return String(x||'—').slice(0,10)} function tr(x){return x} function safeUrl(){return''} function factCell(a,b){return'<div>'+a+b+'</div>'}
        var ui=window.createGovernmentRevenueDossier({obj:obj,arr:arr,esc:esc,text:text,n:n,money:money,date:date,tr:tr,safeUrl:safeUrl,factCell:factCell,host:function(){return host},selected:function(){return selected}});
        ui.loadCompany('LMT');setTimeout(function(){listeners.award();setTimeout(function(){listeners.next();setTimeout(function(){input.value='Beacon';listeners.search.call(input);setTimeout(function(){process.stdout.write(JSON.stringify({calls:calls,html:host.innerHTML}))},270)},10)},10)},10);
        """
    ) % {"responses": json.dumps(responses), "dossier_js": DOSSIER_JS}
    test_path = tmp_path / "subaward_paging.js"
    test_path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(test_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "/api/government-revenue/award/award-1/subawards?limit=25&cursor=cursor-2" in out["calls"]
    assert "/api/government-revenue/award/award-1/subawards?limit=25&subrecipient=Beacon" in out["calls"]
    assert "Beacon Works" in out["html"]


@needs_node
def test_dossier_runtime_never_turns_verified_count_only_into_zero_details(tmp_path: Path) -> None:
    prime_id, subaward_id = "grd1-" + "f" * 24, "grsd1-" + "1" * 24
    responses = {
        "/api/government-revenue/dossier/company/LMT": {
            "schema_version": "1.0.0", "content_id": prime_id, "company": {"ticker": "LMT"},
        },
        "/api/government-revenue/company/LMT/awards?limit=8": {
            "schema_version": "1.0.0", "content_id": prime_id,
            "results": [{"award_key": "award-1", "identity": {"generated_award_id": "CONT_AWD_1"}}],
            "next_cursor": None, "total": 1,
        },
        "/api/government-revenue/award/award-1": {
            "schema_version": "1.0.0", "content_id": prime_id,
            "award": {"award_key": "award-1", "identity": {"generated_award_id": "CONT_AWD_1"}, "dates": {}, "values": {}},
        },
        "/api/government-revenue/award/award-1/actions?limit=20": {
            "schema_version": "1.0.0", "content_id": prime_id, "results": [], "next_cursor": None, "total": 0,
        },
        "/api/government-revenue/award/award-1/subawards?limit=25": {
            "schema_version": "1.0.0", "content_id": subaward_id,
            "parent_coverage": {
                "status": "partial", "collection_state": "high_count_count_only",
                "count_verified": True, "reported_count": 900, "records_published": 0,
                "truncated_by_collection_policy": True,
            },
            "results": [], "next_cursor": None, "total": 0,
        },
    }
    script = textwrap.dedent(
        """
        var window=globalThis,listeners={},selected='company:LMT';
        var host={innerHTML:'',insertAdjacentHTML:function(_,x){this.innerHTML+=x},
          querySelectorAll:function(q){return q==='[data-award-key]'&&this.innerHTML.indexOf('data-award-key')>=0?[{dataset:{awardKey:'award-1'},addEventListener:function(_,f){listeners.award=f}}]:[]},querySelector:function(){return null}};
        var responses=%(responses)s;window.fetch=function(url){var value=responses[url];return Promise.resolve({ok:!!value,status:value?200:404,json:function(){return Promise.resolve(value)}})};
        %(dossier_js)s
        function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)} function arr(x){return Array.isArray(x)?x:[]}
        function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
        function text(x,fb){return x==null||x===''?(fb==null?'—':fb):String(x)} function n(x){var v=Number(x);return Number.isFinite(v)?v:null}
        function money(x){return x==null?'—':'$'+x} function date(x){return String(x||'—').slice(0,10)} function tr(x){return x} function safeUrl(){return''} function factCell(a,b){return'<div>'+a+b+'</div>'}
        var ui=window.createGovernmentRevenueDossier({obj:obj,arr:arr,esc:esc,text:text,n:n,money:money,date:date,tr:tr,safeUrl:safeUrl,factCell:factCell,host:function(){return host},selected:function(){return selected}});
        ui.loadCompany('LMT');setTimeout(function(){listeners.award();setTimeout(function(){process.stdout.write(host.innerHTML)},10)},10);
        """
    ) % {"responses": json.dumps(responses), "dossier_js": DOSSIER_JS}
    test_path = tmp_path / "subaward_count_only.js"
    test_path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(test_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "Count verified · details not collected" in result.stdout
    assert "USAspending reported 900 subawards" in result.stdout
    assert "verified count-only state" in result.stdout
    assert "No subawards reported" not in result.stdout
    assert 'class="subaward-table"' not in result.stdout


@needs_node
def test_dossier_back_invalidates_pending_subaward_and_evidence_work(tmp_path: Path) -> None:
    """Late subaward work must not reclaim a dossier after its Back transition."""
    prime_id, subaward_id = "grd1-" + "9" * 24, "grsd1-" + "8" * 24
    responses = {
        "/api/government-revenue/dossier/company/LMT": {
            "schema_version": "1.0.0", "content_id": prime_id, "company": {"ticker": "LMT"},
        },
        "/api/government-revenue/company/LMT/awards?limit=8": {
            "schema_version": "1.0.0", "content_id": prime_id,
            "results": [{"award_key": "award-1", "identity": {"generated_award_id": "CONT_AWD_1"}, "description": "Prime award"}],
            "next_cursor": "book-cursor", "total": 2,
        },
        "/api/government-revenue/company/LMT/awards?limit=8&cursor=book-cursor": {
            "schema_version": "1.0.0", "content_id": prime_id,
            "results": [{"award_key": "award-2", "identity": {"generated_award_id": "CONT_AWD_2"}, "description": "Second award"}],
            "next_cursor": None, "total": 2,
        },
        "/api/government-revenue/award/award-1": {
            "schema_version": "1.0.0", "content_id": prime_id,
            "award": {"award_key": "award-1", "identity": {"generated_award_id": "CONT_AWD_1"}, "dates": {}, "values": {}},
        },
        "/api/government-revenue/award/award-1/actions?limit=20": {
            "schema_version": "1.0.0", "content_id": prime_id, "results": [], "next_cursor": None, "total": 0,
        },
        "/api/government-revenue/award/award-1/subawards?limit=25": {
            "schema_version": "1.0.0", "content_id": subaward_id,
            "parent_coverage": {"status": "ok", "collection_state": "complete", "reported_count": 1, "records_published": 1},
            "results": [{"subaward_key": "subaward:one", "identity": {}, "subawardee_name": "Atlas", "dates": {}, "reported_amount": {"amount": 1}}],
            "next_cursor": None, "total": 1,
        },
        "/api/government-revenue/award/award-1/subawards?limit=25&subrecipient=Stale": {
            "schema_version": "1.0.0", "content_id": subaward_id,
            "parent_coverage": {"status": "ok", "collection_state": "complete", "reported_count": 1, "records_published": 1},
            "results": [], "next_cursor": None, "total": 0,
        },
        "/api/government-revenue/subaward/subaward%3Aone": {
            "schema_version": "1.0.0", "content_id": subaward_id,
            "subaward": {"subaward_key": "subaward:one", "identity": {}, "subawardee_name": "Atlas", "dates": {}, "reported_amount": {"amount": 1}},
        },
    }
    script = textwrap.dedent(
        """
        var window=globalThis,listeners={},deferred={},calls=[],selected='company:LMT',drawer=null;
        var input={value:'',addEventListener:function(kind,fn){listeners[kind==='input'?'search':'searchKey']=fn}};
        var host={innerHTML:'',insertAdjacentHTML:function(_,x){this.innerHTML+=x},
          querySelectorAll:function(q){
            if(q==='[data-award-key]'&&this.innerHTML.indexOf('data-award-key')>=0)return[{dataset:{awardKey:'award-1'},addEventListener:function(_,fn){listeners.award=fn}}];
            if(q==='[data-subaward-key]'&&this.innerHTML.indexOf('data-subaward-key')>=0)return[{dataset:{subawardKey:'subaward:one'},addEventListener:function(_,fn){listeners.evidence=fn}}];
            return [];
          },
          querySelector:function(q){
            if(q==='[data-dossier-back]'&&this.innerHTML.indexOf('data-dossier-back')>=0)return{addEventListener:function(_,fn){listeners.back=fn}};
            if(q==='[data-more-awards]'&&this.innerHTML.indexOf('data-more-awards')>=0)return{addEventListener:function(_,fn){listeners.moreAwards=fn}};
            if(q==='[data-subaward-search]'&&this.innerHTML.indexOf('data-subaward-search')>=0)return input;
            return null;
          }};
        var responses=%(responses)s;
        function response(value){return{ok:!!value,status:value?200:404,json:function(){return Promise.resolve(value)}}}
        window.fetch=function(url){
          calls.push(url);
          if(url.indexOf('cursor=book-cursor')>=0)return new Promise(function(resolve){deferred.moreAwards=function(){resolve(response(responses[url]))}});
          if(url.indexOf('subrecipient=Stale')>=0)return new Promise(function(resolve){deferred.search=function(){resolve(response(responses[url]))}});
          if(url.indexOf('/subaward/subaward%%3Aone')>=0)return new Promise(function(resolve){deferred.evidence=function(){resolve(response(responses[url]))}});
          return Promise.resolve(response(responses[url]));
        };
        %(dossier_js)s
        function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)} function arr(x){return Array.isArray(x)?x:[]}
        function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
        function text(x,fb){return x==null||x===''?(fb==null?'—':fb):String(x)} function n(x){var v=Number(x);return Number.isFinite(v)?v:null}
        function money(x){return x==null?'—':'$'+x} function date(x){return String(x||'—').slice(0,10)} function tr(x){return x} function safeUrl(){return''} function factCell(a,b){return'<div>'+a+b+'</div>'}
        var ui=window.createGovernmentRevenueDossier({obj:obj,arr:arr,esc:esc,text:text,n:n,money:money,date:date,tr:tr,safeUrl:safeUrl,factCell:factCell,host:function(){return host},selected:function(){return selected},openEvidenceDrawer:function(value){drawer=value}});
        ui.loadCompany('LMT');setTimeout(function(){listeners.moreAwards();listeners.award();setTimeout(function(){
          deferred.moreAwards();setTimeout(function(){
            var afterMore=host.innerHTML;input.value='Stale';listeners.search.call(input);setTimeout(function(){
              listeners.back();deferred.search();setTimeout(function(){
                var afterList=host.innerHTML;listeners.award();setTimeout(function(){
                  // The evidence request is dispatched from inside withAuth()'s
                  // promise chain (the API is bearer-authenticated), so it is in
                  // flight one microtask after the click rather than during it.
                  // Yield before clicking back so this still pins what it always
                  // pinned: a request ALREADY IN FLIGHT, invalidated by back,
                  // whose late response must not paint.
                  listeners.evidence();setTimeout(function(){
                    listeners.back();deferred.evidence();setTimeout(function(){
                      process.stdout.write(JSON.stringify({afterMore:afterMore,afterList:afterList,final:host.innerHTML,drawer:drawer,calls:calls}));
                    },10);
                  },10);
                },10);
              },10);
            },270);
          },10);
        },10)},10);
        """
    ) % {"responses": json.dumps(responses), "dossier_js": DOSSIER_JS}
    test_path = tmp_path / "subaward_back_cancellation.js"
    test_path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(test_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)

    assert "dossier-detail" in out["afterMore"]
    assert "Official award book" in out["afterList"]
    assert "dossier-detail" not in out["afterList"]
    assert "Official award book" in out["final"]
    assert "dossier-detail" not in out["final"]
    assert out["drawer"] is None
    assert "/api/government-revenue/award/award-1/subawards?limit=25&subrecipient=Stale" in out["calls"]
    assert "/api/government-revenue/subaward/subaward%3Aone" in out["calls"]


@needs_node
def test_budget_program_runtime_uses_display_only_source_graph_and_receipts(tmp_path: Path) -> None:
    """The budget cockpit must be precomputed, receipt-first, and non-signal-bearing."""
    content_id = "grbg1-" + "a" * 24
    authority = {
        "tier": "display", "context_only": True, "can_rank": False,
        "can_size": False, "can_gate": False, "can_originate_signal": False,
        "can_add_candidates": False, "can_escalate": False,
    }
    program = {
        "program_key": "dod-program:procurement-line-item:department-of-air-force:1234:10",
        "kind": "procurement_line_item", "native_identifier": "10",
        "name": "<img src=x onerror=alert(1)>",
    }
    line = {
        "line_key": "dod:p1:department-of-air-force:1234:p1-line-item:10:fy2026:president-budget-request",
        "program_name": program["name"], "fiscal_year": 2026, "exhibit": "p1",
        "component": "Air Force", "appropriation_code": "1234", "budget_activity": "BA 5",
        "native_identifier": {"value": "10"},
        "amounts": [
            {"semantic": "president_budget_request_total", "amount_usd": 1500000},
            {"semantic": "discretionary_request", "amount_usd": 1400000},
            {"semantic": "reconciliation_request", "amount_usd": 100000},
            {"semantic": "prior_year_enacted_reference", "amount_usd": 900000},
        ],
        "known_at": "2026-08-02T00:00:00Z",
        "source": {"receipt_id": "p1-receipt", "document_sha256": "b" * 64, "source_url": "https://comptroller.war.gov/p1.pdf"},
        "provenance": {"page_number": 17, "page_text_sha256": "c" * 64},
    }
    coverage = {
        "president_budget_request": {"status": "ok", "reason": "Official P-1 evidence."},
        "authorization": {"status": "uncollected", "reason": "Not collected."},
        "appropriation_enacted": {"status": "uncollected", "reason": "Not collected."},
        "execution": {"status": "uncollected", "reason": "Not collected."},
    }
    listing = {
        "contract": "government_budget_program_graph.v1", "schema_version": "1.0.0", "content_id": content_id,
        "as_of": "2026-08-02", "known_at": "2026-08-02T00:00:00Z", "authority": authority,
        "source_coverage": coverage, "documents": [], "limitations": ["Request evidence only."], "programs": [program], "total": 1,
    }
    detail = {
        **listing, "program": program, "lines": [line],
        "documents": [{"receipt_id": "p1-receipt", "source_url": "https://comptroller.war.gov/p1.pdf", "extraction_semantic_sha256": "d" * 64}],
        "documentary_edges": [],
    }
    responses = {
        "/api/government-revenue/budget-programs": listing,
        "/api/government-revenue/program/dod-program%3Aprocurement-line-item%3Adepartment-of-air-force%3A1234%3A10": detail,
    }
    script = textwrap.dedent(
        """
        var window=globalThis, rows=[], drawer=null, selected='budget:dod-program:procurement-line-item:department-of-air-force:1234:10', listeners={};
        var host={className:'',innerHTML:'',querySelector:function(q){if(q==='[data-budget-evidence]'&&this.innerHTML.indexOf('data-budget-evidence')>=0)return{addEventListener:function(_,f){listeners.evidence=f},focus:function(){}};if(q==='[data-budget-copy]'&&this.innerHTML.indexOf('data-budget-copy')>=0)return{addEventListener:function(_,f){listeners.copy=f},textContent:''};return null}};
        var responses=%(responses)s;window.fetch=function(url){var value=responses[url];return Promise.resolve({ok:!!value,status:value?200:404,json:function(){return Promise.resolve(value)}})};
        %(dossier_js)s
        function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)} function arr(x){return Array.isArray(x)?x:[]}
        function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
        function text(x,fb){return x==null||x===''?(fb==null?'—':fb):String(x)} function n(x){var v=Number(x);return Number.isFinite(v)?v:null}
        function money(x){return x==null?'—':'$'+x} function date(x){return String(x||'—').slice(0,10)} function tr(x){return x} function safeUrl(x){return /^https:/.test(String(x||''))?String(x):''}
        var ui=window.createGovernmentRevenueBudget({obj:obj,arr:arr,esc:esc,text:text,n:n,money:money,date:date,tr:tr,safeUrl:safeUrl,host:function(){return host},isSelected:function(id){return id===selected},onRows:function(value){rows=value},openEvidenceDrawer:function(value){drawer=value},copyLink:function(){}});
        ui.load().then(function(){ui.render(rows[0]);setTimeout(function(){listeners.evidence();process.stdout.write(JSON.stringify({rows:rows,html:host.innerHTML,drawer:drawer}))},8)});
        """
    ) % {"responses": json.dumps(responses), "dossier_js": DOSSIER_JS}
    test_path = tmp_path / "budget_program_ui.js"
    test_path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(test_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)

    assert out["rows"][0]["kind"] == "budget_program"
    assert "Funding-stage firewall" in out["html"]
    assert "Request evidence is upstream—not funded revenue" in out["html"]
    assert "&lt;img src=x onerror=alert(1)&gt;" in out["html"]
    assert "<img src=x" not in out["html"]
    assert out["drawer"]["title"] == "DoD budget source chain"
    assert "page_text_sha256" in out["drawer"]["html"]
    assert "can_originate_signal: false" in out["drawer"]["html"]


@needs_node
def test_budget_graph_absence_is_projection_missing_not_empty_valid(tmp_path: Path) -> None:
    script = textwrap.dedent(
        """
        var window=globalThis, published=[];
        window.fetch=function(){return Promise.resolve({ok:false,status:503,json:function(){return Promise.resolve({})}})};
        %(dossier_js)s
        function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)} function arr(x){return Array.isArray(x)?x:[]}
        function esc(x){return String(x==null?'':x)} function text(x,fb){return x==null||x===''?(fb==null?'—':fb):String(x)}
        function n(x){var v=Number(x);return Number.isFinite(v)?v:null}
        function money(x){return String(x)} function date(x){return String(x||'')} function tr(x){return x} function safeUrl(){return ''}
        var ui=window.createGovernmentRevenueBudget({obj:obj,arr:arr,esc:esc,text:text,n:n,money:money,date:date,tr:tr,safeUrl:safeUrl,host:function(){return {className:'',innerHTML:'',querySelector:function(){return null}}},isSelected:function(){return false},onRows:function(rows,meta){published.push({rows:rows.length,status:meta.status})}});
        ui.load().then(function(){process.stdout.write(JSON.stringify({published:published,state:ui.state()}))});
        """
    ) % {"dossier_js": DOSSIER_JS}
    path = tmp_path / "budget_projection_missing.js"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["state"] == "projection_missing"
    assert out["published"][-1]["status"] == "projection_missing"
    assert out["published"][-1]["rows"] == 0


# --------------------------------------------------------------------------------------
# D2 Identity Atlas — the reviewed path from an exact award recipient up to a listed
# issuer. Its whole product job is to state an UNRESOLVED hop plainly instead of minting
# one, so these tests pin the honest states (not_asserted, conflict, listing_terminated)
# as hard as they pin the reviewed one.
# --------------------------------------------------------------------------------------
ATLAS_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "government_revenue" / "identity_atlas_pilot.json"
ATLAS_FIXTURE = json.loads(ATLAS_FIXTURE_PATH.read_text(encoding="utf-8"))
PARITY_CSS = (ROOT / "templates" / "government-revenue-parity.css").read_text(encoding="utf-8")

# The frozen unresolved sentence (D2 execution spec §6 / §0 gate 5). The Atlas composes
# it from public_security + attribution + the first gap, so this one string is the whole
# GE contract: verified security, unresolved recipient, not-asserted issuer.
GE_UNRESOLVED_COPY = (
    "Public security: verified · Government recipient attribution: unresolved · "
    "Exact issuer attribution: not asserted — no reviewed exact recipient → legal "
    "entity → GE Aerospace path."
)


def _atlas_node_script(body: str, responder: str) -> str:
    """Harness: the real factory, the real fixture, a stubbed cookie-plane fetch."""
    scaffold = """
        var window=globalThis, fetchCalls=[];
        var ATLAS=__ATLAS__;
        window.fetch=function(url){fetchCalls.push(String(url));return __RESPONDER__};
        __DOSSIER_JS__
        function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)}
        function arr(x){return Array.isArray(x)?x:[]}
        function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
        function text(x,fb){return x==null||x===''?(fb==null?'\\u2014':fb):String(x)}
        function n(x){if(x==null||x===''||typeof x==='boolean')return null;var v=Number(x);return Number.isFinite(v)?v:null}
        function date(x){return String(x||'\\u2014').slice(0,10)}
        function tr(en,cn){return LANG==='zh'?cn:en}
        function zhOn(){return LANG==='zh'}
        function safeUrl(x){try{var u=new URL(String(x||''),'https://example.invalid/');return u.protocol==='https:'?u.href:''}catch(e){return''}}
        function host(){var h={innerHTML:'',classes:{}};h.classList={add:function(k){h.classes[k]=true},remove:function(){for(var i=0;i<arguments.length;i++)delete h.classes[arguments[i]]}};return h}
        function mount(ticker){var h=host();var ui=window.createGovernmentRevenueIdentityAtlas({obj:obj,arr:arr,esc:esc,text:text,n:n,date:date,tr:tr,zh:zhOn,safeUrl:safeUrl,host:function(){return h}});ui.loadCompany(ticker);return{host:h,ui:ui}}
        __BODY__
    """
    return (
        textwrap.dedent(scaffold)
        .replace("__ATLAS__", json.dumps(ATLAS_FIXTURE))
        .replace("__RESPONDER__", responder)
        .replace("__DOSSIER_JS__", DOSSIER_JS)
        .replace("__BODY__", textwrap.dedent(body))
    )


def _run_atlas(tmp_path: Path, name: str, body: str, responder: str) -> dict:
    path = tmp_path / name
    path.write_text(_atlas_node_script(body, responder), encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


OK_RESPONDER = "Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(ATLAS)}})"


def test_identity_atlas_mounts_on_both_company_inspector_paths_only() -> None:
    """One host, both company paths, no new page / nav / header family."""
    assert TEMPLATE.count('id="identityAtlas"') == 1
    assert TEMPLATE.count("identityAtlasSection()") == 3  # definition + 2 call sites
    assert "createGovernmentRevenueIdentityAtlas" in TEMPLATE
    assert "global.createGovernmentRevenueIdentityAtlas=function(api)" in DOSSIER_JS

    # Both company inspector paths mount it, and both hand it the same ticker they hand
    # the award book — an Atlas that loads on one path only is the D2 acceptance gap.
    assert "atlasUI.loadCompany(atlasTicker)" in TEMPLATE
    assert "dossierUI.loadCompany(ticker);atlasUI.loadCompany(ticker);" in TEMPLATE
    assert TEMPLATE.count("identityAtlasSection()+dossierBookSection()") == 2
    # Identity is read before the award tape, never after it.
    assert "dossierBookSection()+identityAtlasSection()" not in TEMPLATE
    # Leaving a company inspector must not leave a stale path behind.
    assert TEMPLATE.count("atlasUI.invalidate()") == 3

    # Cookie plane, not the bearer plane: no Authorization header is ever attached.
    assert "government-revenue-data/identity_atlas.json" in DOSSIER_JS
    atlas_source = DOSSIER_JS.split("createGovernmentRevenueIdentityAtlas")[1].split(
        "global.createGovernmentRevenueBudget"
    )[0]
    assert "credentials:'same-origin'" in atlas_source
    assert "withAuth(" not in atlas_source
    assert "government_revenue_identity_atlas.v1" in atlas_source

    # No third page header family, no new nav entry, no viewport hijack.
    assert TEMPLATE.count('{% include "_site_nav.html.j2" %}') == 1
    assert "_public_nav" not in TEMPLATE
    for banned in ("scrollIntoView", "identity_atlas.html", "identityAtlas.html"):
        assert banned not in TEMPLATE + DOSSIER_JS, banned


def test_identity_atlas_state_inks_and_broken_rail_are_declared() -> None:
    """The rail's break is the section's honesty device — it has to exist in CSS."""
    assert ".truth.conflict{color:var(--gr-bad)}" in TEMPLATE
    assert ".truth.historic{color:var(--gr-muted)}" in TEMPLATE
    # A hop whose successor is not reviewed carries a DASHED connector, and an
    # unresolved node is hollow. Without these two rules an unresolved hop paints
    # exactly like a reviewed one and the section silently overclaims.
    assert ".atlas-hop.break:after{border-left-style:dashed" in PARITY_CSS
    assert (
        ".atlas-hop.unresolved .atlas-node{border-style:dashed;background:transparent"
        in PARITY_CSS
    )
    assert ".atlas-hop.historic .atlas-node:after{" in PARITY_CSS
    # Light is a design target, not a token swap (doctrine §5.8): opaque tinted panel
    # with genuinely white cards, or the dark-first "raised card" inverts into a smudge.
    assert 'html[data-theme="light"] .identity-atlas{background:' in PARITY_CSS
    assert 'html[data-theme="light"] .atlas-entity,' in PARITY_CSS
    # zh drops tracking on the caps rungs (design system §13).
    assert 'html[data-lang="zh"] .atlas-rung' in PARITY_CSS
    # Mobile is a deliberate reduction, not the desktop stack squeezed.
    assert ".atlas-id{grid-template-columns:minmax(0,1fr)}" in PARITY_CSS


@needs_node
def test_identity_atlas_runtime_renders_every_pilot_state(tmp_path: Path) -> None:
    # ONE factory for the whole session, exactly as the page builds it, walked across
    # every pilot the way a reader clicks from company to company.
    body = """
        var LANG='en';
        var current=host();
        var ui=window.createGovernmentRevenueIdentityAtlas({obj:obj,arr:arr,esc:esc,text:text,n:n,date:date,tr:tr,zh:zhOn,safeUrl:safeUrl,host:function(){return current}});
        var list=['IRDM','HII','LMT','GE','BWXT','SPR','NOC'],out={fetchCalls:null,html:{},classes:{}},i=0;
        function step(){
          if(i>=list.length){out.fetchCalls=fetchCalls;process.stdout.write(JSON.stringify(out));return}
          var ticker=list[i++];current=host();ui.loadCompany(ticker);
          setTimeout(function(){out.html[ticker]=current.innerHTML;out.classes[ticker]=Object.keys(current.classes);step()},20);
        }
        step();
    """
    out = _run_atlas(tmp_path, "atlas_states.js", body, OK_RESPONDER)

    # Fetched ONCE per session no matter how many issuers are inspected.
    assert out["fetchCalls"] == ["government-revenue-data/identity-atlas.json"]

    irdm = out["html"]["IRDM"]
    for marker in (
        "Reviewed issuer path",
        "Public security",
        "Legal issuer",
        "Legal entities",
        "Recipient identifiers",
        "Iridium Government Services LLC",
        "Wholly owned",
        "on record since 2025-12-3",
        "Watch — don’t chase",
        "Show identifiers, dates and receipts",
        "Reviewed",  # the identifier-row state word (identifierRows -> verification_state)
    ):
        assert marker in irdm, marker
    # No hop is unresolved and no field-name mismatch prints the "unclear" fallback --
    # the reviewed rail is unbroken end to end (FIX-2).
    assert "atlas-hop reviewed" in irdm
    assert "atlas-hop unresolved" not in irdm
    assert "State unclear" not in irdm
    # Technicals are demoted: the UEI, its sha256 and the known_at clock live inside the
    # receipt expand, never in the always-visible tier.
    head, _, receipts = irdm.partition('<details class="atlas-receipt">')
    assert "S77SW52LCR57" not in head
    assert "S77SW52LCR57" in receipts
    assert "sha256" not in head and "sha256" in receipts
    assert "known at" not in head and "known_at" not in head

    # GE: verified security, unresolved recipient, issuer NOT asserted — verbatim.
    # This is the frozen sentence composed from public_security + attribution +
    # the curated gaps[0] text, which is itself the frozen attribution_reason-class
    # copy the spec quotes literally (D2 execution spec §3).
    ge = out["html"]["GE"]
    assert GE_UNRESOLVED_COPY in ge
    assert "Stand aside" in ge
    assert "Identity unresolved" in ge
    assert "atlas-hop unresolved" in ge
    assert "atlas-hop reviewed break" in ge  # the security hop, then the break
    assert "atlas-entity" not in ge  # nothing is minted where the filing is silent
    assert "Reviewed issuer path" not in ge
    # Adjudicated 2026-08-18 (finding B6): a scope-observed, non-curated identifier
    # is NEVER named at issuer level -- GE's discovery scope contains unrelated
    # third-party companies, so nothing here is named, only an aggregate count.
    assert "atlas-gap" not in ge
    assert "5 recipient identifier(s) observed in the discovery file" in ge
    # The separation boundary is stated, and nothing is carried back across it.
    assert "GE HealthCare Technologies Inc." in ge
    assert "GE Vernova Inc." in ge
    assert "2023-01-03" in ge and "2024-04-02" in ge

    # BWXT: five reviewed chains AND three curated, evidence-backed unresolved
    # identifiers, one an explicit conflict -- and the Legal issuer hop must show
    # the reviewed canonical name, not "Not asserted" (this was FIX-2's blocker:
    # the UI previously read legal_issuer.verification_state, a field the
    # projector never emits, so BWXT's own issuer hop always misread as unresolved).
    bwxt = out["html"]["BWXT"]
    assert "Reviewed issuer path" in bwxt
    assert "Conflict on record" in bwxt
    assert "Link pending" in bwxt
    assert "BWX Technologies, Inc." in bwxt  # the Legal issuer hop's fact
    assert "BWXT ORDNANCE TENNESSEE, INC." in bwxt
    assert "atlas-gap conflict" in bwxt
    assert "records its parent as L3HARRIS TECHNOLOGIES, INC" in bwxt
    assert "reviewed, 3 still unresolved" in bwxt
    assert bwxt.count('class="atlas-entity ') == 6
    assert "State unclear" not in bwxt

    # SPR: historical, never live.
    spr = out["html"]["SPR"]
    assert "Listing terminated" in spr
    assert "listing ended 2025-12-0" in spr
    assert "Ignore" in spr
    assert "This listing has ended" in spr
    assert "atlas-hop historic" in spr
    assert "is-historic" in out["classes"]["SPR"]
    assert "Reviewed issuer path" not in spr
    assert "verified_live" not in spr

    # LMT: fourteen identifiers kept distinct under the single reviewed entity the
    # graph actually declares -- never flattened, never split.
    lmt = out["html"]["LMT"]
    assert "Holds 14 exact recipient identifiers" in lmt
    assert "LOCKHEED MARTIN CORP" in lmt
    # No third-party or scope-observed name is ever printed (finding B6); the
    # discovery-only overflow is an aggregate count, same law as GE.
    assert "recipient identifier(s) observed in the discovery file" in lmt

    # HII: every reviewed entity the graph actually declares renders, none merged away.
    hii = out["html"]["HII"]
    for name in (
        "Huntington Ingalls Incorporated",
        "HUNTINGTON INGALLS INDUSTRIES, INC.",
        "HII Nuclear Inc.",
    ):
        assert name in hii, name

    # A company with no atlas record says so; it never borrows another issuer's path.
    absent = out["html"]["NOC"]
    assert "No identity record for this company" in absent
    assert "Reviewed issuer path" not in absent

    # STRUCTURAL: the Atlas carries identity only, so it cannot leak attribution onto an
    # unlinked event (spec §5 test 4). Two separate checks, because an award-record URL
    # is a legitimate identity RECEIPT (the page where a UEI was observed) while an award
    # NAME, action or amount would be an attribution the Atlas is forbidden to make.
    everything = "".join(out["html"].values())
    at_rest = re.sub(r"<details.*?</details>", " ", everything, flags=re.S)
    visible = re.sub(r"<[^>]*>", " ", at_rest)  # drops every attribute, hrefs included
    for banned in (
        "award_key",
        "generated_award_id",
        "CONT_AWD",
        "obligat",
        "piid",
        "action_date",
        "$",
    ):
        assert banned not in visible, banned
    # Never anywhere, expanded or not: an event impact row, a dollar amount, or a
    # named award. The Atlas has no fields for them by construction.
    for banned in ("listed_company_impacts", "federal_action_obligation", "$", "award_key"):
        assert banned not in everything, banned


@needs_node
def test_identity_atlas_escapes_hostile_source_text(tmp_path: Path) -> None:
    # Looked up by ticker, not array position -- the fixture's own issuer order
    # is the projector's (alphabetical), not an index a test should hard-code.
    body = """
        var LANG='en';
        function byTicker(t){return ATLAS.issuers.find(function(r){return r.ticker===t})}
        var irdmRecord=byTicker('IRDM'),bwxtRecord=byTicker('BWXT');
        irdmRecord.company_name='<img src=x onerror=alert(1)>';
        irdmRecord.entities[1].canonical_name='<script>alert(2)</script>';
        bwxtRecord.unresolved_identifiers[0].observed_name='<b>GE</b>';
        irdmRecord.entities[1].evidence[0].url='javascript:alert(3)';
        var a=mount('IRDM'),b=mount('BWXT');
        setTimeout(function(){process.stdout.write(JSON.stringify({irdm:a.host.innerHTML,bwxt:b.host.innerHTML}))},40);
    """
    out = _run_atlas(tmp_path, "atlas_escape.js", body, OK_RESPONDER)
    assert "&lt;img src=x onerror=alert(1)&gt;" in out["irdm"]
    assert "<img src=x" not in out["irdm"]
    assert "<script>alert(2)</script>" not in out["irdm"]
    assert "&lt;b&gt;GE&lt;/b&gt;" in out["bwxt"]
    assert "javascript:" not in out["irdm"]


@needs_node
def test_identity_atlas_locked_degrades_to_the_membership_teaser(tmp_path: Path) -> None:
    """401 on the cookie plane is a product state, not an outage and not empty data."""
    body = """
        var LANG='en';
        var view=mount('IRDM');
        setTimeout(function(){process.stdout.write(JSON.stringify({html:view.host.innerHTML,state:view.ui.state(),calls:fetchCalls.length}))},40);
    """
    locked = _run_atlas(
        tmp_path,
        "atlas_locked.js",
        body,
        "Promise.resolve({ok:false,status:401,json:function(){return Promise.resolve({})}})",
    )
    assert locked["state"] == "locked"
    assert "Identity path locked" in locked["html"]
    assert "part of a membership" in locked["html"]
    assert '<a class="tool-btn" href="plans.html">' in locked["html"]
    assert "View membership plans" in locked["html"]
    # The teaser still says what stays open — never a bare lock.
    assert "Award history below stays open and is not issuer proof." in locked["html"]
    # A locked lane never claims a reviewed path, and never reads as an outage.
    assert "Reviewed issuer path" not in locked["html"]
    assert "unavailable" not in locked["html"]

    unavailable = _run_atlas(
        tmp_path,
        "atlas_unavailable.js",
        body,
        "Promise.resolve({ok:false,status:503,json:function(){return Promise.resolve({})}})",
    )
    assert unavailable["state"] == "unavailable"
    assert "Identity path unavailable" in unavailable["html"]
    assert "Award history below remains available" in unavailable["html"]
    assert "part of a membership" not in unavailable["html"]

    # A wrong contract is refused rather than half-rendered.
    invalid = _run_atlas(
        tmp_path,
        "atlas_invalid.js",
        body,
        "Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve("
        "{contract:'something_else.v1',schema_version:'1.0.0',issuers:ATLAS.issuers})}})",
    )
    assert invalid["state"] == "invalid"
    assert "Iridium" not in invalid["html"]


@needs_node
def test_identity_atlas_speaks_chinese_without_english_state_names(tmp_path: Path) -> None:
    body = """
        var LANG='zh';
        var ge=mount('GE'),spr=mount('SPR'),irdm=mount('IRDM');
        setTimeout(function(){process.stdout.write(JSON.stringify({ge:ge.host.innerHTML,spr:spr.host.innerHTML,irdm:irdm.host.innerHTML}))},40);
    """
    out = _run_atlas(tmp_path, "atlas_zh.js", body, OK_RESPONDER)
    for marker in ("身份未解析", "暂不参与", "未作断言", "上市证券", "收款方标识", "GE Aerospace 路径"):
        assert marker in out["ge"], marker
    for marker in ("上市已终止", "忽略", "在册公司历史"):
        assert marker in out["spr"], marker
    for marker in ("已核验发行人路径", "观察，不要追高", "全资持有", "显示标识、日期与凭证"):
        assert marker in out["irdm"], marker
    # No English state name is dropped into zh copy (doctrine §5.5).
    joined = out["ge"] + out["spr"] + out["irdm"]
    for leaked in (
        "Reviewed issuer path",
        "Link pending",
        "Identity unresolved",
        "Listing terminated",
        "Conflict on record",
        "not asserted",
        "Stand aside",
        "Watch —",
        "mapping_needed",
        "verified_live",
        "issuer_legal_entity",
    ):
        assert leaked not in joined, leaked


def test_identity_atlas_copy_is_bilingual_and_never_speaks_of_refutation() -> None:
    """Every string the Atlas adds ships an EN and a native-shaped ZH twin."""
    atlas_source = DOSSIER_JS.split("createGovernmentRevenueIdentityAtlas")[1].split(
        "global.createGovernmentRevenueBudget"
    )[0]
    implementation = TEMPLATE + atlas_source
    for english, chinese in (
        ("Identity Atlas", "身份图谱"),
        ("Tracing the identity path", "正在追踪身份路径"),
        (
            "Who the government actually paid, and how that reaches this ticker.",
            "政府实际付款给谁，以及这如何连到该股票代码。",
        ),
        ("Reviewed issuer path", "已核验发行人路径"),
        ("Link pending", "关联待核"),
        ("Identity unresolved", "身份未解析"),
        ("Conflict on record", "记录存在冲突"),
        ("Listing terminated", "上市已终止"),
        ("Public security", "上市证券"),
        ("Legal issuer", "法律发行主体"),
        ("Legal entities", "法律实体"),
        ("Recipient identifiers", "收款方标识"),
        ("Not asserted", "未作断言"),
        ("Where the trail stops", "线索中断之处"),
        ("Legal entities on record", "在册法律实体"),
        ("Corporate history on record", "在册公司历史"),
        ("Still unresolved", "仍未解析"),
        ("Identity path locked", "身份路径已锁定"),
        ("Identity path unavailable", "身份路径不可用"),
        ("View membership plans", "查看会员方案"),
        ("Show identifiers, dates and receipts", "显示标识、日期与凭证"),
        ("Show the evidence cut behind this path", "显示该路径背后的证据截点"),
        ("Stand aside", "暂不参与"),
        ("Ignore", "忽略"),
        ("Watch — don’t chase", "观察，不要追高"),
    ):
        assert english in implementation, english
        assert chinese in implementation, chinese

    # Falsifier / refutation vocabulary is never front-facing (operator 2026-07-27).
    for banned in ("falsifier", "refuted", "refutation", "Refutation", "证伪", "falsified"):
        assert banned not in implementation, banned

    # No translated text in title= (CI-guarded law).
    for chunk in re.findall(r'title="[^"]*"', implementation):
        assert not re.search(r"[一-鿿]", chunk), chunk

    # Glance-tier vocabulary: no internal state names, raw slugs or graph IDs outside the
    # receipt expands (doctrine Law 2). Everything machine-shaped lives behind
    # `entityReceipt` / `cutReceipt` and their `atlas-code` slabs.
    glance = atlas_source.split("function entityReceipt")[0]
    for banned in (
        "display tier",
        "display-tier",
        "context_only",
        "curated_fuzzy_name",
        "grc1-",
        "grmb1-",
        "defense21",
        "central:",
        "graph_digest",
    ):
        assert banned not in glance, banned

    # Display/context only: the Atlas states its own boundary and claims no authority.
    assert "It cannot rank a company, size a position or trigger a trade." in atlas_source
    assert "不得为公司排序、调整仓位或触发交易。" in atlas_source
    # No trade instruction ever — the stance vocabulary is the doctrine's, no more.
    for banned in ("Buy now", "Sell", "target price", "price target", "win probability"):
        assert banned not in atlas_source, banned


def test_identity_atlas_fixture_covers_the_six_pilot_states() -> None:
    """The fixture IS the acceptance surface — keep all six states in it."""
    assert ATLAS_FIXTURE["contract"] == "government_revenue_identity_atlas.v1"
    for key in ("schema_version", "generated_at", "graph_id", "graph_digest", "si_asof"):
        assert ATLAS_FIXTURE[key], key
    records = {row["ticker"]: row for row in ATLAS_FIXTURE["issuers"]}
    assert set(records) == {"IRDM", "HII", "LMT", "GE", "BWXT", "SPR"}

    assert records["IRDM"]["issuer_attribution"] == "reviewed"
    assert records["HII"]["issuer_attribution"] == "reviewed"
    assert sum(len(e["identifiers"]) for e in records["LMT"]["entities"]) == 14
    assert records["GE"]["issuer_attribution"] == "not_asserted"
    assert records["GE"]["entities"] == []
    # Adjudicated 2026-08-18 (finding B6): unresolved_identifiers is curated-only.
    # GE's discovery scope observed several unrelated third-party companies, which
    # the fixture -- regenerated FROM build_identity_atlas(), never hand-authored --
    # correctly names nowhere; they show up only as an aggregate count in gaps[].
    assert records["GE"]["unresolved_identifiers"] == []
    assert any(
        gap["code"] == "observed_identifiers_without_reviewed_path"
        for gap in records["GE"]["gaps"]
    )
    assert len(records["GE"]["separation_events"]) == 2
    assert len(records["BWXT"]["entities"]) == 6
    # BWXT keeps exactly the three curated, evidence-backed identifiers (spec §2's
    # refused trio) -- these ARE named, because each carries human review + evidence.
    assert len(records["BWXT"]["unresolved_identifiers"]) == 3
    assert [
        row["state"] for row in records["BWXT"]["unresolved_identifiers"]
    ].count("evidence_conflict") == 1
    assert records["SPR"]["public_security"]["state"] == "listing_terminated"
    assert records["SPR"]["issuer_attribution"] == "not_asserted"
    assert records["SPR"]["listing_events"][0]["effective_at"] == "2025-12-08"

    # Every reviewed-graph evidence citation is a real https receipt with a genuine
    # sha256 -- no bare, unciteable assertion. Curated evidence (unresolved
    # identifiers, listing/separation events) cites a URL but never claims a hash,
    # since it is a human-reviewed citation, not a strict content-addressed receipt.
    def walk(node) -> None:
        if isinstance(node, dict):
            if "url" in node and "content_sha256" in node:
                assert str(node["url"]).startswith("https://"), node["url"]
                assert len(str(node["content_sha256"])) == 64, node.get("evidence_id")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(ATLAS_FIXTURE)
