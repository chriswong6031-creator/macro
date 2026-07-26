"""engine.marketing.ad_creative — what an ad *is*, and what refuses to become one.

Ad Central spine, module 1 of 5 (`research/AD_CENTRAL_MASTERPLAN.md` §3).

A creative is a typed object, not a string:

    angle × hook × proof × cta × format × destination × claim_passport

`format` carries the placement's hard limits.  Assembly **refuses** rather than
truncates: a headline that does not fit Google's 30 characters is not a shorter
headline, it is a different claim.  A creative whose proof line has no claim
passport is refused at build time (masterplan §0 G-F), never at review time.

Deterministic.  No LLM calls, no randomness, no I/O.  Same inputs ⇒ same
`creative_id` (masterplan §0 G-G).

The destination is the canonical UTM link with ``utm_content = creative_id``, so
the existing attribution join (`attribution.py`, keyed on ``utm_content``)
already knows how to score a creative without a single new field.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .links import canonical_link

# ─────────────────────────────────────────────────────────────────────────────
# Placement formats
#
# Limits are the platforms' own, not ours.  `body_max` for Meta/Reddit is the
# *effective* limit (where the placement truncates in-feed), not the API ceiling —
# an ad that gets clipped mid-proof is an ad that lost its proof.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AdFormat:
    format_id: str
    plane: str                  # owned | organic | paid
    headline_max: int
    body_max: int
    cta_max: int
    links_allowed: bool = True
    media_required: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "format_id": self.format_id,
            "plane": self.plane,
            "headline_max": self.headline_max,
            "body_max": self.body_max,
            "cta_max": self.cta_max,
            "links_allowed": self.links_allowed,
            "media_required": self.media_required,
            "note": self.note,
        }


FORMATS: dict[str, AdFormat] = {
    # ── Plane O — owned inventory (our own pages; no external spend) ──────────
    "site_hero": AdFormat(
        "site_hero", "owned", headline_max=64, body_max=180, cta_max=24,
        note="Landing hero — headline, subhead, primary button.",
    ),
    "site_cta": AdFormat(
        "site_cta", "owned", headline_max=48, body_max=120, cta_max=24,
        note="Inline conversion block (pricing, regwall, end-of-page).",
    ),
    # ── Plane G — organic pre-screen (free attention test) ───────────────────
    "x_post": AdFormat(
        "x_post", "organic", headline_max=100, body_max=180, cta_max=0,
        links_allowed=False, media_required=True,
        note="Desk-network post. 280 total across headline+body; links gated by sentinel.",
    ),
    # ── Plane P — paid inventory (adapters; armed off until Phase 5) ─────────
    "google_search": AdFormat(
        "google_search", "paid", headline_max=30, body_max=90, cta_max=0,
        media_required=False,
        note="Responsive search ad — one headline asset (30) + one description (90).",
    ),
    "meta_feed": AdFormat(
        "meta_feed", "paid", headline_max=40, body_max=125, cta_max=20,
        media_required=True,
        note="Feed placement — primary text clips past ~125 in-feed.",
    ),
    "reddit_promoted": AdFormat(
        "reddit_promoted", "paid", headline_max=100, body_max=280, cta_max=20,
        note="Promoted post — title carries the weight; subreddit-native register.",
    ),
    "x_promoted": AdFormat(
        "x_promoted", "paid", headline_max=100, body_max=180, cta_max=20,
        media_required=True,
        note="Promoted post — same 280 ceiling as organic, links permitted.",
    ),
}

PLANES: tuple[str, ...] = ("owned", "organic", "paid")

# Claim types that make a factual assertion about markets or results.  These may
# not ship without a passport.  A pure positioning line ("Know what changed")
# asserts nothing checkable and needs none.
_PASSPORT_REQUIRED_TYPES: frozenset[str] = frozenset({
    "factual", "directional", "causal",
})

# CI forbids this word in user-facing text (`scripts/check_validated_claims.py`).
# Refused here too so it never reaches copy review.
_FORBIDDEN_COPY: tuple[str, ...] = ("validated",)


# ─────────────────────────────────────────────────────────────────────────────
# Creative
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AdCreative:
    creative_id: str
    arena_id: str | None
    opportunity_id: str
    format_id: str
    plane: str
    # dimensions — the axes the matrix crosses
    angle: str                  # the reason to care
    hook: str                   # the first line
    proof: str                  # the receipt
    cta: str
    # assembled
    headline: str
    body: str
    cta_label: str
    destination: str
    claim_passport_id: str | None = None
    claim_type: str = "promotional"
    media_ref: str | None = None
    status: str = "draft"       # draft | refused | live | retired
    refusals: list[str] = field(default_factory=list)
    mode: str = "shadow"        # shadow | live

    def as_dict(self) -> dict:
        return {
            "creative_id": self.creative_id,
            "arena_id": self.arena_id,
            "opportunity_id": self.opportunity_id,
            "format_id": self.format_id,
            "plane": self.plane,
            "angle": self.angle,
            "hook": self.hook,
            "proof": self.proof,
            "cta": self.cta,
            "headline": self.headline,
            "body": self.body,
            "cta_label": self.cta_label,
            "destination": self.destination,
            "claim_passport_id": self.claim_passport_id,
            "claim_type": self.claim_type,
            "media_ref": self.media_ref,
            "status": self.status,
            "refusals": list(self.refusals),
            "mode": self.mode,
        }

    def text(self) -> str:
        """The comparable surface — what distinctness and near-dup checks read."""
        return " ".join(p for p in (self.headline, self.body, self.cta_label) if p)


# ─────────────────────────────────────────────────────────────────────────────
# Id
# ─────────────────────────────────────────────────────────────────────────────

def creative_id(
    opportunity_id: str,
    format_id: str,
    angle: str,
    hook: str,
    proof: str,
    cta: str,
) -> str:
    """Stable id over the content dimensions.

    Two creatives with the same dimensions on the same placement ARE the same
    creative — the id collapses them, so a re-run of the matrix cannot spend
    twice on one ad.
    """
    payload = "\x1f".join((
        str(opportunity_id), str(format_id),
        str(angle), str(hook), str(proof), str(cta),
    ))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return "adc-" + digest[:12]


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────

def _fits(value: str, limit: int) -> bool:
    """True when *value* fits *limit*.  A limit of 0 means the field must be empty."""
    if limit <= 0:
        return not value.strip()
    return len(value) <= limit


def build(
    *,
    opportunity_id: str,
    format_id: str,
    angle: str,
    hook: str,
    proof: str,
    cta: str,
    claim_passport_id: str | None = None,
    claim_type: str = "promotional",
    arena_id: str | None = None,
    media_ref: str | None = None,
    account_id: str = "adcentral",
    campaign_kind: str = "ad",
    base_url: str | None = None,
    utm_source: str | None = None,
    mode: str = "shadow",
) -> AdCreative:
    """Assemble one creative.  Never raises.

    Returns a creative with ``status="refused"`` and a populated ``refusals``
    list when any gate fails — the matrix filters those out, so a refusal is a
    dropped variant, never a crashed fan-out.

    Gates
    -----
    unknown format            the placement does not exist
    over limit                headline/body/cta exceed the placement's caps
    missing passport          a factual/directional/causal claim with no passport
    forbidden copy            CI-forbidden vocabulary
    media required            placement needs media and none was supplied
    """
    fmt = FORMATS.get(str(format_id))
    refusals: list[str] = []

    # Assemble first so a refused creative still carries readable copy for the
    # operator console — "this is what we would have said, and why we didn't".
    headline = str(hook).strip()
    body = " ".join(p for p in (str(angle).strip(), str(proof).strip()) if p)
    cta_label = str(cta).strip()

    cid = creative_id(opportunity_id, format_id, angle, hook, proof, cta)
    # The destination depends only on the creative id, so even a refused creative
    # gets one — the console can then show exactly where it would have pointed.
    destination = canonical_link(
        account_id, campaign_kind, cid,
        base_url=base_url, utm_source=utm_source,
    )

    if fmt is None:
        return AdCreative(
            creative_id=cid, arena_id=arena_id, opportunity_id=str(opportunity_id),
            format_id=str(format_id), plane="unknown",
            angle=str(angle), hook=str(hook), proof=str(proof), cta=str(cta),
            headline=headline, body=body, cta_label=cta_label,
            destination=destination,
            claim_passport_id=claim_passport_id, claim_type=str(claim_type),
            media_ref=media_ref, status="refused",
            refusals=[f"unknown_format:{format_id}"], mode=str(mode),
        )

    # ── limits ───────────────────────────────────────────────────────────────
    if not _fits(headline, fmt.headline_max):
        refusals.append(f"headline_over_limit:{len(headline)}>{fmt.headline_max}")
    if not _fits(body, fmt.body_max):
        refusals.append(f"body_over_limit:{len(body)}>{fmt.body_max}")
    if not _fits(cta_label, fmt.cta_max):
        if fmt.cta_max <= 0 and cta_label:
            refusals.append(f"cta_not_supported_on:{fmt.format_id}")
        else:
            refusals.append(f"cta_over_limit:{len(cta_label)}>{fmt.cta_max}")

    # ── empties ──────────────────────────────────────────────────────────────
    if not headline:
        refusals.append("empty_headline")
    if not body:
        refusals.append("empty_body")

    # ── passport (masterplan §0 G-F) ─────────────────────────────────────────
    if str(claim_type) in _PASSPORT_REQUIRED_TYPES and not claim_passport_id:
        refusals.append(f"missing_claim_passport:{claim_type}")

    # ── forbidden copy ───────────────────────────────────────────────────────
    haystack = f"{headline} {body} {cta_label}".lower()
    for word in _FORBIDDEN_COPY:
        if word in haystack:
            refusals.append(f"forbidden_copy:{word}")

    # ── media ────────────────────────────────────────────────────────────────
    if fmt.media_required and not media_ref:
        refusals.append(f"media_required_on:{fmt.format_id}")

    return AdCreative(
        creative_id=cid,
        arena_id=arena_id,
        opportunity_id=str(opportunity_id),
        format_id=fmt.format_id,
        plane=fmt.plane,
        angle=str(angle), hook=str(hook), proof=str(proof), cta=str(cta),
        headline=headline, body=body, cta_label=cta_label,
        destination=destination,
        claim_passport_id=claim_passport_id,
        claim_type=str(claim_type),
        media_ref=media_ref,
        status="refused" if refusals else "draft",
        refusals=refusals,
        mode=str(mode),
    )


def formats_for_plane(plane: str) -> list[AdFormat]:
    """Every placement on *plane*, in stable id order."""
    return sorted(
        (f for f in FORMATS.values() if f.plane == plane),
        key=lambda f: f.format_id,
    )


def summarize(creatives: list[AdCreative | dict[str, Any]]) -> dict[str, Any]:
    """Counts by status + a refusal histogram.  Refusals are printed, not hidden."""
    rows = [c.as_dict() if isinstance(c, AdCreative) else dict(c) for c in creatives]
    histogram: dict[str, int] = {}
    for r in rows:
        for reason in (r.get("refusals") or []):
            key = str(reason).split(":", 1)[0]
            histogram[key] = histogram.get(key, 0) + 1
    return {
        "total": len(rows),
        "draft": sum(1 for r in rows if r.get("status") == "draft"),
        "refused": sum(1 for r in rows if r.get("status") == "refused"),
        "live": sum(1 for r in rows if r.get("status") == "live"),
        "refusal_histogram": dict(sorted(histogram.items())),
    }
