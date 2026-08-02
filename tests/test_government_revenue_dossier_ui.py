"""Premium, fail-closed award-book UI contracts for Government Revenue."""
from __future__ import annotations

import json
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
        'src="government-revenue-dossiers.js"',
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
          querySelectorAll:function(q){if(q==='[data-award-key]'&&this.innerHTML.indexOf('data-award-key')>=0)return[{dataset:{awardKey:'award-1'},addEventListener:function(k,f){listeners[k]=f}}];if(q==='[data-subaward-key]'&&this.innerHTML.indexOf('data-subaward-key')>=0)return[{dataset:{subawardKey:'subaward:one'},addEventListener:function(k,f){listeners.evidence=f}}];return[]},
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
        setTimeout(function(){var book=host.innerHTML;listeners.click();setTimeout(function(){var detail=host.innerHTML;listeners.evidence();setTimeout(function(){process.stdout.write(JSON.stringify({book:book,detail:detail,calls:calls,shellModes:shellModes,drawer:{title:drawer.title,html:drawer.html}}))},5)},5)},5);
        """
    ) % {"responses": json.dumps(responses), "dossier_js": DOSSIER_JS}
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
    ):
        assert marker in out["detail"]
    assert "<script>alert(1)</script>" not in out["detail"]
    assert out["shellModes"][-1] is True
    assert out["drawer"]["title"] == "Subaward evidence"
    assert "&lt;b&gt;detail&lt;/b&gt;" in out["drawer"]["html"]
    assert "<b>detail</b>" not in out["drawer"]["html"]
    assert out["calls"] == list(responses)


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
                  listeners.evidence();listeners.back();deferred.evidence();setTimeout(function(){
                    process.stdout.write(JSON.stringify({afterMore:afterMore,afterList:afterList,final:host.innerHTML,drawer:drawer,calls:calls}));
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
