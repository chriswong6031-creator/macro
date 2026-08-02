"""engine/marketing/persona_model.py — the persona INTERNAL MODEL overlay (XG-W4b §E).

The operator's brief asks each desk to carry "an actual internal model,
persistent": core beliefs, expertise, common uncertainties, topics it
challenges, typical sentence length, humor level, confidence level, vocabulary
preferences, permitted real experiences, previous opinions, people it already
interacts with, and — the field that matters most — A RELATIONSHIP TONE PER
ACCOUNT, because humans do not reply identically to everyone.

**Seven of those twelve already exist and are NOT duplicated here.** Duplicating
a field is how two sources of truth drift, so:

    worldview / franchises / beat / context_packs   the FROZEN persona spec layer
    previous opinions                                data/marketing/personas/<id>/theses.jsonl
    people we interact with                          data/marketing/personas/<id>/relations.jsonl
    humor level                                      config/marketing.yml reply_desk.response_mix

and this module owns only the five that had no home: `beliefs`, `expertise`,
`uncertainties`, `challenges`, `confidence`, plus the `lexicon` preference layer
and the per-tier `relationship_tone` copy pools.

THE FENCE (tests/test_marketing_personas.py::test_no_generation_module_reads_a_
persona_spec).  This module is NOT an allowed reader of the frozen spec layer
and must never become one. Persona attributes reach generation through
`expression_dial` (dial, zh, violations, am_r1_hits) and nothing else. The
overlay below is an ADDITIONAL, non-frozen layer beside that seam — never a
replacement, and deliberately never a second ban list: `lexicon.avoid` is
ADVISORY and may not reject a draft. A second ban list is how the fence gets
re-litigated one word at a time.

The overlay store lives at ``config/marketing/persona_models/<id>.yml``. Three
homes were considered and two rejected, on the record:

  * ``data/marketing/personas/<id>/`` is a MACHINE LEDGER whose sole code writer
    is `persona_memory.consolidate()`, enforced by an AST guard. A hand-authored
    document in there muddies an invariant that is currently crisp.
  * ``config/marketing.yml`` is right for the numeric dials (which is where
    `response_mix` lives) and wrong for four per-persona documents: one file
    every lane edits is a merge-conflict generator.

The chosen home also carries no fence risk under ANY spelling — its literal is
``persona_models``, never the quoted token the spec-reference detector matches.

**PERMITTED REAL EXPERIENCE IS THE HIGHEST-RISK FIELD IN THE BRIEF AND THE
HONEST ANSWER IS NONE.**  `permitted_experience` exists, is always empty, and
`load_model` RAISES on a non-empty value. Every lifestyle canon marker on all
four employee specs ships disabled pending that real employee's own
confirmation, and AM-R1 binds hardest on real named humans. The field exists so
that licensing one experience is a deliberate, reviewable act with an error
message telling the operator what else has to change — not a YAML edit nobody
reviews.

Public API (XG-W4b §F.1):
    FAMILIARITY_TIERS / MODEL_SCHEMA / RESPONSE_TYPES / DEFAULT_RESPONSE_MIX
    Confidence / Lexicon / PersonaModel
    load_model(account, *, root=None) -> PersonaModel
    clear_model_cache() -> None
    familiarity(account, handle, *, relations=None, now=None, root=None) -> str
    tone_prefixes(account, tier, *, parent_text="", relations_row=None,
                  now=None, root=None) -> list[str]
    response_mix(account, *, cfg=None, root=None) -> dict[str, float]
    tier_policy(tier, *, declined=False) -> dict     (the §E.4 draft-side table)
    is_declined(relations_row) -> bool
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger(__name__)

__all__ = [
    "MODEL_SCHEMA",
    "FAMILIARITY_TIERS",
    "RESPONSE_TYPES",
    "DEFAULT_RESPONSE_MIX",
    "TIER_WARMTH_MOVES",
    "TIER_BLOCKED_FAMILIES",
    "TIER_SHAPE_BOOST",
    "RECENCY_DEMOTE_DAYS",
    "TONE_PREFIX_MAX_AGE_DAYS",
    "HEDGE_RATE_CEILING",
    "Confidence",
    "Lexicon",
    "PersonaModel",
    "model_path",
    "load_model",
    "clear_model_cache",
    "familiarity",
    "tone_prefixes",
    "response_mix",
    "tier_policy",
    "is_declined",
]

MODEL_SCHEMA = "marketing.persona_model/v1"

#: The relationship ladder, coldest first. A closed vocabulary for the same
#: reason `persona_memory.RELATION_STAGES` is one: "how well do we know this
#: person" is the only judgment this layer holds, and a free-text tier would be
#: an invitation to infer something about them.
FAMILIARITY_TIERS: tuple[str, ...] = ("stranger", "acquainted", "familiar", "regular")

#: Six response types, from the operator's seven (§B.1: "personal
#: interpretation" and "compact explanation" are VOICES of the analytical
#: bucket, not separate quotas).
RESPONSE_TYPES: tuple[str, ...] = (
    "short_reaction", "analytical_addition", "agreement_nuance",
    "disagreement", "question", "humor",
)

#: Per-persona response-type weights (XG-W4b §B.3), overridable at
#: ``config/marketing.yml`` -> ``reply_desk.response_mix.accounts.<id>``.
#:
#: CODE DEFAULTS EXIST SO A MISSING CONFIG NEVER DISARMS THE MIX — the same
#: posture as `reply_queue.PACING_DEFAULTS`. A distribution that silently
#: flattens to uniform when a key is absent is a distribution nobody can trust.
#:
#: Each row sums to 1.00 and NO TWO EMPLOYEE DESKS SHARE A ROW, which is the
#: operator's "percentages should vary by persona" requirement. The four-employee
#: MEAN is 0.30 / 0.265 / 0.16 / 0.135 / 0.08 / 0.06 against the operator's
#: 30/25/15/15/10/5, so the fleet mix is preserved while no single desk is the
#: fleet.
#:
#: THE WORST BUCKET IS TWO POINTS, NOT ONE AND A HALF, and the correction is
#: recorded rather than rounded away: five buckets land inside a point and a
#: half, and `question` does not — 0.08/0.06/0.08/0.10 averages 0.08 against a
#: 0.10 target. It is the one bucket where every desk's own codex pulls the
#: same direction (sophia's "sparing questions", kelly's "pointed questions
#: only when answerable"), so closing it would mean overriding four derivations
#: to hit a round number. `tests/test_marketing_persona_model.py` pins the exact
#: mean per bucket, so a future row edit has to restate the fleet consequence.
#:
#: Every row is DERIVED from that desk's own pinned codex, so a re-weighting
#: argues from the record rather than from taste:
#:   kelly  — "terse, analytical, fragments when they sharpen rhythm" -> highest
#:            short share; "chart detective" + "what would prove this wrong"
#:            -> highest disagreement; "internet-native dry wit" -> highest humor.
#:   sophia — the ONLY codex on the roster that licenses length ("may run
#:            slightly longer when the narrative needs room") -> highest
#:            analytical, lowest short; "sparing questions" -> lowest questions.
#:   cici   — "polite corrections" means her disagreement is EXPRESSED as
#:            agreement-plus-correction -> highest agreement, lowest raw
#:            disagreement; her lawful humor surface is the narrowest -> lowest.
#:   meagan — "opens on a human reaction", "upbeat, quick, human" -> highest
#:            short; "one playful line followed by one useful line" -> highest
#:            humor; crowd translation, not mechanism dispute -> lowest disagree.
#:   flagship — §5 register map: terse verdict, Never column "anything warm".
#:            Agreement is a warmth act -> 0.05. Humor is unavailable to it by
#:            family dial floor -> 0.00, and the renormaliser must survive a
#:            zero-weight bucket without dividing by zero.
DEFAULT_RESPONSE_MIX: dict[str, dict[str, float]] = {
    "kelly":    {"short_reaction": 0.34, "analytical_addition": 0.24,
                 "agreement_nuance": 0.10, "disagreement": 0.18,
                 "question": 0.08, "humor": 0.06},
    "sophia":   {"short_reaction": 0.22, "analytical_addition": 0.34,
                 "agreement_nuance": 0.18, "disagreement": 0.14,
                 "question": 0.06, "humor": 0.06},
    "cici":     {"short_reaction": 0.28, "analytical_addition": 0.28,
                 "agreement_nuance": 0.20, "disagreement": 0.12,
                 "question": 0.08, "humor": 0.04},
    "meagan":   {"short_reaction": 0.36, "analytical_addition": 0.20,
                 "agreement_nuance": 0.16, "disagreement": 0.10,
                 "question": 0.10, "humor": 0.08},
    "flagship": {"short_reaction": 0.30, "analytical_addition": 0.45,
                 "agreement_nuance": 0.05, "disagreement": 0.12,
                 "question": 0.08, "humor": 0.00},
    "founder":  {"short_reaction": 0.34, "analytical_addition": 0.34,
                 "agreement_nuance": 0.10, "disagreement": 0.12,
                 "question": 0.10, "humor": 0.00},
    "_default": {"short_reaction": 0.30, "analytical_addition": 0.25,
                 "agreement_nuance": 0.15, "disagreement": 0.15,
                 "question": 0.10, "humor": 0.05},
}

#: A "regular" we have not spoken to in three months is a "familiar", and
#: pretending otherwise is the same class of claim as inventing a memory.
RECENCY_DEMOTE_DAYS: int = 60

#: A tone prefix is a claim about a SHARED RECENT PAST. Fourteen days is the
#: window inside which "you flagged this one already" is checkable from our own
#: store rather than asserted.
TONE_PREFIX_MAX_AGE_DAYS: int = 14

#: The critic's rolling uncertainty-marker ceiling (§C.1 R2). Every persona's
#: supply-side `confidence.hedge_rate` must sit STRICTLY under it — a drafter
#: target set above the gate that judges it is a lane that rejects its own
#: intended output. `load_model` raises rather than clamping, because a clamp
#: would let the YAML keep lying about what the desk is aiming for.
HEDGE_RATE_CEILING: float = 0.30

# ---------------------------------------------------------------------------
# §E.4 — what changes in the DRAFT at each familiarity tier
# ---------------------------------------------------------------------------
#: Warmth moves available at each tier, CUMULATIVE up the ladder. The drafter
#: lane intersects this with `reply_drafter.warmth_moves_for(...)`; this table
#: never widens that pool, it only narrows it, so every existing fitness gate
#: (parent shape, family, dial floor, needs_thesis/needs_detail, the persona's
#: own guard sweep) still binds first.
#:
#: `quiet_sympathy` is present at EVERY tier on purpose and is not part of the
#: familiarity ladder at all: it is `relationship_only`, shape-gated to a
#: personal setback, and it is the one reply that is not a growth reply. A
#: curated relationship-tier author we have never interacted with is a
#: `stranger` HERE (relations.jsonl is empty at M0) while being exactly the
#: person whose bad week deserves the sympathy line — withholding it on a
#: familiarity technicality would be the wrong failure.
TIER_WARMTH_MOVES: dict[str, tuple[str, ...]] = {
    # Impersonal only. Nothing here claims a shared past or a shared joke.
    "stranger": ("verdict_first", "concrete_image", "open_curiosity",
                 "quiet_sympathy"),
    # Crediting a specific detail and conceding a point both presume we read
    # them before; neither presumes we know them.
    "acquainted": ("verdict_first", "concrete_image", "open_curiosity",
                   "quiet_sympathy", "specific_credit", "concede_and_hold"),
    # A wry aside at a shared frustration needs a shared frustration.
    "familiar": ("verdict_first", "concrete_image", "open_curiosity",
                 "quiet_sympathy", "specific_credit", "concede_and_hold",
                 "wry_solidarity"),
    # You admit you were wrong to people you know. `flat_confession` also needs
    # a real thesis (`needs_thesis` fails closed upstream), so this widens the
    # tier gate and never the evidence gate.
    "regular": ("verdict_first", "concrete_image", "open_curiosity",
                "quiet_sympathy", "specific_credit", "concede_and_hold",
                "wry_solidarity", "flat_confession"),
}

#: `callback` reaches back to a position WE took in front of THIS author. To a
#: stranger that is a stranger quoting himself; from `familiar` up it is a
#: thread being picked up. The family stays gated on a matching thesis upstream.
TIER_BLOCKED_FAMILIES: dict[str, frozenset[str]] = {
    "stranger": frozenset({"callback"}),
    "acquainted": frozenset({"callback"}),
    "familiar": frozenset(),
    "regular": frozenset(),
}

#: Multiplicative shape-prior nudges (§E.4). Texting rhythm is what talking to
#: someone you know looks like; the sampler renormalises after applying these,
#: so a boost bends the odds and never pins a shape.
TIER_SHAPE_BOOST: dict[str, dict[str, float]] = {
    "stranger": {},
    "acquainted": {},
    "familiar": {"fragment_exchange": 1.4},
    "regular": {"one_line": 1.4, "fragment_exchange": 1.4},
}


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Confidence:
    """How sure this desk sounds, and how long its sentences run.

    `hedge_rate` is the DRAFTER's target share of replies carrying ONE
    uncertainty marker; §C.1 R2's `hedge_share_cap` is the CRITIC's ceiling.
    The first must sit under the second or the desk aims at its own gate.
    """

    hedge_rate: float = 0.08
    unhedged_verdict_ok: bool = True
    sentence_units_p50: int = 11
    sentence_units_p90: int = 22


@dataclass(frozen=True)
class Lexicon:
    """Vocabulary PREFERENCES. `avoid` is advisory and may never reject.

    The BANS live in the frozen `voice_codex.banned` and are enforced by
    `expression_dial`. This layer de-prioritises copy selection before the gate
    ever has to fire; a test pins that a draft carrying every `avoid` token
    still clears every critic, because the moment `avoid` can reject, this file
    has become a second ban list outside the adjudicated seam.
    """

    prefer: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class PersonaModel:
    account: str
    beliefs: tuple[str, ...] = ()
    expertise: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    challenges: tuple[str, ...] = ()
    confidence: Confidence = Confidence()
    lexicon: Lexicon = Lexicon()
    relationship_tone: dict[str, tuple[str, ...]] = field(default_factory=dict)
    permitted_experience: tuple[()] = ()
    source: str = "default"

    def tone_pool(self, tier: str) -> tuple[str, ...]:
        """The raw (unswept) tone pool for *tier*. () for an unknown tier."""
        return tuple(self.relationship_tone.get(str(tier)) or ())


_DEFAULT_MODEL_CACHE: dict[tuple[str, str], PersonaModel] = {}


def model_path(account: str, root: Path | str | None = None) -> Path:
    """Where *account*'s overlay lives.

    The directory literal is ``persona_models`` — deliberately not the token the
    spec-reference guard matches, so this path cannot trip the fence under any
    spelling, including inside a comment or an annotation string.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent
    return base / "config" / "marketing" / "persona_models" / f"{str(account).strip()}.yml"


