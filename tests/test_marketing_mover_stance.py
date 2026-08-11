"""Defect 4 (operator, live posts 2026-08-03): the canned directional stance.

THE POST
--------
    $FSLR, biggest move in the index today

    FSLR surged +10.3% today (Technology). Real strength or real damage,
    either way I'd let it settle first.

The operator: "this just did a daily MACD cross and is washed out after 2 months
of downtrend... If it launched then the best thing to do is to chase in, since it
already got washed. So us saying to let it settle is the dumbest thing ever and
just ruins our reputation."

THE RULING BEING PINNED
-----------------------
The defect is not that the stance pointed the wrong way. It is that the lane
emitted a DIRECTIONAL TRADING STANCE IT HAD NEVER COMPUTED: the sentence came out
of a template bank indexed by a sha256 of ticker|account|slot, and no part of
that hash has ever read a chart. A template that says "let it settle" over every
large move is wrong about half the time by construction.

So: we do not issue a directional trading stance we have not computed. Two shapes
remain lawful, and every assertion below pins one of them:

  (a) NO STANCE — the move, an honest admission of what the desk has not done,
      and stop.
  (b) A COMPUTED stance — the real technical state the move landed in, read off
      the name's own daily bars (movers_source.technical_state).

WHAT EACH TEST PINS
-------------------
  test_detector_fires_on_every_stance_that_actually_shipped
      Non-vacuity. The detector is walked over the verbatim copy that went live
      (and over the whole retired bank). A guard that cannot see the defect it
      was written for is decoration; this is the mutation check for the two
      halves that matter — remove any single named pattern in
      copywriter.uncomputed_stance and a line here goes MISS.
  test_detector_stays_quiet_on_lawful_copy
      The other half of the same check: a shape rule that fires on everything
      would pass the bank walk by deleting the product.
  test_mover_and_theme_banks_carry_no_trading_instruction
      THE ENFORCEMENT SWEEP. Enumerates every mover / theme_list template, both
      tail pools, and both voice fillers, and fails on any line matching the
      instruct-the-reader shape. This is what a future "better line" trips.
  test_every_theme_tail_is_v5_clean
      THE VOICE-DOCTRINE-v5 SWEEP (2026-08-11), added when the tail banks were
      rewritten off the first-person question. No "I / my / we / our", no "?",
      no "!", no dash tells, ≤48 chars, no uncomputed stance, and every tail a
      full statement. Fails pre-v5 on all eight retired entries.
  test_fslr_fixture_carries_no_uncomputed_instruction
      The named case, end to end through the real writer, in both the
      state-available and no-bars worlds.
  test_a_known_technical_state_is_cited_in_the_copy
      Shape (b) is wired: a fixture with a known state produces copy that says
      it, not copy that ignores it.
  test_without_bars_the_copy_degrades_to_the_no_stance_shape
      Shape (a) is the floor: no state, no stance, and still a real post.
"""
from __future__ import annotations

import re

import pytest

from engine.marketing import copywriter, movers_source as ms


