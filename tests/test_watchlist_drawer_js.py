"""tests/test_watchlist_drawer_js.py — the W4 per-ticker Intelligence Drawer.

W4 composes a per-name drawer out of artifacts that already exist. The composer is
`templates/watchlist_risk.js` (gated — it never reaches an anonymous visitor); the two
callers are `templates/portfolio.js` (holdings) and `templates/watchlist.js` (watchlist).

What this file pins is the class of defect a drawer is uniquely good at hiding: a
section that renders NOTHING and a section that has nothing to report are the same
pixels, and only one of them is information. Every gate below exists because the
failure it catches would look like success in a screenshot.

  1. HONEST ABSENCE, as a mechanism. Every section builder is run over an EMPTY payload
     and must return a row that names what is missing. A builder that returns '' would
     silently shorten the drawer, and the reviewer would see a clean drawer rather than
     a missing one. This is the gate the wave's "no fabricated values, no silent
     empties" acceptance row cashes out to.
  2. NO FABRICATION on the same empty payload — an absent section may not print a figure.
  3. ATTRIBUTE ESCAPING in the row painter. Tips ride `data-tip-en="…"`; a read carrying
     a quote used to break OUT of the attribute rather than print a stray tag, which is
     a silent failure in exactly the slot where nobody looks.
  4. The STANCE precedence, and that its three words are byte-identical to the copy
     portfolio.js holds — one vocabulary living in two files across the gate boundary.
  5. GLANCE-TIER VOCABULARY. Tier 1 may not carry ENB / MCTR / WRI / lane / study names.
  6. The DOSSIER ROUTE. `stock.html` reads `location.hash` only; the shipped watchlist
     drawer linked `stock.html?t=<T>`, which is a 200 that opens an empty dossier — a
     dead link no link checker can see.
  7. The ANONYMOUS drawer: a lock shell, and zero gated reads.
  8. `entry_signal.action` — an engine string written as an instruction ("take a half
     position here") — never reaches a holdings surface.
  9. The W3 residual: the falling-days claim may not assert a change while printing the
     same number twice.

Same harness as its three sibling suites: these modules are browser IIFEs, node-shelled
behind minimal window/document stubs with readyState 'loading' so init() never runs.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")


def test_node_is_present_when_this_runs_on_ci():
    """A SKIP is not a PASS, and on CI it is indistinguishable from one.

    Every node-shelled test in this file carries `@needs_node`, so with node off PATH
    35 of the 45 skip silently, 10 pass, pytest exits 0 and the workflow step turns
    green having proved nothing — while the job's own comment claims the suite "skips
    loudly". Loudly is this: on CI, a missing node is a FAILURE."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        assert HAS_NODE, (
            "node is not on PATH and this suite is node-shelled — every browser-module "
            "test would SKIP and the step would green. Fix the runner, do not skip.")

ROOT = Path(__file__).resolve().parents[1]
WRISK = ROOT / "templates" / "watchlist_risk.js"
WATCHLIST = ROOT / "templates" / "watchlist.js"
PORTFOLIO = ROOT / "templates" / "portfolio.js"
TEMPLATE = ROOT / "templates" / "watchlist.html.j2"

# the pack this suite runs in; pinned against the workflow at the bottom of this file
PACK_DEPS = {"pytest", "pandas", "numpy", "pyarrow", "yaml"}

SHIM = """
var __lang = LANG;
var __store = {};
global.localStorage = {
  getItem: function (k) {
    return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null;
  },
  setItem: function (k, v) { __store[k] = String(v); },
  removeItem: function (k) { delete __store[k]; }
};
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
global.document = {
  readyState: 'loading',
  documentElement: {
    getAttribute: function (a) { return a === 'data-lang' ? __lang : null; },
    setAttribute: function () {},
    classList: { add: function () {}, remove: function () {} }
  },
  getElementById: function () { return null; },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  addEventListener: function () {},
  removeEventListener: function () {},
  dispatchEvent: function () { return true; },
  createElement: function () { return { style: {}, classList: { add: function () {} } }; }
};
global.window = global;
global.window.addEventListener = function () {};
global.location = { hash: '', pathname: '/watchlist.html', search: '', origin: 'https://x' };
function OUT(o) { process.stdout.write(JSON.stringify(o)); }
"""


def _run(js_body: str, extra: dict | None = None, lang: str = "en") -> dict:
    globs = "\n".join("var %s = %s;" % (k, json.dumps(v)) for k, v in (extra or {}).items())
    script = ("var LANG = %s;\n" % json.dumps(lang)) + SHIM + "\n" + globs + "\n" + textwrap.dedent(js_body)
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


def _wr(js_body: str, extra: dict | None = None, lang: str = "en") -> dict:
    return _run("var WR = require(%s);\n%s" % (json.dumps(str(WRISK)), js_body), extra, lang)


# the six W4 sections, by their exported builder name. `role` is the one fed from book
# state rather than the per-name JSON, so its empty case is a different call shape.
# `chainSection` is here and `chainRows` is not, deliberately: the drawer's transmission
# row must obey the never-empty invariant like every other section, while the RAIL's
# `chainRows` keeps the old contract where '' means "draw nothing here".
JSON_SECTIONS = ["optionsRow", "macroRow", "themeRow", "ownersRow", "notesRow",
                 "chainSection"]

# a real payload shape, trimmed to the fields each builder reads. Values are taken from
# site/stockdata/AAPL.json so the "present" branch is exercised against the real schema
# rather than a shape invented to match the code.
FULL = {
    "ticker": "AAPL",
    "sector": "Technology",
    "asof": "2026-07-01",
    "tech": {"above200": True, "above50": True, "off_52w_high_pct": -4.0, "pct_vs_200dma": 8.1},
    "entry_signal": {"status": "await_confluence",
                     "headline": "Cycle turn — awaiting confluence cross",
                     "headline_zh": "周期拐点 — 等待共振交叉确认",
                     "action": "take a half position here, or wait for the weekly to turn.",
                     "action_zh": "可在此建半仓，或等待周线转向。"},
    "earnings": {"next_date": "2026-08-27", "next_time": "after-hours", "sue_z": 0.4},
    "revisions": {"breadth": 0.72, "est_chg_30d": 1.2, "n_analysts": 41},
    "financials": {"debt_to_assets": 0.28, "fcf_margin": 0.24},
    "accounting_quality": {"verdict": "ok", "n_caution": 0},
    "positioning": {"short": {"pct_float": 1.06}, "short_flow": {"trend_pp": -4.44},
                    "insider": {"n_sellers": 5, "n_buyers": 0, "cluster": True,
                                "quarter": "6mo to 2026-03"}},
    "smart_money": {"n_holders": 4, "n_buying": 1, "n_selling": 0, "as_of": "2026-03-31"},
    "macro_sensitivity": {"tier": "low", "rate_beta": -0.157, "regime": "neutral",
                          "duration_label": {"en": "Duration-neutral", "zh": "久期中性"},
                          "inflation_label": {"en": "Inflation-neutral", "zh": "通胀中性"},
                          "headline": {"en": "Rate risk runs through its market beta.",
                                       "zh": "其利率风险通过市场beta体现。"},
                          "detail": {"en": "Own orthogonal rate beta -0.16.", "zh": "自身正交利率 beta -0.16。"},
                          "caveat": {"en": "Single-name secondary.", "zh": "单只股票为次要口径。"}},
    "gex": {"gamma_regime": "long", "call_wall": 310.0, "put_wall": 275.0, "opex_days": 15},
    "gex_confirm": {"verdict": "caution", "score": -1.5,
                    "label": "Options caution", "label_zh": "期权警示",
                    "reasons": [{"en": "deep long-gamma", "zh": "深度多头 Gamma", "tone": "caution"}]},
    "iv_spread_confirm": {"verdict": "neutral", "ivspread": 0.01519},
    "baskets_membership": [{"slug": "mag7", "name": "Magnificent Seven", "name_zh": "七巨头"},
                           {"slug": "us_sector_tech", "name": "Technology (Equal-Weight)",
                            "name_zh": "信息技术（等权）"}],
    "alerts": {"n_recent": 29, "n_total": 3607,
               "pinned": {"headline": "DOWNTREND → BOTTOMING", "headline_zh": "下跌趋势 → 筑底中",
                          "detail": "BUY SETUP.", "detail_zh": "买入预备。"},
               "timeline": [{"daylabel": "Jun 29, 2026", "daylabel_zh": "2026年6月29日", "events": []}]},
}



