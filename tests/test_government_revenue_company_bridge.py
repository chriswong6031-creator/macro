"""Hostile test matrix for D4 -- Company Financial Truth Bridge (IRDM only).

Frozen spec: research/defense_intelligence/DEFENSE_D4_COMPANY_FINANCIAL_TRUTH_BRIDGE_SPEC.md
Consumption law: agentos/decisions/DEC-D4-COMPANY-RAIL-CONSUMES-CI-V1-CONTEXT.md

The harness below mirrors the D2 Identity Atlas precedent
(tests/test_government_revenue_identity_atlas.py::_run_committed_atlas): it
loads the SHIPPED templates/government-revenue-dossiers.js unmodified and
mounts the real `createGovernmentRevenueCompanyBridge` factory against a
fetch stub that records every requested URL and answers with
per-test-configurable fixtures. The government fact comes from the
committed site/government-revenue-data/workspace.json exemplar event
(govws-a6c70850a9cbdce9fa3e7f3b, HC101319C0006 / P00032) exactly as D3/D2
do, so a silent drift in the artifact's field names fails these tests too.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOSSIER_JS_PATH = ROOT / "templates" / "government-revenue-dossiers.js"
WORKSPACE_PATH = ROOT / "site" / "government-revenue-data" / "workspace.json"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")

BANNED_LABEL_WORDS_EN = ("revenue", "backlog", "bookings", "cash", "fcf")
BANNED_LABEL_WORDS_ZH = ("收入", "积压", "预订", "现金", "自由现金流")


# ---------------------------------------------------------------------------
# Committed-artifact fixture
# ---------------------------------------------------------------------------


def _committed_gov_event() -> dict:
    """The real, committed P00032 workspace event -- not a synthetic double."""
    workspace = json.loads(WORKSPACE_PATH.read_text(encoding="utf-8"))
    for event in workspace["events"]:
        award = event.get("award_change") or {}
        action_id = str(award.get("action_id") or "")
        if award.get("piid") == "HC101319C0006" and "_P00032_" in action_id:
            return event
    raise AssertionError("committed HC101319C0006 / P00032 workspace event was not found")


GOV_EVENT = _committed_gov_event()


# ---------------------------------------------------------------------------
# Company / candidate fixture builders
# ---------------------------------------------------------------------------


def _company_packet(**overrides) -> dict:
    packet = {
        "available": True,
        "schema": "company_intelligence_context.v1",
        "generation_id": "ci-fixture-a",
        "generated_at": "2026-08-20T06:52:58Z",
        "status": "partial",
        "latest_event": {
            "event_id": "cie_77ff210df9c064c3b2fe4aa1",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "call_date": "2026-04-23",
            "claim_citations_pending": True,
            "summary": "SCORE_OVERLAY_SUMMARY_SENTINEL_TEXT",
            "positive_highlights": [
                "Strong demand for L-band government services.",
                "New multi-year contract signed with a commercial partner.",
                "SCORE_OVERLAY_POSITIVE_SENTINEL",
            ],
            "negative_highlights": [
                "Guidance softened for the back half of FY26.",
                "SCORE_OVERLAY_NEGATIVE_SENTINEL",
                "Foreign-exchange headwinds noted on the call.",
            ],
            "metrics": {
                "revenue_growth_pct": 4.2,
                "risk_score": 987654,
            },
            "field_lineage": {
                "summary": "score_overlay",
                "metrics": {"revenue_growth_pct": "earnings_history", "risk_score": "score_overlay"},
                "positive_highlights": ["earnings_history", "earnings_history", "score_overlay"],
                "negative_highlights": ["earnings_history", "score_overlay", "earnings_history"],
            },
            "sources": [
                {"kind": "transcript", "status": "present"},
                {"kind": "press_release", "status": "present"},
            ],
        },
    }
    packet.update(overrides)
    return packet


def _candidates_payload(candidates=None) -> dict:
    return {
        "contract": "government_revenue_candidate_queue.v1",
        "schema_version": "1.0.0",
        "content_id": "grcq1-" + "a" * 24,
        "total": 1,
        "candidates": (
            candidates
            if candidates is not None
            else [
                {
                    "ticker": "IRDM",
                    "issuer": {"ticker": "IRDM", "company_name": "Iridium Communications"},
                    "materiality": {
                        "comparison_state": "not_comparable",
                        "reason_code": "exact_issuer_attributed_denominator_not_available",
                        "issuer_attributed_denominator": None,
                        "materiality_ratio": None,
                    },
                }
            ]
        ),
    }


# ---------------------------------------------------------------------------
# Node harness
# ---------------------------------------------------------------------------


def _bridge_node_script(body: str, *, events: list[dict] | None = None) -> str:
    dossier_js = DOSSIER_JS_PATH.read_text(encoding="utf-8")
    events = events if events is not None else [GOV_EVENT]
    scaffold = """
        var window = globalThis;
        var LANG = 'en';
        var EVENTS = __EVENTS__;
        var fetchCalls = [];
        var FIXTURES = {
          company: null, companyStatus: 200, companyReject: false,
          candidates: null, candidatesStatus: 200, candidatesReject: false
        };
        window.fetch = function(url){
          fetchCalls.push(url);
          if (url.indexOf('/api/company-intelligence/') === 0) {
            if (FIXTURES.companyReject) return Promise.reject(new Error('network'));
            var s = FIXTURES.companyStatus;
            return Promise.resolve({ok: s >= 200 && s < 300, status: s,
              json: function(){ return Promise.resolve(FIXTURES.company); }});
          }
          if (url.indexOf('government-revenue-data/candidates.json') === 0) {
            if (FIXTURES.candidatesReject) return Promise.reject(new Error('network'));
            var cs = FIXTURES.candidatesStatus;
            return Promise.resolve({ok: cs >= 200 && cs < 300, status: cs,
              json: function(){ return Promise.resolve(FIXTURES.candidates); }});
          }
          return Promise.reject(new Error('unexpected_url:' + url));
        };
        __DOSSIER_JS__
        function obj(x){ return !!x && typeof x === 'object' && !Array.isArray(x); }
        function arr(x){ return Array.isArray(x) ? x : []; }
        function esc(x){ return String(x == null ? '' : x).replace(/[&<>"']/g, function(c){
          return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
        function text(x, fb){ return x == null || x === '' ? (fb == null ? '\\u2014' : fb) : String(x); }
        function n(x){ if (x == null || x === '' || typeof x === 'boolean') return null;
          var v = Number(x); return Number.isFinite(v) ? v : null; }
        function date(x){ return String(x || '\\u2014').slice(0, 10); }
        function tr(en, cn){ return LANG === 'zh' ? cn : en; }
        function safeUrl(x){ try { var u = new URL(String(x || ''), 'https://example.invalid/');
          return u.protocol === 'https:' ? u.href : ''; } catch (e) { return ''; } }
        function factCell(labelCopy, value){ return '<div class="fact-cell"><span>' + esc(labelCopy) +
          '</span><b>' + esc(value == null || value === '' ? '\\u2014' : value) + '</b></div>'; }
        function host(){ return {innerHTML: '', hidden: false}; }
        function mount(evts){
          var h = host();
          var ui = window.createGovernmentRevenueCompanyBridge({
            obj: obj, arr: arr, esc: esc, text: text, n: n, date: date, tr: tr, safeUrl: safeUrl,
            factCell: factCell, host: function(){ return h; },
            workspaceEvents: function(){ return evts || EVENTS; }
          });
          return {host: h, ui: ui};
        }
        __BODY__
    """
    return (
        textwrap.dedent(scaffold)
        .replace("__EVENTS__", json.dumps(events))
        .replace("__DOSSIER_JS__", dossier_js)
        .replace("__BODY__", textwrap.dedent(body))
    )


def _run_bridge(tmp_path: Path, name: str, body: str, *, events: list[dict] | None = None) -> dict:
    path = tmp_path / name
    path.write_text(_bridge_node_script(body, events=events), encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def _gov_block(html: str) -> str:
    """Isolate the Government Fact sub-block: from the top of the module's
    innerHTML up to (not including) the second `.atlas-sub` label div, which
    is always the Company Truth header."""
    first = html.index('<div class="inspect-label">')
    second = html.index('<div class="inspect-label">', first + 1)
    return html[:second]


def _comparison_block(html: str) -> str:
    labels = [m.start() for m in re.finditer(r'<div class="inspect-label">', html)]
    assert len(labels) == 4, "expected exactly 4 sub-block headers"
    return html[labels[2] : labels[3]]


# ---------------------------------------------------------------------------
# T1 -- government stability
# ---------------------------------------------------------------------------


@needs_node
def test_t1_government_block_is_byte_identical_across_packet_variation(tmp_path: Path) -> None:
    variants = [
        ("company_ok", "FIXTURES.company = __PACKET_OK__; FIXTURES.candidates = __CANDIDATES__;"),
        ("company_absent", "FIXTURES.companyStatus = 404;"),
        (
            "company_mutated",
            "FIXTURES.company = Object.assign({}, __PACKET_OK__, {generated_at: '2099-01-01T00:00:00Z'});"
            "FIXTURES.candidates = __CANDIDATES__;",
        ),
    ]
    blocks = {}
    for tag, setup in variants:
        setup = setup.replace("__PACKET_OK__", json.dumps(_company_packet())).replace(
            "__CANDIDATES__", json.dumps(_candidates_payload())
        )
        body = f"""
            {setup}
            var m = mount();
            m.ui.loadCompany('IRDM');
            setTimeout(function(){{
              process.stdout.write(JSON.stringify({{html: m.host.innerHTML}}));
            }}, 40);
        """
        out = _run_bridge(tmp_path, f"t1_{tag}.js", body)
        blocks[tag] = _gov_block(out["html"])

    identical = set(blocks.values())
    assert len(identical) == 1, blocks

    gov_html = next(iter(identical))
    assert "HC101319C0006" in gov_html
    assert "P00032" in gov_html
    assert "$18,416,666.66" in gov_html
    assert "2026-05-12" in gov_html  # took effect
    assert "2026-08-12" in gov_html  # first known to Mastermind
    assert 'class="truth late"' in gov_html  # is_late_discovery === true on the committed event


# ---------------------------------------------------------------------------
# T2 -- label law
# ---------------------------------------------------------------------------


@needs_node
def test_t2_label_law_en_and_zh(tmp_path: Path) -> None:
    for lang, banned in (("en", BANNED_LABEL_WORDS_EN), ("zh", BANNED_LABEL_WORDS_ZH)):
        body = f"""
            LANG = {json.dumps(lang)};
            FIXTURES.company = {json.dumps(_company_packet())};
            FIXTURES.candidates = {json.dumps(_candidates_payload())};
            var m = mount();
            m.ui.loadCompany('IRDM');
            setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
        """
        out = _run_bridge(tmp_path, f"t2_{lang}.js", body)
        gov_html = _gov_block(out["html"]).lower()
        for word in banned:
            assert word.lower() not in gov_html, (lang, word, gov_html)
        # The one permitted label is present in the government block.
        assert ("obligation" in gov_html if lang == "en" else "拨款义务" in gov_html)


# ---------------------------------------------------------------------------
# T3 -- revenue present, no denominator
# ---------------------------------------------------------------------------


@needs_node
def test_t3_revenue_facts_present_still_yield_not_comparable_with_no_ratio_node(tmp_path: Path) -> None:
    packet = _company_packet()
    packet["latest_event"]["positive_highlights"][0] = "Government services revenue grew 12% year over year."
    body = f"""
        FIXTURES.company = {json.dumps(packet)};
        FIXTURES.candidates = {json.dumps(_candidates_payload())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t3.js", body)
    comparison = _comparison_block(out["html"])
    assert "not comparable" in comparison.lower() or "不可比" in comparison
    assert "%" not in comparison
    assert "ratio" not in comparison.lower()
    assert re.search(r"\d", comparison) is None, comparison


# ---------------------------------------------------------------------------
# T4 -- backlog word, no attribution
# ---------------------------------------------------------------------------


@needs_node
def test_t4_backlog_highlight_is_verbatim_commentary_with_zero_attribution(tmp_path: Path) -> None:
    packet = _company_packet()
    packet["latest_event"]["negative_highlights"][0] = "Funded backlog declined slightly quarter over quarter."
    packet["latest_event"]["field_lineage"]["negative_highlights"][0] = "earnings_history"
    body = f"""
        FIXTURES.company = {json.dumps(packet)};
        FIXTURES.candidates = {json.dumps(_candidates_payload())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t4.js", body)
    html = out["html"]
    assert "Funded backlog declined slightly quarter over quarter." in html
    comparison = _comparison_block(html)
    assert "not comparable" in comparison.lower() or "不可比" in comparison
    assert "attribut" not in comparison.lower() or "no issuer-attributed denominator" in comparison.lower()


# ---------------------------------------------------------------------------
# T5 -- unavailable typing
# ---------------------------------------------------------------------------


@needs_node
@pytest.mark.parametrize(
    "setup",
    [
        "FIXTURES.companyStatus = 404;",
        "FIXTURES.companyReject = true;",
        "FIXTURES.company = Object.assign({}, __PACKET__, {available: false});",
        "FIXTURES.company = Object.assign({}, __PACKET__, {schema: 'company_intelligence_context.v0'});",
    ],
)
def test_t5_unavailable_typing_renders_the_honest_state_not_zero_not_a_forever_spinner(
    tmp_path: Path, setup: str
) -> None:
    setup = setup.replace("__PACKET__", json.dumps(_company_packet()))
    body = f"""
        {setup}
        FIXTURES.candidates = {json.dumps(_candidates_payload())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t5.js", body)
    html = out["html"]
    assert "Company packet unavailable" in html
    assert "aria-busy" not in html
    assert "$0" not in html


# ---------------------------------------------------------------------------
# T6 -- estimates null
# ---------------------------------------------------------------------------


@needs_node
def test_t6_no_estimate_vocabulary_anywhere_in_the_section(tmp_path: Path) -> None:
    body = f"""
        FIXTURES.company = {json.dumps(_company_packet())};
        FIXTURES.candidates = {json.dumps(_candidates_payload())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t6.js", body)
    assert "estimate" not in out["html"].lower()


# ---------------------------------------------------------------------------
# T7 -- restatement
# ---------------------------------------------------------------------------


@needs_node
def test_t7_restatement_updates_company_block_keeps_government_block_identical(tmp_path: Path) -> None:
    packet_a = _company_packet(generated_at="2026-08-19T00:00:00Z")
    packet_a["latest_event"]["call_date"] = "2026-01-15"
    packet_b = _company_packet(generated_at="2026-08-20T06:52:58Z")
    packet_b["latest_event"]["call_date"] = "2026-04-23"
    body = f"""
        var candidates = {json.dumps(_candidates_payload())};
        FIXTURES.candidates = candidates;
        var m = mount();
        FIXTURES.company = {json.dumps(packet_a)};
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{
          var first = m.host.innerHTML;
          FIXTURES.company = {json.dumps(packet_b)};
          m.ui.loadCompany('IRDM');
          setTimeout(function(){{
            var second = m.host.innerHTML;
            process.stdout.write(JSON.stringify({{first: first, second: second}}));
          }}, 40);
        }}, 40);
    """
    out = _run_bridge(tmp_path, "t7.js", body)
    first_gov, second_gov = _gov_block(out["first"]), _gov_block(out["second"])
    assert first_gov == second_gov
    assert "2026-01-15" in out["first"]
    assert "2026-04-23" in out["second"]
    assert out["first"] != out["second"]


# ---------------------------------------------------------------------------
# T8 -- no wire parsing, single-endpoint allowlist
# ---------------------------------------------------------------------------


@needs_node
def test_t8_fetch_targets_are_only_company_intelligence_and_candidates_artifact(tmp_path: Path) -> None:
    body = f"""
        FIXTURES.company = {json.dumps(_company_packet())};
        FIXTURES.candidates = {json.dumps(_candidates_payload())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{calls: fetchCalls}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t8.js", body)
    calls = out["calls"]
    assert calls, "expected at least one fetch"
    for url in calls:
        assert "irdm-2026q1-call-record" not in url
        assert "stocks/earnings" not in url
        allowed = url.startswith("/api/company-intelligence/") or url.startswith(
            "government-revenue-data/candidates.json"
        )
        assert allowed, url


# ---------------------------------------------------------------------------
# T9 -- IRDM only
# ---------------------------------------------------------------------------


@needs_node
def test_t9_non_irdm_company_renders_no_bridge_section_and_fetches_nothing(tmp_path: Path) -> None:
    body = """
        FIXTURES.company = null;
        var m = mount();
        m.ui.loadCompany('LMT');
        setTimeout(function(){
          process.stdout.write(JSON.stringify({html: m.host.innerHTML, hidden: m.host.hidden, calls: fetchCalls}));
        }, 40);
    """
    out = _run_bridge(tmp_path, "t9.js", body)
    assert out["hidden"] is True
    assert out["html"] == ""
    assert out["calls"] == []


@needs_node
def test_t9_irdm_selection_unhides_the_host(tmp_path: Path) -> None:
    body = f"""
        FIXTURES.company = {json.dumps(_company_packet())};
        FIXTURES.candidates = {json.dumps(_candidates_payload())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{hidden: m.host.hidden}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t9b.js", body)
    assert out["hidden"] is False


# ---------------------------------------------------------------------------
# T10 -- lineage filter
# ---------------------------------------------------------------------------


@needs_node
def test_t10_score_overlay_lineage_fields_never_render(tmp_path: Path) -> None:
    body = f"""
        FIXTURES.company = {json.dumps(_company_packet())};
        FIXTURES.candidates = {json.dumps(_candidates_payload())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t10.js", body)
    html = out["html"]
    assert "SCORE_OVERLAY_SUMMARY_SENTINEL_TEXT" not in html
    assert "SCORE_OVERLAY_POSITIVE_SENTINEL" not in html
    assert "SCORE_OVERLAY_NEGATIVE_SENTINEL" not in html
    assert "987654" not in html  # risk_score metric, lineage score_overlay


@needs_node
def test_t10_revenue_growth_with_score_overlay_lineage_is_excluded(tmp_path: Path) -> None:
    packet = _company_packet()
    packet["latest_event"]["metrics"]["revenue_growth_pct"] = 55.5
    packet["latest_event"]["field_lineage"]["metrics"]["revenue_growth_pct"] = "score_overlay"
    body = f"""
        FIXTURES.company = {json.dumps(packet)};
        FIXTURES.candidates = {json.dumps(_candidates_payload())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t10b.js", body)
    assert "55.5" not in out["html"]


# ---------------------------------------------------------------------------
# Additional gate coverage (§0 gates not carved into their own T-number)
# ---------------------------------------------------------------------------


@needs_node
def test_comparison_copy_is_fixed_regardless_of_candidate_reachability(tmp_path: Path) -> None:
    """§0 gate 3: 'if unreachable (gated/absent) fail closed to the same copy.'"""
    variants = {
        "reachable": json.dumps(_candidates_payload()),
        "absent": "null",
        "wrong_ticker": json.dumps(_candidates_payload(candidates=[{"ticker": "LMT", "materiality": {}}])),
    }
    outputs = {}
    for tag, candidates_js in variants.items():
        reject = "FIXTURES.candidatesStatus = 404;" if tag == "absent" else f"FIXTURES.candidates = {candidates_js};"
        body = f"""
            FIXTURES.company = {json.dumps(_company_packet())};
            {reject}
            var m = mount();
            m.ui.loadCompany('IRDM');
            setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
        """
        out = _run_bridge(tmp_path, f"comparison_{tag}.js", body)
        outputs[tag] = _comparison_block(out["html"])
        assert "not comparable" in outputs[tag].lower() or "不可比" in outputs[tag]

    # The primary sentence (first <p>) is identical no matter what the
    # candidate artifact says -- only an optional trailing note may vary.
    first_paras = {tag: re.search(r"<p[^>]*>.*?</p>", html, re.S).group(0) for tag, html in outputs.items()}
    assert len(set(first_paras.values())) == 1, first_paras


@needs_node
def test_no_zero_no_forever_spinner_on_committed_event_happy_path(tmp_path: Path) -> None:
    body = f"""
        FIXTURES.company = {json.dumps(_company_packet())};
        FIXTURES.candidates = {json.dumps(_candidates_payload())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "happy_path.js", body)
    html = out["html"]
    assert "aria-busy" not in html
    assert "Company packet unavailable" not in html
    assert "Wording verification pending" in html or "措辞核验中" in html
    assert "transcript: present" in html.lower()
