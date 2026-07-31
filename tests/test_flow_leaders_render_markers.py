"""Doctrine-marker regression test for the Flow Leaders page render.

Pins the #3224 user-first revamp at the RENDERED-OUTPUT level: the dot-ladder
signature and plain-word EN/ZH leg copy must come out of the template, and the
pre-#3224 machine slugs (`TSBrd`, `NotTrap`, `PriceOK`, `FlowZ`) must not.

Why output-level: the live page shipped the banned-vocab slug wall for 3 days
(2026-07-22..25) while the template was already compliant — the baked artifact,
not the template, is what users see. This test renders the real template with a
synthetic payload so a regression in either the template or its payload contract
fails loudly, with no dependency on repo data stores.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BANNED_SLUGS = ("TSBrd", "NotTrap", "PriceOK", "FlowZ")

# ─────────────────────────────────────────────────────────────────────────────
# Banned vocabulary — ONE list, two tiers
# ─────────────────────────────────────────────────────────────────────────────
# BANNED_SLUGS above is the #3224 revamp's four-slug pin and stays as it is: it
# names the exact slugs that shipped live for 3 days, so it keeps failing by
# name.  This list is the estate-wide one (kept identical to
# tests/test_build_options_command.py's, so the two options-family surfaces are
# held to the same words), and it is swept per TIER rather than over the whole
# page string:
#   · test_no_banned_vocabulary_in_visible_copy — glance tier, full list
#   · test_no_banned_vocabulary_in_aria_copy    — aria-label, full list (it
#     SUBSTITUTES for the visible content, so it is a screen-reader user's
#     glance tier)
#   · test_no_banned_vocabulary_in_hover_copy   — data-tip-* (Tier 2),
#     BANNED_ON_TIER_2
#
# Measured consequence of NOT having had this: `0DTE` — item 34 below — shipped
# in this page's visible caution-chip label AND its hover tip until 2026-07-31,
# while BANNED_SLUGS stayed green throughout, because the term is not one of the
# four slugs that test was written to catch.
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
# this in both directions: widen the carve-out and that test fails.
#
# Everything NOT listed here stays banned on Tier 2 as well, because it has no
# sanctioned home in user copy on any tier — raw machine slugs (`pain_dist`,
# `wilson_`, `us_sector`), internal state names (`IGNITION`, `Inflect`), the
# non-compliant disclosure form Law 5 explicitly rejects (`expected-null forward
# meter`), and `validated` (CI-guarded estate-wide).  `0DTE` stays banned too:
# it is an acronym, and this page never DEFINES it — the plain phrase carries
# the whole meaning on its own.  Its home is Tier 3, on the page that does
# explain it (content/seo/learn/options/zero-dte-regime.md).
TIER2_RECEIPT_VOCABULARY = {
    "Oracle P",   # study / ruling ID — Law 5: "study ID ... moves to Tier 2"
    "n=",         # sample size — Law 3: "Precision belongs on Tier 2 ('58.3%, n=26, ...')"
    "slow reco",  # the rating label a receipt cites as unchanged — Law 5's example
    # Same family as `n=` under Law 3's "precision belongs on Tier 2": a base
    # rate's error bars are a receipt, not glance-tier copy.
    "FDR", "z-score", "t-stat", "rank-IC",
}
BANNED_ON_TIER_2 = [b for b in BANNED_VOCABULARY if b not in TIER2_RECEIPT_VOCABULARY]


def _row_a(ticker: str = "NVDA") -> dict:
    return {
        "ticker": ticker,
        "sector": "Technology",
        "fire_a": True,
        "recurrence_count": 5,
        "days_since_inflection": None,
        "de_escalation": None,
        "signing_source": "tape",
        "zerodte_dominated": False,
        # A-board ladder legs: one lit, one dark, one null — exercises all three
        # segment states of the ladder macro.
        "A1_flow_recur": True,
        "A2_flow_z_hot": True,
        "A3_oi_confirmed": True,
        "A4_ts_breadth": False,
        "A5_price_leader": True,
        "A6_near_high": True,
        "A7_vol_confirm": None,
        "A8_not_trap": True,
    }


def _row_b(ticker: str = "AMD") -> dict:
    return {
        "ticker": ticker,
        "sector": "Technology",
        "fire_b": True,
        "recurrence_count": 2,
        "days_since_inflection": 2,
        "de_escalation": None,
        "signing_source": "tape",
        "zerodte_dominated": False,
        "B1_washout_recent": True,
        "B2_oversold_osc": True,
        "B3_turn_organ": True,
        "B5_flow_inflect": True,
        "B6_oi_confirmed": False,
        "B7_vol_confirm": None,
        "B8_not_trap": True,
    }


def _render(payload: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    return env.get_template("flow_leaders.html.j2").render(flow_leaders=payload)


def _payload() -> dict:
    return {
        "as_of": "2026-07-25",
        "stale": False,
        "coverage": {
            "n_universe": 2,
            "n_flow_sessions": 134,
            "flow_z_live": True,
            "tape_names": 2,
            "n_etfs": 1,
        },
        "board_a": [_row_a()],
        "board_a_total": 1,
        "board_b": [_row_b()],
        "board_b_total": 1,
        "etf_strip": [{"ticker": "SPY", "net_premium_mn": 12.5, "zerodte_share": 0.4}],
        "cold_start_detail": {
            "n_sessions": 134,
            "required_for_recurrence": 20,
            "message": None,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Copy extraction — one page, three streams
# ─────────────────────────────────────────────────────────────────────────────
def _page_body(rendered: str) -> str:
    """This lane's own copy: the `.wrap` subtree, excluding the shared header.

    `_navlinks.html.j2` is the estate-wide nav inventory (CLAUDE.md §Navigation
    source-of-truth) — its wording is owned by that family, not by this page, so
    a sweep that included it would either fail this lane for someone else's copy
    or pressure this lane to edit a shared file."""
    marker = '<div class="wrap">'
    assert marker in rendered, "page body marker missing — scoping would sweep the shared nav"
    return rendered.split(marker, 1)[1]


def _visible_text(fragment: str) -> str:
    """Text a sighted user reads IN THE FLOW: script, style, comments, tags and
    the two attribute families that are read some other way all come out.

    The tip/aria strip is a TIERING split, not a "nobody can read this" claim.  A
    hover popup IS read: docs/DESIGN_DOCTRINE.md §1 makes `data-tip-en/zh` the
    Tier-2 surface and this estate's whole demotion rule ("nothing is lost by
    moving detail to a hover") depends on it carrying real copy.  So the values
    are not discarded, they are swept on their own tier — _tip_text() below."""
    out = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.S | re.I)
    out = re.sub(r"<style\b.*?</style>", " ", out, flags=re.S | re.I)
    out = re.sub(r"<!--.*?-->", " ", out, flags=re.S)
    out = re.sub(r'data-tip-[a-z-]+\s*=\s*"[^"]*"', " ", out)
    out = re.sub(r'aria-label\s*=\s*"[^"]*"', " ", out)
    out = re.sub(r"<[^>]+>", " ", out)
    return html.unescape(out)


def _attr_values(fragment: str, *attrs: str) -> str:
    """The VALUES of named attributes, as their own text stream. Comments and
    <script>/<style> bodies are dropped first, so this reads only attributes the
    template actually shipped in markup."""
    out = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.S | re.I)
    out = re.sub(r"<style\b.*?</style>", " ", out, flags=re.S | re.I)
    out = re.sub(r"<!--.*?-->", " ", out, flags=re.S)
    found: list[str] = []
    for attr in attrs:
        found += re.findall(rf'{re.escape(attr)}\s*=\s*"([^"]*)"', out)
    return html.unescape("\n".join(found))


def _tip_text(fragment: str) -> str:
    """Tier-2 hover copy: the tip body plus the optional receipt line that
    templates/theme.js renders underneath it (`data-tip-rc-*`)."""
    return _attr_values(fragment, "data-tip-en", "data-tip-zh",
                        "data-tip-rc-en", "data-tip-rc-zh")


def _aria_text(fragment: str) -> str:
    """What a screen-reader user hears INSTEAD of the visible content — the
    ladder is `role="img"` with the full leg read on `aria-label`, so this is
    that user's glance tier and gets the Tier-1 list, not the Tier-2 one."""
    return _attr_values(fragment, "aria-label")