def _rs_text(html: str) -> str:
    """The reads only — the `.rs` cell of every row, tags stripped."""
    return " ".join(re.findall(r'<span class="rs">(.*?)</span>', html, re.S))


# ===========================================================================
# 1. HONEST ABSENCE — the gate this whole wave turns on
# ===========================================================================
@needs_node
@pytest.mark.parametrize("builder", JSON_SECTIONS)
@pytest.mark.parametrize("payload", [{}, None], ids=["empty", "null"])
def test_every_section_speaks_when_it_has_nothing_to_say(builder, payload):
    """A section with no data must SAY so. Returning '' would shorten the drawer, and a
    shorter drawer and a quieter one are the same screenshot.

    MUTATION CHECK: make any of the five builders `return ''` on its absent branch and
    this reds — which is the whole point, because nothing else would."""
    out = _wr("OUT({html: WR.%s(P)});" % builder, {"P": payload})
    html = out["html"]
    assert html.strip(), "%s returned nothing for an absent payload" % builder
    assert 'class="wri-lrow"' in html, "%s did not emit a row" % builder
    read = _rs_text(html)
    assert read.strip(), "%s emitted a row with an EMPTY read" % builder
    # The absence must be MARKED as one, not dressed as an OK — in any of the three
    # marks m8 separated: `na` (we could not read it), `none` (we read it; the answer is
    # none), `n/app` (the dimension does not apply here). What is barred is `ok`.
    marks = ['class="st na"', 'class="st none"', 'class="st n/app"']
    assert any(m in html for m in marks), \
        "%s did not mark itself not-covered" % builder
    assert 'class="st ok"' not in html, "%s dressed an absence as OK" % builder


@needs_node
def test_the_three_coverage_meanings_render_three_different_marks():
    """Nulls-printed separates "we did not measure" from "we measured; the answer is no",
    and one shared `n/a` erased that distinction across the whole drawer.

      na    — a coverage gap. We could not read it; this is NOT an all-clear.
      none  — evaluated, and the answer is none (Transmission: in no armed chain).
      n/app — the dimension does not apply to this row (a watchlist name has no weight).

    MUTATION CHECK: map any two of them onto the same token and this reds. The
    honest-absence sweep does NOT catch that — it asserts a row is marked as
    not-affirmative, which all three still are."""
    out = _wr("OUT({na: WR.optionsRow({}), none: WR.chainSection(null), "
              "napp: WR.roleRow({inBook:false}), "
              "tokens: [WR.lrowHTML({lab:{en:'x',zh:'x'},state:'na',en:'a',zh:'a'}),"
              " WR.lrowHTML({lab:{en:'x',zh:'x'},state:'none',en:'a',zh:'a'}),"
              " WR.lrowHTML({lab:{en:'x',zh:'x'},state:'n/app',en:'a',zh:'a'})]});")
    assert 'class="st na"' in out["na"]
    assert 'class="st none"' in out["none"]
    assert 'class="st n/app"' in out["napp"]

    def token(html):
        import re as _re
        m = _re.search(r'<span class="st [^"]*">(.*?)</span>', html, _re.S)
        return _re.sub(r"<[^>]+>", "|", m.group(1)) if m else None

    marks = [token(h) for h in out["tokens"]]
    assert len(set(marks)) == 3, \
        "three different coverage meanings render as %r — the distinction is gone" % marks
    # and the template styles each of them
    css = TEMPLATE.read_text()
    for cls in (".wri-lrow .st.na", ".wri-lrow .st.none", ".wri-lrow .st.n\\/app"):
        assert cls in css, "%s is emitted and styled nowhere" % cls


@needs_node
def test_the_portfolio_role_section_speaks_for_a_watchlist_name():
    """A watchlist name has no weight and no risk share. That is the ANSWER, not a gap:
    the row says it is being watched rather than held."""
    out = _wr("OUT({html: WR.roleRow({inBook:false})});")
    html = out["html"]
    assert 'class="wri-lrow"' in html and _rs_text(html).strip()
    assert "watchlist" in html, "the not-a-position case must say why there is no weight"
    assert "%" not in _rs_text(html), "a watchlist name must not be given a weight"


@needs_node
def test_the_whole_tier_two_composition_is_never_blank_on_an_empty_payload():
    """The composition of fifteen rows is still fifteen rows, thirteen of them carrying
    the honest-absence mark, when there is nothing behind any of them."""
    out = _wr("OUT({html: WR.intelSections('AAPL', {}, {inBook:true})});")
    html = out["html"]
    assert html.count('class="wri-lrow"') >= 12, html.count('class="wri-lrow"')
    # every W4 section label is present even though nothing was readable
    labels = _wr("OUT(WR.W4_LABEL);")
    for key, lab in labels.items():
        assert lab["en"] in html, "section %s vanished on an empty payload" % key


@needs_node
def test_no_section_invents_a_figure_when_it_has_no_data():
    """`.fig` is the mono-numeral span. On an empty payload there is nothing to put in
    one, so any occurrence is a fabricated value."""
    out = _wr("OUT({html: WR.intelSections('AAPL', {}, {inBook:true})});")
    assert 'class="fig"' not in out["html"], "a figure was printed with no data behind it"


@needs_node
def test_a_partial_payload_degrades_section_by_section_not_drawer_by_drawer():
    """One lane failing degrades ONE section. A name with an options plane and no
    ownership filings gets a real options read AND an honest ownership line."""
    partial = {"gex": FULL["gex"], "gex_confirm": FULL["gex_confirm"], "sector": "Technology"}
    out = _wr("OUT({opt: WR.optionsRow(P), own: WR.ownersRow(P), thm: WR.themeRow(P)});",
              {"P": partial})
    assert 'class="st na"' not in out["opt"], "the options read was real and should not be n/a"
    assert "310" in out["opt"], "the real ceiling level did not render"
    assert 'class="st na"' in out["own"], "ownership had no filings and did not say so"
    assert "filings" in out["own"]
    assert 'class="st na"' not in out["thm"], "the sector was known"


@needs_node
def test_the_full_payload_renders_every_section_for_real():
    """The other half of the honesty gate: a name with data must not render the absent
    branch. A drawer that always says 'not covered' also always passes gate 1."""
    out = _wr(
        "OUT({opt: WR.optionsRow(P), mac: WR.macroRow(P), thm: WR.themeRow(P),"
        " own: WR.ownersRow(P), nts: WR.notesRow(P)});", {"P": FULL})
    for key, html in out.items():
        assert 'class="st na"' not in html, "%s rendered its absent branch on a FULL payload" % key
        assert _rs_text(html).strip()
    assert "310" in out["opt"] and "275" in out["opt"]
    assert "Rate risk runs through its market beta." in out["mac"]
    assert "Magnificent Seven" in out["thm"]
    assert "29" in out["nts"]


@needs_node
def test_sections_render_their_chinese_on_a_full_payload():
    """zh copy lives in the builder, not only the template. Both halves ship in the DOM
    (`.l-en` / `.l-zh`); the zh half must not silently fall back to the English."""
    out = _wr("OUT({thm: WR.themeRow(P), own: WR.ownersRow(P), mac: WR.macroRow(P)});",
              {"P": FULL}, lang="zh")
    assert "七巨头" in out["thm"]
    assert "内部人" in out["own"]
    assert "其利率风险通过市场beta体现。" in out["mac"]


# ===========================================================================
# 2. the row painter — the attribute slot where a mistake is SILENT
# ===========================================================================
@needs_node
def test_a_tip_carrying_a_quote_cannot_break_out_of_its_attribute():
    """`data-tip-en="…"`. A read carrying `"` used to end the attribute and turn the
    rest of the sentence into markup — no stray tag, no visible symptom.

    MUTATION CHECK: drop the `esc()` around `tip.en` in `lrowHTML` and this reds."""
    evil = 'he said "buy" <script>x</script> & more'
    out = _wr("OUT({html: WR.lrowHTML({lab:{en:'L',zh:'L'}, tip:{en:T,zh:T}, en:'r', zh:'r'})});",
              {"T": evil})
    html = out["html"]
    assert "&quot;" in html and "&lt;script&gt;" in html
    assert '<script>' not in html
    # exactly one attribute pair survived — a breakout would have created more
    assert html.count('data-tip-en="') == 1 and html.count('data-tip-zh="') == 1


