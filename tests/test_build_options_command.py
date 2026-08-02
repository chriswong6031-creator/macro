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
# Shared with test_no_banned_vocabulary_in_js_rendered_states (Addition-1 fix,
# adversarial review round 2): one list, so the static-copy sweep and the
# JS-execution sweep can never silently diverge on what counts as banned.
BANNED_VOCABULARY = [
    "IGNITION", "UPTURN_CONFIRMED", "slow reco", "expected-null", "forward meter",
    "display-tier", "K-of-N", "gauntlet", "prereg", "Oracle P", "FlowZ", "TSBrd",
    "NotTrap", "PriceOK", "NearHigh", "VolOK", "TurnOrg", "Inflect", "n=", "FDR",
    "z-score", "t-stat", "rank-IC", "cross-sectional", "multi-timeframe",
    "validated", "us_sector", "yCaution", "BothSides", "EarnWin",
    "pain_dist", "median_depth", "wilson_", "0DTE",
]

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
// OIP W1: window.OEW_TICKER_MANIFEST is now the workspace script's own first
// statement (the manifest embed shares its <script> tag with the IIFE — see
// _extract_workspace_script), so a bare Node eval needs a minimal window global
// to assign onto, same as it already needs document/location/history/fetch.
var window = { addEventListener: function(){} };
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


# ═══════════════════════════════════════════════════════════════════════════════
# OIP W1 — Ticker search/typeahead, the session filmstrip, the five new depth
# reads, and declared-cap copy (research/options_estate/W1_DESIGN_SPEC.md)
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# Declared caps (§6) — fixed copy, baked into the JS source regardless of payload
# ─────────────────────────────────────────────────────────────────────────────
def test_scanner_declares_its_cap_and_links_to_the_full_screener(page):
    assert "Top 200 by premium, sorted" in page
    assert "按权利金排序，前200" in page
    assert 'class="oew-ph-more" href="options_screener.html"' in page
    assert "Open the full screener for all " in page
    assert "打开完整筛选台，查看全部 " in page
    # the masterplan's own "384" example is a snapshot, not a literal — the cap
    # sentence itself must never hardcode a name count (a literal DIGIT count,
    # not the LIVE rows.length reference — the minor fix below intentionally
    # composes 'rows.length + \' names\'' as its honest, sub-200 fallback, so
    # that exact source string is no longer itself a defect signal).
    assert "384" not in page
    # §0.20 minor fix: "Top 200" is a lie when the payload never had 200 rows
    # to truncate — the subtitle must be conditioned on the real count, never
    # unconditional.
    assert "rows.length > 200" in page


@_needs_node
def test_scanner_subtitle_only_claims_the_cap_when_it_actually_truncates(page):
    """Behavioral regression for the §0.20 minor: at <=200 rows nothing is cut,
    so 'Top 200' would be exactly the undeclared-cap-shaped lie this sentence
    exists to prevent. Runs renderScanner for real, at both sides of the cap."""
    def _rows(n):
        return ", ".join(
            "{ ticker: 'T%d', sector: 'Tech', spot: 100, iv30: 0.2, "
            "gross_premium_mn: %d, net_prem_mn: 1, net_prem_tone: 'call-leaning', "
            "asof: '2026-07-24', dist_to_flip_pct: 0.1, gamma_regime: 'long' }"
            % (i, 1000 - i) for i in range(n)
        )
    cases = [(47, "47 names, sorted by premium", "47 个标的，按权利金排序", "Top 200"),
             (250, "Top 200 by premium, sorted", "按权利金排序，前200", "250 names")]
    for n, want_en, want_zh, must_not in cases:
        driver = (_DOM_STUB + _extract_workspace_script(page) + """
        var host = { innerHTML: '' };
        renderScanner(host, { rows: [ """ + _rows(n) + """ ] });
        process.stdout.write(host.innerHTML);
        })();
        """)
        res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
        assert res.returncode == 0, f"node failed (n={n}):\nSTDERR:\n{res.stderr}"
        out = res.stdout
        assert want_en in out, f"n={n}: missing {want_en!r} in subtitle"
        assert want_zh in out, f"n={n}: missing {want_zh!r} in subtitle"
        sub = out[out.index('class="oew-ph-sub"'): out.index("oew-ph-more")]
        assert must_not not in sub, f"n={n}: {must_not!r} must not appear in the subtitle — got {sub!r}"


def test_leaders_declares_both_board_caps_derived_not_hardcoded(page):
    """MAJOR-1 fix (adversarial review round 2): the declared-cap sentence must
    derive its denominator from the arrays already in hand (boardAAll.length /
    boardBFiltered.length), never from L.board_a_total / L.board_b_total — both
    of those are PRE-`_BOARD_CAP` totals in scripts/build_flow_leaders.py's own
    payload (measured board_a_total: 130 vs the 25 rows the builder actually
    ships), so trusting them here previously told a reader the full board held
    130 names when only 25 were ever reachable at the linked URL."""
    assert "L.board_a_total" not in page
    assert "L.board_b_total" not in page
    assert "var boardAAll = L.board_a" in page
    assert "var boardBFiltered = (L.board_b || []).filter" in page
    assert "top 12 of ' + aTotal + ', by recurrence'" in page
    assert "top 12 of ' + bTotal + ', most recent first'" in page
    assert page.count('class="oew-ph-more" href="flow_leaders.html"') == 2
    assert page.count("Open the full boards") >= 2


def _leaders_row_a(ticker: str) -> dict:
    return {
        "ticker": ticker, "sector": "Technology", "fire_a": False,
        "recurrence_count": 5, "days_since_inflection": None, "de_escalation": None,
        "signing_source": "tape", "zerodte_dominated": False,
        "A1_flow_recur": True, "A2_flow_z_hot": True, "A3_oi_confirmed": True,
        "A4_ts_breadth": False, "A5_price_leader": True, "A6_near_high": True,
        "A7_vol_confirm": None, "A8_not_trap": True,
    }


def _leaders_row_b(ticker: str, inflect: bool) -> dict:
    return {
        "ticker": ticker, "sector": "Technology", "fire_b": False,
        "recurrence_count": 2, "days_since_inflection": 2, "de_escalation": None,
        "signing_source": "tape", "zerodte_dominated": False,
        "B1_washout_recent": True, "B2_oversold_osc": True, "B3_turn_organ": True,
        "B5_flow_inflect": inflect, "B6_oi_confirmed": False, "B7_vol_confirm": None,
        "B8_not_trap": True,
    }


