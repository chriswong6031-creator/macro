"""Strict, atomic publication boundary for ``data/regime/latest.json``."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import engine.run as regime_run

ROOT = Path(__file__).resolve().parent.parent


def _reject_nonfinite(token: str):
    raise ValueError(f"nonfinite JSON token: {token}")


def test_nested_nonfinite_numeric_leaves_publish_as_json_null(tmp_path: Path) -> None:
    target = tmp_path / "regime" / "latest.json"
    payload = {
        "finite": 1.25,
        "nested": {
            "list": [float("nan"), float("inf"), -float("inf")],
            "tuple": (np.float32("nan"), {"deep": np.float64("inf")}),
        },
    }

    normalized = regime_run._atomic_write_latest_json(target, payload)
    raw = target.read_text(encoding="utf-8")
    decoded = json.loads(raw, parse_constant=_reject_nonfinite)

    assert normalized == {
        "finite": 1.25,
        "nested": {
            "list": [None, None, None],
            "tuple": (None, {"deep": None}),
        },
    }
    assert decoded == {
        "finite": 1.25,
        "nested": {
            "list": [None, None, None],
            "tuple": [None, {"deep": None}],
        },
    }
    assert "NaN" not in raw
    assert "Infinity" not in raw


def test_valid_json_values_round_trip_exactly_and_default_str_is_preserved(
    tmp_path: Path,
) -> None:
    target = tmp_path / "latest.json"
    json_values = {
        "zero": 0,
        "negative": -17,
        "finite": 3.5,
        "bool": True,
        "none": None,
        "text": "unchanged",
        "nested": [{"value": 0.125}],
    }
    payload = {**json_values, "path": Path("regime/source.json")}

    normalized = regime_run._atomic_write_latest_json(target, payload)
    decoded = json.loads(target.read_text(encoding="utf-8"))

    assert {key: normalized[key] for key in json_values} == json_values
    assert {key: decoded[key] for key in json_values} == json_values
    assert decoded["path"] == "regime/source.json"


def test_replace_failure_keeps_previous_snapshot_and_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "latest.json"
    previous = '{"generation":"previous"}'
    target.write_text(previous, encoding="utf-8")

    def fail_replace(source, destination):
        assert Path(source).parent == target.parent
        assert Path(destination) == target
        assert (
            Path(source).read_text(encoding="utf-8") == '{\n  "generation": "next"\n}'
        )
        raise OSError("injected replace failure")

    monkeypatch.setattr(regime_run.os, "replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        regime_run._atomic_write_latest_json(target, {"generation": "next"})

    assert target.read_text(encoding="utf-8") == previous
    assert list(tmp_path.glob(".latest.json.*.tmp")) == []


def test_publication_fsyncs_file_before_replace_and_directory_after(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "latest.json"
    events: list[str] = []
    real_fsync = regime_run.os.fsync
    real_replace = regime_run.os.replace

    def record_fsync(descriptor: int) -> None:
        events.append("fsync")
        real_fsync(descriptor)

    def record_replace(source, destination) -> None:
        events.append("replace")
        real_replace(source, destination)

    monkeypatch.setattr(regime_run.os, "fsync", record_fsync)
    monkeypatch.setattr(regime_run.os, "replace", record_replace)

    regime_run._atomic_write_latest_json(target, {"ok": True})

    assert events == ["fsync", "replace", "fsync"]
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}


def test_committed_regime_latest_is_strict_finite_json() -> None:
    body = (ROOT / "data" / "regime" / "latest.json").read_text(encoding="utf-8")
    payload = json.loads(body, parse_constant=_reject_nonfinite)

    assert isinstance(payload, dict)
    assert payload["schema_version"] == 1
    json.dumps(payload, allow_nan=False, default=str)
