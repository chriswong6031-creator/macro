"""Frozen, outcome-blind G/A/K/D artifact diagnostics for temporal scale W1A.

The module consumes only an attested chart export and optional locally supplied
lower-grain bars. It deliberately has no market-data, outcome, ranking, or
production-control surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import math
from numbers import Integral, Real
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

from engine.trial_ledger import DEFAULT_PATH, TrialLedger
from scripts.research.temporal_scale.chart_export import LoadedChartExport
from scripts.research.temporal_scale.contracts import (
    ARTIFACT_ATTACK_SCHEMA,
    ArtifactAttackResult,
    ArtifactTest,
    ChartRecipe,
    strict_json_dumps,
)
from scripts.research.temporal_scale.parity import (
    ParityError,
    canonical_indicator_frame,
    compare_indicator_parity,
    truncation_invariance,
)
from scripts.research.temporal_scale.kernel_memory import canonical_kernel_signature
from scripts.research.temporal_scale.session_bars import (
    BarGridSpec,
    SessionBarsError,
    SessionInterval,
    build_session_bars,
)


class ArtifactAttackError(ValueError):
    """The frozen W1A experiment cannot be executed without inference."""


_OPERATION_KEY = "temporal-grain-gakd-artifact-attack-r1-20260903-sol-001"
_TRIAL_FAMILY = "temporal_grain_gakd_r1"
_DROP_PREFIXES = (1, 5, 13, 31, 63)
_REQUIRED_AXES = ("G", "A", "K", "PARITY", "TRUNCATION")
_ALL_AXES = ("G", "A", "K", "D", "PARITY", "TRUNCATION")
_STATUSES = frozenset({"PASS", "FAIL", "UNAVAILABLE"})
_AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_trade": False,
    "may_modify_prophet": False,
}
_IMPLEMENTATION_CONTROLS = (
    "owner_rsi_macd_stochrsi",
    "standard_price_macd_12_26_9",
)
_DATA_PLANE_CONTROLS = ("exact_recipe_plane",)


def _hash(value: object) -> str:
    return hashlib.sha256(strict_json_dumps(value).encode("utf-8")).hexdigest()


def _sorted_unique_ints(values: object, *, name: str) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ArtifactAttackError(f"{name} must be a sequence")
    normalized = tuple(values)
    if not normalized or any(type(value) is not int or value < 1 for value in normalized):
        raise ArtifactAttackError(f"{name} must contain positive integers")
    return tuple(sorted(set(normalized)))


def _sorted_unique_fractions(values: object) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ArtifactAttackError("anchor phases must be a sequence")
    normalized: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ArtifactAttackError("anchor phases must be finite fractions")
        phase = float(value)
        if not math.isfinite(phase) or not 0.0 <= phase < 1.0:
            raise ArtifactAttackError("anchor phases must be within [0, 1)")
        normalized.append(phase)
    if not normalized:
        raise ArtifactAttackError("anchor phases cannot be empty")
    return tuple(sorted(set(normalized)))


def _sorted_unique_strings(values: object, *, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ArtifactAttackError(f"{name} must be a sequence")
    normalized = tuple(values)
    if not normalized or any(type(value) is not str or not value.strip() for value in normalized):
        raise ArtifactAttackError(f"{name} must contain nonempty strings")
    return tuple(sorted(set(normalized)))


@dataclass(frozen=True, slots=True)
class ArtifactGrid:
    human_chart_grains_minutes: tuple[int, ...]
    memory_matched_grains_minutes: tuple[int, ...]
    anchor_phase_fractions: tuple[float, ...]
    session_variants: tuple[str, ...]
    implementation_controls: tuple[str, ...]
    data_plane_controls: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "human_chart_grains_minutes", _sorted_unique_ints(self.human_chart_grains_minutes, name="human grains"))
        object.__setattr__(self, "memory_matched_grains_minutes", _sorted_unique_ints(self.memory_matched_grains_minutes, name="memory grains"))
        object.__setattr__(self, "anchor_phase_fractions", _sorted_unique_fractions(self.anchor_phase_fractions))
        object.__setattr__(self, "session_variants", _sorted_unique_strings(self.session_variants, name="session variants"))
        object.__setattr__(self, "implementation_controls", _sorted_unique_strings(self.implementation_controls, name="implementation controls"))
        object.__setattr__(self, "data_plane_controls", _sorted_unique_strings(self.data_plane_controls, name="data-plane controls"))

    def to_dict(self) -> dict[str, object]:
        return {
            "human_chart_grains_minutes": list(self.human_chart_grains_minutes),
            "memory_matched_grains_minutes": list(self.memory_matched_grains_minutes),
            "anchor_phase_fractions": list(self.anchor_phase_fractions),
            "session_variants": list(self.session_variants),
            "implementation_controls": list(self.implementation_controls),
            "data_plane_controls": list(self.data_plane_controls),
        }

    def sha256(self) -> str:
        return _hash(self.to_dict())


def _chart_mapping(recipe: Mapping[str, object] | ChartRecipe) -> Mapping[str, object]:
    if isinstance(recipe, ChartRecipe):
        return recipe.chart
    if not isinstance(recipe, Mapping):
        raise ArtifactAttackError("recipe must be a ChartRecipe or mapping")
    chart = recipe.get("chart")
    if not isinstance(chart, Mapping):
        raise ArtifactAttackError("complete recipe chart is required")
    return chart


def default_artifact_grid(recipe: Mapping[str, object] | ChartRecipe) -> ArtifactGrid:
    """Freeze the preregistered ratios without rounding non-integral grains."""
    chart = _chart_mapping(recipe)
    nominal_value = chart.get("timeframe_period")
    if not isinstance(nominal_value, str) or not re.fullmatch(r"[1-9][0-9]*", nominal_value):
        raise ArtifactAttackError("complete integer-minute chart timeframe is required")
    nominal = int(nominal_value)
    alternatives = chart.get("allowed_session_variants")
    if isinstance(alternatives, (str, bytes)) or not isinstance(alternatives, Sequence):
        raise ArtifactAttackError("allowed session variants are required")
    grains: list[int] = []
    for ratio in (Fraction(1, 2), Fraction(2, 3), Fraction(1), Fraction(4, 3), Fraction(2)):
        candidate = nominal * ratio
        if candidate.denominator == 1 and candidate.numerator >= 1:
            grains.append(candidate.numerator)
    named_session = chart.get("named_session")
    if type(named_session) is not str or not named_session:
        raise ArtifactAttackError("active named session is required")
    return ArtifactGrid(
        tuple(grains), tuple(grains), (0.0, 0.25, 0.5, 0.75), (*tuple(alternatives), named_session),
        _IMPLEMENTATION_CONTROLS, _DATA_PLANE_CONTROLS,
    )


def _registration_configs(grid: ArtifactGrid) -> list[dict[str, object]]:
    digest = grid.sha256()
    configs: list[dict[str, object]] = []
    variants: tuple[tuple[str, Sequence[object]], ...] = (
        ("G", tuple(f"grain_minutes_{grain}" for grain in grid.human_chart_grains_minutes)),
        ("A", tuple(
            f"session_{session}_phase_{phase:g}"
            for session in grid.session_variants for phase in grid.anchor_phase_fractions
        ) + ("phase_uniqueness",)),
        ("K", (*tuple(f"memory_target_minutes_{grain}" for grain in grid.memory_matched_grains_minutes), *grid.implementation_controls)),
        ("D", ("chart_price_construction", *grid.data_plane_controls)),
        ("PARITY", ("observed_vs_owner_1e-10",)),
        ("TRUNCATION", tuple(f"drop_prefix_{drop}" for drop in _DROP_PREFIXES)),
    )
    for axis, values in variants:
        for value in values:
            configs.append({"axis": axis, "grid_hash": digest, "variant": value})
    return configs


def register_artifact_grid(
    grid: ArtifactGrid,
    *,
    ledger_path: Path,
    info_cutoff: str,
    family: str = _TRIAL_FAMILY,
) -> int:
    """Register the complete grid before any diagnostic executes."""
    if not isinstance(grid, ArtifactGrid):
        raise ArtifactAttackError("grid must be an ArtifactGrid")
    try:
        path = Path(ledger_path)
        if path.resolve() == DEFAULT_PATH.resolve():
            raise ArtifactAttackError("production TrialLedger path is prohibited")
    except ArtifactAttackError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ArtifactAttackError("ledger path is invalid") from exc
    if type(info_cutoff) is not str or not info_cutoff.strip():
        raise ArtifactAttackError("deterministic evidence info_cutoff is required")
    if family != _TRIAL_FAMILY:
        raise ArtifactAttackError("trial family must equal the frozen W1A family")
    try:
        return TrialLedger(path=path, family=family).log_grid(
            _registration_configs(grid), info_cutoff=info_cutoff, source="frozen_gakd_grid",
        )
    except Exception as exc:
        raise ArtifactAttackError("trial-grid registration failed") from exc


def _axis_statuses(tests: Mapping[str, str] | Sequence[ArtifactTest]) -> dict[str, tuple[str, ...]]:
    if isinstance(tests, Mapping):
        materialized: dict[str, tuple[str, ...]] = {}
        for axis, status in tests.items():
            if axis not in (*_ALL_AXES, "DENSITY") or status not in _STATUSES:
                raise ArtifactAttackError("artifact test status mapping is invalid")
            materialized[str(axis)] = (str(status),)
        return materialized
    if isinstance(tests, (str, bytes)) or not isinstance(tests, Sequence):
        raise ArtifactAttackError("tests must be ArtifactTest records")
    materialized = {}
    for test in tests:
        if not isinstance(test, ArtifactTest):
            raise ArtifactAttackError("tests must be ArtifactTest records")
        materialized.setdefault(test.axis, ())
        materialized[test.axis] += (test.status,)
    return materialized


def classify_mechanical_status(
    recipe_complete: bool,
    parity_status: str,
    tests: Mapping[str, str] | Sequence[ArtifactTest],
) -> str:
    """Apply the carrier's fail-closed W1A status priority exactly."""
    if type(recipe_complete) is not bool or parity_status not in {"PASS", "FAIL", "UNRESOLVED_DATA"}:
        raise ArtifactAttackError("classification inputs are invalid")
    statuses = _axis_statuses(tests)
    records = tuple(tests) if not isinstance(tests, Mapping) else ()
    unresolved = (
        not recipe_complete or parity_status == "UNRESOLVED_DATA"
        or any("UNAVAILABLE" in statuses.get(axis, ()) for axis in _REQUIRED_AXES)
        or any(axis not in statuses for axis in _REQUIRED_AXES)
    )
    if unresolved:
        return "UNRESOLVED_DATA"
    artifact = (
        parity_status == "FAIL"
        or any("FAIL" in statuses.get(axis, ()) for axis in _REQUIRED_AXES)
        or any("single_arbitrary_phase_only" in test.findings for test in records)
    )
    return "ARTIFACT" if artifact else "MECHANICALLY_SURVIVES"


