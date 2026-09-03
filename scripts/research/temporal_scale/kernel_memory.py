"""Exact kernel-memory diagnostics for the temporal-scale research harness."""
from __future__ import annotations

import hashlib
import math
import re
from numbers import Real
from typing import Any, Mapping

import numpy as np
import pandas as pd

from engine.entry_radar import indicator_core
from scripts.research.temporal_scale.contracts import (
    KERNEL_SIGNATURE_SCHEMA,
    ContractError,
    KernelSignature,
    strict_json_dumps,
)


class KernelMemoryError(ValueError):
    """Raised when kernel-memory inputs cannot be attested mechanically."""


_MAX_LENGTH = 2**53 - 1
_CLOCK_BASES = frozenset({"bar_count", "elapsed_time", "traded_time", "volume_time", "trade_time", "variance_time"})


def _length(value: object, name: str) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_LENGTH:
        raise KernelMemoryError(f"{name} length must be a real integer in 1..{_MAX_LENGTH}")
    return value


def _half_life(retention: float) -> float:
    return 0.0 if retention == 0.0 else math.log(0.5) / math.log(retention)


def ema_half_life_bars(length: int) -> float:
    length = _length(length, "EMA")
    return _half_life((length - 1) / (length + 1))


def rma_half_life_bars(length: int) -> float:
    length = _length(length, "RMA")
    return _half_life((length - 1) / length)


def ema_length_for_half_life_bars(target: float) -> int:
    if isinstance(target, bool) or not isinstance(target, Real) or target < 0:
        raise KernelMemoryError("target half-life must be finite and nonnegative")
    try:
        target = float(target)
    except (OverflowError, TypeError, ValueError) as exc:
        raise KernelMemoryError("target half-life must be finite and nonnegative") from exc
    if not math.isfinite(target):
        raise KernelMemoryError("target half-life must be finite and nonnegative")
    if target == 0:
        return 1
    if target > ema_half_life_bars(_MAX_LENGTH):
        raise KernelMemoryError("target half-life exceeds float-representable EMA length")
    denominator = -math.expm1(math.log(0.5) / target)
    if not math.isfinite(denominator) or denominator <= 0:
        raise KernelMemoryError("target half-life cannot be represented safely")
    analytic = 2.0 / denominator - 1.0
    if not math.isfinite(analytic):
        raise KernelMemoryError("target half-life cannot be represented safely")
    center = max(1, min(_MAX_LENGTH, int(round(analytic))))
    # The carrier half-life is computed from a binary float retention.  Its ULP
    # maps through dN/dr = 2/(1-r)^2, so this is a bounded analytic uncertainty
    # neighborhood, not a heuristic or unbounded integer search.
    retention = 1.0 - denominator
    radius = max(3, int(math.ceil(2.0 * math.ulp(retention) / (denominator * denominator))))
    lower = max(1, center - radius)
    upper = min(_MAX_LENGTH, center + radius)
    while lower < upper:
        midpoint = (lower + upper) // 2
        if ema_half_life_bars(midpoint) >= target:
            upper = midpoint
        else:
            lower = midpoint + 1
    candidates = range(max(1, lower - 1), min(_MAX_LENGTH, lower + 1) + 1)
    return min(candidates, key=lambda length: (abs(ema_half_life_bars(length) - target), length))


def _finite_real(value: object, *, name: str, allow_missing: bool) -> float | None:
    if value is None or value is pd.NA:
        if allow_missing:
            return None
        raise KernelMemoryError(f"{name} must be finite")
    if isinstance(value, bool) or not isinstance(value, Real):
        raise KernelMemoryError(f"{name} must be a real scalar")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise KernelMemoryError(f"{name} must be a finite real scalar") from exc
    if math.isnan(normalized):
        if allow_missing:
            return None
        raise KernelMemoryError(f"{name} must be finite")
    if not math.isfinite(normalized):
        raise KernelMemoryError(f"{name} must be finite")
    return normalized


