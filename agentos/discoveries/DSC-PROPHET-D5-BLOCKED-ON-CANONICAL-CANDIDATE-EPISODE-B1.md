---
key: PROPHET-D5-BLOCKED-ON-CANONICAL-CANDIDATE-EPISODE-B1
claim: >
  At Macro main 9f373fd9553603192f495260b2100c16c177023b, the frozen V4
  `prophet.candidate_episode/v1` exists only in research/architecture records; no
  canonical runtime implementation was found. The existing Entry Radar runtime
  episode `mastermind.live_entry_episode.v1` is not an alias: it is an operational,
  re-derivable detector lifecycle whose episode ID hashes
  (ticker, detector_id, variant, first_armed_at), whose state lives under an
  injected live state directory, and whose module explicitly says it is not the
  durable evidence store. Therefore Cell F cannot lawfully prove an
  episode-scoped D5 vertical on real canonical V4 episodes until B1 lands.
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
verified_at: 2026-08-22
verified_by: >
  Current-main GitHub code search for candidate_episode/v1 and episode_id plus
  direct inspection of research/prophet_v4/ARCHITECTURE_FREEZE.md,
  agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md, and
  engine/entry_radar/live_ledger.py at/through main 9f373fd9553603192f495260b2100c16c177023b.
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