def clear_model_cache() -> None:
    """Drop the per-(root, account) cache.

    Tests that write overlays into a tmp root call this. Kept as ONE cache with
    ONE clear, because the warmth build's own postmortem is a second cache that
    kept answering after the first was dropped.
    """
    _DEFAULT_MODEL_CACHE.clear()


def _as_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (str(value),)
    if isinstance(value, Sequence):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return ()


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def load_model(account: str, *, root: Path | str | None = None) -> PersonaModel:
    """This desk's internal model. NEVER raises on absence.

    An account with no overlay gets ``source="default"``: empty tuples, a
    conservative `hedge_rate` of 0.08, and NO relationship tone at any tier.
    That absence is the enforcement, not an oversight — the flagship and the
    founder are evidence desks whose register map lists "anything warm" in the
    Never column, so "an evidence desk does not do familiarity" is expressed by
    having no pool to draw from rather than by yet another exclusion table.

    RAISES ValueError on two things, both deliberate:

      * a non-empty ``permitted_experience`` — see the module docstring. The
        message names what else an operator must change, because a raise an
        operator cannot act on is a raise that gets deleted.
      * a ``confidence.hedge_rate`` at or above the critic's ceiling — a
        supply-side target above the gate that judges it would make the desk
        aim at its own rejection.
    """
    acct = str(account or "").strip()
    key = (str(root or ""), acct)
    cached = _DEFAULT_MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    raw: dict[str, Any] = {}
    path = model_path(acct, root)
    if acct and path.exists():
        try:
            import yaml  # noqa: PLC0415

            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            raw = loaded if isinstance(loaded, dict) else {}
        except Exception as exc:  # noqa: BLE001
            # A model we cannot parse is not a model that loaded. Fall to the
            # default rather than half-applying a broken file: a partially read
            # overlay would give the desk half a personality and no warning.
            print(f"::warning title=persona_model_unreadable::{acct}: "
                  f"{path.name} could not be parsed ({exc}) — this desk falls "
                  f"back to the default model with no relationship tone",
                  flush=True)
            raw = {}

    if raw:
        schema = str(raw.get("schema") or "")
        if schema and schema != MODEL_SCHEMA:
            print(f"::warning title=persona_model_schema::{acct}: overlay "
                  f"declares schema {schema!r}, expected {MODEL_SCHEMA!r} — "
                  f"loading it anyway, but a shape change must be visible",
                  flush=True)

    permitted = _as_tuple(raw.get("permitted_experience"))
    if permitted:
        raise ValueError(
            f"{acct}: persona_model.permitted_experience is non-empty "
            f"({list(permitted)!r}) and it MUST stay empty. Licensing a real "
            "experience for a real named employee is a two-file, reviewable "
            "act: the desk's own frozen persona spec carries the lifestyle "
            "canon markers and every one of them ships disabled pending that "
            "employee's confirmation (AM-R1 binds hardest on real humans), and "
            "only then may this field name what the desk may mention. Editing "
            "this YAML alone licenses nothing.")

    conf_raw = raw.get("confidence") if isinstance(raw.get("confidence"), dict) else {}
    confidence = Confidence(
        hedge_rate=_as_float(conf_raw.get("hedge_rate"), 0.08),
        unhedged_verdict_ok=bool(conf_raw.get("unhedged_verdict_ok", True)),
        sentence_units_p50=_as_int(conf_raw.get("sentence_units_p50"), 11),
        sentence_units_p90=_as_int(conf_raw.get("sentence_units_p90"), 22),
    )
    if confidence.hedge_rate >= HEDGE_RATE_CEILING:
        raise ValueError(
            f"{acct}: confidence.hedge_rate={confidence.hedge_rate} is at or "
            f"above the critic's rolling ceiling ({HEDGE_RATE_CEILING}). The "
            "drafter's target must sit STRICTLY under the gate that judges it, "
            "or the desk is aiming at replies register_discipline will reject.")

    lex_raw = raw.get("lexicon") if isinstance(raw.get("lexicon"), dict) else {}
    tone_raw = raw.get("relationship_tone")
    tone: dict[str, tuple[str, ...]] = {}
    if isinstance(tone_raw, dict):
        for tier in FAMILIARITY_TIERS:
            pool = _as_tuple(tone_raw.get(tier))
            if pool:
                tone[tier] = pool
        unknown = sorted(set(map(str, tone_raw)) - set(FAMILIARITY_TIERS))
        if unknown:
            print(f"::warning title=persona_model_tier::{acct}: "
                  f"relationship_tone names unknown tier(s) {unknown} — "
                  f"ignored; the ladder is {list(FAMILIARITY_TIERS)}",
                  flush=True)

    model = PersonaModel(
        account=acct,
        beliefs=_as_tuple(raw.get("beliefs")),
        expertise=tuple(t.lower() for t in _as_tuple(raw.get("expertise"))),
        uncertainties=_as_tuple(raw.get("uncertainties")),
        challenges=_as_tuple(raw.get("challenges")),
        confidence=confidence,
        lexicon=Lexicon(prefer=_as_tuple(lex_raw.get("prefer")),
                        avoid=_as_tuple(lex_raw.get("avoid"))),
        relationship_tone=tone,
        permitted_experience=(),
        source=("model.yml" if raw else "default"),
    )
    _DEFAULT_MODEL_CACHE[key] = model
    return model


