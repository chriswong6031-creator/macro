---
workstream: "WS:ALPHA-INTELLIGENCE-INTEGRATION"
session: claude/k3e-src-a1p-audit-records-20260826
model: fable
ended_because: complete
prs: [6413, 6452]
discoveries:
  - "DSC:SRC-A1-DRIP-CURSOR-DEFERS-REVISION-PROOF"
  - "DSC:NIGHTLY-ARTIFACT-ATTRIBUTION-NEEDS-THE-ENGINE-JOB"
  - "DSC:SRC-A1-FISCAL-ANCHOR-IS-ON-THE-PAYLOAD"
mission: >
  Run the SRC-A1P closeout audit on the first natural second collection of the
  K3E prospective expectation lane, decide whether SRC-A1 promotes from
  BUILT_NOT_PROVEN to PROVEN_LIVE, and repair what the audit found — under the
  Fable COO takeover of the K3E program (Chairman commission 2026-08-25).
state_before: >
  SRC-A1 was BUILT_NOT_PROVEN with exactly one natural collection (C1) on
  record. The EVAL-0 activation receipt, a refreshed capability ledger and the
  takeover handoff had merged as PR #6413 (486b844e3ed7). No natural second
  collection existed, so the proof law in handoffs/SRC_A1.md and the ten
  mutation gates in DATA_CLOCK_RIGHTS_MATRIX.md were untested against real
  repeated production behavior.
changed:
  - path: "research/alpha_intelligence/expectation_market_dynamics/CURRENT_CAPABILITY_LEDGER.md"
    what: "Records the SRC-A1P FAIL verdict with per-invariant outcome, the true engine-job attribution for both collections (correcting the 2026-08-25 entry), and a next action sequenced to the natural cursor wrap."
  - path: "agentos/discoveries/DSC-SRC-A1-DRIP-CURSOR-DEFERS-REVISION-PROOF.md"
    what: "Records that consecutive nightly collections are disjoint by design, so a second night cannot prove revision/supersession semantics."
  - path: "agentos/discoveries/DSC-NIGHTLY-ARTIFACT-ATTRIBUTION-NEEDS-THE-ENGINE-JOB.md"
    what: "Records that daily.yml's DST cron pair makes run-level conclusion anti-correlated with having done the work; attribution requires the engine job."
  - path: "agentos/discoveries/DSC-SRC-A1-FISCAL-ANCHOR-IS-ON-THE-PAYLOAD.md"
    what: "Records that the provider's own endDate is present on the fetched payload but discarded by the yfinance accessor, so fiscal rollover is dischargeable without a vendor or authority gate."
  - path: "collectors/equity_revisions.py (PR #6452, merged 2e0234d94b9381b033f4fe7585a75f5da59335ef)"
    what: "Types an empty provider consensus as UNESTIMABLE instead of recording it as an interpretable 0, without downgrading an already-typed reason and without touching genuine provider zeros in covered groups."
  - path: "tests/test_equity_revisions_w2a.py (PR #6452, merged 2e0234d94b9381b033f4fe7585a75f5da59335ef)"
    what: "Six focused mutation-gate-1 tests including the covered-group regression guard and a NOT_APPLICABLE non-downgrade guard."
