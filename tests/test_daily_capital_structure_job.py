"""The capital-structure lane owns its own job, and its blast radius is itself.

`daily.yml`'s capital-structure chain is an all-or-nothing SEC publication
protocol.  Its compilers are FATAL BY DESIGN — no `continue-on-error`, no
quarantine, no fail-soft — because a partial generation must never be committed
(#4578 added `continue-on-error` to the event spine and was correctly reverted).

That contract is right for the lane and was catastrophic where the lane used to
live.  Inside `collect`, a fatal-by-design chain sat in the one job the whole
nightly hangs off, and three DISTINCT capital-structure defects redded the
entire nightly on three consecutive nights:

    2026-08-04  #4600  pyarrow schema unification broke manifest identity
    2026-08-05  #4640  the SEC-HEADER opener grammar EDGAR actually emits
    2026-08-06  #4740  observation-lineage bytes

Every fix was correct.  The PLACEMENT was the defect, so 2026-08-06 moved the
chain into the `capital_structure` job (`needs: collect`) that nothing needs in
turn.  These tests pin both halves: the lane keeps its undiluted all-or-nothing
law INSIDE the job, and the job cannot reach anything outside itself.

**The handoff is the load-bearing part of the split, and the least obvious.**
Every other post-collect job in this workflow (`us_scan_tier`, `collect_tail`)
reads its inputs from the COMMITTED tree.  This one cannot.  `run collectors`
(`sec_capital_structure`) APPENDS tonight's rows to the TRACKED
`source_manifest.jsonl`, and `collect`'s market checkpoint deliberately UNSTAGES
that path — an unaccepted source ledger must not be committed, and that carve-out
is exactly what preserves #4600's self-heal.  So tonight's rows exist only in
`collect`'s workspace and must cross the job boundary as an artifact.

If they did not, the failure would be silent rather than loud: a fresh
`actions/checkout` would serve the LAST COMMITTED ledger, the compilers would
reproduce yesterday byte-for-byte, "no capital-structure changes to commit"
would print, and the lane would freeze forever while every step stayed green.
Measured on this tree 2026-08-06: 1,258 rows committed against 1,447 in the run
— 189 rows a night lost, their retained R2 bytes orphaned.  So the download is
pinned to precede every compiler, and the receipt check that proves the bytes
are tonight's is pinned to be fatal.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github/workflows/daily.yml"

JOB = "capital_structure"
CS_COMMIT_STEP = "commit capital-structure data"
CS_PUSH_STEP = "push capital-structure data"
HANDOFF_VERIFY_STEP = "verify the capital-structure handoff"
HANDOFF_DOWNLOAD_STEP = "download the capital-structure workspace"

# Every module of the moved chain, valued by what its failure must cost.  The
# whole point of the move is that the answer is "this job, and nothing else".
CAPITAL_STRUCTURE_MODULES = {
    "scripts.materialize_capital_structure_share_counts":
        "share-count publication (pre-production, var-gated off)",
    "scripts.retain_capital_structure_share_counts":
        "retention lane (pre-production, double var-gated off)",
    "scripts.compile_capital_structure_events":
        "event spine — fail-closed by design (#4600 ManifestIdentityError)",
    "scripts.compile_capital_structure_document_terms":
        "term ledger — must not commit a partial ledger (#4640 SEC grammar)",
    "scripts.build_capital_structure_projection":
        "projection — canonical/public twin must stay byte-identical",
    "scripts.check_capital_structure_health":
        "ingestion-truth gate — selected filings with zero durable evidence must fail",
}

# The compilers that must stay fatal for their OWN checkpoint.  The two
# share-count steps are excluded on purpose: they are designed to be SKIPPED
# (repository variables default off).
FATAL_COMPILERS = (
    "scripts.compile_capital_structure_events",
    "scripts.compile_capital_structure_document_terms",
    "scripts.build_capital_structure_projection",
    "scripts.check_capital_structure_health",
)

# Staged path -> the step ids in THIS job that produce it.
#
# `cs_handoff` stands where `steps.collectors.outcome` stood before the split.
# `collectors` runs in `collect` and cross-job step outcomes are not
# referenceable in an `if:` — but this is not a weakening, it is the same
# producer named where it actually lands.  cs_handoff is the step that puts the
# collector's ledger in THIS tree and fails closed unless the bytes match the
# receipt `collect` stamped.
CS_STAGED_PATH_PRODUCERS = {
    "data/capital_structure": ("cs_handoff", "cs_spine", "cs_terms", "cs_projection", "cs_health"),
    "site/capital-structure-data": ("cs_handoff", "cs_spine", "cs_terms", "cs_projection", "cs_health"),
}
CS_GATING_PRODUCERS = sorted(
    {sid for ids in CS_STAGED_PATH_PRODUCERS.values() for sid in ids}
)


@pytest.fixture(scope="module")
def daily() -> dict:
    return yaml.safe_load(DAILY.read_text())


@pytest.fixture(scope="module")
def job(daily) -> dict:
    assert JOB in daily["jobs"], (
        f"daily.yml has no {JOB!r} job. The capital-structure chain is fatal by "
        "design; it must not move back into a job the nightly depends on."
    )
    return daily["jobs"][JOB]


@pytest.fixture(scope="module")
def steps(job) -> list[dict]:
    out = job.get("steps") or []
    assert out, f"the {JOB!r} job has no steps"
    return out


def _index_of(steps: list[dict], needle: str) -> int:
    for i, step in enumerate(steps):
        if needle in (step.get("name") or ""):
            return i
    raise AssertionError(f"no step whose name contains {needle!r}")


def _index_of_run(steps: list[dict], fragment: str) -> int:
    for i, step in enumerate(steps):
        if fragment in str(step.get("run") or ""):
            return i
    raise AssertionError(f"no step whose `run:` contains {fragment!r}")


def _needs(job: dict) -> list[str]:
    raw = job.get("needs") or []
    return [raw] if isinstance(raw, str) else list(raw)


def _is_shell_guarded(step: dict) -> bool:
    """True when every command in the step is `||`-guarded, so it cannot fail."""
    run = str(step.get("run") or "")
    if not run:
        return True
    run = re.sub(r"\\\n\s*", " ", run)
    body = [ln.strip() for ln in run.splitlines()]
    body = [ln for ln in body if ln and not ln.startswith("#")]
    if not body:
        return True
    return all(
        "||" in ln
        or ln.endswith(("then", "else", "fi", "do", "done", "esac", "{", "}"))
        or ln.startswith(("if ", "for ", "while ", "case ", "elif "))
        for ln in body
    )


# --------------------------------------------------------------------------
# THE BLAST RADIUS: the job exists, waits on collect, and nothing waits on it.
# --------------------------------------------------------------------------


def test_the_job_waits_on_collect(job):
    """It reads the tree `collect` commits and the ledger `collect` hands off."""
    assert _needs(job) == ["collect"], (
        f"the {JOB!r} job's needs are {_needs(job)!r}; it must need exactly "
        "['collect'] — the market tree it reads and the ledger artifact it "
        "verifies both come from that job, and widening `needs` re-couples this "
        "fatal-by-design lane to another job's schedule."
    )


def test_nothing_in_the_nightly_depends_on_this_job(daily):
    """THE point of the split, stated as the property it has to have.

    A capital-structure failure must red exactly one job. The moment something
    `needs:` this one, the three-nights-in-a-row defect class is back — a fatal-
    by-design chain sitting upstream of work that has nothing to do with it.
    """
    dependents = sorted(
        name for name, spec in daily["jobs"].items() if JOB in _needs(spec)
    )
    assert not dependents, (
        f"{dependents} now `needs: {JOB}`. That re-couples an all-or-nothing SEC "
        "publication protocol — whose compilers are deliberately fatal and may "
        "never be given continue-on-error — to unrelated nightly work. Read that "
        "job's inputs from the committed tree instead."
    )


def test_the_job_does_not_run_without_a_collect_that_succeeded(job):
    """No `if: always()` here, deliberately — and it is not the killed hard-gate.

    DNR:KILL-NIGHTLY-HARD-GATE forbids hard-gating the DASHBOARD jobs on
    collect's result (partial output beats shipping nothing). This job is not a
    dashboard job and nothing downstream is gated on it. Default `needs:`
    success semantics are the same fence the steps already had — a bare step
    inherits an implicit success(), so any earlier red in `collect` skipped them
    — and they are load-bearing: with no verified handoff there is no ledger to
    compile, and compiling the stale committed one is the silent freeze this
    suite exists to prevent.
    """
    cond = str(job.get("if") or "").strip()
    assert not cond, (
        f"the {JOB!r} job carries `if: {cond}`. An always() here would let the "
        "chain run on a night `collect` failed, where the handoff artifact does "
        "not exist and the tree holds only the committed ledger."
    )


@pytest.mark.parametrize("module,cost", sorted(CAPITAL_STRUCTURE_MODULES.items()))
def test_every_capital_structure_module_lives_in_this_job(daily, module, cost):
    """The chain moved WHOLE. A straggler left behind still reds the nightly."""
    home = sorted(
        name
        for name, spec in daily["jobs"].items()
        for step in (spec.get("steps") or [])
        if module in str(step.get("run") or "")
    )
    assert home == [JOB], (
        f"{module} ({cost}) runs in {home!r}, not exactly [{JOB!r}]. Every step of "
        "this fatal-by-design chain belongs in the isolated job; one left in "
        "`collect` reds the whole nightly by itself."
    )


# --------------------------------------------------------------------------
# THE HANDOFF: tonight's ledger, proven — never the committed one.
# --------------------------------------------------------------------------


def test_the_ledger_arrives_before_any_compiler_reads_it(steps):
    """Download, then verify, then compile — in that order, always.

    A download placed after `actions/checkout`/`git pull` is not decoration:
    either of those would overwrite the handed-off ledger with the committed
    copy, which is the silent-freeze mode this whole suite guards.
    """
    download = _index_of(steps, HANDOFF_DOWNLOAD_STEP)
    verify = _index_of(steps, HANDOFF_VERIFY_STEP)
    first_compiler = min(_index_of_run(steps, m) for m in CAPITAL_STRUCTURE_MODULES)
    assert download < verify < first_compiler, (
        f"order is download={download}, verify={verify}, first compiler="
        f"{first_compiler}. The ledger must be downloaded AND proven to be "
        "tonight's before a compiler reads it."
    )

    checkout_ats = [
        i for i, s in enumerate(steps) if "actions/checkout" in str(s.get("uses") or "")
    ]
    pull_ats = [
        i for i, s in enumerate(steps) if "git pull origin main" in str(s.get("run") or "")
    ]
    assert all(at < download for at in checkout_ats + pull_ats), (
        "an actions/checkout or `git pull` runs AFTER the artifact download "
        f"(checkout={checkout_ats}, pull={pull_ats}, download={download}). Either "
        "would replace the handed-off ledger with the committed one and the lane "
        "would recompile yesterday forever, green."
    )


def test_the_handoff_verification_is_fatal(steps):
    """It is the one check standing between this job and a frozen lane.

    `continue-on-error` or a `|| echo` guard here would turn a missing/mis-pathed
    artifact into a green no-op night, which is precisely the failure the receipt
    exists to make impossible.
    """
    step = steps[_index_of(steps, HANDOFF_VERIFY_STEP)]
    assert step.get("continue-on-error") is not True, (
        "the handoff verification carries continue-on-error; a failed handoff "
        "would then be laundered into a compile against the stale committed ledger"
    )
    assert not _is_shell_guarded(step), (
        "the handoff verification is `||`-guarded, so it can no longer fail and "
        "cannot stop a stale-ledger compile"
    )


def test_the_verification_compares_against_collects_own_receipt(steps):
    """A self-consistent check proves nothing — it must name collect's outputs.

    Recomputing a hash and comparing it to itself, or merely asserting the file
    exists, passes on exactly the tree this guard is meant to reject: the fresh
    checkout's committed ledger. The comparison has to be against the receipt the
    producing job stamped.
    """
    step = steps[_index_of(steps, HANDOFF_VERIFY_STEP)]
    blob = str(step.get("run") or "") + str(step.get("env") or "")

    for output in ("capital_structure_ledger_sha256", "capital_structure_ledger_rows"):
        assert f"needs.collect.outputs.{output}" in blob, (
            f"the handoff verification does not read needs.collect.outputs.{output}. "
            "Without the producing job's receipt it cannot tell tonight's ledger "
            "from the committed one."
        )
    assert "source_manifest.jsonl" in blob, (
        "the verification does not name source_manifest.jsonl — the ledger whose "
        "freshly appended rows are the entire reason the artifact exists"
    )
    assert "exit 1" in str(step.get("run") or ""), (
        "the verification never exits non-zero, so a mismatch cannot stop the "
        "compile chain"
    )


def test_the_handoff_artifact_survives_a_job_rerun(daily, steps):
    """The artifact name must be RUN-scoped, never attempt-scoped.

    "Re-run failed jobs" increments `github.run_attempt` for the whole run while
    re-executing only the failed job. An attempt-scoped artifact name therefore
    makes this job impossible to re-run on its own: attempt 2 would look for a
    name only attempt 1 ever uploaded, the download would fail, and the operator's
    most obvious recovery action would be permanently broken — on the very lane
    that failed three nights running.

    The two names must also be byte-identical, because a download naming anything
    the upload did not produce fails closed on every night, not just on a re-run.
    """
    upload = next(
        s for s in daily["jobs"]["collect"]["steps"]
        if "upload-artifact" in str(s.get("uses") or "")
        and "capital-structure" in str((s.get("with") or {}).get("name") or "")
    )
    download = next(
        s for s in steps if "download-artifact" in str(s.get("uses") or "")
    )
    up_name = str(upload["with"]["name"])
    down_name = str(download["with"]["name"])

    assert up_name == down_name, (
        f"the handoff artifact is uploaded as {up_name!r} and downloaded as "
        f"{down_name!r}. A mismatch fails closed every night."
    )
    assert "github.run_attempt" not in up_name, (
        f"the handoff artifact name {up_name!r} is attempt-scoped. Re-running just "
        "the capital_structure job bumps github.run_attempt without re-running "
        "collect, so the artifact it wants would never have been uploaded."
    )
    assert "github.run_id" in up_name, (
        f"the handoff artifact name {up_name!r} is not run-scoped; a fixed name "
        "would let one night's run download another night's ledger"
    )
    assert upload["with"].get("overwrite") is True, (
        "collect's upload needs `overwrite: true`: re-running the WHOLE workflow "
        "re-runs collect, which must replace its own run-scoped artifact instead "
        "of failing on the duplicate name."
    )


def test_collect_stamps_the_receipt_without_risking_the_night(daily):
    """The producing half: it must publish the receipt and must never red collect.

    Both directions matter. No receipt => this job cannot prove freshness. A
    receipt step that can fail `collect` => a capital-structure concern reds the
    nightly again, through the very change that was supposed to stop that.
    """
    collect = daily["jobs"]["collect"]
    outputs = collect.get("outputs") or {}
    for output in ("capital_structure_ledger_sha256", "capital_structure_ledger_rows"):
        assert output in outputs, (
            f"the collect job no longer publishes {output!r}. The capital_structure "
            "job needs it to prove the artifact it downloaded is tonight's ledger."
        )

    handoff_steps = [
        s
        for s in collect["steps"]
        if "capital-structure handoff receipt" in (s.get("name") or "")
        or "hand the capital-structure workspace" in (s.get("name") or "")
    ]
    assert len(handoff_steps) == 2, (
        f"expected the stamp + upload pair in collect, found {len(handoff_steps)}"
    )
    for step in handoff_steps:
        assert step.get("continue-on-error") is True, (
            f"collect's {step.get('name')!r} can fail the collect job. The whole "
            "split exists so no capital-structure concern can red the job the "
            "nightly hangs off — a failed handoff must fail CLOSED one job over, "
            "in the capital_structure job's verification, not here."
        )


# --------------------------------------------------------------------------
# THE LAW INSIDE THE JOB: all-or-nothing, undiluted by the move.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module", FATAL_COMPILERS)
def test_compile_steps_stay_fatal_for_their_own_checkpoint(steps, module):
    """Isolation must not be mistaken for permission to fail soft (#4578).

    The split makes these steps harmless to the rest of the nightly. It must not
    make them harmless to their OWN generation: a compile failure has to keep the
    rejected ledger out of git.
    """
    step = steps[_index_of_run(steps, module)]
    assert "continue-on-error" not in step, (
        f"{module} carries continue-on-error, so it stops failing and a torn "
        "generation rides the capital-structure checkpoint (#4578 tried exactly "
        "this and was reverted)"
    )
    assert not _is_shell_guarded(step), (
        f"{module} is shell-guarded (`|| echo`), so it can no longer fail and its "
        "checkpoint would commit whatever half-generation it left behind"
    )


def test_the_checkpoint_stages_only_its_own_generation(steps):
    """Narrow staging: exactly the generation and its byte-identical twin.

    A broad `git add data/` here would sweep another lane's runner-tree bytes to
    main under a commit the capital-structure chain can veto — the coupling the
    split removed, reintroduced from the other end.
    """
    run = str(steps[_index_of(steps, CS_COMMIT_STEP)]["run"])
    add_lines = [ln.strip() for ln in run.splitlines() if ln.strip().startswith("git add ")]
    assert add_lines, f"{CS_COMMIT_STEP!r} no longer contains a `git add`"

    staged = {p for line in add_lines for p in line.split()[2:] if not p.startswith("-")}
    assert staged == set(CS_STAGED_PATH_PRODUCERS), (
        f"{CS_COMMIT_STEP!r} stages {sorted(staged)}; it may stage exactly "
        f"{sorted(CS_STAGED_PATH_PRODUCERS)} and nothing else."
    )
    assert not any(p in {"data/", "data", "site/", "site", "."} for p in staged), (
        "a broad add here carries unrelated lanes' bytes on a vetoable checkpoint"
    )


def test_the_checkpoint_gate_names_exactly_the_producers_of_its_staged_paths(steps):
    """Bidirectional: every producer present, and nothing that is not one.

    (a) a missing producer means a partial tree can be checkpointed;
    (b) an extra name lets an unrelated step veto a generation that did compile.
    """
    cond = str(steps[_index_of(steps, CS_COMMIT_STEP)].get("if") or "")
    assert cond, f"{CS_COMMIT_STEP!r} has no `if:` — it inherits success()"

    refs = set(re.findall(r"steps\.([A-Za-z0-9_-]+)\.", cond))
    missing = set(CS_GATING_PRODUCERS) - refs
    assert not missing, (
        f"{CS_COMMIT_STEP!r} does not gate on {sorted(missing)}, which produce the "
        f"tree it stages. if: {cond}"
    )
    extra = refs - set(CS_GATING_PRODUCERS)
    assert not extra, (
        f"{CS_COMMIT_STEP!r} gates on {sorted(extra)}, which do not PRODUCE its "
        f"staged tree. if: {cond}"
    )


def test_the_checkpoint_gate_blocks_a_skipped_producer_like_a_failed_one(steps):
    """`.outcome == 'success'` is the only comparison that blocks 'skipped'.

    `!= 'failure'` lets a SKIPPED producer through, and `.conclusion` is laundered
    to 'success' by a continue-on-error — which matters most here, where the whole
    contract is that the compilers stay fatal. A future `continue-on-error:` on a
    compiler must not buy this commit.
    """
    cond = str(steps[_index_of(steps, CS_COMMIT_STEP)].get("if") or "")
    for step_id in CS_GATING_PRODUCERS:
        assert f"steps.{step_id}.outcome == 'success'" in cond, (
            f"the gate on {step_id!r} must be exactly `steps.{step_id}.outcome == "
            f"'success'`. if: {cond}"
        )
    assert ".conclusion" not in cond, (
        f"the gate uses `.conclusion`, which continue-on-error rewrites to "
        f"'success'. if: {cond}"
    )
    assert "always()" in cond, (
        "without a status function the checkpoint inherits an implicit success() "
        f"and any earlier red in this job skips it. if: {cond!r}"
    )
    assert cond.strip() != "always()", (
        "a bare always() is the 2026-08-04 P0 shape — the commit outrunning its "
        "skipped producers. Name the producing steps."
    )
    assert "success()" not in cond, (
        "success() is job-wide status, not a named producer. if: {cond!r}"
    )


def test_gated_producer_ids_actually_exist(steps):
    """A gate naming a step that does not exist can never be satisfied."""
    ids = {s.get("id") for s in steps if s.get("id")}
    missing = [sid for sid in CS_GATING_PRODUCERS if sid not in ids]
    assert not missing, (
        f"the checkpoint gate names step ids {missing} that no step in the {JOB!r} "
        "job declares — the expression evaluates to '' and the commit could never "
        "run. (`collectors` lives in `collect`; cross-job step outcomes are not "
        "referenceable, which is why `cs_handoff` stands in its place.)"
    )


def test_the_checkpoint_keeps_the_commit_push_split(steps):
    """Local commit in its own step; network publish in another (2026-07-17).

    Run 29542087837: a hung `git push` ate 57m and the job cap killed the step
    mid-publish, so an already-collected night existed only on the runner.
    """
    commit_at = _index_of(steps, CS_COMMIT_STEP)
    push_at = _index_of(steps, CS_PUSH_STEP)
    assert commit_at < push_at

    commit, push = steps[commit_at], steps[push_at]
    commit_run, push_run = str(commit.get("run") or ""), str(push.get("run") or "")

    assert "git commit -m" in commit_run
    assert "git push" not in commit_run and "push_do" not in commit_run, (
        "the commit step performs the network push itself — the 2026-07-17 defect"
    )
    assert "git commit" not in push_run
    assert "scripts/ci/push_retry.sh" in push_run, (
        "the push lost the shared retry policy (contention/conflict split, backoff)"
    )
    assert "perl -e 'alarm" in push_run, (
        "unbounded git network op: macOS runners have no GNU timeout, so only the "
        "perl alarm can kill a hung fetch/pull"
    )

    cond = str(push.get("if") or "")
    assert "always()" in cond, (
        f"the push has `if: {cond or '<none>'}`, which carries no status function, "
        "so an earlier red skips the publish of an already-made commit"
    )
    assert f"steps.{commit.get('id')}.outputs.committed == 'true'" in cond, (
        f"the push must be gated on the commit's own `committed` output; if: {cond}"
    )


def test_rejected_ledger_capture_still_follows_the_whole_chain(steps):
    """`if: failure()` only sees failures that already happened.

    Run 30997579632: the capture sat under the event spine, the document-terms
    compiler two steps later failed, and the capture was SKIPPED. It must stay
    below every capital-structure step.
    """
    capture = _index_of(steps, "capture the rejected capital-structure ledger")
    assert str(steps[capture].get("if") or "").strip() == "failure()"
    last = max(_index_of_run(steps, m) for m in CAPITAL_STRUCTURE_MODULES)
    assert capture > last, (
        "the diagnostics capture moved above a capital-structure step; it would "
        "then fire only for the steps that precede it (run 30997579632)"
    )


def test_the_job_is_declared_in_the_dag(steps):
    """config/dag.yml must carry the lane, in the job's real serial order.

    `scripts/check_dag_conformance.py` compares declared modules against the
    workflow per (workflow, job). A chain that moves jobs without moving its lane
    declaration leaves the DAG describing a job layout that no longer exists.
    """
    dag = yaml.safe_load((ROOT / "config/dag.yml").read_text())
    lanes = [
        lane
        for lane in dag["lanes"]
        if lane.get("workflow") == ".github/workflows/daily.yml"
        and lane.get("job") == JOB
    ]
    assert len(lanes) == 1, (
        f"config/dag.yml declares {len(lanes)} lanes for daily.yml / {JOB}; expected "
        "exactly one"
    )
    declared = [s["id"] for s in lanes[0]["steps"]]
    actual = [
        m
        for m in (
            str(step.get("run") or "").split("python -m ")[-1].split()[0]
            if "python -m " in str(step.get("run") or "")
            else None
            for step in steps
        )
        if m
    ]
    actual_ids = [m.rsplit(".", 1)[-1] for m in actual if m.startswith("scripts.")]
    assert declared == actual_ids, (
        f"config/dag.yml declares {declared} for {JOB}, the workflow runs "
        f"{actual_ids}. The lane must match the job's real serial order."
    )


# ──────────────────────────────────────────────────────────────────────────────
# CS push-loop fence: append-only fence call is after fetch and before rebase
# ──────────────────────────────────────────────────────────────────────────────

_PUSH_STEP_FRAGMENT = "push capital-structure"
_FENCE_CALL = "push_append_only_fence"
_FETCH_FRAGMENT = "git fetch"
_REBASE_FRAGMENT = "pull --rebase"


def _pushcs_run(steps: list[dict]) -> str:
    """Return the `run:` script of the CS push step."""
    for step in steps:
        if _PUSH_STEP_FRAGMENT in (step.get("name") or ""):
            return str(step.get("run") or "")
    for step in steps:
        sid = step.get("id") or ""
        if "pushcs" in sid or "push_cs" in sid:
            return str(step.get("run") or "")
    raise AssertionError(
        f"no pushcs step found (looked for name containing {_PUSH_STEP_FRAGMENT!r} "
        "or id containing 'pushcs')"
    )


def test_cs_push_loop_calls_append_only_fence(steps):
    """daily.yml's CS push loop must call push_append_only_fence.

    DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE: the fence runs after fetch
    and before rebase -X theirs so a proven source_manifest.jsonl prefix drop
    withholds the whole CS family before any --autostash stash-pop can reintroduce
    the stale generation.
    """
    run_script = _pushcs_run(steps)
    assert _FENCE_CALL in run_script, (
        f"the CS push step must call {_FENCE_CALL!r}; "
        "without it, overlapping CS jobs can clobber coherent generations (#5792 ext)"
    )


def test_cs_push_fence_is_after_fetch_before_rebase(steps):
    """The fence call must appear AFTER a git fetch and BEFORE pull --rebase."""
    run_script = _pushcs_run(steps)
    assert _FETCH_FRAGMENT in run_script, (
        f"CS push step must fetch before fencing; no {_FETCH_FRAGMENT!r} found"
    )
    assert _REBASE_FRAGMENT in run_script, (
        f"CS push step must rebase after fencing; no {_REBASE_FRAGMENT!r} found"
    )
    fence_pos = run_script.index(_FENCE_CALL)
    fetch_pos = run_script.index(_FETCH_FRAGMENT)
    rebase_pos = run_script.index(_REBASE_FRAGMENT)
    assert fetch_pos < fence_pos, "fence must come AFTER fetch"
    assert fence_pos < rebase_pos, "fence must come BEFORE rebase"