# ---------------------------------------------------------------------------
# Familiarity — the tier ladder over relations.jsonl
# ---------------------------------------------------------------------------
def is_declined(relations_row: dict | None) -> bool:
    """Did this author decline engagement?

    A SAFETY PREDICATE, not a tone one. Someone who declined gets our most
    neutral register and no warmth move at all, and that has to be readable on
    its own rather than inferred from a tier — `familiarity` maps a decline to
    `stranger`, and a stranger is not the same thing as someone who told us to
    stop.
    """
    if not isinstance(relations_row, dict):
        return False
    return str(relations_row.get("stage") or "").strip().lower() == "declined"


def _parse_contact(value: object) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _demote(tier: str) -> str:
    idx = FAMILIARITY_TIERS.index(tier) if tier in FAMILIARITY_TIERS else 0
    return FAMILIARITY_TIERS[max(0, idx - 1)]


def familiarity(
    account: str,
    handle: str,
    *,
    relations: dict[str, dict] | None = None,
    now: datetime | None = None,
    root: Path | str | None = None,
) -> str:
    """How well this desk knows *handle*. A `FAMILIARITY_TIERS` member.

    Derived deterministically from the persona's own relation ledger and from
    nothing else — no inference about the person, which is the constitution's
    relationship-memory law. The ladder, in order:

      1. `declined` -> `stranger`, and the caller must also suppress warmth
         (`is_declined`). Someone who declined engagement gets our most neutral
         register; that is a safety property, not a tone choice.
      2. no row, or zero touches -> `stranger`.
      3. eight touches, or a `reciprocal` stage -> `regular`.
      4. three touches AND an `engaged` stage -> `familiar`.
      5. otherwise -> `acquainted`.
      6. RECENCY DEMOTION: a last contact older than
         `RECENCY_DEMOTE_DAYS` demotes exactly one tier, and an unparsable one
         demotes too (fail closed). A relationship is a recent thing or it is a
         memory, and treating a three-month silence as intimacy is the same
         class of claim as inventing the conversation.

    **AT M0 THIS IS INERT AND EVERY HANDLE IS A STRANGER.**
    `data/marketing/personas/<id>/relations.jsonl` is written only on the M1
    approval path, so it does not exist yet on any desk. That is the correct
    shipping state and it is printed rather than discovered: the ladder is built
    now because building it after the store fills means a month of replies
    written at the wrong register.
    """
    acct = str(account or "").strip()
    key = str(handle or "").strip().lower().lstrip("@")
    if not acct or not key:
        return "stranger"

    rows = relations
    if rows is None:
        try:
            from engine.marketing import reply_score as _score  # noqa: PLC0415

            rows = _score.load_relations(acct, root)
        except Exception as exc:  # noqa: BLE001
            # An unreadable store is not a store that said "familiar". The cold
            # answer is always the safe one here: it costs a plainer reply,
            # while a warm answer on no evidence costs the account.
            log.warning("persona_model.familiarity: relations unreadable for %r: %s",
                        acct, exc)
            return "stranger"

    row = (rows or {}).get(key)
    if not isinstance(row, dict):
        return "stranger"
    if is_declined(row):
        return "stranger"

    touches = _as_int(row.get("touches"), 0)
    if touches <= 0:
        return "stranger"
    stage = str(row.get("stage") or "").strip().lower()
    if touches >= 8 or stage == "reciprocal":
        tier = "regular"
    elif touches >= 3 and stage == "engaged":
        tier = "familiar"
    else:
        tier = "acquainted"

    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    last = _parse_contact(row.get("last_contact"))
    if last is None or (ts - last) > timedelta(days=RECENCY_DEMOTE_DAYS):
        tier = _demote(tier)
    return tier


