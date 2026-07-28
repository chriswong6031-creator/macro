"""engine.marketing.personas — Persona spec v1 loader + validator (Persona Network W1).

Reads ``config/personas/<id>.yml`` — the persona layer the Persona Network
masterplan (``research/agentic_media/PERSONA_NETWORK_MASTERPLAN_BY_FABLE.md``
§3) puts around the shipped 6-desk newsroom: identity, voice codex, beat,
memory ledger path, cadence profile, isolation slots and a pre-registered
scorecard.

W1 WAS AN ADDITIVE OVERLAY — XG-W1 OPENED EXACTLY ONE SEAM
-----------------------------------------------------------
Persona-Network W1 shipped this layer with NO generation consumer: the only two
readers were the ``--check`` CLI (a CI gate) and the read-only admin Persona
Roster (``admin/personas.py``).  ``config/marketing.yml`` stays canonical for
``desk_network`` (beat/voice/tilt/enabled) and ``copywriter.personas`` stays
canonical for ``voice_notes``/``example_lines``; W2 migrates the copywriter block
onto the codex and deletes the old block with a no-orphan test.

X-Growth W1 (the four employee desks) opened ONE generation-side seam, because a
spec layer nothing reads is decorative and the expression dial has to be
enforceable: ``engine.marketing.expression_dial`` reads ``voice_codex`` for the
personas that declare a ``dial_profile``, and the copy layer calls THAT module
(never this one).  The consumer allow-list in ``tests/test_marketing_personas.py``
is the fence; it is four files, not a policy.

EMPLOYEE SPECS (``persona_kind: employee``)
-------------------------------------------
Real named humans on official rails (masterplan §5 / charter §1).  They carry
four blocks the pseudonymous cohort does not: ``worldview`` (constitution §6.1),
``franchises`` (§12), ``canon`` (§5.2 — allowed stable texture, and the
do-not-invent list is why every canon SLOT ships dark), and ``restraint`` (the
one thing this persona never does).  Their codex additionally carries
``dial_profile`` + machine-readable ``quirk_markers``, which is what makes the
pinned quirk PROSE executable.

Public API
----------
    load_all(root=None) -> dict[str, PersonaSpec]   # raises PersonaSpecError
    check(root=None)    -> dict[str, list[str]]     # path -> errors, never raises
    content_type_ids()  -> tuple[str, ...]          # canonical, read from content_studio
    live_voice_keys()   -> frozenset[str]           # voices the template pool actually has
    voiced_type_ids()   -> frozenset[str]           # types that HAVE voice-keyed templates

    python -m engine.marketing.personas --check     # exit 0 clean / 1 with per-file errors

Import closure (this module is deliberately cheap — CI's ``marketing-engine``
lane installs only ``pytest pyyaml``)
------------------------------------------------------------------------------
  * module level: stdlib (``argparse``, ``re``, ``sys``, ``dataclasses``,
    ``pathlib``, ``typing``) + ``yaml``.  Nothing else, ever.
  * lazy, inside the validation helpers only: ``engine.marketing.content_studio``
    (itself stdlib-only) for the canonical content type-id set and the live copy
    template pool.  The type-id set is READ, never copied here — a hardcoded
    duplicate would drift silently the first time a tenth content type ships.
  * unavoidable package side effect: importing ``engine.marketing.personas``
    executes ``engine/marketing/__init__.py``, which imports
    ``engine.marketing.state`` (stdlib + yaml).  That is the package's closure,
    not this module's; ``content_studio`` is NOT in it (verified by test).

Validation rules (all fail loudly — a bad spec is never silently repaired)
-------------------------------------------------------------------------
``voice`` is REQUIRED and must be a live template-pool voice key that covers
every voice-keyed content type, so ``content_studio._get_copy`` never falls back
for a configured persona.

``tilt`` must carry EXACTLY the content-studio type-id key set.  A partial tilt
is rejected outright rather than filled: at consumption a missing key inherits
``content_studio._DEFAULT_TILT``, so omitting a type does not disable it — it
silently restores the default weight.  Omit ≠ disable, therefore omit ≠ legal.
Weights sum to 1.0 ± 1e-6 and ``signal`` is strictly the largest at ≥ 0.28.

The AM-R1 hard lines (masterplan §1: "enforced as validator rules — not policy
prose") are executable here: every spec's ``voice_codex.banned_patterns`` must
carry the three fabricated-claim patterns.  A persona cannot opt out.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_SPEC_DIR_REL = Path("config") / "personas"

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: ``employee`` (XG-W1): a REAL named human on an official rail — the four
#: employee desks (Meagan/Sophia/Kelly/Cici).  Not a character and not
#: pseudonymous, which is exactly why the isolation checklist stays null on them
#: and why AM-R1 binds hardest there.
PERSONA_KINDS = ("branded", "specialist", "character", "employee")
PIPELINES = ("engine", "hybrid", "llm")
MODEL_TIERS = ("default", "opus")
EMOJI_POLICIES = ("none", "sparse", "signature-set")
WEEKEND_SHAPES = ("light", "medium", "full")
CHRONICLE_PACKS = ("short", "medium", "long")

#: ``signal`` is the largest weight on every account (config/marketing.yml §5).
SIGNAL_TILT_FLOOR = 0.28
#: Tilt weights must sum to 1.0 within this tolerance.
TILT_SUM_TOL = 1e-6

#: Masterplan §1 / AM-R1: no fabricated personal claims, no testimonial product
#: claims.  Every persona carries these three, verbatim, in banned_patterns.
AM_R1_BANNED_PATTERNS = (
    "first-person trade/position/P&L claims",
    "fabricated personal experience",
    "testimonial-style product claims",
)

#: GitHub renders a bounded number of annotations per step; 5 per file shows a
#: multi-fault spec in full without burying the summary.
_MAX_ANNOTATIONS_PER_FILE = 5

#: Memory ledger path pattern (masterplan §4 + §0 ledger law: nightly-advanced).
#: Pinned per-id so a copy-pasted spec can never point two personas at one ledger.
MEMORY_PATH_TEMPLATE = "data/marketing/personas/{id}/theses.jsonl"

_TOP_KEYS = (
    "id", "persona_kind", "archetype", "voice", "voice_codex", "beat", "tilt",
    "pipeline", "model_tier", "cadence", "isolation", "context_packs", "memory",
    "scorecard",
)
#: The cognitive layer the constitution grafts on (charter §2 amendment 2).
#: Optional for every kind, REQUIRED for ``employee`` — a real named human posts
#: from a worldview and a franchise register, not from a style guide alone.
_TOP_OPTIONAL_KEYS = ("worldview", "franchises", "canon", "restraint")

_CODEX_KEYS = ("register", "quirks", "emoji_policy", "banned", "banned_patterns", "zh")
#: Optional codex keys.
#:   emoji_signature — the exact emoji a persona may use.  Required to be
#:     non-empty when emoji_policy is ``signature-set``; permitted with ``sparse``.
#:   dial_profile    — names the expression_dial.PROFILES table this persona's
#:     per-kind personality budget comes from.  Declaring it is what puts an
#:     account ON the dial; omitting it leaves the persona spec-only.
#:   quirk_markers   — the machine-readable encoding of the ``quirks`` prose:
#:     {marker_id: {enabled, note, max_per_post?, max_per_day?, max_share_7d?}}.
#:     Both are required for ``employee``.
_CODEX_OPTIONAL_KEYS = ("emoji_signature", "dial_profile", "quirk_markers")
_CADENCE_KEYS = ("posts_per_day", "min_spacing_min", "jitter_min", "weekend_shape")
_ISOLATION_KEYS = ("profile_id", "egress", "registered_at", "warmed_through", "rail")
_CONTEXT_PACK_KEYS = ("chronicle", "desks")
_SCORECARD_KEYS = ("min_impressions", "promote_after", "kill_after", "alpha_note")
_PROMOTE_KEYS = ("weeks", "engagement_rate_ci_lower_above")
_KILL_KEYS = ("weeks", "engagement_rate_ci_upper_below")


class PersonaSpecError(ValueError):
    """Raised by :func:`load_all` when any committed spec fails validation."""


@dataclass(frozen=True)
class PersonaSpec:
    """One validated ``config/personas/<id>.yml``.

    Pure spec data.  Liveness (does a ``desk_network`` account exist behind it?)
    is deliberately NOT a field: the spec layer does not read
    ``config/marketing.yml``.  The roster (``admin/personas.py``) performs that
    join and derives ``provisioned`` / LIVE / CONFIGURED / PLANNED from it.
    """

    id: str
    persona_kind: str
    archetype: str
    voice: str
    voice_codex: dict[str, Any]
    beat: str
    tilt: dict[str, float]
    pipeline: str
    model_tier: str
    cadence: dict[str, Any]
    isolation: dict[str, Any]
    context_packs: dict[str, Any]
    memory: str
    scorecard: dict[str, Any]
    #: Cognitive layer (constitution §5.1/§6.1/§12).  Empty for the specs that
    #: predate XG-W1; required and populated on every ``employee``.
    worldview: str = ""
    franchises: tuple[str, ...] = ()
    canon: tuple[str, ...] = ()
    restraint: str = ""
    source: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view for the admin panel / JSON responses."""
        return {
            "id": self.id,
            "persona_kind": self.persona_kind,
            "archetype": self.archetype,
            "voice": self.voice,
            "voice_codex": dict(self.voice_codex),
            "beat": self.beat,
            "tilt": dict(self.tilt),
            "pipeline": self.pipeline,
            "model_tier": self.model_tier,
            "cadence": dict(self.cadence),
            "isolation": dict(self.isolation),
            "context_packs": dict(self.context_packs),
            "memory": self.memory,
            "scorecard": dict(self.scorecard),
            "worldview": self.worldview,
            "franchises": list(self.franchises),
            "canon": list(self.canon),
            "restraint": self.restraint,
            "source": self.source,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Canonical sets — READ from content_studio, never duplicated here
# ─────────────────────────────────────────────────────────────────────────────

def content_type_ids() -> tuple[str, ...]:
    """The canonical content type-id set, in content_studio's declared order."""
    from engine.marketing.content_studio import CONTENT_TYPES  # noqa: PLC0415

    return tuple(str(t["id"]) for t in CONTENT_TYPES)


def live_voice_keys() -> frozenset[str]:
    """Voice keys that actually exist in the deterministic copy template pool."""
    from engine.marketing.content_studio import _COPY_TEMPLATES  # noqa: PLC0415

    return frozenset(voice for (_type_id, voice) in _COPY_TEMPLATES)


def voiced_type_ids() -> frozenset[str]:
    """Content types that HAVE voice-keyed templates.

    ``mover`` and ``theme_list`` currently have none for ANY voice — every
    account, spec'd or not, takes ``_get_copy``'s generic tail for those two.
    Excluding them keeps the no-fallback rule honest instead of unwinnable.
    """
    from engine.marketing.content_studio import _COPY_TEMPLATES  # noqa: PLC0415

    return frozenset(type_id for (type_id, _voice) in _COPY_TEMPLATES)


# ─────────────────────────────────────────────────────────────────────────────
# Validation helpers — every one returns a list of plain-word error strings
# ─────────────────────────────────────────────────────────────────────────────

def _is_int(value: Any) -> bool:
    """True for a real int.  ``bool`` is an int in Python and is NOT one here."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _key_errors(where: str, obj: Any, required: tuple[str, ...],
                optional: tuple[str, ...] = ()) -> list[str]:
    """Exact-key-set check for a mapping block."""
    if not isinstance(obj, dict):
        return [f"{where}: expected a mapping, got {type(obj).__name__}"]
    errs: list[str] = []
    missing = [k for k in required if k not in obj]
    extra = [k for k in obj if k not in required and k not in optional]
    if missing:
        errs.append(f"{where}: missing key(s) {sorted(missing)}")
    if extra:
        errs.append(f"{where}: unknown key(s) {sorted(extra)}")
    return errs


def _str_errors(where: str, value: Any) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"{where}: expected a non-empty string"]
    return []


def _str_list_errors(where: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        return [f"{where}: expected a list, got {type(value).__name__}"]
    bad = [repr(v) for v in value if not isinstance(v, str)]
    return [f"{where}: non-string entries {bad}"] if bad else []


def _validate_tilt(tilt: Any) -> list[str]:
    """EXACTLY the content-studio type-id set, summing to 1.0, signal strictly max."""
    type_ids = content_type_ids()
    if not isinstance(tilt, dict):
        return [f"tilt: expected a mapping, got {type(tilt).__name__}"]

    errs: list[str] = []
    missing = sorted(set(type_ids) - set(tilt))
    extra = sorted(set(tilt) - set(type_ids))
    if missing:
        errs.append(
            f"tilt: missing content type(s) {missing} — a partial tilt inherits "
            f"content_studio._DEFAULT_TILT at consumption, so omitting a type does "
            f"not disable it; list all {len(type_ids)} explicitly"
        )
    if extra:
        errs.append(f"tilt: unknown content type(s) {extra} (known: {list(type_ids)})")

    non_numeric = sorted(k for k, v in tilt.items() if not _is_num(v))
    if non_numeric:
        errs.append(f"tilt: non-numeric weight(s) {non_numeric}")
    if errs:
        return errs

    negative = sorted(k for k, v in tilt.items() if float(v) < 0)
    if negative:
        errs.append(f"tilt: negative weight(s) {negative}")

    total = sum(float(v) for v in tilt.values())
    if abs(total - 1.0) > TILT_SUM_TOL:
        errs.append(f"tilt: weights sum to {total!r}, expected 1.0 ± {TILT_SUM_TOL}")

    signal = float(tilt["signal"])
    others = max(float(v) for k, v in tilt.items() if k != "signal")
    if signal <= others:
        errs.append(
            f"tilt: signal ({signal}) must be strictly the largest weight "
            f"(largest other is {others})"
        )
    if signal < SIGNAL_TILT_FLOOR:
        errs.append(f"tilt: signal ({signal}) is below the {SIGNAL_TILT_FLOOR} floor")
    return errs


def _validate_voice(voice: Any) -> list[str]:
    """REQUIRED, and must join the live template pool with no fallback."""
    errs = _str_errors("voice", voice)
    if errs:
        return errs

    live = live_voice_keys()
    if voice not in live:
        return [
            f"voice: {voice!r} is not a live template-pool voice key "
            f"(live keys: {sorted(live)})"
        ]

    from engine.marketing.content_studio import _COPY_TEMPLATES  # noqa: PLC0415

    gaps = sorted(t for t in voiced_type_ids() if (t, voice) not in _COPY_TEMPLATES)
    if gaps:
        return [
            f"voice: {voice!r} has no copy template for {gaps} — content_studio."
            f"_get_copy would fall back to the 'authoritative desk' voice"
        ]
    return []


def _validate_quirk_markers(markers: Any) -> list[str]:
    """``voice_codex.quirk_markers`` — the executable half of the quirk prose.

    Every key must be a marker the house lexicon actually detects.  A typo'd id
    would otherwise declare a quirk nothing enforces AND leave the real marker
    un-declared, i.e. the persona would silently lose a signature and gain a
    permanently-violating one.  The lexicon is imported LAZILY (module docstring:
    this file stays stdlib + yaml at import).
    """
    if not isinstance(markers, dict):
        return [f"voice_codex.quirk_markers: expected a mapping, "
                f"got {type(markers).__name__}"]

    from engine.marketing.expression_dial import (  # noqa: PLC0415
        CANON_MARKERS, MARKER_DECL_KEYS, MARKERS,
    )

    errs: list[str] = []
    unknown = sorted(set(markers) - set(MARKERS))
    if unknown:
        errs.append(
            f"voice_codex.quirk_markers: unknown marker id(s) {unknown} "
            f"(known: {sorted(MARKERS)})"
        )

    for marker_id, decl in sorted(markers.items()):
        where = f"voice_codex.quirk_markers.{marker_id}"
        if not isinstance(decl, dict):
            errs.append(f"{where}: expected a mapping, got {type(decl).__name__}")
            continue
        extra = sorted(set(decl) - set(MARKER_DECL_KEYS))
        if extra:
            errs.append(f"{where}: unknown key(s) {extra} "
                        f"(allowed: {list(MARKER_DECL_KEYS)})")
        if not isinstance(decl.get("enabled"), bool):
            errs.append(f"{where}.enabled: expected a boolean")
        errs += _str_errors(f"{where}.note", decl.get("note"))

        for key in ("max_per_post", "max_per_day", "max_per_7d"):
            if key in decl and (not _is_int(decl[key]) or decl[key] < 1):
                errs.append(f"{where}.{key}: expected an integer >= 1, got {decl[key]!r}")

        # An ENABLED marker with no per-post cap is an uncapped quirk: the dial
        # bounds how many DISTINCT devices a post may carry, never how many times
        # one device repeats, so "okay so ... okay so ... okay so" would satisfy
        # the dial and read as a machine. max_per_post is the only cap that needs
        # no history, so it is the one the loader can and does require.
        if decl.get("enabled") is True and "max_per_post" not in decl:
            errs.append(
                f"{where}.max_per_post: required on an enabled marker — the dial "
                f"counts distinct devices, so without this a single quirk may "
                f"repeat without limit inside one post"
            )
        share = decl.get("max_share_7d")
        if share is not None and (not _is_num(share) or not (0.0 < float(share) <= 1.0)):
            errs.append(f"{where}.max_share_7d: expected a share in (0, 1], got {share!r}")

        # Autobiographical canon describes a REAL person.  Nothing in this repo
        # verifies it, and "unverified personal texture on a real name" is the
        # AM-R1 class, so a canon slot may be declared but never switched on
        # without an employee confirmation recorded in its note.
        if marker_id in CANON_MARKERS and decl.get("enabled") is True:
            errs.append(
                f"{where}.enabled: canon markers ship DARK — {marker_id!r} describes "
                f"a real person's private life and nothing here verifies it "
                f"(AM-R1). Flip it only with the employee's confirmation."
            )
    return errs


def _validate_codex(codex: Any) -> list[str]:
    errs = _key_errors("voice_codex", codex, _CODEX_KEYS, _CODEX_OPTIONAL_KEYS)
    if errs:
        return errs

    if "dial_profile" in codex:
        from engine.marketing.expression_dial import PROFILES  # noqa: PLC0415

        profile = codex["dial_profile"]
        if profile not in PROFILES:
            errs.append(
                f"voice_codex.dial_profile: {profile!r} not one of {sorted(PROFILES)}"
            )
    if "quirk_markers" in codex:
        errs += _validate_quirk_markers(codex["quirk_markers"])

    errs += _str_errors("voice_codex.register", codex.get("register"))
    errs += _str_list_errors("voice_codex.quirks", codex.get("quirks"))
    errs += _str_list_errors("voice_codex.banned", codex.get("banned"))
    errs += _str_list_errors("voice_codex.banned_patterns", codex.get("banned_patterns"))

    policy = codex.get("emoji_policy")
    if policy not in EMOJI_POLICIES:
        errs.append(
            f"voice_codex.emoji_policy: {policy!r} not one of {list(EMOJI_POLICIES)}"
        )

    if not isinstance(codex.get("zh"), bool):
        errs.append("voice_codex.zh: expected a boolean")

    if "emoji_signature" in codex:
        errs += _str_list_errors("voice_codex.emoji_signature", codex["emoji_signature"])
    if policy == "none" and codex.get("emoji_signature"):
        errs.append("voice_codex.emoji_signature: set while emoji_policy is 'none'")
    if policy == "signature-set" and not codex.get("emoji_signature"):
        errs.append(
            "voice_codex.emoji_signature: required (and non-empty) when "
            "emoji_policy is 'signature-set'"
        )

    patterns = codex.get("banned_patterns")
    if isinstance(patterns, list):
        absent = [p for p in AM_R1_BANNED_PATTERNS if p not in patterns]
        if absent:
            errs.append(
                f"voice_codex.banned_patterns: missing the AM-R1 hard lines {absent} "
                f"— no persona may opt out of the fabricated-claim ban"
            )
    return errs


def _validate_cadence(cadence: Any) -> list[str]:
    errs = _key_errors("cadence", cadence, _CADENCE_KEYS)
    if errs:
        return errs

    for key, floor in (("posts_per_day", 1), ("min_spacing_min", 1), ("jitter_min", 0)):
        value = cadence.get(key)
        if not _is_int(value):
            errs.append(f"cadence.{key}: expected an integer, got {value!r}")
        elif value < floor:
            errs.append(f"cadence.{key}: {value} must be >= {floor}")

    shape = cadence.get("weekend_shape")
    if shape not in WEEKEND_SHAPES:
        errs.append(f"cadence.weekend_shape: {shape!r} not one of {list(WEEKEND_SHAPES)}")
    return errs


def _validate_isolation(isolation: Any) -> list[str]:
    """All five §2 checklist slots present; every one nullable until provisioning."""
    errs = _key_errors("isolation", isolation, _ISOLATION_KEYS)
    if errs:
        return errs
    bad = sorted(
        k for k, v in isolation.items() if v is not None and not isinstance(v, str)
    )
    return [f"isolation: non-string, non-null value(s) {bad}"] if bad else []


def _validate_context_packs(packs: Any) -> list[str]:
    errs = _key_errors("context_packs", packs, _CONTEXT_PACK_KEYS)
    if errs:
        return errs

    chronicle = packs.get("chronicle")
    errs += _str_list_errors("context_packs.chronicle", chronicle)
    if isinstance(chronicle, list):
        unknown = sorted(set(str(c) for c in chronicle) - set(CHRONICLE_PACKS))
        if unknown:
            errs.append(
                f"context_packs.chronicle: unknown pack(s) {unknown} "
                f"(known: {list(CHRONICLE_PACKS)})"
            )
        if len(chronicle) != len(set(map(str, chronicle))):
            errs.append("context_packs.chronicle: duplicate pack(s)")

    errs += _str_list_errors("context_packs.desks", packs.get("desks"))
    return errs


def _validate_scorecard(scorecard: Any) -> list[str]:
    errs = _key_errors("scorecard", scorecard, _SCORECARD_KEYS)
    if errs:
        return errs

    floor = scorecard.get("min_impressions")
    if not _is_int(floor) or floor <= 0:
        errs.append(f"scorecard.min_impressions: expected a positive integer, got {floor!r}")

    for block, keys, rate_key in (
        ("promote_after", _PROMOTE_KEYS, "engagement_rate_ci_lower_above"),
        ("kill_after", _KILL_KEYS, "engagement_rate_ci_upper_below"),
    ):
        sub_errs = _key_errors(f"scorecard.{block}", scorecard.get(block), keys)
        if sub_errs:
            errs += sub_errs
            continue
        sub = scorecard[block]
        weeks = sub.get("weeks")
        if not _is_int(weeks) or weeks <= 0:
            errs.append(f"scorecard.{block}.weeks: expected a positive integer, got {weeks!r}")
        rate = sub.get(rate_key)
        if not _is_num(rate) or not (0.0 < float(rate) < 1.0):
            errs.append(
                f"scorecard.{block}.{rate_key}: expected a rate in (0, 1), got {rate!r}"
            )

    errs += _str_errors("scorecard.alpha_note", scorecard.get("alpha_note"))
    return errs


def validate_spec(raw: Any, *, expect_id: str | None = None) -> list[str]:
    """Validate one parsed spec mapping.  Returns [] when it is legal."""
    if not isinstance(raw, dict):
        return [f"spec: expected a mapping, got {type(raw).__name__}"]

    errs = _key_errors("spec", raw, _TOP_KEYS, _TOP_OPTIONAL_KEYS)
    if errs:
        return errs

    spec_id = raw.get("id")
    if not isinstance(spec_id, str) or not _ID_RE.match(spec_id or ""):
        errs.append(f"id: {spec_id!r} must be a lowercase slug matching {_ID_RE.pattern}")
    elif expect_id is not None and spec_id != expect_id:
        errs.append(f"id: {spec_id!r} does not match the file name {expect_id!r}")

    if raw.get("persona_kind") not in PERSONA_KINDS:
        errs.append(
            f"persona_kind: {raw.get('persona_kind')!r} not one of {list(PERSONA_KINDS)}"
        )
    if raw.get("pipeline") not in PIPELINES:
        errs.append(f"pipeline: {raw.get('pipeline')!r} not one of {list(PIPELINES)}")
    if raw.get("model_tier") not in MODEL_TIERS:
        errs.append(f"model_tier: {raw.get('model_tier')!r} not one of {list(MODEL_TIERS)}")

    errs += _str_errors("archetype", raw.get("archetype"))
    errs += _str_errors("beat", raw.get("beat"))
    errs += _validate_voice(raw.get("voice"))
    errs += _validate_codex(raw.get("voice_codex"))
    errs += _validate_tilt(raw.get("tilt"))
    errs += _validate_cadence(raw.get("cadence"))
    errs += _validate_isolation(raw.get("isolation"))
    errs += _validate_context_packs(raw.get("context_packs"))
    errs += _validate_scorecard(raw.get("scorecard"))

    memory = raw.get("memory")
    mem_errs = _str_errors("memory", memory)
    errs += mem_errs
    if not mem_errs and isinstance(spec_id, str):
        expected = MEMORY_PATH_TEMPLATE.format(id=spec_id)
        if memory != expected:
            errs.append(f"memory: expected {expected!r}, got {memory!r}")

    errs += _validate_cognitive_layer(raw)
    return errs


def _validate_cognitive_layer(raw: dict) -> list[str]:
    """The constitution's grafted layers.  Optional in general, REQUIRED on employees.

    An employee account is a real person's name on a real X account.  Shipping
    one without a worldview, a franchise register and a restraint clause is how a
    "persona" degrades into a voice filter over generic desk copy — the failure
    state every §5.x section names by hand.
    """
    errs: list[str] = []

    if "worldview" in raw:
        errs += _str_errors("worldview", raw["worldview"])
    if "restraint" in raw:
        errs += _str_errors("restraint", raw["restraint"])
    for key in ("franchises", "canon"):
        if key in raw:
            errs += _str_list_errors(key, raw[key])

    if raw.get("persona_kind") != "employee":
        return errs

    for key in ("worldview", "restraint"):
        if not str(raw.get(key) or "").strip():
            errs.append(f"{key}: required on persona_kind 'employee'")
    for key in ("franchises", "canon"):
        if not raw.get(key):
            errs.append(f"{key}: required (non-empty) on persona_kind 'employee'")

    codex = raw.get("voice_codex")
    if isinstance(codex, dict):
        if not codex.get("dial_profile"):
            errs.append(
                "voice_codex.dial_profile: required on persona_kind 'employee' — "
                "an employee account that is not on the expression dial is an "
                "unvalidated personality"
            )
        if not codex.get("quirk_markers"):
            errs.append(
                "voice_codex.quirk_markers: required (non-empty) on persona_kind "
                "'employee' — the quirk prose must be machine-readable or the "
                "whitelist enforces nothing"
            )
    return errs


# ─────────────────────────────────────────────────────────────────────────────
# Loading
# ─────────────────────────────────────────────────────────────────────────────

def _root_path(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def spec_dir(root: Path | str | None = None) -> Path:
    """Absolute path of ``config/personas/`` under *root* (repo root by default)."""
    return _root_path(root) / _SPEC_DIR_REL


def spec_paths(root: Path | str | None = None) -> list[Path]:
    """Every ``*.yml`` in the spec directory, name-sorted.  [] when absent."""
    directory = spec_dir(root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.yml"))


def load_spec(path: Path | str) -> tuple[PersonaSpec | None, list[str]]:
    """Parse + validate one spec file.  Returns (spec_or_None, errors)."""
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, [f"unreadable: {exc}"]
    except yaml.YAMLError as exc:
        return None, [f"invalid YAML: {exc}"]

    errors = validate_spec(raw, expect_id=path.stem)
    if errors:
        return None, errors

    return PersonaSpec(
        id=raw["id"],
        persona_kind=raw["persona_kind"],
        archetype=raw["archetype"],
        voice=raw["voice"],
        voice_codex=raw["voice_codex"],
        beat=raw["beat"],
        tilt={k: float(v) for k, v in raw["tilt"].items()},
        pipeline=raw["pipeline"],
        model_tier=raw["model_tier"],
        cadence=raw["cadence"],
        isolation=raw["isolation"],
        context_packs=raw["context_packs"],
        memory=raw["memory"],
        scorecard=raw["scorecard"],
        worldview=str(raw.get("worldview") or ""),
        franchises=tuple(str(f) for f in (raw.get("franchises") or ())),
        canon=tuple(str(c) for c in (raw.get("canon") or ())),
        restraint=str(raw.get("restraint") or ""),
        source=str(path),
    ), []


def _rel(path: Path, repo: Path) -> str:
    """Repo-relative key for a spec path; absolute when it lies outside *repo*."""
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return str(path)


def check(root: Path | str | None = None) -> dict[str, list[str]]:
    """Validate every committed spec.  Returns {relative path: errors}, failures only.

    Never raises — this is what the ``--check`` CLI and any diagnostics read.
    """
    repo = _root_path(root)
    failures: dict[str, list[str]] = {}
    for path in spec_paths(root):
        _spec, errors = load_spec(path)
        if errors:
            failures[_rel(path, repo)] = errors
    return failures


def load_all(root: Path | str | None = None) -> dict[str, PersonaSpec]:
    """Every validated spec, keyed by id.

    Raises :class:`PersonaSpecError` listing every bad file — a spec that does
    not validate must never reach a consumer half-repaired.  A missing
    ``config/personas/`` directory is not an error here (returns ``{}``) so the
    admin roster renders an honest empty state; the ``--check`` CLI treats the
    same absence as a CI failure, because in this repo the directory ships.
    """
    specs: dict[str, PersonaSpec] = {}
    problems: list[str] = []
    for path in spec_paths(root):
        spec, errors = load_spec(path)
        if errors or spec is None:
            problems.extend(f"{path.name}: {e}" for e in errors)
            continue
        if spec.id in specs:
            problems.append(f"{path.name}: duplicate persona id {spec.id!r}")
            continue
        specs[spec.id] = spec

    if problems:
        raise PersonaSpecError(
            f"{len(problems)} persona spec problem(s):\n  " + "\n  ".join(problems)
        )
    return specs


# ─────────────────────────────────────────────────────────────────────────────
# CLI — python -m engine.marketing.personas --check
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m engine.marketing.personas",
        description="Validate config/personas/<id>.yml persona specs (Persona Network W1).",
    )
    parser.add_argument("--check", action="store_true",
                        help="validate every committed spec; exit 1 on any error")
    parser.add_argument("--root", default=None,
                        help="repo root to read config/personas/ from (default: this repo)")
    args = parser.parse_args(argv)

    if not args.check:
        parser.print_help()
        return 0

    directory = spec_dir(args.root)
    if not directory.is_dir():
        # Line-start annotation via a bare print: a logger's level prefix would
        # push "::" off column 0 and GitHub would silently drop it (house law).
        print("::error title=persona-specs::config/personas/ not found "
              f"at {directory}", flush=True)
        print(f"persona specs: FAIL — {directory} does not exist")
        return 1

    repo = _root_path(args.root)
    paths = spec_paths(args.root)
    failures = check(args.root)

    for path in paths:
        errors = failures.get(_rel(path, repo))
        if errors is None:
            print(f"  ok    {path.name}")
        else:
            print(f"  FAIL  {path.name}")
            for err in errors:
                print(f"          {err}")

    n_bad = len(failures)
    print(f"persona specs: {len(paths)} checked, {n_bad} invalid")
    if n_bad:
        for rel, errors in sorted(failures.items()):
            # Line-start annotations via a bare print: a logger's level prefix
            # would push "::" off column 0 and GitHub would silently drop it.
            # Up to _MAX_ANNOTATIONS per file — one line per file hides the rest
            # of a multi-fault spec behind a re-run.
            for err in errors[:_MAX_ANNOTATIONS_PER_FILE]:
                print(f"::error file={rel},title=persona-spec::{err}", flush=True)
            extra = len(errors) - _MAX_ANNOTATIONS_PER_FILE
            if extra > 0:
                print(f"::error file={rel},title=persona-spec::"
                      f"...and {extra} more error(s) — see the step log", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
