from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import re
import runpy

import numpy as np
import pandas as pd
import pytest

from engine.entry_radar import indicator_core
from scripts.research.temporal_scale.chart_export import LoadedChartExport, load_chart_export
from scripts.research.temporal_scale.parity import (
    PARITY_FIELDS,
    ParityError,
    ParityReceipt,
    canonical_indicator_frame,
    compare_indicator_parity,
    truncation_invariance,
)


EXPECTED_FIELDS = (
    ("TG_rsi", "rsi"),
    ("TG_rsi_macd", "rsi_macd"),
    ("TG_rsi_macd_signal", "rsi_macd_signal"),
    ("TG_rsi_macd_hist", "rsi_macd_hist"),
    ("TG_stoch_k", "stoch_k"),
    ("TG_stoch_d", "stoch_d"),
)


def _chart_helpers() -> dict[str, object]:
    return runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_chart_export.py")))


def _close(n: int) -> pd.Series:
    times = pd.Index([1_700_000_000_000 + i * 3_600_000 for i in range(n)], name="TG_time_open_ms")
    values = [100.0 + 4.0 * math.sin(i / 7.0) + 2.0 * math.cos(i / 19.0) + i / 1000.0 for i in range(n)]
    return pd.Series(values, index=times, dtype=float, name="TG_close")


def _canonical_columns(close: pd.Series) -> dict[str, pd.Series]:
    rsi = indicator_core.rsi(close)
    macd, signal = indicator_core.rsi_macd(close)
    stoch_k, stoch_d = indicator_core.stoch_rsi_kd(close)
    return {
        "TG_rsi": rsi,
        "TG_rsi_macd": macd,
        "TG_rsi_macd_signal": signal,
        "TG_rsi_macd_hist": macd - signal,
        "TG_stoch_k": stoch_k,
        "TG_stoch_d": stoch_d,
    }


def loaded_export_from_canonical_fixture(
    tmp_path: Path,
    *,
    n: int = 320,
    perturb: tuple[str, int, float] | None = None,
    final_provisional: bool = False,
) -> LoadedChartExport:
    helpers = _chart_helpers()
    rows = helpers["synthetic_rows"](n)  # type: ignore[operator]
    close = _close(n)
    columns = _canonical_columns(close)
    for position, row in enumerate(rows):
        value = float(close.iloc[position])
        row["TG_open"] = f"{value - 0.25:.16f}"
        row["TG_high"] = f"{value + 0.50:.16f}"
        row["TG_low"] = f"{value - 0.50:.16f}"
        row["TG_close"] = f"{value:.16f}"
        for field, series in columns.items():
            cell = float(series.iloc[position])
            row[field] = "" if math.isnan(cell) else f"{cell:.16f}"
    if perturb is not None:
        field, position, amount = perturb
        rows[position][field] = f"{float(rows[position][field]) + amount:.16f}"
    if final_provisional:
        rows[-1]["TG_is_confirmed"] = "0"
    recipe_path, csv_path = helpers["write_fixture"](tmp_path, rows=rows)  # type: ignore[operator]
    return load_chart_export(recipe_path, csv_path)


def test_exact_fixture_passes_and_receipt_is_frozen(tmp_path: Path) -> None:
    loaded = loaded_export_from_canonical_fixture(tmp_path)
    receipt = compare_indicator_parity(loaded, tolerance=1e-10)
    assert PARITY_FIELDS == EXPECTED_FIELDS
    assert receipt.status == "PASS"
    assert receipt.compared_rows > 0
    assert receipt.first_comparable_bar_ms in loaded.frame["TG_time_open_ms"].tolist()
    expected = _canonical_columns(
        pd.Series(
            loaded.frame["TG_close"].tolist(),
            index=pd.Index(loaded.frame["TG_time_open_ms"].tolist()),
            dtype=float,
        )
    )
    expected_latest_first = max(
        int(series.index[np.flatnonzero(np.isfinite(series.to_numpy(dtype=float)))[0]])
        for series in expected.values()
    )
    assert receipt.first_comparable_bar_ms == expected_latest_first
    assert max(value for value in receipt.max_abs_error.values() if value is not None) <= 1e-10
    with pytest.raises(TypeError):
        receipt.max_abs_error["TG_rsi"] = 0.0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        receipt.status = "FAIL"  # type: ignore[misc]


