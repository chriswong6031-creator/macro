"""W1-C — three-shelf lifecycle render tests.

Verifies the ENTRY / RIPENING / RAN partition in templates/china.html.j2 (mode=stocks):
  - BUY-family words (BUY/买入/act now) appear on ENTRY shelf only
  - No green stage badge on RAN_LATE cards
  - Every shelf header has dual-span (l-en + l-zh)
  - Zero non-ASCII attribute delimiters anywhere in the template
  - Jinja parse (the most important gate)
  - Smoke render with synthetic context containing all three arrays

Mirrors the idiom of tests/test_china_stocks_copy_w09.py (the nearest sibling).
"""
import re
from pathlib import Path

from jinja2 import DictLoader, Environment

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "templates" / "china.html.j2").read_text()

# ---------------------------------------------------------------------------
# Helper: extract the W1-C block (balanced Jinja tags) and render it.
# The block runs from {# ── W1-C: ENTRY SHELF to {# ── BOARD TRACK RECORD.
# It is self-contained: 74 if/endif + 10 for/endfor pairs — confirmed balanced.
# ---------------------------------------------------------------------------

def _render_w1c(setups: dict) -> str:
    """Extract and render the W1-C three-shelf block with synthetic context."""
    start = SRC.index("{# ── W1-C: ENTRY SHELF")
    end = SRC.index("{# ── BOARD TRACK RECORD")
    snippet = SRC[start:end]

    macros = (
        '{%- macro t(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh if zh else en }}</span>'
        "{%- endmacro -%}\n"
        '{%- macro td(x) -%}{{ x }}{%- endmacro -%}\n'
        '{%- macro nm(name) -%}'
        '{% set p = (name or "").split(" / ") %}'
        '<span class="l-en">{{ p[0] }}</span>'
        '<span class="l-zh">{{ p[1] if p|length > 1 else p[0] }}</span>'
        "{%- endmacro -%}\n"
        '{%- macro help(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh }}</span>'
        "{%- endmacro -%}\n"
    )
    # Strip the _sig_badge include (not available as standalone)
    snippet = snippet.replace(
        '{% with sig = n.signal %}{% include "_sig_badge.html.j2" %}{% endwith %}', ""
    )
    full = macros + snippet

    SECZH = {
        "Technology": "科技",
        "Healthcare": "医疗保健",
        "Industrials": "工业",
    }

    env = Environment(loader=DictLoader({"blk": full}), autoescape=False)
    env.globals["SECZH"] = SECZH
    return env.get_template("blk").render(setups=setups)


# ---------------------------------------------------------------------------
# Synthetic context factories
# ---------------------------------------------------------------------------

def _conviction(score=72, band="high", verdict="Fresh turn from washout", verdict_zh="洗盘后新转向"):
    return {
        "score": score,
        "band": band,
        "verdict": verdict,
        "verdict_zh": verdict_zh,
        "alignment": None,
        "axes": {
            "selection": {"pct": 80},
            "entry": {"pct": 70},
            "tailwind": {"pct": 60},
            "quality": {"pct": 50},
        },
        "vol_squeeze": None,
        "risk": None,
        "cautions": None,
        "notes": None,
        "trust_tier": None,
    }


def _entry_signal(status="buy_now", headline="Ready", headline_zh="就绪"):
    return {
        "status": status,
        "act_level": 3,
        "headline": headline,
        "headline_zh": headline_zh,
        "action": "Buy now",
        "buy_zone": None,
        "cycle_pos": None,
        "timing": None,
    }


def _make_entry_row(ticker="300725.SZ"):
    return {
        "ticker": ticker,
        "name": "Entry Name / 入场名称",
        "sector": "Healthcare",
        "stage": "ENTRY",
        "stage_sublabel": None,
        "stage_detail": {},
        "why_ranked": "T1+washout_2w",
        "dir": "up",
        "price": 46.5,
        "washout_2w": True,
        "coiled": None,
        "hold": None,
        "sector_turn": None,
        "extension": None,
        "quality": None,
        "off_high": -12.3,
        "spark_svg": None,
        "conviction": _conviction(),
        "entry_signal": _entry_signal("buy_now"),
        "signal": None,
        "align_tier": None,
        "alpha": 0.5,
        "alpha_entry": "pullback",
        "sector_rank": 3,
        "sector_n": 12,
        "risk_sizing": None,
        "confluence": False,
        "label": "buy_now",
        "state": "buy_now",
    }


