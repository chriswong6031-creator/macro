"""A workflow step's ``run:`` script is LENGTH-CAPPED by GitHub — over it, the file
silently de-registers.

2026-07-27 (#3826 postmortem).  #3826 added ~1,010 characters of inline comment to
render.yml's big re-render step.  Every local gate passed — ``yaml.safe_load``,
``scripts/check_workflow_yaml.py`` (which only checks that the file loads and carries
``on:``/``jobs:``), AND ``actionlint`` 1.7.12, which models GitHub's workflow schema.
GitHub still refused the file:

* ``render.yml`` VANISHED from ``gh api repos/.../actions/workflows`` — only
  ``engine-render`` remained, so the express render lane simply stopped existing;
* every push to EVERY branch carrying the file got a zero-job FAILED run titled by
  PATH (``.github/workflows/render.yml``) instead of by ``name:`` (``render``).  That
  path-vs-name title is the signature to look for — it is the same shape as the
  metabolism-agenda col-0 incident (#2135 → #2260).

The express render lane was dead on main for ~40 minutes before anyone could see it,
because the PR's own checks were all green: this failure mode is invisible to
``gh pr checks``.  It only shows up in the BRANCH run list.

The cause is SIZE, not content, established by bisection against GitHub itself:

===================================================  =============  ==========
run: scalar                                          chars          GitHub
===================================================  =============  ==========
without the comment block                            20,563         accepted
with the comment block                               21,573         REFUSED
with equal-length plain-ASCII filler instead         21,590         REFUSED
===================================================  =============  ==========

The exact cliff between 20,563 and 21,573 was never probed (each probe costs a real
push and main was down), so this guard pins the CONSERVATIVE end: no step's ``run:``
may exceed the largest length GitHub has actually been observed to accept.

The fix when a step trips this: prose belongs in YAML comments ABOVE the step, which
the parser strips and which therefore cost the scalar nothing.  render.yml's
"DELIBERATELY omitted from this lane" block and the size-ceiling note itself both live
there now.  Do NOT "fix" this by deleting the reasoning — move it.

Run: .venv/bin/python -m pytest tests/test_render_run_size_cap.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# Largest run: scalar GitHub has been OBSERVED to accept (render.yml, 2026-07-27).
# 21,573 was refused.  Not the true cliff — the conservative side of the bracket.
OBSERVED_ACCEPTED = 20_563


def _run_steps():
    for wf in WORKFLOWS:
        try:
            doc = yaml.safe_load(wf.read_text())
        except yaml.YAMLError:
            continue  # check_workflow_yaml.py owns parse failures
        if not isinstance(doc, dict):
            continue
        for job_name, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for i, step in enumerate(job.get("steps") or []):
                if isinstance(step, dict) and isinstance(step.get("run"), str):
                    yield wf.name, job_name, i, step.get("name") or f"step[{i}]", step["run"]


def test_no_run_step_exceeds_the_observed_github_ceiling():
    over = [(f"{wf}::{job}::{name}", len(run))
            for wf, job, _, name, run in _run_steps() if len(run) > OBSERVED_ACCEPTED]
    assert not over, (
        "run: scalar over the length GitHub has been observed to accept "
        f"({OBSERVED_ACCEPTED} chars) — GitHub will DE-REGISTER the workflow and stamp "
        "zero-job path-named FAILED runs on every branch. Move prose into YAML comments "
        f"above the step (they cost the scalar nothing): {over}"
    )


def test_the_guard_is_not_vacuous():
    """A cap nothing approaches would pass forever without measuring anything."""
    steps = list(_run_steps())
    assert steps, "no run: steps found — the walker broke, not the workflows"
    assert max(len(run) for *_, run in steps) > OBSERVED_ACCEPTED * 0.5, (
        "no run: step is within 2x of the cap — either the walker is missing steps or "
        "the cap was raised without evidence"
    )


@pytest.mark.parametrize("marker", [
    "canada() {",                       # the builder this whole PR exists for
    "echo canada;;",                    # region_of arm -> push auto-selects scope=canada
    "for R in macro intl china hk canada markets gex baskets sits; do",
])
def test_the_canada_wiring_survived_the_size_fix(marker):
    """The heal must not have been 'delete the feature until it fits'."""
    assert marker in (ROOT / ".github" / "workflows" / "render.yml").read_text()
