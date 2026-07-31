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
# Banned vocabulary — ONE list, three streams
# ─────────────────────────────────────────────────────────────────────────────
# Hoisted out of test_no_banned_vocabulary_in_visible_copy so every sweep in this
# file measures the same words.  Consumers:
#   · test_no_banned_vocabulary_in_visible_copy      — static glance-tier text
#   · test_no_banned_vocabulary_in_aria_copy         — aria-label (glance tier
#     for a screen-reader user: it SUBSTITUTES for the visible content)
#   · test_no_banned_vocabulary_in_hover_copy        — data-tip-* (Tier 2)
#   · test_no_banned_vocabulary_in_script_authored_copy — the workspace script's
#     own string literals (glance AND hover copy it builds at runtime)
# PR #4123 (OIP W1) hoists this same list for a fourth consumer that EXECUTES
# renderTicker/renderScanner/renderLeaders under node; on rebase keep one copy —
# the contents are identical, only the comment differs.
BANNED_VOCABULARY = [
    "IGNITION", "UPTURN_CONFIRMED", "slow reco", "expected-null", "forward meter",
    "display-tier", "K-of-N", "gauntlet", "prereg", "Oracle P", "FlowZ", "TSBrd",
    "NotTrap", "PriceOK", "NearHigh", "VolOK", "TurnOrg", "Inflect", "n=", "FDR",
    "z-score", "t-stat", "rank-IC", "cross-sectional", "multi-timeframe",
    "validated", "us_sector", "yCaution", "BothSides", "EarnWin",
    "pain_dist", "median_depth", "wilson_", "0DTE",
]

