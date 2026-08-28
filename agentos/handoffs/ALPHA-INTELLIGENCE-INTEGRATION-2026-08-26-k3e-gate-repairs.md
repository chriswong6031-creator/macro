---
workstream: "WS:ALPHA-INTELLIGENCE-INTEGRATION"
session: claude/k3e-fiscal-anchor-closeout-20260826
model: fable
ended_because: complete
prs: [6452, 6458, 6461]
discoveries:
  - "DSC:SRC-A1-FISCAL-ANCHOR-IS-ON-THE-PAYLOAD"
  - "DSC:NIGHTLY-ARTIFACT-ATTRIBUTION-NEEDS-THE-ENGINE-JOB"
mission: >
  Close out the SRC-A1P audit wave: repair both mutation-gate defects the audit
  exposed before the collection cursor wraps, and leave the program recoverable
  for the wrap-night audit that can finally exercise the revision path.
state_before: >
  The SRC-A1P audit had returned FAIL with one live defect (mutation gate 1,
  empty provider consensus recorded as an interpretable 0) and one latent
  defect identified but unrepaired (mutation gate 3, fiscal rollover
  indistinguishable from an analyst revision because period_end is 100% null
  and the lineage key is relative-horizon only). The audit outcome and three
  discovery records had merged as PR #6458. Neither collector defect was fixed,
  and the first opportunity for gate 3 to fire is the cursor wrap on or after
  2026-09-01.
changed:
  - path: "collectors/equity_revisions.py (PR #6452, merged 2e0234d94b9381b033f4fe7585a75f5da59335ef)"
    what: "Gate 1 repaired: a group whose covering-analyst count is 0 or unavailable emits typed UNESTIMABLE for any present value, without downgrading an already-typed reason and without touching genuine provider zeros in covered groups."
  - path: "collectors/equity_revisions.py (PR #6461, merged 8a0dc256c0b9275e8376b6c2d70c79ab769282de)"
    what: "Gate 3 repaired: captures Yahoo's per-item endDate into the schema's existing period_end field via a fully guarded private-attribute read, and adds a rollover guard so a differing period_end leaves the row a new original instead of a fabricated supersession."
  - path: "tests/test_equity_revisions_w2a.py (PRs #6452 and #6461)"
    what: "Sixteen new synthetic tests across both repairs, including the covered-group zero regression guard, the NOT_APPLICABLE non-downgrade guard, the gate-3 rollover test, the genuine-revision test, and an anchor-extraction-failure test."
  - path: "research/alpha_intelligence/expectation_market_dynamics/CURRENT_CAPABILITY_LEDGER.md"
    what: "Records both repairs as merged, adds the sibling-session collision row, and reduces the next action to the wrap-night audit alone."
  - path: "agentos/discoveries/DSC-NIGHTLY-ARTIFACT-ATTRIBUTION-NEEDS-THE-ENGINE-JOB.md"
    what: "Amended with the strictly stronger cryptographic attribution method and its verification table."
verified:
  - claim: "Both collector repairs are merged and live on origin/main."
    command: "git merge-base --is-ancestor 2e0234d94b9381b033f4fe7585a75f5da59335ef origin/main; git merge-base --is-ancestor 8a0dc256c0b9275e8376b6c2d70c79ab769282de origin/main; git show origin/main:collectors/equity_revisions.py | grep -c 'non_estimable_group'; git show origin/main:collectors/equity_revisions.py | grep -c '_period_end_anchors\\|period_end_by_horizon'"
    result: "Both SHAs are ancestors of origin/main; the file served from main carries 3 non_estimable_group references and 8 fiscal-anchor references."
  - claim: "The gate-1 repair converts exactly the violating rows and spares every legitimate provider zero."
    command: "simulate the merged predicate against the real C2 artifact extracted from 576959b11804"
    result: "27 rows converted, all value==0.0; 99 already-typed rows preserved (97 NOT_APPLICABLE, 2 UNESTIMABLE); 7 legitimate zeros in covered groups untouched (ALK, AOSL, ARE, CBRL, CNC); 0 non-zero real values discarded."
  - claim: "The fiscal-anchor extraction is functional against the real yfinance shape and is not a silent no-op."
    command: "read yfinance base.py:116 and :329 for the _analysis holder, scrapers/analysis.py:31-32 for side-effect population and :200 for the list-of-dicts shape; then run the merged _raw_earnings_trend_items and _period_end_anchors against that exact shape plus four failure modes"
    result: "Returns {'0q': '2026-09-30', '+1q': '2026-12-31', '0y': '2026-09-30', '+1y': '2027-09-30'}, matching the values observed live on AAPL whose September fiscal year end confirms these are true fiscal period ends. Empty list, absent attribute, raising property and an item lacking endDate all degrade to {} without raising."
  - claim: "The corrected run attribution is provable from the artifact body, not merely inferred from job timing."
    command: "recompute sha256(json([\"src-a1\",\"yfinance\",[\"github_run\",<run_id>]], separators, sort_keys)) for each candidate run and compare to the collection_session_id values in the artifact"
    result: "32786919396 -> 74cfd4a7162056b1... equals C1's session id; 32908543584 -> d9fa989a6c9e3b82... equals C2's session id; both skip-twin runs (32790724676, 32912351235) hash to values absent from the data."
  - claim: "The protected Sol Skillpack did not change between this program's bootstrap pin and the current protected master."
    command: "git diff --name-only 51f9942733b86e550bb9169d2a43462bd28e774f 5f9eca71ad21355b56da2a3c68fa5b61b3f4204a -- docs/sol_skills/ | wc -l"
    result: "0 — protected master advanced but docs/sol_skills/ is byte-identical, so no source-law movement affects this program's bootstrap."
