---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/govrev-event-identity-adjudication
model: opus
ended_because: complete
decisions:
  - DEC:GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD
  - DEC:GOVREV-CANDIDATE-LEDGER-STAYS-APPEND-ONLY
  - DEC:GOVREV-CANDIDATE-PROOF-GATE-ARMED
discoveries:
  - DSC:GOVREV-DOUBLE-COLLECT-PUBLISHED-NOTHING-X-THEIRS-DROPPED-IT

mission: >
  Adjudicate three Government Revenue design defects deliberately left out of the #5870
  heal because they need the owning program's decision: (1) `_event_id` folding the
  collector's retrieval wall clock, (2) append-only ledger orphan accumulation with no
  supersession concept, (3) `GOVREV_CANDIDATE_PROOF_FATAL: "0"` making the lane's own
  proof step non-fatal. Plus settle whether the 15 rail-reclassified candidates from the
  2026-08-18 incident were genuine USAspending publications or pure re-derivation.

state_before: >
  origin/main @87cce5e2d4e1. PR #5870 had restored the collection generation the candidate
  projection was frozen against; PR #5873 had corrected the govrev record to say the
  projection lane is a stable no-op that never clears the red. `candidate_ledger.jsonl` on
  main held 56 rows / 56 distinct candidate_ids / 0 duplicates. main's newest ci.yml run
  (32110254994) showed ci-pack-6 red at `unrun-government-revenue`, but that run was created
  07:11:19Z against head 2a9764ba — 27 minutes BEFORE #5870's heal merged at 07:38:11Z — so
  it proved a pre-heal tree and was already stale on arrival. No decision existed on any of
  the three defects; the durable fix for the write race had been explicitly deferred to this
  program by #5870.

changed:
  - path: agentos/discoveries/DSC-GOVREV-DOUBLE-COLLECT-PUBLISHED-NOTHING-X-THEIRS-DROPPED-IT.md
    what: >
      New. Records that USAspending published NOTHING between the two 2026-08-18 passes
      (376/376 receipt pages byte-identical on request_sha256 AND response_sha256) and
      names `git pull --rebase --autostash -X theirs origin main` as the resolver that
      discards the earlier run's appended rows, with a 12-line standalone reproduction.
  - path: agentos/decisions/DEC-GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD.md
    what: >
      New. Decision NOT to change the `_event_id` seed, `_state_hash`, `_consolidate` or
      `candidate_id`. Records the measurement refuting the "collector re-mints over
      unchanged content" premise, the A -> B -> A -> B collision that makes the fold
      load-bearing, why the prior-state pointer cannot substitute, and that the durable fix
      is the push-path rebase resolution.
  - path: agentos/decisions/DEC-GOVREV-CANDIDATE-LEDGER-STAYS-APPEND-ONLY.md
    what: >
      New. Decision NOT to add a supersession/reconciliation field, tombstones, or
      compaction to `candidate_ledger.jsonl`. Records the byte-prefix binding that a
      mutable field would break, that a repeated candidate_id is legal by design, and the
      per-reader census showing orphans are inert.
  - path: agentos/decisions/DEC-GOVREV-CANDIDATE-PROOF-GATE-ARMED.md
    what: >
      New. Decision to arm the gate, with the verification that #5516's written arming
      precondition is met, and the explicit statement that arming would NOT have caught the
      2026-08-18 incident because the corruption postdates the publish.
  - path: .github/workflows/government-revenue-live.yml
    what: >
      `GOVREV_CANDIDATE_PROOF_FATAL` flipped from "0" to "1", and the preceding comment
      block rewritten from "flip once the constants are derived" to a record of the arming
      and its scope limit.

