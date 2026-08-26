---
schema: agentos.handoff.v1
workstream: "WS:CI-MERGE-CONTROL-PLANE"
session: claude/ship-loop-quiescence-20260824
model: fable
ended_because: complete
prs: [6379]
discoveries:
  - "DSC:CLAUDE-TASK-WAKES-OUTLIVE-TERMINAL-SHIP-STATES"
mission: >
  Sol commission macro#6379: make a session that reaches a lawful terminal
  ship state (PARKED, or a ratified external SHIP LOOP BLOCKED ladder exit)
  actually quiescent — one terminal report and zero new model turns while
  external state is unchanged — without weakening ordinary
  completion (Journey C internal blockers byte-unchanged).
state_before: >
  Wrapper was stateless: every Stop after PARKED re-probed GitHub and
  re-emitted the full PARKED systemMessage (incident PR #6371). Only the
  merged-head ci_failed block minted a ladder-exit key, so any wake after a
  ratified EXTERNAL escape re-blocked the escaped session (incident PR
  #6377, which also stacked a delayed background rerun timer with nothing
  refusing a second). Root cause reproduced live: run_in_background task
  completion starts a <task-notification> turn whose Stop re-enters the
  hooks; no hook surface can enumerate or cancel Claude-native tasks.
changed:
  - path: .claude/hooks/ship_loop_guard.py
    what: >
      _external_exit_key (<code>:<head>:<digest12(reason)>) threaded through
      every EXTERNAL _block site so ratified ladder exits quiesce wakes;
      merged-head ci_failed keeps its original 3-part key. New PreToolUse
      branch (_pre_tool_use/_watcher_request/_watcher_gate/
      _latched_terminal_heads/_deny_watcher): ordinary Bash fails open before
      state access; executed sleep/poll/detached/uncertain watcher forms fail
      closed; one native GitHub condition owner may reserve. Acquisition is
      linearizable under the ledger's single transaction lock. The admitted
      command receives a session-unique marker; occupancy binds to PID plus
      process-start identity, never a global command fragment. Process exit
      alone does not authorize the same HEAD/condition again; only material
      condition change can reserve a later owner after the old identity exits.
      Ledger/lock files are owned regular files in a 0700 directory, opened
      no-follow and saved through unique atomic temp files.
      Second adversarial return: heredoc bodies are structurally removed as
      data while executable headers stay classified; eval/exec/nohup/env -S/
      PowerShell transports fail closed or resolve to the one native condition
      owner; gh flag arity yields canonical repository + run/PR subject
      identity. Because Bash PreToolUse hooks decide in parallel, acquisition
      is now a two-phase transaction inside the same ledger: the hook writes a
      pending marker, and only the aggregate-allowed updated command confirms
      its exact shell PID/start identity before GitHub executes. A quota-denied
      command cannot leave a consumed phantom; a late stale command cannot
      confirm after replacement. Unsafe existing ledger state is distinct from
      genuine absence and blocks Stop / reports SessionStart without following
      planted state or lock symlinks. Third adversarial return: heredoc bodies
      consumed by bash/sh/zsh or Python stdin are classified as executable
      while cat/printf/prose bodies remain data; watcher-shaped command
      substitution and variable-executable transports fail closed. The
      classifier carries the normalized executed gh command into the canonical
      quota helper, so a hot nested watch cannot reserve. The session-ledger
      root and repo-key directories are opened one component at a time with
      dir_fd + O_NOFOLLOW, closing the ancestor-symlink traversal. Fourth
      adversarial return: the safe argv-executing wrappers nice, caffeinate,
      and timeout are structurally unwrapped before gh classification;
      otherwise unknown transports carrying literal child argv ``gh run
      watch`` fail closed while echo/printf/cat/quoted prose remain data. The
      outer OS temp root may be root-owned only when it is a sticky,
      world-writable/searchable directory; the session-root and repo-key
      children remain user-owned 0700 and no-follow.
  - path: .claude/hooks/gh_quota_guard.py
    what: >
      Extracted the existing hot-watch rule into a pure canonical helper. The
      quota hook still owns the threshold and refusal text; ship-loop admission
      consults that same helper before persisting a pending resource claim, so
      parallel hook denial cannot strand an immediate lawful retry.
  - path: scripts/ship_loop_hold_wrapper.py
    what: >
      _handle_stop: first lawful PARKED writes parked_latch
      (parked:<pr>:<head>) into the guard ledger and emits the ONE terminal
      report; an identical re-derived hold passes silently (still fully
      re-probed); any positively changed hold state clears the latch. After
      the opus red-team (F1/F2): an UNANSWERABLE probe never silences —
      local git failures inside _hold_probe read as "not a candidate"
      (delegate + clear latch; the merged-and-pruned branch falls through to
      the guard's merged-PR/CI/render/live chain), and GitHub-layer failures
      raise HoldProbeUnanswerable (delegate with latch kept; the guard files
      its own escapeable outage block).
  - path: .claude/settings.json
    what: PreToolUse:Bash now also runs ship_loop_guard.py (timeout 15).
  - path: tests/test_ship_loop_guard.py
    what: >
      Existing quiescence tests plus adversarial regressions for legal
      sleep/gh spellings, inert quoted-text negative controls, evaluated-hook
      delegation failure, concurrent ledger writers, marker/PID/start identity,
      PID reuse and sibling-session isolation, filesystem symlinks/modes, and
      standing-law parity. Second return adds executable wrapper and heredoc
      negative controls, option-arity/digest identities, real parallel
      quota+ship-hook denial/retry, command-side confirmation, unsafe-ledger
      entrypoints, five unchanged observations with zero admitted successors,
      one material-change owner, and distinct-session isolation. Third return
      adds executable-interpreter heredocs, computed command positions,
      data-only negative controls, immediate quota-denial retirement, and a
      planted session-root ancestor symlink. Fourth return adds real fake-gh
      argv executions through nice/caffeinate/timeout plus a mocked root-owned
      sticky temp-root acceptance and child-symlink refusal.
  - path: tests/test_ship_loop_hold_wrapper.py
    what: >
      Existing narrate-once/release/outage tests plus the complete PARKED →
      outage delegation → canonical last_blocker mutation → two recovered
      Stops regression; the unchanged latch stays silent while positive hold
      changes still clear it.
  - path: CLAUDE.md / AGENTS.md / .cursor/rules/ship-loop-terminal-states.mdc
    what: standing quiescence + one-watcher law matching the executable behavior.
  - path: agentos (WS wave W-QUIESCENCE, DSC record, this handoff)
    what: workstream wave + discovery + continuation record.
verified:
  - claim: adversarial review defects reproduced before repair
    command: python3.12 -m pytest focused watcher/delegation/identity/filesystem/prose selections; python3.12 -m pytest tests/test_ship_loop_hold_wrapper.py -q -k outage_blocker_mutation
    result: 31 failed / 3 passed in guard selection; 1 failed in wrapper selection; 1 additional delegated-child stdout test failed with two hook JSON values, all at the intended missing behaviors
  - claim: full guard and wrapper suites green on repaired tree
    command: python3.12 -m pytest tests/test_ship_loop_guard.py tests/test_ship_loop_hold_wrapper.py -q
    result: 353 passed, 1 skipped; 3 non-failing inherited pytest temp-cleanup warnings
  - claim: wrapper suite independently green
    command: python3.12 -m pytest tests/test_ship_loop_hold_wrapper.py -q
    result: 27 passed; 3 non-failing inherited pytest temp-cleanup warnings
  - claim: adjacent pins green (quota guard, self-mod fence, routing, sparse profile)
    command: python3.12 -m pytest tests/test_gh_quota_guard.py tests/test_self_mod_fence.py tests/test_agent_routing_control.py tests/test_sparse_worktree_profile.py -q
    result: 230 passed
  - claim: self-mod fence selftest green
    command: python3.12 scripts/check_self_mod_fence.py --selftest
    result: 16/16 PASS
  - claim: mutation receipts — removing each mechanism fails its discriminating test
    command: "sed-disable each of: _external_exit_key gate / wrapper latch match / reservation check, then pytest the matching test"
    result: 1 failed for each of the three mutations; restored clean
  - claim: real-proof replay through the REAL binaries with a REAL background primitive
    command: "scratchpad/proof: SessionStart + Stop payloads through scripts/ship_loop_hold_wrapper.py <fixture_guard.py> against a scratch git repo; PreToolUse payloads through .claude/hooks/ship_loop_guard.py; run_in_background 'sleep 75' planted pre-terminalization"
    result: >
      pending Stop → ordinary unmerged block; green Stop → PARKED narrated
      once + latch parked:9999:1c88f196; next Stop silent (exit 0, empty);
      REAL timer fired 22:45:13Z → wake-turn Stop silent, counters unmoved;
      2nd overlapping watcher DENIED (SHIP WATCHER COALESCED); post-terminal
      watcher DENIED (SHIP WATCHER REFUSED); fixture outage → silent latch
      hold; draft→false release → latch cleared + ordinary unmerged block.
  - claim: Agent OS records validate
    command: python3.12 scripts/agentos.py validate
    result: 0 errors (43 inherited warnings; review-date rollover and unrelated phantom-path records)
  - claim: second-return focused red tests reproduced every binding defect
    command: python3 -m pytest -q tests/test_ship_loop_guard.py with classifier/state/parallel-hook selections
    result: >
      executable wrappers and heredocs failed at the intended classifier
      boundary; repository/subject identities were wrong; unsafe Stop and
      SessionStart were silent; path resolution escaped the router; and the
      quota-denied hook path left an unconfirmed condition consumed.
  - claim: second-return focused repair and adjacent suites are green locally
    command: >
      python3.12 -m pytest -q tests/test_ship_loop_hold_wrapper.py
      tests/test_gh_quota_guard.py tests/test_self_mod_fence.py
      tests/test_agent_routing_control.py tests/test_sparse_worktree_profile.py
    result: 257 passed; 3 inherited non-failing pytest temp-cleanup warnings
  - claim: exact guard + wrapper regression suite is green on the second-return tree
    command: python3.12 -m pytest -q tests/test_ship_loop_guard.py tests/test_ship_loop_hold_wrapper.py --maxfail=10
    result: 381 passed, 1 skipped; 3 inherited non-failing pytest temp-cleanup warnings
  - claim: third-return defects reproduced before repair
    command: >
      python3.12 -m pytest -q tests/test_ship_loop_guard.py with executable
      stdin heredoc, computed command, immediate parallel quota retry, and
      ancestor-symlink selections
    result: >
      8 intended failures: all three interpreter heredocs and four computed
      command forms bypassed admission, and the planted ledger-root symlink was
      followed. The immediate retry test also failed until quota preflight was
      moved before reservation. Data-only and five-observation controls stayed
      green.
  - claim: exact quiescence and quota suites are green on the third-return tree
    command: >
      python3.12 -m pytest -q tests/test_ship_loop_guard.py
      tests/test_ship_loop_hold_wrapper.py tests/test_gh_quota_guard.py
      --maxfail=10
    result: 486 passed, 1 skipped; 3 inherited non-failing pytest temp-cleanup warnings
  - claim: adjacent governance suites and validators remain green
    command: >
      python3.12 -m pytest -q tests/test_self_mod_fence.py
      tests/test_agent_routing_control.py tests/test_sparse_worktree_profile.py;
      python3.12 scripts/check_self_mod_fence.py --selftest;
      python3.12 scripts/agentos.py validate
    result: >
      136 passed; self-mod 16/16 PASS; Agent OS 0 errors with 43 inherited
      unrelated warnings.
  - claim: N>=5 proof is scoped to deterministic hook outputs
    command: >
      test_five_unchanged_observations_admit_zero_successor_watchers and
      test_first_parked_stop_narrates_once_then_the_latch_silences_wakes
    result: >
      five unchanged PreToolUse observations each deny with no updatedInput;
      after one PARKED emit, five unchanged wrapper observations each return
      action=silent while all six mechanical probes run. A changed condition
      admits exactly one owner in the separate material-change regression.
      This is not a claim that repository hooks control client model-turn
      creation.
  - claim: fourth-return defects reproduced before repair
    command: >
      python3.12 -m pytest -q tests/test_ship_loop_guard.py -k
      'argv_wrappers_cannot_hide or root_owned_sticky'
    result: >
      5 intended failures: nice, caffeinate, and timeout each returned no
      watcher classification; the simulated root-owned sticky temp root was
      rejected before the secure child boundary, and the negative test proved
      that the child-symlink path had not been reached.
  - claim: exact quiescence and quota suites are green on the fourth-return tree
    command: >
      python3.12 -m pytest -q tests/test_ship_loop_guard.py
      tests/test_ship_loop_hold_wrapper.py tests/test_gh_quota_guard.py
      --maxfail=10
    result: 495 passed, 1 skipped; 3 inherited non-failing pytest temp-cleanup warnings
  - claim: fourth-return adjacent governance remains green
    command: >
      python3.12 -m pytest -q tests/test_self_mod_fence.py
      tests/test_agent_routing_control.py tests/test_sparse_worktree_profile.py;
      python3.12 scripts/check_self_mod_fence.py --selftest
    result: 136 passed; self-mod 16/16 PASS
  - claim: same-carrier current-main reconciliation preserves the full quiescence contract
    command: >
      merge origin/main@39b30673a2015cb16dccab7d99ab77df1e6b2971 into
      claude/ship-loop-quiescence-20260824; resolve the sole conflict in
      WS-CI-MERGE-CONTROL-PLANE by retaining both current P0R/P1/P2/P2R
      receipts and W-QUIESCENCE; git diff --check
    result: clean reconciliation; no unresolved paths and no whitespace errors
  - claim: exact current-main quiescence and adjacent governance suites are green
    command: >
      python3.12 -m pytest -q tests/test_ship_loop_guard.py
      tests/test_ship_loop_hold_wrapper.py tests/test_gh_quota_guard.py
      --maxfail=10; python3.12 -m pytest -q tests/test_self_mod_fence.py
      tests/test_agent_routing_control.py tests/test_sparse_worktree_profile.py;
      python3.12 scripts/check_self_mod_fence.py --selftest;
      python3.12 scripts/agentos.py validate
    result: >
      495 passed, 1 skipped; 136 passed; self-mod 16/16 PASS; Agent OS
      0 errors with 43 inherited warnings
unverified:
  - claim: hosted CI green on the exact PR head
    what_would_verify: ci.yml + fences.yml runs on the PR head after push (watched to conclusion before parking)
unresolved:
  - >
    tests/test_ship_loop_hold_wrapper.py remains waived-unwired in CI
    (config/unrun_test_waivers.yml) — inherited state, deliberately not
    absorbed here per the commission's no-unrelated-cleanup rule; wiring it
    into the self-mod fence job's pytest line is a one-line follow-up.
  - >
    Claude-platform lifecycle behavior outside repository control: the wake
    TURN itself still occurs (the harness re-invokes the model on task
    completion) and the model may still print prose on that turn; the repair
    guarantees the hooks stay silent and refuse new watchers, and standing
    law now instructs sessions to end wake turns without re-reporting.
next_actions:
  - >
    Push the reconciled exact head to the existing PR #6381 carrier, return it
    from HOLD-FOR-SOL, and require authoritative ci.yml + fences.yml proof.
  - On exact-head acceptance, squash-merge without absorbing the separately
    waived hold-wrapper CI wiring into this carrier.
  - After merge, flip W-QUIESCENCE to done with the merge sha.
do_not_redo:
  - Do not attempt hook-side cancellation/enumeration of Claude-native
    background tasks — no such surface exists (DSC:CLAUDE-TASK-WAKES-OUTLIVE-TERMINAL-SHIP-STATES).
  - Do not give internal codes (unmerged, ci_failed_unmerged, guard_error)
    ladder-exit keys — evaluated and excluded on purpose (Journey C).
  - Do not re-key the merged-head ci_failed exit (3-part form is compatible
    with already-ratified session ledgers).
danger_areas:
  - Hook stdout must stay a single JSON value; a stray print ahead of a block
    silently defeats the block (guard audit-emit comment).
  - The wrapper's silent pass MUST keep re-probing GitHub; skipping the probe
    on latch-hit would suppress a Sol release (tested by
    test_first_parked_stop_narrates_once_then_the_latch_silences_wakes's
    open_pull==2 assertion).
  - >
    Never reintroduce an outage-silent path in _handle_stop — an unanswerable
    probe cannot distinguish "hold in force" from "hold released", so silence
    there is a free exit for ordinary work (red-team F1/F2; opus review
    2026-08-24, session transcript).
  - Ordinary non-watcher Bash must stay fail-open before delegation/state, but
    once classified watcher-shaped, unanswerable admission must fail closed.
  - >
    PreToolUse allow is not aggregate permission: keep the pending-marker +
    command-side confirmation seam. Never let an unconfirmed parallel-hook
    claim consume a condition, and never start GitHub before the exact marker,
    PID, and process-start identity are committed under the shared ledger lock.
    The canonical quota helper must run before the pending write; do not copy
    its interval threshold into ship_loop_guard.py or reintroduce a grace-window
    retry for a command another configured hook deterministically denies.
  - >
    Do not let ladder_exits refuse watcher creation (red-team F4 — permanent
    false-DENY of a resumed transient-escape session), and do not free the
    watcher slot on head moves or clock deadlines (Sol's 2026-08-25 blocker —
    the old task may still be alive); require the reserving session's marker,
    PID, and start identity, refuse unknown liveness, and never treat process
    absence as authority for an unchanged successor.
  - >
    Run every mutation receipt against COMMITTED code — `git checkout --` as
    the mutation restore silently reverts any uncommitted repair (this
    session lost and re-applied the acquisition rewrite exactly that way).
---

Root cause, one line: terminal ship states were derived statelessly per Stop
while background wakes are a normal part of the runtime, so every leftover
timer re-ran the full narration/block machinery. The repair latches the exact
frozen state in the existing per-session ledger and refuses redundant watcher
creation — nothing else changed.
