---
workstream: "WS:CRYPTO-INTELLIGENCE"
session: sol/crypto-p0a-close-p0b-commission
model: sol
ended_because: complete
mission: >
  Close P0A at its accepted PROVEN_LIVE boundary, reconcile the stale Agent OS
  record to immutable GitHub truth, freeze the P0B Crypto H5 authority repair and
  commission exactly one bounded implementation attempt without starting alerts,
  a new crypto optimizer or broader cockpit redesign.
state_before: >
  P0A PR #6294 was already merged and accepted PROVEN_LIVE, but the canonical
  workstream still described merge, canonical render and production acceptance as
  outstanding and kept P0B todo. Current H5 already told users that Bitcoin Vector
  sets total crypto exposure, while scripts/build_crypto.py still derived that
  budget directly from signals.alloc_optimal and therefore bypassed the P0A
  btc.decision/v1 integrity projection.
changed:
  - path: agentos/workstreams/WS-CRYPTO-INTELLIGENCE.md
    what: >
      Closed stale P0A release residue with exact merge/current-main receipts,
      moved P0B to in_progress and set the next action to Executive OS admission
      of one implementation carrier followed by bounded H5 authority closure.
  - path: agentos/decisions/DEC-CRYPTO-H5-BTC-BUDGET-AUTHORITY.md
    what: >
      Froze P0B authority law: H5 total budget must consume the canonical final
      btc.decision/v1 state, the class overlay may only split it, and unavailable
      authority must fail closed without a raw-signal fallback.
  - path: agentos/discoveries/DSC-CRYPTO-H5-BYPASSES-BTC-DECISION.md
    what: >
      Recorded the falsifiable current-state defect that H5 reads alloc_optimal
      directly and can therefore remain actionable when the canonical decision is
      integrity-unavailable.
  - path: agentos/handoffs/CRYPTO-INTELLIGENCE-2026-08-24-p0a-close-p0b-commission.md
    what: >
      Provides the cold-stranger implementation packet, acceptance boundary,
      failure cases and exact continuation action for P0B.
verified:
  - claim: >
      P0A release is merged and its exact release carrier had successful CI,
      fence and authority runs before merge.
    command: >
      GitHub fetch PR #6294, its release discussion and merge metadata.
    result: >
      Accepted source 9ce6ce711602f6bb4986ed59ea84d70b704f3eac; reconciliation
      head e573a341e406532748a9ba62e69e8c5444341630; successful CI run
      32706692720, fence run 32706692694 and authority run 32706690630; merged
      2026-08-24T09:02:31Z as f039c86ae037cf75238cfdd1f3d732d9b643dbb7.
  - claim: >
      Current canonical main still renders the P0A governed Bitcoin decision
      projection rather than the retired split-brain action path.
    command: >
      GitHub fetch site/vector.html at main ce4a33aeeed779530942560c5b05f4df8ab0306c
      and inspect the S2 decision markers and copy.
    result: >
      btc.decision/v1, decision status ok, final exposure 100, HOLD 100% BTC / 
      持有 100% BTC and one action / one sizing source are present in the canonical
      generated page.
  - claim: >
      Current H5 bypasses P0A DecisionState for its total budget.
    command: >
      GitHub fetch scripts/build_crypto.py at main
      ce4a33aeeed779530942560c5b05f4df8ab0306c and inspect _allocation() plus its
      caller in main().
    result: >
      main() reads store.read("vector", "signals"); _allocation() assigns total
      exposure from latest["alloc_optimal"] and only then applies the BTC/ETH/alt
      split. It does not consume btc.decision/v1 status/final authority.
  - claim: >
      H5's user-facing contract already says Vector owns total exposure and the
      class overlay only splits it.
    command: >
      GitHub fetch site/crypto.html at main
      ce4a33aeeed779530942560c5b05f4df8ab0306c and inspect data-shelf="H5".
    result: >
      H5 renders Allocation / 配置, says Bitcoin Vector sets total crypto exposure
      and the class overlay only splits it, and currently shows a four-way budget.
  - claim: >
      Existing production/render orchestration supports a same-render authority
      bridge without a new store.
    command: >
      GitHub fetch .github/workflows/render.yml and config/dag.yml at main
      ce4a33aeeed779530942560c5b05f4df8ab0306c and inspect build order.
    result: >
      build_vector precedes build_crypto in the all and macro render scopes and in
      the declared nightly/render DAG; existing notes already state the crypto
      cockpit consumes same-render E0 BTC authority.
  - claim: >
      No open P0B/H5 crypto-allocation implementation carrier existed when this
      commission carrier was created.
    command: >
      GitHub search open macro PRs for P0B H5 crypto allocation and crypto.html
      allocation, then fetch main immediately before branch creation.
    result: >
      No matching open PR; main was exactly
      ce4a33aeeed779530942560c5b05f4df8ab0306c.
