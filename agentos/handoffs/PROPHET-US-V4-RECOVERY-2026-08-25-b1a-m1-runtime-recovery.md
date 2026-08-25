---
workstream: WS:PROPHET-US-V4-RECOVERY
session: b1a-m1-runtime-recovery
model: fable
ended_because: blocked

mission: >
  B1-A: recover the governed M1 publisher runtime if recoverable, or ratify a
  truthful replacement pin if not; then commission merged PR #6363 (M1 private
  publisher Git hardening) onto the governed runtime and obtain natural
  scheduler proof. Explicitly NOT the Chairman-only visibility flip.

state_before: >
  #6363 merged 2026-08-24T14:36:44Z as deb53e6f389b227a9fe47709922b542c3c3fd9b3
  with no install and no natural-cycle claim. A post-merge comment on that PR
  reported the M1 publisher paths absent and declared
  `EXTERNAL_CAPABILITY_BLOCKED: governed M1 engine checkout
  /Users/chriswong/flow-ops-wt and its unrecoverable dirty pin state are
  unavailable`, asserting that operator restoration or a ratified replacement-pin
  migration was the only lawful next step. The accepted Day-6 record
  (DEC:B1-MACRO-PRIVATE-CUTOVER) instead recorded the M1 pin as a deliberate
  operator matter and NOT a flip blocker.

changed:
  - {path: "M1 ~/macro-publisher-runtime", what: "CREATED — clean governed launcher clone (sparse cone ops/launchd + scripts, blobless, depth 1) at fa683411fd92407a9288aa0a4ebbd558da97667d, remote git@github.com:mastermindx-market-intelligence/macro.git, 0 dirty, 59M. Local config matches macro_machine_git._CANONICAL_LOCAL_CONFIG exactly (13/13 keys, no extras); worktree config matches _CANONICAL_WORKTREE_CONFIG."}
  - {path: "M1 ~/Library/LaunchAgents/com.macro.theme-options-witness.plist", what: "REPLACED with the merged #6363 plist (sha256 3ef719ae14aa515a051e83a581c2163db0857571242e65280f9b5fa5d069e7af, blob 3da71dbe144da25d36c65bee459e7ac6d2b0ec4e). Backup: .b1a-pre-6363-20260825T205200Z. Unloaded + reloaded; launchctl print confirms the hardened argument vector."}
  - {path: "M1 ~/Library/LaunchAgents/com.macro.indexgexhistory.plist", what: "REPLACED with the merged #6363 plist (sha256 654d3f3c020b82809249b6244e7aefc90c86aa1f86322e782d678d0913ac7975, blob b3fc77eb3b134557b96355a6b1b6959eb9ce8061). Backup: .b1a-pre-6363-20260825T205200Z. Unloaded + reloaded."}
  - {path: "agentos/decisions/DEC-B1A-M1-RUNTIME-RECOVERED-NO-SUPERSESSION.md", what: "NEW — adjudicates the authority conflict: runtime RECOVERED, Day-6 stands unamended, replacement-pin supersession NOT triggered and forbidden."}
  - {path: "agentos/discoveries/DSC-M1-PUBLISHER-RUNTIME-IS-HOST-LOCAL-AND-DELIBERATELY-PINNED.md", what: "NEW — the runtime is host-local to the M1 and its dirty pin is load-bearing by design; never normalize it."}

