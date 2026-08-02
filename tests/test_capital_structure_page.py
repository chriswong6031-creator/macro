"""Capital Structure observed-filing-state desk shell and browser boundary."""
from __future__ import annotations

import re
import json
import shutil
import subprocess
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from scripts.build_capital_structure_page import render
from scripts import build_public_pages


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"


def _render_template() -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    return env.get_template("capital_structure.html.j2").render(
        active_section="research",
        active_page="capital_structure",
    )


def test_observed_desk_template_renders_bilingually_without_inline_application_code() -> None:
    html = _render_template()
    assert "{{" not in html and "{%" not in html and "{#" not in html
    assert "Observed Filing State" in html
    assert "已观察申报状态" in html
    assert html.count('class="l-en"') >= 20
    assert html.count('class="l-zh"') >= 20
    assert 'class="site-nav"' in html
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    executable_inline = re.findall(
        r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>(.*?)</script>", html, re.S,
    )
    assert executable_inline == []


def test_static_builder_writes_shell_and_exact_companion_assets(tmp_path: Path) -> None:
    isolated_templates = tmp_path / "templates"
    isolated_templates.mkdir()
    for name in (
        "capital_structure.html.j2",
        "capital_structure_boot.js",
        "capital_structure.css",
        "capital_structure.js",
        "_seo_head.html.j2",
        "_site_nav.html.j2",
        "_navlinks.html.j2",
    ):
        shutil.copyfile(TEMPLATES / name, isolated_templates / name)

    page = render(tmp_path)
    isolated_site = tmp_path / "site"
    assert page == isolated_site / "capital_structure.html"
    html = page.read_text(encoding="utf-8")
    assert not re.search(r"[ \t]+$", html, re.M)
    assert 'data-dbase' in html
    assert 'href="capital_structure.css"' in html
    assert 'src="capital_structure_boot.js"' in html
    assert 'src="capital_structure.js"' in html
    assert (isolated_site / "capital_structure_boot.js").read_bytes() == (TEMPLATES / "capital_structure_boot.js").read_bytes()
    assert (isolated_site / "capital_structure.css").read_bytes() == (TEMPLATES / "capital_structure.css").read_bytes()
    assert (isolated_site / "capital_structure.js").read_bytes() == (TEMPLATES / "capital_structure.js").read_bytes()


def test_api_only_runtime_uses_the_audited_observed_state_endpoints() -> None:
    js = (TEMPLATES / "capital_structure.js").read_text(encoding="utf-8")
    for token in (
        "/api/capital-structure/v1",
        "/coverage",
        "/overview",
        "/issuers/resolve?ticker=",
        "/issuers/",
        "/events?limit=",
        "encodeURIComponent",
        "credentials: 'same-origin'",
        "cache: 'no-store'",
        "headers.Authorization = 'Bearer ' + token",
        "window.MDXAuth.client",
        "rel=\"noopener noreferrer\"",
        "safeSecUrl",
    ):
        assert token in js
    assert "fetch(API + path" in js
    assert "capital-structure-data" not in js
    assert "projection.json" not in js
    assert "https://" not in js, "the desk must not make cross-origin browser reads"


