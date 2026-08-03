"""tests/test_mag7_tape_strip.py — Mega-cap tape strip (F2) render tests.

The strip is `templates/_mag7_tape_strip.html.j2`, included by dashboard.html.j2 in
`mode == 'stocks'` at the anchor where the 2026-07-23-removed leadership board sat.
Charter: research/POSTMORTEM_20260803_MAG7_RALLY_SILENCE_BY_FABLE.md §6 F2.
Fences:  research/DO_NOT_REBUILD.md §2 Mag-7 row — plain data display + a watch stance,
         never a directional call, a ranking, or a leadership read.

Every test renders the REAL partial through the SAME context names the page binds
(`latest`, `us_standouts`), so a test passing here is evidence about the shipped code
path and not about a paraphrase of it.

Covers:
  - full fixture render: event lines, own-history receipt, split line, stance line
  - honest-null: display:false, absent `events`, absent `mag7_regime`, empty members
    → literally nothing emitted (no panel shell, no <style>)
  - banned Tier-1 vocabulary (EN + ZH) absent from the rendered strip
  - no title= attribute anywhere (CI law: no translated text in title=)
  - ran-lane overlap line appears with a us_standouts fixture and disappears without
  - rarity band always rounds AWAY from rare (never claims rarer than measured)
  - tier ordering (historic first) and the 3-line cap
  - no animation declared (the strip ships no reduced-motion block, so it may not
    introduce motion)
"""
from __future__ import annotations

import pathlib
import re

import pytest

try:
    from jinja2 import Environment, FileSystemLoader
    _JINJA_OK = True
except ImportError:  # pragma: no cover - CI packs always have jinja2
    _JINJA_OK = False

pytestmark = pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")

ROOT = pathlib.Path(__file__).parent.parent
TEMPLATE_DIR = ROOT / "templates"
PARTIAL = "_mag7_tape_strip.html.j2"


def _env() -> "Environment":
    return Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)


def _render(**ctx) -> str:
    return _env().get_template(PARTIAL).render(**ctx)


# ── fixtures ──────────────────────────────────────────────────────────────────
# Verbatim shape of the `events` block emitted by engine/mag7_regime._compute_events
# for the 2026-07-31 snapshot (postmortem §1) — the week the product stayed silent.
EVENTS: dict = {
    "as_of": "2026-07-31",
    "display": True,
    "window_note": (
        "descriptive percentiles of realized 5- and 21-session returns vs the "
        "member's own full trading history; no forecast"
    ),
    "members": [
        {"sym": "MSFT", "window": "5d", "ret": 0.217501, "pctile": 99.9,
         "tier": "historic", "n_windows": 10169, "hist_years": 40.4,
         "last_larger_date": "2000-10-24", "source": "deep"},
        {"sym": "GOOGL", "window": "5d", "ret": 0.113811, "pctile": 98.57,
         "tier": "extreme", "n_windows": 5517, "hist_years": 21.9,
         "last_larger_date": "2026-05-06", "source": "deep"},
        {"sym": "TSLA", "window": "21d", "ret": -0.268258, "pctile": 1.84,
         "tier": "extreme", "n_windows": 4026, "hist_years": 16.1,
         "last_larger_date": "2026-07-29", "source": "deep"},
    ],
    "cohort": {
        "kind": "split",
        "up": [{"sym": "MSFT", "r5": 0.217501}, {"sym": "GOOGL", "r5": 0.113811}],
        "down": [{"sym": "AAPL", "r5": -0.072398}, {"sym": "META", "r5": -0.064652}],
        "generals": {"now": ["MSFT"], "joining": ["GOOGL", "AMZN"], "coverage": 0.6052},
    },
}

LATEST: dict = {"date": "2026-07-31", "mag7_regime": {"as_of": "2026-07-31",
                                                     "trend_state": "rolling_over",
                                                     "events": EVENTS}}

# Shape of a us_standouts `ran` row (site/factordata/us_standouts.json, 2026-07-31).
STANDOUTS: dict = {
    "as_of": "2026-07-31",
    "ran": [
        {"ticker": "MSFT", "name": "Microsoft Corp", "cross_date": "2026-07-20",
         "pct_since": 15.5, "stage": "ran", "label": "RAN", "label_zh": "已启动"},
        {"ticker": "DOCU", "name": "Docusign", "cross_date": "2026-07-06",
         "pct_since": 16.9, "stage": "ran", "label": "RAN", "label_zh": "已启动"},
    ],
}