verified:
  - {claim: "The governed runtime was NOT lost. /Users/chriswong/flow-ops-wt is intact on the M1 (Mac13,1, Tailscale 100.117.58.62) at exactly the pin the Day-6 record named.", command: "ssh m1 read-only: git rev-parse HEAD = a5f79c83fe0b26e3fbd798ffc4630fc957d09a60 (detached, #2760, 2026-07-17); 395 tracked modified + 20 untracked; status --porcelain sha256 560e8e929c5b768230680966e43001daae7d44a90137c1710627ed0c28e62834; diff HEAD sha256 5ba54da65e39ca975d449431ead3771e2cda49534595bcdac40f453e487adeca; stat dev=16777234 inode=280284433"}
  - {claim: "The PR-comment 'unrecoverable' verdict was scoped to the wrong host and is falsified. It names its own scope in its first clause — 'On the commissioning Mac' (the M2). The M1 was never probed and answered on first attempt.", command: "ssh m1 'ls -lad /Users/chriswong/flow-ops-wt' → present; the same probe on the M2 returns No such file or directory"}
  - {claim: "No newer Sol/Agent-OS ruling superseded the Day-6 record; the durable plane still carries the M1 pin advance as a residual chore, never a blocker.", command: "grep -rl flow-ops-wt agentos/ (6 files, newest 2026-08-23); WS-PROPHET-US-V4-RECOVERY.md:307 'M1 flow-ops-wt pin advance'; no decision/handoff after 2026-08-21 amends DEC:B1-MACRO-PRIVATE-CUTOVER"}
  - {claim: "The ~69 GiB TerraMaster M1 recovery set cannot establish flow-ops-wt identity — it is entirely Chrome code-sign clones.", command: "find /Volumes/Mastermind/Mastermind/scratch/runner-fleet -maxdepth 3 → only m1-recovery-20260824/chrome-code-sign-clones-inactive/code_sign_clone.*; du -sh = 69G; find /Volumes/Mastermind -maxdepth 4 -iname '*flow-ops*' → zero hits"}
  - {claim: "#6363's real scope differs from the commissioning brief: it touches the indexgexhistory and theme-options-witness lanes, NOT a 'prophet collector', and its files live at ops/launchd/* and scripts/macro_machine_git.py.", command: "git show --stat deb53e6f → ops/launchd/{com.macro.indexgexhistory.plist,com.macro.theme-options-witness.plist,run_index_gex_history.sh,run_theme_options_witness.sh}, scripts/macro_machine_git.py, tests/test_macro_anon_dependency_guard.py"}
  - {claim: "The pre-#6363 witness lane was pushing to the Chairman's personal account and surviving only on a silent GitHub repo-move redirect — the exact failure #6363 closes, and one that breaks the moment the repo goes private.", command: "M1 /tmp/theme_options_witness.stderr.log (2026-08-24 17:20): 'remote: This repository moved. Please use the new location: https://github.com/mastermindx-market-intelligence/macro.git / To https://github.com/chriswong6031-creator/macro.git / 86556ac1..6af1ccd1 main -> main'"}
  - {claim: "Machine-identity auth works, is key-selected, and fails CLOSED without the key.", command: "MACRO_PUBLISH_GIT_SSH_KEY=~/.ssh/macro_dashboard_deploy python3 macro_machine_git.py ls-remote <canonical> refs/heads/main → rc=0 + SHA; same without the env var → rc=78 'MACRO_PUBLISH_GIT_SSH_KEY is required'"}
  - {claim: "The wrong-account remote is refused by construction.", command: "macro_machine_git.py ls-remote https://github.com/chriswong6031-creator/macro.git → 'machine Git refuses a non-canonical repository URL'"}
  - {claim: "The publishing identity is a repo-scoped WRITE deploy key, not the Chairman's account.", command: "ssh-keygen -y -f ~/.ssh/macro_dashboard_deploy = ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIGsg0RaONMmPx/E… ; gh api repos/mastermindx-market-intelligence/macro/keys → id=154241382 read_only=false title=key1 with the identical public key. The other three registered keys are read_only=true."}
  - {claim: "No fallback to a user SSH agent, credential helper, global config, URL rewrite, or hooks is possible.", command: "scripts/macro_machine_git.py _git_environment: BatchMode=yes, IdentitiesOnly=yes, IdentityAgent=none, GIT_CONFIG_GLOBAL=/dev/null, GIT_CONFIG_SYSTEM=/dev/null, GIT_CONFIG_NOSYSTEM=1, GIT_TERMINAL_PROMPT=0, core.hooksPath=/dev/null"}
  - {claim: "Both plists are installed, valid, loaded, and carry the hardened argument vector.", command: "plutil -lint OK on both; installed sha256 equals the runtime source sha256 for both; launchctl list shows both at status 0; launchctl print gui/501/com.macro.theme-options-witness and …indexgexhistory show run_with_env.sh from macro-publisher-runtime + MACRO_PUBLISH_GIT_SSH_KEY + PYTHONPATH=flow-ops-wt + the runtime's runner script"}
  - {claim: "Commissioning did NOT mutate the recovered runtime.", command: "post-install re-capture: head a5f79c83…, 395 modified, 20 untracked, status sha256 560e8e92… and diff sha256 5ba54da6… — byte-identical to the pre-install forensic capture"}
  - {claim: "The push-repo clone the lanes perform at run time will satisfy the strict config validator.", command: "~/.ssh = drwx------ uid 501; key -rw------- nlink=1; the identical clone shape produced local config matching all 13 _CANONICAL_LOCAL_CONFIG keys and both _CANONICAL_WORKTREE_CONFIG keys; the clone contract forbids --no-tags so no tagopt key appears"}

