---
key: LAUNCHD-RUNS-A-FROZEN-SNAPSHOT-NOT-THE-REPO
claim: >
  The evening close pass's launchd clock executes a FROZEN COPY at
  $HOME/Library/Application Support/macro-closepass/close_pass_host_runner.py, not
  scripts/close_pass_host_runner.py in any checkout, so merging a change to that file
  deploys NOTHING until an operator re-runs scripts/install_closepass_launchd.sh. The
  freeze is deliberate (install_closepass_launchd.sh:49 - a mid-day push to main must
  not change what the clock executes mid-session) and the same pattern
  scripts/prophet_rescue_launchd.py carries. What made it dangerous until 2026-08-18 was
  the ASYMMETRY in the run receipt: `code_sha` is the LANE worktree's git HEAD, which
  prepare_lane hard-resets to origin/main on every single run, so it reports today's main
  no matter how old the file computing it is. A bootstrap weeks stale therefore produced a
  receipt that read as perfect. Measured: PR #5862 merged as af416e4a1066 while the
  installed copy stayed byte-identical to the PRE-fix main, dated Aug 15 19:54, with
  `grep -c "_git_probe"` returning 0 on it; it was caught only by reading the plist's
  ProgramArguments by hand. The same freeze-plus-install shape applies to every
  ops/launchd/*.plist agent in the estate, none of which the repo tree can speak for.
falsifier: >
  `launchctl print gui/$(id -u)/com.macro.closepass | grep -A3 ProgramArguments` naming a
  path inside a git checkout rather than Application Support; or
  `shasum -a 256 "$HOME/Library/Application Support/macro-closepass/close_pass_host_runner.py"
  "$(git rev-parse --show-toplevel)/scripts/close_pass_host_runner.py"` agreeing
  immediately after a merge that changed the file and BEFORE the installer was re-run; or
  scripts/install_closepass_launchd.sh growing an auto-deploy path (a second cp, a
  self-update in the runner) that removes the freeze.
so_what: >
  NEVER treat a merged PR touching scripts/close_pass_host_runner.py (or any launchd
  wrapper) as deployed. The ship chain for that file has an extra terminal step: re-run
  `bash scripts/install_closepass_launchd.sh`, then verify the installed digest equals
  merged main's. Do NOT diagnose a host-clock symptom from the repo copy - read the file
  launchd actually execs. Do NOT "fix" this by making the runner self-update: that deletes
  the freeze the installer exists to provide. Since PR #5866 the disclosure is automatic
  and you should read it instead of re-deriving this: every receipt carries a `bootstrap`
  block (file_sha256 + mtime of the EXECUTING file, graded against origin/main's copy in
  the lane), the run emits `::error ... BOOTSTRAP DRIFT` naming the distance and the
  re-install command, and `python3 -m scripts.close_pass_slo_report` exits 1 on drift -
  including when a receipt's schema predates the reading checkout's, which is the
  merged-but-not-deployed detector and needs no cooperation from the stale bootstrap.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  PR #5866; PR #5862 (af416e4a1066) deploy discovery;
  scripts/install_closepass_launchd.sh:55 (the single install-time cp) and :49 (freeze
  rationale); ops/launchd/com.macro.closepass.plist ProgramArguments =
  __SUPPORT_DIR__/close_pass_host_runner.py;
  `launchctl print gui/501/com.macro.closepass` (program = /usr/bin/python3, path under
  Application Support);
  `shasum -a 256` on the installed copy vs the checkout (cde03d71de97... both sides after
  the installer re-run, af0afabbc397... for the pre-#5862 vintage);
  `python3 -m scripts.close_pass_slo_report --sessions 3 --now 2026-08-18T06:00:00Z` -> EXIT=1
  with "BOOTSTRAP DRIFT on 2026-08-14: receipt schema 'close_pass.host_run/v1' predates
  this checkout's 'close_pass.host_run/v2'"
scope:
  - macro
  - WS:BREATHING-PLATFORM
  - scripts/close_pass_host_runner.py
  - scripts/install_closepass_launchd.sh
  - scripts/close_pass_slo_report.py
  - ops/launchd/
confidence: verified
---

# launchd runs a frozen snapshot, not the repo — and the receipt's fresh field is the wrong one

## The shape of the trap

Two vintages run every evening and **only one of them moves when a PR merges**:

| | what it is | when it changes |
|---|---|---|
| `code_sha` | the LANE worktree's git HEAD | every run — `prepare_lane` hard-resets to `origin/main` |
| the bootstrap | bytes on disk under Application Support | only when an operator re-runs the installer |

The field that is **always fresh is the one that does not run**. That is why a stale
bootstrap produced a green-looking receipt for three days: nothing in it was wrong, it
just described the wrong file.

## Why the freeze stays

Arming a scheduled publisher is an operator act, and a clock whose code could change
under it mid-session is worse than one that lags. `scripts/prophet_rescue_launchd.py`
makes the same split: the wrapper is frozen plumbing, the POLICY it launches is always
`origin/main` (the runner resets its lane every run). The fix for the gap was never to
remove the freeze — it was to make the freeze's cost **visible**, which is
`DEC:BREATHING-HOST-NATIVE-CLOSE-CLOCK` unchanged plus PR #5866's disclosure.

## Generalisation worth carrying

Any `ops/launchd/*.plist` in this estate points at an installed copy, not at the repo.
Before diagnosing a host-timer symptom from the tree you are standing in, read
`ProgramArguments` and hash what it names. `[[render-commit-ancestry-is-not-what-the-render-ran]]`
is the same class one layer up: what a lane *ran* is not what its commit graph says.
