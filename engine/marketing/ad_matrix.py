"""engine.marketing.ad_matrix — fan-out: one opportunity → many distinct ads.

Ad Central spine, module 2 of 5 (`research/AD_CENTRAL_MASTERPLAN.md` §3).

Crosses the creative dimensions (angle × hook × proof × cta) against the
placements, drops refusals, drops near-duplicates, and caps the matrix.

Two properties this module exists to guarantee:

**Distinctness.**  Fan-out without a distinctness check is buying the same ad N
times and calling it a test.  Pairs above the Jaccard ceiling are dropped, reusing
`campaign_compiler`'s token-Jaccard so Ad Central and the organic lane agree on
what "too similar" means.

**Balanced coverage under a cap.**  `itertools.product` varies the *last* axis
fastest, so taking the first N of a raw cross product yields N ads that all share
angle #1 — a test that can never learn which angle works.  The sweep here is
ordered by total level-distance from the base combination, so a cap of 8 across
3 axes still moves every axis.  What the cap dropped is reported, never silent.

Deterministic.  No LLM calls, no randomness, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any

from . import ad_creative as _ac
from .campaign_compiler import _jaccard, _tokenize

# Same ceiling the organic lane flags at (`campaign_compiler.distinctness`).
DEFAULT_JACCARD_CEILING: float = 0.7
DEFAULT_MAX_CREATIVES: int = 24

# The axes, in the order they compose into copy.  A dimension absent from the
# caller's spec contributes a single empty level (it is simply not tested).
AXES: tuple[str, ...] = ("angle", "hook", "proof", "cta")


# ─────────────────────────────────────────────────────────────────────────────
# Levels
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Level:
    """One setting of one axis.

    `text` is the copy.  `claim_passport_id` / `claim_type` ride on the level
    that makes the assertion — usually `proof` — so the passport gate in
    `ad_creative.build` sees them without the caller re-threading anything.
    """
    level_id: str
    text: str
    claim_passport_id: str | None = None
    claim_type: str | None = None

    def as_dict(self) -> dict:
        return {
            "level_id": self.level_id,
            "text": self.text,
            "claim_passport_id": self.claim_passport_id,
            "claim_type": self.claim_type,
        }


def _coerce_levels(raw: Any) -> list[Level]:
    """Accept Level objects, dicts, or bare strings.  Order is preserved."""
    out: list[Level] = []
    for i, item in enumerate(raw or []):
        if isinstance(item, Level):
            out.append(item)
        elif isinstance(item, dict):
            out.append(Level(
                level_id=str(item.get("level_id") or f"L{i}"),
                text=str(item.get("text") or ""),
                claim_passport_id=item.get("claim_passport_id"),
                claim_type=item.get("claim_type"),
            ))
        else:
            out.append(Level(level_id=f"L{i}", text=str(item)))
    return out or [Level(level_id="L0", text="")]


# ─────────────────────────────────────────────────────────────────────────────
# Balanced sweep order
# ─────────────────────────────────────────────────────────────────────────────

def _balanced_order(sizes: list[int]) -> list[tuple[int, ...]]:
    """Index tuples ordered by distance from the base combination.

    ``sizes=[2,2]`` ⇒ ``(0,0), (0,1), (1,0), (1,1)`` — one axis moves before both
    do.  Under a cap of 3 that still varies each axis once, where the raw product
    order would have spent two of three slots on axis-0 level-0.
    """
    if not sizes:
        return [()]
    combos = list(product(*(range(n) for n in sizes)))
    return sorted(combos, key=lambda idx: (sum(idx), idx))


# ─────────────────────────────────────────────────────────────────────────────
# Fan-out
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MatrixResult:
    opportunity_id: str
    creatives: list[_ac.AdCreative] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    distinctness: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "opportunity_id": self.opportunity_id,
            "creatives": [c.as_dict() for c in self.creatives],
            "dropped": list(self.dropped),
            "distinctness": dict(self.distinctness),
            "coverage": dict(self.coverage),
            "counts": dict(self.counts),
        }


def fan_out(
    *,
    opportunity_id: str,
    formats: list[str],
    angles: Any = None,
    hooks: Any = None,
    proofs: Any = None,
    ctas: Any = None,
    max_creatives: int = DEFAULT_MAX_CREATIVES,
    jaccard_ceiling: float = DEFAULT_JACCARD_CEILING,
    arena_id: str | None = None,
    media_ref: str | None = None,
    account_id: str = "adcentral",
    campaign_kind: str = "ad",
    base_url: str | None = None,
    utm_source: str | None = None,
    mode: str = "shadow",
) -> MatrixResult:
    """Cross the axes against the placements.  Never raises.

    Drop order is deliberate and reported separately for each cause:
      1. ``refused``    — the placement's own gates (limits, passport, media)
      2. ``near_dup``   — Jaccard above the ceiling against an already-kept ad
      3. ``cap``        — the matrix cap, applied last so it never masks a gate

    Returns a `MatrixResult`.  `coverage` reports how many distinct levels of
    each axis survived: an axis that collapsed to one level is an axis this test
    cannot learn anything about, and the caller needs to see that before spending.
    """
    levels: dict[str, list[Level]] = {
        "angle": _coerce_levels(angles),
        "hook": _coerce_levels(hooks),
        "proof": _coerce_levels(proofs),
        "cta": _coerce_levels(ctas),
    }
    fmt_ids = [str(f) for f in (formats or [])]

    kept: list[_ac.AdCreative] = []
    kept_tokens: list[frozenset[str]] = []
    dropped: list[dict] = []
    seen_ids: set[str] = set()

    sizes = [len(levels[a]) for a in AXES]
    order = _balanced_order(sizes)

    # Placement is the OUTER loop: a cap should thin each placement's sweep
    # evenly rather than exhaust the first placement and starve the rest.
    per_format_cap = max(1, max_creatives // len(fmt_ids)) if fmt_ids else 0
    for fmt_id in fmt_ids:
        taken_here = 0
        for idx in order:
            picked = {axis: levels[axis][idx[i]] for i, axis in enumerate(AXES)}
            # A claim passport declared on any axis governs the whole creative;
            # `proof` wins when several declare one (it is the axis that asserts).
            passport = None
            claim_type = "promotional"
            for axis in ("angle", "hook", "cta", "proof"):
                lvl = picked[axis]
                if lvl.claim_passport_id or lvl.claim_type:
                    passport = lvl.claim_passport_id or passport
                    claim_type = lvl.claim_type or claim_type

            creative = _ac.build(
                opportunity_id=opportunity_id,
                format_id=fmt_id,
                angle=picked["angle"].text,
                hook=picked["hook"].text,
                proof=picked["proof"].text,
                cta=picked["cta"].text,
                claim_passport_id=passport,
                claim_type=claim_type,
                arena_id=arena_id,
                media_ref=media_ref,
                account_id=account_id,
                campaign_kind=campaign_kind,
                base_url=base_url,
                utm_source=utm_source,
                mode=mode,
            )

            if creative.creative_id in seen_ids:
                continue
            seen_ids.add(creative.creative_id)

            if creative.status == "refused":
                dropped.append({
                    "creative_id": creative.creative_id,
                    "format_id": fmt_id,
                    "cause": "refused",
                    "detail": list(creative.refusals),
                })
                continue

            tokens = _tokenize(creative.text())
            worst = 0.0
            for prior in kept_tokens:
                sim = _jaccard(tokens, prior)
                if sim > worst:
                    worst = sim
            if worst > jaccard_ceiling:
                dropped.append({
                    "creative_id": creative.creative_id,
                    "format_id": fmt_id,
                    "cause": "near_dup",
                    "detail": [f"jaccard={round(worst, 4)}>{jaccard_ceiling}"],
                })
                continue

            if len(kept) >= max_creatives or taken_here >= per_format_cap:
                dropped.append({
                    "creative_id": creative.creative_id,
                    "format_id": fmt_id,
                    "cause": "cap",
                    "detail": [f"max_creatives={max_creatives}"],
                })
                continue

            kept.append(creative)
            kept_tokens.append(tokens)
            taken_here += 1

    coverage = {
        axis: {
            "levels_offered": len(levels[axis]),
            "levels_surviving": len({getattr(c, axis) for c in kept}),
        }
        for axis in AXES
    }
    coverage["formats"] = {
        "offered": len(fmt_ids),
        "surviving": len({c.format_id for c in kept}),
    }

    distinct = _distinctness_of(kept)
    counts = {
        "built": len(seen_ids),
        "kept": len(kept),
        "dropped_refused": sum(1 for d in dropped if d["cause"] == "refused"),
        "dropped_near_dup": sum(1 for d in dropped if d["cause"] == "near_dup"),
        "dropped_cap": sum(1 for d in dropped if d["cause"] == "cap"),
    }

    return MatrixResult(
        opportunity_id=str(opportunity_id),
        creatives=kept,
        dropped=dropped,
        distinctness=distinct,
        coverage=coverage,
        counts=counts,
    )


def _distinctness_of(creatives: list[_ac.AdCreative]) -> dict[str, Any]:
    """Max pairwise Jaccard across the kept set, and any pair still at the ceiling."""
    if len(creatives) < 2:
        return {"max_similarity": 0.0, "flags": 0, "flagged_pairs": []}
    tokens = [_tokenize(c.text()) for c in creatives]
    max_sim = 0.0
    flagged: list[tuple[str, str, float]] = []
    for i in range(len(tokens)):
        for j in range(i + 1, len(tokens)):
            sim = _jaccard(tokens[i], tokens[j])
            if sim > max_sim:
                max_sim = sim
            if sim > DEFAULT_JACCARD_CEILING:
                flagged.append((
                    creatives[i].creative_id, creatives[j].creative_id, round(sim, 4),
                ))
    return {
        "max_similarity": round(max_sim, 4),
        "flags": len(flagged),
        "flagged_pairs": flagged,
    }
