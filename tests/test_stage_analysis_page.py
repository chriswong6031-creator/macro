"""Tests for scripts/build_stage_analysis_page.py (SGA Wave 3 page).

Verifies:
1. Full-data render from the demo fixture (no crash, no unrendered braces).
2. Warm-up render when the artifact is absent (page still builds, honest empty
   states — a missing input never crashes a build).
3. House-law / doctrine checks on the rendered HTML: nav present, padding-top,
   no 'validated', <title> plain-EN, bilingual l-en/l-zh parity, no title=
   bilingual leak, no svg-span-breakout, no raw earnings-tag slugs on Tier 1.
4. Signature + product elements present (stage arc, micro-arc glyphs, stances).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "stage_page_demo.json"

sys.path.insert(0, str(REPO))

from scripts.build_stage_analysis_page import render  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _render_with_fixture() -> str:
    return render(REPO, fixture=FIXTURE)


def _render_warmup() -> str:
    """Render with no artifact (warm-up state)."""
    return render(REPO, fixture=Path("/nonexistent/path/stage_page_demo.json"))


# ---------------------------------------------------------------------------
# fixture validity
# ---------------------------------------------------------------------------

def test_fixture_is_valid_json_and_rich():
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert raw.get("schema") == "stage_context.v1"
    assert len(raw.get("top_stage2", [])) >= 25, "fixture must be rich (>=25 fresh names)"


# ---------------------------------------------------------------------------
# full-data render (fixture)
# ---------------------------------------------------------------------------

def test_fixture_renders_without_crash():
    html = _render_with_fixture()
    assert len(html) > 50_000


def test_no_unrendered_jinja_braces():
    """No leftover {{ }} or {% %} in the output (render actually completed)."""
    html = _render_with_fixture()
    assert "{{" not in html
    assert "{%" not in html


def test_stage_arc_signature_present():
    """The signature stage arc SVG + its stage numerals render."""
    html = _render_with_fixture()
    assert 'id="arc-svg"' in html
    assert 'class="arc-seg s2"' in html  # the four season segments


def test_micro_arc_glyph_per_board_row():
    """Every board row carries a micro-arc glyph (arc_pos dot, zero vocabulary)."""
    html = _render_with_fixture()
    rows = html.count('class="brow row"')
    macs = html.count('class="mac"')
    assert rows >= 25
    assert macs >= rows, f"expected a micro-arc per row: {macs} glyphs vs {rows} rows"


def test_stance_vocabulary_only_from_doctrine():
    """Every stance shown is from the doctrine six; the banned old-style states
    (no-stance) never appear.  We assert the doctrine words are present."""
    html = _render_with_fixture()
    assert "Act" in html
    assert "Get ready" in html
    assert "Watch — don" in html  # "Watch — don't chase"
    assert "Protect gains" in html


def test_no_warmup_divs_with_full_fixture():
    html = _render_with_fixture()
    assert html.count('class="warmup"') == 0


def test_no_raw_earnings_tag_slugs_on_tier1():
    """Raw taxonomy slugs (guidance_raised, etc.) must be translated to plain
    words — never leak to the surface (DESIGN_DOCTRINE Law 2)."""
    html = _render_with_fixture()
    for slug in ("guidance_raised", "demand_acceleration", "margin_expansion",
                 "macro_sensitivity", "beat_and_raise"):
        assert slug not in html, f"raw tag slug leaked to Tier 1: {slug}"


# ---------------------------------------------------------------------------
# warm-up render (absent artifact)
# ---------------------------------------------------------------------------

def test_warmup_renders_without_crash():
    html = _render_warmup()
    assert len(html) > 5_000


def test_warmup_shows_honest_empty_states():
    """Warm-up must render honest plain-word empty states, not crash."""
    html = _render_warmup()
    assert 'class="warmup"' in html
    assert "runs tonight" in html.lower() or "warming up" in html.lower()


def test_warmup_still_has_nav_and_footer():
    html = _render_warmup()
    assert "nav-mega" in html  # nav still included
    assert "buy or sell signal" in html.lower()  # footer honesty survives


# ---------------------------------------------------------------------------
# house-law / doctrine checks
# ---------------------------------------------------------------------------

def test_nav_mega_marker_present():
    """Site nav (single-source mega menu) is included."""
    html = _render_with_fixture()
    assert "nav-mega" in html


def test_nav_gap_padding_top_ge_14px():
    html = _render_with_fixture()
    m = re.search(r"padding-top:\s*(\d+)", html)
    assert m, "no padding-top found in rendered HTML"
    assert int(m.group(1)) >= 14, f"padding-top too small: {m.group(0)}"


def test_title_is_plain_english():
    """<title> RCDATA must be plain EN — no t()/td() markup, no CJK
    (title RCDATA plain-EN sweep, #2705/#2724)."""
    html = _render_with_fixture()
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    assert m, "no <title> found"
    title = m.group(1)
    assert "<span" not in title, "markup leaked into <title>"
    assert not re.search(r"[一-鿿]", title), "CJK in <title>"


def test_no_validated_claim():
    html = _render_with_fixture()
    assert "validated" not in html.lower()


def test_no_title_attr_bilingual_leak():
    """title= attributes must not contain <span> markup (CI-guarded)."""
    html = _render_with_fixture()
    assert not re.search(r'title="[^"]*<span', html)


def test_no_svg_text_span_breakout():
    """No <span> inside <svg><text> (svg-span-breakout LETHAL trap)."""
    html = _render_with_fixture()
    assert not re.search(r"<text[^>]*>[^<]*<span", html)


def test_bilingual_parity():
    """Both languages present, and equal span counts (every EN has a ZH twin)."""
    html = _render_with_fixture()
    en = html.count('class="l-en"')
    zh = html.count('class="l-zh"')
    assert en > 100
    assert en == zh, f"bilingual parity broken: {en} l-en vs {zh} l-zh"


def test_l_zh_spans_present():
    html = _render_with_fixture()
    assert 'class="l-zh"' in html


def test_footer_plain_word_null_disclosure():
    """Footer states the context/null in plain words (doctrine Law 5)."""
    html = _render_with_fixture()
    assert "never a buy or sell signal" in html


def test_earnings_no_call_honest_null():
    """Names with no analyzed call show the honest plain-word null."""
    html = _render_with_fixture()
    assert "No call yet" in html or "analysis begins with the next report" in html.lower()


def test_no_css_width_over_100pct():
    """FIX 2 — no rendered `width: N%` exceeds 100%. Guards against the sector
    weather double-×100 unit bug (pct_stage2 is already 0-100)."""
    html = _render_with_fixture()
    widths = re.findall(r"width:\s*(\d+(?:\.\d+)?)%", html)
    assert widths, "expected at least one percentage width in the rendered page"
    over = [w for w in widths if float(w) > 100.0]
    assert not over, f"CSS width exceeds 100%: {over}"
