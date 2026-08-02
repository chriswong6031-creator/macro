"""engine.marketing.reply_shape — the SHAPE axis (XG-W4b §A/§B).

THE DEFECT THIS MODULE CLOSES, measured on ``reply_drafter`` at 8b36f766276.
``compose()`` has exactly ONE output shape. Nine of the fourteen families render
as ``{gift}\\n\\n{drawn tail}`` and the other five as ``{frame}{gift}``, so every
employee reply is two sentences minimum and typically 30-45 words — against a
winning-reply corpus whose median is 11 words and in which 26.1% of winners are
1-5 words (``research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md`` §3).
``reply_critics.MAX_REPLY_WORDS`` caps at 60, which is a CEILING and not a SHAPE:
nothing in the drafter could emit "That guidance was much weaker than the headline
suggests." Short reactions were 0% of output. The operator's brief asks for ~30%.

THE LAW THIS ADDS, one sentence (doctrine §13.1):

    A reply's SHAPE is a third rotation axis beside family and warmth, it is
    chosen by a deficit-weighted stable draw rather than a cycle, and the
    deterministic path must be able to emit a fourteen-word committed sentence —
    because a desk whose every reply is gift + grip + doorway is a template with
    four names on it.

**All of it holds with ``reply_voice`` MUTED.** A muted provider is the state that
reaches production the moment a key lapses, and the drafter's own docstring says
the deterministic path is the product. A shape that only exists in a system
prompt is not built, so every renderer here is pure string work over the gift.

WHY A DEFICIT-WEIGHTED DRAW AND NOT A ROTATION. The requirement is contradictory
on purpose and both halves are real: the measured mix has to land near the
operator's 30/25/15/15/10/5, and a deterministic 30/25/15/15/10/5 CYCLE is itself
a tell — four accounts sharing one fintwit audience, stepping through shapes in
lockstep, is the same bot-farm signature the tail build just closed one axis over.
The resolution: the DAY is the control loop (``day_counts`` bends the odds toward
whatever bucket is running cold), the DRAW is the randomiser (a blake2b roll over
(account, as_of, thread_id, family, salt), so two adjacent replies from one desk
get uncorrelated rolls and consecutive identical shapes are possible — a human's
replies are not shape-alternating), and the HASH is what makes both auditable
(``choose_*`` return their weights, deficits and roll, and the queue item carries
them, so an operator re-derives any pick exactly instead of arguing with a coin
flip).

THE FENCE. This module is NOT on
``tests/test_marketing_personas.py::test_no_generation_module_reads_a_persona_spec``'s
allow-list and must never become a persona-spec reader. Persona attributes reach
here only through ``reply_drafter`` (which reaches them through
``expression_dial``) and through the optional ``persona_model`` overlay, which is
a separate, non-frozen layer and never a second ban list. There is deliberately
no ``config`` + persona-directory path literal anywhere in this file.

Public API (frozen by the XG-W4b spec, §F.2):
    REPLY_SHAPES / SHAPE_IDS / SHORT_FORM_SHAPES
    RESPONSE_TYPES / TYPE_FAMILIES / TYPE_SHAPE_PRIOR / DEFAULT_RESPONSE_MIX
    SHAPE_HEADS / SHAPE_TAILS / DEFICIT_FLOOR / MIX_WINDOW_DAYS / MIX_MIN_ITEMS
    shape_ids() -> list[str]
    shapes_for(*, family, parent_shape, response_type, has_chain, gift_units,
               relationship_only=False) -> list[str]
    choose_response_type(account, *, day_counts, thread_id, ...) -> dict
    choose_shape(account, *, response_type, family, ...) -> dict
    render(shape, *, gift, ctx, family, warmth=None, account="", ...) -> str
    heads_for(account, shape, root=None) -> list[str]
    closers_for(account, shape, root=None) -> list[str]
    shape_mix(rows, *, window_days=7) -> dict
    clear_shape_cache() -> None
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. The five shapes
# ---------------------------------------------------------------------------
#
# Budgets are in CONTENT UNITS (``reply_critics._content_units``: words + figures
# + cashtags; handles and URLs count zero) and in characters, and BOTH are
# enforced at BUILD time inside :func:`render`. An over-budget render makes the
# shape unavailable and the caller falls to the next legal one.
#
# NEVER TRUNCATE. Truncation is how a reply loses its verb, and a half sentence
# under a real woman's byline is worse than a mini-essay. "" is the refusal.
#
# ``families_ok`` is the §A.3 matrix, written per shape rather than per family so
# a new family is opt-IN: a family nobody added to a shape gets ``full`` only,
# which is today's behaviour and therefore the safe default.
REPLY_SHAPES: dict[str, dict[str, Any]] = {
    "one_line": {
        "label": "one committed sentence",
        "max_units": 14,
        "max_chars": 100,
        "max_sentences": 1,
        "doorway": False,
        # micro_framework's structure IS the payload (it is the sole
        # LONG_FORM_FAMILIES member) so it may not compress to a line;
        # original_chart and callback each carry a mandatory second element (the
        # chart line, the prior position) a one-liner has nowhere to put; and
        # acknowledgment_plus_one IS an addition by definition, so one_line would
        # delete the acknowledgement half.
        "families_ok": frozenset({
            "missing_variable", "second_order", "respectful_disagreement",
            "compression", "conditional_prediction", "human_reaction", "reframe",
            "cross_market_lead", "correction", "author_question",
            "dry_understatement",
        }),
        "needs": (),
    },
    "fragment_exchange": {
        "label": "two short clauses, texting rhythm",
        "max_units": 18,
        "max_chars": 130,
        "max_sentences": 2,
        "doorway": False,
        # conditional_prediction is a two-legged if/then that reads as a fragment
        # when split, and cross_market_lead/second_order need the room to name
        # the second market.
        "families_ok": frozenset({
            "missing_variable", "respectful_disagreement", "compression",
            "human_reaction", "reframe", "acknowledgment_plus_one",
            "dry_understatement",
        }),
        "needs": ("closer",),
    },
    "addition": {
        "label": "agreement plus the thing they missed",
        "max_units": 26,
        "max_chars": 180,
        "max_sentences": 2,
        "doorway": False,          # the head replaces s2; nothing is appended
        "families_ok": frozenset({
            "missing_variable", "second_order", "reframe", "cross_market_lead",
            "correction", "original_chart", "acknowledgment_plus_one", "callback",
        }),
        "needs": ("head",),
    },
    "compact_chain": {
        "label": "the arrow form",
        "max_units": 22,
        "max_chars": 160,
        "max_sentences": 1,
        "doorway": False,
        "families_ok": frozenset({
            "second_order", "compression", "cross_market_lead", "micro_framework",
        }),
        "needs": ("chain",),
    },
    "full": {
        "label": "gift, grip and doorway",
        # MAX_REPLY_WORDS, unchanged. `full` is byte-for-byte what HEAD produces
        # and a parity test asserts it over the whole family x warmth grid.
        "max_units": 60,
        "max_chars": 240,
        "max_sentences": 0,        # 0 == unbounded; reply_value owns the ceiling
        "doorway": True,
        "families_ok": None,       # every family, including any added later
        "needs": (),
    },
}

SHAPE_IDS: tuple[str, ...] = (
    "one_line", "fragment_exchange", "addition", "compact_chain", "full",
)

#: The two shapes whose replies react to the PARENT's referents rather than
#: introducing their own. ``reply_critics.short_form_engaged`` keys on this set
#: (XG-W4b §D.4): ``_referents("Yeah, but that is the problem.")`` is empty, so
#: ``persona_label`` rejects every short reaction until that exemption lands.
SHORT_FORM_SHAPES: frozenset[str] = frozenset({"one_line", "fragment_exchange"})

#: The ASCII connector for :data:`compact_chain`. **NOT** U+2192 "→": that glyph
#: sits inside ``expression_dial._EMOJI_RE``'s ``←-⇿`` class, so ``apply_pass``
#: STRIPS it and ``violations`` reports an off-signature emoji — the chain would
#: silently render as "higher oil stickier inflation fewer cuts", a list of noun
#: phrases with the causality deleted, and the dial would blame the desk for an
#: emoji it never chose. Measured on HEAD: ``apply_pass`` leaves "->" untouched
#: and rewrites the unicode form; ``_clean`` rewrites em/en dashes and leaves
#: "->" alone. A test pins both directions.
CHAIN_CONNECTOR = " -> "

#: 3 or 4 links. Two is not a chain (it is a sentence with an arrow in it) and
#: five is a paragraph wearing arrows.
CHAIN_MIN_LINKS = 3
CHAIN_MAX_LINKS = 4


def shape_ids() -> list[str]:
    return list(SHAPE_IDS)


# ---------------------------------------------------------------------------
# 2. Response types — the operator's seven, mapped onto six buckets
# ---------------------------------------------------------------------------
#
# The operator names seven response types with six percentages: "personal
# interpretation" and "compact explanation" are VOICES of the analytical bucket,
# not separate quotas, which is why there are six here and not seven.
#
# A TYPE IS A NARROWING OF THE FAMILY POOL, NEVER A REPLACEMENT FOR THE FAMILY
# LRU. ``reply_drafter.rotate_family`` still picks least-recently-used INSIDE the
# narrowed pool, so §13.7 anti-sameness is untouched — the type decides which
# register of moves is on the table, the LRU decides which of them is due.
RESPONSE_TYPES: tuple[str, ...] = (
    "short_reaction", "analytical_addition", "agreement_nuance",
    "disagreement", "question", "humor",
)

#: ``agreement_nuance`` overlaps ``analytical_addition`` on two families
#: DELIBERATELY: the operator's "Exactly — and the refinancing schedule makes it
#: worse" is a second-order move delivered as an agreement. The discriminator is
#: the SHAPE prior (``addition`` at 0.70), not the family.
TYPE_FAMILIES: dict[str, frozenset[str]] = {
    "short_reaction": frozenset({
        "human_reaction", "compression", "reframe", "correction"}),
    "analytical_addition": frozenset({
        "missing_variable", "second_order", "cross_market_lead",
        "micro_framework", "original_chart", "callback",
        "conditional_prediction"}),
    "agreement_nuance": frozenset({
        "acknowledgment_plus_one", "second_order", "missing_variable"}),
    "disagreement": frozenset({
        "respectful_disagreement", "correction", "reframe"}),
    "question": frozenset({"author_question"}),
    "humor": frozenset({"dry_understatement"}),
}

#: The persona skew lives in the TYPE weights (:data:`DEFAULT_RESPONSE_MIX`); the
#: shape prior is a property of the TYPE and is fleet-wide.
#:
#: THE NUMBER THAT MAKES THIS FALSIFIABLE: under the fleet-mean type weights the
#: expected ``full`` share is 0.244. On HEAD it is 1.00. ``test_marketing_
#: reply_shape.py::TestTheMixIsMeasured`` runs 5,000 draws over the four employee
#: desks with these exact tables and asserts realised ``full`` in [0.18, 0.32].
TYPE_SHAPE_PRIOR: dict[str, dict[str, float]] = {
    "short_reaction": {"one_line": 0.55, "fragment_exchange": 0.35, "full": 0.10},
    "analytical_addition": {"addition": 0.35, "full": 0.35, "compact_chain": 0.30},
    "agreement_nuance": {"addition": 0.70, "fragment_exchange": 0.15, "full": 0.15},
    "disagreement": {"one_line": 0.35, "full": 0.45, "fragment_exchange": 0.20},
    "question": {"one_line": 0.55, "full": 0.45},
    "humor": {"one_line": 0.60, "fragment_exchange": 0.40},
}

#: account -> RESPONSE_TYPES -> weight. Overridable at
#: ``config/marketing.yml`` -> ``reply_desk.response_mix.accounts.<id>``; the code
#: defaults exist so a missing config never DISARMS the mix (the PACING_DEFAULTS
#: posture — a knob that silently defaults to "off" is a rule nobody built).
#:
#: THE FOUR-EMPLOYEE MEAN IS 0.30 / 0.265 / 0.16 / 0.135 / 0.08 / 0.06 — the
#: operator's 30/25/15/15/10/5 to within a point and a half on every bucket,
#: while NO TWO DESKS SHARE A ROW. That is "percentages should vary by persona"
#: satisfied without drifting the fleet mix, and a test pins both halves.
#:
#: Every row is derived from that desk's own pinned codex, so a re-weighting
#: argues from the spec and not from vibes:
#:
#:   kelly   "terse, analytical ... fragments when they sharpen rhythm" -> highest
#:           short share. "Chart detective" + "What Would Prove This Wrong?" ->
#:           highest disagreement. "Pointed questions only when answerable" ->
#:           below-average questions. "Internet-native dry wit" -> highest humor.
#:   sophia  "may run slightly longer when the narrative needs room" is the ONLY
#:           codex on the roster that licenses length -> highest analytical,
#:           lowest short. "Sparing questions" -> lowest question rate.
#:   cici    "polite corrections" means her disagreement is EXPRESSED as
#:           agreement-plus-correction -> agreement highest, raw disagreement
#:           lowest of the four. Humor lowest: her lawful surface is narrowest.
#:   meagan  "opens on a human reaction", "upbeat, quick, human" -> highest short.
#:           "One playful line followed by one useful line" -> highest humor. Her
#:           beat is crowd translation, not mechanism dispute -> lowest
#:           disagreement.
#:   flagship §5 register map: "sharp read + data drop, terse verdict", Never
#:           column "anything warm". Agreement is a warmth act -> 0.05. Humor is
#:           unavailable by dial floor -> 0.00, and the renormaliser must handle a
#:           zero-weight bucket without dividing by zero (it does; a test pins it).
DEFAULT_RESPONSE_MIX: dict[str, dict[str, float]] = {
    "kelly": {"short_reaction": 0.34, "analytical_addition": 0.24,
              "agreement_nuance": 0.10, "disagreement": 0.18,
              "question": 0.08, "humor": 0.06},
    "sophia": {"short_reaction": 0.22, "analytical_addition": 0.34,
               "agreement_nuance": 0.18, "disagreement": 0.14,
               "question": 0.06, "humor": 0.06},
    "cici": {"short_reaction": 0.28, "analytical_addition": 0.28,
             "agreement_nuance": 0.20, "disagreement": 0.12,
             "question": 0.08, "humor": 0.04},
    "meagan": {"short_reaction": 0.36, "analytical_addition": 0.20,
               "agreement_nuance": 0.16, "disagreement": 0.10,
               "question": 0.10, "humor": 0.08},
    "flagship": {"short_reaction": 0.30, "analytical_addition": 0.45,
                 "agreement_nuance": 0.05, "disagreement": 0.12,
                 "question": 0.08, "humor": 0.00},
    "founder": {"short_reaction": 0.34, "analytical_addition": 0.34,
                "agreement_nuance": 0.10, "disagreement": 0.12,
                "question": 0.10, "humor": 0.00},
    "_default": {"short_reaction": 0.30, "analytical_addition": 0.25,
                 "agreement_nuance": 0.15, "disagreement": 0.15,
                 "question": 0.10, "humor": 0.05},
}

MIX_DEFAULT_LANE = "_default"

#: THE DRAW'S THREE CONSTANTS, and a DELIBERATE DEVIATION FROM THE SPEC'S
#: LITERAL STEP 4 — recorded here with the arithmetic that forced it, because a
#: silent formula change is how a distribution stops being the operator's.
#:
#: The spec (§A.4) writes ``d[k] = max(0, w[k] - r[k]) + 0.05`` with
#: ``r[k] = counts[k] / max(1, seen)``, and §G.3 requires every per-account
#: response-type share to land within +/-0.05 of target. **Those two cannot both
#: hold**, and the reason is the DAY LENGTH. A desk drafts ~18 replies a day
#: (``reply_desk.daily_caps.per_account_target``), so:
#:
#:   * the additive floor is a large fraction of a small weight. Solving the
#:     spec's own recursion at equilibrium for meagan (short_reaction w=0.36)
#:     gives r = (w + F) / (S + 1) with S ~ 0.42, i.e. a CEILING of 0.275
#:     against a 0.36 target — an 0.085 miss that no amount of running longer
#:     removes, because it is a fixed point and not variance. Measured over
#:     5,000 draws with the spec's literal formula: worst per-account error
#:     0.102, mean full share 0.277.
#:   * a raw ``counts/seen`` is uselessly coarse early in a day. After the FIRST
#:     draw one bucket has r = 1.00 and is suppressed to the floor for the rest
#:     of the morning — and it is the HIGHEST-weight bucket that gets drawn
#:     first most often, so the systematic loser is the desk's own signature
#:     register.
#:
#: The form below fixes both while serving §A.4's two stated intents exactly:
#:
#:     r_smooth[k] = (counts[k] + w[k] * PRIOR_N) / (seen + PRIOR_N)
#:     d[k]        = w[k] + GAIN * max(0, w[k] - r_smooth[k]) + FLOOR
#:
#:   * BASE = the target weight. With no information the draw IS the target,
#:     which is what an unbiased sampler does; the correction is a correction and
#:     not the whole signal.
#:   * SMOOTHED realised share, anchored on the target with PRIOR_N pseudo-counts
#:     (= the day's own target volume). At ``seen = 0`` the correction is exactly
#:     zero rather than "every bucket is infinitely cold".
#:   * FLOOR stays, and keeps its stated job: a bucket at quota is UNLIKELY,
#:     NEVER IMPOSSIBLE. A hard quota makes the last pick of the day DETERMINED,
#:     which is a cycle at the margin and exactly the tell this design avoids.
#:     0.01 rather than 0.05 because the base weight now carries the reachability
#:     the floor used to have to carry alone.
#:
#: MEASURED at (3.0, 0.01, 18) over 5,000 draws across the four employee desks:
#: worst per-account response-type error 0.047 (gate: 0.05), fleet ``full`` share
#: 0.287 (gate: 0.18-0.32), longest consecutive shape run 6 over 1,250 draws.
#: The control loop is NOT decorative — with GAIN at 0 the same simulation runs
#: to a 9-long consecutive run, and `test_the_day_counts_actually_bend_the_odds`
#: is the mutation check.
DEFICIT_FLOOR: float = 0.01
DEFICIT_GAIN: float = 3.0
DEFICIT_PRIOR_N: int = 18

#: The mix is JUDGED over a rolling window, never per reply. A per-reply random
#: draw is not a distribution, and printing a share off six items is the
#: vacuous-N trap: below :data:`MIX_MIN_ITEMS` the shares come back with an ``n``
#: and ``graded: False``.
MIX_WINDOW_DAYS: int = 7
MIX_MIN_ITEMS: int = 40

#: The alarm bar. 7-day ``full`` share above this at >= MIX_MIN_ITEMS means the
#: mini-essay default is back.
MIX_FULL_ALARM: float = 0.45


# ---------------------------------------------------------------------------
# 3. The two copy pools
# ---------------------------------------------------------------------------
#
# Only ``fragment_exchange`` and ``addition`` need copy. ``one_line`` and
# ``compact_chain`` are pure renderers over the gift, and ``full`` already has
# ``reply_drafter.FAMILY_TAILS``.
#
# BOTH POOLS GO THROUGH ``reply_drafter._copy_clears_persona_guards`` UNCHANGED —
# the same single sweep (banned_language + am_r1_hits + expression_dial.
# violations) behind the same ``_GUARD_OK_CACHE``, cleared by the same
# ``clear_warmth_cache()``. There is deliberately NO third cache: the tail build
# shipped exactly that bug for one revision (``clear_tail_cache()`` dropped the
# tail map while the sweep's own map still answered True, so a codex ``banned``
# edit withdrew nothing).
#
# THE LANES ARE DISJOINT BY CONSTRUCTION across the four employee desks — a test
# pins it, exactly as ``FAMILY_TAILS``'s does — so two desks replying to one
# parent can never close on the same fragment. That is a guarantee, not a
# probability, and it is why the copy is per-account rather than one shared pool.
#
# REGISTER GROUNDING, per lane, so a later edit is not a taste argument: sophia
# measured and narrative, zero exclamations, "the harder part" is her register;
# kelly's lowercase asides are pinned for her and her alone and her codex bans
# every hedging softener, so her heads STATE rather than propose; cici polite
# corrections plus the session handoff, written WITHOUT the session_handoff
# marker phrases so the head spends no frame budget the warmth opener may need;
# meagan conversational and human first, "honestly / genuinely" is hers.
#
# THE ``_default`` LANE IS DELIBERATELY COLD. It serves the flagship and the
# founder at reply dial 1, where W1 is inert by dial and §5's register map lists
# "anything warm" in the Never column.
SHAPE_TAILS: dict[str, dict[str, tuple[str, ...]]] = {
    "fragment_exchange": {
        "_default": ("That is the test.", "Which is the point.",
                     "The rest is noise."),
        "sophia": ("Which is the harder part.", "Genuinely the half I keep.",
                   "That is the part that decides it."),
        "kelly": ("that is the whole story.",
                  "actually the only part that matters.",
                  "and plainly nobody has priced it."),
        "cici": ("Worth saying plainly.", "Same read overnight.",
                 "Genuinely the piece people skip."),
        "meagan": ("Honestly that is the whole thing.",
                   "That is the bit I keep turning over.",
                   "Genuinely the part that nags."),
    },
}

#: MEASURED DEVIATION FROM THE SPEC'S VERBATIM HEAD COPY, and the reason, because
#: the alternative was the exact defect the tail build closed one axis over.
#:
#: §A.5 states the law — "every employee-lane entry carries a
#: ``reply_critics.warmth_markers``-visible phrase" — and its own copy breaks it:
#: SIX of the twelve employee heads as written ("Right, with one thing added:",
#: "yep. the part nobody adds:", "right, and the bit under it:", "Yes, and the
#: piece that gets skipped:", "Yes exactly, and the bit under it:", "Right, and
#: one thing on top:") return ``warmth_markers() == []``. That matters because
#: ``addition`` reaches 26 content units and W1 rejects a >=12-unit dial-2 reply
#: with no register marker at all, so :func:`render` narrows the draw to the
#: marker-carrying entries whenever the gift is cold — and meagan had exactly
#: ONE, which welded her whole ``addition`` register to a single sentence across
#: every parent and every thread. One welded line per desk is precisely the
#: bot-farm signature ``FAMILY_TAILS`` exists to prevent.
#:
#: SIX WORDS CHANGED, register preserved, every line still the spec's sentence:
#:   sophia  "one thing added"        -> "one thing worth adding"  (worth adding)
#:           "the harder half"        -> "the harder part"         (her own §A.5 register line)
#:   kelly   "the part nobody adds"   -> "the part that nobody adds"
#:           "the bit under it"       -> "the thing that sits under it"
#:   cici    "the piece that gets skipped" -> "the piece people skip"  (her own closer register)
#:   meagan  "the bit under it"       -> "the part that sits under it"
#:           "one thing on top"       -> "genuinely one thing on top" (hers)
#: The ``_default`` lane is UNTOUCHED and stays deliberately cold: it serves the
#: flagship and the founder at reply dial 1, where W1 is inert by dial.
SHAPE_HEADS: dict[str, dict[str, tuple[str, ...]]] = {
    "addition": {
        "_default": ("Agreed. One addition:", "Right, with one thing added:",
                     "Same read, one addition:"),
        "sophia": ("Agreed, and the part underneath it:",
                   "Right, with one thing worth adding:",
                   "Yes, and the harder part:"),
        "kelly": ("yep. the part that nobody adds:", "agreed. one thing missing:",
                  "right, and the thing that sits under it:"),
        "cici": ("Agreed, and one thing from the overnight side:",
                 "Same read here, with one addition:",
                 "Yes, and the piece people skip:"),
        "meagan": ("Yes exactly, and the part that sits under it:",
                   "Agreed, and honestly the part that follows:",
                   "Right, and genuinely one thing on top:"),
    },
}


def _lane(account: str) -> str:
    """The copy lane *account* draws heads and closers from.

    Reuses ``reply_drafter.tail_lane``'s answer whenever that account has a tail
    lane, so a desk cannot end up on its own lane for doorways and the shared one
    for fragments. The lookup falls back to this module's own tables for a desk
    that has shape copy and no tail copy (none today; the fallback exists so the
    two tables can diverge without a silent mis-lane).
    """
    account = str(account or "")
    for pools in (SHAPE_TAILS, SHAPE_HEADS):
        for lanes in pools.values():
            if account in lanes:
                return account
    return MIX_DEFAULT_LANE


def _swept(account: str, shape: str, kind: str,
           pool: tuple[str, ...], root: Path | str | None) -> list[str]:
    """Entries surviving *account*'s OWN three guards. One sweep, one cache."""
    from engine.marketing import reply_drafter as _rd  # noqa: PLC0415

    return [entry for entry in pool
            if _rd._copy_clears_persona_guards(
                account, entry, f"{kind}::{shape}::{entry}", root)]