def _render_flow_leaders_page(payload: dict) -> str:
    from jinja2 import Environment, FileSystemLoader  # noqa: PLC0415
    env = Environment(loader=FileSystemLoader(str(REPO / "templates")), autoescape=False)
    return env.get_template("flow_leaders.html.j2").render(flow_leaders=payload)


@_needs_node
def test_leaders_denominator_equals_the_row_count_flow_leaders_html_renders(page):
    """MAJOR-1's own required regression: the stated denominator must equal the
    row count the LINKED surface (site/flow_leaders.html) actually renders, not
    a re-derivation of the same formula on both sides. Board A ships 15 rows
    (>12, so the panel's own top-12 display slice truncates something real);
    board B ships 15 rows, 9 of which pass B5_flow_inflect (the corrected #3496
    admission rule both surfaces apply identically) and 6 of which do not.

    Renders BOTH surfaces from the exact same payload — flow_leaders.html.j2
    via Jinja (the real linked page) and renderLeaders() via node (this
    panel's own JS) — and cross-checks the row counts, not just the numbers
    each side independently computes."""
    board_a = [_leaders_row_a(f"AT{i:02d}") for i in range(15)]
    board_b = ([_leaders_row_b(f"BT{i:02d}", True) for i in range(9)]
               + [_leaders_row_b(f"BX{i:02d}", False) for i in range(6)])
    payload = {
        "as_of": "2026-07-30T00:00:00+00:00", "stale": False,
        "coverage": {"n_universe": 30, "n_flow_sessions": 134, "flow_z_live": True,
                     "tape_names": 30, "n_etfs": 0},
        "board_a": board_a, "board_a_total": 999,   # deliberately WRONG pre-cap
        "board_b": board_b, "board_b_total": 999,   # decoy — must never be read
        "etf_strip": [],
        "cold_start_detail": {"n_sessions": 134, "required_for_recurrence": 20, "message": None},
    }

    # 1) The real linked page, rendered from the SAME payload.
    fl_html = _render_flow_leaders_page(payload)
    a_start = fl_html.index("Where money keeps landing")
    b_start = fl_html.index("Turning up from a beating")
    a_section, b_section = fl_html[a_start:b_start], fl_html[b_start:]
    a_rendered = len(re.findall(r'<div class="fl-row', a_section))
    b_rendered = len(re.findall(r'<div class="fl-row', b_section))
    assert a_rendered == 15, "flow_leaders.html board A row count drifted from the fixture"
    assert b_rendered == 9, "flow_leaders.html board B row count drifted from the B5_flow_inflect filter"

    # 2) This panel's own JS, from the SAME payload.
    driver = (_DOM_STUB + _extract_workspace_script(page) + """
    var host = { innerHTML: '' };
    renderLeaders(host, """ + _json.dumps(payload) + """);
    process.stdout.write(host.innerHTML);
    })();
    """)
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = res.stdout
    a_sub = re.search(r"top 12 of (\d+), by recurrence", out)
    b_sub = re.search(r"top 12 of (\d+), most recent first", out)
    assert a_sub and b_sub, f"declared-cap sentence not found in renderLeaders output: {out!r}"

    # 3) Cross-surface parity — the whole point of this regression.
    assert int(a_sub.group(1)) == a_rendered == 15
    assert int(b_sub.group(1)) == b_rendered == 9
    assert "999" not in out, "the decoy pre-cap board_a_total/board_b_total leaked into the sentence"


@_needs_node
def test_where_positions_built_bars_share_one_scale_across_both_columns(page):
    """MAJOR-2 fix (adversarial review round 2): pbCol() used to normalize each
    column (Built/Unwound) to its OWN max, so a much larger unwind and a much
    smaller build could draw at the SAME bar length — the PR's own ZH crop
    showed a +16,279 build and a -27,654 unwind both at 100%. A single shared
    maximum across both columns must make bar length comparable everywhere in
    the panel: the larger absolute value (here the unwind, 1.7x the build)
    must never draw shorter than the smaller one."""
    gx = """{
      meta: { asof: '2026-07-30' },
      summary: { spot: 100, regime: 'long', gamma_flip: 95, call_wall: 110, put_wall: 90, max_pain: 100 },
      expected_move: {},
      oi_delta_clusters: {
        new_oi: [ { K: 100, right: 'call', oi_delta: 16279 } ],
        exit_oi: [ { K: 90, right: 'put', oi_delta: -27654 } ]
      }
    }"""
    driver = (_DOM_STUB + _extract_workspace_script(page) + """
    var host = { innerHTML: '' };
    renderTicker(host, 'SPY', """ + gx + """, null, null);
    process.stdout.write(host.innerHTML);
    })();
    """)
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = res.stdout
    i = out.index("Where positions built")
    panel = out[i: out.index("oew-pfoot", i)]
    widths = [int(w) for w in re.findall(r'style="width:(\d+)%"', panel)]
    assert len(widths) == 2, f"expected exactly one bar per column, got {widths}"
    build_w, unwind_w = widths  # Built column renders before Unwound in the markup
    assert unwind_w == 100, widths
    assert build_w < unwind_w, (
        f"a larger absolute value (-27,654 unwind) rendered no longer than the "
        f"smaller one (+16,279 build): build={build_w}% unwind={unwind_w}%"
    )
    assert build_w == round(16279 / 27654 * 100), widths


def test_where_positions_built_single_row_column_no_longer_pins_its_own_bar_to_100pct(page):
    """Companion to the shared-scale fix: even a column with exactly one row
    must scale against the OTHER column's max, not default back to filling its
    own track (the pre-fix behavior for every single-row column, regardless of
    the other column's size)."""
    src = (REPO / "templates" / "options.html.j2").read_text(encoding="utf-8")
    assert "function pbCol(rows, unwind, sharedMax)" in src
    assert "var top = 0;" not in src.split("function pbCol")[1].split("function ", 1)[0]
    assert "var pbMax = 0;" in src
    assert "pbBuilt.concat(pbUnwound).forEach" in src


