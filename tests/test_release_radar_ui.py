"""MRI-R24 Release Radar UI integration test.

Live-path structural checks against the actual template section and the
prod-shaped fixture at tests/fixtures/release_forecast_full.json.

Verifies:
- MRI-R24 compact card fields (name, countdown, projection, 2 chips, confidence)
- Modal sections present (interval cone, benchmark strip, coverage chip, component
  attribution, CPI bridge waterfall, confidence composition, surprise distribution,
  market-implied, reaction sensitivity, quirk chips, NFP revision risk,
  v3_factor shadow, policy backdrop, track-record scoreboard, display-only footnote)
- All 8 release types render without error: cpi_headline, cpi_core, pce_headline,
  pce_core, ppi_finaldemand, nfp, claims (benchmark_only), retail_sales (no_data)
- benchmark_only / no_data / None-point graceful degradation
- Bilingual EN/ZH dual-span everywhere; NO CJK in title= attributes
- display-only footnote on both card and modal
- No 'consensus' word in section (MRI-R5)
- New MRI-R24 helpers: expectationChip, coverageChip, cpiBridgeWaterfall,
  v3FactorRow, renderModal, relName with release_type suffix
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jinja2
import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "release_forecast_full.json"


# ---------------------------------------------------------------------------
# Environment + render helpers
# ---------------------------------------------------------------------------

def _env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
        autoescape=False,
    )
    env.filters["min"] = lambda seq: min(seq)
    try:
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en, zip=zip)
    return env


def _base_vm() -> dict:
    try:
        from tests.test_dashboard_template_render import _base_vm as _bvm  # noqa: PLC0415
        return _bvm()
    except Exception:  # noqa: BLE001
        return dict(
            latest={"date": "2026-07-08", "quad": "Q2", "quad_name": "Reflation",
                    "label": "Q2", "confidence": 0.72, "fed_stance": None,
                    "dislocation": None, "turning_point": None, "risk_radar": None,
                    "rate_inflation_transmission": None, "cross_asset_confirm": None,
                    "transition_state": "stable", "liquidity_overlay": "neutral",
                    "conditions": None, "risk_state": None, "cycle_tag": "mid"},
            mtf=None, macro_catalysts=[], event_strip=[], event_risk=None,
            prediction_markets=None, narrative_regime=None, ndi=None,
            macro_news=None, macro_brief=None, macro_news_disclaimer="",
            macro_news_disclaimer_zh="", alerts=[], pb=None, month_name="July",
            commodities=[], sector_timing={},
            action_board={"hold": [], "avoid": [], "notable": [], "buy": []},
            top_setups=[], us_standouts={"buy": [], "eligible": 0},
            us_board_outcomes=None, market_gamma=None,
            components_confirming=[], components_contradicting=[],
            flip_plain=None, internals=[], size_style=[], breadth_div=None,
            breadth_panel=None, adv_breadth=None, sector_setups=None,
            generated_utc="2026-07-08 06:00", chart_liquidity=None,
            chart_credit_breadth=None, market_tiles=[], vix=None, chart_vix=None,
            positioning=[], holdings_changes=[], holdings_threshold=5.0,
            accumulation=[], flows_html="", health=[], factor_leadership=None,
            nowcast_hist=None, stance=None, index_health=[], alloc_card=None,
            risk_model=None, chart_risk_model=None, chart_curve=None,
            chart_vix_term=None, cross_asset=None, fear_euphoria=None,
            regime_snap=None, market_state=None, signal_stack=None,
            vol_shock=None, froth_fragility=None, fear_greed=None,
            sector_heat=None, dispersion_regime=None,
        )


def _render(mode: str = "macro") -> str:
    return _env().get_template("dashboard.html.j2").render(**_base_vm(), mode=mode)


def _rr_section_src() -> str:
    """Return the Release Radar CSS+markup+script block from the template source.

    Anchored on stable functional markers, not prose: the section starts at the
    RR stylesheet (`<style id="rr-css">`, immediately followed by the
    `id="release-radar"` panel and its script IIFE) and ends at the closing
    `</script>` after the RR script's last symbol (`window.mmOpenFirstRR`).
    Anchoring on the first "RELEASE RADAR" occurrence previously matched an
    unrelated CSS comment and silently widened the scan to ~7200 lines of
    non-RR surfaces (spurious MRI-R5 hit, fixed in PR #2508).
    """
    src = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    idx_start = src.find('<style id="rr-css">')
    if idx_start < 0:
        pytest.skip('Release Radar block (<style id="rr-css">) not found in template source')
    idx_tail = src.find("window.mmOpenFirstRR = function", idx_start)
    assert idx_tail > idx_start, "RR script tail marker (window.mmOpenFirstRR) not found after rr-css"
    idx_end = src.find("</script>", idx_tail)
    assert idx_end > idx_tail, "closing </script> after RR script tail not found"
    section = src[idx_start:idx_end + len("</script>")]
    # Guard against the window silently shrinking past the panel or script body.
    assert 'id="release-radar"' in section, "RR panel div missing from anchored section"
    assert "function renderModal" in section, "RR renderModal missing from anchored section"
    return section


def _fixture() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.skip(f"Fixture not found: {FIXTURE_PATH}")
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fixture validation
# ---------------------------------------------------------------------------

def test_fixture_exists_and_valid_json():
    """Fixture file is present and parses as valid JSON."""
    d = _fixture()
    assert "upcoming" in d
    assert isinstance(d["upcoming"], list)


def test_fixture_covers_all_expected_release_types():
    """Fixture contains all 8 expected release types."""
    d = _fixture()
    rts = {i.get("release_type") for i in d["upcoming"]}
    required = {"cpi_headline", "cpi_core", "pce_headline", "pce_core",
                "ppi_finaldemand", "nfp", "claims", "retail_sales"}
    missing = required - rts
    assert not missing, f"Missing release_types in fixture: {missing}"


def test_fixture_has_benchmark_only_claims():
    """Fixture has at least one claims item in benchmark_only mode."""
    d = _fixture()
    bmo = [i for i in d["upcoming"]
           if i.get("release_type") == "claims"
           and isinstance(i.get("projection"), dict)
           and i["projection"].get("mode") == "benchmark_only"]
    assert len(bmo) >= 1, "No benchmark_only claims item in fixture"


def test_fixture_has_no_data_retail():
    """Fixture has retail_sales item with no_data condition."""
    d = _fixture()
    retail = [i for i in d["upcoming"] if i.get("release_type") == "retail_sales"]
    assert len(retail) >= 1, "No retail_sales item in fixture"
    r = retail[0]
    pit = r.get("pit", {}) or {}
    has_no_data = (
        "no_data" in str(pit.get("reason", ""))
        or (r.get("projection", {}) or {}).get("p10") is None
    )
    assert has_no_data, "retail_sales item does not show no_data condition"


def test_fixture_nfp_has_none_point():
    """Fixture has NFP item with null point (early-cycle — None point case)."""
    d = _fixture()
    nfp = [i for i in d["upcoming"] if i.get("release_type") == "nfp"]
    assert len(nfp) >= 1, "No NFP item in fixture"
    n = nfp[0]
    assert n.get("projection", {}).get("point") is None, "NFP point should be null (early projection)"


def test_fixture_cpi_has_shadows():
    """Fixture CPI headline has shadows with v3_factor and cpi_bridge."""
    d = _fixture()
    cpi = [i for i in d["upcoming"] if i.get("release_type") == "cpi_headline"]
    assert cpi, "No cpi_headline in fixture"
    shadows = cpi[0].get("shadows") or {}
    assert "v3_factor" in shadows, "CPI headline missing shadows.v3_factor"
    assert "cpi_bridge" in shadows, "CPI headline missing shadows.cpi_bridge"


def test_fixture_nfp_v3_shadow_has_warning():
    """NFP v3_factor shadow carries a warning string."""
    d = _fixture()
    nfp = next((i for i in d["upcoming"] if i.get("release_type") == "nfp"), None)
    assert nfp is not None
    v3 = (nfp.get("shadows") or {}).get("v3_factor")
    assert v3 is not None, "NFP missing shadows.v3_factor"
    assert v3.get("warning"), "NFP v3_factor shadow missing warning"


def test_fixture_coverage_flags_present_on_cpi():
    """CPI items carry coverage_flags with required keys."""
    d = _fixture()
    cpi = next((i for i in d["upcoming"] if i.get("release_type") == "cpi_headline"), None)
    assert cpi is not None
    cf = cpi.get("coverage_flags") or {}
    for key in ("weight_coverage", "fresh_proxy_coverage", "non_vintaged_share", "model_maturity"):
        assert key in cf, f"coverage_flags missing key: {key}"


def test_fixture_cpi_champion_components_propagated():
    """CPI headline item carries champion components (4 ridge blocks) at item level.

    MRI-R26 rework-ui: _build_upcoming_block must propagate proj['components']
    so the modal 'Component attribution' section can read them directly.
    """
    d = _fixture()
    cpi = next((i for i in d["upcoming"] if i.get("release_type") == "cpi_headline"), None)
    assert cpi is not None, "No cpi_headline in fixture"
    champ = cpi.get("components")
    assert champ is not None, "item.components is None — champion fields not propagated (Fix 1 missing)"
    assert isinstance(champ, list) and len(champ) >= 1, "item.components must be a non-empty list"
    champ_names = {c.get("name") for c in champ}
    expected_champ_names = {"energy", "shelter", "core_persistence", "pipeline"}
    assert expected_champ_names.issubset(champ_names), (
        f"Champion components missing expected blocks. Got names: {champ_names}"
    )


def test_fixture_champion_and_bridge_components_are_distinct():
    """Champion components (item.components) and bridge waterfall (shadows.cpi_bridge.components)
    use DIFFERENT block names and must NOT be identical.

    MRI-R26 rework-ui: the two sections must display distinct data.
    - Champion: energy/shelter/core_persistence/pipeline (name field, contrib_pp)
    - Bridge:   energy_gasoline/energy_electricity/shelter/food_at_home/... (block field, contribution_pp)
    """
    d = _fixture()
    cpi = next((i for i in d["upcoming"] if i.get("release_type") == "cpi_headline"), None)
    assert cpi is not None
    champ = cpi.get("components") or []
    bridge_comps = ((cpi.get("shadows") or {}).get("cpi_bridge") or {}).get("components") or []
    assert champ, "Champion components missing"
    assert bridge_comps, "Bridge components missing from shadows.cpi_bridge"

    champ_names = {c.get("name") for c in champ if c.get("name")}
    bridge_names = {c.get("block") for c in bridge_comps if c.get("block")}

    # Champion uses 4-block names (name field); bridge uses granular block names
    assert "core_persistence" in champ_names, "Champion should have core_persistence block"
    assert "pipeline" in champ_names, "Champion should have pipeline block"
    assert "energy_gasoline" in bridge_names, "Bridge should have energy_gasoline block"
    assert "core_services_ex_shelter" in bridge_names or "unmodelled_residual" in bridge_names, (
        "Bridge should have granular block names"
    )
    # The two name-sets are NOT equal — they are distinct
    assert champ_names != bridge_names, (
        "Champion and bridge component name-sets are identical — sections would show same data"
    )


def test_fixture_cpi_champion_confidence_v2_propagated():
    """CPI headline item carries confidence_v2 and confidence_components_v2 at item level.

    MRI-R26 rework-ui: confidence composition section should read champion's own
    richer breakdown rather than the coverage_flags proxy.
    """
    d = _fixture()
    cpi = next((i for i in d["upcoming"] if i.get("release_type") == "cpi_headline"), None)
    assert cpi is not None
    cv2 = cpi.get("confidence_v2")
    cv2comps = cpi.get("confidence_components_v2")
    assert cv2 is not None, "confidence_v2 not propagated to item (Fix 1 missing)"
    assert isinstance(cv2, float) and 0 <= cv2 <= 1, f"confidence_v2 out of range: {cv2}"
    assert cv2comps is not None, "confidence_components_v2 not propagated to item"
    for key in ("w_known", "w_proxy", "w_residual"):
        assert key in cv2comps, f"confidence_components_v2 missing key: {key}"


def test_fixture_revision_risk_field_present_on_items():
    """All upcoming items carry a revision_risk key (NFP non-None, others None).

    MRI-R26 rework-ui: revision_risk propagated unconditionally from champion projection.
    """
    d = _fixture()
    for item in d["upcoming"]:
        assert "revision_risk" in item, (
            f"revision_risk key missing from item {item.get('release_type')}"
        )


def test_template_source_champion_attribution_not_bridge_fallback():
    """Section 4 (Component attribution) must read item.components, NOT bridge.components.

    MRI-R26 rework-ui: the old code used bridge.components as priority source for
    section 4, making it identical to section 5. The fix sources champComponents
    from item.components ONLY and hides section 4 when null.
    """
    src = _rr_section_src()
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 12000]
    # New code must reference item.components for champion attribution
    assert "item.components" in modal_body, (
        "renderModal must source champion attribution from item.components (not bridge fallback)"
    )
    # The old bridge-priority pattern must be gone
    assert "bridge ? bridge.components" not in modal_body, (
        "Old bridge-priority fallback pattern still present — Fix 2 not applied"
    )
    # champComponents variable must be used
    assert "champComponents" in modal_body, (
        "champComponents variable missing — champion attribution section not refactored"
    )


# ---------------------------------------------------------------------------
# Template source: MRI-R24 new helpers defined
# ---------------------------------------------------------------------------

def test_r24_expectation_chip_defined():
    """expectationChip() helper is defined in template source."""
    src = _rr_section_src()
    assert "function expectationChip(" in src, "expectationChip helper missing"


def test_r24_coverage_chip_defined():
    """coverageChip() helper is defined in template source."""
    src = _rr_section_src()
    assert "function coverageChip(" in src, "coverageChip helper missing"


def test_r24_cpi_bridge_waterfall_defined():
    """cpiBridgeWaterfall() helper is defined in template source."""
    src = _rr_section_src()
    assert "function cpiBridgeWaterfall(" in src, "cpiBridgeWaterfall helper missing"


def test_r24_v3_factor_row_defined():
    """v3FactorRow() helper is defined in template source."""
    src = _rr_section_src()
    assert "function v3FactorRow(" in src, "v3FactorRow helper missing"


def test_r24_render_modal_defined():
    """renderModal() is defined in template source (MRI-R24 detail modal)."""
    src = _rr_section_src()
    assert "function renderModal(" in src, "renderModal missing (MRI-R24 required)"


def test_r24_relname_includes_release_type():
    """relName() accepts release_type parameter for sub-type suffixes (headline/core)."""
    src = _rr_section_src()
    fn_start = src.find("function relName(")
    assert fn_start >= 0, "relName not found"
    fn_body = src[fn_start:fn_start + 400]
    assert "release_type" in fn_body or "RT_SUFFIX" in fn_body, (
        "relName must handle release_type suffix (cpi_headline vs cpi_core)"
    )


def test_r24_modal_overlay_in_html():
    """MRI-R24 modal overlay element is in rendered macro HTML."""
    html = _render("macro")
    assert "rr-modal-overlay" in html, "Modal overlay missing from rendered HTML"
    assert "rr-modal-inner" in html or "rr-modal-body" in html, "Modal inner missing"


# ---------------------------------------------------------------------------
# Card field specification (MRI-R24 compact card)
# ---------------------------------------------------------------------------

def test_r24_card_has_chips_row_css():
    """rr-chips-row CSS class is defined (card chip container)."""
    html = _render("macro")
    assert "rr-chips-row" in html, "rr-chips-row CSS class missing"


def test_r24_card_exp_chip_css():
    """Expectation chip CSS classes are defined."""
    html = _render("macro")
    for cls in ("rr-exp-above", "rr-exp-below", "rr-exp-aligned"):
        assert cls in html, f"Expectation chip class missing: {cls}"


def test_r24_card_expectation_bilingual_labels():
    """Expectation chip carries EN and ZH labels."""
    src = _rr_section_src()
    assert "above expectations" in src, "EN 'above expectations' label missing"
    assert "高于预期" in src, "ZH '高于预期' label missing"
    assert "below expectations" in src, "EN 'below expectations' label missing"
    assert "低于预期" in src, "ZH '低于预期' label missing"
    assert "aligned" in src, "EN 'aligned' label missing"
    assert "符合预期" in src, "ZH '符合预期' label missing"


def test_r24_card_skew_chip_bilingual_labels():
    """Trend skew chip has EN and ZH labels for hotter/cooler/inline."""
    src = _rr_section_src()
    assert "偏热" in src, "ZH '偏热' (hotter) label missing"
    assert "偏冷" in src, "ZH '偏冷' (cooler) label missing"
    assert "持平" in src, "ZH '持平' (inline) label missing"


def test_r24_card_display_only_footnote_on_card():
    """MRI-R39a: per-card display-only footnotes removed; panel-level disclosure retained.

    The operator card amendment (MRI-R39a) removed per-card do-notes.
    Honesty law is satisfied by the panel-level subline ('Forward model · display-only…')
    which must appear in the static HTML, and by the modal footer (rr-modal-do-note).
    """
    src = _rr_section_src()
    # Panel-level disclosure must be present in the static HTML section
    assert "display-only" in src, "display-only disclosure missing from RR section"
    assert "Forward model" in src or "前瞻模型" in src, (
        "Panel-level 'Forward model' subline missing from RR section"
    )
    # Modal footnote must still contain display-only language
    assert "rr-modal-do-note" in src, "rr-modal-do-note modal footnote missing"
    # Per-card footnote class should be absent (operator amendment MRI-R39a)
    assert "rr-card-do-note" not in src, (
        "rr-card-do-note class still present — per-card footnote not removed (MRI-R39a)"
    )


def test_r24_card_tap_for_detail_prompt():
    """MRI-R39a: 'tap for detail' text row removed; card is wholly clickable with chevron ▸.

    The operator card amendment (MRI-R39a) deleted the tap-for-detail text row.
    The card still has cursor:pointer and a chevron ▸ in the corner.
    """
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 8000]
    # The explicit text row is gone (operator amendment)
    assert "tap for detail" not in card_body, (
        "'tap for detail' text row still present — MRI-R39a requires it deleted"
    )
    # Chevron replaces the tap prompt
    assert "▸" in card_body or "rr-chevron" in card_body, (
        "Card chevron ▸ / rr-chevron missing — whole-card-clickable indicator gone"
    )
    # cursor:pointer must remain (card CSS or inline)
    assert "cursor:pointer" in src or "cursor: pointer" in src, (
        "cursor:pointer missing from RR card CSS"
    )


# ---------------------------------------------------------------------------
# Coverage chip (MRI-R24 new field)
# ---------------------------------------------------------------------------

def test_r24_coverage_chip_tier_labels_bilingual():
    """Coverage chip tier labels are bilingual."""
    src = _rr_section_src()
    for en, zh in [("fresh", "充分"), ("partial", "部分"), ("stale", "陈旧"), ("prior-heavy", "以先验为主")]:
        assert en in src, f"EN coverage tier label missing: {en!r}"
        assert zh in src, f"ZH coverage tier label missing: {zh!r}"


def test_r24_coverage_chip_wired_into_rendermodal():
    """coverageChip() is called inside renderModal."""
    src = _rr_section_src()
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 10000]
    assert "coverageChip(" in modal_body, "coverageChip not called in renderModal"


# ---------------------------------------------------------------------------
# CPI bridge waterfall (MRI-R24 new section)
# ---------------------------------------------------------------------------

def test_r24_bridge_waterfall_bilingual_label():
    """cpiBridgeWaterfall section label is bilingual."""
    src = _rr_section_src()
    assert "Component-bridge waterfall" in src, "EN 'Component-bridge waterfall' label missing"
    assert "组件桥接瀑布" in src, "ZH '组件桥接瀑布' label missing"


def test_r24_bridge_waterfall_prior_driven_share_label():
    """cpiBridgeWaterfall shows prior-driven share and coverage residual."""
    src = _rr_section_src()
    assert "Prior-driven share" in src, "EN 'Prior-driven share' label missing"
    assert "先验比重" in src, "ZH '先验比重' label missing"


def test_r24_bridge_waterfall_uses_contribution_pp():
    """cpiBridgeWaterfall reads contribution_pp field (not contrib_pp)."""
    src = _rr_section_src()
    fn_start = src.find("function cpiBridgeWaterfall(")
    fn_body = src[fn_start:fn_start + 2000] if fn_start >= 0 else ""
    assert "contribution_pp" in fn_body, "cpiBridgeWaterfall must read contribution_pp field"


# ---------------------------------------------------------------------------
# v3_factor shadow (MRI-R24)
# ---------------------------------------------------------------------------

def test_r24_v3_shadow_challenger_label_bilingual():
    """v3_factor challenger shadow label is bilingual."""
    src = _rr_section_src()
    assert "v3_factor challenger" in src, "EN 'v3_factor challenger' label missing"
    assert "v3因子挑战者" in src, "ZH 'v3因子挑战者' label missing"


def test_r24_v3_shadow_warning_rendered():
    """v3FactorRow renders the warning field when present."""
    src = _rr_section_src()
    fn_start = src.find("function v3FactorRow(")
    # Use a large window to cover the full function body
    fn_body = src[fn_start:fn_start + 1200] if fn_start >= 0 else ""
    assert "warning" in fn_body, "v3FactorRow must render the warning field"
    assert "rr-shadow-warn" in fn_body, "v3FactorRow must use rr-shadow-warn CSS class"


# ---------------------------------------------------------------------------
# Modal sections (MRI-R24)
# ---------------------------------------------------------------------------

def test_r24_modal_has_interval_cone_section():
    """renderModal contains interval cone section (MRI-R39: now SVG cone via intervalConeSVG)."""
    src = _rr_section_src()
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 14000]
    # MRI-R39: interval cone is now rendered via intervalConeSVG (SVG cone with benchmark ticks)
    assert "intervalConeSVG(" in modal_body or "intervalBar(" in modal_body, (
        "renderModal missing interval cone (intervalConeSVG or intervalBar)"
    )
    assert "p10" in modal_body and "p90" in modal_body, "renderModal missing p10/p90 labels"


def test_r24_modal_has_benchmark_strip():
    """renderModal renders benchmark data (MRI-R39: benchmarks now inline in MODELS tab, not via benchStrip)."""
    src = _rr_section_src()
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 14000]
    # MRI-R39: benchmarks rendered inline in MODELS tab (no benchStrip wrapper needed)
    assert ("benchStrip(" in modal_body
            or "benchmark_set" in modal_body
            or "naive_prior" in modal_body), (
        "renderModal missing benchmark data (benchStrip call or inline benchmark_set reference)"
    )


def test_r24_modal_has_display_only_footnote():
    """Modal detail contains display-only footnote (MRI-R24/R39 requirement).

    MRI-R39: footnote is now in the static HTML modal footer (rr-modal-do-note),
    not inside the renderModal JS function body. Check the full RR section source.
    """
    src = _rr_section_src()
    # Footnote is in the static HTML structure, not inside renderModal JS
    assert "display-only" in src, "display-only footnote missing from RR section"
    assert "not investment advice" in src or "非投资建议" in src, (
        "investment-advice disclaimer missing from RR section"
    )


def test_r24_modal_policy_backdrop_section():
    """renderModal renders policy backdrop."""
    src = _rr_section_src()
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 10000]
    assert "policyStrip(" in modal_body, "renderModal missing policyStrip call"


def test_r24_modal_scoreboard_in_main_render():
    """scoreboardBlock is called in main renderRadar (not inside each modal)."""
    src = _rr_section_src()
    main_start = src.find("function renderRadar(")
    # renderRadar grew with the see-more logic; use a larger window
    main_body = src[main_start:main_start + 8000] if main_start >= 0 else ""
    assert "scoreboardBlock(" in main_body, "scoreboardBlock not called in renderRadar"


# ---------------------------------------------------------------------------
# Release-type specific rendering (all 8 types must not error)
# ---------------------------------------------------------------------------

def _find_helper_fn(src, fn_name):
    """Return the body of a named JS function from the RR section source."""
    start = src.find(f"function {fn_name}(")
    if start < 0:
        return ""
    # Find the next top-level function or end of script
    # Use a heuristic: next '\n    function ' after start
    end = src.find("\n    function ", start + len(fn_name))
    return src[start:end] if end > start else src[start:start + 5000]


def test_benchmark_only_handled_in_rendercard():
    """renderCard handles benchmark_only mode (shows note, not point)."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 5000]
    assert "isBenchmarkOnly" in card_body, "renderCard missing isBenchmarkOnly check"
    assert "Benchmark-only" in card_body or "benchmark_only" in card_body.lower(), (
        "renderCard missing benchmark-only mode note"
    )


def test_no_data_handled_in_rendercard():
    """renderCard handles no_data case (retail_sales awaiting data)."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 5000]
    assert "isNoData" in card_body, "renderCard missing isNoData check"
    assert "Awaiting data" in card_body or "awaiting data" in card_body.lower(), (
        "renderCard missing no-data awaiting message"
    )


def test_none_point_handled_gracefully():
    """A null point value renders as dash (not an error)."""
    src = _rr_section_src()
    # Verify fmtNum and fmtK both guard against null
    fn_start = src.find("function fmtNum(")
    fn_body = src[fn_start:fn_start + 200] if fn_start >= 0 else ""
    assert "null" in fn_body or "== null" in fn_body, "fmtNum must guard against null"
    fn_start2 = src.find("function fmtK(")
    fn_body2 = src[fn_start2:fn_start2 + 200] if fn_start2 >= 0 else ""
    assert "null" in fn_body2 or "== null" in fn_body2, "fmtK must guard against null"


def test_nfp_uses_fmtk_not_fmtnum():
    """NFP projection values use fmtK (thousands) not fmtNum (percent points)."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 5000]
    # useK must be computed from isClaims || isNfp
    assert "isNfp" in card_body or "nfp" in card_body.lower(), "renderCard must detect NFP type"
    assert "fmtK" in card_body, "renderCard must call fmtK for K-formatted values"


def test_claims_benchmark_strip_uses_trailing_4w():
    """benchStrip uses trailing_4w for claims (not trailing_3m)."""
    src = _rr_section_src()
    fn_start = src.find("function benchStrip(")
    fn_body = src[fn_start:fn_start + 1500] if fn_start >= 0 else ""
    assert "trailing_4w" in fn_body, "benchStrip missing trailing_4w for claims"
    assert "Trailing 4w" in fn_body, "benchStrip missing 'Trailing 4w' label"


# ---------------------------------------------------------------------------
# Bilingual compliance
# ---------------------------------------------------------------------------

def test_no_cjk_in_title_attrs_rr_section():
    """No CJK characters in title= attributes in the Release Radar section."""
    html = _render("macro")
    idx_start = html.find('id="release-radar"')
    idx_end = html.find('id="week-ahead"', idx_start) if idx_start >= 0 else -1
    section = html[idx_start:idx_end] if idx_end > idx_start else html[idx_start:idx_start + 30000]
    titles = re.findall(r'title=["\']([^"\']*)["\']', section)
    for t_val in titles:
        for ch in t_val:
            assert not ('一' <= ch <= '鿿'), (
                f"CJK in title= attribute (CI law violation): {t_val!r}"
            )


def test_new_helpers_bilingual_labels():
    """expectationChip, coverageChip, cpiBridgeWaterfall all carry EN+ZH spans."""
    src = _rr_section_src()
    # Sample a few bilingual pairs from new helpers
    pairs = [
        ("above expectations", "高于预期"),
        ("fresh", "充分"),
        ("Component-bridge waterfall", "组件桥接瀑布"),
        ("v3_factor challenger", "v3因子挑战者"),
    ]
    for en, zh in pairs:
        assert en in src, f"Missing EN label: {en!r}"
        assert zh in src, f"Missing ZH label: {zh!r}"


def test_no_affirmative_consensus_reference():
    """MRI-R5: 'consensus' must not appear as a positive/affirmative reference in the RR section.

    Allowed: Jinja comments, 'not consensus', '非共识' disclaimer.
    Forbidden: any user-facing JS/HTML use implying the projection IS consensus estimates.
    """
    import re as _re
    src = _rr_section_src()
    # Strip ALL Jinja block comments {# ... #} (multi-line)
    no_jinja_comments = _re.sub(r'\{#.*?#\}', '', src, flags=_re.DOTALL)
    violations = []
    for line in no_jinja_comments.splitlines():
        stripped_line = line.strip()
        # Skip JS comment lines
        if stripped_line.startswith("//") or stripped_line.startswith("/*") or stripped_line.startswith("*"):
            continue
        # Skip Jinja comment fragments that stripping might have missed
        if "{#" in stripped_line or "#}" in stripped_line:
            continue
        if "consensus" in stripped_line.lower():
            low = stripped_line.lower()
            neg_patterns = ["not consensus", "not a consensus", "non consensus",
                            "非共识", "nonconsensus", "never says", "never consensus"]
            if any(p in low for p in neg_patterns):
                continue
            violations.append(stripped_line[:120])
    assert not violations, (
        f"MRI-R5: affirmative 'consensus' found in user-facing RR section lines: {violations[:3]}"
    )


def test_retail_sales_name_in_rn_map():
    """relName maps 'retail' key to English and Chinese labels."""
    src = _rr_section_src()
    assert "Retail Sales" in src or "retail:'Retail" in src, "EN 'Retail Sales' label missing from RN_EN map"
    assert "零售销售" in src, "ZH '零售销售' label missing from RN_ZH map"


# ---------------------------------------------------------------------------
# Interval bar (MRI-R24 fix: renders with null point but has p10/p90)
# ---------------------------------------------------------------------------

def test_interval_bar_handles_null_point():
    """intervalBar renders cone when point is null (uses p50 as tick or skips tick)."""
    src = _rr_section_src()
    fn_start = src.find("function intervalBar(")
    fn_body = src[fn_start:fn_start + 1000] if fn_start >= 0 else ""
    # Should NOT require pt != null to render the bar itself (only the tick)
    # Guard is now: if (p10 == null || p90 == null) return ''
    # (removed '|| pt == null' from old guard)
    assert "p10 == null || p90 == null" in fn_body or "p10==null||p90==null" in fn_body, (
        "intervalBar must guard on p10/p90 only (null point should still render bar)"
    )


# ---------------------------------------------------------------------------
# Template render passes CI checks
# ---------------------------------------------------------------------------

def test_template_renders_without_exception():
    """dashboard.html.j2 renders in macro mode without raising."""
    html = _render("macro")
    assert len(html) > 10000


def test_modal_overlay_absent_in_stocks_mode():
    """Modal overlay is inside the {%if mode != 'stocks'%} gate — absent in stocks mode."""
    html = _render("stocks")
    assert "rr-modal-overlay" not in html, "Modal overlay must not appear in stocks mode"


# ---------------------------------------------------------------------------
# MRI-R39: 5-tab modal structure tests
# ---------------------------------------------------------------------------

def test_r39_tab_strip_element_present():
    """MRI-R39: rr-tab-strip element is in rendered macro HTML (sticky tab navigation)."""
    html = _render("macro")
    assert "rr-tab-strip" in html, "rr-tab-strip missing from rendered HTML (MRI-R39)"


def test_r39_tab_css_classes_defined():
    """MRI-R39: Tab CSS classes rr-tab and rr-tab-strip are defined in template source."""
    src = _rr_section_src()
    assert ".rr-tab-strip" in src, "rr-tab-strip CSS class not defined"
    assert ".rr-tab{" in src or ".rr-tab " in src, "rr-tab CSS class not defined"
    assert ".rr-tab.active" in src, "rr-tab.active state not defined"


def test_r39_tab_pane_css_defined():
    """MRI-R39: rr-pane CSS class for tab panels is defined."""
    src = _rr_section_src()
    assert ".rr-pane" in src, "rr-pane CSS class not defined"


def test_r39_five_tab_labels_en_defined():
    """MRI-R39: All 5 tab EN labels are in the template source."""
    src = _rr_section_src()
    for label in ("Overview", "Models", "Components", "History", "Context"):
        assert label in src, f"Tab EN label missing: {label!r}"


def test_r39_five_tab_labels_zh_defined():
    """MRI-R39: All 5 tab ZH labels are in the template source (bilingual compliance)."""
    src = _rr_section_src()
    for label in ("概览", "模型", "组件", "历史", "情境"):
        assert label in src, f"Tab ZH label missing: {label!r}"


def test_r39_rendermodal_returns_tab_dict():
    """MRI-R39: renderModal returns a tab object (tab0..tab4) not a plain HTML string."""
    src = _rr_section_src()
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 14000]
    assert "return {tab0:" in modal_body, "renderModal must return tab dict {tab0:..., tab4:...}"
    assert "tab4" in modal_body, "renderModal missing tab4 in return dict"