# The list above is a TIER-1 list.  Tier 2 (docs/DESIGN_DOCTRINE.md §1) is the
# SANCTIONED home for "mechanics, definitions, base rates, provenance, receipts",
# and Law 5 spells out what a compliant Tier-2 receipt looks like:
#
#     "backtested basket-level turn = null edge (Oracle P8, n=26); slow reco
#      labels unchanged; display tier."
#
# That sentence — the doctrine's OWN worked example of correct copy — contains
# three entries of BANNED_VOCABULARY.  Sweeping hover copy with the Tier-1 list
# verbatim would therefore fail the doctrine it is supposed to enforce, so the
# hover sweep subtracts exactly the receipt vocabulary the doctrine names, and
# nothing else.  test_tier2_carve_out_is_exactly_the_doctrines_own_example pins
# this: widen the carve-out and that test fails.
#
# Everything NOT listed here stays banned on Tier 2 as well, because it has no
# sanctioned home in user copy on any tier — raw machine slugs (`pain_dist`,
# `wilson_`, `us_sector`), internal state names (`IGNITION`, `Inflect`), the
# non-compliant disclosure form Law 5 explicitly rejects (`expected-null forward
# meter`), and `validated` (CI-guarded estate-wide).  `0DTE` stays banned too:
# it is an acronym, and this workspace never DEFINES it — the plain phrase
# already carries the whole meaning.  Its real home is Tier 3, on a page that
# does explain it (content/seo/learn/options/zero-dte-regime.md).
TIER2_RECEIPT_VOCABULARY = {
    "Oracle P",   # study / ruling ID — Law 5: "study ID ... moves to Tier 2"
    "n=",         # sample size — Law 3: "Precision belongs on Tier 2 ('58.3%, n=26, ...')"
    "slow reco",  # the rating label a receipt cites as unchanged — Law 5's example
    # Same family as `n=` under Law 3's "precision belongs on Tier 2": a base
    # rate's error bars are a receipt, not glance-tier copy.
    "FDR", "z-score", "t-stat", "rank-IC",
}
BANNED_ON_TIER_2 = [b for b in BANNED_VOCABULARY if b not in TIER2_RECEIPT_VOCABULARY]


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic stores — the SHAPES the four upstream builders publish
# ─────────────────────────────────────────────────────────────────────────────
def _stores() -> dict:
    return {
        "flow_desk": {
            "asof": "2026-07-24",
            "direction_note": "net premium direction is SOFT — approximate",
            "direction_reliable": False,
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
                # These 3 rows share the FLOW DESK'S own asof (2026-07-24) — a
                # genuinely agreeing "Complete" fixture.  Vintage-mismatch is
                # exercised separately (test_vintage_mismatch_degrades_quality...).
                {"ticker": "QQQ", "sector": "ETF / Index", "asof": "2026-07-24",
                 "dist_to_flip_pct": -3.86, "gross_premium_mn": 2316.0},
                {"ticker": "SPY", "sector": "ETF / Index", "asof": "2026-07-24",
                 "dist_to_flip_pct": 0.4, "gross_premium_mn": 2615.0},
                {"ticker": "AAPL", "sector": "Tech", "asof": "2026-07-24",
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
            # vs_asof is the SOUND, immediately-preceding session (Thu 07-23 ->
            # Fri 07-24) — the stale multi-session-gap case is exercised
            # separately (test_regime_chip_suppressed_when_baseline...).
            "state_changes": {"vs_asof": "2026-07-23", "items": [
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
        "gex_index": [{"key": k, "asof": "2026-07-24"} for k in INDEX_KEYS],
    }


def _workspace(page: str) -> str:
    """Only the page's OWN subtree — the shared nav is not this lane's copy."""
    start = page.index('<div class="oew">')
    end = page.index("<!-- /oew -->")
    return page[start:end]


def _visible_text(fragment: str) -> str:
    """Text a sighted user reads IN THE FLOW: script, style, comments, tags and
    the two attribute families that are read some other way all come out.

    The tip/aria strip is a TIERING split, not a "nobody can read this" claim —
    the original docstring said "strip everything a user cannot read", and that
    premise was wrong about tips.  A hover popup IS read: docs/DESIGN_DOCTRINE.md
    §1 makes `data-tip-en/zh` the Tier-2 surface and this estate's whole
    demotion rule depends on it carrying real copy.  Believing that copy was
    unreadable is what let the banned term `0DTE` — item 34 of this file's own
    BANNED_VOCABULARY — ship in a live hover from #3590 until 2026-07-30 without
    any sweep ever seeing it.  So the values are not discarded any more, they are
    swept on their own tier: _tip_text() below, against BANNED_ON_TIER_2.
    `aria-label` likewise goes to _aria_text(), against the full Tier-1 list."""
    out = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.S | re.I)
    out = re.sub(r"<style\b.*?</style>", " ", out, flags=re.S | re.I)
    out = re.sub(r"<!--.*?-->", " ", out, flags=re.S)
    out = re.sub(r'data-tip-(?:rc-)?(?:en|zh)\s*=\s*"[^"]*"', " ", out)
    out = re.sub(r'aria-label\s*=\s*"[^"]*"', " ", out)
    out = re.sub(r"<[^>]+>", " ", out)
    return html.unescape(out)


def _attr_values(fragment: str, *attrs: str) -> str:
    """The VALUES of named attributes, as their own text stream.

    Comments and <script>/<style> bodies are dropped first, so this reads only
    attributes the server actually shipped in markup — a tip built at runtime by
    the workspace script is a different stream (_script_authored_text)."""
    out = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.S | re.I)
    out = re.sub(r"<style\b.*?</style>", " ", out, flags=re.S | re.I)
    out = re.sub(r"<!--.*?-->", " ", out, flags=re.S)
    found: list[str] = []
    for attr in attrs:
        found += re.findall(rf'{re.escape(attr)}\s*=\s*"([^"]*)"', out)
    return html.unescape("\n".join(found))


def _tip_text(fragment: str) -> str:
    """Tier-2 hover copy: the tip body plus the optional receipt line that
    templates/theme.js:4988 renders underneath it (`data-tip-rc-*`)."""
    return _attr_values(fragment, "data-tip-en", "data-tip-zh",
                        "data-tip-rc-en", "data-tip-rc-zh")


def _aria_text(fragment: str) -> str:
    """What a screen-reader user hears INSTEAD of the visible content — glance
    tier for them, so it is swept with the Tier-1 list, not the Tier-2 one."""
    return _attr_values(fragment, "aria-label")


def _js_string_literals(src: str) -> list[str]:
    """The string literals of a JS source, and nothing else — single pass.

    A regex over quote pairs is not good enough for this file and never was.
    Its block comments include six with an English possessive ("the page's OWN
    thresholds"), and its regex literals include `/"/g` and `/'/g`; every one of
    those quote characters desynchronises a naive scanner, after which literal
    and non-literal text swap places for the remainder of the file.  The sweep
    stays green either way — just green about the wrong bytes.  Stripping
    comments first with a second regex does not fix it and adds a bug of its
    own: `'//app.mastermind-x.com/?symbol='` is a URL inside a literal, and a
    line-comment strip eats the rest of that line.

    Escape sequences are kept verbatim (`\\'` stays two characters).  No banned
    needle contains a backslash, and decoding them would be a second chance to
    be wrong about bytes nobody reads."""
    out: list[str] = []
    i, n, prev = 0, len(src), ""
    while i < n:
        c = src[i]
        if c in "'\"":
            j, buf = i + 1, []
            while j < n and src[j] != c:
                if src[j] == "\\":
                    buf.append(src[j:j + 2]); j += 2; continue
                buf.append(src[j]); j += 1
            out.append("".join(buf))
            prev, i = c, j + 1
            continue
        if c == "/" and src[i + 1:i + 2] == "/":
            nl = src.find("\n", i)
            i = n if nl < 0 else nl
            continue
        if c == "/" and src[i + 1:i + 2] == "*":
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        # `/` after an operator or an opener starts a regex literal; after an
        # identifier, `)` or `]` it is division.
        if c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%~^<>"):
            j = i + 1
            while j < n and src[j] != "/":
                if src[j] == "\\":
                    j += 2; continue
                if src[j] == "[":                      # a class may hold a bare /
                    while j < n and src[j] != "]":
                        j += 2 if src[j] == "\\" else 1
                j += 1
            prev, i = "/", j + 1
            continue
        if not c.isspace():
            prev = c
        i += 1
    return out


def _script_authored_text(rendered: str) -> str:
    """Every string literal in the workspace's inline script, as one stream.

    The script builds its markup by concatenation (`'... data-tip-en="' + esc(x)
    + '"'`), so no attribute regex can recover a runtime tip from the source —
    but the COPY itself is always a literal, and a literal cannot hide behind a
    state no test happens to drive.  Attribute-name syntax is normalised away
    afterwards because the needles and the markup collide: `n=` matches inside
    the literal `data-tip-en="`, which alone raises 9 false positives here."""
    stream = html.unescape("\n".join(_js_string_literals(_extract_workspace_script(rendered))))
    return re.sub(r'[A-Za-z][\w-]*\s*=\s*(?=["\'])', " ", stream)


def _banned_vocabulary_hits(text: str, needles: list[str] | None = None) -> dict:
    """Substring counts for every banned needle present. Default list is Tier 1."""
    return {b: text.count(b) for b in (needles or BANNED_VOCABULARY) if b in text}


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


def test_regime_chip_carries_its_own_comparison_date_in_its_tooltip(page):
    """A shared panel-level 'since X's close' header conflated two different
    baselines (#F2-14) — each chip must carry its own date instead."""
    assert "'s close</span>" not in page, "the removed panel-level header text is back"
    ws = _workspace(page)
    assert re.search(r'data-tip-en="[^"]*Comparison baseline: 2026-07-23[^"]*"', ws), (
        "regime-flip chip lost its own comparison-date tooltip")


def test_regime_chip_suppressed_when_baseline_is_not_the_prior_session():
    """A multi-session build gap makes 'since <date>' unsound — withhold the
    chip rather than mislabel it (#F2-14, the exact F3-04 build-gap scenario)."""
    stores = _stores()
    stores["market_structure"]["state_changes"]["vs_asof"] = "2026-07-21"  # 3-session gap
    chips = build_context(REPO, stores)["changed"]["chips"]
    labels = {c["en"] for c in chips}
    assert "Dealers now amplify moves" not in labels
    assert "Tape got heavier" in labels, "the unrelated, sound chip must still fire"


def test_regime_chip_fires_when_baseline_is_the_immediately_prior_session():
    chips = build_context(REPO, _stores())["changed"]["chips"]
    labels = {c["en"] for c in chips}
    assert "Dealers now amplify moves" in labels


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


def test_sector_hover_no_longer_claims_a_per_trade_accuracy_figure(page):
    """The sector tone hover misattributed the PER-TRADE agreement statistic
    (~80%) to the aggregated net-sign figure the tone actually displays, which
    the repo's own calibration measures at ~41% and marks permanently
    unreliable (#F1-critical)."""
    assert "4 times in 5" not in page
    assert "recovers true direction" not in page
    assert "还原真实方向" not in page


def test_direction_honesty_is_rendered_not_just_loaded(page):
    """direction_note / direction_reliable were loaded into the render context
    but no template ever referenced them (#F2-09) — the sector panel must
    carry a visible, bilingual caution when the flow desk's own store says
    direction is unreliable."""
    ctx = build_context(REPO, _stores())
    assert ctx["direction_reliable"] is False
    text = _visible_text(_workspace(page))
    assert "not reliable alone" in text
    assert "不足以单独判断" in text


def test_direction_caution_is_silent_when_the_flag_is_absent():
    """No direction_reliable field at all -> no fabricated caution either way."""
    stores = _stores()
    del stores["flow_desk"]["direction_reliable"]
    html = render(REPO, stores)
    assert "not reliable alone" not in html


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


def test_present_but_empty_stores_are_not_complete():
    """A store that is PRESENT but carries no rows/boards is exactly as
    unusable as an absent one — `{"rows": []}` and `{"board_a": [],
    "board_b": []}` are truthy dicts a bare `if not store` waves through (#F2-02)."""
    stores = _stores()
    stores["screener"] = {"rows": []}
    ctx = build_context(REPO, stores)
    assert "screener" in ctx["missing"]
    assert ctx["session"]["quality_en"] == "Partial"

    stores2 = _stores()
    stores2["leaders"] = {"board_a": [], "board_b": []}
    ctx2 = build_context(REPO, stores2)
    assert "leaders" in ctx2["missing"]
    assert ctx2["session"]["quality_en"] == "Partial"

    stores3 = _stores()
    stores3["flow_desk"] = {"asof": "2026-07-24"}   # present, but no `read`
    ctx3 = build_context(REPO, stores3)
    assert "flow_desk" in ctx3["missing"]
    assert ctx3["session"]["quality_en"] == "Partial"


def test_vintage_mismatch_degrades_quality_and_is_named():
    """flow_desk lagging the screener's freshest chain must not read as
    Complete — the mismatch must be named, not silently absorbed (#F2-03/#F2-04)."""
    stores = _stores()
    for row in stores["screener"]["rows"][:3]:
        row["asof"] = "2026-07-25"   # a session newer than flow_desk's own asof
    sess = build_context(REPO, stores)["session"]
    assert sess["quality_en"] == "Partial"
    assert sess["coverage_asof"] == "2026-07-25"
    assert sess["date"] == "2026-07-24"
    assert "2026-07-25" in sess["quality_tip_en"]
    assert "2026-07-24" in sess["quality_tip_en"]
    assert "2026-07-25" in sess["cov_tip_en"], "the coverage tip must say WHEN it was measured"


def test_index_levels_vintage_mismatch_also_degrades_quality():
    stores = _stores()
    stores["gex_index"] = [{"key": k, "asof": "2026-07-22"} for k in INDEX_KEYS]
    sess = build_context(REPO, stores)["session"]
    assert sess["quality_en"] == "Partial"
    assert "2026-07-22" in sess["quality_tip_en"]


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
    not this lane's copy.

    Glance tier only: _visible_text() drops tips, aria-labels and <script>.  The
    other three quarters of the same sweep are the two tests below plus PR #4123's
    JS-execution pass."""
    hits = _banned_vocabulary_hits(_visible_text(_workspace(page)))
    assert hits == {}, f"banned vocabulary in visible copy: {hits}"


def test_no_banned_vocabulary_in_aria_copy(page):
    """`aria-label` replaces the visible content for a screen-reader user, so it
    is that user's glance tier — full Tier-1 list, same as the sighted copy."""
    hits = _banned_vocabulary_hits(_aria_text(_workspace(page)))
    assert hits == {}, f"banned vocabulary in aria copy: {hits}"


def test_no_banned_vocabulary_in_hover_copy(page):
    """Tier-2 hover copy — the blind spot that let `0DTE` ship live (#3590).

    `data-tip-en/zh` is read: it is the doctrine's own Tier-2 surface, and the
    demotion rule ("nothing is lost by moving detail to a hover") only holds if
    what lands there is held to a language standard too.  A looser one than
    Tier 1 — BANNED_ON_TIER_2 — because the hover is where receipts are SUPPOSED
    to live; see that constant for what it subtracts and why."""
    hits = _banned_vocabulary_hits(_tip_text(_workspace(page)), BANNED_ON_TIER_2)
    assert hits == {}, f"banned vocabulary in hover copy: {hits}"


def test_no_banned_vocabulary_in_script_authored_copy(page):
    """The workspace script's own copy, swept as literals rather than as output.

    Complementary to PR #4123's JS-execution sweep, not a duplicate of it:
    executing renderTicker/renderScanner/renderLeaders proves what a DRIVEN state
    renders; sweeping the literals proves no banned term exists in any state at
    all, including branches no fixture reaches.  `ZDTE`'s tip — one of the two
    `0DTE` sites this PR fixes — sits in exactly such a branch
    (`if(r.zerodte_dominated)`), which is why the literal form is the one that
    catches it.  Tier-2 list: this stream mixes glance copy and hover copy, so
    the permissive list is the only one that cannot produce a false positive on
    a legitimate receipt."""
    hits = _banned_vocabulary_hits(_script_authored_text(page), BANNED_ON_TIER_2)
    assert hits == {}, f"banned vocabulary in script-authored copy: {hits}"


# ─────────────────────────────────────────────────────────────────────────────
# Negative controls — a green sweep must mean "clean", never "looked at nothing"
# ─────────────────────────────────────────────────────────────────────────────
def test_hover_sweep_catches_a_planted_term_in_both_languages(page):
    """The control this guard was missing for four months.

    A sweep that silently extracts an EMPTY stream passes forever, which is
    exactly the failure mode that hid `0DTE`: the term was there, the sweep was
    green, and nothing distinguished "no violations" from "no text".  So plant
    the real historical string — verbatim, as it shipped from #3590 — back into
    real workspace markup, in EN and in ZH separately, and require a hit each
    time.  Planting into MARKUP rather than into an already-extracted string is
    the point: it exercises _attr_values' regex, not just the substring count."""
    ws = _workspace(page)
    assert _banned_vocabulary_hits(_tip_text(ws), BANNED_ON_TIER_2) == {}

    shipped_en = "Mostly same-day (0DTE) options — usually day-trading, not positioning for a move."
    shipped_zh = "以当日到期（0DTE）期权为主 — 通常是日内交易，而非布局趋势。"
    for lang, copy in (("en", shipped_en), ("zh", shipped_zh)):
        planted = ws + f'<span class="oew-pips" data-tip-{lang}="{copy}"></span>'
        hits = _banned_vocabulary_hits(_tip_text(planted), BANNED_ON_TIER_2)
        assert hits == {"0DTE": 1}, f"tip sweep blind to a planted {lang} violation: {hits}"

    # The receipt line renders inside the same popup (templates/theme.js:4988),
    # so it is swept too — a term demoted one attribute further is still read.
    planted_rc = ws + '<button class="lens-q" data-tip-rc-en="IGNITION confirmed">?</button>'
    assert _banned_vocabulary_hits(_tip_text(planted_rc), BANNED_ON_TIER_2) == {"IGNITION": 1}


def test_script_sweep_catches_a_planted_term_in_both_languages(page):
    """Same control for the literal stream, planted as the workspace script's
    own tip constants really are written — a bilingual pair inside an array."""
    body = _extract_workspace_script(page)
    plant = ("\nvar PLANT = ['x','y', false,\n"
             "  'Mostly same-day (0DTE) options — usually day-trading, not positioning for a move.',\n"
             "  '以当日到期（0DTE）期权为主 — 通常是日内交易，而非布局趋势。'];\n")
    doctored = page.replace(body, body + plant, 1)
    assert doctored != page, "could not splice the plant into the workspace script"
    hits = _banned_vocabulary_hits(_script_authored_text(doctored), BANNED_ON_TIER_2)
    assert hits == {"0DTE": 2}, f"script sweep blind to a planted violation: {hits}"


def test_the_swept_streams_are_not_empty(page):
    """Guards against the other half of a vacuous pass: an extractor that returns
    nothing at all still satisfies every "no hits" assertion above.  Pin real,
    bilingual copy that the page is known to ship on each stream."""
    ws = _workspace(page)
    tips = _tip_text(ws)
    assert len(tips) > 1000, f"tip stream implausibly short ({len(tips)} chars)"
    assert "quiet-to-frantic scale" in tips, "EN tip copy missing from the tip stream"
    assert "清淡至狂热刻度" in tips, "ZH tip copy missing from the tip stream"

    assert "Options workspace modes" in _aria_text(ws), "aria stream lost the mode tablist label"

    script = _script_authored_text(page)
    assert len(script) > 5000, f"script literal stream implausibly short ({len(script)} chars)"
    assert "day-trading" in script and "日内交易" in script, "script stream lost its tip constants"
    # Normalisation must kill the attribute NAME (`n=` hides inside `data-tip-en="`)
    # without touching the value it introduces.
    assert 'data-tip-en="' not in script, "attribute-name normalisation regressed"


def test_tier2_carve_out_is_exactly_the_doctrines_own_example(page):
    """The carve-out is not a judgement call left open — it is pinned to the one
    sentence docs/DESIGN_DOCTRINE.md Law 5 offers as COMPLIANT Tier-2 copy.

    Narrow it and that sentence fails the hover sweep; widen it and a term with
    no sanctioned home starts passing.  Both directions are asserted here."""
    doctrine_receipt = ("backtested basket-level turn = null edge (Oracle P8, n=26); "
                        "slow reco labels unchanged; display tier.")
    assert _banned_vocabulary_hits(doctrine_receipt, BANNED_ON_TIER_2) == {}, (
        "the hover sweep now rejects the doctrine's own example of compliant Tier-2 copy"
    )
    # ...and it is genuinely a carve-out: the Tier-1 list still rejects it, which
    # is the whole reason hover copy needs its own list.
    assert set(_banned_vocabulary_hits(doctrine_receipt)) == {"Oracle P", "n=", "slow reco"}

    # Nothing beyond the receipt vocabulary was quietly let through.  `0DTE` is
    # named explicitly: it is an acronym this workspace never defines, so the
    # hover is not its home either (Tier 3 is — zero-dte-regime.md).
    assert TIER2_RECEIPT_VOCABULARY == {
        "Oracle P", "n=", "slow reco", "FDR", "z-score", "t-stat", "rank-IC",
    }
    for still_banned in ("0DTE", "IGNITION", "expected-null", "pain_dist", "validated"):
        assert still_banned in BANNED_ON_TIER_2, f"{still_banned} must stay banned on Tier 2"


def test_every_panel_answers_so_what_do_i_do(page):
    """Doctrine Law 1 — every footer answers "so what do I do?" in plain words.

    A stance CHIP is one way to answer; a plain caveat sentence is another, and both
    satisfy Law 1.  What Law 1 forbids is a footer that answers nothing.  The older
    form of this test asserted the chip specifically ("a panel with a footer must
    carry a stance"), which read `WORKSPACE_DESIGN_SPEC.md` §16's per-panel word
    budget as a per-panel MANDATE.  It is a CEILING — a panel with zero chips meets
    it exactly as well as one with a single chip (W1_DESIGN_SPEC §0.13).  Reading it
    as a mandate is what stacked the identical "Watch — don't chase" chip down the
    page until it read as boilerplate; the count is governed by the verdict law
    instead (see test_exactly_one_verdict_surface).
    """
    ws = _workspace(page)
    foots = re.findall(r'<div class="oew-pfoot">(.*?)</div>', ws, re.S)
    assert len(foots) >= 4
    # A chip, or enough prose to be a real sentence in both languages. The bar is
    # deliberately low — it catches a footer that says NOTHING, not one that chose
    # prose over a chip.
    mute = [f for f in foots if "oew-stance" not in f and len(_visible_text(f).split()) < 6]
    assert not mute, f"{len(mute)} footers answer nothing: {mute}"


def test_exactly_one_verdict_surface(page):
    """`OIP_MASTERPLAN.md` §3 verdict law, its machine-checkable half: *"one
    `data-verdict-surface` marker per page; CI greps for duplicates."*

    The marker sits on the Ticker name-header's `.oew-ic-foot` row (placement pinned
    by `W1_DESIGN_SPEC.md` §5.1).  That row is inside `renderTicker()`'s JS string,
    so this greps the WHOLE page, not `_workspace()` — the script block sits after
    the `<!-- /oew -->` boundary.  Comments are stripped first so that prose ABOUT
    the marker never counts as a second one.
    """
    stripped = re.sub(r"<!--.*?-->", " ", page, flags=re.S)
    assert stripped.count("data-verdict-surface") == 1, (
        f"{stripped.count('data-verdict-surface')} verdict surfaces — the law allows one"
    )


def test_chrome_caveats_keep_the_sentence_and_drop_the_chip(page):
    """The two pre-existing chrome spots state their caveat and cast no second verdict.

    Both duplicated the read's decision element: `.oew-nofuse` rides the persistent
    header, so its chip repeated on all four mode tabs, and "Today's measured flow"
    sits below the name header that already carries the marker.  The SENTENCES are
    the valuable half — they survive verbatim in both languages, with the as-of stamp
    where there is one.  (Follow-up flagged by `W1_DESIGN_SPEC.md` §0.13.)
    """
    nofuse = re.search(r'<div class="oew-nofuse">(.*?)</div>', page, re.S)
    assert nofuse, "the non-fusion banner is gone"
    banner = nofuse.group(1)
    assert "oew-stance" not in banner, "non-fusion banner still ships a stance chip"
    assert "Four readings, shown side by side and never averaged into one score." in banner
    assert "四项读数并列呈现，不会合成单一评分。" in banner

    # "Today's measured flow" is JS-built, so assert against the script source.
    flow = re.search(r"Today’s measured flow(.*?)oew-shelf", page, re.S)
    assert flow, "the measured-flow panel is gone"
    seg = flow.group(1)
    assert "oew-stance" not in seg, "measured-flow footer still ships a stance chip"
    assert "Size is a solid read." in seg
    assert "规模数据可靠。" in seg
    assert "oew-asof" in seg, "measured-flow footer lost its as-of stamp"


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
# main() — the "always exits 0" contract (#F1-08)
# ─────────────────────────────────────────────────────────────────────────────
def test_main_exits_zero_even_when_write_page_raises(monkeypatch, tmp_path):
    """The docstring's contract (§5): the builder always exits 0.  write_page
    and the second, redundant context-build-for-logging used to sit OUTSIDE
    the render() try/except, so an exception in either escaped main() despite
    the contract's promise."""
    import scripts.build_options_command as boc

    def _boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr("lib.pages.write_page", _boom)
    rc = boc.main(["--root", str(REPO), "--out", str(tmp_path / "options.html")])
    assert rc == 0
    assert not (tmp_path / "options.html").exists()


def test_main_exits_zero_on_a_genuine_render_failure(monkeypatch, tmp_path):
    import scripts.build_options_command as boc

    def _boom(*_a, **_k):
        raise RuntimeError("template exploded")

    monkeypatch.setattr(boc, "render", _boom)
    rc = boc.main(["--root", str(REPO), "--out", str(tmp_path / "options.html")])
    assert rc == 0


def test_main_writes_the_page_on_the_happy_path(tmp_path):
    import scripts.build_options_command as boc
    out = tmp_path / "options.html"
    rc = boc.main(["--root", str(REPO), "--out", str(out)])
    assert rc == 0
    assert out.exists() and out.stat().st_size > 0


# ─────────────────────────────────────────────────────────────────────────────
# Lazy-mode JS renderers actually produce content from their payload (#F2-05c)
# ─────────────────────────────────────────────────────────────────────────────
import json as _json  # noqa: E402
import shutil as _shutil  # noqa: E402
import subprocess as _subprocess  # noqa: E402

_HAS_NODE = _shutil.which("node") is not None
_needs_node = pytest.mark.skipif(not _HAS_NODE, reason="node not on PATH")


def _extract_workspace_script(rendered: str) -> str:
    """The workspace's one inline <script>'s IIFE body (everything up to but
    excluding the closing `})();`) — renderScanner/Ticker/Leaders are
    closure-local, so a test call must be spliced INSIDE it."""
    anchor = rendered.index("<!-- /oew -->")
    start = rendered.index("<script>", anchor) + len("<script>")
    end = rendered.index("</script>", start)
    body = rendered[start:end].strip()
    assert body.endswith("})();"), "options.html.j2's script no longer ends in the expected IIFE close"
    return body[: -len("})();")]


_DOM_STUB = """
var document = { querySelectorAll: function(){ return []; },
                  getElementById: function(){ return null; },
                  addEventListener: function(){} };
var location = { hash: '', search: '' };
var history = { replaceState: function(){} };
var fetch = function(){ return Promise.reject(new Error('fetch disabled in test')); };
"""


@_needs_node
def test_lazy_mode_renderers_produce_non_empty_markup_from_their_payload(page):
    """The three lazy modes render as literally empty <section> containers
    filled at runtime by JS (templates/options.html.j2:850-856).  The existing
    suite (test_all_four_mode_containers_render,
    test_lazy_payloads_use_plain_fetch_not_injected_script_loaders) asserts
    only the container id and the fetch URL literal — never that the renderer
    produces ANY content from its own fixture payload.  All three could
    silently render empty and stay green (#F2-05c)."""
    driver = _DOM_STUB + _extract_workspace_script(page) + """
    var hostScanner = { innerHTML: '' };
    renderScanner(hostScanner, { rows: [
      { ticker: 'AAPL', sector: 'Tech', spot: 210.5, iv30: 0.28,
        gross_premium_mn: 120.0, net_prem_mn: 40.0, net_prem_tone: 'call-leaning',
        asof: '2026-07-24', dist_to_flip_pct: 0.5, gamma_regime: 'long' }
    ] });

    var hostLeaders = { innerHTML: '' };
    renderLeaders(hostLeaders, {
      as_of: '2026-07-24T00:00:00+00:00', stale: false,
      board_a: [{ ticker: 'MARA', sector: 'Crypto', recurrence_count: 6,
                  A1_flow_recur: true, fire_a: false, de_escalation: {} }],
      board_b: [],
    });

    var hostTicker = { innerHTML: '' };
    renderTicker(hostTicker, 'SPY',
      { meta: { en: 'SPY name', asof: '2026-07-24' },
        summary: { spot: 500, regime: 'long', gamma_flip: 490,
                   call_wall: 520, put_wall: 480, max_pain: 495 },
        expected_move: { daily_pct: 1.1 } },
      { premium_mn: 900, zerodte_share: 0.4, pc_ratio: 0.8,
        net_premium_mn: 120, asof: '2026-07-24' });

    process.stdout.write(JSON.stringify({
      scanner: hostScanner.innerHTML,
      leaders: hostLeaders.innerHTML,
      ticker: hostTicker.innerHTML,
    }));
    })();
    """
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = _json.loads(res.stdout.strip().splitlines()[-1])
    assert "AAPL" in out["scanner"], "renderScanner produced no visible content from its payload"
    assert "MARA" in out["leaders"], "renderLeaders produced no visible content from its payload"
    assert "SPY" in out["ticker"], "renderTicker produced no visible content from its payload"
    for key, val in out.items():
        assert val.strip(), f"render{key} produced empty markup"


@_needs_node
def test_lazy_mode_renderers_show_empty_state_for_an_empty_payload(page):
    """The honest-empty path (no rows / no boards / no chain) must also
    produce SOME markup — not a silently blank host."""
    driver = _DOM_STUB + _extract_workspace_script(page) + """
    var hostScanner = { innerHTML: '' };
    renderScanner(hostScanner, { rows: [] });
    var hostLeaders = { innerHTML: '' };
    renderLeaders(hostLeaders, null);
    var hostTicker = { innerHTML: '' };
    renderTicker(hostTicker, 'ZZZZ', null, null);
    process.stdout.write(JSON.stringify({
      scanner: hostScanner.innerHTML, leaders: hostLeaders.innerHTML, ticker: hostTicker.innerHTML,
    }));
    })();
    """
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = _json.loads(res.stdout.strip().splitlines()[-1])
    for key, val in out.items():
        assert "oew-empty" in val, f"render{key} did not show an honest empty state"


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
