from __future__ import annotations

import json
from pathlib import Path
from dataclasses import replace

import pytest

from scripts.research.temporal_scale.contracts import (
    ArtifactAttackResult,
    ArtifactTest,
    BarReceipt,
    ChartRecipe,
    ContractError,
    EXPORT_PRECISION_INSUFFICIENT,
    KernelSignature,
    REQUIRED_EXPORT_COLUMNS,
    strict_json_dumps,
)


def complete_recipe_dict() -> dict:
    return {
        "schema_version": "mastermind.temporal_chart_recipe.v1",
        "recipe_id": "wmt-720-extended-fixture",
        "captured_at": "2026-09-03T06:00:00Z",
        "capture_status": "complete",
        "observer": "fixture",
        "instrument": {
            "display_symbol": "WMT",
            "tickerid": "NYSE:WMT",
            "main_tickerid": "NYSE:WMT",
            "asset_class": "equity",
            "exchange": "NYSE",
            "vendor_feed": "fixture",
            "currency": "USD",
            "contract_month": None,
            "continuous_symbol": None,
            "roll_recipe": None,
            "settlement_basis": None,
        },
        "chart": {
            "timeframe_period": "720",
            "named_session": "extended",
            "exchange_timezone": "America/New_York",
            "chart_timezone": "America/New_York",
            "extended_hours_enabled": True,
            "price_adjustment": "split_adjusted",
            "dividend_adjustment": "off",
            "back_adjustment": "not_applicable",
            "settlement_as_close": "not_applicable",
            "allowed_session_variants": ["extended", "regular"],
            "chart_is_standard": True,
            "chart_is_heikinashi": False,
            "chart_is_renko": False,
            "chart_is_linebreak": False,
            "chart_is_kagi": False,
            "chart_is_pnf": False,
            "chart_is_range": False,
        },
        "indicator": {
            "observed_indicator_family": "owner_rsi_macd_stochrsi",
            "observed_indicator_title": "Owner RSI-MACD/StochRSI",
            "observed_indicator_source_kind": "repository_exact",
            "observed_indicator_source_hash": "1" * 40,
            "observed_indicator_inputs": {
                "rsi_len": 14, "macd_fast": 14, "macd_slow": 60, "macd_signal": 5,
                "stoch_len": 14, "smooth_k": 3, "smooth_d": 3,
            },
            "probe_indicator_family": "owner_rsi_macd_stochrsi",
            "probe_source_git_blob_sha": "1" * 40,
            "probe_inputs": {
                "rsi_len": 14, "macd_fast": 14, "macd_slow": 60, "macd_signal": 5,
                "stoch_len": 14, "smooth_k": 3, "smooth_d": 3,
            },
            "probe_ema_adjust": False,
            "probe_rma_seed": "sma_seeded",
            "observed_equals_probe": True,
        },
        "export": {
            "csv_filename": "wmt.csv",
            "csv_sha256": "2" * 64,
            "row_count": 3,
            "first_bar_open_ms": 1_700_000_000_000,
            "last_bar_close_ms": 1_700_100_000_000,
            "loaded_history_start_ms": 1_690_000_000_000,
        },
        "rights": {
            "use": "local_research_only",
            "redistribution": "blocked",
            "source_reference": "fixture",
        },
        "missing_fields": [],
    }


def complete_result_dict() -> dict:
    return {
        "schema_version": "mastermind.temporal_artifact_attack.v1",
        "operation_key": "temporal-grain-gakd-artifact-attack-r1-20260903-sol-001",
        "recipes": ["wmt-720-extended-fixture"],
        "frozen_grid_hash": "a" * 64,
        "trial_family": "temporal_grain_gakd_r1",
        "tests": full_axis_tests(),
        "parity": {"status": "PASS"},
        "mechanical_status": "MECHANICALLY_SURVIVES",
        "final_mechanism_classification": None,
        "mechanical_receipts": ["grid-receipt"],
        "observed_indicator_reproduction": {"status": "PASS"},
        "observed_indicator_reproduction_receipts": ["observed-receipt"],
        "owner_probe_control": {"status": "PASS"},
        "owner_probe_control_receipts": ["probe-receipt"],
        "authority": {
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "may_trade": False,
            "may_modify_prophet": False,
        },
    }


