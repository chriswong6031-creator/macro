"""Tests for scripts/build_options_command.py — the Options workspace (OEU M-CMD).

Hermetic by construction: every test drives `render()` / `build_context()` with
IN-MEMORY store dicts, so nothing reads or writes the repo's real data/ or site/
trees (MM_DATA_GUARD stays clean).  One smoke test runs against the real stores
when they happen to be present and skips otherwise.

What these pins protect (each maps to a law the surface must not drift off):
  · all four mode containers render, always — the workspace IS the four modes
  · bilingual parity + no translated title= (CI-guarded house rule)
  · the close line's fill is EXACTLY the coverage share — no floor, no rounding,
    and an UNKNOWN coverage renders empty rather than full
  · the four posture readings are co-displayed and never fused into a score
  · absent stores degrade to honest empty states instead of crashing or faking
  · the payload law: plain fetch(), never a JS-injected <script> loader (#3372)
  · the stance vocabulary stays closed, and "validated" never enters user copy
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.build_options_command import (  # noqa: E402
    INDEX_KEYS,
    build_context,
    build_posture,
    build_bets,
    money_mn,
    render,
    _pips,
)

MODES = ("brief", "scanner", "ticker", "leaders")
DOCTRINE_SIX = {
    "Act", "Get ready", "Watch — don't chase", "Protect gains", "Stand aside", "Ignore",
}
EMPTY_STORES: dict = {
    "flow_desk": None, "screener": None, "leaders": None,
    "market_structure": None, "vol": None, "gex": {}, "gex_index": None,
}


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic stores — the SHAPES the four upstream builders publish
# ─────────────────────────────────────────────────────────────────────────────
def _stores() -> dict:
    return {
        "flow_desk": {
            "asof": "2026-07-24",
            "direction_note": "net premium direction is SOFT — approximate",
            "read": {
                "asof": "2026-07-24", "gross_premium_mn": 18912.4, "zerodte_share": 0.515,
                "intensity_score": 44, "intensity_key": "average",
                "dod_key": "heavier", "dod_pct": 23.0, "stance_key": "watch",
            },
            "sector_heatmap": [
                {"sector": "Technology", "gross_premium_mn": 8040.0, "tone": "pos~", "asof": "2026-07-24"},
                {"sector": "Energy", "gross_premium_mn": 4020.0, "tone": "neg~", "asof": "2026-07-24"},
                {"sector": "Utilities", "gross_premium_mn": 100.0, "tone": "neutral", "asof": "2026-07-24"},
            ],
            "top_movers": [
                {"ticker": "SPY", "net_premium_mn": 347.0, "tone": "neutral",
                 "zerodte_share": 0.697, "zerodte_dominated": False, "asof": "2026-07-24"},
                # tone='neg' (NO tilde) — top_movers and sector_heatmap disagree on the
                # enum, which is exactly why the lean word comes from the number's sign.
                {"ticker": "QQQ", "net_premium_mn": -207.8, "tone": "neg",
                 "zerodte_share": 0.72, "zerodte_dominated": True, "asof": "2026-07-24"},
            ],
        },
        "screener": {
            "n_rows": 4,
            "rows": [
                {"ticker": "QQQ", "sector": "ETF / Index", "asof": "2026-07-26",
                 "dist_to_flip_pct": -3.86, "gross_premium_mn": 2316.0},
                {"ticker": "SPY", "sector": "ETF / Index", "asof": "2026-07-26",
                 "dist_to_flip_pct": 0.4, "gross_premium_mn": 2615.0},
                {"ticker": "AAPL", "sector": "Tech", "asof": "2026-07-26",
                 "dist_to_flip_pct": -0.7, "gross_premium_mn": 307.0},
                # a STALE row — the remainder the close line must show as missing
                {"ticker": "OLD", "sector": "Tech", "asof": "2026-06-22",
                 "dist_to_flip_pct": 12.0, "gross_premium_mn": 1.0},
            ],
        },
        "leaders": {
            "as_of": "2026-07-26T01:51:28+00:00", "stale": False,
            "board_a": [{"ticker": "MARA", "sector": "Crypto", "recurrence_count": 6.0,
                         "A1_flow_recur": True, "A2_flow_z_hot": False, "A5_price_leader": None,
                         "fire_a": False, "de_escalation": {"earnings_window": True}}],
            "board_b": [
                {"ticker": "AEP", "sector": "Utilities", "B5_flow_inflect": True,
                 "B1_washout_recent": True, "days_since_inflection": 0, "fire_b": False},
                # NOT a real turn — must be excluded (the corrected #3496 rule)
                {"ticker": "NOPE", "sector": "Tech", "B5_flow_inflect": False,
                 "days_since_inflection": 0, "fire_b": False},
            ],
            "etf_strip": [{"ticker": "XLF", "net_premium_mn": 726.0}],
            "coverage": {"n_universe": 352},
        },
        "market_structure": {
            "asof": "2026-07-24",
            "gamma": {"regime": "short", "net_gex_pctile": 14.7, "days_in_regime": 3},
            "state_changes": {"vs_asof": "2026-07-21", "items": [
                {"key": "gamma_regime", "from": "long", "to": "short",
                 "note_en": "Dealer gamma regime flipped", "note_zh": "做市商伽马机制翻转"},
                # an unrecognised key must be SKIPPED, never machine-phrased at the user
                {"key": "some_future_key", "from": "a", "to": "b",
                 "note_en": "whatever", "note_zh": "随便"},
            ]},
        },
        "vol": {
            "asof": "2026-07-24",
            "snapshot": {"regime": "normalizing", "risk_score": 0.105, "vix": 18.58,
                         "scored_active": False},
            "game_plan": {"verdict": {"en": "Mixed — normalizing", "zh": "中性 · 修复中"},
                          "scored": False},
        },
        "gex": {
            k: {
                "meta": {"key": k, "en": f"{k} name", "zh": f"{k} 名称", "asof": "2026-07-25"},
                "summary": {"spot": 738.93, "regime": "short", "gamma_flip": 749.52,
                            "dist_to_flip_pct": -1.43, "call_wall": 760.0, "put_wall": 720.0,
                            "max_pain": 745.0, "iv30": 15.26, "put_call_oi_ratio": 1.58},
                "expected_move": {"daily_pct": 0.96},
            } for k in INDEX_KEYS
        },
        "gex_index": [{"key": k, "asof": "2026-07-25"} for k in INDEX_KEYS],
    }


def _workspace(page: str) -> str:
    """Only the page's OWN subtree — the shared nav is not this lane's copy."""
    start = page.index('<div class="oew">')
    end = page.index("<!-- /oew -->")
    return page[start:end]


def _visible_text(fragment: str) -> str:
    """Strip everything a user cannot read: script, style, comments, tip/aria values, tags."""
    out = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.S | re.I)
    out = re.sub(r"<style\b.*?</style>", " ", out, flags=re.S | re.I)
    out = re.sub(r"<!--.*?-->", " ", out, flags=re.S)
    out = re.sub(r'data-tip-(?:rc-)?(?:en|zh)\s*=\s*"[^"]*"', " ", out)
    out = re.sub(r'aria-label\s*=\s*"[^"]*"', " ", out)
    out = re.sub(r"<[^>]+>", " ", out)
    return html.unescape(out)


@pytest.fixture(scope="module")
def page() -> str:
    return render(REPO, _stores())


# ─────────────────────────────────────────────────────────────────────────────
# The workspace IS the four modes
# ─────────────────────────────────────────────────────────────────────────────
def test_all_four_mode_containers_render(page):
    for mode in MODES:
        assert f'id="mode-{mode}"' in page, f"missing mode container: {mode}"
        assert f'data-mode="{mode}"' in page, f"missing mode tab: {mode}"
    assert page.count('role="tabpanel"') == 4
    assert page.count('class="oew-tab"') == 4


def test_brief_is_the_default_active_mode(page):
    """The Brief is baked inline and must be visible without any fetch."""
    assert 'class="oew-mode active" id="mode-brief"' in page
    assert '<button class="oew-tab" role="tab" aria-selected="true" data-mode="brief"' in page
    for mode in ("scanner", "ticker", "leaders"):
        assert f'<section class="oew-mode" id="mode-{mode}"' in page


def test_persistent_chrome_never_depends_on_a_fetch(page):
    """Stamp, posture console and close line are baked — the honesty layer
    must never flash empty while a payload is in flight."""
    for marker in ("oew-stampblock", "oew-console", "oew-closeline", "oew-nofuse"):
        assert marker in page, marker


# ─────────────────────────────────────────────────────────────────────────────
# Bilingual
# ─────────────────────────────────────────────────────────────────────────────
def test_bilingual_span_parity(page):
    ws = _workspace(page)
    markup = re.sub(r"<script\b.*?</script>", " ", ws, flags=re.S | re.I)
    markup = re.sub(r"<style\b.*?</style>", " ", markup, flags=re.S | re.I)
    en, zh = markup.count('class="l-en"'), markup.count('class="l-zh"')
    assert en == zh, f"bilingual parity broken: {en} l-en vs {zh} l-zh"
    # Floor guards against a vacuous pass (0 == 0). The synthetic fixture is small;
    # the real stores render ~330 pairs.
    assert en > 50, "suspiciously few bilingual spans — did the copy stop being paired?"


def test_every_tip_has_a_chinese_twin(page):
    markup = re.sub(r"<script\b.*?</script>", " ", page, flags=re.S | re.I)
    markup = re.sub(r"<style\b.*?</style>", " ", markup, flags=re.S | re.I)
    for m in re.finditer(r"<[a-zA-Z][^>]*?data-tip-en\s*=\s*\"[^\"]*\"[^>]*?>", markup, re.S):
        assert "data-tip-zh" in m.group(0), f"tip without a ZH twin: {m.group(0)[:160]}"


def test_no_translated_text_in_title_attributes(page):
    """CI-guarded house rule: bilingual copy goes in data-tip-*, never title=."""
    bad = [t for t in re.findall(r'title\s*=\s*"([^"]*)"', page)
           if any(ord(c) > 127 for c in t)]
    assert bad == [], f"non-ASCII title= attributes: {bad}"


# ─────────────────────────────────────────────────────────────────────────────
# The close line — the signature carries the honesty fact
# ─────────────────────────────────────────────────────────────────────────────
def test_close_line_fill_is_exactly_the_coverage_share(page):
    """3 of 4 synthetic rows are dated to the latest close -> 75.0%, exactly.
    No floor, no minimum, no threshold colour change, no 'looks better' rounding."""
    ctx = build_context(REPO, _stores())
    assert ctx["session"]["covered"] == 3
    assert ctx["session"]["universe"] == 4
    assert ctx["session"]["coverage_pct"] == 75.0
    assert 'style="--oew-cov:75.0%"' in page


def test_unknown_coverage_renders_empty_not_full():
    """A missing coverage number must NOT paint a complete line."""
    page = render(REPO, dict(EMPTY_STORES))
    assert 'style="--oew-cov:0%"' in page
    assert "--oew-cov:100%" not in page


def test_stale_rows_are_the_close_line_remainder():
    """The one 2026-06-22 row is excluded from `covered` but stays in `universe`."""
    ctx = build_context(REPO, _stores())
    assert ctx["session"]["universe"] - ctx["session"]["covered"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# The posture console — co-displayed, never fused
# ─────────────────────────────────────────────────────────────────────────────
def test_posture_is_four_independent_readings(page):
    cells = build_posture(_stores())
    assert len(cells) == 4
    labels = [c["label_en"] for c in cells]
    assert labels == ["Whole market", "S&P dealers", "Today's tape", "Same-day bets"]
    assert page.count('class="oew-read"') == 4


def test_posture_carries_no_fused_score(page):
    """No combined/average/composite number may exist across the four readings."""
    cells = build_posture(_stores())
    for c in cells:
        assert "score" not in c, "a posture cell grew a score field"
        assert "rank" not in c
    text = _visible_text(_workspace(page))
    assert "never averaged into one score" in text


def test_posture_state_words_come_from_payload_enums():
    """Each state word is an EXISTING label, not a band this builder computed."""
    cells = build_posture(_stores())
    assert cells[0]["state_en"] == "Mixed — normalizing"     # vol desk's own verdict
    assert cells[1]["state_en"] == "Amplifying"              # gamma regime 'short'
    assert cells[2]["state_en"] == "Average"                 # intensity_key 'average'
    # 0DTE has no payload enum anywhere in the repo, so the reading is the share
    # itself — deliberately NOT banded (spec §0.13).
    assert cells[3]["state_en"] == "52% of premium"


def test_raw_machine_enums_never_reach_visible_copy(page):
    """`regime: normalizing` / `gamma.regime: short` are machine slugs."""
    text = _visible_text(_workspace(page))
    assert "normalizing vol surface" not in text
    for slug in (" short ", " long "):
        assert f"gamma{slug}" not in text.lower()


def test_vetted_glyph_is_gated_on_the_payload_scored_flag():
    """Mirrors gex.html's own gate. The glyph is the whole affordance — the word
    'validated' is CI-guarded and never printed as new user copy."""
    unscored = build_posture(_stores())
    assert unscored[0]["vetted"] is False

    scored = _stores()
    scored["vol"]["game_plan"]["scored"] = True
    assert build_posture(scored)[0]["vetted"] is True
    assert "oew-vetted" in render(REPO, scored)


def test_pips_are_a_linear_encoding_not_a_band():
    assert _pips(0.0) == 0
    assert _pips(None) == 0
    assert _pips(0.5) == 2      # 2.5 segments, banker's-rounded — a pure encoding
    assert _pips(0.6) == 3
    assert _pips(1.0) == 5
    assert _pips(0.01) == 1     # a present reading always lights one segment
    assert _pips(5.0) == 5      # clamped, never overflows its own denominator


# ─────────────────────────────────────────────────────────────────────────────
# Brief sections
# ─────────────────────────────────────────────────────────────────────────────
def test_bet_lean_comes_from_the_sign_of_the_displayed_number():
    """top_movers emits 'neg' where sector_heatmap emits 'neg~'; a shared tone map
    silently mislabels put-leaning names as two-sided. flow_desk.html.j2:610-616
    reads the sign instead — so does this."""
    rows = build_bets(_stores())["rows"]
    by_sym = {r["sym"]: r for r in rows}
    assert by_sym["SPY"]["tone_en"] == "call-leaning"
    assert by_sym["QQQ"]["tone_en"] == "put-leaning"
    assert by_sym["QQQ"]["tone_zh"] == "偏看跌"


def test_changed_chips_skip_keys_without_plain_copy():
    """An unrecognised state-change key must be dropped, not machine-phrased."""
    chips = build_context(REPO, _stores())["changed"]["chips"]
    assert len(chips) == 2
    labels = {c["en"] for c in chips}
    assert labels == {"Tape got heavier", "Dealers now amplify moves"}
    assert all(c["zh"] for c in chips)
    assert "some_future_key" not in str(chips)


def test_rail_group_b_uses_the_corrected_washout_rule():
    """Board B admission is B5 (the washout-flip verdict), never
    days_since_inflection — which stays populated for stale flips (#3496)."""
    rail = build_context(REPO, _stores())["rail"]
    assert rail["b"] == ["AEP"]
    assert "NOPE" not in rail["b"]


def test_rail_group_c_reuses_the_shipped_near_flip_threshold():
    """|dist_to_flip_pct| <= 1 is the options_screener page's own `nearflip`
    preset value, reused rather than reinvented."""
    rail = build_context(REPO, _stores())["rail"]
    assert set(rail["c"]) == {"SPY", "AAPL"}
    assert "QQQ" not in rail["c"]   # -3.86%
    assert "OLD" not in rail["c"]   # +12.0%


def test_index_row_covers_the_four_pinned_products(page):
    ctx = build_context(REPO, _stores())
    assert [i["sym"] for i in ctx["indexes"]] == list(INDEX_KEYS)
    for ix in ctx["indexes"]:
        assert ix["head_en"] == "Jumpy — moves get amplified"
        assert ix["head_zh"] == "剧烈 — 波动被放大"
        assert ix["stance"] == "protect"      # follows the regime word 1:1
        assert "below the flip" in ix["line_en"]


def test_sector_bars_share_one_scale():
    """The largest bar is 100%; every other length is directly comparable to it."""
    sectors = build_context(REPO, _stores())["sectors"]
    assert sectors["rows"][0]["width"] == 100.0
    assert sectors["rows"][1]["width"] == 50.0
    assert sectors["rows"][0]["cls"] == "buy" and sectors["rows"][1]["cls"] == "sell"
    assert sectors["top2_pct"] == 99      # (8040+4020)/12160


# ─────────────────────────────────────────────────────────────────────────────
# Degradation — honest, never fake, never a crash
# ─────────────────────────────────────────────────────────────────────────────
def test_every_store_absent_still_renders_all_four_modes():
    page = render(REPO, dict(EMPTY_STORES))
    for mode in MODES:
        assert f'id="mode-{mode}"' in page
    assert page.count('class="l-en"') == page.count('class="l-zh"')


def test_absent_stores_produce_plain_word_empty_states():
    page = render(REPO, dict(EMPTY_STORES))
    empties = re.findall(r'<p class="oew-empty">.*?</p>', page, re.S)
    assert len(empties) >= 5, "sections vanished instead of stating they are empty"
    text = _visible_text("".join(empties))
    assert "no data" not in text.lower(), "bare 'no data' is not an honest empty state"
    for phrase in ("No index chains reported for this close",
                   "Sector premium did not report for this close"):
        assert phrase in page


def test_quality_word_is_a_presence_census_not_a_threshold():
    full = build_context(REPO, _stores())["session"]
    assert full["quality_en"] == "Complete" and full["quality_zh"] == "完整"

    gone = build_context(REPO, dict(EMPTY_STORES))["session"]
    assert gone["quality_en"] == "Partial" and gone["quality_zh"] == "部分"
    assert set(gone["quality_tip_en"]) and set(gone["quality_tip_zh"])


def test_stale_leader_boards_are_named_in_the_quality_receipt():
    stores = _stores()
    stores["leaders"]["stale"] = True
    sess = build_context(REPO, stores)["session"]
    assert sess["quality_en"] == "Partial"
    assert "earlier session" in sess["quality_tip_en"]


def test_partial_stores_degrade_only_their_own_section():
    """One missing store must not take the rest of the page with it."""
    stores = _stores()
    stores["gex"] = {}
    ctx = build_context(REPO, stores)
    assert ctx["indexes"] == []
    assert ctx["sectors"] is not None and ctx["bets"] is not None
    assert "gex" in ctx["missing"]
    assert render(REPO, stores).count('id="mode-brief"') == 1


# ─────────────────────────────────────────────────────────────────────────────
# Payload law + doctrine
# ─────────────────────────────────────────────────────────────────────────────
def test_lazy_payloads_use_plain_fetch_not_injected_script_loaders(page):
    """A JS-injected <script> loader bypasses asset stamping (#3372)."""
    assert "fetch(" in page
    assert "createElement('script')" not in page
    assert 'createElement("script")' not in page
    for url in ("screenerdata/rows.json", "flowleaders/leaders.json", "gex/", "flow/"):
        assert url in page, f"lazy payload source missing: {url}"


def test_no_prefers_color_scheme_rule(page):
    """The house has zero such rules; theme comes from the no-flash boot script.
    Match the RULE, not the word — the CSS comment explains why it is absent."""
    assert re.search(r"@media[^{]*prefers-color-scheme", page) is None


def test_soft_contrast_is_not_redeclared(page):
    """theme.js applies .soft-contrast to every visitor — the page inherits it."""
    assert "html.soft-contrast" not in page


def test_theme_js_is_the_last_body_script(page):
    scripts = re.findall(r"<script[^>]*src=\"([^\"]+)\"", page)
    assert scripts[-1] == "theme.js", f"theme.js must be last, got {scripts[-1]!r}"


def test_scanner_table_wrapper_carries_tbl_scroll(page):
    """theme.js wrapTables() auto-wraps any table not already inside .tbl-scroll;
    a double wrap breaks the sticky header."""
    assert "tbl-scroll oew-tblwrap" in page


def test_ladder_segment_class_does_not_collide_with_the_scanner_control(page):
    """.oew-lseg, never .oew-seg — a second .oew-seg rule wins on source order and
    squashes the Scanner's segmented control to 7px."""
    assert ".oew-lseg{" in page
    assert re.search(r"^\.oew-seg\{", page, re.M) is not None
    assert page.count(".oew-lseg{") == 1


def test_stance_vocabulary_is_closed(page):
    """Only the doctrine six may appear as stance chips — as CLASSES and as WORDS."""
    classes = set(re.findall(r'class="oew-stance st-([a-z]+)"', page))
    assert classes, "no stance chips rendered at all"
    assert classes <= {"act", "ready", "watch", "protect", "aside", "ignore"}, classes

    # Every rendered chip's English text must be one of the six, verbatim.
    words = {
        html.unescape(m).strip()
        for m in re.findall(
            r'class="oew-stance st-[a-z]+">\s*<span class="l-en">(.*?)</span>', page, re.S
        )
    }
    assert words, "stance chips rendered no English text"
    assert words <= DOCTRINE_SIX, f"stance words outside the closed vocabulary: {words - DOCTRINE_SIX}"


def test_validated_never_appears_in_user_copy(page):
    assert "validated" not in page.lower()
    assert "已验证" not in page


def test_no_banned_vocabulary_in_visible_copy(page):
    """Run, not asserted. Scoped to the workspace subtree — the shared nav is
    not this lane's copy."""
    banned = [
        "IGNITION", "UPTURN_CONFIRMED", "slow reco", "expected-null", "forward meter",
        "display-tier", "K-of-N", "gauntlet", "prereg", "Oracle P", "FlowZ", "TSBrd",
        "NotTrap", "PriceOK", "NearHigh", "VolOK", "TurnOrg", "Inflect", "n=", "FDR",
        "z-score", "t-stat", "rank-IC", "cross-sectional", "multi-timeframe",
        "validated", "us_sector", "yCaution", "BothSides", "EarnWin",
        "pain_dist", "median_depth", "wilson_", "0DTE",
    ]
    text = _visible_text(_workspace(page))
    hits = {b: text.count(b) for b in banned if b in text}
    assert hits == {}, f"banned vocabulary in visible copy: {hits}"


def test_every_panel_answers_so_what_do_i_do(page):
    """Doctrine Law 1 — a panel with a footer must carry a stance."""
    ws = _workspace(page)
    foots = re.findall(r'<div class="oew-pfoot">(.*?)</div>', ws, re.S)
    assert len(foots) >= 4
    stanceless = [f for f in foots if "oew-stance" not in f]
    # The index-levels footer is a shared caveat under four cards that each carry
    # their own stance chip — the only sanctioned exception.
    assert len(stanceless) <= 1, f"{len(stanceless)} panels ship without a stance"


# ─────────────────────────────────────────────────────────────────────────────
# Cross-file contracts
# ─────────────────────────────────────────────────────────────────────────────
def test_lex_carries_the_full_doctrine_six():
    from engine.i18n import LEX  # noqa: PLC0415
    for stance in DOCTRINE_SIX:
        assert stance in LEX, f"stance missing from LEX: {stance}"
        assert LEX[stance] and LEX[stance] != stance


@pytest.mark.parametrize("template,mode", [
    ("gex.html.j2", "ticker"),
    ("options_screener.html.j2", "scanner"),
    ("flow_desk.html.j2", "brief"),
    ("flow_leaders.html.j2", "leaders"),
])
def test_absorbed_pages_point_at_their_workspace_mode(template, mode):
    src = (REPO / "templates" / template).read_text(encoding="utf-8")
    assert '_options_workspace_banner.html.j2' in src, f"{template} lost its banner"
    assert f"set oew_mode = '{mode}'" in src, f"{template} points at the wrong mode"


def test_legacy_banner_is_bilingual_and_dismiss_free():
    src = (REPO / "templates" / "_options_workspace_banner.html.j2").read_text(encoding="utf-8")
    assert "options.html#" in src
    assert "本面板已并入期权工作台" in src
    for token in ("localStorage", "dismiss", "onclick"):
        assert token not in src, f"the banner must stay dismiss-free (found {token})"


def test_sitemap_priority_is_pinned_for_the_workspace():
    from lib.seo import _EXPLICIT  # noqa: PLC0415
    assert _EXPLICIT["options"] == ("daily", 0.6)


def test_money_formatting():
    assert money_mn(18912.4) == "$18.9B"
    assert money_mn(341.0) == "$341M"
    assert money_mn(-143.0) == "−$143M"
    assert money_mn(None) == "—"
    assert money_mn(float("nan")) == "—"


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test against the real committed stores (skips when they are absent)
# ─────────────────────────────────────────────────────────────────────────────
def test_real_stores_render_when_present():
    if not (REPO / "site" / "flow_desk.json").exists():
        pytest.skip("live stores not present in this checkout")
    page = render(REPO)
    for mode in MODES:
        assert f'id="mode-{mode}"' in page
    assert "validated" not in page.lower()
    ws = _workspace(page)
    markup = re.sub(r"<script\b.*?</script>", " ", ws, flags=re.S | re.I)
    markup = re.sub(r"<style\b.*?</style>", " ", markup, flags=re.S | re.I)
    assert markup.count('class="l-en"') == markup.count('class="l-zh"')
