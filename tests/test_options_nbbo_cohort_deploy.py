from __future__ import annotations

import plistlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLIST = ROOT / "ops" / "launchd" / "com.mastermind.optionsnbbocohort.plist"
RUNNER = ROOT / "ops" / "launchd" / "run_options_nbbo_cohort_loop.sh"
RUNBOOK = ROOT / "docs" / "runbooks" / "OPTIONS_NBBO_COHORT.md"


def test_launchd_lane_is_independent_five_minute_and_private() -> None:
    with PLIST.open("rb") as handle:
        payload = plistlib.load(handle)
    assert payload["Label"] == "com.mastermind.optionsnbbocohort"
    assert payload["StartInterval"] == 300
    assert payload["KeepAlive"] is False
    assert payload["WorkingDirectory"] == "/Users/chriswong/options-nbbo-ops-wt"
    args = payload["ProgramArguments"]
    assert args == [
        "/bin/sh",
        "/Users/chriswong/options-nbbo-ops-wt/ops/launchd/run_options_nbbo_cohort_loop.sh",
    ]
    env = payload["EnvironmentVariables"]
    assert env["OPTIONS_NBBO_COHORT_PRIVATE_ROOT"].startswith(
        "/Users/chriswong/.mastermind_private/"
    )
    assert not any("TOKEN" in key or "SECRET" in key or "KEY" in key for key in env)
    assert "prophetmarks" not in PLIST.read_text().lower()


def test_runner_records_honest_unavailability_before_expiry_and_advance() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "export TZ=America/New_York" in source
    assert "WINDOW_OPEN_MINUTES=565" in source
    assert "WINDOW_CLOSE_MINUTES=965" in source
    operations = [
        "--initialize",
        "--record-unavailable-cycle",
        "--expire-open",
        "--advance",
    ]
    positions = [source.index(operation) for operation in operations]
    assert positions == sorted(positions)
    assert "--append-event" not in source
    assert "--append-capture-receipt" not in source
    assert "site/" not in source
    assert 'EXPECTED_REPO_ROOT="/Users/chriswong/options-nbbo-ops-wt"' in source
    assert "status --porcelain" in source
    assert "checkout_sha=" in source
    assert "runner_sha256=" in source
    assert "schema_sha256=" in source


def test_runbook_pins_basis_privacy_and_no_fabricated_abstention() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for required in (
        "first valid OPRA NBBO ask",
        "first valid bid",
        "15:55",
        "not a time-to-first-quote cap",
        "$0.65 fee per side",
        "Raw source and competitor bytes",
        "unavailable",
        "do not cover a slot",
        "UNCOVERED_CAPTURE_SESSION",
        "zero covered sessions and zero eligible outcomes",
        "event producer and every successful capture",
        "unarmed",
        "/Users/chriswong/options-nbbo-ops-wt",
        "merge-base --is-ancestor",
        "shasum -a 256",
    ):
        assert required in text
    assert (
        "never\ninstall this lane into the shared `/Users/chriswong/flow-ops-wt`"
        in text
    )


def test_production_source_pins_are_unarmed_in_code() -> None:
    from engine import options_nbbo_cohort as cohort

    for registry in (
        cohort.DEFAULT_EVENT_PRODUCER_REGISTRY,
        cohort.DEFAULT_CAPTURE_PRODUCER_REGISTRY,
    ):
        assert registry
        assert all(row["armed"] is False for row in registry.values())
        assert all(row["source_schema"] is None for row in registry.values())


def test_dag_registers_only_the_host_private_lane() -> None:
    dag = yaml.safe_load((ROOT / "config" / "dag.yml").read_text(encoding="utf-8"))
    rows = [
        row
        for row in dag["modules"]
        if row.get("module") == "scripts.capture_options_nbbo_cohort"
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["impure"] is True
    assert row["needs_secrets"] is False
    assert row["event_driven"] is True
    assert all(
        path.startswith("/Users/chriswong/.mastermind_private/")
        for path in row["writes"]
    )
    assert not any("site/" in path or "data/" in path for path in row["writes"])
    writes = set(row["writes"])
    for required_suffix in (
        "events.jsonl",
        "captures.jsonl",
        "event_evidence/",
        "capture_evidence/",
        ".staging/",
        ".store.lock",
    ):
        assert any(path.endswith(required_suffix) for path in writes)
