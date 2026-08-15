"""
scripts/check_synapse_registry.py — Synapse registry integrity gate.

HARD-FAIL (exit 1) on any structural violation detected by
engine.neuralweb.synapse.validate_registry(). Prints each violation
to stdout with a [VIOLATION] prefix.

Scope: registry INTEGRITY only (required fields, enum validity, producer
existence, duplicate paths) plus one prose-hygiene rule (no restated consumer
counts — see check_consumer_count_claims). This script does NOT check:
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
import re
import sys
from pathlib import Path

# Allow running as a standalone script from the repo root.  Unconditional: an
# already-present root further down sys.path still loses to a foreign package
# ahead of it, so this must pin position 0 every time (see scripts/__init__.py).
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.synapse import load_registry, validate_registry  # noqa: E402

REGISTRY_REL = "config/synapse.yml"

# A restated consumer count is drift by construction: an entry's `consumers:` list
# IS its count, so any prose total is a hand-maintained copy of the line below it.
# Measured 2026-08-14 before this rule landed: 43 of the 77 `# --- N consumers ---`
# section headers disagreed with their own entry (site-us-standouts said 13 for a
# 14-item list; regime-latest said 27 for 37), and the regime-latest notes field
# claimed "28 Python modules + 3 external" against an actual 37 + 4. Every one of
# them read as canon to an evidence-gathering session. The counts are gone; this
# rule keeps them gone.
_CONSUMER_COUNT_CLAIM = re.compile(r"\b\d+\s+consumers?\b", re.IGNORECASE)


def check_consumer_count_claims(text: str) -> list[str]:
    """Return one violation per line of `text` that restates a consumer count.

    Deliberately matches prose ANYWHERE in the file — comment or scalar value —
    because both vectors had already drifted. `\\b` before the digits keeps wave
    labels ("W2 consumers", "W4 consumer", "v1 consumer seam") clean: there is no
    word boundary inside "W2", so they never match.
    """
    violations: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = _CONSUMER_COUNT_CLAIM.search(line)
        if not m:
            continue
        violations.append(
            f"{REGISTRY_REL}:{lineno} restates a consumer count in prose "
            f"({m.group(0)!r}) — an entry's `consumers:` list IS its count, so a "
            f"restated total can only drift. Drop the number; for a dated census "
            f"figure name what was counted instead (e.g. '27 unique module files "
            f"at W7a'). Offending line: {line.strip()!r}"
        )
    return violations


def _run_integrity_check(root: Path) -> int:
    """Load and validate the registry. Returns exit code (0=clean, 1=violations)."""
    try:
        reg = load_registry(root)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 1

    violations = validate_registry(reg, root=root)
    violations += check_consumer_count_claims((root / REGISTRY_REL).read_text())
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

    # --- Test 9: restated consumer counts (both vectors + negative controls) ---
    # Added 2026-08-14 with the count strip. Both halves are load-bearing: the
    # FLAG cases prove the rule fires on the shapes that had drifted, and the
    # CLEAN cases prove it is not just matching the word "consumer" — those three
    # strings are real lines of the registry that must never be flagged.
    def _test_text(label: str, sample: str, should_flag: bool) -> None:
        nonlocal all_passed
        found = check_consumer_count_claims(sample)
        ok = bool(found) == should_flag
        if not ok:
            all_passed = False
        print(f"  selftest [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"    expected flagged={should_flag}, got {len(found)} violation(s)")
            print(f"    sample: {sample.strip()!r}")

    for _label, _sample in (
        ("bare section header", "  # --- 13 consumers ---"),
        ("annotated section header", "  # --- 0 consumers (display rail only) ---"),
        ("singular section header", "  # --- 1 consumer ---"),
        ("count restated in a notes value",
         '    notes: "Highest-consumer artifact in the bus (28 consumers)."'),
    ):
        _test_text(f"flags {_label}", _sample, True)

    for _label, _sample in (
        ("labelled section header", "  # --- W2 sweep 1: China Standout Board ---"),
        ("wave label before the word", "      arithmetic. W2 consumers will be the hub tile"),
        ("wave label, singular", "  # NAR-W3 shared-contract stores (W4 consumer)"),
        ("schema seam", "      konseki.market_memory/v1 consumer seam at context_only"),
        ("a real consumers list", "      - engine/neuralweb/cortex.py"),
    ):
        _test_text(f"leaves {_label} alone", _sample, False)

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