# ─────────────────────────────────────────────────────────────────────────────
# The copy that actually shipped, verbatim.
#
# Sources: data/marketing/outbox/items.jsonl (ob-2026-08-03-924f26d918 is the
# $FSLR post the operator quoted), plus the full retired mover bank from
# copywriter._TEMPLATES and the retired theme tails from movers_source, as they
# stood at 91b0877057f.
# ─────────────────────────────────────────────────────────────────────────────
_SHIPPED_STANCES: tuple[str, ...] = (
    # The live $FSLR body.
    "Real strength or real damage, either way I'd let it settle first.",
    # The rest of the retired mover bank.
    "The kind of flush where I start watching for a bottom setup. "
    "Not catching it yet, levels are on the chart.",
    "One of the bigger moves in the index. The dip buyers get to find out "
    "who was early. Watching, not chasing.",
    "Respecting the move, not stepping in front of it. Levels on the chart.",
    "Worth knowing the same day, not worth chasing the candle. Chart below.",
    "Watching, not chasing.",
    "Numbers on the tape, chart below. Letting it settle.",
    "Logged. Not stepping in.",
    "On the radar. No position, no hurry.",
    "This one ripples past the single name. Letting it settle before I touch anything.",
    "The group will vote on whether it's real within days. Watching, not chasing.",
    "$FSLR +10.3% | read it, don't chase it",
    "Day one after a move this size is for watching, not heroics.",
    "Moves this size need time. The setup comes later or not at all, and both are fine.",
    "Watching, not chasing. What's your read?",
    "Letting the dust settle before doing anything clever.",
    "Chart below. Respecting it, not stepping in front.",
    "Tape check. Not touching it yet.",
    "These have a rough pattern. Watching for the setup, not catching the drop.",
    "Moves this size have a track record, and it counsels patience. Watching.",
    "Not predicting, pointing at how it usually goes. Not chasing here.",
    "I let these settle before I trust them. Levels on the chart.",
    "A move this size usually needs time.",
    # The nightly sibling bank in content_studio.
    "I'd rather be late here than early. Levels are on the chart.",
    "No rush to be a hero on this one. Watching where it settles.",
    "Nothing to do until it stops going down. Chart's below.",
    "Respect the move, don't pay for it. Levels are on the chart.",
    "Nice if you were early. Late entries here get punished.",
    "Good for anyone already in. I'm not paying this price.",
    # The retired theme tails: the same instruction wearing a question mark.
    "Am I too slow waiting for one quiet close?",
    "Do I regret passing on the first bounce?",
    "Does patience cost me the snapback here?",
    "I'd rather be late. Am I paying for that?",
    "Do I miss it if I refuse to pay up here?",
    "Am I too slow waiting for the pullback?",
    "Does not chasing keep costing me money?",
    "I want it to hold first. Too careful of me?",
)

#: Copy that states a fact, a computed state, or an honest admission, and issues
#: no instruction. If the detector fires on these it is not a shape rule, it is a
#: mute button.
_LAWFUL_COPY: tuple[str, ...] = (
    "FSLR surged +10.3% today (Technology).",
    "FSLR closed back above its 50-day average for the first time in two months.",
    "FSLR has been below its 50-day average for two months now.",
    "MU has been back above its 50-day average only a few days, after "
    "three months on the other side.",
    "NVDA has been crossing its 50-day average in both directions lately.",
    # ── v5 register (Voice Doctrine v5, 2026-08-11) ──────────────────────────
    # These five used to be first-person admissions and first-person questions
    # ("No position. What it means needs chart work I have not done.", "Am I
    # watching a rotation or one loud day?"). v5 bans first person and question
    # marks in generated post copy, so a list titled LAWFUL could not keep
    # advertising them. The intent is unchanged — the stance detector must stay
    # quiet on a stated fact, an honest absence, and a breadth note — and the
    # last two are now the LITERAL shipped tails from movers_source, which makes
    # this list a real screen on the live bank rather than a paraphrase of it.
    "No driver has been cited for the move yet.",
    "There is no cited explanation for it, and none is being invented.",
    "That is the biggest move on the board today.",
    "Breadth inside the group, not one leader.",
    "Every name on the list is lower.",
    # ── the descriptive buy/sell nouns (2026-08-04) ──────────────────────────
    # FOUND BY A MERGE, NOT BY REVIEW. The trend-bucket lines and this detector
    # shipped from two lanes for the SAME postmortem; each was green alone, and
    # together the detector quarantined the very copy the other lane wrote to
    # fix the defect. "Selling" and "buying" also name what the TAPE did, and
    # copy most often reaches for the noun compound to DENY a signal, which is
    # the opposite of issuing one. These belong here rather than in their own
    # test because the must-fire direction is already pinned by
    # test_detector_fires_on_every_stance_that_actually_shipped -- a carve-out
    # that silenced the rule would break that sweep, not this list.
    "First green that means anything after months of selling.",
    "A flush this deep after weeks of selling is capitulation territory.",
    "That's a fact about crowds, not a buy signal.",
    "Sell pressure finally let up.",
)


def test_detector_fires_on_every_stance_that_actually_shipped():
    """NON-VACUITY. Fails before the fix in the only way that matters: the
    function under test did not exist, and every line below was live copy."""
    missed = [s for s in _SHIPPED_STANCES if not copywriter.uncomputed_stance(s)]
    assert len(_SHIPPED_STANCES) >= 30, "sample too small to prove a sweep"
    assert not missed, (
        "uncomputed_stance did not see copy that actually shipped:\n"
        + "\n".join(f"  {m!r}" for m in missed)
    )