@needs_node
def test_a_stateless_row_still_emits_its_state_CELL():
    """`.wri-lrow` is a three-column grid (`116px 74px 1fr`). Omitting the middle cell
    drops the read into the state column — which is what the shipped drawer did to its
    Stage and Extension rows.

    MUTATION CHECK: make `lrowHTML` return '' instead of `<span class="st"></span>` for
    a falsy state and this reds."""
    out = _wr("OUT({html: WR.lrowHTML({lab:{en:'L',zh:'L'}, state:'', en:'r', zh:'r'})});")
    assert '<span class="st"></span>' in out["html"]
    out2 = _wr("OUT({html: WR.lrowHTML({lab:{en:'L',zh:'L'}, state:'watch', en:'r', zh:'r'})});")
    assert 'class="st watch"' in out2["html"]


@needs_node
def test_the_chain_row_tips_are_not_double_escaped():
    """The chain rows moved onto the shared painter, which now owns attribute escaping.
    Leaving their own `esc()` calls in place would print `&amp;quot;` in the tooltip."""
    memberships = [{"id": "dollar_up", "label": {"en": "Dollar", "zh": "美元"}, "state": "propagating",
                    "links_confirmed": 2, "n_hops": 4, "channel": "fx",
                    "channel_label": {"en": "FX revenue", "zh": "外汇收入"}, "channel_n": 12}]
    out = _wr("OUT({html: WR.chainDrawerRows(M)});", {"M": memberships})
    assert "&amp;" not in out["html"], "a tip was escaped twice"
    assert 'class="wri-lrow"' in out["html"] and 'data-tip-en="' in out["html"]


# ===========================================================================
# 3. the stance — one vocabulary, two files, one precedence
# ===========================================================================
@needs_node
@pytest.mark.parametrize(
    "lanes,role,expect",
    [
        # nothing on any lane and no badge -> nothing needs a decision
        ({}, None, "none"),
        # the ladder's SEVERE rungs -> Watch. These are the two the role ladder itself
        # grades above plain review (exit_review / trim_review), and using its own
        # grading is what stops Watch from being a constant.
        ({}, {"kind": "exit"}, "watch"),
        ({}, {"kind": "trim"}, "watch"),
        # the ladder's BOTTOM rung is not the top tier. It fires on 26% of the library
        # by itself; promoting it to Watch is what made Watch 93.5%.
        ({}, {"kind": "review"}, "ready"),
        # a lane signal with no badge at all -> Get ready
        ({"price_trend": "elev"}, None, "ready"),
        ({"stretch": "watch"}, None, "ready"),
        ({"events": "elev"}, None, "ready"),
        # a severe badge outranks everything below it
        ({"price_trend": "elev", "balance": "elev"}, {"kind": "exit"}, "watch"),
    ],
)
def test_the_stance_precedence_uses_the_role_ladders_own_grading(lanes, role, expect):
    """MUTATION CHECK: collapse the two branches back to `if (role) return 'watch'` and
    the `{"kind": "review"} -> ready` case reds — which is the exact flattening that
    measured 93.5% Watch across the production library."""
    built = {k: {"state": "ok"} for k in
             ["price_trend", "stretch", "events", "estimates", "balance", "selling", "rates"]}
    for k, st in lanes.items():
        built[k] = {"state": st}
    out = _wr("OUT({s: WR.intelStance(L, R)});", {"L": built, "R": role})
    assert out["s"] == expect


@needs_node
def test_an_overextended_name_is_never_told_nothing_needs_a_decision():
    """The stretch oracles disagree, and the drawer must not resolve that in the
    reader's disfavour.

    Two fields answer "is it stretched": `ladder.alignment.overextended` and
    `entry_signal.status === 'extended'`. The ladder flags a name the entry status calls
    clean on 607 of 1,629 (37.3%) — RIVN is exactly this shape (overextended, status
    `buy_now`) — and because the stance reads the LANE, those names could render
    "No action / Nothing here needs a decision today." over a position the other oracle
    calls overextended.

    The floor is a one-way clamp on the all-clear branch only: it can raise attention,
    never lower it, and it deliberately does NOT touch Get ready (clamping every tier
    moved 549 names and put Watch back to 83.7%, undoing the previous round's partition).

    MUTATION CHECK: drop the `flags && flags.overextended` clamp and this reds."""
    quiet = {k: {"state": "ok"} for k in
             ["price_trend", "stretch", "events", "estimates", "balance", "selling", "rates"]}
    out = _wr("OUT({plain: WR.intelStance(L, null), "
              "floored: WR.intelStance(L, null, {overextended:true}), "
              "flag: WR.overextendedFlag(J), "
              "ready: WR.intelStance(L2, null, {overextended:true})});",
              {"L": quiet, "L2": dict(quiet, stretch={"state": "watch"}),
               "J": {"ladder": {"alignment": {"overextended": True}}}})
    assert out["plain"] == "none", "the fixture is not the all-clear case"
    assert out["floored"] == "watch", "an overextended name was told nothing needs a decision"
    assert out["flag"] is True
    # and the clamp is scoped: a name already carrying attention is not escalated
    assert out["ready"] == "ready", "the floor escalated a tier it should not touch"


@needs_node
def test_the_two_stretch_oracles_do_not_contradict_each_other_in_one_vocabulary():
    """One English word may not name two measurements. The distance row and the entry
    stretch lane are different oracles, so the distance row talks about DISTANCE and does
    not reuse "stretched" — otherwise the drawer renders "Stretched" eight rows above
    "not stretched", which in ZH was a flat self-negation.

    THE LABELS CARRY THE SAME RULE, and round 3 fixed only the row wording. "Stretch"
    over an entry-relative read, a few rows from "Distance from trend", is one English
    word naming two measurements again — so the collision survived a round in the one
    place a reader meets first. Each label now names its own dimension, and the lane's
    sentence is phrased against the ENTRY rather than as a bare negation.

    MUTATION CHECKS: (1) put the bare `Stretch`/`拉伸度` labels back in `LANE_LABEL` and
    the label assertions red; (2) restore `en: 'not stretched'` and the sentence
    assertions red."""
    rivn = {"tech": {"pct_vs_200dma": 8.9, "above200": True, "above50": True},
            "ladder": {"alignment": {"overextended": True}},
            "entry_signal": {"status": "buy_now"}}
    out = _wr("OUT({dist: WR.distanceRow(P), lane: WR.laneRead(P).stretch,"
              " rows: WR.laneRows(P)});", {"P": rivn})
    assert "trend" in out["dist"] and "8.9" in out["dist"]
    assert "tretched" not in out["dist"], \
        "the distance row reused the stretch lane's word: %s" % out["dist"]
    assert "\u62c9\u4f38" not in out["dist"], "the ZH half reused 拉伸 too"
    # the lane keeps its own vocabulary, and the two labels name different dimensions
    assert "Distance from trend" in out["dist"]
    assert "Entry stretch" in out["rows"] and "入场拉伸" in out["rows"], \
        "the lane label does not name its own dimension"
    assert ">Stretch<" not in out["rows"] and ">拉伸度<" not in out["rows"], \
        "the lane label is still the bare word that also names the distance row"
    # and the lane's sentence names the ENTRY, so it can no longer be read as the
    # distance row's negation — "not stretched" under "Well above its own trend" was
    # exactly that, and 未过度拉伸 under 明显高于自身趋势 was its flat ZH form
    assert "not stretched" not in out["lane"]["en"], \
        "the lane still answers the distance row's question: %s" % out["lane"]["en"]
    assert "未过度拉伸" not in out["lane"]["zh"], out["lane"]["zh"]
    assert "entries here" in out["lane"]["en"] and "入场" in out["lane"]["zh"]
    # this fixture IS the disagreement: the ladder says overextended, the lane says clean
    assert out["lane"]["state"] == "ok"


