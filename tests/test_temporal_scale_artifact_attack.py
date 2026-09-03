from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.research.temporal_scale import artifact_attack
from scripts.research.temporal_scale.artifact_attack import (
    ArtifactAttackError,
    ArtifactGrid,
    classify_artifact_attack,
    classify_mechanical_status,
    default_artifact_grid,
    register_artifact_grid,
    run_artifact_attack,
)
from scripts.research.temporal_scale.chart_export import load_chart_export
from scripts.research.temporal_scale.contracts import ArtifactTest, ChartRecipe, LowerGrainRecipe, strict_json_dumps


def recipe() -> dict:
    return {
        "chart": {
            "timeframe_period": "720",
            "named_session": "extended",
            "allowed_session_variants": ["regular", "extended", "regular"],
        }
    }


def _test(axis: str, status: str, *findings: str) -> ArtifactTest:
    return ArtifactTest(
        test_id=f"{axis.lower()}-{status.lower()}",
        axis=axis,
        variant_id=f"{axis.lower()}-variant",
        input_hash="1" * 64,
        status=status,
        metrics={"threshold": 1.0},
        findings=findings or (f"{axis}_{status}",),
    )


def _required(status: str = "PASS") -> tuple[ArtifactTest, ...]:
    return tuple(_test(axis, status) for axis in ("G", "A", "K", "PARITY", "TRUNCATION"))


def _loaded(tmp_path: Path, *, n: int = 1190):
    tmp_path.mkdir(parents=True, exist_ok=True)
    helpers = runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_parity.py")))
    return helpers["loaded_export_from_canonical_fixture"](tmp_path, n=n)


def test_grid_is_frozen_for_720() -> None:
    grid = default_artifact_grid(recipe())
    assert grid.human_chart_grains_minutes == (360, 480, 720, 960, 1440)
    assert grid.memory_matched_grains_minutes == (360, 480, 720, 960, 1440)
    assert grid.anchor_phase_fractions == (0.0, .25, .5, .75)
    assert grid.session_variants == ("extended", "regular")
    assert grid.implementation_controls == ("owner_rsi_macd_stochrsi", "standard_price_macd_12_26_9")
    assert grid.data_plane_controls == ("exact_recipe_plane",)
    assert len(grid.sha256()) == 64
    reordered = ArtifactGrid(
        human_chart_grains_minutes=(1440, 720, 360, 960, 480),
        memory_matched_grains_minutes=(960, 360, 1440, 480, 720),
        anchor_phase_fractions=(0.75, 0.0, 0.5, 0.25),
        session_variants=("regular", "extended"),
        implementation_controls=("standard_price_macd_12_26_9", "owner_rsi_macd_stochrsi"),
        data_plane_controls=("exact_recipe_plane",),
    )
    assert reordered.to_dict() == grid.to_dict()
    assert reordered.sha256() == grid.sha256()


def test_noninteger_ratio_grains_are_omitted_not_rounded() -> None:
    raw = recipe()
    raw["chart"]["timeframe_period"] = "7"
    grid = default_artifact_grid(raw)
    assert grid.human_chart_grains_minutes == (7, 14)


def test_classification_required_k_unavailable_wins() -> None:
    tests = (*_required(), _test("K", "UNAVAILABLE"))
    assert classify_mechanical_status(True, "PASS", tests) == "UNRESOLVED_DATA"
    assert classify_mechanical_status(False, "PASS", _required()) == "UNRESOLVED_DATA"


def test_classification_priority_and_arbitrary_phase_token_are_exact() -> None:
    assert classify_mechanical_status(True, "FAIL", _required()) == "ARTIFACT"
    assert classify_mechanical_status(True, "PASS", (*_required(), _test("A", "PASS", "single_arbitrary_phase_only"))) == "ARTIFACT"
    assert classify_mechanical_status(True, "PASS", _required()) == "MECHANICALLY_SURVIVES"
    assert classify_artifact_attack(True, "PASS", _required()) == "MECHANICALLY_SURVIVES"
    with pytest.raises(ArtifactAttackError):
        classify_mechanical_status(True, "MAYBE", _required())


def test_default_ledger_refused(tmp_path: Path) -> None:
    with pytest.raises(ArtifactAttackError):
        register_artifact_grid(default_artifact_grid(recipe()), ledger_path=Path("data/trial_ledger.jsonl"), info_cutoff="x")


