---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: sol/tfg0-transcript-format-census-20260827-r1
model: sol
ended_because: ci_handoff
mission: >
  Finish TFG-0 after the GOOGL E3-C refusal became canonical: adjudicate structural question
  boundaries and source-supported identity on the already-frozen 16-call development corpus,
  replace impossible outcome bars with source-conditioned acceptance law, freeze a no-leak unseen
  holdout protocol, and leave one bounded TFG-1 implementation packet without modifying compiler or
  production behavior.
state_before: >
  The initial TFG-0 stage had frozen a 16-revision development corpus and eight-revision unopened
  holdout, measured the unchanged compiler at 0/16, and proposed transcript-local source evidence.
  E3-C refusal PR #6497 was still concurrent and the initial >=12/16 development / >=6/8 holdout
  outcome bars had not yet been tested against source-only identity adjudication.
prs:
  - 6521
decisions:
  - DEC:E3FMT-TRANSCRIPT-LOCAL-SOURCE-EVIDENCE-NORMALIZATION
  - DEC:E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT
changed:
  - path: research/earnings_intelligence/e3/tfg0_development_boundary_identity_adjudication.json
    what: >
      Froze source-only development truth from the 16 already-open exact revisions: 110 real
      structural question handoffs, 95 direct next-speaker matches, 6 explicit full-name proxy
      handoffs, 101 source-supported questioners, 9 unresolved separators, 2 explicit management
      role-conflict calls, and exactly 10 source-clean full-call cases.
  - path: research/earnings_intelligence/e3/TFG0_R1_BOUNDARY_IDENTITY_AND_HOLDOUT_SCORING_AMENDMENT_2026-08-27.md
    what: >
      Replaced the impossible provisional numeric outcome bars with source-conditioned development
      and holdout law, froze structural-separator semantics, explicit proxy identity, exact role
      comparison aliases, and no-post-unseal-code-change law.
  - path: agentos/decisions/DEC-E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT.md
    what: >
      Recorded Sol's R1 decision. It has higher precedence for boundary/questioner/role-equivalence
      and scoring clauses but deliberately does not use formal Agent OS supersession because the
      earlier broader transcript-local architecture remains live where not amended.
  - path: research/earnings_intelligence/e3/TFG0_QA_RESPONDENT_IDENTITY_EVIDENCE_AMENDMENT_2026-08-27.md
    what: >
      Froze a future optional nested same-revision respondent-role evidence variant while keeping
      respondent role required/source-supported and keeping TFG-1 production admission AAPL-only.
  - path: research/earnings_intelligence/e3/TFG1_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_R1_2026-08-27.md
    what: >
      Created the sole active TFG-1 implementation packet with complete TDD sequence, exact
      development/holdout gates, stop conditions, proof packet and no-production-coverage boundary.
  - path: research/earnings_intelligence/e3/TFG1_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_2026-08-27.md
    what: >
      Marked the initial implementation packet SUPERSEDED so no worker can accidentally execute its
      stale provisional breadth bars.
  - path: agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-27-tfg0.md
    what: >
      Recast the initial stage as a schema-valid historical handoff and removed stale active numeric
      bars from its body while preserving the initial anti-leakage measurements in Git history.
  - path: agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-27-tfg0-r1.md
    what: >
      This continuation record reconciles merged E3-C refusal state with TFG-0 R1 and leaves the
      exact next operation recoverable by a fresh session.
