"""tests/test_leadership_board.py — "The Big Seven" price-ledger render tests.

The board was rebuilt 2026-07-19 (#3026, after the #2985 declutter): the old
lifecycle/generals/regime skeleton is GONE from the template. The Big Seven
shows raw week/month price moves per name (sorted strongest-week-first by the
view), one verdict that is a literal count of the up rows, a count-derived
de-escalatory stance, one close-date stamp with an NYSE-session staleness
disclosure, and per-row hover receipts. No lifecycle enums, no "leader"
labels, no sector-RS strip, no client-side scripts.

Covers:
  - Full payload render: Tier-1 strings, verdict arithmetic, stance classes.
  - Killed vocabulary stays killed (#2985/#3026): leader/generals/lifecycle,
    sector strip, options-tape chip, structure chip, cw-vs-ew, <script> blocks.
  - Earnings chip within 14d; staleness singular/plural; as-of stamp.
  - Hover receipts carry the demoted detail (50d/200d, vs-market, contribution).
  - Fail-open: None / empty dict / empty members render nothing.
  - Bilingual parity EN/ZH; banned Tier-1 jargon; the "validated" CI law.
  - dashboard.html.j2 smoke: board renders in stocks mode only.
  - build_site._leadership_board_view: sort/up-count/stance arithmetic,
    as-of labels, session lag, lifecycle/earnings/sector threading (legacy
    fields still exported; the template ignores them).
"""
from __future__ import annotations

import json
import pathlib
import sys
import re

import pytest

try:
    from jinja2 import Environment, FileSystemLoader
    _JINJA_OK = True
except ImportError:
    _JINJA_OK = False

TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / "templates"
ROOT = pathlib.Path(__file__).parent.parent


def _env() -> "Environment":
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    return env


# ── full fixture ──────────────────────────────────────────────────────────────
# Mirrors the _leadership_board_view() output contract post-#3026: members are
# pre-sorted strongest-week-first, up_count/n_total/stance_* /as_of_label_* /
# sessions_stale are the view's display arithmetic. The legacy fields (trend_
# state, run, generals, cw/ew, sector_rs, structure, flow, …) are still exported
# by the view — kept here so the render tests PROVE the template ignores them.

FULL_PAYLOAD: dict = {
    "as_of": "2026-07-14",
    "age_days": 0,
    "sessions_stale": 0,
    "up_count": 4,
    "n_total": 7,
    "stance_en": "Watch — don't chase",
    "stance_zh": "观望 — 勿追",
    "as_of_label_en": "Tue Jul 14",
    "as_of_label_zh": "周二 7月14日",
    "lifecycle_stale": False,
    # legacy fields (view still threads them; template must not render them)
    "trend_state": "turning_up",
    "run": {"start": "2026-07-01", "sessions": 8, "cw_ret": 0.0236, "spy_ret": 0.0046},
    "generals": {"now": ["AAPL", "META", "NVDA"], "joining": ["MSFT", "AMZN"], "coverage": 0.67},
    "k7": {"trend": 2, "rs": 5},
    "cw": {"r2": 0.001, "r5": 0.010, "r10": 0.077, "r20": 0.026, "rel20": 0.008},
    "ew": {"r10": 0.083, "r20": 0.035},
    "structure": {"dd_from_252d_high": -0.082, "chip": "recovering"},
    "flow": {
        "pc_word": "call_tilted", "match_sessions": 3, "gross_mn": 450.0,
        "pc_ratio": 0.72, "zerodte_share": 0.31, "coverage": "AAPL+META+NVDA",
        "asof": "2026-07-14",
    },
    "mags": {"px": 65.10, "asof": "2026-07-14", "since_run": 0.057},
    "weights_basis": "polygon_mktcap",
    # sorted strongest-week-first (the view sorts before returning)
    "members": [
        {"sym": "NVDA", "w": 0.13, "r5": 0.06, "r10": 0.09, "r20": 0.07,
         "rs20": 0.05, "above50": True, "above200": True, "contrib10": 0.2,
         "lifecycle": "LEADERSHIP", "earnings": {"next_date": "2026-07-20", "days_until": 6}},
        {"sym": "META", "w": 0.10, "r5": 0.04, "r10": 0.06, "r20": 0.07,
         "rs20": 0.05, "above50": True, "above200": True, "contrib10": 0.15,
         "lifecycle": "CROWDED", "earnings": None},
        {"sym": "AAPL", "w": 0.19, "r5": 0.02, "r10": 0.05, "r20": 0.08,
         "rs20": 0.04, "above50": True, "above200": True, "contrib10": 0.3,
         "lifecycle": "QUIET_ACCUMULATION", "earnings": None},
        {"sym": "AMZN", "w": 0.11, "r5": 0.01, "r10": 0.02, "r20": 0.03,
         "rs20": 0.01, "above50": False, "above200": False, "contrib10": 0.05,
         "lifecycle": "NONE", "earnings": None},
        {"sym": "MSFT", "w": 0.14, "r5": -0.01, "r10": 0.03, "r20": 0.04,
         "rs20": -0.02, "above50": False, "above200": True, "contrib10": 0.1,
         "lifecycle": "BREAKAWAY", "earnings": {"next_date": "2026-07-29", "days_until": 15}},
        {"sym": "GOOGL", "w": 0.10, "r5": -0.02, "r10": -0.01, "r20": -0.02,
         "rs20": -0.03, "above50": False, "above200": False, "contrib10": -0.01,
         "lifecycle": "FAILED", "earnings": None},
        {"sym": "TSLA", "w": 0.07, "r5": -0.04, "r10": -0.06, "r20": -0.07,
         "rs20": -0.08, "above50": False, "above200": False, "contrib10": -0.05,
         "lifecycle": "SUPPRESSED", "earnings": None},
    ],
    "sector_rs": [
        {"ticker": "XLK", "name": "Technology", "name_zh": "科技",
         "rs_rank": 1, "lead": "leading", "conviction_en": "Cautious", "conviction_zh": "谨慎"},
        {"ticker": "XLU", "name": "Utilities", "name_zh": "公用事业",
         "rs_rank": 11, "lead": "lagging", "conviction_en": "Accumulate", "conviction_zh": "积极配置"},
    ],
}

