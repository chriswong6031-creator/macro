---
key: PROPHET-D5-BLOCKED-ON-CANONICAL-CANDIDATE-EPISODE-B1
claim: >
  Revalidated through Macro main 468e3f0257dac41b2e7e90771c3de87640e1c3ee on
  2026-08-23: the frozen V4 `prophet.candidate_episode/v1` exists only in
  research/architecture records; no canonical runtime implementation was found.
  The existing Entry Radar runtime episode `mastermind.live_entry_episode.v1` is not
  an alias: it is an operational, re-derivable detector lifecycle whose episode ID
  hashes (ticker, detector_id, variant, first_armed_at), whose state lives under an
  injected live state directory, and whose module explicitly says it is not the
  durable evidence store. Therefore Cell F cannot lawfully prove an episode-scoped
  D5 vertical on real canonical V4 episodes until B1 lands.
falsifier: >
  A current-main implementation owned by WS:PROPHET-US-V4-RECOVERY that publishes
  and reads `prophet.candidate_episode/v1` on the canonical V4 identity/lifecycle,
  with real production episode proof. Merely having a different object called an
  episode, a ticker/date row, a Context Vector row, a Lab/Radar detector episode,
  or a research fixture does not falsify this discovery.
so_what: >
  MAS-122 architecture can be frozen now, but its requested first runtime vertical
  must remain BLOCKED_ON_CANONICAL_CANDIDATE_EPISODE_B1. Do not mint a surrogate
  D5 episode ID, use (stamp_date,ticker) as a lifecycle, rename Entry Radar’s live
  episode, or widen MAS-122 to implement B1. Once B1 is proven, resume with the
  bounded Earnings event_workspace -> thin D5 adapter -> read-only Prophet Lab
  consumer vertical defined in the Cell F contract.
kind: architecture
verified_at: 2026-08-23
verified_by: >
  GitHub code search for prophet.candidate_episode/v1 on current main returned only
  research/architecture records; open-PR search for candidate episode B1 returned
  #6275 itself and no competing B1 carrier. Direct owner-law inspection covered
  research/prophet_v4/ARCHITECTURE_FREEZE.md,
  research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md,
  agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md, and the Entry Radar live-episode
  contract. Main movement from the Cell F semantic-census pin through
  468e3f0257dac41b2e7e90771c3de87640e1c3ee did not introduce a B1 implementation
  or a D5 owner change.
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