def classify_artifact_attack(
    recipe_complete: bool,
    parity_status: str,
    tests: Mapping[str, str] | Sequence[ArtifactTest],
) -> str:
    """Frozen public name for the amended three-status W1A classifier."""
    return classify_mechanical_status(recipe_complete, parity_status, tests)


def _artifact_test(
    axis: str,
    variant_id: str,
    input_payload: object,
    status: str,
    metrics: Mapping[str, Any],
    findings: Sequence[str],
) -> ArtifactTest:
    input_hash = _hash(input_payload)
    return ArtifactTest(
        test_id=_hash({"axis": axis, "input_hash": input_hash, "variant_id": variant_id}),
        axis=axis,  # type: ignore[arg-type]
        variant_id=variant_id,
        input_hash=input_hash,
        status=status,  # type: ignore[arg-type]
        metrics=dict(metrics),
        findings=tuple(findings),
    )


def _chart_type_tests(recipe: ChartRecipe, input_hash: str) -> tuple[ArtifactTest, ...]:
    if not isinstance(recipe, ChartRecipe) or not re.fullmatch(r"[0-9a-f]{64}", input_hash):
        raise ArtifactAttackError("chart-type evidence is invalid")
    standard = recipe.chart["chart_is_standard"] is True
    status = "PASS" if standard else "FAIL"
    finding = "standard_chart_price_construction" if standard else "nonstandard_chart_price_construction"
    axes = ("D",) if standard else ("A", "D")
    return tuple(
        _artifact_test(
            axis, "chart_price_construction",
            {"chart": dict(recipe.chart), "source": input_hash}, status,
            {"chart_is_standard": standard}, (finding,),
        )
        for axis in axes
    )