RENDER_TMPL = (
    "{% from '_leadership_board.html.j2' import leadership_board as lboard %}"
    "{{ lboard(d) }}"
)
GUARD_TMPL = (
    "{% from '_leadership_board.html.j2' import leadership_board as lboard %}"
    "{% if d %}{{ lboard(d) }}{% endif %}"
)


# ── main render tests ─────────────────────────────────────────────────────────

@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_renders_full_payload_without_exception():
    """Full fixture must render without raising; panel class present."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "big7" in html
    assert len(html) > 500


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_key_tier1_strings_present():
    """Title, verdict, stance, and company display names on Tier 1."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # panel title bilingual
    assert "The Big Seven" in html
    assert "七巨头" in html
    # verdict wording
    assert "up this week" in html
    assert "上涨" in html
    # stance (from the payload)
    assert "Watch — don't chase" in html
    assert "观望 — 勿追" in html
    # company names (Tier 1 display names, not raw tickers)
    assert "Apple" in html
    assert "苹果" in html
    assert "Nvidia" in html
    assert "英伟达" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_verdict_is_literal_count():
    """The cohort verdict is the view's literal up-count — 4 of 7 in the fixture."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "<b>4 of 7</b> up this week" in html
    assert "本周 <b>4/7</b> 上涨" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_no_lifecycle_enums_anywhere():
    """#3026 deleted lifecycle from the board entirely — raw enums must not
    appear ANYWHERE in the render (not even hover), though the payload still
    carries them (legacy view field)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    for term in ["QUIET_ACCUMULATION", "BREAKAWAY", "LEADERSHIP", "CROWDED",
                 "SUPPRESSED", "FAILED", "CATALYST_WINDOW"]:
        assert term not in html, f"Raw lifecycle enum '{term}' leaked into the render"


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_no_leader_vocabulary_anywhere():
    """#3026 verified property: the word 'leader' appears nowhere. The generals
    labels ('carrying the index', 'joining the leaders', 'Led by') are dead."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "leader" not in html.lower()
    assert "carrying the index" not in html
    assert "joining the" not in html
    assert "Led by" not in html
    assert "领涨" not in html
    assert "generals" not in html.lower()


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_count_rule_disclosed_in_help():
    """The ? help discloses the fixed count→stance rule (pre-registered, plain)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "5+ up = In favour" in html
    assert "Stand aside" in html
    assert "nothing scored, nothing predicted" in html
    assert "≥5 上涨 = 有利" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_help_not_a_buy_signal_language():
    """The ? help keeps the heads-up framing: Buy lanes decide entries, hover
    for the per-name receipts."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "the Buy lanes below still decide entries" in html
    assert "Hover any name" in html
    assert "入场时机仍由下方买入通道决定" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_earnings_chip_renders_when_within_14d():
    """Earnings chip on the row face + hover receipt for days_until ≤ 14."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # NVDA has 6d → chip on the row face
    assert "reports 6d" in html
    assert "6日财报" in html
    # …and in the hover receipt
    assert "reports in 6d" in html
    assert "6日后财报" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_earnings_chip_absent_over_14d_or_none():
    """MSFT has days_until=15 (>14) → no chip, no hover mention; AAPL None → none."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "reports 15d" not in html
    assert "reports in 15d" not in html
    assert "15日财报" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_stance_class_in_favour_at_5_up():
    """5+ up rows → the stance line carries the st-fav (green) class."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=dict(FULL_PAYLOAD, up_count=5))
    assert 'class="big7-stance st-fav"' in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_stance_class_stand_aside_at_2_up():
    """≤2 up rows → st-aside (red) class."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=dict(FULL_PAYLOAD, up_count=2))
    assert 'class="big7-stance st-aside"' in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_stance_class_watch_at_4_up():
    """3–4 up rows → st-watch (amber) class (fixture has 4). Check the stance
    element itself — all three st-* names also appear as CSS rules in <style>."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert 'class="big7-stance st-watch"' in html
    assert 'class="big7-stance st-fav"' not in html
    assert 'class="big7-stance st-aside"' not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_stance_default_when_missing():
    """Payload without stance_en/zh falls back to the safe 'Watch' stance."""
    env = _env()
    payload = {k: v for k, v in FULL_PAYLOAD.items() if k not in ("stance_en", "stance_zh")}
    html = env.from_string(RENDER_TMPL).render(d=payload)
    assert "Watch — don't chase" in html
    assert "观望 — 勿追" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_asof_stamp_renders():
    """ONE close-date stamp naming the last print (no age math on Tier 1)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "Prices to Tue Jul 14" in html
    assert "收盘价截至 周二 7月14日" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_asof_stamp_absent_without_label():
    """No as_of_label → the stamp is simply absent (fail-open, no crash)."""
    env = _env()
    payload = {k: v for k, v in FULL_PAYLOAD.items()
               if k not in ("as_of_label_en", "as_of_label_zh")}
    html = env.from_string(RENDER_TMPL).render(d=payload)
    assert "Prices to" not in html
    assert "收盘价截至" not in html
    assert "big7" in html  # board still renders


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_staleness_disclosure_singular():
    """sessions_stale=1 → '1 session behind' (singular), amber, bilingual."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=dict(FULL_PAYLOAD, sessions_stale=1))
    assert "1 session behind" in html
    assert "1 sessions behind" not in html
    assert "滞后1个交易日" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_staleness_disclosure_plural():
    """sessions_stale=2 → '2 sessions behind' disclosed on the glance tier."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=dict(FULL_PAYLOAD, sessions_stale=2))
    assert "2 sessions behind" in html
    assert "滞后2个交易日" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_staleness_absent_when_fresh():
    """sessions_stale=0 (weekend-safe NYSE arithmetic) → no amber scare."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "behind" not in html
    assert "滞后" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_row_arrows_up_down():
    """Rows carry ▲/▼ arrows and up/dn accent classes by week-move sign."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "▲" in html
    assert "▼" in html
    assert 'class="big7-row up"' in html
    assert 'class="big7-row dn"' in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_signed_pct_formatting():
    """Moves print as signed one-decimal percents (+6.0% / -4.0%)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "+6.0%" in html   # NVDA week
    assert "-4.0%" in html   # TSLA week
    assert "+7.0%" in html   # NVDA month


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_rows_render_one_per_member():
    """Exactly one price row per member (7 in the fixture)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert html.count('<div class="big7-row ') == 7


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_null_move_renders_dash_no_crash():
    """A member with no return fields renders an em-dash + neutral dot, no crash."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=dict(FULL_PAYLOAD, members=[{"sym": "AAPL"}]))
    assert "big7" in html
    assert "—" in html
    assert "·" in html  # neutral arrow for a null week move


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_hover_receipt_contents():
    """Per-row hover carries the demoted Tier-2 detail: 50d/200d lines,
    vs-market, and the 10-day contribution as a plain % (no 'leader' badge)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "week +6.0%" in html
    assert "above 50-day line" in html
    assert "below 50-day line" in html   # GOOGL/TSLA below
    assert "200-day line" in html
    assert "vs market (1m)" in html
    assert "10-day share of the group move 20%" in html  # NVDA contrib10=0.2
    assert "50日均线上方" in html
    assert "相对大盘(月)" in html
    assert "近10日组合贡献" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_company_names_and_ticker_span():
    """Tier 1 shows company display names; the raw ticker rides in a small
    .big7-tkr span next to the name."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    for name in ["Apple", "Microsoft", "Nvidia", "Amazon", "Alphabet", "Meta", "Tesla"]:
        assert name in html
    for zh in ["苹果", "微软", "英伟达", "亚马逊", "谷歌", "特斯拉"]:
        assert zh in html
    assert '<span class="big7-tkr">NVDA</span>' in html
    assert '<span class="big7-tkr">AAPL</span>' in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_goog_googl_cross_form():
    """GOOG (the other share class) must map to Alphabet / 谷歌 as well."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(
        d=dict(FULL_PAYLOAD, members=[{"sym": "GOOG", "r5": 0.01, "r20": 0.02}]))
    assert "Alphabet" in html
    assert "谷歌" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_unknown_symbol_falls_back_to_ticker():
    """An unexpected symbol renders its raw ticker rather than crashing."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(
        d=dict(FULL_PAYLOAD, members=[{"sym": "ZZZZ", "r5": 0.01}]))
    assert "ZZZZ" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_no_banned_tier1_vocabulary():
    """Design doctrine: banned Tier-1 jargon must not appear in user-visible copy.
    Strips class attrs, data-tip attrs, style attrs, and <style>...</style> blocks
    before checking — these are not visible to the user."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # strip CSS blocks (not user-visible)
    stripped = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    # strip class attributes (CSS identifiers are not user copy)
    stripped = re.sub(r'\s+class="[^"]*"', '', stripped)
    # strip data-tip (Tier 2 hover — not always-visible Tier 1)
    stripped = re.sub(r'\s+data-tip-[a-z]+="[^"]*"', '', stripped)
    # strip inline style attributes
    stripped = re.sub(r'\s+style="[^"]*"', '', stripped)
    BANNED = [
        "organ", "lobe", "display-tier", "display-only", "confluence",
        "k-of-n", "K-of-N", "percentile", "z-score", "t-stat",
        "Leader Radar",     # internal program name — banned from Tier 1
        "LRV",              # internal acronym
        "M7C",              # internal acronym
        "MLC",              # internal program name
    ]
    for term in BANNED:
        assert term not in stripped, f"Banned Tier-1 term '{term}' found in user-visible HTML"


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_no_validated_word():
    """CI law: 'validated' must never appear in user-facing output."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "validated" not in html.lower()


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_fail_open_none_payload():
    """Panel renders nothing when payload is None."""
    env = _env()
    html = env.from_string(GUARD_TMPL).render(d=None)
    assert "big7" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_fail_open_empty_dict():
    """Panel renders nothing when payload is empty dict (falsy in Jinja2)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d={})
    assert "big7" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_fail_open_empty_members():
    """#3026 gate: a payload with no members renders nothing (no empty shell)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=dict(FULL_PAYLOAD, members=[]))
    assert "big7" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_all_null_members_no_crash():
    """All-null member fields must render without crashing — dashes, no exception."""
    env = _env()
    null_payload = dict(FULL_PAYLOAD, members=[
        {"sym": "AAPL", "lifecycle": None, "earnings": None},
        {"sym": "NVDA", "lifecycle": "NONE", "earnings": None},
    ])
    html = env.from_string(RENDER_TMPL).render(d=null_payload)
    assert "big7" in html
    assert "Apple" in html
    assert "—" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_bilingual_parity():
    """Both EN and ZH strings must appear throughout the panel."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    # English
    assert "The Big Seven" in html
    assert "up this week" in html
    assert "Not a buy signal" in html
    # Chinese
    assert "七巨头" in html
    assert "上涨" in html
    assert "非买入信号" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_footnote_present():
    """ONE footnote: plain moves, hover for detail, not a buy signal."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "Not a buy signal; the lanes below decide entries." in html
    assert "非买入信号；入场由下方通道决定。" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_removed_content_stays_removed():
    """Regression guard on the #2985/#3026 declutter: the killed surfaces must
    not come back even though the legacy payload fields still feed the macro —
    sector-RS strip, options-tape chip, structure chip, cw-vs-ew comparative,
    run-day line, lifecycle plain-words."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "Sector momentum rank" not in html
    assert 'data-sec=' not in html
    assert "Options tape" not in html
    assert "below the year high" not in html
    assert "equal-weight" not in html
    assert "day 8" not in html           # run-day line (fixture run.sessions=8)
    assert "quietly building" not in html
    assert "no trend read" not in html
    assert "stance_matrix" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_static_board_no_client_scripts():
    """#2985 removed the client-side fetch scripts; the board is static HTML."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FULL_PAYLOAD)
    assert "<script" not in html
    assert "fetch(" not in html


