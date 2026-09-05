"""Workflow files above GitHub's processing cap strand runs SILENTLY.

2026-08-12: daily.yml crossed ~512,000 bytes (#5362 pushed it 507,987 ->
515,780) and every subsequent run of it stranded: the 18:30-ET cron never
fired, and all four workflow_dispatch attempts (31543112462, 31550077044,
31551232668, 31553295271) sat queued with ZERO jobs materialized for hours
while every other workflow scheduled normally. Nothing surfaced the cause:
the workflow reported state=active, githubstatus was all-operational, and
`gh run cancel` / force-cancel on the stranded runs returned HTTP 500
(delete: 403). Probe evidence pinning the threshold: an identical dispatch
from a branch whose only change shrank the file to 508,552 bytes
materialized jobs in under 90 seconds (run 31553990222). The documented
limit is "512 KB"; the observed binding threshold lies in
(508552, 515780], consistent with 512,000 decimal.

The budget below is deliberately snug for daily.yml (~508.5 KB today):
any PR that grows it reds here and must SHRINK the file by extracting
inline script blocks to scripts/ci/ (blocks free of ${{ }} expressions
extract verbatim) or by chaining steps into a separate workflow — never
by deleting the load-bearing comments.

2026-08-12 diet: four inline blocks (the two engine builder spines, the
standout-audit-US commit, the cortex commit — 47,737 bytes of body) were
extracted verbatim to scripts/ci/, taking daily.yml to ~469 KB WITH the
#5362 OIP campaign-v2 steps restored. Budget tightened 509,000 -> 487,000
so the file always keeps >=25,000 bytes of emergency headroom below the
512,000 cliff; a PR that reds here diets the file the same way, never by
deleting documentation. Extraction is safe because the guards that read
step bodies resolve `bash scripts/ci/*.sh` back to the script's source via
scripts/workflow_run_source.py — DAG conformance, the push-conflict
census, the brun/ORDER visibility check and the render-options ordering
gate all see through the move (an extracted script must carry that
module's provenance marker in its first 5 lines, or resolution fails
closed). Extract more the same way; do not delete comments to fit.

2026-08-26 diet: PR #6499 had squeezed the file to ~36 bytes under budget by
stripping its own step comments. The three largest ${{ }}-free engine bodies
(commit engine outputs, the Prophet nightly builder, the Prophet checkpoint —
52,056 bytes of body) were extracted verbatim to scripts/ci/ with the marker,
restoring ~52,000 bytes of headroom (~434.8 KB on disk). Tests that read those
bodies raw were routed through scripts/workflow_run_source.py (the same seam
the guards use) with their assertions unchanged.
"""

import re
from pathlib import Path

BUDGET_BYTES = 487_000
REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def test_workflow_files_stay_under_processing_cap():
    over = {
        wf.name: wf.stat().st_size
        for wf in sorted(WORKFLOWS_DIR.glob("*.yml"))
        if wf.stat().st_size > BUDGET_BYTES
    }
    assert not over, (
        f"workflow file(s) over the {BUDGET_BYTES}-byte budget: {over}. "
        "GitHub silently stops processing a workflow file near 512,000 bytes: "
        "cron stops firing and dispatched runs strand queued with zero jobs and "
        "no error anywhere (2026-08-12 daily.yml incident — see this file's "
        "docstring). Shrink the file by extracting inline scripts or splitting "
        "steps into a chained workflow; do not delete documentation comments."
    )


def test_workflow_size_guard_is_owned_and_triggerable_in_ci():
    """The cap guard must execute, not merely exist beside the incident note."""

    manifest = (REPO_ROOT / ".github/ci/legacy-jobs.yml").read_text()
    ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text()
    run_steps = re.findall(r"^\s*run:\s*(.+)$", manifest, flags=re.MULTILINE)
    assert any("tests/test_workflow_file_size.py" in step for step in run_steps)
    assert '      - "tests/test_workflow_file_size.py"' in ci
    assert '      - ".github/workflows/**"' in ci


def test_daily_workflow_keeps_safety_margin_after_campaign_restore():
    daily = WORKFLOWS_DIR / "daily.yml"
    assert daily.stat().st_size <= BUDGET_BYTES
    assert daily.stat().st_size <= 508_000, (
        "campaign-v2 restoration must retain at least a 1,000-byte review margin "
        "below the enforced workflow budget; extract more shell into scripts/ci"
    )
