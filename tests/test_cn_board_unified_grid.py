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
    pre-merge template was verified once at build time by diffing both renders of the
    same fixture; a git-pinned diff cannot live in CI (HEAD moves), so what this suite
    pins forward is every observable half of it: producer order preserved, no glow, no
    marks row, no key line, the conviction-score fallback in the Edge slot, and the
    pre-merge panel title.
  * The track-record dialog grows a "previous board definition" section when the ledger
    carries `prior_record`, and is unchanged when it does not.

GOTCHA inherited from tests/test_china_stocks_w1c_render.py: pv_css() emits the class
SELECTORS as literal text, so bare substrings like "pv-featured" are ALWAYS present in
the output. Every card assertion here targets the full element-class string
(`class="pvcard pv-buy pv-featured"`), never a bare token.
"""
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
         star=False, washout=False, name=None, sector="Technology"):
    return {
        "ticker": ticker,
        "name": name or f"{ticker} Holdings / {ticker}控股",
        "sector": sector,
        "stage": "ENTRY",
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
        "conviction": {"score": 60, "verdict": "Buy zone", "verdict_zh": "买区",
                       "cautions": None, "cautions_zh": None},
        "entry_signal": {"status": status, "headline": "Ready", "headline_zh": "就绪",
                         "action": "Buy in the zone.", "action_zh": "在买区买入。",
                         "buy_zone": {"low": 11.0, "high": 12.5}},
    }


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
            _row("300111.SZ", 61.0, status="hold", lane="more_actionable",
                 reasons=["entry_status_hold"]),
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


def prev2_setups():
    """A pre-v2 artifact: no more_actionable lane, no ranking block, no prophet score."""
    rows = []
    for r in v2_setups()["buy"]:
        r = dict(r)
        r.pop("prophet")
        rows.append(r)
    return {"as_of": "2026-07-31", "board_definition": "cn_standout_v1",
            "buy": rows, "late_or_unfillable": [], "forming": [], "watch": [],
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


def entry_grid(html: str) -> str:
    """The unified live grid only (stops at the RAN/LATE shelf or the depth lanes)."""
    start = html.index('<div class="nbgrid" data-showmore-rows="3">')
    tail = html.index("{# /stgf-entry #}") if "{# /stgf-entry #}" in html else len(html)
    return html[start:tail]


def cards(html: str):
    return CARD_RE.findall(entry_grid(html))


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
    for en, zh in (("Turn not confirmed", "转向未确认"), ("No add here", "此处不加仓"),
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
    html = entry_grid(render_board(v2_setups()))
    assert 'data-tip-en="Buy in the zone." data-tip-zh="在买区买入。"' in html


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


# ── fail-soft: a pre-v2 artifact renders the legacy shelf ───────────────────────────

def test_pre_v2_artifact_gets_no_glow_no_marks_and_the_pre_merge_title():
    html = render_board(prev2_setups())
    got = cards(html)
    assert [tk for _c, tk in got] == ["601111.SS", "601222.SS", "601333.SS"]
    assert all(cls == "pv-buy" for cls, _tk in got)            # no pv-featured anywhere
    assert '<div class="pv-mk">' not in entry_grid(html)       # no marks row at all
    assert '<p class="cn-gridkey">' not in html
    assert "⚡ China Prophet — Featured Entries" in html
    assert "⚡ China Prophet — Live Board" not in html


def test_pre_v2_edge_slot_falls_back_to_the_conviction_score():
    html = entry_grid(render_board(prev2_setups()))
    assert html.count('<span class="pv-edn">60</span>') == 3


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
    assert "Showing the 25 most recent of 40." in prior


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


def test_the_featured_glow_is_never_pinned_to_the_language_flipping_tokens():
    """--up/--down swap red/green under html[data-lang="zh"]; the CN key dot and the
    card glow must both stay on --pv-buy or a Chinese reader sees a red 'buy'."""
    key = SRC[SRC.index(".cn-gridkey-dot {"):SRC.index(".cn-gridkey-dot {") + 400]
    assert "var(--pv-buy)" in key
    assert "var(--up)" not in key


@pytest.mark.parametrize("banned", ["证伪", "falsifier", "thesis refuted"])
def test_no_refutation_language_reaches_this_surface(banned):
    assert banned not in render_board(v2_setups())