# Tier-1 vocabulary the strip may never print, in either language, plus the internal
# artifact / study names. Scanned against the FULL rendered output (attributes and CSS
# class names included) — the identifiers were chosen so no exemption is needed, and an
# exemption is exactly how a banned word gets to ship inside a data-tip.
BANNED = [
    "bullish", "bearish", "chase it", "ignition", "leadership board",
    "breakout confirmed", "validated",
    "看涨", "看跌", "买入", "卖出", "点火",
    "mag7_regime", "MWR", "us_prophet_v1", "prophet_bridge",
]
# Whole-word bans: "buy"/"sell" must not appear as words, but must not false-positive
# on a future attribute value that merely contains the letters.
BANNED_WORDS = ["buy", "sell"]


def _assert_clean(html: str) -> None:
    low = html.lower()
    for term in BANNED:
        assert term.lower() not in low, f"banned term {term!r} in rendered strip"
    for word in BANNED_WORDS:
        assert not re.search(rf"\b{word}\b", low), f"banned word {word!r} in rendered strip"


# ── the event render ──────────────────────────────────────────────────────────

def test_renders_full_fixture():
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    # panel shell + eyebrow, both languages
    assert 'id="megacap-tape"' in html
    assert "Mega-cap tape" in html
    assert "超大盘行情" in html
    # one as-of stamp, exactly one (doctrine Law 4)
    assert html.count("2026-07-31") == 2, "expected one as-of stamp per language, no more"
    # MSFT record line: figure, window, own-history receipt in words
    assert "MSFT" in html
    assert "+21.8%" in html
    assert "in 5 sessions" in html
    assert "its biggest five-day gain since Oct 2000" in html
    assert "自2000年10月以来最大的五日涨幅" in html
    # the extreme tier phrases as a "last bigger" fact, not a record claim
    assert "last bigger in May 2026" in html
    assert "上一次更大是2026年5月" in html
    # the down-window member mirrors
    assert "−26.8%" in html, "figures use a true minus (U+2212), not a hyphen"
    assert "over 21 sessions" in html
    assert "last deeper in Jul 2026" in html
    assert "21个交易日内" in html


def test_split_line_names_the_other_side():
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    assert "The move is split" in html
    assert "走势分化" in html
    assert "AAPL −7.2%" in html
    assert "META −6.5%" in html


def test_stance_line_is_watch_dont_chase():
    """Doctrine Law 1 — every panel answers 'so what do I do', here: nothing."""
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    assert '<span class="m7t-stance">Watch — don\'t chase.</span>' in html
    assert '<span class="m7t-stance">观望，勿追高。</span>' in html
    # names the board's own lane label so the reader can find the name downstream
    assert '<span class="m7t-lane">“Ran”</span>' in html
    assert '<span class="m7t-lane">「已启动」</span>' in html
    assert "the next clean base" in html
    # the ZH clause hugs the bracketed label — no collapsed-whitespace gaps around it
    assert "位于下方看板的<span" in html
    assert "</span>栏；" in html


def test_tier_order_and_cap():
    """Historic first, then extreme; never more than three lines."""
    extra = dict(EVENTS)
    extra["members"] = EVENTS["members"] + [
        {"sym": "AMZN", "window": "5d", "ret": 0.17, "pctile": 97.19,
         "tier": "extreme", "n_windows": 7200, "hist_years": 28.6,
         "last_larger_date": "2025-01-02", "source": "deep"},
        {"sym": "META", "window": "5d", "ret": 0.31, "pctile": 99.95,
         "tier": "historic", "n_windows": 3400, "hist_years": 13.5,
         "last_larger_date": None, "source": "deep"},
    ]
    html = _render(latest={"mag7_regime": {"events": extra}}, us_standouts=None)
    syms = re.findall(r'<span class="m7t-sym">([A-Z]+)</span>', html)
    assert len(syms) == 3, f"cap is three lines, got {syms}"
    # META (99.95 historic) outranks MSFT (99.90 historic); both precede any extreme
    assert syms == ["META", "MSFT", "GOOGL"], syms
    # a null last_larger_date degrades to the record phrasing, never to "since None"
    assert "the biggest five-day gain on its record" in html
    assert "None" not in html