def _pool_for(account: str, shape: str, table: dict[str, dict[str, tuple[str, ...]]],
              kind: str, root: Path | str | None) -> list[str]:
    """The guard-swept pool for this desk, with the documented two-step fallback.

    AN EMPTY LIST IS A REAL ANSWER and :func:`render` treats it as "this shape is
    unavailable to this desk". The tempting alternative — ship the unswept lane so
    the shape stays reachable — is WRONG for the same reason ``tails_for`` says it
    is: it puts copy the persona's own guard just rejected in front of a hostile
    audience under a real woman's name. Losing a shape costs a plainer reply;
    shipping unswept persona copy costs the account.
    """
    lanes = table.get(str(shape)) or {}
    if not lanes:
        return []
    lane = _lane(account)
    clean = _swept(account, shape, kind, tuple(lanes.get(lane) or ()), root)
    if clean:
        return clean
    if lane != MIX_DEFAULT_LANE:
        clean = _swept(account, shape, kind,
                       tuple(lanes.get(MIX_DEFAULT_LANE) or ()), root)
        if clean:
            return clean
    # Bare line-start print, never a logger: every builder here logs with a
    # prefixing format, so log.warning("::warning ...") emits "WARNING ::warning"
    # and GitHub silently drops the annotation — the alarm reviews as armed and
    # produces nothing. House law, five prior occurrences (#3487 .. #3570).
    print(f"::warning title=reply_shape_pool_empty::every {kind} in the "
          f"{shape!r} pool was rejected by {account!r}'s own guards, including "
          f"the {MIX_DEFAULT_LANE!r} lane — this desk cannot draw that shape "
          f"until the copy in reply_shape is fixed", flush=True)
    return []


