#!/usr/bin/env python3
"""PreToolUse guard: enforce CLAUDE.md §Model routing on Agent/Task/Workflow spawns.

Deny only the clear violations (missing model on default agent types, fable
spawns outside the orchestrator+FABLE-WHY gate, fable-pinned agent frontmatter
outside that gate, workflow scripts with un-routed agent() calls, and
fable-routed workflow stages missing a script-level FABLE-WHY line). Fail
OPEN on anything ambiguous or on internal error — a guard that bricks the
harness is worse than a missed warning.
"""
import json
import os
import re
import sys

RULE = (
    "CLAUDE.md §Model routing: spawns must set an explicit model — "
    "sonnet (build/census/mechanical), opus (review/judge), haiku (trivial sweeps). "
    "Fable spawns run ONLY as subagent_type 'orchestrator' with explicit model "
    "'fable' AND a \"FABLE-WHY: <orchestration|brainstorm|creative>: <specific "
    "reason>\" line in the prompt."
)

# Agent types allowed to run fable; the spawn must still carry the explicit
# model AND the justification line below — the type alone grants nothing.
FABLE_OK_TYPES = {"orchestrator"}
FABLE_WHY_RE = re.compile(
    r"FABLE-WHY\s*:\s*(orchestration|brainstorm|creative)\s*:\s*\S.{19,}", re.I
)


def allow():
    sys.exit(0)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _is_fable(model):
    # Substring match catches both the 'fable' alias and full ids
    # like 'claude-fable-5'.
    return "fable" in model


def _frontmatter_model(subagent_type):
    """Best-effort read of a custom agent type's frontmatter model pin."""
    if not subagent_type or not re.fullmatch(r"[\w-]+", subagent_type):
        return ""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or "."
    candidates = (
        os.path.join(project_dir, ".claude", "agents", subagent_type + ".md"),
        os.path.expanduser(
            os.path.join("~", ".claude", "agents", subagent_type + ".md")
        ),
    )
    for path in candidates:
        try:
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(2048)
            m = re.search(r"^\s*model\s*:\s*(\S+)", head, re.M)
            if m:
                return m.group(1).strip().strip("'\"").lower()
        except Exception:
            continue
    return ""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        allow()

    if tool in ("Agent", "Task"):
        model = str(ti.get("model") or "").strip().lower()
        sub = str(ti.get("subagent_type") or "").strip()
        prompt = str(ti.get("prompt") or "")

        if _is_fable(model):
            if sub not in FABLE_OK_TYPES:
                deny(
                    "Blocked: fable spawns require subagent_type 'orchestrator' "
                    "(got %r). " % (sub or "default") + RULE
                )
            if not FABLE_WHY_RE.search(prompt):
                deny(
                    "Blocked: fable orchestrator spawn is missing a valid "
                    "FABLE-WHY line (category + specific reason, >=20 chars). "
                    + RULE
                )
            allow()
        if sub in FABLE_OK_TYPES:
            # orchestrator IS the fable exception — require the deliberate,
            # fully explicit form so intent is always visible in the call.
            deny(
                "Blocked: subagent_type 'orchestrator' requires explicit "
                "model 'fable' plus a FABLE-WHY line in the prompt. " + RULE
            )
        if model:
            allow()  # explicit non-fable model
        if sub == "fork":  # forks inherit the parent model by design
            allow()
        if sub in ("", "claude", "general-purpose", "Explore", "Plan"):
            deny(
                "Blocked: %s spawn without explicit model (subagent_type=%s) "
                "would inherit the session model. Re-call with model set. %s"
                % (tool, sub or "default", RULE)
            )
        # Named custom agent type with no explicit model — honor its
        # frontmatter pin, but a fable pin outside FABLE_OK_TYPES is exactly
        # the silent-inherit hole this guard exists to close.
        if _is_fable(_frontmatter_model(sub)):
            deny(
                "Blocked: agent type %r pins model fable in its frontmatter; "
                "fable runs only via 'orchestrator' + FABLE-WHY. " % sub + RULE
            )
        allow()

    if tool == "Workflow":
        script = ti.get("script") or ""
        if not script:
            sp = ti.get("scriptPath") or ""
            if sp and os.path.isfile(sp):
                try:
                    with open(sp, "r", encoding="utf-8", errors="replace") as f:
                        script = f.read()
                except Exception:
                    allow()
            else:
                allow()  # predefined {name: ...} workflow — vetted elsewhere
        # Fable in workflows is GATED, not banned (operator re-enable
        # 2026-07-18, "reenable fable ultracode"): a script may route stages
        # to fable ONLY when it carries the same FABLE-WHY justification line
        # the Agent-spawn gate requires. The line is the audit trail — grep
        # for drift. Reserve fable stages for judge/synthesis work, never
        # bulk xN mechanical fan-outs.
        script_has_fable_why = bool(FABLE_WHY_RE.search(script))
        if re.search(r"model\s*:\s*['\"`][^'\"`]*fable[^'\"`]*['\"`]", script, re.I):
            if not script_has_fable_why:
                deny(
                    "Blocked: workflow script routes an agent to fable without "
                    "a script-level FABLE-WHY line (category + specific "
                    "reason, >=20 chars). Add \"// FABLE-WHY: "
                    "<orchestration|brainstorm|creative>: <reason>\" to the "
                    "script, and reserve fable for judge/synthesis stages — "
                    "never bulk xN mechanical fan-outs. " + RULE
                )
        if re.search(r"agentType\s*:\s*['\"`]orchestrator['\"`]", script, re.I):
            if not script_has_fable_why:
                deny(
                    "Blocked: workflow script uses agentType 'orchestrator' "
                    "without a script-level FABLE-WHY line. Add the "
                    "justification line or route the stage to sonnet/opus. "
                    + RULE
                )
        if "agent(" in script and "model" not in script and "agentType" not in script:
            deny(
                "Blocked: workflow script calls agent() with no model:/agentType "
                "routing — every agent would inherit the session model. "
                "Add per-stage model overrides. " + RULE
            )
        allow()

    allow()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail open
