"""
scripts/check_synapse_registry.py — Synapse registry integrity gate.

HARD-FAIL (exit 1) on any structural violation detected by
engine.neuralweb.synapse.validate_registry(). Prints each violation
to stdout with a [VIOLATION] prefix.

Scope: registry INTEGRITY only (required fields, enum validity, producer
existence, duplicate paths). This script does NOT check:
  - Consumer coverage (whether every module that reads an artifact is listed)
  - Read-gating (whether reads are authorized) — that is W1's job
  - Envelope stamping — that is W2's job

Usage
-----
  python scripts/check_synapse_registry.py [--root /path/to/repo] [--selftest]

Options
-------
  --root PATH     Repo root for resolving relative paths (default: parent of
                  the scripts/ directory, i.e. the repo root).
  --selftest      Inject a set of synthetic bad entries into the in-memory
                  registry and prove the validator catches each one. Exits 0
                  if all expected violations are caught, 1 otherwise.
                  Precedent: scripts/check_validated_claims.py --selftest.
"""
import argparse
import copy
import sys
from pathlib import Path

# Allow running as a standalone script from the repo root.
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.synapse import load_registry, validate_registry  # noqa: E402


def _run_integrity_check(root: Path) -> int:
    """Load and validate the registry. Returns exit code (0=clean, 1=violations)."""
    try:
        reg = load_registry(root)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 1

    violations = validate_registry(reg, root=root)
    if violations:
        print(f"synapse registry integrity: {len(violations)} violation(s) found")
        for v in violations:
            print(f"  [VIOLATION] {v}")
        return 1

    n_artifacts = len((reg.get("artifacts") or {}))
    print(f"synapse registry OK — {n_artifacts} artifacts registered, 0 violations")
    return 0