def test_detector_stays_quiet_on_lawful_copy():
    """The other half. A rule that fires on a stated fact or on a computed state
    would force the banks into silence rather than into honesty."""
    noisy = [(s, copywriter.uncomputed_stance(s)[:1]) for s in _LAWFUL_COPY
             if copywriter.uncomputed_stance(s)]
    assert not noisy, f"detector over-fires on lawful copy: {noisy}"


# ─────────────────────────────────────────────────────────────────────────────
# The enforcement sweep
# ─────────────────────────────────────────────────────────────────────────────

def _stance_banks() -> list[tuple[str, str]]:
    """(label, line) for every mover/theme reaction line the desk can ship.

    Enumerated from the live data structures, never from a copy of them, so a
    line ADDED to any of these banks is walked the day it is written.
    """
    out: list[tuple[str, str]] = []
    for (type_id, voice), bank in copywriter._TEMPLATES.items():
        if type_id not in ("mover", "theme_list"):
            continue
        for i, variant in enumerate(bank):
            out.append((f"_TEMPLATES[{type_id}/{voice}][{i}].headline", variant[0]))
            out.append((f"_TEMPLATES[{type_id}/{voice}][{i}].body", variant[1]))
    for name, pool in (("_TAIL_DOWN", ms._TAIL_DOWN), ("_TAIL_UP", ms._TAIL_UP)):
        for i, tail in enumerate(pool):
            out.append((f"movers_source.{name}[{i}]", tail))
    for name, filler in (("_MOVER_VOICE_FILLER", copywriter._MOVER_VOICE_FILLER),
                         ("_THEME_VOICE_FILLER", copywriter._THEME_VOICE_FILLER)):
        for voice, line in filler.items():
            out.append((f"copywriter.{name}[{voice}]", line))
    return out


def test_mover_and_theme_banks_carry_no_trading_instruction():
    """THE SWEEP. Every mover/theme template line, both tail pools, both fillers.

    Fails pre-fix on 20+ entries (see _SHIPPED_STANCES, which is that bank). The
    assertion is what a future edit trips: reintroducing "watching, not chasing"
    in any wording fails here rather than on the flagship account.
    """
    lines = _stance_banks()
    assert len(lines) >= 100, f"only {len(lines)} bank lines walked - guard is vacuous"
    bad = [f"{label}: {line!r} -> {copywriter.uncomputed_stance(line)[0][:120]}"
           for label, line in lines if copywriter.uncomputed_stance(line)]
    assert not bad, (
        "a mover/theme bank line tells the reader what to do with the move:\n"
        + "\n".join(bad)
    )


#: The v5 voice bans, as one screen. `\bI\b` stays case-SENSITIVE (a lower-case
#: "i" is an enumeration letter, not the English pronoun); everything else is
#: case-insensitive because a pronoun is capitalised exactly when it opens the
#: sentence, which is the commonest place for it.
_V5_FIRST_PERSON = re.compile(
    r"\bI\b|I'm|I'd|I'll|I've|\b(?:my|mine|myself|me|we|us|our|ours)\b")
_V5_FIRST_PERSON_CI = re.compile(
    r"\b(?:my|mine|myself|me|we|us|our|ours)\b", re.IGNORECASE)


def v5_voice_violations(line: str) -> list[str]:
    """The Voice Doctrine v5 bans a generated bank line must clear. [] = clean.

    Deliberately NOT a call into copywriter: this is the independent screen, so
    a bank that regrows the v4 register fails here even if the generation-side
    validator is loosened or renamed. See the module docstring of
    engine/marketing/movers_source.py for the standing rule.
    """
    out: list[str] = []
    if _V5_FIRST_PERSON.search(line) or _V5_FIRST_PERSON_CI.search(line):
        out.append("first person: the subject of the sentence is the market")
    if "?" in line:
        out.append("question mark: the post states, it does not ask")
    if "!" in line:
        out.append("exclamation mark")
    if "#" in line:
        out.append("hashtag")
    if "—" in line or "–" in line:
        out.append("em/en dash (house dash tell)")
    return out