def _close(loaded: LoadedChartExport) -> pd.Series:
    frame = loaded.frame
    return pd.Series(
        frame["TG_close"].to_numpy(dtype=float),
        index=pd.Index(frame["TG_time_open_ms"].tolist(), dtype="int64", name="TG_time_open_ms"),
        dtype=float, name="TG_close",
    )


def _parity_test(parity: Mapping[str, Any], csv_hash: str) -> ArtifactTest:
    status = "PASS" if parity["status"] == "PASS" else "FAIL"
    failures = tuple(str(value) for value in parity.get("failures", ()))
    return _artifact_test(
        "PARITY", "observed_vs_owner_1e-10",
        {"csv_sha256": csv_hash, "tolerance": 1e-10}, status,
        {
            "compared_rows": parity.get("compared_rows", 0),
            "first_comparable_bar_ms": parity.get("first_comparable_bar_ms"),
            "max_abs_error": dict(parity.get("max_abs_error", {})),
            "tolerance": parity.get("tolerance", 1e-10),
        },
        failures or ("exact_owner_probe_parity",),
    )


def _unavailable(axis: str, variant_id: str, source_hash: str, token: str) -> ArtifactTest:
    return _artifact_test(
        axis, variant_id, {"axis": axis, "source": source_hash, "variant_id": variant_id},
        "UNAVAILABLE", {"available": False}, (token,),
    )


def _session_intervals(name: str) -> tuple[SessionInterval, ...] | None:
    if name in {"regular", "us_regular"}:
        return (SessionInterval("09:30", "16:00", "regular"),)
    if name == "extended":
        return (SessionInterval("04:00", "20:00", "extended"),)
    if name == "24h":
        return (SessionInterval("00:00", "00:00", "market"),)
    return None


def _bars_for(
    rows: pd.DataFrame,
    recipe: ChartRecipe,
    *,
    grain: int,
    phase_fraction: float,
    session_name: str,
) -> tuple[pd.DataFrame, tuple[object, ...]] | None:
    intervals = _session_intervals(session_name)
    if intervals is None:
        return None
    try:
        zone = ZoneInfo(str(recipe.chart["exchange_timezone"]))
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise ArtifactAttackError("recipe exchange timezone is invalid") from exc

    def minutes(ms: int) -> int:
        local = datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(zone)
        return local.hour * 60 + local.minute

    def within(value: int, interval: SessionInterval) -> bool:
        start_hour, start_minute = map(int, interval.start_local.split(":"))
        end_hour, end_minute = map(int, interval.end_local.split(":"))
        start = start_hour * 60 + start_minute
        end = end_hour * 60 + end_minute
        return True if start == end else start <= value < end if start < end else value >= start or value < end

    if not {"open_ms", "close_ms"}.issubset(rows.columns):
        raise ArtifactAttackError("lower-grain bounds are missing")
    selected: list[bool] = []
    try:
        for open_value, close_value in zip(rows["open_ms"], rows["close_ms"], strict=True):
            if isinstance(open_value, bool) or isinstance(close_value, bool) or not isinstance(open_value, Integral) or not isinstance(close_value, Integral):
                raise ArtifactAttackError("lower-grain bounds must be integer milliseconds")
            open_ms, close_ms = int(open_value), int(close_value)
            if close_ms <= open_ms:
                raise ArtifactAttackError("lower-grain bounds must be positive")
            selected.append(any(within(minutes(open_ms), interval) and within(minutes(close_ms - 1), interval) for interval in intervals))
    except ArtifactAttackError:
        raise
    except (OSError, OverflowError, TypeError, ValueError) as exc:
        raise ArtifactAttackError("lower-grain session filtering failed") from exc
    session_rows = rows.loc[selected].copy(deep=True).reset_index(drop=True)
    phase = Fraction(str(phase_fraction)) * grain
    if phase.denominator != 1:
        return None
    phase_minutes = phase.numerator
    if not 0 <= phase_minutes < grain:
        raise ArtifactAttackError("phase cannot be represented at this grain")
    spec = BarGridSpec(
        grid_id=f"{session_name}-{grain}-p{phase_minutes}",
        timezone=str(recipe.chart["exchange_timezone"]), nominal_minutes=grain,
        phase_minutes=phase_minutes, intervals=intervals, include_empty=False,
        close_delay_minutes=0,
    )
    try:
        bars, receipts = build_session_bars(session_rows, recipe_id=recipe.recipe_id, grid=spec)
    except SessionBarsError as exc:
        raise ArtifactAttackError("malformed lower-grain evidence") from exc
    return bars, tuple(receipts)