# ── dashboard.html.j2 smoke tests ────────────────────────────────────────────

def _full_env():
    """Mirror scripts/build_site.py Jinja env (same as test_dashboard_template_render)."""
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
    env.filters["min"] = lambda seq: min(seq)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env


def _base_vm_with_lb() -> dict:
    """Base vm from test_dashboard_template_render extended with leadership_board key."""
    # Minimal vm that passes the existing dashboard render suite
    return dict(
        latest={
            "date": "2026-07-14",
            "quad": "Q2",
            "quad_name": "Reflation",
            "label": "Q2 — Reflation",
            "confidence": 0.72,
            "fed_stance": None,
            "dislocation": None,
            "turning_point": None,
            "risk_radar": None,
            "rate_inflation_transmission": None,
            "cross_asset_confirm": None,
            "transition_state": "stable",
            "liquidity_overlay": "neutral",
            "conditions": None,
            "risk_state": None,
            "cycle_tag": "mid",
        },
        mtf=None,
        macro_catalysts=[],
        event_strip=[],
        event_risk=None,
        prediction_markets=None,
        narrative_regime=None,
        ndi=None,
        macro_news=None,
        macro_brief=None,
        macro_news_disclaimer="",
        macro_news_disclaimer_zh="",
        alerts=[],
        pb=None,
        month_name="July",
        commodities=[],
        sector_timing={},
        action_board={"hold": [], "avoid": [], "notable": [], "buy": []},
        top_setups=[],
        us_standouts=None,
        us_board_outcomes=None,
        market_gamma=None,
        components_confirming=[],
        components_contradicting=[],
        flip_plain=None,
        internals=[],
        size_style=[],
        breadth_div=None,
        breadth_panel=None,
        adv_breadth=None,
        sector_setups=None,
        generated_utc="2026-07-14 06:00",
        chart_liquidity=None,
        chart_credit_breadth=None,
        market_tiles=[],
        vix=None,
        chart_vix=None,
        positioning=[],
        holdings_changes=[],
        holdings_threshold=5.0,
        accumulation=[],
        flows_html="",
        health=[],
        factor_leadership=None,
        nowcast_hist=None,
        stance=None,
        index_health=[],
        alloc_card=None,
        risk_model=None,
        chart_risk_model=None,
        chart_curve=None,
        chart_vix_term=None,
        cross_asset=None,
        fear_euphoria=None,
        regime_snap=None,
        market_state=None,
        signal_stack=None,
        vol_shock=None,
        froth_fragility=None,
        fear_greed=None,
        sector_heat=None,
        dispersion_regime=None,
        policy_lever=None,
        flip_confirmation=None,
        shock_state=None,
        # MLC-W1 new key
        leadership_board=FULL_PAYLOAD,
    )


