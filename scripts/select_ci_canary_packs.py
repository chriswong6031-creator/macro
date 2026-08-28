#!/usr/bin/env python3
"""Select the currently heaviest non-empty pack(s) from a frozen CI plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# This must stay a self-contained stdlib-only literal, NOT an import of
# scripts.ci_semantic_proof.PLAN_SCHEMA: the canary workflow copies this file
# alone into a trusted-control directory OUTSIDE the untrusted candidate
# checkout (`cp scripts/select_ci_canary_packs.py "$RUNNER_TEMP/ci-canary-control/"`,
# .github/workflows/selfhosted-ci-canary.yml `plan` job) precisely so a
# malicious PR tree cannot substitute its own copy of a script this trust
# boundary depends on. A cross-module import would need scripts/ at the same
# relative path as the copy, which does not exist there — see
# scripts/resolve_ci_canary_ref.py and scripts/monitor_ci_host_resources.py,
# the sibling trusted-control scripts, which are stdlib-only for the same
# reason.
#
# The pack runner emits `schema: PLAN_SCHEMA` from
# scripts/ci_semantic_proof.py, which moved to "ci.pack_plan.v2" well before
# this literal was written here. Discovered 2026-08-25 (issue #6351 P0R
# bridge): the stale "ci.pack_plan.v1" literal rejected every plan.json
# scripts/run_ci_pack.py --emit-plan-json actually writes, so this selector
# could never have succeeded once run_ci_pack.py's plan-only path was
# reachable. tests/test_ci_canary_tools.py pins this literal against the
# live PLAN_SCHEMA constant so the two cannot drift apart silently again.
_PLAN_SCHEMA = "ci.pack_plan.v2"


def write_outputs(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def select(plan: dict[str, object], count: int) -> list[dict[str, object]]:
    if plan.get("schema") != _PLAN_SCHEMA:
        raise ValueError("unexpected CI plan schema")
    packs = plan.get("packs")
    if not isinstance(packs, list):
        raise ValueError("plan packs must be a list")
    nonempty = [
        pack
        for pack in packs
        if isinstance(pack, dict)
        and isinstance(pack.get("jobs"), list)
        and pack["jobs"]
        and isinstance(pack.get("weight"), int)
        and isinstance(pack.get("index"), int)
    ]
    if not nonempty:
        raise ValueError("plan contains no executable pack")
    if len(nonempty) < count:
        raise ValueError(
            f"plan has only {len(nonempty)} non-empty pack(s); {count} requested"
        )
    return sorted(nonempty, key=lambda item: (-item["weight"], item["index"]))[:count]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--count", type=int, choices=(1, 3), required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    chosen = select(plan, args.count)
    matrix = {"include": [{"pack": pack["index"]} for pack in chosen]}
    primary = chosen[0]
    outputs = {
        "matrix": json.dumps(matrix, separators=(",", ":")),
        "primary_pack": str(primary["index"]),
        "primary_jobs": json.dumps(primary["jobs"], separators=(",", ":")),
        "selected_packs": json.dumps(chosen, separators=(",", ":")),
    }
    write_outputs(args.github_output, outputs)
    print("CI_CANARY_SELECTION=" + json.dumps(chosen, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
