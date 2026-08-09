#!/usr/bin/env python3
"""A legacy job's declared `paths:` must COVER everything that job reads.

`.github/ci/legacy-jobs.yml` lets a job DECLARE the paths it measures, and
`scripts/run_ci_pack.py` skips that job on a pull request touching none of them.
The declaration is therefore a promise, and this is the gate that makes the
promise checkable: for every job that declares `paths:`, resolve the read-closure
of everything the job runs — its pytest suites and the first-party scripts its
`run:` steps invoke — and fail when a resolved file is matched by no declared
entry.

THE DIRECTION IS THE POINT.  `check_ci_trigger_closure` deliberately UNDER-reports
(its own known-limits say so: direct reads only, path literals are evidence not
proof, `# ci-trigger-closure: data` suppressions).  Under-reporting is the right
bias for "is this suite reachable at all?" and it INVERTS into a silent
wrong-skip the moment a resolver decides what a job may ignore.  So the resolver
is never allowed to decide that here.  It is used only to demand that a
hand-written declaration is BIG ENOUGH:

    resolver misses a file  ->  this guard asks for one pattern less  ->  the
    author's own declaration still covers it, because the author widened
    deliberately (a directory, not a file).

    resolver finds a file the declaration omits  ->  hard failure, and the fix
    is always "declare more", never "skip more".

A job with NO `paths:` key is unskippable and therefore has nothing to promise;
it is not audited here.  That is the safety default, not an exemption.

Exit codes: 0 clean, 1 an uncovered subject, 2 the manifest cannot be read.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Reuse, do not re-implement: the closure guard owns read resolution and the
# suite inventory, run_ci_pack owns the manifest's fail-closed parse, and
# gh_path_filter owns GitHub's glob dialect.  Three imports, zero new dialects.
from scripts import check_ci_trigger_closure as closure_guard  # noqa: E402
from scripts.audit_unrun_tests import CI_MANIFEST  # noqa: E402
from scripts.gh_path_filter import matched  # noqa: E402
from scripts.run_ci_pack import (  # noqa: E402
    LegacyJob,
    ManifestError,
    load_legacy_jobs,
)

# `python3 scripts/foo.py` / `python -m scripts.foo` / `python -m engine.a.b`.
_SCRIPT_PATH = re.compile(r"(?<![\w/.-])(scripts/[\w./-]+\.py)(?![\w])")
_DASH_M = re.compile(r"-m\s+([\w][\w.]*)")


def _module_paths(dotted: str) -> list[str]:
    """Repo-relative file(s) a `-m dotted.module` invocation executes."""
    resolved = closure_guard._resolve(dotted)
    return [rel for rel in resolved if (ROOT / rel).is_file()]


def entry_points(job: LegacyJob, suite_index: dict[str, tuple[str, ...]]) -> set[str]:
    """Every first-party file this job's `run:` steps execute directly.

    Deliberately narrower than "everything the job touches": an inline
    `python -c "..."` body is not parsed, so a job whose only real work happens
    inside one is audited against nothing and must be declared by hand.  That is
    the under-demand direction, which is the safe one for THIS guard.
    """
    found: set[str] = set()
    for step in job.definition["steps"]:
        run = step.get("run")
        if not isinstance(run, str):
            continue
        found |= closure_guard._named_suites(run, suite_index)
        for rel in _SCRIPT_PATH.findall(run):
            if (ROOT / rel).is_file():
                found.add(rel)
        for dotted in _DASH_M.findall(run):
            found.update(_module_paths(dotted))
    return found


def subjects(job: LegacyJob, suite_index: dict[str, tuple[str, ...]],
             cache: dict[str, dict[str, str]]) -> dict[str, str]:
    """``{repo-relative file: why it is a subject}`` for one job."""
    out: dict[str, str] = {}
    for rel in sorted(entry_points(job, suite_index)):
        out.setdefault(rel, "run by this job")
        for read, why in closure_guard.closure(ROOT / rel, 1, cache).items():
            out.setdefault(read, f"{why} of {rel}")
    return out


def uncovered(declared: list[str], found: dict[str, str]) -> list[tuple[str, str]]:
    """Subjects no declared pattern matches, in a stable order."""
    return [
        (rel, why)
        for rel, why in sorted(found.items())
        if not matched(rel, declared)
    ]


def audit(manifest: Path) -> list[dict]:
    """One row per job that declares `paths:`; unannotated jobs are not audited."""
    index = closure_guard.suite_index()
    cache: dict[str, dict[str, str]] = {}
    rows: list[dict] = []
    for job in load_legacy_jobs(manifest):
        declared = job.declared_paths
        if not declared:
            continue
        found = subjects(job, index, cache)
        gaps = uncovered(declared, found)
        rows.append(
            dict(
                job=job.job_id,
                declared=declared,
                subjects=len(found),
                gaps=gaps,
                status="GAP" if gaps else "OK",
            )
        )
    return rows


def _report(rows: list[dict]) -> None:
    for row in rows:
        print(
            f"{row['status']:3s} {row['job']:38s} "
            f"{len(row['declared']):3d} pattern(s)  {row['subjects']:4d} subject(s)"
            f"  {len(row['gaps'])} uncovered"
        )


def _selftest() -> int:
    """Round-trip the detector: it must FIRE on a narrowed declaration.

    A registered guard that has never been seen to fail is a guard nobody has
    reason to trust, so this drives the real repository through both verdicts
    instead of asserting over a fixture that cannot drift with the tree.
    """
    index = closure_guard.suite_index()
    cache: dict[str, dict[str, str]] = {}
    annotated = [
        job for job in load_legacy_jobs(CI_MANIFEST) if job.declared_paths
    ]
    if not annotated:
        print(
            "::error title=ci-pack-paths-selftest::no job declares `paths:`, so "
            "the detector cannot be round-tripped against the live manifest",
            flush=True,
        )
        return 1

    failures: list[str] = []
    probe = next((job for job in annotated if subjects(job, index, cache)), None)
    if probe is None:
        failures.append("no annotated job resolves a single subject")
    else:
        found = subjects(probe, index, cache)
        if not uncovered([], found):
            failures.append(
                f"{probe.job_id}: an EMPTY declaration reported no gap over "
                f"{len(found)} subject(s) — the detector is blind"
            )
        if uncovered(["**"], found):
            failures.append(
                f"{probe.job_id}: `**` reported a gap — the matcher is wrong"
            )
        one = sorted(found)[0]
        if any(rel == one for rel, _ in uncovered([one], found)):
            failures.append(
                f"{probe.job_id}: exact entry {one!r} did not cover itself"
            )

    # A `*` must not cross `/` — the property that makes a directory declaration
    # mean what its author thinks it means.
    if matched("engine/sub/x.py", ["engine/*.py"]):
        failures.append("`engine/*.py` matched a nested file")
    if not matched("engine/sub/x.py", ["engine/**"]):
        failures.append("`engine/**` did not match a nested file")

    for line in failures:
        print(f"::error title=ci-pack-paths-selftest::{line}", flush=True)
    print(
        f"selftest: {len(annotated)} annotated job(s), "
        f"{len(failures)} failure(s)."
    )
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=CI_MANIFEST)
    parser.add_argument(
        "--report", action="store_true", help="print every audited job and exit 0"
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    try:
        rows = audit(args.manifest)
    except ManifestError as exc:
        print(
            f"::error title=ci-pack-paths::cannot read the CI manifest: {exc}",
            flush=True,
        )
        return 2

    if args.report:
        _report(rows)
        return 0

    gaps = [row for row in rows if row["gaps"]]
    for row in gaps:
        for rel, why in row["gaps"]:
            print(
                f"::error title=ci-pack-paths::job {row['job']} declares "
                f"`paths:` but no entry matches {rel} ({why}). A pull request "
                f"touching only {rel} would SKIP this job. Fix: add a pattern "
                f'covering it (prefer the directory, e.g. "{Path(rel).parent}/**"). '
                "Never narrow the subject instead.",
                flush=True,
            )
    audited = len(rows)
    print(
        f"ci-pack paths: {audited} annotated job(s) audited, "
        f"{len(gaps)} with uncovered subjects."
    )
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