def amended_complete_recipe_dict() -> dict:
    raw = complete_recipe_dict()
    raw["chart"].update(
        {
            "chart_is_standard": True,
            "chart_is_heikinashi": False,
            "chart_is_renko": False,
            "chart_is_linebreak": False,
            "chart_is_kagi": False,
            "chart_is_pnf": False,
            "chart_is_range": False,
        }
    )
    raw["indicator"] = {
        "observed_indicator_family": "owner_rsi_macd_stochrsi",
        "observed_indicator_title": "Owner RSI-MACD/StochRSI",
        "observed_indicator_source_kind": "repository_exact",
        "observed_indicator_source_hash": "1" * 40,
        "observed_indicator_inputs": {
            "rsi_len": 14, "macd_fast": 14, "macd_slow": 60, "macd_signal": 5,
            "stoch_len": 14, "smooth_k": 3, "smooth_d": 3,
        },
        "probe_indicator_family": "owner_rsi_macd_stochrsi",
        "probe_source_git_blob_sha": "1" * 40,
        "probe_inputs": {
            "rsi_len": 14, "macd_fast": 14, "macd_slow": 60, "macd_signal": 5,
            "stoch_len": 14, "smooth_k": 3, "smooth_d": 3,
        },
        "probe_ema_adjust": False,
        "probe_rma_seed": "sma_seeded",
        "observed_equals_probe": True,
    }
    return raw


def amended_complete_result_dict() -> dict:
    raw = complete_result_dict()
    raw["observed_indicator_reproduction"] = {"status": "PASS"}
    raw["observed_indicator_reproduction_receipts"] = ["observed-receipt"]
    raw["owner_probe_control"] = {"status": "PASS"}
    raw["owner_probe_control_receipts"] = ["probe-receipt"]
    return raw


def complete_bar_dict() -> dict:
    return {
        "schema_version": "mastermind.temporal_bar_receipt.v1",
        "recipe_id": "recipe",
        "bar_index": 0,
        "open_ms": 0,
        "close_ms": 3_600_000,
        "nominal_minutes": 60,
        "effective_minutes": 60,
        "traded_minutes": 60,
        "volume": 1.0,
        "trade_count": 1,
        "realized_variance": 0.1,
        "session_flags": {
            "premarket": False, "market": True, "postmarket": False,
            "first_session_bar": False, "last_session_bar": False,
            "first_regular_bar": False, "last_regular_bar": False,
        },
        "clipped": False,
        "confirmed": True,
        "empty_interval": False,
        "known_at_ms": 3_600_000,
        "source_row_sha256": "b" * 64,
    }


def complete_kernel_dict() -> dict:
    return {
        "schema_version": "mastermind.temporal_kernel_signature.v1",
        "indicator_spec_hash": "c" * 64,
        "input_series": "close",
        "components": [{"name": "rsi"}],
        "bar_memory": {"rma14_half_life_bars": 9.3},
        "clock_basis": "bar_count",
        "clock_parameter": {},
        "warmup_first_finite_index": {"rsi": 14},
        "linear_diagnostics": {},
        "nonlinear_caveat": "nonlinear",
    }


def complete_artifact_test_dict() -> dict:
    return {
        "test_id": "g", "axis": "G", "variant_id": "exact", "input_hash": "d" * 64,
        "status": "PASS", "metrics": {"count": 1}, "findings": [],
    }


def full_axis_tests() -> list[dict]:
    return [
        {**complete_artifact_test_dict(), "test_id": axis.lower(), "axis": axis,
         "status": "UNAVAILABLE" if axis == "D" else "PASS"}
        for axis in ("G", "A", "K", "D", "PARITY", "TRUNCATION")
    ]


def test_complete_recipe_requires_explicit_chart_type_and_indicator_provenance() -> None:
    assert ChartRecipe.from_dict(amended_complete_recipe_dict()).to_dict() == amended_complete_recipe_dict()


