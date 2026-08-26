"""D6-B1 packet 2 UI/fence/entitlement battery for the ninth FMS mode.

Mirrors ``tests/test_government_revenue_ui.py`` conventions. Covers the
merge-binding B12-B14 battery from
``research/defense_intelligence/DEFENSE_D6B1_FMS_IMPLEMENTATION_SPEC_2026-08-25.md``
§11:

* B12 -- the frozen U5 bilingual copy table (spec §9.3) is present verbatim in
  the template/JS, and mutating either the stage or amount standing negative
  fails.
* B13 -- the baked page stays inside the 303,104-byte page fence, and the FMS
  shell's own marginal contribution (tab + orchestration wiring only -- the
  inspector's rich U5 copy lives in the separate, unfenced
  ``government-revenue-dossiers.js``) stays inside the 8,192-byte shell
  budget.
* B14 -- both new routes reject an anonymous reader, and the baked HTML never
  embeds an FMS case body (only the entitled JSON does).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader

from app import government_revenue as api

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "government_revenue.html.j2"
TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")
DOSSIERS_JS = (ROOT / "templates" / "government-revenue-dossiers.js").read_text(encoding="utf-8")
SITE_PATH = ROOT / "site" / "government_revenue.html"
SITE = SITE_PATH.read_text(encoding="utf-8")

RAW_HTML_BUDGET_BYTES = 303_104
FMS_SHELL_DELTA_BUDGET_BYTES = 8_192

# The frozen U5 table (spec §9.3): (english, chinese) pairs that must appear
# verbatim somewhere in the mode's template/JS. The stage and amount negatives
# are singled out below for the mutation-fails-closed half of B12 because they
# are the two frozen sentences that most directly prevent 26-13 (spec §15.3)
# from ever reading as a signed sale.
U5_STAGE_POSITIVE = "Notified to Congress — not a signed sale"
U5_STAGE_POSITIVE_ZH = "已通知国会 — 尚非已签署军售"
U5_STAGE_NEGATIVE = "Later stage not observed"
U5_STAGE_NEGATIVE_ZH = "未观察到后续阶段"
U5_AMOUNT_LABEL = "Estimated notification value"
U5_AMOUNT_LABEL_ZH = "通知估算金额"
U5_AMOUNT_NEGATIVE = "Proposed-sale estimate — not an award, backlog, or revenue"
U5_AMOUNT_NEGATIVE_ZH = "拟议军售估算 — 并非合同授予、订单积压或收入"
U5_CLOCK_UNAVAILABLE = "Official notification date unavailable"
U5_CLOCK_UNAVAILABLE_ZH = "官方通知日期暂无"
U5_LINKAGE_CONTRACTOR = "Named in source — identity not reviewed"
U5_LINKAGE_CONTRACTOR_ZH = "来源点名 — 身份未审核"
U5_LINKAGE_PROGRAM = "Program link not reviewed"
U5_LINKAGE_PROGRAM_ZH = "项目关联未审核"
U5_ADVANCEMENT = "Requires official evidence of an offered, accepted, or implemented LOA"
U5_ADVANCEMENT_ZH = "须有官方证据证明 LOA 已提出、接受或实施"

U5_TABLE = (
    (U5_STAGE_POSITIVE, U5_STAGE_POSITIVE_ZH),
    (U5_STAGE_NEGATIVE, U5_STAGE_NEGATIVE_ZH),
    (U5_AMOUNT_LABEL, U5_AMOUNT_LABEL_ZH),
    (U5_AMOUNT_NEGATIVE, U5_AMOUNT_NEGATIVE_ZH),
    (U5_CLOCK_UNAVAILABLE, U5_CLOCK_UNAVAILABLE_ZH),
    (U5_LINKAGE_CONTRACTOR, U5_LINKAGE_CONTRACTOR_ZH),
    (U5_LINKAGE_PROGRAM, U5_LINKAGE_PROGRAM_ZH),
    (U5_ADVANCEMENT, U5_ADVANCEMENT_ZH),
)


# ---------------------------------------------------------------------------
# B12 -- frozen bilingual copy table, present verbatim; mutation fails closed.
# ---------------------------------------------------------------------------


def test_fms_tab_and_mode_wiring_present_in_the_shell() -> None:
    assert 'data-mode="fms"' in TEMPLATE
    assert 'id="countFms"' in TEMPLATE
    assert "FMS Congressional Notifications" in TEMPLATE
    assert "FMS 国会通知" in TEMPLATE
    assert "rowsByMode.fms" in TEMPLATE
    assert "fmsUI" in TEMPLATE
    assert "createGovernmentRevenueFms" in TEMPLATE
    assert "fms_case" in TEMPLATE


def _assert_u5_table_present_verbatim(haystack: str) -> None:
    """The real verbatim-presence check, factored out so the guard-the-guard
    test below can run it (and require it to fail) against mutated content
    instead of merely observing that Python string removal did what it did
    (spec §11b.13 -- the tautological U5-mutation test)."""
    for en, zh in U5_TABLE:
        assert en in haystack, f"missing frozen EN string: {en!r}"
        assert zh in haystack, f"missing frozen ZH string: {zh!r}"


def test_u5_frozen_bilingual_table_present_verbatim() -> None:
    """Every U5 EN/ZH pair (spec §9.3) is present verbatim somewhere in the mode.

    The rich per-card copy lives in the unfenced JS factory
    (``createGovernmentRevenueFms``); only the tab label is required to live
    in the byte-fenced HTML template (spec §9.1).
    """
    # Pin the canonical string count first -- a silently shrunk table would
    # otherwise still "pass" the loop below trivially (spec §11b.13).
    assert len(U5_TABLE) == 8
    haystack = TEMPLATE + DOSSIERS_JS
    _assert_u5_table_present_verbatim(haystack)


def test_u5_vocabulary_avoids_house_banned_words() -> None:
    """No falsifier vocabulary, no bare 'validated', 披露 never 申报 (house law)."""
    factory_start = DOSSIERS_JS.index("global.createGovernmentRevenueFms")
    factory_body = DOSSIERS_JS[factory_start:factory_start + 12000]
    banned_en = ("falsifier", "refuted", "thesis", "validated")
    for word in banned_en:
        assert word not in factory_body.lower(), f"banned vocabulary present: {word!r}"
    assert "申报" not in factory_body


@pytest.mark.parametrize(
    "verbatim",
    [
        U5_STAGE_NEGATIVE,
        U5_STAGE_NEGATIVE_ZH,
        U5_AMOUNT_NEGATIVE,
        U5_AMOUNT_NEGATIVE_ZH,
    ],
)
def test_mutating_the_frozen_negative_fails_the_verbatim_check(verbatim: str) -> None:
    """Guard the guard: a mutated/missing standing negative must fail B12.

    26-13 was notified 207+ days before the freeze with zero advancement
    evidence (spec §15.3); the stage/amount negatives are what stop a UI bug
    from ever reading that as a signed sale or a funded figure. If either
    sentence silently regressed, this must fail loudly here rather than at
    the hostile-canary stage.

    Runs the REAL verbatim-presence check (``_assert_u5_table_present_verbatim``)
    against the mutated haystack and requires it to raise. The prior version of
    this test only observed that ``str.replace`` had, in fact, replaced a
    substring -- true by construction and independent of whether the actual
    check function would ever notice (spec §11b.13).
    """
    assert verbatim in DOSSIERS_JS, f"test is stale -- frozen string no longer present: {verbatim!r}"
    corrupted = verbatim[:-1]  # drop the closing character -- no longer verbatim
    mutated_js = DOSSIERS_JS.replace(verbatim, corrupted)
    mutated_haystack = TEMPLATE + mutated_js
    with pytest.raises(AssertionError):
        _assert_u5_table_present_verbatim(mutated_haystack)


# ---------------------------------------------------------------------------
# B13 -- page fence (total) and FMS shell delta (marginal).
# ---------------------------------------------------------------------------


def test_generated_html_stays_inside_the_raw_edge_budget() -> None:
    """The baked page fence, measured against a FRESH render.

    The committed ``site/government_revenue.html`` predates this packet's
    FMS work entirely (it is rendered exclusively by the live-render lane --
    B1/out of scope here), so checking its byte size measures nothing about
    this branch's own impact on the fence (spec §11b.12). Re-point the
    measurement at the same render path ``test_fms_shell_delta_stays_inside_
    its_own_byte_budget`` below already uses for its own "with FMS" render.
    """
    rendered = _render(TEMPLATE).encode("utf-8")
    assert len(rendered) <= RAW_HTML_BUDGET_BYTES


def _strip_fms_shell(template_text: str) -> str:
    """Mechanically remove every D6-B1 packet-2 shell addition.

    Each removal below is the exact literal text inserted by this packet
    (never a heuristic regex over unrelated markup), so this reconstructs the
    pre-FMS template byte-for-byte regardless of git history/HEAD state --
    the mechanical "bake with the fms tab/section removed vs present"
    measurement the spec calls for (§11 B13), without depending on this
    branch never being squash-merged.
    """
    removals = [
        '\n      <button class="mode-tab" type="button" role="tab" aria-selected="false" tabindex="-1" data-mode="fms">{{ t(\'FMS Congressional Notifications\',\'FMS 国会通知\') }}<span class="mode-count" id="countFms">—</span></button>',
        ",fms:[]",
        ",fmsStatus='loading'",
        (
            "\n  // freshness.fms fallback applies ONLY with no module (mirrors budget above).\n"
            "  function fmsFailureState(){var wf=obj(WORKSPACE.freshness)?WORKSPACE.freshness:{},root=obj(DATA.freshness)?DATA.freshness:{},block=obj(wf.fms)?wf.fms:(obj(root.fms)?root.fms:null),fs=block&&block.failure_state;return fs==='projection_missing'||fs==='source_unavailable'?fs:null}\n"
            "  function fallbackFmsStatus(){var fs=fmsFailureState();return fs==='projection_missing'?'projection_missing':'unavailable'}"
        ),
        ",fms:tr('FMS Congressional Notifications','FMS 国会通知')",
        (
            "if(state.mode==='fms')return[fmsStatus==='loading'?tr('Verifying the FMS coverage manifest','正在核验 FMS 覆盖清单'):fmsStatus==='projection_missing'?tr('PROJECTION_MISSING','PROJECTION_MISSING'):"
            "tr('FMS notifications unavailable','FMS 通知暂不可用'),fmsStatus==='loading'?tr('Verifying the official-union coverage manifest before showing any case.','在显示任何案例前，正在核验官方联合覆盖清单。'):"
            "fmsStatus==='projection_missing'?tr('The FMS congressional-notification acquisition lane has not published a case graph on this desk yet, so this is not an empty notification month. Use the Change Tape.','FMS 国会通知采集链路尚未在本台发布案例图谱，因此这不是空通知月份。请使用变化脉搏。'):"
            "tr('No official-union coverage manifest is active in this evidence cut. No case was inferred.','当前证据截点没有生效的官方联合覆盖清单。未推断任何案例。')];"
        ),
        (
            "\n  var fmsUI=typeof window.createGovernmentRevenueFms==='function'?window.createGovernmentRevenueFms({obj:obj,arr:arr,esc:esc,text:text,n:n,money:money,date:date,tr:tr,safeUrl:safeUrl,host:function(){return $('inspector')},"
            "isSelected:function(id){return state.selected===id},openEvidenceDrawer:openEvidenceDrawer,copyLink:copyLink,setMobile:setMobileSummary,onRows:function(rows,meta){rowsByMode.fms=arr(rows).filter(obj);fmsStatus=text((meta||{}).status,'unavailable');"
            "syncCounts();populateFilters();if(state.mode==='fms'){state.selected='';applyFilters()}}}):(function(){fmsStatus=fallbackFmsStatus();return{load:function(){return Promise.resolve([])},refresh:function(){return[]},render:function(){},invalidate:function(){},state:function(){return fmsStatus}}})();"
        ),
        "if(!r||r.kind!=='fms_case')fmsUI.invalidate();",
        "if(r.kind==='fms_case'){fmsUI.render(r);return}",
        ";$('countFms').textContent=rowsByMode.fms.length",
        ",rowsByMode.fms",
        ";fmsUI.load()",
        ";fmsUI.refresh()",
        ",'fms'",
    ]
    stripped = template_text
    for needle in removals:
        assert needle in stripped, f"expected FMS shell fragment not found (test is stale): {needle[:80]!r}"
        stripped = stripped.replace(needle, "")
    return stripped


def _render(template_text: str) -> str:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    html = env.from_string(template_text.replace(
        '{% include "_interfonts.html.j2" %}', ""
    ).replace(
        '{% include "_seo_head.html.j2" %}', ""
    ).replace(
        '{% include "_site_nav.html.j2" %}', ""
    )).render(payload_json="{}", as_of="2026-01-01", known_at="2026-01-01T00:00:00+00:00")
    return "\n".join(line.rstrip() for line in html.splitlines()) + "\n"


def test_fms_shell_delta_stays_inside_its_own_byte_budget() -> None:
    with_fms = _render(TEMPLATE).encode("utf-8")
    without_fms = _render(_strip_fms_shell(TEMPLATE)).encode("utf-8")
    delta = len(with_fms) - len(without_fms)
    assert delta > 0, "FMS shell measured zero or negative bytes; the strip helper is stale"
    assert delta <= FMS_SHELL_DELTA_BUDGET_BYTES, f"FMS shell delta {delta} exceeds the {FMS_SHELL_DELTA_BUDGET_BYTES}-byte budget"


# ---------------------------------------------------------------------------
# B14 -- anonymous boundary + no case bodies in the baked HTML.
# ---------------------------------------------------------------------------


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    ["/api/government-revenue/fms-cases", "/api/government-revenue/fms-case/fms:transmittal:26-13"],
)
def test_fms_routes_reject_an_anonymous_reader(path: str) -> None:
    response = _client().get(path)
    assert response.status_code in (401, 403), (path, response.status_code)


def test_fms_case_key_validation_returns_422_not_500() -> None:
    response = _client().get("/api/government-revenue/fms-case/not-a-valid-key")
    # Anonymous still 401/403s first -- the router-wide dependency runs before
    # the path validator ever executes (spec §8: "no new auth").
    assert response.status_code in (401, 403)


def _authenticated_client() -> TestClient:
    """The house authenticated-client idiom (census: ``tests/test_capital_
    structure_api.py``'s ``client`` fixture) -- override the router's own
    ``require_site_full_user`` dependency so a request actually reaches the
    route body instead of dying at the anonymous 401/403 boundary."""
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_site_full_user] = lambda: {"id": "paid-user"}
    return TestClient(app)


def test_fms_case_key_validation_returns_422_when_authenticated() -> None:
    """spec §11b.13: the 422 malformed-case-key contract must actually be
    exercised, not merely inferred from the anonymous 401 that always fires
    first. ``fms_case`` validates the path param (line ~2923) BEFORE
    touching any data file, so this needs no fixture case graph on disk."""
    response = _authenticated_client().get("/api/government-revenue/fms-case/not-a-valid-key")
    assert response.status_code == 422


def test_fms_site_twin_is_not_in_the_public_allowlist() -> None:
    """The FMS site twin inherits the existing default-deny boundary (spec §13.2).

    No site_access.yml change ships in this packet -- ``/government-revenue-
    data/`` stays default-deny, so ``fms-cases.json`` is anonymous-locked the
    same way ``budget-program.json`` already is, with zero new entitlement
    plane.
    """
    site_access = (ROOT / "config" / "site_access.yml").read_text(encoding="utf-8")
    assert "fms-cases.json" not in site_access
    assert "government-revenue-data" not in re.sub(r"^\s*#.*$", "", site_access, flags=re.M)


def test_no_fms_case_body_is_embedded_in_the_baked_html() -> None:
    """Case data lives only in the entitled JSON; the HTML embeds none of it."""
    match = re.search(r'<script id="gov-data" type="application/json">(.*?)</script>', SITE, re.S)
    assert match, "generated page must carry its compact JSON shell"
    shell = json.loads(match.group(1).replace(r"<\/", "</"))
    assert "cases" not in shell
    assert "fms_cases" not in shell
    blob = json.dumps(shell)
    assert "congressional_notification" not in blob
    assert "grfms1-" not in blob
