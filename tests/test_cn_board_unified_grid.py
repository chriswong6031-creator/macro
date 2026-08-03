"""CN board G0.2 — the unified live grid, and G5 — prior-definition continuity.

Pins the presentation contract of templates/china.html.j2 (mode=stocks) after the
prophet-board-priority merge:

  * `setups.buy` (the featured picks) and `setups.more_actionable` render in ONE
    `.nbgrid` — featured first in the PRODUCER's order, then every actionable row as a
    FULL prophet card in priority-score order. The old collapsed "More live setups"
    compact drawer is gone.
  * The `.pv-featured` glow lands on featured rows and ONLY on featured rows.
  * Every merged row carries the Priority slot, a plain-word marks chip, and no raw
    lane_reasons slug at glance tier.
  * The `late_or_unfillable` / `forming` / legacy depth lanes are untouched.
  * A pre-v2 artifact (no `more_actionable`, no `ranking`, no `prophet` score) still
    renders the legacy shelf — the fail-soft contract. Byte-identity against the
    pre-merge template was verified at build time by rendering BOTH templates against
    the real pre-v2 artifact (git 55836b2f89c) and diffing the tag stream and class
    histogram; a git-pinned diff cannot live in CI (HEAD moves), so what this suite
    pins forward is every observable half of it: producer order preserved, no glow, no
    marks row, no key line, the conviction-score fallback in the Edge slot UNROUNDED,
    the legacy verb map (bounce_wait is a Near, never a Wait), stage 3 on every card,
    and the pre-merge panel title. The pre-v2 fixture therefore carries the REAL
    artifact's status mix — a bounce_wait majority — because a fixture built from
    buy_now rows alone cannot see any of that.
  * The track-record dialog grows a "previous board definition" section when the ledger
    carries `prior_record`, and is unchanged when it does not.

GOTCHA inherited from tests/test_china_stocks_w1c_render.py: pv_css() emits the class
SELECTORS as literal text, so bare substrings like "pv-featured" are ALWAYS present in
the output. Every card assertion here targets the full element-class string
(`class="pvcard pv-buy pv-featured"`), never a bare token.
"""
import collections
import re
from pathlib import Path

import pytest
from jinja2 import DictLoader, Environment

from engine import i18n

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "templates" / "china.html.j2").read_text()

MACROS = (
    '{%- macro t(en, zh="") -%}'
    '<span class="l-en">{{ en }}</span><span class="l-zh">{{ zh if zh else en }}</span>'
    "{%- endmacro -%}\n"
    '{%- macro td(x) -%}{{ x }}{%- endmacro -%}\n'
    '{%- macro nm(name) -%}{% set p = (name or "").split(" / ") %}'
    '<span class="l-en">{{ p[0] }}</span>'
    '<span class="l-zh">{{ p[1] if p|length > 1 else p[0] }}</span>{%- endmacro -%}\n'
    '{%- macro help(en, zh="", cls="") -%}'
    '<span class="help">?<span class="tip"><span class="l-en">{{ en }}</span>'
    '<span class="l-zh">{{ zh }}</span></span></span>{%- endmacro -%}\n'
)

SECZH = {"Technology": "科技", "Industrials": "工业", "Healthcare": "医疗保健"}


def _macro_src(name: str) -> str:
    start = SRC.index("{%% macro %s(" % name)
    return SRC[start:SRC.index("{%- endmacro %}", start) + len("{%- endmacro %}")]


def _env(extra: dict | None = None) -> Environment:
    loader = {
        "_prophet_card.html.j2": (ROOT / "templates" / "_prophet_card.html.j2").read_text(),
        "_track_record_dlg.html.j2": (ROOT / "templates" / "_track_record_dlg.html.j2").read_text(),
    }
    loader.update(extra or {})
    env = Environment(loader=DictLoader(loader), autoescape=False)
    env.globals.update(tr=i18n.tr, td=i18n.td, cn_micro_by_ticker={}, SECZH=SECZH)
    return env


def render_board(setups: dict) -> str:
    """Render the standouts block (facet bar → depth lanes) with synthetic context."""
    start = SRC.index("{# ── W-FCT: shelf partitions hoisted above the panel")
    end = SRC.index("{# ── BOARD TRACK RECORD")
    body = (
        '{% import "_prophet_card.html.j2" as pv %}\n'
        + MACROS + _macro_src("cn_lane_reason") + "\n" + _macro_src("cn_depth_grid") + "\n"
        + SRC[start:end]
    )
    return _env({"blk": body}).get_template("blk").render(setups=setups)