def tier_policy(tier: str, *, declined: bool = False) -> dict[str, Any]:
    """What a familiarity tier changes in the draft (§E.4), as one record.

    Published as ONE table so the drafter lane has a single thing to consume and
    a single thing to test, rather than three lookups that can disagree. Every
    field NARROWS: the warmth list is intersected with the fitness gate's own
    output, the blocked families are removed from an already-computed pool, and
    the shape boost is a multiplier the sampler renormalises. Nothing here can
    make a move available that the persona's own guards rejected.

    `declined=True` empties the warmth list outright. That is the one place this
    table is a hard rule instead of a narrowing, and it needs its own test.
    """
    t = str(tier) if tier in FAMILIARITY_TIERS else "stranger"
    if declined:
        return {
            "tier": "stranger",
            "declined": True,
            "warmth_moves": (),
            "blocked_families": TIER_BLOCKED_FAMILIES["stranger"],
            "shape_boost": {},
            "tone_available": False,
        }
    return {
        "tier": t,
        "declined": False,
        "warmth_moves": TIER_WARMTH_MOVES[t],
        "blocked_families": TIER_BLOCKED_FAMILIES[t],
        "shape_boost": dict(TIER_SHAPE_BOOST[t]),
        "tone_available": t in ("familiar", "regular"),
    }


