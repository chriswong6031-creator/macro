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
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

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
    "macro_monetary.html.j2",
    "_macro_suite_nav.html.j2",
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
    "macro_rates_curves.html.j2",
    "macro_trade_flows.html.j2",
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
    # The fourteen workspace pages plus the one suite hub.
    assert len(pages) == len(builder.SUITE_PAGES) + 1
    assert pages[-1].name == builder.HUB_PAGE.output
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

def _view_of(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return macro_suite_view.build_view(
        snapshot, page_built_at=BUILT_AT,
        artifact={"path": "x", "manifest_path": "y", "sha256": "z", "bytes": 1,
                  "min_client_contract": builder.MIN_CLIENT_CONTRACT})


def _snapshot_at(state_id: Any, x: Any, y: Any) -> dict[str, Any]:
    """The live artifact's SHAPE, carrying a chosen state and coordinate pair.

    Only the three values under test are overridden, so the fixture cannot drift
    away from the real contract, and the assertions cannot depend on what the
    producer published tonight.
    """
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    snapshot["headline"]["state_id"] = state_id
    snapshot["headline"]["quadrant"]["x"] = x
    snapshot["headline"]["quadrant"]["y"] = y
    return snapshot


# Independently chosen: the coordinates and the expected point are written out
# by hand from the stated law (A = low-x/high-y, B = high/high, C = low/low,
# D = high/low; SVG y grows downward, so cy = 100 - y). Nothing here is obtained
# by calling _QUADRANT_GRID or _quadrant_map, which is the whole point -- a table
# derived from the implementation would agree with any implementation.
_QUADRANT_LAW = (
    # state, x,    y,    expected cx, expected cy
    ("A", 20.0, 80.0, 20.0, 20.0),
    ("B", 80.0, 80.0, 80.0, 20.0),
    ("C", 20.0, 20.0, 20.0, 80.0),
    ("D", 80.0, 20.0, 80.0, 80.0),
)

_QUADRANT_MEANING = {
    "A": "Easy funding / Strong support",
    "B": "Tight funding / Strong support",
    "C": "Easy funding / Weak support",
    "D": "Tight funding / Weak support",
}


@pytest.mark.parametrize(("state", "x", "y", "cx", "cy"), _QUADRANT_LAW)
def test_the_quadrant_grid_follows_the_producer_classification_law(
    state: str, x: float, y: float, cx: float, cy: float,
) -> None:
    """The mapping law, on fixtures: every corner, at a coordinate we chose.

    This used to read the live snapshot and assert that C was current and that
    the point sat in the lower half. Both were true of one night's data, not of
    the law: a legitimate A/B/D publication would have reddened this test -- and,
    because it runs in a shared pack, every unrelated PR in that pack too.
    """
    view = _view_of(_snapshot_at(state, x, y))
    cells = {cell["letter"]: cell for cell in view["quadrant_map"]["cells"]}

    assert set(cells) == set(_QUADRANT_MEANING)
    for letter, meaning in _QUADRANT_MEANING.items():
        assert cells[letter]["label"]["en"] == meaning

    current = [letter for letter, cell in cells.items() if cell["current"]]
    assert current == [state]
    assert view["quadrant_map"]["point"] == {"cx": cx, "cy": cy}


def test_the_current_artifact_agrees_with_itself() -> None:
    """Live-data smoke: identity only, never today's letter or half-plane.

    Whatever the producer published, the page must plot THAT -- not a state the
    view decided on, and not a coordinate it invented. The assertions below hold
    for all four quadrants, so a regime change cannot red this test.
    """
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    view = _view_of(snapshot)
    quadrant_map = view["quadrant_map"]
    headline = snapshot["headline"]
    state_id = headline.get("state_id")

    current = [cell["letter"] for cell in quadrant_map["cells"] if cell["current"]]
    if state_id in _QUADRANT_MEANING:
        assert current == [state_id], "the page must show the producer's state, not its own"
    else:
        assert current == [], "an unclassified reading must not light up a quadrant"

    x, y = headline["quadrant"].get("x"), headline["quadrant"].get("y")
    if _is_finite_number(x) and _is_finite_number(y):
        assert quadrant_map["plotted"] is True
        assert quadrant_map["point"]["cx"] == pytest.approx(x)
        assert quadrant_map["point"]["cy"] == pytest.approx(100 - y)
    else:
        assert quadrant_map["plotted"] is False
        assert quadrant_map["point"] is None
        assert quadrant_map["absence"] is not None


def _is_finite_number(value: Any) -> bool:
    """Deliberately re-stated here rather than imported from the view.

    A test that borrows the implementation's own definition of "a number" agrees
    with it by construction, including when it is wrong.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@pytest.mark.parametrize("state_id", [None, "", "Z", "AB", 0])
def test_an_unclassified_reading_never_invents_a_current_quadrant(state_id: Any) -> None:
    """Absent or invalid producer classification must light up nothing."""
    view = _view_of(_snapshot_at(state_id, 20.0, 80.0))
    assert [c["letter"] for c in view["quadrant_map"]["cells"] if c["current"]] == []


@pytest.mark.parametrize("value", [None, "20", "", True, False, float("nan"),
                                   float("inf"), float("-inf"), [], {}])
def test_a_non_numeric_axis_value_plots_no_point(value: Any) -> None:
    """missing != zero, on the axis itself.

    ``true`` and ``NaN`` are the two that slipped through the obvious numeric
    check: bool is a subclass of int, and json.loads parses a bare NaN. The first
    plotted at cx=1.0, the second emitted cx="nan" -- a point that silently
    vanishes while the page still reports a plotted state.
    """
    for x, y in ((value, 80.0), (20.0, value)):
        view = _view_of(_snapshot_at("A", x, y))
        assert view["quadrant_map"]["plotted"] is False
        assert view["quadrant_map"]["point"] is None


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


# --------------------------------------------------------------------------
# absent is not zero, and absent is not no-change
#
# Every assertion below poisons ONE boundary and leaves the rest alone. The
# defect these replace was not that the code was complicated: it was that three
# separate renderers each decided from a FORMATTED string, where an em dash is
# truthy and a real "0" is not.
# --------------------------------------------------------------------------

_NULL_PAGES = ("business_activity", "consumer_payments", "trade_flows")


def _changes_view(prior: Any, current: Any, delta: Any,
                  comparability: str = "COMPARABLE") -> dict[str, Any]:
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    snapshot["changes"]["comparability"] = comparability
    snapshot["changes"]["deltas"] = [{
        "metric_id": "net_liquidity_4w", "prior_value": prior,
        "current_value": current, "delta": delta, "null_reason": None,
    }]
    return _view_of(snapshot)["changes"]["deltas"][0]


def test_a_real_zero_is_a_measurement_and_keeps_its_flat_class() -> None:
    row = _changes_view(1.0, 1.0, 0.0)
    assert row["comparable"] is True
    assert row["delta_present"] is True
    assert row["sign"] == "flat"
    assert row["delta"] == "0", "a measured no-change must still print its zero"
    assert row["absence"] is None


def test_equal_values_are_no_change_not_an_absence() -> None:
    row = _changes_view(763602.0, 763602.0, 0.0)
    assert (row["sign"], row["comparable"]) == ("flat", True)


@pytest.mark.parametrize("poison", [
    {"prior": None}, {"current": None}, {"delta": None},
    {"prior": "1.0"}, {"delta": float("nan")}, {"delta": True},
])
def test_one_absent_cell_makes_the_row_incomparable_and_never_flat(poison: dict) -> None:
    values = {"prior": 1.0, "current": 2.0, "delta": 1.0} | poison
    row = _changes_view(values["prior"], values["current"], values["delta"])
    assert row["comparable"] is False
    assert row["sign"] != "flat", "absent must never wear the no-change styling"
    assert row["absence"] is not None, "an absent cell owes a typed reason"
    for key in ("prior", "current", "delta"):
        if not row[f"{key}_present"]:
            assert row[key] is None, f"{key} must be absent, not the string 'None'"


def test_a_method_incomparable_table_is_gated_even_though_its_rows_are_numeric() -> None:
    """Comparability is a table-level verdict, not a per-cell one.

    Every row here carries three real numbers. The table must still refuse to
    show them as a comparison, because the method changed underneath -- a delta
    across a method change is a fabricated baseline, not a measurement.
    """
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    snapshot["changes"]["comparability"] = "METHOD_CHANGED"
    changes = _view_of(snapshot)["changes"]
    assert changes["comparable"] is False
    assert changes["absence"] is not None
    assert all(row["comparable"] for row in changes["deltas"]), \
        "the rows are individually fine; it is the COMPARISON that is refused"


@pytest.mark.parametrize("page", _NULL_PAGES)
def test_the_named_pages_never_print_python_none(page: str, tmp_path: Path) -> None:
    """The exact three manifestations Sol named, asserted on the built artifact."""
    html = (ROOT / "site" / f"macro_{page}.html").read_text(encoding="utf-8")
    assert ">None<" not in html
    assert "-None\"" not in html
    assert re.search(r'class="mq-delta mq-delta-(?:up|down|flat)"[^>]*>\s*<span class="mq-absent',
                     html) is None, "an absent cell is wearing a success class"


def _boundary_view(distance: Any) -> dict[str, Any]:
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    snapshot["headline"]["nearest_boundary"] = {
        "axis": snapshot["axes"]["items"][0]["axis_id"],
        "distance": distance, "null_reason": None}
    return _view_of(snapshot)["next_action"]


def test_a_boundary_distance_of_exactly_zero_is_the_most_watchable_case() -> None:
    """Sitting ON the line is not "no boundary" — but 0 is falsey."""
    assert _boundary_view(0.0)["token"] == "WATCH_BOUNDARY"


def test_a_missing_boundary_distance_does_not_become_a_watch() -> None:
    """An em dash is truthy; the absence of a distance is not a reason to watch."""
    assert _boundary_view(None)["token"] != "WATCH_BOUNDARY"


def test_every_next_action_carries_a_real_route_to_an_owned_region() -> None:
    html = (ROOT / "site" / "macro_liquidity_regime.html").read_text(encoding="utf-8")
    match = re.search(r'<a class="mq-next-route" href="(#[a-z0-9-]+)"', html)
    assert match, "the action must offer a real link, not a decorative CTA"
    target = match.group(1)[1:]
    assert f'id="{target}"' in html, "the route must land on an id this page actually has"
    # Never into a panel the tab script hides, and never into the evidence drawer,
    # which ships `hidden inert`: both look correct in markup and fail in a browser.
    assert target not in ("mq-panel-drivers", "mq-panel-history", "mq-evidence-drawer")


def test_the_action_precedes_the_full_table_and_ribbon_in_dom_order() -> None:
    html = (ROOT / "site" / "macro_liquidity_regime.html").read_text(encoding="utf-8")
    order = [m.group(1) for m in re.finditer(
        r'class="(mq-glance|mq-next mq-tone-[a-z]+|mq-study|mq-changed|mq-ribbon)"', html)]
    order = [o.split()[0] for o in order]
    assert order[:3] == ["mq-glance", "mq-next", "mq-study"], order[:5]
    assert order.index("mq-changed") > order.index("mq-next")
    assert order.index("mq-ribbon") > order.index("mq-next")


def test_absent_coverage_renders_a_typed_absence_not_an_unlabelled_dash() -> None:
    snapshot = json.loads(_body_path(DATA_ROOT).read_text(encoding="utf-8"))
    snapshot["availability"]["coverage_ratio"] = None
    context = _view_of(snapshot)["context"]
    assert context["coverage_present"] is False
    assert context["coverage_absence"] is not None
    assert context["coverage_absence"]["label"]["en"], "the dash owes the reader a word"


@pytest.mark.parametrize("page", sorted(p.output for p in builder.SUITE_PAGES))
def test_no_built_page_ever_emits_a_none_class_or_value(page: str) -> None:
    """One invariant covering all four `mq-delta-` emission sites at once.

    Three of them are guarded by a `*_present` flag and the fourth sits inside a
    presence check, so `mq-delta-None` cannot be reached today. This asserts the
    OUTPUT rather than the guards, so it still fails if a later change moves a
    selection rule and quietly reintroduces the class -- which is exactly how the
    driver tables got there in the first place.
    """
    html = (ROOT / "site" / page).read_text(encoding="utf-8")
    assert "mq-delta-None" not in html
    assert ">None<" not in html
    assert 'class="mq-delta mq-delta-"' not in html, "an empty sign class is the same bug"