def _numeric_series(values: object, *, name: str, allow_missing: bool, require_finite: bool = False) -> pd.Series:
    if not isinstance(values, pd.Series):
        raise KernelMemoryError(f"{name} must be a pandas Series")
    normalized = [_finite_real(value, name=name, allow_missing=allow_missing) for value in values]
    series = pd.Series([float("nan") if value is None else value for value in normalized], index=values.index, dtype=float)
    if require_finite and not np.isfinite(series.to_numpy()).any():
        raise KernelMemoryError(f"{name} must contain at least one finite value")
    return series


def continuous_ema(values: pd.Series, clock_increments: pd.Series, *, tau: float, seed: float | None = None) -> pd.Series:
    if not isinstance(values, pd.Series) or not isinstance(clock_increments, pd.Series) or not values.index.equals(clock_increments.index):
        raise KernelMemoryError("values and clock increments must be Series with exactly equal indexes")
    tau_value = _finite_real(tau, name="tau", allow_missing=False)
    if tau_value is None or tau_value <= 0:
        raise KernelMemoryError("tau must be positive and finite")
    seed_value = None if seed is None else _finite_real(seed, name="seed", allow_missing=False)
    normalized_values = _numeric_series(values, name="values", allow_missing=True)
    normalized_increments = _numeric_series(clock_increments, name="clock increments", allow_missing=False)
    state = seed_value
    result: list[float] = []
    for value, delta in zip(normalized_values, normalized_increments, strict=True):
        if delta < 0:
            raise KernelMemoryError("clock increments must be finite and nonnegative")
        if not math.isfinite(value):
            result.append(float("nan"))
            continue
        if state is None:
            state = value
        else:
            if delta == 0.0:
                result.append(state)
                continue
            retention = math.exp(-delta / tau_value)
            alpha = 1.0 - retention
            state = retention * state + alpha * value
        result.append(state)
    return pd.Series(result, index=values.index, dtype=float)


def _close_series(close: object) -> pd.Series:
    if not isinstance(close, pd.Series) or len(close) == 0:
        raise KernelMemoryError("close must be a nonempty pandas Series")
    return _numeric_series(close, name="close", allow_missing=True, require_finite=True)


def _first_finite(series: pd.Series) -> int | None:
    positions = np.flatnonzero(np.isfinite(series.to_numpy(dtype=float, na_value=np.nan)))
    return int(positions[0]) if len(positions) else None


def _strict_index_labels(index: pd.Index) -> list[int | str]:
    labels: list[int | str] = []
    for label in index:
        if isinstance(label, bool):
            raise KernelMemoryError("clock vector index labels must be int or str")
        if isinstance(label, (int, np.integer)):
            labels.append(int(label))
        elif isinstance(label, str):
            labels.append(label)
        else:
            raise KernelMemoryError("clock vector index labels must be int or str")
    return labels


def _sha256_json(value: object) -> str:
    return hashlib.sha256(strict_json_dumps(value).encode("utf-8")).hexdigest()


def _clock_provenance(
    close: pd.Series,
    clock_basis: str,
    clock_parameter: Mapping[str, Any] | None,
    clock_increments: pd.Series | None,
) -> Mapping[str, Any]:
    if clock_basis == "bar_count":
        if clock_increments is not None:
            raise KernelMemoryError("bar_count must not receive external clock increments")
        if clock_parameter not in (None, {}):
            raise KernelMemoryError("bar_count must not receive external clock provenance")
        return {}
    if not isinstance(clock_parameter, Mapping):
        raise KernelMemoryError("non-bar clocks require a structured clock_parameter")
    if not isinstance(clock_increments, pd.Series) or not close.index.equals(clock_increments.index):
        raise KernelMemoryError("non-bar clocks require index-aligned actual clock increments")
    unit = clock_parameter.get("unit")
    receipt = clock_parameter.get("source_receipt_sha256")
    if not isinstance(unit, str) or not unit.strip() or not isinstance(receipt, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt):
        raise KernelMemoryError("non-bar clock provenance requires unit and lowercase source receipt SHA-256")
    try:
        strict_json_dumps(dict(clock_parameter))
        labels = _strict_index_labels(close.index)
    except ContractError as exc:
        raise KernelMemoryError("clock provenance must be strict JSON") from exc
    increments = _numeric_series(clock_increments, name="clock increments", allow_missing=False)
    if (increments < 0).any():
        raise KernelMemoryError("clock increments must be finite and nonnegative")
    return {
        "unit": unit,
        "source_receipt_sha256": receipt,
        "actual_vector_sha256": _sha256_json(increments.tolist()),
        "actual_vector_count": len(increments),
        "actual_vector_index_sha256": _sha256_json(labels),
    }


