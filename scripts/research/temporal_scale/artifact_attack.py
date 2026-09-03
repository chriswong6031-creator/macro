"""Frozen, outcome-blind G/A/K/D artifact diagnostics for temporal scale W1A.

The module consumes only an attested chart export and optional locally supplied
lower-grain bars. It deliberately has no market-data, outcome, ranking, or
production-control surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
    LowerGrainRecipe,
    strict_json_dumps,
)
from scripts.research.temporal_scale.parity import (
    ParityError,
    canonical_indicator_frame,
    compare_indicator_parity,
    truncation_invariance,
)
from scripts.research.temporal_scale.kernel_memory import (
    canonical_kernel_signature,
    parameterized_indicator_frame,
)
from scripts.research.temporal_scale.session_bars import (
    BarGridSpec,
    SessionBarsError,
    SessionInterval,
    _bounds,
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
        ) + ("phase_uniqueness", "chart_price_construction")),
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
    if not recipe_complete or parity_status == "UNRESOLVED_DATA":
        return "UNRESOLVED_DATA"
    artifact = (
        parity_status == "FAIL"
        or any("FAIL" in statuses.get(axis, ()) for axis in _REQUIRED_AXES)
        or any("single_arbitrary_phase_only" in test.findings for test in records)
    )
    if artifact:
        return "ARTIFACT"
    unresolved = (
        any("UNAVAILABLE" in statuses.get(axis, ()) for axis in _REQUIRED_AXES)
        or any(axis not in statuses for axis in _REQUIRED_AXES)
    )
    return "UNRESOLVED_DATA" if unresolved else "MECHANICALLY_SURVIVES"


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
    status = (
        "PASS" if parity["status"] == "PASS"
        else "FAIL" if parity["status"] == "FAIL"
        else "UNAVAILABLE"
    )
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
        failures or (
            "exact_owner_probe_parity"
            if status == "PASS"
            else "PARITY_NO_COMPARABLE_ROWS",
        ),
    )


def _unavailable(axis: str, variant_id: str, source_hash: str, token: str) -> ArtifactTest:
    return _artifact_test(
        axis, variant_id, {"axis": axis, "source": source_hash, "variant_id": variant_id},
        "UNAVAILABLE", {"available": False}, (token,),
    )


def _session_evidence(
    recipe: ChartRecipe,
    name: str,
) -> tuple[tuple[SessionInterval, ...], dict[str, tuple[SessionInterval, ...]]] | None:
    """Resolve a session literal only from the recipe's evidenced grammar."""
    definitions = recipe.chart.get("session_definitions")
    if not isinstance(definitions, Mapping) or name not in definitions:
        return None
    definition = definitions[name]
    if not isinstance(definition, Mapping):
        raise ArtifactAttackError("session definition must be an object")

    def intervals(value: object) -> tuple[SessionInterval, ...]:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ArtifactAttackError("session intervals must be an evidenced sequence")
        try:
            return tuple(
                SessionInterval(
                    start_local=str(item["start_local"]),
                    end_local=str(item["end_local"]),
                    label=str(item["label"]),
                )
                for item in value
                if isinstance(item, Mapping)
            )
        except (KeyError, TypeError, ValueError, SessionBarsError) as exc:
            raise ArtifactAttackError("session interval evidence is malformed") from exc

    base = intervals(definition.get("intervals"))
    raw_overrides = definition.get("date_overrides")
    if not isinstance(raw_overrides, Mapping):
        raise ArtifactAttackError("session date overrides must be an object")
    overrides = {str(day): intervals(value) for day, value in raw_overrides.items()}
    return base, overrides


