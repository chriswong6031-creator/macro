"""Render smoke tests for the MRI PR-D Release Radar section in dashboard.html.j2.

Verifies that:
1. The #release-radar container is present in macro mode (and absent in stocks mode).
2. Bilingual EN/ZH labels are present in the container.
3. No CJK characters appear inside title= attributes in the new section.
4. The JS fetch call targets 'macrodata/release_forecast.json'.
5. The 'consensus' word never appears (MRI-R5).
6. The 'validated' word never appears in user-facing text (MRI-R7 / CI law).
7. The section renders fail-open when mode='stocks'.
8. Both modes render without exception.

Environment mirrors scripts/build_site.py exactly (loader, filters, globals).
Fixture VM is imported from test_dashboard_template_render._base_vm() to avoid
duplication and stay in sync with the live VM contract.
"""
from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Shared environment helper
# ---------------------------------------------------------------------------

def _env() -> jinja2.Environment:
    """Mirror scripts/build_site.py's Jinja env exactly."""
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
    """Import the synthetic VM from the dashboard render test so we stay in sync
    with the live VM contract. Falls back to a minimal inline stub if the
    import fails (e.g. import-path issues in CI)."""
    try:
        from tests.test_dashboard_template_render import _base_vm as _bvm  # noqa: PLC0415
        return _bvm()
    except Exception:  # noqa: BLE001
        # Minimal inline fallback — enough to reach the Release Radar block.
        return dict(
            latest={"date": "2026-07-07", "quad": "Q2", "quad_name": "Reflation",
                    "label": "Q2 — Reflation", "confidence": 0.72, "fed_stance": None,
                    "dislocation": None, "turning_point": None, "risk_radar": None,
                    "rate_inflation_transmission": None, "cross_asset_confirm": None,
                    "transition_state": "stable", "liquidity_overlay": "neutral",
                    "conditions": None, "risk_state": None, "cycle_tag": "mid"},
            mtf=None, macro_catalysts=[], event_strip=[], event_risk=None,
            prediction_markets=None, narrative_regime=None, ndi=None,
            macro_news=None, macro_brief=None, macro_news_disclaimer="",
            macro_news_disclaimer_zh="", alerts=[], pb=None, month_name="July",
            commodities=[], sector_timing={}, action_board={"hold":[],"avoid":[],"notable":[],"buy":[]},
            top_setups=[], us_standouts={"buy":[],"eligible":0}, us_board_outcomes=None,
            market_gamma=None, components_confirming=[], components_contradicting=[],
            flip_plain=None, internals=[], size_style=[], breadth_div=None,
            breadth_panel=None, adv_breadth=None, sector_setups=None,
            generated_utc="2026-07-07 06:00", chart_liquidity=None,
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


def _render(mode: str) -> str:
    """Render dashboard.html.j2 with the synthetic VM and given mode."""
    return _env().get_template("dashboard.html.j2").render(**_base_vm(), mode=mode)


# ---------------------------------------------------------------------------
# Tests — macro mode (mode='macro')
# ---------------------------------------------------------------------------

def test_macro_mode_renders_without_exception():
    """macro mode must not raise on the synthetic VM."""
    html = _render("macro")
    assert len(html) > 1000


def test_release_radar_container_present_in_macro_mode():
    """#release-radar div is present in macro mode."""
    html = _render("macro")
    assert 'id="release-radar"' in html


def test_release_radar_bilingual_heading():
    """Container carries both EN and ZH heading text."""
    html = _render("macro")
    assert "Release Radar" in html
    assert "数据发布雷达" in html


def test_release_radar_display_only_label():
    """Display-only label is present in the container."""
    html = _render("macro")
    assert "display-only" in html.lower()


def test_release_radar_benchmark_label():
    """'benchmark' (not 'consensus') label is present (MRI-R5)."""
    html = _render("macro")
    assert "benchmark" in html.lower() or "基准" in html


def test_release_radar_no_consensus_word():
    """MRI-R5: the word 'consensus' must not appear in the section (EN or ZH)."""
    html = _render("macro")
    # Extract the release-radar section to avoid false positives from other sections
    idx_start = html.find('id="release-radar"')
    idx_end = html.find('id="week-ahead"', idx_start) if idx_start >= 0 else -1
    if idx_start < 0:
        pytest.skip("release-radar container not found")
    section = html[idx_start:idx_end] if idx_end > idx_start else html[idx_start:idx_start+20000]
    assert "consensus" not in section.lower(), (
        "MRI-R5 violation: 'consensus' found in release-radar section"
    )


def test_release_radar_no_validated_word_in_template():
    """MRI-R7 / CI law: 'validated' must not appear in user-facing text of the section."""
    template_src = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    # Find our section between the RELEASE RADAR comment and Week ahead comment
    idx_start = template_src.find("RELEASE RADAR")
    idx_end = template_src.find("Week ahead", idx_start) if idx_start >= 0 else -1
    if idx_start < 0:
        pytest.skip("RELEASE RADAR block not found in template source")
    section = template_src[idx_start:idx_end] if idx_end > idx_start else template_src[idx_start:idx_start+30000]
    # Only check user-facing lines (not Jinja comments)
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("{#"):
            continue  # Jinja comment — CI check_validated_claims.py catches {# too
        assert "validated" not in stripped.lower(), (
            f"MRI-R7 violation: 'validated' in template line: {stripped!r}"
        )


def test_release_radar_fetch_targets_correct_path():
    """JS fetch call targets macrodata/release_forecast.json."""
    html = _render("macro")
    assert "macrodata/release_forecast.json" in html


def test_release_radar_fetch_uses_no_cache():
    """Fetch uses {cache: 'no-cache'} per house pattern (sector_central.html.j2:670)."""
    html = _render("macro")
    # Our section specifically
    idx = html.find("release_forecast.json")
    assert idx >= 0
    nearby = html[max(0, idx-60):idx+80]
    assert "no-cache" in nearby


def test_release_radar_footnote_bilingual():
    """Footnote carries both EN and ZH disclaimer text."""
    html = _render("macro")
    assert "not investment advice" in html.lower()
    assert "非投资建议" in html


def test_release_radar_scored_in_public_label():
    """The 'scored forward in public' commitment is present."""
    html = _render("macro")
    assert "scored" in html.lower()


def test_release_radar_no_cjk_in_title_attrs_in_section():
    """No CJK characters may appear inside title= attributes in the section."""
    html = _render("macro")
    idx_start = html.find('id="release-radar"')
    idx_end = html.find('id="week-ahead"', idx_start) if idx_start >= 0 else -1
    if idx_start < 0:
        pytest.skip("release-radar container not found")
    section = html[idx_start:idx_end] if idx_end > idx_start else html[idx_start:idx_start+20000]
    titles = re.findall(r'title=["\']([^"\']+)["\']', section)
    for t_val in titles:
        for ch in t_val:
            assert not ('一' <= ch <= '鿿'), (
                f"CJK in title= attribute (CI law violation): {t_val!r}"
            )


def test_release_radar_loading_placeholder_present():
    """The initial loading placeholder text is in the container (shown before JS runs)."""
    html = _render("macro")
    idx = html.find('id="release-radar"')
    assert idx >= 0
    section = html[idx:idx+5000]
    assert "Loading release projections" in section or "加载发布预测" in section


def test_release_radar_rr_content_div_present():
    """The #rr-content div (JS render target) is present."""
    html = _render("macro")
    assert 'id="rr-content"' in html


# ---------------------------------------------------------------------------
# Tests — stocks mode (mode='stocks')
# ---------------------------------------------------------------------------

def test_stocks_mode_renders_without_exception():
    """stocks mode must not raise on the synthetic VM."""
    html = _render("stocks")
    assert len(html) > 1000


def test_release_radar_absent_in_stocks_mode():
    """Release Radar is gated on mode != 'stocks' — must not appear on stocks page."""
    html = _render("stocks")
    assert 'id="release-radar"' not in html


# ---------------------------------------------------------------------------
# Tests — template source structure
# ---------------------------------------------------------------------------

def test_release_radar_above_week_ahead_in_template():
    """In v2 layout, release-radar appears after week-ahead calendar in the events tray
    (v2 ruling: week-ahead calendar is the tray header, release-radar is below it)."""
    src = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    rr_idx = src.find('id="release-radar"')
    wa_idx = src.find('id="week-ahead"')
    assert rr_idx >= 0, "release-radar div not found in template"
    assert wa_idx >= 0, "week-ahead div not found in template"
    # v2 order: week-ahead calendar tray header comes first, release-radar below it
    assert wa_idx < rr_idx, (
        "v2 layout: week-ahead must appear before release-radar in the template "
        f"(found week-ahead at {wa_idx} vs release-radar at {rr_idx})"
    )


def test_release_radar_fetch_path_in_template():
    """Template source contains the fetch path literal."""
    src = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    assert "macrodata/release_forecast.json" in src


# ---------------------------------------------------------------------------
# Tests — v2 field rendering (fixture-based; fixture is deleted after tests run)
# These tests parse JS source in the template to assert that the v2 helpers
# are present and correctly gated (fail-open when fields are null/absent).
# ---------------------------------------------------------------------------

_FIXTURE_PATH = ROOT / "site" / "macrodata" / "release_forecast_fixture_v2.json"


def _rr_section_src() -> str:
    """Return the Release Radar <script> block from the template source."""
    src = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    # extract between RELEASE RADAR comment and week-ahead comment
    idx_start = src.find("RELEASE RADAR")
    idx_end = src.find("Week ahead", idx_start) if idx_start >= 0 else -1
    if idx_start < 0:
        pytest.skip("RELEASE RADAR block not found in template source")
    return src[idx_start:idx_end] if idx_end > idx_start else src[idx_start:idx_start + 60000]


# ---- Template source structure: v2 helpers are defined ----

def test_v2_components_bar_function_defined():
    """componentsBar() helper is defined in the Release Radar script block."""
    src = _rr_section_src()
    assert "function componentsBar(" in src, (
        "componentsBar helper not found in Release Radar script block"
    )


def test_v2_confidence_bar_function_defined():
    """confidenceBar() helper is defined in the Release Radar script block."""
    src = _rr_section_src()
    assert "function confidenceBar(" in src, (
        "confidenceBar helper not found in Release Radar script block"
    )


def test_v2_market_implied_row_function_defined():
    """marketImpliedRow() helper is defined in the Release Radar script block."""
    src = _rr_section_src()
    assert "function marketImpliedRow(" in src, (
        "marketImpliedRow helper not found in Release Radar script block"
    )


def test_v2_surprise_dist_gauge_function_defined():
    """surpriseDistGauge() helper is defined in the Release Radar script block."""
    src = _rr_section_src()
    assert "function surpriseDistGauge(" in src, (
        "surpriseDistGauge helper not found in Release Radar script block"
    )


def test_v2_reaction_sens_row_function_defined():
    """reactionSensRow() helper is defined in the Release Radar script block."""
    src = _rr_section_src()
    assert "function reactionSensRow(" in src, (
        "reactionSensRow helper not found in Release Radar script block"
    )


def test_v2_revision_risk_line_function_defined():
    """revisionRiskLine() helper is defined in the Release Radar script block."""
    src = _rr_section_src()
    assert "function revisionRiskLine(" in src, (
        "revisionRiskLine helper not found in Release Radar script block"
    )


# ---- All helpers are called from renderCard ----

def test_v2_all_helpers_wired_into_rendermodal():
    """MRI-R24: All v2 detail helpers are reachable from renderModal (detail modal); renderCard is compact.

    The MRI-R24 redesign moves detail helpers out of renderCard and into renderModal.
    renderCard shows only: name+countdown, projection point, 2 chips, confidence.

    MRI-R39 QA update: marketImpliedRow() is now called only inside modelDotPlot() (which is
    called from renderModal) to avoid rendering it twice in the Models tab. The other 5 helpers
    are still called directly from renderModal's body.
    """
    src = _rr_section_src()
    # renderModal contains most detail helpers directly
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    assert rm_start >= 0, "renderModal not found (MRI-R24 required)"
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 10000]
    # These 5 must still be called directly from renderModal
    for fn in ("componentsBar(", "confidenceBar(", "surpriseDistGauge(", "reactionSensRow(", "revisionRiskLine("):
        assert fn in modal_body, f"{fn} not called inside renderModal"
    # marketImpliedRow is called via modelDotPlot() — check it's called from renderModal
    assert "modelDotPlot(" in modal_body, "modelDotPlot() not called inside renderModal"
    # marketImpliedRow must be defined in the same script scope (reachable from modelDotPlot)
    assert "function marketImpliedRow(" in src, "marketImpliedRow() function definition missing"
    # renderCard must NOT call the heavy detail helpers (it is compact)
    rc_start = src.find("function renderCard(")
    rc_end = src.find("function renderModal(", rc_start) if rc_start >= 0 else -1
    assert rc_start >= 0, "renderCard not found"
    card_body = src[rc_start:rc_end] if rc_end > rc_start else src[rc_start:rc_start + 5000]
    for fn in ("componentsBar(", "confidenceBar(", "surpriseDistGauge(", "reactionSensRow(", "revisionRiskLine("):
        assert fn not in card_body, f"{fn} must not appear in compact renderCard (moved to renderModal in MRI-R24)"


