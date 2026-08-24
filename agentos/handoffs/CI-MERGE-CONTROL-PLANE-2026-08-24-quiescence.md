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
  actually quiescent — one terminal report, at most one ship-state watcher,
  zero repeated wake narration/blocking — without weakening ordinary
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
      _latched_terminal_heads/_deny_watcher): one live delayed-wake
      reservation per session ledger; fail-open, kills nothing; non-watcher
      Bash returns before delegation. After the opus red-team: reservations
      expire at the NOMINAL FIRE TIME, no slack, so a fired watcher's
      successor is admitted (F3); only the parked_latch refuses creation —
      ladder exits do not, having no clearing path (F4); sleep parsing is
      suffix-aware s/m/h/d (F5); _save uses a per-PID temp name against
      concurrent PreToolUse writers (F6).
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
    what: 10 new tests — external exit keys, wake quiescence, new-head/
      changed-reason regating, internal-code negative control, watcher
      classification/coalescing/terminal-refusal/fail-open, settings pin.
  - path: tests/test_ship_loop_hold_wrapper.py
    what: 6 new tests — narrate-once latch, outage-holds-latch, outage+drift
      delegates, release clears latch, red-after-park sol/* block, ordinary
      no-latch negative control.
  - path: CLAUDE.md / AGENTS.md / .cursor/rules/ship-loop-terminal-states.mdc
    what: standing quiescence + one-watcher law matching the executable behavior.
  - path: agentos (WS wave W-QUIESCENCE, DSC record, this handoff)
    what: workstream wave + discovery + continuation record.
verified:
  - claim: full guard suite green (one pre-existing mtime flake passes 3/3 standalone)
    command: python3 -m pytest tests/test_ship_loop_guard.py -q
    result: 264 passed, 1 skipped (flake test_the_sweep_removes_a_zero_byte_lock_this_guard_orphaned 3/3 standalone)
  - claim: wrapper suite green
    command: python3 -m pytest tests/test_ship_loop_hold_wrapper.py -q
    result: 24 passed
  - claim: adjacent pins green (quota guard, self-mod fence, routing, sparse profile)
    command: python3 -m pytest tests/test_gh_quota_guard.py tests/test_self_mod_fence.py tests/test_agent_routing_control.py tests/test_sparse_worktree_profile.py -q
    result: 230 passed
  - claim: self-mod fence selftest green
    command: python3 scripts/check_self_mod_fence.py --selftest
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
    command: python3 scripts/agentos.py validate
    result: 0 errors (33 pre-existing warnings)
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
  - Sol review of the held PR; on acceptance, squash-merge and (optionally
    same PR) wire test_ship_loop_hold_wrapper.py into the fence job pytest line.
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
  - _watcher_gate must stay fail-open; a crash-deny would block ordinary Bash
    fleet-wide via settings.json PreToolUse wiring.
  - Do not add slack to the watcher reservation expiry and do not let
    ladder_exits refuse watcher creation — both were shipped and reverted on
    red-team findings F3/F4 (permanent false-DENY of the lawful successor
    watcher / of a resumed transient-escape session).
---

Root cause, one line: terminal ship states were derived statelessly per Stop
while background wakes are a normal part of the runtime, so every leftover
timer re-ran the full narration/block machinery. The repair latches the exact
frozen state in the existing per-session ledger and refuses redundant watcher
creation — nothing else changed.
