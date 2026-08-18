---
workstream: WS:BREATHING-PLATFORM
session: claude/closepass-bootstrap-drift
model: opus
ended_because: complete
mission: >
  Close the two observability gaps found on 2026-08-18 while deploying PR #5862: the
  close-pass run receipt could not say WHICH BOOTSTRAP ran, and nothing anywhere compared
  the launchd-installed snapshot to origin/main. Both gaps are why a merged fix sat inert
  on the host for three days and cost W-ACCEPT day 1 a board.
state_before: >
  scripts/close_pass_host_runner.py recorded `code_sha` (the LANE worktree's git HEAD,
  hard-reset to origin/main every run) and a bare `runner_sha` (a sha256 PREFIX of
  __file__) that was compared to nothing. The two rendered side by side as
  indistinguishable hex - the live 2026-08-18 receipt read
  `"runner_sha": "cde03d71de97"` beside `"code_sha": "af416e4a1066..."`. The installed
  snapshot at $HOME/Library/Application Support/macro-closepass/ was byte-identical to
  PRE-#5862 main, dated Aug 15 19:54, and no check, test or nightly probe could see it.
  scripts/close_pass_slo_report.py graded latency legs only and never read a host receipt.
changed:
  - path: scripts/close_pass_host_runner.py
    what: >
      Receipt schema v1 -> v2. `runner_sha` replaced by a namespaced `bootstrap` block
      (path, full 64-hex file_sha256, mtime, is_installed_copy, installed_path,
      installed_file_sha256, main_file_sha256, matches_main, commits_behind, detail),
      filled at receipt CONSTRUCTION so a lane_unprepared refusal still names the
      plumbing that refused. New compare_bootstrap_to_main() grades the executing bytes
      against the lane's origin/main copy (one file read, no network, no subprocess on
      the healthy path); _bootstrap_commits_behind() walks the vintage with two bounded
      git metadata calls paid ONLY after a mismatch is proven; announce_bootstrap()
      emits `::error ... BOOTSTRAP DRIFT` with both digests, the distance, the snapshot
      mtime and the re-install command. prepare_lane's fail-closed refusal untouched.
  - path: scripts/close_pass_slo_report.py
    what: >
      New bootstrap leg. read_receipts()/bootstrap_state()/bootstrap_verdict()/
      bootstrap_footer() + a `bootstrap` table column + `--receipts-dir` + JSON schema
      v1 -> v2 with a top-level bootstrap_verdict. Exits 1 on drift. A receipt whose
      schema predates the reading checkout's is drift BY PROOF - the merged-but-not-
      deployed detector, which needs no cooperation from the stale bootstrap.
  - path: scripts/install_closepass_launchd.sh
    what: >
      Freeze semantics UNCHANGED (still exactly one operator-run install-time cp). Now
      reports whether that cp moved anything (first install / already at this vintage /
      DEPLOYED old -> new) and prints the digest-comparison and drift-leg commands.
  - path: tests/test_close_pass_host_runner.py
    what: >
      Lane fixture now carries origin/main's own copy of the runner, so the default lane
      has NO drift and every drift test must create the condition. Six new wiring tests
      through the real run(): clean path costs no git; drift fails loudly, names the
      remedy and STILL publishes; unknown distance is None not 0; a match against a
      STALE reference is not certified; an unprepared lane still records who ran; the
      runner never deploys itself.
  - path: tests/test_close_pass_slo_report.py
    what: >
      Autouse fixture pins every test away from the real host receipts (the first run
      graded this Mac Studio's live Application Support state and reddened four unrelated
      latency assertions). Golden table + JSON updated; seven new tests for the leg.
  - path: tests/test_close_pass_lane.py
    what: >
      Replaced the runner_sha assertion; new test pinning that the freeze is disclosed
      every run and that the installer still holds exactly one cp.
  - path: agentos/discoveries/DSC-LAUNCHD-RUNS-A-FROZEN-SNAPSHOT-NOT-THE-REPO.md
    what: the landmine record for the whole ops/launchd/ class, not just this lane