def render_dialog(setups: dict) -> str:
    """Render the track-record chip + dialog block (the `_cl` host wiring)."""
    start = SRC.index("{# ── BOARD TRACK RECORD")
    anchor = "<div style=\"margin:14px 0 0\">{% include '_track_record_dlg.html.j2' %}</div>"
    end = SRC.index(anchor) + len(anchor)
    body = MACROS + SRC[start:end] + "\n{% endif %}"
    return _env({"blk": body}).get_template("blk").render(setups=setups)


# ── fixtures ────────────────────────────────────────────────────────────────────────

def _row(ticker, score, *, status="buy_now", lane="featured", reasons=None, dss=None,
         star=False, washout=False, name=None, sector="Technology", conv=60,
         stage="ENTRY", action="Buy in the zone.", action_zh="在买区买入。"):
    return {
        "ticker": ticker,
        "name": name or f"{ticker} Holdings / {ticker}控股",
        "sector": sector,
        "stage": stage,
        "lane": lane,
        "lane_reasons": reasons if reasons is not None else ["buyable_signal"],
        "days_since_signal": dss,
        "price": 12.34,
        "washout_2w": washout,
        "coiled": {"coiled": True, "star": star, "washout_ctx": True},
        "extension": None,
        "microstructure": None,
        "spark_svg": None,
        "signal": {"tier_cascade": "T1", "asof": "2026-07-31"},
        "prophet": {"score": score, "components": {"signal": 1.0, "reversal_member": 0.0}},
        "conviction": {"score": conv, "verdict": "Buy zone", "verdict_zh": "买区",
                       "cautions": None, "cautions_zh": None},
        "entry_signal": {"status": status, "headline": "Ready", "headline_zh": "就绪",
                         "action": action, "action_zh": action_zh,
                         "buy_zone": {"low": 11.0, "high": 12.5}},
    }


# The two RALLY-ON hold action lines the engine actually emits (engine/cycles.py ~L819).
# The mid-cycle one is what all 25 hold rows of the 2026-08-02 artifact carry.
HOLD_DIP_EN = "Trend intact — hold; add on dips toward the 10-day average."
HOLD_DIP_ZH = "趋势完好——持有；可在回调至 10 日均线附近时加仓。"
HOLD_LATE_EN = "Trend intact — hold. Late in the cycle, so don't add here; a pullback is due."
HOLD_LATE_ZH = "趋势完好——持有。已处周期晚期，此处不宜加仓；回调即将到来。"


def v2_setups(**over):
    """A cn_prophet_v2-shaped artifact: 3 featured + 4 more_actionable."""
    s = {
        "as_of": "2026-07-31",
        "board_definition": "cn_prophet_v2",
        "ranking": {"definition": "cn_prophet_v2", "formula_points": {"signal": 35.0}},
        # Producer order for `buy` is display_rank, NOT score — deliberately jumbled here
        # so a template that re-sorts the featured cohort fails this suite.
        "buy": [_row("601111.SS", 70.0, dss=1), _row("601222.SS", 88.0, dss=0),
                _row("601333.SS", 64.0, dss=9)],
        "more_actionable": [
            # a REAL hold row: the engine's own mid-cycle action line, which the chip
            # copy has to agree with (it used to say "No add here" on top of it)
            _row("300111.SZ", 61.0, status="hold", lane="more_actionable",
                 reasons=["entry_status_hold"],
                 action=HOLD_DIP_EN, action_zh=HOLD_DIP_ZH),
            _row("300222.SZ", 93.0, status="bounce_wait", lane="more_actionable",
                 reasons=["entry_status_bounce_wait"], star=True),
            _row("300333.SZ", 75.0, status="extended", lane="more_actionable",
                 reasons=["entry_status_extended"], dss=2),
            _row("300444.SZ", 82.0, status="bounce_wait", lane="more_actionable",
                 reasons=["sector_cap"], washout=True),
        ],
        "late_or_unfillable": [_row("600999.SS", 40.0, lane="late", reasons=["unfillable"])],
        "forming": [_row("002888.SZ", 30.0, lane="forming", reasons=["no_buyable_tier"])],
        "ripening": [],
        "ran": [],
        "watch": [],
    }
    s.update(over)
    return s


