"""scripts/check_self_mod_fence.py — F2 self-modification fence (R-AUT-5).

Checks whether a PR carries the loop namespace AND touches the IMMUTABLE set.
If both conditions are true, the PR is BLOCKED (exit 1).

Attribution is by namespace + trailer, NOT identity (R-AUT-5):
  - Loop namespace: branch prefix 'metabolism/' or 'claude/loop-'
  - Loop trailer:   'Loop-Authored:' commit trailer present in any commit on the branch

The IMMUTABLE set (hard-coded here and in the F1/F3 manifests):
  .claude/hooks/**
  .claude/settings.json
  .claude/settings.local.json
  .github/workflows/**
  config/grader_manifest.yml
  config/capability_manifest.yml
  config/metabolism_budget.yml
  engine/neuralweb/capability_broker.py
  scripts/check_self_mod_fence.py
  scripts/check_grader_manifest.py
  research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md   (the tier table lives here)
  engine/standout_audit.py               (SA-R2/SA-R4: US taxonomy constants + sensor defs)
  engine/china_standout_audit.py         (SA-R2/SA-R4: CN taxonomy constants)
  engine/standout_review.py              (SA-R4: clamp/whitelist enforcement engine)
  config/standout_review.yml             (SA-R4: coverage clamps + whitelist bounds)

Fail-CLOSED contract:
  - Unclassifiable inputs (can't determine branch, can't list files) → BLOCK (exit 1).
  - Any error in classification → BLOCK (exit 1).
  - Only CLEAR non-loop-namespace PRs with no loop trailers pass freely.

Human/operator PRs (no loop namespace, no loop trailer) always pass.
Loop PRs touching NON-immutable paths always pass.
Only loop + immutable is blocked.

Usage:
    python3 scripts/check_self_mod_fence.py \\
        --branch <branch_name> \\
        --files <file1> [<file2> ...] \\
        [--trailers <raw_trailer_text>]

    python3 scripts/check_self_mod_fence.py --selftest

Exit codes:
    0   OK (human PR, or loop PR touching no immutable path)
    1   BLOCKED (loop PR touching immutable path, or unclassifiable input)
"""
from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

# ── Immutable path patterns (glob-style) ─────────────────────────────────────

IMMUTABLE_PATTERNS: list[str] = [
    ".claude/hooks/**",
    ".github/workflows/**",
    "config/grader_manifest.yml",
    "config/capability_manifest.yml",
    "config/metabolism_budget.yml",
    "engine/neuralweb/capability_broker.py",
    "scripts/check_self_mod_fence.py",
    "scripts/check_grader_manifest.py",
    "research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md",
    # V2-A additions (R-V2-8)
    "config/metabolism_anomaly.yml",
    "config/fable_mode_core.md",
    # V2-B additions (R-V2-8)
    "config/metabolism_schedule.yml",
    # V2-D additions (R-V2-8)
    "config/ux_simplicity_rules.yml",
    # V2-C Unit 6 addition (R-V2-8): the Uncovered-Domain Scout's reference
    # universe. A loop that could add domains could manufacture its own charter
    # mandate — expanding the proposable universe is operator-only.
    "config/nw_information_domains.yml",
    # tap.py holds the T2 safe-default table (conservative timeout actions); a
    # loop-authored branch must NOT flip e.g. promote_lobe's default to 'promote'.
    # Fenced so the docstring's immutability claim is structural, not honor-system.
    "engine/metabolism/tap.py",
    # V3 additions (R-V3-8 / R-V2-8): SLA config + reasoning-receipt schema.
    # The loop must not loosen its own freshness alarms (SLA) or alter the
    # pre-send-gate receipt contract (R-V3-1, R-V3-5a).
    "config/metabolism_context_sla.yml",
    "docs/METABOLISM_REASONING_RECEIPT.md",
    # V4-W3 addition (R-V4-4): the mission self-model.
    # The loop must not rewrite its own purpose.
    "config/nw_mission.yml",
    # V8-A addition (R-V8-3): immune recipe registry + spurious-checks allowlist.
    # Fenced NOW so R-V8-3b auto-merge inherits the guarantee that the loop
    # cannot expand its own auto-merge allowlist or remove spurious-check filters.
    "config/metabolism_immune.yml",
    # V9 addition (R-V9-8): attention-economy policy (band→resource shares,
    # max_focus_lobes, dispatch priorities).  A loop that could edit its own
    # docket_share could grant itself more tokens — operator T2 only.
    "config/metabolism_attention.yml",
    # SA-R2/SA-R4 additions: Standout Accountability ruler files.
    # The attribution taxonomy constants (SA-R2) and coverage clamps (SA-R4)
    # are the loop's own ruler/yardstick — allowing the loop to modify them is
    # equivalent to letting it grade its own homework.  Operator PR required.
    # Note: these files may not exist yet (built in future SA waves); the fence
    # blocks any loop-authored PR that creates OR modifies them.
    "engine/standout_audit.py",
    "engine/china_standout_audit.py",
    "engine/standout_review.py",
    "config/standout_review.yml",
    # settings.json lives at .claude/ (the repo root has no settings.json).
    # This file wires the model-routing-guard hooks; a loop PR that edits it
    # could disable the dispatch-time permission guard.
    ".claude/settings.json",
    ".claude/settings.local.json",
]