def test_registration_persists_every_axis_before_diagnostics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    grid = default_artifact_grid(recipe())
    ledger_path = tmp_path / "trial-ledger.jsonl"
    count = register_artifact_grid(grid, ledger_path=ledger_path, info_cutoff="2026-09-03T06:00:00Z")
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert count == len(rows) > 0
    assert {row["config"]["axis"] for row in rows} == {"G", "A", "K", "D", "PARITY", "TRUNCATION"}
    assert {row["info_cutoff"] for row in rows} == {"2026-09-03T06:00:00Z"}
    assert all(row["config"]["grid_hash"] == grid.sha256() for row in rows)
    registered = {(row["config"]["axis"], row["config"]["variant"]) for row in rows}
    assert ("D", "chart_price_construction") in registered
    assert ("A", "phase_uniqueness") in registered
    assert ("K", "standard_price_macd_12_26_9") in registered

    loaded = _loaded(tmp_path / "loaded")
    calls: list[str] = []
    monkeypatch.setattr(artifact_attack, "register_artifact_grid", lambda *args, **kwargs: calls.append("register") or len(rows))

    def diagnostics(*args, **kwargs):
        calls.append("diagnostics")
        parity = {"status": "PASS", "tolerance": 1e-10, "first_comparable_bar_ms": 1, "compared_rows": 1, "max_abs_error": {}, "failures": []}
        return parity, (*_required(), _test("D", "PASS"))

    monkeypatch.setattr(artifact_attack, "_run_diagnostics", diagnostics)
    result = run_artifact_attack(loaded, lower_grain_rows=None, grid=grid, ledger_path=tmp_path / "ordered.jsonl")
    assert calls == ["register", "diagnostics"]
    assert result.mechanical_status == "MECHANICALLY_SURVIVES"
    assert result.final_mechanism_classification is None
    assert set(result.authority.values()) == {False}


def test_missing_lower_grain_evidence_yields_typed_unresolved_not_proxy(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path)
    result = run_artifact_attack(
        loaded,
        lower_grain_rows=None,
        grid=default_artifact_grid(loaded.recipe),
        ledger_path=tmp_path / "ledger.jsonl",
    )
    assert result.mechanical_status == "UNRESOLVED_DATA"
    assert {test.axis for test in result.tests} >= {"G", "A", "K", "D", "PARITY", "TRUNCATION"}
    assert any(test.axis == "K" and test.status == "UNAVAILABLE" for test in result.tests)
    assert result.owner_probe_control["status"] == "PASS"
    assert result.observed_indicator_reproduction["status"] == "PASS"
    assert all(len(item) == 64 for item in result.mechanical_receipts)
    ledger_rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    registered = {(row["config"]["axis"], row["config"]["variant"]) for row in ledger_rows}
    assert {(test.axis, test.variant_id) for test in result.tests}.issubset(registered)
    assert any(test.axis == "K" and test.variant_id == "standard_price_macd_12_26_9" and test.status == "PASS" for test in result.tests)


def test_warmup_only_attack_is_parity_unavailable_and_unresolved(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path, n=3)
    result = run_artifact_attack(
        loaded,
        lower_grain_rows=None,
        grid=default_artifact_grid(loaded.recipe),
        ledger_path=tmp_path / "ledger.jsonl",
    )
    assert result.parity["status"] == "UNRESOLVED_DATA"
    parity_tests = [test for test in result.tests if test.axis == "PARITY"]
    assert len(parity_tests) == 1
    assert parity_tests[0].status == "UNAVAILABLE"
    assert "PARITY_NO_COMPARABLE_ROWS" in parity_tests[0].findings
    assert result.mechanical_status == "UNRESOLVED_DATA"


