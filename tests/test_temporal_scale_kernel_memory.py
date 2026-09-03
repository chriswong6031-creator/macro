from __future__ import annotations

import ast
import functools
import math
from pathlib import Path
import runpy
from collections.abc import Mapping as AbstractMapping
import textwrap

import numpy as np
import pandas as pd
import pytest

from scripts.research.temporal_scale.kernel_memory import (
    KernelMemoryError,
    canonical_kernel_signature,
    continuous_ema,
    ema_half_life_bars,
    ema_length_for_half_life_bars,
    rma_half_life_bars,
)


def test_exact_half_lives_and_ema60_retention_identity() -> None:
    assert ema_half_life_bars(14) == 4.843767254792992
    assert ema_half_life_bars(60) == 20.792489865319812
    assert ema_half_life_bars(5) == 1.7095112913514545
    assert rma_half_life_bars(14) == 9.353206684999464
    alpha, retention = 2 / 61, (60 - 1) / (60 + 1)
    assert alpha + retention == 1
    assert ema_half_life_bars(60) == pytest.approx(math.log(0.5) / math.log(retention))
    assert 1 / alpha == 30.5
    rma_alpha, rma_retention = 1 / 14, 13 / 14
    assert rma_alpha + rma_retention == 1
    assert rma_half_life_bars(14) == math.log(0.5) / math.log(rma_retention)


@pytest.mark.parametrize("value", (0, -1, True, 1.0, "14", 2**53))
def test_lengths_are_real_integers_at_least_one(value: object) -> None:
    with pytest.raises(KernelMemoryError):
        ema_half_life_bars(value)


def test_inverse_is_stable_nearest_and_round_trips() -> None:
    for length in (1, 14, 60, 10_000, 1_000_000_000):
        assert ema_length_for_half_life_bars(ema_half_life_bars(length)) == length
    assert ema_length_for_half_life_bars(0.0) == 1
    for target in (float("nan"), 1e308, ema_half_life_bars(2**53 - 1) + 1):
        with pytest.raises(KernelMemoryError):
            ema_length_for_half_life_bars(target)
    with pytest.raises(KernelMemoryError):
        ema_length_for_half_life_bars(10**400)


def test_continuous_ema_clock_zero_missing_and_seed_semantics() -> None:
    values = pd.Series([1.0, 10.0, np.nan, 10.0], index=["a", "b", "c", "d"])
    increments = pd.Series([0.0, 1.0, 2.0, 1.0], index=values.index)
    out = continuous_ema(values, increments, tau=1.0)
    assert out.index.equals(values.index)
    assert out.iloc[0] == 1.0
    assert out.iloc[1] == pytest.approx(1 + 9 * (1 - math.exp(-1)))
    assert math.isnan(out.iloc[2])
    assert out.iloc[3] == pytest.approx(out.iloc[1] + (10 - out.iloc[1]) * (1 - math.exp(-1)))
    assert continuous_ema(pd.Series([10.0]), pd.Series([0.0]), tau=1.0, seed=3.0).iloc[0] == 3.0
    assert continuous_ema(pd.Series([1e308]), pd.Series([math.log(2.0)]), tau=1.0, seed=-1e308).iloc[0] == 0.0


def test_object_dtype_task3_style_values_normalize_cellwise_without_coercion() -> None:
    values = pd.Series([np.float64(1.0), None, pd.NA, np.float64(2.0)], index=pd.RangeIndex(4), dtype=object)
    out = continuous_ema(values, pd.Series([0, 1, 1, 1], index=values.index, dtype=object), tau=np.float64(1.0))
    assert out.index.equals(values.index)
    assert out.iloc[0] == 1.0 and math.isnan(out.iloc[1]) and math.isnan(out.iloc[2])
    assert out.iloc[3] == pytest.approx(1 + (1 - math.exp(-1)))
    signature = canonical_kernel_signature(pd.Series([None, np.float64(100), pd.NA, np.float64(101)], dtype=object))
    assert signature.input_series == "close"


def test_task3_loaded_frame_close_survives_object_dtype_boundary(tmp_path: Path) -> None:
    from scripts.research.temporal_scale.chart_export import load_chart_export

    task3_helpers = runpy.run_path(str(Path(__file__).with_name("test_temporal_scale_chart_export.py")))
    recipe_path, csv_path = task3_helpers["write_fixture"](tmp_path)
    loaded = load_chart_export(recipe_path, csv_path)
    task3_close = pd.Series(loaded.frame["TG_close"].tolist(), index=loaded.frame.index, dtype=object)
    assert canonical_kernel_signature(task3_close).input_series == "close"


