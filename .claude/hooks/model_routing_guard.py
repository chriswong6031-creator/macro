#!/usr/bin/env python3
"""PreToolUse guard for semantic agent routing, model control, and commission quality.

Direct Agent/Task spawns are type-checked against .claude/agent-routing.json:
ROUTE -> exact custom agent -> allowed model family -> required prompt contract.

This extends the older model-routing guard. Workflow scripts retain the existing
explicit-routing/FABLE-WHY checks because their internal agent() stages are
validated as code, not direct Agent tool calls.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

FABLE_OK_TYPES = {"orchestrator"}
# The line anchors are load-bearing: a mid-sentence prose mention ("we considered
# FABLE-WHY: creative: ...") must never count as the audit line. But the DOCUMENTED
# Workflow form of this line (CLAUDE.md §Model routing, operator re-enable
# 2026-07-18) is a JavaScript comment inside the script:
#     // FABLE-WHY: brainstorm: <specific reason>
# so a bare `^FABLE-WHY` anchor can never match it and would deny every
# fable-routed workflow stage. Leading comment markers/indentation are therefore
# allowed before the label — and nothing else.
FABLE_WHY_RE = re.compile(
    r"(?mi)^[ \t/#*\-]*FABLE-WHY\s*:\s*(orchestration|brainstorm|creative)\s*:\s*\S.{19,}$"
)
ROUTE_RE = re.compile(r"(?mi)^ROUTE\s*:\s*([a-z][a-z0-9_-]*)\s*$")
HEADER_RE = re.compile(r"(?mi)^\s*(?:#{1,6}\s*)?([A-Z][A-Z0-9 /_-]{1,48})\s*:\s*(.*)$")


def _project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".").resolve()


def _load_registry() -> dict:
    path = _project_dir() / ".claude" / "agent-routing.json"
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("routes"), dict):
        raise ValueError("registry has no routes object")
    return data


def _deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    raise SystemExit(0)


def _allow() -> None:
    raise SystemExit(0)


def _model_family(model: str) -> str:
    m = (model or "").strip().lower()
    for fam in ("fable", "opus", "sonnet", "haiku"):
        if fam in m:
            return fam
    return m


def _frontmatter_model(subagent_type: str) -> str:
    if not subagent_type or not re.fullmatch(r"[\w-]+", subagent_type):
        return ""
    project = _project_dir()
    candidates = (
        project / ".claude" / "agents" / f"{subagent_type}.md",
        Path.home() / ".claude" / "agents" / f"{subagent_type}.md",
    )
    for path in candidates:
        try:
            if not path.is_file():
                continue
            head = path.read_text(encoding="utf-8", errors="replace")[:4096]
            m = re.search(r"(?mi)^\s*model\s*:\s*(\S+)", head)
            if m:
                return _model_family(m.group(1).strip().strip("'\""))
        except OSError:
            continue
    return ""


def _sections(text: str) -> dict[str, str]:
    matches = list(HEADER_RE.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = re.sub(r"\s+", " ", m.group(1).strip().upper())
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        inline = m.group(2).strip()
        tail = text[start:end].strip()
        content = "\n".join(x for x in (inline, tail) if x).strip()
        out[name] = content
    return out


def _validate_commission(prompt: str, spec: dict, route: str) -> None:
    sections = _sections(prompt)
    required = spec.get("required_prompt_sections") or []
    missing = [name for name in required if not sections.get(name, "").strip()]
    if missing:
        _deny(
            f"Blocked ROUTE {route}: commission is missing required section(s): "
            + ", ".join(missing)
            + ". Use exact `SECTION:` labels. The routing guard rejects under-specified "
              "worker prompts so cheap agents do not have to infer the mission."
        )

    mission = sections.get("MISSION", "").strip()
    if mission and len(mission) < 20:
        _deny(
            f"Blocked ROUTE {route}: MISSION is too vague ({len(mission)} chars). "
            "State one bounded objective with enough detail for a fresh worker to execute."
        )

    gates = sections.get("NOT DONE UNLESS", "").strip()
    if gates and len(gates) < 20:
        _deny(
            f"Blocked ROUTE {route}: NOT DONE UNLESS is too weak. "
            "Provide observable acceptance gates, not a generic completion phrase."
        )

    # Ensure the parent commission actually asks for the standardized return
    # packet that SubagentStop will validate.
    return_required = spec.get("required_return_sections") or []
    if return_required:
        ret = sections.get("RETURN", "").upper()
        absent = [name for name in return_required if name not in ret]
        if absent:
            _deny(
                f"Blocked ROUTE {route}: RETURN must request the standard evidence packet "
                f"labels {', '.join(return_required)}; missing {', '.join(absent)}."
            )


def _route_direct_spawn(ti: dict, tool: str, registry: dict) -> None:
    prompt = str(ti.get("prompt") or "")
    sub = str(ti.get("subagent_type") or ti.get("agent_type") or "").strip()
    explicit_model = str(ti.get("model") or "").strip()
    explicit_family = _model_family(explicit_model)

    route_match = ROUTE_RE.search(prompt)
    if not route_match:
        if sub == "fork":
            _deny(
                "Blocked: forked subagents inherit the parent context/model and bypass the "
                "cost-routing contract. Use a named ROUTE worker. If frontier context is "
                "truly required, keep the judgment in the main loop or use the gated "
                "ROUTE orchestration Fable child."
            )
        _deny(
            "Blocked: every direct Agent/Task spawn requires a semantic `ROUTE: <name>` "
            "line. Fable chooses the work class; .claude/agent-routing.json chooses the "
            "agent/model. Do not use generic/general-purpose/Explore/Plan as a routing bypass."
        )

    route = route_match.group(1).lower()
    spec = registry["routes"].get(route)
    if not spec:
        _deny(
            f"Blocked: unknown ROUTE {route!r}. Allowed routes: "
            + ", ".join(sorted(registry["routes"]))
        )

    if spec.get("main_loop_only"):
        _deny(
            f"Blocked: ROUTE {route} is main-loop-only. This work is final judgment/"
            "adjudication and must remain with Fable rather than being delegated."
        )

    expected_agent = str(spec.get("agent") or "")
    expected_model = _model_family(str(spec.get("model") or ""))

    if sub != expected_agent:
        _deny(
            f"Blocked ROUTE {route}: requires subagent_type {expected_agent!r}, got "
            f"{sub or 'default'!r}. Purpose: {spec.get('purpose', '')}"
        )

    if route == "orchestration":
        if explicit_family != "fable":
            _deny(
                "Blocked ROUTE orchestration: orchestrator requires explicit model 'fable'. "
                "Its frontmatter Opus model is a fail-safe floor, not permission to run the route."
            )
        if not FABLE_WHY_RE.search(prompt):
            _deny(
                "Blocked ROUTE orchestration: missing valid "
                "`FABLE-WHY: <orchestration|brainstorm|creative>: <specific reason>` "
                "(specific reason must be at least 20 characters)."
            )
    else:
        # Named custom agents pin their model. If a caller redundantly supplies a model,
        # it may only match the registry; an upgrade/downgrade is a hard failure.
        if explicit_model and explicit_family != expected_model:
            _deny(
                f"Blocked ROUTE {route}: model override {explicit_model!r} resolves to "
                f"{explicit_family!r}, but this route is pinned to {expected_model!r}. "
                "Use the canonical custom agent without changing its model."
            )
        pinned = _frontmatter_model(expected_agent)
        if pinned != expected_model:
            _deny(
                f"Blocked ROUTE {route}: routing registry requires {expected_model!r} but "
                f".claude/agents/{expected_agent}.md pins {pinned or 'no model'!r}. "
                "The control plane is internally inconsistent; fix the registry/agent pair "
                "instead of spawning."
            )

    _validate_commission(prompt, spec, route)


def _validate_workflow(script: str) -> None:
    """Preserve the repo's existing Workflow cost guard."""
    script_has_fable_why = bool(FABLE_WHY_RE.search(script))

    if re.search(r"model\s*:\s*['\"`][^'\"`]*fable[^'\"`]*['\"`]", script, re.I):
        if not script_has_fable_why:
            _deny(
                "Blocked: workflow routes a stage to Fable without a script-level "
                "FABLE-WHY line. Reserve Fable for judge/synthesis stages, never bulk fan-out."
            )
    if re.search(r"agentType\s*:\s*['\"`]orchestrator['\"`]", script, re.I):
        if not script_has_fable_why:
            _deny(
                "Blocked: workflow uses agentType 'orchestrator' without a script-level "
                "FABLE-WHY line."
            )
    if "agent(" in script and "model" not in script and "agentType" not in script:
        _deny(
            "Blocked: workflow calls agent() with no model:/agentType routing; stages "
            "would inherit the session model."
        )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # Existing hook convention: malformed hook input should not brick Claude.
        return

    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        return

    if tool in ("Agent", "Task"):
        try:
            registry = _load_registry()
        except Exception as exc:
            _deny(
                "Blocked: agent routing registry could not be loaded; fail-closed to prevent "
                f"uncontrolled model spend ({type(exc).__name__}: {exc})."
            )
        _route_direct_spawn(ti, tool, registry)
        return

    if tool == "Workflow":
        script = str(ti.get("script") or "")
        if not script:
            sp = str(ti.get("scriptPath") or "")
            if sp and os.path.isfile(sp):
                try:
                    script = Path(sp).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return
            else:
                return  # predefined workflow; versioned script is vetted in-repo
        _validate_workflow(script)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Preserve prior fail-open behavior only for truly unexpected hook failures.
        sys.exit(0)