unverified:
  - claim: >
      A P0B implementation Job/Attempt/Worker has been admitted by Executive OS.
    what_would_verify: >
      A canonical Executive OS admission receipt binding one P0B logical operation
      to one implementation carrier and worker/attempt identity. No such runtime
      mutation was made by this records/commission session.
  - claim: >
      P0B source implementation, exact-head tests, merge, canonical render and real
      production H5 proof are complete.
    what_would_verify: >
      The bounded implementation PR, exact-head CI/authority evidence, normal merge,
      canonical render receipt and desktop/mobile EN/ZH light/dark proof from the
      real H5 production surface.
  - claim: >
      The public Vector URL was independently re-fetched during this reconciliation.
    what_would_verify: >
      A successful external HTTP/browser read of the public Vector URL from an
      environment with working route/DNS. The current Sol environment timed out,
      so no duplicate live receipt was fabricated.
unresolved:
  - >
    Executive OS still must perform the actual P0B Job/Attempt/Worker admission.
    Agent OS commissioning is complete, but QUEUED or EXECUTING must not be claimed
    until that separate runtime receipt exists.
next_actions:
  - >
    Through Executive OS, admit exactly one P0B implementation attempt on one new
    implementation carrier after rechecking current main and open PR/path collision.
  - >
    Start with failing tests in the existing crypto test family. Cover: happy-path
    final exposure and split reconciliation; unexplained raw/final mismatch;
    corrupt most-recent prior allocation; active named override; unavailable/null
    DecisionState; EN/ZH parity; stable data-shelf="H5"; and a static guard proving
    H5 no longer derives its total budget from latest["alloc_optimal"].
  - >
    Extend the existing same-render crypto.cockpit/v1 projection or its existing
    producer/consumer seam so the already-built P0A DecisionState status, as_of and
    final exposure reach build_crypto/H5. Do not create btc_decision.json, a new
    allocation store or another decision lifecycle.
  - >
    Keep the existing deterministic alt-cycle/class overlay limited to splitting an
    available final exposure. BTC + ETH + alts must reconcile to final governed
    exposure and cash must reconcile to 100 minus that exposure; no overlay input may
    originate or rescue the total budget.
  - >
    Run focused decision/crypto tests, Agent OS validation, contract/CI ownership
    checks required by the changed test/import surface, then obtain exact-head hosted
    CI and browser proof on desktop/mobile, light/dark and EN/ZH. After merge, wait
    for the canonical render and verify the real production H5 before asking Sol for
    final acceptance.
  - >
    Return the PR and evidence to Sol and stop. The worker may not self-accept P0B or
    continue into alerts, navigation, asset-model promotion or broader redesign.
