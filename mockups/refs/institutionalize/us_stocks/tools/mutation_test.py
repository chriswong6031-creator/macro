#!/usr/bin/env python3
"""Adversarial mutation test for the R4 closure set.

The R4 harness (tools/verify.py) asserts the closure work is PRESENT. This script
asserts the harness can actually SEE it missing — which is a different claim, and
the only one that makes the harness evidence rather than decoration.

For each mutation it:
  1. applies a textual edit that UNDOES one closure item,
  2. HARD-FAILS if the edit did not actually apply (a mutation that silently
     no-ops is a false pass — the guard looks green because nothing changed),
  3. runs the harness and requires it to FAIL,
  4. records WHICH check caught it, so two guards cannot share one kill and
     leave each other decorative,
  5. restores the file byte-for-byte from an in-memory snapshot.

Restore is from a snapshot taken before the first mutation, not from git — a
`git checkout -- <path>` in a tree with untracked siblings can abort the whole
restore and leave a mutation on disk.

Usage:
  python3 tools/mutation_test.py [base_url]

Exit 0 = every mutation was caught, and each by at least one check that no other
mutation relies on alone.
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ART = HERE.parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8792"

# (id, human name, file, regex pattern, replacement)
# Each pattern MUST match the post-closure artifact. If it does not, the harness
# is being tested against an artifact that never had the fix — reported as ERROR,
# never as a pass.
MUTATIONS = [
    (
        "M1", "remove the card -> name-detail link (PRC-301)",
        "board.js",
        r'href="stock\.html#',
        'href="#dead-',
    ),
    (
        "M2", "remove the stale / behind-the-tape state (PRC-305)",
        "board.js",
        r'isStale\b',
        'false && isStale',
    ),
    (
        "M3", "remove progressive in-place expansion (PRC-306)",
        "board.js",
        r'class="sm-bar"',
        'class="sm-bar-REMOVED" hidden ',
    ),
    (
        "M4", "restore the dishonest anonymous gate copy (PRC-302)",
        "board.js",
        r'The rest are part of the live board[^"]*',
        'The rest are part of the live board \\u2014 entry, target and void levels included.',
    ),
    (
        "M5", "revert desktop no-chart geometry to 24px (VTC-301)",
        "board.css",
        r'(\.pv-nochart\s*\{[^}]*?height:\s*)74px',
        r'\g<1>24px',
    ),
]


def run_harness():
    p = subprocess.run(
        [sys.executable, str(HERE / "verify.py"), BASE],
        capture_output=True, text=True, cwd=str(ART),
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def failed_checks(out):
    return [ln.strip() for ln in out.splitlines() if ln.strip().startswith("FAIL")]


def main():
    files = sorted({m[2] for m in MUTATIONS})
    snapshot = {f: (ART / f).read_text() for f in files}

    print("=" * 74)
    print("BASELINE — the harness must PASS on the unmutated artifact")
    print("=" * 74)
    rc, out = run_harness()
    if rc != 0:
        print(out[-3000:])
        print("\nERROR: baseline harness does not pass. Fix that before mutation testing.")
        return 3
    print(out.strip().splitlines()[-1])

    results, errors = [], []
    try:
        for mid, name, fname, pat, rep in MUTATIONS:
            path = ART / fname
            before = snapshot[fname]
            after, n = re.subn(pat, rep, before, count=0)
            if n == 0:
                errors.append(f"{mid} {name}: PATTERN DID NOT MATCH in {fname} "
                              f"(/{pat}/) — the closure item is absent, or its shape moved. "
                              "Not scored as caught.")
                results.append((mid, name, "ERROR", []))
                continue

            path.write_text(after)
            rc, out = run_harness()
            path.write_text(before)          # restore immediately

            fails = failed_checks(out)
            if rc == 0:
                errors.append(f"{mid} {name}: harness still PASSED with the fix reverted "
                              f"({n} site(s) mutated) — that guard is decorative.")
                results.append((mid, name, "SURVIVED", []))
            else:
                results.append((mid, name, "caught", fails))
    finally:
        for f, txt in snapshot.items():
            (ART / f).write_text(txt)

    print()
    print("=" * 74)
    print("MUTATION MATRIX")
    print("=" * 74)
    for mid, name, status, fails in results:
        print(f"\n{mid}  {name}\n    status: {status}")
        for fl in fails[:6]:
            print(f"    {fl}")
        if len(fails) > 6:
            print(f"    … and {len(fails) - 6} more")

    # Each mutation must be caught by at least one check that is NOT the sole
    # catcher of a different mutation — otherwise one guard is doing two jobs and
    # a single regression can hide behind the other.
    print()
    print("=" * 74)
    print("UNIQUE-KILL ANALYSIS")
    print("=" * 74)
    catcher = {}
    for mid, name, status, fails in results:
        if status != "caught":
            continue
        ids = {re.sub(r"^FAIL\s+", "", f).split()[0] for f in fails}
        catcher[mid] = ids
        print(f"{mid}: caught by {sorted(ids)[:8]}")
    for mid, ids in catcher.items():
        unique = ids - set().union(*[v for k, v in catcher.items() if k != mid]) if len(catcher) > 1 else ids
        if not unique:
            errors.append(f"{mid}: caught only by checks that also catch another mutation — "
                          "no unique observable kill.")
        else:
            print(f"{mid}: unique kill via {sorted(unique)[:4]}")

    print()
    print("=" * 74)
    if errors:
        for e in errors:
            print(f"::error title=mutation-test::{e}", flush=True)
            print(f"FAIL  {e}")
        print(f"\n{len(errors)} mutation-test failure(s)")
        return 2
    print(f"{len(results)}/{len(results)} mutations caught, each with a unique kill")
    return 0


if __name__ == "__main__":
    sys.exit(main())