# ─────────────────────────────────────────────────────────────────────────────
# Ticker-mode search toolbar — static markup + manifest wiring
# ─────────────────────────────────────────────────────────────────────────────
def test_ticker_search_toolbar_is_static_sibling_of_the_render_target(page):
    section = page[page.index('id="mode-ticker"') - 40: page.index('id="mode-ticker"') + 1400]
    assert 'id="oew-tk-q"' in section
    assert 'role="combobox"' in section
    assert 'aria-controls="oew-tk-sugg"' in section
    assert 'id="oew-tk-sugg"' in section
    assert 'role="listbox"' in section
    assert 'id="oew-tk-body"' in section
    # the toolbar must precede the render target, both inside the same section
    assert section.index('id="oew-tk-q"') < section.index('id="oew-tk-body"')


def test_ticker_manifest_embeds_the_real_gex_index_payload(page):
    assert "window.OEW_TICKER_MANIFEST = " in page
    m = re.search(r"window\.OEW_TICKER_MANIFEST = (\[.*?\]);", page, re.S)
    assert m
    data = _json.loads(m.group(1))
    # Addition-2 fix (adversarial review round 2): the embed is a SLIM key/en/zh
    # projection of stores["gex_index"], not the full ~26-field manifest row —
    # setupTickerSearch() (below) reads only those three fields. The fixture's
    # own gex_index entries carry no en/zh, so the projection nulls them.
    assert data == [{"key": k, "en": None, "zh": None} for k in INDEX_KEYS]


def test_ticker_manifest_omits_fields_the_search_never_reads(page):
    """Addition-2 regression: a real gex_index row carries ~26 fields (spot,
    iv30, gamma_flip, call_wall, put_wall, max_pain, asof, ...) that
    setupTickerSearch() never touches. Those must not reach the embedded
    manifest — both because they are dead weight (649 rows x 26 fields grew
    this page 123,775 -> 544,320 bytes) and because a build-time-frozen price
    sitting in a Ticker-mode DOM looks live when it is not."""
    stores = _stores()
    stores["gex_index"] = [{
        "key": "SPY", "en": "SPY name", "zh": "SPY 名称", "grp": "Index", "src": "core",
        "spot": 500.0, "regime": "long", "tier": "full", "thin": False,
        "net_gex_bn": 1.2, "gamma_flip": 490.0, "dist_to_flip_pct": -1.4, "iv30": 12.5,
        "call_wall": 520.0, "put_wall": 480.0, "call_wall_band": "near", "put_wall_band": "near",
        "max_pain": 495.0, "daily_move_pct": 0.9, "put_call_oi_ratio": 0.8,
        "vh_state": "none", "vh_bias": None, "tilt_read": "flat", "skew_tone": "neutral",
        "iv_rank_band": "normal", "asof": "2026-07-24",
    }]
    out = render(REPO, stores)
    m = re.search(r"window\.OEW_TICKER_MANIFEST = (\[.*?\]);", out, re.S)
    assert m
    row = _json.loads(m.group(1))[0]
    assert set(row) == {"key", "en", "zh"}, f"manifest row carries dead fields: {set(row) - {'key', 'en', 'zh'}}"
    assert row == {"key": "SPY", "en": "SPY name", "zh": "SPY 名称"}


def test_search_match_predicate_is_structurally_identical_to_gexjs(page):
    """gex.js's setupSearch() filter (site/gex.js ~line 290) — the new search
    must reproduce it EXACTLY, not a paraphrase. Compares the two predicates
    with only cosmetic differences (quote style, variable name m vs m) removed."""
    gexjs = (REPO / "site" / "gex.js").read_text(encoding="utf-8")
    gex_pred = re.search(
        r'return !q \|\| m\.key\.indexOf\(q\) === 0 \|\| m\.key\.indexOf\(q\) >= 0 '
        r'\|\| \(m\.en \|\| ""\)\.toUpperCase\(\)\.indexOf\(q\) >= 0;',
        gexjs,
    )
    assert gex_pred, "gex.js's own match predicate moved — update this pin"
    ticker_pred = re.search(
        r"return !q \|\| m\.key\.indexOf\(q\) === 0 \|\| m\.key\.indexOf\(q\) >= 0 "
        r"\|\| \(m\.en \|\| ''\)\.toUpperCase\(\)\.indexOf\(q\) >= 0;",
        page,
    )
    assert ticker_pred, "Ticker-mode search predicate not found or has drifted from gex.js's"


def test_search_result_cap_is_12(page):
    assert ".slice(0, 12)" in page


def test_search_row_selection_is_mousedown_not_click(page):
    """Survives the input's own blur handler — click would fire after blur has
    already closed the panel."""
    section = page[page.index("setupTickerSearch"):]
    body = section[: section.index("setupTickerSearch();")]
    assert "addEventListener('mousedown'" in body
    assert "addEventListener('click'" not in body
    assert "e.preventDefault();" in body


def test_search_blur_closes_after_150ms(page):
    section = page[page.index("setupTickerSearch"):]
    body = section[: section.index("setupTickerSearch();")]
    assert "setTimeout(close, 150)" in body


def test_search_focus_ring_uses_the_workspace_accent_not_gex_info(page):
    assert ".oew-tksearch input:focus-visible{outline:2px solid var(--oew-accent)" in page
    assert ".oew-tksearch input:focus-visible{outline:2px solid var(--info)" not in page


def test_slash_shortcut_is_scoped_to_active_ticker_mode(page):
    """§0.16: gex.html's sitewide .nav-search has zero '/' bindings, so no
    collision is possible — but the binding must still guard on #mode-ticker
    being the ACTIVE mode, or it would silently focus an off-screen input."""
    section = page[page.index("setupTickerSearch"):]
    body = section[: section.index("setupTickerSearch();")]
    assert "e.key !== '/'" in body
    assert "INPUT|TEXTAREA|SELECT" in body
    assert "getElementById('mode-ticker')" in body
    assert "classList.contains('active')" in body