verified:
  - claim: The vintage walk returns the true distance against REAL git, and None for a file git has never seen.
    command: "python3 -c 'import scripts.close_pass_host_runner as R; R._bootstrap_commits_behind(...)' over blobs extracted with `git show <sha>:scripts/close_pass_host_runner.py`"
    result: "af416e4a10 -> 0, 964ec2b1d6 -> 1, unknown file -> None"
  - claim: The three emission paths produce the intended annotations against the REAL lane worktree at af416e4a1066.
    command: "python3 - <<'PY' ... R.announce_bootstrap(R.compare_bootstrap_to_main(lane, ident, stale=...)) ... PY"
    result: "drifted -> ::error BOOTSTRAP DRIFT '1 commit(s) behind' with af0afabbc397/cde03d71de97; clean -> 'no drift'; clean+stale -> ::warning UNVERIFIED"
  - claim: The report's drift leg fires against the host's ACTUAL receipts today and exits 1.
    command: "python3 -m scripts.close_pass_slo_report --sessions 3 --now 2026-08-18T06:00:00Z"
    result: "EXIT=1, 'BOOTSTRAP DRIFT on 2026-08-14: receipt schema close_pass.host_run/v1 predates this checkout's close_pass.host_run/v2'"
  - claim: All three close-pass suites pass.
    command: "python3 -m pytest tests/test_close_pass_host_runner.py tests/test_close_pass_slo_report.py tests/test_close_pass_lane.py -q"
    result: "200 passed"
  - claim: The GitHub-annotation and script-import-pinning house guards stay green.
    command: "python3 -m pytest tests/test_gh_annotation_line_start.py tests/test_check_script_import_pinning.py -q"
    result: "15 passed"
  - claim: The installed snapshot was byte-identical to the checkout BEFORE this branch, so the drift the leg reports today is real and not an artifact.
    command: "shasum -a 256 \"$HOME/Library/Application Support/macro-closepass/close_pass_host_runner.py\" scripts/close_pass_host_runner.py (at origin/main)"
    result: "both cde03d71de97... at origin/main; the branch copy is 95300f45da52..."
  - claim: The agent OS store still validates with zero errors after the new discovery record.
    command: "python3 scripts/agentos.py validate"
    result: "172 records - 0 error(s), 13 warning(s) (all pre-existing phantom-path warnings from the sparse worktree)"
unverified:
  - claim: A real launchd firing writes a v2 receipt whose bootstrap block reads matches_main true.
    what_would_verify: "After merging and re-running the installer: /usr/bin/python3 \"$HOME/Library/Application Support/macro-closepass/close_pass_host_runner.py\" --dry-run, then read runs/<session>.json"
  - claim: The four self-hosted runner agents on this box share $HOME with the launchd agent on EVERY macstudio pool host.
    what_would_verify: "Enumerate the macstudio pool and check ~/Library/LaunchAgents/com.macro.closepass.plist on each - this is why a close-pass.yml drift step was REJECTED rather than shipped"
unresolved:
  - >
    The bootstrap verdict is graded only when prepare_lane SUCCEEDS. A holiday fast-exit
    (`not_a_session`, step 1) returns before any reset, so its receipt carries identity
    but no verdict. That is honest (nothing was compared) but it means a host that only
    ever fires on holidays would never be graded. Not a real exposure - the lane fires
    every session - but named so nobody reads the holiday receipt as clean.
  - >
    `commits_behind` counts commits touching this file only, capped at BOOTSTRAP_LOG_SCAN
    (50). Past that the answer is None, never a number. A bootstrap more than 50 file-
    commits stale reports DRIFT with an unknown distance, which is the right failure.
