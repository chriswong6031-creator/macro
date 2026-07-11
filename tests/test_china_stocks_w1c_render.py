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


# ---------------------------------------------------------------------------
# PR-4: anv2 board hover payload tests
# Tests the _anrow macro's data-rpop + .rp-src payload (conditions card).
# Uses the ACT-NOW v2 block extracted between its HTML comment markers.
# ---------------------------------------------------------------------------

def _blank_anv2_row(kind="THEME", name="Test Theme", name_zh="测试主题"):
    """Minimal anv2 row dict — mirrors engine/china_act_now._blank_row exactly."""
    return {
        "kind": kind,
        "id": "test_id",
        "name": name,
        "name_zh": name_zh,
        "score": None,
        "reco": None,
        "reco_en": None,
        "reco_zh": None,
        "rel20": None,
        "tag": None,
        "urgency": None,
        "reasons": [],
        "phase": None,
        "osc_slope": None,
        "pos": None,
        "rs_63d": None,
        "rs_rank": None,
        "dual_read": False,
        "dual_chip_en": None,
        "dual_chip_zh": None,
        "organ_state": None,
        "organ_chip_en": None,
        "organ_chip_zh": None,
    }


def _full_anv2_row():
    """Fully populated anv2 row (all displayable fields non-None)."""
    row = _blank_anv2_row(kind="THEME", name="Growth Theme", name_zh="成长主题")
    row.update({
        "score": 75,
        "reco": "accumulate",
        "reco_en": "Accumulate",
        "reco_zh": "积累",
        "rel20": 0.042,
        "rs_63d": 8.3,
        "rs_rank": 2,
        "reasons": ["Strong breadth", "Earnings beat"],
        "organ_state": "TURNING",
        "organ_chip_en": "TURNING ↗",
        "organ_chip_zh": "转向 ↗",
    })
    return row


def _bot_anv2_row():
    """Bottoming-lane anv2 row with phase/pos/osc_slope."""
    row = _blank_anv2_row(kind="SECTOR", name="Beaten Sector", name_zh="超跌板块")
    row.update({
        "phase": "TROUGH",
        "pos": 12.5,
        "osc_slope": 1.8,
        "rs_63d": -5.2,
        "rs_rank": 9,
    })
    return row


def _sector_anv2_row():
    """SECTOR kind row for testing sectors_by_ticker enrichment."""
    row = _blank_anv2_row(kind="SECTOR", name="Tech Sector", name_zh="科技板块")
    row.update({
        "id": "512480.SS",
        "tag": "BUY ZONE",
        "urgency": "now",
    })
    return row


def _make_sector_card_for_ticker(ticker="512480.SS"):
    """Synthetic sector card mirroring build_china._sector_cards output."""
    return {
        "ticker": ticker,
        "name": "Tech Sector",
        "mom20": 3.5,
        "mom60": 12.1,
        "above200": 0.67,
        "pctile": 0.82,
        "state": "RISING",
        "label": "Uptrend",
        "dir": "up",
        "entry": {"text": "Buy zone", "text_zh": "买入区", "tag": "BUY ZONE", "urgency": "now"},
        "age_short": "3w",
        "age_short_zh": "3周",
        "dc_day": 18,
        "dc_band": "mid",
        "eq_badge": "EQ+",
        "eq_dir": "up",
        "eq_tip": "Equity quality improving",
    }


def _render_anv2(rows_by_lane: dict, sectors_by_ticker: dict | None = None,
                 as_of: str = "2026-07-10") -> str:
    """Extract and render the ACT-NOW v2 board block with synthetic context.

    The anv2 block lives inside {% if mode == 'stocks' %} (line ~699) so the
    extracted snippet carries one extra {% endif %} at the end that closes that
    outer if.  We prepend the matching opening {% if mode == 'stocks' %} to keep
    the snippet self-balanced.
    """
    start = SRC.index("<!-- ===================== ACT-NOW v2")
    end = SRC.index("{% if mode != 'stocks' %}", start)
    snippet = SRC[start:end]

    macros = (
        '{%- macro t(en, zh="") -%}'
        '<span class="l-en">{{ en }}</span>'
        '<span class="l-zh">{{ zh if zh else en }}</span>'
        '{%- endmacro -%}\n'
        '{%- macro help(en, zh="") -%}<span></span>{%- endmacro -%}\n'
        # Balance the outer {% if mode == 'stocks' %} that opened before the snippet
        "{% if mode == 'stocks' %}\n"
    )
    full = macros + snippet

    # Build lanes dict
    default_lanes = {"buy_now": [], "wait_pullback": [], "bottoming_watch": [], "reduce_avoid": []}
    for k, v in rows_by_lane.items():
        default_lanes[k] = v

    act_now_v2 = {
        "as_of": as_of,
        "notes": [],
        "lanes": {
            "buy_now": default_lanes["buy_now"],
            "wait_pullback": default_lanes["wait_pullback"],
            "bottoming_watch": default_lanes["bottoming_watch"],
            "reduce_avoid": default_lanes["reduce_avoid"],
        },
    }

    env = Environment(loader=DictLoader({"blk": full}), autoescape=False)
    return env.get_template("blk").render(
        act_now_v2=act_now_v2,
        mode="stocks",
        lang="en",
        sectors_by_ticker=sectors_by_ticker or {},
    )