@_needs_node
def test_search_behavior_end_to_end():
    """A fuller DOM stub: real event registration + a crude innerHTML->rows
    parse, so this drives the ACTUAL match/cap/keyboard/select code paths
    rather than just pinning their source text.

    Renders its OWN page (not the shared `page` fixture) with a purpose-built
    gex_index, because window.OEW_TICKER_MANIFEST is the workspace script's own
    FIRST statement (baked server-side from ticker_manifest_json) — it assigns
    over anything a test pre-seeds on `window` before the extracted script runs,
    so the only way to control what setupTickerSearch() sees is through the
    fixture the template is rendered against.
    """
    manifest_stores = _stores()
    manifest_stores["gex_index"] = [
        {"key": "SPY", "en": "SPY name", "zh": "SPY 名称", "asof": "2026-07-24"},
        {"key": "SPX", "en": "SPX name", "zh": "SPX 名称", "asof": "2026-07-24"},
        {"key": "SPWR", "en": "SunPower", "zh": "", "asof": "2026-07-24"},
    ] + [
        {"key": f"ZZ{i}", "en": f"S-name {i}", "zh": "", "asof": "2026-07-24"}
        for i in range(20)
    ]
    page = render(REPO, manifest_stores)

    driver = _DOM_STUB + """
    function FakeEl(tag){
      this.tagName = (tag || 'DIV').toUpperCase();
      this._listeners = {}; this._attrs = {}; this._classes = {};
      this.classList = {
        add: (c) => { this._classes[c] = true; },
        remove: (c) => { delete this._classes[c]; },
        contains: (c) => !!this._classes[c],
      };
    }
    FakeEl.prototype.addEventListener = function(t, fn){ (this._listeners[t] = this._listeners[t] || []).push(fn); };
    FakeEl.prototype.setAttribute = function(k, v){ this._attrs[k] = String(v); };
    FakeEl.prototype.getAttribute = function(k){ return this._attrs[k] === undefined ? null : this._attrs[k]; };
    FakeEl.prototype.fire = function(t, evt){ (this._listeners[t] || []).forEach((fn) => fn(evt || { preventDefault(){} })); };
    FakeEl.prototype.querySelectorAll = function(sel){ return sel === '.row' ? (this._rowEls || []) : []; };
    Object.defineProperty(FakeEl.prototype, 'innerHTML', {
      get(){ return this._html || ''; },
      set(v){
        this._html = v;
        var re = /<div class="row[^"]*" data-key="([^"]+)"/g, m, keys = [];
        while ((m = re.exec(v))) keys.push(m[1]);
        this._rowKeys = keys;
        this._rowEls = keys.map((k) => { var e = new FakeEl('div'); e.setAttribute('data-key', k); return e; });
      },
    });

    var inp = new FakeEl('input'), sg = new FakeEl('div');
    var docStub = {
      getElementById(id){
        if (id === 'oew-tk-q') return inp;
        if (id === 'oew-tk-sugg') return sg;
        if (id === 'mode-ticker') return { classList: { contains: () => true, toggle: () => {} } };
        return null;
      },
      querySelectorAll(){ return []; },
      addEventListener(t, fn){ (this._dl = this._dl || {})[t] = (this._dl[t] || []).concat(fn); },
      activeElement: { tagName: 'BODY' },
    };
    document = docStub;
    var histCalls = [];
    history = { replaceState(a, b, c){ histCalls.push(c); } };

    """ + _extract_workspace_script(page) + """
    var results = {};

    // 1) typing a query beginning with 'S' matches SPY/SPX/SPWR by prefix, plus
    //    every S-prefixed ZZ.. name never matches (they don't start with S) —
    //    so exactly the 3 seeded S-tickers show, well under the 12 cap.
    inp.value = 'SP';
    inp.fire('input');
    results.matchedSP = sg._rowKeys.slice();

    // 2) a query matching MANY names caps at 12
    inp.value = '';
    inp.fire('focus');
    results.cappedAt12 = sg._rowKeys.length;

    // 3) selecting a row via mousedown updates the URL hash to that ticker
    inp.fire('input');
    var pick = sg._rowEls[0];
    pick.fire('mousedown');
    results.selectedHash = histCalls[histCalls.length - 1];
    results.inputClearedAfterSelect = inp.value;

    // 4) Escape closes the panel
    inp.value = 'S';
    inp.fire('input');
    inp.fire('keydown', { key: 'Escape', preventDefault(){} });
    results.closedOnEscape = !sg.classList.contains('on');

    // 5) the global "/" shortcut focuses the input while Ticker mode is active
    var focused = false;
    inp.focus = function(){ focused = true; };
    docStub._dl.keydown.forEach((fn) => fn({ key: '/', preventDefault(){} }));
    results.slashFocused = focused;

    process.stdout.write(JSON.stringify(results));
    })();
    """
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = _json.loads(res.stdout.strip().splitlines()[-1])
    assert set(out["matchedSP"]) == {"SPY", "SPX", "SPWR"}, out["matchedSP"]
    assert out["cappedAt12"] == 12
    assert out["selectedHash"] == "#ticker?t=SPY"
    assert out["inputClearedAfterSelect"] == ""
    assert out["closedOnEscape"] is True
    assert out["slashFocused"] is True


