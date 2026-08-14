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
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

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
JSON_SECTIONS = ["optionsRow", "macroRow", "themeRow", "ownersRow", "notesRow"]

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
    # the absence must be marked as one, not dressed as an OK
    assert 'class="st na"' in html, "%s did not mark itself not-covered" % builder


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
    """The composition of thirteen honest rows is still thirteen honest rows."""
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
        # nothing on any lane -> nothing needs a decision
        ({}, None, "none"),
        # the role ladder fired -> Watch, whatever the lanes look like
        ({}, {"kind": "review"}, "watch"),
        # an elevated NON-event lane -> Watch
        ({"price_trend": "elev"}, None, "watch"),
        # an earnings date inside its window raises the EVENTS lane to elev; that is
        # something to be ready for, not something wrong. Without this carve-out every
        # name in an earnings week reads Watch.
        ({"events": "elev"}, None, "ready"),
        # a watch-tier lane -> Get ready
        ({"stretch": "watch"}, None, "ready"),
        # events elev alongside a real elevated lane -> Watch wins
        ({"events": "elev", "balance": "elev"}, None, "watch"),
    ],
)
def test_the_stance_precedence_is_the_one_the_attention_stack_uses(lanes, role, expect):
    built = {k: {"state": "ok"} for k in
             ["price_trend", "stretch", "events", "estimates", "balance", "selling", "rates"]}
    for k, st in lanes.items():
        built[k] = {"state": st}
    out = _wr("OUT({s: WR.intelStance(L, R)});", {"L": built, "R": role})
    assert out["s"] == expect


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
    assert "Cycle turn" in out["html"], "the headline should be what renders"


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
    assert "Cycle turn" in html and "Magnificent Seven" in html
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
    styled them was deleted with the braid hero. Same failure mode, same file: the
    drawer's own classes are checked against the template that renders it."""
    css = TEMPLATE.read_text()
    for cls in ("drw-t1", "drw-lead", "drw-quiet", "drw-full", "wri-lrow", "wri-q",
                "att-stance", "lockshell", "drw-act", "drw-honest"):
        assert "." + cls in css, "%s is emitted by the drawer and styled nowhere" % cls


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
    for path in (WATCHLIST, PORTFOLIO, WRISK):
        src = path.read_text()
        assert 'title="' not in src, "%s emits a title attribute" % path.name


def test_severity_never_paints_from_the_direction_tokens():
    """`--up`/`--down` SWAP under 红涨绿跌. A lane state is a severity, not a price
    direction, so it paints from the health tokens — which deliberately do not swap.
    Painting an error from `--down` turns it GREEN in Chinese."""
    css = TEMPLATE.read_text()
    block = css[css.index(".wri-lrow .st {"):css.index(".wri-lrow .rs {")]
    assert "--up" not in block and "--down" not in block, block


def test_the_version_stamp_moved_for_every_js_file_this_wave_touched():
    """Plain-copy JS goes live in ~3 minutes; the `?v=` stamp waits for a render. A body
    that ships without its stamp bump is served from a warm cache indefinitely."""
    tpl = TEMPLATE.read_text()
    for name, ver in (("watchlist.js", 7), ("watchlist_risk.js", 5), ("portfolio.js", 5)):
        assert '<script src="%s?v=%d"></script>' % (name, ver) in tpl, \
            "%s did not get its stamp bump" % name


def test_the_site_copies_are_byte_identical_to_their_templates():
    """The three JS files are plain-copy pairs. `scripts/check_template_site_sync` is the
    CI guard; this is the same assertion at the wave's own boundary, so a forgotten
    `--fix` fails in the suite that changed the files rather than three jobs away."""
    for name in ("watchlist.js", "watchlist_risk.js", "portfolio.js"):
        tpl = (ROOT / "templates" / name).read_bytes()
        site = (ROOT / "site" / name).read_bytes()
        assert tpl == site, "site/%s has drifted from templates/%s" % (name, name)


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
