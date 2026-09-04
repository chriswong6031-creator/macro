---
key: PROPHET-D5-BLOCKED-ON-CANONICAL-CANDIDATE-EPISODE-B1
claim: >
  FALSIFIED / CLEARED 2026-08-28. The canonical B1 runtime and real production
  episode proof now exist on main. Natural scheduled run 33147282433 published the
  validated HEAD-selected `prophet.candidate_episode/v1` generation and pushed it as
  commit a8ee11ba0e4815e63db1b612da52e70eb21e828d. D5 no longer needs to reconstruct
  or surrogate episode identity and may execute the bounded owner-accepted vertical.
falsifier: >
  A current-main implementation owned by WS:PROPHET-US-V4-RECOVERY that publishes
  and reads `prophet.candidate_episode/v1` on the canonical V4 identity/lifecycle,
  with real production episode proof. Merely having a different object called an
  episode, a ticker/date row, a Context Vector row, an Earnings event workspace, a
  Lab/Radar detector episode, or a research fixture does not falsify this discovery.
so_what: >
  Resume the bounded canonical Earnings event_workspace -> thin D5 adapter ->
  read-only Prophet Lab consumer vertical defined in the Cell F contract. Continue
  to forbid a surrogate D5 episode ID, (stamp_date,ticker) lifecycle, or Entry Radar alias.
kind: architecture
verified_at: 2026-08-28
verified_by: >
  Command `gh run view 33147282433 --job 98870036658 --log` proved the natural
  descendant run at head 24ccea3fe482; command `git show
  a8ee11ba0e4815e63db1b612da52e70eb21e828d` proved the pushed main commit;
  load_candidate_episode_store_snapshot plus load_all_candidates over that committed
  generation returned 467 episodes and zero duplicate episode, event, or source identities.
scope:
  - macro
  - research/prophet_v4
  - engine/entry_radar/live_ledger.py
  - future prophet.intelligence_vector/v1
confidence: verified
---

The blocker is a no-duplicate-lifecycle safeguard, not a preference for a particular
serialization. It clears only when the canonical B1 object exists and is production-
proven enough for Cell F to consume without reconstructing identity itself.

## Status note — 2026-08-26: falsifier HALF met, discovery still STANDS

B1 merged as `878930b3b2f9849e120391fa461ed528f32d2e3c` (PR #6405) at 2026-08-26T00:13:07Z, so
the first half of the falsifier — "a current-main implementation owned by
WS:PROPHET-US-V4-RECOVERY that publishes and reads `prophet.candidate_episode/v1` on the
canonical V4 identity/lifecycle" — is now satisfied.

The second half — "**with real production episode proof**" — is not. `data/us_prophet_rank/episodes/`
does not exist on `main`; B1's writer is schedule-only (`.github/workflows/daily.yml:6443-6444`)
and has not yet executed. B1's own status is MERGED / BUILT_NOT_PROVEN.

This discovery therefore **still stands** and D5 runtime remains blocked. It clears on B1
natural-production acceptance from the first qualifying ordinary scheduled `daily.yml` run whose
HEAD contains the B1 merge — not by dispatch, rerun, replay, or report mode. A run whose head
predates the merge does not qualify even though the job checks out `ref: main`: the workflow
definition is pinned to the triggering commit, so a newly merged workflow *step* cannot appear
in an already-started run (verified against run `32908543584`).

The architecture half of the blocker is now reconciled: see
`research/prophet_v4/flagship_cells/CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md`.

## Status note — 2026-08-28: falsifier fully met, discovery cleared

The first qualifying ordinary scheduled descendant was run `33147282433`, triggered at
`24ccea3fe482ab97c415db387f272b34c4852ed3`. It contains the B1 repair merge and
naturally executed the schedule-only writer. B1 commit
`a8ee11ba0e4815e63db1b612da52e70eb21e828d` pushed generation
`peg:c025bb50c45f319f989a4848249b8a85b65354143e3262f2ad09d07841311b08` to main on
attempt 1. The shared generation validator and sole canonical reader returned 467 lawful
SEC/ISS episodes from 915 immutable events and 5,435 typed suppressions with zero
duplicate episode, event, or source identities. No separate private B1 reader exists.

Unrelated `standout_audit_us` reached its 40-minute timeout before `us_prophet_ledgers`
began. The workflow continued, B1 subsequently succeeded and pushed its durable
generation, while the final run conclusion remained `cancelled` solely because of that
earlier unrelated timeout. This mirrors the
existing evidence-dimension law: the unrelated cancellation is recorded honestly, while
the already-pushed exact production packet remains the B1 acceptance evidence. D5's B1
dependency is therefore cleared; every other D5 boundary remains binding.