def test_rarity_band_rounds_away_from_rare():
    """A 98.57th-percentile week is 'top 2%' — never 'top 1%'. Rounding toward rare
    would claim the move was rarer than it measured."""
    html = _render(latest=LATEST, us_standouts=None)
    assert "top 2% of its 22-year record" in html      # GOOGL 98.57 → band 1.43 → 2
    assert "top 1%" not in html
    assert "top 0.1% of its 40-year record" in html    # MSFT 99.90 → band 0.10 → 0.1
    assert "bottom 2% of its 16-year record" in html   # TSLA 1.84 → 2


# ── honest null: the strip is silent, not empty ───────────────────────────────

@pytest.mark.parametrize("latest", [
    None,
    {},
    {"mag7_regime": None},
    {"mag7_regime": {"as_of": "2026-07-31", "trend_state": "cooling"}},          # no events
    {"mag7_regime": {"events": {"as_of": "2026-07-31", "display": False,
                                "members": [], "cohort": {}}}},                  # quiet day
    {"mag7_regime": {"events": {"display": True, "members": []}}},               # gate lies
    {"mag7_regime": {"events": {"display": True, "members": [
        {"sym": "MSFT", "window": "5d", "ret": 0.02, "pctile": 61.0,
         "tier": None, "n_windows": 10169, "hist_years": 40.4,
         "last_larger_date": "2026-07-01", "source": "deep"}]}}},                # untiered
    {"mag7_regime": "not-a-mapping"},
], ids=["latest-none", "latest-empty", "regime-none", "no-events", "display-false",
        "display-true-no-members", "untiered-member", "regime-not-mapping"])
def test_silent_when_nothing_to_say(latest):
    html = _render(latest=latest, us_standouts=STANDOUTS)
    assert "megacap-tape" not in html, "no panel shell"
    assert "<style" not in html, "no style block either — silence means zero bytes"
    assert "Mega-cap tape" not in html
    assert html.strip() == "", f"expected empty render, got {html.strip()[:200]!r}"


def test_missing_latest_binding_does_not_raise():
    """The include must survive a page render that never bound `latest`."""
    assert _render().strip() == ""


# ── the ran-lane linkage is a fact about existing rows, and it is optional ─────

def test_ran_overlap_line_renders():
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    assert "On the board already — MSFT since Jul 20, +15.5% since." in html
    # ZH spacing: no space after the preceding 。, one space around the em-dash and
    # between the Latin ticker and the CJK that follows it.
    assert "整理平台。已在看板上 — MSFT 自7月20日，此后 +15.5%。" in html
    # only the overlapping name; DOCU is in the ran lane but not in the tape strip
    assert "DOCU" not in html


@pytest.mark.parametrize("standouts", [
    None, {}, {"ran": []},
    {"ran": [{"ticker": "DOCU", "cross_date": "2026-07-06", "pct_since": 16.9}]},
    "not-a-mapping",
], ids=["none", "empty", "no-ran-rows", "no-overlap", "not-mapping"])
def test_ran_overlap_line_absent_without_a_hit(standouts):
    html = _render(latest=LATEST, us_standouts=standouts)
    assert "megacap-tape" in html, "the strip itself still renders"
    assert "On the board already" not in html
    assert "已在看板上" not in html


def test_ran_row_missing_fields_is_fail_open():
    """A ran row with no cross_date / pct_since still yields a grammatical sentence."""
    html = _render(latest=LATEST, us_standouts={"ran": [{"ticker": "MSFT"}]})
    assert "On the board already — MSFT." in html
    assert "None" not in html


# ── house laws ────────────────────────────────────────────────────────────────

def test_no_banned_vocabulary_en_and_zh():
    _assert_clean(_render(latest=LATEST, us_standouts=STANDOUTS))