def _confirmed_lower(frame: pd.DataFrame) -> pd.DataFrame:
    required = ("open_ms", "close_ms", "open", "high", "low", "close", "volume")
    if not set(required).issubset(frame.columns):
        raise ArtifactAttackError("lower-grain evidence is missing required columns")
    normalized = frame.copy(deep=True).reset_index(drop=True)
    for name in ("open_ms", "close_ms"):
        if not normalized[name].map(
            lambda value: not isinstance(value, bool) and isinstance(value, Integral)
        ).all():
            raise ArtifactAttackError("lower-grain bounds must be integer milliseconds")
        normalized[name] = normalized[name].map(int)
    for name in ("open", "high", "low", "close", "volume"):
        def finite(value: object) -> bool:
            return (
                not isinstance(value, bool)
                and isinstance(value, Real)
                and math.isfinite(float(value))
            )

        if not normalized[name].map(finite).all():
            raise ArtifactAttackError("lower-grain OHLCV must be finite real values")
        normalized[name] = normalized[name].map(float)
    if (
        normalized["open_ms"].duplicated().any()
        or not normalized["open_ms"].is_monotonic_increasing
        or (normalized["open_ms"] >= normalized["close_ms"]).any()
        or (normalized["close_ms"].shift(1).iloc[1:] > normalized["open_ms"].iloc[1:]).any()
        or (normalized["volume"] < 0).any()
        or (normalized["high"] < normalized[["open", "close"]].max(axis=1)).any()
        or (normalized["low"] > normalized[["open", "close"]].min(axis=1)).any()
    ):
        raise ArtifactAttackError("lower-grain bounds or OHLCV are malformed")
    confirmation_names = [
        name for name in ("confirmed", "is_confirmed", "TG_is_confirmed")
        if name in normalized.columns
    ]
    if len(confirmation_names) > 1:
        raise ArtifactAttackError("lower-grain evidence has multiple confirmation columns")
    if confirmation_names:
        confirmation = normalized[confirmation_names[0]]
        if not confirmation.map(
            lambda value: type(value) is bool
            or (not isinstance(value, bool) and isinstance(value, Integral) and int(value) in {0, 1})
        ).all():
            raise ArtifactAttackError("lower-grain confirmation values are invalid")
        provisional = [position for position, value in enumerate(confirmation) if not bool(value)]
        if provisional and provisional != [len(normalized) - 1]:
            raise ArtifactAttackError("lower-grain evidence has an interior provisional row")
        if provisional:
            normalized = normalized.iloc[:-1].copy()
    return normalized


def _lower_evidence_hash(frame: pd.DataFrame, csv_hash: str) -> str:
    if not all(type(column) is str for column in frame.columns):
        raise ArtifactAttackError("lower-grain column names must be strings")
    records: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        record: dict[str, object] = {}
        for column in frame.columns:
            value = row[column]
            if value is None or value is pd.NA or (isinstance(value, Real) and not isinstance(value, bool) and pd.isna(value)):
                record[column] = None
            elif type(value) is bool:
                record[column] = value
            elif isinstance(value, Integral):
                record[column] = int(value)
            elif isinstance(value, Real):
                normalized = float(value)
                if not math.isfinite(normalized):
                    raise ArtifactAttackError("lower-grain evidence must be finite or null")
                record[column] = normalized
            elif type(value) is str:
                record[column] = value
            else:
                raise ArtifactAttackError("lower-grain evidence must be strict JSON scalars")
        records.append(record)
    return _hash({"columns": list(frame.columns), "csv_sha256": csv_hash, "records": records})


def _events(frame: pd.DataFrame) -> dict[str, list[int]]:
    result = {
        "bullish_cross_ms": [], "bearish_cross_ms": [],
        "histogram_up_turn_ms": [], "histogram_down_turn_ms": [],
    }
    if frame.empty:
        return result
    macd = frame["rsi_macd"].to_numpy(dtype=float)
    signal = frame["rsi_macd_signal"].to_numpy(dtype=float)
    histogram = frame["rsi_macd_hist"].to_numpy(dtype=float)
    labels = [int(value) for value in frame.index]
    for position in range(1, len(frame)):
        if all(math.isfinite(float(value)) for value in (macd[position - 1], signal[position - 1], macd[position], signal[position])):
            before = float(macd[position - 1]) - float(signal[position - 1])
            current = float(macd[position]) - float(signal[position])
            if current > 0.0 and before <= 0.0:
                result["bullish_cross_ms"].append(labels[position])
            if current < 0.0 and before >= 0.0:
                result["bearish_cross_ms"].append(labels[position])
        if position >= 2 and all(math.isfinite(float(value)) for value in histogram[position - 2:position + 1]):
            before_slope = float(histogram[position - 1]) - float(histogram[position - 2])
            current_slope = float(histogram[position]) - float(histogram[position - 1])
            if current_slope > 0.0 and before_slope <= 0.0:
                result["histogram_up_turn_ms"].append(labels[position])
            if current_slope < 0.0 and before_slope >= 0.0:
                result["histogram_down_turn_ms"].append(labels[position])
    return result


