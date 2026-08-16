#!/usr/bin/env python3
"""Select the currently heaviest non-empty pack(s) from a frozen CI plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def write_outputs(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def select(plan: dict[str, object], count: int) -> list[dict[str, object]]:
    if plan.get("schema") != "ci.pack_plan.v1":
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