verified:
  - claim: "A genuine natural second collection exists, produced by a scheduled run whose engine job succeeded, with no manual dispatch inside the proof window."
    command: "git log --oneline origin/main -- data/revisions/expectation_observations.parquet data/revisions/expectation_attempts.parquet; gh api repos/mastermindx-market-intelligence/macro/actions/runs/32908543584/jobs --jq '.jobs[]|select(.name==\"engine\")'; gh run list --workflow daily.yml --limit 20 --json event"
    result: "Two commits (be061c6d49e9, 576959b11804). Run 32908543584 engine job success 2026-08-26T03:27:14Z->06:23:13Z brackets the C2 commit at 06:15:15Z. All runs in the window are event=schedule."
  - claim: "The prior ledger's C1 attribution was wrong: run 32790724676 skipped every job and produced nothing; the true producer is 32786919396."
    command: "gh api repos/mastermindx-market-intelligence/macro/actions/runs/32790724676/jobs --jq '.jobs[]|\"\\(.name) \\(.conclusion)\"' and the same for 32786919396"
    result: "32790724676: engine | skipped (all jobs skipped, run-level success in 6s). 32786919396: engine | success 2026-08-25T03:04:41Z->05:49:32Z, bracketing C1's commit at 05:42:31Z."
  - claim: "Mutation gate 1 is violated in live accrued data: 36 rows across 9 groups record value 0.0 with NULL missingness_reason while the group has zero covering analysts."
    command: "pyarrow read of C2_expectation_observations.parquet extracted from 576959b11804; join each row to its group's covering_analyst_count; filter value==0.0 and missingness_reason isna"
    result: "43 rows have value==0.0 with NULL missingness; 36 of them sit in zero-analyst groups across 9 distinct (ticker, metric, horizon) groups, including BRK-B revenue 0q."
  - claim: "The zeros are the provider's empty-response shape, not company facts."
    command: "groupby provider_payload_hash for tickers COKE and CRVL in the C2 artifact"
    result: "Both unrelated issuers carry the identical hash 0b12d2e2d596cfb8db98e8adf27a2357f489ddb566c73e8b307e254813fa5b9a."
  - claim: "Consecutive collections are disjoint, so the revision/supersession path is unexercised rather than proven."
    command: "per-collection_session_id groupby of ticker_compat and of the (ticker, metric, horizon, observation_type) logical key in the C2 artifact; count of non-null supersedes_observation_id"
    result: "Session 74cfd4a71620 = 200 tickers A->BOH; session d9fa989a6c9e = 199 tickers BOOT->DHI; ticker overlap 0; logical-key overlap 0; 0 of 22,344 rows carry a supersession."
  - claim: "As-known immutability holds: every prior observation survives byte-equal."
    command: "merge C1 and C2 observation frames on observation_id and diff every column"
    result: "11,200 of 11,200 C1 rows present in C2, 0 mutated cells; C2 is a strict superset with 11,144 new rows."
  - claim: "The repair is merged and live on origin/main."
    command: "gh pr merge 6452 --squash --delete-branch; git fetch origin main; git merge-base --is-ancestor 2e0234d94b9381b033f4fe7585a75f5da59335ef origin/main; git show origin/main:collectors/equity_revisions.py | grep -c non_estimable_group"
    result: "PR #6452 MERGED as 2e0234d94b9381b033f4fe7585a75f5da59335ef, confirmed an ancestor of origin/main, and the predicate is present in the file served from main. Exact-head CI concluded 21 pass / 1 fail, the sole failure being the repo-wide by-design ci-authority/codex/merge-queue-pilot."
  - claim: "The shipped repair converts exactly the violating rows and nothing else."
    command: "simulate the final predicate (group covering_analyst_count is null or 0, observation_type is not covering_analyst_count, existing missingness is None) against the real C2 artifact"
    result: "27 rows converted, all value==0.0; 99 already-typed rows preserved (97 NOT_APPLICABLE, 2 UNESTIMABLE); 7 legitimate zeros in covered groups untouched (ALK, AOSL, ARE, CBRL, CNC); 0 non-zero real values discarded. The 36 flagged rows are these 27 plus the 9 covering_analyst_count rows, which the spec deliberately preserves as interpretable."
  - claim: "The cursor wrap that enables a real re-observation is roughly 7.5 nights, not open-ended."
    command: "read collectors/equity_revisions.py:67 and :612-634; count distinct tickers across data/{breadth,midcap_breadth,smallcap_breadth}/constituents.parquet at origin/main"
    result: "_FRESH_DAYS=6, max_new=200 stalest names per night, universe 1,506 (503+400+603) => 7.5-night cycle; A->BOH collected 2026-08-25 becomes re-eligible 2026-08-31, wrap expected on or after 2026-09-01."
unverified:
  - claim: "The wrap-night collection will contain genuine same-security re-observations and exercise the revision path."
    what_would_verify: "Re-run the SRC-A1P audit on the first collection whose per-session ticker set intersects an earlier session's, and assert non-zero supersedes_observation_id lineage plus correct rollover handling."
  - claim: "The provider's endDate is present for names beyond the single issuer probed."
    what_would_verify: "A coverage sweep of endDate presence across the 1,506-name universe; a build must treat an absent endDate as typed UNAVAILABLE and never guess."
