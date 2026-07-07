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
    """Release Radar block must appear before the week-ahead block in the template."""
    src = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    rr_idx = src.find('id="release-radar"')
    wa_idx = src.find('id="week-ahead"')
    assert rr_idx >= 0, "release-radar div not found in template"
    assert wa_idx >= 0, "week-ahead div not found in template"
    assert rr_idx < wa_idx, (
        "release-radar must appear before week-ahead in the template "
        f"(found at {rr_idx} vs {wa_idx})"
    )


def test_release_radar_fetch_path_in_template():
    """Template source contains the fetch path literal."""
    src = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    assert "macrodata/release_forecast.json" in src
