"""tests/test_tech_lab_offrender_budget.py — the nightly Technical Lab lane's budget.

WHY THIS EXISTS
---------------
`site/confluence_screener.html` was linked from the research mega menu on every
page of the site from 2026-07-19 and had NEVER been rendered once — the URL was
a live 404 for eight days.

The page is rendered by step 5 of daily.yml's `tech_lab_offrender`, and
committed by step 6.  Step 2 of that same job (`build_tech_lab_data`) went from
64 signals to 195 on a 231-ticker universe in #3013 — merged 2026-07-19T01:40,
about four hours BEFORE #3061 added the screener render to the tail of the same
job.  Nobody re-budgeted `timeout-minutes: 40`.  Measured from the 07-26 job
log, the expanded pass costs ~14.6s/ticker → ~56 min, so every nightly from
07-19 to 07-26 was cancelled at exactly the 40m cap partway through step 2, and
steps 3-6 — including the screener render AND the commit — were skipped.

The per-step `set +e … exit 0` wrappers did not help and could not: they make a
*script* error non-fatal, while a job timeout hard-cancels the running step,
skips every later step, and suppresses the `::warning` the step would have
printed.  The job simply reported "cancelled", which is indistinguishable at a
glance from this repo's known-benign cancellations — so an eight-day publish
outage (the screener page, plus stale tech_screener/tech_lab/tech_confluence/
tech_events/m2_profiles artifacts) drew no signal at all.

What is pinned here is the reachability of the publish tail: a budget that
covers the measured workload, and the render step still sitting ahead of the
commit step that ships it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_DAILY = _REPO / ".github" / "workflows" / "daily.yml"

# Measured worst case for the whole job (see the daily.yml note):
#   checkout up to ~15m on the 14k-file tree  + build_tech_lab_data ~57m
#   + build_tech_confluence ~13m + screener page ~1m + m2_profiles ~2m
#   + commit/push-retry band up to ~10m  ≈  98m
# The combo-miner cost is MEASURED (panel 335.4s + mine_long 186.6s + mine_short
# ≈ mine_long + write, 2026-07-27 on the runner host), not the "~8 min" the
# workflow comment used to inherit. A stale step-cost label is what caused the
# outage this suite exists for — re-measure when you touch this number.
# The floor is set just above that; the shipped value carries extra headroom.
_MEASURED_WORST_CASE_MIN = 98
_FLOOR_MIN = 100


def _jobs() -> dict:
    return yaml.safe_load(_DAILY.read_text(encoding="utf-8"))["jobs"]


def _tech_lab() -> dict:
    jobs = _jobs()
    assert "tech_lab_offrender" in jobs, "tech_lab_offrender job vanished from daily.yml"
    return jobs["tech_lab_offrender"]


def _step_names(job: dict) -> list[str]:
    return [s.get("name", "") for s in job.get("steps", [])]


def test_timeout_covers_the_measured_workload():
    """A 40m cap against a ~93m job silently skipped the publish tail for 8 nights."""
    timeout = _tech_lab().get("timeout-minutes")
    assert isinstance(timeout, int), "tech_lab_offrender must declare timeout-minutes"
    assert timeout >= _FLOOR_MIN, (
        f"tech_lab_offrender timeout-minutes={timeout} is below the {_FLOOR_MIN}m floor. "
        f"The job's measured worst case is ~{_MEASURED_WORST_CASE_MIN}m and its LAST step "
        f"is the commit that publishes the screener page + Technical Lab artifacts. "
        f"Under-budgeting this job does not fail loudly — it reports 'cancelled' and "
        f"publishes nothing. Re-measure and re-budget rather than lowering this floor."
    )


def test_screener_render_still_precedes_the_commit_that_ships_it():
    """The page only reaches main if its render step runs before the commit step."""
    names = _step_names(_tech_lab())
    render = [i for i, n in enumerate(names) if "confluence screener page" in n]
    commit = [i for i, n in enumerate(names) if n.startswith("commit Technical Lab")]
    assert render, f"confluence screener render step missing from tech_lab_offrender: {names}"
    assert commit, f"commit step missing from tech_lab_offrender: {names}"
    assert render[0] < commit[0], (
        "the confluence screener renders AFTER the commit step — site/confluence_screener.html "
        "would never reach main, which is exactly the 2026-07-19 defect"
    )


def test_the_commit_step_stages_the_screener_page():
    """`git add site/confluence_screener.html` is what makes the page public."""
    steps = _tech_lab()["steps"]
    commit = next(s for s in steps if s.get("name", "").startswith("commit Technical Lab"))
    body = commit["run"]
    assert "site/confluence_screener.html" in body, (
        "the commit step no longer stages site/confluence_screener.html — the mega-menu "
        "link on every page would 404"
    )
    assert "site/og/confluence_screener.png" in body, (
        "the commit step no longer stages the screener's og:image share card"
    )


def test_heavy_offrender_jobs_that_commit_declare_a_timeout():
    """A commit-bearing nightly job with no budget is the same failure with no cap at all."""
    for name, job in _jobs().items():
        if not isinstance(job, dict):
            continue
        commits = any(
            "git commit" in (s.get("run") or "") for s in job.get("steps", []) or []
        )
        if not commits:
            continue
        assert isinstance(job.get("timeout-minutes"), int), (
            f"daily.yml job {name!r} commits artifacts but declares no timeout-minutes"
        )