next_actions:
  - >
    (owned by this session) After #5866 merges: run `bash scripts/install_closepass_launchd.sh`
    and verify `shasum -a 256` on the installed copy equals merged main's, then a
    `--dry-run` from the INSTALLED path showing bootstrap.matches_main true in the receipt.
    Merging alone provably does not deploy this file - that is the whole subject of the PR.
  - >
    W-ACCEPT day 2/3 grading: `python3 -m scripts.close_pass_slo_report --sessions 3`.
    Exit 1 with a BOOTSTRAP DRIFT footer now means "the host is running code we did not
    merge", which is a deploy action, NOT a latency investigation.
  - >
    Consider extending the same disclosure to the other launchd wrappers named in
    DSC:LAUNCHD-RUNS-A-FROZEN-SNAPSHOT-NOT-THE-REPO (prophet_rescue_launchd.py,
    ops/launchd/com.macro.chainheat.plist). Same freeze, same blind spot, not yet measured.
do_not_redo:
  - >
    Do NOT make the runner self-update to "fix" drift. The freeze is the feature
    (install_closepass_launchd.sh:49): a mid-day push to main must not change what the
    clock executes mid-session. Disclosure with the exact command attached is the whole
    remedy this lane owns, and a test pins that the file imports no shutil and writes
    nothing to its own installed path.
  - >
    Do NOT add a bootstrap-drift step to .github/workflows/close-pass.yml. Considered and
    rejected: the four runner agents on THIS box do run as chriswong with the same $HOME
    (verified), but `runs-on: [self-hosted, macstudio]` is a multi-host pool and the
    launchd agent lives on one machine. A check that can land on a host without the agent
    reports "not installed" and fails open - a detector that silently goes blind, which is
    the exact class this work exists to close.
  - >
    Do NOT grade the whole reported window on bootstrap state. Deliberately only the
    NEWEST session that has a receipt decides the exit code; older drifted rows stay
    visible in the column but do not hold the report red for a week after a heal, which
    is how a leg gets ignored.
  - >
    Do NOT rename `code_sha` or fold the bootstrap digests back into flat `*_sha` keys.
    The namespacing IS the fix for gap 1, and a test asserts no bare `*_sha` key exists
    inside the bootstrap block.
danger_areas:
  - >
    scripts/close_pass_slo_report.py's DEFAULT receipts dir is live host state
    (HOST.support_dir()/runs). Any new test in that module must inherit the autouse
    `_off_host` fixture or it will grade this Mac Studio's real receipts and pass or fail
    on which machine ran it. That is not hypothetical - it happened on the first run here.
  - >
    Anything added to run() between prepare_lane and close_pass_publish spends the
    16:00-16:12 ET wait window. The drift check is deliberately one file read on the
    healthy path and pays its two git calls only after a mismatch is already proven.
  - >
    `matches_main` is tri-state and None is NOT a pass. Any consumer written as
    `if not matches_main: alarm` or `if matches_main is not False: ok` breaks the
    fail-closed contract in one direction or the other.
prs: [5866]
discoveries:
  - "DSC:LAUNCHD-RUNS-A-FROZEN-SNAPSHOT-NOT-THE-REPO"
---

# Breathing Platform — close-pass bootstrap drift (2026-08-18)

## The one sentence

`launchctl` runs a **frozen snapshot**, not the repo, and the receipt field that was
always fresh (`code_sha`, the lane's HEAD) described the wrong file — so a bootstrap
three days stale produced a receipt that read as perfect.

## What a stranger needs to know first

The evening close pass has two vintages and only one moves when a PR merges. Before
touching anything in this lane, read
`DSC:LAUNCHD-RUNS-A-FROZEN-SNAPSHOT-NOT-THE-REPO`, then hash the file
`launchctl print gui/$(id -u)/com.macro.closepass` actually names. The repo copy you are
editing is not what fired last night.

## Where the disclosure now lives

Two instruments, both where the truth is, neither requiring a plist read:

1. **the run** — `::error title=close-pass-host::BOOTSTRAP DRIFT …` in the launchd log,
   with the distance, both digests, the snapshot mtime, and `bash scripts/install_closepass_launchd.sh`.
2. **the report** — `python3 -m scripts.close_pass_slo_report` grows a `bootstrap`
   column and **exits 1** on drift.

Both are disclosure only. Neither heals, by design.