@needs_node
def test_the_distance_row_never_offers_the_raw_percent_as_the_words_evidence():
    """The graded word and the printed number are DIFFERENT MEASUREMENTS, and round 3
    joined them with an em dash: `Well above its own trend — about 8.9% above its
    200-day line.` reads as "well above, and here is the number that says so".

    It is not that number. `ext.grade` grades `ext_z` — the z-score of that same gap
    against the name's OWN 252-day history — so the word is volatility-normalised and
    the number is raw. Measured over the 1,621 artifacts carrying `tech.pct_vs_200dma`,
    **33.6% of ordered pairs invert**: the name graded further out sits at the SMALLER
    raw gap. The committed crops are one such pair (AAPL "in line" at +9.0%, RIVN "well
    above" at +8.9%), so a reader comparing two drawers reads the surface as broken.

    Cure: the number leads as a plain fact of its own, and the word follows behind the
    yardstick it was actually taken against — which is BRANCH-SPECIFIC, because the two
    sources are not the same measure. 1,260 of 1,621 names carry `ext.grade`; the other
    361 fall back to `ladder.alignment.overextended`, which
    `engine/cycles.py::_overextended` reads off daily/3-day StochRSI + RSI14 overbought
    or a >=30% gap. Printing "against how far this name usually runs" over THAT would
    name a measure we did not take — the same defect one rung down.

    MUTATION CHECKS: (1) concatenate word + gap with an em dash again and the ordering
    assertions red; (2) collapse `basis` to the `byExt` branch only and the
    ladder-branch assertions red."""
    # the exact inverting pair the committed crops photograph; neither name carries an
    # `ext` block, which is why both take the ladder branch
    aapl = {"tech": {"pct_vs_200dma": 9.0}, "ladder": {"alignment": {"overextended": False}}}
    rivn = {"tech": {"pct_vs_200dma": 8.9}, "ladder": {"alignment": {"overextended": True}}}
    graded = {"tech": {"pct_vs_200dma": 8.9}, "ext": {"grade": "stretched"}}
    out = _wr("OUT({a: WR.distanceRow(A), r: WR.distanceRow(R), g: WR.distanceRow(G)});",
              {"A": aapl, "R": rivn, "G": graded})

    for key, pct, word in (("a", "9", "in line with its own trend"),
                           ("r", "8.9", "well above its own trend"),
                           ("g", "8.9", "well above its own trend")):
        html = out[key]
        assert word in html, "%s lost its graded word" % key
        # the NUMBER leads, in its own terminated sentence; the word comes after it
        assert html.index("%s%%" % pct) < html.index(word), \
            "%s still trails the number behind the word: %s" % (key, html)
        assert "About %s%% " % pct in html, \
            "%s does not state the gap as a plain fact of its own: %s" % (key, html)
        assert "%s%% above its 200-day line. " % pct in html, \
            "%s welded the gap to the word again: %s" % (key, html)

    # the yardstick is named, and it is the RIGHT one for each source
    assert "Against how far this name usually runs from that line" in out["g"]
    assert "以这只票惯常偏离该均线的幅度衡量" in out["g"]
    for key in ("a", "r"):
        assert "Against how hard it has run lately" in out[key], \
            "the ladder-sourced word claims a normalisation it does not have: %s" % out[key]
        assert "usually runs from that line" not in out[key], \
            "%s names a measure this branch did not take" % key
        assert "以它近期走势的急缓衡量" in out[key]


@needs_node
def test_the_stance_words_are_byte_identical_to_the_copy_portfolio_js_holds():
    """§7(b) of the pinned design ratifies exactly three stance words for holdings
    surfaces. They live in TWO files because portfolio.js runs signed-out and
    watchlist_risk.js never does, so neither can import the other. A copy that can drift
    is worse than no copy — this is the thing that makes it not drift."""
    stance = _wr("OUT(WR.W4_STANCE);")
    src = PORTFOLIO.read_text()
    m = re.search(r"var STANCE = \{(.+?)\};", src, re.S)
    assert m, "portfolio.js's STANCE map moved; re-pin this test deliberately"
    block = m.group(1)
    for key, pair in [("watch", stance["watch"]), ("ready", stance["ready"]), ("none", stance["none"])]:
        assert "'%s'" % pair["en"] in block, "EN stance word %r is not in portfolio.js" % pair["en"]
        assert "'%s'" % pair["zh"] in block, "ZH stance word %r is not in portfolio.js" % pair["zh"]
    # and the barred ones stay barred (§7(b): holdings surfaces are descriptive only)
    for barred in ("Act", "Protect gains"):
        assert barred not in json.dumps(stance), "%r is barred from holdings surfaces" % barred


# ===========================================================================
# 4. Tier 1 — glance tier, and the words it may not use
# ===========================================================================
BANNED_AT_GLANCE = ["ENB", "MCTR", "mctr", "WRI", "enb", "lane", "idio", "variance",
                    "beta", "factor", "topFactorShare", "z-score"]


@needs_node
@pytest.mark.parametrize("payload", [FULL, {}], ids=["full", "empty"])
def test_tier_one_carries_no_internal_vocabulary(payload):
    """Tiers may be NAMED, never explained; internal names live in tips and method
    detail. Tier 1 is the glance read and carries neither."""
    out = _wr("OUT({html: WR.intelTier1('AAPL', P)});", {"P": payload})
    html = out["html"]
    assert html.strip()
    for word in BANNED_AT_GLANCE:
        assert word not in html, "%r reached the glance tier" % word


@needs_node
def test_tier_one_says_the_quiet_thing_out_loud():
    """A name with nothing elevated gets the ratified sentence rather than an empty
    block. 'No finding' is a finding, and it is the most common one."""
    quiet = {"tech": {"above200": True, "above50": True},
             "entry_signal": {"status": "ok", "headline": "In trend"},
             "macro_sensitivity": {"tier": "low", "regime": "neutral"}}
    out = _wr("OUT({html: WR.intelTier1('X', P)});", {"P": quiet})
    assert "Nothing here needs a decision today." in out["html"]
    assert "No action" in out["html"]


@needs_node
def test_the_engines_instruction_string_never_reaches_a_holdings_surface():
    """`entry_signal.action` is written as an imperative — "take a half position here".
    Holdings surfaces are descriptive only (§7(b) / doctrine Law 1), so Tier 1 reads the
    HEADLINE and never the action.

    MUTATION CHECK: swap `es.headline` for `es.action` in `intelTier1HTML` and this
    reds on the phrase itself, not on a proxy."""
    out = _wr("OUT({html: WR.intelTier1('AAPL', P)});", {"P": FULL})
    assert "take a half position" not in out["html"]
    assert "建半仓" not in out["html"]
    # and the HEADLINE is not what renders either — the mapped state copy is
    assert "Cycle turn" not in out["html"], "the raw engine headline reached the DOM"
    assert "Turning, but not confirmed yet" in out["html"]


# ===========================================================================
# 4b. THE DE-IMPERATIVE LAW — the glance tier may not carry a trade instruction
# ===========================================================================
# Packet §0: "descriptive language only — no buy/sell/add/hedge imperatives".
# DESIGN_NOTES §7(b) additionally bars "Act" and "Protect gains" on holdings surfaces
# BY NAME. Measured on the 1,629 production artifacts, the engine's own
# `entry_signal.headline` carries an imperative on 1,085 of them (66.6%), so a
# passthrough is not an edge case — it is the default rendering.
# TWO lists, because there are two different laws and one of them is about GRAMMAR.
#
# STRICT (word-level) applies to Tier-1 copy and to the tooltips that quote an engine
# string. These surfaces speak in the product's voice, so a trading verb in them is the
# product telling the reader what to do.
BANNED_EN = [
    "buy", "sell", "add ", "hedge", "exit", "reduce", "protect", "trim",
    "chase", "half size", "take profit", "position here", "wait for",
    "don't add", "entry open", "act now",
]
BANNED_ZH = [
    "买入", "卖出", "加仓", "减仓", "离场", "止盈", "保护利润", "建半仓",
    "半仓", "追高", "入场窗口", "不宜加仓", "等待回撤", "请",
]