def _run_selftest(root: Path) -> int:
    """
    Inject synthetic bad entries in-memory and prove the validator catches them.
    Returns exit code (0=all violations caught, 1=some escaped).
    """
    base_reg = load_registry(root)
    all_passed = True

    def _test(label: str, mutated_reg: dict, expected_fragment: str) -> None:
        nonlocal all_passed
        violations = validate_registry(mutated_reg, root=root)
        matched = any(expected_fragment.lower() in v.lower() for v in violations)
        status = "PASS" if matched else "FAIL"
        if not matched:
            all_passed = False
        print(f"  selftest [{status}] {label}")
        if not matched:
            print(f"    expected fragment: {expected_fragment!r}")
            print(f"    got violations:    {violations}")

    # --- Test 1: missing required field (path missing) ---
    reg1 = copy.deepcopy(base_reg)
    reg1["artifacts"]["_selftest_missing_path"] = {
        "format": "json",
        "producer": "engine/run.py",
        "owner_program": "engine-fix",
        "cadence": "daily-engine",
        "storage": "git",
        "asof_field": "asof",
        "freshness_sla_hours": 30,
        "schema": "none",
        "tier": "display",
        "weights": "none",
        # NOTE: 'path' is intentionally missing
    }
    _test("missing required field 'path'", reg1, "missing required field 'path'")

    # --- Test 2: invalid tier enum ---
    reg2 = copy.deepcopy(base_reg)
    reg2["artifacts"]["_selftest_bad_tier"] = {
        "path": "data/_selftest/bad_tier.json",
        "format": "json",
        "producer": "engine/run.py",
        "owner_program": "engine-fix",
        "cadence": "daily-engine",
        "storage": "git",
        "asof_field": "asof",
        "freshness_sla_hours": 30,
        "schema": "none",
        "tier": "NOT_A_VALID_TIER",
        "weights": "none",
    }
    _test("invalid tier enum", reg2, "tier")

    # --- Test 3: duplicate path ---
    reg3 = copy.deepcopy(base_reg)
    # Use a path that already exists in the registry
    existing_path = next(
        e["path"]
        for e in reg3["artifacts"].values()
        if isinstance(e, dict) and e.get("path")
    )
    reg3["artifacts"]["_selftest_dup_path"] = {
        "path": existing_path,
        "format": "json",
        "producer": "engine/run.py",
        "owner_program": "engine-fix",
        "cadence": "daily-engine",
        "storage": "git",
        "asof_field": "asof",
        "freshness_sla_hours": 30,
        "schema": "none",
        "tier": "display",
        "weights": "none",
    }
    _test("duplicate path", reg3, "duplicate path")

    # --- Test 4: weights='hand' without notes ---
    reg4 = copy.deepcopy(base_reg)
    reg4["artifacts"]["_selftest_hand_no_notes"] = {
        "path": "data/_selftest/hand_weights.json",
        "format": "json",
        "producer": "engine/run.py",
        "owner_program": "engine-fix",
        "cadence": "daily-engine",
        "storage": "git",
        "asof_field": "asof",
        "freshness_sla_hours": 30,
        "schema": "none",
        "tier": "display",
        "weights": "hand",
        # NOTE: 'notes' is intentionally missing
    }
    _test("hand weights without notes", reg4, "weights='hand' requires a notes field")

    # --- Test 5: scored tier without qual_ladder_ref or notes ---
    reg5 = copy.deepcopy(base_reg)
    reg5["artifacts"]["_selftest_scored_no_evidence"] = {
        "path": "data/_selftest/scored_no_evidence.json",
        "format": "json",
        "producer": "engine/run.py",
        "owner_program": "engine-fix",
        "cadence": "daily-engine",
        "storage": "git",
        "asof_field": "asof",
        "freshness_sla_hours": 30,
        "schema": "none",
        "tier": "scored",
        "weights": "none",
        "horizon_role": "context",
        # NOTE: no qual_ladder_ref and no notes
    }
    _test("scored tier without qual_ladder_ref/notes", reg5, "article 3 honesty")

    # --- Test 6: missing horizon_role field ---
    reg6 = copy.deepcopy(base_reg)
    reg6["artifacts"]["_selftest_missing_horizon_role"] = {
        "path": "data/_selftest/no_horizon_role.json",
        "format": "json",
        "producer": "engine/run.py",
        "owner_program": "engine-fix",
        "cadence": "daily-engine",
        "storage": "git",
        "asof_field": "asof",
        "freshness_sla_hours": 30,
        "schema": "none",
        "tier": "display",
        "weights": "none",
        # NOTE: 'horizon_role' is intentionally missing
    }
    _test("missing required field 'horizon_role'", reg6, "horizon_role")

    # --- Test 7: invalid horizon_role enum value ---
    reg7 = copy.deepcopy(base_reg)
    reg7["artifacts"]["_selftest_bad_horizon_role"] = {
        "path": "data/_selftest/bad_horizon_role.json",
        "format": "json",
        "producer": "engine/run.py",
        "owner_program": "engine-fix",
        "cadence": "daily-engine",
        "storage": "git",
        "asof_field": "asof",
        "freshness_sla_hours": 30,
        "schema": "none",
        "tier": "display",
        "weights": "none",
        "horizon_role": "NOT_A_VALID_HORIZON_ROLE",
    }
    _test("invalid horizon_role enum", reg7, "horizon_role")

    # --- Test 8: producer path that does not exist (review M9) ---------------------
    # Added 2026-07-29. `live-options-flow-current` named
    # `collectors/live_options_flow_poller.py` — a file that has never existed in this
    # repo — and the check could not see it because `storage: r2` exempted the row from
    # the producer-exists rule. `storage` describes where the ARTIFACT lives, not its
    # producer script, so the exemption is gone and this selftest pins the rule for BOTH
    # storage kinds: an r2 row must be judged exactly like a git row.
    for _storage in ("git", "r2"):
        reg8 = copy.deepcopy(base_reg)
        reg8["artifacts"][f"_selftest_phantom_producer_{_storage}"] = {
            "path": f"data/_selftest/phantom_{_storage}.json",
            "format": "json",
            "producer": "collectors/this_file_has_never_existed.py",
            "owner_program": "engine-fix",
            "cadence": "daily-engine",
            "storage": _storage,
            "asof_field": "asof",
            "freshness_sla_hours": 30,
            "schema": "none",
            "tier": "display",
            "horizon_role": "context",
            "weights": "none",
        }
        _test(f"producer path does not exist (storage={_storage})",
              reg8, "producer file not found")

    print()
    if all_passed:
        print("selftest PASSED — all synthetic violations caught")
        return 0
    else:
        print("selftest FAILED — some violations escaped the validator")
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
        help="Run self-test: inject bad entries and prove violations are caught",
    )
    args = parser.parse_args()

    if args.selftest:
        print("Running synapse registry self-test...")
        return _run_selftest(args.root)

    return _run_integrity_check(args.root)


if __name__ == "__main__":
    sys.exit(main())