def test_naked_lower_rows_cannot_activate_primary_gak(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path)
    lower = pd.DataFrame([
        {"open_ms": 1_700_000_000_000, "close_ms": 1_700_003_600_000,
         "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0},
    ])
    result = run_artifact_attack(
        loaded, lower_grain_rows=lower, grid=default_artifact_grid(loaded.recipe),
        ledger_path=tmp_path / "ledger.jsonl",
    )
    primary = [test for test in result.tests if test.axis in {"G", "A"} or (test.axis == "K" and test.variant_id.startswith("memory_target"))]
    assert primary and all(test.status == "UNAVAILABLE" for test in primary)
    assert all("LOWER_GRAIN_MANIFEST_UNAVAILABLE" in test.findings for test in primary)


def test_matching_lower_manifest_crosses_gate_before_reconstruction(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path, n=320)
    lower_records: list[dict[str, float | int]] = []
    for row in loaded.frame.itertuples(index=False):
        step = (int(row.TG_time_close_ms) - int(row.TG_time_open_ms)) // 4
        for part in range(4):
            fraction_left = part / 4
            fraction_right = (part + 1) / 4
            open_value = float(row.TG_open) + (float(row.TG_close) - float(row.TG_open)) * fraction_left
            close_value = float(row.TG_open) + (float(row.TG_close) - float(row.TG_open)) * fraction_right
            lower_records.append({
                "open_ms": int(row.TG_time_open_ms) + part * step,
                "close_ms": int(row.TG_time_open_ms) + (part + 1) * step,
                "open": open_value,
                "high": float(row.TG_high),
                "low": float(row.TG_low),
                "close": close_value,
                "volume": float(row.TG_volume) / 4,
            })
    lower = pd.DataFrame(lower_records)
    lower_hash = "5" * 64
    helpers = runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_contracts.py")))
    manifest = helpers["lower_recipe_dict"](loaded.recipe.to_dict(), lower_hash)
    manifest.update(
        row_count=len(lower),
        first_open_ms=int(lower["open_ms"].iloc[0]),
        last_close_ms=int(lower["close_ms"].iloc[-1]),
        source_timeframe_minutes=15,
    )
    result = run_artifact_attack(
        loaded,
        lower_grain_rows=lower,
        lower_grain_recipe=LowerGrainRecipe.from_dict(manifest),
        lower_grain_csv_sha256=lower_hash,
        grid=default_artifact_grid(loaded.recipe),
        ledger_path=tmp_path / "ledger.jsonl",
    )
    primary = [
        test for test in result.tests
        if test.axis in {"G", "A"} or (test.axis == "K" and test.variant_id.startswith("memory_target"))
    ]
    assert primary
    assert not any("LOWER_MANIFEST" in finding for test in primary for finding in test.findings)


@pytest.mark.parametrize(
    ("equality", "source_kind"),
    [
        (False, "repository_exact"),
        ("unknown", "repository_exact"),
        (False, "invite_only"),
        (False, "closed_source"),
        (False, "tradingview_builtin"),
    ],
)
def test_owner_probe_parity_cannot_substitute_for_observed_math(
    tmp_path: Path,
    equality: object,
    source_kind: str,
) -> None:
    _loaded(tmp_path)
    recipe_path = tmp_path / "recipe.json"
    raw = json.loads(recipe_path.read_text(encoding="utf-8"))
    raw["indicator"]["observed_equals_probe"] = equality
    raw["indicator"]["observed_indicator_source_kind"] = source_kind
    recipe_path.write_text(json.dumps(raw), encoding="utf-8")
    loaded = load_chart_export(recipe_path, tmp_path / "synthetic.csv")
    result = run_artifact_attack(
        loaded, lower_grain_rows=None, grid=default_artifact_grid(loaded.recipe),
        ledger_path=tmp_path / "ledger.jsonl",
    )
    assert result.owner_probe_control["status"] == "PASS"
    assert result.observed_indicator_reproduction["status"] == "UNRESOLVED_DATA"
    assert result.mechanical_status == "UNRESOLVED_DATA"


def test_session_intervals_come_only_from_recipe_evidence() -> None:
    helpers = runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_contracts.py")))
    equity_raw = helpers["complete_recipe_dict"]()
    equity_raw["chart"]["named_session"] = "regular"
    equity = ChartRecipe.from_dict(equity_raw)
    equity_intervals, _ = artifact_attack._session_evidence(equity, "regular")
    assert [(item.start_local, item.end_local) for item in equity_intervals] == [("09:30", "16:00")]

    future_raw = helpers["complete_recipe_dict"]()
    future_raw["instrument"].update(
        asset_class="futures", tickerid="COMEX:SIU2026", main_tickerid="COMEX:SI1!",
        exchange="COMEX", contract_month="202609", settlement_basis="exchange_settlement",
        canonical_id="FUT:XCEC:SI:202609",
    )
    future_raw["chart"].update(
        named_session="regular", allowed_session_variants=["regular", "vendor_named"],
        exchange_timezone="America/Chicago", chart_timezone="America/Chicago",
        price_adjustment="raw", settlement_as_close="on",
        session_definitions={
            "regular": {
                "session_literal": "regular", "human_label": "COMEX electronic with break",
                "timezone": "America/Chicago",
                "intervals": [
                    {"start_local": "17:00", "end_local": "16:00", "label": "electronic"},
                ],
                "date_overrides": {},
                "provenance": {"kind": "provider_documented_exact", "receipt_sha256": "7" * 64},
            },
        },
    )
    future = ChartRecipe.from_dict(future_raw)
    future_intervals, _ = artifact_attack._session_evidence(future, "regular")
    assert [(item.start_local, item.end_local) for item in future_intervals] == [("17:00", "16:00")]
    assert artifact_attack._session_evidence(future, "vendor_named") is None


def test_exact_bar_match_requires_interior_coverage_and_volume() -> None:
    observed = pd.DataFrame([
        {"TG_time_open_ms": 0, "TG_time_close_ms": 180_000, "TG_open": 1.0,
         "TG_high": 4.0, "TG_low": 0.5, "TG_close": 3.0, "TG_volume": 6.0},
    ])
    reconstructed = pd.DataFrame([
        {"open_ms": 0, "close_ms": 180_000, "open": 1.0, "high": 4.0,
         "low": 0.5, "close": 3.0, "volume": 6.0},
    ])
    lower = pd.DataFrame([
        {"open_ms": 0, "close_ms": 60_000, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0},
        {"open_ms": 60_000, "close_ms": 120_000, "open": 1.5, "high": 3.0, "low": 1.0, "close": 2.0, "volume": 2.0},
        {"open_ms": 120_000, "close_ms": 180_000, "open": 2.0, "high": 4.0, "low": 1.5, "close": 3.0, "volume": 3.0},
    ])
    assert artifact_attack._exact_bar_match(observed, reconstructed, lower)[0] is True
    assert artifact_attack._exact_bar_match(observed, reconstructed, lower.drop(index=1))[0] is False
    wrong_volume = observed.copy()
    wrong_volume.loc[0, "TG_volume"] = 7.0
    exact, metrics = artifact_attack._exact_bar_match(wrong_volume, reconstructed, lower)
    assert exact is False and metrics["volume_match"] is False


def test_active_named_session_is_always_in_frozen_grid() -> None:
    raw = recipe()
    raw["chart"]["allowed_session_variants"] = ["regular"]
    assert default_artifact_grid(raw).session_variants == ("extended", "regular")


def test_observed_failure_does_not_falsely_fail_owner_control(tmp_path: Path) -> None:
    helpers = runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_parity.py")))
    loaded = helpers["loaded_export_from_canonical_fixture"](
        tmp_path, n=1190, perturb=("TG_rsi_macd_hist", -1, 1e-4)
    )
    result = run_artifact_attack(
        loaded,
        lower_grain_rows=None,
        grid=default_artifact_grid(loaded.recipe),
        ledger_path=tmp_path / "ledger.jsonl",
    )
    assert result.observed_indicator_reproduction["status"] == "FAIL"
    assert result.owner_probe_control["status"] == "PASS"
    assert result.observed_indicator_reproduction_receipts != result.owner_probe_control_receipts


def test_provisional_lower_row_is_removed_before_coverage_and_receipted() -> None:
    frame = pd.DataFrame([
        {"open_ms": 0, "close_ms": 60_000, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0, "confirmed": True},
        {"open_ms": 60_000, "close_ms": 120_000, "open": 1.5, "high": 2.0, "low": 1.0, "close": 1.7, "volume": 1.0, "confirmed": False},
    ])
    confirmed = artifact_attack._confirmed_lower(frame)
    assert confirmed["open_ms"].tolist() == [0]
    bars = pd.DataFrame(columns=["open_ms", "close_ms", "close"])
    bars.attrs.update(
        excluded_provisional_count=1,
        excluded_provisional_open_ms=(60_000,),
        excluded_provisional_row_sha256="a" * 64,
    )
    metrics = artifact_attack._geometry(bars, ())
    assert metrics["excluded_provisional_count"] == 1
    assert metrics["excluded_provisional_open_ms"] == [60_000]
    assert metrics["excluded_provisional_row_sha256"] == "a" * 64


def test_malformed_lower_evidence_is_error_not_unavailable() -> None:
    frame = pd.DataFrame([
        {"open_ms": 0, "close_ms": 60_000, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0},
        {"open_ms": 0, "close_ms": 120_000, "open": 1.5, "high": 2.0, "low": 1.0, "close": 1.7, "volume": 1.0},
    ])
    with pytest.raises(ArtifactAttackError, match="malformed"):
        artifact_attack._confirmed_lower(frame)


def test_k_binds_actual_elapsed_vector_and_uses_evidenced_sessions(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path)

    def sequence(grain: int):
        count = 100
        step = grain * 60_000
        bars = pd.DataFrame({
            "open_ms": [1_700_000_000_000 + index * step for index in range(count)],
            "close_ms": [1_700_000_000_000 + (index + 1) * step for index in range(count)],
            "close": [100.0 + index / 10.0 + float(index % 7) for index in range(count)],
        })
        receipts = tuple(
            SimpleNamespace(
                clipped=False,
                empty_interval=False,
                effective_minutes=grain,
                source_row_sha256=f"{index:064x}",
                trade_count=None,
                traded_minutes=None,
                realized_variance=None,
                volume=1.0,
                session_flags={"first_session_bar": index % 10 == 0},
            )
            for index in range(count)
        )
        return bars, receipts

    tests = artifact_attack._kernel_tests(
        loaded,
        default_artifact_grid(loaded.recipe),
        {60: sequence(60), 120: sequence(120)},
    )
    assert all(test.status == "PASS" for test in tests)
    assert all(test.metrics["clock_parameter"]["actual_vector_count"] == 100 for test in tests)
    assert all(len(test.metrics["clock_parameter"]["actual_vector_sha256"]) == 64 for test in tests)
    assert all(test.metrics["evidenced_session_count"] == 10 for test in tests)
    assert all(set(test.metrics["executions"]) == {"K0", "K1", "K2"} for test in tests)
    assert all(
        all(len(execution["output_sha256"]) == 64 for execution in test.metrics["executions"].values())
        for test in tests
    )
    assert all("per_output_path_distance" in test.metrics for test in tests)


def test_mapping_only_k_mutation_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = _loaded(tmp_path)

    def sequence(grain: int):
        step = grain * 60_000
        bars = pd.DataFrame({
            "open_ms": [1_700_000_000_000 + index * step for index in range(200)],
            "close_ms": [1_700_000_000_000 + (index + 1) * step for index in range(200)],
            "close": [100.0 + index / 10.0 + float(index % 7) for index in range(200)],
        })
        receipts = tuple(SimpleNamespace(
            effective_minutes=grain, source_row_sha256=f"{index:064x}", volume=1.0,
            trade_count=None, traded_minutes=None, realized_variance=None,
            clipped=False, empty_interval=False,
            session_flags={"first_session_bar": index % 10 == 0},
        ) for index in range(200))
        return bars, receipts

    monkeypatch.setattr(
        artifact_attack, "parameterized_indicator_frame",
        lambda close, _parameters: artifact_attack.canonical_indicator_frame(close),
    )
    tests = artifact_attack._kernel_tests(
        loaded, default_artifact_grid(loaded.recipe), {60: sequence(60), 120: sequence(120)},
    )
    assert any(test.status == "FAIL" and "K_MAPPING_ONLY_MUTATION" in test.findings for test in tests)


def test_exact_bar_only_phase_match_never_emits_artifact_token() -> None:
    test = artifact_attack._phase_uniqueness_test(
        {
            0.0: {"coverage": True, "bar_match": False, "path_pass": False},
            0.25: {"coverage": True, "bar_match": True, "path_pass": False},
            0.5: {"coverage": True, "bar_match": False, "path_pass": False},
            0.75: {"coverage": True, "bar_match": False, "path_pass": False},
        },
        "8" * 64,
    )
    assert "single_arbitrary_phase_only" not in test.findings
    assert test.status == "PASS"


def test_nonstandard_chart_is_an_a_and_d_artifact() -> None:
    helpers = runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_contracts.py")))
    raw = helpers["complete_recipe_dict"]()
    raw["chart"].update(chart_is_standard=False, chart_is_heikinashi=True)
    recipe_value = ChartRecipe.from_dict(raw)
    tests = artifact_attack._chart_type_tests(recipe_value, "2" * 64)
    assert {(test.axis, test.status) for test in tests} == {("A", "FAIL"), ("D", "FAIL")}
    assert all("nonstandard_chart_price_construction" in test.findings for test in tests)
    assert classify_mechanical_status(True, "PASS", (*_required(), *tests)) == "ARTIFACT"


_FORBIDDEN_ROOTS = {"requests", "urllib", "http", "httpx", "socket", "subprocess", "yfinance", "ccxt", "os", "shutil"}
_FORBIDDEN_MODULE_PARTS = {"outcome", "outcomes", "portfolio", "production", "trade_executor"}
_FORBIDDEN_NAMES = {"outcome", "returns", "portfolio", "raw_rows"}


def _boundary_violations(source: str) -> set[str]:
    tree = ast.parse(source)
    violations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = {part.lower() for part in alias.name.split(".")}
                if alias.name.split(".", 1)[0].lower() in _FORBIDDEN_ROOTS or parts & _FORBIDDEN_MODULE_PARTS:
                    violations.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = {part.lower() for part in node.module.split(".")}
            if node.module.split(".", 1)[0].lower() in _FORBIDDEN_ROOTS or parts & _FORBIDDEN_MODULE_PARTS:
                violations.add(node.module)
        elif isinstance(node, ast.Name) and node.id.lower() in _FORBIDDEN_NAMES:
            violations.add(node.id.lower())
        elif isinstance(node, ast.Attribute) and node.attr.lower() in _FORBIDDEN_NAMES:
            violations.add(node.attr.lower())
    return violations


def test_artifact_attack_has_no_network_outcome_or_raw_row_surface() -> None:
    assert _boundary_violations("import requests as r\nr.get('x')")
    assert _boundary_violations("portfolio = returns")
    assert _boundary_violations("from engine.outcomes import evaluate as e")
    assert _boundary_violations("from engine.trade_executor import execute as e")
    assert _boundary_violations("import os as x\nx.replace('a', 'b')")
    source = Path("scripts/research/temporal_scale/artifact_attack.py").read_text(encoding="utf-8")
    assert _boundary_violations(source) == set()


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/research/run_temporal_scale_artifact_attack.py", *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_validate_recipe_writes_atomic_provenance_bundle(tmp_path: Path) -> None:
    _loaded(tmp_path)
    output = tmp_path / "out"
    completed = _run_cli(
        "validate-recipe",
        "--recipe", str(tmp_path / "recipe.json"),
        "--csv", str(tmp_path / "synthetic.csv"),
        "--output-dir", str(output),
        "--observation-ms", "1788431707297",
    )
    assert completed.returncode == 0, completed.stderr
    expected = {
        "normalized_recipe.json", "bar_receipts.json", "kernel_signature.json",
        "parity_receipt.json", "frozen_grid.json", "run_manifest.json",
    }
    assert expected.issubset({path.name for path in output.iterdir()})
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["network_used"] is False
    assert manifest["production_ledger_used"] is False
    assert manifest["observation_ms"] == 1788431707297
    assert manifest["git_head"]
    assert set(manifest["input_sha256"]) == {"recipe", "csv"}


def test_cli_attack_parity_pass_then_typed_unresolved_without_lower_rows(tmp_path: Path) -> None:
    _loaded(tmp_path)
    output = tmp_path / "attack"
    completed = _run_cli(
        "attack",
        "--recipe", str(tmp_path / "recipe.json"),
        "--csv", str(tmp_path / "synthetic.csv"),
        "--output-dir", str(output),
    )
    assert completed.returncode == 0, completed.stderr
    assert "FROZEN_GRID_SHA256=" in completed.stdout
    result = json.loads((output / "artifact_attack_result.json").read_text(encoding="utf-8"))
    assert result["mechanical_status"] == "UNRESOLVED_DATA"
    assert result["final_mechanism_classification"] is None
    assert set(result["authority"].values()) == {False}
    assert all(len(receipt) == 64 for receipt in result["mechanical_receipts"])
    assert (output / "trial_ledger.jsonl").is_file()
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["ledger_sha256"]) == 64