# ─────────────────────────────────────────────────────────────────────────────
# The five new Ticker-mode depth reads — present AND absent/degraded states
# ─────────────────────────────────────────────────────────────────────────────
_GX_FULL = """{
  meta: { en: 'Test Co', zh: '测试公司', asof: '2026-07-30' },
  summary: {
    spot: 500, regime: 'long', gamma_flip: 490, call_wall: 520, put_wall: 480,
    max_pain: 495, call_wall_strength: 80, put_wall_strength: 60, flip_strength: 50,
    magnet_strength: 40, iv30: 22.5, put_call_oi_ratio: 0.9,
    iv_rank: { rank_pct: 43, band: 'normal', n_days: 37, low_confidence: false, horizon: '40d' }
  },
  expected_move: { daily_pct: 1.1 },
  wall_persistence: {
    // board_wall is ALWAYS the row's own dealer-gamma wall (engine/gex_state.py's
    // _wall_persistence sets it from the same call_wall/put_wall this model's own
    // summary carries — 520/480 above) — it is the comparison operand
    // matches_board_wall was computed against, never a second reading to print.
    // level is the independent open-interest wall (B2 regression fixture: the
    // put side used to hand-type board_wall=475, DIFFERENT from summary.put_wall
    // =480, a combination the real engine can never produce — that mismatch is
    // what let the old code's board_wall-reading bug look, in this test, like it
    // was printing two genuinely different numbers).
    call_side: { level: 520, sessions_at_level: 3, matches_board_wall: true, board_wall: 520 },
    put_side: { level: 475, sessions_at_level: 2, matches_board_wall: false, board_wall: 480 }
  },
  oi_delta_clusters: {
    new_oi: [ { K: 525, right: 'put', oi_delta: 196512 }, { K: 750, right: 'call', oi_delta: 86210 } ],
    exit_oi: [ { K: 660, right: 'put', oi_delta: -18624 } ],
    latest_snapshot: '2026-07-30', spot_note_en: 'Snapshot price differs from the board.',
    spot_note_zh: '快照价格与看板不同。'
  },
  net_gex_pctile: { note_en: 'Net GEX sits above 62% of this name’s own stored daily readings.',
                     note_zh: '净GEX高于该标的自身62%的每日记录。' }
}"""
_GX_MINIMAL = """{
  meta: { en: 'Thin Co', zh: '', asof: '2026-07-30' },
  summary: { spot: 10, regime: 'short', gamma_flip: 9, call_wall: 11, put_wall: 8, max_pain: 10 },
  expected_move: {}
}"""
_SESS_FULL = """{
  session_date: '2026-07-30',
  filmstrip_html: '<figure class=\\'ilx oew-film\\' role=\\'img\\'><svg></svg></figure>',
  coverage: { minutes: 300, expected: 391, quality_en: 'The intraday record covers most of the session', quality_zh: 'q' },
  arc_shape_en: 'built steadily in one direction and stayed', arc_shape_zh: '全天单向累积并维持',
  flip: { crosses: 2, last_side: 'above' }
}"""


@_needs_node
def test_ticker_five_new_reads_present_state(page):
    # NOT an f-string: the JS payloads below are full of literal { } that an
    # f-string would try (and fail) to parse as Python expressions.
    driver = (_DOM_STUB + _extract_workspace_script(page) + """
    var host = { innerHTML: '' };
    renderTicker(host, 'NVDA', """ + _GX_FULL + """, null, """ + _SESS_FULL + """);
    process.stdout.write(host.innerHTML);
    })();
    """)
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = res.stdout

    # 1. the filmstrip panel renders the pre-baked SSR fragment verbatim, and
    #    the client-composed sentence matches the spec's worked example
    #    EXACTLY, byte for byte — including the ZH punctuation seam between
    #    the shape clause's own '。' and the flip clause ('。穿越', never the
    #    '。，' a naive concatenation of two independently-punctuated
    #    fragments would produce.
    assert "How the day traded" in out and "今日如何交易" in out
    assert "<figure class='ilx oew-film'" in out
    assert "Premium built steadily in one direction and stayed. Crossed the flip twice, closed above it." in out
    assert "权利金全天单向累积并维持。穿越翻转位两次，收于其上方。" in out
    assert "。，" not in out, "stray period-then-comma in the filmstrip ZH sentence"

    # 2. the wall-check chips: Ceiling agrees (static tip, no $ interpolation —
    #    the "yes" branch never needs the strikes since they're the same one),
    #    Floor disagrees (both strikes interpolated: the independent OI wall
    #    $475 (block.level) and this row's own dealer-gamma wall $480, i.e.
    #    s.put_wall / ownValue — B2 regression: the chip used to read
    #    block.board_wall for the OI slot, which is ownValue's own value
    #    (475 would never have appeared; both slots printed 480).
    assert "oew-wcheck-yes" in out and "confirmed by open interest" in out
    assert "oew-wcheck-no" in out and "open interest disagrees" in out
    assert "($475)" in out and "($480)" in out  # put side's OI wall vs its own wall
    assert "（$475）" in out and "（$480）" in out  # ZH full-width parens twin
    disagree = out[out.index("oew-wcheck-no"):]
    disagree_tip = disagree[disagree.index('data-tip-en="'): disagree.index('">', disagree.index('data-tip-en="'))]
    assert "($475)" in disagree_tip and "($480)" in disagree_tip and (
        disagree_tip.index("($475)") != disagree_tip.index("($480)")
    ), "the two printed wall values must differ, not the same figure twice"

    # 3. Rich or cheap: real pip track + band word + sentence
    assert "Rich or cheap?" in out and "偏贵还是偏便宜？" in out
    assert 'class="oew-rich-pip on"' in out
    assert out.count('class="oew-rich-pip') >= 5
    assert "Normal" in out and "正常" in out  # IVR_BAND word, gex.js verbatim
    assert "cost more than <b class=\"mono\">43%</b>" in out
    assert "of the last <b class=\"mono\">37</b> sessions" in out
    assert "43rd percentile of the last 37 trading sessions" in out

    # 4. Where positions built: two columns, correct sign/color class, and the
    #    rare net_gex_pctile addendum + the spot-divergence receipt on the ?
    assert "Where positions built" in out and "仓位在何处建立" in out
    assert "525P" in out and "+196,512" in out
    assert "750C" in out and "+86,210" in out
    assert "660P" in out and "−18,624" in out
    assert 'class="v build mono"' in out
    assert "oew-pb-pctile" in out and "Net GEX sits above 62%" in out
    assert "Snapshot price differs from the board." in out

    # 5. the two empty-state panels ALWAYS render, even when everything else
    #    is present (E4/E7 are not built yet regardless of this name's coverage)
    assert "What the move is worth" in out and "本次波幅是否值得" in out
    assert "Expiration pressure" in out and "到期压力" in out
    assert out.count("oew-notyet-ghost") == 2
    assert "oew-notyet-cone" in out and "oew-notyet-bar" in out

    # 6. verdict law: EXACTLY one data-verdict-surface, and it is the ONLY
    #    stance chip among the five new/enhanced panels (§0.13 ruling)
    assert out.count("data-verdict-surface") == 1
    # the two always-empty panels and the three real-data new panels carry no
    # .oew-stance at all — only the pre-existing name-header hero and (when
    # present) "Today's measured flow" do.
    new_panel_stances = 0
    for marker in ("How the day traded", "Rich or cheap?", "Where positions built",
                   "What the move is worth", "Expiration pressure"):
        i = out.index(marker)
        panel = out[i: out.index("oew-pfoot", i) + 400]
        if 'class="oew-stance' in panel[: panel.index("</div>")]:
            new_panel_stances += 1
    assert new_panel_stances == 0


