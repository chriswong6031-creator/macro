"""W0.9 — china_stocks page copy smoke tests.

Verifies that the mode=stocks copy in templates/china.html.j2 now describes
the washout->base->fresh-turn archetype (F5 ruling), includes the three mandated
caveats, and complies with the bilingual / t()-in-attributes safety rules.

Mirrors the idiom of tests/test_china_board_track_render.py (the nearest sibling).
"""
import re
from pathlib import Path

from jinja2 import DictLoader, Environment

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "templates" / "china.html.j2").read_text()


def _render_stocks_header() -> str:
    """Render the mode=stocks page header (the first panel in the grid)."""
    marker_start = "<!-- ===================== A-SHARE STOCK DASHBOARD HEADER"
    marker_end = "  {% endif %}\n\n  {% if mode != 'stocks' %}"
    start = SRC.index(marker_start) - len("  {% if mode == 'stocks' %}\n")
    end = SRC.index(marker_end, start) + len("  {% endif %}")
    snippet = SRC[start:end]

    from engine import i18n

    env = Environment(loader=DictLoader({"blk": snippet}), autoescape=False)
    env.globals.update(t=i18n.t, td=i18n.td, tr=i18n.tr, help=lambda *a, **k: "")

    class FakeLatest:
        quad = "Q1"
        quad_name = "Goldilocks"

    class FakePB:
        dial = None

    return env.get_template("blk").render(
        mode="stocks", latest=FakeLatest(), pb=FakePB()
    )


def _render_standout_header() -> str:
    """Render the standout section header up to (but not including) the qvix block."""
    start_marker = '  <div class="panel span12" id="standouts">'
    end_marker = "    {% if setups.qvix_regime %}"
    start = SRC.index(start_marker)
    end = SRC.index(end_marker, start)
    snippet = SRC[start:end]

    # Prepend macro definitions so the snippet is self-contained.
    macros = (
        '{%- macro t(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh if zh else en }}</span>'
        "{%- endmacro -%}\n"
        "{%- macro help(en, zh=\"\") -%}"
        '<span class="help-tip l-en">{{ en }}</span>'
        '<span class="help-tip l-zh">{{ zh }}</span>'
        "{%- endmacro -%}\n"
    )
    full = macros + snippet

    env = Environment(loader=DictLoader({"blk": full}), autoescape=False)

    class FakeSetups:
        buy = [None]  # non-empty so the panel renders

    return env.get_template("blk").render(setups=FakeSetups())


def test_template_parses_without_errors() -> None:
    """Full template must parse (Jinja2 syntax check) — the most important gate."""
    env = Environment(autoescape=False)
    env.parse(SRC)  # raises TemplateSyntaxError on failure


def test_seo_description_names_true_archetype() -> None:
    """SEO meta description must name washout/base/turn, not reversal/low-vol."""
    # Extract the mode=stocks seo_desc assignment
    m = re.search(r"seo_desc = '([^']+)'", SRC)
    assert m, "seo_desc not found in mode=stocks block"
    desc = m.group(1)
    # Must mention the actual archetype
    assert "washout" in desc.lower() or "base" in desc.lower(), (
        f"SEO desc does not name washout/base archetype: {desc!r}"
    )
    # Must NOT lead with 'reversal' or 'low-vol' as the product description
    # (those are separate products per F5 ruling)
    assert "reversal and low-vol reads" not in desc.lower(), (
        f"SEO desc still advertises 'reversal and low-vol reads': {desc!r}"
    )


def test_stocks_header_names_washout_base_turn() -> None:
    """Stocks header subtitle must describe the washout→base→fresh-turn archetype."""
    html = _render_stocks_header()
    assert "washout" in html.lower(), "Header does not mention washout"
    assert "base" in html.lower() or "筑底" in html, "Header does not mention base/筑底"
    # Must NOT claim the archetype is mean-reversion
    assert "mean-reversion setups" not in html, (
        "Header still claims 'mean-reversion setups' (old copy)"
    )


