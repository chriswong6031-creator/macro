---
key: GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD
question: >
  `_event_id` folds the collector's retrieval wall clock `known_at`
  (engine/government_revenue/award_events.py:1400-1419), and `candidate_id` folds
  `event_id` (engine/government_revenue/candidates.py:1665), so a re-derivation re-mints
  identity over unchanged upstream facts — 26 candidates on 2026-08-18, 10 of them with
  `event_type`, `effective_at`, `source_rail`, `source_content_id` and amount all
  byte-identical to their predecessor. Should the seed be changed to make identity a
  function of the evidence alone, and if so how, while keeping the property the fold
  exists to protect?
answer: >
  NO. Keep the `known_at` fold exactly as it is. Change nothing in `_event_id`,
  `_state_hash`, `_consolidate`, or `candidate_id`. The premise that the collector
  re-mints identity over content it has already seen is FALSE — measured, the
  re-observation dedupe works and re-stamps nothing. The 26 re-mints were caused by an
  append-only LOST UPDATE in the push path, and the durable fix belongs there:
  `git pull --rebase --autostash -X theirs origin main`
  (.github/workflows/daily.yml:702, :751, :772, :1313, :1786) resolves the conflicting
  tail hunk of an append-only artifact in favour of the run being replayed, discarding
  rows already on main instead of unioning them. Fixing the seed would re-mint every
  identity in a receipt-bound ledger (a full re-baseline) and would leave the actual
  race untouched.
rationale: >
  Three measurements decide this, and they point away from the seed.

  (1) The collector is ALREADY idempotent across passes over content it can see.
  `_append_event_versions` skips a re-observation whose state hash is unchanged
  (collectors/usaspending_awards.py:1915-1916). Between the two 2026-08-18 passes,
  `award_event_snapshots.parquet` held 194 of 210 rows byte-identical and
  `award_action_versions.parquet` held 35,239 of 35,257. The only rows that moved are the
  16 + 18 that pass 1 had appended and pass 2 never saw, and `event_state_sha256` is
  identical on every one of them. There is no re-stamping to fix.

  (2) `known_at` is load-bearing and the alternatives do not work. `_state_hash` is a
  pure content hash — `SNAPSHOT_STATE_FIELDS`/`ACTION_STATE_FIELDS`
  (award_events.py:48-104) contain no clock, and the collector's own state digest
  explicitly excludes `snapshot_date`, `known_at` and the `*_observed_at` columns
  (collectors/usaspending_awards.py:1774-1781) — so the two A-states of an oscillation
  hash identically. The minimal A -> B -> A is in fact already distinguished without the
  fold, because `changed_fields` carries direction (`before: null` vs `before: B`); the
  real collision is at period >= 2. For A -> B -> A -> B the two (A -> B) events share
  `award_key`, `source_rail`, `state_hash` = h(B), `event_type` AND `changed_fields` =
  [{field, before: A, after: B}]. Without `known_at` they collide, and `_merge`
  (award_events.py:1788-1795) folds the later one into the earlier as a duplicate —
  silently deleting a real transition. `first_seen_at` cannot separate them (constant per
  key). `prior_source_identity` (already computed at award_events.py:1516) cannot either:
  it is h(before) = h(A) for BOTH, adding no information beyond `changed_fields.before`.
  Pinning `known_at` per (award_key, state_hash) to first observation has the same defect.
  The only content-derived discriminator that survives is a per-transition ordinal or a
  hash chain over the event history — and a chain makes every identity depend on the whole
  prior prefix, so the SAME lost-update race would re-mint every downstream id instead of
  26. Strictly more fragile, not less.

  (3) The fault is upstream of the seed. `-X theirs` on a rebase resolves conflicts to the
  replayed commit, so the earlier run's appended tail is dropped rather than unioned. The
  measured receipt diff is exactly that shape: 376 removed, 376 added, same 4-tuple keys,
  and `request_sha256` + `response_sha256` identical on all 376 — USAspending published
  nothing. Repairing that resolution makes identity stable without touching a single
  published id; repairing the seed does the opposite.
