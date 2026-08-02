"""engine.marketing.reply_drafter — per-persona reply drafting (XG-W4).

The reply formula (constitution §9.3): **one gift, one grip, one doorway**.

  * **gift** — a missing fact, mechanism, chart, reframe, or condition. Ours
    comes from the own-feed fact builders, so every number in it is already on
    the whitelist. The drafter never invents a figure.
  * **grip** — tension, surprise, or compression. Family-specific.
  * **doorway** — a natural surface for response. It need not be a question;
    constant questions become formulaic, which is its own tell.

**Families, not paraphrases.** Constitution §9.4 asks for strategically
different DESIGNS, and is explicit that three paraphrases of one thought is the
failure mode. ``FAMILIES`` is therefore a register of reasoning MOVES — the
missing-variable move and the second-order move reach different conclusions from
the same fact, which is what makes an alternate draft worth having. Rotation is
least-recently-used per account, so one successful family cannot take over
(§13.7 anti-sameness).

**Voice is borrowed, never forked.** The banned-vocab guard and the expression
dial belong to ``copywriter``/``expression_dial``; this module calls them with
``kind="reply"`` (dial 2 for employees, 1 for flagship, charter §2 amendment 3)
and owns no word list of its own.

**The LLM phrases, it never drafts.** ``draft_reply`` composes deterministically
and then hands the PRIMARY draft to ``reply_voice.voice_or_fallback`` (E4;
``research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md``), which re-phrases it in the
register the reply corpus says earns a reply. That pass is two-key armed, never
raises, and returns THIS draft on any gate hit — so the deterministic path below
is the product, and the model is an upgrade on top of it. Alternates are never
voiced: they exist to differ in reasoning MOVE, not in wording.

**Charts are EOD-only.** ``chart_render`` reads nightly parquet, so a reply that
attaches one must carry an as-of stamp; presenting yesterday's bar as live is
the failure the charter names by hand. ``attach_chart`` stamps every reference,
and the composer prints the stamp in the copy when a chart rides along.

**The warmth register (XG-W4 warmth build).** ``FAMILIES`` is a register of
analytical MOVES and nothing in it carries warmth, delight, curiosity or the
shared-frustration move — the emotional half of what earns a reply back and a
follow. ``WARMTH_MOVES`` is the second rotation axis that closes that gap: a
reply is now **one reasoning family + one warmth move + one doorway**, with two
independent LRUs so "concede-then-hold + missing variable" cannot become a
signature. The one law that governs all eight moves:

    Warmth is FUSED into the clause that delivers the gift. It is never a
    second sentence bolted on in front of one.

That is the sharpest finding in the winning-reply corpus and it is also Meagan's
own pinned codex line ("the playful line is always followed by the useful one,
never instead of it") — house idiom, not an invention. Warmth never replaces the
gift: an empty gift is still an abstention, because "pure reaction warmth, zero
information" is the one bucket the corpus is confident does not work (median
eng/view 0.0032 against 0.0122 for pure-analytical).

**The doorway is drawn, never welded (XG-W4 tail build).** ``FAMILIES`` gives the
reasoning move and ``WARMTH_MOVES`` the delivery register, but until 2026-08-01
the sentence that CLOSED the reply was one fixed string per family — nine
distinct tails across four personas, every warmth move and every thread, which
is the most legible bot-farm signature four accounts sharing an audience can
emit. ``FAMILY_TAILS`` is the third axis: a per-family, PER-DESK pool of doorway
sentences, picked by a stable hash of (account, family, thread) and rotated
least-recently-used over ``recent_tails``. The lanes are disjoint by
construction, which is what makes "two desks on one parent never close on the
same line" a guarantee rather than a probability.

**The SHAPE is drawn, not fixed (XG-W4b §A/§B).** Families, warmth moves and
doorways all differentiate the CONTENT of a two-sentence gift+grip+doorway
reply — and until 2026-08-02 that was the only shape the composer had. Every
employee reply was 30-45 words against a corpus whose median winner is 11 and
whose 1-5 word replies are 26.1% of the winners; short reactions were 0% of
output. ``reply_shape`` is the fourth axis: five shapes (``one_line``,
``fragment_exchange``, ``addition``, ``compact_chain``, ``full``), a per-persona
response-type mix, and a deficit-weighted stable draw that lands the measured
distribution near the operator's 30/25/15/15/10/5 WITHOUT being a rotation —
because four accounts cycling shapes in lockstep is the same bot-farm signature
the tail build closed one axis over. ``compose(..., shape="full")`` is
byte-identical to what this module shipped before, and a parity test over the
whole family x warmth grid says so.

Public API:
    FAMILIES: dict[str, dict]
    WARMTH_MOVES: dict[str, dict]
    FAMILY_TAILS: dict[str, dict[str, tuple[str, ...]]]
    family_ids() -> list[str]
    warmth_ids() -> list[str]
    rotate_family(recent, *, allowed=None) -> str
    rotate_warmth(recent, *, allowed=None) -> str
    classify_parent(target) -> str | None
    warmth_moves_for(account, *, parent_shape=None, family=None, root=None) -> list[str]
    tail_lane(account) -> str
    tails_for(account, family, root=None) -> list[str]
    select_tail(account, family, *, thread_id, recent_tails=None, root=None) -> str
    render_tail(template, ctx) -> str
    compose(family, gift, ctx, *, warmth=None) -> str
    draft_reply(*, account, target, facts, ...) -> dict
    attach_chart(as_of, chart_id, *, root=None) -> dict | None
    prerender_artillery(tickers, as_of, *, root=None, ...) -> list[dict]
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: The reply-family register (constitution §9.4). Each entry is a distinct
#: reasoning move, with the author-response trigger it serves (§9.5) recorded so
#: a later re-weighting can argue from design intent, not vibes.
FAMILIES: dict[str, dict[str, Any]] = {
    "missing_variable": {
        "label": "missing variable",
        "move": "name the variable the thread has not priced",
        "trigger": "supplies evidence they can evaluate",
        "dial_floor": 1,
    },
    "second_order": {
        "label": "second-order implication",
        "move": "grant the claim, derive what it forces next",
        "trigger": "extends their idea",
        "dial_floor": 1,
    },
    "respectful_disagreement": {
        "label": "respectful disagreement",
        "move": "grant the observation, dispute the mechanism",
        "trigger": "respectfully challenges the mechanism",
        "dial_floor": 1,
    },
    "compression": {
        "label": "compression",
        "move": "compress the whole thread into one line plus the number",
        "trigger": "supplies evidence they can evaluate",
        "dial_floor": 1,
    },
    "conditional_prediction": {
        "label": "conditional prediction",
        "move": "state a falsifiable if/then with a level",
        "trigger": "offers a falsifiable condition",
        "dial_floor": 1,
    },
    "human_reaction": {
        "label": "human reaction + analysis",
        "move": "a plain reaction, then one useful sentence",
        "trigger": "gives credit before adding a complication",
        "dial_floor": 2,
    },
    "reframe": {
        "label": "reframe",
        "move": "change what the move is about",
        "trigger": "extends their idea",
        "dial_floor": 1,
    },
    "cross_market_lead": {
        "label": "cross-market lead",
        "move": "point at the market that moved first",
        "trigger": "connects their topic to an adjacent market",
        "dial_floor": 1,
    },
    "correction": {
        "label": "correction without humiliation",
        "move": "fix the fact, never name the person",
        "trigger": "supplies evidence they can evaluate",
        "dial_floor": 1,
    },
    "micro_framework": {
        "label": "micro-framework",
        "move": "a two-part lens the reader can carry",
        "trigger": "extends their idea",
        "dial_floor": 1,
    },
    "author_question": {
        "label": "author-specific question",
        "move": "one precise question inside their expertise",
        "trigger": "asks a precise question inside their expertise",
        "dial_floor": 1,
    },
    "original_chart": {
        "label": "original chart",
        "move": "lead with the chart nobody else in the thread has",
        "trigger": "supplies evidence they can evaluate",
        "dial_floor": 1,
        "needs_chart": True,
    },
    "acknowledgment_plus_one": {
        "label": "acknowledgment with one useful addition",
        "move": "agree in four words, then add exactly one thing",
        "trigger": "gives credit before adding a complication",
        "dial_floor": 1,
    },
    "callback": {
        "label": "callback",
        "move": "connect to a prior public position of ours",
        "trigger": "extends their idea",
        "dial_floor": 1,
        "needs_callback": True,
    },
    # ── XG-W4b (§B.2): the fifteenth family, and the first one added since the
    # register was written ────────────────────────────────────────────────────
    #
    # HUMOR HAD NO HOME. The operator's response mix puts 5% on humor; the
    # doctrine's top-60 corpus puts dry wit at 28.3%, the single largest WINNING
    # category (§2); §5 grants a humor budget to every employee desk. And there
    # was no family whose MOVE produces it — a humor quota routed to
    # `human_reaction` produces a plain reaction with a comedy label on it, which
    # is a distribution that reads right in a report and wrong in a timeline.
    #
    # `dial_floor: 2` is what keeps it off the flagship and the founder, and it
    # is the reason `dial_floor` on FAMILIES stops being decorative in this
    # build: `draft_reply`'s `allowed` comprehension now reads it (see the WHY
    # there). No second availability table to maintain.
    #
    # PER-DESK LAWFULNESS, from each pinned codex, so a later "cici should not
    # joke" edit argues with the derivation rather than with taste:
    #   kelly   "internet-native dry wit" is her verbatim §5 register. Her home.
    #   meagan  WARM variant only. Her codex bans "finance-bro irony" and her
    #           restraint line is "the playful line is always followed by the
    #           useful one, never instead of it" — affectionate about a crowd,
    #           never ironic about a person.
    #   sophia  permitted and rare. "Calm confidence" tolerates understatement,
    #           and her craft-metaphor cap (1/7d) is untouched because
    #           understatement spends no metaphor.
    #   cici    permitted, NARROWED. Her banned list (`exotic`, `mysterious
    #           east`, `China up/down`) names exactly the failure mode of humor
    #           on her beat: a joke about a market she covers is one step from a
    #           joke about a country. Her lawful surface is the CLOCK and the
    #           FORECASTERS only, never a market, a people or a policy — enforced
    #           the way `wry_solidarity`'s target rule is, by the copy pool plus
    #           `_targets_a_person`.
    #   flagship / founder — none, by dial_floor.
    "dry_understatement": {
        "label": "dry understatement",
        "move": "state the absurd consequence flatly, no setup and no explanation",
        "trigger": "gives the room a line worth quoting",
        "dial_floor": 2,
    },
}

#: A family that draws ANOTHER family's doorway pool in the ``full`` shape.
#:
#: `dry_understatement`'s lawful shapes are `one_line`, `fragment_exchange` and
#: `full`; only the last needs a doorway, and the register it needs there is the
#: plain-reaction register `human_reaction` already owns. Writing a fifth
#: near-identical pool would have added twenty lines of copy expressing one
#: mapping. The alias lives in `tails_for` rather than in `compose` so
#: `select_tail`, `compose` and `draft_reply`'s reported tail cannot disagree —
#: a history that records a doorway which never shipped is worse than no history.
_TAIL_FAMILY_ALIAS: dict[str, str] = {"dry_understatement": "human_reaction"}


def family_ids() -> list[str]:
    return list(FAMILIES.keys())


def rotate_family(recent: list[str] | tuple[str, ...] | None, *,
                  allowed: list[str] | None = None) -> str:
    """Least-recently-used family (§13.7: one family may not take over).

    ``recent`` is oldest-first. Families never used rank ahead of any family
    that has been; among used ones, the longest-ago wins.
    """
    pool = [f for f in (allowed or family_ids()) if f in FAMILIES]
    if not pool:
        pool = family_ids()
    recent_list = [str(f) for f in (recent or [])]
    def _key(fam: str) -> tuple[int, int]:
        try:
            return (1, recent_list.index(fam))
        except ValueError:
            return (0, pool.index(fam))
    return sorted(pool, key=_key)[0]


# ===========================================================================
# The warmth register — the emotional half of the reply formula
# ===========================================================================
#
# WHY THIS IS A SECOND AXIS AND NOT FOURTEEN MORE FAMILIES. A family is the
# reasoning MOVE the reply makes; a warmth move is the REGISTER the move is
# delivered in. Folding warmth into ``FAMILIES`` would have forced a choice
# between "concede and hold" and "missing variable" when the corpus's best reply
# is both at once (MacroAlf → @NorthmanTrader, 59 likes: a three-word concession
# running straight into the mechanism, no full stop between them). Two axes with
# two independent LRUs is also what stops any single family×warmth pairing from
# hardening into a tell.
#
# WHY WARMTH IS NOT A PAYLOAD. Measured on the 75-row winning-reply corpus, both
# buckets THIN: pure reaction warmth with zero information, n=14, median eng/view
# 0.0032; pure analytical with zero warmth markers, n=10, median 0.0122. Read
# correctly that does NOT say "be cold" — it says warmth that occupies its own
# sentence spends words and returns nothing, while warmth that shapes the
# DELIVERY of a real point costs zero words and changes who replies. Hence the
# ≤5 content-unit budget on a standalone opener (``compose`` RAISES above it),
# and hence ``fuse: "conjunction"`` being the preferred form.
#
# WHY ``dial_floor`` IS WIRED HERE AND IS NOT IN ``FAMILIES``. Every FAMILIES
# entry declares ``dial_floor`` and NOTHING reads it (verified across drafter,
# voice and critics) — a decorative field. Here it is load-bearing: a warmth move
# is admissible only when the account's reply dial reaches its floor, which is
# what mechanically keeps the flagship an evidence desk (reply dial 1, charter §2
# amendment 3) while the four employee desks (reply dial 2) get the warm
# register. Until now that rule existed only as prose in the reply doctrine's §5
# register map ("Never: anything warm" in the flagship column).

#: Closed vocabulary of parent-post shapes. ``fits``/``wrong_when`` draw from
#: this and nothing else, so a typo is a test failure rather than a move that
#: silently never fires. ``sensitive_event`` is never a ``fits`` value for any
#: move: ``reply_critics.blocklist`` hard-stops the whole item on those terms and
#: that gate is upstream of everything here.
PARENT_SHAPES: tuple[str, ...] = (
    "analysis_claim", "data_post", "chart_post", "question_to_the_room",
    "prediction", "hot_take", "correction_of_someone_else", "resource_or_thread",
    "personal_setback", "personal_win", "wire_or_headline", "sensitive_event",
)

#: The eight warmth moves. Each entry:
#:
#:   label            human name
#:   does             the SENTENCE-LEVEL mechanic, handed to the phrasing prompt
#:   fits             parent shapes the move is for (PARENT_SHAPES members)
#:   wrong_when       parent shapes the move is WRONG for; the fitness gate
#:   dial_floor       1 or 2; read against the account's codex reply dial
#:   fuse             "conjunction" (no full stop; the preferred form) or
#:                    "standalone" (its own sentence, hard ≤5 content units)
#:   families_ok      reasoning families the move may ride, or None for any
#:   openers          per-account register copy (see WHY below)
#:   needs_detail     the opener carries a {detail} slot filled from the parent
#:   needs_thesis     selectable only against an OPEN entry in the opinion ledger
#:   relationship_only  ships without an analytical gift; not a growth move
#:
#: WHY THE OPENERS ARE KEYED BY ACCOUNT AND WHY THAT IS NOT A HARDCODED
#: AVAILABILITY TABLE. The per-persona codices in the persona SPEC layer (which
#: only ``expression_dial`` may read from here, see the fence note below)
#: are §5-FROZEN ("assemble, never invent") — this build may not add a quirk
#: marker, may not edit a register line, and therefore has nowhere else to put
#: REGISTER COPY. What the codex does own is AVAILABILITY, and
#: ``warmth_moves_for`` derives that from the live spec every time it is called:
#:
#:   1. ``voice_codex.warmth_moves`` (``allow``/``deny``), when a spec declares
#:      it — the canonical override, honoured today, used by no spec today;
#:   2. ``voice_codex.dial_profile`` → the reply dial → ``dial_floor``;
#:   3. ``voice_codex.zh`` → moves whose opener carries a Chinese term;
#:   4. every opener is run through the persona's OWN guards
#:      (``copywriter.banned_language`` + ``expression_dial.violations`` +
#:      ``am_r1_hits``) and a move with no surviving opener is unavailable.
#:
#: (4) is the one that matters: adding a word to a codex ``banned`` list, or
#: switching a quirk marker dark, removes the offending opener the same night
#: with NO code change. An account with no opener written for a move is out of
#: character for it, and the grounding is recorded in the comment beside it.
WARMTH_MOVES: dict[str, dict[str, Any]] = {
    # -- MOVE 1 -------------------------------------------------------------
    # Grants the other side in ≤5 words, no full stop, then runs straight into
    # the mechanism that holds our position. The concession IS the warmth; the
    # mechanism is the gift. Evidence: MacroAlf → @NorthmanTrader, 59 likes,
    # "Fair point but risk premia and valuations could be plausibly
    # supportive... Here we are looking at Powell keeping policy tight while we
    # sleepwalk into a recession". The single cleanest instance in the corpus.
    "concede_and_hold": {
        "label": "concede and hold",
        "does": ("grant the other side in five words or fewer, with no full "
                 "stop, then run straight into the mechanism that holds our "
                 "position; no hedge between the two"),
        "fits": ("analysis_claim", "hot_take", "prediction",
                 "correction_of_someone_else"),
        # A concession to a FACT reads as filler (there is no position to
        # concede), and conceding to someone's bad week is not a concession.
        "wrong_when": ("data_post", "wire_or_headline", "personal_setback",
                       "personal_win", "sensitive_event"),
        "dial_floor": 1,
        "fuse": "conjunction",
        "families_ok": frozenset({
            "respectful_disagreement", "second_order", "reframe",
            "missing_variable", "correction", "cross_market_lead",
        }),
        "openers": {
            # sophia: her warmth channel is GENEROSITY OF FRAME — she concedes
            # ground elegantly and holds position. Her codex is "polished,
            # narrative, measured; zero exclamations", so no "!" here or below.
            "sophia": ("Fair, and the harder part is that",),
            # kelly: her codex bans every hedging softener (kinda/maybe/sorta/
            # i guess/probably just), so her concession is FLAT, never hedged.
            # Lowercase is register-pinned for her and for her alone.
            "kelly": ("fair. the thing that argues against it:",),
            # cici: "polite corrections" is her pinned register, and the polite
            # correction IS a concession followed by a hold.
            "cici": ("Holds for the US session. Overnight it looks different:",),
            # meagan: her codex opens on a human REACTION, so a concession
            # competes with her signature opener. Available, deliberately thin.
            "meagan": ("okay so that is fair, and the part underneath it:",),
        },
    },
    # -- MOVE 2 -------------------------------------------------------------
    # A prior wrong read stated flatly, zero self-flagellation, zero apology,
    # then the corrected model. Vulnerability as a DELIVERY VEHICLE for content,
    # never as content. Evidence: saxena_puru → @TraderCT, 46 likes — "Yes, I
    # didn't know party would end during QE... I was wrong." The confession is
    # the frame; the replaced mental model is the payload.
    "flat_confession": {
        "label": "flat confession",
        "does": ("state a prior wrong read flatly in one clause, with no "
                 "apology and no self-flagellation, then hand over the "
                 "corrected model"),
        "fits": ("analysis_claim", "prediction", "hot_take"),
        # Manufacturing a confession is fabricated experience about our own
        # reasoning and is barred by the same principle as AM-R1; and a
        # confession on someone's bad news makes their moment about us.
        "wrong_when": ("personal_setback", "personal_win", "sensitive_event",
                       "wire_or_headline"),
        "dial_floor": 2,
        "fuse": "standalone",
        "families_ok": frozenset({
            "correction", "reframe", "second_order", "missing_variable",
        }),
        # HARD WIRING, not a style note. `reply_critics.position_consistency`
        # rejects a draft contradicting an open thesis UNLESS the draft carries
        # a literal phrase from `_CHANGE_MARKERS` — and a confession is BY
        # CONSTRUCTION that contradiction. An opener phrased "I read this
        # backwards" trips the very critic this move exists to satisfy, so every
        # opener below contains a change marker verbatim and a test pins it.
        "needs_change_marker": True,
        # AM-R1 applied to our own reasoning history: we do not invent having
        # been wrong any more than we invent having been anywhere. No open
        # thesis in the ledger, no confession.
        "needs_thesis": True,
        "openers": {
            # kelly: "What Would Prove This Wrong?" is her pinned franchise, so
            # the confession is her own method applied to herself — the single
            # highest-value warmth move on her desk, not a weakness.
            "kelly": ("i was wrong about this one",),
            # meagan: register is "human"; the okay-so opener is hers.
            "meagan": ("okay so I had this wrong",),
            # sophia: "measured" makes a confession read heavier, so it is
            # written short and plain rather than narrated.
            "sophia": ("I had this wrong",),
            # cici: "polite corrections" extends to correcting herself.
            "cici": ("I had this wrong earlier",),
        },
    },
    # -- MOVE 3 -------------------------------------------------------------
    # An unhedged verdict of ≤5 words, no throat-clearing, then the gift. The
    # warmth is CONFIDENCE EXTENDED TO THE READER: it credits the parent's
    # instinct and trusts the room to keep up. Evidence: MacroAlf →
    # @justintrimble, 65 likes / 8,082 views / 0.009 eng-per-view — "It's utter
    # magic. Most people don't realise it". Highest per-view short reaction in
    # the corpus, and the second clause splits the room into two groups and
    # invites self-sorting: that is the doorway (D1).
    "verdict_first": {
        "label": "verdict first",
        "does": ("open on an unhedged verdict of five words or fewer with no "
                 "throat clearing and no softener, then the gift"),
        "fits": ("analysis_claim", "chart_post", "data_post",
                 "question_to_the_room"),
        # A verdict about a PERSON rather than a claim is a dignity failure, and
        # an unhedged sentence is a stronger claim than a hedged one: the
        # epistemics law does not stop at the site boundary.
        "wrong_when": ("personal_setback", "personal_win", "sensitive_event"),
        "dial_floor": 1,
        "fuse": "standalone",
        "families_ok": None,
        "openers": {
            "kelly": ("that is the whole story",),
            "sophia": ("This is the part that matters",),
            "cici": ("Same read from this side",),
            # meagan is OUT: her codex requires the playful line THEN the useful
            # one, so a bare verdict is off-shape for her.
        },
    },
    # -- MOVE 4 -------------------------------------------------------------
    # Praise ONE NAMED DETAIL of the parent, then add. Never "great post". The
    # specificity is what makes praise read as sincere rather than as engagement
    # farming. Evidence: SirOfFinance thread, 14 likes / 10,535 views — praise
    # citing a concrete consequence rather than an adjective. Its mirror image
    # is the corpus's most repeated LOSER: "Smart man", "Will it come back?",
    # 1-3 likes each from accounts with real reach.
    "specific_credit": {
        "label": "specific credit",
        "does": ("credit one NAMED detail of the post (a variable, a chart, a "
                 "line), never an adjective and never the post as a whole, "
                 "then add exactly one thing"),
        "fits": ("chart_post", "resource_or_thread", "analysis_claim",
                 "data_post", "personal_win"),
        # Crediting a hot take reads as agreeing with a position we do not hold.
        "wrong_when": ("hot_take", "personal_setback", "sensitive_event"),
        "dial_floor": 1,
        "fuse": "conjunction",
        "families_ok": frozenset({
            "acknowledgment_plus_one", "second_order", "missing_variable",
            "cross_market_lead", "correction",
        }),
        # The {detail} slot is filled by a DETERMINISTIC extractor from the
        # parent text. EMPTY EXTRACTION MEANS THE MOVE IS UNAVAILABLE — there is
        # no generic fallback, because the generic fallback IS the losing
        # pattern. Note also that praise vocabulary carries no `_referents()`,
        # so `persona_label` would kill a credit-only draft: correct, and a
        # second reason the gift stays mandatory.
        "needs_detail": True,
        "openers": {
            "cici": ("Your point about {detail} is the one people skip. "
                     "Adding from the Asia session:",),
            "kelly": ("the {detail} line is the load bearing one.",),
            "meagan": ("the {detail} bit is the whole post honestly.",),
            "sophia": ("The {detail} point is the one that carries this.",),
        },
    },
    # -- MOVE 5 -------------------------------------------------------------
    # A shared frustration aimed at a PROCESS, a CROWD or an INSTITUTION —
    # never a person — in a dry register, landing soft rather than bitter.
    # Evidence: Convertbond → @DougKass, media critique closed playfully.
    # COUNTER-evidence, and the reason this move is fenced hardest: the
    # WSJ/SBF cluster (15 rows, 226-4,564 likes) is the same emotional energy
    # pointed at PEOPLE, and it is a standing brand exclusion (doctrine §4) —
    # the highest raw likes in the data, zero information, incompatible with
    # AM-R1 personas. THE TARGET is what discriminates the move from the
    # antipattern, so `_targets_a_person` enforces it at selection time.
    "wry_solidarity": {
        "label": "wry solidarity",
        "does": ("name a frustration shared with the reader, aimed at a "
                 "process, a crowd or an institution and never at a person; "
                 "dry, and landing soft rather than bitter"),
        "fits": ("wire_or_headline", "hot_take", "prediction", "analysis_claim"),
        "wrong_when": ("personal_setback", "personal_win", "sensitive_event"),
        "dial_floor": 2,
        "fuse": "standalone",
        "families_ok": frozenset({
            "reframe", "compression", "second_order", "missing_variable",
        }),
        "openers": {
            # kelly: "internet-native dry wit" is pinned register.
            "kelly": ("this gets rediscovered every cycle",),
            # sophia: capped and measured; no cynicism, no world-weariness.
            "sophia": ("We will be told this was obvious afterwards",),
            # meagan: WARM VARIANT ONLY, never ironic — her codex bans
            # "finance-bro irony" outright.
            "meagan": ("the frustrating part is how normal this looks",),
            # cici is OUT: "bright, worldly" is her pinned register and
            # world-weariness is off-register for her; cynicism about Asia also
            # drifts toward her own banned list ("exotic", "mysterious east").
        },
    },
    # -- MOVE 6 -------------------------------------------------------------
    # A real economic point delivered through one specific, physical, slightly
    # funny image instead of the abstract mechanism. Insight and delight in the
    # SAME sentence, never a joke clause plus an analysis clause. Evidence:
    # Convertbond → @AxelMerk, 13 likes / 3,927 views — "Americans have to pay
    # more for proper pasta now.": a complete tariff pass-through argument in
    # nine words with no mechanism vocabulary at all.
    "concrete_image": {
        "label": "concrete image",
        "does": ("deliver the point through one specific physical image "
                 "instead of the abstract mechanism; the image and the "
                 "insight are the same sentence, and it needs no setup"),
        "fits": ("analysis_claim", "data_post", "wire_or_headline", "chart_post"),
        # An image that trivialises a real loss, and a joke that needs a
        # sentence of setup (anti-exemplar 7: it scored zero).
        "wrong_when": ("personal_setback", "personal_win", "sensitive_event"),
        "dial_floor": 2,
        "fuse": "standalone",
        "families_ok": frozenset({"reframe", "compression", "micro_framework"}),
        "openers": {
            # cici: "worldly" carries this natively, and the zh gloss is her
            # most distinctive warm act. NOTE THE PARENTHESES: verified against
            # the shipped guard, a comma-appositive gloss ("结构性行情, a market
            # that...") is REJECTED by `vocab` as untranslated Chinese, while
            # the parenthetical form passes. Requires `voice_codex.zh`.
            "cici": ("The overnight version is simpler, 结构性行情 "
                     "(structural market):",),
            # meagan: "one playful line followed by one useful line" is her
            # pinned restraint, which is this move's law in her own words.
            "meagan": ("the human version of that number:",),
            # sophia: ≤1 elegant image is her codex cap (craft_metaphor,
            # max_per_7d 1), so her frame is plain and spends no metaphor.
            "sophia": ("Put plainly:",),
            # kelly: running metaphors are capped at 1/7d on her codex, so her
            # frame is the flat one.
            "kelly": ("the plain version:",),
        },
    },
    # -- MOVE 7 -------------------------------------------------------------
    # Hand the author the floor by naming precisely what we cannot resolve — as
    # a STATEMENT, not a question, in the default form. The warmth is deference.
    # EVIDENCE IS WEAK AND SAYS SO: the prior corpus is explicit that
    # OP-directed questions cluster in the zero-like pool, and the new corpus's
    # question rate is 16%. This move survives on CHARTER grounds (§3 makes the
    # author replying back the highest-value outcome, which likes do not
    # measure) with the like evidence against it, which is why the statement
    # form is the default and the question form is capped by the producer.
    "open_curiosity": {
        "label": "open curiosity",
        "does": ("name precisely what we cannot resolve from here, as a "
                 "statement and not a question, and leave the floor to the "
                 "person best placed to close it"),
        "fits": ("analysis_claim", "chart_post", "prediction",
                 "resource_or_thread"),
        "wrong_when": ("personal_setback", "personal_win", "sensitive_event"),
        "dial_floor": 2,
        "fuse": "standalone",
        "families_ok": frozenset({
            "author_question", "second_order", "conditional_prediction",
            "micro_framework",
        }),
        "openers": {
            # cici and meagan are the inviting registers.
            "cici": ("What I cannot see from this side:",),
            "meagan": ("the bit I keep turning over:",),
            # kelly: "pointed questions only when answerable" — so the
            # statement form names the answerability.
            "kelly": ("the open question, and it is answerable:",),
            # sophia: "sparing questions"; the statement form only.
            "sophia": ("The part I cannot settle from here:",),
        },
    },
    # -- MOVE 8 -------------------------------------------------------------
    # A short, first-name-free acknowledgement of a setback, then STOP. This is
    # the ONE move that may ship without an analytical gift, and the one move
    # that is explicitly NOT a growth move. Evidence: "Stay strong, Niall..." —
    # 7 likes / 2,677 views / 0.0026 eng-per-view, the FLOOR of the
    # distribution. It exists for relationship maintenance and for the register
    # anchor it provides, and the corpus is clear it does not drive growth.
    #
    # THE GATE ABOVE IT: `reply_critics.blocklist` hard-stops the whole item on
    # any DEFAULT_SENSITIVE_TERMS hit in draft OR parent, so this move can never
    # reach a bereavement, a disaster or a death. Its lawful surface is the
    # narrow band of PROFESSIONAL setback that is not on that list — a bad
    # quarter, a shipped bug, a project shelved, a hack.
    #
    # NEVER AT M2/M3 even after those modes ship: a sympathy reply is the one
    # shape that must always have a human in the loop.
    "quiet_sympathy": {
        "label": "quiet sympathy",
        "does": ("acknowledge a professional setback in eight words or fewer, "
                 "with no first name and no advice, and then stop"),
        "fits": ("personal_setback",),
        "wrong_when": tuple(s for s in PARENT_SHAPES if s != "personal_setback"),
        "dial_floor": 2,
        "fuse": "standalone",
        "families_ok": frozenset({"human_reaction"}),
        # Ships without an analytical gift and routes to the relationship tier.
        # `persona_label` carries ONE documented exemption for this, double
        # gated on `relationship_only` AND on the warmth id, so it cannot be
        # used to smuggle a referent-free growth reply through.
        "relationship_only": True,
        # NO FIRST NAME. The corpus register uses first names; we cannot,
        # because a name implies a relationship we have not established and
        # reads worse screenshotted. Enforced deterministically in `compose`
        # and again in the `fabrication` critic, for every draft.
        "no_first_name": True,
        "openers": {
            "meagan": ("that is a rough one. hope the rebuild is quick",),
            "cici": ("Sorry to see this. Hope the fix is a short one",),
            "sophia": ("That is a hard week. Hope it turns quickly",),
            # kelly is OUT: her terse dry register makes sympathy read as stiff
            # or sarcastic, which is the worst possible miss on this shape.
        },
    },
}

#: Moves whose opener carries a Chinese term, so they need ``voice_codex.zh``.
#: Derived, never hand-listed: a future opener that gains a zh term is caught.
_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")

#: The standalone-opener budget, in content units. The corpus's landing openers
#: are 2 ("Much appreciated:") and 3 ("Fair point but"); above 5 the opener stops
#: being a delivery register and becomes the bolted-on sentence W3 kills.
MAX_WARMTH_OPENER_UNITS = 5


def warmth_ids() -> list[str]:
    return list(WARMTH_MOVES.keys())


def rotate_warmth(recent: list[str] | tuple[str, ...] | None, *,
                  allowed: list[str] | None = None) -> str | None:
    """Least-recently-used warmth move, or None when nothing is admissible.

    Mirrors :func:`rotate_family` deliberately, and is a SEPARATE LRU on
    purpose: one rotation over the product of families and warmth moves would
    let a single pairing recur every 14 items while looking rotated. Two
    independent LRUs is what makes "concede-then-hold + missing variable" unable
    to become a signature.

    Returns None rather than falling back to the full register when *allowed* is
    empty: an empty pool here means every move was found WRONG for this parent
    or unavailable to this persona, and quietly ignoring that would ship the
    exact off-shape warmth the fitness rules exist to prevent. No warmth is
    always a legal answer — it is today's behaviour.

    RANKED ON THE LAST USE, NOT THE FIRST, and that is a deliberate difference
    from :func:`rotate_family`. "Least recently used" means the move whose MOST
    RECENT appearance is furthest back; ``list.index`` returns the FIRST
    appearance, so a move used at positions 0 and 19 of a twenty-item window
    outranks one used only at position 5 — it is "least recently FIRST used",
    which lets a move recur every other item while reading as rotated. Measured
    over two cycles that skew produced a 6-to-1 usage spread across a five-move
    pool, which is a tell. ``rotate_family`` carries the older reading; changing
    it is a separate call with its own regression surface.
    """
    pool = [w for w in (allowed if allowed is not None else warmth_ids())
            if w in WARMTH_MOVES]
    if not pool:
        return None
    recent_list = [str(w) for w in (recent or [])]
    last_use = {move: idx for idx, move in enumerate(recent_list)}
    def _key(move: str) -> tuple[int, int]:
        if move in last_use:
            return (1, last_use[move])
        return (0, pool.index(move))
    return sorted(pool, key=_key)[0]


# ---------------------------------------------------------------------------
# Parent-shape classification (the fitness gate's input)
# ---------------------------------------------------------------------------
#: Ordered most-specific-first. First match wins, and the ORDER IS THE RULING:
#: a post that is both a chart and a question is a chart post, because the
#: chart is what the reply has to earn its way past.
_SHAPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # A first-person professional setback. Deliberately NARROW: misreading an
    # analysis claim as a setback would make `quiet_sympathy` available where it
    # is grotesque, while the reverse merely makes it unavailable. Under-
    # detection is the safe direction, so this list is short and literal.
    ("personal_setback", re.compile(
        r"\b(?:we|i)\s+(?:got\s+)?(?:hacked|breached|laid\s+off|shut(?:ting)?\s+down|"
        r"shelv\w+|lost\s+the\s+\w+|had\s+to\s+(?:cut|pull|kill))\b"
        r"|\b(?:rough|brutal|bad|tough)\s+(?:quarter|year|month|launch|week\s+here)\b"
        r"|\bstepping\s+(?:down|away)\b|\bwe\s+are\s+winding\s+down\b"
        r"|\b(?:our|the)\s+(?:outage|incident|postmortem)\b", re.IGNORECASE)),
    ("personal_win", re.compile(
        r"\b(?:we|i)\s+(?:just\s+)?(?:shipped|launched|raised|closed\s+our|"
        r"crossed|hit)\b|\b(?:excited|thrilled|proud)\s+to\s+(?:announce|share)\b",
        re.IGNORECASE)),
    ("resource_or_thread", re.compile(
        r"\bthread\b|\U0001F9F5|\b1/\d{1,2}\b|\bfull\s+(?:writeup|write-up|note|piece)\b"
        r"|\blink\s+(?:below|in\s+(?:bio|replies))\b", re.IGNORECASE)),
    ("chart_post", re.compile(
        r"\b(?:this\s+)?chart\b|\bcharted\b|\bplotted\b|\bthe\s+(?:blue|red|orange)\s+line\b"
        r"|\by[-\s]?axis\b|\bsecond\s+panel\b", re.IGNORECASE)),
    ("correction_of_someone_else", re.compile(
        r"^\s*(?:actually|correction[:,])\b|\bthat\s+(?:is|'s)\s+(?:not\s+right|wrong)\b"
        r"|\bto\s+be\s+clear[,:]", re.IGNORECASE)),
    ("wire_or_headline", re.compile(
        r"\bbreaking\b|\bjust\s+in\b|\breuters\b|\bbloomberg\b|\bheadline[s]?:",
        re.IGNORECASE)),
    ("prediction", re.compile(
        r"\b(?:will|won't|wont)\s+(?:be|go|break|hold|get|reach|end)\b"
        r"|\bby\s+(?:year[-\s]end|q[1-4]|next\s+(?:year|quarter))\b"
        r"|\bi\s+expect\b|\bmy\s+(?:base\s+case|call)\b", re.IGNORECASE)),
    ("hot_take", re.compile(
        r"\b(?:nobody|everyone|no\s+one)\s+(?:is|has|wants|gets|understands)\b"
        r"|\b(?:insane|ridiculous|absurd|nonsense|delusional)\b"
        r"|\bthe\s+whole\s+thing\s+is\b|\bunpopular\s+opinion\b", re.IGNORECASE)),
)


def classify_parent(target: dict | str | None) -> str | None:
    """The parent post's shape, from :data:`PARENT_SHAPES`. None for no text.

    Deterministic and deliberately coarse. The classifier feeds a FITNESS gate,
    not a score, so its only job is to keep a move that is WRONG for the shape
    unavailable; a shape it reads conservatively costs at most one warmth move.

    ``sensitive_event`` is returned FIRST when any ``reply_critics``
    sensitive-event term appears, so no warmth move can ever be offered on one —
    belt and braces above ``blocklist``, which stops the whole item anyway.

    ``analysis_claim`` is the documented RESIDUAL: most fintwit posts are a
    claim about the market, and the moves that key on it are the low-risk ones.
    ``data_post`` is decided last, on figure density, because a claim carrying a
    number is still a claim.
    """
    if isinstance(target, dict):
        text = str(target.get("text") or "")
        if target.get("chart") or target.get("has_media"):
            # A declared chart outranks the prose classifier: the reply has to
            # earn its way past the chart whatever the caption says.
            declared_chart = True
        else:
            declared_chart = False
    else:
        text = str(target or "")
        declared_chart = False
    if not text.strip():
        return None

    low = text.lower()
    try:
        from engine.marketing import reply_critics as _rc  # noqa: PLC0415

        sensitive = tuple(_rc.DEFAULT_SENSITIVE_TERMS)
    except Exception as exc:  # noqa: BLE001
        # Unreadable list => assume the worst. A warmth move on a disaster is
        # not a risk this classifier is allowed to take on an import failure.
        log.warning("reply_drafter.classify_parent: sensitive terms unavailable (%s)", exc)
        return "sensitive_event"
    if any(term in low for term in sensitive):
        return "sensitive_event"

    if declared_chart:
        return "chart_post"
    for shape, pattern in _SHAPE_PATTERNS:
        if pattern.search(text):
            return shape
    if text.rstrip().endswith("?"):
        return "question_to_the_room"

    # A figure-dense post with no stance verb is a data drop, not a claim.
    try:
        from engine.marketing import reply_critics as _rc2  # noqa: PLC0415

        figures = len(_rc2.number_tokens(text))
    except Exception:  # noqa: BLE001
        figures = 0
    if figures >= 2 and not re.search(
            r"\b(?:i|we)\s+(?:think|read|reckon|suspect|argue)\b", low):
        return "data_post"
    return "analysis_claim"


# ---------------------------------------------------------------------------
# Warmth availability — derived from the LIVE persona spec, every call
# ---------------------------------------------------------------------------
def _reply_dial(account: str, root: Path | str | None = None) -> int:
    """The account's reply dial, read from ``voice_codex.dial_profile``.

    An account with NO codex (the flagship spec declares no ``dial_profile``,
    so ``expression_dial`` deliberately leaves it off the dial) resolves to 1,
    the evidence-desk dial. That is the conservative direction in both
    directions at once: it withholds every ``dial_floor: 2`` warmth move from an
    account whose register we cannot read, and it keeps the anti-cold critic
    (which fires only at dial >= 2) inert there.
    """
    try:
        from engine.marketing import expression_dial as _dial  # noqa: PLC0415

        codex = _dial.codex_for(str(account or ""), root=root)
        if codex is None:
            return 1
        return int(codex.dial("reply"))
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_drafter._reply_dial: %s for %r", exc, account)
        return 1


# WHY THERE IS NO `voice_codex.warmth_moves` ALLOW/DENY BLOCK READ HERE.
# The obvious way to make availability spec-driven is to let each persona spec
# name the warmth moves it grants. It is also a FENCE BREACH:
# `tests/test_marketing_personas.py::test_no_generation_module_reads_a_persona_spec`
# pins that the spec layer has exactly four readers, and `expression_dial` is
# the ONE generation-side seam that was adjudicated open (XG-W1) precisely so
# the copy layer calls the dial and never `personas`. This module therefore
# reaches the codex only THROUGH the dial — `_reply_dial` reads
# `voice_codex.dial_profile`, `_codex_zh` reads `voice_codex.zh`, and
# `_opener_clears_persona_guards` runs `expression_dial.violations`, which
# enforces `voice_codex.quirk_markers` and `voice_codex.banned` in full. That
# already makes the spec canonical for availability with no code change: a word
# added to a `banned` list, or a quirk marker switched dark, withdraws the
# offending opener the same night.
#
# An explicit per-move grant belongs on `expression_dial.CodexRules` (one new
# field, read by the sanctioned reader) whenever an operator wants one. Adding
# it here instead would put a fifth reader behind the fence for a copy law.


#: (account, fragment-key, "", root-key) → clean?  The guard sweep below runs
#: `banned_language` + `expression_dial.violations` + `am_r1_hits` per fragment,
#: which is cheap but not free, and the answer only changes when a persona spec
#: changes. `expression_dial.clear_cache()` is the documented way to invalidate
#: a codex; this cache is cleared alongside it by `clear_warmth_cache`.
#:
#: ONE CACHE FOR BOTH REGISTERS (openers and doorway tails), because there is one
#: guard sweep. A second cache in front of the same function is how a spec edit
#: comes to look like it landed on one register and not the other: the tail layer
#: shipped with exactly that bug for one revision — `clear_tail_cache()` dropped
#: the tail map while the sweep's own map still answered True, so a codex `banned`
#: word withdrew nothing.
_GUARD_OK_CACHE: dict[tuple[str, str, str, str], bool] = {}


def clear_warmth_cache() -> None:
    """Drop the per-opener guard cache (tests that write specs into a tmp root).

    Clears the TAIL cache too. Both caches key on a persona spec that
    ``expression_dial.clear_cache()`` invalidates in one call, and a caller that
    dropped only half of them would get a half-refreshed register — the shape
    that makes a spec edit look like it landed on the openers and not on the
    doorways.
    """
    _GUARD_OK_CACHE.clear()
    clear_tail_cache()


def _copy_clears_persona_guards(account: str, probe: str, cache_key: str,
                                root: Path | str | None = None) -> bool:
    """Does this fragment survive the persona's OWN three guards?

    This is the mechanism that makes the persona specs canonical rather than
    decorative: a word added to a codex ``banned`` list, a quirk marker switched
    dark, or a new AM-R1 detector removes the offending copy from the register
    the same night, with no code change here. The three guards are the same
    three the shipped copy has to clear downstream, so a fragment that trips one
    is not a style choice, it is a defect that would have cost a whole item at
    critic time.

    Shared by the warmth openers and the doorway tails so there is ONE guard
    sweep, not two that can drift: the tails were added later and a forked copy
    of this function is how the second register quietly stops being checked.
    """
    key = (str(account), str(cache_key), "", str(root or ""))
    cached = _GUARD_OK_CACHE.get(key)
    if cached is not None:
        return cached
    ok = True
    try:
        from engine.marketing import expression_dial as _dial  # noqa: PLC0415
        from engine.marketing.copywriter import banned_language  # noqa: PLC0415

        if banned_language(probe):
            ok = False
        elif _dial.am_r1_hits(probe):
            ok = False
        elif _dial.violations("", probe, account=str(account), kind="reply",
                              root=root, include_house_bans=False):
            ok = False
    except Exception as exc:  # noqa: BLE001
        # A guard we cannot run is not a guard that passed. Withhold the
        # fragment: losing one warmth move costs a plainer reply, shipping
        # unchecked persona copy costs the account.
        log.warning("reply_drafter: guard sweep unavailable for %r (%s)",
                    account, exc)
        ok = False
    _GUARD_OK_CACHE[key] = ok
    return ok


def _opener_clears_persona_guards(account: str, opener: str,
                                  root: Path | str | None = None) -> bool:
    """Does this warmth opener survive the persona's OWN guards?

    The ``{detail}`` slot is filled with a neutral placeholder before the sweep:
    a bare "{detail}" is not English and the register guards would judge the
    punctuation rather than the copy.
    """
    probe = str(opener or "").replace("{detail}", "breadth")
    return _copy_clears_persona_guards(account, probe, str(opener or ""), root)


def openers_for(account: str, move: str, root: Path | str | None = None) -> list[str]:
    """Every opener *account* may use for *move*, after the live guard sweep."""
    spec = WARMTH_MOVES.get(str(move)) or {}
    candidates = list((spec.get("openers") or {}).get(str(account)) or ())
    return [o for o in candidates if _opener_clears_persona_guards(account, o, root)]


def warmth_moves_for(
    account: str,
    *,
    parent_shape: str | None = None,
    family: str | None = None,
    root: Path | str | None = None,
    has_thesis: bool = False,
    has_detail: bool = False,
    tier: str | None = None,
) -> list[str]:
    """Warmth moves admissible for this account, parent and family.

    Every gate here is a real one, and every one of the codex-derived gates
    reaches the spec THROUGH ``expression_dial`` (see the fence note above):

      1. ``dial_floor`` against the account's codex reply dial — the mechanism
         that keeps the flagship an evidence desk;
      2. ``voice_codex.zh`` for a move whose opener carries a Chinese term;
      3. FITNESS: the parent shape must be in ``fits`` and out of
         ``wrong_when``. An unknown shape (no parent text) admits nothing —
         warmth is shape-conditioned by design, so an unclassifiable parent
         gets today's plain draft rather than a guess;
      4. ``families_ok`` against the chosen reasoning family;
      5. ``needs_thesis`` / ``needs_detail`` / ``relationship_only``
         preconditions, each of which FAILS CLOSED;
      6. at least one opener surviving the persona's own guards, which is where
         ``voice_codex.quirk_markers`` and ``voice_codex.banned`` bind.
    """
    shape = str(parent_shape) if parent_shape else None
    if shape == "sensitive_event":
        return []
    dial = _reply_dial(account, root)
    out: list[str] = []
    for move, spec in WARMTH_MOVES.items():
        if dial < int(spec.get("dial_floor") or 1):
            continue
        if shape is None or shape not in (spec.get("fits") or ()):
            continue
        if shape in (spec.get("wrong_when") or ()):
            continue
        fams = spec.get("families_ok")
        if fams is not None and family is not None and str(family) not in fams:
            continue
        if spec.get("needs_thesis") and not has_thesis:
            continue
        if spec.get("needs_detail") and not has_detail:
            continue
        if spec.get("relationship_only") and str(tier or "") != "relationship":
            continue
        openers = openers_for(account, move, root)
        if not openers:
            continue
        if any(_CJK_RE.search(o) for o in openers) and not _codex_zh(account, root):
            # A zh-carrying opener on a non-zh desk is a defect, not a language
            # choice (expression_dial says so at every dial, including 0).
            openers = [o for o in openers if not _CJK_RE.search(o)]
            if not openers:
                continue
        out.append(move)
    return out


def _codex_zh(account: str, root: Path | str | None = None) -> bool:
    try:
        from engine.marketing import expression_dial as _dial  # noqa: PLC0415

        codex = _dial.codex_for(str(account or ""), root=root)
        return bool(codex is not None and codex.zh)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# The {detail} extractor for `specific_credit`
# ---------------------------------------------------------------------------
#: Ordinal references to a chart or a paragraph, which read as a named detail.
_ORDINAL_DETAIL_RE = re.compile(
    r"\b(?:first|second|third|last|bottom|top)\s+"
    r"(?:chart|panel|line|paragraph|point|column|row)\b", re.IGNORECASE)
_QUOTED_RE = re.compile(r"[\"“]([^\"”]{4,40})[\"”]")


def extract_detail(parent_text: str) -> str:
    """One concrete noun phrase from the parent, or "" when there is none.

    Order: an ordinal chart/paragraph reference, then a quoted phrase, then a
    named mechanism token, then a cashtag. EMPTY IS A REAL ANSWER and the caller
    must treat it as "the move is unavailable" — the generic fallback ("great
    post", "smart man") is the corpus's single most repeated LOSER, so there is
    deliberately no fallback to fall back to.
    """
    text = str(parent_text or "")
    if not text.strip():
        return ""
    # MECHANISM FIRST, and the order is load-bearing rather than aesthetic: a
    # `specific_credit` opener is a full sentence, so its first sentence must
    # carry a concrete referent or it trips both W3 (bolted-on warmth) and
    # `persona_label`. A mechanism token and a cashtag ARE referents; "second
    # chart" and a quoted phrase are not, so they rank below.
    try:
        from engine.marketing import reply_critics as _rc  # noqa: PLC0415

        mechanisms = set(_rc._MECHANISM_TOKENS)
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_drafter.extract_detail: mechanism list unavailable (%s)", exc)
        mechanisms = set()
    for word in re.findall(r"[A-Za-z]+", text):
        if word.lower() in mechanisms:
            return word.lower()
    match = re.search(r"\$[A-Za-z][A-Za-z0-9.\-]{0,9}\b", text)
    if match:
        return match.group(0).upper()
    match = _ORDINAL_DETAIL_RE.search(text)
    if match:
        return match.group(0).lower()
    match = _QUOTED_RE.search(text)
    if match:
        return match.group(1).strip().lower()
    return ""


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _subject_of(ctx: dict) -> str:
    """A short noun phrase to hang the grip on."""
    subj = str(ctx.get("subject") or "").strip()
    if subj:
        return subj
    ticker = str(ctx.get("ticker") or "").strip()
    if ticker:
        return ticker.lstrip("$")
    return "the move"


def _lead_of(ctx: dict) -> str:
    """The mechanism this family points at (never a new number)."""
    return str(ctx.get("mechanism") or "credit").strip()


def _clean(text: str) -> str:
    """Strip the dash tells the shared guard bans, and collapse whitespace.

    Em/en dashes are a documented LLM tell and a hard ban in
    ``copywriter.banned_language``. Rewriting them here (rather than letting the
    guard reject) keeps the drafter honest without giving it a second word list.
    """
    text = text.replace("—", ", ").replace("–", "-").replace("―", "-")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


#: Family templates that open on their OWN canned affect line. When a warmth
#: move is applied, that line is REPLACED rather than stacked on top of: two
#: concessions in one reply is the theatre `concede_and_hold.wrong_when` warns
#: about, and "Agreed, with one addition." in front of a specific credit is the
#: same defect. Replacing it is also the upgrade the warmth build exists for —
#: these three canned lines are precisely the "analytical gift wearing one line
#: of affect" that the register audit named.
_FAMILY_CANNED_PREAMBLE: dict[str, str] = {
    "respectful_disagreement": "Observation holds. The mechanism is where I'd push back.\n\n",
    "acknowledgment_plus_one": "Agreed, with one addition.\n\n",
    "human_reaction": "okay, this one is actually interesting.\n\n",
    # Not affect, but the same collision: a warmth opener already ending on a
    # colon followed by "Short version:" is two colons and two frames.
    "compression": "Short version: ",
}

# ===========================================================================
# The doorway register — a POOL per family PER DESK, never one welded line
# ===========================================================================
#
# THE DEFECT THIS CLOSES, measured on the composer that shipped 2026-08-01.
# `compose` builds [warmth opener] + [gift] + [body/doorway]. The warmth register
# differentiated only the OPENER; the closing sentence was ONE FIXED STRING PER
# FAMILY, byte-identical across every persona, every warmth move and every
# thread. Four personas x every family x every lawful warmth move produced NINE
# distinct tails in total:
#
#   missing_variable        "The price move is the reaction. Credit is the test."   x33
#   second_order            "If that holds, the pressure shows up in credit ..."    x33
#   respectful_disagreement "That reads like credit, not semis."                    x33
#   human_reaction          "That is the part I'd watch."                           x33
#
# sophia, kelly, cici and meagan reply into OVERLAPPING fintwit audiences from
# accounts presented as different real women. A byte-identical second sentence
# across those accounts is the single most legible bot-farm signature available,
# and the drafter's own docstring says the deterministic path IS the product
# whenever `reply_voice` is muted. It is also the same welded-tail defect
# `copywriter.repeated_closer_violations` exists for one lane over (autopsy
# defect 6: 27% of one week's posts closing on one of nine sentences); the reply
# desk simply had no equivalent gate.
#
# WHY THE LANES ARE PER-ACCOUNT AND DISJOINT rather than one shared pool with a
# hashed pick. The requirement is that two desks replying to the SAME parent
# never draw the same tail. A shared pool cannot promise that: with five entries
# and four desks, a hash-mod pick collides on roughly one thread in five, and
# there is no fleet roster in this module to permute against (the drafter is
# handed one account at a time and `expression_dial` is the only spec seam it may
# use). Disjoint per-account lanes make the collision UNREACHABLE instead of
# unlikely, and they are also how the warmth `openers` table already works — the
# register copy lives beside the persona it belongs to, and a test pins the
# disjointness so a later edit cannot quietly merge two lanes.
#
# WHY THE COPY IS HERE AND NOT IN THE PERSONA SPECS. Same fence as the warmth
# openers, for the same reason: the specs are §5-FROZEN ("assemble, never
# invent") and `tests/test_marketing_personas.py::
# test_no_generation_module_reads_a_persona_spec` pins the spec layer's four
# adjudicated readers, which do not include this module. AVAILABILITY still comes
# from the live spec through `expression_dial` — `tails_for` runs every candidate
# through the persona's own `banned_language` + dial + AM-R1 sweep, so a word
# added to a codex `banned` list or a quirk marker switched dark withdraws the
# offending doorway the same night with NO code change here.
#
# WHY EVERY EMPLOYEE TAIL CARRIES A WARMTH MARKER and no flagship tail does.
# `reply_critics.warmth_register` W1 rejects a >=12-content-unit reply from a
# dial-2 desk that carries no human-register marker at all, and the common case
# is `warmth=None` (an unclassifiable parent, or a family the register cannot
# warm) — which is exactly when the tail is the ONLY differentiated copy in the
# draft. The pre-fix constants failed that test by construction: the very string
# `test_w1_kills_a_twelve_unit_cold_printout` uses as its cold-printout fixture
# is what `compose("missing_variable", ...)` returned. Putting a
# `warmth_markers`-visible phrase in every employee lane is the SUPPLY-SIDE
# mitigation this module's docstring already names, and it is register work
# rather than decoration: "the part that" is Sophia's measured register, "fair."
# and "actually" are Kelly's flat one, "worth saying / plainly / same read" is
# Cici's polite-correction register, "honestly / genuinely" is Meagan's. The
# `_default` lane is deliberately COLD: it serves the flagship and the founder,
# whose reply dial is 1, where W1 is inert and the doctrine's §5 register map
# lists "anything warm" in the Never column.
#
# WHY NOT EVERY TAIL IS A QUESTION. Doctrine §11.8 ranks the doorway forms and
# the question is the WEAKEST of the six (16% of the landing corpus; the highest
# per-view replies carry none). Only `author_question` — the family whose entire
# move is one precise question — closes on a question mark; a test pins that, so
# a later pool edit cannot turn the desk into an interrogation.
#
# SCOPE. This closes the welded TAIL. Families whose frame is a PREFIX
# (`compression`'s "Short version:", `correction`'s "One thing worth fixing in
# the thread:", `original_chart`'s "Charted it.") carry the same defect in the
# other position and are deliberately NOT touched here; they are absent from
# FAMILY_TAILS and a test pins that absence so the next build knows the gap is
# known rather than covered.

#: The lane a desk with no per-account copy falls to. One shared lane, so two
#: UNATTRIBUTED desks could collide on it — the live fleet is five named
#: accounts, four of which have their own lane and the fifth (founder) is the
#: only occupant of this one, and a test pins the five-way divergence.
TAIL_DEFAULT_LANE = "_default"

#: Neutral slot fillers for the guard sweep. Same compromise the openers make
#: with ``{detail}`` -> "breadth": a bare "{lead}" is not English and the
#: register guards would judge the braces rather than the copy.
_TAIL_PROBE_CTX: dict[str, str] = {"subject": "the tape", "mechanism": "breadth"}

#: family -> lane -> the doorway sentences that lane may close on.
#:
#: Slots: ``{lead}`` / ``{lead_cap}`` (the mechanism, from ``_lead_of``),
#: ``{subject}`` / ``{subject_cap}`` (from ``_subject_of``), and — for
#: ``callback`` only — ``{prior_clause}``, which renders to ": <the prior
#: position>" when the caller supplied one and to "." when it did not. That slot
#: exists because the callback tail is the one whose grammar CHANGES with its
#: input; writing two pools would have doubled the copy to express one comma.
#:
#: NO TAIL MAY CARRY A FIGURE. Grip and doorway introducing no numbers is what
#: keeps ``fact_discipline`` satisfiable by construction, and a test pins it.
FAMILY_TAILS: dict[str, dict[str, tuple[str, ...]]] = {
    # -- name the variable the thread has not priced -------------------------
    "missing_variable": {
        TAIL_DEFAULT_LANE: (
            "The price move is the reaction. {lead_cap} is the test.",
            "{lead_cap} is the variable this thread has not priced.",
            "The tape has a view on {subject}. It has not taken one on {lead}.",
        ),
        # sophia: story-led and measured, so the variable arrives as the half of
        # the story the thread has not told yet.
        "sophia": (
            "The move is the visible half. The part that decides it is {lead}.",
            "The harder part is that every version of this runs through {lead} first.",
            "{subject_cap} is what the thread is arguing about. {lead_cap} is what I keep watching.",
        ),
        # kelly: lowercase and clipped. Her codex bans every hedging softener, so
        # these state the gap flat rather than proposing it.
        "kelly": (
            "the move is the symptom. {lead} is the thing that decides it.",
            "nobody has priced {lead} yet. that is the part that matters.",
            "{subject} is downstream. {lead} is where i keep landing.",
        ),
        # cici: polite correction plus the session handoff, written WITHOUT the
        # `session_handoff` marker phrases so the tail spends no frame budget the
        # warmth opener may already need.
        "cici": (
            "Worth saying plainly: {lead} has not been priced here.",
            "The US session traded {subject}. The overnight tape trades {lead}, and that is the part that decides it.",
            "{lead_cap} is the piece this thread leaves out, and people skip it every time.",
        ),
        # meagan: conversational, human first.
        "meagan": (
            "Honestly the reaction is the easy part. {lead_cap} is what decides it.",
            "Nobody has put a price on {lead} yet and that is the thing that matters.",
            "The bit I keep coming back to is {lead}, not {subject}.",
        ),
    },
    # -- grant the claim, derive what it forces next -------------------------
    "second_order": {
        TAIL_DEFAULT_LANE: (
            "If that holds, the pressure shows up in {lead} before it shows up in {subject}.",
            "Grant it, and the next thing that has to move is {lead}.",
            "Take that as given and {lead} carries the consequence, not {subject}.",
        ),
        "sophia": (
            "Agreed on the premise, and it lands on {lead} before it lands on {subject}.",
            "The harder part is what it forces next, which is {lead}.",
            "Accept that and {subject} stops being the interesting bit. The part that moves is {lead}.",
        ),
        "kelly": (
            "fair. then {lead} has to give, not {subject}.",
            "if that is right, {lead} moves next. that is the part that is testable.",
            "the consequence lands in {lead} first. {subject} is where i keep looking second.",
        ),
        "cici": (
            "Agreed, and the follow-on sits in {lead} rather than in {subject}.",
            "Granting that, {lead} tends to move before the US open. That is the part that gets skipped.",
            "If the claim holds, {lead} is the thing that has to move next.",
        ),
        "meagan": (
            "If that is right, the thing that moves next is {lead}, not {subject}.",
            "Run it forward one step and it genuinely lands on {lead}.",
            "Grant the point and honestly {lead} is what has to move next.",
        ),
    },
    # -- grant the observation, dispute the mechanism ------------------------
    "respectful_disagreement": {
        TAIL_DEFAULT_LANE: (
            "That reads like {lead}, not {subject}.",
            "The observation stands. The mechanism looks like {lead}.",
            "Same facts, different driver: {lead} rather than {subject}.",
        ),
        "sophia": (
            "The observation is right. The part that reads differently is the step to {subject}.",
            "Fair, and the cause looks more like {lead} than {subject}.",
            "I keep landing on {lead} as the driver rather than {subject}.",
        ),
        "kelly": (
            "no argument on the facts. the mechanism actually looks like {lead}.",
            "same tape, different cause. the part that i would push on is {lead}, not {subject}.",
            "agreed on what happened. the why looks like {lead}, not {subject}.",
        ),
        "cici": (
            "Agreed on what happened. Less sure that {subject} is what caused it.",
            "Small correction on the mechanism: from this side it looks different, closer to {lead}.",
            "The observation holds. The part that I would move is the cause, to {lead}.",
        ),
        "meagan": (
            "The facts are fine. Honestly it is the step from {lead} to {subject} I would push on.",
            "Right on what happened, less right on why. This actually looks like {lead}.",
            "The thing that does not follow for me is {lead} to {subject}.",
        ),
    },
    # -- state a falsifiable if/then with a level ----------------------------
    # D2 in the doorway ranking, and X-LEGAL in plain terms (charter §2
    # amendment 4). The #3821 operator ruling that banned falsifier language is
    # SITE surfaces only; §11.8 says in as many words that a builder pattern
    # matching on it must not scrub D2 off the reply desk. What is avoided here
    # is the JARGON ("falsifier", "refuted"), never the form.
    "conditional_prediction": {
        TAIL_DEFAULT_LANE: (
            "If {lead} keeps going the same direction while {subject} stays put, "
            "the two are arguing and one of them is wrong.",
            "If {lead} turns and {subject} does not follow, this read does not hold.",
            "The pair is the test: {lead} and {subject} cannot both be right for long.",
        ),
        "sophia": (
            "The condition is simple. {lead_cap} and {subject} cannot hold this "
            "together, and the harder part is which one gives.",
            "If {lead} keeps drifting while {subject} holds, I read one of the two as wrong.",
            "Either {lead} comes back toward {subject}, or the link between them is "
            "the part that was never there.",
        ),
        "kelly": (
            "the test: {lead} keeps going and {subject} does not follow. then plainly "
            "the link is not there.",
            "one of these two is wrong. i keep watching {lead} for the answer.",
            "the clean test is {lead} moving while {subject} sits still. that is the "
            "part that settles it.",
        ),
        "cici": (
            "The condition to watch: {lead} moving while {subject} stays where it is. "
            "That is the part that decides it.",
            "If the overnight session takes {lead} further and {subject} holds, this "
            "read looks different by the open.",
            "Either {lead} comes back toward {subject}, or the link is not real. "
            "Worth saying that plainly.",
        ),
        "meagan": (
            "The clean test is {lead} moving again while {subject} sits still. "
            "Honestly that settles it.",
            "If {lead} keeps going and {subject} never reacts, I had this wrong.",
            "These two cannot both be right. The thing that breaks first says which.",
        ),
    },
    # -- a plain reaction, then one useful sentence --------------------------
    "human_reaction": {
        TAIL_DEFAULT_LANE: (
            "That is the part I'd watch.",
            "The useful part here is {lead}.",
            "Worth watching {lead} and {subject} together rather than separately.",
        ),
        "sophia": (
            "That is the detail I keep coming back to.",
            "The interesting part is not the move. Honestly it is what {lead} does next.",
            "I keep turning over the {lead} side of this.",
        ),
        "kelly": (
            "that is the bit i would watch.",
            "the useful part of this is {lead}. actually the only useful part.",
            "noted. {lead} is what i am watching.",
        ),
        "cici": (
            "That is the line I keep for the next session.",
            "Genuinely useful, and {lead} is the piece I carry forward.",
            "The part that stays with me is {lead}.",
        ),
        "meagan": (
            "Honestly the useful part here is {lead}.",
            "That is the thing that keeps nagging at me: {lead}.",
            "The part that I would actually act on is {lead}.",
        ),
    },
    # -- change what the move is about ---------------------------------------
    "reframe": {
        TAIL_DEFAULT_LANE: (
            "Worth reading this as a {lead} story rather than a {subject} story.",
            "This is less about {subject} than it is about {lead}.",
            "Change the label from {subject} to {lead} and it makes more sense.",
        ),
        "sophia": (
            "The harder part is that this is a {lead} story showing up in {subject}.",
            "The headline says {subject}. The story I read underneath is {lead}.",
            "Same event, different title. The part that carries it is {lead}.",
        ),
        "kelly": (
            "file this under {lead}, not {subject}. that is the part that changes.",
            "it looks like a {subject} move. it is actually a {lead} move.",
            "swap the label. plainly {lead} is doing the work here.",
        ),
        "cici": (
            "From this side it looks different: a {lead} story wearing a {subject} headline.",
            "Reframed for the next session, this belongs to {lead}. Worth saying that plainly.",
            "The cleaner label is {lead}, with {subject} as the part that shows.",
        ),
        "meagan": (
            "This honestly reads more like {lead} than {subject}.",
            "Relabel it. The thing that is actually moving is {lead}.",
            "It is a {lead} story. {subject_cap} is genuinely just where it showed up.",
        ),
    },
    # -- point at the market that moved first --------------------------------
    "cross_market_lead": {
        TAIL_DEFAULT_LANE: (
            "{lead_cap} moved first. {subject_cap} is catching up.",
            "The lead came from {lead}. {subject_cap} followed.",
            "{subject_cap} is the echo here. {lead_cap} is the source.",
        ),
        "sophia": (
            "{lead_cap} wrote this first and {subject} is reading it back, which is "
            "the part that matters.",
            "The move started in {lead} and reached {subject} late. That is the harder part to price.",
            "Order of events matters here, and I keep it as {lead} then {subject}.",
        ),
        "kelly": (
            "{lead} went first. {subject} is late. that is the whole story.",
            "the lead came out of {lead}, not {subject}. that is the part that is testable.",
            "check {lead} before {subject}. plainly that is the order.",
        ),
        "cici": (
            "{lead_cap} had already moved before the US open. {subject_cap} caught up "
            "after, and that is the part that repeats.",
            "From this side {lead} led and {subject} followed by a session. Same read overnight.",
            "The overnight tape had this in {lead} first. Genuinely worth checking that order.",
        ),
        "meagan": (
            "{lead_cap} got there first and {subject} is honestly only now catching on.",
            "The move was in {lead} before it was in {subject}. That is the thing that keeps repeating.",
            "{subject_cap} is following {lead} here. The part that surprises me is how long it takes.",
        ),
    },
    # -- one precise question inside their expertise -------------------------
    # THE ONE FAMILY THAT MAY CLOSE ON A QUESTION MARK (§11.8, D6: "weak,
    # capped"). The rolling caps (<=20% of an account's replies ending in a
    # question, <=2 author-directed per account per 7 days) live at SELECTION
    # time in `reply_producer`, because a critic sees one draft and cannot
    # express a rolling week.
    "author_question": {
        TAIL_DEFAULT_LANE: (
            "Does your read on {subject} survive if {lead} keeps moving against it?",
            "Where does {lead} sit in your version of this?",
            "What would {lead} have to do for you to drop the {subject} read?",
        ),
        "sophia": (
            "The part that I cannot settle is {lead}. Does it change your read on {subject}?",
            "I keep coming back to {lead} here. How much of the {subject} view rests on it?",
            "Genuinely asking: what is the {lead} print that would move you off this?",
        ),
        "kelly": (
            "actually curious: what does {lead} have to do before you drop the {subject} read?",
            "the part that i cannot settle is {lead}. where does it fit in your version?",
            "i keep looking for this one: what would prove this wrong on the {lead} side?",
        ),
        "cici": (
            "Genuinely curious about the {lead} side. Does your {subject} read hold if "
            "it moves overnight?",
            "The part that I keep re-checking is {lead}. What would you want to see from it first?",
            "Same read from this side on {subject}. Where does {lead} fit in your version?",
        ),
        "meagan": (
            "Honestly the {lead} side is what I cannot place. What would it have to do "
            "to change your mind on {subject}?",
            "The thing that I keep re-reading is {lead}. Where does it land in your read?",
            "Actually curious: is {lead} in your version of this, or is it all {subject}?",
        ),
    },
    # -- connect to a prior public position of ours --------------------------
    "callback": {
        TAIL_DEFAULT_LANE: (
            "Same condition we flagged before{prior_clause}",
            "This is the same setup we wrote up earlier{prior_clause}",
            "We have had this one on the list for a while{prior_clause}",
        ),
        "sophia": (
            "The condition we described has not changed, and I keep it on the list{prior_clause}",
            "Same shape as the read we ran before. That is the part that interests me{prior_clause}",
            "This is the same thread we picked up earlier. Genuinely the same condition{prior_clause}",
        ),
        "kelly": (
            "we had this one flagged already. actually the same condition{prior_clause}",
            "same setup, same condition as before. that is the part that repeats{prior_clause}",
            "this is the one i keep coming back to{prior_clause}",
        ),
        "cici": (
            "We flagged this same condition in an earlier session. Same read{prior_clause}",
            "The read from before still applies. Worth saying that plainly{prior_clause}",
            "Same condition carried over from earlier, and I keep it open{prior_clause}",
        ),
        "meagan": (
            "This is honestly the one we kept talking about{prior_clause}",
            "Same condition we flagged, and it is genuinely still doing the same thing{prior_clause}",
            "The thing that keeps coming back is this exact setup{prior_clause}",
        ),
    },
}

def clear_tail_cache() -> None:
    """Drop the guard-sweep cache (tests that write specs into a tmp root).

    The SAME map ``clear_warmth_cache`` drops, because the openers and the tails
    run one sweep: see the WHY on :data:`_GUARD_OK_CACHE` for the one-revision
    bug that a second, tail-only cache produced.
    """
    _GUARD_OK_CACHE.clear()


def tail_lane(account: str) -> str:
    """The lane *account* draws its doorways from.

    A desk with no lane of its own falls to :data:`TAIL_DEFAULT_LANE`, which is
    a REAL answer rather than a fallback: the flagship and the founder are
    evidence desks whose register map lists "anything warm" in the Never column,
    and the nine pseudonymous D13 specs carry no codex to fit copy to at all.
    """
    account = str(account or "")
    for lanes in FAMILY_TAILS.values():
        if account in lanes:
            return account
    return TAIL_DEFAULT_LANE


#: "a the tape story", "the the curve side". A slot value MAY carry its own
#: determiner ("the tape", "the curve", "the move" — the subject fallback itself
#: is one), and a template that reads naturally before a bare noun ("a credit
#: story rather than a capex story") then doubles the article.
#:
#: THIS IS NOT A DEFECT THE TAIL BUILD INTRODUCED — it fires on the two lines the
#: shipped composer already used, `reframe`'s "Worth reading this as a {lead}
#: story rather than a {subject} story" and `author_question`'s "...drop the
#: {subject} read?" — which is why the fix belongs at the RENDER layer and not in
#: thirteen hand-edited templates: the next template author gets it for free, and
#: the live lines are healed in the same change.
#:
#: DELIBERATELY CASE-SENSITIVE ON THE SECOND ARTICLE. Under IGNORECASE this eats
#: "the A-share market" (`\bA\b` matches), which is live China-desk vocabulary. A
#: slot value is lowercase, so requiring a lowercase second article costs nothing
#: and closes that hole; a test pins the A-share case.
_ARTICLE_COLLISION_RE = re.compile(r"\b([Aa]n?|[Tt]he)\s+(an?|the)\b")


def _fix_article_collision(text: str) -> str:
    """Drop a template's article when the slot brought its own.

    The SLOT wins: it carries the fact ("the tape"), the template's article is
    scaffolding. Sentence-initial capitalisation is carried across so "The the
    tape" becomes "The tape" and not "the tape".
    """
    def _sub(match: re.Match[str]) -> str:
        kept = match.group(2)
        if match.group(1)[:1].isupper():
            kept = kept[:1].upper() + kept[1:]
        return kept
    return _ARTICLE_COLLISION_RE.sub(_sub, str(text or ""))


def render_tail(template: str, ctx: dict | None = None) -> str:
    """Fill a tail template's slots from *ctx*.

    ``{prior_clause}`` is the one grammar-changing slot: ": <prior>" when the
    caller carries a prior position, "." when it does not. It exists so the
    ``callback`` lane needs one pool instead of two.
    """
    ctx = dict(ctx or {})
    subject = _subject_of(ctx)
    lead = _lead_of(ctx)
    prior = str(ctx.get("callback") or "").strip()
    return _fix_article_collision(str(template or "").format(
        lead=lead, lead_cap=lead.capitalize(),
        subject=subject, subject_cap=subject.capitalize(),
        prior_clause=(f": {prior}" if prior else "."),
    ))


def tails_for(account: str, family: str,
              root: Path | str | None = None) -> list[str]:
    """Every doorway *account* may close *family* on, after the live guard sweep.

    The sweep is the same one ``openers_for`` runs, so the persona specs stay
    canonical for the doorways exactly as they are for the warmth openers: a word
    added to a codex ``banned`` list, or a quirk marker switched dark, withdraws
    the offending tail the same night with no code change here.

    AN EMPTY LIST IS A REAL ANSWER and the composer treats it as "close on
    nothing". The tempting alternative — ship the unswept lane so the reply keeps
    its doorway — was written first and is WRONG: it puts copy the persona's own
    guard just rejected in front of a hostile audience under a real woman's name,
    which is strictly worse than the welded constant this build replaced. A
    missing doorway costs a plainer reply and the downstream critics still judge
    what ships; a banned doorway costs the account.

    The two-step fallback is deliberate. A ban that wipes ONE desk's lane (a word
    on that codex's ``banned`` list) still leaves the neutral ``_default`` lane,
    which is swept against THIS account before it is offered — so the usual
    outcome is a plainer close, not none. Only a ban that wipes both is a build
    defect in the copy, and it says so as a GitHub annotation (bare line-start
    print: a logger prefix would push "::" off column zero and Actions would
    silently drop the annotation — house law).
    """
    family = _TAIL_FAMILY_ALIAS.get(str(family), str(family))
    lanes = FAMILY_TAILS.get(str(family)) or {}
    if not lanes:
        return []

    def _swept(pool: tuple[str, ...] | list[str]) -> list[str]:
        return [tail for tail in pool
                if _copy_clears_persona_guards(
                    account, render_tail(tail, _TAIL_PROBE_CTX),
                    f"tail::{family}::{tail}", root)]

    lane = tail_lane(account)
    clean = _swept(lanes.get(lane) or ())
    if clean:
        return clean
    if lane != TAIL_DEFAULT_LANE:
        clean = _swept(lanes.get(TAIL_DEFAULT_LANE) or ())
        if clean:
            return clean
    print(f"::warning title=reply_tail_pool_empty::every doorway in the "
          f"{family!r} pool was rejected by {account!r}'s own guards, including "
          f"the {TAIL_DEFAULT_LANE!r} lane — replies from this desk will close "
          f"on nothing until the copy in reply_drafter.FAMILY_TAILS is fixed",
          flush=True)
    return []


def _stable_index(*parts: str) -> int:
    """A process-stable integer from *parts*.

    NOT ``hash()``: PYTHONHASHSEED randomises string hashing per interpreter, so
    a selector built on it would draw a different doorway on every nightly run
    and no rotation history could ever match what was actually enqueued. A test
    runs the selection in a separate interpreter under a hostile seed.
    """
    raw = "\x1f".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big")


def pick_from_pool(pool: list[str] | tuple[str, ...], *,
                   key_parts: tuple[str, ...] | list[str],
                   recent: list[str] | tuple[str, ...] | None = None) -> str:
    """One entry from *pool* by stable hash plus least-recently-used rotation.

    EXTRACTED FROM :func:`select_tail` SO THE SHAPE LAYER CANNOT FORK IT
    (XG-W4b §A.2.2). ``reply_shape`` draws its fragment closers and addition
    heads with exactly these semantics; a second selector beside this one would
    be a second set of rotation rules to keep in step, and the tail build already
    paid for that class of mistake once with two caches in front of one guard
    sweep.

    TWO AXES, and both are needed. The HASH of *key_parts* makes the pick
    deterministic — the same desk on the same parent draws the same entry, so a
    draft can be reproduced and an operator edit is not fighting a coin flip —
    and it diverges across parents, which is what stops one desk wearing one
    sentence all week. The ROTATION over *recent* is what the hash cannot
    promise: two parents can land on the same lane entry, and a desk that closes
    three nights running on the same line has welded its own tail without any
    help from its siblings.
    """
    pool = list(pool or [])
    if not pool:
        return ""
    start = _stable_index(*[str(p) for p in key_parts]) % len(pool)
    order = [pool[(start + i) % len(pool)] for i in range(len(pool))]
    window = [str(t) for t in (recent or [])]
    for entry in order:
        if entry not in window:
            return entry
    # Window wider than the lane: degrade to least-recently-used rather than
    # raising or blanking the doorway. A saturated window is a rotation input
    # problem, never a reason to ship a reply with no close.
    #
    # LAST occurrence, not first. `recent` is oldest-first and may repeat, so the
    # least-recently-used entry is the one whose MOST RECENT use is furthest
    # back: on [t1, t0, t1] the answer is t0, while `recent.index` — the idiom
    # `rotate_family` and `rotate_warmth` use — returns t1, the one used a moment
    # ago. Those two are left alone here (their windows are read straight off the
    # queue and rarely repeat inside one), but the difference is real and a test
    # pins this side of it.
    last_use = {entry: i for i, entry in enumerate(window)}
    return min(order, key=lambda entry: last_use.get(entry, -1))


def select_tail(account: str, family: str, *, thread_id: str = "",
                recent_tails: list[str] | tuple[str, ...] | None = None,
                root: Path | str | None = None) -> str:
    """One doorway template for this (account, family, thread). "" when none.

    Cross-DESK divergence is not enforced here at all: it is a property of the
    lanes being disjoint (see the WHY above), which is why it holds for every
    thread rather than for most of them. The hash-plus-rotation mechanics live in
    :func:`pick_from_pool`, which the shape layer shares.
    """
    return pick_from_pool(
        tails_for(account, family, root),
        key_parts=(str(account), str(family), str(thread_id)),
        recent=recent_tails,
    )


#: Tokens that keep their capital when a conjunction-fused opener runs into the
#: gift. Everything with an internal capital, a leading ``$`` or a leading digit
#: is detected structurally; this list is for ordinary Capitalised proper nouns
#: our own fact builders emit. UNDER-DECAPPING IS THE SAFE DIRECTION: a stray
#: capital mid-sentence reads as a typo, lowercasing a name changes a fact.
_PROPER_NOUN_EXEMPT: frozenset[str] = frozenset({
    "fed", "powell", "treasury", "treasuries", "china", "japan", "europe",
    "germany", "britain", "america", "americans", "brent", "bitcoin", "ether",
    "nasdaq", "russell", "dow", "gold", "opec", "ecb", "boj", "pboc", "boe",
    "washington", "beijing", "tokyo", "london", "wall", "street", "congress",
    "trump", "yellen", "lagarde", "ueda", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday", "january", "february", "march",
    "april", "may", "june", "july", "august", "september", "october",
    "november", "december",
})

_SENTENCE_TERMINAL = (".", "!", "?")


def _decap(text: str) -> str:
    """Lowercase the first character, unless the first token is a proper noun.

    Only reached for a ``fuse: "conjunction"`` opener that ends mid-clause, so
    the gift is continuing a sentence and its capital is wrong. Getting this
    wrong ships "fair, and the harder part is that nVIDIA..." — hence the
    structural tests before the word list.
    """
    body = str(text or "")
    if not body:
        return body
    first = re.split(r"\s+", body.strip(), maxsplit=1)[0]
    bare = first.strip("\"'“”(),.:;")
    if not bare or not bare[0].isalpha():
        return body            # $NVDA, 0.9%, "quoted"
    if bare.isupper() or any(c.isupper() for c in bare[1:]):
        return body            # NVDA, EURUSD, iPhone, S&P
    if bare.lower() in _PROPER_NOUN_EXEMPT:
        return body
    return body[0].lower() + body[1:]


def _opening_sentence_is_legal(opener: str) -> tuple[bool, str]:
    """Does this opener's FIRST SENTENCE survive W3?

    W3 (the anti-cold critic's bolted-on-warmth rule) kills a draft whose first
    sentence carries no concrete referent and runs over
    :data:`MAX_WARMTH_OPENER_UNITS` content units — "Great point, really
    appreciate you laying this out so clearly!" in front of the analysis. This
    is that exact test, run at BUILD time so the shape never reaches the queue.

    THE FIRST SENTENCE, NOT THE LAST. An opener may carry an internal full stop
    ("Holds for the US session. Overnight it looks different:") and still join
    the gift on a colon; the sentence W3 will judge is the one BEFORE that full
    stop, so checking only openers that END on terminal punctuation would have
    let a six-unit referent-free opening sentence through under a colon join.

    Returns ``(True, "")`` when the critic module cannot be imported: a thin
    runtime must not turn a budget check into a crash inside the composer, and
    the critic itself still runs downstream on whatever ships.
    """
    try:
        from engine.marketing import reply_critics as _rc  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_drafter: opener budget check unavailable (%s)", exc)
        return True, ""
    sentences = _rc._sentences(opener)
    if len(sentences) < 2 and not str(opener).rstrip().endswith(_SENTENCE_TERMINAL):
        # No sentence boundary inside the opener and none at its end: the opener
        # runs INTO the gift, so the sentence W3 judges carries the gift's own
        # referents and there is nothing to budget here.
        return True, ""
    head = sentences[0] if sentences else str(opener or "")
    units = _rc._content_units(head)
    if units <= MAX_WARMTH_OPENER_UNITS or _rc._referents(head):
        return True, ""
    return False, (
        f"warmth opener {head!r} stands as its own sentence at {units} content "
        f"units with no concrete referent (budget {MAX_WARMTH_OPENER_UNITS}) — "
        "that is the bolted-on shape, not a delivery register"
    )


def fuse_warmth(opener: str, body: str, *, fuse: str = "standalone") -> str:
    """Join a warmth opener to a composed body under the fusion law.

    THE LAW: warmth is fused into the clause that delivers the gift, never
    bolted on as a second sentence in front of one. Three join forms, decided by
    the opener's own trailing punctuation, so the copy declares its own shape
    rather than a flag doing it at a distance:

      * opener ends on ``:``   → the gift continues the clause; capital kept.
      * opener ends on ``.!?`` → a real sentence boundary; capital kept, and the
        opener must survive :func:`_opening_sentence_is_legal`.
      * opener ends on a word  → conjunction fuse for a ``conjunction`` move
        (the gift is decapitalised and runs straight on), and a COLON join for
        a ``standalone`` move. The colon is deliberate: appending a period would
        manufacture the referent-free opening sentence W3 exists to kill, which
        is how "i was wrong about this one." (6 units, no referent) would have
        been rejected by our own critic for obeying our own register.

    Raises ``ValueError`` on an over-budget sentence-terminating opener: a
    composer that silently ships the bolted-on shape is worse than a loud build
    failure, and every shipped opener is pinned by a test.
    """
    opener = _clean(opener)
    body = str(body or "").strip()
    if not opener:
        return body
    if not body:
        return opener
    ok, why = _opening_sentence_is_legal(opener)
    if not ok:
        raise ValueError(why)
    tail = opener[-1]
    if tail in _SENTENCE_TERMINAL:
        return f"{opener} {body}"
    if tail == ":":
        return f"{opener} {body}"
    if str(fuse) == "conjunction":
        return f"{opener} {_decap(body)}"
    return f"{opener}: {body}"


def compose(family: str, gift: str, ctx: dict | None = None, *,
            warmth: str | None = None, shape: str = "full",
            components: dict | None = None) -> str:
    """Build one draft from a family + a gift sentence, optionally warmed.

    ``shape`` is the THIRD rotation axis (XG-W4b §A). ``shape="full"`` — the
    default, and what every pre-existing caller gets — is BYTE-FOR-BYTE the
    composer that shipped: a parity test asserts ``compose(f, g, c, warmth=w)``
    equals ``compose(f, g, c, warmth=w, shape="full")`` over the whole family x
    warmth grid, so the shape build cannot regress the shipped path. Every other
    shape is rendered by ``reply_shape.render``, which builds from the GIFT and
    never runs the family frame below — that is how the canned preamble is
    stripped for the short forms, by construction rather than by a startswith()
    a new frame could slip past. ``reply_shape.render`` returns "" when the shape
    cannot be built inside budget, and so does this function: the caller falls to
    the next legal shape.

    The gift is used VERBATIM: it came from an own-feed fact builder, so its
    numbers are already whitelisted. Grip and doorway introduce no figures,
    which is what keeps ``fact_discipline`` satisfiable by construction.

    ``warmth`` names a :data:`WARMTH_MOVES` entry. With ``warmth=None`` this
    function is byte-for-byte what it was before the warmth build, which is why
    every pre-existing compose test still passes unchanged.

    THE DOORWAY IS DRAWN, NOT HARDCODED. ``ctx["thread_id"]`` (the parent/thread
    id) and ``ctx["recent_tails"]`` (this desk's recent doorways, oldest first)
    feed :func:`select_tail`; see the WHY beside :data:`FAMILY_TAILS` for what
    the welded per-family constant cost. An absent ``thread_id`` is legal and
    only means every parent shares one hash bucket, which the rotation still
    breaks up — but a caller that HAS a parent id and does not pass it has thrown
    away the cross-thread half of the divergence.
    """
    ctx = dict(ctx or {})
    if str(shape or "full") != "full":
        from engine.marketing import reply_shape as _rs  # noqa: PLC0415

        return _rs.render(str(shape), gift=gift, ctx=ctx, family=str(family),
                          warmth=warmth, account=str(ctx.get("account") or ""),
                          root=ctx.get("root"), components=components)
    gift = _clean(gift)
    subject = _subject_of(ctx)
    lead = _lead_of(ctx)
    stamp = str(ctx.get("as_of_stamp") or "").strip()
    drawn = render_tail(
        select_tail(str(ctx.get("account") or ""), str(family),
                    thread_id=str(ctx.get("thread_id") or ""),
                    recent_tails=list(ctx.get("recent_tails") or []),
                    root=ctx.get("root")),
        ctx,
    )
    # An empty draw is legal (``tails_for`` withheld the whole pool from this
    # desk) and means "close on nothing" — never a dangling blank paragraph.
    tail = f"\n\n{drawn}" if drawn else ""

    if family == "missing_variable":
        body = f"{gift}{tail}"
    elif family == "second_order":
        body = f"{gift}{tail}"
    elif family == "respectful_disagreement":
        body = (f"Observation holds. The mechanism is where I'd push back.\n\n"
                f"{gift}{tail}")
    elif family == "compression":
        body = f"Short version: {gift}"
    elif family == "conditional_prediction":
        body = f"{gift}{tail}"
    elif family == "human_reaction":
        body = f"okay, this one is actually interesting.\n\n{gift}{tail}"
    elif family == "reframe":
        body = f"{gift}{tail}"
    elif family == "cross_market_lead":
        body = f"{gift}{tail}"
    elif family == "correction":
        body = f"One thing worth fixing in the thread: {gift}"
    elif family == "micro_framework":
        body = (f"Two questions settle this.\n\n1. What is {lead} doing.\n"
                f"2. Whether {subject} agrees.\n\n{gift}")
    elif family == "author_question":
        body = f"{gift}{tail}"
    elif family == "original_chart":
        body = f"Charted it.\n\n{gift}"
    elif family == "acknowledgment_plus_one":
        body = f"Agreed, with one addition.\n\n{gift}"
    elif family == "callback":
        # The one tail whose GRAMMAR changes with its input; `{prior_clause}` in
        # the template carries the ": <prior>" / "." fork so the lane needs one
        # pool rather than two.
        body = f"{gift}{tail}"
    elif family == "dry_understatement":
        # No frame, by design: the move is "state the absurd consequence flatly,
        # no setup and no explanation", and a setup is exactly what a frame is.
        # The doorway comes from `human_reaction`'s pool via `_TAIL_FAMILY_ALIAS`.
        body = f"{gift}{tail}"
    else:
        body = gift

    move = WARMTH_MOVES.get(str(warmth)) if warmth else None
    if move is not None:
        opener = _resolve_opener(move, ctx)
        if opener:
            if move.get("relationship_only"):
                # The one move that ships WITHOUT an analytical gift. The
                # opener is the whole reply, and it is deliberately not a
                # growth reply: it exists for relationship maintenance and the
                # register anchor. `persona_label` will find no referent in it,
                # which is correct and is handled by that critic's single
                # documented exemption.
                body = opener
            else:
                canned = _FAMILY_CANNED_PREAMBLE.get(str(family))
                if canned and body.startswith(canned):
                    body = body[len(canned):]
                body = fuse_warmth(opener, body,
                                   fuse=str(move.get("fuse") or "standalone"))

    if stamp:
        body = f"{body}\n\n({stamp})"
    return _clean(body)


def _resolve_opener(move: dict, ctx: dict) -> str:
    """Pick this account's opener for *move* and fill any ``{detail}`` slot.

    Empty when the account has no opener for the move, or when the move needs a
    ``{detail}`` and the extractor found none. Both are REAL answers: an absent
    opener means the move is out of character for this desk, and an empty detail
    means the only remaining form of the credit is the generic praise that is
    the corpus's most repeated loser.
    """
    account = str(ctx.get("account") or "")
    root = ctx.get("root")
    openers = [o for o in (move.get("openers") or {}).get(account) or ()
               if _opener_clears_persona_guards(account, o, root)]
    if not openers:
        return ""
    opener = str(openers[0])
    if "{detail}" in opener:
        detail = str(ctx.get("detail") or "").strip()
        if not detail:
            return ""
        opener = opener.replace("{detail}", detail)
    return opener


# ---------------------------------------------------------------------------
# Chart attachment (reply artillery)
# ---------------------------------------------------------------------------
def attach_chart(as_of: str, chart_id: str, *, root: Path | str | None = None) -> dict | None:
    """Reference an ALREADY-RENDERED chart by path. Never renders here.

    Returns the queue item's ``chart`` block (``local_path`` + ``public_url``,
    charter §5) with an as-of stamp, or None when no such chart exists. Charts
    are EOD-only, so the stamp is mandatory: a nightly bar presented as live is
    the exact misrepresentation the charter calls out.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent
    rel = Path("data") / "marketing" / "outbox" / "media" / str(as_of) / f"{chart_id}.png"
    local = base / rel
    if not local.exists():
        return None
    public_url = None
    try:
        from engine.marketing import media_publish as _mp  # noqa: PLC0415

        public_url = _mp.public_url_for_key(_mp.chart_key(as_of, chart_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_drafter: cannot build public url for %r: %s", chart_id, exc)
    return {
        "local_path": str(rel),
        "public_url": public_url,
        "chart_id": chart_id,
        "as_of": as_of,
        "as_of_stamp": f"chart as of {as_of} close",
    }


def prerender_artillery(
    tickers: list[str],
    as_of: str,
    *,
    root: Path | str | None = None,
    closes_for: Any = None,
    limit: int = 12,
) -> list[dict]:
    """Pre-render charts for the day's trending tickers.

    Deliberately minimal: this is a small scheduled sweep that REUSES the
    existing render machinery (``chart_render`` + ``media_publish``) so a reply
    can attach a chart nobody else in the thread has. It renders nothing new
    conceptually and owns no chart style.

    ``closes_for(ticker) -> (dates, o, h, l, c, v) | None`` is injected so this
    function needs no data-layer import and stays testable in a stdlib lane.
    Imports of the render stack are lazy and are allowed to RAISE: a sweep that
    silently renders nothing is indistinguishable from a sweep that ran.
    """
    if not tickers:
        return []
    if closes_for is None:
        raise ValueError(
            "prerender_artillery needs a closes_for(ticker) callable — a sweep "
            "that silently renders nothing is indistinguishable from one that ran"
        )
    from engine.marketing import chart_render as _cr  # noqa: PLC0415
    from engine.marketing import media_publish as _mp  # noqa: PLC0415

    out: list[dict] = []
    for ticker in list(tickers)[:limit]:
        series = closes_for(ticker)
        if not series:
            continue
        # The documented contract is a (dates, o, h, l, c, v) tuple; a mapping
        # of the same fields is accepted too. Anything else is a caller bug and
        # says so, rather than rendering zero charts in silence.
        if isinstance(series, dict):
            kwargs = dict(series)
        elif isinstance(series, (tuple, list)) and len(series) == 6:
            dates, o, h, low, close, vol = series
            kwargs = {"dates": dates, "o": o, "h": h, "l": low, "c": close, "v": vol}
        else:
            raise TypeError(
                f"closes_for({ticker!r}) returned {type(series).__name__}; expected a "
                "(dates, o, h, l, c, v) tuple or an equivalent mapping"
            )
        try:
            svg = _cr.render_chart_v2(ticker=ticker, **kwargs)
            if not svg:
                continue
            chart_id = f"reply-{str(ticker).lstrip('$').lower()}"
            published = _mp.publish_card(svg, chart_id=chart_id, as_of=as_of, root=root)
            out.append({
                "ticker": ticker,
                "chart_id": chart_id,
                "local_path": published.get("media_png_path") or published.get("svg_path"),
                "public_url": published.get("media_url"),
                "as_of_stamp": f"chart as of {as_of} close",
            })
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_drafter: artillery render failed for %s: %s", ticker, exc)
    return out


# ---------------------------------------------------------------------------
# The drafter
# ---------------------------------------------------------------------------
def _pick_gift(facts: dict) -> tuple[str, list[str]]:
    """Highest-salience own-feed fact, plus the whitelist it licenses."""
    rows = [f for f in (facts or {}).get("facts") or [] if isinstance(f, dict) and f.get("text")]
    rows.sort(key=lambda f: -float(f.get("salience") or 0.0))
    whitelist = [str(n) for n in (facts or {}).get("numbers_whitelist") or []]
    return (str(rows[0]["text"]) if rows else ""), whitelist


#: Second-person pronouns. `wry_solidarity` may aim at a process, a crowd or an
#: institution and NEVER at a person, and the target is the only thing that
#: separates the move from the WSJ/SBF antipattern cluster (high likes, zero
#: information, a standing brand exclusion).
_SECOND_PERSON_RE = re.compile(r"\b(?:you|your|yours|you're|youre)\b", re.IGNORECASE)


def _targets_a_person(text: str, *, parent_author: str = "") -> bool:
    """True when the copy points at a HUMAN rather than a process or a crowd."""
    body = str(text or "")
    if _SECOND_PERSON_RE.search(body) or re.search(r"(?<![\w.])@[A-Za-z0-9_]{2,}", body):
        return True
    return bool(author_name_hits(body, parent_author))


def author_name_hits(text: str, parent_author: str) -> list[str]:
    """Parent-author display-name tokens appearing in *text*.

    A first name implies a relationship we have not established and reads worse
    screenshotted, so it is barred on EVERY draft and not only the sympathy one
    (the corpus's own sympathy register uses first names; we cannot borrow it).
    Tokens under three characters, and tokens that are ordinary English words or
    ticker-shaped, are ignored: a handle like "vol" or "Max" would otherwise ban
    half the vocabulary.
    """
    who = str(parent_author or "").strip().lstrip("@")
    if not who:
        return []
    body = str(text or "")
    hits: list[str] = []
    # CamelCase splits too. Fintwit handles are overwhelmingly "NorthmanTrader"
    # / "SirOfFinance" shaped, and a whole-handle match would never fire on the
    # first name inside them, which is the token a reply actually uses.
    parts: list[str] = []
    for token in re.split(r"[\s_\-.]+", who):
        parts.extend(re.findall(r"[A-Z][a-z]+|[a-z]+|[A-Z]+(?![a-z])", token) or [token])
    for token in parts:
        bare = re.sub(r"[^A-Za-z]", "", token)
        if len(bare) < 3 or bare.lower() in _COMMON_WORD_NAMES:
            continue
        if re.search(rf"(?<!\w){re.escape(bare)}(?!\w)", body, re.IGNORECASE):
            hits.append(bare)
    return hits


#: Handles and display names that are also ordinary words. Matching these would
#: ban common vocabulary rather than a person's name.
_COMMON_WORD_NAMES: frozenset[str] = frozenset({
    "the", "and", "for", "vol", "max", "bond", "gold", "market", "macro",
    "trader", "capital", "research", "data", "chart", "value", "growth",
    "alpha", "beta", "index", "fund", "risk", "rate", "rates", "street",
    "cycle", "story", "read", "tape", "flow", "flows", "signal", "desk",
    "note", "notes", "trade", "trades", "quant", "edge", "book", "long",
    "short", "call", "put", "spread", "curve", "credit", "equity",
})


# ---------------------------------------------------------------------------
# The SHAPE axis seam (XG-W4b §A/§B)
# ---------------------------------------------------------------------------
#
# EVERY ONE OF THESE HELPERS IMPORTS `reply_shape` LAZILY AND DEGRADES TO TODAY'S
# BEHAVIOUR. `reply_shape` and `persona_model` are separate modules landing in
# separate lanes; a drafter that raises because an overlay is missing has turned
# a distribution upgrade into an outage on the one path that must never have one.
# Absent module, absent overlay, unreadable YAML — all of them resolve to
# `shape="full"`, `response_type=""` and `familiarity="stranger"`, which is byte
# for byte what the composer did before this build.

#: shape id -> does this shape carry a doorway sentence. Read by `draft_reply` to
#: decide whether the tail it drew is actually IN the copy. Mirrors
#: `reply_shape.REPLY_SHAPES[*]["doorway"]` and is resolved through it when the
#: module is importable; the literal is the degraded answer.
REPLY_SHAPE_DOORWAY: dict[str, bool] = {
    "one_line": False, "fragment_exchange": False, "addition": False,
    "compact_chain": False, "full": True,
}


def _familiarity_of(account: str, target: dict | None, relations_row: dict | None,
                    root: Path | str | None) -> str:
    """The §E relationship tier for this parent's author. "stranger" on anything.

    SHIPS INERT TODAY and that is the honest state, not a bug:
    ``data/marketing/personas/<id>/relations.jsonl`` is written only by the M1
    approval path and the desk is at M0 on every account, so every handle is a
    stranger until approvals accumulate. Built now because building it after the
    store fills means a month of replies written at the wrong register.
    """
    try:
        from engine.marketing import persona_model as _pm  # noqa: PLC0415

        handle = str((target or {}).get("author") or "")
        return str(_pm.familiarity(str(account or ""), handle,
                                   relations={handle: relations_row}
                                   if relations_row else None,
                                   root=root) or "stranger")
    except Exception as exc:  # noqa: BLE001
        log.debug("reply_drafter: familiarity unavailable for %r (%s)", account, exc)
        return "stranger"


def _day_slice(day_counts: dict | None, axis: str) -> dict[str, int]:
    """One axis's counts-so-far-today out of the caller's ``day_counts``.

    TWO AXES SHARE ONE PARAMETER because the frozen signature (§F.3) carries one
    ``day_counts``, and two draws reading one another's counts would make the
    deficit term meaningless — a desk that had drafted six ``analytical_addition``
    replies would look to the SHAPE draw like it had drafted six of a shape that
    does not exist, and the realised share would be computed off a denominator
    from the wrong universe.

    The nested form ``{"shape": {...}, "response_type": {...}}`` is canonical. A
    FLAT dict is accepted and read as the axis whose vocabulary its keys belong
    to, because that is what a caller written against the one-line contract will
    pass; a flat dict with keys from neither vocabulary is ignored rather than
    guessed at.
    """
    counts = dict(day_counts or {})
    sub = counts.get(axis)
    if isinstance(sub, dict):
        return {str(k): int(v or 0) for k, v in sub.items()}
    if any(isinstance(v, dict) for v in counts.values()):
        return {}                      # nested form, other axis only
    try:
        from engine.marketing import reply_shape as _rs  # noqa: PLC0415

        vocab = set(_rs.RESPONSE_TYPES if axis == "response_type" else _rs.SHAPE_IDS)
    except Exception:  # noqa: BLE001
        return {}
    flat = {str(k): int(v or 0) for k, v in counts.items() if not isinstance(v, dict)}
    return flat if flat and set(flat) <= vocab else {}


def _narrow_to_type(pool: list[str], response_type: str) -> list[str]:
    """*pool* restricted to the families this response type is made of."""
    try:
        from engine.marketing import reply_shape as _rs  # noqa: PLC0415

        fams = _rs.TYPE_FAMILIES.get(str(response_type))
    except Exception:  # noqa: BLE001
        return list(pool)
    if not fams:
        return list(pool)
    return [f for f in pool if f in fams]


def _choose_type(account: str, *, requested: str | None, allowed: list[str],
                 day_counts: dict[str, int] | None, thread_id: str, as_of: str,
                 cfg: dict | None, root: Path | str | None) -> dict[str, Any]:
    """The response-type draw, with its whole derivation, or an inert record."""
    try:
        from engine.marketing import reply_shape as _rs  # noqa: PLC0415

        if requested and requested in _rs.RESPONSE_TYPES:
            return {"value": requested, "roll": 0.0, "source": "requested",
                    "weights": {}, "deficits": {}, "legal": [requested],
                    "day_counts": dict(day_counts or {})}
        return _rs.choose_response_type(
            account, day_counts=_day_slice(day_counts, "response_type"),
            thread_id=thread_id,
            as_of=as_of, cfg=cfg, root=root, allowed=list(allowed))
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_drafter: response-type draw unavailable for %r: %s",
                    account, exc)
        return {"value": "", "roll": 0.0, "source": "unavailable",
                "weights": {}, "deficits": {}, "legal": [],
                "day_counts": dict(day_counts or {})}


def _compose_shaped(family: str, gift: str, ctx: dict, *, warmth: str | None,
                    account: str, requested: str | None, response_type: str,
                    parent_shape: str | None, day_counts: dict[str, int] | None,
                    familiarity: str, has_chain: bool, as_of: str,
                    root: Path | str | None,
                    avoid: set[str] | None = None) -> tuple[str, str, float, str, str]:
    """(text, shape, roll, warmth_dropped, shape_copy) for one family.

    THE FALLBACK WALK IS THE POINT. ``reply_shape.render`` returns "" whenever a
    shape cannot be built inside its budget — an over-long gift, a lane whose
    copy the persona's own guards rejected, a head that would leave the reply
    with no register marker for W1 to see. That is a REFUSAL, never a truncation,
    so the caller tries the next legal shape and ends on ``full``, which is
    always legal (``shapes_for`` gate 5) and always renders. A legal set that
    could come back empty would be a lane abstaining for a FORMATTING reason,
    which is worse than a mini-essay.

    ``avoid`` IS NOT AN OPTIMISATION, IT IS THE ALTERNATE GUARANTEE. The short
    shapes render the GIFT and drop the family frame entirely — that is what
    makes them short — so `compression` under `one_line` and `missing_variable`
    under `one_line` are the same sentence. §9.4's whole point is that a second
    draft is worth having only when it reasons differently, and two byte-identical
    alternates are three copies of one thought wearing three family labels. A
    candidate already drafted is therefore skipped, and the family falls to the
    next legal shape (ending at `full`, which always carries its frame and its
    doorway and so always differs). Caught by
    `test_alternates_are_different_families_not_paraphrases`, which went red the
    moment the shape layer landed.
    """
    try:
        from engine.marketing import reply_shape as _rs  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_drafter: reply_shape unavailable (%s); full only", exc)
        try:
            return compose(family, gift, ctx, warmth=warmth), "full", 0.0, "", ""
        except ValueError:
            return "", "full", 0.0, "", ""

    try:
        from engine.marketing import reply_critics as _rc  # noqa: PLC0415

        gift_units = _rc._content_units(gift)
    except Exception:  # noqa: BLE001
        gift_units = len(str(gift or "").split())

    pick = _rs.choose_shape(
        account, response_type=response_type, family=family,
        parent_shape=parent_shape, thread_id=str(ctx.get("thread_id") or ""),
        day_counts=_day_slice(day_counts, "shape"), has_chain=has_chain,
        gift_units=gift_units, as_of=as_of, tier=familiarity)
    roll = float(pick.get("roll") or 0.0)
    legal = list(pick.get("legal") or ["full"])
    drawn = str(pick.get("value") or "full")
    if requested and requested in _rs.REPLY_SHAPES:
        drawn, legal = requested, [requested] + [s for s in legal if s != requested]

    # Drawn first, then the rest of the legal set by descending pick weight, then
    # `full` as the residual. Ordering the fallbacks by weight rather than by
    # SHAPE_IDS position keeps a refused short form falling to the OTHER short
    # form before it falls to a mini-essay.
    weights = pick.get("deficits") or {}
    rest = sorted((s for s in legal if s != drawn),
                  key=lambda s: -float(weights.get(s, 0.0)))
    for shape in [drawn, *rest, "full"]:
        parts: dict[str, Any] = {}
        try:
            text = compose(family, gift, ctx, warmth=warmth, shape=shape,
                           components=parts)
        except ValueError as exc:
            # An over-budget opener is a BUILD defect, not a runtime condition:
            # report it loudly and let the caller retry without the warmth.
            log.warning("reply_drafter: warmth %r rejected at compose for %r: %s",
                        warmth, account, exc)
            return "", shape, roll, "", ""
        if text.strip() and text not in (avoid or set()):
            return (text, shape, roll, str(parts.get("warmth_dropped") or ""),
                    str(parts.get("shape_copy") or ""))
    return "", "full", roll, "", ""


def draft_reply(
    *,
    account: str,
    target: dict,
    facts: dict,
    family: str | None = None,
    recent_families: list[str] | None = None,
    warmth: str | None = None,
    recent_warmth: list[str] | None = None,
    recent_tails: list[str] | None = None,
    shape: str | None = None,
    response_type: str | None = None,
    recent_shapes: list[str] | None = None,
    day_counts: dict[str, int] | None = None,
    relations_row: dict | None = None,
    as_of: str = "",
    has_thesis: bool = False,
    tier: str | None = None,
    chart: dict | None = None,
    callback: str | None = None,
    cfg: dict | None = None,
    root: Path | str | None = None,
    n_alts: int = 2,
) -> dict[str, Any]:
    """Draft one reply plus genuinely different alternates.

    Returns {draft, alt_drafts, family, alt_families, warmth, alt_warmth,
             tail, alt_tails, parent_shape, numbers_whitelist, components,
             dial_violations}.

    The alternates come from DIFFERENT families, not from re-wording the
    primary: §9.4's whole point is that a second draft is worth having only when
    it reasons differently. An empty gift returns an empty draft rather than
    padding — Law 1 (value before activity) means abstention is a legal answer.

    ``warmth`` / ``recent_warmth`` drive the SECOND rotation axis. The warmth
    move is composed DETERMINISTICALLY, before ``reply_voice`` is ever
    consulted, so a muted model still produces a warm reply rather than a cold
    one — that is the whole difference between this build and a prompt tweak.
    ``recent_warmth`` is the account's last enqueued warmth values, oldest
    first; the caller (``reply_producer``) reads them off the queue exactly as
    it already reads ``recent_families``.

    ``shape`` / ``response_type`` / ``recent_shapes`` / ``day_counts`` drive the
    FOURTH axis (XG-W4b §A/§B). The response type is drawn first and NARROWS the
    family pool (``reply_shape.TYPE_FAMILIES``); the family LRU then picks inside
    that narrowing, so §13.7 anti-sameness is untouched. The shape is drawn
    second and decides what the copy LOOKS like — one committed sentence, two
    short clauses, an agreement plus the thing they missed, an arrow chain, or
    today's gift + grip + doorway. Both draws are deficit-weighted against
    ``day_counts`` (the day is the control loop) and rolled off a blake2b hash of
    (account, as_of, thread, family), so the pick is reproducible from the queue
    record and is not a cycle. ``as_of`` is what gives the roll a day dimension;
    omitting it is legal and only collapses every day into one hash bucket.

    ``tier`` HERE IS THE QUEUE TIER (growth / relationship / defensive), which is
    what ``warmth_moves_for`` gates ``quiet_sympathy`` on. It is NOT the §E
    relationship FAMILIARITY tier — that one is derived from ``relations_row``
    and is passed to ``reply_shape.choose_shape`` under its own name. The two are
    different words for different closed sets and mixing them would silently
    hand `stranger` to a gate expecting `relationship`.

    ``recent_tails`` is the THIRD rotation axis, threaded the same way and
    carrying the same kind of value: the doorway TEMPLATES this desk recently
    closed on, oldest first, as returned in ``tail`` / ``alt_tails``. Templates
    rather than rendered sentences because the rendering changes with the
    subject and the mechanism, so a history of finished copy could never match
    what the selector is choosing between. The primary and every alternate draw
    against the SAME window; they cannot collide with each other because the
    alternates are different FAMILIES and no template appears under two.
    """
    gift, whitelist = _pick_gift(facts)
    parent_shape = classify_parent(target)
    parent_author = str((target or {}).get("author") or "")
    detail = extract_detail(str((target or {}).get("text") or ""))

    if not gift.strip():
        # ABSTENTION STILL WINS. A warmth move may never manufacture a reply out
        # of nothing — that is the "pure reaction warmth" bucket, the one thing
        # the corpus is confident does not work. The single exception is the
        # relationship-tier sympathy move, which is not a growth reply at all
        # and is gated on the tier, the parent shape AND an available opener.
        sympathy = warmth_moves_for(
            account, parent_shape=parent_shape, family="human_reaction",
            root=root, has_thesis=has_thesis, has_detail=bool(detail), tier=tier,
        )
        sympathy = [m for m in sympathy
                    if WARMTH_MOVES[m].get("relationship_only")]
        if sympathy:
            move = sympathy[0]
            text = compose("human_reaction", "",
                           {"account": account, "root": root, "detail": detail},
                           warmth=move)
            if text.strip():
                return {
                    "draft": _clean(text), "alt_drafts": [],
                    "family": "human_reaction", "alt_families": [],
                    "warmth": move, "alt_warmth": [],
                    # The sympathy reply is the one draft with NO gift and no
                    # doorway (the opener is the whole reply), so it closes on
                    # nothing and reports nothing. Present-and-empty rather than
                    # absent: a caller that reads the field on every return path
                    # must not KeyError on the one abstention-shaped answer.
                    "tail": "", "alt_tails": [],
                    # `shapes_for` returns ["one_line"] for a relationship_only
                    # draft: the opener IS the reply, there is no gift to close
                    # on and no head to add to. Reported rather than blank so a
                    # caller reading `shape` on every return path gets a member
                    # of SHAPE_IDS and not "".
                    "shape": "one_line", "alt_shapes": [], "shape_copy": "",
                    "alt_shape_copy": [],
                    "response_type": "short_reaction",
                    "familiarity": _familiarity_of(account, target, relations_row, root),
                    "shape_roll": 0.0, "type_roll": 0.0,
                    "parent_shape": parent_shape,
                    "numbers_whitelist": whitelist,
                    "components": {
                        "gift": "", "family_move": FAMILIES["human_reaction"]["move"],
                        "trigger": FAMILIES["human_reaction"]["trigger"],
                        "warmth_move": WARMTH_MOVES[move]["does"],
                        "relationship_only": True, "chart": False,
                        "shape": "one_line", "response_type": "short_reaction",
                        "warmth_dropped": "",
                        "voice_mode": "off",
                    },
                    "dial_violations": [],
                    "voice": {"text": _clean(text), "mode": "off",
                              "provider": None, "violations": []},
                }
        return {
            "draft": "", "alt_drafts": [], "family": None, "alt_families": [],
            "warmth": None, "alt_warmth": [], "tail": "", "alt_tails": [],
            "shape": "", "alt_shapes": [], "shape_copy": "",
            "alt_shape_copy": [], "response_type": "",
            "familiarity": "", "shape_roll": 0.0, "type_roll": 0.0,
            "parent_shape": parent_shape,
            "numbers_whitelist": whitelist, "components": {"abstained": "no own-feed fact"},
            "dial_violations": [],
        }

    # THE DIAL GATE, and the moment `FAMILIES.dial_floor` stops being decorative.
    # Every FAMILIES entry has declared `dial_floor` since the register was
    # written and NOTHING read it (the module's own WHY beside WARMTH_MOVES says
    # so, and `tests/test_marketing_reply_warmth.py::TestDialFloorIsWired` pins
    # the asymmetry and asks whoever wires it to come here and say so — this is
    # that edit). It becomes load-bearing with `dry_understatement`: humor is
    # granted to the four employee desks and to neither evidence desk, and a
    # dial floor read HERE expresses that with no second availability table to
    # keep in step. `_reply_dial` reaches the codex through `expression_dial`,
    # which is the one adjudicated seam — the fence is untouched.
    dial = _reply_dial(account, root)
    allowed = [f for f, spec in FAMILIES.items()
               if not (spec.get("needs_chart") and not chart)
               and not (spec.get("needs_callback") and not callback)
               and dial >= int(spec.get("dial_floor") or 1)]

    # WARMTH-SUPPLY-AWARE ROTATION. The anti-cold critic rejects a long reply
    # from an employee desk that carries no human register, so a family for
    # which THIS parent admits no warmth move is a family that will draft an
    # item the gate then kills — an abstention the reader never sees and the
    # operator cannot diagnose. Narrowing the pool to families the register can
    # actually warm turns that silent loss into a different, equally valid
    # reasoning move. The narrowing is a PREFERENCE, never a pin: if no family
    # admits a move, the full pool is restored and the plain draft ships, which
    # is exactly what the flagship (dial 1) always gets.
    warmable = [f for f in allowed
                if warmth_moves_for(account, parent_shape=parent_shape, family=f,
                                    root=root, has_thesis=has_thesis,
                                    has_detail=bool(detail), tier=tier)]
    pool = warmable or allowed

    # ── The response type: a NARROWING of the family pool, not a replacement for
    # the family LRU ─────────────────────────────────────────────────────────
    chain = list((facts or {}).get("chain") or (target or {}).get("chain") or [])
    familiarity = _familiarity_of(account, target, relations_row, root)
    rtype_pick = _choose_type(account, requested=response_type, allowed=allowed,
                              day_counts=day_counts, thread_id=str(
                                  target.get("thread_root_id")
                                  or target.get("status_id")
                                  or target.get("url")
                                  or target.get("author") or ""),
                              as_of=as_of, cfg=cfg, root=root)
    rtype = str(rtype_pick.get("value") or "")
    type_pool = _narrow_to_type(pool, rtype) or _narrow_to_type(allowed, rtype) or pool
    primary = (family if family in FAMILIES
               else rotate_family(recent_families, allowed=type_pool))

    ctx = {
        "subject": target.get("subject") or target.get("ticker"),
        "ticker": target.get("ticker"),
        "mechanism": target.get("mechanism"),
        "as_of_stamp": (chart or {}).get("as_of_stamp"),
        "callback": callback,
        "account": account,
        "root": root,
        "detail": detail,
        # The parent's own words, for the BUILD-TIME element floor
        # (`reply_shape._elements_ok`): "a specific reference to the post" can
        # only be checked against the post. Absent, the floor simply finds no
        # reference and the short shapes lean harder on their opinion/marker
        # halves — degraded, never wrong.
        "parent_text": str((target or {}).get("text") or ""),
        "cfg": cfg,
        # THE PARENT IDENTITY IS THE DIVERGENCE INPUT. First the thread root,
        # then this post's own id, then the URL, then the author: the first
        # stable thing available. Falling through to "" is legal and only
        # collapses every parent into one hash bucket, which the rotation still
        # breaks up — but a target that carries an id and does not pass it here
        # has thrown away the cross-thread half of the anti-sameness guarantee.
        "thread_id": str(target.get("thread_root_id")
                         or target.get("status_id")
                         or target.get("url")
                         or target.get("author") or ""),
    }

    order = [primary] + [f for f in rotate_order(type_pool, primary) if f != primary]
    order += [f for f in rotate_order(pool, primary) if f not in order]
    order += [f for f in rotate_order(allowed, primary) if f not in order]
    drafts: list[tuple[str, str]] = []
    warmths: list[str | None] = []
    tails: list[str] = []
    shapes: list[str] = []
    rolls: list[float] = []
    dropped: list[str] = []
    shape_copies: list[str] = []
    # ONE WINDOW, NOT AN ACCUMULATING ONE. The first version of this loop also
    # fed each drawn tail back in, so the primary and its alternates could not
    # collide — DEAD CODE, and a mutation test proved it: the alternates come
    # from `rotate_order`, which yields DISTINCT families, and the pools are
    # family-scoped and share no template across families, so a tail drawn for
    # one family is never a candidate for the next. The distinctness is a
    # property of the pool table (a test pins that no template appears under two
    # families) and pretending a rotation was enforcing it would hide which
    # invariant is really load-bearing.
    window = [str(t) for t in (recent_tails or [])]
    for fam in order[: 1 + max(0, int(n_alts))]:
        move = _select_warmth(
            account, family=fam, parent_shape=parent_shape, root=root,
            recent_warmth=recent_warmth, requested=warmth if fam == primary else None,
            has_thesis=has_thesis, has_detail=bool(detail), tier=tier,
            parent_author=parent_author,
        )
        # Selected TWICE on purpose, and the two must agree: once here for the
        # record the caller rotates on, once inside `compose` for the copy. Same
        # inputs, same pure function; a test asserts the reported tail is the one
        # in the draft, because a history that records a doorway which never
        # shipped is worse than no history.
        drawn = select_tail(account, fam, thread_id=str(ctx["thread_id"]),
                            recent_tails=window, root=root)
        fam_ctx = {**ctx, "recent_tails": list(window), "chain": list(chain),
                   "recent_shape_copy": list(recent_shapes or [])}
        text, used_shape, roll, drop, copy_used = _compose_shaped(
            fam, gift, fam_ctx, warmth=move, account=account,
            requested=shape if fam == primary else None,
            response_type=rtype, parent_shape=parent_shape,
            day_counts=day_counts, familiarity=familiarity,
            has_chain=bool(chain), as_of=as_of, root=root,
            avoid={t for _, t in drafts},
        )
        if not text:
            # `full` is always legal and always renders, so an empty answer here
            # means the warmth opener itself was refused at compose time. Ship
            # the plain draft rather than the shape the anti-cold critic would
            # kill a moment later.
            move = None
            text, used_shape, roll, drop, copy_used = _compose_shaped(
                fam, gift, fam_ctx, warmth=None, account=account,
                requested="full", response_type=rtype, parent_shape=parent_shape,
                day_counts=day_counts, familiarity=familiarity,
                has_chain=bool(chain), as_of=as_of, root=root,
                avoid={t for _, t in drafts},
            )
        drafts.append((fam, text))
        warmths.append(move)
        # A shape that suppresses the doorway did not USE the doorway it drew,
        # and reporting one it never shipped is exactly the defect the tail
        # build's "selected twice, and the two must agree" comment names.
        tails.append(drawn if REPLY_SHAPE_DOORWAY.get(used_shape, True) else "")
        shapes.append(used_shape)
        rolls.append(roll)
        dropped.append(drop)
        shape_copies.append(copy_used)

    # Voice pass: the SHARED dial, kind="reply". apply_pass is deterministic
    # clean-up only (off-signature emoji, exclamation downgrade); everything
    # else the dial dislikes is reported, never silently rewritten.
    polished: list[tuple[str, str]] = []
    for fam, text in drafts:
        try:
            from engine.marketing import expression_dial as _dial  # noqa: PLC0415

            _, body = _dial.apply_pass("", text, account=account, kind="reply", root=root)
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_drafter: dial pass unavailable for %r: %s", account, exc)
            body = text
        polished.append((fam, _clean(body)))

    # E4 phrasing pass — OPTIONAL, and DOWNSTREAM of everything above. The
    # deterministic draft is the argument and the fallback, so this line can
    # only change words, never whether a reply exists.
    voice = _voice_pass(
        polished[0][1], family=polished[0][0], account=account, target=target,
        whitelist=whitelist, cfg=cfg, root=root, warmth=warmths[0],
    )
    polished[0] = (polished[0][0], voice["text"])

    # The dial's own findings on the SHIPPING primary text, reported not
    # swallowed: the critics re-run this independently, but a drafter that
    # returns an empty violation list it never populated is a permanent
    # all-clear to any caller that trusts the field. Graded AFTER the voice
    # pass, because grading the pre-voice text would describe copy that is not
    # the copy being returned.
    dial_violations: list[str] = []
    try:
        from engine.marketing import expression_dial as _dial  # noqa: PLC0415

        dial_violations = list(_dial.violations(
            "", polished[0][1], account=account, kind="reply", root=root,
            include_house_bans=False,
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_drafter: dial grading unavailable for %r: %s", account, exc)

    return {
        "draft": polished[0][1],
        "alt_drafts": [t for _, t in polished[1:]],
        "family": polished[0][0],
        "alt_families": [f for f, _ in polished[1:]],
        "warmth": warmths[0],
        "alt_warmth": warmths[1:],
        # The doorway TEMPLATE this draft closed on, for the caller's rotation
        # history. Reported for the same reason `family` is: a rotation axis the
        # producer cannot read back is an axis that resets every night.
        "tail": tails[0],
        "alt_tails": tails[1:],
        # The SHAPE axis, reported for the same reason `family` and `tail` are:
        # an axis the producer cannot read back is an axis that resets every
        # night, which is precisely what happened to the warmth and tail LRUs
        # between the last two builds and this one (see reply_producer §F.5).
        "shape": shapes[0],
        "alt_shapes": shapes[1:],
        # The head or closer TEMPLATE the shape drew, for the caller's rotation
        # history — the same field `tail` is and for the same reason. Templates,
        # never rendered copy: the rendering changes with the gift, so a history
        # of finished sentences could never match what the selector is choosing
        # between.
        "shape_copy": shape_copies[0],
        "alt_shape_copy": shape_copies[1:],
        "response_type": rtype,
        "familiarity": familiarity,
        "shape_roll": rolls[0],
        "type_roll": float(rtype_pick.get("roll") or 0.0),
        "parent_shape": parent_shape,
        "numbers_whitelist": whitelist,
        "components": {
            "gift": gift,
            "family_move": FAMILIES[polished[0][0]]["move"],
            "trigger": FAMILIES[polished[0][0]]["trigger"],
            "warmth_move": (WARMTH_MOVES[warmths[0]]["does"] if warmths[0] else None),
            "parent_shape": parent_shape,
            "shape": shapes[0],
            "response_type": rtype,
            # "" or "shape": a warmth move the SHAPE could not carry (a colon
            # join inside a one-sentence budget, or an addition head that is
            # already the acknowledgement). Reported rather than silent, because
            # a rotation history that records a move which never reached the copy
            # is a history that lies to the next draw.
            "warmth_dropped": dropped[0],
            "chart": bool(chart),
            "voice_mode": voice["mode"],
        },
        "dial_violations": dial_violations,
        "voice": voice,
    }


def _select_warmth(
    account: str,
    *,
    family: str,
    parent_shape: str | None,
    root: Path | str | None,
    recent_warmth: list[str] | None,
    requested: str | None = None,
    has_thesis: bool = False,
    has_detail: bool = False,
    tier: str | None = None,
    parent_author: str = "",
) -> str | None:
    """One warmth move for this (account, family, parent), or None.

    None is a first-class answer and is what a flagship reply, an unclassifiable
    parent, or a family with no compatible move all resolve to — those get
    today's plain draft byte for byte.
    """
    pool = warmth_moves_for(
        account, parent_shape=parent_shape, family=family, root=root,
        has_thesis=has_thesis, has_detail=has_detail, tier=tier,
    )
    # `wry_solidarity` may aim at a process, a crowd or an institution and never
    # at a person. The parent AUTHOR is what makes the difference between the
    # move and the antipattern, so a thread whose author's name is in play at
    # all withdraws it — the target discriminates the move, so an ambiguous
    # target is not a target we take.
    if "wry_solidarity" in pool and _targets_a_person(
            " ".join((WARMTH_MOVES["wry_solidarity"].get("openers") or {})
                     .get(account) or ()), parent_author=parent_author):
        pool = [m for m in pool if m != "wry_solidarity"]
    if requested and requested in pool:
        return requested
    return rotate_warmth(recent_warmth, allowed=pool)


def _voice_pass(
    draft: str,
    *,
    family: str,
    account: str,
    target: dict,
    whitelist: list[str],
    cfg: dict | None,
    root: Path | str | None,
    warmth: str | None = None,
) -> dict[str, Any]:
    """The E4 LLM phrasing hook. Returns {text, mode, provider, violations}.

    ``reply_voice.voice_or_fallback`` is two-key armed (config
    ``reply_desk.voice.enabled`` + ``MARKETING_LLM_ENABLED``), never raises, and
    hands back THIS draft on any gate hit, provider failure or disarmed key. The
    try/except here is therefore about the IMPORT — if the module is absent or
    broken, the deterministic draft is still what ships, and the alternates are
    never voiced at all (they exist to differ in reasoning MOVE, and one call
    per drafted reply is what keeps the runaway guard meaningful).

    The output is re-``_clean``ed: no dash tell may leave this module, whoever
    wrote the sentence.
    """
    fallback = {"text": draft, "mode": "off", "provider": None, "violations": []}
    try:
        from engine.marketing import reply_voice as _voice  # noqa: PLC0415

        out = _voice.voice_or_fallback(
            draft,
            family=family,
            account=account,
            parent_text=str((target or {}).get("text") or ""),
            parent_author=str((target or {}).get("author") or ""),
            numbers_whitelist=list(whitelist or []),
            family_spec=FAMILIES.get(family),
            warmth=warmth,
            warmth_spec=WARMTH_MOVES.get(str(warmth)) if warmth else None,
            cfg=cfg,
            root=root,
        )
    except Exception as exc:  # noqa: BLE001 — a drafted reply must still exist
        log.warning("reply_drafter: voice pass unavailable for %r: %s", account, exc)
        return fallback
    text = _clean(str(out.get("text") or "")) or draft
    return {
        "text": text,
        "mode": str(out.get("mode") or "off"),
        "provider": out.get("provider"),
        "violations": list(out.get("violations") or []),
    }


def rotate_order(allowed: list[str], primary: str) -> list[str]:
    """Deterministic alternate ordering: the families furthest from the primary
    in the register, so alternates differ in MOVE, not in wording."""
    pool = [f for f in allowed if f != primary]
    if not pool:
        return []
    try:
        idx = allowed.index(primary)
    except ValueError:
        idx = 0
    return pool[idx:] + pool[:idx]


__all__ = [
    "FAMILIES", "family_ids", "rotate_family", "rotate_order", "compose",
    "draft_reply", "attach_chart", "prerender_artillery",
    "WARMTH_MOVES", "PARENT_SHAPES", "MAX_WARMTH_OPENER_UNITS", "warmth_ids",
    "rotate_warmth", "classify_parent", "warmth_moves_for", "openers_for",
    "extract_detail", "fuse_warmth", "author_name_hits", "clear_warmth_cache",
    "FAMILY_TAILS", "TAIL_DEFAULT_LANE", "tail_lane", "tails_for",
    "select_tail", "render_tail", "clear_tail_cache", "pick_from_pool",
    "REPLY_SHAPE_DOORWAY",
]