def test_no_banned_vocabulary_in_edge_branches():
    """The broad_up / broad_down / no-last-larger branches are copy too."""
    for kind in ("broad_up", "broad_down"):
        ev = dict(EVENTS)
        ev["cohort"] = dict(EVENTS["cohort"], kind=kind)
        html = _render(latest={"mag7_regime": {"events": ev}}, us_standouts=STANDOUTS)
        assert "The move is broad" in html
        assert "走势整体一致" in html
        _assert_clean(html)


def test_no_title_attribute_anywhere():
    """CI law: no translated text in title= attributes. The strip uses none at all,
    so the absence is checked outright rather than by inspecting their contents."""
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    assert not re.search(r"\stitle\s*=", html), "strip must carry no title= attribute"
    # …and its Tier-2 receipts are on the sanctioned attributes instead
    assert "data-tip-en=" in html and "data-tip-zh=" in html


def test_tier2_receipt_carries_the_window_count_and_span():
    """The precision the glance tier demoted lives here, in both languages."""
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    assert "99.90th percentile of 10,169 overlapping 5-session windows" in html
    assert "across 40.4 years of tape" in html
    assert "Last larger: 2000-10-24." in html
    assert "Source: full trading history." in html
    assert "在 40.4 年、10,169 个重叠的 5 日窗口中位于第 99.90 百分位。" in html
    assert "上一次更大：2000-10-24。" in html
    # the disclosure sentence — Law 5's "nulls printed" in plain words, on Tier 2
    assert "Windows overlap — this ranks the move, it is not an independent sample." in html


def test_bilingual_parity_of_every_line():
    """Each l-en span is matched by an l-zh sibling — no line ships in one language."""
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    assert html.count('class="l-en"') == html.count('class="l-zh"')
    assert html.count('class="l-en"') > 0


def test_no_animation_declared():
    """The strip ships no @media (prefers-reduced-motion) block, so it may not declare
    motion. Adding a transition means adding the kill block — this pins that pairing."""
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.DOTALL))
    assert style, "the strip ships its own scoped style block"
    for prop in ("animation", "transition", "@keyframes"):
        assert prop not in style, f"{prop} declared without a reduced-motion kill block"
    assert "prefers-reduced-motion" not in style


def test_no_directional_color_on_words():
    """Colour lives on the numeric figure only. State words use --text/--muted; the
    rail is neutral. --up/--down may only be reached through --ink-* on .m7t-fig.

    Scanned over DECLARATIONS — CSS comments are stripped first, because the block's
    prose deliberately names the tokens it is explaining (and a comment paints
    nothing). The banned-vocabulary scan above stays strict on the full output."""
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.DOTALL))
    decls = re.sub(r"/\*.*?\*/", "", style, flags=re.DOTALL)
    assert "--ink-up" in decls, "the figure ink must still be declared"
    for line in decls.splitlines():
        if "--up" in line or "--down" in line:
            assert ".m7t-fig" in line, f"directional token outside the figure: {line.strip()}"
    # and no tinted container: the panel takes the house surface, unmodified
    assert "background" not in decls, "no container wash — the featured-glow law"


def test_no_font_below_nine_px():
    html = _render(latest=LATEST, us_standouts=STANDOUTS)
    style = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.DOTALL))
    sizes = [float(m) for m in re.findall(r"font-size:\s*([\d.]+)px", style)]
    assert sizes, "expected explicit font sizes"
    assert min(sizes) >= 9.0, f"sub-9px type: {min(sizes)}"


# ── wiring: the page actually includes it, at the right anchor ────────────────

def test_dashboard_includes_the_strip_at_the_board_anchor():
    src = (TEMPLATE_DIR / "dashboard.html.j2").read_text(encoding="utf-8")
    assert '{% include "_mag7_tape_strip.html.j2" %}' in src
    inc = src.index('{% include "_mag7_tape_strip.html.j2" %}')
    hdr = src.index('id="stocks-header"')
    ruling = src.index("Ignition Radar strip + \"Big Seven\" leadership board REMOVED")
    assert hdr < inc < ruling, "include belongs between #stocks-header and the 07-23 ruling note"
    # the ruling comment survives — it is the record of what may not come back
    assert "research/DO_NOT_REBUILD.md" in src[ruling:ruling + 400]


