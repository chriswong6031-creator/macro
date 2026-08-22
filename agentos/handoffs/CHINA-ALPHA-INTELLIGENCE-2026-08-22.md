---
workstream: WS:CHINA-ALPHA-INTELLIGENCE
session: claude/p1-r2-announcement-id-integrity
model: opus
ended_because: complete
prs: [6229]
decisions: [DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION]
discoveries: [DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP]
mission: >
  Execute Sol's 2026-08-22 commission "P1-R2 — ANNOUNCEMENT-ID INTEGRITY": make it
  impossible for a missing/blank/NaN/whitespace announcementId to be silently
  deduplicated, discarded, or converted into clean absence authority, at BOTH the
  collectors/china_filings.py write boundary and the collectors/china_visits.py
  candidate boundary. Bounded scope: those two collectors, their directly owning
  tests, and minimal Agent OS reconciliation. Sol's dictated post-merge state:
  "PARTIAL / normal-path PROVEN_LIVE, malformed-key repair BUILT_NOT_PROVEN".
state_before: >
  P1 was accepted DONE / PROVEN_LIVE on 2026-08-21 (Sol P1 NATURAL-RUN ADJUDICATION,
  closeout PR #6215, squash f156b073414a37eed006b6aee86d8ce3054946d1) on natural
  asia-close run 32460910383 with an exact 145-candidate reconciliation. That
  acceptance rested on POSITIVE evidence — 145 of 145 candidates carried a distinct
  non-falsy announcementId — not on the absence of a hole. The hole itself was named
  and deliberately left unrepaired in that session because Sol's adjudication said
  "Do not independently widen the implementation", and was recorded as
  DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP pending its own commission. Two
  silent-drop shapes existed: china_filings.write_filings() ran
  drop_duplicates(subset=["announcementId"]), and pandas treats N rows sharing ""
  as duplicates of EACH OTHER, so N malformed rows collapsed into ONE with no
  counter; china_visits.refresh() used a bare comprehension
  `[_derive_row(f, ts) for f in candidates if f.get("announcementId")]` with no typed
  exclusion, no counter and no health note, while n_candidates kept counting the
  PRE-filter list.
changed:
  - path: collectors/china_filings.py
    what: >
      Added the pure, never-raising key predicate the whole repair rests on —
      key_anomaly() (returns one of the frozen names missing/nan/empty/whitespace,
      or None), normalize_announcement_id(), partition_by_key_integrity(). Added the
      process-local LAST_KEY_INTEGRITY global (never persisted, reset fail-closed at
      fetch() entry, canonical shape excluded_total/excluded_by_type/
      preexisting_unkeyed/at). write_filings() now partitions new_rows on that
      predicate BEFORE any dedup, so malformed rows are a typed COUNTED exclusion
      instead of a drop_duplicates collapse; splits the ACCRUED store with a
      vectorized mask and writes any pre-existing unkeyed row back VERBATIM, never
      subjecting it to the keyed dedup; computes net_new off the keyed frames only;
      and goes loud via log.error plus a bare line-start
      ::warning GitHub annotation. _parse_announcement() now leaves an absent
      announcementId as None ("missing") instead of flattening it to "" ("empty").
      fetch() folds LAST_KEY_INTEGRITY into LAST_RUN_OUTCOME["key_integrity"] on
      both exit paths and appends a typed errors[] entry so ok degrades to False —
      without touching the single raise condition, so the Asia lane stays fail-soft.
  - path: collectors/china_visits.py
    what: >
      account_candidates() replaces the bare comprehension with an explicit typed
      split using the SAME key_anomaly predicate imported from china_filings (never
      re-derived here, so the two boundaries cannot silently diverge); it also
      returns up to 5 excluded_identities formatted sec_code|publish_ts|title[:60],
      log/annotation only, because an excluded row has no announcementId to name it
      by. refresh() mechanically verifies `represented + typed_exclusions ==
      eligible` as an explicit branch and refuses to write anything on a mismatch.
      The collectors.china_filings import that supplies the predicate is now
      fail-closed (import failure degrades to source_failure instead of deriving
      blind). Typed exclusions type the run "upstream_degraded" with success=False,
      and when a degraded same-run china_filings outcome fires too, ONE record's
      detail names BOTH causes distinctly. _write_health() gained an optional
      keyword-only accounting param persisted as an additive candidate_accounting
      field, written on the clean path as well as the degraded one. refresh()'s
      return dict keeps status/n_candidates/n_new and adds n_represented/
      n_excluded/exclusions.
  - path: tests/test_china_filings_collector.py
    what: >
      Added TestKeyAnomaly (18 cases), TestNormalizeAnnouncementId,
      TestPartitionByKeyIntegrity, TestWriteFilingsKeyIntegrity and
      TestKeyIntegrityMutationGuard — covering every value in Sol's hostile list
      plus pre-existing-unkeyed preservation and a mutation guard proving the
      exclusion depends on the real predicate rather than on the test's own logic.
  - path: tests/test_china_visits_collector.py
    what: >
      Added TestAccountCandidates, TestRefreshKeyIntegrity,
      TestMeasuredAbsenceCannotAdvance, TestAccountingMutationGuard and
      TestVisitBlockUpstreamDegradedP1R2 — including a keyless institutional-visit
      row already present in the filings store (proving the visits boundary defends
      independently of china_filings), valid rows preserved beside malformed ones,
      lane-survives-health-loud, and the dossier reading "stale" rather than
      "measured_no_event" end to end.
  - path: agentos/decisions/DEC-CHINA-KEY-INTEGRITY-TYPED-EXCLUSION.md
    what: >
      New. Records why one shared predicate owned by the natural-key module, why a
      typed exclusion rather than a silent drop or a keyless append, and the three
      rejected alternatives — a fallback composite key (forbidden new identity
      system), an unbounded keyless append, and a fifth _HEALTH_STATES value.
  - path: agentos/discoveries/DSC-CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP.md
    what: >
      Appended a "REPAIRED BY P1-R2" body paragraph naming what changed at both
      boundaries. Frontmatter claim/falsifier/so_what deliberately untouched — they
      record what was true when the discovery was verified.
  - path: agentos/workstreams/WS-CHINA-ALPHA-INTELLIGENCE.md
    what: >
      Added the p1r2 wave (status in_progress, depends_on [p1]) carrying Sol's
      dictated post-merge state verbatim and the standing gate. The existing p1
      wave is untouched — it is a Sol-accepted receipt.
verified:
  - claim: The malformed-announcementId path has fired ZERO times in production, so
      this is a rare-branch repair proven by hostile fixtures rather than by a
      naturally occurring malformed row.
    command: >
      git cat-file -p origin/main:data/china_filings/filings.parquet piped into
      pandas.read_parquet, then counting isna() and the non-na rows whose
      astype("string").str.strip() == "" (scratchpad census_keys.py)
    result: >
      54,078 rows; 0 NaN/None; 0 empty-or-whitespace; 54,078 distinct keys, i.e.
      one distinct key per row.
  - claim: The two owning test files are fully green after the repair.
    command: python3 -m pytest tests/test_china_visits_collector.py tests/test_china_filings_collector.py -q
    result: 183 passed, 3 warnings in 34.96s
  - claim: The surfaces that guard or consume the touched code did not regress.
    command: python3 -m pytest tests/test_china_intel_hub_visits.py tests/test_nightly_timings.py tests/test_gh_annotation_line_start.py -q
    result: 66 passed, 3 warnings
  - claim: The Agent OS store still validates with the three new/edited records.
    command: python3 scripts/agentos.py validate
    result: >
      517 records (44 workstreams, 167 decisions, 140 discoveries, 166 handoffs) —
      0 error(s), 26 warning(s), all 26 pre-existing on unrelated records.
  - claim: Splitting the accrued store with a vectorized mask is ~45x cheaper than
      the to_dict("records") round-trip and preserves every column dtype, which is
      why write_filings() uses the mask.
    command: >
      scratchpad bench_partition.py — reads the real 54,078-row store from
      origin/main via git cat-file, times partition_by_key_integrity(
      existing.to_dict("records")) against existing["announcementId"].map(
      key_anomaly).notna(), and diffs the resulting dtypes against the original
    result: >
      0.55s vs 0.01s (~45x); DTYPES CHANGED: none for both paths; both produce
      keyed=54078 unkeyed=0.
  - claim: engine/china_intel_hub.py was read but never edited, as the commission
      required.
    command: git status --short && git diff origin/main --stat
    result: >
      Only the seven commissioned files plus this handoff appear; china_intel_hub.py
      is absent from the diff.
  - claim: No production module outside china_filings itself calls the changed
      write path, so the blast radius is contained to this collector pair.
    command: grep -rn "write_filings\|_parse_announcement\|china_filings.load_filings" --include="*.py" . filtered to exclude collectors/china_filings.py and its own test
    result: >
      Only collectors/china_visits.py (in prose comments) and test files; no other
      production caller.
unverified:
  - claim: The repair behaves correctly in the live Asia-close lane (deployment / no
      regression on the normal, well-keyed path).
    what_would_verify: >
      The next natural asia-close.yml run containing this merge: confirm the `asia`
      JOB conclusion is success (not merely the run — early cron slots conclude
      run-success with the asia job SKIPPED), that china_filings -> china_visits
      still run back to back in the same invocation with china_visits at ~0.0s and
      zero network, that data/china_visits/health.json reads status ok with the new
      candidate_accounting field present and eligible == represented_downstream,
      and that LAST_RUN_OUTCOME carried key_integrity with excluded_total 0. This is
      the ONLY remaining P1-R2 proof lane, and Sol scoped it explicitly to
      deployment/no-regression — a naturally occurring malformed ID is NOT required.
  - claim: The malformed-key branch itself behaves correctly in production.
    what_would_verify: >
      A real CNInfo payload carrying a malformed announcementId. It has never
      happened (0 of 54,078 rows), so this branch is proven ONLY by the hostile
      fixtures and stays BUILT_NOT_PROVEN indefinitely. Do not wait for it and do
      not manufacture one.
unresolved:
  - >
      A permanent-degradation property that Sol should rule on. Requirement 6 is
      implemented literally and fail-closed: ANY run whose accounting carries a
      typed exclusion writes upstream_degraded and does not advance
      last_success_utc. Because china_filings now PRESERVES a pre-existing unkeyed
      row in the accrued store verbatim (rather than discarding it), a single
      historical malformed institutional_visit row would make china_visits report a
      typed exclusion on EVERY subsequent night, freezing absence authority for the
      whole plane until the store is repaired by hand. That is honest and
      fail-closed, and it cannot fire today (0 malformed rows in 54,078), but it is
      a blunt instrument: one bad upstream row would suppress measured_no_event for
      every A-share name. The alternative — distinguishing "this run encountered a
      malformed key" from "the store contains a historical malformed row" and
      degrading only on the former — was NOT built, because Sol's requirement 6
      names malformed-key CONDITIONS without that split and self-excusing a
      standing condition is exactly the shape this repair exists to prevent.
  - >
      collectors/china_filings.py's write_filings() still calls load_filings(),
      which SWALLOWS a read error and returns an empty frame — so an unreadable
      accrued store causes the next write to REPLACE the whole tape with just
      tonight's batch. This is pre-existing behavior, unchanged by P1-R2, and out of
      this commission's scope. collectors/china_visits.py already solved the same
      problem with _read_store_strict() + an explicit ABORT; china_filings has no
      equivalent. It needs its own commission.
next_actions:
  - >
      Report the merged P1-R2 exact head to Sol for review, with the reconciliation
      of what was and was not proven, and the two unresolved items above.
  - >
      On the first natural asia-close.yml run containing this merge, execute the
      deployment/no-regression proof described in the first `unverified` entry.
      Nothing else about P1-R2 is pending.
  - >
      Await Sol's ruling on the permanent-degradation property before changing any
      degradation semantics. Do not soften requirement 6 unilaterally.
do_not_redo:
  - >
      Do NOT re-run or re-derive the P1 145-candidate reconciliation. Sol accepted
      it on 2026-08-21 and explicitly ruled "Do not rerun P1 and do not alter the
      145-row receipt". The receipt is
      research/china_alpha_intelligence/receipts/P1_NATURAL_RUN_RECEIPT_2026-08-21.md
      plus p1_candidate_reconciliation_2026-08-21.tsv.
  - >
      Do NOT add a fifth _HEALTH_STATES value for malformed keys. It was evaluated
      and rejected: engine/china_intel_hub.py's _visit_block() diverts a no-rows
      name away from measured_no_event on the LITERAL string "upstream_degraded"
      only, so a new state falls through that check and renders a degraded run as a
      clean measured absence — the exact silent conversion this repair exists to
      prevent. See DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION.
  - >
      Do NOT mint a fallback/composite announcement id (sec_code+title+date or
      anything similar) for a malformed row, and do NOT append malformed rows to the
      store keyless. The first is a forbidden second identity plane; the second
      grows the store unbounded because the same malformed source row reappears in
      every 3-day re-pull with nothing to dedup against.
  - >
      Do NOT edit engine/china_intel_hub.py to accommodate this repair. The repair
      was deliberately designed to need zero hub changes, and the hub is out of
      scope for the commission.
  - >
      Do NOT start P1B, L0, R1/R2, P2 or any other China Alpha Intelligence family.
      Sol's gate is standing and was restated in this commission. L0 in particular
      still has no bounded builder commission in
      research/china_alpha_intelligence/commissions/ — it must come from Sol, never
      be improvised.
danger_areas:
  - >
      write_filings() REWRITES the entire accrued production parquet on every
      nightly call (54,078 rows today, growing ~2,860/night). Any change to the
      existing_keyed / existing_unkeyed split, the concat order, or the sort is a
      data-loss risk on the whole tape, not just on tonight's batch. The split is
      deliberately a boolean mask over the ORIGINAL frame rather than a
      to_dict("records") round-trip, both for cost and so the frame's own dtypes and
      column order survive untouched.
  - >
      key_anomaly() must NEVER raise, for any input, because it runs inside the C0
      market-critical Asia lane on every row. Two ordering facts are load-bearing:
      the NaN check must run BEFORE any str() coercion (str(float('nan')) == 'nan',
      which would read as a well-formed key), and pd.isna() must be wrapped because
      it returns an ARRAY for list/array-like input whose truth value raises
      ValueError. Never rewrite this function to use a plain `if value:` truth test —
      bool(pd.NA) raises.
  - >
      The mechanical accounting identity in refresh() must stay an explicit `if`
      branch. A bare assert is stripped under python -O, and an AssertionError raised
      inside refresh()'s own broad `except Exception` would be caught and degraded to
      an indistinguishable generic source_failure.
  - >
      The GitHub annotations in both collectors must stay BARE line-start print()
      calls with flush=True. Routing one through the logger prefixes the line, and
      GitHub silently drops it — the call reviews as an alarm, runs clean, and
      produces nothing. Guarded by tests/test_gh_annotation_line_start.py.
  - >
      This worktree is SPARSE: data/, site/, mockups/ and verify_shots/ are absent.
      Never `git add -A` here, and never run the full pytest suite (it yields ~1,700
      artifact failures that mean nothing). Read store bytes with
      `git cat-file -p <rev>:<path>` into an io.BytesIO rather than materializing
      them.
---

## Why this repair was worth building for a branch that has never fired

Every instrument this plane owns was consistent with a silent drop. `n_candidates`
counted the pre-filter list, `health.json` read `ok`, the workflow concluded
success, and the aggregate row count looked right — a run that dropped k eligible
filings printed exactly the same shape as a run that dropped none. That is why the
2026-08-21 P1 acceptance had to be reconciled per-announcementId from the two
stores at the immutable collection commit: the collector's own receipts could not
answer the question. After P1-R2 they can. `health.json` now carries
`candidate_accounting` with `eligible`, `represented_downstream`, `typed_exclusions`
and `exclusions_by_type` on the clean path as well as the degraded one, so the
identity `represented_downstream + typed_exclusions == eligible` is auditable from
the receipt itself. That is the concrete thing this change bought, and it is worth
more than the rare branch it also closes.

## The one design hinge

Reusing `upstream_degraded` instead of minting a new health state is not a
shortcut, it is the correctness requirement. `engine/china_intel_hub.py`'s
`_visit_block()` sends a no-rows name to `stale` only when the status matches that
literal string; every unrecognized status falls through to the `measured_no_event`
branch. A state named for key integrity would therefore have rendered a degraded
run as a clean, honest-looking "no visit filings for this company" — the precise
failure this repair exists to prevent, reintroduced by the repair itself. The hub
was read to establish this and deliberately left unedited.