def _banned_vocabulary_hits(text: str, needles: list[str] | None = None) -> dict:
    """Substring counts for every banned needle present. Default list is Tier 1."""
    return {b: text.count(b) for b in (needles or BANNED_VOCABULARY) if b in text}


def _payload_all_cautions() -> dict:
    """The payload the copy sweeps run against: every caution chip DRIVEN.

    _payload()'s rows carry `zerodte_dominated: False` and `de_escalation: None`,
    so on that fixture the whole caution strip is an untaken branch — and a sweep
    over an untaken branch is green about copy it never saw.  That is exactly how
    `0DTE` sat in this page's chip label and tip while the render test above
    stayed green.  Every flag is on here, and the sweeps assert the chips are
    actually present before they assert the words are clean."""
    payload = _payload()
    cautions = {"earnings_window": True, "vol_trade": True,
                "protective_put": True, "gamma_caution": True}
    for row in (payload["board_a"] + payload["board_b"]):
        row["zerodte_dominated"] = True
        row["de_escalation"] = dict(cautions)
        row["signing_source"] = "estimate"      # drives the `~est` sign dot + its tip
    return payload


@pytest.fixture(scope="module")
def body() -> str:
    return _page_body(_render(_payload_all_cautions()))


def test_render_carries_dot_ladder_signature():
    html = _render(_payload())
    assert 'class="ladder"' in html, "#3224 dot-ladder signature missing from render"
    assert 'class="seg seg-on"' in html, "lit ladder segment missing"
    assert 'class="seg seg-off"' in html, "dark ladder segment missing"
    assert 'class="seg seg-nul"' in html, "null ladder segment missing"


