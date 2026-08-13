---
key: AGENTOS-CLAIMS-ARE-NOT-LIVE-ACTIVITY
question: >
  Should Agent OS track which agent is working right now — heartbeats, live session state,
  automatic death detection — as the commissioning brief (PART VII, PART XIV) asked?
answer: >
  No. No new heartbeat or session-tracking service. Agent OS claim notes are ADVISORY and
  must never be represented as authoritative live activity. The Control Pane MAY DISPLAY
  the Executive OS's existing heartbeat/job state and fleet/worktree evidence — it must not
  create a second runtime authority.
rationale: >
  Chairman ruling C2, 2026-08-12: "APPROVE WITH SEMANTIC FIX". The design was already right
  to decline the service (census §6.3 forbids it; FleetView is the product answer), but the
  ruling tightened what the surface may CLAIM about what it shows. The distinction is the
  whole point: a claim note is a line in a git file that no other session can even read
  until it merges, so it can only prevent day-scale collisions. Live truth about which
  worker is alive already exists in the Executive OS runtime, which holds real lease tokens
  and heartbeats. Displaying that is reuse; re-deriving it here would be the second runtime
  authority invariant I1 exists to prevent.
alternatives:
  - option: Build heartbeats and live session tracking in Agent OS, as the brief asked
    why_not: >
      Creates a second runtime authority over worker liveness, contradicting census §6.3 and
      duplicating control_plane/executive_runtime.py, which already holds lease tokens,
      heartbeats and LOST reconciliation.
  - option: Keep the claim but present it as live activity in the brief ("claimed by X")
    why_not: >
      The precise failure the ruling names. It reads as authoritative presence when it is an
      author's stale note, so a reader trusts it over `git worktree list`, which is the only
      thing that answers the same-hour question.
  - option: Drop the claim field entirely
    why_not: >
      It still carries real day-scale signal at near-zero cost, and it names an accountable
      author. Removing it loses that for no gain once the labelling is honest.
evidence:
  - "Chairman ruling C2, 2026-08-12"
  - "research/EXECUTIVE_OS_PHASE0_CENSUS.md §6.3 — no worker/session tracking service"
  - "Mastermind control_plane/executive_runtime.py — lease tokens, heartbeats, quota fences (the real liveness authority)"
  - "scripts/agentos.py — claim rendered as 'claim note:', with an advisory legend printed above the table"
affects: ["WS:AGENT-OS", "scripts/agentos.py", "agentos/README.md"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-12
---

## What changed in the artifact

`docs/AGENT_OS_STATE.md` previously rendered `claimed by <branch>`, which reads as presence.
It now renders `claim note: <branch>` under an explicit legend stating that claim notes are
advisory, that live worker/job state is the Executive OS runtime, and that occupancy evidence
is `git worktree list`.

## The boundary, stated for future surfaces

A Control Pane may **read and display** Executive OS heartbeat/job state. It may **not**
compute, cache as truth, or arbitrate liveness. If a future surface needs to answer "is this
worker alive?", it asks `control_plane/`; it does not grow its own answer.
