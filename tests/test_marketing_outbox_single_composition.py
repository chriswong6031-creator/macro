"""ONE COMPOSITION PER POST — `outbox.compose_text` never emits line 1 twice.

THE DEFECT THIS SUITE PINS. Four shipped breaking items carried their own
headline TWICE inside a single text, joined by a wire opener:

    ob-2026-08-01-170b51e475   "Heads up:"       posted
    ob-2026-08-01-c3d08a7993   "TRUMP:"          quarantined
    ob-2026-08-02-e731cc12b9   "Now crossing."   quarantined
    ob-2026-08-03-6e554a3eb1   "On the tape:"    posted

THE CAUSE CHAIN, top to bottom:

  1. `breaking_summary._deterministic_summary` returns "{headline} -- {source}"
     when `_det_lead_sentence` finds no usable lead. That relay is DOCUMENTED
     and correct as a WHOLE POST ("still the honest thing to send when the
     headline is all we were given") — it is only a duplicate once somebody
     puts it behind the same headline.
  2. `press_lane` reads it as `summary`, strips the source clause, and hands
     it to `wire_voice.compose_post`, which prefixes an opener.
  3. `outbox.compose_text` joins headline + that body with a blank line.

Step 3 is the seam, and it is where the guard lives, because the gate that
saves the live lane today (`wire_format.wire_post_shape` → short_form →
blank headline, applied in `press_lane.run_press_tick`) sits in the CALLER:
`fastlane` and `engine/press/research_lane` join at the same function with no
gate at all. A guard in the join covers every producer at once.

Offline: stdlib + pytest only, no repo `data/` reads, no network, no LLM.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.marketing.outbox import compose_text  # noqa: E402

#: Reconstructed from ob-2026-08-03-6e554a3eb1. A FirstSquawk relay whose
#: packet carried no body snippet, so the "summary" came back as the headline.
LIVE_HEADLINE = (
    "Fed's Williams: central bank very committed to returning inflation to 2%"
)

#: (id, opener, attribution) for each shipped duplicate. Openers are
#: `wire_voice._OPENERS_*` pool entries.
LIVE_EXEMPLARS = [
    ("ob-2026-08-01-170b51e475", "Heads up:", ""),
    ("ob-2026-08-01-c3d08a7993", "TRUMP:", "@financialjuice reporting"),
    ("ob-2026-08-02-e731cc12b9", "Now crossing.", ""),
    ("ob-2026-08-03-6e554a3eb1", "On the tape:", ""),
]


def _restated_body(opener: str, headline: str, attribution: str) -> str:
    """The body press_lane composed for each shipped duplicate.

    `wire_voice.compose_post` collapses whitespace and joins
    ``f"{opener} {body}"``, so a summary that IS the headline comes out as the
    opener followed by line 1 verbatim.
    """
    body = f"{opener} {headline}".strip()
    return f"{body} -- {attribution}" if attribution else body


# ─────────────────────────────────────────────────────────────────────────────
# 1. The shipped defect, byte for byte
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("item_id", "opener", "attribution"), LIVE_EXEMPLARS)
def test_a_shipped_duplicate_now_composes_exactly_once(item_id, opener, attribution):
    body = _restated_body(opener, LIVE_HEADLINE, attribution)
    text = compose_text(LIVE_HEADLINE, body)

    # The headline appears ONCE in the shipped text, not twice.
    assert text.count(LIVE_HEADLINE) == 1, f"{item_id} still doubles:\n{text}"

    # ... and the surviving half is the ENRICHED one: the body keeps the
    # opener and the source clause, so nothing the reader had is lost.
    assert text == body, item_id
    assert text.startswith(opener), item_id
    if attribution:
        assert text.endswith(f"-- {attribution}"), item_id

    # No blank-line join happened at all.
    assert "\n\n" not in text, item_id


def test_the_old_join_is_what_shipped_so_this_guard_is_not_theoretical():
    """Pins the pre-fix shape, so a regression reads as "the duplicate is back".

    This is the naive join the function used to be — headline, blank line,
    body — reproduced here from the two arguments alone.
    """
    body = _restated_body("On the tape:", LIVE_HEADLINE, "")
    naive = "\n\n".join(p for p in (LIVE_HEADLINE, body) if p)

    assert naive.count(LIVE_HEADLINE) == 2, "fixture no longer reproduces the bug"
    assert compose_text(LIVE_HEADLINE, body) != naive


def test_the_upstream_relay_that_feeds_the_seam_still_returns_the_headline():
    """The cause is real and UNCHANGED — this guard is load-bearing.

    `_deterministic_summary` is documented to fall back to the headline relay,
    and that fallback is correct for a standalone post. If it is ever changed
    to return "" instead, this test fails loudly rather than letting the guard
    above quietly become dead code.
    """
    from engine.marketing.breaking_summary import _deterministic_summary

    summary = _deterministic_summary({
        "headline": LIVE_HEADLINE,
        "source_name": "FirstSquawk",
        "source": "wire",
        "body_snippet": "",
    })
    assert summary == f"{LIVE_HEADLINE} -- FirstSquawk"
    assert LIVE_HEADLINE in summary, (
        "the seam guard exists because this relay returns line 1 as a body"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. The guard is TIGHT — it fires on restatement and on nothing else
# ─────────────────────────────────────────────────────────────────────────────

def test_an_additive_body_still_gets_the_two_line_join():
    """The house shape is unchanged for every post that actually says more."""
    body = ("He added that the committee is not on a preset course. "
            "-- FirstSquawk")
    text = compose_text(LIVE_HEADLINE, body)

    assert text == f"{LIVE_HEADLINE}\n\n{body}"
    assert "\n\n" in text


def test_shared_vocabulary_is_not_restatement():
    """A coverage ratio would fire here; verbatim containment does not."""
    headline = "Fed's Williams: central bank very committed to 2% inflation"
    body = ("Williams said the central bank is committed to the 2% target and "
            "named inflation as the reason. -- FirstSquawk")
    text = compose_text(headline, body)

    assert text.startswith(headline)
    assert "\n\n" in text, "an additive body must survive the guard"


def test_a_short_label_headline_can_never_collapse_a_two_line_post():
    """"$AAPL" appearing in its own body is a layout, not a duplicate."""
    for headline in ("$AAPL", "Gold", "FOMC", "Breaking news"):
        body = f"{headline} is the story of the session so far."
        text = compose_text(headline, body)
        assert text == f"{headline}\n\n{body}", headline


def test_the_match_survives_spacing_and_case_but_not_a_different_sentence():
    # Collapsed whitespace and a case change still count as a restatement,
    # because wire_voice re-spaces every body it composes.
    spaced = LIVE_HEADLINE.replace(" ", "   ").upper()
    assert compose_text(LIVE_HEADLINE, f"On the tape: {spaced}").count("\n\n") == 0

    # A genuinely different second statement is not one.
    assert "\n\n" in compose_text(LIVE_HEADLINE, "On the tape: rates are unchanged.")


# ─────────────────────────────────────────────────────────────────────────────
# 3. The existing contract is untouched
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("head", "body", "want"), [
    ("", "body only", "body only"),
    (LIVE_HEADLINE, "", LIVE_HEADLINE),
    (None, None, ""),
    ("", "", ""),
    ("  Head  ", "  Body of the post goes here  ", "Head\n\nBody of the post goes here"),
])
def test_the_flattening_contract_is_unchanged(head, body, want):
    assert compose_text(head, body) == want


def test_it_never_raises_on_non_string_halves():
    for head, body in ((1, 2), ({"a": 1}, ["b"]), (object(), None)):
        assert isinstance(compose_text(head, body), str)
