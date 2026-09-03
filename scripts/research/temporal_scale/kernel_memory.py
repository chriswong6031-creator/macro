"""Exact kernel-memory diagnostics for the temporal-scale research harness."""
from __future__ import annotations

import hashlib
import inspect
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
_OWNER_CONFIG = {
    "family": "R-A canon (SMA-seeded RMA == Pine ta.rsi)", "module": "engine.canon",
    "rsi_len": 14, "stoch_len": 14, "smooth_k": 3, "smooth_d": 3,
    "macd_fast": 14, "macd_slow": 60, "macd_signal": 5,
    "ema_adjust": "adjust=False", "rma_seed": "sma_seeded",
}


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


def _bound_owner_callables() -> tuple[Any, Any, Any, Any]:
    """Fail closed if owner defaults cannot establish the declared frozen recipe."""
    names = ("rsi", "rsi_macd", "rsi_macd_hist", "stoch_rsi_kd")
    functions = tuple(getattr(indicator_core, name, None) for name in names)
    try:
        for function in functions:
            if not callable(function):
                raise KernelMemoryError("owner public signatures cannot bind the frozen recipe")
            parameters = tuple(inspect.signature(function).parameters.values())
            if len(parameters) != 1:
                raise KernelMemoryError("owner public signatures cannot bind the frozen recipe")
            parameter = parameters[0]
            if parameter.name != "close" or parameter.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD or parameter.default is not inspect.Parameter.empty:
                raise KernelMemoryError("owner public signatures cannot bind the frozen recipe")
    except KernelMemoryError:
        raise
    except (TypeError, ValueError, AttributeError) as exc:
        raise KernelMemoryError("owner public signatures cannot bind the frozen recipe") from exc
    try:
        current = indicator_core.INDICATOR_CORE
        if not isinstance(current, Mapping) or any(current.get(key) != value for key, value in _OWNER_CONFIG.items()):
            raise KernelMemoryError("owner public defaults drift from the frozen recipe")
    except (AttributeError, TypeError, ValueError) as exc:
        raise KernelMemoryError("owner public defaults cannot bind the frozen recipe") from exc
    return functions  # type: ignore[return-value]


def _call_owner(function: Any, close: pd.Series, name: str) -> object:
    try:
        return function(close)
    except TypeError as exc:
        raise KernelMemoryError(f"owner {name} rejected the bound close input") from exc


def _owner_series(value: object, close: pd.Series, name: str) -> pd.Series:
    if not isinstance(value, pd.Series) or len(value) != len(close) or not value.index.equals(close.index):
        raise KernelMemoryError(f"owner {name} must return an index-aligned pandas Series")
    return _numeric_series(value, name=f"owner {name}", allow_missing=True)


def _owner_pair(value: object, close: pd.Series, name: str) -> tuple[pd.Series, pd.Series]:
    if type(value) is not tuple or len(value) != 2:
        raise KernelMemoryError(f"owner {name} must return exactly two Series")
    return _owner_series(value[0], close, f"{name}[0]"), _owner_series(value[1], close, f"{name}[1]")


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
        if clock_parameter is not None:
            if not isinstance(clock_parameter, Mapping):
                raise KernelMemoryError("bar_count clock_parameter must be null or an empty mapping")
            try:
                if list(clock_parameter.items()):
                    raise KernelMemoryError("bar_count must not receive external clock provenance")
            except KernelMemoryError:
                raise
            except Exception as exc:
                raise KernelMemoryError("bar_count clock_parameter cannot be materialized") from exc
        return {}
    if not isinstance(clock_parameter, Mapping):
        raise KernelMemoryError("non-bar clocks require a structured clock_parameter")
    try:
        keys = set(clock_parameter.keys())
        if keys != {"unit", "source_receipt_sha256"}:
            raise KernelMemoryError("non-bar clock provenance keys must be exact")
        unit = clock_parameter["unit"]
        receipt = clock_parameter["source_receipt_sha256"]
        if not isinstance(unit, str) or not unit.strip() or not isinstance(receipt, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt):
            raise KernelMemoryError("non-bar clock provenance requires unit and lowercase source receipt SHA-256")
        strict_json_dumps({"unit": unit, "source_receipt_sha256": receipt})
        labels = _strict_index_labels(close.index)
    except KernelMemoryError:
        raise
    except Exception as exc:
        raise KernelMemoryError("clock provenance must be strict JSON") from exc
    if not isinstance(clock_increments, pd.Series) or not close.index.equals(clock_increments.index):
        raise KernelMemoryError("non-bar clocks require index-aligned actual clock increments")
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
    rsi_function, macd_function, hist_function, stoch_function = _bound_owner_callables()
    rsi = _owner_series(_call_owner(rsi_function, close, "rsi"), close, "rsi")
    macd, signal = _owner_pair(_call_owner(macd_function, close, "rsi_macd"), close, "rsi_macd")
    hist = _owner_series(_call_owner(hist_function, close, "rsi_macd_hist"), close, "rsi_macd_hist")
    stoch_k, stoch_d = _owner_pair(_call_owner(stoch_function, close, "stoch_rsi_kd"), close, "stoch_rsi_kd")
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