def test_continuous_ema_rejects_alignment_clock_and_numeric_errors() -> None:
    with pytest.raises(KernelMemoryError):
        continuous_ema(pd.Series([1.0]), pd.Series([1.0], index=[1]), tau=1.0)
    for increments in (pd.Series([-1.0]), pd.Series([np.inf])):
        with pytest.raises(KernelMemoryError):
            continuous_ema(pd.Series([1.0]), increments, tau=1.0)
    for invalid in (True, 1 + 2j, "1", [], {"x": 1}, object(), np.inf):
        with pytest.raises(KernelMemoryError):
            continuous_ema(pd.Series([invalid], dtype=object), pd.Series([0]), tau=1.0)
    with pytest.raises(KernelMemoryError):
        continuous_ema(pd.Series([1.0]), pd.Series([True], dtype=object), tau=1.0)
    with pytest.raises(KernelMemoryError):
        continuous_ema(pd.Series([1.0]), pd.Series([0.0]), tau=1.0, seed=True)
    with pytest.raises(KernelMemoryError):
        continuous_ema(pd.Series([10**400], dtype=object), pd.Series([0.0]), tau=1.0)


def test_canonical_signature_calls_owner_and_is_contract_valid_immutable() -> None:
    close = pd.Series(np.linspace(100, 200, 200))
    signature = canonical_kernel_signature(close, clock_basis="bar_count")
    assert signature.clock_basis == "bar_count"
    assert set(signature.warmup_first_finite_index) == {"rsi", "rsi_macd", "rsi_macd_signal", "rsi_macd_hist", "stoch_k", "stoch_d"}
    assert signature.to_dict() == type(signature).from_dict(signature.to_dict()).to_dict()
    with pytest.raises(TypeError):
        signature.clock_parameter["x"] = 1