alternatives:
  - option: Remove `known_at` from the `_event_id` seed
    why_not: >
      Collides the 2nd and 4th events of an A -> B -> A -> B oscillation; `_merge`
      (award_events.py:1788-1795) then silently drops the later real transition. Loses
      evidence to prevent duplication of evidence.
  - option: Pin `known_at` per (award_key, state_hash) to first observation of that state
    why_not: >
      Same collision as above for a repeated identical transition, and additionally
      re-mints every existing id whose state was ever re-entered. Already refuted in
      DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS.
  - option: Fold `prior_source_identity` (the predecessor state hash) into the seed
    why_not: >
      Adds zero discriminating power — it equals h(`changed_fields[].before`), which is
      already in the seed. Both (A -> B) events of the oscillation carry h(A).
  - option: Replace the clock with a per-(award_key, source_rail, transition) occurrence
      ordinal, or chain each event id to its predecessor
    why_not: >
      Correct in principle and the only content-derived option that preserves the
      property, but it makes identity depend on the entire history prefix, so the very
      lost-update race that motivated this would re-mint the whole downstream chain rather
      than 26 rows. It also requires a full receipt-bound re-baseline of a live ledger,
      already flagged as an operator call (#5873). Revisit only AFTER the push-path
      resolution is fixed, if idempotence is still not achieved.
  - option: Fix `-X theirs` in daily.yml's push path in this PR
    why_not: >
      Correct fix, wrong PR. That idiom appears at five sites across the nightly's push
      retries for ALL of `data/`, not just govrev; a wrong union strategy there can wedge
      the entire nightly publish. It needs its own PR with its own blast-radius review,
      and it must not ride along with a CI gate change. Named here as the owning
      next_action rather than silently deferred.
evidence:
  - "engine/government_revenue/award_events.py:1400-1419 — the seed and its `known_at` comment"
  - "engine/government_revenue/award_events.py:48-104 — SNAPSHOT_STATE_FIELDS / ACTION_STATE_FIELDS carry no clock"
  - "engine/government_revenue/award_events.py:292-302 — _state_hash is a pure content hash"
  - "engine/government_revenue/award_events.py:1788-1795 — _merge folds equal event_ids, making a collision lossy"
  - "engine/government_revenue/award_events.py:1516 — prior_source_identity is computed but not seeded"
  - "engine/government_revenue/award_events.py:1597,1600 — _pit_known_at is also a _consolidate grouping key"
  - "engine/government_revenue/candidates.py:1665 — candidate_id = digest(family, issuer, event_id)"
  - "collectors/usaspending_awards.py:1915-1916 — re-observation with unchanged state hash is SKIPPED"
  - "collectors/usaspending_awards.py:1774-1781 — collector state digest excludes every clock"
  - "collectors/usaspending_awards.py:641-643, :2973 — known_at origin is datetime.now(timezone.utc)"
  - ".github/workflows/daily.yml:702,751,772,1313,1786 — git pull --rebase --autostash -X theirs origin main"
  - ".github/workflows/daily.yml:65 — each cron and each dispatch gets its own concurrency group, cancel-in-progress false"
  - "Measured: award_event_snapshots.parquet 194/210 rows untouched; award_action_versions.parquet 35,239/35,257 untouched; event_state_sha256 identical on every moved row"
  - "Measured: collection_receipts.jsonl 376/376 changed rows carry identical request_sha256 AND response_sha256"
  - "DSC:GOVREV-DOUBLE-COLLECT-PUBLISHED-NOTHING-X-THEIRS-DROPPED-IT"
  - "DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS"
  - "PR #5870 (0e362f095f10), PR #5873 (6a05ee743636)"
affects:
  - engine/government_revenue/award_events.py
  - engine/government_revenue/candidates.py
  - collectors/usaspending_awards.py
  - .github/workflows/daily.yml
confidence: high
reversibility: easy
decided_by: session claude/govrev-event-identity-adjudication
decided_at: 2026-08-18
---

## Detail

### The property the fold actually protects

The comment at `award_events.py:1407` says the fold exists so that `A -> B -> A` emits
three distinct immutable events. That is true but understates the case in one direction
and overstates it in another.

Overstated: the minimal `A -> B -> A` does NOT need the clock. The three events differ in
`state_hash` (h(A), h(B), h(A)) and in `changed_fields` direction, and the first-observation
branch passes `before=None` (`award_events.py:1642`) where the reversion passes `before=B`.
Those three seeds are already distinct.

Understated: the collision is at period >= 2. `A -> B -> A -> B` emits two `(A -> B)`
events whose every non-clock seed component is identical. That is the case the fold is
really carrying, and it is a real case for an award whose obligated balance oscillates
across reporting cycles. `_merge` treats an equal `event_id` as the same event and folds
the occurrences together, so a collision does not merely duplicate — it deletes.

### Why "make identity a function of the evidence" is the wrong goal here

It sounds right, and in a system with a single writer it would be. But the evidence for a
repeated identical transition is, by construction, identical evidence. The only way to
separate the Nth occurrence from the first is to appeal to something outside the content:
either when we observed it (the current design) or where it sits in an ordered history (an
ordinal or chain).

An ordinal/chain is the more principled choice and is the option to revisit later. It is
worse *today* because it couples every identity to the integrity of the whole prior
history, and the incident that prompted this question is precisely a history-integrity
failure. Under the same `-X theirs` lost update, a chained scheme would have re-minted every
identity after the lost rows instead of 26. Fix the history first; then the chain becomes
attractive rather than dangerous.

### What to do instead

The owning next action is the push-path resolution, not the seed. Append-only artifacts
(`collection_receipts.jsonl`, `award_event_snapshots.parquet`,
`award_action_versions.parquet`, `candidate_ledger.jsonl`) must not be conflict-resolved
with `-X theirs`; they need a union or a post-rebase recompute, plus a base-freshness check
against `origin/main` at push time. That is a separate PR against
`.github/workflows/daily.yml` and `scripts/ci/push_retry.sh` with its own review, because
the same idiom carries the entire nightly's data publish.

Revisit this decision if, after the push path is fixed, identity still churns — that would
falsify measurement (1) and reopen the ordinal/chain option.