@_needs_node
def test_ticker_five_new_reads_absent_or_degraded_state(page):
    driver = (_DOM_STUB + _extract_workspace_script(page) + """
    var host = { innerHTML: '' };
    renderTicker(host, 'THIN', """ + _GX_MINIMAL + """, null, null);
    process.stdout.write(host.innerHTML);
    })();
    """)
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = res.stdout

    # 1. no session record at all -> the client-composed honest-null filmstrip,
    #    not a blank hole
    assert "oew-film-null" in out
    assert "No intraday record for this session" in out and "本交易日没有盘中记录" in out

    # 2. no wall_persistence block -> silence, not a "no data" chip
    assert "oew-wcheck" not in out

    # 3. no iv_rank at all -> the honest .oew-notyet treatment, named reason
    assert "Not enough price history on file yet" in out
    assert "该标的历史价格记录不足" in out

    # 4. no oi_delta_clusters -> the coverage-gap sentence, never a blank grid
    assert "oew-pb-note" in out
    assert "This name has no matched open-interest change on file for this close." in out
    assert 'class="oew-pb"' not in out  # the 2-column grid must NOT render

    # 5. still exactly one verdict surface (the name-header), zero stance chips
    #    anywhere in the five new/enhanced panels
    assert out.count("data-verdict-surface") == 1
    assert "oew-notyet-cone" in out and "oew-notyet-bar" in out


@_needs_node
def test_rich_or_cheap_low_confidence_shows_history_building_chip(page):
    gx = """{
      meta: { asof: '2026-07-30' },
      summary: { spot: 50, regime: 'long', gamma_flip: 48, call_wall: 52, put_wall: 47,
                 max_pain: 49, iv_rank: { rank_pct: 70, band: 'rich', n_days: 12, low_confidence: true } },
      expected_move: {}
    }"""
    driver = (_DOM_STUB + _extract_workspace_script(page) + """
    var host = { innerHTML: '' };
    renderTicker(host, 'YNG', """ + gx + """, null, null);
    process.stdout.write(host.innerHTML);
    })();
    """)
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    out = res.stdout
    assert "history building — 12d" in out
    assert "历史积累中 — 12天" in out
    # the pip track must NOT render alongside the building chip — never a track
    # with too few days behind it to mean anything
    rich = out[out.index("Rich or cheap?"):]
    rich = rich[: rich.index("oew-pfoot")]
    assert "oew-rich-pip on" not in rich


@_needs_node
def test_no_banned_vocabulary_in_js_rendered_states(page):
    """Addition-1 fix (adversarial review round 2): _visible_text() strips
    <script>...</script> wholesale (see test_no_banned_vocabulary_in_visible_copy's
    docstring, earlier in this file), so that sweep is structurally blind to
    every word renderTicker()/renderScanner()/renderLeaders() themselves
    generate — exactly the copy this wave added. This sweep executes all
    three, across the states the PR's own manual sweep claimed to cover
    (Ticker: full / minimal / young-iv_rank — reusing _GX_FULL/_SESS_FULL/
    _GX_MINIMAL, this file's own existing fixtures, so a change to those
    fixtures cannot silently narrow this sweep's coverage; Scanner and
    Leaders: one representative present-data state each), and greps the REAL
    rendered innerHTML rather than the source text. See
    test_no_banned_vocabulary_sweep_catches_a_planted_term for proof this
    sweep is not vacuously green."""
    gx_young = """{
      meta: { asof: '2026-07-30' },
      summary: { spot: 50, regime: 'long', gamma_flip: 48, call_wall: 52, put_wall: 47,
                 max_pain: 49, iv_rank: { rank_pct: 70, band: 'rich', n_days: 12, low_confidence: true } },
      expected_move: {}
    }"""
    driver = (_DOM_STUB + _extract_workspace_script(page) + """
    var out = {};

    var hostFull = { innerHTML: '' };
    renderTicker(hostFull, 'NVDA', """ + _GX_FULL + """, null, """ + _SESS_FULL + """);
    out.tickerFull = hostFull.innerHTML;

    var hostMinimal = { innerHTML: '' };
    renderTicker(hostMinimal, 'THIN', """ + _GX_MINIMAL + """, null, null);
    out.tickerMinimal = hostMinimal.innerHTML;

    var hostYoung = { innerHTML: '' };
    renderTicker(hostYoung, 'YNG', """ + gx_young + """, null, null);
    out.tickerYoung = hostYoung.innerHTML;

    var hostScanner = { innerHTML: '' };
    renderScanner(hostScanner, { rows: [
      { ticker: 'AAPL', sector: 'Tech', spot: 210.5, iv30: 0.28,
        gross_premium_mn: 120.0, net_prem_mn: 40.0, net_prem_tone: 'call-leaning',
        asof: '2026-07-24', dist_to_flip_pct: 0.5, gamma_regime: 'long' }
    ] });
    out.scanner = hostScanner.innerHTML;

    var hostLeaders = { innerHTML: '' };
    renderLeaders(hostLeaders, {
      as_of: '2026-07-24T00:00:00+00:00', stale: false,
      board_a: [{ ticker: 'MARA', sector: 'Crypto', recurrence_count: 6,
                  A1_flow_recur: true, fire_a: false, de_escalation: {} }],
      board_b: [{ ticker: 'AEP', sector: 'Utilities', B5_flow_inflect: true,
                  days_since_inflection: 0, fire_b: false }],
      etf_strip: [{ ticker: 'XLF', net_premium_mn: 726.0 }],
    });
    out.leaders = hostLeaders.innerHTML;

    process.stdout.write(JSON.stringify(out));
    })();
    """)
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}\nSTDOUT:\n{res.stdout}"
    states = _json.loads(res.stdout.strip().splitlines()[-1])
    for key, val in states.items():
        assert val.strip(), f"render output for state {key!r} was empty — sweep would be vacuous"
    combined = "\n".join(states.values())
    hits = _banned_vocabulary_hits(_visible_text(combined))
    assert hits == {}, f"banned vocabulary in JS-rendered copy: {hits}"


