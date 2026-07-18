"""engine.marketing.publication — Publication receipts, desk network, correction bus.

Pure in-memory dataclasses and helpers — no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# DeskAccount
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DeskAccount:
    id: str
    handle: str | None         # None until assigned
    kind: str                  # branded | generic
    beat: str
    voice: str
    corpus: str
    tilt: dict = field(default_factory=dict)          # per-type weight map (spec §2.4)
    mix_observed: dict = field(default_factory=dict)  # observed counts (spec §2.5)
    stage: str = "A"
    status: str = "warming"
    authority: str = "G1"
    health: dict = field(default_factory=lambda: {
        "warnings": 0,
        "followers": None,
        "engagement": None,
    })

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "handle": self.handle,
            "kind": self.kind,
            "beat": self.beat,
            "voice": self.voice,
            "corpus": self.corpus,
            "tilt": dict(self.tilt),
            "mix_observed": dict(self.mix_observed),
            "stage": self.stage,
            "status": self.status,
            "authority": self.authority,
            "health": dict(self.health),
        }


# ─────────────────────────────────────────────────────────────────────────────
# desk_network
# ─────────────────────────────────────────────────────────────────────────────

def desk_network(cfg: dict | None = None) -> dict[str, Any]:
    """Build desk network state from config/marketing.yml ``desk_network`` section.

    Returns the state dict used in marketing_state.json §3.
    """
    dn_cfg = (cfg or {}).get("desk_network", {}) or {}
    stage = dn_cfg.get("stage", "A")
    raw_accounts = dn_cfg.get("accounts", []) or []

    accounts: list[DeskAccount] = []
    for acct in raw_accounts:
        accounts.append(DeskAccount(
            id=acct.get("id", ""),
            handle=acct.get("handle", None),
            kind=acct.get("kind", "generic"),
            beat=acct.get("beat", ""),
            voice=acct.get("voice", ""),
            corpus=acct.get("corpus", "full"),
            tilt=dict(acct.get("tilt", {})),
            mix_observed={},
            stage=stage,
            status="warming",
            authority="G1",
        ))

    # Compute distinctness across beats (token-Jaccard on beat strings)
    from engine.marketing.campaign_compiler import distinctness as _dist
    beats = [a.beat for a in accounts]
    dist = _dist(beats)

    return {
        "stage": stage,
        "actuation": {
            "path": "human_in_loop",
            "api_eligible": False,
            "control_loop": "drafted",
        },
        "distinctness": {
            "max_similarity": dist["max_similarity"],
            "flags": dist["flags"],
        },
        "accounts": [a.as_dict() for a in accounts],
    }


# ─────────────────────────────────────────────────────────────────────────────
# PublicationReceipt
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PublicationReceipt:
    publication_id: str
    asset_id: str
    channel: str
    account: str
    remote_id: str | None
    published_at: str
    effective_copy_hash: str
    policy_version: str
    audience: str
    destination: str
    campaign_id: str
    experiment_cell: str | None
    correction_state: str = "clean"
    takedown_method: str = "unpublish_via_adapter"
    mode: str = "shadow"

    def as_dict(self) -> dict:
        return {
            "publication_id": self.publication_id,
            "asset_id": self.asset_id,
            "channel": self.channel,
            "account": self.account,
            "remote_id": self.remote_id,
            "published_at": self.published_at,
            "effective_copy_hash": self.effective_copy_hash,
            "policy_version": self.policy_version,
            "audience": self.audience,
            "destination": self.destination,
            "campaign_id": self.campaign_id,
            "experiment_cell": self.experiment_cell,
            "correction_state": self.correction_state,
            "takedown_method": self.takedown_method,
            "mode": self.mode,
        }


# ─────────────────────────────────────────────────────────────────────────────
# CorrectionBus
# ─────────────────────────────────────────────────────────────────────────────

class CorrectionBus:
    """Given a changed claim id, return derivative asset ids.

    Pure in-memory — no persistence.  The caller provides the claim passport
    registry (list of dicts with claim_id + derivative_asset_ids).
    """

    def __init__(self, claim_registry: list[dict[str, Any]]) -> None:
        self._index: dict[str, list[str]] = {}
        for c in claim_registry:
            cid = c.get("claim_id", "")
            if cid:
                self._index[cid] = c.get("derivative_asset_ids", [])

    def derivatives(self, claim_id: str) -> list[str]:
        """Return derivative asset ids for the given claim_id."""
        return list(self._index.get(claim_id, []))