# IMPERATIVE (phrase-level) applies to the WHOLE drawer, and it is deliberately narrower
# — because a word-level ban over the whole composition is wrong, not merely strict. The
# Ownership row renders "insiders: 5 selling, 0 buying" and "1 adding, 0 trimming": those
# are DESCRIPTIONS OF OTHER PEOPLE'S FILED BEHAVIOUR, which is exactly the content the CEO
# handoff §10 asks that section for. Banning "selling" from a section about who is selling
# would delete the requirement to satisfy the guard. What is barred is the instruction
# MOOD directed at the reader, so the list is phrases.
#
# Verified to catch all eight imperatives the engine actually emits: "wait for a
# pullback" (588), "Buy soon" (252), "don't add here" (104), "protect gains" (50), "Wait
# for the pullback" (34), "half size" (29), "Buy zone / entry open" (25), "Exit /
# reduce" (3) — plus the alert vocabulary ("BUY ZONE", "BUY SETUP", "take profit").
IMPERATIVE_EN = [
    "buy soon", "buy zone", "buy now", "buy setup", "wait for", "don't add",
    "do not add", "protect gains", "half size", "half position", "take profit",
    "back up the truck", "add here", "trim here", "exit /", "entry open",
]
IMPERATIVE_ZH = [
    "等待回撤", "不宜加仓", "保护利润", "建半仓", "止盈", "买入区",
    "入场窗口", "即将买入", "离场/减仓", "可建半仓",
]


def _banned_hits(text):
    low = text.lower()
    return ([w for w in BANNED_EN if w in low] +
            [w for w in BANNED_ZH if w in text])


def _imperative_hits(text):
    low = text.lower()
    return ([w for w in IMPERATIVE_EN if w in low] +
            [w for w in IMPERATIVE_ZH if w in text])


def test_the_imperative_list_catches_every_instruction_the_engine_emits():
    """The guard's own guard. `IMPERATIVE_*` is narrower than a word ban, so it has to be
    shown to still catch the real vocabulary — otherwise narrowing it is just weakening
    it. These are the engine's verbatim headlines and alert strings, measured from the
    production library."""
    for phrase in [
        "Extended \u2014 wait for a pullback", "Buy soon \u2014 on confirmation",
        "Hold \u2014 don't add here", "Topping \u2014 protect gains",
        "Wait for the pullback", "Partial entry \u2014 half size now",
        "Buy zone \u2014 entry open now", "Exit / reduce \u2014 rolling over",
        "BUY ZONE \u2192 NEARING A HIGH", "BUY SETUP. A new cycle low likely formed",
        "\u8fc7\u5ea6\u62c9\u4f38 \u2014 \u7b49\u5f85\u56de\u64a4",
        "\u89c1\u9876 \u2014 \u4fdd\u62a4\u5229\u6da6",
        "\u6301\u6709 \u2014 \u6b64\u5904\u4e0d\u5b9c\u52a0\u4ed3",
    ]:
        assert _imperative_hits(phrase), "the imperative list misses %r" % phrase
    # and it does NOT fire on the descriptive third-party facts the drawer must render
    for ok in ["insiders: 5 selling, 0 buying", "1 adding, 0 trimming",
               "4 of the funds we track hold it",
               "\u5185\u90e8\u4eba\uff1a5 \u4eba\u5356\u51fa\u30010 \u4eba\u4e70\u5165"]:
        assert not _imperative_hits(ok), "%r is a description, not an instruction" % ok


@needs_node
def test_every_string_the_tier_one_mapper_can_emit_is_descriptive():
    """The WHOLE mapping table, not one fixture. A ban-token test over a single sample
    proves one row; this walks every entry the table can ever emit, in both languages,
    plus the fallback pair.

    MUTATION CHECK: put any engine headline ("Extended — wait for a pullback", "Topping
    — protect gains") into T1_STATE and this reds on the token."""
    table = _wr("OUT({t: WR.T1_STATE, f: [WR.t1Fallback({tech:{above200:true}}), "
                "WR.t1Fallback({tech:{above200:false}}), WR.t1Fallback({})]});")
    pairs = list(table["t"].values()) + table["f"]
    assert len(pairs) >= 12, "the mapping table shrank: %d entries" % len(pairs)
    for pair in pairs:
        for lang in ("en", "zh"):
            hits = _banned_hits(pair[lang])
            assert not hits, "Tier-1 copy %r carries %s" % (pair[lang], hits)


@needs_node
def test_the_engine_headline_never_reaches_the_dom_at_any_tier():
    """`entry_signal.headline` AND `.action` are both engine trade instructions. Neither
    may be rendered, and the map is keyed on `status` so a reworded headline still lands
    on descriptive copy instead of falling through to passthrough.

    MUTATION CHECK: restore `es.headline` as the lead and this reds on the headline text
    itself. (It does NOT cover a `|| es.headline` fallback bolted onto `intelLead` — the
    payload below uses a MAPPED status, so a fallback never evaluates. The unmapped-status
    sibling directly beneath is what covers that branch; the two are separate checks
    because they fail for separate reasons.)"""
    payload = dict(FULL)
    payload["entry_signal"] = {
        "status": "extended",
        "headline": "Extended \u2014 wait for a pullback",
        "headline_zh": "\u8fc7\u5ea6\u62c9\u4f38 \u2014 \u7b49\u5f85\u56de\u64a4",
        "action": "take a half position here",
    }
    out = _wr("OUT({html: WR.intelTier1('X', P), lead: WR.intelLead(P)});", {"P": payload})
    assert "wait for a pullback" not in out["html"]
    assert "\u7b49\u5f85\u56de\u64a4" not in out["html"]
    assert "half position" not in out["html"]
    assert not _banned_hits(out["html"]), _banned_hits(out["html"])
    assert out["lead"]["en"] == "Extended \u2014 no pullback yet"


@needs_node
def test_an_unknown_status_falls_back_to_a_state_read_not_to_the_engine_string():
    """A total map stops being total the moment its fallback is a passthrough."""
    payload = {"entry_signal": {"status": "some_new_status_the_engine_added",
                                "headline": "Buy now \u2014 back up the truck"},
               "tech": {"above200": True}}
    out = _wr("OUT({lead: WR.intelLead(P), html: WR.intelTier1('X', P)});", {"P": payload})
    assert "Buy now" not in out["html"] and "truck" not in out["html"]
    assert out["lead"]["en"] == "Holding above its 200-day line"
    payload2 = {"entry_signal": {"status": "unknown_x", "headline": "Sell it all"}}
    out2 = _wr("OUT({lead: WR.intelLead(P)});", {"P": payload2})
    assert out2["lead"]["en"] == "No state read for this name tonight."


@needs_node
def test_the_pinned_alert_note_is_never_quoted_into_a_tooltip():
    """`alerts.pinned` is written in the same trading voice: 1,292 of the 1,611 names
    carrying one (80.2%) include a banned token ("BUY ZONE", "BUY SETUP", "take
    profit"). The notes row counts and dates the trail; it does not quote it.

    MUTATION CHECK: put `p.headline`/`p.detail` back in the tip and this reds."""
    out = _wr("OUT({html: WR.notesRow(P)});", {"P": FULL})
    assert "DOWNTREND" not in out["html"] and "BUY SETUP" not in out["html"]
    assert not _banned_hits(out["html"]), _banned_hits(out["html"])


@needs_node
def test_no_section_of_a_fully_populated_drawer_carries_a_trade_instruction():
    """The whole composition, over the realistic payload — Tier 1 and all fifteen rows
    the composer emits, including every tip attribute."""
    out = _wr("OUT({html: WR.intelTier1('AAPL', P) + WR.intelSections('AAPL', P, "
              "{inBook:true, weightPct:16.2})});", {"P": FULL})
    hits = _imperative_hits(out["html"])
    assert not hits, "the drawer carries %s" % hits


