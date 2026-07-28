"""Copy substance + repetition gates (2026-07-28 wholesale Outbox rejection).

WHAT HAPPENED. The operator read the day's Outbox and rejected it: "we're just
spitting out word salad", "these aren't X posts". 42 of 72 posts were
quarantined by hand and 11 rewritten manually (PR #3922). That sweep was a
LEDGER action — it fixed the queue and left the generator untouched, so the
same day would have reproduced all of it.

Every post is ``generated headline + real data sentence + generated tail``. The
data sentence is computed from OHLCV and was fine. Every failure was in the
generated wrapper, in six classes:

  1. UNSUPPORTED CLAIM  "$FDS | the group in one chart ... This is the name I
     read the whole space through."  → no group is named anywhere in the post
  2. SAYS NOTHING       "$ROST | on my desk all week ... One picture, whole
     thesis."                         → the tail carries no information
  3. HEADLINE/BODY MISMATCH  headline "How I filter what I watch" over a body
     entirely about $TEL
  4. CIRCULAR           "That's most of why $FDS at 247.10 is worth your
     attention."                      → the fact justifies itself
  5. REPEATED CASHTAG per account per day (two flagship $CBOE, two cici $LKFN)
  6. REPEATED TEMPLATE FRAME per account per day ("$TEL close to going",
     "$CBOE close to going", "$FDS close to going")

THE BAR the operator set, which every test here encodes: a post must name a
ticker, state a dated fact with its numbers, and then say something that
FOLLOWS from that fact.

The load-bearing test in this file is TestWholeBankIsSubstantive: it walks the
ENTIRE template bank against every fact kind and fails if any render trips the
screen. A template added later with a vibe tail fails HERE rather than on the
flagship account.
"""
from __future__ import annotations

import re
from typing import Any

import pytest

from engine.marketing import consequence as cq
from engine.marketing import copywriter as cw
from engine.marketing.sentinel import gate_plan, skeleton, skeleton_similarity


# ─────────────────────────────────────────────────────────────────────────────
# Fact fixtures — the real text chart_facts/market_facts/movers_source emit,
# one per consequence-bank key family. Copied from the emitters so a fact whose
# wording drifts away from the consequence written for it shows up here.
# ─────────────────────────────────────────────────────────────────────────────

FACTS: tuple[tuple[str, str], ...] = (
    ("sma_50_reclaim", "TEL reclaimed its 50-day average (205.23), first time since Jul 2026"),
    ("sma_200_loss", "TEL lost its 200-day average (198.40), first time since Mar 2026"),
    ("new_52w_high", "ROST hit a new 52-week high"),
    ("new_52w_low", "ROST hit a new 52-week low"),
    ("near_52w_high", "FDS is 2.4% below its 52-week high (272.40)"),
    ("near_52w_low", "FDS is 3.1% above its 52-week low (198.10)"),
    ("volume_record", "CBOE had its highest daily volume in ~14m today"),
    ("volume_surge", "CBOE saw 3.2x its average volume today"),
    ("streak_green", "LKFN has closed green 5 sessions in a row"),
    ("streak_red", "LKFN has closed red 5 sessions in a row"),
    ("weekly_streak_up", "LKFN has been up 4 weeks in a row"),
    ("weekly_streak_dn", "LKFN has been down 4 weeks in a row"),
    ("biggest_move", "CUBI moved +8.2% today, its biggest single-day up in ~14m"),
    ("nr7", "CUBI is in a tight range today, narrowest of the last 7 sessions (range: 2.14)"),
    ("avwap_reclaim",
     "CUBI closed back above 77.99, the average price paid since the Jun 26 volume spike"),
    ("avwap_hold",
     "CUBI has held 77.99, the average price paid since the Jun 26 volume spike, "
     "for 22 straight sessions"),
    ("poc_level",
     "FDS is 1.8% above 205.23, the price where the most shares changed hands in the past 3 months"),
    ("in_value_area",
     "FDS is sitting between 200.00 and 210.00, where most of the past 3 months of volume traded"),
    ("poc_retest_hold",
     "FDS dipped back to 205.23, the most-traded price of the past 3 months, and held"),
    ("pct_20d", "TEL is up 12.3% over the last month"),
    ("mover_pct", "TEL surged +8.2% today (Technology)."),
    ("mover_magnitude", "TEL is 8.2% lower on the day, one of the biggest moves in the index."),
    ("growth_inflation",
     "Growth data's been roughly steady while inflation readings are still warm. "
     "18 groups on the move today."),
    ("liquidity_overlay", "Liquidity's tight right now."),
    ("transition_state", "The picture's still shifting, not settled yet."),
    ("tape_direction", "Buyers showed up across most of the tape today."),
    ("theme_count", "18 different groups are on the move today."),
    ("sector_leader", "Energy led today +2.1%; 7 of 11 sectors closed in the green."),
    ("sector_laggard", "Utilities lagged today -1.4%."),
    ("biggest_stock_mover", "NVDA rose +8.2% today, the biggest single-stock move in the index."),
    ("breadth_active",
     "142 of 503 names in the S&P universe are showing bullish momentum setups right now."),
    ("top_setup_breadth", "The most active bullish setup is firing on 31 names today."),
    ("event_catalyst", "The jobs report came in warmer than expected and the tape agreed."),
)

