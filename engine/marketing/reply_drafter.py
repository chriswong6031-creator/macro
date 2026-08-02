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

Public API:
    FAMILIES: dict[str, dict]
    WARMTH_MOVES: dict[str, dict]
    family_ids() -> list[str]
    warmth_ids() -> list[str]
    rotate_family(recent, *, allowed=None) -> str
    rotate_warmth(recent, *, allowed=None) -> str
    classify_parent(target) -> str | None
    warmth_moves_for(account, *, parent_shape=None, family=None, root=None) -> list[str]
    compose(family, gift, ctx, *, warmth=None) -> str
    draft_reply(*, account, target, facts, ...) -> dict
    attach_chart(as_of, chart_id, *, root=None) -> dict | None
    prerender_artillery(tickers, as_of, *, root=None, ...) -> list[dict]
"""
from __future__ import annotations

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
}


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


#: (account, move, opener, root-key) → clean?  The guard sweep below runs
#: `banned_language` + `expression_dial.violations` + `am_r1_hits` per opener,
#: which is cheap but not free, and the answer only changes when a persona spec
#: changes. `expression_dial.clear_cache()` is the documented way to invalidate
#: a codex; this cache is cleared alongside it by `clear_warmth_cache`.
_OPENER_OK_CACHE: dict[tuple[str, str, str, str], bool] = {}


def clear_warmth_cache() -> None:
    """Drop the per-opener guard cache (tests that write specs into a tmp root)."""
    _OPENER_OK_CACHE.clear()


def _opener_clears_persona_guards(account: str, opener: str,
                                  root: Path | str | None = None) -> bool:
    """Does this opener survive the persona's OWN guards?

    This is the mechanism that makes the persona specs canonical rather than
    decorative: a word added to a codex ``banned`` list, a quirk marker switched
    dark, or a new AM-R1 detector removes the offending opener from the register
    the same night, with no code change here. The three guards are the same
    three the shipped copy has to clear downstream, so an opener that trips one
    is not a style choice, it is a defect that would have cost a whole item at
    critic time.

    The ``{detail}`` slot is filled with a neutral placeholder before the sweep:
    a bare "{detail}" is not English and the register guards would judge the
    punctuation rather than the copy.
    """
    probe = str(opener or "").replace("{detail}", "breadth")
    key = (str(account), str(opener), "", str(root or ""))
    cached = _OPENER_OK_CACHE.get(key)
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
        # opener: losing one warmth move costs a plainer reply, shipping
        # unchecked persona copy costs the account.
        log.warning("reply_drafter: opener guard sweep unavailable for %r (%s)",
                    account, exc)
        ok = False
    _OPENER_OK_CACHE[key] = ok
    return ok


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
            warmth: str | None = None) -> str:
    """Build one draft from a family + a gift sentence, optionally warmed.

    The gift is used VERBATIM: it came from an own-feed fact builder, so its
    numbers are already whitelisted. Grip and doorway introduce no figures,
    which is what keeps ``fact_discipline`` satisfiable by construction.

    ``warmth`` names a :data:`WARMTH_MOVES` entry. With ``warmth=None`` this
    function is byte-for-byte what it was before the warmth build, which is why
    every pre-existing compose test still passes unchanged.
    """
    ctx = dict(ctx or {})
    gift = _clean(gift)
    subject = _subject_of(ctx)
    lead = _lead_of(ctx)
    stamp = str(ctx.get("as_of_stamp") or "").strip()

    if family == "missing_variable":
        body = f"{gift}\n\nThe price move is the reaction. {lead.capitalize()} is the test."
    elif family == "second_order":
        body = (f"{gift}\n\nIf that holds, the pressure shows up in {lead} before it "
                f"shows up in {subject}.")
    elif family == "respectful_disagreement":
        body = (f"Observation holds. The mechanism is where I'd push back.\n\n{gift}\n\n"
                f"That reads like {lead}, not {subject}.")
    elif family == "compression":
        body = f"Short version: {gift}"
    elif family == "conditional_prediction":
        body = (f"{gift}\n\nIf {lead} keeps going the same direction while {subject} "
                f"stays put, the two are arguing and one of them is wrong.")
    elif family == "human_reaction":
        body = f"okay, this one is actually interesting.\n\n{gift}\n\nThat is the part I'd watch."
    elif family == "reframe":
        body = f"{gift}\n\nWorth reading this as a {lead} story rather than a {subject} story."
    elif family == "cross_market_lead":
        body = f"{gift}\n\n{lead.capitalize()} moved first. {subject.capitalize()} is catching up."
    elif family == "correction":
        body = f"One thing worth fixing in the thread: {gift}"
    elif family == "micro_framework":
        body = (f"Two questions settle this.\n\n1. What is {lead} doing.\n"
                f"2. Whether {subject} agrees.\n\n{gift}")
    elif family == "author_question":
        body = (f"{gift}\n\nDoes your read on {subject} survive if {lead} keeps "
                f"moving against it?")
    elif family == "original_chart":
        body = f"Charted it.\n\n{gift}"
    elif family == "acknowledgment_plus_one":
        body = f"Agreed, with one addition.\n\n{gift}"
    elif family == "callback":
        prior = str(ctx.get("callback") or "").strip()
        body = (f"{gift}\n\nSame condition we flagged before: {prior}" if prior
                else f"{gift}\n\nSame condition we flagged before.")
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


def draft_reply(
    *,
    account: str,
    target: dict,
    facts: dict,
    family: str | None = None,
    recent_families: list[str] | None = None,
    warmth: str | None = None,
    recent_warmth: list[str] | None = None,
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
             parent_shape, numbers_whitelist, components, dial_violations}.

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
                    "parent_shape": parent_shape,
                    "numbers_whitelist": whitelist,
                    "components": {
                        "gift": "", "family_move": FAMILIES["human_reaction"]["move"],
                        "trigger": FAMILIES["human_reaction"]["trigger"],
                        "warmth_move": WARMTH_MOVES[move]["does"],
                        "relationship_only": True, "chart": False,
                        "voice_mode": "off",
                    },
                    "dial_violations": [],
                    "voice": {"text": _clean(text), "mode": "off",
                              "provider": None, "violations": []},
                }
        return {
            "draft": "", "alt_drafts": [], "family": None, "alt_families": [],
            "warmth": None, "alt_warmth": [], "parent_shape": parent_shape,
            "numbers_whitelist": whitelist, "components": {"abstained": "no own-feed fact"},
            "dial_violations": [],
        }

    allowed = [f for f, spec in FAMILIES.items()
               if not (spec.get("needs_chart") and not chart)
               and not (spec.get("needs_callback") and not callback)]

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
    primary = family if family in FAMILIES else rotate_family(recent_families, allowed=pool)

    ctx = {
        "subject": target.get("subject") or target.get("ticker"),
        "ticker": target.get("ticker"),
        "mechanism": target.get("mechanism"),
        "as_of_stamp": (chart or {}).get("as_of_stamp"),
        "callback": callback,
        "account": account,
        "root": root,
        "detail": detail,
    }

    order = [primary] + [f for f in rotate_order(pool, primary) if f != primary]
    order += [f for f in rotate_order(allowed, primary) if f not in order]
    drafts: list[tuple[str, str]] = []
    warmths: list[str | None] = []
    for fam in order[: 1 + max(0, int(n_alts))]:
        move = _select_warmth(
            account, family=fam, parent_shape=parent_shape, root=root,
            recent_warmth=recent_warmth, requested=warmth if fam == primary else None,
            has_thesis=has_thesis, has_detail=bool(detail), tier=tier,
            parent_author=parent_author,
        )
        try:
            text = compose(fam, gift, ctx, warmth=move)
        except ValueError as exc:
            # An over-budget opener is a BUILD defect, not a runtime condition:
            # report it loudly and ship the plain draft rather than the shape
            # the anti-cold critic would kill a moment later.
            log.warning("reply_drafter: warmth %r rejected at compose for %r: %s",
                        move, account, exc)
            move, text = None, compose(fam, gift, ctx)
        drafts.append((fam, text))
        warmths.append(move)

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
        "parent_shape": parent_shape,
        "numbers_whitelist": whitelist,
        "components": {
            "gift": gift,
            "family_move": FAMILIES[polished[0][0]]["move"],
            "trigger": FAMILIES[polished[0][0]]["trigger"],
            "warmth_move": (WARMTH_MOVES[warmths[0]]["does"] if warmths[0] else None),
            "parent_shape": parent_shape,
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
]