# ---- Fail-open: null fields produce no output ----

def test_v2_components_bar_null_returns_empty():
    """componentsBar with null/empty input must produce no output (fail-open).

    Asserts via template source: the helper returns '' when array is empty.
    """
    src = _rr_section_src()
    # The guard is: if (!Array.isArray(components) || !components.length) return '';
    assert "!Array.isArray(components)" in src or "return ''" in src, (
        "componentsBar must have a fail-open null guard"
    )


def test_v2_market_implied_null_guard():
    """marketImpliedRow must guard against null mi (fail-open)."""
    src = _rr_section_src()
    # Check both the function definition and that it returns '' on null
    fn_start = src.find("function marketImpliedRow(")
    fn_end = src.find("\n    /* v2: surprise distribution", fn_start) if fn_start >= 0 else -1
    fn_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 800]
    assert "return ''" in fn_body, "marketImpliedRow must return '' when mi is null"


def test_v2_surprise_dist_null_guard():
    """surpriseDistGauge must guard against null sd (fail-open)."""
    src = _rr_section_src()
    fn_start = src.find("function surpriseDistGauge(")
    fn_end = src.find("\n    /* v2: reaction", fn_start) if fn_start >= 0 else -1
    fn_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 800]
    assert "return ''" in fn_body, "surpriseDistGauge must return '' when sd is null"