# Types that carry no ticker (the "filler" family) plus theme_list, which is a
# multi-cashtag format with its own laws.
_NO_TICKER_TYPES = frozenset({"macro", "event", "education"})


def _ctx(fact_id: str, fact_text: str, *, type: str, voice: str,
         ticker: str = "TEL") -> dict[str, Any]:
    """A writer context shaped like build_context's output."""
    tkr = "" if type in _NO_TICKER_TYPES else ticker
    return {
        "type": type,
        "voice": voice,
        "ticker": tkr,
        "cashtag": f"${tkr}" if tkr else "",
        "account": "flagship",
        "as_of": "2026-07-28",
        "top_fact_text": fact_text,
        "top_facts": [{"id": fact_id, "text": fact_text}],
        "consequence_text": cq.consequence_for(fact_id, seed=f"{tkr}|flagship|D1-S1"),
        "entry_str": "205.23", "t1_str": "212.00", "t2_str": "220.00",
        "inv_str": "199.10", "stop_str": "199.10",
        "gain_pct_str": "+4.2%", "loss_pct_str": "-2.1%", "win_rate_str": "58%",
        "target_label": "T1", "direction": "BULL", "mover_pct": "+8.2%",
        "theme_name": "",
    }


def _render(variant: tuple, ctx: dict) -> tuple[str, str]:
    headline = cw._render_template(variant[0], ctx)
    body = cw.fit_to_budget(headline, cw._render_template(variant[1], ctx), ctx)
    return headline, body


# ─────────────────────────────────────────────────────────────────────────────
# The operator's own examples. These are the ground truth for the screen: the
# four hand-rewritten posts define "good", the rejected ones define "bad", and
# a detector that disagrees with either is wrong no matter how clean its logic.
# ─────────────────────────────────────────────────────────────────────────────

