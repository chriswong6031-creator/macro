---
key: PROPHET-D5-BLOCKED-ON-CANONICAL-CANDIDATE-EPISODE-B1
claim: >
  Revalidated through Macro main 5216c57afa0793e2ea8a68a20f85bd6729a26049 on
  2026-08-23: the frozen V4 `prophet.candidate_episode/v1` exists only in
  research/architecture records; no canonical runtime implementation was found.
  The existing Entry Radar runtime episode `mastermind.live_entry_episode.v1` is not
  an alias: it is an operational, re-derivable detector lifecycle whose episode ID
  hashes (ticker, detector_id, variant, first_armed_at), whose state lives under an
  injected live state directory, and whose module explicitly says it is not the
  durable evidence store. The newly landed Earnings Event Intelligence Compiler E3-A
  records also create no Prophet episode lifecycle: E3 extends canonical
  `event_workspace.v1`, E3-A is a non-promoted calibration/negative-method experiment,
  and E3-B live Q&A remains locked. Therefore Cell F cannot lawfully prove an
  episode-scoped D5 vertical on real canonical V4 episodes until B1 lands.
falsifier: >
  A current-main implementation owned by WS:PROPHET-US-V4-RECOVERY that publishes
  and reads `prophet.candidate_episode/v1` on the canonical V4 identity/lifecycle,
  with real production episode proof. Merely having a different object called an
  episode, a ticker/date row, a Context Vector row, an Earnings event workspace, a
  Lab/Radar detector episode, or a research fixture does not falsify this discovery.
so_what: >
  MAS-122 architecture can be frozen now, but its requested first runtime vertical
  must remain BLOCKED_ON_CANONICAL_CANDIDATE_EPISODE_B1. Do not mint a surrogate
  D5 episode ID, use (stamp_date,ticker) as a lifecycle, rename Entry Radar’s live
  episode, or widen MAS-122 to implement B1. Once B1 is proven, resume with the
  bounded owner-accepted canonical Earnings event_workspace -> thin D5 adapter ->
  read-only Prophet Lab consumer vertical defined in the Cell F contract.
kind: architecture
verified_at: 2026-08-23
verified_by: >
  GitHub code search for prophet.candidate_episode/v1 on current main returned only
  research/architecture records; open-PR search for candidate episode B1 returned
  #6275 itself and no competing B1 carrier. Direct owner-law inspection covered
  research/prophet_v4/ARCHITECTURE_FREEZE.md,
  research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md,
  agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md, the Entry Radar live-episode
  contract, and current-main WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER plus its E3
  architecture/landing records. Main movement from the Cell F semantic-census pin
  through 5216c57afa0793e2ea8a68a20f85bd6729a26049 did not introduce a B1
  implementation or a D5 owner change.
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
