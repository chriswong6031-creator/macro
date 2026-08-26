# K3E Current Capability Ledger

Date pinned: 2026-08-26
Macro `origin/main` observed at pin time: `fe84261a206e`
(main advances continuously — live GitHub evidence outranks this pin for later
collision checks)
Protected Mastermind `origin/master`: `51f9942733b86e550bb9169d2a43462bd28e774f`
Protected Sol Skillpack schema/version/minimum bootstrap:
`mastermind.sol_skillpack.v1` / `1.0.0` / `1`
Skillpack `INDEX.md` and skills loaded from that same protected SHA.

Supersedes the 2026-08-25 revision, which predated the second natural
collection and its audit.

## Program state

| capability | current state | evidence / note |
|---|---|---|
| K3E-0 architecture freeze | `SPEC_ONLY` (accepted, binding) | Merged PR `#6329`, merge `2a90b59423b567071f5b10d9e5ec29ee9397ed79`; freeze and both DEC records untouched since 2026-08-23 |
| SRC-A1 prospective expectation accrual | **`BUILT_NOT_PROVEN`** — audited, one named defect, core semantics unexercised | Implementation merged PR `#6342`, merge `dc51502ba1b0e5304537ab504d3708028c96afc6`. Two natural collections exist (C1, C2 below). The 2026-08-26 SRC-A1P audit returned **FAIL**: mutation gate 1 violated in live data, and five proof-law invariants structurally unexercised. Does NOT promote. See "SRC-A1P audit outcome" |
| VEND-0 vendor bake-off | research complete (`SAMPLE_REQUIRED / PROBE_FURTHER`) | Merged PR `#6339`, merge `f53f8e77b360ae0b1c413c2e9e666ebedfa30fa0`. No winner, rights clearance, trial, or sample proof. Vendor contact/procurement requires separate current Chairman authorization. Does not block a lawful free-estate EXP-1 |
| EVAL-0 evaluation preregistration | frozen (`SPEC_ONLY`, immutable) | Merged PR `#6341`, merge `8185690d04dd96f871fa4858c6352ff2a95880eb`, registration `K3E-EVAL-0-V1`, canonical digest `986ec117e8517b77e8dece565fd9d9dc169e758beb9d1619acc443e061ef87fd`. Activation receipt merged PR `#6413`, merge `486b844e3ed700ae920e69b0cf1aabf6f49afeb1`; boundary resolved 2026-08-24 |
| EXP-1 expectation surface | `NOT_BUILT` | Gated on SRC-A1 `PROVEN_LIVE` + fresh collision census. Gate NOT satisfied |
| MKT-1 market-response surface | `NOT_BUILT` | Gated on EXP-1 acceptance; must reuse existing price/residual/options owners |
| CPL-1 coupling / lag / disagreement | `NOT_BUILT` | Gated on EXP-1 + MKT-1 |
| PHASE-1 descriptive phase projection | `NOT_BUILT` | Gated on CPL-1; components stay visible, no collapsed scalar |
| MAS-118 family-specific incorporation science | separate owner program | Fence unchanged; K3E advance does not complete it |
| MAS-119 cross-domain `ExpectationBaseline` federation | separate owner program | Fence unchanged; K3E advance does not complete it |

## Natural collections and their true producing runs

Attribution is by the **`engine` job**, never by run-level conclusion
(`DSC:NIGHTLY-ARTIFACT-ATTRIBUTION-NEEDS-THE-ENGINE-JOB`). This CORRECTS the
2026-08-25 ledger, which named run `32790724676` as C1's producer; that run
reported run-level `success` in six seconds with `engine | completed/skipped`
and produced nothing.

| collection | producing run (`event: schedule`) | `engine` job | commit | artifact sizes |
|---|---|---|---|---|
| C1 | `32786919396` (run-level `cancelled` from a later job) | **success** 2026-08-25T03:04:41Z → 05:49:32Z | `be061c6d49e9b9e40cea5b01b9b7b9acacdc757a` @ 05:42:31Z | obs 868,471 B / att 42,701 B |
| C2 | `32908543584` | **success** 2026-08-26T03:27:14Z → 06:23:13Z | `576959b11804d4d7a0b0f19d443b232234c00ce7` @ 06:15:15Z | obs 1,703,859 B / att 76,089 B |

Neither was manually dispatched; no `workflow_dispatch` run of `daily.yml`
occurred inside the proof window.

Run attribution is additionally proven at body level: each collection's
`collection_session_id` equals the collector's deterministic
`sha256(json(["src-a1","yfinance",["github_run","<run id>"]]))` preimage for
its producing run — C1 `74cfd4a71620…` = H(`32786919396`), C2 `d9fa989a6c9e…`
= H(`32908543584`), recomputed exactly (independent verification receipt,
`SRC_A1_C1C2_INDEPENDENT_VERIFICATION_2026-08-26.md`). A row minted outside
the real scheduled run cannot carry that session id.

## SRC-A1P audit outcome (2026-08-26) — verdict FAIL

True counts: C1 = 11,200 observations / 200 attempts (199 `success`, 1 honest
`partial`). C2 file = 22,344 observations / 400 attempts, being C1 retained in
full plus 11,144 new rows from a second session (197 `success`, 2 `partial`,
1 `null`).