def test_render_carries_plain_word_leg_copy():
    html = _render(_payload())
    # Tier-2 receipt copy, EN + ZH (user-first doctrine: no machine slugs on glance).
    assert "Money keeps showing up" in html
    assert "资金反复出现" in html
    assert "Not a failed breakout" in html
    assert "Money flipped positive" in html


def test_render_has_no_banned_machine_slugs():
    html = _render(_payload())
    for slug in BANNED_SLUGS:
        assert slug not in html, f"banned pre-#3224 machine slug {slug!r} in render"


def test_render_survives_empty_boards():
    # Absent-safe: an empty payload must still render (honest-null page), not crash.
    html = _render({})
    assert "<html" in html
    for slug in BANNED_SLUGS:
        assert slug not in html


# ---------------------------------------------------------------------------
# OEU bug-wave F3-18 — the page stamp renders the underlying SESSION, not the
# build's wall-clock timestamp (which can be a weekend/holiday date while
# every board row describes the last real NYSE session).
# ---------------------------------------------------------------------------

def test_render_prefers_session_date_over_as_of_for_the_stamp():
    payload = _payload()
    payload["as_of"] = "2026-07-26T14:36:28+00:00"   # a Sunday build timestamp
    payload["session_date"] = "2026-07-24"            # the Friday session the boards describe
    html = _render(payload)
    assert '<span class="num">2026-07-24</span>' in html
    assert "2026-07-26" not in html


def test_render_falls_back_to_as_of_when_session_date_absent():
    """Backward-compat: an older payload shape (no session_date key at all)
    must still render something, not a blank stamp."""
    payload = _payload()
    payload["as_of"] = "2026-07-25T09:00:00+00:00"
    assert "session_date" not in payload
    html = _render(payload)
    assert '<span class="num">2026-07-25</span>' in html


# ---------------------------------------------------------------------------
# Banned vocabulary, swept per tier — the gap that let `0DTE` ship
# ---------------------------------------------------------------------------
# The chip and tip this section is written around, before and after 2026-07-31.
# Kept as literals so the negative controls below reconstruct the exact bytes
# that shipped, rather than a paraphrase of them.
PRE_FIX_LABEL = ("0DTE-heavy", "0DTE为主")
PRE_FIX_TIP = ("Mostly same-day (0DTE) options — usually day-trading, not positioning for a move.",
               "以当日到期（0DTE）期权为主 — 通常是日内交易，而非布局趋势。")