def heads_for(account: str, shape: str,
              root: Path | str | None = None) -> list[str]:
    """Every head *account* may open *shape* on, after the live guard sweep."""
    return _pool_for(account, shape, SHAPE_HEADS, "head", root)


def closers_for(account: str, shape: str,
                root: Path | str | None = None) -> list[str]:
    """Every closer *account* may close *shape* on, after the live guard sweep."""
    return _pool_for(account, shape, SHAPE_TAILS, "closer", root)


def clear_shape_cache() -> None:
    """Drop the guard-sweep cache. Delegates: there is ONE cache, on purpose."""
    from engine.marketing import reply_drafter as _rd  # noqa: PLC0415

    _rd.clear_warmth_cache()


# ---------------------------------------------------------------------------
# 4. Which shapes compose with which families
# ---------------------------------------------------------------------------
def shapes_for(*, family: str, parent_shape: str | None, response_type: str,
               has_chain: bool, gift_units: int,
               relationship_only: bool = False) -> list[str]:
    """The shapes this (family, parent, gift) may legally take, in SHAPE_IDS order.

    Every gate is a real one and every one of them fails toward ``full``:

      1. ``parent_shape == "sensitive_event"`` -> ``[]``. ``reply_critics.
         blocklist`` hard-stops the whole item anyway; this is belt and braces,
         the same posture ``warmth_moves_for`` takes.
      2. a ``relationship_only`` draft (the ``quiet_sympathy`` reply, which ships
         with NO analytical gift) -> ``["one_line"]`` and nothing else. The
         opener IS the reply; there is no gift to close on and no head to add to.
      3. ``gift_units > max_units - 2`` -> that shape is unavailable, because the
         render would over-budget and :func:`render` would refuse it anyway. Two
         units of slack is the smallest head/closer in the pools.
      4. ``has_chain is False`` -> ``compact_chain`` unavailable. The drafter may
         NOT synthesise a causal chain from a single gift: that is inventing a
         mechanism, the same class of defect as inventing a figure.
      5. ``full`` is ALWAYS in the returned list. It is the residual and the
         fallback — a legal set that could come back empty is a lane that
         abstains for a FORMATTING reason, which is worse than a mini-essay.
    """
    if str(parent_shape or "") == "sensitive_event":
        return []
    if relationship_only:
        return ["one_line"]

    family = str(family or "")
    out: list[str] = []
    for shape in SHAPE_IDS:
        spec = REPLY_SHAPES[shape]
        if shape == "full":
            out.append(shape)
            continue
        fams = spec.get("families_ok")
        if fams is not None and family not in fams:
            continue
        if "chain" in (spec.get("needs") or ()) and not has_chain:
            continue
        if int(gift_units) > int(spec["max_units"]) - 2:
            continue
        out.append(shape)
    # Canonical order, so the cumulative walk in `_draw` is reproducible from a
    # queue record. `full` is appended above in SHAPE_IDS position, so this is
    # already SHAPE_IDS order; the sort is a pin, not a fix.
    return [s for s in SHAPE_IDS if s in out]


