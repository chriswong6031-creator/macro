"""tests/test_marketing_wire_dehandle.py — SOURCE-ACCOUNT DE-HANDLING (operator law 2026-08-02).

We reword and republish news; we NEVER tag or brand the original account. Three
real posts on @mastermindx001 on 2026-08-02/03 broke that law:

  1. "On the tape: GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER TRUMP
      SAID FRESH IRAN TALKS WOULD BEGIN LATER MONDAY, RAISING HOPES
      -- @FirstSquawk reporting"
  2. "Now crossing. JUST IN: 🇺🇸🇮🇷 US CENTCOM says it has redirected 35 vessels
      as Iran's blockade continues on the Strait of Hormuz."   (DOUBLE OPENER)
  3. "... -- @financialjuice reporting", plus a "@BRICSinfo · AGGREGATOR" card chip.

The three fixture headlines below are those posts' own bodies, verbatim.

WHAT IS PINNED, and the mutation each pin is armed against:
  1. parse_tweets de-handles the DISPLAY name only — and `x_handle` / `source`
     SURVIVE. That second half is the pin that catches an over-eager future
     de-handling: the independence key reads `x_handle` first, so dropping it
     silently collapses two relays of one claim onto one source and kills the
     >=2-independent-sources instant path.
  2. Two DIFFERENT handles carrying the same claim still count as 2 independent
     sources, all the way through to corroboration_decision returning "instant".
  3. The credit is the generic "wire reports"; the direct-quote VENUE
     ("on Truth Social") is untouched.
  4. No composed post for any of the three fixtures carries an "@" at all.
  5. strip_wire_opener kills OUR-opener-plus-THEIR-opener, collapses a stack,
     spares a mid-sentence "breaking", and is inert with no opener of our own.
  6. The output-level backstop: banned_language / foreign_handle_mentions flag a
     foreign handle, allowlist ours, and do NOT trip on an email or a cashtag.
  7. card_input_violations names the offending PARAM.
  8. _strip_trailing_source_clause reaches a handle alias, and the legacy
     single-argument behaviour is unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine.marketing import copywriter as _cw  # noqa: E402
from engine.marketing.copywriter import (  # noqa: E402
    banned_language,
    card_input_violations,
    foreign_handle_mentions,
    own_account_handles,
)
from engine.marketing.press_corroboration import corroboration_decision  # noqa: E402
from engine.marketing.press_lane import (  # noqa: E402
    _corroboration_key,
    _independent_source,
    _strip_trailing_source_clause,
)
from engine.marketing.press_providers import (  # noqa: E402
    GENERIC_RELAY_DISPLAY,
    TwitterApiIoProvider,
    display_source_name,
)
from engine.marketing.wire_voice import compose_post, strip_wire_opener  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# The three live posts, as ingestion sees them
# ─────────────────────────────────────────────────────────────────────────────

GOLD_HEADLINE = (
    "GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER TRUMP SAID FRESH IRAN "
    "TALKS WOULD BEGIN LATER MONDAY, RAISING HOPES"
)
CENTCOM_HEADLINE = (
    "JUST IN: 🇺🇸🇮🇷 US CENTCOM says it has redirected 35 vessels as Iran's "
    "blockade continues on the Strait of Hormuz."
)
KOREA_HEADLINE = (
    "S. KOREAN TRADE BALANCE PRELIM ACTUAL 30.32B (FORECAST 29.487B, "
    "PREVIOUS 36.09B) $MACRO"
)

#: (handle, tweet text) for each real post.
LIVE_FIXTURES: tuple[tuple[str, str], ...] = (
    ("FirstSquawk", GOLD_HEADLINE),
    ("BRICSinfo", CENTCOM_HEADLINE),
    ("financialjuice", KOREA_HEADLINE),
)


def _tweet_response(text: str, *, tid: str = "1955000000000000001") -> dict:
    """A twitterapi.io /twitter/user/last_tweets body carrying one tweet."""
    return {
        "status": "success",
        "has_next_page": False,
        "tweets": [
            {"id": tid, "text": text, "createdAt": "Sun Aug 02 14:05:00 +0000 2026"},
        ],
    }


def _provider(handle: str) -> TwitterApiIoProvider:
    return TwitterApiIoProvider(
        {"handles": [{"handle": handle, "tier": "fast", "corroboration_class": "hearsay"}],
         "poll_tiers": {"fast": 75}},
        spend_cap_usd=75.0,
    )


def _parse_one(handle: str, text: str) -> dict:
    items, _since = _provider(handle).parse_tweets(
        _tweet_response(text),
        {"handle": handle, "corroboration_class": "hearsay"},
        since_id=None,
    )
    assert len(items) == 1
    return items[0]


@pytest.fixture(autouse=True)
def _pinned_own_handles(monkeypatch):
    """Pin the own-handle allowlist so no test depends on the live roster.

    The memo is also cleared on the way in AND out: a test that resolves it from
    config would otherwise leak that value into every later test in the session.
    """
    _cw._reset_own_handles_cache()
    monkeypatch.setattr(_cw, "_OWN_HANDLES_CACHE", frozenset({"mastermindx001"}))
    yield
    _cw._reset_own_handles_cache()


# ─────────────────────────────────────────────────────────────────────────────
# PIN 1 — ingestion de-handles the DISPLAY name, and only the display name
# ─────────────────────────────────────────────────────────────────────────────

class TestIngestionDeHandling:
    @pytest.mark.parametrize("handle,text", LIVE_FIXTURES)
    def test_display_name_is_generic_and_handle_survives(self, handle, text):
        item = _parse_one(handle, text)
        # The DISPLAY name is generic — this is what reaches a post body.
        assert item["source_name"] == "Newswire"
        assert item["source_name"] == GENERIC_RELAY_DISPLAY
        assert "@" not in item["source_name"]
        # …and the INTERNAL keys are untouched. Corroboration and the
        # independence key read these; de-handling them kills the >=2-source path.
        assert item["x_handle"] == handle
        assert item["source"] == f"x_{handle}"
        assert item["url"] == f"https://twitter.com/{handle}/status/1955000000000000001"

    def test_textless_tweet_headline_carries_no_handle(self):
        item = _parse_one("FirstSquawk", "")
        assert item["headline"] == "Wire flash"
        assert "@" not in item["headline"]

    @pytest.mark.parametrize("raw", ["@FirstSquawk", "FirstSquawk", "", "   ", "@"])
    def test_display_source_name_collapses_handle_shapes(self, raw):
        assert display_source_name(raw) == GENERIC_RELAY_DISPLAY

    def test_display_source_name_passes_a_real_publisher_name_through(self):
        # Multi-word / dotted names are not handle-shaped and survive verbatim —
        # the normalizer must not rename every non-relay source to "Newswire".
        assert display_source_name("Truth Social (via CNN archive)") == (
            "Truth Social (via CNN archive)")
        assert display_source_name("  cnbc.com  ") == "cnbc.com"


# ─────────────────────────────────────────────────────────────────────────────
# PIN 2 — two handles are still TWO independent sources
# ─────────────────────────────────────────────────────────────────────────────

class TestIndependenceSurvivesDeHandling:
    def _relay(self, handle: str, headline: str) -> dict:
        """A SCORED-shaped relay item as press_lane's accumulate loop sees it."""
        item = _parse_one(handle, headline)
        return {**item, "event_class": "geopolitical",
                "matched": {"tickers": [], "macro_keys": ["iran"], "sectors": []}}

    def test_two_handles_are_two_independent_sources(self):
        a = self._relay("FirstSquawk", GOLD_HEADLINE)
        b = self._relay("financialjuice", GOLD_HEADLINE)
        # Same generic display name — the ONLY thing that changed.
        assert a["source_name"] == b["source_name"] == GENERIC_RELAY_DISPLAY
        # Same claim (so they land in one corroboration bucket)…
        assert _corroboration_key(a) == _corroboration_key(b)
        # …but DISTINCT independence keys, which is what makes them count as two.
        assert _independent_source(a) != _independent_source(b)
        assert _independent_source(a) == "x:firstsquawk"
        assert _independent_source(b) == "x:financialjuice"

    def test_the_lane_counter_reaches_two_and_the_gate_opens(self):
        """The lane's own accumulate loop, run over the pair (press_lane step 2)."""
        corr: dict[str, dict] = {}
        for item in (self._relay("FirstSquawk", GOLD_HEADLINE),
                     self._relay("financialjuice", GOLD_HEADLINE)):
            entry = corr.setdefault(_corroboration_key(item), {"sources": []})
            src = _independent_source(item)
            if src and src not in entry["sources"]:
                entry["sources"].append(src)

        assert len(corr) == 1, "the pair must share ONE claim bucket"
        n_sources = len(next(iter(corr.values()))["sources"])
        assert n_sources == 2

        decision = corroboration_decision(
            self._relay("FirstSquawk", GOLD_HEADLINE),
            corroborated_sources=n_sources, window_ok=True,
        )
        # The >=2-independent-sources instant path is ALIVE after de-handling.
        assert decision["gate"] == "instant"


