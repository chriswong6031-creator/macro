"""engine/market_structure_context.py — Market Structure context change-feed.

Same-day-idempotent change-feed for the market_structure_context.v1 artifact.
Pattern mirrors engine/transmission_context.py (build_changes / compact_state /
diff_changes) — adapted to the market-structure fingerprint keys.

PUBLIC API
----------
compact_state(artifact)  → dict   fingerprint of the 6 tracked state keys
diff_changes(prev, curr) → list   ≤6 change items
build_changes(old, new, asof) → (changes_block, prev_state_block)

HOUSE LAWS
----------
* Display-tier context only; display_only=True on every emitted item.
* Fail-open everywhere — absent/corrupt input → empty changes, never raises.
* MSP-R3: the fingerprint contains NO fused numeric composite.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_MAX_CHANGES = 6

# Fingerprint keys tracked for state change detection
_FINGERPRINT_KEYS = [
    "gamma_regime",
    "vc_state",
    "cta_state",
    "agreement",
    "rv_cross_state",
    "cor1m_regime",
]

# Importance ordering for capping at 6
_DIFF_ORDER = _FINGERPRINT_KEYS

# ---------------------------------------------------------------------------
# Label maps (bilingual)
# ---------------------------------------------------------------------------

_GAMMA_REGIME_LABELS: dict[str, tuple[str, str]] = {
    "long":  ("Dealers long gamma (absorbing)", "庄家净多伽马（吸收波动）"),
    "short": ("Dealers short gamma (amplifying)", "庄家净空伽马（放大波动）"),
}

_FLOW_STATE_LABELS: dict[str, tuple[str, str]] = {
    "adding":  ("adding",  "加仓"),
    "pausing": ("pausing", "暂停"),
    "cutting": ("cutting", "减仓"),
}

_AGREEMENT_LABELS: dict[str, tuple[str, str]] = {
    "aligned_adding":  ("Aligned adding",  "一致加仓"),
    "aligned_cutting": ("Aligned cutting", "一致减仓"),
    "paused":          ("Both pausing",    "双方暂停"),
    "split":           ("Split",           "分歧"),
}

_RV_CROSS_LABELS: dict[str, tuple[str, str]] = {
    "stress": ("Stress (short-term vol elevated)", "压力（短期波动率偏高）"),
    "calm":   ("Calm",                             "平静"),
}

_COR1M_REGIME_LABELS: dict[str, tuple[str, str]] = {
    "elevated":   ("Elevated correlation (crowded)", "相关性偏高（拥挤）"),
    "normal":     ("Normal correlation",              "正常相关性"),
    "dispersion": ("Dispersion (stock-picker's market)", "分散（选股市场）"),
}


def _label_pair(mapping: dict, key: str | None) -> tuple[str, str]:
    if key and key in mapping:
        return mapping[key]
    return (key or "—", key or "—")


# ---------------------------------------------------------------------------
# compact_state
# ---------------------------------------------------------------------------

def compact_state(artifact: dict | None) -> dict:
    """Extract a 6-key comparison fingerprint from a market_structure artifact.

    All keys fail-open to None.  No numeric composites (MSP-R3).
    """
    if not isinstance(artifact, dict):
        return {k: None for k in _FINGERPRINT_KEYS}

    gamma = artifact.get("gamma") or {}
    sys_block = artifact.get("systematic") or {}
    vc = sys_block.get("vc") or {}
    cta = sys_block.get("cta") or {}
    vol = artifact.get("vol") or {}
    disp = artifact.get("dispersion") or {}

    return {
        "gamma_regime":   gamma.get("regime"),
        "vc_state":       vc.get("state"),
        "cta_state":      cta.get("state"),
        "agreement":      sys_block.get("agreement"),
        "rv_cross_state": vol.get("rv_cross_state"),
        "cor1m_regime":   disp.get("cor1m_regime"),
    }


# ---------------------------------------------------------------------------
# diff_changes
# ---------------------------------------------------------------------------

def diff_changes(prev: dict, curr: dict) -> list[dict]:
    """Compare two compact_state dicts; emit at most 6 change items.

    None-side transitions (first appearance) are skipped — no noise on debut.
    """
    candidates: list[tuple[int, dict]] = []

    def _add(key: str, old, new, en: str, zh: str):
        if old is None or new is None:
            return
        if old == new:
            return
        idx = _DIFF_ORDER.index(key) if key in _DIFF_ORDER else 99
        candidates.append((idx, {
            "key": key,
            "from": old,
            "to": new,
            "note_en": en,
            "note_zh": zh,
            "display_only": True,
        }))

    # gamma_regime
    if prev.get("gamma_regime") != curr.get("gamma_regime"):
        oe, oz = _label_pair(_GAMMA_REGIME_LABELS, prev.get("gamma_regime"))
        ne, nz = _label_pair(_GAMMA_REGIME_LABELS, curr.get("gamma_regime"))
        _add("gamma_regime", prev.get("gamma_regime"), curr.get("gamma_regime"),
             f"Dealer gamma regime: {oe} → {ne}",
             f"庄家伽马机制：{oz} → {nz}")

    # vc_state
    if prev.get("vc_state") != curr.get("vc_state"):
        oe, oz = _label_pair(_FLOW_STATE_LABELS, prev.get("vc_state"))
        ne, nz = _label_pair(_FLOW_STATE_LABELS, curr.get("vc_state"))
        _add("vc_state", prev.get("vc_state"), curr.get("vc_state"),
             f"Vol-control funds: {oe} → {ne}",
             f"波动率控制基金：{oz} → {nz}")

    # cta_state
    if prev.get("cta_state") != curr.get("cta_state"):
        oe, oz = _label_pair(_FLOW_STATE_LABELS, prev.get("cta_state"))
        ne, nz = _label_pair(_FLOW_STATE_LABELS, curr.get("cta_state"))
        _add("cta_state", prev.get("cta_state"), curr.get("cta_state"),
             f"CTA funds: {oe} → {ne}",
             f"CTA基金：{oz} → {nz}")

    # agreement
    if prev.get("agreement") != curr.get("agreement"):
        oe, oz = _label_pair(_AGREEMENT_LABELS, prev.get("agreement"))
        ne, nz = _label_pair(_AGREEMENT_LABELS, curr.get("agreement"))
        _add("agreement", prev.get("agreement"), curr.get("agreement"),
             f"Systematic agreement: {oe} → {ne}",
             f"系统化机构一致性：{oz} → {nz}")

    # rv_cross_state
    if prev.get("rv_cross_state") != curr.get("rv_cross_state"):
        oe, oz = _label_pair(_RV_CROSS_LABELS, prev.get("rv_cross_state"))
        ne, nz = _label_pair(_RV_CROSS_LABELS, curr.get("rv_cross_state"))
        _add("rv_cross_state", prev.get("rv_cross_state"), curr.get("rv_cross_state"),
             f"Vol regime: {oe} → {ne}",
             f"波动率状态：{oz} → {nz}")

    # cor1m_regime
    if prev.get("cor1m_regime") != curr.get("cor1m_regime"):
        oe, oz = _label_pair(_COR1M_REGIME_LABELS, prev.get("cor1m_regime"))
        ne, nz = _label_pair(_COR1M_REGIME_LABELS, curr.get("cor1m_regime"))
        _add("cor1m_regime", prev.get("cor1m_regime"), curr.get("cor1m_regime"),
             f"Correlation regime: {oe} → {ne}",
             f"相关性机制：{oz} → {nz}")

    candidates.sort(key=lambda x: x[0])
    return [item for _, item in candidates[:_MAX_CHANGES]]


# ---------------------------------------------------------------------------
# build_changes
# ---------------------------------------------------------------------------

def build_changes(
    old_artifact: dict | None,
    new_artifact: dict,
    new_asof: str,
) -> tuple[dict, dict]:
    """Same-day-idempotent changes block builder.

    Returns (changes_block, prev_state_block).

    Semantics mirror transmission_context.build_changes:
    - old_artifact is None → empty changes, no prev_state.
    - old_artifact["asof"] != new_asof → diff old → new (new day).
    - old_artifact["asof"] == new_asof (same-day rebuild) → reuse the
      prev_state stored in old to avoid phantom re-fires.
    """
    if old_artifact is None:
        return (
            {"vs_asof": None, "items": []},
            {"as_of": None, "state": {}},
        )

    old_asof = old_artifact.get("asof")

    if old_asof != new_asof:
        # New day — diff against yesterday's compact state
        base = compact_state(old_artifact)
        base_asof = old_asof
    else:
        # Same-day rebuild — reuse stored prev_state (idempotent)
        prev_state_stored = old_artifact.get("prev_state") or {}
        base = prev_state_stored.get("state") or {}
        base_asof = prev_state_stored.get("as_of")

    if not base_asof or not base:
        items: list[dict] = []
    else:
        new_cs = compact_state(new_artifact)
        items = diff_changes(base, new_cs)

    changes = {"vs_asof": base_asof, "items": items}
    prev_state = {"as_of": base_asof, "state": base}
    return changes, prev_state
