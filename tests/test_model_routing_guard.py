"""Tests for .claude/hooks/model_routing_guard.py (PreToolUse model-routing guard).

Runs the hook as a subprocess exactly as the harness does (JSON payload on
stdin), asserting the deny/allow matrix for Agent/Task spawns and Workflow
scripts — including the 2026-07-18 operator re-enable of fable workflow
stages gated on a script-level FABLE-WHY line.

The hook's contract: exit 0 always; a DENY prints a JSON body with
permissionDecision == "deny"; an ALLOW prints nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "model_routing_guard.py"

FABLE_WHY = "FABLE-WHY: brainstorm: open-ended judgment steering major downstream work"


def _run(payload: dict) -> tuple[int, dict | None]:
    """Run the hook with *payload* on stdin. Returns (returncode, decision).

    decision is the parsed hookSpecificOutput dict on a deny, else None.
    """
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=10,
    )
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if not out:
        return proc.returncode, None
    try:
        return proc.returncode, json.loads(out).get("hookSpecificOutput")
    except Exception:
        return proc.returncode, None


def _is_deny(decision: dict | None) -> bool:
    return bool(decision) and decision.get("permissionDecision") == "deny"


def agent(model="", subagent_type="", prompt="do the thing"):
    return {
        "tool_name": "Agent",
        "tool_input": {"model": model, "subagent_type": subagent_type, "prompt": prompt},
    }


def workflow(script):
    return {"tool_name": "Workflow", "tool_input": {"script": script}}


# ---------------------------------------------------------------------------
# Hook contract
# ---------------------------------------------------------------------------

def test_always_exits_zero_on_garbage():
    proc = subprocess.run(
        [sys.executable, str(HOOK)], input=b"not json", capture_output=True, timeout=10
    )
    assert proc.returncode == 0


def test_unrelated_tool_allowed():
    rc, dec = _run({"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert rc == 0 and not _is_deny(dec)


# ---------------------------------------------------------------------------
# Agent/Task spawns
# ---------------------------------------------------------------------------

def test_explicit_sonnet_allowed():
    rc, dec = _run(agent(model="sonnet", subagent_type="Explore"))
    assert rc == 0 and not _is_deny(dec)


def test_default_type_without_model_denied():
    for sub in ("", "claude", "general-purpose", "Explore", "Plan"):
        rc, dec = _run(agent(subagent_type=sub))
        assert rc == 0 and _is_deny(dec), f"expected deny for subagent_type={sub!r}"


def test_fork_inherits_allowed():
    rc, dec = _run(agent(subagent_type="fork"))
    assert rc == 0 and not _is_deny(dec)


def test_fable_outside_orchestrator_denied():
    rc, dec = _run(agent(model="fable", subagent_type="builder", prompt=FABLE_WHY))
    assert _is_deny(dec)
    rc, dec = _run(agent(model="claude-fable-5", subagent_type="", prompt=FABLE_WHY))
    assert _is_deny(dec)


def test_fable_orchestrator_without_why_denied():
    rc, dec = _run(agent(model="fable", subagent_type="orchestrator"))
    assert _is_deny(dec)
    # Too-short reason fails the >=20 char requirement
    rc, dec = _run(agent(model="fable", subagent_type="orchestrator",
                         prompt="FABLE-WHY: brainstorm: short"))
    assert _is_deny(dec)


def test_fable_orchestrator_with_why_allowed():
    rc, dec = _run(agent(model="fable", subagent_type="orchestrator", prompt=FABLE_WHY))
    assert rc == 0 and not _is_deny(dec)


def test_orchestrator_without_explicit_fable_denied():
    rc, dec = _run(agent(model="", subagent_type="orchestrator", prompt=FABLE_WHY))
    assert _is_deny(dec)
    rc, dec = _run(agent(model="opus", subagent_type="orchestrator", prompt=FABLE_WHY))
    assert _is_deny(dec)


# ---------------------------------------------------------------------------
# Workflow scripts
# ---------------------------------------------------------------------------

ROUTED = "await agent('build it', {model: 'sonnet'})"
UNROUTED = "await agent('build it')"
FABLE_STAGE = "await agent('adjudicate the panel', {model: 'fable', effort: 'high'})"
ORCH_STAGE = "await agent('steer the program', {agentType: 'orchestrator'})"


def test_workflow_routed_allowed():
    rc, dec = _run(workflow(f"export const meta = {{}}\n{ROUTED}"))
    assert rc == 0 and not _is_deny(dec)


def test_workflow_unrouted_denied():
    rc, dec = _run(workflow(f"export const meta = {{}}\n{UNROUTED}"))
    assert _is_deny(dec)


def test_workflow_fable_without_why_denied():
    rc, dec = _run(workflow(f"export const meta = {{}}\n{ROUTED}\n{FABLE_STAGE}"))
    assert _is_deny(dec)
    assert "FABLE-WHY" in (dec or {}).get("permissionDecisionReason", "")


def test_workflow_fable_with_why_allowed():
    script = f"export const meta = {{}}\n// {FABLE_WHY}\n{ROUTED}\n{FABLE_STAGE}"
    rc, dec = _run(workflow(script))
    assert rc == 0 and not _is_deny(dec)


def test_workflow_orchestrator_without_why_denied():
    rc, dec = _run(workflow(f"export const meta = {{}}\n{ROUTED}\n{ORCH_STAGE}"))
    assert _is_deny(dec)


def test_workflow_orchestrator_with_why_allowed():
    script = f"export const meta = {{}}\n// {FABLE_WHY}\n{ROUTED}\n{ORCH_STAGE}"
    rc, dec = _run(workflow(script))
    assert rc == 0 and not _is_deny(dec)


def test_workflow_short_why_still_denied():
    script = f"export const meta = {{}}\n// FABLE-WHY: creative: nope\n{FABLE_STAGE}"
    rc, dec = _run(workflow(script))
    assert _is_deny(dec)


def test_workflow_why_length_boundary():
    # FABLE_WHY_RE requires \S.{19,} — a 19-char reason fails, 20 passes.
    r19 = "a" * 19
    r20 = "a" * 20
    denied = f"export const meta = {{}}\n// FABLE-WHY: creative: {r19}\n{FABLE_STAGE}"
    allowed = f"export const meta = {{}}\n// FABLE-WHY: creative: {r20}\n{FABLE_STAGE}"
    rc, dec = _run(workflow(denied))
    assert _is_deny(dec), "19-char reason must be denied"
    rc, dec = _run(workflow(allowed))
    assert rc == 0 and not _is_deny(dec), "20-char reason must pass"


def test_workflow_named_predefined_allowed():
    rc, dec = _run({"tool_name": "Workflow", "tool_input": {"name": "review-changes"}})
    assert rc == 0 and not _is_deny(dec)