def test_chart_type_cannot_silently_normalize_nonstandard_or_incoherent_bars() -> None:
    raw = amended_complete_recipe_dict()
    raw["chart"]["chart_is_heikinashi"] = True
    with pytest.raises(ContractError, match="chart.type_coherence"):
        ChartRecipe.from_dict(raw)


def test_unknown_chart_type_is_only_lawful_as_named_incomplete_provenance() -> None:
    raw = amended_complete_recipe_dict()
    raw["capture_status"] = "incomplete"
    raw["chart"]["chart_is_standard"] = None
    raw["missing_fields"] = ["chart.chart_is_standard", "chart.type_coherence"]
    assert ChartRecipe.from_dict(raw).capture_status == "incomplete"


@pytest.mark.parametrize("field, value", [("observed_indicator_source_hash", "2" * 40), ("observed_indicator_inputs", {"rsi_len": 7})])
def test_observed_equals_probe_requires_exact_source_hash_and_inputs(
    field: str, value: object,
) -> None:
    raw = amended_complete_recipe_dict()
    raw["indicator"]["observed_indicator_title"] = "Owner RSI-MACD/StochRSI"
    raw["indicator"][field] = value
    with pytest.raises(ContractError, match="observed_equals_probe"):
        ChartRecipe.from_dict(raw)


def test_invite_only_indicator_cannot_be_completed_by_attaching_owner_probe() -> None:
    raw = amended_complete_recipe_dict()
    raw["indicator"]["observed_indicator_source_kind"] = "invite_only"
    with pytest.raises(ContractError, match="observed_indicator_source_kind"):
        ChartRecipe.from_dict(raw)
    raw["capture_status"] = "incomplete"
    raw["indicator"]["observed_indicator_source_hash"] = None
    raw["indicator"]["observed_indicator_inputs"] = None
    raw["indicator"]["observed_equals_probe"] = "unknown"
    raw["missing_fields"] = [
        "indicator.observed_indicator_source_hash",
        "indicator.observed_indicator_inputs",
    ]
    assert ChartRecipe.from_dict(raw).capture_status == "incomplete"


def test_w1a_result_requires_separate_observed_and_owner_control_channels() -> None:
    assert ArtifactAttackResult.from_dict(amended_complete_result_dict()).to_dict() == amended_complete_result_dict()


def test_result_indicator_channels_reject_untyped_statuses() -> None:
    raw = amended_complete_result_dict()
    raw["observed_indicator_reproduction"] = {"status": "OWNER_PROBE_SUBSTITUTION"}
    with pytest.raises(ContractError, match="observed_indicator_reproduction.status"):
        ArtifactAttackResult.from_dict(raw)


@pytest.mark.parametrize(
    ("mutator", "expected_status"),
    [
        (lambda raw: raw["parity"].update(status="UNRESOLVED_DATA"), "UNRESOLVED_DATA"),
        (lambda raw: raw["observed_indicator_reproduction"].update(status="UNRESOLVED_DATA"), "UNRESOLVED_DATA"),
        (lambda raw: raw["owner_probe_control"].update(status="FAIL"), "ARTIFACT"),
        (lambda raw: raw["tests"].append({**complete_artifact_test_dict(), "status": "UNAVAILABLE"}), "UNRESOLVED_DATA"),
        (lambda raw: raw["tests"].append({**complete_artifact_test_dict(), "status": "FAIL"}), "ARTIFACT"),
        (lambda raw: raw["tests"].append({**complete_artifact_test_dict(), "findings": ["single_arbitrary_phase_only"]}), "ARTIFACT"),
    ],
)
def test_result_rejects_survival_when_carrier_priority_requires_another_status(
    mutator, expected_status: str,
) -> None:
    raw = complete_result_dict()
    mutator(raw)
    with pytest.raises(ContractError, match=expected_status):
        ArtifactAttackResult.from_dict(raw)


def test_d_unavailability_does_not_block_mechanical_survival() -> None:
    raw = complete_result_dict()
    raw["tests"] = full_axis_tests()
    assert ArtifactAttackResult.from_dict(raw).mechanical_status == "MECHANICALLY_SURVIVES"