verified:
  - claim: The GOOGL E3-C refusal is canonical and still does not complete parent E3-C.
    command: >
      GitHub PR #6497 exact-head review and merge; merge SHA
      f244f0b34330cac9c98a815a3c0e97d0ba5b1d7f.
    result: >
      Accepted refusal merged; GOOGL is spent as clean OOS evidence; E3-C remains in progress and
      E3-P remains locked.
  - claim: TFG development selection was anti-leakage and exact.
    command: >
      GitHub Actions run 33042834588 jobs/artifacts 98420076116, 9634504377 and 9634565138.
    result: >
      2,909 eligible held revisions; exact ranks 1-16 selected before body inspection; 16/16 byte
      replay; unchanged deterministic compiler 0/16.
  - claim: Development source-only Q&A geometry and identity were frozen independently of compiler output.
    command: >
      GitHub Actions run 33056549015 job 98464657203 artifact 9639840320 plus
      research/earnings_intelligence/e3/tfg0_development_boundary_identity_adjudication.json.
    result: >
      110 structural handoffs; 95 direct matches; 6 explicit full-name proxies; 101 supported
      questioners; 9 unresolved separator-only handoffs; ARRY/CTRE role conflicts; 10 source-clean calls.
  - claim: The TFG-1 format holdout is frozen but its bodies remain unopened.
    command: >
      GitHub Actions run 33043554816 job 98422311316 artifact 9634756392 and current PR changed-file census.
    result: >
      Exact ranks 17-24 recorded by pair + SHA only; no holdout body fixture or holdout-body
      adjudication exists on PR #6521.
  - claim: Final TFG-0 diff is records/research only.
    command: >
      GitHub list_pr_changed_filenames for Macro PR #6521 at the current R1 carrier head.
    result: >
      Only research/earnings_intelligence/e3/* and agentos/decisions|handoffs/* paths are changed;
      no engine, script, workflow, test, config, data, Terminal or production publication path remains.
unverified:
  - TFG-1 compiler implementation is not built and no implementation success is claimed.
  - The eight frozen holdout bodies remain intentionally unopened; their source-clean power is unknown.
  - No new production issuer/Q&A coverage is claimed by TFG-0; production proof is not owed by this records-only architecture wave.
unresolved:
  - >
    Whether the frozen TFG-1 method can satisfy all 10 source-clean development calls and the unseen
    holdout remains unknown until a separate coding worker executes the R1 handoff under TDD.
  - >
    Whether the unseen eight-call holdout has at least 6 source-clean slots is intentionally unknown;
    source-only holdout adjudication happens only after the TFG-1 implementation head is frozen.
next_actions:
  - >
    Sol exact-head reviews and, only on binding green hosted CI, merges PR #6521 as SPEC_ONLY
    architecture/research. Merge does not complete E3-C.
  - >
    After #6521 lands, commission one strong frontier coding worker on
    `research/earnings_intelligence/e3/TFG1_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_R1_2026-08-27.md`.
  - >
    After a Sol-accepted TFG-1 result, commission a fresh pre-registered untouched-production-OOS
    selection/proof. Only that later OOS pass may close E3-C and make E3-P eligible.
do_not_redo:
  - Do not reselect or expand the 16-call development corpus after seeing source/parser outcomes.
  - Do not open, replace, skip or rerank the eight frozen holdout bodies before TFG-1 implementation-head freeze.
  - Do not inspect CAT/BAC/SNOW during TFG development or use GOOGL again as clean OOS acceptance.
  - Do not restore the rejected >=12/16 development outcome bar or bare >=6/8 holdout outcome bar.
  - Do not make respondent role nullable, invent generic Management, or use external/fuzzy person identity.
  - Do not create another transcript, Q&A, person, publication, model-routing or lifecycle plane.
  - Do not widen the AAPL-only production accepted-revision gate during TFG-1 and do not start E3-P.
danger_areas:
  - >
    A real question handoff may be structurally certain while its person identity is unresolved. Dropping
    the separator would merge adjacent exchanges; guessing the person would violate source-supported identity.
  - >
    Explicit proxy speakers are source-supported only under the frozen full-name on-for/sitting-in-for law.
    The principal analyst's affiliation does not automatically transfer to the proxy.
  - >
    Segment role metadata is incomplete and can contradict same-revision title text. Role comparison aliases
    are closed to CEO/CFO/COO families only; `CIO` is deliberately not an alias because it is ambiguous.
  - >
    The current Terminal consumer accepts an exact four-key respondent object. The optional roster-evidence
    variant is production-unarmed in TFG-1; a later fresh-OOS product vertical must update/verify the real
    consumer before any extended respondent publishes.
  - >
    Once TFG-1 opens the eight holdout bodies after implementation freeze, no code change is permitted on that
    operation. A miss is a falsifier/return-to-Sol, not an invitation to tune the same holdout.
---

# Earnings Event Intelligence Compiler — TFG-0 R1 continuation

TFG-0 is a records/research architecture wave only. The GOOGL refusal is already canonical. This R1
continuation freezes the method-hardening evidence, corrects the experiment scoring law, and leaves one
active implementation packet. If PR #6521 lands, classify TFG-0 as `SPEC_ONLY`, not built or proven live.

The sole active TFG-1 packet is:

`research/earnings_intelligence/e3/TFG1_DETERMINISTIC_TRANSCRIPT_FORMAT_HARDENING_HANDOFF_R1_2026-08-27.md`

Do not open the eight-body holdout before that worker freezes its implementation head. Do not inspect
CAT/BAC/SNOW. Do not start E3-P.
