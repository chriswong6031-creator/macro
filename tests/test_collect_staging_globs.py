"""Staging-glob invariant for collect-lane commit steps (neural-web D7).

The qledger grader runs inside every ``scripts.collect`` invocation
(scripts/collect.py -> grade_qledger.run_as_collect_step) and rewrites the
TRACKED ``site/qledger/track_record.json`` (un-ignored by #1139).  Any commit
step in a workflow that runs ``scripts.collect`` must therefore stage
``site/qledger/`` alongside ``data/`` — a tracked-but-unstaged modification
makes ``git pull --rebase`` refuse with "unstaged changes", and the push loop
dies after 5 attempts with only a swallowed warning.  The 2026-07-03 and
2026-07-04 daily collections were silently lost exactly this way.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# workflows whose jobs invoke scripts.collect (the qledger grader runs in all of them)
COLLECT_WORKFLOWS = ["daily.yml", "asia-close.yml"]


def _collect_commit_steps(wf_path: Path) -> list[str]:
    """Return the `run` bodies of steps that git-commit collected data."""
    doc = yaml.safe_load(wf_path.read_text())
    bodies = []
    for job in (doc.get("jobs") or {}).values():
        runs = [s.get("run", "") for s in job.get("steps", []) if s.get("run")]
        if not any("scripts.collect" in r for r in runs):
            continue
        bodies += [r for r in runs if "git add" in r and "git commit" in r]
    return bodies


def test_collect_workflows_parse():
    for name in COLLECT_WORKFLOWS:
        yaml.safe_load((WORKFLOWS / name).read_text())


def test_collect_jobs_have_commit_steps():
    for name in COLLECT_WORKFLOWS:
        assert _collect_commit_steps(WORKFLOWS / name), (
            f"{name}: no commit step found in the scripts.collect job — "
            "test needs updating if the lane was restructured"
        )


def test_collect_commit_steps_stage_qledger():
    """Every collect-lane commit step must stage site/qledger/ explicitly
    (or stage all of site/, which covers it)."""
    for name in COLLECT_WORKFLOWS:
        for body in _collect_commit_steps(WORKFLOWS / name):
            adds = re.findall(r"git add ([^\n]+)", body)
            staged = " ".join(adds)
            assert "site/qledger" in staged or re.search(r"\bsite/?(\s|$)", staged), (
                f"{name}: collect commit step stages only ({staged!r}) — "
                "site/qledger/track_record.json is written by the qledger grader "
                "during collect and MUST be staged, else the rebase+push dies on "
                "'unstaged changes' and the night's data is silently lost"
            )