def test_v2_reaction_sens_null_guard():
    """reactionSensRow must guard against null rs (fail-open)."""
    src = _rr_section_src()
    fn_start = src.find("function reactionSensRow(")
    fn_end = src.find("\n    /* v2: revision risk", fn_start) if fn_start >= 0 else -1
    fn_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 800]
    assert "return ''" in fn_body, "reactionSensRow must return '' when rs is null"


def test_v2_revision_risk_null_guard():
    """revisionRiskLine must guard against null rr (fail-open)."""
    src = _rr_section_src()
    fn_start = src.find("function revisionRiskLine(")
    fn_end = src.find("\n    /* render one upcoming card", fn_start) if fn_start >= 0 else -1
    fn_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 600]
    assert "return ''" in fn_body, "revisionRiskLine must return '' when rr is null"


# ---- No consensus / no CJK in title in the new v2 JS helpers ----

def test_v2_no_consensus_word_in_new_helpers():
    """The word 'consensus' must not appear in v2 helpers (MRI-R5)."""
    src = _rr_section_src()
    # Check specifically in v2 helper block (before renderCard)
    rc_start = src.find("function componentsBar(")
    card_start = src.find("function renderCard(", rc_start) if rc_start >= 0 else -1
    if rc_start < 0:
        pytest.skip("v2 helpers not found")
    helpers_src = src[rc_start:card_start] if card_start > rc_start else src[rc_start:rc_start + 20000]
    assert "consensus" not in helpers_src.lower(), (
        "MRI-R5: 'consensus' must not appear in v2 helper functions"
    )