def _geometry(bars: pd.DataFrame, receipts: Sequence[object]) -> dict[str, Any]:
    provisional_metrics = {
        "excluded_provisional_count": int(bars.attrs.get("excluded_provisional_count", 0)),
        "excluded_provisional_open_ms": list(bars.attrs.get("excluded_provisional_open_ms", ())),
        "excluded_provisional_row_sha256": bars.attrs.get("excluded_provisional_row_sha256"),
    }
    if bars.empty:
        metrics = {
            "bar_count": 0, "finite_indicator_cells": 0, "warmup_loss": 0,
            "total_variation": None, "events": _events(pd.DataFrame()),
            "clipped_bar_prevalence": None, "empty_bar_prevalence": None,
            "missing_minutes": int(bars.attrs.get("missing_minutes", 0)),
        }
        metrics.update(provisional_metrics)
        return metrics
    close = pd.Series(
        bars["close"].to_numpy(dtype=float),
        index=pd.Index(bars["open_ms"].tolist(), dtype="int64", name="TG_time_open_ms"),
        dtype=float,
    )
    indicators = canonical_indicator_frame(close)
    finite = np.isfinite(indicators.to_numpy(dtype=float))
    first_finite = [int(np.flatnonzero(finite[:, index])[0]) for index in range(finite.shape[1]) if finite[:, index].any()]
    histogram = indicators["rsi_macd_hist"].dropna().to_numpy(dtype=float)
    events = _events(indicators)
    clipped_count = sum(bool(getattr(receipt, "clipped", False)) for receipt in receipts)
    empty_count = sum(bool(getattr(receipt, "empty_interval", False)) for receipt in receipts)
    session_count = sum(bool(getattr(receipt, "session_flags", {}).get("first_session_bar", False)) for receipt in receipts)
    metrics = {
        "bar_count": len(bars), "finite_indicator_cells": int(finite.sum()),
        "warmup_loss": max(first_finite) if first_finite else len(bars),
        "total_variation": float(np.abs(np.diff(histogram)).sum()) if len(histogram) > 1 else 0.0,
        "events": events,
        "event_density_per_session": float(sum(len(value) for value in events.values()) / max(1, session_count)),
        "evidenced_session_count": session_count,
        "clipped_bar_prevalence": clipped_count / len(receipts) if receipts else None,
        "empty_bar_prevalence": empty_count / len(receipts) if receipts else None,
        "missing_minutes": int(bars.attrs.get("missing_minutes", 0)),
    }
    metrics.update(provisional_metrics)
    return metrics


def _grain_and_anchor_tests(
    loaded: LoadedChartExport,
    lower_grain_rows: pd.DataFrame,
    grid: ArtifactGrid,
) -> tuple[tuple[ArtifactTest, ...], dict[int, tuple[pd.DataFrame, tuple[object, ...]]]]:
    recipe = loaded.recipe
    nominal = int(str(recipe.chart["timeframe_period"]))
    named = str(recipe.chart["named_session"])
    confirmed_lower = _confirmed_lower(lower_grain_rows)
    source_hash = _lower_evidence_hash(lower_grain_rows, loaded.csv_sha256)
    tests: list[ArtifactTest] = []
    grain_sequences: dict[int, tuple[pd.DataFrame, tuple[object, ...]]] = {}
    for grain in grid.human_chart_grains_minutes:
        built = _bars_for(lower_grain_rows, recipe, grain=grain, phase_fraction=0.0, session_name=named)
        variant = f"grain_minutes_{grain}"
        if built is None:
            tests.append(_unavailable("G", variant, source_hash, "G_SESSION_RECONSTRUCTION_UNAVAILABLE"))
            continue
        bars, receipts = built
        grain_sequences[grain] = (bars, receipts)
        tests.append(_artifact_test(
            "G", variant,
            {"source": source_hash, "grain": grain, "receipts": [getattr(item, "source_row_sha256", "") for item in receipts]},
            "PASS" if not bars.empty else "UNAVAILABLE", _geometry(bars, receipts),
            ("mechanical_grain_geometry_recorded",) if not bars.empty else ("G_NO_RECONSTRUCTED_BARS",),
        ))

    phase_matches: list[float] = []
    phase_comparisons = 0
    observed = loaded.frame
    observed_keys = {
        (int(row.TG_time_open_ms), int(row.TG_time_close_ms)): (
            float(row.TG_open), float(row.TG_high), float(row.TG_low), float(row.TG_close)
        )
        for row in observed.itertuples(index=False)
    }
    lower_covers_observed = (
        not confirmed_lower.empty
        and int(confirmed_lower["open_ms"].min()) <= min(key[0] for key in observed_keys)
        and int(confirmed_lower["close_ms"].max()) >= max(key[1] for key in observed_keys)
    )
    for session in grid.session_variants:
        for phase in grid.anchor_phase_fractions:
            built = _bars_for(lower_grain_rows, recipe, grain=nominal, phase_fraction=phase, session_name=session)
            variant = f"session_{session}_phase_{phase:g}"
            if built is None:
                tests.append(_unavailable("A", variant, source_hash, "A_SESSION_RECONSTRUCTION_UNAVAILABLE"))
                continue
            bars, receipts = built
            if bars.empty:
                tests.append(_unavailable("A", variant, source_hash, "A_SESSION_ROWS_UNAVAILABLE"))
                continue
            phase_comparisons += 1
            reconstructed_keys = {
                (int(row.open_ms), int(row.close_ms)): (float(row.open), float(row.high), float(row.low), float(row.close))
                for row in bars.itertuples(index=False)
            }
            common = sorted(set(observed_keys) & set(reconstructed_keys))
            same_boundaries = bool(common) and len(common) == len(observed_keys) == len(reconstructed_keys)
            exact = same_boundaries and all(
                all(abs(left - right) <= 1e-10 for left, right in zip(observed_keys[key], reconstructed_keys[key], strict=True))
                for key in common
            )
            if exact:
                phase_matches.append(phase)
            metrics = _geometry(bars, receipts)
            metrics.update({
                "exact_motivating_bar_match": exact, "matched_boundaries": len(common),
                "observed_bars": len(observed_keys), "reconstructed_bars": len(reconstructed_keys),
                "timestamp_displacement_ms": 0 if exact else None,
            })
            motivating = session == named and phase == 0.0
            diagnostic_status = "PASS"
            findings = ("exact_motivating_bar_construction",) if exact else ("anchor_session_geometry_recorded",)
            if motivating and not exact:
                diagnostic_status = "FAIL" if lower_covers_observed else "UNAVAILABLE"
                findings = (
                    "motivating_bar_construction_mismatch"
                    if lower_covers_observed
                    else "MOTIVATING_BAR_COVERAGE_INSUFFICIENT",
                )
            tests.append(_artifact_test(
                "A", variant,
                {"source": source_hash, "variant": variant, "receipts": [getattr(item, "source_row_sha256", "") for item in receipts]},
                diagnostic_status, metrics, findings,
            ))
    if len(set(phase_matches)) == 1 and phase_matches[0] != 0.0:
        tests.append(_artifact_test(
            "A", "phase_uniqueness", {"source": source_hash, "matches": phase_matches},
            "PASS", {"matching_phases": sorted(set(phase_matches))}, ("single_arbitrary_phase_only",),
        ))
    elif phase_comparisons:
        tests.append(_artifact_test(
            "A", "phase_uniqueness", {"source": source_hash, "matches": phase_matches},
            "PASS", {"matching_phases": sorted(set(phase_matches))}, ("single_arbitrary_phase_not_detected",),
        ))
    else:
        tests.append(_unavailable("A", "phase_uniqueness", source_hash, "A_PHASE_COMPARISON_UNAVAILABLE"))
    return tuple(tests), grain_sequences