def test_canonical_signature_uses_each_public_owner_channel_and_output_warmups(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.entry_radar import indicator_core

    calls: list[str] = []
    index = pd.RangeIndex(10)
    channels = {
        "rsi": pd.Series([np.nan, 50.0, 51.0, 52.0, 53.0, 54.0, 55.0, 56.0, 57.0, 58.0], index=index),
        "rsi_macd": (pd.Series([np.nan, np.nan, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], index=index), pd.Series([np.nan, np.nan, np.nan, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5], index=index)),
        "rsi_macd_hist": pd.Series([np.nan, np.nan, np.nan, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5], index=index),
        "stoch_rsi_kd": (pd.Series([np.nan, np.nan, np.nan, np.nan, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0], index=index), pd.Series([np.nan, np.nan, np.nan, np.nan, np.nan, 10.0, 10.0, 10.0, 10.0, 10.0], index=index)),
    }

    def wrapper(name: str):
        def wrapped(close: pd.Series):
            calls.append(name)
            return channels[name]
        return wrapped

    for name in channels:
        monkeypatch.setattr(indicator_core, name, wrapper(name))
    signature = canonical_kernel_signature(pd.Series(np.linspace(100, 200, 10)))
    assert {name: calls.count(name) for name in channels} == {name: 1 for name in channels}
    assert {component["name"] for component in signature.components} == {"rsi", "rsi_macd", "rsi_macd_hist", "stoch_rsi"}
    assert signature.warmup_first_finite_index == {"rsi": 1, "rsi_macd": 2, "rsi_macd_signal": 3, "rsi_macd_hist": 3, "stoch_k": 4, "stoch_d": 5}
    assert signature.indicator_spec_hash == "2315288df6bcdef053a19789dbb8748e6cf819c8ad15d3874ffe9459a497f758"


def test_owner_default_config_is_bound_and_calls_have_exact_supported_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.entry_radar import indicator_core

    calls: dict[str, dict[str, object]] = {}
    originals = {name: getattr(indicator_core, name) for name in ("rsi", "rsi_macd", "rsi_macd_hist", "stoch_rsi_kd")}

    def wrapper(name: str):
        @functools.wraps(originals[name])
        def wrapped(*args: object, **kwargs: object):
            calls[name] = kwargs
            return originals[name](*args, **kwargs)
        return wrapped

    for name in originals:
        monkeypatch.setattr(indicator_core, name, wrapper(name))
    canonical_kernel_signature(pd.Series(np.linspace(100, 200, 200)))
    # Owner public signatures expose only ``close`` today, so fail-closed config
    # binding correctly permits no unsupported kwargs.
    assert calls == {name: {} for name in originals}
    drifted = dict(indicator_core.INDICATOR_CORE)
    drifted["macd_slow"] = 59
    monkeypatch.setattr(indicator_core, "INDICATOR_CORE", drifted)
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(pd.Series(np.linspace(100, 200, 200)))


@pytest.mark.parametrize(
    "replacement",
    (
        lambda *, close: pd.Series(close),
        lambda close, /: pd.Series(close),
        lambda close, *extra: pd.Series(close),
        lambda close, extra=None: pd.Series(close),
        None,
    ),
)
def test_owner_signature_must_be_one_positional_close_without_extras(monkeypatch: pytest.MonkeyPatch, replacement: object) -> None:
    from engine.entry_radar import indicator_core

    monkeypatch.setattr(indicator_core, "rsi", replacement)
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(pd.Series(np.linspace(1, 100, 100)))


@pytest.mark.parametrize(
    "bad_return",
    (
        [1.0, 2.0],
        pd.Series([1.0, 2.0], index=["foreign", "index"]),
        pd.Series([True, False], dtype=object),
    ),
)
def test_owner_return_shape_and_cells_are_validated(monkeypatch: pytest.MonkeyPatch, bad_return: object) -> None:
    from engine.entry_radar import indicator_core

    monkeypatch.setattr(indicator_core, "rsi", lambda close: bad_return)
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(pd.Series(np.linspace(1, 100, 100)))


@pytest.mark.parametrize("bad_pair", ((pd.Series([1.0]),), (pd.Series([1.0]), [1.0]), [pd.Series([1.0]), pd.Series([1.0])]))
def test_owner_pair_return_tuple_arity_and_member_types_are_validated(monkeypatch: pytest.MonkeyPatch, bad_pair: object) -> None:
    from engine.entry_radar import indicator_core

    monkeypatch.setattr(indicator_core, "rsi_macd", lambda close: bad_pair)
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(pd.Series(np.linspace(1, 100, 100)))


def test_canonical_signature_warmups_match_actual_owner_outputs() -> None:
    from engine.entry_radar import indicator_core

    close = pd.Series(np.linspace(100, 200, 200))
    rsi = indicator_core.rsi(close)
    macd, signal = indicator_core.rsi_macd(close)
    hist = indicator_core.rsi_macd_hist(close)
    stoch_k, stoch_d = indicator_core.stoch_rsi_kd(close)
    expected = {
        name: next((position for position, value in enumerate(channel) if np.isfinite(value)), None)
        for name, channel in {"rsi": rsi, "rsi_macd": macd, "rsi_macd_signal": signal, "rsi_macd_hist": hist, "stoch_k": stoch_k, "stoch_d": stoch_d}.items()
    }
    assert canonical_kernel_signature(close).warmup_first_finite_index == expected


@pytest.mark.parametrize("clock_parameter", (3, [], {"actual_vector_provenance": 3}))
def test_canonical_signature_normalizes_invalid_clock_parameter_errors(clock_parameter: object) -> None:
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(
            pd.Series(np.linspace(1, 100, 100)),
            clock_basis="traded_time",
            clock_parameter=clock_parameter,
            clock_increments=pd.Series(np.ones(100)),
        )


def test_clock_parameter_is_strict_json_and_detached_immutable() -> None:
    parameter = {"unit": "seconds", "source_receipt_sha256": "a" * 64}
    increments = pd.Series(np.ones(100), index=pd.RangeIndex(100))
    signature = canonical_kernel_signature(
        pd.Series(np.linspace(1, 100, 100)),
        clock_basis="elapsed_time",
        clock_parameter=parameter,
        clock_increments=increments,
    )
    parameter["unit"] = "changed"
    assert signature.clock_parameter["unit"] == "seconds"
    with pytest.raises(TypeError):
        signature.clock_parameter["unit"] = "changed"
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(
            pd.Series(np.linspace(1, 100, 100)),
            clock_basis="elapsed_time",
            clock_parameter={"unit": "seconds", "source_receipt_sha256": "a" * 64, "bad": float("nan")},
            clock_increments=increments,
        )


def test_clock_provenance_is_exact_keyed_and_has_stable_attested_goldens() -> None:
    close = pd.Series([100.0, 101.0], index=pd.RangeIndex(2))
    parameter = {"unit": "seconds", "source_receipt_sha256": "c" * 64}
    signature = canonical_kernel_signature(close, clock_basis="elapsed_time", clock_parameter=parameter, clock_increments=pd.Series([1.0, 2.0], index=close.index))
    assert signature.clock_parameter["actual_vector_sha256"] == "44c32c0bf4f665d42f890db37d9eef40d82f33c1379e1871917625787d164d4b"
    assert signature.clock_parameter["actual_vector_index_sha256"] == "463f2998327eb3a694145e6014444480b2235be84aa6cfd57871cc64f1cd816c"
    changed_vector = canonical_kernel_signature(close, clock_basis="elapsed_time", clock_parameter=parameter, clock_increments=pd.Series([1.0, 3.0], index=close.index))
    changed_index = canonical_kernel_signature(close.set_axis(["a", "b"]), clock_basis="elapsed_time", clock_parameter=parameter, clock_increments=pd.Series([1.0, 2.0], index=["a", "b"]))
    changed_receipt = canonical_kernel_signature(close, clock_basis="elapsed_time", clock_parameter={"unit": "seconds", "source_receipt_sha256": "d" * 64}, clock_increments=pd.Series([1.0, 2.0], index=close.index))
    assert changed_vector.clock_parameter["actual_vector_sha256"] != signature.clock_parameter["actual_vector_sha256"]
    assert changed_index.clock_parameter["actual_vector_index_sha256"] != signature.clock_parameter["actual_vector_index_sha256"]
    assert changed_receipt.clock_parameter["source_receipt_sha256"] != signature.clock_parameter["source_receipt_sha256"]
    for hostile in ({"unit": "seconds", "source_receipt_sha256": "c" * 64, "extra": "lost"}, {"unit": "seconds", "source_receipt_sha256": "c" * 64, "extra": {}}):
        with pytest.raises(KernelMemoryError):
            canonical_kernel_signature(close, clock_basis="elapsed_time", clock_parameter=hostile, clock_increments=pd.Series([1.0, 2.0]))
    cyclic: dict[str, object] = {"unit": "seconds"}
    cyclic["source_receipt_sha256"] = cyclic
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(close, clock_basis="elapsed_time", clock_parameter=cyclic, clock_increments=pd.Series([1.0, 2.0]))


@pytest.mark.parametrize("close", (pd.Series([1.0, np.inf]), pd.Series(["1", "2"]), [1.0, 2.0]))
def test_canonical_signature_rejects_noncanonical_close_without_coercion(close: object) -> None:
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(close)


@pytest.mark.parametrize("basis", ("bar_count", "elapsed_time", "traded_time", "volume_time", "trade_time", "variance_time"))
def test_all_clock_enums_and_nonbar_provenance_fence(basis: str) -> None:
    close = pd.Series(np.linspace(1, 100, 100))
    parameter = {"unit": "seconds", "source_receipt_sha256": "b" * 64} if basis != "bar_count" else None
    increments = pd.Series(np.ones(100), index=close.index) if basis != "bar_count" else None
    signature = canonical_kernel_signature(close, clock_basis=basis, clock_parameter=parameter, clock_increments=increments)
    assert signature.clock_basis == basis
    if basis != "bar_count":
        with pytest.raises(KernelMemoryError):
            canonical_kernel_signature(close, clock_basis=basis, clock_parameter={})
        assert signature.clock_parameter == {
            "unit": "seconds", "source_receipt_sha256": "b" * 64,
            "actual_vector_count": 100,
            "actual_vector_sha256": signature.clock_parameter["actual_vector_sha256"],
            "actual_vector_index_sha256": signature.clock_parameter["actual_vector_index_sha256"],
        }


def test_nonbar_clock_rejects_vector_mismatch_bad_receipt_and_index_labels() -> None:
    close = pd.Series(np.linspace(1, 100, 100))
    parameter = {"unit": "seconds", "source_receipt_sha256": "c" * 64}
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(close, clock_basis="traded_time", clock_parameter=parameter)
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(close, clock_basis="traded_time", clock_parameter={"unit": "", "source_receipt_sha256": "C" * 64}, clock_increments=pd.Series(np.ones(100)))
    with pytest.raises(KernelMemoryError):
        canonical_kernel_signature(pd.Series(np.linspace(1, 100, 100), index=[("bad",)] * 100), clock_basis="traded_time", clock_parameter=parameter, clock_increments=pd.Series(np.ones(100), index=[("bad",)] * 100))


def test_bar_count_metadata_is_empty_mapping_without_adversarial_equality() -> None:
    class ExplosiveMapping(AbstractMapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise RuntimeError("hostile")

        def __iter__(self):
            raise RuntimeError("hostile")

        def __len__(self) -> int:
            raise RuntimeError("hostile")

        def __eq__(self, other: object) -> bool:
            raise RuntimeError("hostile")

    close = pd.Series(np.linspace(1, 100, 100))
    assert canonical_kernel_signature(close, clock_parameter={}).clock_basis == "bar_count"
    for hostile in (ExplosiveMapping(), np.array([]), {"cyclic": None}):
        with pytest.raises(KernelMemoryError):
            canonical_kernel_signature(close, clock_parameter=hostile)


_UNSAFE_ROOTS = frozenset({"requests", "urllib", "httpx", "socket", "subprocess", "os"})
_MUTATING_CALLS = frozenset({"write", "write_text", "write_bytes", "unlink", "remove", "rename", "replace", "touch", "mkdir", "makedirs", "rmdir", "rmtree", "move", "system", "popen"})
_OPEN_TARGETS = frozenset({"open", "builtins.open", "io.open", "pathlib.Path.open"})


def _assert_no_unsafe_effects(source: str) -> None:
    tree = ast.parse(source)
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _UNSAFE_ROOTS, f"unsafe import: {root}"
                aliases[alias.asname or root] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0]
            assert root not in _UNSAFE_ROOTS, f"unsafe import: {root}"
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{module}.{alias.name}" if module else alias.name

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
        if not isinstance(node, ast.Call):
            continue
        target = dotted(node.func)
        assert target.split(".", 1)[0] not in _UNSAFE_ROOTS, f"unsafe call: {target}"
        assert target.rsplit(".", 1)[-1] not in _MUTATING_CALLS, f"unsafe mutation: {target}"
        if target in _OPEN_TARGETS:
            mode_node = next((keyword.value for keyword in node.keywords if keyword.arg == "mode"), None)
            if mode_node is None:
                position = 0 if target == "pathlib.Path.open" else 1
                mode_node = node.args[position] if len(node.args) > position else None
            if mode_node is None:
                mode = "r"
            else:
                assert isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str), f"unsafe open mode: {target}"
                mode = mode_node.value
            assert not ({"w", "a", "x", "+"} & set(mode)), f"unsafe open mode: {target}"