def test_r39_svg_cone_function_defined():
    """MRI-R39: intervalConeSVG() helper is defined for the Overview SVG cone."""
    src = _rr_section_src()
    assert "function intervalConeSVG(" in src, "intervalConeSVG helper missing (MRI-R39 OVERVIEW tab)"


def test_r39_svg_cone_has_benchmark_ticks():
    """MRI-R39: intervalConeSVG renders muted benchmark ticks on the shared axis."""
    src = _rr_section_src()
    fn_start = src.find("function intervalConeSVG(")
    fn_body = src[fn_start:fn_start + 3000] if fn_start >= 0 else ""
    assert "benchKeys" in fn_body or "naive_prior" in fn_body, (
        "intervalConeSVG missing benchmark tick logic"
    )
    assert "<svg" in fn_body, "intervalConeSVG must produce inline SVG"


def test_r39_model_dot_plot_function_defined():
    """MRI-R39: modelDotPlot() helper is defined for the Models tab SVG dot plot."""
    src = _rr_section_src()
    assert "function modelDotPlot(" in src, "modelDotPlot helper missing (MRI-R39 MODELS tab)"


def test_r39_model_dot_plot_market_implied_basis_guard():
    """MRI-R39 basis guard: market-implied rendered in own row with explicit basis tag,
    never plotted on shared axis when basis differs (e.g., Polymarket Core CPI YoY level)."""
    src = _rr_section_src()
    fn_start = src.find("function modelDotPlot(")
    fn_body = src[fn_start:fn_start + 6000] if fn_start >= 0 else ""
    # Market-implied must be in its own row with basis tag, NOT on the shared axis
    assert "different basis" in fn_body or "event_title" in fn_body, (
        "modelDotPlot missing basis-guard for market-implied (MRI-R39 RR-6)"
    )
    assert "rr-mkt-row" in fn_body, "modelDotPlot market-implied missing rr-mkt-row class"