def test_every_theme_tail_is_v5_clean():
    """THE v5 SWEEP over both tail pools (Voice Doctrine v5, 2026-08-11).

    Fails pre-v5 on all eight entries: the retired bank was first-person
    questions ("Am I getting a second session out of this?"). This is the
    assertion a future "better line" trips, and it is a superset of the older
    rules rather than a replacement for them — the length ceiling and the
    uncomputed-stance screen are re-asserted here so one test names every
    property a tail owes.
    """
    pools = {"_TAIL_DOWN": ms._TAIL_DOWN, "_TAIL_UP": ms._TAIL_UP}
    bad: list[str] = []
    for name, pool in pools.items():
        assert len(pool) == 4, f"{name} has {len(pool)} tails, want 4"
        for i, tail in enumerate(pool):
            for v in v5_voice_violations(tail):
                bad.append(f"{name}[{i}] {tail!r}: {v}")
            if len(tail) > ms._TAIL_MAX_CHARS:
                bad.append(f"{name}[{i}] {tail!r}: {len(tail)} chars "
                           f"(max {ms._TAIL_MAX_CHARS})")
            if copywriter.uncomputed_stance(tail):
                bad.append(f"{name}[{i}] {tail!r}: "
                           f"{copywriter.uncomputed_stance(tail)[0][:90]}")
            if not tail.rstrip().endswith("."):
                bad.append(f"{name}[{i}] {tail!r}: a tail is a full statement")
    assert not bad, "\n".join(bad)
    assert not (set(ms._TAIL_DOWN) & set(ms._TAIL_UP)), (
        "a tail in both pools would render direction-keying decorative")


def test_no_rewritten_headline_is_stranded_on_a_connective():
    """Collateral guard for a bank REWRITE, not for the stance rule.

    Rewriting 24 headlines is 24 fresh chances to end one on a preposition
    ("what the move landed on"), which validate_copy reports as a fragment and
    which the stance detector has no reason to notice. The FSLR fixture only
    renders the ONE variant its hash lands on, so the whole bank is walked here.
    """
    ctx = {
        "cashtag": "$FSLR", "ticker": "FSLR", "mover_pct": "+10.3%",
        "theme_name": "Solar", "theme_agg_pct": "+3.7%", "theme_direction": "up",
        "mover_state": "FSLR closed back above its 50-day average",
        "top_fact_text": "FSLR surged +10.3% today (Technology).",
        "cashtag_list": "$A $B $C $D",
        "theme_question": "Breadth inside the group, not one leader.",
        "voice": "authoritative desk", "type": "mover",
    }
    bad = []
    for (type_id, voice), bank in copywriter._TEMPLATES.items():
        if type_id not in ("mover", "theme_list"):
            continue
        for variant in bank:
            rendered = copywriter._render_template(variant[0], ctx)
            for v in copywriter.headline_fragments(rendered):
                bad.append(f"{type_id}/{voice}: {v}")
    assert not bad, "\n".join(bad)