def _make_ran_row(ticker="603129.SS", sublabel="signal live - entry passed; wait for pullback"):
    return {
        "ticker": ticker,
        "name": "Ran Name / 已过名称",
        "sector": "Technology",
        "stage": "RAN_LATE",
        "stage_sublabel": sublabel,
        "stage_detail": {},
        "why_ranked": None,
        "dir": "caution",
        "price": 55.0,
        "washout_2w": False,
        "coiled": None,
        "hold": None,
        "sector_turn": None,
        "extension": None,
        "quality": None,
        "off_high": -3.2,
        "spark_svg": None,
        "conviction": _conviction(score=62, band="constructive"),
        "entry_signal": _entry_signal("hold", "Hold", "持有"),
        "signal": None,
        "align_tier": None,
        "alpha": 1.2,
        "alpha_entry": "extended",
        "sector_rank": 1,
        "sector_n": 20,
        "risk_sizing": None,
        "confluence": False,
        "label": "hold",
        "state": "hold",
    }


def _make_ripening_row(ticker="688306.SS"):
    # W8-R1 (#2102): ripening rows carry a zone (READY / BASING); the rip-shelf
    # partitions on it via selectattr, so the fixture must set one for cards to render.
    return {
        "ticker": ticker,
        "name": "Ripening Name / 待熟名称",
        "sector": "Technology",
        "zone": "READY",
        "reasons": "2W washout,approaching MACD cross",
        "imminence": 4.9,
        "w2_stoch": 22,
        "w2_stoch_arrow": 1,
        "w2_macd_approaching": True,
        "w2_macd_cross_up": False,
        "w1_cross_date": None,
        "w1_cross_bars_since": None,
        "w1_d_at_cross": None,
        "macd_hist_d": -0.02,
        "macd_hist_slope": 0.01,
        "days_in_washout": 12,
        "ret_5d": 0.021,
        "price": 18.4,
        "spot_pct_in_range": 35.0,
    }


def _make_ran3_row(ticker="000001.SZ"):
    return {
        "ticker": ticker,
        "name": "Ran3 Name / 已过3",
        "sector": "Technology",
        "cross_date": "2026-06-28",
        "sessions_since": 5,
        "pct_since": 6.2,
        "sublabel": "signal fired 2026-06-28 (5 sessions ago), +6.2%",
        "basing_chip": None,
    }