def _bars_for(
    rows: pd.DataFrame,
    recipe: ChartRecipe,
    *,
    grain: int,
    phase_fraction: float,
    session_name: str,
) -> tuple[pd.DataFrame, tuple[object, ...]] | None:
    evidence = _session_evidence(recipe, session_name)
    if evidence is None:
        return None
    intervals, date_overrides = evidence
    try:
        definition = recipe.chart["session_definitions"][session_name]
        session_timezone = str(definition["timezone"])
        zone = ZoneInfo(session_timezone)
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        raise ArtifactAttackError("recipe session timezone is invalid") from exc

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
            local_day = datetime.fromtimestamp(open_ms / 1000, zone).date()
            candidate_days = (local_day - timedelta(days=1), local_day)
            selected.append(any(
                open_ms >= interval_open and close_ms <= interval_close
                for day in candidate_days
                for interval_open, interval_close in (
                    _bounds(
                        day,
                        interval,
                        zone,
                    )
                    for interval in date_overrides.get(day.isoformat(), intervals)
                )
            ))
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
        timezone=session_timezone, nominal_minutes=grain,
        phase_minutes=phase_minutes, intervals=intervals, include_empty=False,
        close_delay_minutes=0, date_overrides=date_overrides,
    )
    try:
        bars, receipts = build_session_bars(session_rows, recipe_id=recipe.recipe_id, grid=spec)
    except SessionBarsError as exc:
        if str(exc) == "lower-grain row outside every declared session":
            return None
        raise ArtifactAttackError("malformed lower-grain evidence") from exc
    bars.attrs["session_definition_sha256"] = _hash(definition)
    bars.attrs["session_definition_provenance"] = dict(definition["provenance"])
    return bars, tuple(receipts)


def _exact_bar_match(
    observed: pd.DataFrame,
    reconstructed: pd.DataFrame,
    lower: pd.DataFrame,
) -> tuple[bool, dict[str, Any]]:
    """Prove boundary, allocation, adjacency, OHLC, and available-volume identity."""
    observed_columns = {
        "TG_time_open_ms", "TG_time_close_ms", "TG_open", "TG_high", "TG_low", "TG_close",
    }
    reconstructed_columns = {"open_ms", "close_ms", "open", "high", "low", "close", "volume"}
    lower_columns = reconstructed_columns
    if not observed_columns.issubset(observed.columns):
        raise ArtifactAttackError("observed bar evidence is incomplete")
    if not reconstructed_columns.issubset(reconstructed.columns) or not lower_columns.issubset(lower.columns):
        raise ArtifactAttackError("reconstructed bar evidence is incomplete")

    tolerance = 1e-10
    observed_rows = list(observed.itertuples(index=False))
    reconstructed_by_bounds = {
        (int(row.open_ms), int(row.close_ms)): row
        for row in reconstructed.itertuples(index=False)
    }
    duplicate_reconstructed_bounds = len(reconstructed_by_bounds) != len(reconstructed)
    duplicate_source_bounds = bool(lower[["open_ms", "close_ms"]].duplicated().any())
    ordered_lower = lower.sort_values(["open_ms", "close_ms"])
    source_nonoverlap = bool(
        len(ordered_lower) < 2
        or np.all(
            ordered_lower["close_ms"].to_numpy(dtype=np.int64)[:-1]
            <= ordered_lower["open_ms"].to_numpy(dtype=np.int64)[1:]
        )
    )
    assigned: list[int] = []
    boundary_match = not duplicate_reconstructed_bounds and len(observed_rows) == len(reconstructed)
    endpoint_coverage = True
    adjacency = True
    ohlc_match = True
    volume_match = True
    per_bar_source_counts: list[int] = []

    for observed_row in observed_rows:
        bounds = (int(observed_row.TG_time_open_ms), int(observed_row.TG_time_close_ms))
        rebuilt = reconstructed_by_bounds.get(bounds)
        if rebuilt is None:
            boundary_match = False
        members = lower[
            (lower["open_ms"] >= bounds[0]) & (lower["close_ms"] <= bounds[1])
        ]
        per_bar_source_counts.append(len(members))
        if members.empty:
            endpoint_coverage = False
            adjacency = False
            ohlc_match = False
            volume_match = False
            continue
        member_indexes = [int(value) for value in members.index]
        assigned.extend(member_indexes)
        member_opens = members["open_ms"].to_numpy(dtype=np.int64)
        member_closes = members["close_ms"].to_numpy(dtype=np.int64)
        endpoint_coverage &= int(member_opens[0]) == bounds[0] and int(member_closes[-1]) == bounds[1]
        adjacency &= bool(np.all(member_closes[:-1] == member_opens[1:]))
        aggregated = {
            "open": float(members["open"].iloc[0]),
            "high": float(members["high"].max()),
            "low": float(members["low"].min()),
            "close": float(members["close"].iloc[-1]),
            "volume": float(members["volume"].sum()),
        }
        observed_values = {
            "open": float(observed_row.TG_open),
            "high": float(observed_row.TG_high),
            "low": float(observed_row.TG_low),
            "close": float(observed_row.TG_close),
        }
        ohlc_match &= all(abs(observed_values[name] - aggregated[name]) <= tolerance for name in observed_values)
        if rebuilt is not None:
            ohlc_match &= all(abs(float(getattr(rebuilt, name)) - aggregated[name]) <= tolerance for name in observed_values)
            volume_match &= abs(float(rebuilt.volume) - aggregated["volume"]) <= tolerance
        observed_volume = getattr(observed_row, "TG_volume", None)
        if observed_volume is not None and not pd.isna(observed_volume):
            volume_match &= abs(float(observed_volume) - aggregated["volume"]) <= tolerance

    if observed_rows:
        first_open = min(int(row.TG_time_open_ms) for row in observed_rows)
        last_close = max(int(row.TG_time_close_ms) for row in observed_rows)
        eligible = lower[(lower["open_ms"] < last_close) & (lower["close_ms"] > first_open)]
        eligible_indexes = [int(value) for value in eligible.index]
    else:
        eligible_indexes = []
        endpoint_coverage = False
    assigned_once = sorted(assigned) == sorted(eligible_indexes) and len(assigned) == len(set(assigned))
    exact = all((
        bool(observed_rows), boundary_match, endpoint_coverage, adjacency,
        assigned_once, not duplicate_source_bounds, source_nonoverlap, ohlc_match, volume_match,
    ))
    return exact, {
        "adjacent_source_rows": adjacency,
        "assigned_source_rows": len(assigned),
        "boundary_match": boundary_match,
        "duplicate_source_bounds": duplicate_source_bounds,
        "eligible_source_rows": len(eligible_indexes),
        "endpoint_coverage": endpoint_coverage,
        "every_source_row_assigned_once": assigned_once,
        "observed_bars": len(observed_rows),
        "ohlc_match": ohlc_match,
        "per_bar_source_counts": per_bar_source_counts,
        "reconstructed_bars": len(reconstructed),
        "source_nonoverlap": source_nonoverlap,
        "volume_match": volume_match,
    }


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
        "session_definition_sha256": bars.attrs.get("session_definition_sha256"),
        "session_definition_provenance": bars.attrs.get("session_definition_provenance"),
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