# ─────────────────────────────────────────────────────────────────────────────
# PIN 3 — the credit is generic; the VENUE attribution is untouched
# ─────────────────────────────────────────────────────────────────────────────

class TestCorroborationCredit:
    def test_attributed_path_credits_the_wire_not_the_account(self):
        d = corroboration_decision(
            {"corroboration_class": "hearsay", "source_tier": "x_relay",
             "event_class": "company_news", "source_name": "@financialjuice",
             "x_handle": "financialjuice"},
            corroborated_sources=1, window_ok=False,
        )
        assert d["gate"] == "attributed"
        assert d["attribution"] == "wire reports"
        assert "@" not in d["attribution"]

    def test_digest_political_path_credits_the_wire(self):
        d = corroboration_decision(
            {"corroboration_class": "hearsay", "source_tier": "x_relay",
             "event_class": "geopolitical", "source_name": "@FirstSquawk"},
            corroborated_sources=1, window_ok=False,
        )
        assert d["gate"] == "digest"
        assert d["attribution"] == "wire reports"

    def test_digest_strict_path_credits_the_wire(self):
        d = corroboration_decision(
            {"corroboration_class": "hearsay", "source_tier": "x_relay",
             "event_class": "company_news", "strict_corroboration": True,
             "source_name": "@BRICSinfo"},
            corroborated_sources=1, window_ok=False,
        )
        assert d["gate"] == "digest"
        assert d["attribution"] == "wire reports"

    def test_direct_quote_venue_attribution_is_unchanged(self):
        d = corroboration_decision(
            {"corroboration_class": "direct-quote", "source_tier": "mirror",
             "event_class": "policy"},
            corroborated_sources=1, window_ok=False,
        )
        assert d["gate"] == "instant"
        assert d["attribution"] == "on Truth Social"

    def test_a_source_name_that_is_still_a_handle_never_reaches_the_credit(self):
        """Belt AND braces: even an un-de-handled item cannot leak its name here."""
        for name in ("@FirstSquawk", "@BRICSinfo", "@financialjuice"):
            d = corroboration_decision(
                {"corroboration_class": "hearsay", "source_tier": "x_relay",
                 "event_class": "company_news", "source_name": name},
                corroborated_sources=1, window_ok=False,
            )
            assert name not in d["attribution"]