verified:
  - claim: >
      USAspending published nothing between the two collection passes; every receipt page
      that differs between the two commits carries identical request and response hashes.
    command: >
      Extracted `data/government_revenue/collection_receipts.jsonl` at 59ccb9c774c8 and
      93ab221b81dd via `git show`, took the multiset difference of canonical-JSON lines,
      indexed both sides by (subject.award_key, subject.ticker, rail, page) and compared
      every field.
    result: >
      376 rows only-in-pass-1, 376 only-in-pass-2, 376 common keys. Fields differing on all
      376: run_id, observed_at, receipt_id. Fields identical on all 376: endpoint, has_next,
      page, rail, record_count, request_sha256, response_sha256, schema_version, subject.
      168 distinct award keys, 21 tickers. Zero pages with a changed response_sha256.
  - claim: >
      The collector's re-observation dedupe works; `known_at` is not re-stamped over
      content a run can see. Only the rows the second run never saw were re-derived.
    command: >
      Read `award_event_snapshots.parquet` and `award_action_versions.parquet` at both
      commits via `git show` into pandas and ran a null-aware per-column comparison.
    result: >
      award_event_snapshots 210 rows both sides; only `known_at` and `source_receipt_id`
      differ, only on positions 194-209 (16 rows), `event_state_sha256` identical on all 16.
      award_action_versions 35,257 rows both sides; only `known_at`, `first_seen_at`,
      `award_recipient_known_at`, `source_receipt_id` differ, only on positions
      35,239-35,256 (18 rows), `event_state_sha256` identical on all 18. 194/210 and
      35,239/35,257 rows untouched.
  - claim: >
      `git pull --rebase --autostash -X theirs origin main` silently discards the other
      run's appended tail rows in an append-only file.
    command: >
      Standalone 12-line git reproduction outside this repo (init, clone, append a
      different tail line in each clone, then `git pull --rebase --autostash -X theirs
      origin master` in the second) — printed in the DSC Detail section.
    result: >
      Resulting file contains base1, base2, RUN_B_row. RUN_A_row is gone, with no conflict
      reported and no retry fired.
  - claim: >
      The three suites the proof gate runs are green at HEAD, so arming the gate does not
      block a govrev publish today.
    command: >
      `python3 -m pytest -p no:cacheprovider tests/test_government_revenue_candidates.py
      tests/test_government_revenue_candidate_projection.py
      tests/test_government_revenue_candidate_fixture.py -q`
    result: "92 passed, 3 warnings in 635.99s (0:10:35). Zero failures."
  - claim: >
      #5516's written arming precondition is met — all three hand-typed GRAPH-VINTAGE
      constants it named are now derived.
    command: >
      Grepped `reviewed_issuer_company_count`, `mapping_needed`, `mapping_backlog`,
      `canonical_frozen_at`, `canonical_candidate_census` across the three proof-gate test
      files.
    result: >
      `reviewed_issuer_company_count` asserted `== len(...)`
      (test_government_revenue_candidates.py:295); `mapping_needed` asserted
      `== len(canonical_requested_issuer_tickers())` (:265 and
      test_government_revenue_candidate_projection.py:715); the 19-ticker list asserted
      against `list(canonical_requested_issuer_tickers())` (:271). Remaining `== 19` / `== 21`
      occurrences are explanatory comments. The one surviving literal, `mapping_needed == 2`
      (:614), asserts against a synthetic in-test fixture, not the live graph vintage.
  - claim: "Flipping the env value trips no wiring mirror."
    command: >
      `grep -rn "GOVREV_CANDIDATE_PROOF_FATAL|govrev candidate proof|prove the candidate
      projection" tests/ scripts/ .github/` excluding the workflow itself.
    result: "No matches. The variable appears only in government-revenue-live.yml."
  - claim: "The committed ledger on main holds no orphans today."
    command: "`git show HEAD:data/government_revenue/candidate_ledger.jsonl | wc -l` plus a Python parse."
    result: >
      56 rows, 56 distinct candidate_id, 56 distinct observation_id, 0 duplicates, all rows
      `candidate_state: awaiting_crosscheck`. The "82 rows for 56 live" figure is the
      prospective state had the 26 re-mints been issued forward; #5870 restored coherence
      before that happened.
  - claim: "The agentos records validate."
    command: "`python3 scripts/agentos.py validate`"
    result: "0 error(s); the 10 warnings are pre-existing and belong to other workstreams."

  - claim: >
      The ci-pack-6 red on main's run 32110254994 was already FIXED by PR #5870 before this
      session began — that run's head predates the heal. It is not a live red and not a
      data-churn artifact.
    command: >
      `git log -1 --format='%cI' 0e362f095f10` (the #5870 merge commit);
      `gh run view 32110254994 --json createdAt,headSha`;
      `git merge-base --is-ancestor 0e362f095f10 2a9764ba5b442875878f83461ffe8763b728f451`.
    result: >
      #5870 merged 2026-08-18T07:38:11Z. Run 32110254994 was created 07:11:19Z on head
      2a9764ba, 27 minutes EARLIER, and the ancestry test confirms the heal is NOT in that
      run's tree. So the run proved a pre-heal main. Corroborated independently by the
      session that owned the heal (verified 39 passed at main fc9d58195e16).
  - claim: >
      The whole `unrun-government-revenue` step passes at 87cce5e2d4e1, the post-heal HEAD
      this branch is cut from.
    command: >
      Ran all 19 files enumerated by .github/ci/legacy-jobs.yml:7644 at HEAD, in three
      batches (the three proof-gate suites serially, then 8 files and 11 files under
      `-n 4 --dist load`, plus tests/test_government_revenue_wave8_api.py).
    result: "92 + 247 + 231 + 7 = 577 passed, 0 failed."

unverified:
  - claim: >
      That the failure MODE cannot recur. #5870 healed this instance's data; the race that
      produced it — two overlapping collect jobs plus an `-X theirs` push resolution — is
      still live until the push-path work lands.
    what_would_verify: >
      A night with two overlapping `daily.yml` collect jobs that leaves
      `collection_receipts.jsonl` a prefix-extension of its predecessor. Until then treat
      recurrence as expected, not as a new defect.
  - claim: >
      That no consumer outside this repo distinguishes a live candidate from an orphaned
      one via `/candidate/{id}/history`.
    what_would_verify: >
      Grep the terminal repo (charting-app) and the Mastermind repo for that route; this
      session's census covered macro only.

unresolved:
  - >
      The push-path fix itself. `-X theirs` appears at .github/workflows/daily.yml:702,
      :751, :772, :1313, :1786 and governs the entire nightly data publish, not just
      govrev. It needs its own PR and its own blast-radius review. Deliberately not bundled
      with a CI gate change. NOTE: an earlier revision of this handoff floated `merge=union`
      as the cheap half of that fix. That is REFUTED and must not be shipped for
      `data/government_revenue/` — see do_not_redo. The live remedy is the base fence
      (PR #5885), which withholds the whole coherence family.
  - >
      ci-pack-6 remains red on main at `unrun-government-revenue`. Not caused by, and not
      cleared by, this session's work. Because `.github/workflows/**` is a CI authority
      path (scripts/ci_authority_paths.py:25-30), the workflow flip in this PR sets
      authority_changed=true, so a base-inherited red does not excuse it and this PR needs
      main itself green on ci-pack-6 to merge.
  - >
      Whether the `/candidate/{id}/history` route should disclose liveness. Decided to be
      out of scope here (public API surface, no measured failure); the fix, if wanted, is a
      derived field computed from the queue the route already holds — never a ledger
      mutation.

next_actions:
  - >
      Open the push-path PR against .github/workflows/daily.yml and
      scripts/ci/push_retry.sh: stop resolving append-only artifacts with `-X theirs`, and
      add a base-freshness check against origin/main before the push. Append-only set:
      collection_receipts.jsonl, award_event_snapshots.parquet,
      award_action_versions.parquet, candidate_ledger.jsonl. This is the durable fix for
      the identity churn and the one #5870 deferred to this program.
  - >
      Identify the file failing inside `unrun-government-revenue`'s 20-file step on main
      and either heal it in one whole-pack PR or escalate the operator disposition #5873
      describes. The three proof-gate suites are green, so the red is in one of the other 17.
  - >
      Once the push path is fixed and identity stops churning, revisit whether to replace
      the `known_at` fold with a per-transition occurrence ordinal or an event hash chain —
      the only content-derived scheme that preserves the oscillation property. It is the
      more principled design and is only dangerous while history integrity is unreliable.

do_not_redo:
  - >
      Do NOT add `merge=union` (or any `.gitattributes` merge driver) for
      `data/government_revenue/`. This session proposed it and was REFUTED by PR #5885;
      verified here. `candidate_ledger.jsonl` is bound by an exact BYTE PREFIX hash —
      `prefix = ledger.raw[:prior_byte_count]` then `sha256(prefix) != prior_sha256 -> raise
      CandidateProjectionError` (scripts/build_government_revenue_candidates.py:540-542) — so
      a union-merged tail cannot reproduce the hash and union turns a SILENT lost update into
      a HARD lane failure. Union also cannot cover the parquet spine (binary), which is what
      actually moved candidate_id; and partial application leaves receipts from both runs
      against a spine from one, the exact mixed generation the torn-generation refusal
      (collectors/usaspending_awards.py:3956-3972) exists to prevent. The 20 existing
      `merge=union` entries are all STANDALONE ledgers with no cross-artifact hash binding;
      `data/government_revenue/` is ONE hash-bound generation. The unit of correctness is the
      family, not the file. Same objection as the `is_current` refusal in
      DEC:GOVREV-CANDIDATE-LEDGER-STAYS-APPEND-ONLY — both rewrite bytes behind a recorded
      prefix.
  - >
      Do NOT remove `known_at` from the `_event_id` seed, and do NOT pin it per
      (award_key, state_hash) to first observation. Both collide the 2nd and 4th events of
      an A -> B -> A -> B oscillation, and `_merge` (award_events.py:1788-1795) folds the
      collision, deleting a real transition. Settled in
      DEC:GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD.
  - >
      Do NOT fold `prior_source_identity` into the seed as a substitute. It equals
      h(changed_fields.before), already in the seed, so it adds zero discriminating power —
      both (A -> B) events carry h(A).
  - >
      Do NOT investigate whether the collector re-stamps `known_at` on re-observation. It
      does not; `_append_event_versions` skips an unchanged state hash
      (collectors/usaspending_awards.py:1915-1916), measured at 194/210 and 35,239/35,257
      rows untouched.
  - >
      Do NOT treat the 2026-08-18 rail reclassifications as USAspending publications. All
      376 differing receipt pages carry identical response_sha256; nothing was published.
  - >
      Do NOT add is_current / replaced_by / supersedes_row_id to the candidate ledger, and
      do NOT prune or compact it. Breaks the byte-prefix binding at
      scripts/build_government_revenue_candidates.py:498-538. Settled in
      DEC:GOVREV-CANDIDATE-LEDGER-STAYS-APPEND-ONLY.
  - >
      Do NOT revive engine/government_revenue/candidate_grader.py to supply supersession.
      It targets candidate_issuance_log.jsonl, which does not exist, and
      test_amendment_window_is_closed_and_the_grader_remains_uncalled asserts by AST walk
      that zero modules import it.
  - >
      Do NOT claim the proof gate would have caught the 2026-08-18 incident. The fold
      published at 04:15:52Z against a coherent tree; the clobbering pass committed at
      04:21:53Z.

danger_areas:
  - >
      `.github/workflows/**`, `.github/ci/**` and `scripts/**` are CI authority paths
      (scripts/ci_authority_paths.py:25-50). Any edit there sets authority_changed=true on
      the PR head, which removes the base-inherited-red excuse — the PR then needs main
      itself green. Budget for that before bundling a workflow edit with anything else.
  - >
      `-X theirs` is not a safe conflict strategy for append-only artifacts anywhere. It has
      now cost this repo evidence twice in two lanes — here, and the render-lane paywall
      splice. Treat any new `-X theirs` in a push path as a defect until proven otherwise.
  - >
      The candidate ledger's integrity is a BYTE-PREFIX binding plus a recorded
      sha256/byte_count, not a row-level schema check. Anything that rewrites a historical
      row — even adding a field — fails it by construction.
  - >
      This worktree was sparse; `data/` had to be materialized with
      `python3 scripts/worktree_sparse.py add data` before the govrev suites could run. A
      sparse tree makes these suites fail as artifacts, not as regressions.
  - >
      The proof step is `if: steps.gate.outputs.publish == 'yes'`, so an armed gate only
      bites on a publishing night. Do not conclude from a quiet night that the arming is
      inert.
---

Three defects adjudicated; two resolved as decisions NOT to change code, one shipped as a
one-value arming of the lane's own proof gate. The load-bearing correction is that the
2026-08-18 identity churn is not an `event_id` design defect at all: the collector's
re-observation dedupe works, USAspending published nothing in the window, and the rows were
lost by `git pull --rebase --autostash -X theirs origin main` resolving an append-only tail
conflict in favour of the replayed commit. The durable fix is that push path, which is the
first next action and is deliberately not in this PR.
