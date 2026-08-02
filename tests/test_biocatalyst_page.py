"""BioCatalyst's public shell, client boundary, and build integration tests."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from scripts.build_biocatalyst import render_from_state


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def _render() -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    return env.get_template("biocatalyst.html.j2").render(
        generated_utc="2026-08-02T12:00:00Z",
        active_section="research",
        active_page="biocatalyst",
    )


def test_biocatalyst_shell_is_bilingual_shared_navigation_only_and_data_free():
    source = (TEMPLATES / "biocatalyst.html.j2").read_text(encoding="utf-8")
    html = _render()

    assert source.count('{% include "_site_nav.html.j2" %}') == 1
    assert "<nav" not in source
    assert html.count('class="site-nav"') == 1
    assert html.count('class="l-en"') >= 20
    assert html.count('class="l-zh"') >= 20
    assert "Registry Milestone Monitor" in html
    assert "登记里程碑监测" in html

    # The static shell explains the product but cannot disclose a study, a
    # generated list, or an opaque internal record reference before site_full
    # has been enforced by the API.
    assert re.search(r"\bNCT\d{8}\b", html) is None
    for forbidden in (
        '"trials"',
        '"nct_id"',
        "canonical_study",
        "source_snapshot",
        "generation_id",
        "raw_object_key",
    ):
        assert forbidden not in html


def test_biocatalyst_shell_has_one_accessible_three_pane_milestone_workbench():
    html = _render()
    for identifier in (
            "bci-filter-pane",
            "bci-queue-pane",
            "bci-inspector-pane",
            "bci-window-control",
            "bci-field-filter",
            "bci-search",
        "bci-phase-filter",
        "bci-status-filter",
        "bci-condition-filter",
        "bci-queue",
            "bci-inspector-body",
            "bci-refresh",
            "bci-load-more",
            "bci-page-status",
            "bci-brain-launch",
    ):
        assert f'id="{identifier}"' in html or f'class="{identifier}"' in html
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    assert 'role="radiogroup"' in html
    assert 'role="radio"' in html
    assert "Dates are recorded by ClinicalTrials.gov" in html
    assert "A registry listing is not government validation" in html
    assert "this view does not make a trade call" in html
    assert "<option" in html
    assert re.search(r"<option[^>]*>\s*<span", html) is None


def test_biocatalyst_client_uses_authenticated_milestone_pages_and_current_dossiers_only():
    js = (TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    for token in (
            "/api/biocatalyst/v1/trials",
            "/api/biocatalyst/v1/trials/milestones",
            "headers.Authorization = 'Bearer ' + token",
        "window.MDXAuth.client",
        "credentials: 'same-origin'",
        "cache: 'no-store'",
        "textContent",
        "encodeURIComponent(id)",
        "rel = 'noopener noreferrer'",
        "URLSearchParams",
        "aria-selected",
        "ArrowDown",
        "Escape",
        "langchange",
        "Primary endpoints",
        "Secondary endpoints",
        "bci-endpoint",
        "Registry record updates",
        "V' + group.before + ' → V' + group.after",
        "Submitted ",
        "Before: ",
        "After: ",
        "historyUnavailableCopy",
        "historyKindLabel",
            "Registry field updated",
            "登记字段更新",
            "incomplete_chain",
            "next_cursor",
            "milestone_kind",
            "next_30d",
            "AbortController",
            "generation-restarted",
            "first-load",
            "page-loading",
            "locked",
            "empty",
            "Evidence & trust",
            "current_only",
            "ACTUAL",
            "ESTIMATED",
            "UNKNOWN",
            "DATE_PARTS",
            "URLSearchParams",
            "Load more",
        ):
            assert token in js
    assert "innerHTML" not in js
    assert "new Date" not in js
    assert "fetchTrialPages" not in js
    assert "limit=250" not in js
    assert "localStorage" not in js
    assert "sessionStorage" not in js
    assert "clinicaltrials.gov/study/" in js
    assert "probability" not in js.lower()
    assert "normalized.replace(/_/g, ' ')" not in js
    for forbidden in (
        "protocol amendment",
        "activated",
        "closed",
        "delay",
        "velocity",
        "materiality",
        "forecast",
        "pdufa",
        "approval",
    ):
        assert forbidden not in js.lower()


def test_biocatalyst_assets_have_responsive_motion_and_focus_guards():
    css = (TEMPLATES / "biocatalyst.css").read_text(encoding="utf-8")
    for token in (
        "@media (min-width: 1121px)",
        "@media (max-width: 1120px)",
        "@media (max-width: 760px)",
        ":focus-visible",
        "prefers-reduced-motion",
        ".bci-inspector-pane.is-open",
        ".bci-scrim",
        ".bci-inspector-close,.bci-scrim { display: none !important; }",
        ".bci-window-options",
        ".bci-load-more",
        ".bci-evidence-strip",
        ".bci-date-type.is-actual",
        "body.bci-page #mmb-launch { display: none !important; }",
        ".bci-brain-launch { display: inline-flex;",
        "backdrop-filter: none",
        "min-height: 0; height: 100%; overflow: hidden",
        "animation: none !important",
    ):
        assert token in css
    assert "animation-duration: 2s" not in css


def test_biocatalyst_milestone_runtime_defaults_to_ninety_days_and_preserves_verified_pages():
    """Audit the UI contract around the non-inferential milestone endpoint.

    These assertions intentionally inspect the public runtime source so a future
    visual refactor cannot silently widen the default request, merge malformed
    pages, leak a paid page after access loss, or strand keyboard focus in the
    compact inspector.
    """

    html = _render()
    js = (TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")

    assert 'data-window="90"' in html
    assert re.search(r'class="bci-window is-active"[^>]*aria-checked="true"[^>]*data-window="90"', html)
    assert re.search(r'class="bci-window"[^>]*aria-checked="false"[^>]*data-window="30"', html)
    assert "filters: { field: 'primary_completion', window: '90'" in js
    assert "WINDOW_VALUES[windowName] ? windowName : '90'" in js
    assert "window: '90', q: '', phase: '', status: '', condition: ''" in js
    assert "MILESTONE_WINDOWS = { '30': 'next_30d', '90': 'next_90d'" in js

    for token in (
        "function isAccessError(error)",
        "error.status === 402",
        "function restartableAppendError(error)",
        "error.status === 400 || error.status === 409",
        "validateMilestoneEnvelope(payload)",
        "queryMatchesCurrentFilters(query)",
        "effectiveWindowIsSane",
        "partialDateMatchesPrecision",
        "kind === state.filters.field",
        "function validateMilestonePage(items, existingRows)",
        "function validateMilestonePagination(payload, existingRows, requestedCursor, previousPayload)",
        "Duplicate milestone identity",
        "Milestone total changed during pagination",
        "Repeated milestone cursor",
        "append-unavailable",
        "Last verified page",
        "state.rows.length && !state.accessLocked",
        "function lockWorkspace()",
        "aria-modal",
        "function trapInspectorFocus(event)",
        "document.activeElement === ui.inspector",
        "state.returnFocus",
        "function syncQueueSelection()",
        "trigger && document.contains(trigger)",
        "returnTrialId",
        "data-date-type",
        "Registry date type:",
        "Retry loading more registry milestones",
        "window.addEventListener('resize', syncInspectorDialog)",
        "closeInspector({ restoreFocus: false, writeUrl: false, render: false })",
        "abort('detailController'); state.detailToken += 1",
        "function paintLockedWorkspace()",
        "function paintAppendFailure()",
        "function paintUnavailableWorkspace()",
    ):
        assert token in js

    # Access errors clear all prior rows before the finally block can repaint;
    # transient append failures instead retain the last verified cursor/rows.
    assert "state.rows = []; state.nextCursor = ''; state.payload = null" in js
    assert "if (options.append && state.rows.length) { preserveAppendFailure(); return; }" in js
    assert "handleUnavailable(error, { append: append });" in js

    # Entitlement loss invalidates both concurrent request lanes before any paid
    # rows are cleared, so a late dossier response cannot repaint the workspace.
    lock_body = js[js.index("function lockWorkspace()") : js.index("function paintAppendFailure()")]
    assert lock_body.index("abort('detailController')") < lock_body.index("state.rows = []")
    assert lock_body.index("state.detailToken += 1") < lock_body.index("state.rows = []")

    close_body = js[js.index("function closeInspector(options)") : js.index("function detailLoading()")]
    assert "showInspectorEmpty(tr('Trial dossier'" in close_body
    assert close_body.index("state.detail = null") < close_body.index("showInspectorEmpty")

    # Runtime language changes must repaint exceptional states directly instead
    # of routing an append failure through updateMetadata(), which clears it.
    language_body = js[js.index("document.addEventListener('langchange'") : js.index("window.addEventListener('popstate'")]
    assert language_body.index("state.accessLocked") < language_body.index("state.appendFailed")
    assert language_body.index("state.appendFailed") < language_body.index("updateMetadata(state.payload)")


def test_biocatalyst_mobile_uses_an_inline_mastermind_entry_not_a_fixed_filter_overlay():
    """The global fixed launcher must not intercept the phone filter controls."""

    html = _render()
    js = (TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    css = (TEMPLATES / "biocatalyst.css").read_text(encoding="utf-8")

    assert 'id="bci-condition-filter"' in html
    assert 'id="bci-brain-launch"' in html
    assert html.index('id="bci-condition-filter"') < html.index('id="bci-brain-launch"')
    assert "window.MMBrain.open" in js
    assert "body.bci-page #mmb-launch { display: none !important; }" in css
    assert ".bci-brain-launch { display: inline-flex;" in css


def test_biocatalyst_renderer_writes_only_the_shell_and_paired_assets(tmp_path: Path):
    # The builder must be testable without mutating the repository's served
    # tree. It only needs the template family, so a directory symlink preserves
    # the real include graph while redirecting all emitted site bytes.
    (tmp_path / "templates").symlink_to(TEMPLATES, target_is_directory=True)
    page = render_from_state(tmp_path)
    html = page.read_text(encoding="utf-8")
    assert page == tmp_path / "site" / "biocatalyst.html"
    assert re.search(r"\bNCT\d{8}\b", html) is None
    assert (tmp_path / "site" / "biocatalyst.css").read_bytes() == (TEMPLATES / "biocatalyst.css").read_bytes()
    assert (tmp_path / "site" / "biocatalyst.js").read_bytes() == (TEMPLATES / "biocatalyst.js").read_bytes()
    assert not list((tmp_path / "site").glob(".biocatalyst.*.tmp"))
    assert 'src="biocatalyst.js"' in html
    assert 'href="biocatalyst.css"' in html


def test_biocatalyst_is_registered_preview_with_a_site_full_api_boundary():
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
    free_registered = policy["free_registered"]["exact"]
    assert "/biocatalyst.html" in free_registered
    assert "/biocatalyst.css" in free_registered
    assert "/biocatalyst.js" in free_registered

    page_source = (TEMPLATES / "biocatalyst.html.j2").read_text(encoding="utf-8")
    api_source = (ROOT / "app" / "biocatalyst.py").read_text(encoding="utf-8")
    assert "/api/biocatalyst/" not in page_source
    assert "require_site_full_user" in api_source
    assert "enforce_site_full" in api_source


def test_biocatalyst_is_wired_into_the_site_renderer_and_research_navigation():
    site_builder = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    nav = (TEMPLATES / "_navlinks.html.j2").read_text(encoding="utf-8")
    plans = (TEMPLATES / "plans.html.j2").read_text(encoding="utf-8")
    assert "scripts.build_biocatalyst" in site_builder
    assert "biocatalyst.html render failed" in site_builder
    assert nav.count("biocatalyst.html") == 1
    assert "BioCatalyst Intelligence" in nav
    assert plans.count("BioCatalyst Trial Watch") == 2
    assert "probability" not in plans.lower()
    assert "forecast" in plans.lower()  # explicit non-forecast boundary


def test_render_lane_owns_and_narrows_biocatalyst_builder():
    render = (ROOT / ".github" / "workflows" / "render.yml").read_text(
        encoding="utf-8"
    )
    assert '- "scripts/build_biocatalyst.py"' in render
    assert "templates/biocatalyst.*" in render
    assert "scripts/build_biocatalyst.py) echo macro;;" in render


def test_biocatalyst_runtime_is_valid_javascript():
    node = shutil.which("node")
    if node is None:
        return
    result = subprocess.run(
        [node, "--check", str(TEMPLATES / "biocatalyst.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