def test_every_mover_voice_bank_offers_both_lawful_shapes():
    """The needs_state / no_state partition must be TOTAL and non-degenerate.

    _variant_allowed filters the pool to exactly one of the two shapes, and
    write_posts_deterministic falls back to the UNFILTERED bank when the pool
    comes back empty. A voice missing either side would therefore silently
    restore the unfiltered pool - and with it the possibility of rendering a
    "{mover_state}" line into a context that has no state.

    SCOPED TO THE NON-BUCKET BANK (2026-08-04). The trend-context lines are a
    SECOND, independent axis that landed for the same postmortem from another
    lane: they gate on the tape shape, carry no {mover_state} token, and so
    declare neither state tag by design. Requiring totality over the whole bank
    would force a meaningless state tag onto every future bucket line. What has
    to stay total is the partition of the lines the state axis actually governs,
    because that is what makes the empty-pool fallback unreachable.
    """
    for (type_id, voice), bank in copywriter._TEMPLATES.items():
        if type_id != "mover":
            continue
        state_bank = [
            v for v in bank
            if not (copywriter._MOVER_CONTEXT_TAG_SET
                    & (set(v[2]) if len(v) > 2 else set()))
        ]
        tags = [set(v[2]) if len(v) > 2 else set() for v in state_bank]
        with_state = [t for t in tags if "needs_state" in t]
        without = [t for t in tags if "no_state" in t]
        assert with_state, f"mover/{voice}: no needs_state variant"
        assert without, f"mover/{voice}: no no_state variant"
        assert len(with_state) + len(without) == len(state_bank), (
            f"mover/{voice}: a non-bucket variant declares neither shape"
        )
        # A needs_state line must actually use the token, and a no_state line
        # must not - otherwise the tag is a label with no referent.
        for variant in bank:
            tagset = set(variant[2]) if len(variant) > 2 else set()
            uses = "{mover_state}" in variant[0] or "{mover_state}" in variant[1]
            assert uses == ("needs_state" in tagset), (
                f"mover/{voice}: tag and token disagree in {variant[0]!r}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# The computed state
# ─────────────────────────────────────────────────────────────────────────────

def _washed_out_then_reclaimed() -> list[float]:
    """The $FSLR shape: a long stretch under the 50-day, then a session that
    closes back above it. Sixty flat bars seed the average, forty-four sessions
    of steady decline take price under it, and one +35% session reclaims it."""
    closes = [100.0] * 60 + [100.0 - 0.5 * i for i in range(1, 45)]
    closes.append(closes[-1] * 1.35)
    return closes


def _washed_out_still_under() -> list[float]:
    """Same washout, and the big up-day does NOT clear the average. This is the
    literal $FSLR tape: +10.3% off a two-month slide is still under the 50-day."""
    closes = [100.0] * 60 + [100.0 - 0.5 * i for i in range(1, 45)]
    closes.append(closes[-1] * 1.103)
    return closes


def test_state_reads_the_setup_the_canned_stance_never_looked_at():
    """The arithmetic, pinned per branch. Each phrase is a fact about the bars."""
    assert ms._state_from_closes("FSLR", _washed_out_then_reclaimed()) == (
        "FSLR closed back above its 50-day average for the first time in two months"
    )
    assert ms._state_from_closes("FSLR", _washed_out_still_under()) == (
        "FSLR has been below its 50-day average for two months now"
    )
    fresh = _washed_out_then_reclaimed()
    fresh += [fresh[-1] * 1.01, fresh[-1] * 1.02]
    assert "only a few days" in (ms._state_from_closes("FSLR", fresh) or "")


def test_a_flat_series_gets_no_state_rather_than_a_confident_one():
    """PINS the two-sided-test defect. `close > sma` has no third state, so a
    price sitting exactly on its average resolved to "below" and a flat series
    produced the fully confident "X has been below its 50-day average for a
    month now" about a price that had not moved at all."""
    assert ms._state_from_closes("X", [100.0] * 90) is None


def test_short_or_broken_history_yields_no_state():
    """Degrading to no-stance is always lawful; guessing never is."""
    assert ms._state_from_closes("X", [100.0] * 40) is None
    assert ms._state_from_closes("X", []) is None
    assert ms._state_from_closes("X", ["nope"] * 90) is None  # type: ignore[list-item]


def test_technical_state_is_fail_soft_when_the_bars_are_not_there(tmp_path):
    """No parquet, no pandas, no store: None, never an exception."""
    assert ms.technical_state("NOSUCH", tmp_path) is None
    assert ms.technical_state("", tmp_path) is None
    assert ms.technical_state("FSLR", None) is None


# ─────────────────────────────────────────────────────────────────────────────
# End to end through the real writer
# ─────────────────────────────────────────────────────────────────────────────

_FSLR_MOVER = {"ticker": "FSLR", "name": "First Solar", "pct": 10.28,
               "sector": "Technology", "asof": "2026-08-03",
               "source": "sp500_heatmap"}


def _render(monkeypatch, *, closes: list[float] | None,
            voice: str = "authoritative desk") -> tuple[str, str]:
    """(headline, body) for the $FSLR mover through the production path.

    Only the BAR LOADER is stubbed - facts, context, template selection and
    validation are all the real ones, so an assertion here lands on the copy the
    lane would actually ship.
    """
    import engine.marketing.chart_render as cr

    def _fake(ticker, root, n=90, subdirs=None):
        if closes is None:
            return None
        dates = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(closes))]
        return (dates, list(closes), list(closes), list(closes), list(closes),
                [1_000_000.0] * len(closes))

    monkeypatch.setattr(cr, "load_ohlcv", _fake)
    facts = ms.mover_facts(_FSLR_MOVER, root=".", asof="2026-08-03")
    ctx = copywriter.build_context(
        {"type": "mover", "ticker": "FSLR", "cashtag": "$FSLR",
         "account": "flagship", "_mover_data": _FSLR_MOVER,
         "_mover_facts": facts},
        facts=facts)
    ctx.update({"type": "mover", "voice": voice, "slot": "LIVE-EOD",
                "has_chart": True})
    posts = copywriter.write_posts_deterministic([ctx])
    assert posts, "writer returned nothing"
    return posts[0].get("headline", ""), posts[0].get("body", "")


