"""W1-C — three-shelf lifecycle render tests.

Verifies the ENTRY / RIPENING / RAN partition in templates/china.html.j2 (mode=stocks):
  - BUY-family words (BUY/买入/act now) appear on ENTRY shelf only
  - No green (buy) card banding on RAN_LATE cards
  - Every shelf header has dual-span (l-en + l-zh)
  - Zero non-ASCII attribute delimiters anywhere in the template
  - Jinja parse (the most important gate)
  - Smoke render with synthetic context containing all three arrays

Mirrors the idiom of tests/test_china_stocks_copy_w09.py (the nearest sibling).

Prophet-card redesign (2026-07-21) — what moved, and why this suite was re-pinned:
  - The ENTRY and RAN/LATE shelf cards no longer use the old nb-card markup. The old
    per-card stage badges (the green ENTRY badge + the muted RAN badge), the why-ranked
    chip, and the entry-gauge green-banding classes are all DEAD (they survive only as
    unreferenced CSS rules; this suite no longer asserts against any of them).
    Cards now render via {{ pv.pv_card({...}) }} from templates/_prophet_card.html.j2:
      · ENTRY rows -> verb 'buy'  (class="pvcard pv-buy",  stage 3 -> 'Ready' on)
      · RAN/LATE   -> verb 'wait' (class="pvcard pv-wait", stage 4 -> 'Trend' on)
    The verb hue (--pv-buy) keeps Buy green; there is no green banding on a WAIT card
    by construction, so B1/B2 is now enforced structurally, not by a class suppression.
  - GOTCHA: the pv_css() <style> block emits the class SELECTORS `.pv-buy`, `.pv-wait`
    etc. as literal text, so the bare substrings "pv-buy" / "pv-wait" are ALWAYS present
    in the output. Card-presence / card-absence assertions MUST target the full
    element-class string 'class="pvcard pv-buy"' / 'class="pvcard pv-wait"'.
  - why_ranked / tier / sig detail were DELIBERATELY demoted off this surface into the
    china_lookup analyzer (template comment ~L3206). test_why_ranked_chip_on_entry_cards
    was DELETED for that reason (2026-07-21) — the data was not lost, it moved a click away.
  - The i18n global tr() (engine/i18n.tr — canonical-ZH glossary lookup, EN fallback) is
    injected by the real builders; the harness registers the REAL tr so assertions pin
    real translation behavior (e.g. tr("BUY ZONE") == "买入区"), never a guess.
"""
import re
from pathlib import Path

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

from engine import i18n  # real tr() — light (markupsafe only); builders inject it as a global

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"
SRC = (TPL / "china.html.j2").read_text()

# Imports the real template carries at file top, OUTSIDE every snippet these
# helpers slice out. Mirror them here or the slice renders against Undefined —
# {{ dc.dc_card(...) }} then raises UndefinedError, which is a harness fault, not
# a template fault. Paired with the FileSystemLoader in _env() below, the slices
# exercise the REAL shared partials instead of stubs.
SNIPPET_IMPORTS = (
    '{% import "_prophet_card.html.j2" as pv %}\n'
    '{% import "_decision_card.html.j2" as dc %}\n'
    '{% import "_lens.html.j2" as lens %}\n'
)


def _env(extra: dict | None = None) -> Environment:
    """Jinja env whose loader can resolve ANY partial templates/ holds.

    The old harness hand-registered each partial in a DictLoader, so every new
    {% import %} in china.html.j2 broke these tests until someone remembered to
    add it. A FileSystemLoader fallback removes that failure mode for good.
    """
    env = Environment(
        loader=ChoiceLoader([DictLoader(extra or {}), FileSystemLoader(str(TPL))]),
        autoescape=False,
    )
    env.globals["tr"] = i18n.tr
    env.globals["td"] = i18n.td
    return env