def test_dashboard_macro_mode_board_absent():
    """dashboard.html.j2 macro mode must NOT render the board (#2604: operator
    removed it from macro.html — `mode == 'stocks'` gate; us_stocks-only)."""
    env = _full_env()
    html = env.get_template("dashboard.html.j2").render(**_base_vm_with_lb(), mode="macro")
    assert len(html) > 50_000
    assert "The Big Seven" not in html
    assert "七巨头" not in html


def test_dashboard_stocks_mode_board_present():
    """dashboard.html.j2 stocks mode renders The Big Seven; the old Mag 7 panel
    markup and the 'Leadership Board' name stay gone (#3026 rename)."""
    env = _full_env()
    html = env.get_template("dashboard.html.j2").render(**_base_vm_with_lb(), mode="stocks")
    assert len(html) > 50_000
    assert "The Big Seven" in html
    assert "七巨头" in html
    assert "Leadership Board" not in html
    # Mag 7 panel element markup must be absent (render removed in MLC-W2a)
    body = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    assert "m7p-top" not in body
    assert "m7p-badge" not in body
    assert "m7p-ev" not in body


def test_dashboard_macro_mode_null_leadership_board():
    """dashboard.html.j2 renders cleanly when leadership_board is None (panel absent)."""
    env = _full_env()
    vm = _base_vm_with_lb()
    vm["leadership_board"] = None
    html = env.get_template("dashboard.html.j2").render(**vm, mode="macro")
    assert len(html) > 50_000
    assert "The Big Seven" not in html


