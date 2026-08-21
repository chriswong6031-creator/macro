"""Hostile test matrix for D4 -- Company Financial Truth Bridge (IRDM only).

Frozen spec: research/defense_intelligence/DEFENSE_D4_COMPANY_FINANCIAL_TRUTH_BRIDGE_SPEC.md
Consumption law: agentos/decisions/DEC-D4-COMPANY-RAIL-CONSUMES-CI-V1-CONTEXT.md

Adversarial-review amendment (2026-08-20): this suite must be `gate: code`
(merge-binding), which means ZERO moving-data dependence. The P00032
exemplar event is therefore a FROZEN, committed test fixture
(tests/fixtures/govrev_company_bridge/p00032_event.json) rather than a live
read of the nightly-rewritten site/government-revenue-data/workspace.json --
this suite never reads site/government-revenue-data/ or
data/government_revenue/ at all. The government FACTS themselves (piid,
obligation, dates, receipt sha) are still the real committed truth; only the
READ PATH changed.

The harness loads the SHIPPED templates/government-revenue-dossiers.js
unmodified, and also extracts the REAL page helper functions (esc, text,
date, tr, zh, n, money, factCell, safeUrl, obj, arr) verbatim from
templates/government_revenue.html.j2 -- not hand-retyped stand-ins -- so a
regression in either file's real formatting/localization breaks this suite,
not just a private copy of it.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOSSIER_JS_PATH = ROOT / "templates" / "government-revenue-dossiers.js"
TEMPLATE_PATH = ROOT / "templates" / "government_revenue.html.j2"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "govrev_company_bridge" / "p00032_event.json"

TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")

BANNED_LABEL_WORDS_EN = ("revenue", "backlog", "bookings", "sales", "cash", "fcf")
BANNED_LABEL_WORDS_ZH = ("收入", "积压", "预订", "销售", "现金", "自由现金流")


# ---------------------------------------------------------------------------
# Committed fixture (frozen, gate:code safe -- no moving-data dependence)
# ---------------------------------------------------------------------------


def _load_gov_event() -> dict:
    event = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert event["award_change"]["piid"] == "HC101319C0006"
    assert "_P00032_" in event["award_change"]["action_id"]
    return event


GOV_EVENT = _load_gov_event()


# ---------------------------------------------------------------------------
# Real page helpers -- extracted verbatim from templates/government_revenue.html.j2,
# never hand-retyped, so this suite tracks the REAL production formatting/
# localization rather than a private stand-in copy of it.
# ---------------------------------------------------------------------------

_HELPER_NAMES = ["obj", "arr", "zh", "tr", "esc", "n", "text", "money", "date", "safeUrl", "factCell"]


def _extract_helper_line(name: str) -> str:
    pattern = re.compile(r"^  function " + re.escape(name) + r"\(.*$", re.M)
    match = pattern.search(TEMPLATE)
    assert match, f"real helper function {name!r} not found in government_revenue.html.j2 -- extraction pattern drifted"
    return match.group(0)


def _real_helpers_js() -> str:
    return "\n".join(_extract_helper_line(name) for name in _HELPER_NAMES)


REAL_HELPERS_JS = _real_helpers_js()


# ---------------------------------------------------------------------------
# Company packet fixture builder
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


# ---------------------------------------------------------------------------
# Node harness
# ---------------------------------------------------------------------------


def _bridge_node_script(body: str) -> str:
    dossier_js = DOSSIER_JS_PATH.read_text(encoding="utf-8")
    scaffold = """
        var window = globalThis;
        var LANG = 'en';
        var document = { documentElement: { getAttribute: function(name){
          return name === 'data-lang' ? LANG : 'en';
        } } };
        var location = { href: 'https://example.test/government_revenue.html' };
        var GOV_EVENT = __GOV_EVENT__;
        var fetchCalls = [];
        var FIXTURES = {
          company: null, companyStatus: 200, companyReject: false, companyHang: false
        };
        window.fetch = function(url){
          fetchCalls.push(url);
          if (url.indexOf('/api/company-intelligence/') === 0) {
            if (FIXTURES.companyHang) return new Promise(function(){});
            if (FIXTURES.companyReject) return Promise.reject(new Error('network'));
            var s = FIXTURES.companyStatus;
            return Promise.resolve({ok: s >= 200 && s < 300, status: s,
              json: function(){ return Promise.resolve(FIXTURES.company); }});
          }
          return Promise.reject(new Error('unexpected_url:' + url));
        };
        __REAL_HELPERS__
        __DOSSIER_JS__
        function host(){ return {innerHTML: '', hidden: false}; }
        function mount(opts){
          opts = opts || {};
          var h = host();
          var events = opts.events !== undefined ? opts.events : [GOV_EVENT];
          var ready = opts.workspaceComplete !== undefined ? opts.workspaceComplete : true;
          var api = {
            obj: obj, arr: arr, esc: esc, text: text, n: n, date: date, tr: tr, safeUrl: safeUrl,
            factCell: factCell, host: function(){ return h; },
            workspaceEvents: function(){ return events; },
            workspaceComplete: function(){ return ready; }
          };
          if (opts.timeoutMs !== undefined) api.companyFetchTimeoutMs = opts.timeoutMs;
          var ui = window.createGovernmentRevenueCompanyBridge(api);
          return {host: h, ui: ui};
        }
        __BODY__
    """
    return (
        textwrap.dedent(scaffold)
        .replace("__GOV_EVENT__", json.dumps(GOV_EVENT))
        .replace("__REAL_HELPERS__", REAL_HELPERS_JS)
        .replace("__DOSSIER_JS__", dossier_js)
        .replace("__BODY__", textwrap.dedent(body))
    )


def _run_bridge(tmp_path: Path, name: str, body: str) -> dict:
    path = tmp_path / name
    path.write_text(_bridge_node_script(body), encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def _gov_block(html: str) -> str:
    """Isolate the Government Fact sub-block: from the top of the module's
    innerHTML up to (not including) the second `.inspect-label` header div,
    which is always the Company Truth header (the module's own render()
    emits exactly four `.inspect-label` headers in a fixed order)."""
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
        ("company_ok", f"FIXTURES.company = {json.dumps(_company_packet())};"),
        ("company_absent", "FIXTURES.companyStatus = 404;"),
        (
            "company_mutated",
            "FIXTURES.company = "
            + json.dumps(_company_packet(generated_at="2099-01-01T00:00:00Z"))
            + ";",
        ),
    ]
    blocks = {}
    for tag, setup in variants:
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
    assert "May 12, 2026" in gov_html  # took effect, REAL date() formatting
    assert "Aug 12, 2026" in gov_html  # first known to Mastermind
    assert 'class="truth late"' in gov_html  # is_late_discovery === true on the fixture


# ---------------------------------------------------------------------------
# T2 -- label law (now includes "sales" per gate 2, R8)
# ---------------------------------------------------------------------------


@needs_node
def test_t2_label_law_en_and_zh(tmp_path: Path) -> None:
    for lang, banned in (("en", BANNED_LABEL_WORDS_EN), ("zh", BANNED_LABEL_WORDS_ZH)):
        body = f"""
            LANG = {json.dumps(lang)};
            FIXTURES.company = {json.dumps(_company_packet())};
            var m = mount();
            m.ui.loadCompany('IRDM');
            setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
        """
        out = _run_bridge(tmp_path, f"t2_{lang}.js", body)
        gov_html = _gov_block(out["html"]).lower()
        for word in banned:
            assert word.lower() not in gov_html, (lang, word, gov_html)
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
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t6.js", body)
    assert "estimate" not in out["html"].lower()


# ---------------------------------------------------------------------------
# T7 -- restatement (R7: memoized per ticker, so restatement lands on the
# NEXT fresh open, after invalidate() -- not on every re-selection of an
# already-open panel; see R7 in the module's loadCompanyPacket() comment).
# ---------------------------------------------------------------------------


@needs_node
def test_t7_restatement_updates_company_block_keeps_government_block_identical(tmp_path: Path) -> None:
    packet_a = _company_packet(generated_at="2026-08-19T00:00:00Z")
    packet_a["latest_event"]["call_date"] = "2026-01-15"
    packet_b = _company_packet(generated_at="2026-08-20T06:52:58Z")
    packet_b["latest_event"]["call_date"] = "2026-04-23"
    body = f"""
        var m = mount();
        FIXTURES.company = {json.dumps(packet_a)};
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{
          var first = m.host.innerHTML;
          m.ui.invalidate();
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
    assert "Jan 15, 2026" in out["first"]
    assert "Apr 23, 2026" in out["second"]
    assert out["first"] != out["second"]


# ---------------------------------------------------------------------------
# T8 -- no wire parsing, single-endpoint allowlist (amended: candidates
# artifact is now NEVER requested -- comparison is fixed closed-state copy).
# ---------------------------------------------------------------------------


@needs_node
def test_t8_only_fetch_target_is_company_intelligence_candidates_never_requested(tmp_path: Path) -> None:
    body = f"""
        FIXTURES.company = {json.dumps(_company_packet())};
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
        assert "candidates.json" not in url
        assert "government-revenue-candidate" not in url
        assert url.startswith("/api/company-intelligence/"), url


# ---------------------------------------------------------------------------
# T9 -- IRDM only
# ---------------------------------------------------------------------------


@needs_node
def test_t9_non_irdm_company_renders_no_bridge_section_and_fetches_nothing(tmp_path: Path) -> None:
    body = """
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
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "t10b.js", body)
    assert "55.5" not in out["html"]