class TestOperatorExamples:

    # Verbatim from the approved set in PR #3922.
    APPROVED = [
        ("$CUBI is back above the buyers' average",
         "CUBI closed above 77.99, the average price paid since the Jun 26 volume spike. "
         "Everyone who bought that spike is now roughly flat instead of underwater, which "
         "changes who sells into strength. No entry yet.",
         "CUBI",
         "CUBI closed above 77.99, the average price paid since the Jun 26 volume spike"),
        ("$TEL back over its 50-day",
         "TEL reclaimed 205.23 today, its first close above the 50-day average since Jul 2026. "
         "One reclaim isn't a trend. I want it to hold that level on a pullback before it's a "
         "setup, watching, not buying.",
         "TEL",
         "TEL reclaimed 205.23 today, its first close above the 50-day average since Jul 2026"),
        ("$FDS is 2.4% off its high",
         "FDS at 247.10 against a 52-week high of 272.40. That's close enough that the high "
         "itself is the level that matters: clear it and there's no overhead supply left, fail "
         "it again and this is the second rejection from the same place.",
         "FDS", "FDS at 247.10 against a 52-week high of 272.40"),
        ("$ROST just printed a new 52-week high",
         "ROST made a new 52-week high at 235.80, its first since Jun 2026. New highs are where "
         "I stop guessing and start watching the retest. The old high is the level it has to "
         "defend.",
         "ROST", "ROST made a new 52-week high at 235.80, its first since Jun 2026"),
    ]

    @pytest.mark.parametrize("headline,body,ticker,fact", APPROVED)
    def test_approved_posts_pass_the_screen(self, headline, body, ticker, fact):
        """The operator's hand-rewritten posts are the target. They must pass."""
        ctx = {"type": "chart", "ticker": ticker, "cashtag": f"${ticker}",
               "top_fact_text": fact, "theme_name": ""}
        assert cw.consequence_violations(headline, body, ctx) == []

    # Verbatim from the rejected set, one per failure class.
    REJECTED = [
        ("unsupported claim", "$FDS | the group in one chart",
         "FDS at 247.10. This is the name I read the whole space through.",
         "FDS", "FDS at 247.10"),
        ("says nothing", "$ROST | on my desk all week",
         "ROST at 235.80. One picture, whole thesis.", "ROST", "ROST at 235.80"),
        ("headline/body mismatch", "How I filter what I watch",
         "TEL reclaimed its 50-day average (205.23). $TEL stays on watch until the missing "
         "piece shows up.",
         "TEL", "TEL reclaimed its 50-day average (205.23)"),
        ("circular", "$FDS chart",
         "FDS at 247.10 against a 52-week high of 272.40. That's most of why $FDS at 247.10 "
         "is worth your attention.",
         "FDS", "FDS at 247.10 against a 52-week high of 272.40"),
        ("says nothing", "$TEL close to going",
         "TEL reclaimed its 50-day average (205.23). Almost there. Haven't touched it. "
         "Watching live.",
         "TEL", "TEL reclaimed its 50-day average (205.23)"),
    ]

    @pytest.mark.parametrize("klass,headline,body,ticker,fact", REJECTED)
    def test_rejected_posts_are_caught(self, klass, headline, body, ticker, fact):
        """Each rejected post is caught, and caught as the RIGHT class."""
        ctx = {"type": "watchlist", "ticker": ticker, "cashtag": f"${ticker}",
               "top_fact_text": fact, "theme_name": ""}
        violations = cw.consequence_violations(headline, body, ctx)
        assert violations, f"{klass} example shipped clean: {headline!r}"
        assert any(v.startswith(klass) for v in violations), \
            f"expected a {klass!r} violation, got {violations}"


# ─────────────────────────────────────────────────────────────────────────────
# The bank walk. This is the test that stops the defect coming back.
# ─────────────────────────────────────────────────────────────────────────────

class TestWholeBankIsSubstantive:

    def _all_renders(self):
        for fact_id, fact_text in FACTS:
            for (type_id, voice), variants in cw._TEMPLATES.items():
                if type_id == "theme_list":
                    continue  # own format law (>=4 cashtags + closing question)
                ctx = _ctx(fact_id, fact_text, type=type_id, voice=voice)
                for variant in variants:
                    if not cw._variant_allowed(variant, ctx):
                        continue
                    headline, body = _render(variant, ctx)
                    yield fact_id, type_id, voice, variant, headline, body, ctx

    def test_every_template_render_says_something(self):
        """No (template x fact kind) render trips the substance screen."""
        failures = []
        for fid, typ, voice, variant, headline, body, ctx in self._all_renders():
            violations = cw.consequence_violations(headline, body, ctx)
            if violations:
                failures.append(f"[{fid}] {typ}/{voice}: {violations[0]}\n"
                                f"    HL {variant[0]}\n    BD {variant[1]}")
        assert not failures, (
            f"{len(failures)} template renders say nothing / claim an unnamed "
            f"group / mismatch their headline:\n" + "\n".join(failures[:25])
        )

    def test_every_template_render_fits_the_post_budget(self):
        """fit_to_budget keeps fact + consequence + stance inside 275 chars."""
        failures = []
        for fid, typ, voice, variant, headline, body, _ctx_ in self._all_renders():
            total = len(headline) + 1 + len(body)
            if total > cw._MAX_CHARS:
                failures.append(f"[{fid}] {typ}/{voice}: {total} chars\n    {headline}\n    {body}")
        assert not failures, (
            f"{len(failures)} renders exceed {cw._MAX_CHARS} chars:\n"
            + "\n".join(failures[:10])
        )

    def test_no_template_reintroduces_a_bare_group_claim(self):
        """A template naming a peer set with no group data is the #1 defect."""
        offenders = []
        for (type_id, voice), variants in cw._TEMPLATES.items():
            if type_id == "theme_list":
                continue
            for variant in variants:
                text = f"{variant[0]} {variant[1]}".lower()
                hits = [r for r in cw._GROUP_REFERENTS if r in text]
                # A template may legitimately say "the group" only if it also
                # renders the members, i.e. carries the cashtag_list token.
                if hits and "{cashtag_list}" not in f"{variant[0]} {variant[1]}":
                    offenders.append(f"{type_id}/{voice}: {hits} in {variant[0]!r}")
        assert not offenders, (
            "templates promise a peer set they cannot name:\n" + "\n".join(offenders)
        )


