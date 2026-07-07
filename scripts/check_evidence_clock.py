"""scripts/check_evidence_clock.py — CI-grade integrity gate for the evidence clock artifact.

HARD-FAIL (exit 1) on any structural violation.  Validates:
  1. Artifact parses as JSON.
  2. schema == "neuralweb.evidence_clock.v1".
  3. authority == "display_only".
  4. Every row state is in the 9-state enum.
  5. No forbidden keys anywhere in rows (score, rank, weight, size, allocation).
  6. Every forbidden_actions list contains "promote" and "mutate_source_state".
  7. evidence_refs are repo-relative string paths (not absolute).
  8. summary counts match rows.

--selftest: injects synthetic bad payloads in-memory and asserts the checker
catches them.  Mimics scripts/check_synapse_registry.py --selftest pattern.

Usage:
    python -m scripts.check_evidence_clock [--root PATH] [--selftest]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

VALID_STATES = frozenset({
    "accruing", "due", "overdue", "stale", "missing",
    "blocked", "promotion_eligible", "human_review", "not_ready",
})
FORBIDDEN_KEYS = frozenset({"score", "rank", "weight", "size", "allocation"})
REQUIRED_FORBIDDEN_ACTIONS = {"promote", "mutate_source_state"}


def _violations(payload: dict) -> list[str]:
    """Return list of violation strings (empty = clean)."""
    errs: list[str] = []

    # 1. schema
    if payload.get("schema") != "neuralweb.evidence_clock.v1":
        errs.append(f"schema must be 'neuralweb.evidence_clock.v1', got {payload.get('schema')!r}")

    # 2. authority
    if payload.get("authority") != "display_only":
        errs.append(f"authority must be 'display_only', got {payload.get('authority')!r}")

    rows = payload.get("rows") or []
    summary = payload.get("summary") or {}

    # 3. summary row count matches
    n_rows_reported = summary.get("n_rows")
    if n_rows_reported is not None and n_rows_reported != len(rows):
        errs.append(
            f"summary.n_rows={n_rows_reported} does not match len(rows)={len(rows)}"
        )

    # 4. summary by_state counts match rows
    by_state = summary.get("by_state") or {}
    actual_counts: dict[str, int] = {}
    for row in rows:
        s = row.get("state", "unknown")
        actual_counts[s] = actual_counts.get(s, 0) + 1
    for state, count in by_state.items():
        actual = actual_counts.get(state, 0)
        if count != actual:
            errs.append(
                f"summary.by_state[{state!r}]={count} does not match actual count {actual}"
            )

    for i, row in enumerate(rows):
        prefix = f"row[{i}] clock_id={row.get('clock_id')!r}"

        # 5. state enum
        state = row.get("state")
        if state not in VALID_STATES:
            errs.append(f"{prefix}: invalid state {state!r}")

        # 6. forbidden keys in row top-level
        for fk in FORBIDDEN_KEYS:
            if fk in row:
                errs.append(f"{prefix}: forbidden key {fk!r} present in row")

        # Also check readiness dict
        readiness = row.get("readiness") or {}
        for fk in FORBIDDEN_KEYS:
            if fk in readiness:
                errs.append(f"{prefix}: forbidden key {fk!r} present in readiness")

        # Also check packet
        packet = row.get("packet")
        if packet:
            for fk in FORBIDDEN_KEYS:
                if fk in packet:
                    errs.append(f"{prefix}: forbidden key {fk!r} present in packet")

        # 7. forbidden_actions must include "promote" and "mutate_source_state"
        fa = set(row.get("forbidden_actions") or [])
        missing_fa = REQUIRED_FORBIDDEN_ACTIONS - fa
        if missing_fa:
            errs.append(f"{prefix}: forbidden_actions missing required entries: {sorted(missing_fa)}")

        # 8. evidence_refs must be strings, not absolute paths
        refs = row.get("evidence_refs") or []
        for ref in refs:
            if not isinstance(ref, str):
                errs.append(f"{prefix}: evidence_refs entry is not a string: {ref!r}")
            elif Path(ref).is_absolute():
                errs.append(f"{prefix}: evidence_refs contains absolute path: {ref!r}")

    return errs


def _check_artifact(root: Path) -> int:
    artifact_path = root / "data" / "neuralweb" / "evidence_clock.json"
    if not artifact_path.exists():
        print(f"[ERROR] artifact not found: {artifact_path}")
        return 1

    try:
        with open(artifact_path, encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] artifact does not parse as JSON: {exc}")
        return 1

    errs = _violations(payload)
    if errs:
        print(f"evidence clock: {len(errs)} violation(s) found")
        for v in errs:
            print(f"  [VIOLATION] {v}")
        return 1

    n_rows = len(payload.get("rows") or [])
    n_gaps = len(payload.get("gaps") or [])
    print(f"evidence clock OK — {n_rows} rows, {n_gaps} gaps, 0 violations")
    return 0


def _run_selftest(root: Path) -> int:
    """Inject synthetic bad payloads and assert the checker catches them."""
    all_passed = True

    def _good_payload() -> dict:
        return {
            "schema": "neuralweb.evidence_clock.v1",
            "as_of": "2026-07-06",
            "generated_utc": "2026-07-06T00:00:00Z",
            "authority": "display_only",
            "summary": {
                "n_rows": 1,
                "by_state": {"accruing": 1},
                "n_acknowledged": 0,
                "top_due": None,
                "morning_line": "1 accruing.",
            },
            "rows": [{
                "clock_id": "test:foo",
                "source_system": "experiments",
                "subject_id": "foo",
                "subject_type": "experiment",
                "owner_program": None,
                "clock_type": "come_back_on",
                "due_at": None,
                "as_of": None,
                "state": "accruing",
                "date_state": "accruing",
                "readiness": {},
                "allowed_actions": ["inspect"],
                "forbidden_actions": ["promote", "mutate_source_state", "score"],
                "evidence_refs": ["data/experiments/registry_seed.json"],
                "regenerate_cmd": None,
                "acknowledged": False,
                "review": None,
                "packet": None,
            }],
            "gaps": [],
            "caveats": [],
        }

    def _test(label: str, mutated: dict, expected_fragment: str) -> None:
        nonlocal all_passed
        errs = _violations(mutated)
        matched = any(expected_fragment.lower() in v.lower() for v in errs)
        status = "PASS" if matched else "FAIL"
        if not matched:
            all_passed = False
        print(f"  selftest [{status}] {label}")
        if not matched:
            print(f"    expected fragment: {expected_fragment!r}")
            print(f"    got violations:    {errs}")

    # Test 1: wrong schema
    p = _good_payload()
    p["schema"] = "wrong.schema"
    _test("wrong schema", p, "schema must be")

    # Test 2: wrong authority
    p = _good_payload()
    p["authority"] = "scored"
    _test("wrong authority", p, "authority must be")

    # Test 3: invalid state
    p = _good_payload()
    p["rows"][0]["state"] = "not_a_valid_state"
    _test("invalid state", p, "invalid state")

    # Test 4: forbidden key 'score' in row
    p = _good_payload()
    p["rows"][0]["score"] = 0.9
    _test("forbidden key 'score' in row", p, "forbidden key 'score'")

    # Test 5: forbidden key 'rank' in readiness
    p = _good_payload()
    p["rows"][0]["readiness"]["rank"] = 1
    _test("forbidden key 'rank' in readiness", p, "forbidden key 'rank'")

    # Test 6: missing 'promote' in forbidden_actions
    p = _good_payload()
    p["rows"][0]["forbidden_actions"] = ["score"]
    _test("missing 'promote' in forbidden_actions", p, "forbidden_actions missing")

    # Test 7: absolute path in evidence_refs
    p = _good_payload()
    p["rows"][0]["evidence_refs"] = ["/absolute/path/to/file.json"]
    _test("absolute evidence_ref", p, "absolute path")

    # Test 8: summary n_rows mismatch
    p = _good_payload()
    p["summary"]["n_rows"] = 99
    _test("summary n_rows mismatch", p, "n_rows=99 does not match")

    # Test 9: summary by_state mismatch
    p = _good_payload()
    p["summary"]["by_state"] = {"due": 5}
    _test("summary by_state mismatch", p, "by_state")

    print()
    if all_passed:
        print("selftest PASSED — all synthetic violations caught")
        return 0
    else:
        print("selftest FAILED — some violations escaped the checker")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_REPO_ROOT,
        help="Repo root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Inject synthetic bad payloads and prove violations are caught",
    )
    args = parser.parse_args()

    if args.selftest:
        print("Running evidence clock self-test...")
        return _run_selftest(args.root)

    return _check_artifact(args.root)


if __name__ == "__main__":
    sys.exit(main())
