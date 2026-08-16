#!/usr/bin/env python3
"""Require hosted/self-hosted logical-result parity for the canary pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hosted", type=Path, required=True)
    parser.add_argument("--selfhosted", type=Path, required=True)
    args = parser.parse_args()
    hosted = json.loads(args.hosted.read_text(encoding="utf-8"))
    selfhosted = json.loads(args.selfhosted.read_text(encoding="utf-8"))
    fields = ("tested_sha", "base_sha", "pack", "plan_sha256", "logical_jobs", "failed_jobs", "result")
    mismatches = {
        field: {"hosted": hosted.get(field), "selfhosted": selfhosted.get(field)}
        for field in fields
        if hosted.get(field) != selfhosted.get(field)
    }
    for label, receipt in (("hosted", hosted), ("selfhosted", selfhosted)):
        if sorted(receipt.get("executed_jobs") or []) != sorted(
            receipt.get("logical_jobs") or []
        ):
            mismatches[f"{label}_execution"] = {
                "expected": receipt.get("logical_jobs"),
                "executed": receipt.get("executed_jobs"),
            }
    summary = {
        "schema": "ci.selfhosted_canary_comparison.v1",
        "parity": not mismatches,
        "mismatches": mismatches,
        "hosted": hosted,
        "selfhosted": selfhosted,
    }
    print("CI_CANARY_COMPARISON=" + json.dumps(summary, sort_keys=True), flush=True)
    if mismatches:
        print("::error title=ci-canary-parity::hosted/self-hosted results differ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