# The real pre-v2 artifact (git 55836b2f89c:site/factordata/china_standouts.json) held
# 110 buy rows: bounce_wait 84, hold 10, buy_now 7, partial 7, topping 2 — 104 ENTRY and
# 6 RAN_LATE. This fixture keeps that SHAPE at 1/10 scale, and it is the whole point of
# the pre-v2 half of this suite: the old fixture derived its rows from v2_setups()["buy"],
# whose statuses are only ever buy_now, so every row took the one code path that happened
# to be gated correctly. 90 of 110 real rows took the OTHER path and were silently
# re-styled (pv-near → pv-wait, Ready → Turning / Trend) with nothing here to see it.
PREV2_MIX = (("bounce_wait", 6), ("hold", 2), ("buy_now", 1), ("partial", 1), ("topping", 1))
# what origin/main's legacy expression renders for each of those statuses
PREV2_VERB = {"bounce_wait": "pv-near", "hold": "pv-hold", "topping": "pv-hold",
              "buy_now": "pv-buy", "partial": "pv-buy"}


def prev2_setups():
    """A pre-v2 artifact: no more_actionable lane, no ranking block, no prophet score."""
    rows, i = [], 0
    for status, n in PREV2_MIX:
        for _ in range(n):
            i += 1
            # one FRACTIONAL conviction score: the legacy Edge slot passes the raw value
            # through, so a v2-only '%.0f' rounding leaking onto this path shows up here.
            r = _row("6000%02d.SS" % i, 0.0, status=status,
                     conv=61.5 if i == 1 else 60,
                     action=HOLD_DIP_EN if status == "hold" else "Buy in the zone.",
                     action_zh=HOLD_DIP_ZH if status == "hold" else "在买区买入。")
            r.pop("prophet")
            rows.append(r)
    # one RAN_LATE row, as the real artifact had: it renders its own shelf below the
    # grid, which is also what makes entry_grid()'s slice end somewhere real.
    tail = _row("600900.SS", 0.0, status="hold", stage="RAN_LATE")
    tail.pop("prophet")
    return {"as_of": "2026-07-31", "board_definition": "cn_standout_v1",
            "buy": rows + [tail], "late_or_unfillable": [], "forming": [], "watch": [],
            "ripening": [], "ran": []}


def _ledger(prior=None):
    led = {
        "state": "accruing",
        "as_of": "2026-07-31",
        "summary": {"n_calls": 9, "first_write": "2026-07-30", "first_read_est": "2026-08-28"},
        "rows": [],
        "meta": {"board_definition": "cn_prophet_v2"},
    }
    if prior is not None:
        led["prior_record"] = prior
    return led


# Shape + label format copied from the real emitter
# (scripts/build_china_library._cn_era_label / doc["prior_record"]): the era name and its
# date span arrive JOINED by " · ", which the dialog splits back into its two header slots.
PRIOR = {
    "label_en": "previous board definition · Jun 30 – Jul 29 2026",
    "label_zh": "上一版选股口径 · 2026年6月30日–7月29日",
    "board_definition": "cn_standout_v1",
    "date_from": "2026-06-30", "date_to": "2026-07-29",
    "summary": {"win_pct": 47.5, "expectancy_pct": -0.62, "n_matured": 61, "n_logged": 65},
    "rows": [{"t": "000582.SZ", "nm": "Beibu Gulf Port / 北部湾港", "d": "2026-07-14",
              "x": 2.4, "dy": 10, "st": "beat", "m": True},
             {"t": "600519.SS", "nm": "Kweichow Moutai / 贵州茅台", "d": "2026-07-02",
              "x": -3.1, "dy": 10, "st": "lag", "m": True}],
    "meta": {"n_total": 65},
}


# ── helpers ─────────────────────────────────────────────────────────────────────────

CARD_RE = re.compile(r'<a class="pvcard ([^"]+)" href="china_lookup\.html#([^"]+)"')
# chip kind + its EN label, in emit order (the chip's first child is always the l-en span)
MARK_RE = re.compile(r'<span class="pv-mk-i pv-mk-(\w+)"[^>]*><span class="l-en">([^<]*)</span>')

# Everything that can legally follow the unified grid. The previous sentinel was the
# Jinja comment `{# /stgf-entry #}`, which the renderer STRIPS — so the helper fell back
# to "the rest of the page" and never actually excluded the RAN/LATE shelf or the depth
# lanes. Count-based assertions written against it were reading the whole board.
_GRID_END = ('<div class="stgf-grp" data-stf="ran">', '<div class="rip-shelf"',
             '<details class="cn-depth')


def entry_grid(html: str) -> str:
    """The unified live grid only (stops at the RAN/LATE shelf or the depth lanes)."""
    start = html.index('<div class="nbgrid" data-showmore-rows="3">')
    hits = [html.index(m, start) for m in _GRID_END if m in html[start:]]
    return html[start:min(hits)] if hits else html[start:]