unverified:
  - claim: "Natural production proof for the theme-options-witness lane."
    what_would_verify: >
      NOT YET OBSERVED at handoff-write. The lane's scheduler is
      StartCalendarInterval Weekday=1..5 Hour=17 Minute=15 (America/Vancouver);
      the first natural post-install execution is 2026-08-25 17:15 PDT, and the
      install completed 13:52 PDT the same day. Verify from the M1 that
      /tmp/theme_options_witness.{stdout,stderr}.log show a run whose launcher
      path is ~/macro-publisher-runtime/ops/launchd/run_theme_options_witness.sh,
      that ~/witness-push-repo-private was created by the lane itself with
      remote git@github.com:mastermindx-market-intelligence/macro.git, that the
      push carries NO 'This repository moved' redirect notice, and that
      flow-ops-wt's status/diff digests are unchanged. No synthetic invocation
      was substituted, and the lane was NOT hand-run to manufacture a receipt.
  - claim: "Natural production proof for the index/GEX history lane."
    what_would_verify: >
      Its scheduler is StartCalendarInterval Weekday=0 Hour=20 (Sundays, America/Vancouver),
      so its first natural post-install execution is 2026-08-30 20:00 PDT. No synthetic
      invocation was substituted. Verify then: /tmp/index_gex_history.{stdout,stderr}.log
      show the run_with_env.sh path under macro-publisher-runtime, the push tail using
      ~/indexgex-push-repo-private against the canonical SSH remote, and the five
      data/index_gex_history artifacts landing on canonical main.

