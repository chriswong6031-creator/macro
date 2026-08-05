"""Which steps may discard a night of market data — bounded, named, and visible.

`daily.yml`'s `collect` job spends up to ~3 hours pulling the market data plane
(235 `data/stocks` names, `data/baskets/ohlcv`, the breadth close caches) and
lands all of it in ONE step: "commit data".  The collected bytes live only on
the runner, where the next job's `actions/checkout` deletes them.

**Updated 2026-08-05 — the commit no longer answers to job status.**  It used to
carry no `if:` at all, so it inherited an implicit success() and ANY earlier
non-zero step skipped it and discarded the night.  It now gates on the NAMED
steps that produce what it stages (`steps.collectors.outcome == 'success'`),
compared with `.outcome` so a SKIPPED producer blocks exactly like a failed one
— the lesson of the 2026-08-04 P0, where an `always()` commit step outran its
skipped normalizers and committed raw un-normalized pages sitewide.  A bare
`always()` here would be that same defect.  See the gate tests below.

So an allowlisted veto below no longer discards the market collection.  It still
matters, and this module still guards it, because a step that exits non-zero
still REDS the run and still skips every step after it — including the rest of
the capital-structure chain and the small additive producers (Finviz themes,
ZORI) whose output would then simply not refresh that night.

That is not hypothetical.  On 2026-08-05 (run 30960328285) the collectors step
SUCCEEDED after 2h52m and `compile capital-structure event spine` raised
`ManifestIdentityError` (the night's re-fetched SEC source manifests no longer
hashed to what the committed generation pinned).  The job died there, "commit
data" never ran, and the night was discarded — the fourth consecutive loss
(08-02/08-03 were a duck-typing crash inside the collectors step, fixed in #4560;
08-04 was the runner host filling its disk).

**That veto is deliberate.**  `tests/test_capital_structure_compiler.py::
test_nightly_order_and_render_network_firewall_are_pinned` asserts, in its own
words, that "a capital-structure integrity failure must BLOCK the nightly
checkpoint" — it pins the compile step to run after collection, before the data
commit, and WITHOUT `continue-on-error`.  This module does not fight that pin,
and the 2026-08-05 gate does not either: that lane's real requirement is that a
partial capital-structure generation is never COMMITTED, which is now enforced
by SCOPE instead of by veto.  `run collectors` has already rewritten the tracked
`source_manifest.jsonl` by the time the spine validates it, so on a rejection the
tree holds a refused source ledger beside the previous generation's events; the
commit unstages `data/capital_structure/` + `site/capital-structure-data/`
whenever that chain did not fully succeed.  The torn generation is never
committed, the compile still reds the run, and the price data survives.

What it does is keep the blast radius **bounded and named**: the veto set is an
explicit allowlist below, so a step added later cannot quietly join it.  A new
unguarded step between the collectors and the commit is almost always an
oversight (the house idiom is `|| echo "::warning::..."` or
`continue-on-error: true`), and today it would cost a whole night's collection
silently.  If a step genuinely needs to block the checkpoint, adding it here is
the deliberate act that makes the cost visible to the next reader.
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

COMMIT_STEP = "commit data"
COLLECTORS_STEP = "run collectors"

# Steps that MAY fail the collect job before "commit data", and why.  Every entry
# costs the night's market collection when it fires — that is the accepted price,
# not an accident.  Keyed by a distinctive fragment of the step's `run:`.
#
# The capital-structure lane is an all-or-nothing SEC publication protocol: its
# own daily.yml comments require that "a partial capital-structure generation is
# never committed" and that its immutable event versions/edges "ride the same
# checkpoint" as the data.  The event-spine entry is additionally pinned by
# test_capital_structure_compiler.py (see module docstring) — do not remove it
# here without changing that test and its owning program.
DELIBERATE_VETO_STEPS = {
    "scripts.materialize_capital_structure_share_counts":
        "capital-structure share-count publication (pre-production, var-gated off)",
    "scripts.retain_capital_structure_share_counts":
        "capital-structure retention lane (pre-production, double var-gated off)",
    "scripts.compile_capital_structure_events":
        "capital-structure event spine — fail-closed by design, pinned by "
        "test_capital_structure_compiler.py::"
        "test_nightly_order_and_render_network_firewall_are_pinned",
    "scripts.compile_capital_structure_document_terms":
        "capital-structure term ledger — must not commit a partial ledger",
    "scripts.build_capital_structure_projection":
        "capital-structure projection — canonical/public twin must stay byte-identical",
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


def test_only_allowlisted_steps_may_discard_the_nights_collection(collect_steps):
    """A NEW unguarded step between the collectors and the commit is an oversight.

    Since 2026-08-05 such a step no longer discards the collection (the commit
    gates on named producers, not job status), but it still reds the run and
    still skips every producer after it, so its output silently stops
    refreshing. Steps that must fail the job belong in DELIBERATE_VETO_STEPS,
    where the cost is written down.
    """
    start = _index_of(collect_steps, COLLECTORS_STEP)
    end = _index_of(collect_steps, COMMIT_STEP)
    assert start < end, "collectors must run before the commit checkpoint"

    offenders = [
        (i, collect_steps[i].get("name"))
        for i in range(start + 1, end)
        if not _is_non_fatal(collect_steps[i]) and _veto_reason(collect_steps[i]) is None
    ]
    assert not offenders, (
        "these steps sit between the collectors and 'commit data' and can fail the "
        "job, which SKIPS the commit and discards the whole night's market data "
        f"(~3h of collection): {offenders}. Guard each with `continue-on-error: "
        "true` or the house `|| echo \"::warning::...\"` idiom — or, if it truly "
        "must block the checkpoint, add it to DELIBERATE_VETO_STEPS with the reason."
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


def test_commit_step_still_precedes_its_push_and_salvage(collect_steps):
    """The commit/push split is what survives a job-cap cancel; keep the order."""
    commit = _index_of(collect_steps, COMMIT_STEP)
    push = _index_of(collect_steps, "push data")
    salvage = _index_of(collect_steps, "salvage push")
    assert commit < push < salvage, (
        "the local commit must precede the network publish, and the salvage push "
        "must follow both (2026-07-17 postmortem)"
    )


# --------------------------------------------------------------------------
# The commit's own gate: NAMED PRODUCERS, never job status, never bare always().
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
# `must_gate=False` means the step writes into the staged tree but a miss is a
# no-op diff rather than a torn tree, so it does not block the checkpoint.  The
# capital-structure chain is the interesting case: it DOES write tracked staged
# paths, so it cannot simply be ignored, but it must not veto price collection
# either — it is handled by unstaging its paths (see the carve-out test below).
STAGED_PATH_PRODUCERS = {
    "data/": [("collectors", True)],
    "site/qledger/": [("collectors", True)],
    "site/capital-structure-data/": [
        ("cs_spine", False), ("cs_terms", False), ("cs_projection", False),
    ],
}

GATING_PRODUCERS = sorted({
    step_id
    for producers in STAGED_PATH_PRODUCERS.values()
    for step_id, must_gate in producers
    if must_gate
})

CAPITAL_STRUCTURE_CHAIN = ("cs_spine", "cs_terms", "cs_projection")


def _commit_step(steps: list[dict]) -> dict:
    return steps[_index_of(steps, COMMIT_STEP)]


def _gate_refs(cond: str) -> set[str]:
    """Every `steps.<id>.<field>` referenced by an `if:` expression."""
    return set(re.findall(r"steps\.([A-Za-z0-9_-]+)\.", cond))


def test_every_staged_path_has_a_declared_producer(collect_steps):
    """Anti-rot: a new `git add` path must be mapped before it can ship.

    This is what keeps the gate honest. Without it, someone stages a new tree,
    forgets to name its producer, and the commit silently checkpoints a path
    nobody is gating — the original defect wearing a new path.
    """
    run = _commit_step(collect_steps)["run"]
    add_lines = [ln.strip() for ln in run.splitlines() if ln.strip().startswith("git add ")]
    assert add_lines, "commit step no longer contains a `git add` — the mapping is fiction"

    staged = {p for line in add_lines for p in line.split()[2:] if not p.startswith("-")}
    undeclared = staged - set(STAGED_PATH_PRODUCERS)
    assert not undeclared, (
        f"'commit data' stages {sorted(undeclared)}, which STAGED_PATH_PRODUCERS does "
        "not map to a producing step. Add the mapping (and gate on the producer if a "
        "partial write there would corrupt the tree) before staging a new path."
    )
    unstaged = set(STAGED_PATH_PRODUCERS) - staged
    assert not unstaged, (
        f"STAGED_PATH_PRODUCERS maps {sorted(unstaged)}, which the commit no longer "
        "stages — a stale mapping licenses a gate that guards nothing."
    )


def test_commit_gate_names_exactly_the_producers_of_its_staged_paths(collect_steps):
    """Bidirectional: every gating producer present, and nothing else.

    (a) a missing producer means a partial tree can be checkpointed;
    (b) an extra name means an unrelated subsystem can discard the night, which
        is precisely what cost 08-02..08-05.
    """
    cond = str(_commit_step(collect_steps).get("if") or "")
    assert cond, "'commit data' has no `if:` — it inherits success() and ANY earlier red discards the night"

    refs = _gate_refs(cond)
    missing = set(GATING_PRODUCERS) - refs
    assert not missing, (
        f"'commit data' does not gate on {sorted(missing)}, which produce the tree it "
        f"stages. A partial or skipped run of those would be checkpointed. if: {cond}"
    )
    extra = refs - set(GATING_PRODUCERS)
    assert not extra, (
        f"'commit data' gates on {sorted(extra)}, which do not PRODUCE its staged tree. "
        "A consumer, audit, or tripwire in this gate can discard a whole night of price "
        f"collection over an unrelated failure. if: {cond}"
    )


@pytest.mark.parametrize("step_id", GATING_PRODUCERS)
def test_gated_producer_ids_actually_exist(collect_steps, step_id):
    """A gate naming a step that does not exist can never be satisfied."""
    ids = {s.get("id") for s in collect_steps if s.get("id")}
    assert step_id in ids, (
        f"the commit gate names step id {step_id!r}, which no collect step declares — "
        "the expression would evaluate to '' and the commit could never run"
    )


def test_commit_gate_blocks_a_skipped_producer_exactly_like_a_failed_one(collect_steps):
    """The 2026-08-04 P0's actual lesson.

    An always() commit outran its SKIPPED normalizers and committed raw pages
    sitewide. `.outcome == 'success'` is the only comparison that blocks on
    'skipped'; `!= 'failure'` lets a skipped producer through, and `.conclusion`
    is laundered to 'success' by a continue-on-error.
    """
    cond = str(_commit_step(collect_steps).get("if") or "")

    for step_id in GATING_PRODUCERS:
        assert f"steps.{step_id}.outcome == 'success'" in cond, (
            f"the gate on {step_id!r} must be exactly "
            f"`steps.{step_id}.outcome == 'success'`. A `!= 'failure'` test lets a "
            "SKIPPED producer through, and `.conclusion` is laundered by "
            f"continue-on-error. if: {cond}"
        )
    assert ".conclusion" not in cond, (
        "the commit gate uses `.conclusion`, which a continue-on-error rewrites to "
        f"'success' — it cannot see the failure it is meant to block. if: {cond}"
    )


def test_commit_gate_is_explicit_never_bare_always_or_implicit_success(collect_steps):
    """It must survive an unrelated red, and must not be a blank cheque."""
    cond = str(_commit_step(collect_steps).get("if") or "").strip()

    assert "always()" in cond, (
        "without a status function the commit inherits an implicit success() and any "
        f"earlier red in the ~3h job discards the night's collection. if: {cond!r}"
    )
    assert cond != "always()" and _gate_refs(cond), (
        "`if: always()` alone is a bare always() — the 2026-08-04 P0 shape, where the "
        "commit outran its skipped producers. Name the producing steps explicitly."
    )
    assert "success()" not in cond, (
        "success() is job-wide status, not a named producer: it re-couples the commit "
        f"to every unrelated step in the job. if: {cond!r}"
    )


def test_capital_structure_paths_are_carved_out_when_its_chain_did_not_succeed(
    collect_steps,
):
    """A compile failure must not discard price data — nor commit a torn generation.

    The capital-structure lane is all-or-nothing: `run collectors` has already
    rewritten the TRACKED source_manifest.jsonl by the time the spine validates
    it, so on a rejection the tree holds a refused source ledger beside the
    previous generation's events. Committing that publishes a torn generation
    AND makes it permanent (#4600's self-heal restores a clean ledger from git
    each night). So the chain does not gate the commit — it gates its own PATHS.
    """
    step = _commit_step(collect_steps)
    run = step["run"]
    env = step.get("env") or {}

    reset_lines = [
        ln for ln in run.splitlines()
        if "git reset" in ln and "data/capital_structure" in ln
    ]
    assert reset_lines, (
        "the commit no longer unstages data/capital_structure on an incomplete "
        "capital-structure chain. Either it now commits a torn generation, or the "
        "chain was moved back into the commit gate — where it discards price data."
    )
    assert any("site/capital-structure-data" in ln for ln in reset_lines), (
        "the carve-out unstages data/capital_structure but leaves the public twin "
        "site/capital-structure-data/ staged — the two must move together or the "
        "'byte-identical twin' law breaks"
    )

    for step_id in CAPITAL_STRUCTURE_CHAIN:
        var = next(
            (k for k, v in env.items() if f"steps.{step_id}.outcome" in str(v)), None
        )
        assert var, (
            f"the commit step does not read steps.{step_id}.outcome into its env, so "
            "the carve-out cannot see whether that link of the chain ran"
        )
        assert f'"${var}" != success' in run or f'"${{{var}}}" != success' in run, (
            f"${var} is wired into env but the carve-out never tests it — a failure of "
            f"{step_id!r} would still stage its half-written generation"
        )


# --------------------------------------------------------------------------
# The R2 publishes are NOT part of the checkpoint the veto set protects.
# --------------------------------------------------------------------------
# The allowlist above bounds which steps may discard the night's GIT commit.
# The R2 store publishes sit after that commit and answer to a different law:
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
def test_r2_publish_runs_after_the_commit_checkpoint(collect_steps, step_name):
    """Publishing must never delay the local commit (2026-07-17 postmortem)."""
    assert _index_of(collect_steps, COMMIT_STEP) < _index_of(collect_steps, step_name), (
        f"{step_name!r} moved ahead of {COMMIT_STEP!r}; a slow upload would then sit "
        "between the collection and the checkpoint that preserves it"
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
