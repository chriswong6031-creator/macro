"""tests/test_self_mod_fence.py — F2 self-modification fence tests.

Four test groups (matching the spec):
  1. Loop PR touching immutable path → BLOCKED
  2. Human PR touching same immutable path → allowed
  3. Loop PR touching non-immutable path → allowed
  4. Unclassifiable input → BLOCKED (fail-closed)

Plus selftest.
"""
from __future__ import annotations

import pytest

from scripts.check_self_mod_fence import check, selftest, IMMUTABLE_PATTERNS, LOOP_BRANCH_PREFIXES


# ── 1. Loop PR + immutable path → BLOCKED ────────────────────────────────────

@pytest.mark.parametrize("branch,files,trailers,label", [
    (
        "metabolism/propose-til",
        ["config/grader_manifest.yml"],
        "",
        "loop branch prefix + grader_manifest",
    ),
    (
        "claude/loop-build-something",
        [".github/workflows/ci.yml"],
        "",
        "claude/loop- prefix + workflow file",
    ),
    (
        "metabolism/owns-broker",
        ["engine/neuralweb/capability_broker.py"],
        "",
        "loop branch + capability_broker.py",
    ),
    (
        "metabolism/owns-hooks",
        [".claude/hooks/model_routing_guard.py"],
        "",
        "loop branch + .claude/hooks/**",
    ),
    (
        "metabolism/adj",
        ["scripts/check_self_mod_fence.py"],
        "",
        "loop branch + check_self_mod_fence.py itself",
    ),
    (
        "metabolism/adj",
        ["scripts/check_grader_manifest.py"],
        "",
        "loop branch + check_grader_manifest.py",
    ),
    (
        "metabolism/adj",
        ["config/capability_manifest.yml"],
        "",
        "loop branch + capability_manifest.yml",
    ),
    (
        "metabolism/adj",
        ["config/metabolism_budget.yml"],
        "",
        "loop branch + metabolism_budget.yml",
    ),
    (
        "metabolism/adj",
        ["research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md"],
        "",
        "loop branch + masterplan (tier table)",
    ),
    # SA-R2/SA-R4: standout ruler files must be blocked
    (
        "metabolism/neuter-guards",
        [".claude/settings.json"],
        "",
        "loop branch + .claude/settings.json (hook-wiring guard)",
    ),
    (
        "metabolism/neuter-guards",
        [".claude/settings.local.json"],
        "",
        "loop branch + .claude/settings.local.json (hook-wiring guard)",
    ),
    (
        "metabolism/self-tune-ruler",
        ["engine/standout_audit.py"],
        "",
        "loop branch + engine/standout_audit.py (SA-R2 US taxonomy ruler)",
    ),
    (
        "metabolism/self-tune-ruler",
        ["engine/china_standout_audit.py"],
        "",
        "loop branch + engine/china_standout_audit.py (SA-R2 CN taxonomy ruler)",
    ),
    (
        "metabolism/self-tune-ruler",
        ["engine/standout_review.py"],
        "",
        "loop branch + engine/standout_review.py (SA-R4 clamp enforcement)",
    ),
    (
        "metabolism/self-tune-ruler",
        ["config/standout_review.yml"],
        "",
        "loop branch + config/standout_review.yml (SA-R4 clamp values)",
    ),
    (
        "claude/human-pr-with-trailer",
        ["config/grader_manifest.yml"],
        "Loop-Authored: propose-lobe run=abc123",
        "loop trailer + immutable path (even on human-looking branch)",
    ),
])
def test_loop_pr_immutable_is_blocked(branch, files, trailers, label):
    """Loop PRs touching the IMMUTABLE set must be BLOCKED."""
    rc, msg = check(branch=branch, changed_files=files, trailers_text=trailers)
    assert rc != 0, (
        f"[{label}] Expected BLOCKED but got PASS. "
        f"Branch='{branch}', files={files}. Message: {msg[:200]}"
    )
    assert "BLOCKED" in msg, f"[{label}] Message should say BLOCKED: {msg[:200]}"


# ── 2. Human PR + immutable path → allowed ───────────────────────────────────

