#!/usr/bin/env python3
"""Create a bounded machine-readable receipt from one CI canary pack."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


GROUP = re.compile(r"^::group::([^ ]+) —")
FAILED = "CI_PACK_FAILED_JOBS="
PREWARM = "CI_CACHE_PREWARM="


def trace2_fetch_seconds(path: Path | None) -> float | None:
    if path is None or not path.exists():
        return None
    command_by_sid: dict[str, str] = {}
    total = 0.0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        sid = str(event.get("sid", ""))
        if event.get("event") == "cmd_name":
            command_by_sid[sid] = str(event.get("name", ""))
        elif event.get("event") == "exit" and command_by_sid.get(sid) == "fetch":
            total += float(event.get("t_abs", 0.0))
    return round(total, 3)


def metrics(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    samples = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not samples:
        return {}
    return {
        "samples": len(samples),
        "cpu_peak_percent": max(item["cpu_percent"] for item in samples),
        "cpu_mean_percent": round(
            sum(item["cpu_percent"] for item in samples) / len(samples), 2
        ),
        "load_peak_1m": max(item["load"][0] for item in samples),
        "memory_available_min_bytes": min(
            item["memory_available_bytes"] for item in samples
        ),
        "swap_used_peak_bytes": max(item["swap_used_bytes"] for item in samples),
        "disk_free_min_bytes": min(item["disk_free_bytes"] for item in samples),
    }


def read_float(path: Path | None) -> float | None:
    if path is None or not path.exists():
        return None
    return float(path.read_text(encoding="utf-8").strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--pack", type=int, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--tested-sha", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--runner-kind", required=True)
    parser.add_argument("--runner-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace2", type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--checkout-seconds", type=Path)
    parser.add_argument("--dependency-seconds", type=Path)
    parser.add_argument("--test-seconds", type=Path)
    parser.add_argument("--wall-seconds", type=Path)
    parser.add_argument("--cache-before", type=Path)
    parser.add_argument("--cache-after", type=Path)
    parser.add_argument("--workspace-object-bytes", type=int, default=0)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    expected = next(
        pack["jobs"] for pack in plan["packs"] if int(pack["index"]) == args.pack
    )
    executed: list[str] = []
    failed: list[str] = []
    prewarm: dict[str, object] | None = None
    for line in args.log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = GROUP.match(line)
        if match and match.group(1) not in executed:
            executed.append(match.group(1))
        if line.startswith(FAILED):
            failed = json.loads(line[len(FAILED) :])
        if line.startswith(PREWARM):
            prewarm = json.loads(line[len(PREWARM) :])
    receipt = {
        "schema": "ci.selfhosted_canary_receipt.v1",
        "runner_kind": args.runner_kind,
        "runner_name": args.runner_name,
        "tested_sha": args.tested_sha,
        "base_sha": args.base_sha,
        "pack": args.pack,
        "plan_sha256": plan["plan_sha256"],
        "logical_jobs": expected,
        "executed_jobs": sorted(executed),
        "failed_jobs": failed,
        "exit_code": args.exit_code,
        "result": "passed" if args.exit_code == 0 else "failed",
        "prewarm": prewarm,
        "origin_fetch_seconds": trace2_fetch_seconds(args.trace2),
        "checkout_seconds": read_float(args.checkout_seconds),
        "dependency_seconds": read_float(args.dependency_seconds),
        "test_seconds": read_float(args.test_seconds),
        "wall_seconds": read_float(args.wall_seconds),
        "cache_bytes_before": read_float(args.cache_before),
        "cache_bytes_after": read_float(args.cache_after),
        "workspace_object_bytes": args.workspace_object_bytes,
        "resources": metrics(args.metrics),
    }
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("CI_CANARY_RECEIPT=" + json.dumps(receipt, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
