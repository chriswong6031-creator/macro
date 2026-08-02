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
    }
    script = textwrap.dedent(
        """
        var window=globalThis, calls=[], selected='company:LMT', listeners={};
        var host={innerHTML:'',insertAdjacentHTML:function(_,x){this.innerHTML+=x},
          querySelectorAll:function(q){return q==='[data-award-key]'&&this.innerHTML.indexOf('data-award-key')>=0?[{dataset:{awardKey:'award-1'},addEventListener:function(k,f){listeners[k]=f}}]:[]},
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
        var ui=window.createGovernmentRevenueDossier({obj:obj,arr:arr,esc:esc,text:text,n:n,money:money,date:date,tr:tr,safeUrl:safeUrl,factCell:factCell,host:function(){return host},selected:function(){return selected}});
        ui.loadCompany('LMT');
        setTimeout(function(){var book=host.innerHTML;listeners.click();setTimeout(function(){process.stdout.write(JSON.stringify({book:book,detail:host.innerHTML,calls:calls}))},5)},5);
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
    ):
        assert marker in out["detail"]
    assert out["calls"] == list(responses)
