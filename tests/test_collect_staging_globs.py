"""Staging-glob invariant for collect-lane commit steps (neural-web D7).

The qledger grader runs inside every ``scripts.collect`` invocation
(scripts/collect.py -> grade_qledger.run_as_collect_step) and rewrites the
TRACKED ``site/qledger/track_record.json`` (un-ignored by #1139).  Left
unstaged, that tracked modification makes ``git pull --rebase`` refuse with
"unstaged changes", the push loop dies after 5 attempts with only a swallowed
warning, and the night's collection is silently lost — the 2026-07-03 and
2026-07-04 daily collections went exactly this way.

The invariant is therefore about the FIRST checkpoint of a collect job, not
about every commit step in it.  Since #4731 (2026-08-06) the daily collect job
checkpoints twice: a market checkpoint that stages ``data/ site/qledger/``, and
a deliberately narrow capital-structure checkpoint that stages only
``data/capital_structure site/capital-structure-data`` so a capital-structure
veto can no longer cost the night's market data.  A broad ``git add`` in that
second step would re-open the coupling the split removed, so demanding
``site/qledger/`` from it is wrong — by the time it runs the qledger is already
committed, and there is nothing left for a rebase to trip on.

What keeps that safe is ordering, and ordering is what these tests pin:
  * the first commit step in a collect job stages ``site/qledger/``, so the
    grader's tracked write is committed before any push step's rebase; and
  * every later commit step is gated on at least the step outcomes the first
    one is gated on, so it can never run in a state where the first did not.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# workflows whose jobs invoke scripts.collect (the qledger grader runs in all of them)
COLLECT_WORKFLOWS = ["daily.yml", "asia-close.yml"]

# `steps.<id>.outcome == 'success'` and friends, as written in a workflow `if:`
_GATE_TERM = re.compile(
    r"steps\.([A-Za-z0-9_-]+)\.(outcome|conclusion)\s*==\s*'([a-z]+)'"
)


def _uncommented(body: str) -> str:
    """Drop whole-line shell comments from a `run` body.

    The `git add` scan below is a plain regex over the body, and these bodies
    carry long prose comments that quote the very commands they explain (the
    market checkpoint's own comment block names ``git add data/`` three times).
    Without this, a step that DELETED its real ``git add site/qledger/`` would
    still satisfy the assertion on the strength of a comment mentioning it.
    """
    return "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )


def _staged_paths(step: dict) -> str:
    """Space-joined pathspecs this step actually stages."""
    return " ".join(re.findall(r"git add ([^\n]+)", _uncommented(step.get("run", ""))))


def _gate_terms(step: dict) -> set[tuple[str, str, str]]:
    """The (step_id, field, value) conditions in this step's `if:`."""
    return set(_GATE_TERM.findall(str(step.get("if", "") or "")))


def _collect_commit_jobs(wf_path: Path) -> dict[str, list[dict]]:
    """job name -> its git-committing steps, in workflow order.

    Only jobs that invoke ``scripts.collect`` are considered — those are the
    jobs in which the qledger grader runs and leaves a tracked write behind.
    """
    doc = yaml.safe_load(wf_path.read_text())
    jobs: dict[str, list[dict]] = {}
    for name, job in (doc.get("jobs") or {}).items():
        steps = [s for s in (job.get("steps") or []) if s.get("run")]
        if not any("scripts.collect" in s["run"] for s in steps):
            continue
        commits = [
            s for s in steps if "git add" in s["run"] and "git commit" in s["run"]
        ]
        if commits:
            jobs[name] = commits
    return jobs


def test_collect_workflows_parse():
    for name in COLLECT_WORKFLOWS:
        yaml.safe_load((WORKFLOWS / name).read_text())


def test_collect_jobs_have_commit_steps():
    for name in COLLECT_WORKFLOWS:
        assert _collect_commit_jobs(WORKFLOWS / name), (
            f"{name}: no commit step found in the scripts.collect job — "
            "test needs updating if the lane was restructured"
        )


def test_collect_commit_steps_stage_qledger():
    """The FIRST commit step of every collect job must stage site/qledger/.

    (Or all of site/, which covers it.)  Later, deliberately narrow checkpoints
    are fine — see the module docstring and
    test_later_collect_checkpoints_cannot_outrun_the_qledger_checkpoint, which
    is what makes them safe.
    """
    for name in COLLECT_WORKFLOWS:
        for job, commits in _collect_commit_jobs(WORKFLOWS / name).items():
            staged = _staged_paths(commits[0])
            assert "site/qledger" in staged or re.search(r"\bsite/?(\s|$)", staged), (
                f"{name}: job {job!r}: its FIRST commit step "
                f"({commits[0].get('name') or commits[0].get('id')!r}) stages only "
                f"({staged!r}) — site/qledger/track_record.json is written by the "
                "qledger grader during collect and MUST be committed by that first "
                "checkpoint, else the rebase+push dies on 'unstaged changes' and the "
                "night's data is silently lost (2026-07-03, 2026-07-04)"
            )


def test_later_collect_checkpoints_cannot_outrun_the_qledger_checkpoint():
    """A later checkpoint may stage narrowly only because it can never run alone.

    This is the load-bearing half of the relaxation above.  The daily job's
    capital-structure checkpoint stages no qledger path; that is safe purely
    because its `if:` requires everything the market checkpoint's `if:` requires
    (plus the three capital-structure producers), so it cannot fire in a state
    where the qledger was left uncommitted.  Drop that coupling — a new
    checkpoint gated on `always()` alone, say — and the 07-03 loss is back with
    nothing else in the suite watching for it.
    """
    for name in COLLECT_WORKFLOWS:
        for job, commits in _collect_commit_jobs(WORKFLOWS / name).items():
            required = _gate_terms(commits[0])
            for step in commits[1:]:
                staged = _staged_paths(step)
                if "site/qledger" in staged or re.search(r"\bsite/?(\s|$)", staged):
                    continue  # stages the qledger itself; ordering is moot
                missing = required - _gate_terms(step)
                assert not missing, (
                    f"{name}: job {job!r}: commit step "
                    f"({step.get('name') or step.get('id')!r}) stages ({staged!r}) — "
                    "no qledger path — but its `if:` drops "
                    f"{sorted(missing)}, which the first checkpoint requires. It can "
                    "therefore run when the qledger checkpoint did NOT, leaving the "
                    "grader's tracked write unstaged for this step's rebase+push. "
                    "Either stage site/qledger/ here too, or gate this step on at "
                    "least the first checkpoint's conditions."
                )