def test_cli_paired_lower_recipe_is_normalized_and_hashed_even_when_unresolved(tmp_path: Path) -> None:
    loaded = _loaded(tmp_path, n=320)
    first = loaded.frame.iloc[0]
    lower_path = tmp_path / "lower.csv"
    pd.DataFrame([{
        "open_ms": int(first["TG_time_open_ms"]),
        "close_ms": int(first["TG_time_close_ms"]),
        "open": float(first["TG_open"]),
        "high": float(first["TG_high"]),
        "low": float(first["TG_low"]),
        "close": float(first["TG_close"]),
        "volume": float(first["TG_volume"]),
    }]).to_csv(lower_path, index=False)
    lower_hash = hashlib.sha256(lower_path.read_bytes()).hexdigest()
    helpers = runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_contracts.py")))
    manifest = helpers["lower_recipe_dict"](loaded.recipe.to_dict(), lower_hash)
    manifest.update(
        row_count=1,
        first_open_ms=int(first["TG_time_open_ms"]),
        last_close_ms=int(first["TG_time_close_ms"]),
        source_timeframe_minutes=60,
    )
    manifest_path = tmp_path / "lower-recipe.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "paired-lower"
    completed = _run_cli(
        "attack",
        "--recipe", str(tmp_path / "recipe.json"),
        "--csv", str(tmp_path / "synthetic.csv"),
        "--lower-grain-csv", str(lower_path),
        "--lower-grain-recipe", str(manifest_path),
        "--output-dir", str(output),
    )
    assert completed.returncode == 0, completed.stderr
    assert (output / "normalized_lower_grain_recipe.json").is_file()
    run_manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert set(run_manifest["input_sha256"]) == {
        "recipe", "csv", "lower_grain_csv", "lower_grain_recipe",
    }
    result = json.loads((output / "artifact_attack_result.json").read_text(encoding="utf-8"))
    assert result["mechanical_status"] == "UNRESOLVED_DATA"
    assert any(
        "LOWER_MANIFEST_FINAL_ENDPOINT_UNCOVERED" in test["findings"]
        for test in result["tests"]
    )


