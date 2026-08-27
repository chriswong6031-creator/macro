---
workstream: "WS:EARNINGS-EVENT-INTELLIGENCE-COMPILER"
session: sol/tfg0-transcript-format-census-20260827-initial
model: sol
ended_because: complete
mission: >
  Pre-register a transcript-format generalization development corpus before opening new transcript
  bodies, measure the unchanged deterministic Q&A compiler across that independent corpus, freeze an
  eight-revision metadata-only holdout, and produce the first transcript-local source-evidence
  architecture without modifying runtime code or consuming GOOGL/CAT/BAC/SNOW as fresh acceptance data.
state_before: >
  E3-B was PROVEN_LIVE on AAPL. The frozen GOOGL E3-C second-event attempt had exposed a genuine
  source-format refusal and was still being repaired under HOLD-FOR-SOL on PR #6497. GOOGL's failure
  cues were therefore development-visible and could not lawfully be used as a repaired OOS pass.
prs:
  - 6521
decisions:
  - DEC:E3FMT-TRANSCRIPT-LOCAL-SOURCE-EVIDENCE-NORMALIZATION
  - DEC:E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT
changed:
  - path: research/earnings_intelligence/e3/TFG0_TRANSCRIPT_FORMAT_GENERALIZATION_PREREG_2026-08-27.md
    what: >
      Froze the development-corpus selection law before body inspection: live transcript index,
      exact advertised SHA, bounded date/period eligibility, exclude AAPL/GOOGL/GOOG/CAT/BAC/SNOW,
      sort by deterministic TFG0 hash and take the first 16.
  - path: research/earnings_intelligence/e3/tfg0_transcript_format_development_corpus_selection.json
    what: >
      Recorded the exact 16 development revisions selected from 2,909 eligible held revisions with
      zero selected-body inspection before freeze.
  - path: research/earnings_intelligence/e3/tfg0_transcript_format_census_receipt.json
    what: >
      Recorded 16/16 byte replay, 0/16 success through the unchanged deterministic compiler, role
      sparsity and terminal-cue diversity across the independently frozen development corpus.
  - path: research/earnings_intelligence/e3/tfg1_transcript_format_holdout_selection.json
    what: >
      Froze eight further metadata/SHA-ranked revisions as an unseen format holdout; their bodies
      were not opened by TFG-0.
  - path: agentos/decisions/DEC-E3FMT-TRANSCRIPT-LOCAL-SOURCE-EVIDENCE-NORMALIZATION.md
    what: >
      Froze the first transcript-local source-evidence normalization architecture: no terminal-phrase
      admission authority, no external person lookup, no new store/control plane, and same-revision
      role evidence only.
verified:
  - claim: Development corpus selection was frozen before body inspection.
    command: >
      GitHub Actions run 33042834588 freeze job 98420076116 plus
      research/earnings_intelligence/e3/tfg0_transcript_format_development_corpus_selection.json.
    result: >
      2,909 eligible revisions; exact ranks 1-16 selected by the pre-registered hash law;
      bodies_inspected_before_freeze=0.
  - claim: All selected development source revisions byte replayed and the unchanged compiler failed on all 16.
    command: >
      GitHub Actions artifacts 9634504377 and 9634565138 from run 33042834588.
    result: >
      16/16 byte replay; 0/16 unchanged-compiler success; 11 operator_intro_identity_unparsed and
      5 zero_qa_boundaries.
  - claim: The separate format holdout was frozen without opening its bodies.
    command: >
      GitHub Actions run 33043554816 job 98422311316 and artifact 9634756392.
    result: >
      Exact ranks 17-24 recorded by pair + SHA only; bodies_inspected=0.
unverified:
  - TFG-1 implementation behavior is not built or claimed by this handoff.
  - The eight frozen holdout bodies remain intentionally unopened and therefore uncharacterized.
unresolved:
  - >
    The first architecture draft could not yet know how many development calls were independently
    source-clean for all-or-nothing reconstruction, nor how explicit analyst proxies and source-role
    conflicts should score. Those questions were resolved later in the R1 continuation handoff and
    R1 decision; this initial record is historical input, not the active implementation packet.
next_actions:
  - >
    Follow `agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-27-tfg0-r1.md`
    and the R1 architecture amendment for final TFG-0 acceptance. Do not execute the initial numeric
    breadth bars from this historical stage.
do_not_redo:
  - Do not reselect the 16-call development corpus after seeing body/parser outcomes.
  - Do not open or replace the frozen eight-call holdout during TFG-0.
  - Do not use GOOGL, CAT, BAC or SNOW as TFG development bodies.
  - Do not interpret the unchanged 0/16 result as authority to add ticker/provider-specific parser branches.
danger_areas:
  - >
    This initial stage recorded provisional >=12/16 and >=6/8 outcome bars before source-only
    adjudication was complete. Those bars are superseded by the R1 source-conditioned law and must
    never be used to pressure identity guessing or partial publication.
  - >
    Segment role metadata is incomplete and sometimes conflicts with explicit same-revision title
    text. A future compiler must treat it as evidence, not unquestioned truth.
---

# TFG-0 initial handoff — historical stage

This handoff preserves the first anti-leakage selection/census stage. The active continuation and
implementation law is the later R1 handoff:

`agentos/handoffs/EARNINGS-EVENT-INTELLIGENCE-COMPILER-2026-08-27-tfg0-r1.md`

Git history preserves the original draft in full. The replacement above intentionally removes stale
numeric bars from the active text while keeping the measurements and selection provenance recoverable.
