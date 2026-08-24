---
schema: agentos.discovery.v1
key: CLAUDE-TASK-WAKES-OUTLIVE-TERMINAL-SHIP-STATES
claim: >
  A Claude Code background task (run_in_background Bash timer) survives every
  terminal ship-loop verdict and, on completion, starts a NEW model turn via a
  <task-notification> whose Stop re-enters the ship-loop hooks — and the
  platform exposes no mechanism for a repository hook to enumerate, identify,
  or cancel Claude-native background tasks, so watcher lifetime is controllable
  only at creation (PreToolUse) and at wake (Stop).
falsifier: >
  Run `sleep 45 && echo wake` as a run_in_background Bash in any Claude Code
  session and watch the transcript: if completion no longer starts a
  <task-notification> turn, or if `grep -r "task" .claude/settings.json` plus
  the hooks docs show a task-enumeration/cancellation hook surface, this is
  stale.
so_what: >
  Never design ship-loop quiescence around "cancel the watcher" — it is not
  implementable from a hook. Quiesce by (1) refusing duplicate/pointless
  watcher creation at PreToolUse and (2) latching terminal states in the
  per-session ledger so the wake turn's Stop passes silently
  (parked_latch + external ladder_exits keys, PR claude/ship-loop-quiescence-20260824).
  Also: stop_hook_active is False on task-notification turns, so re-entrancy
  must be proven from the guard's own ledger, never the payload flag alone.
kind: runtime
verified_at: 2026-08-24
verified_by: >
  Live reproduction 2026-08-24 in the Sol #6379 commission session (45s
  run_in_background timer completed → <task-notification> turn observed);
  incident witnesses PR #6371 (repeated PARKED narration) and PR #6377
  (session visibly Holding with 1 running task after handoff).
scope:
  - macro
  - .claude/hooks/ship_loop_guard.py
  - scripts/ship_loop_hold_wrapper.py
confidence: verified
---

The 2026-08-04 `stop_hook_active` reset class (guard module docstring) was the
first sighting of the same runtime fact from the other side: a background task
notification starts a turn the harness did not consider hook-initiated. This
record generalizes it: background waits are part of the real execution
environment, they outlive terminal verdicts, and only creation-gating plus
wake-latching — both deterministic, both inside the existing per-session
ship ledger — can make a terminal state actually quiescent.
