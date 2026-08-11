"""Governed coherent-target CPI ridge shadow.

This module is deliberately narrower than the legacy Release Radar models.  It
fits only the preregistered ``coherent_ridge_v1`` CPI headline/core candidates,
uses the completed Wave 2A target cohort, and raises on every incomplete or
inconsistent contract.  The producer catches those failures and publishes no
candidate point or forward-ledger row.

The implementation is pure NumPy/pandas (plus PyYAML for the governed registry)
and has no scoring, ranking, trading, Prophet, or Neural Web authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import yaml


SCHEMA = "release_cpi_coherent_shadow.v1"
MODEL_ID = "coherent_ridge_v1"
MODEL_EPOCH = "coherent_ridge_v1"
TARGET_EPOCH = "alfred_same_release_vintage_proxy_v1"

RIDGE_LAMBDA = 1.0
MIN_TRAIN_OBS = 60
MIN_INTERVAL_OBS = 24
INTERVAL_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

REGISTRY_PATH = Path("config/release_forecast_model_registry.yml")
PREREG_PATH = Path("research/release_forecast/PREREG_COHERENT_RIDGE_V1.md")
HISTORY_PATH = Path(
    "data/release_forecast/cpi_truth/alfred_same_release_vintage_proxy_v1.json"
)
PARITY_PATH = Path("data/release_forecast/cpi_truth/parity_report.json")
COMPLETION_PATH = Path("data/release_forecast/cpi_truth/build_completion.json")
VINTAGES_PATH = Path("data/fred_vintage/vintages.parquet")
GASOLINE_PATH = Path("data/fred/GASREGW.parquet")

FEATURE_ORDER: dict[str, tuple[str, ...]] = {
    "cpi_headline": (
        "cpi_hl_mom_lag1",
        "cpi_hl_mom_lag2",
        "cpi_hl_mom_lag3",
        "sticky_mom_lag1",
        "median_mom_lag1",
        "flex_mom_lag1",
        "gasoline_mom",
        "ppi_mom_lag1",
    ),
    "cpi_core": (
        "cpi_core_mom_lag1",
        "cpi_core_mom_lag2",
        "cpi_core_mom_lag3",
        "sticky_mom_lag1",
        "median_mom_lag1",
        "flex_mom_lag1",
        "ppi_mom_lag1",
    ),
}

_RATE_SERIES = {
    "sticky_mom_lag1": ("STICKCPIM157SFRBATL", False),
    "median_mom_lag1": ("MEDCPIM158SFRBCLE", True),
    "flex_mom_lag1": ("FLEXCPIM157SFRBATL", False),
}
_PERIOD_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


class CoherentShadowContractError(ValueError):
    """The frozen candidate contract is incomplete or inconsistent."""


class MissingFeatureError(CoherentShadowContractError):
    """An exact-period feature is not available by the decision cutoff."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def _sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _payload_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _seal_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic receipt whose sha256 covers every other field."""
    if "sha256" in payload:
        raise CoherentShadowContractError("receipt payload already contains sha256")
    body = dict(payload)
    return {**body, "sha256": _payload_sha256(body)}


def verify_sealed_receipt(receipt: Mapping[str, Any]) -> bool:
    """Verify a receipt produced by :func:`_seal_receipt`."""
    if not isinstance(receipt, Mapping):
        return False
    claimed = receipt.get("sha256")
    if not isinstance(claimed, str) or not re.fullmatch(r"[0-9a-f]{64}", claimed):
        return False
    body = {key: value for key, value in receipt.items() if key != "sha256"}
    return _payload_sha256(body) == claimed


def _artifact(root: Path, relative_path: Path) -> tuple[bytes, dict[str, Any]]:
    path = root / relative_path
    if not path.is_file():
        raise CoherentShadowContractError(f"required artifact is missing: {relative_path}")
    body = path.read_bytes()
    if not body:
        raise CoherentShadowContractError(f"required artifact is empty: {relative_path}")
    return body, {
        "path": relative_path.as_posix(),
        "sha256": _sha256_bytes(body),
        "bytes": len(body),
    }