# ---------------------------------------------------------------------------
# Helper: extract the W1-C block (balanced Jinja tags) and render it.
# The block runs from the W-FCT partition anchor (which hoists the shelf row
# partition sets — _entry_rows / _ran_late_rows / _rip* / _ran — ABOVE the panel
# div so the facet bar can count them) to {# ── BOARD TRACK RECORD.  Extracting
# from the W-FCT anchor (not the later "W1-C: ENTRY SHELF" comment) is load-bearing:
# without it the partition sets are undefined and every shelf renders empty.  The
# anchor sits BELOW the <script id="stocktable-data"> JSON block, so extraction
# from it is clean Jinja.
# ---------------------------------------------------------------------------

def _render_w1c(setups: dict) -> str:
    """Extract and render the W1-C three-shelf block with synthetic context."""
    start = SRC.index("{# ── W-FCT: shelf partitions hoisted above the panel")
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
    # Prophet-card partial (2026-07-21 redesign): the shelf cards render via
    # {{ pv.pv_card(...) }}; the real template imports it at file top (outside this
    # snippet), so mirror the import here and register the partial with the loader.
    full = SNIPPET_IMPORTS + macros + snippet

    SECZH = {
        "Technology": "科技",
        "Healthcare": "医疗保健",
        "Industrials": "工业",
    }

    env = _env({"blk": full})
    env.globals["SECZH"] = SECZH
    # Real i18n tr() — the extended (W-FCT) snippet calls tr() (limit-state ZH twin);
    # the builders inject env.globals.update(tr=i18n.tr).  cn_micro_by_ticker is guarded
    # by a falsy check in the ENTRY loop; {} keeps it explicit rather than Undefined.
    env.globals["tr"] = i18n.tr
    env.globals["cn_micro_by_ticker"] = {}
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
    """The W1-C block (W-FCT partition anchor → board track comment) must have balanced
    if/for tags.

    This protects against an edit that breaks the tag balance without breaking the full
    template parse (a nested snippet can be unbalanced while the parent is not).  Anchored
    to the same W-FCT start marker the render harness extracts from, so a broken balance
    here maps directly to a render failure.
    """
    start = SRC.index("{# ── W-FCT: shelf partitions hoisted above the panel")
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
    list — no banner needed), so st-entry no longer appears as a shelf tag. ENTRY cards
    now render via the Prophet card (verb chip, not a per-card shelf badge — 2026-07-21).

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


def test_entry_cards_render_with_buy_verb_and_ready_stage():
    """ENTRY cards render as a Prophet buy card at the 'Ready' lifecycle stage.

    Re-pinned from the retired green ENTRY nb-card badge (2026-07-21 Prophet redesign):
    the ENTRY row's entry_signal.status=buy_now maps to verb 'buy' (green pv-buy card)
    and stage=3, which lights the 'Ready' step of the Bottoming→Turning→Ready→Trend rail.
    """
    html = _render_w1c(_full_setups())
    # Fixture ticker present (content invariant)
    assert "300725.SZ" in html, "ENTRY fixture ticker missing from rendered output"
    # buy verb card (full element class — the bare 'pv-buy' substring is always in pv_css)
    assert 'class="pvcard pv-buy"' in html, "ENTRY card must render as a pv-buy (buy verb) card"
    # 'Ready' stage lit (stage 3)
    assert '<span class="on"><span class="l-en">Ready' in html, (
        "ENTRY card must light the 'Ready' lifecycle stage"
    )