@needs_node
def test_a_past_earnings_date_is_not_reported_as_a_coming_one():
    """`earnings.next_date` goes stale: measured across the library, 1,197 of the 1,205
    names carrying one are already PAST it, because the per-ticker artifacts bake on a
    cadence the earnings calendar outruns. The lane guarded its CHIP for this and not its
    state or its sentence, so it read "reports Jul 30" in a confident `ok` about a date
    that had come and gone.

    MUTATION CHECK: drop the `past` branch and this reds on both the state and the verb."""
    past = {"earnings": {"next_date": "2020-03-04", "next_time": "after-hours"}}
    out = _wr("OUT({lane: WR.laneRead(P).events});", {"P": past})
    assert out["lane"]["state"] == "na", out["lane"]
    assert "last reported" in out["lane"]["en"], out["lane"]["en"]
    assert "reports " not in out["lane"]["en"]
    assert out["lane"]["chip"] is None
    # a genuinely future date still reads forward, with its window state intact
    fut = {"earnings": {"next_date": "2099-01-05", "next_time": "after-hours"}}
    out2 = _wr("OUT({lane: WR.laneRead(P).events});", {"P": fut})
    assert out2["lane"]["state"] == "ok" and out2["lane"]["en"].startswith("reports ")


# ===========================================================================
# 5. canonical links — a route that 200s is not a route that works
# ===========================================================================
def test_the_dossier_link_uses_a_form_stock_html_can_actually_read():
    """`templates/stock.html.j2` takes its ticker from `location.hash` (four readers) and
    from exactly ONE query parameter — `?ticker=`, which a boot shim rewrites into the
    hash. The shipped watchlist drawer linked `stock.html?t=<T>`: not the hash, and not
    the one parameter that is honoured. A real page, a real 200, and an empty dossier —
    which is precisely the shape no link checker can see, so it is checked here."""
    stock = (ROOT / "templates" / "stock.html.j2").read_text()
    assert "location.hash" in stock
    params = set(re.findall(r"URLSearchParams\(location\.search\)\.get\('([^']+)'\)", stock))
    assert params == {"ticker"}, \
        "stock.html's accepted query parameters changed (%s); re-derive this test" % sorted(params)
    # matched at the EMIT shape — `stock.html?t=` immediately closing a JS string, which
    # is how the href was built. Prose naming the old form (this test's own subject, and
    # the comment in watchlist.js recording the fix) is not a link.
    emit = re.compile(r"""stock\.html\?t=['"]""")
    for path in (WATCHLIST, PORTFOLIO):
        src = path.read_text()
        assert not emit.search(src), "%s links the dossier by a param it cannot read" % path.name
        assert "stock.html#" in src, "%s lost its dossier link" % path.name


def test_the_terminal_deep_link_uses_the_route_the_terminal_actually_reads():
    """Verified against the charting-app route rather than guessed: the terminal page
    reads `?symbol ?? ?sym`. Both callers emit the same shape, so a route change is one
    grep rather than two."""
    for path in (WATCHLIST, PORTFOLIO):
        src = path.read_text()
        assert "app.mastermind-x.com/terminal?sym=" in src, path.name
        assert "from=macro" in src, path.name


# ===========================================================================
# 6. the anonymous drawer — a lock shell, and zero gated reads
# ===========================================================================
@needs_node
def test_the_anonymous_drawer_is_a_lock_shell_and_reads_nothing_gated():
    """The four gated scripts never reach a signed-out visitor (packet §14 A9), so
    `window.SD` and `window.WRI` are simply absent. The drawer must render the page's
    own lock grammar — not a shorter drawer, and not a blurred one."""
    out = _run(
        "var WL = require(%s);\n"
        "OUT({html: WL.drawerHTML({t:'AAPL', n:'Apple', s:'Technology'}, 8)});"
        % json.dumps(str(WATCHLIST)))
    html = out["html"]
    assert 'class="lockshell' in html, "the anonymous drawer is not the lock shell"
    assert "Free" in html and "data-gate-save" in html, "no way out of the lock shell"
    # nothing board-tier leaks, and the Board's count ladder is not borrowed
    for leak in ("wri-lrow", "st na", "st watch", "Magnificent", "conc-row", "att-stance"):
        assert leak not in html, "anonymous drawer leaked %r" % leak


@needs_node
def test_the_signed_in_drawer_renders_the_composition():
    """The other side of the same branch. Without this, the anonymous branch is the only
    one a test ever sees — and that is exactly the branch that must not be the only one
    that works."""
    out = _run(
        "var WR = require(%s);\n"
        "var WL = require(%s);\n"
        "global.SD = { lz: function (a, b) { return a; } };\n"
        "global.WRI = WR;\n"
        "WL.__setDetail('AAPL', {raw: PAY, tech: PAY.tech, summary: '', flag: null, evt: null});\n"
        "OUT({html: WL.drawerHTML({t:'AAPL', n:'Apple', s:'Technology'}, 8)});"
        % (json.dumps(str(WRISK)), json.dumps(str(WATCHLIST))), {"PAY": FULL})
    html = out["html"]
    assert 'class="lockshell' not in html
    assert html.count('class="wri-lrow"') >= 12, html.count('class="wri-lrow"')
    assert "Turning, but not confirmed yet" in html and "Magnificent Seven" in html
    # a watchlist name is watched, not held — no weight is invented for it
    assert "watchlist, so it carries no weight" in html
    assert "stock.html#AAPL" in html


@needs_node
def test_a_name_the_build_could_not_read_keeps_its_row_and_says_why():
    """`null` means read-and-absent. The row stays; only its detail is missing."""
    out = _run(
        "var WR = require(%s);\n"
        "var WL = require(%s);\n"
        "global.SD = { lz: function (a, b) { return a; } };\n"
        "global.WRI = WR;\n"
        "WL.__setDetail('ZZZZ', null);\n"
        "OUT({html: WL.drawerHTML({t:'ZZZZ', n:'ZZZZ', s:''}, 8)});"
        % (json.dumps(str(WRISK)), json.dumps(str(WATCHLIST))))
    assert "could not read this name" in out["html"]
    assert 'class="drw-act"' in out["html"], "the links row must survive a missing detail"


# ===========================================================================
# 7. the W3 residual — a claim may not assert a change and print one number twice
# ===========================================================================
@needs_node
def test_the_falling_days_claim_never_says_not_three_over_three():
    """W3 disclosed this and left it for W4. `enbClamp(...).bets` rounds, floors at 1 and
    caps at the name count, so two different raw values reach one integer by three
    routes. The claim then read "your 6 names move like about 3, not 3".

    The fixture takes the twin route: `diverges` fires from a stress-only pair while the
    two ENBs (2.4 / 2.2) round to the same 2.

    MUTATION CHECK: delete the `degenerate` branch and this reds on the doubled number."""
    held = ["A", "B", "C", "D", "E", "F"]
    RR = {
        "hasStress": True, "diverges": True,
        "stressOnlyPairs": [{"a": "A", "b": "B", "rho": 0.74}],
        "calm": {"ok": True, "held": held, "enb": 2.4, "topFactorShare": 0.42},
        "stress": {"ok": True, "held": held, "enb": 2.2, "topFactorShare": 0.51},
    }
    out = _wr("OUT({html: WR.stressHTML(RR, null)});", {"RR": RR})
    html = out["html"]
    figs = re.findall(r'<span class="fig">([^<]+)</span>', html)
    claim = html[:html.index("</p>")] if "</p>" in html else html
    assert "not <span" not in claim, "the degenerate case still uses the 'X, not Y' shape"
    assert "not by a whole direction" in html, "the degenerate case did not say so"
    assert "2.4" in figs and "2.2" in figs, figs
    # and the counts line under the bars follows the claim's precision
    assert html.count("2.4") >= 2 and html.count("2.2") >= 2, \
        "the counts line printed a different precision from the claim it sits under"


