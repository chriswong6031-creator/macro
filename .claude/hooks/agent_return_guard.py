#!/usr/bin/env python3
"""SubagentStop guard: require routed workers to return a complete evidence packet.

The first malformed stop is blocked and the missing contract is fed back to the
same worker. If stop_hook_active is already true, allow the second stop to avoid
an infinite hook loop; the parent can then adjudicate any remaining deficiency.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HEADER_RE = re.compile(r"(?mi)^\s*(?:#{1,6}\s*)?([A-Z][A-Z0-9 /_-]{1,48})\s*:\s*(.*)$")


def _project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".").resolve()


def _load_registry() -> dict:
    with (_project_dir() / ".claude" / "agent-routing.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def _sections(text: str) -> dict[str, str]:
    matches = list(HEADER_RE.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = re.sub(r"\s+", " ", m.group(1).strip().upper())
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        inline = m.group(2).strip()
        tail = text[start:end].strip()
        out[name] = "\n".join(x for x in (inline, tail) if x).strip()
    return out


def _route_for_agent(registry: dict, agent_type: str) -> tuple[str, dict] | tuple[None, None]:
    for route, spec in registry.get("routes", {}).items():
        if spec.get("agent") == agent_type:
            return route, spec
    return None, None


def _block(reason: str) -> None:
    print(reason, file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        registry = _load_registry()
    except Exception:
        return

    agent_type = str(payload.get("agent_type") or "")
    route, spec = _route_for_agent(registry, agent_type)
    if not route or not spec:
        return

    required = spec.get("required_return_sections") or []
    if not required:
        return  # e.g. exceptional Fable orchestrator

    message = str(payload.get("last_assistant_message") or "")
    sections = _sections(message)
    problems = []

    for name in required:
        content = sections.get(name, "").strip()
        if not content:
            problems.append(f"missing/empty {name}")

    status = sections.get("STATUS", "").strip().upper()
    allowed_status = {str(x).upper() for x in registry.get("status_values", [])}
    if status and status not in allowed_status:
        problems.append(
            "STATUS must be exactly one of " + " | ".join(sorted(allowed_status))
        )

    result = sections.get("RESULT", "").strip()
    if result and len(result) < 8:
        problems.append("RESULT is too thin to be useful")

    evidence = sections.get("EVIDENCE", "").strip()
    if evidence and evidence.lower() in {"none", "n/a", "na", "unknown"}:
        problems.append("EVIDENCE cannot be empty/none; cite the receipts supporting the result")

    if not problems:
        return

    # A stop hook can otherwise recurse forever. Give the worker one deterministic
    # correction pass, then let the parent see the residual problem.
    if bool(payload.get("stop_hook_active")):
        return

    _block(
        f"ROUTE {route} return contract incomplete. Fix your FINAL response before "
        "returning to Fable. Use exactly these labels: "
        + ", ".join(required)
        + ". Problems: "
        + "; ".join(problems)
        + ". Do not add process narration; repair the evidence packet."
    )


if __name__ == "__main__":
    main()