def _kernel_tests(
    loaded: LoadedChartExport,
    grid: ArtifactGrid,
    sequences: Mapping[int, tuple[pd.DataFrame, tuple[object, ...]]],
) -> tuple[ArtifactTest, ...]:
    def unavailable_all(token: str) -> tuple[ArtifactTest, ...]:
        return tuple(
            _unavailable(
                "K", f"memory_target_minutes_{target}", loaded.csv_sha256, token,
            )
            for target in grid.memory_matched_grains_minutes
        )

    def elapsed_vector(bars: pd.DataFrame) -> pd.Series:
        close_values = bars["close_ms"].to_numpy(dtype=np.int64)
        first = (int(bars["close_ms"].iloc[0]) - int(bars["open_ms"].iloc[0])) / 60_000.0
        values = np.concatenate(([first], np.diff(close_values) / 60_000.0))
        return pd.Series(
            values,
            index=pd.Index(bars["open_ms"].tolist(), dtype="int64", name="TG_time_open_ms"),
            dtype=float,
        )

    nominal = int(str(loaded.recipe.chart["timeframe_period"]))
    usable = {grain: value for grain, value in sequences.items() if len(value[0]) >= 2}
    if nominal not in usable or len(usable) < 2:
        return unavailable_all("K_ALTERNATE_ACTUAL_CLOCK_UNAVAILABLE")
    base_bars = usable[nominal][0]
    base_elapsed = elapsed_vector(base_bars)
    base_median = float(np.median(base_elapsed.to_numpy(dtype=float)))
    if not math.isfinite(base_median) or base_median <= 0:
        return unavailable_all("K_ACTUAL_CLOCK_INVALID")
    finite_windows = {
        "rsi_length": 14,
        "macd_fast_length": 14,
        "macd_slow_length": 60,
        "macd_signal_length": 5,
        "stoch_length": 14,
        "stoch_smooth_k": 3,
        "stoch_smooth_d": 3,
    }

    def nearest_count(target_span: float, median: float) -> int:
        raw = target_span / median
        lower = max(1, math.floor(raw))
        upper = max(1, math.ceil(raw))
        return min((lower, upper), key=lambda value: (abs(value * median - target_span), value))

    tests: list[ArtifactTest] = []
    for target in grid.memory_matched_grains_minutes:
        choices: list[tuple[float, int, float]] = []
        for grain, (bars, _) in usable.items():
            elapsed = elapsed_vector(bars)
            median = float(np.median(elapsed.to_numpy(dtype=float)))
            choices.append((abs(median - target), grain, median))
        _, chosen_grain, chosen_median = min(choices, key=lambda item: (item[0], item[1]))
        bars, receipts = usable[chosen_grain]
        elapsed = elapsed_vector(bars)
        selected_close = pd.Series(
            bars["close"].to_numpy(dtype=float), index=elapsed.index, dtype=float,
        )
        clock_receipt_hash = _hash([
            getattr(receipt, "source_row_sha256", "") for receipt in receipts
        ])
        signature = canonical_kernel_signature(
            selected_close,
            clock_basis="elapsed_time",
            clock_parameter={"unit": "minutes", "source_receipt_sha256": clock_receipt_hash},
            clock_increments=elapsed,
        )
        half_life_mappings = {
            name: {
                "mapped_bars": nearest_count(float(bars_value) * base_median, chosen_median),
                "target_elapsed_span_minutes": float(bars_value) * base_median,
            }
            for name, bars_value in signature.bar_memory.items()
        }
        finite_window_mappings = {
            name: {
                "mapped_bars": nearest_count(float(bars_value) * base_median, chosen_median),
                "target_elapsed_span_minutes": float(bars_value) * base_median,
            }
            for name, bars_value in finite_windows.items()
        }
        metrics = _geometry(bars, receipts)
        metrics.update({
            "actual_clock": "close_to_close_elapsed_minutes", "actual_clock_count": len(elapsed),
            "actual_clock_median_minutes": chosen_median, "bar_count": len(bars),
            "declared_open_session_minutes": float(sum(int(getattr(item, "effective_minutes", 0)) for item in receipts)),
            "memory_target_minutes": target, "nearest_median_grain_minutes": chosen_grain,
            "reference_actual_clock_median_minutes": base_median,
            "clock_parameter": dict(signature.clock_parameter),
            "empirical_half_life_mappings": half_life_mappings,
            "finite_window_mappings": finite_window_mappings,
            "trade_clock_available": all(getattr(item, "trade_count", None) is not None for item in receipts),
            "traded_clock_available": all(getattr(item, "traded_minutes", None) is not None for item in receipts),
            "variance_clock_available": all(getattr(item, "realized_variance", None) is not None for item in receipts),
            "volume_clock_available": all(getattr(item, "volume", None) is not None for item in receipts),
        })
        tests.append(_artifact_test(
            "K", f"memory_target_minutes_{target}",
            {"csv": loaded.csv_sha256, "target": target, "grain": chosen_grain, "elapsed": elapsed.tolist(), "clock_receipt_hash": clock_receipt_hash},
            "PASS", metrics, ("actual_elapsed_memory_mapping_recorded",),
        ))
    return tuple(tests)