def cards(html: str):
    return CARD_RE.findall(entry_grid(html))


def card_html(html: str, ticker: str) -> str:
    """One card's markup, by ticker (pv_card emits no nested anchor)."""
    grid = entry_grid(html)
    i = grid.index('href="china_lookup.html#%s"' % ticker)
    return grid[grid.rindex("<a class=", 0, i):grid.index("</a>", i)]


def marks_of(html: str, ticker: str):
    """[(kind, EN label), …] for one card, in EMIT order — the order the [:2] slice and
    the ≤560px one-chip CSS rule both act on."""
    return MARK_RE.findall(card_html(html, ticker))


# ── G0.2 — one grid, featured first, then score order ───────────────────────────────

def test_merged_grid_is_featured_first_then_score_desc():
    seq = [tk for _cls, tk in cards(render_board(v2_setups()))]
    assert seq == [
        # featured, in the PRODUCER's order — 88 does not jump above 70
        "601111.SS", "601222.SS", "601333.SS",
        # then every actionable row, priority score descending
        "300222.SZ", "300444.SZ", "300333.SZ", "300111.SZ",
    ], seq


def test_grid_holds_every_row_from_both_lanes():
    s = v2_setups()
    assert len(cards(render_board(s))) == len(s["buy"]) + len(s["more_actionable"]) == 7


def test_glow_class_lands_on_featured_rows_and_only_those():
    got = cards(render_board(v2_setups()))
    glowing = {tk for cls, tk in got if "pv-featured" in cls}
    assert glowing == {"601111.SS", "601222.SS", "601333.SS"}
    # full-markup idiom, not a bare token (pv_css emits the selector as literal text)
    html = render_board(v2_setups())
    assert '<a class="pvcard pv-buy pv-featured" href="china_lookup.html#601222.SS"' in html
    assert 'pv-featured" href="china_lookup.html#300222.SZ"' not in html


def test_unranked_row_sorts_last_instead_of_raising():
    s = v2_setups()
    s["more_actionable"][1]["prophet"] = {}          # score missing entirely
    s["more_actionable"][2]["prophet"] = {"score": None}
    seq = [tk for _c, tk in cards(render_board(s))]
    assert seq[-2:] == ["300222.SZ", "300333.SZ"] or set(seq[-2:]) == {"300222.SZ", "300333.SZ"}
    assert seq[3] == "300444.SZ"                     # highest surviving score leads the tail


# ── the merged rows are FULL cards, not a compact list ──────────────────────────────

def test_more_actionable_rows_render_full_cards_with_the_priority_slot():
    html = entry_grid(render_board(v2_setups()))
    # one Edge slot labelled Priority per card, on all seven
    assert html.count('<span class="pv-edl"><span class="l-en">Priority</span>'
                      '<span class="l-zh">优先级</span></span>') == 7
    # the score itself is a WHOLE number in the slot (Law 3), for a merged row
    assert '<span class="pv-edn">93</span>' in html
    assert '<span class="pv-edn">93.0</span>' not in html
    # full-card furniture the compact drawer never had
    assert html.count('<div class="pv-stp">') == 7           # lifecycle tracker
    assert html.count('<div class="pv-zn">') == 7            # zone footer
    assert html.count('<span class="pv-chip"') == 7          # verb chip


def test_merged_rows_carry_the_honest_verb_and_lifecycle_stage():
    got = dict((tk, cls) for cls, tk in cards(render_board(v2_setups())))
    # the engine's own headline for bounce_wait says "wait" — never "near"
    assert got["300222.SZ"] == "pv-wait"
    assert got["300333.SZ"] == "pv-wait"                     # extended is not a Near either
    assert got["300111.SZ"] == "pv-hold"
    assert got["601222.SS"] == "pv-buy pv-featured"


# ── G0.2 marks-row parity ───────────────────────────────────────────────────────────

def _marks(html: str):
    return re.findall(r'<div class="pv-mk">(.*?)</div>', entry_grid(html), re.S)


def test_every_merged_card_reserves_the_marks_row():
    assert len(_marks(render_board(v2_setups()))) == 7


def test_featured_and_new_chips():
    rows = _marks(render_board(v2_setups()))
    feat = [m for m in rows if "pv-mk-feat" in m]
    assert len(feat) == 3
    assert '<span class="l-en">★ Featured</span><span class="l-zh">★ 精选</span>' in feat[0]
    # NEW is recency-gated: dss 1 and 0 earn it, dss 9 does not, and a null NEVER does
    new = [m for m in rows if "pv-mk-new" in m]
    assert len(new) == 3          # 601111 (1), 601222 (0), 300333 (2)


