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
    assert "BioCatalyst Intelligence" in html
    assert "Trial Intelligence Workspace" in html
    assert "试验智能工作台" in html

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


def test_biocatalyst_shell_has_one_accessible_three_pane_trial_intelligence_workbench():
    html = _render()
    for identifier in (
            "bci-filter-pane",
            "bci-queue-pane",
            "bci-inspector-pane",
            "bci-window-control",
            "bci-mode-control",
            "bci-mode-milestones",
            "bci-mode-changes",
            "bci-mode-prospective",
            "bci-field-filter",
            "bci-change-kind-filter",
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
    assert 'role="tablist"' in html
    assert 'role="tab"' in html
    assert 'id="bci-queue-pane" role="tabpanel" aria-labelledby="bci-mode-milestones"' in html
    assert html.count('aria-controls="bci-queue-pane"') == 3
    assert "Dates and field updates are recorded by ClinicalTrials.gov" in html
    assert "A registry listing is not government validation" in html
    assert "Review the source record—no trade call." in html
    assert "请查看来源记录，不作交易判断。" in html
    js = (TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    for kind in (
        "endpoint_added",
        "endpoint_removed",
        "endpoint_role_changed",
        "endpoint_measure_changed",
        "endpoint_time_frame_changed",
        "endpoint_description_changed",
        "enrollment_changed",
        "registry_status_changed",
        "study_date_changed",
        "site_listing_changed",
        "lead_sponsor_text_changed",
        "intervention_added",
        "intervention_removed",
        "intervention_changed",
    ):
        assert f"'{kind}'" in js
    assert 'id="bci-change-kind-filter" aria-label="Updated field"' in html
    assert "<option" in html
    assert re.search(r"<option[^>]*>\s*<span", html) is None


def test_biocatalyst_client_uses_authenticated_source_fact_pages_and_current_dossiers_only():
    js = (TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    for token in (
            "/api/biocatalyst/v1/trials",
            "/api/biocatalyst/v1/trials/milestones",
            "/api/biocatalyst/v1/trials/changes",
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
            "last_30d",
            "CHANGE_WINDOWS",
            "change_kind",
            "registry_change",
            "before_display_version",
            "after_display_version",
            "source_submitted_at",
            "version_url",
            "history_url",
            "history_coverage",
            "protocol_change_asserted",
            "materiality_assessed",
            "validateChangeEnvelope(payload)",
            "validateChangePage(payload.changes, existingRows)",
            "validateChangePagination(payload, existingRows, cursor",
            "makeChangeRow",
            "bci-change-preview",
            "bci-change-version",
            "Change Tape",
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
        ".bci-mode-control",
        ".bci-change-card",
        ".bci-change-preview",
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


def test_biocatalyst_modes_default_to_milestones_and_preserve_verified_pages():
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
    assert "mode: 'milestones'" in js
    assert "filters: { field: 'primary_completion', change_kind: '', prospective_change_kind: '', window: '90'" in js
    assert "WINDOW_VALUES[windowName] ? windowName : '90'" in js
    assert "change_kind: '', prospective_change_kind: '', window: '90', q: '', phase: '', status: '', condition: ''" in js
    assert "MILESTONE_WINDOWS = { '30': 'next_30d', '90': 'next_90d'" in js
    assert "CHANGE_WINDOWS = { '30': 'last_30d', '90': 'last_90d'" in js

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
        "Retry loading more ' + noun",
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
    assert "syncControls(); localizeControls();" in language_body
    assert language_body.index("state.accessLocked") < language_body.index("state.appendFailed")
    assert language_body.index("state.appendFailed") < language_body.index("updateMetadata(state.payload)")
    assert "announce(state.rows.length ? tr('Loaded '" in language_body
    assert "announce(tr('Retrieving ' + activeNoun()" in language_body


def test_biocatalyst_change_tape_client_contract_is_mode_bound_and_fail_closed():
    """Change Tape may show only exact, display-safe registry facts.

    This is deliberately source-level: it keeps a future visual refactor from
    accepting an unsigned/mismatched cursor page, treating a source update as
    a protocol or materiality conclusion, or allowing an old list/detail
    response to repaint after the operator changes mode or loses entitlement.
    """

    js = (TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    html = _render()

    for token in (
        "function validChangeEvidence(evidence, id, afterVersion)",
        "function validRegistryChange(change)",
        "function validChange(item)",
        "function validateChangeEnvelope(payload)",
        "function changeQueryMatchesCurrentFilters(query)",
        "function effectiveChangeWindowIsSane(window, apiWindow)",
        "function changeIdentity(item)",
        "function validateChangePage(items, existingRows)",
        "function validateChangePagination(payload, existingRows, requestedCursor, previousPayload)",
        "Duplicate registry change identity",
        "Repeated registry change cursor",
        "Incomplete registry change pagination",
        "function setMode(value, trigger)",
        "abort('listController'); state.listToken += 1; abort('detailController'); state.detailToken += 1",
        "function isChangeMode()",
        "activeApi()",
        "activeWindow()",
        "setMode(button.getAttribute('data-mode'), button)",
        "ArrowRight",
        "exactHistoryUrl",
        "exactHistoryRootUrl",
        "safeJson",
        "fullTimestamp",
        "source_submitted_at",
        "record_history_complete",
        "registry_record_changed",
        "protocol_change_asserted') === false",
        "materiality_assessed') === false",
        "isChangeMode() ? validateChangePage",
            "if (isProspectiveMode()) validateProspectiveEnvelope(payload); else if (isChangeMode()) validateChangeEnvelope(payload); else validateMilestoneEnvelope(payload);",
            "if (isProspectiveMode()) validateProspectivePagination(payload, existingRows, cursor, append ? state.payload : null); else if (isChangeMode()) validateChangePagination(payload, existingRows, cursor, append ? state.payload : null);",
    ):
        assert token in js
    assert js.count("function validateChangeEnvelope(payload)") == 1
    assert "function validChangeEnvelope(payload)" not in js

    assert "localStorage" not in js
    assert "sessionStorage" not in js
    assert "innerHTML" not in js
    assert "No trade call" not in js  # claim stays in the bilingual shell, not data handling
    assert 'data-mode="milestones"' in html
    assert 'data-mode="changes"' in html
    assert 'aria-selected="true"' in html

    # The browser accepts the same bounded JSON value domain as the API and
    # renders exact JSON literals in the dossier. Queue cards are explicitly a
    # compact preview, so blank, whitespace-only, and long values are never
    # silently recast as absent facts.
    for token in (
        "Array.from(value).length <= 12000",
        "value.length <= 200",
        "Object.keys(value).length > 100",
        "Array.from(key).length <= 256",
        "depth > 12",
        "JSON.stringify(value)",
        "Registry value preview; open the dossier for the full exact value",
        "History coverage: ",
        "knowledge_cutoff",
        "History retrieved through ",
        "clean(valueAt(window, 'date_basis')) !== 'source_submitted_at'",
        "data-row-key",
        "state.selectedKey",
        "rowKey === state.selectedKey",
        "kindNames.slice(0, 3)",
        "ui.queuePane.setAttribute('aria-labelledby', button.id)",
        "AUTHORITY_ALLOWED_USES = ['display', 'context', 'explain']",
        "AUTHORITY_FORBIDDEN_USES = ['originate_signal', 'rank_security', 'select_security', 'size_position', 'gate_decision', 'execute_trade', 'raise_authority']",
        "Object.keys(authority).sort().join('|') === 'allowed_uses|classification|decision_authority|forbidden_uses'",
        "validAuthority(payload.authority)",
        "changes.length <= 2000",
        "!fullTimestamp(payloadAsOf)",
        "var activeRow = selectedRow();",
        "state.selectedKey && rowIdentity(item) === state.selectedKey",
            "function activeSingularNoun()",
            "if (isProspectiveMode()) return tr('first-seen observation', '首次观测记录');",
    ):
        assert token in js
    assert "Choose a registry milestone to read the current trial record" not in js
    assert "Choose a registry milestone when full access is confirmed" not in js
    assert "clean(String(value))" not in js
    assert "changes.length <= 40" not in js
    assert "changes.forEach(function (change) { line.appendChild" not in js
    assert "var selectedRow = state.rows.filter(function (item) { return nctOf(item.trial) === state.selectedId; })[0];" not in js


def test_biocatalyst_first_seen_tape_is_prospective_current_only_and_never_recasts_its_clock():
    """First-seen Tape is an observation ledger, not a third history presentation.

    The browser must reject payloads that blur a collector-observation interval
    into a source event time, reveal non-display-safe operations, or carry a
    row identity that collapses multiple observations for the same NCT.
    """

    html = _render()
    js = (TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    css = (TEMPLATES / "biocatalyst.css").read_text(encoding="utf-8")

    assert 'id="bci-mode-prospective"' in html
    assert 'data-mode="prospective"' in html
    assert 'data-label-en="First-seen Tape"' in html
    assert 'data-label-zh="首次观测记录"' in html
    assert html.count('aria-controls="bci-queue-pane"') == 3

    for token in (
        "/api/biocatalyst/v1/trials/prospective-changes",
        "PROSPECTIVE_WINDOWS",
        "function isProspectiveMode()",
        "function validProspectiveEvidence(evidence, id, observedAt)",
        "function validObservedInterval(interval, observedAt)",
        "function validProspectiveChange(change)",
        "function validProspectiveChangeItem(item)",
        "function observationTimestampLabel(value)",
        "function prospectiveQueryMatchesCurrentFilters(query)",
        "function effectiveProspectiveWindowIsSane(window, apiWindow)",
        "function validateProspectiveEnvelope(payload)",
        "function prospectiveIdentity(item)",
        "function validateProspectivePage(items, existingRows)",
        "function validateProspectivePagination(payload, existingRows, requestedCursor, previousPayload)",
        "Duplicate prospective observation identity",
        "Repeated prospective cursor",
        "Incomplete prospective pagination",
        "prospective_changes",
        "prospective_change",
        "change_id",
        "first_observed_at",
        "observed_interval",
        "at_or_before",
        "observation_at_or_before_utc",
        "prospective_current_only",
        "current_trial_record",
        "coverage_state",
        "pre_baseline_trials",
        "total_exact_operation_count",
        "display_change_count",
        "omitted_operation_count",
        "changes.length <= 128",
        "['present', 'missing']",
        "PROSPECTIVE_CHANGE_KIND_VALUES",
        "makeProspectiveRow",
        "bci-prospective-card",
        "bci-observation-preview",
        "First observed",
        "Observed at / before",
        "no display-safe detail",
        "function prospectiveObservationSection(prospectiveChange)",
        "showDetail(detail, queueEvidence, queueItem)",
        "if (isProspectiveMode()) ui.inspectorBody.appendChild(prospectiveObservationSection",
    ):
        assert token in js

    prospective_row = js[js.index("function makeProspectiveRow") : js.index("function syncQueueSelection")]
    prospective_detail = js[js.index("function prospectiveObservationSection") : js.index("function historySection")]
    assert "Submitted " not in prospective_row
    assert "version" not in prospective_row.lower()
    assert "history" not in prospective_row.lower()
    assert "Submitted " not in prospective_detail
    assert "version" not in prospective_detail.lower()
    assert "history" not in prospective_detail.lower()
    assert "observationTimestampLabel(" in prospective_row
    assert "observationTimestampLabel(" in prospective_detail

    # A prospective response binds to the same request and current-record scope.
    # It accepts only the prospective vocabulary, retains that selection across
    # ordinary tab switches, and never carries a retrospective kind into the
    # prospective request or control surface.
    query_body = js[js.index("function prospectiveQueryMatchesCurrentFilters") : js.index("function effectiveProspectiveWindowIsSane")]
    assert "change_kind: activeChangeKind() || 'all'" in query_body
    assert "state.filters.prospective_change_kind" in js
    assert "state.mode === 'prospective' && PROSPECTIVE_CHANGE_KIND_VALUES[changeKind] ? changeKind : ''" in js
    assert "assign('change_kind', (isChangeMode() || isProspectiveMode()) ? activeChangeKind() : '', true);" in js
    assert "if (isChangeMode() || isProspectiveMode())" in js
    assert "if (activeChangeKind()) params.set('change_kind', activeChangeKind());" in js
    assert "ui.changeKindControl.hidden = !(isChangeMode() || isProspectiveMode());" in js
    assert "function paintChangeKindOptions()" in js
    assert "All observed fields" in js
    assert "All display-safe fields" in js
    assert "Observed field" in js
    assert "Updated field" in js
    prospective_catalog = js[js.index("var PROSPECTIVE_CHANGE_KIND_CATALOG") : js.index("var CHANGE_WINDOWS")]
    for kind in (
        "registry_status",
        "enrollment_target",
        "enrollment_actual",
        "enrollment_count",
        "enrollment_type",
        "primary_completion_date",
        "completion_date",
        "site_set",
        "endpoint_record",
    ):
        assert f"'{kind}'" in prospective_catalog
    for historical_kind in (
        "endpoint_added",
        "endpoint_removed",
        "endpoint_role_changed",
        "enrollment_changed",
        "registry_status_changed",
        "study_date_changed",
        "intervention_added",
    ):
        assert historical_kind not in prospective_catalog
    set_mode_body = js[js.index("function setMode(value, trigger)") : js.index("function openBrain")]
    assert "state.filters.change_kind = '';" not in set_mode_body
    assert "else if (!isProspectiveMode()) params.set('milestone_kind', state.filters.field);" in js

    for forbidden in (
        "probability",
        "forecast",
        "pdufa",
        "approval",
        "localStorage",
        "sessionStorage",
        "innerHTML",
    ):
        assert forbidden not in js.lower()

    for token in (
        ".bci-mode-control { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));",
        ".bci-mode-prospective.is-active",
        ".bci-prospective-card",
        ".bci-observation-receipt",
        ".bci-observation-preview.is-omitted",
        ".bci-observation-section",
        ".bci-observation-delta",
        "@media (max-width: 760px)",
        "@media (max-width: 450px)",
    ):
        assert token in css


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