unresolved:
  - "SRC-A1 remains BUILT_NOT_PROVEN. Promotion requires a clean wrap-night audit discharging the five currently-unexercised invariants (I2, I3, I5, I7, cross-collection G7), not merely a third disjoint collection."
  - "Fiscal rollover (mutation gate 3) is currently undischargeable in the artifact: period_end, fiscal_period and fiscal_year are 100% null and horizon labels are relative-only, while the lineage key is (ticker, metric, horizon_label_raw, observation_type). The first opportunity to violate it arrives at cursor wrap. Fix is known and lawful — capture the provider's own endDate — but is NOT yet built."
  - "correction_state is state-dependent rather than payload-dependent (original in C1, missing in C2 for identical conditions) and is permanently non-comparable across collections because C1 is lawfully immutable. No evidence is lost; a consumer must read missingness_reason, not correction_state, to detect missing data."
next_actions:
  - "Build the fiscal anchor: capture the provider's item-level endDate into period_end via a guarded private-attribute read that degrades to typed UNAVAILABLE when absent, and make _apply_lineage rollover-aware so a period change is not recorded as an analyst revision. Must land before the cursor wrap on or after 2026-09-01. See DSC:SRC-A1-FISCAL-ANCHOR-IS-ON-THE-PAYLOAD."
  - "At cursor wrap, re-run the full SRC-A1P audit on the first collection containing same-security re-observations; only a clean result promotes SRC-A1 to PROVEN_LIVE."
  - "Only after that promotion plus a fresh collision census may EXP-1 start, as its own bounded PR with a real machine or product consumer."
do_not_redo:
  - "Do not manually dispatch, rerun or cancel daily.yml to manufacture a collection. Natural runs only; the two existing collections are both event=schedule."
  - "Do not widen cadence, batch size, _FRESH_DAYS or universe to force an earlier ticker overlap. That is a mutation the frozen contract gates behind operating evidence, and the natural wrap is only about a week out."
  - "Do not retro-mutate the 36 already-accrued defective rows. The contract forbids hindsight overwrite; they stand as the honest record of what was collected, and the heal changes only future collections."
  - "Do not escalate fiscal rollover as a vendor, rights or authority gate — the anchor is already on the payload the collector fetches."
  - "Do not join EDGAR (data/edgar/eps_quarterly.parquet) or the Nasdaq earnings-date owner (data/earnings/earnings.parquet) to obtain a period end; the former is historical and the latter is a report date, and both add mapping risk the in-payload anchor does not carry."
  - "VEND-0 is complete at SAMPLE_REQUIRED/PROBE_FURTHER; EVAL-0 law is frozen and immutable. Neither is reopened by this audit."
danger_areas:
  - "Attribution: daily.yml's six-second run-level SUCCESS means every job was SKIPPED, while the run that truly built often reports run-level CANCELLED. Always resolve the engine job. This trap reached a merged records PR before it was caught."
  - "A second natural collection looks like proof and is not. Disjoint ticker sets mean accrual and immutability are proven while revision semantics are entirely unexercised."
  - "The G1 discriminator is covering_analyst_count == 0, never value == 0. Keying on the value would destroy 7 legitimate provider zeros in covered groups."
  - "The two SRC-A1 parquet artifacts live under data/, which sparse worktrees omit. Never git add -A an unexpected data/ diff; read historical bodies via git show from the producing commits."
  - "K2-B's merged contract paths and the canonical K3-E Opportunity Evidence Vector lane share this workstream but are separate programs; K3E work touches neither."
---

Fable COO continuation wave under the 2026-08-25 Chairman takeover. The natural
second collection arrived on schedule and was audited against the frozen proof
law rather than accepted because it existed.

The honest result is that it proved less than it appeared to. Accrual, session
lineage, as-known immutability, clock separation and no-backfill are all
genuinely demonstrated on production data. The revision, supersession,
failure-does-not-overwrite and fiscal-rollover behaviors are not — the lane's
freshness cursor guarantees consecutive nights observe disjoint securities, so
the machinery those invariants describe has never run. Recording those five as
NOT_TESTABLE rather than PASS is the difference between a real promotion and a
paper one.

One real defect was found and is being repaired in its own carrier, and one
latent defect (fiscal rollover) was identified before it could fire, with a
lawful in-payload fix and a deadline set by the cursor wrap rather than by
preference.

No escalation to Sol is owed from this wave. The audit exposed defects whose
remedies are fully determined by already-frozen law, and the one question that
looked like an authority gate — whether a fiscal anchor is obtainable from the
free estate — resolved to yes on the provider payload the collector already
fetches.