def test_required_k_unavailability_is_unresolved_before_mechanical_survival() -> None:
    """K is required, while explicit D coverage may remain unavailable."""
    raw = complete_result_dict()
    raw["tests"] = [
        {**complete_artifact_test_dict(), "test_id": "g", "axis": "G", "status": "PASS"},
        {**complete_artifact_test_dict(), "test_id": "a", "axis": "A", "status": "PASS"},
        {**complete_artifact_test_dict(), "test_id": "k", "axis": "K", "status": "UNAVAILABLE"},
        {**complete_artifact_test_dict(), "test_id": "d", "axis": "D", "status": "UNAVAILABLE"},
        {**complete_artifact_test_dict(), "test_id": "parity", "axis": "PARITY", "status": "PASS"},
        {**complete_artifact_test_dict(), "test_id": "truncation", "axis": "TRUNCATION", "status": "PASS"},
    ]
    with pytest.raises(ContractError, match="mechanical_status must be UNRESOLVED_DATA"):
        ArtifactAttackResult.from_dict(raw)
    raw["mechanical_status"] = "UNRESOLVED_DATA"
    assert ArtifactAttackResult.from_dict(raw).mechanical_status == "UNRESOLVED_DATA"


def test_survival_requires_all_six_axis_coverage_and_receipted_evidence_channels() -> None:
    raw = complete_result_dict()
    raw["tests"] = []
    with pytest.raises(ContractError, match="coverage"):
        ArtifactAttackResult.from_dict(raw)
    raw["tests"] = full_axis_tests()
    raw["recipes"] = []
    with pytest.raises(ContractError, match="recipes"):
        ArtifactAttackResult.from_dict(raw)
    raw = complete_result_dict()
    raw["tests"] = full_axis_tests()
    raw["mechanical_receipts"] = []
    with pytest.raises(ContractError, match="mechanical_receipts"):
        ArtifactAttackResult.from_dict(raw)
    raw = complete_result_dict()
    raw["tests"] = full_axis_tests()
    raw["observed_indicator_reproduction_receipts"] = []
    with pytest.raises(ContractError, match="observed_indicator_reproduction_receipts"):
        ArtifactAttackResult.from_dict(raw)
    raw = complete_result_dict()
    raw["tests"] = full_axis_tests()
    raw["owner_probe_control_receipts"] = []
    with pytest.raises(ContractError, match="owner_probe_control_receipts"):
        ArtifactAttackResult.from_dict(raw)


def test_early_unresolved_result_does_not_require_full_axis_grid() -> None:
    raw = complete_result_dict()
    raw["mechanical_status"] = "UNRESOLVED_DATA"
    raw["parity"] = {"status": "UNRESOLVED_DATA"}
    raw["observed_indicator_reproduction"] = {"status": "UNRESOLVED_DATA"}
    raw["owner_probe_control"] = {"status": "UNRESOLVED_DATA"}
    raw["tests"] = []
    assert ArtifactAttackResult.from_dict(raw).mechanical_status == "UNRESOLVED_DATA"


def test_direct_constructors_validate_and_deep_freeze_all_five_records() -> None:
    recipe = ChartRecipe(**complete_recipe_dict())
    bar = BarReceipt(**complete_bar_dict())
    kernel = KernelSignature(**complete_kernel_dict())
    artifact_test = ArtifactTest(**complete_artifact_test_dict())
    result_raw = complete_result_dict()
    result_raw["tests"] = tuple(ArtifactTest.from_dict(item) for item in result_raw["tests"])
    result = ArtifactAttackResult(**result_raw)
    for mapping, key in (
        (recipe.instrument, "tickerid"), (bar.session_flags, "market"),
        (kernel.bar_memory, "rma14_half_life_bars"), (artifact_test.metrics, "count"),
        (result.parity, "status"),
    ):
        with pytest.raises(TypeError):
            mapping[key] = None
    with pytest.raises(ContractError):
        replace(recipe, schema_version="wrong")
    with pytest.raises(ContractError):
        replace(bar, schema_version="wrong")
    with pytest.raises(ContractError):
        replace(kernel, schema_version="wrong")
    with pytest.raises(ContractError):
        replace(artifact_test, test_id="")
    with pytest.raises(ContractError):
        replace(result, schema_version="wrong")