def _observed_indicator_frame(loaded: LoadedChartExport) -> pd.DataFrame:
    frame = loaded.frame
    return pd.DataFrame(
        {
            "rsi": frame["TG_rsi"].to_numpy(dtype=float),
            "rsi_macd": frame["TG_rsi_macd"].to_numpy(dtype=float),
            "rsi_macd_signal": frame["TG_rsi_macd_signal"].to_numpy(dtype=float),
            "rsi_macd_hist": frame["TG_rsi_macd_hist"].to_numpy(dtype=float),
            "stoch_k": frame["TG_stoch_k"].to_numpy(dtype=float),
            "stoch_d": frame["TG_stoch_d"].to_numpy(dtype=float),
        },
        index=pd.Index(frame["TG_time_close_ms"].tolist(), dtype="int64", name="TG_time_close_ms"),
    )


def _project_indicator_path(frame: pd.DataFrame, clock: pd.Index) -> pd.DataFrame:
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ArtifactAttackError("indicator path clock must be strictly increasing")
    union = frame.index.union(clock).sort_values()
    return frame.reindex(union).ffill().reindex(clock)


def _path_comparison(
    observed: pd.DataFrame,
    candidate: pd.DataFrame,
    clock: pd.Index,
) -> dict[str, Any]:
    left = _project_indicator_path(observed, clock)
    right = _project_indicator_path(candidate, clock)
    columns = tuple(observed.columns)
    fully_finite = np.isfinite(left[list(columns)].to_numpy(dtype=float)).all(axis=1)
    fully_finite &= np.isfinite(right[list(columns)].to_numpy(dtype=float)).all(axis=1)
    common_rows = int(fully_finite.sum())
    distances: dict[str, dict[str, float | int | None]] = {}
    for name in columns:
        left_values = left[name].to_numpy(dtype=float)
        right_values = right[name].to_numpy(dtype=float)
        mask = np.isfinite(left_values) & np.isfinite(right_values)
        delta = np.abs(left_values[mask] - right_values[mask])
        distances[name] = {
            "common_finite_rows": int(mask.sum()),
            "mean_abs": float(delta.mean()) if len(delta) else None,
            "max_abs": float(delta.max()) if len(delta) else None,
        }
    left_common = left.loc[fully_finite]
    right_common = right.loc[fully_finite]
    sign_topology_equal = bool(common_rows) and np.array_equal(
        np.sign(left_common["rsi_macd_hist"].to_numpy(dtype=float)),
        np.sign(right_common["rsi_macd_hist"].to_numpy(dtype=float)),
    )
    comparable_mask = pd.Series(fully_finite, index=clock, dtype=bool)
    left_events = _events(left.where(comparable_mask, axis=0))
    right_events = _events(right.where(comparable_mask, axis=0))
    event_symmetric_difference = {
        key: sorted(set(left_events[key]) ^ set(right_events[key]))
        for key in left_events
    }
    distance_pass = bool(common_rows) and all(
        value["max_abs"] is not None and float(value["max_abs"]) <= 1e-10
        for value in distances.values()
    )
    event_pass = not any(event_symmetric_difference.values())
    return {
        "common_lower_clock_rows": len(clock),
        "common_finite_rows": common_rows,
        "event_symmetric_difference": event_symmetric_difference,
        "path_pass": distance_pass and sign_topology_equal and event_pass,
        "per_output_path_distance": distances,
        "sign_topology_equal": sign_topology_equal,
    }


