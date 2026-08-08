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

#4746 (2026-08-07) then moved the whole capital-structure chain into its own
job, so no collect job carries that second checkpoint any more.  What daily.yml
does carry is a different shape: the chain-snapshot salvage step (#4705), gated
on ``collectors.outcome != 'success'`` — the exact NEGATION of the market
checkpoint's gate.  It is not a later checkpoint racing the first; it is the
other side of a fork, and it exists precisely because the market commit was
skipped.  Demanding the market checkpoint's gate from it would make it
unsatisfiable, and demanding ``site/qledger/`` from it would publish a
track_record.json graded on a collect run that FAILED.

What keeps all of this safe is ordering, and ordering is what these tests pin:
  * the first commit step in a collect job stages ``site/qledger/``, so the
    grader's tracked write is committed before any push step's rebase; and
  * every later commit step either is gated on at least the step outcomes the
    first one is gated on (SUBSET — it cannot run in a state where the first did
    not), or negates one of them (FORK — it cannot run in the same branch at all)
    while carrying ``--autostash`` on its own rebase, which is what actually
    stops the grader's unstaged write from refusing that rebase.
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

# The same term NEGATED — `steps.<id>.outcome != 'success'`.  A step carrying the
# negation of a term the first checkpoint REQUIRES runs in the disjoint branch: the
# two can never both fire in one run.  See _outruns_the_qledger_checkpoint.
_NEGATED_GATE_TERM = re.compile(
    r"steps\.([A-Za-z0-9_-]+)\.(outcome|conclusion)\s*!=\s*'([a-z]+)'"
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


def _negated_gate_terms(step: dict) -> set[tuple[str, str, str]]:
    """The (step_id, field, value) conditions this step's `if:` requires to be FALSE."""
    return set(_NEGATED_GATE_TERM.findall(str(step.get("if", "") or "")))


def _outruns_the_qledger_checkpoint(required: set, step: dict) -> str | None:
    """Why `step` may push with the grader's write uncommitted — or None if it cannot.

    Factored out so the workflow scan below and the exemption-is-narrow unit tests
    exercise the SAME predicate; a mirrored re-implementation in the unit tests would
    pass while the real rule rotted.
    """
    staged = _staged_paths(step)
    if "site/qledger" in staged or re.search(r"\bsite/?(\s|$)", staged):
        return None  # stages the qledger itself; ordering is moot

    missing = required - _gate_terms(step)
    if not missing:
        return None  # requires everything the first checkpoint requires

    # MUTUALLY EXCLUSIVE BRANCH.  A step gated on the NEGATION of a term the first
    # checkpoint requires (`collectors.outcome != 'success'` against its
    # `== 'success'`) is not a later checkpoint at all — it is the other side of a
    # fork, and the two provably never both run.  daily.yml's chain-snapshot salvage
    # is exactly this: it exists BECAUSE the market commit was skipped, so demanding
    # the market commit's own gate would make it unsatisfiable, and demanding it
    # stage site/qledger/ would publish a track_record.json graded on a collect run
    # that FAILED — the "bulk tree committed ahead of its skipped normalizers" P0
    # that the market checkpoint's own comment block warns against.
    #
    # The exemption is CONDITIONAL, not a pass.  The hazard this suite exists for is
    # a rebase refusing on the grader's unstaged tracked write, so the fork's own
    # rebase must carry --autostash — the mitigation daily.yml already names as "the
    # durable guard ... survives ANY stray tracked write collect leaves outside
    # data/+site/qledger/".  Verified here rather than assumed: a fork branch that
    # rebases WITHOUT it reopens 07-03 in its own lane and still fails.
    if _negated_gate_terms(step) & required:
        if "--autostash" in _uncommented(step.get("run", "") or ""):
            return None
        return (
            "runs in the branch where the first checkpoint was SKIPPED by "
            f"construction (it negates {sorted(_negated_gate_terms(step) & required)}), "
            "which is legitimate — but its own rebase does not use --autostash, so "
            "the grader's unstaged tracked write can still refuse the rebase and lose "
            "this step's commit. Add --autostash to its `git pull --rebase`."
        )

    return (
        f"its `if:` drops {sorted(missing)}, which the first checkpoint requires. It "
        "can therefore run when the qledger checkpoint did NOT, leaving the grader's "
        "tracked write unstaged for this step's rebase+push. Either stage "
        "site/qledger/ here too, or gate this step on at least the first "
        "checkpoint's conditions."
    )


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
    """A narrow later commit step is safe only if it cannot push behind a skipped qledger.

    This is the load-bearing half of the relaxation above.  Two shapes satisfy it:

      SUBSET     — the step's `if:` requires everything the first checkpoint's does,
                   so by the time it runs the qledger is already committed.  This was
                   #4731's capital-structure checkpoint (since moved to its own job by
                   #4746, so no collect job carries one today).

      FORK       — the step's `if:` NEGATES a term the first checkpoint requires, so the
                   two are disjoint and it is not a "later checkpoint" at all.  daily.yml's
                   chain-snapshot salvage (`collectors.outcome != 'success'`, #4705) is
                   this: it runs BECAUSE the market commit was skipped.  Exempt only
                   while its own rebase carries --autostash — see
                   _outruns_the_qledger_checkpoint, which checks that rather than
                   assuming it.

    Anything else — a new checkpoint gated on `always()` alone, say — and the 07-03 loss
    is back with nothing else in the suite watching for it.
    """
    for name in COLLECT_WORKFLOWS:
        for job, commits in _collect_commit_jobs(WORKFLOWS / name).items():
            required = _gate_terms(commits[0])
            for step in commits[1:]:
                reason = _outruns_the_qledger_checkpoint(required, step)
                assert reason is None, (
                    f"{name}: job {job!r}: commit step "
                    f"({step.get('name') or step.get('id')!r}) stages "
                    f"({_staged_paths(step)!r}) — no qledger path — and {reason}"
                )


class TestTheForkExemptionStaysNarrow:
    """Guard the guard: the FORK carve-out must not become a way past the rule.

    These drive the real predicate, not a copy of it, so a regression in
    _outruns_the_qledger_checkpoint fails here instead of passing a mirror.
    """

    REQUIRED = {("collectors", "outcome", "success")}
    NARROW = 'git add -- "$f"\ngit commit -m x\n'
    REBASE = "git pull --rebase --autostash -X theirs origin main\n"

    def _step(self, gate: str, run: str) -> dict:
        return {"name": "synthetic", "if": gate, "run": run}

    def test_the_real_salvage_shape_is_exempt(self):
        step = self._step(
            "always() && steps.collectors.outcome != 'success'", self.NARROW + self.REBASE
        )
        assert _outruns_the_qledger_checkpoint(self.REQUIRED, step) is None

    def test_a_fork_without_autostash_still_fails(self):
        """The exemption is conditional on the mitigation actually being there."""
        step = self._step(
            "always() && steps.collectors.outcome != 'success'",
            self.NARROW + "git pull --rebase -X theirs origin main\n",
        )
        reason = _outruns_the_qledger_checkpoint(self.REQUIRED, step)
        assert reason is not None and "--autostash" in reason

    def test_a_bare_always_checkpoint_still_fails(self):
        """The docstring's own counter-example must stay red."""
        step = self._step("always()", self.NARROW + self.REBASE)
        reason = _outruns_the_qledger_checkpoint(self.REQUIRED, step)
        assert reason is not None and "drops" in reason

    def test_negating_an_UNRELATED_step_is_not_a_fork(self):
        """`!=` on some other step proves nothing about this checkpoint's branch."""
        step = self._step(
            "always() && steps.something_else.outcome != 'success'",
            self.NARROW + self.REBASE,
        )
        reason = _outruns_the_qledger_checkpoint(self.REQUIRED, step)
        assert reason is not None and "drops" in reason

    def test_a_comment_mentioning_autostash_does_not_count(self):
        """_uncommented is load-bearing here, same as it is for `git add`."""
        step = self._step(
            "always() && steps.collectors.outcome != 'success'",
            self.NARROW + "# we deliberately skip --autostash here\n"
            "git pull --rebase -X theirs origin main\n",
        )
        reason = _outruns_the_qledger_checkpoint(self.REQUIRED, step)
        assert reason is not None and "--autostash" in reason

    def test_a_subset_step_is_still_exempt(self):
        """The original SUBSET shape must keep working (no collect job has one today)."""
        step = self._step(
            "always() && steps.collectors.outcome == 'success' "
            "&& steps.cs_build.outcome == 'success'",
            self.NARROW + self.REBASE,
        )
        assert _outruns_the_qledger_checkpoint(self.REQUIRED, step) is None