# ─────────────────────────────────────────────────────────────────────────────
# PIN 4 — no composed post carries an "@"
# ─────────────────────────────────────────────────────────────────────────────

class TestComposedPostsCarryNoHandle:
    @pytest.mark.parametrize("handle,text", LIVE_FIXTURES)
    def test_end_to_end_composed_post_has_no_handle(self, handle, text):
        item = _parse_one(handle, text)
        decision = corroboration_decision(
            {**item, "event_class": "company_news"},
            corroborated_sources=1, window_ok=False,
        )
        base = _strip_trailing_source_clause(
            item["headline"], item["source_name"],
            f"@{item['x_handle']}", item["x_handle"],
        )
        post = compose_post(
            opener="On the tape:", summary=base,
            attribution=decision["attribution"], tape_stamp="GOLD +0.6%",
        )
        assert "@" not in post, post
        assert handle.lower() not in post.lower(), post
        # And the output-level backstop agrees.
        assert not [v for v in banned_language(post) if "handle mention" in v]

    def test_the_exact_live_gold_post_would_no_longer_compose(self):
        """The literal 2026-08-02 body, rebuilt through the fixed chain."""
        item = _parse_one("FirstSquawk", GOLD_HEADLINE)
        post = compose_post(
            opener="On the tape:", summary=item["headline"],
            attribution=corroboration_decision(
                {**item, "event_class": "company_news"})["attribution"],
        )
        assert post.endswith("-- wire reports")
        assert "@FirstSquawk reporting" not in post


# ─────────────────────────────────────────────────────────────────────────────
# PIN 5 — the double opener
# ─────────────────────────────────────────────────────────────────────────────

