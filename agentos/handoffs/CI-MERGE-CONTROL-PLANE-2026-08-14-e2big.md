---
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: ci-e2big-changed-files-bc9510
model: fable
ended_because: ci_handoff
mission: >
  Repair PR 5578's deterministic CI failure (every pack dead at launch,
  "Argument list too long") and fix the general infrastructure defect, without
  touching the Radar's frozen research conclusions.
state_before: >
  PR 5578 (14 files, armed) red on run 31775693780: ci-plan green, all 12
  packs failed to start bash, ci-gate red. merge-on-green disabled_manually
  since ~04:13Z. Main red on 6 legacy jobs across packs 0/7/8/9/11
  (producer-bake regressions). Two competing control-plane rewrites in flight
  (PR 5585 claude, PR 5591 codex); 5585 closed mid-session in a collision
  reconciliation naming 5591 canonical.
root_cause: >
  Two stacked defects. (1) Scope: ci-plan diffs from the pull_request payload
  base.sha, frozen at PR-open and not refreshed by synchronize (receipt: the
  failing run fired 9s after the head push and still carried 2ca4718 =
  main@04:12:29Z); main moved 45 commits / 8,581 distinct paths in the 2h03m
  window (nightly bake), all attributed to the PR. (2) Transport: the list
  rode a job output into pack step env as CI_CHANGED_FILES_JSON = 350,264
  bytes, over Linux's per-string execve cap MAX_ARG_STRLEN = 131,072, so
  starting /usr/bin/bash fails deterministically. See
  DSC:CI-CHANGED-FILES-ENV-HAS-AN-EXECVE-CEILING.
changed:
  - path: scripts/run_ci_pack.py
    what: >
      New --emit-changed-files writes the resolved list or the token null on
      BOTH the success and planner-fallback paths; the changed_files job
      output is replaced by changed_files_sha256 plus changed_files_count; the
      digest joins plan_hash_payload so the existing --expect-plan-sha parity
      refuses a missing, truncated, or swapped artifact; resolve_changed_files
      is file-first (CI_CHANGED_FILES_FILE) with widen-on-doubt preserved on
      the unpinned path; child environments always get the file path and never
      CI_CHANGED_FILES_JSON.
  - path: .github/workflows/ci.yml
    what: >
      Unconditional ci-changed-files artifact upload (if-no-files-found
      error); pack-side download plus path-only GITHUB_ENV export; the
      CI_CHANGED_FILES_JSON env line is deleted.
  - path: scripts/check_self_mod_fence.py and scripts/check_conflict_markers.py
    what: >
      File-first planner-list resolution; exit-code contracts unchanged
      (0/2/3 for print-planner-files; RuntimeError-red for markers).
  - path: four wired test suites
    what: >
      E2BIG execve mutation regression (18k paths, over 2MB, real spawn),
      digest fail-closed matrix, stale-base git-never-invoked pin, ci.yml
      wiring pins, fence file-mode units with env isolation fixtures.
verified:
  - claim: main healed on all 6 red legacy jobs before any re-trigger
    command: >
      Full-checkout worktree at origin/main 91c3c64: check_validated_claims
      exit 0; check_contract_drift exit 0; marketing trio 308 passed;
      seasonality calibration plus shadow 135 passed. First repro faked 146
      violations because a plain git worktree add inherits
      core.sparseCheckout=true and silently drops
      data/regime/validated_claims_allowlist.json; a full checkout is the only
      valid instrument for site- and data-scanning suites.
  - claim: the payload really exceeds the execve cap
    command: >
      git diff --name-only 2ca4718..a4e2e80 json-encodes to 8,581 paths /
      350,264 bytes; the regression reproduces OSError E2BIG via a real
      subprocess spawn on darwin and linux.
do_not_redo:
  - >
    Do not re-trigger PR 5578 by push or reopen until this transport fix is ON
    MAIN: base.sha is frozen at PR-open, so every refresh recomputes the same
    giant list under the old law and E2BIGs again.
  - >
    Do not verify site- or data-scanning guards from a default worktree: git
    worktree add inherits core.sparseCheckout=true here; disable sparse first
    or the run is invalid (146 phantom violations measured).
  - >
    Do not re-enable merge-on-green as a side effect: it was disabled manually
    during the 394-wakes-per-8h storm and the wake-diet never merged (PR 5585
    closed). Manual concluded-green merges under the wedge exception are the
    interim path; re-enablement is the control-plane program's or operator's
    call.
danger_areas:
  - >
    PR 5591 (codex control-plane lineage) carries both defects — env transport
    at two pack steps, a GITHUB_ENV injection in its plan job, and the
    stale-base law; receipts posted on the PR 2026-08-14. If it merges over
    this repair without preserving the transport, the wiring-pin regressions
    in tests/test_ci_plan_workflow.py go red BY DESIGN; the fix is to preserve
    the transport, not to delete the pins.
  - >
    The armed-PR backlog is red-stale from the pre-5592 window; a fresh main
    baseline (workflow_dispatch, preflighting for in-flight runs first) is
    needed before base-inherited-red reasoning can drain it.
unverified:
  - claim: "PR 5578's refreshed run executes packs to an honest conclusion under the repaired transport."
    what_would_verify: "A post-merge close/reopen of PR 5578 whose ci-pack jobs run test payloads (not launch failures) and conclude; green merges it, red names a genuine failure."
  - claim: "The transport survives the canonical control-plane rewrite (PR 5591 lineage)."
    what_would_verify: "tests/test_ci_plan_workflow.py wiring pins stay green after that lineage lands — zero CI_CHANGED_FILES_JSON in ci.yml, artifact steps present."
unresolved:
  - "merge-on-green remains disabled_manually (since ~04:13Z); re-enablement is the control-plane program's or operator's call — the wake-diet that motivated the disable died with PR 5585's close."
  - "The stale-base scope law (payload base.sha, frozen at PR-open) still over-widens old PRs to full suite; fixing the comparison law is 5591-lineage territory (receipts posted on that PR 2026-08-14)."
  - "The armed-PR backlog is red-stale from the pre-5592 window and needs a fresh main baseline before base-inherited-red reasoning can drain it."
next_actions:
  - "After this PR merges: close/reopen PR 5578; verify its packs EXECUTE rather than die at launch; squash-merge on concluded green under the wedge exception while the sweeper stays disabled."
  - "Dispatch one main ci.yml baseline after the merge (preflight for in-flight main runs first — a re-dispatch cancels the live proof)."
  - "Hold the 5591 lineage to the transport contract: the wiring pins go red by design if the env transport returns; preserve the transport, not the pins' deletion."
---
