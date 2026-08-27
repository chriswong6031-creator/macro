---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: sol/tfg1-v1-falsifier-adjudication-20260827
model: sol
ended_because: ci_handoff
mission: >
  Adjudicate the TFG-1 v1 development-gold falsifier, preserve its scientific stop, correct only
  the three omitted structural handoffs in durable machine gold, and leave one bounded R2
  implementation operation while keeping the unseen holdout sealed and E3 production gates locked.
state_before: >
  TFG-0 had frozen a 110-separator development adjudication and eight-slot unopened holdout. TFG-1
  v1 faithfully recovered all 110 frozen separators and found three additional combined
  Q&A-opener-plus-first-question handoffs omitted by the gold: MBLY #21, ARRY #31 and KREF #15.
  The worker stopped before compiler implementation freeze or holdout access and returned PR #6555
  asking Sol to rule on the corrected counts, MBLY classification and successor operation.
prs:
  - 6497
  - 6521
  - 6555
decisions:
  - DEC:E3C-GOOGL-OOS-REFUSAL-SPENDS-EVENT
  - DEC:E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT
  - DEC:E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS
discoveries:
  - DSC:TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES
changed:
  - path: research/earnings_intelligence/e3/tfg1_development_boundary_identity_adjudication_r2.json
    what: >
      Sol-ratified R2 machine gold preserving all original TFG-0 adjudication except the three
      demonstrated first-handoff omissions and their mechanically resulting partition: 113
      separators, 97 direct, 6 proxy, 103 supported, 10 unresolved, nine source-clean calls.
  - path: agentos/decisions/DEC-E3FMT-DEVELOPMENT-GOLD-R2-FIRST-HANDOFF-OMISSIONS.md
    what: >
      Records Sol's partial gold correction. R1 method/identity/role/holdout/no-production law
      remains controlling; only the erroneous counts and MBLY source-clean classification change.
  - path: research/earnings_intelligence/e3/TFG1_R2_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-27.md
    what: >
      Sole active successor implementation packet using new operation key
      tfg1-r2-deterministic-transcript-format-hardening-20260827-v1, corrected RED/GREEN gates,
      unchanged single-use holdout law, and current Chairman pre-work Slack ACK envelope law.
  - path: agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-27-tfg1-r2-ready.md
    what: >
      This continuation supersedes the unresolved organizational state in the prior TFG-1 falsifier
      handoff by recording Sol's ruling and exact next operation. The prior handoff remains historical
      evidence of the worker stop.
verified:
  - claim: "The three disputed segments are genuine structural separators under already-binding TFG law."
    command: >
      Sol compared the original frozen tfg0_development_boundary_identity_adjudication.json with
      TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_ARCHITECTURE_FREEZE_2026-08-27.md,
      TFG0_R1_BOUNDARY_IDENTITY_AND_HOLDOUT_SCORING_AMENDMENT_2026-08-27.md, and PR #6555's exact
      source excerpts for MBLY #21, ARRY #31 and KREF #15.
    result: >
      All three satisfy the frozen question-bearing Operator-handoff plus immediate
      non-housekeeping-turn separator law. The original gold omitted them inconsistently.
  - claim: "The corrected R2 partition is mechanical rather than a new outcome threshold."
    command: >
      Start from the original 110/95/6/101/9 partition; add ARRY #31 and KREF #15 as direct exact
      matches and MBLY #21 as unresolved while preserving every original per-call label.
    result: >
      113 structural / 97 direct / 6 proxy / 103 supported / 10 unresolved. MBLY becomes non-clean,
      reducing source-clean calls from 10 to exactly 9; the remaining non-clean set has 7 calls.
  - claim: "TFG-1 v1 preserved the scientific stop and did not spend the holdout."
    command: >
      Review PR #6555 exact head 0b98a2c9c0ff234549bb64aec40b3868255441bf and its falsifier receipt.
    result: >
      No engine/compiler source change, no implementation head freeze, holdout_bodies_inspected=0,
      zero model calls, AAPL-only production admission unchanged, no CAT/BAC/SNOW or fresh OOS work.
  - claim: "The transcript replay discovery prevents a false COF revision-mismatch stop."
    command: >
      PR #6555 measurement compares raw decompressed hashing with TFG-0 canonical JSON
      re-serialization hashing against the frozen index.
    result: >
      Canonical JSON replay is 16/16; raw decompressed hashing alone false-fails COF/2026Q2.
  - claim: "Current main did not introduce an E3/Q&A/compiler collision after #6555 pickup."
    command: >
      Compare #6555 pickup base a50f4998bf02484b858fb2cdddbea0a53ab12d01 to current main during Sol review.
    result: >
      No research/earnings_intelligence/e3, engine/company_intelligence, or E3 workstream path moved.
      A newer Chairman decision did add the initial-envelope pre-work Slack ACK rule, and R2 handoff
      incorporates it for any future Slack worker handoff.