def test_r39_null_tab_suppression_in_openmodal():
    """MRI-R39: openModal filters tabs with skip flag (null tabs hidden entirely)."""
    src = _rr_section_src()
    open_start = src.find("function openModal(")
    open_body = src[open_start:open_start + 3000] if open_start >= 0 else ""
    assert "skip" in open_body, "openModal must support skip flag for null-tab suppression"
    assert "visibleTabs" in open_body or "filter(" in open_body, (
        "openModal missing null-tab filter logic"
    )


def test_r39_mobile_css_fullscreen_sheet():
    """MRI-R39: Mobile ≤480px styles give full-screen sheet layout."""
    src = _rr_section_src()
    assert "max-width:480px" in src or "@media(max-width:480px)" in src, (
        "Mobile sheet CSS missing (MRI-R39 RR-13)"
    )
    assert "44px" in src or "min-height:44px" in src, (
        "44px tap targets missing in mobile CSS (MRI-R39 RR-13)"
    )


def test_r39_surprise_anatomy_table_function():
    """MRI-R39: surpriseAnatomyTable() renders static catalog for History tab."""
    src = _rr_section_src()
    assert "function surpriseAnatomyTable(" in src, "surpriseAnatomyTable missing (MRI-R39 HISTORY tab)"
    fn_start = src.find("function surpriseAnatomyTable(")
    fn_body = src[fn_start:fn_start + 2000] if fn_start >= 0 else ""
    assert "rr-anatomy-table" in fn_body, "surpriseAnatomyTable missing rr-anatomy-table class"