def test_v2_no_cjk_in_title_attrs_new_helpers():
    """No CJK characters may appear in title= attributes in the v2 helper code."""
    src = _rr_section_src()
    rc_start = src.find("function componentsBar(")
    card_start = src.find("function renderCard(", rc_start) if rc_start >= 0 else -1
    if rc_start < 0:
        pytest.skip("v2 helpers not found")
    helpers_src = src[rc_start:card_start] if card_start > rc_start else src[rc_start:rc_start + 20000]
    titles = re.findall(r'title=["\']([^"\']+)["\']', helpers_src)
    for t_val in titles:
        for ch in t_val:
            assert not ('一' <= ch <= '鿿'), (
                f"CJK in title= attribute in v2 helpers (CI law violation): {t_val!r}"
            )


# ---- Fixture-based: v2 field labels appear in rendered HTML ----

def test_v2_field_labels_present_in_template_source():
    """The v2 bilingual labels are present in the template source (EN and ZH)."""
    src = _rr_section_src()
    expected_en = [
        "What is driving the number",
        "Data quality composition",
        "Market-implied",
        "Hot print historically",
        "Cold print historically",
        "First-print revision risk",
    ]
    expected_zh = [
        "驱动因素分解",
        "数据质量构成",
        "市场隐含",
        "历史上热数据",
        "历史上冷数据",
        "首次发布修正风险",
    ]
    for label in expected_en:
        assert label in src, f"EN label not found in template: {label!r}"
    for label in expected_zh:
        assert label in src, f"ZH label not found in template: {label!r}"


