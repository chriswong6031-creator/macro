"""Canonical Bitcoin DecisionState projection.

This module does not score Bitcoin, size Bitcoin, fetch data, or persist state.
It validates the existing final BTC allocation and turns it into one deterministic
user action.  Statistical/model outputs remain receipts; none can create a second
target exposure.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import math
from typing import Any

import numpy as np
import pandas as pd

SCHEMA = "btc.decision/v1"
MATERIAL_CHANGE_PP = 10.0
RAW_FINAL_TOLERANCE_PP = 0.5

_ADVISORY_KEYS = (
    "levels",
    "rationale",
    "key_risk_en",
    "key_risk_zh",
    "horizon_en",
    "horizon_zh",
)


def _finite(value: Any) -> float | None:
    """Return a finite float, refusing bool/None/NaN/inf."""
    if value is None or isinstance(value, (bool, np.bool_)):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _bool(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _pct(fraction: float | None) -> float | None:
    return None if fraction is None else round(100.0 * fraction, 6)


def _display_pct(value: float) -> int:
    """Presentation percentage; authoritative fractional value is retained separately."""
    return int(round(value))


def _utc_text(value: datetime | None) -> str:
    dt = value or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_of(index_value: Any) -> str | None:
    try:
        return pd.Timestamp(index_value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return _text(index_value)


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    """Return a JSON-serializable copy of an already-small advisory receipt."""
    if depth >= 8:
        return None
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v, depth=depth + 1) for v in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return deepcopy(value)
    return _text(value)


def _advisory(recommendation: Mapping[str, Any] | None) -> dict[str, Any]:
    rec = recommendation if isinstance(recommendation, Mapping) else {}
    levels = _json_safe(rec.get("levels")) if isinstance(rec.get("levels"), Mapping) else None
    rationale = (
        _json_safe(rec.get("rationale"))
        if isinstance(rec.get("rationale"), (list, tuple))
        else None
    )
    out = {
        "levels": levels,
        "rationale": rationale,
        "key_risk_en": _text(rec.get("key_risk_en")),
        "key_risk_zh": _text(rec.get("key_risk_zh")),
        "horizon_en": _text(rec.get("horizon_en")),
        "horizon_zh": _text(rec.get("horizon_zh")),
    }
    out["authority_class"] = "context_only"
    out["source"] = "engine.btc_recommend"
    out["available"] = bool(
        levels or rationale or any(out.get(key) for key in _ADVISORY_KEYS[2:])
    )
    return out


def _previous_exposure(signals: pd.DataFrame) -> float | None:
    if "alloc_optimal" not in signals:
        return None
    for value in reversed(signals["alloc_optimal"].iloc[:-1].tolist()):
        previous = _finite(value)
        if previous is not None:
            return previous
    return None


def _project_action(current_pct: float, previous_pct: float | None) -> dict[str, Any]:
    shown = _display_pct(current_pct)
    if previous_pct is None:
        code = "SET_EXPOSURE"
        en = f"MODEL TARGET {shown}% BTC"
        zh = f"模型目标仓位 {shown}% BTC"
        change = None
    else:
        change = round(current_pct - previous_pct, 6)
        if change >= MATERIAL_CHANGE_PP:
            code = "INCREASE_EXPOSURE"
            en = f"INCREASE TO {shown}% BTC"
            zh = f"增持至 {shown}% BTC"
        elif change <= -MATERIAL_CHANGE_PP:
            code = "REDUCE_EXPOSURE"
            en = f"REDUCE TO {shown}% BTC"
            zh = f"减持至 {shown}% BTC"
        elif current_pct == 0:
            code = "STAY_OUT"
            en = "STAY OUT — 0% BTC"
            zh = "保持空仓 — 0% BTC"
        else:
            code = "HOLD_EXPOSURE"
            en = f"HOLD {shown}% BTC"
            zh = f"持有 {shown}% BTC"
    return {
        "action_code": code,
        "action_en": en,
        "action_zh": zh,
        "change_pp": change,
    }


def build_decision(
    signals: pd.DataFrame,
    master: Mapping[str, Any] | None,
    *,
    recommendation: Mapping[str, Any] | None = None,
    sizing: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one deterministic, integrity-checked BTC decision projection.

    `signals.alloc_optimal` is the sole final exposure authority.
    `signals.alloc_optimal_raw`, when present, is the pre-override exposure.
    Any raw/final disagreement must be explained by an active named override.
    """
    base: dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": None,
        "generated_at": _utc_text(generated_at),
        "status": "unavailable",
        "authority": {
            "program": "crypto-intelligence",
            "allocation_source": "signals.alloc_optimal",
            "raw_allocation_source": "signals.alloc_optimal_raw",
            "action_method": "deterministic_projection",
            "authority_class": "decision_bearing",
        },
        "raw_model": None,
        "override": None,
        "final": None,
        "advisory": _advisory(recommendation),
        "receipts": {
            "kelly_risk_budget_pct": None,
            "continuous_momentum": None,
            "categorical_momentum": None,
            "risk_index": None,
            "risk_regime": None,
            "valuation_state": None,
            "market_extreme": None,
            "authority_class": "context_only",
        },
        "integrity": {"ok": False, "checks": {}, "errors": []},
    }

    if signals is None or not isinstance(signals, pd.DataFrame) or signals.empty:
        base["integrity"]["errors"].append("EMPTY_SIGNALS")
        return base

    last = signals.iloc[-1]
    base["as_of"] = _as_of(signals.index[-1])

    final = _finite(last.get("alloc_optimal"))
    raw = _finite(last.get("alloc_optimal_raw"))
    previous = _previous_exposure(signals)

    override_active = _bool(last.get("override_active"))
    override_id = _text(last.get("override_id"))
    override_released = _bool(last.get("override_released"))
    release_frac = _finite(last.get("override_release_frac"))

    final_present = final is not None
    final_in_range = bool(final_present and 0.0 <= final <= 1.0)
    raw_in_range = raw is None or 0.0 <= raw <= 1.0
    release_frac_in_range = release_frac is None or 0.0 <= release_frac <= 1.0
    named_override = not override_active or override_id is not None

    mismatch_pp = None
    mismatch = False
    if raw is not None and final_in_range and raw_in_range:
        mismatch_pp = round(abs(raw - final) * 100.0, 6)
        mismatch = mismatch_pp > RAW_FINAL_TOLERANCE_PP
    mismatch_explained = not mismatch or (override_active and override_id is not None)

    checks = {
        "final_present": final_present,
        "final_in_range": final_in_range,
        "raw_in_range_or_absent": raw_in_range,
        "release_frac_in_range_or_absent": release_frac_in_range,
        "active_override_is_named": named_override,
        "raw_final_evaluable": raw is not None and final_in_range and raw_in_range,
        "raw_final_consistent_or_named_override": mismatch_explained,
    }
    errors: list[str] = []
    if not final_present:
        errors.append("MISSING_FINAL_ALLOCATION")
    elif not final_in_range:
        errors.append("FINAL_ALLOCATION_OUT_OF_RANGE")
    if not raw_in_range:
        errors.append("RAW_ALLOCATION_OUT_OF_RANGE")
    if not release_frac_in_range:
        errors.append("OVERRIDE_RELEASE_FRAC_OUT_OF_RANGE")
    if override_active and override_id is None:
        errors.append("ACTIVE_OVERRIDE_WITHOUT_ID")
    if mismatch and not mismatch_explained:
        errors.append("RAW_FINAL_MISMATCH_WITHOUT_NAMED_OVERRIDE")

    master_map = master if isinstance(master, Mapping) else {}
    raw_model = {
        "stance_en": next(
            (
                text
                for text in (
                    _text(master_map.get("band_en")),
                    _text(master_map.get("stance_en")),
                    _text(master_map.get("band")),
                )
                if text is not None
            ),
            None,
        ),
        "stance_zh": next(
            (
                text
                for text in (
                    _text(master_map.get("band_zh")),
                    _text(master_map.get("stance_zh")),
                )
                if text is not None
            ),
            None,
        ),
        "master_score": _finite(master_map.get("score")),
        "exposure": raw if raw_in_range else None,
        "exposure_pct": _pct(raw) if raw_in_range else None,
    }
    override = {
        "active": override_active,
        "override_id": override_id,
        "released": override_released,
        "release_frac": release_frac if release_frac_in_range else None,
        "raw_exposure_pct": _pct(raw) if raw_in_range else None,
        "final_exposure_pct": _pct(final) if final_in_range else None,
        "difference_pp": mismatch_pp,
    }

    sizing_map = sizing if isinstance(sizing, Mapping) else {}
    kelly = _finite(sizing_map.get("size_pct"))
    if kelly is None:
        kelly = _finite(sizing_map.get("kelly_pct"))

    receipts = {
        "kelly_risk_budget_pct": kelly,
        "continuous_momentum": _finite(last.get("momentum")),
        "categorical_momentum": _text(last.get("momentum_state")),
        "risk_index": _finite(last.get("risk_index")),
        "risk_regime": _text(last.get("risk_regime")),
        "valuation_state": _text(last.get("valuation_state")),
        "market_extreme": _text(last.get("market_extreme")),
        "authority_class": "context_only",
    }

    base["raw_model"] = raw_model
    base["override"] = override
    base["receipts"] = receipts

    if errors:
        base["final"] = {
            "exposure": final if final_in_range else None,
            "exposure_pct": _display_pct(_pct(final)) if final_in_range else None,
            "previous_exposure_pct": _pct(previous),
            "change_pp": None,
            "action_code": None,
            "action_en": None,
            "action_zh": None,
        }
        base["integrity"] = {"ok": False, "checks": checks, "errors": errors}
        return base

    current_pct = _pct(final)
    previous_pct = _pct(previous)
    assert current_pct is not None
    action = _project_action(current_pct, previous_pct)
    final_block = {
        "exposure": final,
        "exposure_pct": _display_pct(current_pct),
        "previous_exposure_pct": previous_pct,
        **action,
    }

    # By construction, action copy is generated from this exact target.
    checks["action_projects_final_exposure"] = True
    base["status"] = "ok"
    base["final"] = final_block
    base["integrity"] = {"ok": True, "checks": checks, "errors": []}
    return base