# ---------------------------------------------------------------------------
# 5. The sampler
# ---------------------------------------------------------------------------
def _normalise(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(v)) for v in weights.values())
    if total <= 0.0:
        # EVERY bucket at zero is a real state (the flagship's humor row is
        # 0.00), and it must not divide by zero. Uniform over the legal set is
        # the only answer that does not silently pick one.
        n = max(1, len(weights))
        return {k: 1.0 / n for k in weights}
    return {k: max(0.0, float(v)) / total for k, v in weights.items()}


def _draw(*, account: str, weights: dict[str, float], day_counts: dict[str, int],
          key_parts: tuple[str, ...], salt: str) -> dict[str, Any]:
    """The five-step deficit-weighted stable draw. Shared by both choosers.

    1. legal set = ``weights`` keys (the caller narrows).
    2. target weights, renormalised over the legal set.
    3. realised share so far TODAY, SMOOTHED against the target with
       :data:`DEFICIT_PRIOR_N` pseudo-counts.
    4. deficit ``w + DEFICIT_GAIN * max(0, w - r) + DEFICIT_FLOOR`` — see the
       WHY on those three constants for the arithmetic that put the target
       weight in the base rather than leaving the floor to carry it.
    5. a blake2b roll in [0,1) walked against the cumulative normalised deficit.

    ``_stable_index`` is ``reply_drafter``'s, i.e. blake2b and NOT ``hash()``:
    PYTHONHASHSEED randomises string hashing per interpreter, so a seed-dependent
    selector could never be reproduced from the queue record that claims to
    explain it. A test runs the draw in a separate interpreter under a hostile
    seed.
    """
    from engine.marketing import reply_drafter as _rd  # noqa: PLC0415

    legal = list(weights)
    if not legal:
        return {"value": "", "weights": {}, "deficits": {}, "roll": 0.0,
                "legal": [], "day_counts": dict(day_counts or {}), "source": "empty"}

    w = _normalise(weights)
    counts = {str(k): max(0, int(v or 0)) for k, v in (day_counts or {}).items()}
    seen = sum(counts.values())
    realised = {k: (counts.get(k, 0) + w[k] * DEFICIT_PRIOR_N)
                   / (seen + DEFICIT_PRIOR_N) for k in legal}
    deficits = {k: w[k] + DEFICIT_GAIN * max(0.0, w[k] - realised[k])
                   + DEFICIT_FLOOR for k in legal}
    picks = _normalise(deficits)

    roll = _rd._stable_index(*key_parts, salt) / float(1 << 64)
    acc = 0.0
    value = legal[-1]
    for k in legal:
        acc += picks[k]
        if roll < acc:
            value = k
            break
    return {"value": value, "weights": w, "deficits": deficits,
            "roll": roll, "legal": legal, "day_counts": counts, "source": ""}


