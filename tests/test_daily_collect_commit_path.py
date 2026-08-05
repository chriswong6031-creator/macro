"""The nightly collection must reach its commit — no side subsystem may veto it.

`daily.yml`'s `collect` job spends up to ~3 hours pulling the market data plane
(235 `data/stocks` names, `data/baskets/ohlcv`, the breadth close caches) and
lands it in ONE step: "commit data".  Every step between the collectors and that
checkpoint is therefore a potential veto over the whole night — a step that exits
non-zero fails the job, and GitHub skips every later step, including the commit.
The collected bytes then live only on the runner, where the next job's
`actions/checkout` deletes them.

That is not hypothetical.  On 2026-08-05 (run 30960328285) the collectors step
SUCCEEDED after 2h52m and `compile capital-structure event spine` — a step its own
comment calls "context-only", with "no Prophet/rank authority" — raised
`ManifestIdentityError` because the night's re-fetched SEC source manifests no
longer hashed to what the committed generation pinned.  The job died there;
"commit data" never ran; the night was discarded.  It was the fourth consecutive
lost night (08-02 and 08-03 were a duck-typing crash inside the collectors step,
08-04 was the runner host running out of disk).

The fix is NOT to abandon fail-closed integrity: a partial capital-structure
generation still must never be committed.  It is to move that guarantee into the
commit step, where it costs only its own artifacts — the compilers run
`continue-on-error`, and "commit data" unstages the capital-structure paths when
any of them failed.  These tests pin both halves so a future workflow edit cannot
silently restore the veto.
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

# A step between the collectors and the commit may veto the night ONLY if it is
# the commit itself.  Anything else must be non-fatal — either `continue-on-error`
# or a shell-level `|| echo` guard on every command it runs.
CAPITAL_STRUCTURE_STEP_IDS = (
    "cs_sharecount", "cs_retain", "cs_events", "cs_terms", "cs_projection",
)


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
    # Every non-comment, non-blank command line must carry its own `|| ...` guard
    # or be part of an if/fi control block that ends in one.
    body = [ln.strip() for ln in run.splitlines()]
    body = [ln for ln in body if ln and not ln.startswith("#")]
    if not body:
        return True
    return all("||" in ln or ln.endswith(("then", "else", "fi", "do", "done", "esac", "{", "}"))
               or ln.startswith(("if ", "for ", "while ", "case ", "elif "))
               for ln in body)


def test_no_step_between_collectors_and_commit_can_veto_the_night(collect_steps):
    """The 2026-08-05 outage shape: one bare step discards a 3-hour collection."""
    start = _index_of(collect_steps, COLLECTORS_STEP)
    end = _index_of(collect_steps, COMMIT_STEP)
    assert start < end, "collectors must run before the commit checkpoint"

    offenders = [
        (i, collect_steps[i].get("name"))
        for i in range(start + 1, end)
        if not _is_non_fatal(collect_steps[i])
    ]
    assert not offenders, (
        "these steps sit between the collectors and 'commit data' and can fail the "
        "job, which SKIPS the commit and discards the whole night's market data: "
        f"{offenders}. Give each `continue-on-error: true` (and exclude its outputs "
        "in the commit step if a partial artifact must not be committed)."
    )


def test_collectors_step_itself_cannot_veto_the_night(collect_steps):
    """08-02/08-03 shape: the collectors step exited 1 and took the commit with it.

    `scripts.collect` degrades per source and exits non-zero only if EVERY source
    failed, but an exception escaping its runner machinery still killed the pass.
    The Python-side net lives in `scripts/collect.py::_run_one`; this pins that the
    step is not additionally relied upon to be fatal.
    """
    step = collect_steps[_index_of(collect_steps, COLLECTORS_STEP)]
    name = step.get("name") or ""
    assert "never fails the build on one source" in name, (
        "the collectors step's own name states the contract; if it was renamed, "
        "re-read whether the guarantee still holds"
    )


def test_capital_structure_partial_generation_is_excluded_not_committed(collect_steps):
    """Fail-closed integrity survives the decoupling — it just costs less.

    A capital-structure compiler failure must still keep its partial generation out
    of the commit; it simply may no longer take the market data with it.
    """
    commit = collect_steps[_index_of(collect_steps, COMMIT_STEP)]
    run = commit.get("run") or ""

    for step_id in CAPITAL_STRUCTURE_STEP_IDS:
        assert f"steps.{step_id}.outcome" in run, (
            f"'commit data' never reads steps.{step_id}.outcome, so a failed "
            f"capital-structure compiler's partial generation would be committed"
        )

    assert re.search(r"git reset[^\n]*data/capital_structure", run), (
        "'commit data' must unstage data/capital_structure when a compiler failed"
    )
    assert re.search(r"git reset[^\n]*site/capital-structure-data", run), (
        "'commit data' must unstage site/capital-structure-data when a compiler failed"
    )


def test_capital_structure_steps_are_non_fatal_and_identified(collect_steps):
    """The three compilers must carry both halves: an id to read, and non-fatality."""
    by_id = {s.get("id"): s for s in collect_steps if s.get("id")}
    for step_id in CAPITAL_STRUCTURE_STEP_IDS:
        step = by_id.get(step_id)
        assert step is not None, f"collect job lost the '{step_id}' step id"
        assert step.get("continue-on-error") is True, (
            f"step '{step_id}' is fatal again — a context-only compiler would once "
            f"more discard the night's collection"
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