@_needs_node
def test_filmstrip_sentence_flip_clause_across_crossing_counts(page):
    """filmCount()'s three branches (once/twice/N times, 一次/两次/N次) and the
    ZH punctuation seam ('。' + flip clause, never '。，'), for every count."""
    cases = [
        (1, "below", "Crossed the flip once, closed below it.", "穿越翻转位一次，收于其下方。"),
        (2, "above", "Crossed the flip twice, closed above it.", "穿越翻转位两次，收于其上方。"),
        (5, "above", "Crossed the flip 5 times, closed above it.", "穿越翻转位5次，收于其上方。"),
    ]
    for crosses, side, want_en, want_zh in cases:
        sess = ("{ session_date: '2026-07-30', filmstrip_html: '<figure></figure>', "
                "coverage: { minutes: 300, expected: 391, quality_en: 'q', quality_zh: 'q2' }, "
                "arc_shape_en: 'x', arc_shape_zh: 'y', "
                "flip: { crosses: " + str(crosses) + ", last_side: '" + side + "' } }")
        driver = (_DOM_STUB + _extract_workspace_script(page) + """
        var host = { innerHTML: '' };
        renderTicker(host, 'SPY', """ + _GX_MINIMAL + """, null, """ + sess + """);
        process.stdout.write(host.innerHTML);
        })();
        """)
        res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
        assert res.returncode == 0, f"node failed (crosses={crosses}):\nSTDERR:\n{res.stderr}"
        out = res.stdout
        assert want_en in out, f"crosses={crosses}: missing {want_en!r}"
        assert want_zh in out, f"crosses={crosses}: missing {want_zh!r}"
        assert "。，" not in out


@_needs_node
def test_filmstrip_shape_words_compose_without_doubling_the_subject(page):
    """B3 regression: SHAPE_WORDS (engine/session_digest.py) must never carry
    its own "Premium"/"权利金" subject — filmstripSentence() always supplies
    it by prefixing one. Real rendered output before this fix: 'Premium
    premium barely moved all day.' / '权利金全天权利金几乎没有变化。' (the
    "flat" tag) and 'Premium too little tape to describe the day.' (the
    "insufficient" tag — precisely what a young store produces). Pulls the
    SIX REAL tags straight from the engine so this test tracks the source,
    not a hand-copied duplicate, and fails if a future edit reintroduces an
    embedded subject in any one of them."""
    from engine.session_digest import SHAPE_WORDS
    assert len(SHAPE_WORDS) == 6, "expected exactly the six pinned arc shapes"
    for tag, (en, zh) in SHAPE_WORDS.items():
        sess = ("{ session_date: '2026-07-30', filmstrip_html: '<figure></figure>', "
                 "coverage: { minutes: 300, expected: 391, quality_en: 'q', quality_zh: 'q2' }, "
                 "arc_shape_en: " + _json.dumps(en) + ", arc_shape_zh: " + _json.dumps(zh) + ", "
                 "flip: { crosses: 0, last_side: null } }")
        driver = (_DOM_STUB + _extract_workspace_script(page) + """
        var host = { innerHTML: '' };
        renderTicker(host, 'SPY', """ + _GX_MINIMAL + """, null, """ + sess + """);
        process.stdout.write(host.innerHTML);
        })();
        """)
        res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
        assert res.returncode == 0, f"node failed (tag={tag}):\nSTDERR:\n{res.stderr}"
        out = res.stdout
        film = out[out.index("How the day traded"): out.index("The map")]
        want_en, want_zh = "Premium " + en + ".", "权利金" + zh + "。"
        assert want_en in film, f"{tag}: expected {want_en!r} — got {film!r}"
        assert want_zh in film, f"{tag}: expected {want_zh!r} — got {film!r}"
        assert film.count("Premium") == 1, f"{tag}: EN subject doubled — {film!r}"
        assert film.count("权利金") == 1, f"{tag}: ZH subject doubled — {film!r}"


@_needs_node
def test_filmstrip_null_disclosure_prints_once_not_twice(page):
    """M1 regression: the null figure's own .oew-film-empty span and
    filmstripSentence() used to both print the SAME disclosure for the same
    null condition, doubling it in the panel. Covers both null paths: sess
    entirely absent (404 / not yet fetched — the client FILM_NULL_HTML
    fallback) and a real record reporting zero covered minutes (the server's
    own honest-null filmstrip_html, coverage.minutes===0)."""
    driver_a = (_DOM_STUB + _extract_workspace_script(page) + """
    var host = { innerHTML: '' };
    renderTicker(host, 'THIN', """ + _GX_MINIMAL + """, null, null);
    process.stdout.write(host.innerHTML);
    })();
    """)
    res_a = _subprocess.run(["node", "-e", driver_a], capture_output=True, text=True, timeout=30)
    assert res_a.returncode == 0, f"node failed:\nSTDERR:\n{res_a.stderr}"
    film_a = res_a.stdout[res_a.stdout.index("How the day traded"): res_a.stdout.index("The map")]
    # strip the figure's own aria-label (the accessible-name twin every ilx
    # figure carries, same idiom as test_new_ticker_panels_... above) before
    # counting VISIBLE occurrences — a duplication bug is a second VISIBLE
    # print, not the standard sighted-text/accessible-name pairing.
    visible_a = re.sub(r'aria-label\s*=\s*"[^"]*"', " ", film_a)
    assert visible_a.count("No intraday record for this session") == 1, film_a
    assert visible_a.count("本交易日没有盘中记录") == 1, film_a
    assert "oew-pfoot" not in film_a, "no footer needed when sess itself is entirely absent"

    null_fig = ('<figure class="ilx oew-film oew-film-null"><span class="oew-film-empty">'
                '<span class="l-en">No intraday record for this session</span>'
                '<span class="l-zh">本交易日没有盘中记录</span></span></figure>')
    sess_b = ("{ session_date: '2026-07-29', filmstrip_html: " + _json.dumps(null_fig) + ", "
              "coverage: { minutes: 0, expected: 391, "
              "quality_en: 'No intraday record for this session', "
              "quality_zh: '本交易日没有盘中记录' }, "
              "arc_shape_en: 'x', arc_shape_zh: 'y', flip: { crosses: 0 } }")
    driver_b = (_DOM_STUB + _extract_workspace_script(page) + """
    var host = { innerHTML: '' };
    renderTicker(host, 'SPY', """ + _GX_MINIMAL + """, null, """ + sess_b + """);
    process.stdout.write(host.innerHTML);
    })();
    """)
    res_b = _subprocess.run(["node", "-e", driver_b], capture_output=True, text=True, timeout=30)
    assert res_b.returncode == 0, f"node failed:\nSTDERR:\n{res_b.stderr}"
    film_b = res_b.stdout[res_b.stdout.index("How the day traded"): res_b.stdout.index("The map")]
    visible_b = re.sub(r'aria-label\s*=\s*"[^"]*"', " ", film_b)
    assert visible_b.count("No intraday record for this session") == 1, film_b
    assert visible_b.count("本交易日没有盘中记录") == 1, film_b
    # the as-of stamp is independent of the disclosure suppression and must
    # still print — session_date is a real, known fact even on a zero-
    # coverage day.
    assert "2026-07-29" in film_b