def test_perturbed_histogram_fails_with_exact_token(tmp_path: Path) -> None:
    loaded = loaded_export_from_canonical_fixture(
        tmp_path, perturb=("TG_rsi_macd_hist", -1, 1e-4)
    )
    receipt = compare_indicator_parity(loaded, tolerance=1e-10)
    assert receipt.status == "FAIL"
    assert receipt.failures == ("PARITY_TOLERANCE_EXCEEDED:TG_rsi_macd_hist",)


def test_every_field_must_have_comparable_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = loaded_export_from_canonical_fixture(tmp_path)
    monkeypatch.setattr(
        indicator_core, "rsi", lambda close: pd.Series(np.nan, index=close.index, dtype=float)
    )
    receipt = compare_indicator_parity(loaded)
    assert receipt.status == "FAIL"
    assert receipt.failures == ("PARITY_NO_COMPARABLE_ROWS",)
    assert receipt.max_abs_error["TG_rsi"] is None


@pytest.mark.parametrize(
    "index",
    [
        [10, 11, "12"],
        [10, 10, 11],
        [10, 12, 11],
        [10, True, 12],
    ],
)
def test_close_requires_exact_strict_increasing_unique_integer_time_index(index: list[object]) -> None:
    with pytest.raises(ParityError):
        canonical_indicator_frame(pd.Series([1.0, 2.0, 3.0], index=index))


def test_owner_output_cannot_positionally_shift(monkeypatch: pytest.MonkeyPatch) -> None:
    close = _close(100)
    original = indicator_core.rsi

    def shifted(series: pd.Series) -> pd.Series:
        result = original(series)
        result.index = result.index + 1
        return result

    monkeypatch.setattr(indicator_core, "rsi", shifted)
    with pytest.raises(ParityError, match="index-aligned"):
        canonical_indicator_frame(close)


@pytest.mark.parametrize(
    "bad_output",
    [
        [1.0, 2.0],
        pd.Series([True] * 100, index=_close(100).index),
        pd.Series([float("inf")] * 100, index=_close(100).index),
    ],
)
def test_malformed_owner_scalar_and_container_outputs_normalize(
    monkeypatch: pytest.MonkeyPatch, bad_output: object
) -> None:
    monkeypatch.setattr(indicator_core, "rsi", lambda _close: bad_output)
    with pytest.raises(ParityError):
        canonical_indicator_frame(_close(100))


@pytest.mark.parametrize(
    "bad_cell",
    [None, pd.NA, float("nan"), float("inf"), True, "1.0", [1.0], 10**400],
)
def test_close_cells_fail_closed_as_parity_error(bad_cell: object) -> None:
    close = _close(100).astype(object)
    close.iloc[0] = bad_cell
    with pytest.raises(ParityError):
        canonical_indicator_frame(close)


@pytest.mark.parametrize("bad_index", [[-1, 0, 1], [0, 1, 10**400]])
def test_timestamp_range_errors_are_normalized(bad_index: list[int]) -> None:
    with pytest.raises(ParityError):
        canonical_indicator_frame(
            pd.Series([1.0, 2.0, 3.0], index=pd.Index(np.asarray(bad_index, dtype=object)))
        )


def test_final_provisional_row_is_excluded_before_parity(tmp_path: Path) -> None:
    loaded = loaded_export_from_canonical_fixture(tmp_path, n=321, final_provisional=True)
    assert len(loaded.frame) == 320
    assert loaded.excluded_provisional_row_sha256 is not None
    assert compare_indicator_parity(loaded).status == "PASS"


def test_canonical_calls_each_allowed_owner_once(monkeypatch: pytest.MonkeyPatch) -> None:
    counts = {"rsi": 0, "rsi_macd": 0, "stoch_rsi_kd": 0}
    for name in tuple(counts):
        original = getattr(indicator_core, name)

        def wrapper(close: pd.Series, *, _name: str = name, _original=original):
            counts[_name] += 1
            return _original(close)

        monkeypatch.setattr(indicator_core, name, wrapper)
    frame = canonical_indicator_frame(_close(320))
    assert tuple(frame.columns) == tuple(field[1] for field in EXPECTED_FIELDS)
    assert counts == {"rsi": 1, "rsi_macd": 1, "stoch_rsi_kd": 1}


def test_truncation_1127_is_five_typed_unavailable_records() -> None:
    tests = truncation_invariance(_close(1127), drop_prefixes=(1, 5, 13, 31, 63))
    assert len(tests) == 5
    assert {test.axis for test in tests} == {"TRUNCATION"}
    assert {test.status for test in tests} == {"UNAVAILABLE"}
    assert {test.findings for test in tests} == {("TRUNCATION_HISTORY_INSUFFICIENT",)}