# ── Loop namespace markers ────────────────────────────────────────────────────

LOOP_BRANCH_PREFIXES: list[str] = [
    "metabolism/",
    "claude/loop-",
]

LOOP_TRAILER_KEY = "Loop-Authored:"


# ── Classification helpers ───────────────────────────────────────────────────

def _is_loop_branch(branch: str) -> bool:
    """Return True if the branch name carries the reserved loop namespace."""
    for prefix in LOOP_BRANCH_PREFIXES:
        if branch.startswith(prefix):
            return True
    return False


def _has_loop_trailer(trailers_text: str) -> bool:
    """Return True if the raw commit-trailer text contains a 'Loop-Authored:' line."""
    for line in trailers_text.splitlines():
        if line.strip().startswith(LOOP_TRAILER_KEY):
            return True
    return False


def _matches_immutable(file_path: str) -> bool:
    """Return True if the file path matches any immutable pattern."""
    # Normalise separators; strip leading '/' and './' so that './config/foo.yml'
    # and 'config/foo.yml' resolve to the same key.
    norm = file_path.replace("\\", "/").lstrip("/")
    if norm.startswith("./"):
        norm = norm[2:]
    for pattern in IMMUTABLE_PATTERNS:
        # fnmatch handles * and ** matching
        if fnmatch.fnmatch(norm, pattern):
            return True
        # Also handle ** as "any depth" by trying with partial prefix
        if "**" in pattern:
            # Simple sub-match: strip the trailing /** and check prefix
            base = pattern.replace("/**", "").replace("**", "")
            if base and norm.startswith(base.rstrip("/")):
                return True
    return False


# ── Main check ───────────────────────────────────────────────────────────────

def check(
    branch: str,
    changed_files: list[str],
    trailers_text: str = "",
) -> tuple[int, str]:
    """Run the self-modification fence.

    Parameters
    ----------
    branch : str
        The PR's branch name.
    changed_files : list[str]
        List of files changed by the PR (relative paths).
    trailers_text : str
        Raw commit-trailer text from the commits on the branch.

    Returns
    -------
    (exit_code, message)
        exit_code 0 → PASS; 1 → BLOCKED.
        message explains the decision.
    """
    # Fail-closed: unclassifiable inputs → BLOCK
    if not branch:
        return 1, "BLOCKED: branch name is empty — unclassifiable, fail-closed."

    # Determine if this is a loop PR
    try:
        loop_branch = _is_loop_branch(branch)
        loop_trailer = _has_loop_trailer(trailers_text) if trailers_text else False
        is_loop_pr = loop_branch or loop_trailer
    except Exception as e:
        return 1, f"BLOCKED: could not classify PR as loop/human ({e}) — fail-closed."

    # Human PRs always pass
    if not is_loop_pr:
        return 0, (
            f"PASS: branch '{branch}' carries no loop namespace or trailer — "
            f"human/operator PR; immutable-set check skipped."
        )

    # Loop PR: check for immutable-path touches
    try:
        immutable_hits = [f for f in changed_files if _matches_immutable(f)]
    except Exception as e:
        return 1, f"BLOCKED: could not classify changed files ({e}) — fail-closed."

    if immutable_hits:
        reason = "loop branch prefix" if loop_branch else "Loop-Authored: commit trailer"
        return 1, (
            f"BLOCKED: loop PR (attributed by {reason}) touches the IMMUTABLE set.\n"
            f"  Branch: {branch}\n"
            f"  Immutable files touched:\n"
            + "".join(f"    - {f}\n" for f in immutable_hits)
            + "\n"
            f"  The IMMUTABLE set is defined in R-AUT-4 and config/grader_manifest.yml.\n"
            f"  Grader-modifying changes require T2 operator-tap and a human-authored PR.\n"
            f"  Self-modification fence violations cannot be overridden automatically."
        )

    loop_reason = "loop branch prefix" if loop_branch else "Loop-Authored: commit trailer"
    return 0, (
        f"PASS: loop PR (attributed by {loop_reason}) branch='{branch}' "
        f"touches {len(changed_files)} file(s), none in the IMMUTABLE set."
    )


# ── Selftest ──────────────────────────────────────────────────────────────────