def _json_artifact(
    root: Path,
    relative_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    body, receipt = _artifact(root, relative_path)
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoherentShadowContractError(
            f"required artifact is not valid JSON: {relative_path}"
        ) from exc
    if not isinstance(value, dict):
        raise CoherentShadowContractError(
            f"required artifact is not a JSON object: {relative_path}"
        )
    return value, receipt


def _as_date(value: date | str, *, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise CoherentShadowContractError(f"{field} is not an ISO date") from exc
    raise CoherentShadowContractError(f"{field} is not a date")


def _clock_date(value: Any, *, field: str) -> date:
    if not isinstance(value, str) or not value:
        raise CoherentShadowContractError(f"{field} clock is missing")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise CoherentShadowContractError(f"{field} clock is invalid") from exc


def _month(value: str, *, field: str = "period") -> date:
    if not isinstance(value, str) or not _PERIOD_RE.fullmatch(value):
        raise CoherentShadowContractError(f"{field} must be canonical YYYY-MM")
    return date(int(value[:4]), int(value[5:]), 1)


def _month_text(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _shift_month(value: date, offset: int) -> date:
    ordinal = value.year * 12 + value.month - 1 + offset
    year, zero_month = divmod(ordinal, 12)
    return date(year, zero_month + 1, 1)


def _finite(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise CoherentShadowContractError(f"{field} is boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CoherentShadowContractError(f"{field} is not numeric") from exc
    if not math.isfinite(result):
        raise CoherentShadowContractError(f"{field} is not finite")
    return result


def _round_half_up_1dp(value: float) -> float:
    rounded = Decimal(str(_finite(value, field="rounded value"))).quantize(
        Decimal("0.1"),
        rounding=ROUND_HALF_UP,
    )
    result = float(rounded)
    return 0.0 if result == 0.0 else result


def _round_interval_endpoint_1dp(value: float, *, endpoint: str) -> float:
    """Round a published interval endpoint without narrowing the raw band."""
    modes = {
        "lower": ROUND_FLOOR,
        "median": ROUND_HALF_UP,
        "upper": ROUND_CEILING,
    }
    try:
        mode = modes[endpoint]
    except KeyError as exc:
        raise CoherentShadowContractError(f"unknown interval endpoint: {endpoint}") from exc
    rounded = Decimal(str(_finite(value, field="interval endpoint"))).quantize(
        Decimal("0.1"),
        rounding=mode,
    )
    result = float(rounded)
    return 0.0 if result == 0.0 else result


def _require_exact_mapping(actual: Any, expected: Mapping[str, Any], field: str) -> None:
    if actual != expected:
        raise CoherentShadowContractError(f"registry {field} does not match preregistration")


def _load_model_receipt(root: Path, asof: date) -> tuple[dict[str, Any], dict[str, Any]]:
    registry_body, registry_artifact = _artifact(root, REGISTRY_PATH)
    try:
        registry = yaml.safe_load(registry_body)
    except yaml.YAMLError as exc:
        raise CoherentShadowContractError("model registry is not valid YAML") from exc
    if not isinstance(registry, dict) or registry.get("schema") != "release_forecast_model_registry.v1":
        raise CoherentShadowContractError("model registry schema is incompatible")
    model = (registry.get("models") or {}).get(MODEL_ID)
    if not isinstance(model, dict):
        raise CoherentShadowContractError("coherent_ridge_v1 registry entry is missing")

    exact_identity = {
        "model_id": MODEL_ID,
        "model_epoch": MODEL_EPOCH,
        "callable": "engine.release_cpi_coherent_shadow.project_cpi_coherent_shadow",
        "output_schema": SCHEMA,
        "status": "shadow_candidate",
        "releases": ["cpi_headline", "cpi_core"],
    }
    for key, expected in exact_identity.items():
        if model.get(key) != expected:
            raise CoherentShadowContractError(f"registry identity field {key} is incompatible")

    target = model.get("target")
    if not isinstance(target, dict):
        raise CoherentShadowContractError("registry target contract is missing")
    target_expected = {
        "epoch": TARGET_EPOCH,
        "value_field": "published_proxy_1dp",
        "history_path": HISTORY_PATH.as_posix(),
        "parity_path": PARITY_PATH.as_posix(),
        "completion_path": COMPLETION_PATH.as_posix(),
        "require_completed_parity": True,
        "require_exact_release_calendar_lags": True,
        "cross_vintage_target_reconstruction_allowed": False,
    }
    for key, expected in target_expected.items():
        if target.get(key) != expected:
            raise CoherentShadowContractError(f"registry target field {key} is incompatible")

    expected_bindings = {
        "history": ["path", "sha256", "bytes", "history_hash"],
        "parity": ["path", "sha256", "bytes"],
        "completion": ["path", "sha256", "bytes", "evidence_available_at"],
    }
    _require_exact_mapping(
        target.get("truth_receipt_bindings"), expected_bindings, "truth receipt bindings"
    )
    _require_exact_mapping(
        target.get("artifact_gates"),
        {
            "history": {
                "schema": "release_cpi_target_history.v1",
                "status": "candidate",
                "display_only": True,
                "authority": False,
            },
            "parity": {
                "schema": "release_cpi_truth_parity.v1",
                "status": "passed",
                "display_only": True,
                "authority": False,
            },
            "completion": {
                "schema": "release_cpi_truth_build_completion.v1",
                "status": "complete",
                "completion_boundary": True,
                "display_only": True,
                "authority": False,
            },
            "exact_candidate_target_epoch_required": True,
            "official_first_print_status_required": "withheld",
        },
        "target artifact gates",
    )
    _require_exact_mapping(
        model.get("feature_order"),
        {key: list(value) for key, value in FEATURE_ORDER.items()},
        "feature order",
    )
    _require_exact_mapping(
        model.get("feature_provenance"),
        {
            "own_target_lags": {
                "source": "coherent_target_history",
                "value_field": "published_proxy_1dp",
                "period_rule": "exact_calendar_prior_months",
                "release_date_lte_decision_asof": True,
            },
            "sticky_mom_lag1": {
                "series": "STICKCPIM157SFRBATL",
                "source": "alfred_vintage",
                "source_units": "percent_change_seasonally_adjusted_monthly",
                "transform": "identity",
                "period_rule": "exact_target_minus_1_calendar_month",
            },
            "median_mom_lag1": {
                "series": "MEDCPIM158SFRBCLE",
                "source": "alfred_vintage",
                "source_units": "percent_change_at_annual_rate_seasonally_adjusted_monthly",
                "transform": "compound_annual_rate_to_monthly_percent",
                "formula": "((1 + value / 100) ** (1 / 12) - 1) * 100",
                "period_rule": "exact_target_minus_1_calendar_month",
            },
            "flex_mom_lag1": {
                "series": "FLEXCPIM157SFRBATL",
                "source": "alfred_vintage",
                "source_units": "percent_change_seasonally_adjusted_monthly",
                "transform": "identity",
                "period_rule": "exact_target_minus_1_calendar_month",
            },
            "ppi_mom_lag1": {
                "series": "PPIFIS",
                "source": "alfred_vintage",
                "source_units": "index_level_seasonally_adjusted_monthly",
                "transform": "adjacent_calendar_levels_percent_change",
                "formula": "(level_t / level_t_minus_1 - 1) * 100",
                "period_rule": "exact_target_minus_1_and_minus_2_calendar_month_pair",
            },
            "gasoline_mom": {
                "series": "GASREGW",
                "source": "unrevised_timestamp_filtered",
                "source_units": "dollars_per_gallon_weekly",
                "transform": "reference_month_average_percent_change",
                "formula": "(mean(target_month_observations) / mean(prior_month_observations) - 1) * 100",
                "target_month": "forecast_target_period",
                "prior_month": "exact_calendar_prior_month",
                "observation_timestamp_lt_decision_asof": True,
                "target_month_must_be_complete": True,
                "prior_month_must_be_complete": True,
                "releases": ["cpi_headline"],
            },
            "common_cutoff_rules": {
                "realtime_start_lte_decision_asof": True,
                "alfred_source_period_strictly_before_target": True,
            },
            "excluded_features": [
                "shelter_nowcast",
                "zori",
                "revision_optimistic_parquet_legs",
            ],
        },
        "feature provenance and transforms",
    )

    training = model.get("training") or {}
    training_expected = {
        "method": "expanding_ridge",
        "chronological_refit_each_step": True,
        "complete_case": True,
        "column_dropping_allowed": False,
        "imputation_allowed": False,
        "baseline_fallback_allowed": False,
        "minimum_complete_prior_rows": MIN_TRAIN_OBS,
        "ridge_lambda": RIDGE_LAMBDA,
        "standardization": {
            "scope": "train_only",
            "sample_std_ddof": 1,
            "zero_variance_scale": 1.0,
        },
        "intercept": {"included": True, "penalized": False},
        "solver": {
            "primary": "numpy_solve",
            "numerical_singularity_fallback": "numpy_lstsq",
        },
        "decision_cutoff": "release_date_minus_1_calendar_day",
        "decision_cutoff_must_equal_requested_asof": True,
        "training_label_release_date_lte_prediction_cutoff": True,
        "live_release_date_strictly_after_asof": True,
        "live_period_rule": "exact_calendar_month_after_latest_eligible_target",
        "numeric_features_must_be_finite": True,
        "missing_contract_behavior": "fail_closed_no_output",
    }
    for key, expected in training_expected.items():
        if training.get(key) != expected:
            raise CoherentShadowContractError(f"registry training field {key} is incompatible")

    intervals = model.get("intervals") or {}
    interval_expected = {
        "method": "empirical_prior_oos_residual_quantiles",
        "residual": "actual_raw_target_minus_raw_ridge_point",
        "quantiles": list(INTERVAL_QUANTILES),
        "interpolation": "numpy_linear",
        "strictly_prior_oos_residuals_only": True,
        "minimum_prior_oos_residuals": MIN_INTERVAL_OBS,
        "live_uses_all_prior_oos_residuals": True,
        "fallback_allowed": False,
        "band_construction": "raw_point_plus_residual_quantile",
        "published_rounding": {
            "p10_p25": "decimal_round_floor_1dp",
            "p50": "decimal_round_half_up_1dp",
            "p75_p90": "decimal_round_ceiling_1dp",
        },
    }
    for key, expected in interval_expected.items():
        if intervals.get(key) != expected:
            raise CoherentShadowContractError(f"registry interval field {key} is incompatible")

    output = model.get("output") or {}
    for key, expected in {
        "point_raw_preserved": True,
        "published_rounding": "decimal_round_half_up_1dp",
        "ledger_row_type": "shadow_projection",
        "forward_evaluation_scoring": True,
        "scoring_target_epoch_must_match": True,
        "scoring_rows_must_be_genuinely_forward": True,
        "historical_backfill_to_forward_ledger_allowed": False,
        "display_only": True,
        "authority": False,
        "promotion_authorized": False,
    }.items():
        if output.get(key) != expected:
            raise CoherentShadowContractError(f"registry output field {key} is incompatible")
    if set((model.get("authority_fence") or {}).values()) != {False}:
        raise CoherentShadowContractError("registry authority fence is open")
    exclusions = model.get("ensemble_exclusions") or {}
    if any(
        exclusions.get(key) is not expected
        for key, expected in {
            "combined_v1_input_allowed": False,
            "internal_ensemble_v1_input_allowed": False,
            "automatic_promotion_allowed": False,
            "promotion_review_allowed": False,
        }.items()
    ):
        raise CoherentShadowContractError("registry ensemble/promotion fence is open")
    if float(exclusions.get("combined_v1_weight", math.nan)) != 0.0 or float(
        exclusions.get("internal_ensemble_v1_weight", math.nan)
    ) != 0.0:
        raise CoherentShadowContractError("registry gives the shadow a nonzero weight")

    prereg = model.get("preregistration") or {}
    if prereg.get("path") != PREREG_PATH.as_posix():
        raise CoherentShadowContractError("registry preregistration path is incompatible")
    if (
        prereg.get("attempt") != 1
        or prereg.get("maximum_attempts_for_epoch") != 1
        or prereg.get("frozen_before_forward_accrual") is not True
        or prereg.get("observed_performance_allowed_in_spec") is not False
        or prereg.get("amendment_requires_new_model_epoch") is not True
    ):
        raise CoherentShadowContractError("registry preregistration is not frozen")
    prereg_body, prereg_artifact = _artifact(root, PREREG_PATH)
    prereg_text = prereg_body.decode("utf-8")
    if MODEL_ID not in prereg_text or TARGET_EPOCH not in prereg_text:
        raise CoherentShadowContractError("preregistration identity is incompatible")

    frozen_at = registry.get("frozen_at")
    if not isinstance(frozen_at, str) or _as_date(frozen_at, field="registry frozen_at") > asof:
        raise CoherentShadowContractError("model registry was not frozen by the decision date")

    receipt = _seal_receipt(
        {
            "schema": "release_cpi_coherent_model_receipt.v1",
            "model_id": MODEL_ID,
            "model_epoch": MODEL_EPOCH,
            "registry": registry_artifact,
            "preregistration": prereg_artifact,
            "frozen_at": frozen_at,
            "attempt": 1,
            "ridge_lambda": RIDGE_LAMBDA,
            "minimum_complete_prior_rows": MIN_TRAIN_OBS,
            "minimum_prior_oos_residuals": MIN_INTERVAL_OBS,
            "feature_order": {key: list(value) for key, value in FEATURE_ORDER.items()},
        }
    )
    return model, receipt


def _validate_history_targets(history: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    targets = history.get("targets")
    if not isinstance(targets, list) or not targets:
        raise CoherentShadowContractError("coherent target history has no targets")
    expected_history_hash = f"sha256:{_payload_sha256(targets)}"
    if history.get("history_hash") != expected_history_hash:
        raise CoherentShadowContractError("coherent target history payload hash mismatch")
    if history.get("n_targets") != len(targets):
        raise CoherentShadowContractError("coherent target history row count mismatch")

    index: dict[tuple[str, str], dict[str, Any]] = {}
    identities: dict[str, set[tuple[str, str]]] = {
        "cpi_headline": set(),
        "cpi_core": set(),
    }
    for position, raw in enumerate(targets):
        if not isinstance(raw, dict):
            raise CoherentShadowContractError(f"target row {position} is not an object")
        release = raw.get("release")
        if release not in FEATURE_ORDER:
            raise CoherentShadowContractError(f"target row {position} has unknown release")
        period_text = raw.get("period")
        _month(period_text, field=f"target row {position} period")
        release_day = _as_date(raw.get("release_date"), field="target release_date")
        value = _finite(raw.get("published_proxy_1dp"), field="published_proxy_1dp")
        if not math.isclose(value * 10.0, round(value * 10.0), abs_tol=1e-9):
            raise CoherentShadowContractError("coherent target is not at published 0.1pp precision")
        if raw.get("target_epoch") != TARGET_EPOCH:
            raise CoherentShadowContractError("coherent target row has the wrong target epoch")
        if raw.get("same_release_vintage") is not True:
            raise CoherentShadowContractError("coherent target is not same-release-vintage")
        if raw.get("cross_vintage_fallback_used") is not False:
            raise CoherentShadowContractError("coherent target used cross-vintage fallback")
        if raw.get("display_only") is not True or raw.get("authority") is not False:
            raise CoherentShadowContractError("coherent target authority rail is incompatible")
        key = (release, period_text)
        if key in index:
            raise CoherentShadowContractError(f"duplicate coherent target {release}/{period_text}")
        row = dict(raw)
        row["_release_date"] = release_day
        row["_target"] = value
        index[key] = row
        identities[release].add((period_text, release_day.isoformat()))
    if identities["cpi_headline"] != identities["cpi_core"]:
        raise CoherentShadowContractError("headline/core coherent histories are not aligned")
    return index


def _load_truth_receipt(
    root: Path,
    asof: date,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any], dict[str, Any]]:
    history, history_artifact = _json_artifact(root, HISTORY_PATH)
    parity, parity_artifact = _json_artifact(root, PARITY_PATH)
    completion, completion_artifact = _json_artifact(root, COMPLETION_PATH)

    if history.get("schema") != "release_cpi_target_history.v1":
        raise CoherentShadowContractError("coherent target history schema is incompatible")
    if history.get("target_epoch") != TARGET_EPOCH or history.get("status") != "candidate":
        raise CoherentShadowContractError("coherent target history epoch/status is incompatible")
    if history.get("display_only") is not True or history.get("authority") is not False:
        raise CoherentShadowContractError("coherent target history authority rail is incompatible")

    if parity.get("schema") != "release_cpi_truth_parity.v1" or parity.get("status") != "passed":
        raise CoherentShadowContractError("coherent target parity has not passed")
    parity_epoch = parity.get("candidate_target_epoch") or {}
    if parity_epoch.get("name") != TARGET_EPOCH or parity_epoch.get("promotion_authorized") is not False:
        raise CoherentShadowContractError("coherent target parity epoch is incompatible")
    if parity.get("display_only") is not True or parity.get("authority") is not False:
        raise CoherentShadowContractError("coherent target parity authority rail is incompatible")
    cases = parity.get("cases")
    if not isinstance(cases, list) or not cases or any(
        not isinstance(case, dict)
        or case.get("status")
        not in ({"passed"} if case.get("classification") != "explicit_gap" else {"explicit_gap"})
        for case in cases
    ):
        raise CoherentShadowContractError("coherent target parity cases are incomplete")

    if (
        completion.get("schema") != "release_cpi_truth_build_completion.v1"
        or completion.get("status") != "complete"
        or completion.get("completion_boundary") is not True
    ):
        raise CoherentShadowContractError("coherent truth cohort is not complete")
    if completion.get("candidate_target_epoch") != TARGET_EPOCH:
        raise CoherentShadowContractError("completion target epoch is incompatible")
    if completion.get("display_only") is not True or completion.get("authority") is not False:
        raise CoherentShadowContractError("completion authority rail is incompatible")

    history_hash = history.get("history_hash")
    if parity.get("history_hash") != history_hash or completion.get("history_hash") != history_hash:
        raise CoherentShadowContractError("truth artifacts do not bind one history hash")
    bindings = completion.get("artifacts") or {}
    history_binding = bindings.get("history") or {}
    parity_binding = bindings.get("parity") or {}
    if (
        history_binding.get("path") != history_artifact["path"]
        or history_binding.get("artifact_sha256") != history_artifact["sha256"]
        or history_binding.get("artifact_bytes") != history_artifact["bytes"]
        or history_binding.get("history_hash") != history_hash
        or parity_binding.get("path") != parity_artifact["path"]
        or parity_binding.get("artifact_sha256") != parity_artifact["sha256"]
        or parity_binding.get("artifact_bytes") != parity_artifact["bytes"]
        or parity_binding.get("history_hash") != history_hash
    ):
        raise CoherentShadowContractError("completion artifact bindings are stale or tampered")

    candidate_data_asof = history.get("candidate_data_asof")
    evidence_available_at = completion.get("evidence_available_at")
    if parity.get("candidate_data_asof") != candidate_data_asof or completion.get(
        "candidate_data_asof"
    ) != candidate_data_asof:
        raise CoherentShadowContractError("truth candidate-data clocks disagree")
    if parity.get("evidence_available_at") != evidence_available_at:
        raise CoherentShadowContractError("truth evidence clocks disagree")
    if _clock_date(candidate_data_asof, field="candidate_data_asof") > asof:
        raise CoherentShadowContractError("candidate target evidence was not available at decision date")
    if _clock_date(evidence_available_at, field="evidence_available_at") > asof:
        raise CoherentShadowContractError("completed parity was not available at decision date")

    official_epochs = [
        history.get("official_target_epoch") or {},
        parity.get("official_target_epoch") or {},
        completion.get("official_target_epoch") or {},
    ]
    if any(
        epoch.get("name") != "official_first_print_v1"
        or epoch.get("status") != "withheld"
        or epoch.get("promotion_authorized") is not False
        for epoch in official_epochs
    ):
        raise CoherentShadowContractError("withheld official-first-print rail is incompatible")

    target_index = _validate_history_targets(history)
    receipt = _seal_receipt(
        {
            "schema": "release_cpi_coherent_truth_receipt.v1",
            "target_epoch": TARGET_EPOCH,
            "history": {**history_artifact, "history_hash": history_hash},
            "parity": parity_artifact,
            "completion": {
                **completion_artifact,
                "evidence_available_at": evidence_available_at,
            },
            "candidate_data_asof": candidate_data_asof,
            "official_first_print_epoch": "withheld",
        }
    )
    return target_index, history, receipt


def _load_feature_sources(
    root: Path,
    *,
    require_gasoline: bool,
) -> tuple[pd.DataFrame, pd.DataFrame | None, dict[str, Any]]:
    vintages_body, vintages_artifact = _artifact(root, VINTAGES_PATH)
    try:
        vintages = pd.read_parquet(root / VINTAGES_PATH)
    except Exception as exc:
        raise CoherentShadowContractError("ALFRED feature parquet cannot be read") from exc
    required_columns = {"series", "period", "value", "realtime_start"}
    if not required_columns.issubset(vintages.columns):
        raise CoherentShadowContractError("ALFRED feature parquet schema is incomplete")
    vintages = vintages.copy()
    for column in ("period", "realtime_start"):
        vintages[column] = pd.to_datetime(vintages[column], errors="coerce")
    if vintages[list(required_columns - {"series", "value"})].isna().any().any():
        raise CoherentShadowContractError("ALFRED feature parquet has invalid timestamps")

    gasoline: pd.DataFrame | None = None
    source_receipts: dict[str, Any] = {"alfred_vintages": vintages_artifact}
    if require_gasoline:
        gasoline_body, gasoline_artifact = _artifact(root, GASOLINE_PATH)
        try:
            gasoline = pd.read_parquet(root / GASOLINE_PATH)
        except Exception as exc:
            raise CoherentShadowContractError("GASREGW parquet cannot be read") from exc
        if gasoline.empty or len(gasoline.columns) != 1:
            raise CoherentShadowContractError("GASREGW parquet schema is incompatible")
        gasoline = gasoline.copy()
        gasoline.index = pd.to_datetime(gasoline.index, errors="coerce")
        if gasoline.index.isna().any():
            raise CoherentShadowContractError("GASREGW parquet has invalid timestamps")
        source_receipts["gasregw"] = gasoline_artifact
        # Keep the body variables live through the reads so static reviewers can
        # see the hash is over the exact bytes parsed above.
        del gasoline_body
    del vintages_body
    return vintages, gasoline, source_receipts


def _exact_alfred_observation(
    vintages: pd.DataFrame,
    *,
    series: str,
    source_period: date,
    cutoff: date,
) -> tuple[float, dict[str, Any]]:
    """Return the latest vintage known by cutoff for one exact source month."""
    source_ts = pd.Timestamp(source_period)
    cutoff_ts = pd.Timestamp(cutoff)
    subset = vintages[
        (vintages["series"] == series)
        & (vintages["period"] == source_ts)
        & (vintages["realtime_start"] <= cutoff_ts)
    ].copy()
    if subset.empty:
        raise MissingFeatureError(
            f"{series} exact period {_month_text(source_period)} is unavailable by {cutoff}"
        )
    latest_start = subset["realtime_start"].max()
    selected = subset[subset["realtime_start"] == latest_start].copy()
    if len(selected) > 1:
        selected_values = {
            _finite(value, field=f"{series} duplicate value") for value in selected["value"]
        }
        if "realtime_end" in selected.columns:
            selected_ends = {str(value) for value in selected["realtime_end"]}
        else:
            selected_ends = {"absent"}
        if len(selected_values) != 1 or len(selected_ends) != 1:
            raise MissingFeatureError(
                f"{series} exact period {_month_text(source_period)} has ambiguous "
                "latest-vintage rows"
            )
    row = selected.iloc[0]
    value = _finite(row["value"], field=f"{series} value")
    receipt: dict[str, Any] = {
        "source": "FRED/ALFRED",
        "series_id": series,
        "source_period": _month_text(source_period),
        "realtime_start": pd.Timestamp(row["realtime_start"]).date().isoformat(),
        "realtime_start_operator": "<=",
        "decision_cutoff": cutoff.isoformat(),
        "vintage_selection": "latest_known_for_exact_period",
    }
    if "realtime_end" in row.index and not pd.isna(row["realtime_end"]):
        receipt["realtime_end"] = str(row["realtime_end"])
    return value, receipt


def _gasoline_feature(
    gasoline: pd.DataFrame,
    *,
    target_period: date,
    cutoff: date,
) -> tuple[float, dict[str, Any]]:
    cutoff_ts = pd.Timestamp(cutoff)
    current_start = pd.Timestamp(target_period)
    current_end = pd.Timestamp(_shift_month(target_period, 1))
    prior_start = pd.Timestamp(_shift_month(target_period, -1))
    if cutoff_ts < current_end:
        raise MissingFeatureError("GASREGW target calendar month is not complete at cutoff")
    if gasoline.index.has_duplicates:
        raise MissingFeatureError("GASREGW has ambiguous duplicate observation timestamps")
    known = gasoline[gasoline.index < cutoff_ts]
    column = gasoline.columns[0]
    current = known.loc[
        (known.index >= current_start) & (known.index < current_end), column
    ]
    prior = known.loc[
        (known.index >= prior_start) & (known.index < current_start), column
    ]
    current_values = pd.to_numeric(current, errors="coerce").dropna()
    prior_values = pd.to_numeric(prior, errors="coerce").dropna()
    if current_values.empty or prior_values.empty:
        raise MissingFeatureError("GASREGW exact target/prior month averages are incomplete")
    expected_current = set(pd.date_range(current_start, current_end, inclusive="left", freq="W-MON"))
    expected_prior = set(pd.date_range(prior_start, current_start, inclusive="left", freq="W-MON"))
    if set(current_values.index) != expected_current or set(prior_values.index) != expected_prior:
        raise MissingFeatureError(
            "GASREGW exact target/prior calendar months do not contain every weekly Monday"
        )
    current_avg = _finite(current_values.mean(), field="GASREGW target-month average")
    prior_avg = _finite(prior_values.mean(), field="GASREGW prior-month average")
    if prior_avg == 0.0:
        raise MissingFeatureError("GASREGW prior-month average is zero")
    value = (current_avg / prior_avg - 1.0) * 100.0
    return _finite(value, field="gasoline_mom"), {
        "source": "FRED",
        "series_id": "GASREGW",
        "source_period": _month_text(target_period),
        "prior_source_period": _month_text(_shift_month(target_period, -1)),
        "transform": "month_average_pct_change",
        "observation_timestamp_operator": "<",
        "decision_cutoff": cutoff.isoformat(),
        "target_month_observations": int(len(current_values)),
        "prior_month_observations": int(len(prior_values)),
        "target_month_last_observation": pd.Timestamp(current_values.index.max()).date().isoformat(),
        "prior_month_last_observation": pd.Timestamp(prior_values.index.max()).date().isoformat(),
    }


def _build_feature_vector(
    *,
    release: str,
    target_period: date,
    cutoff: date,
    target_index: Mapping[tuple[str, str], Mapping[str, Any]],
    history_hash: str,
    vintages: pd.DataFrame,
    gasoline: pd.DataFrame | None,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    if release not in FEATURE_ORDER:
        raise CoherentShadowContractError(f"unsupported coherent release: {release}")
    values: dict[str, float] = {}
    provenance: dict[str, dict[str, Any]] = {}

    own_prefix = "cpi_hl_mom" if release == "cpi_headline" else "cpi_core_mom"
    for lag in (1, 2, 3):
        source_period = _shift_month(target_period, -lag)
        source_text = _month_text(source_period)
        row = target_index.get((release, source_text))
        if row is None:
            raise MissingFeatureError(f"coherent target lag {release}/{source_text} is absent")
        available_at = row.get("_release_date") or _as_date(
            row.get("release_date"), field="target lag release_date"
        )
        if available_at > cutoff:
            raise MissingFeatureError(
                f"coherent target lag {release}/{source_text} was not released by cutoff"
            )
        value = row.get("_target")
        if value is None:
            value = _finite(row.get("published_proxy_1dp"), field="target lag")
        feature = f"{own_prefix}_lag{lag}"
        values[feature] = _finite(value, field=feature)
        provenance[feature] = {
            "source": "coherent_target_history",
            "source_period": source_text,
            "available_at": available_at.isoformat(),
            "value_field": "published_proxy_1dp",
            "target_epoch": TARGET_EPOCH,
            "history_hash": history_hash,
            "exact_calendar_lag": lag,
        }

    source_period = _shift_month(target_period, -1)
    for feature, (series, annualized) in _RATE_SERIES.items():
        raw, receipt = _exact_alfred_observation(
            vintages,
            series=series,
            source_period=source_period,
            cutoff=cutoff,
        )
        if annualized:
            if raw <= -100.0:
                raise MissingFeatureError("annualized median CPI rate is outside transform domain")
            value = ((1.0 + raw / 100.0) ** (1.0 / 12.0) - 1.0) * 100.0
            transform = "annual_rate_to_monthly_compound"
        else:
            value = raw
            transform = "direct_monthly_percent"
        values[feature] = _finite(value, field=feature)
        provenance[feature] = {**receipt, "transform": transform, "raw_value": raw}

    ppi_current, ppi_current_receipt = _exact_alfred_observation(
        vintages,
        series="PPIFIS",
        source_period=source_period,
        cutoff=cutoff,
    )
    ppi_prior_period = _shift_month(target_period, -2)
    ppi_prior, ppi_prior_receipt = _exact_alfred_observation(
        vintages,
        series="PPIFIS",
        source_period=ppi_prior_period,
        cutoff=cutoff,
    )
    if ppi_prior == 0.0:
        raise MissingFeatureError("PPIFIS prior exact-month level is zero")
    values["ppi_mom_lag1"] = _finite(
        (ppi_current / ppi_prior - 1.0) * 100.0,
        field="ppi_mom_lag1",
    )
    provenance["ppi_mom_lag1"] = {
        "source": "FRED/ALFRED",
        "series_id": "PPIFIS",
        "source_period": _month_text(source_period),
        "prior_source_period": _month_text(ppi_prior_period),
        "transform": "exact_month_level_pct_change",
        "current_vintage": ppi_current_receipt,
        "prior_vintage": ppi_prior_receipt,
    }

    if release == "cpi_headline":
        if gasoline is None:
            raise MissingFeatureError("GASREGW source is absent")
        gas_value, gas_receipt = _gasoline_feature(
            gasoline,
            target_period=target_period,
            cutoff=cutoff,
        )
        values["gasoline_mom"] = gas_value
        provenance["gasoline_mom"] = gas_receipt

    order = FEATURE_ORDER[release]
    if tuple(values) != order:
        # Feature construction order is not the contract order for headline
        # because gasoline is intentionally computed after the common legs.
        values = {feature: values[feature] for feature in order if feature in values}
    if tuple(values) != order or any(not math.isfinite(value) for value in values.values()):
        raise MissingFeatureError("fixed complete-case live vector is incomplete")
    provenance = {feature: provenance[feature] for feature in order}
    return values, provenance


def _fit_ridge(
    X_train: np.ndarray,
    y_train: np.ndarray,
    x_predict: np.ndarray,
) -> tuple[float, dict[str, Any]]:
    """Fit frozen ridge with train-only z-scoring and unpenalized intercept."""
    X = np.asarray(X_train, dtype=float)
    y = np.asarray(y_train, dtype=float)
    x = np.asarray(x_predict, dtype=float)
    if X.ndim != 2 or y.ndim != 1 or x.ndim != 1 or len(X) != len(y):
        raise CoherentShadowContractError("ridge matrix shapes are incompatible")
    if X.shape[1] != len(x) or len(X) < 2:
        raise CoherentShadowContractError("ridge feature dimensions are incompatible")
    if not np.isfinite(X).all() or not np.isfinite(y).all() or not np.isfinite(x).all():
        raise CoherentShadowContractError("ridge inputs are not complete and finite")

    means = np.mean(X, axis=0)
    scales = np.std(X, axis=0, ddof=1)
    scales = np.where(scales == 0.0, 1.0, scales)
    if not np.isfinite(means).all() or not np.isfinite(scales).all():
        raise CoherentShadowContractError("ridge train-only standardization failed")
    Xz = (X - means) / scales
    xz = (x - means) / scales
    design = np.column_stack((Xz, np.ones(len(Xz), dtype=float)))
    penalty = np.diag([RIDGE_LAMBDA] * X.shape[1] + [0.0])
    system = design.T @ design + penalty
    rhs = design.T @ y
    solver = "numpy_solve"
    try:
        beta = np.linalg.solve(system, rhs)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(system, rhs, rcond=None)[0]
        solver = "numpy_lstsq_numerical_singularity"
    point = float(np.append(xz, 1.0) @ beta)
    if not math.isfinite(point) or not np.isfinite(beta).all():
        raise CoherentShadowContractError("ridge produced a non-finite result")
    return point, {
        "means": [float(value) for value in means],
        "scales": [float(value) for value in scales],
        "coefficients": [float(value) for value in beta[:-1]],
        "intercept": float(beta[-1]),
        "solver": solver,
    }


def _complete_historical_records(
    *,
    release: str,
    live_period: date,
    live_cutoff: date,
    target_index: Mapping[tuple[str, str], Mapping[str, Any]],
    history_hash: str,
    vintages: pd.DataFrame,
    gasoline: pd.DataFrame | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible: list[Mapping[str, Any]] = []
    for (row_release, period_text), row in target_index.items():
        if row_release != release:
            continue
        period_month = _month(period_text)
        release_day = row.get("_release_date") or _as_date(
            row.get("release_date"), field="historical target release_date"
        )
        if period_month < live_period and release_day <= live_cutoff:
            eligible.append(row)
    eligible.sort(key=lambda row: (_month(str(row["period"])), row["_release_date"]))
    if not eligible:
        raise CoherentShadowContractError("no eligible coherent training labels")
    latest = _month(str(eligible[-1]["period"]))
    if _shift_month(latest, 1) != live_period:
        raise CoherentShadowContractError(
            "live period is not the exact month after the latest eligible coherent label"
        )

    complete: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in eligible:
        row_period = _month(str(row["period"]))
        row_release_date = row["_release_date"]
        row_cutoff = row_release_date - timedelta(days=1)
        try:
            features, _ = _build_feature_vector(
                release=release,
                target_period=row_period,
                cutoff=row_cutoff,
                target_index=target_index,
                history_hash=history_hash,
                vintages=vintages,
                gasoline=gasoline,
            )
        except MissingFeatureError as exc:
            excluded.append({"period": _month_text(row_period), "reason": str(exc)})
            continue
        complete.append(
            {
                "period": _month_text(row_period),
                "release_date": row_release_date,
                "cutoff": row_cutoff,
                "target": _finite(row["_target"], field="historical target"),
                "features": features,
            }
        )
    return complete, excluded


def _matrix(
    records: Sequence[Mapping[str, Any]],
    feature_order: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    X = np.asarray(
        [[record["features"][feature] for feature in feature_order] for record in records],
        dtype=float,
    )
    y = np.asarray([record["target"] for record in records], dtype=float)
    return X, y


def _walk_forward_residuals(
    records: Sequence[Mapping[str, Any]],
    feature_order: Sequence[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for position, record in enumerate(records):
        prior = [
            candidate
            for candidate in records[:position]
            if candidate["release_date"] <= record["cutoff"]
        ]
        if len(prior) < MIN_TRAIN_OBS:
            continue
        X, y = _matrix(prior, feature_order)
        x = np.asarray([record["features"][name] for name in feature_order], dtype=float)
        point, fit = _fit_ridge(X, y, x)
        results.append(
            {
                "period": record["period"],
                "release_date": record["release_date"].isoformat(),
                "n_train": len(prior),
                "point_raw": point,
                "actual_raw_target": float(record["target"]),
                "residual": float(record["target"] - point),
                "solver": fit["solver"],
            }
        )
    return results


def project_cpi_coherent_shadow(
    *,
    release: str,
    asof: date,
    root: str | Path,
    period: str,
    release_date: date | None,
) -> dict[str, Any]:
    """Project the preregistered coherent-target CPI shadow or raise fail-closed.

    ``asof`` is the T-1 decision cutoff.  The live release date must be exactly
    one calendar day later, every feature is required at its exact frozen source
    month, and all governed receipts must validate before fitting begins.
    """
    if release not in FEATURE_ORDER:
        raise CoherentShadowContractError(f"unsupported coherent release: {release}")
    decision_asof = _as_date(asof, field="asof")
    live_period = _month(period)
    if release_date is None:
        raise CoherentShadowContractError("release_date is required for the T-1 cutoff")
    live_release_date = _as_date(release_date, field="release_date")
    if live_release_date <= decision_asof:
        raise CoherentShadowContractError("live release date must be strictly after asof")
    if live_release_date - timedelta(days=1) != decision_asof:
        raise CoherentShadowContractError("asof must equal release_date minus one calendar day")

    repo_root = Path(root).resolve()
    model, model_receipt = _load_model_receipt(repo_root, decision_asof)
    target_index, history, truth_receipt = _load_truth_receipt(repo_root, decision_asof)
    history_hash = str(history["history_hash"])

    eligible_periods = [
        _month(period_text)
        for (row_release, period_text), row in target_index.items()
        if row_release == release and row["_release_date"] <= decision_asof
    ]
    if not eligible_periods or _shift_month(max(eligible_periods), 1) != live_period:
        raise CoherentShadowContractError(
            "live period is not the exact month after the latest eligible coherent label"
        )

    vintages, gasoline, source_receipts = _load_feature_sources(
        repo_root,
        require_gasoline=release == "cpi_headline",
    )

    if (release, period) in target_index:
        row = target_index[(release, period)]
        if row["_release_date"] <= decision_asof:
            raise CoherentShadowContractError("requested period is already an observed target")

    live_features, live_feature_provenance = _build_feature_vector(
        release=release,
        target_period=live_period,
        cutoff=decision_asof,
        target_index=target_index,
        history_hash=history_hash,
        vintages=vintages,
        gasoline=gasoline,
    )
    records, excluded = _complete_historical_records(
        release=release,
        live_period=live_period,
        live_cutoff=decision_asof,
        target_index=target_index,
        history_hash=history_hash,
        vintages=vintages,
        gasoline=gasoline,
    )
    if len(records) < MIN_TRAIN_OBS:
        raise CoherentShadowContractError(
            f"only {len(records)} complete prior rows; {MIN_TRAIN_OBS} required"
        )

    feature_order = FEATURE_ORDER[release]
    X_train, y_train = _matrix(records, feature_order)
    x_live = np.asarray([live_features[name] for name in feature_order], dtype=float)
    point_raw, fit_receipt = _fit_ridge(X_train, y_train, x_live)

    oos = _walk_forward_residuals(records, feature_order)
    if len(oos) < MIN_INTERVAL_OBS:
        raise CoherentShadowContractError(
            f"only {len(oos)} prior OOS residuals; {MIN_INTERVAL_OBS} required"
        )
    residuals = np.asarray([row["residual"] for row in oos], dtype=float)
    try:
        residual_quantiles = np.quantile(
            residuals,
            INTERVAL_QUANTILES,
            method="linear",
        )
    except TypeError:  # NumPy < 1.22 compatibility; same linear algorithm.
        residual_quantiles = np.quantile(
            residuals,
            INTERVAL_QUANTILES,
            interpolation="linear",
        )
    bounds_raw = [float(point_raw + value) for value in residual_quantiles]
    bounds = [
        _round_interval_endpoint_1dp(bounds_raw[0], endpoint="lower"),
        _round_interval_endpoint_1dp(bounds_raw[1], endpoint="lower"),
        _round_interval_endpoint_1dp(bounds_raw[2], endpoint="median"),
        _round_interval_endpoint_1dp(bounds_raw[3], endpoint="upper"),
        _round_interval_endpoint_1dp(bounds_raw[4], endpoint="upper"),
    ]
    if any(left > right for left, right in zip(bounds, bounds[1:])):
        raise CoherentShadowContractError("rounded empirical interval is unordered")

    input_manifest = _seal_receipt(
        {
            "schema": "release_cpi_coherent_input_manifest.v1",
            "release": release,
            "period": period,
            "decision_asof": decision_asof.isoformat(),
            "feature_order": list(feature_order),
            "values": live_features,
            "feature_receipts": live_feature_provenance,
            "source_artifacts": source_receipts,
            "complete_case": True,
        }
    )
    inputs_hash = input_manifest["sha256"]

    training_rows_payload = [
        {
            "period": row["period"],
            "release_date": row["release_date"].isoformat(),
            "target": row["target"],
            "features": row["features"],
        }
        for row in records
    ]
    training_receipt = _seal_receipt(
        {
            "schema": "release_cpi_coherent_training_receipt.v1",
            "release": release,
            "period": period,
            "model_epoch": MODEL_EPOCH,
            "target_epoch": TARGET_EPOCH,
            "input_manifest_sha256": input_manifest["sha256"],
            "method": "expanding_ridge",
            "decision_cutoff": decision_asof.isoformat(),
            "feature_order": list(feature_order),
            "target_value_field": "published_proxy_1dp",
            "n": len(records),
            "minimum_required": MIN_TRAIN_OBS,
            "eligible_label_release_date_max": max(
                row["release_date"] for row in records
            ).isoformat(),
            "training_period_min": records[0]["period"],
            "training_period_max": records[-1]["period"],
            "excluded_incomplete_rows": len(excluded),
            "training_rows_sha256": _payload_sha256(training_rows_payload),
            "standardization": {
                "scope": "train_only",
                "sample_std_ddof": 1,
                "zero_variance_scale": 1.0,
                "means": fit_receipt["means"],
                "scales": fit_receipt["scales"],
            },
            "ridge_lambda": RIDGE_LAMBDA,
            "intercept_penalized": False,
            "coefficients": fit_receipt["coefficients"],
            "intercept": fit_receipt["intercept"],
            "solver": fit_receipt["solver"],
        }
    )
    interval_receipt = _seal_receipt(
        {
            "schema": "release_cpi_coherent_interval_receipt.v1",
            "release": release,
            "period": period,
            "model_epoch": MODEL_EPOCH,
            "target_epoch": TARGET_EPOCH,
            "training_receipt_sha256": training_receipt["sha256"],
            "point_raw": float(point_raw),
            "method": "empirical_prior_oos_residual_quantiles",
            "residual": "actual_raw_target_minus_raw_ridge_point",
            "quantiles": list(INTERVAL_QUANTILES),
            "interpolation": "numpy_linear",
            "n": len(oos),
            "minimum_required": MIN_INTERVAL_OBS,
            "oos_period_min": oos[0]["period"],
            "oos_period_max": oos[-1]["period"],
            "oos_residuals_sha256": _payload_sha256(oos),
            "residual_quantiles_raw": [float(value) for value in residual_quantiles],
            "bounds_raw": bounds_raw,
            "published_rounding": {
                "point_and_p50": "decimal_round_half_up_1dp",
                "p10_p25": "decimal_round_floor_1dp",
                "p75_p90": "decimal_round_ceiling_1dp",
            },
            "strictly_prior_to_live": True,
        }
    )

    pit_provenance = {
        "schema": "release_cpi_coherent_pit_provenance.v1",
        "decision_cutoff": decision_asof.isoformat(),
        "decision_cutoff_rule": "release_date_minus_1_calendar_day",
        "training_label_release_date_operator": "<=",
        "live_release_date_operator": ">",
        "exact_calendar_source_periods": True,
        "candidate_data_asof": history.get("candidate_data_asof"),
        "evidence_available_at": truth_receipt["completion"]["evidence_available_at"],
        "feature_receipts": live_feature_provenance,
        "vintaged_legs": [
            name for name in feature_order if name != "gasoline_mom"
        ],
        "unrevised_legs": ["gasoline_mom"] if release == "cpi_headline" else [],
        "revision_optimistic_legs": [],
        "absent_legs": [],
        "display_only": True,
        "authority": False,
    }

    result = {
        "schema": SCHEMA,
        "status": "shadow_candidate",
        "release": release,
        "period": period,
        "release_date": live_release_date.isoformat(),
        "asof": decision_asof.isoformat(),
        "model": MODEL_ID,
        "model_epoch": MODEL_EPOCH,
        "target_epoch": TARGET_EPOCH,
        "point": _round_half_up_1dp(point_raw),
        "point_raw": float(point_raw),
        "p10": bounds[0],
        "p25": bounds[1],
        "p50": bounds[2],
        "p75": bounds[3],
        "p90": bounds[4],
        # No confidence transform was preregistered.  Presence with null is more
        # honest than inventing an empirical score after seeing residuals.
        "confidence": None,
        "input_completeness": 1.0,
        "inputs_hash": inputs_hash,
        "input_manifest": input_manifest,
        "model_receipt": model_receipt,
        "truth_receipt": truth_receipt,
        "training_receipt": training_receipt,
        "interval_receipt": interval_receipt,
        "pit_provenance": pit_provenance,
        "display_only": True,
        "authority": False,
        "promotion_authorized": False,
    }
    if not all(
        verify_sealed_receipt(result[key])
        for key in (
            "input_manifest",
            "model_receipt",
            "truth_receipt",
            "training_receipt",
            "interval_receipt",
        )
    ):
        raise CoherentShadowContractError("internal receipt sealing failed")
    if inputs_hash != input_manifest["sha256"]:
        raise CoherentShadowContractError("inputs_hash does not bind the exact input manifest")
    return result


__all__ = [
    "CoherentShadowContractError",
    "FEATURE_ORDER",
    "MIN_INTERVAL_OBS",
    "MIN_TRAIN_OBS",
    "MissingFeatureError",
    "project_cpi_coherent_shadow",
    "verify_sealed_receipt",
]
