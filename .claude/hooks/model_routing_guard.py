#!/usr/bin/env python3
"""PreToolUse guard: enforce CLAUDE.md §Model routing on Agent/Task/Workflow spawns.

Deny only the clear violations (missing model on default agent types, any 'fable'
spawn, workflow scripts with un-routed agent() calls). Fail OPEN on anything
ambiguous or on internal error — a guard that bricks the harness is worse than
a missed warning.
"""
import json
import os
import re
import sys

RULE = (
    "CLAUDE.md §Model routing: spawns must set an explicit model — "
    "sonnet (build/census/mechanical), opus (review/judge), haiku (trivial sweeps). "
    "Never spawn fable; it is main-loop only."
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
        if model == "fable":
            deny("Blocked: model 'fable' may not be spawned. " + RULE)
        if model:
            allow()
        if sub == "fork":  # forks inherit the parent model by design
            allow()
        if sub in ("", "claude", "general-purpose", "Explore", "Plan"):
            deny(
                "Blocked: %s spawn without explicit model (subagent_type=%s) "
                "would inherit the session model. Re-call with model set. %s"
                % (tool, sub or "default", RULE)
            )
        allow()  # named custom agent type — may pin its own model in frontmatter

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
        if re.search(r"model\s*:\s*['\"]fable['\"]", script):
            deny("Blocked: workflow script spawns model 'fable'. " + RULE)
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