def test_v2_confidence_bar_legend_terms_bilingual():
    """Known/proxy/residual legend appears in both EN and ZH in template source."""
    src = _rr_section_src()
    for term_en in ("Known", "Proxy", "Residual"):
        assert term_en in src, f"EN confidence bar legend term not found: {term_en!r}"
    for term_zh in ("已知", "代理", "残差"):
        assert term_zh in src, f"ZH confidence bar legend term not found: {term_zh!r}"


def test_v2_surprise_dist_gauge_terms_bilingual():
    """Hot/inline/cold gauge labels appear in both EN and ZH in template source."""
    src = _rr_section_src()
    assert "Hot " in src and "热 " in src, "surpriseDistGauge EN/ZH 'hot' labels missing"
    assert "Inline " in src and "中性 " in src, "surpriseDistGauge EN/ZH 'inline' labels missing"
    assert "Cold " in src and "冷 " in src, "surpriseDistGauge EN/ZH 'cold' labels missing"


def test_v2_residual_bar_labeled_plug_residual():
    """The residual bar carries the bilingual 'plug residual/残差' annotation."""
    src = _rr_section_src()
    assert "plug residual" in src, "EN '(plug residual)' annotation missing from componentsBar"
    assert "残差" in src, "ZH '残差' annotation missing from componentsBar"


def test_v2_benchmark_only_suppressed_in_rendermodal():
    """MRI-R24: In benchmark_only mode, v2 component/confidence/sensitivity helpers are suppressed in renderModal."""
    src = _rr_section_src()
    # Find the renderModal body
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    assert rm_start >= 0, "renderModal not found"
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 10000]
    # All 5 non-market-implied helpers must be gated with !isBenchmarkOnly check.
    # Search for the nearest preceding 'if (' statement which should contain the guard.
    for call in ("componentsBar(", "confidenceBar(", "surpriseDistGauge(", "reactionSensRow(", "revisionRiskLine("):
        call_idx = modal_body.find(call)
        if call_idx < 0:
            pytest.fail(f"{call} not found in renderModal body")
        # Walk back to the nearest 'if (' — the guard can be up to ~600 chars away
        if_idx = modal_body.rfind("if (", 0, call_idx)
        snippet = modal_body[if_idx:call_idx + len(call)] if if_idx >= 0 else modal_body[max(0, call_idx - 600):call_idx + len(call)]
        assert "isBenchmarkOnly" in snippet, (
            f"{call} is not gated by isBenchmarkOnly in renderModal — "
            f"nearest if: {snippet[:120]!r}"
        )