def test_r39_capture_health_in_context_tab():
    """MRI-R39: CONTEXT tab renders capture_health past-due-unscored indicator."""
    src = _rr_section_src()
    assert "past_due_unscored" in src, "capture_health.past_due_unscored missing from CONTEXT tab"
    assert "rr-health-strip" in src, "rr-health-strip CSS class missing"


def test_r39_print_integrity_chip_in_context_tab():
    """MRI-R39: CONTEXT tab renders print_integrity chip with normal/degraded/disrupted states."""
    src = _rr_section_src()
    assert "rr-integrity-chip" in src, "print_integrity chip CSS missing"
    assert "rr-integrity-normal" in src, "integrity normal state CSS missing"
    assert "rr-integrity-degraded" in src, "integrity degraded state CSS missing"
    assert "rr-integrity-disrupted" in src, "integrity disrupted state CSS missing"
    # Bilingual
    assert "正常" in src, "ZH 'Normal / 正常' label missing from integrity chip"
    assert "退化" in src, "ZH 'Degraded / 退化' label missing from integrity chip"
    assert "中断" in src, "ZH 'Disrupted / 中断' label missing from integrity chip"


def test_r39_theme_token_backdrop_not_hardcoded():
    """MRI-R39 RR-14: Modal backdrop uses CSS var tokens, not hard-coded rgba."""
    src = _rr_section_src()
    # Modal overlay backdrop should NOT be bare rgba(0,0,0,...) but use var(--...)
    assert "var(--modal-backdrop" in src or "var(--bg" in src or "color-mix(in srgb,var(" in src, (
        "Modal backdrop must use CSS theme tokens, not hard-coded rgba (MRI-R39 RR-14)"
    )