def _phase_uniqueness_test(
    phase_results: Mapping[float, Mapping[str, object]],
    source_hash: str,
) -> ArtifactTest:
    phases = tuple(sorted(phase_results))
    if not phases or any(not bool(phase_results[phase].get("coverage")) for phase in phases):
        return _unavailable("A", "phase_uniqueness", source_hash, "A_PHASE_STABILITY_UNAVAILABLE")
    semantic = phase_results.get(0.0)
    nonzero_bar = [
        phase for phase in phases
        if phase != 0.0 and bool(phase_results[phase].get("bar_match"))
    ]
    nonzero_path = [
        phase for phase in phases
        if phase != 0.0 and bool(phase_results[phase].get("path_pass"))
    ]
    arbitrary_only = (
        semantic is not None
        and not bool(semantic.get("bar_match"))
        and not bool(semantic.get("path_pass"))
        and len(nonzero_bar) == 1
        and nonzero_bar == nonzero_path
    )
    metrics = {
        "bar_matching_phases": nonzero_bar,
        "path_passing_phases": nonzero_path,
        "phase_results": {str(phase): dict(phase_results[phase]) for phase in phases},
        "semantic_phase": 0.0,
    }
    return _artifact_test(
        "A", "phase_uniqueness", {"source": source_hash, "phase_results": metrics["phase_results"]},
        "PASS", metrics,
        ("single_arbitrary_phase_only",) if arbitrary_only else ("single_arbitrary_phase_not_detected",),
    )


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
        built = _bars_for(confirmed_lower, recipe, grain=grain, phase_fraction=0.0, session_name=named)
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

    observed = loaded.frame
    observed_path = _observed_indicator_frame(loaded)
    lower_clock = pd.Index(
        confirmed_lower["close_ms"].tolist(), dtype="int64", name="TG_time_close_ms",
    )
    if len(observed):
        lower_clock = lower_clock[
            (lower_clock >= int(observed["TG_time_open_ms"].min()))
            & (lower_clock <= int(observed["TG_time_close_ms"].max()))
        ]
    phase_results: dict[float, dict[str, object]] = {}
    for session in grid.session_variants:
        for phase in grid.anchor_phase_fractions:
            built = _bars_for(confirmed_lower, recipe, grain=nominal, phase_fraction=phase, session_name=session)
            variant = f"session_{session}_phase_{phase:g}"
            if built is None:
                tests.append(_unavailable("A", variant, source_hash, "A_SESSION_RECONSTRUCTION_UNAVAILABLE"))
                if session == named:
                    phase_results[phase] = {"coverage": False, "bar_match": False, "path_pass": False}
                continue
            bars, receipts = built
            if bars.empty:
                tests.append(_unavailable("A", variant, source_hash, "A_SESSION_ROWS_UNAVAILABLE"))
                if session == named:
                    phase_results[phase] = {"coverage": False, "bar_match": False, "path_pass": False}
                continue
            exact, bar_metrics = _exact_bar_match(observed, bars, confirmed_lower)
            candidate_close = pd.Series(
                bars["close"].to_numpy(dtype=float),
                index=pd.Index(bars["close_ms"].tolist(), dtype="int64", name="TG_time_close_ms"),
                dtype=float,
            )
            candidate_path = canonical_indicator_frame(candidate_close)
            path_metrics = _path_comparison(observed_path, candidate_path, lower_clock)
            metrics = _geometry(bars, receipts)
            metrics.update(bar_metrics)
            metrics.update(path_metrics)
            metrics["exact_motivating_bar_match"] = exact
            metrics["timestamp_displacement_ms"] = 0 if exact else None
            motivating = session == named and phase == 0.0
            diagnostic_status = "PASS"
            findings = ("exact_motivating_bar_construction",) if exact else ("anchor_session_geometry_recorded",)
            if motivating and not exact:
                window_covered = (
                    bool(len(observed)) and not confirmed_lower.empty
                    and int(confirmed_lower["open_ms"].min()) <= int(observed["TG_time_open_ms"].min())
                    and int(confirmed_lower["close_ms"].max()) >= int(observed["TG_time_close_ms"].max())
                )
                diagnostic_status = "FAIL" if window_covered else "UNAVAILABLE"
                findings = (
                    "motivating_bar_construction_mismatch"
                    if window_covered
                    else "MOTIVATING_BAR_COVERAGE_INSUFFICIENT",
                )
            tests.append(_artifact_test(
                "A", variant,
                {"source": source_hash, "variant": variant, "receipts": [getattr(item, "source_row_sha256", "") for item in receipts]},
                diagnostic_status, metrics, findings,
            ))
            if session == named:
                phase_results[phase] = {
                    "coverage": bool(bar_metrics["endpoint_coverage"]),
                    "bar_match": exact,
                    "path_pass": bool(path_metrics["path_pass"]),
                }
    tests.append(_phase_uniqueness_test(phase_results, source_hash))
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

    usable = {grain: value for grain, value in sequences.items() if len(value[0]) >= 2}
    nominal = int(str(loaded.recipe.chart["timeframe_period"]))
    if nominal not in usable or len(usable) < 2:
        return unavailable_all("K_ALTERNATE_ACTUAL_CLOCK_UNAVAILABLE")
    fixed_parameters = {
        "rsi_len": 14,
        "macd_fast": 14,
        "macd_slow": 60,
        "macd_signal": 5,
        "stoch_len": 14,
        "smooth_k": 3,
        "smooth_d": 3,
    }

    def nearest_count(target_span: float, median: float) -> int:
        raw = target_span / median
        lower = max(1, math.floor(raw))
        upper = max(1, math.ceil(raw))
        return min((lower, upper), key=lambda value: (abs(value * median - target_span), value))

    def output_summary(frame: pd.DataFrame) -> dict[str, Any]:
        records = [
            {
                name: None if pd.isna(row[name]) else float(row[name])
                for name in frame.columns
            }
            for _, row in frame.iterrows()
        ]
        total_variation: dict[str, float | None] = {}
        for name in frame.columns:
            finite = frame[name].dropna().to_numpy(dtype=float)
            total_variation[name] = float(np.abs(np.diff(finite)).sum()) if len(finite) else None
        return {
            "events": _events(frame),
            "finite_rows": int(np.isfinite(frame.to_numpy(dtype=float)).all(axis=1).sum()),
            "output_sha256": _hash({"columns": list(frame.columns), "index": [int(value) for value in frame.index], "records": records}),
            "total_variation": total_variation,
        }

    def path_distance(reference: pd.DataFrame, candidate: pd.DataFrame) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in reference.columns:
            left = reference[name].to_numpy(dtype=float)
            right = candidate[name].to_numpy(dtype=float)
            mask = np.isfinite(left) & np.isfinite(right)
            delta = np.abs(left[mask] - right[mask])
            result[name] = {
                "common_finite_rows": int(mask.sum()),
                "mean_abs": float(delta.mean()) if len(delta) else None,
                "max_abs": float(delta.max()) if len(delta) else None,
            }
        return result

    def symmetric_events(left: Mapping[str, Sequence[int]], right: Mapping[str, Sequence[int]]) -> dict[str, list[int]]:
        return {key: sorted(set(left[key]) ^ set(right[key])) for key in left}

    def span_receipt(
        increments: pd.Series,
        parameters: Mapping[str, int],
        reference_median: float,
    ) -> dict[str, Any]:
        receipt: dict[str, Any] = {}
        for name, count in parameters.items():
            spans = increments.rolling(count).sum().dropna().to_numpy(dtype=float)
            quantiles = np.quantile(spans, (0.1, 0.5, 0.9)).tolist() if len(spans) else [None, None, None]
            target_span = float(fixed_parameters[name] * reference_median)
            receipt[name] = {
                "achieved_span_minutes": {"p10": quantiles[0], "median": quantiles[1], "p90": quantiles[2]},
                "mapped_bars": count,
                "mapping_error_minutes": None if quantiles[1] is None else float(quantiles[1]) - target_span,
                "target_span_minutes": target_span,
            }
        return receipt

    base_bars, base_receipts = usable[nominal]
    base_elapsed = elapsed_vector(base_bars)
    if (
        len(base_receipts) != len(base_bars)
        or not np.isfinite(base_elapsed.to_numpy(dtype=float)).all()
        or (base_elapsed <= 0).any()
        or any(
            isinstance(getattr(receipt, "effective_minutes", None), bool)
            or not isinstance(getattr(receipt, "effective_minutes", None), Real)
            or not math.isfinite(float(getattr(receipt, "effective_minutes", 0)))
            or float(getattr(receipt, "effective_minutes", 0)) <= 0
            for receipt in base_receipts
        )
    ):
        return unavailable_all("K_REFERENCE_CLOCK_UNAVAILABLE")
    base_open_session = np.asarray(
        [float(getattr(receipt, "effective_minutes")) for receipt in base_receipts], dtype=float,
    )
    base_elapsed_median = float(np.median(base_elapsed.to_numpy(dtype=float)))
    base_open_median = float(np.median(base_open_session))
    if not all(math.isfinite(value) and value > 0 for value in (base_elapsed_median, base_open_median)):
        return unavailable_all("K_REFERENCE_CLOCK_INVALID")

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
        if (
            len(receipts) != len(bars)
            or any(
                isinstance(getattr(receipt, "effective_minutes", None), bool)
                or not isinstance(getattr(receipt, "effective_minutes", None), Real)
                or not math.isfinite(float(getattr(receipt, "effective_minutes", 0)))
                or float(getattr(receipt, "effective_minutes", 0)) <= 0
                for receipt in receipts
            )
        ):
            tests.append(_unavailable(
                "K", f"memory_target_minutes_{target}", loaded.csv_sha256,
                "K_OPEN_SESSION_CLOCK_UNAVAILABLE",
            ))
            continue
        if not np.isfinite(elapsed.to_numpy(dtype=float)).all() or (elapsed <= 0).any():
            tests.append(_unavailable(
                "K", f"memory_target_minutes_{target}", loaded.csv_sha256,
                "K_ELAPSED_CLOCK_UNAVAILABLE",
            ))
            continue
        open_session = pd.Series(
            [float(getattr(receipt, "effective_minutes")) for receipt in receipts],
            index=elapsed.index,
            dtype=float,
        )
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
        elapsed_median = float(np.median(elapsed.to_numpy(dtype=float)))
        open_median = float(np.median(open_session.to_numpy(dtype=float)))
        if not all(math.isfinite(value) and value > 0 for value in (elapsed_median, open_median)):
            tests.append(_unavailable(
                "K", f"memory_target_minutes_{target}", loaded.csv_sha256,
                "K_ACTUAL_CLOCK_INVALID",
            ))
            continue
        parameter_specs = {
            "K0": dict(fixed_parameters),
            "K1": {
                name: nearest_count(float(value) * base_elapsed_median, elapsed_median)
                for name, value in fixed_parameters.items()
            },
            "K2": {
                name: nearest_count(float(value) * base_open_median, open_median)
                for name, value in fixed_parameters.items()
            },
        }
        frames = {
            execution: parameterized_indicator_frame(selected_close, parameters)
            for execution, parameters in parameter_specs.items()
        }
        executions = {
            execution: {
                "parameter_spec": parameter_specs[execution],
                **output_summary(frame),
            }
            for execution, frame in frames.items()
        }
        distances = {
            execution: path_distance(frames["K0"], frames[execution])
            for execution in ("K1", "K2")
        }
        event_differences = {
            execution: symmetric_events(executions["K0"]["events"], executions[execution]["events"])
            for execution in ("K1", "K2")
        }
        changed = [execution for execution in ("K1", "K2") if parameter_specs[execution] != parameter_specs["K0"]]
        mapping_only_executions = [
            execution
            for execution in changed
            if executions[execution]["output_sha256"] == executions["K0"]["output_sha256"]
        ]
        metrics = _geometry(bars, receipts)
        metrics.update({
            "actual_clock": "close_to_close_elapsed_minutes", "actual_clock_count": len(elapsed),
            "actual_clock_median_minutes": chosen_median, "bar_count": len(bars),
            "declared_open_session_minutes": float(sum(int(getattr(item, "effective_minutes", 0)) for item in receipts)),
            "memory_target_minutes": target, "nearest_median_grain_minutes": chosen_grain,
            "reference_elapsed_clock_median_minutes": base_elapsed_median,
            "reference_open_session_clock_median_minutes": base_open_median,
            "clock_parameter": dict(signature.clock_parameter),
            "event_symmetric_difference": event_differences,
            "executions": executions,
            "parameter_specs": parameter_specs,
            "per_output_path_distance": distances,
            "span_receipts": {
                "K1_elapsed": span_receipt(elapsed, parameter_specs["K1"], base_elapsed_median),
                "K2_open_session": span_receipt(open_session, parameter_specs["K2"], base_open_median),
            },
            "trade_clock_available": all(getattr(item, "trade_count", None) is not None for item in receipts),
            "traded_clock_available": all(getattr(item, "traded_minutes", None) is not None for item in receipts),
            "variance_clock_available": all(getattr(item, "realized_variance", None) is not None for item in receipts),
            "volume_clock_available": all(getattr(item, "volume", None) is not None for item in receipts),
        })
        tests.append(_artifact_test(
            "K", f"memory_target_minutes_{target}",
            {"csv": loaded.csv_sha256, "target": target, "grain": chosen_grain, "elapsed": elapsed.tolist(), "clock_receipt_hash": clock_receipt_hash},
            "FAIL" if mapping_only_executions else "PASS", metrics,
            (
                "K_MAPPING_ONLY_MUTATION",
                *(f"K_MAPPING_ONLY_MUTATION:{execution}" for execution in mapping_only_executions),
            ) if mapping_only_executions else ("parameterized_kernel_paths_executed",),
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
    token: str | Sequence[str] = "LOWER_GRAIN_EVIDENCE_UNAVAILABLE",
) -> tuple[ArtifactTest, ...]:
    findings = (token,) if isinstance(token, str) else tuple(token)

    def unavailable(axis: str, variant_id: str) -> ArtifactTest:
        return _artifact_test(
            axis,
            variant_id,
            {"axis": axis, "source": loaded.csv_sha256, "variant_id": variant_id},
            "UNAVAILABLE",
            {"available": False},
            findings,
        )

    tests: list[ArtifactTest] = []
    tests.extend(
        unavailable("G", f"grain_minutes_{grain}")
        for grain in grid.human_chart_grains_minutes
    )
    tests.extend(
        unavailable("A", f"session_{session}_phase_{phase:g}")
        for session in grid.session_variants
        for phase in grid.anchor_phase_fractions
    )
    tests.append(unavailable("A", "phase_uniqueness"))
    tests.extend(
        unavailable("K", f"memory_target_minutes_{grain}")
        for grain in grid.memory_matched_grains_minutes
    )
    return tuple(tests)


def _run_diagnostics(
    loaded: LoadedChartExport,
    *,
    lower_grain_rows: pd.DataFrame | None,
    lower_grain_recipe: LowerGrainRecipe | None,
    lower_grain_csv_sha256: str | None,
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
        elif lower_grain_recipe is None or lower_grain_csv_sha256 is None:
            tests.extend(_lower_evidence_unavailable_tests(
                loaded, grid, "LOWER_GRAIN_MANIFEST_UNAVAILABLE",
            ))
        else:
            if type(lower_grain_rows) is not pd.DataFrame:
                raise ArtifactAttackError("lower_grain_rows must be an exact DataFrame or null")
            if not isinstance(lower_grain_recipe, LowerGrainRecipe):
                raise ArtifactAttackError("lower_grain_recipe must be an exact LowerGrainRecipe or null")
            confirmed = _confirmed_lower(lower_grain_rows)
            if confirmed.empty:
                tests.extend(_lower_evidence_unavailable_tests(
                    loaded, grid, "LOWER_GRAIN_CONFIRMED_ROWS_UNAVAILABLE",
                ))
            else:
                durations = (
                    (confirmed["close_ms"] - confirmed["open_ms"]) / 60_000
                ).to_numpy(dtype=float)
                if (
                    not np.isfinite(durations).all()
                    or not np.equal(durations, np.floor(durations)).all()
                    or len(set(int(value) for value in durations)) != 1
                ):
                    mismatch_tokens = ("LOWER_MANIFEST_SOURCE_TIMEFRAME_UNRESOLVED",)
                else:
                    mismatch_tokens = lower_grain_recipe.mismatches(
                        loaded.recipe,
                        csv_sha256=lower_grain_csv_sha256,
                        row_count=len(confirmed),
                        first_open_ms=int(confirmed["open_ms"].iloc[0]),
                        last_close_ms=int(confirmed["close_ms"].iloc[-1]),
                        source_timeframe_minutes=int(durations[0]),
                    )
                if mismatch_tokens:
                    tests.extend(_lower_evidence_unavailable_tests(loaded, grid, mismatch_tokens))
                else:
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
    exact_inheritance = (
        indicator["observed_equals_probe"] is True
        and indicator["observed_indicator_source_kind"] in {"repository_exact", "pine_source_exact"}
        and indicator["observed_indicator_family"] == indicator["probe_indicator_family"]
        and indicator["observed_indicator_source_hash"] == indicator["probe_source_git_blob_sha"]
        and indicator["observed_indicator_inputs"] == indicator["probe_inputs"]
    )
    status = (
        "UNRESOLVED_DATA" if not exact_inheritance
        else "PASS" if parity["status"] == "PASS"
        else "FAIL" if parity["status"] == "FAIL"
        else "UNRESOLVED_DATA"
    )
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
    lower_grain_recipe: LowerGrainRecipe | None = None,
    lower_grain_csv_sha256: str | None = None,
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
    parity, tests = _run_diagnostics(
        loaded,
        lower_grain_rows=lower_grain_rows,
        lower_grain_recipe=lower_grain_recipe,
        lower_grain_csv_sha256=lower_grain_csv_sha256,
        grid=grid,
    )
    observed_status, observed_receipt = _observed_channel(loaded, parity)
    probe_status, probe_receipt = _owner_channel(loaded)
    status = classify_mechanical_status(recipe.capture_status == "complete", str(parity["status"]), tests)
    if status == "MECHANICALLY_SURVIVES" and observed_status != "PASS":
        status = "UNRESOLVED_DATA"
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
