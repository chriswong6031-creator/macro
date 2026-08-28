---
workstream: WS:FUNDAMENTAL-FORENSICS
session: claude/ff1r-bounded-july-recovery
model: codex
ended_because: ci_handoff
mission: >
  Implement the separately commissioned FF-1R bounded July recovery engine
  without changing FF-0, FF-2, previous-quarter reconciliation, or production
  state.
state_before: >
  FF-1P2R was PROVEN_LIVE, but FF-1R was explicitly NOT_STARTED /
  NOT_COMMISSIONED. Recovery mode failed closed with recovery_plan_required;
  the live Q3 canary indicated 2,560 relevant rows / 2,541 canonical CIKs
  after the July boundary, so a bounded plan-before-acquisition capability was
  required before any lawful recovery dispatch.
changed:
  - path: engine/fundamental_forensics/broad_sec_store.py
    what: >
      Add immutable recovery-plan binding, compact continuation cursor,
      bounded selected-CIK processing, selective historical Submissions shard
      handling, and final-only latest-complete composition.
  - path: collectors/edgar_forensics.py
    what: >
      Reuse the established SEC collector seam for bounded historical
      submissions-file retrieval without a second HTTP client.
  - path: scripts/run_fundamental_forensics_broad_sec.py
    what: >
      Bind recovery invocation to the frozen July recovery boundary and pass
      the historical retrieval seam.
  - path: .github/workflows/filing-forensics-broad-sec.yml
    what: >
      Keep the existing lane and make recovery dispatch use the frozen
      FF-1R boundary; no production dispatch was performed.
  - path: contracts/fundamental_forensics_broad_sec_run.schema.json
    what: >
      Record recovery plan identity, tranche counts and bounded acquisition
      coverage in the run receipt contract.
  - path: contracts/fundamental_forensics_broad_sec_recovery_plan.schema.json
    what: >
      Define the immutable recovery plan receipt contract.
  - path: contracts/fundamental_forensics_broad_sec_issuer_manifest.schema.json
    what: >
      Preserve current and historical Submissions component provenance in
      issuer evidence.
  - path: tests/test_fundamental_forensics_broad_sec.py
    what: >
      Exercise frozen-plan, bounded-tranche, retry, selective historical
      shard, causal-admission and final-composition cases.
  - path: tests/test_edgar_forensics_collector.py
    what: >
      Exercise exact historical submissions-file URL, byte limit, identity and
      persistence boundaries.
  - path: agentos/decisions/DEC-FF-1R-BOUNDED-JULY-RECOVERY.md
    what: >
      Record the separate bounded recovery architecture and reciprocal
      supersession of the earlier not-commissioned decision.
  - path: agentos/discoveries/DSC-FF-1R-RECOVERY-PLAN-EPOCH-IS-FROZEN.md
    what: >
      Record why recovery uses a frozen latest-complete/index plan epoch while
      the current incremental plane remains independent.
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: >
      Mark FF-1R as BUILT_NOT_PROVEN / HOLD-FOR-SOL while retaining the
      previous-quarter and FF-2 prohibitions.
verified:
  - claim: >
      The complete scoped FF-1R kernel, collector, lane and EDGAR-index battery
      passes on the reviewed local candidate, including hostile continuation,
      exact-time, byte-transport and final-composition cases.
    command: >
      python3 -m pytest -q tests/test_fundamental_forensics_broad_sec.py
      tests/test_edgar_forensics_collector.py
      tests/test_filing_forensics_broad_sec_lane.py
      tests/test_fundamental_forensics_edgar_index.py
    result: >
      Exit 0: 120 passed, 1 pre-existing sparse-checkout skip and 4 non-blocking
      fixture/temporary-cleanup warnings.
  - claim: >
      AgentOS record relationships and schema are valid after the FF-1R
      decision, discovery, workstream update and continuation handoff.
    command: python3 scripts/agentos.py validate
    result: >
      Exit 0: 582 records, 0 errors and 28 pre-existing warnings unrelated to
      FUNDAMENTAL-FORENSICS. No CI or PR receipt exists yet.
