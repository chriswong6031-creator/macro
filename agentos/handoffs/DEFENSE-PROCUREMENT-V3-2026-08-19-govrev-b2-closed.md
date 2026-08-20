---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/govrev-reviewed-non-issuance
model: fable
ended_because: complete
prs:
  - 6008
discoveries:
  - DSC:GOVREV-UNISSUED-CANDIDATES-SELF-RETIRE

mission: >
  Re-commission of the same brief the previous session answered as #6004:
  implement option B2 (reviewed non-issuance record — new manifest + schema +
  loader) for the two source-emitted-but-unissued BWXT candidates, or adjudicate
  B3 (share one as_of between the source-truth and projection paths).

state_before: >
  The brief described emitted 64 / queue 54 / ledger 62 distinct, with the
  residual being exactly two BWXT rows excused by the issuance-frontier anchor.
  That is the PRE-#6004 state. #6004 had already refused B2 on evidence and
  narrowed the excuse to the publisher's committed graph-vintage receipt, and
  its handoff listed as UNVERIFIED that "the next publishing run passes step
  10's proof and actually issues the two rows" — no publishing run had fired at
  the time it was written.

changed:
  - path: agentos/discoveries/DSC-GOVREV-UNISSUED-CANDIDATES-SELF-RETIRE.md
    what: >
      New discovery recording that the two BWXT rows have since ISSUED, that the
      unaccounted set is now empty, that a B2 manifest naming an issued identity
      is refused at load, and that B3's silent-drop premise is false. Carries the
      falsifier that would reopen B2.
  - path: agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-19-govrev-b2-closed.md
    what: This handoff; closes #6004's open unverified item.