def test_complete_recipe_rejects_empty_probe_inputs_and_invalid_scalars_enums() -> None:
    raw = complete_recipe_dict()
    raw["indicator"]["probe_inputs"] = {}
    with pytest.raises(ContractError, match="probe_inputs"):
        ChartRecipe.from_dict(raw)
    raw = complete_recipe_dict()
    raw["chart"]["price_adjustment"] = "banana"
    with pytest.raises(ContractError, match="price_adjustment"):
        ChartRecipe.from_dict(raw)
    raw = complete_recipe_dict()
    raw["indicator"]["probe_rma_seed"] = "mystery_seed"
    with pytest.raises(ContractError, match="probe_rma_seed"):
        ChartRecipe.from_dict(raw)
    raw = complete_recipe_dict()
    raw["instrument"]["vendor_feed"] = 17
    with pytest.raises(ContractError, match="vendor_feed"):
        ChartRecipe.from_dict(raw)


def test_incomplete_futures_must_name_the_concrete_or_roll_identity_gap() -> None:
    raw = complete_recipe_dict()
    raw["capture_status"] = "incomplete"
    raw["instrument"].update(asset_class="futures", contract_month=None)
    raw["missing_fields"] = []
    with pytest.raises(ContractError, match="instrument.contract_month"):
        ChartRecipe.from_dict(raw)
    raw = complete_recipe_dict()
    raw["capture_status"] = "incomplete"
    raw["instrument"].update(asset_class="futures", tickerid="COMEX:SI1!", main_tickerid="COMEX:SI1!", continuous_symbol="SI1!", roll_recipe=None)
    raw["missing_fields"] = []
    with pytest.raises(ContractError, match="instrument.roll_recipe"):
        ChartRecipe.from_dict(raw)


def test_indicator_channels_are_status_only_strict_json_mappings() -> None:
    raw = complete_result_dict()
    raw["observed_indicator_reproduction"] = {"status": "PASS", "freeform_success": "no"}
    with pytest.raises(ContractError, match="observed_indicator_reproduction"):
        ArtifactAttackResult.from_dict(raw)


def test_all_contract_scalars_sequences_and_json_keys_refuse_implicit_coercion() -> None:
    recipe = ChartRecipe.from_dict(complete_recipe_dict())
    with pytest.raises(ContractError, match="recipe_id"):
        replace(recipe, recipe_id=7)
    with pytest.raises(ContractError, match="observer"):
        replace(recipe, observer={})
    with pytest.raises(ContractError, match="captured_at"):
        replace(recipe, captured_at="2026-09-03T06:00:00")
    raw = complete_recipe_dict()
    raw["instrument"]["contract_month"] = "202613"
    with pytest.raises(ContractError, match="contract_month"):
        ChartRecipe.from_dict(raw)
    bar = BarReceipt.from_dict(complete_bar_dict())
    with pytest.raises(ContractError, match="recipe_id"):
        replace(bar, recipe_id=0)
    kernel = KernelSignature.from_dict(complete_kernel_dict())
    with pytest.raises(ContractError, match="input_series"):
        replace(kernel, input_series=[])
    with pytest.raises(ContractError, match="bar_memory"):
        replace(kernel, bar_memory={"rma14_half_life_bars": True})
    artifact_test = ArtifactTest.from_dict(complete_artifact_test_dict())
    with pytest.raises(ContractError, match="test_id"):
        replace(artifact_test, test_id=1)
    with pytest.raises(ContractError, match="findings"):
        replace(artifact_test, findings="not-a-sequence")
    result = ArtifactAttackResult.from_dict({**complete_result_dict(), "tests": full_axis_tests()})
    with pytest.raises(ContractError, match="operation_key"):
        replace(result, operation_key=1)
    with pytest.raises(ContractError, match="recipes"):
        replace(result, recipes="recipe")
    raw_artifact_test = complete_artifact_test_dict()
    raw_artifact_test["metrics"] = {1: "bad-key"}
    with pytest.raises(ContractError, match="keys"):
        ArtifactTest.from_dict(raw_artifact_test)
    raw = complete_result_dict()
    raw["owner_probe_control"] = {"status": "PASS", "payload": object()}
    with pytest.raises(ContractError, match="owner_probe_control"):
        ArtifactAttackResult.from_dict(raw)


