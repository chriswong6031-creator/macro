#!/usr/bin/env python3
"""Require hosted/self-hosted logical-result AND raw-evidence parity.

Diagnostic-only comparator (#6351 P0R bridge, spec item C.6): in addition to
the original receipt-field parity, this now requires STRICT canonical
equality of the hosted and self-hosted ``ci.semantic_fragment.v1`` documents
for the same pack, after validating both fragments describe the SAME frozen
plan. This module deliberately imports only pure canonicalization helpers
(``FRAGMENT_SCHEMA``, ``canonical_sha256``) from
``scripts/ci_semantic_proof.py`` — never ``reconcile_evidence`` or any other
merge-authority entry point. This workflow never calls
``scripts/merge_on_green.py``; a diagnostic canary comparison is not, and
must never become, a merge-gating verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ci_semantic_proof import FRAGMENT_SCHEMA, canonical_sha256  # noqa: E402


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(
    hosted: dict,
    selfhosted: dict,
    hosted_fragment: dict,
    selfhosted_fragment: dict,
) -> dict:
    """Pure comparison, importable for tests without a filesystem round-trip."""
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

    for label, fragment in (("hosted", hosted_fragment), ("selfhosted", selfhosted_fragment)):
        if fragment.get("schema") != FRAGMENT_SCHEMA:
            mismatches[f"{label}_fragment_schema"] = {
                "expected": FRAGMENT_SCHEMA,
                "actual": fragment.get("schema"),
            }
    # Identity validation against the same plan BEFORE the strict byte
    # comparison: a plan/identity mismatch is a more specific, more useful
    # finding than "these two 4KB documents differ somewhere."
    identity_fields = (
        "workflow_run_id",
        "workflow",
        "event",
        "role",
        "tested_tree_sha",
        "subject_head_sha",
        "base_sha",
        "plan_sha256",
    )
    for field in identity_fields:
        if hosted_fragment.get(field) != selfhosted_fragment.get(field):
            mismatches[f"fragment_{field}"] = {
                "hosted": hosted_fragment.get(field),
                "selfhosted": selfhosted_fragment.get(field),
            }
    if hosted_fragment.get("tested_tree_sha") != hosted.get("tested_sha"):
        mismatches["fragment_receipt_identity"] = {
            "hosted_fragment_tested_tree_sha": hosted_fragment.get("tested_tree_sha"),
            "hosted_receipt_tested_sha": hosted.get("tested_sha"),
        }
    if not mismatches:
        hosted_digest = canonical_sha256(hosted_fragment)
        selfhosted_digest = canonical_sha256(selfhosted_fragment)
        if hosted_digest != selfhosted_digest:
            mismatches["fragment_canonical_sha256"] = {
                "hosted": hosted_digest,
                "selfhosted": selfhosted_digest,
            }
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hosted", type=Path, required=True)
    parser.add_argument("--selfhosted", type=Path, required=True)
    parser.add_argument("--hosted-fragment", type=Path, required=True)
    parser.add_argument("--selfhosted-fragment", type=Path, required=True)
    args = parser.parse_args()
    hosted = _load(args.hosted)
    selfhosted = _load(args.selfhosted)
    hosted_fragment = _load(args.hosted_fragment)
    selfhosted_fragment = _load(args.selfhosted_fragment)
    mismatches = compare(hosted, selfhosted, hosted_fragment, selfhosted_fragment)
    summary = {
        "schema": "ci.selfhosted_canary_comparison.v2",
        "parity": not mismatches,
        "mismatches": mismatches,
        "hosted": hosted,
        "selfhosted": selfhosted,
    }
    print("CI_CANARY_COMPARISON=" + json.dumps(summary, sort_keys=True), flush=True)
    if mismatches:
        print("::error title=ci-canary-parity::hosted/self-hosted results differ", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
