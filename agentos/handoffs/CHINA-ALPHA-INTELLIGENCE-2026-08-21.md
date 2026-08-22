---
workstream: WS:CHINA-ALPHA-INTELLIGENCE
session: claude/p1-receipt-capture
model: fable
ended_because: complete
mission: >
  FABLE-00 China Alpha P1 close-out under the Sol P1 NATURAL-RUN ADJUDICATION
  (2026-08-21). Sol supplied the qualifying run and forbade waiting for or
  triggering another Asia-close. Mandate: from the immutable run and collection
  commit, reconcile ALL 145 same-run institutional-visit candidates against the
  visit plane per announcementId — never substituting n_candidates=145,
  health=ok, workflow success, or aggregate row counts — require
  represented_downstream + named_typed_exclusions == 145 with zero silent drops
  and zero next-cycle deferrals; then, only if the data path passes, finish the
  product acceptance on the deployed production China dossier (desktop +
  mobile) and open ONE records-only closeout PR flipping P1 to DONE /
  PROVEN_LIVE. Explicitly forbidden: widening the implementation, starting P1B
  / L0 / R1 / R2 / P2 or any later China family.
state_before: >
  P1 BUILT_NOT_PROVEN. #6050 (visit tape) merged as squash c54d1b55f673 with
  the page half proven live but zero real visit rows; P1-R1 (same-cycle
  derivation) merged as #6142 squash 650be4dfe6d5 with post-merge ship-loop
  proof run 32435629231 only. pr0d and D2B2-CN-HK already DONE / PROVEN_LIVE
  (recorded in #6165). One execution gate open in the tranche: the first
  natural asia-close.yml run containing #6142. This session's own watcher
  frontier was stale — Sol had already identified run 32460910383 and handed
  it over.
changed:
  - path: research/china_alpha_intelligence/receipts/P1_NATURAL_RUN_RECEIPT_2026-08-21.md
    what: >
      NEW. The P1 natural-run receipt: immutable pointers with verified
      ancestry, the same-invocation execution-order log extract, persisted
      health/coverage, the full 145-candidate reconciliation arithmetic with
      origin and freshness splits, the classifier cross-check, the named
      residual risk, the production product-acceptance table, and the final
      production capability statement plus what it does NOT claim.
  - path: research/china_alpha_intelligence/receipts/p1_candidate_reconciliation_2026-08-21.tsv
    what: >
      NEW. One row per candidate, 145 rows: announcement_id, sec_code,
      sec_name, exchange, publish_ts, has_announcement_id,
      filing_new_in_this_run_delta, represented_in_visit_plane,
      visit_system_recorded_at, row_origin, typed_exclusion, title. This is the
      artifact Sol's "exact 145-candidate reconciliation" names; the receipt
      markdown only summarizes it.
  - path: verify_shots/china_p1_visits_desktop_2026-08-21.png
    what: >
      NEW. Anonymous production crop, 1280px viewport at 2x DPR, of the
      Institutional-visits section on https://www.mastermind-x.com/china_intel.html
      showing 601328.SS 交通银行 populated alongside 14 measured-null cards.
  - path: verify_shots/china_p1_visits_mobile_2026-08-21.png
    what: >
      NEW. Same section at a 375px iPhone viewport, heading through the
      populated 601328.SS card.
  - path: agentos/discoveries/DSC-CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP.md
    what: >
      NEW landmine. china_visits' falsy-announcementId drop is a bare
      comprehension guard with no typed exclusion, no counter and no health
      note, while n_candidates keeps counting the pre-filter list — so the
      collector's own receipts cannot distinguish a clean run from one that
      dropped k candidates. Fired zero times on the proof run; deliberately not
      repaired.
  - path: agentos/workstreams/WS-CHINA-ALPHA-INTELLIGENCE.md
    what: >
      p1 wave flipped in_progress -> done with the full receipt appended to its
      next_action (run/commit pointers, ancestry, execution order, health,
      reconciliation, origin + freshness splits, product evidence, residual
      risk, and the standing later-wave closure); wave title restated as DONE /
      PROVEN_LIVE; the top-level next_action rewritten so it no longer names
      the P1 proof as pending and names the closed gate instead.
verified:
  - claim: The run is real and its lane actually executed (not a gated-off no-op).
    command: >
      gh run view 32460910383 --json ... --jq '...' and
      gh run view 32460910383 --json jobs — run conclusion success; job `asia`
      conclusion success, 2026-08-21T08:45:24Z -> 10:36:17Z; job `ths_rescrape`
      skipped; head 1ab485789d446d202c8da600edb81f6416e8871f.
  - claim: The code under test is actually in the run and in the proved page.
    command: >
      git merge-base --is-ancestor 650be4dfe6d5... 1ab48578... (ok);
      git merge-base --is-ancestor 650be4dfe6d5... 324c9ca7ab98... (ok);
      git merge-base --is-ancestor 324c9ca7ab98... 927fb6a78046... (ok).
  - claim: china_visits consumed china_filings' refresh in the SAME invocation.
    command: >
      gh run view 32460910383 --log --job 96713913690 | grep -E
      "china_visits|china_filings|china_irm" — china_filings returned ok at
      09:29:55.1701Z, china_visits started 09:29:55.1719Z (2.0 ms later) and
      returned ok [0.0s], china_irm followed at 09:29:55.1940Z.
  - claim: All 145 candidates are represented downstream, none silently dropped.
    command: >
      python3 over `git cat-file -p 324c9ca7:data/china_filings/filings.parquet`
      and `...:data/china_visits/visits.parquet`, reproducing the collector's
      filter — 145 candidates, 145 distinct non-falsy announcementIds, 0 falsy,
      145 present in the visit plane, 0 unrepresented, all stamped
      system_recorded_at 2026-08-21T09:29:55.173073+00:00.
  - claim: No next-cycle deferral of this run's own fresh filings.
    command: >
      Same script, diffing against `324c9ca7^` — 72 of the 145 filings are new
      in this run's own store delta and 72/72 are represented; the other 73 are
      the 2026-08-20 bootstrap cohort. Also 72/72 raw keyword matches in the
      2,860-row delta were stored category=institutional_visit (zero classifier
      loss).
  - claim: The product surface is live, honest, and anonymous-visible.
    command: >
      Anonymous headless load of https://www.mastermind-x.com/china_intel.html
      at 1280px and 375px; section text read from the DOM and cropped to
      verify_shots/china_p1_visits_{desktop,mobile}_2026-08-21.png.
do_not_redo:
  - Do not wait for, dispatch, or re-run another asia-close to "confirm" P1 —
    run 32460910383 is the frozen falsifier and it passed. Re-running proves
    nothing and the nightly lanes are never yours to trigger.
  - Do not re-derive the reconciliation from china_visits' own receipts
    (n_candidates, health.json, workflow conclusion, visits.parquet row count).
    All four are consistent with a silent drop — see
    DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP. Reconcile per announcementId
    from the two stores at the collection commit.
  - Do not "fix" the falsy-announcementId drop opportunistically. Sol's
    adjudication forbids widening the implementation in this lane; the repair
    needs its own commission.
  - Do not treat the 480s per-exchange page-budget truncation as a P1 defect.
    It is a frozen upstream design property (3-day re-pull heals the tail) and
    deliberately not a degradation signal.
  - Do not start P1B, L0, R1, R2, P2 or any other China family. There is still
    no bounded L0 builder commission in
    research/china_alpha_intelligence/commissions/ — return to Sol for one.
danger_areas:
  - The Browser pane could not paint (its screenshot path returned blank/stale
    frames because the pane was hidden), and Claude in Chrome was not
    connected. The crops here came from a scratchpad playwright venv driving
    the already-cached chromium anonymously. If a future session sees blank
    crops, that is the pane, not a broken page — check the DOM text first.
  - An orphaned `.mmacc-scrim` node sits on the page with opacity 0 /
    visibility hidden. It is NOT a regwall; china_intel.html is
    anonymous-visible. Do not conclude the dossier is gated from that node's
    presence.
  - This worktree started sparse; verify_shots was materialized with
    `python3 scripts/worktree_sparse.py add verify_shots` before writing the
    crops. Never `git add -A` a data/ or site/ diff from a sparse tree.
  - The p1 wave's next_action is now a very long single-line receipt. Append to
    it; do not reflow or rewrite it, and never replace an immutable SHA with a
    branch-head SHA.
unverified:
  - The 480s per-exchange page budget truncated both exchanges (sse 215/290,
    szse 226/291), so this run's CNInfo page coverage for 2026-08-21 is
    incomplete by design. No claim is made that every visit-class filing
    published that day was fetched — only that every filing that WAS fetched
    became a visit row in the same invocation. The 3-day re-pull is the stated
    healer and was not independently verified here.
  - The `upstream_degraded` path shipped in P1-R1 has never fired in
    production. It is proven by the merged deterministic tests only; this run
    was healthy, so its live behavior is untested.
  - Only the EN rendering of the visits block was cropped. The ZH strings exist
    in the template and were read from the DOM, but no ZH crop was captured.
unresolved:
  - Whether to commission the bounded repair for
    DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP — turning the silent
    falsy-announcementId drop into a typed, counted exclusion surfaced in
    health.json. Sol's adjudication forbade widening the implementation in this
    lane, so it was left alone; it is the one open decision from this proof.
  - L0 still has no bounded builder commission in
    research/china_alpha_intelligence/commissions/. It cannot be improvised;
    Sol owns that commission.
next_actions:
  - Sol reviews the P1 closeout. Nothing in this workstream is authorized to
    start until that review returns — P1B, L0, R1/R2, P2 and every later China
    Alpha wave stay closed.
  - If Sol commissions it, repair the untyped announcementId drop as its own
    bounded change (typed exclusion + counter + health note), with the
    reconciliation TSV shape as the acceptance target.
---

## Why P1 passed on evidence rather than on a clean-looking receipt

The whole point of Sol's strengthened acceptance is that this plane's own
instruments cannot prove the thing being claimed. `n_candidates=145`,
`health.status=ok`, a green workflow, and a 145-row parquet are all *equally*
consistent with a run that dropped candidates or deferred them a cycle — which
is exactly what the 2026-08-20 bootstrap night looked like from the outside
(`0 candidate row(s) this run`, status `ok`, workflow success). So the receipt
is built from the two stores at the immutable collection commit, per
`announcementId`, with the collector's filter reproduced rather than trusted.

The number that actually falsifies the one-cycle latency is not 145. It is
**72/72**: the institutional-visit filings this invocation *itself* fetched, all
of which became visit rows inside the same invocation, 2.0 ms after
`china_filings` returned. The remaining 73 are the bootstrap cohort that
`DSC:CHINA-VISITS-FIRST-CYCLE-ZERO-IS-BOOTSTRAP-NOT-QUIET` predicted would
surface on the next natural run — and 72 + 73 = 145 closes that prediction too.

## The hole that did not fire

`collectors/china_visits.py` filters candidates with
`if f.get("announcementId")` and says nothing when that is false. Zero of the
145 hit it, so the arithmetic is exact — but the reconciliation had to *prove*
that rather than assume it, because no instrument the collector emits would have
shown otherwise. That asymmetry is recorded as a landmine and handed to Sol as
the one open decision, unrepaired, per the adjudication.