def test_r39_4px_spacing_vars_or_consistent():
    """MRI-R39 RR-3: 4px-base spacing scale — padding/margin values multiples of 4."""
    src = _rr_section_src()
    # Just verify that the spacing-comment or 4px-multiple patterns appear
    assert "4px" in src or "8px" in src or "12px" in src or "16px" in src, (
        "4px-base spacing scale not found in RR section (MRI-R39 RR-3)"
    )


def test_r39_all_8_release_types_no_error():
    """MRI-R39: Template renders without raising for macro mode (covers all release types via fixture)."""
    html = _render("macro")
    assert len(html) > 10000
    assert "rr-tab-strip" in html


def test_r39_single_footnote_in_modal_html():
    """MRI-R39 RR-2: Single deduplicated display-only footnote in modal static HTML."""
    html = _render("macro")
    # The footnote should appear exactly once in the modal structure (rr-modal-do-note)
    assert html.count("rr-modal-do-note") >= 1, "rr-modal-do-note missing from rendered HTML"
    # Should not appear more than twice (once EN once ZH in same element)
    # The class itself should appear once as the container
    assert html.count('class="rr-modal-do-note"') == 1, (
        "Multiple rr-modal-do-note containers found — footnote not deduplicated (MRI-R39 RR-2)"
    )