def _response_mix(account: str, *, cfg: dict | None,
                  root: Path | str | None) -> tuple[dict[str, float], str]:
    """(weights, source) for *account*, defensively.

    ``persona_model`` is ANOTHER LANE'S MODULE. It is imported lazily and every
    failure — absent module, absent overlay, unreadable YAML — degrades to this
    module's own table. A missing overlay may never crash a draft, and a
    response-mix that silently becomes uniform because an import moved is a mix
    that stopped being the operator's.
    """
    try:
        from engine.marketing import persona_model as _pm  # noqa: PLC0415

        mix = _pm.response_mix(str(account or ""), cfg=cfg, root=root)
        clean = {k: float(mix[k]) for k in RESPONSE_TYPES if k in (mix or {})}
        if clean and sum(clean.values()) > 0:
            return clean, "persona_model"
    except Exception as exc:  # noqa: BLE001
        log.debug("reply_shape: persona_model unavailable (%s); using defaults", exc)

    over = (((cfg or {}).get("reply_desk") or {}).get("response_mix") or {})
    row = (over.get("accounts") or {}).get(str(account or ""))
    if isinstance(row, dict):
        clean = {k: float(row[k]) for k in RESPONSE_TYPES if k in row}
        if clean and sum(clean.values()) > 0:
            return clean, "config"
    table = DEFAULT_RESPONSE_MIX.get(str(account or ""))
    if table:
        return dict(table), "default"
    return dict(DEFAULT_RESPONSE_MIX[MIX_DEFAULT_LANE]), "default_lane"


