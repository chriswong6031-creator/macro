"""Money register — `wire_format.humanize_money` and the lanes wired to it.

VOICE DOCTRINE BAN #8: "Number formatting like traders write: $1.0M not
$1000K; big figures rounded to the digit that matters."

THE CENSUS THIS SUITE PINS. 679 shipped marketing items (2026-08-11) carried
two forms no desk writes:

  * raw comma-grouped dollar figures out of the breaking/wire lane —
    "$7,639,791,784 in market cap gained today", "$220,529,779,571 in market
    cap on August 3", "a $34,864,886,849 gain on the day";
  * "$1000K" out of the K-suffix formatter — "a director opened a new roughly
    $1000K position in $BRVE" — where the mantissa rounded up into a fourth
    digit instead of promoting a band.

Both are band failures, so both die on ONE rule: a mantissa never prints four
digits. The tests below are ordered defect-first — the boundary table, then
the four-digit property, then one integration assertion per wired call site
that a representative composed sentence carries the humanized form and NOT a
written-out million.

Offline: stdlib + pytest only, no repo `data/` reads (sparse-excluded in agent
worktrees), no network, no LLM.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.marketing.wire_format import humanize_money  # noqa: E402

#: A dollar figure of a million or more written out in full — the census
#: defect. Two comma groups is $1,000,000; three is the 10-digit shape.
WRITTEN_OUT_MILLIONS = re.compile(r"\$\d{1,3}(?:,\d{3}){2,}")

#: A four-digit mantissa in front of a PROMOTABLE scale suffix: "$1000K",
#: "$1000M", "$1500B". T is deliberately absent — it is the top band, so a
#: quadrillion prints "$1000T" by design rather than inventing a suffix nobody
#: reads (pinned in test_the_top_band_has_no_promotion_and_that_is_the_ceiling).
FOUR_DIGIT_MANTISSA = re.compile(r"\$\d{4,}(?:\.\d+)?[KMB]\b")


# ─────────────────────────────────────────────────────────────────────────────
# 1. The band table — the documented contract, boundary by boundary
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("value", "want"), [
    # < 1e3 — no decimals, comma-grouped
    (0, "$0"),
    (1, "$1"),
    (450, "$450"),
    (450.4, "$450"),
    (999, "$999"),
    # >= 1e3 — K band, no decimals
    (1_000, "$1K"),
    (15_000, "$15K"),
    (450_400, "$450K"),
    (999_000, "$999K"),
    # THE $1000K DEFECT. Both of these round into a fourth mantissa digit and
    # must promote instead. 999_500 is under a million and still prints "$1.0M"
    # because it is the ROUNDING, not the value, that crosses the line.
    (999_500, "$1.0M"),
    (999_999, "$1.0M"),
    # >= 1e6 — M band, one decimal below 10M
    (1_000_000, "$1.0M"),
    (2_100_000, "$2.1M"),
    (6_920_000, "$6.9M"),
    # ... and no decimals at or above 10M, including the carry off 9.99...M,
    # which must read "$10M" and never "$10.0M".
    (9_999_999, "$10M"),
    (10_000_000, "$10M"),
    (83_400_000, "$83M"),
    (317_000_000, "$317M"),
    # >= 1e9 — B band at three significant figures
    (999_999_999, "$1.00B"),      # never "$1000M"
    (1_000_000_000, "$1.00B"),
    (1_200_000_000, "$1.20B"),
    (4_200_000_000, "$4.20B"),
    (7_639_791_784, "$7.64B"),    # the doctrine's own exemplar figure
    (42_000_000_000, "$42.0B"),
    (220_529_779_571, "$221B"),
    # >= 1e12 — T band, same rule, rather than a four-digit B
    (999_999_999_999, "$1.00T"),  # never "$1000B"
    (1_234_000_000_000, "$1.23T"),
    (1_500_000_000_000, "$1.50T"),
])
def test_band_table_is_the_documented_contract(value, want):
    assert humanize_money(value) == want, f"{value!r} -> {humanize_money(value)!r}"


def test_the_exact_boundaries_named_in_the_doctrine_brief():
    """The six magnitudes the brief calls out, asserted as one block.

    Kept separate from the table above so a regression reads as "the boundary
    moved" rather than as one row of thirty.
    """
    assert humanize_money(999_999) == "$1.0M"
    assert humanize_money(1_000_000) == "$1.0M"
    assert humanize_money(9_999_999) == "$10M"
    assert humanize_money(10_000_000) == "$10M"
    assert humanize_money(999_999_999) == "$1.00B"
    assert humanize_money(1_000_000_000) == "$1.00B"


# ─────────────────────────────────────────────────────────────────────────────
# 2. The property that kills the whole defect class
# ─────────────────────────────────────────────────────────────────────────────

def test_a_mantissa_never_prints_four_digits():
    """"$1000K" / "$1000M" / "$1500B" are unreachable at any magnitude.

    Swept rather than sampled: every decade from a dollar to a quadrillion,
    with the just-under-carry values that produced the shipped "$1000K" sitting
    exactly on each band edge.
    """
    values: list[float] = []
    for exp in range(0, 16):
        base = 10.0 ** exp
        values.extend([base, base * 1.5, base * 9.99, base - 1, base - 0.5])
    values.extend([999_499, 999_500, 999_999, 999_999_499, 999_999_999_499])

    for v in values:
        for signed in (False, True):
            for sig in (1, 2, 3, 4, 5, 6):
                for probe in (v, -v):
                    out = humanize_money(probe, signed=signed, sig=sig)
                    assert not FOUR_DIGIT_MANTISSA.search(out), (
                        f"four-digit mantissa from {probe!r} "
                        f"(signed={signed}, sig={sig}): {out!r}"
                    )


def test_the_top_band_has_no_promotion_and_that_is_the_ceiling():
    """A quadrillion prints a wide T mantissa rather than a made-up suffix.

    Documented, not accidental: global market cap is ~$1e14, so the T band's
    own overflow is unreachable in market copy, and "$1000T" is still readable
    where "$1.0Q" is not.
    """
    assert humanize_money(1e15) == "$1000T"
    assert humanize_money(1e14) == "$100T"


def test_nothing_at_or_above_a_million_is_written_out_in_full():
    for exp in range(6, 16):
        base = 10.0 ** exp
        for v in (base, base * 1.5, base * 9.99):
            out = humanize_money(v)
            assert not WRITTEN_OUT_MILLIONS.search(out), f"{v!r} -> {out!r}"
            assert out[-1] in "KMBT", f"{v!r} -> {out!r} lost its scale suffix"


# ─────────────────────────────────────────────────────────────────────────────
# 3. sig, signs, and the fail-soft contract
# ─────────────────────────────────────────────────────────────────────────────

def test_sig_shortens_the_billions_mantissa_to_the_doctrines_form():
    assert humanize_money(7_639_791_784) == "$7.64B"          # default sig=3
    assert humanize_money(7_639_791_784, sig=2) == "$7.6B"    # doctrine's shorter form
    assert humanize_money(7_639_791_784, sig=1) == "$8B"
    assert humanize_money(1_234_000_000_000, sig=2) == "$1.2T"


def test_sig_is_clamped_and_never_raises_on_junk():
    assert humanize_money(7_639_791_784, sig=0) == humanize_money(7_639_791_784, sig=1)
    assert humanize_money(7_639_791_784, sig=99) == humanize_money(7_639_791_784, sig=6)
    assert humanize_money(7_639_791_784, sig="x") == "$7.64B"  # falls back to 3
    assert humanize_money(7_639_791_784, sig=None) == "$7.64B"


def test_the_M_and_K_bands_ignore_sig_they_are_already_at_the_digit_that_matters():
    for sig in (1, 2, 3, 4, 5, 6):
        assert humanize_money(83_400_000, sig=sig) == "$83M"
        assert humanize_money(2_100_000, sig=sig) == "$2.1M"
        assert humanize_money(450_400, sig=sig) == "$450K"


def test_negatives_keep_their_sign_ahead_of_the_symbol():
    assert humanize_money(-7_639_791_784) == "-$7.64B"
    assert humanize_money(-999_999) == "-$1.0M"
    assert humanize_money(-450) == "-$450"


def test_signed_prefixes_positives_only_and_never_signs_zero():
    assert humanize_money(7_639_791_784, signed=True) == "+$7.64B"
    assert humanize_money(2_100_000, signed=True) == "+$2.1M"
    assert humanize_money(-2_100_000, signed=True) == "-$2.1M"
    assert humanize_money(0, signed=True) == "$0"
    assert humanize_money(0.0, signed=True) == "$0"


@pytest.mark.parametrize("bad", [
    None, float("nan"), float("inf"), float("-inf"),
    "", "  ", "abc", "$1,000", [], {}, (), object(), b"nope",
])
def test_unusable_input_returns_empty_string_so_a_caller_can_fall_back(bad):
    """A money formatter that raises takes the whole post down with it.

    Every wired call site is inside a copy builder, so the contract is "" and
    a caller that falls back — never an exception.
    """
    assert humanize_money(bad) == ""


def test_it_accepts_anything_float_accepts():
    assert humanize_money("7639791784") == "$7.64B"
    assert humanize_money(" 1000000 ") == "$1.0M"
    assert humanize_money(b"7639791784") == "$7.64B"   # float() takes bytes too
    assert humanize_money(True) == "$1"          # bool is an int is a float
    assert humanize_money(math.pi * 1e9) == "$3.14B"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Integration — one composed sentence per wired call site
# ─────────────────────────────────────────────────────────────────────────────

def test_congress_feed_display_usd_can_no_longer_ship_1000K():
    """The K-suffix formatter itself. Shared by the congress and insider lanes."""
    from engine.marketing.congress_feed import display_usd

    # The shipped defect: a $999.5K position printed "$1000K".
    assert display_usd(999_500) == "$1.0M"
    assert display_usd(999_999) == "$1.0M"
    assert "K" not in display_usd(999_500)

    # ... and the band that never existed: above $1T the old table printed
    # a four-digit B mantissa.
    assert display_usd(1_500_000_000_000) == "$1.50T"

    # Everything that fits its own band is UNTOUCHED — this lane's mantissa law
    # ("$6.92M", "$298K", "$1,001" written out under 10K) is deliberate and
    # documented, so the promotion fix must not quietly re-register it.
    assert display_usd(1_001) == "$1,001"
    assert display_usd(15_000) == "$15K"
    assert display_usd(298_500) == "$298K"
    assert display_usd(6_920_000) == "$6.92M"
    assert display_usd(1_200_000_000) == "$1.20B"

    # No magnitude reaches a four-digit mantissa any more.
    for exp in range(3, 16):
        base = 10.0 ** exp
        for v in (base, base * 1.5, base * 9.99, base - 0.5):
            for probe in (v, -v):
                out = display_usd(probe)
                assert not FOUR_DIGIT_MANTISSA.search(out), f"{probe!r} -> {out!r}"


def test_insider_purchase_sentence_carries_the_humanized_position():
    """The shipped exemplar: "a director opened a new roughly $1000K position"."""
    from engine.marketing.insider_feed import insider_facts

    packet = insider_facts({
        "ticker": "BRVE", "insider_name": "Nancy Koskey Patzwahl",
        "role": "Director", "shares": 25_000, "price": 39.98,
        "shares_following": 27_270, "prior_shares": 2_270,
        "purchase_value": 999_500.0, "trade_date": "2026-07-27",
        "file_date": "2026-07-28", "lag_days": 1, "ownership": "direct",
        "mechanism": "MATERIAL_ADDITION", "why_it_matters": "It got bigger.",
    })
    purchase = next(f for f in packet["facts"] if f["id"] == "insider_purchase")
    text = purchase["text"]

    assert "roughly $1.0M" in text, text
    assert "$1000K" not in text
    assert not FOUR_DIGIT_MANTISSA.search(text), text
    assert not WRITTEN_OUT_MILLIONS.search(text), text


def test_congress_disclosure_sentence_carries_a_humanized_range():
    """The congress lane's amount range runs through the same formatter."""
    from engine.marketing.congress_feed import congress_facts

    packet = congress_facts({
        "ticker": "NVDA", "representative": "Nancy Pelosi", "title": "Rep.",
        "side": "purchase", "amount_low": 999_500.0, "amount_high": 5_000_000.0,
        "trade_date": "2026-07-20", "file_date": "2026-08-01", "lag_days": 12,
    })
    blob = " ".join(str(f.get("text") or "") for f in packet["facts"])

    assert "$1000K" not in blob
    assert not FOUR_DIGIT_MANTISSA.search(blob), blob
    assert not WRITTEN_OUT_MILLIONS.search(blob), blob


