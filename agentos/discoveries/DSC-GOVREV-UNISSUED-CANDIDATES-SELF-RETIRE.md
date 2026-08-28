---
key: GOVREV-UNISSUED-CANDIDATES-SELF-RETIRE
claim: >
  A Government Revenue candidate that is source-emitted but not yet issued needs
  NO reviewed non-issuance record: nightly issuance retires it from the
  unaccounted set by construction. Measured 2026-08-19 at main f57565ac52bf,
  the two BWXT rows (grc1-2431cef9fbca1f209edb0f45,
  grc1-81a1a8df4bdb97de3b1cdfa8, award CONT_AWD_89233123CNA000308_8900) that
  PR #6004 recorded as unaccounted had ISSUED — emitted 64 / ledger 64 distinct
  / quarantined 8 / queue 56, unaccounted = 0, and ledger-minus-quarantined ==
  queue exactly. A B2-style manifest naming them is not merely unnecessary but
  UNLOADABLE: engine/government_revenue/candidates.py:551-552 raises "a reviewed
  historical source identity was issued as a candidate" when manifest keys
  intersect issued keys.
falsifier: >
  A fresh measurement where unaccounted = emitted_ids - ledger_ids -
  quarantined_ids is NON-EMPTY while candidate_projection_status.recipient_graph_id
  == recipient_entity_graph.graph_id (publisher caught up, so the #6004 vintage
  excuse is inert). That is the only state a reviewed non-issuance record would
  be a record OF. Re-run the measurement before re-proposing; today it is empty.
so_what: >
  Do not build the reviewed non-issuance record (option B2) and do not collapse
  latest.as_of into payload.generated_at (option B3). B3's premise — a silent
  admission asymmetry between the two clocks — is FALSE: both edges abort loudly
  (scripts/build_government_revenue_candidates.py:619-622 "current candidate
  observation is after the frozen generated_at clock"; :993-1006 "new candidate
  observation is not forward of the prior frozen generated_at clock"). Sharing
  one clock would convert those hard refusals into invisible omissions, the exact
  failure class the suppression/correction apparatus exists to prevent. B2 would
  additionally subtract ids from the unaccounted set PERMANENTLY, including after
  they issue, holing the one gate that catches the 2026-08-10 incident class.
kind: constraint
verified_at: 2026-08-19
verified_by: "measured at main f57565ac52bf with data/ materialized: build_candidate_observations + candidate_ledger.jsonl + candidate_queue.json + load_candidate_issuance_correction_manifest -> 64/64/8/56, unaccounted=[]; both BWXT ids in_ledger=True in_queue=True, entered ledger in nightly 36a660c1e596 (2026-08-19T17:23Z), absent in prior nightly b73f3954c4dc; tests/test_government_revenue_candidates.py 43 passed 1 skipped, the skip being test_covered_row_that_issues_leaves_unaccounted_by_construction:884 skipping on empty unaccounted; refusal sites read at candidates.py:551-552 and build_government_revenue_candidates.py:619-622,:993-1006"
scope:
  - "macro"
  - "engine/government_revenue/candidates.py"
  - "scripts/build_government_revenue_candidates.py"
  - "config/government_revenue/"
confidence: verified
---

Supersedes the standing action item in the 2026-08-19 opus debug packet and the
#5997 PR body, both of which proposed option B2 while the two BWXT rows were
still unissued. PR #6004 already refused B2 on evidence; this record adds the
measurement showing the rows have since issued, so the motivating exemplars no
longer exist and a manifest built for them would state a false fact.

The publisher-vintage excuse added by #6004 is currently INERT, not merely
unused: published and committed graph ids are both
`recipient-graph:reviewed:2026-08-19:defense21-v1`, so `publisher_is_behind` is
False and the incident gate runs at full strength while passing.

Known gap carried forward from #6004 and NOT closed here: the publisher-vintage
lag has no alarm. A publisher that never fires again stays silent forever while
the conjunct keeps excusing rows — same family as the cancel-invisibility law in
CLAUDE.md. That is the successor work worth commissioning, not B2.

See `DSC:GRAPH-REPUBLISH-RETIMES-EVERY-CANDIDATE-CLOCK` for why any such record's
entry key must be graph/clock-independent, and
`tests/test_government_revenue_candidates.py:250-253` for the accounting identity
(`queue.counts.total - len(corrections.entries) == status.candidate_count`,
64 - 8 = 56) that already asserts closure.