def _implementation_and_data_tests(
    loaded: LoadedChartExport,
    grid: ArtifactGrid,
    parity: Mapping[str, Any],
) -> tuple[ArtifactTest, ...]:
    recipe = loaded.recipe
    tests: list[ArtifactTest] = []
    for control in grid.implementation_controls:
        metrics: dict[str, Any]
        if control == "owner_rsi_macd_stochrsi":
            metrics = {
                "observed_family": recipe.indicator["observed_indicator_family"],
                "probe_family": recipe.indicator["probe_indicator_family"],
                "observed_equals_probe": recipe.indicator["observed_equals_probe"],
                "probe_source_git_blob_sha": recipe.indicator["probe_source_git_blob_sha"],
                "parity_status": parity["status"],
            }
            control_status = "PASS"
            finding = "owner_implementation_executed"
        else:
            close = _close(loaded)
            fast = close.ewm(span=12, adjust=False).mean()
            slow = close.ewm(span=26, adjust=False).mean()
            macd = fast - slow
            signal = macd.ewm(span=9, adjust=False).mean()
            histogram = macd - signal
            control_frame = pd.DataFrame({
                "rsi_macd": macd,
                "rsi_macd_signal": signal,
                "rsi_macd_hist": histogram,
            })
            metrics = {
                "control_family": "standard_price_macd",
                "fast": 12,
                "slow": 26,
                "signal": 9,
                "input": "close",
                "finite_histogram_count": int(np.isfinite(histogram.to_numpy(dtype=float)).sum()),
                "histogram_total_variation": float(np.abs(np.diff(histogram.to_numpy(dtype=float))).sum()),
                "events": _events(control_frame),
            }
            control_status = "PASS"
            finding = "standard_price_macd_control_executed"
        tests.append(_artifact_test(
            "K", control,
            {"control": control, "csv_sha256": loaded.csv_sha256, "metrics": metrics},
            control_status, metrics, (finding,),
        ))
    for control in grid.data_plane_controls:
        metrics = {
            "tickerid": recipe.instrument["tickerid"],
            "main_tickerid": recipe.instrument["main_tickerid"],
            "exchange": recipe.instrument["exchange"],
            "vendor_feed": recipe.instrument["vendor_feed"],
            "price_adjustment": recipe.chart["price_adjustment"],
            "dividend_adjustment": recipe.chart["dividend_adjustment"],
            "back_adjustment": recipe.chart["back_adjustment"],
            "settlement_as_close": recipe.chart["settlement_as_close"],
        }
        tests.append(_artifact_test(
            "D", control,
            {"control": control, "csv_sha256": loaded.csv_sha256, "metrics": metrics},
            "PASS", metrics, ("exact_recipe_data_plane_recorded",),
        ))
    return tuple(tests)


def _lower_evidence_unavailable_tests(
    loaded: LoadedChartExport,
    grid: ArtifactGrid,
) -> tuple[ArtifactTest, ...]:
    tests: list[ArtifactTest] = []
    tests.extend(
        _unavailable(
            "G", f"grain_minutes_{grain}", loaded.csv_sha256,
            "LOWER_GRAIN_EVIDENCE_UNAVAILABLE",
        )
        for grain in grid.human_chart_grains_minutes
    )
    tests.extend(
        _unavailable(
            "A", f"session_{session}_phase_{phase:g}", loaded.csv_sha256,
            "LOWER_GRAIN_EVIDENCE_UNAVAILABLE",
        )
        for session in grid.session_variants
        for phase in grid.anchor_phase_fractions
    )
    tests.append(_unavailable(
        "A", "phase_uniqueness", loaded.csv_sha256,
        "LOWER_GRAIN_EVIDENCE_UNAVAILABLE",
    ))
    tests.extend(
        _unavailable(
            "K", f"memory_target_minutes_{grain}", loaded.csv_sha256,
            "LOWER_GRAIN_EVIDENCE_UNAVAILABLE",
        )
        for grain in grid.memory_matched_grains_minutes
    )
    return tuple(tests)


