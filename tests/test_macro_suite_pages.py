"""Macro & Monetary suite shell + Liquidity Regime workspace page (F01 / R1B).

Three things are under test, in order of how badly they would hurt in
production:

1. FAIL-CLOSED READING. Every way a published artifact can be wrong — missing,
   unreadable, schema-violating, version-mismatched, hash-tampered, or
   contradicted by its own manifest — must produce the typed refusal page, never
   a silently empty one and never a stale state.
2. HONEST ABSENCE. The real artifact is a first print: its one-month vector and
   its what-changed block are WARMUP. The page must say so in words a reader
   understands, and must not draw a zero, a flat line or an empty chart frame.
3. NO DEAD SURFACES AND NO SLUGS. Scenario and Alerts must not render as tabs
   while the artifact declares them unavailable, and no closed-vocabulary token
   may reach the reader outside the monospace machine-receipt channel.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from lib import macro_suite_labels as labels
from lib import macro_suite_view
from scripts import build_macro_suite_pages as builder

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DATA_ROOT = ROOT / "site" / "macrodata"
PAGE = builder.SUITE_PAGES[0]
BUILT_AT = "2026-09-04T12:00:00Z"

_TEMPLATE_NAMES = (
    "macro_liquidity_regime.html.j2",
    "macro_growth_real_economy.html.j2",
    "macro_business_activity.html.j2",
    "macro_labor_markets.html.j2",
    "macro_inflation_system.html.j2",
    "macro_monetary_policy.html.j2",
    "macro_financial_conditions.html.j2",
    "macro_liquidity_central_banks.html.j2",
    "macro_capital_structure.html.j2",
    "macro_housing_real_estate.html.j2",
    "macro_consumer_payments.html.j2",
    "macro_national_debt_liabilities.html.j2",
    "_macro_suite_shell.html.j2",
    "_seo_head.html.j2",
    "_site_nav.html.j2",
    "_navlinks.html.j2",
    "macro_suite_boot.js",
    "macro_suite.css",
    "macro_suite.js",
)


def _isolated_root(tmp_path: Path) -> Path:
    """A minimal repo root carrying only the templates the page needs."""
    templates = tmp_path / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    for name in _TEMPLATE_NAMES:
        shutil.copyfile(TEMPLATES / name, templates / name)
    return tmp_path


def _data_copy(tmp_path: Path) -> Path:
    """A writable copy of the published macrodata tree, for tampering."""
    destination = tmp_path / "macrodata"
    shutil.copytree(DATA_ROOT / "workspaces", destination / "workspaces")
    return destination


def _body_path(data_root: Path) -> Path:
    return data_root / "workspaces" / PAGE.workspace_id / PAGE.region / "latest.json"


def _manifest_path(data_root: Path) -> Path:
    return data_root / "workspaces" / "manifest.json"


def _build(tmp_path: Path, data_root: Path) -> str:
    root = _isolated_root(tmp_path)
    pages = builder.render(root, data_root=data_root, out_dir=tmp_path / "site",
                           page_built_at=BUILT_AT)
    assert len(pages) == len(builder.SUITE_PAGES)
    return pages[0].read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def live_html(tmp_path_factory) -> str:
    tmp_path = tmp_path_factory.mktemp("macro_suite_live")
    return _build(tmp_path, DATA_ROOT)


# --------------------------------------------------------------------------
# the shipped artifact renders a real, complete page
# --------------------------------------------------------------------------

def test_the_published_artifact_renders_the_named_state_and_both_axes(live_html: str) -> None:
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    assert snapshot["headline"]["state_label"]["en"] in live_html
    assert snapshot["headline"]["state_label"]["zh"] in live_html
    assert f'>{snapshot["headline"]["quadrant"]["x"]:.2f}<' in live_html
    assert f'>{snapshot["headline"]["quadrant"]["y"]:.2f}<' in live_html
    assert "{{" not in live_html and "{%" not in live_html and "{#" not in live_html


def test_every_grammar_region_is_present(live_html: str) -> None:
    for anchor in (
        'id="mq-context"',            # 1 context header
        'class="mq-ribbon"',          # 2 causal implications ribbon
        'class="mq-headline"',        # 3 headline state band
        'role="tablist"',             # 4 tabs
        'class="mq-map-svg"',         # 5 dominant visualization
        'class="mq-diagnostics"',     # 6 diagnostics
        'class="mq-changed"',         # 7 what changed
        'class="mq-metrics"',         # 8 component metrics
        'class="mq-series"',          # 8 component histories
        'id="mq-evidence-drawer"',    # 9 evidence drawer
    ):
        assert anchor in live_html, anchor


def test_the_page_is_bilingual_through_the_toggle_and_never_dual_language(live_html: str) -> None:
    assert live_html.count('class="l-en"') >= 120
    assert live_html.count('class="l-zh"') >= 120
    # Every reviewed pair must differ; an l-en that already carries its own zh
    # would print both languages at once in Chinese mode.
    pairs = re.findall(r'<span class="l-en">(.*?)</span><span class="l-zh">(.*?)</span>', live_html)
    assert pairs
    assert not [en for en, zh in pairs if zh and en.endswith(zh) and en != zh]


def test_the_shared_site_chrome_is_taken_whole_not_hand_rolled(live_html: str) -> None:
    assert live_html.count('class="site-nav"') == 1
    assert live_html.count('class="nav-ctrls"') == 1
    assert "data-dbase" in live_html
    assert 'href="macro_suite.css"' in live_html
    assert 'src="macro_suite.js"' in live_html
    assert 'src="macro_suite_boot.js"' in live_html


def test_no_executable_inline_script_reaches_the_page(live_html: str) -> None:
    """The only inline script a page may carry is the shared data-base shim."""
    inline = re.findall(
        r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)([^>]*)>", live_html)
    assert all("data-dbase" in attrs for attrs in inline), inline


# --------------------------------------------------------------------------
# no dead surfaces
# --------------------------------------------------------------------------

def test_scenario_and_alert_tabs_do_not_render_while_the_contract_withholds_them(live_html: str) -> None:
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    assert snapshot["scenario_contract"]["execution_available"] is False
    assert snapshot["alert_contract"]["service_available"] is False
    assert 'data-mq-tab="scenario"' not in live_html
    assert 'data-mq-tab="alerts"' not in live_html
    assert 'data-mq-panel="scenario"' not in live_html
    assert 'data-mq-panel="alerts"' not in live_html
    for tab_id in ("current", "drivers", "history"):
        assert f'data-mq-tab="{tab_id}"' in live_html
    # Withheld, but named — silence would be its own kind of dishonesty.
    assert "Scenario execution not available" in live_html
    assert "Alert service not available" in live_html


def test_the_page_is_not_advertised_in_production_navigation() -> None:
    """Navigation law: no menu entry until the Minimum Coherent Suite is proven."""
    nav = (TEMPLATES / "_navlinks.html.j2").read_text(encoding="utf-8")
    assert "macro_liquidity_regime" not in nav


def test_no_analyst_or_trade_authority_language_reaches_the_surface(live_html: str) -> None:
    surface = live_html.lower()
    for forbidden in ("buy signal", "sell signal", "price target", "recommend", "forecast that"):
        assert forbidden not in surface
    assert "display-only context" in surface
    assert "cannot rank, gate, size, originate a" in surface


# --------------------------------------------------------------------------
# honest absence
# --------------------------------------------------------------------------

def test_the_vector_renders_its_typed_state_honestly(live_html: str) -> None:
    """First prints show the WARMUP badge; later prints show the real numbers.

    The page must render whatever the artifact truthfully says — a WARMUP
    print draws no arrow and no fabricated zero, while a PRESENT vector (the
    artifact became a second print once build_all gained self-prior pickup in
    R2) renders its dx/dy values instead of the warmup badge.
    """
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    vec = snapshot["headline"]["one_month_vector"]
    warmup = labels.NULL_REASON["WARMUP"]
    if vec["status"] == "PRESENT":
        assert vec["dx"] is not None and vec["dy"] is not None
        assert warmup["en"] not in live_html
    else:
        assert vec["null_reason"] == "WARMUP"
        assert warmup["en"] in live_html
        assert warmup["zh"] in live_html
        assert "No movement arrow is drawn" in live_html
        # A zero vector would be a fabricated reading, not a missing one.
        assert "Δx +0" not in live_html and "Δx 0" not in live_html


def test_what_changed_matches_the_artifact_comparability(live_html: str) -> None:
    """Numeric comparison renders only when the artifact declares one; a
    missing/incomparable prior renders the typed refusal instead of an
    invented baseline."""
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    comparability = snapshot["changes"]["comparability"]
    if comparability == "NO_PRIOR":
        assert labels.COMPARABILITY["NO_PRIOR"]["en"] in live_html
        assert labels.COMPARABILITY["NO_PRIOR"]["zh"] in live_html
        assert "invent a baseline that does not exist" in live_html
    else:
        assert labels.COMPARABILITY["NO_PRIOR"]["en"] not in live_html


def test_absent_component_histories_draw_no_empty_chart(live_html: str) -> None:
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    assert snapshot["series"]["items"] == []
    assert labels.NULL_REASON["INSUFFICIENT_HISTORY"]["en"] in live_html
    assert "would read as a flat line at zero" in live_html


# --------------------------------------------------------------------------
# no producer slug reaches the reader
# --------------------------------------------------------------------------

_CODE_RECEIPT = re.compile(r"<code[^>]*>.*?</code>", re.S)
_ATTRS = re.compile(r"<[^>]+>")


def test_no_closed_vocabulary_token_is_rendered_raw_as_prose(live_html: str) -> None:
    """Tokens may appear only inside the <code> machine-receipt channel.

    Everything a reader reads as language goes through
    lib.macro_suite_labels, which is why an added contract token cannot ship as
    an English-looking shout like ``STALE_SOURCE``.
    """
    prose = _ATTRS.sub(" ", _CODE_RECEIPT.sub(" ", live_html))
    leaked = [token for token in (
        set(labels.known("freshness")) | set(labels.known("null_reason"))
        | set(labels.known("presence")) | set(labels.known("evidence_class"))
        | {"higher_tighter", "higher_stronger", "USD_bn", "composite_prior_only",
           "roc_over_owner_window", "NO_PRIOR", "context_only"}
    ) if re.search(rf"(?<![\w/.]){re.escape(token)}(?![\w/.])", prose)]
    assert leaked == [], leaked


def test_the_shipped_artifact_needs_no_unreviewed_label() -> None:
    labels.reset_unknown_tokens()
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    macro_suite_view.build_view(
        snapshot, page_built_at=BUILT_AT,
        artifact={"path": "x", "manifest_path": "y", "sha256": "z", "bytes": 1,
                  "min_client_contract": builder.MIN_CLIENT_CONTRACT})
    assert labels.unknown_tokens() == ()


def test_an_unknown_token_degrades_to_readable_text_and_is_reported() -> None:
    labels.reset_unknown_tokens()
    assert labels.label("freshness", "SOME_FUTURE_STATE") == {
        "en": "Some future state", "zh": "Some future state"}
    assert "freshness:SOME_FUTURE_STATE" in labels.unknown_tokens()
    labels.reset_unknown_tokens()


def test_every_published_horizon_and_region_has_a_reviewed_name() -> None:
    """`current` / `weeks` and an English region name are producer tokens; a
    Chinese reader must not meet either of them raw."""
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    horizons = {i["horizon"] for i in snapshot["implications"]["items"] if i.get("horizon")}
    assert horizons <= set(labels.known("horizon")), horizons
    assert snapshot["region"]["code"] in labels.known("region")


def test_every_published_metric_id_has_a_reviewed_public_name() -> None:
    """The reference product leaks provider series ids into its legends. Every
    metric this page shows must resolve to a reviewed name instead."""
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    published = {metric["metric_id"] for metric in snapshot["metrics"]["items"]}
    assert published <= set(labels.known("metric")), published - set(labels.known("metric"))


def test_a_percentile_is_never_silently_rescaled() -> None:
    """0.046 is a percentile on a 0-1 basis. Printing 4.6% would be a
    transformation the contract never declared."""
    assert labels.fmt_number(0.046031746031746035) == "0.04603"
    assert labels.fmt_ratio_pct(1.0) == "100%"


# --------------------------------------------------------------------------
# fail-closed reading
# --------------------------------------------------------------------------

def _assert_refusal(html: str, reason_token: str) -> None:
    reviewed = labels.NULL_REASON[reason_token]
    assert "mq-shell-degraded" in html
    assert reviewed["en"] in html and reviewed["zh"] in html
    assert "This workspace is not rendering a state" in html
    assert "本工作区当前不呈现任何状态" in html
    # Identity still renders (the reader must know WHICH page refused) ...
    assert "Liquidity Regime Monitor" in html
    # ... but no state, no axes, no map, no numbers from the refused artifact.
    assert "Easy funding / Weak support" not in html
    assert 'class="mq-map-svg"' not in html
    assert "20.05" not in html and "25.12" not in html
    assert 'role="tablist"' not in html


def test_a_tampered_content_hash_renders_the_refusal_page(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    body_path = _body_path(data_root)
    snapshot = json.loads(body_path.read_text(encoding="utf-8"))
    snapshot["headline"]["quadrant"]["x"] = 99.9   # content changed, hash not
    body_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                         encoding="utf-8")
    _assert_refusal(_build(tmp_path, data_root), "COMPUTATION_REFUSED")


def test_an_unsupported_schema_version_fails_closed(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    body_path = _body_path(data_root)
    snapshot = json.loads(body_path.read_text(encoding="utf-8"))
    snapshot["schema"]["version"] = "2.0.0"
    body_path.write_text(json.dumps(snapshot), encoding="utf-8")
    _assert_refusal(_build(tmp_path, data_root), "COMPUTATION_REFUSED")


def test_an_unknown_top_level_key_fails_closed(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    body_path = _body_path(data_root)
    snapshot = json.loads(body_path.read_text(encoding="utf-8"))
    snapshot["surprise_block"] = {"anything": True}
    body_path.write_text(json.dumps(snapshot), encoding="utf-8")
    _assert_refusal(_build(tmp_path, data_root), "COMPUTATION_REFUSED")


def test_malformed_json_renders_a_source_failure_not_an_empty_page(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    _body_path(data_root).write_text("{ not json", encoding="utf-8")
    _assert_refusal(_build(tmp_path, data_root), "SOURCE_FAILED")


def test_a_missing_artifact_renders_a_source_failure(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    _body_path(data_root).unlink()
    _assert_refusal(_build(tmp_path, data_root), "SOURCE_FAILED")


def test_a_manifest_that_disagrees_with_its_body_is_refused(tmp_path: Path) -> None:
    """Atomic publication exists so a header can never describe a different
    generation than the body. The reader enforces the same invariant."""
    data_root = _data_copy(tmp_path)
    manifest_path = _manifest_path(data_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["workspaces"]["liquidity_regime/US"]["content_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _assert_refusal(_build(tmp_path, data_root), "DISAGREEMENT")


def test_a_manifest_byte_count_that_disagrees_with_the_body_is_refused(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    manifest_path = _manifest_path(data_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["workspaces"]["liquidity_regime/US"]["bytes"] = 7
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _assert_refusal(_build(tmp_path, data_root), "DISAGREEMENT")


def test_a_workspace_the_manifest_does_not_publish_is_not_covered(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    manifest_path = _manifest_path(data_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["workspaces"] = {}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _assert_refusal(_build(tmp_path, data_root), "NOT_COVERED")


def test_a_manifest_demanding_a_newer_client_contract_is_refused(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    manifest_path = _manifest_path(data_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["min_client_contract"] = "mastermind.macro_workspace_snapshot.v2@2.0.0"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _assert_refusal(_build(tmp_path, data_root), "COMPUTATION_REFUSED")


def test_a_traversal_path_in_the_manifest_is_refused(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    manifest_path = _manifest_path(data_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["workspaces"]["liquidity_regime/US"]["path"] = "../../../etc/hosts"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _assert_refusal(_build(tmp_path, data_root), "SOURCE_FAILED")


# --------------------------------------------------------------------------
# the dominant visualization
# --------------------------------------------------------------------------

def test_the_quadrant_grid_follows_the_producer_classification_law() -> None:
    """A = low-x/high-y, B = high-x/high-y, C = low-x/low-y, D = high-x/low-y."""
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    view = macro_suite_view.build_view(
        snapshot, page_built_at=BUILT_AT,
        artifact={"path": "x", "manifest_path": "y", "sha256": "z", "bytes": 1,
                  "min_client_contract": builder.MIN_CLIENT_CONTRACT})
    cells = {cell["letter"]: cell for cell in view["quadrant_map"]["cells"]}
    assert cells["A"]["label"]["en"] == "Easy funding / Strong support"
    assert cells["B"]["label"]["en"] == "Tight funding / Strong support"
    assert cells["C"]["label"]["en"] == "Easy funding / Weak support"
    assert cells["D"]["label"]["en"] == "Tight funding / Weak support"
    assert cells["C"]["current"] is True
    assert [c["current"] for c in cells.values()].count(True) == 1
    # SVG y grows downward: a weak-support reading must plot in the LOWER half.
    assert view["quadrant_map"]["point"]["cy"] == pytest.approx(100 - 25.12)
    assert view["quadrant_map"]["point"]["cx"] == pytest.approx(20.05)


def test_a_missing_axis_value_plots_no_point_at_all() -> None:
    """The failure that would matter most: a missing axis silently drawn at 0."""
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    snapshot["headline"]["quadrant"]["y"] = None
    snapshot["headline"]["quadrant"]["y_status"] = "ABSENT"
    snapshot["headline"]["null_reason"] = "SOURCE_FAILED"
    view = macro_suite_view.build_view(
        snapshot, page_built_at=BUILT_AT,
        artifact={"path": "x", "manifest_path": "y", "sha256": "z", "bytes": 1,
                  "min_client_contract": builder.MIN_CLIENT_CONTRACT})
    assert view["quadrant_map"]["plotted"] is False
    assert view["quadrant_map"]["point"] is None


# --------------------------------------------------------------------------
# assets, registry and lane wiring
# --------------------------------------------------------------------------

def test_shared_assets_are_copied_byte_for_byte(tmp_path: Path) -> None:
    root = _isolated_root(tmp_path)
    builder.render(root, data_root=DATA_ROOT, out_dir=tmp_path / "site", page_built_at=BUILT_AT)
    for asset in builder.SHARED_ASSETS:
        assert (tmp_path / "site" / asset).read_bytes() == (TEMPLATES / asset).read_bytes()


def test_committed_site_assets_match_their_templates() -> None:
    """check_template_site_sync pairs templates/<x> with site/<x>; a drifted pair
    ships a page styled by one file and a stylesheet built from another."""
    for asset in builder.SHARED_ASSETS:
        assert (ROOT / "site" / asset).read_bytes() == (TEMPLATES / asset).read_bytes()


def test_the_suite_registry_only_publishes_workspaces_the_producer_has_built() -> None:
    from engine.market_os.macro_workspaces import registry as producer_registry
    built = set(producer_registry.built_ids())
    for page in builder.SUITE_PAGES:
        assert page.workspace_id in built, page.workspace_id
        assert page.region in producer_registry.entry(page.workspace_id)["regions_supported"]


def test_adding_a_workspace_page_needs_only_a_registry_entry_and_a_template() -> None:
    """The reuse contract for workspaces 2-12."""
    for page in builder.SUITE_PAGES:
        assert (TEMPLATES / page.template).exists()
        template = (TEMPLATES / page.template).read_text(encoding="utf-8")
        assert '{% import "_macro_suite_shell.html.j2" as shell' in template
        assert "shell.body(view)" in template
        assert "shell.degraded_body(view)" in template


def test_the_render_lane_owns_this_builder() -> None:
    render_yml = (ROOT / ".github" / "workflows" / "render.yml").read_text(encoding="utf-8")
    assert '- "scripts/build_macro_suite_pages.py"' in render_yml
    assert '- "templates/**"' in render_yml


def test_the_page_template_parses_and_the_shell_is_a_macro_library() -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True,
                      undefined=StrictUndefined)
    env.get_template("macro_liquidity_regime.html.j2")
    shell = env.get_template("_macro_suite_shell.html.j2").module
    for macro in ("body", "degraded_body", "context_header", "implications_ribbon",
                  "headline_band", "tab_bar", "quadrant_map", "diagnostics",
                  "what_changed", "component_metrics", "component_histories",
                  "evidence_drawer"):
        assert hasattr(shell, macro), macro


def test_the_suite_runtime_is_valid_javascript() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")
    for name in ("macro_suite_boot.js", "macro_suite.js"):
        result = subprocess.run([node, "--check", str(TEMPLATES / name)],
                                capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------
# evidence drawer
# --------------------------------------------------------------------------

def test_the_evidence_drawer_carries_every_clock_and_the_authority_ceiling(live_html: str) -> None:
    for key, name, _meaning in labels.CLOCKS:
        assert name["en"] in live_html, key
        assert name["zh"] in live_html, key
    for key, name, _meaning in labels.NON_ECONOMIC_CLOCKS:
        assert name["en"] in live_html, key
    assert "Not an economic clock" in live_html
    assert "DESCRIPTIVE" in live_html
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    assert snapshot["generation"]["content_sha256"] in live_html
    assert snapshot["generation"]["generation_id"] in live_html
    for source in snapshot["sources"]["items"]:
        assert source["label"]["en"] in live_html
        assert (source["provider"] or "") in live_html


def test_the_drawer_starts_closed_and_inert(live_html: str) -> None:
    assert 'aria-hidden="true" tabindex="-1" hidden inert' in live_html
    js = (TEMPLATES / "macro_suite.js").read_text(encoding="utf-8")
    for token in ("setInert(ui.shell, true);", "setInert(ui.siteNav, true);",
                  "handleDrawerKeydown", "state.lastFocus.focus({ preventScroll: true })",
                  "ui.drawer.setAttribute('aria-modal', 'true');"):
        assert token in js
    assert "https://" not in js, "the suite runtime must make no cross-origin read"
    assert "fetch(" not in js, "the page is server-rendered from a validated artifact"
