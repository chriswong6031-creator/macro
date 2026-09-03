"""Owner-probe indicator parity and history-truncation diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from numbers import Integral, Real
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.entry_radar import indicator_core
from scripts.research.temporal_scale.chart_export import LoadedChartExport
from scripts.research.temporal_scale.contracts import ArtifactTest, strict_json_dumps


class ParityError(ValueError):
    """Raised when parity evidence cannot be checked without inference."""


PARITY_FIELDS = (
    ("TG_rsi", "rsi"),
    ("TG_rsi_macd", "rsi_macd"),
    ("TG_rsi_macd_signal", "rsi_macd_signal"),
    ("TG_rsi_macd_hist", "rsi_macd_hist"),
    ("TG_stoch_k", "stoch_k"),
    ("TG_stoch_d", "stoch_d"),
)
_PARITY_EXPORT_FIELDS = tuple(exported for exported, _ in PARITY_FIELDS)
_PARITY_OWNER_FIELDS = tuple(owner for _, owner in PARITY_FIELDS)
_FROZEN_TOLERANCE = 1e-10
_TRUNCATION_DROPS = (1, 5, 13, 31, 63)
_COMPARISON_TAIL = 256
_CONVERGENCE_BARS = 871
_HISTORY_FLOOR = 1190
_MAX_BOUNDED_OUTPUT_DELTA = 400.0
_EVENT_KEYS = (
    "bullish_cross_ms",
    "bearish_cross_ms",
    "histogram_up_turn_ms",
    "histogram_down_turn_ms",
)


def _exact_tolerance(value: object) -> float:
    if type(value) is not float or value != _FROZEN_TOLERANCE:
        raise ParityError("tolerance must be the frozen built-in float 1e-10")
    return value


def _finite_real(value: object, *, name: str, allow_missing: bool) -> float | None:
    if value is None or value is pd.NA:
        if allow_missing:
            return None
        raise ParityError(f"{name} must be finite")
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ParityError(f"{name} must be a real scalar")
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ParityError(f"{name} must be a finite real scalar") from exc
    if math.isnan(normalized):
        if allow_missing:
            return None
        raise ParityError(f"{name} must be finite")
    if not math.isfinite(normalized):
        raise ParityError(f"{name} must be finite")
    return normalized


def _time_index(index: object, *, name: str) -> pd.Index:
    if not isinstance(index, pd.Index) or len(index) == 0:
        raise ParityError(f"{name} must have a nonempty integer time index")
    labels: list[int] = []
    for label in index:
        if isinstance(label, bool) or not isinstance(label, Integral):
            raise ParityError(f"{name} index must contain only integer timestamps")
        normalized = int(label)
        if not 0 <= normalized <= 2**63 - 1:
            raise ParityError(f"{name} index timestamps must fit nonnegative signed int64")
        labels.append(normalized)
    if len(set(labels)) != len(labels):
        raise ParityError(f"{name} index timestamps must be unique")
    if any(right <= left for left, right in zip(labels, labels[1:])):
        raise ParityError(f"{name} index timestamps must be strictly increasing")
    return pd.Index(labels, name="TG_time_open_ms", dtype="int64")


def _close_series(close: object) -> pd.Series:
    if type(close) is not pd.Series or len(close) == 0:
        raise ParityError("close must be an exact nonempty pandas Series")
    index = _time_index(close.index, name="close")
    values = [_finite_real(value, name="close", allow_missing=False) for value in close.tolist()]
    return pd.Series(values, index=index, dtype=float, name="TG_close")


def _nullable_series(value: object, index: pd.Index, *, name: str) -> pd.Series:
    if type(value) is not pd.Series or len(value) != len(index):
        raise ParityError(f"owner {name} must return an exact length pandas Series")
    if not value.index.equals(index):
        raise ParityError(f"owner {name} must return an index-aligned pandas Series")
    cells = [_finite_real(cell, name=f"owner {name}", allow_missing=True) for cell in value.tolist()]
    return pd.Series([np.nan if cell is None else cell for cell in cells], index=index, dtype=float)


def _owner_pair(value: object, index: pd.Index, *, name: str) -> tuple[pd.Series, pd.Series]:
    if type(value) is not tuple or len(value) != 2:
        raise ParityError(f"owner {name} must return exactly two Series")
    return (
        _nullable_series(value[0], index, name=f"{name}[0]"),
        _nullable_series(value[1], index, name=f"{name}[1]"),
    )


def _owner_call(function: object, close: pd.Series, *, name: str) -> object:
    if not callable(function):
        raise ParityError(f"owner {name} must be callable")
    try:
        return function(close)
    except ParityError:
        raise
    except Exception as exc:
        raise ParityError(f"owner {name} failed") from exc


def _maximum_absolute_error(left: np.ndarray, right: np.ndarray) -> float | None:
    maximum = 0.0
    for left_cell, right_cell in zip(left, right, strict=True):
        difference = abs(float(left_cell) - float(right_cell))
        if not math.isfinite(difference):
            return None
        maximum = max(maximum, difference)
    return maximum


def canonical_indicator_frame(close: pd.Series) -> pd.DataFrame:
    """Recompute the exact owner indicator family on a timestamp-indexed close."""
    normalized = _close_series(close)
    index = normalized.index
    rsi = _nullable_series(
        _owner_call(indicator_core.rsi, normalized, name="rsi"), index, name="rsi"
    )
    macd, signal = _owner_pair(
        _owner_call(indicator_core.rsi_macd, normalized, name="rsi_macd"),
        index,
        name="rsi_macd",
    )
    stoch_k, stoch_d = _owner_pair(
        _owner_call(indicator_core.stoch_rsi_kd, normalized, name="stoch_rsi_kd"),
        index,
        name="stoch_rsi_kd",
    )
    return pd.DataFrame(
        {
            "rsi": rsi,
            "rsi_macd": macd,
            "rsi_macd_signal": signal,
            "rsi_macd_hist": macd - signal,
            "stoch_k": stoch_k,
            "stoch_d": stoch_d,
        },
        index=index,
    )


@dataclass(frozen=True, slots=True)
class ParityReceipt:
    status: Literal["PASS", "FAIL"]
    tolerance: float
    first_comparable_bar_ms: int | None
    compared_rows: int
    max_abs_error: Mapping[str, float | None]
    failures: tuple[str, ...]

    def __post_init__(self) -> None:
        _exact_tolerance(self.tolerance)
        if self.status not in {"PASS", "FAIL"}:
            raise ParityError("parity status must be PASS or FAIL")
        if self.first_comparable_bar_ms is not None and (
            type(self.first_comparable_bar_ms) is not int or self.first_comparable_bar_ms < 0
        ):
            raise ParityError("first comparable timestamp must be a nonnegative integer or null")
        if type(self.compared_rows) is not int or self.compared_rows < 0:
            raise ParityError("compared_rows must be a nonnegative integer")
        if not isinstance(self.max_abs_error, Mapping):
            raise ParityError("max_abs_error must be a mapping")
        try:
            errors = dict(self.max_abs_error)
        except Exception as exc:
            raise ParityError("max_abs_error cannot be materialized") from exc
        if tuple(errors) != _PARITY_EXPORT_FIELDS:
            raise ParityError("max_abs_error keys and order must equal PARITY_FIELDS")
        normalized_errors: dict[str, float | None] = {}
        for field, value in errors.items():
            normalized = _finite_real(value, name=f"max_abs_error[{field}]", allow_missing=True)
            if normalized is not None and normalized < 0:
                raise ParityError("maximum absolute errors must be nonnegative")
            normalized_errors[field] = normalized
        if isinstance(self.failures, str) or type(self.failures) not in {tuple, list}:
            raise ParityError("failures must be a non-string sequence")
        failures = tuple(self.failures)
        if not all(type(item) is str and item for item in failures):
            raise ParityError("failures must contain deterministic nonempty tokens")
        if self.status == "PASS" and failures:
            raise ParityError("PASS parity cannot contain failures")
        if self.status == "FAIL" and not failures:
            raise ParityError("FAIL parity requires a failure")
        if self.status == "PASS" and (self.compared_rows == 0 or self.first_comparable_bar_ms is None):
            raise ParityError("PASS parity requires comparable rows")
        object.__setattr__(self, "max_abs_error", MappingProxyType(normalized_errors))
        object.__setattr__(self, "failures", failures)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "tolerance": self.tolerance,
            "first_comparable_bar_ms": self.first_comparable_bar_ms,
            "compared_rows": self.compared_rows,
            "max_abs_error": dict(self.max_abs_error),
            "failures": list(self.failures),
        }


def _export_frame(loaded: object) -> tuple[pd.DataFrame, pd.Index]:
    if type(loaded) is not LoadedChartExport:
        raise ParityError("loaded must be an exact attested LoadedChartExport")
    frame = loaded.frame
    required = ("TG_time_open_ms", "TG_close", *_PARITY_EXPORT_FIELDS)
    if any(field not in frame.columns for field in required):
        raise ParityError("loaded export lacks parity fields")
    raw_times = frame["TG_time_open_ms"]
    if type(raw_times) is not pd.Series:
        raise ParityError("TG_time_open_ms must be a Series")
    index = _time_index(pd.Index(raw_times.tolist()), name="TG_time_open_ms")
    return frame, index


def compare_indicator_parity(
    loaded: LoadedChartExport, *, tolerance: float = _FROZEN_TOLERANCE
) -> ParityReceipt:
    """Compare attested observed export fields with a fresh owner-probe recomputation."""
    tolerance = _exact_tolerance(tolerance)
    frame, index = _export_frame(loaded)
    close_values = [_finite_real(value, name="TG_close", allow_missing=False) for value in frame["TG_close"].tolist()]
    close = pd.Series(close_values, index=index, dtype=float, name="TG_close")
    owner = canonical_indicator_frame(close)
    max_errors: dict[str, float | None] = {}
    pair_masks: list[np.ndarray] = []
    first_times: list[int] = []
    exceeded: list[str] = []
    no_comparable = False
    for exported_field, owner_field in PARITY_FIELDS:
        observed_values = [
            _finite_real(value, name=exported_field, allow_missing=True)
            for value in frame[exported_field].tolist()
        ]
        observed = np.asarray([np.nan if value is None else value for value in observed_values], dtype=float)
        expected = owner[owner_field].to_numpy(dtype=float)
        mask = np.isfinite(observed) & np.isfinite(expected)
        pair_masks.append(mask)
        positions = np.flatnonzero(mask)
        if len(positions) == 0:
            no_comparable = True
            max_errors[exported_field] = None
            continue
        first_times.append(int(index[int(positions[0])]))
        error = _maximum_absolute_error(observed[mask], expected[mask])
        max_errors[exported_field] = error
        if error is None or error > tolerance:
            exceeded.append(f"PARITY_TOLERANCE_EXCEEDED:{exported_field}")
    common = np.logical_and.reduce(pair_masks) if pair_masks else np.zeros(len(index), dtype=bool)
    compared_rows = int(np.count_nonzero(common))
    if compared_rows == 0:
        no_comparable = True
    failures = (("PARITY_NO_COMPARABLE_ROWS",) if no_comparable else ()) + tuple(exceeded)
    return ParityReceipt(
        status="FAIL" if failures else "PASS",
        tolerance=tolerance,
        first_comparable_bar_ms=max(first_times) if first_times else None,
        compared_rows=compared_rows,
        max_abs_error=max_errors,
        failures=failures,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(strict_json_dumps(value).encode("utf-8")).hexdigest()


def _input_hash(close: pd.Series) -> str:
    payload = {
        "TG_time_open_ms": [int(value) for value in close.index],
        "TG_close": [float(value) for value in close.to_numpy(dtype=float)],
    }
    return _sha256_json(payload)


def _variant_input_hash(source_input_hash: str, drop: int) -> str:
    return _sha256_json(
        {
            "comparison_tail": _COMPARISON_TAIL,
            "drop_prefix": drop,
            "max_bounded_output_delta": _MAX_BOUNDED_OUTPUT_DELTA,
            "seed_convergence_bars": _CONVERGENCE_BARS,
            "source_input_hash": source_input_hash,
            "tolerance": _FROZEN_TOLERANCE,
        }
    )


def _test_id(input_hash: str, drop: int) -> str:
    return _sha256_json(
        {
            "axis": "TRUNCATION",
            "comparison_tail": _COMPARISON_TAIL,
            "drop_prefix": drop,
            "input_hash": input_hash,
            "seed_convergence_bars": _CONVERGENCE_BARS,
            "tolerance": _FROZEN_TOLERANCE,
        }
    )


def _truncation_metrics(
    *,
    available_rows: int,
    drop: int,
    compared_rows: int,
    max_errors: Mapping[str, float | None],
    baseline_events: Mapping[str, list[int]],
    truncated_events: Mapping[str, list[int]],
    event_agreement: bool | None,
) -> dict[str, Any]:
    return {
        "available_rows": available_rows,
        "baseline_event_timestamps": dict(baseline_events),
        "comparison_tail": _COMPARISON_TAIL,
        "compared_rows": compared_rows,
        "drop_prefix": drop,
        "event_timestamp_agreement": event_agreement,
        "history_floor": _HISTORY_FLOOR,
        "max_bounded_output_delta": _MAX_BOUNDED_OUTPUT_DELTA,
        "max_abs_error": dict(max_errors),
        "required_rows": drop + _CONVERGENCE_BARS + _COMPARISON_TAIL,
        "seed_convergence_bars": _CONVERGENCE_BARS,
        "tolerance": _FROZEN_TOLERANCE,
        "truncated_event_timestamps": dict(truncated_events),
    }


def _empty_events() -> dict[str, list[int]]:
    return {key: [] for key in _EVENT_KEYS}


def _event_timestamps(frame: pd.DataFrame, *, tail_start_ms: int) -> dict[str, list[int]]:
    """Extract exact owner cross and histogram-direction turn timestamps."""
    required = {"rsi_macd", "rsi_macd_signal", "rsi_macd_hist"}
    if not required.issubset(frame.columns):
        raise ParityError("owner frame lacks event fields")
    index = _time_index(frame.index, name="owner event frame")
    macd = frame["rsi_macd"].to_numpy(dtype=float)
    signal = frame["rsi_macd_signal"].to_numpy(dtype=float)
    histogram = frame["rsi_macd_hist"].to_numpy(dtype=float)
    result = _empty_events()
    for position in range(1, len(frame)):
        timestamp = int(index[position])
        if timestamp < tail_start_ms:
            continue
        if all(math.isfinite(float(value)) for value in (macd[position - 1], signal[position - 1], macd[position], signal[position])):
            previous_difference = float(macd[position - 1]) - float(signal[position - 1])
            current_difference = float(macd[position]) - float(signal[position])
            if current_difference > 0.0 and previous_difference <= 0.0:
                result["bullish_cross_ms"].append(timestamp)
            if current_difference < 0.0 and previous_difference >= 0.0:
                result["bearish_cross_ms"].append(timestamp)
        if position < 2 or not all(
            math.isfinite(float(value))
            for value in (histogram[position - 2], histogram[position - 1], histogram[position])
        ):
            continue
        previous_slope = float(histogram[position - 1]) - float(histogram[position - 2])
        current_slope = float(histogram[position]) - float(histogram[position - 1])
        if current_slope > 0.0 and previous_slope <= 0.0:
            result["histogram_up_turn_ms"].append(timestamp)
        if current_slope < 0.0 and previous_slope >= 0.0:
            result["histogram_down_turn_ms"].append(timestamp)
    return result


def truncation_invariance(
    close: pd.Series,
    *,
    drop_prefixes: Sequence[int],
    comparison_tail: int = _COMPARISON_TAIL,
    tolerance: float = _FROZEN_TOLERANCE,
) -> tuple[ArtifactTest, ...]:
    """Recompute owner indicators after every frozen prefix drop and compare the full tail."""
    normalized = _close_series(close)
    _exact_tolerance(tolerance)
    if isinstance(drop_prefixes, (str, bytes)) or not isinstance(drop_prefixes, Sequence):
        raise ParityError("drop_prefixes must be the frozen non-string sequence")
    try:
        drops = tuple(drop_prefixes)
    except Exception as exc:
        raise ParityError("drop_prefixes cannot be materialized") from exc
    if len(drops) != len(_TRUNCATION_DROPS) or any(type(drop) is not int for drop in drops):
        raise ParityError("drop_prefixes must equal (1, 5, 13, 31, 63)")
    if drops != _TRUNCATION_DROPS:
        raise ParityError("drop_prefixes must equal (1, 5, 13, 31, 63)")
    if type(comparison_tail) is not int or comparison_tail != _COMPARISON_TAIL:
        raise ParityError("comparison_tail must equal the frozen value 256")
    source_input_hash = _input_hash(normalized)
    empty_errors = {field: None for field in _PARITY_OWNER_FIELDS}
    empty_events = _empty_events()
    baseline = canonical_indicator_frame(normalized) if len(normalized) >= min(drops) + _CONVERGENCE_BARS + _COMPARISON_TAIL else None
    tail_index = normalized.index[-_COMPARISON_TAIL:]
    records: list[ArtifactTest] = []
    for drop in drops:
        input_hash = _variant_input_hash(source_input_hash, drop)
        required_rows = drop + _CONVERGENCE_BARS + _COMPARISON_TAIL
        if len(normalized) < required_rows or baseline is None:
            records.append(
                ArtifactTest(
                    test_id=_test_id(input_hash, drop),
                    axis="TRUNCATION",
                    variant_id=f"drop_prefix_{drop}",
                    input_hash=input_hash,
                    status="UNAVAILABLE",
                    metrics=_truncation_metrics(
                        available_rows=len(normalized),
                        drop=drop,
                        compared_rows=0,
                        max_errors=empty_errors,
                        baseline_events=empty_events,
                        truncated_events=empty_events,
                        event_agreement=None,
                    ),
                    findings=("TRUNCATION_HISTORY_INSUFFICIENT",),
                )
            )
            continue
        recomputed = canonical_indicator_frame(normalized.iloc[drop:])
        aligned = baseline.index[-_COMPARISON_TAIL:].equals(tail_index) and tail_index.isin(recomputed.index).all()
        max_errors: dict[str, float | None] = {}
        failed = not aligned
        complete_tail = bool(aligned)
        baseline_events = _empty_events()
        truncated_events = _empty_events()
        event_agreement: bool | None = None
        if aligned:
            baseline_tail = baseline.loc[tail_index]
            recomputed_tail = recomputed.loc[tail_index]
            for field in _PARITY_OWNER_FIELDS:
                expected = baseline_tail[field].to_numpy(dtype=float)
                actual = recomputed_tail[field].to_numpy(dtype=float)
                comparable = np.isfinite(expected) & np.isfinite(actual)
                if len(expected) != _COMPARISON_TAIL or not bool(np.all(comparable)):
                    max_errors[field] = None
                    complete_tail = False
                    continue
                error = _maximum_absolute_error(expected, actual)
                if error is None:
                    max_errors[field] = None
                    complete_tail = False
                    continue
                max_errors[field] = error
                if error > tolerance:
                    failed = True
            if complete_tail:
                tail_start_ms = int(tail_index[0])
                baseline_events = _event_timestamps(baseline, tail_start_ms=tail_start_ms)
                truncated_events = _event_timestamps(recomputed, tail_start_ms=tail_start_ms)
                event_agreement = baseline_events == truncated_events
                if not event_agreement:
                    failed = True
        else:
            max_errors = dict(empty_errors)
        if not complete_tail:
            status = "UNAVAILABLE"
            findings = ("TRUNCATION_COMPARABLE_EVIDENCE_UNAVAILABLE",)
        elif failed:
            status = "FAIL"
            findings = (
                ("TRUNCATION_EVENT_TIMESTAMPS_DIVERGED",)
                if event_agreement is False and all(value is not None and value <= tolerance for value in max_errors.values())
                else ("TRUNCATION_INVARIANCE_FAILED",)
            )
        else:
            status = "PASS"
            findings = ("TRUNCATION_INVARIANCE_PASSED",)
        records.append(
            ArtifactTest(
                test_id=_test_id(input_hash, drop),
                axis="TRUNCATION",
                variant_id=f"drop_prefix_{drop}",
                input_hash=input_hash,
                status=status,
                metrics=_truncation_metrics(
                    available_rows=len(normalized),
                    drop=drop,
                    compared_rows=_COMPARISON_TAIL if complete_tail else 0,
                    max_errors=max_errors,
                    baseline_events=baseline_events,
                    truncated_events=truncated_events,
                    event_agreement=event_agreement,
                ),
                findings=findings,
            )
        )
    return tuple(records)
