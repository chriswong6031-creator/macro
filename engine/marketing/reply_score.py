"""engine.marketing.reply_score — deterministic reply-opportunity scoring (XG-W4).

**LLM never scores.** Charter §2 amendment 9 extends the LLM-never-scores law to
every critic including persona/readability/engagement: "engagement potential"
and "follow-conversion potential" come from THIS module's features, never from a
model's judgment. Nothing here calls a model, and nothing here may.

**Every weight is a hypothesis.** Charter §8: the borrowed-distribution numbers
(5-15 minute windows, mid-tier over megacap, author reply-back value) come from
an uncontrolled, survivorship-prone tracked cohort. They ship as config with an
evaluation plan, not as constants, and every score carries its ``_components``
so a re-weighting never needs a re-run of discovery to be auditable.

Features (all deterministic, all in [0, 1]):

    author_tier         relationship > conversion > breakout (charter §3: the
                        portfolio needs all three, but conversion and
                        relationship outweigh vanity reach)
    age_fit            1.0 inside the reply window, decaying either side
    velocity           engagement per minute, log-compressed and capped
    saturation         reply count as a PENALTY — visible room near the top of
                        a conversation is the whole point (constitution §9.1)
    beat_fit           token overlap between the post and the desk's beats
    own_post           inbound on our own thread: our audience, lowest risk
    relationship_stage prior public interaction context, when a store exists

Public API:
    DEFAULT_WEIGHTS / DEFAULT_PARAMS
    features(target, *, persona_beats, now=None, params=None, relations=None) -> dict
    score_target(target, *, persona_beats, cfg=None, now=None, relations=None) -> dict
    rank(targets, *, persona_beats, cfg=None, now=None, relations=None) -> list[dict]
    load_relations(account, root=None) -> dict
"""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: Tier priors. Charter §3/§9.2: relationship and conversion carry more weight
#: than breakout, because a giant post produces impressions and a mid-tier
#: expert produces a relationship. Null until our own telemetry ranks them.
DEFAULT_TIER_PRIOR: dict[str, float] = {
    "relationship": 1.00,
    "inbound": 0.95,
    "conversion": 0.85,
    "breakout": 0.55,
    "unknown": 0.30,
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "author_tier": 0.26,
    "age_fit": 0.22,
    "velocity": 0.14,
    "saturation": 0.14,
    "beat_fit": 0.14,
    "own_post": 0.06,
    "relationship_stage": 0.04,
}

DEFAULT_PARAMS: dict[str, Any] = {
    # The reply window, in minutes. Charter §3 / §8 assumptions register.
    "window_open_min": 5.0,
    "window_close_min": 15.0,
    # How fast the fit decays outside the window before the target is dead.
    "pre_window_ramp_min": 5.0,
    "post_window_decay_min": 45.0,
    # Saturation: a thread with this many replies has no visible room left.
    "saturation_full": 60.0,
    # Velocity normaliser: engagement/minute that already counts as "hot".
    "velocity_hot": 40.0,
    # Below this score a target is not worth a draft.
    "min_score": 0.35,
}