**PASS (7):** own session/attempt lineage per collection; all 11,200 prior
observations retained byte-equal across all 30 columns with C2 a strict
superset; explicit correction lineage with zero orphans; clocks distinct on
every row (`system_observed_at == provider_observed_at` on 0 of 22,344);
no backfill into an earlier cutoff (strict monotone clock separation);
provider horizons not collapsed within a collection (exactly 4 per group for
all 798 groups); analyst counts not substituted by reviser counts; publication
data-consistent with the scheduler path (24 h 22 m spacing).

**FAIL (1) — mutation gate 1, "missing value becoming `0`":** 36 rows across 9
`(ticker, metric, horizon)` groups carry `value == 0.0` with NULL
`missingness_reason` while the group's `covering_analyst_count` is 0.
`BRK-B` revenue `0q` records Berkshire's current-quarter revenue consensus as
$0.00, flagged interpretable. `COKE` and `CRVL` — unrelated issuers — share a
byte-identical `provider_payload_hash`, proving the empty-response shape.
**Healed** for future collections by merged PR `#6452`, merge
`2e0234d94b9381b033f4fe7585a75f5da59335ef`: a group whose covering-analyst
count is 0 or unavailable now emits typed `UNESTIMABLE` for any present value,
without downgrading an already-typed reason and without touching genuine
provider zeros in covered groups. The 36 already-accrued rows are NOT
retro-mutated — the contract forbids hindsight overwrite, so they stand as the
honest record of what was collected.

**NOT_TESTABLE (5) — the structural finding:** C1 covered `A`→`BOH`, C2 covered
`BOOT`→`DHI`; per-session ticker overlap **0**, logical-key overlap **0**. The
lane drips the 200 stalest names nightly over a 1,506-name universe with
`_FRESH_DAYS = 6`, so consecutive nights are disjoint by design and the
revision/supersession machinery has never fired (0 of 22,344 rows carry a
supersession). Unchanged-values-do-not-fabricate-revisions,
changed-payloads-append/supersede, failures-do-not-overwrite, fiscal-rollover,
and cross-collection horizon stability remain **unexercised, not satisfied**
(`DSC:SRC-A1-DRIP-CURSOR-DEFERS-REVISION-PROOF`).

**Independent concurrence:** a parallel Fable COO session executed the same
audit independently on the same pair (19-condition sheet, null-safe body
comparison, frozen gate suite 30/30 at current main) and reached the identical
verdict — FAIL on mutation gate 1 alone, all other exercisable conditions PASS,
same 9 violation groups (row-count difference is counting-net only: 27
non-count interpretable-value rows vs 36 total zero-value rows). Receipt:
`SRC_A1_C1C2_INDEPENDENT_VERIFICATION_2026-08-26.md`.

**Non-blocking observations:** `correction_state` is state-dependent rather than
payload-dependent (`original` in C1, `missing` in C2 for identical data
conditions), permanently non-comparable across collections because C1 is
lawfully immutable; no evidence is lost since `missingness_reason` carries the
truth. Two of five contract clocks (`source_effective_at`,
`source_published_at`) are 100% null and will stay so for this provider, so
revision timing is measurable only at collector resolution — lawful, and
decision-relevant for EXP-1.

## Live adjacent lanes (observed 2026-08-26)

| lane | state | why it matters here |
|---|---|---|
| PR `#6452` zero-substitution heal | merged `2e0234d94b93` | This program's carrier for the gate-1 defect; live on main |
| PR `#6461` fiscal-anchor / rollover fence | OPEN (`collectors/equity_revisions.py` + tests only) | The in-flight carrier for "Next action" step 2: captures the provider's `endDate` into `period_end` before cursor wrap can fire mutation gate 3 |
| K2-B institutional manager intent (PR `#6370`) | merged 2026-08-24T17:53:03Z | Same parent workstream; its contract paths are owned on main, not in flight — do not touch from K3E lanes |
| sibling worktree `alpha-k3e-evidence-vector-855c3a` | branch at main tip, no commits, no PR | Canonical K3-E Opportunity Evidence Vector — a distinct program per the K3E-0 naming law; path surface disjoint |
| `daily.yml` nightly engine lane | scheduled | Sole lawful producer of collection evidence; never manually dispatched/rerun/cancelled to manufacture proof |

## Next action

1. ~~Land PR `#6452`~~ **done** — merged `2e0234d94b9381b033f4fe7585a75f5da59335ef`.
2. Capture the provider's own `endDate` into `period_end` and make the lineage
   pass rollover-aware, before first re-observation
   (`DSC:SRC-A1-FISCAL-ANCHOR-IS-ON-THE-PAYLOAD`). Without it, a quarter that
   rolls between observations is recorded as an analyst revision — mutation
   gate 3 — and the first opportunity to violate it arrives at cursor wrap.
3. At cursor wrap (**expected on or after 2026-09-01**; `A`→`BOH` collected
   2026-08-25, `_FRESH_DAYS = 6`, 7.5-night cycle), re-run the SRC-A1P audit on
   the first collection containing genuine same-security re-observations, and
   test the five currently-unexercised invariants.
4. Only on a clean wrap-night audit does SRC-A1 become `PROVEN_LIVE` and EXP-1
   become eligible, after a fresh collision census.

Waiting for the natural wrap is the lawful path. Widening cadence, batch size
or universe to force an overlap sooner is a mutation the frozen contract gates
behind operating evidence and must not be done to obtain proof faster.