class TestDoubleOpener:
    def test_our_opener_plus_their_opener_collapses_to_one(self):
        post = compose_post(opener="Now crossing.", summary=CENTCOM_HEADLINE)
        assert "JUST IN:" not in post
        assert post.startswith("Now crossing. 🇺🇸🇮🇷 US CENTCOM says")

    def test_flags_after_the_opener_survive(self):
        assert strip_wire_opener(CENTCOM_HEADLINE).startswith("🇺🇸🇮🇷 US CENTCOM")

    def test_flags_before_the_opener_survive_in_place(self):
        assert strip_wire_opener("🚨 BREAKING: rates cut") == "🚨 rates cut"

    def test_stacked_openers_collapse(self):
        assert strip_wire_opener("BREAKING: JUST IN: text") == "text"
        assert strip_wire_opener("URGENT - ALERT: FLASH: text") == "text"

    def test_mid_sentence_breaking_survives(self):
        text = "The story is breaking: rates up"
        assert strip_wire_opener(text) == text
        assert strip_wire_opener("Gold jumped. JUST IN: nothing here") == (
            "Gold jumped. JUST IN: nothing here")

    def test_no_separator_is_prose_not_a_hook(self):
        assert strip_wire_opener("Breaking news on the tape") == (
            "Breaking news on the tape")

    def test_an_empty_opener_leaves_the_wire_opener_intact(self):
        """With no hook of our own, theirs is the only one — removing it would
        leave the post opening on a bald fragment."""
        post = compose_post(opener="", summary=CENTCOM_HEADLINE)
        assert post.startswith("JUST IN: 🇺🇸🇮🇷 US CENTCOM says")

    def test_a_body_that_is_only_a_hook_is_never_emptied(self):
        assert strip_wire_opener("BREAKING:") == "BREAKING:"

    def test_a_clean_body_is_untouched(self):
        assert strip_wire_opener(GOLD_HEADLINE) == GOLD_HEADLINE
        assert strip_wire_opener(KOREA_HEADLINE) == KOREA_HEADLINE


# ─────────────────────────────────────────────────────────────────────────────
# PIN 6 — the output-level backstop (the gate that beats the queue)
# ─────────────────────────────────────────────────────────────────────────────

class TestHandleMentionScreen:
    def test_foreign_handle_is_flagged(self):
        assert foreign_handle_mentions("On the tape -- @FirstSquawk reporting") == (
            ["firstsquawk"])
        assert banned_language("On the tape -- @FirstSquawk reporting") == (
            ["source handle mention: '@firstsquawk'"])

    def test_every_live_offender_is_flagged(self):
        for handle in ("FirstSquawk", "financialjuice", "BRICSinfo"):
            viols = banned_language(f"Gold up -- @{handle} reporting")
            assert viols == [f"source handle mention: '@{handle.lower()}'"]

    def test_our_own_handle_is_allowlisted(self):
        assert foreign_handle_mentions("more at @mastermindx001") == []
        assert banned_language("more at @mastermindx001") == []

    def test_own_handles_argument_overrides_the_roster(self):
        assert foreign_handle_mentions("hi @FirstSquawk", {"FirstSquawk"}) == []
        assert foreign_handle_mentions("hi @FirstSquawk", {"@firstsquawk"}) == []
        assert banned_language("hi @FirstSquawk", own_handles={"firstsquawk"}) == []

    def test_email_address_is_not_a_mention(self):
        assert foreign_handle_mentions("write to foo@bar.com now") == []
        assert banned_language("write to foo@bar.com now") == []
        assert foreign_handle_mentions("support@mastermind-x.com") == []

    def test_cashtag_is_not_a_mention(self):
        assert foreign_handle_mentions("$AAPL up 2%, $MACRO steady") == []
        assert banned_language(KOREA_HEADLINE) == []

    def test_duplicates_collapse_and_order_is_stable(self):
        assert foreign_handle_mentions(
            "@FirstSquawk and @BRICSinfo and @FirstSquawk again"
        ) == ["firstsquawk", "bricsinfo"]

    def test_existing_positional_callers_are_unchanged(self):
        # The new parameter is keyword-ONLY: every existing call site still works
        # and still sees the dash/vocab/cheese verdicts it always saw.
        assert "em dash (U+2014)" in banned_language("gold — up")
        assert banned_language("Gold rose 0.6% to $4,070 an ounce.") == []

    def test_own_account_handles_never_raises(self, tmp_path):
        # No config/marketing.yml under this root -> {} rather than an exception.
        assert own_account_handles(root=tmp_path) == frozenset()
        assert own_account_handles(cfg={"desk_network": {"accounts": [
            {"id": "flagship", "handle": "@MastermindX001"},
            {"id": "noh"},
            {"id": "blank", "handle": "  "},
        ]}}, root=tmp_path) == frozenset({"mastermindx001"})


# ─────────────────────────────────────────────────────────────────────────────
# PIN 7 — card-input params
# ─────────────────────────────────────────────────────────────────────────────

