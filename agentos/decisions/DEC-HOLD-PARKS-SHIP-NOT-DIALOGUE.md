---
key: HOLD-PARKS-SHIP-NOT-DIALOGUE
question: >
  Repository law described a ratified PARKED / HOLD-FOR-SOL as session-terminal. A held
  worker therefore stops everything, including its reciprocal dialogue with the holding
  authority. Is PARKED terminal for the whole session and the
  worker<->Sol child dialogue, or only for the current ship/merge attempt?
answer: >
  Only for the ship/merge attempt. HOLD-FOR-SOL remains a hard merge barrier binding every
  merge path, and every eligibility gate is unchanged: exact head pushed, worktree clean, PR
  draft, no merge-on-green, native auto-merge null, Sol authority and Sol release condition
  recorded, and every binding check concluded green. PARKED still means unmerged — not
  SHIPPED, not deployed, not live — and merge, mark ready, auto-merge, render, deploy and
  retry all remain forbidden. What changes is scope, not permission: PARKED is terminal for
  the current ship/merge attempt, and the reciprocal worker<->Sol child dialogue remains
  nonterminal. The same child, the same carrier, the same branch and the same PR resume on a
  later same-carrier Sol CONTINUE / RULING / REQUEST_REPAIR, and only an explicit same-carrier
  Sol STOP (or ACCEPTED / STOP, CLOSED / STOP) closes the child. A worker may yield its
  reasoning turn at PARKED only after it has posted one exact-carrier RESULT / HOLD-FOR-SOL
  and established a truthful continuation path — WATCH_ARMED for a real verified registration,
  otherwise WATCH_UNAVAILABLE naming the surface checked and the exact failure. "Waiting for
  Sol" is not a continuation path. The Stop wrapper may state these obligations but stays
  non-authoritative: it asserts no watcher state, infers no transport state, elects no Sol,
  creates no successor or next wave, and grants no merge or release.
rationale: >
  Five facts were collapsed into one word: the task/wave boundary, the PR merge hold, the
  reasoning-session yield, the child STOP, and program completion. Calling PARKED
  session-terminal is accurate for the ship attempt and false for the dialogue, so a correct
  reading of the law produced the exact behavior Mastermind's session-close law forbids —
  the worker goes quiet and the holding authority waits on a child that has silently
  disappeared, when "silence is never a terminal receipt" and every return owes an explicit
  CONTINUE or terminal STOP. The mirror-image failure is already on the record: PR #6608 took
  121 consecutive blocks because a lawful hold was instead told to merge, and the repair for
  that corrected the ADVICE without widening permission. This record does the same on the
  other side. Scoping the terminality is also what makes the barrier survivable: an agent that
  believes only "stop" or "merge" are available will eventually pick the forbidden one, whereas
  an agent that can lawfully yield the ship attempt and stay reachable has no incentive to
  touch the merge at all.
alternatives:
  - option: Leave the law as written and rely on workers to infer the narrow reading
    why_not: the inference already failed in production; a guard that repeats a wrong-scoped instruction teaches sessions to distrust the guard, which is worse than silence
  - option: Make PARKED fully nonterminal so the worker keeps polling the held PR
    why_not: that restores the unsatisfiable Stop loop the PARKED state was created to end, and re-poll on a held PR burns the shared GitHub quota for no possible outcome
  - option: Have the Stop hook read the carrier and report whether a continuation is armed
    why_not: the hook cannot see the transport; it would have to infer or fabricate state, and a false WATCH_ARMED is worse than no claim at all
  - option: Add a watcher/lifecycle store so continuation state is durable and machine-checked
    why_not: explicitly out of scope — it duplicates the Executive OS lifecycle authority the Skillpack forbids duplicating, and the obligation is enforceable as law without a new plane
evidence:
  - "scripts/ship_loop_hold_wrapper.py main(): pre-repair text 'This is a terminal PARKED state ... Do not re-enter the ship loop unless Sol releases the hold'"
  - "DEC:SOL-HOLD-IS-A-MERGE-BARRIER answer, pre-amendment: PARKED declared session-terminal rather than ship-attempt-terminal"
  - "CLAUDE.md and AGENTS.md carried the same session-terminal clause at four sites; all corrected in this PR"
  - "Mastermind@821e90f8f0f01dd1ed7bf11a6c548a5f410c2a32 docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md §1-§3: every reciprocal dialogue needs an explicit CONTINUE or STOP edge; silence is never a terminal receipt; WATCH_ARMED or WATCH_UNAVAILABLE is required before yielding"
  - "PR #6608: 121 consecutive blocks from the mirror-image scope error (lawful hold told to merge)"
  - "tests/test_ship_loop_hold_wrapper.py: message tests plus a five-file source-law parity test, so a future edit to one file cannot silently re-open the conflation in another"
affects:
  - scripts/ship_loop_hold_wrapper.py
  - tests/test_ship_loop_hold_wrapper.py
  - CLAUDE.md
  - AGENTS.md
  - "DEC:SOL-HOLD-IS-A-MERGE-BARRIER"
  - "DEC:SESSION-LENGTH-IS-NOT-A-COST-CONTROL"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-09-01
---

## Scope

This record refines the terminality SCOPE created by `DEC:SOL-HOLD-IS-A-MERGE-BARRIER`.
It supersedes nothing. That record's merge authority is untouched and unweakened: a
recorded hold still binds the sweeper, blanket-arming sessions and manual merges alike,
enforcement is still state rather than intent, and conditional merge authority granted for
one PR still never transfers to another.

Nothing here releases any existing hold, changes the CI-green requirement, or creates a
watcher, task, lifecycle, queue, retry or RuntimeBinding store.

## The five distinct facts

1. **task/wave boundary** — a checkpoint in a program (`DEC:SESSION-LENGTH-IS-NOT-A-COST-CONTROL`);
2. **PR merge hold** — `HOLD-FOR-SOL`, a hard merge barrier on every merge path;
3. **reasoning-session yield** — the provider turn ends; the child is not closed;
4. **child STOP** — an explicit same-carrier Sol terminal edge;
5. **program completion** — the whole mission is delivered.

`PARKED` is terminal for (2)'s current ship attempt and permits (3). It asserts nothing
about (1), (4) or (5). None of these may be inferred from any other.

## What a held worker owes before it yields

- one exact-carrier `RESULT / HOLD-FOR-SOL`, already posted;
- a truthful continuation receipt: `WATCH_ARMED` only for a real, verified registration,
  otherwise `WATCH_UNAVAILABLE` naming the checked surface and the exact failure;
- no re-polling of the held PR, and no `SHIP LOOP BLOCKED` report — waiting is not a
  qualifying blocker.

After a nonterminal Sol continuation the same bound session rereads the carrier, resumes
the same child, branch and PR, and re-arms its continuation path after its next
nonterminal return.

## Reporting honesty is unchanged

`PARKED / HOLD-FOR-SOL` is never described as merged, shipped, deployed or live. It is
not deployment evidence and not live verification. `DONE` for ordinary work remains the
merge.

## What would reopen this

Evidence that a scoped-terminal PARKED lets sessions evade the merge barrier — a held PR
merged, marked ready, armed, or retried by a session citing dialogue continuity — or a
production-proven canonical continuation path that makes the truthful-receipt obligation
machine-checkable rather than law-only.
