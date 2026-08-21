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
    assert 'id="arc-wrap"' in html
    assert "drawArc" in html  # the JS signature-arc builder draws the four seasons


def test_stage_board_client_rendered_with_stage_chips():
    """v2 Stage Board renders client-side (rows load from site/stagedata) and uses
    stage chips; the arc is a once-drawn hero signature, not a per-row glyph."""
    html = _render_with_fixture()
    assert 'data-tab="board"' in html
    assert "stagechip" in html


def test_stance_vocabulary_only_from_doctrine():
    """Every stance shown is from the doctrine six; the banned old-style states
    (no-stance) never appear.  We assert the doctrine words are present."""
    html = _render_with_fixture()
    assert "Watch — don" in html  # "Watch — don't chase"
    assert "Protect gains" in html
    assert "Stand aside" in html
    assert "In favour" in html


def test_no_warmup_divs_with_full_fixture():
    html = _render_with_fixture()
    assert html.count('class="warmup"') == 0


def test_earnings_tag_slugs_prettified():
    """Raw taxonomy slugs are mapped to plain words via TAG_META/tagLabel.  A slug
    may appear as a JS map key, but the prettify mechanism must exist so a slug is
    never rendered raw to the user (DESIGN_DOCTRINE Law 2)."""
    html = _render_with_fixture()
    assert "TAG_META" in html
    assert "tagLabel" in html


# ---------------------------------------------------------------------------
# warm-up render (absent artifact)
# ---------------------------------------------------------------------------

def test_warmup_renders_without_crash():
    html = _render_warmup()
    assert len(html) > 5_000


def test_warmup_shows_honest_empty_states():
    """Warm-up must render honest plain-word empty states, not crash."""
    html = _render_warmup()
    assert 'class="empty"' in html
    assert "runs tonight" in html.lower() or "warming up" in html.lower()


def test_warmup_still_has_nav_and_footer():
    html = _render_warmup()
    assert "nav-mega" in html  # nav still included
    assert "never a buy signal" in html.lower()  # footer honesty survives


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


def test_uses_canonical_san_francisco_inter_stack_only():
    """Stage Analysis must not introduce a page-specific webfont.

    Apple platforms use San Francisco via -apple-system; self-hosted Inter is
    the cross-platform fallback used across the main Mastermind experience.
    """
    html = _render_with_fixture()
    assert "Space Grotesk" not in html
    assert "fonts.googleapis.com" not in html
    assert "--font-display:-apple-system,BlinkMacSystemFont,'SF Pro Display',Inter" in html
    assert "font:14px/1.5 var(--font-display)" in html


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
    assert "never a buy signal or a sizing input" in html


def test_earnings_no_call_honest_null():
    """Names with no analyzed call show the honest plain-word null."""
    html = _render_with_fixture()
    assert "No earnings" in html  # honest plain-word empty state for the earnings surface


def test_earnings_reader_links_to_terminal_company_intelligence():
    """The cross-sectional Stage reader hands a selected ticker to the full Terminal dossier."""
    html = _render_with_fixture()
    assert 'id="reader-terminal"' in html
    assert "https://app.mastermind-x.com/analysis?symbol=" in html
    assert "&page=intelligence" in html


def test_no_css_width_over_100pct():
    """FIX 2 — no rendered `width: N%` exceeds 100%. Guards against the sector
    weather double-×100 unit bug (pct_stage2 is already 0-100)."""
    html = _render_with_fixture()
    widths = re.findall(r"width:\s*(\d+(?:\.\d+)?)%", html)
    assert widths, "expected at least one percentage width in the rendered page"
    over = [w for w in widths if float(w) > 100.0]
    assert not over, f"CSS width exceeds 100%: {over}"


# ---------------------------------------------------------------------------
# Wave 8 — market-weather branch reachability
# ---------------------------------------------------------------------------
def _render_weather(tmp_path: Path, weather: str) -> str:
    """Render the hero with a synthetic market.weather value."""
    base = json.loads(FIXTURE.read_text())
    base.setdefault("market", {})["weather"] = weather
    fx = tmp_path / f"weather_{weather}.json"
    fx.write_text(json.dumps(base))
    return render(REPO, fixture=fx)


def test_deteriorating_weather_renders_the_declining_stance(tmp_path):
    """`_weather()` emits 'deteriorating'; the hero must render the STAND-ASIDE
    copy for it.

    Regression pin: the template branched on 'declining', a value the engine
    never emits, so the branch was dead and a deteriorating market fell through
    to the 'mixed' copy — telling the user to "pick spots" while >=40% of names
    sat in Stage 4. The wrong-way assertion is the point: rendering 'mixed' for
    a deteriorating tape is the defect, not a formatting nit.
    """
    html = _render_weather(tmp_path, "deteriorating")
    # "Downtrends dominate" is unique to the hero's declining stance; the bare
    # words "Stand aside" also live in the client-side stage-label map, which
    # renders regardless of weather, so they cannot discriminate the branch.
    assert "Downtrends dominate" in html, (
        "deteriorating weather must render the declining/stand-aside hero")
    assert "No clear season" not in html, (
        "deteriorating weather fell through to the 'mixed' stance copy")


def test_mixed_weather_still_renders_the_mixed_stance(tmp_path):
    html = _render_weather(tmp_path, "mixed")
    assert "No clear season" in html
    assert "Downtrends dominate" not in html


def test_advancing_weather_still_renders_the_advancing_stance(tmp_path):
    html = _render_weather(tmp_path, "advancing")
    assert "Good weather for fresh breakouts" in html
    assert "No clear season" not in html
    assert "Downtrends dominate" not in html


def test_no_target_week_renders_unavailable_not_warming_up(tmp_path):
    """Acceptance gate §2.4: a MATURE-lane failure (no completed Stage week could
    be resolved) must never be described as a first run.

    "Warming up" is honest copy only when there is no artifact at all. Here the
    artifact exists and is well-formed — it just has no current cross-sectional
    authority — so the page must say so. Asserting the ABSENCE of the warm-up
    string is the whole point of the test.
    """
    base = json.loads(FIXTURE.read_text())
    base["target_stage_week"] = None
    base.setdefault("market", {})["weather"] = None
    base["counts"] = {k: None for k in (base.get("counts") or {"total": None})}
    base["population"] = {
        "status": "no_target_week", "target_stage_week": None,
        "target_week_source": "unresolved", "spy_stage_week": None,
        "population_modal_week": None,
        "current": 0, "stale": 0, "unknown": 2741, "total": 2741,
        "current_coverage_pct": None, "data_session": None,
        "week_histogram": [], "issues": ["no_target_week"],
    }
    fx = tmp_path / "no_target_week.json"
    fx.write_text(json.dumps(base))
    html = render(REPO, fixture=fx)

    assert "Stage read unavailable" in html
    # Scoped to the HERO. The bare words "Warming up" also live in the client-side
    # screener-table empty state, which is a DIFFERENT surface and still carries
    # first-run copy for a mature-lane failure — tracked as PR B scope (spec §8),
    # not something this assertion should mask.
    assert "The first stage read runs tonight" not in html, (
        "the hero must not describe a mature-lane failure as a first run")
    assert "The arc fills in once the weekly classification lands" not in html
    # The retired build-date label must not come back on this path either.
    assert "Priced <b>" not in html


def test_warmup_with_no_artifact_still_says_warming_up():
    """The genuine first-run state keeps its warm-up copy — the §2.4 unavailable
    branch must not swallow it."""
    html = _render_warmup()
    assert "The first stage read runs tonight" in html
    assert "Stage read unavailable" not in html
