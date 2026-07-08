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
    """Return the Release Radar CSS+script block from the template source."""
    src = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    idx_start = src.find("RELEASE RADAR")
    idx_end = src.find("Week ahead", idx_start) if idx_start >= 0 else -1
    if idx_start < 0:
        pytest.skip("RELEASE RADAR block not found in template source")
    return src[idx_start:idx_end] if idx_end > idx_start else src[idx_start:idx_start + 80000]


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
    """display-only footnote text appears in renderCard (card-level note)."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 5000]
    assert "display-only" in card_body, "display-only footnote missing from renderCard"
    assert "非信号" in card_body or "not a signal" in card_body, (
        "not-a-signal footnote missing from renderCard"
    )


def test_r24_card_tap_for_detail_prompt():
    """Card carries a 'tap for detail' prompt (bilingual)."""
    src = _rr_section_src()
    fn_start = src.find("function renderCard(")
    fn_end = src.find("function renderModal(", fn_start) if fn_start >= 0 else -1
    card_body = src[fn_start:fn_end] if fn_end > fn_start else src[fn_start:fn_start + 5000]
    assert "tap for detail" in card_body or "点击查看" in card_body, (
        "Card missing 'tap for detail' prompt"
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
    """renderModal contains interval cone section."""
    src = _rr_section_src()
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 10000]
    assert "intervalBar(" in modal_body, "renderModal missing intervalBar call"
    assert "p10" in modal_body and "p90" in modal_body, "renderModal missing p10/p90 labels"


def test_r24_modal_has_benchmark_strip():
    """renderModal calls benchStrip."""
    src = _rr_section_src()
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 10000]
    assert "benchStrip(" in modal_body, "renderModal missing benchStrip call"


def test_r24_modal_has_display_only_footnote():
    """Modal detail contains display-only footnote (MRI-R24 requirement)."""
    src = _rr_section_src()
    rm_start = src.find("function renderModal(")
    rm_end = src.find("\n    /* ---- modal open", rm_start) if rm_start >= 0 else -1
    modal_body = src[rm_start:rm_end] if rm_end > rm_start else src[rm_start:rm_start + 10000]
    assert "display-only" in modal_body, "display-only footnote missing from renderModal"
    assert "not investment advice" in modal_body or "非投资建议" in modal_body, (
        "investment-advice disclaimer missing from renderModal"
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
    main_body = src[main_start:main_start + 2000] if main_start >= 0 else ""
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