def test_dashboard_stocks_mode_null_leadership_board():
    """dashboard.html.j2 renders cleanly when leadership_board is None (panel absent,
    fail-open). NB: assert on the EN title — 七巨头 also appears in the stocks-mode
    Turn Setups help tip, independent of this board."""
    env = _full_env()
    vm = _base_vm_with_lb()
    vm["leadership_board"] = None
    html = env.get_template("dashboard.html.j2").render(**vm, mode="stocks")
    assert len(html) > 50_000
    assert "The Big Seven" not in html


# ── build_site._leadership_board_view unit tests ──────────────────────────────

def test_leadership_board_view_missing_m7(tmp_path, monkeypatch):
    """_leadership_board_view returns None when mag7_regime/latest.json is absent."""
    import types
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is None


def test_leadership_board_view_valid_m7_only(tmp_path, monkeypatch):
    """_leadership_board_view returns the Big Seven display arithmetic when m7
    is present: up_count/n_total/stance/as-of labels alongside the members."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    m7 = {"as_of": "2026-07-14", "trend_state": "turning_up",
          "members": [{"sym": "AAPL", "r5": 0.01, "r10": 0.02, "r20": 0.03,
                       "rs20": 0.01, "above50": True, "above200": True, "contrib10": 0.1}],
          "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {}}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "sectordata").mkdir(parents=True)
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is not None
    assert result["trend_state"] == "turning_up"
    assert "members" in result
    assert "sector_rs" in result
    # Big Seven display arithmetic (#3026)
    assert result["up_count"] == 1
    assert result["n_total"] == 1
    assert result["stance_en"] == "Stand aside"   # 1 up ≤ 2
    assert result["as_of_label_en"] == "Tue Jul 14"


def test_leadership_board_view_no_trend_state(tmp_path, monkeypatch):
    """_leadership_board_view returns None when trend_state is missing."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps({"as_of": "2026-07-14"}))
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is None