def selftest() -> int:
    """Prove the fence blocks loop+immutable and allows the other three cases."""
    print("Running selftest...")
    failures: list[str] = []

    cases = [
        # (branch, files, trailers, expected_exit, label)
        (
            "metabolism/some-lobe",
            ["config/grader_manifest.yml", "data/metabolism/heartbeat.jsonl"],
            "",
            1,  # BLOCKED — loop branch + immutable
            "loop branch prefix + immutable path → BLOCKED",
        ),
        (
            "claude/loop-propose-til",
            ["engine/neuralweb/capability_broker.py"],
            "",
            1,  # BLOCKED — loop prefix + immutable
            "loop branch prefix claude/loop-* + immutable → BLOCKED",
        ),
        (
            "claude/some-human-pr",
            ["config/grader_manifest.yml"],
            "",
            0,  # PASS — human branch (no loop prefix)
            "human branch touching immutable path → allowed",
        ),
        (
            "metabolism/some-lobe",
            ["engine/neuralweb/some_new_organ.py", "data/neuralweb/foo.json"],
            "",
            0,  # PASS — loop branch but NOT immutable paths
            "loop branch touching non-immutable paths → allowed",
        ),
        (
            "claude/human-pr",
            ["engine/neuralweb/capability_broker.py"],
            "Loop-Authored: propose-lobe run=abc123",  # trailer present
            1,  # BLOCKED — loop trailer + immutable
            "loop trailer + immutable path → BLOCKED",
        ),
        (
            "claude/human-pr",
            ["engine/neuralweb/capability_broker.py"],
            "Co-Authored-By: human@example.com",  # no loop trailer
            0,  # PASS — no loop namespace
            "human trailer + immutable path → allowed",
        ),
        (
            "metabolism/owns-fence",
            [".claude/hooks/model_routing_guard.py"],
            "",
            1,  # BLOCKED — loop + .claude/hooks/**
            "loop branch + .claude/hooks/** → BLOCKED",
        ),
        (
            "metabolism/owns-workflow",
            [".github/workflows/ci.yml"],
            "",
            1,  # BLOCKED — loop + .github/workflows/**
            "loop branch + .github/workflows/** → BLOCKED",
        ),
        (
            "",  # empty branch → unclassifiable → fail-closed
            ["anything.py"],
            "",
            1,
            "empty branch → unclassifiable → BLOCKED (fail-closed)",
        ),
        # SA-R2/SA-R4: standout ruler files → BLOCKED for loop PRs
        (
            "metabolism/neuter-guards",
            [".claude/settings.json"],
            "",
            1,  # BLOCKED — loop PR touching hook-wiring settings file
            "loop branch + .claude/settings.json → BLOCKED",
        ),
        (
            "metabolism/neuter-guards",
            [".claude/settings.local.json"],
            "",
            1,  # BLOCKED — loop PR touching hook-wiring settings file
            "loop branch + .claude/settings.local.json → BLOCKED",
        ),
        (
            "metabolism/self-tune-ruler",
            ["engine/standout_audit.py"],
            "",
            1,  # BLOCKED — SA-R2: loop may not move its own ruler
            "loop branch + engine/standout_audit.py → BLOCKED (SA-R2)",
        ),
        (
            "metabolism/self-tune-ruler",
            ["engine/china_standout_audit.py"],
            "",
            1,  # BLOCKED — SA-R2: CN taxonomy constants
            "loop branch + engine/china_standout_audit.py → BLOCKED (SA-R2)",
        ),
        (
            "metabolism/self-tune-ruler",
            ["engine/standout_review.py"],
            "",
            1,  # BLOCKED — SA-R4: clamp enforcement engine
            "loop branch + engine/standout_review.py → BLOCKED (SA-R4)",
        ),
        (
            "metabolism/self-tune-ruler",
            ["config/standout_review.yml"],
            "",
            1,  # BLOCKED — SA-R4: coverage clamp values
            "loop branch + config/standout_review.yml → BLOCKED (SA-R4)",
        ),
    ]

    for branch, files, trailers, expected_exit, label in cases:
        rc, msg = check(branch, files, trailers)
        status = "PASS" if rc == expected_exit else "FAIL"
        if rc != expected_exit:
            failures.append(f"{label}: expected exit {expected_exit}, got {rc} — {msg[:120]}")
        print(f"  [{status}] {label}")

    if failures:
        print("\nSELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("selftest OK")
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="F2 self-modification fence — blocks loop PRs touching the IMMUTABLE set."
    )
    ap.add_argument(
        "--branch",
        default="",
        help="PR branch name.",
    )
    ap.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="List of changed files (relative paths).",
    )
    ap.add_argument(
        "--trailers",
        default="",
        help="Raw commit-trailer text from the PR's commits.",
    )
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="Run synthetic selftest; exit 0 on pass, 1 on failure.",
    )
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    # Fail-closed: if we can't even parse the arguments, block.
    exit_code, message = check(
        branch=args.branch,
        changed_files=args.files or [],
        trailers_text=args.trailers or "",
    )

    if exit_code != 0:
        print(message, file=sys.stderr)
    else:
        print(message)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
