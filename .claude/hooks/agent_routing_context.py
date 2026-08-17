#!/usr/bin/env python3
"""SessionStart context injector for the semantic agent-routing control plane."""
from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> None:
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".").resolve()
    path = project / ".claude" / "agent-routing.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    routes = registry.get("routes", {})
    order = ["extract", "census", "research", "draft", "analysis", "debug",
             "build", "review", "design", "judgment", "orchestration"]
    mappings = []
    contracts = []
    for route in order:
        spec = routes.get(route)
        if not spec:
            continue
        if spec.get("main_loop_only"):
            mappings.append(f"{route}->Fable main loop")
        else:
            mappings.append(f"{route}->{spec.get('agent')}({spec.get('model')})")
        required = spec.get("required_prompt_sections") or []
        if required and route not in {"orchestration"}:
            contracts.append(f"{route}=" + "/".join(required))

    print(
        "AGENT ROUTING CONTROL (hook-enforced): For every direct Agent/Task delegation, "
        "Fable chooses semantic ROUTE, never a model tier. Use the exact custom agent in "
        ".claude/agent-routing.json; generic/general-purpose/Explore/Plan/fork are not "
        "routing bypasses. Model overrides may not change the route's model family. "
        "Final judgment stays in Fable. Exceptional Fable child = ROUTE orchestration + "
        "orchestrator + explicit model fable + valid FABLE-WHY. "
        "ROUTES: " + "; ".join(mappings) + ". "
        "Commission fields (exact SECTION: labels): " + "; ".join(contracts) + ". "
        "Every normal worker RETURN must request STATUS/RESULT/EVIDENCE/GAPS/DEVIATIONS. "
        "If the spawn guard rejects a call, fix the route/commission; never evade the guard."
    )


if __name__ == "__main__":
    main()
