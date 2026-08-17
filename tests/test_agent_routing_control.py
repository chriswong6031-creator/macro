import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / ".claude" / "hooks" / "model_routing_guard.py"
RETURN_GUARD = ROOT / ".claude" / "hooks" / "agent_return_guard.py"
CONTEXT = ROOT / ".claude" / "hooks" / "agent_routing_context.py"
REGISTRY = ROOT / ".claude" / "agent-routing.json"


def run_hook(script: Path, payload: dict):
    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def commission(route: str, *, return_labels=True):
    base = {
        "census": [
            ("MISSION", "Map the complete current ingestion path for the commissioned subsystem."),
            ("WHY", "Fable needs verified current state before freezing the next architecture."),
            ("SCOPE", "Only the named subsystem and its direct contracts."),
            ("OUT OF SCOPE", "No implementation, redesign, or adjacent recommendations."),
            ("QUESTIONS", "Trace sources, transforms, consumers, and unresolved dead paths."),
            ("NOT DONE UNLESS", "Every material pipeline claim has exact file:line evidence and unknowns are explicit."),
            ("EVIDENCE REQUIRED", "Exact file:line receipts and commands used to establish coverage."),
        ],
        "build": [
            ("MISSION", "Implement the frozen parser contract and its regression tests exactly as specified."),
            ("WHY", "This packet realizes one frozen vertical slice of the parent architecture."),
            ("SCOPE", "Parser implementation and directly associated tests only."),
            ("OUT OF SCOPE", "No redesign, dependency migration, or unrelated cleanup."),
            ("FROZEN SPEC", "Preserve the existing public interface and add only the requested field handling."),
            ("OWNED FILES", "engine/example.py and tests/test_example.py."),
            ("TESTS", "Run the targeted parser tests and any directly affected contract tests."),
            ("NOT DONE UNLESS", "All specified behavior exists and the targeted test receipts are green."),
        ],
        "orchestration": [
            ("MISSION", "Design the bounded multi-wave architecture for this irreversible cross-repo program."),
            ("WHY", "The parent requires frontier judgment across conflicting architectural constraints."),
            ("SCOPE", "Architecture and wave decomposition only."),
            ("OUT OF SCOPE", "No mechanical census, implementation, or bulk verification."),
            ("NOT DONE UNLESS", "The architecture resolves the named tradeoffs and has explicit acceptance gates."),
        ],
    }[route]
    lines = [f"ROUTE: {route}"]
    if route == "orchestration":
        lines += [
            "FABLE-WHY: orchestration: This program has irreversible cross-repo decisions that ordinary draft-and-review cannot recover."
        ]
    for key, value in base:
        lines += ["", f"{key}:", value]
    ret = "STATUS / RESULT / EVIDENCE / GAPS / DEVIATIONS" if return_labels else "Give a useful answer."
    lines += ["", "RETURN:", ret]
    return "\n".join(lines)


def direct_payload(sub: str, prompt: str, model=None):
    ti = {"subagent_type": sub, "prompt": prompt}
    if model is not None:
        ti["model"] = model
    return {"tool_name": "Agent", "tool_input": ti}


def denial(cp):
    if not cp.stdout.strip():
        return ""
    data = json.loads(cp.stdout)
    return data["hookSpecificOutput"]["permissionDecisionReason"]


def test_valid_census_uses_scout_sonnet_pin():
    cp = run_hook(GUARD, direct_payload("scout", commission("census")))
    assert cp.returncode == 0
    assert cp.stdout == ""


def test_wrong_agent_for_route_is_denied():
    cp = run_hook(GUARD, direct_payload("builder", commission("census")))
    assert "requires subagent_type 'scout'" in denial(cp)


def test_wrong_model_override_is_denied():
    cp = run_hook(GUARD, direct_payload("scout", commission("census"), model="opus"))
    assert "pinned to 'sonnet'" in denial(cp)


def test_matching_redundant_model_override_is_allowed():
    cp = run_hook(GUARD, direct_payload("scout", commission("census"), model="sonnet"))
    assert cp.stdout == ""


def test_missing_route_is_denied():
    cp = run_hook(
        GUARD,
        direct_payload("scout", "MISSION:\nMap the repository carefully and return evidence."),
    )
    assert "requires a semantic `ROUTE: <name>`" in denial(cp)