verified:
  - claim: >
      The unaccounted set is EMPTY and both BWXT ids are issued and published —
      emitted 64, ledger 64 distinct, quarantined 8, queue 56, and
      ledger-minus-quarantined equals the queue exactly.
    command: >
      python3 -c "from scripts.build_government_revenue import build_payload;
      from engine.government_revenue.candidates import build_candidate_observations,
      load_candidate_issuance_correction_manifest; ..." over
      data/government_revenue/{recipient_entity_graph,candidate_queue}.json and
      candidate_ledger.jsonl, run at main f57565ac52bf with data/ materialized
    result: >
      emitted 64 / ledger 64 / quarantined 8 / queue 56; unaccounted = [];
      ledger-quarantined == queue -> True; ledger_ids - emitted -> [];
      grc1-2431cef9fbca1f209edb0f45 and grc1-81a1a8df4bdb97de3b1cdfa8 both
      in_ledger=True, in_queue=True, quarantined=False.
  - claim: >
      Nightly issued the two rows, closing #6004's unverified item — the
      publishing run fired and the proof passed.
    command: >
      for sha in $(git log --format=%H -20 -- data/government_revenue/candidate_ledger.jsonl);
      do git show $sha:data/government_revenue/candidate_ledger.jsonl | grep -c
      grc1-2431cef9fbca1f209edb0f45; done
    result: >
      Present from 36a660c1e596 ("govrev: SAM opportunity evidence
      2026-08-19T17:23Z") onward; absent in the prior nightly b73f3954c4dc.
  - claim: >
      The incident gate runs at FULL strength (not merely unused) and passes —
      publisher and committed graph vintages match, so publisher_is_behind is
      False and the #6004 excuse branch is dead.
    command: >
      python3 -m pytest tests/test_government_revenue_candidates.py -q; plus
      reading recipient_graph_id from candidate_projection_status.json against
      graph_id from recipient_entity_graph.json
    result: >
      43 passed, 1 skipped in 358.71s. Both ids read
      recipient-graph:reviewed:2026-08-19:defense21-v1. The single skip is
      test_covered_row_that_issues_leaves_unaccounted_by_construction:884
      skipping on an empty unaccounted set — the deferral resolving itself.
  - claim: >
      A B2 manifest naming these rows would be REFUSED at load, so B2 is
      unimplementable rather than merely unnecessary.
    command: sed -n '540,560p' engine/government_revenue/candidates.py
    result: >
      candidates.py:551-552 raises ValueError("a reviewed historical source
      identity was issued as a candidate") when manifest keys intersect issued
      keys.
  - claim: >
      B3's motivating mechanism does not exist — the two-clock boundary aborts
      loudly on both edges, so there is no silent-drop state to reconcile.
    command: >
      sed -n '615,625p;990,1010p' scripts/build_government_revenue_candidates.py
    result: >
      :619-622 raises CandidateProjectionError("current candidate observation is
      after the frozen generated_at clock"); :993-1006 raises
      CandidateProjectionError("new candidate observation is not forward of the
      prior frozen generated_at clock: ...").

unverified:
  - claim: >
      That the emptiness of the unaccounted set is durable for FUTURE
      republishes. It is durable for these two rows (the ledger is append-only,
      so an issued id can never re-enter the unaccounted set), but a later
      reviewed-graph republish can mint new rows that sit unaccounted until the
      next publish.
    what_would_verify: >
      Re-run the core measurement after the next defense-graph republish and
      confirm unaccounted returns to empty once the publisher consumes the new
      vintage.
  - claim: >
      That the publisher-vintage lag alarm is still absent. Read from #6004's
      handoff and not independently re-audited this session.
    what_would_verify: >
      grep the govrev builders and government-revenue-live.yml for any
      instrument comparing candidate_projection_status.recipient_graph_id to
      recipient_entity_graph.graph_id across a publishing window.

unresolved:
  - >
    The publisher-vintage lag STILL has no alarm — carried forward unchanged
    from #6004. A publisher that never fires again stays silent forever while
    the conjunct keeps excusing rows. Same family as the cancel-invisibility law
    in CLAUDE.md. This is the successor commission.
  - >
    The latent wedge #6004 flagged at build_government_revenue_candidates.py:896
    (known_at <= prior_frozen_at is a hard error, not a skip) is untouched and
    still latent.

next_actions:
  - >
    Build the publisher-lag alarm: an instrument that reds or annotates when
    candidate_projection_status.recipient_graph_id has trailed
    recipient_entity_graph.graph_id across a publishing window. This is the one
    real gap left in this area.
  - >
    Do NOT re-commission B2 or B3 from the 2026-08-19 opus debug packet — that
    packet is now twice-stale. If a future brief cites it, re-measure first.

do_not_redo:
  - >
    Do not build a reviewed non-issuance record for the BWXT rows. They are
    ISSUED as of nightly 36a660c1e596; a manifest naming them is refused at load
    by candidates.py:551-552 and would state a false fact in an immutable chain.
    This supersedes nothing in #6004's do_not_redo — it strengthens its first
    entry from "not yet shown necessary" to "now provably impossible".
  - >
    Do not pursue B3 in any framing. Its premise (a silent admission asymmetry
    between latest.as_of and payload.generated_at) is FALSE — both edges abort
    loudly. Collapsing the clocks would convert hard refusals into invisible
    omissions, the exact class the suppression apparatus exists to prevent.
  - >
    Do not re-stamp or extend the immutable suppression/correction pair
    (carried forward from #6004).
  - >
    Do not treat the 8-row queue delta (64 emitted vs 56 queued) as an anomaly.
    It is EXACTLY the 8 reviewed HII rows in candidate_issuance_corrections.v1.json,
    verified by set equality, and tests/test_government_revenue_candidates.py:250-253
    already asserts that identity.

danger_areas:
  - >
    tests/test_government_revenue_candidates.py is INSIDE the publish proof gate
    (government-revenue-live.yml, GOVREV_CANDIDATE_PROOF_FATAL=1). A red there
    refuses the publish and freezes the render finalize gate fleet-wide. Carried
    forward from #6004 and still true; this session changed no test code.
  - >
    Reproduction trap: there is NO build_payload in
    engine/government_revenue/candidates.py. It lives in
    scripts/build_government_revenue.py. Importing it from the engine module
    raises ImportError and can be mistaken for a broken tree.
  - >
    Measuring this area requires data/ on disk. In a sparse session worktree run
    `python3 scripts/worktree_sparse.py add data` FIRST — and note `timeout` does
    not exist on this macOS shell, so a `timeout ...` wrapper silently voids the
    whole command while still reporting exit 0.
---

# DEFENSE-PROCUREMENT-V3 — B2/B3 closed on evidence (2026-08-19, second pass)

`WS:DEFENSE-PROCUREMENT-V3` · mints `DSC:GOVREV-UNISSUED-CANDIDATES-SELF-RETIRE`
· closes the open `unverified` item in
`agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-19-govrev-non-issuance.md` (#6004).

## What happened

This session was handed the same brief #6004 answered, still describing the
pre-#6004 numbers (emitted 64 / queue 54 / two BWXT rows unaccounted). Measuring
before building showed the premise had expired: nightly `36a660c1e596`
(2026-08-19T17:23Z) issued both rows. `unaccounted` is now empty, the queue
carries 56, and the accounting closes exactly.

The previous session predicted this. Its first `do_not_redo` said not to write a
manifest "without first showing an unaccounted row NOT explained by the vintage
lag and NOT issuable by a future publishing run". Both rows were issuable, and a
publishing run issued them. The deferral was correct engineering, not a debt.

## Why nothing was built

B2 is now *unimplementable*, not merely unnecessary: `candidates.py:551-552`
refuses a manifest whose keys intersect issued keys. B3's premise is false: the
two-clock boundary raises `CandidateProjectionError` on both edges rather than
dropping rows silently, so there is no asymmetry to reconcile and collapsing the
clocks would trade loud refusals for invisible omissions.

Shipped: one discovery record and this handoff. No engine, config, contract, or
test code changed.

## The one real gap

The publisher-vintage lag still has no alarm. That is the successor commission,
and it is the only thing in this area worth a session right now.