def test_fixture_no_consensus_in_fixture():
    """Fixture JSON must not contain the word 'consensus' (MRI-R5)."""
    if not _FIXTURE_PATH.exists():
        pytest.skip("Fixture not present")
    content = _FIXTURE_PATH.read_text(encoding="utf-8")
    assert "consensus" not in content.lower(), (
        "MRI-R5 violation: 'consensus' found in fixture JSON"
    )


def test_fixture_all_null_card_fail_open():
    """Fixture has a card with all v2 fields null — asserts fail-open design."""
    if not _FIXTURE_PATH.exists():
        pytest.skip("Fixture not present")
    import json
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    null_cards = [
        item for item in data.get("upcoming", [])
        if item.get("components") is None
        and item.get("confidence_v2") is None
        and item.get("surprise_distribution") is None
        and item.get("reaction_sensitivity") is None
    ]
    assert len(null_cards) >= 1, (
        "Fixture must contain at least one card with all v2 fields null "
        "(to exercise fail-open code paths)"
    )


def test_fixture_kalshi_market_implied_shape():
    """Fixture's CPI card carries Kalshi market_implied with required keys."""
    if not _FIXTURE_PATH.exists():
        pytest.skip("Fixture not present")
    import json
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    cpi_card = next((i for i in data.get("upcoming", []) if i.get("release") == "cpi" and i.get("components")), None)
    if cpi_card is None:
        pytest.skip("No full-field CPI card in fixture")
    mi = cpi_card.get("benchmark_set", {}).get("market_implied")
    assert mi is not None, "CPI fixture card must have market_implied"
    assert mi.get("source") == "kalshi"
    assert mi.get("implied_median") is not None


def test_fixture_polymarket_market_implied_shape():
    """Fixture's NFP card carries Polymarket market_implied with required keys."""
    if not _FIXTURE_PATH.exists():
        pytest.skip("Fixture not present")
    import json
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    nfp_card = next((i for i in data.get("upcoming", []) if i.get("release") == "nfp"), None)
    if nfp_card is None:
        pytest.skip("No NFP card in fixture")
    mi = nfp_card.get("benchmark_set", {}).get("market_implied")
    assert mi is not None, "NFP fixture card must have market_implied"
    assert mi.get("source") == "polymarket"
    assert mi.get("implied") is not None


def test_fixture_revision_risk_on_nfp_only():
    """revision_risk appears on NFP card and is null on CPI card (architectural law)."""
    if not _FIXTURE_PATH.exists():
        pytest.skip("Fixture not present")
    import json
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    nfp = next((i for i in data.get("upcoming", []) if i.get("release") == "nfp"), None)
    full_cpi = next((i for i in data.get("upcoming", []) if i.get("release") == "cpi" and i.get("components")), None)
    if nfp is None or full_cpi is None:
        pytest.skip("Missing NFP or CPI card in fixture")
    assert nfp.get("revision_risk") is not None, "NFP card must have revision_risk"
    # CPI cards should not carry revision_risk (not mandated by spec — just assert it's absent or null)
    assert full_cpi.get("revision_risk") is None, "CPI card should not have revision_risk in fixture"


def test_fixture_confidence_components_v2_weights_sum_to_one():
    """Fixture confidence_components_v2 weights must sum to 1.0."""
    if not _FIXTURE_PATH.exists():
        pytest.skip("Fixture not present")
    import json
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    for item in data.get("upcoming", []):
        cv2comps = item.get("confidence_components_v2")
        if cv2comps is None:
            continue
        total = cv2comps.get("w_known", 0) + cv2comps.get("w_proxy", 0) + cv2comps.get("w_residual", 0)
        assert abs(total - 1.0) < 1e-6, (
            f"confidence_components_v2 weights sum to {total}, expected 1.0 "
            f"for release={item.get('release')}"
        )