class TestConsequenceBank:
    """The bank is the specification of 'substantive'. It must meet its own bar."""

    def test_every_consequence_is_fact_anchored(self):
        unanchored = []
        for key, lines in cq.CONSEQUENCES.items():
            for line in lines:
                lower = line.lower()
                anchored = bool(cw._NUMBER_RE.search(line)) or any(
                    re.search(rf"\b{re.escape(a)}", lower) for a in cw._FACT_ANCHORS
                )
                if not anchored:
                    unanchored.append(f"{key}: {line}")
        assert not unanchored, (
            "consequences that reference nothing the fact established (the "
            "screen would reject its own bank):\n" + "\n".join(unanchored)
        )

    def test_every_consequence_clears_the_house_language_bar(self):
        """No em dashes, no study names, no banned vocab, no cheese."""
        bad = []
        for key, lines in cq.CONSEQUENCES.items():
            for line in lines:
                hits = cw.banned_language(line)
                if hits:
                    bad.append(f"{key}: {hits} in {line!r}")
        assert not bad, "\n".join(bad)

    def test_every_consequence_fits_its_length_cap(self):
        over = [f"{k}: {len(s)} chars" for k, v in cq.CONSEQUENCES.items()
                for s in v if len(s) > cq._MAX_CONSEQUENCE_CHARS]
        assert not over, "\n".join(over)

    def test_every_fact_kind_the_engine_emits_has_a_consequence(self):
        """A fact with no consequence renders {consequence} empty, which makes
        its templates ineligible — silent volume loss. Catch it here."""
        missing = [fid for fid, _ in FACTS if not cq.has_consequence(fid)]
        assert not missing, f"fact kinds with no consequence bank entry: {missing}"

    def test_parameterised_fact_ids_normalise(self):
        assert cq.normalize_fact_id("sma_20_reclaim") == "sma_reclaim"
        assert cq.normalize_fact_id("sma_200_loss") == "sma_loss"
        assert cq.normalize_fact_id("pct_5d") == "pct_change"
        assert cq.normalize_fact_id("new_52w_high") == "new_52w_high"

    def test_consequence_is_deterministic_and_spreads_by_seed(self):
        a = cq.consequence_for("sma_50_reclaim", seed="TEL|flagship|D1-S1")
        assert a == cq.consequence_for("sma_50_reclaim", seed="TEL|flagship|D1-S1")
        # Different tickers on one account should mostly take different lines,
        # which is what keeps sentinel's frame gate from dropping one of them.
        picks = {cq.consequence_for("sma_50_reclaim", seed=f"{t}|flagship|D1-S1")
                 for t in ("TEL", "CBOE", "FDS", "CUBI", "ROST", "LKFN")}
        assert len(picks) >= 2

    def test_unknown_fact_kind_returns_empty_not_filler(self):
        assert cq.consequence_for("no_such_fact", seed="x") == ""
        assert cq.consequence_from_facts([{"id": "no_such_fact"}], seed="x") == ""

    def test_consequence_walks_to_the_first_covered_fact(self):
        facts = [{"id": "no_such_fact"}, {"id": "new_52w_high"}]
        assert cq.consequence_from_facts(facts, seed="s") in cq.CONSEQUENCES["new_52w_high"]