def test_attention_source_why_sentence_names_dollar_volume_like_a_desk(tmp_path):
    """Pool 1's `why` string, composed off a tmp_path pack (never repo data/)."""
    from engine.marketing.attention_source import PACK_REL, top_by_dollar_volume

    pack_path = tmp_path / PACK_REL
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(json.dumps({
        "trade_date": "2026-08-10",
        "tickers": {
            "AAPL": {"adv_rank": 1, "adv20_dollars": 7_639_791_784.0},
            "TINY": {"adv_rank": 2, "adv20_dollars": 450_400.0},
            "MIDC": {"adv_rank": 3, "adv20_dollars": 2_400_000.0},
        },
    }), encoding="utf-8")

    rows = top_by_dollar_volume(tmp_path, n=3, as_of="2026-08-10")
    whys = {r["ticker"]: r["why"] for r in rows}

    assert "$7.64B a day" in whys["AAPL"], whys.get("AAPL")
    # Under a million the old table printed "$450,400 a day"; a desk writes $450K.
    assert "$450K a day" in whys["TINY"], whys.get("TINY")
    # ... and the digit that matters survives: this used to render "$2M".
    assert "$2.4M a day" in whys["MIDC"], whys.get("MIDC")

    for why in whys.values():
        assert not WRITTEN_OUT_MILLIONS.search(why), why
        assert not FOUR_DIGIT_MANTISSA.search(why), why


def test_earnings_headline_revenue_is_humanized(tmp_path):
    """The earnings card's revenue chips, composed end to end."""
    from engine.marketing.earnings_card import build_earnings_post

    post = build_earnings_post(
        "META", "Meta Platforms", 5.50, 5.00,
        42_000_000_000.0, 40_000_000_000.0, tmp_path, quarter="Q2 2026",
    )
    headline = post["headline"]

    assert "Rev $42.0B" in headline, headline
    assert "$40.0B" in headline, headline
    assert not WRITTEN_OUT_MILLIONS.search(headline), headline
    assert not FOUR_DIGIT_MANTISSA.search(headline), headline

    body = post["body"]
    assert not WRITTEN_OUT_MILLIONS.search(body), body


def test_a_sub_million_revenue_no_longer_ships_a_raw_comma_figure(tmp_path):
    """The old `_short_rev` fell through to "$450,000" below a million."""
    from engine.marketing.earnings_card import build_earnings_post

    post = build_earnings_post(
        "TINY", "Tiny Co", 0.10, 0.08,
        450_400.0, 400_000.0, tmp_path,
    )
    assert "$450K" in post["headline"], post["headline"]
    assert "450,400" not in post["headline"]
