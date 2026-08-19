---
key: GOVREV-EVENT-ID-FOLDS-RETRIEVAL-CLOCK
claim: >
  Government Revenue `event_id` seeds on the collector's RETRIEVAL clock
  (engine/government_revenue/award_events.py:1408-1419 folds `known_at` into the seed;
  the comment states the intent is that A -> B -> A emit three distinct immutable
  events). Because `candidate_id` digests over {candidate_family, issuer_company_id,
  event_id} (engine/government_revenue/candidates.py:1665), a second collector pass
  over IDENTICAL upstream facts re-mints both ids. Measured 2026-08-18 across the two
  daily-collection commits 59ccb9c774c8 (04:01Z) and 93ab221b81dd (04:21Z): 26 of 56
  candidates re-minted, pairing 1:1 with their orphans on (candidate_family,
  issuer_company_id, record_id) across 16 award records. 10 of the 26 differed in
  `event_id` and NOTHING else — event_type, effective_at, source_rail,
  source_content_id and amount all byte-identical. Every one of the 26 had an amount
  identical or float-repr-identical to its predecessor (834000.5599999726 ->
  834000.56). No money moved in any of them.
falsifier: >
  Run the collector twice over a frozen upstream fixture and show `event_id` is
  stable across passes. Equivalently, read
  engine/government_revenue/award_events.py:1408-1419 and confirm `known_at` is
  absent from the seed.
so_what: >
  (1) A govrev `candidate_id` is collection-pass-scoped, NOT fact-scoped — never pin,
  cache, join on, or reconcile against one as though it identifies an award event.
  (2) When a projection folds BETWEEN two collection passes, the append-only ledger
  freezes against pass 1 while the checked-in source is pass 2, and the anti-backfill
  gate then refuses the re-mints and RAISES for the whole run
  (scripts/build_government_revenue_candidates.py:898-911, the issuance-correction
  branch — note :993-1007 carries identical error text and is dead code whenever a
  correction manifest exists, so the message alone cannot tell you which fired).
  (3) The condition is TRANSIENT, not a permanent wedge: `known_at` is a retrieval
  wall clock on BOTH sides of the comparison, so the next collection stamps forward
  and the rows append — verified by replaying the gate with a bumped `known_at`
  (no raise, appendable 26). The cost of letting it self-heal is ~24h of red main
  blocking every armed PR, plus 26 permanently ORPHANED rows in an append-only
  ledger (82 rows for 56 live candidates).
  (4) Every other disposition is structurally closed, so do not go looking: the
  historical suppression manifest is unreachable when a correction manifest exists,
  its loader additionally requires observed_known_at <= the predecessor generation
  (engine/government_revenue/candidates.py:319-324), and the correction manifest is
  sealed after activation and bijection-bound to it.
  (5) The lane publishes a projection its own suite fails —
  GOVREV_CANDIDATE_PROOF_FATAL: "0"
  (.github/workflows/government-revenue-live.yml:540).
kind: landmine
verified_at: 2026-08-18
verified_by: >
  Rebuilt candidate observations against both generations and diffed against
  data/government_revenue/candidate_ledger.jsonl; replayed
  _match_historical_suppressions directly against real inputs with the frozen clock
  2026-08-18T04:17:31.654847Z and again with a bumped known_at; the 19-file
  unrun-government-revenue step went 1 failed/352 passed -> 353 passed after
  restoring source coherence. PR #5870.
scope:
  - macro
  - data/government_revenue/
  - engine/government_revenue/award_events.py
  - engine/government_revenue/candidates.py
  - scripts/build_government_revenue_candidates.py
confidence: verified
---

**One incident, two fleet-blocking reds.** `daily.yml:651` committed
`data: daily collection 2026-08-18` twice, 20 minutes apart, with
`government-revenue-live` folding pass 1 in between (5214d0b20a17 04:15Z, +26 ledger
rows, clock frozen 04:17:31.654847Z). The same double collection moved
`data/baskets/ohlcv/B.parquet`'s digest twice in 21 minutes — see
[[DSC-BASKET-OHLCV-REWRITES-HISTORY-NIGHTLY]]. Diagnosing either red in isolation
hides that the trigger is shared.

**Diagnostic order that works.** Count BOTH directions first: 56 rows each side with
26 orphaned AND 26 unaccounted means candidates were RE-MINTED, not created. Then ask
which commit last wrote each artifact — two same-day collection commits is the tell.
Then check which files the consumer actually READS: the candidate spine reads
`award_event_snapshots.parquet`, `award_action_versions.parquet`,
`collection_receipts.jsonl` and `award_event_projection_state.json`
(engine/government_revenue/metrics.py:512,745-750), NOT the obvious
`awards|award_actions|award_snapshots.parquet`.

**Repair shape when it recurs.** Check whether the second pass touched any DERIVED
artifact. On 2026-08-18 it touched none — ledger, projection state, queue,
latest.json, dossiers and site/* all still came from the fold — so restoring the 18
source/state files to the generation the derived artifacts were computed from
restored coherence without loosening the gate that detected it. Move the whole set
(award tables, the idv and subaward rails, and data/usaspending/*) or the restore is
half-advanced.

Pack indices rebalance per PR: this job sat in `ci-pack-6` on main's 04:53Z baseline
and `ci-pack-7` on a sibling PR. Never trust a pack index from a failure report.
