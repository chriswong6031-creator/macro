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
  .github/ci/**
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
    python3 scripts/check_self_mod_fence.py --print-planner-files

Exit codes:
    0   OK (human PR, or loop PR touching no immutable path)
    1   BLOCKED (loop PR touching immutable path, or unclassifiable input)
    2   --print-planner-files: the planner's list is malformed
    3   --print-planner-files: the planner published no list at all

--print-planner-files reads TWO sources, file first (2026-08-14, run
31775693780): ``CI_CHANGED_FILES_FILE`` names a file holding the list, and
``CI_CHANGED_FILES_JSON`` carries it inline. The file exists because the inline
form measured 350,264 bytes on PR #5578, past execve's 131,072-byte
MAX_ARG_STRLEN, and killed every pack at launch. Set-but-unreadable and empty
files are MALFORMED (exit 2), not unset: a transport that lost its payload must
fail closed, exactly like a truncated env string. Exit 3 means neither source is
configured, and only then may the caller fall back to git.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from scripts.ci_authority_paths import (
        CI_AUTHORITY_PATTERNS,
        matches_pattern_set,
    )
except ModuleNotFoundError:  # Direct ``python scripts/check_self_mod_fence.py``.
    from ci_authority_paths import CI_AUTHORITY_PATTERNS, matches_pattern_set

# ── Immutable path patterns (glob-style) ─────────────────────────────────────

IMMUTABLE_PATTERNS: list[str] = [
    *CI_AUTHORITY_PATTERNS,
    ".claude/hooks/**",
    "config/grader_manifest.yml",
    "config/capability_manifest.yml",
    # V11 addition: metabolism budget + gate policy.
    # fivehour_done_pct, weekly_done_pct, weekly_key_stop_pct, manual_floor_pct
    # and the per-cycle USD/token caps are operator-ratified spend knobs.
    # A loop-authored edit could raise its own quota ceiling or disable the
    # manual-run hard floor — operator T2 action required for any change.
    "config/metabolism_budget.yml",
    "engine/neuralweb/capability_broker.py",
    "research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md",
    # V2-A additions (R-V2-8)
    "config/metabolism_anomaly.yml",
    "config/fable_mode_core.md",
    # V2-B additions (R-V2-8)
    "config/metabolism_schedule.yml",
    # V2-D additions (R-V2-8)
    "config/ux_simplicity_rules.yml",
    # V12 addition (R-V12-3/R-V12-8): Surface Curator saturation thresholds +
    # audit byte allowance, and the attention operator_pins policy.  A loop
    # that could raise saturated_markers, the byte allowance, or unpin itself
    # could legalise its own scoreboard-stacking — operator T2 only.
    # (config/metabolism_attention.yml is already fenced below per R-V9-8.)
    "config/metabolism_surface_rules.yml",
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
    # CRX-R7 addition: Codex research lane operator policy.
    # budget_pct, sandbox, max_sessions_per_window, and case_pr_mode are
    # token-spend knobs that belong to the operator.  A loop-authored edit to
    # this file could raise its own budget ceiling or auto-promote cases without
    # human review.  Operator T2 action required for any change.
    "config/codex_lane.yml",
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
    return matches_pattern_set(norm, IMMUTABLE_PATTERNS)


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
            "metabolism/owns-ci-manifest",
            [".github/ci/legacy-jobs.yml"],
            "",
            1,  # BLOCKED — loop + packed CI manifest
            "loop branch + .github/ci/** → BLOCKED",
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


# ── CI planner file list (packs are fetch-depth:1 after #5564) ────────────────


def parse_ci_changed_files_json(raw: str | None) -> tuple[str, list[str]]:
    """Decode ci-plan's ``CI_CHANGED_FILES_JSON`` without touching git.

    Returns ``(status, paths)``:
      * ``ok`` — well-formed JSON array of strings, or the token ``null``
        (planner-verified empty / main dispatch). ``paths`` may be empty.
      * ``unset`` — env missing or blank; caller may fall back to ``git diff``.
      * ``malformed`` — present but not a JSON array of strings.

    Fail-closed belongs to the caller, and only for ``malformed`` / a failed
    git fallback after ``unset``. A depth-1 clone that cannot see
    ``origin/main...HEAD`` is not unclassifiable when ci-plan already listed
    the files (measured 2026-08-13: #5556/#5519/#5499 after #5564).
    """
    if raw is None or raw == "":
        return "unset", []
    stripped = raw.strip()
    if stripped == "null":
        return "ok", []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return "malformed", []
    if not isinstance(parsed, list) or not all(
        isinstance(path, str)
        and path
        and not any(
            ord(character) < 32
            or ord(character) == 127
            or character in {"\u0085", "\u2028", "\u2029"}
            for character in path
        )
        for path in parsed
    ):
        return "malformed", []
    return "ok", parsed


def changed_files_from_git(base_ref: str) -> list[str] | None:
    """Read both sides of a rename/copy through Git's NUL-safe status stream."""
    if not base_ref:
        return None
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--name-status",
                "-z",
                "--find-renames",
                "--find-copies",
                f"{base_ref}...HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    fields = result.stdout.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    paths: list[str] = []
    index = 0
    try:
        while index < len(fields):
            status = fields[index]
            index += 1
            if not status:
                raise ValueError("empty status")
            if status[0] in {"R", "C"}:
                paths.extend((fields[index], fields[index + 1]))
                index += 2
            else:
                paths.append(fields[index])
                index += 1
    except (IndexError, ValueError):
        return None
    paths = list(dict.fromkeys(path for path in paths if path))
    status, safe_paths = parse_ci_changed_files_json(json.dumps(paths))
    return safe_paths if status == "ok" and safe_paths else None


def read_ci_changed_files_file(path: str | None) -> tuple[str, list[str]]:
    """Decode the planner's changed-file list from a FILE, same three statuses.

    The file is the production transport since 2026-08-14 (run 31775693780):
    the same list rode a job output into every pack step's environment at
    350,264 bytes, and execve refuses a single env string past 131,072 bytes on
    Linux, so all twelve packs died before running a test. The bytes are
    identical to the env form — this only changes where they are read from.

    A configured-but-unreadable or EMPTY file returns ``malformed``, never
    ``unset``: ``unset`` licenses the caller's git fallback, and answering "no
    transport configured" for a transport that lost its payload is precisely
    the fail-open this fence's contract forbids.
    """
    if not path:
        return "unset", []
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "malformed", []
    status, paths = parse_ci_changed_files_json(raw)
    return ("malformed", []) if status == "unset" else (status, paths)


def planner_changed_files() -> tuple[str, list[str]]:
    """Read the planner authority from its bounded file transport, then legacy env."""
    if os.environ.get("CI_CHANGED_FILES_FILE"):
        return read_ci_changed_files_file(os.environ.get("CI_CHANGED_FILES_FILE"))
    return parse_ci_changed_files_json(os.environ.get("CI_CHANGED_FILES_JSON"))


def print_planner_files(raw: str | None = None) -> int:
    """CLI for the packed live-check shell. See module docstring for exit codes.

    Source order is file, then inline env: ci-plan publishes both names, and a
    stale inline string must never out-vote the artifact the packs downloaded.
    """
    if raw is not None:
        status, paths = parse_ci_changed_files_json(raw)
    else:
        status, paths = planner_changed_files()
    if status == "unset":
        return 3
    if status == "malformed":
        return 2
    sys.stdout.write("\n".join(paths))
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
        "--planner-files",
        action="store_true",
        help=(
            "Read the exact changed paths from CI_CHANGED_FILES_FILE if set, "
            "else CI_CHANGED_FILES_JSON."
        ),
    )
    ap.add_argument(
        "--base-sha",
        default="",
        help="Discover both sides of changed paths from BASE...HEAD using NUL-safe git output.",
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
    ap.add_argument(
        "--print-planner-files",
        action="store_true",
        help=(
            "Print ci-plan's changed paths (one per line), read from "
            "CI_CHANGED_FILES_FILE if set, else CI_CHANGED_FILES_JSON. "
            "Exit 0 if well-formed, 2 if malformed, 3 if neither is set."
        ),
    )
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.print_planner_files:
        return print_planner_files()

    if args.planner_files and args.base_sha:
        print("BLOCKED: choose one changed-file authority — fail-closed.", file=sys.stderr)
        return 1
    if args.planner_files:
        source_status, changed_files = planner_changed_files()
        if source_status == "malformed":
            print(
                "BLOCKED: CI_CHANGED_FILES_FILE/CI_CHANGED_FILES_JSON is malformed — fail-closed.",
                file=sys.stderr,
            )
            return 1
        if source_status == "unset":
            print(
                "BLOCKED: CI_CHANGED_FILES_FILE/CI_CHANGED_FILES_JSON is unset — fail-closed.",
                file=sys.stderr,
            )
            return 1
    elif args.base_sha:
        changed_files = changed_files_from_git(args.base_sha)
        if not changed_files:
            print("BLOCKED: could not determine changed files — fail-closed.", file=sys.stderr)
            return 1
    else:
        changed_files = args.files or []

    # Fail-closed: if we can't even parse the arguments, block.
    exit_code, message = check(
        branch=args.branch,
        changed_files=changed_files,
        trailers_text=args.trailers or "",
    )

    if exit_code != 0:
        print(message, file=sys.stderr)
    else:
        print(message)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