class TestConsequenceTokenWiring:

    def test_variant_needing_a_consequence_is_skipped_when_there_is_none(self):
        """A {consequence} template with an empty consequence would render a
        bare fact plus a stance — the exact says-nothing shape."""
        variant = ("{cashtag} note", "{top_fact} {consequence} Watching.")
        ctx = {"type": "chart", "ticker": "TEL", "cashtag": "$TEL",
               "consequence_text": ""}
        assert cw._variant_allowed(variant, ctx) is False
        ctx["consequence_text"] = "One reclaim isn't a trend. It has to hold that level."
        assert cw._variant_allowed(variant, ctx) is True

    def test_render_substitutes_the_consequence(self):
        ctx = _ctx("new_52w_high", "ROST hit a new 52-week high", type="chart",
                   voice="authoritative desk", ticker="ROST")
        out = cw._render_template("{top_fact} {consequence}", ctx)
        assert ctx["consequence_text"] in out
        assert "{consequence}" not in out

    def test_build_context_populates_the_consequence(self):
        ctx = cw.build_context(
            {"ticker": "ROST", "type": "chart", "account": "flagship", "slot": "D1-S1"},
            facts={"facts": [{"id": "new_52w_high", "text": "ROST hit a new 52-week high",
                              "salience": 9, "numbers": []}],
                   "numbers_whitelist": []},
        )
        assert ctx["consequence_text"] in cq.CONSEQUENCES["new_52w_high"]


class TestFitToBudget:

    def test_drops_trailing_stance_not_the_consequence(self):
        fact = ("Growth data's been roughly steady while inflation readings are still warm. "
                "18 groups on the move today.")
        consequence = ("Broad moves mean the tape agrees. Narrow ones mean a few names are "
                       "carrying it, and that's a different market.")
        # Long enough that fact + consequence + stance genuinely overruns 275.
        headline = "The macro read this week, and what it changes"
        body = f"{fact} {consequence} Cautious until it clears, as always."
        ctx = {"top_fact_text": fact, "consequence_text": consequence}
        assert len(headline) + 1 + len(body) > cw._MAX_CHARS, "fixture must overrun"

        trimmed = cw.fit_to_budget(headline, body, ctx)

        assert len(headline) + 1 + len(trimmed) <= cw._MAX_CHARS
        assert fact in trimmed, "the fact must never be trimmed"
        assert consequence in trimmed, "the consequence must never be trimmed"
        assert "Cautious until it clears" not in trimmed

    def test_leaves_a_fitting_body_untouched(self):
        ctx = {"top_fact_text": "ROST hit a new 52-week high", "consequence_text": ""}
        body = "ROST hit a new 52-week high. Watching."
        assert cw.fit_to_budget("$ROST high", body, ctx) == body

    def test_never_cuts_into_protected_text_even_when_still_over(self):
        """When only the fact+consequence remain and they still overrun, the
        body is returned intact and the length law reports it. Trimming into
        the substance to satisfy a character count is never the right trade."""
        fact = "F" * 200
        consequence = "C" * 120
        ctx = {"top_fact_text": fact, "consequence_text": consequence}
        body = f"{fact} {consequence}"
        out = cw.fit_to_budget("headline", body, ctx)
        assert fact in out and consequence in out


# ─────────────────────────────────────────────────────────────────────────────
# Repetition: the two defects the ledger sweep could not fix
# ─────────────────────────────────────────────────────────────────────────────

def _item(iid: str, account: str, *, headline: str, body: str,
          cashtag: str = "", type: str = "chart", slot: str = "") -> dict:
    return {
        "id": iid, "account": account, "type": type,
        "headline": headline, "body": body,
        "cashtag": cashtag, "ticker": cashtag.lstrip("$"),
        "status": "drafted", "provenance": "test",
        "slot": slot or f"D1-{iid}",
    }


