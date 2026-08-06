"""Which steps may cost a night of market data — bounded, named, and visible.

`daily.yml`'s `collect` job spends up to ~3 hours pulling the market data plane
(235 `data/stocks` names, `data/baskets/ohlcv`, the breadth close caches).  The
collected bytes live only on the runner, where the next job's `actions/checkout`
deletes them, so the ONLY thing that makes a night real is a commit that lands.

**Updated 2026-08-06 — the job now has TWO checkpoints, split by SCOPE.**

    run collectors
      -> additive producers (Finviz, ZORI) + the two store tripwires
      -> "commit market data" + "push market data"      <-- checkpoint 1
      -> the five capital-structure steps
      -> "commit capital-structure data" + "push capital-structure data"

Before the split there was ONE commit and it sat AFTER the capital-structure
chain.  Two earlier fixes had already narrowed the damage — the commit gates on
NAMED producers (`steps.collectors.outcome == 'success'`) rather than job status,
and the capital-structure paths were carved out of it when the chain failed — so
a capital-structure failure no longer DISCARDED the collection outright.  What
neither fix could remove is the WINDOW: ~3h of collected bytes stayed unpublished
for the whole length of the capital-structure chain, one job-cap cancel, runner
death, or host-disk fault away from being deleted by the next checkout.  Six
consecutive nights from 2026-08-01 went that way, through four unrelated defects
(#4534 duck-typing, runner ENOSPC, #4600 ledger identity, #4640 SEC grammar), and
`data/stocks` froze at 2026-07-31.

The split closes the window instead of narrowing it: the market plane is
committed and PUSHED before a single capital-structure step starts, so no
capital-structure outcome can reach it — not by failing, not by hanging, not by
eating the job's remaining budget.

**The capital-structure lane keeps its own law, undiluted.**  It is an
all-or-nothing SEC publication protocol: `run collectors`
(`sec_capital_structure`) rewrites the TRACKED `source_manifest.jsonl` long
before the spine validates it, so between the two checkpoints the tree
legitimately holds a source ledger no compiler has accepted yet.  Checkpoint 1
UNSTAGES those paths — and must never `git checkout` them, because that freshly
collected ledger is the compilers' INPUT.  Checkpoint 2 commits them only after
the whole chain returned success; on a failure it simply never runs, the rejected
ledger dies with the runner's workspace, and the next night's checkout restores a
clean ledger from git (#4600's self-heal).  A partial generation is still never
committed, and `scripts.compile_capital_structure_events` is still fatal — for
its OWN checkpoint.  `continue-on-error` on it was tried in #4578 and correctly
reverted; the sibling pin
`test_capital_structure_compiler.py::test_nightly_order_and_render_network
_firewall_are_pinned` asserts that from the other side.

So `DELIBERATE_VETO_STEPS` below is now EMPTY, which is the whole point: every
step that used to be on it moved BELOW the market checkpoint.  The allowlist
stays because it is the thing that keeps a future re-coupling deliberate — a new
unguarded step between the collectors and the market commit is almost always an
oversight (the house idiom is `|| echo "::warning::..."` or
`continue-on-error: true`), and adding one to the list is the act that writes the
cost down for the next reader.
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

MARKET_COMMIT_STEP = "commit market data"
MARKET_PUSH_STEP = "push market data"
CS_COMMIT_STEP = "commit capital-structure data"
CS_PUSH_STEP = "push capital-structure data"
COLLECTORS_STEP = "run collectors"

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

# The chain that must stay BELOW the market checkpoint. Keyed by the `python -m`
# module each step runs, valued by what it would cost if it climbed back above it.
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
# THE SPLIT ITSELF: the market checkpoint precedes every capital-structure step.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module,cost", sorted(CAPITAL_STRUCTURE_STEPS.items()))
def test_capital_structure_steps_run_after_the_market_checkpoint(
    collect_steps, module, cost
):
    """The 2026-08-06 split, stated from the market side.

    Moving any of these back above "commit market data" re-opens the window that
    cost six consecutive nights: ~3h of collected bytes sitting unpublished on a
    runner for the length of the capital-structure chain. It is not enough that
    the commit SURVIVES a capital-structure failure (it already did, via the
    named-producer gate) — it must not WAIT for one.
    """
    commit = _index_of(collect_steps, MARKET_COMMIT_STEP)
    push = _index_of(collect_steps, MARKET_PUSH_STEP)
    at = _index_of_run(collect_steps, module)
    assert at > push > commit, (
        f"{module} ({cost}) runs at step {at}, before the market checkpoint "
        f"(commit={commit}, push={push}). The night's market data would again be "
        "held on the runner across the whole capital-structure chain."
    )


def test_the_two_checkpoints_are_ordered_and_distinctly_named(collect_steps):
    """Market commit -> market push -> CS steps -> CS commit -> CS push.

    The naming matters as much as the order. `test_capital_structure_compiler.py`
    locates the capital-structure checkpoint by name; if the second commit were
    called "commit data ..." it would satisfy that pin's old letter while the
    market plane silently rode a capital-structure-vetoed checkpoint again.
    """
    market_commit = _index_of(collect_steps, MARKET_COMMIT_STEP)
    market_push = _index_of(collect_steps, MARKET_PUSH_STEP)
    cs_commit = _index_of(collect_steps, CS_COMMIT_STEP)
    cs_push = _index_of(collect_steps, CS_PUSH_STEP)
    assert market_commit < market_push < cs_commit < cs_push

    names = [str(s.get("name") or "") for s in collect_steps]
    bare = [n for n in names if n.startswith("commit data")]
    assert not bare, (
        f"a collect step is still named {bare!r}. The two checkpoints must be "
        "distinguishable by name — 'commit market data' and 'commit "
        "capital-structure data'."
    )
    assert names[cs_commit].startswith("commit capital-structure data"), names[cs_commit]


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
    "commit_step,push_step",
    [(MARKET_COMMIT_STEP, MARKET_PUSH_STEP), (CS_COMMIT_STEP, CS_PUSH_STEP)],
)
def test_each_checkpoint_keeps_the_commit_push_split(collect_steps, commit_step, push_step):
    """The local commit is its own step; the network publish is a separate one.

    2026-07-17 postmortem (run 29542087837): a hung `git push` ate 57m and the
    150m job cap killed the step mid-publish, so an already-collected night
    existed only on the runner. Both checkpoints carry the same shape — commit
    first, push in a separate always()-guarded step gated on the commit's output.
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
    push can still reach it — immediately after that push, not at the end of the
    job behind the capital-structure chain.
    """
    market_push = _index_of(collect_steps, MARKET_PUSH_STEP)
    salvage = _index_of(collect_steps, "salvage push")
    cs_commit = _index_of(collect_steps, CS_COMMIT_STEP)
    assert market_push < salvage < cs_commit, (
        "the salvage push must follow the market push directly (2026-07-17 / "
        "2026-07-16 postmortems), before the capital-structure chain"
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

# Checkpoint 2 stages exactly the capital-structure generation and its
# byte-identical public twin. `collectors` produces the source ledger; the three
# compilers produce the events, terms, and projection. All four gate.
CS_STAGED_PATH_PRODUCERS = {
    "data/capital_structure": [
        ("collectors", True), ("cs_spine", True), ("cs_terms", True),
        ("cs_projection", True),
    ],
    "site/capital-structure-data": [
        ("collectors", True), ("cs_spine", True), ("cs_terms", True),
        ("cs_projection", True),
    ],
}

CAPITAL_STRUCTURE_CHAIN = ("cs_spine", "cs_terms", "cs_projection")


def _gating(producers: dict) -> list[str]:
    return sorted({
        step_id
        for entries in producers.values()
        for step_id, must_gate in entries
        if must_gate
    })


MARKET_GATING_PRODUCERS = _gating(MARKET_STAGED_PATH_PRODUCERS)
CS_GATING_PRODUCERS = _gating(CS_STAGED_PATH_PRODUCERS)

CHECKPOINTS = {
    MARKET_COMMIT_STEP: (MARKET_STAGED_PATH_PRODUCERS, MARKET_GATING_PRODUCERS),
    CS_COMMIT_STEP: (CS_STAGED_PATH_PRODUCERS, CS_GATING_PRODUCERS),
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


@pytest.mark.parametrize(
    "step_id", sorted(set(MARKET_GATING_PRODUCERS) | set(CS_GATING_PRODUCERS))
)
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


def test_capital_structure_commit_stages_only_its_own_generation(collect_steps):
    """Checkpoint 2 must not re-couple the market plane to the capital-structure lane.

    A broad `git add data/` here would put the night's market collection back
    behind a gate the capital-structure chain can veto — the defect the split
    removed, reintroduced from the other end.
    """
    run = str(collect_steps[_index_of(collect_steps, CS_COMMIT_STEP)]["run"])
    add_lines = [ln.strip() for ln in run.splitlines() if ln.strip().startswith("git add ")]
    staged = {p for line in add_lines for p in line.split()[2:] if not p.startswith("-")}
    assert staged == set(CS_STAGED_PATH_PRODUCERS), (
        f"'commit capital-structure data' stages {sorted(staged)}; it may stage "
        f"exactly {sorted(CS_STAGED_PATH_PRODUCERS)} and nothing else."
    )
    assert not any(p in {"data/", "data", "site/", "site", "."} for p in staged), (
        "a broad add here re-couples the market plane to the capital-structure chain"
    )


def test_capital_structure_compile_steps_stay_fatal_for_their_own_checkpoint(
    collect_steps,
):
    """No continue-on-error on the compile chain (#4578 tried it; correctly reverted).

    The split makes those steps harmless to the market plane. It must not make
    them harmless to their OWN generation: a compile failure has to keep the
    rejected ledger out of git, and `continue-on-error` would launder it into a
    commit.
    """
    for module in (
        "scripts.compile_capital_structure_events",
        "scripts.compile_capital_structure_document_terms",
        "scripts.build_capital_structure_projection",
    ):
        step = collect_steps[_index_of_run(collect_steps, module)]
        assert "continue-on-error" not in step, (
            f"{module} carries continue-on-error. Its failure would be laundered to "
            "'success' nowhere — but the step would stop failing, and a torn "
            "generation would ride the capital-structure checkpoint (#4578)."
        )
        assert _is_non_fatal(step) is False, (
            f"{module} is shell-guarded (`|| echo`), so it can no longer fail. Its "
            "checkpoint would then commit whatever half-generation it left behind."
        )


def test_rejected_ledger_capture_still_follows_the_whole_chain(collect_steps):
    """`if: failure()` only sees failures that already happened.

    Run 30997579632: the capture sat under the event spine, the document-terms
    compiler two steps later failed, and the capture was SKIPPED. It must stay
    below every capital-structure step — and above the capital-structure commit
    is fine, since that commit is skipped on any failure anyway.
    """
    capture = _index_of(collect_steps, "capture the rejected capital-structure ledger")
    assert str(collect_steps[capture].get("if") or "").strip() == "failure()"
    last_cs = max(_index_of_run(collect_steps, m) for m in CAPITAL_STRUCTURE_STEPS)
    assert capture > last_cs, (
        "the diagnostics capture moved above a capital-structure step; it would "
        "then fire only for the steps that precede it (run 30997579632)"
    )


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
def test_r2_publish_runs_after_both_checkpoints(collect_steps, step_name):
    """Publishing must never delay either local commit (2026-07-17 postmortem)."""
    at = _index_of(collect_steps, step_name)
    assert _index_of(collect_steps, MARKET_COMMIT_STEP) < at, (
        f"{step_name!r} moved ahead of {MARKET_COMMIT_STEP!r}; a slow upload would "
        "then sit between the collection and the checkpoint that preserves it"
    )
    assert _index_of(collect_steps, CS_COMMIT_STEP) < at, (
        f"{step_name!r} moved ahead of {CS_COMMIT_STEP!r}"
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
