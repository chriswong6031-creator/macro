"""Pin the award-event bundle validator's CALL-SITE wiring, not just its body.

2026-08-08: the first daily run ever to reach the serialized publish lane's
validator died twice over — the workflow passed the bundle array
(snapshots, actions, state) into a STATE SNAPSHOTS ACTIONS positional
contract, and, once reordered, the file-path invocation could not import
``collectors.usaspending_awards`` because sys.path[0] was scripts/ci/.
Both defects were invisible to the existing function-level tests: the guard
had been dark behind the upstream workspace-schema red since it shipped.
These tests exercise the wiring exactly as the workflow does.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "government-revenue-live.yml"
SCRIPT = REPO / "scripts" / "ci" / "validate_government_revenue_award_event_bundle.py"
BUNDLE = [
    REPO / "data" / "government_revenue" / "award_event_projection_state.json",
    REPO / "data" / "government_revenue" / "award_event_snapshots.parquet",
    REPO / "data" / "government_revenue" / "award_action_versions.parquet",
]


def _invocation_args() -> list[str]:
    src = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"python scripts/ci/validate_government_revenue_award_event_bundle\.py"
        r"((?:\s*\\\n\s*\S+)+)",
        src,
    )
    assert match, "validator invocation not found in government-revenue-live.yml"
    return [
        line.strip().rstrip("\\").strip()
        for line in match.group(1).splitlines()
        if line.strip().rstrip("\\").strip()
    ]


def test_workflow_passes_state_snapshots_actions_in_that_order():
    args = _invocation_args()
    assert len(args) == 3, f"expected 3 positional paths, got {args}"
    assert args[0].endswith("award_event_projection_state.json"), args
    assert args[1].endswith("award_event_snapshots.parquet"), args
    assert args[2].endswith("award_action_versions.parquet"), args
    # Passing the bundle array put a parquet where json.loads expected the
    # state object — any regression back to "${...[@]}" must fail here.
    assert not any(arg.startswith("$") for arg in args), args


def test_script_passes_as_invoked_by_the_workflow():
    """Run the script the exact way the workflow does: file path, repo-root
    CWD, no PYTHONPATH — covering the sys.path bootstrap and the committed
    bundle in one end-to-end pass."""
    if not all(path.exists() for path in BUNDLE):
        # A checkout without the collector's first committed generation is the
        # workflow's explicit "not initialized yet" branch; nothing to pin.
        import pytest

        pytest.skip("committed award-event bundle absent in this checkout")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *[str(path) for path in BUNDLE]],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=180,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
    )
    assert proc.returncode == 0, (
        f"validator failed as-invoked: stdout={proc.stdout[-400:]} "
        f"stderr={proc.stderr[-400:]}"
    )