# ---------------------------------------------------------------------------
# Relationship tone — the AM-R1 gate
# ---------------------------------------------------------------------------
_TOPIC_TOKEN_RE = re.compile(r"[a-z0-9$]+")

#: Tokens too common to prove a topic overlap. A tone prefix that fired because
#: both the stored topic and the parent contain "market" is a tone prefix that
#: fires on everything, which is the same as no gate at all.
_TOPIC_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "this", "that", "from", "into", "about",
    "market", "markets", "stock", "stocks", "price", "prices", "today",
    "week", "month", "year", "post", "thread", "data", "chart",
})

_MIN_TOPIC_TOKEN_LEN = 4


def _topic_tokens(text: str) -> set[str]:
    return {t for t in _TOPIC_TOKEN_RE.findall(str(text or "").lower())
            if len(t) >= _MIN_TOPIC_TOKEN_LEN and t not in _TOPIC_STOPWORDS}


def tone_prefixes(
    account: str,
    tier: str,
    *,
    parent_text: str = "",
    relations_row: dict | None = None,
    now: datetime | None = None,
    root: Path | str | None = None,
) -> list[str]:
    """Familiar-register openers this desk may legally use on this author.

    THE SHARPEST RULE IN §E, and the reason this function is mostly refusals.
    The operator's own example — "this is exactly what you warned about last
    week" — is A CLAIM ABOUT THE PAST. An unverified claim about a shared
    history is the same class of fabrication as an invented lunch, and AM-R1
    does not care that the claim is small. It is lawful only when it is
    CHECKABLE FROM OUR OWN STORE, so this returns [] unless ALL of:

      * the tier is `familiar` or `regular` (§E.4);
      * `relations_row["last_contact"]` is inside `TONE_PREFIX_MAX_AGE_DAYS` of
        `now` — "last week" has to have been last week;
      * at least one stored `topics` entry token-overlaps `parent_text`, so
        "the one you kept pointing at" points at something;
      * the copy survives the persona's OWN guard sweep, exactly as the warmth
        openers and the doorway tails do (one sweep, three callers).

    Both preconditions FAIL CLOSED and each has its own test. The precedent is
    `flat_confession.needs_thesis`: we do not invent having been wrong, and we
    do not invent having spoken.

    THE POOLS THEMSELVES CARRY TWO COPY RULES, pinned by test rather than by
    review: no first name ever (a tone prefix is the one place a builder is
    tempted, and `fabrication` bars the parent author's name tokens on every
    draft), and no bare "lol" — `_DIGNITY_TOKENS` already carries `lmao` and
    `lol no`, a bare `lol` is one edit from a contempt tell, and the operator's
    own example survives its removal intact.
    """
    acct = str(account or "").strip()
    if not acct or str(tier) not in ("familiar", "regular"):
        return []
    if not isinstance(relations_row, dict) or is_declined(relations_row):
        return []

    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    last = _parse_contact(relations_row.get("last_contact"))
    if last is None or (ts - last) > timedelta(days=TONE_PREFIX_MAX_AGE_DAYS):
        return []

    parent_tokens = _topic_tokens(parent_text)
    if not parent_tokens:
        return []
    topics = relations_row.get("topics")
    topics = topics if isinstance(topics, (list, tuple)) else ()
    if not any(_topic_tokens(t) & parent_tokens for t in topics):
        return []

    pool = load_model(acct, root=root).tone_pool(str(tier))
    if not pool:
        return []
    try:
        from engine.marketing import reply_drafter as _rd  # noqa: PLC0415

        return [p for p in pool
                if _rd._copy_clears_persona_guards(acct, p, f"tone::{tier}::{p}", root)]
    except Exception as exc:  # noqa: BLE001
        # A guard we cannot run is not a guard that passed — the same posture
        # the warmth openers take. Losing the tone costs a neutral reply;
        # shipping unswept persona copy costs the account.
        log.warning("persona_model.tone_prefixes: guard sweep unavailable for %r: %s",
                    acct, exc)
        return []


