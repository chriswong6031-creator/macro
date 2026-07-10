"""scripts/check_grader_manifest.py — F1 grader-immutability manifest guard.

Mirrors the structure of scripts/check_house_law_registry.py exactly.

Recomputes the SHA-256 hash of every file declared in config/grader_manifest.yml
and hard-fails (exit 1) if any hash has drifted.  A missing file is also a hard
failure — the manifest must name REAL files.

Why this matters (R-AUT-7): the graders are the loop's fitness scoreboard.  If the
loop could modify them, it could rewrite its own evaluation criteria — the highest-
leverage attack on the autonomic safety model.  This CI check prevents that by making
any drift in a grader file immediately visible at PR merge time, for both human and
loop-authored changes.

Quarantine path (when drift is detected):
    1. A loop-authored PR that causes drift is BLOCKED by the F2 self-modification
       fence BEFORE it reaches this check (loop can never modify the IMMUTABLE set).
    2. A human-authored PR that intentionally changes a grader must also update
       config/grader_manifest.yml (run --regen, inspect the delta, ratify in PR).
    3. This check then passes because the manifest hash matches the new file.

The --regen flag regenerates the manifest hashes from the current files on disk.
Use it ONLY when intentionally updating a grader with operator approval.

Usage:
    python3 scripts/check_grader_manifest.py            # check; exit 1 on drift
    python3 scripts/check_grader_manifest.py --regen    # regenerate manifest hashes
    python3 scripts/check_grader_manifest.py --selftest # synthetic assertions; exit 0/1
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

import yaml

MANIFEST_PATH = "config/grader_manifest.yml"
EXPECTED_SCHEMA = "grader_manifest.v1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest(root: Path) -> dict:
    p = root / MANIFEST_PATH
    with open(p) as f:
        return yaml.safe_load(f)


def check(root: Path | None = None) -> int:
    """Run the manifest check.  Returns 0 on pass, 1 on any hard failure."""
    if root is None:
        root = _repo_root()

    # Load manifest — missing manifest is a hard failure
    try:
        manifest = _load_manifest(root)
    except FileNotFoundError:
        print(f"HARD: manifest not found: {root / MANIFEST_PATH}")
        return 1
    except Exception as e:
        print(f"HARD: could not load manifest {MANIFEST_PATH}: {e}")
        return 1

    # Schema check
    if manifest.get("schema") != EXPECTED_SCHEMA:
        print(
            f"HARD: manifest schema must be '{EXPECTED_SCHEMA}', "
            f"got '{manifest.get('schema')}'"
        )
        return 1

    files = manifest.get("files", [])
    if not isinstance(files, list) or not files:
        print("HARD: manifest 'files' must be a non-empty list")
        return 1

    findings: list[str] = []

    for entry in files:
        if not isinstance(entry, dict):
            findings.append("HARD: manifest entry is not a dict")
            continue

        rel_path = entry.get("path")
        expected_hash = entry.get("sha256")

        if not rel_path:
            findings.append("HARD: manifest entry missing 'path'")
            continue
        if not expected_hash:
            findings.append(f"HARD [{rel_path}]: manifest entry missing 'sha256'")
            continue

        abs_path = root / rel_path
        if not abs_path.exists():
            findings.append(
                f"HARD [{rel_path}]: file does not exist on disk. "
                f"If intentionally deleted, remove it from {MANIFEST_PATH}."
            )
            continue

        actual_hash = _sha256_file(abs_path)
        if actual_hash != expected_hash:
            findings.append(
                f"HARD [{rel_path}]: hash drift detected.\n"
                f"  expected: {expected_hash}\n"
                f"  actual  : {actual_hash}\n"
                f"\n"
                f"  Quarantine path: this drift is a T2 event (R-AUT-7).\n"
                f"  Loop-authored PRs touching this file are blocked by the F2 fence.\n"
                f"  Human-authored changes must run:\n"
                f"    python3 scripts/check_grader_manifest.py --regen\n"
                f"  Inspect the fitness delta vs the frozen replay corpus, ratify\n"
                f"  in the PR body, and commit both this file and the manifest update."
            )

    if findings:
        for f in findings:
            print(f)
        return 1

    n = len(files)
    print(f"check_grader_manifest: OK — {n} grader file(s) match their registered hashes.")
    return 0


def regen(root: Path | None = None) -> int:
    """Regenerate manifest hashes from files on disk.  Writes updated manifest."""
    if root is None:
        root = _repo_root()

    try:
        manifest = _load_manifest(root)
    except FileNotFoundError:
        print(f"HARD: manifest not found: {root / MANIFEST_PATH}")
        return 1
    except Exception as e:
        print(f"HARD: could not load manifest: {e}")
        return 1

    files = manifest.get("files", [])
    updated = 0
    missing = 0

    for entry in files:
        rel_path = entry.get("path")
        if not rel_path:
            continue
        abs_path = root / rel_path
        if not abs_path.exists():
            print(f"WARN [{rel_path}]: file not found — keeping old hash")
            missing += 1
            continue
        new_hash = _sha256_file(abs_path)
        old_hash = entry.get("sha256", "")
        if new_hash != old_hash:
            print(f"  updated [{rel_path}]: {old_hash[:12]}... -> {new_hash[:12]}...")
            entry["sha256"] = new_hash
            updated += 1
        else:
            print(f"  unchanged [{rel_path}]: {new_hash[:12]}...")

    manifest_path = root / MANIFEST_PATH
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\nregen complete: {updated} updated, {missing} missing, "
          f"{len(files) - updated - missing} unchanged.")
    if missing:
        print("WARNING: some files were missing — review the manifest before committing.")
    return 0 if missing == 0 else 1


def selftest() -> int:
    """Synthetic assertions that prove the check catches drift and missing files."""
    print("Running selftest...")
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="grader_manifest_selftest_") as tmpdir:
        tmp = Path(tmpdir)

        # Create fake grader files
        (tmp / "scripts").mkdir()
        (tmp / "engine").mkdir()
        (tmp / "config").mkdir()

        good_content = b"# grader content v1\ndef grade(): pass\n"
        bad_content = b"# TAMPERED grader content\ndef grade(): return 42\n"

        good_hash = hashlib.sha256(good_content).hexdigest()

        (tmp / "scripts" / "grade_thematic.py").write_bytes(good_content)

        # Test 1: clean manifest passes
        manifest_clean = {
            "schema": "grader_manifest.v1",
            "generated_at": "2026-07-09",
            "owner_program": "test",
            "files": [
                {
                    "path": "scripts/grade_thematic.py",
                    "sha256": good_hash,
                    "role": "orchestrator",
                    "notes": "test",
                },
            ],
        }
        (tmp / "config" / "grader_manifest.yml").write_text(
            yaml.dump(manifest_clean, default_flow_style=False)
        )
        rc = check(root=tmp)
        if rc != 0:
            failures.append("Clean manifest should pass but returned non-zero")

        # Test 2: hash drift is detected
        (tmp / "scripts" / "grade_thematic.py").write_bytes(bad_content)
        rc = check(root=tmp)
        if rc == 0:
            failures.append("Tampered file should fail but returned 0")
        # Restore
        (tmp / "scripts" / "grade_thematic.py").write_bytes(good_content)

        # Test 3: missing file is detected (fail-closed)
        manifest_missing = {
            "schema": "grader_manifest.v1",
            "generated_at": "2026-07-09",
            "owner_program": "test",
            "files": [
                {
                    "path": "scripts/grade_thematic.py",
                    "sha256": good_hash,
                    "role": "orchestrator",
                    "notes": "test",
                },
                {
                    "path": "engine/does_not_exist.py",
                    "sha256": "aabbcc",
                    "role": "sensor",
                    "notes": "test",
                },
            ],
        }
        (tmp / "config" / "grader_manifest.yml").write_text(
            yaml.dump(manifest_missing, default_flow_style=False)
        )
        rc = check(root=tmp)
        if rc == 0:
            failures.append("Missing file should fail (fail-closed) but returned 0")

        # Test 4: wrong schema is detected
        manifest_bad_schema = {
            "schema": "wrong_schema.v99",
            "files": [],
        }
        (tmp / "config" / "grader_manifest.yml").write_text(
            yaml.dump(manifest_bad_schema, default_flow_style=False)
        )
        rc = check(root=tmp)
        if rc == 0:
            failures.append("Wrong schema should fail but returned 0")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("selftest OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="F1 grader-immutability manifest guard."
    )
    ap.add_argument(
        "--regen",
        action="store_true",
        help="Regenerate manifest hashes from files on disk (human operator only).",
    )
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="Run synthetic selftest; exit 0 on pass, 1 on failure.",
    )
    ap.add_argument(
        "--root",
        default=None,
        metavar="PATH",
        help="Repository root (default: auto-detected from script location).",
    )
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else None

    if args.selftest:
        return selftest()
    if args.regen:
        return regen(root=root)
    return check(root=root)


if __name__ == "__main__":
    sys.exit(main())
