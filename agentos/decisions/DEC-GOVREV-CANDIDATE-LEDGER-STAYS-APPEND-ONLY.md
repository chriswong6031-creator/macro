---
key: GOVREV-CANDIDATE-LEDGER-STAYS-APPEND-ONLY
question: >
  When a re-derivation re-mints `candidate_id`, the re-minted rows append to
  `data/government_revenue/candidate_ledger.jsonl` while the superseded ones stay
  forever — 56 live candidates would sit inside 82 rows. There is no reconciliation or
  supersession concept. Should one be added?
answer: >
  NO supersession or reconciliation FIELD on the ledger, and no compaction, pruning or
  rewriting of it. The ledger is a receipt-bound append-only evidence log whose integrity
  contract is a byte-prefix binding; a mutable `is_current` / `replaced_by` / tombstone
  would require rewriting historical rows and would break exactly the property that makes
  it evidence rather than a cache. Liveness is already a DERIVED projection and needs no
  ledger field: `build_candidate_queue()` is a pure projection of `latest_payload` and
  never reads the ledger, so orphans cannot reach the rendered surface. Orphan rows are
  inert to every reader measured. The one real residue — `/candidate/{id}/history` serves
  an orphaned id with HTTP 200 and no indication it is no longer live — is a DERIVED
  disclosure question, not a ledger-shape question, and is recorded as a follow-up rather
  than fixed by mutating the ledger.
rationale: >
  Three findings decide this.

  (1) Mutating the ledger would break its own integrity contract.
  `_validate_ledger_state_binding` (scripts/build_government_revenue_candidates.py:498-538)
  proves the on-disk ledger is a strict BYTE-PREFIX extension of what the previous run
  recorded, and `app/government_revenue.py:807-830` binds `ledger_sha256` / `byte_count` /
  `line_count` against `candidate_projection_state.json`. Setting `is_current: false` on an
  earlier row rewrites bytes behind the recorded prefix, so every one of those checks fails
  by construction. A supersession field is not a small schema addition here; it is a repeal
  of the append-only contract.

  (2) A repeated `candidate_id` is LEGAL BY DESIGN, not a corruption. The writer rejects a
  duplicate `observation_id` and a duplicate observation-key tuple but deliberately accepts a
  repeated `candidate_id` — a later observation of the same candidate is a normal event,
  pinned by `tests/test_government_revenue_candidate_grader.py`
  `test_closed_window_guard_allows_a_later_observation_of_an_existing_candidate`. So the
  ledger already has no notion of "the one live row per candidate", and adding one would
  contradict a behaviour the suite asserts.

  (3) Orphans are inert. Reader census: `build_candidate_queue()`
  (engine/government_revenue/candidates.py:1913) never opens the ledger — the queue the site
  renders is regenerated from `latest_payload` each run, so an orphan cannot appear in a
  listing. `app/government_revenue.py:670,742,807-830` reads all rows but only to validate
  whole-file canonicality and the sha256/byte-count binding — an integrity check, not a live
  filter. `scripts/check_vintage_pin_fence.py:50` is a whole-file hash fence.
  `engine/government_revenue/candidate_grader.py` carries the only supersession vocabulary in
  the program (`supersedes_row_id`, `RETRACTION_REASONS`, `superseded_ancestors()`) but
  operates on `candidate_issuance_log.jsonl`, which does not exist in the repo
  (`git ls-tree -r HEAD --name-only | grep issuance_log` → empty) and whose module nothing
  imports. No reader treats an orphan as corrupting.

  Storage is not a motive either: 26 extra JSONL rows per incident, and incidents of this
  class are supposed to stop once the push-path lost update is fixed
  (DEC:GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD).