@pytest.mark.parametrize("voice", sorted(
    {v for (t, v) in copywriter._TEMPLATES if t == "mover"}))
@pytest.mark.parametrize("bars", ["state", "no-bars"])
def test_fslr_fixture_carries_no_uncomputed_instruction(monkeypatch, voice, bars):
    """THE NAMED CASE. Every voice, both worlds, through the real writer.

    Pre-fix this fails on the authoritative-desk render, which is the bank that
    held "Real strength or real damage, either way I'd let it settle first."
    """
    closes = _washed_out_then_reclaimed() if bars == "state" else None
    headline, body = _render(monkeypatch, closes=closes, voice=voice)
    text = f"{headline} {body}"
    assert "$FSLR" in text and "+10.3%" in text
    assert copywriter.uncomputed_stance(text) == [], (
        f"{voice}/{bars}: {text!r} -> {copywriter.uncomputed_stance(text)}")
    assert "{" not in text, f"unfilled token in {text!r}"
    # A rewritten bank is a fresh chance to strand a headline on a connective,
    # which validate_copy reports but nothing in the stance rule would notice.
    assert copywriter.headline_fragments(headline) == [], headline
    assert copywriter.banned_language(text) == [], text


@pytest.mark.parametrize("voice", sorted(
    {v for (t, v) in copywriter._TEMPLATES if t == "mover"}))
def test_a_known_technical_state_is_cited_in_the_copy(monkeypatch, voice):
    """SHAPE (b) IS WIRED. Given bars carrying a known state, the post says it.

    This is the half a "no stance" fix alone would not deliver: the ruling asks
    for a computed stance where one is available, not for silence everywhere.
    """
    headline, body = _render(
        monkeypatch, closes=_washed_out_then_reclaimed(), voice=voice)
    assert "50-day average" in body, f"{voice}: state not cited in {body!r}"
    assert "for the first time in two months" in body, body


@pytest.mark.parametrize("voice", sorted(
    {v for (t, v) in copywriter._TEMPLATES if t == "mover"}))
def test_without_bars_the_copy_degrades_to_the_no_stance_shape(monkeypatch, voice):
    """SHAPE (a) IS THE FLOOR. No bars, so no state, so no stance - and still a
    real post that names the move and carries a reaction."""
    headline, body = _render(monkeypatch, closes=None, voice=voice)
    assert "50-day" not in body, f"{voice}: claimed a state it never computed: {body!r}"
    assert "+10.3%" in f"{headline} {body}"
    assert copywriter.uncomputed_stance(f"{headline} {body}") == []


def test_validate_copy_rejects_an_instruction_on_a_mover_but_not_elsewhere():
    """The last net, and its SCOPE.

    The banks are clean, so this catches the other routes into these two kinds
    (the nightly LLM writer, a future hand-composed lane). It is scoped to
    mover/theme_list because a watchlist_runaway post that declines to chase is
    talking about a level THIS DESK published and then watched run away - a
    computed position, and the honest one. Widening this would delete copy that
    earned its stance.
    """
    ctx = {"ticker": "FSLR", "cashtag": "$FSLR", "type": "mover",
           "account": "flagship", "numbers_whitelist": ["+10.3%"],
           "emoji_budget": 0}
    dirty = "FSLR surged +10.3% today. I'd let it settle first."
    stance = [v for v in copywriter.validate_copy("$FSLR +10.3%", dirty, ctx)
              if "uncomputed stance" in v]
    assert stance, "validate_copy let a mover ship a canned trading instruction"

    runaway = dict(ctx, type="watchlist_runaway")
    assert not [v for v in copywriter.validate_copy("$FSLR ran", dirty, runaway)
                if "uncomputed stance" in v], (
        "the gate must not reach the kinds whose stance IS computed")
