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
"""

from pathlib import Path

BUDGET_BYTES = 509_000
WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"


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