SHIPPED_LABEL = ("Same-day heavy", "当日到期为主")
SHIPPED_TIP = ("Same-day contracts are usually day-trading, not positioning for a move.",
               "当日到期合约通常用于日内交易，而非布局趋势。")


def test_no_banned_vocabulary_in_visible_copy(body):
    """Glance tier — the full Tier-1 list, on copy read without hovering."""
    hits = _banned_vocabulary_hits(_visible_text(body))
    assert hits == {}, f"banned vocabulary in visible copy: {hits}"


def test_no_banned_vocabulary_in_aria_copy(body):
    """`aria-label` replaces the visible content for a screen-reader user, so it
    is that user's glance tier — full Tier-1 list, same as the sighted copy."""
    hits = _banned_vocabulary_hits(_aria_text(body))
    assert hits == {}, f"banned vocabulary in aria copy: {hits}"


def test_no_banned_vocabulary_in_hover_copy(body):
    """Tier-2 hover copy — the half of this page no sweep used to look at.

    `data-tip-en/zh` is read: it is the doctrine's own Tier-2 surface, and this
    page leans on it hard (every caution chip, every ladder, every `?` help).
    The demotion rule only holds if what lands there is held to a language
    standard too — a looser one than Tier 1 (BANNED_ON_TIER_2), because the
    hover is where receipts are SUPPOSED to live."""
    hits = _banned_vocabulary_hits(_tip_text(body), BANNED_ON_TIER_2)
    assert hits == {}, f"banned vocabulary in hover copy: {hits}"


def test_same_day_caution_chip_ships_plain_words_on_both_tiers(body):
    """Pin the fix by name, not only through the generic sweep: a revert that
    re-introduced the acronym under a different spelling would still trip the
    sweep, but this says which chip and what it must say instead."""
    for lang in (0, 1):
        assert SHIPPED_LABEL[lang] in _visible_text(body), \
            f"same-day caution chip label missing: {SHIPPED_LABEL[lang]!r}"
        assert SHIPPED_TIP[lang] in _tip_text(body), \
            f"same-day caution chip tip missing: {SHIPPED_TIP[lang]!r}"
    # Wording is shared verbatim with the options workspace's twin of this chip
    # (scripts/build_options_command.py, templates/options.html.j2's `ZDTE`), so
    # the two surfaces describe the same state in the same words.
    assert SHIPPED_LABEL == ("Same-day heavy", "当日到期为主")


# ---------------------------------------------------------------------------
# Negative controls — a green sweep must mean "clean", never "looked at nothing"
# ---------------------------------------------------------------------------
def test_caution_chips_are_actually_driven(body):
    """The control the sweeps stand on.

    _payload()'s rows leave every caution flag off, so a sweep run against it
    would be green about a branch that never rendered — which is how the term
    survived here.  The copy fixture drives them; this asserts it worked."""
    visible = _visible_text(body)
    for label in ("Same-day heavy", "Earnings soon", "Both sides",
                  "Looks hedged", "Fragile tape"):
        assert label in visible, f"caution chip {label!r} not driven — sweeps are vacuous"


def test_streams_are_not_vacuous(body):
    """Each stream must carry real bilingual copy of its OWN kind.

    A sweep whose extractor silently returns "" passes forever.  The tip stream
    additionally must not still contain attribute syntax (that would mean the
    values were never unwrapped), and the visible stream must not contain tip
    copy (that would mean the tier split collapsed and Tier-2 receipts were
    being judged by the Tier-1 list)."""
    visible, tips, aria = _visible_text(body), _tip_text(body), _aria_text(body)
    for name, stream in (("visible", visible), ("tip", tips), ("aria", aria)):
        assert len(stream) > 200, f"{name} stream is near-empty ({len(stream)} chars)"
    assert "资金" in visible and "money" in visible.lower(), "visible stream lost a language"
    assert "期权" in tips and "options" in tips.lower(), "tip stream lost a language"
    assert "signs confirming" in aria, "aria stream is not the ladder read"
    assert "data-tip-en=" not in tips, "tip stream still carries attribute syntax"
    assert SHIPPED_TIP[0] not in visible, "tier split collapsed: hover copy leaked into visible"