unverified:
  - claim: >
      Required GitHub CI, fences, authority and review proof accept the final
      candidate.
    what_would_verify: >
      Push a draft HOLD-FOR-SOL PR, wait for its exact-head checks, and inspect
      raw mergeability and review threads without arming auto-merge.
  - claim: >
      FF-1R recovery is production commissioned or has completed a production run.
    what_would_verify: >
      Only an explicit post-review Sol release may authorize the exactly
      bounded production procedure; none was requested or run in this session.
decisions:
  - DEC:FF-1R-BOUNDED-JULY-RECOVERY
discoveries:
  - DSC:FF-1R-RECOVERY-PLAN-EPOCH-IS-FROZEN
unresolved:
  - >
    Exact-head test, CI, fence, review and Sol acceptance receipts are still
    required. The capability remains BUILT_NOT_PROVEN / HOLD-FOR-SOL.
  - >
    Previous-quarter weekly reconciliation remains SPEC_ONLY / NOT_BUILT.
  - >
    FF-2 remains FORBIDDEN / NOT_STARTED.
next_actions:
  - >
    Commit and push the bounded capability, then open a draft PR whose body
    names HOLD-FOR-SOL and the required exact-head review/CI release condition;
    do not arm merge-on-green or native auto-merge.
  - >
    After an explicit Sol release and merge, perform only the separately
    authorized production recovery runs; otherwise stop at the HOLD.
do_not_redo:
  - >
    Do not restore recovery to #5898, a per-issuer census, submissions.zip,
    companyfacts.zip, the rejected all-pending fanout, a recovery queue, or a
    second latest pointer.
  - >
    Do not let recovery follow a mutable current index, retain a giant pending
    CIK list, advance a cursor on a failed issuer, or publish a partial tranche
    as latest-complete.
  - >
    Do not start previous-quarter weekly reconciliation, FF-2, Wave-2 changes,
    Capital Structure, Prophet, a production dispatch, or CI redesign.
danger_areas:
  - >
    `recovery_from` is exactly 2026-07-12T11:23:15Z. The plan must bind the
    sha-verified complete anchor, canonical universe, EDGAR index snapshot,
    relevant-set and candidate digest before issuer acquisition; mismatch must
    fail before SEC or Research R2 mutation.
  - >
    The 64 selected-CIK bound is not permission for unlimited historical
    fetches. Only declared date-span-matching filings.files shards may be
    retrieved, under their shard and byte caps; conflicting duplicate accession
    facts fail closed.
  - >
    Current incremental processing may publish newer evidence while recovery is
    in progress. The final recovery result must compose against that current
    complete state and preserve source-clock monotonicity; intermediate work
    must remain below latest-complete.
---

## §0 State

FF-1R bounded July recovery is locally BUILT_NOT_PROVEN and must remain
HOLD-FOR-SOL. It freezes the July recovery target from the existing complete
EDGAR evidence and progresses through bounded CIK tranches. There is no PR,
CI receipt, production dispatch, or production result in
this handoff.

## §1 What is LEFT

1. Create a draft HOLD-FOR-SOL PR without auto-merge and collect exact-head
   semantic CI, contract, fence, authority and review receipts.
2. Wait for explicit Sol release. Do not perform a recovery dispatch before
   that release; previous-quarter reconciliation and FF-2 stay out of scope.

## §2 What will bite you

The recovery plan is frozen intentionally. A later current-quarter index is
not a reason to alter the candidate sequence. A recovery retry must reject
anchor, universe, index, relevant-set, candidate or plan drift before network
work. Intermediate successful issuer data is not a complete recovery result,
so publishing it as latest-complete would discard the current incremental
plane's newer evidence.

## §3 What was decided and found

DEC:FF-1R-BOUNDED-JULY-RECOVERY supersedes the earlier decision only by
implementing the expressly separate commission; the constraints on all other
work remain. DSC:FF-1R-RECOVERY-PLAN-EPOCH-IS-FROZEN records the immutable
plan epoch and its interaction with current incremental processing.

## §4 Not in scope

No FF-0, FF-2, prior-quarter reconciliation, Wave-2, public product, Capital
Structure, Prophet, CI control-plane, production dispatch, merge, or
auto-merge policy changed. This handoff is not a production receipt.