def test_fork_is_denied_as_cost_bypass():
    cp = run_hook(GUARD, direct_payload("fork", "Investigate the repository."))
    assert "forked subagents inherit" in denial(cp)


def test_judgment_cannot_be_spawned():
    prompt = "ROUTE: judgment\nMISSION:\nMake the final architecture decision for this program."
    cp = run_hook(GUARD, direct_payload("analyst", prompt, model="fable"))
    assert "main-loop-only" in denial(cp)


def test_valid_fable_orchestration_requires_explicit_fable():
    cp = run_hook(
        GUARD,
        direct_payload("orchestrator", commission("orchestration"), model="fable"),
    )
    assert cp.stdout == ""


def test_fable_orchestration_without_why_is_denied():
    prompt = commission("orchestration").replace(
        "FABLE-WHY: orchestration: This program has irreversible cross-repo decisions that ordinary draft-and-review cannot recover.\n",
        "",
    )
    cp = run_hook(GUARD, direct_payload("orchestrator", prompt, model="fable"))
    assert "missing valid" in denial(cp)


def _opus_orchestration(with_skill=True):
    # The Opus seat (operator 2026-08-17) spends no fable, so it carries no
    # FABLE-WHY; what it must carry instead is the fable-mode skill directive.
    prompt = commission("orchestration").replace(
        "FABLE-WHY: orchestration: This program has irreversible cross-repo decisions that ordinary draft-and-review cannot recover.\n",
        "",
    )
    if with_skill:
        prompt += "\n\nInvoke the fable-mode skill (Skill tool) before substantive work."
    return prompt


def test_opus_orchestration_with_fable_mode_skill_is_allowed():
    cp = run_hook(GUARD, direct_payload("orchestrator", _opus_orchestration(), model="opus"))
    assert cp.returncode == 0
    assert cp.stdout == ""


def test_opus_orchestration_without_fable_mode_skill_is_denied():
    cp = run_hook(
        GUARD, direct_payload("orchestrator", _opus_orchestration(with_skill=False), model="opus")
    )
    assert "fable-mode" in denial(cp)


def test_orchestration_on_other_models_is_still_denied():
    cp = run_hook(GUARD, direct_payload("orchestrator", _opus_orchestration(), model="sonnet"))
    assert "explicit model 'fable'" in denial(cp)


def test_under_specified_commission_is_denied():
    prompt = commission("census").replace(
        "\nQUESTIONS:\nTrace sources, transforms, consumers, and unresolved dead paths.", ""
    )
    cp = run_hook(GUARD, direct_payload("scout", prompt))
    assert "QUESTIONS" in denial(cp)


def test_return_instruction_must_request_standard_packet():
    cp = run_hook(
        GUARD, direct_payload("scout", commission("census", return_labels=False))
    )
    assert "RETURN must request" in denial(cp)


def test_workflow_without_routing_is_denied():
    payload = {
        "tool_name": "Workflow",
        "tool_input": {"script": "const x = await agent('do the thing', {label:'x'})"},
    }
    cp = run_hook(GUARD, payload)
    assert "no model:/agentType routing" in denial(cp)


def test_workflow_fable_requires_audit_line():
    payload = {
        "tool_name": "Workflow",
        "tool_input": {"script": "const x = await agent('judge', {model:'fable'})"},
    }
    cp = run_hook(GUARD, payload)
    assert "without a script-level FABLE-WHY" in denial(cp)


def test_worker_return_contract_accepts_complete_packet():
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "scout",
        "stop_hook_active": False,
        "last_assistant_message": (
            "STATUS: PASS\n"
            "RESULT:\nMapped the full current pipeline and its direct consumer.\n"
            "EVIDENCE:\nengine/x.py:10-41; config/y.yml:3-8.\n"
            "GAPS:\nnone\n"
            "DEVIATIONS:\nnone\n"
        ),
    }
    cp = run_hook(RETURN_GUARD, payload)
    assert cp.returncode == 0