def test_lane_chip_is_plain_words_never_a_raw_slug():
    html = entry_grid(render_board(v2_setups()))
    for en, zh in (("Turn not confirmed", "转向未确认"),
                   ("Hold — add on dips", "持有 · 逢低加仓"),
                   ("Already ran", "已经拉升"), ("Sector quota full", "该行业已满额")):
        assert (f'<span class="l-en">{en}</span><span class="l-zh">{zh}</span>') in html
    # no machine slug survives into the grid at glance tier
    assert "entry_status_" not in html
    assert "lane_reasons" not in html


def test_unknown_lane_code_falls_back_to_a_generic_chip_carrying_its_receipt():
    s = v2_setups()
    s["more_actionable"][0]["lane_reasons"] = ["some_future_gate"]
    html = entry_grid(render_board(s))
    assert '<span class="l-en">Entry not open yet</span>' in html
    assert "some_future_gate" in html          # the raw code is demoted into the hover
    assert '>some_future_gate<' not in html    # …and never rendered as visible text


def test_lane_chip_hover_is_the_rows_own_action_line():
    """The hover is the row's OWN action, per name — never a constant restated 105
    times. Exercised on the hold row, whose action line is the real engine string."""
    html = entry_grid(render_board(v2_setups()))
    assert f'data-tip-en="{HOLD_DIP_EN}" data-tip-zh="{HOLD_DIP_ZH}"' in html
    assert 'data-tip-en="Buy in the zone." data-tip-zh="在买区买入。"' in html


def test_hold_chip_never_contradicts_the_rows_own_action_line():
    """M13. `entry_status_hold` used to render a CONSTANT "No add here" chip whose own
    hover said "add on dips toward the 10-day average" — the chip and its receipt gave
    opposite instructions on all 21 hold rows in the 2026-08-02 grid. The chip now
    reads the action: add-on-dips holds say so, late-cycle holds keep the no-add wording
    (both strings come from engine/cycles.py, so this is the full hold vocabulary)."""
    dips = entry_grid(render_board(v2_setups()))
    assert ('<span class="l-en">Hold — add on dips</span>'
            '<span class="l-zh">持有 · 逢低加仓</span>') in dips
    assert "No add here" not in dips

    s = v2_setups()
    s["more_actionable"][0]["entry_signal"]["action"] = HOLD_LATE_EN
    s["more_actionable"][0]["entry_signal"]["action_zh"] = HOLD_LATE_ZH
    late = entry_grid(render_board(s))
    assert ('<span class="l-en">No add here</span>'
            '<span class="l-zh">此处不加仓</span>') in late
    assert "add on dips</span>" not in late


def test_shape_chip_uses_plain_words_and_only_the_discriminating_forms():
    html = entry_grid(render_board(v2_setups()))
    assert '<span class="l-en">Selling easing</span><span class="l-zh">抛压减弱</span>' in html
    assert '<span class="l-en">Washed out</span><span class="l-zh">洗盘充分</span>' in html
    # "Coiled" is a banned Tier-1 token (DESIGN_DOCTRINE §7 row 12) and is true of nearly
    # every row anyway — it must never reach a chip even though every fixture row has it.
    assert ">Coiled<" not in html


def test_marks_row_is_capped_at_two_chips():
    for m in _marks(render_board(v2_setups())):
        assert m.count('class="pv-mk-i') <= 2


def test_narrow_screens_show_one_mark_so_the_grid_rows_stay_aligned():
    assert "#standouts .nbgrid .pv-mk-i ~ .pv-mk-i { display:none; }" in SRC


def test_the_phone_abbreviates_the_priority_label_it_does_not_rename_it():
    """m24. Both labels are CURRENT and that is the whole answer: the card's own slot is
    'Priority' (pv_card edge_label_*), and below 680px the board swaps the text for a
    4-letter 'Rank' so a 2-up phone card keeps its ticker legible. The reference shots
    read RANK because they are phone shots — pinning the pair here so the next reviewer
    does not have to re-derive it from a screenshot."""
    assert "'edge_label_en': 'Priority', 'edge_label_zh': '优先级'" in SRC
    assert "#standouts .nbgrid[data-showmore-rows] .pv-edl::after" in SRC
    assert 'content:"Rank"' in SRC
    assert ('html[data-lang="zh"] #standouts .nbgrid[data-showmore-rows] .pv-edl::after'
            '{ content:"序"; }') in SRC


