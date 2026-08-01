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
    assert 'href="fundamental_forensics.css"' in html
    assert 'src="fundamental_forensics.js"' in html
    assert 'https://www.mastermind-x.com/fundamental_forensics.html' in html
    assert 'src="theme.js"' in html
    # There is no executable page-inline JS; the SEO structured data block is
    # allowed and is not application logic.
    executable_inline = re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>(.*?)</script>", html, re.S)
    assert executable_inline == []


def test_disclosure_surfaces_make_the_text_comparison_boundary_and_source_path_plain():
    html = _render()
    assert 'id="ff-disclosure-feed"' in html
    assert 'id="ff-redline-list"' in html
    assert 'id="ff-timeline"' in html
    assert 'id="ff-disclosure-section"' in html
    assert 'class="ff-lexical-glyph"' in html
    assert "This is a text comparison, not an explanation of motive, materiality, or financial impact." in html
    assert "Every row links back to the matched SEC filing excerpts." in html
    assert "The filing record behind this review" in html
    assert "Confirm the reporting form, filing date, accession, and original SEC document" in html


def test_workbench_dom_ids_are_unique_and_bilingual():
    html = _render()
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    assert html.count('class="l-en"') >= 20
    assert html.count('class="l-zh"') >= 20
    assert "财报变化雷达" in html
    assert "Evidence inspector" in html


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
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css


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