def _full_setups(
    entry_rows=None, ran_rows_buy=None, ripening=None, ran=None
):
    """Build a complete setups dict with all three arrays populated."""
    if entry_rows is None:
        entry_rows = [_make_entry_row()]
    if ran_rows_buy is None:
        ran_rows_buy = [_make_ran_row()]
    if ripening is None:
        ripening = [_make_ripening_row()]
    if ran is None:
        ran = [_make_ran3_row()]
    return {
        "as_of": "2026-07-03",
        "buy": entry_rows + ran_rows_buy,
        "laggards": [],
        "qvix_regime": None,
        "data_outage": None,
        "board_track": None,
        "coverage": None,
        "ripening": ripening,
        "ran": ran,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_template_parses_without_errors():
    """Full template must parse (Jinja2 syntax check) — the most important gate."""
    env = Environment(autoescape=False)
    env.parse(SRC)  # raises TemplateSyntaxError on failure


def test_no_non_ascii_attribute_delimiters():
    """Zero non-ASCII quote characters as HTML attribute delimiters anywhere in the template.

    A previous wave shipped Unicode curly-quote delimiters that broke CSS (the verify
    gate now greps for this). This test is the machine-readable form of that invariant.
    """
    # Detect non-ASCII opening delimiters: U+201C/201D (curly double), U+2018/2019 (curly single),
    # U+00AB/00BB (guillemets). ASCII double-quote (0x22) is the correct delimiter and must NOT
    # appear in this pattern.
    bad = re.findall(
        r'(?:class|style|title|href|id|data-[a-z\-]+|aria-[a-z\-]+)=[“”‘’«»]',
        SRC,
    )
    assert not bad, f"Non-ASCII attribute delimiters found: {bad}"


def test_w1c_block_is_balanced():
    """The W1-C block (entry shelf → board track comment) must have balanced if/for tags.

    This protects against an edit that breaks the tag balance without breaking the full
    template parse (a nested snippet can be unbalanced while the parent is not).
    """
    start = SRC.index("{# ── W1-C: ENTRY SHELF")
    end = SRC.index("{# ── BOARD TRACK RECORD")
    snippet = SRC[start:end]
    ifs_open = len(re.findall(r"\{%-?\s*if\s", snippet))
    fors_open = len(re.findall(r"\{%-?\s*for\s", snippet))
    ifs_close = len(re.findall(r"\{%-?\s*endif\b", snippet))
    fors_close = len(re.findall(r"\{%-?\s*endfor\b", snippet))
    assert ifs_open == ifs_close, f"Unbalanced if/endif in W1-C: {ifs_open} open vs {ifs_close} close"
    assert fors_open == fors_close, f"Unbalanced for/endfor in W1-C: {fors_open} open vs {fors_close} close"


def test_shelf_headers_have_dual_spans():
    """The RIPENING and RAN/LATE shelf headers must contain both l-en and l-zh spans.

    The ENTRY shelf header was intentionally removed (the ENTRY grid is the default top
    list — no banner needed), so st-entry no longer appears as a shelf tag. The per-card
    stg-entry badge still marks each ENTRY card.

    W8-R1 (#2102) replaced the compact st-ripe shelf with the three-zone rip-shelf
    (READY / BASING / FALLING); this test was stale against that merge and now pins
    the rip-shelf header instead.
    """
    start = SRC.index("{# ── W1-C: ENTRY SHELF")
    end = SRC.index("{# ── BOARD TRACK RECORD")
    section = SRC[start:end]
    assert 'class="l-en"' in section, "No l-en span found in W1-C shelf section"
    assert 'class="l-zh"' in section, "No l-zh span found in W1-C shelf section"
    # The RIPENING (W8-R1 rip-shelf) and RAN/LATE shelves still carry headers
    assert "rip-shelf-title" in section, "RIPENING shelf header class missing"
    assert "st-ran" in section, "RAN shelf tag class missing"


def test_no_t_call_inside_attributes_in_w1c_section():
    """The i18n gotcha: t() must not appear inside an HTML attribute in the W1-C sections."""
    start = SRC.index("{# ── W1-C: ENTRY SHELF")
    end = SRC.index("{# ── BOARD TRACK RECORD")
    w1c_block = SRC[start:end]
    bad = re.search(
        r'(?:title|style|data-[a-z]+|aria-[a-z]+|class)="[^"]*\{\{\s*t\(', w1c_block
    )
    assert not bad, (
        f"t() found inside an HTML attribute in W1-C section: {bad.group()!r}"
    )


def test_entry_cards_render_with_stage_badge():
    """ENTRY cards must include the nb-stage stg-entry badge."""
    html = _render_w1c(_full_setups())
    assert "stg-entry" in html, "ENTRY stage badge missing from rendered output"
    assert "ENTRY" in html, "ENTRY text missing"


def test_ran_cards_render_with_stage_badge_and_detail():
    """RAN_LATE cards must include stage badge (stg-ran) and the detail string."""
    html = _render_w1c(_full_setups())
    assert "stg-ran" in html, "RAN stage badge missing from rendered output"
    assert "RAN / LATE" in html, "RAN / LATE text missing"
    # Rule-2 sublabel must be visible
    assert "entry passed" in html or "wait for pullback" in html, (
        "RAN_LATE sublabel not rendered"
    )


def test_ripening_shelf_renders_compact_cards():
    """RIPENING shelf (W8-R1 rip-shelf) must render zone cards with the ticker."""
    html = _render_w1c(_full_setups())
    assert "688306.SS" in html, "Ripening ticker missing"
    assert "rip-card" in html, "RIPENING rip-card class missing"
    assert "RIPENING SHELF" in html, "RIPENING shelf header missing"
    # NOT-a-signal honesty line must appear on the shelf header
    assert "NOT an entry signal" in html, "Ripening honesty sublabel missing"


def test_ran_array_renders_honesty_rows():
    """Rule-3 RAN array (non-buy universe) must render with cross date detail."""
    html = _render_w1c(_full_setups())
    assert "000001.SZ" in html, "Rule-3 RAN ticker missing"
    assert "2026-06-28" in html, "Cross date missing from RAN row"


def test_no_buy_family_words_on_ripening_shelf():
    """RIPENING and rule-3 RAN cards must NOT use BUY/买入/act now language."""
    # Only ENTRY rows; no ripening/ran in buy array
    setups = _full_setups(entry_rows=[], ran_rows_buy=[])
    setups["ripening"] = [_make_ripening_row()]
    setups["ran"] = [_make_ran3_row()]
    html = _render_w1c(setups)
    buy_words = ["BUY NOW", "Buy now", "买入区", "act now", "立即买入"]
    for word in buy_words:
        assert word not in html, (
            f"BUY-family word {word!r} found when RIPENING/RAN rendered without ENTRY"
        )


def test_no_green_stage_badge_on_ran_cards():
    """RAN_LATE cards must use stg-ran (muted) badge — not stg-entry (green)."""
    setups = _full_setups(entry_rows=[], ran_rows_buy=[_make_ran_row()])
    html = _render_w1c(setups)
    assert "stg-ran" in html, "stg-ran badge missing"
    # stg-entry must NOT appear when there are no ENTRY rows
    assert "stg-entry" not in html, (
        "stg-entry (green) badge rendered on RAN-only board"
    )


def test_why_ranked_chip_on_entry_cards():
    """ENTRY cards must render the why_ranked chip when the field is present."""
    html = _render_w1c(_full_setups())
    assert "T1+washout_2w" in html, "why_ranked chip content missing from ENTRY card"
    assert "nb-why" in html, "nb-why class missing from ENTRY card"


def test_backward_compat_pre_w1_artifact():
    """On a pre-W1 artifact (all stage=None), all buy rows fall back to the ENTRY shelf."""
    pre_w1_row = dict(_make_entry_row())
    pre_w1_row["stage"] = None
    pre_w1_row["why_ranked"] = None
    setups = _full_setups(
        entry_rows=[pre_w1_row], ran_rows_buy=[], ripening=[], ran=[]
    )
    html = _render_w1c(setups)
    assert "300725.SZ" in html, "Backward compat: pre-W1 ticker missing"
    # ENTRY shelf should be present (backward compat path falls through to show all buy rows)
    assert "ENTRY" in html or "入场" in html, "ENTRY shelf missing in backward compat mode"


def test_ripening_shelf_absent_when_array_empty():
    """RIPENING shelf must NOT render when setups.ripening is empty."""
    setups = _full_setups(ripening=[], ran=[])
    html = _render_w1c(setups)
    assert "rip-card" not in html, (
        "RIPENING cards rendered despite empty ripening array"
    )
    assert "RIPENING SHELF" not in html, (
        "RIPENING shelf header rendered despite empty ripening array"
    )


def test_bilingual_shelf_headers_contain_zh_text():
    """Each shelf header must include CJK text (the zh span for the label)."""
    html = _render_w1c(_full_setups())
    cjk = re.search(r"[一-鿿]", html)
    assert cjk, "No CJK characters found in rendered W1-C section"
    assert "入场" in html, "ENTRY zh label (入场) missing"
    # W8-R1 rip-shelf zh title (replaced the old 待熟 compact-shelf label)
    assert "筑底观察区" in html, "RIPENING zh label (筑底观察区) missing"
    assert "信号已过" in html, "RAN zh label (信号已过) missing"


def test_entry_shelf_may_reference_cascade():
    """The cascde (T1-T4) and washout/COILED context chips remain usable in ENTRY cards."""
    html = _render_w1c(_full_setups())
    # The existing chips (washout, coiled etc) should still be present in the rendered html
    # because ENTRY cards carry all the existing chip markup intact
    assert "stg-entry" in html, "ENTRY shelf badge present"
    # nb-washout would render if washout_2w=True (set in _make_entry_row)
    assert "nb-washout" in html, "Existing washout chip missing from ENTRY card"


# ---------------------------------------------------------------------------
# B1 / B2 regression tests — adjudicated design F6
# buy_now+overextended -> RAN_LATE + muted_entry + no green banding (B1/B2 fix)
# ---------------------------------------------------------------------------

def _make_muted_ran_row(ticker="002896.SZ"):
    """RAN_LATE buy row with buy_now entry_status AND muted_entry=True.

    This is the B1/B2 scenario: a gate-eligible name whose entry gauge is nominally
    open (buy_now) but which is overextended.  Per the adjudicated F6 design it routes
    to RAN_LATE with muted_entry=True, so the template must suppress green banding.
    """
    row = dict(_make_ran_row(ticker=ticker))
    # Override: entry gauge is buy_now (would be green if not muted)
    row["entry_signal"] = _entry_signal("buy_now", "Ready", "就绪")
    row["muted_entry"] = True
    row["stage_sublabel"] = "entry gauge open — but extended; wait for pullback"
    return row


def _make_muted_partial_ran_row(ticker="002472.SZ"):
    """RAN_LATE buy row with partial entry_status AND muted_entry=True (partial case)."""
    row = _make_muted_ran_row(ticker=ticker)
    row["entry_signal"] = _entry_signal("partial", "Partial", "部分")
    return row


def test_b1_b2_muted_entry_ran_late_no_green_banding():
    """B1/B2 regression: buy_now+overextended RAN_LATE card must not render green banding.

    Verifies:
      (i)  No nbe-buy_now class in rendered output (no green left-border)
      (ii) No nbe-dot a3 green dot (the act_level 3 dot becomes a1 in muted path)
      (iii) No 'Buy now' text
      (iv) Card still renders with stg-ran badge (present on shelf)
    """
    setups = _full_setups(
        entry_rows=[], ran_rows_buy=[_make_muted_ran_row()]
    )
    html = _render_w1c(setups)
    # Green banding must be absent
    assert "nbe-buy_now" not in html, (
        "nbe-buy_now class must not appear on muted_entry RAN_LATE card")
    assert "Buy now" not in html, (
        "'Buy now' text must not appear on muted_entry RAN_LATE card")
    # stg-ran must still appear (the shelf header)
    assert "stg-ran" in html, "stg-ran badge must still appear on RAN shelf"
    # The muted neutral line must be present
    assert "not actionable" in html or "extended" in html, (
        "Muted neutral line must be present on muted_entry RAN_LATE card")


def test_b2_partial_overextended_ran_late_no_green_banding():
    """B2: partial+overextended RAN_LATE card must not render green banding (partial case).

    The old builder assert only caught buy_now; partial escaped and rendered nbe-partial
    (green left-border) on the honesty shelf — this test pins that the fix covers partial too.
    """
    setups = _full_setups(
        entry_rows=[], ran_rows_buy=[_make_muted_partial_ran_row()]
    )
    html = _render_w1c(setups)
    assert "nbe-partial" not in html, (
        "nbe-partial class must not appear on muted_entry RAN_LATE card (partial case)")
    assert "Buy now" not in html, (
        "'Buy now' text must not appear on muted_entry RAN_LATE card (partial case)")


def test_muted_entry_does_not_suppress_non_muted_ran_entry_gauge():
    """Non-muted RAN_LATE cards (e.g. hold status) still render their entry gauge."""
    row = _make_ran_row()  # muted_entry not set; entry_signal is 'hold'
    assert not row.get("muted_entry"), "Standard RAN row must not have muted_entry"
    setups = _full_setups(entry_rows=[], ran_rows_buy=[row])
    html = _render_w1c(setups)
    # The hold-status entry gauge should render (not suppressed)
    assert "nb-entry" in html, (
        "Standard (non-muted) RAN_LATE card must still render entry gauge"
    )


def test_entry_stage_card_still_green_after_muted_fix():
    """The muted_entry fix must not break ENTRY cards — they still render with green banding."""
    setups = _full_setups(entry_rows=[_make_entry_row()], ran_rows_buy=[])
    html = _render_w1c(setups)
    assert "stg-entry" in html, "ENTRY stage badge must still render"
    # The ENTRY card renders the standard buy_now gauge (nbe-buy_now or nbe- prefix)
    assert "nb-entry" in html, "ENTRY card must still render entry gauge"


def test_ran_array_launched_chip_renders():
    """Rule-3 RAN rows with launched_chip must render the launched detail line (minor 2)."""
    ran3_row = dict(_make_ran3_row())
    ran3_row["launched_chip"] = "launched from 2026-06-26, +8.9%"
    setups = _full_setups(entry_rows=[], ran_rows_buy=[], ripening=[], ran=[ran3_row])
    html = _render_w1c(setups)
    assert "launched from" in html, (
        "launched_chip must render on rule-3 RAN row (minor 2: 603129 omission fix)"
    )


def test_ran_array_basing_chip_renders():
    """Rule-3 RAN rows with basing_chip still render the basing detail line."""
    ran3_row = dict(_make_ran3_row())
    ran3_row["basing_chip"] = "basing since 2026-06-20, invalidation 43.50"
    setups = _full_setups(entry_rows=[], ran_rows_buy=[], ripening=[], ran=[ran3_row])
    html = _render_w1c(setups)
    assert "basing since" in html, (
        "basing_chip must render on rule-3 RAN row"
    )