do_not_redo:
  - >
    Do not reopen P0A. PR #6294 and its PROVEN_LIVE decision boundary are accepted.
  - >
    Do not restore the retired midterm calendar veto or make legacy btc_recommend,
    Kelly, categorical momentum or a new crypto score a decision-bearing budget owner.
  - >
    Do not create a second DecisionState file/store merely to bridge Vector and H5;
    the existing build order and crypto.cockpit/v1 projection provide the seam to
    extend.
  - >
    Do not expand P0B into alerts, a crypto-wide optimizer, recommender removal,
    ETH/alt statistical promotion, navigation or full cockpit redesign.
  - >
    Do not call green CI, a merge or canonical render final acceptance; the real H5
    production user journey must be proven separately.
danger_areas:
  - >
    Happy-path equality is misleading: a direct alloc_optimal read often yields the
    same number as btc.decision/v1. The repair is only proven when adversarial
    integrity-invalid states make H5 unavailable too.
  - >
    `crypto.cockpit/v1` already exists and the nightly/render DAG deliberately runs
    build_vector before build_crypto. Creating another persistent JSON authority
    would duplicate rather than repair this seam.
  - >
    Decision and class-overlay clocks must remain visible. H5 must carry the governed
    decision as_of; a missing/unavailable decision cannot be replaced by a fresher
    market-board input or by yesterday's allocation.
  - >
    Rounding may be presentation-only. The implementation must reconcile on the
    authoritative exposure value before display rounding so BTC/ETH/alts/cash cannot
    silently create or destroy budget.
  - >
    Generated site pages are publication artifacts and are continuously regenerated.
    Reconcile generated-byte ownership at release instead of using generated HTML as
    the source of decision authority.
decisions:
  - "DEC:CRYPTO-H5-BTC-BUDGET-AUTHORITY"
discoveries:
  - "DSC:CRYPTO-H5-BYPASSES-BTC-DECISION"
---

# Crypto Intelligence — P0A close / P0B commission handoff

## §0 State — what is true right now

P0A is closed at its accepted PROVEN_LIVE boundary. PR #6294 merged the governed
`btc.decision/v1` authority and current canonical main still renders one final BTC
action and one sizing source. The stale durable record that still described merge
and production acceptance as pending has been corrected.

P0B is separately commissioned and marked `in_progress` in Agent OS, but no Executive
OS Job/Attempt/Worker admission has been claimed. Its exact target is Crypto H5, not a
new page: H5 already exists and already tells the user that Bitcoin Vector owns total
crypto exposure. The defect is that its builder independently rereads the raw final
allocation column instead of honoring the governed DecisionState eligibility boundary.

## §1 What is LEFT — in order

### 1. Runtime admission and authority precedence

Executive OS must admit one logical P0B operation to one implementation carrier.
Immediately before admission, re-fetch Macro `main` and search open PRs touching the
P0B paths. Do not reuse this records-only branch as the implementation carrier.

Authority order for implementation is:

1. Chairman's current P0B commission and the current protected Sol skillpack.
2. `DEC:CRYPTO-H5-BTC-BUDGET-AUTHORITY` for the frozen decision boundary.
3. `research/CRYPTO_COCKPIT_MASTERPLAN.md` for the established H5 product contract and
   no-premature-signal-authority law.
4. `engine/btc_decision.py` and merged PR #6294 for P0A contract semantics.
5. Current repository code and tests for implementation facts.

Older handoffs are context, not permission to widen scope.

### 2. Complete user journey

A user opens Crypto Intelligence and reaches H5 Allocation. When the canonical Bitcoin
DecisionState is `ok`, H5 shows exactly one total crypto exposure inherited from that
DecisionState, then explains how the existing class overlay splits the available budget
among BTC, ETH and altcoins. Cash is the residual. The user can trace the budget back to
Vector authority and never encounters a second target or contradictory action.

When DecisionState is unavailable, H5 must visibly become unavailable/non-actionable.
It must not display a stale four-way target, silently convert unavailable to 0%, recompute
from raw signals, or use another model as a substitute. Bilingual copy must carry the same
numeric and authority meaning.

### 3. Data, contract, time, null and correction behavior