# ---------------------------------------------------------------------------
# R2 -- bounded timeout, never an eternal spinner
# ---------------------------------------------------------------------------


@needs_node
def test_r2_hung_fetch_resolves_to_unavailable_via_the_bounded_timeout(tmp_path: Path) -> None:
    body = """
        FIXTURES.companyHang = true;
        var m = mount({timeoutMs: 20});
        m.ui.loadCompany('IRDM');
        setTimeout(function(){
          process.stdout.write(JSON.stringify({html: m.host.innerHTML}));
        }, 200);
    """
    out = _run_bridge(tmp_path, "r2_hung.js", body)
    html = out["html"]
    assert "Company packet unavailable" in html
    assert "aria-busy" not in html


# ---------------------------------------------------------------------------
# R4 -- correct receipt: the action's own transaction record, not the award
# snapshot (matched by content_sha256 against award_change.source_identity).
# ---------------------------------------------------------------------------


@needs_node
def test_r4_receipt_link_is_the_actions_own_transaction_receipt_not_the_award_snapshot(
    tmp_path: Path,
) -> None:
    want_sha = GOV_EVENT["award_change"]["source_identity"]["content_sha256"]
    want_receipt = next(r for r in GOV_EVENT["evidence"]["receipts"] if r["content_sha256"] == want_sha)
    other_receipt_urls = [
        r["url"] for r in GOV_EVENT["evidence"]["receipts"] if r["content_sha256"] != want_sha
    ]
    assert other_receipt_urls, "fixture must carry a decoy (award-snapshot) receipt to prove selectivity"

    body = f"""
        FIXTURES.company = {json.dumps(_company_packet())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "r4.js", body)
    gov_html = _gov_block(out["html"])
    assert f'href="{want_receipt["url"]}"' in gov_html
    for other_url in other_receipt_urls:
        assert f'href="{other_url}"' not in gov_html


# ---------------------------------------------------------------------------
# R14 -- receipt link fails CLOSED: an exact content_sha256 match is the only
# way a source link renders. No positional (rows[0]), URL-shape, or nearest-
# receipt fallback -- a missing match means NO link, never an unrelated
# receipt presented as "Open official receipt" (D4.1 amendment, 2026-08-21).
# ---------------------------------------------------------------------------


@needs_node
def test_r14a_no_receipt_carries_the_wanted_sha_yields_no_source_link(tmp_path: Path) -> None:
    mutated = copy.deepcopy(GOV_EVENT)
    mutated["award_change"]["source_identity"]["content_sha256"] = "f" * 64
    decoy_urls = [r["url"] for r in mutated["evidence"]["receipts"]]
    assert decoy_urls, "fixture must still carry receipts to prove they are never used as a fallback"

    body = f"""
        var m = mount({{events: [{json.dumps(mutated)}], workspaceComplete: true}});
        m.ui.loadCompany('IRDM');
        process.stdout.write(JSON.stringify({{html: m.host.innerHTML}}));
    """
    out = _run_bridge(tmp_path, "r14a.js", body)
    gov_html = _gov_block(out["html"])
    assert 'class="source-link"' not in gov_html, gov_html
    for url in decoy_urls:
        assert f'href="{url}"' not in gov_html


@needs_node
@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e["award_change"].pop("source_identity", None),
        lambda e: e["award_change"]["source_identity"].pop("content_sha256", None),
        lambda e: e["award_change"]["source_identity"].__setitem__("content_sha256", ""),
    ],
    ids=["source_identity_absent", "content_sha256_key_missing", "content_sha256_empty"],
)
def test_r14b_missing_source_identity_yields_no_source_link_never_an_arbitrary_receipt(
    tmp_path: Path, mutate
) -> None:
    mutated = copy.deepcopy(GOV_EVENT)
    mutate(mutated)
    receipt_urls = [r["url"] for r in mutated["evidence"]["receipts"]]
    assert receipt_urls, "fixture must still carry receipts to prove none get substituted"

    body = f"""
        var m = mount({{events: [{json.dumps(mutated)}], workspaceComplete: true}});
        m.ui.loadCompany('IRDM');
        process.stdout.write(JSON.stringify({{html: m.host.innerHTML}}));
    """
    out = _run_bridge(tmp_path, "r14b.js", body)
    gov_html = _gov_block(out["html"])
    assert 'class="source-link"' not in gov_html, gov_html
    for url in receipt_urls:
        assert f'href="{url}"' not in gov_html


@needs_node
def test_r14c_exact_match_with_a_rejected_url_shape_yields_no_source_link(tmp_path: Path) -> None:
    mutated = copy.deepcopy(GOV_EVENT)
    want_sha = mutated["award_change"]["source_identity"]["content_sha256"]
    for r in mutated["evidence"]["receipts"]:
        if r["content_sha256"] == want_sha:
            r["url"] = "javascript:alert(1)"  # safeUrl only accepts protocol 'https:'

    body = f"""
        var m = mount({{events: [{json.dumps(mutated)}], workspaceComplete: true}});
        m.ui.loadCompany('IRDM');
        process.stdout.write(JSON.stringify({{html: m.host.innerHTML}}));
    """
    out = _run_bridge(tmp_path, "r14c.js", body)
    gov_html = _gov_block(out["html"])
    assert 'class="source-link"' not in gov_html, gov_html
    assert "javascript:" not in gov_html


def _receipt_url_function_source() -> str:
    source = DOSSIER_JS_PATH.read_text(encoding="utf-8")
    marker = "function receiptUrl(event){"
    start = source.index(marker)
    depth = 0
    i = start + len(marker) - 1  # index of the opening brace
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
        i += 1
    raise AssertionError("receiptUrl() has unbalanced braces -- extraction pattern drifted")


def test_r14d_shipped_receipturl_source_carries_no_positional_fallback() -> None:
    """Mutation-discipline pin: asserts against the SHIPPED source text
    directly, so reintroducing `(wantSha && rows.find(...)) || rows[0]`
    stays red here even if a future harness change weakens R14a/R14b's
    runtime assertions."""
    fn_source = _receipt_url_function_source()
    assert "rows[0]" not in fn_source, fn_source
    assert re.search(r"\|\|\s*rows\b", fn_source) is None, fn_source


# ---------------------------------------------------------------------------
# R5 -- hydration-aware government fact state (loading vs genuinely absent)
# ---------------------------------------------------------------------------


@needs_node
def test_r5_events_empty_and_not_hydrated_shows_loading_not_unavailable(tmp_path: Path) -> None:
    body = """
        var m = mount({events: [], workspaceComplete: false});
        m.ui.loadCompany('IRDM');
        process.stdout.write(JSON.stringify({html: m.host.innerHTML}));
    """
    out = _run_bridge(tmp_path, "r5_loading.js", body)
    gov_html = _gov_block(out["html"])
    assert "aria-busy" in gov_html
    assert "Government fact unavailable" not in gov_html


@needs_node
def test_r5_events_empty_and_hydrated_shows_unavailable_not_a_spinner(tmp_path: Path) -> None:
    body = """
        var m = mount({events: [], workspaceComplete: true});
        m.ui.loadCompany('IRDM');
        process.stdout.write(JSON.stringify({html: m.host.innerHTML}));
    """
    out = _run_bridge(tmp_path, "r5_unavailable.js", body)
    gov_html = _gov_block(out["html"])
    assert "Government fact unavailable" in gov_html
    assert "aria-busy" not in gov_html


# ---------------------------------------------------------------------------
# R7 -- memoization: repeated selections don't refetch; invalidate() + a
# fresh selection retries (and picks up a restatement, see T7 above).
# ---------------------------------------------------------------------------


@needs_node
def test_r7_repeated_selection_of_the_same_ticker_does_not_refetch(tmp_path: Path) -> None:
    body = f"""
        FIXTURES.company = {json.dumps(_company_packet())};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{
          var callsAfterFirst = fetchCalls.length;
          m.ui.loadCompany('IRDM');
          m.ui.loadCompany('IRDM');
          setTimeout(function(){{
            process.stdout.write(JSON.stringify({{callsAfterFirst: callsAfterFirst, callsAfterRepeats: fetchCalls.length}}));
          }}, 20);
        }}, 40);
    """
    out = _run_bridge(tmp_path, "r7_memo.js", body)
    assert out["callsAfterFirst"] == 1
    assert out["callsAfterRepeats"] == 1


@needs_node
def test_r7_unavailable_result_is_not_cached_and_retries_on_a_fresh_selection(tmp_path: Path) -> None:
    body = f"""
        FIXTURES.companyStatus = 404;
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{
          var firstHtml = m.host.innerHTML;
          m.ui.invalidate();
          FIXTURES.companyStatus = 200;
          FIXTURES.company = {json.dumps(_company_packet())};
          m.ui.loadCompany('IRDM');
          setTimeout(function(){{
            process.stdout.write(JSON.stringify({{firstHtml: firstHtml, secondHtml: m.host.innerHTML, calls: fetchCalls.length}}));
          }}, 40);
        }}, 40);
    """
    out = _run_bridge(tmp_path, "r7_retry.js", body)
    assert "Company packet unavailable" in out["firstHtml"]
    assert "Company packet unavailable" not in out["secondHtml"]
    assert out["calls"] == 2


# ---------------------------------------------------------------------------
# R9 -- null/non-numeric growth is SKIPPED, never a "—" value claim
# ---------------------------------------------------------------------------


@needs_node
def test_r9_null_revenue_growth_skips_the_metric_row_entirely(tmp_path: Path) -> None:
    packet = _company_packet()
    packet["latest_event"]["metrics"]["revenue_growth_pct"] = None
    body = f"""
        FIXTURES.company = {json.dumps(packet)};
        var m = mount();
        m.ui.loadCompany('IRDM');
        setTimeout(function(){{ process.stdout.write(JSON.stringify({{html: m.host.innerHTML}})); }}, 40);
    """
    out = _run_bridge(tmp_path, "r9.js", body)
    assert "Revenue growth" not in out["html"]
    assert "收入增长" not in out["html"]


# ---------------------------------------------------------------------------
# R10 -- ticker-constrained match, latest known_at wins on multiple matches
# ---------------------------------------------------------------------------


@needs_node
def test_r10_event_matching_piid_and_mod_but_wrong_ticker_is_excluded(tmp_path: Path) -> None:
    decoy = copy.deepcopy(GOV_EVENT)
    decoy["listed_company_impacts"] = [{"ticker": "LMT"}]
    decoy["primary_ticker"] = "LMT"
    decoy["tickers"] = ["LMT"]
    body = f"""
        var m = mount({{events: [{json.dumps(decoy)}], workspaceComplete: true}});
        m.ui.loadCompany('IRDM');
        process.stdout.write(JSON.stringify({{html: m.host.innerHTML}}));
    """
    out = _run_bridge(tmp_path, "r10_wrong_ticker.js", body)
    gov_html = _gov_block(out["html"])
    assert "Government fact unavailable" in gov_html
    assert "$18,416,666.66" not in gov_html


@needs_node
def test_r10_multiple_matches_prefer_the_latest_known_at(tmp_path: Path) -> None:
    older = copy.deepcopy(GOV_EVENT)
    older["change"]["known_at"] = "2026-08-01T00:00:00+00:00"
    older["amounts"][0]["value"] = 1111111.11

    newer = copy.deepcopy(GOV_EVENT)
    newer["change"]["known_at"] = "2026-08-15T00:00:00+00:00"
    newer["amounts"][0]["value"] = 2222222.22

    body = f"""
        var m = mount({{events: [{json.dumps(older)}, {json.dumps(newer)}], workspaceComplete: true}});
        m.ui.loadCompany('IRDM');
        process.stdout.write(JSON.stringify({{html: m.host.innerHTML}}));
    """
    out = _run_bridge(tmp_path, "r10_latest.js", body)
    gov_html = _gov_block(out["html"])
    assert "$2,222,222.22" in gov_html
    assert "$1,111,111.11" not in gov_html


# ---------------------------------------------------------------------------
# R12 -- non-rounding, comma-grouped display (verbatim fractional digits)
# ---------------------------------------------------------------------------


@needs_node
def test_r12_obligation_display_never_rounds_extra_precision(tmp_path: Path) -> None:
    mutated = copy.deepcopy(GOV_EVENT)
    mutated["amounts"][0]["value"] = 18416666.659999967
    body = f"""
        var m = mount({{events: [{json.dumps(mutated)}]}});
        m.ui.loadCompany('IRDM');
        process.stdout.write(JSON.stringify({{html: m.host.innerHTML}}));
    """
    out = _run_bridge(tmp_path, "r12.js", body)
    gov_html = _gov_block(out["html"])
    # toFixed(2) would round this to $18,416,666.66, silently discarding the
    # extra precision the source number actually carries (Node's own
    # String(18416666.659999967) === "18416666.659999967", verified above
    # this module's docstring claims). The non-rounding formatter must show
    # that full value, comma-grouped, verbatim -- never the rounded one.
    assert "$18,416,666.659999967" in gov_html, gov_html
    assert "$18,416,666.66<" not in gov_html
    assert "$18,416,666.66 " not in gov_html


# ---------------------------------------------------------------------------
# R13 note: _gov_block()/_comparison_block() above already slice on the REAL
# `.inspect-label` sub-block headers (not a stray `.atlas-sub` reference).
# ---------------------------------------------------------------------------


@needs_node
def test_no_zero_no_forever_spinner_on_committed_fixture_happy_path(tmp_path: Path) -> None:
    body = f"""
        FIXTURES.company = {json.dumps(_company_packet())};
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


def test_no_moving_data_dependence() -> None:
    """gate:code law: this suite must never READ live/nightly-rewritten trees.

    Checks actual Path()/open()-style construction sites, not prose (this
    module's own docstrings and comments legitimately explain, by name, the
    live trees it deliberately avoids reading).
    """
    source = Path(__file__).read_text(encoding="utf-8")
    for banned in (
        r'ROOT\s*/\s*"site"\s*/\s*"government-revenue-data"',
        r'ROOT\s*/\s*"data"\s*/\s*"government_revenue"',
    ):
        assert not re.search(banned, source), banned
    assert FIXTURE_PATH == ROOT / "tests" / "fixtures" / "govrev_company_bridge" / "p00032_event.json"