def canonical_kernel_signature(
    close: pd.Series,
    *,
    clock_basis: str = "bar_count",
    clock_parameter: Mapping[str, Any] | None = None,
    clock_increments: pd.Series | None = None,
) -> KernelSignature:
    close = _close_series(close)
    if not isinstance(clock_basis, str) or clock_basis not in _CLOCK_BASES:
        raise KernelMemoryError("clock_basis is unknown")
    parameter = _clock_provenance(close, clock_basis, clock_parameter, clock_increments)
    rsi = indicator_core.rsi(close)
    macd, signal = indicator_core.rsi_macd(close)
    hist = indicator_core.rsi_macd_hist(close)
    stoch_k, stoch_d = indicator_core.stoch_rsi_kd(close)
    spec = {
        "owner_family": "R-A canon (SMA-seeded RMA == Pine ta.rsi)", "owner_module": "engine.canon",
        "owner_public_module": "engine.entry_radar.indicator_core", "input": "close", "rsi_len": 14,
        "macd_fast": 14, "macd_slow": 60, "macd_signal": 5, "stoch_len": 14,
        "smooth_k": 3, "smooth_d": 3, "ema_adjust": False, "rma_seed": "sma_seeded",
    }
    indicator_spec_hash = _sha256_json(spec)
    alpha = {"ema14": 2 / 15, "ema60": 2 / 61, "ema5": 2 / 6, "rma14": 1 / 14}
    return KernelSignature(
        schema_version=KERNEL_SIGNATURE_SCHEMA,
        indicator_spec_hash=indicator_spec_hash,
        input_series="close",
        components=(
            {"name": "rsi", "owner": "engine.entry_radar.indicator_core.rsi"},
            {"name": "rsi_macd", "owner": "engine.entry_radar.indicator_core.rsi_macd"},
            {"name": "rsi_macd_hist", "owner": "engine.entry_radar.indicator_core.rsi_macd_hist"},
            {"name": "stoch_rsi", "owner": "engine.entry_radar.indicator_core.stoch_rsi_kd"},
        ),
        bar_memory={"ema14": ema_half_life_bars(14), "ema60": ema_half_life_bars(60), "ema5": ema_half_life_bars(5), "rma14": rma_half_life_bars(14)},
        clock_basis=clock_basis,
        clock_parameter=parameter,
        warmup_first_finite_index={"rsi": _first_finite(rsi), "rsi_macd": _first_finite(macd), "rsi_macd_signal": _first_finite(signal), "rsi_macd_hist": _first_finite(hist), "stoch_k": _first_finite(stoch_k), "stoch_d": _first_finite(stoch_d)},
        linear_diagnostics={"alpha": alpha, "retention": {"ema14": 13 / 15, "ema60": 59 / 61, "ema5": 4 / 6, "rma14": 13 / 14}, "half_life_bars": {"ema14": ema_half_life_bars(14), "ema60": ema_half_life_bars(60), "ema5": ema_half_life_bars(5), "rma14": rma_half_life_bars(14)}, "clock_provenance": "bar_count" if clock_basis == "bar_count" else parameter},
        nonlinear_caveat="StochRSI rolling min/max and smoothing are not established equivalent by linear half-life matching.",
    )