def choose_response_type(account: str, *, day_counts: dict[str, int],
                         thread_id: str, as_of: str = "",
                         cfg: dict | None = None,
                         root: Path | str | None = None,
                         allowed: list[str] | None = None) -> dict[str, Any]:
    """One response type for this desk and this thread, plus its whole derivation.

    ``allowed`` is the family pool the drafter has already narrowed by
    ``needs_chart`` / ``needs_callback`` / ``dial_floor``. A type whose family set
    is EMPTY after that narrowing is illegal — which is how humor becomes
    unavailable to the flagship and the founder with no second table to maintain:
    ``dry_understatement`` carries ``dial_floor: 2``, the drafter drops it from
    ``allowed`` at reply dial 1, and the type goes with it.
    """
    pool = set(allowed) if allowed is not None else None
    weights, source = _response_mix(account, cfg=cfg, root=root)
    legal: dict[str, float] = {}
    for rtype in RESPONSE_TYPES:
        fams = TYPE_FAMILIES.get(rtype) or frozenset()
        if pool is not None and not (fams & pool):
            continue
        legal[rtype] = float(weights.get(rtype, 0.0))
    if not legal:
        # Every type narrowed away is a real state only when `allowed` is empty,
        # which the drafter never does — but a caller that did must not get a
        # KeyError instead of a draft.
        legal = {"analytical_addition": 1.0}
        source = f"{source}+fallback"
    out = _draw(account=account, weights=legal, day_counts=day_counts,
                key_parts=(str(account), str(as_of), str(thread_id)),
                salt="type")
    out["source"] = source
    return out


def choose_shape(account: str, *, response_type: str, family: str,
                 parent_shape: str | None, thread_id: str,
                 day_counts: dict[str, int], has_chain: bool, gift_units: int,
                 as_of: str = "", tier: str | None = None,
                 relationship_only: bool = False) -> dict[str, Any]:
    """One shape for this draft, plus its whole derivation.

    The prior is a property of the TYPE (:data:`TYPE_SHAPE_PRIOR`); the persona
    skew lives entirely in the type weights. ``tier`` is the §E relationship
    familiarity: someone you talk to often gets the texting rhythm more often,
    which is the operator's own contrast made mechanical rather than asserted.

    ``salt="shape"`` makes this draw INDEPENDENT of the type draw on the same
    key — one hash feeding both would correlate them and a correlated pair is a
    two-column cycle wearing a random hat.
    """
    legal_shapes = shapes_for(family=family, parent_shape=parent_shape,
                              response_type=response_type, has_chain=has_chain,
                              gift_units=gift_units,
                              relationship_only=relationship_only)
    prior = TYPE_SHAPE_PRIOR.get(str(response_type)) or {}
    # A shape legal by FAMILY but carrying no prior for this TYPE is out: leaving
    # it in at deficit-floor weight leaks `addition` into humor at ~4% and quietly
    # dilutes exactly the distribution this build exists to hit. `full` is the one
    # exception, always present (shapes_for gate 5), so the set is never empty.
    weights = {s: float(prior.get(s, 0.0)) for s in legal_shapes
               if s in prior or s == "full"}
    if not weights:
        weights = {"full": 1.0}

    weights = _tier_bend(weights, tier)
    out = _draw(account=account, weights=weights, day_counts=day_counts,
                key_parts=(str(account), str(as_of), str(thread_id), str(family)),
                salt="shape")
    out["source"] = f"type_prior:{response_type}"
    return out


#: §E.4: what a familiarity tier changes about the SHAPE prior. A regular gets
#: the short forms more often because that is what people who talk often actually
#: write to each other; a stranger's prior is untouched. Multiplicative and then
#: renormalised, so a tier bends the odds and never pins a shape.
TIER_SHAPE_BOOST: dict[str, dict[str, float]] = {
    "familiar": {"fragment_exchange": 1.4},
    "regular": {"one_line": 1.4, "fragment_exchange": 1.4},
}


def _tier_bend(weights: dict[str, float], tier: str | None) -> dict[str, float]:
    boost = TIER_SHAPE_BOOST.get(str(tier or ""))
    if not boost:
        return weights
    return {k: v * float(boost.get(k, 1.0)) for k, v in weights.items()}


# ---------------------------------------------------------------------------
# 6. The renderers
# ---------------------------------------------------------------------------
def _units(text: str) -> int:
    from engine.marketing import reply_critics as _rc  # noqa: PLC0415

    return _rc._content_units(text)


def _sentence_count(text: str) -> int:
    from engine.marketing import reply_critics as _rc  # noqa: PLC0415

    return len(_rc._sentences(text))


def _register_marker_ok(text: str, account: str,
                        root: Path | str | None) -> bool:
    """Would W1 (``warmth_register``'s cold-printout kill) pass this text?

    RUN AT BUILD TIME, for exactly the reason ``_opening_sentence_is_legal``
    already runs W3 at build time one module over: a shape the critics will kill
    a moment later is an abstention the reader never sees and the operator cannot
    diagnose. Measured on the §A.5 copy: six of the twelve employee ``addition``
    heads ("Right, with one thing added:", "yep. the part nobody adds:", ...)
    carry no ``warmth_markers``-visible phrase, so head + a markerless gift lands
    at 18-20 content units with zero register and W1 rejects it. Rather than edit
    operator-facing register copy, the DRAW is narrowed to the marker-carrying
    entries whenever the body needs one — see :func:`_draw_copy`.
    """
    from engine.marketing import reply_critics as _rc  # noqa: PLC0415
    from engine.marketing import reply_drafter as _rd  # noqa: PLC0415

    if _rd._reply_dial(account, root) < 2:
        return True                       # flagship/founder: W1 is inert by dial
    if _rc.warmth_markers(text, {"account": account, "root": root}):
        return True
    bar = int(_rc.DEFAULT_THRESHOLDS.get("warmth_min_units", 12))
    return _units(text) < bar