`btc.decision/v1` remains the only decision-bearing total-budget contract. The minimum
load-bearing fields for H5 are decision `status`, `as_of`, integrity eligibility and final
exposure. Preserve the exact final fractional exposure for reconciliation; display rounding
is presentation only.

The existing `crypto.cockpit/v1` same-render projection is the preferred transport seam.
`build_vector` already precedes `build_crypto` in both nightly and normal render lanes. Extend
that existing projection additively or pass the already-built DecisionState through the
existing producer/consumer boundary. Do not create another durable allocation or lifecycle
store.

Null/unavailable means no decision-bearing H5 budget. An explained active named override may
produce a valid final exposure because P0A already owns that correction seam. An unexplained
raw/final mismatch, corrupt latest prior allocation, invalid range or other P0A integrity
failure must propagate as unavailable. A fresher class-market input does not repair a stale,
missing or invalid decision authority.

### 4. Deterministic, statistical and model-generated methods

The authoritative total budget is deterministic projection from the P0A final allocation
contract. The existing alt-cycle regime, ETH/BTC signal and class grid may remain statistical
or deterministic context exactly as they are today, but their authority class is split-only:
they choose proportions inside an already-authorized budget and cannot set total exposure.

No LLM summary, sentiment, new optimizer, recommendation object, Kelly receipt or categorical
momentum state may originate, rank, size, gate or rescue the total H5 budget in P0B.

### 5. Failure states and acceptance tests

The implementation is not accepted unless tests prove at least these states:

- valid decision, including 100% happy path: H5 total equals the exact governed final exposure;
- active named override: H5 uses the governed final exposure, not raw pre-override exposure;
- unexplained raw/final mismatch: H5 is unavailable and has no target split;
- invalid most-recent non-null prior allocation: H5 is unavailable and does not search older rows;
- missing/null/out-of-range DecisionState: fail closed, no stale or zero fallback;
- reconciliation: BTC + ETH + alts equals final exposure before display rounding and cash equals
  100 minus final exposure;
- source guard: H5 budget production code no longer derives total exposure from
  `latest["alloc_optimal"]`;
- stable H5 selector and bilingual numeric parity remain intact.

Then prove the real user journey in the browser at relevant desktop/mobile breakpoints, light
and dark themes, English and Chinese. After merge, require the canonical render and production
H5 proof before Sol final acceptance.

### 6. Stop condition

Stop after one independently useful P0B vertical: H5 total-budget authority is singular,
fail-closed and proven end to end. Return the PR and evidence to Sol. Do not self-merge or
continue into adjacent product work unless separately authorized by the current release law.

## §2 What will bite you

The most dangerous false positive is a successful happy-path screenshot. H5 and Vector often
show the same percentage today because both ultimately touch `alloc_optimal`; that does not
prove a shared authority boundary. Only adversarial invalid states demonstrate whether H5
actually honors P0A's eligibility contract.

The second trap is architectural convenience. A new `btc_decision.json` looks simple but would
create another persistent truth surface even though the pipeline already renders Vector before
Crypto and already has `crypto.cockpit/v1` as the same-render display contract. Extend the
existing seam instead.

The third trap is rounding. Split math must reconcile using the authoritative fractional
exposure, then round for display. Do not let three rounded risk buckets plus cash become a new
budget by accident.

## §3 What was decided and found

`DEC:CRYPTO-H5-BTC-BUDGET-AUTHORITY` — H5 inherits the governed final Bitcoin DecisionState as
its total crypto budget; the class overlay is split-only and unavailable fails closed.

`DSC:CRYPTO-H5-BYPASSES-BTC-DECISION` — current H5 bypasses P0A integrity by directly reading
`signals.alloc_optimal` for total exposure.

## §4 Not in scope — do not adopt

P0B does not reopen or modify the accepted P0A thesis. It does not build alerts, remove the
legacy recommender everywhere, redesign the full crypto cockpit, create an ETH/alt trading
model, promote descriptive class signals into sizing authority, change navigation, or create a
new portfolio optimizer. Those require separate product/research authority and separate waves.