@pytest.mark.parametrize("missing_fields", ["", b"", {"chart.named_session": "missing"}])
def test_chart_recipe_direct_constructor_rejects_nonsequence_missing_fields(missing_fields: object) -> None:
    """A direct constructor must not turn a string, bytes, or mapping into a tuple."""
    recipe = ChartRecipe.from_dict(complete_recipe_dict())
    with pytest.raises(ContractError, match="missing_fields must be a non-string sequence"):
        replace(recipe, missing_fields=missing_fields)


def test_chart_recipe_direct_constructor_normalizes_malformed_utc_time_to_contract_error() -> None:
    """A date with a Z suffix is not a UTC-aware ISO-8601 datetime."""
    recipe = ChartRecipe.from_dict(complete_recipe_dict())
    with pytest.raises(ContractError, match="captured_at must be ISO-8601 UTC ending in Z"):
        replace(recipe, captured_at="2026-09-03Z")


def test_complete_recipe_round_trips_without_defaults(tmp_path: Path) -> None:
    raw = complete_recipe_dict()
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert ChartRecipe.from_json(path).to_dict() == raw


def test_complete_recipe_rejects_an_unnamed_missing_identity_field(tmp_path: Path) -> None:
    raw = complete_recipe_dict()
    raw["instrument"]["tickerid"] = ""
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ContractError, match="instrument.tickerid"):
        ChartRecipe.from_json(path)


def test_incomplete_recipe_requires_each_absent_identity_field_to_be_named(tmp_path: Path) -> None:
    raw = complete_recipe_dict()
    raw["capture_status"] = "incomplete"
    raw["instrument"]["tickerid"] = ""
    raw["missing_fields"] = ["instrument.tickerid"]
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert ChartRecipe.from_json(path).capture_status == "incomplete"


def test_concrete_future_uses_existing_fut_identity_semantics() -> None:
    raw = complete_recipe_dict()
    raw["instrument"].update(
        {
            "display_symbol": "SI",
            "tickerid": "COMEX:SIZ2026",
            "main_tickerid": "COMEX:SIZ2026",
            "asset_class": "futures",
            "exchange": "COMEX",
            "contract_month": "202612",
            "canonical_id": "FUT:XCEC:SI:202612",
        }
    )
    assert ChartRecipe.from_dict(raw).instrument["canonical_id"] == "FUT:XCEC:SI:202612"


def test_continuous_silver_requires_roll_and_explicit_feed_session(tmp_path: Path) -> None:
    raw = complete_recipe_dict()
    raw["instrument"].update(
        {
            "display_symbol": "SI",
            "tickerid": "COMEX:SI1!",
            "main_tickerid": "COMEX:SI1!",
            "asset_class": "futures",
            "exchange": "COMEX",
            "continuous_symbol": "SI1!",
            "roll_recipe": None,
        }
    )
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ContractError, match="roll_recipe"):
        ChartRecipe.from_json(path)


@pytest.mark.parametrize(
    ("display_symbol", "tickerid", "proxy_feed"),
    [
        ("SI", "COMEX:SI1!", "yahoo:SI=F"),
        ("WMT", "NYSE:WMT", "polygon:WMT"),
        ("WMT", "NYSE:WMT", "massive:WMT"),
    ],
)
def test_proxy_identity_cannot_satisfy_a_different_tradingview_recipe(
    display_symbol: str, tickerid: str, proxy_feed: str,
) -> None:
    raw = complete_recipe_dict()
    raw["instrument"]["display_symbol"] = display_symbol
    raw["instrument"]["tickerid"] = tickerid
    raw["instrument"]["main_tickerid"] = tickerid
    raw["instrument"]["vendor_feed"] = proxy_feed
    with pytest.raises(ContractError, match="vendor_feed"):
        ChartRecipe.from_dict(raw)