def _elements_ok(text: str, *, account: str, shape: str, ctx: dict,
                 root: Path | str | None) -> bool:
    """Would the two-of-five engagement floor pass this text? (XG-W4b §D)

    RUN AT BUILD TIME FOR THE SAME REASON W1 AND W3 ARE. ``reply_elements``
    requires at least two of {a specific reference to the post, a clear opinion,
    a reason, a conversational marker, a question or opening}, and a SHORT shape
    is where that floor actually bites: ``one_line`` carrying nothing but the
    gift is a competent summary, which is the operator's named failure mode
    ("humans have a SPECIFIC REACTION, not a competent summary"). Checking here
    turns "the desk drafted a one-liner and then silently abstained at the gate"
    into "the desk drafted a fragment exchange instead", because the closers and
    heads carry the marker the bare gift does not.

    FAILS OPEN on an absent or broken critic — deliberately, and it is the only
    fail-open in this module. ``reply_elements`` lands in a different lane; a
    shape layer that refused every render because a sibling module was
    mid-edit would be an outage caused by a check, and the critic still runs
    downstream on whatever ships. The DOWNSTREAM gate is the enforcement; this
    is supply-side steering.
    """
    try:
        from engine.marketing import reply_critics as _rc  # noqa: PLC0415

        critic = getattr(_rc, "reply_elements", None)
        if critic is None:
            return True
        verdict = critic(text, {
            "account": account, "root": root, "shape": shape,
            "parent_text": str(ctx.get("parent_text") or ""),
            "warmth": ctx.get("warmth"),
            "relationship_only": bool(ctx.get("relationship_only")),
            "numbers_whitelist": list(ctx.get("numbers_whitelist") or []),
            "corpus": [], "cfg": ctx.get("cfg"),
        })
        return not (verdict or {}).get("reasons")
    except Exception as exc:  # noqa: BLE001
        log.debug("reply_shape: element floor unavailable (%s)", exc)
        return True


def _draw_copy(pool: list[str], *, account: str, family: str, shape: str,
               thread_id: str, recent: list[str] | None) -> str:
    """One entry from *pool*, by the SAME stable-hash + LRU selector tails use.

    Deliberately ``reply_drafter.pick_from_pool``: a second selector is a second
    set of rotation semantics to keep in step, and the tail build already paid
    for that lesson once with two caches.
    """
    from engine.marketing import reply_drafter as _rd  # noqa: PLC0415

    return _rd.pick_from_pool(
        pool, key_parts=(str(account), str(shape), str(family), str(thread_id)),
        recent=recent)


def _budget_ok(text: str, spec: dict[str, Any]) -> bool:
    if not text:
        return False
    if _units(text) > int(spec["max_units"]):
        return False
    if len(text) > int(spec["max_chars"]):
        return False
    max_sent = int(spec.get("max_sentences") or 0)
    return not (max_sent and _sentence_count(text) > max_sent)


def render(shape: str, *, gift: str, ctx: dict | None = None, family: str = "",
           warmth: str | None = None, tail: str = "", account: str = "",
           root: Path | str | None = None,
           components: dict | None = None) -> str:
    """Build one shaped draft. ``""`` when the shape cannot be rendered.

    An empty return is the documented REFUSAL and the caller falls to the next
    legal shape (``reply_drafter.draft_reply`` walks the sampler's ordered legal
    set and ends on ``full``, which is always legal). NEVER TRUNCATES: a reply
    clipped to fit a budget has lost its verb, and a half sentence under a real
    woman's byline is worse than a mini-essay.

    ``components``, when given, receives ``warmth_dropped`` ("" or "shape") and
    ``shape_copy`` (the head or closer template drawn), so ``draft_reply`` can
    report WHY a warmth move it selected is not in the copy. A silent drop is how
    a rotation history comes to record a move that never shipped.

    ``shape="full"`` delegates straight back to ``reply_drafter.compose`` and is
    byte-identical to it: the parity gate is what stops the shape build from
    regressing the shipped path, so there is exactly one implementation of it.
    """
    from engine.marketing import reply_drafter as _rd  # noqa: PLC0415

    ctx = dict(ctx or {})
    account = str(account or ctx.get("account") or "")
    root = root if root is not None else ctx.get("root")
    parts = components if components is not None else {}
    parts.setdefault("warmth_dropped", "")
    parts.setdefault("shape_copy", "")

    shape = str(shape or "full")
    if shape == "full":
        return _rd.compose(family, gift, ctx, warmth=warmth, shape="full")
    spec = REPLY_SHAPES.get(shape)
    if spec is None:
        return ""

    gift = _rd._clean(gift)
    if not gift.strip() and shape != "compact_chain":
        return ""

    thread_id = str(ctx.get("thread_id") or "")
    move = _rd.WARMTH_MOVES.get(str(warmth)) if warmth else None
    opener = _rd._resolve_opener(move, {**ctx, "account": account, "root": root}) if move else ""
    fuse = str((move or {}).get("fuse") or "standalone")

    def _with_warmth(body: str, *, conjunction_only: bool) -> tuple[str, bool]:
        """(text, warmth_used). Drops the opener rather than the shape."""
        if not opener:
            return body, False
        if conjunction_only and fuse != "conjunction":
            # A colon join manufactures a second clause and blows a one-sentence
            # budget. Drop the WARMTH, keep the shape: the alternative loses the
            # short reply entirely, which is the thing this build exists to add.
            return body, False
        try:
            return _rd.fuse_warmth(opener, body, fuse=fuse), True
        except ValueError as exc:
            log.warning("reply_shape: opener rejected for %r/%r: %s",
                        account, shape, exc)
            return body, False

    if shape == "one_line":
        body, used = _with_warmth(gift, conjunction_only=True)
    elif shape == "fragment_exchange":
        pool = closers_for(account, shape, root)
        if not pool:
            return ""
        closer = _draw_copy(pool, account=account, family=family, shape=shape,
                            thread_id=thread_id,
                            recent=list(ctx.get("recent_shape_copy") or []))
        head_text, used = _with_warmth(gift, conjunction_only=False)
        if not _register_marker_ok(f"{head_text} {closer}", account, root):
            marked = [c for c in pool
                      if _register_marker_ok(f"{head_text} {c}", account, root)]
            if not marked:
                return ""
            closer = _draw_copy(marked, account=account, family=family,
                                shape=shape, thread_id=thread_id,
                                recent=list(ctx.get("recent_shape_copy") or []))
        parts["shape_copy"] = closer
        body = f"{head_text} {closer}"
    elif shape == "addition":
        pool = heads_for(account, shape, root)
        if not pool:
            return ""
        head = _draw_copy(pool, account=account, family=family, shape=shape,
                          thread_id=thread_id,
                          recent=list(ctx.get("recent_shape_copy") or []))
        if not _register_marker_ok(f"{head} {gift}", account, root):
            marked = [h for h in pool
                      if _register_marker_ok(f"{h} {gift}", account, root)]
            if not marked:
                return ""
            head = _draw_copy(marked, account=account, family=family, shape=shape,
                              thread_id=thread_id,
                              recent=list(ctx.get("recent_shape_copy") or []))
        parts["shape_copy"] = head
        # THE HEAD REPLACES THE FAMILY'S CANNED PREAMBLE, it is never stacked on
        # top of it: "Agreed, with one addition." in front of "Agreed. One
        # addition:" is the two-acknowledgements theatre `concede_and_hold.
        # wrong_when` already warns about. The shaped renderer builds from the
        # GIFT and never runs the family branch, so the preamble is stripped by
        # construction rather than by a startswith() that a new frame could miss.
        #
        # Warmth is dropped here for the same reason: the head IS the
        # acknowledgement, and a warmth opener in front of it is the same stack.
        used = False
        body = f"{head} {gift}"
    elif shape == "compact_chain":
        links = [str(x).strip().rstrip(".") for x in (ctx.get("chain") or [])
                 if str(x).strip()]
        if not (CHAIN_MIN_LINKS <= len(links) <= CHAIN_MAX_LINKS):
            return ""
        body, used = _with_warmth(
            CHAIN_CONNECTOR.join(links) + ".", conjunction_only=True)
    else:
        return ""

    if move is not None and opener and not used:
        parts["warmth_dropped"] = "shape"

    stamp = str(ctx.get("as_of_stamp") or "").strip()
    if stamp:
        body = f"{body} ({stamp})"
    body = _rd._clean(body)

    if not _budget_ok(body, spec):
        return ""
    if not _register_marker_ok(body, account, root):
        return ""
    if not _elements_ok(body, account=account, shape=shape, ctx=ctx, root=root):
        return ""
    return body


