from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def _render() -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    return env.get_template("fundamental_forensics.html.j2").render(
        generated_utc="2026-08-01T12:00:00Z",
        state_summary={"companies": 1492, "findings": 1054},
        active_section="research",
        active_page="fundamental_forensics",
    )


def test_workbench_renders_seven_functional_views_and_external_assets():
    html = _render()
    for tab in ("radar", "statements", "disclosures", "redlines", "timeline", "compare", "trace"):
        assert f'id="ff-tab-{tab}"' in html
        assert f'id="ff-panel-{tab}"' in html
    assert 'id="ff-company-search"' in html
    assert 'id="ff-evidence"' in html
    assert 'href="fundamental_forensics.css?v=20260811-ux"' in html
    assert 'src="fundamental_forensics.js?v=20260811-ux"' in html
    assert 'https://www.mastermind-x.com/fundamental_forensics.html' in html
    assert 'src="theme.js"' in html
    # There is no executable page-inline JS; the SEO structured data block is
    # allowed and is not application logic.
    executable_inline = re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>(.*?)</script>", html, re.S)
    assert executable_inline == []


def test_member_experience_leads_with_value_and_explains_the_workflow():
    html = _render()
    for element_id in (
        "ff-overview",
        "ff-overview-status",
        "ff-quick-signal",
        "ff-quick-signal-title",
        "ff-stat-attention",
        "ff-stat-watch",
        "ff-stat-coverage",
        "ff-stat-sources",
    ):
        assert f'id="{element_id}"' in html
    assert "Spot the changes that matter." in html
    assert "Pick a company. We compare its latest filing" in html
    assert "The important changes, up front" in html
    assert "Compare the numbers" in html
    assert "Read wording changes" in html
    assert "Verify the source" in html
    assert "Needs attention" in html
    assert "Keep an eye on" in html
    assert "Review now" not in html


def test_disclosure_surfaces_make_the_text_comparison_boundary_and_source_path_plain():
    html = _render()
    assert 'id="ff-disclosure-feed"' in html
    assert 'id="ff-redline-list"' in html
    assert 'id="ff-timeline"' in html
    assert 'id="ff-disclosure-section"' in html
    assert 'class="ff-lexical-glyph"' in html
    assert "This compares language between filings. It shows what changed—not why it changed." in html
    assert "Each row shows matching passages from both SEC filings." in html
    assert "See which filings are being compared" in html
    assert "Check the filing type, date, and original SEC document." in html


def test_sources_tab_preserves_compatibility_and_adds_a_scoped_receipt_reader():
    html = _render()
    # ``trace`` remains the stable outer view contract for navigation, deep
    # links, and the pre-existing evidence map. The receipt view is nested so
    # it cannot displace the SEC source path.
    assert 'id="ff-tab-trace"' in html
    assert 'id="ff-panel-trace"' in html
    assert 'id="ff-source-tabs"' in html
    assert 'id="ff-source-tab-map"' in html
    assert 'id="ff-source-tab-receipt"' in html
    assert 'id="ff-source-panel-map" role="tabpanel" aria-labelledby="ff-source-tab-map" tabindex="-1"' in html
    assert 'id="ff-source-panel-receipt" role="tabpanel" aria-labelledby="ff-source-tab-receipt" tabindex="-1"' in html
    assert 'id="ff-receipt"' in html
    assert 'id="ff-receipt-inspector"' in html
    assert 'id="ff-receipt-inspector-close"' in html
    assert '</aside>\n  <div class="ff-scrim" id="ff-scrim" hidden></div>\n</div>\n\n<template' in html
    assert '<span class="l-en">Sources</span>' in html
    assert '<span class="l-zh">来源凭据</span>' in html
    assert "Run record" in html
    assert "运行记录" in html


def test_workbench_dom_ids_are_unique_and_bilingual():
    html = _render()
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    assert html.count('class="l-en"') >= 20
    assert html.count('class="l-zh"') >= 20
    assert "找出真正重要的财报变化" in html
    assert "Signal details" in html