def test_worker_return_contract_blocks_missing_evidence():
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "researcher",
        "stop_hook_active": False,
        "last_assistant_message": (
            "STATUS: PASS\nRESULT:\nThe research is complete.\nGAPS:\nnone\nDEVIATIONS:\nnone\n"
        ),
    }
    cp = run_hook(RETURN_GUARD, payload)
    assert cp.returncode == 2
    assert "missing/empty EVIDENCE" in cp.stderr


def test_worker_return_contract_blocks_none_evidence():
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "reviewer",
        "stop_hook_active": False,
        "last_assistant_message": (
            "STATUS: PASS\nRESULT:\nNo material findings found.\nEVIDENCE:\nnone\n"
            "GAPS:\nnone\nDEVIATIONS:\nnone\n"
        ),
    }
    cp = run_hook(RETURN_GUARD, payload)
    assert cp.returncode == 2
    assert "EVIDENCE cannot be empty" in cp.stderr


def test_worker_return_contract_one_retry_only():
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "scout",
        "stop_hook_active": True,
        "last_assistant_message": "I think it is done.",
    }
    cp = run_hook(RETURN_GUARD, payload)
    assert cp.returncode == 0


def test_registry_agent_frontmatter_models_are_consistent():
    registry = json.loads(REGISTRY.read_text())
    for route, spec in registry["routes"].items():
        agent = spec.get("agent")
        if not agent or route == "orchestration":
            continue
        text = (ROOT / ".claude" / "agents" / f"{agent}.md").read_text()
        m = re.search(r"(?mi)^model:\s*(\S+)", text)
        assert m, (route, agent)
        assert m.group(1).strip("'\"").lower() == spec["model"], (route, agent)


def test_settings_wire_all_three_control_hooks():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    assert "SubagentStop" in settings["hooks"]
    text = json.dumps(settings)
    assert "model_routing_guard.py" in text
    assert "agent_return_guard.py" in text
    assert "agent_routing_context.py" in text


def test_context_hook_exposes_compact_route_map():
    cp = run_hook(CONTEXT, {})
    assert cp.returncode == 0
    assert "census->scout(sonnet)" in cp.stdout
    assert "judgment->Fable main loop" in cp.stdout
    assert "ROUTE orchestration" in cp.stdout


def test_registry_cost_tiers_cannot_silently_drift():
    registry = json.loads(REGISTRY.read_text())
    routes = registry["routes"]
    assert routes["extract"]["model"] == "haiku"
    # Build returned to Sonnet by standing operator order 2026-08-17, reversing the
    # 2026-07-21 "Opus builds code" order. The design lane (2026-07-18) and the
    # review lane did NOT reverse — they stay Opus, asserted as a closed set below.
    assert routes["build"]["model"] == "sonnet"
    assert {r for r, s in routes.items() if s["model"] == "sonnet"} == {
        "census", "research", "draft", "build"
    }
    assert {r for r, s in routes.items() if s["model"] == "opus"} == {
        "analysis", "debug", "review", "design"
    }
    assert {r for r, s in routes.items() if s["model"] == "fable"} == {
        "judgment", "orchestration"
    }
    assert routes["judgment"]["main_loop_only"] is True
    assert routes["orchestration"]["requires_fable_why"] is True
    # Opus may hold the orchestrator seat only under the fable-mode doctrine
    # (operator 2026-08-17); the skill it names must actually exist.
    assert routes["orchestration"]["opus_alternative"] == {
        "model": "opus",
        "requires_skill": "fable-mode",
    }
    assert (ROOT / ".claude" / "skills" / "fable-mode" / "SKILL.md").is_file()


def test_read_only_routes_are_not_pointed_at_authoring_agents():
    # A cheap MODEL is not a cheap AGENT IDENTITY. `build` is legitimately Sonnet
    # (operator 2026-08-17), so the tier alone no longer separates read-only work
    # from authoring work — the agent identity does. The extraction/census/research
    # routes must never resolve to the builder or designer, whose contracts assume
    # an owned-files write mandate, and the build route must keep its own agent.
    registry = json.loads(REGISTRY.read_text())
    for route in ("extract", "census", "research"):
        assert registry["routes"][route]["agent"] not in {"builder", "designer"}
        assert registry["routes"][route]["model"] in {"haiku", "sonnet"}
    assert registry["routes"]["build"]["agent"] == "builder"
    assert registry["routes"]["design"]["agent"] == "designer"