# ---------------------------------------------------------------------------
# 7. The measurement window
# ---------------------------------------------------------------------------
def _target_shape_mix(account: str, *, cfg: dict | None = None,
                      root: Path | str | None = None) -> dict[str, float]:
    """Expected shape shares for *account* under its own type weights.

    Computed from the tables rather than stored, so a re-weighting of either
    table moves the target the report grades against in the same commit. This is
    the NOMINAL prior (no deficit floor, no chain availability, no tier bend), so
    a realised share a few points off it is normal — it is a reference line, not
    a gate. The only gate is :data:`MIX_FULL_ALARM`.
    """
    weights, _ = _response_mix(account, cfg=cfg, root=root)
    weights = _normalise(weights)
    out = {s: 0.0 for s in SHAPE_IDS}
    for rtype, w in weights.items():
        for shape, share in (TYPE_SHAPE_PRIOR.get(rtype) or {}).items():
            out[shape] = out.get(shape, 0.0) + w * share
    return out


def shape_mix(rows: list[dict], *, window_days: int = MIX_WINDOW_DAYS,
              cfg: dict | None = None, root: Path | str | None = None,
              today: str = "") -> dict[str, Any]:
    """Realised-vs-target shape mix for ONE account's queue rows.

    ``rows`` are ``reply_queue`` items (``as_of``, ``account``, ``shape``). The
    caller filters to one account; the account is read back off the rows so a
    mis-filtered call is visible in the report rather than averaged away.

    BELOW :data:`MIX_MIN_ITEMS` THE SHARES ARE REPORTED AND NOT GRADED
    (``graded: False``, with the ``n``). Printing a share off six items is the
    vacuous-N trap, and a desk-health report that grades noise trains an operator
    to ignore it.

    Emits the drift annotation as a BARE LINE-START print — a logger call would
    emit "WARNING ::warning ..." and GitHub would drop it silently, so the alarm
    would review as armed while producing nothing (house law, five occurrences).
    """
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    account = ""
    for row in rows:
        account = str(row.get("account") or "")
        if account:
            break

    cutoff = ""
    if window_days and window_days > 0:
        try:
            end = date.fromisoformat(today) if today else max(
                (date.fromisoformat(str(r.get("as_of"))) for r in rows
                 if str(r.get("as_of") or "")), default=None)
            if end is not None:
                cutoff = (end - timedelta(days=int(window_days) - 1)).isoformat()
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_shape.shape_mix: unreadable as_of (%s)", exc)
            cutoff = ""

    window = [r for r in rows
              if not cutoff or str(r.get("as_of") or "") >= cutoff]
    counts: dict[str, int] = {}
    for row in window:
        shape = str(row.get("shape") or "")
        if shape:
            counts[shape] = counts.get(shape, 0) + 1
    n = sum(counts.values())
    realised = {s: (counts.get(s, 0) / n if n else 0.0) for s in SHAPE_IDS}
    target = _target_shape_mix(account, cfg=cfg, root=root)
    drift = {s: round(realised[s] - target.get(s, 0.0), 4) for s in SHAPE_IDS}
    graded = n >= MIX_MIN_ITEMS

    if graded and realised.get("full", 0.0) > MIX_FULL_ALARM:
        print(f"::warning title=reply_shape_mix_drift::{account} {window_days}d "
              f"shape mix: full {realised['full']:.2f} against target "
              f"{target.get('full', 0.0):.2f} over {n} items — the mini-essay "
              f"default is back", flush=True)

    return {"account": account, "n": n, "window_days": int(window_days),
            "graded": graded, "counts": counts,
            "realised": {s: round(v, 4) for s, v in realised.items()},
            "target": {s: round(v, 4) for s, v in target.items()},
            "drift": drift}


__all__ = [
    "REPLY_SHAPES", "SHAPE_IDS", "SHORT_FORM_SHAPES", "CHAIN_CONNECTOR",
    "CHAIN_MIN_LINKS", "CHAIN_MAX_LINKS",
    "RESPONSE_TYPES", "TYPE_FAMILIES", "TYPE_SHAPE_PRIOR",
    "DEFAULT_RESPONSE_MIX", "MIX_DEFAULT_LANE", "SHAPE_HEADS", "SHAPE_TAILS",
    "DEFICIT_FLOOR", "MIX_WINDOW_DAYS", "MIX_MIN_ITEMS", "MIX_FULL_ALARM",
    "TIER_SHAPE_BOOST",
    "shape_ids", "shapes_for", "choose_response_type", "choose_shape", "render",
    "heads_for", "closers_for", "shape_mix", "clear_shape_cache",
]