def test_leadership_board_view_sector_rs_enrichment(tmp_path, monkeypatch):
    """_leadership_board_view still threads sector_rs from sector_central.json
    (legacy view field — the Big Seven template ignores it)."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    m7 = {"as_of": "2026-07-14", "trend_state": "turning_up", "members": [],
          "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {}}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    sc_dir = tmp_path / "site" / "sectordata"
    sc_dir.mkdir(parents=True)
    sc_doc = {
        "as_of": "2026-07-14",
        "sectors": [
            {"ticker": "XLK", "name": "Technology", "name_zh": "科技",
             "momentum": {"rs_rank": 1, "lead": "leading"},
             "conviction": {"label_en": "Cautious", "label_zh": "谨慎"}},
            {"ticker": "XLU", "name": "Utilities", "name_zh": "公用事业",
             "momentum": {"rs_rank": 11, "lead": "lagging"},
             "conviction": {"label_en": "Accumulate", "label_zh": "积极配置"}},
        ],
    }
    (sc_dir / "sector_central.json").write_text(json.dumps(sc_doc))
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is not None
    assert len(result["sector_rs"]) == 2
    assert result["sector_rs"][0]["ticker"] == "XLK"
    assert result["sector_rs"][0]["rs_rank"] == 1
    assert result["sector_rs"][0]["lead"] == "leading"
    assert result["sector_rs"][1]["ticker"] == "XLU"
    assert result["sector_rs"][1]["rs_rank"] == 11


def test_leadership_board_view_earnings_stale_omitted(tmp_path, monkeypatch):
    """Earnings chip is omitted when as_of is stale (>7d old)."""
    import types
    import datetime
    (tmp_path / "mag7_regime").mkdir()
    m7 = {"as_of": "2026-07-14", "trend_state": "turning_up",
          "members": [{"sym": "AAPL"}], "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {}}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    # Write stale earnings parquet
    try:
        import pandas as pd
        (tmp_path / "earnings").mkdir()
        stale_date = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
        edf = pd.DataFrame({
            "next_date": ["2026-07-20"],
            "next_time": ["PMC"],
            "as_of": [stale_date + "T00:00:00+00:00"],
        }, index=pd.Index(["AAPL"], name="ticker"))
        edf.to_parquet(tmp_path / "earnings" / "earnings.parquet")
    except Exception:
        pytest.skip("pandas/pyarrow not available")
    (tmp_path / "site").mkdir(exist_ok=True)
    (tmp_path / "site" / "sectordata").mkdir(parents=True, exist_ok=True)
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is not None
    # earnings chip must be absent (stale as_of)
    aapl_member = next((m for m in result["members"] if m.get("sym") == "AAPL"), None)
    assert aapl_member is not None
    assert aapl_member.get("earnings") is None


# ── LRV lifecycle from radar.json (frozen-store fix, 2026-07-16) ──────────────
# The view still threads lifecycle states (behind the radar.json freshness
# gate) into members — the Big Seven template ignores them, but the gating
# logic is live code and its fail-open behavior stays under test.

def _radar_view(tmp_path, monkeypatch, radar_doc):
    """m7 fixture + optional radar.json; returns _leadership_board_view()."""
    import types
    (tmp_path / "mag7_regime").mkdir(exist_ok=True)
    m7 = {"as_of": "2026-07-14", "trend_state": "turning_up",
          "members": [{"sym": "AAPL", "above50": True},
                      {"sym": "NVDA", "above50": False}],
          "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {}}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    (tmp_path / "site").mkdir(exist_ok=True)
    if radar_doc is not None:
        rr_dir = tmp_path / "site" / "leaderradar"
        rr_dir.mkdir(parents=True, exist_ok=True)
        (rr_dir / "radar.json").write_text(json.dumps(radar_doc))
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    return bs._leadership_board_view()


def _fresh_asof() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def test_view_lifecycle_from_fresh_radar(tmp_path, monkeypatch):
    """Fresh radar.json → rows[].state mapped onto members; not stale."""
    result = _radar_view(tmp_path, monkeypatch, {
        "as_of": _fresh_asof(), "stale": False,
        "rows": [{"ticker": "AAPL", "state": "QUIET_ACCUMULATION"},
                 {"ticker": "NVDA", "state": "NONE"},
                 {"ticker": "ZZZZ", "state": "BREAKAWAY"}],  # non-M7: ignored
    })
    assert result is not None
    assert result["lifecycle_stale"] is False
    by_sym = {m["sym"]: m for m in result["members"]}
    assert by_sym["AAPL"]["lifecycle"] == "QUIET_ACCUMULATION"
    assert by_sym["NVDA"]["lifecycle"] == "NONE"


def test_view_lifecycle_stale_radar_gated(tmp_path, monkeypatch):
    """as_of older than 7 calendar days → no lifecycle reads, stale disclosed."""
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    result = _radar_view(tmp_path, monkeypatch, {
        "as_of": old, "stale": False,
        "rows": [{"ticker": "AAPL", "state": "QUIET_ACCUMULATION"}],
    })
    assert result is not None
    assert result["lifecycle_stale"] is True
    by_sym = {m["sym"]: m for m in result["members"]}
    assert by_sym["AAPL"]["lifecycle"] is None


def test_view_lifecycle_radar_absent(tmp_path, monkeypatch):
    """No radar.json at all → fail-open, stale disclosed, members lifecycle None."""
    result = _radar_view(tmp_path, monkeypatch, None)
    assert result is not None
    assert result["lifecycle_stale"] is True
    assert all(m["lifecycle"] is None for m in result["members"])


def test_view_lifecycle_radar_self_reported_stale(tmp_path, monkeypatch):
    """radar.json stale:true → gated even when as_of is fresh."""
    result = _radar_view(tmp_path, monkeypatch, {
        "as_of": _fresh_asof(), "stale": True,
        "rows": [{"ticker": "AAPL", "state": "QUIET_ACCUMULATION"}],
    })
    assert result is not None
    assert result["lifecycle_stale"] is True
    by_sym = {m["sym"]: m for m in result["members"]}
    assert by_sym["AAPL"]["lifecycle"] is None


def test_view_threads_structure_flow_mags_weights_basis(tmp_path, monkeypatch):
    """_leadership_board_view threads structure/flow/mags/weights_basis from m7
    json (legacy fields — exported for compatibility, unrendered since #3026)."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    m7 = {
        "as_of": "2026-07-14",
        "trend_state": "running_broad",
        "members": [],
        "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {},
        "structure": {"dd_from_252d_high": -0.05, "chip": "recovering"},
        "flow": {"pc_word": "call_tilted", "match_sessions": 3},
        "mags": {"px": 64.5, "asof": "2026-07-14"},
        "weights_basis": "polygon_mktcap",
    }
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    (tmp_path / "site").mkdir(exist_ok=True)
    (tmp_path / "site" / "sectordata").mkdir(parents=True, exist_ok=True)
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._leadership_board_view()
    assert result is not None
    assert result["structure"] == {"dd_from_252d_high": -0.05, "chip": "recovering"}
    assert result["flow"]["pc_word"] == "call_tilted"
    assert result["mags"]["px"] == 64.5
    assert result["weights_basis"] == "polygon_mktcap"