@pytest.mark.parametrize("lang", [0, 1])
def test_visible_sweep_catches_the_pre_fix_label(body, lang):
    """Plant the exact label that shipped back into real markup, per language."""
    planted = body.replace(SHIPPED_LABEL[lang], PRE_FIX_LABEL[lang])
    assert planted != body, f"plant was a no-op — {SHIPPED_LABEL[lang]!r} is no longer the label"
    hits = _banned_vocabulary_hits(_visible_text(planted))
    assert "0DTE" in hits, f"visible sweep blind to the pre-fix label in lang {lang}"


@pytest.mark.parametrize("lang", [0, 1])
def test_hover_sweep_catches_the_pre_fix_tip(body, lang):
    """Plant the exact tip that shipped back into real markup, per language.

    This is the control that was missing for the whole life of this page: the
    tip stream did not exist, so nothing could have caught it."""
    planted = body.replace(SHIPPED_TIP[lang], PRE_FIX_TIP[lang])
    assert planted != body, f"plant was a no-op — {SHIPPED_TIP[lang]!r} is no longer the tip"
    hits = _banned_vocabulary_hits(_tip_text(planted), BANNED_ON_TIER_2)
    assert "0DTE" in hits, f"hover sweep blind to the pre-fix tip in lang {lang}"


def test_aria_sweep_is_the_tier_1_list_not_the_tier_2_one(body):
    """`n=` is banned on Tier 1 and carved out on Tier 2, so it tells the two
    lists apart: planted in an aria-label it must fire, planted in a tip it
    must not."""
    anchor = "signs confirming"
    assert anchor in _aria_text(body), "aria anchor moved — this control is vacuous"
    planted = body.replace(anchor, anchor + " (n=26)")
    assert "n=" in _banned_vocabulary_hits(_aria_text(planted)), \
        "aria copy is being swept with the permissive Tier-2 list"
    tip_planted = body.replace(SHIPPED_TIP[0], SHIPPED_TIP[0] + " (n=26)")
    assert tip_planted != body, "tip plant was a no-op"
    assert _banned_vocabulary_hits(_tip_text(tip_planted), BANNED_ON_TIER_2) == {}, \
        "Tier-2 carve-out is not being applied to hover copy"


def test_hover_sweep_still_catches_terms_with_no_sanctioned_home(body):
    """The carve-out is narrow: a term that has no home on ANY tier must still
    fire inside a tip."""
    planted = body.replace(SHIPPED_TIP[0], SHIPPED_TIP[0] + " IGNITION")
    assert planted != body, "plant was a no-op"
    assert "IGNITION" in _banned_vocabulary_hits(_tip_text(planted), BANNED_ON_TIER_2)


def test_tier2_carve_out_is_exactly_the_doctrines_own_example():
    """docs/DESIGN_DOCTRINE.md Law 5's worked example of COMPLIANT Tier-2 copy
    contains three Tier-1 banned entries.  Sweeping hover copy with the Tier-1
    list would fail the doctrine it enforces — so the carve-out must clear that
    sentence, and must not clear anything the doctrine did not sanction."""
    example = ("backtested basket-level turn = null edge (Oracle P8, n=26); "
               "slow reco labels unchanged; display tier.")
    assert _banned_vocabulary_hits(example) != {}, \
        "the doctrine's own example no longer trips the Tier-1 list — re-derive the carve-out"
    assert _banned_vocabulary_hits(example, BANNED_ON_TIER_2) == {}, \
        "the carve-out no longer clears the doctrine's own compliant example"
    # …and stays narrow. These have no sanctioned home on any tier.
    for term in ("IGNITION", "0DTE", "validated", "us_sector", "pain_dist", "expected-null"):
        assert term in BANNED_ON_TIER_2, f"{term!r} must stay banned on Tier 2"
    assert TIER2_RECEIPT_VOCABULARY <= set(BANNED_VOCABULARY), \
        "carve-out names a term the Tier-1 list does not ban — it subtracts nothing"