alternatives:
  - option: Add `is_current` / `replaced_by` / `supersedes_row_id` to the ledger row contract
    why_not: >
      Requires rewriting historical rows, which breaks the byte-prefix binding at
      scripts/build_government_revenue_candidates.py:498-538 and the sha256/byte-count
      binding at app/government_revenue.py:807-830. Repeals the append-only contract to
      solve a problem no reader has.
  - option: Append tombstone rows that retract superseded ids (append-only, no rewrite)
    why_not: >
      Contract-safe but solves nothing today — no reader filters on liveness, so the
      tombstones would be written and never read. It also needs a reviewed disposition class
      that does not exist (#5873), and inventing one to mark rows nothing consumes is
      ceremony. Reconsider only if a consumer appears that must distinguish them.
  - option: Compact or prune orphaned rows
    why_not: >
      Destroys evidence and breaks the prefix binding outright. The observations really were
      made and really were receipt-bound; deleting them makes the ledger a cache.
  - option: Wire up the existing candidate_grader supersession machinery to this ledger
    why_not: >
      It targets a different artifact (`candidate_issuance_log.jsonl`) that does not exist and
      that nothing imports; `test_amendment_window_is_closed_and_the_grader_remains_uncalled`
      asserts by AST walk that zero modules import the grader. Adopting it would mean
      reviving a deliberately dormant subsystem to serve a need that has not been shown.
  - option: "(none considered) — accept orphans silently with no record"
    why_not: >
      The `/candidate/{id}/history` disclosure gap is real even if minor; leaving it
      undocumented is how it gets rediscovered as a bug later. Recorded as a follow-up.
evidence:
  - "scripts/build_government_revenue_candidates.py:460-490,498-538 — canonical row validation and byte-prefix state binding"
  - "app/government_revenue.py:129,670,742,807-830 — whole-ledger integrity binding, not a live-row filter"
  - "app/government_revenue.py:1736-1775 — /candidate/{id}/history filters the ledger by candidate_id; 404 only when no row exists"
  - "engine/government_revenue/candidates.py:1913 — build_candidate_queue is a pure projection of latest_payload, never reads the ledger"
  - "contracts/government_revenue/government_revenue_candidate.v1.schema.json — no is_current / supersedes / replaced_by / active field"
  - "engine/government_revenue/candidate_grader.py:174 — ISSUANCE_LOG_FILENAME = candidate_issuance_log.jsonl; git ls-tree shows no such file"
  - "tests/test_government_revenue_candidate_grader.py — test_amendment_window_is_closed_and_the_grader_remains_uncalled (AST walk: zero importers); test_closed_window_guard_allows_a_later_observation_of_an_existing_candidate"
  - "scripts/check_vintage_pin_fence.py:50 — whole-file vintage fence over candidate_ledger.jsonl"
  - "git show HEAD:data/government_revenue/candidate_ledger.jsonl | wc -l → 56 rows, 56 distinct candidate_id, 0 duplicates on main today"
  - "DEC:GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD"
affects:
  - data/government_revenue/candidate_ledger.jsonl
  - scripts/build_government_revenue_candidates.py
  - app/government_revenue.py
  - contracts/government_revenue/
confidence: high
reversibility: easy
decided_by: session claude/govrev-event-identity-adjudication
decided_at: 2026-08-18
---

## Detail

### The orphan count is a counterfactual, not a state on main

"82 rows for 56 live candidates" describes what the ledger WOULD hold had the projection
self-healed by issuing the 26 re-identified candidates forward. It did not: PR #5870
restored the collection generation the projection was frozen against, and the committed
ledger on main is 56 rows with 56 distinct `candidate_id`s and no duplicates. So this
decision is about the general shape, not about repairing a current corruption.

### The one residue worth naming

`/candidate/{id}/history` (app/government_revenue.py:1736) filters the ledger by
`candidate_id` and 404s only when no row matches. An orphaned id therefore still returns
200 with its observations, while being absent from the queue listing that
`build_candidate_queue()` produces. That is defensible — the observation genuinely was made
and is receipt-bound, and an immutable evidence log that keeps serving it is being honest —
but a consumer cannot tell an orphan from a live candidate from the response alone.

If that is worth closing, the fix is a DERIVED field on the history envelope (the route
already holds `queue`, so "is this candidate_id present in the current queue" is available
without touching a single ledger byte). That is additive, non-mutating, and contract-safe.
It is deliberately NOT bundled here: it is a public API surface change, it is not required
by any measured failure, and this PR's shipped change is a CI gate.

### Standing guidance

Do not hand-write ledger rows, do not allowlist ids, do not prune. When a red reports
first-seen candidates with neither a ledger issuance nor a reviewed suppression, check
whether the same (candidate_family, issuer_company_id, award-ref, effective_at) tuples also
appear as orphaned rows before believing new records arrived — 26 unaccounted paired 1:1
with 26 orphans over 18 tuples in this incident, which is re-identification, not discovery.
