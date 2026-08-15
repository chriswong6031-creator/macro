---
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: prophet-fusion-w2-pr2 (worktree prophet-fusion-w2-pr2-c618eb, branch claude/prophet-fusion-pr2)
model: fable
ended_because: complete
prs: ["#5593", "#5602", "#5604", "#5667", "#PENDING_PR2"]
mission: >
  PR-2 / wave w2: the C2 regularized evidence-family stack + the §5.3 redundancy/
  estimability/CMI plane + the cross-fitted incremental-vs-Prophet harness, under the
  frozen §9.2 fold law — which REFUSES the inferential fit on the 24-date frame. The
  wave's lawful product: the machinery (synthetic-proven, mutation-receipted), the
  descriptive tables, the governed family-grain BH-FDR table (ZERO rejections under
  the t-referenced instrument), and the registry truth repairs (short_int
  pit_settlement with backtest admission DEFERRED; the variance-floor law; sue_z
  deferral). Independent adversarial review: SHIP-WITH-FIXES, 2 BLOCKER + 5 MAJOR +
  5 ADVISORY, all reproduced-then-fixed; disposition table in the wave doc §12.
state_before: >
  PR-1b (#5667) merged 2026-08-14T21:16Z. Graded frame unchanged since the race
  (24 dates 06-15..07-31; H=42/63 zero; no prophet-scored date graded). Candidates
  store: 5 stamps, last curated 2026-08-07. §13.0 closure OPEN at session start; two
  stale pre-merge-head daily runs queued (31756228858, 31753425298); tonight's cron
  run 31848262472 (22:52Z) was superseded/cancelled by sibling 31851452961 (23:45Z),
  pending at handoff time.
changed:
  - path: research/prophet_fusion/families.yml
    what: "short_interest pit_status -> pit_settlement on #5602's merged mechanism,
      with BACKTEST ADMISSION DEFERRED (review F-5: knowable_date is DERIVED at
      settlement + 10 CALENDAR days on every buildable frame, 2-3 days short of the
      ~8-session FINRA publication lag on all 3 committed settlements); variance_floor
      + variance_floor_spec landed (DSC resolution, feature-only, null-semantics-aware,
      as-of-night form explicitly unimplemented -> PR-3); sue_z re-home deferred with
      reason (telemetry columns unstamped)"
  - path: scripts/prophet_fusion_arena.py
    what: "PIT_SETTLEMENT vocabulary + BACKTEST_LAWFUL_STATUSES (= {pit} — the
      pit_settlement admission is deliberately deferred, receipt in the constant's
      comment); gate + pit_columns read the set"
  - path: scripts/prophet_fusion_c2.py
    what: "NEW (~2.9k lines): estimability census (8 families x 55 members, both
      frames, variance axis); §5.3 redundancy matrices; permutation-calibrated
      family-grain CMI; cross-fitted incremental residualization harness (frozen
      fingerprinted residualizer); C2 nonneg elastic-net logistic+linear at family
      grain (scipy L-BFGS-B, RNG-free, registered 9-cell grid, structural family
      budget, first-class missingness); t-referenced p instrument with normal printed
      beside; DESCRIPTIVE_MIN_DATES=8; deterministic report; --selftest (12 stages)"
  - path: research/prophet_fusion/pr2_c2/report.json
    what: "committed machine table: refusals verbatim (0 lawful folds), zero fitted
      coefficients, registered-before-outcomes byte order, no wall-clock,
      byte-identical reruns"
  - path: research/prophet_fusion/PR2_C2_REDUNDANCY.md
    what: "wave doc §0-§12 (incl. the full adversarial-review disposition table) +
      main-loop Adjudication; doc tables machine-checked against report.json by suite"
  - path: tests/test_prophet_fusion_c2.py
    what: "75 tests incl. mutation-receipt pins (8 receipts a-h), PR-1b parity read
      from the sibling report.json at abs 5e-4, doc-table pins, pit-deferral pins"
  - path: tests/test_prophet_fusion_families.py + tests/test_prophet_fusion_arena.py
    what: "pit_settlement vocabulary + deferred-admission pins (both flip on the lag
      reconciliation, deliberately)"
  - path: .github/ci/legacy-jobs.yml
    what: "C2 suite joins the fusion step (same-step law); scipy pinned explicitly in
      the install line; requirements.txt:17 comment names the new consumer"
  - path: agentos (WS record, this handoff, DSC resolution)
    what: "w1b done (#5667) / w2 done on merge; DSC-COVERAGE-FLOOR resolution section;
      owns_paths graduated to research/prophet_fusion/ + scripts/prophet_fusion_*"