@pytest.mark.parametrize("branch,files,label", [
    (
        "claude/eloquent-kilby-64ffe7",
        ["config/grader_manifest.yml"],
        "human worktree branch + grader_manifest",
    ),
    (
        "feature/update-ci",
        [".github/workflows/ci.yml"],
        "feature branch + workflow file",
    ),
    (
        "main",
        ["scripts/check_grader_manifest.py"],
        "main branch + check script",
    ),
    (
        "fix/capability-broker-patch",
        ["engine/neuralweb/capability_broker.py"],
        "human fix branch + broker",
    ),
    (
        "claude/metabolism-phase0-cage",
        ["config/grader_manifest.yml", ".github/workflows/ci.yml"],
        "this PR's own branch (human worktree) + immutable files",
    ),
])
def test_human_pr_immutable_is_allowed(branch, files, label):
    """Human PRs (no loop namespace or trailer) pass freely, even touching immutable paths."""
    rc, msg = check(branch=branch, changed_files=files, trailers_text="")
    assert rc == 0, (
        f"[{label}] Expected PASS but got BLOCKED. "
        f"Branch='{branch}'. Message: {msg[:200]}"
    )


# ── 3. Loop PR + non-immutable path → allowed ────────────────────────────────

@pytest.mark.parametrize("branch,files,label", [
    (
        "metabolism/til-fitness-card",
        ["engine/neuralweb/til_fitness.py", "data/metabolism/fitness/til.json"],
        "loop branch + new organ files",
    ),
    (
        "claude/loop-propose-til",
        ["data/metabolism/journal/cycle_001.json"],
        "loop propose branch + journal artifact",
    ),
    (
        "metabolism/learn-cycle",
        ["docs/AUTONOMY_LOG.md", "data/neuralweb/governance.jsonl"],
        "loop learn branch + docs and governance log",
    ),
])
def test_loop_pr_non_immutable_is_allowed(branch, files, label):
    """Loop PRs touching only non-immutable paths pass freely."""
    rc, msg = check(branch=branch, changed_files=files, trailers_text="")
    assert rc == 0, (
        f"[{label}] Expected PASS but got BLOCKED. "
        f"Branch='{branch}'. Message: {msg[:200]}"
    )


# ── 4. Unclassifiable → BLOCKED (fail-closed) ────────────────────────────────

def test_empty_branch_is_fail_closed():
    """Empty branch name → unclassifiable → BLOCKED."""
    rc, msg = check(branch="", changed_files=["anything.py"])
    assert rc != 0, "Empty branch must be BLOCKED (fail-closed)"
    assert "BLOCKED" in msg


# ── 5. Selftest ───────────────────────────────────────────────────────────────

def test_selftest_passes():
    """The built-in selftest covers all required cases."""
    rc = selftest()
    assert rc == 0, "check_self_mod_fence selftest must pass"


# ── 6. Pattern coverage ───────────────────────────────────────────────────────

def test_immutable_patterns_cover_all_required_paths():
    """Every path required by the spec appears in IMMUTABLE_PATTERNS."""
    required = [
        ".claude/hooks/",
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".github/workflows/",
        "config/grader_manifest.yml",
        "config/capability_manifest.yml",
        "config/metabolism_budget.yml",
        "engine/neuralweb/capability_broker.py",
        "scripts/check_self_mod_fence.py",
        "scripts/check_grader_manifest.py",
        "research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md",
        # SA-R2/SA-R4 standout ruler files
        "engine/standout_audit.py",
        "engine/china_standout_audit.py",
        "engine/standout_review.py",
        "config/standout_review.yml",
    ]
    for req in required:
        # At least one pattern must match the required path or be a prefix
        found = any(
            req in p or p.replace("/**", "").replace("**", "") in req
            for p in IMMUTABLE_PATTERNS
        )
        assert found, (
            f"Required immutable path '{req}' not covered by any IMMUTABLE_PATTERNS entry."
        )


def test_loop_branch_prefixes_are_defined():
    """The loop branch prefixes list is non-empty."""
    assert LOOP_BRANCH_PREFIXES, "LOOP_BRANCH_PREFIXES must be non-empty"
    assert "metabolism/" in LOOP_BRANCH_PREFIXES
    assert any("loop-" in p for p in LOOP_BRANCH_PREFIXES)