unverified:
  - claim: "TFG-1 R2 compiler implementation satisfies the corrected development gates."
    what_would_verify: >
      A new bounded worker operation implementing under RED-first TDD and returning exact 16-call
      evidence with 113/103/10/9/7 gates green plus AAPL 7/26/68.
  - claim: "The eight-slot unseen holdout is adequately powered and passes the frozen R2 compiler."
    what_would_verify: >
      Only after corrected development gates are green and exact implementation head is frozen may
      the eight bodies be opened, source-adjudicated before compiler output, and scored once.
unresolved:
  - >
    R2 implementation performance is unknown. The holdout source-clean count and compiler result are
    intentionally unknown because the holdout remains sealed.
  - >
    Parent E3-C remains incomplete even if TFG-1 R2 later succeeds; a fresh untouched-production-OOS
    operation is still required for closure.
next_actions:
  - >
    Complete Sol exact-head review/CI of PR #6555 after the records-only R2 canonicalization and merge
    it only if the final changed surface remains records/research-only and hosted CI/fences/active
    ci-authority are green.
  - >
    After #6555 lands, commission exactly one strong frontier coding worker on
    research/earnings_intelligence/e3/TFG1_R2_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-27.md
    under new operation key tfg1-r2-deterministic-transcript-format-hardening-20260827-v1.
  - >
    If that worker is handed off via Slack, the initial envelope must require the exact ACK before
    work, full-thread read, and no execution before both steps; Slack ACK remains transport evidence only.
  - >
    Do not start fresh E3-OOS2 or E3-P unless/until Sol independently accepts a successful R2 return.
do_not_redo:
  - "Do not edit the historical TFG-0 adjudication to conceal the 110-separator falsifier."
  - "Do not reuse operation key tfg1-deterministic-transcript-format-hardening-20260827-v1; it terminated at the accepted development-gold falsifier."
  - "Do not reopen or rerank the 16-call development corpus."
  - "Do not open, replace, skip or rerank the eight holdout bodies before R2 implementation-head freeze."
  - "Do not infer MBLY #21 identity via fuzzy names, initials, external biography or placeholder repair."
  - "Do not inspect CAT/BAC/SNOW or use GOOGL as clean OOS evidence."
  - "Do not widen production AAPL-only revision admission, register Alphabet, create another Q&A/person/transcript/model/control plane, or start E3-P."
  - "Do not raw-byte hash decompressed transcript bodies as the TFG revision identity gate; use the canonical-JSON convention recorded by the discovery."
danger_areas:
  - >
    Pre-registration does not require preserving a proven label error. The lawful correction changes
    only source truth that contradicts the already-frozen method; it does not tune the method to a
    desired compiler outcome.
  - >
    MBLY #21 is both structurally real and person-unresolved. Dropping it would contaminate geometry;
    guessing identity would violate source support. R2 must preserve separator-only refusal.
  - >
    The unseen holdout is single-use. Any body inspection before implementation freeze or any code
    change after unseal invalidates the R2 operation and requires stop/return rather than rescue.
  - >
    A TFG-1 R2 pass is method-hardening evidence only. It is not second-issuer production proof and
    cannot close E3-C or unlock E3-P.
---

# TFG-1 R2 ready continuation

Sol accepted the v1 development-gold falsifier and ruled YES on all three worker questions. The
historical 110-boundary gold remains preserved as falsified evidence; the R2 machine adjudication is
the sole grading truth for the successor implementation.

**Current capability state:** TFG-0 `SPEC_ONLY`; TFG-1 v1 `STOPPED_AT_DEVELOPMENT_GATE` with valid
negative scientific evidence; TFG-1 R2 `NOT_BUILT`; E3-C in progress; E3-P locked.

The exact next operation is `tfg1-r2-deterministic-transcript-format-hardening-20260827-v1` using
`research/earnings_intelligence/e3/TFG1_R2_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-27.md`.
