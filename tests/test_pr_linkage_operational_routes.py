"""All twenty frozen execution routes exercised through real CLI phase seams."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from lib import pr_linkage_validator as core
from tests.test_pr_linkage_validator import MANIFEST, VALID, observation

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("pr_linkage_cli", ROOT / "scripts/pr_linkage_validator.py")
cli = importlib.util.module_from_spec(SPEC); assert SPEC.loader; SPEC.loader.exec_module(cli)


def assert_route(capsys, status, reason):
    out, err = capsys.readouterr()
    assert out == ""
    payload = json.loads(err)
    expected = next(r for r in MANIFEST["execution_error"]["routes"] if r["reason_code"] == reason)
    assert status == expected["exit"]
    assert (payload["error"]["component"], payload["error"]["code"], payload["error"]["reason_code"]) == (expected["component"], expected["error_code"], reason)
    assert payload["execution_error_hash"] == core.digest(payload["error"])


@pytest.mark.parametrize("reason", [r["reason_code"] for r in MANIFEST["execution_error"]["routes"][:12]])
def test_all_input_contract_routes_are_typed(monkeypatch, capsys, reason):
    monkeypatch.setattr(cli, "read_input", lambda _: b"{}")
    monkeypatch.setattr(cli, "parse_input", lambda _: (_ for _ in ()).throw(core.ValidationError(reason)))
    assert_route(capsys, cli.main(["x"]), reason)


@pytest.mark.parametrize("reason, seam", [
    ("INPUT_READ_FAILED", "read_input"), ("PARSER_INTERNAL_ERROR", "parse_input"),
    ("EVALUATOR_INTERNAL_ERROR", "evaluate"), ("RENDERER_INTERNAL_ERROR", "render"),
    ("NONDETERMINISTIC_RESULT", "render"),
])
def test_internal_phase_routes_are_operational(monkeypatch, capsys, reason, seam):
    if seam == "read_input":
        monkeypatch.setattr(cli, seam, lambda _: (_ for _ in ()).throw(cli.PhaseFailure(reason)))
        assert_route(capsys, cli.main(["x"]), reason); return
    raw = core.canonical_json(observation(VALID))
    monkeypatch.setattr(cli, "read_input", lambda _: raw)
    if seam == "parse_input":
        calls = {"n": 0}
        def parse(_):
            calls["n"] += 1
            if calls["n"] == 1: raise cli.PhaseFailure(reason)
            return MANIFEST
        monkeypatch.setattr(cli, seam, parse)
    elif seam == "evaluate": monkeypatch.setattr(cli, seam, lambda *_: (_ for _ in ()).throw(cli.PhaseFailure(reason)))
    elif reason == "NONDETERMINISTIC_RESULT":
        calls = {"n": 0}; original = cli.render
        def unstable(*args):
            calls["n"] += 1
            return original(*args) + str(calls["n"]).encode()
        monkeypatch.setattr(cli, seam, unstable)
    else: monkeypatch.setattr(cli, seam, lambda *_: (_ for _ in ()).throw(cli.PhaseFailure(reason)))
    assert_route(capsys, cli.main(["x"]), reason)


@pytest.mark.parametrize("reason, seam", [
    ("OUTPUT_TEMP_CREATE_FAILED", "mkstemp"), ("OUTPUT_WRITE_FAILED", "write"), ("OUTPUT_REPLACE_FAILED", "replace"),
])
def test_atomic_output_failure_routes_are_operational(monkeypatch, capsys, tmp_path, reason, seam):
    src = tmp_path / "input.json"; src.write_bytes(core.canonical_json(observation(VALID)))
    if seam == "mkstemp": monkeypatch.setattr(cli.tempfile, seam, lambda **_: (_ for _ in ()).throw(OSError("temp")))
    elif seam == "write": monkeypatch.setattr(cli.os, seam, lambda *_: (_ for _ in ()).throw(OSError("write")))
    else: monkeypatch.setattr(cli.os, seam, lambda *_: (_ for _ in ()).throw(OSError("replace")))
    assert_route(capsys, cli.main([str(src), "--output", str(tmp_path / "report.json")]), reason)
    assert not list(tmp_path.glob(".report.json.*"))


def test_operational_route_measurement(capsys):
    routes = [r["reason_code"] for r in MANIFEST["execution_error"]["routes"]]
    missing = sorted(set(cli.ROUTES) ^ set(routes))
    print(f"operational_routes={len(routes)} missing={missing}")
    assert len(routes) == 20 and missing == []