@needs_node
def test_the_falling_days_claim_handles_the_capped_route():
    """Route 2 of 3. calm 9.0 / stress 7.0 over six names: BOTH clamp to the name count,
    so every figure the tab could print is the display cap rather than the measurement.

    The 1dp cure does NOT work here — `shown` caps too, so it prints "6.0 ... 6.0" and
    "tightens, but not by a whole direction" becomes a FALSE quantitative claim hiding
    two whole directions. The capped case names the cap and makes no numeric claim.

    MUTATION CHECK: set `bounded = false` and this reds."""
    held = ["A", "B", "C", "D", "E", "F"]
    out = _wr("OUT({html: WR.stressHTML(RR, null)});", {"RR": {"hasStress": True, "diverges": True, "stressOnlyPairs": [{"a": "A", "b": "B", "rho": 0.74}], "calm": {"ok": True, "held": held, "enb": 9.0, "topFactorShare": 0.42}, "stress": {"ok": True, "held": held, "enb": 7.0, "topFactorShare": 0.51}}})
    html = out["html"]
    claim = html[:html.index("</p>")] if "</p>" in html else html
    assert "not by a whole direction" not in claim, \
        "the capped case claimed a sub-unit change it cannot measure"
    assert "not <span" not in claim
    assert "display limit" in claim, claim[:300]
    assert "6.0" not in claim, "a capped figure was printed as if it were a measurement"


@needs_node
def test_the_falling_days_claim_handles_the_floored_route():
    """Route 3 of 3. calm 0.8 / stress 0.4: both floor at one direction.

    MUTATION CHECK: remove the `Math.max(1, ...)` floor from `shown` and this reds —
    the claim starts printing "0.8" for a book that cannot move in less than one
    direction, contradicting the whole number beside it."""
    held = ["A", "B", "C", "D", "E", "F"]
    out = _wr("OUT({html: WR.stressHTML(RR, null), c: WR.enbClamp(0.8, 6), "
              "s: WR.enbClamp(0.4, 6)});", {"RR": {"hasStress": True, "diverges": True, "stressOnlyPairs": [{"a": "A", "b": "B", "rho": 0.74}], "calm": {"ok": True, "held": held, "enb": 0.8, "topFactorShare": 0.42}, "stress": {"ok": True, "held": held, "enb": 0.4, "topFactorShare": 0.51}}})
    assert out["c"]["shown"] == 1 and out["s"]["shown"] == 1, (out["c"], out["s"])
    html = out["html"]
    claim = html[:html.index("</p>")] if "</p>" in html else html
    assert "floor of one direction" in claim, claim[:300]
    assert "not by a whole direction" not in claim
    assert "0.8" not in html and "0.4" not in html


@needs_node
def test_the_ordinary_falling_days_claim_still_uses_whole_numbers():
    """The cure is scoped to the degenerate case. A whole number is the right unit for
    'how many separate directions' and the ordinary claim keeps it."""
    held = ["A", "B", "C", "D", "E", "F"]
    RR = {
        "hasStress": True, "diverges": True, "stressOnlyPairs": [],
        "calm": {"ok": True, "held": held, "enb": 3.4, "topFactorShare": 0.42},
        "stress": {"ok": True, "held": held, "enb": 1.9, "topFactorShare": 0.61},
    }
    out = _wr("OUT({html: WR.stressHTML(RR, null)});", {"RR": RR})
    html = out["html"]
    assert "not <span" in html, "the ordinary claim lost its 'X, not Y' shape"
    figs = re.findall(r'<span class="fig">([^<]+)</span>', html)
    assert "3" in figs and "2" in figs, figs
    assert "not by a whole direction" not in html


# ===========================================================================
# 8. the template — the classes the drawer emits must be styled here
# ===========================================================================
def test_every_class_the_drawer_emits_has_a_rule_on_this_page():
    """The `.wri-*` classes shipped unstyled for a whole wave because the block that
    styled them was deleted with the braid hero. Same failure mode, same remedy — but
    DERIVED, not hand-listed: a hand-written list covers exactly the classes whoever
    wrote it thought of, which is why `.wri-rail-chain` sat unstyled from #3527 until
    this wave. The set is read out of the emitters, so the next class someone adds is
    covered on the day they add it."""
    css = TEMPLATE.read_text() + (ROOT / "templates" / "theme.css").read_text()
    emitted = set()
    for path in (WRISK, PORTFOLIO, WATCHLIST):
        src = path.read_text()
        for m in re.finditer(r"""class=\\?["']([^"'\\]+)""", src):
            for cls in m.group(1).split():
                if cls.startswith(("wri-", "drw-")) or cls in ("drw", "att-stance", "lockshell"):
                    emitted.add(cls)
    assert len(emitted) >= 10, "the class harvester found almost nothing: %s" % sorted(emitted)
    missing = sorted(c for c in emitted if ("." + c) not in css)
    assert not missing, "emitted by the drawer and styled nowhere: %s" % missing


def test_dark_is_keyed_on_the_bare_root_not_an_attribute():
    """§7(a): `:root` IS the dark theme; `html[data-theme="dark"]` matches nothing for a
    first-time visitor and ships dead while measuring green in any harness that sets the
    attribute. W4 adds CSS to this file, so it re-proves the rule for the file.

    Scoped to SELECTOR use — the template's own comment names the banned pattern in
    order to explain it, and a test that cannot tell a rule from its explanation would
    fail the file for documenting itself."""
    css = TEMPLATE.read_text()
    selectors = re.findall(r'^[^/\n*]*(?:html)?\[data-theme="dark"\][^\n]*[{,]', css, re.M)
    assert not selectors, selectors


def test_no_translated_text_rides_a_title_attribute():
    """House law: bilingual copy goes in `.l-en`/`.l-zh` or `data-tip-en`/`data-tip-zh`,
    never `title=`. `scripts/check_title_i18n` enforces it over `.j2`/`.html` only, so a
    JS file EMITTING a title attribute is outside its reach — which is how
    `watchlist.js` shipped `title="从清单移除"` on the legacy remove button, beside an
    `aria-label` already carrying the same string. These three files emit none."""
    # a REGEX over `title\s*=`, not the literal `title="`. Single-quoted emission,
    # a space before the `=`, or a concatenated attribute name all slip past a literal
    # — and emitter-quoting has switched off a guard in this repo before.
    # Matched at the EMIT shape — an attribute name, `=`, and the OPENING QUOTE of its
    # value — so single-quoted emission and whitespace around the `=` are both caught,
    # while prose naming the attribute (including the comment recording this fix) is not
    # a rendered attribute. A literal `'title="'` was the first version and would miss
    # `title ='` and `title='`; the emitter-quoting trap has switched off a guard in this
    # repo before, which is why this is a pattern and not a substring.
    pat = re.compile(r"""(?<![-\w])title\s*=\s*["']""")
    for path in (WATCHLIST, PORTFOLIO, WRISK):
        hits = [ln for ln in path.read_text().splitlines() if pat.search(ln)]
        assert not hits, "%s emits a title attribute: %s" % (path.name, hits[:3])


def test_severity_never_paints_from_the_direction_tokens():
    """`--up`/`--down` SWAP under 红涨绿跌. A lane state is a severity, not a price
    direction, so it paints from the health tokens — which deliberately do not swap.
    Painting an error from `--down` turns it GREEN in Chinese."""
    css = TEMPLATE.read_text()
    block = css[css.index(".wri-lrow .st {"):css.index(".wri-lrow .rs {")]
    # comments stripped first: the block now carries a comment EXPLAINING that these
    # rules must not use the direction tokens, and a guard that cannot tell a rule from
    # its explanation fails the file for documenting itself. Fifth occurrence of this
    # trap in this wave, so it is called out here by name.
    block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    assert "--up" not in block and "--down" not in block, block


def test_the_version_stamp_moved_for_every_js_file_this_wave_touched():
    """Plain-copy JS goes live in ~3 minutes; the `?v=` stamp waits for a render. A body
    that ships without its stamp bump is served from a warm cache indefinitely.

    Asserted as a MONOTONIC INCREASE against `origin/main`, not against hardcoded
    numbers. Pinning `?v=7` would latch this wave's boundary into the suite and red the
    NEXT legitimate bump — a test that fails on correct future work is a worse defect
    than the one it guards. Self-retiring by construction: once this merges, main's
    values equal the branch's and the comparison is vacuously true, which is the right
    behaviour for a wave-scoped check."""
    tpl = TEMPLATE.read_text()
    base = subprocess.run(
        ["git", "-C", str(ROOT), "show", "origin/main:templates/watchlist.html.j2"],
        capture_output=True, text=True)
    if base.returncode != 0:
        pytest.skip("origin/main not fetched in this checkout")

    def stamps(text):
        return {m.group(1): int(m.group(2))
                for m in re.finditer(r'<script src="([a-z_]+\.js)\?v=(\d+)"></script>', text)}

    now, was = stamps(tpl), stamps(base.stdout)
    changed = [n for n in ("watchlist.js", "watchlist_risk.js", "portfolio.js")
               if (ROOT / "templates" / n).read_bytes()
               != subprocess.run(["git", "-C", str(ROOT), "show", "origin/main:templates/" + n],
                                 capture_output=True).stdout]
    for name in changed:
        assert name in now and name in was, name
        assert now[name] > was[name], (
            "%s changed but its ?v= stamp did not move (main=%d, branch=%d)"
            % (name, was[name], now[name]))