verified:
  - claim: the inferential C2 fit and crossfit incremental are REFUSED, nothing fitted
    command: report.json c2_fit.status / incremental.crossfit.status; suite pins
    result: "refused_no_lawful_folds both; §9.2 refusal verbatim; zero
      coefficient-bearing keys (recursive key walk by reviewer and suite); no
      in-sample fallback path exists (pinned)"
  - claim: the governed family table has ZERO rejections under the t instrument
    command: report.json what_does_x_add (n_tests 3, p_t-keyed BH)
    result: "F5 nearest miss (+0.074, p_t .0268, p_adj .0805; serving-lawful
      decomposition +0.052 CI covers 0); F2 null_unresolved (-0.083, CI excl 0,
      p_t .0556, p_adj .0834); F4 null; F1/F3/F7 insufficient_coverage; F6
      structural; F8 not_estimable (vote_inert 0.333)"
  - claim: determinism + reproducibility
    command: CLI x3 (builder) + x3 (commissioning session, independent) + suite
    result: "byte-identical every time incl. vs the committed artifact; no wall-clock;
      seeds registered (bootstrap 20260814 B=2000, CMI 20260818 B=500); C2 path RNG-free"
  - claim: suites green over the full branch
    command: pytest 5 fusion suites; test_us_board_rank.py; audit_unrun_tests; agentos
      validate; check_validated_claims; check_blocklist_drift; run_ci_pack validate
    result: "257 passed (75 c2 + 182 siblings); board-rank 324 passed (live fence);
      audit clean on the rebased tree; agentos 0 errors; claims OK; blocklist OK;
      193 pack jobs validate"
  - claim: mutation receipts bite (8)
    command: builder receipts a-h, re-executed post-fix where affected
    result: "fold-refusal embed / raw-member injection / BH bypass / w>=0 drop /
      serving-dead force-include / variance-floor bypass / t->normal revert /
      design-membership drop — each reds named tests, module restored byte-identical"
  - claim: independent adversarial review ran and every finding is dispositioned
    command: opus reviewer over the branch diff (12-attack commission + 5 claim checks)
    result: "SHIP-WITH-FIXES; F-1/F-2 BLOCKER + F-3..F-7 MAJOR + F-8..F-12 ADVISORY +
      3 nits — ALL fixed (doc §12 table); reviewer verified machinery clean on
      leakage/budget/determinism/fence/signs"
unverified:
  - claim: PR-1a §13.0 live closure — the post-merge nightly stamps a fresh curated date
    what_would_verify: "first post-#5604 daily.yml completion with a post-merge head:
      fresh curated stamp_date > 2026-08-12 in data/us_prophet_rank/candidates, prior
      rows value-identical, Aug 8-13 hole NOT backfilled, staleness warnings quiet,
      real producer path. Check steps are re-creatable: compare origin/main's
      2026-08.parquet against the pre-nightly baseline commit (this PR's part-1
      commit); tonight's live run is 31851452961 (23:45Z cron; the 22:52Z sibling was
      cancelled by concurrency). NOT observable at handoff time — engine job runs
      ~hours; deliberately NOT dispatched (recovery etiquette; prophet_rescue owns)"