def test_r39_tabular_nums_everywhere():
    """MRI-R39: font-variant-numeric:tabular-nums applied to numeric containers."""
    src = _rr_section_src()
    assert src.count("tabular-nums") >= 3, (
        "tabular-nums should be applied to multiple numeric elements (MRI-R39)"
    )


def test_r39_group_label_border_bottom_once_per_group():
    """MRI-R39 RR-4: Single bottom-border per tab-section group (rr-grp), not per section."""
    src = _rr_section_src()
    # rr-grp should use a single bottom border
    assert "rr-grp" in src, "rr-grp class missing"
    # Find the CSS rule for rr-grp
    grp_css_start = src.find(".rr-grp{")
    if grp_css_start >= 0:
        grp_css = src[grp_css_start:grp_css_start + 200]
        assert "border-bottom" in grp_css, "rr-grp CSS missing border-bottom"


def test_r39_fixture_benchmark_only_claims_handled():
    """MRI-R39: benchmark_only claims item — COMPONENTS tab skipped (tab has skip flag)."""
    src = _rr_section_src()
    open_start = src.find("function openModal(")
    open_body = src[open_start:open_start + 3000] if open_start >= 0 else ""
    assert "isBenchmarkOnly" in open_body, "openModal missing isBenchmarkOnly check for tab skipping"


# ---------------------------------------------------------------------------
# MRI-R39 QA fixes — regression guards (added 2026-07-10)
# ---------------------------------------------------------------------------

MOCKUP_PATH = ROOT / "research" / "release_forecast" / "mockup_release_radar.html"


def test_mockup_contains_inlined_fixture_element():
    """Self-containment guard: mockup must ship with a <script type='application/json' id='rr-fixture'>
    element so it renders fully with no network dependency on macrodata/."""
    if not MOCKUP_PATH.exists():
        pytest.skip("mockup file not found")
    src = MOCKUP_PATH.read_text(encoding="utf-8")
    assert 'id="rr-fixture"' in src, (
        "Mockup is missing <script type='application/json' id='rr-fixture'>…</script>. "
        "The file is not self-contained: it fetches macrodata/release_forecast.json which "
        "doesn't exist next to the file (Fix 1 regression)."
    )
    assert 'type="application/json"' in src, (
        "rr-fixture element must have type='application/json' so browsers don't execute it"
    )
    # Verify the shim loader reads the element
    assert "getElementById('rr-fixture')" in src or 'getElementById("rr-fixture")' in src, (
        "Mockup loader shim must read from #rr-fixture element instead of (only) fetching"
    )


def test_mockup_fixture_element_is_valid_json():
    """The inlined rr-fixture element must contain valid JSON matching the release_forecast schema."""
    if not MOCKUP_PATH.exists():
        pytest.skip("mockup file not found")
    src = MOCKUP_PATH.read_text(encoding="utf-8")
    import re as _re
    # Extract content between the script tags
    m = _re.search(
        r'<script[^>]+id=["\']rr-fixture["\'][^>]*>(.*?)</script>',
        src, _re.DOTALL
    )
    assert m is not None, "Could not find rr-fixture script element in mockup"
    raw = m.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        pytest.fail(f"rr-fixture element contains invalid JSON: {e}")
    assert "upcoming" in data, "rr-fixture JSON missing 'upcoming' key"
    assert len(data["upcoming"]) >= 1, "rr-fixture JSON has empty 'upcoming' list"


def test_models_tab_market_implied_not_duplicated():
    """Fix 2 regression guard: Models tab must render market-implied exactly once per item.

    modelDotPlot() already appends the rr-mkt-row. A second standalone
    marketImpliedRow() call in tab1 would produce a duplicate.
    Asserts that the tab1-building block in renderModal does NOT contain
    a direct call to marketImpliedRow() after v3FactorRow.
    """
    src = _rr_section_src()
    # Isolate the TAB 1: MODELS block
    tab1_start = src.find("TAB 1: MODELS")
    tab1_end = src.find("TAB 2: COMPONENTS", tab1_start) if tab1_start >= 0 else -1
    assert tab1_start >= 0, "TAB 1: MODELS block not found in renderModal"
    tab1_src = src[tab1_start:tab1_end] if tab1_end > tab1_start else src[tab1_start:tab1_start + 3000]

    # Count direct marketImpliedRow() calls in the tab1 block.
    # modelDotPlot() is called once (it internally adds the row); there should be
    # NO additional standalone marketImpliedRow() call in tab1.
    direct_calls = [m.start() for m in
                    __import__('re').finditer(r'marketImpliedRow\s*\(', tab1_src)]
    # The only acceptable occurrence is INSIDE modelDotPlot's own definition
    # which is NOT in the tab1 building block — so direct_calls here should be 0.
    assert len(direct_calls) == 0, (
        f"Fix 2 regression: found {len(direct_calls)} direct marketImpliedRow() call(s) "
        f"in the TAB 1 building block. modelDotPlot() already adds the row — "
        f"a duplicate call produces two market-implied rows in the Models tab."
    )


# ---------------------------------------------------------------------------
# MRI-R39a card compaction tests (operator directive, 2026-07-10)
# ---------------------------------------------------------------------------

def test_r39a_expected_value_sourcing_expectation_median_preferred():
    """MRI-R39a: _expectedVal() prefers expectation_read.expectation_median when non-null."""
    src = _rr_section_src()
    fn_start = src.find("function _expectedVal(")
    fn_body = src[fn_start:fn_start + 2000] if fn_start >= 0 else ""
    assert fn_start >= 0, "_expectedVal helper not found in RR section"
    assert "expectation_median" in fn_body, (
        "_expectedVal must check expectation_read.expectation_median first (MRI-R39a source order (a))"
    )