def test_truncation_required_history_is_computed_per_prefix_drop() -> None:
    tests = truncation_invariance(_close(1189), drop_prefixes=(1, 5, 13, 31, 63))
    assert len(tests) == 5
    assert [test.status for test in tests] == ["PASS", "PASS", "PASS", "PASS", "UNAVAILABLE"]
    assert [test.metrics["required_rows"] for test in tests] == [1128, 1132, 1140, 1158, 1190]


def test_truncation_1190_is_exact_deterministic_five_passes_and_recomputes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = {"rsi": 0, "rsi_macd": 0, "stoch_rsi_kd": 0}
    for name in tuple(counts):
        original = getattr(indicator_core, name)

        def wrapper(close: pd.Series, *, _name: str = name, _original=original):
            counts[_name] += 1
            return _original(close)

        monkeypatch.setattr(indicator_core, name, wrapper)
    close = _close(1190)
    first = truncation_invariance(close, drop_prefixes=(1, 5, 13, 31, 63))
    assert len(first) == 5
    assert tuple(test.variant_id for test in first) == tuple(
        f"drop_prefix_{drop}" for drop in (1, 5, 13, 31, 63)
    )
    assert all(test.status == "PASS" for test in first)
    assert all(test.metrics["compared_rows"] == 256 for test in first)
    assert all(test.metrics["max_bounded_output_delta"] == 400.0 for test in first)
    assert all(test.metrics["event_timestamp_agreement"] is True for test in first)
    assert all(test.metrics["baseline_event_timestamps"] == test.metrics["truncated_event_timestamps"] for test in first)
    assert all(re.fullmatch(r"[0-9a-f]{64}", test.test_id) for test in first)
    assert all(re.fullmatch(r"[0-9a-f]{64}", test.input_hash) for test in first)
    assert len({test.input_hash for test in first}) == 5
    assert counts == {"rsi": 6, "rsi_macd": 6, "stoch_rsi_kd": 6}
    second = truncation_invariance(close, drop_prefixes=(1, 5, 13, 31, 63))
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]


def test_truncation_detects_deliberate_prefix_dependent_divergence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = indicator_core.rsi

    def divergent(close: pd.Series) -> pd.Series:
        result = original(close)
        return result + float(close.iloc[0]) / 10_000.0

    monkeypatch.setattr(indicator_core, "rsi", divergent)
    tests = truncation_invariance(_close(1190), drop_prefixes=(1, 5, 13, 31, 63))
    assert any(test.status == "FAIL" for test in tests)
    assert all(test.metrics["compared_rows"] == 256 for test in tests)
    assert all(
        test.findings == ("TRUNCATION_INVARIANCE_FAILED",)
        for test in tests
        if test.status == "FAIL"
    )


def test_truncation_event_timestamp_divergence_fails_below_numeric_tolerance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_length = 1190

    def near_equal_events(close: pd.Series) -> pd.DataFrame:
        frame = pd.DataFrame(
            0.0,
            index=close.index,
            columns=("rsi", "rsi_macd", "rsi_macd_signal", "rsi_macd_hist", "stoch_k", "stoch_d"),
        )
        if len(close) == baseline_length - 1:
            position = len(frame) - 200
            frame.iloc[position, frame.columns.get_loc("rsi_macd")] = 5e-11
            frame.iloc[position, frame.columns.get_loc("rsi_macd_hist")] = 5e-11
        return frame

    monkeypatch.setattr(
        "scripts.research.temporal_scale.parity.canonical_indicator_frame",
        near_equal_events,
    )
    tests = truncation_invariance(_close(baseline_length), drop_prefixes=(1, 5, 13, 31, 63))
    first = tests[0]
    assert max(value for value in first.metrics["max_abs_error"].values() if value is not None) <= 1e-10
    assert first.metrics["event_timestamp_agreement"] is False
    assert first.status == "FAIL"
    assert first.findings == ("TRUNCATION_EVENT_TIMESTAMPS_DIVERGED",)


def test_truncation_missing_comparable_tail_is_unavailable_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(close: pd.Series) -> pd.DataFrame:
        return pd.DataFrame(
            np.nan,
            index=close.index,
            columns=("rsi", "rsi_macd", "rsi_macd_signal", "rsi_macd_hist", "stoch_k", "stoch_d"),
        )

    monkeypatch.setattr(
        "scripts.research.temporal_scale.parity.canonical_indicator_frame",
        unavailable,
    )
    tests = truncation_invariance(_close(1190), drop_prefixes=(1, 5, 13, 31, 63))
    assert {test.status for test in tests} == {"UNAVAILABLE"}
    assert {test.findings for test in tests} == {("TRUNCATION_COMPARABLE_EVIDENCE_UNAVAILABLE",)}