def _run_diagnostics(
    loaded: LoadedChartExport,
    *,
    lower_grain_rows: pd.DataFrame | None,
    grid: ArtifactGrid,
) -> tuple[dict[str, Any], tuple[ArtifactTest, ...]]:
    try:
        parity_receipt = compare_indicator_parity(loaded, tolerance=1e-10)
        parity = parity_receipt.to_dict()
        tests: list[ArtifactTest] = [_parity_test(parity, loaded.csv_sha256)]
        tests.extend(truncation_invariance(_close(loaded), drop_prefixes=_DROP_PREFIXES, comparison_tail=256, tolerance=1e-10))
        tests.extend(_chart_type_tests(loaded.recipe, loaded.csv_sha256))
        tests.extend(_implementation_and_data_tests(loaded, grid, parity))
        if lower_grain_rows is None:
            tests.extend(_lower_evidence_unavailable_tests(loaded, grid))
        else:
            if type(lower_grain_rows) is not pd.DataFrame:
                raise ArtifactAttackError("lower_grain_rows must be an exact DataFrame or null")
            ga_tests, sequences = _grain_and_anchor_tests(loaded, lower_grain_rows.copy(deep=True), grid)
            tests.extend(ga_tests)
            tests.extend(_kernel_tests(loaded, grid, sequences))
        return parity, tuple(tests)
    except ArtifactAttackError:
        raise
    except (ParityError, SessionBarsError, KeyError, TypeError, ValueError) as exc:
        raise ArtifactAttackError("artifact diagnostics rejected malformed evidence") from exc


def _observed_channel(
    loaded: LoadedChartExport,
    parity: Mapping[str, Any],
) -> tuple[str, str]:
    indicator = loaded.recipe.indicator
    status = "PASS" if parity["status"] == "PASS" else "FAIL" if parity["status"] == "FAIL" else "UNRESOLVED_DATA"
    receipt = _hash({
        "channel": "observed_indicator_reproduction",
        "csv_sha256": loaded.csv_sha256,
        "observed_indicator_family": indicator["observed_indicator_family"],
        "observed_indicator_inputs": dict(indicator["observed_indicator_inputs"]),
        "observed_indicator_source_hash": indicator["observed_indicator_source_hash"],
        "observed_indicator_source_kind": indicator["observed_indicator_source_kind"],
        "observed_indicator_title": indicator["observed_indicator_title"],
        "parity": dict(parity),
        "recipe_id": loaded.recipe.recipe_id,
    })
    return status, receipt


def _owner_channel(loaded: LoadedChartExport) -> tuple[str, str]:
    indicator = loaded.recipe.indicator
    signature = canonical_kernel_signature(_close(loaded))
    receipt = _hash({
        "channel": "owner_probe_control",
        "indicator_spec_hash": signature.indicator_spec_hash,
        "probe_ema_adjust": indicator["probe_ema_adjust"],
        "probe_indicator_family": indicator["probe_indicator_family"],
        "probe_inputs": dict(indicator["probe_inputs"]),
        "probe_rma_seed": indicator["probe_rma_seed"],
        "probe_source_git_blob_sha": indicator["probe_source_git_blob_sha"],
        "recipe_id": loaded.recipe.recipe_id,
    })
    return "PASS", receipt


def run_artifact_attack(
    loaded: LoadedChartExport,
    *,
    lower_grain_rows: pd.DataFrame | None,
    grid: ArtifactGrid,
    ledger_path: Path,
) -> ArtifactAttackResult:
    """Register, execute, and totalize one research-only W1A artifact attack."""
    if type(loaded) is not LoadedChartExport:
        raise ArtifactAttackError("loaded must be an exact attested LoadedChartExport")
    if not isinstance(grid, ArtifactGrid):
        raise ArtifactAttackError("grid must be an ArtifactGrid")
    recipe = loaded.recipe
    if recipe.chart["named_session"] not in grid.session_variants:
        raise ArtifactAttackError("frozen grid omits the active named session")
    register_artifact_grid(grid, ledger_path=ledger_path, info_cutoff=recipe.captured_at)
    parity, tests = _run_diagnostics(loaded, lower_grain_rows=lower_grain_rows, grid=grid)
    status = classify_mechanical_status(recipe.capture_status == "complete", str(parity["status"]), tests)
    observed_status, observed_receipt = _observed_channel(loaded, parity)
    probe_status, probe_receipt = _owner_channel(loaded)
    mechanical_receipts = tuple(sorted({grid.sha256(), *(_hash(test.to_dict()) for test in tests)}))
    return ArtifactAttackResult(
        schema_version=ARTIFACT_ATTACK_SCHEMA, operation_key=_OPERATION_KEY,
        recipes=(recipe.recipe_id,), frozen_grid_hash=grid.sha256(), trial_family=_TRIAL_FAMILY,
        tests=tests, parity=parity, mechanical_status=status,  # type: ignore[arg-type]
        final_mechanism_classification=None, mechanical_receipts=mechanical_receipts,
        observed_indicator_reproduction={"status": observed_status},
        observed_indicator_reproduction_receipts=(observed_receipt,),
        owner_probe_control={"status": probe_status}, owner_probe_control_receipts=(probe_receipt,),
        authority=dict(_AUTHORITY),
    )


__all__ = [
    "ArtifactAttackError", "ArtifactGrid", "classify_artifact_attack", "classify_mechanical_status",
    "default_artifact_grid", "register_artifact_grid", "run_artifact_attack",
]