# The real 2026-08-02 row the review named: extended + fired yesterday + washed out, so
# it earns three chips and only two survive the slice — one on a phone.
CN_000983 = dict(status="extended", lane="more_actionable",
                 reasons=["entry_status_extended"], dss=1, washout=True,
                 name="Shanxi Coking Coal / 山西焦煤", sector="Energy")


def test_gate_chip_leads_the_marks_row_so_a_phone_never_drops_it():
    """M15. Emit order was feat · NEW · gate · shape, so a fresh non-featured row put
    New first — and below 560px the one-chip rule shows only the first chip. 000983.SZ
    lost "Already ran" and displayed a bare "New", which reads as encouragement on a row
    the board is holding back. The gate chip now leads on every non-featured card."""
    s = v2_setups()
    s["more_actionable"] = s["more_actionable"] + [_row("000983.SZ", 46.9, **CN_000983)]
    html = render_board(s)
    got = marks_of(html, "000983.SZ")
    assert [k for k, _lbl in got] == ["lane", "new"], got
    assert got[0][1] == "Already ran"        # the chip the phone keeps
    # a featured row has no gate chip, so its rank mark still leads
    assert marks_of(html, "601222.SS")[0] == ("feat", "★ Featured")
    # …and this only matters because of the CSS rule that drops the rest
    assert "#standouts .nbgrid .pv-mk-i ~ .pv-mk-i { display:none; }" in SRC


# ── the old drawer is gone; the other depth lanes are not ───────────────────────────

def test_more_live_setups_depth_block_is_deleted():
    html = render_board(v2_setups())
    assert "More live setups" not in html
    assert "更多实时形态" not in html
    assert '<details class="cn-depth" data-stf="entry">' not in html


def test_the_other_depth_lanes_are_untouched():
    html = render_board(v2_setups())
    assert '<details class="cn-depth late" data-stf="ran">' in html
    assert "Wait / unfillable / do not chase" in html
    assert '<details class="cn-depth forming" data-stf="early">' in html
    assert "Early warnings — not confirmed" in html
    # …and they still use the compact grid, not full cards
    assert '<a class="cn-depth-card" href="china_lookup.html#600999.SS">' in html
    assert '<a class="cn-depth-card" href="china_lookup.html#002888.SZ">' in html


def test_legacy_watch_lane_still_collapses_when_no_v2_lane_exists():
    s = v2_setups(more_actionable=[], late_or_unfillable=[], forming=[],
                  watch=[_row("000111.SZ", 20.0, lane="watch")])
    html = render_board(s)
    assert "Legacy depth — classification pending" in html


# ── facet counts ────────────────────────────────────────────────────────────────────

def test_live_signal_facet_count_still_sums_both_lanes_and_now_matches_the_grid():
    html = render_board(v2_setups())
    n = re.search(r'data-facet="entry".*?<span class="stgf-n">(\d+)</span>', html, re.S)
    assert n and n.group(1) == "7"
    assert len(cards(html)) == 7      # the chip and the grid can never disagree again


def test_grid_key_line_states_the_two_axis_rule_once():
    html = render_board(v2_setups())
    assert html.count('<p class="cn-gridkey">') == 1
    assert "Glowing = act today." in html
    assert "发光卡＝今天可动手。" in html


def _words(text: str) -> int:
    return len([w for w in text.split() if re.search(r"[0-9A-Za-z]", w)])


def test_tier_1_and_tier_2_copy_stay_inside_their_word_budgets():
    """DESIGN_DOCTRINE §1: a Tier-1 subtitle is ≤14 words, a Tier-2 tip ≤ ~80. The key
    line sits above 111 cards and the h2 `?` carries the two-axis receipt; both are the
    kind of copy that grows a clause per review round if nothing counts it."""
    key = re.search(r'<p class="cn-gridkey">.*?l-en">([^<]*)</span>',
                    render_board(v2_setups()), re.S)
    assert key and _words(key.group(1)) <= 14, key and key.group(1)
    tip = SRC[SRC.index('help("Two things decide') + 6:]
    assert _words(tip[:tip.index('", "')]) <= 80


# ── fail-soft: a pre-v2 artifact renders the legacy shelf ───────────────────────────