unverified:
  - claim: "The endDate anchor is present for names beyond the single issuer probed live."
    what_would_verify: "A coverage sweep of endDate presence across the 1,506-name universe, or simply reading period_end coverage in the first post-repair collection. The implementation treats an absent anchor as no anchor, so low coverage degrades gate-3 discharge rather than breaking anything."
  - claim: "The first post-repair collection is gate-1 clean and carries populated period_end values."
    what_would_verify: "Re-run the zero-substitution and period_end coverage checks against the next natural engine commit touching data/revisions/expectation_observations.parquet."
unresolved:
  - "SRC-A1 remains BUILT_NOT_PROVEN. Five proof-law invariants stay unexercised until a collection contains genuine same-security re-observations; the cursor wrap is expected on or after 2026-09-01."
  - "PR #6469, a parallel session's records carrier for the same C1-to-C2 audit, is open and was branched before #6458 merged, so its CURRENT_CAPABILITY_LEDGER.md copy predates the merged content. It was fenced with a cross-comment asking for a rebase to superset rather than closed. Its SRC_A1_C1C2_NATURAL_AUDIT_2026-08-26.md receipt is additive and belongs on main."
  - "correction_state remains state-dependent rather than payload-dependent and is not enumerated by the contract. Untouched by this wave deliberately; a consumer must read missingness_reason, not correction_state, to detect missing data."
next_actions:
  - "Observe (never dispatch) the next natural engine-bearing collection and confirm it is gate-1 clean and that period_end is populated where the provider supplies an anchor."
  - "At cursor wrap, expected on or after 2026-09-01, re-run the full SRC-A1P audit on the first collection containing genuine same-security re-observations, testing the five currently-unexercised invariants: unchanged values not fabricating revisions, changed payloads appending and superseding with explicit lineage, failure and null states not overwriting good prior evidence, fiscal rollover not misclassified as a revision, and cross-collection horizon stability."
  - "Only a clean wrap-night audit promotes SRC-A1 to PROVEN_LIVE; then a fresh collision census, then EXP-1 as its own bounded PR with a real machine or product consumer."
do_not_redo:
  - "Do not manually dispatch, rerun or cancel daily.yml to manufacture a collection. Natural runs only."
  - "Do not widen cadence, batch size, _FRESH_DAYS or universe to force an earlier ticker overlap. That is a mutation the frozen contract gates behind operating evidence."
  - "Do not populate fiscal_period or fiscal_year from endDate. That derivation is inference and the contract forbids guessed fiscal mapping; period_end alone discharges gate 3."
  - "Do not add period_end to _apply_lineage's key_columns. A null-vs-null equality there silently breaks lineage for every unanchored row; the rollover guard is deliberately a separate explicit check."
  - "Do not retro-mutate the already-accrued defective rows. The contract forbids hindsight overwrite; the repairs change only future collections."
  - "Do not re-audit C1 versus C2 for revision semantics. The pair is disjoint by construction and the question is not answerable from it."
danger_areas:
  - "The fiscal anchor reads a PRIVATE yfinance attribute. Its failure mode is a silent no-op: a wrong path degrades to no anchor, leaving gate 3 open while appearing fixed, and no test catches it because tests supply their own stubs. If yfinance is upgraded, re-verify against scrapers/analysis.py that _earnings_trend is still populated as a side effect of the estimate accessors and is still a list of dicts carrying endDate."
  - "Attribution: prefer the collection_session_id hash recomputation over Actions API archaeology. daily.yml's six-second run-level SUCCESS means every job was SKIPPED."
  - "A second natural collection looks like proof and is not, whenever the ticker sets are disjoint."
  - "The G1 discriminator is covering_analyst_count == 0, never value == 0."
  - "The SRC-A1 parquet artifacts live under data/, which sparse worktrees omit. Never git add -A an unexpected data/ diff; read historical bodies via git show."
---

Repair wave closing the SRC-A1P audit. Both mutation-gate defects the audit
exposed are now repaired and live on main, ahead of the cursor wrap that will
first exercise the revision path.

Gate 1 was a live defect in accrued data. Gate 3 was latent — never yet fired,
because no security has been observed twice — and was fixed on the strength of
an investigation showing the provider already supplies the anchor the schema
reserves. Both repairs were validated against the real production artifact
rather than against their own tests: the gate-1 predicate was simulated over
the C2 parquet to confirm it converts exactly the 27 defective rows and spares
the 7 legitimate provider zeros, and the gate-3 extractor was run against the
real yfinance payload shape read out of the installed package source, because
its failure mode is a silent no-op that a passing test suite cannot detect.

No escalation to Sol is owed. Both remedies were fully determined by
already-frozen contract law, the one question that resembled an authority gate
resolved to a provider fact already on the fetched payload, protected master
moved without changing the Skillpack, and the one active collision was
reconciled by cross-comment rather than adjudication.