def test_cli_parity_failure_writes_typed_artifact_result(tmp_path: Path) -> None:
    helpers = runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_parity.py")))
    helpers["loaded_export_from_canonical_fixture"](
        tmp_path, n=1190, perturb=("TG_rsi_macd_hist", -1, 1e-4)
    )
    output = tmp_path / "parity-fail"
    completed = _run_cli(
        "attack",
        "--recipe", str(tmp_path / "recipe.json"),
        "--csv", str(tmp_path / "synthetic.csv"),
        "--output-dir", str(output),
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads((output / "parity_receipt.json").read_text(encoding="utf-8"))["status"] == "FAIL"
    result = json.loads((output / "artifact_attack_result.json").read_text(encoding="utf-8"))
    assert result["mechanical_status"] == "ARTIFACT"
    assert (output / "trial_ledger.jsonl").is_file()


def test_cli_refuses_production_ledger_before_writing_it(tmp_path: Path) -> None:
    _loaded(tmp_path)
    output = tmp_path / "refused"
    completed = _run_cli(
        "attack",
        "--recipe", str(tmp_path / "recipe.json"),
        "--csv", str(tmp_path / "synthetic.csv"),
        "--output-dir", str(output),
        "--ledger-path", "data/trial_ledger.jsonl",
    )
    assert completed.returncode != 0
    assert "production TrialLedger" in completed.stderr
    assert not output.exists()


def test_cli_incomplete_recipe_is_unresolved_without_loading_csv(tmp_path: Path) -> None:
    helpers = runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_contracts.py")))
    raw = helpers["complete_recipe_dict"]()
    raw["capture_status"] = "incomplete"
    raw["instrument"]["tickerid"] = ""
    raw["missing_fields"] = ["instrument.tickerid"]
    recipe_path = tmp_path / "incomplete.json"
    recipe_path.write_text(json.dumps(raw), encoding="utf-8")
    output = tmp_path / "incomplete-out"
    completed = _run_cli(
        "attack",
        "--recipe", str(recipe_path),
        "--csv", str(tmp_path / "does-not-exist.csv"),
        "--output-dir", str(output),
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads((output / "artifact_attack_result.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert result["mechanical_status"] == "UNRESOLVED_DATA"
    assert result["recipes"] == [raw["recipe_id"]]
    assert manifest["csv_loaded"] is False