def test_runtime_contract_accessibility_and_security_guards():
    js = (TEMPLATES / "fundamental_forensics.js").read_text(encoding="utf-8")
    for token in (
        "/api/forensics/state",
        "/data/fundamental_forensics/private/state.json.gz",
        "DecompressionStream",
        "ranked_findings",
        "URLSearchParams",
        "data-finding-id",
        "renderStatements",
        "renderCompare",
        "renderTrace",
        "renderDisclosureFeed",
        "renderRedlines",
        "renderTimeline",
        "renderDisclosureEvidence",
        "renderTabEvidenceEmpty",
        "disclosure_bundle",
        "disclosures",
        "disclosureTracks",
        "readyDisclosureTracks",
        "selectedDisclosureTrack",
        "current_filing",
        "prior_filing",
        "accepted_at",
        "redlines",
        "redline_ops",
        "source_excerpt",
        "prior_receipt",
        "current_receipt",
        "renderEvidence",
        "ATTESTED_HISTORY_URL",
        "historyRequest",
        "/api/forensics/v1/attested-history",
        "/latest",
        "normalizedCik",
        "receiptOwnerMatches",
        "loadReceiptRoots",
        "requestReceiptRoot",
        "renderReceiptInspector",
        "openReceiptInspector",
        "closeReceiptInspector",
        "setInert",
        "focusableInEvidence",
        "safeUrl",
        "rel=\"noopener noreferrer\"",
    ):
        assert token in js
    assert "parsed.protocol === 'http:' || parsed.protocol === 'https:'" in js
    assert ".replace(/</g, '&lt;')" in js
    assert "var pct = numeric * 100;" in js
    assert "Math.abs(numeric) <= 1" not in js
    assert "actionKey === 'limited' ? '?'" in js
    assert "Coverage incomplete" in js
    assert "missing checks remain unknown" in js
    assert "Observed language is not a motive claim" in js
    assert "across ' + pairCount + ' filing pair" in js
    assert "_track_form" in js
    assert "_filing_role" in js
    assert "No comparable filing pair yet" in js
    assert "suppressed_boilerplate" in js
    assert "Array.isArray(bundle.redlines) ? bundle.redlines : []" in js
    assert "No run record for this company" in js
    assert "all_leaves_attested" in js
    assert "partially_attested" in js
    assert "not_attested" in js
    assert "not_evaluable" in js
    assert "does not reread source material" in js
    assert "Cell identifiers are trace keys" in js
    assert "No selected correspondence is recorded in this receipt." in js
    assert "if (!receiptReadyPayload(payload)) throw new Error('Receipt identity is malformed');" in js
    assert "credentials: 'same-origin'" in js
    assert "cache: 'no-store'" in js


def test_runtime_is_valid_javascript():
    node = shutil.which("node")
    if node is None:
        return
    result = subprocess.run(
        [node, "--check", str(TEMPLATES / "fundamental_forensics.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_receipt_runtime_contract_rejects_malformed_dynamic_payloads():
    node = shutil.which("node")
    if node is None:
        return
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests" / "fundamental_forensics_receipt_contract.test.mjs")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_responsive_evidence_lens_has_desktop_drawer_and_mobile_sheet():
    css = (TEMPLATES / "fundamental_forensics.css").read_text(encoding="utf-8")
    assert "@media (min-width: 1100px)" in css
    assert "@media (max-width: 1099px)" in css
    assert "@media (min-width: 701px) and (max-width: 1300px)" in css
    assert "@media (max-width: 700px)" in css
    assert ".ff-evidence.is-open" in css
    assert ".ff-scrim" in css
    assert ".ff-disclosure-card" in css
    assert ".ff-redline-card" in css
    assert ".ff-source-excerpt" in css
    assert ".ff-lexical-glyph" in css
    assert ".ff-timeline-card" in css
    assert ".ff-source-tabs" in css
    assert ".ff-receipt-inspector" in css
    assert ".ff-receipt-waterfall" in css
    assert ".ff-receipt-status-grid" in css
    assert "body.ff-modal-open #mmb-launch" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert ".ff-overview" in css
    assert ".ff-quick-signal" in css
    assert ".ff-tab-group" in css
    assert ".ff-signal-meaning" in css
    assert ".ff-view-guide" in css
    assert '.ff-workspace[data-tab="statements"]' in css


def test_forensics_browser_state_stays_inside_paid_same_origin_boundary():
    js = (TEMPLATES / "fundamental_forensics.js").read_text(encoding="utf-8")
    shim = (TEMPLATES / "data_base.js").read_text(encoding="utf-8")
    publisher = (ROOT / "scripts" / "publish_r2.py").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/api/forensics/state" in js
    assert "headers.Authorization = 'Bearer ' + token" in js
    assert "window.MDXAuth.client" in js
    assert "IS_LOOPBACK" in js
    assert "|forensics)" not in shim
    assert '"forensics"' not in publisher
    assert "data/fundamental_forensics/private/" in gitignore
    assert "site/forensics/state.json.gz" not in js