def test_kernel_module_has_no_network_outcome_or_data_loader_effects() -> None:
    import scripts.research.temporal_scale.kernel_memory as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    _assert_no_unsafe_effects(source)
    for forbidden in ("outcome", "portfolio", "read_csv", "read_parquet", "technicals"):
        assert forbidden not in source


@pytest.mark.parametrize(
    "snippet",
    (
        "import socket\nsocket.create_connection(('example.test', 443))",
        "from socket import create_connection as connect\nconnect(('example.test', 443))",
        "import os\nos.replace('old', 'new')",
        "from pathlib import Path\nPath('x').unlink()",
        "from pathlib import Path\nPath('x').write_text('x')",
        "import subprocess\nsubprocess.run(['echo', 'x'])",
        "from subprocess import Popen as spawn\nspawn(['echo', 'x'])",
        "import os\nos.system('echo x')",
        "from os import popen as shell\nshell('echo x')",
        "open('x', 'w')",
    ),
)
def test_effect_guard_rejects_unsafe_imports_calls_and_writes(snippet: str) -> None:
    with pytest.raises(AssertionError):
        _assert_no_unsafe_effects(textwrap.dedent(snippet))


def test_effect_guard_permits_read_only_and_rejects_dynamic_path_mode() -> None:
    _assert_no_unsafe_effects("from pathlib import Path\nPath('fixture').open('rb')\nopen('fixture', 'r')")
    with pytest.raises(AssertionError):
        _assert_no_unsafe_effects("from pathlib import Path\nmode_var = 'r'\nPath('fixture').open(mode_var)")
