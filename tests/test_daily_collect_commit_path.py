"""Which steps may cost a night of market data — bounded, named, and visible.

`daily.yml`'s `collect` job spends up to ~3 hours pulling the market data plane
(235 `data/stocks` names, `data/baskets/ohlcv`, the breadth close caches).  The
collected bytes live only on the runner, where the next job's `actions/checkout`
deletes them, so the ONLY thing that makes a night real is a commit that lands.

**Updated 2026-08-06 — first the checkpoint split, then the JOB split.**

    run collectors
      -> additive producers (Finviz, ZORI) + the two store tripwires
      -> "commit market data" + "push market data"      <-- the checkpoint
      -> salvage push (cancel path)
      -> the capital-structure handoff (stamp receipt, upload artifact)
      -> the two R2 store publishes

Before the checkpoint split there was ONE commit and it sat AFTER the
capital-structure chain.  Two earlier fixes had already narrowed the damage —
the commit gates on NAMED producers (`steps.collectors.outcome == 'success'`)
rather than job status, and the capital-structure paths were carved out of it
when the chain failed — so a capital-structure failure no longer DISCARDED the
collection outright.  What neither fix could remove is the WINDOW: ~3h of
collected bytes stayed unpublished for the whole length of the capital-structure
chain, one job-cap cancel, runner death, or host-disk fault away from being
deleted by the next checkout.  Six consecutive nights from 2026-08-01 went that
way, through four unrelated defects (#4534 duck-typing, runner ENOSPC, #4600
ledger identity, #4640 SEC grammar), and `data/stocks` froze at 2026-07-31.

**The chain then left this job entirely.**  Even below the checkpoint it was
still a fatal-by-design lane inside the job the whole nightly hangs off, and it
redded the nightly on three consecutive nights for three unrelated causes (#4600
08-04, #4640 08-05, #4740 08-06).  It now runs in the `capital_structure` job
(`needs: collect`), which nothing needs in turn.  That job's own law — the
all-or-nothing checkpoint, the fatal compilers, the narrow staging, the receipt
that proves it compiled TONIGHT's ledger — is pinned by
`tests/test_daily_capital_structure_job.py`.  This file keeps the market side.

**What this job still owes the capital-structure lane** is the carve-out and the
handoff, and they are two halves of one contract.  `run collectors`
(`sec_capital_structure`) rewrites the TRACKED `source_manifest.jsonl` long
before any compiler validates it, so the market checkpoint UNSTAGES those paths
— and must never `git checkout` them, because that freshly collected ledger is
the compilers' INPUT.  Unstaged means uncommitted, which means the ledger cannot
reach the next job through git at all: it goes as an artifact, with a
sha256/row-count receipt published as a job output.  Both handoff steps are
`continue-on-error`, because the entire point of the split is that no
capital-structure concern may red THIS job; a failed handoff fails closed one job
over instead.

So `DELIBERATE_VETO_STEPS` below is now EMPTY, which is the whole point: every
step that used to be on it left the job.  The allowlist stays because it is the
thing that keeps a future re-coupling deliberate — a new unguarded step between
the collectors and the market commit is almost always an oversight (the house
idiom is `|| echo "::warning::..."` or `continue-on-error: true`), and adding one
to the list is the act that writes the cost down for the next reader.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.workflow_run_source import resolve_run_source  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github/workflows/daily.yml"

MARKET_COMMIT_STEP = "commit market data"
MARKET_PUSH_STEP = "push market data"
COLLECTORS_STEP = "run collectors"
HANDOFF_STAMP_STEP = "stamp the capital-structure handoff receipt"
HANDOFF_UPLOAD_STEP = "hand the capital-structure workspace to its own job"

# Steps that MAY fail the collect job before "commit market data", and why.  Every
# entry costs the night's market collection when it fires — that would be an
# accepted price, not an accident.  Keyed by a distinctive fragment of the step's
# `run:`.
#
# EMPTY since the 2026-08-06 two-checkpoint split.  It used to hold all five
# capital-structure steps; they now run AFTER the market checkpoint and answer to
# their own commit, so nothing between the collectors and the market commit may
# fail the job at all.  Keep the mechanism: an entry added here is a deliberate,
# reviewed decision to put a night of collection behind one more step.
DELIBERATE_VETO_STEPS: dict[str, str] = {}

# The chain that must stay OUT of this job entirely. Keyed by the `python -m`
# module each step runs, valued by what it would cost if it came back.
CAPITAL_STRUCTURE_STEPS = {
    "scripts.materialize_capital_structure_share_counts":
        "share-count publication (pre-production, var-gated off)",
    "scripts.retain_capital_structure_share_counts":
        "retention lane (pre-production, double var-gated off)",
    "scripts.compile_capital_structure_events":
        "event spine — fail-closed by design (#4600 ManifestIdentityError, 08-05)",
    "scripts.compile_capital_structure_document_terms":
        "term ledger — must not commit a partial ledger (#4640 SEC grammar)",
    "scripts.build_capital_structure_projection":
        "projection — canonical/public twin must stay byte-identical",
}


@pytest.fixture(scope="module")
def collect_steps() -> list[dict]:
    doc = yaml.safe_load(DAILY.read_text())
    steps = doc["jobs"]["collect"]["steps"]
    assert steps, "collect job has no steps — workflow shape changed"
    return steps


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


def _is_non_fatal(step: dict) -> bool:
    """True when this step cannot fail the job."""
    if step.get("continue-on-error") is True:
        return True
    run = step.get("run") or ""
    if not run:
        return True  # `uses:` action steps are not the veto class this guards
    # Join backslash continuations FIRST: the house idiom puts the `|| echo` guard
    # on the continuation line ("python foo.py \\\n  || echo ..."), so a physical
    # line scan reads a guarded command as bare.
    run = re.sub(r"\\\n\s*", " ", run)
    body = [ln.strip() for ln in run.splitlines()]
    body = [ln for ln in body if ln and not ln.startswith("#")]
    if not body:
        return True
    return all("||" in ln or ln.endswith(("then", "else", "fi", "do", "done", "esac", "{", "}"))
               or ln.startswith(("if ", "for ", "while ", "case ", "elif "))
               for ln in body)


def _veto_reason(step: dict) -> str | None:
    run = str(step.get("run") or "")
    for fragment, reason in DELIBERATE_VETO_STEPS.items():
        if fragment in run:
            return reason
    return None


# --------------------------------------------------------------------------
# THE SPLIT ITSELF: no capital-structure step runs in this job at all.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module,cost", sorted(CAPITAL_STRUCTURE_STEPS.items()))
def test_no_capital_structure_step_runs_in_the_collect_job(collect_steps, module, cost):
    """The 2026-08-06 job split, stated from the market side.

    The earlier checkpoint split already stopped these steps from DELAYING or
    DISCARDING the night's market data. It could not stop them from redding the
    job the whole nightly hangs off, which they did on three consecutive nights
    (#4600 08-04, #4640 08-05, #4740 08-06). Moving one back here re-couples an
    all-or-nothing SEC publication protocol — whose compilers are deliberately
    fatal and may never be given continue-on-error — to every `needs: collect`
    job in the workflow.
    """
    present = [
        i for i, s in enumerate(collect_steps) if module in str(s.get("run") or "")
    ]
    assert not present, (
        f"{module} ({cost}) is back in the collect job at step(s) {present}. It "
        "belongs to the `capital_structure` job (needs: collect), which nothing "
        "needs in turn — see tests/test_daily_capital_structure_job.py."
    )


def test_the_market_checkpoint_is_ordered_and_distinctly_named(collect_steps):
    """commit market data -> push market data, and never the bare old name.

    The naming matters as much as the order. `test_capital_structure_compiler.py`
    locates both checkpoints by name; a step called "commit data ..." would
    satisfy that pin's pre-split letter while the market plane silently rode a
    capital-structure-vetoed checkpoint again.
    """
    market_commit = _index_of(collect_steps, MARKET_COMMIT_STEP)
    market_push = _index_of(collect_steps, MARKET_PUSH_STEP)
    assert market_commit < market_push

    names = [str(s.get("name") or "") for s in collect_steps]
    bare = [n for n in names if n.startswith("commit data")]
    assert not bare, (
        f"a collect step is named {bare!r} again. The market checkpoint is "
        "'commit market data'; the capital-structure one is 'commit "
        "capital-structure data' and lives in another job."
    )


def test_the_capital_structure_handoff_can_never_cost_the_night(collect_steps):
    """The handoff pays for the split; it must not be able to charge this job.

    The ledger the `capital_structure` job compiles is deliberately NOT committed
    here (see the carve-out test below), so it crosses as an artifact. That is a
    capital-structure concern living in the collect job — exactly the shape the
    split removed — and it is only safe because neither step can fail the job.
    A failed stamp or upload must fail CLOSED one job over, in that job's handoff
    verification, never here.
    """
    for step_name in (HANDOFF_STAMP_STEP, HANDOFF_UPLOAD_STEP):
        step = collect_steps[_index_of(collect_steps, step_name)]
        assert step.get("continue-on-error") is True, (
            f"{step_name!r} is not continue-on-error, so a capital-structure "
            "handoff failure reds the collect job and every `needs: collect` job "
            "pays for it — the defect the split exists to remove."
        )

    # And it must sit after the checkpoint, for the same reason everything else does.
    push = _index_of(collect_steps, MARKET_PUSH_STEP)
    assert _index_of(collect_steps, HANDOFF_STAMP_STEP) > push, (
        "the handoff receipt is stamped before the market push. It must be stamped "
        "AFTER: that push rebases with --autostash, and a conflicted re-apply "
        "resets hard to origin/main's committed ledger (#4600's self-heal). The "
        "receipt has to describe whatever actually survived."
    )


def test_only_allowlisted_steps_may_cost_the_nights_collection(collect_steps):
    """A NEW unguarded step between the collectors and the market commit.

    Such a step reds the job, which SKIPS the commit gate's siblings and delays
    the checkpoint — the exact shape the split was made to remove. Since
    2026-08-06 the allowlist is empty and should stay that way; a step that
    genuinely must block the market checkpoint belongs in DELIBERATE_VETO_STEPS,
    where the cost is written down.
    """
    start = _index_of(collect_steps, COLLECTORS_STEP)
    end = _index_of(collect_steps, MARKET_COMMIT_STEP)
    assert start < end, "collectors must run before the market checkpoint"

    offenders = [
        (i, collect_steps[i].get("name"))
        for i in range(start + 1, end)
        if not _is_non_fatal(collect_steps[i]) and _veto_reason(collect_steps[i]) is None
    ]
    assert not offenders, (
        "these steps sit between the collectors and 'commit market data' and can "
        "fail the job, which skips the commit and leaves ~3h of collection on the "
        f"runner: {offenders}. Guard each with `continue-on-error: true` or the "
        'house `|| echo "::warning::..."` idiom — or, if it truly must block the '
        "checkpoint, add it to DELIBERATE_VETO_STEPS with the reason."
    )


def test_the_veto_allowlist_is_not_stale(collect_steps):
    """Every allowlisted veto must still exist, so the list cannot rot into fiction."""
    runs = " \n".join(str(s.get("run") or "") for s in collect_steps)
    missing = [frag for frag in DELIBERATE_VETO_STEPS if frag not in runs]
    assert not missing, (
        f"DELIBERATE_VETO_STEPS names steps the collect job no longer runs: {missing}. "
        "Drop them — a stale allowlist silently licenses a future step that reuses "
        "the name."
    )


def test_collectors_step_contract_is_stated_in_its_own_name(collect_steps):
    """08-02/08-03 shape: the collectors step exited 1 and took the commit with it.

    `scripts.collect` degrades per source and exits non-zero only if EVERY source
    failed, but an exception escaping its runner machinery still killed the pass
    (#4560 added the `_run_one` net). This pins the stated contract so a rename
    cannot quietly drop it.
    """
    step = collect_steps[_index_of(collect_steps, COLLECTORS_STEP)]
    assert "never fails the build on one source" in (step.get("name") or ""), (
        "the collectors step's own name states the contract; if it was renamed, "
        "re-read whether the guarantee still holds"
    )


@pytest.mark.parametrize(
    "commit_step,push_step", [(MARKET_COMMIT_STEP, MARKET_PUSH_STEP)]
)
def test_each_checkpoint_keeps_the_commit_push_split(collect_steps, commit_step, push_step):
    """The local commit is its own step; the network publish is a separate one.

    2026-07-17 postmortem (run 29542087837): a hung `git push` ate 57m and the
    150m job cap killed the step mid-publish, so an already-collected night
    existed only on the runner. The capital-structure checkpoint carries the same
    shape one job over, pinned by tests/test_daily_capital_structure_job.py.
    """
    commit_at = _index_of(collect_steps, commit_step)
    push_at = _index_of(collect_steps, push_step)
    assert commit_at < push_at, f"{commit_step!r} must precede {push_step!r}"

    commit = collect_steps[commit_at]
    push = collect_steps[push_at]
    commit_run = str(commit.get("run") or "")
    push_run = str(push.get("run") or "")

    assert "git commit -m" in commit_run, f"{commit_step!r} no longer commits"
    assert "git push" not in commit_run and "push_do" not in commit_run, (
        f"{commit_step!r} performs the network push itself — merging the two back "
        "together is the 2026-07-17 defect. Keep the publish in its own step."
    )
    assert "git commit" not in push_run, (
        f"{push_step!r} commits as well as pushes; the commit must already be "
        "atomic before any network op runs"
    )
    assert "scripts/ci/push_retry.sh" in push_run, (
        f"{push_step!r} no longer sources the shared retry policy — it loses the "
        "contention/conflict split and the jittered backoff (render run 30167139398)"
    )
    assert "perl -e 'alarm" in push_run, (
        f"{push_step!r} has an unbounded git network op. macOS runners have no GNU "
        "timeout; a hung fetch/pull can only be killed by the perl alarm."
    )

    cond = str(push.get("if") or "")
    assert "always()" in cond, (
        f"{push_step!r} has `if: {cond or '<none>'}`, which carries no status "
        "function, so GitHub ANDs an implicit success() onto it and an earlier red "
        "skips the publish of an already-made commit"
    )
    commit_id = commit.get("id")
    assert commit_id and f"steps.{commit_id}.outputs.committed == 'true'" in cond, (
        f"{push_step!r} must be gated on {commit_step!r}'s own `committed` output "
        f"(id={commit_id!r}); if: {cond}"
    )


def test_salvage_push_covers_the_market_commit(collect_steps):
    """The cancel-path last-ditch publish belongs to the expensive checkpoint.

    It runs `if: cancelled()`, so it must sit where a cancel during the market
    push can still reach it — immediately after that push, not behind slower work
    later in the job.
    """
    market_push = _index_of(collect_steps, MARKET_PUSH_STEP)
    salvage = _index_of(collect_steps, "salvage push")
    assert salvage == market_push + 1, (
        "the salvage push must follow the market push DIRECTLY (2026-07-17 / "
        f"2026-07-16 postmortems); it is at {salvage}, the push at {market_push}"
    )
    cond = str(collect_steps[salvage].get("if") or "")
    assert "cancelled()" in cond and "steps.commitdata.outputs.committed" in cond, (
        f"the salvage push lost its cancel/commit gate; if: {cond}"
    )


# --------------------------------------------------------------------------
# Checkpoint 1: the market commit's gate — NAMED PRODUCERS, never job status.
# --------------------------------------------------------------------------
#
# "commit data" used to carry no `if:` at all, so it inherited an implicit
# success() and any earlier red discarded the night (08-02..08-05, four nights,
# three unrelated causes).  A bare `always()` is the other failure mode and is
# worse: on 2026-08-04 an always() commit step outran its SKIPPED normalizers
# and committed raw un-normalized pages sitewide.
#
# The lawful shape is a gate on the NAMED steps that PRODUCE what the commit
# stages, compared with `.outcome == 'success'` so a SKIPPED producer blocks
# exactly like a failed one.  These tests pin that shape from both sides: every
# producer must be in the gate, and nothing else may be.

# Staged path prefix -> (step id that produces it, must_gate).
#
# The capital-structure paths are NOT here any more: since 2026-08-06 they are
# staged by checkpoint 2, and this commit only unstages them (see the carve-out
# test below).
MARKET_STAGED_PATH_PRODUCERS = {
    "data/": [("collectors", True)],
    "site/qledger/": [("collectors", True)],
}

# The capital-structure checkpoint's own staging + gate moved with the chain;
# tests/test_daily_capital_structure_job.py owns them now.
CAPITAL_STRUCTURE_CHAIN = ("cs_spine", "cs_terms", "cs_projection")


def _gating(producers: dict) -> list[str]:
    return sorted({
        step_id
        for entries in producers.values()
        for step_id, must_gate in entries
        if must_gate
    })


MARKET_GATING_PRODUCERS = _gating(MARKET_STAGED_PATH_PRODUCERS)

CHECKPOINTS = {
    MARKET_COMMIT_STEP: (MARKET_STAGED_PATH_PRODUCERS, MARKET_GATING_PRODUCERS),
}


def _gate_refs(cond: str) -> set[str]:
    """Every `steps.<id>.<field>` referenced by an `if:` expression."""
    return set(re.findall(r"steps\.([A-Za-z0-9_-]+)\.", cond))


@pytest.mark.parametrize("commit_step", sorted(CHECKPOINTS))
def test_every_staged_path_has_a_declared_producer(collect_steps, commit_step):
    """Anti-rot: a new `git add` path must be mapped before it can ship.

    This is what keeps the gates honest. Without it, someone stages a new tree,
    forgets to name its producer, and a checkpoint silently commits a path nobody
    is gating — the original defect wearing a new path.
    """
    producers, _ = CHECKPOINTS[commit_step]
    run = collect_steps[_index_of(collect_steps, commit_step)]["run"]
    add_lines = [ln.strip() for ln in run.splitlines() if ln.strip().startswith("git add ")]
    assert add_lines, f"{commit_step!r} no longer contains a `git add` — the mapping is fiction"

    staged = {p for line in add_lines for p in line.split()[2:] if not p.startswith("-")}
    undeclared = staged - set(producers)
    assert not undeclared, (
        f"{commit_step!r} stages {sorted(undeclared)}, which its producer map does "
        "not cover. Add the mapping (and gate on the producer if a partial write "
        "there would corrupt the tree) before staging a new path."
    )
    unstaged = set(producers) - staged
    assert not unstaged, (
        f"the producer map claims {commit_step!r} stages {sorted(unstaged)}, which "
        "it no longer does — a stale mapping licenses a gate that guards nothing."
    )


@pytest.mark.parametrize("commit_step", sorted(CHECKPOINTS))
def test_commit_gate_names_exactly_the_producers_of_its_staged_paths(
    collect_steps, commit_step
):
    """Bidirectional: every gating producer present, and nothing else.

    (a) a missing producer means a partial tree can be checkpointed;
    (b) an extra name means an unrelated subsystem can veto this checkpoint,
        which is precisely what cost 08-02..08-05 on the market side.
    """
    _, gating = CHECKPOINTS[commit_step]
    cond = str(collect_steps[_index_of(collect_steps, commit_step)].get("if") or "")
    assert cond, (
        f"{commit_step!r} has no `if:` — it inherits success() and ANY earlier red "
        "in the ~3h job skips it"
    )

    refs = _gate_refs(cond)
    missing = set(gating) - refs
    assert not missing, (
        f"{commit_step!r} does not gate on {sorted(missing)}, which produce the tree "
        f"it stages. A partial or skipped run of those would be checkpointed. if: {cond}"
    )
    extra = refs - set(gating)
    assert not extra, (
        f"{commit_step!r} gates on {sorted(extra)}, which do not PRODUCE its staged "
        f"tree. A consumer, audit, or tripwire in this gate can discard real work "
        f"over an unrelated failure. if: {cond}"
    )


@pytest.mark.parametrize("step_id", sorted(MARKET_GATING_PRODUCERS))
def test_gated_producer_ids_actually_exist(collect_steps, step_id):
    """A gate naming a step that does not exist can never be satisfied."""
    ids = {s.get("id") for s in collect_steps if s.get("id")}
    assert step_id in ids, (
        f"a commit gate names step id {step_id!r}, which no collect step declares — "
        "the expression would evaluate to '' and the commit could never run"
    )


@pytest.mark.parametrize("commit_step", sorted(CHECKPOINTS))
def test_commit_gate_blocks_a_skipped_producer_exactly_like_a_failed_one(
    collect_steps, commit_step
):
    """The 2026-08-04 P0's actual lesson.

    An always() commit outran its SKIPPED normalizers and committed raw pages
    sitewide. `.outcome == 'success'` is the only comparison that blocks on
    'skipped'; `!= 'failure'` lets a skipped producer through, and `.conclusion`
    is laundered to 'success' by a continue-on-error — which matters most on the
    capital-structure checkpoint, whose whole contract is that its compile steps
    stay fatal (a future `continue-on-error:` there must not buy a commit).
    """
    _, gating = CHECKPOINTS[commit_step]
    cond = str(collect_steps[_index_of(collect_steps, commit_step)].get("if") or "")

    for step_id in gating:
        assert f"steps.{step_id}.outcome == 'success'" in cond, (
            f"{commit_step!r}'s gate on {step_id!r} must be exactly "
            f"`steps.{step_id}.outcome == 'success'`. A `!= 'failure'` test lets a "
            "SKIPPED producer through, and `.conclusion` is laundered by "
            f"continue-on-error. if: {cond}"
        )
    assert ".conclusion" not in cond, (
        f"{commit_step!r}'s gate uses `.conclusion`, which a continue-on-error "
        f"rewrites to 'success' — it cannot see the failure it must block. if: {cond}"
    )


@pytest.mark.parametrize("commit_step", sorted(CHECKPOINTS))
def test_commit_gate_is_explicit_never_bare_always_or_implicit_success(
    collect_steps, commit_step
):
    """It must survive an unrelated red, and must not be a blank cheque."""
    cond = str(collect_steps[_index_of(collect_steps, commit_step)].get("if") or "").strip()

    assert "always()" in cond, (
        f"without a status function {commit_step!r} inherits an implicit success() "
        f"and any earlier red in the ~3h job skips it. if: {cond!r}"
    )
    assert cond != "always()" and _gate_refs(cond), (
        f"`if: always()` alone is a bare always() — the 2026-08-04 P0 shape, where "
        "the commit outran its skipped producers. Name the producing steps."
    )
    assert "success()" not in cond, (
        "success() is job-wide status, not a named producer: it re-couples the commit "
        f"to every unrelated step in the job. if: {cond!r}"
    )


def test_market_commit_unstages_capital_structure_unconditionally(collect_steps):
    """Checkpoint 1 must drop the capital-structure paths — always, and by UNSTAGE.

    Two failure modes, opposite directions:

      * it stages them anyway. `run collectors` has already rewritten the tracked
        source_manifest.jsonl, and no compiler has accepted it yet, so the market
        commit would publish a source ledger that may be about to be REJECTED —
        and #4600's self-heal (each night restores a clean ledger from git) dies
        with it, because the drift becomes permanent.
      * it `git checkout`s them. The pre-split carve-out did exactly that, and it
        was right THEN: it fired after a FAILED chain, restoring the clean
        committed ledger. Here the chain has not run and that ledger is its
        INPUT, so a checkout would feed the spine yesterday's manifests every
        single night — a silently frozen lane that still goes green.
    """
    step = collect_steps[_index_of(collect_steps, MARKET_COMMIT_STEP)]
    run = str(step["run"])
    body = [ln.strip() for ln in run.splitlines() if not ln.strip().startswith("#")]

    reset_lines = [
        ln for ln in body
        if ln.startswith("git reset") and "data/capital_structure" in ln
    ]
    assert reset_lines, (
        "'commit market data' no longer unstages data/capital_structure, so the "
        "broad `git add data/` above it commits an unvalidated source ledger."
    )
    assert any("site/capital-structure-data" in ln for ln in reset_lines), (
        "the carve-out unstages data/capital_structure but leaves the public twin "
        "site/capital-structure-data/ staged — the two must move together or the "
        "'byte-identical twin' law breaks"
    )
    assert not any(
        ln.startswith("git checkout") and "capital_structure" in ln for ln in body
    ), (
        "'commit market data' reverts the capital-structure paths with `git "
        "checkout`. That discards the ledger the collectors just fetched, which is "
        "the INPUT to the compile chain below — the lane would recompile yesterday "
        "forever while every step stayed green."
    )

    # Unconditional: no `if [ ... ]` may guard the reset. Before the split the
    # carve-out was conditional on the chain's outcomes; those outcomes are now
    # the empty string here, so a surviving condition would be a silent no-op.
    idx = body.index(reset_lines[0])
    assert not any(ln.startswith(("if ", "elif ")) for ln in body[:idx]), (
        "the capital-structure unstage sits inside a conditional. At this point in "
        "the job no capital-structure step has run, so any `steps.cs_*.outcome` "
        "test evaluates to '' and the carve-out silently stops firing."
    )
    for var in CAPITAL_STRUCTURE_CHAIN:
        assert var not in str(step.get("env") or {}), (
            f"'commit market data' still reads {var} into its env; that outcome is "
            "always empty here because the step has not run yet"
        )


# The capital-structure checkpoint's narrow staging, its fatal compilers, and the
# placement of the rejected-ledger capture moved with the chain into
# tests/test_daily_capital_structure_job.py. They are the same laws, asserted
# against the job that now runs them.


# --------------------------------------------------------------------------
# The R2 publishes are NOT part of either checkpoint's gate.
# --------------------------------------------------------------------------
# The allowlist above bounds which steps may cost the night's GIT commit.
# The R2 store publishes sit after both commits and answer to a different law:
# they carry the day's upserted increments back to an R2-CANONICAL store, and
# the engine job's `audit_r2 --strict` anchor goes red within 26h if they do
# not run.  They were nevertheless collateral damage of every veto, because a
# step `if:` that names no status function inherits an implicit success().
#
# Run 30960328285 is the cost: the massive_stock_day publish had been in the
# workflow for three nights and had never once executed.  These tests pin the
# decoupling so a future edit cannot silently re-attach them to the veto.

R2_PUBLISH_STEPS = {
    "publish attention store back to R2": "steps.attention_restore.outcome",
    "publish massive_stock_day store back to R2": "steps.massive_restore.outcome",
}

_STATUS_FUNCS = ("always(", "failure(", "cancelled(", "!cancelled(")


@pytest.mark.parametrize("step_name,restore_gate", sorted(R2_PUBLISH_STEPS.items()))
def test_r2_publish_survives_a_veto_but_keeps_its_restore_gate(
    collect_steps, step_name, restore_gate
):
    """Each R2 publish must run after an earlier red AND stay restore-gated.

    Two failure modes, opposite directions:
      * no status function -> implicit success() -> skipped by any earlier red,
        which is how the store froze (nothing published 2026-07-30 -> 08-05);
      * no restore gate -> a failed/partial restore leaves a shallow tree that
        would overwrite the deep store on R2. The gate is the fence; keep both.
    """
    step = collect_steps[_index_of(collect_steps, step_name)]
    cond = str(step.get("if") or "")

    assert cond, f"{step_name!r} lost its `if:` entirely — the restore fence is gone"
    assert any(fn in cond for fn in _STATUS_FUNCS), (
        f"{step_name!r} has `if: {cond}`, which contains no status-check function, so "
        "GitHub ANDs an implicit success() onto it and ANY earlier failure in the ~3h "
        "collect job skips the publish. The R2 store then goes stale and the engine "
        "job's audit_r2 anchor reds within 26h. Use `always() && <restore gate>`."
    )
    assert restore_gate in cond, (
        f"{step_name!r} dropped its restore gate ({restore_gate}). Without it a failed "
        "or partial R2 restore leaves a shallow local tree that this step would publish "
        "OVER the deep canonical store."
    )


@pytest.mark.parametrize("step_name", sorted(R2_PUBLISH_STEPS))
def test_r2_publish_runs_after_the_market_checkpoint(collect_steps, step_name):
    """Publishing must never delay the local commit (2026-07-17 postmortem)."""
    at = _index_of(collect_steps, step_name)
    assert _index_of(collect_steps, MARKET_COMMIT_STEP) < at, (
        f"{step_name!r} moved ahead of {MARKET_COMMIT_STEP!r}; a slow upload would "
        "then sit between the collection and the checkpoint that preserves it"
    )
    assert _index_of(collect_steps, HANDOFF_UPLOAD_STEP) < at, (
        f"{step_name!r} moved ahead of the capital-structure handoff. The handoff "
        "is what lets the isolated job compile tonight's ledger at all; a slow or "
        "hung R2 upload must not sit in front of it and burn the job's budget."
    )


def test_store_tripwire_still_fires_on_a_lost_night(collect_steps):
    """The massive_store content audit must run even when the night is discarded.

    `continue-on-error: true` stops this step from FAILING the job; it does not
    stop an earlier failure from SKIPPING it. Through 08-02..08-05 the tripwire
    was dark on exactly the nights that needed it, and the freeze surfaced six
    days later as the engine job's R2 staleness anchor instead.
    """
    step = collect_steps[_index_of(collect_steps, "audit massive_stock_day store")]
    cond = str(step.get("if") or "")

    assert any(fn in cond for fn in _STATUS_FUNCS), (
        "the massive_store tripwire has `if: "
        f"{cond or '<none>'}`, so an earlier red in the collect job skips it and the "
        "store's freshness alarm goes dark on precisely the nights it matters."
    )
    assert step.get("continue-on-error") is True, (
        "the tripwire now runs under always(); without continue-on-error a content "
        "fail would red the collect job it was designed never to block."
    )


@pytest.mark.parametrize("step_name", sorted(R2_PUBLISH_STEPS))
def test_r2_publish_is_itself_non_fatal(collect_steps, step_name):
    """A failed upload must not red the collect job — the anchor alarm carries it."""
    step = collect_steps[_index_of(collect_steps, step_name)]
    assert _is_non_fatal(step), (
        f"{step_name!r} can now fail the collect job. It runs under always(), so a "
        "publish failure would red an otherwise-successful night. Keep the house "
        '`|| echo "::warning::..."` guard.'
    )


# ── the other way to lose a night: publish it, then overwrite it ──────────────
# The commit path above makes a night REAL. This guard covers the mirror defect:
# a LATER job in the same night restoring a stale GHA cache on top of what an
# earlier job already committed, then committing the stale copy back.
#
# 2026-08-06, measured: `collect` wrote data/breadth/_closes_cache.parquet through
# the 08-05 close (348 rows x 510 names, 361136284f2); the `engine` job 14 hours
# later committed it back at 2026-07-31 (345 x 509, 2dfebf35dbd), because its
# actions/cache step carried `restore-keys: breadth-closes-`, which matches the
# newest cache under that prefix from ANY prior run.
#
# The blast radius was the whole US board. engine/residual_alpha.py stamps
# as_of = R.index.max() off that panel, alpha.json carries it, build_stock_library
# copies it into us_standouts.json, and the snapshotter keys on as_of — so
# data/us_board_ledger/snapshots.jsonl appended NOTHING for six days while the
# board kept publishing picks ranked on 07-31 factors next to current-day prices.
#
# china*/hk* never had this problem: the commit steps unstage every asia-owned
# path (W0b, 2026-07-08), so a stale restore there cannot reach a commit. This
# test encodes the real invariant rather than a list of paths — a git-tracked
# cache path that the commit step does NOT unstage must not carry a restore-key.

import fnmatch  # noqa: E402
import subprocess  # noqa: E402


def _is_git_tracked(path: str) -> bool:
    """True when the path has at least one tracked file (so a commit can carry it)."""
    out = subprocess.run(["git", "ls-files", "--", path],
                         cwd=ROOT, capture_output=True, text=True).stdout
    return bool(out.strip())


def _unstaged_by(commit_run: str, path: str) -> bool:
    """True when a `git reset` in the commit step unstages this path (asia-owned carve-out)."""
    for line in commit_run.splitlines():
        line = line.strip()
        if not line.startswith("git reset"):
            continue
        for tok in line.split():
            if not tok.startswith("data/"):
                continue
            if path == tok or path.startswith(tok.rstrip("*")) or fnmatch.fnmatch(path, tok):
                return True
    return False


#: Jobs that CONSUME the breadth panel without regenerating it. `collect` is
#: deliberately absent: it is the PRODUCER, and there its prefix restore-key is
#: load-bearing — it warm-starts the ~3-year panel so the collectors only have to
#: append today's closes. Restoring a prior cache and then rewriting the file is
#: safe; restoring one and then committing it unchanged is what corrupts the night.
_CACHE_CONSUMER_JOBS = ["engine"]


@pytest.mark.parametrize("job_name", _CACHE_CONSUMER_JOBS)
def test_no_job_restores_a_stale_cache_over_data_it_will_commit(job_name):
    doc = yaml.safe_load(DAILY.read_text())
    job = doc["jobs"][job_name]
    steps = job.get("steps") or []
    # 512KB-cap diet: some commit bodies live in scripts/ci/ — resolve the
    # effective source so the unstage carve-outs below stay visible.
    commit_run = "\n".join(
        resolve_run_source(str(s.get("run") or ""), ROOT) for s in steps
        if "commit" in ((s.get("name") or "").lower())
    )

    offenders = []
    for st in steps:
        if not str(st.get("uses") or "").startswith("actions/cache@"):
            continue
        w = st.get("with") or {}
        path = str(w.get("path") or "").strip()
        if not path.startswith("data/") or not w.get("restore-keys"):
            continue
        if not _is_git_tracked(path):
            continue              # untracked: no commit can carry it back
        if _unstaged_by(commit_run, path):
            continue              # carved out of `git add data/` before the commit
        offenders.append(f"{path} (restore-keys: {str(w['restore-keys']).strip()})")

    assert not offenders, (
        f"daily.yml job {job_name!r} restores a prefix-matched GHA cache onto GIT-TRACKED "
        f"paths it then commits: {offenders}. A prefix restore-key matches the newest cache "
        f"from ANY prior run, so this overwrites data an earlier job committed tonight and "
        f"pushes the stale copy back — it froze the US board at as_of=2026-07-31 for six "
        f"days on 2026-08-06. Either drop restore-keys (the job then simply uses the fresh "
        f"panel already in the git checkout) or unstage the path in the commit step the way "
        f"the asia-owned china*/hk* carve-out does."
    )


def test_gitignored_russell_cache_uses_the_collect_jobs_exact_same_run_key():
    """The engine checkout cannot carry the Russell panel; the cache handoff must.

    PR #4798 correctly removed engine's broad ``restore-keys`` because a prefix match
    could overwrite tonight's tracked panels with a prior run. Russell is the exception
    to the checkout fallback: ``_closes_cache.parquet`` is gitignored. The producer used
    ``russell-closes-<run_id>`` while engine requested
    ``russell-closes-engine-<run_id>``, guaranteeing a miss on cold runners and making
    the keep-FIRST name-score stamp lose roughly 1,220 names.
    """
    path = "data/russell_breadth/_closes_cache.parquet"
    assert not _is_git_tracked(path), (
        "the Russell close cache became git-tracked; reassess whether the cross-job "
        "cache handoff is still the source of truth"
    )

    doc = yaml.safe_load(DAILY.read_text())
    engine = doc["jobs"]["engine"]
    assert "collect" in engine.get("needs", []), (
        "engine must wait for collect to finish and save the same-run Russell cache"
    )

    def cache_step(job_name: str) -> dict:
        matches = [
            step for step in doc["jobs"][job_name]["steps"]
            if str((step.get("with") or {}).get("path") or "").strip() == path
        ]
        assert len(matches) == 1, (
            f"expected one {path} cache step in {job_name!r}, found {len(matches)}"
        )
        return matches[0]

    producer_step = cache_step("collect")
    consumer_step = cache_step("engine")
    producer = producer_step.get("with") or {}
    consumer = consumer_step.get("with") or {}
    expected = "russell-closes-${{ github.run_id }}"

    assert producer.get("key") == expected
    assert producer_step.get("uses") == "actions/cache@v4", (
        "collect must use the combined cache action so the same-run Russell key is "
        "saved after collection; restore-only would leave engine with nothing to consume"
    )
    assert consumer_step.get("uses") == "actions/cache/restore@v4", (
        "engine is a cache consumer only. Using the combined cache action lets a miss "
        "save an engine-owned key back into the producer's fallback namespace."
    )
    assert consumer.get("key") == producer.get("key"), (
        "engine must request collect's exact same-run Russell cache key. A distinct key "
        "cannot hit, and adding a broad restore-key would reintroduce the stale-cache "
        "overwrite that PR #4798 removed."
    )
    assert not consumer.get("restore-keys"), (
        "engine's Russell restore must remain exact-key-only; a prefix fallback may select "
        "a prior run and silently reintroduce stale source data"
    )
