from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKSTREAM = ROOT / "agentos/workstreams/WS-SOL-CAPABILITY-FABRIC.md"
DECISION = ROOT / "agentos/decisions/DEC-SOL-CAPABILITY-FABRIC-FEDERATED-TYPED-CONTROL.md"
DISCOVERY = ROOT / "agentos/discoveries/DSC-SCF-DIGEST-ONLY-PREPARED-ACTION-REQUIRES-HIDDEN-STORE.md"
HANDOFF = ROOT / "agentos/handoffs/SOL-CAPABILITY-FABRIC-2026-08-30-f0-protected-gh0-next.md"


def _record(path: Path) -> tuple[dict[str, Any], str]:
    assert path.is_file(), f"missing durable Agent OS record: {path.relative_to(ROOT)}"
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) == 3 and not parts[0].strip(), f"invalid frontmatter: {path}"
    data = yaml.safe_load(parts[1])
    assert isinstance(data, dict), f"frontmatter must be a mapping: {path}"
    return data, parts[2]


def test_sol_capability_fabric_closeout_records_exist() -> None:
    for path in (WORKSTREAM, DECISION, DISCOVERY, HANDOFF):
        assert path.is_file()


def test_workstream_preserves_program_state_and_exact_next_operation() -> None:
    data, body = _record(WORKSTREAM)
    assert data["key"] == "SOL-CAPABILITY-FABRIC"
    assert data["status"] == "active"
    assert data["program"] == "project-active-build-control"
    assert data["owner"] == "ceo-sol"
    assert set(data["repos"]) == {"macro", "mastermind"}
    assert "created" not in data and "updated" not in data

    waves = {wave["id"]: wave for wave in data["waves"]}
    assert waves["SCF-F0"]["status"] == "done"
    assert waves["SCF-F0"]["pr"] == 283
    assert waves["SCF-GH0"]["status"] == "todo"
    assert waves["SCF-CAP1"]["status"] == "todo"
    for wave_id in (
        "SCF-GH1",
        "SCF-GH2",
        "SCF-RUN1",
        "SCF-S1",
        "SCF-E1",
        "SCF-SURF1",
        "SCF-SURF2",
        "SCF-SURF3",
        "SCF-FLEET1",
        "SCF-FLEET2",
        "SCF-OPS1",
        "SCF-OPS2",
        "SCF-A3",
        "SCF-OBS1",
        "SCF-UI1",
        "SCF-CANARY1",
        "SCF-CUTOVER",
    ):
        assert wave_id in waves

    next_action = data["next_action"]
    for required in (
        "mastermind-sol-capability-fabric-gh0-20260830-sol-001",
        "COGNITION_ROUTE: CHAT_PRO_DEFAULT",
        "PREFERRED_AVENUE: CTO Sol",
        "WHY NOT FABLE",
        "RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE",
        "PLACEMENT_STATE: WAITING_CAPACITY / needs_placement",
    ):
        assert required in next_action
    assert "RECEIVER_MODE: OPEN_PICKUP" not in next_action
    assert "No child inherits START" in body
    assert "No worker-facing commission" in body


def test_federated_control_decision_is_durable_and_rejects_super_mcp() -> None:
    data, body = _record(DECISION)
    assert data["key"] == "SOL-CAPABILITY-FABRIC-FEDERATED-TYPED-CONTROL"
    assert "One Experience, Federated Authority" in data["answer"]
    assert len(data["alternatives"]) >= 3
    assert "WS:SOL-CAPABILITY-FABRIC" in data["affects"]
    assert data["decided_by"] == "ceo-sol"
    assert data["decided_at"] == "2026-08-30"
    assert "super-MCP" in body
    assert "Executive OS" in body
    assert "Agent OS" in body
    assert "RuntimeBinding" in body
    assert "Capacity" in body


def test_digest_only_prepared_action_defect_is_recorded() -> None:
    data, body = _record(DISCOVERY)
    assert data["key"] == "SCF-DIGEST-ONLY-PREPARED-ACTION-REQUIRES-HIDDEN-STORE"
    assert "digest" in data["claim"].lower()
    assert "hidden" in data["claim"].lower()
    assert "prepared_token" in data["so_what"]
    assert data["verified_at"] == "2026-08-30"
    assert "#283" in data["verified_by"]
    assert "git -C Mastermind show" in data["falsifier"]
    assert "authenticated self-contained expiring token" in body
    assert "no durable prepared-action store" in body


def test_handoff_carries_exact_merge_proof_limits_and_gh0_continuation() -> None:
    data, body = _record(HANDOFF)
    assert data["workstream"] == "WS:SOL-CAPABILITY-FABRIC"
    assert data["session"] == "sol/sol-capability-fabric-agentos-closeout-20260830"
    assert data["model"] == "codex"
    assert 283 in data["prs"]
    assert data["ended_because"] == "complete"

    verified = "\n".join(
        f"{item['claim']}\n{item['command']}\n{item['result']}" for item in data["verified"]
    )
    for required in (
        "98bc7a71dcd70947c7a18eb5af7493a2f62a2571",
        "33319728861",
        "33319727198",
        "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED",
    ):
        assert required in verified

    unverified = "\n".join(
        f"{item['claim']}\n{item['what_would_verify']}" for item in data["unverified"]
    )
    assert "GH0" in unverified
    assert "live" in unverified.lower()

    next_actions = "\n".join(str(item) for item in data["next_actions"])
    assert "mastermind-sol-capability-fabric-gh0-20260830-sol-001" in next_actions
    assert "WAITING_CAPACITY / needs_placement" in next_actions
    assert "no child START" in body
    assert "PARTIAL_CLOSEOUT" in body


def test_closeout_does_not_overclaim_runtime_or_assignment() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (WORKSTREAM, DECISION, DISCOVERY, HANDOFF))
    assert "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED" in combined
    assert "RECEIVER_MODE: OPEN_PICKUP" not in combined
    assert "PLACEMENT_STATE: WAITING_CAPACITY / needs_placement" in combined
    assert "No worker-facing commission or receiver-specific watcher is authorized before placement" in combined
    assert "SCF is PROVEN_LIVE" not in combined