_TOKEN_RE = re.compile(r"[a-z0-9$]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(text or "").lower()))


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def _parse_when(value: object) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Relationship memory (XG-W3 owns the store; this is a read-only seam)
# ---------------------------------------------------------------------------
def load_relations(account: str, root: Path | str | None = None) -> dict[str, dict]:
    """Public interaction context per author handle, when the store exists.

    XG-W3 owns ``engine/marketing/persona_memory.py`` and the write side of
    ``data/marketing/personas/<id>/relations.jsonl``. This wave only READS it,
    directly and fail-soft, so the two waves do not collide on a file. When the
    store is absent every target scores ``relationship_stage = 0.0`` and the
    component records ``source: "absent"`` — a missing input is printed, not
    hidden (house epistemics law).

    Constitution §14.1: public, relevant interaction context only. Nothing
    sensitive is inferred here and nothing may be added that does.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parent.parent.parent
    path = base / "data" / "marketing" / "personas" / str(account) / "relations.jsonl"
    if not path.exists():
        return {}
    try:
        from engine.marketing.ledgers import read_jsonl  # noqa: PLC0415

        rows = read_jsonl(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("reply_score: cannot read relations for %r: %s", account, exc)
        return {}
    out: dict[str, dict] = {}
    for row in rows:
        handle = str(row.get("handle") or "").strip().lower().lstrip("@")
        if handle:
            out[handle] = row  # last row wins: the store is append-only
    return out


#: Relationship escalation ladder (constitution §14.4). Higher = warmer.
#:
#: THIS TABLE SCORED EVERY REAL ROW AT ZERO UNTIL XG-W4b, and it did it
#: silently. The vocabulary below was written against a ladder that was never
#: built: `persona_memory.RELATION_STAGES` — the CLOSED set `record_relation`
#: validates against, and the only vocabulary that can ever appear in
#: relations.jsonl — is `{"", cold, engaged, reciprocal, declined}`. The two
#: production writers use exactly two of those words (`reply_export` records
#: `engaged` when a reply is confirmed sent, `reply_producer` records
#: `reciprocal` when the author answers us), and NEITHER appeared here. So
#: `_STAGE_SCALE.get(stage, 0.0)` returned the 0.0 default for every row the
#: store will ever hold, the `relationship_stage` feature was dead weight at any
#: weight, and the failure was invisible because 0.0 is also the honest answer
#: for an ABSENT store — the state the desk is in today at M0. The feature would
#: have looked correct right up to the moment it mattered.
#:
#: The live vocabulary is now first-class. `seen`/`liked`/`replied`/`recurring`
#: are retained as aliases of their nearest live stage rather than deleted, so a
#: historical row written before the closed vocabulary existed still scores
#: something rather than silently reverting to the same 0.0 this defect was.
_STAGE_SCALE: dict[str, float] = {
    # The live vocabulary (persona_memory.RELATION_STAGES).
    "": 0.0,
    "cold": 0.0,
    # We have demonstrably spoken to them (a receipt landed).
    "engaged": 0.60,
    # They answered us — the charter's highest-value outcome.
    "reciprocal": 1.0,
    # They declined engagement. The LOWEST rung, deliberately equal to cold and
    # never negative: this feature is a ranking prior, and the actual "do not
    # approach" enforcement is the warmth suppression in persona_model, not a
    # number that a re-weighting could flip.
    "declined": 0.0,
    # Legacy aliases — see the WHY above.
    "seen": 0.25,
    "liked": 0.50,
    "replied": 0.60,
    "recurring": 1.0,
}


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
def _age_fit(age_min: float, p: dict) -> float:
    """1.0 inside the reply window, ramping in and decaying out.

    A reply is worth most when the conversation is current but not saturated.
    Before the window the thread has not gathered an audience; long after it,
    the reply is invisible and the draft is dead weight (which is why the queue
    expires it rather than holding it).
    """
    open_m = float(p["window_open_min"])
    close_m = float(p["window_close_min"])
    if open_m <= age_min <= close_m:
        return 1.0
    if age_min < open_m:
        ramp = float(p["pre_window_ramp_min"]) or 1.0
        return _clamp01(1.0 - (open_m - age_min) / ramp * 0.5)
    decay = float(p["post_window_decay_min"]) or 1.0
    return _clamp01(1.0 - (age_min - close_m) / decay)


def features(
    target: dict,
    *,
    persona_beats: list[str] | None = None,
    now: datetime | None = None,
    params: dict | None = None,
    relations: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Compute every scoring feature for one target. No I/O, no LLM."""
    p = {**DEFAULT_PARAMS, **(params or {})}
    ts = now or datetime.now(timezone.utc)

    tier = str(target.get("author_tier") or "unknown").lower()
    tier_prior = DEFAULT_TIER_PRIOR.get(tier, DEFAULT_TIER_PRIOR["unknown"])

    created = _parse_when(target.get("created_at"))
    age_min = max(0.0, (ts - created).total_seconds() / 60.0) if created else float("inf")
    age_fit = _age_fit(age_min, p) if created else 0.0

    replies = float(target.get("reply_count") or 0)
    likes = float(target.get("like_count") or 0)
    reposts = float(target.get("retweet_count") or 0)
    engagement = replies + likes + reposts

    if created and age_min > 0:
        per_min = engagement / age_min
        hot = float(p["velocity_hot"]) or 1.0
        velocity = _clamp01(math.log1p(per_min) / math.log1p(hot))
    else:
        velocity = 0.0

    full = float(p["saturation_full"]) or 1.0
    saturation = _clamp01(1.0 - replies / full)  # already a "room left" score

    beats = {str(b).lower() for b in (persona_beats or [])}
    beat_tokens: set[str] = set()
    for b in beats:
        beat_tokens |= _tokens(b)
    post_tokens = _tokens(target.get("text"))
    beat_fit = (
        _clamp01(len(beat_tokens & post_tokens) / max(1, min(len(beat_tokens), 12)))
        if beat_tokens else 0.0
    )

    own_post = 1.0 if target.get("kind") in {"mention", "our_post_reply"} else 0.0

    handle = str(target.get("author") or "").lower().lstrip("@")
    rel_row = (relations or {}).get(handle)
    if rel_row is None:
        rel_stage, rel_source = 0.0, ("absent" if relations is None else "unseen")
    else:
        rel_stage = _STAGE_SCALE.get(str(rel_row.get("stage") or "cold").lower(), 0.0)
        rel_source = "relations.jsonl"

    return {
        "author_tier": round(tier_prior, 6),
        "age_fit": round(age_fit, 6),
        "velocity": round(velocity, 6),
        "saturation": round(saturation, 6),
        "beat_fit": round(beat_fit, 6),
        "own_post": own_post,
        "relationship_stage": round(rel_stage, 6),
        # Inspection context — not scored, but printed so a re-weighting can be
        # argued from the record instead of re-polling twitterapi.io.
        "_context": {
            "tier": tier,
            "age_min": None if created is None else round(age_min, 2),
            "reply_count": replies,
            "engagement": engagement,
            "relationship_source": rel_source,
        },
    }


def score_target(
    target: dict,
    *,
    persona_beats: list[str] | None = None,
    cfg: dict | None = None,
    now: datetime | None = None,
    relations: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Score one target. Returns {score, components, features, eligible}.

    ``components`` is the per-feature CONTRIBUTION (weight x feature), which is
    what gets persisted on the queue item: it answers "why did this rank here"
    without the reader needing the weight table in front of them.
    """
    rd = ((cfg or {}).get("reply_desk") or {})
    weights = {**DEFAULT_WEIGHTS, **(rd.get("score_weights") or {})}
    params = {**DEFAULT_PARAMS, **(rd.get("score_params") or {})}

    feats = features(target, persona_beats=persona_beats, now=now,
                     params=params, relations=relations)
    components: dict[str, float] = {}
    total = 0.0
    weight_sum = 0.0
    for name, weight in weights.items():
        if name not in feats:
            log.warning("reply_score: unknown weight %r — ignored", name)
            continue
        contribution = float(weight) * float(feats[name])
        components[name] = round(contribution, 6)
        total += contribution
        weight_sum += float(weight)

    score = round(total / weight_sum, 6) if weight_sum else 0.0
    return {
        "score": score,
        "components": components,
        "features": feats,
        "eligible": score >= float(params["min_score"]),
        "min_score": float(params["min_score"]),
    }


def rank(
    targets: list[dict],
    *,
    persona_beats: list[str] | None = None,
    cfg: dict | None = None,
    now: datetime | None = None,
    relations: dict[str, dict] | None = None,
) -> list[dict]:
    """Score and sort targets, best first. Ties break on status id for stability."""
    scored: list[dict] = []
    for t in targets:
        result = score_target(t, persona_beats=persona_beats, cfg=cfg, now=now,
                              relations=relations)
        scored.append({**t, "score": result["score"], "score_components": result["components"],
                       "score_features": result["features"], "eligible": result["eligible"]})
    scored.sort(key=lambda r: (-float(r["score"]), str(r.get("status_id") or "")))
    return scored


__all__ = [
    "DEFAULT_WEIGHTS", "DEFAULT_PARAMS", "DEFAULT_TIER_PRIOR",
    "features", "score_target", "rank", "load_relations",
]
