"""Canonical Bitcoin Vector decision projection.

``btc.decision/v1`` is the single user-action contract for Bitcoin Vector.  It
projects the final, already-governed ``alloc_optimal`` series into an exact action
and exposure.  It does not rescore Bitcoin, choose a Kelly fraction, retune any
signal, or create another store.

Analytical reads (Kelly, momentum state, valuation, risk, cones) remain receipts.
They may explain or challenge the final allocation, but they cannot silently emit a
second target exposure.
"""
from __future__ import annotations

from datetime import datetime
import math
from typing import Any

import pandas as pd

SCHEMA = "btc.decision/v1"
MATERIAL_CHANGE_PP = 10.0
_EPS_PP = 0.05


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _bool(value: Any) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "active"}
    try:
        return bool(int(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _date_text(value: Any) -> str | None:
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001 - malformed clock becomes unavailable, never a crash
        return None


def _unavailable(as_of: str | None, code: str, detail: str) -> dict:
    return {
        "schema": SCHEMA,
        "status": "unavailable",
        "as_of": as_of,
        "error": {"code": code, "detail": detail},
        "authority": {
            "program": "crypto-intelligence",
            "source": "bitcoin_vector",
            "allocation_variant": "optimal",
        },
    }


def _action(final_pct: int, previous_pct: int | None, change_pp: float | None,
            material_change_pp: float) -> tuple[str, str, str, str]:
    """Deterministically project the final exposure into one exact action."""
    if previous_pct is None or change_pp is None:
        return (
            "set",
            f"SET TO {final_pct}% BTC",
            f"将 BTC 仓位设为 {final_pct}%",
            "bull" if final_pct > 0 else "bear",
        )
    if change_pp >= material_change_pp:
        return (
            "increase",
            f"INCREASE TO {final_pct}% BTC",
            f"将 BTC 仓位提高至 {final_pct}%",
            "bull",
        )
    if change_pp <= -material_change_pp:
        return (
            "reduce",
            f"REDUCE TO {final_pct}% BTC",
            f"将 BTC 仓位降至 {final_pct}%",
            "bear",
        )
    if final_pct <= 0:
        return "stay_out", "STAY OUT · 0% BTC", "保持空仓 · BTC 0%", "bear"
    hold_tone = "bull" if final_pct >= 50 else "neutral"
    return "hold", f"HOLD {final_pct}% BTC", f"维持 BTC {final_pct}% 仓位", hold_tone


def build(
    sig: pd.DataFrame,
    master: dict | None = None,
    advisory: dict | None = None,
    *,
    generated_at: datetime | str | None = None,
    material_change_pp: float = MATERIAL_CHANGE_PP,
) -> dict:
    """Build the canonical ``btc.decision/v1`` projection.

    The latest ``alloc_optimal`` value is the sole final exposure authority.  A
    raw/final difference is legal only when the same row carries a named active
    override.  Missing or contradictory authority fails the action contract closed;
    it is never coerced to 0%, neutral, or HOLD.
    """
    if sig is None or sig.empty:
        return _unavailable(None, "missing_signal_frame", "No Bitcoin signal frame was supplied.")

    as_of = _date_text(sig.index[-1])
    if "alloc_optimal" not in sig.columns:
        return _unavailable(
            as_of,
            "missing_authoritative_allocation",
            "alloc_optimal is absent; no final BTC exposure can be asserted.",
        )

    last = sig.iloc[-1]
    final_frac = _finite(last.get("alloc_optimal"))
    if final_frac is None:
        return _unavailable(
            as_of,
            "missing_authoritative_allocation",
            "The latest alloc_optimal value is unavailable.",
        )
    if not 0.0 <= final_frac <= 1.0:
        return _unavailable(
            as_of,
            "invalid_authoritative_allocation",
            f"alloc_optimal={final_frac!r} is outside the lawful [0, 1] range.",
        )

    raw_value = _finite(last.get("alloc_optimal_raw"))
    raw_available = raw_value is not None
    raw_frac = final_frac if raw_value is None else raw_value
    if not 0.0 <= raw_frac <= 1.0:
        return _unavailable(
            as_of,
            "invalid_raw_allocation",
            f"alloc_optimal_raw={raw_frac!r} is outside the lawful [0, 1] range.",
        )

    prior = pd.to_numeric(sig["alloc_optimal"].iloc[:-1], errors="coerce").dropna()
    previous_frac = _finite(prior.iloc[-1]) if len(prior) else None
    if previous_frac is not None and not 0.0 <= previous_frac <= 1.0:
        previous_frac = None

    final_pct = int(round(100.0 * final_frac))
    raw_pct = int(round(100.0 * raw_frac))
    previous_pct = int(round(100.0 * previous_frac)) if previous_frac is not None else None
    change_pp = round(100.0 * (final_frac - previous_frac), 1) if previous_frac is not None else None
    raw_final_delta_pp = round(100.0 * (final_frac - raw_frac), 3)

    override_active = _bool(last.get("override_active"))
    override_id = _clean_text(last.get("override_id"))
    override_released = _bool(last.get("override_released"))
    override_release_frac = _finite(last.get("override_release_frac"))
    reentry_trigger = _clean_text(last.get("reentry_trigger"))

    named_active_override = bool(override_active and override_id)
    delta_requires_override = abs(raw_final_delta_pp) > _EPS_PP
    raw_final_valid = (not delta_requires_override) or named_active_override
    override_identity_valid = (not override_active) or bool(override_id)

    if not raw_final_valid or not override_identity_valid:
        code = "unnamed_raw_final_conflict" if delta_requires_override else "unnamed_active_override"
        detail = (
            f"Raw exposure {raw_pct}% and final exposure {final_pct}% differ by "
            f"{raw_final_delta_pp:+.3f}pp without a named active override."
            if delta_requires_override
            else "override_active is true but override_id is empty."
        )
        return {
            "schema": SCHEMA,
            "status": "conflict",
            "as_of": as_of,
            "error": {"code": code, "detail": detail},
            "authority": {
                "program": "crypto-intelligence",
                "source": "bitcoin_vector",
                "allocation_variant": "optimal",
            },
            "raw_model": {"exposure_pct": raw_pct},
            "override": {"active": override_active, "override_id": override_id},
            "final": {"exposure_pct": final_pct},
            "integrity": {
                "raw_final_delta_has_named_override": False,
                "action_projects_final_exposure": False,
            },
        }

    action_code, action_en, action_zh, tone = _action(
        final_pct, previous_pct, change_pp, float(material_change_pp)
    )
    advisory = advisory or {}
    advisory_lo = _finite(advisory.get("exposure_lo"))
    advisory_hi = _finite(advisory.get("exposure_hi"))
    advisory_tone = _clean_text(advisory.get("tone"))
    advisory_band_contains_final = (
        advisory_lo is not None and advisory_hi is not None
        and advisory_lo <= final_pct <= advisory_hi
    )
    advisory_tone_consistent = not (
        (final_pct >= 50 and advisory_tone == "bear")
        or (final_pct <= 0 and advisory_tone == "bull")
    )
    advisory_consistent = advisory_band_contains_final and advisory_tone_consistent
    score_value = _finite((master or {}).get("score"))
    stance = (master or {}).get("band") or (master or {}).get("stance")
    generated = generated_at.isoformat() if isinstance(generated_at, datetime) else generated_at
    kelly_value = _finite(advisory.get("kelly_pct"))

    decision = {
        "schema": SCHEMA,
        "status": "ok",
        "as_of": as_of,
        "generated_at": generated,
        "authority": {
            "program": "crypto-intelligence",
            "source": "bitcoin_vector",
            "allocation_variant": "optimal",
        },
        "raw_model": {
            "stance": stance,
            "master_score": int(round(score_value)) if score_value is not None else None,
            "exposure_pct": raw_pct,
            "raw_series_available": raw_available,
        },
        "override": {
            "active": override_active,
            "override_id": override_id,
            "released": override_released,
            "release_frac": override_release_frac,
            "reentry_trigger": reentry_trigger,
        },
        "final": {
            "exposure_pct": final_pct,
            "previous_exposure_pct": previous_pct,
            "change_pp": change_pp,
            "action_code": action_code,
            "action_en": action_en,
            "action_zh": action_zh,
            "tone": tone,
            "basis_en": (
                "Exact final exposure from the canonical Bitcoin Vector allocation. "
                "Kelly and factor states below are analytical receipts only."
            ),
            "basis_zh": (
                "仓位精确取自比特币向量的最终权威配置。下方 Kelly 与各因子状态仅作分析收据。"
            ),
        },
        "advisory": {
            "posture_en": advisory.get("action"),
            "posture_zh": advisory.get("action_zh"),
            "conviction": advisory.get("conviction"),
            "basis_en": advisory.get("basis_en"),
            "basis_zh": advisory.get("basis_zh"),
            "directional": advisory.get("directional"),
            "levels": advisory.get("levels") or {},
            "rationale": advisory.get("rationale") or [],
            "key_risk_en": advisory.get("key_risk_en"),
            "key_risk_zh": advisory.get("key_risk_zh"),
            "horizon_en": advisory.get("horizon_en"),
            "horizon_zh": advisory.get("horizon_zh"),
        },
        "receipts": {
            "kelly_risk_budget_pct": int(round(kelly_value)) if kelly_value is not None else None,
            "continuous_momentum": _finite(last.get("momentum")),
            "categorical_momentum": _clean_text(last.get("momentum_state")),
            "risk_index": _finite(last.get("risk_index")),
            "risk_regime": _clean_text(last.get("risk_regime")),
            "valuation_state": _clean_text(last.get("valuation_state")),
            "market_extreme": _clean_text(last.get("market_extreme")),
        },
        "integrity": {
            "final_equals_authoritative_allocation": True,
            "raw_final_delta_pp": raw_final_delta_pp,
            "raw_final_delta_has_named_override": raw_final_valid,
            "action_projects_final_exposure": True,
            "advisory_can_resize": False,
            "advisory_band_contains_final": advisory_band_contains_final,
            "advisory_tone_consistent": advisory_tone_consistent,
            "advisory_consistent_with_final": advisory_consistent,
        },
    }
    return decision