# ---------------------------------------------------------------------------
# Response mix
# ---------------------------------------------------------------------------
def response_mix(
    account: str,
    *,
    cfg: dict | None = None,
    root: Path | str | None = None,  # noqa: ARG001 — API symmetry (§F.1)
) -> dict[str, float]:
    """`RESPONSE_TYPES` -> weight for *account*, normalised to 1.0.

    Resolution order: the config override
    (``reply_desk.response_mix.accounts.<id>``) layered ONTO the code row for
    that account, then the code row, then `_default`. Layering rather than
    replacing is deliberate — an operator tuning one bucket ("give cici more
    humor") must not silently zero the five they did not mention.

    A row whose weights all resolve to zero falls back to `_default` rather than
    dividing by zero; the flagship's `humor: 0.00` is a legal single-bucket zero
    and must keep working, which is why the guard is on the SUM.
    """
    acct = str(account or "").strip()
    base = dict(DEFAULT_RESPONSE_MIX.get(acct) or DEFAULT_RESPONSE_MIX["_default"])

    over = (((cfg or {}).get("reply_desk") or {}).get("response_mix") or {})
    accounts = over.get("accounts") if isinstance(over, dict) else None
    row = (accounts or {}).get(acct) if isinstance(accounts, dict) else None
    if isinstance(row, dict):
        for key, value in row.items():
            if str(key) in RESPONSE_TYPES:
                base[str(key)] = _as_float(value, base.get(str(key), 0.0))
            else:
                print(f"::warning title=response_mix_unknown_type::{acct}: "
                      f"reply_desk.response_mix names unknown response type "
                      f"{str(key)!r} — ignored; the six are "
                      f"{list(RESPONSE_TYPES)}", flush=True)

    weights = {k: max(0.0, _as_float(base.get(k), 0.0)) for k in RESPONSE_TYPES}
    total = sum(weights.values())
    if total <= 0.0:
        weights = {k: max(0.0, float(DEFAULT_RESPONSE_MIX["_default"][k]))
                   for k in RESPONSE_TYPES}
        total = sum(weights.values())
    return {k: round(v / total, 6) for k, v in weights.items()}