def test_pre_v2_artifact_gets_no_glow_no_marks_and_the_pre_merge_title():
    html = render_board(prev2_setups())
    got = cards(html)
    # producer order, untouched — no score re-sort on the legacy path
    assert [tk for _c, tk in got] == ["6000%02d.SS" % i for i in range(1, 12)]
    assert not [c for c, _tk in got if "pv-featured" in c]     # no glow anywhere
    assert '<div class="pv-mk">' not in entry_grid(html)       # no marks row at all
    assert '<p class="cn-gridkey">' not in html
    assert "⚡ China Prophet — Featured Entries" in html
    assert "⚡ China Prophet — Live Board" not in html


def test_pre_v2_verbs_follow_the_legacy_map_not_the_merged_one():
    """THE pre-v2 regression (B1). `_is_feat` is set FROM `_cn_v2`, so on a pre-v2
    artifact no row is featured — and gating the new status→verb map on `_is_feat` alone
    sent every legacy row down it. Measured on the real artifact: 78 of 104 entry cards
    flipped pv-near → pv-wait. bounce_wait is a NEAR on this path, and pv-wait cannot
    appear in the grid at all, because origin/main's expression has no branch that
    produces one."""
    hist = collections.Counter(cls for cls, _tk in cards(render_board(prev2_setups())))
    assert hist == collections.Counter(
        {"pv-near": 6, "pv-hold": 3, "pv-buy": 2}), hist
    assert "pv-wait" not in hist
    # the same statement per status, so a future map edit names the row it broke
    seq = [cls for cls, _tk in cards(render_board(prev2_setups()))]
    expect = [PREV2_VERB[s] for s, n in PREV2_MIX for _ in range(n)]
    assert seq == expect, list(zip(seq, expect))


def test_pre_v2_lifecycle_stage_is_pinned_at_ready_on_every_card():
    """main hard-codes stage 3. The merged map moves bounce_wait to Turning and hold to
    Trend — correct for a v2 row, a silent re-style of 90 of 110 legacy ones."""
    grid = entry_grid(render_board(prev2_setups()))
    assert grid.count('<span class="on"><span class="l-en">Ready</span>') == 11
    for other in ("Bottoming", "Turning", "Trend"):
        assert '<span class="on"><span class="l-en">%s</span>' % other not in grid


def test_pre_v2_edge_slot_falls_back_to_the_conviction_score_unrounded():
    """The '%.0f' whole-number Priority is a v2 decision. On the legacy path the raw
    value is passed through exactly as the pre-merge template did."""
    grid = entry_grid(render_board(prev2_setups()))
    assert '<span class="pv-edn">61.5</span>' in grid       # fractional, NOT rounded
    assert '<span class="pv-edn">62</span>' not in grid
    assert grid.count('<span class="pv-edn">60</span>') == 10


def test_v2_gate_survives_an_empty_more_actionable_lane():
    """A v2 night that gates everything out is still v2 — the ranking block says so."""
    html = render_board(v2_setups(more_actionable=[]))
    assert "⚡ China Prophet — Live Board" in html
    assert '<a class="pvcard pv-buy pv-featured" href="china_lookup.html#601222.SS"' in html
    # …but the key line needs both cohorts to have anything to explain
    assert '<p class="cn-gridkey">' not in html


# ── G5 — prior-definition continuity in the track-record dialog ─────────────────────

def test_prior_record_section_renders_below_the_live_record():
    html = render_dialog({"board_definition": "cn_prophet_v2", "as_of": "2026-07-31",
                          "track_ledger": _ledger(PRIOR)})
    assert '<div class="trd-stg trd-stg-3 trd-prior">' in html
    assert html.index('id="trd-tbl-mount"') < html.index('class="trd-stg trd-stg-3 trd-prior"')
    # the era NAME lands in the pill, its SPAN in the muted slot beside it — never both
    assert ('<span class="l-en">previous board definition</span>'
            '<span class="l-zh">上一版选股口径</span>') in html
    assert '<span class="l-en">Jun 30 – Jul 29 2026</span>' in html
    assert '<span class="l-zh">2026年6月30日–7月29日</span>' in html
    assert html.count("Jun 30 – Jul 29 2026") == 1        # not double-printed


def test_prior_record_states_the_non_pooling_rule_in_words():
    html = render_dialog({"board_definition": "cn_prophet_v2", "as_of": "2026-07-31",
                          "track_ledger": _ledger(PRIOR)})
    assert "never added to the record above" in html
    assert "绝不并入上方记录" in html
    assert "<b>48%</b> of 61 finished trades" in html