@pytest.mark.parametrize("bad", [1e-9, 0.0, -1.0, True, np.float64(1e-10)])
def test_tolerance_is_exact_builtin_frozen_value(bad: object) -> None:
    with pytest.raises(ParityError):
        truncation_invariance(
            _close(1190), drop_prefixes=(1, 5, 13, 31, 63), tolerance=bad
        )  # type: ignore[arg-type]


def test_truncation_configuration_is_exact() -> None:
    close = _close(1190)
    with pytest.raises(ParityError):
        truncation_invariance(close, drop_prefixes=(1, 5, 13, 31))
    with pytest.raises(ParityError):
        truncation_invariance(close, drop_prefixes=(1, 5, 13, 31, True))
    with pytest.raises(ParityError):
        truncation_invariance(close, drop_prefixes=(1, 5, 13, 31, 63), comparison_tail=255)
    with pytest.raises(ParityError):
        truncation_invariance(
            pd.DataFrame({"close": close}), drop_prefixes=(1, 5, 13, 31, 63)
        )  # type: ignore[arg-type]


def test_parity_receipt_constructor_validates_all_fields() -> None:
    errors = {field: 0.0 for field, _ in EXPECTED_FIELDS}
    receipt = ParityReceipt(
        status="PASS", tolerance=1e-10, first_comparable_bar_ms=1,
        compared_rows=1, max_abs_error=errors, failures=(),
    )
    assert receipt.to_dict()["max_abs_error"] == errors
    with pytest.raises(ParityError):
        ParityReceipt(
            status="PASS", tolerance=1e-10, first_comparable_bar_ms=1,
            compared_rows=1, max_abs_error={"TG_rsi": 0.0}, failures=(),
        )


_FORBIDDEN_ROOTS = {"requests", "urllib", "http", "httpx", "socket", "subprocess", "ftplib"}
_FORBIDDEN_CALLS = {
    "open", "write", "write_text", "write_bytes", "to_csv", "unlink", "remove", "rename",
    "replace", "touch", "mkdir", "makedirs", "rmdir", "rmtree", "move", "system", "popen",
}
_FORBIDDEN_DOMAIN_NAMES = {"outcome", "returns", "trade", "portfolio", "ledger", "production", "raw_rows"}


def _guard_violations(source: str) -> set[str]:
    tree = ast.parse(source)
    violations: set[str] = set()
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0].lower()
                aliases[alias.asname or root] = alias.name
                if root in _FORBIDDEN_ROOTS:
                    violations.add(root)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0].lower()
            if root in _FORBIDDEN_ROOTS:
                violations.add(root)
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{module}.{alias.name}"

    def dotted(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = dotted(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        if isinstance(node, ast.Call):
            return dotted(node.func)
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = dotted(node.func).lower()
            root = target.split(".", 1)[0]
            leaf = target.rsplit(".", 1)[-1]
            if root in _FORBIDDEN_ROOTS:
                violations.add(root)
            if leaf in _FORBIDDEN_CALLS:
                violations.add(leaf)
        elif isinstance(node, ast.Name) and node.id.lower() in _FORBIDDEN_DOMAIN_NAMES:
            violations.add(node.id.lower())
        elif isinstance(node, ast.Attribute) and node.attr.lower() in _FORBIDDEN_DOMAIN_NAMES:
            violations.add(node.attr.lower())
    return violations


def test_ast_guard_is_self_tested_and_parity_has_no_effect_or_outcome_path() -> None:
    assert _guard_violations("import socket\nsocket.create_connection(('x', 1))")
    assert _guard_violations("from socket import create_connection as connect\nconnect(('x', 1))")
    assert _guard_violations("from pathlib import Path\nPath('x').write_text('x')")
    assert _guard_violations("import os as sneaky\nsneaky.replace('x', 'y')")
    assert _guard_violations("import subprocess\nsubprocess.run(['x'])")
    assert _guard_violations("open('x', 'w')")
    assert _guard_violations("raw_rows = []")
    assert _guard_violations("portfolio.trade()")
    source = Path("scripts/research/temporal_scale/parity.py").read_text(encoding="utf-8")
    assert _guard_violations(source) == set()