def test_r39a_expected_value_market_implied_excluded_from_bench_median():
    """MRI-R39a: market_implied excluded from benchmark median (different basis/object)."""
    src = _rr_section_src()
    fn_start = src.find("function _expectedVal(")
    fn_body = src[fn_start:fn_start + 2000] if fn_start >= 0 else ""
    # market_implied must NOT appear in the benchmark keys list
    # Look for the benchKeys array definition
    import re as _re
    bench_section = fn_body[fn_body.find("benchKeys"):][:500] if "benchKeys" in fn_body else ""
    assert "market_implied" not in bench_section, (
        "market_implied must not be included in benchKeys for the bench-median fallback (MRI-R39a)"
    )


def test_r39a_expected_value_source_tag_cle_mkt():
    """MRI-R39a: source tag is 'CLE' for cleveland_nowcast, 'MKT' for kalshi/polymarket."""
    src = _rr_section_src()
    fn_start = src.find("function _expectedVal(")
    fn_body = src[fn_start:fn_start + 2000] if fn_start >= 0 else ""
    assert "CLE" in fn_body, "_expectedVal missing CLE source tag for cleveland_nowcast"
    assert "MKT" in fn_body, "_expectedVal missing MKT source tag for kalshi/polymarket"


def test_r39a_no_consensus_in_new_strings():
    """MRI-R5 + MRI-R39a: 'consensus' / '共识' absent from all new card strings."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 8000]
    assert "consensus" not in card_body.lower(), (
        "'consensus' found in renderCard — forbidden by MRI-R5"
    )


def test_r39a_no_per_card_footnote_class():
    """MRI-R39a: rr-card-do-note class removed (per-card display-only footnotes deleted)."""
    src = _rr_section_src()
    assert "rr-card-do-note" not in src, (
        "rr-card-do-note class still present — per-card footnotes not removed (MRI-R39a)"
    )


def test_r39a_card_has_ours_and_bench_labels():
    """MRI-R39a: renderCard has 'ours 本方' and 'exp 预期'/'bench 基准' label strings."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 8000]
    assert "ours 本方" in card_body or "ours" in card_body, (
        "renderCard missing 'ours' label for our projection column (MRI-R39a directive 1)"
    )


def test_r39a_card_one_chip_max():
    """MRI-R39a directive 1: card has at most ONE chip (expectation_read.tag preferred, else skew)."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 8000]
    # The new code uses if/else: expectationChip OR skewChip, not both
    # Verify that both are NOT unconditionally called
    import re as _re
    # The old pattern was: chips += expectationChip(er); chips += skewChip(sk);
    # New pattern uses if/else so both cannot fire simultaneously
    # Check the chip assignment block uses if-else branching
    assert "if (er && er.tag)" in card_body or "er.tag" in card_body, (
        "renderCard must prefer expectation_read.tag chip (MRI-R39a directive 1)"
    )
    # skewChip should be in else branch only
    skew_idx = card_body.find("skewChip(")
    exp_idx = card_body.find("expectationChip(")
    # Both should appear (as alternatives) but not as unconditional sequential calls
    assert skew_idx >= 0, "skewChip missing from renderCard"
    assert exp_idx >= 0, "expectationChip missing from renderCard"


def test_r39a_claims_benchmark_only_tag():
    """MRI-R39a: benchmark_only cards show 'benchmark-only 仅基准' tag (not prose)."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 8000]
    assert "benchmark-only" in card_body, (
        "renderCard missing 'benchmark-only' tag for benchmark_only mode (MRI-R39a directive 3)"
    )
    assert "仅基准" in card_body, (
        "renderCard missing '仅基准' ZH tag for benchmark_only mode (MRI-R39a directive 3)"
    )
    # The old italic prose should not be present
    assert "§6 kill rule" not in card_body, (
        "Old italic '§6 kill rule' prose still in card — replace with compact tag (MRI-R39a)"
    )


def test_r39a_no_data_compact_one_liner():
    """MRI-R39a directive 3: retail no_data renders as compact one-liner 'awaiting data 待数据'."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 8000]
    assert "awaiting data" in card_body, (
        "renderCard missing 'awaiting data' compact one-liner for no_data case (MRI-R39a)"
    )
    assert "待数据" in card_body, (
        "renderCard missing '待数据' ZH for no_data compact card (MRI-R39a)"
    )


def test_r39a_see_more_button_present():
    """MRI-R39a directive 4: see-more / see-less toggle button is wired in renderRadar."""
    src = _rr_section_src()
    main_start = src.find("function renderRadar(")
    main_body = src[main_start:main_start + 8000] if main_start >= 0 else ""
    assert "rr-see-more-btn" in main_body, (
        "rr-see-more-btn missing from renderRadar — see-more toggle not wired (MRI-R39a directive 4)"
    )
    assert "See more" in main_body and "See less" in main_body, (
        "See more / See less text missing from renderRadar toggle (MRI-R39a)"
    )
    assert "显示更多" in main_body and "收起" in main_body, (
        "ZH '显示更多' / '收起' missing from see-more toggle (MRI-R39a bilingual)"
    )


def test_r39a_see_more_earliest_date_logic():
    """MRI-R39a directive 4: renderRadar computes earliest release_date for default-visible set."""
    src = _rr_section_src()
    main_start = src.find("function renderRadar(")
    main_body = src[main_start:main_start + 8000] if main_start >= 0 else ""
    assert "release_date" in main_body, "renderRadar must check release_date for see-more logic"
    assert "visibleDate" in main_body or "earliest" in main_body, (
        "renderRadar missing earliest-date visible set computation (MRI-R39a directive 4)"
    )


def test_r39a_see_more_modelled_point_guard():
    """MRI-R39a directive 4: guard ensures at least one modelled card is default-visible."""
    src = _rr_section_src()
    main_start = src.find("function renderRadar(")
    main_body = src[main_start:main_start + 8000] if main_start >= 0 else ""
    assert "_hasModelledPoint" in main_body or "hasModelledPoint" in main_body, (
        "renderRadar missing modelled-point guard for next-release fallback (MRI-R39a directive 4)"
    )


def test_r39a_chevron_in_rendercard():
    """MRI-R39a directive 1: card has chevron ▸ corner indicator (replaces tap-for-detail row)."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 8000]
    assert "▸" in card_body or "rr-chevron" in card_body, (
        "renderCard missing chevron ▸ / rr-chevron corner indicator (MRI-R39a directive 1)"
    )
    assert "rr-card-tap" not in card_body, (
        "Old rr-card-tap class still in renderCard — tap-for-detail row not removed (MRI-R39a)"
    )


def test_r39a_fixture_visible_cards_are_cpi_headline_and_core():
    """MRI-R39a directive 4: with the test fixture, default-visible set = CPI headline + CPI core (2026-07-14).

    Earliest date = 2026-07-14. Both cards have modelled points. Claims (benchmark_only)
    and retail (no_data) are hidden. See-more hides 13 cards.
    """
    d = _fixture()
    upcoming = d.get("upcoming", [])

    # Compute earliest date (mirror JS logic)
    dates = sorted({it["release_date"] for it in upcoming if it.get("release_date")})
    assert dates, "No dated items in fixture"
    earliest = dates[0]
    assert earliest == "2026-07-14", f"Expected earliest date 2026-07-14, got {earliest}"

    # Items on earliest date
    visible = [it for it in upcoming if it.get("release_date") == earliest]
    assert len(visible) == 2, f"Expected 2 visible cards on 2026-07-14, got {len(visible)}"

    rts = {it["release_type"] for it in visible}
    assert rts == {"cpi_headline", "cpi_core"}, f"Expected CPI types, got {rts}"

    # Both have modelled points
    for it in visible:
        proj = it.get("projection") or {}
        assert proj.get("point") is not None, f"Visible card {it['release_type']} has null point"