def _plan(queues: dict[str, list[dict]], as_of: str = "2026-07-28") -> dict:
    return {
        "schema_version": 1, "produced_by": "test",
        "produced_at": f"{as_of}T00:00:00Z", "as_of": as_of,
        "accounts": [{"id": a, "queue": q} for a, q in queues.items()],
    }


def _cfg(**sentinel: Any) -> dict:
    base = {
        "max_posts_per_account_per_day": -1,
        "max_media_posts_per_account_per_day": -1,
        "max_same_cashtag_per_account_per_day": 1,
        "max_filler_per_account_per_day": 1,
        "frame_similarity": 0.60,
        "near_dup_jaccard": 0.50,
        "require_signal_disclosure": False,
    }
    base.update(sentinel)
    return {"sentinel": base}


def _reasons(report: dict) -> dict[str, list[str]]:
    return {e["id"]: e["reasons"] for e in report["quarantined"]}


class TestSkeleton:

    def test_blanks_tickers_and_numbers(self):
        # The cashtag's "$" is consumed by the ticker pattern, and any leftover
        # "$" would be eaten by the number pattern anyway.
        assert skeleton("$TEL close to going") == "X close to going"
        assert skeleton("TEL at 205.23") == "X at N"

    def test_the_founder_frame_repeat_is_visible_as_a_skeleton(self):
        """The exact 2026-07-28 collision. Token Jaccard cannot see it; the
        skeleton comparison is what makes it obvious."""
        a = "$TEL close to going. Almost there. Haven't touched it. Watching live."
        b = "$CBOE close to going. Almost there. Haven't touched it. Watching live."
        raw = cw._token_jaccard(a, b)
        assert skeleton_similarity(a, b) >= 0.60
        assert raw < 0.99, "raw token overlap is what let this ship"

    def test_genuinely_different_posts_score_below_the_threshold(self):
        a = ("$CUBI is back above the buyers' average. CUBI closed above 77.99, the average "
             "price paid since the Jun 26 volume spike. Everyone who bought that spike is now "
             "roughly flat instead of underwater.")
        b = ("$ROST just printed a new 52-week high. ROST made a new 52-week high at 235.80. "
             "New highs are where I stop guessing and start watching the retest.")
        assert skeleton_similarity(a, b) < 0.60