# ── Big Seven display arithmetic (#3026) ──────────────────────────────────────

def _arith_view(tmp_path, monkeypatch, members, as_of="2026-07-14"):
    """m7 fixture with given members; returns _leadership_board_view()."""
    import types
    (tmp_path / "mag7_regime").mkdir(exist_ok=True)
    m7 = {"as_of": as_of, "trend_state": "turning_up", "members": members,
          "run": {}, "generals": {}, "k7": {}, "cw": {}, "ew": {}}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(m7))
    (tmp_path / "site").mkdir(exist_ok=True)
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    fake_config.load = lambda: {"paths": {"site": str(tmp_path / "site")}}
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    return bs._leadership_board_view()


def test_view_sorts_members_strongest_week_first(tmp_path, monkeypatch):
    """Members come back sorted by week move desc; null r5 sinks to the bottom.
    up_count counts positive weeks only; n_total counts names WITH a week read."""
    result = _arith_view(tmp_path, monkeypatch, [
        {"sym": "AAPL", "r5": 0.01},
        {"sym": "NVDA", "r5": 0.06},
        {"sym": "TSLA", "r5": -0.04},
        {"sym": "MSFT", "r5": None},
    ])
    assert result is not None
    assert [m["sym"] for m in result["members"]] == ["NVDA", "AAPL", "TSLA", "MSFT"]
    assert result["up_count"] == 2
    assert result["n_total"] == 3   # MSFT has no week read


