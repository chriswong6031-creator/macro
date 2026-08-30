---
workstream: WS:FUNDAMENTAL-FORENSICS
session: sol/ff-fif-recovery-reconcile-20260829
model: sol
ended_because: continuation
mission: >
  Reconcile the combined Fundamental Forensics + Financial Intelligence Fabric
  program after the ANGO source-law repair landed, restore current-quarter broad
  SEC production health without widening source budgets, and leave the exact
  historical recovery continuation recoverable from Agent OS rather than chat.
state_before: >
  Agent OS still described FF-1R as PARKED / HOLD-FOR-SOL on PR #6391 even
  though #6391 had already merged. The frozen July recovery plan remained at
  cursor/completed 0 with backlog 2,571. A scheduled current-quarter incremental
  run had also become DEGRADED on aggregate Company Facts run-budget exhaustion.
changed:
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: >
      Reconcile #6391 as ON_MAIN, record the five-attempt bounded live incremental
      drain to a complete 2,842/2,842 census, preserve the untouched July recovery
      checkpoint, and keep previous-quarter reconciliation plus FF-2 locked.
  - path: agentos/handoffs/FUNDAMENTAL-FORENSICS-2026-08-29-FF-FIF-RECOVERY-RECONCILIATION.md
    what: >
      Preserve exact production receipts, capacity/credential gates, no-rebuild
      boundaries, and the next lawful operation for a fresh Sol/COO session.
verified:
  - claim: ANGO representational-equivalence source law is merged on main.
    evidence: >
      Macro PR #6391 merged as a8075391fa895ec706976cd9cb9238c7e4cbdaea;
      DEC:FF-1-ACCEPTANCE-DATETIME-COMPARES-BY-INSTANT is present on current main.
  - claim: Current-quarter incremental FF-1 returned to a complete production head without raising caps.
    evidence: >
      GitHub Actions run 33247138975 drained only typed aggregate Company Facts
      queue_overflow partials on the same workflow carrier: run_f14d89994239f7cd7583
      backlog 42; run_c6059aa15979d46bc4e7 backlog 32;
      run_3923c15f657b40a64afa backlog 20; run_13bf80ca9b8550495053
      backlog 8; final attempt-5 job 99190103903 / run_0e66732e4f506b25446a
      SUCCESS with expected/observed 2842/2842, failed=0,
      companyfacts_deferred=0, recovery_backlog=0, failures=[] and
      latest-complete advanced. Latest relevant SEC accepted_at was
      2026-08-28T20:28:19.000Z.
  - claim: The aggregate Company Facts failures were bounded-resource partials, not source conflicts.
    evidence: >
      Frozen per-run aggregate budget remained 32 MiB and per-object limit 64 MiB.
      CRWD, HQY, OKTA and TECH were refused only when their lawful current snapshot
      would exceed the remaining aggregate run envelope. Existing broad-SEC tests
      require durable issuer commits, refusal to advance latest-complete on partial,
      and next-poll reuse until backlog zero.
  - claim: The July historical recovery state was not modified by current-quarter recovery.
    evidence: >
      No historical recovery workflow_dispatch was issued after #6391 landing.
      Plan e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4,
      recovery_from=2026-07-12T11:23:15Z, cursor/completed 0, backlog 2,571 and
      null last-successful recovery receipt remain the governing checkpoint.
unverified:
  - claim: Protected attested-history writer credential is ready.
    what_would_verify: >
      Metadata-only proof that protected environment secret
      R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID has updated_at later than
      2026-08-11T03:27:33Z, without reading or exposing any secret value.
  - claim: FF-1 is globally correction-safe.
    what_would_verify: >
      Backlog-zero July FF-1R completion plus production-proven previous-quarter
      weekly reconciliation and a complete composition that preserves newer
      current-incremental evidence.
unresolved:
  - >
    July FF-1R is BUILT_NOT_PROVEN. Its next run must be a NEW workflow_dispatch
    operation from the exact frozen cursor 0; old runs 32626273461 and
    32708350406 must never be rerun.
  - >
    Previous-quarter weekly reconciliation is SPEC_ONLY / NOT_BUILT, so FF-1
    cannot yet be called globally correction-safe and FF-2 remains forbidden.
  - >
    Production attested issuer admission remains blocked/unproven; FIF-3A4R is
    accepted architecture only and production issuer service remains NOT_BUILT.
  - >
    Fable remains the Chairman-preferred sustained COO for the combined program,
    but contemporaneous placement census found no unambiguous idle Fable
    principal capacity. Terra/CTO capacity was also fully occupied. Sol therefore
    retained principal CEO control and used only bounded low-ambiguity child work.
next_actions:
  - >
    Sol reviews and lands this records-only reconciliation on its single carrier.
  - >
    After landing, commission exactly one NEW FF-1R recovery workflow_dispatch
    with mode=recovery and recovery_from=2026-07-12T11:23:15Z. ANGO remains the
    first cursor-zero issuer; do not skip, regenerate the plan, or move the cursor.
  - >
    Reconcile that operation's exact effect before any subsequent recovery
    dispatch; continue bounded tranches until backlog zero or a new typed blocker.
  - >
    Then implement/prove previous-quarter weekly reconciliation before unlocking
    FF-2 or production attested-history/FIF admission.
do_not_redo:
  - Do not raise MAX_COMPANYFACTS_BYTES_PER_RUN to avoid resumable partial polls.
  - Do not rerun historical workflow runs 32626273461 or 32708350406.
  - Do not normalize or rewrite exact SEC acceptance_datetime evidence.
  - Do not create a second SEC source plane, issuer identity system, financial semantic model, query kernel, metric registry, statement model, attested-history bucket/publisher, event workspace, lifecycle, queue or retry plane.
  - Do not start FIF-3A4, another golden issuer, attested W0B, or FF-2 before the source gates above are satisfied.
danger_areas:
  - >
    Current-quarter backlog=0 is not July recovery backlog=0. The field name
    recovery_backlog in incremental receipts describes deferred Company Facts
    work for that poll and must never be used to imply FF-1R completion.
  - >
    Only a backlog-zero historical final composition may advance latest-complete,
    and it must preserve the newer current-quarter evidence now proven by
    run_0e66732e4f506b25446a.
  - >
    An unclaimed Slack delivery is not active work. Do not describe Fable/Terra
    as executing this program unless a concrete receiver ACKs and STARTs.
decisions:
  - DEC:FF-1R-BOUNDED-JULY-RECOVERY
  - DEC:FF-1-ACCEPTANCE-DATETIME-COMPARES-BY-INSTANT
discoveries:
  - DSC:FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT
---

## Exact current capability state

Current-quarter EDGAR-index discovery is PROVEN_LIVE and currently complete in
production. FF-1 as a whole remains PARTIAL because historical July recovery and
previous-quarter correction coverage are still outstanding. FIF remains downstream:
FIF-1 is frozen, FIF-2 is fixture-proven, FIF-3 is in progress, FIF-3A4R is
accepted architecture / NOT_BUILT, and no production attested issuer service has
been proven.

## One coherent program law

SEC source truth and FIF intelligence/product work remain one dependency chain.
Do not let fixture semantics or customer UI advance past unresolved source/correction
truth, and do not let source-plane completion become a substitute for the actual
statement/query/forensic/product/consumer capability once those gates are cleared.
