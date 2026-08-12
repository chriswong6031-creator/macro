from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_native_host_wrapper_and_manifest_are_installable_and_secret_free() -> None:
    wrapper = ROOT / "ops" / "native_messaging" / "run_momoedge_browser_host.sh"
    manifest = json.loads(
        (ROOT / "ops" / "native_messaging" / "com.mastermind.optionsnbbocohort.momoedge_observe.json").read_text()
    )
    assert stat.S_IMODE(wrapper.stat().st_mode) == 0o755
    assert manifest["path"] == "/Users/chriswong/options-nbbo-ops-wt/ops/native_messaging/run_momoedge_browser_host.sh"
    source = wrapper.read_text() + json.dumps(manifest)
    for marker in ("TOKEN", "PASSWORD", "COOKIE", "AUTHORIZATION", "API_KEY"):
        assert marker not in source.upper()
    assert "/Users/chriswong/.mastermind_private/momoedge_browser_observe_v1" in source
    assert "/Users/chriswong/.mastermind_private/options_nbbo_cohort_v1" not in source
    assert 'exec "$PYTHON_BIN" -I "$OPS_CHECKOUT/scripts/momoedge_browser_receiver.py"' in source


def test_observe_only_contract_schemas_are_valid_and_closed() -> None:
    for name in (
        "options.momoedge_browser_observation.v1.schema.json",
        "options.momoedge_browser_observe_journal.v1.schema.json",
    ):
        schema = json.loads((ROOT / "contracts" / "options" / name).read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
        assert "coverage" in schema["description"].lower()


def test_runbook_requires_user_control_and_forbids_cohort_integration() -> None:
    runbook = (ROOT / "docs" / "runbooks" / "MOMOEDGE_BROWSER_COMPANION.md").read_text()
    assert "unavoidable user-controlled browser actions" in runbook
    assert "coverage_eligible=false" in runbook
    assert "never retrospectively eligible" in runbook.replace("\n", " ")
    assert "explicit transport gap" in " ".join(runbook.split())
    assert "never reads, copies" in runbook
    assert "hgplipfmplcbbkjmhaijacaanmiljfdi" in runbook


def test_observer_slice_does_not_import_or_modify_cohort_producer() -> None:
    observer = (ROOT / "engine" / "options_momoedge_browser_adapter.py").read_text()
    receiver = (ROOT / "scripts" / "momoedge_browser_receiver.py").read_text()
    forbidden = (
        "from engine.options_nbbo_cohort",
        "import engine.options_nbbo_cohort",
        "append_capture_receipt(",
        "append_event(",
        "producer_registry[",
        "record_unavailable_cycle(",
    )
    for marker in forbidden:
        assert marker not in observer
        assert marker not in receiver


def test_receiver_malformed_frame_emits_one_protocol_only_bounded_ack(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    private_root = tmp_path / "momoedge_browser_observe_v1"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.momoedge_browser_receiver",
            "--private-root",
            str(private_root),
        ],
        cwd=ROOT,
        input=(10).to_bytes(4, "little") + b"{}",
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 0
    assert completed.stderr == b""
    length = int.from_bytes(completed.stdout[:4], "little")
    assert len(completed.stdout) == 4 + length
    ack = json.loads(completed.stdout[4:])
    assert ack == {
        "accepted": False,
        "coverage_eligible": False,
        "created": False,
        "disposition": "unavailable",
        "journal_sha256": None,
        "raw_sha256": None,
        "reason": "receiver_rejected",
        "schema": "options.momoedge_browser_native_ack/v1",
    }


@pytest.mark.parametrize("isolated", [False, True])
def test_receiver_direct_entry_pins_repo_against_hostile_cwd_and_pythonpath(
    tmp_path: Path, isolated: bool
) -> None:
    hostile = tmp_path / "hostile"
    (hostile / "engine").mkdir(parents=True)
    (hostile / "engine" / "__init__.py").write_text("")
    (hostile / "engine" / "options_momoedge_browser_adapter.py").write_text(
        "raise RuntimeError('hostile import won')\n"
    )
    tmp_path.chmod(0o700)
    private_root = tmp_path / "momoedge_browser_observe_v1"
    command = [sys.executable]
    if isolated:
        command.append("-I")
    command.extend(
        [
            str(ROOT / "scripts" / "momoedge_browser_receiver.py"),
            "--private-root",
            str(private_root),
        ]
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(hostile)
    completed = subprocess.run(
        command,
        cwd=hostile,
        env=environment,
        input=(2).to_bytes(4, "little") + b"{}",
        capture_output=True,
        timeout=10,
        check=True,
    )
    assert completed.stderr == b""
    length = int.from_bytes(completed.stdout[:4], "little")
    ack = json.loads(completed.stdout[4 : 4 + length])
    assert ack["schema"] == "options.momoedge_browser_native_ack/v1"
    assert ack["reason"] == "receiver_rejected"