class TestCardInputScreen:
    def test_offending_param_is_named(self):
        assert card_input_violations(
            summary=f"{CENTCOM_HEADLINE} -- @BRICSinfo", headline="ok"
        ) == ["card param 'summary': source handle mention: '@bricsinfo'"]

    def test_clean_params_return_empty(self):
        assert card_input_violations(
            summary=GOLD_HEADLINE, headline="Gold higher",
            rows=[{"ticker": "GLD", "note": "up 0.6%"}], stamp=None, n=3,
        ) == []

    def test_nested_rows_are_screened(self):
        viols = card_input_violations(
            rows=[{"ticker": "GLD", "note": "via @FirstSquawk"}],
        )
        assert viols == ["card param 'rows': source handle mention: '@firstsquawk'"]

    def test_our_own_handle_is_allowed_on_a_card(self):
        assert card_input_violations(footer="@mastermindx001") == []

    def test_the_live_aggregator_chip_is_caught(self):
        assert card_input_violations(chip="@BRICSinfo · AGGREGATOR") == [
            "card param 'chip': source handle mention: '@bricsinfo'"]


# ─────────────────────────────────────────────────────────────────────────────
# PIN 8 — the trailing-source strip reaches the handle aliases
# ─────────────────────────────────────────────────────────────────────────────

class TestTrailingSourceClause:
    def test_alias_strip(self):
        assert _strip_trailing_source_clause(
            "X -- @FirstSquawk", "Newswire", "@FirstSquawk", "FirstSquawk") == "X"

    def test_bare_handle_alias_strip(self):
        assert _strip_trailing_source_clause(
            "X -- FirstSquawk", "Newswire", "@FirstSquawk", "FirstSquawk") == "X"

    def test_the_at_sign_goes_with_the_clause_on_the_live_body(self):
        # The 2026-08-02 gold post's own em-dash vintage: the "@" leaves with the
        # clause rather than dangling on the end of the body.
        out = _strip_trailing_source_clause(
            f"{GOLD_HEADLINE} — @FirstSquawk", "Newswire",
            "@FirstSquawk", "FirstSquawk")
        assert out == GOLD_HEADLINE
        assert "@" not in out

    def test_longest_candidate_wins_on_a_double_clause_body(self):
        """Candidate order is LONGEST FIRST, not argument order.

        A contract pin, and the only shape that can tell the two apart: when two
        candidates BOTH match the tail, the shorter one strips half a clause and
        leaves the rest of it in the body. (The @-vs-bare pair the call site
        passes cannot distinguish them — a dash never sits directly in front of
        the bare form — so without this case the ordering would ship unpinned.)
        """
        assert _strip_trailing_source_clause(
            "X -- Newswire -- @FirstSquawk",
            "Newswire", "@FirstSquawk", "Newswire -- @FirstSquawk") == "X"

    def test_display_name_still_strips_when_it_is_the_one_present(self):
        assert _strip_trailing_source_clause(
            "X -- Newswire", "Newswire", "@FirstSquawk", "FirstSquawk") == "X"

    def test_legacy_single_argument_behaviour_is_unchanged(self):
        assert _strip_trailing_source_clause("X -- Reuters", "Reuters") == "X"
        assert _strip_trailing_source_clause("X — Reuters", "Reuters") == "X"
        assert _strip_trailing_source_clause("X -- Reuters", "") == "X -- Reuters"
        # A dash INSIDE the headline is kept (only the exact clause is stripped).
        assert _strip_trailing_source_clause(
            "Risk-off tape -- Reuters", "Reuters") == "Risk-off tape"
        assert _strip_trailing_source_clause(
            "Risk-off tape", "Reuters") == "Risk-off tape"

    def test_blank_candidates_are_skipped_and_never_chop_a_bare_dash(self):
        """A blank candidate makes the DASH ITSELF the suffix.

        Without the skip, "X --" ends with "--" and silently loses it — and the
        legacy contract for a blank source_name is "return the text untouched".
        Asserting only that a blank alias is harmless alongside a real one does
        NOT pin this: with a real candidate present the blank one never gets to
        match anything.
        """
        assert _strip_trailing_source_clause("X --", "") == "X --"
        assert _strip_trailing_source_clause("X --", "Newswire", "", "  ") == "X --"
        assert _strip_trailing_source_clause("X -- Newswire", "Newswire", "", "  ") == "X"
        assert _strip_trailing_source_clause("X -- Y", "", "", "  ") == "X -- Y"