def test_recipe_rights_use_and_redistribution_are_closed_enums() -> None:
    raw = complete_recipe_dict()
    raw["rights"]["use"] = "research_only"
    with pytest.raises(ContractError, match="rights.use"):
        ChartRecipe.from_dict(raw)
    raw = complete_recipe_dict()
    raw["rights"]["redistribution"] = "maybe"
    with pytest.raises(ContractError, match="rights.redistribution"):
        ChartRecipe.from_dict(raw)


def test_bar_receipt_rejects_inconsistent_duration_and_empty_activity() -> None:
    raw = {
        "schema_version": "mastermind.temporal_bar_receipt.v1",
        "recipe_id": "recipe",
        "bar_index": 0,
        "open_ms": 0,
        "close_ms": 3_600_000,
        "nominal_minutes": 60,
        "effective_minutes": 59,
        "traded_minutes": None,
        "volume": None,
        "trade_count": None,
        "realized_variance": None,
        "session_flags": {
            "premarket": False,
            "market": True,
            "postmarket": False,
            "first_session_bar": False,
            "last_session_bar": False,
            "first_regular_bar": False,
            "last_regular_bar": False,
        },
        "clipped": False,
        "confirmed": True,
        "empty_interval": False,
        "known_at_ms": 3_600_000,
        "source_row_sha256": "b" * 64,
    }
    with pytest.raises(ContractError, match="effective_minutes"):
        BarReceipt.from_dict(raw)
    raw["effective_minutes"] = 60
    raw["empty_interval"] = True
    raw["volume"] = 0.0
    with pytest.raises(ContractError, match="empty_interval"):
        BarReceipt.from_dict(raw)


def test_kernel_and_artifact_test_reject_bad_hashes_and_nonfinite_values() -> None:
    kernel = {
        "schema_version": "mastermind.temporal_kernel_signature.v1",
        "indicator_spec_hash": "not-a-hash",
        "input_series": "close",
        "components": [],
        "bar_memory": {"rma14_half_life_bars": float("inf")},
        "clock_basis": "bar_count",
        "clock_parameter": {},
        "warmup_first_finite_index": {},
        "linear_diagnostics": {},
        "nonlinear_caveat": "nonlinear",
    }
    with pytest.raises(ContractError, match="finite"):
        KernelSignature.from_dict(kernel)
    kernel["bar_memory"] = {"rma14_half_life_bars": 9.3}
    with pytest.raises(ContractError, match="indicator_spec_hash"):
        KernelSignature.from_dict(kernel)
    artifact_test = {
        "test_id": "parity",
        "axis": "PARITY",
        "variant_id": "exact",
        "input_hash": "c" * 64,
        "status": "PASS",
        "metrics": {"error": float("nan")},
        "findings": [],
    }
    with pytest.raises(ContractError, match="finite"):
        ArtifactTest.from_dict(artifact_test)


def test_strict_json_rejects_nonfinite_values() -> None:
    with pytest.raises(ContractError, match="finite"):
        strict_json_dumps({"bad": float("nan")})


def test_result_rejects_authority_escalation_even_when_status_survives() -> None:
    raw = complete_result_dict()
    raw["authority"]["may_rank"] = True
    with pytest.raises(ContractError, match="authority"):
        ArtifactAttackResult.from_dict(raw)


def test_result_rejects_a_mechanism_conclusion_under_zero_authority() -> None:
    raw = complete_result_dict()
    raw["final_mechanism_classification"] = "FILTER_MEMORY"
    with pytest.raises(ContractError, match="final_mechanism_classification"):
        ArtifactAttackResult.from_dict(raw)


def test_w1a_result_uses_only_mechanical_statuses() -> None:
    raw = complete_result_dict()
    raw["mechanical_status"] = "FILTER_MEMORY"
    with pytest.raises(ContractError, match="mechanical_status"):
        ArtifactAttackResult.from_dict(raw)


def test_task_three_export_contract_vocabulary_is_frozen() -> None:
    assert {
        "TG_time_tradingday_ms",
        "TG_open",
        "TG_high",
        "TG_low",
        "TG_close",
        "TG_volume",
    }.issubset(REQUIRED_EXPORT_COLUMNS)
    assert EXPORT_PRECISION_INSUFFICIENT == "INSUFFICIENT_EXPORT_PRECISION"