unresolved:
  - "Chairman-only: the macro PUBLIC→PRIVATE visibility flip. Untouched here, as commissioned."
  - "Post-flip cutover steps from Day-6 remain open: Pages delete, jsDelivr purge, post-flip proof matrix, §8b re-review."
  - >
    NEW GATE FOUND (report-only, NOT fixed here — outside B1-A's commissioned scope):
    installing #6363 closes the wrong-account path for the TWO lanes it covers, but a
    LIVE anonymous consumer remains on the M1. `~/macro-live` fetches
    `https://github.com/chriswong6031-creator/macro.git` anonymously with no auth
    config, surviving only on GitHub's repo-move redirect, and it is CURRENT:
    FETCH_HEAD mtime 2026-08-25T13:48:31 PDT, HEAD f0ccbd37 = canonical main that
    minute. Loaded agent `com.macro.live-breadth` rides it. This WILL hard-fail at
    the visibility flip. Day-6's Wave A/B migration covered the VPS `/opt/macro` and
    the Mastermind vendor symlink; it did not enumerate M1-local anonymous consumers.
    Treat this as a blocking input to MACRO-PRIVATE-CUTOVER READY.
  - >
    Dormant, lower priority: `~/hub-ops-wt` is on
    `git@github.com:chriswong6031-creator/macro.git` and is referenced by three loaded
    agents (`com.mastermind.optionshub`, `com.mastermind.levelsseal`,
    `com.mastermind.levelsgrader`), but its FETCH_HEAD mtime is 2026-08-02T20:22:55 —
    three weeks stale, so it is not actively pulling. `~/fund-engine-wt` is likewise on
    a wrong-account HTTPS remote with no loaded agent referencing it. Enumerate and
    migrate these under the cutover packet, not here.
  - "The legacy push repos ~/indexgex-push-repo and ~/witness-push-repo still point at https://github.com/chriswong6031-creator/macro and are now ORPHANED by the install. They are disposable and self-recreating; deleting them is an operator hygiene call, not a B1-A act."
  - "PR #6363's shipped plists fail strict XML parsing (stdlib plistlib) because the embedded documentation comments contain `--`, which XML forbids inside comments. macOS CFPropertyList/plutil accept them, so launchd is unaffected and `plutil -lint` is green. Cosmetic-but-real portability wart; not a blocker."

next_actions:
  - >
    Bank the theme-options-witness natural receipt from the 2026-08-25 17:15 PDT
    execution (or, if that cycle is missed, the next weekday 17:15). Do NOT hand-run
    the lane and present the output as production proof.
  - "On 2026-08-30 20:00 PDT bank the index/GEX natural receipt the same way; do NOT dispatch it by hand."
  - "Only after both lane receipts exist should the private-cutover packet return to Sol; the visibility flip stays the Chairman's isolated act."

do_not_redo:
  - "Do NOT re-diagnose the M1 runtime as lost from an absent path on whatever Mac a session occupies. Probe the M1 over Tailscale (`ssh m1`) FIRST. See DSC:M1-PUBLISHER-RUNTIME-IS-HOST-LOCAL-AND-DELIBERATELY-PINNED."
  - "Do NOT advance, reset, clean, or reconstruct /Users/chriswong/flow-ops-wt. Its detached dirty pin at a5f79c83 is the deliberate engine that the merged #6363 lanes consume via PYTHONPATH/WorkingDirectory/.env. Normalizing it destroys the governed runtime."
  - "Do NOT execute a replacement-pin migration for this runtime. It was recovered; supersession is not triggered. See DEC:B1A-M1-RUNTIME-RECOVERED-NO-SUPERSESSION."
  - "Do NOT treat the 2026-08-24 PR #6363 comment as a Sol ruling. It is a session terminal note scoped to the commissioning Mac."
  - "Do NOT hand-run the publisher lanes and present the output as production proof; both lanes must be observed on their own schedulers."

danger_areas:
  - "flow-ops-wt's gitdir is a linked worktree under ~/Documents, which macOS TCC denies to launchd agents. That is WHY the lanes push from a separate $HOME push repo. Never 'simplify' the lane to git directly inside flow-ops-wt — it will fail under launchd only, not when you test it by hand."
  - "The old lanes' pushes to chriswong6031-creator/macro succeeded only via GitHub's repo-move redirect. Any lane still on that remote will hard-fail at the private flip, silently until then."
  - "Rollback is `cp <plist>.b1a-pre-6363-20260825T205200Z <plist>` then unload/load — but rolling back re-arms the wrong-account push path, so roll back only for a genuine lane failure, never for tidiness."
  - "macro_machine_git.py fails closed on ANY unknown repository-local config key. A future session that runs a stray `git config` inside a push repo will wedge that lane until the repo is deleted and re-cloned."

discoveries:
  - "DSC:M1-PUBLISHER-RUNTIME-IS-HOST-LOCAL-AND-DELIBERATELY-PINNED"
decisions:
  - "DEC:B1A-M1-RUNTIME-RECOVERED-NO-SUPERSESSION"
---

# Handoff — B1-A M1 runtime recovery + #6363 commissioning · 2026-08-25

> **State at merge:** recovery and commissioning are DONE and receipted. The one
> remaining gate is an external scheduler clock that cannot be accelerated: the
> theme-options-witness lane fires Mon–Fri 17:15 America/Vancouver and the
> index/GEX lane fires Sundays 20:00. `ended_because: blocked` names exactly that
> clock — not a defect, not a missing capability, and not a reason for another
> session to re-open the recovery question. The natural receipts are banked in a
> follow-up records PR by this same session; do NOT hand-run either lane.


The governed M1 publisher runtime was **recovered, not replaced**. It was never
lost: `/Users/chriswong/flow-ops-wt` sits on the M1 exactly where the Day-6
record said it did, at exactly the pin the Day-6 record named, with its dirty
state intact and cryptographically fixed by two digests captured before any
mutation and re-verified byte-identical afterwards.

The competing claim — that the checkout was unrecoverable and that installation,
natural proof, and cutover were therefore blocked — came from a PR comment whose
own first clause scopes it to "the commissioning Mac". That machine is the M2.
The runtime is host-local to the M1. An absent path on one host was generalized
into a loss verdict, and that verdict would, if honored, have authorized exactly
the destructive act this mission forbids: superseding a live governed runtime
with a replacement pin.

Commissioning #6363 required no replacement and no change to the pinned engine.
The merged design deliberately separates a **current, disposable launcher** from
a **deliberately pinned engine**, so the install was purely additive: one clean
governed clone, two plist swaps, both backed up. The dirty pin is not damage to
be repaired — it is load-bearing state the merged contract depends on.