def _runtime_hooks() -> dict:
    """Execute the pure, API-response-facing helpers without loading a browser."""
    node = shutil.which("node")
    if node is None:
        return {}
    harness = r'''
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const window = { __CAPITAL_STRUCTURE_DESK_TEST__: {} };
const document = { readyState: 'loading', addEventListener() {}, documentElement: { getAttribute() { return 'en'; } } };
vm.runInNewContext(source, { window, document, Date, Number, Array, Promise, console });
const hooks = window.__CAPITAL_STRUCTURE_DESK_TEST__;
console.log(JSON.stringify({
  issuer: hooks.resolveIssuerId({ issuer: { issuer_id: 'sec:cik:0000123456' } }),
  old: hooks.isRecentObserved('2026-06-30T16:34:39Z', '2026-08-01T16:34:39Z'),
  edge: hooks.isRecentObserved('2026-07-02T16:34:39Z', '2026-08-01T16:34:39Z'),
  future: hooks.isRecentObserved('2026-08-02T16:34:39Z', '2026-08-01T16:34:39Z'),
  lifecycle: hooks.labelPair('lifecycle', 'effective'),
  subtype: hooks.labelPair('subtype', 'effectiveness_notice'),
  classification: hooks.labelPair('classification', 'deferred_linkage'),
  change: hooks.labelPair('change', 'effectiveness_notice_observed'),
  unknown: hooks.labelPair('subtype', 'unknown_future_token')
}));
'''
    result = subprocess.run(
        [node, "-e", harness, str(TEMPLATES / "capital_structure.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_exact_ticker_resolver_reads_the_api_envelope_issuer_and_selects_it() -> None:
    hooks = _runtime_hooks()
    if not hooks:
        return
    assert hooks["issuer"] == "sec:cik:0000123456"
    js = (TEMPLATES / "capital_structure.js").read_text(encoding="utf-8")
    assert "var issuer = data && data.issuer;" in js
    assert "var issuerId = resolveIssuerId(data);" in js
    assert "return selectIssuer(issuerId, { focus: true });" in js


def test_stable_issuer_deep_links_survive_reload_and_history_navigation() -> None:
    js = (TEMPLATES / "capital_structure.js").read_text(encoding="utf-8")
    for token in (
        "searchParams.get('issuer')",
        "url.searchParams.set('issuer', issuerId);",
        "window.history[replace ? 'replaceState' : 'pushState']",
        "window.addEventListener('popstate'",
        "selectIssuer(requestedId, { updateUrl: false })",
        "selectIssuer(issuerId, { updateUrl: false, focus: true })",
    ):
        assert token in js


def test_recent_filter_uses_a_projection_as_of_clock_with_a_fixed_thirty_day_window() -> None:
    hooks = _runtime_hooks()
    if not hooks:
        return
    assert hooks["old"] is False
    assert hooks["edge"] is True
    assert hooks["future"] is False
    js = (TEMPLATES / "capital_structure.js").read_text(encoding="utf-8")
    html = (TEMPLATES / "capital_structure.html.j2").read_text(encoding="utf-8")
    assert "var RECENT_WINDOW_DAYS = 30;" in js
    assert "projectionAsOf()" in js
    assert "isRecentObserved(observedAt(latestFor(item)), projectionAsOf())" in js
    assert "Observed in 30 days" in html


def test_event_labels_are_explicitly_bilingual_with_a_safe_generic_fallback() -> None:
    hooks = _runtime_hooks()
    if not hooks:
        return
    assert hooks["lifecycle"] == ["Effective", "已生效"]
    assert hooks["subtype"] == ["SEC effectiveness notice", "SEC 生效通知"]
    assert hooks["classification"] == ["Link review pending", "待关联复核"]
    assert hooks["change"] == ["SEC effectiveness notice observed", "已观察到 SEC 生效通知"]
    assert hooks["unknown"] == ["Observed SEC filing", "已观察 SEC 申报"]
    js = (TEMPLATES / "capital_structure.js").read_text(encoding="utf-8")
    assert "titleCase(" not in js
    assert "labelFor('change', change.change_type)" in js
    assert "labelFor('classification', latest.classification_state)" in js


def test_api_rendered_labels_follow_the_site_language_event_contract() -> None:
    js = (TEMPLATES / "capital_structure.js").read_text(encoding="utf-8")
    assert "document.addEventListener('langchange', relabelDynamicContent);" in js
    assert "updateLocalizedAttributes();" in js
    assert "if (state.record) renderRecord(state.record);" in js
    assert "mastermind:languagechange" not in js


def test_no_derived_finance_or_trade_authority_reaches_the_desk_copy() -> None:
    surface = "\n".join(
        (TEMPLATES / name).read_text(encoding="utf-8")
        for name in ("capital_structure.html.j2", "capital_structure.css", "capital_structure.js")
    ).lower()
    for forbidden in ("risk score", "capacity", "runway", "probability", "buy signal", "sell signal"):
        assert forbidden not in surface
    assert "investigate filings" in surface
    assert "not a trade call" in surface


def test_responsive_drawer_and_mobile_one_column_contract() -> None:
    css = (TEMPLATES / "capital_structure.css").read_text(encoding="utf-8")
    for token in (
        "@media (max-width: 960px)",
        "@media (max-width: 700px)",
        "grid-template-columns: 1fr;",
        ".cs-evidence-drawer.is-open",
        ".cs-scrim",
        ":focus-visible",
        "prefers-reduced-motion",
    ):
        assert token in css


def test_evidence_drawer_is_a_closed_hidden_modal_until_opened() -> None:
    html = _render_template()
    js = (TEMPLATES / "capital_structure.js").read_text(encoding="utf-8")
    assert 'id="cs-evidence-drawer"' in html
    assert 'aria-hidden="true" tabindex="-1" hidden inert' in html
    for token in (
        "ui.evidenceDrawer.hidden = false;",
        "ui.evidenceDrawer.setAttribute('role', 'dialog');",
        "ui.evidenceDrawer.setAttribute('aria-modal', 'true');",
        "setInert(ui.shell, true);",
        "setInert(ui.siteNav, true);",
        "ui.closeEvidence.focus();",
        "focusableInDrawer",
        "handleDrawerKeydown",
        "ui.evidenceDrawer.hidden = true;",
        "state.lastFocus.focus({ preventScroll: true });",
    ):
        assert token in js


def test_plans_matrix_states_the_paid_observed_filing_state_feature(tmp_path: Path) -> None:
    build_public_pages.build(tmp_path)
    plans = (tmp_path / "plans.html").read_text(encoding="utf-8")
    assert "Capital Structure" in plans
    assert "Observed filing state" in plans
    assert "已观察申报状态" in plans
    assert "Full observed state &amp; SEC receipts" in plans
    shipped = (SITE / "plans.html").read_text(encoding="utf-8")
    assert "Capital Structure" in shipped
    assert "Observed filing state" in shipped


def test_runtime_is_valid_javascript() -> None:
    node = shutil.which("node")
    if node is None:
        return
    for name in ("capital_structure_boot.js", "capital_structure.js"):
        result = subprocess.run(
            [node, "--check", str(TEMPLATES / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_prepaint_boot_restores_theme_and_language_without_inline_script() -> None:
    html = _render_template()
    boot = (TEMPLATES / "capital_structure_boot.js").read_text(encoding="utf-8")
    assert '<script src="capital_structure_boot.js"></script>' in html
    assert "localStorage.getItem('lang')" in boot
    assert "setAttribute('data-lang', lang)" in boot
    assert "document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';" in boot


def test_site_access_locks_the_direct_artifact_prefix() -> None:
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
    prefixes = policy["premium"]["enforced_early"]["prefixes"]
    assert "/capital-structure-data/" in prefixes
    assert "/capital-structure-data/" not in policy["public"]["prefixes"]


def test_full_site_builder_has_a_canonical_desk_render_hook() -> None:
    source = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    assert "from scripts.build_capital_structure_page import render as _render_capital_structure" in source
    assert "_cs_page = _render_capital_structure(config.ROOT)" in source


def test_research_navigation_exposes_the_premium_desk() -> None:
    nav = (TEMPLATES / "_navlinks.html.j2").read_text(encoding="utf-8")
    assert 'href="{{ NP }}capital_structure.html"' in nav
    assert "Capital Structure" in nav