def test_the_site_copies_are_byte_identical_to_their_templates():
    """The three JS files are plain-copy pairs. `scripts/check_template_site_sync` is the
    CI guard; this is the same assertion at the wave's own boundary, so a forgotten
    `--fix` fails in the suite that changed the files rather than three jobs away."""
    for name in ("watchlist.js", "watchlist_risk.js", "portfolio.js"):
        tpl = (ROOT / "templates" / name).read_bytes()
        site = (ROOT / "site" / name).read_bytes()
        assert tpl == site, "site/%s has drifted from templates/%s" % (name, name)


# ===========================================================================
# 8b. THE LIBRARY SWEEPS — local only, because CI has no nightly artifacts
# ===========================================================================
# `site/stockdata/` is an untracked nightly artifact directory: 1,629 per-ticker JSONs
# in a full checkout, none in CI and none in a fresh agent worktree. These two tests
# therefore SKIP where they cannot run — but they are the only place a distribution
# claim can be checked at all, and both findings they exist for (a 66.6% imperative
# rate, a 93.5% Watch rate) were invisible to every fixture-based test in this file.
LIBRARY = ROOT / "site" / "stockdata"
needs_library = pytest.mark.skipif(
    not LIBRARY.is_dir() or len(list(LIBRARY.glob("*.json"))) < 100,
    reason="site/stockdata/ nightly artifacts not present in this checkout")

SWEEP_JS = """
var fs = require('fs'), path = require('path');
var WR = require(%s);
var dir = %s;
var files = fs.readdirSync(dir).filter(function (f) {
  return /\\.json$/.test(f) && f !== 'index.json';
});
var leads = {}, stance = {}, n = 0, bad = [];
files.forEach(function (f) {
  var j; try { j = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')); } catch (e) { return; }
  if (!j || typeof j !== 'object' || Array.isArray(j)) return;
  n++;
  var lead = WR.intelLead(j);
  leads[lead.en + '\\u0001' + lead.zh] = (leads[lead.en + '\\u0001' + lead.zh] || 0) + 1;
  var L = WR.laneRead(j);
  // THE THIRD ARGUMENT IS NOT OPTIONAL FOR A DRIFT RECEIPT. `intelStance` grew a
  // `flags` parameter carrying `ladder.alignment.overextended`, and that flag applies
  // the one-way floor over the all-clear branch — so a 2-arg sweep measures the
  // PRE-floor stance and prints a distribution the live DOM never renders. Measured on
  // this library the gap is 48 names at No action against the 16 the drawer actually
  // paints. `intelTier1HTML` passes exactly this; so does the sweep.
  //
  // (This template is interpolated with printf-style formatting, so a literal percent
  // sign anywhere in it — including in a comment like this one — raises TypeError
  // before the sweep ever runs. Both tests SKIP in CI for want of the nightly
  // artifacts, so a local run is the ONLY place that failure can be seen.)
  var s = WR.intelStance(L, WR.roleBadge(L), {overextended: WR.overextendedFlag(j)});
  stance[s] = (stance[s] || 0) + 1;
});
OUT({n: n, leads: Object.keys(leads), stance: stance});
"""


@needs_node
@needs_library
def test_no_tier_one_lead_in_the_real_library_carries_an_instruction():
    """The sweep the fixture tests cannot be: every distinct Tier-1 lead the REAL
    library produces, checked against the strict list.

    This is the test that would have caught the shipped defect. Every fixture-based
    check in this file passed while 1,085 of 1,629 names rendered a trade instruction,
    because a fixture only ever contains the statuses someone thought to write down."""
    out = _run(SWEEP_JS % (json.dumps(str(WRISK)), json.dumps(str(LIBRARY))))
    assert out["n"] > 1000, "swept only %d artifacts" % out["n"]
    for key in out["leads"]:
        en, zh = key.split("\u0001")
        assert not _banned_hits(en), "%r carries %s" % (en, _banned_hits(en))
        assert not _banned_hits(zh), "%r carries %s" % (zh, _banned_hits(zh))
    # a total map produces a SMALL closed set; an explosion means passthrough crept back
    assert len(out["leads"]) <= 20, \
        "%d distinct leads — the map is leaking raw engine text" % len(out["leads"])


@needs_node
@needs_library
def test_the_stance_partitions_the_real_library_instead_of_being_a_constant():
    """The distribution, measured rather than asserted from taste.

    The shipped version put 93.5% of the library in Watch, and this file's own prose
    claimed 'No finding is the most common' — false by roughly 32x. A mark on nineteen
    names in twenty is not a mark. The true shape, with the stance keyed to the role
    ladder's own graded rungs, is roughly half Watch / half Get ready / a small tail of
    No action, and No action being RARE is the honest reading of a library where almost
    every name has at least one elevated lane.

    Bounds, not point values: this is real nightly data and it moves."""
    out = _run(SWEEP_JS % (json.dumps(str(WRISK)), json.dumps(str(LIBRARY))))
    n = out["n"]
    st = out["stance"]
    frac = {k: st.get(k, 0) / n for k in ("watch", "ready", "none")}
    print("\nstance over %d artifacts: %s" % (
        n, "  ".join("%s=%d (%.1f%%)" % (k, st.get(k, 0), 100 * frac[k])
                     for k in ("watch", "ready", "none"))))
    assert frac["watch"] < 0.70, (
        "Watch is %.1f%% of the library — a mark that common is the background, not a "
        "mark. Re-derive the precedence rather than relaxing this bound." % (100 * frac["watch"]))
    assert frac["ready"] > 0.15, \
        "Get ready is %.1f%% — the middle tier has collapsed" % (100 * frac["ready"])


# ===========================================================================
# 9. this file's own contract with the runner
# ===========================================================================
def test_this_suite_imports_only_what_its_pack_installs():
    """An out-of-pack import passes locally and ERRORs on CI at collection time. Same
    guard the sibling suites carry, for the same reason."""
    import ast
    import sys

    tree = ast.parse(Path(__file__).read_text())
    stdlib = getattr(sys, "stdlib_module_names", set())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if not top or top in stdlib or top in PACK_DEPS or top == "__future__":
                continue
            offenders.append(name)
    assert not offenders, (
        "these imports are not in the pack's install set %s — they pass locally and "
        "ERROR on CI: %s" % (sorted(PACK_DEPS), sorted(set(offenders))))


def test_the_pack_dep_list_matches_the_job_that_runs_this_file():
    """PACK_DEPS above is a copy of a list that lives in the workflow. A copy that can
    drift is worse than no copy, so it is checked against the source of truth."""
    wf = (ROOT / ".github" / "ci" / "legacy-jobs.yml").read_text()
    job = wf[wf.index("  wri-risk-core:"):]
    job = job[:job.index("\n  house-law-registry:")] if "\n  house-law-registry:" in job else job
    assert "tests/test_watchlist_drawer_js.py" in job, \
        "this suite is not run by wri-risk-core — wire it, or re-pin PACK_DEPS"
    m = re.search(r"run: pip install ([^\n]+)", job)
    assert m, "the install line moved"
    installed = {d.strip() for d in m.group(1).split()}
    normalised = {"pyyaml": "yaml"}
    installed = {normalised.get(d, d) for d in installed}
    assert installed == PACK_DEPS, (
        "the job's install set moved; update PACK_DEPS deliberately. "
        "job=%s PACK_DEPS=%s" % (sorted(installed), sorted(PACK_DEPS)))