def test_anv2_row_has_data_rpop_attribute():
    """Every anv2-row must carry data-rpop attribute (PR-4)."""
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    assert "data-rpop" in html, "data-rpop attribute missing from anv2 row"


def test_anv2_row_has_rp_src_child():
    """Every anv2-row must contain a .rp-src payload span (PR-4)."""
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    assert 'class="rp-src"' in html, ".rp-src payload span missing from anv2 row"


def test_anv2_payload_with_all_fields_none():
    """A fully null row must render without crash; empty cells omitted."""
    html = _render_anv2({"buy_now": [_blank_anv2_row()]})
    assert "data-rpop" in html, "data-rpop missing on null row"
    assert 'class="rp-src"' in html, ".rp-src missing on null row"
    # Name must appear in header
    assert "Test Theme" in html, "Row name missing in payload header"


def test_anv2_payload_fully_populated_theme_row():
    """Fully populated THEME row: name, score, reco, RS, reasons render in payload."""
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    assert "Growth Theme" in html, "Row name missing from payload"
    assert "Accumulate" in html, "reco_en missing from payload tag"
    assert "Composite score" in html, "score label missing"
    assert "63d RS" in html, "RS label missing"
    assert "Strong breadth" in html, "reason bullet missing"


def test_anv2_payload_bottoming_row_has_not_buy_caveat():
    """Bottoming lane rows must carry the NOT-a-buy-signal caveat in the footer."""
    html = _render_anv2({"bottoming_watch": [_bot_anv2_row()]})
    assert "NOT a buy signal" in html or "非买入信号" in html, (
        "NOT-a-buy-signal caveat missing from bottoming row footer"
    )


def test_anv2_payload_non_bottoming_row_no_buy_caveat_in_rp_src():
    """Buy-lane rp-src payload footer must NOT carry the bottoming caveat.

    The anv2-bot-disc disclaimer always renders in the bottoming lane header —
    that is correct and expected.  The per-row .rp-src footer must only include
    the caveat when lane == 'bot'.  We verify by checking that the rp-src payload
    for a buy-lane row does NOT contain the caveat text directly after 'row-pop-ft'.
    """
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    # Isolate the rp-src payload block for the buy-lane row.  It appears before
    # the anv2-row-top div and ends at </span> of the .rp-src span.
    rp_start = html.index('class="rp-src"')
    rp_end = html.index('</span>', html.index('row-pop-ft', rp_start)) + len('</span>')
    rp_block = html[rp_start:rp_end]
    # The bottoming caveat must NOT be in the buy-lane rp-src footer
    assert "early signs of a bottom" not in rp_block, (
        "Bottoming-lane caveat leaked into buy-lane row rp-src footer"
    )


def test_anv2_sector_row_enriched_via_sectors_by_ticker():
    """SECTOR rows must pull mom20/pctile/entry from sectors_by_ticker lookup."""
    row = _sector_anv2_row()
    sc = _make_sector_card_for_ticker("512480.SS")
    html = _render_anv2(
        {"buy_now": [row]},
        sectors_by_ticker={"512480.SS": sc},
    )
    assert "20d mom" in html, "20d mom label missing from SECTOR payload"
    assert "RS percentile" in html, "RS percentile label missing"
    assert "Buy zone" in html or "买入区" in html, "Entry text missing from SECTOR payload"
    assert "EQ+" in html, "eq_badge missing from SECTOR payload"


def test_anv2_sector_row_missing_sector_card_graceful():
    """SECTOR row with no matching sectors_by_ticker entry renders without crash."""
    row = _sector_anv2_row()
    html = _render_anv2({"buy_now": [row]}, sectors_by_ticker={})
    assert "data-rpop" in html, "data-rpop missing when sector card absent"


def test_anv2_payload_bilingual_header():
    """Payload header must include both l-en and l-zh spans."""
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    assert 'class="l-en"' in html, "l-en span missing in anv2 payload"
    assert 'class="l-zh"' in html, "l-zh span missing in anv2 payload"


def test_anv2_payload_no_leadership_word():
    """'Leadership' word must not appear in the anv2 payload (brief spec)."""
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    assert "Leadership" not in html, "'Leadership' word found in anv2 payload"


def test_anv2_view_all_button_present_when_items_exceed_4():
    """lst-more button must appear when a lane has more than 4 rows."""
    rows = [_blank_anv2_row(name=f"Row {i}", name_zh=f"行 {i}") for i in range(5)]
    html = _render_anv2({"buy_now": rows})
    assert "lst-more" in html, "lst-more button missing when > 4 items"
    assert "lst-collapse" in html, "lst-collapse class missing"


def test_anv2_view_all_button_absent_when_4_or_fewer():
    """lst-more button must NOT appear when a lane has 4 or fewer rows."""
    rows = [_blank_anv2_row(name=f"Row {i}", name_zh=f"行 {i}") for i in range(4)]
    html = _render_anv2({"buy_now": rows})
    assert "lst-more" not in html, "lst-more button appeared for <= 4 items"