def test_ran_cards_render_with_wait_verb_and_shelf_header():
    """RAN_LATE cards render under the st-ran shelf header as Prophet wait cards.

    Re-pinned from the retired muted RAN nb-card badge (2026-07-21 Prophet redesign): the
    shelf header still carries the st-ran tag ('RAN / LATE' / '信号已过'), each card renders
    as verb 'wait' (pv-wait), and the "entry passed" note rides in the zone-note slot.
    """
    html = _render_w1c(_full_setups())
    # Fixture ticker present (content invariant)
    assert "603129.SS" in html, "RAN_LATE fixture ticker missing from rendered output"
    # Shelf header tag + bilingual label still live
    assert "st-ran" in html, "RAN shelf tag class missing from rendered output"
    assert "RAN / LATE" in html, "RAN / LATE text missing"
    assert "信号已过" in html, "RAN zh label (信号已过) missing"
    # wait verb card (full element class — bare 'pv-wait' substring is always in pv_css)
    assert 'class="pvcard pv-wait"' in html, "RAN_LATE card must render as a pv-wait (wait verb) card"
    # "Entry passed" note rendered in the zone slot
    assert "Entry passed" in html, "RAN_LATE 'Entry passed' zone note not rendered"


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
    """RIPENING and rule-3 RAN cards must NOT use BUY/买入/act now language.

    Banned-word list may be EXTENDED, never shrunk. NOTE: this render has no ENTRY nor
    RAN_LATE buy rows, so the RAN_LATE-shelf tooltip explainer 买入就绪度 (buy-readiness,
    a legitimate explainer, not a call to buy) is out of scope here by construction.
    """
    # Only ripening + rule-3 RAN rows; no ENTRY / RAN_LATE buy rows.
    setups = _full_setups(entry_rows=[], ran_rows_buy=[])
    setups["ripening"] = [_make_ripening_row()]
    setups["ran"] = [_make_ran3_row()]
    html = _render_w1c(setups)
    # Positive control: the fixtures actually reached the output (guards against a vacuous
    # pass where the shelves silently rendered nothing and every absence trivially held).
    assert "688306.SS" in html, "ripening fixture ticker missing (banned-word check is vacuous)"
    assert "000001.SZ" in html, "rule-3 RAN fixture ticker missing (banned-word check is vacuous)"
    buy_words = ["BUY NOW", "Buy now", "买入区", "act now", "立即买入"]
    for word in buy_words:
        assert word not in html, (
            f"BUY-family word {word!r} found when RIPENING/RAN rendered without ENTRY"
        )


def test_no_green_buy_card_on_ran_cards():
    """RAN_LATE cards must render as pv-wait — never the green pv-buy card.

    Re-pinned from the retired green/muted nb-card stage badges (2026-07-21 Prophet
    redesign).  The full element-class string is asserted because the bare 'pv-buy'/'pv-wait'
    substrings are ALWAYS present (pv_css() emits them as CSS selectors).

    POSITIVE CONTROL (anti-ghost): an ENTRY-only render DOES contain the pv-buy card
    element — this proves 'class="pvcard pv-buy"' is the live marker whose ABSENCE the
    RAN-only render is asserting, not a renamed/dead string that can never appear.
    """
    # RAN-only render: wait card present, buy card absent
    ran_setups = _full_setups(entry_rows=[], ran_rows_buy=[_make_ran_row()])
    ran_html = _render_w1c(ran_setups)
    assert "603129.SS" in ran_html, "RAN fixture ticker missing (render is vacuous)"
    assert 'class="pvcard pv-wait"' in ran_html, "RAN card must render as a pv-wait card"
    assert 'class="pvcard pv-buy"' not in ran_html, (
        "green pv-buy card rendered on RAN-only board"
    )
    # Positive control: ENTRY-only render DOES contain the pv-buy card element
    entry_setups = _full_setups(entry_rows=[_make_entry_row()], ran_rows_buy=[])
    entry_html = _render_w1c(entry_setups)
    assert 'class="pvcard pv-buy"' in entry_html, (
        "positive control failed: ENTRY-only render must contain the pv-buy card"
    )


# NOTE (2026-07-21 Prophet-card redesign): test_why_ranked_chip_on_entry_cards was
# DELETED here.  why_ranked (and tier / sig detail) were deliberately demoted OFF this
# board surface — the template comment at the ENTRY loop (~L3206 of china.html.j2) records
# it: "Old nbcard retired; disclosures demoted, not deleted: ... tier/sig detail →
# china_lookup analyzer".  The data was not lost; it moved one click away (china_lookup.html).
# Re-pinning the test to any substring on this surface would be vacuous, so it is removed.


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
    """RIPENING shelf must NOT render when setups.ripening is empty.

    The buy shelves stay populated (entry + ran_late defaults) so the render is non-empty —
    absence of the ripening shelf is what's under test, not an empty page.
    """
    setups = _full_setups(ripening=[], ran=[])
    html = _render_w1c(setups)
    # Positive control: the board still rendered (ENTRY fixture present) — the ripening
    # absence below is a real absence, not a vacuous empty-render.
    assert "300725.SZ" in html, "ENTRY fixture ticker missing (render is vacuous)"
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