def test_iv_rank_band_never_reaches_a_directional_token(page):
    """M2 regression: IVR_BAND used var(--down) for 'Vol rich' and var(--up)
    for 'Cheap'/'Very cheap' — site/theme.css swaps --up/--down under ZH, so
    the same NON-directional volatility level rendered red in EN and green
    in ZH. IV rank is not one of the two sanctioned direction instruments
    (masterplan §0.8: tape_flow, ΔOI) — no band may resolve to either token."""
    ivr_block = page[page.index("var IVR_BAND"): page.index("function filmOrdinal")]
    assert "--up" not in ivr_block, ivr_block
    assert "--down" not in ivr_block, ivr_block
    for word in ("Vol rich", "Elevated", "Normal", "Cheap", "Very cheap"):
        assert word in ivr_block, f"missing band word: {word}"


@_needs_node
def test_rich_or_cheap_band_color_is_never_directional_at_runtime(page):
    """Behavioral companion to the static IVR_BAND check above: renders all
    five real bands and confirms each one's actual resolved inline color
    never reaches --up/--down."""
    for band in ("rich", "elevated", "normal", "cheap", "very_cheap"):
        gx = ("{ meta: { asof: '2026-07-30' }, summary: { spot: 50, regime: 'long', "
              "gamma_flip: 48, call_wall: 52, put_wall: 47, max_pain: 49, "
              "iv_rank: { rank_pct: 50, band: '" + band + "', n_days: 37, low_confidence: false } }, "
              "expected_move: {} }")
        driver = (_DOM_STUB + _extract_workspace_script(page) + """
        var host = { innerHTML: '' };
        renderTicker(host, 'SPY', """ + gx + """, null, null);
        process.stdout.write(host.innerHTML);
        })();
        """)
        res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
        assert res.returncode == 0, f"node failed (band={band}):\nSTDERR:\n{res.stderr}"
        out = res.stdout
        i = out.index("Rich or cheap?")
        rich = out[i: out.index("oew-pfoot", i)]
        assert 'oew-rich-band" style="color:' in rich, f"band={band}: band word did not render — {rich!r}"
        start = rich.index('oew-rich-band" style="color:') + len('oew-rich-band" style="color:')
        color = rich[start: rich.index('"', start)]
        assert "--up" not in color and "--down" not in color, f"band={band}: directional token {color!r}"


@_needs_node
def test_low_confidence_suppresses_the_percentile_sentence(page):
    """Minor fix: low_confidence already swaps the pip track for the plain
    'history building — Nd' chip — the full percentile sentence must not
    ALSO render beside it (it claims a settled reading the chip next to it
    just disclaimed). rank_pct is deliberately present here (n=3, thin but
    non-null) — the old bug only fired when the model still returned a
    number alongside low_confidence=true."""
    gx = ("{ meta: { asof: '2026-07-30' }, summary: { spot: 50, regime: 'long', "
          "gamma_flip: 48, call_wall: 52, put_wall: 47, max_pain: 49, "
          "iv_rank: { rank_pct: 70, band: 'rich', n_days: 3, low_confidence: true } }, "
          "expected_move: {} }")
    driver = (_DOM_STUB + _extract_workspace_script(page) + """
    var host = { innerHTML: '' };
    renderTicker(host, 'YNG', """ + gx + """, null, null);
    process.stdout.write(host.innerHTML);
    })();
    """)
    res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}"
    out = res.stdout
    assert "history building — 3d" in out and "历史积累中 — 3天" in out
    rich = out[out.index("Rich or cheap?"): out.index("oew-pfoot", out.index("Rich or cheap?"))]
    assert "cost more than" not in rich, f"percentile sentence must not render at low_confidence — {rich!r}"
    assert "70%" not in rich


@_needs_node
def test_new_ticker_panels_keep_bilingual_span_parity_in_every_state(page):
    """test_bilingual_span_parity (above) strips <script> and therefore only
    ever checked the STATIC/baked markup. The five new panels are entirely
    client-rendered, so their l-en/l-zh balance needs its own check, across
    every state each panel can render (masterplan §0 gate #6)."""
    cases = [
        ("full", "'NVDA', " + _GX_FULL + ", null, " + _SESS_FULL),
        ("minimal", "'THIN', " + _GX_MINIMAL + ", null, null"),
    ]
    for name, args in cases:
        driver = (_DOM_STUB + _extract_workspace_script(page) + """
        var host = { innerHTML: '' };
        renderTicker(host, """ + args + """);
        process.stdout.write(host.innerHTML);
        })();
        """)
        res = _subprocess.run(["node", "-e", driver], capture_output=True, text=True, timeout=30)
        assert res.returncode == 0, f"node failed ({name}):\nSTDERR:\n{res.stderr}"
        out = re.sub(r'data-tip-(?:rc-)?(?:en|zh)\s*=\s*"[^"]*"', " ", res.stdout)
        out = re.sub(r'aria-label\s*=\s*"[^"]*"', " ", out)
        en, zh = out.count('class="l-en"'), out.count('class="l-zh"')
        assert en == zh and en > 0, f"{name} state: {en} l-en spans vs {zh} l-zh spans"


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            pass  # this module is pytest-only (fixtures required)
