"""Which steps may discard a night of market data — bounded, named, and visible.

`daily.yml`'s `collect` job spends up to ~3 hours pulling the market data plane
(235 `data/stocks` names, `data/baskets/ohlcv`, the breadth close caches) and
lands all of it in ONE step: "commit data".  Any step between the collectors and
that checkpoint which exits non-zero fails the job, and GitHub then skips every
later step — including the commit.  The collected bytes live only on the runner,
where the next job's `actions/checkout` deletes them.

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
commit, and WITHOUT `continue-on-error`.  This module does not fight that pin.

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

    The 2026-08-05 shape: one bare step discards a 2h52m collection. Steps that
    must block the checkpoint belong in DELIBERATE_VETO_STEPS, where the cost is
    written down.
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