def test_view_stance_thresholds(tmp_path, monkeypatch):
    """The disclosed, de-escalatory count→stance rule: 5+ up = In favour ·
    3–4 = Watch, don't chase · ≤2 = Stand aside. Caps at 'In favour'."""
    cases = [
        (7, "In favour", "有利"),
        (5, "In favour", "有利"),
        (4, "Watch — don't chase", "观望 — 勿追"),
        (3, "Watch — don't chase", "观望 — 勿追"),
        (2, "Stand aside", "观望为主"),
        (0, "Stand aside", "观望为主"),
    ]
    for ups, want_en, want_zh in cases:
        members = [{"sym": f"S{i}", "r5": 0.01 if i < ups else -0.01} for i in range(7)]
        result = _arith_view(tmp_path, monkeypatch, members)
        assert result is not None
        assert result["up_count"] == ups
        assert result["stance_en"] == want_en, f"{ups} up → {result['stance_en']}"
        assert result["stance_zh"] == want_zh


def test_view_as_of_label_bilingual(tmp_path, monkeypatch):
    """The close-date stamp names the print day plainly, EN + ZH."""
    result = _arith_view(tmp_path, monkeypatch, [{"sym": "AAPL", "r5": 0.01}],
                         as_of="2026-07-14")  # a Tuesday
    assert result is not None
    assert result["as_of_label_en"] == "Tue Jul 14"
    assert result["as_of_label_zh"] == "周二 7月14日"


def test_view_asof_session_lag_weekend_fresh(monkeypatch):
    """_asof_session_lag counts NYSE sessions, not calendar days — a Friday
    close on a weekend reads 0 (the #3026 weekend-false-alarm fix)."""
    from datetime import date
    import lib.nyse_calendar as nc
    import scripts.build_site as bs
    # Pin "the session the market should have printed" to Fri 2026-07-17
    monkeypatch.setattr(nc, "expected_last_session", lambda now=None: date(2026, 7, 17))
    assert bs._asof_session_lag("2026-07-17") == 0   # Friday close, fresh
    assert bs._asof_session_lag("2026-07-18") == 0   # Saturday stamp, still fresh
    assert bs._asof_session_lag("2026-07-16") == 1   # missed Friday
    assert bs._asof_session_lag("2026-07-14") == 3   # Wed+Thu+Fri missing
    assert bs._asof_session_lag(None) is None