class TestFrameRepeatGate:

    def test_same_frame_two_tickers_one_account_is_quarantined(self):
        items = [
            _item("f1", "founder", cashtag="$TEL", slot="D1-S1",
                  headline="$TEL close to going",
                  body="TEL reclaimed its 50-day average (205.23). Almost there. "
                       "Haven't touched it. Watching live."),
            _item("f2", "founder", cashtag="$CBOE", slot="D1-S2",
                  headline="$CBOE close to going",
                  body="CBOE reclaimed its 50-day average (283.85). Almost there. "
                       "Haven't touched it. Watching live."),
        ]
        _, report = gate_plan(_plan({"founder": items}), _cfg(), receipts_age_days=1)
        reasons = _reasons(report)
        assert "f1" not in reasons, "first use of a frame survives"
        assert any(r.startswith("frame_repeat:") for r in reasons.get("f2", [])), reasons

    def test_the_same_frame_on_two_DIFFERENT_accounts_is_allowed(self):
        """Different desks are different voices to different audiences. The
        defect is one account sounding like a bot, not a shared house frame."""
        body = ("TEL reclaimed its 50-day average (205.23). Almost there. "
                "Haven't touched it. Watching live.")
        items_a = [_item("a1", "founder", cashtag="$TEL", headline="$TEL close to going",
                         body=body)]
        items_b = [_item("b1", "cici", cashtag="$CBOE", headline="$CBOE close to going",
                         body=body.replace("TEL", "CBOE").replace("205.23", "283.85"))]
        _, report = gate_plan(_plan({"founder": items_a, "cici": items_b}),
                              _cfg(near_dup_jaccard=0.99), receipts_age_days=1)
        assert not [r for rs in _reasons(report).values() for r in rs
                    if r.startswith("frame_repeat:")]

    def test_the_same_frame_on_two_different_DAYS_is_allowed(self):
        """One desk reusing a frame next week is cadence, not spam."""
        items = [
            _item("d1", "founder", cashtag="$TEL", slot="D1-S1",
                  headline="$TEL close to going",
                  body="TEL reclaimed its 50-day average (205.23). Almost there. "
                       "Haven't touched it. Watching live."),
            _item("d2", "founder", cashtag="$CBOE", slot="D4-S1",
                  headline="$CBOE close to going",
                  body="CBOE reclaimed its 50-day average (283.85). Almost there. "
                       "Haven't touched it. Watching live."),
        ]
        _, report = gate_plan(_plan({"founder": items}), _cfg(), receipts_age_days=1)
        assert not [r for rs in _reasons(report).values() for r in rs
                    if r.startswith("frame_repeat:")]

    def test_distinct_reads_on_one_account_both_survive(self):
        items = [
            _item("g1", "cici", cashtag="$CUBI", slot="D1-S1",
                  headline="$CUBI is back above the buyers' average",
                  body="CUBI closed above 77.99, the average price paid since the Jun 26 "
                       "volume spike. Everyone who bought that spike is now roughly flat "
                       "instead of underwater."),
            _item("g2", "cici", cashtag="$ROST", slot="D1-S2",
                  headline="$ROST just printed a new 52-week high",
                  body="ROST made a new 52-week high at 235.80. New highs are where I stop "
                       "guessing and start watching the retest."),
        ]
        _, report = gate_plan(_plan({"cici": items}), _cfg(), receipts_age_days=1)
        assert report["counts"]["quarantined"] == 0, report["quarantined"]

    def test_report_carries_frame_stats(self):
        _, report = gate_plan(_plan({"cici": [
            _item("s1", "cici", cashtag="$A", headline="One", body="Reclaimed the level."),
        ]}), _cfg(), receipts_age_days=1)
        block = report["checks"]["frame_repeat"]
        assert block["threshold"] == 0.60
        assert "hits" in block and "pairs_checked" in block


class TestCashtagUniqueness:

    def test_one_account_cannot_repeat_a_cashtag(self):
        """The literal 2026-07-28 defect: two flagship posts on $CBOE."""
        items = [
            _item("c1", "flagship", cashtag="$CBOE", slot="D1-S1", type="chart",
                  headline="$CBOE reclaimed its average",
                  body="CBOE reclaimed its 50-day average (283.85). The level that capped it "
                       "now has to support it."),
            _item("c2", "flagship", cashtag="$CBOE", slot="D1-S2", type="watchlist",
                  headline="$CBOE on the radar",
                  body="CBOE is 2.4% below its 52-week high (297.10). Clear it and there is "
                       "no overhead supply left."),
        ]
        _, report = gate_plan(_plan({"flagship": items}), _cfg(), receipts_age_days=1)
        reasons = _reasons(report)
        assert "c2" in reasons, "second $CBOE post must not survive"
        assert any(r.startswith("cashtag_cap:") for r in reasons["c2"]), reasons

    def test_same_cashtag_same_kind_is_blocked_even_if_the_cap_is_raised(self):
        """The kind-aware backstop. #3904 raised the cap 1 -> 3 for volume and
        that is exactly how the repeats shipped; if a future push raises it
        again, two posts on one ticker must still be different reads."""
        items = [
            _item("k1", "flagship", cashtag="$LKFN", slot="D1-S1", type="chart",
                  headline="$LKFN reclaimed its average",
                  body="LKFN reclaimed its 50-day average (60.10). The level that capped it "
                       "now has to support it."),
            _item("k2", "flagship", cashtag="$LKFN", slot="D1-S2", type="chart",
                  headline="$LKFN cleared the high",
                  body="LKFN hit a new 52-week high. Nobody who owns it is underwater, so "
                       "there is no trapped supply."),
        ]
        _, report = gate_plan(_plan({"flagship": items}),
                              _cfg(max_same_cashtag_per_account_per_day=3),
                              receipts_age_days=1)
        reasons = _reasons(report)
        assert any(r.startswith("cashtag_same_kind:") for r in reasons.get("k2", [])), reasons

    def test_two_accounts_may_share_a_cashtag(self):
        items_a = [_item("x1", "flagship", cashtag="$TEL", headline="$TEL reclaimed",
                         body="TEL reclaimed its 50-day average (205.23). It has to hold that "
                              "level on a pullback.")]
        items_b = [_item("y1", "cici", cashtag="$TEL", headline="$TEL is close",
                         body="TEL is 2.4% below its 52-week high (272.40). Clear it and there "
                              "is no overhead supply.")]
        _, report = gate_plan(_plan({"flagship": items_a, "cici": items_b}),
                              _cfg(), receipts_age_days=1)
        assert report["counts"]["quarantined"] == 0, report["quarantined"]


