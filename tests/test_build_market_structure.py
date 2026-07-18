"""Tests for scripts/build_market_structure.py (MSP Wave 2).

Verifies:
1. Warm-up mode (msp=None) renders all 6 warm-up placeholders, no crash.
2. Fixture mode renders full data without warm-up placeholders.
3. House-law checks on rendered HTML (padding-top, no stf-*, no validated, no
   title= bilingual, no svg-span-breakout).
4. Key UI elements present in full-data render.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "market_structure_latest.json"

sys.path.insert(0, str(REPO))

from scripts.build_market_structure import render  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _render_with_fixture() -> str:
    return render(REPO, fixture=FIXTURE)


def _render_warmup() -> str:
    """Render with no artifact (warm-up state)."""
    return render(REPO, fixture=Path("/nonexistent/path/market_structure_latest.json"))


# ---------------------------------------------------------------------------
# warm-up mode
# ---------------------------------------------------------------------------

def test_warmup_renders_without_crash():
    """msp=None path must not raise; returns non-empty HTML."""
    html = _render_warmup()
    assert len(html) > 1000


def test_warmup_shows_six_placeholders():
    """All 6 panels show warm-up divs when artifact is absent."""
    html = _render_warmup()
    count = html.count('class="warmup"')
    assert count == 6, f"expected 6 warmup divs, got {count}"


def test_warmup_no_crash_on_none_gamma():
    """Hero panel does not crash in warm-up mode."""
    html = _render_warmup()
    assert "warming up" in html.lower() or "warming" in html.lower()


# ---------------------------------------------------------------------------
# full-data mode (fixture)
# ---------------------------------------------------------------------------

def test_fixture_renders_without_crash():
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    html = _render_with_fixture()
    assert len(html) > 50_000


def test_no_warmup_divs_with_full_fixture():
    html = _render_with_fixture()
    count = html.count('class="warmup"')
    assert count == 0, f"warmup divs present with full fixture: {count}"


def test_hero_regime_present():
    html = _render_with_fixture()
    assert "absorbing" in html.lower()  # gamma long → "Dealers absorbing moves"


def test_gex_history_chart_present():
    html = _render_with_fixture()
    assert "gex-chart" in html
    assert "spx-flip-chart" in html


def test_systematic_flows_panels_present():
    html = _render_with_fixture()
    assert "sys-chart" in html
    assert "Volatility-control" in html or "波动率控制" in html


def test_dispersion_panel_present():
    html = _render_with_fixture()
    assert "cor-chart" in html


def test_week_map_panel_present():
    """Week map panel shows when fixture has week_map key."""
    html = _render_with_fixture()
    raw = json.loads(FIXTURE.read_text())
    if raw.get("week_map"):
        assert "locked_close" in html or "Locked Friday" in html or "锁定周五" in html
    else:
        assert 'class="warmup"' in html or "week_map" in html


def test_state_changes_strip_present():
    html = _render_with_fixture()
    assert "sc-strip" in html
    assert "sc-chip" in html


def test_chart_data_injected():
    html = _render_with_fixture()
    assert "MSP_GAMMA_HIST" in html
    assert "MSP_SYS_HIST" in html
    assert "MSP_COR_HIST" in html


# ---------------------------------------------------------------------------
# house-law checks
# ---------------------------------------------------------------------------

def test_nav_gap_padding_top_ge_14px():
    """body must have padding-top >= 14px (check_nav_gap.py law)."""
    html = _render_with_fixture()
    m = re.search(r"padding-top:\s*(\d+)", html)
    assert m, "no padding-top found in rendered HTML"
    assert int(m.group(1)) >= 14, f"padding-top too small: {m.group(0)}"


def test_no_stf_class():
    """No .stf-* class names (owned by stocktable.js — forbidden per house law)."""
    html = _render_with_fixture()
    hits = [c for c in re.findall(r'class="[^"]*"', html) if "stf-" in c]
    assert not hits, f"stf- class found: {hits[:3]}"


def test_no_validated_claim():
    """'validated' must not appear in user-facing HTML (CI-guarded)."""
    html = _render_with_fixture()
    assert "validated" not in html.lower()


def test_no_title_bilingual():
    """title= attributes must not contain <span> markup (CI-guarded)."""
    html = _render_with_fixture()
    assert not re.search(r'title="[^"]*<span', html)


def test_no_svg_text_span():
    """No <span> inside <svg><text> elements (svg-span-breakout LETHAL trap)."""
    html = _render_with_fixture()
    assert not re.search(r"<text[^>]*>[^<]*<span", html)


def test_bilingual_structure():
    """Both .l-en and .l-zh spans present (bilingual template)."""
    html = _render_with_fixture()
    assert 'class="l-en"' in html
    assert 'class="l-zh"' in html


def test_range_buttons_present():
    """localStorage-backed range buttons present in panel 2."""
    html = _render_with_fixture()
    assert "msp-gex-range" in html
    assert "rbtn" in html


def test_footer_display_only_disclaimer():
    """display_only disclaimer must appear in footer."""
    html = _render_with_fixture()
    assert "display_only" in html


def test_model_estimate_disclaimer():
    """Model estimate / not audited disclaimer must appear."""
    html = _render_with_fixture()
    assert "model estimate" in html.lower() or "model estimates" in html.lower()