def test_entry_shelf_carries_washout_context():
    """The washout context survives the Prophet redesign, folded into the verb-chip tooltip.

    Re-pinned from the retired nb-washout chip (2026-07-21): when washout_2w=True the ENTRY
    card appends ' · washed out (2W)' to the verb-chip data-tip (english) and ' · 2周洗盘'
    (zh).  _make_entry_row sets washout_2w=True, so both twins must be present.
    """
    html = _render_w1c(_full_setups())
    assert "300725.SZ" in html, "ENTRY fixture ticker missing (render is vacuous)"
    assert "washed out (2W)" in html, (
        "washout context ' · washed out (2W)' missing from ENTRY verb-chip tooltip"
    )
    assert "2周洗盘" in html, "washout context zh twin (2周洗盘) missing from ENTRY tooltip"


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

    Re-pinned to the Prophet redesign (2026-07-21).  Under F6, a muted_entry row keeps the
    WAIT verb (there is no green pv-buy card by construction) and swaps the verb-chip tooltip
    headline to 'gauge open — but extended; not actionable' / '量表打开 — 但已延伸；当前不可操作'.
    Verifies:
      (i)   The card renders (fixture ticker present) as pv-wait, never the green pv-buy card
      (ii)  No 'Buy now' action text leaks onto the honesty shelf
      (iii) The muted 'not actionable' neutral line (and its zh twin) is present
    """
    setups = _full_setups(
        entry_rows=[], ran_rows_buy=[_make_muted_ran_row()]
    )
    html = _render_w1c(setups)
    assert "002896.SZ" in html, "muted RAN fixture ticker missing (render is vacuous)"
    # Green banding is impossible by construction — verb is WAIT, card is pv-wait
    assert 'class="pvcard pv-buy"' not in html, (
        "green pv-buy card must not appear on muted_entry RAN_LATE card")
    assert 'class="pvcard pv-wait"' in html, (
        "muted_entry RAN_LATE card must render as a pv-wait card")
    assert "Buy now" not in html, (
        "'Buy now' text must not appear on muted_entry RAN_LATE card")
    # The muted neutral line must be present (english + zh twin)
    assert "not actionable" in html, (
        "Muted neutral line 'not actionable' must be present on muted_entry RAN_LATE card")
    assert "不可操作" in html, (
        "Muted neutral line zh twin (不可操作) must be present on muted_entry RAN_LATE card")


def test_b2_partial_overextended_ran_late_no_green_banding():
    """B2: partial+overextended RAN_LATE card must not render green banding (partial case).

    The old builder assert only caught buy_now; partial escaped and rendered the green
    banding on the honesty shelf.  Re-pinned to the Prophet redesign: a partial+muted row
    is still a WAIT card (pv-wait), so the green pv-buy card can never appear, and no
    'Buy now' action text leaks.
    """
    setups = _full_setups(
        entry_rows=[], ran_rows_buy=[_make_muted_partial_ran_row()]
    )
    html = _render_w1c(setups)
    assert "002472.SZ" in html, "muted partial RAN fixture ticker missing (render is vacuous)"
    assert 'class="pvcard pv-buy"' not in html, (
        "green pv-buy card must not appear on muted_entry RAN_LATE card (partial case)")
    assert 'class="pvcard pv-wait"' in html, (
        "muted_entry partial RAN_LATE card must render as a pv-wait card")
    assert "Buy now" not in html, (
        "'Buy now' text must not appear on muted_entry RAN_LATE card (partial case)")


def test_muted_entry_does_not_suppress_non_muted_ran_entry_headline():
    """Non-muted RAN_LATE cards (e.g. hold status) still surface their entry headline.

    Re-pinned from the retired nb-entry gauge (2026-07-21): a non-muted RAN row is NOT
    swapped to the 'not actionable' line, so its entry_signal.headline ('Hold' / '持有',
    set in _make_ran_row) rides through into the verb-chip tooltip.  This proves the muted
    swap is scoped to muted_entry rows and does not blanket-suppress the entry read.
    """
    row = _make_ran_row()  # muted_entry not set; entry_signal is 'hold'
    assert not row.get("muted_entry"), "Standard RAN row must not have muted_entry"
    setups = _full_setups(entry_rows=[], ran_rows_buy=[row])
    html = _render_w1c(setups)
    assert "603129.SS" in html, "non-muted RAN fixture ticker missing (render is vacuous)"
    # The hold-status entry headline (both twins) must ride through, not the muted line
    assert "Hold" in html, "non-muted RAN card must surface its entry headline ('Hold')"
    assert "持有" in html, "non-muted RAN card must surface its entry headline zh twin ('持有')"
    assert "not actionable" not in html, (
        "the muted 'not actionable' swap must not fire on a non-muted RAN card"
    )


def test_entry_stage_card_still_green_after_muted_fix():
    """The muted_entry fix must not break ENTRY cards — they still render the green buy card.

    Re-pinned to the Prophet redesign (2026-07-21): the ENTRY row's buy_now status still
    maps to the green pv-buy card with the 'Ready' stage lit.
    """
    setups = _full_setups(entry_rows=[_make_entry_row()], ran_rows_buy=[])
    html = _render_w1c(setups)
    assert "300725.SZ" in html, "ENTRY fixture ticker missing (render is vacuous)"
    assert 'class="pvcard pv-buy"' in html, "ENTRY card must still render the green pv-buy card"
    assert '<span class="on"><span class="l-en">Ready' in html, (
        "ENTRY card must still light the 'Ready' lifecycle stage"
    )


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
        "rel5": None,
        "tag": None,
        "tag_zh": None,
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
        "href": None,
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
        "tag_zh": "买入区",
        "urgency": "now",
    })
    return row


def _make_sector_card_for_ticker(ticker="512480.SS"):
    """Synthetic sector card mirroring build_china._sector_cards output.

    Contract (per engine/china_inputs.py):
      - pctile: float in 0-100 range (rs.rank(pct=True)*100)
      - above200: bool (single-name bool from above_200d_trend)
    """
    return {
        "ticker": ticker,
        "name": "Tech Sector",
        "mom20": 3.5,
        "mom60": 12.1,
        "above200": True,
        "pctile": 82.0,
        "state": "RISING",
        "label": "Uptrend",
        "dir": "up",
        "entry": {"text": "Buy zone", "text_zh": "买入区", "tag": "BUY ZONE",
                  "tag_zh": "买入区", "urgency": "now"},
        "age_short": "3w",
        "age_short_zh": "3周",
        "dc_day": 18,
        "dc_band": "mid",
        "eq_badge": "EQ+",
        "eq_dir": "up",
        "eq_tip": "Equity quality improving",
    }


def _make_sector_card_none_enrichment(ticker="600519.SS"):
    """Sector card where optional enrichment fields are present but None.

    Tests that the template omits those cells gracefully without crash.
    """
    return {
        "ticker": ticker,
        "name": "Wine Sector",
        "mom20": None,
        "mom60": None,
        "above200": None,
        "pctile": None,
        "state": "FLAT",
        "label": "Flat",
        "dir": "flat",
        "entry": None,
        "age_short": None,
        "age_short_zh": None,
        "dc_day": None,
        "dc_band": None,
        "eq_badge": None,
        "eq_dir": None,
        "eq_tip": None,
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
    full = SNIPPET_IMPORTS + macros + snippet

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

    # The anv2 board calls tr() for every l-zh fallback (name/kind/reco/tag/phase/
    # organ_state/reasons).  _env registers the REAL tr — the builders inject it as a global.
    env = _env({"blk": full})
    return env.get_template("blk").render(
        act_now_v2=act_now_v2,
        mode="stocks",
        lang="en",
        sectors_by_ticker=sectors_by_ticker or {},
    )


def test_anv2_row_has_data_rpop_attribute():
    """Every anv2-row must carry data-rpop attribute (PR-4)."""
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    assert "Growth Theme" in html, "fixture row name missing (render is vacuous)"
    assert "data-rpop" in html, "data-rpop attribute missing from anv2 row"


def test_anv2_row_has_rp_src_child():
    """Every anv2-row must contain a .rp-src payload span (PR-4)."""
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    assert "Growth Theme" in html, "fixture row name missing (render is vacuous)"
    assert "rp-src row-pop-decision" in html, "shared decision-card payload missing from anv2 row"


def test_anv2_payload_with_all_fields_none():
    """A fully null row must render without crash; empty cells omitted."""
    html = _render_anv2({"buy_now": [_blank_anv2_row()]})
    assert "data-rpop" in html, "data-rpop missing on null row"
    assert "rp-src row-pop-decision" in html, "shared decision-card payload missing on null row"
    # Name must appear in header
    assert "Test Theme" in html, "Row name missing in payload header"


def test_anv2_payload_fully_populated_theme_row():
    """Fully populated THEME row: name, score, reco, RS, reasons render in payload."""
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    assert "Growth Theme" in html, "Row name missing from payload"
    assert "Accumulate" in html, "reco_en missing from payload tag"
    # Score rides the ring, not a "Composite score" label cell (shared decision card).
    assert "row-pop-score-ring" in html, "score ring missing from theme payload"
    assert 'style="--score:75"' in html, "score not driving the ring fill"
    assert "Current read" in html, "read kicker missing from theme payload"
    assert "20d lead" in html, "20d lead stat missing"
    # Engine reasons collapse onto the one-line sub, no longer a bullet list.
    assert "Strong breadth" in html, "engine reason missing from theme sub line"


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
    # Positive control: the fixture row actually rendered (guards against a vacuous pass).
    assert "Growth Theme" in html, "fixture row name missing (render is vacuous)"
    # Isolate the rp-src payload block for the buy-lane row.  It appears before
    # the anv2-row-top div and ends at </span> of the .rp-src span.
    rp_start = html.index("rp-src row-pop-decision")
    rp_end = html.index("anv2-row-top", rp_start)
    rp_block = html[rp_start:rp_end]
    # The bottoming caveat must NOT be in the buy-lane rp-src footer
    assert "early signs of a bottom" not in rp_block, (
        "Bottoming-lane caveat leaked into buy-lane row rp-src footer"
    )


def test_anv2_sector_row_enriched_via_sectors_by_ticker():
    """SECTOR rows must pull mom20/pctile/entry from sectors_by_ticker lookup.

    pctile is already 0-100 — rendered value must be '82', NOT '8200'.
    above200 is a bool — rendered as glyph (▲/—), NOT as percentage.
    """
    row = _sector_anv2_row()
    sc = _make_sector_card_for_ticker("512480.SS")
    html = _render_anv2(
        {"buy_now": [row]},
        sectors_by_ticker={"512480.SS": sc},
    )
    assert "20d move" in html, "20d move stat missing from SECTOR payload"
    assert "Strength rank" in html, "strength rank stat missing"
    assert "Buy zone" in html or "买入区" in html, "Entry text missing from SECTOR payload"
    assert "EQ+" in html, "eq_badge missing from SECTOR payload"
    # pctile 82.0 must render as '82p', NOT '8200p' (already-0-100 value)
    assert "82p" in html, "pctile 82.0 must render as '82p'"
    assert "8200" not in html, "pctile double-scaled to 8200 — ×100 bug present"
    # above200=True bool must render as '▲' glyph, NOT as a percentage
    assert "▲" in html, "above200=True bool must render as ▲ glyph"
    payload = html[html.index("rp-src row-pop-decision"):]
    payload = payload[:payload.index("anv2-row-top")]
    assert "100%" not in payload, "above200 bool must not render as '100%' in the payload"


def test_anv2_sector_row_missing_sector_card_graceful():
    """SECTOR row with no matching sectors_by_ticker entry renders without crash."""
    row = _sector_anv2_row()
    html = _render_anv2({"buy_now": [row]}, sectors_by_ticker={})
    assert "Tech Sector" in html, "fixture row name missing (render is vacuous)"
    assert "data-rpop" in html, "data-rpop missing when sector card absent"


def test_anv2_sector_tag_chip_bilingual():
    """SECTOR tag chip must render EN/ZH twins via t(), not raw English only.

    DESIGN_DOCTRINE Law 2/§5.5: bilingual parity at the glance tier — the ZH
    board must show 买入区, not 'BUY ZONE'.
    """
    html = _render_anv2({"buy_now": [_sector_anv2_row()]})
    start = html.index("anv2-chip-tag")
    chip = html[start:start + 300]  # window covers both nested l-en/l-zh spans
    assert 'class="l-en">BUY ZONE' in chip, "EN tag missing from tag chip"
    assert 'class="l-zh">买入区' in chip, "ZH tag twin missing from tag chip"


def test_anv2_sector_tag_chip_falls_back_to_glossary_when_tag_zh_none():
    """tag_zh=None (older artifact) must fall back to tr(tag) — the canonical-ZH glossary.

    Re-pinned for real-i18n tr behavior (the harness now registers the real engine.i18n.tr,
    matching the builders).  The template renders {{ t(row.tag, row.tag_zh or tr(row.tag)) }};
    with tag_zh=None the l-zh span carries tr('BUY ZONE') == '买入区' (glossary hit, LEX), NOT
    the raw English 'BUY ZONE'.  This is stronger than the old EN-echo pin: it verifies the
    bilingual board shows the canonical Chinese even when the artifact omits tag_zh.
    """
    # Guard: the fallback under test is a real glossary hit, not an EN echo.
    assert i18n.tr("BUY ZONE") == "买入区", "fixture assumption: tr('BUY ZONE') is a glossary hit"
    row = _sector_anv2_row()
    row["tag_zh"] = None
    html = _render_anv2({"buy_now": [row]})
    start = html.index("anv2-chip-tag")
    chip = html[start:start + 300]  # window covers both nested l-en/l-zh spans
    assert 'class="l-en">BUY ZONE' in chip, "l-en tag missing from tag chip"
    assert 'class="l-zh">买入区' in chip, "l-zh span must fall back to tr(tag) glossary term (买入区)"


def test_anv2_payload_bilingual_header():
    """Payload header must include both l-en and l-zh spans."""
    html = _render_anv2({"buy_now": [_full_anv2_row()]})
    assert "Growth Theme" in html, "fixture row name missing (render is vacuous)"
    assert 'class="l-en"' in html, "l-en span missing in anv2 payload"
    assert 'class="l-zh"' in html, "l-zh span missing in anv2 payload"


def test_anv2_payload_leadership_word_only_when_leadership_data_present():
    """The payload may claim a "Leadership read" ONLY when the row carries one.

    The original PR-4 brief banned the word outright, because the board carried no
    leadership data at all — the word would have been an unsupported claim. The
    2026-08-02 US-parity pass lifts theme_intel.leadership onto the lane row, so
    the honest invariant is no longer "never say it" but "only say it when the
    evidence is there". That is the stronger guard: a blanket string ban would
    still pass if the kicker claimed a leadership read on a row with no data.
    """
    # With leadership data — the kicker names it.
    lead = _full_anv2_row()
    lead["leadership"] = "broad"
    html = _render_anv2({"buy_now": [lead]})
    assert "Growth Theme" in html, "fixture row name missing (render is vacuous)"
    assert "Leadership read" in html, "leadership read kicker missing when data present"

    # Without it — the word must not appear anywhere in the payload.
    bare = _full_anv2_row()
    bare.pop("leadership", None)
    html = _render_anv2({"buy_now": [bare]})
    assert "Growth Theme" in html, "fixture row name missing (render is vacuous)"
    assert "Leadership" not in html, "'Leadership' claimed on a row with no leadership data"
    assert "Current read" in html, "neutral kicker missing on a row with no leadership data"


def test_anv2_view_all_button_present_when_items_exceed_4():
    """lst-more button must appear when a lane has more than 4 rows."""
    rows = [_blank_anv2_row(name=f"Row {i}", name_zh=f"行 {i}") for i in range(5)]
    html = _render_anv2({"buy_now": rows})
    assert "Row 0" in html, "fixture rows missing (render is vacuous)"
    assert "lst-more" in html, "lst-more button missing when > 4 items"
    assert "lst-collapse" in html, "lst-collapse class missing"


def test_anv2_view_all_button_absent_when_4_or_fewer():
    """lst-more button must NOT appear when a lane has 4 or fewer rows."""
    rows = [_blank_anv2_row(name=f"Row {i}", name_zh=f"行 {i}") for i in range(4)]
    html = _render_anv2({"buy_now": rows})
    # Positive control: the 4 rows actually rendered (absence of lst-more is non-vacuous).
    assert "Row 0" in html, "fixture rows missing (render is vacuous)"
    assert "Row 3" in html, "fixture rows missing (render is vacuous)"
    assert "lst-more" not in html, "lst-more button appeared for <= 4 items"


def test_anv2_sector_card_none_enrichment_fields_render_without_crash():
    """SECTOR row with a card where mom20/mom60/pctile/above200 are all None must
    render without crash and must omit those cells from the payload.

    Covers the case where a sector card exists in sectors_by_ticker but the
    enrichment fields have not yet been computed (e.g. new listing, data gap).
    """
    row = _sector_anv2_row()
    # Override the ticker to match the None-enrichment card
    row = dict(row)
    row["id"] = "600519.SS"
    sc = _make_sector_card_none_enrichment("600519.SS")
    html = _render_anv2(
        {"buy_now": [row]},
        sectors_by_ticker={"600519.SS": sc},
    )
    # Must render at all (no crash) — fixture content present proves the row rendered
    assert "Tech Sector" in html, "fixture row name missing (render is vacuous)"
    assert "data-rpop" in html, "data-rpop missing when enrichment fields are None"
    assert "rp-src row-pop-decision" in html, "decision card missing when enrichment fields are None"
    # None-valued cells must be omitted — labels should NOT appear
    assert "20d mom" not in html, "20d mom label rendered despite mom20=None"
    assert "60d mom" not in html, "60d mom label rendered despite mom60=None"
    assert "RS percentile" not in html, "RS percentile label rendered despite pctile=None"
    assert "Above 200d" not in html, "Above 200d label rendered despite above200=None"


# ---------------------------------------------------------------------------
# Suite-level anti-vacuity canary
# ---------------------------------------------------------------------------


def test_positive_control_fixture_drives_output():
    """Suite-level canary: the fixtures must actually reach the rendered output.

    Renders the full three-shelf board with every fixture array populated and asserts all
    four fixture tickers appear (one per shelf: ENTRY / RAN_LATE / ripening / ran-array).
    Then renders with every array empty and asserts NONE of them appear.  If the extraction
    marker drifts, a partition set goes undefined, or a shelf silently stops rendering, one
    of these two halves goes red — this is the guard against a re-pin that passes vacuously.
    """
    tickers = ("300725.SZ", "603129.SS", "688306.SS", "000001.SZ")

    populated = _render_w1c(_full_setups())
    for tk in tickers:
        assert tk in populated, (
            f"populated render is missing fixture ticker {tk!r} — a shelf is not rendering"
        )

    empty = _render_w1c(
        _full_setups(entry_rows=[], ran_rows_buy=[], ripening=[], ran=[])
    )
    for tk in tickers:
        assert tk not in empty, (
            f"empty render still contains fixture ticker {tk!r} — output is not fixture-driven"
        )