class TestFillerCap:

    def test_a_desk_cannot_run_a_whole_day_of_no_ticker_posts(self):
        """Kelly's ENTIRE 2026-07-28 day was four of these, so she shipped
        nothing after the operator's review."""
        items = [
            _item(f"m{n}", "kelly", cashtag="", type=t, slot=f"D1-S{n}",
                  headline=h, body=b)
            for n, (t, h, b) in enumerate([
                ("macro", "Macro, plainly",
                 "Growth data's been roughly steady while inflation is warm. Broad moves mean "
                 "the tape agrees."),
                ("macro", "Where things stand up top",
                 "18 different groups are on the move today. That count is the breadth check."),
                ("education", "The whole method, plainly",
                 "142 of 503 names show momentum setups. Rising counts precede trends."),
                ("event", "What just happened",
                 "The jobs report came in warmer than expected. Markets move on surprise."),
            ])
        ]
        _, report = gate_plan(_plan({"kelly": items}), _cfg(), receipts_age_days=1)
        killed = [i for i, rs in _reasons(report).items()
                  if any(r.startswith("filler_cap_daily:") for r in rs)]
        assert len(killed) == 3, _reasons(report)
        assert report["counts"]["passed"] == 1

    def test_ticker_posts_are_not_filler(self):
        items = [
            _item(f"t{n}", "kelly", cashtag=f"${c}", type="chart", slot=f"D1-S{n}",
                  headline=f"${c} reclaimed its average",
                  body=f"{c} reclaimed its 50-day average (205.23). The level that capped it "
                       f"now has to support it.")
            for n, c in enumerate(("TEL", "CBOE", "FDS"))
        ]
        _, report = gate_plan(_plan({"kelly": items}), _cfg(), receipts_age_days=1)
        assert not [i for i, rs in _reasons(report).items()
                    if any(r.startswith("filler_cap_daily") for r in rs)], _reasons(report)

    def test_config_and_code_defaults_agree(self):
        import yaml
        from engine.marketing import sentinel as sn
        cfg = yaml.safe_load(open("config/marketing.yml"))["sentinel"]
        assert cfg["max_filler_per_account_per_day"] == \
            sn._DEFAULT_MAX_FILLER_PER_ACCOUNT_PER_DAY
        assert cfg["frame_similarity"] == sn._DEFAULT_FRAME_SIMILARITY
        assert cfg["max_same_cashtag_per_account_per_day"] == \
            sn._DEFAULT_MAX_SAME_CASHTAG_PER_ACCOUNT_PER_DAY == 1


class TestKellyBankWidened:

    def test_the_dry_receipts_forward_macro_bank_is_wide_enough_to_not_repeat(self):
        """Four variants on a type that runs daily is a repeat generator. Kelly
        shipped four macro posts in one day that were four ways to say the same
        thing."""
        bank = cw._TEMPLATES[("macro", "dry, receipts-forward")]
        assert len(bank) >= 7, f"Kelly's macro bank is only {len(bank)} variants"

    def test_kellys_macro_headlines_are_all_distinct(self):
        bank = cw._TEMPLATES[("macro", "dry, receipts-forward")]
        headlines = [h for h, _b in bank]
        assert len(set(headlines)) == len(headlines)
