"""Tests for .claude/hooks/model_routing_guard.py (PreToolUse model-routing guard).

Runs the hook as a subprocess exactly as the harness does (JSON payload on
stdin), asserting the deny/allow matrix for Agent/Task spawns and Workflow
scripts — including the 2026-07-18 operator re-enable of fable workflow
stages gated on a script-level FABLE-WHY line.

DIRECT-SPAWN CONTRACT (#5823): a model pin is no longer a routing decision. Every
direct Agent/Task spawn must carry a semantic `ROUTE: <name>` line resolved through
.claude/agent-routing.json, plus a structured commission — so the older
"explicit model is sufficient" and "fork inherits the parent" rows of this matrix
are DENIALS by design now, each paired here with the properly-routed form that is
still allowed. The commission builder is imported from
tests/test_agent_routing_control.py rather than re-implemented, so the two suites
cannot drift apart on what a conforming commission looks like.

The hook's contract: exit 0 always; a DENY prints a JSON body with
permissionDecision == "deny"; an ALLOW prints nothing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "model_routing_guard.py"

# reuse the routing-contract commission builder regardless of pytest's import mode
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_agent_routing_control import commission  # noqa: E402

FABLE_WHY = "FABLE-WHY: brainstorm: open-ended judgment steering major downstream work"


def _run(payload: dict) -> tuple[int, dict | None]:
    """Run the hook with *payload* on stdin. Returns (returncode, decision).

    decision is the parsed hookSpecificOutput dict on a deny, else None.

    CLAUDE_PROJECT_DIR is pinned to this checkout because the guard resolves
    .claude/agent-routing.json from it (falling back to cwd); an inherited value
    from an enclosing Claude session would otherwise test another tree's registry.
    """
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=10,
        env=env,
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


def _reason(decision: dict | None) -> str:
    return (decision or {}).get("permissionDecisionReason", "")


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

def test_explicit_sonnet_without_route_denied():
    # Superseded row (#5823): `model: 'sonnet'` + a generic Explore spawn used to be
    # sufficient. A model pin is not a routing decision any more — the ROUTE registry
    # picks both the agent and the model, so an unrouted spawn is denied whatever its
    # tier, and Explore/general-purpose cannot be used as the bypass.
    rc, dec = _run(agent(model="sonnet", subagent_type="Explore"))
    assert rc == 0 and _is_deny(dec)
    assert "requires a semantic `ROUTE: <name>`" in _reason(dec)


def test_explicit_sonnet_allowed_when_routed():
    # The positive counterpart: the same cheap tier IS allowed through its route,
    # with the exact registry agent and a conforming commission.
    rc, dec = _run(
        agent(model="sonnet", subagent_type="scout", prompt=commission("census"))
    )
    assert rc == 0 and not _is_deny(dec), _reason(dec)


def test_default_type_without_model_denied():
    for sub in ("", "claude", "general-purpose", "Explore", "Plan"):
        rc, dec = _run(agent(subagent_type=sub))
        assert rc == 0 and _is_deny(dec), f"expected deny for subagent_type={sub!r}"


def test_fork_denied_as_cost_routing_bypass():
    # Superseded row (#5823): a fork used to be allowed precisely BECAUSE it inherits
    # the parent model. That inheritance is now the objection — a fork carries the
    # frontier context/model past the cost-routing contract, so it is denied
    # deliberately and the denial names the sanctioned replacement.
    rc, dec = _run(agent(subagent_type="fork"))
    assert rc == 0 and _is_deny(dec)
    reason = _reason(dec)
    assert "forked subagents inherit" in reason
    assert "named ROUTE worker" in reason


def test_fork_cannot_be_laundered_through_a_route_marker():
    # Attaching a valid commission does not make a fork a routed worker: the route's
    # agent identity is checked against subagent_type.
    rc, dec = _run(agent(subagent_type="fork", prompt=commission("census")))
    assert rc == 0 and _is_deny(dec)
    assert "requires subagent_type 'scout'" in _reason(dec)


def test_fable_outside_orchestrator_denied():
    rc, dec = _run(agent(model="fable", subagent_type="builder", prompt=FABLE_WHY))
    assert _is_deny(dec)
    rc, dec = _run(agent(model="claude-fable-5", subagent_type="", prompt=FABLE_WHY))
    assert _is_deny(dec)
    # Those two deny on the missing ROUTE. A fully routed non-orchestration spawn
    # still cannot be upgraded to fable — the route's pinned family wins.
    rc, dec = _run(agent(model="fable", subagent_type="builder", prompt=commission("build")))
    assert _is_deny(dec)
    assert "pinned to 'sonnet'" in _reason(dec)


def _orchestration(why: str | None) -> str:
    """A conforming ROUTE orchestration commission with its FABLE-WHY line swapped.

    Built from the sibling suite's commission() so the reason wording can change
    there without silently turning these assertions into no-ops.
    """
    lines = [
        ln for ln in commission("orchestration").splitlines()
        if not ln.upper().startswith("FABLE-WHY")
    ]
    if why is not None:
        lines.insert(1, why)
    return "\n".join(lines)


def test_fable_orchestrator_without_why_denied():
    rc, dec = _run(agent(model="fable", subagent_type="orchestrator"))
    assert _is_deny(dec)
    # Too-short reason fails the >=20 char requirement
    rc, dec = _run(agent(model="fable", subagent_type="orchestrator",
                         prompt="FABLE-WHY: brainstorm: short"))
    assert _is_deny(dec)
    # Both of those now deny on the missing ROUTE. Fully routed, the FABLE-WHY gate
    # itself is the cause — for an absent line and for a too-short reason alike.
    for why in (None, "FABLE-WHY: brainstorm: short"):
        rc, dec = _run(agent(model="fable", subagent_type="orchestrator",
                             prompt=_orchestration(why)))
        assert _is_deny(dec), f"expected deny for why={why!r}"
        assert "missing valid" in _reason(dec)


def test_fable_orchestrator_with_why_but_no_route_denied():
    # Superseded row (#5823): a valid FABLE-WHY line alone used to buy the Fable
    # child. The gated spawn now additionally requires `ROUTE: orchestration` and a
    # commission, so the audit line on its own is not enough.
    rc, dec = _run(agent(model="fable", subagent_type="orchestrator", prompt=FABLE_WHY))
    assert rc == 0 and _is_deny(dec)
    assert "requires a semantic `ROUTE: <name>`" in _reason(dec)


def test_fable_orchestrator_allowed_with_route_and_commission():
    # The positive counterpart: the complete gated form is still permitted, so the
    # 2026-07-18 operator re-enable of the Fable child survives this tightening.
    rc, dec = _run(agent(model="fable", subagent_type="orchestrator",
                         prompt=commission("orchestration")))
    assert rc == 0 and not _is_deny(dec), _reason(dec)


def test_orchestrator_without_explicit_fable_denied():
    rc, dec = _run(agent(model="", subagent_type="orchestrator", prompt=FABLE_WHY))
    assert _is_deny(dec)
    rc, dec = _run(agent(model="opus", subagent_type="orchestrator", prompt=FABLE_WHY))
    assert _is_deny(dec)
    # Routed, the explicit-fable requirement is the actual cause: the orchestrator's
    # opus frontmatter is a fail-safe floor, not permission to run the route.
    for model in ("", "opus"):
        rc, dec = _run(agent(model=model, subagent_type="orchestrator",
                             prompt=commission("orchestration")))
        assert _is_deny(dec), f"expected deny for model={model!r}"
        assert "requires explicit model 'fable'" in _reason(dec)


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