def test_strip_is_absent_from_macro_mode():
    """The include sits inside the `mode == 'stocks'` block; macro pages never see it."""
    src = (TEMPLATE_DIR / "dashboard.html.j2").read_text(encoding="utf-8")
    stocks_open = src.index("{% if mode == 'stocks' %}")
    inc = src.index('{% include "_mag7_tape_strip.html.j2" %}')
    stocks_close = src.index("{% endif %}", inc)
    assert stocks_open < inc < stocks_close


def _dashboard_vm(**over) -> dict:
    """Minimal view-model for a full dashboard.html.j2 render (shape copied from
    tests/test_mag7_panel.py::test_mag7_panel_absent_from_dashboard_stocks_mode)."""
    vm = dict(
        latest={"date": "2026-07-31", "quad": "Q2", "quad_name": "Reflation",
                "label": "Q2 — Reflation", "confidence": 0.72,
                "fed_stance": None, "dislocation": None, "turning_point": None,
                "risk_radar": None, "rate_inflation_transmission": None,
                "cross_asset_confirm": None, "transition_state": "stable",
                "liquidity_overlay": "neutral", "conditions": None,
                "risk_state": None, "cycle_tag": "mid"},
        mtf=None, macro_catalysts=[], event_strip=[], event_risk=None,
        prediction_markets=None, narrative_regime=None, ndi=None,
        macro_news=None, macro_brief=None,
        macro_news_disclaimer="", macro_news_disclaimer_zh="",
        alerts=[], pb=None, month_name="July", commodities=[],
        sector_timing={}, action_board={"hold": [], "avoid": [], "notable": [], "buy": []},
        top_setups=[], us_standouts=None, us_board_outcomes=None,
        market_gamma=None, components_confirming=[], components_contradicting=[],
        flip_plain=None, internals=[], size_style=[], breadth_div=None,
        breadth_panel=None, adv_breadth=None, sector_setups=None,
        generated_utc="2026-07-31 06:00", chart_liquidity=None,
        chart_credit_breadth=None, market_tiles=[], vix=None, chart_vix=None,
        positioning=[], holdings_changes=[], holdings_threshold=5.0,
        accumulation=[], flows_html="", health=[], factor_leadership=None,
        nowcast_hist=None, stance=None, index_health=[], alloc_card=None,
        risk_model=None, chart_risk_model=None, chart_curve=None,
        chart_vix_term=None, cross_asset=None, fear_euphoria=None,
        regime_snap=None, market_state=None, signal_stack=None, vol_shock=None,
        froth_fragility=None, fear_greed=None, sector_heat=None,
        dispersion_regime=None, policy_lever=None, flip_confirmation=None,
        shock_state=None, leadership_board=None,
    )
    vm.update(over)
    return vm


def _render_dashboard(**over) -> str:
    from engine import i18n
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env.get_template("dashboard.html.j2").render(**_dashboard_vm(**over), mode="stocks")


def test_full_page_render_emits_the_strip():
    """The include actually fires inside the real page — not just standalone.

    This is the test that would catch a macro-name collision with dashboard.html.j2's
    own t()/help(), a context binding the partial cannot see, or an autoescape
    difference between the harness and the builder."""
    latest = dict(_dashboard_vm()["latest"], mag7_regime={"as_of": "2026-07-31",
                                                          "events": EVENTS})
    html = _render_dashboard(latest=latest, us_standouts=STANDOUTS)
    assert 'id="megacap-tape"' in html
    assert "its biggest five-day gain since Oct 2000" in html
    assert "自2000年10月以来最大的五日涨幅" in html
    assert "On the board already — MSFT since Jul 20, +15.5% since." in html
    # …and it lands between the page header and the removed board's ruling note
    hdr = html.index('id="stocks-header"')
    strip = html.index('id="megacap-tape"')
    assert hdr < strip
    body = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    assert "m7p-top" not in body, "the killed 2026-07-23 panel stays gone"


def test_full_page_render_is_silent_without_events():
    """The real page on a quiet day: the partial contributes nothing at all."""
    html = _render_dashboard()  # us_standouts=None, latest has no mag7_regime
    assert "megacap-tape" not in html
    assert "Mega-cap tape" not in html