def test_prior_record_never_gets_the_headline_number_treatment():
    """Non-pooling is enforced by LAYOUT too: the 26px verdict cards stay the live
    definition's alone, so a reader can never read the closed book as the desk's stat."""
    html = render_dialog({"board_definition": "cn_prophet_v2", "as_of": "2026-07-31",
                          "track_ledger": _ledger(PRIOR)})
    prior = html[html.index('class="trd-stg trd-stg-3 trd-prior"'):]
    assert '<div class="trd-card-v' not in prior
    assert '<div class="trd-cards">' not in prior


def test_prior_record_rows_render_in_the_dialog_table_idiom():
    html = render_dialog({"board_definition": "cn_prophet_v2", "as_of": "2026-07-31",
                          "track_ledger": _ledger(PRIOR)})
    prior = html[html.index('class="trd-stg trd-stg-3 trd-prior"'):]
    assert '<table class="trd-tbl">' in prior
    assert '<td class="trd-tk">000582.SZ' in prior
    assert '<span class="trd-dot trd-dot-up"></span>' in prior      # beat
    assert '<span class="trd-dot trd-dot-dn"></span>' in prior      # lagged
    assert "+2.4%" in prior and "-3.1%" in prior


def test_prior_record_caps_its_row_list_and_says_so():
    big = dict(PRIOR)
    big["rows"] = [{"t": f"{600000 + i}.SS", "nm": "X / X", "d": "2026-07-%02d" % (i % 28 + 1),
                    "x": 1.0, "dy": 10, "st": "beat", "m": True} for i in range(40)]
    html = render_dialog({"board_definition": "cn_prophet_v2", "as_of": "2026-07-31",
                          "track_ledger": _ledger(big)})
    prior = html[html.index('class="trd-stg trd-stg-3 trd-prior"'):]
    assert prior.count('<td class="trd-tk">') == 25
    # STALE PIN REPAIRED (was "Showing the 25 most recent of 40."): the dialog no longer
    # keeps the NEWEST 25 — it keeps the finished trades first (_track_record_dlg.html.j2
    # "WHICH 25"), and the total it discloses is the era's own logged count (meta.n_total
    # = 65 here), not the length of the row list it was handed.
    assert "Showing 25 of 65 — finished trades first." in prior


def test_prior_record_absent_leaves_the_dialog_untouched():
    setups = {"board_definition": "cn_prophet_v2", "as_of": "2026-07-31",
              "track_ledger": _ledger()}
    html = render_dialog(setups)
    assert '<div class="trd-stg trd-stg-3 trd-prior">' not in html
    assert "Previous board definition" not in html
    assert "前版榜单定义" not in html
    # the live record above is completely unaffected by the optional key
    with_prior = render_dialog({**setups, "track_ledger": _ledger(PRIOR)})
    head = 'class="trd-stg trd-stg-3 trd-prior"'
    assert with_prior[:with_prior.index(head)].startswith(html[:200])


def test_prior_record_with_no_scored_summary_says_so_instead_of_printing_nulls():
    unscored = dict(PRIOR, summary={"n_logged": 12})
    html = render_dialog({"board_definition": "cn_prophet_v2", "as_of": "2026-07-31",
                          "track_ledger": _ledger(unscored)})
    assert "too few of them finished to score" in html
    assert "None%" not in html and "—%" not in html


# ── house rules that must survive both changes ──────────────────────────────────────

def test_no_cjk_inside_a_title_attribute_anywhere_in_the_touched_blocks():
    for html in (render_board(v2_setups()),
                 render_dialog({"board_definition": "cn_prophet_v2", "as_of": "2026-07-31",
                                "track_ledger": _ledger(PRIOR)})):
        for attr in re.findall(r'\stitle="([^"]*)"', html):
            assert not re.search(r"[一-鿿]", attr), attr


def test_the_cn_grid_key_dot_is_never_pinned_to_the_language_flipping_tokens():
    """SCOPE: the CN grid-key dot only — the one glow-coloured element this template
    owns. `--up`/`--down` swap red/green under html[data-lang="zh"], so a key bullet on
    --up would print a RED dot next to "glowing = act today" for a Chinese reader. The
    card's own aura lives in templates/_prophet_card.html.j2 and is pinned by the
    prophet-card suite, not here; this file cannot see a change to it."""
    key = SRC[SRC.index(".cn-gridkey-dot {"):SRC.index(".cn-gridkey-dot {") + 400]
    assert "var(--pv-buy)" in key
    assert "var(--up)" not in key


@pytest.mark.parametrize("banned", ["证伪", "falsifier", "thesis refuted"])
def test_no_refutation_language_reaches_this_surface(banned):
    assert banned not in render_board(v2_setups())