def test_standout_h2_subtitle_is_archetype() -> None:
    """h2 subtitle chip must read 'washout → base → fresh turn', not 'bottoming alignment'."""
    html = _render_standout_header()
    assert "washout" in html.lower(), "h2 subtitle missing washout"
    # Old subtitle: 'cycle-aligned bottoming · weekly + 3-day + daily turning up'
    assert "cycle-aligned bottoming" not in html, (
        "Old 'cycle-aligned bottoming' subtitle still present"
    )
    assert "weekly + 3-day + daily turning up" not in html, (
        "Old weekly-3d-daily alignment copy still present"
    )


def test_standout_help_contains_three_caveats() -> None:
    """The help tooltip must include all three mandated caveats (F5)."""
    html = _render_standout_header()
    # Caveat (i): reversal is a SEPARATE product
    assert "separate product" in html.lower() or "separate" in html.lower(), (
        "Caveat (i) — reversal is a separate product — not found in help tooltip"
    )
    # Caveat (ii): 0-100 score is buy-readiness, not conviction-edge
    assert "buy-readiness" in html.lower() or "买入就绪" in html, (
        "Caveat (ii) — buy-readiness / conviction-edge — not found"
    )
    # Caveat (iii): forward grades are accruing
    assert "accruing" in html.lower() or "累积" in html, (
        "Caveat (iii) — forward grades accruing — not found"
    )


def test_standout_help_describes_cascade() -> None:
    """Help tooltip must mention the T1-T4 cascade (the actual admission gate)."""
    html = _render_standout_header()
    assert "T1" in html and "T4" in html, (
        "Help tooltip does not mention T1–T4 cascade"
    )


def test_standout_help_says_rank_not_bottoming_alignment() -> None:
    """Help must NOT describe the board as a bottoming-alignment screen."""
    html = _render_standout_header()
    assert "MULTI-TIMEFRAME BOTTOMING-ALIGNMENT" not in html, (
        "Old 'MULTI-TIMEFRAME BOTTOMING-ALIGNMENT screen' copy still present"
    )
    assert "Ranked by alignment quality" not in html, (
        "Old 'Ranked by alignment quality' copy still present"
    )


def test_standfirst_paragraph_honest() -> None:
    """Standfirst must describe cascade tier + washout/COILED as the rank driver."""
    html = _render_standout_header()
    # Must mention cascade tier
    assert "cascade tier" in html.lower() or "级联层级" in html, (
        "Standfirst does not name cascade tier as rank driver"
    )
    # Must not claim ranked by 'alignment quality'
    assert "Ranked by alignment quality" not in html, (
        "Old alignment-quality ranking claim still present in standfirst"
    )


def test_bilingual_dual_spans_present() -> None:
    """Rendered output must contain both l-en and l-zh spans (bilingual compliance)."""
    html = _render_stocks_header() + _render_standout_header()
    assert 'class="l-en"' in html or "l-en" in html, "No l-en spans found"
    assert 'class="l-zh"' in html or "l-zh" in html, "No l-zh spans found"
    assert "洗盘" in html or "筑底" in html, "No ZH copy found for washout/base"


def test_no_t_call_inside_attributes_in_changed_blocks() -> None:
    """The i18n gotcha: t() must never appear inside an HTML attribute value.

    Checks the two changed regions: stocks-header block and standout h2/standfirst.
    """
    # Extract stocks-header block
    start = SRC.index("<!-- ===================== A-SHARE STOCK DASHBOARD HEADER")
    end = SRC.index("  {% if mode != 'stocks' %}", start)
    header_block = SRC[start:end]

    # Extract standout header up to qvix
    ss = SRC.index('  <div class="panel span12" id="standouts">')
    se = SRC.index("    {% if setups.qvix_regime %}", ss)
    standout_block = SRC[ss:se]

    for name, block in [("header", header_block), ("standout", standout_block)]:
        bad = re.search(
            r'(?:title|style|data-[a-z]+|aria-[a-z]+|class)="[^"]*\{\{\s*t\(', block
        )
        assert not bad, (
            f"t() found inside an HTML attribute in the {name} block: {bad.group()!r}"
        )


def test_no_straight_reversal_claims_in_standout_header() -> None:
    """The standout section must not claim 'reversal' is the ranking mechanism."""
    html = _render_standout_header()
    # The old standfirst mentioned 'A-share reversal / relative-strength leg only as a tiebreaker'
    assert "reversal / relative-strength leg only as a tiebreaker" not in html, (
        "Old reversal-tiebreaker copy still present"
    )