unresolved:
  - "short_int knowable-lag reconciliation CHIPPED to the owning lane (task_a85de1cd):
    _SI_KNOWABLE_LAG_DAYS=10 calendar under-waits the ~8-session publication lag;
    engine constant + its false 'deliberately conservative' comment; on landing, flip
    BACKTEST_LAWFUL_STATUSES + the two deliberately-flippable admission tests +
    the families.yml deferral paragraph"
  - "sue_z re-home -> first stamped row carrying it (telemetry stamps begin with the
    first post-#5604 nightly); census train/serve flips from not_yet_measurable then"
  - "known_redundancy_edges: 7/8 unmeasurable (unwired second sides, named); the
    hub-leg row's 'F1..F4' range-in-member-position spec is UNRESOLVABLE and needs a
    registry re-spec"
  - "PR-1a advisories A3 (_safe_out_dir scope) / A4 (dummy stamping) / A5
    (disclosed_gaps fail-open) / A7 (sparse-tree vacuity) remain open, deliberately
    not absorbed into a research PR"
  - "insider panel collector still stopped at 2026q1; name_score two-memories with the
    owning lane; F3 relay 0.000 / theme payload §13.4 repair items unchanged"
next_actions:
  - "PR-3 (wave w3): nightly shadow-scoring lane EXACTLY on the PR-1b prereg (G3, G4,
    C1-as-raced, C1-minus-F2 vs G0/G0'); W2 registers NO new rung and its
    zero-rejection table perturbs nothing. Carry in: as-of-night floor evaluation on
    BOTH axes (presence + variance); the t-referenced p instrument for graded tables;
    §13.0 closure as a precondition for trusting context-vector-fed telemetry"
  - "Verify §13.0 on the first completed post-merge nightly (see unverified)"
  - "C2 fitted read re-enters when the fold law is satisfiable: 91 graded dates needed,
    67 more than held (arithmetic derived through arena.build_folds itself)"
  - "Watch ~2026-08-24: first H=10 grade maturation (unchanged)"
do_not_redo:
  - "Do not fit C2 in-sample on a refused frame — no fallback path exists; adding one
    is the weakened-fit failure the commissioning forbids"
  - "Do not re-tune the variance floor against outcomes — feature-only law; its
    multiplicity lever is disclosed in §7's sensitivity block (zero rejections at
    both F8-p extremes)"
  - "Do not quote the draft's one-rejection F5 table — it was an artifact of the
    normal-approximation p at 15 blocks and exists in no committed artifact; the
    governed instrument is t-referenced and the committed table has ZERO rejections"
  - "Do not treat pit_settlement as backtest-admissible until the knowable-lag
    reconciliation lands — the deferral is fail-closed and its tests flip with it"
  - "Do not treat pit_settlement as depth — 3 settlements; backfill before deep joins"
  - "(inherited) PR-0/PR-1a/PR-1b do_not_redo lists remain binding — see the
    2026-08-14 handoff, which this file supersedes as latest"
danger_areas:
  - "The F5 'nearest miss' decomposes: score-membership (+0.074) leans on the
    serving-dead insider member; serving-lawful is +0.052 with CI covering zero —
    a forward-looking reader (PR-3) reasons from the latter"
  - "At 12-15 date-blocks the normal-approximation p is NOT a neutral convenience
    (it manufactured the draft's only rejection); governed tables carry both
    references, verdicts key on t"
  - "(inherited) G0-replay is not 'what the champion did live'; G4's tie-band;
    payload-less dates leave the deployed cell; era boundaries"
---

Cold-stranger summary: W2 asked whether enough lawful data exists to fit the evidence
families, and the honest answer — refused, 67 more graded dates needed — is the wave's
central result, delivered with the complete machinery to run the fit the day the fold
law is satisfiable. The descriptive plane it lawfully established: 3 families / 4
members are even fit-eligible today; the estate's load-bearing redundancy is within F2
(alpha×off_high +0.436), not across families; and under the governed t-referenced
BH-FDR instrument NO family's incremental-over-Prophet read survives — F5 is the
nearest miss and its serving-lawful form covers zero. An independent adversarial review
(SHIP-WITH-FIXES) forced the p-instrument correction that dissolved the draft's only
rejection, caught the F5 serving-dead lean, and blocked the pit_settlement backtest
admission on a measured under-waiting lag — all dispositioned in the wave doc §12.
Next real evidence arrives from forward accrual: the §13.0 closure, then PR-3's
prospective shadow race on the PR-1b prereg, unchanged.

*Prior sessions of this program (PR-0, PR-1a, PR-1b — all 2026-08-14) are recorded in
`agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-14.md`, which this file
supersedes as the latest record without altering it.*