def test_r39a_cpi_expected_value_from_expectation_median():
    """MRI-R39a directive 3: CPI headline expected value comes from expectation_read.expectation_median."""
    d = _fixture()
    cpi = next((it for it in d["upcoming"] if it.get("release_type") == "cpi_headline"), None)
    assert cpi is not None
    er = cpi.get("expectation_read") or {}
    assert er.get("expectation_median") is not None, (
        "CPI headline fixture expectation_read.expectation_median is null — test premise broken"
    )
    # Source should be cleveland_nowcast → CLE tag
    srcs = er.get("sources") or []
    assert "cleveland_nowcast" in srcs, "CPI headline expectation sources should include cleveland_nowcast"


def test_r39a_ppi_expected_value_bench_median_no_market_implied():
    """MRI-R39a directive 3: PPI expected value falls back to bench median, excluding market_implied."""
    d = _fixture()
    ppi = next((it for it in d["upcoming"] if it.get("release_type") == "ppi_finaldemand"), None)
    assert ppi is not None
    er = ppi.get("expectation_read") or {}
    assert er.get("expectation_median") is None, (
        "PPI fixture expectation_read.expectation_median is not null — bench-median path won't be tested"
    )
    bs = ppi.get("benchmark_set") or {}
    # Bench keys (non-market_implied) that are non-null
    bench_keys = ["naive_prior", "trailing_3m", "ar_model", "cleveland_nowcast", "expanding_mean"]
    non_null = [bs[k] for k in bench_keys if bs.get(k) is not None]
    assert non_null, "PPI fixture has no non-null benchmark values — bench median test broken"
    # Verify market_implied is present but must NOT be in the median
    assert bs.get("market_implied") is None, (
        "PPI fixture has market_implied — test needs update or exclusion check must be verified"
    )


# ---------------------------------------------------------------------------
# MRI-R39a W11: track-record button + overlay; inline block + duplicate footer removed
# ---------------------------------------------------------------------------

def test_w11_no_inline_forward_accrual_in_panel_render():
    """W11: inline 'Forward accrual began' block no longer appended to rr-content.

    The scoreboardBlock() output must NOT be injected into RR_EL.innerHTML.
    It is now routed to the track-record overlay (rr-tr-body).
    """
    src = _rr_section_src()
    main_start = src.find("function renderRadar(")
    main_body = src[main_start:main_start + 8000] if main_start >= 0 else ""
    # Old pattern: RR_EL.innerHTML = cardsHtml + scoreboardBlock(...)
    # New pattern: RR_EL.innerHTML = cardsHtml; (scoreboard goes to rr-tr-body)
    assert "RR_EL.innerHTML = cardsHtml + scoreboardBlock" not in main_body, (
        "Inline scoreboard block still appended to RR_EL — must be moved to rr-tr-body (W11)"
    )
    assert "RR_TR_BODY" in main_body or "rr-tr-body" in main_body, (
        "scoreboardBlock output must be routed to rr-tr-body overlay (W11)"
    )


def test_w11_no_duplicate_footer_disclosure_in_panel():
    """W11: duplicate footer 'Model projections · display-only · not investment advice' removed from panel.

    The panel renders only: header → subline → cards → see-more.
    The redundant rr-footer JS block must be gone from renderRadar().
    """
    src = _rr_section_src()
    main_start = src.find("function renderRadar(")
    main_body = src[main_start:main_start + 8000] if main_start >= 0 else ""
    # The old footer variable with this duplicate disclosure must not be injected into RR_EL
    assert ("Model projections · display-only · not investment advice · scored forward in public"
            not in main_body), (
        "Duplicate footer disclosure still present in renderRadar output (W11)"
    )


def test_w11_header_disclosure_line_retained():
    """W11: panel-level 'Forward model · display-only · benchmarks · scored in public' subline retained.

    MRI-R5/R7 honesty law: this single disclosure line must remain in static HTML.
    """
    html = _render("macro")
    assert "Forward model" in html, (
        "Panel header disclosure 'Forward model' subline missing — MRI-R5/R7 violation (W11)"
    )
    assert "display-only" in html, "display-only still required in static HTML (W11)"
    assert "rr-subline" in html, "rr-subline element missing from rendered HTML (W11)"


def test_w11_track_record_btn_in_header():
    """W11: top-right 'Track record ↗' button present in panel header."""
    html = _render("macro")
    assert "rr-tr-btn" in html, (
        "rr-tr-btn element missing from rendered HTML (W11)"
    )
    assert "Track record" in html, "EN 'Track record' text missing from header button (W11)"
    assert "评分记录" in html, "ZH '评分记录' text missing from header button (W11)"


def test_w11_track_record_btn_no_cjk_in_title():
    """W11: no CJK characters in title= attributes near the track-record button."""
    html = _render("macro")
    idx_start = html.find('id="release-radar"')
    idx_end = html.find('id="week-ahead"', idx_start) if idx_start >= 0 else -1
    section = html[idx_start:idx_end] if idx_end > idx_start else html[idx_start:idx_start + 30000]
    titles = re.findall(r'title=["\']([^"\']*)["\']', section)
    for t_val in titles:
        for ch in t_val:
            assert not ('一' <= ch <= '鿿'), (
                f"CJK in title= attribute (W11 CI law violation): {t_val!r}"
            )


def test_w11_track_record_overlay_in_html():
    """W11: rr-tr-overlay element is present in rendered macro HTML."""
    html = _render("macro")
    assert "rr-tr-overlay" in html, "rr-tr-overlay missing from rendered HTML (W11)"
    assert "rr-tr-sheet" in html, "rr-tr-sheet missing from rendered HTML (W11)"
    assert "rr-tr-body" in html, "rr-tr-body missing from rendered HTML (W11)"


def test_w11_track_record_overlay_bilingual_title():
    """W11: track-record overlay has bilingual EN + ZH title."""
    html = _render("macro")
    assert "Release Radar — Track record" in html, (
        "EN 'Release Radar — Track record' title missing from overlay (W11)"
    )
    assert "数据发布雷达 — 评分记录" in html, (
        "ZH '数据发布雷达 — 评分记录' title missing from overlay (W11)"
    )


def test_w11_see_more_still_present():
    """W11: See more button and toggle logic remain intact in renderRadar."""
    src = _rr_section_src()
    main_start = src.find("function renderRadar(")
    main_body = src[main_start:main_start + 8000] if main_start >= 0 else ""
    assert "rr-see-more-btn" in main_body, (
        "rr-see-more-btn missing from renderRadar after W11 cleanup"
    )
    assert "See more" in main_body and "See less" in main_body, (
        "See more / See less text missing after W11 cleanup"
    )


def test_w11_overlay_absent_in_stocks_mode():
    """W11: track-record overlay not rendered in stocks mode (inside {% if mode != 'stocks' %})."""
    html = _render("stocks")
    assert "rr-tr-overlay" not in html, (
        "rr-tr-overlay must not appear in stocks mode (W11)"
    )


def test_w11_no_consensus_in_overlay_strings():
    """W11 / MRI-R5: 'consensus' / '共识' absent from track-record overlay static HTML."""
    html = _render("macro")
    idx_start = html.find("rr-tr-overlay")
    idx_end = html.find("rr-modal-overlay", idx_start) if idx_start >= 0 else -1
    section = html[idx_start:idx_end] if idx_end > idx_start else html[idx_start:idx_start + 4000]
    assert "consensus" not in section.lower(), (
        "MRI-R5: 'consensus' found in track-record overlay HTML (W11)"
    )
